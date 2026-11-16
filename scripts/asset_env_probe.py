"""Test .env database connections using TCP, SELECT 1 and SHOW DATABASES only."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path


def probe(env_file, source):
    from dotenv import dotenv_values
    values = dotenv_values(env_file)
    prefix = source + "_"
    result = {"source": source, "stage": "configuration", "status": "failed"}
    started = time.monotonic()
    connection = None
    try:
        host, user = values.get(prefix + "HOST"), values.get(prefix + "USER")
        if not host or not user:
            result["status"] = "not_configured"
            return result
        port = int(values.get(prefix + "PORT") or (10000 if source == "HIVE" else 3306))
        result["stage"] = "tcp"
        with socket.create_connection((host, port), timeout=6):
            pass
        result["tcp"] = "passed"
        result["stage"] = "database_session"
        if source == "HIVE":
            from pyhive import hive
            socket.setdefaulttimeout(8)
            connection = hive.connect(host=host, port=port, username=user,
                                      password=values.get(prefix + "PASSWORD") or None,
                                      database=values.get(prefix + "DATABASE") or "default",
                                      auth=values.get(prefix + "AUTH") or "NONE")
        else:
            import pymysql
            connection = pymysql.connect(host=host, port=port, user=user,
                password=values.get(prefix + "PASSWORD") or "",
                database=values.get(prefix + "DATABASE") or None,
                charset=values.get(prefix + "CHARSET") or "utf8mb4",
                connect_timeout=6, read_timeout=8, write_timeout=8)
        cursor = connection.cursor()
        try:
            result["stage"] = "select_one"
            cursor.execute("SELECT 1")
            result["select_one"] = "passed" if cursor.fetchone()[0] == 1 else "unexpected_result"
            result["stage"] = "metadata"
            cursor.execute("SHOW DATABASES")
            result["visible_databases"] = [str(row[0]) for row in cursor.fetchall()]
            result["configured_database"] = values.get(prefix + "DATABASE")
            result.update(status="passed", stage="complete")
        finally:
            cursor.close()
    except Exception as error:
        result["error_type"] = type(error).__name__
        for key in ("errno", "winerror"):
            code = getattr(error, key, None)
            if isinstance(code, int):
                result[key] = code
        if error.args and isinstance(error.args[0], int):
            result["driver_code"] = error.args[0]
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                connection.close()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--source", choices=["MYSQL", "ERP_MYSQL", "HIVE"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.append(str(args.site_packages.resolve()))
    logging.disable(logging.CRITICAL)
    if args.source:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = probe(args.env_file, args.source)
        print(json.dumps(result, ensure_ascii=True))
        return
    results = []
    for source in ("MYSQL", "ERP_MYSQL", "HIVE"):
        command = [sys.executable, str(Path(__file__).resolve()), "--env-file", str(args.env_file.resolve()),
                   "--site-packages", str(args.site_packages.resolve()), "--source", source]
        try:
            child = subprocess.run(command, capture_output=True, text=True, timeout=30)
            result = json.loads(child.stdout) if child.returncode == 0 else {"source": source, "status": "probe_process_failed"}
        except subprocess.TimeoutExpired:
            result = {"source": source, "status": "timeout", "timeout_seconds": 30}
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
