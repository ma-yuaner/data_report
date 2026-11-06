"""Confirmed arithmetic only; source bindings must be verified before live use."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re

RULE_ID = "qunar-commission-loss-config-v13"


def evaluate_commission_loss(*, is_qunar, single_ticket_profit, sales_commission, stop_loss):
    """Evaluate a single CNY ticket, never invent missing inputs or compare order totals."""
    if is_qunar is False:
        return {"ruleId": RULE_ID, "status": "not_applicable", "missingEvidence": [],
                "prerequisite": "非去哪儿平台不得选择佣金、点击费亏损；平台条件优先，不依赖佣金或止损证据"}
    missing = []
    values = {}
    for key, raw in (("singleTicketProfit", single_ticket_profit), ("salesCommission", sales_commission), ("stopLoss", stop_loss)):
        if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)) or not re.fullmatch(r"-?[0-9]{1,20}(?:\.[0-9]{1,12})?", str(raw)):
            missing.append(key)
            continue
        try:
            values[key] = Decimal(str(raw))
        except InvalidOperation:
            missing.append(key)
    if type(is_qunar) is not bool:
        missing.append("verifiedQunarPlatform")
    if values.get("salesCommission", Decimal(0)) < 0:
        missing.append("negativeCommissionSemantics")
    if values.get("stopLoss", Decimal(0)) < 0:
        missing.append("nonnegativeStopLoss")
    result = {"ruleId": RULE_ID, "formula": "singleTicketProfit + salesCommission >= -stopLoss",
              "currency": "CNY", "grain": "single_ticket", "status": "insufficient", "missingEvidence": missing,
              "notice": "只核对选因是否符合已确认规则，不判断责任或实际财务损失；按出票明细核算，止损值须有一致日志依据"}
    if missing:
        return result
    if not is_qunar or values["salesCommission"] == 0:
        result.update(status="not_applicable", prerequisite="须为去哪儿且实际销售佣金为正")
        return result
    with localcontext() as context:
        context.prec = 64
        adjusted = values["singleTicketProfit"] + values["salesCommission"]
        boundary = -values["stopLoss"]
    result.update(status="supported" if adjusted >= boundary else "contradicted",
                  inputs={key: format(value, "f") for key, value in values.items()},
                  adjustedProfit=format(adjusted, "f"), boundary=format(boundary, "f"),
                  calculation=f"{values['singleTicketProfit']} + {values['salesCommission']} = {adjusted}; {adjusted} >= {boundary}: {adjusted >= boundary}")
    return result


def parse_stop_loss_log(text):
    """Extract matching fragments, never silently pick one of several ticket/log contexts."""
    if not isinstance(text, str) or len(text) > 20000:
        return {"status": "insufficient", "records": []}
    number = r"(-?[0-9]{1,20}(?:\.[0-9]{1,12})?)"
    pattern = (r"当前底价为\s*[:：]\s*" + number + r"\s*元\s*[,，]\s*结算费用为\s*[:：]\s*" + number
               + r"\s*元\s*[,，]\s*亏损金额\s*[:：]\s*" + number + r"\s*元\s*[,，]\s*止损值配置为\s*[:：]\s*" + number + r"\s*元")
    records = []
    for match in re.finditer(pattern, text):
        base, settlement, loss, threshold = map(Decimal, match.groups())
        with localcontext() as context:
            context.prec = 64
            profit = settlement - base
            consistent = (base - settlement).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == loss.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        records.append({"basePrice": format(base, "f"), "settlement": format(settlement, "f"),
                        "reportedLoss": format(loss, "f"), "stopLoss": format(threshold, "f"),
                        "derivedProfit": format(profit, "f"), "amountsConsistent": consistent,
                        "amountComparison": "CNY_ROUND_HALF_UP_2DP"})
    return {"status": "ready" if len(records) == 1 and records[0]["amountsConsistent"] else "ambiguous" if len(records) > 1 else "insufficient",
            "records": records, "notice": "日志推导值不等于已验证的自动出票单票利润；须关联具体日志ID、时间和单票"}
