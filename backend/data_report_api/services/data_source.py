from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


LIVE_DATA_MODES = frozenset({"mysql", "hive"})
SUPPORTED_DATA_MODES = LIVE_DATA_MODES | {"mock"}


@dataclass(frozen=True)
class TableSpec:
    table: str
    time_field: str


TABLE_SPECS: dict[str, dict[str, TableSpec]] = {
    "mysql": {
        "issue": TableSpec("bi_order_issue_year", "operator_date"),
        "refund": TableSpec("bi_refund_issue_year", "apply_datetime"),
        "change": TableSpec("bi_change_issue_year", "change_issue_time"),
        "ancillary": TableSpec("bi_aux_pur_year", "create_time"),
    },
    "hive": {
        "issue": TableSpec("dwd_order_issue_wide_year", "issue_ticket_time"),
        "refund": TableSpec("dwd_refund_issue_year", "apply_datetime"),
        "change": TableSpec("dwd_change_issue_year", "change_issue_time"),
        "ancillary": TableSpec("dwd_aux_pur_year", "create_time"),
    },
}

FIELD_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "mysql": {
        "issue": {
            "marketing_airline": "air_line",
            "issue_supplier_cname": "supplier_name",
            "issue_ticketing_office_no": "pcc_code",
            "dep_city": "dep_city_code",
            "arr_city": "arr_city_code",
        }
    },
    "hive": {},
}


def data_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("DATA_MODE", "mysql")).strip().lower()
    if mode not in SUPPORTED_DATA_MODES:
        raise RuntimeError("DATA_MODE 只支持 mysql、hive 或 mock")
    return mode


def is_live_mode(mode: str) -> bool:
    return mode in LIVE_DATA_MODES


class DataSource:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.mode = data_mode(config)
        if self.mode not in LIVE_DATA_MODES:
            raise ValueError(f"不支持的数据源模式: {self.mode}")
        database_key = "MYSQL_DATABASE" if self.mode == "mysql" else "HIVE_DATABASE"
        default_database = "sibebid" if self.mode == "mysql" else "lywz"
        self.database = str(config.get(database_key, default_database)).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.database):
            raise RuntimeError(f"{self.engine_label}库名配置不合法")

    @property
    def engine_label(self) -> str:
        return "MySQL" if self.mode == "mysql" else "Hive"

    @property
    def label(self) -> str:
        return f"{self.engine_label} · {self.database}"

    @property
    def cache_key(self) -> str:
        return f"{self.mode}:{self.database}"

    def table(self, business_key: str) -> TableSpec:
        try:
            return TABLE_SPECS[self.mode][business_key]
        except KeyError as error:
            raise ValueError(f"不支持的业务类型: {business_key}") from error

    def qualified_table(self, business_key: str) -> str:
        spec = self.table(business_key)
        return f"{self.database}.{spec.table}"

    def field(self, business_key: str, logical_field: str) -> str:
        return FIELD_MAPPINGS.get(self.mode, {}).get(business_key, {}).get(logical_field, logical_field)

    def count_expression(self, business_key: str, condition: str | None = None) -> str:
        if self.mode == "mysql" and business_key == "issue":
            if condition:
                return f"coalesce(sum(case when {condition} then coalesce(iss_num, 0) else 0 end), 0)"
            return "coalesce(sum(iss_num), 0)"
        if condition:
            return f"sum(case when {condition} then 1 else 0 end)"
        return "count(1)"

    def period_expression(self, field: str, granularity: str) -> str:
        length = 7 if granularity == "month" else 10
        if self.mode == "mysql":
            pattern = "%Y-%m" if granularity == "month" else "%Y-%m-%d"
            return f"date_format({field}, '{pattern}')"
        return f"substr({field}, 1, {length})"

    def string_cast(self, expression: str) -> str:
        target_type = "char" if self.mode == "mysql" else "string"
        return f"cast({expression} as {target_type})"

    def connect(self):
        return self._connect_mysql() if self.mode == "mysql" else self._connect_hive()

    def _connect_mysql(self):
        host = str(self.config.get("MYSQL_HOST", "")).strip()
        user = str(self.config.get("MYSQL_USER", "")).strip()
        if not host or not user:
            raise RuntimeError("MySQL连接配置不完整")

        import pymysql

        return pymysql.connect(
            host=host,
            port=int(self.config.get("MYSQL_PORT", 3306)),
            user=user,
            password=str(self.config.get("MYSQL_PASSWORD", "")),
            database=self.database,
            charset=str(self.config.get("MYSQL_CHARSET", "utf8mb4")),
            connect_timeout=int(self.config.get("MYSQL_CONNECT_TIMEOUT", 10)),
            read_timeout=int(self.config.get("MYSQL_READ_TIMEOUT", 60)),
            write_timeout=int(self.config.get("MYSQL_WRITE_TIMEOUT", 60)),
            autocommit=True,
        )

    def _connect_hive(self):
        host = str(self.config.get("HIVE_HOST", "")).strip()
        user = str(self.config.get("HIVE_USER", "")).strip()
        if not host or not user:
            raise RuntimeError("Hive连接配置不完整")

        from pyhive import hive

        return hive.connect(
            host=host,
            port=int(self.config.get("HIVE_PORT", 10000)),
            database=self.database,
            username=user,
            password=str(self.config.get("HIVE_PASSWORD", "")) or None,
            auth=str(self.config.get("HIVE_AUTH", "NONE")),
        )
