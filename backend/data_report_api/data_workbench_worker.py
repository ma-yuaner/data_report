"""Run with python -m data_report_api.data_workbench_worker.

Independent bounded worker; heavy queries run in killable spawned processes.
"""
from __future__ import annotations

import logging
import multiprocessing
import shutil
import signal
import time
from pathlib import Path

from .config import Config
from .services.workbench_service import WorkbenchService
from .services.workbench_store import WorkbenchError

LOGGER = logging.getLogger("data-workbench-worker")
STOP = False


def stop_worker(_signal, _frame):
    global STOP
    STOP = True


def execute_process(root, claim, output, temp, connection):
    try:
        from .services.workbench_engine import execute
        from .services.workbench_store import WorkbenchStore
        store = WorkbenchStore(root)
        body, owner = claim["body"], claim["owner"]
        source = store.get("dataset", body["sourceId"], owner)
        if source["_path"] != body["_source"]["path"]:
            raise WorkbenchError("源数据版本已变化", "SOURCE_CHANGED")

        def resolve(source_id):
            current = store.get("dataset", source_id, owner)
            frozen = body["_rights"].get(source_id)
            if not frozen or current["_path"] != frozen["path"]:
                raise WorkbenchError("关联源数据版本无效", "SOURCE_CHANGED")
            return frozen

        def check_cancel():
            job = store.get_job(claim["id"], owner)
            if job["status"] != "running":
                raise WorkbenchError("任务已取消", "CANCELLED")
            return False

        limits = {**body["_limits"], "temp_directory": temp}
        result = execute(body["_source"], body["steps"], resolve, output, limits=limits, check_cancel=check_cancel)
        connection.send({"result": result})
    except Exception as error:
        # Engine errors never escape as raw SQL, paths, or driver exceptions.
        from .services.workbench_engine import WorkbenchEngineError
        code = getattr(error, "code", "EXECUTION_FAILED")
        safe_error = isinstance(error, (WorkbenchEngineError, WorkbenchError))
        connection.send({"error": str(error) if safe_error else "任务执行失败，请检查步骤、字段类型及关联规模", "code": code if safe_error else "EXECUTION_FAILED",
                         "report": getattr(error, "report", None)})
    finally:
        connection.close()


def run_claim(service, claim):
    store, config = service.store, service.config
    directory = store.root / "attempts" / (claim["id"] + "-" + claim["token"])
    output = directory / "result.parquet"
    temp = directory / "temp"
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=execute_process, args=(str(store.root), claim, str(output), str(temp), child))
    started = time.monotonic()
    timeout = max(1, int(config.get("DATA_WORKBENCH_TIMEOUT", 600)))
    try:
        directory.mkdir()
        temp.mkdir()
        process.start()
        child.close()
        while True:
            status = store.heartbeat(claim["id"], claim["token"])
            if status == "lost":
                return
            if status == "cancel_requested":
                store.finish(claim["id"], claim["token"], "cancelled", {})
                return
            if STOP:
                store.finish(claim["id"], claim["token"], "failed", {"error": "执行服务已停止，请重新运行", "code": "WORKER_STOPPED"})
                return
            if time.monotonic() - started > timeout:
                store.finish(claim["id"], claim["token"], "failed", {"error": "任务超时，请缩小范围或简化步骤", "code": "TIMEOUT"})
                return
            if parent.poll(0.5):
                try:
                    message = parent.recv()
                except EOFError:
                    message = {"error": "计算进程异常退出，请重试", "code": "WORKER_INTERRUPTED"}
                if "result" in message:
                    result = message["result"]
                    store.finish(claim["id"], claim["token"], "succeeded", {
                        "fields": result["fields"], "rowCount": result["rowCount"], "report": result.get("report", {})}, staged=output)
                else:
                    store.finish(claim["id"], claim["token"], "failed", {k: v for k, v in message.items() if v is not None})
                return
            if not process.is_alive():
                store.finish(claim["id"], claim["token"], "failed", {"error": "计算进程异常退出，请重试", "code": "WORKER_INTERRUPTED"})
                return
    except Exception:
        LOGGER.exception("Workbench job failed: %s", claim["id"])
        store.finish(claim["id"], claim["token"], "failed", {"error": "任务执行异常，请重试", "code": "WORKER_ERROR"})
    finally:
        parent.close()
        child.close()
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join(5)
        # Only the uniquely owned attempt directory is removed; sources/results remain.
        if directory.parent == store.root / "attempts" and directory.name == claim["id"] + "-" + claim["token"]:
            shutil.rmtree(directory, ignore_errors=True)


def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    config = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    # Config class may not define optional knobs; environment works for the worker.
    import os
    for key, value in os.environ.items():
        if key.startswith("DATA_WORKBENCH_"):
            config[key] = value
    service = WorkbenchService(config, 0, str(Path(__file__).resolve().parents[1] / "instance"))
    LOGGER.info("Workbench worker started (single-host shared directory)")
    while not STOP:
        claim = service.store.claim(concurrency=max(1, int(config.get("DATA_WORKBENCH_CONCURRENCY", 1))))
        if claim:
            run_claim(service, claim)
        else:
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
