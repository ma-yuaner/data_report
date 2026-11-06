"""Order-level analytics from current catalog + metric snapshots + human recognition."""
from decimal import Decimal


def aggregate(rows, statuses, reviews, labels):
    categories, departments = {}, {}
    totals = {'orders':len(rows), 'autoPassed':0, 'autoConcluded':0, 'humanReviewed':0, 'humanProblems':0, 'includedErrors':0, 'profitMissing':0}
    def bucket(target, key, label):
        return target.setdefault(key, {'key':key,'label':label,'orders':0,'problemOrders':0,'includedErrors':0,'profitMissing':0,'_profit':Decimal(0),'_loss':Decimal(0)})
    def add(b, row, problem, included):
        b['orders']+=1;b['problemOrders']+=int(problem);b['includedErrors']+=int(included)
        if row.get('total_profit') is None:b['profitMissing']+=1
        else:
            p=Decimal(str(row['total_profit']));b['_profit']+=p
            if p<0:b['_loss']+=p
    for row in rows:
        identifier=str(row['id']);status=statuses.get(identifier,{})
        totals['autoPassed']+=int(status.get('status')=='supported')
        totals['autoConcluded']+=int(status.get('status') in ('supported','problem'))
        review=reviews.get(identifier)
        current=bool(review and ((review.get('snapshotKind')=='prepared' and review.get('resultId')==status.get('resultId')) or (review.get('snapshotKind')=='catalog' and review.get('catalogRunId')==row.get('catalog_run_id') and not status.get('resultId'))))
        problem=current and review['conclusion']=='problem'
        included=problem and review.get('_disposition')=='included'
        totals['humanReviewed']+=int(current and review['conclusion'] in ('no_issue','problem'))
        totals['humanProblems']+=int(problem);totals['includedErrors']+=int(included)
        totals['profitMissing']+=int(row.get('total_profit') is None)
        reason=row['profit_reason_type'];add(bucket(categories,reason,labels.get(reason,reason)),row,problem,included)
        names=row.get('departments') or ['业务部门未同步']
        for name in set(names):add(bucket(departments,name,name),row,problem,included)
    def finish(values):
        output=[]
        for value in values.values():
            p=value.pop('_profit');loss=value.pop('_loss')
            value.update(totalProfit=None if value['profitMissing'] else str(p),lossProfit=None if value['profitMissing'] else str(loss))
            output.append(value)
        return output
    return {'metrics':totals,'categories':sorted(finish(categories),key=lambda x:(x['totalProfit'] is None,Decimal(x['totalProfit'] or '0'))),
            'departments':sorted(finish(departments),key=lambda x:(-x['problemOrders'],x['label'])),
            'notes':['统计范围为所选出票日期风控目录，跨日订单去重；自动形成结论占比=(自动通过+疑似问题)/目录订单数。',
                     '总利润为订单全部出票明细issue_profit之和，不加佣金；任一缺失时该组利润为空，不能当0。',
                     '部门取出票核对表业务归属，不代表责任部门；一单多部门分别展示，部门行不可相加为去重总量。',
                     '人工问题与计入差错按当前有效人工结论统计，历史失效结论不计入。']}


def analytics(service, owner, start, end):
    # HTTP only reads published aggregates. It never scans catalog order facts.
    from .risk_analytics_snapshot import read_snapshot
    return read_snapshot(service.config, start, end)
