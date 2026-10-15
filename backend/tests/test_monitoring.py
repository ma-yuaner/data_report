import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from data_report_api.services.monitoring import (
    MonitorRuleCompiler,
    MonitoringService,
    _compare_condition,
    _mask_webhook,
    _validate_wecom_webhook,
    _wecom_test_message,
)


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
        "platform_name": "携程",
        "site_code": "CTRIP_01",
        "site_name": "携程一部",
        "order_source": "平台手工订单",
        "airline_code": "HO",
        "departure_code": "PVG",
        "arrival_code": "KUL",
        "journey_type": "ROUND_TRIP",
        "segment_type": "直达",
        "advance_sale_days": 14,
        "loss_threshold_min": Decimal("0"),
        "loss_threshold_max": Decimal("30"),
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
        "actual_placement_at": datetime(2026, 10, 11, 11, 30),
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
    assert {"platform_name", "site_name", "order_source", "airline_code", "departure_location_codes", "cabin_codes", "trip_type", "journey_type", "advance_sale_days", "estimated_profit_cny", "order_time"} <= field_codes
    assert "platform_code" not in field_codes
    assert "route_text" not in field_codes
    cabin_roles = {(params[4], params[7]) for params in condition_params if params[3] == "cabin_codes"}
    assert ("SUBSET_OF", "INCLUDE") in cabin_roles
    assert ("DISJOINT", "EXCLUDE") in cabin_roles
    profit_conditions = {
        (params[4], json.loads(params[6]))
        for params in condition_params
        if params[3] == "estimated_profit_cny"
    }
    assert profit_conditions == {("GTE", "-30"), ("LTE", "0")}


def test_diagnostic_condition_comparison_covers_name_source_and_time():
    assert _compare_condition("携程", "EQ", "携程")
    assert not _compare_condition("直连订单", "EQ", "平台手工订单")
    assert _compare_condition(
        datetime(2026, 10, 12, 15, 0),
        "BETWEEN",
        ["2026-10-12 14:55:00", "2026-10-31 23:59:59"],
    )


def test_monitoring_service_requires_explicit_view_permission():
    source, _connection, _cursor = source_with_cursor()
    service = MonitoringService({}, source=source)

    with pytest.raises(PermissionError, match="没有监控中心查看权限"):
        service.overview({"id": 5, "is_admin": False, "permissions": []})

    source.connect.assert_not_called()


def test_task_monitoring_returns_current_rule_conditions():
    source, _connection, cursor = source_with_cursor()
    service = MonitoringService({}, source=source)
    cursor.fetchone.return_value = {
        "id": 19,
        "rule_code": "SPM-17-31",
        "rule_name": "EK平台手工订单投放",
        "current_version_no": 2,
        "current_version_id": 29,
        "status": "ACTIVE",
    }
    cursor.fetchall.return_value = [{
        "id": 81,
        "rule_version_id": 29,
        "group_no": 1,
        "sort_no": 3,
        "field_code": "order_source",
        "operator_code": "EQ",
        "value_type": "STRING",
        "value_json": '"平台手工订单"',
        "condition_role": "INCLUDE",
    }]

    result = service.task_monitoring({"id": 1, "is_admin": True}, 17)

    assert result["available"] is True
    assert result["rule"]["currentVersionNo"] == 2
    assert result["conditions"] == [{
        "id": 81,
        "ruleVersionId": 29,
        "groupNo": 1,
        "sortNo": 3,
        "fieldCode": "order_source",
        "operatorCode": "EQ",
        "valueType": "STRING",
        "valueJson": '"平台手工订单"',
        "conditionRole": "INCLUDE",
    }]
    condition_query, condition_params = cursor.execute.call_args_list[1].args
    assert "monitor_rule_condition" in condition_query
    assert condition_params == (29,)


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


def test_disabling_smart_placement_rule_ends_linked_task_in_same_transaction():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "id": 7,
            "status": "ACTIVE",
            "current_version_id": 10,
            "source_business_type": "SMART_PLACEMENT_EXECUTION",
            "source_parent_id": 17,
        },
        {"id": 17, "status": "MONITORING"},
    ]
    service = MonitoringService({}, source=source)

    result = service.update_rule_status(
        {"id": 1, "display_name": "系统管理员", "is_admin": True},
        7,
        {"status": "DISABLED", "note": "测试政策清理前停止监控"},
    )

    assert result == {"id": 7, "status": "DISABLED"}
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("UPDATE sibebid.smart_placement_task" in sql for sql in sql_calls)
    assert any("smart_placement_operation_log" in sql for sql in sql_calls)
    connection.commit.assert_called_once()


