"""Read committed daily verification facts, independently of an account's load jobs."""
import hashlib,json
from pathlib import Path
from .risk_commission_rule import RULE_ID
from .risk_child_loss import SUPPORTED_REASONS
from .risk_order_evidence import _rows,order_id,EvidenceError

PROJECTION="""o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date,
 p.etl_run_id AS prepared_run_id,p.rule_version,p.engine_hash,p.source_updated_at,p.reason_code,
 p.evidence_hash,p.result_json,p.prepared_at,d.etl_run_id AS ready_run_id,
 d.rule_version AS ready_version,d.engine_hash AS ready_hash"""
JOINS=""" FROM bi_risk_order_day o
 LEFT JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id
 LEFT JOIN bi_risk_prepared_day d ON d.issue_date=o.issue_date"""
STATUS_PROJECTION=PROJECTION.replace('p.result_json,',
    "JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.status')) AS published_status,"
    "JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.ruleVersion')) AS body_version,"
    "JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.engineHash')) AS body_hash,")


def engine_hash():
    return json.loads(Path(__file__).with_name('risk_engine_bundle.meta.json').read_text(encoding='utf-8'))['sha256']


def stamp(value):return None if value is None else str(value).replace(' ','T')


def fact(row, expected_engine_hash=None):
    if row.get('profit_reason_type') not in SUPPORTED_REASONS:return None
    digest=expected_engine_hash or engine_hash()
    ready=(row.get('prepared_run_id')==row.get('catalog_run_id')==row.get('ready_run_id')
           and row.get('catalog_run_id') is not None
           and row.get('rule_version')==row.get('ready_version')==RULE_ID
           and row.get('engine_hash')==row.get('ready_hash')==digest
           and row.get('reason_code')==row.get('profit_reason_type')
           and stamp(row.get('source_updated_at'))==stamp(row.get('update_time')))
    if not ready:return None
    if 'published_status' in row:
        body={'status':row['published_status'],'ruleVersion':row.get('body_version'),'engineHash':row.get('body_hash')}
    else:
        if not row.get('result_json'):return None
        try:body=json.loads(row['result_json'])
        except (ValueError,TypeError):raise EvidenceError('已发布清洗结果内容损坏，请检查对应日期批次',503) from None
    if not isinstance(body,dict):raise EvidenceError('已发布清洗结果内容损坏，请检查对应日期批次',503)
    if (body.get('ruleVersion')!=RULE_ID or body.get('engineHash')!=digest
            or body.get('status') not in ('supported','problem','insufficient','failed')):
        raise EvidenceError('已发布清洗结果版本或状态不一致',503)
    identity=[str(row['issue_date'])[:10],str(row['order_id']),RULE_ID,digest,row['evidence_hash']]
    stable_id=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32]
    body.update(id=stable_id,orderId=str(row['order_id']),reasonCode=row['profit_reason_type'],
                sourceUpdatedAt=stamp(row['update_time']),catalogRunId=row['catalog_run_id'],
                issueDate=str(row['issue_date'])[:10],checkedAt=stamp(row['prepared_at']),
                sourceMode='prepared_etl',isCurrent=True,evidenceHash=row['evidence_hash'])
    return body


def statuses(cursor,scope,parameters):
    marks=','.join(['%s']*len(SUPPORTED_REASONS))
    cursor.execute('SELECT '+STATUS_PROJECTION+JOINS+' WHERE '+scope+' AND o.profit_reason_type IN ('+marks+') LIMIT 20001',(*parameters,*SUPPORTED_REASONS))
    rows=_rows(cursor)
    if len(rows)>20000:raise EvidenceError('已接规则订单超过当前汇总上限，请缩小日期范围',413)
    result={}
    digest=engine_hash()
    for row in rows:
        body=fact(row, digest)
        result[str(row['order_id'])]={'status':body['status'] if body else 'outdated' if row.get('prepared_run_id') else 'unchecked',
                                    'caseId':None,'resultId':body['id'] if body else None,'reasonCode':row['profit_reason_type']}
    return result


def one(fetch,identifier,issue_date=None,lock=False):
    args=[order_id(identifier)];scope='o.order_id=%s'
    if issue_date:
        from datetime import date
        try:parsed=date.fromisoformat(str(issue_date))
        except (ValueError,TypeError):raise EvidenceError('出票日期无效') from None
        scope+=' AND o.issue_date=%s';args.append(parsed.isoformat())
    rows=fetch('SELECT '+PROJECTION+JOINS+' WHERE '+scope+' ORDER BY o.issue_date DESC LIMIT 1'+(' FOR UPDATE' if lock else ''),tuple(args))
    return fact(rows[0]) if rows else None


def coverage(cursor,first,last):
    cursor.execute('''SELECT p.issue_date,p.diagnostics_json FROM bi_risk_prepared_day p JOIN bi_risk_sync_day c
      ON c.issue_date=p.issue_date AND c.etl_run_id=p.etl_run_id
      WHERE p.issue_date>=%s AND p.issue_date<=%s AND p.rule_version=%s AND p.engine_hash=%s''',
                   (first.isoformat(),last.isoformat(),RULE_ID,engine_hash()))
    rows=_rows(cursor);ready={str(r['issue_date'])[:10] for r in rows};reports=[]
    for row in rows:
        report=json.loads(row['diagnostics_json'])
        reports.append({key:report.get(key) for key in ('day','orders','statuses','insufficientCauses','seconds')})
    from datetime import timedelta
    days=[(first+timedelta(days=n)).isoformat() for n in range((last-first).days+1)]
    return {'readyDays':sorted(ready),'missingDays':[d for d in days if d not in ready],'reports':sorted(reports,key=lambda r:r['day']),
            'mode':'daily_prepared_facts','ruleVersion':RULE_ID}
