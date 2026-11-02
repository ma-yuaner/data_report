"""Manual order classification for assessment; never rewrites business outcomes."""
from ..shared.placement_errors import PlacementChangeConflict

EXCLUSION_TABLE = 'smart_placement_order_exclusion'
REASONS = {'AFTER_SALES', 'DATA_ERROR', 'OTHER'}


def classification_request(values):
    if 'assessmentExcluded' not in values:
        if {'assessmentVersion', 'exceptionReasonCode', 'assessmentNote'} & values.keys():
            raise ValueError('请明确选择正常订单或异常订单')
        return None
    excluded = values['assessmentExcluded']
    version = values.get('assessmentVersion')
    if type(excluded) is not bool or type(version) is not int or version < 0:
        raise ValueError('订单分类或版本不合法，请刷新后重试')
    code = values.get('exceptionReasonCode') if excluded else None
    if excluded and not isinstance(code, str):
        raise ValueError('请选择异常类型')
    code = code.strip() if code else None
    if excluded and code not in REASONS:
        raise ValueError('请选择售后问题、数据异常或其他异常')
    note = values.get('assessmentNote') or ''
    if not isinstance(note, str) or len(note.strip()) > 1000:
        raise ValueError('异常/恢复说明须为不超过1000字的文本')
    note = note.strip()
    if excluded and not note:
        raise ValueError('异常说明不能为空')
    return {'excluded': int(excluded), 'version': version, 'code': code, 'note': note}


def change_classification(service, cursor, match, actor, request, now):
    if request is None:
        return {}
    platform, order_no = match.get('platform_name'), match.get('ota_order_no')
    if not str(platform or '').strip() or not str(order_no or '').strip():
        raise ValueError('订单平台或OTA订单号缺失，无法保存考核分类，请先核对源数据')
    table = service._table(EXCLUSION_TABLE)
    cursor.execute(f"""INSERT IGNORE INTO {table}
        (platform_name,ota_order_no,is_excluded,version,created_by_id,created_by_name,updated_by_id,updated_by_name,created_at,updated_at)
        VALUES (%s,%s,0,0,%s,%s,%s,%s,%s,%s)""",
        (platform, order_no, actor[0], actor[1], actor[0], actor[1], now, now))
    cursor.execute(f'SELECT * FROM {table} WHERE platform_name=%s AND ota_order_no=%s FOR UPDATE', (platform, order_no))
    row = cursor.fetchone()
    before = dict(row) if isinstance(row, dict) else dict(zip((column[0] for column in cursor.description), row)) if row else None
    if not before:
        raise ValueError('订单考核分类暂不可用，请刷新后重试')
    previous = int(before['is_excluded'])
    version = int(before['version'])
    same = (previous == request['excluded'] and (before.get('reason_code') or None) == request['code']
            and (before.get('reason_note') or '') == request['note'])
    if version != request['version'] and not same:
        raise PlacementChangeConflict('订单分类已被其他人修改，请刷新后重新核对；本次未保存')
    if previous and not request['excluded'] and not request['note']:
        raise ValueError('恢复正常订单必须填写恢复原因')
    if same or (not previous and not request['excluded']):
        return {'assessmentExcluded': previous, 'assessmentVersion': version,
                'exceptionReasonCode': before.get('reason_code'), 'assessmentNote': before.get('reason_note'),
                'assessmentUpdatedBy': before.get('updated_by_name'), 'assessmentUpdatedAt': before.get('updated_at')}
    cursor.execute(f"""UPDATE {table} SET is_excluded=%s,reason_code=%s,reason_note=%s,
        source_match_id=%s,version=version+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s
        WHERE id=%s AND version=%s""",
        (request['excluded'], request['code'], request['note'], match['id'], actor[0], actor[1], now, before['id'], version))
    if cursor.rowcount != 1:
        raise PlacementChangeConflict('订单分类版本冲突，请刷新后重试；本次未保存')
    after = {'assessmentExcluded': request['excluded'], 'assessmentVersion': version + 1,
             'exceptionReasonCode': request['code'], 'assessmentNote': request['note'],
             'assessmentUpdatedBy': actor[1], 'assessmentUpdatedAt': now}
    service._log(cursor, task_id=int(match['task_id']), match_id=int(match['id']),
        action='ASSESSMENT_EXCLUDE' if request['excluded'] else 'ASSESSMENT_RESTORE', actor=actor,
        from_status='EXCLUDED' if previous else 'NORMAL', to_status='EXCLUDED' if request['excluded'] else 'NORMAL',
        note=request['note'], detail={'platformName': platform, 'otaOrderNo': order_no,
            'before': {'excluded': previous, 'reasonCode': before.get('reason_code'), 'note': before.get('reason_note'), 'version': version},
            'after': after, 'scope': 'SAME_PLATFORM_AND_OTA_ORDER'})
    return after


def order_count_expression(condition):
    return f"COUNT(DISTINCT CASE WHEN {condition} THEN COALESCE(m.platform_name,'') END, CASE WHEN {condition} THEN m.ota_order_no END)"


def assessment_aggregates():
    primary = "COALESCE(e.is_excluded,0)=0 AND COALESCE(a.attribution_type,'PRIMARY')='PRIMARY'"
    return f"""
        {order_count_expression(primary)} assessment_order_count,
        {order_count_expression('e.is_excluded=1')} abnormal_order_count,
        CASE WHEN COUNT(CASE WHEN {primary} THEN 1 END)=0 THEN 0 ELSE
            SUM(CASE WHEN {primary} THEN COALESCE(o.ticket_count,m.ticket_count) END) END assessment_ticket_count,
        CASE WHEN COUNT(CASE WHEN {primary} THEN 1 END)=0 THEN 0 ELSE
            SUM(CASE WHEN {primary} THEN COALESCE(o.segment_count,m.segment_count) END) END assessment_segment_count,
        CASE WHEN COUNT(CASE WHEN {primary} THEN 1 END)=0 THEN 0 ELSE
            SUM(CASE WHEN {primary} THEN COALESCE(o.estimated_profit_cny,m.estimated_profit_cny) END) END assessment_profit_cny,
        SUM(CASE WHEN {primary} AND o.outcome_status='TICKETED' THEN 1 ELSE 0 END) assessment_ticketed_order_count,
        SUM(CASE WHEN {primary} AND o.smart_participated=1 THEN 1 ELSE 0 END) assessment_participated_count,
        SUM(CASE WHEN {primary} AND o.smart_succeeded=1 THEN 1 ELSE 0 END) assessment_succeeded_count,
        SUM(CASE WHEN {primary} AND o.smart_used=1 THEN 1 ELSE 0 END) assessment_used_count
    """


def assessment_rates(summary):
    ticketed = int(summary.get('assessmentTicketedOrderCount') or 0)
    participated = int(summary.get('assessmentParticipatedCount') or 0)
    succeeded = int(summary.get('assessmentSucceededCount') or 0)
    summary['assessmentParticipationRate'] = round(participated / ticketed, 6) if ticketed else None
    summary['assessmentSuccessRate'] = round(succeeded / participated, 6) if participated else None
