"""Generic monitoring control plane and smart-placement rule compiler."""
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
from ..time_utils import business_now_naive


LOGGER = logging.getLogger(__name__)
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


def _is_missing_table(error: Exception) -> bool:
    text = str(error).lower()
    return "doesn't exist" in text or "does not exist" in text or "1146" in text


def _dict_row(cursor, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    columns = [item[0] for item in (cursor.description or ())]
    return dict(zip(columns, row))


def _dict_rows(cursor, rows: list[Any]) -> list[dict[str, Any]]:
    return [item for row in rows if (item := _dict_row(cursor, row)) is not None]


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _grain_option_fields(option_source: Any) -> list[str]:
    text = _clean_text(option_source)
    if not text.upper().startswith(ANALYSIS_GRAIN_OPTION_PREFIX):
        return []
    raw = text[len(ANALYSIS_GRAIN_OPTION_PREFIX):]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _rule_group_dimensions(version: dict[str, Any] | None) -> list[str]:
    """Read the analysis grain from the rule version snapshot, tolerating legacy versions."""
    if not version:
        return []
    snapshot = _json_dict(version.get("condition_snapshot_json"))
    raw = snapshot.get("groupDimensions")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _event_scope(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = _json_dict(row.get("match_snapshot_json"))
    raw = snapshot.get("scope")
    return dict(raw) if isinstance(raw, dict) else {}


def _action_target(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = _json_dict(row.get("target_snapshot_json"))
    raw = snapshot.get("scope")
    return dict(raw) if isinstance(raw, dict) else {}


def _resource_target_key(row: dict[str, Any]) -> str:
    scope = _event_scope(row)
    parts = [f"{key}={scope[key]}" for key in sorted(scope) if scope.get(key) not in (None, "")]
    return "|".join(parts)[:200] or str(row.get("rule_code") or row.get("entity_key") or "RESOURCE")[:200]


def _positive_minutes(value: Any, default: list[int] | None = None) -> list[int]:
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


def _scope_field_label(field_code: str) -> str:
    return next((label for code, label in SCOPE_FIELD_LABELS if code == field_code), field_code)


def _public_row(row: dict[str, Any], **extra: Any) -> dict[str, Any]:
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part[:1].upper() + part[1:] for part in tail)

    result = {camel(key): _json_value(value) for key, value in row.items()}
    result.update(extra)
    return result


def _permissions(user: dict[str, Any]) -> set[str]:
    return {str(item) for item in user.get("permissions") or ()}


def _require(user: dict[str, Any], permission: str, message: str) -> None:
    if bool(user.get("is_admin")) or permission in _permissions(user):
        return
    raise PermissionError(message)


def _qualified(database: str, table: str) -> str:
    return f"{database}.{table}"


def _first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values())) if row else None
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return row


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _split_values(value: Any) -> list[str]:
    text = _clean_text(value).replace("，", ",").replace("/", ",").replace(";", ",")
    return list(dict.fromkeys(item.strip().upper() for item in text.split(",") if item.strip()))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = re.split(r"[,，;；\s]+", _clean_text(value))
    return list(dict.fromkeys(_clean_text(item) for item in items if _clean_text(item)))


def _mask_webhook(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    key = text.rsplit("key=", 1)[-1]
    suffix = key[-6:] if len(key) >= 6 else key
    return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=******{suffix}"


def _validate_wecom_webhook(value: Any, *, required: bool) -> str:
    text = _clean_text(value)
    if not text and not required:
        return ""
    if not text:
        raise ValueError("企业微信Webhook不能为空")
    if not re.fullmatch(r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9_-]+", text):
        raise ValueError("企业微信Webhook格式不正确")
    return text


def _wecom_test_message(endpoint_name: str, mentioned_user_ids: list[str], mentioned_mobiles: list[str]) -> dict[str, Any]:
    return {
        "msgtype": "text",
        "text": {
            "content": f"企业数据中台通知测试\n通知群：{endpoint_name}\n配置验证成功后，监控命中会自动发送到本群。",
            "mentioned_list": mentioned_user_ids,
            "mentioned_mobile_list": mentioned_mobiles,
        },
    }


def _json_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return _string_list(value)
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed = value
    return _string_list(parsed)


def _time_range(first: Any, last: Any) -> list[str] | None:
    if not first and not last:
        return None
    if isinstance(first, date) and not isinstance(first, datetime):
        first = datetime.combine(first, time.min)
    if isinstance(last, date) and not isinstance(last, datetime):
        last = datetime.combine(last, time.max.replace(microsecond=0))
    return [
        _json_value(first) if first else "0001-01-01T00:00:00",
        _json_value(last) if last else "9999-12-31T23:59:59",
    ]


def _datetime_bound(value: Any, *, end_of_day: bool = False) -> datetime | None:
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


def _smart_order_time_range(task: dict[str, Any], execution: dict[str, Any]) -> list[str] | None:
    """Use the strict intersection of sales dates and actual policy availability."""
    starts = [
        _datetime_bound(task.get("order_start_date")),
        _datetime_bound(execution.get("actual_placement_at")),
        _datetime_bound(execution.get("effective_start_at")),
        _datetime_bound(execution.get("monitoring_start_at")),
    ]
    ends = [
        _datetime_bound(task.get("order_end_date"), end_of_day=True),
        _datetime_bound(execution.get("effective_end_at"), end_of_day=True),
    ]
    actual_starts = [value for value in starts if value is not None]
    actual_ends = [value for value in ends if value is not None]
    first = max(actual_starts) if actual_starts else None
    last = min(actual_ends) if actual_ends else None
    if first and last and first > last:
        raise ValueError("销售日期与实际投放/政策有效期没有交集")
    return _time_range(first, last)


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).strip().replace("T", " ")).replace(tzinfo=None)
    except ValueError as error:
        raise ValueError(f"{field_name}格式不正确") from error


def _condition_set(value: Any) -> set[str]:
    if value is None:
        return set()
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,，;/|\s]+", str(value))
    return {str(item).strip().upper() for item in values if str(item).strip()}


def _condition_scalar(value: Any) -> str:
    return "" if value is None else str(value).strip().upper()


def _compare_condition(actual: Any, operator: str, expected: Any) -> bool:
    operator = operator.upper()
    if operator == "EQ":
        return _condition_scalar(actual) == _condition_scalar(expected)
    if operator == "NE":
        return _condition_scalar(actual) != _condition_scalar(expected)
    if operator == "IN":
        return _condition_scalar(actual) in _condition_set(expected)
    if operator == "NOT_IN":
        return _condition_scalar(actual) not in _condition_set(expected)
    if operator == "OVERLAP":
        return bool(_condition_set(actual) & _condition_set(expected))
    if operator in {"CONTAINS_ALL", "SUPERSET_OF"}:
        return _condition_set(actual).issuperset(_condition_set(expected))
    if operator == "SUBSET_OF":
        actual_set = _condition_set(actual)
        return bool(actual_set) and actual_set.issubset(_condition_set(expected))
    if operator == "DISJOINT":
        return _condition_set(actual).isdisjoint(_condition_set(expected))
    if operator == "BETWEEN":
        values = list(expected or []) if isinstance(expected, (list, tuple)) else []
        if len(values) != 2:
            return False
        actual_time = _datetime_bound(actual)
        start = _datetime_bound(values[0])
        end = _datetime_bound(values[1], end_of_day=True)
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


