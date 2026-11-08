"""Shared monitoring contracts, conversions and data-source access."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from urllib import request as urlrequest
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from .data_source import DataSource
from ..shared.placement_locations import resolve_airports, resolved_location
from ..time_utils import business_now_naive
from ..shared.daily_segment import TEMPLATE as DAILY_SEGMENT_TEMPLATE, EVENT as DAILY_SEGMENT_EVENT, validate_daily_conditions


LOGGER = logging.getLogger("data_report_api.services.monitoring")
TEMPLATE_TABLE = "monitor_rule_template"
TEMPLATE_FIELD_TABLE = "monitor_rule_template_field"
RULE_TABLE = "monitor_rule"
VERSION_TABLE = "monitor_rule_version"
CONDITION_TABLE = "monitor_rule_condition"
RULE_LOG_TABLE = "monitor_rule_operation_log"
RUN_TABLE = "monitor_run_log"
EVENT_TABLE = "monitor_alert_event"
OUTBOX_TABLE = "monitor_notify_outbox"
EVENT_LOG_TABLE = "monitor_event_operation_log"
EVENT_POLICY_TABLE = "monitor_event_lifecycle_policy"
ACTION_ORDER_TABLE = "monitor_resource_action_order"
ACTION_LOG_TABLE = "monitor_resource_action_operation_log"
FEATURE_TABLE = "rt_order_monitor_feature"
RULE_STAT_TABLE = "monitor_rule_run_stat"
NOTIFY_ENDPOINT_TABLE = "monitor_notify_endpoint"
MESSAGE_TEMPLATE_TABLE = "monitor_message_template"
NOTIFY_ROUTE_TABLE = "monitor_notify_route"
SMART_TASK_TABLE = "smart_placement_task"
SMART_TASK_LOG_TABLE = "smart_placement_operation_log"

SMART_TEMPLATE = "SMART_PLACEMENT_ORDER"
SMART_ORDER_SOURCES = frozenset({"平台手工订单", "直连订单"})
MANUAL_RULE_TEMPLATES = frozenset({
    DAILY_SEGMENT_TEMPLATE,
    "ORDER_SEGMENT_THRESHOLD",
    "GDS_QUERY_RATIO_DAILY",
    "OTA_SUCCESS_RATE_DAILY",
})
RESOURCE_RULE_TEMPLATES = frozenset({"GDS_QUERY_RATIO_DAILY", "OTA_SUCCESS_RATE_DAILY"})
RULE_STATUSES = frozenset({"SCHEDULED", "ACTIVE", "PAUSED", "EXPIRED", "DISABLED"})
EVENT_STATUSES = frozenset({
    "OPEN", "ACKNOWLEDGED", "OBSERVING", "ESCALATED",
    "ACTION_PENDING", "ACTION_IN_PROGRESS", "ACTION_APPLIED",
    "RESOLVED", "IGNORED", "CLOSED",
})
ACTIVE_EVENT_STATUSES = frozenset({
    "OPEN", "ACKNOWLEDGED", "OBSERVING", "ESCALATED",
    "ACTION_PENDING", "ACTION_IN_PROGRESS", "ACTION_APPLIED",
})
TERMINAL_EVENT_STATUSES = frozenset({"RESOLVED", "IGNORED", "CLOSED"})
ACTION_TYPES = frozenset({"RATE_LIMIT", "DISABLE", "EXTEND_DISABLE", "RESTORE"})
ACTION_STATUSES = frozenset({
    "PENDING", "ACCEPTED", "EXECUTING", "SUCCEEDED", "FAILED",
    "CANCELLED", "RECOVERY_PENDING", "RECOVERED",
})
ACTIVE_ACTION_STATUSES = frozenset({"PENDING", "ACCEPTED", "EXECUTING", "SUCCEEDED", "RECOVERY_PENDING"})
EVENT_RESOLUTION_CODES = frozenset({
    "FIXED", "EXPECTED_TEST", "BUSINESS_ACCEPTED", "FALSE_POSITIVE",
    "TECH_ACTION_REQUIRED", "OTHER",
})
ENDPOINT_STATUSES = frozenset({"ACTIVE", "DISABLED"})
NOTIFY_EVENT_CODES = frozenset({
    DAILY_SEGMENT_EVENT,
    "SMART_ORDER_MATCHED", "SMART_ATTENTION_REMINDER",
    "SMART_ATTENTION_ESCALATED", "SMART_POLICY_EXPIRED",
    "RESOURCE_GOVERNANCE_DAILY_ALERT",
})
ANALYSIS_GRAIN_FIELD = "analysis_grain"
ANALYSIS_GRAIN_OPTION_PREFIX = "RESOURCE_GOVERNANCE_GRAIN:"
RESOURCE_GRAIN_DIMENSIONS = {
    "GDS_QUERY_RATIO_DAILY": ("gds_code", "pcc_code"),
    "OTA_SUCCESS_RATE_DAILY": ("ota_code", "ota_site_code", "source_api_group"),
}
SCOPE_FIELD_LABELS = (
    ("gds_code", "GDS"),
    ("pcc_code", "PCC"),
    ("ota_code", "平台"),
    ("ota_site_code", "站点"),
    ("source_api_group", "接口"),
)
RECIPIENT_STRATEGIES = frozenset({"TASK_ASSIGNEE", "ATTENTION_OWNER", "RULE_OWNER", "NONE"})


class MonitoringUnavailable(RuntimeError):
    pass


def is_missing_table(error: Exception) -> bool:
    text = str(error).lower()
    return "doesn't exist" in text or "does not exist" in text or "1146" in text


def dict_row(cursor, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    columns = [item[0] for item in (cursor.description or ())]
    return dict(zip(columns, row))


def dict_rows(cursor, rows: list[Any]) -> list[dict[str, Any]]:
    return [item for row in rows if (item := dict_row(cursor, row)) is not None]


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def grain_option_fields(option_source: Any) -> list[str]:
    text = clean_text(option_source)
    if not text.upper().startswith(ANALYSIS_GRAIN_OPTION_PREFIX):
        return []
    raw = text[len(ANALYSIS_GRAIN_OPTION_PREFIX):]
    return [item.strip() for item in raw.split(",") if item.strip()]


def rule_group_dimensions(version: dict[str, Any] | None) -> list[str]:
    """Read the analysis grain from the rule version snapshot, tolerating legacy versions."""
    if not version:
        return []
    snapshot = json_dict(version.get("condition_snapshot_json"))
    raw = snapshot.get("groupDimensions")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def event_scope(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = json_dict(row.get("match_snapshot_json"))
    raw = snapshot.get("scope")
    return dict(raw) if isinstance(raw, dict) else {}


def action_target(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = json_dict(row.get("target_snapshot_json"))
    raw = snapshot.get("scope")
    return dict(raw) if isinstance(raw, dict) else {}


def resource_target_key(row: dict[str, Any]) -> str:
    scope = event_scope(row)
    parts = [f"{key}={scope[key]}" for key in sorted(scope) if scope.get(key) not in (None, "")]
    return "|".join(parts)[:200] or str(row.get("rule_code") or row.get("entity_key") or "RESOURCE")[:200]


def positive_minutes(value: Any, default: list[int] | None = None) -> list[int]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed = []
    result: list[int] = []
    if isinstance(parsed, list):
        for item in parsed:
            try:
                minutes = int(item)
            except (TypeError, ValueError):
                continue
            if minutes > 0:
                result.append(minutes)
    return result or list(default or [60, 240, 1440])


def scope_field_label(field_code: str) -> str:
    return next((label for code, label in SCOPE_FIELD_LABELS if code == field_code), field_code)


def public_row(row: dict[str, Any], **extra: Any) -> dict[str, Any]:
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part[:1].upper() + part[1:] for part in tail)

    result = {camel(key): json_value(value) for key, value in row.items()}
    result.update(extra)
    return result


def permissions(user: dict[str, Any]) -> set[str]:
    return {str(item) for item in user.get("permissions") or ()}


def require(user: dict[str, Any], permission: str, message: str) -> None:
    if bool(user.get("is_admin")) or permission in permissions(user):
        return
    raise PermissionError(message)


def qualified(database: str, table: str) -> str:
    return f"{database}.{table}"


def first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values())) if row else None
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return row


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def split_values(value: Any) -> list[str]:
    text = clean_text(value).replace("，", ",").replace("/", ",").replace(";", ",")
    return list(dict.fromkeys(item.strip().upper() for item in text.split(",") if item.strip()))


def string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = re.split(r"[,，;；\s]+", clean_text(value))
    return list(dict.fromkeys(clean_text(item) for item in items if clean_text(item)))


def mask_webhook(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    key = text.rsplit("key=", 1)[-1]
    suffix = key[-6:] if len(key) >= 6 else key
    return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=******{suffix}"


def validate_wecom_webhook(value: Any, *, required: bool) -> str:
    text = clean_text(value)
    if not text and not required:
        return ""
    if not text:
        raise ValueError("企业微信Webhook不能为空")
    if not re.fullmatch(r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9_-]+", text):
        raise ValueError("企业微信Webhook格式不正确")
    return text


def wecom_test_message(endpoint_name: str, mentioned_user_ids: list[str], mentioned_mobiles: list[str]) -> dict[str, Any]:
    return {
        "msgtype": "text",
        "text": {
            "content": f"企业数据中台通知测试\n通知群：{endpoint_name}\n配置验证成功后，监控命中会自动发送到本群。",
            "mentioned_list": mentioned_user_ids,
            "mentioned_mobile_list": mentioned_mobiles,
        },
    }


def json_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return string_list(value)
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed = value
    return string_list(parsed)


def time_range(first: Any, last: Any) -> list[str] | None:
    if not first and not last:
        return None
    if isinstance(first, date) and not isinstance(first, datetime):
        first = datetime.combine(first, time.min)
    if isinstance(last, date) and not isinstance(last, datetime):
        last = datetime.combine(last, time.max.replace(microsecond=0))
    return [
        json_value(first) if first else "0001-01-01T00:00:00",
        json_value(last) if last else "9999-12-31T23:59:59",
    ]


def datetime_bound(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.max.replace(microsecond=0) if end_of_day else time.min)
    text = str(value).strip().replace("T", " ")
    try:
        parsed = datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None
    if len(text) == 10:
        return datetime.combine(parsed.date(), time.max.replace(microsecond=0) if end_of_day else time.min)
    return parsed


def smart_order_time_range(task: dict[str, Any], execution: dict[str, Any]) -> list[str] | None:
    """Use the strict intersection of sales dates and actual policy availability."""
    starts = [
        datetime_bound(task.get("order_start_date")),
        datetime_bound(execution.get("actual_placement_at")),
        datetime_bound(execution.get("effective_start_at")),
        datetime_bound(execution.get("monitoring_start_at")),
    ]
    ends = [
        datetime_bound(task.get("order_end_date"), end_of_day=True),
        datetime_bound(execution.get("effective_end_at"), end_of_day=True),
    ]
    actual_starts = [value for value in starts if value is not None]
    actual_ends = [value for value in ends if value is not None]
    first = max(actual_starts) if actual_starts else None
    last = min(actual_ends) if actual_ends else None
    if first and last and first > last:
        raise ValueError("销售日期与实际投放/政策有效期没有交集")
    return time_range(first, last)


def parse_datetime(value: Any, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).strip().replace("T", " ")).replace(tzinfo=None)
    except ValueError as error:
        raise ValueError(f"{field_name}格式不正确") from error


def condition_set(value: Any) -> set[str]:
    if value is None:
        return set()
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,，;/|\s]+", str(value))
    return {str(item).strip().upper() for item in values if str(item).strip()}


def condition_scalar(value: Any) -> str:
    return "" if value is None else str(value).strip().upper()


def compare_condition(actual: Any, operator: str, expected: Any) -> bool:
    operator = operator.upper()
    if operator == "EQ":
        return condition_scalar(actual) == condition_scalar(expected)
    if operator == "NE":
        return condition_scalar(actual) != condition_scalar(expected)
    if operator == "IN":
        return condition_scalar(actual) in condition_set(expected)
    if operator == "NOT_IN":
        return condition_scalar(actual) not in condition_set(expected)
    if operator == "OVERLAP":
        return bool(condition_set(actual) & condition_set(expected))
    if operator in {"CONTAINS_ALL", "SUPERSET_OF"}:
        return condition_set(actual).issuperset(condition_set(expected))
    if operator == "SUBSET_OF":
        actual_set = condition_set(actual)
        return bool(actual_set) and actual_set.issubset(condition_set(expected))
    if operator == "DISJOINT":
        return condition_set(actual).isdisjoint(condition_set(expected))
    if operator == "BETWEEN":
        values = list(expected or []) if isinstance(expected, (list, tuple)) else []
        if len(values) != 2:
            return False
        actual_time = datetime_bound(actual)
        start = datetime_bound(values[0])
        end = datetime_bound(values[1], end_of_day=True)
        return bool(actual_time and start and end and start <= actual_time <= end)
    if operator in {"GT", "GTE", "LT", "LTE"}:
        try:
            left, right = Decimal(str(actual)), Decimal(str(expected))
        except Exception:
            return False
        return {"GT": left > right, "GTE": left >= right, "LT": left < right, "LTE": left <= right}[operator]
    if operator == "IS_NULL":
        return actual in (None, "")
    if operator == "NOT_NULL":
        return actual not in (None, "")
    return False


class MonitoringSource:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        self.source = source or DataSource({**config, "DATA_MODE": "mysql"})

    def _table(self, name: str) -> str:
        return qualified(self.source.database, name)

    def _unavailable(self, error: Exception, message: str) -> MonitoringUnavailable:
        LOGGER.exception(message)
        if is_missing_table(error):
            return MonitoringUnavailable("监控中心表尚未创建，请先执行monitoring-center-schema.sql")
        return MonitoringUnavailable(message)
