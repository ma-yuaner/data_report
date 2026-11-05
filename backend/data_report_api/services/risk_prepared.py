"""Consume atomically published sibebid preparation; no ERP connection or live fallback."""
from datetime import date,timedelta
import json,time,uuid
from pathlib import Path
from .risk_commission_rule import RULE_ID
from .risk_verification_flow import FlowError
from .risk_child_loss import SUPPORTED_REASONS


def consume(service,owner,body,progress):
    first=date.fromisoformat(body['startDate']);last=date.fromisoformat(body['endDate'])
    days=[(first+timedelta(days=n)).isoformat() for n in range((last-first).days+1)]
    expected_engine=json.loads(Path(__file__).with_name('risk_engine_bundle.meta.json').read_text(encoding='utf-8'))['sha256']
    with service.db() as db:
        ready=db.execute("SELECT p.issue_date,p.etl_run_id,p.rule_version,p.engine_hash,p.row_count,p.diagnostics_json FROM bi_risk_prepared_day p JOIN bi_risk_sync_day d ON d.issue_date=p.issue_date AND d.etl_run_id=p.etl_run_id WHERE p.issue_date>=? AND p.issue_date<=?",(days[0],days[-1])).fetchall()
        covered={str(row['issue_date'])[:10]:row for row in ready if row['rule_version']==RULE_ID and row['engine_hash']==expected_engine}
        missing=[day for day in days if day not in covered]
        if missing:raise FlowError('所选日期尚无当前版本完整清洗结果：'+','.join(missing)+'；请先运行独立风控清洗任务，页面不会回退逐单查ERP',409)
        reasons=(body['reason'],) if body.get('reason') else SUPPORTED_REASONS
        marks=','.join(['?']*len(reasons))
        scope="o.issue_date>=? AND o.issue_date<=? AND o.profit_reason_type IN ("+marks+") AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date AND newer.issue_date<=?)"
        params=(days[0],days[-1],*reasons,days[-1])
        expected=db.execute('SELECT COUNT(*) AS n FROM bi_risk_order_day o WHERE '+scope,params).fetchone()['n']
        rows=db.execute("SELECT o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id,o.issue_date,p.evidence_hash,p.result_json,p.prepared_at FROM bi_risk_order_day o JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id AND p.etl_run_id=o.etl_run_id AND p.reason_code=o.profit_reason_type AND p.source_updated_at <=> o.update_time AND p.rule_version=? AND p.engine_hash=? WHERE "+scope+" ORDER BY o.order_id LIMIT 2001",(RULE_ID,expected_engine,*params)).fetchall()
        if int(expected)>2000:raise FlowError('所选范围超过2000单，请缩小日期范围；清洗数据仍保留',413)
        if len(rows)!=int(expected):raise FlowError('清洗结果与目录批次或源版本不一致，未加载部分结果；请检查清洗报告',409)
        lock=db.execute("SELECT status,updated FROM auto_jobs WHERE id=? AND owner=? FOR UPDATE",(body['id'],owner)).fetchone()
        if not lock or lock['status']!='running' or lock['updated']<time.time()-600:raise FlowError('加载任务已失效，未发布结果',409)
        counts={};loaded=0
        for row in rows:
            result=json.loads(row['result_json'])
            if result.get('ruleVersion')!=RULE_ID or result.get('engineHash')!=expected_engine or result.get('status') not in ('supported','problem','insufficient','rule_pending'):
                raise FlowError('清洗结果内容或版本不一致，未发布结果',409)
            result.update(id=uuid.uuid4().hex,orderId=str(row['order_id']),reasonCode=row['profit_reason_type'],
                          sourceUpdatedAt=None if row['update_time'] is None else str(row['update_time']).replace(' ','T'),
                          catalogRunId=row['etl_run_id'],issueDate=str(row['issue_date'])[:10],checkedAt=str(row['prepared_at']).replace(' ','T'),loadedAt=service_now(),
                          checkedAtEpoch=prepared_epoch(row['prepared_at']),jobId=body['id'],evidenceHash=row['evidence_hash'],sourceMode='prepared_etl')
            db.execute('INSERT INTO auto_results VALUES(?,?,?,?,?)',(result['id'],owner,result['orderId'],time.time(),json.dumps(result,ensure_ascii=False)))
            counts[result['status']]=counts.get(result['status'],0)+1;loaded+=1
        body.update(status='complete',phase='complete',done=loaded,total=loaded,remaining=0,refreshedRows=0,reused=loaded,
                    message='已加载独立清洗核实结果；未查询ERP',sourceMode='prepared_etl',outcomes=counts,
                    preparationReports=[json.loads(covered[day]['diagnostics_json']) for day in days])
        db.execute("UPDATE auto_jobs SET status='complete',updated=?,body=? WHERE id=? AND owner=? AND status='running'",(time.time(),json.dumps(body,ensure_ascii=False),body['id'],owner))


def service_now():
    from datetime import datetime,timezone
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def prepared_epoch(value):
    from datetime import datetime,timezone
    parsed=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=timezone(timedelta(hours=8))).timestamp() if parsed.tzinfo is None else parsed.timestamp()
