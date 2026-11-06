"""Fail-closed historical configuration matching, no order stop-loss log fallback."""
from copy import deepcopy
from bisect import bisect_right
from datetime import datetime
from decimal import Decimal
import hashlib
import html
import json
import re

from .risk_rule_priority import priority, priority_key, conditions, LABELS
from .risk_loss_threshold_config import LOSS_RULE_TYPE,ticket_threshold
from .risk_order_evidence import _rows

MATCH_FIELDS=('ota_code','ota_site_code','product_type','issue_supplier_code','issue_gds','issue_pcc',
              'booking_supplier_code','booking_gds','booking_pcc','airline','airline_except','cabin','cabin_except',
              'cabin_grade','cabin_grade_except','origin','origin_except','destination','destination_except',
              'issue_ticketing_date','travel_start_date','travel_end_date','travel_date_scope','travel_time_scope',
              'reverse_flag','is_transfer','business_earliest_days','business_latest_days','manual_flag','flight_number')
SAFE_FIELDS=('id','rule_type','rule_group_type','status','create_time','update_time','start_time','end_time','version','ext_json',*MATCH_FIELDS)
SUPPORTED=('cabin','cabin_grade','origin','destination','flight_number','ota_code','ota_site_code','product_type','issue_supplier_code','issue_gds','issue_pcc','airline','manual_flag')


def instant(value):
    if isinstance(value,datetime):return value if value.tzinfo is None else None
    try:
        parsed=datetime.fromisoformat(str(value).replace(' ','T')) if value else None
        return parsed if parsed is None or parsed.tzinfo is None else None
    except ValueError:return None


def canonical(raw):
    value=json.loads(raw,parse_float=Decimal) if isinstance(raw,str) else raw
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),
                      default=lambda item:{'$decimal':str(item)} if isinstance(item,Decimal) else str(item))


def restore(rule,logs,at):
    """Only JSON/cosmetic edits are reversible here; missing/other edits remain unknown."""
    state=deepcopy(rule);created=instant(rule.get('create_time'));updated=instant(rule.get('update_time'))
    if at is None or created is None or updated is None:return None,'配置或出票时间缺失'
    if created>at:return False,''
    if updated<=at:return state,''
    later=[row for row in logs if instant(row.get('operator_datetime')) and instant(row['operator_datetime'])>at]
    later.sort(key=lambda row:(instant(row['operator_datetime']),int(row['id'])),reverse=True)
    if not later:return None,'配置已改动但缺少出票后的完整变更历史'
    version=rule.get('version');last=instant(later[0].get('operator_datetime'))
    if version is None or last!=updated:return None,'配置更新时间与最后变更不一致'
    refs=[]
    for row in later:
        if row.get('version')!=version:return None,f'配置变更版本链断档：预期版本{version}，日志{row["id"]}版本{row.get("version")}，不能证明出票时配置'
        raw=html.unescape(str(row.get('operator_content') or ''))
        if len(raw)>20000:return None,'配置变更内容截断'
        content=re.sub(r'<(?:br\s*/?|/?b)>','',raw,flags=re.I)
        blocks=[block.strip() for block in re.findall(r'【([^【】]*)】',content)]
        changes=[block for block in blocks if '由 ' in block or '由\'' in block or '修改为' in block]
        if not changes:return None,'配置变更不是可还原的字段差异'
        for block in changes:
            if block.startswith(('规则名称','备注')):continue
            if not block.startswith('扩展字段'):return None,'历史匹配条件或状态变化尚不能可靠还原'
            match=re.search(r"由\s*'(\{.*\})'\s*修改为\s*'(\{.*\})'",block,re.S)
            if not match:return None,'配置扩展JSON变更不可解析'
            try:
                if canonical(state.get('ext_json'))!=canonical(match.group(2)):return None,'配置新旧JSON链不连续'
                # A filter change also changes rule scope. Do not mistake a threshold-only rollback for full scope recovery.
                before=json.loads(match.group(1));after=json.loads(match.group(2))
                if before.get('extFilter')!=after.get('extFilter'):return None,'历史扩展匹配条件发生变化'
                state['ext_json']=match.group(1)
            except (ValueError,TypeError,AttributeError):return None,'配置历史JSON无效'
        refs.append(str(row['id']));version=int(version)-1
    previous=[row for row in logs if instant(row.get('operator_datetime')) and instant(row['operator_datetime'])<=at and row.get('version')==version]
    if previous:state['update_time']=max(instant(row['operator_datetime']) for row in previous)
    elif version==1:state['update_time']=created
    else:return None,'缺少出票时版本基线'
    state['version']=version;state['historyReferences']=refs
    return state,''




