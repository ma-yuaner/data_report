"""Manual API refresh reuses the pinned standalone ETL, never shells out to 216."""
from datetime import date

from .data_source import DataSource
from .risk_order_evidence import RiskOrderEvidenceService
from . import risk_order_sync_generated as sync


def refresh_range(config, start, end, progress, prepare_day):
    values = dict(config)
    if values.get("MYSQL_DATABASE") != "sibebid":
        raise ValueError("风控刷新目标须为sibebid")
    values["DATA_MODE"] = "mysql"
    for key in ("CONNECT_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT"):
        values[f"MYSQL_{key}"] = min(max(int(values.get(f"MYSQL_{key}", 20)), 1), 20)
        values[f"ERP_MYSQL_{key}"] = min(max(int(values.get(f"ERP_MYSQL_{key}", 20)), 1), 20)
    source = target = None
    try:
        source = RiskOrderEvidenceService(values)._connect()
        target = DataSource(values).connect()
        return sync.run(source, target, date.fromisoformat(start), date.fromisoformat(end),
                        progress=progress, prepare_day=prepare_day)
    finally:
        # Same source transactions, staging, gates and lock as the standalone ETL.
        # Failed close must not prevent the other connection from being closed.
        import sys
        primary_failure = sys.exc_info()[0] is not None
        complete = sync.close_all([source, target], "close")
        if not complete and not primary_failure:
            raise sync.ETLError("RESOURCE_CLEANUP_FAILED")
