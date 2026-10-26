"""Atomic aggregate storage. Production schema is installed separately by an operator."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager


class StoreUnavailable(Exception):
    def __init__(self, message, code="ADM_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


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
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        except Exception as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            number = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
            errors = {
                1146: ("ADM_TABLE_MISSING", "ADM专用表尚未建立，请在实际连接的sibebid库执行ADM新建DDL"),
                1054: ("ADM_SCHEMA_UPGRADE_REQUIRED", "ADM表结构尚未升级，请执行ADM索引升级DDL"),
                1045: ("ADM_DATABASE_AUTH_FAILED", "ADM数据库认证失败，请核对账号配置"),
                1044: ("ADM_DATABASE_PERMISSION", "ADM账号没有目标库访问权限"),
                1142: ("ADM_DATABASE_PERMISSION", "ADM账号缺少当前操作所需的表权限"),
                1049: ("ADM_DATABASE_NOT_FOUND", "ADM目标数据库不存在，请核对实际连接库"),
                2003: ("ADM_DATABASE_UNREACHABLE", "ADM数据库无法连接，请核对网络与服务状态"),
                2013: ("ADM_DATABASE_CONNECTION_LOST", "ADM数据库连接中断，请刷新核对保存结果"),
            }
            code, message = errors.get(number, ("ADM_UNAVAILABLE", "ADM存储操作失败，请核对连接、表结构或数据格式"))
            raise StoreUnavailable(message, code) from exc
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

    def workflow_cases(self, maximum=5000, include_closed=False):
        """Bounded live worklist source; never silently publish a partial dashboard."""
        status = "case_status" if self.mode == "mysql" else "json_extract(payload,'$.status')"
        with self.connection() as conn:
            where = f"{status} NOT IN ('DRAFT','CLOSED','HISTORICAL')"
            if include_closed:
                where = f"({where} OR ({status}='CLOSED' AND json_extract(payload,'$.openRemediation')=true))"
            rows = self.query(conn, f"SELECT payload FROM adm_case_document WHERE {where} LIMIT ?", (maximum + 1,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def report_cases(self, maximum=5000):
        """Separate bounded source; closed historical volume must not break live worklists."""
        status = "case_status" if self.mode == "mysql" else "json_extract(payload,'$.status')"
        with self.connection() as conn:
            rows = self.query(conn, f"SELECT payload FROM adm_case_document WHERE {status} NOT IN ('DRAFT','HISTORICAL') LIMIT ?", (maximum + 1,)).fetchall()
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
            except (sqlite3.IntegrityError,) as exc:
                raise Conflict("创建冲突，请重新查询") from exc
            except Exception as exc:
                if exc.args and exc.args[0] == 1062:
                    raise Conflict("创建冲突，请刷新核对") from exc
                raise
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

    def check(self):
        with self.connection() as conn:
            fields = "id,version,payload,case_status,supplier_code,business_category,updated_at" if self.mode == "mysql" else "id,version,payload"
            self.query(conn, f"SELECT {fields} FROM adm_case_document LIMIT 0")

    def same_identity(self, case):
        conditions = []
        for name in ("admNo", "supplierName", "supplierType"):
            field = f"JSON_UNQUOTE(JSON_EXTRACT(payload,'$.{name}'))" if self.mode == "mysql" else f"json_extract(payload,'$.{name}')"
            conditions.append(field + "=?")
        with self.connection() as conn:
            rows = self.query(conn, "SELECT payload FROM adm_case_document WHERE " + " AND ".join(conditions) + " LIMIT 100", tuple(case.get(name) for name in ("admNo", "supplierName", "supplierType"))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def page_all(self, filters, page, size, stamp):
        """Only for an explicitly authorized all-scope request; no partial-source search."""
        def field(column, path):
            return column if self.mode == "mysql" else f"json_extract(payload,'$.{path}')"
        status = field("case_status", "status")
        updated = field("updated_at", "updatedAt")
        where, values = ["1=1"], []
        if str(filters.get("activeOnly", "")).lower() == "true":
            where.append(status + " NOT IN ('CLOSED','HISTORICAL')")
        for key, column, path in [("status", "case_status", "status"), ("businessCategory", "business_category", "businessCategory"), ("supplierCode", "supplier_code", "supplierCode")]:
            if filters.get(key) not in (None, ""):
                where.append(field(column, path) + "=?")
                values.append(filters[key])
        if filters.get("search"):
            # Full-scope users may search all source facts; escape LIKE metacharacters.
            term = str(filters["search"]).strip().lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
            where.append("LOWER(CAST(payload AS CHAR)) LIKE ? ESCAPE '!'" if self.mode == "mysql" else "LOWER(payload) LIKE ? ESCAPE '!'")
            values.append("%" + term + "%")
        clause = " AND ".join(where)
        def j(path):
            return f"JSON_UNQUOTE(JSON_EXTRACT(payload,'$.{path}'))" if self.mode == "mysql" else f"json_extract(payload,'$.{path}')"
        active = f"{status} NOT IN ('CLOSED','HISTORICAL') AND CAST(COALESCE({j('voided')},'false') AS CHAR) NOT IN ('true','1')"
        deadline = j("deadline")
        length = "CHAR_LENGTH" if self.mode == "mysql" else "LENGTH"
        count = "JSON_LENGTH(payload,'$.lines')" if self.mode == "mysql" else "json_array_length(payload,'$.lines')"
        with self.connection() as conn:
            row = self.query(conn, f"SELECT COUNT(*),COALESCE(SUM({count}),0),COALESCE(SUM(CASE WHEN {active} THEN 1 ELSE 0 END),0),COALESCE(SUM(CASE WHEN {active} AND {deadline}<>'' AND (({length}({deadline})=10 AND {deadline}<?) OR ({length}({deadline})>10 AND {deadline}<?)) THEN 1 ELSE 0 END),0) FROM adm_case_document WHERE {clause}", (stamp[:10], stamp, *values)).fetchone()
            rows = self.query(conn, f"SELECT payload FROM adm_case_document WHERE {clause} ORDER BY {updated} DESC,id DESC LIMIT ? OFFSET ?", (*values, size, (page - 1) * size)).fetchall()
        return [json.loads(item[0]) for item in rows], {"cases": row[0], "lines": row[1], "open": row[2], "overdue": row[3]}