LEGACY_FIELDS={'OTA平台':'ota_code','OTA站点':'ota_site_code','产品类型':'product_type','航司':'airline',
 '除外航司':'airline_except','出票供应商':'issue_supplier_code','出票GDS':'issue_gds','出票PCC':'issue_pcc',
 '出发地':'origin','除外出发地':'origin_except','目的地':'destination','除外目的地':'destination_except',
 '舱位':'cabin','除外舱位':'cabin_except','舱等':'cabin_grade','除外舱等':'cabin_grade_except','航班号':'flight_number'}


def restore_legacy(rule,logs,at):
    """Validate the entire legacy ledger, then replay its explicit before/after values."""
    created,updated=instant(rule.get('create_time')),instant(rule.get('update_time'));version=rule.get('version')
    if at is None or created is None or updated is None or created>at or updated<=at:return None,'历史还原时点不适用'
    if type(version) is not int or version<1 or len(logs)!=version+1:return None,'历史创建/修改记录数量与配置版本不一致'
    dates=[instant(row.get('operator_datetime')) for row in logs]
    if any(t is None for t in dates) or len(set(dates))!=len(dates) or min(dates)!=created or max(dates)!=updated:return None,'历史时间链缺失或冲突'
    if len({str(row.get('id')) for row in logs})!=len(logs):return None,'历史日志重复'
    if any(str(row.get('business_obj_id'))!=str(rule['id']) or row.get('version')!=0 for row in logs):return None,'历史对象或版本格式不一致'
    ordered=sorted(logs,key=lambda row:instant(row['operator_datetime']))
    if str(ordered[0].get('operator_content') or '').strip()!='新增规则。':return None,'历史缺少创建基线'
    state=deepcopy(rule);as_of=None;refs=[]
    for row in reversed(ordered[1:]):
        when=instant(row['operator_datetime'])
        if when<=at and as_of is None:as_of=deepcopy(state)
        raw=html.unescape(str(row.get('operator_content') or ''))
        if len(raw)>20000:return None,'历史内容超过完整性上限'
        content=re.sub(r'<(?:br\s*/?|/?b)>','',raw,flags=re.I)
        action=re.fullmatch(r'修改规则状态为：(挂起|启用)。',content)
        if action:
            expected={'挂起':'2','启用':'1'}[action.group(1)]
            if state.get('status') is not None and str(state['status'])!=expected:return None,'历史状态与当前值冲突'
            state['status']=None
        else:
            blocks=re.findall(r'【([^【】]*)】',content)
            if len(blocks)<2 or blocks[0]!='修改出票规则信息' or re.sub(r'【[^【】]*】','',content).strip():return None,'历史动作格式未支持'
            for block in reversed(blocks[1:]):
                change=re.fullmatch(r"(.+?)\s+由\s*'(.*)'\s*修改为\s*'(.*)'",block,re.S)
                if not change:return None,'历史字段差异不可解析'
                label,before,after=change.groups()
                if label in ('规则名称','备注'):continue
                if label=='扩展字段':
                    try:
                        if canonical(state.get('ext_json'))!=canonical(after):return None,'历史扩展JSON新旧链不连续'
                        if not isinstance(json.loads(before),dict):return None,'历史扩展JSON无效'
                    except (ValueError,TypeError):return None,'历史扩展JSON无效'
                    state['ext_json']=before
                elif label in LEGACY_FIELDS:
                    key=LEGACY_FIELDS[label]
                    if tokens(state.get(key))!=tokens(after):return None,'历史字段新旧值不连续：'+key
                    state[key]=before
                elif label in ('生效时间','失效时间'):
                    key='start_time' if label=='生效时间' else 'end_time'
                    current=instant(state.get(key));old=instant(before);new=instant(after)
                    if current is None or old is None or new is None or current.date()!=new.date():return None,'历史有效期新旧值不连续'
                    if label=='生效时间' and (current.hour,current.minute,current.second)!=(0,0,0):return None,'历史生效时间边界异常'
                    if label=='失效时间' and (current.hour,current.minute,current.second)!=(23,59,59):return None,'历史失效时间边界异常'
                    state[key]=old.replace(hour=current.hour,minute=current.minute,second=current.second,microsecond=current.microsecond)
                else:return None,'历史字段未支持：'+label
        if when>at:refs.append(str(row['id']))
    if as_of is None:as_of=deepcopy(state)
    as_of.update(version=version-len(refs),update_time=max(t for t in dates if t<=at),historyReferences=refs,historyProof='complete_legacy_edit_ledger')
    return as_of,''


