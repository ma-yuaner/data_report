"""Smart-placement workflow backed by the MySQL collaboration tables."""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time as monotonic_time
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .data_source import DataSource
from .monitoring import MonitorRuleCompiler, MonitoringUnavailable
from ..time_utils import as_business_naive, business_now_naive


LOGGER = logging.getLogger(__name__)
TASK_TABLE = "smart_placement_task"
REVIEW_TABLE = "smart_placement_review"
EXECUTION_TABLE = "smart_placement_execution"
MATCH_TABLE = "smart_placement_order_match"
LOG_TABLE = "smart_placement_operation_log"
OUTCOME_TABLE = "smart_placement_order_outcome"
ATTRIBUTION_TABLE = "smart_placement_match_attribution"
EFFECT_REVIEW_TABLE = "smart_placement_effect_review"
MONITOR_RULE_TABLE = "monitor_rule"
DIMENSION_TABLE = "bi_business_profit_dimension_day"
MANAGER_RELATION_TABLE = "sys_user_manager_relation"
TASK_SCOPE_RESOURCE = "smart_placement.task"
ORDER_SCOPE_RESOURCE = "smart_placement.order"
MANAGER_RELATION_RESOURCE = "smart_placement"

_DIMENSION_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DIMENSION_CACHE_LOCK = threading.Lock()

TASK_STATUSES = frozenset({
    "DRAFT", "PENDING_DATA_REVIEW", "PENDING_POLICY_REVIEW", "CLAIMABLE",
    "IN_PROGRESS", "MONITORING", "FAILED", "REJECTED", "CLOSED", "ENDED",
})
PRIORITIES = frozenset({"HIGH", "MEDIUM", "LOW"})
REVIEW_STAGES = {
    "DATA_MANAGER": ("PENDING_DATA_REVIEW", "PENDING_POLICY_REVIEW", "data_reviewed_at"),
    "POLICY_MANAGER": ("PENDING_POLICY_REVIEW", "CLAIMABLE", "policy_reviewed_at"),
}
REVIEW_RESULTS = frozenset({"APPROVED", "RETURNED", "REJECTED"})
POLICY_EXECUTABLE_LEVELS = frozenset({"EXECUTABLE", "CONDITIONAL", "NOT_EXECUTABLE"})
ATTENTION_STATUSES = frozenset({"IN_PROGRESS", "COMPLETED", "NO_ACTION"})
ORDER_SOURCES = frozenset({"平台手工订单", "直连订单"})
TRIP_TYPES = frozenset({"ONE_WAY", "ROUND_TRIP", "MULTI_CITY"})
SEGMENT_TYPES = frozenset({"直达", "中转"})
CODE_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
PERMISSION_CREATE = "smart_placement.create"
PERMISSION_EDIT = "smart_placement.edit"
PERMISSION_DELETE = "smart_placement.delete"
PERMISSION_WITHDRAW = "smart_placement.withdraw"
PERMISSION_CANCEL = "smart_placement.cancel"
PERMISSION_REVIEW_DATA = "smart_placement.review_data"
PERMISSION_REVIEW_POLICY = "smart_placement.review_policy"
PERMISSION_CLAIM = "smart_placement.claim"
PERMISSION_EXECUTE = "smart_placement.execute"
PERMISSION_ORDER_ATTENTION = "smart_placement.orders.attention"
PERMISSION_STOP = "smart_placement.stop"
PERMISSION_EFFECT_REVIEW = "smart_placement.effect_review"


class SmartPlacementUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return business_now_naive()


def _business_now() -> datetime:
    return business_now_naive()


def _text(value: Any, name: str, maximum: int, *, required: bool = False) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{name}不能为空")
    if len(result) > maximum:
        raise ValueError(f"{name}不能超过{maximum}个字符")
    return result


def _code(value: Any, name: str, *, required: bool = False) -> str:
    result = _text(value, name, 128, required=required)
    if result and not CODE_RE.fullmatch(result):
        raise ValueError(f"{name}格式不合法")
    return result


