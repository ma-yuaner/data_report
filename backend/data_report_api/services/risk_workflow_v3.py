"""Version 3 review-to-case workflow. All writes share the existing receipt transaction."""
import json
import uuid
from .risk_review_contract import choice, encoded, now, version
from .risk_problem_tags import text
from .risk_verification_flow import FlowError


def optional(value, limit, label):
    return '' if value in (None, '') else text(value, limit, label)


def review(service, actor, payload):
    def save(db):
        items = payload.get('orders')
        if not isinstance(items, list) or not 1 <= len(items) <= 100 or any(not isinstance(i, dict) for i in items):
            raise FlowError('请选择1至100笔订单')
        conclusion = choice(payload.get('conclusion'), ('no_issue', 'problem'), '人工结论')
        if len(items) > 1 and conclusion != 'no_issue':
            raise FlowError('有问题的订单请逐单核实')
        reason = text(payload.get('reason'), 2000, '核实依据')
        remark = optional(payload.get('remark'), 2000, '备注')
        consultation = choice(payload.get('consultation', 'pending'), ('pending', 'consulted'), '咨询状态') if conclusion == 'problem' else None
        seen, case_ids = set(), []
        for item in sorted(items, key=lambda i: (str(i.get('orderId')), str(i.get('issueDate')))):
            case_id = item.get('caseId')
            case = service._case(db, case_id, True) if case_id else None
            current = service._snapshot(db, item.get('orderId'), item.get('issueDate'), True)
            key = (current['orderId'], current['issueDate'])
            if key in seen:
                raise FlowError('订单重复')
            seen.add(key)
            metadata = db.execute('SELECT ota_order_no,ota_code FROM bi_risk_order_day WHERE order_id=? AND issue_date=?', key).fetchone()
            metadata = dict(metadata) if metadata else {}
            old = service._review(db, *key, lock=True)
            if current['resultId'] != item.get('resultId') or version(item.get('version')) != (old['version'] if old else 0):
                raise FlowError('订单证据或人工记录已变化，请刷新后重新核实', 409)
            if (old or {}).get('caseId') != (case_id or None):
                raise FlowError('订单案例关联已变化，请刷新后重试', 409)
            if case:
                if payload.get('caseVersion') is not None and case['version'] != version(payload['caseVersion']):
                    raise FlowError('案例已变化，请刷新后重新核实', 409)
                n = db.execute('SELECT COUNT(*) AS n FROM bi_risk_order_reviews WHERE case_id=?', (case_id,)).fetchone()['n']
                if n > 1:
                    raise FlowError('此历史案例关联多单，请从原案例统一调整，避免影响其他订单', 409)
                before_case = dict(case)
                case.update(workflowVersion=3, conclusion=conclusion, consultation=consultation, remark=remark,
                            version=case['version'] + 1, updatedAt=now())
                if conclusion == 'no_issue':
                    case.update(state='done', nextAt=None, nextStep=reason)
                    if case['disposition'] == 'included':
                        case.update(disposition='excluded', wasIncluded=True)
                elif before_case['conclusion'] != 'problem':
                    case.update(state='todo', nextAt=None, nextStep=reason)
                service._save_case(db, case)
                service._event(db, case_id, actor, 'recognition', before_case, case, reason)
            elif conclusion == 'problem':
                case_id = uuid.uuid4().hex
                case = dict(id=case_id, workflowVersion=3, version=1, title='人工核实问题 · ' + str(metadata.get('ota_order_no') or current['issueDate']),
                            conclusion='problem', disposition='pending', state='todo', consultation=consultation,
                            remark=remark, assignee='', nextAt=None, nextStep=reason, firstSeen=False, special=False,
                            specialReason='', problemType='', cause=reason, responsibility='', createdAt=now(), updatedAt=now())
                db.execute('INSERT INTO bi_risk_followup_cases (id,version,conclusion,disposition,state,assignee,next_at,first_seen,special,body,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (case_id, 1, 'problem', 'pending', 'todo', '', None, 0, 0, encoded(case), case['updatedAt']))
            body = {**current, 'otaOrderNo': metadata.get('ota_order_no'), 'otaCode': metadata.get('ota_code'), 'workflowVersion': 3, 'version': (old['version'] if old else 0) + 1,
                    'conclusion': conclusion, 'reason': reason, 'remark': remark, 'consultation': consultation,
                    'caseId': case_id, 'actor': actor, 'at': now()}
            if old:
                db.execute('UPDATE bi_risk_order_reviews SET version=?,case_id=?,body=? WHERE order_id=? AND issue_date=?',
                           (body['version'], case_id, encoded(body), *key))
            else:
                db.execute('INSERT INTO bi_risk_order_reviews (order_id,issue_date,version,case_id,body) VALUES(?,?,?,?,?)',
                           (*key, body['version'], case_id, encoded(body)))
            service._event(db, case_id, actor, 'review', old, body, reason)
            if case_id:
                case_ids.append(case_id)
        return {'count': len(items), 'caseId': case_ids[0] if len(case_ids) == 1 else None, 'caseIds': case_ids, 'casePool': case.get('disposition') if len(items) == 1 and case else None}
    return service._transaction(actor, payload, save)


def update(service, actor, case_id, payload):
    def save(db):
        before = service._case(db, case_id, True)
        if before['version'] != version(payload.get('version')):
            raise FlowError('案例已被修改，请刷新后重新填写', 409)
        note = text(payload.get('note'), 2000, '跟进或认定依据')
        body = {**before, **{k: payload.get(k, before.get(k)) for k in ('conclusion', 'disposition', 'state', 'consultation', 'assignee', 'nextStep', 'nextAt', 'problemType', 'cause', 'responsibility', 'remark')}}
        body['workflowVersion'] = 3
        choice(body['conclusion'], ('no_issue', 'problem'), '人工结论')
        choice(body['disposition'], ('pending', 'included', 'excluded'), '差错认定')
        choice(body['state'], ('todo', 'following', 'waiting', 'done'), '跟进状态')
        if body['conclusion'] == 'no_issue':
            body['state'] = 'done'
            body['disposition'] = 'excluded' if before['disposition'] in ('included', 'excluded') else 'pending'
        if body['disposition'] == 'excluded' and before['disposition'] not in ('included', 'excluded'):
            raise FlowError('不计入差错必须从计入差错池转入')
        if body['conclusion'] == 'problem' and body['disposition'] == 'pending' and body['state'] == 'done':
            raise FlowError('待认定问题须先核实无问题或确认计入差错，不能直接完成')
        if before['disposition'] in ('included', 'excluded') and body['disposition'] == 'pending' and body['conclusion'] == 'problem':
            raise FlowError('已认定案例不能退回待认定池，请调整计入或不计入差错')
        body['consultation'] = choice(body.get('consultation') or 'pending', ('pending', 'consulted'), '咨询状态') if body['conclusion'] == 'problem' else None
        for k, limit, label in (('assignee',80,'负责人'),('nextStep',1000,'下一步'),('problemType',500,'问题类型'),('cause',500,'原因'),('responsibility',500,'责任归属'),('remark',2000,'备注')):
            body[k] = optional(body.get(k), limit, label)
        if body.get('nextAt'):
            from datetime import datetime
            from zoneinfo import ZoneInfo
            try:
                dt = datetime.fromisoformat(str(body['nextAt']))
                body['nextAt'] = dt.replace(tzinfo=dt.tzinfo or ZoneInfo('Asia/Shanghai')).isoformat(timespec='minutes')
            except (TypeError, ValueError):
                raise FlowError('下次跟进时间无效') from None
        else:
            body['nextAt'] = None
        if body['state'] == 'done':
            body['nextAt'] = None
        action = payload.get('libraryAction')
        if action:
            choice(action, ('special', 'firstSeen'), '案例归档操作')
            if action == 'firstSeen' and not before.get('special'):
                raise FlowError('请先从特殊案例中核对，再转为首次出现')
            body.update(special=action == 'special', firstSeen=action == 'firstSeen', specialReason=note)
        rows = db.execute('SELECT order_id,issue_date,body FROM bi_risk_order_reviews WHERE case_id=? ORDER BY order_id,issue_date FOR UPDATE', (case_id,)).fetchall()
        recognition_changed = any(body[k] != before.get(k) for k in ('conclusion','disposition')) or (body['state'] == 'done' and before['state'] != 'done')
        for row in rows:
            old = json.loads(row['body'])
            if recognition_changed:
                current = service._snapshot(db, row['order_id'], str(row['issue_date'])[:10], True)
                if current['resultId'] != old['resultId']:
                    raise FlowError('关联订单证据已变化，请先重新核实后再认定或完成', 409)
            old_consultation = (old.get('consultation') or 'pending') if old.get('conclusion') == 'problem' else None
            if old.get('conclusion') == body['conclusion'] and old_consultation == body['consultation'] and (old.get('remark') or '') == body['remark']:
                continue  # Recognition/archive events do not pretend to be a new human check.
            after = {**old, 'workflowVersion':3, 'conclusion':body['conclusion'], 'consultation':body['consultation'], 'remark':body['remark'], 'version':old['version']+1, 'actor':actor, 'at':now()}
            if body['conclusion'] != old['conclusion']:
                after['reason'] = note
            db.execute('UPDATE bi_risk_order_reviews SET version=?,body=? WHERE order_id=? AND issue_date=?', (after['version'],encoded(after),row['order_id'],str(row['issue_date'])[:10]))
            service._event(db, case_id, actor, 'review_sync', old, after, note)
        body.update(version=before['version']+1, updatedAt=now(), wasIncluded=before.get('wasIncluded',False) or before['disposition']=='included' or body['disposition']=='included')
        service._save_case(db,body)
        service._event(db,case_id,actor,'followup',before,body,note)
        return body
    return service._transaction(actor,payload,save)
