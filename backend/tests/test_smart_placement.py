from unittest.mock import MagicMock

import pytest

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
        {"id": 3, "display_name": "数据分析员", "is_admin": False},
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
            {"id": 3, "display_name": "数据分析员"},
            task_payload(includeCabins="Y,B", excludeCabins="B,X"),
        )

    service.source.connect.assert_not_called()


def test_review_requires_admin_before_database_access():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(PermissionError, match="仅管理员"):
        service.review_task(
            {"id": 3, "display_name": "政策员", "is_admin": False},
            17,
            {"stage": "DATA_MANAGER", "result": "APPROVED"},
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


def test_missing_tables_return_actionable_setup_message():
    service, _connection, _cursor = service_with_cursor()
    service.source.connect.side_effect = Exception(1146, "table missing")

    with pytest.raises(SmartPlacementUnavailable, match="smart-placement-schema.sql"):
        service.list_tasks()


def test_order_period_cannot_exceed_one_year():
    service, _connection, _cursor = service_with_cursor()

    with pytest.raises(ValueError, match="超过366天"):
        service.list_orders(start_date="2025-01-01", end_date="2026-10-09")

    service.source.connect.assert_not_called()
