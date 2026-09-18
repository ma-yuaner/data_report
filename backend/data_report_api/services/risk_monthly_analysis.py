"""Monthly comparison of existing MySQL reconciliation records, not settled P&L."""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .comprehensive_analysis import parse_period
from .data_source import DataSource

DEFINITIONS = (
    {"key": "issue", "label": "出票", "table": "bi_order_issue_profit_reconcile_year", "timeField": "business_date"},
    {"key": "change", "label": "改签", "table": "bi_order_change_profit_reconcile_year", "timeField": "stat_date"},
    {"key": "refund", "label": "退票", "table": "bi_order_refund_profit_reconcile_year", "timeField": "business_date"},
)
PROFIT_CONDITIONS = {"all": "", "loss": "AND estimated_profit_cny < 0", "profit": "AND estimated_profit_cny > 0", "zero": "AND estimated_profit_cny = 0"}


def summarize(rows: list[dict], available=True) -> dict:
    count = sum(row["rowCount"] for row in rows)
    ticket_missing = sum(row["ticketMissingCount"] for row in rows)
    profit_missing = sum(row["profitMissingCount"] for row in rows)
    tickets = [row["knownTicketCount"] for row in rows if row["knownTicketCount"] is not None]
    profits = [Decimal(row["knownProfit"]) for row in rows if row["knownProfit"] is not None]
    known_tickets = sum(tickets) if tickets else None
    known_profit = str(sum(profits, Decimal(0))) if profits else None
    return {
        "rowCount": count if available else None,
        "ticketCount": known_tickets if available and ticket_missing == 0 else None,
        "estimatedProfit": known_profit if available and profit_missing == 0 else None,
        "knownTicketCount": known_tickets if available else None,
        "knownProfit": known_profit if available else None,
        "ticketMissingCount": ticket_missing if available else 0,
        "profitMissingCount": profit_missing if available else 0,
        "status": "unavailable" if not available else "no_records" if not count else "incomplete" if ticket_missing or profit_missing else "ready",
    }


def month_periods(first: date, last: date) -> list[dict]:
    result = []
    month = first.replace(day=1)
    while month <= last:
        month_last = month.replace(day=calendar.monthrange(month.year, month.month)[1])
        result.append({"month": month.strftime("%Y-%m"), "label": f"{month.year}年{month.month}月", "isPartial": first > month or last < month_last})
        month = month_last + timedelta(days=1)
    return result


class RiskMonthlyAnalysisService:
    def __init__(self, config):
        self.source = DataSource({**config, "DATA_MODE": "mysql"})

    def analysis(self, start_value=None, end_value=None, business_type="all", profit_status="all", date_basis="reconcile"):
        first, last = parse_period(start_value, end_value)
        if business_type not in {"all", *(item["key"] for item in DEFINITIONS)}:
            raise ValueError("业务类型只支持全部、出票、改签或退票")
        if profit_status not in PROFIT_CONDITIONS:
            raise ValueError("盈亏范围只支持全部、亏损、盈利或零利润")
        if date_basis not in ("overview", "reconcile"):
            raise ValueError("不支持的月份日期口径")
        definitions = [{**item, "timeField": "stat_date" if date_basis == "reconcile" and item["key"] == "refund" else item["timeField"]} for item in DEFINITIONS if business_type == "all" or item["key"] == business_type]
        result = {
            "source": self.source.label, "available": False, "error": "", "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "filters": {"businessType": business_type, "profitStatus": profit_status, "dateBasis": date_basis},
            "businesses": [{**item, "metrics": summarize([], False)} for item in definitions],
            "summary": summarize([], False), "months": [],
            "notes": [
                "票数按SUM(ticket_num)，金额按SUM(estimated_profit_cny)，CNY预估利润，不代表财务已结算利润。",
                "当前只统计所选日期内的核对表记录，是否仅亏损及历史同步覆盖由源数据决定；默认不额外限定亏损。",
                "源NULL票数与利润明确提示；存在缺失时完整指标显示为—，仅已知部分单列，不按0补齐。",
                "无记录月份显示—，不是已证实没有业务；缺失或未同步数据不作为0元。",
                "跨月期间按真实所选日期汇总，部分月份标注范围不完整，不自动计算环比或同比。",
                "出退改票数分别列示，不合计为去重客票数；本页核对利润不再并入经营总览或综合分析利润。",
                "未接入ADM、实际结算、后返完整性与风险识别规则；不据此自动判断风险根因或责任。",
            ],
        }
        connection = cursor = None
        try:
            parts, parameters = [], []
            for item in definitions:
                field = item["timeField"]
                parts.append(f"SELECT '{item['key']}' AS business_type, SUBSTR({field},1,7) AS business_month, "
                             "COUNT(1), SUM(ticket_num), SUM(estimated_profit_cny), "
                             "SUM(CASE WHEN ticket_num IS NULL THEN 1 ELSE 0 END), "
                             "SUM(CASE WHEN estimated_profit_cny IS NULL THEN 1 ELSE 0 END) "
                             f"FROM {self.source.database}.{item['table']} WHERE {field} >= %s AND {field} < %s "
                             f"{PROFIT_CONDITIONS[profit_status]} GROUP BY SUBSTR({field},1,7)")
                parameters.extend((first.isoformat(), (last + timedelta(days=1)).isoformat()))
            connection = self.source.connect()
            cursor = connection.cursor()
            # One UNION ALL statement: same MySQL snapshot, no cross-table joins or multiplication.
            cursor.execute(" UNION ALL ".join(parts), tuple(parameters))
            rows = []
            expected_months = {item["month"] for item in month_periods(first, last)}
            for raw in cursor.fetchall():
                if raw[0] not in {item["key"] for item in definitions} or raw[1] not in expected_months:
                    raise RuntimeError("源日期不能归入标准业务月份，请检查源日期格式")
                count, ticket_missing, profit_missing = int(raw[2]), int(raw[5]), int(raw[6])
                if count <= 0 or not 0 <= ticket_missing <= count or not 0 <= profit_missing <= count:
                    raise RuntimeError("核对记录计数异常，请检查源数据")
                rows.append({"businessKey": raw[0], "month": raw[1], "rowCount": count,
                             "knownTicketCount": int(raw[3]) if raw[3] is not None else None,
                             "knownProfit": str(raw[4]) if raw[4] is not None else None,
                             "ticketMissingCount": ticket_missing, "profitMissingCount": profit_missing})
            result["summary"] = summarize(rows)
            result["businesses"] = [{**item, "metrics": summarize([row for row in rows if row["businessKey"] == item["key"]])} for item in definitions]
            for period in month_periods(first, last):
                selected = [row for row in rows if row["month"] == period["month"]]
                result["months"].append({**period, "metrics": {item["key"]: summarize([row for row in selected if row["businessKey"] == item["key"]]) for item in definitions}, "summary": summarize(selected)})
            result["available"] = True
        except Exception as error:
            logging.getLogger(__name__).exception("MySQL risk monthly reconciliation query failed")
            result["error"] = str(error) if isinstance(error, RuntimeError) else "风控月度核对查询失败，请检查MySQL连接与三张核对表字段。"
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
        return result
