"""Strict 19-column ADM daily creation workbook support."""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import os
from zipfile import BadZipFile, ZipFile

from .policy import AdmError


HEADERS = (
    "ADM单号", "下发方类型", "下发方名称", "主单原币币种", "主单原币总金额", "下发日期",
    "主单回复截止时间", "主单备注", "OTA平台", "OTA订单号", "供应商", "航司", "票号", "PNR编码",
    "明细原币金额", "业务归属部门", "负责组长", "差异类型", "细分差异原因",
)
KEYS = (
    "admNo", "issuerType", "issuerName", "currency", "originalAmount", "issuedDate",
    "replyDeadline", "remark", "ota", "otaOrderNo", "supplier", "airline", "ticketNo", "pnr",
    "lineAmount", "department", "leader", "diffType", "differenceReason",
)
MASTER_KEYS = KEYS[:8]
EXAMPLE_ADM_PREFIX = "【示例】"
OPTIONS_SHEET_NAME = "填写选项"
OPERATOR_HEADERS = (
    "系统主单ID", "ADM单号", "内部明细ID", "OTA平台", "OTA订单号", "供应商", "航司",
    "票号", "PNR编码", "附件地址", "业务归属部门", "负责组长", "操作人员", "处理截止时间",
    "下发方类型", "下发方名称", "ADM主单原币币种", "本笔订单ADM金额（原币）",
    "本笔订单ADM金额（人民币）", "ADM主单原币总金额", "ADM主单人民币总金额",
    "数据版本", "原状态", "恢复编码决定", "恢复编码发起时间",
    "恢复编码当前状态", "恢复编码处理确认", "本次动作", "申诉原因", "申诉对象",
    "不申诉原因", "问题归因", "差异订单匹配状态", "补充问题说明",
)
OPERATOR_ACTIONS = {
    "提交申诉", "申诉成功", "申诉失败", "不申诉",
    "重新提交负责人审核", "仅补充订单资料", "暂不处理",
}
LEGACY_OPERATOR_ACTIONS = {
    "保存为申诉中": "提交申诉", "提交申诉成功": "申诉成功",
    "提交申诉不成功": "申诉失败", "提交不申诉": "不申诉",
    "重新申诉": "提交申诉", "补充材料并重新提交": "重新提交负责人审核",
    "更正后重新提交审核": "重新提交负责人审核",
}
RETURN_SUPPLEMENT_PREFIX = "【驳回补充材料】"
RETURN_REAPPEAL_PREFIX = "【驳回重新申诉】"


def review_return_mode(item):
    reason = str(item.get("latest_review_return_reason") or "")
    if reason.startswith(RETURN_SUPPLEMENT_PREFIX):
        return "SUPPLEMENT"
    if reason.startswith(RETURN_REAPPEAL_PREFIX):
        return "REAPPEAL"
    # Historical new-system RETURNED rows did not persist a subtype. Treat them
    # conservatively as supplement-only so the ambiguous state is never exposed.
    return "SUPPLEMENT" if str(item.get("latest_review_status") or "") == "RETURNED" else None


def _operator_actions(item):
    if "WITHDRAWN" in {str(item.get("review_status") or ""), str(item.get("latest_review_status") or "")}:
        return ["重新提交负责人审核", "仅补充订单资料", "暂不处理"]
    return_mode = review_return_mode(item)
    if return_mode == "SUPPLEMENT":
        return ["重新提交负责人审核", "仅补充订单资料", "暂不处理"]
    if return_mode == "REAPPEAL":
        return ["提交申诉", "申诉成功", "申诉失败", "不申诉",
                "仅补充订单资料", "暂不处理"]
    return ["提交申诉", "申诉成功", "申诉失败", "不申诉",
            "仅补充订单资料", "暂不处理"]


