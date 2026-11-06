"""Transactional normalized ADM storage; never reads or writes adm_case_document."""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager

from .store import Conflict, StoreUnavailable


CASE_CHILDREN = {"lines", "attachments", "timeline", "assignmentSegments", "handoverHistory", "fxSource", "fxHistory"}
LINE_CHILDREN = {"appeals", "recoveries", "collections", "reviews"}


SQLITE_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS adm_case (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL, idempotency_key TEXT UNIQUE,
 internal_no TEXT NOT NULL UNIQUE, adm_no TEXT NOT NULL,
 supplier_code TEXT, supplier_name TEXT, supplier_type TEXT, status TEXT NOT NULL,
 business_category TEXT, issued_date TEXT, deadline TEXT, updated_at TEXT NOT NULL,
 voided INTEGER NOT NULL DEFAULT 0, open_remediation INTEGER NOT NULL DEFAULT 0,
 payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adm_case_adm_no ON adm_case(adm_no);
CREATE INDEX IF NOT EXISTS idx_adm_case_status_update ON adm_case(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_adm_case_supplier_date ON adm_case(supplier_code,issued_date);
CREATE INDEX IF NOT EXISTS idx_adm_case_category_update ON adm_case(business_category,updated_at);
CREATE TABLE IF NOT EXISTS adm_case_line (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_internal_no TEXT NOT NULL UNIQUE,
 line_order INTEGER NOT NULL, status TEXT NOT NULL, order_no TEXT, owner_id TEXT,
 payload TEXT NOT NULL, UNIQUE(case_id,line_order),
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_adm_line_case_status ON adm_case_line(case_id,status);
CREATE INDEX IF NOT EXISTS idx_adm_line_order_no ON adm_case_line(order_no);
CREATE TABLE IF NOT EXISTS adm_case_attachment (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT, category TEXT, created_at TEXT,
 payload TEXT NOT NULL, FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_event (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT, action TEXT, occurred_at TEXT,
 event_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_adm_event_case_order ON adm_case_event(case_id,event_order);
CREATE TABLE IF NOT EXISTS adm_case_assignment (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, record_kind TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_appeal (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_recovery (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_collection (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_review (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, line_id TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS adm_case_fx_snapshot (
 record_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, record_kind TEXT NOT NULL,
 record_order INTEGER NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(case_id) REFERENCES adm_case(id) ON DELETE CASCADE
);
"""


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
                conn.executescript(SQLITE_SCHEMA)
            else:
                import pymysql

                def option(name, default=None):
                    return self.config.get("ADM_MYSQL_" + name) or self.config.get("MYSQL_" + name, default)

                if not option("HOST") or not option("USER"):
                    raise StoreUnavailable("ADM MySQL连接尚未配置")
                conn = pymysql.connect(
                    host=option("HOST"), port=int(option("PORT", 3306)), user=option("USER"),
                    password=option("PASSWORD", ""), database=option("DATABASE"), charset="utf8mb4",
                    connect_timeout=5, read_timeout=15, write_timeout=15, autocommit=False,
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
                1146: ("ADM_TABLE_MISSING", "ADM新表尚未建立，请先执行ADM normalized V1 DDL"),
                1054: ("ADM_SCHEMA_UPGRADE_REQUIRED", "ADM新表结构不完整，请核对normalized V1 DDL"),
                1045: ("ADM_DATABASE_AUTH_FAILED", "ADM数据库认证失败，请核对账号配置"),
                1044: ("ADM_DATABASE_PERMISSION", "ADM账号没有目标库访问权限"),
                1142: ("ADM_DATABASE_PERMISSION", "ADM账号缺少当前操作所需的表权限"),
                1049: ("ADM_DATABASE_NOT_FOUND", "ADM目标数据库不存在，请核对实际连接库"),
                1213: ("ADM_DATABASE_BUSY", "ADM编号或主单正在被并发修改，请重试"),
                1205: ("ADM_DATABASE_BUSY", "ADM数据库锁等待超时，请重试"),
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

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _record_key(prefix, item, index):
        return f"{prefix}:{item.get('id') or index}"

    def _load_case(self, conn, case_id):
        row = self.query(conn, "SELECT id,version,internal_no,adm_no,payload FROM adm_case WHERE id=?", (case_id,)).fetchone()
        if not row:
            return None
        case = json.loads(row[4])
        case.update(id=str(row[0]), version=int(row[1]), internalNo=str(row[2]), admNo=str(row[3]))
        lines, by_line = [], {}
        for line_id, internal_no, payload in self.query(
            conn, "SELECT id,line_internal_no,payload FROM adm_case_line WHERE case_id=? ORDER BY line_order", (case_id,)
        ).fetchall():
            line = json.loads(payload)
            line.update(id=str(line_id), lineInternalNo=str(internal_no))
            for name in LINE_CHILDREN:
                line[name] = []
            lines.append(line)
            by_line[line["id"]] = line
        case["lines"] = lines
        case["attachments"] = [json.loads(item[0]) for item in self.query(
            conn, "SELECT payload FROM adm_case_attachment WHERE case_id=? ORDER BY created_at,id", (case_id,)
        ).fetchall()]
        case["timeline"] = [json.loads(item[0]) for item in self.query(
            conn, "SELECT payload FROM adm_case_event WHERE case_id=? ORDER BY event_order", (case_id,)
        ).fetchall()]
        case["assignmentSegments"], case["handoverHistory"] = [], []
        for kind, payload in self.query(
            conn, "SELECT record_kind,payload FROM adm_case_assignment WHERE case_id=? ORDER BY record_kind,record_order", (case_id,)
        ).fetchall():
            case["assignmentSegments" if kind == "SEGMENT" else "handoverHistory"].append(json.loads(payload))
        for name, table in {
            "appeals": "adm_case_appeal", "recoveries": "adm_case_recovery",
            "collections": "adm_case_collection", "reviews": "adm_case_review",
        }.items():
            for line_id, payload in self.query(
                conn, f"SELECT line_id,payload FROM {table} WHERE case_id=? ORDER BY line_id,record_order", (case_id,)
            ).fetchall():
                if str(line_id) in by_line:
                    by_line[str(line_id)][name].append(json.loads(payload))
        case["fxSource"], case["fxHistory"] = None, []
        for kind, payload in self.query(
            conn, "SELECT record_kind,payload FROM adm_case_fx_snapshot WHERE case_id=? ORDER BY record_order", (case_id,)
        ).fetchall():
            if kind == "CURRENT":
                case["fxSource"] = json.loads(payload)
            else:
                case["fxHistory"].append(json.loads(payload))
        return case

    def _load_many(self, conn, ids):
        return [case for case in (self._load_case(conn, str(case_id)) for case_id in ids) if case]

    def all(self):
        with self.connection() as conn:
            ids = [row[0] for row in self.query(conn, "SELECT id FROM adm_case ORDER BY updated_at DESC,id DESC").fetchall()]
            return self._load_many(conn, ids)

    def workflow_cases(self, maximum=5000, include_closed=False):
        where = "status NOT IN ('DRAFT','CLOSED','HISTORICAL')"
        if include_closed:
            where = "status NOT IN ('DRAFT','CLOSED','HISTORICAL') OR (status='CLOSED' AND open_remediation=1)"
        with self.connection() as conn:
            ids = [row[0] for row in self.query(
                conn, f"SELECT id FROM adm_case WHERE {where} ORDER BY updated_at DESC,id DESC LIMIT ?", (maximum + 1,)
            ).fetchall()]
            return self._load_many(conn, ids)

    def report_cases(self, maximum=5000):
        with self.connection() as conn:
            ids = [row[0] for row in self.query(
                conn, "SELECT id FROM adm_case WHERE status NOT IN ('DRAFT','HISTORICAL') ORDER BY updated_at DESC,id DESC LIMIT ?", (maximum + 1,)
            ).fetchall()]
            return self._load_many(conn, ids)

    def get(self, case_id):
        with self.connection() as conn:
            return self._load_case(conn, str(case_id))

    def get_by_internal_no(self, internal_no):
        with self.connection() as conn:
            row = self.query(conn, "SELECT id FROM adm_case WHERE internal_no=?", (internal_no,)).fetchone()
            return self._load_case(conn, str(row[0])) if row else None

    @staticmethod
    def _assign_readable_numbers(case, existing_numbers):
        adm_no = str(case.get("admNo") or "").strip()
        used = []
        for internal_no in existing_numbers:
            head, separator, suffix = str(internal_no or "").rpartition("-")
            if separator and suffix.isdigit() and head == adm_no[: 49 - len(suffix)]:
                used.append(int(suffix))
        ordinal = max([len(existing_numbers), *used], default=0) + 1
        suffix = f"{ordinal:02d}"
        case["internalNo"] = f"{adm_no[: 49 - len(suffix)]}-{suffix}"
        for index, line in enumerate(case.get("lines") or [], 1):
            line["lineInternalNo"] = f"{case['internalNo']}-{index:03d}"

    def _main_payload(self, case):
        result = copy.deepcopy(case)
        for key in CASE_CHILDREN | {"id", "version", "internalNo", "admNo"}:
            result.pop(key, None)
        return result

    def _line_payload(self, line):
        result = copy.deepcopy(line)
        for key in LINE_CHILDREN | {"id", "lineInternalNo"}:
            result.pop(key, None)
        return result

    def _insert_main(self, conn, case, key):
        self.query(
            conn,
            "INSERT INTO adm_case(id,version,idempotency_key,internal_no,adm_no,supplier_code,supplier_name,supplier_type,status,business_category,issued_date,deadline,updated_at,voided,open_remediation,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                case["id"], case["version"], key, case["internalNo"], case["admNo"], case.get("supplierCode"),
                case.get("supplierName"), case.get("supplierType"), case["status"], case.get("businessCategory"),
                case.get("issuedDate"), case.get("deadline"), case["updatedAt"], 1 if case.get("voided") else 0,
                1 if case.get("openRemediation") else 0, self._json(self._main_payload(case)),
            ),
        )

    def _replace_children(self, conn, case):
        case_id = case["id"]
        for table in (
            "adm_case_appeal", "adm_case_recovery", "adm_case_collection", "adm_case_review",
            "adm_case_attachment", "adm_case_event", "adm_case_assignment", "adm_case_fx_snapshot", "adm_case_line",
        ):
            self.query(conn, f"DELETE FROM {table} WHERE case_id=?", (case_id,))
        for line_order, line in enumerate(case.get("lines") or [], 1):
            self.query(
                conn, "INSERT INTO adm_case_line(id,case_id,line_internal_no,line_order,status,order_no,owner_id,payload) VALUES(?,?,?,?,?,?,?,?)",
                (line["id"], case_id, line["lineInternalNo"], line_order, line["status"], line.get("orderNo"), line.get("ownerId"), self._json(self._line_payload(line))),
            )
            for name, table in {
                "appeals": "adm_case_appeal", "recoveries": "adm_case_recovery",
                "collections": "adm_case_collection", "reviews": "adm_case_review",
            }.items():
                for index, item in enumerate(line.get(name) or [], 1):
                    self.query(
                        conn, f"INSERT INTO {table}(record_key,case_id,line_id,record_order,payload) VALUES(?,?,?,?,?)",
                        (self._record_key(f"{line['id']}:{name}", item, index), case_id, line["id"], index, self._json(item)),
                    )
        for item in case.get("attachments") or []:
            self.query(
                conn, "INSERT INTO adm_case_attachment(id,case_id,line_id,category,created_at,payload) VALUES(?,?,?,?,?,?)",
                (item["id"], case_id, item.get("lineId"), item.get("category"), item.get("createdAt"), self._json(item)),
            )
        for index, item in enumerate(case.get("timeline") or [], 1):
            self.query(
                conn, "INSERT INTO adm_case_event(id,case_id,line_id,action,occurred_at,event_order,payload) VALUES(?,?,?,?,?,?,?)",
                (item["id"], case_id, item.get("lineId"), item.get("action"), item.get("at"), index, self._json(item)),
            )
        for kind, name in (("SEGMENT", "assignmentSegments"), ("HANDOVER", "handoverHistory")):
            for index, item in enumerate(case.get(name) or [], 1):
                self.query(
                    conn, "INSERT INTO adm_case_assignment(record_key,case_id,record_kind,record_order,payload) VALUES(?,?,?,?,?)",
                    (self._record_key(f"{case_id}:{kind}", item, index), case_id, kind, index, self._json(item)),
                )
        if case.get("fxSource") is not None:
            self.query(
                conn, "INSERT INTO adm_case_fx_snapshot(record_key,case_id,record_kind,record_order,payload) VALUES(?,?,?,?,?)",
                (f"{case_id}:FX:CURRENT", case_id, "CURRENT", 0, self._json(case["fxSource"])),
            )
        for index, item in enumerate(case.get("fxHistory") or [], 1):
            self.query(
                conn, "INSERT INTO adm_case_fx_snapshot(record_key,case_id,record_kind,record_order,payload) VALUES(?,?,?,?,?)",
                (f"{case_id}:FX:HISTORY:{index}", case_id, "HISTORY", index, self._json(item)),
            )

    def create(self, case, key=None):
        with self.connection() as conn:
            if self.mode == "sqlite":
                conn.execute("BEGIN IMMEDIATE")
            if key:
                row = self.query(conn, "SELECT id FROM adm_case WHERE idempotency_key=?", (key,)).fetchone()
                if row:
                    previous = self._load_case(conn, str(row[0]))
                    if previous.get("requestHash") != case.get("requestHash"):
                        raise Conflict("相同幂等键请求内容不同")
                    return previous
            lock = " FOR UPDATE" if self.mode == "mysql" else ""
            index = " FORCE INDEX (idx_adm_case_adm_no)" if self.mode == "mysql" else ""
            rows = self.query(conn, f"SELECT internal_no FROM adm_case{index} WHERE adm_no=?{lock}", (case.get("admNo"),)).fetchall()
            self._assign_readable_numbers(case, [row[0] for row in rows])
            try:
                self._insert_main(conn, case, key)
                self._replace_children(conn, case)
            except sqlite3.IntegrityError as exc:
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
                "UPDATE adm_case SET version=?,internal_no=?,adm_no=?,supplier_code=?,supplier_name=?,supplier_type=?,status=?,business_category=?,issued_date=?,deadline=?,updated_at=?,voided=?,open_remediation=?,payload=? WHERE id=? AND version=?",
                (
                    case["version"], case["internalNo"], case["admNo"], case.get("supplierCode"), case.get("supplierName"),
                    case.get("supplierType"), case["status"], case.get("businessCategory"), case.get("issuedDate"),
                    case.get("deadline"), case["updatedAt"], 1 if case.get("voided") else 0,
                    1 if case.get("openRemediation") else 0, self._json(self._main_payload(case)), case["id"], expected,
                ),
            )
            if cursor.rowcount != 1:
                raise Conflict("数据已被其他人修改，请刷新后重试")
            self._replace_children(conn, case)

    def check(self):
        with self.connection() as conn:
            for table in (
                "adm_case", "adm_case_line", "adm_case_event", "adm_case_attachment", "adm_case_assignment",
                "adm_case_appeal", "adm_case_recovery", "adm_case_collection", "adm_case_review", "adm_case_fx_snapshot",
            ):
                self.query(conn, f"SELECT 1 FROM {table} LIMIT 0")

    def same_identity(self, case):
        with self.connection() as conn:
            ids = [row[0] for row in self.query(
                conn, "SELECT id FROM adm_case WHERE adm_no=? AND supplier_name=? AND supplier_type=? LIMIT 100",
                (case.get("admNo"), case.get("supplierName"), case.get("supplierType")),
            ).fetchall()]
            return self._load_many(conn, ids)

    def page_all(self, filters, page, size, stamp):
        where, values = ["1=1"], []
        if str(filters.get("activeOnly", "")).lower() == "true":
            where.append("c.status NOT IN ('CLOSED','HISTORICAL')")
        for key, column in (("status", "status"), ("businessCategory", "business_category"), ("supplierCode", "supplier_code")):
            if filters.get(key) not in (None, ""):
                where.append("c." + column + "=?")
                values.append(filters[key])
        if filters.get("search"):
            term = str(filters["search"]).strip().lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
            cast_case = "CAST(c.payload AS CHAR)" if self.mode == "mysql" else "c.payload"
            cast_line = "CAST(l.payload AS CHAR)" if self.mode == "mysql" else "l.payload"
            where.append(
                f"(LOWER(c.internal_no) LIKE ? ESCAPE '!' OR LOWER(c.adm_no) LIKE ? ESCAPE '!' OR LOWER({cast_case}) LIKE ? ESCAPE '!' "
                f"OR EXISTS (SELECT 1 FROM adm_case_line l WHERE l.case_id=c.id AND (LOWER(l.line_internal_no) LIKE ? ESCAPE '!' OR LOWER(COALESCE(l.order_no,'')) LIKE ? ESCAPE '!' OR LOWER({cast_line}) LIKE ? ESCAPE '!')))"
            )
            values.extend(["%" + term + "%"] * 6)
        clause = " AND ".join(where)
        length = "CHAR_LENGTH" if self.mode == "mysql" else "LENGTH"
        active = "c.status NOT IN ('CLOSED','HISTORICAL') AND c.voided=0"
        with self.connection() as conn:
            counts = self.query(
                conn,
                f"SELECT COUNT(*),COALESCE(SUM(CASE WHEN {active} THEN 1 ELSE 0 END),0),COALESCE(SUM(CASE WHEN {active} AND COALESCE(c.deadline,'')<>'' AND (({length}(c.deadline)=10 AND c.deadline<?) OR ({length}(c.deadline)>10 AND c.deadline<?)) THEN 1 ELSE 0 END),0) FROM adm_case c WHERE {clause}",
                (stamp[:10], stamp, *values),
            ).fetchone()
            line_count = self.query(
                conn, f"SELECT COUNT(*) FROM adm_case_line l JOIN adm_case c ON c.id=l.case_id WHERE {clause}", tuple(values)
            ).fetchone()[0]
            ids = [row[0] for row in self.query(
                conn, f"SELECT c.id FROM adm_case c WHERE {clause} ORDER BY c.updated_at DESC,c.id DESC LIMIT ? OFFSET ?",
                (*values, size, (page - 1) * size),
            ).fetchall()]
            cases = self._load_many(conn, ids)
        return cases, {"cases": counts[0], "lines": line_count, "open": counts[1], "overdue": counts[2]}
