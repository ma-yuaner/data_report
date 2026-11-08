from decimal import Decimal
import unittest

from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.service import AdmWorkflowService
from data_report_api.services.admwf.workflow import (
    closure_blockers,
    difference_query_key,
    status_after_approval,
    validate_submit,
)


class AdmWorkflowStateTest(unittest.TestCase):
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

    def test_failed_appeal_is_blocked_by_diff_before_collection(self):
        status = status_after_approval(
            appeal_status="FAILED", diff_match_status="NOT_MATCHED", collection_required=True,
            expected_collection_amount=Decimal("100"), collected_amount=Decimal("0"),
        )
        self.assertEqual(status, "WAITING_DIFF")

    def test_matched_diff_then_waits_for_exact_collection(self):
        self.assertEqual(status_after_approval(
            appeal_status="NO_APPEAL", diff_match_status="MATCHED_OTA_ORDER", collection_required=True,
            expected_collection_amount="100", collected_amount="99.99",
        ), "WAITING_COLLECTION")
        self.assertEqual(status_after_approval(
            appeal_status="NO_APPEAL", diff_match_status="MATCHED_OTA_ORDER", collection_required=True,
            expected_collection_amount="100", collected_amount="100",
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

    def test_under_or_over_collection_does_not_complete(self):
        for collected in ("99.99", "100.01"):
            with self.subTest(collected=collected):
                self.assertEqual(status_after_approval(
                    appeal_status="NO_APPEAL", diff_match_status="MATCHED_LINE_INTERNAL_NO",
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
