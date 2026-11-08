"""Pure state decisions for the confirmed ADM workflow."""

from decimal import Decimal

from .policy import AdmError


FINAL_APPEAL_RESULTS = frozenset({"SUCCEEDED", "FAILED", "NO_APPEAL"})
DIFF_MATCHED = frozenset({
    "MATCHED_OTA_ORDER", "MATCHED_LEGACY_ADM_NO", "MATCHED_LINE_INTERNAL_NO",
})


def difference_query_key(*, source_type, ota_order_no, adm_no, line_internal_no):
    ota_value = str(ota_order_no or "").strip()
    if ota_value:
        return {
            "keyType": "OTA_ORDER_NO",
            "keyValue": ota_value,
            "matchedStatus": "MATCHED_OTA_ORDER",
        }
    if source_type == "LEGACY":
        return {
            "keyType": "LEGACY_ADM_NO",
            "keyValue": str(adm_no or "").strip(),
            "matchedStatus": "MATCHED_LEGACY_ADM_NO",
        }
    return {
        "keyType": "LINE_INTERNAL_NO",
        "keyValue": str(line_internal_no or "").strip(),
        "matchedStatus": "MATCHED_LINE_INTERNAL_NO",
    }


def requires_diff_match(appeal_status):
    return appeal_status in {"FAILED", "NO_APPEAL"}


def validate_submit(recovery_status, appeal_status, problem_attribution):
    if recovery_status not in {"NOT_REQUIRED", "CONFIRMED"}:
        raise AdmError("恢复编码事项尚未处理完成")
    if appeal_status not in FINAL_APPEAL_RESULTS:
        raise AdmError("申诉或不申诉尚未形成最终结果")
    if requires_diff_match(appeal_status) and problem_attribution not in {"HUMAN", "PLATFORM", "SYSTEM"}:
        raise AdmError("申诉失败或不申诉时必须选择问题归因")


def status_after_approval(*, appeal_status, diff_match_status, collection_required,
                          expected_collection_amount, collected_amount):
    if requires_diff_match(appeal_status) and diff_match_status not in DIFF_MATCHED:
        return "WAITING_DIFF"
    if collection_required:
        expected = Decimal(str(expected_collection_amount or "0"))
        collected = Decimal(str(collected_amount or "0"))
        if expected <= 0:
            raise AdmError("需要回款时应回款金额必须大于0")
        if collected != expected:
            return "WAITING_COLLECTION"
    return "COMPLETED"


def closure_blockers(lines):
    blockers = []
    for line in lines:
        if line["line_status"] not in {"COMPLETED", "VOIDED", "HISTORICAL"}:
            blockers.append({
                "lineId": line["id"], "lineInternalNo": line["line_internal_no"],
                "status": line["line_status"],
            })
    return blockers
