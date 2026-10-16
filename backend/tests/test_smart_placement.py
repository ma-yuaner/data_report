from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from data_report_api.services import smart_placement as smart_placement_module
from data_report_api.services.smart_placement import (
    SmartPlacementService,
    SmartPlacementUnavailable,
)


def service_with_cursor():
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    cursor = connection.cursor.return_value
    return SmartPlacementService({}, source=source), connection, cursor


def task_payload(**changes):
    values = {
        "opportunityName": "东南亚航线增量机会",
        "opportunitySource": "MANUAL",
        "analysisStartDate": "2026-09-01",
        "analysisEndDate": "2026-09-30",
        "platformCode": "CTRIP",
        "platformName": "携程",
        "siteCode": "CTRIP_01",
        "siteName": "乐游携程一部",
        "airlineCode": "HO",
        "departureCode": "PVG",
        "arrivalCode": "KUL",
        "journeyType": "ROUND_TRIP",
        "segmentType": "直达",
        "flightNos": "HO1355,HO1356",
        "includeCabins": "Y,B,M",
        "excludeCabins": "X,N",
        "productType": "公布转私有",
        "orderSource": "平台手工订单",
        "advanceSaleDays": 14,
        "placementMethod": "下调20元后测试投放",
        "lossThresholdMin": 0,
        "lossThresholdMax": 30,
        "longTerm": False,
        "suggestedEffectiveStart": "2026-10-11 00:00:00",
        "suggestedEffectiveEnd": "2026-10-18 23:59:59",
        "historicalTicketCount": 128,
        "historicalProfitCny": "3660.25",
        "estimatedMonthTicketCount": 40,
        "estimatedMonthProfitCny": "1200.00",
        "analysisConclusion": "历史订单能够支撑小范围验证",
        "priority": "HIGH",
        "expectedCompleteAt": "2026-10-10 18:00:00",
        "submit": True,
    }
    values.update(changes)
    return values


