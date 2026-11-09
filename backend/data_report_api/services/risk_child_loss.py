"""RLA040: average issued-ticket profit, no commission; Ctrip split-order scope."""
from decimal import Decimal, localcontext
import re
from .risk_order_evidence import _rows

CHILD_REASON='RLA040'
ANCILLARY_REASON='RLA041'
# Both codes map exactly to 正常业务 in the published PRODUCT_PROFIT_REASON_TYPE dictionary.
NORMAL_REASONS=('R001','RPA000')
PROFIT_REASONS={
    'RPA006':'返点盈利', 'RPA005':'私有运价盈利', 'RPA007':'汇率盈利',
    'RPA009':'NDC盈利', 'RPA002':'K位盈利', 'R026':'降舱/废票盈利',
    'RPB007':'动态舱位盈利', 'RPA001':'官网盈利', 'RPA013':'加价盈利',
    'RPA011':'境内外配置票价差盈利', 'RPA012':'外采盈利',
}
BET_REASONS={
    'RLA068':'对赌亏损-K位','RLA047':'对赌亏损-NDC对赌',
    'RLA50':'对赌亏损-国内行程','RLA046':'对赌亏损-辅营',
    'RLA045':'对赌亏损-退改','RLA069':'对赌亏损-私有',
    'RLA070':'对赌亏损-青年票','RLA067':'对赌亏损-降舱',
}
SUPPORTED_REASONS=('RLA013',CHILD_REASON,ANCILLARY_REASON,*BET_REASONS,*NORMAL_REASONS,*PROFIT_REASONS)
ORDER_FIELDS='id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,ota_order_no,relation_ota_order_no,profit_reason_type,update_time'
RELATED_SQL="SELECT "+ORDER_FIELDS+" FROM order_info WHERE ota_code=%s AND ota_site_code <=> %s AND (ota_order_no IN ({marks}) OR relation_ota_order_no IN ({marks})) ORDER BY id LIMIT 101"
AGE_SQL="SELECT i.id,p.age_type FROM order_info_issue i LEFT JOIN order_info_passenger p ON p.id=i.passenger_id AND p.order_id=i.order_id WHERE i.order_id=%s ORDER BY i.id LIMIT 201"


def read_child_evidence(cursor,order,cache,read_basic):
    nodes={str(order['id']):order};seen=set();complete=True;problems=[]
    if order.get('ota_code')=='CTRIP':
        if not order.get('ota_order_no'):
            complete=False;problems.append('携程OTA订单号缺失，不能确定拆单范围')
        while complete:
            codes={str(r.get(k)) for r in nodes.values() for k in ('ota_order_no','relation_ota_order_no') if r.get(k)}
            pending=codes-seen
            if not pending:break
            marks=','.join(['%s']*len(pending));params=sorted(pending)
            cursor.execute(RELATED_SQL.format(marks=marks),(order['ota_code'],order.get('ota_site_code'),*params,*params))
            found=_rows(cursor)
            if len(found)>100:
                complete=False;problems.append('携程关联单超过100单，未使用截断范围');break
            for row in found:nodes[str(row['id'])]=row
            seen.update(pending)
            if len(nodes)>100:
                complete=False;problems.append('携程关联闭包超过100单');break
        wanted={str(r['relation_ota_order_no']) for r in nodes.values() if r.get('relation_ota_order_no')}
        actual={str(r['ota_order_no']) for r in nodes.values() if r.get('ota_order_no')}
        if wanted-actual:
            complete=False;problems.append('关联OTA订单尚未找到，不能用部分订单计算平均利润')
    elif not order.get('ota_code'):
        complete=False;problems.append('平台缺失，不能确定核算范围')
    issues=[];anchor=[];scope=[]
    for key,node in sorted(nodes.items()):
        base=read_basic(cursor,key,cache,_basic=True)
        if not base['complete'] or not base['issues']:
            complete=False;problems.append('核算范围存在出票明细缺失或截断')
        cursor.execute(AGE_SQL,(node['id'],));ages=_rows(cursor)
        mapped={str(row['id']):row.get('age_type') for row in ages}
        if len(ages)>200 or len(mapped)!=len(ages):
            complete=False;problems.append('出票乘机人关联截断或重复')
        for row in base['issues']:
            row['ageType']=mapped.get(str(row['id']))
            issues.append(row)
        if key==str(order['id']):anchor=base['issues']
        scope.append({'orderId':key,'updatedAt':node.get('update_time'),'ticketCount':len(base['issues'])})
        if len(issues)>2000:
            complete=False;problems.append('关联范围超过2000票');break
    return {'order':order,'issues':anchor,'groupIssues':issues,'groupScope':scope,'complete':complete,
            'scopeProblems':sorted(set(problems)),'logs':[]}


