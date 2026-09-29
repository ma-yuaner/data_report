from __future__ import annotations

from data_report_api.services.risk_upload_loader import (
    composite_key_join,
    composite_key_stats,
    normalized_key_field,
)
from data_report_api.services.risk_upload_definitions import (
    ISSUE_COLUMNS,
    RISK_UPLOAD_DEFINITIONS,
)


class FakeCursor:
    def __init__(self, result: tuple[int, int, int, int, int]):
        self.result = result
        self.sql = ""

    def execute(self, sql: str):
        self.sql = sql

    def fetchone(self):
        return self.result


def test_composite_key_join_matches_ticket_and_normalized_passenger():
    condition = composite_key_join("old_rows", "new_rows")

    assert "TRIM(old_rows.`issue_ticket_no`)=TRIM(new_rows.`issue_ticket_no`)" in condition
    assert (
        "UPPER(TRIM(old_rows.`passenger_name`))="
        "UPPER(TRIM(new_rows.`passenger_name`))"
    ) in condition


def test_composite_key_stats_tracks_missing_and_distinct_keys():
    cursor = FakeCursor((10, 1, 2, 7, 6))

    stats = composite_key_stats(cursor, "lywz.target_table")

    assert stats.total == 10
    assert stats.valid == 7
    assert stats.distinct == 6
    assert stats.missing == {"issue_ticket_no": 1, "passenger_name": 2}
    assert "FROM lywz.target_table" in cursor.sql
    assert "COUNT(DISTINCT" in cursor.sql
    assert normalized_key_field("", "issue_ticket_no") in cursor.sql
    assert normalized_key_field("", "passenger_name") in cursor.sql


def test_issue_upload_uses_latest_excel_tail_fields():
    assert ISSUE_COLUMNS[-4:] == (
        ("月份", "month_name"),
        ("订单来源", "order_source"),
        ("产品类型", "product_type"),
        ("备注【整理】", "sort_remark"),
    )
    headers = {source for source, _target in ISSUE_COLUMNS}
    assert headers.isdisjoint({"正确原因", "计入差错", "备注【原始】"})


def test_change_upload_uses_three_part_merge_key():
    definition = RISK_UPLOAD_DEFINITIONS["change"]
    assert definition.merge_key_fields == (
        "issue_ticket_no",
        "passenger_name",
        "change_order_no",
    )
    assert definition.write_mode == "按出票票号+乘客姓名+改签单号增量更新；0利润删除"
    condition = composite_key_join("old_rows", "new_rows", definition.merge_key_fields)
    assert "TRIM(old_rows.`change_order_no`)=TRIM(new_rows.`change_order_no`)" in condition


def test_change_composite_stats_require_change_order_number():
    cursor = FakeCursor((10, 0, 0, 3, 7, 7))
    stats = composite_key_stats(
        cursor,
        "lywz.change_table",
        RISK_UPLOAD_DEFINITIONS["change"].merge_key_fields,
    )
    assert stats.valid == 7
    assert stats.missing["change_order_no"] == 3
    assert "`change_order_no` IS NOT NULL" in cursor.sql
    assert "TRIM(`change_order_no`)" in cursor.sql
