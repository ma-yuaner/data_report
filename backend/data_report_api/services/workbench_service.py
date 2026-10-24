"""Owner-scoped workbench application service; no business database writes."""
from __future__ import annotations

import copy
import multiprocessing
import time
from pathlib import Path

from .workbench_store import WorkbenchError, WorkbenchStore, uid, utc


OPERATORS = ["trim", "replace", "cast", "filter", "derive", "group", "join", "append", "select"]


def public(body):
    return {key: value for key, value in body.items() if not key.startswith("_")}


def import_process(source, output, sheet, limits, connection):
    try:
        from .workbench_engine import import_dataset
        connection.send({"result": import_dataset(source, output, sheet_name=sheet, limits=limits)})
    except Exception as error:
        from .workbench_engine import WorkbenchEngineError
        safe = isinstance(error, WorkbenchEngineError)
        connection.send({"error": str(error) if safe else "文件解析失败，请检查格式、工作表和文件限制", "code": error.code if safe else "IMPORT_FAILED"})
    finally:
        connection.close()


class WorkbenchService:
    def __init__(self, config, owner, instance_path=None):
        self.config = config
        self.owner = int(owner)
        self.store = WorkbenchStore(config.get("DATA_WORKBENCH_DIR") or str(Path(instance_path or "instance") / "data-workbench"))
        self.limits = {
            "max_rows": int(config.get("DATA_WORKBENCH_MAX_ROWS", 2_000_000)),
            "max_columns": int(config.get("DATA_WORKBENCH_MAX_COLUMNS", 300)),
            "max_join_rows": int(config.get("DATA_WORKBENCH_MAX_JOIN_ROWS", 3_000_000)),
            "max_output_rows": int(config.get("DATA_WORKBENCH_MAX_OUTPUT_ROWS", 3_000_000)),
            "max_join_expansion": float(config.get("DATA_WORKBENCH_MAX_JOIN_EXPANSION", 5)),
            "memory_limit": str(config.get("DATA_WORKBENCH_MEMORY_LIMIT", "512MB")),
            "threads": int(config.get("DATA_WORKBENCH_THREADS", 2)),
            "max_temp_directory_size": str(config.get("DATA_WORKBENCH_TEMP_LIMIT", "2GB")),
            "max_file_bytes": int(config.get("DATA_WORKBENCH_UPLOAD_BYTES", 200 * 1024 * 1024)),
        }

    def source(self, source_id):
        body = self.store.get("dataset", self.identifier(source_id), self.owner)
        return {"path": body["_path"], "fields": body["fields"], "rowCount": body["rowCount"]}

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise WorkbenchError("资源标识无效")
        return value

    @staticmethod
    def name(value, default):
        value = str(value or default).strip()
        if not value or len(value) > 120:
            raise WorkbenchError("名称长度必须为1至120字符")
        return value

    def validate(self, source_id, steps):
        source = self.source(source_id)
        if not isinstance(steps, list) or len(steps) > 50:
            raise WorkbenchError("步骤必须为列表且最多50步")
        if len(str(steps)) > 200_000:
            raise WorkbenchError("步骤配置过大")
        ids = set()
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("op") not in OPERATORS:
                raise WorkbenchError(f"第{index + 1}步操作不支持", "INVALID_STEP")
            sid = step.get("id")
            if not isinstance(sid, str) or not sid or len(sid) > 64 or not all(c.isalnum() or c in "_-" for c in sid) or sid in ids:
                raise WorkbenchError(f"第{index + 1}步标识无效或重复", "INVALID_STEP")
            ids.add(sid)
            if step["op"] in ("join", "append"):
                self.source(step.get("rightSourceId"))
        return source

    def catalog(self):
        return {"datasets": [public(x) for x in self.store.list("dataset", self.owner)],
                "recipes": self.store.list("recipe", self.owner),
                "jobs": [public(x) for x in self.store.list_jobs(self.owner)],
                "operators": OPERATORS, "limits": {**self.limits, "previewRows": 200, "maxSteps": 50,
                    "uploadBytes": int(self.config.get("DATA_WORKBENCH_UPLOAD_BYTES", 200 * 1024 * 1024))}}

    def upload(self, upload, name=None, sheet=None):
        if not upload or not upload.filename:
            raise WorkbenchError("请选择CSV或XLSX文件")
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in (".csv", ".xlsx"):
            raise WorkbenchError("仅支持CSV和XLSX", "UNSUPPORTED_FILE")
        if sheet is not None and (not isinstance(sheet, str) or len(sheet) > 100):
            raise WorkbenchError("工作表名称无效")
        token, resource_id = uid(), uid()
        timeout = max(1, min(600, int(self.config.get("DATA_WORKBENCH_IMPORT_TIMEOUT", 300))))
        if not self.store.acquire_slot("import", token, timeout + 60):
            raise WorkbenchError("当前已有文件导入，请稍后重试", "IMPORT_BUSY", 429)
        source = self.store.root / "uploads" / (resource_id + suffix)
        target = self.store.root / "sources" / (resource_id + ".parquet")
        successful = False
        process = None
        started = time.monotonic()
        try:
            title = self.name(name, Path(upload.filename).stem)
            maximum = int(self.config.get("DATA_WORKBENCH_UPLOAD_BYTES", 200 * 1024 * 1024))
            size = 0
            with source.open("xb") as stream:
                while True:
                    if time.monotonic() - started > timeout:
                        raise WorkbenchError("上传超时，请重新上传", "UPLOAD_TIMEOUT", 408)
                    chunk = upload.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > maximum:
                        raise WorkbenchError("文件超过上传大小限制", "UPLOAD_TOO_LARGE", 413)
                    stream.write(chunk)
            if not size:
                raise WorkbenchError("文件为空")
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=import_process, args=(str(source), str(target), sheet or None, self.limits, child))
            process.start()
            child.close()
            if not parent.poll(max(0, timeout - (time.monotonic() - started))):
                raise WorkbenchError("导入超时，请拆分文件后重试", "IMPORT_TIMEOUT", 408)
            try:
                message = parent.recv()
            except EOFError:
                raise WorkbenchError("导入进程中断，请重试", "IMPORT_FAILED") from None
            finally:
                parent.close()
            process.join(5)
            if "error" in message:
                raise WorkbenchError(message["error"], message["code"])
            result = message["result"]
            body = {"id": resource_id, "name": title, "fields": result["fields"], "rowCount": result["rowCount"],
                    "quality": result.get("quality", {}), "createdAt": utc(), "_path": str(target), "_original": str(source)}
            self.store.insert("dataset", self.owner, body)
            successful = True
            return public(body)
        finally:
            if process and process.is_alive():
                process.terminate()
                process.join(5)
            if not successful:
                source.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
            self.store.release_slot("import", token)

    def save_recipe(self, values, recipe_id=None):
        source_id, steps = values.get("sourceId"), values.get("steps", [])
        self.validate(source_id, steps)
        body = {"id": self.identifier(recipe_id) if recipe_id else uid(), "name": self.name(values.get("name"), "未命名流程"),
                "sourceId": source_id, "steps": copy.deepcopy(steps), "revision": 1, "createdAt": utc(), "updatedAt": utc()}
        if recipe_id:
            revision = values.get("revision")
            if not isinstance(revision, int) or isinstance(revision, bool):
                raise WorkbenchError("缺少有效流程版本")
            return self.store.update_recipe(self.owner, body, revision)
        return self.store.insert("recipe", self.owner, body)

    def copy_recipe(self, recipe_id, name=None):
        old = self.store.get("recipe", self.identifier(recipe_id), self.owner)
        return self.save_recipe({**old, "name": name or (old["name"][:110] + " 副本")})

    def submit(self, values):
        source_id, steps = values.get("sourceId"), values.get("steps", [])
        source = self.validate(source_id, steps)
        kind = values.get("kind", "run")
        if kind not in ("run", "preview"):
            raise WorkbenchError("任务类型无效")
        recipe_id = values.get("recipeId")
        if recipe_id:
            recipe = self.store.get("recipe", self.identifier(recipe_id), self.owner)
            if values.get("recipeRevision") != recipe["revision"]:
                raise WorkbenchError("流程版本已变化，请刷新后提交", "REVISION_CONFLICT", 409)
        rights = {step["rightSourceId"]: self.source(step["rightSourceId"]) for step in steps if step["op"] in ("join", "append")}
        body = {"id": uid(), "kind": kind, "sourceId": source_id, "steps": copy.deepcopy(steps),
                "createdAt": utc(), "updatedAt": utc(), "_source": source, "_rights": rights,
                "_limits": copy.deepcopy(self.limits), "recipeId": recipe_id, "recipeRevision": values.get("recipeRevision")}
        return public(self.store.enqueue(self.owner, body))

    def job(self, job_id):
        return public(self.store.get_job(self.identifier(job_id), self.owner))

    @staticmethod
    def page(offset, limit):
        try:
            offset, limit = int(offset), int(limit)
        except (TypeError, ValueError):
            raise WorkbenchError("分页参数无效") from None
        if offset < 0 or limit < 1 or limit > 200:
            raise WorkbenchError("offset需非负，limit范围1至200")
        return offset, limit

    def dataset_preview(self, source_id, offset=0, limit=100):
        from .workbench_engine import preview
        source = self.source(source_id)
        offset, limit = self.page(offset, limit)
        return preview(source["path"], source["fields"], offset=offset, limit=limit, scope="source")

    def completed(self, job_id):
        body = self.store.get_job(self.identifier(job_id), self.owner)
        if body["status"] != "succeeded":
            raise WorkbenchError("任务尚未成功，结果不可用", "RESULT_NOT_READY", 409)
        # Re-authorize every frozen reference, not just the job itself.
        self.source(body["sourceId"])
        for step in body["steps"]:
            if step["op"] in ("join", "append"):
                self.source(step["rightSourceId"])
        return body

    def job_preview(self, job_id, offset=0, limit=100):
        from .workbench_engine import preview
        body = self.completed(job_id)
        offset, limit = self.page(offset, limit)
        return preview(body["_path"], body["fields"], offset=offset, limit=limit,
                       scope="preview" if body["kind"] == "preview" else "full", report=body.get("report"))

    def download(self, job_id):
        from .workbench_engine import export_csv
        body = self.completed(job_id)
        return export_csv(body["_path"], body["fields"])

    def publish(self, job_id, name=None):
        body = self.completed(job_id)
        return public(self.store.publish(body["id"], self.owner, self.name(name, "加工结果")))
