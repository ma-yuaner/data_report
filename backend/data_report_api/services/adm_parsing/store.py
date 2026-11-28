"""Version-checked intake persistence. Production DDL is applied separately."""
import json
import sqlite3
from threading import Lock
from contextlib import contextmanager
from pathlib import Path

from ..admwf.policy import AdmError
from ..admwf.repository import AdmWorkflowRepository

_sqlite_intake_lock = Lock()

SQLITE_SCHEMA = """CREATE TABLE IF NOT EXISTS adm_parse_task (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, version_no INTEGER NOT NULL,
 state TEXT NOT NULL, updated_at TEXT NOT NULL, request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(owner_id,request_key));
 CREATE INDEX IF NOT EXISTS idx_adm_parse_owner ON adm_parse_task(owner_id,updated_at);
 CREATE INDEX IF NOT EXISTS idx_adm_parse_state ON adm_parse_task(state,updated_at);"""


class ParsingStore:
    def __init__(self, config):
        self.config = config
        self.sqlite = config.get("ADM_PARSING_STORAGE_MODE", "mysql") == "sqlite"
        if self.sqlite and not (config.get("TESTING") and config.get("ADM_PARSING_SQLITE_PATH")):
            raise AdmError("SQLite仅用于显式隔离本地测试", 503, "PARSE_STORAGE_CONFIG")
        if config.get("ADM_PARSING_STORAGE_MODE", "mysql") not in {"mysql", "sqlite"}:
            raise AdmError("解析存储模式无效", 503, "PARSE_STORAGE_CONFIG")

    @contextmanager
    def db(self):
        if not self.sqlite:
            with AdmWorkflowRepository(self.config).transaction() as conn:
                yield conn
            return
        path = Path(self.config["ADM_PARSING_SQLITE_PATH"])
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SQLITE_SCHEMA)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, conn, sql, params=()):
        cursor = conn.cursor()
        cursor.execute(sql if self.sqlite else sql.replace("?", "%s"), params)
        return cursor

    @contextmanager
    def intake_lock(self):
        if self.sqlite:
            with _sqlite_intake_lock:
                yield
            return
        with self.db() as conn:
            name = "data_report_adm_parse_intake"
            row = self.query(conn, "SELECT GET_LOCK(?, 10) AS acquired", (name,)).fetchone()
            if not row or row["acquired"] != 1:
                raise AdmError("ADM收件处理中，请稍后重试", 409, "PARSE_INTAKE_BUSY")
            try:
                yield
            finally:
                self.query(conn, "SELECT RELEASE_LOCK(?)", (name,))

    def matching_intakes(self, field, value):
        paths = {"bundle": "$.bundleHash", "identity": "$.intakeIdentity"}
        expression = f"JSON_EXTRACT(payload,'{paths[field]}')"
        if not self.sqlite:
            expression = f"JSON_UNQUOTE({expression})"
        with self.db() as conn:
            rows = self.query(conn, f"SELECT payload FROM adm_parse_task WHERE state<>'DELETED' AND {expression}=?",
                              (value,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get(self, task_id):
        with self.db() as conn:
            row = self.query(conn, "SELECT payload FROM adm_parse_task WHERE id=?", (task_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def by_key(self, owner, key):
        with self.db() as conn:
            row = self.query(conn, "SELECT payload FROM adm_parse_task WHERE owner_id=? AND request_key=?", (owner, key)).fetchone()
        return json.loads(row["payload"]) if row else None

    def create(self, task, key, digest):
        try:
            with self.db() as conn:
                self.query(conn, "INSERT INTO adm_parse_task(id,owner_id,version_no,state,updated_at,request_key,request_hash,payload) VALUES(?,?,?,?,?,?,?,?)",
                           (task["id"], task["ownerId"], task["version"], task["state"], task["updatedAt"], key, digest, json.dumps(task, ensure_ascii=False)))
        except Exception:
            previous = self.by_key(task["ownerId"], key)
            if previous and previous["requestHash"] == digest:
                return previous
            if previous:
                raise AdmError("同一上传请求的文件不同，请重新打开上传窗口", 409, "PARSE_IDEMPOTENCY") from None
            raise
        return task

    def save(self, task, expected):
        with self.db() as conn:
            cursor = self.query(conn, "UPDATE adm_parse_task SET version_no=?,state=?,updated_at=?,payload=? WHERE id=? AND version_no=?",
                                (task["version"], task["state"], task["updatedAt"], json.dumps(task, ensure_ascii=False, allow_nan=False), task["id"], expected))
            if cursor.rowcount != 1:
                raise AdmError("解析任务已更新，请刷新后操作", 409, "PARSE_VERSION_CONFLICT")

    def list(self, owner, page, size, state=""):
        where, params = ("state<>'DELETED'", []) if owner is None else ("state<>'DELETED' AND owner_id=?", [owner])
        if state:
            where += " AND state=?"
            params.append(state)
        with self.db() as conn:
            count = self.query(conn, "SELECT COUNT(*) AS total FROM adm_parse_task WHERE " + where, params).fetchone()["total"]
            rows = self.query(conn, "SELECT payload FROM adm_parse_task WHERE " + where + " ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
        return [json.loads(row["payload"]) for row in rows], count

    def queued(self):
        with self.db() as conn:
            rows = self.query(conn, "SELECT id FROM adm_parse_task WHERE state='QUEUED' ORDER BY updated_at LIMIT 20").fetchall()
        return [row["id"] for row in rows]
