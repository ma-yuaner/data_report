"""Atomic aggregate storage. Production schema is installed separately by an operator."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager


class StoreUnavailable(Exception):
    pass


class Conflict(Exception):
    pass


class AdmStore:
    def __init__(self, config):
        self.config = config
        self.mode = str(config.get("ADM_STORAGE_MODE", "mysql")).lower()
        if self.mode not in {"mysql", "sqlite"}:
            raise StoreUnavailable("ADM持久化模式无效")
        if self.mode == "sqlite" and (not config.get("TESTING") or not config.get("ADM_SQLITE_PATH")):
            raise StoreUnavailable("SQLite仅允许显式TESTING隔离验收并指定ADM_SQLITE_PATH")

    @contextmanager
    def connection(self):
        conn = None
        try:
            if self.mode == "sqlite":
                conn = sqlite3.connect(self.config["ADM_SQLITE_PATH"], timeout=15)
                conn.execute("PRAGMA busy_timeout=15000")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS adm_case_document (id TEXT PRIMARY KEY, version INTEGER NOT NULL, idempotency_key TEXT UNIQUE, payload TEXT NOT NULL)"
                )
            else:
                import pymysql

                def option(name, default=None):
                    return self.config.get("ADM_MYSQL_" + name) or self.config.get("MYSQL_" + name, default)

                if not option("HOST") or not option("USER"):
                    raise StoreUnavailable("ADM MySQL连接尚未配置")
                conn = pymysql.connect(
                    host=option("HOST"),
                    port=int(option("PORT", 3306)),
                    user=option("USER"),
                    password=option("PASSWORD", ""),
                    database=option("DATABASE"),
                    charset="utf8mb4",
                    connect_timeout=5,
                    read_timeout=15,
                    write_timeout=15,
                    autocommit=False,
                )
            yield conn
            conn.commit()
        except (Conflict, StoreUnavailable):
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            raise StoreUnavailable("ADM存储不可用，请检查连接及已执行的DDL") from exc
        finally:
            if conn:
                conn.close()

    def query(self, conn, sql, params=()):
        cursor = conn.cursor()
        cursor.execute(sql.replace("?", "%s") if self.mode == "mysql" else sql, params)
        return cursor

    def all(self):
        with self.connection() as conn:
            rows = self.query(conn, "SELECT payload FROM adm_case_document").fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, case_id):
        with self.connection() as conn:
            row = self.query(conn, "SELECT payload FROM adm_case_document WHERE id=?", (case_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def create(self, case, key=None):
        with self.connection() as conn:
            if key:
                row = self.query(
                    conn, "SELECT payload FROM adm_case_document WHERE idempotency_key=?", (key,)
                ).fetchone()
                if row:
                    previous = json.loads(row[0])
                    if previous.get("requestHash") != case.get("requestHash"):
                        raise Conflict("相同幂等键请求内容不同")
                    return previous
            try:
                self.query(
                    conn,
                    "INSERT INTO adm_case_document(id,version,idempotency_key,payload) VALUES(?,?,?,?)",
                    (case["id"], case["version"], key, json.dumps(case, ensure_ascii=False)),
                )
            except Exception as exc:
                raise Conflict("创建冲突，请重新查询") from exc
        return case

    def save(self, case, expected):
        with self.connection() as conn:
            cursor = self.query(
                conn,
                "UPDATE adm_case_document SET version=?,payload=? WHERE id=? AND version=?",
                (case["version"], json.dumps(case, ensure_ascii=False), case["id"], expected),
            )
            if cursor.rowcount != 1:
                raise Conflict("数据已被其他人修改，请刷新后重试")
