"""Persisted, single-active policy extraction on the existing SQLite volume."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import Lock, Thread
import time
from uuid import uuid4

from .calculation import fetch_policy_reference
from .extraction import (
    PROMPT_VERSION, ExtractionError, call_model, model_settings, page_inputs,
    validate_scheme_coverage, validated_draft, verify_hkg_rate_table,
)
from .store import connect, encode

LEASE_SECONDS = 900
STAGES = {"reading", "model", "validating", "reference"}
_worker_lock = Lock()
_workers = set()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def enqueue(db, identifier, name, raw):
    fingerprint = sha256(raw).hexdigest()
    profile = {
        "id": identifier, "name": name, "airline": "", "period": "", "source": "model",
        "fileSha256": fingerprint, "uploadRevision": uuid4().hex,
        "parse": {"status": "pending", "stage": "queued", "executionId": uuid4().hex, "createdAt": stamp()},
    }
    db.execute("INSERT OR IGNORE INTO rebate_policies(id, profile, original) VALUES (?, ?, ?)",
               (identifier, encode(profile), raw))
    row = db.execute("SELECT * FROM rebate_policies WHERE id=?", (identifier,)).fetchone()
    if json.loads(row["profile"]).get("fileSha256") != fingerprint:
        raise ExtractionError("同一提交标识已绑定另一份文件")
    return row


def prepare_legacy(db):
    db.execute(
        "UPDATE rebate_policies SET profile=json_set(profile,'$.parse',"
        "json_object('status','pending','stage','queued')) "
        "WHERE json_extract(profile,'$.policy') IS NOT NULL "
        "AND json_extract(profile,'$.mappingReference') IS NULL "
        "AND json_extract(profile,'$.parse') IS NULL"
    )


def _write(db, profile):
    db.execute("UPDATE rebate_policies SET profile=? WHERE id=?", (encode(profile), profile["id"]))


def _claim(directory):
    with connect(directory) as db:
        db.execute("BEGIN IMMEDIATE")
        active = db.execute(
            "SELECT profile FROM rebate_policies WHERE json_extract(profile,'$.parse.token') IS NOT NULL LIMIT 1"
        ).fetchone()
        if active:
            profile = json.loads(active["profile"])
            job = profile["parse"]
            if time.time() - job["claimedAt"] < LEASE_SECONDS:
                return None
            job.pop("token")
            if job["stage"] == "model" and "candidate" not in job:
                job.update(status="failed", error="模型执行中断，调用结果未知。确认后可显式重试。")
            else:
                job["stage"] = "queued"
            _write(db, profile)
        row = db.execute(
            "SELECT * FROM rebate_policies "
            "WHERE json_extract(profile,'$.parse.status')='pending' "
            "AND json_extract(profile,'$.parse.stage')='queued' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if not row:
            return None
        profile = json.loads(row["profile"])
        job = profile["parse"]
        stage = "reference" if "policy" in profile else "validating" if "candidate" in job else "reading"
        job.update(token=uuid4().hex, claimedAt=time.time(), stage=stage)
        _write(db, profile)
        return profile, row["original"]


def _checkpoint(directory, profile, stage, **changes):
    job = profile["parse"]
    token = job["token"]
    job.update(changes, stage=stage)
    if changes.get("status") in {"ready", "failed"}:
        job.pop("token")
        job.pop("claimedAt", None)
    else:
        job["claimedAt"] = time.time()
    with connect(directory) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT profile FROM rebate_policies WHERE id=? AND json_extract(profile,'$.parse.token')=?",
            (profile["id"], token),
        ).fetchone()
        if not row:
            return False
        stored = json.loads(row["profile"])
        stored["parse"] = job
        if stored.get("source") == "model" and "policy" in profile:
            stored.update({key: profile[key] for key in ("policy", "airline", "period")})
        if "mappingReference" in profile:
            stored["mappingReference"] = profile["mappingReference"]
        _write(db, stored)
        return True


def retry(db, row):
    profile = json.loads(row["profile"])
    job = profile.get("parse")
    if not job or job["status"] != "failed":
        raise ExtractionError("只有失败的解析任务可以重试")
    if job["stage"] == "model" and "candidate" not in job:
        history = job.setdefault("attempts", [])
        history.append({key: job[key] for key in ("executionId", "stage", "error", "finishedAt") if key in job})
        job["executionId"] = uuid4().hex
    job.pop("error", None)
    job.update(status="pending", stage="queued")
    _write(db, profile)
    return profile


def _process(directory, config, logger, profile, raw):
    stage = profile["parse"]["stage"]
    job = profile["parse"]
    try:
        if stage == "reading":
            model_settings(config)
            pages = page_inputs(raw, config)
            stage = "model"
            if not _checkpoint(directory, profile, stage, modelStartedAt=stamp(),
                               inputPages=[{"page": p["page"], "image": bool(p["image"])} for p in pages]):
                return
            candidate, receipt = call_model(config, pages)
            stage = "validating"
            if not _checkpoint(directory, profile, stage, candidate=candidate, modelReceipt=receipt,
                               modelFinishedAt=stamp(), pageTexts=[p["text"] for p in pages]):
                return
        if stage == "validating":
            page_texts = job["pageTexts"]
            allow_legacy = job.get("modelReceipt", {}).get("promptVersion") != PROMPT_VERSION
            draft = validated_draft(job["candidate"], page_texts, allow_legacy=allow_legacy)
            draft = verify_hkg_rate_table(draft, raw, page_texts)
            validate_scheme_coverage(draft, len(page_texts))
            contract = draft["contract"]
            profile.update(policy=draft, airline=contract["airline"] or "",
                           period=" 至 ".join(value for value in (contract["start"], contract["end"]) if value))
            job.pop("pageTexts", None)
            stage = "reference"
            if not _checkpoint(directory, profile, stage):
                return
        reference = fetch_policy_reference(config)
        if len(reference.get("rows", [])) != 1:
            raise ExtractionError("未取得可用于核对的 Hive 参考记录")
        profile["mappingReference"] = {**reference, "preparedAt": stamp(), "scope": "wideTableExample"}
        _checkpoint(directory, profile, "complete", status="ready", finishedAt=stamp())
    except Exception as error:
        logger.warning("Rebate parse failed stage=%s type=%s", stage, type(error).__name__)
        message = str(error) if isinstance(error, ExtractionError) else (
            "Hive 参考记录准备失败，已保留解析初稿。重试只会补准备参考记录。"
            if stage == "reference" else "政策解析阶段执行失败，原件已保留。"
        )
        if "token" in job:
            _checkpoint(directory, profile, stage, status="failed", error=message, finishedAt=stamp())


def drain(directory, config, logger):
    while (claimed := _claim(directory)) is not None:
        _process(directory, config, logger, *claimed)


def kick(directory, config, logger):
    """Resume queued submissions on the next API visit after a process restart."""
    directory = str(directory)
    with _worker_lock:
        if directory in _workers:
            return
        _workers.add(directory)

    def work():
        try:
            drain(directory, config, logger)
        except Exception as error:
            logger.warning("Rebate parse queue interrupted: %s", type(error).__name__)
        finally:
            with _worker_lock:
                _workers.discard(directory)

    Thread(target=work, name="rebate-policy-parser", daemon=True).start()
