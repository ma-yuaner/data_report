"""Explicit offline ERP history intake. Never connects to or writes the ERP database."""
import hashlib
import json
import re
import uuid

from ...time_utils import business_now_naive
from .service import AdmError, AdmService, CASE_FIELDS


def prepare(raw):
    if not isinstance(raw, dict):
        raise AdmError("每条历史数据须为JSON对象")
    fields = {re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(): value for key, value in raw.items()}
    def text(key):
        return "" if fields.get(key) is None else str(fields[key]).strip()
    old_id = text("id")
    if not re.fullmatch(r"\d{1,20}", old_id):
        raise AdmError("历史id须为原ERP数字主键，不能用ADM号或行号替代")
    types = {"1": "PLATFORM", "2": "AIRLINE", "3": "SUPPLIER", "平台": "PLATFORM", "航司": "AIRLINE", "供应商": "SUPPLIER"}
    category = text("category")
    case = {
        "admNo": text("adm_no"), "supplierName": text("supplier_name") or text("supplier_code"),
        "supplierCode": text("supplier_code"), "supplierType": types.get(text("supplier_type"), "OTHER"),
        "currency": text("currency"), "originalAmount": text("total_amount"),
        "originalAmountCny": text("total_amount_cny"), "ticketCount": text("ticket_count"),
        "airline": text("airline"), "businessCategory": category,
        "issuedDate": text("supply_issue_date")[:10], "deadline": text("adm_deadline"),
        "description": text("diff_detail_reason"), "remark": text("remark"),
        "source": {"system": "erp-adm-records", "recordId": old_id, "fields": raw},
    }
    line = {
        "businessType": "UNKNOWN", "platform": text("ota_name") or text("ota_code"),
        "platformCode": text("ota_code"), "orderNo": text("ota_order_no"), "ticketNo": text("ticket_no"),
        "pnr": text("pnr_no"), "currency": case["currency"], "amount": case["originalAmount"],
        "amountCny": case["originalAmountCny"], "ticketCount": case["ticketCount"],
        "airline": case["airline"], "businessCategory": category,
        "actualOwner": text("actual_owner"), "actualHandler": text("actual_handler"),
        "recoveryDeadline": text("pnr_recover_time"), "resolution": text("resolution"),
        "description": case["description"], "differenceDescription": case["description"],
        "diffType": text("diff_type"), "diffSecondType": text("diff_second_type"), "remark": case["remark"],
    }
    # Do not split old comma-separated values without an explicit order/ticket/amount mapping.
    case["lines"] = [line]
    key = hashlib.sha256(("erp.adm_records:" + old_id).encode()).hexdigest()
    return case, {"sourceKey": key, "oldId": old_id, "fields": raw,
                  "originalStatus": text("adm_status"), "originalRecordStatus": text("status"),
                  "originalStatusLabel": {"0":"待申诉","1":"申诉中","2":"待审核","3":"已结案"}.get(text("adm_status"), "原状态待核对"),
                  "attachmentState": "NOT_MIGRATED" if text("file_url") else "NO_SOURCE_ADDRESS",
                  "verified": False}


def preview(exchange, user, file):
    if not user.get("is_admin"):
        raise AdmError("历史归档导入仅限管理员", 403, "ADM_FORBIDDEN")
    content = file.stream.read(exchange.maximum + 1)
    if len(content) > exchange.maximum:
        raise AdmError("历史JSON超过上传限制", 413)
    try:
        records = json.loads(content.decode("utf-8-sig"), parse_float=str, parse_int=str)
    except (ValueError, UnicodeError):
        raise AdmError("请提供UTF-8 JSON数组，不接受SQL文件或可执行脚本", 422) from None
    if not isinstance(records, list) or not 1 <= len(records) <= exchange.row_limit:
        raise AdmError("历史JSON须为非空数组，且不超过导入行数上限", 422)
    cases, errors, seen = [], [], set()
    service = AdmService(exchange.config)
    for position, raw in enumerate(records, 1):
        try:
            case, history = prepare(raw)
            if history["sourceKey"] in seen:
                raise AdmError("同一文件的ERP原id重复，请先核对，不按ADM号合并")
            seen.add(history["sourceKey"])
            if not case["admNo"] or not case["supplierName"]:
                raise AdmError("ADM号和供应商编码/名称不能为空")
            service._clean(case, CASE_FIELDS)
            service._new_line(case, case["lines"][0])
            case["history"] = history
            cases.append(case)
        except AdmError as error:
            errors.append({"row": position, "message": str(error)})
    plan = {"id": uuid.uuid4().hex, "userId": str(user["id"]), "createdAt": business_now_naive().isoformat(),
            "format": "erp-history-json", "mode": "HISTORY_ARCHIVE", "cases": cases, "errors": errors,
            "warnings": ["只读历史归档，不生成活跃待办，不证明已审核/付款；旧锁和账号权限不继承。附件地址仅保留，原件尚未迁移。"]}
    exchange.root.mkdir(parents=True, exist_ok=True)
    exchange._save_plan(plan)
    return {"previewId": plan["id"], "format": plan["format"], "mode": plan["mode"],
            "rowCount": len(records), "errors": errors[:200], "errorCount": len(errors), "warnings": plan["warnings"],
            "cases": [{"admNo": case["admNo"], "oldId": case["history"]["oldId"], "supplierName": case["supplierName"],
                       "lineCount": 1, "originalStatus": case["history"]["originalStatus"]} for case in cases]}
