from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from openpyxl import load_workbook

from data_report_api.services.admwf.excel import (
    AdmDailyWorkbook, HEADERS, OPERATOR_HEADERS, _operator_actions, _operator_stage,
)
from data_report_api.services.admwf.catalog import AdmCatalog
from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.service import AdmWorkflowService, _json_value
from data_report_api.services.comprehensive_export import ComprehensiveExportService


class Upload:
    def __init__(self, content, filename="adm.xlsx"):
        self.filename = filename
        self.stream = BytesIO(content)


class AdmDailyWorkbookTest(unittest.TestCase):
    def setUp(self):
        self.excel = AdmDailyWorkbook({"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024})
        self.diff_types = ["ADM-金额差异", "ADM-退票差异"]

    def workbook_bytes(self, rows):
        content = self.excel.template(self.diff_types)
        workbook = load_workbook(content)
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def test_import_template_is_delivered_by_common_export_task(self):
        with TemporaryDirectory() as root:
            service = ComprehensiveExportService({
                "COMPREHENSIVE_EXPORT_ROOT": root,
                "ADM_IMPORT_MAX_ROWS": 20,
                "ADM_IMPORT_MAX_BYTES": 1024 * 1024,
                "ADMWF_DIFF_TYPE_OPTIONS_RESOLVER": lambda _search, _limit: [
                    {"code": "ADM-金额差异", "name": "ADM-金额差异"},
                    {"code": "ADM-退票差异", "name": "ADM-退票差异"},
                ],
            })
            user = {
                "id": 1, "display_name": "负责人", "permissions": ["adm.create"],
                "menu_codes": ["adm.center"],
            }
            task = service.create_background(user, {"kind": "adm_import_template"})
            self.assertEqual(task["status"], "SUCCEEDED")
            self.assertEqual(task["taskLabel"], "ADM跨主单导入模板")
            path, name = service.download(user, task["id"])
            self.assertEqual(name, "ADM日常建单19列模板.xlsx")
            workbook = load_workbook(path, read_only=True)
            try:
                self.assertEqual(tuple(cell.value for cell in workbook.active[1]), HEADERS)
            finally:
                workbook.close()

    def test_template_has_exact_19_headers(self):
        workbook = load_workbook(self.excel.template(self.diff_types))
        self.assertEqual(tuple(cell.value for cell in workbook.active[1]), HEADERS)
        self.assertEqual(workbook.active.max_row, 3)
        self.assertTrue(str(workbook.active["A2"].value).startswith("【示例】"))
        self.assertEqual(workbook["填写选项"].sheet_state, "hidden")
        validations = list(workbook.active.data_validations.dataValidation)
        self.assertTrue(any(item.formula1 == "ADM_DIFF_TYPE_OPTIONS" for item in validations))
        workbook.close()

    def test_template_examples_are_ignored_when_real_rows_are_present(self):
        main = ["ADM-REAL-1", "航司", "CA", "CNY", 100, "2026-11-10", "2026-11-12 18:00:00", ""]
        line = ["", "", "", "CA", "999-1", "ABC123", 100, "业务部", "组长甲", "ADM-金额差异", "原因"]
        parsed = self.excel.parse(Upload(self.workbook_bytes([main + line])))
        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(parsed["rows"][0]["admNo"], "ADM-REAL-1")

    def test_parse_groups_same_adm_number_and_keeps_optional_blanks(self):
        main = ["ADM-1", "平台", "携程", "USD", 100, "2026-11-01", "2026-11-03 12:00:00", ""]
        line = ["", "", "", "", "", "", 50, "业务部", "组长甲", "AD01", "原因"]
        parsed = self.excel.parse(Upload(self.workbook_bytes([main + line, main + line])))
        self.assertEqual(len(parsed["groups"]), 1)
        self.assertEqual(len(parsed["groups"][0]), 2)
        self.assertEqual(parsed["groups"][0][0]["otaOrderNo"], "")

    def test_rejects_changed_header(self):
        content = self.excel.template(self.diff_types)
        workbook = load_workbook(content)
        workbook.active["A1"] = "被修改"
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        with self.assertRaises(AdmError):
            self.excel.parse(Upload(output.getvalue()))

    def test_preview_resolves_names_without_department_leader_membership_rule(self):
        class Catalog:
            def optional_master_value(self, kind, value):
                return {"code": f"{kind}-01", "name": value} if value else None

            def department_value(self, value):
                return {"code": "D01", "name": value}

            def user_value(self, value, leader=False):
                return {"id": 9, "name": value}

            def diff_type_value(self, value):
                return {"code": "AD01", "name": value}

            def fx(self, currency):
                return {"rateValue": "1", "sourceCode": 6, "exchangeUnit": 1,
                        "rateField": "central_parity_rate"}

        class Repository:
            def create_import_batch(self, *args, **kwargs):
                self.args, self.kwargs = args, kwargs
                return 17

        main = ["ADM-2", "航司", "MU", "CNY", 100, "2026-11-01", "2026-11-03 12:00:00", ""]
        line = ["", "", "", "", "", "", 100, "业务部", "不受部门限制的组长", "ADM-退票", "细分原因"]
        content = self.workbook_bytes([main + line])
        repository = Repository()
        with TemporaryDirectory() as root:
            service = AdmWorkflowService(
                {"ADM_IMPORT_ROOT": root, "ADM_IMPORT_MAX_ROWS": 20,
                 "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
                repository=repository, catalog=Catalog(),
            )
            result = service.preview_import(
                {"id": 1, "display_name": "负责人", "permissions": ["adm.create"]},
                Upload(content),
            )
        self.assertTrue(result["canCommit"])
        self.assertEqual(result["failedRows"], 0)
        self.assertEqual(repository.kwargs["total_rows"], 1)

    def test_preview_reports_missing_supplier_name_as_row_error(self):
        class Catalog:
            @staticmethod
            def optional_master_value(_kind, _value):
                return None

        class Repository:
            @staticmethod
            def create_import_batch(*_args, **_kwargs):
                return 18

        main = ["ADM-3", "供应商", "", "CNY", 100, "2026-11-10", "2026-11-12 18:00:00", ""]
        line = ["", "", "", "", "", "", 100, "业务部", "组长甲", "ADM-金额差异", "细分原因"]
        with TemporaryDirectory() as root:
            service = AdmWorkflowService(
                {"ADM_IMPORT_ROOT": root, "ADM_IMPORT_MAX_ROWS": 20,
                 "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
                repository=Repository(), catalog=Catalog(),
            )
            result = service.preview_import(
                {"id": 1, "display_name": "负责人", "permissions": ["adm.create"]},
                Upload(self.workbook_bytes([main + line])),
            )
        self.assertFalse(result["canCommit"])
        self.assertEqual(result["failedRows"], 1)
        self.assertEqual(result["groups"][0]["message"], "供应商类型的下发方名称不能为空")

    def test_operator_export_matches_34_column_business_template_and_state_actions(self):
        row = {
            "case_internal_no": "ADM-01", "adm_no": "ADM", "line_internal_no": "ADM-01-001",
            "ota_code": "OTA-01", "ota_name": "示例平台", "ota_order_no": None,
            "supplier_code": "SUP-01", "supplier_name": "示例供应商", "airline_name": None,
            "ticket_no": None, "pnr": None, "department_name": "业务部", "leader_name": "组长",
            "attachment_address": "/api/v1/adm/cases/1/attachments/2/preview",
            "operator_name": "操作员", "process_deadline": "2026-11-08 12:00:00",
            "issuer_type": "AIRLINE", "issuer_name": "MU", "currency": "CNY",
            "original_amount": 10, "cny_amount": 10, "case_original_amount": 10, "case_cny_amount": 10,
            "line_status": "PROCESSING", "version_no": 2, "recovery_status": "UNDECIDED",
            "appeal_status": "UNDECIDED", "problem_attribution": None,
            "diff_match_status": "NOT_REQUIRED", "investigation_note": None,
            "recovery_started_at": None,
            "latest_review_status": None, "latest_review_return_reason": None,
            "latest_appeal_reason": None, "latest_appeal_target": None,
            "latest_no_appeal_reason": None,
        }
        workbook = load_workbook(self.excel.operator_export([row]))
        self.assertEqual(tuple(cell.value for cell in workbook.active[1]), OPERATOR_HEADERS)
        self.assertEqual(len(OPERATOR_HEADERS), 34)
        self.assertEqual(OPERATOR_HEADERS[9], "附件地址")
        self.assertEqual(OPERATOR_HEADERS[21:23], ("数据版本", "原状态"))
        self.assertIn("系统主单ID", OPERATOR_HEADERS)
        self.assertEqual(workbook.active["A2"].value, "ADM-01")
        self.assertEqual(workbook.active["D2"].value, "OTA-01 / 示例平台")
        self.assertEqual(workbook.active["F2"].value, "SUP-01 / 示例供应商")
        self.assertEqual(workbook.active["V2"].value, 2)
        self.assertEqual(workbook.active["W2"].value, "待编码处理")
        formulas = [item.formula1 for item in workbook.active.data_validations.dataValidation]
        self.assertTrue(any("需要恢复编码" in formula for formula in formulas))
        self.assertTrue(any("仅补充订单资料" in formula for formula in formulas))
        self.assertTrue(any("平台问题" in formula for formula in formulas))
        self.assertFalse(workbook.active["D2"].protection.locked)
        for address in ("AC2", "AD2", "AE2", "AF2", "AH2"):
            self.assertFalse(workbook.active[address].protection.locked, address)
        self.assertTrue(workbook.active["J2"].protection.locked)
        self.assertEqual(workbook.active["J2"].fill.fgColor.rgb, "00F2F4F7")
        self.assertGreaterEqual(workbook.active.column_dimensions["J"].width, 30)
        self.assertFalse(workbook.active.protection.formatColumns)
        workbook.active["AB2"] = "暂不处理"
        output = BytesIO()
        workbook.save(output)
        self.assertTrue(workbook.active["A2"].protection.locked)
        workbook.close()
        parsed = self.excel.parse_operator_results(Upload(output.getvalue(), "operator.xlsx"))
        self.assertEqual(parsed[0]["attachmentAddress"], "/api/v1/adm/cases/1/attachments/2/preview")
        self.assertEqual(parsed[0]["action"], "暂不处理")

    def test_catalog_accepts_code_name_combination_for_ota_and_supplier(self):
        catalog = AdmCatalog({})
        calls = []

        def query(sql, params):
            calls.append((sql, params))
            if len(calls) in {1, 3}:
                return []
            return [{"code": params[0], "name": params[1]}]

        catalog._query_all = query
        self.assertEqual(
            catalog.optional_master_value("ota", "OTA-01 / 示例平台"),
            {"code": "OTA-01", "name": "示例平台"},
        )
        self.assertEqual(
            catalog.optional_master_value("supplier", "SUP-01/示例供应商"),
            {"code": "SUP-01", "name": "示例供应商"},
        )

    def test_returned_review_has_specific_page_and_excel_actions(self):
        supplement = {
            "latest_review_status": "RETURNED",
            "latest_review_return_reason": "【驳回补充材料】缺少行程单",
            "recovery_status": "CONFIRMED", "appeal_status": "FAILED",
        }
        reappeal = {
            "latest_review_status": "RETURNED",
            "latest_review_return_reason": "【驳回重新申诉】对象选择错误",
            "recovery_status": "CONFIRMED", "appeal_status": "UNDECIDED",
        }
        legacy = {
            "latest_review_status": "RETURNED", "latest_review_return_reason": "旧退回原因",
            "recovery_status": "CONFIRMED", "appeal_status": "FAILED",
        }
        self.assertEqual(_operator_stage(supplement), "驳回补充材料")
        self.assertEqual(_operator_actions(supplement), ["重新提交负责人审核", "仅补充订单资料", "暂不处理"])
        self.assertEqual(_operator_stage(reappeal), "驳回重新申诉")
        self.assertIn("提交申诉", _operator_actions(reappeal))
        self.assertEqual(_operator_stage(legacy), "驳回补充材料")
        self.assertEqual(_operator_actions(legacy), ["重新提交负责人审核", "仅补充订单资料", "暂不处理"])
        withdrawn = {
            "review_status": "WITHDRAWN", "latest_review_status": "APPROVED",
            "recovery_status": "NOT_REQUIRED", "appeal_status": "NO_APPEAL",
        }
        self.assertEqual(_operator_stage(withdrawn), "审核撤回待重提")
        self.assertEqual(_operator_actions(withdrawn), ["重新提交负责人审核", "仅补充订单资料", "暂不处理"])

    def test_recovery_stage_controls_later_action_options(self):
        undecided = {"recovery_status": "UNDECIDED", "appeal_status": "UNDECIDED"}
        waiting = {"recovery_status": "WAITING", "appeal_status": "UNDECIDED"}
        reminder = {"recovery_status": "REMINDER_DUE", "appeal_status": "UNDECIDED"}
        self.assertEqual(_operator_stage(undecided), "待编码处理")
        self.assertEqual(_operator_stage(waiting), "等待恢复编码")
        self.assertEqual(_operator_stage(reminder), "确认已查看并处理")
        for item in (waiting, reminder):
            self.assertIn("提交申诉", _operator_actions(item))
            self.assertIn("申诉成功", _operator_actions(item))
            self.assertIn("申诉失败", _operator_actions(item))

    def test_appeal_stage_matches_current_process(self):
        expected = {
            "UNDECIDED": "待决定",
            "IN_PROGRESS": "申诉中",
            "SUCCEEDED": "申诉成功",
            "FAILED": "申诉失败",
            "NO_APPEAL": "不申诉",
        }
        for appeal_status, value in expected.items():
            item = {"recovery_status": "NOT_REQUIRED", "appeal_status": appeal_status}
            self.assertEqual(_operator_stage(item), value)

        returned = {
            "latest_review_status": "RETURNED",
            "latest_review_return_reason": "【驳回补充材料】补充凭证",
            "recovery_status": "CONFIRMED", "appeal_status": "FAILED",
        }
        self.assertEqual(_operator_stage(returned), "驳回补充材料")

    def test_operator_import_persists_every_editable_business_field(self):
        context = {
            "id": 11, "case_id": 3, "case_internal_no": "ADM-03", "adm_no": "ADM-3",
            "line_internal_no": "ADM-03-001", "case_status": "ACTIVE", "line_status": "PROCESSING",
            "review_status": None, "latest_review_status": None, "latest_review_return_reason": None,
            "operator_id": 6, "operator_name": "陈艳", "version_no": 2,
            "ota_code": "OLD-OTA", "ota_name": "旧平台", "ota_order_no": "OLD-ORDER",
            "supplier_code": "OLD-SUP", "supplier_name": "旧供应商",
            "airline_code": "CA", "airline_name": "CA", "ticket_no": "OLD-TICKET", "pnr": "OLDPNR",
            "department_name": "业务部", "leader_name": "吴泽展", "process_deadline": "2026-11-12 18:00:00",
            "issuer_type": "SUPPLIER", "issuer_name": "下发方", "currency": "CNY",
            "original_amount": 10, "cny_amount": 10, "case_original_amount": 10, "case_cny_amount": 10,
            "recovery_status": "NOT_REQUIRED", "recovery_started_at": None,
            "appeal_status": "UNDECIDED", "problem_attribution": None,
            "diff_match_status": "PENDING", "investigation_note": None, "attachment_address": "",
            "latest_appeal_reason": None, "latest_appeal_target": None, "latest_no_appeal_reason": None,
        }

        class Repository:
            def __init__(self):
                self.calls = []

            def operator_import_context(self, _numbers):
                return {context["line_internal_no"]: context}

            def update_operator_supplement(self, case_id, line_id, actor, data):
                self.calls.append(("supplement", case_id, line_id, actor, data))

            def record_no_appeal(self, case_id, line_id, actor, reason, attribution):
                self.calls.append(("noAppeal", case_id, line_id, actor, reason, attribution))

            def submit_review(self, case_id, line_id, actor):
                self.calls.append(("submit", case_id, line_id, actor))

        class Catalog:
            @staticmethod
            def optional_master_value(kind, value):
                return {"code": f"{kind}-NEW", "name": value} if value else None

        exported = self.excel.operator_export([context])
        workbook = load_workbook(exported)
        sheet = workbook.active
        for cell, value in {
            "D2": "新平台", "E2": "NEW-ORDER", "F2": "新供应商", "G2": "MU",
            "H2": "NEW-TICKET", "I2": "NEWPNR", "AB2": "提交不申诉",
            "AE2": "确认不申诉", "AF2": "平台问题", "AH2": "补充后的问题说明",
        }.items():
            sheet[cell] = value
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        repository = Repository()
        service = AdmWorkflowService(
            {"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
            repository=repository, catalog=Catalog(),
        )
        result = service.import_operator_results(
            {"id": 6, "display_name": "陈艳", "permissions": ["adm.handle"]},
            Upload(output.getvalue(), "operator.xlsx"),
        )
        self.assertEqual(result["committed"], 1)
        supplement = next(call[4] for call in repository.calls if call[0] == "supplement")
        self.assertEqual(
            {key: supplement[key] for key in ("otaName", "otaOrderNo", "supplierName", "airlineName", "ticketNo", "pnr", "investigationNote")},
            {"otaName": "新平台", "otaOrderNo": "NEW-ORDER", "supplierName": "新供应商",
             "airlineName": "MU", "ticketNo": "NEW-TICKET", "pnr": "NEWPNR",
             "investigationNote": "补充后的问题说明"},
        )
        no_appeal = next(call for call in repository.calls if call[0] == "noAppeal")
        self.assertEqual(no_appeal[4:], ("确认不申诉", "PLATFORM"))
        self.assertTrue(any(call[0] == "submit" for call in repository.calls))

    def test_waiting_recovery_can_confirm_and_submit_success_in_one_import(self):
        context = {
            "id": 12, "case_id": 3, "case_internal_no": "ADM-03", "adm_no": "ADM-3",
            "line_internal_no": "ADM-03-002", "case_status": "ACTIVE", "line_status": "PROCESSING",
            "review_status": None, "latest_review_status": None, "latest_review_return_reason": None,
            "operator_id": 6, "operator_name": "陈艳", "version_no": 2,
            "ota_code": None, "ota_name": None, "ota_order_no": None,
            "supplier_code": None, "supplier_name": None, "airline_code": None, "airline_name": None,
            "ticket_no": None, "pnr": None, "department_name": "业务部", "leader_name": "吴泽展",
            "process_deadline": "2026-11-12 18:00:00", "issuer_type": "SUPPLIER",
            "issuer_name": "下发方", "currency": "CNY", "original_amount": 10, "cny_amount": 10,
            "case_original_amount": 10, "case_cny_amount": 10, "recovery_status": "WAITING",
            "recovery_started_at": "2026-11-10 10:00:00", "appeal_status": "UNDECIDED",
            "problem_attribution": None, "diff_match_status": "NOT_REQUIRED", "investigation_note": None,
            "attachment_address": "", "latest_appeal_reason": None, "latest_appeal_target": None,
            "latest_no_appeal_reason": None,
        }

        class Repository:
            def __init__(self): self.calls = []
            def operator_import_context(self, _numbers): return {context["line_internal_no"]: context}
            def update_operator_supplement(self, *args): self.calls.append(("supplement", *args))
            def confirm_recovery(self, *args): self.calls.append(("confirm", *args))
            def start_appeal(self, *args): self.calls.append(("start", *args))
            def finish_appeal(self, *args, **kwargs): self.calls.append(("finish", *args, kwargs))
            def submit_review(self, *args): self.calls.append(("submit", *args))

        class Catalog:
            @staticmethod
            def optional_master_value(kind, value):
                return {"code": f"{kind}-NEW", "name": value} if value else None

        workbook = load_workbook(self.excel.operator_export([context]))
        sheet = workbook.active
        self.assertFalse(sheet["AA2"].protection.locked)
        sheet["AB2"], sheet["AC2"], sheet["AD2"] = "申诉成功", "航司确认撤销", "航司"
        output = BytesIO(); workbook.save(output); workbook.close()
        # The 48-hour reminder may become due after export. It must not invalidate
        # an otherwise unchanged WAITING workbook because reminder time is not a gate.
        context["recovery_status"] = "REMINDER_DUE"
        repository = Repository()
        service = AdmWorkflowService(
            {"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
            repository=repository, catalog=Catalog(),
        )
        result = service.import_operator_results(
            {"id": 6, "display_name": "陈艳", "permissions": ["adm.handle"]},
            Upload(output.getvalue(), "operator.xlsx"),
        )
        self.assertEqual(result["committed"], 1)
        self.assertEqual([item[0] for item in repository.calls], ["confirm", "start", "finish", "submit"])

        workbook = load_workbook(self.excel.operator_export([context]))
        workbook.active["D2"] = "新平台"
        output = BytesIO(); workbook.save(output); workbook.close()
        repository = Repository()
        service = AdmWorkflowService(
            {"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
            repository=repository, catalog=Catalog(),
        )
        result = service.import_operator_results(
            {"id": 6, "display_name": "陈艳", "permissions": ["adm.handle"]},
            Upload(output.getvalue(), "operator.xlsx"),
        )
        self.assertEqual(result["committed"], 1)
        self.assertEqual([item[0] for item in repository.calls], ["supplement"])

    def test_undecided_recovery_can_be_started_confirmed_and_finished_in_one_import(self):
        context = {
            "id": 13, "case_id": 4, "case_internal_no": "ADM-04", "adm_no": "ADM-4",
            "line_internal_no": "ADM-04-001", "case_status": "ACTIVE", "line_status": "PROCESSING",
            "review_status": None, "latest_review_status": None, "latest_review_return_reason": None,
            "operator_id": 6, "operator_name": "陈艳", "version_no": 1,
            "ota_code": None, "ota_name": None, "ota_order_no": None,
            "supplier_code": None, "supplier_name": None, "airline_code": None, "airline_name": None,
            "ticket_no": None, "pnr": None, "department_name": "业务部", "leader_name": "吴泽展",
            "process_deadline": "2026-11-12 18:00:00", "issuer_type": "SUPPLIER",
            "issuer_name": "下发方", "currency": "CNY", "original_amount": 10, "cny_amount": 10,
            "case_original_amount": 10, "case_cny_amount": 10, "recovery_status": "UNDECIDED",
            "recovery_started_at": None, "appeal_status": "UNDECIDED", "problem_attribution": None,
            "diff_match_status": "NOT_REQUIRED", "investigation_note": None, "attachment_address": "",
            "latest_appeal_reason": None, "latest_appeal_target": None, "latest_no_appeal_reason": None,
        }

        class Repository:
            def __init__(self): self.calls = []
            def operator_import_context(self, _numbers): return {context["line_internal_no"]: context}
            def decide_recovery(self, *args, **kwargs): self.calls.append(("decide", *args, kwargs))
            def confirm_recovery(self, *args): self.calls.append(("confirm", *args))
            def start_appeal(self, *args): self.calls.append(("start", *args))
            def finish_appeal(self, *args, **kwargs): self.calls.append(("finish", *args, kwargs))
            def submit_review(self, *args): self.calls.append(("submit", *args))

        class Catalog:
            @staticmethod
            def optional_master_value(_kind, _value): return None

        workbook = load_workbook(self.excel.operator_export([context]))
        sheet = workbook.active
        sheet["X2"] = "需要恢复编码"
        sheet["AB2"], sheet["AC2"], sheet["AD2"], sheet["AF2"] = (
            "申诉失败", "航司拒绝撤销", "航司", "平台问题",
        )
        output = BytesIO(); workbook.save(output); workbook.close()
        repository = Repository()
        service = AdmWorkflowService(
            {"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024},
            repository=repository, catalog=Catalog(),
        )
        result = service.import_operator_results(
            {"id": 6, "display_name": "陈艳", "permissions": ["adm.handle"]},
            Upload(output.getvalue(), "operator.xlsx"),
        )
        self.assertEqual(result["committed"], 1)
        self.assertEqual(
            [item[0] for item in repository.calls],
            ["decide", "confirm", "start", "finish", "submit"],
        )

    def test_legacy_source_payload_preserves_original_field_names_and_zero(self):
        value = _json_value({"legacy_source": {"source_payload": {"adm_no": "OLD-1", "total_amount_cny": 0}}})
        self.assertEqual(value["legacySource"]["sourcePayload"]["adm_no"], "OLD-1")
        self.assertEqual(value["legacySource"]["sourcePayload"]["total_amount_cny"], 0)


if __name__ == "__main__":
    unittest.main()
