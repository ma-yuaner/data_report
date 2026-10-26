"""Durable notifications with CAS claims and conservative unknown delivery semantics."""
import json
import re
from datetime import datetime, timedelta
from urllib import request

from .operations import OperationsService, digest
from .policy import AdmError, has, identity, now
from .reports import ReportService
from .store import Conflict


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_wecom(endpoint, mention):
    url = endpoint["url"]
    if not re.fullmatch(r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9_-]+", url):
        raise ValueError("INVALID_ENDPOINT")
    if not mention or mention == "@all" or len(mention) > 200:
        raise ValueError("MISSING_IDENTITY")
    payload = {"msgtype": "text", "text": {"content": "数据中台ADM有待办理或需跟进事项，请登录本人工作台核对。此提醒不代表已完成处理。", "mentioned_list": [mention]}}
    body = json.dumps(payload, ensure_ascii=False).encode()
    # No arbitrary URLs, redirects, business details or static @all.
    with request.build_opener(NoRedirect()).open(request.Request(url, body, {"Content-Type": "application/json"}, method="POST"), timeout=10) as response:
        result = json.loads(response.read(65536).decode())
    return int(result.get("errcode", -1))


class NotificationWorker(OperationsService):
    def active_user(self, user_id):
        resolver = self.service.config.get("ADM_USER_RESOLVER")
        user = resolver(user_id) if callable(resolver) else None
        if not user or not user.get("is_enabled", True) or user.get("must_change_password"):
            return None
        if not user.get("is_admin") and ("adm.view" not in user.get("permissions", []) or "adm.center" not in user.get("menu_codes", [])):
            return None
        return user

    def run_once(self):
        policy = self.policy()
        actor = self.active_user(policy.get("approvedBy")) if policy.get("approvedBy") else None
        if not actor or not actor.get("is_admin"):
            return {"enabled": False, "reason": "NO_ACTIVE_APPROVAL"}
        stamp = now()
        instant = datetime.fromisoformat(stamp)
        tasks = self.tasks(actor)
        by_id = {item["id"]: item for item in tasks}
        created = 0
        if policy["notificationsEnabled"]:
            for task in tasks:
                owner = self.active_user(task["ownerId"]) if task["ownerId"] else None
                if not owner:
                    continue
                due = datetime.fromisoformat(task["dueAt"]) if task["dueAt"] else None
                severity = "OVERDUE" if task["overdue"] else "DUE_SOON" if due and policy["leadMinutes"] and due - instant <= timedelta(minutes=policy["leadMinutes"]) else "ASSIGNED"
                bucket = int(instant.timestamp() // (policy["repeatMinutes"] * 60)) if policy["repeatMinutes"] and severity == "OVERDUE" else 0
                recipients = [(owner, False)]
                if due and task["overdue"] and policy["escalationMinutes"] and instant - due >= timedelta(minutes=policy["escalationMinutes"]):
                    case = self.service.store.get(task["caseId"])
                    coordinator = self.active_user(case.get("coordinatorId", case["createdBy"]))
                    if coordinator and self.service._full(coordinator, case) and identity(coordinator) != identity(owner):
                        recipients.append((coordinator, True))
                for recipient, escalation in recipients:
                    for channel, endpoint in [("IN_APP", "")] + [("WECOM", value) for value in policy["endpointIds"]]:
                        key = "notice-" + digest([task["id"], task["round"], task["status"], task["ownerId"], task["dueAt"], identity(recipient), severity, bucket, policy["version"], channel, endpoint])
                        if self.store.get(key):
                            continue
                        record = dict(id=key, kind="NOTICE", channel=channel, recipientId=identity(recipient), taskId=task["id"], taskStatus=task["status"], round=task["round"],
                                      caseId=task["caseId"], lineId=task["lineId"], dueAt=task["dueAt"], sourceOwnerId=task["ownerId"], escalation=escalation,
                                      title="ADM待办升级提醒" if escalation else "ADM待办提醒", body="请登录工作台核对本人待办；已读不代表处理完成。", url=task["url"],
                                      createdAt=stamp, readAt=None, policyVersion=policy["version"], endpointId=endpoint, attempts=0,
                                      status="DELIVERED" if channel == "IN_APP" else "QUEUED", errorCode=None)
                        if self._valid(recipient, record, by_id):
                            try:
                                self.store.save(record)
                                created += 1
                            except Conflict:
                                pass
        self.deliver(actor, policy, by_id)
        if policy["snapshotsEnabled"] and instant.strftime("%H:%M") >= policy["snapshotAt"]:
            key = "daily-" + stamp[:10] + "-" + str(policy["version"])
            marker = self.store.get(key)
            if not marker:
                # CAS reservation: a crash is visible as UNKNOWN and never invents a second daily capture.
                try:
                    marker = self.store.save(dict(id=key, kind="SCHEDULE", status="CAPTURING", createdAt=stamp))
                except Conflict:
                    marker = None
                if marker:
                    try:
                        report = ReportService(self.service).capture(actor, {"reason": "已批准的每日定时快照；仍待人工核对发布"})
                        marker.update(status="CAPTURED", reportId=report["id"])
                        self.store.save(marker, marker["version"])
                    except Exception:
                        marker["status"] = "UNKNOWN"
                        self.store.save(marker, marker["version"])
                        raise
        return {"enabled": policy["notificationsEnabled"], "created": created}

    def _valid(self, user, row, tasks):
        task = tasks.get(row["taskId"])
        if not task or task["status"] != row["taskStatus"] or task["dueAt"] != row.get("dueAt") or task["round"] != row["round"] or task["ownerId"] != row["sourceOwnerId"]:
            return False
        try:
            case = self.service._read(user, row["caseId"])
            line = self.service._line(case, row["lineId"])
            self.service._line_access(user, case, line)
            if row.get("escalation"):
                return has(user, "adm.assign") and self.service._full(user, case) and str(case.get("coordinatorId", case["createdBy"])) == identity(user)
            if task["kind"] in {"COLLABORATION", "REMEDIATION"}:
                from .collaboration import task_actions
                collaboration = next((item for item in line.get("collaborations", []) if item["id"] == task.get("taskId")), None)
                expected = "collaboration_review" if task["status"] == "PENDING_REVIEW" else "collaboration_accept" if task["status"] == "PENDING_ACCEPT" else "collaboration_submit"
                return bool(collaboration and identity(user) == task["ownerId"] and expected in task_actions(user, case, line, collaboration, self.service._full(user, case)))
            permission = {"ASSIGN": "adm.assign", "REVIEW": "adm.review", "FINANCE": "adm.finance.confirm"}.get(task["kind"], "adm.handle")
            return has(user, permission) and identity(user) == task["ownerId"]
        except AdmError:
            return False

    def deliver(self, actor, policy, tasks):
        # Bounded queue. No silent retry of uncertain deliveries or process interruption.
        rows = self.store.list("NOTICE", int(self.service.config.get("ADM_NOTICE_SCAN_LIMIT", 1000)), channel="WECOM", statuses=["QUEUED", "SENDING"])
        for row in rows:
            if row["status"] == "SENDING":
                if datetime.fromisoformat(now()) - datetime.fromisoformat(row["claimedAt"]) > timedelta(minutes=2):
                    row.update(status="UNKNOWN", errorCode="STALE_CLAIM")
                    self._save_state(row)
                continue
            if row["status"] != "QUEUED":
                continue
            recipient = self.active_user(row["recipientId"])
            if not policy["notificationsEnabled"] or row["policyVersion"] != policy["version"] or not recipient or not self._valid(recipient, row, tasks):
                row.update(status="CANCELLED", errorCode="TASK_OR_POLICY_CHANGED")
                self._save_state(row)
                continue
            if not self.service.config.get("ADM_EXTERNAL_DELIVERY_ENABLED", False):
                continue
            resolver = self.service.config.get("ADM_ENDPOINT_RESOLVER")
            binding = self.service.config.get("ADM_NOTIFICATION_IDENTITY")
            try:
                endpoint = resolver(actor, row["endpointId"]) if callable(resolver) else None
                if not endpoint or endpoint["fingerprint"] != policy.get("endpointFingerprints", {}).get(row["endpointId"]):
                    raise ValueError("ENDPOINT_REAPPROVAL_REQUIRED")
                mention = binding(actor, row["recipientId"]) if callable(binding) else None
                if not mention or mention == "@all":
                    raise ValueError("MISSING_IDENTITY")
            except Exception:
                row.update(status="FAILED", errorCode="ENDPOINT_OR_IDENTITY_UNAVAILABLE")
                self._save_state(row)
                continue
            row.update(status="SENDING", claimedAt=now(), attempts=row["attempts"] + 1)
            if not self._save_state(row):
                continue
            # Recheck approval after CAS claim, immediately before crossing the external boundary.
            current = self.policy()
            current_actor = self.active_user(current.get("approvedBy"))
            current_recipient = self.active_user(row["recipientId"])
            if current["version"] != policy["version"] or not current["notificationsEnabled"] or not current_actor or not current_actor.get("is_admin") or not current_recipient or not self._valid(current_recipient, row, {item["id"]: item for item in self.tasks(current_actor)}):
                row.update(status="CANCELLED", errorCode="PRE_SEND_RECHECK_FAILED")
                self._save_state(row)
                continue
            try:
                endpoint = resolver(current_actor, row["endpointId"])
                if endpoint["fingerprint"] != current["endpointFingerprints"].get(row["endpointId"]):
                    row.update(status="CANCELLED", errorCode="ENDPOINT_CHANGED")
                else:
                    mention = binding(current_actor, row["recipientId"])
                    transport = self.service.config.get("ADM_NOTIFICATION_TRANSPORT") or send_wecom
                    code = transport(endpoint, mention)
                    row.update(status="SENT" if code == 0 else "FAILED", errorCode=None if code == 0 else "WECOM_REJECTED", receiptAt=now(), receiptCode=code)
            except Exception:
                row.update(status="UNKNOWN", errorCode="DELIVERY_OUTCOME_UNKNOWN")
            self._save_state(row)

    def _save_state(self, row):
        try:
            saved = self.store.save(row, row["version"])
            row.update(saved)
            return True
        except Conflict:
            return False
