from __future__ import annotations

import logging
import re
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .profit_overview import _period


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


BUSINESS_DEFINITIONS = {
    "refund": {
        "name": "退票",
        "table": "dwd_refund_issue_year",
        "timeField": "apply_datetime",
        "profitField": "refund_profit",
        "countLabel": "退票数",
        "segmentField": None,
        "segmentLabel": None,
        "condition": "business_type_desc in ('正常退票（退票）', '售后退票作废（退票）') and supplier_refund_operator is not null and trim(supplier_refund_operator) <> ''",
        "conditionLabel": "正常退票或售后退票作废，且供应退款操作人不为空",
    },
    "change": {
        "name": "改签",
        "table": "dwd_change_issue_year",
        "timeField": "change_issue_time",
        "profitField": "change_profit",
        "countLabel": "改签数",
        "segmentField": None,
        "segmentLabel": None,
        "condition": "1 = 1",
        "conditionLabel": "按改签出票时间统计全部记录",
    },
    "ancillary": {
        "name": "增值",
        "table": "dwd_aux_pur_year",
        "timeField": "create_time",
        "profitField": "profit",
        "countLabel": "增值数",
        "segmentField": "flight_num",
        "segmentLabel": "增值航段数",
        "condition": "aux_status = '已购买'",
        "conditionLabel": "增值状态为已购买",
    },
}


def _number(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class BusinessProfitAnalysisService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def analysis(self, business_type: str, start_value: str | None, end_value: str | None) -> dict[str, Any]:
        if business_type not in BUSINESS_DEFINITIONS:
            raise ValueError("不支持的业务类型")
        start, end = _period(start_value, end_value)
        mode = str(self.config.get("DATA_MODE", "mock")).lower()
        cache_key = (mode, business_type, start.isoformat(), end.isoformat())
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result

        definition = BUSINESS_DEFINITIONS[business_type]
        result = self._fetch_hive(business_type, definition, start, end) if mode == "hive" else self._mock_result(business_type, definition, start, end)
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _connect(self):
        host = str(self.config.get("HIVE_HOST", "")).strip()
        user = str(self.config.get("HIVE_USER", "")).strip()
        database = str(self.config.get("HIVE_DATABASE", "lywz")).strip()
        if not host or not user:
            raise RuntimeError("Hive连接配置不完整")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            raise RuntimeError("Hive库名配置不合法")
        from pyhive import hive

        return hive.connect(
            host=host,
            port=int(self.config.get("HIVE_PORT", 10000)),
            database=database,
            username=user,
            password=str(self.config.get("HIVE_PASSWORD", "")) or None,
            auth=str(self.config.get("HIVE_AUTH", "NONE")),
        )

    def _fetch_hive(self, business_type: str, definition: dict[str, Any], start: date, end: date) -> dict[str, Any]:
        database = str(self.config.get("HIVE_DATABASE", "lywz")).strip()
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        granularity = "month" if (end - start).days > 62 else "day"
        period_expression = f"substr({definition['timeField']}, 1, {'7' if granularity == 'month' else '10'})"
        segment_expression = f"coalesce(sum({definition['segmentField']}), 0)" if definition["segmentField"] else "cast(null as bigint)"
        start_at = f"{start.isoformat()} 00:00:00"
        end_at = f"{(end + timedelta(days=1)).isoformat()} 00:00:00"
        sql = f"""
            SELECT
                {period_expression} as period_value,
                count(1) as business_count,
                {segment_expression} as segment_count,
                coalesce(sum({definition['profitField']}), 0) as profit,
                sum(case when {definition['profitField']} < 0 then 1 else 0 end) as negative_count
            FROM {database}.{definition['table']}
            WHERE {definition['timeField']} >= '{start_at}'
              AND {definition['timeField']} < '{end_at}'
              AND {definition['condition']}
            GROUP BY {period_expression}
            ORDER BY period_value
        """
        try:
            connection = self._connect()
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
            finally:
                connection.close()
        except Exception:
            LOGGER.exception("Business profit query failed: %s", business_type)
            return self._unavailable(business_type, definition, database, start, end, generated_at)

        items = [
            {
                "period": str(row[0]), "count": int(row[1] or 0),
                "segmentCount": None if definition["segmentField"] is None else int(row[2] or 0),
                "profit": _number(row[3]), "negativeCount": int(row[4] or 0),
            }
            for row in rows if row[0]
        ]
        total_count = sum(item["count"] for item in items)
        total_segments = None if definition["segmentField"] is None else sum(int(item["segmentCount"] or 0) for item in items)
        total_profit = sum(float(item["profit"]) for item in items)
        negative_count = sum(item["negativeCount"] for item in items)
        return {
            "mode": "live", "source": f"Hive · {database}.{definition['table']}", "available": True,
            "error": None, "generatedAt": generated_at, "cacheHit": False,
            "business": self._business_meta(business_type, definition),
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": {
                "count": total_count, "segmentCount": total_segments, "profit": _number(total_profit),
                "averageProfit": _number(total_profit / total_count) if total_count else 0,
                "negativeCount": negative_count,
                "negativeRate": round(negative_count / total_count * 100, 2) if total_count else 0,
            },
            "trend": {"granularity": granularity, "items": items},
        }

    @staticmethod
    def _business_meta(business_type: str, definition: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": business_type, "name": definition["name"], "countLabel": definition["countLabel"],
            "segmentLabel": definition["segmentLabel"], "timeField": definition["timeField"],
            "profitField": definition["profitField"], "conditionLabel": definition["conditionLabel"],
        }

    @classmethod
    def _unavailable(cls, business_type, definition, database, start, end, generated_at):
        return {
            "mode": "live", "source": f"Hive · {database}.{definition['table']}", "available": False,
            "error": f"{definition['name']}利润查询失败", "generatedAt": generated_at, "cacheHit": False,
            "business": cls._business_meta(business_type, definition),
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": None, "trend": {"granularity": "day", "items": []},
        }

    @classmethod
    def _mock_result(cls, business_type, definition, start, end):
        base = {"refund": (6515, None, 2177422.42), "change": (3320, None, 231450.8), "ancillary": (45223, 50307, 2213368.03)}[business_type]
        items = []
        for month in range(1, 10):
            items.append({"period": f"2026-{month:02d}", "count": round(base[0] / 9), "segmentCount": None if base[1] is None else round(base[1] / 9), "profit": round(base[2] / 9, 2), "negativeCount": round(base[0] / 45)})
        return {
            "mode": "mock", "source": "演示数据", "available": True, "error": None,
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "cacheHit": False,
            "business": cls._business_meta(business_type, definition),
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": {"count": base[0], "segmentCount": base[1], "profit": base[2], "averageProfit": round(base[2] / base[0], 2), "negativeCount": round(base[0] / 5), "negativeRate": 20},
            "trend": {"granularity": "month", "items": items},
        }