def test_create_task_persists_separate_scope_and_excluded_cabins():
    service, connection, cursor = service_with_cursor()
    cursor.lastrowid = 17

    result = service.create_task(
        {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.create"]},
        task_payload(),
    )

    assert result["id"] == 17
    assert result["status"] == "PENDING_DATA_REVIEW"
    insert_query, insert_params = cursor.execute.call_args_list[0].args
    assert "platform_code,platform_name" in insert_query
    assert "departure_code,arrival_code" in insert_query
    assert "journey_type,segment_type" in insert_query
    assert "advance_sale_days" in insert_query
    assert "loss_threshold_min,loss_threshold_max,long_term_flag" in insert_query
    assert "include_cabins,exclude_cabins" in insert_query
    assert "Y,B,M" in insert_params
    assert "X,N" in insert_params
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()


def test_create_task_normalizes_multiple_order_sources():
    service, connection, cursor = service_with_cursor()
    cursor.lastrowid = 19

    result = service.create_task(
        {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
        task_payload(orderSource=["直连订单", "平台手工订单"]),
    )

    assert result["id"] == 19
    insert_params = cursor.execute.call_args_list[0].args[1]
    assert "平台手工订单,直连订单" in insert_params
    connection.commit.assert_called_once()


def test_create_task_rejects_overlapping_cabin_rules_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="不能重复"):
        service.create_task(
            {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
            task_payload(includeCabins="Y,B", excludeCabins="B,X"),
        )

    service.source.connect.assert_not_called()


def test_create_long_term_task_allows_empty_end_time():
    service, connection, cursor = service_with_cursor()
    cursor.lastrowid = 18

    result = service.create_task(
        {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
        task_payload(longTerm=True, suggestedEffectiveEnd=""),
    )

    assert result["status"] == "PENDING_DATA_REVIEW"
    insert_params = cursor.execute.call_args_list[0].args[1]
    assert None in insert_params
    connection.commit.assert_called_once()


def test_create_task_rejects_reversed_loss_threshold_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="亏损阈值上限不能小于下限"):
        service.create_task(
            {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
            task_payload(lossThresholdMin=30, lossThresholdMax=10),
        )

    service.source.connect.assert_not_called()


def test_review_requires_matching_business_role_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(PermissionError, match="没有数据审核权限"):
        service.review_task(
            {"id": 3, "display_name": "政策员", "is_admin": False},
            17,
            {"stage": "DATA_MANAGER", "result": "APPROVED"},
        )

    service.source.connect.assert_not_called()


def test_update_draft_can_resubmit_by_creator():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "DRAFT",
        "created_by_id": 3,
        "submitted_at": None,
    }

    result = service.update_task(
        {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.edit"]},
        17,
        task_payload(),
    )

    assert result == {"id": 17, "taskNo": "SP202610100001", "status": "PENDING_DATA_REVIEW"}
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "status=%s" in update_query
    assert "PENDING_DATA_REVIEW" in update_params
    connection.commit.assert_called_once()


def test_policy_manager_return_resubmits_directly_to_policy_review():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "DRAFT",
        "created_by_id": 3,
        "submitted_at": None,
        "resume_review_stage": "POLICY_MANAGER",
    }

    result = service.update_task(
        {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.edit"]},
        17,
        task_payload(),
    )

    assert result["status"] == "PENDING_POLICY_REVIEW"
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "resume_review_stage=%s" in update_query
    assert "PENDING_POLICY_REVIEW" in update_params
    connection.commit.assert_called_once()


def test_update_draft_rejects_non_creator():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "DRAFT",
        "created_by_id": 3,
        "submitted_at": None,
    }

    with pytest.raises(PermissionError, match="创建人、当前负责人或管理员"):
        service.update_task(
            {"id": 9, "display_name": "其他用户", "is_admin": False, "permissions": ["smart_placement.edit"]},
            17,
            task_payload(submit=False),
        )

    connection.rollback.assert_called_once()


def test_task_detail_serializes_date_fields_without_datetime_separator():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "analysis_start_date": date(2026, 9, 1),
    }
    cursor.fetchall.side_effect = [[], [], [], []]

    result = service.task_detail({"id": 1, "is_admin": True}, 17)

    assert result["task"]["analysisStartDate"] == "2026-09-01"


def test_delete_draft_soft_deletes_and_keeps_audit_log():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "DRAFT",
        "created_by_id": 3,
    }

    result = service.delete_task(
        {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.delete"]},
        17,
    )

    assert result == {"id": 17, "deleted": True}
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "SET is_deleted=1" in update_query
    assert update_params[-1] == 17
    log_query, log_params = cursor.execute.call_args_list[2].args
    assert "INSERT INTO" in log_query
    assert "DELETE" in log_params
    connection.commit.assert_called_once()


def test_delete_running_task_is_rejected():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "MONITORING",
        "created_by_id": 3,
    }

    with pytest.raises(ValueError, match="只有草稿或已驳回"):
        service.delete_task(
            {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.delete"]},
            17,
        )

    connection.rollback.assert_called_once()


def test_creator_can_withdraw_pending_data_review_back_to_draft():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "PENDING_DATA_REVIEW",
        "created_by_id": 3,
    }

    result = service.withdraw_task(
        {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.withdraw"]},
        17,
    )

    assert result == {"id": 17, "taskNo": "SP202610100001", "status": "DRAFT"}
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "status='DRAFT'" in update_query
    assert "resume_review_stage='DATA_MANAGER'" in update_query
    assert update_params[-1] == 17
    _log_query, log_params = cursor.execute.call_args_list[2].args
    assert "WITHDRAW" in log_params
    connection.commit.assert_called_once()


def test_creator_cannot_withdraw_after_data_review_started_next_stage():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "PENDING_POLICY_REVIEW",
        "created_by_id": 3,
    }

    with pytest.raises(ValueError, match="待数据审核任务"):
        service.withdraw_task(
            {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.withdraw"]},
            17,
        )

    connection.rollback.assert_called_once()


def test_data_manager_can_cancel_unclaimed_task_with_required_reason():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "CLAIMABLE",
        "created_by_id": 3,
    }

    result = service.cancel_task(
        {"id": 6, "display_name": "数据运营经理", "permissions": ["smart_placement.cancel"]},
        17,
        {"reason": "业务已取消，不再需要投放"},
    )

    assert result == {"id": 17, "taskNo": "SP202610100001", "status": "CLOSED"}
    update_query, update_params = cursor.execute.call_args_list[1].args
    assert "status='CLOSED'" in update_query
    assert update_params[-1] == 17
    _log_query, log_params = cursor.execute.call_args_list[2].args
    assert "CANCEL" in log_params
    assert "业务已取消，不再需要投放" in log_params
    connection.commit.assert_called_once()