def test_ended_smart_placement_task_cannot_be_reenabled_from_monitoring_center():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "id": 7,
            "status": "DISABLED",
            "current_version_id": 10,
            "source_business_type": "SMART_PLACEMENT_EXECUTION",
            "source_parent_id": 17,
        },
        {"id": 17, "status": "ENDED"},
    ]
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="不能从监控中心直接启用"):
        service.update_rule_status(
            {"id": 1, "display_name": "系统管理员", "is_admin": True},
            7,
            {"status": "ACTIVE"},
        )

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


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

    with pytest.raises(ValueError, match="仅开放订单航段、GDS查定比和OTA成功率模板"):
        service.create_rule(
            {"id": 1, "is_admin": True},
            {"templateCode": "METRIC_THRESHOLD", "ruleName": "利润阈值", "conditions": []},
        )

    source.connect.assert_not_called()


def test_gds_daily_rule_uses_resource_business_type_and_daily_schedule():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 5, "template_code": "GDS_QUERY_RATIO_DAILY", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "gds_code", "field_name": "GDS", "value_type": "STRING", "allowed_operators": "EQ", "required_flag": 1},
        {"field_code": "search_request_count_all", "field_name": "最小查询量", "value_type": "NUMBER", "allowed_operators": "GTE", "required_flag": 1},
        {"field_code": "query_to_segment_ratio", "field_name": "查定比上限", "value_type": "NUMBER", "allowed_operators": "GT,GTE", "required_flag": 1},
    ]
    cursor.lastrowid = 31
    service = MonitoringService({}, source=source)

    result = service.create_rule(
        {"id": 1, "display_name": "数据运营经理", "is_admin": True},
        {
            "templateCode": "GDS_QUERY_RATIO_DAILY", "ruleName": "1A查定比超过4000",
            "conditions": [
                {"fieldCode": "gds_code", "operatorCode": "EQ", "value": "1A"},
                {"fieldCode": "search_request_count_all", "operatorCode": "GTE", "value": 100},
                {"fieldCode": "query_to_segment_ratio", "operatorCode": "GT", "value": 4000},
            ],
        },
    )

    assert result["id"] == 31
    rule_insert = next(call for call in cursor.execute.call_args_list if "INSERT INTO sibebid.monitor_rule (" in call.args[0])
    assert rule_insert.args[1][4] == "RESOURCE_GOVERNANCE"
    assert rule_insert.args[1][11] == 86400
    connection.commit.assert_called_once()


ANALYSIS_GRAIN_FIELD_ROW = {
    "field_code": "analysis_grain", "field_name": "异常分析粒度",
    "value_type": "ANALYSIS_GRAIN", "allowed_operators": "EQ", "required_flag": 0,
}


def test_gds_rule_snapshot_stores_analysis_grain_and_changes_rule_hash():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 5, "template_code": "GDS_QUERY_RATIO_DAILY", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "gds_code", "field_name": "GDS", "value_type": "STRING", "allowed_operators": "EQ", "required_flag": 1},
        {"field_code": "search_request_count_all", "field_name": "最小查询量", "value_type": "NUMBER", "allowed_operators": "GTE", "required_flag": 1},
        {"field_code": "query_to_segment_ratio", "field_name": "查定比上限", "value_type": "NUMBER", "allowed_operators": "GT,GTE", "required_flag": 1},
        ANALYSIS_GRAIN_FIELD_ROW,
    ]
    cursor.lastrowid = 41
    service = MonitoringService({}, source=source)

    result = service.create_rule(
        {"id": 1, "display_name": "数据运营经理", "is_admin": True},
        {
            "templateCode": "GDS_QUERY_RATIO_DAILY", "ruleName": "1A按PCC查定比超过4000",
            "conditions": [
                {"fieldCode": "gds_code", "operatorCode": "EQ", "value": "1A"},
                {"fieldCode": "search_request_count_all", "operatorCode": "GTE", "value": 100},
                {"fieldCode": "query_to_segment_ratio", "operatorCode": "GT", "value": 4000},
            ],
            "groupDimensions": ["pcc_code"],
        },
    )

    assert result["id"] == 41
    version_insert = next(call for call in cursor.execute.call_args_list if "INSERT INTO sibebid.monitor_rule_version (" in call.args[0])
    snapshot = json.loads(version_insert.args[1][6])
    assert snapshot["groupDimensions"] == ["pcc_code"]
    assert [item["fieldCode"] for item in snapshot["conditions"]] == [
        "gds_code", "search_request_count_all", "query_to_segment_ratio",
    ]
    condition_sql = [call for call in cursor.execute.call_args_list if "INSERT INTO sibebid.monitor_rule_condition (" in call.args[0]]
    assert len(condition_sql) == 3
    assert all("analysis_grain" not in str(call.args[1]) for call in condition_sql)
    connection.commit.assert_called_once()


