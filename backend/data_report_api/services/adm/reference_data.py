"""Read-only ADM reference options from the confirmed ERP database."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from ..data_source import DataSource
from .policy import AdmError


def _identifier(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        raise AdmError(f"{label}配置不合法", 503, "ADM_REFERENCE_CONFIG")
    return text


class AdmReferenceData:
    def __init__(self, config: dict[str, Any]):
        mysql = dict(config)
        mysql.update(
            DATA_MODE="mysql",
            MYSQL_HOST=config.get("ERP_MYSQL_HOST"),
            MYSQL_PORT=config.get("ERP_MYSQL_PORT", 3306),
            MYSQL_DATABASE=config.get("ADM_REFERENCE_DATABASE") or config.get("ERP_MYSQL_DATABASE") or "sibedb",
            MYSQL_USER=config.get("ERP_MYSQL_USER"),
            MYSQL_PASSWORD=config.get("ERP_MYSQL_PASSWORD"),
            MYSQL_CHARSET=config.get("ERP_MYSQL_CHARSET", "utf8mb4"),
            MYSQL_CONNECT_TIMEOUT=config.get("ERP_MYSQL_CONNECT_TIMEOUT", 10),
            MYSQL_READ_TIMEOUT=config.get("ERP_MYSQL_READ_TIMEOUT", 60),
            MYSQL_WRITE_TIMEOUT=config.get("ERP_MYSQL_WRITE_TIMEOUT", 60),
            MYSQL_POOL_SIZE=config.get("ERP_MYSQL_POOL_SIZE", 4),
            MYSQL_POOL_MIN_CACHED=config.get("ERP_MYSQL_POOL_MIN_CACHED", 1),
        )
        self.source = DataSource(mysql)
        self.database = _identifier(self.source.database, "ADM参考库")
        self.ota_table = _identifier(config.get("ADM_OTA_TABLE", "sibe_ota"), "OTA表")
        self.supplier_table = _identifier(config.get("ADM_SUPPLIER_TABLE", "sibe_supplier"), "供应商表")
        self.exchange_table = _identifier(config.get("ADM_EXCHANGE_RATE_TABLE", "sibe_exchange_rate"), "汇率表")
        self.exchange_source = 6
        actual_source = str(config.get("ADM_EXCHANGE_RATE_ACTUAL_SOURCE") or "").strip()
        self.exchange_actual_source = int(actual_source) if actual_source else None

    def _pairs(self, table: str, code: str, name: str) -> list[dict[str, str]]:
        connection = None
        try:
            import pymysql

            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"SELECT `{code}` code,`{name}` name FROM `{self.database}`.`{table}` "
                    f"WHERE COALESCE(TRIM(`{code}`),'')<>'' AND COALESCE(TRIM(`{name}`),'')<>'' "
                    f"ORDER BY `{name}`,`{code}` LIMIT 5001"
                )
                rows = cursor.fetchall()
            if len(rows) > 5000:
                raise AdmError("ADM参考选项超过5000条，请先治理启用范围", 503, "ADM_REFERENCE_CAPACITY")
            return [
                {
                    "code": str(row["code"]),
                    "name": str(row["name"]),
                    "label": f"{row['code']}/{row['name']}",
                    "exportValue": f"{row['code']}/{row['name']}",
                }
                for row in rows
            ]
        except AdmError:
            raise
        except Exception as error:
            raise AdmError("ADM ERP参考数据暂不可用", 503, "ADM_REFERENCE_UNAVAILABLE") from error
        finally:
            if connection is not None:
                connection.close()

    def options(self) -> dict[str, Any]:
        return {
            "sourceDatabase": self.database,
            "platforms": self._pairs(self.ota_table, "ota_code", "ota_cname"),
            "suppliers": self._pairs(self.supplier_table, "supplier_code", "supplier_cname"),
            "exchangeRateSource": {
                "table": self.exchange_table,
                "configured": True,
                "source": self.exchange_source,
                "actualSource": self.exchange_actual_source,
                "rateColumn": "central_parity_rate",
                "effectiveAtColumn": "update_time",
                "baseCurrency": "CNY",
                "precision": 8,
                "maxAgeHours": None,
                "limitation": "固定使用source=6；导入时取当时最新行并保存不可变快照，不因更新时间阻止建单",
            },
        }

    def rate_snapshot(self, currency: str, at: datetime | None = None) -> dict[str, Any]:
        """Return an immutable, read-only ERP exchange-rate snapshot."""
        code = str(currency or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise AdmError("币种须为三位大写代码")
        zone = ZoneInfo("Asia/Shanghai")
        requested_at = at or datetime.now(zone)
        if requested_at.tzinfo is not None:
            requested_at = requested_at.astimezone(zone).replace(tzinfo=None)
        if code == "CNY":
            return {
                "rate": "1.00000000", "effectiveAt": requested_at.isoformat(timespec="seconds"),
                "rowId": None, "source": "BASE_CURRENCY", "actualSource": None,
                "baseCurrency": "CNY", "exchangeCurrency": "CNY", "rateColumn": "identity",
            }
        connection = None
        try:
            import pymysql

            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute("START TRANSACTION READ ONLY")
                sql = (
                    f"SELECT id,source,actual_source,currency,exchange_currency,central_parity_rate,update_time "
                    f"FROM `{self.database}`.`{self.exchange_table}` "
                    "WHERE source=%s AND data_flag=0 AND currency='CNY' AND exchange_currency=%s "
                    "AND central_parity_rate>0 AND update_time<=%s"
                )
                params: list[Any] = [self.exchange_source, code, requested_at]
                if self.exchange_actual_source is not None:
                    sql += " AND actual_source=%s"
                    params.append(self.exchange_actual_source)
                sql += " ORDER BY update_time DESC,id DESC LIMIT 1"
                cursor.execute(sql, params)
                row = cursor.fetchone()
            connection.rollback()
            if not row:
                raise AdmError(f"{code}没有可用的人民币汇率", 422, "ADM_EXCHANGE_RATE_MISSING")
            effective_at = row["update_time"]
            rate = Decimal(str(row["central_parity_rate"]))
            return {
                "rate": format(rate, ".8f"),
                "effectiveAt": effective_at.isoformat(timespec="seconds"),
                "rowId": str(row["id"]),
                "source": int(row["source"]),
                "actualSource": int(row["actual_source"]) if row["actual_source"] is not None else None,
                "baseCurrency": str(row["currency"]),
                "exchangeCurrency": str(row["exchange_currency"]),
                "rateColumn": "central_parity_rate",
            }
        except AdmError:
            raise
        except Exception as error:
            raise AdmError("ADM汇率参考数据暂不可用", 503, "ADM_EXCHANGE_RATE_UNAVAILABLE") from error
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()
