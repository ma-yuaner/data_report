"""Offline tests for the Hive smart-analysis API contract and SQL boundaries."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import smart_analysis as module


def aggregate_values(
    tickets=10, total_profit="100.0000", segments=12, refunds=1,
    smart=(6, 5, 4, "80.0000"), down=(4, 3, 2, "30.0000"),
    void=(3, 2, 2, "50.0000"), source_rows=2,
):
    return (
        source_rows, tickets, Decimal(total_profit) if total_profit is not None else None,
        segments, refunds,
        smart[0], smart[1], smart[2], Decimal(smart[3]) if smart[3] is not None else None,
        down[0], down[1], down[2], Decimal(down[3]) if down[3] is not None else None,
        void[0], void[1], void[2], Decimal(void[3]) if void[3] is not None else None,
        datetime(2026, 10, 9, 14, 30, 0),
    )


@pytest.fixture()
def source():
    value = MagicMock()
    value.database = "lywz"
    return value


def test_overview_uses_dimension_table_and_recalculates_rates(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchall.return_value = [
        ("2026-10-08", *aggregate_values()),
        ("2026-10-09", *aggregate_values(tickets=5, smart=(2, 1, 1, "20.0000"))),
    ]
    result = module.SmartAnalysisService({}, source=source).overview(
        start_value="2026-10-08", end_value="2026-10-09",
        first_dep_start="2026-10-10", filters={"platform": "携程"},
    )
    assert result["available"] is True
    assert result["hasData"] is True
    assert result["metrics"]["ticketCount"] == 15
    assert result["metrics"]["smart"]["usedCount"] == 5
    assert result["metrics"]["smart"]["useRate"] == pytest.approx(1 / 3)
    assert result["metrics"]["smart"]["profit"] == "100.0000"
    assert len(result["dailyTrend"]) == 2
    query, params = cursor.execute.call_args.args
    assert "lywz.dwd_smart_issue_dimension_day" in query
    assert "dwd_smart_issue_detail" not in query
    assert "携程" not in query
    assert params == ("2026-10-08", "2026-10-09", "2026-10-10", "携程")


def test_overview_empty_is_not_published_as_real_zero(source):
    source.connect.return_value.cursor.return_value.fetchall.return_value = []
    result = module.SmartAnalysisService({}, source=source).overview(
        start_value="2026-10-09", end_value="2026-10-09",
    )
    assert result["available"] is True
    assert result["hasData"] is False
    assert result["metrics"]["ticketCount"] is None
    assert result["metrics"]["smart"]["useRate"] is None


def test_dimensions_group_sort_and_page_are_whitelisted(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.side_effect = [aggregate_values(), (1,)]
    cursor.fetchall.return_value = [("东方航空", "携程", *aggregate_values())]
    result = module.SmartAnalysisService({}, source=source).dimensions(
        start_value="2026-10-09", end_value="2026-10-09",
        group_by="airline,platform", smart_type="down", sort_by="smartProfit",
        direction="desc", page_value="1", page_size_value="20",
    )
    assert result["available"] is True
    assert result["total"] == 1
    assert result["rows"][0]["path"][0]["value"] == "东方航空"
    assert result["rows"][0]["metrics"]["down"]["usedCount"] == 2
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert all("lywz.dwd_smart_issue_dimension_day" in query for query in queries)
    assert "down_profit DESC" in queries[-1]
    assert "row_no > 0" in queries[-1] and "row_no <= 20" in queries[-1]


def test_details_use_detail_table_stage_flags_and_selected_fields(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = (1, 1, Decimal("23.50"), datetime(2026, 10, 9, 15, 0, 0))
    # issueId, platform, four evidence flags
    cursor.fetchall.return_value = [(123, "携程", 1, 1, 0, 0)]
    result = module.SmartAnalysisService({}, source=source).details(
        start_value="2026-10-09", end_value="2026-10-09",
        smart_type="down", stage="success", fields_value="issueId,platform",
        page_value=1, page_size_value=20,
    )
    assert result["available"] is True
    assert result["summary"] == {"ticketCount": 1, "orderCount": 1, "profit": "23.50"}
    assert result["rows"][0]["issueId"] == "123"
    assert result["rows"][0]["downSucceeded"] is True
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert all("lywz.dwd_smart_issue_detail" in query for query in queries)
    assert all("src.down_succeeded = 1" in query for query in queries)
    assert "row_number()" in queries[-1]


def test_detail_unused_stage_includes_null_smart_confirm(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = (0, 0, None, None)
    cursor.fetchall.return_value = []
    module.SmartAnalysisService({}, source=source).details(
        start_value="2026-10-01", end_value="2026-10-02",
        smart_type="all", stage="unused",
    )
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert "src.smart_confirm IS NULL" in queries[-1]
    assert "src.smart_confirm NOT IN ('智能降舱','智能废票')" in queries[-1]


def test_filters_and_field_names_never_interpolate_user_input(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchall.return_value = []
    malicious = "x' OR 1=1 --"
    module.SmartAnalysisService({}, source=source).overview(
        start_value="2026-10-09", end_value="2026-10-09", filters={"airline": malicious},
    )
    query, params = cursor.execute.call_args.args
    assert malicious not in query
    assert params[-1] == malicious
    service = module.SmartAnalysisService({}, source=source)
    with pytest.raises(ValueError):
        service.dimensions(start_value="2026-10-09", end_value="2026-10-09", group_by="air_line;drop table x")
    with pytest.raises(ValueError):
        service.details(start_value="2026-10-09", end_value="2026-10-09", fields_value="issue_id;drop")


def test_smart_routes_validate_inputs_and_return_contract(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchall.return_value = [("2026-10-09", *aggregate_values())]
    with patch.object(module, "DataSource", return_value=source):
        client = create_app(TestConfig).test_client()
        response = client.get("/api/v1/smart-analysis/overview?startDate=2026-10-09&endDate=2026-10-09")
        assert response.status_code == 200
        assert response.json["data"]["source"] == "Hive · lywz.dwd_smart_issue_dimension_day"
        bad = client.get("/api/v1/smart-analysis/dimensions?startDate=2026-10-09&endDate=2026-10-09&groupBy=unknown")
        assert bad.status_code == 400
        bad = client.get("/api/v1/smart-analysis/details?startDate=2026-10-09&endDate=2026-10-09&stage=imagined")
        assert bad.status_code == 400


def test_hive_override_does_not_mutate_global_config():
    with patch.object(module, "DataSource") as source_class:
        config = {"DATA_MODE": "mysql", "HIVE_DATABASE": "another"}
        module.SmartAnalysisService(config)
        assert config == {"DATA_MODE": "mysql", "HIVE_DATABASE": "another"}
        passed = source_class.call_args.args[0]
        assert passed["DATA_MODE"] == "hive"
        assert passed["HIVE_DATABASE"] == "lywz"
