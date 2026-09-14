from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .data_source import DataSource, data_mode, is_live_mode
from .profit_overview import _period


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


FIELD_DEFINITIONS = (
    ("order_id", "订单关联键", "订单下钻与跨表关联", "number"),
    ("ota_cname", "销售平台", "平台利润归因", "string"),
    ("ota_site_cname", "销售站点", "站点利润归因", "string"),
    ("marketing_airline", "航司", "航司利润归因", "string"),
    ("issue_supplier_cname", "出票供应商", "采购与供应归因", "string"),
    ("org_cname", "所属组织", "部门利润归因", "string"),
    ("issue_operator", "出票员", "出票人员分析", "string"),
    ("policy_operator", "政策员", "政策人员分析", "string"),
    ("issue_ticketing_office_no", "PCC / Office", "出票配置归因", "string"),
    ("route", "出发到达城市", "航线利润归因", "route"),
    ("issue_way_desc", "出票方式", "自动与人工出票分析", "string"),
    ("issue_profit", "出票利润", "利润指标计算", "number"),
)


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _base_where(start: date, end: date, time_field: str) -> str:
    start_at = f"{start.isoformat()} 00:00:00"
    end_at = f"{(end + timedelta(days=1)).isoformat()} 00:00:00"
    return f"""
        order_status = 'TICKETED'
        AND issue_status = 'I_UPDATED'
        AND refund_flag <> 3
        AND refund_issue_flag = '否'
        AND {time_field} >= '{start_at}'
        AND {time_field} < '{end_at}'
    """


def _completeness_expression(field: str, kind: str) -> str:
    if kind == "number":
        return f"sum(case when {field} is not null then 1 else 0 end)"
    if kind == "route":
        return "sum(case when dep_city is not null and trim(dep_city) <> '' and arr_city is not null and trim(arr_city) <> '' then 1 else 0 end)"
    return f"sum(case when {field} is not null and trim({field}) <> '' then 1 else 0 end)"


