"""Application business-time helpers.

Authentication session expiry remains UTC internally. User-facing business and
operation timestamps use China Standard Time, which has no daylight-saving
changes, so a fixed UTC+08:00 offset is reliable even in minimal containers
without the system tzdata package.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


ASIA_SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")


def business_now() -> datetime:
    """Return the current aware Asia/Shanghai time."""
    return datetime.now(ASIA_SHANGHAI)


def business_now_naive() -> datetime:
    """Return Asia/Shanghai wall-clock time for MySQL DATETIME columns."""
    return business_now().replace(tzinfo=None)


def as_business_naive(value: datetime) -> datetime:
    """Normalize an aware datetime to Shanghai; treat naive input as local time."""
    if value.tzinfo is None:
        return value
    return value.astimezone(ASIA_SHANGHAI).replace(tzinfo=None)
