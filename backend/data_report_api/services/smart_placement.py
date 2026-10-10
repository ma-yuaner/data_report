"""Smart-placement workflow backed by the MySQL collaboration tables."""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time as monotonic_time
from copy import deepcopy
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .data_source import DataSource


LOGGER = logging.getLogger(__name__)
TASK_TABLE = "smart_placement_task"
REVIEW_TABLE = "smart_placement_review"
EXECUTION_TABLE = "smart_placement_execution"
MATCH_TABLE = "smart_placement_order_match"
LOG_TABLE = "smart_placement_operation_log"
DIMENSION_TABLE = "bi_business_profit_dimension_day"

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
CODE_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


class SmartPlacementUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _business_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


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
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
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

    order_start = _date_value(values.get("orderStartDate"), "订单开始日期")
    order_end = _date_value(values.get("orderEndDate"), "订单结束日期")
    if order_start and order_end and order_end < order_start:
        raise ValueError("订单结束日期不能早于开始日期")
    travel_start = _date_value(values.get("travelStartDate"), "起飞开始日期")
    travel_end = _date_value(values.get("travelEndDate"), "起飞结束日期")
    if travel_start and travel_end and travel_end < travel_start:
        raise ValueError("起飞结束日期不能早于开始日期")

    suggested_start = _datetime_value(
        values.get("suggestedEffectiveStart"), "建议生效时间", required=submit,
    )
    suggested_end = _datetime_value(
        values.get("suggestedEffectiveEnd"), "建议失效时间", required=submit,
    )
    if suggested_start and suggested_end and suggested_end <= suggested_start:
        raise ValueError("建议失效时间必须晚于生效时间")

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
        "route_text": _text(values.get("routeText"), "航程", 300) or None,
        "journey_type": _text(values.get("journeyType"), "航程类型", 32) or None,
        "flight_nos": _text(values.get("flightNos"), "航班号", 500) or None,
        "include_cabins": ",".join(included_list) or None,
        "exclude_cabins": ",".join(excluded_list) or None,
        "product_type": _text(values.get("productType"), "产品类型", 150) or None,
        "order_start_date": order_start,
        "order_end_date": order_end,
        "travel_start_date": travel_start,
        "travel_end_date": travel_end,
        "placement_method": _text(values.get("placementMethod"), "建议投放方式", 300, required=True),
        "adjustment_value": _decimal(values.get("adjustmentValue"), "建议调整值"),
        "adjustment_unit": _text(values.get("adjustmentUnit"), "调整单位", 32) or None,
        "suggested_effective_start": suggested_start,
        "suggested_effective_end": suggested_end,
        "historical_ticket_count": _integer(values.get("historicalTicketCount"), "历史票数"),
        "historical_segment_count": _integer(values.get("historicalSegmentCount"), "历史航段数"),
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
    role = "ADMIN" if bool(user.get("is_admin") or user.get("isAdmin")) else "USER"
    return user_id, name[:100], role


def _require_manager(user: dict[str, Any]) -> None:
    if not bool(user.get("is_admin") or user.get("isAdmin")):
        raise PermissionError("当前首版仅管理员可执行经理审核")


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
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part[:1].upper() + part[1:] for part in tail)
    return {camel(key): _json_value(value) for key, value in row.items()}


