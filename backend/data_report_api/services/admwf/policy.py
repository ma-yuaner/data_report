"""Stable ADM workflow policies shared by the service and HTTP adapters."""

from datetime import datetime
from zoneinfo import ZoneInfo


CASE_STATUSES = frozenset({"DRAFT", "ACTIVE", "CLOSED", "HISTORICAL", "VOIDED", "DELETED"})
LINE_STATUSES = frozenset({
    "PENDING_LEADER", "PENDING_OPERATOR", "PENDING_ACCEPT", "PROCESSING",
    "PENDING_REVIEW", "WAITING_DIFF", "WAITING_COLLECTION", "COMPLETED",
    "HISTORICAL", "VOIDED",
})


class AdmError(Exception):
    def __init__(self, message, status=400, code="ADM_INVALID"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def business_now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def identity(user):
    if not user or not user.get("id"):
        raise AdmError("请先登录", 401, "ADM_AUTH")
    return int(user["id"])


def display_name(user):
    return str(user.get("display_name") or user.get("full_name") or user.get("username") or identity(user))


def has(user, permission):
    return bool(user.get("is_admin")) or permission in set(user.get("permissions") or [])


def require(user, permission):
    identity(user)
    if not has(user, permission):
        raise AdmError("无此ADM操作权限", 403, "ADM_FORBIDDEN")
