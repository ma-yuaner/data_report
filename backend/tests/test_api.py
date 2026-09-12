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


def test_overview_rejects_invalid_period(client):
    response = client.get("/api/v1/dashboard/overview?startDate=2026-09-12&endDate=2026-09-11")
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_issue_profit_demo_contains_analysis_and_coverage(client):
    response = client.get("/api/v1/analysis/issue-profit?startDate=2026-01-01&endDate=2026-09-12")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["available"] is True
    assert payload["summary"]["issueCount"] > 0
    assert len(payload["completeness"]) == 12
    assert set(payload["dimensions"]) == {"platform", "airline", "supplier", "organization"}


def test_coverage_distinguishes_missing_from_zero(client):
    response = client.get("/api/v1/assets/coverage")
    items = response.get_json()["data"]["items"]
    assert any(item["state"] == "missing" for item in items)
    assert any(item["state"] == "pending" for item in items)
