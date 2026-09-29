from __future__ import annotations

from data_report_api.services.risk_upload_loader import (
    composite_key_join,
    composite_key_stats,
    normalized_key_field,
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
    assert stats.missing_ticket == 1
    assert stats.missing_passenger == 2
    assert "FROM lywz.target_table" in cursor.sql
    assert "COUNT(DISTINCT" in cursor.sql
    assert normalized_key_field("", "issue_ticket_no") in cursor.sql
    assert normalized_key_field("", "passenger_name") in cursor.sql
