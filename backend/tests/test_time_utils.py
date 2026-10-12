from datetime import datetime, timezone

from data_report_api.services.smart_placement import _datetime_value
from data_report_api.time_utils import ASIA_SHANGHAI, as_business_naive, business_now


def test_business_now_uses_asia_shanghai_offset():
    current = business_now()

    assert current.tzinfo == ASIA_SHANGHAI
    assert current.utcoffset().total_seconds() == 8 * 60 * 60


def test_aware_datetime_is_normalized_to_shanghai_wall_clock():
    source = datetime(2026, 10, 10, 0, 30, tzinfo=timezone.utc)

    assert as_business_naive(source) == datetime(2026, 10, 10, 8, 30)
    assert _datetime_value("2026-10-10T00:30:00Z", "投放时间") == datetime(
        2026, 10, 10, 8, 30
    )


def test_naive_datetime_is_treated_as_shanghai_wall_clock():
    source = datetime(2026, 10, 10, 9, 15)

    assert as_business_naive(source) is source
