def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "UP"
    assert payload["data"]["dataMode"] == "mock"


def test_overview_marks_mock_data(client):
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["mode"] == "mock"
    assert len(payload["kpis"]) == 4
    assert payload["status"]["metricState"] == "口径待确认"


def test_coverage_distinguishes_missing_from_zero(client):
    response = client.get("/api/v1/assets/coverage")
    items = response.get_json()["data"]["items"]
    assert any(item["state"] == "missing" for item in items)
    assert any(item["state"] == "pending" for item in items)