class IssueProfitAnalysisService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def analysis(self, start_value: str | None, end_value: str | None) -> dict[str, Any]:
        start, end = _period(start_value, end_value)
        mode = data_mode(self.config)
        cache_key = (mode, start.isoformat(), end.isoformat())
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result

        source = DataSource(self.config) if is_live_mode(mode) else None
        result = self._fetch_live(source, start, end) if source else self._mock_result(start, end)
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _fetch_live(self, source: DataSource, start: date, end: date) -> dict[str, Any]:
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            connection = source.connect()
            try:
                summary, completeness = self._summary_and_completeness(connection, source, start, end)
                trend = self._trend(connection, source, start, end)
                dimensions = self._dimensions(connection, source, start, end)
            finally:
                connection.close()
        except Exception:
            LOGGER.exception("Issue profit analysis query failed")
            return {
                "mode": "live", "source": source.label, "available": False,
                "error": "出票利润分析查询失败", "generatedAt": generated_at, "cacheHit": False,
                "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
                "summary": None, "trend": {"granularity": "day", "items": []},
                "dimensions": {}, "completeness": [], "coverageSummary": None,
            }

        coverage_values = [item["rate"] for item in completeness]
        coverage_summary = {
            "averageRate": round(sum(coverage_values) / len(coverage_values), 1) if coverage_values else 0,
            "ready": sum(item["state"] == "ready" for item in completeness),
            "partial": sum(item["state"] == "partial" for item in completeness),
            "missing": sum(item["state"] == "missing" for item in completeness),
            "total": len(completeness),
        }
        return {
            "mode": "live", "source": f"{source.label}.{source.table('issue').table}", "available": True,
            "error": None, "generatedAt": generated_at, "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": summary, "trend": trend, "dimensions": dimensions,
            "completeness": completeness, "coverageSummary": coverage_summary,
        }

    @staticmethod
    def _summary_and_completeness(connection, source: DataSource, start: date, end: date):
        spec = source.table("issue")
        completeness_sql = ",\n".join(
            f"{_completeness_expression(field, kind)} as complete_{index}"
            for index, (field, _label, _usage, kind) in enumerate(FIELD_DEFINITIONS)
        )
        sql = f"""
            SELECT
                count(1) as issue_count,
                coalesce(sum(segment_num), 0) as segment_count,
                coalesce(sum(issue_profit), 0) as issue_profit,
                sum(case when issue_profit < 0 then 1 else 0 end) as loss_count,
                sum(case when issue_profit > 0 then 1 else 0 end) as profit_count,
                sum(case when issue_profit = 0 then 1 else 0 end) as zero_profit_count,
                sum(case when issue_profit is not null then 1 else 0 end) as profit_value_count,
                {completeness_sql}
            FROM {source.qualified_table('issue')}
            WHERE {_base_where(start, end, spec.time_field)}
        """
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
        finally:
            cursor.close()
        total = int(row[0] or 0)
        profit = _number(row[2] or 0)
        loss_count = int(row[3] or 0)
        summary = {
            "issueCount": total,
            "segmentCount": int(row[1] or 0),
            "profit": profit,
            "averageProfit": _number(float(profit) / total) if total else 0,
            "lossCount": loss_count,
            "lossRate": round(loss_count / total * 100, 2) if total else 0,
            "profitCount": int(row[4] or 0),
            "zeroProfitCount": int(row[5] or 0),
        }
        completeness = []
        for index, (field, label, usage, _kind) in enumerate(FIELD_DEFINITIONS):
            non_null = int(row[7 + index] or 0)
            rate = round(non_null / total * 100, 1) if total else 0
            state = "ready" if rate >= 95 else "partial" if rate >= 80 else "missing"
            completeness.append(
                {"field": field, "label": label, "usage": usage, "nonNullCount": non_null, "totalCount": total, "rate": rate, "state": state}
            )
        return summary, completeness

    @staticmethod
    def _trend(connection, source: DataSource, start: date, end: date) -> dict[str, Any]:
        spec = source.table("issue")
        granularity = "month" if (end - start).days > 62 else "day"
        expression = source.period_expression(spec.time_field, granularity)
        sql = f"""
            SELECT {expression} as period_value, count(1), coalesce(sum(issue_profit), 0)
            FROM {source.qualified_table('issue')}
            WHERE {_base_where(start, end, spec.time_field)}
            GROUP BY {expression}
            ORDER BY period_value
        """
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return {
            "granularity": granularity,
            "items": [{"period": str(row[0]), "count": int(row[1] or 0), "profit": _number(row[2] or 0)} for row in rows if row[0]],
        }

    @staticmethod
    def _dimensions(connection, source: DataSource, start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        spec = source.table("issue")
        dimension_fields = {
            "platform": "ota_cname",
            "airline": "marketing_airline",
            "supplier": "issue_supplier_cname",
            "organization": "org_cname",
        }
        result: dict[str, list[dict[str, Any]]] = {"platform": [], "airline": [], "supplier": [], "organization": []}
        for key, field in dimension_fields.items():
            normalized = f"case when {field} is null or trim({field}) = '' then '未填写' else {field} end"
            sql = f"""
                SELECT {normalized} as dim_value, count(1), coalesce(sum(issue_profit), 0)
                FROM {source.qualified_table('issue')}
                WHERE {_base_where(start, end, spec.time_field)}
                GROUP BY {normalized}
            """
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
                rows = cursor.fetchall()
            finally:
                cursor.close()
            items = [{"name": str(row[0]), "count": int(row[1] or 0), "profit": _number(row[2] or 0)} for row in rows]
            result[key] = sorted(items, key=lambda item: abs(float(item["profit"] or 0)), reverse=True)[:8]
        return result

    @staticmethod
    def _mock_result(start: date, end: date) -> dict[str, Any]:
        fields = []
        rates = (100, 98.6, 97.8, 99.2, 96.4, 94.8, 91.5, 87.2, 82.6, 99.7, 95.4, 100)
        total = 128600
        for definition, rate in zip(FIELD_DEFINITIONS, rates):
            field, label, usage, _kind = definition
            state = "ready" if rate >= 95 else "partial" if rate >= 80 else "missing"
            fields.append({"field": field, "label": label, "usage": usage, "nonNullCount": round(total * rate / 100), "totalCount": total, "rate": rate, "state": state})
        dimensions = {
            key: [{"name": f"演示{index + 1}", "count": 18000 - index * 1300, "profit": (-1 if index % 3 == 0 else 1) * (820000 - index * 76000)} for index in range(6)]
            for key in ("platform", "airline", "supplier", "organization")
        }
        return {
            "mode": "mock", "source": "演示数据", "available": True, "error": None,
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": {"issueCount": total, "segmentCount": 196500, "profit": -2220857.63, "averageProfit": -17.27, "lossCount": 48120, "lossRate": 37.42, "profitCount": 75200, "zeroProfitCount": 5280},
            "trend": {"granularity": "month", "items": [{"period": f"2026-{month:02d}", "count": 13000 + month * 600, "profit": -480000 + month * 72000} for month in range(1, 10)]},
            "dimensions": dimensions, "completeness": fields,
            "coverageSummary": {"averageRate": round(sum(rates) / len(rates), 1), "ready": sum(rate >= 95 for rate in rates), "partial": sum(80 <= rate < 95 for rate in rates), "missing": sum(rate < 80 for rate in rates), "total": len(rates)},
        }
