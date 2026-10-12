"""Generic monitoring control plane and smart-placement rule compiler."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
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
FEATURE_TABLE = "rt_order_monitor_feature"
RULE_STAT_TABLE = "monitor_rule_run_stat"

SMART_TEMPLATE = "SMART_PLACEMENT_ORDER"
RULE_STATUSES = frozenset({"SCHEDULED", "ACTIVE", "PAUSED", "EXPIRED", "DISABLED"})
EVENT_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED", "RESOLVED", "IGNORED", "CLOSED"})


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


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part[:1].upper() + part[1:] for part in tail)

    return {camel(key): _json_value(value) for key, value in row.items()}


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
    """Compile one successful smart-placement execution into an immutable rule version."""

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
    ) -> dict[str, Any]:
        cursor.execute(
            f"SELECT id FROM {_qualified(database, TEMPLATE_TABLE)} "
            "WHERE template_code=%s AND status='ACTIVE'",
            (SMART_TEMPLATE,),
        )
        template_id = _first_value(cursor.fetchone())
        if not template_id:
            raise MonitoringUnavailable("智能投放监控模板尚未初始化，请先执行monitoring-center-schema.sql")

        effective_start = execution.get("effective_start_at")
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
        add("order_source", "EQ", "STRING", _clean_text(execution.get("order_source") or task.get("order_source")))
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
        loss_min = task.get("loss_threshold_min")
        loss_max = task.get("loss_threshold_max")
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
                rule_id, 1, rule_hash, effective_start, effective_end, "AND",
                snapshot_text, f"投放第{attempt_no}次执行成功自动生成", "ACTIVE",
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
                rule_id, version_id, "CREATE", None, status, actor[0], actor[1],
                "投放成功后自动生成监控规则",
                json.dumps({"taskId": task["id"], "executionId": execution_id}, ensure_ascii=False), now,
            ),
        )
        return {
            "ruleId": rule_id,
            "ruleCode": rule_code,
            "ruleVersionId": version_id,
            "ruleVersionNo": 1,
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
            cursor.execute(
                f"""SELECT COUNT(1) total_events,
                           SUM(CASE WHEN event_status='OPEN' THEN 1 ELSE 0 END) open_events,
                           SUM(CASE WHEN event_status='ACKNOWLEDGED' THEN 1 ELSE 0 END) acknowledged_events
                    FROM {self._table(EVENT_TABLE)}
                    WHERE occurred_at >= %s""",
                (datetime.combine(business_now_naive().date(), time.min),),
            )
            event_summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
            cursor.execute(
                f"""SELECT COUNT(1) pending_notifications
                    FROM {self._table(OUTBOX_TABLE)}
                    WHERE status IN ('PENDING','FAILED')"""
            )
            pending_notifications = int(_first_value(cursor.fetchone()) or 0)
            cursor.execute(
                f"""SELECT * FROM {self._table(RUN_TABLE)}
                    ORDER BY started_at DESC,id DESC LIMIT 8"""
            )
            recent_runs = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {
                "available": True,
                "source": f"MySQL · {self.source.database}",
                "ruleSummary": rule_summary,
                "eventSummary": event_summary,
                "pendingNotifications": pending_notifications,
                "recentRuns": recent_runs,
            }
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
            cursor.execute(f"SELECT * FROM {self._table(TEMPLATE_TABLE)} ORDER BY id")
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
        except Exception as error:
            raise self._unavailable(error, "监控模板查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def _validated_conditions(self, cursor, template_id: int, values: Any) -> list[dict[str, Any]]:
        if not isinstance(values, list) or not values:
            raise ValueError("监控规则至少需要一个条件")
        cursor.execute(
            f"SELECT * FROM {self._table(TEMPLATE_FIELD_TABLE)} WHERE template_id=%s AND status='ACTIVE' ORDER BY sort_no,id",
            (template_id,),
        )
        fields = {str(row["field_code"]): row for row in _dict_rows(cursor, list(cursor.fetchall()))}
        result: list[dict[str, Any]] = []
        present: set[str] = set()
        for index, item in enumerate(values, 1):
            if not isinstance(item, dict):
                raise ValueError(f"第{index}个规则条件格式不正确")
            field_code = str(item.get("fieldCode") or "").strip()
            field = fields.get(field_code)
            if not field:
                raise ValueError(f"字段{field_code or index}不属于当前模板")
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
        return result

    def create_rule(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有监控规则管理权限")
        template_code = str(values.get("templateCode") or "").strip().upper()
        if template_code != "ORDER_SEGMENT_THRESHOLD":
            raise ValueError("当前手工配置仅开放订单航段阈值模板；智能投放规则由投放成功自动生成")
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
        notify_policy = values.get("notifyPolicy") if isinstance(values.get("notifyPolicy"), dict) else {}
        notify_policy.setdefault("channels", ["IN_APP"])
        notify_policy.setdefault("ownerUserId", owner_id)
        notify_policy.setdefault("ownerUserName", owner_name)
        schedule_seconds = max(30, min(int(values.get("scheduleSeconds") or 60), 86400))
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
            conditions = self._validated_conditions(cursor, int(template["id"]), values.get("conditions"))
            snapshot = {"templateCode": template_code, "conditionRelation": "AND", "conditions": conditions}
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
                (rule_code, rule_name, template["id"], template_code, "ORDER_RISK", owner_id, owner_name,
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
                           (SELECT COUNT(1) FROM {self._table(EVENT_TABLE)} e WHERE e.rule_id=r.id) hit_count
                    FROM {self._table(RULE_TABLE)} r
                    JOIN {self._table(TEMPLATE_TABLE)} t ON t.id=r.template_id
                    WHERE {condition}
                    ORDER BY FIELD(r.status,'ACTIVE','SCHEDULED','PAUSED','EXPIRED','DISABLED'),r.updated_at DESC
                    LIMIT %s OFFSET %s""",
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
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
                public_versions.append(item)
            return {"rule": _public_row(rule), "versions": public_versions, "logs": [_public_row(row) for row in logs]}
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
            if normalized not in EVENT_STATUSES:
                raise ValueError("事件状态不支持")
            where.append("event_status=%s"); params.append(normalized)
        if template:
            where.append("template_code=%s"); params.append(template.strip().upper())
        if keyword:
            token = f"%{keyword.strip()[:100]}%"
            where.append("(event_no LIKE %s OR rule_code LIKE %s OR entity_key LIKE %s OR event_title LIKE %s)")
            params.extend([token, token, token, token])
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
            return {"rows": [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))], "total": total, "page": page, "pageSize": page_size}
        except Exception as error:
            raise self._unavailable(error, "监控事件查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_event_status(self, user: dict[str, Any], event_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require(user, "monitor.event.manage", "当前账号没有监控事件处理权限")
        target = str(values.get("status") or "").strip().upper()
        if target not in {"ACKNOWLEDGED", "RESOLVED", "IGNORED", "CLOSED"}:
            raise ValueError("事件目标状态不支持")
        note = str(values.get("note") or "").strip()[:1000]
        if target in {"RESOLVED", "IGNORED", "CLOSED"} and not note:
            raise ValueError("解决、忽略或关闭事件必须填写处理说明")
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
            cursor.execute(
                f"UPDATE {self._table(EVENT_TABLE)} SET event_status=%s,resolved_at=%s WHERE id=%s",
                (target, current if target in {"RESOLVED", "IGNORED", "CLOSED"} else None, event_id),
            )
            cursor.execute(
                f"""INSERT INTO {self._table(EVENT_LOG_TABLE)}
                    (event_id,from_status,to_status,operator_id,operator_name,operation_note,created_at)
                    VALUES ({','.join(['%s'] * 7)})""",
                (event_id, old, target, actor_id, actor_name, note or "确认关注事件", current),
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
            return {"available": bool(rule), "rule": _public_row(rule) if rule else None}
        except Exception as error:
            raise self._unavailable(error, "投放任务监控状态查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
