"""Read only the BI catalog; never fall back to ERP on missing/stale data."""
from datetime import timedelta

from .data_source import DataSource
from .risk_order_evidence import EvidenceError, RiskOrderEvidenceService, _rows


class RiskVerificationCatalog:
    def __init__(self, config, source=None):
        self.config = config
        self.source = source

    def _connect(self):
        if self.source is None:
            if self.config.get("MYSQL_DATABASE") != "sibebid":
                raise EvidenceError("风控目录须配置MYSQL_DATABASE=sibebid，不回退ERP直查", 503)
            values = {**self.config, "DATA_MODE": "mysql"}
            # Request budgets are local to this reader, not a change to shared settings.
            for key in ("CONNECT_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT"):
                values[f"MYSQL_{key}"] = min(max(int(values.get(f"MYSQL_{key}", 8)), 1), 8)
            self.source = DataSource(values)
        connection = self.source.connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("START TRANSACTION READ ONLY")
            finally:
                cursor.close()
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def coverage(cursor, first, last):
        cursor.execute("SELECT issue_date,etl_run_id,row_count,synced_at FROM bi_risk_sync_day WHERE issue_date >= %s AND issue_date <= %s ORDER BY issue_date", (first.isoformat(), last.isoformat()))
        rows = _rows(cursor)
        seen = {str(row["issue_date"]): row for row in rows}
        expected = [(first + timedelta(days=index)).isoformat() for index in range((last - first).days + 1)]
        missing = [day for day in expected if day not in seen]
        if missing:
            raise EvidenceError("风控目录未同步出票日期：" + ",".join(missing) + "；请点击更新并核实，未同步不代表零订单", 409, "RISK_CATALOG_NOT_SYNCED")
        cursor.execute("""SELECT order_id FROM bi_risk_order_day
            WHERE issue_date >= %s AND issue_date <= %s GROUP BY order_id
            HAVING COUNT(DISTINCT CAST(profit_reason_type AS BINARY)) > 1
                OR COUNT(DISTINCT update_time) > 1
                OR (COUNT(update_time)>0 AND COUNT(update_time)<COUNT(*)) LIMIT 1""",
                       (first.isoformat(), last.isoformat()))
        if cursor.fetchall():
            raise EvidenceError("所选出票日期存在同一订单的不同源版本，请重跑完整日期范围后再核查；不能沿用旧版本结论", 409)
        cursor.execute("SELECT status,started_at,finished_at,error_code FROM bi_risk_sync_run WHERE start_date <= %s AND end_date >= %s ORDER BY started_at DESC,etl_run_id DESC LIMIT 1", (last.isoformat(), first.isoformat()))
        attempts = _rows(cursor)
        times = [str(row["synced_at"]) for row in rows]
        return {"source": "sibebid", "mode": "etl_catalog", "complete": True,
                "oldestSyncedAt": min(times), "newestSyncedAt": max(times),
                "days": rows, "latestAttempt": attempts[0] if attempts else None}

    @staticmethod
    def reason_labels(cursor):
        cursor.execute("SELECT det_code,det_cname,etl_run_id FROM bi_risk_reason_dict WHERE parent_code=%s LIMIT 5001", ("PRODUCT_PROFIT_REASON_TYPE",))
        rows = _rows(cursor)
        labels = {}
        versions = {row["etl_run_id"] for row in rows}
        for row in rows:
            if row["det_code"] in labels or not row["det_cname"]:
                raise EvidenceError("盈亏原因字典存在重复或空名称，请重新同步字典", 409)
            labels[row["det_code"]] = row["det_cname"]
        if len(rows) > 5000 or len(versions) > 1:
            raise EvidenceError("盈亏原因字典批次不完整，请重新同步字典", 409)
        return labels, next(iter(versions), "")

    @staticmethod
    def _close(cursor, connection):
        if connection is not None:
            try:
                connection.rollback()
            finally:
                RiskOrderEvidenceService._close(cursor, connection)
