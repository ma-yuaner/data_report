"""Offline tests of ADS coverage, nullable money, filters, and API boundaries."""
import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import comprehensive_analysis as module


def fact(
    business="issue", count=3, known="12.1234", missing=0, platform="P1",
    product="普通", policy="政策员甲", day="2026-09-18", key="row1",
    segments=5, segment_missing=0,
):
    return {
        **dict.fromkeys(module.COLUMNS), "row_key": key, "dt": day, "business_date": day,
        "row_type": "data", "business_type": business, "ota_code": platform, "ota_cname": platform,
        "ota_site_code": "S1", "ota_site_cname": "站点一", "airline_code": "HO",
        "ticket_product_raw": product, "policy_operator": policy,
        "business_count": count, "profit_missing_count": missing,
        "segment_count": segments if business in ("issue", "ancillary") else None,
        "segment_missing_count": segment_missing if business in ("issue", "ancillary") else None,
        "known_profit_cny": Decimal(known) if known is not None else None,
        "estimated_profit_cny": Decimal(known) if missing == 0 and known is not None else None,
        "metric_version": "v1", "etl_run_id": "run1", "etl_updated_at": "2026-09-18 16:29:17",
    }


def snapshot(data=(), day=None):
    rows = list(copy.deepcopy(data))
    snapshot_day = day or (rows[0]["dt"] if rows else "2026-09-18")
    for business in module.BUSINESSES:
        selected = [row for row in rows if row["business_type"] == business]
        marker = fact(business=business, day=snapshot_day, key="coverage-" + business)
        marker.update(row_type="coverage", business_count=None, known_profit_cny=None, estimated_profit_cny=None,
                      segment_count=None, segment_missing_count=None,
                      source_row_count=sum(row["business_count"] for row in selected),
                      profit_missing_count=sum(row["profit_missing_count"] for row in selected))
        rows.append(marker)
    return rows


