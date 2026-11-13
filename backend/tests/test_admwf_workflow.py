from decimal import Decimal
import unittest

from data_report_api.services.admwf.catalog import AdmCatalog
from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.repository import AdmWorkflowRepository
from data_report_api.services.admwf.service import AdmWorkflowService
from data_report_api.services.admwf.workflow import (
    closure_blockers,
    difference_query_key,
    status_after_approval,
    validate_submit,
)


class AdmWorkflowStateTest(unittest.TestCase):
    def test_currency_options_come_from_reference_source_and_keep_cny(self):
        catalog = AdmCatalog({
            "ADMWF_CURRENCY_OPTIONS_RESOLVER": lambda search, limit: [
                {"code": "usd", "name": "usd"},
                {"code": "aud", "name": "aud"},
            ],
        })
        self.assertEqual(
            catalog.options("currency"),
            [
                {"code": "CNY", "name": "CNY"},
                {"code": "USD", "name": "USD"},
                {"code": "AUD", "name": "AUD"},
            ],
        )

    def test_assigned_owner_actions_do_not_allow_unassigned_admin_override(self):
        class Repository:
            @staticmethod
            def get_case(case_id):
                return {"case": {"coordinator_id": 7}}

        service = AdmWorkflowService({}, repository=Repository(), catalog=object())
        with self.assertRaisesRegex(AdmError, "只有该主单ADM负责人"):
            service._assigned_owner_actor(
                {"id": 8, "is_admin": True, "permissions": ["adm.review"]},
                1,
                "更换组长",
                "adm.review",
            )

    def test_workbench_scope_is_personal_even_for_admin_capabilities(self):
        conditions, values = AdmWorkflowRepository._workbench_scope(6, {
            "assignLeader": True,
            "assignOperator": True,
            "handle": True,
            "review": True,
            "diffMatch": True,
            "collection": True,
        })
        clause = " OR ".join(conditions)
        self.assertIn("c.coordinator_id=%s", clause)
        self.assertIn("l.leader_id=%s", clause)
        self.assertIn("l.operator_id=%s", clause)
        self.assertNotIn("1=1", clause)
        self.assertEqual(values.count(6), 3)

    def test_exchange_rate_preview_uses_catalog_and_serializes_decimal(self):
        class Catalog:
            def fx(self, currency):
                self.currency = currency
                return {"rateValue": Decimal("6.70134700"), "exchangeUnit": 100}

        catalog = Catalog()
        service = AdmWorkflowService({}, repository=object(), catalog=catalog)
        result = service.exchange_rate({"id": 1, "permissions": ["adm.view"]}, "usd")
        self.assertEqual(catalog.currency, "USD")
        self.assertEqual(result["rateValue"], "6.70134700")

    def test_review_collection_choice_only_applies_to_successful_appeal(self):
        class Repository:
            def __init__(self, appeal_status): self.appeal_status = appeal_status; self.called = None
            def get_case(self, _case_id):
                return {"case": {"coordinator_id": 7}, "lines": [{"id": 9, "appeal_status": self.appeal_status}]}
            def decide_review(self, *args, **kwargs): self.called = (args, kwargs); return {"ok": True}

        user = {"id": 7, "display_name": "负责人", "permissions": ["adm.review"]}
        repository = Repository("SUCCEEDED")
        service = AdmWorkflowService({}, repository=repository, catalog=object())
        with self.assertRaises(AdmError):
            service.decide_review(user, 1, 9, {"result": "APPROVED"})
        service.decide_review(user, 1, 9, {
            "result": "APPROVED", "collectionRequired": True, "expectedCollectionAmount": "100",
        })
        self.assertTrue(repository.called[1]["collection_required"])

        repository = Repository("FAILED")
        service = AdmWorkflowService({}, repository=repository, catalog=object())
        with self.assertRaises(AdmError):
            service.decide_review(user, 1, 9, {
                "result": "APPROVED", "collectionRequired": True, "expectedCollectionAmount": "100",
            })
        service.decide_review(user, 1, 9, {"result": "APPROVED"})
        self.assertFalse(repository.called[1]["collection_required"])

    def test_failed_appeal_is_blocked_by_diff_before_collection(self):
        status = status_after_approval(
            appeal_status="FAILED", diff_match_status="NOT_MATCHED", collection_required=True,
            expected_collection_amount=Decimal("100"), collected_amount=Decimal("0"),
        )
        self.assertEqual(status, "WAITING_DIFF")

    def test_matched_diff_completes_without_collection_branch(self):
        self.assertEqual(status_after_approval(
            appeal_status="NO_APPEAL", diff_match_status="MATCHED_OTA_ORDER", collection_required=True,
            expected_collection_amount="100", collected_amount="99.99",
        ), "COMPLETED")
        self.assertEqual(status_after_approval(
            appeal_status="FAILED", diff_match_status="MATCHED_OTA_ORDER", collection_required=False,
            expected_collection_amount=None, collected_amount="0",
        ), "COMPLETED")

    def test_difference_query_key_uses_ota_first(self):
        self.assertEqual(difference_query_key(
            source_type="LEGACY", ota_order_no="OTA-1", adm_no="ADM-1",
            line_internal_no="ADM-1-01-001",
        )["keyType"], "OTA_ORDER_NO")

    def test_legacy_without_ota_uses_original_adm_no(self):
        result = difference_query_key(
            source_type="LEGACY", ota_order_no=None, adm_no="ADM-OLD",
            line_internal_no="ADM-OLD-01-001",
        )
        self.assertEqual(result["keyValue"], "ADM-OLD")
        self.assertEqual(result["matchedStatus"], "MATCHED_LEGACY_ADM_NO")

    def test_new_manual_and_excel_without_ota_use_line_internal_no(self):
        for source_type in ("MANUAL", "EXCEL"):
            with self.subTest(source_type=source_type):
                result = difference_query_key(
                    source_type=source_type, ota_order_no="", adm_no="ADM-NEW",
                    line_internal_no="ADM-NEW-01-002",
                )
                self.assertEqual(result["keyValue"], "ADM-NEW-01-002")
                self.assertEqual(result["matchedStatus"], "MATCHED_LINE_INTERNAL_NO")

    def test_successful_appeal_does_not_require_diff_or_collection(self):
        self.assertEqual(status_after_approval(
            appeal_status="SUCCEEDED", diff_match_status="NOT_REQUIRED", collection_required=False,
            expected_collection_amount=None, collected_amount="0",
        ), "COMPLETED")

    def test_successful_appeal_waits_for_required_collection(self):
        self.assertEqual(status_after_approval(
            appeal_status="SUCCEEDED", diff_match_status="NOT_REQUIRED", collection_required=True,
            expected_collection_amount="100", collected_amount="0",
        ), "WAITING_COLLECTION")
        self.assertEqual(status_after_approval(
            appeal_status="SUCCEEDED", diff_match_status="NOT_REQUIRED", collection_required=True,
            expected_collection_amount="100", collected_amount="100",
        ), "COMPLETED")

    def test_successful_appeal_under_or_over_collection_does_not_complete(self):
        for collected in ("99.99", "100.01"):
            with self.subTest(collected=collected):
                self.assertEqual(status_after_approval(
                    appeal_status="SUCCEEDED", diff_match_status="NOT_REQUIRED",
                    collection_required=True, expected_collection_amount="100", collected_amount=collected,
                ), "WAITING_COLLECTION")

    def test_submit_requires_attribution_after_failure(self):
        with self.assertRaises(AdmError):
            validate_submit("NOT_REQUIRED", "FAILED", None)

    def test_voided_line_does_not_block_close(self):
        lines = [
            {"id": 1, "line_internal_no": "A-001", "line_status": "COMPLETED"},
            {"id": 2, "line_internal_no": "A-002", "line_status": "VOIDED"},
            {"id": 3, "line_internal_no": "A-003", "line_status": "PROCESSING"},
        ]
        self.assertEqual([item["lineId"] for item in closure_blockers(lines)], [3])