def test_analysis_grain_rejects_unknown_or_non_resource_dimension():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 5, "template_code": "GDS_QUERY_RATIO_DAILY", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "gds_code", "field_name": "GDS", "value_type": "STRING", "allowed_operators": "EQ", "required_flag": 1},
        {"field_code": "search_request_count_all", "field_name": "最小查询量", "value_type": "NUMBER", "allowed_operators": "GTE", "required_flag": 1},
        {"field_code": "query_to_segment_ratio", "field_name": "查定比上限", "value_type": "NUMBER", "allowed_operators": "GT,GTE", "required_flag": 1},
        ANALYSIS_GRAIN_FIELD_ROW,
    ]
    service = MonitoringService({}, source=source)
    base = {
        "templateCode": "GDS_QUERY_RATIO_DAILY", "ruleName": "1A按维度拆分",
        "conditions": [
            {"fieldCode": "gds_code", "operatorCode": "EQ", "value": "1A"},
            {"fieldCode": "search_request_count_all", "operatorCode": "GTE", "value": 100},
            {"fieldCode": "query_to_segment_ratio", "operatorCode": "GT", "value": 4000},
        ],
    }

    with pytest.raises(ValueError, match="异常分析粒度只支持"):
        service.create_rule({"id": 1, "is_admin": True}, {**base, "groupDimensions": ["segment_count"]})
    with pytest.raises(ValueError, match="异常分析粒度必须是数组"):
        service.create_rule({"id": 1, "is_admin": True}, {**base, "groupDimensions": "pcc_code"})

    connection.rollback.assert_called()
    connection.commit.assert_not_called()


def test_analysis_grain_cannot_be_submitted_as_a_condition():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 5, "template_code": "GDS_QUERY_RATIO_DAILY", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "gds_code", "field_name": "GDS", "value_type": "STRING", "allowed_operators": "EQ", "required_flag": 1},
        ANALYSIS_GRAIN_FIELD_ROW,
    ]
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="不要写入规则条件"):
        service.create_rule(
            {"id": 1, "is_admin": True},
            {
                "templateCode": "GDS_QUERY_RATIO_DAILY", "ruleName": "1A按PCC拆分",
                "conditions": [
                    {"fieldCode": "gds_code", "operatorCode": "EQ", "value": "1A"},
                    {"fieldCode": "analysis_grain", "operatorCode": "EQ", "value": "pcc_code"},
                ],
            },
        )

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_rule_detail_exposes_group_dimensions_per_version():
    from data_report_api.services.monitoring import _rule_group_dimensions

    assert _rule_group_dimensions({"condition_snapshot_json": '{"groupDimensions":["pcc_code","gds_code"]}'}) == ["pcc_code", "gds_code"]
    assert _rule_group_dimensions({"condition_snapshot_json": '{"templateCode":"GDS_QUERY_RATIO_DAILY"}'}) == []
    assert _rule_group_dimensions({"condition_snapshot_json": "not-json"}) == []
    assert _rule_group_dimensions(None) == []