def historical_exclusion(rule,logs,at,facts):
    """Compatibility entry: exclusion uses the same validated decoder as restoration."""
    state,error=restore_legacy(rule,logs,at)
    if state is None:return None
    for key in ('ota_code','airline'):
        if tokens(state.get(key)) and tokens(facts.get(key)) and not tokens(state[key])&tokens(facts[key]):
            return {'ruleId':str(rule['id']),'field':key,'historyReferences':state['historyReferences'],
                    'basis':'complete_legacy_edit_ledger_scope_exclusion'}
    return None


def tokens(value):
    return {item.strip().casefold() for item in re.split(r'[,;/|]',str(value)) if item.strip()} if value is not None and str(value).strip() else set()


EXCLUSIONS={'airline_except':'airline','cabin_except':'cabin','cabin_grade_except':'cabin_grade',
            'origin_except':'origin','destination_except':'destination'}
ISSUE_WAYS={'ALL_SYSTEM':'全自动','SYSTEM':'半自动','MANUAL':'手工'}


def matches(rule,facts):
    unknown=[]
    for key in SUPPORTED:
        wanted=rule.get(key)
        if wanted is None or not str(wanted).strip():continue
        actual=facts.get(key)
        if actual is None or not str(actual).strip():unknown.append(key);continue
        if key=='manual_flag':
            if str(wanted)!=str(actual):return False,[]
        elif not tokens(wanted)&tokens(actual):return False,[]
    for key,source in EXCLUSIONS.items():
        if not tokens(rule.get(key)):continue
        actual=facts.get(source)
        if not tokens(actual):unknown.append(source);continue
        if tokens(rule[key])&tokens(actual):return False,[]
    # These flags affect rank but the loss-rule branch does not filter by them.
    unknown.extend(key for key in MATCH_FIELDS if key not in (*SUPPORTED,*EXCLUSIONS,'reverse_flag','is_transfer') and rule.get(key) is not None and str(rule[key]).strip())
    try:
        ext=json.loads(rule.get('ext_json') or '{}')
        filters=ext.get('extFilter') or {}
        for key,value in filters.items():
            if value is None or not str(value).strip():continue
            if key=='paramOne' and rule.get('rule_group_type')=='RB01003':
                if not facts.get('issue_way'):unknown.append('issue_way')
                elif facts['issue_way'] not in ISSUE_WAYS:unknown.append('issue_way非法编码')
                elif not tokens(value).issubset({key.casefold() for key in ISSUE_WAYS}):unknown.append('extFilter.paramOne非法出票方式')
                else:
                    configured=tokens(value)
                    # User-confirmed loss-rule semantics: manual group includes semi-automatic.
                    if 'manual' in configured:configured.add('system')
                    if not configured&tokens(facts['issue_way']):return False,[]
            else:unknown.append('extFilter.'+key)
    except (ValueError,TypeError,AttributeError):unknown.append('ext_json')
    return (None if unknown else True),unknown


def explain_conditions(rule,facts):
    rows=[]
    try:configured=conditions(rule)
    except (ValueError,TypeError,AttributeError):
        return [{'field':'ext_json','label':'扩展配置','value':'不可解析','actual':None,'outcome':'unknown','missing':['ext_json']}]
    for condition in configured:
        key=condition['field']
        if key.startswith('extFilter.'):
            partial={'rule_group_type':rule.get('rule_group_type'),'ext_json':json.dumps({'extFilter':{key.split('.',1)[1]:json.loads(rule.get('ext_json') or '{}')['extFilter'][key.split('.',1)[1]]}})}
            source='issue_way' if key=='extFilter.paramOne' else key
        else:
            partial={key:rule.get(key)}
            source=EXCLUSIONS.get(key,key)
        matched,missing=matches(partial,facts)
        rows.append({**condition,'actual':str(facts[source]) if facts.get(source) is not None else None,
                     'outcome':'rank_only' if key in ('reverse_flag','is_transfer') else 'matched' if matched is True else 'excluded' if matched is False else 'unknown',
                     'missing':missing})
    return rows


