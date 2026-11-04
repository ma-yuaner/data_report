"""Explicit single-order, read-only diagnostic. No model, writes, names or ticket numbers."""
import argparse
import json

from ..config import Config
from .risk_order_evidence import EvidenceError, RiskOrderEvidenceService
from .risk_commission_rule import parse_stop_loss_log


def summarize(evidence):
    blocks = evidence["blocks"]
    fields = ("id", "sale_commission_amount", "issue_profit", "issue_currency", "issue_exchange_rate", "sale_currency", "sale_exchange_rate")
    logs = []
    for row in blocks["operatorLogs"]["records"]:
        parsed = parse_stop_loss_log(row.get("operator_content"))
        if parsed["records"]:
            logs.append({"logId": row["id"], "at": row.get("operator_datetime"), "extracted": parsed})
    return {"erpOrderId": evidence["erpOrderId"], "profitReasonType": evidence["order"].get("profit_reason_type"),
            "otaCode": evidence["order"].get("ota_code"), "commissionType": evidence["order"].get("commission_type"),
            "issuesStatus": blocks["issues"]["status"], "issues": [{key: row.get(key) for key in fields} for row in blocks["issues"]["records"]],
            "logsStatus": blocks["operatorLogs"]["status"], "stopLossLogCandidates": logs,
            "notice": "只读取证摘要，不含姓名、票号或日志原文。issue_profit不是已验证的自动出票单票利润；平台映射及单票关联待核实，不能据此自动形成业务结论。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-no", required=True)
    args = parser.parse_args()
    values = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    try:
        evidence = RiskOrderEvidenceService(values).evidence(args.order_no, ["issues", "operatorLogs"], "orderNo")
        print(json.dumps(summarize(evidence), ensure_ascii=False, indent=2))
    except EvidenceError as error:
        print(json.dumps({"success": False, "message": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
