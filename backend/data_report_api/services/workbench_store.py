"""Single-host durable workbench metadata and fenced worker claims."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def uid():
    return uuid.uuid4().hex


class WorkbenchError(ValueError):
    def __init__(self, message, code="INVALID_REQUEST", status=400, report=None):
        super().__init__(message)
        self.code, self.status, self.report = code, status, report


class WorkbenchStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("sources", "results", "attempts", "uploads"):
            (self.root / name).mkdir(exist_ok=True)
        self.db = self.root / "metadata.sqlite3"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS resources(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, owner INTEGER NOT NULL,
              body TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS resources_owner ON resources(owner,kind,created);
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, owner INTEGER NOT NULL, body TEXT NOT NULL,
              status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
              token TEXT, lease REAL, attempt INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);
            CREATE TABLE IF NOT EXISTS slots(name TEXT PRIMARY KEY,token TEXT,lease REAL);
            """)

    def connect(self):
        db = sqlite3.connect(str(self.db), timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        return db

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def get(self, kind, resource_id, owner):
        with self.connect() as db:
            row = db.execute("SELECT body FROM resources WHERE id=? AND kind=? AND owner=?", (resource_id, kind, owner)).fetchone()
        if not row:
            raise WorkbenchError("资源不存在或无权访问", "NOT_FOUND", 404)
        return json.loads(row["body"])

    def list(self, kind, owner):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM resources WHERE kind=? AND owner=? ORDER BY created DESC", (kind, owner)).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def insert(self, kind, owner, body):
        with self.connect() as db:
            db.execute("INSERT INTO resources VALUES(?,?,?,?,?)", (body["id"], kind, owner, json.dumps(body, ensure_ascii=False), time.time()))
        return body

    def update_recipe(self, owner, body, revision):
        with self.transaction() as db:
            row = db.execute("SELECT body FROM resources WHERE id=? AND kind='recipe' AND owner=?", (body["id"], owner)).fetchone()
            if not row:
                raise WorkbenchError("流程不存在", "NOT_FOUND", 404)
            old = json.loads(row["body"])
            if old["revision"] != revision:
                raise WorkbenchError("流程已被修改，请刷新后重试", "REVISION_CONFLICT", 409)
            body.update(revision=revision + 1, createdAt=old["createdAt"])
            db.execute("UPDATE resources SET body=? WHERE id=?", (json.dumps(body, ensure_ascii=False), body["id"]))
        return body

    def publish(self, job_id, owner, name):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                raise WorkbenchError("任务不存在", "NOT_FOUND", 404)
            job = self.job_body(row)
            if job["status"] != "succeeded":
                raise WorkbenchError("仅成功任务可以发布", "RESULT_NOT_READY", 409)
            existing = db.execute("SELECT body FROM resources WHERE id=? AND kind='dataset' AND owner=?", (job_id, owner)).fetchone()
            if existing:
                return json.loads(existing["body"])
            body = {"id": job_id, "name": name, "rowCount": job["rowCount"], "fields": job["fields"],
                    "createdAt": utc(), "quality": {"publishedFromJob": job_id, "scope": "full"}, "_path": job["_path"]}
            db.execute("INSERT INTO resources VALUES(?,'dataset',?,?,?)", (job_id, owner, json.dumps(body, ensure_ascii=False), time.time()))
            return body

    @staticmethod
    def job_body(row):
        body = json.loads(row["body"])
        body.update(status=row["status"], updatedAt=utc(row["updated"]))
        return body

    def get_job(self, job_id, owner):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
        if not row:
            raise WorkbenchError("任务不存在或无权访问", "NOT_FOUND", 404)
        return self.job_body(row)

    def list_jobs(self, owner):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 100", (owner,)).fetchall()
        return [self.job_body(row) for row in rows]

    def enqueue(self, owner, body, max_pending=5):
        now = time.time()
        with self.transaction() as db:
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE owner=? AND status IN ('queued','running','cancel_requested')", (owner,)).fetchone()[0]
            if count >= max_pending:
                raise WorkbenchError("待处理任务过多，请等待或取消已有任务", "QUEUE_FULL", 429)
            db.execute("INSERT INTO jobs(id,owner,body,status,created,updated) VALUES(?,?,?,'queued',?,?)", (body["id"], owner, json.dumps(body, ensure_ascii=False), now, now))
        return self.get_job(body["id"], owner)

    def cancel(self, job_id, owner):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                raise WorkbenchError("任务不存在", "NOT_FOUND", 404)
            status = "cancelled" if row["status"] == "queued" else "cancel_requested" if row["status"] == "running" else row["status"]
            db.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", (status, time.time(), job_id))
        return self.get_job(job_id, owner)

    def claim(self, concurrency=1, lease_seconds=30, max_attempts=3):
        now = time.time()
        with self.transaction() as db:
            expired = db.execute("SELECT * FROM jobs WHERE status IN ('running','cancel_requested') AND lease<?", (now,)).fetchall()
            for row in expired:
                body = json.loads(row["body"])
                status = "cancelled" if row["status"] == "cancel_requested" else "failed" if row["attempt"] >= max_attempts else "queued"
                if status == "failed":
                    body.update(error="任务执行中断，重试次数已达限制", code="WORKER_INTERRUPTED")
                db.execute("UPDATE jobs SET status=?,body=?,token=NULL,lease=NULL,updated=? WHERE id=?", (status, json.dumps(body, ensure_ascii=False), now, row["id"]))
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('running','cancel_requested')").fetchone()[0]
            if active >= concurrency:
                return None
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            token = uid()
            db.execute("UPDATE jobs SET status='running',token=?,lease=?,attempt=attempt+1,updated=? WHERE id=?", (token, now + lease_seconds, now, row["id"]))
            return {"id": row["id"], "owner": row["owner"], "token": token, "body": json.loads(row["body"])}

    def heartbeat(self, job_id, token, lease_seconds=30):
        with self.transaction() as db:
            row = db.execute("SELECT status,lease FROM jobs WHERE id=? AND token=?", (job_id, token)).fetchone()
            if not row or row["lease"] < time.time() or row["status"] not in ("running", "cancel_requested"):
                return "lost"
            db.execute("UPDATE jobs SET lease=? WHERE id=? AND token=?", (time.time() + lease_seconds, job_id, token))
            return row["status"]

    def finish(self, job_id, token, status, details, staged=None):
        # The rename and metadata commit are fenced under one writer transaction.
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND token=?", (job_id, token)).fetchone()
            if not row or row["lease"] < time.time() or row["status"] not in ("running", "cancel_requested"):
                return False
            if row["status"] == "cancel_requested":
                status, details = "cancelled", {}
            body = json.loads(row["body"])
            if status == "succeeded":
                target = self.root / "results" / (job_id + ".parquet")
                Path(staged).replace(target)
                body["_path"] = str(target)
            body.update(details)
            db.execute("UPDATE jobs SET body=?,status=?,updated=?,lease=NULL WHERE id=? AND token=?", (json.dumps(body, ensure_ascii=False), status, time.time(), job_id, token))
        return True

    def acquire_slot(self, name, token, seconds=600):
        with self.transaction() as db:
            row = db.execute("SELECT lease FROM slots WHERE name=?", (name,)).fetchone()
            if row and row["lease"] > time.time():
                return False
            db.execute("INSERT OR REPLACE INTO slots VALUES(?,?,?)", (name, token, time.time() + seconds))
        return True

    def release_slot(self, name, token):
        with self.connect() as db:
            db.execute("DELETE FROM slots WHERE name=? AND token=?", (name, token))


def utc(value=None):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(time.time() if value is None else value, timezone.utc).isoformat()
