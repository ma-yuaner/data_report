"""Query MySQL business wide-table rows for comprehensive-analysis drill-down."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from .comprehensive_analysis import BUSINESSES, DIMENSIONS, parse_period
from .data_source import DataSource


@dataclass(frozen=True)
class DetailSpec:
    table: str
    time_field: str
    event_id: str
    issue_id: str | None
    airline: str
    profit: str
    segments: str | None
    quantity: str
    base_condition: str | None = None


DETAIL_SPECS = {
    "issue": DetailSpec(
        table="bi_order_issue_year",
        time_field="operator_date",
        event_id="order_id",
        issue_id=None,
        airline="air_line",
        profit="issue_profit",
        segments="segment_num",
        quantity="COALESCE(src.iss_num,0)",
        base_condition=(
            "src.order_status='TICKETED' AND src.issue_status='I_UPDATED' "
            "AND src.refund_flag<>3 AND src.refund_issue_flag='否'"
        ),
    ),
    "refund": DetailSpec(
        table="bi_refund_issue_year",
        time_field="apply_datetime",
        event_id="refund_issue_id",
        issue_id="issue_id",
        airline="marketing_airline_s",
        profit="refund_profit",
        segments="segment_num",
        quantity="1",
        base_condition=(
            "src.business_type_desc IN ('正常退票（退票）','售后退票作废（退票）') "
            "AND src.supplier_refund_operator IS NOT NULL "
            "AND TRIM(src.supplier_refund_operator)<>''"
        ),
    ),
    "change": DetailSpec(
        table="bi_change_issue_year",
        time_field="change_issue_time",
        event_id="change_issue_id",
        issue_id="issue_id",
        airline="air_line",
        profit="change_profit",
        segments=None,
        quantity="1",
    ),
    "ancillary": DetailSpec(
        table="bi_aux_pur_year",
        time_field="create_time",
        event_id="pur_id",
        issue_id=None,
        airline="air_line",
        profit="profit",
        segments="flight_num",
        quantity="1",
        base_condition="src.aux_status='已购买'",
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
    if spec.base_condition:
        conditions.append(spec.base_condition)

    direct_dimensions = {
        "platform": ("src.ota_code", "src.ota_cname"),
        "site": ("src.ota_code", "src.ota_site_code", "src.ota_site_cname"),
        "airline": (f"src.{spec.airline}",),
        "policy": ("src.policy_operator",),
    }
    for key, expressions in direct_dimensions.items():
        if key not in filters:
            continue
        for expression, value in zip(expressions, filters[key]):
            condition, values = normalized_condition(expression, value)
            conditions.append(condition)
            parameters.extend(values)

    issue_id = (
        f"CAST(src.{spec.issue_id} AS CHAR)"
        if spec.issue_id
        else "CAST(NULL AS CHAR)"
    )
    segments = (
        f"CAST(src.{spec.segments} AS SIGNED)"
        if spec.segments
        else "CAST(NULL AS SIGNED)"
    )
    where_clause = "\n  AND ".join(conditions)
    count_query = f"SELECT COUNT(1) FROM {table} src WHERE {where_clause}"
    offset = (page - 1) * page_size
    data_query = (
        "SELECT "
        f"CAST(src.{spec.time_field} AS CHAR), "
        f"CAST(src.{spec.event_id} AS CHAR), {issue_id}, "
        "CAST(src.order_id AS CHAR),\n"
        "       NULLIF(TRIM(src.ota_code),''), NULLIF(TRIM(src.ota_cname),''), "
        "NULLIF(TRIM(src.ota_site_code),''), NULLIF(TRIM(src.ota_site_cname),''),\n"
        f"       NULLIF(TRIM(src.{spec.airline}),''), CAST(NULL AS CHAR), "
        f"NULLIF(TRIM(src.policy_operator),''), {segments},\n"
        f"       src.{spec.profit}, CAST({spec.quantity} AS SIGNED)\n"
        f"FROM {table} src\n"
        f"WHERE {where_clause}\n"
        f"ORDER BY src.{spec.time_field} DESC, src.{spec.event_id} DESC\n"
        "LIMIT %s OFFSET %s"
    )
    return count_query, data_query, parameters, [*parameters, page_size, offset]


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
                "当前MySQL出退改增宽表尚未同步与ADS一致的机票产品字段，"
                "不能忽略产品条件返回错误明细；请先补充ticket_product_raw字段。"
            )
        spec = DETAIL_SPECS[business]
        response = {
            "available": False,
            "error": "",
            "source": f"MySQL · {self.source.database}.{spec.table}",
            "business": {"key": business, "label": BUSINESS_LABELS[business]},
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
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
            for index, row in enumerate(raw_rows, start=(page - 1) * page_size + 1):
                profit = row[12]
                rows.append(
                    {
                        "recordKey": f"{business}-{index}-{row[1] or ''}-{row[3] or ''}",
                        "eventTime": str(row[0] or ""),
                        "businessId": str(row[1] or ""),
                        "issueId": str(row[2] or ""),
                        "orderId": str(row[3] or ""),
                        "otaCode": row[4],
                        "otaName": row[5],
                        "siteCode": row[6],
                        "siteName": row[7],
                        "airline": row[8],
                        "product": row[9],
                        "policyOperator": row[10],
                        "segmentCount": int(row[11]) if row[11] is not None else None,
                        "profit": str(profit) if isinstance(profit, Decimal) else (
                            str(profit) if profit is not None else None
                        ),
                        "businessCount": int(row[13] or 0),
                    }
                )
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
