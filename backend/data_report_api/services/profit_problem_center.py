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


PROBLEM_DEFINITIONS = (
    {
        "key": "issue", "name": "出票", "profitField": "issue_profit",
        "eventId": "cast(id as string)", "orderNo": "coalesce(ota_order_no, order_no, cast(order_id as string))",
        "ticketNo": "issue_ticket_no", "platform": "ota_cname", "supplier": "issue_supplier_cname",
        "airline": "marketing_airline", "operator": "issue_operator",
        "condition": "order_status = 'TICKETED' and issue_status = 'I_UPDATED' and refund_flag <> 3 and refund_issue_flag = '否'",
    },
    {
        "key": "refund", "name": "退票", "profitField": "refund_profit",
        "eventId": "cast(refund_issue_id as string)", "orderNo": "coalesce(ota_order_no, cast(order_id as string))",
        "ticketNo": "refund_ticket_no", "platform": "ota_cname", "supplier": "supplier_cname",
        "airline": "marketing_airline", "operator": "supplier_refund_operator",
        "condition": "business_type_desc in ('正常退票（退票）', '售后退票作废（退票）') and supplier_refund_operator is not null and trim(supplier_refund_operator) <> ''",
    },
    {
        "key": "change", "name": "改签", "profitField": "change_profit",
        "eventId": "cast(change_issue_id as string)", "orderNo": "coalesce(ota_order_no, cast(order_id as string))",
        "ticketNo": "issue_ticket_no", "platform": "ota_cname", "supplier": "supplier_cname",
        "airline": "cast(null as string)", "operator": "change_operator", "condition": "1 = 1",
    },
    {
        "key": "ancillary", "name": "增值", "profitField": "profit",
        "eventId": "cast(pur_id as string)", "orderNo": "coalesce(ota_order_no, cast(order_id as string))",
        "ticketNo": "cast(null as string)", "platform": "ota_cname", "supplier": "supplier_cname",
        "airline": "cast(null as string)", "operator": "operator_name", "condition": "aux_status = '已购买'",
    },
)


