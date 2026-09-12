from __future__ import annotations

import logging
import re
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


METRICS = (
    {
        "key": "issue",
        "label": "出票",
        "countLabel": "出票数",
        "segmentLabel": "航段数",
        "timeField": "issue_ticket_time",
        "sql": """
            SELECT count(1), coalesce(sum(segment_num), 0), coalesce(sum(issue_profit), 0)
            FROM {database}.dwd_order_issue_wide_year
            WHERE order_status = 'TICKETED'
              AND issue_status = 'I_UPDATED'
              AND refund_flag <> 3
              AND refund_issue_flag = '否'
              AND issue_ticket_time >= '{start_at}'
              AND issue_ticket_time < '{end_at}'
        """,
    },
    {
        "key": "refund",
        "label": "退票",
        "countLabel": "退票数",
        "segmentLabel": None,
        "timeField": "apply_datetime",
        "sql": """
            SELECT count(1), cast(null as bigint), coalesce(sum(refund_profit), 0)
            FROM {database}.dwd_refund_issue_year
            WHERE supplier_refund_operator is not null
              AND trim(supplier_refund_operator) <> ''
              AND apply_datetime >= '{start_at}'
              AND apply_datetime < '{end_at}'
        """,
    },
    {
        "key": "change",
        "label": "改签",
        "countLabel": "改签数",
        "segmentLabel": None,
        "timeField": "change_issue_time",
        "sql": """
            SELECT count(1), cast(null as bigint), coalesce(sum(change_profit), 0)
            FROM {database}.dwd_change_issue_year
            WHERE change_issue_time >= '{start_at}'
              AND change_issue_time < '{end_at}'
        """,
    },
    {
        "key": "ancillary",
        "label": "增值",
        "countLabel": "增值数",
        "segmentLabel": "增值航段数",
        "timeField": "create_time",
        "sql": """
            SELECT count(1), coalesce(sum(flight_num), 0), coalesce(sum(profit), 0)
            FROM {database}.dwd_aux_pur_year
            WHERE aux_status = '已购买'
              AND create_time >= '{start_at}'
              AND create_time < '{end_at}'
        """,
    },
)


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _period(start_value: str | None, end_value: str | None) -> tuple[date, date]:
    today = datetime.now().astimezone().date()
    try:
        start = date.fromisoformat(start_value) if start_value else today.replace(day=1)
        end = date.fromisoformat(end_value) if end_value else today
    except ValueError as error:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if (end - start).days > 366:
        raise ValueError("单次查询范围不能超过 366 天")
    return start, end


class ProfitOverviewService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def overview(self, start_value: str | None, end_value: str | None) -> dict[str, Any]:
        start, end = _period(start_value, end_value)
        mode = str(self.config.get("DATA_MODE", "mock")).lower()
        cache_key = (mode, start.isoformat(), end.isoformat())
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)), 0)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result

        metrics = self._fetch_hive(start, end) if mode == "hive" else self._mock_metrics()
        complete = all(item["available"] for item in metrics)
        total = sum(float(item["profit"]) for item in metrics) if complete else None
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        result = {
            "mode": "live" if mode == "hive" else "mock",
            "source": f"Hive · {self.config.get('HIVE_DATABASE', 'lywz')}" if mode == "hive" else "演示数据",
            "generatedAt": generated_at,
            "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "status": {
                "label": "Hive实时汇总" if mode == "hive" else "演示数据",
                "freshness": f"查询时间 {generated_at[11:19]}",
                "metricState": "业务估算口径",
            },
            "totalProfit": {"value": _number(total), "available": complete},
            "metrics": metrics,
            "notes": [
                "总预估利润 = 出票利润 + 退票利润 + 改签利润 + 增值利润。",
                "金额单位暂按元展示，当前属于业务估算利润，不代表财务已结算利润。",
                "四类业务使用各自发生时间过滤；结束日期按当天闭区间处理。",
                "退票仅统计供应退款操作人不为空的记录。",
            ],
        }
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _fetch_hive(self, start: date, end: date) -> list[dict[str, Any]]:
        host = str(self.config.get("HIVE_HOST", "")).strip()
        user = str(self.config.get("HIVE_USER", "")).strip()
        database = str(self.config.get("HIVE_DATABASE", "lywz")).strip()
        if not host or not user:
            return [self._failed_metric(metric, "Hive连接配置不完整") for metric in METRICS]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            return [self._failed_metric(metric, "Hive库名配置不合法") for metric in METRICS]

        try:
            from pyhive import hive

            connection = hive.connect(
                host=host,
                port=int(self.config.get("HIVE_PORT", 10000)),
                database=database,
                username=user,
                password=str(self.config.get("HIVE_PASSWORD", "")) or None,
                auth=str(self.config.get("HIVE_AUTH", "NONE")),
            )
        except Exception:
            LOGGER.exception("Unable to connect to Hive")
            return [self._failed_metric(metric, "Hive连接失败") for metric in METRICS]

        start_at = f"{start.isoformat()} 00:00:00"
        end_at = f"{(end + timedelta(days=1)).isoformat()} 00:00:00"
        results: list[dict[str, Any]] = []
        try:
            for metric in METRICS:
                cursor = connection.cursor()
                try:
                    cursor.execute(metric["sql"].format(database=database, start_at=start_at, end_at=end_at))
                    row = cursor.fetchone()
                    results.append(
                        {
                            "key": metric["key"],
                            "label": metric["label"],
                            "countLabel": metric["countLabel"],
                            "count": int(row[0] or 0),
                            "segmentLabel": metric["segmentLabel"],
                            "segmentCount": _number(row[1]),
                            "profit": _number(row[2] or 0),
                            "timeField": metric["timeField"],
                            "available": True,
                            "error": None,
                        }
                    )
                except Exception:
                    LOGGER.exception("Hive profit query failed: %s", metric["key"])
                    results.append(self._failed_metric(metric, "该业务查询失败"))
                finally:
                    cursor.close()
        finally:
            connection.close()
        return results

    @staticmethod
    def _failed_metric(metric: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "key": metric["key"],
            "label": metric["label"],
            "countLabel": metric["countLabel"],
            "count": None,
            "segmentLabel": metric["segmentLabel"],
            "segmentCount": None,
            "profit": None,
            "timeField": metric["timeField"],
            "available": False,
            "error": error,
        }

    @staticmethod
    def _mock_metrics() -> list[dict[str, Any]]:
        values = (("issue", 18420, 22680, 386420.50), ("refund", 1260, None, 58430.20), ("change", 835, None, 31680.00), ("ancillary", 3210, 3476, 76520.80))
        lookup = {item[0]: item[1:] for item in values}
        return [
            {
                "key": metric["key"], "label": metric["label"], "countLabel": metric["countLabel"],
                "count": lookup[metric["key"]][0], "segmentLabel": metric["segmentLabel"],
                "segmentCount": lookup[metric["key"]][1], "profit": lookup[metric["key"]][2],
                "timeField": metric["timeField"], "available": True, "error": None,
            }
            for metric in METRICS
        ]