def _operator_stage(item):
    if "WITHDRAWN" in {str(item.get("review_status") or ""), str(item.get("latest_review_status") or "")}:
        return "审核撤回待重提"
    if str(item.get("latest_review_status") or "") == "RETURNED":
        return "驳回重新申诉" if review_return_mode(item) == "REAPPEAL" else "驳回补充材料"
    recovery = str(item.get("recovery_status") or "UNDECIDED")
    appeal = str(item.get("appeal_status") or "UNDECIDED")
    if recovery == "UNDECIDED":
        return "待编码处理"
    if recovery == "WAITING":
        return "等待恢复编码"
    if recovery == "REMINDER_DUE":
        return "确认已查看并处理"
    return {
        "UNDECIDED": "待决定",
        "IN_PROGRESS": "申诉中",
        "SUCCEEDED": "申诉成功",
        "FAILED": "申诉失败",
        "NO_APPEAL": "不申诉",
    }.get(appeal, appeal or "待决定")


def _operator_label(value):
    return {
        "PENDING_ACCEPT": "待接单", "PROCESSING": "办理中",
        "UNDECIDED": "待判断", "NOT_REQUIRED": "无需恢复编码",
        "WAITING": "等待线下恢复", "REMINDER_DUE": "恢复完成待确认", "CONFIRMED": "已恢复并处理",
        "SUPPLIER": "供应商", "PLATFORM": "平台", "AIRLINE": "航司",
        "HUMAN": "人为问题", "SYSTEM": "系统问题",
    }.get(str(value or ""), value)


def _diff_label(value, item=None):
    appeal = str((item or {}).get("appeal_status") or "UNDECIDED")
    review = str((item or {}).get("review_status") or "")
    if appeal == "SUCCEEDED":
        return "无需匹配"
    if appeal not in {"FAILED", "NO_APPEAL"} or review != "APPROVED":
        return "未开始"
    raw = str(value or "")
    if raw.startswith("MATCHED"):
        return "已录入"
    return {
        "NOT_REQUIRED": "无需匹配", "PENDING": "待匹配",
        "UNMATCHED": "未录入", "NOT_MATCHED": "未录入",
        "QUERY_FAILED": "查询失败", "NOT_CONNECTED": "未连接",
    }.get(raw, value)


def _attribution_label(value):
    return {"HUMAN": "人为问题", "PLATFORM": "平台问题", "SYSTEM": "系统问题"}.get(
        str(value or ""), value,
    )


def _reference_label(code, name):
    raw_code = str(code or "").strip()
    raw_name = str(name or "").strip()
    if raw_code and raw_name and raw_code != raw_name:
        return f"{raw_code} / {raw_name}"
    return raw_code or raw_name or ""


def _cell_text(cell):
    if cell.data_type == "f":
        raise AdmError("导入文件不允许使用公式单元格")
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).strip()


