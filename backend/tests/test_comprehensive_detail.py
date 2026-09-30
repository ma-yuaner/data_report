from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from data_report_api.services import comprehensive_detail as module


def encoded_filters(include_product: bool = False):
    result = {
        "platform": '["CTRIP","携程"]',
        "site": '["CTRIP","LY","乐游携程一部"]',
        "airline": '["AH"]',
        "policy": '["李小青"]',
    }
    if include_product:
        result["product"] = '["CTRIP","携程","公布转私有"]'
    return result


def test_issue_queries_use_mysql_reconcile_wide_table_and_bound_dimensions():
    count_query, data_query, count_params, data_params = module.build_detail_queries(
        database="sibebid",
        business="issue",
        start_date="2026-09-29",
        next_date="2026-09-30",
        filters=module.parse_detail_filters(encoded_filters()),
        page=2,
        page_size=50,
    )

    assert "sibebid.bi_order_issue_profit_reconcile_year" in count_query
    assert "NULLIF(TRIM(src.ota_cname),'')=%s" in count_query
    assert "NULLIF(TRIM(src.ota_site_cname),'')=%s" in count_query
    assert "NULLIF(TRIM(src.marketing_airline),'')=%s" in count_query
    assert "NULLIF(TRIM(src.policy_operator),'')=%s" in count_query
    assert "src.estimated_profit_cny/src.segment_num" in data_query
    assert "ORDER BY src.business_date DESC" in data_query
    assert data_query.endswith("LIMIT %s OFFSET %s")
    assert count_params == [
        "2026-09-29",
        "2026-09-30",
        "携程",
        "乐游携程一部",
        "AH",
        "李小青",
    ]
    assert data_params[-2:] == [50, 50]


@pytest.mark.parametrize(
    ("business", "source_table", "time_field", "airline"),
    [
        ("refund", "bi_order_refund_profit_reconcile_year", "business_date", "marketing_airline"),
        ("change", "bi_order_change_profit_reconcile_year", "stat_date", "marketing_airline"),
        ("ancillary", "bi_aux_pur_year", "create_time", "air_line"),
    ],
)
def test_each_business_uses_its_mysql_wide_table(
    business, source_table, time_field, airline
):
    count_query, data_query, _count_params, _data_params = module.build_detail_queries(
        database="sibebid",
        business=business,
        start_date="2026-09-29",
        next_date="2026-09-30",
        filters={"airline": ["AH"]},
        page=1,
        page_size=20,
    )

    assert f"sibebid.{source_table}" in count_query
    assert f"src.{time_field}>=%s" in count_query
    assert f"NULLIF(TRIM(src.{airline}),'')=%s" in count_query
    assert f"FROM sibebid.{source_table}" in data_query


@pytest.mark.parametrize(
    ("business", "expected_titles"),
    [
        (
            "issue",
            ["OTA平台名称", "站点名称", "出票日期", "OTA订单号", "关联订单号", "出票票号", "业务盈亏原因", "利润备注", "航程", "航司", "航段数", "供应商名称", "预估利润(公式)", "政策员", "出票员", "票数", "单段利润"],
        ),
        (
            "change",
            ["OTA平台名称", "站点名称", "业务日期", "OTA订单号", "关联订单号", "出票票号", "改签单号", "利润备注", "航司", "供应商名称", "预估利润(公式)", "政策员", "操作员", "业绩分类", "票数"],
        ),
        (
            "refund",
            ["OTA平台名称", "站点名称", "业务日期", "OTA订单号", "关联订单号", "出票票号", "利润备注", "航司", "供应商名称", "预估利润(公式)", "实际利润(推算)", "政策员", "操作员", "业绩分类", "票数"],
        ),
        (
            "ancillary",
            ["OTA平台名称", "站点名称", "业务日期", "进单日期", "OTA订单号", "关联订单号", "出票票号", "航司", "供应商名称", "预估利润(公式)", "政策员", "操作员", "业绩分类", "票数"],
        ),
    ],
)
def test_detail_columns_follow_business_workbook(business, expected_titles):
    assert [item.title for item in module.DETAIL_SPECS[business].columns] == expected_titles


def test_product_filter_is_blocked_until_wide_tables_have_matching_field():
    source = MagicMock()
    source.database = "sibebid"
    with patch.object(module, "DataSource", return_value=source):
        service = module.ComprehensiveDetailService({})
        with pytest.raises(ValueError, match="ticket_product_raw"):
            service.details(
                start_value="2026-09-29",
                end_value="2026-09-29",
                business="issue",
                filters=encoded_filters(include_product=True),
            )
    source.connect.assert_not_called()


def test_service_returns_mysql_rows_without_hive_or_demo_fallback():
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    count_cursor = MagicMock()
    data_cursor = MagicMock()
    connection.cursor.side_effect = [count_cursor, data_cursor]
    count_cursor.fetchone.return_value = (1,)
    data_cursor.fetchall.return_value = [
        (
            "携程",
            "乐游携程一部",
            "2026-09-29",
            "ota-1",
            "relation-1",
            "018-1234567890",
            "RPA000",
            "利润备注",
            "HKG-PVG",
            "AH",
            2,
            "供应商A",
            Decimal("12.34000000"),
            "李小青",
            "出票员A",
            3,
            Decimal("6.17000000"),
        )
    ]
    with patch.object(module, "DataSource", return_value=source) as data_source:
        result = module.ComprehensiveDetailService({"DATA_MODE": "hive"}).details(
            start_value="2026-09-29",
            end_value="2026-09-29",
            business="issue",
            filters=encoded_filters(),
        )

    assert result["available"] is True
    assert result["source"] == "MySQL · sibebid.bi_order_issue_profit_reconcile_year"
    assert result["total"] == 1
    assert result["rows"][0]["estimatedProfit"] == "12.34000000"
    assert result["rows"][0]["ticketCount"] == 3
    assert result["rows"][0]["singleSegmentProfit"] == "6.17000000"
    assert result["columns"][0]["title"] == "OTA平台名称"
    assert data_source.call_args.args[0]["DATA_MODE"] == "mysql"
    count_cursor.execute.assert_called_once()
    data_cursor.execute.assert_called_once()
    count_cursor.close.assert_called_once()
    data_cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_detail_range_and_pagination_are_bounded_before_connect():
    with patch.object(module, "DataSource") as data_source:
        data_source.return_value.database = "sibebid"
        service = module.ComprehensiveDetailService({})
        with pytest.raises(ValueError):
            service.details(
                start_value="2026-01-01",
                end_value="2026-09-29",
                business="issue",
                filters={},
            )
        with pytest.raises(ValueError):
            service.details(
                start_value="2026-09-29",
                end_value="2026-09-29",
                business="issue",
                filters={},
                page_size_value=101,
            )
        data_source.return_value.connect.assert_not_called()