class HistoricalThresholds:
    def __init__(self,cursor):
        # Include disabled/deleted historical rules, and rules previously logged as a loss-rule type.
        cursor.execute("SELECT "+','.join('r.'+field for field in SAFE_FIELDS)+""" FROM base_issue_match_rule r WHERE r.rule_business_type=%s
          AND (r.rule_type=%s OR EXISTS (SELECT 1 FROM base_issue_match_log l
            WHERE l.business_obj=%s AND l.business_obj_id=r.id AND l.operator_type=%s))
          ORDER BY r.id LIMIT 1001""",('RB01',LOSS_RULE_TYPE,'RB01',LOSS_RULE_TYPE))
        rows=_rows(cursor)
        self.problem=None;self.rules=[];self.logs={}
        if len(rows)>1000:self.problem='历史配置候选超过1000条，不能用截断集合判定';return
        self.rules=[{key:row.get(key) for key in SAFE_FIELDS} for row in rows]
        if not rows:return
        ids=[row['id'] for row in rows]
        cursor.execute("SELECT id,business_obj_id,operator_datetime,version,LEFT(operator_content,20001) AS operator_content FROM base_issue_match_log WHERE business_obj=%s AND business_obj_id IN ("+','.join(['%s']*len(ids))+") ORDER BY operator_datetime DESC,id DESC LIMIT 20001",('RB01',*ids))
        logs=_rows(cursor)
        if len(logs)>20000:self.problem='配置变更超过历史取证上限，不能假定历史完整';return
        for row in logs:self.logs.setdefault(str(row['business_obj_id']),[]).append(row)

    def _restore_cached(self,rule,at):
        # State depends on the historical change interval, not each ticket's distinct timestamp.
        if not hasattr(self,'_restore_cache'):self._restore_cache={};self._boundaries={}
        key=str(rule['id'])
        if key not in self._boundaries:
            self._boundaries[key]=sorted({t for t in [instant(rule.get('create_time')),instant(rule.get('update_time')),*[instant(row.get('operator_datetime')) for row in self.logs.get(key,[])]] if t is not None})
        cache_key=(key,bisect_right(self._boundaries[key],at))
        if cache_key not in self._restore_cache:
            state,error=restore(rule,self.logs.get(key,[]),at);legacy=None;legacy_error=''
            if state is None:legacy,legacy_error=restore_legacy(rule,self.logs.get(key,[]),at)
            self._restore_cache[cache_key]=(state,error,legacy,legacy_error)
        return self._restore_cache[cache_key]

    def resolve(self,issue,order):
        if self.problem:return {'status':'insufficient','reason':self.problem}
        at=instant(issue.get('issue_ticket_time'))
        if at is None:return {'status':'insufficient','reason':'缺少有效出票时间，无法还原配置'}
        pcc=issue.get('issue_office_no') if issue.get('issue_office_no')==issue.get('issue_ticketing_office_no') else None
        facts={'ota_code':order.get('ota_code'),'ota_site_code':order.get('ota_site_code'),'product_type':order.get('product_type'),
               'manual_flag':order.get('manual_flag'),'issue_supplier_code':issue.get('supplier_code'),
               'issue_gds':issue.get('issue_gds_channel'),'issue_pcc':pcc,'airline':issue.get('marketing_airline'),'issue_way':order.get('issue_way')}
        facts.update(issue.get('matchingFacts') or {})
        candidates=[];unknown=[];diagnostics=[];excluded=[];scope_exclusions=[];trace=[]
        context={'matchingFacts':{key:str(value) for key,value in facts.items() if value is not None},
                 'matchingFactProblems':issue.get('matchingFactProblems') or {},'candidateTrace':trace}
        def unresolved(rule,stage,reason,fields=None):
            unknown.append(reason)
            diagnostics.append({'ruleId':str(rule['id']),'stage':stage,'reason':reason,'fields':fields or []})
            trace.append({'ruleId':str(rule['id']),'outcome':'unknown','stage':stage,'reason':reason})
        for rule in self.rules:
            state,error,legacy,legacy_error=self._restore_cached(rule,at)
            if state is False:
                trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'出票时尚未创建'})
                continue
            if state is None:
                if legacy is not None:
                    proof=next(({'ruleId':str(rule['id']),'field':key,'historyReferences':legacy['historyReferences'],'basis':legacy['historyProof']} for key in ('ota_code','airline') if tokens(legacy.get(key)) and tokens(facts.get(key)) and not tokens(legacy[key])&tokens(facts[key])),None)
                    if proof:
                        scope_exclusions.append(proof)
                        trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'完整历史链证明平台或航司不适用','historyReferences':proof['historyReferences']})
                        continue
                    if legacy.get('status') is not None:state=legacy
                    else:
                        error='历史配置状态无法还原'
                        legacy_error='历史状态动作没有修改前值，不能证明出票时启用状态'
                if state is None:
                    unresolved(rule,'history',error+'；'+legacy_error)
                    continue
            if state.get('rule_type')!=LOSS_RULE_TYPE:
                trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'出票时不是亏损阈值规则'})
                continue
            start,end=instant(state.get('start_time')),instant(state.get('end_time'))
            if start and end and not start<=at<=end:
                trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'出票时不在配置有效期'})
                continue
            if str(state.get('status'))!='1':
                trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'出票时状态非启用'})
                continue
            match,missing=matches(state,facts)
            if match is False:
                excluded.append(str(rule['id']))
                trace.append({'ruleId':str(rule['id']),'outcome':'excluded','reason':'订单条件不符合','conditions':explain_conditions(state,facts)})
                continue
            if match is None:
                detail='配置条件未可靠绑定：'+','.join(missing)
                sources=issue.get('matchingFactProblems') or {}
                explanations=sorted({sources.get(EXCLUSIONS.get(key,key), '') for key in missing} - {''})
                if explanations:detail+='；'+'；'.join(explanations)
                unresolved(rule,'conditions',detail,missing)
                continue
            try:
                ranked=priority(state)
                key=priority_key(state)
            except (ValueError,TypeError,AttributeError):
                unresolved(rule,'priority','配置权重或排序字段无法可靠解析')
                continue
            candidates.append((*key,state))
            trace.append({'ruleId':str(rule['id']),'outcome':'matched',**ranked,
                          'updateTime':str(state['update_time']),'configurationVersion':state.get('version'),
                          'conditions':explain_conditions(state,facts)})
        if unknown:return {**context,'status':'insufficient','reason':f'规则{diagnostics[0]["ruleId"]}：{unknown[0]}（共{len(unknown)}条未知候选，保留阻断）',
                           'unresolvedCandidates':len(unknown),'diagnostics':diagnostics,'matchedCandidateIds':[str(row[3]['id']) for row in candidates],
                           'issueWay':order.get('issue_way'),'issueWayLabel':ISSUE_WAYS.get(order.get('issue_way'),'未知编码')}
        if not candidates:return {**context,'status':'insufficient','reason':'没有可靠匹配到出票时亏损阈值配置；出票方式：'+ISSUE_WAYS.get(order.get('issue_way'),'未知')+'（'+str(order.get('issue_way') or '缺失')+'），请核对兜底是否覆盖该方式',
                                  'excludedCandidateIds':excluded,'issueWay':order.get('issue_way'),'issueWayLabel':ISSUE_WAYS.get(order.get('issue_way'),'未知编码')}
        state=max(candidates,key=lambda item:item[:3])[3]
        amount=ticket_threshold(state.get('ext_json'),issue.get('segmentCount'))
        if amount['status']!='ready':return {**context,**amount,'ruleId':str(state['id']),**priority(state)}
        ordered=sorted(candidates,key=lambda item:item[:3],reverse=True)
        context['matchedCandidateIds']=[str(row[3]['id']) for row in ordered]
        for item in trace:
            if item['outcome']=='matched':item['outcome']='selected' if item['ruleId']==str(state['id']) else 'lower_priority'
        snapshot=json.loads(json.dumps({key:state.get(key) for key in SAFE_FIELDS},default=str))
        snapshot['version']=state.get('version')
        digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
        return {**context,**amount,**priority(state),'ruleId':str(state['id']),'configurationVersion':state.get('version'),'asOf':str(issue['issue_ticket_time']),
                'configurationHash':digest,'configurationSnapshot':snapshot,'historyReferences':state.get('historyReferences',[]),
                'source':'base_issue_match_rule.ext_json','basis':'issue_time_configuration','historyProof':state.get('historyProof','versioned_log_chain'),'excludedHistoricalCandidates':scope_exclusions}
