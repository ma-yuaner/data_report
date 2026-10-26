"""ADM application rules, authorization and atomic audit history."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .store import AdmStore, Conflict, StoreUnavailable
from .policy import AdmError, has, identity, now, require, uid
from .workflow import WORKFLOW_ACTIONS, WorkflowService, associated_ids, role_actions, segment_assign, segment_accept

CASE_STATUSES = ["DRAFT", "PENDING_ASSIGN", "PROCESSING", "PENDING_REVIEW", "WAITING_FINANCE", "CLOSED", "HISTORICAL"]
LINE_STATUSES = ["PENDING_ASSIGN", "PENDING_ACCEPT", "PROCESSING", "PENDING_REVIEW", "WAITING_FINANCE", "COMPLETED", "HISTORICAL"]
CATEGORIES = ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "FINANCE", "ANALYSIS"]
ANALYSIS_FIELDS = ("facts", "dispute", "cause", "proposal", "conclusion", "prevention")
CASE_FIELDS = (
    "supplierCode", "airline", "ticketCount", "originalAmountCny", "businessCategory",
    "admNo",
    "supplierName",
    "supplierType",
    "currency",
    "originalAmount",
    "issuedDate",
    "deadline",
    "description",
    "remark",
    "analysis",
)
LINE_FIELDS = (
    "platformCode", "airline", "ticketCount", "amountCny", "businessCategory",
    "actualOwner", "actualHandler", "recoveryDeadline", "resolution",
    "businessType",
    "platform",
    "shop",
    "site",
    "orderNo",
    "ticketNo",
    "pnr",
    "system",
    "pcc",
    "currency",
    "amount",
    "description",
    "differenceDescription",
    "diffType",
    "diffSecondType",
    "remark",
    "matchStatus",
    "matchEvidence",
    "unlinkedReason",
    "analysis",
    "attribution",
    "appealDecision",
    "appealReason",
    "recoveryRequired",
    "finance",
)


def deadline_expired(value):
    if not value:
        return False
    zone = ZoneInfo("Asia/Shanghai")
    deadline = (
        datetime.combine(date.fromisoformat(value), time(23, 59, 59), zone)
        if len(value) == 10
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=zone)
    return deadline < datetime.now(zone)


def money(value, nullable=True):
    if value is None or value == "":
        if nullable:
            return None
        raise AdmError("金额不能为空")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise AdmError("金额格式无效") from None
    if (
        not result.is_finite()
        or result < 0
        or result > Decimal("999999999999999.9999")
        or result.as_tuple().exponent < -4
    ):
        raise AdmError("金额须为非负十进制，最多四位小数")
    return format(result, "f")


class AdmService:
    def __init__(self, config):
        self.config = config
        try:
            self.store = AdmStore(config)
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc

    def _get(self, case_id):
        try:
            case = self.store.get(str(case_id))
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        if not case:
            raise AdmError("ADM不存在", 404, "ADM_NOT_FOUND")
        return case

    def _all(self):
        try:
            return self.store.all()
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc

    def _full(self, user, case):
        coordinator = case.get("coordinatorId", case["createdBy"])
        return has(user, "adm.scope.all") or str(coordinator) == identity(user)

    def _ids(self, user, scope="mine"):
        ids = {identity(user)}
        if scope == "team":
            require(user, "adm.scope.team")
            ids.update(str(item) for item in user.get("managed_user_ids") or [])
        return ids

    def _visible_lines(self, user, case, scope="team"):
        if self._full(user, case):
            return case["lines"]
        ids = self._ids(user, "team" if scope == "team" and has(user, "adm.scope.team") else "mine")
        return [line for line in case["lines"] if associated_ids(line) & ids]

    def _read(self, user, case_id):
        require(user, "adm.view")
        case = self._get(case_id)
        if not self._full(user, case) and not self._visible_lines(user, case):
            raise AdmError("无此ADM数据访问权限", 403, "ADM_FORBIDDEN")
        return case

    def _write(self, user, case_id, body, permission, full=False, control_action=None):
        require(user, permission)
        case = self._read(user, case_id)
        if full and not self._full(user, case):
            raise AdmError("此操作需完整主单范围", 403, "ADM_FORBIDDEN")
        if type(body.get("version")) is not int or body["version"] != case["version"]:
            raise AdmError("版本冲突，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
        if case.get("historicalArchive") and not (control_action == "archive_attachment" and user.get("is_admin")):
            raise AdmError("历史档案只读；请引用新建继续处理，保留原始状态", 409, "ADM_HISTORY_READ_ONLY")
        if case["status"] == "CLOSED" and control_action != "reopen":
            raise AdmError("已结案只读，请授权重开", 409, "ADM_CLOSED")
        if (case.get("paused") or case.get("voided")) and control_action not in {"resume", "reopen"}:
            raise AdmError("主单已挂起或作废", 409, "ADM_INACTIVE")
        return case

    def _line(self, case, line_id):
        line = next((item for item in case["lines"] if item["id"] == str(line_id)), None)
        if not line:
            raise AdmError("明细不存在", 404, "ADM_NOT_FOUND")
        return line

    def _line_access(self, user, case, line):
        if not self._full(user, case) and line not in self._visible_lines(user, case):
            raise AdmError("无明细访问权限", 403, "ADM_FORBIDDEN")

    def _event(self, user, case, action, detail=None, line_id=None):
        detail = copy.deepcopy(detail or {})
        if line_id:
            line = self._line(case, line_id)
            detail["responsibility"] = {"ownerId": line.get("ownerId"), "ownerName": line.get("ownerName"), "round": case["round"]}
        case["timeline"].append(
            {
                "id": uid(),
                "action": action,
                "lineId": line_id,
                "actorId": identity(user),
                "actorName": user.get("display_name") or user.get("username") or identity(user),
                "at": now(),
                "detail": detail,
            }
        )

    def _derive(self, case):
        if case["status"] in {"CLOSED", "DRAFT", "HISTORICAL"}:
            return
        states = {line["status"] for line in case["lines"]}
        if not states or states == {"PENDING_ASSIGN"}:
            case["status"] = "PENDING_ASSIGN"
        elif states <= {"COMPLETED", "WAITING_FINANCE"} and "WAITING_FINANCE" in states:
            case["status"] = "WAITING_FINANCE"
        elif states <= {"COMPLETED", "PENDING_REVIEW"}:
            case["status"] = "PENDING_REVIEW"
        else:
            case["status"] = "PROCESSING"

    def _save(self, user, case, action, detail=None, line_id=None):
        expected = case["version"]
        self._derive(case)
        case["version"] += 1
        case["updatedAt"] = now()
        self._event(user, case, action, detail, line_id)
        try:
            self.store.save(case, expected)
        except Conflict as exc:
            raise AdmError(str(exc), 409, "ADM_VERSION_CONFLICT") from exc
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        return self._present(user, case)

    def _clean(self, body, fields):
        result = {}
        for field in fields:
            if field not in body:
                continue
            value = body[field]
            if field in {"amount", "originalAmount", "originalAmountCny", "amountCny"}:
                value = money(value)
            elif field == "ticketCount":
                if value in (None, ""):
                    value = None
                elif not str(value).isdigit() or int(value) > 2147483647:
                    raise AdmError("票号数量须为非负整数，最多2147483647")
                else:
                    value = int(value)
            elif field == "analysis":
                if not isinstance(value, dict) or any(key not in ANALYSIS_FIELDS for key in value):
                    raise AdmError("分析字段无效")
                if any(not isinstance(text, str) or len(text) > 10000 for text in value.values()):
                    raise AdmError("分析内容须为文本，单项最多10000字")
                value = dict(value)
            elif field == "finance":
                if not isinstance(value, dict) or type(value.get("required")) is not bool:
                    raise AdmError("财务需求须明确required布尔值")
                value = {
                    "required": value["required"],
                    "reason": str(value.get("reason", ""))[:5000],
                    "status": "PENDING" if value["required"] else "NOT_REQUIRED",
                    "reference": None,
                    "amount": None,
                    "currency": None,
                }
            elif field == "recoveryRequired":
                if type(value) is not bool:
                    raise AdmError("recoveryRequired须为布尔值")
            else:
                if value is not None and not isinstance(value, str):
                    raise AdmError(f"{field}须为文本")
                value = value or ""
                if len(value) > (10000 if field in {"description", "differenceDescription"} else 5000):
                    raise AdmError(f"{field}内容过长")
            if field == "issuedDate" and value:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    raise AdmError("下发日期须为YYYY-MM-DD") from None
            if field in {"deadline", "recoveryDeadline"} and value:
                try:
                    if len(value) == 10:
                        date.fromisoformat(value)
                    else:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        value = (
                            (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai")))
                            .astimezone(ZoneInfo("Asia/Shanghai"))
                            .isoformat(timespec="seconds")
                        )
                except ValueError:
                    raise AdmError("截止时间须为日期或ISO日期时间（北京时间）") from None
            if field == "currency" and value and (len(value) != 3 or not value.isalpha() or not value.isupper()):
                raise AdmError("币种须为三位大写代码")
            if field == "businessType" and value not in {"ISSUE", "REFUND", "CHANGE", "UNKNOWN"}:
                raise AdmError("业务类型无效")
            if field == "businessCategory" and value not in {"", "0", "1", "2"}:
                raise AdmError("业务大类须为票务、业务、客服或留空")
            if field in {"admNo", "supplierCode"} and len(value) > (100 if field == "admNo" else 200):
                raise AdmError("ADM号最多100字，下发方编码最多200字")
            if field == "matchStatus" and value not in {"UNVERIFIED", "OURS", "NOT_OURS"}:
                raise AdmError("订单归属无效")
            if field == "appealDecision" and value not in {"UNDECIDED", "REQUIRED", "NOT_REQUIRED"}:
                raise AdmError("申诉决策无效")
            result[field] = value
        return result

    def config_info(self, user):
        require(user, "adm.view")
        try:
            self.store.check()
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        people_provider = self.config.get("ADM_WORKFLOW_USER_OPTIONS")
        people = people_provider() if callable(people_provider) and any(has(user, p) for p in ("adm.assign", "adm.handle")) else {}
        assignees = people.get("handle", [])
        if not people and has(user, "adm.assign") and callable(self.config.get("ADM_USER_OPTIONS")):
            assignees = self.config["ADM_USER_OPTIONS"]()
        return {
            "storageMode": self.store.mode,
            "available": True,
            "capabilities": {"orders": False, "finance": False, "notifications": False, "inAppWorklist": True},
            "caseStatuses": CASE_STATUSES,
            "lineStatuses": LINE_STATUSES,
            "businessTypes": ["ISSUE", "REFUND", "CHANGE", "UNKNOWN"],
            "attachmentCategories": CATEGORIES,
            "assignees": assignees if has(user, "adm.assign") else [],
            "people": people,
        }

    def _public_attachment(self, item):
        return {key: value for key, value in item.items() if key != "storageKey"}

    def _present(self, user, source, detail=True):
        case = copy.deepcopy(source)
        case["legacyCoordination"] = "coordinatorId" not in source
        case["coordinatorId"] = source.get("coordinatorId", source["createdBy"])
        full = self._full(user, source)
        visible = self._visible_lines(user, source)
        ids = {line["id"] for line in visible}
        case["partial"] = not full
        case["lines"] = copy.deepcopy(visible)
        case["attachments"] = [
            self._public_attachment(item) for item in case["attachments"] if full or item.get("lineId") in ids
        ]
        case["timeline"] = [item for item in case["timeline"] if full or item.get("lineId") in ids]
        case["lineCount"] = len(case["lines"])
        case["completedCount"] = sum(line["status"] == "COMPLETED" for line in case["lines"])
        case["attachmentCount"] = len(case["attachments"])
        case["allowedActions"] = []
        if case.get("historicalArchive"):
            case["allowedActions"] = ["copy"] if full and has(user, "adm.create") else []
            if full and user.get("is_admin") and has(user, "adm.edit"):
                case["allowedActions"].append("upload")
        elif full and source["status"] != "CLOSED":
            actions = {"copy": "adm.create"}
            if not source.get("voided"):
                if source.get("paused"):
                    actions["resume"] = "adm.edit"
                else:
                    actions.update(
                        {
                            "edit": "adm.edit",
                            "pause": "adm.edit",
                            "void": "adm.edit",
                            "addLine": "adm.edit",
                            "upload": "adm.edit",
                            "coordinator": "adm.assign",
                        }
                    )
                    if source["status"] == "DRAFT":
                        actions["publish"] = "adm.edit"
                    elif detail and self._closure(source)["canClose"]:
                        actions["close"] = "adm.close"
            case["allowedActions"] = [action for action, permission in actions.items() if has(user, permission)]
        elif full and has(user, "adm.reopen"):
            case["allowedActions"] = ["reopen", "copy"] if has(user, "adm.create") else ["reopen"]
        for line in case["lines"]:
            if not full:
                line.pop("source", None)
            line["attachments"] = [item for item in case["attachments"] if item.get("lineId") == line["id"]]
            line["allowedActions"] = self._line_actions(user, source, line)
            line["uploadCategories"] = (
                ["FINANCE"] if line["status"] == "WAITING_FINANCE" else
                ["VERIFICATION", "ANALYSIS"] if line["status"] == "PENDING_REVIEW" else CATEGORIES
            ) if "upload" in line["allowedActions"] else []
        case["closureCheck"] = (
            (
                self._closure(source)
                if full
                else {"canClose": False, "checks": [], "blockers": ["仅可查看授权明细，无法核对整单"], "amounts": None}
            )
            if detail
            else None
        )
        case.pop("idempotencyKey", None)
        case.pop("requestHash", None)
        if not full:
            case.update(originalAmount=None, originalAmountCny=None, ticketCount=None, remark="", description="", analysis={}, snapshots=[], analysisVersions=[])
            case.pop("source", None)
            case.pop("history", None)

        def redact_internal(value):
            if isinstance(value, dict):
                return {
                    key: redact_internal(item)
                    for key, item in value.items()
                    if key not in {"storageKey", "requestHash"}
                }
            if isinstance(value, list):
                return [redact_internal(item) for item in value]
            return value

        case = redact_internal(case)
        if not detail:
            for field in ("lines", "attachments", "timeline", "snapshots", "analysisVersions", "closureCheck", "source", "history"):
                case.pop(field, None)
        return case

    def _line_actions(self, user, case, line):
        if case["status"] in {"CLOSED", "HISTORICAL"} or case.get("paused") or case.get("voided"):
            return []
        result = []
        if line["status"] == "PENDING_ASSIGN" and self._full(user, case) and has(user, "adm.edit"):
            result.append("edit")
        if case["status"] == "DRAFT":
            return result
        if has(user, "adm.assign") and self._full(user, case) and line["status"] in {"PENDING_ASSIGN", "PENDING_ACCEPT", "PROCESSING"}:
            result.append("assign")
        mine = str(line.get("ownerId")) == identity(user)
        if mine and has(user, "adm.handle"):
            if line["status"] == "PENDING_ACCEPT":
                result.append("claim")
            if line["status"] == "PROCESSING":
                if line.get("lockedBy") == identity(user):
                    result += ["edit", "upload", "recovery", "appeal", "difference", "submit", "unlock"]
                elif line.get("lockedBy") is None:
                    result.append("lock")
        if line["status"] == "PENDING_REVIEW" and has(user, "adm.review"):
            reviewer = (line.get("workflow") or {}).get("reviewerId")
            if (not reviewer or str(reviewer) == identity(user) or user.get("is_admin")) and (not mine or self.config.get("ADM_ALLOW_SELF_REVIEW", False)):
                result += ["approve", "return", "upload"]
        if line["status"] == "WAITING_FINANCE" and has(user, "adm.finance.confirm"):
            finance_owner = (line.get("workflow") or {}).get("financeOwnerId")
            if not finance_owner or str(finance_owner) == identity(user) or user.get("is_admin"):
                result += ["finance_confirm", "upload"]
        if has(user, "adm.unlock.force"):
            result.append("unlock")
        return result + role_actions(user, case, line, self._full(user, case))

    def list_cases(self, user, filters):
        require(user, "adm.view")
        scope = filters.get("scope", "mine")
        if scope not in {"mine", "team", "all"}:
            raise AdmError("范围无效")
        if scope == "all":
            require(user, "adm.scope.all")
        ids = self._ids(user, scope)
        try:
            page, size = max(1, int(filters.get("page", 1))), min(100, max(1, int(filters.get("pageSize", 20))))
        except (ValueError, TypeError):
            raise AdmError("分页参数无效") from None
        if scope == "all":
            try:
                cases, summary = self.store.page_all(filters, page, size, now())
            except StoreUnavailable as exc:
                raise AdmError(str(exc), 503, exc.code) from exc
            return {"items": [self._present(user, case, detail=False) for case in cases],
                    "pagination": {"page": page, "pageSize": size, "total": summary["cases"]}, "summary": summary}
        items = []
        keyword = str(filters.get("search", "")).strip().lower()
        for case in self._all():
            if str(filters.get("activeOnly", "")).lower() == "true" and case["status"] in {"CLOSED", "HISTORICAL"}:
                continue
            if (
                scope != "all"
                and str(case.get("coordinatorId", case["createdBy"])) not in ids
                and not any(associated_ids(line) & ids for line in case["lines"])
            ):
                continue
            if filters.get("status") and case["status"] != filters["status"]:
                continue
            if any(filters.get(key) not in (None, "") and str(case.get(key, "")) != str(filters[key]) for key in ("businessCategory", "supplierCode")):
                continue
            public = self._present(user, case, detail=False)
            searchable = {
                "case": public,
                "lines": [
                    {
                        key: line.get(key)
                        for key in (
                            "orderNo",
                            "ticketNo",
                            "pnr",
                            "platform",
                            "shop",
                            "site",
                            "description",
                            "differenceDescription",
                            "remark",
                        )
                    }
                    for line in self._visible_lines(user, case)
                ],
            }
            if keyword and keyword not in json.dumps(searchable, ensure_ascii=False).lower():
                continue
            items.append(public)
        items.sort(key=lambda item: item["updatedAt"], reverse=True)
        summary = {
            "cases": len(items),
            "lines": sum(item["lineCount"] for item in items),
            "open": sum(item["status"] not in {"CLOSED", "HISTORICAL"} and not item.get("voided") for item in items),
            "overdue": sum(
                bool(deadline_expired(item.get("deadline")) and item["status"] not in {"CLOSED", "HISTORICAL"} and not item.get("voided"))
                for item in items
            ),
        }
        summaries = []
        for item in items[(page - 1) * size : page * size]:
            for field in ("lines", "attachments", "timeline", "snapshots", "analysisVersions", "closureCheck"):
                item.pop(field, None)
            summaries.append(item)
        return {
            "items": summaries,
            "pagination": {"page": page, "pageSize": size, "total": len(items)},
            "summary": summary,
        }

    def create_case(self, user, body, history=None):
        require(user, "adm.create")
        require(user, "adm.view")
        fields = self._clean(body, CASE_FIELDS)
        if not fields.get("admNo") or not fields.get("supplierName"):
            raise AdmError("ADM号和下发方必填")
        case = {
            "id": uid(),
            "version": 1,
            "status": "DRAFT",
            "paused": False,
            "voided": False,
            "createdBy": identity(user),
            "coordinatorId": identity(user),
            "coordinatorName": user.get("display_name") or user.get("username") or identity(user),
            "createdAt": now(),
            "updatedAt": now(),
            "lines": [],
            "attachments": [],
            "timeline": [],
            "analysis": {},
            "analysisVersions": [],
            "snapshots": [],
            "round": 1,
            **{key: "" for key in CASE_FIELDS if key != "analysis"},
            **fields,
        }
        case["originalAmount"] = fields.get("originalAmount")
        case["originalAmountCny"] = fields.get("originalAmountCny")
        case["ticketCount"] = fields.get("ticketCount")
        if "source" in body:
            if not isinstance(body["source"], dict) or len(json.dumps(body["source"], ensure_ascii=False)) > 100000:
                raise AdmError("来源快照格式或大小无效")
            case["source"] = copy.deepcopy(body["source"])
        initial_lines = body.get("lines", [])
        if (
            not isinstance(initial_lines, list)
            or len(initial_lines) > 1000
            or any(not isinstance(line, dict) for line in initial_lines)
        ):
            raise AdmError("初始明细须为对象数组，最多1000条")
        for initial_line in initial_lines:
            case["lines"].append(self._new_line(case, initial_line, historical=history is not None))
        case["requestHash"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if history is not None:
            if not user.get("is_admin"):
                raise AdmError("历史归档导入仅限管理员", 403)
            case.update(historicalArchive=True, history=copy.deepcopy(history), status="HISTORICAL")
        self._event(user, case, "history_import" if history is not None else "create", {"sourceCaseId": body.get("sourceCaseId")})
        key = body.get("idempotencyKey")
        if key and (not isinstance(key, str) or len(key) > 150):
            raise AdmError("幂等键无效")
        key = f"{identity(user)}:{key}" if key else None
        if history is not None:
            key = "history:" + history["sourceKey"]
        try:
            created = self.store.create(case, key)
        except Conflict as exc:
            raise AdmError(str(exc), 409, "ADM_CONFLICT") from exc
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        result = self._present(user, created)
        try:
            duplicates = self.store.same_identity(created)
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        result["duplicateCandidates"] = [
            {
                "id": item["id"],
                "admNo": item["admNo"],
                "currency": item["currency"],
                "originalAmount": item["originalAmount"],
                "status": item["status"],
            }
            for item in duplicates
            if item["id"] != created["id"]
            and item["admNo"] == created["admNo"]
            and item["supplierName"] == created["supplierName"]
            and item["supplierType"] == created["supplierType"]
            and self._full(user, item)
        ]
        return result

    def import_case(self, user, body):
        require(user, "adm.import")
        return self.create_case(user, body)

    def case_detail(self, user, case_id):
        return self._present(user, self._read(user, case_id))

    def update_case(self, user, case_id, body):
        case = self._write(user, case_id, body, "adm.edit", True)
        changes = self._clean(body, CASE_FIELDS)
        before = {key: copy.deepcopy(case.get(key)) for key in changes}
        if "analysis" in changes:
            case["analysisVersions"].append(
                {"version": case["version"], "analysis": case["analysis"], "at": now(), "actorId": identity(user)}
            )
        case.update(changes)
        return self._save(user, case, "edit", {"before": before, "after": changes})

    def copy_case(self, user, case_id, body):
        source = self._read(user, case_id)
        if not self._full(user, source):
            raise AdmError("引用新建需完整主单范围", 403)
        if type(body.get("version")) is not int or body["version"] != source["version"]:
            raise AdmError("版本冲突", 409, "ADM_VERSION_CONFLICT")
        return self.create_case(
            user,
            {
                "supplierName": source["supplierName"],
                "supplierType": source["supplierType"],
                "description": source["description"],
                "remark": source["remark"],
                "currency": source["currency"],
                **{key: value for key, value in body.items() if key in CASE_FIELDS or key in {"idempotencyKey", "lines"}},
                "sourceCaseId": source["id"],
            },
        )

    def add_line(self, user, case_id, body):
        case = self._write(user, case_id, body, "adm.edit", True)
        line = self._new_line(case, body)
        case["lines"].append(line)
        return self._save(user, case, "add_line", {"line": copy.deepcopy(line)}, line["id"])

    def bulk_assign(self, user, case_id, body):
        case = self._write(user, case_id, body, "adm.assign", True)
        ids = body.get("lineIds")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
            raise AdmError("批量分配请选择1—100条不同明细")
        for line_id in ids:
            self._line(case, line_id)
        outcomes = []
        version = case["version"]
        for line_id in ids:
            try:
                result = self.line_action(user, case_id, line_id, {"version": version, "action": "assign", "ownerId": body.get("ownerId"), "reason": body.get("reason"), "summary": body.get("summary")})
                version = result["version"]
                saved_line = next(item for item in result["lines"] if item["id"] == line_id)
                outcomes.append({"lineId": line_id, "status": "SAVED", "handoverPending": (saved_line.get("handover") or {}).get("status") == "PENDING"})
            except AdmError as error:
                outcomes.append({"lineId": line_id, "status": "FAILED", "message": str(error), "code": error.code})
                if error.code == "ADM_VERSION_CONFLICT":
                    outcomes.extend({"lineId": item, "status": "SKIPPED", "message": "版本变化，未继续处理"} for item in ids[len(outcomes):])
                    break
        return {"items": outcomes, "successCount": sum(item["status"] == "SAVED" for item in outcomes), "failedCount": sum(item["status"] != "SAVED" for item in outcomes)}

    def _new_line(self, case, body, historical=False):
        line = {
            **{key: "" for key in LINE_FIELDS},
            "id": uid(),
            "businessType": "UNKNOWN",
            "currency": case["currency"],
            "amount": None,
            "amountCny": None,
            "ticketCount": None,
            "status": "PENDING_ASSIGN",
            "ownerId": None,
            "ownerName": "",
            "lockedBy": None,
            "analysis": {},
            "analysisVersions": [],
            "appeals": [],
            "recoveries": [],
            "difference": {
                "declaration": "UNDECLARED",
                "verification": "NOT_CONNECTED",
                "reference": "",
                "evidence": [],
            },
            "finance": {"required": True, "status": "PENDING", "reference": None, "amount": None, "currency": None},
            "appealDecision": "UNDECIDED",
            "recoveryRequired": False,
            "matchStatus": "UNVERIFIED",
            "reviews": [],
            **self._clean(body, LINE_FIELDS),
        }
        if isinstance(body.get("source"), dict):
            line["source"] = copy.deepcopy(body["source"])
        # No approved recovery SLA yet: absence is unknown, not an invented +48h deadline.
        if historical:
            line["status"] = "HISTORICAL"
            line["finance"]["status"] = "HISTORICAL_UNVERIFIED"
        return line

    def update_line(self, user, case_id, line_id, body):
        case = self._write(user, case_id, body, "adm.edit" if has(user, "adm.edit") else "adm.handle")
        line = self._line(case, line_id)
        self._line_access(user, case, line)
        if line["status"] != "PENDING_ASSIGN":
            if "edit" not in self._line_actions(user, case, line):
                raise AdmError("仅当前处理人可编辑处理中明细", 403)
        elif not self._full(user, case):
            raise AdmError("待分配明细需专员编辑", 403)
        changes = self._clean(body, LINE_FIELDS)
        before = {key: copy.deepcopy(line.get(key)) for key in changes}
        if "analysis" in changes:
            line["analysisVersions"].append(
                {
                    "version": case["version"],
                    "analysis": copy.deepcopy(line["analysis"]),
                    "at": now(),
                    "actorId": identity(user),
                }
            )
        line.update(changes)
        return self._save(user, case, "edit_line", {"before": before, "after": changes}, line_id)

    def _evidence(self, case, line_id, ids):
        if not isinstance(ids, list) or not ids:
            raise AdmError("须引用已上传的证据附件")
        allowed = {item["id"] for item in case["attachments"] if item.get("lineId") in {None, "", line_id}}
        if any(item not in allowed for item in ids):
            raise AdmError("附件证据不存在或不属于此明细")
        verifier = self.config.get("ADM_ATTACHMENT_VERIFIER")
        if not callable(verifier):
            raise AdmError("附件存储完整性校验尚未配置", 503, "ADM_UNAVAILABLE")
        referenced = [item for item in case["attachments"] if item["id"] in ids]
        if not all(self._verified_attachment(item) for item in referenced):
            raise AdmError("引用证据缺失、损坏或不可读")
        return list(dict.fromkeys(ids))

    def _verified_attachment(self, item):
        verifier = self.config.get("ADM_ATTACHMENT_VERIFIER")
        if not callable(verifier):
            return False
        try:
            return bool(verifier(copy.deepcopy(item)))
        except Exception:
            return False

    def _submission_blockers(self, case, line):
        blockers = []
        if (line.get("handover") or {}).get("status") == "PENDING":
            blockers.append("仍有待确认交接，请先接受、驳回或取消")
        for key, label in [
            ("description", "问题描述"),
            ("platform", "平台"),
            ("diffType", "差异一级分类"),
            ("diffSecondType", "差异二级分类"),
            ("attribution", "结案归因"),
            ("matchEvidence", "归属核实依据"),
        ]:
            if not line.get(key):
                blockers.append(label + "未填写")
        if line["businessType"] == "UNKNOWN" or line["matchStatus"] == "UNVERIFIED":
            blockers.append("业务类型或我司归属待核实")
        if not line.get("orderNo") and not line.get("unlinkedReason"):
            blockers.append("订单号或未关联依据缺失")
        for key in ("facts", "cause", "proposal", "conclusion"):
            if not line["analysis"].get(key):
                blockers.append("分析" + key + "缺失")
        if line.get("amount") is None or not line.get("currency"):
            blockers.append("分摊金额或币种缺失")
        if line.get("appealDecision") == "UNDECIDED":
            blockers.append("申诉决策未填写")
        if line.get("appealDecision") == "NOT_REQUIRED" and not line.get("appealReason"):
            blockers.append("不申诉原因缺失")
        if line.get("appealDecision") == "REQUIRED" and not line["appeals"]:
            blockers.append("需申诉但尚无申诉记录")
        latest = {}
        for appeal in line["appeals"]:
            latest[(appeal["targetType"], appeal["targetName"])] = appeal
        if any(item["status"] not in {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WITHDRAWN"} for item in latest.values()):
            blockers.append("仍有未终结申诉")
        latest_recovery = {}
        for recovery in line["recoveries"]:
            latest_recovery[(recovery["system"], recovery["pcc"])] = recovery
        if (line.get("recoveryRequired") and not latest_recovery) or any(
            item["status"] != "COMPLETED" for item in latest_recovery.values()
        ):
            blockers.append("必需编码恢复未完成")
        if not line["finance"]["required"] and not line["finance"].get("reason"):
            blockers.append("无需财务处理依据缺失")
        if not any(item.get("lineId") == line["id"] for item in case["attachments"]):
            blockers.append("明细结果证据缺失")
        elif not all(
            self._verified_attachment(item) for item in case["attachments"] if item.get("lineId") == line["id"]
        ):
            blockers.append("明细证据缺失、损坏或不可读")
        return blockers

    def line_action(self, user, case_id, line_id, body):
        action = body.get("action")
        if action in WORKFLOW_ACTIONS:
            return WorkflowService(self).line_action(user, case_id, line_id, body)
        permissions = {
            "lock": "adm.handle",
            "assign": "adm.assign",
            "claim": "adm.handle",
            "unlock": "adm.handle",
            "submit": "adm.handle",
            "approve": "adm.review",
            "return": "adm.review",
            "finance_confirm": "adm.finance.confirm",
            "recovery": "adm.handle",
            "appeal": "adm.handle",
            "difference": "adm.handle",
        }
        if action not in permissions:
            raise AdmError("明细操作无效")
        permission = "adm.unlock.force" if action == "unlock" and has(user, "adm.unlock.force") else permissions[action]
        case = self._write(user, case_id, body, permission)
        line = self._line(case, line_id)
        self._line_access(user, case, line)
        if action not in self._line_actions(user, case, line):
            raise AdmError("当前状态或处理人不允许此操作", 409, "ADM_ACTION_BLOCKED")
        if action == "assign":
            if line["status"] in {"COMPLETED", "WAITING_FINANCE"}:
                raise AdmError("审核完成明细需先重开或退回", 409)
            if line.get("ownerId"):
                detail = WorkflowService(self).request_transfer(user, case, line, body)
                return self._save(user, case, "transfer_request", detail, line_id)
            owner = str(body.get("ownerId") or "")
            if not owner:
                raise AdmError("请选择处理人")
            resolver = self.config.get("ADM_USER_RESOLVER")
            if resolver:
                selected = resolver(owner)
                if not selected or not selected.get("is_enabled", True):
                    raise AdmError("处理人不存在或停用")
                if not has(selected, "adm.view") or not has(selected, "adm.handle"):
                    raise AdmError("处理人尚未配置ADM查看和处理权限，请先在账号管理授权")
                if not selected.get("is_admin") and "adm.center" not in (selected.get("menu_codes") or []):
                    raise AdmError("处理人尚未配置ADM菜单权限")
                owner_name = selected.get("display_name") or selected.get("username") or owner
            elif self.config.get("TESTING"):
                owner_name = owner
            else:
                raise AdmError("处理人目录尚未接入", 503, "ADM_UNAVAILABLE")
            if line.get("ownerId") and not body.get("reason"):
                raise AdmError("转单须填写原因")
            line.update(ownerId=owner, ownerName=owner_name, status="PENDING_ACCEPT", lockedBy=None)
            segment_assign(case, line, str(body.get("reason") or "首次分配"))
        elif action == "claim":
            line.update(status="PROCESSING", lockedBy=identity(user), acceptedAt=now())
            segment_accept(case, line)
        elif action == "lock":
            line["lockedBy"] = identity(user)
        elif action == "unlock":
            if line.get("lockedBy") not in {None, identity(user)} and not str(body.get("reason") or "").strip():
                raise AdmError("强制解锁须填写原因")
            if line.get("lockedBy") not in {None, identity(user)} and not has(user, "adm.unlock.force"):
                raise AdmError("只能解锁本人持单", 403)
            line["lockedBy"] = None
        elif action == "submit":
            blockers = self._submission_blockers(case, line)
            if blockers:
                raise AdmError("；".join(blockers), 409, "ADM_SUBMIT_BLOCKED")
            line.update(status="PENDING_REVIEW", lockedBy=None, submittedAt=now())
        elif action in {"approve", "return"}:
            if not str(body.get("reason") or "").strip():
                raise AdmError("审核意见必填")
            if action == "approve":
                blockers = self._submission_blockers(case, line)
                if blockers:
                    raise AdmError("；".join(blockers), 409)
                line["status"] = "WAITING_FINANCE" if line["finance"]["required"] else "COMPLETED"
            else:
                line.update(status="PROCESSING", lockedBy=line["ownerId"])
            line["reviews"].append(
                {
                    "action": action,
                    "reason": body["reason"],
                    "actorId": identity(user),
                    "at": now(),
                    "version": case["version"],
                }
            )
        elif action == "finance_confirm":
            evidence = self._evidence(case, line_id, body.get("evidence"))
            amount = money(body.get("amount"), False)
            if not body.get("reference") or body.get("currency") != line["currency"]:
                raise AdmError("财务凭证号及对应币种必填")
            if Decimal(amount) > Decimal(line["amount"]):
                raise AdmError("确认金额不能超过明细分摊金额")
            line["finance"].update(
                status="CONFIRMED",
                reference=body["reference"],
                amount=amount,
                currency=body["currency"],
                evidence=evidence,
                confirmedBy=identity(user),
                confirmedAt=now(),
                source="MANUAL_EVIDENCE",
                reason=str(body.get("reason") or ""),
            )
            if (
                amount != line["amount"]
                and Decimal(amount) != Decimal(line["amount"])
                and not line["finance"]["reason"]
            ):
                raise AdmError("财务金额与分摊不同时须说明减免或其他处置")
            line["status"] = "COMPLETED"
        elif action == "recovery":
            self._recovery(user, case, line, body)
        elif action == "appeal":
            self._appeal(user, case, line, body)
        elif action == "difference":
            declaration = body.get("declaration")
            if declaration not in {"UNDECLARED", "MANUAL_DECLARED", "NOT_REQUIRED"}:
                raise AdmError("人工差异声明无效")
            evidence = self._evidence(case, line_id, body.get("evidence")) if declaration == "MANUAL_DECLARED" else []
            if declaration != "UNDECLARED" and not body.get("reason"):
                raise AdmError("差异声明须填写说明")
            line["difference"].update(
                declaration=declaration,
                reference=str(body.get("reference") or ""),
                evidence=evidence,
                reason=str(body.get("reason") or ""),
                updatedBy=identity(user),
                updatedAt=now(),
                verification="NOT_CONNECTED",
            )
        audit = {key: value for key, value in body.items() if key not in {"version", "action"}}
        if line["status"] == "COMPLETED":
            line["completedAt"] = now()
            for segment in line.get("assignmentSegments", []):
                if not segment.get("endedAt"):
                    segment["endedAt"] = line["completedAt"]
        return self._save(user, case, action, audit, line_id)

    def _recovery(self, user, case, line, body):
        status = body.get("status", "PENDING")
        if status not in {"PENDING", "PROCESSING", "COMPLETED", "EXCEPTION"}:
            raise AdmError("恢复状态无效")
        code = str(body.get("code") or body.get("inputCode") or "").strip()
        system, pcc = str(body.get("system") or line.get("system") or ""), str(body.get("pcc") or line.get("pcc") or "")
        if ":" in code:
            context, code = (part.strip() for part in code.split(":", 1))
            if "-" in context:
                system, pcc = (part.strip() for part in context.split("-", 1))
        if not code:
            raise AdmError("待恢复编码必填")
        previous = next(
            (item for item in reversed(line["recoveries"]) if item["system"] == system and item["pcc"] == pcc), None
        )
        if previous and previous["code"] == code and not body.get("recoveryId"):
            return
        if body.get("recoveryId"):
            if not previous or previous["id"] != body["recoveryId"] or previous["code"] != code:
                raise AdmError("恢复任务版本已变化", 409)
            record = previous
        else:
            record = {
                "id": uid(),
                "system": system,
                "pcc": pcc,
                "code": code,
                "originalPnr": line.get("pnr", ""),
                "version": (previous["version"] + 1) if previous else 1,
                "createdAt": now(),
                "history": [],
            }
            line["recoveries"].append(record)
            if previous:
                status = "PENDING"
        if status == "EXCEPTION" and not body.get("reason"):
            raise AdmError("恢复异常须填写原因")
        if status == "COMPLETED" and not body.get("resultCode"):
            raise AdmError("恢复完成须填写恢复后编码")
        evidence = self._evidence(case, line["id"], body.get("evidence")) if status == "COMPLETED" else []
        record.update(
            status=status,
            resultCode=str(body.get("resultCode") or "") if status == "COMPLETED" else "",
            reason=str(body.get("reason") or ""),
            evidence=evidence,
            updatedBy=identity(user),
            updatedAt=now(),
        )
        record["history"].append({key: copy.deepcopy(value) for key, value in record.items() if key != "history"})

    def _appeal(self, user, case, line, body):
        status = body.get("status", "DRAFT")
        if status not in {"DRAFT", "SUBMITTED", "NEED_INFO", "SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WITHDRAWN"}:
            raise AdmError("申诉状态无效")
        target_type, target_name = body.get("targetType"), str(body.get("targetName") or "").strip()
        if target_type not in {"PLATFORM", "SUPPLIER", "AIRLINE"} or not target_name or not body.get("reason"):
            raise AdmError("申诉对象类型、主体和原因必填")
        evidence = (
            self._evidence(case, line["id"], body.get("evidence"))
            if status in {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WITHDRAWN"}
            else []
        )
        record = {
            "id": uid(),
            "targetType": target_type,
            "targetName": target_name,
            "status": status,
            "reason": body["reason"],
            "evidence": evidence,
            "at": now(),
            "actorId": identity(user),
            "round": 1,
            "currency": line["currency"],
            "amount": money(body.get("amount")),
            "waivedAmount": money(body.get("waivedAmount")),
        }
        previous = next(
            (
                item
                for item in reversed(line["appeals"])
                if item["targetType"] == target_type and item["targetName"] == target_name
            ),
            None,
        )
        record["round"] = previous["round"] + 1 if previous else 1
        if status in {"SUCCESS", "PARTIAL_SUCCESS"} and record["waivedAmount"] is None:
            raise AdmError("申诉成功须明确减免金额")
        if record["waivedAmount"] and (
            line["amount"] is None or Decimal(record["waivedAmount"]) > Decimal(line["amount"])
        ):
            raise AdmError("减免金额超过明细金额")
        line["appeals"].append(record)

    def _closure(self, case):
        checks = []

        def check(code, label, passed, line_id=None):
            checks.append(
                {"code": code, "label": label, "passed": bool(passed), **({"lineId": line_id} if line_id else {})}
            )

        check(
            "ACTIVE",
            "主单已发布且未挂起作废",
            case["status"] != "DRAFT" and not case.get("paused") and not case.get("voided"),
        )
        check("LINES", "至少一条订单处理明细", bool(case["lines"]))
        check("ORIGINAL", "已上传下发原件", any(item["category"] == "ORIGINAL" for item in case["attachments"]))
        evidence_ids = set()
        for line in case["lines"]:
            evidence_ids.update(line["finance"].get("evidence") or [])
            evidence_ids.update(line["difference"].get("evidence") or [])
            for record in line["appeals"] + line["recoveries"]:
                evidence_ids.update(record.get("evidence") or [])
        required_files = [
            item
            for item in case["attachments"]
            if item["category"] == "ORIGINAL" or item["id"] in evidence_ids or item.get("lineId")
        ]
        check(
            "FILES_INTACT",
            "原件及必需证据仍可读且校验完整",
            bool(required_files)
            and evidence_ids <= {item["id"] for item in required_files}
            and all(self._verified_attachment(item) for item in required_files),
        )
        check(
            "IDENTITY",
            "ADM身份及日期截止完整",
            all(case.get(key) for key in ("admNo", "supplierName", "issuedDate", "deadline", "description")),
        )
        check(
            "ANALYSIS",
            "主单事实、结论和预防改进完整",
            all(case["analysis"].get(key) for key in ("facts", "conclusion", "prevention")),
        )
        allocated = sum(
            (
                Decimal(line["amount"])
                for line in case["lines"]
                if line.get("amount") is not None and line.get("currency") == case["currency"]
            ),
            Decimal("0"),
        )
        original = Decimal(case["originalAmount"]) if case.get("originalAmount") is not None else None
        gap = original - allocated if original is not None else None
        check(
            "AMOUNTS",
            "原币金额全部分摊核平",
            gap == 0
            and original is not None
            and all(
                line.get("amount") is not None and line.get("currency") == case["currency"] for line in case["lines"]
            ),
        )
        for line in case["lines"]:
            check(
                "LINE_COMPLETED",
                "明细已完成审核和必需财务",
                line["status"] == "COMPLETED"
                and bool(line["reviews"])
                and (not line["finance"]["required"] or line["finance"]["status"] == "CONFIRMED"),
                line["id"],
            )
        return {
            "canClose": all(item["passed"] for item in checks),
            "checks": checks,
            "blockers": [
                item["label"] + ("：" + item["lineId"] if item.get("lineId") else "")
                for item in checks
                if not item["passed"]
            ],
            "amounts": {
                "currency": case["currency"],
                "originalAmount": case.get("originalAmount"),
                "allocatedAmount": format(allocated, "f"),
                "gap": format(gap, "f") if gap is not None else None,
            },
        }

    def closure_check(self, user, case_id):
        case = self._read(user, case_id)
        return self._present(user, case)["closureCheck"]

    def timeline(self, user, case_id):
        return self.case_detail(user, case_id)["timeline"]

    def case_action(self, user, case_id, body):
        action = body.get("action")
        if action == "coordinator":
            return WorkflowService(self).coordinate(user, case_id, body)
        if action not in {"publish", "pause", "resume", "void", "close", "reopen"}:
            raise AdmError("主单操作无效")
        permission = {"close": "adm.close", "reopen": "adm.reopen"}.get(action, "adm.edit")
        case = self._write(user, case_id, body, permission, True, control_action=action)
        if action == "publish":
            if case["status"] != "DRAFT" or not case["lines"] or not case.get("admNo") or not case.get("supplierName"):
                raise AdmError("仅有明细且身份完整的草稿可发布", 409)
            case["status"] = "PENDING_ASSIGN"
        elif action in {"pause", "void"}:
            if not body.get("reason"):
                raise AdmError("挂起或作废原因必填")
            if action == "pause" and not body.get("reviewDate"):
                raise AdmError("挂起复查日期必填")
            case["paused" if action == "pause" else "voided"] = True
            case["pauseReason" if action == "pause" else "voidReason"] = body["reason"]
            if action == "pause":
                case["pauseReviewDate"] = body["reviewDate"]
        elif action == "resume":
            if case.get("voided"):
                raise AdmError("作废主单不能恢复", 409)
            case["paused"] = False
        elif action == "close":
            checks = self._closure(case)
            if not checks["canClose"]:
                raise AdmError("；".join(checks["blockers"]), 409, "ADM_CLOSE_BLOCKED")
            snapshot = copy.deepcopy({key: value for key, value in case.items() if key != "snapshots"})
            case["snapshots"].append(
                {
                    "id": uid(),
                    "closedAt": now(),
                    "closedBy": identity(user),
                    "round": case["round"],
                    "sha256": hashlib.sha256(
                        json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
                    ).hexdigest(),
                    "data": snapshot,
                }
            )
            case.update(status="CLOSED", closedAt=now(), closedBy=identity(user))
        else:
            if case["status"] != "CLOSED" or not body.get("reason"):
                raise AdmError("重开须为已结案并填写原因", 409)
            ids = body.get("lineIds") or [line["id"] for line in case["lines"]]
            if (
                not isinstance(ids, list)
                or not ids
                or any(item not in {line["id"] for line in case["lines"]} for item in ids)
            ):
                raise AdmError("重开明细范围无效")
            for line in case["lines"]:
                if line["id"] in ids:
                    line.update(status="PENDING_ACCEPT" if line.get("ownerId") else "PENDING_ASSIGN", lockedBy=None)
                    if line["finance"]["required"]:
                        line["finance"]["status"] = "PENDING"
            case.update(status="PROCESSING", round=case["round"] + 1, closedAt=None, closedBy=None)
        return self._save(
            user, case, action, {key: value for key, value in body.items() if key not in {"version", "action"}}
        )

    def add_attachment(self, user, case_id, body):
        attachment = body.get("attachment")
        if not isinstance(attachment, dict) or not all(
            attachment.get(key) for key in ("id", "name", "category", "storageKey", "sha256")
        ):
            raise AdmError("附件元数据不完整")
        if attachment["category"] not in CATEGORIES:
            raise AdmError("附件分类无效")
        line_id = attachment.get("lineId")
        permission = "adm.edit" if has(user, "adm.edit") else "adm.handle"
        if line_id and not has(user, "adm.edit"):
            current = self._read(user, case_id)
            current_line = self._line(current, line_id)
            if current_line["status"] == "PENDING_REVIEW":
                permission = "adm.review"
            elif current_line["status"] == "WAITING_FINANCE":
                permission = "adm.finance.confirm"
        case = self._write(user, case_id, body, permission, control_action="archive_attachment")
        if line_id:
            line = self._line(case, line_id)
            self._line_access(user, case, line)
            if not (self._full(user, case) and has(user, "adm.edit")):
                if "upload" not in self._line_actions(user, case, line):
                    raise AdmError("当前节点无明细材料上传权限", 403)
                permitted = ["FINANCE"] if line["status"] == "WAITING_FINANCE" else ["VERIFICATION", "ANALYSIS"] if line["status"] == "PENDING_REVIEW" else CATEGORIES
                if attachment["category"] not in permitted:
                    raise AdmError("此节点仅允许上传对应审核/财务材料", 403)
        elif not (self._full(user, case) and has(user, "adm.edit")):
            raise AdmError("无主单材料上传权限", 403)
        if any(item["id"] == attachment["id"] for item in case["attachments"]):
            raise AdmError("附件ID重复", 409)
        metadata = copy.deepcopy(attachment)
        metadata.update(
            uploadedBy=identity(user),
            createdAt=now(),
            version=1
            + sum(item["name"] == attachment["name"] and item.get("lineId") == line_id for item in case["attachments"]),
        )
        case["attachments"].append(metadata)
        if case.get("historicalArchive"):
            case["history"]["attachmentState"] = "MANUALLY_SUPPLEMENTED"
        return self._save(
            user,
            case,
            "attachment_added",
            {"attachmentId": metadata["id"], "name": metadata["name"], "category": metadata["category"]},
            line_id,
        )

    def attachment(self, user, case_id, attachment_id):
        case = self._read(user, case_id)
        attachment = next((item for item in case["attachments"] if item["id"] == str(attachment_id)), None)
        if not attachment:
            raise AdmError("附件不存在", 404)
        if not self._full(user, case) and attachment.get("lineId") not in {
            line["id"] for line in self._visible_lines(user, case)
        }:
            raise AdmError("无附件权限", 403)
        return copy.deepcopy(attachment)
