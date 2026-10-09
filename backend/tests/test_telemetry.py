import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_report_api.services.telemetry import TelemetryService


def service_with_cursor():
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    cursor = connection.cursor.return_value
    return TelemetryService({}, source=source), connection, cursor


def visit_payload():
    return {
        "visitId": "a" * 32,
        "moduleCode": "business-analysis",
        "pageCode": "comprehensive-analysis",
        "routePath": "/analysis/comprehensive",
        "pageTitle": "综合分析",
        "referrerPageCode": "overview",
        "loadDurationMs": 321,
        "viewportWidth": 1440,
        "viewportHeight": 900,
        "deviceType": "desktop",
        "appVersion": "test",
    }


def event_payload(event_id="b" * 32, event_type="filter_apply"):
    return {
        "eventId": event_id,
        "visitId": "a" * 32,
        "moduleCode": "business-analysis",
        "pageCode": "comprehensive-analysis",
        "routePath": "/analysis/comprehensive",
        "eventType": event_type,
        "elementCode": "filter-query",
        "elementName": "查询",
        "resultStatus": "success",
        "durationMs": 432,
        "context": {
            "filterKeys": ["platform", "airline"],
            "dateRangeDays": 30,
            "ticketNo": "SECRET-TICKET",
        },
        "eventVersion": 1,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "appVersion": "test",
    }


def test_visit_identity_comes_from_authenticated_session():
    service, connection, cursor = service_with_cursor()
    result = service.start_visit(
        {"id": 7, "is_admin": True}, {"session_id": 19}, visit_payload()
    )
    assert result == {"visitId": "a" * 32}
    query, params = cursor.execute.call_args.args
    assert "sys_user_page_visit" in query
    assert params[1:4] == (7, 19, "admin")
    assert params[5] == "comprehensive-analysis"
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_events_drop_sensitive_context_and_increment_only_inserted_actions():
    service, _connection, cursor = service_with_cursor()
    cursor.rowcount = 1
    result = service.record_events(
        {"id": 8, "is_admin": False}, {"session_id": 20},
        {"events": [event_payload()]},
    )
    assert result == {"accepted": 1}
    insert_call = cursor.execute.call_args_list[0]
    query, params = insert_call.args
    assert "INSERT IGNORE" in query
    context = json.loads(params[15])
    assert context == {"filterKeys": ["platform", "airline"], "dateRangeDays": 30}
    assert "SECRET" not in params[15]
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "action_count = action_count +" in update_query
    assert update_params[0] == 1


def test_invalid_or_oversized_event_batches_are_rejected_before_connect():
    service, _connection, _cursor = service_with_cursor()
    for events in ([], [event_payload(event_type="unsupported")], [event_payload()] * 51):
        with pytest.raises(ValueError):
            service.record_events({"id": 1}, {}, {"events": events})
    service.source.connect.assert_not_called()


def test_dashboard_combines_page_quality_user_preference_and_paths():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = (12, 3, 2, 75_000, 1_200)
    cursor.fetchall.side_effect = [
        [("comprehensive-analysis", "综合分析", "业务分析", 8, 3, 90_000, 1_500, 21, 1)],
        [("comprehensive-analysis", 9, 1, 2)],
        [(datetime(2026, 10, 9), 12, 3, 75_000)],
        [("overview", "comprehensive-analysis", "综合分析", 6)],
        [
            (1, "数据管理员", "admin", "comprehensive-analysis", "综合分析", 5, 300_000),
            (1, "数据管理员", "admin", "overview", "经营总览", 2, 60_000),
        ],
        [(datetime(2026, 10, 9, 1, 2, 3), 1, "数据管理员", "comprehensive-analysis", "query_failed", "分析接口", "failed", 3200)],
    ]
    result = service.dashboard({"is_admin": True}, "2026-10-09", "2026-10-09")
    assert result["available"] is True
    assert result["summary"]["visits"] == 12
    assert result["summary"]["queryFailureRate"] == 10.0
    assert result["summary"]["emptyResultRate"] == pytest.approx(22.22, abs=0.01)
    assert result["pages"][0]["quickExits"] == 1
    assert result["users"][0]["primaryPageTitle"] == "综合分析"
    assert result["users"][0]["visits"] == 7
    assert result["paths"][0]["fromPageCode"] == "overview"
    assert result["recentEvents"][0]["eventType"] == "query_failed"
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_dashboard_requires_admin_and_missing_table_is_explained():
    service, _connection, _cursor = service_with_cursor()
    with pytest.raises(PermissionError):
        service.dashboard({"is_admin": False}, "2026-10-09", "2026-10-09")
    service.source.connect.side_effect = Exception(1146, "table missing")
    result = service.dashboard({"is_admin": True}, "2026-10-09", "2026-10-09")
    assert result["available"] is False
    assert "建表SQL" in result["error"]
