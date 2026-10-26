"""Scoped collaboration, remediation, responsibility review and file grants."""
import copy

from .policy import AdmError, has, identity, now, uid
from .workflow import WorkflowService, timestamp

ACTIONS = {"collaboration_create", "collaboration_accept", "collaboration_submit", "collaboration_review", "collaboration_cancel", "responsibility_propose", "responsibility_review"}


def task_actions(user, case, line, task, full):
    if case.get("voided") or case.get("paused") or case["status"] in {"DRAFT", "HISTORICAL"}:
        return []
    if case["status"] == "CLOSED" and task["kind"] != "REMEDIATION":
        return []
    actor = identity(user)
    owner = str(task["ownerId"]) == actor and has(user, "adm.handle")
    manager = (full and has(user, "adm.assign")) or (str(line.get("ownerId")) == actor and has(user, "adm.handle"))
    result = []
    if owner and task["status"] == "PENDING_ACCEPT":
        result.append("collaboration_accept")
    if owner and task["status"] == "PROCESSING":
        result.append("collaboration_submit")
    if manager and not owner and task["status"] == "PENDING_REVIEW":
        result.append("collaboration_review")
    if manager and task["status"] not in {"COMPLETED", "CANCELLED"}:
        result.append("collaboration_cancel")
    return result


def extra_actions(user, case, line, full):
    result = []
    active = case["status"] not in {"DRAFT", "CLOSED", "HISTORICAL"} and not case.get("paused") and not case.get("voided")
    actor = identity(user)
    manager = full and has(user, "adm.assign")
    owner = str(line.get("ownerId")) == actor and line["status"] == "PROCESSING" and line.get("lockedBy") == actor and has(user, "adm.handle")
    if active and line["status"] != "COMPLETED" and (owner or manager):
        result += ["collaboration_create", "responsibility_propose"]
    proposal = line.get("responsibility") or {}
    reviewer = str((line.get("workflow") or {}).get("reviewerId")) == actor
    if active and has(user, "adm.review") and (full or reviewer) and proposal.get("status") == "PENDING_REVIEW" and proposal.get("proposedBy") != actor:
        result.append("responsibility_review")
    if any("collaboration_submit" in task_actions(user, case, line, task, full) for task in line.get("collaborations", [])):
        result.append("upload")
    return result


def upload_categories(user, case, line, full):
    if full and has(user, "adm.edit"):
        return ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "FINANCE", "ANALYSIS"]
    actor = identity(user)
    if line["status"] == "PROCESSING" and str(line.get("ownerId")) == actor and line.get("lockedBy") == actor:
        return ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "FINANCE", "ANALYSIS"]
    if any("collaboration_submit" in task_actions(user, case, line, task, full) for task in line.get("collaborations", [])):
        return ["VERIFICATION", "ANALYSIS"]
    return ["FINANCE"] if line["status"] == "WAITING_FINANCE" else ["VERIFICATION", "ANALYSIS"]


def file_visible(item, line_ids):
    return item.get("lineId") in line_ids or bool(set(item.get("sharedLineIds") or []) & line_ids)


def blockers(case, line):
    return ["必需协办尚未完成"] if any(task.get("required") and task.get("round") == case["round"] and task["status"] not in {"COMPLETED", "CANCELLED"} for task in line.get("collaborations", [])) else []


def review_recipient(service, case, line, task):
    resolver = service.config.get("ADM_USER_RESOLVER")
    coordinator = case.get("coordinatorId", case["createdBy"])
    for candidate in (line.get("ownerId"), coordinator, task.get("requestedBy")):
        person = resolver(candidate) if candidate and callable(resolver) else None
        accessible = person and person.get("is_enabled", True) and not person.get("must_change_password") and has(person, "adm.view") and (person.get("is_admin") or "adm.center" in person.get("menu_codes", []))
        if accessible and "collaboration_review" in task_actions(person, case, line, task, service._full(person, case)):
            return str(candidate), person.get("display_name") or person.get("username"), False
    return str(coordinator), "协调人：需安排独立复核（可取消后重新分配）", True


