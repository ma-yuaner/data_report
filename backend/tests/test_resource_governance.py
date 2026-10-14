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

    def configure_rows(self, *, pnr_column=True, pnr=20):
        summary = (
            3, 100000, 95000, 2000, 1800, 25, 20, pnr,
            15000, 500000, 90000, datetime(2026, 10, 14, 8, 30),
        )
        self.cursor.fetchone.side_effect = [(1 if pnr_column else 0,), summary]
        self.cursor.fetchall.side_effect = [
            [("携程", "携程一部", "1A", "HKGH228DF", "SEARCH")],
            [("20261014",) + summary[:11]],
            [("1A",) + summary[:11]],
        ]

    def test_gds_overview_uses_real_pnr_and_keeps_layers_separate(self):
        self.configure_rows()
        result = module.ResourceGovernanceService({"RESOURCE_GOVERNANCE_TARGET_RATIO": 4000}).overview(
            "2026-10-01", "2026-10-14", data_source="gds", group_by="gds",
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["summary"]["pnrCount"], 20)
        self.assertEqual(result["summary"]["queryToPnrRatio"], "5000.00")
        self.assertEqual(result["summary"]["excessQueryCount"], 20000)
        self.assertEqual(result["dimension"]["rows"][0]["name"], "1A")
        self.assertEqual(result["trend"][0]["date"], "2026-10-14")
        executed = [call.args for call in self.cursor.execute.call_args_list]
        self.assertTrue(any("SUM(pnr_count)" in sql for sql, *_ in executed))
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
        self.assertNotIn("SUM(pnr_count)", executed_sql)
        self.assertIn(
            "SUM(order_request_count_all), SUM(order_request_success),\nNULL, SUM(search_cache_count)",
            executed_sql,
        )

    def test_ota_layer_rejects_gds_dimension_by_falling_back_to_platform(self):
        self.configure_rows()
        result = module.ResourceGovernanceService({}).overview(
            "2026-10-14", "2026-10-14", data_source="ota", group_by="pcc",
        )
        self.assertEqual(result["dimension"]["key"], "platform")
        dimension_sql = self.cursor.execute.call_args_list[-1].args[0]
        self.assertIn("GROUP BY ota_code", dimension_sql)
        self.assertEqual(self.cursor.execute.call_args_list[-1].args[1][2], 0)

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

    def test_route_is_available_and_validates_layer(self):
        app = create_app(TestConfig)
        with patch.object(module, "DataSource", return_value=self.source):
            response = app.test_client().get("/api/v1/resource-governance/overview?dataSource=all")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
