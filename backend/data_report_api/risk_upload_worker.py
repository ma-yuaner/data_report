from __future__ import annotations

import logging
import signal
import time
from pathlib import Path
from typing import Any

from .config import Config
from .services.risk_upload import RiskUploadStore
from .services.risk_upload_definitions import RISK_UPLOAD_DEFINITIONS
from .services.risk_upload_loader import load_excel_to_hive


LOGGER = logging.getLogger("risk-upload-worker")
STOP = False


def config_dict() -> dict[str, Any]:
    return {
        name: getattr(Config, name)
        for name in dir(Config)
        if name.isupper() and not name.startswith("_")
    }


def stop_worker(_signal: int, _frame: Any) -> None:
    global STOP
    STOP = True


def cleanup_upload(store: RiskUploadStore, job: dict[str, Any]) -> None:
    path = Path(job["stored_path"]).resolve()
    files_root = (store.root / "files").resolve()
    if files_root not in path.parents or path.parent.name != job["id"]:
        LOGGER.error("Refusing to clean an unexpected upload path for job %s", job["id"])
        return
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except OSError:
        LOGGER.warning("Unable to remove upload file for job %s", job["id"])


def run_job(store: RiskUploadStore, job: dict[str, Any], config: dict[str, Any]) -> None:
    definition = RISK_UPLOAD_DEFINITIONS[job["business_type"]]
    rows_read = None
    rows_written = None

    def task_log(message: str) -> None:
        store.append_log(job["id"], message)
        LOGGER.info("job=%s %s", job["id"], message)

    try:
        task_log(f"开始处理{definition.label}Excel：{job['original_name']}")
        rows_read, rows_written = load_excel_to_hive(
            definition=definition,
            excel_path=job["stored_path"],
            sheet_name=job["sheet_name"],
            load_date=job["load_date"],
            config=config,
            log=task_log,
        )
        message = f"{definition.label}导入完成：Hive正式表{rows_written:,}行"
        task_log(message)
        store.finish(
            job["id"], success=True, rows_read=rows_read,
            rows_written=rows_written, message=message,
        )
    except Exception as error:
        if isinstance(error, (ValueError, RuntimeError, FileNotFoundError)):
            message = str(error)
        else:
            message = f"{type(error).__name__}，请查看Worker服务日志"
        task_log(f"任务失败：{message}")
        store.finish(
            job["id"], success=False, rows_read=rows_read,
            rows_written=rows_written, message=message,
        )
        LOGGER.exception("Risk upload job %s failed", job["id"])
    finally:
        cleanup_upload(store, job)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    config = config_dict()
    store = RiskUploadStore(Config.RISK_UPLOAD_ROOT)
    recovered = store.recover_interrupted()
    if recovered:
        LOGGER.warning("Marked %s interrupted upload jobs as failed", recovered)
    poll_seconds = max(1, int(Config.RISK_UPLOAD_POLL_SECONDS))
    LOGGER.info("Risk upload worker started; poll=%ss", poll_seconds)
    while not STOP:
        job = store.claim_next()
        if job is None:
            time.sleep(poll_seconds)
            continue
        run_job(store, job, config)
    LOGGER.info("Risk upload worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
