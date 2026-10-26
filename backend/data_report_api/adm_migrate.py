"""Offline ADM migration preflight, default read-only. Explicit mapping; no URL downloads."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from werkzeug.datastructures import FileStorage

from .services.adm import AdmError, AdmService
from .services.adm.attachments import AdmAttachmentService, validate_document, verify_stored_attachment
from .services.adm.history import prepare
from .services.adm.service import CASE_FIELDS


def read_json(path, maximum=20971520):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise AdmError("迁移输入超过20MB上限")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_float=str)


def plan_bundle(erp, mapping, recovery_path=None, logs=None, attachment_root=None, config=None):
    """Return an in-memory plan; no target connection, filesystem writes or imports of old app."""
    if not isinstance(erp, list) or not 1 <= len(erp) <= 10000 or not isinstance(mapping, dict):
        raise AdmError("ERP须为1~10000条JSON数组；mapping须为对象")
    service = AdmService(config or {"ADM_STORAGE_MODE": "mysql"})
    cases, errors = {}, []
    for number, raw in enumerate(erp, 1):
        try:
            body, history = prepare(raw)
            if history["oldId"] in cases:
                raise AdmError("ERP原ID重复，不允许自动合并")
            if not body["admNo"] or not body["supplierName"]:
                raise AdmError("缺少ADM号或供应商")
            service._clean(body, CASE_FIELDS)
            service._new_line(body, body["lines"][0], historical=True)
            history.update(pythonRecovery=[], legacyLogs=[], migrationFiles=[])
            cases[history["oldId"]] = {"body": body, "history": history}
        except (AdmError, TypeError, ValueError):
            errors.append({"source": "erp", "row": number, "code": "INVALID_OR_DUPLICATE_RECORD"})
    recovery = []
    if recovery_path:
        source = Path(recovery_path).resolve(strict=True)
        # URI read-only prevents the previous application's schema/init/upsert side effects.
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            recovery = [dict(row) for row in connection.execute("SELECT * FROM adm_recovery_followup LIMIT 10001")]
        if len(recovery) > 10000:
            raise AdmError("旧恢复记录超过迁移容量，请分批导出")
    recovery_map = mapping.get("recoveryToErp", {})
    if not isinstance(recovery_map, dict):
        raise AdmError("recoveryToErp须为旧恢复主键到ERP主键的显式映射")
    used = set()
    for row in recovery:
        old = str(row["id"])
        target = str(recovery_map.get(old, ""))
        if target not in cases:
            errors.append({"source": "recovery", "id": old, "code": "MISSING_EXPLICIT_MAPPING"})
            continue
        if str(row.get("adm_record_id")) != target:
            errors.append({"source": "recovery", "id": old, "code": "ERP_ID_CONFLICT"})
            continue
        used.add(old)
        cases[target]["history"]["pythonRecovery"].append(row)
    for key in set(recovery_map) - used:
        errors.append({"source": "mapping", "id": key, "code": "UNRESOLVED_RECOVERY_MAPPING"})
    if logs is not None:
        if not isinstance(logs, list) or len(logs) > 10000:
            raise AdmError("旧日志须为不超过10000条JSON数组")
        for number, record in enumerate(logs, 1):
            target = str(record.get("erpId", "")) if isinstance(record, dict) else ""
            if target not in cases or not isinstance(record.get("entries"), list):
                errors.append({"source": "logs", "row": number, "code": "MISSING_EXPLICIT_MAPPING"})
            else:
                cases[target]["history"]["legacyLogs"].extend(record["entries"])
    files = mapping.get("attachments", [])
    if not isinstance(files, list) or len(files) > 10000:
        raise AdmError("附件清单无效或超过容量")
    root = Path(attachment_root).resolve(strict=True) if attachment_root else None
    if root and not root.is_dir():
        raise AdmError("附件根路径必须为目录")
    for number, item in enumerate(files, 1):
        try:
            if not isinstance(item, dict):
                raise ValueError()
            target = str(item.get("erpId", ""))
            relative = Path(item.get("path", ""))
            if target not in cases or root is None or relative.is_absolute() or not relative.parts or ".." in relative.parts:
                raise ValueError()
            source = (root / relative).resolve(strict=True)
            if not source.is_relative_to(root) or not source.is_file() or any((root.joinpath(*relative.parts[:index])).is_symlink() for index in range(1, len(relative.parts) + 1)):
                raise ValueError()
            if source.stat().st_size > 20971520:
                raise ValueError()
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            if item.get("sha256") != sha or item.get("category", "ORIGINAL") not in {"ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "FINANCE", "ANALYSIS"}:
                raise ValueError()
            validate_document(source, source.suffix.lower(), 20971520)
            cases[target]["history"]["migrationFiles"].append({"path": str(relative), "sha256": sha, "category": item.get("category", "ORIGINAL")})
        except (ValueError, TypeError, OSError, AdmError):
            errors.append({"source": "attachment", "row": number, "code": "UNSAFE_MISSING_INVALID_OR_HASH_MISMATCH"})
    for item in cases.values():
        if len(json.dumps(item["history"], ensure_ascii=False)) > 1000000:
            errors.append({"source": "history", "id": item["history"]["oldId"], "code": "HISTORY_TOO_LARGE"})
    return {"cases": list(cases.values()), "errors": errors, "attachmentRoot": str(root) if root else None}


def apply_bundle(service, user, plan):
    if plan["errors"]:
        raise AdmError("迁移预检存在错误，禁止部分静默导入")
    if not user.get("is_admin") or not user.get("is_enabled", True):
        raise AdmError("迁移须为当前有效管理员", 403)
    files = AdmAttachmentService(service.config, service)
    results = []
    for record in plan["cases"]:
        # Idempotency fingerprints the complete immutable legacy input, not ADM number.
        history, body = record["history"], dict(record["body"])
        body["source"] = {**body["source"], "migrationBundleDigest": hashlib.sha256(json.dumps(history, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        case = service.create_case(user, body, history=history)
        for item in history["migrationFiles"]:
            stored = service.store.get(case["id"])
            existing = [entry for entry in stored["attachments"] if entry.get("sha256") == item["sha256"] and entry.get("category") == item["category"]]
            if existing:
                if not all(service._verified_attachment(entry) for entry in existing):
                    raise AdmError("已迁移附件缺失或损坏，请先修复，不覆盖历史")
                continue
            source = (Path(plan["attachmentRoot"]) / item["path"]).resolve(strict=True)
            if not source.is_relative_to(Path(plan["attachmentRoot"])) or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
                raise AdmError("预检后附件已改变，禁止导入")
            with source.open("rb") as stream:
                result = files.upload(user, case["id"], FileStorage(stream=stream, filename=source.name), {"version": case["version"], "category": item["category"]})
            case = result
        results.append({"sourceId": history["oldId"], "caseId": case["id"], "version": case["version"]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--erp", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--recovery-sqlite")
    parser.add_argument("--logs")
    parser.add_argument("--attachment-root")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--admin-id")
    args = parser.parse_args()
    plan = plan_bundle(read_json(args.erp), read_json(args.mapping), args.recovery_sqlite, read_json(args.logs) if args.logs else None, args.attachment_root)
    if not args.apply:
        print(json.dumps({"mode": "PREVIEW_ONLY", "cases": len(plan["cases"]), "errors": plan["errors"], "files": sum(len(row["history"]["migrationFiles"]) for row in plan["cases"]), "warnings": ["未连接目标库、未写文件；须先核对来源映射、目标已有档案冲突及附件内容"]}, ensure_ascii=False))
        return
    if not args.admin_id:
        parser.error("--apply必须同时指定--admin-id，身份从平台账号库重新验证")
    from .config import Config
    from .services.auth import MySqlAuthStore
    config = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    user = MySqlAuthStore(config).get_user_by_id(int(args.admin_id))
    if not user:
        raise AdmError("管理员不存在", 403)
    config["ADM_ATTACHMENT_VERIFIER"] = lambda item: verify_stored_attachment(config, item)
    print(json.dumps({"mode": "APPLIED", "items": apply_bundle(AdmService(config), user, plan)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
