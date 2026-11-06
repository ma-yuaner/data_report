"""Team review and follow-up. Writes only dedicated sibebid tables, never ERP/ETL."""
import hashlib
import json
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .risk_auto_store import RiskAutoStore, StoreConflict
from .risk_verification_flow import FlowError, _owner
from .risk_prepared_facts import one, engine_hash
from .risk_commission_rule import RULE_ID
from .risk_child_loss import SUPPORTED_REASONS
from .risk_problem_tags import text
from .risk_verification_overview import _integer
from .risk_order_evidence import order_id

CONCLUSIONS = ('no_issue', 'problem', 'unknown')
DISPOSITIONS = ('pending', 'included', 'excluded')
STATES = ('todo', 'following', 'waiting', 'done')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def choice(value, options, label):
    if value not in options:
        raise FlowError(label + '无效')
    return value


def day(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise FlowError('出票日期无效') from None


def version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlowError('请提供记录版本')
    return value


def planning(body):
    body['assignee'] = text(body.get('assignee'), 80, '负责人')
    body['nextStep'] = text(body.get('nextStep'), 1000, '下一步或完成结果')
    choice(body.get('state'), STATES, '跟进状态')
    if body['state'] != 'done':
        try:
            dt = datetime.fromisoformat(str(body.get('nextAt')))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
            body['nextAt'] = dt.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='minutes')
        except (TypeError, ValueError):
            raise FlowError('未完成案例须填写下次跟进时间') from None
    else:
        body['nextAt'] = None
        if body['conclusion'] == 'unknown' or body['disposition'] == 'pending':
            raise FlowError('待补证或待认定案例不能完成')
    for key in ('firstSeen', 'special'):
        if not isinstance(body.get(key, False), bool):
            raise FlowError('案例标记无效')
        body[key] = body.get(key, False)
    if body['firstSeen'] or body['special']:
        body['specialReason'] = text(body.get('specialReason'), 1000, '首次或特殊案例说明')


