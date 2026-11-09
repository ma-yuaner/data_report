"""Verify profit reasons against the sum of the order's issued-ticket profits."""
from decimal import Decimal, localcontext

from .risk_child_loss import number


def evaluate_order_profit(evidence, version):
    issues = evidence.get('issues', [])
    aggregate = {'ticketCount': len(issues), 'currency': 'CNY'}
    result = {'ruleVersion': version, 'status': 'insufficient', 'platform': evidence['order'].get('ota_code'),
              'summary': '整单出票利润证据不足', 'aggregate': aggregate, 'tickets': [],
              'stopLoss': None, 'missing': [], 'logReferences': []}
    if not evidence.get('complete') or not issues:
        result['missing'] = ['完整出票明细']
        return result

    profits = [number(issue.get('issue_profit')) for issue in issues]
    if None in profits:
        result['missing'] = ['完整出票利润']
        return result

    with localcontext() as context:
        context.prec = 64
        total = sum(profits, Decimal(0))
    aggregate['totalProfit'] = format(total, 'f')
    if total > 0:
        result.update(status='supported', summary='整单出票利润大于 0，自动通过')
    else:
        result.update(status='problem', summary='整单出票利润小于或等于 0，选因有问题')
    return result
