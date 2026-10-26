"""Responsibility handover and live, permission-scoped worklists.

No guessed SLA, performance score, external delivery or historical reconstruction.
Mutations use the aggregate's existing CAS transaction and audit log.
"""

from collections import Counter
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .policy import AdmError, has, identity, now, require, uid
from .store import StoreUnavailable

ZONE = ZoneInfo("Asia/Shanghai")
DATE_FIELDS = ("acceptanceDueAt", "processingDueAt", "reviewDueAt", "financeDueAt")
ROLE_FIELDS = {"reviewerId": "review", "financeOwnerId": "finance"}
WORKFLOW_ACTIONS = {"plan", "follow_up", "transfer_request", "transfer_accept", "transfer_reject", "transfer_cancel"}


def timestamp(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise AdmError("期限必须为北京时间日期或日期时间")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if len(value) == 10:
            result = datetime.combine(result.date(), time(23, 59, 59))
        result = result.replace(tzinfo=ZONE) if result.tzinfo is None else result.astimezone(ZONE)
        return result.isoformat(timespec="seconds")
    except (ValueError, OverflowError):
        raise AdmError("期限格式无效") from None


def associated_ids(line):
    workflow = line.get("workflow") or {}
    ids = {
        str(value)
        for value in (line.get("ownerId"), workflow.get("reviewerId"), workflow.get("financeOwnerId"))
        if value
    }
    transfer = line.get("handover") or {}
    if transfer.get("status") == "PENDING":
        ids.add(str(transfer["toId"]))
    return ids


def role_actions(user, case, line, full):
    if case["status"] in {"DRAFT", "CLOSED", "HISTORICAL"} or case.get("paused") or case.get("voided"):
        return []
    actor = identity(user)
    manager = full and has(user, "adm.assign")
    owner = str(line.get("ownerId")) == actor and has(user, "adm.handle")
    active = line["status"] in {"PENDING_ACCEPT", "PROCESSING"}
    pending = (line.get("handover") or {}).get("status") == "PENDING"
    result = []
    if manager and line["status"] not in {"COMPLETED", "HISTORICAL"}:
        result.append("plan")
    if active and line.get("ownerId"):
        if pending:
            if str(line["handover"]["toId"]) == actor and has(user, "adm.handle"):
                result += ["transfer_accept", "transfer_reject"]
            if owner or manager:
                result.append("transfer_cancel")
        elif owner or manager:
            result.append("transfer_request")
    if owner and line["status"] == "PROCESSING" and line.get("lockedBy") == actor:
        result.append("follow_up")
    return result


def segment_assign(case, line, reason=""):
    stamp = now()
    for segment in line.setdefault("assignmentSegments", []):
        if not segment.get("endedAt"):
            segment["endedAt"] = stamp
    line["assignmentSegments"].append(
        {
            "id": uid(),
            "ownerId": line["ownerId"],
            "ownerName": line.get("ownerName", ""),
            "assignedAt": stamp,
            "acceptedAt": None,
            "endedAt": None,
            "round": case["round"],
            "reason": reason,
            "deadlines": {key: (line.get("workflow") or {}).get(key) for key in DATE_FIELDS},
        }
    )
    line["assignedAt"] = stamp


def segment_accept(case, line):
    segments = line.setdefault("assignmentSegments", [])
    if not segments or segments[-1].get("endedAt") or segments[-1].get("round") != case["round"]:
        segment_assign(case, line, "接单时建立办理段；未补造旧分配时间")
    segments[-1]["acceptedAt"] = line["acceptedAt"]
    line.setdefault("firstAcceptedAt", line["acceptedAt"])


class WorkflowService:
    def __init__(self, service):
        self.service = service

    def resolve(self, value, purpose):
        if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).isdigit():
            raise AdmError("请选择有效账号")
        resolver = self.service.config.get("ADM_USER_RESOLVER")
        user = resolver(str(value)) if callable(resolver) else None
        if user is None and self.service.config.get("TESTING") and not callable(resolver):
            user = {"id": str(value), "username": str(value), "is_admin": True}
        permission = {
            "handle": "adm.handle",
            "review": "adm.review",
            "finance": "adm.finance.confirm",
            "coordinate": "adm.assign",
        }[purpose]
        if (
            not user
            or not user.get("is_enabled", True)
            or not has(user, "adm.view")
            or not has(user, permission)
            or (not user.get("is_admin") and "adm.center" not in (user.get("menu_codes") or []))
        ):
            raise AdmError("账号不存在、停用或缺少对应ADM菜单/功能权限")
        return str(user["id"]), user.get("display_name") or user.get("username") or str(user["id"])

    def coordinate(self, user, case_id, body):
        case = self.service._write(user, case_id, body, "adm.assign", True)
        if not str(body.get("reason") or "").strip():
            raise AdmError("更换协调人须填写原因")
        actor, name = self.resolve(body.get("coordinatorId"), "coordinate")
        before = case.get("coordinatorId", case["createdBy"])
        case.update(coordinatorId=actor, coordinatorName=name)
        return self.service._save(
            user, case, "coordinator", {"before": before, "after": actor, "reason": body["reason"]}
        )

    def line_action(self, user, case_id, line_id, body):
        action = body.get("action")
        permission = "adm.assign" if action == "plan" else "adm.handle"
        if action in {"transfer_request", "transfer_cancel"} and has(user, "adm.assign"):
            permission = "adm.assign"
        case = self.service._write(user, case_id, body, permission)
        line = self.service._line(case, line_id)
        self.service._line_access(user, case, line)
        if action not in role_actions(user, case, line, self.service._full(user, case)):
            raise AdmError("当前状态或身份不能执行此工作流操作", 409, "ADM_ACTION_BLOCKED")
        if action == "plan":
            detail = self._plan(line, body)
        elif action == "follow_up":
            waiting = str(body.get("waitingFor") or "").strip()
            reason = str(body.get("waitingReason") or "").strip()
            due = timestamp(body.get("nextFollowUpAt"))
            note = str(body.get("reason") or "").strip()
            if len(waiting) > 200 or len(reason) > 4000 or len(note) > 4000:
                raise AdmError("跟进内容过长")
            if not note or (waiting and (not reason or not due)):
                raise AdmError("请填写有效跟进说明；等待须有原因及下次跟进时间")
            line.setdefault("workflow", {}).update(waitingFor=waiting, waitingReason=reason, nextFollowUpAt=due)
            line["lastFollowUpAt"] = now()
            detail = {"waitingFor": waiting, "waitingReason": reason, "nextFollowUpAt": due, "reason": note}
        elif action == "transfer_request":
            detail = self.request_transfer(user, case, line, body)
        else:
            transfer = line["handover"]
            reason = str(body.get("reason") or "").strip()
            if action != "transfer_accept" and not reason:
                raise AdmError("驳回/取消交接须填写原因")
            if len(reason) > 4000:
                raise AdmError("交接回复过长")
            transfer.update(
                status={"transfer_accept": "ACCEPTED", "transfer_reject": "REJECTED", "transfer_cancel": "CANCELLED"}[
                    action
                ],
                respondedAt=now(),
                responseReason=reason,
            )
            if action == "transfer_accept":
                # Current owner is unchanged until this CAS succeeds; no authority gap.
                self.resolve(identity(user), "handle")
                line.update(
                    ownerId=transfer["toId"],
                    ownerName=transfer["toName"],
                    status="PROCESSING",
                    lockedBy=identity(user),
                    acceptedAt=now(),
                )
                segment_assign(case, line, transfer["reason"])
                segment_accept(case, line)
            line.setdefault("handoverHistory", []).append(dict(transfer))
            detail = dict(transfer)
        return self.service._save(user, case, action, detail, line_id)

    def _plan(self, line, body):
        if not str(body.get("reason") or "").strip():
            raise AdmError("调整人员/期限须填写原因")
        if len(str(body["reason"])) > 4000:
            raise AdmError("调整原因过长")
        values = dict(line.get("workflow") or {})
        before = dict(values)
        for key, purpose in ROLE_FIELDS.items():
            if key in body:
                value = body[key]
                active_role = (
                    "reviewerId"
                    if line["status"] == "PENDING_REVIEW"
                    else "financeOwnerId"
                    if line["status"] == "WAITING_FINANCE"
                    else None
                )
                if key == active_role and values.get(key) and str(value or "") != str(values[key]):
                    raise AdmError("审核/财务进行中不得通过计划更换责任人，请先按授权退回处置", 409)
                name_key = "reviewerName" if key == "reviewerId" else "financeOwnerName"
                if value in (None, ""):
                    values.update({key: None, name_key: ""})
                else:
                    person_id, name = self.resolve(value, purpose)
                    if (
                        key == "reviewerId"
                        and person_id == str(line.get("ownerId"))
                        and not self.service.config.get("ADM_ALLOW_SELF_REVIEW", False)
                    ):
                        raise AdmError("审核人与当前承办人不能相同")
                    values.update({key: person_id, name_key: name})
        for key in DATE_FIELDS:
            if key in body:
                values[key] = timestamp(body[key])
        line["workflow"] = values
        return {"before": before, "after": dict(values), "reason": body["reason"]}

    def request_transfer(self, user, case, line, body):
        if (
            line["status"] not in {"PENDING_ACCEPT", "PROCESSING"}
            or (line.get("handover") or {}).get("status") == "PENDING"
        ):
            raise AdmError("此状态不可转交，或已有待确认交接", 409)
        actor, name = self.resolve(body.get("ownerId"), "handle")
        if actor == str(line.get("ownerId")):
            raise AdmError("不能转交给当前承办人")
        reason = str(body.get("reason") or "").strip()
        summary = str(body.get("summary") or reason).strip()
        if not reason or max(len(reason), len(summary)) > 4000:
            raise AdmError("转交原因必填且交接内容不得超过4000字")
        transfer = {
            "id": uid(),
            "status": "PENDING",
            "fromId": line["ownerId"],
            "fromName": line.get("ownerName", ""),
            "toId": actor,
            "toName": name,
            "requestedBy": identity(user),
            "requestedAt": now(),
            "reason": reason,
            "summary": summary,
        }
        line["handover"] = transfer
        return dict(transfer)

    def overview(self, user, filters):
        require(user, "adm.view")
        if filters.get("date") or filters.get("businessDate"):
            raise AdmError("当前观察不支持历史日期回溯，请勿作为历史日报使用")
        if filters.get("kind") and filters["kind"] not in {
            "ASSIGN",
            "ACCEPT",
            "PROCESS",
            "TRANSFER",
            "REVIEW",
            "FINANCE",
            "FOLLOW_UP",
        }:
            raise AdmError("任务环节无效")
        scope = filters.get("scope", "mine")
        if scope not in {"mine", "team", "all"}:
            raise AdmError("数据范围无效")
        if scope == "all":
            require(user, "adm.scope.all")
        ids = self.service._ids(user, scope)
        try:
            page = max(1, int(filters.get("page", 1)))
            size = min(100, max(1, int(filters.get("pageSize", 20))))
        except (ValueError, TypeError):
            raise AdmError("分页参数无效") from None
        stamp = now()
        items = []

        def add(case, line, kind, label, owner, name, due, needs_assignee=False, summary_only=False):
            if scope != "all" and str(owner or "") not in ids:
                return
            if filters.get("kind") and filters["kind"] != kind:
                return
            normalized = timestamp(due)
            overdue = bool(normalized and datetime.fromisoformat(normalized) < datetime.fromisoformat(stamp))
            line_id = line["id"] if line else None
            items.append(
                {
                    "id": f"{case['id']}:{line_id or 'main'}:{kind}",
                    "caseId": case["id"],
                    "lineId": line_id,
                    "admNo": case["admNo"],
                    "kind": kind,
                    "label": label,
                    "ownerId": str(owner) if owner else None,
                    "ownerName": name or "待指定",
                    "status": line["status"] if line else case["status"],
                    "dueAt": normalized or None,
                    "overdue": overdue,
                    "paused": bool(case.get("paused")),
                    "version": case["version"],
                    "needsAssignee": needs_assignee,
                    "coordinationOnly": summary_only,
                    "url": None
                    if summary_only
                    else f"/adm/cases/{case['id']}" + (f"/lines/{line_id}" if line_id else ""),
                }
            )
            if summary_only:
                items[-1]["lineId"] = None

        maximum = int(self.service.config.get("ADM_WORKFLOW_MAX_CASES", 5000))
        try:
            cases = self.service.store.workflow_cases(maximum)
        except StoreUnavailable as error:
            raise AdmError(str(error), 503, error.code) from error
        if len(cases) > maximum:
            raise AdmError(
                "活跃主单超过当前观察容量，请先完成任务索引升级；未返回截断汇总", 422, "ADM_WORKFLOW_CAPACITY"
            )
        for case in cases:
            if case["status"] in {"DRAFT", "CLOSED", "HISTORICAL"} or case.get("voided"):
                continue
            coordinator = str(case.get("coordinatorId", case["createdBy"]))
            full = self.service._full(user, case)
            coordination_visible = scope == "all" or coordinator in ids
            for line in case["lines"]:
                visible = full or bool(associated_ids(line) & ids)
                if not visible and not coordination_visible:
                    continue
                workflow = line.get("workflow") or {}
                owner, name = line.get("ownerId"), line.get("ownerName")
                if line["status"] == "PENDING_ASSIGN":
                    if full or coordination_visible:
                        add(
                            case,
                            line,
                            "ASSIGN",
                            "待分配承办人",
                            coordinator,
                            case.get("coordinatorName"),
                            None,
                            True,
                            not visible,
                        )
                elif line["status"] == "PENDING_ACCEPT" and visible:
                    add(case, line, "ACCEPT", "待接单", owner, name, workflow.get("acceptanceDueAt"))
                elif line["status"] == "PROCESSING" and visible:
                    add(
                        case,
                        line,
                        "PROCESS",
                        "待办理",
                        owner,
                        name,
                        workflow.get("processingDueAt") or case.get("deadline"),
                    )
                elif line["status"] in {"PENDING_REVIEW", "WAITING_FINANCE"}:
                    review = line["status"] == "PENDING_REVIEW"
                    person = workflow.get("reviewerId" if review else "financeOwnerId")
                    if (person and visible) or (not person and (full or coordination_visible)):
                        add(
                            case,
                            line,
                            "REVIEW" if review else "FINANCE",
                            "待审核" if review else "待财务确认",
                            person or coordinator,
                            workflow.get("reviewerName" if review else "financeOwnerName")
                            if person
                            else "协调人：请指定节点责任人",
                            workflow.get("reviewDueAt" if review else "financeDueAt"),
                            not person,
                            not visible,
                        )
                transfer = line.get("handover") or {}
                if transfer.get("status") == "PENDING" and visible:
                    add(
                        case,
                        line,
                        "TRANSFER",
                        "待确认交接",
                        transfer["toId"],
                        transfer["toName"],
                        workflow.get("acceptanceDueAt"),
                    )
                if line["status"] == "PROCESSING" and workflow.get("waitingFor") and visible:
                    add(case, line, "FOLLOW_UP", "等待外部：需跟进", owner, name, workflow.get("nextFollowUpAt"))
        items.sort(key=lambda item: (not item["overdue"], item["dueAt"] or "9999", item["id"]))
        counts = Counter(item["kind"] for item in items)
        people = {}
        for item in items:
            key = item["ownerId"] or "UNASSIGNED"
            person = people.setdefault(
                key,
                {
                    "ownerId": item["ownerId"],
                    "ownerName": item["ownerName"],
                    "tasks": 0,
                    "overdue": 0,
                    "missingDeadline": 0,
                },
            )
            person["tasks"] += 1
            person["overdue"] += int(item["overdue"])
            person["missingDeadline"] += int(not item["dueAt"])
        return {
            "generatedAt": stamp,
            "businessDate": stamp[:10],
            "scope": scope,
            "summary": {
                "tasks": len(items),
                "overdue": sum(item["overdue"] for item in items),
                "unassigned": sum(item["needsAssignee"] for item in items),
                "missingDeadline": sum(not item["dueAt"] for item in items),
                "waiting": counts["FOLLOW_UP"],
            },
            "people": sorted(people.values(), key=lambda item: (item["ownerName"], item["ownerId"] or "")),
            "items": items[(page - 1) * size : page * size],
            "pagination": {"page": page, "pageSize": size, "total": len(items)},
            "limitations": [
                "当前授权范围的实时任务观察，非历史日报或绩效排名",
                "任务数不等于订单数；等待和交接任务单列，不重复计算金额",
                "期限缺失不表示达标；未批准SLA、权重、日历或公开范围",
                "站内待办可查询，尚未接入站外自动推送；旧表数据不混算",
            ],
        }
