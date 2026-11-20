"""Serve the ETL completion-date facts without opening an ERP connection."""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

from .change_sla import BUSINESS_ZONE, ROW_LIMIT, ChangeSlaQueryError, _date_range


class ChangeSlaSnapshotUnavailable(RuntimeError):
    pass


def read_reporting_snapshot(config, start, end, node):
    if node not in ("audit", "operation"):
        raise ChangeSlaQueryError("请选择改期审核或改期操作")
    today = datetime.now(BUSINESS_ZONE).date()
    if start is not None or end is not None:
        first, last = _date_range(start, end, today)
    root = Path(config["DATA_WORKBENCH_DIR"])
    path = Path(config.get("CHANGE_SLA_SNAPSHOT_PATH") or root / "change-sla-facts.sqlite3").resolve()
    if not path.is_file():
        raise ChangeSlaSnapshotUnavailable("改签报表尚未完成首次同步")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=5)) as db:
        db.execute("BEGIN")
        latest = db.execute(
            "SELECT MAX(business_date) FROM change_sla_coverage WHERE node=? AND business_date<=?",
            (node, today.isoformat()),
        ).fetchone()[0]
        if not latest:
            raise ChangeSlaSnapshotUnavailable("当前节点尚未完成首次同步")
        if start is None and end is None:
            first, last = _date_range(latest, latest, today)
        bounds = (node, first.isoformat(), last.isoformat())
        coverage = {day: (count, cutoff) for day, count, cutoff in db.execute(
            "SELECT business_date, row_count, snapshot_ms FROM change_sla_coverage WHERE node=? AND business_date BETWEEN ? AND ?",
            bounds,
        )}
        if not coverage:
            raise ChangeSlaSnapshotUnavailable("所选日期尚未同步，请查询已同步日期")
        expected = sum(count for count, _ in coverage.values())
        if expected > ROW_LIMIT:
            raise ChangeSlaQueryError("当前范围单节点超过 5,000 条，请缩短日期后查询")
        facts = db.execute("""
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