def test_cancel_rejects_claimed_or_monitoring_task():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17,
        "task_no": "SP202610100001",
        "status": "IN_PROGRESS",
        "created_by_id": 3,
    }

    with pytest.raises(ValueError, match="待审核或待认领"):
        service.cancel_task(
            {"id": 6, "display_name": "数据运营经理", "permissions": ["smart_placement.cancel"]},
            17,
            {"reason": "业务取消"},
        )

    connection.rollback.assert_called_once()


def test_cancel_requires_reason_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="作废原因不能为空"):
        service.cancel_task(
            {"id": 6, "display_name": "数据运营经理", "permissions": ["smart_placement.cancel"]},
            17,
            {"reason": ""},
        )

    service.source.connect.assert_not_called()


def test_data_review_approval_does_not_require_confirmation_checkboxes():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.return_value = {
        "id": 17, "task_no": "SP202610100017", "status": "PENDING_DATA_REVIEW",
    }

    result = service.review_task(
        {"id": 1, "display_name": "管理员", "is_admin": True},
        17,
        {"stage": "DATA_MANAGER", "result": "APPROVED"},
    )

    assert result == {"id": 17, "status": "PENDING_POLICY_REVIEW"}
    insert_params = cursor.execute.call_args_list[1].args[1]
    assert insert_params[4:7] == (None, None, None)
    connection.commit.assert_called_once()


def test_batch_review_is_atomic_and_applies_same_result_to_all_tasks():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.side_effect = [
        {"id": 17, "task_no": "SP17", "status": "PENDING_DATA_REVIEW"},
        {"id": 18, "task_no": "SP18", "status": "PENDING_DATA_REVIEW"},
    ]

    result = service.batch_review_tasks(
        {"id": 1, "display_name": "管理员", "is_admin": True},
        {"taskIds": [17, 18], "stage": "DATA_MANAGER", "result": "APPROVED", "adjustedPriority": "HIGH"},
    )

    assert result == {"count": 2, "taskIds": [17, 18], "status": "PENDING_POLICY_REVIEW"}
    assert cursor.execute.call_count == 8
    connection.commit.assert_called_once()


def test_batch_review_rolls_back_when_one_task_is_not_in_expected_stage():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.side_effect = [
        {"id": 17, "task_no": "SP17", "status": "PENDING_DATA_REVIEW"},
        {"id": 18, "task_no": "SP18", "status": "PENDING_POLICY_REVIEW"},
    ]

    with pytest.raises(ValueError, match="SP18"):
        service.batch_review_tasks(
            {"id": 1, "display_name": "管理员", "is_admin": True},
            {"taskIds": [17, 18], "stage": "DATA_MANAGER", "result": "APPROVED"},
        )

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_policy_review_cannot_approve_non_executable_task():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="不能选择审核通过"):
        service.review_task(
            {"id": 1, "display_name": "管理员", "is_admin": True},
            17,
            {
                "stage": "POLICY_MANAGER",
                "result": "APPROVED",
                "policyExecutableLevel": "NOT_EXECUTABLE",
                "riskLevel": "HIGH",
            },
        )

    service.source.connect.assert_not_called()