class ComprehensiveTests(unittest.TestCase):
    def setUp(self):
        self.source = MagicMock()
        self.source.database = "sibebid"
        self.connection = self.source.connect.return_value
        self.cursor = self.connection.cursor.return_value
        self.source_patch = patch.object(module, "DataSource", return_value=self.source)
        self.source_patch.start()
        self.log_patch = patch.object(module.logging.getLogger(module.__name__), "exception")
        self.log_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.addCleanup(self.log_patch.stop)

    def analysis(self, rows, **kwargs):
        self.cursor.fetchmany.return_value = [tuple(row.get(column) for column in module.COLUMNS) for row in rows]
        return module.ComprehensiveAnalysisService({"DATA_MODE": "mysql"}).analysis("2026-09-18", "2026-09-18", **kwargs)

    def test_real_counts_and_decimal_total(self):
        result = self.analysis(snapshot([fact(), fact("refund", 2, "-0.1234", key="r2")]))
        self.assertTrue(result["available"])
        self.assertEqual(result["totalProfit"], "12.0000")
        self.assertEqual(result["metrics"]["issue"]["count"], 3)
        self.assertEqual(result["metrics"]["issue"]["segmentCount"], 5)
        self.assertEqual(result["metrics"]["issue"]["segmentMissingCount"], 0)
        self.assertEqual(result["metrics"]["refund"]["count"], 2)
        self.assertEqual(result["trend"][0]["totalProfit"], result["totalProfit"])
        self.assertEqual(result["comparison"][0]["totalProfit"], result["totalProfit"])

    def test_four_covered_zero_businesses_are_real_zero(self):
        result = self.analysis(snapshot())
        self.assertTrue(result["available"])
        self.assertEqual(result["totalProfit"], "0")
        self.assertEqual(result["metrics"]["ancillary"]["count"], 0)

    def test_absent_partition_is_not_zero(self):
        result = self.analysis([])
        self.assertFalse(result["available"])
        self.assertEqual(result["coverage"]["missingDays"], ["2026-09-18"])
        self.assertIsNone(result["totalProfit"])
        self.assertIsNone(result["metrics"]["issue"]["count"])

    def test_partial_period_is_not_published(self):
        self.analysis(snapshot([fact()]))
        result = module.ComprehensiveAnalysisService({}).analysis("2026-09-17", "2026-09-18")
        self.assertFalse(result["available"])
        self.assertEqual(result["coverage"]["availableDays"], ["2026-09-18"])
        self.assertIsNone(result["totalProfit"])

    def test_partial_and_all_missing_profits_stay_null(self):
        result = self.analysis(snapshot([fact(count=3, known="8.0001", missing=1), fact("refund", 2, None, missing=2, key="r2")]))
        self.assertTrue(result["available"])
        self.assertIsNone(result["metrics"]["issue"]["profit"])
        self.assertEqual(result["metrics"]["issue"]["knownProfit"], "8.0001")
        self.assertIsNone(result["metrics"]["refund"]["knownProfit"])
        self.assertIsNone(result["comparison"][0]["totalProfit"])
        self.assertIsNone(result["totalProfit"])

    def test_missing_product_preserves_amount(self):
        result = self.analysis(snapshot([fact(product=None)]), group="product")
        self.assertEqual(result["totalProfit"], "12.1234")
        self.assertIn("待补充产品", result["comparison"][0]["name"])
        self.assertEqual(result["metrics"]["issue"]["productMissingCount"], 3)

    def test_platform_namespaced_products_do_not_merge(self):
        result = self.analysis(snapshot([fact(), fact(platform="P2", key="r2")]), group="product")
        self.assertEqual(len(result["comparison"]), 2)
        self.assertEqual(len(result["options"]["product"]), 2)

    def test_platform_labels_only_show_chinese_name(self):
        row = fact(platform="CTRIP")
        row["ota_cname"] = "携程"
        result = self.analysis(snapshot([row]), group="platform")
        self.assertEqual(result["options"]["platform"][0]["label"], "携程")
        self.assertEqual(result["comparison"][0]["name"], "携程")
        self.assertNotIn("CTRIP", result["comparison"][0]["name"])

    def test_policy_operator_supports_options_group_filter_and_unknown(self):
        one = fact(policy="政策员甲")
        two = fact(policy="政策员乙", key="r2")
        unknown = fact(policy=None, key="r3")
        result = self.analysis(snapshot([one, two, unknown]), group="policy")
        self.assertEqual({row["name"] for row in result["comparison"]}, {"政策员甲", "政策员乙", "未知政策员"})
        self.assertEqual(len(result["options"]["policy"]), 3)
        selected = self.analysis(
            snapshot([one, two, unknown]),
            group="policy",
            filters={"policy": module.dimension_value(two, "policy")},
        )
        self.assertEqual(selected["metrics"]["issue"]["count"], 3)
        self.assertEqual([row["name"] for row in selected["comparison"]], ["政策员乙"])

    def test_and_filters_change_cards_trend_and_comparison_together(self):
        one, two = fact(), fact(platform="P2", key="r2")
        result = self.analysis(snapshot([one, two]), group="airline", filters={"platform": module.dimension_value(one, "platform"), "airline": module.dimension_value(one, "airline")})
        self.assertEqual(result["metrics"]["issue"]["count"], 3)
        self.assertEqual(result["comparison"][0]["totalProfit"], "12.1234")
        self.assertEqual(len(result["options"]["platform"]), 2)

    def test_comparison_defaults_to_issue_segments_and_can_sort_by_issue_profit(self):
        high_profit = fact(platform="P1", known="100.0000", segments=2, key="p1")
        high_segments = fact(platform="P2", known="10.0000", segments=7, segment_missing=1, key="p2")
        rows = snapshot([high_profit, high_segments])
        default_result = self.analysis(rows, group="platform")
        profit_result = self.analysis(rows, group="platform", sort="profit")
        self.assertEqual([row["name"] for row in default_result["comparison"]], ["P2", "P1"])
        self.assertEqual(default_result["comparison"][0]["metrics"]["issue"]["segmentCount"], 7)
        self.assertEqual(default_result["comparison"][0]["metrics"]["issue"]["segmentMissingCount"], 1)
        self.assertEqual([row["name"] for row in profit_result["comparison"]], ["P1", "P2"])

    def test_empty_filter_result_is_covered_zero(self):
        result = self.analysis(snapshot([fact()]), filters={"airline": '["ZZ"]'})
        self.assertTrue(result["available"])
        self.assertEqual(result["totalProfit"], "0")
        self.assertEqual(result["comparison"], [])

    def test_broken_coverage_version_run_or_quantity_rejected(self):
        cases = []
        rows = snapshot([fact()]); rows[-1]["etl_run_id"] = "run2"; cases.append(rows)
        rows = snapshot([fact()]); rows[0]["metric_version"] = "v999"; cases.append(rows)
        rows = snapshot([fact()]); rows[0]["metric_version"] = "v2"; cases.append(rows)
        rows = snapshot([fact()]); rows[1]["source_row_count"] = 100; cases.append(rows)
        rows = snapshot([fact()]); rows.pop(); cases.append(rows)
        rows = snapshot([fact()]); rows.append(copy.deepcopy(rows[0])); cases.append(rows)
        rows = snapshot([fact()]); rows[0]["business_date"] = "2026-09-17"; cases.append(rows)
        for rows in cases:
            with self.subTest(rows=rows):
                result = self.analysis(rows)
                self.assertFalse(result["available"])
                self.assertIsNone(result["totalProfit"])

    def test_missing_profit_not_silently_zero_filled(self):
        rows = snapshot([fact(count=1, known=None, missing=1)])
        rows[0]["estimated_profit_cny"] = Decimal(0)
        self.assertFalse(self.analysis(rows)["available"])

    def test_connection_failure_has_no_demo_fallback(self):
        self.source.connect.side_effect = Exception("do not publish private diagnostics")
        result = self.analysis([])
        self.assertFalse(result["available"])
        self.assertNotIn("private", result["error"])
        self.assertEqual(result["comparison"], [])

    def test_query_is_only_ads_and_bound_dates(self):
        row = fact(platform="P' OR 1=1 --")
        self.analysis(snapshot([row]), filters={"platform": module.dimension_value(row, "platform")})
        query, params = self.cursor.execute.call_args.args
        self.assertIn("sibebid.bi_business_profit_dimension_day", query)
        self.assertIn("policy_operator", query)
        self.assertNotIn("dwd_order", query)
        self.assertNotIn("OR 1=1", query)
        self.assertEqual(params, ("2026-09-18", "2026-09-18"))
        self.cursor.close.assert_called_once()
        self.connection.close.assert_called_once()

    def test_oversized_snapshot_rejected_not_truncated(self):
        with patch.object(module, "MAX_ROWS", 2):
            result = self.analysis(snapshot([fact()]))
        self.assertFalse(result["available"])
        self.assertIsNone(result["totalProfit"])

    def test_diagnosis_compares_equal_previous_period_with_decimal_changes(self):
        current_rows = snapshot([fact(count=3, known="12.1234")])
        previous_rows = snapshot([fact(count=2, known="10.0000", day="2026-09-17")])
        self.cursor.fetchmany.side_effect = [
            [tuple(row.get(column) for column in module.COLUMNS) for row in current_rows],
            [tuple(row.get(column) for column in module.COLUMNS) for row in previous_rows],
        ]
        result = module.ComprehensiveAnalysisService({}).diagnosis(
            "2026-09-18", "2026-09-18", group="airline"
        )
        self.assertTrue(result["available"])
        self.assertTrue(result["previous"]["available"])
        self.assertEqual(result["previous"]["period"], {"startDate": "2026-09-17", "endDate": "2026-09-17"})
        self.assertEqual(result["changes"]["totalProfit"], "2.1234")
        self.assertEqual(result["changes"]["metrics"]["issue"], {"count": 1, "profit": "2.1234"})
        self.assertEqual(result["current"]["comparison"][0]["name"], "HO")

    def test_diagnosis_does_not_publish_change_when_previous_is_missing(self):
        current_rows = snapshot([fact()])
        self.cursor.fetchmany.side_effect = [
            [tuple(row.get(column) for column in module.COLUMNS) for row in current_rows],
            [],
        ]
        result = module.ComprehensiveAnalysisService({}).diagnosis("2026-09-18", "2026-09-18")
        self.assertTrue(result["available"])
        self.assertFalse(result["previous"]["available"])
        self.assertIsNone(result["changes"]["totalProfit"])
        self.assertIsNone(result["changes"]["metrics"]["issue"]["profit"])

    def test_input_validation_before_connect(self):
        service = module.ComprehensiveAnalysisService({})
        for args in [("2026-09-19", "2026-09-18"), ("2025-01-01", "2026-09-18"), ("invalid", "2026-09-18")]:
            with self.assertRaises(ValueError): service.analysis(*args)
        with self.assertRaises(ValueError): service.analysis(group="department")
        with self.assertRaises(ValueError): service.analysis(sort="totalProfit")
        for token in ['"HO"', '[1]', '["HO", "CA"]']:
            with self.assertRaises(ValueError): service.analysis(filters={"airline": token})
        self.source.connect.assert_not_called()

    def test_mysql_override_does_not_mutate_global_hive_config(self):
        config = {"DATA_MODE": "hive", "MYSQL_DATABASE": "sibebid"}
        module.ComprehensiveAnalysisService(config)
        self.assertEqual(config["DATA_MODE"], "hive")
        self.assertEqual(module.DataSource.call_args.args[0]["DATA_MODE"], "mysql")

    def test_route_and_bad_input(self):
        self.cursor.fetchmany.return_value = [tuple(row.get(column) for column in module.COLUMNS) for row in snapshot([fact()])]
        client = create_app(TestConfig).test_client()
        good = client.get("/api/v1/analysis/comprehensive?startDate=2026-09-18&endDate=2026-09-18")
        self.assertEqual(good.status_code, 200)
        self.assertTrue(good.json["data"]["available"])
        self.assertEqual(client.get("/api/v1/analysis/comprehensive?groupBy=department").status_code, 400)
        self.assertEqual(client.get("/api/v1/analysis/comprehensive?sortBy=totalProfit").status_code, 400)
        current_rows = snapshot([fact()])
        previous_rows = snapshot([fact(day="2026-09-17")])
        self.cursor.fetchmany.side_effect = [
            [tuple(row.get(column) for column in module.COLUMNS) for row in current_rows],
            [tuple(row.get(column) for column in module.COLUMNS) for row in previous_rows],
        ]
        diagnosis = client.get("/api/v1/analysis/comprehensive/diagnosis?startDate=2026-09-18&endDate=2026-09-18")
        self.assertEqual(diagnosis.status_code, 200)
        self.assertEqual(diagnosis.json["data"]["changes"]["totalProfit"], "0.0000")


if __name__ == "__main__":
    unittest.main()
