"""ADM workflow application service."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import hashlib
import re
import uuid

from .attachments import AdmAttachmentStorage
from .catalog import AdmCatalog
from .domain import MASTER_DEPARTMENTS, appeal_target, business_date, business_datetime, money, normalize_create, normalize_line, text
from .excel import (
    AdmDailyWorkbook, StoredUpload, _diff_label, _operator_actions, _operator_label,
    _operator_stage,
)
from .policy import APPEAL_TARGETS, AdmError, business_now, display_name, has, identity, require
from .repository import AdmWorkflowRepository
from .workflow import difference_query_key


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            _camel(key): (_json_raw_value(item) if key == "source_payload" else _json_value(item))
            for key, item in value.items()
            if key not in {"storage_key"}
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _json_raw_value(value):
    """Serialize archived source JSON without renaming or cleaning its original keys."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_raw_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_raw_value(item) for item in value]
    return value


def _camel(value):
    return re.sub(r"_([a-z0-9])", lambda match: match.group(1).upper(), str(value))


def require_any(user, *permissions):
    if any(has(user, permission) for permission in permissions):
        return
    raise AdmError("当前账号没有执行该ADM操作的功能权限", 403, "ADM_FORBIDDEN")


class AdmWorkflowService:
    def __init__(self, config, repository=None, catalog=None):
        self.config = config
        self.repository = repository or AdmWorkflowRepository(config)
        self.catalog = catalog or AdmCatalog(config)
        self.attachment_storage = AdmAttachmentStorage(config)
        self.daily_workbook = AdmDailyWorkbook(config)

    def import_template(self, user):
        require(user, "adm.create")
        diff_types = self.catalog.options("diffType", "", 200)
        return self.daily_workbook.template([item["name"] for item in diff_types])

    def _normalize_import_group(self, rows):
        first = rows[0]
        issuer_map = {"平台": "PLATFORM", "供应商": "SUPPLIER", "航司": "AIRLINE"}
        issuer_type = issuer_map.get(first["issuerType"].strip(), first["issuerType"].strip().upper())
        issuer_name = first["issuerName"].strip()
        issuer_code = None
        if issuer_type == "PLATFORM":
            issuer = self.catalog.optional_master_value("ota", issuer_name)
            if not issuer:
                raise AdmError("平台类型的下发方名称不能为空")
            issuer_code, issuer_name = issuer["code"], issuer["name"]
        elif issuer_type == "SUPPLIER":
            issuer = self.catalog.optional_master_value("supplier", issuer_name)
            if not issuer:
                raise AdmError("供应商类型的下发方名称不能为空")
            issuer_code, issuer_name = issuer["code"], issuer["name"]
        elif issuer_type != "AIRLINE":
            raise AdmError("下发方类型必须为平台、供应商或航司")
        lines = []
        seen_lines = set()
        for row in rows:
            department = self.catalog.department_value(row["department"])
            leader = self.catalog.user_value(row["leader"], leader=True)
            diff_type = self.catalog.diff_type_value(row["diffType"])
            ota = self.catalog.optional_master_value("ota", row["ota"])
            supplier = self.catalog.optional_master_value("supplier", row["supplier"])
            lines.append({
                "otaCode": ota["code"] if ota else None,
                "otaName": ota["name"] if ota else None,
                "otaOrderNo": row["otaOrderNo"],
                "supplierCode": supplier["code"] if supplier else None,
                "supplierName": supplier["name"] if supplier else None,
                "airlineCode": None,
                "airlineName": row["airline"],
                "ticketNo": row["ticketNo"],
                "pnr": row["pnr"],
                "originalAmount": row["lineAmount"],
                "departmentCode": department["code"],
                "departmentName": department["name"],
                "leaderId": leader["id"],
                "leaderName": leader["name"],
                "diffTypeCode": diff_type["code"],
                "diffTypeName": diff_type["name"],
                "differenceReason": row["differenceReason"],
                "investigationNote": None,
            })
        body = {
            "admNo": first["admNo"], "issuerType": issuer_type,
            "issuerCode": issuer_code, "issuerName": issuer_name,
            "currency": first["currency"], "originalAmount": first["originalAmount"],
            "issuedDate": first["issuedDate"], "replyDeadline": first["replyDeadline"],
            "remark": first["remark"], "lines": lines,
        }
        fx = self.catalog.fx(str(first["currency"] or "").strip().upper())
        normalize_create(body, fx["rateValue"])
        return body

    def _validate_import(self, parsed):
        bodies, errors, summaries = [], [], []
        for group in parsed["groups"]:
            first_row = group[0]["rowNumber"]
            try:
                body = self._normalize_import_group(group)
                bodies.append(body)
                summaries.append({
                    "admNo": body["admNo"], "rowCount": len(group),
                    "firstRow": first_row, "status": "VALID",
                })
            except AdmError as error:
                errors.append({"firstRow": first_row, "rowCount": len(group), "message": error.message})
                summaries.append({
                    "admNo": group[0].get("admNo") or None, "rowCount": len(group),
                    "firstRow": first_row, "status": "INVALID", "message": error.message,
                })
            except (KeyError, TypeError, ValueError):
                message = "数据格式无效，请检查该主单的必填字段和基础资料"
                errors.append({"firstRow": first_row, "rowCount": len(group), "message": message})
                summaries.append({
                    "admNo": group[0].get("admNo") or None, "rowCount": len(group),
                    "firstRow": first_row, "status": "INVALID", "message": message,
                })
        return bodies, errors, summaries

    def preview_import(self, user, upload):
        require(user, "adm.create")
        parsed = self.daily_workbook.parse(upload)
        bodies, errors, summaries = self._validate_import(parsed)
        actor = self._actor(user)
        batch_no = "ADMIMP-" + business_now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        file_name = Path(str(getattr(upload, "filename", "") or "ADM导入.xlsx").replace("\\", "/")).name[:255]
        digest = hashlib.sha256(parsed["content"]).hexdigest()
        failed_rows = sum(item["rowCount"] for item in errors)
        path = self.daily_workbook.save_preview(batch_no, parsed["content"])
        try:
            batch_id = self.repository.create_import_batch(
                batch_no, file_name, digest, actor, total_rows=len(parsed["rows"]),
                failed_rows=failed_rows, errors=errors,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return {
            "batchId": batch_id, "batchNo": batch_no, "templateVersion": "DAILY19_V1",
            "totalRows": len(parsed["rows"]), "validRows": len(parsed["rows"]) - failed_rows,
            "failedRows": failed_rows, "groups": summaries, "canCommit": not errors,
        }

    def commit_import(self, user, batch_no):
        require(user, "adm.create")
        batch = self.repository.get_import_batch(str(batch_no))
        if not batch:
            raise AdmError("ADM导入批次不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and batch["imported_by_id"] != actor["id"]:
            raise AdmError("只能提交自己创建的ADM导入批次", 403, "ADM_FORBIDDEN")
        if batch["status"] == "COMMITTED":
            return {"batchNo": batch["batch_no"], "status": "COMMITTED", "alreadyCommitted": True}
        if batch["status"] == "PREVIEWED" and int(batch["failed_rows"]):
            raise AdmError("预检存在错误，请修正Excel后重新上传", 409, "ADM_IMPORT_INVALID")
        self.repository.claim_import_batch(batch["id"])
        success_rows = 0
        created = []
        try:
            stored = StoredUpload(self.daily_workbook.preview_path(batch["batch_no"]))
            try:
                parsed = self.daily_workbook.parse(stored)
            finally:
                stored.close()
            if hashlib.sha256(parsed["content"]).hexdigest() != batch["file_sha256"]:
                raise AdmError("导入预检文件已变更，请重新上传")
            bodies, errors, _ = self._validate_import(parsed)
            if errors:
                raise AdmError("导入数据重新校验未通过")
            for position, body in enumerate(bodies, 1):
                result = self.create_case(
                    user, body, source_type="EXCEL",
                    idempotency_key=f"admwf-import:{batch['batch_no']}:{position}",
                    import_batch_id=batch["id"],
                )
                success_rows += len(body["lines"])
                created.append({
                    "caseId": result["case"]["id"], "internalNo": result["case"]["internalNo"],
                    "admNo": result["case"]["admNo"], "lineCount": len(result["lines"]),
                })
            self.repository.finish_import_batch(
                batch["id"], status="COMMITTED", success_rows=success_rows, failed_rows=0,
            )
            return {
                "batchNo": batch["batch_no"], "status": "COMMITTED",
                "successRows": success_rows, "cases": created,
            }
        except Exception as error:
            message = error.message if isinstance(error, AdmError) else "ADM导入提交失败"
            self.repository.finish_import_batch(
                batch["id"], status="FAILED", success_rows=success_rows,
                failed_rows=max(0, int(batch["total_rows"]) - success_rows),
                errors=[{"message": message}],
            )
            raise

    @staticmethod
    def _actor(user):
        return {"id": identity(user), "name": display_name(user)}

    def create_case(self, user, body, *, source_type="MANUAL", idempotency_key=None,
                    import_batch_id=None):
        require(user, "adm.create")
        currency = text((body or {}).get("currency"), "主单原币币种", 3).upper()
        fx = self.catalog.fx(currency)
        master_only = source_type == "MANUAL" and (body or {}).get("masterOnly") is True
        data = normalize_create(body, fx["rateValue"], master_only=master_only)
        if master_only:
            data["airlineName"] = text(body.get("airlineName"), "航司", 100)
            department_code = text(body.get("departmentCode"), "归属部门", 64)
            department_name = MASTER_DEPARTMENTS.get(department_code)
            if not department_name:
                raise AdmError("归属部门请选择机票、票务或客服")
            leader = self.catalog.user(body.get("leaderId"), leader=True)
            diff_type = self.catalog.diff_type(text(body.get("diffTypeCode"), "差异类型", 64))
            data["lineDefaults"] = {
                "departmentCode": department_code, "departmentName": department_name,
                "leaderId": leader["id"], "leaderName": leader["name"],
                "diffTypeCode": diff_type["code"], "diffTypeName": diff_type["name"],
                "differenceReason": text(body.get("differenceReason"), "细分差异原因", 1000),
            }
        if not master_only and data["issuerType"] in {"PLATFORM", "SUPPLIER"}:
            issuer_kind = "ota" if data["issuerType"] == "PLATFORM" else "supplier"
            issuer = self.catalog.optional_master(issuer_kind, data["issuerCode"])
            if not issuer:
                raise AdmError("下发方编码不能为空")
            data.update(issuerCode=issuer["code"], issuerName=issuer["name"])
        else:
            data["issuerCode"] = None
        for position, line in enumerate(data["lines"], 1):
            department = self.catalog.department(line["departmentCode"])
            line.update(departmentCode=department["code"], departmentName=department["name"])
            diff_type = self.catalog.diff_type(line["diffTypeCode"])
            line.update(diffTypeCode=diff_type["code"], diffTypeName=diff_type["name"])
            leader = self.catalog.user(line["leaderId"], leader=True)
            line.update(leaderId=leader["id"], leaderName=leader["name"])
            if line["otaCode"]:
                ota = self.catalog.optional_master("ota", line["otaCode"])
                line.update(otaCode=ota["code"], otaName=ota["name"])
            elif line["otaName"]:
                raise AdmError(f"第{position}条明细选择OTA时必须同时提供OTA编码")
            if line["supplierCode"]:
                supplier = self.catalog.optional_master("supplier", line["supplierCode"])
                line.update(supplierCode=supplier["code"], supplierName=supplier["name"])
            elif line["supplierName"]:
                raise AdmError(f"第{position}条明细选择供应商时必须同时提供供应商编码")
        result = self.repository.create_case(
            data, fx, self._actor(user), source_type=source_type, idempotency_key=idempotency_key,
            import_batch_id=import_batch_id,
            case_status="DRAFT" if not master_only and source_type == "MANUAL" and (body or {}).get("saveAsDraft") is True else "ACTIVE",
        )
        return _json_value(result)

    def publish_draft(self, user, case_id):
        actor = self._owner_actor(user, case_id, "发布草稿", "adm.create", "adm.review")
        return _json_value(self.repository.publish_draft(int(case_id), actor))

    def delete_draft(self, user, case_id, body):
        actor = self._owner_actor(user, case_id, "删除草稿", "adm.create", "adm.review")
        return _json_value(self.repository.delete_draft(
            int(case_id), actor, text((body or {}).get("reason"), "草稿删除原因", 1000),
        ))

    def case_detail(self, user, case_id):
        require(user, "adm.view")
        try:
            target = int(case_id)
        except (TypeError, ValueError):
            raise AdmError("ADM主单ID无效", 404, "ADM_NOT_FOUND") from None
        # The recovery worker advances due reminders independently of this read.
        result = self.repository.get_case(target)
        if not result:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        return _json_value(result)

    def case_summary(self, user, case_id):
        require(user, "adm.view")
        try:
            target = int(case_id)
        except (TypeError, ValueError):
            raise AdmError("ADM主单ID无效", 404, "ADM_NOT_FOUND") from None
        result = self.repository.get_case_summary(target)
        if not result:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        return _json_value(result)

    def update_case(self, user, case_id, body):
        actor = self._assigned_owner_actor(
            user, case_id, "编辑主单基础信息", "adm.create", "adm.manage", "adm.review",
        )
        stored = self.repository.get_case(int(case_id))
        case = stored["case"]
        if case["case_status"] not in {"DRAFT", "ACTIVE"}:
            raise AdmError("当前主单状态只允许查看基础信息", 409, "ADM_ACTION_BLOCKED")
        payload = body or {}
        issuer_type = text(payload.get("issuerType"), "下发方类型", 32)
        if issuer_type not in {"SUPPLIER", "PLATFORM", "AIRLINE"}:
            raise AdmError("下发方类型必须为供应商、平台或航司")
        issuer_code = text(payload.get("issuerCode"), "下发方编码", 64, required=False)
        issuer_name = text(payload.get("issuerName"), "下发方名称", 200)
        if case.get("lineDefaults"):
            if issuer_type == "PLATFORM":
                raise AdmError("下发方类型必须为供应商或航司")
            issuer_code = None
        elif issuer_type in {"SUPPLIER", "PLATFORM"}:
            issuer = self.catalog.optional_master("supplier" if issuer_type == "SUPPLIER" else "ota", issuer_code)
            if not issuer:
                raise AdmError("下发方编码不能为空")
            issuer_code, issuer_name = issuer["code"], issuer["name"]
        else:
            issuer_code = None
        data = {
            "admNo": text(payload.get("admNo"), "ADM单号", 100),
            "issuerType": issuer_type,
            "issuerCode": issuer_code,
            "issuerName": issuer_name,
            "issuedDate": business_date(payload.get("issuedDate"), "下发日期"),
            "replyDeadline": business_datetime(payload.get("replyDeadline"), "主单回复截止时间"),
            "remark": text(payload.get("remark"), "主单备注", 1000, required=False),
        }
        return _json_value(self.repository.update_case_basic(int(case_id), data, actor))

    def update_line(self, user, case_id, line_id, body):
        actor = self._assigned_owner_actor(
            user, case_id, "编辑订单基础信息", "adm.create", "adm.manage", "adm.review",
        )
        stored = self.repository.get_case(int(case_id))
        line = next((item for item in stored["lines"] if int(item["id"]) == int(line_id)), None)
        if not line:
            raise AdmError("ADM订单明细不存在", 404, "ADM_NOT_FOUND")
        if line["line_status"] in {"COMPLETED", "HISTORICAL", "VOIDED"}:
            raise AdmError("当前订单状态只允许查看基础信息", 409, "ADM_ACTION_BLOCKED")
        payload = body or {}
        if stored["case"].get("lineDefaults"):
            payload = {
                **payload,
                "departmentCode": line["department_code"], "departmentName": line["department_name"],
                "leaderId": line["leader_id"], "leaderName": line["leader_name"],
                "diffTypeCode": line["diff_type_code"], "diffTypeName": line["diff_type_name"],
                "differenceReason": line["difference_reason"],
            }
        normalized = normalize_line({
            "originalAmount": line["original_amount"],
            "otaCode": payload.get("otaCode"), "otaName": payload.get("otaName"),
            "otaOrderNo": payload.get("otaOrderNo"),
            "supplierCode": payload.get("supplierCode"), "supplierName": payload.get("supplierName"),
            "airlineCode": payload.get("airlineCode"), "airlineName": payload.get("airlineName"),
            "ticketNo": payload.get("ticketNo"), "pnr": payload.get("pnr"),
            "departmentCode": payload.get("departmentCode"), "departmentName": payload.get("departmentName"),
            "leaderId": payload.get("leaderId"), "leaderName": payload.get("leaderName"),
            "diffTypeCode": payload.get("diffTypeCode"), "diffTypeName": payload.get("diffTypeName"),
            "differenceReason": payload.get("differenceReason"),
            "investigationNote": payload.get("investigationNote"),
        }, stored["fxSnapshot"]["rate_value"])
        ota = self.catalog.optional_master("ota", normalized["otaCode"])
        supplier = self.catalog.optional_master("supplier", normalized["supplierCode"])
        department_code = normalized["departmentCode"]
        department = (
            {"code": department_code, "name": MASTER_DEPARTMENTS[department_code]}
            if department_code in MASTER_DEPARTMENTS
            else self.catalog.department(department_code)
        )
        leader = (
            {"id": line["leader_id"], "name": line["leader_name"]}
            if normalized["leaderId"] == line["leader_id"]
            else self.catalog.user(normalized["leaderId"], leader=True)
        )
        diff_type = self.catalog.diff_type(normalized["diffTypeCode"])
        normalized.update(
            otaCode=ota["code"] if ota else None, otaName=ota["name"] if ota else None,
            supplierCode=supplier["code"] if supplier else None,
            supplierName=supplier["name"] if supplier else None,
            departmentCode=department["code"], departmentName=department["name"],
            leaderId=leader["id"], leaderName=leader["name"],
            diffTypeCode=diff_type["code"], diffTypeName=diff_type["name"],
        )
        if stored["case"].get("master_recovery_status"):
            normalized.update(
                supplierCode=line.get("supplier_code"), supplierName=line.get("supplier_name"),
                airlineCode=line.get("airline_code"), airlineName=line.get("airline_name"),
            )
        return _json_value(self.repository.update_line_basic(int(case_id), int(line_id), normalized, actor))

    def master_leader_transfer(self, user, case_id, body):
        require_any(user, "adm.assign_operator", "adm.assign")
        body = body or {}
        accepted = body.get("accepted")
        if accepted is not None and type(accepted) is not bool:
            raise AdmError("转派确认结果无效")
        target = None if accepted is not None else self.catalog.user(body.get("targetUserId"), leader=True)
        reason = text(body.get("reason"), "转派或拒绝原因", 1000, required=accepted is not True)
        return _json_value(self.repository.master_leader_transfer(
            int(case_id), self._actor(user), target=target, reason=reason, accepted=accepted,
        ))

    def master_recovery(self, user, case_id, body):
        action = (body or {}).get("action")
        if action not in {"skip", "request", "start"}:
            raise AdmError("恢复编码操作无效")
        if action == "start":
            require_any(user, "adm.create", "adm.manage", "adm.review")
        else:
            require_any(user, "adm.assign_operator", "adm.assign")
        actor = self._actor(user)
        locators = None
        line = None
        if action == "request":
            raw = text(body.get("locators"), "GDS-PCC-PNR", 2000)
            entries = [item.strip().upper() for item in raw.replace("，", ",").split(",")]
            if not all(re.fullmatch(r"[A-Z0-9]{2}-[A-Z0-9]{3,8}-[A-Z0-9]{5,8}", item) for item in entries):
                raise AdmError("请按 GDS-PCC-PNR 格式填写，多条用逗号分隔，例如 1G-5S75-13124N")
            locators = ",".join(entries)
        if action == "skip":
            stored = self.repository.get_case(int(case_id))
            if not stored or not stored["case"].get("lineDefaults") or not stored.get("fxSnapshot"):
                raise AdmError("主单资料或冻结汇率不存在")
            case = stored["case"]
            line = normalize_line({**case["lineDefaults"], "originalAmount": case["original_amount"]},
                                  stored["fxSnapshot"]["rate_value"])
        return _json_value(self.repository.master_recovery(int(case_id), action, actor, locators=locators, line=line))

    def add_line(self, user, case_id, body):
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        case = stored["case"]
        if case.get("master_recovery_status") == "RECOVERED":
            require_any(user, "adm.assign_operator", "adm.assign")
            actor = self._actor(user)
            if actor["id"] != case["lineDefaults"]["leaderId"]:
                raise AdmError("只有该主单的负责组长可以补录订单", 403, "ADM_FORBIDDEN")
        else:
            actor = self._owner_actor(user, case_id, "新增订单", "adm.create", "adm.manage")
        fx = stored.get("fxSnapshot")
        if not fx:
            raise AdmError("主单冻结汇率不存在", 500, "ADM_REFERENCE_INVALID")
        raw_line = (body or {}).get("line")
        defaults = stored["case"].get("lineDefaults")
        if defaults and isinstance(raw_line, dict):
            selected_leader = raw_line.get("leaderId") if case.get("master_recovery_status") == "RECOVERED" else None
            raw_line = {**raw_line, **defaults}
            if selected_leader:
                raw_line["leaderId"] = selected_leader
        line = normalize_line(raw_line, fx["rate_value"])
        if line["originalAmount"] <= 0:
            raise AdmError("新增订单金额必须大于0")
        if not defaults:
            department = self.catalog.department(line["departmentCode"])
            line.update(departmentCode=department["code"], departmentName=department["name"])
            diff_type = self.catalog.diff_type(line["diffTypeCode"])
            line.update(diffTypeCode=diff_type["code"], diffTypeName=diff_type["name"])
        leader = self.catalog.user(line["leaderId"], leader=True)
        line.update(leaderId=leader["id"], leaderName=leader["name"])
        if line["otaCode"]:
            ota = self.catalog.optional_master("ota", line["otaCode"])
            line.update(otaCode=ota["code"], otaName=ota["name"])
        elif line["otaName"]:
            raise AdmError("选择OTA时必须同时提供OTA编码")
        if line["supplierCode"]:
            supplier = self.catalog.optional_master("supplier", line["supplierCode"])
            line.update(supplierCode=supplier["code"], supplierName=supplier["name"])
        elif line["supplierName"]:
            raise AdmError("选择供应商时必须同时提供供应商编码")
        raw_amounts = (body or {}).get("existingAmounts")
        if not isinstance(raw_amounts, list):
            raise AdmError("请提交全部现有有效明细的调整后金额")
        amounts = {}
        for item in raw_amounts:
            try:
                line_id = int(item.get("lineId"))
            except (AttributeError, TypeError, ValueError):
                raise AdmError("现有明细ID无效") from None
            if line_id in amounts:
                raise AdmError("现有明细ID重复")
            amounts[line_id] = money(item.get("originalAmount"), "调整后明细金额")
            if amounts[line_id] <= 0:
                raise AdmError("调整后每条有效明细金额必须大于0")
        reason = text((body or {}).get("reason"), "新增订单及金额调整说明", 1000, required=not defaults or bool(amounts))
        return _json_value(self.repository.add_line(int(case_id), line, amounts, actor, reason or "首次录入订单明细"))

    def config_payload(self, user):
        require(user, "adm.view")
        provider = self.config.get("ADM_WORKFLOW_USER_OPTIONS")
        people = provider() if callable(provider) else {"handle": [], "leader": [], "coordinate": []}
        may_select = {
            "leader": any(has(user, permission) for permission in ("adm.create", "adm.manage", "adm.review", "adm.assign_leader")),
            "handle": any(has(user, permission) for permission in ("adm.assign_operator", "adm.assign")),
        }
        people = {**people, **{
            role: [item for item in people.get(role, []) if allowed or not item.get("disabled")]
            for role, allowed in may_select.items()
        }}
        return _json_value({
            "caseStatuses": ["DRAFT", "ACTIVE", "CLOSED", "HISTORICAL", "VOIDED", "DELETED"],
            "sourceTypes": ["MANUAL", "EXCEL", "LEGACY", "TEST"],
            "lineStatuses": [
                "PENDING_LEADER", "PENDING_OPERATOR", "PENDING_ACCEPT", "PROCESSING",
                "PENDING_REVIEW", "WAITING_DIFF", "WAITING_COLLECTION", "COMPLETED",
                "HISTORICAL", "VOIDED",
            ],
            "issuerTypes": ["PLATFORM", "SUPPLIER", "AIRLINE"],
            "appealTargets": [{"value": code, "label": name} for code, name in APPEAL_TARGETS.items()],
            "appealResults": ["SUCCEEDED", "FAILED"],
            "problemAttributions": ["HUMAN", "PLATFORM", "SYSTEM"],
            "attachmentCategories": ["ADM_ORIGINAL", "APPEAL", "COLLECTION", "OTHER"],
            "people": people,
            "permissions": {
                "view": has(user, "adm.view"), "create": has(user, "adm.create"),
                "assignLeader": has(user, "adm.assign_leader") or has(user, "adm.review"),
                "assignOperator": has(user, "adm.assign_operator") or has(user, "adm.assign"),
                "assign": has(user, "adm.assign_operator") or has(user, "adm.assign"),
                "handle": has(user, "adm.handle"), "review": has(user, "adm.review"),
                "diffMatch": has(user, "adm.diff_match") or has(user, "adm.review"),
                "collection": has(user, "adm.collection") or has(user, "adm.review"),
                "close": has(user, "adm.close") or has(user, "adm.review"),
                "manage": has(user, "adm.manage") or has(user, "adm.review"),
            },
        })

    def reference_options(self, user, kind, query):
        require(user, "adm.view")
        try:
            limit = int(query.get("limit", 100))
        except (TypeError, ValueError):
            raise AdmError("基础资料数量参数无效") from None
        return _json_value(self.catalog.options(kind, query.get("search"), limit))

    def exchange_rate(self, user, currency):
        require(user, "adm.view")
        code = text(currency, "币种", 3).upper()
        return _json_value(self.catalog.fx(code))

    @staticmethod
    def _page_params(query):
        try:
            page = max(1, int(query.get("page", 1)))
            page_size = min(100, max(1, int(query.get("pageSize", 20))))
        except (TypeError, ValueError):
            raise AdmError("分页参数无效") from None
        return page, page_size

    @staticmethod
    def _ledger_query(query, default_metric):
        page, page_size = AdmWorkflowService._page_params(query)
        metric = str(query.get("metric") or default_metric)
        if metric not in {default_metric, "pending", "open", "soon", "late"}:
            raise AdmError("台账指标参数无效")
        filters = {
            "status": str(query.get("status") or "").strip() or None,
            "search": str(query.get("search") or "").strip() or None,
            "activeOnly": str(query.get("activeOnly") or "").lower() == "true",
            "metric": metric,
            "sourceType": str(query.get("sourceType") or "").strip().upper() or None,
        }
        if filters["sourceType"] not in {None, "MANUAL", "EXCEL", "LEGACY", "TEST"}:
            raise AdmError("数据来源筛选无效")
        return filters, page, page_size

    def list_cases(self, user, query):
        require(user, "adm.view")
        filters, page, page_size = self._ledger_query(query, "range")
        return _json_value(self.repository.list_cases(filters, page, page_size))

    def list_ledger_lines(self, user, query):
        require(user, "adm.view")
        filters, page, page_size = self._ledger_query(query, "all")
        return _json_value(self.repository.list_ledger_lines(filters, page, page_size))

    @staticmethod
    def _workbench_capabilities(user):
        return {
            "assignLeader": has(user, "adm.assign_leader") or has(user, "adm.review"),
            "assignOperator": has(user, "adm.assign_operator") or has(user, "adm.assign"),
            "handle": has(user, "adm.handle"),
            "review": has(user, "adm.review"),
            "diffMatch": has(user, "adm.diff_match") or has(user, "adm.review"),
            "collection": has(user, "adm.collection") or has(user, "adm.review"),
            "close": has(user, "adm.close") or has(user, "adm.review"),
        }
    def workbench(self, user):
        require(user, "adm.view")
        # The recovery worker advances due reminders independently of this read.
        capabilities = self._workbench_capabilities(user)
        actor = self._actor(user)
        result = self.repository.list_workbench(actor["id"], capabilities, is_admin=bool(user.get("is_admin")))
        master_tasks = getattr(self.repository, "list_master_workbench", None)
        if master_tasks:
            capabilities["masterRecovery"] = any(has(user, code) for code in ("adm.create", "adm.manage", "adm.review"))
            items = master_tasks(actor["id"], capabilities)
            result["items"].extend(items)
            result["summary"]["total"] += len(items)
        return _json_value(result)

    def workbench_queue(self, user, query):
        require(user, "adm.view")
        queue = str(query.get("queue") or "")
        if queue not in {"close", "transfer"}:
            raise AdmError("工作台清单类型无效")
        status = str(query.get("status") or "pending")
        if status not in {"pending", "all"}:
            raise AdmError("转派筛选无效")
        page, page_size = self._page_params(query)
        return _json_value(self.repository.list_workbench_queue(
            self._actor(user)["id"], self._workbench_capabilities(user), queue, page, page_size,
            pending_only=status == "pending",
        ))

    def assign_operator(self, user, case_id, line_id, body):
        require_any(user, "adm.assign_operator", "adm.assign")
        result = self.repository.get_case(int(case_id))
        if not result:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        line = next((item for item in result["lines"] if item["id"] == int(line_id)), None)
        if not line:
            raise AdmError("ADM明细不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and line["leader_id"] != actor["id"]:
            raise AdmError("组长只能分配自己负责的明细", 403, "ADM_FORBIDDEN")
        operator = self.catalog.user((body or {}).get("operatorId"), leader=False)
        saved = self.repository.assign_operator(
            int(case_id), int(line_id), operator, actor,
            reason=text((body or {}).get("reason"), "分配说明", 1000, required=False),
        )
        return _json_value(saved)

    def change_leader(self, user, case_id, line_id, body):
        actor = self._assigned_owner_actor(
            user, case_id, "更换组长", "adm.assign_leader", "adm.review",
        )
        leader = self.catalog.user((body or {}).get("leaderId"), leader=True)
        return _json_value(self.repository.change_leader(
            int(case_id), int(line_id), leader, actor,
            text((body or {}).get("reason"), "更换组长原因", 1000),
        ))

    def request_transfer(self, user, case_id, line_id, body):
        body = body or {}
        role = body.get("targetRole") or "OPERATOR"
        if role == "LEADER":
            require_any(user, "adm.assign_operator", "adm.assign")
        elif role == "OPERATOR":
            require_any(user, "adm.assign_operator", "adm.assign", "adm.handle")
        else:
            raise AdmError("转派岗位无效")
        target = self.catalog.user(body.get("targetUserId") or body.get("operatorId"), leader=role == "LEADER")
        return _json_value(self.repository.request_transfer(
            int(case_id), int(line_id), target, self._actor(user),
            text(body.get("reason"), "转派原因", 1000),
            text(body.get("handoverNote"), "交接说明", 2000), target_role=role,
            can_lead=has(user, "adm.assign_operator") or has(user, "adm.assign"), can_handle=has(user, "adm.handle"),
        ))

    def decide_transfer(self, user, case_id, line_id, transfer_id, decision, body):
        require_any(user, "adm.handle", "adm.assign_operator", "adm.assign")
        allowed_roles = []
        if has(user, "adm.handle"):
            allowed_roles.append("OPERATOR")
        if has(user, "adm.assign_operator") or has(user, "adm.assign"):
            allowed_roles.append("LEADER")
        return _json_value(self.repository.decide_transfer(
            int(case_id), int(line_id), int(transfer_id), self._actor(user), decision,
            text((body or {}).get("reason"), "拒绝原因", 1000, required=False), allowed_roles=allowed_roles,
        ))

    def accept_line(self, user, case_id, line_id, *, source="WEB"):
        require(user, "adm.handle")
        if source not in {"WEB", "EXCEL"}:
            raise AdmError("接单来源无效")
        return _json_value(self.repository.accept_line(int(case_id), int(line_id), self._actor(user), source=source))

    def update_investigation_note(self, user, case_id, line_id, body):
        require(user, "adm.handle")
        note = text((body or {}).get("investigationNote"), "订单情况说明", 10000)
        return _json_value(self.repository.update_investigation_note(
            int(case_id), int(line_id), self._actor(user), note,
        ))

    def claim_and_export(self, user, body):
        require(user, "adm.handle")
        raw_ids = (body or {}).get("lineIds")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise AdmError("请选择要接单并导出的ADM明细")
        if len(raw_ids) > 1000:
            raise AdmError("单次最多导出1000条ADM明细")
        try:
            line_ids = [int(value) for value in raw_ids]
        except (TypeError, ValueError):
            raise AdmError("ADM明细ID无效") from None
        if any(value <= 0 for value in line_ids):
            raise AdmError("ADM明细ID无效")
        return self.repository.claim_for_export(
            line_ids, self._actor(user), self.daily_workbook.operator_export,
        )

    def import_operator_results(self, user, upload, *, dry_run=False):
        require(user, "adm.handle")
        rows = self.daily_workbook.parse_operator_results(upload)
        actor = self._actor(user)
        contexts = self.repository.operator_import_context([row["lineInternalNo"] for row in rows])
        attribution_map = {"人为问题": "HUMAN", "平台问题": "PLATFORM", "系统问题": "SYSTEM",
                           "HUMAN": "HUMAN", "PLATFORM": "PLATFORM", "SYSTEM": "SYSTEM"}
        decision_map = {"需要恢复编码": "NEEDED", "无需恢复编码": "NOT_NEEDED",
                        "NEEDED": "NEEDED", "NOT_NEEDED": "NOT_NEEDED"}
        prepared = []
        preview_rows = []
        seen_lines = set()

        for row in rows:
            line = contexts.get(row["lineInternalNo"])
            prefix = f"第{row['rowNumber']}行"
            row_errors = []
            if row["lineInternalNo"] in seen_lines:
                row_errors.append("文件内重复订单")
            seen_lines.add(row["lineInternalNo"])
            if not line:
                row_errors.append("内部明细编号不存在")
                preview_rows.append({"rowNumber": row["rowNumber"], "lineInternalNo": row["lineInternalNo"],
                                     "action": row["action"], "status": "错误", "reason": "；".join(row_errors)})
                continue
            if line["case_status"] != "ACTIVE":
                row_errors.append("所属主单不是处理中状态")
            if int(line["operator_id"] or 0) != int(actor["id"]):
                row_errors.append("当前操作员与登录账号不一致")
            if int(line["version_no"]) != int(row["versionNo"]):
                row_errors.append("数据版本已变化，请重新导出")
            if line["case_internal_no"] != row["caseInternalNo"] or line["adm_no"] != row["admNo"]:
                row_errors.append("主单编号与系统记录不一致")
            if row["operatorName"] != str(line.get("operator_name") or ""):
                row_errors.append("操作人员字段已被修改")
            reminder_transition = (
                str(line.get("recovery_status") or "") == "REMINDER_DUE"
                and row["lineStatus"] == "等待恢复编码"
                and row["recoveryStatus"] == str(_operator_label("WAITING"))
            )
            if row["lineStatus"] != _operator_stage(line) and not reminder_transition:
                row_errors.append("原状态已变化，请重新导出")
            if row["attachmentAddress"] != str(line.get("attachment_address") or ""):
                row_errors.append("附件地址为只读字段，不允许修改")
            def date_cell(value):
                if value is None:
                    return ""
                if isinstance(value, datetime):
                    return value.replace(microsecond=0).isoformat(sep=" ")
                return str(value)

            readonly_text = {
                "业务归属部门": (row["departmentName"], str(line.get("department_name") or "")),
                "负责组长": (row["leaderName"], str(line.get("leader_name") or "")),
                "处理截止时间": (row["processDeadline"], date_cell(line.get("process_deadline"))),
                "下发方类型": (row["issuerType"], str(_operator_label(line.get("issuer_type")) or "")),
                "下发方名称": (row["issuerName"], str(line.get("issuer_name") or "")),
                "原币币种": (row["currency"], str(line.get("currency") or "")),
                "恢复编码发起时间": (row["recoveryStartedAt"], date_cell(line.get("recovery_started_at"))),
                "恢复编码当前状态": (row["recoveryStatus"], str(_operator_label(line.get("recovery_status")) or "")),
                "差异订单匹配状态": (row["diffMatchStatus"], str(_diff_label(line.get("diff_match_status"), line) or "")),
            }
            for field, (actual, expected) in readonly_text.items():
                if reminder_transition and field == "恢复编码当前状态":
                    continue
                if actual != expected:
                    row_errors.append(f"{field}为只读字段，不允许修改")
            readonly_amounts = {
                "本笔订单ADM金额（原币）": (row["originalAmount"], line.get("original_amount")),
                "本笔订单ADM金额（人民币）": (row["cnyAmount"], line.get("cny_amount")),
                "ADM主单原币总金额": (row["caseOriginalAmount"], line.get("case_original_amount")),
                "ADM主单人民币总金额": (row["caseCnyAmount"], line.get("case_cny_amount")),
            }
            for field, (actual, expected) in readonly_amounts.items():
                try:
                    unchanged = Decimal(str(actual or "0")) == Decimal(str(expected or "0"))
                except Exception:
                    unchanged = False
                if not unchanged:
                    row_errors.append(f"{field}为只读字段，不允许修改")
            action = row["action"]
            allowed_actions = set(_operator_actions(line))
            if action and action not in allowed_actions:
                row_errors.append(f"当前状态不允许执行“{action}”，请重新导出Excel")
            attribution = attribution_map.get(row["problemAttribution"].strip().upper())
            decision = decision_map.get(row["recoveryDecision"].strip().upper())
            try:
                ota = self.catalog.optional_master_value("ota", row["ota"])
                supplier = self.catalog.optional_master_value("supplier", row["supplier"])
            except AdmError as error:
                row_errors.append(error.message)
                preview_rows.append({"rowNumber": row["rowNumber"], "lineInternalNo": row["lineInternalNo"],
                                     "action": action, "status": "错误", "reason": "；".join(row_errors)})
                continue
            supplement = {
                "otaCode": ota["code"] if ota else None,
                "otaName": ota["name"] if ota else None,
                "otaOrderNo": text(row["otaOrderNo"], "OTA订单号", 200, required=False),
                "supplierCode": supplier["code"] if supplier else None,
                "supplierName": supplier["name"] if supplier else None,
                "airlineCode": line.get("airline_code") if row["airline"] == str(line.get("airline_name") or "") else None,
                "airlineName": text(row["airline"], "航司", 200, required=False),
                "ticketNo": text(row["ticketNo"], "票号", 200, required=False),
                "pnr": text(row["pnr"], "PNR编码", 100, required=False),
                "investigationNote": text(row["investigationNote"], "补充问题说明", 10000, required=False),
            }
            supplement_columns = {
                "otaCode": "ota_code", "otaName": "ota_name", "otaOrderNo": "ota_order_no",
                "supplierCode": "supplier_code", "supplierName": "supplier_name",
                "airlineCode": "airline_code", "airlineName": "airline_name",
                "ticketNo": "ticket_no", "pnr": "pnr", "investigationNote": "investigation_note",
            }
            supplement_changed = any(
                supplement[key] != line.get(column) for key, column in supplement_columns.items()
            )
            recovery = str(line.get("recovery_status") or "UNDECIDED")
            expected_decision = ("需要恢复编码" if recovery in {"WAITING", "REMINDER_DUE", "CONFIRMED"}
                                 else "无需恢复编码" if recovery == "NOT_REQUIRED" else "")
            decision_changed = row["recoveryDecision"] != expected_decision
            expected_confirmation = "已查看并处理" if recovery == "CONFIRMED" else ""
            confirmation_changed = row["recoveryConfirmation"] != expected_confirmation
            if line["line_status"] != "PROCESSING":
                row_errors.append("当前明细不在办理中，不能导入操作员处理结果")
            if decision_changed and recovery != "UNDECIDED":
                row_errors.append("当前阶段不允许修改恢复编码决定")
            if decision_changed and not decision:
                row_errors.append("恢复编码决定必须为需要恢复编码或无需恢复编码")
            if confirmation_changed and row["recoveryConfirmation"] != "已查看并处理":
                row_errors.append("恢复编码处理确认值无效")
            if confirmation_changed and recovery not in {"WAITING", "REMINDER_DUE"}:
                row_errors.append("当前阶段不允许确认恢复编码已处理")
            if supplement_changed and action in {"", "暂不处理"}:
                action = "仅补充订单资料"
                row["action"] = action
            elif action == "仅补充订单资料" and not supplement_changed:
                action = ""
                row["action"] = ""
            projected_recovery = ("WAITING" if decision == "NEEDED" else "NOT_REQUIRED") if decision_changed else recovery
            if confirmation_changed:
                projected_recovery = "CONFIRMED"
            final_actions = {"提交申诉", "申诉成功", "申诉失败", "不申诉"}
            implicit_confirmation = action in final_actions and projected_recovery in {"WAITING", "REMINDER_DUE"}
            if implicit_confirmation:
                projected_recovery = "CONFIRMED"
            if action in final_actions and projected_recovery not in {"NOT_REQUIRED", "CONFIRMED"}:
                row_errors.append("请先完成恢复编码决定及查看确认")
            if action in {"提交申诉", "申诉成功", "申诉失败"} and not row["appealReason"].strip():
                row_errors.append("申诉原因必填")
            if action in {"提交申诉", "申诉成功", "申诉失败"}:
                target = row["appealTarget"].strip()
                historical_target = str(line.get("latest_appeal_target") or "").strip()
                # An existing appeal can be completed using its original target text.
                if not (line.get("appeal_status") == "IN_PROGRESS" and target and target == historical_target):
                    try:
                        row["appealTarget"] = appeal_target(target)
                    except AdmError as error:
                        row_errors.append(error.message)
            if action == "不申诉" and not row["noAppealReason"].strip():
                row_errors.append("不申诉原因必填")
            if action in {"申诉失败", "不申诉"} and not attribution:
                row_errors.append("问题归因必填")
            has_change = supplement_changed or decision_changed or confirmation_changed or action not in {"", "暂不处理"}
            status = "错误" if row_errors else "可提交" if has_change else "跳过"
            reason = "；".join(row_errors) or ("校验通过" if status == "可提交" else "本行未填写处理动作，资料和状态保持原值")
            preview_rows.append({"rowNumber": row["rowNumber"], "lineInternalNo": row["lineInternalNo"],
                                 "action": action or row["recoveryConfirmation"] or row["recoveryDecision"],
                                 "status": status, "reason": reason})
            if status == "可提交":
                prepared.append((row, line, decision, attribution, supplement, supplement_changed,
                                 decision_changed, confirmation_changed))
        failed = sum(item["status"] == "错误" for item in preview_rows)
        skipped = sum(item["status"] == "跳过" for item in preview_rows)
        if dry_run:
            return {"canCommit": bool(prepared) and not failed, "totalRows": len(preview_rows),
                    "validRows": len(prepared), "skippedRows": skipped, "failedRows": failed,
                    "rows": preview_rows}
        if failed:
            messages = [f"第{item['rowNumber']}行：{item['reason']}" for item in preview_rows if item["status"] == "错误"]
            raise AdmError("；".join(messages[:20]), 409, "ADM_OPERATOR_IMPORT_INVALID")
        results = []
        for row, line, decision, attribution, supplement, supplement_changed, decision_changed, confirmation_changed in prepared:
            case_id, line_id = int(line["case_id"]), int(line["id"])
            if supplement_changed:
                self.repository.update_operator_supplement(case_id, line_id, actor, supplement)
            action = row["action"]
            if decision_changed:
                self.repository.decide_recovery(case_id, line_id, decision, actor,
                                                reason=row["investigationNote"].strip() or None)
            implicit_confirmation = action in {"提交申诉", "申诉成功", "申诉失败", "不申诉"} and (
                (decision_changed and decision == "NEEDED")
                or str(line.get("recovery_status") or "") in {"WAITING", "REMINDER_DUE"}
            )
            if confirmation_changed or implicit_confirmation:
                self.repository.confirm_recovery(case_id, line_id, actor)
            appeal_status = str(line.get("appeal_status") or "UNDECIDED")
            target_status = {"申诉成功": "SUCCEEDED", "申诉失败": "FAILED"}.get(action)
            appeal_actions = {"提交申诉", "申诉成功", "申诉失败"}
            if action in appeal_actions and appeal_status == "IN_PROGRESS" and (
                row["appealReason"].strip() != str(line.get("latest_appeal_reason") or "")
                or row["appealTarget"].strip() != str(line.get("latest_appeal_target") or "")
            ):
                self.repository.update_active_appeal(
                    case_id, line_id, actor, row["appealReason"].strip(), row["appealTarget"].strip(),
                )
            if (action in appeal_actions
                    and appeal_status != "IN_PROGRESS" and appeal_status != target_status):
                self.repository.start_appeal(case_id, line_id, actor, row["appealReason"].strip(),
                                             row["appealTarget"].strip())
                appeal_status = "IN_PROGRESS"
            if action == "申诉成功" and appeal_status != "SUCCEEDED":
                self.repository.finish_appeal(case_id, line_id, actor, "SUCCEEDED", note=row["resultNote"].strip() or None)
            if action == "申诉成功":
                self.repository.submit_review(case_id, line_id, actor)
            elif action == "申诉失败" and appeal_status != "FAILED":
                self.repository.finish_appeal(case_id, line_id, actor, "FAILED", attribution,
                                              row["resultNote"].strip() or None)
            if action == "申诉失败":
                self.repository.submit_review(case_id, line_id, actor)
            elif action == "不申诉":
                if appeal_status != "NO_APPEAL":
                    self.repository.record_no_appeal(case_id, line_id, actor, row["noAppealReason"].strip(), attribution)
                self.repository.submit_review(case_id, line_id, actor)
            elif action == "重新提交负责人审核":
                self.repository.submit_review(case_id, line_id, actor)
            results.append({"rowNumber": row["rowNumber"], "lineInternalNo": row["lineInternalNo"],
                            "action": action or row["recoveryConfirmation"] or row["recoveryDecision"],
                            "status": "已提交"})
        return {"committed": len(results), "skipped": skipped, "rows": results}

    def decide_recovery(self, user, case_id, line_id, body):
        require(user, "adm.handle")
        decision = str((body or {}).get("decision") or "").strip().upper()
        reason = text((body or {}).get("reason"), "无需恢复原因", 1000, required=False)
        return _json_value(self.repository.decide_recovery(
            int(case_id), int(line_id), decision, self._actor(user), reason=reason,
            allow_override=bool(user.get("is_admin")),
        ))

    def confirm_recovery(self, user, case_id, line_id):
        require(user, "adm.handle")
        return _json_value(self.repository.confirm_recovery(
            int(case_id), int(line_id), self._actor(user), allow_override=bool(user.get("is_admin")),
        ))

    def start_appeal(self, user, case_id, line_id, body):
        require(user, "adm.handle")
        reason = text((body or {}).get("appealReason"), "申诉原因", 1000)
        target = appeal_target((body or {}).get("appealTarget"))
        return _json_value(self.repository.start_appeal(
            int(case_id), int(line_id), self._actor(user), reason, target,
            allow_override=bool(user.get("is_admin")),
        ))

    def finish_appeal(self, user, case_id, line_id, body):
        require(user, "adm.handle")
        result = str((body or {}).get("result") or "").strip().upper()
        attribution = str((body or {}).get("problemAttribution") or "").strip().upper() or None
        note = text((body or {}).get("resultNote"), "申诉结果说明", 2000, required=False)
        return _json_value(self.repository.finish_appeal(
            int(case_id), int(line_id), self._actor(user), result, attribution, note,
            allow_override=bool(user.get("is_admin")),
        ))

    def record_no_appeal(self, user, case_id, line_id, body):
        require(user, "adm.handle")
        reason = text((body or {}).get("reason"), "不申诉原因", 1000)
        attribution = str((body or {}).get("problemAttribution") or "").strip().upper()
        return _json_value(self.repository.record_no_appeal(
            int(case_id), int(line_id), self._actor(user), reason, attribution,
            allow_override=bool(user.get("is_admin")),
        ))

    def submit_review(self, user, case_id, line_id):
        require(user, "adm.handle")
        return _json_value(self.repository.submit_review(
            int(case_id), int(line_id), self._actor(user), allow_override=bool(user.get("is_admin")),
        ))

    def decide_review(self, user, case_id, line_id, body):
        require(user, "adm.review")
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError("只有该主单ADM负责人可以审核", 403, "ADM_FORBIDDEN")
        result = str((body or {}).get("result") or "").strip().upper()
        return_type = str((body or {}).get("returnType") or "").strip().upper() or None
        required_value = (body or {}).get("collectionRequired")
        if required_value is not True and required_value is not False and required_value is not None:
            raise AdmError("是否需要回款必须为布尔值")
        appeal_status = next(
            (str(item.get("appeal_status") or "") for item in stored.get("lines", [])
             if int(item.get("id") or 0) == int(line_id)),
            "",
        )
        if result == "APPROVED" and appeal_status == "SUCCEEDED" and required_value is None:
            raise AdmError("申诉成功审核通过时必须确认是否需要回款")
        if result == "APPROVED" and appeal_status in {"FAILED", "NO_APPEAL"}:
            if required_value is True:
                raise AdmError("申诉失败或不申诉不进入回款流程，应先完成差异订单匹配")
            required_value = False
        expected = None
        if result == "APPROVED" and appeal_status == "SUCCEEDED" and required_value is True:
            expected = money((body or {}).get("expectedCollectionAmount"), "应回款金额")
            if expected <= 0:
                raise AdmError("需要回款时应回款金额必须大于0")
        return _json_value(self.repository.decide_review(
            int(case_id), int(line_id), actor, result,
            comment=text((body or {}).get("comment"), "审核说明", 2000, required=False),
            return_reason=text((body or {}).get("returnReason"), "退回原因", 2000, required=False),
            return_type=return_type,
            collection_required=required_value, expected_amount=expected,
            collection_note=text((body or {}).get("collectionNote"), "回款判断说明", 1000, required=False),
        ))

    def withdraw_review(self, user, case_id, line_id, body):
        actor = self._owner_actor(user, case_id, "撤回审核", "adm.manage", "adm.review")
        return _json_value(self.repository.withdraw_review(
            int(case_id), int(line_id), actor,
            text((body or {}).get("reason"), "审核撤回原因", 1000),
        ))

    def check_difference_order(self, user, case_id, line_id):
        require_any(user, "adm.diff_match", "adm.review")
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError("只有该主单ADM负责人可以核验差异单", 403, "ADM_FORBIDDEN")
        line = next((item for item in stored["lines"] if item["id"] == int(line_id)), None)
        if not line:
            raise AdmError("ADM明细不存在", 404, "ADM_NOT_FOUND")
        query = difference_query_key(
            source_type=stored["case"]["source_type"], ota_order_no=line["ota_order_no"],
            adm_no=stored["case"]["adm_no"], line_internal_no=line["line_internal_no"],
        )
        match = self.catalog.difference_match(query)
        return _json_value(self.repository.record_difference_check(
            int(case_id), int(line_id), actor, match,
        ))

    def record_collection(self, user, case_id, line_id, body):
        require_any(user, "adm.collection", "adm.review")
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError("只有该主单ADM负责人可以登记回款", 403, "ADM_FORBIDDEN")
        voucher_no = text((body or {}).get("voucherNo"), "凭证号", 200, required=False)
        raw_attachment_ids = (body or {}).get("attachmentIds") or []
        if not isinstance(raw_attachment_ids, list):
            raise AdmError("回款凭证附件格式无效")
        try:
            attachment_ids = list(dict.fromkeys(int(value) for value in raw_attachment_ids))
        except (TypeError, ValueError):
            raise AdmError("回款凭证附件无效") from None
        if any(value <= 0 for value in attachment_ids):
            raise AdmError("回款凭证附件无效")
        if not voucher_no and not attachment_ids:
            raise AdmError("每次回款必须填写凭证号或上传凭证附件")
        amount = money((body or {}).get("amount"), "回款金额")
        if amount <= 0:
            raise AdmError("回款金额必须大于0")
        return _json_value(self.repository.record_collection(
            int(case_id), int(line_id), actor, amount=amount,
            received_date=business_date((body or {}).get("receivedDate"), "回款日期"),
            voucher_no=voucher_no,
            description=text((body or {}).get("description"), "回款说明", 2000),
            attachment_ids=attachment_ids,
        ))

    def void_collection(self, user, case_id, line_id, collection_id, body):
        require_any(user, "adm.collection", "adm.review")
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError("只有该主单ADM负责人可以作废回款记录", 403, "ADM_FORBIDDEN")
        return _json_value(self.repository.void_collection(
            int(case_id), int(line_id), int(collection_id), actor,
            text((body or {}).get("reason"), "作废原因", 1000),
        ))

    def _owner_actor(self, user, case_id, action, *permissions):
        require_any(user, *(permissions or ("adm.review",)))
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if not user.get("is_admin") and stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError(f"只有该主单ADM负责人可以{action}", 403, "ADM_FORBIDDEN")
        return actor

    def _assigned_owner_actor(self, user, case_id, action, *permissions):
        """Require the actual ADM coordinator even when the account is a system administrator."""
        require_any(user, *(permissions or ("adm.review",)))
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        if stored["case"]["coordinator_id"] != actor["id"]:
            raise AdmError(f"只有该主单ADM负责人可以{action}", 403, "ADM_FORBIDDEN")
        return actor

    def void_line(self, user, case_id, line_id, body):
        actor = self._owner_actor(user, case_id, "作废明细", "adm.manage", "adm.review")
        return _json_value(self.repository.void_line(
            int(case_id), int(line_id), actor,
            text((body or {}).get("reason"), "明细作废原因", 1000),
        ))

    def rebalance_lines(self, user, case_id, body):
        actor = self._owner_actor(user, case_id, "调整明细金额", "adm.manage", "adm.review")
        raw_lines = (body or {}).get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise AdmError("请提交全部有效明细金额")
        amounts = {}
        for item in raw_lines:
            try:
                line_id = int(item.get("lineId"))
            except (AttributeError, TypeError, ValueError):
                raise AdmError("明细ID无效") from None
            if line_id <= 0 or line_id in amounts:
                raise AdmError("明细ID重复或无效")
            amounts[line_id] = money(item.get("originalAmount"), "明细原币金额")
        return _json_value(self.repository.rebalance_lines(
            int(case_id), amounts, actor,
            text((body or {}).get("reason"), "金额调整原因", 1000),
        ))

    def close_case(self, user, case_id):
        actor = self._owner_actor(user, case_id, "结案", "adm.close", "adm.review")
        return _json_value(self.repository.close_case(int(case_id), actor))

    def void_case(self, user, case_id, body):
        actor = self._owner_actor(user, case_id, "作废主单", "adm.manage", "adm.review")
        return _json_value(self.repository.void_case(
            int(case_id), actor, text((body or {}).get("reason"), "主单作废原因", 1000),
        ))

    def _attachment_actor(self, user, stored, action, line_id=None):
        require(user, "adm.view")
        actor = self._actor(user)
        if user.get("is_admin") or stored["case"]["coordinator_id"] == actor["id"]:
            return actor
        eligible_lines = [
            line for line in stored["lines"]
            if line["line_status"] not in {"COMPLETED", "VOIDED", "HISTORICAL"}
            and actor["id"] in {line["leader_id"], line["operator_id"]}
        ]
        if line_id is not None:
            eligible_lines = [line for line in eligible_lines if int(line["id"]) == int(line_id)]
        if stored["case"]["case_status"] == "ACTIVE" and eligible_lines:
            return actor
        raise AdmError(f"当前人员不在该ADM主单办理范围内，不能{action}", 403, "ADM_FORBIDDEN")

    def upload_attachment(self, user, case_id, upload, category, line_id=None):
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        target_line_id = None
        if line_id not in {None, ""}:
            try:
                target_line_id = int(line_id)
            except (TypeError, ValueError):
                raise AdmError("附件所属明细无效", 400, "ADM_INVALID") from None
            if target_line_id <= 0 or not any(int(line["id"]) == target_line_id for line in stored["lines"]):
                raise AdmError("附件所属明细不属于当前ADM主单", 400, "ADM_INVALID")
        actor = self._attachment_actor(user, stored, "上传附件", target_line_id)
        category_value = text(category, "附件分类", 32).upper()
        metadata = self.attachment_storage.save(int(case_id), upload)
        try:
            return _json_value(self.repository.add_attachment(
                int(case_id), actor, category_value, metadata, target_line_id,
            ))
        except Exception:
            self.attachment_storage.path(metadata["storageKey"]).unlink(missing_ok=True)
            raise

    def attachment_file(self, user, case_id, attachment_id, *, download=False, reason=None):
        require(user, "adm.view")
        stored = self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        if download:
            return self.authorize_attachment_download(
                user, case_id, attachment_id, reason=reason, audit=True, stored=stored,
            )
        attachment = self.repository.attachment(int(case_id), int(attachment_id))
        if attachment["preview_status"] != "AVAILABLE":
            raise AdmError("该文件类型暂不支持在线预览", 409, "ADM_PREVIEW_UNSUPPORTED")
        return self.attachment_storage.path(attachment["storage_key"]), attachment

    def authorize_attachment_download(
        self, user, case_id, attachment_id, *, reason=None, audit=False, stored=None,
    ):
        """Authorize an original-file export without requiring the file to be previewable."""
        require(user, "adm.view")
        stored = stored or self.repository.get_case(int(case_id))
        if not stored:
            raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
        actor = self._actor(user)
        self._attachment_actor(user, stored, "下载附件")
        assigned = stored["case"]["coordinator_id"] == actor["id"] or (
            stored["case"]["case_status"] == "ACTIVE" and any(
                line["line_status"] not in {"COMPLETED", "VOIDED", "HISTORICAL"}
                and actor["id"] in {line["leader_id"], line["operator_id"]}
                for line in stored["lines"]
            )
        )
        if user.get("is_admin") and not assigned and not str(reason or "").strip():
            raise AdmError("管理员兜底下载必须填写访问原因")
        attachment = self.repository.attachment(int(case_id), int(attachment_id))
        if audit:
            self.repository.audit_attachment_download(
                int(case_id), int(attachment_id), actor, str(reason or "").strip() or None,
            )
        return self.attachment_storage.path(attachment["storage_key"]), attachment

    def void_attachment(self, user, case_id, attachment_id, body):
        actor = self._owner_actor(user, case_id, "作废附件")
        return _json_value(self.repository.void_attachment(
            int(case_id), int(attachment_id), actor,
            text((body or {}).get("reason"), "附件作废原因", 1000),
        ))