def number(raw):
    if isinstance(raw,bool) or not isinstance(raw,(str,int,Decimal)) or not re.fullmatch(r'-?[0-9]{1,20}(?:\.[0-9]{1,12})?',str(raw)):return None
    return Decimal(str(raw))


def evaluate_child(evidence,version):
    order=evidence['order'];all_tickets=evidence.get('groupIssues',[])
    base={'ruleVersion':version,'status':'insufficient','summary':'证据不足','tickets':[],
          'platform':order.get('ota_code'),'stopLoss':None,'missing':[], 'logReferences':[],
          'aggregate':{'orderCount':len(evidence.get('groupScope',[])),'ticketCount':len(all_tickets),
                       'scope':evidence.get('groupScope',[]),'commissionIncluded':False}}
    if not evidence.get('complete') or not all_tickets:
        return {**base,'missing':evidence.get('scopeProblems') or ['完整关联范围及出票明细'],'summary':'核算范围不完整，不能判定综合无亏损'}
    types=[row.get('ageType') for row in all_tickets]
    child_count=sum(t=='CHD' for t in types);infant_count=sum(t=='INF' for t in types)
    base['aggregate'].update(childTickets=child_count,infantTickets=infant_count)
    if not child_count and not infant_count:
        if any(t not in ('ADU','CHD','INF') for t in types):
            return {**base,'missing':['乘机人年龄类型'],'summary':'缺少可靠年龄类型，不能认定全为成人'}
        return {**base,'status':'problem','summary':'核算范围全部为成人，不允许选择综合无亏损－儿童/婴儿'}
    profits=[number(row.get('issue_profit')) for row in all_tickets]
    if any(p is None for p in profits):
        return {**base,'missing':['完整出票利润（CNY）'],'summary':'有出票利润缺失或无效，未补0计算'}
    with localcontext() as context:
        context.prec=64
        total=sum(profits,Decimal(0));count=len(profits);average=total/Decimal(count)
        base['aggregate'].update(totalProfit=format(total,'f'),averageProfit=format(average,'f'),averageProfitDisplay=format(average,'.4f'),currency='CNY',averageFormula='sum(issue_profit) / issued_ticket_count')
        statuses=[]
        for issue in evidence['issues']:
            config=issue.get('thresholdConfiguration') or {};threshold=number(config.get('amount'))
            result={'id':str(issue['id']),'profit':str(issue.get('issue_profit')),'commission':None,'currency':'CNY',
                    'segmentCount':issue.get('segmentCount'),'configuration':config,'stopLoss':config.get('amount'),
                    'status':'insufficient','explanation':config.get('reason') or '出票时止损值证据不足'}
            if config.get('status')=='ready' and threshold is not None and threshold>=0:
                # Cross-multiply to avoid rounding a repeating average across the boundary.
                passed=total>=-threshold*Decimal(count)
                verdict='满足' if passed else '不满足'
                result.update(status='supported' if passed else 'problem',adjustedProfit=format(average,'.4f'),
                              boundary=format(-threshold,'f'),explanation=f'总出票利润{total}元 / {count}票；平均利润与－{threshold}元比较：{verdict}（不加佣金，边界按总利润≥－阈值×票数精确比较）')
            statuses.append(result['status']);base['tickets'].append(result)
    values={r['stopLoss'] for r in base['tickets']}
    if len(values)==1:base['stopLoss']=next(iter(values))
    if not statuses:return {**base,'missing':['当前订单出票明细']}
    status='problem' if 'problem' in statuses else 'insufficient' if 'insufficient' in statuses else 'supported'
    base.update(status=status,summary={'problem':'综合平均单票利润突破当前单至少一张票的止损阈值',
                'insufficient':'存在儿童/婴儿，但当前单部分止损证据不足',
                'supported':'存在儿童/婴儿，综合平均单票利润满足当前单止损阈值'}[status])
    return base
