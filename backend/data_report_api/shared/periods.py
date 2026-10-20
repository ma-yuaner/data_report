"""Existing date contracts; defaults and range semantics are intentionally distinct."""

from datetime import date, datetime, timedelta, timezone

from ..time_utils import business_now


def parse_profit_period(start_value: str | None, end_value: str | None) -> tuple[date, date]:
    today = business_now().date()
    try:
        start = date.fromisoformat(start_value) if start_value else today
        end = date.fromisoformat(end_value) if end_value else today
    except ValueError as error:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if (end - start).days > 366:
        raise ValueError("单次查询范围不能超过 366 天")
    return start, end


def parse_analysis_period(start: str | None, end: str | None) -> tuple[date, date]:
    today = datetime.now(timezone(timedelta(hours=8))).date()
    try:
        first = date.fromisoformat(start or today.isoformat())
        last = date.fromisoformat(end or first.isoformat())
        if start and first.isoformat() != start or end and last.isoformat() != end:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("日期必须为YYYY-MM-DD格式") from None
    if last < first or (last - first).days > 365:
        raise ValueError("结束日期不能早于开始日期，单次范围不能超过366天")
    return first, last
