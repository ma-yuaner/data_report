from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from openpyxl import load_workbook
from data_report_api.services.admwf.excel import AdmMasterWorkbook, MASTER_HEADERS
from data_report_api.services.admwf.service import AdmWorkflowService
from data_report_api.services.admwf.policy import AdmError

class Upload:
    filename = "masters.xlsx"
    def __init__(self, content): self.stream = BytesIO(content)

class Catalog:
    def options(self, kind, search="", limit=200):
        return [{"code":"CI","name":"中华航空","ticketingCode":"297"}] if kind == "airline" else [{"code":"S1","name":"供应商甲"}]
    def optional_master(self, kind, code):
        return next(row for row in self.options(kind) if row["code"] == code)
    def user_value(self, value, leader=False): return {"id":3,"name":value}
    def user(self, value, leader=False): return {"id":3,"name":"组长甲"}
    def fx(self, currency):
        return {"rateValue":"1","sourceCode":6,"exchangeUnit":1,"rateField":"central_parity_rate"}

class MasterImportTest(unittest.TestCase):
    def setUp(self): self.excel = AdmMasterWorkbook({"ADM_IMPORT_MAX_ROWS":20})
    def row(self): return ["6007100530","航司","","CI（297）","297-1234567890","票务","其他","CNY","100","2026-11-13","2026-11-20 18:00:00","组长甲","","原因说明",""]
    def content(self, rows):
        book = load_workbook(self.excel.template())
        self.assertEqual(tuple(cell.value for cell in book.active[1]), MASTER_HEADERS)
        for row in rows: book.active.append(row)
        result = BytesIO(); book.save(result); book.close(); return result.getvalue()
    def test_roundtrip_one_row_one_master_without_details(self):
        content = self.content([self.row()])
        parsed = self.excel.parse(Upload(content))
        self.assertEqual(parsed["templateVersion"],"MASTER15_V2")
        service = AdmWorkflowService({}, repository=object(), catalog=Catalog())
        bodies, errors, _ = service._validate_import(parsed)
        self.assertFalse(errors)
        self.assertTrue(bodies[0]["masterOnly"])
        self.assertNotIn("lines",bodies[0])
        data, _, master = service._prepare_create_case(bodies[0],"EXCEL")
        self.assertTrue(master)
        self.assertEqual(data["lines"],[])
        self.assertEqual(data["lineDefaults"]["masterIntake"]["ticketingCode"],"297")
        self.assertEqual(data["lineDefaults"]["departmentCode"],"")
    def test_duplicate_master_and_formula_rejected(self):
        with self.assertRaisesRegex(AdmError,"重复"): self.excel.parse(Upload(self.content([self.row(),self.row()])))
        row=self.row();row[8]="=1+2"
        with self.assertRaisesRegex(AdmError,"公式"): self.excel.parse(Upload(self.content([row])))
    def test_required_penalty_and_supplier_and_optional_diff_type(self):
        service=AdmWorkflowService({},repository=object(),catalog=Catalog())
        for index, value, message in [(6,"","罚单"),(1,"供应商","供应商"),(3,"XX（123）","航司")]:
            row=self.row();row[index]=value
            parsed=self.excel.parse(Upload(self.content([row])))
            _, errors, _=service._validate_import(parsed)
            self.assertTrue(errors)
            self.assertIn(message,errors[0]["message"])
    def test_preview_commit_counts_masters_and_passes_no_lines(self):
        class Repository:
            def create_import_batch(self, no, name, digest, actor, **kwargs):
                self.batch={"id":1,"batch_no":no,"file_sha256":digest,"imported_by_id":actor["id"],"status":"PREVIEWED","failed_rows":0,"total_rows":1};return 1
            def get_import_batch(self,no): return self.batch
            def claim_import_batch(self,id): pass
            def create_case(self,data,fx,actor,**kwargs):
                self.created=data
                return {"case":{"id":1,"internal_no":"INTERNAL","adm_no":data["admNo"]},"lines":[]}
            def finish_import_batch(self,id,**kwargs): self.finished=kwargs
        with TemporaryDirectory() as root:
            repo=Repository();service=AdmWorkflowService({"ADM_IMPORT_ROOT":root},repository=repo,catalog=Catalog())
            user={"id":1,"permissions":["adm.create"]}
            preview=service.preview_import(user,Upload(self.content([self.row()])))
            self.assertTrue(preview["canCommit"])
            result=service.commit_import(user,preview["batchNo"])
            self.assertEqual(result["successRows"],1)
            self.assertEqual(result["cases"][0]["lineCount"],0)
            self.assertEqual(repo.created["lines"],[])
            self.assertIn("masterIntake",repo.created["lineDefaults"])
