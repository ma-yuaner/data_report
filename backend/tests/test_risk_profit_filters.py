from datetime import date

import pytest

from data_report_api.services.data_source import DataSource
from data_report_api.services.risk_profit_summary import (
    OPTION_LIMIT, RISK_FILTER_FIELDS, RISK_PROFIT_DEFINITIONS, RiskProfitSummaryService,
    _CACHE, _filter_conditions, normalize_risk_filters,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


class FakeConnection:
    def __init__(self, fail_table=None, option_rows=None):
        self.calls = []
        self.fail_table = fail_table
        self.option_rows = option_rows if option_rows is not None else [("机票业务1部",), ("机票业务2部",)]
        self.closed = False
        self.cursor_closed = 0

    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, sql, parameters=()):
                connection.calls.append((sql, parameters))
                if connection.fail_table and connection.fail_table in sql:
                    raise RuntimeError("simulated query failure")

            def fetchone(self):
                return (3, -120.25)

            def fetchall(self):
                return connection.option_rows

            def close(self):
                connection.cursor_closed += 1

        return Cursor()

    def close(self):
        self.closed = True


@pytest.mark.parametrize("mode", ["mysql", "hive"])
def test_all_dimension_filters_are_bound_and_profit_filter_is_row_level(monkeypatch, mode):
    connection = FakeConnection()
    monkeypatch.setattr(DataSource, "connect", lambda self: connection)
    values = {"platform": "携程", "site": "香港携程一部", "department": "机票业务1部",
              "airline": "HO", "supplier": "马来西亚CIT", "profitStatus": "loss"}
    result = RiskProfitSummaryService({"DATA_MODE": mode}).summary("2026-08-01", "2026-08-31", values)
    assert result["available"] is True
    assert result["filters"] == values
    assert len(connection.calls) == 3
    for sql, parameters in connection.calls:
        for column in RISK_FILTER_FIELDS.values():
            assert f"{column} = %s" in sql
        assert "AND estimated_profit_cny < 0" in sql
        assert "HAVING" not in sql
        assert parameters == ("携程", "香港携程一部", "机票业务1部", "HO", "马来西亚CIT")
    assert connection.closed and connection.cursor_closed == 3


