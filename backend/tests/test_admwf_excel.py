from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from openpyxl import load_workbook

from data_report_api.services.admwf.excel import AdmDailyWorkbook, HEADERS, OPERATOR_HEADERS
from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.service import AdmWorkflowService


class Upload:
    def __init__(self, content, filename="adm.xlsx"):
        self.filename = filename
        self.stream = BytesIO(content)


class AdmDailyWorkbookTest(unittest.TestCase):
    def setUp(self):
        self.excel = AdmDailyWorkbook({"ADM_IMPORT_MAX_ROWS": 20, "ADM_IMPORT_MAX_BYTES": 1024 * 1024})

    def workbook_bytes(self, rows):
        content = self.excel.template()
        workbook = load_workbook(content)
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def test_template_has_exact_19_headers(self):
        workbook = load_workbook(self.excel.template(), read_only=True)
        self.assertEqual(tuple(cell.value for cell in workbook.active[1]), HEADERS)
        workbook.close()

    def test_parse_groups_same_adm_number_and_keeps_optional_blanks(self):
        main = ["ADM-1", "平台", "携程", "USD", 100, "2026-11-01", "2026-11-03 12:00:00", ""]
        line = ["", "", "", "", "", "", 50, "业务部", "组长甲", "AD01", "原因"]
        parsed = self.excel.parse(Upload(self.workbook_bytes([main + line, main + line])))
        self.assertEqual(len(parsed["groups"]), 1)
        self.assertEqual(len(parsed["groups"][0]), 2)
        self.assertEqual(parsed["groups"][0][0]["otaOrderNo"], "")

    def test_rejects_changed_header(self):
        content = self.excel.template()
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

    def test_operator_export_uses_business_numbers_not_technical_ids(self):
        row = {
            "case_internal_no": "ADM-01", "adm_no": "ADM", "line_internal_no": "ADM-01-001",
            "ota_name": None, "ota_order_no": None, "supplier_name": None, "airline_name": None,
            "ticket_no": None, "pnr": None, "department_name": "业务部", "leader_name": "组长",
            "operator_name": "操作员", "process_deadline": "2026-11-08 12:00:00",
            "issuer_type": "AIRLINE", "issuer_name": "MU", "currency": "CNY",
            "original_amount": 10, "cny_amount": 10, "case_original_amount": 10, "case_cny_amount": 10,
            "line_status": "PROCESSING", "version_no": 2, "recovery_status": "UNDECIDED",
            "appeal_status": "UNDECIDED", "problem_attribution": None,
            "diff_match_status": "NOT_REQUIRED", "investigation_note": None,
        }
        workbook = load_workbook(self.excel.operator_export([row]), read_only=True)
        self.assertEqual(tuple(cell.value for cell in workbook.active[1]), OPERATOR_HEADERS)
        self.assertNotIn("系统主单ID", OPERATOR_HEADERS)
        self.assertEqual(workbook.active["A2"].value, "ADM-01")
        workbook.close()


if __name__ == "__main__":
    unittest.main()
