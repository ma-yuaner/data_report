"""Private HR MySQL documents and preview receipts; production DDL is manual."""
import json
import sqlite3
from contextlib import contextmanager

from ..data_source import DataSource


class MailError(Exception):
    def __init__(self, message, code="HR_MAIL_INVALID", status=422):
        super().__init__(message)
        self.code, self.status = code, status


class Store:
    def __init__(self, config):
        self.config = config
        self.sqlite = bool(config.get("TESTING") and config.get("HR_MAIL_SQLITE_PATH"))

    @contextmanager
    def connection(self):
        conn = None
        try:
            if self.sqlite:
                conn = sqlite3.connect(self.config["HR_MAIL_SQLITE_PATH"], timeout=15)
                conn.execute("CREATE TABLE IF NOT EXISTS hr_mail_upload(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,payload TEXT NOT NULL)")
                conn.execute("CREATE TABLE IF NOT EXISTS hr_mail_batch(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,request_key TEXT UNIQUE,payload TEXT NOT NULL)")
                conn.execute("CREATE TABLE IF NOT EXISTS hr_mail_preview(batch_id TEXT,item_id TEXT,viewer_id TEXT,receipt TEXT NOT NULL,PRIMARY KEY(batch_id,item_id,viewer_id))")
                conn.commit()
            else:
                conn = DataSource({**self.config, "DATA_MODE": "mysql"}).connect()
                conn.begin()
            yield conn
            conn.commit()
        except MailError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            number = error.args[0] if error.args else None
            code = "HR_MAIL_DDL_MISSING" if number in (1146, 1054) else "HR_MAIL_STORAGE_UNAVAILABLE"
            raise MailError("HR邮件存储不可用，请核对连接、权限和专用DDL", code, 503) from error
        finally:
            if conn:
                conn.close()

    def sql(self, conn, sql, params=()):
        cursor = conn.cursor()
        cursor.execute(sql if self.sqlite else sql.replace("?", "%s"), params)
        return cursor

    def check(self):
        with self.connection() as conn:
            for query in (
                "SELECT id,owner_id,payload FROM hr_mail_upload LIMIT 0",
                "SELECT id,owner_id,version,status,created_at,request_key,payload FROM hr_mail_batch LIMIT 0",
                "SELECT batch_id,item_id,viewer_id,receipt FROM hr_mail_preview LIMIT 0",
            ):
                self.sql(conn, query)

    def upload(self, value):
        with self.connection() as conn:
            self.sql(conn, "INSERT INTO hr_mail_upload(id,owner_id,payload) VALUES(?,?,?)", (value["id"], value["ownerId"], json.dumps(value, ensure_ascii=False)))

    def get_upload(self, upload_id, owner):
        with self.connection() as conn:
            row = self.sql(conn, "SELECT payload FROM hr_mail_upload WHERE id=? AND owner_id=?", (upload_id, owner)).fetchone()
        if not row:
            raise MailError("文件不存在或不属于当前账号", "HR_MAIL_NOT_FOUND", 404)
        return json.loads(row[0])

    def get(self, batch_id):
        with self.connection() as conn:
            row = self.sql(conn, "SELECT payload FROM hr_mail_batch WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise MailError("批次不存在或无权限", "HR_MAIL_NOT_FOUND", 404)
        return json.loads(row[0])

    def create(self, value):
        with self.connection() as conn:
            # Unique immutable request key prevents concurrent double-parse batches.
            sql = "INSERT OR IGNORE" if self.sqlite else "INSERT IGNORE"
            self.sql(conn, sql + " INTO hr_mail_batch(id,owner_id,version,status,created_at,request_key,payload) VALUES(?,?,?,?,?,?,?)", (value["id"], value["ownerId"], value["version"], value["status"], value["createdAt"], value["requestKey"], json.dumps(value, ensure_ascii=False)))
            row = self.sql(conn, "SELECT payload FROM hr_mail_batch WHERE request_key=?", (value["requestKey"],)).fetchone()
        if not row:
            raise MailError("创建批次失败", "HR_MAIL_STORAGE_UNAVAILABLE", 503)
        return json.loads(row[0])

    def save(self, value, version):
        value = {**value, "version": version + 1}
        with self.connection() as conn:
            cursor = self.sql(conn, "UPDATE hr_mail_batch SET version=?,status=?,payload=? WHERE id=? AND version=?", (value["version"], value["status"], json.dumps(value, ensure_ascii=False), value["id"], version))
            if cursor.rowcount != 1:
                raise MailError("批次已更新，请刷新核对；不会重复发送", "HR_MAIL_CONFLICT", 409)
        return value

    def preview(self, batch_id, item_id, viewer, receipt):
        with self.connection() as conn:
            sql = "INSERT OR IGNORE" if self.sqlite else "INSERT IGNORE"
            self.sql(conn, sql + " INTO hr_mail_preview(batch_id,item_id,viewer_id,receipt) VALUES(?,?,?,?)", (batch_id, item_id, viewer, receipt))
            return self.sql(conn, "SELECT receipt FROM hr_mail_preview WHERE batch_id=? AND item_id=? AND viewer_id=?", (batch_id, item_id, viewer)).fetchone()[0]

    def receipt(self, batch_id, item_id, viewer):
        with self.connection() as conn:
            row = self.sql(conn, "SELECT receipt FROM hr_mail_preview WHERE batch_id=? AND item_id=? AND viewer_id=?", (batch_id, item_id, viewer)).fetchone()
        return row[0] if row else ""

    def list(self, user, args):
        page, size = max(1, int(args.get("page", 1))), min(100, max(1, int(args.get("pageSize", 15))))
        clauses, params = [], []
        if not user.get("is_admin"):
            clauses.append("owner_id=?")
            params.append(str(user["id"]))
        if args.get("status"):
            clauses.append("status=?")
            params.append(str(args["status"]))
        # JSON payload search remains scoped; escaped LIKE never expands wildcard scope.
        if args.get("search"):
            text = str(args["search"])[:200].replace("!", "!!").replace("%", "!%").replace("_", "!_")
            clauses.append("CAST(payload AS CHAR) LIKE ? ESCAPE '!'")
            params.append("%" + text + "%")
        if args.get("reportType"):
            clauses.append("request_key LIKE ?")
            params.append(str(args["reportType"]) + ":%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            total = self.sql(conn, "SELECT COUNT(*) FROM hr_mail_batch" + where, params).fetchone()[0]
            rows = self.sql(conn, "SELECT payload FROM hr_mail_batch" + where + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total, "page": page, "pageSize": size}

    def active(self):
        with self.connection() as conn:
            rows = self.sql(conn, "SELECT payload FROM hr_mail_batch WHERE status IN ('QUEUED','RUNNING') ORDER BY created_at,id LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]