def test_failed_execution_retry_requires_next_handle_time_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="下次处理时间不能为空"):
        service.register_execution(
            {"id": 3, "display_name": "政策员", "is_admin": False, "permissions": ["smart_placement.execute"]},
            17,
            {
                "result": "FAILED",
                "failureType": "NO_RESOURCE",
                "failureReason": "暂无资源",
                "retryRequired": True,
            },
        )

    service.source.connect.assert_not_called()


def test_successful_execution_compiles_monitor_rule_in_same_transaction(monkeypatch):
    registered_at = datetime(2026, 10, 11, 12, 0)
    monkeypatch.setattr(smart_placement_module, "_now", lambda: registered_at)
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [
        {
            "id": 17,
            "task_no": "SP202610100001",
            "opportunity_name": "东南亚机会",
            "status": "IN_PROGRESS",
            "current_assignee_id": 3,
            "current_assignee_name": "政策员",
            "platform_code": "CTRIP",
            "platform_name": "携程",
            "airline_code": "HO",
            "order_source": "平台手工订单",
        },
        (1,),
    ]
    cursor.lastrowid = 31
    compiler = MagicMock()
    compiler.sync_smart_placement.return_value = {
        "ruleId": 71,
        "ruleCode": "SPM-17-31",
        "ruleVersionId": 72,
        "ruleStatus": "ACTIVE",
    }
    service = SmartPlacementService({}, source=source, monitor_rule_compiler=compiler)

    result = service.register_execution(
        {"id": 3, "display_name": "政策员", "is_admin": False, "permissions": ["smart_placement.execute"]},
        17,
        {
            "result": "SUCCESS",
            "externalPolicyId": "POLICY-001",
            "actualPlacementAt": "2026-10-11 10:00:00",
            "effectiveStartAt": "2026-10-11 10:00:00",
            "longTerm": True,
            "orderSource": [],
            "segmentType": "直达",
            "lossThresholdMin": 0,
            "lossThresholdMax": 30,
        },
    )

    assert result["status"] == "MONITORING"
    assert result["monitorRule"]["ruleCode"] == "SPM-17-31"
    compiler.sync_smart_placement.assert_called_once()
    compiled_execution = compiler.sync_smart_placement.call_args.kwargs["execution"]
    assert compiled_execution["effective_end_at"] is None
    assert compiled_execution["monitoring_start_at"] == registered_at
    assert compiled_execution["order_source"] is None
    insert_query, insert_params = next(
        call.args for call in cursor.execute.call_args_list
        if "INSERT INTO sibebid.smart_placement_execution" in call.args[0]
    )
    assert insert_query.count("%s") == len(insert_params)
    connection.commit.assert_called_once()


def test_successful_execution_rejects_policy_that_expires_before_monitoring_can_start(monkeypatch):
    service, _connection, _cursor = service_with_cursor()
    monkeypatch.setattr(
        smart_placement_module, "_now",
        lambda: datetime(2026, 10, 11, 12, 0),
    )

    with pytest.raises(ValueError, match="最终监控生效时间"):
        service.register_execution(
            {"id": 3, "display_name": "政策员", "permissions": ["smart_placement.execute"]},
            17,
            {
                "result": "SUCCESS",
                "externalPolicyId": "POLICY-002",
                "actualPlacementAt": "2026-10-11 10:00:00",
                "effectiveStartAt": "2026-10-11 10:00:00",
                "effectiveEndAt": "2026-10-11 11:00:00",
                "lossThresholdMin": 0,
                "lossThresholdMax": 30,
            },
        )

    service.source.connect.assert_not_called()