class AdmDailyWorkbook:
    def __init__(self, config):
        self.max_rows = int(config.get("ADM_IMPORT_MAX_ROWS") or 10000)
        self.max_bytes = int(config.get("ADM_IMPORT_MAX_BYTES") or 20 * 1024 * 1024)
        self.root = Path(str(config.get("ADM_IMPORT_ROOT") or "/app/var/adm/imports")).resolve()

    def template(self, diff_types):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.workbook.defined_name import DefinedName
        from openpyxl.worksheet.datavalidation import DataValidation

        choices = list(dict.fromkeys(str(item or "").strip() for item in diff_types if str(item or "").strip()))
        if not choices:
            raise AdmError("ADM差异类型暂无有效选项，请联系管理员维护基础资料", 503, "ADM_REFERENCE_UNAVAILABLE")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ADM导入"
        sheet.append(HEADERS)
        example_master = [
            f"{EXAMPLE_ADM_PREFIX}ADM-2026-001", "航司", "CA", "CNY", 1000,
            "2026-11-10", "2026-11-12 18:00:00", "示例：相同ADM单号的主单字段须保持一致",
        ]
        sheet.append(example_master + [
            "示例OTA", "EXAMPLE-ORDER-001", "", "CA", "999-1234567890", "ABC123",
            600, "示例业务部", "示例组长", choices[0], "示例第一条明细",
        ])
        sheet.append(example_master + [
            "示例OTA", "EXAMPLE-ORDER-002", "", "CA", "999-1234567891", "ABC124",
            400, "示例业务部", "示例组长", choices[0], "示例第二条明细",
        ])
        header = sheet[1]
        for cell in header:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="245FCE")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        widths = (20, 14, 22, 14, 18, 14, 21, 24, 18, 24, 20, 12, 20, 16, 18, 22, 18, 22, 32)
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[chr(64 + index)].width = width
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = "A1:S1"
        issuer_validation = DataValidation(type="list", formula1='"平台,供应商,航司"', allow_blank=False)
        sheet.add_data_validation(issuer_validation)
        issuer_validation.add(f"B2:B{self.max_rows + 1}")
        options_sheet = workbook.create_sheet(OPTIONS_SHEET_NAME)
        options_sheet.append(["差异类型"])
        for value in choices:
            options_sheet.append([value])
        options_sheet.sheet_state = "hidden"
        workbook.defined_names.add(DefinedName(
            "ADM_DIFF_TYPE_OPTIONS",
            attr_text=f"'{OPTIONS_SHEET_NAME}'!$A$2:$A${len(choices) + 1}",
        ))
        diff_validation = DataValidation(type="list", formula1="ADM_DIFF_TYPE_OPTIONS", allow_blank=False)
        diff_validation.error = "请选择下拉列表中的有效差异类型"
        diff_validation.errorTitle = "差异类型无效"
        diff_validation.showErrorMessage = True
        sheet.add_data_validation(diff_validation)
        diff_validation.add(f"R2:R{self.max_rows + 1}")
        example_fill = PatternFill("solid", fgColor="FFF7E6")
        for row in sheet.iter_rows(min_row=2, max_row=3, min_col=1, max_col=len(HEADERS)):
            for cell in row:
                cell.fill = example_fill
                cell.font = Font(color="8C6D1F", italic=True)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        sheet.column_dimensions["H"].hidden = False
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    def _read_bytes(self, upload):
        filename = str(getattr(upload, "filename", "") or "").strip()
        if not filename.lower().endswith(".xlsx"):
            raise AdmError("请上传.xlsx格式的19列ADM模板")
        content = upload.stream.read(self.max_bytes + 1)
        if len(content) > self.max_bytes:
            raise AdmError(f"Excel文件不能超过{self.max_bytes // (1024 * 1024)}MB")
        if not content:
            raise AdmError("Excel文件不能为空")
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(item.file_size for item in entries) > 50 * 1024 * 1024:
                    raise AdmError("Excel解压后的文件数或体积超限")
                names = {item.filename.lower() for item in entries}
                if "[content_types].xml" not in names or any(name.endswith("vbaproject.bin") for name in names):
                    raise AdmError("Excel文件结构无效或包含宏")
        except BadZipFile:
            raise AdmError("Excel文件已损坏") from None
        return content

    def parse(self, upload):
        from openpyxl import load_workbook

        content = self._read_bytes(upload)
        try:
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
        except Exception as exc:
            raise AdmError("Excel文件无法读取") from exc
        try:
            names = {sheet.title for sheet in workbook.worksheets}
            if "ADM导入" not in names or not names.issubset({"ADM导入", OPTIONS_SHEET_NAME}):
                raise AdmError("19列ADM模板工作表结构已被修改，请重新下载模板")
            sheet = workbook["ADM导入"]
            actual_headers = tuple(_cell_text(sheet.cell(1, index)) for index in range(1, len(HEADERS) + 1))
            if actual_headers != HEADERS:
                raise AdmError("Excel表头或列顺序已被修改，请重新下载19列模板")
            rows = []
            for row_number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=len(HEADERS)), 2):
                values = [_cell_text(cell) for cell in cells]
                if not any(values):
                    continue
                if values[0].startswith(EXAMPLE_ADM_PREFIX):
                    continue
                if len(rows) >= self.max_rows:
                    raise AdmError(f"单次最多导入{self.max_rows}行明细")
                rows.append({"rowNumber": row_number, **dict(zip(KEYS, values))})
            if not rows:
                raise AdmError("Excel中没有正式ADM明细，请在示例行下方填写数据")
            groups = {}
            for row in rows:
                adm_no = row["admNo"].strip()
                key = adm_no or f"__ROW_{row['rowNumber']}"
                groups.setdefault(key, []).append(row)
            for group in groups.values():
                first = group[0]
                for row in group[1:]:
                    if any(row[key] != first[key] for key in MASTER_KEYS):
                        raise AdmError(f"第{row['rowNumber']}行：同一ADM单号的主单字段必须完全一致")
            return {"content": content, "rows": rows, "groups": list(groups.values())}
        finally:
            workbook.close()

    def save_preview(self, batch_no, content):
        self.root.mkdir(parents=True, exist_ok=True)
        final_path = (self.root / f"{batch_no}.xlsx").resolve()
        temporary_path = (self.root / f"{batch_no}.uploading").resolve()
        if self.root not in final_path.parents:
            raise AdmError("ADM导入存储路径无效", 500, "ADM_IMPORT_STORAGE")
        try:
            with temporary_path.open("xb") as target:
                target.write(content)
            os.replace(temporary_path, final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return final_path

    def preview_path(self, batch_no):
        path = (self.root / f"{batch_no}.xlsx").resolve()
        if self.root not in path.parents or not path.is_file():
            raise AdmError("导入预检文件不存在", 404, "ADM_IMPORT_FILE_NOT_FOUND")
        return path

    def operator_export(self, rows):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "待处理订单"
        sheet.append(OPERATOR_HEADERS)
        for item in rows:
            sheet.append([
                item["case_internal_no"], item["adm_no"], item["line_internal_no"],
                _reference_label(item.get("ota_code"), item.get("ota_name")),
                item["ota_order_no"], _reference_label(item.get("supplier_code"), item.get("supplier_name")),
                item["airline_name"], item["ticket_no"],
                item["pnr"], item.get("attachment_address"), item["department_name"], item["leader_name"], item["operator_name"],
                item["process_deadline"], _operator_label(item["issuer_type"]), item["issuer_name"], item["currency"],
                item["original_amount"], item["cny_amount"], item["case_original_amount"],
                item["case_cny_amount"], item["version_no"], _operator_stage(item),
                ("需要恢复编码" if item["recovery_status"] in {"WAITING", "REMINDER_DUE", "CONFIRMED"}
                 else "无需恢复编码" if item["recovery_status"] == "NOT_REQUIRED" else ""),
                item.get("recovery_started_at"), _operator_label(item["recovery_status"]),
                "已查看并处理" if item["recovery_status"] == "CONFIRMED" else "", "",
                item.get("latest_appeal_reason"), item.get("latest_appeal_target"),
                item.get("latest_no_appeal_reason"),
                _attribution_label(item["problem_attribution"]), _diff_label(item["diff_match_status"], item),
                item["investigation_note"],
            ])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="245FCE")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        readonly_fill = PatternFill("solid", fgColor="F2F4F7")
        editable_fill = PatternFill("solid", fgColor="FFFFFF")
        border = Border(bottom=Side(style="thin", color="DCE3ED"))
        for row_number, (row, item) in enumerate(zip(sheet.iter_rows(min_row=2), rows), 2):
            recovery = str(item.get("recovery_status") or "UNDECIDED")
            return_mode = review_return_mode(item)
            correction_only = return_mode == "SUPPLEMENT" or "WITHDRAWN" in {
                str(item.get("review_status") or ""), str(item.get("latest_review_status") or ""),
            }
            editable_columns = {4, 5, 6, 7, 8, 9, 28}
            if recovery == "UNDECIDED":
                editable_columns.add(24)
            if recovery in {"WAITING", "REMINDER_DUE"}:
                editable_columns.add(27)
            if not correction_only:
                editable_columns.update({29, 30, 31, 32, 34})
            for index, cell in enumerate(row, 1):
                cell.protection = Protection(locked=index not in editable_columns)
                cell.fill = editable_fill if index in editable_columns else readonly_fill
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border
            validations = (
                (24, ["需要恢复编码", "无需恢复编码"] if recovery == "UNDECIDED" else []),
                (27, ["已查看并处理"] if recovery in {"WAITING", "REMINDER_DUE"} else []),
                (28, _operator_actions(item)),
                (32, ["人为问题", "平台问题", "系统问题"] if not correction_only else []),
            )
            for column, options in validations:
                if not options:
                    continue
                validation = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
                validation.error = "请选择当前状态允许的选项"
                validation.errorTitle = "选项无效"
                validation.showErrorMessage = True
                sheet.add_data_validation(validation)
                validation.add(sheet.cell(row_number, column))
        for column in (18, 19, 20, 21):
            for cell in sheet.iter_cols(min_col=column, max_col=column, min_row=2):
                for item in cell:
                    item.number_format = "#,##0.00"
        widths = (
            18, 18, 22, 18, 24, 20, 16, 20, 16, 36, 20, 16, 16, 22, 16, 22, 20,
            20, 20, 22, 22, 18, 12, 20, 22, 22, 22, 24, 32, 24, 32, 18, 24, 42,
        )
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.row_dimensions[1].height = 34
        for row_number in range(2, sheet.max_row + 1):
            sheet.row_dimensions[row_number].height = 36
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(OPERATOR_HEADERS))}1"
        sheet.protection.sheet = True
        # Keep locked cells protected while allowing users to resize columns and use filters.
        sheet.protection.formatColumns = False
        sheet.protection.autoFilter = False
        sheet.protection.sort = False
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        output.seek(0)
        return output

    def parse_operator_results(self, upload):
        from openpyxl import load_workbook

        content = self._read_bytes(upload)
        try:
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
        except Exception as exc:
            raise AdmError("操作员处理结果Excel无法读取") from exc
        try:
            if len(workbook.worksheets) != 1:
                raise AdmError("操作员处理结果只能包含一个工作表")
            sheet = workbook.worksheets[0]
            actual = tuple(_cell_text(sheet.cell(1, index)) for index in range(1, len(OPERATOR_HEADERS) + 1))
            if actual != OPERATOR_HEADERS:
                raise AdmError("处理结果Excel表头或列顺序已被修改，请重新从工作台导出")
            rows = []
            for row_number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=len(OPERATOR_HEADERS)), 2):
                values = [_cell_text(cell) for cell in cells]
                if not any(values):
                    continue
                action = LEGACY_OPERATOR_ACTIONS.get(values[27], values[27])
                if action and action not in OPERATOR_ACTIONS:
                    raise AdmError(f"第{row_number}行：本次处理动作无效")
                try:
                    version = int(values[21])
                except (TypeError, ValueError):
                    raise AdmError(f"第{row_number}行：数据版本无效") from None
                rows.append({
                    "rowNumber": row_number, "caseInternalNo": values[0], "admNo": values[1],
                    "lineInternalNo": values[2], "operatorName": values[12], "lineStatus": values[22],
                    "versionNo": version, "action": action, "ota": values[3],
                    "otaOrderNo": values[4], "supplier": values[5], "airline": values[6],
                    "ticketNo": values[7], "pnr": values[8], "attachmentAddress": values[9],
                    "departmentName": values[10], "leaderName": values[11], "processDeadline": values[13],
                    "issuerType": values[14], "issuerName": values[15], "currency": values[16],
                    "originalAmount": values[17], "cnyAmount": values[18],
                    "caseOriginalAmount": values[19], "caseCnyAmount": values[20],
                    "recoveryStartedAt": values[24],
                    "recoveryStatus": values[25], "diffMatchStatus": values[32],
                    "recoveryDecision": values[23], "recoveryConfirmation": values[26],
                    "appealReason": values[28], "appealTarget": values[29],
                    "noAppealReason": values[30], "problemAttribution": values[31],
                    "investigationNote": values[33], "resultNote": values[33],
                })
            if not rows:
                raise AdmError("Excel中没有订单数据")
            return rows
        finally:
            workbook.close()


class StoredUpload:
    def __init__(self, path):
        self.filename = Path(path).name
        self.stream = Path(path).open("rb")

    def close(self):
        self.stream.close()
