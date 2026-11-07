"""Immutable order verification evidence and append-only current-rule observations."""
import hashlib
import json
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

from .risk_auto_store import RiskAutoStore, StoreConflict
from .risk_followup import day, encoded, now
from .risk_order_evidence import order_id
from .risk_prepared_facts import one
from .risk_verification_flow import FlowError, _owner
from .risk_issue_rule_configs import RiskIssueRuleConfigs
from .risk_loss_threshold_config import LOSS_RULE_TYPE, ticket_threshold


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', value):
        raise FlowError('操作标识无效')
    return value


def timestamp(value):
    dt=datetime.fromisoformat(str(value))
    if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    return dt.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='microseconds')


def value_changed(before, after):
    if before is None or after is None:return None
    try:
        a,b=Decimal(str(before)),Decimal(str(after))
        return a!=b if a.is_finite() and b.is_finite() else None
    except (InvalidOperation,ValueError):return None


class RiskConfigEvidence:
    def __init__(self, config, store=None, reader=None):
        self.config=config
        self.store=store or RiskAutoStore(config)
        self.reader=reader or RiskIssueRuleConfigs(config)

    @staticmethod
    def _load(db, order, issue_date, lock=False):
        row=db.execute('SELECT id,body FROM bi_risk_config_evidence WHERE order_id=? AND issue_date=?'+(' FOR UPDATE' if lock else ''),(order,issue_date)).fetchone()
        body=json.loads(row['body']) if row else None
        if body is not None and body.get('schemaVersion')!=1:
            raise FlowError('原配置证据结构版本不受支持，未覆盖历史记录',503)
        return body

    def get(self, order, issue_date):
        order,issue_date=str(order_id(order)),day(issue_date)
        with self.store.db() as db:
            saved=self._load(db,order,issue_date)
            if not saved:return None
            rows=db.execute('SELECT body FROM bi_risk_config_observations WHERE evidence_id=? ORDER BY seq DESC LIMIT 501',(saved['id'],)).fetchall()
        observations=[json.loads(row['body']) for row in rows[:500]]
        return {**saved,'latest':observations[0] if observations else None,'observations':observations,'historyTruncated':len(rows)>500}

    def history(self, order, issue_date):
        """Read ETL-published revisions; viewing never saves or recomputes evidence."""
        order, issue_date = str(order_id(order)), day(issue_date)
        with self.store.db() as db:
            rows = db.execute("""SELECT order_id,issue_date,reason_code,rule_version,engine_hash,evidence_hash,
                result_json,source_updated_at,etl_run_id,prepared_at,valid_from,valid_to,last_checked_at
                FROM bi_risk_prepared_order_history WHERE order_id=? AND issue_date=?
                ORDER BY valid_from DESC,etl_run_id DESC LIMIT 51""", (order, issue_date)).fetchall()
        items = []
        for row in rows[:50]:
            try:
                result = json.loads(row['result_json'])
            except (ValueError, TypeError):
                raise FlowError('历史核查内容损坏，请联系管理员核对清洗批次', 503) from None
            if not isinstance(result, dict) or result.get('status') not in ('supported', 'problem', 'insufficient', 'failed'):
                raise FlowError('历史核查内容无效，请联系管理员核对清洗批次', 503)
            identity = [issue_date, order, row['rule_version'], row['engine_hash'], row['evidence_hash']]
            result.update(id=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32],
                          historyRunId=str(row['etl_run_id']),
                          orderId=order, issueDate=issue_date, reasonCode=row['reason_code'], checkedAt=str(row['prepared_at']),
                          sourceUpdatedAt=str(row['source_updated_at']) if row['source_updated_at'] is not None else None,
                          sourceMode='prepared_etl', isCurrent=False)
            items.append({'versionKey': str(row['etl_run_id']), 'result': result, 'validFrom': str(row['valid_from']),
                          'validTo': str(row['valid_to']) if row['valid_to'] is not None else None,
                          'lastCheckedAt': str(row['last_checked_at'])})
        return {'items': items, 'truncated': len(rows) > 50}

    def save(self, actor, order, payload):
        actor,order,issue_date=_owner(actor),str(order_id(order)),day(payload.get('issueDate'))
        try:
            with self.store.db() as db:
                existing=self._load(db,order,issue_date,True)
                if existing:return {**existing,'alreadySaved':True}
                current=one(lambda sql,args:db.execute(sql,args).fetchall(),order,issue_date,True)
                if not current or current['id']!=payload.get('resultId'):
                    raise FlowError('清洗证据已变化或未就绪，请刷新后保存当前核对证据',409)
                body={'schemaVersion':1,'id':uuid.uuid4().hex,'orderId':order,'issueDate':issue_date,'savedAt':now(),'savedBy':actor,
                      'original':current,'originalHash':digest(current),
                      'notice':'原单票止损及核对结论已固定；后续观察仅提醒，不重算、不覆盖。'}
                if len(encoded(body).encode('utf-8'))>4*1024*1024:
                    raise FlowError('配置证据超过保存上限，未截断或保存部分记录',413)
                db.execute('INSERT INTO bi_risk_config_evidence (id,order_id,issue_date,original_result_id,body) VALUES(?,?,?,?,?)',
                           (body['id'],order,issue_date,current['id'],encoded(body)))
                return body
        except StoreConflict:
            saved=self.get(order,issue_date)
            if saved:return {**saved,'alreadySaved':True}
            raise FlowError('保存发生冲突，请刷新核对',409) from None

    @staticmethod
    def compare(original, source, previous=None):
        observed=timestamp(source['observedAt'])
        rules={str(row['id']):row for row in source['items']}
        previous_tickets={row['ticketId']:row for row in (previous or {}).get('tickets',[])}
        result=[]
        for ticket in original.get('tickets',[]):
            config=ticket.get('configuration') or {}
            rule_id=str(config['ruleId']) if config.get('ruleId') else None
            row=rules.get(rule_id)
            status,reason,amount='unavailable','原核对没有可靠关联规则，不能猜测最新值',None
            if rule_id:
                if row is None:reason='原关联规则当前不存在或不属于出票规则，不能用其他规则替代'
                elif row.get('contentTruncated'):reason='当前规则内容超过取证上限，未使用截断值'
                elif row.get('rule_type')!=LOSS_RULE_TYPE:reason='原关联规则当前不是亏损阈值配置'
                else:
                    calculated=ticket_threshold(row.get('ext_json'),ticket.get('segmentCount'))
                    status=calculated['status'];reason=calculated.get('reason','同规则当前分段值，仅提醒，未重新判断本单适用性')
                    amount=calculated.get('amount')
            current_fingerprint=digest(row) if row is not None else None
            effective=None
            if row is not None:
                try:
                    effective=(str(row.get('status'))=='1' and
                               (row.get('start_time') is None or timestamp(row['start_time'])<=observed) and
                               (row.get('end_time') is None or timestamp(row['end_time'])>=observed))
                except (ValueError,TypeError):effective=None
            original_fingerprint=config.get('configurationHash')
            baseline=previous_tickets.get(str(ticket['id']))
            before=baseline.get('latestStopLoss') if baseline else ticket.get('stopLoss')
            configuration_changed=(current_fingerprint!=baseline.get('sourceFingerprint')) if baseline else None
            # Compare source snapshots with the same historical hashing vocabulary when available.
            if not baseline and row is not None and config.get('configurationSnapshot'):
                original_snapshot=config['configurationSnapshot']
                configuration_changed=any((str(row.get(key))!=str(value)) if key=='id' else encoded(row.get(key))!=encoded(value) for key,value in original_snapshot.items())
            item={'ticketId':str(ticket['id']),'ruleId':rule_id,'segmentCount':ticket.get('segmentCount'),
                  'originalStopLoss':ticket.get('stopLoss'),'originalResult':ticket.get('status'),
                  'originalConfigurationVersion':config.get('configurationVersion'),'originalConfigurationHash':original_fingerprint,
                  'originalTimeBasis':{'asOf':config.get('asOf'),'basis':config.get('basis'),'historyProof':config.get('historyProof'),
                                       'historicalVerified':bool(config.get('basis')=='issue_time_configuration' and config.get('asOf') and config.get('historyProof'))},
                  'beforeStopLoss':before,'latestStopLoss':amount,'status':status,'reason':reason,'sourceFingerprint':current_fingerprint,
                  'valueChanged':value_changed(before,amount),
                  'differentFromOriginal':value_changed(ticket.get('stopLoss'),amount),
                  'configurationChanged':configuration_changed,'sourceVersion':row.get('version') if row else None,
                  'sourceUpdatedAt':str(row['update_time']) if row and row.get('update_time') is not None else None,
                  'sourceStatus':row.get('status') if row else None,
                  'sourceCurrentlyEffective':effective,
                  'sourceStart':str(row['start_time']) if row and row.get('start_time') is not None else None,
                  'sourceEnd':str(row['end_time']) if row and row.get('end_time') is not None else None,
                  'sourceSnapshot':json.loads(encoded(row)) if row else None,
                  'observedAt':observed,'effectiveChangeAt':None,'effectiveTimeBasis':'仅有源更新时间和本次观察时点，未证明该变更的真实生效时点',
                  'usedForOriginalCalculation':False}
            result.append(item)
        return result

    def observe(self, actor, order, payload):
        actor,order,issue_date=_owner(actor),str(order_id(order)),day(payload.get('issueDate'))
        request_id=identifier(payload.get('requestId'));request_hash=digest([actor,order,issue_date,payload])
        # An existing receipt is returned before querying ERP, including after timeout/retry.
        def replay(db):
            row=db.execute('SELECT request_hash,body FROM bi_risk_config_observations WHERE request_id=?',(request_id,)).fetchone()
            if not row:return None
            if row['request_hash']!=request_hash:raise FlowError('操作标识已用于其他请求',409)
            return json.loads(row['body'])
        with self.store.db() as db:
            prior=replay(db)
            if prior:return prior
            saved=self._load(db,order,issue_date)
            if not saved:raise FlowError('请先保存原核对配置证据',409)
        ids=[t.get('configuration',{}).get('ruleId') for t in saved['original'].get('tickets',[]) if t.get('configuration') and t['configuration'].get('ruleId')]
        if not ids:raise FlowError('原核对无可靠关联规则，不能观察或猜测最新值',409)
        source=self.reader.read_identifiers(ids)
        try:
            with self.store.db() as db:
                self._load(db,order,issue_date,True)
                prior=replay(db)
                if prior:return prior
                row=db.execute('SELECT body FROM bi_risk_config_observations WHERE evidence_id=? ORDER BY seq DESC LIMIT 1',(saved['id'],)).fetchone()
                previous=json.loads(row['body']) if row else None
                observed=timestamp(source['observedAt'])
                if previous and observed<previous['observedAt']:
                    raise FlowError('此观察早于已保存的最新观察，未覆盖最新提醒，请重试',409)
                body={'schemaVersion':1,'id':uuid.uuid4().hex,'evidenceId':saved['id'],'observedBy':actor,'observedAt':observed,'recordedAt':now(),
                      'previousObservationId':previous['id'] if previous else None,
                      'tickets':self.compare(saved['original'],source,previous),
                      'notice':'仅原关联规则当前配置的观察，不代表出票时有效，不重新匹配或核算原单。'}
                body['changed']=any(t['valueChanged'] is True or t['configurationChanged'] is True for t in body['tickets'])
                body['hasUnavailable']=any(t['status']!='ready' for t in body['tickets'])
                body['hasUnknownComparison']=any(t['valueChanged'] is None or t['configurationChanged'] is None for t in body['tickets'])
                db.execute('INSERT INTO bi_risk_config_observations (id,evidence_id,request_id,request_hash,body) VALUES(?,?,?,?,?)',
                           (body['id'],saved['id'],request_id,request_hash,encoded(body)))
                return body
        except StoreConflict:
            with self.store.db() as db:
                prior=replay(db)
                if prior:return prior
            raise FlowError('观察保存冲突，请刷新后重试',409) from None