def _date_value(value: Any, name: str, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{name}不能为空")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise ValueError(f"{name}必须为YYYY-MM-DD") from error


def _datetime_value(value: Any, name: str, *, required: bool = False) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{name}不能为空")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return as_business_naive(parsed)
    except ValueError as error:
        raise ValueError(f"{name}必须为有效日期时间") from error


def _decimal(value: Any, name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{name}必须为数字") from error


def _integer(value: Any, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name}必须为整数") from error
    if result < 0:
        raise ValueError(f"{name}不能小于0")
    return result


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() in {"1", "true", "yes"}


def _order_source(value: Any, name: str = "订单来源") -> str | None:
    result = _text(value, name, 32) or None
    if result and result not in ORDER_SOURCES:
        raise ValueError(f"{name}只支持平台手工订单或直连订单")
    return result


def _segment_type(value: Any, name: str = "航段类型") -> str | None:
    result = _text(value, name, 32) or None
    if result == "直飞":
        result = "直达"
    if result and result not in SEGMENT_TYPES:
        raise ValueError(f"{name}只支持直达或中转")
    return result


def _trip_type(value: Any, name: str = "航程类型") -> str | None:
    aliases = {
        "单程": "ONE_WAY",
        "往返": "ROUND_TRIP",
        "多程": "MULTI_CITY",
        "多城市": "MULTI_CITY",
    }
    result = _text(value, name, 32).upper() or None
    if result:
        result = aliases.get(result, result)
    if result and result not in TRIP_TYPES:
        raise ValueError(f"{name}只支持单程、往返或多程")
    return result


def _loss_thresholds(values: dict[str, Any], *, required: bool = False) -> tuple[Decimal | None, Decimal | None]:
    minimum = _decimal(values.get("lossThresholdMin"), "亏损阈值下限")
    maximum = _decimal(values.get("lossThresholdMax"), "亏损阈值上限")
    if required and (minimum is None or maximum is None):
        raise ValueError("亏损阈值区间不能为空")
    if minimum is not None and minimum < 0:
        raise ValueError("亏损阈值下限不能小于0")
    if maximum is not None and maximum < 0:
        raise ValueError("亏损阈值上限不能小于0")
    if minimum is not None and maximum is not None and maximum < minimum:
        raise ValueError("亏损阈值上限不能小于下限")
    return minimum, maximum


def _required_value(values: dict[str, Any], key: str, name: str) -> Any:
    value = values.get(key)
    if value in (None, ""):
        raise ValueError(f"{name}不能为空")
    return value


def _task_fields(values: dict[str, Any], *, submit: bool) -> dict[str, Any]:
    """Validate and normalize every editable task field in one place."""
    source = _text(values.get("opportunitySource"), "机会来源", 32, required=True).upper()
    rule_code = _code(
        values.get("analysisRuleCode"), "分析规则编号",
        required=submit and source == "AUTO_ANALYSIS",
    )
    analysis_start = _date_value(values.get("analysisStartDate"), "分析开始日期", required=True)
    analysis_end = _date_value(values.get("analysisEndDate"), "分析结束日期", required=True)
    if analysis_end < analysis_start:
        raise ValueError("分析结束日期不能早于开始日期")

    order_start = _date_value(values.get("orderStartDate"), "销售开始日期")
    order_end = _date_value(values.get("orderEndDate"), "销售结束日期")
    if order_start and order_end and order_end < order_start:
        raise ValueError("销售结束日期不能早于开始日期")
    travel_start = _date_value(values.get("travelStartDate"), "去程旅行开始日期")
    travel_end = _date_value(values.get("travelEndDate"), "去程旅行结束日期")
    if travel_start and travel_end and travel_end < travel_start:
        raise ValueError("去程旅行结束日期不能早于开始日期")

    long_term = _bool(values.get("longTerm"))

    suggested_start = _datetime_value(
        values.get("suggestedEffectiveStart"), "建议生效时间", required=submit,
    )
    suggested_end = _datetime_value(
        values.get("suggestedEffectiveEnd"), "建议失效时间", required=submit and not long_term,
    )
    if long_term:
        suggested_end = None
    if suggested_start and suggested_end and suggested_end <= suggested_start:
        raise ValueError("建议失效时间必须晚于生效时间")

    loss_threshold_min, loss_threshold_max = _loss_thresholds(values, required=submit)

    include_cabins = _text(values.get("includeCabins"), "包含舱位", 500)
    exclude_cabins = _text(values.get("excludeCabins"), "排除舱位", 500)
    included_list = list(dict.fromkeys(
        item.strip().upper()
        for item in include_cabins.replace("，", ",").split(",")
        if item.strip()
    ))
    excluded_list = list(dict.fromkeys(
        item.strip().upper()
        for item in exclude_cabins.replace("，", ",").split(",")
        if item.strip()
    ))
    overlap = sorted(set(included_list) & set(excluded_list))
    if overlap:
        raise ValueError(f"包含舱位和排除舱位不能重复：{','.join(overlap)}")

    priority = _text(values.get("priority") or "MEDIUM", "优先级", 16).upper()
    if priority not in PRIORITIES:
        raise ValueError("优先级不支持")

    if submit:
        _required_value(values, "historicalTicketCount", "历史票数")
        _required_value(values, "historicalProfitCny", "历史利润")
        _required_value(values, "estimatedMonthTicketCount", "预估月票数")
        _required_value(values, "estimatedMonthProfitCny", "预估月利润")

    return {
        "opportunity_name": _text(values.get("opportunityName"), "机会名称", 200, required=True),
        "opportunity_source": source,
        "analysis_rule_code": rule_code or None,
        "analysis_start_date": analysis_start,
        "analysis_end_date": analysis_end,
        "platform_code": _code(values.get("platformCode"), "平台编码") or None,
        "platform_name": _text(values.get("platformName"), "平台名称", 100, required=True),
        "site_code": _code(values.get("siteCode"), "站点编码") or None,
        "site_name": _text(values.get("siteName"), "站点名称", 150) or None,
        "airline_code": _code(values.get("airlineCode"), "航司", required=True).upper(),
        "departure_code": _code(values.get("departureCode"), "出发地").upper() or None,
        "arrival_code": _code(values.get("arrivalCode"), "到达地").upper() or None,
        # route_text is retained for legacy rows only. New policies match the
        # structured departure/arrival fields and do not require a full route.
        "route_text": None,
        "journey_type": _trip_type(values.get("journeyType")),
        "segment_type": _segment_type(values.get("segmentType")),
        "flight_nos": _text(values.get("flightNos"), "航班号", 500) or None,
        "include_cabins": ",".join(included_list) or None,
        "exclude_cabins": ",".join(excluded_list) or None,
        "product_type": _text(values.get("productType"), "产品类型", 150) or None,
        "order_source": _order_source(values.get("orderSource")),
        "order_start_date": order_start,
        "order_end_date": order_end,
        "advance_sale_days": _integer(values.get("advanceSaleDays"), "提前销售天数"),
        "travel_start_date": travel_start,
        "travel_end_date": travel_end,
        "placement_method": _text(values.get("placementMethod"), "建议投放方式", 300, required=True),
        "loss_threshold_min": loss_threshold_min,
        "loss_threshold_max": loss_threshold_max,
        "long_term_flag": 1 if long_term else 0,
        "suggested_effective_start": suggested_start,
        "suggested_effective_end": suggested_end,
        "historical_ticket_count": _integer(values.get("historicalTicketCount"), "历史票数"),
        "historical_profit_cny": _decimal(values.get("historicalProfitCny"), "历史利润"),
        "estimated_month_ticket_count": _integer(values.get("estimatedMonthTicketCount"), "预估月票数"),
        "estimated_month_profit_cny": _decimal(values.get("estimatedMonthProfitCny"), "预估月利润"),
        "analysis_conclusion": _text(values.get("analysisConclusion"), "分析结论", 10_000, required=True),
        "risk_note": _text(values.get("riskNote"), "风险提示", 10_000) or None,
        "priority": priority,
        "expected_complete_at": _datetime_value(values.get("expectedCompleteAt"), "期望完成时间", required=True),
    }


def _is_missing_table(error: Exception) -> bool:
    return bool(getattr(error, "args", ())) and error.args[0] == 1146


def _actor(user: dict[str, Any]) -> tuple[int, str, str]:
    user_id = int(user.get("id") or 0)
    if not user_id:
        raise PermissionError("登录用户信息不完整")
    name = str(user.get("display_name") or user.get("displayName") or user.get("username") or user_id)
    roles = user.get("business_roles") or user.get("businessRoles") or []
    role_codes = [str(row.get("code")) for row in roles if isinstance(row, dict) and row.get("code")]
    role = "ADMIN" if _is_admin(user) else ",".join(role_codes) or "USER"
    return user_id, name[:100], role


def _is_admin(user: dict[str, Any]) -> bool:
    return bool(user.get("is_admin") or user.get("isAdmin"))


def _permissions(user: dict[str, Any]) -> set[str]:
    return {str(value) for value in (user.get("permissions") or [])}


def _has_permission(user: dict[str, Any], permission: str) -> bool:
    return _is_admin(user) or permission in _permissions(user)


def _require_permission(user: dict[str, Any], permission: str, message: str) -> None:
    if _has_permission(user, permission):
        return
    if user.get("rbac_configured") is False or user.get("rbacConfigured") is False:
        raise PermissionError("智能投放角色尚未配置，请管理员先执行smart-placement-rbac.sql并分配岗位")
    raise PermissionError(message)


def _dict_rows(cursor, rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [dict(row) for row in rows]
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in rows]


def _dict_row(cursor, row: Any) -> dict[str, Any] | None:
    return _dict_rows(cursor, [row])[0] if row is not None else None


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part[:1].upper() + part[1:] for part in tail)
    return {camel(key): _json_value(value) for key, value in row.items()}


class SmartPlacementService:
    def __init__(
        self,
        config: dict[str, Any],
        source: DataSource | None = None,
        monitor_rule_compiler: MonitorRuleCompiler | None = None,
    ):
        self.source = source or DataSource({**config, "DATA_MODE": "mysql"})
        self.monitor_rule_compiler = monitor_rule_compiler or MonitorRuleCompiler()

    def _table(self, name: str) -> str:
        return f"{self.source.database}.{name}"

    def dimension_options(self) -> dict[str, Any]:
        """Return canonical single-select values from the MySQL ADS mirror."""
        cache_key = self.source.cache_key
        ttl = max(int(self.source.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _DIMENSION_CACHE_LOCK:
            cached = _DIMENSION_CACHE.get(cache_key)
            if cached and monotonic_time.monotonic() - cached[0] < ttl:
                return deepcopy(cached[1])

        qualified = self._table(DIMENSION_TABLE)
        queries = {
            "platforms": (
                f"SELECT DISTINCT ota_code, ota_cname FROM {qualified} "
                "WHERE row_type='data' AND NULLIF(TRIM(ota_cname),'') IS NOT NULL "
                "ORDER BY ota_cname, ota_code LIMIT 501",
                500,
            ),
            "sites": (
                f"SELECT DISTINCT ota_code, ota_cname, ota_site_code, ota_site_cname FROM {qualified} "
                "WHERE row_type='data' AND NULLIF(TRIM(ota_site_cname),'') IS NOT NULL "
                "ORDER BY ota_cname, ota_site_cname, ota_site_code LIMIT 2001",
                2000,
            ),
            "airlines": (
                f"SELECT DISTINCT airline_code FROM {qualified} "
                "WHERE row_type='data' AND NULLIF(TRIM(airline_code),'') IS NOT NULL "
                "ORDER BY airline_code LIMIT 501",
                500,
            ),
            "products": (
                f"SELECT DISTINCT ota_code, ota_cname, ticket_product_raw FROM {qualified} "
                "WHERE row_type='data' AND NULLIF(TRIM(ticket_product_raw),'') IS NOT NULL "
                "ORDER BY ota_cname, ticket_product_raw LIMIT 1001",
                1000,
            ),
        }
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            rows: dict[str, list[Any]] = {}
            truncated: dict[str, bool] = {}
            for key, (query, limit) in queries.items():
                cursor.execute(query)
                fetched = list(cursor.fetchall())
                truncated[key] = len(fetched) > limit
                rows[key] = fetched[:limit]
            result = {
                "source": f"MySQL · {qualified}",
                "platforms": [
                    {"value": str(name).strip(), "label": str(name).strip(), "code": str(code or "").strip()}
                    for code, name in rows["platforms"]
                ],
                "sites": [
                    {
                        "value": str(site_name).strip(), "label": str(site_name).strip(),
                        "code": str(site_code or "").strip(),
                        "platformName": str(platform_name or "").strip(),
                        "platformCode": str(platform_code or "").strip(),
                    }
                    for platform_code, platform_name, site_code, site_name in rows["sites"]
                ],
                "airlines": [
                    {"value": str(row[0]).strip().upper(), "label": str(row[0]).strip().upper()}
                    for row in rows["airlines"]
                ],
                "products": [
                    {
                        "value": str(product).strip(), "label": str(product).strip(),
                        "platformName": str(platform_name or "").strip(),
                        "platformCode": str(platform_code or "").strip(),
                    }
                    for platform_code, platform_name, product in rows["products"]
                ],
                "truncated": truncated,
            }
            if ttl > 0:
                with _DIMENSION_CACHE_LOCK:
                    _DIMENSION_CACHE[cache_key] = (monotonic_time.monotonic(), deepcopy(result))
            return result
        except Exception as error:
            LOGGER.exception("Smart placement dimension options failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("综合分析ADS表尚未同步，暂时无法加载投放维度下拉选项") from error
            raise SmartPlacementUnavailable("投放维度选项查询失败") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    @staticmethod
    def _task_no() -> str:
        return f"SP{_business_now():%Y%m%d%H%M%S}{secrets.token_hex(3).upper()}"

    @staticmethod
    def _match_no() -> str:
        return f"SM{_business_now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}"

    def _log(
        self, cursor, *, task_id: int, action: str, actor: tuple[int, str, str],
        from_status: str | None = None, to_status: str | None = None,
        note: str | None = None, detail: dict[str, Any] | None = None,
        match_id: int | None = None,
    ) -> None:
        cursor.execute(
            f"""
            INSERT INTO {self._table(LOG_TABLE)} (
                task_id, match_id, action_code, from_status, to_status,
                operator_id, operator_name, operator_role_snapshot,
                operation_note, detail_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id, match_id, action, from_status, to_status,
                actor[0], actor[1], actor[2], note,
                json.dumps(detail, ensure_ascii=False, default=_json_value) if detail else None,
            ),
        )

    def _task_for_update(self, cursor, task_id: int) -> dict[str, Any]:
        cursor.execute(
            f"SELECT * FROM {self._table(TASK_TABLE)} WHERE id=%s AND is_deleted=0 FOR UPDATE",
            (task_id,),
        )
        row = _dict_row(cursor, cursor.fetchone())
        if not row:
            raise ValueError("投放任务不存在")
        return row

    def _visibility_condition(self, user: dict[str, Any], alias: str = "t") -> tuple[str, list[Any]]:
        if _is_admin(user):
            return "1=1", []
        actor_id = int(user.get("id") or 0)
        if not actor_id:
            raise PermissionError("登录用户信息不完整")
        raw_scopes = user.get("data_scopes") or user.get("dataScopes") or {}
        scope_type = str(raw_scopes.get(TASK_SCOPE_RESOURCE) or "").upper()
        if scope_type == "ALL":
            return "1=1", []
        clauses: list[str] = []
        params: list[Any] = []
        permissions = _permissions(user)
        if permissions.intersection({PERMISSION_CREATE, PERMISSION_EDIT, PERMISSION_DELETE, PERMISSION_WITHDRAW}):
            clauses.append(f"{alias}.created_by_id=%s")
            params.append(actor_id)
        if PERMISSION_CLAIM in permissions or PERMISSION_EXECUTE in permissions:
            clauses.append(f"({alias}.status='CLAIMABLE' OR {alias}.current_assignee_id=%s)")
            params.append(actor_id)
        workflow_scope = scope_type in {"WORKFLOW", "MANAGED"} or not scope_type
        if workflow_scope and PERMISSION_CANCEL in permissions:
            clauses.append(f"{alias}.status IN ('PENDING_DATA_REVIEW','PENDING_POLICY_REVIEW','CLAIMABLE')")
        if workflow_scope and PERMISSION_REVIEW_DATA in permissions:
            clauses.append(
                f"({alias}.status='PENDING_DATA_REVIEW' OR EXISTS (SELECT 1 FROM {self._table(REVIEW_TABLE)} rv WHERE rv.task_id={alias}.id AND rv.review_stage='DATA_MANAGER' AND rv.reviewer_id=%s))"
            )
            params.append(actor_id)
        if workflow_scope and PERMISSION_REVIEW_POLICY in permissions:
            clauses.append(
                f"({alias}.status='PENDING_POLICY_REVIEW' OR EXISTS (SELECT 1 FROM {self._table(REVIEW_TABLE)} rv WHERE rv.task_id={alias}.id AND rv.review_stage='POLICY_MANAGER' AND rv.reviewer_id=%s))"
            )
            params.append(actor_id)
        if scope_type == "MANAGED":
            clauses.append(
                f"EXISTS (SELECT 1 FROM {self._table(MANAGER_RELATION_TABLE)} mr "
                f"WHERE mr.manager_user_id=%s AND mr.resource_code=%s AND mr.is_active=1 "
                f"AND (mr.member_user_id={alias}.created_by_id "
                f"OR mr.member_user_id={alias}.current_assignee_id "
                f"OR EXISTS (SELECT 1 FROM {self._table(REVIEW_TABLE)} mrv "
                f"WHERE mrv.task_id={alias}.id AND mrv.reviewer_id=mr.member_user_id)))"
            )
            params.extend([actor_id, MANAGER_RELATION_RESOURCE])
        return ("(" + " OR ".join(clauses) + ")", params) if clauses else ("1=0", [])

    def _order_visibility_condition(self, user: dict[str, Any], alias: str = "m") -> tuple[str, list[Any]]:
        if _is_admin(user):
            return "1=1", []
        actor_id = int(user.get("id") or 0)
        if not actor_id:
            raise PermissionError("登录用户信息不完整")
        raw_scopes = user.get("data_scopes") or user.get("dataScopes") or {}
        scope_type = str(raw_scopes.get(ORDER_SCOPE_RESOURCE) or "SELF").upper()
        if scope_type == "ALL":
            return "1=1", []
        task_alias = "scope_task"
        task_participation = [
            f"{task_alias}.created_by_id=%s",
            f"{task_alias}.current_assignee_id=%s",
        ]
        params: list[Any] = [actor_id, actor_id, actor_id]
        if scope_type in {"WORKFLOW", "MANAGED"}:
            task_participation.append(
                f"EXISTS (SELECT 1 FROM {self._table(REVIEW_TABLE)} scope_review "
                f"WHERE scope_review.task_id={task_alias}.id AND scope_review.reviewer_id=%s)"
            )
            params.append(actor_id)
        clauses = [
            f"{alias}.attention_owner_id=%s",
            f"EXISTS (SELECT 1 FROM {self._table(TASK_TABLE)} {task_alias} "
            f"WHERE {task_alias}.id={alias}.task_id AND ({' OR '.join(task_participation)}))",
        ]
        if scope_type == "MANAGED":
            clauses.append(
                f"EXISTS (SELECT 1 FROM {self._table(MANAGER_RELATION_TABLE)} mr "
                f"JOIN {self._table(TASK_TABLE)} managed_task ON managed_task.id={alias}.task_id "
                f"WHERE mr.manager_user_id=%s AND mr.resource_code=%s AND mr.is_active=1 "
                f"AND (mr.member_user_id={alias}.attention_owner_id "
                f"OR mr.member_user_id=managed_task.created_by_id "
                f"OR mr.member_user_id=managed_task.current_assignee_id "
                f"OR EXISTS (SELECT 1 FROM {self._table(REVIEW_TABLE)} managed_review "
                f"WHERE managed_review.task_id=managed_task.id AND managed_review.reviewer_id=mr.member_user_id)))"
            )
            params.append(actor_id)
            params.append(MANAGER_RELATION_RESOURCE)
        return "(" + " OR ".join(clauses) + ")", params

    def list_tasks(
        self, *, user: dict[str, Any], status: str = "", keyword: str = "", platform: str = "",
        airline: str = "", owner: str = "", scope: str = "",
        page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        if status and status not in TASK_STATUSES:
            raise ValueError("任务状态不支持")
        if scope not in {"", "review", "claim", "mine"}:
            raise ValueError("任务分组不支持")
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100))
        visibility, visibility_params = self._visibility_condition(user)
        where = ["t.is_deleted=0", visibility]
        params: list[Any] = list(visibility_params)
        if status:
            where.append("t.status=%s"); params.append(status)
        if keyword:
            token = f"%{_text(keyword, '搜索词', 100)}%"
            where.append("(t.task_no LIKE %s OR t.opportunity_name LIKE %s OR t.airline_code LIKE %s OR t.departure_code LIKE %s OR t.arrival_code LIKE %s)")
            params.extend([token, token, token, token, token])
        if platform:
            where.append("t.platform_name=%s"); params.append(_text(platform, "平台", 100))
        if airline:
            where.append("t.airline_code=%s"); params.append(_code(airline, "航司"))
        if owner:
            where.append("t.current_assignee_name=%s"); params.append(_text(owner, "负责人", 100))
        if scope == "review":
            review_statuses: list[str] = []
            if _is_admin(user) or _has_permission(user, PERMISSION_REVIEW_DATA):
                review_statuses.append("'PENDING_DATA_REVIEW'")
            if _is_admin(user) or _has_permission(user, PERMISSION_REVIEW_POLICY):
                review_statuses.append("'PENDING_POLICY_REVIEW'")
            where.append(f"t.status IN ({','.join(review_statuses)})" if review_statuses else "1=0")
        elif scope == "claim":
            where.append("t.status='CLAIMABLE'" if _has_permission(user, PERMISSION_CLAIM) else "1=0")
        elif scope == "mine":
            actor_id = int(user.get("id") or 0)
            if not actor_id:
                raise ValueError("登录用户信息不完整")
            where.append("(t.current_assignee_id=%s OR t.created_by_id=%s)")
            params.extend([actor_id, actor_id])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT t.status, COUNT(1) AS amount FROM {self._table(TASK_TABLE)} t WHERE t.is_deleted=0 AND {visibility} GROUP BY t.status",
                tuple(visibility_params),
            )
            status_rows = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(TASK_TABLE)} t WHERE {condition}", tuple(params))
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"""
                SELECT id, task_no, opportunity_name, opportunity_source,
                       platform_name, site_name, airline_code, departure_code,
                       arrival_code, route_text, include_cabins, exclude_cabins,
                       product_type, order_source, placement_method, estimated_month_ticket_count,
                       estimated_month_profit_cny, priority, status,
                       current_assignee_id, current_assignee_name, expected_complete_at,
                       created_by_id, created_by_name,
                       created_at, updated_at
                FROM {self._table(TASK_TABLE)} t
                WHERE {condition}
                ORDER BY FIELD(priority,'HIGH','MEDIUM','LOW'),
                         CASE WHEN expected_complete_at IS NULL THEN 1 ELSE 0 END,
                         expected_complete_at, id DESC
                LIMIT %s OFFSET %s
                """,
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            summary = {key: 0 for key in TASK_STATUSES}
            for row in status_rows:
                summary[str(row["status"])] = int(row["amount"])
            return {"available": True, "error": "", "summary": summary, "rows": rows, "total": total, "page": page, "pageSize": page_size}
        except Exception as error:
            LOGGER.exception("Smart placement task list failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def analysis_coverage(
        self, *, user: dict[str, Any], start_value: Any, end_value: Any,
        filters: dict[str, Any] | None = None, limit: int = 1000,
    ) -> dict[str, Any]:
        """Return placement tasks that can explain the current smart-analysis slice.

        The smart ADS remains the source of business metrics.  This query only adds
        workflow coverage and matched-order evidence, and always applies the same
        task visibility rules as the placement workbench.
        """
        first = _date_value(start_value, "开始日期", required=True)
        last = _date_value(end_value, "结束日期", required=True)
        if first is None or last is None or first > last:
            raise ValueError("智能综合分析日期范围不正确")
        limit = max(1, min(int(limit), 2000))
        visibility, visibility_params = self._visibility_condition(user)
        where = [
            "t.is_deleted=0", visibility,
            "(t.analysis_start_date IS NULL OR t.analysis_start_date<=%s)",
            "(t.analysis_end_date IS NULL OR t.analysis_end_date>=%s)",
        ]
        params: list[Any] = [*visibility_params, last, first]
        cleaned = {key: str(value or "").strip() for key, value in (filters or {}).items()}

        field_map = {
            "platform": "t.platform_name", "site": "t.site_name",
            "airline": "t.airline_code", "productType": "t.product_type",
            "orderSource": "t.order_source",
        }
        wildcard_fields = {"site", "productType", "orderSource"}
        for key, column in field_map.items():
            value = cleaned.get(key, "")
            if not value:
                continue
            if value == "__NULL__":
                where.append(f"NULLIF(TRIM({column}),'') IS NULL")
            elif key in wildcard_fields:
                where.append(f"(NULLIF(TRIM({column}),'') IS NULL OR {column}=%s)")
                params.append(value)
            else:
                where.append(f"{column}=%s")
                params.append(value)
        route = cleaned.get("route", "")
        if route:
            if route == "__NULL__":
                where.append("NULLIF(TRIM(t.route_text),'') IS NULL AND NULLIF(TRIM(t.departure_code),'') IS NULL AND NULLIF(TRIM(t.arrival_code),'') IS NULL")
            else:
                where.append("((NULLIF(TRIM(t.route_text),'') IS NULL AND NULLIF(TRIM(t.departure_code),'') IS NULL AND NULLIF(TRIM(t.arrival_code),'') IS NULL) OR t.route_text=%s OR CONCAT_WS('-',NULLIF(t.departure_code,''),NULLIF(t.arrival_code,''))=%s)")
                params.extend([route, route])

        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT t.id,t.task_no,t.opportunity_name,t.status,t.priority,
                       t.platform_name,t.site_name,t.airline_code,t.departure_code,
                       t.arrival_code,t.route_text,t.product_type,t.order_source,
                       t.analysis_start_date,t.analysis_end_date,
                       t.current_assignee_name,t.monitoring_started_at,t.updated_at,
                       (SELECT e.external_policy_id FROM {self._table(EXECUTION_TABLE)} e
                        WHERE e.task_id=t.id AND e.execution_result='SUCCESS'
                        ORDER BY e.id DESC LIMIT 1) AS external_policy_id,
                       (SELECT COUNT(1) FROM {self._table(MATCH_TABLE)} m
                        WHERE m.task_id=t.id) AS matched_order_count
                FROM {self._table(TASK_TABLE)} t
                WHERE {condition}
                ORDER BY CASE t.status WHEN 'MONITORING' THEN 0 WHEN 'IN_PROGRESS' THEN 1
                         WHEN 'CLAIMABLE' THEN 2 WHEN 'PENDING_POLICY_REVIEW' THEN 3
                         WHEN 'PENDING_DATA_REVIEW' THEN 4 WHEN 'DRAFT' THEN 5 ELSE 6 END,
                         t.updated_at DESC,t.id DESC
                LIMIT %s
                """,
                tuple([*params, limit + 1]),
            )
            raw_rows = _dict_rows(cursor, list(cursor.fetchall()))
            truncated = len(raw_rows) > limit
            raw_rows = raw_rows[:limit]
            status_counts = {status: 0 for status in TASK_STATUSES}
            matched_order_count = 0
            for row in raw_rows:
                status = str(row.get("status") or "")
                if status in status_counts:
                    status_counts[status] += 1
                matched_order_count += int(row.get("matched_order_count") or 0)
            return {
                "available": True, "error": "", "truncated": truncated,
                "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
                "summary": {
                    "taskCount": len(raw_rows),
                    "monitoringTaskCount": status_counts["MONITORING"],
                    "workflowTaskCount": sum(status_counts[key] for key in (
                        "PENDING_DATA_REVIEW", "PENDING_POLICY_REVIEW", "CLAIMABLE", "IN_PROGRESS",
                    )),
                    "matchedOrderCount": matched_order_count,
                    "statusCounts": status_counts,
                },
                "rows": [_public_row(row) for row in raw_rows],
            }
        except (PermissionError, ValueError):
            raise
        except Exception as error:
            LOGGER.exception("Smart placement analysis coverage failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，综合分析暂时只能展示智能指标") from error
            raise SmartPlacementUnavailable("投放覆盖查询失败，综合分析暂时只能展示智能指标") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def task_detail(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            visibility, visibility_params = self._visibility_condition(user)
            cursor.execute(
                f"SELECT t.* FROM {self._table(TASK_TABLE)} t WHERE t.id=%s AND t.is_deleted=0 AND {visibility}",
                tuple([task_id, *visibility_params]),
            )
            task = _dict_row(cursor, cursor.fetchone())
            if not task:
                raise ValueError("投放任务不存在")
            cursor.execute(f"SELECT * FROM {self._table(REVIEW_TABLE)} WHERE task_id=%s ORDER BY id", (task_id,))
            reviews = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(EXECUTION_TABLE)} WHERE task_id=%s ORDER BY attempt_no DESC", (task_id,))
            executions = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(LOG_TABLE)} WHERE task_id=%s ORDER BY id DESC LIMIT 200", (task_id,))
            logs = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(EFFECT_REVIEW_TABLE)} WHERE task_id=%s ORDER BY id DESC", (task_id,))
            effect_reviews = _dict_rows(cursor, list(cursor.fetchall()))
            return {
                "task": _public_row(task),
                "reviews": [_public_row(row) for row in reviews],
                "executions": [_public_row(row) for row in executions],
                "logs": [_public_row(row) for row in logs],
                "effectReviews": [_public_row(row) for row in effect_reviews],
            }
        except ValueError:
            raise
        except Exception as error:
            LOGGER.exception("Smart placement task detail failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务详情查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def create_task(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_CREATE, "当前账号没有投放机会录入权限")
        actor = _actor(user)
        submit = _bool(values.get("submit"))
        fields = _task_fields(values, submit=submit)
        status = "PENDING_DATA_REVIEW" if submit else "DRAFT"
        now = _now()
        task_no = self._task_no()
        columns = ["task_no", *fields.keys(), "status", "submitted_at", "created_by_id", "created_by_name",
            "updated_by_id", "updated_by_name", "created_at", "updated_at",
        ]
        params = [
            task_no, *fields.values(),
            status, now if status == "PENDING_DATA_REVIEW" else None,
            actor[0], actor[1], actor[0], actor[1], now, now,
        ]
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            placeholders = ",".join(["%s"] * len(columns))
            cursor.execute(f"INSERT INTO {self._table(TASK_TABLE)} ({','.join(columns)}) VALUES ({placeholders})", tuple(params))
            task_id = int(cursor.lastrowid)
            self._log(cursor, task_id=task_id, action="SUBMIT" if status != "DRAFT" else "CREATE", actor=actor, to_status=status, note="提交数据经理审核" if status != "DRAFT" else "保存草稿")
            connection.commit()
            return {"id": task_id, "taskNo": task_no, "status": status}
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement task create failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务创建失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_task(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_EDIT, "当前账号没有投放机会编辑权限")
        actor = _actor(user)
        submit = _bool(values.get("submit"))
        fields = _task_fields(values, submit=submit)
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "DRAFT":
                raise ValueError("只有草稿或退回修改的任务可以编辑")
            editable_people = {int(task.get("created_by_id") or 0), int(task.get("current_assignee_id") or 0)}
            if actor[0] not in editable_people and actor[2] != "ADMIN":
                raise PermissionError("只能由创建人、当前负责人或管理员编辑该任务")
            resume_stage = str(task.get("resume_review_stage") or "DATA_MANAGER")
            next_status = (
                "PENDING_POLICY_REVIEW" if submit and resume_stage == "POLICY_MANAGER"
                else "PENDING_DATA_REVIEW" if submit else "DRAFT"
            )
            assignments = ",".join(f"{name}=%s" for name in fields)
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET {assignments}, status=%s,
                        submitted_at=%s, resume_review_stage=%s, updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                tuple([*fields.values(), next_status, now if submit else task.get("submitted_at"), None if submit else task.get("resume_review_stage"), actor[0], actor[1], now, task_id]),
            )
            self._log(
                cursor, task_id=task_id, action="RESUBMIT" if submit else "UPDATE",
                actor=actor, from_status="DRAFT", to_status=next_status,
                note=("修改后重新提交政策经理审核" if resume_stage == "POLICY_MANAGER" else "修改后重新提交数据经理审核") if submit else "更新草稿",
            )
            connection.commit()
            return {"id": task_id, "taskNo": task["task_no"], "status": next_status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement task update failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务修改失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def delete_task(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        _require_permission(user, PERMISSION_DELETE, "当前账号没有删除投放机会的权限")
        actor = _actor(user)
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] not in {"DRAFT", "REJECTED"}:
                raise ValueError("只有草稿或已驳回任务可以删除")
            if int(task.get("created_by_id") or 0) != actor[0] and actor[2] != "ADMIN":
                raise PermissionError("只能由创建人或管理员删除该任务")
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET is_deleted=1,
                        updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                (actor[0], actor[1], now, task_id),
            )
            self._log(
                cursor, task_id=task_id, action="DELETE", actor=actor,
                from_status=task["status"], to_status=task["status"], note="删除投放任务",
            )
            connection.commit()
            return {"id": task_id, "deleted": True}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement task delete failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务删除失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def withdraw_task(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        _require_permission(user, PERMISSION_WITHDRAW, "当前账号没有撤回投放任务的权限")
        actor = _actor(user)
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "PENDING_DATA_REVIEW":
                raise ValueError("只有尚未处理的待数据审核任务可以撤回")
            if int(task.get("created_by_id") or 0) != actor[0] and actor[2] != "ADMIN":
                raise PermissionError("只能由创建人或管理员撤回该任务")
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET status='DRAFT', submitted_at=NULL,
                        resume_review_stage='DATA_MANAGER', updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                (actor[0], actor[1], now, task_id),
            )
            self._log(
                cursor, task_id=task_id, action="WITHDRAW", actor=actor,
                from_status="PENDING_DATA_REVIEW", to_status="DRAFT",
                note="创建人撤回并继续修改",
            )
            connection.commit()
            return {"id": task_id, "taskNo": task["task_no"], "status": "DRAFT"}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement task withdraw failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务撤回失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def cancel_task(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_CANCEL, "当前账号没有作废投放任务的权限")
        actor = _actor(user)
        reason = _text(values.get("reason"), "作废原因", 1000, required=True)
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] not in {"PENDING_DATA_REVIEW", "PENDING_POLICY_REVIEW", "CLAIMABLE"}:
                raise ValueError("只有待审核或待认领任务可以作废")
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET status='CLOSED', closed_at=%s,
                        resume_review_stage=NULL, updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                (now, actor[0], actor[1], now, task_id),
            )
            self._log(
                cursor, task_id=task_id, action="CANCEL", actor=actor,
                from_status=task["status"], to_status="CLOSED", note=reason,
            )
            connection.commit()
            return {"id": task_id, "taskNo": task["task_no"], "status": "CLOSED"}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement task cancel failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务作废失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def review_task(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        stage = _text(values.get("stage"), "审核环节", 32, required=True).upper()
        if stage not in REVIEW_STAGES:
            raise ValueError("审核环节不支持")
        _require_permission(
            user,
            PERMISSION_REVIEW_DATA if stage == "DATA_MANAGER" else PERMISSION_REVIEW_POLICY,
            "当前账号没有数据审核权限" if stage == "DATA_MANAGER" else "当前账号没有政策审核权限",
        )
        actor = _actor(user)
        result = _text(values.get("result"), "审核结果", 16, required=True).upper()
        if result not in REVIEW_RESULTS:
            raise ValueError("审核结果不支持")
        comment = _text(values.get("comment"), "审核意见", 10_000, required=result != "APPROVED")
        policy_executable = _text(values.get("policyExecutableLevel"), "政策可执行性", 32).upper()
        risk_level = _text(values.get("riskLevel"), "风险等级", 16).upper()
        if stage == "DATA_MANAGER" and result == "APPROVED":
            confirmations = (
                _bool(values.get("dataMetricConfirmed")),
                _bool(values.get("sampleSufficient")),
                _bool(values.get("estimatedValueConfirmed")),
            )
            if not all(confirmations):
                raise ValueError("数据审核通过前必须完成数据口径、样本充分性和预估价值确认")
        if stage == "POLICY_MANAGER":
            if not policy_executable or policy_executable not in POLICY_EXECUTABLE_LEVELS:
                raise ValueError("请选择有效的政策可执行性")
            if not risk_level or risk_level not in PRIORITIES:
                raise ValueError("请选择风险等级")
            if result == "APPROVED" and policy_executable == "NOT_EXECUTABLE":
                raise ValueError("政策不可执行时不能选择审核通过")
        expected_status, approved_status, reviewed_column = REVIEW_STAGES[stage]
        next_status = approved_status if result == "APPROVED" else "DRAFT" if result == "RETURNED" else "REJECTED"
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != expected_status:
                raise ValueError(f"当前任务状态为{task['status']}，不能执行该审核")
            cursor.execute(
                f"""
                INSERT INTO {self._table(REVIEW_TABLE)} (
                    task_id, review_stage, review_result, review_comment,
                    data_metric_confirmed, sample_sufficient, estimated_value_confirmed,
                    policy_executable_level, risk_level, risk_control_requirement,
                    claim_scope, adjusted_priority, adjusted_complete_at,
                    reviewer_id, reviewer_name, reviewer_role_snapshot, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    task_id, stage, result, comment or None,
                    _bool(values.get("dataMetricConfirmed")) if stage == "DATA_MANAGER" else None,
                    _bool(values.get("sampleSufficient")) if stage == "DATA_MANAGER" else None,
                    _bool(values.get("estimatedValueConfirmed")) if stage == "DATA_MANAGER" else None,
                    policy_executable or None if stage == "POLICY_MANAGER" else None,
                    risk_level or None if stage == "POLICY_MANAGER" else None,
                    _text(values.get("riskControlRequirement"), "风控要求", 10_000) or None if stage == "POLICY_MANAGER" else None,
                    _text(values.get("claimScope"), "认领范围", 500) or None if stage == "POLICY_MANAGER" else None,
                    _text(values.get("adjustedPriority"), "调整优先级", 16) or None,
                    _datetime_value(values.get("adjustedCompleteAt"), "调整完成时间"),
                    actor[0], actor[1], stage, now,
                ),
            )
            priority = _text(values.get("adjustedPriority"), "调整优先级", 16).upper()
            if priority and priority not in PRIORITIES:
                raise ValueError("调整优先级不支持")
            cursor.execute(
                f"""
                UPDATE {self._table(TASK_TABLE)}
                SET status=%s, {reviewed_column}=%s,
                    resume_review_stage=%s,
                    priority=COALESCE(%s, priority), expected_complete_at=COALESCE(%s, expected_complete_at),
                    closed_at=%s, updated_by_id=%s, updated_by_name=%s,
                    version_no=version_no+1, updated_at=%s
                WHERE id=%s
                """,
                (next_status, now, stage if result == "RETURNED" else None, priority or None, _datetime_value(values.get("adjustedCompleteAt"), "调整完成时间"), now if next_status == "REJECTED" else None, actor[0], actor[1], now, task_id),
            )
            self._log(cursor, task_id=task_id, action="REVIEW", actor=actor, from_status=expected_status, to_status=next_status, note=comment or result, detail={"stage": stage, "result": result})
            connection.commit()
            return {"id": task_id, "status": next_status}
        except ValueError:
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement review failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放审核提交失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def claim_task(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_CLAIM, "当前账号没有投放任务认领权限")
        actor = _actor(user)
        planned_at = _datetime_value(values.get("plannedCompleteAt"), "计划完成时间", required=True)
        note = _text(values.get("note"), "认领备注", 1000)
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "CLAIMABLE":
                raise ValueError("该任务当前不可认领")
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)}
                    SET status='IN_PROGRESS', current_assignee_id=%s, current_assignee_name=%s,
                        claimed_at=%s, expected_complete_at=%s, updated_by_id=%s,
                        updated_by_name=%s, version_no=version_no+1, updated_at=%s
                    WHERE id=%s""",
                (actor[0], actor[1], now, planned_at, actor[0], actor[1], now, task_id),
            )
            self._log(cursor, task_id=task_id, action="CLAIM", actor=actor, from_status="CLAIMABLE", to_status="IN_PROGRESS", note=note or "认领任务", detail={"plannedCompleteAt": planned_at})
            connection.commit()
            return {"id": task_id, "status": "IN_PROGRESS", "assigneeName": actor[1]}
        except ValueError:
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement claim failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放任务认领失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def register_execution(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_EXECUTE, "当前账号没有投放结果登记权限")
        actor = _actor(user)
        result = _text(values.get("result"), "投放结果", 16, required=True).upper()
        if result not in {"SUCCESS", "FAILED"}:
            raise ValueError("投放结果不支持")
        policy_id = _text(values.get("externalPolicyId"), "外部政策ID", 128, required=result == "SUCCESS")
        if policy_id and not CODE_RE.fullmatch(policy_id):
            raise ValueError("外部政策ID格式不合法")
        failure_type = _text(values.get("failureType"), "失败类型", 64, required=result == "FAILED")
        failure_reason = _text(values.get("failureReason"), "失败原因", 10_000, required=result == "FAILED")
        actual_at = _datetime_value(values.get("actualPlacementAt"), "实际投放时间", required=result == "SUCCESS")
        effective_start = _datetime_value(values.get("effectiveStartAt"), "政策生效时间", required=result == "SUCCESS")
        long_term = result == "SUCCESS" and _bool(values.get("longTerm"))
        effective_end = _datetime_value(
            values.get("effectiveEndAt"), "政策失效时间",
            required=result == "SUCCESS" and not long_term,
        )
        if long_term:
            effective_end = None
        if effective_start and effective_end and effective_end <= effective_start:
            raise ValueError("政策失效时间必须晚于生效时间")
        loss_threshold_min, loss_threshold_max = _loss_thresholds(
            values, required=result == "SUCCESS",
        )
        retry_required = _bool(values.get("retryRequired"))
        next_handle_at = _datetime_value(values.get("nextHandleAt"), "下次处理时间", required=result == "FAILED" and retry_required)
        include_cabins = _text(values.get("includeCabins"), "包含舱位", 500)
        exclude_cabins = _text(values.get("excludeCabins"), "排除舱位", 500)
        included_list = list(dict.fromkeys(
            item.strip().upper()
            for item in include_cabins.replace("，", ",").split(",")
            if item.strip()
        ))
        excluded_list = list(dict.fromkeys(
            item.strip().upper()
            for item in exclude_cabins.replace("，", ",").split(",")
            if item.strip()
        ))
        overlap = sorted(set(included_list) & set(excluded_list))
        if overlap:
            raise ValueError(f"实际包含舱位和排除舱位不能重复：{','.join(overlap)}")
        execution = {
            "external_policy_id": policy_id or None,
            "external_policy_name": _text(values.get("externalPolicyName"), "外部政策名称", 200) or None,
            "actual_placement_at": actual_at,
            "effective_start_at": effective_start,
            "effective_end_at": effective_end,
            "platform_code": _code(values.get("platformCode"), "平台编码") or None,
            "platform_name": _text(values.get("platformName"), "平台名称", 100) or None,
            "site_code": _code(values.get("siteCode"), "站点编码") or None,
            "site_name": _text(values.get("siteName"), "站点名称", 150) or None,
            "airline_code": _code(values.get("airlineCode"), "航司").upper() or None,
            "departure_code": _code(values.get("departureCode"), "出发地").upper() or None,
            "arrival_code": _code(values.get("arrivalCode"), "到达地").upper() or None,
            "route_text": None,
            "segment_type": _segment_type(values.get("segmentType"), "实际航段类型"),
            "flight_nos": _text(values.get("flightNos"), "航班号", 500) or None,
            "include_cabins": ",".join(included_list) or None,
            "exclude_cabins": ",".join(excluded_list) or None,
            "product_type": _text(values.get("productType"), "产品类型", 150) or None,
            "order_source": _order_source(values.get("orderSource"), "实际订单来源"),
            "loss_threshold_min": loss_threshold_min,
            "loss_threshold_max": loss_threshold_max,
            "long_term_flag": 1 if long_term else 0,
            "placement_channel": _text(values.get("placementChannel"), "投放渠道", 100) or None,
            "proof_url": _text(values.get("proofUrl"), "投放凭证", 500) or None,
            "execution_note": _text(values.get("executionNote"), "执行说明", 10_000) or None,
        }
        next_status = "MONITORING" if result == "SUCCESS" else "IN_PROGRESS" if retry_required else "FAILED"
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "IN_PROGRESS":
                raise ValueError("只有执行中的任务可以登记投放结果")
            if int(task.get("current_assignee_id") or 0) != actor[0] and actor[2] != "ADMIN":
                raise PermissionError("只能由任务认领人或管理员登记投放结果")
            cursor.execute(f"SELECT COALESCE(MAX(attempt_no),0)+1 FROM {self._table(EXECUTION_TABLE)} WHERE task_id=%s", (task_id,))
            attempt = int(cursor.fetchone()[0])
            cursor.execute(
                f"""
                INSERT INTO {self._table(EXECUTION_TABLE)} (
                    task_id, attempt_no, execution_result, external_policy_id,
                    external_policy_name, actual_placement_at, effective_start_at,
                    effective_end_at, platform_code, platform_name, site_code,
                    site_name, airline_code, departure_code, arrival_code, route_text,
                    segment_type, flight_nos, include_cabins, exclude_cabins,
                    product_type, order_source, loss_threshold_min, loss_threshold_max,
                    long_term_flag, placement_channel, proof_url,
                    execution_note, failure_type, failure_reason, retry_required,
                    next_handle_at, operator_id, operator_name, created_at
                ) VALUES ({','.join(['%s'] * 35)})
                """,
                (
                    task_id, attempt, result, policy_id or None,
                    execution["external_policy_name"],
                    actual_at, effective_start, effective_end,
                    execution["platform_code"] or task.get("platform_code"),
                    execution["platform_name"] or task.get("platform_name"),
                    execution["site_code"] or task.get("site_code"),
                    execution["site_name"] or task.get("site_name"),
                    execution["airline_code"] or task.get("airline_code"),
                    execution["departure_code"] or task.get("departure_code"),
                    execution["arrival_code"] or task.get("arrival_code"),
                    None,
                    execution["segment_type"] or task.get("segment_type"),
                    execution["flight_nos"] or task.get("flight_nos"),
                    execution["include_cabins"] or task.get("include_cabins"),
                    execution["exclude_cabins"] or task.get("exclude_cabins"),
                    execution["product_type"] or task.get("product_type"),
                    execution["order_source"] or task.get("order_source"),
                    execution["loss_threshold_min"] if execution["loss_threshold_min"] is not None else task.get("loss_threshold_min"),
                    execution["loss_threshold_max"] if execution["loss_threshold_max"] is not None else task.get("loss_threshold_max"),
                    execution["long_term_flag"],
                    execution["placement_channel"],
                    execution["proof_url"],
                    execution["execution_note"],
                    failure_type or None,
                    failure_reason or None, retry_required,
                    next_handle_at,
                    actor[0], actor[1], now,
                ),
            )
            execution_id = int(cursor.lastrowid)
            monitor_rule = None
            if result == "SUCCESS":
                resolved_execution = {
                    **execution,
                    "platform_code": execution["platform_code"] or task.get("platform_code"),
                    "platform_name": execution["platform_name"] or task.get("platform_name"),
                    "site_code": execution["site_code"] or task.get("site_code"),
                    "site_name": execution["site_name"] or task.get("site_name"),
                    "airline_code": execution["airline_code"] or task.get("airline_code"),
                    "departure_code": execution["departure_code"] or task.get("departure_code"),
                    "arrival_code": execution["arrival_code"] or task.get("arrival_code"),
                    "route_text": None,
                    "segment_type": execution["segment_type"] or task.get("segment_type"),
                    "flight_nos": execution["flight_nos"] or task.get("flight_nos"),
                    "include_cabins": execution["include_cabins"] or task.get("include_cabins"),
                    "exclude_cabins": execution["exclude_cabins"] or task.get("exclude_cabins"),
                    "product_type": execution["product_type"] or task.get("product_type"),
                    "order_source": execution["order_source"] or task.get("order_source"),
                    "loss_threshold_min": execution["loss_threshold_min"] if execution["loss_threshold_min"] is not None else task.get("loss_threshold_min"),
                    "loss_threshold_max": execution["loss_threshold_max"] if execution["loss_threshold_max"] is not None else task.get("loss_threshold_max"),
                    "long_term_flag": execution["long_term_flag"],
                }
                monitor_rule = self.monitor_rule_compiler.sync_smart_placement(
                    cursor=cursor,
                    database=self.source.database,
                    task=task,
                    execution_id=execution_id,
                    attempt_no=attempt,
                    execution=resolved_execution,
                    actor=actor,
                    now=now,
                )
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)}
                    SET status=%s, monitoring_started_at=%s, closed_at=%s,
                        updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                (next_status, now if next_status == "MONITORING" else None, now if next_status == "FAILED" else None, actor[0], actor[1], now, task_id),
            )
            self._log(cursor, task_id=task_id, action="EXECUTE", actor=actor, from_status="IN_PROGRESS", to_status=next_status, note=_text(values.get("executionNote"), "执行说明", 1000) or failure_reason or result, detail={"executionId": execution_id, "result": result, "externalPolicyId": policy_id, "monitorRule": monitor_rule})
            connection.commit()
            return {"id": execution_id, "taskId": task_id, "status": next_status, "monitorRule": monitor_rule}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except MonitoringUnavailable as error:
            if connection is not None: connection.rollback()
            raise SmartPlacementUnavailable(str(error)) from error
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement execution register failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("投放结果登记失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_orders(
        self, *, user: dict[str, Any], start_date: str = "", end_date: str = "", attention_status: str = "",
        platform: str = "", airline: str = "", owner: str = "", keyword: str = "",
        page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        first = _date_value(start_date, "开始日期") or _business_now().date()
        last = _date_value(end_date, "结束日期") or first
        if last < first or (last - first).days > 366:
            raise ValueError("订单查询日期范围不合法或超过366天")
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        visibility, visibility_params = self._order_visibility_condition(user)
        where = ["m.matched_at >= %s", "m.matched_at < %s", visibility]
        params: list[Any] = [datetime.combine(first, time.min), datetime.combine(last + timedelta(days=1), time.min), *visibility_params]
        if attention_status:
            where.append("m.attention_status=%s"); params.append(_text(attention_status, "关注状态", 20))
        if platform:
            where.append("m.platform_name=%s"); params.append(_text(platform, "平台", 100))
        if airline:
            where.append("m.airline_code=%s"); params.append(_code(airline, "航司"))
        if owner:
            where.append("m.attention_owner_name=%s"); params.append(_text(owner, "负责人", 100))
        if keyword:
            token = f"%{_text(keyword, '搜索词', 128)}%"
            where.append("(m.ota_order_no LIKE %s OR m.external_policy_id LIKE %s OR m.route_text LIKE %s)")
            params.extend([token, token, token])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT COUNT(1) AS order_count,
                           COUNT(DISTINCT CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN m.ota_order_no END) AS primary_order_count,
                           SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.ticket_count,m.ticket_count) END) AS ticket_count,
                           SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.segment_count,m.segment_count) END) AS segment_count,
                           SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.estimated_profit_cny,m.estimated_profit_cny) END) AS estimated_profit,
                           SUM(CASE WHEN attention_status IN ('PENDING','ESCALATED') THEN 1 ELSE 0 END) AS pending_count,
                           COUNT(DISTINCT external_policy_id) AS active_policy_count,
                           SUM(CASE WHEN o.outcome_status='TICKETED' AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) AS ticketed_order_count,
                           SUM(CASE WHEN o.smart_participated=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) AS smart_participated_count,
                           SUM(CASE WHEN o.smart_succeeded=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) AS smart_succeeded_count,
                           SUM(CASE WHEN o.smart_used=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) AS smart_used_count,
                           SUM(CASE WHEN o.data_freshness_status='STALE' THEN 1 ELSE 0 END) AS stale_count,
                           SUM(CASE WHEN o.data_freshness_status='MISSING' OR o.match_id IS NULL THEN 1 ELSE 0 END) AS waiting_sync_count
                    FROM {self._table(MATCH_TABLE)} m
                    LEFT JOIN {self._table(OUTCOME_TABLE)} o ON o.match_id=m.id
                    LEFT JOIN {self._table(ATTRIBUTION_TABLE)} a ON a.match_id=m.id
                    WHERE {condition}""",
                tuple(params),
            )
            summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
            participated = int(summary.get("smartParticipatedCount") or 0)
            succeeded = int(summary.get("smartSucceededCount") or 0)
            ticketed = int(summary.get("ticketedOrderCount") or 0)
            summary["smartParticipationRate"] = round(participated / ticketed, 6) if ticketed else None
            summary["smartSuccessRate"] = round(succeeded / participated, 6) if participated else None
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(MATCH_TABLE)} m WHERE {condition}", tuple(params))
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"""SELECT m.*,
                           o.outcome_status,o.data_freshness_status,o.source_table outcome_source_table,
                           o.source_updated_at outcome_source_updated_at,o.last_checked_at outcome_last_checked_at,
                           o.ticket_no current_ticket_no,o.passenger_name current_passenger_name,
                           o.ticket_time current_ticket_time,o.ticket_count current_ticket_count,
                           o.segment_count current_segment_count,o.estimated_profit_cny current_estimated_profit_cny,
                           o.order_status current_order_status,o.issue_status current_issue_status,
                           o.smart_confirm,o.smart_participated,o.smart_succeeded,o.smart_used,
                           a.attribution_type,a.primary_match_id,a.matched_policy_count,a.attribution_note
                    FROM {self._table(MATCH_TABLE)} m
                    LEFT JOIN {self._table(OUTCOME_TABLE)} o ON o.match_id=m.id
                    LEFT JOIN {self._table(ATTRIBUTION_TABLE)} a ON a.match_id=m.id
                    WHERE {condition}
                    ORDER BY CASE m.attention_status WHEN 'ESCALATED' THEN 0 WHEN 'PENDING' THEN 1 WHEN 'IN_PROGRESS' THEN 2 ELSE 3 END,
                             m.matched_at DESC, m.id DESC LIMIT %s OFFSET %s""",
                tuple([*params, page_size, (page - 1) * page_size]),
            )
            rows = [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
            return {"available": True, "error": "", "period": {"startDate": first.isoformat(), "endDate": last.isoformat()}, "summary": summary, "rows": rows, "total": total, "page": page, "pageSize": page_size}
        except Exception as error:
            LOGGER.exception("Smart placement order list failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("智能投放收单查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_attention(self, user: dict[str, Any], match_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_ORDER_ATTENTION, "当前账号没有收单关注处理权限")
        actor = _actor(user)
        status = _text(values.get("status"), "关注状态", 20, required=True).upper()
        if status not in ATTENTION_STATUSES:
            raise ValueError("关注状态不支持")
        resolution_code = _text(values.get("resolutionCode"), "处理结果", 64, required=status in {"COMPLETED", "NO_ACTION"})
        note = _text(values.get("resolutionNote"), "处理说明", 10_000, required=status == "NO_ACTION")
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            visibility, visibility_params = self._order_visibility_condition(user)
            cursor.execute(
                f"SELECT m.* FROM {self._table(MATCH_TABLE)} m WHERE m.id=%s AND {visibility} FOR UPDATE",
                tuple([match_id, *visibility_params]),
            )
            match = _dict_row(cursor, cursor.fetchone())
            if not match:
                raise ValueError("匹配订单不存在")
            old_status = str(match["attention_status"])
            completed_at = now if status in {"COMPLETED", "NO_ACTION"} else None
            cursor.execute(
                f"""UPDATE {self._table(MATCH_TABLE)}
                    SET attention_status=%s, attention_owner_id=COALESCE(attention_owner_id,%s),
                        attention_owner_name=COALESCE(attention_owner_name,%s),
                        first_response_at=COALESCE(first_response_at,%s), completed_at=%s,
                        resolution_code=%s, resolution_note=%s, updated_at=%s WHERE id=%s""",
                (status, actor[0], actor[1], now, completed_at, resolution_code or None, note or None, now, match_id),
            )
            self._log(cursor, task_id=int(match["task_id"]), match_id=match_id, action="ATTENTION", actor=actor, from_status=old_status, to_status=status, note=note or resolution_code or "开始关注")
            connection.commit()
            return {"id": match_id, "status": status, "ownerName": match.get("attention_owner_name") or actor[1]}
        except ValueError:
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement attention update failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放表尚未创建，请先执行smart-placement-schema.sql") from error
            raise SmartPlacementUnavailable("订单关注状态更新失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def _effect_summary(self, cursor, task_id: int) -> dict[str, Any]:
        cursor.execute(
            f"""SELECT COUNT(1) raw_match_count,
                       COUNT(DISTINCT CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN m.ota_order_no END) attributed_order_count,
                       SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.ticket_count,m.ticket_count) END) ticket_count,
                       SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.segment_count,m.segment_count) END) segment_count,
                       SUM(CASE WHEN COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN COALESCE(o.estimated_profit_cny,m.estimated_profit_cny) END) estimated_profit_cny,
                       SUM(CASE WHEN o.outcome_status='TICKETED' AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) ticketed_order_count,
                       SUM(CASE WHEN o.smart_participated=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) smart_participated_count,
                       SUM(CASE WHEN o.smart_succeeded=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) smart_succeeded_count,
                       SUM(CASE WHEN o.smart_used=1 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY' THEN 1 ELSE 0 END) smart_used_count,
                       SUM(CASE WHEN m.attention_status IN ('COMPLETED','NO_ACTION') THEN 1 ELSE 0 END) handled_count,
                       SUM(CASE WHEN o.data_freshness_status='STALE' THEN 1 ELSE 0 END) stale_count,
                       SUM(CASE WHEN o.data_freshness_status='MISSING' OR o.match_id IS NULL THEN 1 ELSE 0 END) waiting_sync_count,
                       MIN(m.matched_at) first_matched_at,MAX(m.matched_at) last_matched_at
                FROM {self._table(MATCH_TABLE)} m
                LEFT JOIN {self._table(OUTCOME_TABLE)} o ON o.match_id=m.id
                LEFT JOIN {self._table(ATTRIBUTION_TABLE)} a ON a.match_id=m.id
                WHERE m.task_id=%s""",
            (task_id,),
        )
        summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
        ticketed = int(summary.get("ticketedOrderCount") or 0)
        participated = int(summary.get("smartParticipatedCount") or 0)
        succeeded = int(summary.get("smartSucceededCount") or 0)
        raw_matches = int(summary.get("rawMatchCount") or 0)
        handled = int(summary.get("handledCount") or 0)
        summary["smartParticipationRate"] = round(participated / ticketed, 6) if ticketed else None
        summary["smartSuccessRate"] = round(succeeded / participated, 6) if participated else None
        summary["attentionCompletionRate"] = round(handled / raw_matches, 6) if raw_matches else None
        return summary

    def effect_summary(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            visibility, params = self._visibility_condition(user)
            cursor.execute(
                f"SELECT t.id FROM {self._table(TASK_TABLE)} t WHERE t.id=%s AND t.is_deleted=0 AND {visibility}",
                tuple([task_id, *params]),
            )
            if not cursor.fetchone():
                raise ValueError("投放任务不存在或无权查看")
            return {"taskId": task_id, "summary": self._effect_summary(cursor, task_id)}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            LOGGER.exception("Smart placement effect summary failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放闭环表尚未创建，请执行smart-placement-lifecycle-notification-v2.sql") from error
            raise SmartPlacementUnavailable("政策效果查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def stop_monitoring(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_STOP, "当前账号没有停止投放监控权限")
        reason = _text(values.get("reason"), "停止原因", 1000, required=True)
        actor = _actor(user); current = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "MONITORING":
                raise ValueError("只有监控中的投放任务可以停止")
            cursor.execute(
                f"""UPDATE {self._table(MONITOR_RULE_TABLE)}
                    SET status='DISABLED',updated_by_id=%s,updated_by_name=%s,updated_at=%s
                    WHERE source_parent_id=%s AND source_business_type='SMART_PLACEMENT_EXECUTION'
                      AND status IN ('ACTIVE','SCHEDULED','PAUSED')""",
                (actor[0], actor[1], current, task_id),
            )
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET status='ENDED',closed_at=%s,
                    updated_by_id=%s,updated_by_name=%s,version_no=version_no+1,updated_at=%s
                    WHERE id=%s""",
                (current, actor[0], actor[1], current, task_id),
            )
            self._log(cursor,task_id=task_id,action="STOP_MONITORING",actor=actor,from_status="MONITORING",to_status="ENDED",note=reason)
            connection.commit()
            return {"id": task_id, "status": "ENDED"}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement stop monitoring failed")
            raise SmartPlacementUnavailable("停止投放监控失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def create_effect_review(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_permission(user, PERMISSION_EFFECT_REVIEW, "当前账号没有政策效果复盘权限")
        result = _text(values.get("result"), "复盘结果", 32, required=True).upper()
        if result not in {"CONTINUE", "ADJUST", "STOP", "COMPLETED"}:
            raise ValueError("复盘结果不支持")
        conclusion = _text(values.get("conclusion"), "复盘结论", 10_000, required=True)
        next_action = _text(values.get("nextAction"), "下一步动作", 10_000)
        actor = _actor(user); current = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] not in {"MONITORING", "ENDED"}:
                raise ValueError("只有监控中或已结束的任务可以登记效果复盘")
            snapshot = self._effect_summary(cursor, task_id)
            cursor.execute(
                f"""INSERT INTO {self._table(EFFECT_REVIEW_TABLE)} (
                    task_id,review_result,review_conclusion,next_action,reviewer_id,
                    reviewer_name,metric_snapshot_json,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (task_id,result,conclusion,next_action or None,actor[0],actor[1],json.dumps(snapshot,ensure_ascii=False,default=_json_value),current),
            )
            review_id = int(cursor.lastrowid)
            next_status = str(task["status"])
            if result in {"STOP", "COMPLETED"} and next_status == "MONITORING":
                cursor.execute(
                    f"""UPDATE {self._table(MONITOR_RULE_TABLE)} SET status='DISABLED',
                        updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE source_parent_id=%s AND source_business_type='SMART_PLACEMENT_EXECUTION'
                          AND status IN ('ACTIVE','SCHEDULED','PAUSED')""",
                    (actor[0], actor[1], current, task_id),
                )
                next_status = "ENDED"
                cursor.execute(
                    f"""UPDATE {self._table(TASK_TABLE)} SET status='ENDED',closed_at=%s,
                        updated_by_id=%s,updated_by_name=%s,version_no=version_no+1,updated_at=%s WHERE id=%s""",
                    (current, actor[0], actor[1], current, task_id),
                )
            elif result == "ADJUST":
                cursor.execute(
                    f"""UPDATE {self._table(MONITOR_RULE_TABLE)} SET status='DISABLED',
                        updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE source_parent_id=%s AND source_business_type='SMART_PLACEMENT_EXECUTION'
                          AND status IN ('ACTIVE','SCHEDULED','PAUSED')""",
                    (actor[0], actor[1], current, task_id),
                )
                next_status = "DRAFT"
                cursor.execute(
                    f"""UPDATE {self._table(TASK_TABLE)} SET status='DRAFT',closed_at=NULL,
                        submitted_at=NULL,resume_review_stage='POLICY_MANAGER',
                        updated_by_id=%s,updated_by_name=%s,version_no=version_no+1,updated_at=%s WHERE id=%s""",
                    (actor[0], actor[1], current, task_id),
                )
            self._log(cursor,task_id=task_id,action="EFFECT_REVIEW",actor=actor,from_status=task["status"],to_status=next_status,note=conclusion,detail={"result": result, "reviewId": review_id})
            connection.commit()
            return {"id": review_id, "taskId": task_id, "result": result, "taskStatus": next_status, "metricSnapshot": snapshot}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Smart placement effect review failed")
            if _is_missing_table(error):
                raise SmartPlacementUnavailable("智能投放闭环表尚未创建，请执行smart-placement-lifecycle-notification-v2.sql") from error
            raise SmartPlacementUnavailable("政策效果复盘保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