def test_list_orders_returns_real_summary_and_rows():
    service, connection, cursor = service_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "order_count": 2,
            "ticket_count": 3,
            "segment_count": 4,
            "estimated_profit": "88.50",
            "pending_count": 1,
            "active_policy_count": 1,
        },
        (2,),
    ]
    cursor.fetchall.return_value = [
        {
            "id": 11,
            "task_id": 17,
            "ota_order_no": "OTA001",
            "external_policy_id": "POLICY001",
            "attention_status": "PENDING",
        }
    ]

    result = service.list_orders(
        user={"id": 1, "is_admin": True},
        start_date="2026-10-01", end_date="2026-10-09", page=1, page_size=30,
    )

    assert result["available"] is True
    assert result["summary"]["orderCount"] == 2
    assert result["rows"][0]["otaOrderNo"] == "OTA001"
    assert result["period"] == {"startDate": "2026-10-01", "endDate": "2026-10-09"}
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_managed_scope_adds_manager_member_relation_to_order_query():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchone.side_effect = [
        {
            "order_count": 0,
            "ticket_count": 0,
            "segment_count": 0,
            "estimated_profit": "0",
            "pending_count": 0,
            "active_policy_count": 0,
        },
        (0,),
    ]
    cursor.fetchall.return_value = []

    service.list_orders(
        user={
            "id": 6,
            "is_admin": False,
            "data_scopes": {"smart_placement.order": "MANAGED"},
        },
        start_date="2026-10-01",
        end_date="2026-10-09",
    )

    summary_query, summary_params = cursor.execute.call_args_list[0].args
    assert "sys_user_manager_relation" in summary_query
    assert "mr.member_user_id=m.attention_owner_id" in summary_query
    assert summary_params[-2:] == (6, "smart_placement")


def test_dimension_options_returns_canonical_ads_values():
    smart_placement_module._DIMENSION_CACHE.clear()
    service, connection, cursor = service_with_cursor()
    service.source.cache_key = "dimension-test"
    service.source.config = {"PROFIT_CACHE_TTL": 300}
    cursor.fetchall.side_effect = [
        [("CTRIP", "携程")],
        [("CTRIP", "携程", "SITE01", "乐游携程一部")],
        [("ho",)],
        [("CTRIP", "携程", "公布转私有")],
    ]

    result = service.dimension_options()

    assert result["source"] == "MySQL · sibebid.bi_business_profit_dimension_day"
    assert result["platforms"] == [{"value": "携程", "label": "携程", "code": "CTRIP"}]
    assert result["sites"][0]["platformName"] == "携程"
    assert result["airlines"][0]["value"] == "HO"
    assert result["products"][0]["value"] == "公布转私有"
    assert cursor.execute.call_count == 4
    connection.close.assert_called_once()


def test_list_tasks_work_scope_adds_real_server_side_conditions():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchall.side_effect = [[], []]
    cursor.fetchone.return_value = (0,)

    service.list_tasks(user={"id": 8, "permissions": ["smart_placement.edit"]}, scope="mine")

    count_query, count_params = cursor.execute.call_args_list[1].args
    assert "t.current_assignee_id=%s OR t.created_by_id=%s" in count_query
    assert count_params == (8, 8, 8)


def test_analysis_coverage_applies_business_filters_and_returns_real_workflow_state():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchall.return_value = [{
        "id": 31, "task_no": "SP31", "opportunity_name": "EK携程投放",
        "status": "MONITORING", "priority": "HIGH", "platform_name": "携程",
        "site_name": None, "airline_code": "EK", "departure_code": "HKG",
        "arrival_code": "DXB", "route_text": "HKG-DXB", "product_type": None,
        "order_source": "直连订单", "analysis_start_date": date(2026, 10, 1),
        "analysis_end_date": date(2026, 10, 31), "current_assignee_name": "政策员",
        "monitoring_started_at": None, "updated_at": None,
        "external_policy_id": "POL31", "matched_order_count": 7,
    }]

    result = service.analysis_coverage(
        user={"id": 1, "is_admin": True},
        start_value="2026-10-01", end_value="2026-10-15",
        filters={"platform": "携程", "airline": "EK", "route": "HKG-DXB", "orderSource": "直连订单"},
    )

    assert result["summary"] == {
        "taskCount": 1, "monitoringTaskCount": 1,
        "workflowTaskCount": 0, "matchedOrderCount": 7,
        "statusCounts": {status: (1 if status == "MONITORING" else 0) for status in smart_placement_module.TASK_STATUSES},
    }
    assert result["rows"][0]["externalPolicyId"] == "POL31"
    query, params = cursor.execute.call_args.args
    assert "t.platform_name=%s" in query
    assert "t.airline_code=%s" in query
    assert "CONCAT_WS" in query
    assert "FIND_IN_SET(%s,REPLACE(REPLACE(t.order_source,'，',','),' ',''))>0" in query
    assert "NULLIF(TRIM(t.route_text),'') IS NULL" in query
    assert "coverage_execution.effective_start_at" in query
    assert "latest_execution.execution_result='SUCCESS'" in query
    assert "NOT EXISTS" in query
    assert params[:-1] == (
        datetime(2026, 10, 16), datetime(2026, 10, 1), datetime(2026, 10, 1),
        date(2026, 10, 15), date(2026, 10, 1),
        "携程", "EK", "直连订单", "HKG-DXB", "HKG-DXB",
    )
    assert params[-1] == 1001


