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
        actual_reason = optional(payload.get('actualProfitReason'), 200, '实际盈亏原因')
        disposition = choice(payload.get('initialDisposition', 'pending'), ('pending', 'included'), '差错认定')
        direct = conclusion == 'problem' and disposition == 'included'
        if conclusion == 'problem' and not actual_reason and ('actualProfitReason' in payload or direct):
            raise FlowError('请填写实际盈亏原因')
        seen, case_ids = set(), []
        for item in sorted(items, key=lambda i: (str(i.get('orderId')), str(i.get('issueDate')))):
            case_id = item.get('caseId')
            case = service._case(db, case_id, True) if case_id else None
            current = service._snapshot(db, item.get('orderId'), item.get('issueDate'), True)
            key = (current['orderId'], current['issueDate'])
            if key in seen:
                raise FlowError('订单重复')
            seen.add(key)
            metadata = db.execute('''SELECT o.ota_order_no,o.order_no,o.ota_code,o.profit_reason_type,s.synced_at
                FROM bi_risk_order_day o LEFT JOIN bi_risk_sync_day s ON s.issue_date=o.issue_date AND s.etl_run_id=o.etl_run_id
                WHERE o.order_id=? AND o.issue_date=?''', key).fetchone()
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
                if direct and case['state'] == 'done' and case['disposition'] != 'included':
                    raise FlowError('已完结案例请在案例跟进中调整差错认定', 409)
                case.update(workflowVersion=3, conclusion=conclusion, consultation=consultation, remark=remark,
                            version=case['version'] + 1, updatedAt=now())
                if conclusion == 'problem' and actual_reason:
                    case.update(actualProfitReason=actual_reason, title=actual_reason)
                if conclusion == 'no_issue':
                    case.update(state='done', disposition='excluded', nextAt=None, nextStep=reason,
                                wasIncluded=case.get('wasIncluded', False) or case['disposition'] == 'included')
                elif before_case['conclusion'] != 'problem':
                    case.update(disposition='pending', state='todo', nextAt=None, nextStep=reason)
                if direct:
                    case.update(disposition='included', state='done', nextAt=None, nextStep=reason, wasIncluded=True)
                if case.get('recognitionSource') == 'reason_rule':
                    case['recognitionSource'] = 'manual'
                service._save_case(db, case)
                service._event(db, case_id, actor, 'recognition', before_case, case, reason)
            elif conclusion == 'problem':
                case_id = uuid.uuid4().hex
                state = 'done' if direct else 'todo'
                case = dict(id=case_id, workflowVersion=3, version=1, title=actual_reason or '未记录实际盈亏原因',
                            actualProfitReason=actual_reason, conclusion='problem', disposition=disposition, state=state, consultation=consultation,
                            remark=remark, assignee=actor, nextAt=None, nextStep=reason, firstSeen=False, special=False, wasIncluded=direct,
                            specialReason='', problemType='', cause=reason, responsibility='', createdAt=now(), updatedAt=now())
                db.execute('INSERT INTO bi_risk_followup_cases (id,version,conclusion,disposition,state,assignee,next_at,first_seen,special,body,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (case_id, 1, 'problem', disposition, state, actor, None, 0, 0, encoded(case), case['updatedAt']))
            body = {**current, 'otaOrderNo': metadata.get('ota_order_no'), 'businessOrderNo': metadata.get('order_no'),
                    'otaCode': metadata.get('ota_code'), 'workflowVersion': 3, 'version': (old['version'] if old else 0) + 1,
                    'conclusion': conclusion, 'reason': reason, 'remark': remark, 'consultation': consultation,
                    'caseId': case_id, 'actor': actor, 'at': now()}
            if case_id:
                first_reason = (old or {}).get('firstProfitReason')
                if old and 'firstProfitReason' not in old and old.get('recognitionSource') == 'reason_rule':
                    first_reason = old.get('routingReason')
                if not (old or {}).get('caseId'):
                    first_reason = metadata.get('profit_reason_type')
                body.update(firstProfitReason=first_reason, latestProfitReason=metadata.get('profit_reason_type'),
                            latestReasonSyncedAt=str(metadata['synced_at']) if metadata.get('synced_at') else None,
                            actualProfitReason=case.get('actualProfitReason'))
            if old:
                db.execute('UPDATE bi_risk_order_reviews SET version=?,case_id=?,body=? WHERE order_id=? AND issue_date=?',
                           (body['version'], case_id, encoded(body), *key))
            else:
                db.execute('INSERT INTO bi_risk_order_reviews (order_id,issue_date,version,case_id,body) VALUES(?,?,?,?,?)',
                           (*key, body['version'], case_id, encoded(body)))
            service._event(db, case_id, actor, 'direct_error' if direct else 'review', old,
                           {**body, 'disposition': disposition, 'state': 'done'} if direct else body, reason)
            if case_id:
                case_ids.append(case_id)
        return {'count': len(items), 'caseId': case_ids[0] if len(case_ids) == 1 else None, 'caseIds': case_ids, 'casePool': case.get('disposition') if len(items) == 1 and case else None}
    return service._transaction(actor, payload, save)


def update(service, actor, case_id, payload):
    def save(db):
        before = service._case(db, case_id, True)
        if before['version'] != version(payload.get('version')):
            raise FlowError('案例已被修改，请刷新后重新填写', 409)
        body = {**before, **{k: payload.get(k, before.get(k)) for k in ('conclusion', 'disposition', 'state', 'consultation', 'nextStep', 'nextAt', 'problemType', 'cause', 'responsibility', 'remark')}}
        body['workflowVersion'] = 3
        choice(body['conclusion'], ('no_issue', 'problem'), '人工结论')
        choice(body['disposition'], ('pending', 'included', 'excluded'), '差错认定')
        choice(body['state'], ('todo', 'following', 'waiting', 'done'), '跟进状态')
        action = payload.get('libraryAction')
        note = optional(payload.get('note'), 2000, '完结说明') if body['state'] == 'done' and not action else text(payload.get('note'), 2000, '跟进或归档说明')
        if not action and body['conclusion'] == 'no_issue':
            body['state'] = 'done'
            body['disposition'] = 'excluded'
        if before['state'] == 'done' and body['state'] != 'done':
            raise FlowError('已完结案例只能调整认定；重新核查请从订单证据进入')
        if body['disposition'] in ('included', 'excluded') and body['disposition'] != before['disposition'] and body['state'] != 'done':
            raise FlowError('保存差错认定时须完结跟进')
        if body['conclusion'] == 'problem' and body['disposition'] == 'pending' and body['state'] == 'done':
            raise FlowError('完结跟进须选择计入差错或不计入差错')
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
            if not note:
                note = '完结跟进：计入差错' if body['disposition'] == 'included' else '完结跟进：不计入差错'
        if action:
            choice(action, ('special', 'firstSeen'), '案例归档操作')
            if action == 'firstSeen' and not before.get('special'):
                raise FlowError('请先从特殊案例中核对，再转为首次出现')
            body.update(special=action == 'special', firstSeen=action == 'firstSeen', specialReason=note)
        recognition_changed = any(body[k] != before.get(k) for k in ('conclusion','disposition')) or (body['state'] == 'done' and before['state'] != 'done')
        snapshots = {}
        if recognition_changed:
            # Match publication's catalog-before-review lock order.
            keys = db.execute('SELECT order_id,issue_date FROM bi_risk_order_reviews WHERE case_id=? ORDER BY issue_date,order_id', (case_id,)).fetchall()
            for row in keys:
                key = (row['order_id'], str(row['issue_date'])[:10])
                snapshots[key] = service._snapshot(db, *key, lock=True)['resultId']
        rows = db.execute('SELECT order_id,issue_date,body FROM bi_risk_order_reviews WHERE case_id=? ORDER BY issue_date,order_id FOR UPDATE', (case_id,)).fetchall()
        for row in rows:
            old = json.loads(row['body'])
            if recognition_changed and snapshots.get((row['order_id'], str(row['issue_date'])[:10])) != old['resultId']:
                raise FlowError('订单证据已变化，请先重新核实后再认定或完结', 409)
            old_consultation = (old.get('consultation') or 'pending') if old.get('conclusion') == 'problem' else None
            if old.get('conclusion') == body['conclusion'] and old_consultation == body['consultation'] and (old.get('remark') or '') == body['remark']:
                continue  # Recognition/archive events do not pretend to be a new human check.
            after = {**old, 'workflowVersion':3, 'conclusion':body['conclusion'], 'consultation':body['consultation'], 'remark':body['remark'], 'version':old['version']+1, 'actor':actor, 'at':now()}
            if body['conclusion'] != old['conclusion']:
                after['reason'] = note
                after['recognitionSource'] = 'manual'
                body['recognitionSource'] = 'manual'
            db.execute('UPDATE bi_risk_order_reviews SET version=?,body=? WHERE order_id=? AND issue_date=?', (after['version'],encoded(after),row['order_id'],str(row['issue_date'])[:10]))
            service._event(db, case_id, actor, 'review_sync', old, after, note)
        body.update(version=before['version']+1, updatedAt=now(), wasIncluded=before.get('wasIncluded',False) or before['disposition']=='included' or body['disposition']=='included')
        service._save_case(db,body)
        service._event(db,case_id,actor,'followup',before,body,note)
        return body
    return service._transaction(actor,payload,save)
