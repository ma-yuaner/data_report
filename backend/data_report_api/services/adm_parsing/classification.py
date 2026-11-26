"""Reason suggestions transcribed from user screenshot 2026-11-19; never assigns users."""
import re

RULES = (
    (r"churning|duplicated|duplicate", "重复预定", "业务部"),
    (r"inactive segments", "未删除无效航段", "业务部"),
    (r"fictitious names?", "虚假姓名", "业务部"),
    (r"endorsements missing|fake segment", "违规出票", "业务部"),
    (r"YQ/YR.*not.*accurately", "税费错误", "业务部"),
    (r"blackout dates", "屏蔽日期出票", "业务部"),
    (r"booking violation|class of service not available|RIPA/OD", "违规订位", "业务部"),
    (r"VOID TICKET IS NOT PERMITTED", "不可废票", "业务部"),
    (r"booking class error|RBD violation", "出票错误", "业务部"),
    (r"advance reservation|reservation/departure conditions", "提前预定和售票", "业务部"),
    (r"fare rule violation", "违反票价规定", "业务部"),
    (r"high cancellation", "取消率过高", "业务部"),
    (r"unticketed bookings", "订位不出票", "业务部"),
    (r"non-commissionable|comm error", "返点错误", "票务部"),
    (r"incorrect tour code|ticket designator", "旅行代码错误", "票务部"),
    (r"recall commissions", "收回返点", "票务部"),
    (r"incorrect refund penalty", "退票费错误", "客服部"),
    (r"re-issue fee error", "改签费错误", "客服部"),
    (r"name correction", "收取改名费", "客服部"),
    (r"no show charge", "收回误机费", "客服部"),
    (r"VOL FULL REFUND|TICKET REFUND, RECALL", "退票收回返点", "客服部"),
    (r"CHANGE TKT NO COMM AND VAT", "改期收回返点", "客服部"),
)


def suggest(candidate):
    reason = candidate.get("adm", {}).get("reason") if isinstance(candidate, dict) and isinstance(candidate.get("adm"), dict) else None
    matches = [{"reason": name, "department": department} for pattern, name, department in RULES if isinstance(reason, str) and re.search(pattern, reason, re.I)]
    return {"status": "suggested" if len(matches) == 1 else "ambiguous" if matches else "unmatched", "matches": matches, "ruleVersion": "adm-reason/2026-11-19", "requiresReview": True}