def _number(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class ProfitProblemCenterService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def problems(self, start_value: str | None, end_value: str | None) -> dict[str, Any]:
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
        start_at = f"{start.isoformat()} 00:00:00"
        end_at = f"{(end + timedelta(days=1)).isoformat()} 00:00:00"
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Problem center %s connection failed", source.engine_label)
            return self._connection_failed(source, start, end, generated_at)

        businesses: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        try:
            for definition in PROBLEM_DEFINITIONS:
                sql = self._query(definition, source, start_at, end_at)
                cursor = connection.cursor()
                try:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    total_count = int(rows[0][9] or 0) if rows else 0
                    loss_amount = abs(float(rows[0][10] or 0)) if rows else 0
                    businesses.append({
                        "key": definition["key"], "name": definition["name"],
                        "negativeCount": total_count, "lossAmount": _number(loss_amount),
                        "available": True, "error": None,
                    })
                    for row in rows:
                        items.append({
                            "businessKey": definition["key"], "businessName": definition["name"],
                            "eventId": str(row[0] or ""), "orderNo": str(row[1] or ""),
                            "ticketNo": str(row[2] or ""), "platform": str(row[3] or "未标记"),
                            "supplier": str(row[4] or "未标记"), "airline": str(row[5] or "未标记"),
                            "operator": str(row[6] or "未标记"), "occurredAt": str(row[7] or ""),
                            "profit": _number(row[8]),
                        })
                except Exception:
                    LOGGER.exception("Profit problem query failed: %s", definition["key"])
                    businesses.append({
                        "key": definition["key"], "name": definition["name"],
                        "negativeCount": None, "lossAmount": None,
                        "available": False, "error": "负利润查询失败",
                    })
                finally:
                    cursor.close()
        finally:
            connection.close()

        complete = all(item["available"] for item in businesses)
        total_loss = sum(float(item["lossAmount"] or 0) for item in businesses if item["available"])
        for item in businesses:
            item["lossShare"] = round(float(item["lossAmount"] or 0) / total_loss * 100, 2) if complete and total_loss else 0
        items.sort(key=lambda item: float(item["profit"]))
        summary = None if not complete else {
            "negativeCount": sum(int(item["negativeCount"] or 0) for item in businesses),
            "lossAmount": _number(total_loss),
            "affectedBusinessCount": sum(1 for item in businesses if int(item["negativeCount"] or 0) > 0),
            "availableBusinessCount": len(businesses),
        }
        return {
            "mode": "live", "source": source.label, "available": complete,
            "generatedAt": generated_at, "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": summary, "businesses": businesses, "items": items[:20],
            "notes": [
                "当前问题中心只识别出、退、改、增业务中利润小于0的记录。",
                "负利润属于待调查经营问题，不直接等同于人员责任或财务最终损失。",
            ],
        }

    @staticmethod
    def _query(definition: dict[str, Any], source: DataSource, start_at: str, end_at: str) -> str:
        spec = source.table(definition["key"])
        expressions = {
            key: value.replace(" as string)", " as char)") if source.mode == "mysql" else value
            for key, value in definition.items()
            if isinstance(value, str)
        }
        return f"""
            SELECT event_id, order_no, ticket_no, platform, supplier, airline, operator_name,
                   occurred_at, profit_value, total_count, total_profit
            FROM (
                SELECT
                    {expressions['eventId']} as event_id,
                    {expressions['orderNo']} as order_no,
                    {expressions['ticketNo']} as ticket_no,
                    {expressions['platform']} as platform,
                    {expressions['supplier']} as supplier,
                    {expressions['airline']} as airline,
                    {expressions['operator']} as operator_name,
                    {spec.time_field} as occurred_at,
                    {definition['profitField']} as profit_value,
                    count(1) over() as total_count,
                    sum({definition['profitField']}) over() as total_profit
                FROM {source.qualified_table(definition['key'])}
                WHERE {spec.time_field} >= '{start_at}'
                  AND {spec.time_field} < '{end_at}'
                  AND {definition['condition']}
                  AND {definition['profitField']} < 0
            ) loss_records
            ORDER BY profit_value ASC
            LIMIT 20
        """

    @staticmethod
    def _connection_failed(source: DataSource, start: date, end: date, generated_at: str) -> dict[str, Any]:
        businesses = [
            {"key": item["key"], "name": item["name"], "negativeCount": None, "lossAmount": None, "lossShare": 0, "available": False, "error": f"{source.engine_label}连接失败"}
            for item in PROBLEM_DEFINITIONS
        ]
        return {
            "mode": "live", "source": source.label, "available": False,
            "generatedAt": generated_at, "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": None, "businesses": businesses, "items": [],
            "notes": [f"{source.engine_label}连接失败，未将缺失业务按0处理。"],
        }

    @staticmethod
    def _mock_result(start: date, end: date) -> dict[str, Any]:
        businesses = [
            {"key": "issue", "name": "出票", "negativeCount": 35, "lossAmount": 8620.5, "lossShare": 63.7, "available": True, "error": None},
            {"key": "refund", "name": "退票", "negativeCount": 8, "lossAmount": 2310.8, "lossShare": 17.08, "available": True, "error": None},
            {"key": "change", "name": "改签", "negativeCount": 5, "lossAmount": 1740.2, "lossShare": 12.86, "available": True, "error": None},
            {"key": "ancillary", "name": "增值", "negativeCount": 3, "lossAmount": 860.0, "lossShare": 6.36, "available": True, "error": None},
        ]
        items = [
            {"businessKey": "issue", "businessName": "出票", "eventId": "DEMO-1001", "orderNo": "DEMO-ORDER", "ticketNo": "DEMO-TICKET", "platform": "演示平台", "supplier": "演示供应商", "airline": "XX", "operator": "演示人员", "occurredAt": f"{end.isoformat()} 10:30:00", "profit": -1280.5},
        ]
        return {
            "mode": "mock", "source": "演示数据", "available": True,
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "cacheHit": False,
            "period": {"startDate": start.isoformat(), "endDate": end.isoformat()},
            "summary": {"negativeCount": 51, "lossAmount": 13531.5, "affectedBusinessCount": 4, "availableBusinessCount": 4},
            "businesses": businesses, "items": items,
            "notes": ["当前问题中心只识别业务估算利润小于0的记录。"],
        }
