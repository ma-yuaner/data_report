from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import gds_route_analysis as module


def columns():
    return [(name, "string") for name in sorted(module.REQUIRED_COLUMNS)]


def metrics(search=1000, search_success=920, mp=600, mpis=300, ndc=100):
    return (
        1250, search, search_success, 80, 850, 840, 20, 200, 92000,
        150, 120, 30, 5, 24000, 3,
        100, 80, 20, 2, 16000, 1,
        mp, mpis, ndc, 600, 400, "2026-10-15 23:59:00",
    )


def test_route_service_queries_hive_and_keeps_api_stages_separate():
    source = MagicMock()
    source.database = "lywz"
    source.label = "Hive · lywz"
    connection = source.connect.return_value
    cursor = connection.cursor.return_value
    state = {"sql": "", "params": ()}

    def execute(sql, params=()):
        state["sql"], state["params"] = sql, params

    def fetchone():
        return metrics()

    def fetchall():
        if state["sql"].startswith("DESCRIBE"):
            return columns()
        if state["sql"].startswith("SELECT DISTINCT"):
            return [("1A", "HKGH228DF", "CTRIP", "CTRIP_HK", "1A_MPIS")]
        return [
            (
                "HKG-ICN", "香港", "首尔", "HKG", "ICN",
                "CTRIP", "CTRIP_HK", "1A", "HKGH228DF",
            ) + metrics()
        ]

    cursor.execute.side_effect = execute
    cursor.fetchone.side_effect = fetchone
    cursor.fetchall.side_effect = fetchall

    with patch.object(module, "business_now", return_value=datetime(2026, 10, 16, 10, 0)):
        result = module.GdsRouteAnalysisService(
            {"GDS_ROUTE_MAX_ROWS": 500, "GDS_ROUTE_MAX_DAYS": 31}, source=source
        ).overview(
            "2026-10-14", "2026-10-15",
            {"gds": "1A", "platform": "CTRIP", "keyword": "HKG"},
        )

    assert result["available"] is True
    assert result["table"] == "lywz.dws_gds_airroute_day"
    assert result["summary"]["searchSuccessRate"] == "92.00"
    assert result["summary"]["verifySuccessRate"] == "80.00"
    assert result["summary"]["orderSuccessRate"] == "80.00"
    assert result["summary"]["mpShare"] == "60.00"
    assert result["rows"][0]["route"] == "HKG-ICN"
    assert result["rows"][0]["platform"] == "CTRIP"
    assert result["options"]["apiGroup"] == ["1A_MPIS"]
    grouped_call = next(
        call for call in cursor.execute.call_args_list
        if "GROUP BY airroute_code" in call.args[0]
    )
    assert "api_method = 'search'" in grouped_call.args[0]
    assert "api_method = 'verify'" in grouped_call.args[0]
    assert "api_method = 'orderCreate'" in grouped_call.args[0]
    assert grouped_call.args[1] == (
        "2026-10-14", "2026-10-15", "CTRIP", "1A", "%HKG%",
    )


def test_route_metric_sql_has_no_literal_percent_conflicting_with_pyhive_params():
    assert "%MPIS" not in module.METRIC_SQL
    assert "%NDC" not in module.METRIC_SQL
    assert "rlike 'MPIS$'" in module.METRIC_SQL
    assert "rlike 'NDC$'" in module.METRIC_SQL


def test_route_service_caps_period_at_yesterday_and_rejects_wide_range():
    source = MagicMock()
    source.database = "lywz"
    source.label = "Hive · lywz"
    service = module.GdsRouteAnalysisService(
        {"GDS_ROUTE_MAX_DAYS": 7}, source=source
    )
    with patch.object(module, "business_now", return_value=datetime(2026, 10, 16, 10, 0)):
        assert service._period("2026-10-15", "2026-10-16") == (
            datetime(2026, 10, 15).date(), datetime(2026, 10, 15).date(),
        )
        with pytest.raises(ValueError, match="最多查询7天"):
            service._period("2026-10-01", "2026-10-15")


def test_route_endpoint_returns_service_data_and_unavailable_status():
    app = create_app(TestConfig)
    client = app.test_client()
    payload = {"available": True, "rows": []}
    with patch(
        "data_report_api.routes.GdsRouteAnalysisService.overview", return_value=payload
    ) as overview:
        response = client.get(
            "/api/v1/resource-governance/gds/routes?startDate=2026-10-14&endDate=2026-10-15&gds=1A"
        )
    assert response.status_code == 200
    assert response.get_json()["data"] == payload
    assert overview.call_args.kwargs["filters"]["gds"] == "1A"

    with patch(
        "data_report_api.routes.GdsRouteAnalysisService.overview",
        side_effect=module.GdsRouteAnalysisUnavailable("Hive失败"),
    ):
        response = client.get("/api/v1/resource-governance/gds/routes")
    assert response.status_code == 503
    assert response.get_json()["message"] == "Hive失败"
