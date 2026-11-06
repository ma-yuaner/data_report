"""ADM application rules, authorization and atomic audit history."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .normalized_store import AdmStore
from .store import Conflict, StoreUnavailable
from .policy import AdmError, has, identity, now, require, uid
from .workflow import WORKFLOW_ACTIONS, WorkflowService, associated_ids, role_actions, segment_assign, segment_accept
from .access import file_visible, upload_categories
from .v05 import (
    ATTRIBUTIONS,
    ORDER_STATUSES,
    collection_total,
    exact_amounts,
    require_exact_amounts,
    validate_attribution,
)

CASE_STATUSES = ["DRAFT", "PENDING_LEADER_ASSIGNMENT", "IN_PROGRESS", "READY_TO_CLOSE", "CLOSED", "HISTORICAL"]
LINE_STATUSES = [*ORDER_STATUSES, "HISTORICAL"]
CATEGORIES = ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "COLLECTION", "ANALYSIS"]
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
    "supplierCode", "supplier",
    "actualOwner", "actualHandler", "recoveryDeadline", "resolution",
    "businessType",
    "platform",
    "shop",
    "site",
    "orderNo",
    "ticketNo",
    "pnr",
    "attachmentUrl",
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
    "investigationNote",
    "departmentCode",
    "departmentName",
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


def internal_adm_no(adm_no, case_id):
    """Compatibility number for pre-readable-number documents only."""
    suffix = str(case_id or "").replace("-", "").upper()[:8]
    prefix = str(adm_no or "").strip()[:34]
    return f"{prefix}-LEGACY-{suffix}"


def next_line_internal_no(case):
    prefix = str(case.get("internalNo") or "").strip()
    if not prefix:
        return ""
    used = []
    for line in case.get("lines") or []:
        match = re.fullmatch(re.escape(prefix) + r"-(\d+)", str(line.get("lineInternalNo") or ""))
        if match:
            used.append(int(match.group(1)))
    return f"{prefix}-{max(used, default=0) + 1:03d}"


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
        self._reference_options_cache = None
        try:
            self.store = AdmStore(config)
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc

    def _reference_options(self):
        if self._reference_options_cache is None:
            provider = self.config.get("ADM_REFERENCE_OPTIONS")
            self._reference_options_cache = provider() if callable(provider) else {}
        return self._reference_options_cache

    def _get(self, case_id):
        try:
            case = self.store.get(str(case_id))
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        if not case:
            raise AdmError("ADM不存在", 404, "ADM_NOT_FOUND")
        return case

    def _get_by_internal_no(self, internal_no):
        try:
            case = self.store.get_by_internal_no(str(internal_no))
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
        # 全量查询范围不等于操作权限。只有管理员或本单ADM负责人
        # 拥有整单管理范围，避免scope.all账号越权修改他人的单。
        return bool(user.get("is_admin")) or str(coordinator) == identity(user)

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
        case_people = {
            str(value)
            for value in (
                case.get("ownerId"),
                (case.get("handover") or {}).get("toId")
                if (case.get("handover") or {}).get("status") == "PENDING"
                else None,
            )
            if value
        }
        if case_people & ids:
            return case["lines"]
        return [line for line in case["lines"] if associated_ids(line) & ids]

    def _read(self, user, case_id):
        require(user, "adm.view")
        return self._get(case_id)

    def _read_by_internal_no(self, user, internal_no):
        require(user, "adm.view")
        return self._get_by_internal_no(internal_no)

    def _write(self, user, case_id, body, permission, full=False, control_action=None):
        require(user, permission)
        case = self._read(user, case_id)
        if full and not self._full(user, case):
            raise AdmError("此操作需完整主单范围", 403, "ADM_FORBIDDEN")
        if type(body.get("version")) is not int or body["version"] != case["version"]:
            raise AdmError("版本冲突，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
        if case.get("historicalArchive") and not (control_action == "archive_attachment" and user.get("is_admin")):
            raise AdmError("历史档案只读；请引用新建继续处理，保留原始状态", 409, "ADM_HISTORY_READ_ONLY")
        if case["status"] == "CLOSED" and control_action not in {"reopen", "remediation"}:
            raise AdmError("已结案只读，请授权重开", 409, "ADM_CLOSED")
        if (case.get("paused") or case.get("voided")) and control_action not in {"resume", "reopen"}:
            raise AdmError("主单已挂起或作废", 409, "ADM_INACTIVE")
        return case

    def _line(self, case, line_id):
        reference = str(line_id)
        line = next(
            (
                item for item in case["lines"]
                if item["id"] == reference or str(item.get("lineInternalNo") or "") == reference
            ),
            None,
        )
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
            detail["responsibility"] = {"ownerId": case.get("ownerId"), "ownerName": case.get("ownerName"), "round": case["round"]}
            detail["measurement"] = {"ownerId": case.get("ownerId"), "ownerName": case.get("ownerName"), "round": case["round"], "businessType": line.get("businessType"), "lineStatus": line["status"]}
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
        case["openRemediation"] = False
        if case["status"] in {"CLOSED", "DRAFT", "HISTORICAL"}:
            return
        states = {line["status"] for line in case["lines"]}
        if not states or states == {"PENDING_LEADER_ASSIGNMENT"}:
            case["status"] = "PENDING_LEADER_ASSIGNMENT"
        elif states == {"COMPLETED"}:
            case["status"] = "READY_TO_CLOSE"
        else:
            case["status"] = "IN_PROGRESS"

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
        return self._present_with_difference_verification(user, case)

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
            if field == "attachmentUrl" and value and not re.fullmatch(r"https://[^\s]{1,2048}", value):
                raise AdmError("附件地址须为有效HTTPS地址")
            if field in {"admNo", "supplierCode"} and len(value) > (100 if field == "admNo" else 200):
                raise AdmError("ADM号最多100字，下发方编码最多200字")
            if field == "matchStatus" and value not in {"UNVERIFIED", "OURS", "NOT_OURS"}:
                raise AdmError("订单归属无效")
            if field == "appealDecision" and value not in {"UNDECIDED", "REQUIRED", "NOT_REQUIRED"}:
                raise AdmError("申诉决策无效")
            result[field] = value
        return result

    def _apply_exchange_rate(self, case, *, force=False):
        """Fill a missing CNY amount and retain the exact ERP row used."""
        currency = str(case.get("currency") or "").strip()
        original = case.get("originalAmount")
        if not currency or original in (None, ""):
            if force:
                case.update(fxRate=None, fxDate=None, fxSource=None)
            return
        if case.get("originalAmountCny") not in (None, "") and not force:
            return
        provider = self.config.get("ADM_EXCHANGE_RATE_LOOKUP")
        if currency == "CNY" and not callable(provider):
            case["originalAmountCny"] = format(Decimal(str(original)).quantize(Decimal("0.00000001")), "f")
            case["fxRate"] = "1.00000000"
            case["fxDate"] = now()
            case["fxSource"] = {
                "rate": "1.00000000", "effectiveAt": case["fxDate"], "rowId": None,
                "source": "BASE_CURRENCY", "actualSource": None,
                "baseCurrency": "CNY", "exchangeCurrency": "CNY", "rateColumn": "identity",
            }
            return
        if not callable(provider):
            # Explicitly entered CNY values remain supported in isolated/test
            # deployments that intentionally have no ERP reference provider.
            if case.get("originalAmountCny") in (None, ""):
                raise AdmError("汇率参考数据提供器未配置", 503, "ADM_EXCHANGE_RATE_UNAVAILABLE")
            return
        snapshot = provider(currency)
        rate = Decimal(str(snapshot["rate"]))
        amount = Decimal(str(original)) * rate
        case["originalAmountCny"] = format(amount.quantize(Decimal("0.00000001")), "f")
        case["fxRate"] = format(rate, ".8f")
        case["fxDate"] = snapshot["effectiveAt"]
        case["fxSource"] = copy.deepcopy(snapshot)

    def _apply_line_exchange_rate(self, case, line, *, force=False):
        if line.get("amount") in (None, ""):
            if force:
                line["amountCny"] = None
            return
        if line.get("amountCny") not in (None, "") and not force:
            return
        rate = case.get("fxRate")
        if rate in (None, ""):
            currency = str(case.get("currency") or "")
            provider = self.config.get("ADM_EXCHANGE_RATE_LOOKUP")
            if currency == "CNY" and not callable(provider):
                snapshot = {
                    "rate": "1.00000000", "effectiveAt": now(), "rowId": None,
                    "source": "BASE_CURRENCY", "actualSource": None,
                    "baseCurrency": "CNY", "exchangeCurrency": "CNY", "rateColumn": "identity",
                }
            elif callable(provider):
                snapshot = provider(currency)
            else:
                raise AdmError("汇率参考数据提供器未配置", 503, "ADM_EXCHANGE_RATE_UNAVAILABLE")
            rate = snapshot["rate"]
            case["fxRate"] = format(Decimal(str(rate)), ".8f")
            case["fxDate"] = snapshot["effectiveAt"]
            case["fxSource"] = copy.deepcopy(snapshot)
        amount = Decimal(str(line["amount"])) * Decimal(str(rate))
        line["amountCny"] = format(amount.quantize(Decimal("0.00000001")), "f")

    def config_info(self, user):
        require(user, "adm.view")
        try:
            self.store.check()
        except StoreUnavailable as exc:
            raise AdmError(str(exc), 503, exc.code) from exc
        people_provider = self.config.get("ADM_WORKFLOW_USER_OPTIONS")
        people = people_provider() if callable(people_provider) and any(has(user, p) for p in ("adm.assign", "adm.handle")) else {}
        reference_provider = self.config.get("ADM_REFERENCE_OPTIONS")
        references = self._reference_options() if callable(reference_provider) else {
            "platforms": [], "suppliers": [],
            "exchangeRateSource": {"table": "sibe_exchange_rate", "configured": False, "limitation": "参考数据提供器未配置"},
        }
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
            "references": references,
        }

    def _apply_line_references(self, line, validate_difference_type=True):
        reference_provider = self.config.get("ADM_REFERENCE_OPTIONS")
        references = self._reference_options() if callable(reference_provider) else None
        for code_key, name_key, collection, label in (
            ("platformCode", "platform", "platforms", "OTA平台"),
            ("supplierCode", "supplier", "suppliers", "供应商"),
        ):
            code = str(line.get(code_key) or "")
            if not code:
                line[name_key] = ""
                continue
            if references is None:
                continue
            option = next((item for item in references.get(collection, []) if item["code"] == code), None)
            if not option:
                raise AdmError(f"{label}编码不存在或不在当前启用来源中")
            line[name_key] = option["name"]
        difference_type = str(line.get("diffType") or "").strip()
        if validate_difference_type and difference_type and references is not None and "differenceTypes" in references:
            enabled = {
                str(item.get("code") or item.get("name") or "").strip()
                for item in references.get("differenceTypes", [])
            }
            if difference_type not in enabled:
                raise AdmError("差异类型不存在或不在当前启用来源中")
            line["diffType"] = difference_type
        people_provider = self.config.get("ADM_WORKFLOW_USER_OPTIONS")
        people = people_provider() if callable(people_provider) else {}
        department_code = str(line.get("departmentCode") or "")
        if department_code and callable(people_provider):
            department = next((item for item in people.get("departments", []) if item["code"] == department_code), None)
            if not department:
                raise AdmError("业务归属部门不存在或不在当前组织来源中")
            line["departmentName"] = department["name"]

    def _require_assignment_ready(self, case, line):
        require_exact_amounts(case)
        for key, label in (("departmentCode", "业务归属部门"), ("diffType", "差异类型"), ("diffSecondType", "细分差异原因")):
            if not str(line.get(key) or "").strip():
                raise AdmError(label + "未填写", 409, "ADM_ASSIGNMENT_BLOCKED")

    def _public_attachment(self, item, *, can_download=False):
        return {**{key: value for key, value in item.items() if key != "storageKey"}, "canDownload": can_download}

    def _present(self, user, source, detail=True):
        case = copy.deepcopy(source)
        case["legacyCoordination"] = "coordinatorId" not in source
        case["coordinatorId"] = source.get("coordinatorId", source["createdBy"])
        full = self._full(user, source)
        # ADM台账是全员可查询的业务账本。是否可以办理仍由_full、
        # _line_actions和各写接口单独判定，不能用字段裁剪代替操作鉴权。
        whole_case_visible = True
        visible = source["lines"]
        ids = {line["id"] for line in visible}
        download_ids = {line["id"] for line in self._visible_lines(user, source)}
        case["partial"] = not whole_case_visible
        case["lines"] = copy.deepcopy(visible)
        case["attachments"] = [
            self._public_attachment(item, can_download=full or file_visible(item, download_ids))
            for item in case["attachments"]
            if whole_case_visible or file_visible(item, ids)
        ]
        case["timeline"] = [item for item in case["timeline"] if whole_case_visible or item.get("lineId") in ids]
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
            line["attachments"] = [item for item in case["attachments"] if file_visible(item, {line["id"]})]
            line["allowedActions"] = self._line_actions(user, source, line)
            line["uploadCategories"] = upload_categories(user, source, line, full) if "upload" in line["allowedActions"] else []
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
        full = self._full(user, case)
        status = line["status"]
        actor = identity(user)
        mine = str(case.get("ownerId") or line.get("ownerId")) == actor
        if status == "PENDING_LEADER_ASSIGNMENT" and full and has(user, "adm.edit"):
            result.append("edit")
        if case["status"] == "DRAFT":
            return result
        if full and has(user, "adm.assign"):
            if status in {"PENDING_LEADER_ASSIGNMENT", "PENDING_OPERATOR_ASSIGNMENT"} and not case.get("ownerId"):
                result.append("assign_operator")
            if status not in {"PENDING_REVIEW", "PENDING_COLLECTION", "COMPLETED", "HISTORICAL"}:
                result.append("plan")
        if mine and has(user, "adm.handle"):
            if status == "PENDING_CODE_PROCESSING":
                recovery = (line.get("recovery") or {}).get("state", "UNDECIDED")
                if recovery == "UNDECIDED":
                    result.append("recovery_decide")
                elif recovery == "WAITING_MANUAL":
                    result.append("recovery_complete")
            if status == "PENDING_DECISION":
                result.append("decide")
            if status == "APPEAL_IN_PROGRESS":
                result.append("appeal_result")
            if status == "REJECTED_FOR_REVISION":
                result.append("resubmit")
            if status in {
                "PENDING_CODE_PROCESSING",
                "PENDING_DECISION",
                "APPEAL_IN_PROGRESS",
                "REJECTED_FOR_REVISION",
            }:
                result += ["edit", "upload"]
        coordinator = str(case.get("coordinatorId", case["createdBy"]))
        is_reviewer = bool(user.get("is_admin")) or actor == coordinator
        if status == "PENDING_REVIEW" and has(user, "adm.review") and is_reviewer:
            if not mine or self.config.get("ADM_ALLOW_SELF_REVIEW", False):
                result += ["approve", "return", "upload"]
        if status == "PENDING_COLLECTION" and has(user, "adm.review") and is_reviewer:
            result += ["record_collection", "upload"]
        return list(dict.fromkeys(result + role_actions(user, case, line, full)))

    def list_cases(self, user, filters):
        require(user, "adm.view")
        scope = filters.get("scope", "mine")
        if scope not in {"mine", "team", "all"}:
            raise AdmError("范围无效")
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

    def create_case(self, user, body, history=None, activate_import=False):
        require(user, "adm.create")
        require(user, "adm.view")
        fields = self._clean(body, CASE_FIELDS)
        if not fields.get("admNo") or not fields.get("supplierName"):
            raise AdmError("ADM号和下发方必填")
        case_id = uid()
        case = {
            "id": case_id,
            "contractVersion": "ADM_V05",
            "version": 1,
            "status": "DRAFT",
            "paused": False,
            "voided": False,
            "createdBy": identity(user),
            "coordinatorId": identity(user),
            "coordinatorName": user.get("display_name") or user.get("username") or identity(user),
            "ownerId": None,
            "ownerName": "",
            "handover": None,
            "handoverHistory": [],
            "assignmentSegments": [],
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
        case.update(fxRate=None, fxDate=None, fxSource=None)
        self._apply_exchange_rate(case)
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
            case["lines"].append(self._new_line(case, initial_line, historical=history is not None, activate_import=activate_import))
        if activate_import:
            require(user, "adm.assign")
            require_exact_amounts(case)
            owners = {(line.get("ownerId"), line.get("ownerName")) for line in case["lines"] if line.get("ownerId")}
            if not case["lines"] or len(owners) != 1 or any(line["status"] != "PENDING_CODE_PROCESSING" for line in case["lines"]):
                raise AdmError("19列建单导入的同一ADM必须指定同一有效整单承办人", 422, "ADM_IMPORT_INVALID")
            owner_id, owner_name = owners.pop()
            case.update(ownerId=owner_id, ownerName=owner_name)
            assigned_at = now()
            case["assignmentSegments"].append(
                {"id": uid(), "ownerId": owner_id, "ownerName": owner_name, "assignedAt": assigned_at,
                 "acceptedAt": assigned_at, "endedAt": None, "round": case["round"], "reason": "19列建单导入"}
            )
            case["status"] = "IN_PROGRESS"
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
        result = self._present_with_difference_verification(user, created)
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
        activate = (body.get("source") or {}).get("system") == "daily19"
        return self.create_case(user, body, activate_import=activate)

    def case_detail(self, user, case_id):
        return self._present_with_difference_verification(user, self._read(user, case_id))

    def _present_with_difference_verification(self, user, source):
        case = self._present(user, source)
        if not case.get("internalNo") and case.get("admNo") and case.get("id"):
            case["internalNo"] = internal_adm_no(case["admNo"], case["id"])
        lines = case.get("lines") or []
        lookup = self.config.get("ADM_DIFFERENCE_MATCH_LOOKUP")
        checked_at = now()
        if not callable(lookup):
            return case
        internal_no = str(case.get("internalNo") or "").strip()
        values = [str(line.get("orderNo") or "").strip() for line in lines]
        if internal_no:
            values.append(internal_no)
        try:
            matched = set(lookup(values))
        except Exception:
            for line in lines:
                difference = line.setdefault("difference", {})
                difference.update(
                    verification="CHECK_FAILED", matchedBy=None, matchedValue=None,
                    checkedAt=checked_at,
                )
            return case
        for line in lines:
            order_no = str(line.get("orderNo") or "").strip()
            difference = line.setdefault("difference", {})
            if order_no and order_no in matched:
                verification, matched_by, matched_value = "RECORDED", "OTA_ORDER_NO", order_no
            elif internal_no and internal_no in matched:
                verification, matched_by, matched_value = "RECORDED", "INTERNAL_ADM_NO", internal_no
            else:
                verification, matched_by, matched_value = "NOT_RECORDED", None, None
            difference.update(
                verification=verification, matchedBy=matched_by, matchedValue=matched_value,
                checkedAt=checked_at,
            )
        return case

    def update_case(self, user, case_id, body):
        case = self._write(user, case_id, body, "adm.edit", True)
        changes = self._clean(body, CASE_FIELDS)
        before = {key: copy.deepcopy(case.get(key)) for key in changes}
        if "analysis" in changes:
            case["analysisVersions"].append(
                {"version": case["version"], "analysis": case["analysis"], "at": now(), "actorId": identity(user)}
            )
        previous_currency = case.get("currency")
        case.update(changes)
        if "originalAmountCny" in changes:
            case.update(fxRate=None, fxDate=None, fxSource=None)
        explicit_cny = "originalAmountCny" in changes and changes["originalAmountCny"] not in (None, "")
        currency_changed = "currency" in changes and case.get("currency") != previous_currency
        if currency_changed and not explicit_cny:
            if case.get("fxSource"):
                case.setdefault("fxHistory", []).append(
                    {"rate": case.get("fxRate"), "date": case.get("fxDate"), "source": copy.deepcopy(case.get("fxSource")), "changedAt": now(), "changedBy": identity(user)}
                )
            case.update(originalAmountCny=None, fxRate=None, fxDate=None, fxSource=None)
            self._apply_exchange_rate(case, force=True)
        elif "originalAmount" in changes and not explicit_cny:
            if case.get("fxRate") not in (None, ""):
                case["originalAmountCny"] = format(
                    (Decimal(str(case["originalAmount"])) * Decimal(str(case["fxRate"]))).quantize(Decimal("0.00000001")),
                    "f",
                )
            else:
                self._apply_exchange_rate(case, force=True)
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
        if not case.get("lines"):
            raise AdmError("主单没有可分配的订单明细", 409)
        return self.line_action(
            user,
            case_id,
            case["lines"][0]["id"],
            {**body, "action": "assign_operator", "version": case["version"]},
        )

    def _new_line(self, case, body, historical=False, activate_import=False):
        line = {
            **{key: "" for key in LINE_FIELDS},
            "id": uid(),
            "businessType": "UNKNOWN",
            "currency": case["currency"],
            "amount": None,
            "amountCny": None,
            "ticketCount": None,
            "status": "PENDING_LEADER_ASSIGNMENT",
            "leaderId": None,
            "leaderName": "",
            "ownerId": case.get("ownerId"),
            "ownerName": case.get("ownerName", ""),
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
            # Kept as a read-only legacy snapshot for pre-0.5 documents. New
            # workflow writes collectionExpectedAmount/collections instead.
            "finance": {"required": False, "status": "NOT_APPLICABLE", "reference": None, "amount": None, "currency": None},
            "appealDecision": "UNDECIDED",
            "processingResult": "UNDECIDED",
            "attribution": "",
            "recoveryRequired": False,
            "recovery": {
                "state": "UNDECIDED",
                "decidedBy": None,
                "decidedAt": None,
                "completedBy": None,
                "completedAt": None,
            },
            "reviewResult": "UNDECIDED",
            "reviewedBy": None,
            "reviewedAt": None,
            "collectionExpectedAmount": None,
            "collectionStatus": "NOT_REQUIRED",
            "collections": [],
            "matchStatus": "UNVERIFIED",
            "reviews": [],
            **self._clean(body, LINE_FIELDS),
        }
        line["lineInternalNo"] = next_line_internal_no(case)
        line["currency"] = case["currency"]
        self._apply_line_exchange_rate(case, line)
        self._apply_line_references(line, validate_difference_type=not historical)
        if activate_import:
            owner_id, owner_name = WorkflowService(self).resolve(body.get("initialOwnerId"), "handle")
            line.update(ownerId=owner_id, ownerName=owner_name, status="PENDING_CODE_PROCESSING", assignedAt=now())
            segment_assign(case, line, "19列建单导入")
        if isinstance(body.get("source"), dict):
            line["source"] = copy.deepcopy(body["source"])
        if case.get("ownerId") and not historical and not activate_import:
            line.update(status="PENDING_CODE_PROCESSING", assignedAt=now())
            segment_assign(case, line, "新增订单沿用整单当前承办人")
        # No approved recovery SLA yet: absence is unknown, not an invented +48h deadline.
        if historical:
            line["status"] = "HISTORICAL"
            line["finance"]["status"] = "HISTORICAL_UNVERIFIED"
        return line

    def update_line(self, user, case_id, line_id, body):
        case = self._write(user, case_id, body, "adm.edit" if has(user, "adm.edit") else "adm.handle")
        line = self._line(case, line_id)
        self._line_access(user, case, line)
        if line["status"] != "PENDING_LEADER_ASSIGNMENT":
            if "edit" not in self._line_actions(user, case, line):
                raise AdmError("仅当前处理人可编辑处理中明细", 403)
        elif not self._full(user, case):
            raise AdmError("待分配明细需专员编辑", 403)
        changes = self._clean(body, LINE_FIELDS)
        if "currency" in changes and changes["currency"] != case["currency"]:
            raise AdmError("明细币种必须引用主单币种，不能独立修改")
        changes.pop("currency", None)
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
        if "amount" in changes and not ("amountCny" in changes and changes["amountCny"] not in (None, "")):
            line["amountCny"] = None
            self._apply_line_exchange_rate(case, line, force=True)
        self._apply_line_references(line)
        return self._save(user, case, "edit_line", {"before": before, "after": changes}, line_id)

    def _evidence(self, case, line_id, ids):
        if not isinstance(ids, list) or not ids:
            raise AdmError("须引用已上传的证据附件")
        allowed = {item["id"] for item in case["attachments"] if item.get("lineId") in {None, "", line_id} or file_visible(item, {line_id})}
        if any(not isinstance(item, str) or item not in allowed for item in ids):
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
        if (case.get("handover") or {}).get("status") == "PENDING":
            blockers.append("仍有待确认交接，请先接受、驳回或取消")
        for key, label in [("diffType", "差异类型"), ("diffSecondType", "细分差异原因")]:
            if not line.get(key):
                blockers.append(label + "未填写")
        if line.get("amount") is None or not line.get("currency"):
            blockers.append("明细原币金额或主单币种缺失")
        recovery_state = (line.get("recovery") or {}).get("state")
        if recovery_state not in {"NOT_REQUIRED", "MANUALLY_COMPLETED"}:
            blockers.append("恢复编码前置尚未人工完成")
        if line.get("processingResult") == "UNDECIDED":
            blockers.append("处理结果未填写")
        if line.get("processingResult") == "NO_APPEAL" and not line.get("appealReason"):
            blockers.append("不申诉原因缺失")
        if line.get("processingResult") in {"NO_APPEAL", "APPEAL_FAILED"} and line.get("attribution") not in ATTRIBUTIONS:
            blockers.append("问题归因未填写")
        return blockers

    def line_action(self, user, case_id, line_id, body):
        action = body.get("action")
        if action in WORKFLOW_ACTIONS:
            return WorkflowService(self).line_action(user, case_id, line_id, body)
        permissions = {
            "assign_operator": "adm.assign",
            "recovery_decide": "adm.handle",
            "recovery_complete": "adm.handle",
            "decide": "adm.handle",
            "appeal_result": "adm.handle",
            "resubmit": "adm.handle",
            "approve": "adm.review",
            "return": "adm.review",
            "record_collection": "adm.review",
        }
        if action not in permissions:
            raise AdmError("明细操作无效")
        case = self._write(user, case_id, body, permissions[action])
        line = self._line(case, line_id)
        self._line_access(user, case, line)
        if action not in self._line_actions(user, case, line):
            raise AdmError("当前状态或处理人不允许此操作", 409, "ADM_ACTION_BLOCKED")
        actor = identity(user)

        def resolve(value, purpose):
            return WorkflowService(self).resolve(value, purpose)

        if action == "assign_operator":
            for candidate in case["lines"]:
                if candidate["status"] not in {"PENDING_LEADER_ASSIGNMENT", "PENDING_OPERATOR_ASSIGNMENT"}:
                    raise AdmError("整单已有订单进入办理，不能再次分配；请使用整单转派", 409)
                self._require_assignment_ready(case, candidate)
            owner_id, owner_name = resolve(body.get("ownerId"), "handle")
            case.update(ownerId=owner_id, ownerName=owner_name)
            assigned_at = now()
            for candidate in case["lines"]:
                candidate.update(
                    ownerId=owner_id,
                    ownerName=owner_name,
                    status="PENDING_CODE_PROCESSING",
                    assignedAt=assigned_at,
                    recovery={"state": "UNDECIDED", "decidedBy": None, "decidedAt": None, "completedBy": None, "completedAt": None},
                )
                segment_assign(case, candidate, str(body.get("reason") or "ADM负责人分配整单承办人"))
            case.setdefault("assignmentSegments", []).append(
                {"id": uid(), "ownerId": owner_id, "ownerName": owner_name, "assignedAt": assigned_at,
                 "acceptedAt": assigned_at, "endedAt": None, "round": case["round"],
                 "reason": str(body.get("reason") or "ADM负责人分配整单承办人")}
            )
        elif action == "recovery_decide":
            if type(body.get("required")) is not bool:
                raise AdmError("须明确是否需要恢复编码")
            required = body["required"]
            line["recoveryRequired"] = required
            line["recovery"] = {
                "state": "WAITING_MANUAL" if required else "NOT_REQUIRED",
                "decidedBy": actor,
                "decidedAt": now(),
                "completedBy": None,
                "completedAt": None,
            }
            if not required:
                line["status"] = "PENDING_DECISION"
        elif action == "recovery_complete":
            recovery = line.get("recovery") or {}
            if recovery.get("state") != "WAITING_MANUAL":
                raise AdmError("当前没有等待人工完成的编码恢复", 409, "ADM_ACTION_BLOCKED")
            recovery.update(state="MANUALLY_COMPLETED", completedBy=actor, completedAt=now())
            line["status"] = "PENDING_DECISION"
        elif action == "decide":
            decision = str(body.get("decision") or "")
            if decision == "APPEAL":
                if not str(body.get("reason") or "").strip() or not str(body.get("target") or "").strip():
                    raise AdmError("申诉原因和申诉对象必填")
                line.update(appealDecision="REQUIRED", appealReason=str(body["reason"]), status="APPEAL_IN_PROGRESS")
                line["appeals"].append({"id": uid(), "status": "IN_PROGRESS", "reason": str(body["reason"]), "target": str(body["target"]), "actorId": actor, "at": now()})
            elif decision == "NO_APPEAL":
                if not str(body.get("reason") or "").strip():
                    raise AdmError("不申诉原因必填")
                line.update(
                    appealDecision="NOT_REQUIRED",
                    appealReason=str(body["reason"]),
                    processingResult="NO_APPEAL",
                    attribution=validate_attribution(body.get("attribution")),
                    status="PENDING_REVIEW",
                    submittedAt=now(),
                )
            else:
                raise AdmError("处理决定无效")
        elif action == "appeal_result":
            result = str(body.get("result") or "")
            if result not in {"APPEAL_SUCCESS", "APPEAL_FAILED"}:
                raise AdmError("申诉结果无效")
            line["processingResult"] = result
            line["attribution"] = "" if result == "APPEAL_SUCCESS" else validate_attribution(body.get("attribution"))
            line["status"] = "PENDING_REVIEW"
            line["submittedAt"] = now()
            line["appeals"].append({"id": uid(), "status": "SUCCESS" if result == "APPEAL_SUCCESS" else "FAILED", "reason": str(body.get("reason") or ""), "actorId": actor, "at": now()})
        elif action == "resubmit":
            decision, result = str(body.get("decision") or ""), str(body.get("result") or "")
            if decision == "APPEAL":
                reason, target = str(body.get("reason") or "").strip(), str(body.get("target") or "").strip()
                if not reason or not target:
                    raise AdmError("申诉原因和申诉对象必填")
                line.update(appealDecision="REQUIRED", appealReason=reason, processingResult="UNDECIDED", attribution="", status="APPEAL_IN_PROGRESS")
                line["appeals"].append({"id": uid(), "status": "IN_PROGRESS", "reason": reason, "target": target, "actorId": actor, "at": now()})
            elif decision == "NO_APPEAL":
                reason = str(body.get("reason") or "").strip()
                if not reason:
                    raise AdmError("不申诉原因必填")
                line.update(appealDecision="NOT_REQUIRED", appealReason=reason, processingResult="NO_APPEAL", attribution=validate_attribution(body.get("attribution")), status="PENDING_REVIEW", submittedAt=now())
            elif result in {"APPEAL_SUCCESS", "APPEAL_FAILED"}:
                reason, target = str(body.get("reason") or "").strip(), str(body.get("target") or "").strip()
                if not reason or not target:
                    raise AdmError("申诉原因和申诉对象必填")
                line.update(appealDecision="REQUIRED", appealReason=reason, processingResult=result, attribution="" if result == "APPEAL_SUCCESS" else validate_attribution(body.get("attribution")), status="PENDING_REVIEW", submittedAt=now())
                line["appeals"].append({"id": uid(), "status": "SUCCESS" if result == "APPEAL_SUCCESS" else "FAILED", "reason": reason, "target": target, "actorId": actor, "at": now()})
            else:
                blockers = self._submission_blockers(case, line)
                if blockers:
                    raise AdmError("；".join(blockers), 409, "ADM_SUBMIT_BLOCKED")
                line.update(status="PENDING_REVIEW", submittedAt=now())
        elif action in {"approve", "return"}:
            reason = str(body.get("reason") or "")
            if action == "return":
                line.update(status="REJECTED_FOR_REVISION", reviewResult="RETURNED", reviewedBy=actor, reviewedAt=now())
            else:
                requires_collection = body.get("requiresCollection")
                if type(requires_collection) is not bool:
                    raise AdmError("审核通过时须明确是否需要回款")
                expected = money(body.get("collectionExpectedAmount"), False) if requires_collection else None
                if requires_collection and Decimal(expected) <= 0:
                    raise AdmError("应追回金额必须大于0")
                line.update(
                    status="PENDING_COLLECTION" if requires_collection else "COMPLETED",
                    reviewResult="APPROVED",
                    reviewedBy=actor,
                    reviewedAt=now(),
                    collectionExpectedAmount=expected,
                    collectionStatus="PENDING" if requires_collection else "NOT_REQUIRED",
                )
            line["reviews"].append({"action": action, "reason": reason, "actorId": actor, "at": now(), "version": case["version"]})
        elif action == "record_collection":
            amount = money(body.get("amount"), False)
            if Decimal(amount) <= 0:
                raise AdmError("本次回款金额必须大于0")
            if not str(body.get("receivedDate") or "").strip():
                raise AdmError("回款日期必填")
            expected = Decimal(str(line.get("collectionExpectedAmount") or "0"))
            if collection_total(line) + Decimal(amount) > expected:
                raise AdmError("累计回款不能超过应追回金额")
            evidence = []
            if body.get("evidence"):
                evidence = self._evidence(case, line_id, body["evidence"])
            line["collections"].append({
                "id": uid(), "amount": amount, "currency": line["currency"],
                "receivedDate": str(body["receivedDate"]), "note": str(body.get("note") or ""),
                "evidence": evidence, "recordedBy": actor, "recordedAt": now(),
            })
            if collection_total(line) == expected:
                line.update(status="COMPLETED", collectionStatus="COMPLETED")
            else:
                line["collectionStatus"] = "PARTIAL"
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
        evidence_ids = set()
        for line in case["lines"]:
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
            "现有附件仍可读且校验完整",
            evidence_ids <= {item["id"] for item in required_files}
            and all(self._verified_attachment(item) for item in required_files),
        )
        check(
            "IDENTITY",
            "ADM身份及日期截止完整",
            all(case.get(key) for key in ("admNo", "supplierName", "currency", "originalAmount", "issuedDate", "deadline")),
        )
        original, allocated, amounts_match = exact_amounts(case)
        gap = original - allocated if original is not None else None
        check(
            "AMOUNTS",
            "原币金额全部分摊核平",
            amounts_match,
        )
        for line in case["lines"]:
            check(
                "LINE_COMPLETED",
                "明细已完成审核及必要回款",
                line["status"] == "COMPLETED"
                and line.get("reviewResult") == "APPROVED"
                and (
                    line.get("collectionStatus") == "NOT_REQUIRED"
                    or collection_total(line) >= Decimal(str(line.get("collectionExpectedAmount") or "0"))
                ),
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
            require_exact_amounts(case)
            case["status"] = "PENDING_LEADER_ASSIGNMENT"
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
            closed_at = datetime.fromisoformat(case["closedAt"])
            case["attachmentCleanupDueAt"] = (closed_at + timedelta(days=7)).isoformat(timespec="seconds")
            case["attachmentCleanupCancelledAt"] = None
        else:
            if case["status"] != "CLOSED" or not body.get("reason"):
                raise AdmError("重开须为已结案并填写原因", 409)
            if case.get("attachmentCleanupState") == "DELETING":
                raise AdmError("附件清理正在执行，暂不能重开", 409, "ADM_ATTACHMENT_CLEANUP_RUNNING")
            ids = body.get("lineIds") or [line["id"] for line in case["lines"]]
            if (
                not isinstance(ids, list)
                or not ids
                or any(item not in {line["id"] for line in case["lines"]} for item in ids)
            ):
                raise AdmError("重开明细范围无效")
            for line in case["lines"]:
                if line["id"] in ids:
                    line.update(
                        status="PENDING_CODE_PROCESSING" if line.get("ownerId") else (
                            "PENDING_OPERATOR_ASSIGNMENT" if line.get("leaderId") else "PENDING_LEADER_ASSIGNMENT"
                        ),
                        lockedBy=None,
                    )
            case.update(
                status="IN_PROGRESS",
                round=case["round"] + 1,
                closedAt=None,
                closedBy=None,
                attachmentCleanupCancelledAt=now() if case.get("attachmentCleanupState") != "COMPLETED" else None,
                attachmentCleanupDueAt=None,
            )
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
            elif current_line["status"] == "PENDING_COLLECTION":
                permission = "adm.review"
        current = self._read(user, case_id)
        remediation = line_id and current["status"] == "CLOSED" and "upload" in self._line_actions(user, current, self._line(current, line_id))
        case = self._write(user, case_id, body, permission, control_action="remediation" if remediation else "archive_attachment")
        if line_id:
            line = self._line(case, line_id)
            self._line_access(user, case, line)
            if remediation or not (self._full(user, case) and has(user, "adm.edit")):
                if "upload" not in self._line_actions(user, case, line):
                    raise AdmError("当前节点无明细材料上传权限", 403)
                permitted = ["VERIFICATION", "ANALYSIS"] if remediation else upload_categories(user, case, line, self._full(user, case))
                if attachment["category"] not in permitted:
                    raise AdmError("此节点仅允许上传对应审核或回款材料", 403)
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
        if not self._full(user, case) and not file_visible(attachment, {
            line["id"] for line in self._visible_lines(user, case)
        }):
            raise AdmError("无附件下载权限", 403, "ADM_FORBIDDEN")
        return copy.deepcopy(attachment)

    def attachment_preview(self, user, case_id, attachment_id):
        """Allow ledger viewers to inspect bytes online without download authority."""
        case = self._read(user, case_id)
        attachment = next((item for item in case["attachments"] if item["id"] == str(attachment_id)), None)
        if not attachment:
            raise AdmError("附件不存在", 404)
        return copy.deepcopy(attachment)
