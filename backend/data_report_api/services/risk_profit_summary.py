from __future__ import annotations

import logging
import json
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from .data_source import DataSource, data_mode, is_live_mode
from .profit_overview import _number, _period


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, ...], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()

RISK_FILTER_FIELDS = {
    "platform": "ota_cname",
    "site": "ota_site_cname",
    "department": "org_cname",
    "airline": "marketing_airline",
    "supplier": "supplier_cname",
}
PROFIT_STATUS_CONDITIONS = {
    "all": "",
    "loss": "estimated_profit_cny < 0",
    "profit": "estimated_profit_cny > 0",
    "zero": "estimated_profit_cny = 0",
}
OPTION_LIMIT = 50


def normalize_risk_filters(values: dict[str, Any] | None) -> dict[str, str]:
    values = values or {}
    if set(values) - (set(RISK_FILTER_FIELDS) | {"profitStatus"}):
        raise ValueError("不支持的核对筛选条件")
    result = {}
    for key in RISK_FILTER_FIELDS:
        value = values.get(key) or ""
        if not isinstance(value, str) or len(value) > 150:
            raise ValueError("筛选名称必须为不超过150字符的文本")
        result[key] = value if value.strip() else ""
    status = values.get("profitStatus") or "all"
    if not isinstance(status, str) or status not in PROFIT_STATUS_CONDITIONS:
        raise ValueError("盈亏状态只支持全部、亏损、盈利或零利润")
    result["profitStatus"] = status
    return result


