"""ADM attachment visibility and node-scoped upload permissions."""

from .policy import has, identity


def upload_categories(user, case, line, full):
    if full and has(user, "adm.edit"):
        return ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "COLLECTION", "ANALYSIS"]
    actor = identity(user)
    owner = str(case.get("ownerId") or line.get("ownerId") or "") == actor
    if owner and line["status"] in {
        "PENDING_CODE_PROCESSING",
        "PENDING_DECISION",
        "APPEAL_IN_PROGRESS",
        "REJECTED_FOR_REVISION",
    }:
        return ["ORIGINAL", "VERIFICATION", "RECOVERY", "APPEAL", "ANALYSIS"]
    return ["COLLECTION"] if line["status"] == "PENDING_COLLECTION" else ["VERIFICATION", "ANALYSIS"]


def file_visible(item, line_ids):
    return item.get("lineId") in line_ids or bool(set(item.get("sharedLineIds") or []) & line_ids)