def test_ota_daily_rule_requires_success_rate_and_matching_minimum_volume():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {"id": 6, "template_code": "OTA_SUCCESS_RATE_DAILY", "status": "ACTIVE"}
    cursor.fetchall.return_value = [
        {"field_code": "ota_code", "field_name": "平台编码", "value_type": "STRING", "allowed_operators": "EQ", "required_flag": 1},
        {"field_code": "search_request_count_all", "field_name": "查询最小请求量", "value_type": "NUMBER", "allowed_operators": "GTE", "required_flag": 0},
        {"field_code": "search_success_rate", "field_name": "查询成功率下限", "value_type": "NUMBER", "allowed_operators": "LT,LTE", "required_flag": 0},
    ]
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="查询成功率规则必须同时填写最小请求量"):
        service.create_rule(
            {"id": 1, "display_name": "管理员", "is_admin": True},
            {
                "templateCode": "OTA_SUCCESS_RATE_DAILY", "ruleName": "携程查询成功率低于99%",
                "conditions": [
                    {"fieldCode": "ota_code", "operatorCode": "EQ", "value": "CTRIP"},
                    {"fieldCode": "search_success_rate", "operatorCode": "LT", "value": 99},
                ],
            },
        )

    connection.rollback.assert_called_once()


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
        {"status": "RESOLVED", "resolutionCode": "FIXED", "note": "订单已由业务关注"},
    )
    assert result == {"id": 9, "status": "RESOLVED"}
    connection.commit.assert_called_once()
    assert any("monitor_event_operation_log" in call.args[0] for call in cursor.execute.call_args_list)


def test_event_observation_requires_future_deadline_and_writes_assignment():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "id": 9, "event_status": "OPEN", "business_type": "RESOURCE_GOVERNANCE",
            "severity": "P1", "due_at": None,
        },
        {"id": 8, "full_name": "资源负责人", "username": "owner"},
        {"initial_due_minutes": 240, "max_observe_hours": 120},
    ]
    service = MonitoringService({}, source=source)
    observe_until = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    result = service.update_event_status(
        {"id": 1, "display_name": "管理员", "is_admin": True},
        9,
        {
            "status": "OBSERVING", "assigneeUserId": 8,
            "observeUntil": observe_until, "note": "测试流量，继续观察",
        },
    )

    assert result == {"id": 9, "status": "OBSERVING"}
    update_call = next(call for call in cursor.execute.call_args_list if "SET event_status=%s" in call.args[0])
    assert update_call.args[1][1:3] == (8, "资源负责人")
    connection.commit.assert_called_once()


def test_resource_event_creates_versioned_technical_action_order():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "id": 9, "event_status": "ACKNOWLEDGED", "business_type": "RESOURCE_GOVERNANCE",
            "severity": "P1", "template_code": "GDS_QUERY_RATIO_DAILY", "rule_id": 7,
            "rule_code": "MON-GDS-1", "entity_key": "2026-10-14|GDS:1A / PCC:ABC",
            "match_snapshot_json": '{"scope":{"gds_code":"1A","pcc_code":"ABC"}}',
        },
        None,
        {"id": 8, "full_name": "技术负责人", "username": "tech"},
        {"action_durations_json": "[60,240,1440]", "permanent_after_count": 4},
        (1,),
    ]
    cursor.lastrowid = 55
    service = MonitoringService({}, source=source)

    result = service.create_action_order(
        {"id": 1, "display_name": "数据经理", "is_admin": True},
        9,
        {"actionType": "DISABLE", "assigneeUserId": 8, "requestNote": "临时下线并回写结果"},
    )

    assert result["id"] == 55
    assert result["occurrenceNo"] == 2
    assert result["permanent"] is False
    insert_call = next(call for call in cursor.execute.call_args_list if "INSERT INTO sibebid.monitor_resource_action_order" in call.args[0])
    assert insert_call.args[1][7:10] == ("DISABLE", 2, 0)
    assert any("event_status='ACTION_PENDING'" in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


def test_technical_action_success_updates_order_and_event_with_audit():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "id": 55, "event_id": 9, "action_status": "EXECUTING",
            "planned_start_at": datetime(2026, 10, 15, 9),
            "planned_end_at": datetime(2026, 10, 15, 13),
        },
        {"event_status": "ACTION_IN_PROGRESS"},
    ]
    service = MonitoringService({}, source=source)

    result = service.update_action_order(
        {"id": 8, "display_name": "技术负责人", "is_admin": True},
        55,
        {"action": "SUCCESS", "executionReference": "CHANGE-1001", "note": "已完成下线"},
    )

    assert result == {"id": 55, "status": "SUCCEEDED", "eventStatus": "ACTION_APPLIED"}
    assert any("monitor_resource_action_operation_log" in call.args[0] for call in cursor.execute.call_args_list)
    event_update = next(call for call in cursor.execute.call_args_list if "SET event_status=%s,action_order_id=%s,due_at=%s" in call.args[0])
    assert event_update.args[1][:2] == ("ACTION_APPLIED", 55)
    connection.commit.assert_called_once()


