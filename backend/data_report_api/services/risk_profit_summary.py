from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from .data_source import DataSource
from .profit_overview import _number, _period


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


RISK_PROFIT_DEFINITIONS = (
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


class RiskProfitSummaryService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def summary(self, start_value: str | None, end_value: str | None) -> dict[str, Any]:
        start, end = _period(start_value, end_value)
        hive_config = dict(self.config)
        hive_config["DATA_MODE"] = "hive"
        source = DataSource(hive_config)
        cache_key = (source.cache_key, start.isoformat(), end.isoformat())
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result

        metrics = self._fetch(source, start, end)
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        start_month = start.strftime("%Y-%m")
        end_month = end.strftime("%Y-%m")
        result = {
            "source": source.label,
            "generatedAt": generated_at,
            "cacheHit": False,
            "available": all(item["available"] for item in metrics),
            "period": {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "monthLabel": start_month if start_month == end_month else f"{start_month} 至 {end_month}",
            },
            "metrics": metrics,
            "notes": [
                "本区域独立读取 Hive 利润核对表，不参与原经营总览四项利润合计。",
                "票数为 sum(ticket_num)，利润为 sum(estimated_profit_cny)。",
            ],
        }
        if result["available"]:
            with _CACHE_LOCK:
                _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _fetch(self, source: DataSource, start: date, end: date) -> list[dict[str, Any]]:
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Unable to connect to Hive for risk profit summary")
            return [self._failed_metric(item, "Hive连接失败") for item in RISK_PROFIT_DEFINITIONS]

        end_exclusive = end + timedelta(days=1)
        results: list[dict[str, Any]] = []
        try:
            for definition in RISK_PROFIT_DEFINITIONS:
                cursor = connection.cursor()
                try:
                    cursor.execute(self._query(source, definition, start, end_exclusive))
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
                    LOGGER.exception("Hive risk profit query failed: %s", definition["key"])
                    results.append(self._failed_metric(definition, "该业务查询失败"))
                finally:
                    cursor.close()
        finally:
            connection.close()
        return results

    @staticmethod
    def _query(source: DataSource, definition: dict[str, str], start: date, end_exclusive: date) -> str:
        return f"""
            SELECT coalesce(sum(ticket_num), 0), coalesce(sum(estimated_profit_cny), 0)
            FROM {source.database}.{definition['table']}
            WHERE {definition['timeField']} >= '{start.isoformat()}'
              AND {definition['timeField']} < '{end_exclusive.isoformat()}'
        """

    @staticmethod
    def _failed_metric(definition: dict[str, str], error: str) -> dict[str, Any]:
        return {
            **definition,
            "ticketCount": None,
            "estimatedProfit": None,
            "available": False,
            "error": error,
        }
