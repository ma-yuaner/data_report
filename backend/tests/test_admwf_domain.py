from decimal import Decimal
import unittest

from data_report_api.services.admwf.domain import allocate_cny_amounts, normalize_create
from data_report_api.services.admwf.policy import AdmError


def valid_body():
    return {
        "admNo": "ADM/001", "issuerType": "AIRLINE", "issuerName": "测试航司",
        "currency": "USD", "originalAmount": "100.00", "issuedDate": "2026-11-07",
        "replyDeadline": "2026-11-08 18:00:00", "remark": "",
        "lines": [
            {"originalAmount": "40", "departmentCode": "D1", "departmentName": "票务部",
             "leaderId": 7, "leaderName": "组长A", "diffTypeCode": "T1",
             "diffTypeName": "金额差异", "differenceReason": "原因1"},
            {"originalAmount": "60", "departmentCode": "D2", "departmentName": "客服部",
             "leaderId": 8, "leaderName": "组长B", "diffTypeCode": "T2",
             "diffTypeName": "退票差异", "differenceReason": "原因2"},
        ],
    }


class AdmWorkflowDomainTest(unittest.TestCase):
    def test_cny_residual_is_assigned_to_last_non_zero_line(self):
        total, lines = allocate_cny_amounts(
            [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")], Decimal("0.50"),
        )
        self.assertEqual(total, Decimal("0.02"))
        self.assertEqual(lines, [Decimal("0.01"), Decimal("0.01"), Decimal("0.00")])
        self.assertEqual(sum(lines), total)

    def test_master_cny_is_converted_once_and_lines_match_it(self):
        body = valid_body()
        body["originalAmount"] = "0.03"
        body["lines"][0]["originalAmount"] = "0.01"
        body["lines"][1]["originalAmount"] = "0.02"
        result = normalize_create(body, Decimal("0.50"))
        self.assertEqual(result["cnyAmount"], Decimal("0.02"))
        self.assertEqual(sum(line["cnyAmount"] for line in result["lines"]), result["cnyAmount"])

    def test_confirmed_central_parity_rate_is_already_per_one_currency_unit(self):
        body = valid_body()
        body["originalAmount"] = "100.00"
        body["lines"][0]["originalAmount"] = "100.00"
        body["lines"][1]["originalAmount"] = "0.00"
        result = normalize_create(body, "4.80")
        self.assertEqual(result["lines"][0]["cnyAmount"], Decimal("480.00"))

    def test_normalize_create_allows_six_optional_order_fields_to_be_empty(self):
        result = normalize_create(valid_body(), Decimal("6.701347"))
        self.assertEqual(result["originalAmount"], Decimal("100.00"))
        self.assertEqual(result["cnyAmount"], Decimal("670.13"))
        self.assertIsNone(result["lines"][0]["otaOrderNo"])
        self.assertIsNone(result["lines"][0]["ticketNo"])
        self.assertIsNone(result["lines"][0]["pnr"])

    def test_normalize_create_rejects_unbalanced_amount_even_for_draft(self):
        body = valid_body()
        body["lines"][1]["originalAmount"] = "59.99"
        with self.assertRaisesRegex(AdmError, "明细原币金额之和"):
            normalize_create(body, Decimal("6.701347"))
