"""Explicit, non-destructive migration of legacy automatic risk records only.

Default/--preview reads SQLite counts and never opens a MySQL connection.
--apply requires --source-stopped: stop all legacy writers before using it and
keep both legacy and new writers stopped until successful migration/cutover.
--archive-only preserves legacy history separately and never writes MySQL rows.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .risk_auto_store import COLUMNS, RiskAutoStore, StoreConflict


class MigrationConflict(RuntimeError):
    """Target content or order differs; the complete transaction is rolled back."""


def _open_readonly(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _tables(connection):
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return [table for table in COLUMNS if table in names]


def preview(root):
    """Safe summary: no record identifiers, owners, bodies, or credentials."""
    with closing(_open_readonly(Path(root) / "workflow.sqlite3")) as source:
        source.execute("BEGIN")
        tables = _tables(source)
        counts = {table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  if table in tables else 0 for table in COLUMNS}
        active = source.execute("SELECT COUNT(*) FROM auto_jobs WHERE status IN ('queued','running')").fetchone()[0] if "auto_jobs" in tables else 0
        return {"mode": "preview", "counts": counts, "activeJobsToFail": active, "mysqlConnected": False}


def _backup(root):
    root = Path(root).resolve()
    folder = root / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"risk-auto-migration-{uuid.uuid4().hex}.sqlite3"
    # SQLite backup includes a consistent committed snapshot, including WAL data.
    with closing(_open_readonly(root / "workflow.sqlite3")) as source:
        with closing(sqlite3.connect(str(backup))) as target:
            source.backup(target)
    return backup


def _normalized(table, row):
    values = {column: row[column] for column in COLUMNS[table]}
    # MySQL deployments may use a permissive sql_mode. Reject values that could
    # otherwise be truncated/coerced silently, before reporting a successful copy.
    patterns = {"id": r"[0-9a-f]{32}", "owner": r"[0-9]{1,19}",
                "result_id": r"[0-9a-f]{32}", "order_id": r"[0-9]{1,19}",
                "status": r"[a-z_]{1,16}"}
    for column, pattern in patterns.items():
        if column in values and (not isinstance(values[column], str) or not re.fullmatch(pattern, values[column])):
            raise MigrationConflict("Legacy field does not fit the target schema")
    for column in ("updated", "created"):
        if column in values and (type(values[column]) not in {int, float} or not math.isfinite(values[column])):
            raise MigrationConflict("Legacy timestamp is not a finite number")
    if not isinstance(values["body"], str):
        raise MigrationConflict("Legacy body must be text")
    if table == "auto_jobs" and values["status"] in {"queued", "running"}:
        body = json.loads(values["body"])
        if not isinstance(body, dict):
            raise MigrationConflict("Legacy active job body must be a JSON object")
        body.update(status="failed", migrationNote="旧SQLite任务迁移时终止；未恢复执行，请通过刷新核对重新启动")
        values.update(status="failed", body=json.dumps(body, ensure_ascii=False))
    return values


def apply(config, *, source_stopped=False, store=None):
    """Copy one backup snapshot in one transaction; never delete/update the source."""
    if not source_stopped:
        raise ValueError("Stop all old API/workers and acknowledge with --source-stopped")
    root = Path(config.get("RISK_VERIFICATION_ROOT") or "/app/var/risk-verification")
    backup = _backup(root)
    hasher = hashlib.sha256()
    with backup.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    counts = {table: {"inserted": 0, "skipped": 0} for table in COLUMNS}
    failed = 0
    target = store if store is not None else RiskAutoStore(config)
    with closing(_open_readonly(backup)) as source:
        source.execute("BEGIN")
        tables = _tables(source)
        with target.db() as db:
            for table, columns in COLUMNS.items():
                rows = source.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY rowid").fetchall() if table in tables else []
                # Require an exact prefix to avoid assigning a newer seq to older
                # history on a partial import, or mixing live target/source data.
                existing = db.execute(f"SELECT id FROM {table} ORDER BY rowid FOR UPDATE").fetchall()
                if [row["id"] for row in existing] != [row["id"] for row in rows[:len(existing)]]:
                    raise MigrationConflict("Target order/content is not a prefix of the source snapshot")
                for row in rows:
                    values = _normalized(table, row)
                    if table == "auto_jobs" and row["status"] in {"queued", "running"}:
                        failed += 1
                    current = db.execute(f"SELECT {','.join(columns)} FROM {table} WHERE id=? FOR UPDATE", (values["id"],)).fetchone()
                    if current is not None:
                        if any(current[column] != values[column] for column in columns):
                            raise MigrationConflict("Matching target ID has different field content")
                        counts[table]["skipped"] += 1
                        continue
                    try:
                        db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(values[column] for column in columns))
                    except StoreConflict as error:
                        raise MigrationConflict("Concurrent or conflicting target write; migration rolled back") from error
                    counts[table]["inserted"] += 1
    return {"mode": "apply", "counts": counts, "activeJobsFailed": failed, "backupCreated": True, "backupSha256": digest}


def archive(config, *, source_stopped=False, store=None):
    """Keep legacy history separately; check MySQL readiness using SELECT only."""
    if not source_stopped:
        raise ValueError("Stop all legacy writers and acknowledge with --source-stopped")
    root = Path(config.get("RISK_VERIFICATION_ROOT") or "/app/var/risk-verification")
    backup = _backup(root)
    backup.chmod(0o600)
    with closing(_open_readonly(backup)) as source:
        source.execute("BEGIN")
        checks = source.execute("PRAGMA integrity_check").fetchall()
        if len(checks) != 1 or checks[0][0] != "ok":
            raise MigrationConflict("Legacy backup integrity check failed")
        tables = _tables(source)
        counts = {table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  if table in tables else 0 for table in COLUMNS}
    hasher = hashlib.sha256()
    with backup.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    target_counts = {}
    target = store if store is not None else RiskAutoStore(config)
    with target.db() as db:
        for table, columns in COLUMNS.items():
            db.execute(f"SELECT rowid,{','.join(columns)} FROM {table} LIMIT 0").fetchall()
            target_counts[table] = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    report = {"mode": "archive_only", "counts": counts, "targetCounts": target_counts,
              "targetModified": False, "legacyImported": False, "backupCreated": True,
              "backupFile": backup.name, "backupSha256": digest}
    manifest = backup.with_suffix(".json")
    content = {**report, "schemaVersion": 1, "createdAt": datetime.now(timezone.utc).isoformat()}
    with manifest.open("x", encoding="utf-8") as output:
        manifest.chmod(0o600)
        json.dump(content, output, ensure_ascii=False, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    report["manifestFile"] = manifest.name
    return report


def failure_details(error):
    """Only fixed reason codes and numeric driver codes; no exception text."""
    conflicts = {
        "Target order/content is not a prefix of the source snapshot": "TARGET_HISTORY_CONFLICT",
        "Matching target ID has different field content": "SAME_ID_DIFFERENT_CONTENT",
        "Legacy backup integrity check failed": "BACKUP_INTEGRITY_FAILED",
    }
    code = conflicts.get(str(error), "MIGRATION_CONFLICT") if isinstance(error, MigrationConflict) else "STORAGE_OR_BACKUP_FAILED"
    if isinstance(error, PermissionError):
        code = "BACKUP_PERMISSION_DENIED"
    current, seen = error, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        args = getattr(current, "args", ())
        if args and type(args[0]) is int:
            return {"errorCode": code, "dbCode": args[0]}
        current = current.__cause__ or current.__context__
    return {"errorCode": code}


def main(argv=None, config=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Default: SQLite safe counts only, no MySQL")
    mode.add_argument("--apply", action="store_true", help="Backup and migrate auto_* to pre-created sibebid tables")
    mode.add_argument("--archive-only", action="store_true", help="Archive legacy SQLite separately; never write MySQL records")
    parser.add_argument("--source-stopped", action="store_true", help="Confirm all legacy API/automatic-task writers are stopped")
    args = parser.parse_args(argv)
    if (args.apply or args.archive_only) and not args.source_stopped:
        parser.error("--apply/--archive-only requires --source-stopped")
    if config is None:
        from ..config import Config
        config = {name: getattr(Config, name) for name in dir(Config) if name.isupper()}
    try:
        if args.archive_only:
            report = archive(config, source_stopped=args.source_stopped)
        else:
            report = apply(config, source_stopped=args.source_stopped) if args.apply else preview(config.get("RISK_VERIFICATION_ROOT") or "/app/var/risk-verification")
    except Exception as error:
        # Do not leak DB driver errors/SQL parameters, source bodies or credentials.
        print(json.dumps({"status": "failed", **failure_details(error), "message": "Migration/archive aborted; preserve backup and investigate locally; no successful cutover reported"}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
