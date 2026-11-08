"""Shared risk query bounds and metric projection for readers and snapshots."""
from datetime import date

from .risk_order_evidence import EvidenceError


METRIC_JOIN = """ LEFT JOIN bi_risk_order_metric_day m ON m.issue_date=o.issue_date AND m.order_id=o.order_id AND m.catalog_run_id=o.etl_run_id
 LEFT JOIN bi_risk_order_metric_day_ready mr ON mr.issue_date=o.issue_date AND mr.catalog_run_id=o.etl_run_id"""


METRIC_PROFIT = 'CASE WHEN mr.issue_date IS NOT NULL THEN m.total_profit ELSE NULL END'


METRIC_FIELDS = f",{METRIC_PROFIT} AS total_profit,CASE WHEN mr.issue_date IS NOT NULL THEN m.segment_count ELSE NULL END AS segment_count,CASE WHEN mr.issue_date IS NOT NULL THEN m.body ELSE NULL END AS metric_body"


def period(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise EvidenceError("请提供YYYY-MM-DD格式的起止日期") from None
    if first > last or (last - first).days > 30 or last == date.max:
        raise EvidenceError("按出票日期查询，范围须为1至31天")
    return first, last


def positive_integer(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit():
        raise EvidenceError(f"{name}必须为正整数")
    value = int(value)
    if not 1 <= value <= maximum:
        raise EvidenceError(f"{name}超出允许范围")
    return value
