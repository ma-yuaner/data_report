from datetime import date, datetime
from decimal import Decimal

from data_report_api.jobs.target_management import (
    Scope,
    TargetManagementDailyJob,
    _datetime,
    source_daily_sql,
    calendar_progress_rate,
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
        "policy_total_segments": 4,
        "policy_ticket_count": 2,
        "policy_profit_count": 2,
        "policy_profit": Decimal("30"),
        "policy_loss_amount": Decimal("5"),
        "policy_loss_ticket_count": 1,
        "policy_loss_segment_count": 1,
        "reward_segments": 2,
        "reward_ticket_count": 1,
        "reward_profit_count": 1,
        "reward_profit": Decimal("10"),
        "reward_loss_amount": Decimal("0"),
        "reward_loss_ticket_count": 0,
        "reward_loss_segment_count": 0,
        "eligible_reward_segments": 1,
        "eligible_reward_ticket_count": 1,
        "eligible_reward_profit_count": 1,
        "eligible_reward_profit": Decimal("8"),
        "eligible_reward_loss_amount": Decimal("0"),
        "eligible_reward_loss_ticket_count": 0,
        "eligible_reward_loss_segment_count": 0,
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


def test_calendar_progress_uses_elapsed_days_over_total_days():
    start = date(2026, 10, 1)
    end = date(2026, 10, 31)

    first = calendar_progress_rate(start, end, start)
    middle = calendar_progress_rate(start, end, date(2026, 10, 15))

    assert first == Decimal(1) / Decimal(31)
    assert middle == Decimal(15) / Decimal(31)
    assert calendar_progress_rate(start, end, end) == Decimal("1")


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


def test_gds_reward_metric_uses_eligible_airlift_segments():
    scope = Scope(
        scene="GDS", dimension_key="GDS:1A",
        metric_code="REWARD_SEGMENT", gds_code="1A", department_code="SD01", owner_name="袁健",
    )

    records = job()._records(date(2026, 10, 18), [scope], [source_row()], "BATCH")
    indexed = {record["metric_code"]: record for record in records}

    assert indexed["REWARD_SEGMENT"]["actual_value"] == Decimal("1")
    assert indexed["REWARD_SEGMENT"]["ticket_count"] == 1
    assert indexed["ISSUE_PROFIT"]["actual_value"] == Decimal("8")


def test_policy_scope_uses_group_leader_department_and_gds():
    scope = Scope(
        scene="POLICY", dimension_key="POLICY:P1:GDS:1A",
        metric_code="REWARD_SEGMENT", gds_code="1A",
        policy_group_code="P1", policy_leader_name="政策员A", department_code="SD01",
    )
    rows = [
        source_row(policy_operator_id=318, reward_segments=2),
        source_row(policy_operator_id=999, policy_operator_name="政策员B", reward_segments=50),
        source_row(policy_operator_id=343, gds_code="1G", reward_segments=30),
        source_row(
            policy_operator_id=318, gds_code="AVIA", reward_segments=0,
            policy_total_segments=5, policy_ticket_count=1, policy_profit_count=1,
            policy_profit=Decimal("12"), policy_loss_amount=Decimal("0"),
            policy_loss_ticket_count=0, policy_loss_segment_count=0,
        ),
    ]

    records = job()._records(date(2026, 10, 18), [scope], rows, "BATCH")
    completion = next(record for record in records if record["metric_code"] == "REWARD_SEGMENT")
    summary = {
        record["metric_code"]: record
        for record in records if record["dimension_key"] == "POLICY_LEADER:P1:SUMMARY"
    }

    assert completion["actual_value"] == Decimal("2")
    assert completion["dimension_key"] == "POLICY:P1:GDS:1A"
    assert summary["POLICY_TOTAL_SEGMENT"]["actual_value"] == Decimal("13")
    assert summary["ISSUE_PROFIT"]["actual_value"] == Decimal("72")


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
                     "target_scene": "PLATFORM", "metric_code": "ISSUED_AIRLIFT_SEGMENT",
                     "platform_code": "CTRIP", "gds_code": "", "policy_group_code": "",
                     "department_code": "", "owner_user_id": None,
                     "config_updated_at": datetime(2026, 10, 1, 8)},
                    {"target_item_id": 2, "period_start": date(2026, 10, 2), "period_end": date(2026, 10, 3),
                     "target_scene": "GDS", "metric_code": "REWARD_SEGMENT",
                     "platform_code": "", "gds_code": "1A", "policy_group_code": "",
                     "department_code": "SD01", "owner_user_id": 1,
                     "config_updated_at": datetime(2026, 10, 3, 9)},
                ]
            if self.call == 2:
                return [
                {"target_item_id": 1, "stat_date": date(2026, 10, 1), "etl_updated_at": datetime(2026, 10, 1, 9)},
                {"target_item_id": 1, "stat_date": date(2026, 10, 3), "etl_updated_at": datetime(2026, 10, 3, 10)},
                {"target_item_id": 2, "stat_date": date(2026, 10, 2), "etl_updated_at": datetime(2026, 10, 3, 8)},
                {"target_item_id": 2, "stat_date": date(2026, 10, 3), "etl_updated_at": datetime(2026, 10, 3, 10)},
                ]
            return [
                {"dimension_key": "PLATFORM:CTRIP", "metric_code": "ISSUED_AIRLIFT_SEGMENT", "business_date": date(2026, 10, 1)},
                {"dimension_key": "PLATFORM:CTRIP", "metric_code": "ISSUED_AIRLIFT_SEGMENT", "business_date": date(2026, 10, 3)},
                {"dimension_key": "GDS:1A:DEPT:SD01:OWNER:1", "metric_code": "REWARD_SEGMENT", "business_date": date(2026, 10, 2)},
                {"dimension_key": "GDS:1A:DEPT:SD01:OWNER:1", "metric_code": "REWARD_SEGMENT", "business_date": date(2026, 10, 3)},
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
