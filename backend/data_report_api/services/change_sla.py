"""Read-only ERP change SLA data, one row per source document."""
from datetime import date, datetime, time, timedelta, timezone

from .data_source import DataSource

BUSINESS_ZONE = timezone(timedelta(hours=8))
ROW_LIMIT = 5000

AUDIT_SQL = """
SELECT a.id, a.create_time, a.apply_time,
       CASE WHEN a.audit_flag IN (1,2) THEN a.audit_operator_time END,
       a.audit_flag, a.ota_code, a.marketing_airline, a.audit_operator_name, a.change_category,
       (SELECT COUNT(DISTINCT c.id) FROM ext_order_change_extend e
        JOIN order_change c ON c.id=e.change_id WHERE e.change_audit_id=a.id)
FROM (
    SELECT id, create_time, apply_time, audit_operator_time, audit_flag, ota_code, marketing_airline, audit_operator_name, change_category
    FROM order_change_audit WHERE create_time >= %s AND create_time < %s
    ORDER BY create_time, id LIMIT %s
) a

"""

OPERATION_SQL = """
SELECT c.id, c.create_time,
       (SELECT MAX(h.create_time) FROM order_change_status_history h
        WHERE h.change_id=c.id AND h.change_status='HANDLE'),
       (SELECT MAX(h.create_time) FROM order_change_status_history h
        WHERE h.change_id=c.id AND h.change_status='ACCEPT'),
       c.change_status, c.ota_code, c.marketing_airline, c.change_operator, c.change_category,
       (SELECT COUNT(DISTINCT a.id) FROM ext_order_change_extend e
        JOIN order_change_audit a ON a.id=e.change_audit_id WHERE e.change_id=c.id),
       c.latest_issue_time
FROM (
    SELECT id, create_time, change_status, ota_code, marketing_airline, latest_issue_time, change_operator, change_category
    FROM order_change WHERE create_time >= %s AND create_time < %s
    ORDER BY create_time, id LIMIT %s
) c

"""


class ChangeSlaQueryError(ValueError):
    pass


def _epoch(value):
    return int(value.replace(tzinfo=BUSINESS_ZONE).timestamp() * 1000) if value is not None else None


def _date_range(start, end, today):
    if start is None and end is None:
        return today, today
    try:
        first, last = date.fromisoformat(start or ""), date.fromisoformat(end or "")
    except ValueError:
        raise ChangeSlaQueryError("请选择有效的创建日期范围") from None
    if last < first or (last - first).days >= 31 or last > today:
        raise ChangeSlaQueryError("创建日期范围须在最近可查日期内，单次最多 31 天，截止日期不能晚于今天")
    return first, last


def _audit(row):
    identifier, created, start, end, flag, platform, airline, owner, category, linked = row
    terminal = {0: "pending", 1: "completed", 2: "completed", 3: "withdrawn"}.get(flag, "unknown")
    return _record(identifier, created, start, end, flag, platform, airline, owner, category, linked,
                   terminal, "audit_operator_time" if end is not None else "")


def _operation(row):
    identifier, created, start, accepted, status, platform, airline, owner, category, linked, issued = row
    terminal = {"HANDLE": "pending", "ACCEPT": "completed", "REPULSE": "rejected"}.get(status, "unknown")
    end, end_source = None, ""
    if status == "ACCEPT":
        if accepted is not None:
            end, end_source = accepted, "ACCEPT"
        elif start is not None and issued is not None and issued >= start:
            end, end_source = issued, "latest_issue_time"
    return _record(identifier, created, start, end, status, platform, airline, owner, category, linked, terminal, end_source)


def _record(identifier, created, start, end, status, platform, airline, owner, category, linked, terminal, end_source):
    return {
        "id": str(identifier), "created": created.date().isoformat(), "start": _epoch(start), "end": _epoch(end),
        "sourceStatus": str(status), "platform": platform or "未知平台", "air": airline or "未知航司",
        "owner": (owner or "").strip() or "未记录", "kind": {0: "改期", 1: "改名", 2: "改证件"}.get(category, "未分类"), "linked": linked, "terminal": terminal, "endSource": end_source,
    }


def _rules(config):
    rules = []
    for key, node in (("AUDIT", "改期审核"), ("OPERATION", "改期操作")):
        value = str(config.get(f"CHANGE_SLA_{key}_MINUTES") or "").strip()
        if value.isdecimal() and 1 <= int(value) <= 14400:
            rules.append({"id": f"ERP-{key}", "node": node, "kind": "*", "air": "*", "minutes": int(value), "priority": 10})
    return rules


def read_change_sla(config, start, end, *, source=None):
    if source is None:
        keys = ("HOST", "PORT", "DATABASE", "USER", "PASSWORD", "CHARSET", "CONNECT_TIMEOUT",
                "READ_TIMEOUT", "WRITE_TIMEOUT", "POOL_SIZE", "POOL_MIN_CACHED")
        if any(not config.get(f"ERP_MYSQL_{key}") for key in ("HOST", "DATABASE", "USER")):
            raise RuntimeError("ERP configuration unavailable")
        erp = {f"MYSQL_{key}": config[f"ERP_MYSQL_{key}"] for key in keys if f"ERP_MYSQL_{key}" in config}
        source = DataSource({**erp, "DATA_MODE": "mysql", "MYSQL_TIME_ZONE": "+08:00"})
    first, last = _date_range(start, end, datetime.now(BUSINESS_ZONE).date())
    bounds = (datetime.combine(first, time.min), datetime.combine(last + timedelta(days=1), time.min), ROW_LIMIT + 1)
    connection = source.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            cursor.execute("SELECT NOW()")
            snapshot = _epoch(cursor.fetchone()[0])
            records = {}
            for key, sql, convert in (("audit", AUDIT_SQL, _audit), ("operation", OPERATION_SQL, _operation)):
                cursor.execute(sql, bounds)
                rows = cursor.fetchall()
                if len(rows) > ROW_LIMIT:
                    raise ChangeSlaQueryError("当前时段单节点超过 5,000 条，请缩短创建日期范围后重试")
                records[key] = [convert(row) for row in rows]
            return {"snapshot": snapshot, "dates": [first.isoformat(), last.isoformat()], "records": records, "rules": _rules(config)}
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
