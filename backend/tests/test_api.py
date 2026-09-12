from datetime import datetime

from data_report_api.services.business_profit_analysis import BUSINESS_DEFINITIONS
from data_report_api.services.profit_overview import METRICS


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
    refund_sql = next(metric["sql"] for metric in METRICS if metric["key"] == "refund")
    assert expected in refund_sql
    assert expected in BUSINESS_DEFINITIONS["refund"]["condition"]


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
    assert any(item["name"] == "总预估利润" for item in payload["metrics"])
    assert payload["analysisTaskCount"] == 149
    assert len(payload["analyses"]) == 11


def test_coverage_distinguishes_missing_from_zero(client):
    response = client.get("/api/v1/assets/coverage")
    items = response.get_json()["data"]["items"]
    assert any(item["state"] == "missing" for item in items)
    assert any(item["state"] == "pending" for item in items)
