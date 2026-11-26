"""Real upload/read/model/validate/save pipeline, isolated from existing ADM cases."""
import copy
import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from ..admwf.policy import AdmError, business_now, has
from .classification import suggest
from ..admwf.catalog import AdmCatalog
from .contract import VERSION, template, validate
from .recheck import VALIDATION_VERSION, prepare, related_documents
from .table_sources import fee_details
from .documents import EXTENSIONS, extract
from .model import PROMPT_VERSION, ParsingModel
from .store import ParsingStore

_lock = threading.Lock()
_workers = set()


def stamp():
    return business_now().isoformat(sep=" ", timespec="seconds")


class ParsingService:
    def __init__(self, config):
        self.config = config
        self.root = Path(config["ADM_PARSING_ROOT"]).resolve()
        self.store = ParsingStore(config)

    def actor(self, user, write=False):
        local = self.config.get("TESTING") and user and user.get("is_admin") and user.get("id") == 0
        if not user or not user.get("id") and not local:
            raise AdmError("请先登录", 401, "PARSE_AUTH")
        if not has(user, "adm.view") or write and not (has(user, "adm.create") or has(user, "adm.manage")):
            raise AdmError("无ADM解析操作权限", 403, "PARSE_FORBIDDEN")
        return str(user["id"])

    def status(self, user):
        self.actor(user)
        self.wake()
        return {"ai": ParsingModel(self.config).status(), "schemaVersion": VERSION, "template": template(),
                "localTesting": bool(self.config.get("TESTING")),
                "canUpload": has(user, "adm.create") or has(user, "adm.manage"), "extensions": sorted(EXTENSIONS),
                "maxFiles": 10, "maxFileBytes": 20 * 1024 * 1024,
                "notice": "API配置仅在服务器环境变量中设置；解析只提取材料，不恢复PNR或变更原有ADM业务"}

    def _get(self, user, task_id, write=False):
        actor = self.actor(user, write)
        if not re.fullmatch(r"[a-f0-9]{32}", str(task_id)):
            raise AdmError("解析任务不存在", 404, "PARSE_NOT_FOUND")
        task = self.store.get(task_id)
        if not task or task["state"] == "DELETED" or task["ownerId"] != actor and not has(user, "adm.manage"):
            raise AdmError("解析任务不存在或无权查看", 404, "PARSE_NOT_FOUND")
        return task

    def _path(self, key):
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise AdmError("解析文件路径无效", 400, "PARSE_FILE_PATH")
        return path

    def _checkpoint_path(self, task_id):
        return self.root / "checkpoints" / (task_id + ".json")

    def _checkpoint(self, task, failed=False):
        path = self._checkpoint_path(task["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        envelope = {"task": task, "failed": failed, "createdAt": stamp()}
        temporary.write_text(json.dumps(envelope, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)

    def _pending_save(self, task):
        path = self._checkpoint_path(task["id"])
        if task["state"] == "RUNNING" and path.is_file():
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if not envelope["failed"] and datetime.fromisoformat(envelope["createdAt"]) > business_now() - timedelta(minutes=2):
                return None
            result = envelope["task"]
            if result["version"] == task["version"] + 1 and result.get("attemptId") == task.get("attemptId"):
                return result
        return None

    def _public(self, task, detail=False):
        result = copy.deepcopy(task)
        if detail:
            result["classification"] = suggest(result.get("candidate"))
        if task.get("startedAt"):
            end = business_now() if task["state"] in {"QUEUED", "RUNNING"} else datetime.fromisoformat(task.get("finishedAt") or task["updatedAt"])
            result["elapsedSeconds"] = max(0, int((end - datetime.fromisoformat(task["startedAt"])).total_seconds()))
        result.pop("requestHash", None)
        result.pop("attemptId", None)
        for file in result["files"]:
            file.pop("storageKey", None)
        if not detail:
            for key in ("segments", "candidate", "issues", "history", "originalCandidate", "revalidationHistory", "adjustments", "relatedDocuments", "attachmentFees"):
                result.pop(key, None)
        return result

    def detail(self, user, task_id):
        task = self._get(user, task_id)
        if task["state"] == "QUEUED":
            self.wake()
        pending = self._pending_save(task)
        if pending:
            result = self._public(pending, True)
            result["version"] = task["version"]
            result["saveStatus"] = "FAILED"
            return result
        if task["state"] == "RUNNING" and datetime.fromisoformat(task["updatedAt"]) < business_now() - timedelta(minutes=10):
            old = task["version"]
            task.update(state="FAILED", error={"code": "PARSE_INTERRUPTED", "message": "解析进程中断或超过10分钟，请显式重试；未自动重复调用模型"}, version=old+1, updatedAt=stamp())
            self.store.save(task, old)
        return {
            **self._public(task, True),
            "canDelete": (has(user, "adm.create") or has(user, "adm.manage"))
            and not task.get("registration") and task["state"] not in {"QUEUED", "RUNNING"},
        }

    def delete(self, user, task_id, version):
        task = self._get(user, task_id, True)
        if type(version) is not int or task["version"] != version:
            raise AdmError("任务版本已改变，请刷新后再试", 409, "PARSE_VERSION_CONFLICT")
        if task.get("registration"):
            raise AdmError("来件已登记台账，无法删除", 409, "PARSE_ALREADY_REGISTERED")
        if task["state"] in {"QUEUED", "RUNNING"}:
            raise AdmError("请等待解析结束后再删除", 409, "PARSE_BUSY")
        task.update(state="DELETED", version=version + 1, updatedAt=stamp(), deletedBy=str(user["id"]))
        self.store.save(task, version)

    def list(self, user, page=1, size=20, state=""):
        owner = self.actor(user)
        if type(page) is not int or type(size) is not int or page < 1 or not 1 <= size <= 100 or page > 10000:
            raise AdmError("分页参数无效", 400, "PARSE_PAGE")
        if state not in {"", "UPLOADED", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"}:
            raise AdmError("解析状态无效", 400, "PARSE_STATE")
        items, total = self.store.list(None if has(user, "adm.manage") else owner, page, size, state)
        for i, task in enumerate(items):
            pending = self._pending_save(task)
            if pending:
                pending.update(version=task["version"], saveStatus="FAILED")
                items[i] = pending
        return {"items": [self._public(t) for t in items], "total": total, "page": page, "pageSize": size}

    def upload(self, user, uploads, key):
        actor = self.actor(user, True)
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", str(key or "")):
            raise AdmError("缺少有效上传请求标识", 422, "PARSE_REQUEST_KEY")
        if not 1 <= len(uploads) <= 10:
            raise AdmError("每件请选择1至10份材料", 422, "PARSE_FILE_COUNT")
        task_id, files, total = uuid.uuid4().hex, [], 0
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            for upload in uploads:
                name = str(upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
                extension = Path(name).suffix.lower()
                if not name or len(name) > 240 or any(ord(c) < 32 for c in name) or extension not in EXTENSIONS:
                    raise AdmError("文件名或格式无效，支持PDF、XLSX、TXT、CSV、DOCX；旧XLS请另存为XLSX", 422, "PARSE_FILE_TYPE")
                file_id = uuid.uuid4().hex
                storage_key = f"files/{task_id}/{file_id}{extension}"
                path = self._path(storage_key)
                path.parent.mkdir(parents=True, exist_ok=True)
                size, digest = 0, hashlib.sha256()
                files.append({"id": file_id, "name": name, "storageKey": storage_key})
                with path.open("xb") as target:
                    while chunk := upload.stream.read(65536):
                        size += len(chunk)
                        total += len(chunk)
                        if size > 20 * 1024 * 1024 or total > 50 * 1024 * 1024:
                            raise AdmError("单份文件上限20MB，单件合计上限50MB", 413, "PARSE_FILE_LIMIT")
                        digest.update(chunk)
                        target.write(chunk)
                if not size:
                    raise AdmError("不能上传空文件", 422, "PARSE_FILE_EMPTY")
                files[-1].update(size=size, sha256=digest.hexdigest())
            fingerprint = hashlib.sha256(json.dumps([(f["name"], f["sha256"]) for f in files], ensure_ascii=False).encode()).hexdigest()
            task = {"id": task_id, "ownerId": actor, "title": files[0]["name"], "version": 1, "state": "UPLOADED", "createdAt": stamp(), "updatedAt": stamp(),
                    "files": files, "requestHash": fingerprint, "segments": [], "candidate": None, "issues": [], "history": [], "attempts": 0, "error": None, "saveStatus": "SAVED"}
            result = self.store.create(task, key, fingerprint)
            if result["state"] == "DELETED":
                raise AdmError("该上传请求对应的来件已删除，请重新打开上传窗口", 409, "PARSE_DELETED")
            if result["id"] != task_id:
                for f in files:
                    self._path(f["storageKey"]).unlink(missing_ok=True)
            return self._public(result, True)
        except Exception:
            for f in files:
                self._path(f["storageKey"]).unlink(missing_ok=True)
            raise

    def enqueue(self, user, task_id, version):
        task = self._get(user, task_id, True)
        if task.get("registration"):
            raise AdmError("来件已登记台账，请在台账办理；解析快照已保留", 409, "PARSE_ALREADY_REGISTERED")
        if type(version) is not int or task["version"] != version:
            raise AdmError("任务版本已改变，请刷新后再试", 409, "PARSE_VERSION_CONFLICT")
        if task["state"] in {"QUEUED", "RUNNING"}:
            return self._public(task, True)
        if task["attempts"] >= 10:
            raise AdmError("单件已达10次解析上限，请检查材料与配置", 429, "PARSE_ATTEMPT_LIMIT")
        if task["attempts"]:
            task["history"].append({"at": stamp(), "attempt": task["attempts"], "state": task["state"], "candidate": task["candidate"], "issues": task["issues"], "error": task.get("error"), "usage": task.get("usage"), "originalCandidate": task.get("originalCandidate"), "adjustments": task.get("adjustments"), "airlineMatch": task.get("airlineMatch")})
            task["history"][-1].update({key: task.get(key) for key in (
                "model", "responseModel", "promptVersion", "validationVersion", "outputFormat", "schemaMatched",
            )})
        task.update(stage="QUEUED", startedAt=None, finishedAt=None, originalCandidate=None, adjustments=[], airlineMatch=None, relatedDocuments=[], attachmentFees=[], state="QUEUED", version=version+1, updatedAt=stamp(), candidate=None, issues=[], error=None, usage=None, saveStatus="SAVED")
        task.update(outputFormat=None, schemaMatched=None, responseModel=None)
        self.store.save(task, version)
        self.wake()
        return self._public(task, True)

    def process(self, task_id):
        task = self.store.get(task_id)
        if not task or task["state"] != "QUEUED":
            return
        expected = task["version"]
        task.update(stage="READING", startedAt=stamp(), state="RUNNING", version=expected+1, updatedAt=stamp(), attemptId=uuid.uuid4().hex, attempts=task["attempts"]+1)
        self.store.save(task, expected)
        expected = task["version"]
        def advance(stage):
            nonlocal expected
            task.update(stage=stage, version=expected+1, updatedAt=stamp())
            self.store.save(task, expected)
            expected = task["version"]

        model = ParsingModel(self.config)
        try:
            for file in task["files"]:
                if hashlib.sha256(self._path(file["storageKey"]).read_bytes()).hexdigest() != file["sha256"]:
                    raise AdmError("原件内容与上传时不一致，已阻止调用模型，请重新上传", 422, "PARSE_FILE_CHANGED")
            task["segments"] = extract(task["files"], self.root, int(self.config.get("ADM_PARSING_MAX_INPUT_CHARS", 60000)))
            advance("MODEL")
            task["candidate"], task["usage"] = model.call(task["files"], task["segments"])
            advance("VALIDATING")
            self._evaluate(task)
            task["state"] = "FAILED" if any(i["level"] == "error" for i in task["issues"]) else "SUCCEEDED"
            task["error"] = {"code": "PARSE_VALIDATION_FAILED", "message": "返回字段未通过校验，请查看明细后重试"} if task["state"] == "FAILED" else None
        except AdmError as error:
            task.update(state="FAILED", error={"code": error.code, "message": error.message})
        except Exception:
            task.update(state="FAILED", error={"code": "PARSE_INTERNAL", "message": "解析处理失败，请检查材料或联系管理员"})
            logging.error("ADM parsing task failed; no document content logged")
        task.update(stage="FINISHED", finishedAt=stamp(), version=expected+1, updatedAt=stamp(),
                    model=model.status()["model"], responseModel=model.response_model,
                    promptVersion=PROMPT_VERSION, validationVersion=VALIDATION_VERSION,
                    outputFormat=model.output_format, schemaMatched=model.schema_matched)
        self._checkpoint(task)
        try:
            self.store.save(task, expected)
            self._checkpoint_path(task_id).unlink(missing_ok=True)
        except Exception:
            self._checkpoint(task, failed=True)
            logging.error("ADM parsing save failed; durable checkpoint retained for explicit save retry")

    def _evaluate(self, task):
        original = task.get("originalCandidate")
        if original is None:
            original = copy.deepcopy(task.get("candidate"))
            task["originalCandidate"] = original
        task["candidate"], task["adjustments"] = prepare(original, task["segments"])
        task["relatedDocuments"] = related_documents(task["segments"])
        task["attachmentFees"] = fee_details(task["candidate"], task["segments"])
        task["validationVersion"] = VALIDATION_VERSION
        task["issues"] = validate(task["candidate"], task["segments"])
        candidate = task["candidate"]
        adm = candidate.get("adm") if isinstance(candidate, dict) else None
        code = adm.get("airlineCode") if isinstance(adm, dict) else None
        matched = {"sourceCode": code, "status": "NOT_PROVIDED", "code": None, "name": None}
        if code and isinstance(code, str) and re.fullmatch(r"[0-9]{3}|[A-Z0-9]{2}", code):
            if any(i["level"] == "error" and i["path"] == "/adm/airlineCode" for i in task["issues"]):
                matched["status"] = "SOURCE_INVALID"
            else:
                try:
                    options = AdmCatalog(self.config).document_airline_options(code)
                    # A three-digit Airline Code is matched to ticketingCode, never to a name substring.
                    field = "ticketingCode" if len(code) == 3 else "code"
                    def source_key(row):
                        token = str(row.get(field) or "").strip().upper()
                        if field == "ticketingCode" and token.isascii() and token.isdigit() and len(token) <= 3:
                            token = token.zfill(3)
                        return token
                    exact = [r for r in options if source_key(r) == code]
                    if len(exact) == 1:
                        matched.update(status="MATCHED", code=str(exact[0]["code"]), name=str(exact[0]["name"]))
                    else:
                        matched["status"] = "AMBIGUOUS" if exact else "NOT_FOUND"
                except AdmError:
                    matched["status"] = "UNAVAILABLE"
                if matched["status"] != "MATCHED":
                    message = {"UNAVAILABLE": "系统航司资料读取失败，可稍后重新校验，不调用模型", "AMBIGUOUS": "航司编码匹配到多条系统资料，待人工核对", "NOT_FOUND": "系统中未找到该Airline Code对应的启用航司"}[matched["status"]]
                    task["issues"].append({"code": "AIRLINE_" + matched["status"], "path": "/adm/airlineCode", "message": message, "level": "warning"})
        task["airlineMatch"] = matched

    def revalidate(self, user, task_id, version):
        task = self._get(user, task_id, True)
        if task.get("registration"):
            raise AdmError("来件已登记台账，登记时解析快照已保留", 409, "PARSE_ALREADY_REGISTERED")
        if type(version) is not int or task["version"] != version:
            raise AdmError("任务版本已改变，请刷新后再试", 409, "PARSE_VERSION_CONFLICT")
        if task["state"] in {"QUEUED", "RUNNING"}:
            raise AdmError("任务尚在处理，请等待完成后重新校验", 409, "PARSE_BUSY")
        if not isinstance(task.get("candidate"), dict) or not task.get("segments"):
            raise AdmError("没有已保存的模型结果及原文，无法重新校验", 422, "PARSE_NO_CANDIDATE")
        task.setdefault("revalidationHistory", []).append({"at": stamp(), "actorId": str(user["id"]), "version": version, "candidate": copy.deepcopy(task["candidate"]), "issues": copy.deepcopy(task["issues"]), "state": task["state"], "validationVersion": task.get("validationVersion")})
        task.setdefault("finishedAt", task["updatedAt"])
        self._evaluate(task)
        failed = any(i["level"] == "error" for i in task["issues"])
        task.update(state="FAILED" if failed else "SUCCEEDED", stage="FINISHED", version=version+1,
                    updatedAt=stamp(), revalidatedAt=stamp(), revalidatedById=str(user["id"]), saveStatus="SAVED",
                    error={"code": "PARSE_VALIDATION_FAILED", "message": "已有结果仍有校验问题，请核对具体字段"} if failed else None)
        self.store.save(task, version)
        return {**self._public(task, True), "canDelete": True}

    def retry_save(self, user, task_id, version):
        task = self._get(user, task_id, True)
        if task["version"] != version or type(version) is not int:
            raise AdmError("任务已更新，请先刷新", 409, "PARSE_VERSION_CONFLICT")
        pending = self._pending_save(task)
        if pending:
            self.store.save(pending, version)
            self._checkpoint_path(task_id).unlink(missing_ok=True)
        return self.detail(user, task_id)

    def file(self, user, task_id, file_id):
        task = self._get(user, task_id)
        item = next((f for f in task["files"] if f["id"] == file_id), None)
        if not item:
            raise AdmError("原件不存在", 404, "PARSE_FILE_MISSING")
        path = self._path(item["storageKey"])
        if not path.is_file():
            raise AdmError("原件不存在", 404, "PARSE_FILE_MISSING")
        return path, item["name"]

    def wake(self):
        if self.config.get("ADM_PARSING_DISABLE_BACKGROUND"):
            return
        # At most one bounded worker per configured root in each web process.
        key = str(self.root)
        with _lock:
            if key in _workers:
                return
            _workers.add(key)
        def work():
            try:
                for task_id in self.store.queued():
                    try:
                        self.process(task_id)
                    except AdmError as error:
                        if error.code != "PARSE_VERSION_CONFLICT":
                            logging.error("ADM parse worker storage unavailable: %s", error.code)
            except Exception:
                logging.error("ADM parse worker unavailable; check dedicated parsing schema and storage")
            finally:
                with _lock:
                    _workers.discard(key)
        threading.Thread(target=work, name="adm-parsing", daemon=True).start()
