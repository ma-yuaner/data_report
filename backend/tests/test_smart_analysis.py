"""Offline tests for the MySQL smart-analysis API contract and SQL boundaries."""
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
    value.database = "sibebid"
    return value


def test_overview_uses_dimension_table_and_recalculates_rates(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = aggregate_values(
        tickets=15, total_profit="200.0000", segments=24, refunds=2,
        smart=(8, 6, 5, "100.0000"), source_rows=4,
    )
    result = module.SmartAnalysisService({}, source=source).overview(
        start_value="2026-10-08", end_value="2026-10-09",
        first_dep_start="2026-10-10", first_dep_end="2026-10-10",
        filters={"platform": "携程"},
    )
    assert result["available"] is True
    assert result["hasData"] is True
    assert result["metrics"]["ticketCount"] == 15
    assert result["metrics"]["smart"]["usedCount"] == 5
    assert result["metrics"]["smart"]["useRate"] == pytest.approx(1 / 3)
    assert result["metrics"]["smart"]["profit"] == "100.0000"
    assert result["dailyTrend"] == []
    calls = cursor.execute.call_args_list
    total_query, total_params = calls[0].args
    assert len(calls) == 1
    assert "sibebid.bi_smart_issue_dimension_year" in total_query
    assert "bi_smart_issue_detail_year" not in total_query
    assert "携程" not in total_query
    assert total_params == ("2026-10-08", "2026-10-09", "2026-10-10", "2026-10-10", "携程")


def test_issue_period_is_optional_when_another_complete_period_is_selected(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = aggregate_values()
    result = module.SmartAnalysisService({}, source=source).overview(
        first_dep_start="2026-10-08", first_dep_end="2026-10-09",
    )
    assert result["available"] is True
    query, params = cursor.execute.call_args.args
    assert "src.issue_ticket_date" not in query.split("WHERE", 1)[1]
    assert "src.first_dep_date >= %s" in query
    assert params == ("2026-10-08", "2026-10-09")


def test_at_least_one_complete_period_is_required(source):
    service = module.SmartAnalysisService({}, source=source)
    with pytest.raises(ValueError, match="至少选择一个完整范围"):
        service.overview(start_value="", end_value="")
    with pytest.raises(ValueError, match="同时选择进单日期"):
        service.overview(order_start="2026-10-08")


def test_overview_empty_is_not_published_as_real_zero(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = aggregate_values(source_rows=0)
    cursor.fetchall.return_value = []
    result = module.SmartAnalysisService({}, source=source).overview(
        start_value="2026-10-09", end_value="2026-10-09",
    )
    assert result["available"] is True
    assert result["hasData"] is False
    assert result["metrics"]["ticketCount"] is None
    assert result["metrics"]["smart"]["useRate"] is None


def test_overview_trend_can_use_departure_date_with_its_own_window(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchall.return_value = [("2026-12-15", *aggregate_values())]
    result = module.SmartAnalysisService({}, source=source).trends(
        start_value="2026-10-01", end_value="2026-10-09",
        first_dep_start="2026-12-01", first_dep_end="2026-12-15",
        trend_date="departure",
    )
    assert result["trend"] == {
        "dateType": "departure", "dateLabel": "首段起飞日期",
        "cutoffSource": "首段起飞结束日期",
        "cutoffDate": "2026-12-15", "dailyStartDate": "2026-11-16",
        "monthlyStartDate": "2026-01-01",
    }
    trend_query, trend_params = cursor.execute.call_args.args
    assert "sibebid.bi_smart_issue_dimension_year" in trend_query
    assert "GROUP BY src.first_dep_date" in trend_query
    assert trend_params == ("2026-01-01", "2026-12-15", "2026-10-01", "2026-10-09")


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
    assert all("sibebid.bi_smart_issue_dimension_year" in query for query in queries)
    assert "(sum(src.down_profit_sum) IS NULL) ASC" in queries[-1]
    assert "down_profit DESC" in queries[-1]
    assert "LIMIT 0, 20" in queries[-1]
    assert "row_number()" not in queries[-1].lower()


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
    assert all("sibebid.bi_smart_issue_detail_year" in query for query in queries)
    assert all("src.down_succeeded = 1" in query for query in queries)
    assert "LIMIT 0, 20" in queries[-1]
    assert "row_number()" not in queries[-1].lower()


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


def test_ticket_drawer_loads_all_fields_by_bound_issue_id(source):
    cursor = source.connect.return_value.cursor.return_value
    ordered_fields = module.ordered_detail_fields(tuple(module.DETAIL_BY_KEY))
    cursor.fetchone.return_value = tuple(
        123 if field.key == "issueId" else "智能降舱" if field.key == "smartConfirm" else None
        for field in ordered_fields
    )
    result = module.SmartAnalysisService({}, source=source).ticket("123")
    assert result["available"] is True
    assert result["found"] is True
    assert result["record"]["issueId"] == "123"
    assert len(result["columns"]) == len(module.DETAIL_FIELDS)
    query, params = cursor.execute.call_args.args
    assert "sibebid.bi_smart_issue_detail_year" in query
    assert "date_format(src.issue_ticket_date,'%%Y-%%m')" in query
    assert "WHERE src.issue_id = %s" in query
    assert "cast(src.issue_id" not in query.lower()
    assert "123" not in query
    assert params == ("123",)


def test_detail_dimensions_are_ordered_before_metrics(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = (0, 0, None, None)
    cursor.fetchall.return_value = []
    result = module.SmartAnalysisService({}, source=source).details(
        start_value="2026-10-09", end_value="2026-10-09",
        fields_value="issueProfit,issueTicketNo,platform,otaOrderNo",
    )
    keys = [column["key"] for column in result["columns"]]
    assert keys[:2] == ["issueId", "otaOrderNo"]
    assert keys.index("issueTicketNo") < keys.index("issueProfit")
    assert keys.index("platform") < keys.index("issueProfit")


def test_detail_export_rejects_more_than_fifty_thousand_rows(source):
    cursor = source.connect.return_value.cursor.return_value
    cursor.fetchone.return_value = (module.MAX_DETAIL_EXPORT_ROWS + 1,)
    with pytest.raises(ValueError, match="50000"):
        module.SmartAnalysisService({}, source=source).export_details(
            start_value="2026-10-01", end_value="2026-10-09",
            fields_value="issueId,platform",
        )
    assert cursor.execute.call_count == 1


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
    cursor.fetchone.return_value = aggregate_values()
    cursor.fetchall.return_value = [("2026-10-09", *aggregate_values())]
    with patch.object(module, "DataSource", return_value=source):
        client = create_app(TestConfig).test_client()
        response = client.get("/api/v1/smart-analysis/overview?startDate=2026-10-09&endDate=2026-10-09")
        assert response.status_code == 200
        assert response.json["data"]["source"] == "MySQL · sibebid.bi_smart_issue_dimension_year"
        bad = client.get("/api/v1/smart-analysis/dimensions?startDate=2026-10-09&endDate=2026-10-09&groupBy=unknown")
        assert bad.status_code == 400
        bad = client.get("/api/v1/smart-analysis/details?startDate=2026-10-09&endDate=2026-10-09&stage=imagined")
        assert bad.status_code == 400


def test_mysql_override_does_not_mutate_global_config():
    with patch.object(module, "DataSource") as source_class:
        config = {"DATA_MODE": "hive", "MYSQL_DATABASE": "another"}
        module.SmartAnalysisService(config)
        assert config == {"DATA_MODE": "hive", "MYSQL_DATABASE": "another"}
        passed = source_class.call_args.args[0]
        assert passed["DATA_MODE"] == "mysql"
        assert passed["MYSQL_DATABASE"] == "sibebid"
