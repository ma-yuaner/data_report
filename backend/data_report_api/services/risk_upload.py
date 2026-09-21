from __future__ import annotations

import hashlib
import hmac
import shutil
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage

from .risk_upload_definitions import RISK_UPLOAD_DEFINITIONS


ACTIVE_STATUSES = ("queued", "running")
FINAL_STATUSES = ("success", "failed")


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RiskUploadStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.sqlite3"
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_upload_jobs (
                    id TEXT PRIMARY KEY,
                    business_type TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_sha256 TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    load_date TEXT,
                    status TEXT NOT NULL,
                    queued_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    rows_read INTEGER,
                    rows_written INTEGER,
                    message TEXT NOT NULL DEFAULT '',
                    log_text TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_risk_upload_jobs_status_time "
                "ON risk_upload_jobs(status, queued_at)"
            )

    @staticmethod
    def public_job(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item.pop("stored_path", None)
        return {
            "id": item["id"],
            "businessType": item["business_type"],
            "targetTable": item["target_table"],
            "originalName": item["original_name"],
            "fileSize": item["file_size"],
            "fileSha256": item["file_sha256"],
            "sheetName": item["sheet_name"],
            "loadDate": item["load_date"],
            "status": item["status"],
            "queuedAt": item["queued_at"],
            "startedAt": item["started_at"],
            "finishedAt": item["finished_at"],
            "rowsRead": item["rows_read"],
            "rowsWritten": item["rows_written"],
            "message": item["message"],
            "logs": [line for line in item.get("log_text", "").splitlines() if line][-80:],
        }

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM risk_upload_jobs ORDER BY queued_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [self.public_job(row) for row in rows]

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM risk_upload_jobs "
                "WHERE business_type=? AND file_sha256=? AND status IN ('queued','running') LIMIT 1",
                (job["business_type"], job["file_sha256"]),
            ).fetchone()
            if duplicate:
                raise ValueError("同一文件的同类导入任务正在排队或执行，请勿重复提交")
            connection.execute(
                """
                INSERT INTO risk_upload_jobs (
                    id, business_type, target_table, original_name, stored_path,
                    file_size, file_sha256, sheet_name, load_date, status, queued_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    job["id"], job["business_type"], job["target_table"],
                    job["original_name"], job["stored_path"], job["file_size"],
                    job["file_sha256"], job["sheet_name"], job["load_date"],
                    job["queued_at"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM risk_upload_jobs WHERE id=?", (job["id"],)
            ).fetchone()
        return self.public_job(row)

    def claim_next(self) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM risk_upload_jobs WHERE status='queued' "
                "ORDER BY queued_at LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            started_at = now_text()
            changed = connection.execute(
                "UPDATE risk_upload_jobs SET status='running', started_at=?, "
                "message='正在校验Excel与Hive表结构' WHERE id=? AND status='queued'",
                (started_at, row["id"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return None
            connection.commit()
            result = dict(row)
            result.update(status="running", started_at=started_at, message="正在校验Excel与Hive表结构")
            return result
        finally:
            connection.close()

    def append_log(self, job_id: str, message: str) -> None:
        safe = " ".join(str(message).replace("\x00", "").splitlines()).strip()[:1000]
        if not safe:
            return
        line = f"{now_text()} {safe}"
        with self.connect() as connection:
            current = connection.execute(
                "SELECT log_text FROM risk_upload_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if current is None:
                return
            lines = (current["log_text"] + "\n" + line).strip().splitlines()[-200:]
            connection.execute(
                "UPDATE risk_upload_jobs SET log_text=? WHERE id=?",
                ("\n".join(lines), job_id),
            )

    def finish(self, job_id: str, *, success: bool, rows_read: int | None,
               rows_written: int | None, message: str) -> None:
        status = "success" if success else "failed"
        with self.connect() as connection:
            connection.execute(
                "UPDATE risk_upload_jobs SET status=?, finished_at=?, rows_read=?, "
                "rows_written=?, message=? WHERE id=?",
                (status, now_text(), rows_read, rows_written, str(message)[:1000], job_id),
            )

    def recover_interrupted(self) -> int:
        with self.connect() as connection:
            changed = connection.execute(
                "UPDATE risk_upload_jobs SET status='failed', finished_at=?, "
                "message='导入Worker重启，任务状态不确定；请先核对Hive目标表后重新上传' "
                "WHERE status='running'",
                (now_text(),),
            ).rowcount
        return changed


class RiskUploadService:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.enabled = bool(config.get("RISK_UPLOAD_ENABLED", True))
        self.token = str(config.get("RISK_UPLOAD_TOKEN", ""))
        self.max_bytes = int(config.get("RISK_UPLOAD_MAX_BYTES", 200 * 1024 * 1024))
        self.store = RiskUploadStore(str(config.get("RISK_UPLOAD_ROOT", "/app/var/risk-uploads")))

    def authorize(self, supplied_token: str | None) -> None:
        if not self.enabled:
            raise PermissionError("风控数据上传功能未启用")
        if self.token and not hmac.compare_digest(self.token, supplied_token or ""):
            raise PermissionError("导入口令不正确")

    def status(self, supplied_token: str | None = None) -> dict[str, Any]:
        definitions = [
            {
                "key": item.key,
                "label": item.label,
                "targetTable": item.target_table,
                "defaultSheet": item.default_sheet,
                "writeMode": item.write_mode,
                "requiresLoadDate": item.partition_date_required,
            }
            for item in RISK_UPLOAD_DEFINITIONS.values()
        ]
        history_authorized = not self.token or hmac.compare_digest(
            self.token, supplied_token or ""
        )
        return {
            "enabled": self.enabled,
            "tokenRequired": bool(self.token),
            "historyAuthorized": history_authorized,
            "maxFileSizeMb": self.max_bytes // (1024 * 1024),
            "definitions": definitions,
            "jobs": self.store.list_jobs() if history_authorized else [],
        }

    def submit(self, *, business_type: str, upload: FileStorage | None,
               sheet_name: str | None, load_date: str | None,
               confirmed: bool, token: str | None) -> dict[str, Any]:
        self.authorize(token)
        if not confirmed:
            raise ValueError("请先确认本次导入会覆盖Hive目标表或指定分区")
        try:
            definition = RISK_UPLOAD_DEFINITIONS[business_type]
        except KeyError:
            raise ValueError("业务类型只支持出票、退票或改签") from None
        if upload is None or not upload.filename:
            raise ValueError("请选择需要上传的Excel文件")
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            raise ValueError("只支持.xlsx或.xlsm文件")

        selected_sheet = (sheet_name or definition.default_sheet).strip()
        if not selected_sheet or len(selected_sheet) > 100 or any(ord(char) < 32 for char in selected_sheet):
            raise ValueError("工作表名称不合法")
        selected_date = None
        if definition.partition_date_required:
            try:
                selected_date = date.fromisoformat(load_date or "").isoformat()
            except ValueError:
                raise ValueError("出票导入必须填写yyyy-MM-dd格式的dt分区日期") from None

        job_id = uuid.uuid4().hex
        job_dir = self.store.root / "files" / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        stored_path = job_dir / f"source{suffix}"
        digest = hashlib.sha256()
        size = 0
        try:
            with stored_path.open("xb") as output:
                while True:
                    chunk = upload.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError(
                            f"上传文件超过{self.max_bytes // (1024 * 1024)}MB限制"
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise ValueError("上传文件为空")
            job = self.store.create_job(
                {
                    "id": job_id,
                    "business_type": business_type,
                    "target_table": definition.target_table,
                    "original_name": Path(upload.filename).name[:255],
                    "stored_path": str(stored_path),
                    "file_size": size,
                    "file_sha256": digest.hexdigest(),
                    "sheet_name": selected_sheet,
                    "load_date": selected_date,
                    "queued_at": now_text(),
                }
            )
            return job
        except Exception:
            if job_dir.exists():
                shutil.rmtree(job_dir)
            raise
