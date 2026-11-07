"""Scheduled, target-only analytics snapshots. HTTP never aggregates order facts."""
import argparse
import hashlib
import json
import sys
import uuid
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from zoneinfo import ZoneInfo

from .risk_auto_store import RiskAutoStore, StoreUnavailable, StoreCommittedCleanupError
from .risk_order_evidence import EvidenceError
from .risk_prepared_facts import STATUS_PROJECTION, JOINS, fact, engine_hash
from .risk_commission_rule import RULE_ID
from .risk_verification_overview import _period, METRIC_JOIN, METRIC_FIELDS

MANIFEST = 'bi_risk_analytics_snapshot'
BUCKET = 'bi_risk_analytics_bucket'
VERSION = 'risk-analytics-v4'
INTERVAL_MINUTES = 15
COUNTERS = ('orders','auto_passed','auto_concluded','human_reviewed','human_problems','included_errors','profit_missing')
LOCK = 'risk-analytics-snapshot-v4'


class AnalyticsError(ValueError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def safe_error(error):
    if isinstance(error,AnalyticsError):return error.code
    if isinstance(error,EvidenceError):return 'ANALYTICS_FACT_VERSION_INVALID'
    if isinstance(error,StoreUnavailable):
        cause=error.__cause__
        if getattr(cause,'args',()) and cause.args[0]==2013:return 'ANALYTICS_DATABASE_CONNECTION_LOST'
        return 'ANALYTICS_DATABASE_OPERATION_NOT_CONFIRMED'
    if isinstance(error,ValueError):return 'ANALYTICS_SOURCE_VALUE_INVALID'
    return 'ANALYTICS_REFRESH_NOT_CONFIRMED'


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def day(value):
    return str(value)[:10]


def current_rules(raw):
    try:
        meta = json.loads(raw)
    except (ValueError, TypeError):
        return False
    return isinstance(meta, dict) and meta.get('ruleVersion') == RULE_ID and meta.get('engineHash') == engine_hash()


def request_snapshot(config, start, end, store=None, force=False):
    _, last = _period(start, end)
    if last < date.min + timedelta(days=30):raise EvidenceError('分析结束日期过早')
    store = store or RiskAutoStore(config)
    at = now()
    with store.db() as db:
        previous = db.execute('SELECT snapshot_id,schema_version,checked_at,last_error_code,body FROM '+MANIFEST+' WHERE end_date=?',(last.isoformat(),)).fetchone()
        if previous and previous.get('checked_at') and not force:
            checked = datetime.fromisoformat(str(previous['checked_at']))
            if previous['snapshot_id'] and previous['schema_version'] == VERSION and current_rules(previous.get('body')) and not previous['last_error_code'] and checked >= at - timedelta(minutes=INTERVAL_MINUTES):
                return {'status':'ready','endDate':last.isoformat(),'refreshMinutes':INTERVAL_MINUTES}
        db.execute('INSERT INTO '+MANIFEST+' (end_date,schema_version,requested_at,request_generation,processed_generation,retry_after) VALUES(?,?,?,1,0,?) ON DUPLICATE KEY UPDATE requested_at=VALUES(requested_at),request_generation=request_generation+1',
                   (last.isoformat(), VERSION, at, at))
    return {'status':'queued', 'endDate':last.isoformat(), 'refreshMinutes':INTERVAL_MINUTES,
            'message':'分析请求已排队，由定时任务生成；查询不实时扫描订单'}


def _freshness(meta, first, last):
    days = [r for r in meta.get('catalogDays',[]) if first.isoformat() <= day(r['issue_date']) <= last.isoformat()]
    present = {day(r['issue_date']) for r in days}
    missing = []; cursor = first
    while cursor <= last:
        if cursor.isoformat() not in present: missing.append(cursor.isoformat())
        cursor += timedelta(days=1)
    stamps = [str(r['synced_at']) for r in days if r.get('synced_at')]
    return {'source':'sibebid','mode':'etl_catalog','complete':not missing,'missingDays':missing,'days':days,
            'oldestSyncedAt':min(stamps) if stamps else '', 'newestSyncedAt':max(stamps) if stamps else ''}


def summarize_buckets(rows):
    result = {'metrics':{name:0 for name in ('orders','autoPassed','autoConcluded','humanReviewed','humanProblems','includedErrors','profitMissing')},'categories':[],'departments':[]}
    mapping = dict(zip(COUNTERS, ('orders','autoPassed','autoConcluded','humanReviewed','humanProblems','includedErrors','profitMissing')))
    for row in rows:
        if row['dimension'] == 'total':
            for key, output in mapping.items(): result['metrics'][output] += int(row[key] or 0)
            continue
        item = {'key':row['group_key'],'label':row['group_label'],'orders':int(row['orders']),
                'problemOrders':int(row['human_problems']),'includedErrors':int(row['included_errors']),
                'profitMissing':int(row['profit_missing']),
                'totalProfit':None if row['profit_missing'] else str(row['known_profit']),
                'lossProfit':None if row['profit_missing'] else str(row['known_loss'])}
        result['categories' if row['dimension'] == 'category' else 'departments'].append(item)
    result['categories'].sort(key=lambda r:(r['totalProfit'] is None,Decimal(r['totalProfit'] or '0'),r['key']))
    result['departments'].sort(key=lambda r:(-r['problemOrders'],r['label']))
    return result


def read_snapshot(config, start, end, store=None):
    first, last = _period(start, end)
    store = store or RiskAutoStore(config)
    # Manifest + buckets are read from one database snapshot during publication.
    with store.db(consistent_snapshot=True) as db:
        row = db.execute('SELECT * FROM '+MANIFEST+' WHERE end_date=?',(last.isoformat(),)).fetchone()
        if not row or not row['snapshot_id'] or row['schema_version'] != VERSION:
            return {'status':'pending','period':{'startDate':start,'endDate':end},'refreshMinutes':INTERVAL_MINUTES,
                    'lastErrorCode':row.get('last_error_code') if row else None,
                    'message':'所选结束日期的分析快照尚未生成，请等待定时分析任务；不会按实时逐单计算回退'}
        fields = ','.join('SUM('+key+') AS '+key for key in (*COUNTERS,'known_profit','known_loss'))
        rows = db.execute('SELECT dimension,group_key,group_label,'+fields+' FROM '+BUCKET+' WHERE end_date=? AND snapshot_id=? AND issue_date>=? AND issue_date<=? GROUP BY dimension,group_key,group_label',
                          (last.isoformat(),row['snapshot_id'],first.isoformat(),last.isoformat())).fetchall()
    meta = json.loads(row['body'])
    if not isinstance(meta,dict) or meta.get('version') != VERSION:
        raise EvidenceError('分析快照内容无效，请联系管理员检查定时任务',503)
    if not current_rules(row['body']):
        return {'status':'pending','period':{'startDate':start,'endDate':end},'refreshMinutes':INTERVAL_MINUTES,
                'lastErrorCode':'ANALYTICS_RULE_VERSION_OUTDATED',
                'message':'分析快照使用旧核实规则，请等待当前规则清洗及分析调度完成；旧统计保留，不作为当前结果展示'}
    freshness=_freshness(meta,first,last)
    if not freshness['days']:
        return {'status':'pending','period':{'startDate':start,'endDate':end},'refreshMinutes':INTERVAL_MINUTES,
                'lastErrorCode':'CATALOG_RANGE_NOT_READY','message':'所选出票日期目录尚未同步，请先完成对应日期风控清洗；分析调度不查ERP补数据，未同步不代表零订单'}
    return {**summarize_buckets(rows),'status':'ready','period':{'startDate':start,'endDate':end},
            'dataFreshness':freshness,'generatedAt':str(row['generated_at']),
            'sourceCutoff':str(row['source_cutoff']),'checkedAt':str(row['checked_at']),
            'refreshPending':row['request_generation']>row['processed_generation'],
            'lastErrorCode':row['last_error_code'],'refreshMinutes':INTERVAL_MINUTES,
            'notes':['读取每15分钟调度发布的分析快照，人工认定在下一次成功刷新后体现；实时案例跟进不受影响。',
                     '按查询结束日预先选择每单最后出票日，再按起日汇总，跨日订单不重复相加。',
                     '自动形成结论占比=(自动通过+疑似问题)/目录订单数；任一利润缺失则该分类利润合计为空。',
                     '业务部门归属不代表责任认定；一单多部门分别展示，部门行不可相加为去重总量。']}


class Builder:
    def __init__(self, end, labels, limit=50000):
        self.end=end; self.labels=labels; self.limit=limit; self.groups={}; self.orders=0

    def add(self,row,body):
        status=body['status'] if body else None
        review=json.loads(row['review_body']) if row.get('review_body') else None
        if review is not None and not isinstance(review,dict):raise AnalyticsError('ANALYTICS_REVIEW_INVALID')
        current=bool(review and ((review.get('snapshotKind')=='prepared' and body and review.get('resultId')==body['id']) or (review.get('snapshotKind')=='catalog' and not body and review.get('catalogRunId')==row['catalog_run_id'])))
        reviewed=current and review.get('conclusion') in ('no_issue','problem')
        problem=current and review.get('conclusion')=='problem'
        metric=json.loads(row['metric_body']) if row.get('metric_body') else {}
        if not isinstance(metric,dict) or (row.get('metric_body') and metric.get('version')!=3):raise AnalyticsError('ANALYTICS_METRIC_VERSION_INVALID')
        departments=metric.get('departments') or ['业务部门未同步']
        if not isinstance(departments,list) or any(not isinstance(v,str) for v in departments):raise AnalyticsError('ANALYTICS_DEPARTMENT_INVALID')
        reason=str(row['profit_reason_type'])
        dimensions=[('total','total','总量'),('category',reason,self.labels.get(reason,reason))]
        dimensions += [('department',v,v) for v in sorted(set(departments))]
        counts=dict(zip(COUNTERS,(1,int(status=='supported'),int(status in ('supported','problem')),int(bool(reviewed)),int(bool(problem)),int(bool(problem and row.get('case_disposition')=='included')),int(row.get('total_profit') is None))))
        amount=None if row.get('total_profit') is None else Decimal(str(row['total_profit']))
        if amount is not None and (not amount.is_finite() or amount != amount.quantize(Decimal('0.0001'))):raise AnalyticsError('ANALYTICS_PROFIT_INVALID')
        for dimension,key,label in dimensions:
            if len(key)>200 or len(label)>500:raise AnalyticsError('ANALYTICS_DIMENSION_LENGTH')
            identity=(day(row['issue_date']),dimension,key)
            if identity not in self.groups:
                if len(self.groups)>=self.limit:raise AnalyticsError('ANALYTICS_BUCKET_LIMIT')
                self.groups[identity]={'issue_date':identity[0],'dimension':dimension,'group_hash':hashlib.sha256(key.encode()).hexdigest(),'group_key':key,'group_label':label,
                                       **{k:0 for k in COUNTERS},'known_profit':Decimal('0.0000'),'known_loss':Decimal('0.0000')}
            item=self.groups[identity]
            for key in COUNTERS:item[key]+=counts[key]
            if amount is not None:
                with localcontext() as context:
                    context.prec=50
                    item['known_profit']+=amount
                    if amount<0:item['known_loss']+=amount
                    if abs(item['known_profit'])>=Decimal('1e34') or abs(item['known_loss'])>=Decimal('1e34'):raise AnalyticsError('ANALYTICS_PROFIT_OVERFLOW')
        self.orders+=1


def source_metadata(db,first,last,digest):
    bounds=(first.isoformat(),last.isoformat())
    meta={'version':VERSION,'ruleVersion':RULE_ID,'engineHash':digest,'windowStart':bounds[0],'windowEnd':bounds[1]}
    for key,table,columns in (
        ('catalogDays','bi_risk_sync_day','issue_date,etl_run_id,row_count,synced_at'),
        ('preparedDays','bi_risk_prepared_day','issue_date,etl_run_id,rule_version,engine_hash,prepared_at'),
        ('metricDays','bi_risk_order_metric_day_ready','issue_date,catalog_run_id,row_count,measured_at')):
        meta[key]=[dict(r) for r in db.execute('SELECT '+columns+' FROM '+table+' WHERE issue_date>=? AND issue_date<=? ORDER BY issue_date',bounds).fetchall()]
    actual=db.execute('SELECT issue_date,etl_run_id,COUNT(*) AS n FROM bi_risk_order_day WHERE issue_date>=? AND issue_date<=? GROUP BY issue_date,etl_run_id',bounds).fetchall()
    expected={day(r['issue_date']):r for r in meta['catalogDays']}
    counts={}
    for row in actual:
        key=day(row['issue_date'])
        if key not in expected or key in counts or row['etl_run_id']!=expected[key]['etl_run_id']:raise AnalyticsError('ANALYTICS_CATALOG_BATCH_MISMATCH')
        counts[key]=int(row['n'])
    if any(counts.get(key,0)!=int(value['row_count']) for key,value in expected.items()):raise AnalyticsError('ANALYTICS_CATALOG_COUNT_MISMATCH')
    meta['reviewVersion']=dict(db.execute('SELECT COUNT(*) AS n,COALESCE(SUM(version),0) AS v FROM bi_risk_order_reviews WHERE issue_date>=? AND issue_date<=?',bounds).fetchone())
    meta['caseVersion']=dict(db.execute('SELECT COUNT(*) AS n,COALESCE(SUM(c.version),0) AS v FROM bi_risk_followup_cases c WHERE EXISTS (SELECT 1 FROM bi_risk_order_reviews r WHERE r.case_id=c.id AND r.issue_date>=? AND r.issue_date<=?)',bounds).fetchone())
    # Per-day review/case generations allow unchanged bucket reuse. All reads
    # belong to the same source snapshot as directory and fact metadata.
    meta['reviewDays']=[dict(r) for r in db.execute('SELECT issue_date,COUNT(*) AS n,COALESCE(SUM(version),0) AS v FROM bi_risk_order_reviews WHERE issue_date>=? AND issue_date<=? GROUP BY issue_date ORDER BY issue_date',bounds).fetchall()]
    meta['caseDays']=[dict(r) for r in db.execute('SELECT r.issue_date,COUNT(*) AS n,COALESCE(SUM(c.version),0) AS v FROM bi_risk_order_reviews r JOIN bi_risk_followup_cases c ON c.id=r.case_id WHERE r.issue_date>=? AND r.issue_date<=? GROUP BY r.issue_date ORDER BY r.issue_date',bounds).fetchall()]
    dictionary=db.execute('SELECT det_code,det_cname,etl_run_id FROM bi_risk_reason_dict WHERE parent_code=? ORDER BY det_code LIMIT 5001',('PRODUCT_PROFIT_REASON_TYPE',)).fetchall()
    labels={r['det_code']:r['det_cname'] for r in dictionary}
    if len(dictionary)>5000 or len(labels)!=len(dictionary) or any(not r['det_cname'] for r in dictionary) or len({r['etl_run_id'] for r in dictionary})>1:raise AnalyticsError('ANALYTICS_DICTIONARY_INVALID')
    meta['dictionary']=[dict(r) for r in dictionary]
    return meta,labels,hashlib.sha256(encoded(meta).encode()).hexdigest()


def catalog_membership(db,meta,existing):
    """Hash ordered IDs only, not evidence JSON, to validate cross-day deduplication.

    A directory republish changes its run ID even when membership is identical.
    Reuse the prior hash only for exactly unchanged directory metadata.
    """
    try:old=json.loads(existing.get('body') or '{}') if existing else {}
    except (ValueError,TypeError):old={}
    if not isinstance(old,dict):old={}
    old_days={day(r['issue_date']):r for r in old.get('catalogDays',[])}
    hashes={}
    for covered in meta['catalogDays']:
        key=day(covered['issue_date'])
        prior=old.get('catalogMembership',{}).get(key)
        if prior and encoded(old_days.get(key))==encoded(covered):
            hashes[key]=prior;continue
        digest=hashlib.sha256();after=0;count=0
        while True:
            rows=db.execute('SELECT order_id FROM bi_risk_order_day WHERE issue_date=? AND order_id>? ORDER BY order_id LIMIT ?',(key,after,1000)).fetchall()
            ids=[int(r['order_id']) for r in rows]
            if not ids:break
            if ids!=sorted(set(ids)) or ids[0]<=after:raise AnalyticsError('ANALYTICS_CURSOR_NOT_MONOTONIC')
            for identifier in ids:digest.update((str(identifier)+'\n').encode('ascii'))
            count+=len(ids);after=ids[-1]
            if len(ids)<1000:break
        if count!=int(covered['row_count']):raise AnalyticsError('ANALYTICS_CATALOG_COUNT_MISMATCH')
        hashes[key]={'rows':count,'sha256':digest.hexdigest()}
    return hashes


def day_signatures(meta):
    result={day(r['issue_date']):{} for r in meta['catalogDays']}
    for field in ('catalogDays','preparedDays','metricDays','reviewDays','caseDays'):
        for row in meta.get(field,[]):
            key=day(row['issue_date'])
            if key in result:result[key][field]=row
    return {key:hashlib.sha256(encoded(value).encode()).hexdigest() for key,value in result.items()}


def reusable_days(existing,meta):
    if not existing or not existing.get('snapshot_id') or existing.get('schema_version')!=VERSION:return set()
    try:old=json.loads(existing.get('body') or '{}')
    except (ValueError,TypeError):return set()
    if not isinstance(old,dict) or old.get('reuseVersion')!=1 or not current_rules(existing.get('body')):return set()
    # A directory change anywhere can move an order's canonical latest day.
    # Rebuild all days in that case; never reuse a day with stale deduplication.
    if any(encoded(old.get(k))!=encoded(meta.get(k)) for k in ('catalogMembership','dictionary','windowStart','windowEnd')):return set()
    return {key for key,value in meta['daySignatures'].items() if old.get('daySignatures',{}).get(key)==value and key in old.get('dayOrderCounts',{}) and key in old.get('dayBucketCounts',{})}


def build_snapshot(store,end,existing=None,batch_size=250,max_buckets=50000):
    first=end-timedelta(days=30);cutoff=now();digest=engine_hash()
    with store.db(consistent_snapshot=True) as db:
        metadata_started=time.monotonic()
        meta,labels,signature=source_metadata(db,first,end,digest)
        print(encoded({'phase':'analytics_metadata','seconds':round(time.monotonic()-metadata_started,3)}),flush=True)
        if not meta['catalogDays']:raise AnalyticsError('ANALYTICS_CATALOG_NOT_READY')
        if existing and existing.get('snapshot_id') and existing.get('source_signature')==signature and existing.get('schema_version')==VERSION and current_rules(existing.get('body')):
            return None,meta,signature,cutoff
        membership_started=time.monotonic()
        meta['catalogMembership']=catalog_membership(db,meta,existing)
        print(encoded({'phase':'analytics_membership','seconds':round(time.monotonic()-membership_started,3),'days':len(meta['catalogMembership'])}),flush=True)
        meta['daySignatures']=day_signatures(meta)
        reusable=reusable_days(existing,meta)
        builder=Builder(end,labels,max_buckets)
        reused_days=[];read_seconds=0.0;aggregate_seconds=0.0
        meta['dayOrderCounts']={}
        projection=STATUS_PROJECTION+METRIC_FIELDS+',r.body AS review_body,c.disposition AS case_disposition'
        joins=JOINS+METRIC_JOIN+' LEFT JOIN bi_risk_order_reviews r ON r.order_id=o.order_id AND r.issue_date=o.issue_date LEFT JOIN bi_risk_followup_cases c ON c.id=r.case_id'
        # Use the date/order primary key first, then join only a bounded page.
        # The order/date secondary index proves absence of a newer partition.
        page_sql="""SELECT o.order_id FROM bi_risk_order_day o WHERE o.issue_date=? AND o.order_id>?
          AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date AND newer.issue_date<=?)
          ORDER BY o.order_id LIMIT ?"""
        for covered in meta['catalogDays']:
            business_day=day(covered['issue_date']);after=0
            if business_day in reusable:
                cached=db.execute('SELECT * FROM '+BUCKET+' WHERE end_date=? AND snapshot_id=? AND issue_date=?',(end.isoformat(),existing['snapshot_id'],business_day)).fetchall()
                totals=[r for r in cached if r['dimension']=='total']
                previous_meta=json.loads(existing['body'])
                expected=int(previous_meta['dayOrderCounts'][business_day])
                if len(cached)!=int(previous_meta['dayBucketCounts'][business_day]) or len(totals)>1 or (cached and len(totals)!=1) or sum(int(r['orders']) for r in totals)!=expected:raise AnalyticsError('ANALYTICS_REUSE_BUCKET_INVALID')
                meta['dayOrderCounts'][business_day]=expected
                for item in cached:
                    identity=(business_day,item['dimension'],item['group_key'])
                    if identity in builder.groups or len(builder.groups)>=max_buckets:raise AnalyticsError('ANALYTICS_BUCKET_LIMIT')
                    builder.groups[identity]={k:item[k] for k in ('issue_date','dimension','group_hash','group_key','group_label',*COUNTERS,'known_profit','known_loss')}
                builder.orders+=sum(int(r['orders']) for r in totals)
                reused_days.append(business_day)
                print(encoded({'phase':'analytics_day_reused','day':business_day,'buckets':len(cached),'processedOrders':builder.orders}),flush=True)
                continue
            day_start_orders=builder.orders
            while True:
                started=time.monotonic()
                identifiers=[int(row['order_id']) for row in db.execute(page_sql,(business_day,after,end.isoformat(),batch_size)).fetchall()]
                if not identifiers:break
                if identifiers!=sorted(set(identifiers)) or identifiers[0]<=after:raise AnalyticsError('ANALYTICS_CURSOR_NOT_MONOTONIC')
                marks=','.join('?' for _ in identifiers)
                rows=db.execute('SELECT '+projection+joins+' WHERE o.issue_date=? AND o.order_id IN ('+marks+') ORDER BY o.order_id',(business_day,*identifiers)).fetchall()
                if [int(row['order_id']) for row in rows]!=identifiers or any(day(row['issue_date'])!=business_day for row in rows):raise AnalyticsError('ANALYTICS_PAGE_INCOMPLETE')
                fetched=time.monotonic()
                for row in rows:builder.add(row,fact(row,expected_engine_hash=digest))
                aggregated=time.monotonic();read_seconds+=fetched-started;aggregate_seconds+=aggregated-fetched
                after=identifiers[-1]
                print(encoded({'phase':'analytics_page','day':business_day,'pageOrders':len(rows),'processedOrders':builder.orders,'seconds':round(time.monotonic()-started,3),'readSeconds':round(fetched-started,3),'aggregateSeconds':round(aggregated-fetched,3)}),flush=True)
                if len(identifiers)<batch_size:break
            meta['dayOrderCounts'][business_day]=builder.orders-day_start_orders
        meta['dayBucketCounts']={key:0 for key in meta['dayOrderCounts']}
        for key in builder.groups:meta['dayBucketCounts'][key[0]]+=1
        meta['bucketCount']=len(builder.groups)
        meta['reuseVersion']=1
        print(encoded({'phase':'analytics_build_complete','orders':builder.orders,'reusedDays':reused_days,'readSeconds':round(read_seconds,3),'aggregateSeconds':round(aggregate_seconds,3),'buckets':len(builder.groups)}),flush=True)
        return builder,meta,signature,cutoff


def publish(store,end,generation,builder,meta,signature,cutoff):
    started=time.monotonic()
    finished=now();snapshot_id=uuid.uuid4().hex if builder is not None else None
    try:
        with store.db() as db:
            if builder is not None:
                db.execute('DELETE FROM '+BUCKET+' WHERE end_date=?',(end.isoformat(),))
                columns=('end_date','issue_date','dimension','group_hash','group_key','group_label','snapshot_id',*COUNTERS,'known_profit','known_loss')
                sql='INSERT INTO '+BUCKET+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')'
                pending=[]
                for item in builder.groups.values():
                    values={'end_date':end.isoformat(),'snapshot_id':snapshot_id,**item}
                    pending.append(tuple(values[key] for key in columns))
                    if len(pending)>=500:
                        db.executemany(sql,pending);pending=[]
                if pending:db.executemany(sql,pending)
                db.execute('UPDATE '+MANIFEST+' SET snapshot_id=?,schema_version=?,source_signature=?,source_cutoff=?,generated_at=?,checked_at=?,processed_generation=?,last_error_code=NULL,order_count=?,body=?,retry_after=? WHERE end_date=?',
                           (snapshot_id,VERSION,signature,cutoff,finished,cutoff,generation,builder.orders,encoded(meta),finished,end.isoformat()))
            else:
                db.execute('UPDATE '+MANIFEST+' SET checked_at=?,processed_generation=?,last_error_code=NULL,retry_after=? WHERE end_date=?',
                           (cutoff,generation,finished,end.isoformat()))
    except StoreCommittedCleanupError:
        return {'endDate':end.isoformat(),'status':'published' if builder is not None else 'unchanged','orders':builder.orders if builder is not None else None,'warning':'ANALYTICS_PUBLISH_CLEANUP_FAILED'}
    print(encoded({'phase':'analytics_publication','endDate':end.isoformat(),'seconds':round(time.monotonic()-started,3),'rebuilt':builder is not None}),flush=True)
    return {'endDate':end.isoformat(),'status':'published' if builder is not None else 'unchanged','orders':builder.orders if builder is not None else None}


def run(config,end=None,max_end_days=32,batch_size=250,max_buckets=50000,store=None):
    store=store or RiskAutoStore(config);today=end or now().date();results=[];errors=[];already_running=False
    try:
        with store.db() as lock_db:
            locked=lock_db.execute('SELECT GET_LOCK(?,0) AS acquired',(LOCK,)).fetchone()
            if not locked or locked['acquired']!=1:
                already_running=True
            else:
                try:
                    request_snapshot(config,(today-timedelta(days=30)).isoformat(),today.isoformat(),store,force=True)
                    at=now();due=at-timedelta(minutes=INTERVAL_MINUTES)
                    candidates=lock_db.execute('SELECT * FROM '+MANIFEST+' WHERE retry_after<=? AND (request_generation>processed_generation OR checked_at IS NULL OR checked_at<=? OR schema_version<>?) ORDER BY CASE WHEN end_date=? THEN 0 WHEN request_generation>processed_generation THEN 1 ELSE 2 END,requested_at DESC,checked_at ASC LIMIT ?',
                                               (at,due,VERSION,today.isoformat(),max_end_days)).fetchall()
                    for candidate in candidates:
                        target=date.fromisoformat(day(candidate['end_date']))
                        phase='source'
                        try:
                            builder,meta,signature,cutoff=build_snapshot(store,target,candidate,batch_size,max_buckets)
                            phase='publish'
                            results.append(publish(store,target,candidate['request_generation'],builder,meta,signature,cutoff))
                        except Exception as error:
                            # Commit acknowledgement can be unknown; never claim rollback success.
                            code=safe_error(error)
                            try:
                                with store.db() as db:
                                    db.execute('UPDATE '+MANIFEST+' SET last_error_code=?,retry_after=? WHERE end_date=?',(code,now()+timedelta(minutes=INTERVAL_MINUTES),target.isoformat()))
                            except Exception:pass
                            results.append({'endDate':target.isoformat(),'status':'failed','errorCode':code,'publicationState':'not_attempted' if phase=='source' else 'not_confirmed'})
                finally:
                    try:lock_db.execute('SELECT RELEASE_LOCK(?)',(LOCK,))
                    except Exception:errors.append('ANALYTICS_LOCK_RELEASE_FAILED')
    except Exception:errors.append('ANALYTICS_JOB_DATABASE_FAILED')
    # Do not erase confirmed per-date publications if finalization fails.
    failed=bool(errors) or any(r['status']=='failed' or r.get('warning') for r in results)
    return {'status':'partial_failure' if failed and results else 'failed' if failed else 'already_running' if already_running else 'success','days':results,'errors':errors}


def check_schema(store):
    with store.db() as db:
        catalog_indexes=db.execute('SHOW INDEX FROM bi_risk_order_day').fetchall()
        grouped={}
        for item in sorted(catalog_indexes,key=lambda row:int(row['Seq_in_index'])):grouped.setdefault(item['Key_name'],[]).append(item['Column_name'])
        if grouped.get('PRIMARY')!=['issue_date','order_id'] or not any(value[:2]==['order_id','issue_date'] for value in grouped.values()):raise AnalyticsError('ANALYTICS_CATALOG_INDEX_MISSING')
        db.execute('SELECT end_date,snapshot_id,schema_version,source_signature,source_cutoff,generated_at,checked_at,requested_at,request_generation,processed_generation,retry_after,last_error_code,order_count,body FROM '+MANIFEST+' LIMIT 0').fetchall()
        db.execute('SELECT end_date,issue_date,dimension,group_hash,group_key,group_label,snapshot_id,'+','.join((*COUNTERS,'known_profit','known_loss'))+' FROM '+BUCKET+' LIMIT 0').fetchall()
        fields={r['Field']:str(r['Type']).lower() for r in db.execute('SHOW FULL COLUMNS FROM '+BUCKET).fetchall()}
        if fields.get('known_profit')!='decimal(38,4)' or fields.get('known_loss')!='decimal(38,4)':raise AnalyticsError('ANALYTICS_SCHEMA_PRECISION_MISMATCH')
        for table, expected in ((MANIFEST,('end_date',)),(BUCKET,('end_date','issue_date','dimension','group_hash'))):
            indexes=db.execute('SHOW INDEX FROM '+table).fetchall()
            primary=tuple(r['Column_name'] for r in sorted(indexes,key=lambda r:int(r['Seq_in_index'])) if r['Key_name']=='PRIMARY')
            if primary!=expected:raise AnalyticsError('ANALYTICS_SCHEMA_KEY_MISMATCH')
        for table in (MANIFEST,BUCKET,'bi_risk_order_day','bi_risk_sync_day','bi_risk_prepared_order','bi_risk_prepared_day','bi_risk_order_metric_day','bi_risk_order_metric_day_ready','bi_risk_order_reviews','bi_risk_followup_cases','bi_risk_reason_dict'):
            rows=db.execute('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?',(table,)).fetchall()
            if len(rows)!=1 or str(rows[0]['ENGINE']).upper()!='INNODB':raise AnalyticsError('ANALYTICS_SCHEMA_ENGINE_MISMATCH')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group();modes.add_argument('--preview',action='store_true');modes.add_argument('--check-schema',action='store_true')
    parser.add_argument('--end-date',type=date.fromisoformat)
    parser.add_argument('--max-end-days',type=int,default=32);parser.add_argument('--batch-size',type=int,default=250);parser.add_argument('--max-buckets',type=int,default=50000)
    args=parser.parse_args(argv)
    if not 1<=args.max_end_days<=128 or not 1<=args.batch_size<=5000 or not 1<=args.max_buckets<=1000000:parser.error('invalid bounded workload')
    if args.preview:
        print(encoded({'status':'offline_preview','refreshMinutes':INTERVAL_MINUTES,'tables':[MANIFEST,BUCKET],'source':'sibebid_only','sourceQueriesExecuted':False}));return 0
    try:
        from ..config import Config
        config={key:getattr(Config,key) for key in dir(Config) if key.isupper()}
        store=RiskAutoStore(config);check_schema(store)
        result={'status':'schema_ready'} if args.check_schema else run(config,args.end_date,args.max_end_days,args.batch_size,args.max_buckets,store)
    except Exception as error:result={'status':'failed','errorCode':safe_error(error),'days':[]}
    print(encoded(result));return 1 if result['status'] in ('failed','partial_failure') else 0

if __name__=='__main__':raise SystemExit(main())
