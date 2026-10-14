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

    def configure_rows(self, *, pnr_column=True, pnr=20, pnr_missing=0, pnr_applicable=True):
        summary = (
            3, 100000, 95000, 2000, 1800, 25, 20, pnr,
            pnr_missing, 15000, 200, 2, 500000, 40000, 5000,
            0, 18, 1, datetime(2026, 10, 14, 8, 30),
        )
        self.cursor.fetchone.side_effect = (
            [(1 if pnr_column else 0,), summary] if pnr_applicable else [summary]
        )
        self.cursor.fetchall.side_effect = [
            [("携程", "携程一部", "1A", "HKGH228DF", "SEARCH")],
            [("20261014",) + summary[:18]],
            [(("1A" if pnr_applicable else "携程"),) + summary[:18]],
        ]

    def test_gds_overview_uses_real_pnr_and_keeps_layers_separate(self):
        self.configure_rows()
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000,1G:3000"}).overview(
            "2026-10-01", "2026-10-14", data_source="gds", group_by="gds", filters={"gds": "1A"},
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["summary"]["pnrCount"], 20)
        self.assertEqual(result["summary"]["queryToPnrRatio"], "5000.00")
        self.assertEqual(result["summary"]["excessQueryCount"], 20000)
        self.assertEqual(result["summary"]["targetRatio"], 4000)
        self.assertEqual(result["dimension"]["rows"][0]["name"], "1A")
        self.assertEqual(result["dimension"]["rows"][0]["targetRatio"], 4000)
        self.assertEqual(result["trend"][0]["date"], "2026-10-14")
        executed = [call.args for call in self.cursor.execute.call_args_list]
        self.assertTrue(any("SUM(pnr_num)" in sql for sql, *_ in executed))
        self.assertTrue(any(params[:3] == ("20261001", "20261014", 1) for _, params in executed[1:]))

    def test_missing_pnr_column_is_explicit_and_does_not_fallback_to_order_success(self):
        self.configure_rows(pnr_column=False, pnr=None)
        result = module.ResourceGovernanceService({}).overview("2026-10-14", "2026-10-14")
        self.assertTrue(result["available"])
        self.assertFalse(result["pnrColumnAvailable"])
        self.assertEqual(result["summary"]["status"], "pnr_field_missing")
        self.assertIsNone(result["summary"]["pnrCount"])
        self.assertIsNone(result["summary"]["queryToPnrRatio"])
        executed_sql = "\n".join(call.args[0] for call in self.cursor.execute.call_args_list)
        self.assertNotIn("SUM(pnr_num)", executed_sql)
        self.assertIn(
            "SUM(order_request_count_all), SUM(order_request_success),\nNULL, NULL,\nSUM(search_cache_count)",
            executed_sql,
        )

    def test_partial_pnr_sync_blocks_ratio_and_excess_calculation(self):
        self.configure_rows(pnr=20, pnr_missing=1)
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_GDS_TARGETS": "1A:4000"}).overview(
            "2026-10-14", "2026-10-14", data_source="gds", filters={"gds": "1A"},
        )
        self.assertEqual(result["summary"]["status"], "pnr_partial")
        self.assertEqual(result["summary"]["pnrMissingRowCount"], 1)
        self.assertIsNone(result["summary"]["queryToPnrRatio"])
        self.assertIsNone(result["summary"]["excessQueryCount"])
        self.assertFalse(result["pnrDataAvailable"])

    def test_ota_layer_rejects_gds_dimension_by_falling_back_to_platform(self):
        self.configure_rows(pnr=None, pnr_applicable=False)
        result = module.ResourceGovernanceService({
            "RESOURCE_GOVERNANCE_OTA_SUCCESS_TARGETS": '{"携程":{"search":96,"verify":95,"order":90}}',
        }).overview(
            "2026-10-14", "2026-10-14", data_source="ota", group_by="pcc", filters={"platform": "携程"},
        )
        self.assertEqual(result["dimension"]["key"], "platform")
        self.assertFalse(result["pnrApplicable"])
        self.assertEqual(result["summary"]["status"], "not_applicable")
        self.assertIsNone(result["summary"]["pnrCount"])
        self.assertIsNone(result["summary"]["queryToPnrRatio"])
        self.assertEqual(result["summary"]["successTargets"]["search"], "96.00")
        self.assertEqual(result["dimension"]["rows"][0]["successTargets"]["order"], "90.00")
        dimension_sql = self.cursor.execute.call_args_list[-1].args[0]
        self.assertIn("GROUP BY ota_code", dimension_sql)
        self.assertEqual(self.cursor.execute.call_args_list[-1].args[1][2], 0)
        executed_sql = "\n".join(call.args[0] for call in self.cursor.execute.call_args_list)
        self.assertNotIn("information_schema.COLUMNS", executed_sql)
        self.assertNotIn("SUM(pnr_num)", executed_sql)

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


if __name__ == "__main__":
    unittest.main()
