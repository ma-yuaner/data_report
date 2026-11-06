"""Read-only ADM business references from HOTEL and FI databases."""

from __future__ import annotations

from typing import Any, Iterable

from ..data_source import DataSource
from .policy import AdmError


def _source(config: dict[str, Any], prefix: str, default_database: str) -> DataSource:
    mysql = dict(config)
    mysql.update(
        DATA_MODE="mysql",
        MYSQL_HOST=config.get(f"{prefix}_MYSQL_HOST"),
        MYSQL_PORT=config.get(f"{prefix}_MYSQL_PORT", 3306),
        MYSQL_DATABASE=config.get(f"{prefix}_MYSQL_DATABASE") or default_database,
        MYSQL_USER=config.get(f"{prefix}_MYSQL_USER"),
        MYSQL_PASSWORD=config.get(f"{prefix}_MYSQL_PASSWORD"),
        MYSQL_CHARSET=config.get(f"{prefix}_MYSQL_CHARSET", "utf8mb4"),
        MYSQL_CONNECT_TIMEOUT=config.get(f"{prefix}_MYSQL_CONNECT_TIMEOUT", 10),
        MYSQL_READ_TIMEOUT=config.get(f"{prefix}_MYSQL_READ_TIMEOUT", 60),
        MYSQL_WRITE_TIMEOUT=config.get(f"{prefix}_MYSQL_WRITE_TIMEOUT", 60),
        MYSQL_POOL_SIZE=4,
        MYSQL_POOL_MIN_CACHED=1,
    )
    return DataSource(mysql)


class AdmBusinessReference:
    """Provide active difference types and exact FI difference-order matches."""

    def __init__(self, config: dict[str, Any]):
        self.hotel = _source(config, "HOTEL", "common_prod_db")
        self.fi = _source(config, "FI", "ibf_prod_db")

    def options(self) -> dict[str, Any]:
        connection = None
        try:
            import pymysql

            connection = self.hotel.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT DISTINCT TRIM(det_cname) name "
                    "FROM base_com_type_det "
                    "WHERE type_code=%s AND det_cname LIKE %s AND status=1 "
                    "AND COALESCE(TRIM(det_cname),'')<>'' ORDER BY name",
                    ("FI_AMT_DIFF_TYPE", "ADM-%"),
                )
                rows = cursor.fetchall()
            return {
                "differenceTypeSource": {
                    "database": self.hotel.database,
                    "table": "base_com_type_det",
                    "typeCode": "FI_AMT_DIFF_TYPE",
                    "configured": True,
                },
                "differenceTypes": [
                    {"code": str(row["name"]), "name": str(row["name"]), "label": str(row["name"])}
                    for row in rows
                ],
                "differenceEntrySource": {
                    "database": self.fi.database,
                    "table": "order_info_diff_reason",
                    "configured": True,
                    "matchPriority": ["OTA_ORDER_NO", "INTERNAL_ADM_NO"],
                },
            }
        except Exception as error:
            raise AdmError("ADM差异类型参考数据暂不可用", 503, "ADM_DIFFERENCE_TYPE_UNAVAILABLE") from error
        finally:
            if connection is not None:
                connection.close()

    def matched_difference_keys(self, values: Iterable[str]) -> set[str]:
        keys = list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))
        if not keys:
            return set()
        matched: set[str] = set()
        connection = None
        try:
            import pymysql

            connection = self.fi.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                for start in range(0, len(keys), 500):
                    chunk = keys[start : start + 500]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(
                        "SELECT DISTINCT ota_order_no FROM order_info_diff_reason "
                        "WHERE diff_reason=%s AND sys_product_type=%s AND diff_type=%s "
                        f"AND ota_order_no IN ({placeholders})",
                        ["R01", "P1", "D1", *chunk],
                    )
                    matched.update(str(row["ota_order_no"]).strip() for row in cursor.fetchall())
            return matched
        except Exception as error:
            raise AdmError("FI差异单核验暂不可用", 503, "ADM_DIFFERENCE_MATCH_UNAVAILABLE") from error
        finally:
            if connection is not None:
                connection.close()
