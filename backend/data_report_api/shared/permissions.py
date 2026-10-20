"""Shared permission representation; callers keep their existing admin rules."""

from typing import Any


def permission_codes(user: dict[str, Any]) -> set[str]:
    return {str(value) for value in (user.get("permissions") or user.get("permission_codes") or [])}