class AdmMaterialConfirmationTest(unittest.TestCase):
    def connection(self, confirmed, amounts):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                import sqlite3
                with sqlite3.connect(":memory:") as db:
                    db.execute("CREATE TABLE admwf_operation_log(id INTEGER,line_id INTEGER,event_type TEXT,operation_note TEXT)")
                    db.execute("CREATE TABLE admwf_case_line(case_id INTEGER,line_status TEXT,original_amount DECIMAL)")
                    db.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), params)
                self.sql = sql
            def fetchone(self): return {"id": 1} if confirmed else None
            def fetchall(self): return [{"original_amount": Decimal(v)} for v in amounts]
        class Connection:
            def cursor(self): return Cursor()
        return Connection()

    def test_dispatch_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(AdmError, "已补充资料"):
            AdmWorkflowRepository._require_line_ready(self.connection(False, ["100"]),
                {"id": 1, "master_recovery_status": "RECOVERED", "original_amount": Decimal("100")}, {"id": 2})

    def test_confirmation_allows_optional_fields_when_total_matches(self):
        AdmWorkflowRepository._require_line_ready(self.connection(True, ["100", "0"]),
            {"id": 1, "master_recovery_status": "RECOVERED", "original_amount": Decimal("100")}, {"id": 2})

    def test_confirmation_does_not_bypass_total_check(self):
        with self.assertRaisesRegex(AdmError, "合计"):
            AdmWorkflowRepository._require_line_ready(self.connection(True, ["99"]),
                {"id": 1, "master_recovery_status": "RECOVERED", "original_amount": Decimal("100")}, {"id": 2})


