"""Query MySQL business wide-table rows for comprehensive-analysis drill-down."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .comprehensive_analysis import BUSINESSES, DIMENSIONS, parse_period
from .data_source import DataSource


@dataclass(frozen=True)
class DetailColumn:
    key: str
    title: str
    expression: str
    value_type: str = "text"
    width: int = 140


@dataclass(frozen=True)
class DetailSpec:
    table: str
    time_field: str
    order_field: str
    platform_filters: tuple[tuple[str, int], ...]
    site_filters: tuple[tuple[str, int], ...]
    airline_field: str
    policy_field: str
    columns: tuple[DetailColumn, ...]


def column(
    key: str,
    title: str,
    field_or_expression: str,
    value_type: str = "text",
    width: int = 140,
    *,
    raw: bool = False,
) -> DetailColumn:
    expression = field_or_expression if raw else f"src.{field_or_expression}"
    return DetailColumn(key, title, expression, value_type, width)


DETAIL_SPECS = {
    "issue": DetailSpec(
        table="bi_order_issue_profit_reconcile_year",
        time_field="business_date",
        order_field="issue_ticket_no",
        platform_filters=(("src.ota_cname", 1),),
        site_filters=(("src.ota_site_cname", 2),),
        airline_field="marketing_airline",
        policy_field="policy_operator",
        columns=(
            column("otaName", "OTA平台名称", "ota_cname", width=125),
            column("siteName", "站点名称", "ota_site_cname", width=150),
            column("issueDate", "出票日期", "issue_date", "date", 115),
            column("otaOrderNo", "OTA订单号", "ota_order_no", width=150),
            column("relationOrderNo", "关联订单号", "relation_order_no", width=150),
            column("issueTicketNo", "出票票号", "issue_ticket_no", width=150),
            column("profitReason", "业务盈亏原因", "profit_reason_type", width=160),
            column("profitRemark", "利润备注", "profit_remark", width=220),
            column("airRoute", "航程", "air_route", width=160),
            column("airline", "航司", "marketing_airline", width=85),
            column("segmentCount", "航段数", "segment_num", "count", 90),
            column("supplierName", "供应商名称", "supplier_cname", width=150),
            column("estimatedProfit", "预估利润(公式)", "estimated_profit_cny", "money", 145),
            column("policyOperator", "政策员", "policy_operator", width=110),
            column("operator", "出票员", "issue_operator", width=110),
            column("ticketCount", "票数", "ticket_num", "count", 85),
            column(
                "singleSegmentProfit",
                "单段利润",
                "CASE WHEN src.segment_num IS NULL OR src.segment_num=0 "
                "THEN NULL ELSE src.estimated_profit_cny/src.segment_num END",
                "money",
                125,
                raw=True,
            ),
        ),
    ),
    "change": DetailSpec(
        table="bi_order_change_profit_reconcile_year",
        time_field="stat_date",
        order_field="change_order_no",
        platform_filters=(("src.ota_cname", 1),),
        site_filters=(("src.ota_site_cname", 2),),
        airline_field="marketing_airline",
        policy_field="policy_operator",
        columns=(
            column("otaName", "OTA平台名称", "ota_cname", width=125),
            column("siteName", "站点名称", "ota_site_cname", width=150),
            column("businessDate", "业务日期", "stat_date", "date", 115),
            column("otaOrderNo", "OTA订单号", "ota_order_no", width=150),
            column("relationOrderNo", "关联订单号", "relation_order_no", width=150),
            column("issueTicketNo", "出票票号", "issue_ticket_no", width=150),
            column("changeOrderNo", "改签单号", "change_order_no", width=150),
            column("profitRemark", "利润备注", "profit_remark", width=220),
            column("airline", "航司", "marketing_airline", width=85),
            column("supplierName", "供应商名称", "supplier_cname", width=150),
            column("estimatedProfit", "预估利润(公式)", "estimated_profit_cny", "money", 145),
            column("policyOperator", "政策员", "policy_operator", width=110),
            column("operator", "操作员", "change_operator", width=110),
            column("performanceCategory", "业绩分类", "performance_category", width=155),
            column("ticketCount", "票数", "ticket_num", "count", 85),
        ),
    ),
    "refund": DetailSpec(
        table="bi_order_refund_profit_reconcile_year",
        time_field="business_date",
        order_field="refund_order_no",
        platform_filters=(("src.ota_cname", 1),),
        site_filters=(("src.ota_site_cname", 2),),
        airline_field="marketing_airline",
        policy_field="policy_operator",
        columns=(
            column("otaName", "OTA平台名称", "ota_cname", width=125),
            column("siteName", "站点名称", "ota_site_cname", width=150),
            column("businessDate", "业务日期", "business_date", "date", 115),
            column("otaOrderNo", "OTA订单号", "ota_order_no", width=150),
            column("relationOrderNo", "关联订单号", "relation_order_no", width=150),
            column("issueTicketNo", "出票票号", "issue_ticket_no", width=150),
            column("profitRemark", "利润备注", "profit_remark", width=220),
            column("airline", "航司", "marketing_airline", width=85),
            column("supplierName", "供应商名称", "supplier_cname", width=150),
            column("estimatedProfit", "预估利润(公式)", "estimated_profit_cny", "money", 145),
            column("actualProfit", "实际利润(推算)", "actual_profit_cny", "money", 145),
            column("policyOperator", "政策员", "policy_operator", width=110),
            column("operator", "操作员", "refund_operator", width=110),
            column("performanceCategory", "业绩分类", "performance_category", width=155),
            column("ticketCount", "票数", "ticket_num", "count", 85),
        ),
    ),
    "ancillary": DetailSpec(
        table="bi_aux_pur_year",
        time_field="create_time",
        order_field="pur_id",
        platform_filters=(("src.ota_code", 0), ("src.ota_cname", 1)),
        site_filters=(("src.ota_code", 0), ("src.ota_site_code", 1), ("src.ota_site_cname", 2)),
        airline_field="air_line",
        policy_field="policy_operator",
        columns=(
            column("otaName", "OTA平台名称", "ota_cname", width=125),
            column("siteName", "站点名称", "ota_site_cname", width=150),
            column("businessDate", "业务日期", "DATE(src.create_time)", "date", 115, raw=True),
            column("entryDate", "进单日期", "create_time", "datetime", 175),
            column("otaOrderNo", "OTA订单号", "ota_order_no", width=150),
            column("relationOrderNo", "关联订单号", "order_id", width=150),
            column("issueTicketNo", "出票票号", "CAST(NULL AS CHAR)", width=150, raw=True),
            column("airline", "航司", "air_line", width=85),
            column("supplierName", "供应商名称", "supplier_cname", width=150),
            column("estimatedProfit", "预估利润(公式)", "profit", "money", 145),
            column("policyOperator", "政策员", "policy_operator", width=110),
            column("operator", "操作员", "operator_name", width=110),
            column("performanceCategory", "业绩分类", "CAST(NULL AS CHAR)", width=155, raw=True),
            column("ticketCount", "票数", "1", "count", 85, raw=True),
        ),
    ),
}

BUSINESS_LABELS = {
    "issue": "出票",
    "refund": "退票",
    "change": "改签",
    "ancillary": "增值",
}


def parse_detail_filters(filters: dict[str, str | None]) -> dict[str, list[str | None]]:
    result: dict[str, list[str | None]] = {}
    for key, fields in DIMENSIONS.items():
        token = filters.get(key)
        if not token:
            continue
        try:
            values = json.loads(token)
            if not isinstance(values, list) or len(values) != len(fields):
                raise ValueError
            if any(
                value is not None
                and (not isinstance(value, str) or len(value) > 1000)
                for value in values
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"{key}筛选值不合法") from None
        result[key] = values
    return result


def normalized_condition(expression: str, value: str | None) -> tuple[str, list[str]]:
    normalized = f"NULLIF(TRIM({expression}),'')"
    if value is None:
        return f"{normalized} IS NULL", []
    return f"{normalized}=%s", [value]


def build_detail_queries(
    *,
    database: str,
    business: str,
    start_date: str,
    next_date: str,
    filters: dict[str, list[str | None]],
    page: int,
    page_size: int,
) -> tuple[str, str, list[str], list[Any]]:
    spec = DETAIL_SPECS[business]
    table = f"{database}.{spec.table}"
    conditions = [f"src.{spec.time_field}>=%s", f"src.{spec.time_field}<%s"]
    parameters: list[str] = [start_date, next_date]

    mappings = {
        "platform": spec.platform_filters,
        "site": spec.site_filters,
        "airline": ((f"src.{spec.airline_field}", 0),),
        "policy": ((f"src.{spec.policy_field}", 0),),
    }
    for key, expressions in mappings.items():
        if key not in filters:
            continue
        for expression, value_index in expressions:
            condition, values = normalized_condition(expression, filters[key][value_index])
            conditions.append(condition)
            parameters.extend(values)

    where_clause = "\n  AND ".join(conditions)
    count_query = f"SELECT COUNT(1) FROM {table} src WHERE {where_clause}"
    offset = (page - 1) * page_size
    select_clause = ",\n       ".join(item.expression for item in spec.columns)
    data_query = (
        f"SELECT {select_clause}\n"
        f"FROM {table} src\n"
        f"WHERE {where_clause}\n"
        f"ORDER BY src.{spec.time_field} DESC, src.{spec.order_field} DESC\n"
        "LIMIT %s OFFSET %s"
    )
    return count_query, data_query, parameters, [*parameters, page_size, offset]


def serialize_value(value: Any, value_type: str) -> str | int | None:
    if value is None:
        return None
    if value_type == "count":
        return int(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return str(value)
    return str(value)


class ComprehensiveDetailService:
    def __init__(self, config: dict[str, Any]):
        self.source = DataSource({**config, "DATA_MODE": "mysql"})

    def details(
        self,
        *,
        start_value: str | None,
        end_value: str | None,
        business: str,
        filters: dict[str, str | None],
        page_value: str | int | None = 1,
        page_size_value: str | int | None = 50,
    ) -> dict[str, Any]:
        if business not in BUSINESSES:
            raise ValueError("不支持的业务类型")
        first, last = parse_period(start_value, end_value)
        if (last - first).days > 30:
            raise ValueError("宽表明细单次最多查询31天，请从日汇总进入或缩小日期范围")
        try:
            page = int(page_value or 1)
            page_size = int(page_size_value or 50)
        except (TypeError, ValueError):
            raise ValueError("分页参数不合法") from None
        if page < 1 or page > 10_000 or page_size < 1 or page_size > 100:
            raise ValueError("页码必须大于0，每页最多100条")
        parsed_filters = parse_detail_filters(filters)
        if "product" in parsed_filters:
            raise ValueError(
                "当前MySQL明细宽表尚未同步与ADS一致的机票产品字段，"
                "不能忽略产品条件返回错误明细；请先补充ticket_product_raw字段。"
            )
        spec = DETAIL_SPECS[business]
        response = {
            "available": False,
            "error": "",
            "source": f"MySQL · {self.source.database}.{spec.table}",
            "business": {"key": business, "label": BUSINESS_LABELS[business]},
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "columns": [
                {
                    "key": item.key,
                    "title": item.title,
                    "valueType": item.value_type,
                    "width": item.width,
                }
                for item in spec.columns
            ],
            "page": page,
            "pageSize": page_size,
            "total": 0,
            "rows": [],
        }
        count_query, data_query, count_params, data_params = build_detail_queries(
            database=self.source.database,
            business=business,
            start_date=first.isoformat(),
            next_date=(last + timedelta(days=1)).isoformat(),
            filters=parsed_filters,
            page=page,
            page_size=page_size,
        )
        connection = count_cursor = data_cursor = None
        try:
            connection = self.source.connect()
            count_cursor = connection.cursor()
            count_cursor.execute(count_query, count_params)
            total = int(count_cursor.fetchone()[0] or 0)
            data_cursor = connection.cursor()
            data_cursor.execute(data_query, data_params)
            raw_rows = data_cursor.fetchall()
            rows = []
            for index, raw_row in enumerate(raw_rows, start=(page - 1) * page_size + 1):
                row = {
                    item.key: serialize_value(value, item.value_type)
                    for item, value in zip(spec.columns, raw_row)
                }
                row["recordKey"] = f"{business}-{page}-{index}"
                rows.append(row)
            response["rows"] = rows
            response["total"] = total
            response["available"] = True
            return response
        except Exception:
            logging.getLogger(__name__).exception("MySQL comprehensive detail query failed")
            response["error"] = "宽表明细查询失败，请检查MySQL连接、源表字段与当前筛选条件。"
            return response
        finally:
            if count_cursor is not None:
                count_cursor.close()
            if data_cursor is not None:
                data_cursor.close()
            if connection is not None:
                connection.close()
