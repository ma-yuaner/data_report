"""Risk-profit analysis and order drill-down from MySQL reconciliation tables."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .comprehensive_analysis import parse_period
from .data_source import DataSource


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskBusinessSpec:
    key: str
    label: str
    table: str
    time_field: str
    service_order_field: str
    verify_field: str
    operator_field: str
    reason_field: str | None = None


SPECS = {
    "issue": RiskBusinessSpec(
        key="issue",
        label="出票",
        table="bi_order_issue_profit_reconcile_year",
        time_field="business_date",
        service_order_field="order_no",
        verify_field="risk_verify_result",
        operator_field="issue_operator",
        reason_field="profit_reason_type",
    ),
    "refund": RiskBusinessSpec(
        key="refund",
        label="退票",
        table="bi_order_refund_profit_reconcile_year",
        time_field="stat_date",
        service_order_field="refund_order_no",
        verify_field="verify_result",
        operator_field="refund_operator",
    ),
    "change": RiskBusinessSpec(
        key="change",
        label="改签",
        table="bi_order_change_profit_reconcile_year",
        time_field="stat_date",
        service_order_field="change_order_no",
        verify_field="verify_result",
        operator_field="change_operator",
    ),
}

FILTER_FIELDS = {
    "platform": "ota_cname",
    "site": "ota_site_cname",
    "department": "org_cname",
    "airline": "marketing_airline",
    "supplier": "supplier_cname",
    "policy": "policy_operator",
}

GROUP_FIELDS = {
    "platform": ("平台", "ota_cname"),
    "site": ("站点", "ota_site_cname"),
    "department": ("业务部门", "org_cname"),
    "airline": ("航司", "marketing_airline"),
    "supplier": ("供应商", "supplier_cname"),
    "policy": ("政策员", "policy_operator"),
    "reason": ("盈亏原因", None),
    "verifyResult": ("核实结果", None),
}

PROFIT_CONDITIONS = {
    "all": None,
    "loss": "estimated_profit_cny < 0",
    "profit": "estimated_profit_cny > 0",
    "zero": "estimated_profit_cny = 0",
}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def normalize_filters(values: dict[str, Any] | None, spec: RiskBusinessSpec) -> dict[str, str]:
    values = values or {}
    supported = {*FILTER_FIELDS, "reason", "verifyResult", "profitStatus"}
    if set(values) - supported:
        raise ValueError("不支持的风控筛选条件")
    result: dict[str, str] = {}
    for key in (*FILTER_FIELDS, "reason", "verifyResult"):
        value = values.get(key) or ""
        if not isinstance(value, str) or len(value) > 150:
            raise ValueError("筛选值必须为不超过150字符的文本")
        result[key] = value.strip()
    if result["reason"] and not spec.reason_field:
        raise ValueError(f"{spec.label}核对表尚无标准盈亏原因字段，不能按原因筛选")
    status = values.get("profitStatus") or "all"
    if not isinstance(status, str) or status not in PROFIT_CONDITIONS:
        raise ValueError("盈亏状态只支持全部、亏损、盈利或零利润")
    result["profitStatus"] = status
    return result


def available_groups(spec: RiskBusinessSpec) -> list[dict[str, str]]:
    result = []
    for key, (label, _) in GROUP_FIELDS.items():
        if key == "reason" and not spec.reason_field:
            continue
        result.append({"key": key, "label": label})
    return result


def _group_field(spec: RiskBusinessSpec, group: str) -> str:
    if group == "reason":
        if not spec.reason_field:
            raise ValueError(f"{spec.label}核对表尚无标准盈亏原因字段")
        return spec.reason_field
    if group == "verifyResult":
        return spec.verify_field
    field = GROUP_FIELDS.get(group, (None, None))[1]
    if field is None:
        raise ValueError("不支持的分析维度")
    return field


def build_where(
    spec: RiskBusinessSpec,
    start_date: str,
    next_date: str,
    filters: dict[str, str],
) -> tuple[str, list[str]]:
    clauses = [f"{spec.time_field} >= %s", f"{spec.time_field} < %s"]
    parameters = [start_date, next_date]
    for key, field in FILTER_FIELDS.items():
        if filters[key]:
            clauses.append(f"NULLIF(TRIM({field}),'') = %s")
            parameters.append(filters[key])
    if filters["reason"]:
        clauses.append(f"NULLIF(TRIM({spec.reason_field}),'') = %s")
        parameters.append(filters["reason"])
    if filters["verifyResult"]:
        clauses.append(f"NULLIF(TRIM({spec.verify_field}),'') = %s")
        parameters.append(filters["verifyResult"])
    profit_condition = PROFIT_CONDITIONS[filters["profitStatus"]]
    if profit_condition:
        clauses.append(profit_condition)
    return " AND ".join(clauses), parameters


METRIC_SELECT = """
COUNT(1),
SUM(ticket_num),
SUM(estimated_profit_cny),
SUM(CASE WHEN ticket_num IS NULL THEN 1 ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny IS NULL THEN 1 ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny < 0 THEN ticket_num ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny < 0 THEN estimated_profit_cny ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny < 0 AND ticket_num IS NULL THEN 1 ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny > 0 THEN ticket_num ELSE 0 END),
SUM(CASE WHEN estimated_profit_cny = 0 THEN ticket_num ELSE 0 END)
""".strip()


def metric_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    row_count = int(row[0] or 0)
    ticket_missing = int(row[3] or 0)
    profit_missing = int(row[4] or 0)
    loss_ticket_missing = int(row[7] or 0)
    known_ticket = _int(row[1])
    known_profit = _decimal(row[2])
    known_loss_tickets = _int(row[5]) or 0
    known_loss_profit = _decimal(row[6]) or Decimal(0)
    complete_tickets = known_ticket if row_count and ticket_missing == 0 else None
    complete_profit = known_profit if row_count and profit_missing == 0 else None
    loss_tickets = (
        known_loss_tickets
        if row_count and profit_missing == 0 and loss_ticket_missing == 0
        else None
    )
    loss_profit = known_loss_profit if row_count and profit_missing == 0 else None
    average_loss = None
    loss_share = None
    if loss_tickets and loss_profit is not None:
        average_loss = abs(loss_profit) / Decimal(loss_tickets)
    if complete_tickets and loss_tickets is not None:
        loss_share = Decimal(loss_tickets) / Decimal(complete_tickets)
    return {
        "rowCount": row_count,
        "ticketCount": complete_tickets,
        "knownTicketCount": known_ticket,
        "ticketMissingCount": ticket_missing,
        "estimatedProfit": _text(complete_profit),
        "knownProfit": _text(known_profit),
        "profitMissingCount": profit_missing,
        "lossTicketCount": loss_tickets,
        "lossEstimatedProfit": _text(loss_profit),
        "averageLossPerTicket": _text(average_loss),
        "lossTicketShare": _text(loss_share),
        "profitTicketCount": _int(row[8]) if row_count and profit_missing == 0 else None,
        "zeroTicketCount": _int(row[9]) if row_count and profit_missing == 0 else None,
        "status": (
            "no_records" if row_count == 0 else
            "incomplete" if ticket_missing or profit_missing else
            "ready"
        ),
    }


class RiskBusinessAnalysisService:
    def __init__(self, config: dict[str, Any]):
        self.source = DataSource({**config, "DATA_MODE": "mysql"})

    def analysis(
        self,
        *,
        business_type: str,
        start_value: str | None = None,
        end_value: str | None = None,
        group: str = "platform",
        filters: dict[str, Any] | None = None,
        page_value: str | int | None = 1,
        page_size_value: str | int | None = 30,
    ) -> dict[str, Any]:
        if business_type not in SPECS:
            raise ValueError("业务类型只支持出票、退票或改签")
        spec = SPECS[business_type]
        first, last = parse_period(start_value, end_value)
        groups = available_groups(spec)
        if group not in {item["key"] for item in groups}:
            raise ValueError(f"{spec.label}不支持当前分析维度")
        normalized_filters = normalize_filters(filters, spec)
        try:
            page = int(page_value or 1)
            page_size = int(page_size_value or 30)
        except (TypeError, ValueError):
            raise ValueError("分页参数不合法") from None
        if page < 1 or page > 10000 or page_size < 1 or page_size > 100:
            raise ValueError("页码必须大于0，每页最多100条")

        table = f"{self.source.database}.{spec.table}"
        where, parameters = build_where(
            spec,
            first.isoformat(),
            (last + timedelta(days=1)).isoformat(),
            normalized_filters,
        )
        group_field = _group_field(spec, group)
        response: dict[str, Any] = {
            "available": False,
            "error": "",
            "source": f"MySQL · {table}",
            "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "business": {"key": spec.key, "label": spec.label},
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat(), "timeField": spec.time_field},
            "filters": normalized_filters,
            "availableGroups": groups,
            "groupBy": group,
            "reasonAvailable": bool(spec.reason_field),
            "summary": metric_from_row((0, None, None, 0, 0, 0, 0, 0, 0, 0)),
            "trend": [],
            "dimensions": [],
            "orders": {"page": page, "pageSize": page_size, "total": 0, "rows": []},
            "notes": [
                "票数按SUM(ticket_num)，金额按SUM(estimated_profit_cny)，保留源正负号和NULL，不代表财务已结算利润。",
                f"{spec.label}按{spec.time_field}筛选；维度名称为精确匹配，订单列表继承当前全部筛选条件。",
                "亏损票数占比=亏损记录票数/所选记录总票数；平均每张亏损=亏损金额绝对值/亏损票数。",
            ],
        }
        if not spec.reason_field:
            response["notes"].append(
                f"{spec.label}表尚无标准盈亏原因字段，原因维度暂不开放；利润备注只作为订单证据展示，不替代标准原因。"
            )

        connection = None
        cursors = []
        try:
            connection = self.source.connect()

            summary_cursor = connection.cursor()
            cursors.append(summary_cursor)
            summary_cursor.execute(f"SELECT {METRIC_SELECT} FROM {table} WHERE {where}", parameters)
            response["summary"] = metric_from_row(summary_cursor.fetchone())

            trend_cursor = connection.cursor()
            cursors.append(trend_cursor)
            trend_cursor.execute(
                f"SELECT SUBSTR({spec.time_field},1,7), {METRIC_SELECT} "
                f"FROM {table} WHERE {where} GROUP BY SUBSTR({spec.time_field},1,7) "
                f"ORDER BY SUBSTR({spec.time_field},1,7)",
                parameters,
            )
            response["trend"] = [
                {"period": str(row[0]), **metric_from_row(row[1:])}
                for row in trend_cursor.fetchall()
            ]

            dimension_cursor = connection.cursor()
            cursors.append(dimension_cursor)
            group_expression = f"NULLIF(TRIM({group_field}),'')"
            dimension_cursor.execute(
                f"SELECT {group_expression}, {METRIC_SELECT} FROM {table} WHERE {where} "
                f"GROUP BY {group_expression} "
                "ORDER BY SUM(estimated_profit_cny) ASC, SUM(ticket_num) DESC LIMIT 50",
                parameters,
            )
            response["dimensions"] = [
                {
                    "key": str(index),
                    "name": str(row[0]) if row[0] is not None else "未填写",
                    "value": str(row[0]) if row[0] is not None else None,
                    **metric_from_row(row[1:]),
                }
                for index, row in enumerate(dimension_cursor.fetchall(), start=1)
            ]

            count_cursor = connection.cursor()
            cursors.append(count_cursor)
            count_cursor.execute(f"SELECT COUNT(1) FROM {table} WHERE {where}", parameters)
            response["orders"]["total"] = int(count_cursor.fetchone()[0] or 0)

            order_cursor = connection.cursor()
            cursors.append(order_cursor)
            reason_expression = spec.reason_field or "NULL"
            offset = (page - 1) * page_size
            order_cursor.execute(
                "SELECT "
                f"CAST({spec.time_field} AS CHAR), CAST(ota_order_no AS CHAR), "
                "CAST(relation_order_no AS CHAR), CAST(issue_ticket_no AS CHAR), "
                f"CAST({spec.service_order_field} AS CHAR), NULLIF(TRIM(passenger_name),''), "
                "NULLIF(TRIM(ota_cname),''), NULLIF(TRIM(ota_site_cname),''), "
                "NULLIF(TRIM(org_cname),''), NULLIF(TRIM(marketing_airline),''), "
                "NULLIF(TRIM(air_route),''), NULLIF(TRIM(supplier_cname),''), "
                f"NULLIF(TRIM(policy_operator),''), NULLIF(TRIM({spec.operator_field}),''), "
                f"NULLIF(TRIM({reason_expression}),''), NULLIF(TRIM(profit_remark),''), "
                f"NULLIF(TRIM({spec.verify_field}),''), ticket_num, estimated_profit_cny, actual_profit_cny "
                f"FROM {table} WHERE {where} "
                f"ORDER BY {spec.time_field} DESC, estimated_profit_cny ASC "
                "LIMIT %s OFFSET %s",
                [*parameters, page_size, offset],
            )
            response["orders"]["rows"] = [
                {
                    "recordKey": f"{spec.key}-{page}-{index}-{row[3] or ''}-{row[4] or ''}-{row[5] or ''}",
                    "businessDate": str(row[0] or ""),
                    "otaOrderNo": str(row[1] or ""),
                    "relationOrderNo": str(row[2] or ""),
                    "issueTicketNo": str(row[3] or ""),
                    "serviceOrderNo": str(row[4] or ""),
                    "passengerName": row[5],
                    "platform": row[6],
                    "site": row[7],
                    "department": row[8],
                    "airline": row[9],
                    "route": row[10],
                    "supplier": row[11],
                    "policyOperator": row[12],
                    "operator": row[13],
                    "reason": row[14],
                    "profitRemark": row[15],
                    "verifyResult": row[16],
                    "ticketCount": _int(row[17]),
                    "estimatedProfit": _text(row[18]),
                    "actualProfit": _text(row[19]),
                }
                for index, row in enumerate(order_cursor.fetchall(), start=(page - 1) * page_size + 1)
            ]
            response["available"] = True
        except Exception:
            LOGGER.exception("MySQL %s risk business analysis failed", spec.key)
            response["error"] = f"{spec.label}风控利润分析查询失败，请检查MySQL连接、表结构与同步批次。"
            response["trend"] = []
            response["dimensions"] = []
            response["orders"] = {"page": page, "pageSize": page_size, "total": 0, "rows": []}
        finally:
            for cursor in cursors:
                cursor.close()
            if connection is not None:
                connection.close()
        return response
