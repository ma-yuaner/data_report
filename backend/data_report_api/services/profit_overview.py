from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .data_source import DataSource, TABLE_SPECS, data_mode, is_live_mode


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


METRICS = (
    {
        "key": "issue",
        "label": "出票",
        "countLabel": "出票数",
        "segmentLabel": "航段数",
        "segmentField": "segment_num",
        "profitField": "issue_profit",
        "condition": "order_status = 'TICKETED' and issue_status = 'I_UPDATED' and refund_flag <> 3 and refund_issue_flag = '否'",
    },
    {
        "key": "refund",
        "label": "退票",
        "countLabel": "退票数",
        "segmentLabel": None,
        "segmentField": None,
        "profitField": "refund_profit",
        "condition": "business_type_desc in ('正常退票（退票）', '售后退票作废（退票）') and supplier_refund_operator is not null and trim(supplier_refund_operator) <> ''",
    },
    {
        "key": "change",
        "label": "改签",
        "countLabel": "改签数",
        "segmentLabel": None,
        "segmentField": None,
        "profitField": "change_profit",
        "condition": "1 = 1",
    },
    {
        "key": "ancillary",
        "label": "增值",
        "countLabel": "增值数",
        "segmentLabel": "增值航段数",
        "segmentField": "flight_num",
        "profitField": "profit",
        "condition": "aux_status = '已购买'",
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
        start = date.fromisoformat(start_value) if start_value else today
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
        metrics = self._fetch_live(source, start, end) if source else self._mock_metrics()
        complete = all(item["available"] for item in metrics)
        total = sum(float(item["profit"]) for item in metrics) if complete else None
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        result = {
            "mode": "live" if source else "mock",
            "source": source.label if source else "演示数据",
            "generatedAt": generated_at,
            "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "status": {
                "label": f"{source.engine_label}实际数据" if source else "演示数据",
                "freshness": f"查询时间 {generated_at[11:19]}",
                "metricState": "业务估算口径",
            },
            "totalProfit": {"value": _number(total), "available": complete},
            "metrics": metrics,
            "notes": [
                "总预估利润 = 出票利润 + 退票利润 + 改签利润 + 增值利润。",
                "金额单位暂按元展示，当前属于业务估算利润，不代表财务已结算利润。",
                "四类业务使用各自发生时间过滤；结束日期按当天闭区间处理。",
                "退票仅统计正常退票、售后退票作废，且供应退款操作人不为空的记录。",
            ],
        }
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _fetch_live(self, source: DataSource, start: date, end: date) -> list[dict[str, Any]]:
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Unable to connect to %s", source.engine_label)
            return [self._failed_metric(metric, source, f"{source.engine_label}连接失败") for metric in METRICS]

        start_at = f"{start.isoformat()} 00:00:00"
        end_at = f"{(end + timedelta(days=1)).isoformat()} 00:00:00"
        results: list[dict[str, Any]] = []
        try:
            for metric in METRICS:
                cursor = connection.cursor()
                try:
                    spec = source.table(metric["key"])
                    count_expression = source.count_expression(metric["key"])
                    segment_expression = f"coalesce(sum({metric['segmentField']}), 0)" if metric["segmentField"] else "NULL"
                    sql = f"""
                        SELECT {count_expression}, {segment_expression}, coalesce(sum({metric['profitField']}), 0)
                        FROM {source.qualified_table(metric['key'])}
                        WHERE {metric['condition']}
                          AND {spec.time_field} >= '{start_at}'
                          AND {spec.time_field} < '{end_at}'
                    """
                    cursor.execute(sql)
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
                            "timeField": spec.time_field,
                            "available": True,
                            "error": None,
                        }
                    )
                except Exception:
                    LOGGER.exception("%s profit query failed: %s", source.engine_label, metric["key"])
                    results.append(self._failed_metric(metric, source, "该业务查询失败"))
                finally:
                    cursor.close()
        finally:
            connection.close()
        return results

    @staticmethod
    def _failed_metric(metric: dict[str, Any], source: DataSource, error: str) -> dict[str, Any]:
        return {
            "key": metric["key"],
            "label": metric["label"],
            "countLabel": metric["countLabel"],
            "count": None,
            "segmentLabel": metric["segmentLabel"],
            "segmentCount": None,
            "profit": None,
            "timeField": source.table(metric["key"]).time_field,
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
                "timeField": TABLE_SPECS["mysql"][metric["key"]].time_field, "available": True, "error": None,
            }
            for metric in METRICS
        ]
