"""Read a completely published observation. Never query ERP or start a job."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .risk_auto_store import RiskAutoStore
from .risk_followup import day
from .risk_order_evidence import order_id
from .risk_prepared_facts import one
from .risk_verification_flow import FlowError

RUN_FIELDS = 'run_id,run_day,status,observed_at,source_hash,source_changed,error_code,started_at,completed_at'


def result_id(row):
    identity = [str(row['issue_date'])[:10], str(row['order_id']), row['rule_version'], row['engine_hash'], row['evidence_hash']]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32]


def run_view(row):
    if not row:
        return None
    return {'runId': row['run_id'], 'runDay': str(row['run_day']), 'status': row['status'],
            'observedAt': str(row['observed_at']) if row['observed_at'] is not None else None,
            'sourceHash': row['source_hash'], 'sourceChangedAfterSnapshot': bool(row['source_changed']),
            'lastError': row['error_code'], 'startedAt': str(row['started_at']),
            'completedAt': str(row['completed_at']) if row['completed_at'] is not None else None}


class RiskLatestConfig:
    def __init__(self, config, store=None):
        self.store = store or RiskAutoStore(config)

    def get(self, order, issue_date, expected_result_id, history_run_id=None):
        order, issue_date = str(order_id(order)), day(issue_date)
        if not isinstance(expected_result_id, str) or not re.fullmatch(r'[a-f0-9]{32}', expected_result_id):
            raise FlowError('请提供当前查看的核查证据版本')
        if history_run_id is not None and (not isinstance(history_run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', history_run_id)):
            raise FlowError('历史核查版本标识无效')
        with self.store.db(consistent_snapshot=True) as db:
            if history_run_id is not None:
                history = db.execute('''SELECT issue_date,order_id,etl_run_id,rule_version,engine_hash,evidence_hash
                    FROM bi_risk_prepared_order_history WHERE order_id=? AND issue_date=? AND etl_run_id=?''',
                                     (order, issue_date, history_run_id)).fetchone()
                if not history or result_id(history) != expected_result_id:
                    raise FlowError('历史核查与当前查看的证据版本不一致', 409)
            else:
                current = one(lambda sql, args: db.execute(sql, args).fetchall(), order, issue_date)
                if not current or current['id'] != expected_result_id:
                    raise FlowError('核查证据已变化，请重新打开订单后查看最新配置', 409)
                history = db.execute('''SELECT issue_date,order_id,etl_run_id,rule_version,engine_hash,evidence_hash
                    FROM bi_risk_prepared_order_history WHERE order_id=? AND issue_date=? AND valid_to IS NULL
                    AND rule_version=? AND engine_hash=? AND evidence_hash=?''',
                                     (order, issue_date, current['ruleVersion'], current['engineHash'], current['evidenceHash'])).fetchone()
            attempt = db.execute('SELECT '+RUN_FIELDS+' FROM bi_risk_latest_config_run ORDER BY run_day DESC,started_at DESC LIMIT 1').fetchone()
            latest_attempt = run_view(attempt)
            diagnostic = db.execute('SELECT state_json FROM bi_risk_refresh_state WHERE state_key=?', ('latest_config_last_attempt',)).fetchone()
            if diagnostic:
                try:
                    item = json.loads(diagnostic['state_json'])
                    if not isinstance(item, dict) or not isinstance(item.get('startedAt'), str) or item.get('status') not in ('running', 'failed', 'partial', 'success', 'skipped'):
                        raise ValueError()
                    if not latest_attempt or item['startedAt'].replace('T', ' ') > latest_attempt['startedAt'].replace('T', ' '):
                        latest_attempt = {key: item.get(key) for key in ('runId', 'status', 'lastError', 'startedAt', 'completedAt')}
                except (ValueError, TypeError):
                    raise FlowError('最新配置刷新诊断无效，请核对每日任务', 503) from None
            pointer = db.execute('SELECT state_json FROM bi_risk_refresh_state WHERE state_key=?', ('latest_config_published_run',)).fetchone()
            business_now = datetime.now(ZoneInfo('Asia/Shanghai'))
            expected_day = business_now.date() - timedelta(days=int(business_now.hour < 6))
            response = {'state': 'unrefreshed', 'historyRunId': str(history['etl_run_id']) if history else None,
                        'expectedRunDay': expected_day.isoformat(),
                        'observation': None, 'publishedRun': None, 'latestAttempt': latest_attempt}
            if not pointer:
                return response
            try:
                published = json.loads(pointer['state_json'])
            except (ValueError, TypeError):
                raise FlowError('最新配置发布指针无效，请核对每日任务', 503) from None
            if not isinstance(published, str) or not re.fullmatch(r'[a-f0-9]{32}', published):
                raise FlowError('最新配置发布版本无效，请核对每日任务', 503)
            run = db.execute('SELECT '+RUN_FIELDS+' FROM bi_risk_latest_config_run WHERE run_id=?', (published,)).fetchone()
            if not run or run['status'] != 'success':
                raise FlowError('最新配置成功版本未就绪，请核对每日任务', 503)
            response['publishedRun'] = run_view(run)
            if not history:
                return response
            history_key = hashlib.sha256(f"{issue_date}|{order}|{history['etl_run_id']}".encode()).hexdigest()
            row = db.execute('''SELECT v.body,m.fallback_json FROM bi_risk_latest_config_member m
                JOIN bi_risk_latest_config_value v ON v.value_id=m.value_id AND v.history_key=m.history_key
                WHERE m.run_id=? AND m.history_key=? AND m.issue_date=? AND m.order_id=? AND m.history_run_id=?''',
                             (published, history_key, issue_date, order, history['etl_run_id'])).fetchone()
            if not row:
                return response
            try:
                observation = json.loads(row['body'])
            except (ValueError, TypeError):
                raise FlowError('最新配置观察内容损坏，原核查未修改', 503) from None
            if (not isinstance(observation, dict) or observation.get('schemaVersion') != 1
                    or observation.get('historyKey') != history_key or observation.get('resultId') != expected_result_id
                    or not isinstance(observation.get('tickets'), list)):
                raise FlowError('最新配置观察证据版本不一致，原核查未修改', 503)
            try:
                fallback = json.loads(row['fallback_json']) if row['fallback_json'] else {}
            except (ValueError, TypeError):
                raise FlowError('最新配置上次可用依据损坏，请核对每日任务', 503) from None
            if not isinstance(fallback, dict):
                raise FlowError('最新配置上次可用依据无效', 503)
            for ticket in observation['tickets']:
                if not isinstance(ticket, dict) or not isinstance(ticket.get('ticketId'), str):
                    raise FlowError('最新配置逐票关联无效', 503)
                if ticket['status'] != 'matched' and ticket['ticketId'] in fallback:
                    old = fallback[ticket['ticketId']]
                    if not isinstance(old, dict) or old.get('ticketId') != ticket['ticketId'] or old.get('status') != 'matched':
                        raise FlowError('最新配置上次可用票依据关联无效', 503)
                    ticket['lastSuccessful'] = old
            response.update(state='ready', observation=observation)
            return response
