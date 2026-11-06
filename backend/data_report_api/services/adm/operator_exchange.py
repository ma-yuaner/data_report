"""ADM 0.5 operator-owned 34-column offline task exchange."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ...time_utils import business_now_naive
from .attachments import validate_document
from .exchange import check_permission, excel_text, reference_export_value, split_reference
from .policy import AdmError, identity
from .service import AdmService, internal_adm_no


LEGACY_OPERATOR34 = [
    "主单内部单号", "ADM单号", "明细内部单号", "OTA平台", "OTA订单号", "供应商", "航司", "票号", "PNR编码",
    "业务归属部门", "ADM负责人", "当前承办人", "处理截止时间", "下发方类型", "下发方名称", "ADM主单原币币种",
    "本笔订单ADM金额（原币）", "本笔订单ADM金额（人民币）", "ADM主单原币总金额", "ADM主单人民币总金额",
    "原状态", "数据版本", "原处理结论", "恢复编码决定", "恢复编码发起时间", "恢复编码当前状态",
    "恢复编码处理确认", "本次动作", "申诉原因", "申诉对象", "不申诉原因", "问题归因",
    "差异订单匹配状态", "订单核查情况及原因说明",
]
OPERATOR35 = [*LEGACY_OPERATOR34[:9], "附件地址", *LEGACY_OPERATOR34[9:]]
# Compatibility export for callers that imported the old constant name.
OPERATOR34 = OPERATOR35

STATUS_LABELS = {
    "PENDING_CODE_PROCESSING": "待编码处理",
    "PENDING_DECISION": "待决定",
    "APPEAL_IN_PROGRESS": "申诉中",
    "REJECTED_FOR_REVISION": "驳回待修改",
}
RECOVERY_LABELS = {
    "UNDECIDED": "待判断", "WAITING_MANUAL": "等待线下恢复",
    "NOT_REQUIRED": "无需恢复编码", "MANUALLY_COMPLETED": "已恢复并处理",
}
ACTIONS = {"保存为申诉中", "提交申诉成功", "提交申诉不成功", "提交不申诉", "仅补充订单资料", "暂不处理"}
ATTRIBUTIONS = {"人为问题": "HUMAN", "平台问题": "PLATFORM", "系统问题": "SYSTEM"}


def _number(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _option(value: str, options: list[dict], label: str) -> dict:
    code, name = split_reference(value)
    matches = [item for item in options if (code and str(item.get("code")) == code) or (not code and name == str(item.get("name")))]
    if len(matches) != 1:
        raise AdmError(f"{label}须填写唯一的编码/名称")
    return matches[0]


class AdmOperatorExchange:
    def __init__(self, config: dict):
        self.config = config
        self.root = Path(str(config.get("ADM_IMPORT_ROOT", "/app/var/adm-imports"))).resolve()
        self.maximum = int(config.get("ADM_ATTACHMENT_MAX_BYTES", 20 * 1024 * 1024))
        self.row_limit = min(5000, int(config.get("ADM_IMPORT_MAX_ROWS", 10000)))

    def _eligible(self, user: dict, statuses: set[str] | None = None) -> list[tuple[dict, dict]]:
        check_permission(user, "adm.handle")
        service = AdmService(self.config)
        actor = identity(user)
        allowed = statuses or set(STATUS_LABELS)
        rows = []
        for case in service._all():
            if case.get("status") in {"CLOSED", "HISTORICAL"} or case.get("paused") or case.get("voided"):
                continue
            for line in case.get("lines", []):
                if str(line.get("ownerId") or "") == actor and line.get("status") in allowed:
                    rows.append((case, line))
                    if len(rows) > self.row_limit:
                        raise AdmError(f"待处理订单超过{self.row_limit}行，请缩小任务类型后导出", 422, "ADM_EXPORT_LIMIT")
        return rows

    def export(self, user: dict, status_values: list[str] | None = None) -> tuple[io.BytesIO, str]:
        statuses = set(status_values or STATUS_LABELS)
        if not statuses or not statuses.issubset(STATUS_LABELS):
            raise AdmError("导出任务类型无效")
        rows = self._eligible(user, statuses)
        lookup = self.config.get("ADM_DIFFERENCE_MATCH_LOOKUP")
        matched: set[str] = set()
        match_failed = False
        if callable(lookup):
            keys = [str(line.get("orderNo") or "").strip() for case, line in rows]
            keys.extend(
                str(case.get("internalNo") or internal_adm_no(case.get("admNo"), case.get("id")))
                for case, _line in rows
            )
            try:
                matched = set(lookup(keys))
            except Exception:
                match_failed = True
        book = Workbook()
        sheet = book.active
        sheet.title = "待处理订单"
        sheet.append(OPERATOR35)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:AI{max(2, len(rows) + 1)}"
        gray = PatternFill("solid", fgColor="F2F4F7")
        blue = PatternFill("solid", fgColor="245FCE")
        for cell in sheet[1]:
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.fill = blue
            cell.protection = Protection(locked=True)
        for case, line in rows:
            recovery = line.get("recovery") or {}
            appeal = (line.get("appeals") or [{}])[-1]
            order_no = str(line.get("orderNo") or "").strip()
            case_internal_no = str(
                case.get("internalNo") or internal_adm_no(case.get("admNo"), case.get("id"))
            )
            if not callable(lookup):
                difference_status = "未接入"
            elif match_failed:
                difference_status = "核验失败"
            elif order_no and order_no in matched:
                difference_status = "已录入（OTA订单号）"
            elif case_internal_no in matched:
                difference_status = "已录入（内部单号）"
            else:
                difference_status = "未录入"
            values = [
                case_internal_no, case["admNo"], line.get("lineInternalNo") or line["id"], reference_export_value(line.get("platformCode"), line.get("platform")),
                line.get("orderNo"), reference_export_value(line.get("supplierCode"), line.get("supplier")), line.get("airline"),
                line.get("ticketNo"), line.get("pnr"), line.get("attachmentUrl"),
                reference_export_value(line.get("departmentCode"), line.get("departmentName")),
                case.get("coordinatorName"), case.get("ownerName"), line.get("deadline") or case.get("deadline"), case.get("supplierType"),
                reference_export_value(case.get("supplierCode"), case.get("supplierName")), case.get("currency"), _number(line.get("amount")),
                _number(line.get("amountCny")), _number(case.get("originalAmount")), _number(case.get("originalAmountCny")), STATUS_LABELS[line["status"]],
                case["version"], line.get("processingResult") or "", "需要恢复编码" if line.get("recoveryRequired") else "无需恢复编码" if recovery.get("state") == "NOT_REQUIRED" else "",
                recovery.get("decidedAt"), RECOVERY_LABELS.get(recovery.get("state", "UNDECIDED"), recovery.get("state", "")), "", "",
                line.get("appealReason") or appeal.get("reason") or "", appeal.get("target") or "", line.get("appealReason") if line.get("processingResult") == "NO_APPEAL" else "",
                next((label for label, code in ATTRIBUTIONS.items() if code == line.get("attribution")), ""),
                difference_status, line.get("investigationNote") or line.get("recoveryNote") or "",
            ]
            row = sheet.append(values) or sheet[sheet.max_row]
            row_number = sheet.max_row
            attachment_url = str(line.get("attachmentUrl") or "").strip()
            if re.fullmatch(r"https://[^\s]{1,2048}", attachment_url):
                sheet.cell(row_number, 10).hyperlink = attachment_url
                sheet.cell(row_number, 10).style = "Hyperlink"
            editable = {4, 5, 6, 7, 8, 9, 29, 30, 31, 32, 33, 35}
            if line["status"] == "PENDING_CODE_PROCESSING" and recovery.get("state", "UNDECIDED") == "UNDECIDED":
                editable.add(25)
            if line["status"] == "PENDING_CODE_PROCESSING" and recovery.get("state") in {"UNDECIDED", "WAITING_MANUAL"}:
                editable.add(28)
            for column in range(1, 36):
                cell = sheet.cell(row_number, column)
                cell.protection = Protection(locked=column not in editable)
                if column not in editable:
                    cell.fill = gray
            if 25 in editable:
                validation = DataValidation(type="list", formula1='"需要恢复编码,无需恢复编码"', allow_blank=True)
                sheet.add_data_validation(validation); validation.add(sheet.cell(row_number, 25))
            if 28 in editable:
                validation = DataValidation(type="list", formula1='"已恢复并处理"', allow_blank=True)
                sheet.add_data_validation(validation); validation.add(sheet.cell(row_number, 28))
            validation = DataValidation(type="list", formula1='"保存为申诉中,提交申诉成功,提交申诉不成功,提交不申诉,仅补充订单资料,暂不处理"', allow_blank=True)
            sheet.add_data_validation(validation); validation.add(sheet.cell(row_number, 29))
            attribution = DataValidation(type="list", formula1='"人为问题,平台问题,系统问题"', allow_blank=True)
            sheet.add_data_validation(attribution); attribution.add(sheet.cell(row_number, 33))
            for column in (18, 19, 20, 21):
                sheet.cell(row_number, column).number_format = "#,##0.00"
        for index, width in enumerate([23,22,23,25,22,25,16,22,18,45,22,18,18,22,14,25,18,20,20,20,20,16,14,18,18,21,20,20,22,28,22,28,16,22,30], 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.protection.sheet = True
        sheet.protection.password = "ADM-V05-OPERATOR"
        content = io.BytesIO(); book.save(content); book.close(); content.seek(0)
        return content, f"ADM_操作人员待处理_{business_now_naive():%Y%m%d_%H%M}.xlsx"

    def _save_plan(self, plan: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{plan['id']}.operator.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as output:
            json.dump(plan, output, ensure_ascii=False)
            temporary = Path(output.name)
        temporary.replace(destination)

    def preview(self, user: dict, file) -> dict:
        check_permission(user, "adm.handle")
        if not str(file.filename or "").lower().endswith(".xlsx"):
            raise AdmError("请选择从本人工作台导出的XLSX文件", 422, "ADM_IMPORT_TYPE")
        content = file.stream.read(self.maximum + 1)
        if len(content) > self.maximum:
            raise AdmError("处理结果文件超过大小限制", 413, "ADM_IMPORT_LIMIT")
        self.root.mkdir(parents=True, exist_ok=True)
        preview_id = uuid.uuid4().hex
        source = self.root / f"{preview_id}.operator.xlsx"
        source.write_bytes(content)
        try:
            validate_document(source, ".xlsx", self.maximum)
            book = load_workbook(source, read_only=True, data_only=False, keep_links=False)
            try:
                if book.sheetnames != ["待处理订单"]:
                    raise AdmError("操作人员处理结果须为单Sheet Excel", 422, "ADM_HEADERS")
                sheet = book["待处理订单"]
                iterator = sheet.iter_rows()
                headers = [excel_text(cell.value) for cell in next(iterator, [])]
                if headers not in (OPERATOR35, LEGACY_OPERATOR34):
                    raise AdmError("模板表头或顺序已修改，请重新导出", 422, "ADM_HEADERS")
                legacy_layout = headers == LEGACY_OPERATOR34
                service = AdmService(self.config)
                references = self.config["ADM_REFERENCE_OPTIONS"]() if callable(self.config.get("ADM_REFERENCE_OPTIONS")) else {"platforms": [], "suppliers": []}
                actor = identity(user); items = []; errors = []
                for number, cells in enumerate(iterator, 2):
                    if number > self.row_limit + 1:
                        raise AdmError(f"最多回导{self.row_limit}行", 413, "ADM_IMPORT_LIMIT")
                    if not any(cell.value not in (None, "") for cell in cells):
                        continue
                    if any(cell.data_type == "f" for cell in cells):
                        errors.append({"row": number, "message": "不接受公式，请粘贴为值"}); continue
                    values = [excel_text(cells[index].value) if index < len(cells) else "" for index in range(len(headers))]
                    if legacy_layout:
                        values.insert(9, "")
                    try:
                        case = service._read_by_internal_no(user, values[0]); line = service._line(case, values[2])
                        if str(line.get("ownerId")) != actor:
                            raise AdmError("订单已不属于当前操作人员")
                        if STATUS_LABELS.get(line.get("status")) != values[21] or str(case["version"]) != values[22]:
                            raise AdmError("订单状态或数据版本已变化，请重新导出")
                        changes = {}
                        for index, code_key, name_key, collection, label in ((3,"platformCode","platform","platforms","OTA平台"),(5,"supplierCode","supplier","suppliers","供应商")):
                            current = reference_export_value(line.get(code_key), line.get(name_key))
                            if values[index] != current:
                                if values[index]:
                                    option = _option(values[index], references.get(collection, []), label)
                                    changes.update({code_key: str(option["code"]), name_key: str(option["name"])})
                                else:
                                    changes.update({code_key: "", name_key: ""})
                        for index, key in ((4,"orderNo"),(6,"airline"),(7,"ticketNo"),(8,"pnr"),(34,"investigationNote")):
                            if values[index] != excel_text(line.get(key)):
                                changes[key] = values[index]
                        recovery_decision, recovery_handling, action = values[24], values[27], values[28]
                        if action and action not in ACTIONS:
                            raise AdmError("本次动作无效")
                        if changes and action not in {"仅补充订单资料", "保存为申诉中", "提交申诉成功", "提交申诉不成功", "提交不申诉"}:
                            raise AdmError("资料有变化，请选择“仅补充订单资料”或实际处理动作")
                        recovery_state = (line.get("recovery") or {}).get("state", "UNDECIDED")
                        if recovery_decision and not (line["status"] == "PENDING_CODE_PROCESSING" and recovery_state == "UNDECIDED"):
                            raise AdmError("当前恢复阶段不能修改恢复编码决定")
                        if recovery_decision not in {"", "需要恢复编码", "无需恢复编码"}:
                            raise AdmError("恢复编码决定无效")
                        if recovery_handling not in {"", "已恢复并处理"}:
                            raise AdmError("恢复编码处理确认无效")
                        if recovery_handling and recovery_state not in {"UNDECIDED", "WAITING_MANUAL"}:
                            raise AdmError("当前恢复阶段不能确认已恢复并处理")
                        if recovery_handling and recovery_state == "UNDECIDED" and recovery_decision != "需要恢复编码":
                            raise AdmError("同一行确认已恢复并处理前，须先选择需要恢复编码")
                        result_actions = {"保存为申诉中", "提交申诉成功", "提交申诉不成功", "提交不申诉"}
                        effective_decision_ready = line["status"] in {"PENDING_DECISION", "REJECTED_FOR_REVISION"}
                        effective_appeal_ready = line["status"] == "APPEAL_IN_PROGRESS"
                        if line["status"] == "PENDING_CODE_PROCESSING":
                            effective_decision_ready = recovery_decision == "无需恢复编码" or bool(recovery_handling)
                        if action in result_actions and not (effective_decision_ready or effective_appeal_ready):
                            raise AdmError("编码恢复前置尚未完成，不能提交申诉或不申诉结果")
                        if effective_appeal_ready and action not in {"", "暂不处理", "仅补充订单资料", "提交申诉成功", "提交申诉不成功"}:
                            raise AdmError("申诉中订单只能提交申诉成功或不成功")
                        if action in {"保存为申诉中", "提交申诉成功", "提交申诉不成功"} and (not values[29] or not values[30]):
                            raise AdmError("申诉原因和申诉对象必填")
                        if action == "提交不申诉" and not values[31]:
                            raise AdmError("不申诉原因必填")
                        if action in {"提交申诉不成功", "提交不申诉"} and values[32] not in ATTRIBUTIONS:
                            raise AdmError("问题归因必填")
                        if action in {"", "暂不处理"} and not changes and not recovery_decision and not recovery_handling:
                            items.append({"row": number, "status": "SKIPPED"}); continue
                        items.append({"row": number, "status": "READY", "caseId": case["id"], "lineId": line["id"], "version": case["version"], "lineStatus": line["status"], "changes": changes, "recoveryDecision": recovery_decision, "recoveryHandling": recovery_handling, "action": action, "appealReason": values[29], "appealTarget": values[30], "noAppealReason": values[31], "attribution": ATTRIBUTIONS.get(values[32], "")})
                    except AdmError as error:
                        errors.append({"row": number, "message": str(error)})
                plan = {"id": preview_id, "userId": actor, "createdAt": business_now_naive().isoformat(), "sha256": hashlib.sha256(content).hexdigest(), "items": items, "errors": errors, "outcomes": {}}
                self._save_plan(plan)
                return {"previewId": preview_id, "rowCount": len(items) + len(errors), "readyCount": sum(item["status"] == "READY" for item in items), "skippedCount": sum(item["status"] == "SKIPPED" for item in items), "errorCount": len(errors), "errors": errors[:200], "items": [{key: item[key] for key in ("row","status")} for item in items]}
            finally:
                book.close()
        except Exception:
            if not (self.root / f"{preview_id}.operator.json").exists(): source.unlink(missing_ok=True)
            raise

    def commit(self, user: dict, preview_id: str) -> dict:
        check_permission(user, "adm.handle")
        if not re.fullmatch(r"[a-f0-9]{32}", preview_id):
            raise AdmError("处理结果预览不存在", 404, "ADM_IMPORT_NOT_FOUND")
        path = self.root / f"{preview_id}.operator.json"
        if not path.is_file():
            raise AdmError("处理结果预览不存在或已清理", 404, "ADM_IMPORT_NOT_FOUND")
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan["userId"] != identity(user):
            raise AdmError("没有此处理结果预览权限", 403, "ADM_FORBIDDEN")
        if datetime.fromisoformat(plan["createdAt"]) < business_now_naive() - timedelta(hours=2):
            raise AdmError("预览已过期，请重新导出并上传", 409, "ADM_IMPORT_EXPIRED")
        if plan["errors"]:
            raise AdmError("预览存在错误，请修正后重新上传", 422, "ADM_IMPORT_INVALID")
        service = AdmService(self.config); outcomes = plan.get("outcomes", {})
        for item in plan["items"]:
            key = str(item["row"])
            if item["status"] != "READY" or key in outcomes: continue
            try:
                case = service.case_detail(user, item["caseId"])
                if case["version"] != item["version"]:
                    raise AdmError("数据版本已变化，请重新导出", 409, "ADM_VERSION_CONFLICT")
                if item["changes"]:
                    case = service.update_line(user, item["caseId"], item["lineId"], {"version": case["version"], **item["changes"]})
                if item["recoveryDecision"]:
                    case = service.line_action(user, item["caseId"], item["lineId"], {"version": case["version"], "action": "recovery_decide", "required": item["recoveryDecision"] == "需要恢复编码"})
                if item["recoveryHandling"]:
                    case = service.line_action(user, item["caseId"], item["lineId"], {"version": case["version"], "action": "recovery_complete"})
                action = item["action"]
                if action not in {"", "暂不处理", "仅补充订单资料"}:
                    line = service._line(case, item["lineId"])
                    if line["status"] == "REJECTED_FOR_REVISION":
                        body = {"version": case["version"], "action": "resubmit", "decision": "APPEAL" if action == "保存为申诉中" else "NO_APPEAL" if action == "提交不申诉" else "", "result": "APPEAL_SUCCESS" if action == "提交申诉成功" else "APPEAL_FAILED" if action == "提交申诉不成功" else "", "reason": item["appealReason"] or item["noAppealReason"], "target": item["appealTarget"], "attribution": item["attribution"]}
                        case = service.line_action(user, item["caseId"], item["lineId"], body)
                    else:
                        if line["status"] == "PENDING_DECISION":
                            decision = "NO_APPEAL" if action == "提交不申诉" else "APPEAL"
                            case = service.line_action(user, item["caseId"], item["lineId"], {"version": case["version"], "action": "decide", "decision": decision, "reason": item["noAppealReason"] if decision == "NO_APPEAL" else item["appealReason"], "target": item["appealTarget"], "attribution": item["attribution"]})
                        if action in {"提交申诉成功", "提交申诉不成功"}:
                            case = service.line_action(user, item["caseId"], item["lineId"], {"version": case["version"], "action": "appeal_result", "result": "APPEAL_SUCCESS" if action == "提交申诉成功" else "APPEAL_FAILED", "reason": item["appealReason"], "attribution": item["attribution"]})
                outcomes[key] = {"row": item["row"], "status": "SUCCESS", "caseId": item["caseId"], "lineId": item["lineId"], "version": case["version"]}
            except AdmError as error:
                outcomes[key] = {"row": item["row"], "status": "FAILED", "message": str(error), "code": error.code}
            plan["outcomes"] = outcomes; self._save_plan(plan)
        result = list(outcomes.values())
        return {"previewId": preview_id, "items": result, "successCount": sum(item["status"] == "SUCCESS" for item in result), "failedCount": sum(item["status"] == "FAILED" for item in result), "skippedCount": sum(item["status"] == "SKIPPED" for item in plan["items"])}
