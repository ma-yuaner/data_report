"""Register one saved parsing intake as a master ADM, without model calls or new tables."""
import copy
import hashlib
import json
from types import SimpleNamespace

from ..admwf.policy import AdmError, has, require
from ..admwf.service import AdmWorkflowService, _json_value
from .service import stamp


def pending(service, user, search="", page=1):
    owner = service.actor(user)
    require(user, "adm.create")
    if type(page) is not int or not 1 <= page <= 10000 or len(search) > 100:
        raise AdmError("待登记查询参数无效", 422, "PARSE_QUERY")
    store = service.store
    where = "state='SUCCEEDED' AND JSON_EXTRACT(payload,'$.registration.caseId') IS NULL"
    params = []
    if not has(user, "adm.manage"):
        where += " AND owner_id=?"
        params.append(owner)
    if search.strip():
        # JSON_EXTRACT is supported by both the production MySQL and isolated SQLite store.
        contains = "INSTR" if store.sqlite else "LOCATE"
        fields = ("$.candidate.adm.number", "$.files", "$.airlineMatch.name", "$.candidate.adm.airlineCode")
        clauses = []
        for field in fields:
            expression = f"LOWER(COALESCE(JSON_EXTRACT(payload,'{field}'),''))"
            clauses.append(f"{contains}({expression},?)>0" if store.sqlite else f"{contains}(?,{expression})>0")
            params.append(search.strip().lower())
        where += " AND (" + " OR ".join(clauses) + ")"
    with store.db() as conn:
        total = store.query(conn, "SELECT COUNT(*) AS total FROM adm_parse_task WHERE " + where, params).fetchone()["total"]
        rows = store.query(conn, "SELECT payload FROM adm_parse_task WHERE " + where + " ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?", (*params, 20, (page - 1) * 20)).fetchall()
    items = []
    for row in rows:
        task = json.loads(row["payload"])
        item = service._public(task)
        item["adm"] = task.get("candidate", {}).get("adm", {})
        item["warningCount"] = sum(i["level"] == "warning" for i in task.get("issues", []))
        items.append(item)
    return {"items": items, "total": total, "page": page, "pageSize": 20}


def register(service, user, task_id, body):
    require(user, "adm.create")
    service._get(user, task_id, True)
    if service.store.sqlite:
        raise AdmError("登记台账需使用正式ADM数据库", 503, "PARSE_REGISTER_STORAGE")
    workflow = AdmWorkflowService(service.config)
    actor = workflow._actor(user)
    # File copies are staged before commit, and metadata/link/case are committed together.
    # On an ambiguous COMMIT failure copies are kept; deleting them could damage a committed case.
    with workflow.repository.transaction() as conn:
        row = service.store.query(conn, "SELECT payload FROM adm_parse_task WHERE id=? FOR UPDATE", (task_id,)).fetchone()
        if not row:
            raise AdmError("解析来件不存在", 404, "PARSE_NOT_FOUND")
        task = json.loads(row["payload"])
        if task["ownerId"] != str(user["id"]) and not has(user, "adm.manage"):
            raise AdmError("无权登记该来件", 403, "PARSE_FORBIDDEN")
        if task.get("registration"):
            return {"registration": task["registration"], "alreadyRegistered": True}
        if type(body.get("version")) is not int or body["version"] != task["version"]:
            raise AdmError("解析结果已更新，请重新选择来件核对", 409, "PARSE_VERSION_CONFLICT")
        if task["state"] != "SUCCEEDED" or task.get("saveStatus") != "SAVED" or any(i["level"] == "error" for i in task.get("issues", [])):
            raise AdmError("请先完成解析校验并保存，再登记台账", 409, "PARSE_NOT_READY")
        if body.get("confirmed") is not True:
            raise AdmError("请核对带入字段、原件和待核对提示后确认登记", 422, "PARSE_CONFIRM_REQUIRED")
        form = body.get("form")
        if not isinstance(form, dict):
            raise AdmError("缺少台账登记内容", 422, "PARSE_REGISTER_FORM")
        # Master intake does not invent financial allocations or recover PNRs from parsed lines.
        form = {**form, "masterOnly": True, "saveAsDraft": False}
        data, fx, _ = workflow._prepare_create_case(form)
        source = {"taskId": task_id, "version": task["version"], "registeredAt": stamp(),
                  "candidate": copy.deepcopy(task["candidate"]), "issues": copy.deepcopy(task.get("issues", [])),
                  "segments": copy.deepcopy(task.get("segments", [])),
                  "relatedDocuments": task.get("relatedDocuments", []), "attachmentFees": task.get("attachmentFees", []),
                  "files": service._public(task)["files"], "airlineMatch": task.get("airlineMatch")}
        data["lineDefaults"]["parsingSource"] = source
        fingerprint = hashlib.sha256(json.dumps(sorted(f["sha256"] for f in task["files"])).encode()).hexdigest()
        try:
            result = workflow.repository.create_case(data, fx, actor, idempotency_key="adm-parse-" + fingerprint, connection=conn)
        except Exception as error:
            if error.args and error.args[0] in {1062, 1213}:
                raise AdmError("相同原件正在登记，请稍后刷新并再次确认关联结果", 409, "PARSE_REGISTER_CONFLICT") from error
            raise
        case = result["case"]
        existing_source = (case.get("lineDefaults") or {}).get("parsingSource") or {}
        reuse = existing_source.get("taskId") != task_id
        if reuse and case.get("case_status") not in {"ACTIVE", "DRAFT"}:
            raise AdmError("相同原件已登记且台账已结束，请联系负责人核对", 409, "PARSE_DUPLICATE_CLOSED")
        copied = []
        try:
            for file in ([] if reuse else task["files"]):
                path = service._path(file["storageKey"])
                with path.open("rb") as stream:
                    metadata = workflow.attachment_storage.save(case["id"], SimpleNamespace(filename=file["name"], stream=stream))
                copied.append(metadata)
                if metadata["sha256"] != file["sha256"] or metadata["fileSize"] != file["size"]:
                    raise AdmError("原件与上传记录不一致，已取消登记", 422, "PARSE_FILE_CHANGED")
                workflow.repository.add_attachment(case["id"], actor, "ADM_ORIGINAL", metadata, connection=conn)
            registration = {"caseId": case["id"], "internalNo": case["internal_no"],
                            "at": source["registeredAt"], "by": actor["name"], "sourceVersion": task["version"]}
            old = task["version"]
            task.update(registration=registration, version=old + 1, updatedAt=stamp())
            cursor = service.store.query(conn, "UPDATE adm_parse_task SET version_no=?,updated_at=?,payload=? WHERE id=? AND version_no=?", (task["version"], task["updatedAt"], json.dumps(task, ensure_ascii=False, allow_nan=False), task_id, old))
            if cursor.rowcount != 1:
                raise AdmError("来件版本已变化，已取消登记", 409, "PARSE_VERSION_CONFLICT")
            workflow.repository.append_operation_log(conn, case_id=case["id"], line_id=None,
                event_no=workflow.repository._next_event_no(conn, case["id"]), event_type="REGISTER_PARSE_INTAKE",
                operator_id=actor["id"], operator_name=actor["name"], after={"sourceTaskId": task_id, "sourceVersion": old},
                changed_fields=["parsingSource", "attachments"], operation_source="WEB")
        except Exception:
            for metadata in copied:
                workflow.attachment_storage.path(metadata["storageKey"]).unlink(missing_ok=True)
            raise
    return {"registration": _json_value(registration), "alreadyRegistered": reuse}
