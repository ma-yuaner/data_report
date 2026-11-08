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
OPERATOR_HEADERS = (
    "主单内部编号", "ADM单号", "明细内部编号", "OTA平台", "OTA订单号", "供应商", "航司",
    "票号", "PNR编码", "业务归属部门", "负责组长", "操作员", "处理截止时间",
    "下发方类型", "下发方名称", "原币币种", "明细原币金额", "明细人民币金额",
    "主单原币总金额", "主单人民币总金额", "明细状态", "数据版本", "恢复处理状态",
    "申诉状态", "问题归因", "差异单匹配状态", "订单情况说明", "本次处理动作",
    "恢复编码决定", "无需恢复原因", "恢复处理确认", "申诉原因", "申诉对象",
    "不申诉原因", "本次问题归因", "申诉结果说明",
)
OPERATOR_ACTIONS = {
    "更新订单情况说明", "登记恢复决定", "确认恢复处理", "开始申诉",
    "登记申诉成功", "登记申诉失败", "登记不申诉", "提交审核",
}


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

    def template(self):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ADM导入"
        sheet.append(HEADERS)
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
            if len(workbook.worksheets) != 1:
                raise AdmError("19列ADM模板只能包含一个工作表")
            sheet = workbook.worksheets[0]
            actual_headers = tuple(_cell_text(sheet.cell(1, index)) for index in range(1, len(HEADERS) + 1))
            if actual_headers != HEADERS:
                raise AdmError("Excel表头或列顺序已被修改，请重新下载19列模板")
            rows = []
            for row_number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=len(HEADERS)), 2):
                values = [_cell_text(cell) for cell in cells]
                if not any(values):
                    continue
                if len(rows) >= self.max_rows:
                    raise AdmError(f"单次最多导入{self.max_rows}行明细")
                rows.append({"rowNumber": row_number, **dict(zip(KEYS, values))})
            if not rows:
                raise AdmError("Excel中没有ADM明细")
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
        from openpyxl.styles import Font, PatternFill, Protection
        from openpyxl.utils import get_column_letter

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "待处理明细"
        sheet.append(OPERATOR_HEADERS)
        for item in rows:
            sheet.append([
                item["case_internal_no"], item["adm_no"], item["line_internal_no"], item["ota_name"],
                item["ota_order_no"], item["supplier_name"], item["airline_name"], item["ticket_no"],
                item["pnr"], item["department_name"], item["leader_name"], item["operator_name"],
                item["process_deadline"], item["issuer_type"], item["issuer_name"], item["currency"],
                item["original_amount"], item["cny_amount"], item["case_original_amount"],
                item["case_cny_amount"], item["line_status"], item["version_no"], item["recovery_status"],
                item["appeal_status"], item["problem_attribution"], item["diff_match_status"],
                item["investigation_note"], "", "", "", "", "", "", "", "", "",
            ])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="245FCE")
        for row in sheet.iter_rows(min_row=2):
            for index, cell in enumerate(row, 1):
                cell.protection = Protection(locked=index < 27)
        for column in (17, 18, 19, 20):
            for cell in sheet.iter_cols(min_col=column, max_col=column, min_row=2):
                for item in cell:
                    item.number_format = "#,##0.00"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(OPERATOR_HEADERS))}1"
        sheet.protection.sheet = True
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
                action = values[27]
                if not action:
                    continue
                if action and action not in OPERATOR_ACTIONS:
                    raise AdmError(f"第{row_number}行：本次处理动作无效")
                try:
                    version = int(values[21])
                except (TypeError, ValueError):
                    raise AdmError(f"第{row_number}行：数据版本无效") from None
                rows.append({
                    "rowNumber": row_number, "caseInternalNo": values[0], "admNo": values[1],
                    "lineInternalNo": values[2], "operatorName": values[11], "lineStatus": values[20],
                    "versionNo": version, "investigationNote": values[26], "action": action,
                    "recoveryDecision": values[28], "noRecoveryReason": values[29],
                    "recoveryConfirmation": values[30], "appealReason": values[31],
                    "appealTarget": values[32], "noAppealReason": values[33],
                    "problemAttribution": values[34], "resultNote": values[35],
                })
            if not rows:
                raise AdmError("Excel中没有填写任何处理动作或订单情况说明")
            return rows
        finally:
            workbook.close()


class StoredUpload:
    def __init__(self, path):
        self.filename = Path(path).name
        self.stream = Path(path).open("rb")

    def close(self):
        self.stream.close()
