from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from ..time_utils import business_now
from .data_source import DataSource


class GdsRouteAnalysisUnavailable(RuntimeError):
    """The Hive route aggregate is unavailable or does not match its contract."""


REQUIRED_COLUMNS = {
    "operator_date", "data_source", "api_method", "source_api_group",
    "gds_code", "pcc_code", "airroute_code", "dep_airport", "arr_airport",
    "dep_city", "arr_city", "ota_code", "ota_site_code", "poi_code",
    "poi_list", "api_request_count_all", "api_request_success",
    "api_request_error", "api_execute_time", "api_result_success",
    "api_cache_count", "api_timeout_count", "api_price_count",
    "api_price_change", "direct_flight_count", "connecting_flight_count",
    "operator_mintes_max",
}

DIMENSION_COLUMNS = (
    "airroute_code", "dep_city", "arr_city", "dep_airport", "arr_airport",
    "ota_code", "ota_site_code", "gds_code", "pcc_code",
)


def _identifier(value: Any, default: str) -> str:
    text = str(value or default).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        raise RuntimeError("GDS航线Hive表名配置不合法")
    return text


def _number(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return int(value)
    return int(value)


def _ratio(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return f"{numerator * 100 / denominator:.2f}"


def _average(total: int, count: int) -> str | None:
    if count <= 0:
        return None
    return f"{total / count:.2f}"


def _channel_expression(channel: str) -> str:
    normalized = "upper(regexp_replace(coalesce(source_api_group, ''), '[^A-Za-z0-9]', ''))"
    if channel == "MPIS":
        return f"{normalized} rlike 'MPIS$'"
    if channel == "NDC":
        return f"{normalized} rlike 'NDC$'"
    return f"not ({normalized} rlike 'MPIS$') and not ({normalized} rlike 'NDC$')"


METRIC_SQL = f"""
    coalesce(sum(api_request_count_all), 0),
    coalesce(sum(case when api_method = 'search' then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_request_success else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_request_error else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_result_success else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_price_count else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_timeout_count else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_cache_count else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then api_execute_time else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_request_success else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_request_error else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_timeout_count else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_execute_time else 0 end), 0),
    coalesce(sum(case when api_method = 'verify' then api_price_change else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_request_success else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_request_error else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_timeout_count else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_execute_time else 0 end), 0),
    coalesce(sum(case when api_method = 'orderCreate' then api_price_change else 0 end), 0),
    coalesce(sum(case when api_method = 'search' and {_channel_expression('MP')} then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'search' and {_channel_expression('MPIS')} then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'search' and {_channel_expression('NDC')} then api_request_count_all else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then direct_flight_count else 0 end), 0),
    coalesce(sum(case when api_method = 'search' then connecting_flight_count else 0 end), 0),
    max(operator_mintes_max)
""".strip()


def _metric(row: Iterable[Any]) -> dict[str, Any]:
    values = list(row)
    numbers = [_number(value) for value in values[:26]]
    (
        request_count, search_requests, search_success, search_errors,
        search_result_success, search_price_count, search_timeouts, search_cache,
        search_execute_time, verify_requests, verify_success, verify_errors,
        verify_timeouts, verify_execute_time, verify_price_changes, order_requests,
        order_success, order_errors, order_timeouts, order_execute_time,
        order_price_changes, mp_requests, mpis_requests, ndc_requests,
        direct_flights, connecting_flights,
    ) = numbers
    return {
        "requestCount": request_count,
        "searchRequests": search_requests,
        "searchSuccess": search_success,
        "searchFailure": search_errors,
        "searchResultSuccess": search_result_success,
        "searchPriceCount": search_price_count,
        "searchTimeouts": search_timeouts,
        "searchCacheCount": search_cache,
        "searchSuccessRate": _ratio(search_success, search_requests),
        "searchResultSuccessRate": _ratio(search_result_success, search_requests),
        "searchTimeoutRate": _ratio(search_timeouts, search_requests),
        "searchCacheRate": _ratio(search_cache, search_requests),
        "avgSearchExecuteTime": _average(search_execute_time, search_success),
        "verifyRequests": verify_requests,
        "verifySuccess": verify_success,
        "verifyFailure": verify_errors,
        "verifySuccessRate": _ratio(verify_success, verify_requests),
        "verifyTimeoutRate": _ratio(verify_timeouts, verify_requests),
        "verifyPriceChangeRate": _ratio(verify_price_changes, verify_requests),
        "avgVerifyExecuteTime": _average(verify_execute_time, verify_success),
        "orderRequests": order_requests,
        "orderSuccess": order_success,
        "orderFailure": order_errors,
        "orderSuccessRate": _ratio(order_success, order_requests),
        "orderTimeoutRate": _ratio(order_timeouts, order_requests),
        "orderPriceChangeRate": _ratio(order_price_changes, order_requests),
        "avgOrderExecuteTime": _average(order_execute_time, order_success),
        "mpSearchRequests": mp_requests,
        "mpisSearchRequests": mpis_requests,
        "ndcSearchRequests": ndc_requests,
        "mpShare": _ratio(mp_requests, search_requests),
        "mpisShare": _ratio(mpis_requests, search_requests),
        "ndcShare": _ratio(ndc_requests, search_requests),
        "directFlightCount": direct_flights,
        "connectingFlightCount": connecting_flights,
        "sourceUpdatedAt": str(values[26]) if values[26] is not None else None,
    }


class GdsRouteAnalysisService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        self.config = config
        self.source = source or DataSource({**config, "DATA_MODE": "hive"})
        self.table_name = _identifier(config.get("GDS_ROUTE_HIVE_TABLE"), "dws_gds_airroute_day")
        self.table = f"{self.source.database}.{self.table_name}"
        self.max_rows = max(50, min(int(config.get("GDS_ROUTE_MAX_ROWS", 500)), 2000))
        self.max_days = max(1, min(int(config.get("GDS_ROUTE_MAX_DAYS", 31)), 92))

    def overview(
        self,
        start_value: str | None,
        end_value: str | None,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        start_date, end_date = self._period(start_value, end_value)
        normalized_filters = {key: str(value or "").strip() for key, value in (filters or {}).items()}
        connection = self.source.connect()
        cursor = connection.cursor()
        try:
            self._validate_schema(cursor)
            where_sql, params = self._where(start_date, end_date, normalized_filters)
            cursor.execute(f"SELECT {METRIC_SQL} FROM {self.table} WHERE {where_sql}", tuple(params))
            summary_row = cursor.fetchone()
            summary = _metric(summary_row or [0] * 27)

            dimensions = ", ".join(DIMENSION_COLUMNS)
            cursor.execute(
                f"SELECT {dimensions}, {METRIC_SQL} FROM {self.table} WHERE {where_sql} "
                f"GROUP BY {dimensions} ORDER BY sum(case when api_method = 'search' "
                f"then api_request_count_all else 0 end) DESC LIMIT {self.max_rows + 1}",
                tuple(params),
            )
            raw_rows = list(cursor.fetchall())
            truncated = len(raw_rows) > self.max_rows
            rows = [self._route_row(row) for row in raw_rows[: self.max_rows]]
            options = self._options(cursor, start_date, end_date)
            return {
                "source": self.source.label,
                "table": self.table,
                "available": True,
                "generatedAt": business_now().isoformat(timespec="seconds"),
                "period": {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
                "filters": normalized_filters,
                "summary": summary,
                "rows": rows,
                "rowCount": len(rows),
                "resultLimit": self.max_rows,
                "truncated": truncated,
                "options": options,
                "notes": [
                    "航线页直接查询Hive日汇总，不经过MySQL服务表。",
                    "查询、验价、生单分别按api_method=search、verify、orderCreate统计。",
                    "查询日志不写实际航司，首版不使用poi_code拆分查询量。",
                    "本表没有出票航段分母，航线页不计算查定比，避免产生错误结论。",
                ],
            }
        except ValueError:
            raise
        except Exception as error:
            raise GdsRouteAnalysisUnavailable(f"GDS航线Hive查询失败：{error}") from error
        finally:
            try:
                cursor.close()
            finally:
                connection.close()

    def _period(self, start_value: str | None, end_value: str | None) -> tuple[date, date]:
        yesterday = business_now().date() - timedelta(days=1)
        end_date = self._date(end_value, yesterday)
        if end_date > yesterday:
            end_date = yesterday
        start_date = self._date(start_value, end_date)
        if start_date > end_date:
            raise ValueError("统计开始日期不能晚于结束日期")
        if (end_date - start_date).days + 1 > self.max_days:
            raise ValueError(f"Hive航线明细单次最多查询{self.max_days}天")
        return start_date, end_date

    @staticmethod
    def _date(value: str | None, default: date) -> date:
        if not str(value or "").strip():
            return default
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except ValueError as error:
            raise ValueError("日期格式必须为YYYY-MM-DD") from error

    def _validate_schema(self, cursor) -> None:
        cursor.execute(f"DESCRIBE {self.table}")
        columns = {
            str(row[0]).strip().lower()
            for row in cursor.fetchall()
            if row and str(row[0] or "").strip() and not str(row[0]).startswith("#")
        }
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise GdsRouteAnalysisUnavailable(
                f"{self.table}缺少航线分析字段：{','.join(missing)}"
            )

    def _where(
        self, start_date: date, end_date: date, filters: dict[str, str]
    ) -> tuple[str, list[Any]]:
        clauses = [
            "operator_date >= %s", "operator_date <= %s",
            "(trim(data_source) = '1' or upper(trim(data_source)) = 'GDS')",
            "coalesce(trim(airroute_code), '') <> ''",
        ]
        params: list[Any] = [start_date.isoformat(), end_date.isoformat()]
        mappings = {
            "platform": "ota_code", "site": "ota_site_code", "gds": "gds_code",
            "pcc": "pcc_code", "apiGroup": "source_api_group", "route": "airroute_code",
        }
        for key, field in mappings.items():
            value = filters.get(key, "")
            if value:
                clauses.append(f"trim({field}) = %s")
                params.append(value)
        keyword = filters.get("keyword", "").upper()
        if keyword:
            clauses.append(
                "upper(concat_ws('|', coalesce(airroute_code,''), coalesce(dep_airport,''), "
                "coalesce(arr_airport,''), coalesce(dep_city,''), coalesce(arr_city,''), "
                "coalesce(poi_code,''), coalesce(poi_list,''))) like %s"
            )
            params.append(f"%{keyword}%")
        return " AND ".join(clauses), params

    def _options(self, cursor, start_date: date, end_date: date) -> dict[str, list[str]]:
        cursor.execute(
            f"SELECT DISTINCT gds_code, pcc_code, ota_code, ota_site_code, source_api_group "
            f"FROM {self.table} WHERE operator_date >= %s AND operator_date <= %s "
            "AND (trim(data_source) = '1' or upper(trim(data_source)) = 'GDS') LIMIT 2000",
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()
        keys = ("gds", "pcc", "platform", "site", "apiGroup")
        result = {key: set() for key in keys}
        for row in rows:
            for index, key in enumerate(keys):
                value = str(row[index] or "").strip()
                if value:
                    result[key].add(value)
        return {key: sorted(values) for key, values in result.items()}

    @staticmethod
    def _route_row(row: Iterable[Any]) -> dict[str, Any]:
        values = list(row)
        dimensions = [str(value or "").strip() for value in values[: len(DIMENSION_COLUMNS)]]
        payload = dict(zip(DIMENSION_COLUMNS, dimensions))
        payload.update(_metric(values[len(DIMENSION_COLUMNS):]))
        payload.update({
            "id": "|".join(dimensions),
            "route": payload.pop("airroute_code"),
            "depCity": payload.pop("dep_city"),
            "arrCity": payload.pop("arr_city"),
            "depAirport": payload.pop("dep_airport"),
            "arrAirport": payload.pop("arr_airport"),
            "platform": payload.pop("ota_code"),
            "site": payload.pop("ota_site_code"),
            "gdsCode": payload.pop("gds_code"),
            "pccCode": payload.pop("pcc_code"),
        })
        return payload
