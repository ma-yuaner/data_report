"""Bounded set-based ERP extraction, replaying the canonical reader without extra SQL."""
from collections import defaultdict
from copy import deepcopy
import time
from .risk_order_evidence import _rows
from .risk_child_loss import ANCILLARY_REASON, CHILD_REASON, ORDER_FIELDS, PROFIT_REASONS
from .risk_ancillary_loss import ANCILLARY_SQL, MAX_ANCILLARY_ROWS
from .risk_historical_threshold import HistoricalThresholds

ISSUE_FIELDS='id,order_id,passenger_id,issue_profit,sale_commission_amount,sale_currency,issue_ticket_time,supplier_code,marketing_airline,issue_gds_channel,issue_office_no,issue_ticketing_office_no'
SEGMENT_FIELDS='i.issue_id,i.segment_id,s.id,s.order_id,s.airlift_flag,s.cabin,s.cabin_grade,s.flight_number,s.dep_airport,s.arr_airport,s.journey_sequence,s.segment_sequence'


class BatchEvidence:
    def __init__(self,cursor,identifiers,history=None,check_plans=False):
        self.cursor=cursor;self.query_count=0;self.started=time.monotonic();self.check_plans=check_plans
        self.orders={};self.issues=defaultdict(list);self.links=defaultdict(list);self.ages=defaultdict(list);self.airports=defaultdict(list)
        self._orders(identifiers)
        self.history = history
        if self.history is None and any(row.get('profit_reason_type') not in PROFIT_REASONS for row in self.orders.values()):
            self.history = HistoricalThresholds(cursor)
        self.ancillary_purchases = defaultdict(list)
        ancillary_numbers = sorted({row['ota_order_no'] for row in self.orders.values()
                                    if row.get('profit_reason_type') == ANCILLARY_REASON
                                    and row.get('ota_order_no')})
        for chunk in self.chunks(ancillary_numbers):
            marks = ','.join(['%s'] * len(chunk))
            rows = self.query(ANCILLARY_SQL.format(marks=marks, limit=10001), tuple(chunk))
            if len(rows) > 10000:
                raise ValueError('BATCH_ANCILLARY_LIMIT')
            for row in rows:
                self.ancillary_purchases[row['ota_order_no']].append(row)
        child_nodes={key for key,row in self.orders.items() if row.get('profit_reason_type')==CHILD_REASON}
        seen=set()
        for _ in range(100):
            groups=defaultdict(set)
            for row in self.orders.values():
                if str(row['id']) in child_nodes and row.get('ota_code')=='CTRIP':
                    for key in ('ota_order_no','relation_ota_order_no'):
                        code=row.get(key);identity=(row.get('ota_site_code'),code)
                        if code and identity not in seen:groups[row.get('ota_site_code')].add(code)
            if not groups:break
            for site,codes in groups.items():
                values=sorted(codes);seen.update((site,code) for code in codes)
                for chunk in self.chunks(values):
                    marks=','.join(['%s']*len(chunk))
                    rows=self.query('SELECT '+ORDER_FIELDS+' FROM order_info WHERE ota_code=%s AND ota_site_code <=> %s AND (ota_order_no IN ('+marks+') OR relation_ota_order_no IN ('+marks+')) ORDER BY id LIMIT 10001',('CTRIP',site,*chunk,*chunk))
                    if len(rows)>10000:raise ValueError('BATCH_RELATED_ORDER_LIMIT')
                    child_nodes.update(str(row['id']) for row in rows)
                    self.orders.update((str(row['id']),row) for row in rows)
            if len(self.orders)>10000:raise ValueError('BATCH_RELATED_ORDER_LIMIT')
        else:raise ValueError('BATCH_RELATION_DEPTH_LIMIT')
        threshold_orders = {key for key, row in self.orders.items()
                            if key in child_nodes or row.get('profit_reason_type') not in PROFIT_REASONS}
        ticket_count=0
        for chunk in self.chunks(list(self.orders)):
            marks=','.join(['%s']*len(chunk))
            rows=self.query('SELECT '+ISSUE_FIELDS+' FROM order_info_issue WHERE order_id IN ('+marks+') ORDER BY id LIMIT 100001',tuple(chunk))
            ticket_count+=len(rows)
            if len(rows)>100000 or ticket_count>100000:raise ValueError('BATCH_TICKET_LIMIT')
            for row in rows:self.issues[str(row['order_id'])].append(row)
            if not threshold_orders.intersection(chunk):
                continue
            ages=self.query('SELECT i.id,i.order_id,p.age_type FROM order_info_issue i LEFT JOIN order_info_passenger p ON p.id=i.passenger_id AND p.order_id=i.order_id WHERE i.order_id IN ('+marks+') ORDER BY i.id LIMIT 100001',tuple(chunk))
            if len(ages)>100000:raise ValueError('BATCH_AGE_LIMIT')
            for row in ages:self.ages[str(row['order_id'])].append(row)
        ids=[str(row['id']) for key, group in self.issues.items() if key in threshold_orders for row in group]
        if len(ids)>100000:raise ValueError('BATCH_TICKET_LIMIT')
        link_count=0
        for chunk in self.chunks(ids):
            marks=','.join(['%s']*len(chunk))
            rows=self.query('SELECT '+SEGMENT_FIELDS+' FROM order_info_issue_segment i LEFT JOIN order_info_segment s ON s.id=i.segment_id WHERE i.issue_id IN ('+marks+') ORDER BY i.issue_id,s.id LIMIT 100001',tuple(chunk))
            link_count+=len(rows)
            if len(rows)>100000 or link_count>500000:raise ValueError('BATCH_SEGMENT_LIMIT')
            for row in rows:self.links[str(row['issue_id'])].append(row)
        airports=sorted({self.orders[key].get(k) for key in threshold_orders
                         for k in ('dep_city','arr_city') if self.orders[key].get(k)})
        for chunk in self.chunks(airports):
            marks=','.join(['%s']*len(chunk))
            rows=self.query('SELECT airport_code,city_code,country_code,zone_code,area_code,update_time FROM base_airport WHERE airport_code IN ('+marks+') AND status=1 LIMIT 2001',tuple(chunk))
            if len(rows)>2000:raise ValueError('BATCH_AIRPORT_LIMIT')
            for row in rows:self.airports[row['airport_code']].append(row)

    @staticmethod
    def chunks(values):
        for offset in range(0,len(values),500):yield values[offset:offset+500]

    def query(self,sql,args):
        if self.check_plans:
            self.cursor.execute('EXPLAIN '+sql,args)
            plans=_rows(self.cursor)
            if not plans or any(str(r.get('type','')).upper() in ('ALL','INDEX') for r in plans):raise ValueError('BATCH_SOURCE_PLAN_UNSAFE')
        self.query_count+=1;self.cursor.execute(sql,args);return _rows(self.cursor)

    def _orders(self,identifiers):
        for chunk in self.chunks(list(identifiers)):
            marks=','.join(['%s']*len(chunk))
            rows=self.query('SELECT '+ORDER_FIELDS+' FROM order_info WHERE id IN ('+marks+')',tuple(chunk))
            if len(rows)!=len(chunk):raise ValueError('BATCH_ROOT_ORDER_MISSING')
            self.orders.update((str(row['id']),row) for row in rows)

    def replay(self):return ReplayCursor(self)


