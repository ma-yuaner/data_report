from datetime import datetime

from data_report_api.services.business_profit_analysis import BUSINESS_DEFINITIONS
from data_report_api.services.data_source import DataSource, TABLE_SPECS, data_mode
from data_report_api.services.profit_overview import METRICS
from data_report_api.services.profit_problem_center import PROBLEM_DEFINITIONS, ProfitProblemCenterService


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "UP"
    assert payload["data"]["dataMode"] == "mock"


def test_overview_returns_four_profit_components(client):
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["mode"] == "mock"
    assert len(payload["metrics"]) == 4
    assert {item["key"] for item in payload["metrics"]} == {"issue", "refund", "change", "ancillary"}
    assert payload["totalProfit"]["value"] == sum(item["profit"] for item in payload["metrics"])
    assert payload["status"]["metricState"] == "业务估算口径"
    today = datetime.now().astimezone().date().isoformat()
    assert payload["period"] == {"startDate": today, "endDate": today}


def test_overview_rejects_invalid_period(client):
    response = client.get("/api/v1/dashboard/overview?startDate=2026-09-12&endDate=2026-09-11")
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_refund_profit_uses_confirmed_business_types():
    expected = "business_type_desc in ('正常退票（退票）', '售后退票作废（退票）')"
    refund_condition = next(metric["condition"] for metric in METRICS if metric["key"] == "refund")
    assert expected in refund_condition
    assert expected in BUSINESS_DEFINITIONS["refund"]["condition"]


def test_mysql_is_mapped_to_sibebid_bi_tables_and_operator_date():
    source = DataSource({"DATA_MODE": "mysql", "MYSQL_DATABASE": "sibebid"})
    assert source.label == "MySQL · sibebid"
    assert source.qualified_table("issue") == "sibebid.bi_order_issue_year"
    assert source.table("issue").time_field == "operator_date"
    assert source.table("refund").table == "bi_refund_issue_year"
    assert source.table("change").table == "bi_change_issue_year"
    assert source.table("ancillary").table == "bi_aux_pur_year"
    assert source.period_expression("operator_date", "day") == "date_format(operator_date, '%Y-%m-%d')"


def test_hive_switch_retains_authoritative_tables_and_dialect():
    source = DataSource({"DATA_MODE": "hive", "HIVE_DATABASE": "lywz"})
    assert source.label == "Hive · lywz"
    assert source.qualified_table("issue") == "lywz.dwd_order_issue_wide_year"
    assert source.table("issue").time_field == "issue_ticket_time"
    assert source.period_expression("issue_ticket_time", "month") == "substr(issue_ticket_time, 1, 7)"
    assert TABLE_SPECS["hive"]["ancillary"].table == "dwd_aux_pur_year"


def test_unknown_data_mode_never_silently_becomes_mock():
    try:
        data_mode({"DATA_MODE": "myslq"})
    except RuntimeError as error:
        assert "mysql、hive 或 mock" in str(error)
    else:
        raise AssertionError("未知数据源模式必须明确失败")


def test_problem_query_uses_mysql_table_time_and_cast_dialect():
    source = DataSource({"DATA_MODE": "mysql", "MYSQL_DATABASE": "sibebid"})
    sql = ProfitProblemCenterService._query(
        PROBLEM_DEFINITIONS[0], source, "2026-09-14 00:00:00", "2026-09-15 00:00:00"
    )
    assert "FROM sibebid.bi_order_issue_year" in sql
    assert "operator_date >= '2026-09-14 00:00:00'" in sql
    assert "cast(id as char)" in sql
    assert "as string" not in sql


def test_issue_profit_demo_contains_analysis_and_coverage(client):
    response = client.get("/api/v1/analysis/issue-profit?startDate=2026-01-01&endDate=2026-09-12")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["available"] is True
    assert payload["summary"]["issueCount"] > 0
    assert len(payload["completeness"]) == 12
    assert set(payload["dimensions"]) == {"platform", "airline", "supplier", "organization"}


def test_business_profit_pages_share_a_stable_contract(client):
    for business_type in ("refund", "change", "ancillary"):
        response = client.get(f"/api/v1/analysis/business-profit/{business_type}?startDate=2026-01-01&endDate=2026-09-12")
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["business"]["key"] == business_type
        assert payload["summary"]["count"] > 0
        assert payload["trend"]["items"]


def test_problem_center_exposes_loss_summary_and_evidence(client):
    response = client.get("/api/v1/problems/profit-loss?startDate=2026-09-12&endDate=2026-09-12")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["available"] is True
    assert payload["summary"]["negativeCount"] > 0
    assert len(payload["businesses"]) == 4
    assert payload["items"][0]["profit"] < 0


def test_asset_catalog_exposes_real_tables_and_metric_definitions(client):
    response = client.get("/api/v1/assets/catalog")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert len(payload["assets"]) == 4
    assert {item["key"] for item in payload["assets"]} == {"issue", "refund", "change", "ancillary"}
    assert next(item for item in payload["assets"] if item["key"] == "issue")["table"] == "bi_order_issue_year"
    assert next(item for item in payload["assets"] if item["key"] == "issue")["timeField"] == "operator_date"
    assert any(item["name"] == "总预估利润" for item in payload["metrics"])
    assert payload["analysisTaskCount"] == 149
    assert len(payload["analyses"]) == 11


def test_coverage_distinguishes_missing_from_zero(client):
    response = client.get("/api/v1/assets/coverage")
    items = response.get_json()["data"]["items"]
    assert any(item["state"] == "missing" for item in items)
    assert any(item["state"] == "pending" for item in items)