class CollaborationService:
    def __init__(self, service):
        self.service = service

    def action(self, user, case_id, line_id, body):
        action = body.get("action")
        current = self.service._read(user, case_id)
        current_line = self.service._line(current, line_id)
        task = next((item for item in current_line.get("collaborations", []) if item["id"] == body.get("taskId")), None)
        remediation = task and task["kind"] == "REMEDIATION" and action.startswith("collaboration_") and action != "collaboration_create"
        permission = "adm.review" if action == "responsibility_review" else "adm.assign" if self.service._full(user, current) and has(user, "adm.assign") else "adm.handle"
        case = self.service._write(user, case_id, body, permission, control_action="remediation" if remediation else None)
        line = self.service._line(case, line_id)
        self.service._line_access(user, case, line)
        full = self.service._full(user, case)
        if action in {"collaboration_create", "responsibility_propose", "responsibility_review"}:
            if action not in extra_actions(user, case, line, full):
                raise AdmError("当前身份或状态不允许此协作/认定操作", 403)
        else:
            task = next((item for item in line.get("collaborations", []) if item["id"] == body.get("taskId")), None)
            if not task or action not in task_actions(user, case, line, task, full):
                raise AdmError("无此协办任务操作权限", 403)
        if action == "collaboration_create":
            owner, name = WorkflowService(self.service).resolve(body.get("ownerId"), "handle")
            title, description = str(body.get("title") or "").strip(), str(body.get("description") or "").strip()
            kind = body.get("kind", "COLLABORATION")
            required = body.get("required", False)
            if not title or len(title) > 200 or not description or len(description) > 4000 or kind not in {"COLLABORATION", "REMEDIATION"} or type(required) is not bool:
                raise AdmError("请填写有效任务标题、说明、类型及是否必需")
            if len(line.get("collaborations", [])) >= 100:
                raise AdmError("每条明细最多100项协作/整改任务")
            task = {"id": uid(), "kind": kind, "title": title, "description": description, "ownerId": owner, "ownerName": name,
                    "requestedBy": identity(user), "requestedByName": user.get("display_name") or user.get("username") or identity(user), "createdAt": now(),
                    "dueAt": timestamp(body.get("dueAt")), "required": required, "round": case["round"], "status": "PENDING_ACCEPT", "result": "", "evidence": [], "reviews": []}
            line.setdefault("collaborations", []).append(task)
        elif action == "collaboration_accept":
            task.update(status="PROCESSING", acceptedAt=now())
        elif action == "collaboration_submit":
            result = str(body.get("result") or "").strip()
            if not result or len(result) > 8000:
                raise AdmError("协办结果必填，最多8000字")
            evidence = self.service._evidence(case, line_id, body.get("evidence"))
            task.update(status="PENDING_REVIEW", result=result, evidence=evidence, submittedAt=now())
        elif action in {"collaboration_review", "collaboration_cancel"}:
            reason = str(body.get("reason") or "").strip()
            if not reason or len(reason) > 4000 or (action.endswith("review") and type(body.get("approved")) is not bool):
                raise AdmError("审核/取消须有效意见和明确结论")
            if action.endswith("cancel"):
                task.update(status="CANCELLED", cancelledAt=now())
            else:
                if body["approved"]:
                    self.service._evidence(case, line_id, task["evidence"])
                task.update(status="COMPLETED" if body["approved"] else "PROCESSING", reviewedAt=now())
            task["reviews"].append({"actorId": identity(user), "at": now(), "reason": reason, "action": action, "approved": body.get("approved")})
        elif action == "responsibility_propose":
            kind = body.get("type")
            reason, subject = str(body.get("reason") or "").strip(), str(body.get("subject") or "").strip()
            if kind not in {"PERSON", "SYSTEM", "SUPPLIER", "AIRLINE", "PLATFORM", "UNDETERMINED"} or not reason or len(reason) > 4000 or len(subject) > 200:
                raise AdmError("责任类型/依据无效")
            if kind not in {"PERSON", "UNDETERMINED"} and not subject:
                raise AdmError("请填写具体责任主体")
            person, name = WorkflowService(self.service).resolve(body.get("responsibleUserId"), "handle") if kind == "PERSON" else (None, "")
            evidence = self.service._evidence(case, line_id, body.get("evidence"))
            if line.get("responsibility"):
                line.setdefault("responsibilityHistory", []).append(copy.deepcopy(line["responsibility"]))
            line["responsibility"] = {"id": uid(), "status": "PENDING_REVIEW", "type": kind, "responsibleUserId": person, "responsibleName": name,
                                      "subject": subject, "reason": reason, "evidence": evidence, "proposedBy": identity(user), "proposedAt": now()}
        elif action == "responsibility_review":
            reason = str(body.get("reason") or "").strip()
            if type(body.get("approved")) is not bool or not reason or len(reason) > 4000:
                raise AdmError("责任复核须明确结论和依据")
            proposal = line["responsibility"]
            self.service._evidence(case, line_id, proposal["evidence"])
            proposal.update(status="CONFIRMED" if body["approved"] else "REJECTED", reviewedBy=identity(user), reviewedAt=now(), reviewReason=reason)
        return self.service._save(user, case, action, {key: value for key, value in body.items() if key not in {"version", "action"}}, line_id)

    def share(self, user, case_id, body):
        case = self.service._write(user, case_id, body, "adm.edit", True)
        line_ids = body.get("lineIds")
        valid = {line["id"] for line in case["lines"]}
        if not isinstance(line_ids, list) or any(not isinstance(item, str) or item not in valid for item in line_ids) or len(set(line_ids)) != len(line_ids):
            raise AdmError("共享范围必须为本主单内不同明细")
        if body.get("acknowledgeFullFile") is not True or not str(body.get("reason") or "").strip():
            raise AdmError("须确认整份文件内容适合共享，并填写授权依据")
        attachment = next((item for item in case["attachments"] if item["id"] == body.get("attachmentId")), None)
        if not attachment or not self.service._verified_attachment(attachment):
            raise AdmError("待共享附件不存在或不可读")
        original_id = body.get("redactedFromId")
        if original_id and (original_id == attachment["id"] or not any(item["id"] == original_id for item in case["attachments"])):
            raise AdmError("脱敏原件关联无效")
        attachment.update(sharedLineIds=line_ids, redactedFromId=original_id or None, sharingConfirmedBy=identity(user), sharingConfirmedAt=now())
        return self.service._save(user, case, "attachment_share", {"attachmentId": attachment["id"], "lineIds": line_ids, "redactedFromId": original_id, "reason": str(body["reason"])})