class ReplayCursor:
    description=[]
    def __init__(self,batch):self.batch=batch;self.result=[];self.calls=0
    def execute(self,sql,params=()):
        self.calls+=1;b=self.batch
        if 'FROM order_info WHERE id=%s' in sql:
            row=b.orders.get(str(params[0]));self.result=[row] if row else []
        elif 'FROM order_info WHERE ota_code=%s' in sql:
            codes=set(params[2:]);self.result=sorted([r for r in b.orders.values() if r.get('ota_code')==params[0] and r.get('ota_site_code')==params[1] and (r.get('ota_order_no') in codes or r.get('relation_ota_order_no') in codes)],key=lambda r:int(r['id']))[:101]
        elif 'LEFT JOIN order_info_passenger' in sql:
            self.result=b.ages.get(str(params[0]),[])[:201]
        elif 'FROM order_auxiliary a' in sql:
            self.result = b.ancillary_purchases.get(params[0], [])[:MAX_ANCILLARY_ROWS + 1]
        elif 'FROM order_info_issue WHERE order_id=%s' in sql:
            self.result=b.issues.get(str(params[0]),[])[:201]
        elif 'AS link_count' in sql:
            links=b.links.get(str(params[1]),[])
            matched={str(r['id']) for r in links if r.get('id') is not None and str(r.get('order_id'))==str(params[0]) and str(r.get('airlift_flag')) in ('0','1')}
            air={str(r['id']) for r in links if r.get('id') is not None and str(r.get('order_id'))==str(params[0]) and str(r.get('airlift_flag'))=='1'}
            self.result=[{'link_count':len(links),'matched_segment_count':len(matched),'segment_count':len(air)}]
        elif 'FROM order_info_issue_segment i JOIN order_info_segment s' in sql:
            self.result=[r for r in b.links.get(str(params[0]),[]) if str(r.get('order_id'))==str(params[1]) and str(r.get('airlift_flag'))=='1'][:201]
        elif 'FROM base_airport WHERE airport_code=%s' in sql:
            self.result=b.airports.get(params[0],[])[:2]
        else:raise ValueError('UNSUPPORTED_EVIDENCE_REPLAY_QUERY')
    def fetchall(self):return deepcopy(self.result)


def cause_code(result):
    if result.get('status')!='insufficient':return None
    reasons=[r.get('explanation','') for r in result.get('tickets',[])]
    text=' '.join([result.get('summary',''),*result.get('missing',[]),*reasons])
    if '历史状态动作没有修改前值' in text:return 'HISTORY_STATUS_BASELINE_MISSING'
    if '未支持' in text or '不可解析' in text:return 'PARSER_REVIEW_REQUIRED'
    if '数量与配置版本不一致' in text or '时间链缺失' in text:return 'HISTORY_LEDGER_INCOMPLETE'
    if any(word in text for word in ('历史','版本链','变更')):return 'HISTORY_RECONSTRUCTION'
    if '配置条件未可靠绑定' in text:return 'MATCH_FACTS_INCOMPLETE'
    if '没有可靠匹配到' in text:return 'NO_APPLICABLE_RULE'
    if '配置权重或排序字段' in text:return 'PRIORITY_EVIDENCE'
    missing=' '.join(result.get('missing',[]))
    if any(word in text for word in ('关联','范围不完整','截断')):return 'SCOPE_INCOMPLETE'
    if '年龄' in missing or '年龄类型' in text:return 'PASSENGER_EVIDENCE'
    if '出票利润' in missing or '增值利润' in missing or '佣金' in missing or '币种' in text:return 'MONEY_EVIDENCE'
    if '止损值缺失或无效' in missing:return 'THRESHOLD_EVIDENCE'
    if any(r.get('configuration',{}).get('status')!='ready' for r in result.get('tickets',[])):return 'THRESHOLD_EVIDENCE'
    return 'UNCLASSIFIED_EVIDENCE'
