from datetime import datetime, timedelta

import pytest

from data_report_api.services.target_etl_trigger import TargetEtlTriggerService
from data_report_api.target_management_daily import TargetManagementDailyJob
from data_report_api.time_utils import business_now


def trigger_service() -> TargetEtlTriggerService:
    instance = TargetEtlTriggerService.__new__(TargetEtlTriggerService)
    instance.database = "sibebid"
    instance.cooldown_seconds = 120
    instance.lock_wait_seconds = 30
    instance.stale_seconds = 7200
    return instance


def test_public_trigger_status_keeps_real_counts_and_active_state():
    result = trigger_service()._public({
        "id": 8,
        "status": "RUNNING",
        "trigger_type": "MANUAL",
        "requested_by_name": "管理员",
        "requested_at": datetime(2026, 10, 19, 17, 0),
        "started_at": datetime(2026, 10, 19, 17, 0, 2),
        "finished_at": None,
        "data_through_date": datetime(2026, 10, 19),
        "processed_dates": 2,
        "dws_rows": 540,
        "ads_rows": 20,
        "error_message": None,
    })

    assert result["status"] == "RUNNING"
    assert result["canTrigger"] is False
    assert result["processedDates"] == 2
    assert result["dwsRows"] == 540
    assert result["adsRows"] == 20


def test_trigger_requires_target_management_permission():
    with pytest.raises(PermissionError):
        trigger_service().trigger({"permissions": ["business_config.target_progress.view"]})


def test_cooldown_uses_request_time_without_inventing_state():
    service = trigger_service()
    row = {
        "status": "SUCCEEDED",
        "requested_at": business_now().replace(tzinfo=None) - timedelta(seconds=30),
    }

    remaining = service._cooldown(row)

    assert 89 <= remaining <= 90


class LockCursor:
    def __init__(self, acquired: int):
        self.acquired = acquired
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append((query, params))

    def fetchone(self):
        return (self.acquired,)


class LockConnection:
    def __init__(self, acquired: int):
        self.cursor_instance = LockCursor(acquired)
        self.closed = False

    def cursor(self, *_args):
        return self.cursor_instance

    def close(self):
        self.closed = True


class LockSource:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def test_daily_job_advisory_lock_is_held_until_explicit_release():
    connection = LockConnection(1)
    job = TargetManagementDailyJob.__new__(TargetManagementDailyJob)
    job.main = LockSource(connection)

    held = job.acquire_run_lock(3)

    assert held is connection
    assert connection.closed is False
    assert "GET_LOCK" in connection.cursor_instance.queries[0][0]
    TargetManagementDailyJob.release_run_lock(held)
    assert "RELEASE_LOCK" in connection.cursor_instance.queries[1][0]
    assert connection.closed is True


def test_daily_job_closes_connection_when_advisory_lock_is_busy():
    connection = LockConnection(0)
    job = TargetManagementDailyJob.__new__(TargetManagementDailyJob)
    job.main = LockSource(connection)

    assert job.acquire_run_lock() is None
    assert connection.closed is True