def test_technical_action_requires_explicit_permission():
    source, _connection, _cursor = source_with_cursor()
    service = MonitoringService({}, source=source)

    with pytest.raises(PermissionError, match="没有技术工单查看权限"):
        service.list_action_orders({"id": 3, "is_admin": False, "permissions": []})
    source.connect.assert_not_called()


def test_wecom_endpoint_helpers_mask_validate_and_build_real_mentions():
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abcDEF_123456"
    assert _validate_wecom_webhook(webhook, required=True) == webhook
    assert _mask_webhook(webhook).endswith("******123456")
    payload = _wecom_test_message("智能收单群", ["zhangsan"], ["13800000000"])
    assert payload["text"]["mentioned_list"] == ["zhangsan"]
    assert payload["text"]["mentioned_mobile_list"] == ["13800000000"]


def test_create_wecom_endpoint_persists_secret_but_only_returns_identity():
    source, connection, cursor = source_with_cursor()
    cursor.lastrowid = 19
    service = MonitoringService({}, source=source)

    result = service.save_notify_endpoint(
        {"id": 1, "display_name": "系统管理员", "is_admin": True},
        {
            "endpointName": "智能收单群",
            "webhookUrl": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abcDEF_123456",
            "mentionedUserIds": ["zhangsan"],
            "mentionedMobiles": ["13800000000"],
            "smartPlacementEnabled": True,
            "status": "ACTIVE",
        },
    )

    assert result["id"] == 19
    assert "webhook" not in result
    connection.commit.assert_called_once()
    params = next(call.args[1] for call in cursor.execute.call_args_list if "INSERT INTO" in call.args[0])
    assert "key=abcDEF_123456" in params[3]


def test_notification_route_links_event_template_group_and_dynamic_recipient_strategy():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {"id": 3, "event_code": "SMART_ORDER_MATCHED", "channel": "WECOM"},
        {"id": 12},
    ]
    cursor.lastrowid = 31
    service = MonitoringService({}, source=source)

    result = service.save_notify_route(
        {"id": 1, "display_name": "系统管理员", "is_admin": True},
        {
            "routeName": "智能收单群通知",
            "eventCode": "SMART_ORDER_MATCHED",
            "endpointId": 12,
            "templateId": 3,
            "recipientStrategy": "TASK_ASSIGNEE",
            "priorityNo": 10,
            "status": "ACTIVE",
        },
    )

    assert result == {"id": 31, "eventCode": "SMART_ORDER_MATCHED", "status": "ACTIVE"}
    connection.commit.assert_called_once()
    insert_params = next(
        call.args[1]
        for call in cursor.execute.call_args_list
        if "INSERT INTO" in call.args[0]
    )
    assert insert_params[4:9] == (12, 3, "TASK_ASSIGNEE", 0, 10)


def test_resource_governance_notification_route_is_configurable_without_rebuilding_rule():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.side_effect = [
        {"id": 13, "event_code": "RESOURCE_GOVERNANCE_DAILY_ALERT", "channel": "WECOM"},
        {"id": 7},
    ]
    cursor.lastrowid = 32
    service = MonitoringService({}, source=source)

    result = service.save_notify_route(
        {"id": 1, "display_name": "系统管理员", "is_admin": True},
        {
            "routeName": "资源治理日异常通知",
            "eventCode": "RESOURCE_GOVERNANCE_DAILY_ALERT",
            "endpointId": 7,
            "templateId": 13,
            "recipientStrategy": "RULE_OWNER",
            "priorityNo": 20,
            "status": "ACTIVE",
        },
    )

    assert result == {"id": 32, "eventCode": "RESOURCE_GOVERNANCE_DAILY_ALERT", "status": "ACTIVE"}
    connection.commit.assert_called_once()


def test_external_message_template_rejects_unapproved_order_fields():
    source, connection, cursor = source_with_cursor()
    cursor.fetchone.return_value = {
        "id": 3,
        "field_schema_json": '{"allowedFields":[]}',
        "version_no": 1,
    }
    service = MonitoringService({}, source=source)

    with pytest.raises(ValueError, match="未授权变量"):
        service.update_message_template(
            {"id": 1, "display_name": "系统管理员", "is_admin": True},
            3,
            {
                "titleTemplate": "智能收单提醒",
                "bodyTemplate": "订单号：{otaOrderNo}",
                "status": "ACTIVE",
            },
        )

    connection.rollback.assert_called_once()
