from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..time_utils import business_now
from .data_source import DataSource


TABLE_NAME = "bi_ota_gds_request_day"
DATA_SOURCES = {
    "ota": {"value": 0, "label": "OTA"},
    "gds": {"value": 1, "label": "GDS"},
}
DIMENSIONS = {
    "platform": {"field": "ota_code", "label": "平台"},
    "site": {"field": "ota_site_code", "label": "站点"},
    "gds": {"field": "gds_code", "label": "GDS"},
    "pcc": {"field": "pcc_code", "label": "PCC"},
    "apiGroup": {"field": "source_api_group", "label": "接口分组"},
}
FILTER_FIELDS = {key: value["field"] for key, value in DIMENSIONS.items()}
METRIC_SELECT = """
COUNT(1),
SUM(search_request_count_all), SUM(search_request_success),
SUM(verify_request_count_all), SUM(verify_request_success),
SUM(order_request_count_all), SUM(order_request_success),
{pnr_expression}, SUM(search_cache_count), SUM(search_execute_time),
SUM(search_request_count)
""".strip()


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("日期格式必须为YYYY-MM-DD") from error


def _clean_filter(value: Any) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > 100:
        raise ValueError("筛选值长度不能超过100个字符")
    return cleaned


def _rate(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    value = Decimal(numerator) * Decimal(100) / Decimal(denominator)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ratio(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    value = Decimal(numerator) / Decimal(denominator)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _date_label(value: Any) -> str:
    raw = str(value or "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _metric(row: tuple[Any, ...], pnr_column_available: bool, target_ratio: int) -> dict[str, Any]:
    row_count = int(row[0] or 0)
    search_requests = int(row[1] or 0)
    search_success = int(row[2] or 0)
    verify_requests = int(row[3] or 0)
    verify_success = int(row[4] or 0)
    order_requests = int(row[5] or 0)
    order_success = int(row[6] or 0)
    pnr_count = int(row[7]) if row[7] is not None else None
    search_cache = int(row[8] or 0)
    search_execute_time = int(row[9] or 0)
    search_effective_requests = int(row[10] or 0)

    if row_count == 0:
        status = "no_records"
    elif not pnr_column_available:
        status = "pnr_field_missing"
    elif pnr_count is None:
        status = "pnr_data_missing"
    elif pnr_count == 0 and search_requests > 0:
        status = "denominator_zero"
    else:
        status = "ready"

    excess = None if pnr_count is None else max(search_requests - pnr_count * target_ratio, 0)
    return {
        "rowCount": row_count,
        "searchRequests": search_requests,
        "searchSuccess": search_success,
        "verifyRequests": verify_requests,
        "verifySuccess": verify_success,
        "orderRequests": order_requests,
        "orderSuccess": order_success,
        "pnrCount": pnr_count,
        "queryToPnrRatio": _ratio(search_requests, pnr_count or 0),
        "ratioInfinite": bool(search_requests > 0 and pnr_count == 0),
        "searchSuccessRate": _rate(search_success, search_requests),
        "verifySuccessRate": _rate(verify_success, verify_requests),
        "orderSuccessRate": _rate(order_success, order_requests),
        "searchCacheRate": _rate(search_cache, search_requests),
        "avgSearchExecuteTime": _ratio(search_execute_time, search_effective_requests),
        "excessQueryCount": excess,
        "status": status,
    }


class ResourceGovernanceService:
    def __init__(self, config: dict[str, Any]):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.source = DataSource(mysql_config)
        self.target_ratio = max(1, int(config.get("RESOURCE_GOVERNANCE_TARGET_RATIO", 4000)))

    def overview(
        self,
        start_value: str | None = None,
        end_value: str | None = None,
        data_source: str = "gds",
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        today = business_now().date()
        first = _parse_date(start_value, today.replace(day=1))
        last = _parse_date(end_value, today)
        if first > last:
            raise ValueError("开始日期不能晚于结束日期")
        if (last - first).days > 366:
            raise ValueError("单次最多查询367天")
        source_key = str(data_source or "gds").strip().lower()
        if source_key not in DATA_SOURCES:
            raise ValueError("数据层只支持OTA或GDS")
        default_group = "gds" if source_key == "gds" else "platform"
        dimension_key = str(group_by or default_group).strip()
        if dimension_key not in DIMENSIONS:
            raise ValueError("不支持的分析维度")
        if source_key == "ota" and dimension_key in {"gds", "pcc"}:
            dimension_key = "platform"
        cleaned_filters = {
            key: _clean_filter((filters or {}).get(key)) for key in FILTER_FIELDS
        }

        result = {
            "source": self.source.label,
            "table": f"{self.source.database}.{TABLE_NAME}",
            "available": False,
            "error": "",
            "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "dataSource": {"key": source_key, **DATA_SOURCES[source_key]},
            "targetRatio": self.target_ratio,
            "pnrColumnAvailable": False,
            "pnrDataAvailable": False,
            "filters": cleaned_filters,
            "options": {key: [] for key in FILTER_FIELDS},
            "summary": _metric((0,) + (None,) * 10, False, self.target_ratio),
            "trend": [],
            "dimension": {"key": dimension_key, "label": DIMENSIONS[dimension_key]["label"], "rows": []},
            "notes": [
                "OTA与GDS是两个独立分析层，页面不跨层相加。",
                "查定比按查询总量÷实际有效PNR数重算，order_request_success仅表示直连生单接口成功。",
                "无有效PNR显示为∞，PNR未同步显示为—，二者不会混为0。",
            ],
        }
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                "SELECT COUNT(1) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME='pnr_count'",
                (self.source.database, TABLE_NAME),
            )
            pnr_column_available = bool(int((cursor.fetchone() or (0,))[0] or 0))
            pnr_expression = "SUM(pnr_count)" if pnr_column_available else "NULL"
            metric_select = METRIC_SELECT.format(pnr_expression=pnr_expression)

            date_params = [first.strftime("%Y%m%d"), last.strftime("%Y%m%d"), DATA_SOURCES[source_key]["value"]]
            base_where = ["operator_date >= %s", "operator_date <= %s", "data_source = %s"]
            option_sql = (
                "SELECT DISTINCT ota_code, ota_site_code, gds_code, pcc_code, source_api_group "
                f"FROM {self.source.database}.{TABLE_NAME} WHERE " + " AND ".join(base_where) + " LIMIT 5000"
            )
            cursor.execute(option_sql, tuple(date_params))
            option_rows = cursor.fetchall()
            for index, key in enumerate(("platform", "site", "gds", "pcc", "apiGroup")):
                result["options"][key] = sorted({str(row[index]).strip() for row in option_rows if row[index] is not None and str(row[index]).strip()})

            where = list(base_where)
            parameters: list[Any] = list(date_params)
            for key, value in cleaned_filters.items():
                if value:
                    where.append(f"{FILTER_FIELDS[key]} = %s")
                    parameters.append(value)
            where_sql = " AND ".join(where)
            table = f"{self.source.database}.{TABLE_NAME}"

            cursor.execute(f"SELECT {metric_select}, MAX(create_time) FROM {table} WHERE {where_sql}", tuple(parameters))
            summary_row = cursor.fetchone() or ((0,) + (None,) * 11)
            summary = _metric(tuple(summary_row[:11]), pnr_column_available, self.target_ratio)
            summary["sourceUpdatedAt"] = summary_row[11].isoformat(sep=" ", timespec="seconds") if isinstance(summary_row[11], datetime) else (str(summary_row[11]) if summary_row[11] else None)
            result["summary"] = summary

            cursor.execute(
                f"SELECT operator_date, {metric_select} FROM {table} WHERE {where_sql} "
                "GROUP BY operator_date ORDER BY operator_date",
                tuple(parameters),
            )
            result["trend"] = [
                {"date": _date_label(row[0]), **_metric(tuple(row[1:]), pnr_column_available, self.target_ratio)}
                for row in cursor.fetchall()
            ]

            dimension = DIMENSIONS[dimension_key]
            dimension_field = dimension["field"]
            cursor.execute(
                f"SELECT {dimension_field}, {metric_select} FROM {table} WHERE {where_sql} "
                f"AND {dimension_field} <> '' GROUP BY {dimension_field} "
                "ORDER BY SUM(search_request_count_all) DESC LIMIT 500",
                tuple(parameters),
            )
            result["dimension"]["rows"] = [
                {
                    "value": str(row[0]),
                    "name": str(row[0]),
                    **_metric(tuple(row[1:]), pnr_column_available, self.target_ratio),
                }
                for row in cursor.fetchall()
            ]
            result["pnrColumnAvailable"] = pnr_column_available
            result["pnrDataAvailable"] = pnr_column_available and summary["pnrCount"] is not None
            result["available"] = True
        except Exception as error:
            logging.getLogger(__name__).exception("GDS/OTA resource governance query failed")
            result["error"] = "GDS/OTA资源汇总查询失败，请检查MySQL连接、表结构与同步批次。"
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
        return result