def _filter_conditions(filters: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    clauses = []
    parameters = []
    for key, field in RISK_FILTER_FIELDS.items():
        if filters.get(key):
            clauses.append(f"AND {field} = %s")
            parameters.append(filters[key])
    condition = PROFIT_STATUS_CONDITIONS[filters.get("profitStatus", "all")]
    if condition:
        clauses.append(f"AND {condition}")
    return "\n".join(clauses), tuple(parameters)


HIVE_RISK_PROFIT_DEFINITIONS = (
    {
        "key": "issue",
        "label": "出票",
        "table": "dwd_order_issue_profit_reconcile_year",
        "timeField": "business_date",
    },
    {
        "key": "refund",
        "label": "退票",
        "table": "dwd_order_refund_profit_reconcile_year",
        "timeField": "business_date",
    },
    {
        "key": "change",
        "label": "改签",
        "table": "dwd_order_change_profit_reconcile_year",
        "timeField": "stat_date",
    },
)

RISK_PROFIT_DEFINITIONS = {
    "hive": HIVE_RISK_PROFIT_DEFINITIONS,
    "mysql": tuple(
        {**definition, "table": definition["table"].replace("dwd_", "bi_", 1)}
        for definition in HIVE_RISK_PROFIT_DEFINITIONS
    ),
}


class RiskProfitSummaryService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def _source(self) -> DataSource:
        source_config = dict(self.config)
        mode = data_mode(source_config)
        # Reconciliation never fabricates mock figures; unconfigured MySQL is unavailable.
        source_config["DATA_MODE"] = mode if is_live_mode(mode) else "mysql"
        return DataSource(source_config)

    def _cached(self, cache_key: tuple[str, ...]) -> dict[str, Any] | None:
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result
        return None

    def _store(self, cache_key: tuple[str, ...], result: dict[str, Any]) -> None:
        if not result["available"] or int(self.config.get("PROFIT_CACHE_TTL", 300)) <= 0:
            return
        with _CACHE_LOCK:
            if cache_key not in _CACHE and len(_CACHE) >= 256:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))

    def summary(
        self, start_value: str | None, end_value: str | None, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        start, end = _period(start_value, end_value)
        filters = normalize_risk_filters(filters)
        source = self._source()
        cache_key = ("summary", source.cache_key, start.isoformat(), end.isoformat(), json.dumps(filters, sort_keys=True))
        cached = self._cached(cache_key)
        if cached:
            return cached

        metrics = self._fetch(source, start, end, filters)
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        start_month = start.strftime("%Y-%m")
        end_month = end.strftime("%Y-%m")
        result = {
            "source": source.label,
            "generatedAt": generated_at,
            "cacheHit": False,
            "available": all(item["available"] for item in metrics),
            "filters": filters,
            "period": {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "monthLabel": start_month if start_month == end_month else f"{start_month} 至 {end_month}",
            },
            "metrics": metrics,
            "notes": [
                f"本区域独立读取 {source.engine_label} 利润核对表，不参与原经营总览四项利润合计。",
                "票数为 sum(ticket_num)，利润为 sum(estimated_profit_cny)。",
                "维度名称精确匹配；盈亏按源记录预估利润正负筛选，不是按汇总后的净利润判断。",
            ],
        }
        self._store(cache_key, result)
        return result

    def _fetch(self, source: DataSource, start: date, end: date, filters: dict[str, str]) -> list[dict[str, Any]]:
        definitions = RISK_PROFIT_DEFINITIONS[source.mode]
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Unable to connect to %s for risk profit summary", source.engine_label)
            return [self._failed_metric(item, f"{source.engine_label}连接失败") for item in definitions]

        end_exclusive = end + timedelta(days=1)
        results: list[dict[str, Any]] = []
        try:
            for definition in definitions:
                cursor = connection.cursor()
                try:
                    sql = self._query(source, definition, start, end_exclusive, filters)
                    parameters = _filter_conditions(filters)[1]
                    cursor.execute(sql, parameters) if parameters else cursor.execute(sql)
                    row = cursor.fetchone()
                    results.append(
                        {
                            **definition,
                            "ticketCount": int(row[0] or 0),
                            "estimatedProfit": _number(row[1] or 0),
                            "available": True,
                            "error": None,
                        }
                    )
                except Exception:
                    LOGGER.exception("%s risk profit query failed: %s", source.engine_label, definition["key"])
                    results.append(self._failed_metric(definition, "该业务查询失败"))
                finally:
                    cursor.close()
        finally:
            connection.close()
        return results

    @staticmethod
    def _query(
        source: DataSource, definition: dict[str, str], start: date, end_exclusive: date,
        filters: dict[str, str] | None = None,
    ) -> str:
        conditions, _ = _filter_conditions(filters or {})
        return f"""
            SELECT coalesce(sum(ticket_num), 0), coalesce(sum(estimated_profit_cny), 0)
            FROM {source.database}.{definition['table']}
            WHERE {definition['timeField']} >= '{start.isoformat()}'
              AND {definition['timeField']} < '{end_exclusive.isoformat()}'
              {conditions}
        """

    def filter_options(
        self, start_value: str | None, end_value: str | None, field: str | None,
        search: str | None = None, filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if field not in RISK_FILTER_FIELDS:
            raise ValueError("不支持的核对筛选字段")
        search = search or ""
        if len(search) > 150:
            raise ValueError("筛选搜索不能超过150字符")
        start, end = _period(start_value, end_value)
        filters = normalize_risk_filters(filters)
        filters[field] = ""  # Other active dimensions constrain suggestions, not the edited dimension itself.
        source = self._source()
        cache_key = (
            "options", source.cache_key, start.isoformat(), end.isoformat(), field, search,
            json.dumps(filters, sort_keys=True),
        )
        cached = self._cached(cache_key)
        if cached:
            return cached
        result = {"source": source.label, "field": field, "options": [], "truncated": False,
                  "available": True, "errors": [], "cacheHit": False}
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Unable to connect to %s for risk filter options", source.engine_label)
            result.update(available=False, errors=[f"{source.engine_label}连接失败"])
            return result
        options = set()
        try:
            for definition in RISK_PROFIT_DEFINITIONS[source.mode]:
                cursor = connection.cursor()
                try:
                    sql, parameters = self._options_query(source, definition, start, end + timedelta(days=1), field, search, filters)
                    cursor.execute(sql, parameters) if parameters else cursor.execute(sql)
                    rows = cursor.fetchall()
                    result["truncated"] = result["truncated"] or len(rows) > OPTION_LIMIT
                    options.update(str(row[0]) for row in rows if row[0] is not None and str(row[0]).strip())
                except Exception:
                    LOGGER.exception("Risk filter options query failed: %s", definition["key"])
                    result["available"] = False
                    result["errors"].append(f"{definition['label']}筛选项查询失败")
                finally:
                    cursor.close()
        finally:
            connection.close()
        result["truncated"] = result["truncated"] or len(options) > OPTION_LIMIT
        result["options"] = sorted(options)[:OPTION_LIMIT]
        self._store(cache_key, result)
        return result

    @staticmethod
    def _options_query(
        source: DataSource, definition: dict[str, str], start: date, end_exclusive: date,
        field: str, search: str, filters: dict[str, str],
    ) -> tuple[str, tuple[str, ...]]:
        column = RISK_FILTER_FIELDS[field]
        conditions, parameters = _filter_conditions(filters)
        search_condition = ""
        if search:
            # DB-API binding prevents SQL injection; escape LIKE wildcards for literal prefix search.
            pattern = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            search_condition = f"AND {column} LIKE %s"
            parameters += (pattern,)
        return f"""
            SELECT DISTINCT {column}
            FROM {source.database}.{definition['table']}
            WHERE {definition['timeField']} >= '{start.isoformat()}'
              AND {definition['timeField']} < '{end_exclusive.isoformat()}'
              AND {column} IS NOT NULL AND {column} <> ''
              {conditions}
              {search_condition}
            ORDER BY {column}
            LIMIT {OPTION_LIMIT + 1}
        """, parameters

    @staticmethod
    def _failed_metric(definition: dict[str, str], error: str) -> dict[str, Any]:
        return {
            **definition,
            "ticketCount": None,
            "estimatedProfit": None,
            "available": False,
            "error": error,
        }
