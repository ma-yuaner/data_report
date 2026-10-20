from datetime import date, datetime
from decimal import Decimal

from data_report_api.jobs.target_management import (
    Scope,
    TargetManagementDailyJob,
    _datetime,
    source_daily_sql,
    weekday_progress_rate,
)


def job() -> TargetManagementDailyJob:
    return TargetManagementDailyJob.__new__(TargetManagementDailyJob)


def source_row(**overrides):
    row = {
        "business_date": date(2026, 10, 18),
        "platform_code": "CTRIP",
        "gds_code": "1A",
        "policy_operator_id": 318,
        "policy_operator_name": "政策员A",
        "issued_segments": 3,
        "issued_ticket_count": 2,
        "issued_profit_count": 2,
        "issued_profit": Decimal("30"),
        "loss_amount": Decimal("5"),
        "loss_ticket_count": 1,
        "loss_segment_count": 1,
        "reward_segments": 2,
        "reward_ticket_count": 1,
        "reward_profit_count": 1,
        "reward_profit": Decimal("10"),
        "reward_loss_amount": Decimal("0"),
        "reward_loss_ticket_count": 0,
        "reward_loss_segment_count": 0,
        "eligible_1a_segments": 1,
        "eligible_1a_ticket_count": 1,
        "eligible_1a_profit_count": 1,
        "eligible_1a_profit": Decimal("8"),
        "eligible_1a_loss_amount": Decimal("0"),
        "eligible_1a_loss_ticket_count": 0,
        "eligible_1a_loss_segment_count": 0,
        "source_max_time": datetime(2026, 10, 18, 23, 0),
    }
    row.update(overrides)
    return row


def test_weekday_curve_is_normalized_and_monotonic():
    start = date(2026, 10, 1)
    end = date(2026, 10, 31)

    first = weekday_progress_rate(start, end, start)
    middle = weekday_progress_rate(start, end, date(2026, 10, 15))

    assert Decimal("0") < first < middle < Decimal("1")
    assert weekday_progress_rate(start, end, end) == Decimal("1")


def test_mysql_datetime_strings_are_normalized_for_scheduler_comparison():
    assert _datetime("2026-10-03 09:00:00") == datetime(2026, 10, 3, 9)


def test_source_sql_reproduces_supplied_legacy_filters():
    sql = source_daily_sql("sibedb")

    assert "o.order_status='TICKETED'" in sql
    assert "oi.refund_flag<>3" in sql
    assert "segment.airlift_flag=1" in sql
    assert "oi.reward_trip_count" in sql
    assert "ticket.gds_code='1A'" in sql
    assert "ticket.reward_flag=1" in sql
    assert "adult.age_type<>'INF'" in sql
    assert "oi.issue_ticket_time >= %s" in sql


def test_platform_records_use_real_issued_segments_and_profit():
    scope = Scope(
        scene="PLATFORM", dimension_key="PLATFORM:CTRIP",
        metric_code="ISSUED_AIRLIFT_SEGMENT", platform_code="CTRIP",
    )

    records = job()._records(date(2026, 10, 18), [scope], [source_row()], "BATCH")
    indexed = {record["metric_code"]: record for record in records}

    assert indexed["ISSUED_AIRLIFT_SEGMENT"]["actual_value"] == Decimal("3")
    assert indexed["ISSUED_AIRLIFT_SEGMENT"]["ticket_count"] == 2
    assert indexed["ISSUE_PROFIT"]["actual_value"] == Decimal("30")
    assert indexed["LOSS_AMOUNT"]["actual_value"] == Decimal("5")
    assert indexed["LOSS_TICKET_COUNT"]["actual_value"] == 1


def test_reward_metric_uses_reward_trip_count_not_all_airlift_segments():
    scope = Scope(
        scene="GDS", dimension_key="GDS:1A",
        metric_code="REWARD_SEGMENT", gds_code="1A",
    )

    records = job()._records(date(2026, 10, 18), [scope], [source_row()], "BATCH")
    indexed = {record["metric_code"]: record for record in records}

    assert indexed["REWARD_SEGMENT"]["actual_value"] == Decimal("2")
    assert indexed["REWARD_SEGMENT"]["ticket_count"] == 1
    assert indexed["ISSUE_PROFIT"]["actual_value"] == Decimal("10")


def test_policy_scope_only_sums_selected_member_ids_and_gds():
    scope = Scope(
        scene="POLICY", dimension_key="POLICY:P1:GDS:1A",
        metric_code="REWARD_SEGMENT", gds_code="1A",
        policy_group_code="P1", member_user_ids=(318, 343),
    )
    rows = [
        source_row(policy_operator_id=318, reward_segments=2),
        source_row(policy_operator_id=999, reward_segments=50),
        source_row(policy_operator_id=343, gds_code="1G", reward_segments=30),
    ]

    records = job()._records(date(2026, 10, 18), [scope], rows, "BATCH")

    assert records[0]["actual_value"] == Decimal("2")


def test_missing_source_is_null_and_never_fake_zero():
    scope = Scope(
        scene="PLATFORM", dimension_key="PLATFORM:CTRIP",
        metric_code="ISSUED_AIRLIFT_SEGMENT", platform_code="CTRIP",
    )

    records = job()._records(date(2026, 10, 18), [scope], [], "BATCH")

    assert all(record["actual_value"] is None for record in records)
    assert all(record["data_status"] == "MISSING" for record in records)


def test_incomplete_profit_is_partial_and_null():
    scope = Scope(
        scene="PLATFORM", dimension_key="PLATFORM:CTRIP",
        metric_code="ISSUED_AIRLIFT_SEGMENT", platform_code="CTRIP",
    )
    row = source_row(issued_profit_count=1, issued_ticket_count=2)

    records = job()._records(date(2026, 10, 18), [scope], [row], "BATCH")
    indexed = {record["metric_code"]: record for record in records}

    assert indexed["ISSUED_AIRLIFT_SEGMENT"]["actual_value"] == Decimal("3")
    assert indexed["ISSUE_PROFIT"]["actual_value"] is None
    assert indexed["ISSUE_PROFIT"]["data_status"] == "PARTIAL"


def test_pending_dates_backfills_missing_and_rebuilds_stale_config():
    class Cursor:
        def __init__(self):
            self.call = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query, _params):
            self.call += 1

        def fetchall(self):
            if self.call == 1:
                return [
                    {"target_item_id": 1, "period_start": date(2026, 10, 1), "period_end": date(2026, 10, 3),
                     "config_updated_at": datetime(2026, 10, 1, 8)},
                    {"target_item_id": 2, "period_start": date(2026, 10, 2), "period_end": date(2026, 10, 3),
                     "config_updated_at": datetime(2026, 10, 3, 9)},
                ]
            return [
                {"target_item_id": 1, "stat_date": date(2026, 10, 1), "etl_updated_at": datetime(2026, 10, 1, 9)},
                {"target_item_id": 1, "stat_date": date(2026, 10, 3), "etl_updated_at": datetime(2026, 10, 3, 10)},
                {"target_item_id": 2, "stat_date": date(2026, 10, 2), "etl_updated_at": datetime(2026, 10, 3, 8)},
                {"target_item_id": 2, "stat_date": date(2026, 10, 3), "etl_updated_at": datetime(2026, 10, 3, 10)},
            ]

    class Connection:
        def cursor(self, *_args):
            return Cursor()

        def close(self):
            pass

    instance = job()
    instance.target_database = "sibebid"
    instance.main = type("Source", (), {"connect": lambda _self: Connection()})()

    assert instance.pending_dates(date(2026, 10, 3)) == [
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]