def test_analysis_coverage_treats_unrestricted_optional_task_fields_as_wildcards():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchall.return_value = []

    service.analysis_coverage(
        user={"id": 1, "is_admin": True},
        start_value="2026-10-01", end_value="2026-10-15",
        filters={"site": "乐游携程一部", "productType": "公布转私有"},
    )

    query, params = cursor.execute.call_args.args
    assert "(NULLIF(TRIM(t.site_name),'') IS NULL OR t.site_name=%s)" in query
    assert "(NULLIF(TRIM(t.product_type),'') IS NULL OR t.product_type=%s)" in query
    assert params[:-1] == (
        datetime(2026, 10, 16), datetime(2026, 10, 1), datetime(2026, 10, 1),
        date(2026, 10, 15), date(2026, 10, 1),
        "乐游携程一部", "公布转私有",
    )


def test_cancel_permission_can_see_all_active_pre_claim_tasks():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchall.side_effect = [[], []]
    cursor.fetchone.return_value = (0,)

    service.list_tasks(user={"id": 6, "permissions": ["smart_placement.cancel"]})

    summary_query, summary_params = cursor.execute.call_args_list[0].args
    assert "PENDING_DATA_REVIEW" in summary_query
    assert "PENDING_POLICY_REVIEW" in summary_query
    assert "CLAIMABLE" in summary_query
    assert summary_params == ()


def test_managed_scope_adds_manager_member_relation_to_task_query():
    service, _connection, cursor = service_with_cursor()
    cursor.fetchall.side_effect = [[], []]
    cursor.fetchone.return_value = (0,)

    service.list_tasks(user={
        "id": 6,
        "permissions": ["smart_placement.review_policy"],
        "data_scopes": {"smart_placement.task": "MANAGED"},
    })

    summary_query, summary_params = cursor.execute.call_args_list[0].args
    assert "sys_user_manager_relation" in summary_query
    assert "mr.member_user_id=t.current_assignee_id" in summary_query
    assert summary_params[-2:] == (6, "smart_placement")


def test_missing_tables_return_actionable_setup_message():
    service, _connection, _cursor = service_with_cursor()
    service.source.connect.side_effect = Exception(1146, "table missing")

    with pytest.raises(SmartPlacementUnavailable, match="smart-placement-schema.sql"):
        service.list_tasks(user={"id": 1, "is_admin": True})


def test_order_period_cannot_exceed_one_year():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="超过366天"):
        service.list_orders(
            user={"id": 1, "is_admin": True},
            start_date="2025-01-01", end_date="2026-10-09",
        )

    service.source.connect.assert_not_called()


def test_attention_update_requires_explicit_function_permission_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(PermissionError, match="没有收单关注处理权限"):
        service.update_attention(
            {"id": 8, "display_name": "只读人员", "is_admin": False, "permissions": []},
            11,
            {"status": "IN_PROGRESS"},
        )

    service.source.connect.assert_not_called()
