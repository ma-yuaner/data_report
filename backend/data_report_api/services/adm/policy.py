"""Shared identity/permission rules for aggregates and workflow."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo


class AdmError(Exception):
    def __init__(self, message, status=400, code="ADM_INVALID"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def uid():
    return str(uuid.uuid4())


def has(user, permission):
    return bool(user.get("is_admin")) or permission in (user.get("permissions") or [])


def identity(user):
    if not user or not user.get("id"):
        raise AdmError("请先登录", 401, "ADM_AUTH")
    return str(user["id"])


def require(user, permission):
    identity(user)
    if not has(user, permission):
        raise AdmError("无此ADM操作权限", 403, "ADM_FORBIDDEN")
