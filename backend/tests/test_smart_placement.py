from datetime import date
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
        "routeText": "PVG-KUL,KUL-PVG",
        "flightNos": "HO1355,HO1356",
        "includeCabins": "Y,B,M",
        "excludeCabins": "X,N",
        "productType": "公布转私有",
        "placementMethod": "下调20元后测试投放",
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
    assert "include_cabins,exclude_cabins" in insert_query
    assert "Y,B,M" in insert_params
    assert "X,N" in insert_params
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()


def test_create_task_rejects_overlapping_cabin_rules_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="不能重复"):
        service.create_task(
            {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
            task_payload(includeCabins="Y,B", excludeCabins="B,X"),
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
        {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.create"]},
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
        {"id": 3, "display_name": "数据分析员", "permissions": ["smart_placement.create"]},
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

    with pytest.raises(PermissionError, match="创建人或管理员"):
        service.update_task(
            {"id": 9, "display_name": "其他用户", "is_admin": False, "permissions": ["smart_placement.create"]},
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
    cursor.fetchall.side_effect = [[], [], []]

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
        {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.create"]},
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
            {"id": 3, "display_name": "数据分析员", "is_admin": False, "permissions": ["smart_placement.create"]},
            17,
        )

    connection.rollback.assert_called_once()


def test_data_review_approval_requires_all_confirmations_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="必须完成"):
        service.review_task(
            {"id": 1, "display_name": "管理员", "is_admin": True},
            17,
            {"stage": "DATA_MANAGER", "result": "APPROVED"},
        )

    service.source.connect.assert_not_called()


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
        start_date="2026-10-01", end_date="2026-10-09", page=1, page_size=30,
    )

    assert result["available"] is True
    assert result["summary"]["orderCount"] == 2
    assert result["rows"][0]["otaOrderNo"] == "OTA001"
    assert result["period"] == {"startDate": "2026-10-01", "endDate": "2026-10-09"}
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


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

    service.list_tasks(user={"id": 8, "permissions": ["smart_placement.create"]}, scope="mine")

    count_query, count_params = cursor.execute.call_args_list[1].args
    assert "t.current_assignee_id=%s OR t.created_by_id=%s" in count_query
    assert count_params == (8, 8, 8)


def test_missing_tables_return_actionable_setup_message():
    service, _connection, _cursor = service_with_cursor()
    service.source.connect.side_effect = Exception(1146, "table missing")

    with pytest.raises(SmartPlacementUnavailable, match="smart-placement-schema.sql"):
        service.list_tasks(user={"id": 1, "is_admin": True})


def test_order_period_cannot_exceed_one_year():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="超过366天"):
        service.list_orders(start_date="2025-01-01", end_date="2026-10-09")

    service.source.connect.assert_not_called()
