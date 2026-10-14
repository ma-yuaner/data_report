import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import resource_governance as module


class ResourceGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.source = MagicMock()
        self.source.database = "sibebid"
        self.source.label = "MySQL · sibebid"
        self.connection = self.source.connect.return_value
        self.cursor = self.connection.cursor.return_value
        self.source_patch = patch.object(module, "DataSource", return_value=self.source)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)

    def configure_rows(self, *, segment_column=True, segments=20, segment_missing=0, ratio_applicable=True):
        summary = (
            3, 100000, 95000, 2000, 1800, 25, 20, segments,
            segment_missing, 15000, 200, 2, 500000, 40000, 5000,
            0, 18, 1, datetime(2026, 10, 14, 8, 30),
        )
        self.cursor.fetchone.side_effect = (
            [(1 if segment_column else 0,), summary] if ratio_applicable else [summary]
        )
        self.cursor.fetchall.side_effect = [
            [("携程", "携程一部", "1A", "HKGH228DF", "SEARCH")],
            [("20261014",) + summary[:18]],
            [(("1A" if ratio_applicable else "携程"),) + summary[:18]],
        ]

    def test_gds_overview_uses_segment_count_and_keeps_layers_separate(self):
        self.configure_rows()
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000,1G:3000"}).overview(
            "2026-10-01", "2026-10-14", data_source="gds", group_by="gds", filters={"gds": "1A"},
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["summary"]["segmentCount"], 20)
        self.assertEqual(result["summary"]["queryToSegmentRatio"], "5000.00")
        self.assertEqual(result["summary"]["excessQueryCount"], 20000)
        self.assertEqual(result["summary"]["targetRatio"], 4000)
        self.assertEqual(result["dimension"]["rows"][0]["name"], "1A")
        self.assertEqual(result["dimension"]["rows"][0]["targetRatio"], 4000)
        self.assertEqual(result["trend"][0]["date"], "2026-10-14")
        executed = [call.args for call in self.cursor.execute.call_args_list]
        self.assertTrue(any("SUM(seg_num)" in sql for sql, *_ in executed))
        self.assertTrue(any(params[:3] == ("20261001", "20261014", 1) for _, params in executed[1:]))

    def test_missing_segment_column_is_explicit_and_does_not_fallback_to_other_counts(self):
        self.configure_rows(segment_column=False, segments=None)
        result = module.ResourceGovernanceService({}).overview("2026-10-14", "2026-10-14")
        self.assertTrue(result["available"])
        self.assertFalse(result["segmentColumnAvailable"])
        self.assertEqual(result["summary"]["status"], "segment_field_missing")
        self.assertIsNone(result["summary"]["segmentCount"])
        self.assertIsNone(result["summary"]["queryToSegmentRatio"])
        executed_sql = "\n".join(call.args[0] for call in self.cursor.execute.call_args_list)
        self.assertNotIn("SUM(seg_num)", executed_sql)
        self.assertIn(
            "SUM(order_request_count_all), SUM(order_request_success),\nNULL, NULL,\nSUM(search_cache_count)",
            executed_sql,
        )

    def test_partial_segment_sync_blocks_ratio_and_excess_calculation(self):
        self.configure_rows(segments=20, segment_missing=1)
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000"}).overview(
            "2026-10-14", "2026-10-14", data_source="gds", filters={"gds": "1A"},
        )
        self.assertEqual(result["summary"]["status"], "segment_partial")
        self.assertEqual(result["summary"]["segmentMissingRowCount"], 1)
        self.assertIsNone(result["summary"]["queryToSegmentRatio"])
        self.assertIsNone(result["summary"]["excessQueryCount"])
        self.assertFalse(result["segmentDataAvailable"])

    def test_ota_layer_rejects_gds_dimension_by_falling_back_to_platform(self):
        self.configure_rows(segments=None, ratio_applicable=False)
        result = module.ResourceGovernanceService({
            "RESOURCE_GOVERNANCE_OTA_SUCCESS_TARGETS": '{"携程":{"search":96,"verify":95,"order":90}}',
        }).overview(
            "2026-10-14", "2026-10-14", data_source="ota", group_by="pcc", filters={"platform": "携程"},
        )
        self.assertEqual(result["dimension"]["key"], "platform")
        self.assertFalse(result["ratioApplicable"])
        self.assertEqual(result["summary"]["status"], "not_applicable")
        self.assertIsNone(result["summary"]["segmentCount"])
        self.assertIsNone(result["summary"]["queryToSegmentRatio"])
        self.assertEqual(result["summary"]["successTargets"]["search"], "96.00")
        self.assertEqual(result["dimension"]["rows"][0]["successTargets"]["order"], "90.00")
        dimension_sql = self.cursor.execute.call_args_list[-1].args[0]
        self.assertIn("GROUP BY ota_code", dimension_sql)
        self.assertEqual(self.cursor.execute.call_args_list[-1].args[1][2], 0)
        executed_sql = "\n".join(call.args[0] for call in self.cursor.execute.call_args_list)
        self.assertNotIn("information_schema.COLUMNS", executed_sql)
        self.assertNotIn("SUM(seg_num)", executed_sql)

    def test_invalid_inputs_fail_before_connecting(self):
        service = module.ResourceGovernanceService({})
        for kwargs in (
            {"start_value": "bad-date"},
            {"start_value": "2026-10-15", "end_value": "2026-10-14"},
            {"data_source": "all"},
            {"group_by": "airline"},
        ):
            with self.assertRaises(ValueError):
                service.overview(**kwargs)
        self.source.connect.assert_not_called()

    def test_separate_routes_fix_their_own_data_layer(self):
        app = create_app(TestConfig)
        with patch("data_report_api.routes.ResourceGovernanceService") as service_class:
            service_class.return_value.overview.return_value = {"available": True}
            client = app.test_client()
            gds_response = client.get("/api/v1/resource-governance/gds/overview")
            self.assertEqual(gds_response.status_code, 200)
            self.assertEqual(service_class.return_value.overview.call_args.kwargs["data_source"], "gds")
            ota_response = client.get("/api/v1/resource-governance/ota/overview")
            self.assertEqual(ota_response.status_code, 200)
            self.assertEqual(service_class.return_value.overview.call_args.kwargs["data_source"], "ota")

    def test_gds_rows_flag_objects_above_the_governance_target(self):
        self.configure_rows()
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000"}).overview(
            "2026-10-01", "2026-10-14", data_source="gds", group_by="gds", filters={"gds": "1A"},
        )
        summary = result["summary"]
        self.assertTrue(summary["breach"])
        self.assertIn("查定比超过治理目标4000:1", summary["breachReasons"])
        row = result["dimension"]["rows"][0]
        self.assertTrue(row["breach"])
        self.assertEqual(result["breachObjectCount"], 1)
        self.assertFalse(result["breachOnly"])

    def test_breach_only_filters_normal_objects_out(self):
        self.configure_rows()
        service = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000"})
        all_rows = service.overview("2026-10-14", "2026-10-14", data_source="gds", group_by="gds")
        self.assertEqual(len(all_rows["dimension"]["rows"]), 1)

        self.configure_rows(segments=50)
        normal = service.overview("2026-10-14", "2026-10-14", data_source="gds", group_by="gds")
        self.assertFalse(normal["dimension"]["rows"][0]["breach"])
        self.assertEqual(normal["breachObjectCount"], 0)

        filtered = service.overview("2026-10-14", "2026-10-14", data_source="gds", group_by="gds", breach_only=True)
        self.assertTrue(filtered["breachOnly"])
        self.assertEqual(filtered["dimension"]["rows"], [])

    def test_ota_rows_flag_stages_below_the_platform_target(self):
        self.configure_rows(segments=None, ratio_applicable=False)
        result = module.ResourceGovernanceService({
            "RESOURCE_GOVERNANCE_OTA_SUCCESS_TARGETS": '{"携程":{"search":96,"verify":95,"order":10}}',
        }).overview(
            "2026-10-14", "2026-10-14", data_source="ota", group_by="platform", filters={"platform": "携程"},
        )
        # 配置值：查询1万条成功9500（95%）、验价2000条成功1800（90%）、生单25条成功20（80%）。
        reasons = result["summary"]["breachReasons"]
        self.assertTrue(result["summary"]["breach"])
        self.assertIn("查询成功率95.00%低于目标96.00%", reasons)
        self.assertIn("验价成功率90.00%低于目标95.00%", reasons)
        self.assertFalse(any("生单成功率" in reason for reason in reasons))

    def test_ota_without_configured_target_is_not_marked_as_breach(self):
        self.configure_rows(segments=None, ratio_applicable=False)
        result = module.ResourceGovernanceService({}).overview(
            "2026-10-14", "2026-10-14", data_source="ota", group_by="platform",
        )
        self.assertFalse(result["summary"]["breach"])
        self.assertEqual(result["summary"]["breachReasons"], [])
        self.assertEqual(result["breachObjectCount"], 0)

    def test_route_passes_breach_only_flag(self):
        app = create_app(TestConfig)
        with patch("data_report_api.routes.ResourceGovernanceService") as service_class:
            service_class.return_value.overview.return_value = {"available": True}
            client = app.test_client()
            client.get("/api/v1/resource-governance/gds/overview?breachOnly=true")
            self.assertTrue(service_class.return_value.overview.call_args.kwargs["breach_only"])
            client.get("/api/v1/resource-governance/gds/overview")
            self.assertFalse(service_class.return_value.overview.call_args.kwargs["breach_only"])


if __name__ == "__main__":
    unittest.main()
