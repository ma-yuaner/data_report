"""Serve the ETL completion-date facts without opening an ERP connection."""
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

from .change_sla import BUSINESS_ZONE, ROW_LIMIT, ChangeSlaQueryError, _date_range
from .data_source import DataSource


class ChangeSlaSnapshotUnavailable(RuntimeError):
    pass


@contextmanager
def _snapshot_reader(config):
    local_path = config.get("CHANGE_SLA_SNAPSHOT_PATH")
    if local_path:
        path = Path(local_path).resolve()
        if not path.is_file():
            raise ChangeSlaSnapshotUnavailable("改签报表尚未完成首次同步")
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=5)) as db:
            db.execute("BEGIN")
            yield db.execute
        return

    source = DataSource({**config, "DATA_MODE": "mysql"})
    with closing(source.connect()) as db, closing(db.cursor()) as cursor:
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        try:
            def execute(sql, params):
                sql = sql.replace("change_sla_facts", "bi_change_sla_fact").replace(
                    "change_sla_coverage", "bi_change_sla_coverage"
                ).replace("?", "%s")
                cursor.execute(sql, params)
                return cursor
            try:
                yield execute
            except Exception as exc:
                if exc.args and exc.args[0] == 1146:
                    raise ChangeSlaSnapshotUnavailable("改签报表尚未建表或完成首次同步") from exc
                raise
        finally:
            db.rollback()


def read_reporting_snapshot(config, start, end, node):
    if node not in ("audit", "operation"):
        raise ChangeSlaQueryError("请选择改期审核或改期操作")
    today = datetime.now(BUSINESS_ZONE).date()
    if start is not None or end is not None:
        first, last = _date_range(start, end, today)
    with _snapshot_reader(config) as execute:
        latest = execute(
            "SELECT MAX(business_date) FROM change_sla_coverage WHERE node=? AND business_date<=?",
            (node, today.isoformat()),
        ).fetchone()[0]
        if not latest:
            raise ChangeSlaSnapshotUnavailable("当前节点尚未完成首次同步")
        latest = str(latest)
        if start is None and end is None:
            first, last = _date_range(latest, latest, today)
        bounds = (node, first.isoformat(), last.isoformat())
        coverage = {str(day): (count, cutoff) for day, count, cutoff in execute(
            "SELECT business_date, row_count, snapshot_ms FROM change_sla_coverage WHERE node=? AND business_date BETWEEN ? AND ?",
            bounds,
        ).fetchall()}
        if not coverage:
            raise ChangeSlaSnapshotUnavailable("所选日期尚未同步，请查询已同步日期")
        expected = sum(count for count, _ in coverage.values())
        if expected > ROW_LIMIT:
            raise ChangeSlaQueryError("当前范围单节点超过 5,000 条，请缩短日期后查询")
        facts = execute("""
            SELECT f.payload
            FROM change_sla_facts f
            JOIN change_sla_coverage c ON c.node=f.node AND c.business_date=f.business_date
            WHERE f.node=? AND f.business_date BETWEEN ? AND ?
            ORDER BY f.business_date DESC, f.source_id DESC LIMIT ?
        """, (*bounds, ROW_LIMIT+1)).fetchall()
        if len(facts) != expected:
            raise ChangeSlaSnapshotUnavailable("报表覆盖记录与明细不一致，请联系数据团队核对同步批次")
    days = [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    records = {"audit": [], "operation": []}
    for row in facts:
        record = json.loads(row[0])
        record.setdefault("ruleDecision", {
            "source": "pending", "minutes": None, "version": "",
            "detail": "该批次尚未匹配平台规则",
        })
        records[node].append(record)
    return {
        "snapshot": max(cutoff for _, cutoff in coverage.values()),
        "dates": [first.isoformat(), last.isoformat()],
        "records": records,
        "rules": [
            {"id": "FALLBACK-AUDIT", "node": "改期审核", "minutes": 60},
            {"id": "FALLBACK-OPERATION", "node": "改期操作", "minutes": 90},
        ],
        "coverage": {"missingDates": [day for day in days if day not in coverage], "latestCoveredDate": latest},
    }
