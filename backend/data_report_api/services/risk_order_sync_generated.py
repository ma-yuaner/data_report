# Generated offline from data-team-repo@e5521ed9686bbf453ed0fdee2b326de367f709fc:etl_scripts/automation/risk_verification_order_day_etl.py
# Canonical SHA256: 4322fb2fde8508cce7ede7cb137f3a5f8366a7fff8f0f6ea63328a0cb2fcd86b; do not edit this runtime copy.
#!/usr/bin/env python3
"""ERP只读分批取证索引 -> sibebid风控日查询表；不执行任何业务判断。

显式1-31天，逐日完整重载。只有日staging完成后才事务切换，不清全表。
--preview完全离线；--check-schema仅元数据、普通EXPLAIN，不执行源数据查询。
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import copy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
ZONE = timezone(timedelta(hours=8))
LOCK = "risk_verification_order_day_v1"
DAY = "bi_risk_order_day"
COVERAGE = "bi_risk_sync_day"
RUN = "bi_risk_sync_run"
STAGE = "risk_order_day_stage"
REASON_DICT = "bi_risk_reason_dict"
REASON_PARENT = "PRODUCT_PROFIT_REASON_TYPE"
DICT_FIELDS = {"parent_code", "type_code", "det_code", "det_cname", "update_time"}
COLUMNS = ("issue_date", "order_id", "order_no", "ota_order_no", "ota_code",
           "profit_reason_type", "create_time", "update_time", "etl_run_id")
SOURCE_COLUMNS = {
    "order_info_issue": {"id", "order_id", "issue_ticket_time"},
    "order_info": {"id", "order_no", "ota_order_no", "ota_code", "profit_reason_type", "create_time", "update_time"},
}
TARGET_COLUMNS = {
    DAY: set(COLUMNS),
    COVERAGE: {"issue_date", "etl_run_id", "row_count", "synced_at"},
    RUN: {"etl_run_id", "start_date", "end_date", "status", "started_at", "finished_at", "row_count", "error_code"},
}


class ETLError(ValueError):
    """Only fixed safe error codes are returned to the operator."""


def now():
    return datetime.now(ZONE).replace(tzinfo=None, microsecond=0)


def close_all(resources, method):
    """Try every acquired resource; callers report a fixed cleanup error code."""
    complete = True
    for resource in resources:
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception:
                complete = False
    return complete


def parse_date(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        if parsed.isoformat() != value or parsed == date.max:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError("日期必须为YYYY-MM-DD且可计算次日") from None


def rows(cursor):
    names = [item[0] for item in cursor.description]
    return [dict(row) if isinstance(row, dict) else dict(zip(names, row)) for row in cursor.fetchall()]


def execute_rows(cursor, sql, parameters=()):
    cursor.execute(sql, parameters)
    return rows(cursor)


def date_bounds(day):
    return datetime.combine(day, datetime.min.time()), datetime.combine(day + timedelta(days=1), datetime.min.time())


def issue_query(day, limit, after=None):
    start, end = date_bounds(day)
    where = "issue_ticket_time >= %s AND issue_ticket_time < %s"
    parameters = [start, end]
    if after is not None:
        where += " AND (issue_ticket_time > %s OR (issue_ticket_time = %s AND id > %s))"
        parameters.extend([after[0], after[0], after[1]])
    parameters.append(limit)
    return (f"SELECT id,order_id,issue_ticket_time FROM order_info_issue WHERE {where} "
            "ORDER BY issue_ticket_time,id LIMIT %s"), tuple(parameters)


def schema(cursor, required):
    for table, expected in required.items():
        actual = {row["Field"] for row in execute_rows(cursor, f"SHOW COLUMNS FROM `{table}`")}
        if not expected.issubset(actual):
            raise ETLError("SCHEMA_COLUMNS_MISSING")


def target_types(cursor):
    """CREATE IF NOT EXISTS cannot silently accept an incompatible previous table."""
    fixed = {
        DAY: {"issue_date": r"date", "order_id": r"bigint(?:\(\d+\))?(?: unsigned)?",
              "create_time": r"datetime\(6\)", "update_time": r"datetime\(6\)"},
        COVERAGE: {"issue_date": r"date", "row_count": r"bigint(?:\(\d+\))?(?: unsigned)?", "synced_at": r"datetime(?:\([0-6]\))?"},
        RUN: {"start_date": r"date", "end_date": r"date", "row_count": r"bigint(?:\(\d+\))?(?: unsigned)?",
              "started_at": r"datetime(?:\([0-6]\))?", "finished_at": r"datetime(?:\([0-6]\))?"},
    }
    lengths = {DAY: {"order_no": 128, "ota_order_no": 128, "ota_code": 64, "profit_reason_type": 120, "etl_run_id": 32},
               COVERAGE: {"etl_run_id": 32}, RUN: {"etl_run_id": 32, "status": 16, "error_code": 64}}
    for table in TARGET_COLUMNS:
        fields = {row["Field"]: row for row in execute_rows(cursor, f"SHOW COLUMNS FROM `{table}`")}
        for field, pattern in fixed[table].items():
            if not re.fullmatch(pattern, str(fields[field].get("Type", "")).lower()):
                raise ETLError("TARGET_COLUMN_TYPE_INCOMPATIBLE")
        for field, minimum in lengths[table].items():
            kind = re.fullmatch(r"(?:var)?char\((\d+)\)", str(fields[field].get("Type", "")).lower())
            if not kind or int(kind[1]) < minimum:
                raise ETLError("TARGET_COLUMN_LENGTH_INCOMPATIBLE")


def indexes(cursor, table):
    result = {}
    for row in execute_rows(cursor, f"SHOW INDEX FROM `{table}`"):
        result.setdefault(row["Key_name"], {})[int(row["Seq_in_index"])] = row["Column_name"]
    return {key: tuple(value[position] for position in sorted(value)) for key, value in result.items()}


def require_plan(cursor, sql, parameters, acceptable_keys):
    plans = execute_rows(cursor, "EXPLAIN " + sql, parameters)
    if not plans or not all(row.get("key") in acceptable_keys and row.get("type") in {"range", "ref", "eq_ref", "const"} and "filesort" not in str(row.get("Extra", "")).lower() for row in plans):
        raise ETLError("SOURCE_INDEX_PLAN_UNSAFE")


def validate(source, target, start, end, batch_size):
    database = execute_rows(target, "SELECT DATABASE() AS db")[0]["db"]
    if database != "sibebid":
        raise ETLError("TARGET_DATABASE_MUST_BE_SIBEBID")
    schema(source, SOURCE_COLUMNS)
    schema(target, TARGET_COLUMNS)
    validate_dictionary_schema(source, target)
    target_types(target)
    order_indexes = indexes(source, "order_info")
    if order_indexes.get("PRIMARY") != ("id",):
        raise ETLError("SOURCE_ORDER_PRIMARY_MISSING")
    issue_indexes = indexes(source, "order_info_issue")
    if issue_indexes.get("PRIMARY") != ("id",):
        raise ETLError("SOURCE_ISSUE_PRIMARY_MISSING")
    date_keys = {key for key, columns in issue_indexes.items() if columns and columns[0] == "issue_ticket_time"}
    if not date_keys:
        raise ETLError("SOURCE_ISSUE_DATE_INDEX_MISSING")
    target_indexes = indexes(target, DAY)
    if target_indexes.get("PRIMARY") != ("issue_date", "order_id") or not any(columns[:2] == ("order_id", "issue_date") for columns in target_indexes.values()) or not any(columns[:2] == ("issue_date", "profit_reason_type") for columns in target_indexes.values()):
        raise ETLError("TARGET_DAY_INDEX_MISSING")
    if indexes(target, COVERAGE).get("PRIMARY") != ("issue_date",) or indexes(target, RUN).get("PRIMARY") != ("etl_run_id",):
        raise ETLError("TARGET_PRIMARY_MISSING")
    engines = execute_rows(target, "SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (%s,%s,%s)", (DAY, COVERAGE, RUN))
    if len(engines) != 3 or any(str(row["ENGINE"]).upper() != "INNODB" for row in engines):
        raise ETLError("TARGET_REQUIRES_INNODB")
    source_engines = execute_rows(source, "SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (%s,%s)", ("order_info", "order_info_issue"))
    if len(source_engines) != 2 or any(str(row["ENGINE"]).upper() != "INNODB" for row in source_engines):
        raise ETLError("SOURCE_REQUIRES_SNAPSHOT_CAPABLE_INNODB")
    day = start
    while day <= end:
        sql, parameters = issue_query(day, batch_size)
        require_plan(source, sql, parameters, date_keys)
        # Also gate the keyset continuation shape before any business read.
        sql, parameters = issue_query(day, batch_size, (date_bounds(day)[0], 0))
        require_plan(source, sql, parameters, date_keys)
        day += timedelta(days=1)
    require_plan(source, "SELECT id FROM order_info WHERE id > %s ORDER BY id LIMIT %s", (0, 1), {"PRIMARY"})
    return date_keys


def validate_dictionary_schema(source, target):
    schema(source, {"system_com_type_det": DICT_FIELDS})
    schema(target, {REASON_DICT: {"parent_code", "type_code", "det_code", "det_cname", "source_updated_at", "etl_run_id", "synced_at"}})
    if indexes(target, REASON_DICT).get("PRIMARY") != ("parent_code", "det_code"):
        raise ETLError("TARGET_DICTIONARY_PRIMARY_MISSING")
    fields = {row["Field"]: row for row in execute_rows(target, f"SHOW COLUMNS FROM `{REASON_DICT}`")}
    for field, minimum in (("parent_code", 120), ("type_code", 120), ("det_code", 120), ("det_cname", 500), ("etl_run_id", 32)):
        kind = re.fullmatch(r"(?:var)?char\((\d+)\)", str(fields[field].get("Type", "")).lower())
        if not kind or int(kind[1]) < minimum:
            raise ETLError("TARGET_DICTIONARY_COLUMN_INCOMPATIBLE")
    if str(fields["source_updated_at"].get("Type", "")).lower() != "datetime(6)" or not re.fullmatch(r"datetime(?:\([0-6]\))?", str(fields["synced_at"].get("Type", "")).lower()):
        raise ETLError("TARGET_DICTIONARY_COLUMN_INCOMPATIBLE")
    engine = execute_rows(target, "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (REASON_DICT,))
    if len(engine) != 1 or str(engine[0]["ENGINE"]).upper() != "INNODB":
        raise ETLError("TARGET_DICTIONARY_REQUIRES_INNODB")


def dictionary_rows(source):
    records = execute_rows(source, "SELECT det_code,det_cname,update_time,type_code FROM system_com_type_det WHERE parent_code=%s LIMIT 5001", (REASON_PARENT,))
    if not records:
        raise ETLError("SOURCE_DICTIONARY_EMPTY")
    if len(records) > 5000:
        raise ETLError("SOURCE_DICTIONARY_LIMIT_EXCEEDED")
    mapped = {}
    for row in records:
        code, name = row["det_code"], row["det_cname"]
        if not isinstance(code, str) or not code.strip() or len(code) > 120 or not isinstance(name, str) or not name.strip() or len(name) > 500:
            raise ETLError("SOURCE_DICTIONARY_VALUE_INVALID")
        if code in mapped:
            raise ETLError("SOURCE_DICTIONARY_CODE_DUPLICATED")
        source_type = row.get("type_code")
        if source_type is None:
            source_type = ""
        if not isinstance(source_type, str) or len(source_type) > 120:
            raise ETLError("SOURCE_DICTIONARY_VALUE_INVALID")
        mapped[code] = (code, name.strip(), row.get("update_time"), source_type)
    return list(mapped.values())


def sync_dictionary(source, target, connection, run_id):
    values = dictionary_rows(source)
    connection.commit()
    connection.begin()
    try:
        target.execute(f"DELETE FROM {REASON_DICT} WHERE parent_code=%s", (REASON_PARENT,))
        target.executemany(f"INSERT INTO {REASON_DICT} (parent_code,type_code,det_code,det_cname,source_updated_at,etl_run_id,synced_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           [(REASON_PARENT, source_type, code, name, updated, run_id, now()) for code, name, updated, source_type in values])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return len(values)


def normalize_order(row):
    value = row.get("profit_reason_type")
    if value is None or not str(value).strip(" "):
        return None
    value = str(value)
    if len(value) > 120:
        raise ETLError("SOURCE_REASON_TOO_LONG")
    result = dict(row)
    result["profit_reason_type"] = value
    for key, limit in (("order_no", 128), ("ota_order_no", 128), ("ota_code", 64)):
        if result.get(key) is not None and len(str(result[key])) > limit:
            raise ETLError("SOURCE_FIELD_TOO_LONG")
    return result


def stage_day(source, target, connection, day, run_id, batch_size, max_rows, date_keys, progress=None):
    """Bounded pages; target temporary table absorbs same-order multi-ticket duplicates."""
    target.execute(f"DELETE FROM {STAGE}")
    connection.commit()
    after, seen = None, 0
    while True:
        sql, parameters = issue_query(day, batch_size, after)
        require_plan(source, sql, parameters, date_keys)
        tickets = execute_rows(source, sql, parameters)
        if not tickets:
            break
        seen += len(tickets)
        if progress is not None:
            progress({"phase": "refreshing", "day": day.isoformat(), "sourceRows": seen})
        if seen > max_rows:
            raise ETLError("SOURCE_DAY_ROW_LIMIT_EXCEEDED")
        identifiers = sorted({int(row["order_id"]) for row in tickets if row["order_id"] is not None})
        if len(identifiers) == 0 or any(row["order_id"] is None for row in tickets):
            raise ETLError("SOURCE_ORDER_LINK_MISSING")
        marks = ",".join(["%s"] * len(identifiers))
        query = f"SELECT id,order_no,ota_order_no,ota_code,profit_reason_type,create_time,update_time FROM order_info WHERE id IN ({marks})"
        require_plan(source, query, tuple(identifiers), {"PRIMARY"})
        orders = execute_rows(source, query, tuple(identifiers))
        if len(orders) != len(identifiers):
            raise ETLError("SOURCE_ORDER_LINK_MISSING")
        values = []
        for order in orders:
            order = normalize_order(order)
            if order is not None:
                values.append((day, int(order["id"]), order.get("order_no"), order.get("ota_order_no"), order.get("ota_code"), order["profit_reason_type"], order.get("create_time"), order.get("update_time"), run_id))
        if values:
            updates = ",".join(f"{key}=VALUES({key})" for key in COLUMNS[2:])
            target.executemany(f"INSERT INTO {STAGE} ({','.join(COLUMNS)}) VALUES ({','.join(['%s'] * len(COLUMNS))}) ON DUPLICATE KEY UPDATE {updates}", values)
            connection.commit()
        tail = tickets[-1]
        next_after = (tail["issue_ticket_time"], int(tail["id"]))
        if after is not None and next_after <= after:
            raise ETLError("SOURCE_CURSOR_NOT_ADVANCING")
        after = next_after
        if len(tickets) < batch_size:
            break
    return int(execute_rows(target, f"SELECT COUNT(*) AS n FROM {STAGE}")[0]["n"])


def publish_day(connection, target, day, run_id, expected_rows, before_commit=None):
    connection.commit()
    connection.begin()
    try:
        target.execute(f"DELETE FROM {DAY} WHERE issue_date=%s", (day,))
        target.execute(f"INSERT INTO {DAY} ({','.join(COLUMNS)}) SELECT {','.join(COLUMNS)} FROM {STAGE}")
        actual = int(execute_rows(target, f"SELECT COUNT(*) AS n FROM {DAY} WHERE issue_date=%s", (day,))[0]["n"])
        if actual != expected_rows:
            raise ETLError("PUBLISH_COUNT_MISMATCH")
        target.execute(f"INSERT INTO {COVERAGE} (issue_date,etl_run_id,row_count,synced_at) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE etl_run_id=VALUES(etl_run_id),row_count=VALUES(row_count),synced_at=VALUES(synced_at)", (day, run_id, actual, now()))
        target.execute(f"UPDATE {RUN} SET row_count=row_count+%s WHERE etl_run_id=%s", (actual, run_id))
        if before_commit is not None:
            before_commit(target)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def run(source_connection, target_connection, start, end, batch_size=500, max_rows=2000000, check_only=False, dictionary_only=False, progress=None, prepare_day=None):
    source = target = None
    locked = False
    registered = False
    run_id = uuid.uuid4().hex
    try:
        source, target = source_connection.cursor(), target_connection.cursor()
        source.execute("SET time_zone='+08:00'")
        target.execute("SET time_zone='+08:00'")
        if progress is not None:
            progress({"phase": "checking_schema"})
        date_keys = validate(source, target, start, end, batch_size)
        source_connection.rollback()
        target_connection.rollback()
        if check_only:
            return {"status": "schema_and_plans_checked", "sourceBusinessRowsRead": False}
        lock = execute_rows(target, "SELECT GET_LOCK(%s,0) AS acquired", (LOCK,))[0]["acquired"]
        if lock != 1:
            raise ETLError("ANOTHER_SYNC_IS_RUNNING")
        locked = True
        target.execute(f"INSERT INTO {RUN} (etl_run_id,start_date,end_date,status,started_at,row_count) VALUES (%s,%s,%s,'running',%s,0)", (run_id, start, end, now()))
        target_connection.commit()
        registered = True
        if progress is not None:
            progress({"phase": "refreshing_dictionary"})
        dictionary_count = sync_dictionary(source, target, target_connection, run_id)
        source_connection.rollback()
        if dictionary_only:
            target.execute(f"UPDATE {RUN} SET status='success',finished_at=%s WHERE etl_run_id=%s", (now(), run_id))
            target_connection.commit()
            return {"status": "dictionary_synced", "runId": run_id, "dictionaryRows": dictionary_count, "orderRowsRead": False}
        target.execute(f"CREATE TEMPORARY TABLE {STAGE} LIKE {DAY}")
        target_connection.commit()
        day = start
        total = 0
        while day <= end:
            # Daily repeatable-read snapshot prevents ticket/order page drift within this day.
            source_connection.rollback()
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            source.execute("SET TRANSACTION READ ONLY")
            source.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            count = stage_day(source, target, target_connection, day, run_id, batch_size, max_rows, date_keys, progress)
            publication = prepare_day(source, target, day, run_id) if prepare_day is not None else None
            source_connection.rollback()
            publish_day(target_connection, target, day, run_id, count, publication)
            total += count
            if progress is not None:
                progress({"phase": "refreshing", "day": day.isoformat(), "publishedRows": total})
            print(json.dumps({"day": day.isoformat(), "status": "published", "rows": count}, ensure_ascii=False))
            day += timedelta(days=1)
        target.execute(f"UPDATE {RUN} SET status='success',finished_at=%s WHERE etl_run_id=%s", (now(), run_id))
        target_connection.commit()
        return {"status": "success", "runId": run_id, "rows": total, "dictionaryRows": dictionary_count}
    except Exception as error:
        target_connection.rollback()
        if registered:
            try:
                code = str(error) if isinstance(error, ETLError) else "DATABASE_OPERATION_FAILED"
                target.execute(f"UPDATE {RUN} SET status='failed',finished_at=%s,error_code=%s WHERE etl_run_id=%s", (now(), code, run_id))
                target_connection.commit()
            except Exception:
                target_connection.rollback()
        raise
    finally:
        had_error = sys.exc_info()[0] is not None
        complete = close_all([source_connection], "rollback")
        if locked:
            try:
                target.execute("SELECT RELEASE_LOCK(%s)", (LOCK,))
            except Exception:
                complete = False
        complete = close_all([source, target], "close") and complete
        if not complete and not had_error:
            raise ETLError("RESOURCE_CLEANUP_FAILED")


def open_connections():
    """Use the existing public connector, preserving its encoded credentials/params."""
    for directory in (ROOT, ROOT / "analysis" / "scripts"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from common_libs.config.db_config import erp_config, sibebid_config
    engines, connections = [], []
    try:
        if sibebid_config.database != "sibebid":
            raise ETLError("TARGET_DATABASE_MUST_BE_SIBEBID")
        if (erp_config.host, erp_config.port, erp_config.database) == (sibebid_config.host, sibebid_config.port, sibebid_config.database):
            raise ETLError("SOURCE_TARGET_MUST_DIFFER")
        for config in (erp_config, sibebid_config):
            local_config = copy(config)
            local_config.params = dict(config.params or {})
            local_config.params.update(connect_timeout=5, read_timeout=20, write_timeout=20)
            local_config.params.setdefault("charset", "utf8mb4")
            # The shared helper prints raw connection exceptions. Do not expose them.
            with redirect_stdout(_QuietOutput()), redirect_stderr(_QuietOutput()):
                engine = local_config.get_connect()
                engines.append(engine)
                connections.append(engine.raw_connection())
        return engines, connections
    except Exception:
        close_all(connections, "close")
        close_all(engines, "dispose")
        raise


class _QuietOutput:
    """Discard connector diagnostics without retaining credentials in a buffer."""
    def write(self, value):
        return len(value)

    def flush(self):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=parse_date)
    parser.add_argument("--end-date", required=True, type=parse_date)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-source-rows", type=int, default=2000000)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preview", action="store_true")
    modes.add_argument("--check-schema", action="store_true")
    modes.add_argument("--dictionary-only", action="store_true", help="只同步盈亏原因字典，不读取订单业务数据")
    args = parser.parse_args(argv)
    if args.start_date > args.end_date or (args.end_date - args.start_date).days > 30:
        parser.error("日期范围必须为1至31天")
    if not 1 <= args.batch_size <= 2000 or not 1 <= args.max_source_rows <= 10000000:
        parser.error("batch-size须1至2000；max-source-rows须1至10000000")
    if args.preview:
        print(json.dumps({"mode": "offline_preview", "target": "sibebid", "startDate": args.start_date.isoformat(), "endDate": args.end_date.isoformat(), "tables": [*TARGET_COLUMNS, REASON_DICT], "publication": "per_day_atomic_replace", "batchSize": args.batch_size, "sourceQueriesExecuted": False}, ensure_ascii=False))
        return 0
    engines, connections = [], []
    error_code = None
    result = None
    try:
        engines, connections = open_connections()
        result = run(*connections, args.start_date, args.end_date, args.batch_size, args.max_source_rows, args.check_schema, args.dictionary_only)
    except Exception as error:
        if isinstance(error, ETLError):
            error_code = str(error)
        elif isinstance(error, ImportError):
            error_code = "RUNTIME_DEPENDENCY_MISSING"
        else:
            error_code = "DATABASE_OPERATION_FAILED"
    finally:
        complete = close_all(connections, "close")
        complete = close_all(engines, "dispose") and complete
        if not complete and error_code is None:
            error_code = "RESOURCE_CLEANUP_FAILED"
    if error_code is not None:
        print(json.dumps({"status": "failed", "errorCode": error_code, "action": "停止；核对错误码及已发布批次，勿清表或盲目重试"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