class SmartPlacementService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        self.source = source or DataSource({**config, "DATA_MODE": "mysql"})

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

    def list_tasks(
        self, *, status: str = "", keyword: str = "", platform: str = "",
        airline: str = "", owner: str = "", scope: str = "", actor_id: int = 0,
        page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        if status and status not in TASK_STATUSES:
            raise ValueError("任务状态不支持")
        if scope not in {"", "review", "claim", "mine"}:
            raise ValueError("任务分组不支持")
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100))
        where = ["is_deleted=0"]
        params: list[Any] = []
        if status:
            where.append("status=%s"); params.append(status)
        if keyword:
            token = f"%{_text(keyword, '搜索词', 100)}%"
            where.append("(task_no LIKE %s OR opportunity_name LIKE %s OR route_text LIKE %s)")
            params.extend([token, token, token])
        if platform:
            where.append("platform_name=%s"); params.append(_text(platform, "平台", 100))
        if airline:
            where.append("airline_code=%s"); params.append(_code(airline, "航司"))
        if owner:
            where.append("current_assignee_name=%s"); params.append(_text(owner, "负责人", 100))
        if scope == "review":
            where.append("status IN ('PENDING_DATA_REVIEW','PENDING_POLICY_REVIEW')")
        elif scope == "claim":
            where.append("status='CLAIMABLE'")
        elif scope == "mine":
            if not actor_id:
                raise ValueError("登录用户信息不完整")
            where.append("(current_assignee_id=%s OR created_by_id=%s)")
            params.extend([actor_id, actor_id])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(f"SELECT status, COUNT(1) AS amount FROM {self._table(TASK_TABLE)} WHERE is_deleted=0 GROUP BY status")
            status_rows = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(TASK_TABLE)} WHERE {condition}", tuple(params))
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"""
                SELECT id, task_no, opportunity_name, opportunity_source,
                       platform_name, site_name, airline_code, departure_code,
                       arrival_code, route_text, include_cabins, exclude_cabins,
                       product_type, placement_method, estimated_month_ticket_count,
                       estimated_month_profit_cny, priority, status,
                       current_assignee_id, current_assignee_name, expected_complete_at,
                       created_by_id, created_by_name,
                       created_at, updated_at
                FROM {self._table(TASK_TABLE)}
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
    def task_detail(self, task_id: int) -> dict[str, Any]:
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(TASK_TABLE)} WHERE id=%s AND is_deleted=0", (task_id,))
            task = _dict_row(cursor, cursor.fetchone())
            if not task:
                raise ValueError("投放任务不存在")
            cursor.execute(f"SELECT * FROM {self._table(REVIEW_TABLE)} WHERE task_id=%s ORDER BY id", (task_id,))
            reviews = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(EXECUTION_TABLE)} WHERE task_id=%s ORDER BY attempt_no DESC", (task_id,))
            executions = _dict_rows(cursor, list(cursor.fetchall()))
            cursor.execute(f"SELECT * FROM {self._table(LOG_TABLE)} WHERE task_id=%s ORDER BY id DESC LIMIT 200", (task_id,))
            logs = _dict_rows(cursor, list(cursor.fetchall()))
            return {
                "task": _public_row(task),
                "reviews": [_public_row(row) for row in reviews],
                "executions": [_public_row(row) for row in executions],
                "logs": [_public_row(row) for row in logs],
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
        actor = _actor(user)
        submit = _bool(values.get("submit"))
        fields = _task_fields(values, submit=submit)
        next_status = "PENDING_DATA_REVIEW" if submit else "DRAFT"
        now = _now()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            task = self._task_for_update(cursor, task_id)
            if task["status"] != "DRAFT":
                raise ValueError("只有草稿或退回修改的任务可以编辑")
            if int(task.get("created_by_id") or 0) != actor[0] and actor[2] != "ADMIN":
                raise PermissionError("只能由创建人或管理员编辑该任务")
            assignments = ",".join(f"{name}=%s" for name in fields)
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)} SET {assignments}, status=%s,
                        submitted_at=%s, updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                tuple([*fields.values(), next_status, now if submit else task.get("submitted_at"), actor[0], actor[1], now, task_id]),
            )
            self._log(
                cursor, task_id=task_id, action="RESUBMIT" if submit else "UPDATE",
                actor=actor, from_status="DRAFT", to_status=next_status,
                note="修改后重新提交数据经理审核" if submit else "更新草稿",
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

    def review_task(self, user: dict[str, Any], task_id: int, values: dict[str, Any]) -> dict[str, Any]:
        _require_manager(user)
        actor = _actor(user)
        stage = _text(values.get("stage"), "审核环节", 32, required=True).upper()
        if stage not in REVIEW_STAGES:
            raise ValueError("审核环节不支持")
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
                    priority=COALESCE(%s, priority), expected_complete_at=COALESCE(%s, expected_complete_at),
                    closed_at=%s, updated_by_id=%s, updated_by_name=%s,
                    version_no=version_no+1, updated_at=%s
                WHERE id=%s
                """,
                (next_status, now, priority or None, _datetime_value(values.get("adjustedCompleteAt"), "调整完成时间"), now if next_status == "REJECTED" else None, actor[0], actor[1], now, task_id),
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
        effective_end = _datetime_value(values.get("effectiveEndAt"), "政策失效时间", required=result == "SUCCESS")
        if effective_start and effective_end and effective_end <= effective_start:
            raise ValueError("政策失效时间必须晚于生效时间")
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
                    flight_nos, include_cabins, exclude_cabins, product_type,
                    adjustment_value, adjustment_unit, placement_channel, proof_url,
                    execution_note, failure_type, failure_reason, retry_required,
                    next_handle_at, operator_id, operator_name, created_at
                ) VALUES ({','.join(['%s'] * 32)})
                """,
                (
                    task_id, attempt, result, policy_id or None,
                    _text(values.get("externalPolicyName"), "外部政策名称", 200) or None,
                    actual_at, effective_start, effective_end,
                    _code(values.get("platformCode"), "平台编码") or task.get("platform_code"),
                    _text(values.get("platformName"), "平台名称", 100) or task.get("platform_name"),
                    _code(values.get("siteCode"), "站点编码") or task.get("site_code"),
                    _text(values.get("siteName"), "站点名称", 150) or task.get("site_name"),
                    _code(values.get("airlineCode"), "航司").upper() or task.get("airline_code"),
                    _code(values.get("departureCode"), "出发地").upper() or task.get("departure_code"),
                    _code(values.get("arrivalCode"), "到达地").upper() or task.get("arrival_code"),
                    _text(values.get("routeText"), "航程", 300) or task.get("route_text"),
                    _text(values.get("flightNos"), "航班号", 500) or task.get("flight_nos"),
                    ",".join(included_list) or task.get("include_cabins"),
                    ",".join(excluded_list) or task.get("exclude_cabins"),
                    _text(values.get("productType"), "产品类型", 150) or task.get("product_type"),
                    _decimal(values.get("adjustmentValue"), "实际调整值"),
                    _text(values.get("adjustmentUnit"), "调整单位", 32) or task.get("adjustment_unit"),
                    _text(values.get("placementChannel"), "投放渠道", 100) or None,
                    _text(values.get("proofUrl"), "投放凭证", 500) or None,
                    _text(values.get("executionNote"), "执行说明", 10_000) or None,
                    failure_type or None,
                    failure_reason or None, retry_required,
                    next_handle_at,
                    actor[0], actor[1], now,
                ),
            )
            execution_id = int(cursor.lastrowid)
            cursor.execute(
                f"""UPDATE {self._table(TASK_TABLE)}
                    SET status=%s, monitoring_started_at=%s, closed_at=%s,
                        updated_by_id=%s, updated_by_name=%s,
                        version_no=version_no+1, updated_at=%s WHERE id=%s""",
                (next_status, now if next_status == "MONITORING" else None, now if next_status == "FAILED" else None, actor[0], actor[1], now, task_id),
            )
            self._log(cursor, task_id=task_id, action="EXECUTE", actor=actor, from_status="IN_PROGRESS", to_status=next_status, note=_text(values.get("executionNote"), "执行说明", 1000) or failure_reason or result, detail={"executionId": execution_id, "result": result, "externalPolicyId": policy_id})
            connection.commit()
            return {"id": execution_id, "taskId": task_id, "status": next_status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
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
        self, *, start_date: str = "", end_date: str = "", attention_status: str = "",
        platform: str = "", airline: str = "", owner: str = "", keyword: str = "",
        page: int = 1, page_size: int = 30,
    ) -> dict[str, Any]:
        first = _date_value(start_date, "开始日期") or _business_now().date()
        last = _date_value(end_date, "结束日期") or first
        if last < first or (last - first).days > 366:
            raise ValueError("订单查询日期范围不合法或超过366天")
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        where = ["matched_at >= %s", "matched_at < %s"]
        params: list[Any] = [datetime.combine(first, time.min), datetime.combine(last + timedelta(days=1), time.min)]
        if attention_status:
            where.append("attention_status=%s"); params.append(_text(attention_status, "关注状态", 20))
        if platform:
            where.append("platform_name=%s"); params.append(_text(platform, "平台", 100))
        if airline:
            where.append("airline_code=%s"); params.append(_code(airline, "航司"))
        if owner:
            where.append("attention_owner_name=%s"); params.append(_text(owner, "负责人", 100))
        if keyword:
            token = f"%{_text(keyword, '搜索词', 128)}%"
            where.append("(ota_order_no LIKE %s OR external_policy_id LIKE %s OR route_text LIKE %s)")
            params.extend([token, token, token])
        condition = " AND ".join(where)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT COUNT(1) AS order_count,
                           COALESCE(SUM(ticket_count),0) AS ticket_count,
                           COALESCE(SUM(segment_count),0) AS segment_count,
                           COALESCE(SUM(estimated_profit_cny),0) AS estimated_profit,
                           SUM(CASE WHEN attention_status IN ('PENDING','ESCALATED') THEN 1 ELSE 0 END) AS pending_count,
                           COUNT(DISTINCT external_policy_id) AS active_policy_count
                    FROM {self._table(MATCH_TABLE)} WHERE {condition}""",
                tuple(params),
            )
            summary = _public_row(_dict_row(cursor, cursor.fetchone()) or {})
            cursor.execute(f"SELECT COUNT(1) FROM {self._table(MATCH_TABLE)} WHERE {condition}", tuple(params))
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"""SELECT * FROM {self._table(MATCH_TABLE)} WHERE {condition}
                    ORDER BY CASE attention_status WHEN 'ESCALATED' THEN 0 WHEN 'PENDING' THEN 1 WHEN 'IN_PROGRESS' THEN 2 ELSE 3 END,
                             matched_at DESC, id DESC LIMIT %s OFFSET %s""",
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
            cursor.execute(f"SELECT * FROM {self._table(MATCH_TABLE)} WHERE id=%s FOR UPDATE", (match_id,))
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
