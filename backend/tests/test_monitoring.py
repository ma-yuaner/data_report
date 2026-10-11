from datetime import datetime
from unittest.mock import MagicMock

import pytest

from data_report_api.services.monitoring import MonitorRuleCompiler, MonitoringService


def source_with_cursor():
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    cursor = connection.cursor.return_value
    return source, connection, cursor


def test_smart_placement_compiler_creates_versioned_structured_conditions():
    cursor = MagicMock()
    cursor.fetchone.return_value = (9,)
    cursor.lastrowid = 77
    task = {
        "id": 17,
        "opportunity_name": "东南亚投放机会",
        "current_assignee_id": 8,
        "current_assignee_name": "政策员",
        "platform_code": "CTRIP",
        "site_code": "CTRIP_01",
        "airline_code": "HO",
        "departure_code": "PVG",
        "arrival_code": "KUL",
        "include_cabins": "Y,B",
        "exclude_cabins": "X",
        "product_type": "公布转私有",
        "order_start_date": "2026-10-01",
        "order_end_date": "2026-10-31",
        "travel_start_date": "2026-10-11",
        "travel_end_date": "2026-11-30",
    }
    execution = {
        "external_policy_id": "POLICY-001",
        "effective_start_at": datetime(2026, 10, 11, 12, 0),
        "effective_end_at": datetime(2026, 10, 31, 23, 59),
        "airline_code": "HO",
        "include_cabins": "Y,B",
        "exclude_cabins": "X",
    }

    result = MonitorRuleCompiler().sync_smart_placement(
        cursor=cursor,
        database="sibebid",
        task=task,
        execution_id=31,
        attempt_no=1,
        execution=execution,
        actor=(8, "政策员", "POLICY_OPERATOR"),
        now=datetime(2026, 10, 11, 10, 0),
    )

    assert result["ruleCode"] == "SPM-17-31"
    assert result["ruleStatus"] == "SCHEDULED"
    assert result["conditionCount"] >= 8
    condition_params = [
        call.args[1]
        for call in cursor.execute.call_args_list
        if "monitor_rule_condition" in call.args[0]
    ]
    field_codes = {params[3] for params in condition_params}
    assert {"platform_code", "airline_code", "departure_location_codes", "cabin_codes", "order_time"} <= field_codes
    cabin_roles = {(params[4], params[7]) for params in condition_params if params[3] == "cabin_codes"}
    assert ("SUBSET_OF", "INCLUDE") in cabin_roles
    assert ("DISJOINT", "EXCLUDE") in cabin_roles


def test_monitoring_service_requires_explicit_view_permission():
    source, _connection, _cursor = source_with_cursor()
    service = MonitoringService({}, source=source)

    with pytest.raises(PermissionError, match="没有监控中心查看权限"):
        service.overview({"id": 5, "is_admin": False, "permissions": []})

    source.connect.assert_not_called()


def test_pause_rule_requires_reason_before_database_access():
    source, _connection, _cursor = source_with_cursor()
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="必须填写原因"):
        service.update_rule_status(
            {"id": 1, "display_name": "管理员", "is_admin": True},
            7,
            {"status": "PAUSED"},
        )

    source.connect.assert_not_called()


def test_rule_status_update_is_transactional_and_audited():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {
        "id": 7,
        "status": "ACTIVE",
        "current_version_id": 10,
    }
    service = MonitoringService({}, source=source)

    result = service.update_rule_status(
        {"id": 1, "display_name": "系统管理员", "is_admin": True},
        7,
        {"status": "PAUSED", "note": "业务临时暂停"},
    )

    assert result == {"id": 7, "status": "PAUSED"}
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()
    assert any("monitor_rule_operation_log" in call.args[0] for call in cursor.execute.call_args_list)


def test_manual_order_segment_rule_is_validated_versioned_and_audited():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 4, "template_code": "ORDER_SEGMENT_THRESHOLD", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "segment_count", "field_name": "航段数", "value_type": "NUMBER", "allowed_operators": "GT,GTE", "required_flag": 1},
        {"field_code": "airline_code", "field_name": "航司", "value_type": "STRING_SET", "allowed_operators": "IN", "required_flag": 0},
    ]
    cursor.lastrowid = 22
    service = MonitoringService({}, source=source)

    result = service.create_rule(
        {"id": 1, "display_name": "数据运营经理", "is_admin": True},
        {
            "templateCode": "ORDER_SEGMENT_THRESHOLD",
            "ruleName": "多航段订单提醒",
            "severity": "P1",
            "conditions": [
                {"fieldCode": "segment_count", "operatorCode": "GTE", "value": 6},
                {"fieldCode": "airline_code", "operatorCode": "IN", "value": ["CA", "MU"]},
            ],
        },
    )

    assert result["id"] == 22
    assert result["versionNo"] == 1
    assert result["ruleCode"].startswith("MON-")
    connection.commit.assert_called_once()
    sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "monitor_rule_version" in sql
    assert "monitor_rule_condition" in sql
    assert "monitor_rule_operation_log" in sql


def test_manual_rule_rejects_non_executable_template_before_database_access():
    source, _connection, _cursor = source_with_cursor()
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="仅开放订单航段阈值模板"):
        service.create_rule(
            {"id": 1, "is_admin": True},
            {"templateCode": "METRIC_THRESHOLD", "ruleName": "利润阈值", "conditions": []},
        )

    source.connect.assert_not_called()


def test_event_resolution_requires_note_and_writes_audit_log():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 9, "event_status": "OPEN"}
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="必须填写处理说明"):
        service.update_event_status({"id": 1, "is_admin": True}, 9, {"status": "RESOLVED"})
    source.connect.assert_not_called()

    result = service.update_event_status(
        {"id": 1, "display_name": "管理员", "is_admin": True},
        9,
        {"status": "RESOLVED", "note": "订单已由业务关注"},
    )
    assert result == {"id": 9, "status": "RESOLVED"}
    connection.commit.assert_called_once()
    assert any("monitor_event_operation_log" in call.args[0] for call in cursor.execute.call_args_list)