class AdmMaterialSqlContractTest(unittest.TestCase):
    def test_detail_confirmation_queries_use_real_log_column(self):
        import ast
        import inspect
        import sqlite3
        import textwrap
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
            CREATE TABLE admwf_case_line(id INTEGER,case_id INTEGER,line_no INTEGER);
            CREATE TABLE admwf_operation_log(id INTEGER,line_id INTEGER,event_type TEXT,operation_note TEXT);
            INSERT INTO admwf_case_line VALUES(2,1,1);
            INSERT INTO admwf_operation_log VALUES(1,2,'UPDATE_LINE_BASIC_INFO','资料已确认');
        """)
        for method in [AdmWorkflowRepository.get_case, AdmWorkflowRepository.get_case_summary]:
            tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
            query = next(node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value.startswith("SELECT l.*") and "material_confirmed" in node.value)
            with self.subTest(method=method.__name__):
                self.assertEqual(db.execute(query.replace("%s", "?"), (1,)).fetchone()[-1], 1)


class AdmMasterRecoveryRoutingTest(unittest.TestCase):
    def repository(self, state="LEADER_DECISION", locators=None):
        from contextlib import nullcontext
        from data_report_api.services.admwf.policy import business_now
        case = {"id": 1, "case_status": "ACTIVE", "master_recovery_status": state,
                "coordinator_id": 9, "line_defaults_json": {"leaderId": 2},
                "created_at": business_now(), "leader_first_action_at": business_now(),
                "recovery_locators": locators}
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                if sql.startswith("UPDATE admwf_case SET master_recovery_status"):
                    case["master_recovery_status"] = params[0]
                    case["recovery_locators"] = params[1] or case["recovery_locators"]
                    case["master_recovery_due_at"] = params[2]
            def fetchone(self): return case
        class Connection:
            def cursor(self): return Cursor()
        repo = AdmWorkflowRepository({})
        repo.transaction = lambda: nullcontext(Connection())
        repo._next_event_no = lambda *args: 1
        repo.append_operation_log = lambda *args, **kwargs: None
        repo.get_case = lambda *args, **kwargs: {"case": case}
        repo.add_line = lambda *args, **kwargs: {"case": case, "lineAdded": True}
        return repo

    def test_needed_carries_locators_to_owner_before_countdown(self):
        repo = self.repository()
        result = repo.master_recovery(1, "request", {"id": 2, "name": "leader"}, locators="1G-5S75-ABC123,1A-BKK247-DEF456")
        self.assertEqual(result["case"]["master_recovery_status"], "OWNER_RECOVERY")
        self.assertEqual(result["case"]["recovery_locators"], "1G-5S75-ABC123,1A-BKK247-DEF456")
        self.assertIsNone(result["case"]["master_recovery_due_at"])

    def test_skip_adds_order_without_owner_recovery(self):
        result = self.repository().master_recovery(1, "skip", {"id": 2, "name": "leader"}, locators="1G-5S75-ABC123", line={"pnr": "ABC123"})
        self.assertEqual(result["case"]["master_recovery_status"], "NOT_REQUIRED")
        self.assertTrue(result["lineAdded"])
        self.assertIsNone(result["case"]["master_recovery_due_at"])

    def test_owner_starts_only_with_saved_locators(self):
        repo = self.repository("OWNER_RECOVERY", "1G-5S75-ABC123")
        result = repo.master_recovery(1, "start", {"id": 9, "name": "owner"})
        self.assertEqual(result["case"]["master_recovery_status"], "RECOVERING")
        self.assertEqual(result["case"]["recovery_locators"], "1G-5S75-ABC123")
        self.assertIsNotNone(result["case"]["master_recovery_due_at"])
        with self.assertRaisesRegex(AdmError, "缺少"):
            self.repository("OWNER_RECOVERY").master_recovery(1, "start", {"id": 9, "name": "owner"})
