"""Storage for annotation projects, sample revisions and immutable releases."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .data_source import DataSource


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS annotation_project (
 id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, owner_id TEXT NOT NULL,
 kind TEXT NOT NULL, version_no INTEGER NOT NULL, labels TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS annotation_member (
 project_id TEXT NOT NULL, account_id TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT NOT NULL,
 PRIMARY KEY(project_id, account_id), FOREIGN KEY(project_id) REFERENCES annotation_project(id));
CREATE TABLE IF NOT EXISTS annotation_sample (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, fingerprint TEXT NOT NULL, creator_id TEXT NOT NULL,
 assignee_id TEXT NOT NULL, status TEXT NOT NULL, version_no INTEGER NOT NULL, updated_at TEXT NOT NULL,
 name TEXT NOT NULL, title TEXT NOT NULL, platform TEXT NOT NULL, source_task_id TEXT,
 expected INTEGER, position_count INTEGER NOT NULL, payload TEXT NOT NULL, segments TEXT NOT NULL,
 UNIQUE(project_id, fingerprint), FOREIGN KEY(project_id) REFERENCES annotation_project(id));
CREATE INDEX IF NOT EXISTS idx_annotation_member_account ON annotation_member(account_id, project_id);
CREATE INDEX IF NOT EXISTS idx_annotation_sample_status ON annotation_sample(project_id,status,updated_at,id);
CREATE INDEX IF NOT EXISTS idx_annotation_sample_assignee ON annotation_sample(project_id,assignee_id,status,updated_at,id);
CREATE TABLE IF NOT EXISTS annotation_revision (
 sample_id TEXT NOT NULL, version_no INTEGER NOT NULL, action TEXT NOT NULL, actor_id TEXT NOT NULL,
 occurred_at TEXT NOT NULL, note TEXT NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(sample_id,version_no), FOREIGN KEY(sample_id) REFERENCES annotation_sample(id));
CREATE TABLE IF NOT EXISTS annotation_dataset (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL COLLATE NOCASE,
 created_at TEXT NOT NULL, creator_id TEXT NOT NULL, sample_count INTEGER NOT NULL, payload TEXT NOT NULL,
 UNIQUE(project_id,name), FOREIGN KEY(project_id) REFERENCES annotation_project(id));
"""

SAMPLE_COLUMNS = ("id,project_id,creator_id,assignee_id,status,version_no,updated_at,"
                  "name,title,platform,source_task_id,expected,position_count,payload")


def encode(payload):
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def duplicate(error):
    return (isinstance(error, sqlite3.IntegrityError) and "UNIQUE" in str(error)
            or bool(error.args and error.args[0] == 1062))


class AnnotationStore:
    def __init__(self, config):
        self.config = config
        self.path = config.get("ANNOTATION_SQLITE_PATH")
        if self.path and not config.get("TESTING"):
            raise ValueError("标注 SQLite 仅用于隔离测试")

    @contextmanager
    def transaction(self, *, write=False):
        if self.path:
            path = Path(self.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=15)
            conn.row_factory = sqlite3.Row
        else:
            conn = DataSource({**self.config, "DATA_MODE": "mysql"}).connect()
        try:
            if self.path:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.executescript(SQLITE_SCHEMA)
                conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            else:
                conn.begin()
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def cursor(self, conn, sql, args=()):
        if self.path:
            cursor = conn.cursor()
        else:
            from pymysql.cursors import DictCursor
            cursor = conn.cursor(DictCursor)
        try:
            cursor.execute(sql if self.path else sql.replace("?", "%s"), args)
            yield cursor
        finally:
            cursor.close()

    def one(self, conn, sql, args=()):
        with self.cursor(conn, sql, args) as cursor:
            row = cursor.fetchone()
            return dict(row) if row else None

    def all(self, conn, sql, args=()):
        with self.cursor(conn, sql, args) as cursor:
            return [dict(row) for row in cursor.fetchall()]

    def write(self, conn, sql, args=()):
        with self.cursor(conn, sql, args) as cursor:
            return cursor.rowcount

    def project(self, conn, ident, *, lock=False):
        suffix = " FOR UPDATE" if lock and not self.path else ""
        return self.one(conn, "SELECT * FROM annotation_project WHERE id=?" + suffix, (ident,))

    def members(self, conn, ident):
        return self.all(conn, "SELECT account_id AS id,role,display_name AS name FROM annotation_member "
                              "WHERE project_id=? ORDER BY display_name,account_id", (ident,))

    def sample(self, conn, ident):
        return self.one(conn, "SELECT " + SAMPLE_COLUMNS + ",segments FROM annotation_sample WHERE id=?", (ident,))
