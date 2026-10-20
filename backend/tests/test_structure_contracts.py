"""Protect externally visible contracts during structural refactoring."""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.shared.periods import parse_analysis_period, parse_profit_period
from data_report_api.shared.permissions import permission_codes


def test_original_api_route_contract_is_preserved():
    expected = json.loads((Path(__file__).parent / "fixtures/api-route-contract.json").read_text(encoding="utf-8"))
    for _ in range(2):  # app factory must register each domain safely in multiple instances
        app = create_app(TestConfig)
        actual = [
            {"path": rule.rule, "methods": sorted(rule.methods - {"HEAD", "OPTIONS"}), "endpoint": rule.endpoint}
            for rule in app.url_map.iter_rules()
            if rule.endpoint.startswith("api.")
        ]
        assert sorted(actual, key=lambda item: (item["path"], item["methods"])) == expected


def test_shared_periods_keep_distinct_missing_end_defaults():
    with patch("data_report_api.shared.periods.business_now", return_value=datetime(2026, 10, 20, tzinfo=timezone.utc)):
        assert parse_profit_period("2026-10-01", None) == (date(2026, 10, 1), date(2026, 10, 20))
    assert parse_analysis_period("2026-10-01", None) == (date(2026, 10, 1), date(2026, 10, 1))


def test_shared_periods_preserve_existing_range_limits_and_errors():
    assert parse_profit_period("2024-01-01", "2025-01-01") == (date(2024, 1, 1), date(2025, 1, 1))
    with pytest.raises(ValueError, match="单次范围不能超过366天"):
        parse_analysis_period("2024-01-01", "2025-01-01")
    with pytest.raises(ValueError, match="日期必须为YYYY-MM-DD格式"):
        parse_analysis_period("20260101", "2026-01-02")
    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        parse_profit_period("2026-10-20", "2026-10-01")


@pytest.mark.parametrize("user, expected", [
    ({}, set()),
    ({"permissions": ["a", 1]}, {"a", "1"}),
    ({"permission_codes": ["b"]}, {"b"}),
    ({"permissions": [], "permission_codes": ["b"]}, {"b"}),
    ({"permissions": ["a"], "permission_codes": ["b"]}, {"a"}),
])
def test_permission_representation_preserves_legacy_fallback(user, expected):
    assert permission_codes(user) == expected
