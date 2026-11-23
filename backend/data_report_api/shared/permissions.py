"""Shared permission representation; callers keep their existing admin rules."""

from typing import Any

PLACEMENT_POLICY_EXPORT_PERMISSION = "smart_placement.policies.export"


def permission_codes(user: dict[str, Any]) -> set[str]:
    return {str(value) for value in (user.get("permissions") or user.get("permission_codes") or [])}