def test_user_text_is_never_interpolated_into_sql(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(DataSource, "connect", lambda self: connection)
    payload = "O'Reilly' OR 1=1 --"
    RiskProfitSummaryService({"DATA_MODE": "mysql"}).summary("2026-08-01", "2026-08-31", {"supplier": payload})
    for sql, parameters in connection.calls:
        assert payload not in sql
        assert parameters == (payload,)


@pytest.mark.parametrize("values", [{"profitStatus": "bad"}, {"profitStatus": ["loss"]},
                                  {"department": "a" * 151}, {"department": 42}, {"rawSql": "1=1"}])
def test_invalid_filters_are_rejected(values):
    with pytest.raises(ValueError):
        normalize_risk_filters(values)


@pytest.mark.parametrize("status,condition", [("all", ""), ("loss", "estimated_profit_cny < 0"),
                                             ("profit", "estimated_profit_cny > 0"), ("zero", "estimated_profit_cny = 0")])
def test_profit_status_does_not_turn_missing_profit_into_zero(status, condition):
    sql, parameters = _filter_conditions(normalize_risk_filters({"profitStatus": status}))
    assert condition in sql
    assert "coalesce" not in sql
    assert parameters == ()


def test_filters_are_part_of_summary_cache_key(monkeypatch):
    connections = []
    def connect(source):
        connection = FakeConnection()
        connections.append(connection)
        return connection
    monkeypatch.setattr(DataSource, "connect", connect)
    service = RiskProfitSummaryService({"DATA_MODE": "mysql", "PROFIT_CACHE_TTL": 300})
    first = service.summary("2026-08-01", "2026-08-31", {"department": "一部"})
    second = service.summary("2026-08-01", "2026-08-31", {"department": "二部"})
    again = service.summary("2026-08-01", "2026-08-31", {"department": "一部"})
    assert not first["cacheHit"] and not second["cacheHit"] and again["cacheHit"]
    assert len(connections) == 2
    assert again["filters"]["department"] == "一部"


def test_option_query_uses_dates_other_filters_and_literal_prefix_search(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(DataSource, "connect", lambda self: connection)
    result = RiskProfitSummaryService({"DATA_MODE": "mysql"}).filter_options(
        "2026-08-01", "2026-08-31", "department", "机_%", {"platform": "携程", "department": "当前输入"},
    )
    assert result["available"] is True
    assert result["options"] == ["机票业务1部", "机票业务2部"]
    assert len(connection.calls) == 3
    for sql, parameters in connection.calls:
        assert "SELECT DISTINCT org_cname" in sql
        assert "< '2026-09-01'" in sql
        assert "ota_cname = %s" in sql
        assert "org_cname = %s" not in sql
        assert parameters == ("携程", "机\\_\\%%")
        assert f"LIMIT {OPTION_LIMIT + 1}" in sql
    assert connection.closed and connection.cursor_closed == 3


def test_options_are_bounded_and_truncation_is_disclosed(monkeypatch):
    connection = FakeConnection(option_rows=[(f"站点{i:03}",) for i in range(OPTION_LIMIT + 1)])
    monkeypatch.setattr(DataSource, "connect", lambda self: connection)
    result = RiskProfitSummaryService({"DATA_MODE": "mysql"}).filter_options("2026-08-01", "2026-08-31", "site")
    assert result["truncated"] is True
    assert len(result["options"]) == OPTION_LIMIT


def test_partial_option_failure_keeps_successful_suggestions_and_is_not_cached(monkeypatch):
    connection = FakeConnection(fail_table="bi_order_refund_profit_reconcile_year")
    monkeypatch.setattr(DataSource, "connect", lambda self: connection)
    service = RiskProfitSummaryService({"DATA_MODE": "mysql"})
    result = service.filter_options("2026-08-01", "2026-08-31", "department")
    assert result["available"] is False
    assert result["options"]
    assert result["errors"] == ["退票筛选项查询失败"]
    assert not _CACHE


def test_partial_metric_failure_stays_unavailable_and_never_reads_hive(monkeypatch):
    connection = FakeConnection(fail_table="bi_order_refund_profit_reconcile_year")
    modes = []
    def connect(source):
        modes.append(source.mode)
        return connection
    monkeypatch.setattr(DataSource, "connect", connect)
    result = RiskProfitSummaryService({"DATA_MODE": "mysql"}).summary("2026-08-01", "2026-08-31", {"profitStatus": "loss"})
    assert modes == ["mysql"]
    assert result["available"] is False
    refund = next(item for item in result["metrics"] if item["key"] == "refund")
    assert refund["ticketCount"] is None and refund["estimatedProfit"] is None
    assert not _CACHE


def test_summary_api_accepts_filters_but_core_overview_is_not_filtered(client):
    response = client.get("/api/v1/dashboard/risk-profit-summary?department=机票业务1部&profitStatus=loss")
    assert response.status_code == 200
    assert response.get_json()["data"]["filters"]["department"] == "机票业务1部"
    response = client.get("/api/v1/dashboard/overview?department=机票业务1部&profitStatus=loss")
    assert len(response.get_json()["data"]["metrics"]) == 4


@pytest.mark.parametrize("query", ["profitStatus=bad", "department=" + "a" * 151])
def test_summary_api_invalid_filters_return_400(client, query):
    response = client.get("/api/v1/dashboard/risk-profit-summary?" + query)
    assert response.status_code == 400


@pytest.mark.parametrize("query", ["field=rawSql", "field=department&search=" + "a" * 151,
                                  "field=department&startDate=2026-09-12&endDate=2026-09-11"])
def test_option_api_invalid_requests_return_400(client, query):
    response = client.get("/api/v1/dashboard/risk-profit-filter-options?" + query)
    assert response.status_code == 400


def test_option_api_handles_connection_failure_without_fabricating_values(client):
    response = client.get("/api/v1/dashboard/risk-profit-filter-options?field=department")
    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["available"] is False and result["options"] == []


@pytest.mark.parametrize("mode", ["mysql", "hive"])
def test_options_keep_per_business_time_fields(mode):
    source = DataSource({"DATA_MODE": mode})
    for definition in RISK_PROFIT_DEFINITIONS[mode]:
        sql, _ = RiskProfitSummaryService._options_query(
            source, definition, date(2026, 8, 1), date(2026, 9, 1), "site", "", normalize_risk_filters(None),
        )
        assert f"{definition['timeField']} >= '2026-08-01'" in sql
        assert f"{definition['timeField']} < '2026-09-01'" in sql
