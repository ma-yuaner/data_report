"""Eight confirmed bet-loss reasons: original CNY profit vs each ticket's stop loss."""
from decimal import localcontext
from .risk_child_loss import number


def evaluate_bet(evidence, version):
    order = evidence['order']
    base = {'ruleVersion': version, 'status': 'insufficient', 'summary': '证据不足',
            'platform': order.get('ota_code'), 'tickets': [], 'stopLoss': None,
            'logReferences': [], 'missing': [], 'commissionIncluded': False,
            'formula': 'issue_profit >= -stop_loss', 'currency': 'CNY', 'grain': 'single_ticket'}
    if not evidence.get('complete'):
        return {**base, 'missing': ['完整出票明细'], 'summary': '出票范围不完整，不能判为通过'}
    if not evidence.get('issues'):
        return {**base, 'missing': ['出票明细'], 'summary': '没有可核实的出票明细'}
    for issue in evidence['issues']:
        config = issue.get('thresholdConfiguration') or {}
        profit, threshold = number(issue.get('issue_profit')), number(config.get('amount'))
        result = {'id': str(issue['id']), 'profit': issue.get('issue_profit'),
                  'profitSource': 'order_info_issue.issue_profit', 'commission': None, 'currency': 'CNY',
                  'segmentCount': issue.get('segmentCount'), 'configuration': config,
                  'stopLoss': None, 'status': 'insufficient'}
        missing = []
        if profit is None:
            missing.append('出票利润缺失或无效')
        if config.get('status') != 'ready' or threshold is None or threshold < 0:
            missing.append(config.get('reason') or '出票时单票止损值缺失或无效')
        else:
            result['stopLoss'] = format(threshold, 'f')
        if missing:
            result['explanation'] = '；'.join(missing)
            base['missing'].extend(missing)
        else:
            with localcontext() as context:
                context.prec = 64
                boundary = -threshold
                passed = profit >= boundary
            verdict = '满足' if passed else '突破'
            result.update(status='supported' if passed else 'problem',
                          adjustedProfit=format(profit, 'f'), boundary=format(boundary, 'f'),
                          explanation=f'单票出票利润{profit}元 ≥ －止损值{threshold}元：{verdict}止损条件（不加佣金或预期收益）')
        base['tickets'].append(result)
    base['missing'] = sorted(set(base['missing']))
    thresholds = {row['stopLoss'] for row in base['tickets']}
    if len(thresholds) == 1:
        base['stopLoss'] = next(iter(thresholds))
    statuses = {row['status'] for row in base['tickets']}
    status = 'problem' if 'problem' in statuses else 'insufficient' if 'insufficient' in statuses else 'supported'
    base.update(status=status, summary={
        'problem': '至少一张票的出票利润突破单票止损值，选因有问题',
        'insufficient': '部分票缺少出票利润或出票时止损证据，不能判为通过',
        'supported': '全部出票明细的原始利润均满足单票止损条件',
    }[status])
    return base


def evaluate_normal(evidence, version):
    """Normal business uses the same per-ticket historical stop-loss arithmetic.

    A supported result closes the automatic check; manual sampling remains optional.
    No commission, platform prerequisite, cross-order averaging or human verdict is added.
    """
    result = evaluate_bet(evidence, version)
    result['summary'] = {
        'supported': '正常业务全部出票明细均满足出票时单票止损条件，自动通过（已闭环），可人工抽查',
        'problem': '正常业务至少一张票的出票利润突破单票止损值，需人工核实',
        'insufficient': '正常业务取证不完整或缺少出票利润、出票时止损证据，不能判为通过',
    }[result['status']]
    return result