class MonitorRuleCompiler:
    """Compile a successful execution or its confirmed amendment into an immutable version."""

    def sync_smart_placement(
        self,
        *,
        cursor,
        database: str,
        task: dict[str, Any],
        execution_id: int,
        attempt_no: int,
        execution: dict[str, Any],
        actor: tuple[int, str, str],
        now: datetime,
        existing_rule: dict[str, Any] | None = None,
        change_reason: str | None = None,
    ) -> dict[str, Any]:
        cursor.execute(
            f"SELECT id FROM {_qualified(database, TEMPLATE_TABLE)} "
            "WHERE template_code=%s AND status='ACTIVE'",
            (SMART_TEMPLATE,),
        )
        template_id = _first_value(cursor.fetchone())
        if not template_id:
            raise MonitoringUnavailable("智能投放监控模板尚未初始化，请先执行monitoring-center-schema.sql")

        effective_start = execution.get("monitoring_start_at") or execution.get("effective_start_at")
        effective_end = execution.get("effective_end_at")
        if effective_end and effective_end <= now:
            status = "EXPIRED"
        elif effective_start and effective_start > now:
            status = "SCHEDULED"
        else:
            status = "ACTIVE"

        conditions: list[dict[str, Any]] = []

        def add(field: str, operator: str, value_type: str, value: Any, role: str = "INCLUDE") -> None:
            if value is None or value == "" or value == []:
                return
            conditions.append({
                "groupNo": 1,
                "sortNo": len(conditions) + 1,
                "fieldCode": field,
                "operatorCode": operator,
                "valueType": value_type,
                "value": value,
                "conditionRole": role,
            })

        platform_name = _clean_text(execution.get("platform_name") or task.get("platform_name"))
        site_name = _clean_text(execution.get("site_name") or task.get("site_name"))
        # The order wide table provides stable Chinese names but not always the
        # same platform/site codes as the policy source.  Smart-placement rules
        # therefore use names as their canonical matching dimensions.
        add("platform_name", "EQ", "STRING", platform_name)
        add("site_name", "EQ", "STRING", site_name)
        raw_order_source = execution.get("order_source") if "order_source" in execution else task.get("order_source")
        order_sources = _split_values(raw_order_source)
        if len(order_sources) == 1:
            add("order_source", "EQ", "STRING", order_sources[0])
        elif order_sources and set(order_sources) != SMART_ORDER_SOURCES:
            add("order_source", "IN", "STRING_SET", order_sources)
        add("airline_code", "IN", "STRING_SET", _split_values(execution.get("airline_code") or task.get("airline_code")))
        add("departure_location_codes", "OVERLAP", "STRING_SET", _split_values(execution.get("departure_code") or task.get("departure_code")))
        add("arrival_location_codes", "OVERLAP", "STRING_SET", _split_values(execution.get("arrival_code") or task.get("arrival_code")))

        add("flight_nos", "OVERLAP", "STRING_SET", _split_values(execution.get("flight_nos") or task.get("flight_nos")))
        add("cabin_codes", "SUBSET_OF", "STRING_SET", _split_values(execution.get("include_cabins") or task.get("include_cabins")))
        add("cabin_codes", "DISJOINT", "STRING_SET", _split_values(execution.get("exclude_cabins") or task.get("exclude_cabins")), "EXCLUDE")
        add("product_type", "IN", "STRING_SET", _split_values(execution.get("product_type") or task.get("product_type")))
        trip_type = _clean_text(task.get("journey_type"))
        trip_type_values = {
            "ONE_WAY": ["ONE_WAY", "单程"],
            "ROUND_TRIP": ["ROUND_TRIP", "往返"],
            "MULTI_CITY": ["MULTI_CITY", "多程", "多城市"],
        }.get(trip_type, [trip_type] if trip_type else [])
        add("trip_type", "IN", "STRING_SET", trip_type_values)
        segment_type = _clean_text(execution.get("segment_type") or task.get("segment_type"))
        if segment_type == "直达":
            add("journey_type", "IN", "STRING_SET", ["直达", "直飞"])
        else:
            add("journey_type", "EQ", "STRING", segment_type)
        add("advance_sale_days", "GTE", "NUMBER", task.get("advance_sale_days"))
        loss_min = execution.get("loss_threshold_min") if "loss_threshold_min" in execution else task.get("loss_threshold_min")
        loss_max = execution.get("loss_threshold_max") if "loss_threshold_max" in execution else task.get("loss_threshold_max")
        if loss_min is not None and loss_max is not None:
            # Business users enter loss as a positive absolute interval. The
            # order feature stores profit, so 0-30 CNY maps to -30 <= profit <= 0.
            add("estimated_profit_cny", "GTE", "NUMBER", -Decimal(str(loss_max)))
            add("estimated_profit_cny", "LTE", "NUMBER", -Decimal(str(loss_min)))
        add("order_time", "BETWEEN", "DATETIME", _smart_order_time_range(task, execution))
        add("first_departure_time", "BETWEEN", "DATETIME", _time_range(task.get("travel_start_date"), task.get("travel_end_date")))

        snapshot = {
            "templateCode": SMART_TEMPLATE,
            "taskId": int(task["id"]),
            "executionId": execution_id,
            "externalPolicyId": execution.get("external_policy_id"),
            "conditionRelation": "AND",
            "conditions": conditions,
        }
        snapshot_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=_json_value)
        rule_hash = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        rule_code = f"SPM-{int(task['id'])}-{execution_id}"
        task_name = _clean_text(task.get("opportunity_name")) or f"智能投放任务{task['id']}"
        policy_id = _clean_text(execution.get("external_policy_id"))
        rule_name = f"{task_name} · {policy_id}"[:200]
        notify_policy = json.dumps({
            "channels": ["IN_APP"],
            "ownerUserId": int(task.get("current_assignee_id") or actor[0]),
            "ownerUserName": _clean_text(task.get("current_assignee_name")) or actor[1],
        }, ensure_ascii=False)

        version_no = int(existing_rule["current_version_no"]) + 1 if existing_rule else 1
        if existing_rule:
            rule_id = int(existing_rule["id"])
            rule_code = existing_rule["rule_code"]
            cursor.execute(
                f"""UPDATE {_qualified(database, RULE_TABLE)} SET status=%s,
                    effective_start_at=%s,effective_end_at=%s,current_version_no=%s,
                    updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s""",
                (status, effective_start, effective_end, version_no, actor[0], actor[1], now, rule_id),
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO {_qualified(database, RULE_TABLE)} (
                    rule_code,rule_name,template_id,template_code,business_type,
                    source_business_type,source_business_id,source_parent_id,
                    owner_user_id,owner_user_name,severity,status,effective_start_at,
                    effective_end_at,schedule_seconds,notify_policy_json,
                    current_version_no,created_by_id,created_by_name,created_at,
                    updated_by_id,updated_by_name,updated_at
                ) VALUES ({','.join(['%s'] * 23)})
                """,
                (
                    rule_code, rule_name, int(template_id), SMART_TEMPLATE, "SMART_PLACEMENT",
                    "SMART_PLACEMENT_EXECUTION", execution_id, int(task["id"]),
                    int(task.get("current_assignee_id") or actor[0]),
                    _clean_text(task.get("current_assignee_name")) or actor[1],
                    "P1", status, effective_start, effective_end, 60, notify_policy,
                    1, actor[0], actor[1], now, actor[0], actor[1], now,
                ),
            )
            rule_id = int(cursor.lastrowid)
        cursor.execute(
            f"""
            INSERT INTO {_qualified(database, VERSION_TABLE)} (
                rule_id,version_no,rule_hash,effective_start_at,effective_end_at,
                condition_relation,condition_snapshot_json,change_reason,status,
                created_by_id,created_by_name,created_at
            ) VALUES ({','.join(['%s'] * 12)})
            """,
            (
                rule_id, version_no, rule_hash, effective_start, effective_end, "AND",
                snapshot_text, change_reason or f"投放第{attempt_no}次执行成功自动生成", "ACTIVE",
                actor[0], actor[1], now,
            ),
        )
        version_id = int(cursor.lastrowid)
        for condition in conditions:
            cursor.execute(
                f"""
                INSERT INTO {_qualified(database, CONDITION_TABLE)} (
                    rule_version_id,group_no,sort_no,field_code,operator_code,
                    value_type,value_json,condition_role,created_at
                ) VALUES ({','.join(['%s'] * 9)})
                """,
                (
                    version_id, condition["groupNo"], condition["sortNo"],
                    condition["fieldCode"], condition["operatorCode"], condition["valueType"],
                    json.dumps(condition["value"], ensure_ascii=False, default=_json_value),
                    condition["conditionRole"], now,
                ),
            )
        cursor.execute(
            f"UPDATE {_qualified(database, RULE_TABLE)} SET current_version_id=%s WHERE id=%s",
            (version_id, rule_id),
        )
        cursor.execute(
            f"""
            INSERT INTO {_qualified(database, RULE_LOG_TABLE)} (
                rule_id,rule_version_id,action_code,from_status,to_status,
                operator_id,operator_name,operation_note,detail_json,created_at
            ) VALUES ({','.join(['%s'] * 10)})
            """,
            (
                rule_id, version_id, "UPDATE" if existing_rule else "CREATE", existing_rule.get("status") if existing_rule else None, status, actor[0], actor[1],
                change_reason or "投放成功后自动生成监控规则",
                json.dumps({"taskId": task["id"], "executionId": execution_id}, ensure_ascii=False), now,
            ),
        )
        return {
            "ruleId": rule_id,
            "ruleCode": rule_code,
            "ruleVersionId": version_id,
            "ruleVersionNo": version_no,
            "ruleStatus": status,
            "conditionCount": len(conditions),
        }


class MonitoringService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        self.source = source or DataSource({**config, "DATA_MODE": "mysql"})

    def _table(self, name: str) -> str:
        return _qualified(self.source.database, name)

    def _unavailable(self, error: Exception, message: str) -> MonitoringUnavailable:
        LOGGER.exception(message)
        if _is_missing_table(error):
            return MonitoringUnavailable("监控中心表尚未创建，请先执行monitoring-center-schema.sql")
        return MonitoringUnavailable(message)

    def overview(self, user: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.center.view", "当前账号没有监控中心查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT COUNT(1) total_rules,
                           SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) active_rules,
                           SUM(CASE WHEN status='SCHEDULED' THEN 1 ELSE 0 END) scheduled_rules,
                           SUM(CASE WHEN status='PAUSED' THEN 1 ELSE 0 END) paused_rules
                    FROM {self._table(RULE_TABLE)}"""
            )
            rule_summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
            today_start = datetime.combine(business_now_naive().date(), time.min)
            cursor.execute(
                f"""SELECT SUM(CASE WHEN occurred_at>=%s THEN 1 ELSE 0 END) total_events,
                           SUM(CASE WHEN occurred_at>=%s AND event_status IN ('OPEN','ESCALATED','ACTION_PENDING') THEN 1 ELSE 0 END) open_events,
                           SUM(CASE WHEN occurred_at>=%s AND event_status IN ('ACKNOWLEDGED','OBSERVING','ACTION_IN_PROGRESS','ACTION_APPLIED') THEN 1 ELSE 0 END) acknowledged_events,
                           SUM(CASE WHEN event_status='ESCALATED' THEN 1 ELSE 0 END) escalated_events,
                           SUM(CASE WHEN event_status IN ('OPEN','ACKNOWLEDGED','OBSERVING','ESCALATED','ACTION_PENDING','ACTION_IN_PROGRESS')
                                      AND due_at IS NOT NULL AND due_at<%s THEN 1 ELSE 0 END) overdue_events
                    FROM {self._table(EVENT_TABLE)}""",
                (today_start, today_start, today_start, business_now_naive()),
            )
            event_summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
            cursor.execute(
                f"""SELECT COUNT(1) pending_notifications
                    FROM {self._table(OUTBOX_TABLE)}
                    WHERE status IN ('PENDING','FAILED')"""
            )
            pending_notifications = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"""SELECT COUNT(1) failed_runs FROM {self._table(RUN_TABLE)}
                    WHERE status='FAILED' AND started_at>=%s""",
                (today_start,),
            )
            failed_runs = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"""SELECT * FROM {self._table(RUN_TABLE)}
                    ORDER BY started_at DESC,id DESC LIMIT 8"""
            )
            recent_runs = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            cursor.execute(
                f"""SELECT * FROM {self._table(EVENT_TABLE)}
                    WHERE event_status IN ('OPEN','ACKNOWLEDGED','OBSERVING','ESCALATED','ACTION_PENDING','ACTION_IN_PROGRESS')
                    ORDER BY FIELD(severity,'P0','P1','P2','P3'),occurred_at DESC,id DESC LIMIT 6"""
            )
            attention_events = [
                _public_row(row, scope=_event_scope(row))
                for row in _dict_rows(cursor, list(cursor.fetchall()))
            ]
            cursor.execute(
                f"""SELECT e.rule_id,e.rule_code,MAX(r.rule_name) rule_name,COUNT(1) event_count
                    FROM {self._table(EVENT_TABLE)} e
                    LEFT JOIN {self._table(RULE_TABLE)} r ON r.id=e.rule_id
                    WHERE e.occurred_at>=%s GROUP BY e.rule_id,e.rule_code
                    ORDER BY event_count DESC,e.rule_id LIMIT 5""",
                (today_start,),
            )
            top_rules = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {
                "available": True,
                "source": f"MySQL · {self.source.database}",
                "ruleSummary": rule_summary,
                "eventSummary": event_summary,
                "pendingNotifications": pending_notifications,
                "failedRuns": failed_runs,
                "recentRuns": recent_runs,
                "attentionEvents": attention_events,
                "topRules": top_rules,
            }
        except PermissionError:
            raise
        except Exception as error:
            raise self._unavailable(error, "监控中心概览查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def templates(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.center.view", "当前账号没有监控模板查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            placeholders = ",".join(["%s"] * len(MANUAL_RULE_TEMPLATES))
            cursor.execute(
                f"SELECT * FROM {self._table(TEMPLATE_TABLE)} WHERE status='ACTIVE' AND template_code IN ({placeholders}) ORDER BY id",
                tuple(sorted(MANUAL_RULE_TEMPLATES)),
            )
            templates = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(
                f"SELECT * FROM {self._table(TEMPLATE_FIELD_TABLE)} WHERE status='ACTIVE' ORDER BY template_id,sort_no,id"
            )
            fields = _dict_rows(cursor, list(cursor.fetchall()))
            fields_by_template: dict[int, list[dict[str, Any]]] = {}
            for field in fields:
                fields_by_template.setdefault(int(field["template_id"]), []).append(_public_row(field))
            result = []
            for template in templates:
                item = _public_row(template)
                item["fields"] = fields_by_template.get(int(template["id"]), [])
                result.append(item)
            return result
        except (ValueError, PermissionError):
            if connection is not None:
                connection.rollback()
            raise
        except Exception as error:
            raise self._unavailable(error, "监控模板查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def _validated_conditions(
        self, cursor, template_id: int, values: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if not isinstance(values, list) or not values:
            raise ValueError("监控规则至少需要一个条件")
        cursor.execute(
            f"SELECT * FROM {self._table(TEMPLATE_FIELD_TABLE)} WHERE template_id=%s AND status='ACTIVE' ORDER BY sort_no,id",
            (template_id,),
        )
        fields = {str(row["field_code"]): row for row in _dict_rows(cursor, list(cursor.fetchall()))}
        grain_fields = {
            code for code, field in fields.items()
            if str(field.get("value_type") or "").strip().upper() == "ANALYSIS_GRAIN"
        }
        result: list[dict[str, Any]] = []
        present: set[str] = set()
        for index, item in enumerate(values, 1):
            if not isinstance(item, dict):
                raise ValueError(f"第{index}个规则条件格式不正确")
            field_code = str(item.get("fieldCode") or "").strip()
            field = fields.get(field_code)
            if not field:
                raise ValueError(f"字段{field_code or index}不属于当前模板")
            if field_code in grain_fields:
                raise ValueError("异常分析粒度请使用独立参数提交，不要写入规则条件")
            operator = str(item.get("operatorCode") or "").strip().upper()
            allowed = {token.strip().upper() for token in str(field["allowed_operators"]).split(",") if token.strip()}
            if operator not in allowed:
                raise ValueError(f"字段{field['field_name']}不支持运算符{operator}")
            value = item.get("value")
            if value in (None, "", []):
                raise ValueError(f"字段{field['field_name']}的条件值不能为空")
            if operator == "BETWEEN" and (not isinstance(value, list) or len(value) != 2):
                raise ValueError(f"字段{field['field_name']}必须填写开始和结束值")
            present.add(field_code)
            result.append({
                "groupNo": max(1, int(item.get("groupNo") or 1)),
                "sortNo": index,
                "fieldCode": field_code,
                "operatorCode": operator,
                "valueType": str(field["value_type"]),
                "value": value,
                "conditionRole": str(item.get("conditionRole") or "INCLUDE").strip().upper(),
            })
        missing = [str(field["field_name"]) for code, field in fields.items() if bool(field["required_flag"]) and code not in present]
        if missing:
            raise ValueError(f"缺少模板必填条件：{','.join(missing)}")
        return result, fields

    def _validated_group_dimensions(
        self, fields: dict[str, dict[str, Any]], template_code: str, values: Any,
    ) -> list[str]:
        """Resolve the resource-governance analysis grain into snapshot ``groupDimensions``."""
        allowed = tuple(RESOURCE_GRAIN_DIMENSIONS.get(template_code) or ())
        if not allowed:
            if values not in (None, "", []):
                raise ValueError("当前模板不支持异常分析粒度")
            return []
        if values in (None, "", []):
            return []
        if not isinstance(values, list):
            raise ValueError("异常分析粒度必须是数组")
        result: list[str] = []
        for item in values:
            dimension = str(item or "").strip()
            if not dimension:
                continue
            if dimension not in allowed:
                labels = "、".join(str(fields[code]["field_name"]) for code in allowed if code in fields)
                raise ValueError(f"异常分析粒度只支持{labels}")
            if dimension not in result:
                result.append(dimension)
        return result

    def create_rule(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有监控规则管理权限")
        template_code = str(values.get("templateCode") or "").strip().upper()
        if template_code not in MANUAL_RULE_TEMPLATES:
            raise ValueError("当前手工配置仅开放订单航段、GDS查定比和OTA成功率模板；智能投放规则由投放成功自动生成")
        rule_name = str(values.get("ruleName") or "").strip()[:200]
        if not rule_name:
            raise ValueError("规则名称不能为空")
        severity = str(values.get("severity") or "P2").strip().upper()
        if severity not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("告警等级不支持")
        effective_start = _parse_datetime(values.get("effectiveStartAt"), "生效时间")
        effective_end = _parse_datetime(values.get("effectiveEndAt"), "失效时间")
        if effective_start and effective_end and effective_end <= effective_start:
            raise ValueError("失效时间必须晚于生效时间")
        current = business_now_naive()
        status = "SCHEDULED" if effective_start and effective_start > current else "ACTIVE"
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        owner_id = int(values.get("ownerUserId") or actor_id)
        owner_name = str(values.get("ownerUserName") or actor_name).strip()[:100]
        raw_notify_policy = values.get("notifyPolicy") if isinstance(values.get("notifyPolicy"), dict) else {}
        endpoint_ids: list[int] = []
        for item in raw_notify_policy.get("wecomEndpointIds") or []:
            try:
                endpoint_ids.append(int(item))
            except (TypeError, ValueError):
                raise ValueError("企业微信通知群ID格式不正确") from None
        endpoint_ids = list(dict.fromkeys(item for item in endpoint_ids if item > 0))
        notify_channels = ["IN_APP"]
        if endpoint_ids:
            notify_channels.append("WECOM")
        notify_policy = {
            "channels": notify_channels,
            "ownerUserId": owner_id,
            "ownerUserName": owner_name,
            "wecomEndpointIds": endpoint_ids,
        }
        is_resource_rule = template_code in RESOURCE_RULE_TEMPLATES
        schedule_seconds = 86400 if is_resource_rule else max(30, min(int(values.get("scheduleSeconds") or 60), 86400))
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(TEMPLATE_TABLE)} WHERE template_code=%s AND status='ACTIVE' FOR UPDATE",
                (template_code,),
            )
            template = _dict_row(cursor, cursor.fetchone())
            if not template:
                raise ValueError("监控模板不存在或已停用")
            if endpoint_ids:
                placeholders = ",".join(["%s"] * len(endpoint_ids))
                cursor.execute(
                    f"SELECT id FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE status='ACTIVE' AND channel='WECOM' AND id IN ({placeholders})",
                    tuple(endpoint_ids),
                )
                found_ids = {int(_first_value(row)) for row in cursor.fetchall()}
                if found_ids != set(endpoint_ids):
                    raise ValueError("选择的企业微信通知群不存在或已停用")
            conditions, template_fields = self._validated_conditions(cursor, int(template["id"]), values.get("conditions"))
            grain_field_codes = {
                code for code, field in template_fields.items()
                if str(field.get("value_type") or "").strip().upper() == "ANALYSIS_GRAIN"
            }
            if grain_field_codes & {str(item["fieldCode"]) for item in conditions}:
                raise ValueError("异常分析粒度请使用独立参数提交，不要写入规则条件")
            if template_code == "OTA_SUCCESS_RATE_DAILY":
                present = {str(item["fieldCode"]) for item in conditions}
                stages = (
                    ("search_success_rate", "search_request_count_all", "查询"),
                    ("verify_success_rate", "verify_request_count_all", "验价"),
                    ("order_success_rate", "order_request_count_all", "生单"),
                )
                selected = [(rate, volume, label) for rate, volume, label in stages if rate in present]
                if not selected:
                    raise ValueError("OTA成功率规则至少需要选择查询、验价或生单中的一个成功率指标")
                missing_volume = [label for rate, volume, label in selected if volume not in present]
                if missing_volume:
                    raise ValueError(f"{','.join(missing_volume)}成功率规则必须同时填写最小请求量")
            group_dimensions = self._validated_group_dimensions(
                template_fields, template_code, values.get("groupDimensions"),
            )
            snapshot = {
                "templateCode": template_code,
                "conditionRelation": "AND",
                "conditions": conditions,
                "groupDimensions": group_dimensions,
            }
            snapshot_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=_json_value)
            rule_hash = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
            rule_code = f"MON-{uuid.uuid4().hex[:20].upper()}"
            cursor.execute(
                f"""INSERT INTO {self._table(RULE_TABLE)} (
                    rule_code,rule_name,template_id,template_code,business_type,
                    owner_user_id,owner_user_name,severity,status,effective_start_at,effective_end_at,
                    schedule_seconds,notify_policy_json,current_version_no,
                    created_by_id,created_by_name,created_at,updated_by_id,updated_by_name,updated_at
                ) VALUES ({','.join(['%s'] * 20)})""",
                (rule_code, rule_name, template["id"], template_code,
                 "RESOURCE_GOVERNANCE" if is_resource_rule else "ORDER_RISK", owner_id, owner_name,
                 severity, status, effective_start, effective_end, schedule_seconds,
                 json.dumps(notify_policy, ensure_ascii=False), 1, actor_id, actor_name, current,
                 actor_id, actor_name, current),
            )
            rule_id = int(cursor.lastrowid)
            cursor.execute(
                f"""INSERT INTO {self._table(VERSION_TABLE)} (
                    rule_id,version_no,rule_hash,effective_start_at,effective_end_at,condition_relation,
                    condition_snapshot_json,change_reason,status,created_by_id,created_by_name,created_at
                ) VALUES ({','.join(['%s'] * 12)})""",
                (rule_id, 1, rule_hash, effective_start, effective_end, "AND", snapshot_text,
                 str(values.get("changeReason") or "新建监控规则")[:500], "ACTIVE", actor_id, actor_name, current),
            )
            version_id = int(cursor.lastrowid)
            for condition in conditions:
                cursor.execute(
                    f"""INSERT INTO {self._table(CONDITION_TABLE)} (
                        rule_version_id,group_no,sort_no,field_code,operator_code,value_type,value_json,condition_role,created_at
                    ) VALUES ({','.join(['%s'] * 9)})""",
                    (version_id, condition["groupNo"], condition["sortNo"], condition["fieldCode"],
                     condition["operatorCode"], condition["valueType"],
                     json.dumps(condition["value"], ensure_ascii=False, default=_json_value),
                     condition["conditionRole"], current),
                )
            cursor.execute(f"UPDATE {self._table(RULE_TABLE)} SET current_version_id=%s WHERE id=%s", (version_id, rule_id))
            cursor.execute(
                f"""INSERT INTO {self._table(RULE_LOG_TABLE)} (
                    rule_id,rule_version_id,action_code,from_status,to_status,operator_id,operator_name,operation_note,created_at
                ) VALUES ({','.join(['%s'] * 9)})""",
                (rule_id, version_id, "CREATE", None, status, actor_id, actor_name,
                 str(values.get("changeReason") or "新建监控规则")[:1000], current),
            )
            connection.commit()
            return {"id": rule_id, "ruleCode": rule_code, "status": status, "versionNo": 1}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "监控规则创建失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_rules(
        self, user: dict[str, Any], *, status: str = "", template: str = "",
        keyword: str = "", page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        _require(user, "monitor.center.view", "当前账号没有监控规则查看权限")
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        where = ["1=1"]
        params: list[Any] = []
        if status:
            normalized = str(status).strip().upper()
            if normalized not in RULE_STATUSES:
                raise ValueError("规则状态不支持")
            where.append("r.status=%s"); params.append(normalized)
        if template:
            where.append("r.template_code=%s"); params.append(str(template).strip().upper())
        if keyword:
            token = f"%{str(keyword).strip()[:100]}%"
            where.append("(r.rule_code LIKE %s OR r.rule_name LIKE %s OR r.owner_user_name LIKE %s)")
            params.extend([token, token, token])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(RULE_TABLE)} r WHERE {condition}", tuple(params))
            total = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"""SELECT r.*,t.template_name,
                           (SELECT COUNT(1) FROM {self._table(EVENT_TABLE)} e WHERE e.rule_id=r.id) hit_count,
                           (SELECT v.condition_snapshot_json FROM {self._table(VERSION_TABLE)} v
                             WHERE v.id=r.current_version_id) current_snapshot_json
                    FROM {self._table(RULE_TABLE)} r
                    JOIN {self._table(TEMPLATE_TABLE)} t ON t.id=r.template_id
                    WHERE {condition}
                    ORDER BY FIELD(r.status,'ACTIVE','SCHEDULED','PAUSED','EXPIRED','DISABLED'),r.updated_at DESC
                    LIMIT %s OFFSET %s""",
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [
                _public_row(
                    row,
                    groupDimensions=_rule_group_dimensions({"condition_snapshot_json": row.get("current_snapshot_json")}),
                )
                for row in _dict_rows(cursor, list(cursor.fetchall()))
            ]
            for row in rows:
                row.pop("currentSnapshotJson", None)
            return {"rows": rows, "total": total, "page": page, "pageSize": page_size}
        except Exception as error:
            raise self._unavailable(error, "监控规则查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def rule_detail(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        _require(user, "monitor.center.view", "当前账号没有监控规则查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(RULE_TABLE)} WHERE id=%s", (rule_id,))
            rule = _dict_row(cursor, cursor.fetchone())
            if not rule:
                raise ValueError("监控规则不存在")
            canonical_platform_name = canonical_site_name = None
            if rule.get("template_code") == SMART_TEMPLATE:
                cursor.execute(
                    f"""SELECT COALESCE(NULLIF(e.platform_name,''),NULLIF(t.platform_name,'')) platform_name,
                               COALESCE(NULLIF(e.site_name,''),NULLIF(t.site_name,'')) site_name
                        FROM {self._table('smart_placement_task')} t
                        LEFT JOIN {self._table('smart_placement_execution')} e ON e.id=%s
                        WHERE t.id=%s""",
                    (rule.get("source_business_id"), rule.get("source_parent_id")),
                )
                canonical_row = _dict_row(cursor, cursor.fetchone()) or {}
                canonical_platform_name = canonical_row.get("platform_name")
                canonical_site_name = canonical_row.get("site_name")
            cursor.execute(f"SELECT * FROM {self._table(VERSION_TABLE)} WHERE rule_id=%s ORDER BY version_no DESC", (rule_id,))
            versions = _dict_rows(cursor, list(cursor.fetchall()))
            version_ids = [int(row["id"]) for row in versions]
            conditions: list[dict[str, Any]] = []
            if version_ids:
                placeholders = ",".join(["%s"] * len(version_ids))
                cursor.execute(
                    f"SELECT * FROM {self._table(CONDITION_TABLE)} WHERE rule_version_id IN ({placeholders}) ORDER BY rule_version_id DESC,group_no,sort_no",
                    tuple(version_ids),
                )
                conditions = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(RULE_LOG_TABLE)} WHERE rule_id=%s ORDER BY id DESC LIMIT 200", (rule_id,))
            logs = _dict_rows(cursor, list(cursor.fetchall()))
            conditions_by_version: dict[int, list[dict[str, Any]]] = {}
            for condition in conditions:
                conditions_by_version.setdefault(int(condition["rule_version_id"]), []).append(_public_row(condition))
            public_versions = []
            for version in versions:
                item = _public_row(version)
                item["conditions"] = conditions_by_version.get(int(version["id"]), [])
                item["groupDimensions"] = _rule_group_dimensions(version)
                public_versions.append(item)
            return {
                "rule": _public_row(rule, groupDimensions=_rule_group_dimensions(versions[0] if versions else None)),
                "versions": public_versions,
                "logs": [_public_row(row) for row in logs],
            }
        except ValueError:
            raise
        except Exception as error:
            raise self._unavailable(error, "监控规则详情查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def diagnose_rule(self, user: dict[str, Any], rule_id: int, ota_order_no: str) -> dict[str, Any]:
        """Explain one rule/order decision without persisting an order×rule log."""
        _require(user, "monitor.center.view", "当前账号没有监控规则诊断权限")
        order_no = str(ota_order_no or "").strip()
        if not order_no:
            raise ValueError("请输入OTA订单号")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(RULE_TABLE)} WHERE id=%s", (rule_id,))
            rule = _dict_row(cursor, cursor.fetchone())
            if not rule:
                raise ValueError("监控规则不存在")
            cursor.execute(
                f"SELECT * FROM {self._table(FEATURE_TABLE)} WHERE ota_order_no=%s ORDER BY source_updated_at DESC,id DESC LIMIT 1",
                (order_no,),
            )
            feature = _dict_row(cursor, cursor.fetchone())
            stages: list[dict[str, Any]] = [{
                "code": "FEATURE",
                "name": "标准特征采集",
                "passed": feature is not None,
                "message": "已找到订单特征" if feature else "标准特征表尚未采集到该订单，请检查特征ETL水位和源宽表create_time",
            }]
            if not feature:
                return {
                    "rule": _public_row(rule), "order": None, "matched": False,
                    "conditions": [], "stages": stages, "recentStats": [],
                }

            cursor.execute(
                f"SELECT * FROM {self._table(CONDITION_TABLE)} WHERE rule_version_id=%s ORDER BY group_no,sort_no",
                (rule["current_version_id"],),
            )
            conditions = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(
                f"SELECT field_code,field_name FROM {self._table(TEMPLATE_FIELD_TABLE)} WHERE template_id=%s",
                (rule["template_id"],),
            )
            field_names = {str(row[0] if not isinstance(row, dict) else row["field_code"]): str(row[1] if not isinstance(row, dict) else row["field_name"]) for row in cursor.fetchall()}
            details: list[dict[str, Any]] = []
            grouped: dict[int, list[bool]] = {}
            for condition in conditions:
                condition = dict(condition)
                legacy_field = str(condition["field_code"])
                if rule.get("template_code") == SMART_TEMPLATE and legacy_field in {"platform_code", "site_code"}:
                    replacement = canonical_platform_name if legacy_field == "platform_code" else canonical_site_name
                    if not replacement:
                        continue
                    condition["field_code"] = "platform_name" if legacy_field == "platform_code" else "site_name"
                    condition["value_json"] = json.dumps(replacement, ensure_ascii=False)
                try:
                    expected = json.loads(condition["value_json"])
                except (TypeError, json.JSONDecodeError):
                    expected = condition["value_json"]
                field_code = str(condition["field_code"])
                actual = feature.get(field_code)
                passed = _compare_condition(actual, str(condition["operator_code"]), expected)
                group_no = int(condition["group_no"])
                grouped.setdefault(group_no, []).append(passed)
                details.append({
                    "fieldCode": field_code,
                    "fieldName": field_names.get(field_code, field_code),
                    "operatorCode": condition["operator_code"],
                    "expected": _json_value(expected),
                    "actual": _json_value(actual),
                    "passed": passed,
                    "conditionRole": condition.get("condition_role") or "INCLUDE",
                    "groupNo": group_no,
                })
            relation = "AND"
            cursor.execute(f"SELECT condition_relation FROM {self._table(VERSION_TABLE)} WHERE id=%s", (rule["current_version_id"],))
            version_row = cursor.fetchone()
            if version_row:
                relation = str(_first_value(version_row) or "AND").upper()
            group_results = [all(items) for items in grouped.values()]
            conditions_passed = bool(group_results) and (any(group_results) if relation == "OR" else all(group_results))
            rule_runnable = str(rule.get("status")) == "ACTIVE"
            stages.extend([
                {"code": "RULE", "name": "规则运行状态", "passed": rule_runnable, "message": f"当前状态：{rule.get('status')}"},
                {"code": "CONDITIONS", "name": "业务条件匹配", "passed": conditions_passed, "message": "全部条件通过" if conditions_passed else f"{sum(not item['passed'] for item in details)}项条件未通过"},
            ])
            matched = rule_runnable and conditions_passed
            cursor.execute(
                f"SELECT event_no,event_status,occurred_at FROM {self._table(EVENT_TABLE)} WHERE rule_id=%s AND entity_key=%s ORDER BY id DESC LIMIT 1",
                (rule_id, feature["feature_key"]),
            )
            event = _dict_row(cursor, cursor.fetchone())
            stages.append({
                "code": "EVENT", "name": "命中事件落库", "passed": event is not None,
                "message": f"已生成事件{event['event_no']}" if event else ("条件当前通过，但尚未生成事件；请检查匹配任务运行时间" if matched else "条件未通过，不应生成事件"),
            })
            cursor.execute(
                f"SELECT * FROM {self._table(RULE_STAT_TABLE)} WHERE rule_id=%s ORDER BY created_at DESC,id DESC LIMIT 10",
                (rule_id,),
            )
            recent_stats = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {
                "rule": _public_row(rule), "order": _public_row(feature), "event": _public_row(event) if event else None,
                "matched": matched, "conditions": details, "stages": stages, "recentStats": recent_stats,
            }
        except ValueError:
            raise
        except Exception as error:
            raise self._unavailable(error, "监控规则匹配诊断失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_rule_status(self, user: dict[str, Any], rule_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有监控规则管理权限")
        target = str(values.get("status") or "").strip().upper()
        if target not in {"ACTIVE", "PAUSED", "DISABLED"}:
            raise ValueError("规则只支持启用、暂停或停用")
        note = str(values.get("note") or "").strip()[:1000]
        if target in {"PAUSED", "DISABLED"} and not note:
            raise ValueError("暂停或停用规则必须填写原因")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        now = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(RULE_TABLE)} WHERE id=%s FOR UPDATE", (rule_id,))
            rule = _dict_row(cursor, cursor.fetchone())
            if not rule:
                raise ValueError("监控规则不存在")
            old = str(rule["status"])
            if old == "EXPIRED" and target == "ACTIVE":
                raise ValueError("已过期规则不能直接启用，请创建新版本")
            linked_task = None
            linked_task_id = int(rule.get("source_parent_id") or 0)
            is_smart_placement = (
                str(rule.get("source_business_type") or "").upper() == "SMART_PLACEMENT_EXECUTION"
                and linked_task_id > 0
            )
            if is_smart_placement and target in {"ACTIVE", "DISABLED"}:
                cursor.execute(
                    f"SELECT id,status FROM {self._table(SMART_TASK_TABLE)} WHERE id=%s FOR UPDATE",
                    (linked_task_id,),
                )
                linked_task = _dict_row(cursor, cursor.fetchone())
                if not linked_task:
                    raise ValueError("关联的智能投放任务不存在，不能调整监控状态")
                if target == "ACTIVE" and str(linked_task.get("status")) != "MONITORING":
                    raise ValueError("投放政策任务已结束或不在监控中，不能从监控中心直接启用；请回到投放政策调整并重新审核")
            cursor.execute(
                f"UPDATE {self._table(RULE_TABLE)} SET status=%s,updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s",
                (target, actor_id, actor_name, now, rule_id),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(RULE_LOG_TABLE)} (
                    rule_id,rule_version_id,action_code,from_status,to_status,
                    operator_id,operator_name,operation_note,created_at
                ) VALUES ({','.join(['%s'] * 9)})""",
                (rule_id, rule.get("current_version_id"), target, old, target, actor_id, actor_name, note or "规则状态调整", now),
            )
            if target == "DISABLED" and linked_task and str(linked_task.get("status")) == "MONITORING":
                cursor.execute(
                    f"""UPDATE {self._table(SMART_TASK_TABLE)}
                        SET status='ENDED',closed_at=%s,updated_by_id=%s,updated_by_name=%s,
                            version_no=version_no+1,updated_at=%s
                        WHERE id=%s""",
                    (now, actor_id, actor_name, now, linked_task_id),
                )
                roles = user.get("business_roles") or user.get("businessRoles") or []
                role_codes = [str(row.get("code")) for row in roles if isinstance(row, dict) and row.get("code")]
                role_snapshot = "ADMIN" if user.get("is_admin") or user.get("isAdmin") else ",".join(role_codes) or "USER"
                cursor.execute(
                    f"""INSERT INTO {self._table(SMART_TASK_LOG_TABLE)} (
                        task_id,match_id,action_code,from_status,to_status,
                        operator_id,operator_name,operator_role_snapshot,operation_note,detail_json,created_at
                    ) VALUES ({','.join(['%s'] * 11)})""",
                    (
                        linked_task_id, None, "STOP_MONITORING_CENTER", "MONITORING", "ENDED",
                        actor_id, actor_name, role_snapshot[:64], note or "从监控中心停用规则",
                        json.dumps({"ruleId": rule_id, "ruleStatus": target}, ensure_ascii=False), now,
                    ),
                )
            connection.commit()
            return {"id": rule_id, "status": target}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "监控规则状态更新失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_events(
        self, user: dict[str, Any], *, status: str = "", template: str = "",
        start_date: str = "", end_date: str = "", keyword: str = "",
        assignee_user_id: int | None = None, only_mine: bool = False,
        overdue_only: bool = False,
        page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        _require(user, "monitor.event.view", "当前账号没有监控事件查看权限")
        today = business_now_naive().date()
        first = date.fromisoformat(start_date) if start_date else today
        last = date.fromisoformat(end_date) if end_date else first
        if last < first or (last - first).days > 366:
            raise ValueError("事件查询日期范围不合法或超过366天")
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        where = ["occurred_at >= %s", "occurred_at < %s"]
        params: list[Any] = [datetime.combine(first, time.min), datetime.combine(last + timedelta(days=1), time.min)]
        if status:
            normalized = status.strip().upper()
            if normalized == "UNRESOLVED":
                where.append("event_status IN ('OPEN','ACKNOWLEDGED','OBSERVING','ESCALATED','ACTION_PENDING','ACTION_IN_PROGRESS')")
            elif normalized not in EVENT_STATUSES:
                raise ValueError("事件状态不支持")
            else:
                where.append("event_status=%s"); params.append(normalized)
        if template:
            where.append("template_code=%s"); params.append(template.strip().upper())
        if keyword:
            token = f"%{keyword.strip()[:100]}%"
            where.append("(event_no LIKE %s OR rule_code LIKE %s OR entity_key LIKE %s OR event_title LIKE %s)")
            params.extend([token, token, token, token])
        if only_mine:
            where.append("assignee_user_id=%s"); params.append(int(user.get("id") or 0))
        elif assignee_user_id:
            where.append("assignee_user_id=%s"); params.append(int(assignee_user_id))
        if overdue_only:
            where.append("event_status IN ('OPEN','ACKNOWLEDGED','OBSERVING','ESCALATED','ACTION_PENDING','ACTION_IN_PROGRESS')")
            where.append("due_at IS NOT NULL AND due_at<%s"); params.append(business_now_naive())
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(EVENT_TABLE)} WHERE {condition}", tuple(params))
            total = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"SELECT * FROM {self._table(EVENT_TABLE)} WHERE {condition} ORDER BY occurred_at DESC,id DESC LIMIT %s OFFSET %s",
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [_public_row(row, scope=_event_scope(row)) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {"rows": rows, "total": total, "page": page, "pageSize": page_size}
        except Exception as error:
            raise self._unavailable(error, "监控事件查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_event_assignees(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.event.view", "当前账号没有监控事件查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT id,username,full_name
                    FROM {self._table('sys_user')}
                    WHERE is_active=1
                    ORDER BY full_name,username,id"""
            )
            return [
                {
                    "id": int(row["id"]),
                    "username": str(row.get("username") or ""),
                    "displayName": str(row.get("full_name") or row.get("username") or ""),
                }
                for row in _dict_rows(cursor, list(cursor.fetchall()))
            ]
        except Exception as error:
            raise self._unavailable(error, "监控事件责任人查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def event_detail(self, user: dict[str, Any], event_id: int) -> dict[str, Any]:
        _require(user, "monitor.event.view", "当前账号没有监控事件查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(EVENT_TABLE)} WHERE id=%s", (event_id,))
            event = _dict_row(cursor, cursor.fetchone())
            if not event:
                raise ValueError("监控事件不存在")
            cursor.execute(
                f"SELECT * FROM {self._table(EVENT_LOG_TABLE)} WHERE event_id=%s ORDER BY created_at DESC,id DESC",
                (event_id,),
            )
            return {
                "event": _public_row(event, scope=_event_scope(event)),
                "logs": [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))],
            }
        except ValueError:
            raise
        except Exception as error:
            raise self._unavailable(error, "监控事件详情查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_event_status(self, user: dict[str, Any], event_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.event.manage", "当前账号没有监控事件处理权限")
        target = str(values.get("status") or "").strip().upper()
        if target not in {"ACKNOWLEDGED", "OBSERVING", "RESOLVED", "IGNORED", "CLOSED"}:
            raise ValueError("事件目标状态不支持")
        note = str(values.get("note") or "").strip()[:1000]
        if target in TERMINAL_EVENT_STATUSES and not note:
            raise ValueError("解决、忽略或关闭事件必须填写处理说明")
        if target == "OBSERVING" and not note:
            raise ValueError("延后观察必须填写观察原因")
        observe_until = _parse_datetime(values.get("observeUntil"), "观察截止时间")
        if target == "OBSERVING" and observe_until is None:
            raise ValueError("延后观察必须填写观察截止时间")
        resolution_code = str(values.get("resolutionCode") or "").strip().upper() or None
        if target in TERMINAL_EVENT_STATUSES and resolution_code not in EVENT_RESOLUTION_CODES:
            raise ValueError("请选择处理结论")
        assignee_user_id = int(values.get("assigneeUserId") or 0) or None
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(EVENT_TABLE)} WHERE id=%s FOR UPDATE", (event_id,))
            event = _dict_row(cursor, cursor.fetchone())
            if not event:
                raise ValueError("监控事件不存在")
            old = str(event["event_status"])
            if old in TERMINAL_EVENT_STATUSES:
                raise ValueError("已结束的事件不能再次处理")
            if old in {"ACTION_PENDING", "ACTION_IN_PROGRESS", "ACTION_APPLIED"}:
                raise ValueError("事件已进入技术工单阶段，请在技术工单中回写执行结果")
            if assignee_user_id:
                cursor.execute(
                    f"SELECT id,full_name,username FROM {self._table('sys_user')} WHERE id=%s AND is_active=1",
                    (assignee_user_id,),
                )
                assignee = _dict_row(cursor, cursor.fetchone())
                if not assignee:
                    raise ValueError("选择的责任人不存在或已停用")
                assignee_name = str(assignee.get("full_name") or assignee.get("username") or "")[:100]
            else:
                assignee_user_id = int(event.get("assignee_user_id") or actor_id)
                assignee_name = str(event.get("assignee_user_name") or actor_name)[:100]
            cursor.execute(
                f"""SELECT initial_due_minutes,max_observe_hours
                    FROM {self._table(EVENT_POLICY_TABLE)}
                    WHERE business_type=%s AND severity=%s AND status='ACTIVE'""",
                (str(event.get("business_type") or ""), str(event.get("severity") or "P2")),
            )
            policy = _dict_row(cursor, cursor.fetchone()) or {}
            max_observe_hours = max(1, int(policy.get("max_observe_hours") or 168))
            if target == "OBSERVING" and observe_until:
                if observe_until <= current:
                    raise ValueError("观察截止时间必须晚于当前时间")
                if observe_until > current + timedelta(hours=max_observe_hours):
                    raise ValueError(f"单次观察时间不能超过{max_observe_hours}小时")
            if target == "OBSERVING":
                due_at = observe_until
            elif target in TERMINAL_EVENT_STATUSES:
                due_at = None
            else:
                due_at = event.get("due_at") or current + timedelta(
                    minutes=max(1, int(policy.get("initial_due_minutes") or 1440))
                )
            action_code = {
                "ACKNOWLEDGED": "ACKNOWLEDGE", "OBSERVING": "OBSERVE",
                "RESOLVED": "RESOLVE", "IGNORED": "IGNORE", "CLOSED": "CLOSE",
            }[target]
            detail = {
                "assigneeUserId": assignee_user_id,
                "assigneeUserName": assignee_name,
                "observeUntil": _json_value(observe_until),
                "resolutionCode": resolution_code,
                "dueAt": _json_value(due_at),
            }
            cursor.execute(
                f"""UPDATE {self._table(EVENT_TABLE)}
                    SET event_status=%s,assignee_user_id=%s,assignee_user_name=%s,
                        due_at=%s,observe_until=%s,resolution_code=%s,resolved_at=%s
                    WHERE id=%s""",
                (
                    target, assignee_user_id, assignee_name, due_at,
                    observe_until if target == "OBSERVING" else None,
                    resolution_code if target in TERMINAL_EVENT_STATUSES else None,
                    current if target in TERMINAL_EVENT_STATUSES else None, event_id,
                ),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(EVENT_LOG_TABLE)}
                    (event_id,action_code,from_status,to_status,operator_id,operator_name,
                     operation_note,operation_detail_json,created_at)
                    VALUES ({','.join(['%s'] * 9)})""",
                (
                    event_id, action_code, old, target, actor_id, actor_name,
                    note or "确认关注事件", json.dumps(detail, ensure_ascii=False), current,
                ),
            )
            connection.commit()
            return {"id": event_id, "status": target}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "监控事件状态更新失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_action_orders(
        self, user: dict[str, Any], *, status: str = "", action_type: str = "",
        assignee_user_id: int | None = None, only_mine: bool = False,
        keyword: str = "", page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        _require(user, "monitor.action.view", "当前账号没有技术工单查看权限")
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        where = ["1=1"]
        params: list[Any] = []
        if status:
            normalized = status.strip().upper()
            if normalized not in ACTION_STATUSES:
                raise ValueError("技术工单状态不支持")
            where.append("a.action_status=%s"); params.append(normalized)
        if action_type:
            normalized = action_type.strip().upper()
            if normalized not in ACTION_TYPES:
                raise ValueError("技术动作类型不支持")
            where.append("a.action_type=%s"); params.append(normalized)
        if only_mine:
            where.append("a.assignee_user_id=%s"); params.append(int(user.get("id") or 0))
        elif assignee_user_id:
            where.append("a.assignee_user_id=%s"); params.append(int(assignee_user_id))
        if keyword:
            token = f"%{keyword.strip()[:100]}%"
            where.append("(a.action_no LIKE %s OR a.rule_code LIKE %s OR a.target_key LIKE %s OR e.event_title LIKE %s)")
            params.extend([token, token, token, token])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT COUNT(1)
                    FROM {self._table(ACTION_ORDER_TABLE)} a
                    JOIN {self._table(EVENT_TABLE)} e ON e.id=a.event_id
                    WHERE {condition}""",
                tuple(params),
            )
            total = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"""SELECT a.*,e.event_no,e.event_title,e.event_status
                    FROM {self._table(ACTION_ORDER_TABLE)} a
                    JOIN {self._table(EVENT_TABLE)} e ON e.id=a.event_id
                    WHERE {condition}
                    ORDER BY a.created_at DESC,a.id DESC LIMIT %s OFFSET %s""",
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [_public_row(row, target=_action_target(row)) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {"rows": rows, "total": total, "page": page, "pageSize": page_size}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("技术工单表尚未创建，请先执行resource-governance-action-work-order-v5.sql") from error
            raise self._unavailable(error, "技术工单查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def action_order_detail(self, user: dict[str, Any], action_order_id: int) -> dict[str, Any]:
        _require(user, "monitor.action.view", "当前账号没有技术工单查看权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT a.*,e.event_no,e.event_title,e.event_status
                    FROM {self._table(ACTION_ORDER_TABLE)} a
                    JOIN {self._table(EVENT_TABLE)} e ON e.id=a.event_id
                    WHERE a.id=%s""",
                (action_order_id,),
            )
            action_order = _dict_row(cursor, cursor.fetchone())
            if not action_order:
                raise ValueError("技术工单不存在")
            cursor.execute(
                f"SELECT * FROM {self._table(ACTION_LOG_TABLE)} WHERE action_order_id=%s ORDER BY created_at DESC,id DESC",
                (action_order_id,),
            )
            return {
                "order": _public_row(action_order, target=_action_target(action_order)),
                "logs": [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))],
            }
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("技术工单表尚未创建，请先执行resource-governance-action-work-order-v5.sql") from error
            raise self._unavailable(error, "技术工单详情查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def create_action_order(self, user: dict[str, Any], event_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.event.manage", "当前账号没有生成技术工单权限")
        action_type = str(values.get("actionType") or "").strip().upper()
        if action_type not in ACTION_TYPES - {"RESTORE"}:
            raise ValueError("请选择限流、下线或延长下线动作")
        assignee_user_id = int(values.get("assigneeUserId") or 0)
        if assignee_user_id <= 0:
            raise ValueError("请选择技术执行人")
        request_note = _clean_text(values.get("requestNote"))[:1000]
        if not request_note:
            raise ValueError("请填写技术执行要求")
        requested_by_id = int(user.get("id") or 0)
        requested_by_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        planned_start_at = _parse_datetime(values.get("plannedStartAt"), "计划执行时间") or current
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(EVENT_TABLE)} WHERE id=%s FOR UPDATE", (event_id,))
            event = _dict_row(cursor, cursor.fetchone())
            if not event:
                raise ValueError("监控事件不存在")
            if str(event.get("business_type") or "") != "RESOURCE_GOVERNANCE":
                raise ValueError("当前只有GDS/OTA资源治理事件支持生成技术工单")
            if str(event.get("event_status") or "") in TERMINAL_EVENT_STATUSES:
                raise ValueError("已结束事件不能生成技术工单")
            cursor.execute(
                f"""SELECT id,action_no FROM {self._table(ACTION_ORDER_TABLE)}
                    WHERE event_id=%s AND action_status IN ('PENDING','ACCEPTED','EXECUTING','SUCCEEDED','RECOVERY_PENDING')
                    ORDER BY id DESC LIMIT 1""",
                (event_id,),
            )
            active_order = _dict_row(cursor, cursor.fetchone())
            if active_order:
                raise ValueError(f"事件已有未结束技术工单{active_order.get('action_no')}，不能重复创建")
            cursor.execute(
                f"SELECT id,full_name,username FROM {self._table('sys_user')} WHERE id=%s AND is_active=1",
                (assignee_user_id,),
            )
            assignee = _dict_row(cursor, cursor.fetchone())
            if not assignee:
                raise ValueError("选择的技术执行人不存在或已停用")
            assignee_name = str(assignee.get("full_name") or assignee.get("username") or "")[:100]
            cursor.execute(
                f"""SELECT action_durations_json,permanent_after_count
                    FROM {self._table(EVENT_POLICY_TABLE)}
                    WHERE business_type=%s AND severity=%s AND status='ACTIVE'""",
                (str(event.get("business_type") or ""), str(event.get("severity") or "P2")),
            )
            policy = _dict_row(cursor, cursor.fetchone()) or {}
            target_key = _resource_target_key(event)
            cursor.execute(
                f"""SELECT COUNT(1) FROM {self._table(ACTION_ORDER_TABLE)}
                    WHERE resource_type=%s AND target_key=%s
                      AND action_type<>'RESTORE' AND action_status IN ('SUCCEEDED','RECOVERY_PENDING','RECOVERED')""",
                ("GDS" if str(event.get("template_code") or "") == "GDS_QUERY_RATIO_DAILY" else "OTA", target_key),
            )
            occurrence_no = int(_first_value(cursor.fetchone()) or 0) + 1
            permanent_after_count = max(1, int(policy.get("permanent_after_count") or 4))
            permanent_flag = occurrence_no >= permanent_after_count
            durations = _positive_minutes(policy.get("action_durations_json"))
            duration_minutes = durations[min(occurrence_no - 1, len(durations) - 1)]
            planned_end_at = None if permanent_flag else planned_start_at + timedelta(minutes=duration_minutes)
            action_no = f"RWO-{current:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8].upper()}"
            resource_type = "GDS" if str(event.get("template_code") or "") == "GDS_QUERY_RATIO_DAILY" else "OTA"
            target_snapshot_json = str(event.get("match_snapshot_json") or "{}")
            cursor.execute(
                f"""INSERT INTO {self._table(ACTION_ORDER_TABLE)} (
                    action_no,event_id,rule_id,rule_code,resource_type,target_key,target_snapshot_json,
                    action_type,occurrence_no,permanent_flag,request_note,requested_by_id,requested_by_name,
                    assignee_user_id,assignee_user_name,action_status,planned_start_at,planned_end_at,created_at,updated_at
                ) VALUES ({','.join(['%s'] * 20)})""",
                (
                    action_no,event_id,event.get("rule_id"),event.get("rule_code"),resource_type,target_key,target_snapshot_json,
                    action_type,occurrence_no,1 if permanent_flag else 0,request_note,requested_by_id,requested_by_name,
                    assignee_user_id,assignee_name,"PENDING",planned_start_at,planned_end_at,current,current,
                ),
            )
            action_order_id = int(cursor.lastrowid)
            detail = {
                "actionType": action_type, "occurrenceNo": occurrence_no,
                "permanent": permanent_flag, "plannedStartAt": planned_start_at,
                "plannedEndAt": planned_end_at, "assigneeUserId": assignee_user_id,
            }
            cursor.execute(
                f"""INSERT INTO {self._table(ACTION_LOG_TABLE)}
                    (action_order_id,action_code,from_status,to_status,operator_id,operator_name,operation_note,operation_detail_json,created_at)
                    VALUES (%s,'CREATE',NULL,'PENDING',%s,%s,%s,%s,%s)""",
                (action_order_id, requested_by_id, requested_by_name, request_note, json.dumps(detail, ensure_ascii=False, default=_json_value), current),
            )
            snapshot = _json_dict(target_snapshot_json)
            payload = {
                "eventNo": event.get("event_no"), "eventCode": "RESOURCE_ACTION_ORDER_CREATED",
                "title": f"[待接单] {event.get('event_title') or '资源治理技术工单'}",
                "ruleCode": event.get("rule_code"), "resourceType": resource_type,
                "businessDate": snapshot.get("businessDate"),
                "scope": " / ".join(f"{key}:{value}" for key, value in _event_scope(event).items() if value not in (None, "")) or target_key,
                "actionNo": action_no, "actionType": action_type,
                "assigneeUserName": assignee_name, "recipientUserIds": [assignee_user_id],
            }
            cursor.execute(
                f"""INSERT IGNORE INTO {self._table(OUTBOX_TABLE)}
                    (event_id,notification_key,channel,target_type,target_id,target_name,payload_json,status,next_retry_at)
                    VALUES (%s,%s,'IN_APP','USER',%s,%s,%s,'PENDING',%s)""",
                (
                    event_id, f"ACTION_CREATE:{action_order_id}", str(assignee_user_id), assignee_name,
                    json.dumps(payload, ensure_ascii=False, default=_json_value), current,
                ),
            )
            old_event_status = str(event.get("event_status") or "OPEN")
            cursor.execute(
                f"UPDATE {self._table(EVENT_TABLE)} SET event_status='ACTION_PENDING',action_order_id=%s,due_at=%s,observe_until=NULL WHERE id=%s",
                (action_order_id, planned_start_at, event_id),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(EVENT_LOG_TABLE)}
                    (event_id,action_code,from_status,to_status,operator_id,operator_name,operation_note,operation_detail_json,created_at)
                    VALUES (%s,'CREATE_ACTION_ORDER',%s,'ACTION_PENDING',%s,%s,%s,%s,%s)""",
                (event_id, old_event_status, requested_by_id, requested_by_name, request_note, json.dumps({"actionOrderId": action_order_id, "actionNo": action_no}, ensure_ascii=False), current),
            )
            connection.commit()
            return {
                "id": action_order_id, "actionNo": action_no, "status": "PENDING",
                "occurrenceNo": occurrence_no, "permanent": permanent_flag,
                "plannedStartAt": _json_value(planned_start_at), "plannedEndAt": _json_value(planned_end_at),
            }
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            if _is_missing_table(error):
                raise MonitoringUnavailable("技术工单表尚未创建，请先执行resource-governance-action-work-order-v5.sql") from error
            raise self._unavailable(error, "技术工单创建失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_action_order(self, user: dict[str, Any], action_order_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.action.manage", "当前账号没有技术工单处理权限")
        action = str(values.get("action") or "").strip().upper()
        transitions = {
            "ACCEPT": ({"PENDING"}, "ACCEPTED"),
            "START": ({"PENDING", "ACCEPTED"}, "EXECUTING"),
            "SUCCESS": ({"ACCEPTED", "EXECUTING"}, "SUCCEEDED"),
            "FAIL": ({"PENDING", "ACCEPTED", "EXECUTING", "RECOVERY_PENDING"}, "FAILED"),
            "CANCEL": ({"PENDING", "ACCEPTED"}, "CANCELLED"),
            "RECOVER": ({"RECOVERY_PENDING"}, "RECOVERED"),
        }
        if action not in transitions:
            raise ValueError("技术工单动作不支持")
        note = _clean_text(values.get("note"))[:1000]
        if action in {"SUCCESS", "FAIL", "CANCEL", "RECOVER"} and not note:
            raise ValueError("执行成功、失败、取消或恢复必须填写回执说明")
        execution_reference = _clean_text(values.get("executionReference"))[:200] or None
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(ACTION_ORDER_TABLE)} WHERE id=%s FOR UPDATE", (action_order_id,))
            order = _dict_row(cursor, cursor.fetchone())
            if not order:
                raise ValueError("技术工单不存在")
            old = str(order.get("action_status") or "")
            allowed, target = transitions[action]
            if old not in allowed:
                raise ValueError(f"当前工单状态{old}不能执行{action}动作")
            accepted_at = current if target == "ACCEPTED" else order.get("accepted_at")
            executed_at = current if target in {"SUCCEEDED", "FAILED"} else order.get("executed_at")
            recovered_at = current if target == "RECOVERED" else order.get("recovered_at")
            failure_reason = note if target == "FAILED" else order.get("failure_reason")
            cursor.execute(
                f"""UPDATE {self._table(ACTION_ORDER_TABLE)}
                    SET action_status=%s,accepted_at=%s,executed_at=%s,recovered_at=%s,
                        execution_reference=COALESCE(%s,execution_reference),execution_note=%s,
                        failure_reason=%s,updated_at=%s WHERE id=%s""",
                (target, accepted_at, executed_at, recovered_at, execution_reference, note or order.get("execution_note"), failure_reason, current, action_order_id),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(ACTION_LOG_TABLE)}
                    (action_order_id,action_code,from_status,to_status,operator_id,operator_name,operation_note,operation_detail_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (action_order_id, action, old, target, actor_id, actor_name, note or action, json.dumps({"executionReference": execution_reference}, ensure_ascii=False), current),
            )
            event_status = {
                "ACCEPTED": "ACTION_IN_PROGRESS", "EXECUTING": "ACTION_IN_PROGRESS",
                "SUCCEEDED": "ACTION_APPLIED", "FAILED": "ESCALATED",
                "CANCELLED": "ACKNOWLEDGED", "RECOVERED": "RESOLVED",
            }[target]
            if target == "SUCCEEDED":
                due_at = order.get("planned_end_at")
            elif target == "FAILED":
                due_at = current
            elif target == "RECOVERED":
                due_at = None
            else:
                due_at = order.get("planned_start_at")
            event_action_order_id = None if target in {"FAILED", "CANCELLED"} else action_order_id
            cursor.execute(f"SELECT event_status FROM {self._table(EVENT_TABLE)} WHERE id=%s FOR UPDATE", (order["event_id"],))
            event = _dict_row(cursor, cursor.fetchone()) or {}
            cursor.execute(
                f"""UPDATE {self._table(EVENT_TABLE)}
                    SET event_status=%s,action_order_id=%s,due_at=%s,observe_until=NULL,
                        resolution_code=%s,resolved_at=%s WHERE id=%s""",
                (
                    event_status, event_action_order_id, due_at,
                    "FIXED" if target == "RECOVERED" else None,
                    current if target == "RECOVERED" else None,
                    order["event_id"],
                ),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(EVENT_LOG_TABLE)}
                    (event_id,action_code,from_status,to_status,operator_id,operator_name,operation_note,operation_detail_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    order["event_id"], f"ACTION_{action}", str(event.get("event_status") or ""), event_status,
                    actor_id, actor_name, note or action,
                    json.dumps({"actionOrderId": action_order_id, "actionStatus": target, "executionReference": execution_reference}, ensure_ascii=False), current,
                ),
            )
            connection.commit()
            return {"id": action_order_id, "status": target, "eventStatus": event_status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            if _is_missing_table(error):
                raise MonitoringUnavailable("技术工单表尚未创建，请先执行resource-governance-action-work-order-v5.sql") from error
            raise self._unavailable(error, "技术工单状态更新失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_runs(self, user: dict[str, Any], *, job_type: str = "", status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        _require(user, "monitor.run.view", "当前账号没有运行日志查看权限")
        where = ["1=1"]
        params: list[Any] = []
        if job_type:
            where.append("job_type=%s"); params.append(job_type.strip().upper())
        if status:
            where.append("status=%s"); params.append(status.strip().upper())
        limit = max(1, min(int(limit), 500))
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(RUN_TABLE)} WHERE {' AND '.join(where)} ORDER BY started_at DESC,id DESC LIMIT %s",
                tuple([*params, limit]),
            )
            return [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
        except Exception as error:
            raise self._unavailable(error, "监控运行日志查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    @staticmethod
    def _public_endpoint(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "endpointCode": str(row.get("endpoint_code") or ""),
            "endpointName": str(row.get("endpoint_name") or ""),
            "channel": str(row.get("channel") or "WECOM"),
            "webhookMasked": _mask_webhook(row.get("webhook_url")),
            "webhookConfigured": bool(row.get("webhook_url")),
            "mentionedUserIds": _json_list(row.get("mentioned_user_ids")),
            "mentionedMobiles": _json_list(row.get("mentioned_mobiles")),
            "smartPlacementEnabled": bool(row.get("smart_placement_enabled")),
            "status": str(row.get("status") or "DISABLED"),
            "updatedByName": str(row.get("updated_by_name") or "SYSTEM"),
            "updatedAt": _json_value(row.get("updated_at")),
        }

    def list_notify_endpoints(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} ORDER BY status='ACTIVE' DESC,smart_placement_enabled DESC,id"
            )
            return [self._public_endpoint(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise self._unavailable(error, "通知群配置查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def resolve_notification_endpoint(self, user: dict[str, Any], endpoint_id: str) -> dict[str, Any]:
        """Server-only bridge for other modules; never expose its raw URL through HTTP."""
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        if not str(endpoint_id).isdigit():
            raise ValueError("通知端点ID无效")
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s", (int(endpoint_id),))
            row = _dict_row(cursor, cursor.fetchone())
            if not row or row.get("status") != "ACTIVE" or row.get("channel") != "WECOM":
                raise ValueError("通知端点不存在、停用或不是企业微信群")
            url = _validate_wecom_webhook(row.get("webhook_url"), required=True)
            fingerprint = hashlib.sha256((url + str(row.get("updated_at"))).encode()).hexdigest()
            return {"id": str(row["id"]), "name": str(row.get("endpoint_name") or ""), "url": url, "fingerprint": fingerprint}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            raise MonitoringUnavailable("ADM通知端点读取失败") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def save_notify_endpoint(
        self,
        user: dict[str, Any],
        values: dict[str, Any],
        endpoint_id: int | None = None,
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        endpoint_name = _clean_text(values.get("endpointName"))[:100]
        if not endpoint_name:
            raise ValueError("通知群名称不能为空")
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if status not in ENDPOINT_STATUSES:
            raise ValueError("通知群状态不支持")
        mentioned_user_ids = _string_list(values.get("mentionedUserIds"))
        mentioned_mobiles = _string_list(values.get("mentionedMobiles"))
        invalid_mobiles = [item for item in mentioned_mobiles if not re.fullmatch(r"\+?\d{6,20}", item)]
        if invalid_mobiles:
            raise ValueError(f"@手机号格式不正确：{invalid_mobiles[0]}")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            existing = None
            if endpoint_id is not None:
                cursor.execute(
                    f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s FOR UPDATE",
                    (endpoint_id,),
                )
                existing = _dict_row(cursor, cursor.fetchone())
                if not existing:
                    raise ValueError("通知群配置不存在")
            webhook = _validate_wecom_webhook(values.get("webhookUrl"), required=existing is None)
            if not webhook and existing:
                webhook = str(existing.get("webhook_url") or "")
            if existing:
                cursor.execute(
                    f"""UPDATE {self._table(NOTIFY_ENDPOINT_TABLE)}
                        SET endpoint_name=%s,webhook_url=%s,mentioned_user_ids=%s,mentioned_mobiles=%s,
                            smart_placement_enabled=%s,status=%s,updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE id=%s""",
                    (
                        endpoint_name, webhook, json.dumps(mentioned_user_ids, ensure_ascii=False),
                        json.dumps(mentioned_mobiles, ensure_ascii=False),
                        1 if values.get("smartPlacementEnabled") else 0, status,
                        actor_id, actor_name, current, endpoint_id,
                    ),
                )
                saved_id = int(endpoint_id)
                endpoint_code = str(existing.get("endpoint_code") or "")
            else:
                endpoint_code = f"WECOM-{uuid.uuid4().hex[:16].upper()}"
                cursor.execute(
                    f"""INSERT INTO {self._table(NOTIFY_ENDPOINT_TABLE)} (
                        endpoint_code,endpoint_name,channel,webhook_url,mentioned_user_ids,mentioned_mobiles,
                        smart_placement_enabled,status,created_by_id,created_by_name,created_at,
                        updated_by_id,updated_by_name,updated_at
                    ) VALUES ({','.join(['%s'] * 14)})""",
                    (
                        endpoint_code, endpoint_name, "WECOM", webhook,
                        json.dumps(mentioned_user_ids, ensure_ascii=False),
                        json.dumps(mentioned_mobiles, ensure_ascii=False),
                        1 if values.get("smartPlacementEnabled") else 0, status,
                        actor_id, actor_name, current, actor_id, actor_name, current,
                    ),
                )
                saved_id = int(cursor.lastrowid)
            connection.commit()
            return {
                "id": saved_id,
                "endpointCode": endpoint_code,
                "endpointName": endpoint_name,
                "status": status,
                "smartPlacementEnabled": bool(values.get("smartPlacementEnabled")),
            }
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise self._unavailable(error, "通知群配置保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def test_notify_endpoint(self, user: dict[str, Any], endpoint_id: int) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群测试权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s", (endpoint_id,))
            endpoint = _dict_row(cursor, cursor.fetchone())
            if not endpoint:
                raise ValueError("通知群配置不存在")
            if str(endpoint.get("status")) != "ACTIVE":
                raise ValueError("通知群已停用，请先启用后再测试")
            body = json.dumps(
                _wecom_test_message(
                    str(endpoint.get("endpoint_name") or "企业微信群"),
                    _json_list(endpoint.get("mentioned_user_ids")),
                    _json_list(endpoint.get("mentioned_mobiles")),
                ),
                ensure_ascii=False,
            ).encode("utf-8")
            response = urlrequest.urlopen(
                urlrequest.Request(
                    str(endpoint["webhook_url"]),
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                ),
                timeout=10,
            )
            result = json.loads(response.read().decode("utf-8"))
            if int(result.get("errcode", -1)) != 0:
                raise ValueError(f"企业微信返回失败：{result.get('errmsg') or result}")
            return {"id": endpoint_id, "success": True, "message": "测试消息发送成功"}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise MonitoringUnavailable(f"企业微信测试发送失败：{error}") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_message_templates(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} ORDER BY event_code,channel,id"
            )
            rows = []
            for row in _dict_rows(cursor, list(cursor.fetchall())):
                item = _public_row(row)
                item["fieldSchema"] = json.loads(row.get("field_schema_json") or "{}")
                item.pop("fieldSchemaJson", None)
                rows.append(item)
            return rows
        except PermissionError:
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("通知模型表尚未创建，请先执行smart-placement-lifecycle-notification-v2.sql") from error
            raise self._unavailable(error, "通知模板查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_message_template(
        self, user: dict[str, Any], template_id: int, values: dict[str, Any],
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        title = _clean_text(values.get("titleTemplate"))[:300]
        body = _clean_text(values.get("bodyTemplate"))
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if not title or not body:
            raise ValueError("消息标题和正文模板不能为空")
        if len(body) > 4000:
            raise ValueError("消息正文模板不能超过4000个字符")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("消息模板状态不支持")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s FOR UPDATE",
                (template_id,),
            )
            row = _dict_row(cursor, cursor.fetchone())
            if not row:
                raise ValueError("消息模板不存在")
            schema = json.loads(row.get("field_schema_json") or "{}")
            allowed = {str(item) for item in schema.get("allowedFields") or []}
            placeholders = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", f"{title}\n{body}"))
            invalid = sorted(placeholders - allowed)
            if invalid:
                raise ValueError(f"消息模板包含未授权变量：{','.join(invalid)}")
            cursor.execute(
                f"""UPDATE {self._table(MESSAGE_TEMPLATE_TABLE)}
                    SET title_template=%s,body_template=%s,status=%s,
                        version_no=version_no+1,updated_by_id=%s,
                        updated_by_name=%s,updated_at=%s WHERE id=%s""",
                (title, body, status, actor_id, actor_name, business_now_naive(), template_id),
            )
            connection.commit()
            return {"id": template_id, "versionNo": int(row.get("version_no") or 1) + 1, "status": status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "通知模板保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def create_message_template(
        self, user: dict[str, Any], values: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy a registered event template without widening its event or field contract."""
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        try:
            source_template_id = int(values.get("sourceTemplateId") or 0)
        except Exception as error:
            raise ValueError("请选择基础消息模板") from error
        if source_template_id <= 0:
            raise ValueError("请选择基础消息模板")
        template_name = _clean_text(values.get("templateName"))[:100]
        title = _clean_text(values.get("titleTemplate"))[:300]
        body = _clean_text(values.get("bodyTemplate"))
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if not template_name:
            raise ValueError("消息模板名称不能为空")
        if not title or not body:
            raise ValueError("消息标题和正文模板不能为空")
        if len(body) > 4000:
            raise ValueError("消息正文模板不能超过4000个字符")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("消息模板状态不支持")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s AND status IN ('ACTIVE','DISABLED') FOR UPDATE",
                (source_template_id,),
            )
            source = _dict_row(cursor, cursor.fetchone())
            if not source:
                raise ValueError("基础消息模板不存在")
            schema_text = str(source.get("field_schema_json") or "{}")
            schema = json.loads(schema_text)
            allowed = {str(item) for item in schema.get("allowedFields") or []}
            placeholders = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", f"{title}\n{body}"))
            invalid = sorted(placeholders - allowed)
            if invalid:
                raise ValueError(f"消息模板包含未授权变量：{','.join(invalid)}")
            event_code = str(source.get("event_code") or "").upper()
            channel = str(source.get("channel") or "WECOM").upper()
            template_code = f"CUSTOM_{event_code[:32]}_{uuid.uuid4().hex[:12].upper()}"
            cursor.execute(
                f"""INSERT INTO {self._table(MESSAGE_TEMPLATE_TABLE)} (
                    template_code,template_name,event_code,channel,title_template,body_template,
                    field_schema_json,version_no,status,created_by_id,created_by_name,
                    updated_by_id,updated_by_name,created_at,updated_at
                ) VALUES ({','.join(['%s'] * 15)})""",
                (
                    template_code, template_name, event_code, channel, title, body,
                    schema_text, 1, status, actor_id, actor_name, actor_id, actor_name,
                    business_now_naive(), business_now_naive(),
                ),
            )
            saved_id = int(cursor.lastrowid)
            connection.commit()
            return {
                "id": saved_id, "templateCode": template_code,
                "eventCode": event_code, "status": status,
            }
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "消息模板创建失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_notify_routes(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知路由配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT r.*,t.template_code,t.template_name,e.endpoint_name
                    FROM {self._table(NOTIFY_ROUTE_TABLE)} r
                    JOIN {self._table(MESSAGE_TEMPLATE_TABLE)} t ON t.id=r.template_id
                    LEFT JOIN {self._table(NOTIFY_ENDPOINT_TABLE)} e ON e.id=r.endpoint_id
                    ORDER BY r.event_code,r.priority_no,r.id"""
            )
            return [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
        except PermissionError:
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("通知模型表尚未创建，请先执行smart-placement-lifecycle-notification-v2.sql") from error
            raise self._unavailable(error, "通知路由查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def save_notify_route(
        self, user: dict[str, Any], values: dict[str, Any], route_id: int | None = None,
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知路由配置权限")
        route_name = _clean_text(values.get("routeName"))[:100]
        event_code = _clean_text(values.get("eventCode")).upper()
        strategy = _clean_text(values.get("recipientStrategy") or "TASK_ASSIGNEE").upper()
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        use_defaults = bool(values.get("useSmartDefaultEndpoints"))
        if not route_name:
            raise ValueError("通知路由名称不能为空")
        if event_code not in NOTIFY_EVENT_CODES:
            raise ValueError("通知事件类型不支持")
        if strategy not in RECIPIENT_STRATEGIES:
            raise ValueError("动态收件人策略不支持")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("通知路由状态不支持")
        try:
            template_id = int(values.get("templateId"))
            endpoint_id = int(values["endpointId"]) if values.get("endpointId") not in (None, "") else None
            priority_no = max(1, min(int(values.get("priorityNo") or 100), 9999))
        except (TypeError, ValueError) as error:
            raise ValueError("通知模板、通知群或优先级格式不正确") from error
        if not endpoint_id and not use_defaults:
            raise ValueError("请选择通知群，或启用全部默认通知群")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT id,event_code,channel FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s AND status='ACTIVE'",
                (template_id,),
            )
            template = _dict_row(cursor, cursor.fetchone())
            if not template or str(template["event_code"]) != event_code or str(template["channel"]) != "WECOM":
                raise ValueError("所选消息模板与事件类型不匹配或已停用")
            if endpoint_id:
                cursor.execute(
                    f"SELECT id FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s AND channel='WECOM'",
                    (endpoint_id,),
                )
                if not cursor.fetchone():
                    raise ValueError("通知群不存在")
            if route_id:
                cursor.execute(f"SELECT route_code FROM {self._table(NOTIFY_ROUTE_TABLE)} WHERE id=%s FOR UPDATE", (route_id,))
                existing = _dict_row(cursor, cursor.fetchone())
                if not existing:
                    raise ValueError("通知路由不存在")
                cursor.execute(
                    f"""UPDATE {self._table(NOTIFY_ROUTE_TABLE)}
                        SET route_name=%s,event_code=%s,endpoint_id=%s,template_id=%s,
                            recipient_strategy=%s,use_smart_default_endpoints=%s,
                            priority_no=%s,status=%s,updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE id=%s""",
                    (route_name,event_code,endpoint_id,template_id,strategy,int(use_defaults),priority_no,status,actor_id,actor_name,current,route_id),
                )
                saved_id = route_id
            else:
                route_code = f"NRT-{uuid.uuid4().hex[:16].upper()}"
                cursor.execute(
                    f"""INSERT INTO {self._table(NOTIFY_ROUTE_TABLE)} (
                        route_code,route_name,event_code,channel,endpoint_id,template_id,
                        recipient_strategy,use_smart_default_endpoints,priority_no,status,
                        created_by_id,created_by_name,created_at,updated_by_id,updated_by_name,updated_at
                    ) VALUES ({','.join(['%s'] * 16)})""",
                    (route_code,route_name,event_code,"WECOM",endpoint_id,template_id,strategy,int(use_defaults),priority_no,status,actor_id,actor_name,current,actor_id,actor_name,current),
                )
                saved_id = int(cursor.lastrowid)
            connection.commit()
            return {"id": saved_id, "eventCode": event_code, "status": status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "通知路由保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def task_monitoring(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT r.*,
                           (SELECT COUNT(1) FROM {self._table(EVENT_TABLE)} e WHERE e.rule_id=r.id) hit_count,
                           (SELECT COUNT(1) FROM {self._table(EVENT_TABLE)} e WHERE e.rule_id=r.id AND e.event_status='OPEN') open_event_count
                    FROM {self._table(RULE_TABLE)} r
                    WHERE r.source_business_type='SMART_PLACEMENT_EXECUTION' AND r.source_parent_id=%s
                    ORDER BY r.id DESC LIMIT 1""",
                (task_id,),
            )
            rule = _dict_row(cursor, cursor.fetchone())
            conditions: list[dict[str, Any]] = []
            if rule:
                version_id = rule.get("current_version_id")
                if not version_id:
                    cursor.execute(
                        f"SELECT id FROM {self._table(VERSION_TABLE)} WHERE rule_id=%s ORDER BY version_no DESC LIMIT 1",
                        (rule["id"],),
                    )
                    version_id = _first_value(cursor.fetchone())
                if version_id:
                    cursor.execute(
                        f"""SELECT c.* FROM {self._table(CONDITION_TABLE)} c
                            WHERE c.rule_version_id=%s
                            ORDER BY c.group_no,c.sort_no,c.id""",
                        (version_id,),
                    )
                    conditions = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {
                "available": bool(rule),
                "rule": _public_row(rule) if rule else None,
                "conditions": conditions,
            }
        except Exception as error:
            raise self._unavailable(error, "投放任务监控状态查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
