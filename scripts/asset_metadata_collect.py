"""Read-only metadata inventory using the authorized shared connection objects."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib
import io
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

MYSQL_QUERIES = {
    "tables": "SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE,ENGINE,TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
    "columns": "SELECT TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY,EXTRA,COLUMN_COMMENT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION",
    "keys": "SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,COLUMN_NAME,ORDINAL_POSITION,REFERENCED_TABLE_SCHEMA,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION",
    "indexes": "SELECT TABLE_SCHEMA,TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX",
    "views": "SELECT TABLE_SCHEMA,TABLE_NAME,VIEW_DEFINITION FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
}


def query(connection, sql, params=None):
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params) if params else cursor.execute(sql)
        names = [column[0] for column in cursor.description] if cursor.description else []
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
        raise ValueError("unsupported_identifier")
    return "`" + value + "`"


def mysql(cfg):
    local = copy.copy(cfg)
    local.params = dict(cfg.params or {})
    local.params.update(connect_timeout=8, read_timeout=30, write_timeout=10)
    engine, connection = None, None
    try:
        if hasattr(cfg, "env_source"):
            import pymysql
            connection = pymysql.connect(host=cfg.host, port=cfg.port, user=cfg.user,
                password=cfg.password, database=cfg.database, charset=cfg.charset,
                connect_timeout=8, read_timeout=30, write_timeout=10)
        else:
            engine = local.get_connect()
            connection = engine.raw_connection()
        databases = [str(next(iter(row.values()))) for row in query(connection, "SHOW DATABASES")]
        result = {"visible_databases": databases, "databases": [], "visibility": "current_account_only"}
        for database in sorted(set(databases) - {"mysql", "information_schema", "performance_schema", "sys"}):
            item = {"database": database, "status": "not_visible", "sections": {}}
            if database in databases:
                item["status"] = "complete"
                for name, sql in MYSQL_QUERIES.items():
                    try:
                        records = query(connection, sql, (database,))
                        item["sections"][name] = [view_dependencies(row) for row in records] if name == "views" else records
                    except Exception as error:
                        item["status"] = "partial"
                        item["sections"][name] = {"status": "failed", "error_type": type(error).__name__}
            result["databases"].append(item)
        return result
    finally:
        if connection is not None:
            connection.close()
        if engine is not None:
            engine.dispose()


def view_dependencies(row):
    result = {"database": row["TABLE_SCHEMA"], "table": row["TABLE_NAME"], "status": "definition_unavailable"}
    definition = row.get("VIEW_DEFINITION")
    if not definition:
        return result
    result["definition_sha256"] = hashlib.sha256(definition.encode()).hexdigest()
    try:
        import sqlglot
        from sqlglot import exp
        from sqlglot.optimizer.scope import build_scope
        scope = build_scope(sqlglot.parse_one(definition, read="mysql"))
        if scope is None:
            result["status"] = "unsupported_definition"
            return result
        tables = set()
        for part in scope.traverse():
            for _, source in part.selected_sources.values():
                if isinstance(source, exp.Table):
                    tables.add((source.db or row["TABLE_SCHEMA"], source.name))
        result.update(status="definition_parsed", dependencies=[{"database": db, "table": name} for db, name in sorted(tables)])
    except Exception as error:
        result.update(status="parse_failed", error_type=type(error).__name__)
    return result


def hive(cfg, limit):
    if hasattr(cfg, "env_source"):
        from pyhive import hive as driver
        import socket
        socket.setdefaulttimeout(30)
        connection = driver.connect(host=cfg.host, port=cfg.port, username=cfg.user,
            password=cfg.password or None, database=cfg.database, auth=cfg.auth)
    else:
        from impala.dbapi import connect
        connection = connect(host=cfg.host, port=cfg.port, user=cfg.user,
                             database=cfg.database, auth_mechanism="NOSASL",
                             timeout=15, retries=1)
    try:
        databases = [str(next(iter(row.values()))) for row in query(connection, "SHOW DATABASES")]
        result = {"visible_databases": databases, "databases": [], "visibility": "current_account_only"}
        remaining = limit
        for database in databases:
            item = {"database": database, "status": "complete", "tables": []}
            result["databases"].append(item)
            try:
                tables = query(connection, "SHOW TABLES IN " + identifier(database))
                item["listed_table_count"] = len(tables)
                for row in tables:
                    table = str(next(iter(row.values())))
                    if remaining <= 0:
                        item["status"] = "partial_limit"
                        break
                    remaining -= 1
                    entry = {"table": table, "status": "complete"}
                    item["tables"].append(entry)
                    try:
                        description = query(connection, "DESCRIBE FORMATTED " + identifier(database) + "." + identifier(table))
                        entry.update(hive_description(description))
                    except Exception as error:
                        entry.update(status="failed", error_type=type(error).__name__)
                        item["status"] = "partial"
            except Exception as error:
                item.update(status="failed", error_type=type(error).__name__)
        return result
    finally:
        connection.close()


def hive_description(rows):
    """Keep schema/comments and storage type; exclude owners, locations and properties."""
    columns, partitions, properties = [], [], {}
    partition_section = False
    seen = set()
    for row in rows:
        values = list(row.values())
        name = str(values[0] or "").strip()
        kind = str(values[1] or "").strip() if len(values) > 1 else ""
        comment = str(values[2] or "").strip() if len(values) > 2 else ""
        if name.startswith("# Partition Information"):
            partition_section = True
        if name.startswith("# Detailed Table Information"):
            break
        if name and not name.startswith("#") and kind and (name, kind, partition_section) not in seen:
            entry = {"name": name, "type": kind, "comment": comment}
            (partitions if partition_section else columns).append(entry)
            seen.add((name, kind, partition_section))
    for row in rows:
        values = list(row.values())
        key = str(values[0] or "").strip().rstrip(":")
        if key in {"Table Type", "InputFormat", "OutputFormat", "SerDe Library"}:
            properties[key] = str(values[1] or "").strip()
        if key == "comment":
            properties["comment"] = str(values[1] or "").strip()
        if key == "Location":
            location = urlsplit(str(values[1] or "").strip())
            properties["location_path_sha256"] = hashlib.sha256(location.path.rstrip("/").encode()).hexdigest()
            properties["storage_root_sha256"] = hashlib.sha256((location.scheme + "://" + location.netloc).encode()).hexdigest()
    partition_names = {column["name"] for column in partitions}
    columns = [column for column in columns if column["name"] not in partition_names]
    return {"columns": columns, "partition_columns": partitions, "properties": properties}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etl-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--source", choices=["erp_config", "log_config", "sibebid_config", "hive_engine", "MYSQL", "ERP_MYSQL", "HIVE"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, action="append", default=[])
    parser.add_argument("--hive-table-limit", type=int, default=2000)
    args = parser.parse_args()
    if args.hive_table_limit <= 0:
        parser.error("hive-table-limit must be positive")
    for directory in args.site_packages:
        sys.path.append(str(directory.resolve()))
    if args.etl_root:
        for path in [args.etl_root, args.etl_root / "analysis/scripts"]:
            sys.path.insert(0, str(path.resolve()))
    result = {"source": args.source, "environment": "authorized_connection_environment_unclassified",
              "generated_at": datetime.now(timezone.utc).isoformat(), "status": "failed"}
    # Shared helpers can print connection exceptions. Suppress them; only safe error
    # classes are emitted. No credentials, addresses or exception text are persisted.
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            if args.env_file:
                from dotenv import dotenv_values
                values = dotenv_values(args.env_file)
                prefix = args.source + "_"
                cfg = SimpleNamespace(env_source=args.source, params={},
                    host=values[prefix + "HOST"], port=int(values.get(prefix + "PORT") or (10000 if args.source == "HIVE" else 3306)),
                    user=values[prefix + "USER"], password=values.get(prefix + "PASSWORD") or "",
                    database=values.get(prefix + "DATABASE"), charset=values.get(prefix + "CHARSET") or "utf8mb4",
                    auth=values.get(prefix + "AUTH") or "NONE")
            else:
                module = importlib.import_module("common_libs.config.db_config")
                cfg = getattr(module, args.source)
            identity = str(cfg.host).lower() + ":" + str(cfg.port)
            result["instance_id"] = hashlib.sha256(identity.encode()).hexdigest()[:16]
            result["configured_database"] = cfg.database
            result["metadata"] = hive(cfg, args.hive_table_limit) if args.source in {"hive_engine", "HIVE"} else mysql(cfg)
            result["status"] = "collected"
        except Exception as error:
            result["error_type"] = type(error).__name__
            detail = str(error).lower()
            original = getattr(error, "orig", error)
            if original.args and isinstance(original.args[0], int):
                result["driver_error_code"] = original.args[0]
            result["network_error_codes"] = re.findall(r"(?:winerror|errno)\s*(\d+)", detail)
            result["error_category"] = next((category for marker, category in [
                ("timed out", "network_timeout"), ("10060", "network_timeout"),
                ("10013", "network_permission"), ("10061", "connection_refused"),
                ("getaddrinfo", "name_resolution"), ("access denied", "authentication_denied"),
            ] if marker in detail), "connection_or_dependency_error")
            if isinstance(error, ModuleNotFoundError):
                result["missing_module"] = error.name
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / (args.source + ".json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if result["status"] == "collected":
        # Only a successful complete attempt replaces the previous successful snapshot.
        partial = any(item["status"] != "complete" for item in result["metadata"]["databases"])
        result["coverage"] = "partial" if partial else "complete_for_requested_visible_scope"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if not partial:
            (args.output / (args.source + ".last_success.json")).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ["source", "status", "error_type", "error_category", "missing_module", "coverage"] if key in result}))
    return 0 if result["status"] == "collected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