class RiskFollowup:
    def __init__(self, config, store=None):
        self.store = store or RiskAutoStore(config)

    def _transaction(self, actor, payload, action):
        actor = _owner(actor)
        key = payload.get('requestId')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', key):
            raise FlowError('请求标识无效，请重新打开表单')
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        def receipt(db):
            row = db.execute('SELECT actor,digest,response FROM bi_risk_followup_requests WHERE id=?', (key,)).fetchone()
            if not row:
                return None
            if row['actor'] != actor or row['digest'] != digest:
                raise FlowError('请求标识已用于其他操作', 409)
            return json.loads(row['response'])
        try:
            with self.store.db() as db:
                old = receipt(db)
                if old is not None:
                    return old
                # Reserve before mutation; a racing duplicate rolls back then reads committed receipt.
                db.execute('INSERT INTO bi_risk_followup_requests (id,actor,digest,response) VALUES(?,?,?,?)', (key, actor, digest, '{}'))
                result = action(db)
                db.execute('UPDATE bi_risk_followup_requests SET response=? WHERE id=?', (encoded(result), key))
                return result
        except StoreConflict:
            with self.store.db() as db:
                old = receipt(db)
                if old is not None:
                    return old
            raise FlowError('记录已被其他人修改，请刷新后重试', 409) from None

    @staticmethod
    def _snapshot(db, identifier, issue_date, lock=False):
        identifier, issue_date = str(order_id(identifier)), day(issue_date)
        body = one(lambda sql, args: db.execute(sql, args).fetchall(), identifier, issue_date, lock)
        if body:
            return {'orderId': identifier, 'issueDate': issue_date, 'resultId': body['id'], 'systemStatus': body['status'],
                    'snapshotKind': 'prepared', 'evidenceHash': body['evidenceHash'], 'ruleVersion': body['ruleVersion'], 'engineHash': body['engineHash']}
        row = db.execute('SELECT order_id,profit_reason_type,update_time,etl_run_id FROM bi_risk_order_day WHERE order_id=? AND issue_date=?' + (' FOR UPDATE' if lock else ''), (identifier, issue_date)).fetchone()
        if not row:
            raise FlowError('订单不在该出票日已同步目录中', 409)
        return {'orderId': identifier, 'issueDate': issue_date,
                'resultId': 'catalog-' + hashlib.sha256(encoded(dict(row)).encode()).hexdigest()[:32],
                'systemStatus': 'unchecked', 'snapshotKind': 'catalog', 'catalogRunId': row['etl_run_id']}

    @staticmethod
    def _stale_clause():
        # Same daily readiness gates as fact(); no ERP calls or stored "current" flag.
        ready = """o.order_id IS NOT NULL AND p.etl_run_id=o.etl_run_id AND d.etl_run_id=p.etl_run_id
          AND p.rule_version=? AND d.rule_version=p.rule_version AND p.engine_hash=? AND d.engine_hash=p.engine_hash
          AND p.source_updated_at<=>o.update_time AND p.reason_code=o.profit_reason_type
          AND JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.ruleVersion'))=p.rule_version
          AND JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.engineHash'))=p.engine_hash
          AND JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.status')) IN ('supported','problem','insufficient','failed')"""
        ready += ' AND o.profit_reason_type IN (' + ','.join("'" + code + "'" for code in SUPPORTED_REASONS) + ')'
        valid = """((JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.snapshotKind'))='prepared' AND (""" + ready + """)
          AND p.evidence_hash=JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.evidenceHash'))
          AND p.rule_version=JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.ruleVersion'))
          AND p.engine_hash=JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.engineHash')))
          OR (JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.snapshotKind'))='catalog' AND o.order_id IS NOT NULL
          AND o.etl_run_id=JSON_UNQUOTE(JSON_EXTRACT(r.body,'$.catalogRunId')) AND NOT COALESCE((""" + ready + """),0)))"""
        sql = """EXISTS (SELECT 1 FROM bi_risk_order_reviews r
          LEFT JOIN bi_risk_order_day o ON o.order_id=r.order_id AND o.issue_date=r.issue_date
          LEFT JOIN bi_risk_prepared_order p ON p.order_id=r.order_id AND p.issue_date=r.issue_date
          LEFT JOIN bi_risk_prepared_day d ON d.issue_date=r.issue_date
          WHERE r.case_id=c.id AND NOT COALESCE(""" + valid + ",0))"
        return sql, (RULE_ID, engine_hash(), RULE_ID, engine_hash())

    @staticmethod
    def _review(db, identifier, issue_date, lock=False):
        row = db.execute('SELECT version,body FROM bi_risk_order_reviews WHERE order_id=? AND issue_date=?' + (' FOR UPDATE' if lock else ''), (identifier, issue_date)).fetchone()
        return json.loads(row['body']) if row else None

    def order(self, identifier, issue_date):
        with self.store.db() as db:
            current = self._snapshot(db, identifier, issue_date)
            review = self._review(db, current['orderId'], current['issueDate'])
            events = db.execute('SELECT body FROM bi_risk_followup_events WHERE order_id=? AND issue_date=? ORDER BY seq DESC LIMIT 101', (current['orderId'], current['issueDate'])).fetchall()
            return {**current, 'review': review, 'stale': bool(review and review['resultId'] != current['resultId']), 'version': review['version'] if review else 0,
                    'events': [json.loads(row['body']) for row in events[:100]], 'eventsTruncated': len(events) > 100}

    def summaries(self, items):
        if not isinstance(items, list) or len(items) > 100 or any(not isinstance(item, dict) for item in items):
            raise FlowError('最多读取100笔订单人工状态')
        result = []
        with self.store.db() as db:
            for item in items:
                current = self._snapshot(db, item.get('orderId'), item.get('issueDate'))
                review = self._review(db, current['orderId'], current['issueDate'])
                result.append({**current, 'review': review, 'stale': bool(review and review['resultId'] != current['resultId']), 'version': review['version'] if review else 0})
        return result

    def policies(self):
        with self.store.db() as db:
            rows = db.execute('SELECT body FROM bi_risk_review_policies ORDER BY created_at DESC,id DESC LIMIT 501').fetchall()
            if len(rows) > 500:
                raise FlowError('策略超过500项，请治理策略目录', 413)
            return [json.loads(row['body']) for row in rows]

    def policy_create(self, actor, payload):
        def create(db):
            body = {key: text(payload.get(key), limit, label) for key, limit, label in (
                ('name', 100, '规则名称'), ('policyVersion', 60, '规则版本'), ('scope', 1000, '适用范围'), ('basis', 20000 if payload.get('ruleDocument') is True else 2000, '规则正文'))}
            body.update(ruleDocument=payload.get('ruleDocument') is True, id=uuid.uuid4().hex, start=day(payload.get('start')), end=day(payload.get('end')), actor=actor, at=now())
            if body['start'] > body['end']:
                raise FlowError('策略有效期起止不正确')
            db.execute('INSERT INTO bi_risk_review_policies (id,body) VALUES(?,?)', (body['id'], encoded(body)))
            return body
        return self._transaction(actor, payload, create)

    @staticmethod
    def _case(db, case_id, lock=False):
        if not isinstance(case_id, str) or not re.fullmatch(r'[a-f0-9]{32}', case_id):
            raise FlowError('案例编号无效')
        row = db.execute('SELECT body FROM bi_risk_followup_cases WHERE id=?' + (' FOR UPDATE' if lock else ''), (case_id,)).fetchone()
        if not row:
            raise FlowError('案例不存在', 404)
        return json.loads(row['body'])

    @staticmethod
    def _save_case(db, body):
        db.execute('UPDATE bi_risk_followup_cases SET version=?,conclusion=?,disposition=?,state=?,assignee=?,next_at=?,first_seen=?,special=?,body=?,updated_at=? WHERE id=?',
                   (body['version'], body['conclusion'], body['disposition'], body['state'], body['assignee'],
                    body.get('nextAt'), int(body['firstSeen']), int(body['special']), encoded(body), body['updatedAt'], body['id']))

    @staticmethod
    def _event(db, case_id, actor, kind, before, after, note):
        body = {'actor': actor, 'at': now(), 'kind': kind, 'before': before, 'after': after, 'note': note}
        db.execute('INSERT INTO bi_risk_followup_events (id,case_id,order_id,issue_date,body) VALUES(?,?,?,?,?)', (uuid.uuid4().hex, case_id, after.get('orderId'), after.get('issueDate'), encoded(body)))

    def review(self, actor, payload):
        if payload.get('workflowVersion') == 3:
            from .risk_workflow_v3 import review
            return review(self, actor, payload)
        def save(db):
            items = payload.get('orders')
            if not isinstance(items, list) or not 1 <= len(items) <= 100 or any(not isinstance(item, dict) for item in items):
                raise FlowError('请选择1至100笔订单')
            conclusion = choice(payload.get('conclusion'), CONCLUSIONS, '人工结论')
            reason = text(payload.get('reason'), 2000, '核实依据')
            if len(items) > 1 and conclusion != 'no_issue':
                raise FlowError('批量核实仅支持同策略确认无问题')
            simple = payload.get('simpleReview') is True
            markers = {}
            if simple:
                for field in ('firstSeen', 'special'):
                    if not isinstance(payload.get(field, False), bool):
                        raise FlowError('核实类型无效')
                    markers[field] = payload.get(field, False)
                markers['specialReason'] = text(payload.get('specialReason'), 1000, '类型说明') if any(markers.values()) else ''
                type_ids = payload.get('problemTypeIds', []) if conclusion == 'problem' else []
                if not isinstance(type_ids, list) or len(type_ids) > 10 or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value) for value in type_ids) or len(set(type_ids)) != len(type_ids):
                    raise FlowError('请选择最多10个不重复的问题类型')
                markers['problemTypes'] = []
                if type_ids:
                    rows = db.execute('SELECT id,name FROM bi_risk_problem_types WHERE id IN (' + ','.join('?' for _ in type_ids) + ')', tuple(type_ids)).fetchall()
                    found = {row['id']: row['name'] for row in rows}
                    if len(found) != len(type_ids):
                        raise FlowError('问题类型已变化，请刷新后重新选择', 409)
                    markers['problemTypes'] = [{'id': value, 'name': found[value]} for value in type_ids]

            policy = None
            no_issue_reason = payload.get('noIssueReason', 'company_policy')
            if conclusion == 'no_issue':
                choice(no_issue_reason, ('company_policy', 'evidence_verified', 'system_false_positive'), '无问题原因')
            if conclusion == 'no_issue' and (len(items) > 1 or no_issue_reason == 'company_policy'):
                row = db.execute('SELECT body FROM bi_risk_review_policies WHERE id=?', (str(payload.get('policyId', '')),)).fetchone()
                if not row:
                    raise FlowError('请选择已登记的具体公司策略')
                policy = json.loads(row['body'])
                if payload.get('scopeConfirmed') is not True:
                    raise FlowError('请逐单核对并确认符合策略适用范围')
            case = None
            case_id = payload.get('caseId')
            # Lock shared case before order rows consistently with case updates.
            if simple and case_id:
                raise FlowError('简版人工核实不关联案例')
            if case_id:
                case = self._case(db, case_id, True)
                if case['version'] != version(payload.get('caseVersion')) or case['state'] == 'done' or case['conclusion'] != conclusion:
                    raise FlowError('案例已变化、已完成或核实结论不同，请刷新后选择', 409)
            checked = []
            keys = set()
            for item in sorted(items, key=lambda row: (str(row.get('orderId')), str(row.get('issueDate')))):
                current = self._snapshot(db, item.get('orderId'), item.get('issueDate'), True)
                key = (current['orderId'], current['issueDate'])
                if key in keys:
                    raise FlowError('订单重复')
                keys.add(key)
                old = self._review(db, *key, lock=True)
                if item.get('resultId') != current['resultId'] or version(item.get('version')) != (old['version'] if old else 0):
                    raise FlowError('订单证据或人工记录已变化，请刷新后重新核实', 409)
                if old and old.get('caseId') and old.get('caseId') != case_id:
                    raise FlowError('订单已有跟进案例，请进入原案例处理', 409)
                if policy and not policy['start'] <= current['issueDate'] <= policy['end']:
                    raise FlowError('策略有效期不覆盖所选订单，未保存任何订单', 409)
                checked.append((current, old))
            if conclusion != 'no_issue' and not case and not simple:
                fields = ('title', 'problemType', 'cause', 'responsibility', 'assignee', 'nextStep', 'nextAt', 'specialReason')
                case = {key: payload.get(key) for key in fields}
                case.update(id=uuid.uuid4().hex, version=1, conclusion=conclusion, disposition='pending', state='todo',
                            firstSeen=payload.get('firstSeen', False), special=payload.get('special', False), createdAt=now(), updatedAt=now())
                case['title'] = text(case.get('title'), 160, '案例标题')
                for key, label in (('problemType', '问题类型'), ('cause', '发生原因或待核实项'), ('responsibility', '责任归属或待确认说明')):
                    case[key] = text(case.get(key), 500, label)
                planning(case)
                db.execute('INSERT INTO bi_risk_followup_cases (id,version,conclusion,disposition,state,assignee,next_at,first_seen,special,body,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (case['id'], 1, conclusion, 'pending', 'todo', case['assignee'], case['nextAt'], int(case['firstSeen']), int(case['special']), encoded(case), case['updatedAt']))
            elif case:
                existing_count = db.execute('SELECT COUNT(*) AS n FROM bi_risk_order_reviews WHERE case_id=?', (case_id,)).fetchone()['n']
                additions = sum(not old or old.get('caseId') != case_id for _, old in checked)
                if existing_count + additions > 1000:
                    raise FlowError('案例最多关联1000单，请拆分案例', 413)
                case['version'] += 1
                case['updatedAt'] = now()
                self._save_case(db, case)
            for current, old in checked:
                body = {**current, 'version': (old['version'] if old else 0) + 1, 'conclusion': conclusion, 'reason': reason,
                        **markers, 'policy': policy, 'noIssueReason': no_issue_reason if conclusion == 'no_issue' else None,
                        'caseId': case['id'] if case else None, 'actor': actor, 'at': now()}
                if old:
                    db.execute('UPDATE bi_risk_order_reviews SET version=?,case_id=?,body=? WHERE order_id=? AND issue_date=?',
                               (body['version'], body['caseId'], encoded(body), body['orderId'], body['issueDate']))
                else:
                    db.execute('INSERT INTO bi_risk_order_reviews (order_id,issue_date,version,case_id,body) VALUES(?,?,?,?,?)',
                               (body['orderId'], body['issueDate'], body['version'], body['caseId'], encoded(body)))
                self._event(db, body['caseId'], actor, 'review', old, body, reason)
            return {'count': len(checked), 'caseId': case['id'] if case else None}
        return self._transaction(actor, payload, save)

    def detail(self, case_id):
        with self.store.db() as db:
            body = self._case(db, case_id)
            rows = db.execute('SELECT body FROM bi_risk_order_reviews WHERE case_id=? ORDER BY issue_date DESC,order_id LIMIT 1001', (case_id,)).fetchall()
            if len(rows) > 1000:
                raise FlowError('案例关联超过1000单，请拆分案例', 413)
            orders = []
            for row in rows:
                review = json.loads(row['body'])
                try:
                    current = self._snapshot(db, review['orderId'], review['issueDate'])
                    stale = current['resultId'] != review['resultId']
                except FlowError as error:
                    if error.status != 409:
                        raise
                    stale = True
                orders.append({**review, 'stale': stale})
            events = db.execute('SELECT body FROM bi_risk_followup_events WHERE case_id=? ORDER BY seq DESC LIMIT 501', (case_id,)).fetchall()
            return {**body, 'orders': orders, 'events': [json.loads(row['body']) for row in events[:500]], 'eventsTruncated': len(events) > 500}

    def update(self, actor, case_id, payload):
        with self.store.db() as read_db:
            current_case = self._case(read_db, case_id)
        if payload.get('workflowVersion') == 3 or current_case.get('workflowVersion') == 3:
            from .risk_workflow_v3 import update
            return update(self, actor, case_id, payload)
        def save(db):
            before = self._case(db, case_id, True)
            if before['version'] != version(payload.get('version')):
                raise FlowError('案例已被修改，请刷新后重新填写', 409)
            note = text(payload.get('note'), 2000, '本次跟进或调整依据')
            body = {**before, **{key: payload.get(key, before.get(key)) for key in (
                'conclusion', 'disposition', 'state', 'assignee', 'nextStep', 'nextAt', 'firstSeen', 'special',
                'specialReason', 'problemType', 'cause', 'responsibility')}}
            choice(body['conclusion'], CONCLUSIONS, '人工结论')
            choice(body['disposition'], DISPOSITIONS, '差错认定')
            if body['conclusion'] == 'unknown' and body['disposition'] != 'pending':
                raise FlowError('暂无法判断时只能待认定')
            if body['conclusion'] == 'no_issue' and body['disposition'] != 'excluded':
                raise FlowError('确认无问题时应选择不计入差错')
            for key, label in (('problemType', '问题类型'), ('cause', '发生原因'), ('responsibility', '责任归属')):
                body[key] = text(body.get(key), 500, label)
            planning(body)
            rows = db.execute('SELECT order_id,issue_date,body FROM bi_risk_order_reviews WHERE case_id=? ORDER BY order_id,issue_date FOR UPDATE', (case_id,)).fetchall()
            for row in rows:
                review = json.loads(row['body'])
                # New recognition/closure requires current reviewed evidence; follow-up itself remains possible.
                if body['conclusion'] != before['conclusion'] or body['disposition'] != before['disposition'] or (body['state'] == 'done' and before['state'] != 'done'):
                    current = self._snapshot(db, row['order_id'], str(row['issue_date'])[:10], True)
                    if current['resultId'] != review['resultId']:
                        raise FlowError('关联订单证据已变化，请先逐单重新核实后再认定或完成', 409)
                if body['conclusion'] != before['conclusion']:
                    after_review = {**review, 'conclusion': body['conclusion'], 'version': review['version'] + 1, 'actor': actor, 'at': now(), 'reason': note}
                    db.execute('UPDATE bi_risk_order_reviews SET version=?,body=? WHERE order_id=? AND issue_date=?',
                               (after_review['version'], encoded(after_review), row['order_id'], str(row['issue_date'])[:10]))
            body.update(version=before['version'] + 1, updatedAt=now())
            self._save_case(db, body)
            self._event(db, case_id, actor, 'followup', before, body, note)
            return body
        return self._transaction(actor, payload, save)

    def listing(self, params, actor):
        clauses, args = ['1=1'], []
        for key, column, options in (('disposition', 'disposition', DISPOSITIONS), ('state', 'state', STATES), ('conclusion', 'conclusion', CONCLUSIONS)):
            value = params.get(key)
            if value:
                clauses.append(column + '=?')
                args.append(choice(value, options, key))
        for key, column in (('firstSeen', 'first_seen'), ('special', 'special')):
            if params.get(key) == '1':
                clauses.append(column + '=1')
        if params.get('assignee'):
            clauses.append('assignee=?')
            args.append(text(params['assignee'], 80, '负责人'))
        if params.get('overdue') == '1':
            clauses.append("state<>'done' AND next_at<?")
            args.append(now())
        if params.get('q'):
            clauses.append('(id=? OR JSON_UNQUOTE(JSON_EXTRACT(body,\'$.title\')) LIKE ?)')
            query = text(params['q'], 160, '搜索内容')
            args.extend((query, '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'))
        page = _integer(params.get('page', '1'), '页码', 100000)
        size = _integer(params.get('pageSize', '20'), '每页数量', 100)
        scope = ' AND '.join(clauses)
        stale_sql, stale_args = self._stale_clause()
        with self.store.db() as db:
            count = db.execute('SELECT COUNT(*) AS n FROM bi_risk_followup_cases WHERE ' + scope, tuple(args)).fetchone()['n']
            rows = db.execute('SELECT c.body,' + stale_sql + ' AS stale FROM bi_risk_followup_cases c WHERE ' + scope + ' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?', (*stale_args, *args, size, (page - 1) * size)).fetchall()
            metrics = db.execute("SELECT COUNT(*) AS total,SUM(conclusion='problem' AND disposition='pending' AND stale=0) AS pending,SUM(conclusion='problem' AND disposition='included' AND stale=0) AS included,SUM(conclusion<>'unknown' AND disposition='excluded' AND stale=0) AS excluded,SUM(state<>'done' AND next_at<?) AS overdue,SUM(conclusion='unknown' AND stale=0) AS unknown,SUM(stale) AS stale FROM (SELECT c.*," + stale_sql + ' AS stale FROM bi_risk_followup_cases c) scoped', (now(), *stale_args)).fetchone()
        return {'items': [{**json.loads(row['body']), 'stale': bool(row['stale'])} for row in rows], 'total': int(count), 'metrics': {key: int(value or 0) for key, value in dict(metrics).items()}, 'page': page, 'pageSize': size}
