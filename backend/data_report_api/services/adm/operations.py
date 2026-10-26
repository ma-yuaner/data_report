"""Durable ADM operations. Explicit approval, bounded reads, no automatic DDL in production."""
import copy
import hashlib
import json
import re

from .policy import AdmError, identity, now, require
from .store import Conflict, StoreUnavailable
from .workflow import WorkflowService

DEFAULTS = dict(notificationsEnabled=False, endpointIds=[], leadMinutes=None, repeatMinutes=None,
                escalationMinutes=None, snapshotsEnabled=False, snapshotAt="", rankingEnabled=False,
                minimumSamples=None, approvalNote="")


class OperationStore:
    def __init__(self, store):
        self.store = store

    def _table(self, conn):
        if self.store.mode == "sqlite":
            self.store.query(conn, "CREATE TABLE IF NOT EXISTS adm_operation_document (id TEXT PRIMARY KEY, kind TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")

    def get(self, record_id):
        with self.store.connection() as conn:
            self._table(conn)
            row = self.store.query(conn, "SELECT payload FROM adm_operation_document WHERE id=?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind, maximum=100, recipient=None, date=None, channel=None, statuses=None):
        where, params = "kind=?", [kind]
        if recipient is not None:
            where += " AND json_extract(payload,'$.recipientId')=?"
            params.append(str(recipient))
        if date is not None:
            where += " AND json_extract(payload,'$.businessDate')=?"
            params.append(date)
        if channel:
            where += " AND json_extract(payload,'$.channel')=?"
            params.append(channel)
        if statuses:
            where += " AND json_extract(payload,'$.status') IN (" + ",".join("?" for _ in statuses) + ")"
            params.extend(statuses)
        if self.store.mode == "mysql":
            where = where.replace("json_extract(payload,'$.recipientId')", "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.recipientId'))").replace("json_extract(payload,'$.businessDate')", "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.businessDate'))")
            for field in ("channel", "status"):
                where = where.replace(f"json_extract(payload,'$.{field}')", f"JSON_UNQUOTE(JSON_EXTRACT(payload,'$.{field}'))")
        with self.store.connection() as conn:
            self._table(conn)
            rows = self.store.query(conn, f"SELECT payload FROM adm_operation_document WHERE {where} ORDER BY updated_at DESC,id DESC LIMIT ?", (*params, maximum)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save(self, record, expected=0):
        record = copy.deepcopy(record)
        record["version"] = expected + 1
        with self.store.connection() as conn:
            self._table(conn)
            payload = json.dumps(record, ensure_ascii=False)
            if expected:
                cursor = self.store.query(conn, "UPDATE adm_operation_document SET version=?,payload=?,updated_at=? WHERE id=? AND version=?", (record["version"], payload, now(), record["id"], expected))
                if cursor.rowcount != 1:
                    raise Conflict("运营记录版本冲突")
            else:
                try:
                    self.store.query(conn, "INSERT INTO adm_operation_document(id,kind,version,payload,updated_at) VALUES(?,?,?,?,?)", (record["id"], record["kind"], 1, payload, now()))
                except Exception as error:
                    if getattr(error, "args", [None])[0] == 1062 or error.__class__.__name__ == "IntegrityError":
                        raise Conflict("运营记录已存在") from error
                    raise
            if record["kind"] == "POLICY":
                audit = dict(record, id=f"policy-revision-{record['version']}", kind="POLICY_REVISION")
                self.store.query(conn, "INSERT INTO adm_operation_document(id,kind,version,payload,updated_at) VALUES(?,?,?,?,?)", (audit["id"], audit["kind"], audit["version"], json.dumps(audit, ensure_ascii=False), now()))
        return record


class OperationsService:
    def __init__(self, service):
        self.service = service
        self.store = OperationStore(service.store)

    @staticmethod
    def admin(user):
        require(user, "adm.view")
        if not user.get("is_admin"):
            raise AdmError("运营策略与发布仅限系统管理员", 403)

    def policy(self):
        return self.store.get("adm-policy") or dict(copy.deepcopy(DEFAULTS), id="adm-policy", kind="POLICY", version=0)

    def config(self, user):
        self.admin(user)
        policy = self.policy()
        provider = self.service.config.get("ADM_ENDPOINT_OPTIONS")
        available = callable(self.service.config.get("ADM_ENDPOINT_RESOLVER"))
        try:
            options = provider(user) if callable(provider) else []
        except AdmError:
            options, available = [], False
        return {**{key: policy[key] for key in DEFAULTS}, "version": policy["version"], "endpointOptions": options,
                "endpointAvailable": available,
                "externalDeliveryEnabled": bool(self.service.config.get("ADM_EXTERNAL_DELIVERY_ENABLED", False))}

    def configure(self, user, body):
        self.admin(user)
        if set(body) - (set(DEFAULTS) | {"version"}):
            raise AdmError("包含不可编辑策略字段")
        old = self.policy()
        if type(body.get("version")) is not int or old["version"] != body["version"]:
            raise AdmError("运营策略版本冲突，请刷新", 409, "ADM_VERSION_CONFLICT")
        values = {key: copy.deepcopy(body.get(key, old[key])) for key in DEFAULTS}
        for key in ("notificationsEnabled", "snapshotsEnabled", "rankingEnabled"):
            if type(values[key]) is not bool:
                raise AdmError("策略启用项必须是布尔值")
        for key in ("leadMinutes", "repeatMinutes", "escalationMinutes", "minimumSamples"):
            if values[key] is not None and (type(values[key]) is not int or not 1 <= values[key] <= 525600):
                raise AdmError("频率、提前量、升级时长与最小样本须为有效正整数")
        if not isinstance(values["approvalNote"], str) or not values["approvalNote"].strip() or len(values["approvalNote"]) > 4000:
            raise AdmError("必须记录业务批准依据，最多4000字")
        if not isinstance(values["snapshotAt"], str) or (values["snapshotAt"] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", values["snapshotAt"])):
            raise AdmError("快照时间须为北京时间HH:mm")
        if values["snapshotsEnabled"] and not values["snapshotAt"]:
            raise AdmError("启用每日快照必须明确执行时间")
        if values["rankingEnabled"] and not values["minimumSamples"]:
            raise AdmError("试运行排名必须明确最小样本")
        endpoints = values["endpointIds"]
        if not isinstance(endpoints, list) or len(endpoints) > 20 or any(not isinstance(item, str) for item in endpoints) or len(set(endpoints)) != len(endpoints):
            raise AdmError("通知端点无效")
        resolver = self.service.config.get("ADM_ENDPOINT_RESOLVER")
        if endpoints and not callable(resolver):
            raise AdmError("通知端点尚未接入", 503)
        fingerprints = {item: resolver(user, item)["fingerprint"] for item in endpoints}
        record = dict(values, id="adm-policy", kind="POLICY", approvedBy=identity(user), approvedAt=now(), endpointFingerprints=fingerprints,
                      previousApproval={"version": old["version"], "approvedBy": old.get("approvedBy"), "approvedAt": old.get("approvedAt"), "approvalNote": old.get("approvalNote")})
        self.store.save(record, old["version"])
        return self.config(user)

    def tasks(self, user, cases=None):
        result = WorkflowService(self.service).overview(user, {"scope": "all"}, unpaginated=True, source_cases=cases)["items"]
        return [item for item in result if not item["paused"]]

    def preview(self, user):
        self.admin(user)
        config = self.config(user)
        tasks = self.tasks(user)
        return dict(enabled=config["notificationsEnabled"], externalDeliveryEnabled=config["externalDeliveryEnabled"], tasks=len(tasks),
                    wouldCreate=len(tasks) if config["notificationsEnabled"] else 0,
                    missingConfig=["站外投递部署开关关闭"] if config["endpointIds"] and not config["externalDeliveryEnabled"] else [],
                    warnings=["仅预览，不创建通知、不发送；任务期限缺失不表示达标", "员工绑定和当前对象权限在worker投递前再次核验"])

    def current_notice(self, user, record):
        if record.get("recipientId") != identity(user):
            return False
        try:
            case = self.service._read(user, record["caseId"])
            line = self.service._line(case, record["lineId"])
            self.service._line_access(user, case, line)
            if case.get("paused") or case.get("voided") or case["round"] != record["round"]:
                return False
            # Resolve current ownership, stage and deadline; version changes alone don't invalidate a task.
            if record.get("escalation"):
                if not self.service._full(user, case) or str(case.get("coordinatorId", case["createdBy"])) != identity(user):
                    return False
                resolver = self.service.config.get("ADM_USER_RESOLVER")
                policy = self.policy()
                actor = resolver(policy.get("approvedBy")) if callable(resolver) and policy.get("approvedBy") else None
                if not actor or not actor.get("is_enabled", True) or not actor.get("is_admin"):
                    return False
                items = self.tasks(actor)
            else:
                items = WorkflowService(self.service).overview(user, {"scope": "mine"}, unpaginated=True)["items"]
            from .notifications import NotificationWorker
            return NotificationWorker(self.service)._valid(user, record, {item["id"]: item for item in items})
        except AdmError:
            return False
        return False

    def inbox(self, user):
        require(user, "adm.view")
        rows = [item for item in self.store.list("NOTICE", 100, identity(user), channel="IN_APP") if self.current_notice(user, item)]
        items = [{key: item.get(key) for key in ("id", "version", "title", "body", "createdAt", "readAt", "caseId", "lineId", "url", "status")} for item in rows]
        return dict(items=items, unread=sum(not item.get("readAt") for item in items), limit=100, limitations=["最多最近100条，未读数仅此范围；已失效任务隐藏"])

    def read(self, user, record_id, body):
        require(user, "adm.view")
        record = self.store.get(record_id)
        if not record or record.get("kind") != "NOTICE" or record.get("channel") != "IN_APP" or not self.current_notice(user, record):
            raise AdmError("通知不存在或当前无权访问", 404)
        if type(body.get("version")) is not int or record["version"] != body["version"]:
            raise AdmError("通知版本冲突", 409, "ADM_VERSION_CONFLICT")
        record["readAt"] = now()
        saved = self.store.save(record, record["version"])
        return {key: saved.get(key) for key in ("id", "version", "readAt", "status")}

    def deliveries(self, user):
        self.admin(user)
        keys = ("id", "version", "channel", "recipientId", "status", "attempts", "createdAt", "nextAttemptAt", "errorCode")
        return {"items": [{key: item.get(key) for key in keys} for item in self.store.list("NOTICE", 100)], "limit": 100}


def unavailable(error):
    if isinstance(error, Conflict):
        return AdmError("运营记录版本冲突，请刷新", 409, "ADM_VERSION_CONFLICT")
    if isinstance(error, StoreUnavailable):
        return AdmError("ADM运营存储不可用，请核对adm_operation_document专用DDL与连接", 503, error.code)
    return error


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
