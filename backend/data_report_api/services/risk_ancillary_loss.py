"""Verify the combined ticket and ancillary profit at order grain."""
from decimal import Decimal, localcontext

from .risk_child_loss import number


MAX_ANCILLARY_ROWS = 200
ANCILLARY_SQL = """
SELECT a.ota_order_no, a.id AS auxiliary_id, p.id AS purchase_id, p.pur_profit
FROM order_auxiliary a
LEFT JOIN order_auxiliary_pur p ON p.aux_id = a.id
WHERE a.ota_order_no IN ({marks})
ORDER BY a.ota_order_no, a.id, p.id
LIMIT {limit}
""".strip()


def evaluate_ancillary(evidence, version):
    order = evidence['order']
    issues = evidence.get('issues', [])
    purchases = evidence.get('ancillaryPurchases', [])
    aggregate = {'grain': 'order', 'currency': 'CNY', 'ticketCount': len(issues)}
    result = {'ruleVersion': version, 'platform': order.get('ota_code'), 'status': 'insufficient',
              'summary': '整单综合利润证据不足', 'aggregate': aggregate, 'tickets': [],
              'stopLoss': None, 'missing': [], 'logReferences': []}

    def insufficient(reason):
        result['missing'] = [reason]
        return result

    if not evidence.get('complete') or not issues:
        return insufficient('完整出票明细')
    if not order.get('ota_order_no') or not purchases:
        return insufficient('同OTA订单号的增值订单及购买明细')
    if len(purchases) > MAX_ANCILLARY_ROWS:
        return insufficient('增值购买范围截断')
    if any(row.get('ota_order_no') != order['ota_order_no'] or row.get('purchase_id') is None
           for row in purchases):
        return insufficient('完整增值订单购买明细及OTA关联')
    if len({str(row['purchase_id']) for row in purchases}) != len(purchases):
        return insufficient('增值购买明细重复')

    ticket_profits = [number(row.get('issue_profit')) for row in issues]
    ancillary_profits = [number(row.get('pur_profit')) for row in purchases]
    if None in ticket_profits or None in ancillary_profits:
        return insufficient('完整出票利润及增值利润')

    with localcontext() as context:
        context.prec = 64
        ticket_total = sum(ticket_profits, Decimal(0))
        ancillary_total = sum(ancillary_profits, Decimal(0))
        total = ticket_total + ancillary_total
        aggregate.update(ticketProfit=format(ticket_total, 'f'), ancillaryProfit=format(ancillary_total, 'f'),
                         totalProfit=format(total, 'f'), ancillaryOrderCount=len({row['auxiliary_id'] for row in purchases}),
                         ancillaryPurchaseCount=len(purchases), commissionIncluded=False)
        for issue in issues:
            config = issue.get('thresholdConfiguration') or {}
            threshold = number(config.get('amount'))
            item = {'id': str(issue['id']), 'profit': issue.get('issue_profit'), 'commission': None,
                    'currency': 'CNY', 'segmentCount': issue.get('segmentCount'), 'configuration': config,
                    'stopLoss': None, 'status': 'insufficient',
                    'explanation': config.get('reason') or '缺少出票时通用配置止损值'}
            if config.get('status') == 'ready' and threshold is not None and threshold >= 0:
                boundary = -threshold
                passed = total >= boundary
                item.update(status='supported' if passed else 'problem', stopLoss=format(threshold, 'f'),
                            adjustedProfit=format(total, 'f'), boundary=format(boundary, 'f'),
                            explanation=f'整单出票利润{ticket_total}元＋增值利润{ancillary_total}元＝{total}元，'
                                        f'通用配置止损下界{boundary}元，{"满足" if passed else "突破"}止损条件')
            else:
                result['missing'].append(item['explanation'])
            result['tickets'].append(item)

    thresholds = {row['stopLoss'] for row in result['tickets']}
    if len(thresholds) == 1:
        result['stopLoss'] = next(iter(thresholds))
    statuses = {row['status'] for row in result['tickets']}
    result['status'] = 'problem' if 'problem' in statuses else 'insufficient' if 'insufficient' in statuses else 'supported'
    result['summary'] = {
        'problem': '整单综合利润突破适用通用配置的止损下界',
        'insufficient': '整单综合利润已算出，适用通用配置证据不完整',
        'supported': '整单出票利润加增值利润满足适用通用配置的止损条件',
    }[result['status']]
    result['missing'] = sorted(set(result['missing']))
    return result
