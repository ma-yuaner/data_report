"""ADM 0.5 order state and money rules.

This module is deliberately free of persistence and HTTP concerns so the
workflow contract can be tested without a database or production data.
"""

from __future__ import annotations

from decimal import Decimal

from .policy import AdmError


ORDER_STATUSES = (
    "PENDING_LEADER_ASSIGNMENT",
    "PENDING_OPERATOR_ASSIGNMENT",
    "PENDING_CODE_PROCESSING",
    "PENDING_DECISION",
    "APPEAL_IN_PROGRESS",
    "PENDING_REVIEW",
    "REJECTED_FOR_REVISION",
    "PENDING_COLLECTION",
    "COMPLETED",
)

RECOVERY_STATES = ("UNDECIDED", "NOT_REQUIRED", "WAITING_MANUAL", "MANUALLY_COMPLETED")
DECISIONS = ("UNDECIDED", "APPEAL", "NO_APPEAL")
RESULTS = ("UNDECIDED", "APPEAL_SUCCESS", "APPEAL_FAILED", "NO_APPEAL")
ATTRIBUTIONS = ("HUMAN", "PLATFORM", "SYSTEM")


def exact_amounts(case: dict) -> tuple[Decimal | None, Decimal, bool]:
    """Return master total, line total and whether every line can be reconciled."""
    if case.get("originalAmount") in (None, "") or not case.get("lines"):
        return None, Decimal("0"), False
    total = Decimal(str(case["originalAmount"]))
    allocated = Decimal("0")
    for line in case["lines"]:
        if line.get("amount") in (None, "") or line.get("currency") != case.get("currency"):
            return total, allocated, False
        allocated += Decimal(str(line["amount"]))
    return total, allocated, total == allocated


def require_exact_amounts(case: dict) -> None:
    total, allocated, matched = exact_amounts(case)
    if not matched:
        expected = "未填写" if total is None else format(total, "f")
        raise AdmError(
            f"主单原币总金额必须精确等于明细合计（主单{expected}，明细{format(allocated, 'f')}）",
            409,
            "ADM_AMOUNT_MISMATCH",
        )


def collection_total(line: dict) -> Decimal:
    return sum((Decimal(str(item["amount"])) for item in line.get("collections", [])), Decimal("0"))


def validate_attribution(value: object) -> str:
    normalized = str(value or "")
    if normalized not in ATTRIBUTIONS:
        raise AdmError("问题归因须为人为问题、平台问题或系统问题")
    return normalized
