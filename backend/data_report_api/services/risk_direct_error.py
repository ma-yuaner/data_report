"""Stable evidence identity for reason-based case recognition."""
from .risk_child_loss import REASON_CASE_ROUTES


def reason_snapshot(order_id, issue_date, reason):
    identifier, day = str(order_id), str(issue_date)[:10]
    return {
        'orderId': identifier, 'issueDate': day,
        'resultId': f'reason-{reason}-{day}-{identifier}',
        'systemStatus': REASON_CASE_ROUTES[reason][0], 'snapshotKind': 'reason_rule', 'routingReason': reason,
    }
