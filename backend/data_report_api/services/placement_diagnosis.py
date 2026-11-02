"""Route/platform receipt diagnostics based on deployed policies, including zero-hit policies."""
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
import json
import logging

from .smart_placement import (
    SmartPlacementService, SmartPlacementUnavailable, PlacementChangeConflict,
    _actor, _dict_rows, _dict_row, _require_permission, _public_row, _text, _datetime_value,
)
from ..time_utils import business_now_naive

REASONS = {'PENDING_CHECK', 'NOT_VISIBLE', 'RANKING', 'PRICE', 'CONDITIONS', 'INVENTORY', 'OTHER'}
FOLLOWUP_STATUSES = {'OPEN', 'OBSERVING', 'ADJUSTED', 'SUSPEND_SUGGESTED', 'RESOLVED'}
PROBLEMS = {'ALL', 'PLATFORM_GAP', 'ALL_NO_ORDERS', 'INTERRUPTED', 'DUE', 'DATA_CHECK', 'OBSERVING'}
MAX_POLICIES = 2000
MAX_RECEIPTS = 100000
LOGGER = logging.getLogger(__name__)


def require_menu(user):
    _actor(user)
    if not (user.get('is_admin') or user.get('isAdmin') or 'smart.placement.policies' in (user.get('menu_codes') or user.get('menuCodes') or [])):
        raise PermissionError('当前账号没有投放政策菜单权限')


def stamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            pass
    return None


def followup_value(row):
    try:
        value = json.loads(row.get('followup_json') or '{}')
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def observation(row):
    starts = [stamp(row.get(key)) for key in ('actual_placement_at', 'effective_start_at', 'monitoring_started_at', 'rule_start_at', 'version_created_at', 'resumed_at', 'order_start_date')]
    starts = [value for value in starts if value]
    return max(starts) if starts else None


def scope_values(row):
    actual = row.get('execution_id') and row['task_status'] in {'MONITORING', 'ENDED', 'CLOSED'}
    result = {}
    for key in ('airline_code', 'departure_type', 'departure_code', 'arrival_type', 'arrival_code', 'segment_type', 'route_text'):
        result[key] = row.get(('actual_' if actual else '') + key)
        if actual and key in {'airline_code', 'segment_type'}:
            result[key] = result[key] or row.get(key)
        if result[key] and key.endswith(('_type', '_code')) and key != 'segment_type':
            result[key] = str(result[key]).upper()
    result['journey_type'] = {'单程': 'ONE_WAY', '往返': 'ROUND_TRIP', '多程': 'MULTI_CITY', '多城市': 'MULTI_CITY'}.get(row.get('journey_type'), row.get('journey_type'))
    if result['segment_type'] == '直飞': result['segment_type'] = '直达'
    return result


def platform_name(row):
    actual = row.get('execution_id') and row['task_status'] in {'MONITORING', 'ENDED', 'CLOSED'}
    return (row.get('actual_platform_name') if actual else None) or row['platform_name']


def row_key(values):
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def build_matrix(policies, receipt_rows, *, now, days, healthy):
    """No rank/demand inference; missing permissions, stale pipelines and unknown times stay explicit."""
    window_start = now - timedelta(days=days)
    receipts = defaultdict(list)
    for receipt in receipt_rows:
        receipts[int(receipt['execution_id'])].append(receipt)
    groups = {}
    for source in policies:
        row = dict(source)
        scope = scope_values(row)
        key = row_key(scope)
        group = groups.setdefault(key, {'key': key, **_public_row(scope), 'cells': {}, 'diagnosis': 'OBSERVING', 'due': False})
        platform = platform_name(row)
        cell = group['cells'].setdefault(platform, {'platform': platform, 'policies': [], '_orders': set(), '_eligible': set()})
        start = observation(row)
        sales_end = stamp(row.get('order_end_date'))
        if sales_end: sales_end += timedelta(days=1) - timedelta(microseconds=1)
        end = min([now, *[value for value in (stamp(row.get('effective_end_at')), stamp(row.get('rule_end_at')), sales_end) if value]])
        state = 'ACTIVE'
        if not row.get('execution_id') or row['task_status'] not in {'MONITORING', 'ENDED', 'CLOSED'}:
            state = 'NOT_PLACED'
        elif row['task_status'] != 'MONITORING':
            state = 'EXPIRED' if end < now else 'PAUSED'
        elif start is None or not row.get('rule_id') or not row.get('version_created_at'):
            state = 'DATA_CHECK'
        elif start > now:
            state = 'SCHEDULED'
        elif end < now:
            state = 'EXPIRED'
        elif row['task_status'] != 'MONITORING' or row.get('rule_status') != 'ACTIVE':
            state = 'PAUSED'
        elif not row.get('order_scope_complete'):
            state = 'RESTRICTED'
        elif not healthy or not stamp(row.get('last_run_at')) or stamp(row['last_run_at']) > now or (now - stamp(row['last_run_at'])).total_seconds() > max(1800, int(row.get('schedule_seconds') or 300) * 3):
            state = 'DATA_CHECK'
        elif stamp(row.get('last_unknown_match_at')) and stamp(row['last_unknown_match_at']) >= start:
            state = 'DATA_CHECK'
        period_orders, eligible = set(), set()
        if row.get('order_scope_complete') and start:
            for receipt in receipts[int(row.get('execution_id') or 0)]:
                order_at = stamp(receipt.get('order_time'))
                if order_at and max(start, window_start) <= order_at <= end:
                    order = (receipt.get('platform_name') or platform, receipt['ota_order_no'])
                    period_orders.add(order)
                    if not receipt.get('assessment_excluded'):
                        eligible.add(order)
        last = stamp(row.get('last_order_at'))
        if last and (not start or last < start or last > end):
            last = None
        age = max(0, (now - start).total_seconds() / 86400) if start else None
        no_order_days = max(0, (now - max([value for value in (start, last) if value])).total_seconds() / 86400) if start else None
        if state == 'ACTIVE':
            if period_orders:
                state = 'RECEIVING'
            elif age is not None and age < days:
                state = 'OBSERVING'
            elif no_order_days is not None and no_order_days >= days:
                state = 'INTERRUPTED' if last else 'NO_ORDERS'
            else:
                state = 'OBSERVING'
        followup = followup_value(row)
        due = bool(followup.get('status') != 'RESOLVED' and stamp(followup.get('nextReviewAt')) and stamp(followup['nextReviewAt']) <= now)
        group['due'] = group['due'] or due
        policy = {'taskId': row['task_id'], 'taskNo': row['task_no'], 'name': row['opportunity_name'],
            'executionId': row.get('execution_id'), 'externalPolicyId': row.get('external_policy_id'), 'state': state,
            'siteName': row.get('actual_site_name') or row.get('site_name'), 'ownerName': row.get('current_assignee_name') or row.get('created_by_name'),
            'observedFrom': start.isoformat(sep=' ') if start else None, 'observedDays': round(age, 2) if age is not None else None,
            'observedUntil': end.isoformat(sep=' '),
            'lastOrderAt': last.isoformat(sep=' ') if last else None, 'noOrderDays': round(no_order_days, 2) if no_order_days is not None else None,
            'periodOrderCount': len(period_orders) if row.get('order_scope_complete') else None,
            'assessmentOrderCount': len(eligible) if row.get('order_scope_complete') else None,
            'lastRunAt': str(row.get('last_run_at') or ''), 'followup': followup, 'followupId': int(row.get('followup_id') or 0), 'due': due,
            'followupRecordedBy': row.get('followup_operator'), 'followupRecordedAt': str(row.get('followup_created_at') or ''),
            'conditions': {name: str(row[name]) if row.get(name) is not None else None for name in ('include_cabins', 'exclude_cabins', 'product_type', 'order_source', 'travel_start_date', 'travel_end_date', 'order_start_date', 'order_end_date', 'advance_sale_days', 'flight_nos', 'loss_threshold_min', 'loss_threshold_max')},
            'orderScopeComplete': bool(row.get('order_scope_complete'))}
        cell['policies'].append(policy)
        # Current comparisons count only current monitoring policies. Inactive policies remain in drilldown.
        if row['task_status'] == 'MONITORING' and row.get('rule_status') == 'ACTIVE' and state not in {'SCHEDULED', 'EXPIRED'}:
            cell['_orders'].update(period_orders)
            cell['_eligible'].update(eligible)
    priorities = ['RECEIVING', 'RESTRICTED', 'DATA_CHECK', 'INTERRUPTED', 'NO_ORDERS', 'OBSERVING', 'SCHEDULED', 'PAUSED', 'EXPIRED', 'NOT_PLACED']
    for group in groups.values():
        group['mixedConditions'] = len({json.dumps(policy['conditions'], default=str, sort_keys=True) for cell in group['cells'].values() for policy in cell['policies']}) > 1
        for cell in group['cells'].values():
            states = [item['state'] for item in cell['policies']]
            cell['state'] = next(value for value in priorities if value in states)
            cell['periodOrderCount'] = len(cell.pop('_orders')) if 'RESTRICTED' not in states else None
            cell['assessmentOrderCount'] = len(cell.pop('_eligible')) if 'RESTRICTED' not in states else None
            cell['lastOrderAt'] = max((item['lastOrderAt'] for item in cell['policies'] if item['lastOrderAt']), default=None)
            cell['mixedConditions'] = len({json.dumps(item['conditions'], default=str, sort_keys=True) for item in cell['policies']}) > 1
        states = [cell['state'] for cell in group['cells'].values()]
        comparable = [state for state in states if state not in {'NOT_PLACED', 'PAUSED', 'EXPIRED', 'SCHEDULED'}]
        group['hasInterruption'] = 'INTERRUPTED' in states
        bad = {'NO_ORDERS', 'INTERRUPTED'}
        if 'RECEIVING' in states and any(state in bad for state in states):
            group['diagnosis'] = 'PLATFORM_GAP'
        elif comparable and all(state in bad for state in comparable):
            group['diagnosis'] = 'ALL_NO_ORDERS'
        elif 'INTERRUPTED' in states:
            group['diagnosis'] = 'INTERRUPTED'
        elif any(state in {'DATA_CHECK', 'RESTRICTED'} for state in states):
            group['diagnosis'] = 'DATA_CHECK'
        elif 'RECEIVING' in states and not any(state in bad for state in states):
            group['diagnosis'] = 'RECEIVING'
        elif any(state in bad for state in states):
            group['diagnosis'] = 'PARTIAL_NO_ORDERS'
        else:
            group['diagnosis'] = 'OBSERVING'
    rank = {'PLATFORM_GAP': 0, 'ALL_NO_ORDERS': 1, 'INTERRUPTED': 2, 'PARTIAL_NO_ORDERS': 3, 'DATA_CHECK': 4, 'OBSERVING': 5, 'RECEIVING': 6}
    return sorted(groups.values(), key=lambda row: (not row['due'], rank[row['diagnosis']], row['key']))


class PlacementDiagnosisService:
    def __init__(self, config, *, placement=None):
        self.placement = placement or SmartPlacementService(config)

    def list(self, user, values):
        require_menu(user)
        days = int(values.get('days') or 7)
        if days not in {3, 7, 14, 30}:
            raise ValueError('观察窗口只支持3、7、14或30天')
        problem = values.get('problem') or 'ALL'
        if problem not in PROBLEMS:
            raise ValueError('诊断筛选不支持')
        page = max(1, int(values.get('page') or 1)); size = max(1, min(50, int(values.get('pageSize') or 20)))
        service = self.placement
        visible, params = service._visibility_condition(user)
        menu_codes = user.get('menu_codes') or user.get('menuCodes') or []
        has_orders = bool(user.get('is_admin') or user.get('isAdmin') or 'smart.placement.orders' in menu_codes)
        complete, complete_params = service._order_visibility_condition(user, 'diagnostic_scope') if has_orders else ('1=0', [])
        # A synthetic match without an attention owner tests whole-task order coverage, not one visible receipt.
        complete = complete.replace('diagnostic_scope.attention_owner_id', 'NULL').replace('diagnostic_scope.task_id', 't.id')
        where = ['t.is_deleted=0', visible]
        if values.get('airline'):
            where.append("(CASE WHEN e.id IS NOT NULL AND t.status IN ('MONITORING','ENDED','CLOSED') THEN COALESCE(e.airline_code,t.airline_code) ELSE t.airline_code END)=%s")
            params.append(_text(values['airline'], '航司', 32).upper())
        if values.get('keyword'):
            token = '%' + _text(values['keyword'], '航线/机会关键字', 100) + '%'
            where.append('(t.opportunity_name LIKE %s OR t.departure_code LIKE %s OR t.arrival_code LIKE %s OR e.departure_code LIKE %s OR e.arrival_code LIKE %s)')
            params.extend([token] * 5)
        table = service._table
        connection = cursor = None
        now = business_now_naive()
        try:
            connection = service.source.connect(); cursor = connection.cursor()
            cursor.execute(f"""SELECT t.id task_id,t.task_no,t.opportunity_name,t.status task_status,
                t.platform_name,t.site_name,t.airline_code,t.departure_type,t.departure_code,t.arrival_type,t.arrival_code,
                t.segment_type,t.journey_type,t.route_text,t.monitoring_started_at,t.current_assignee_name,t.created_by_name,
                t.travel_start_date,t.travel_end_date,t.order_start_date,t.order_end_date,t.advance_sale_days,e.id execution_id,e.external_policy_id,e.actual_placement_at,
                e.effective_start_at,e.effective_end_at,e.platform_name actual_platform_name,e.site_name actual_site_name,
                e.airline_code actual_airline_code,e.departure_type actual_departure_type,e.departure_code actual_departure_code,
                e.arrival_type actual_arrival_type,e.arrival_code actual_arrival_code,e.segment_type actual_segment_type,e.route_text actual_route_text,
                COALESCE(NULLIF(e.include_cabins,''),t.include_cabins) include_cabins,
                COALESCE(NULLIF(e.exclude_cabins,''),t.exclude_cabins) exclude_cabins,
                COALESCE(NULLIF(e.product_type,''),t.product_type) product_type,e.order_source,
                COALESCE(NULLIF(e.flight_nos,''),t.flight_nos) flight_nos,
                CASE WHEN e.id IS NULL THEN t.loss_threshold_min ELSE e.loss_threshold_min END loss_threshold_min,
                CASE WHEN e.id IS NULL THEN t.loss_threshold_max ELSE e.loss_threshold_max END loss_threshold_max,
                r.id rule_id,r.status rule_status,r.effective_start_at rule_start_at,r.effective_end_at rule_end_at,r.last_run_at,r.schedule_seconds,
                v.created_at version_created_at,
                (SELECT MAX(ro.created_at) FROM {table('monitor_rule_operation_log')} ro WHERE ro.rule_id=r.id AND ro.from_status='PAUSED' AND ro.to_status='ACTIVE') resumed_at,
                CASE WHEN {complete} THEN 1 ELSE 0 END order_scope_complete,
                f.id followup_id,f.detail_json followup_json,f.operator_name followup_operator,f.created_at followup_created_at
                FROM {table('smart_placement_task')} t
                LEFT JOIN {table('smart_placement_execution')} e ON e.id=(SELECT MAX(ex.id) FROM {table('smart_placement_execution')} ex WHERE ex.task_id=t.id AND ex.execution_result='SUCCESS')
                LEFT JOIN {table('monitor_rule')} r ON r.source_business_type='SMART_PLACEMENT_EXECUTION' AND r.source_business_id=e.id AND r.source_parent_id=t.id
                LEFT JOIN {table('monitor_rule_version')} v ON v.id=r.current_version_id
                LEFT JOIN {table('smart_placement_operation_log')} f ON f.id=(SELECT MAX(fl.id) FROM {table('smart_placement_operation_log')} fl WHERE fl.task_id=t.id AND fl.action_code='ROUTE_FOLLOWUP')
                WHERE {' AND '.join(where)} ORDER BY t.id DESC LIMIT {MAX_POLICIES + 1}""", tuple([*complete_params, *params]))
            policies = _dict_rows(cursor, list(cursor.fetchall()))
            if len(policies) > MAX_POLICIES:
                raise ValueError('匹配政策超过2000条，请按航司或航线缩小范围；本次未生成部分诊断')
            platforms = sorted({platform_name(row) for row in policies})
            if len(platforms) > 40:
                raise ValueError('平台超过40个，请缩小查询范围')
            cursor.execute(f"""SELECT job_type,status,finished_at FROM {table('monitor_run_log')}
                WHERE status<>'SKIPPED' AND started_at>=%s AND
                ((job_type='RULE_MATCH' AND source_code='RULE_MATCH:RT_ORDER_FEATURE') OR
                 (job_type='FEATURE_ETL' AND source_code LIKE 'BI_ISSUE_HOLD_PNR_DAY:%%')) ORDER BY id DESC LIMIT 50""", (now - timedelta(minutes=30),))
            health = {}
            for run in _dict_rows(cursor, list(cursor.fetchall())):
                health.setdefault(run['job_type'], {'status': run['status'], 'finishedAt': str(run.get('finished_at') or '')})
            healthy = all(health.get(kind, {}).get('status') == 'SUCCESS' and stamp(health[kind]['finishedAt'])
                          and now - timedelta(minutes=30) <= stamp(health[kind]['finishedAt']) <= now for kind in ('FEATURE_ETL', 'RULE_MATCH'))
            execution_rows = {int(row['execution_id']): row for row in policies if row.get('execution_id') and row.get('order_scope_complete')}
            receipts = []
            if execution_rows:
                ids = list(execution_rows)
                task_ids = sorted({row['task_id'] for row in execution_rows.values()})
                visibility, order_params = service._order_visibility_condition(user)
                cursor.execute(f"""SELECT m.execution_id,MAX(CASE WHEN m.order_time<=%s THEN m.order_time END) last_order_at,
                    MAX(CASE WHEN m.order_time IS NULL THEN m.matched_at END) last_unknown_match_at
                    FROM {table('smart_placement_order_match')} m WHERE m.task_id IN ({','.join(['%s'] * len(task_ids))})
                    AND m.execution_id IN ({','.join(['%s'] * len(ids))}) AND {visibility}
                    GROUP BY m.execution_id""", tuple([now, *task_ids, *ids, *order_params]))
                metrics = {int(row['execution_id']): row for row in _dict_rows(cursor, list(cursor.fetchall()))}
                for eid, row in execution_rows.items():
                    row.update(metrics.get(eid, {}))
                cursor.execute(f"""SELECT DISTINCT m.execution_id,m.platform_name,m.ota_order_no,m.order_time,
                    COALESCE(x.is_excluded,0) assessment_excluded
                    FROM {table('smart_placement_order_match')} m
                    LEFT JOIN {table('smart_placement_order_exclusion')} x ON x.platform_name=m.platform_name AND x.ota_order_no=m.ota_order_no
                    WHERE m.task_id IN ({','.join(['%s'] * len(task_ids))}) AND m.execution_id IN ({','.join(['%s'] * len(ids))})
                    AND m.order_time>=%s AND m.order_time<=%s AND {visibility}
                    ORDER BY m.execution_id LIMIT {MAX_RECEIPTS + 1}""", tuple([*task_ids, *ids, now - timedelta(days=days), now, *order_params]))
                receipts = _dict_rows(cursor, list(cursor.fetchall()))
                if len(receipts) > MAX_RECEIPTS:
                    raise ValueError('窗口内命中明细超过10万条，请缩小查询范围；本次未生成部分诊断')
            rows = build_matrix(policies, receipts, now=now, days=days, healthy=healthy)
            summary = {key: sum(row['diagnosis'] == key for row in rows) for key in ('PLATFORM_GAP', 'ALL_NO_ORDERS', 'INTERRUPTED', 'DATA_CHECK')}
            summary['INTERRUPTED'] = sum(row['hasInterruption'] for row in rows)
            summary.update(total=len(rows), due=sum(row['due'] for row in rows))
            filtered = [row for row in rows if problem == 'ALL' or (problem == 'DUE' and row['due']) or (problem == 'INTERRUPTED' and row['hasInterruption']) or row['diagnosis'] == problem]
            return {'rows': filtered[(page-1)*size:page*size], 'total': len(filtered), 'page': page, 'pageSize': size,
                'platforms': platforms, 'summary': summary, 'days': days, 'asOf': now.isoformat(sep=' '), 'windowStart': (now - timedelta(days=days)).isoformat(sep=' '),
                'health': health, 'dataHealthy': healthy, 'scopeNote': '仅比较当前权限内政策及有整任务收单权限的订单；无数据不代表全市场无需求。'}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            LOGGER.exception('Placement route diagnosis failed')
            raise SmartPlacementUnavailable('航线诊断暂不可用，请核对智能投放、考核分类及监控配套表') from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def followup(self, user, task_id, values):
        require_menu(user)
        _require_permission(user, 'smart_placement.orders.attention', '当前账号没有业务跟进权限')
        actor = _actor(user)
        reason = values.get('reason'); status = values.get('status')
        expected = values.get('followupId')
        if not isinstance(reason, str) or not isinstance(status, str) or reason not in REASONS or status not in FOLLOWUP_STATUSES or type(expected) is not int or expected < 0:
            raise ValueError('跟进类型、状态或版本不合法')
        note = _text(values.get('note'), '跟进说明', 1000, required=True)
        review = _datetime_value(values.get('nextReviewAt'), '下次复查时间', required=True) if status != 'RESOLVED' else None
        now = business_now_naive()
        if review and review <= now:
            raise ValueError('下次复查时间必须晚于当前时间')
        payload = {'reason': reason, 'status': status, 'note': note, 'nextReviewAt': review.isoformat(sep=' ') if review else None}
        service = self.placement; table = service._table
        connection = cursor = None
        try:
            connection = service.source.connect(); connection.begin(); cursor = connection.cursor()
            visibility, params = service._visibility_condition(user)
            cursor.execute(f'SELECT t.id,t.current_assignee_name FROM {table("smart_placement_task")} t WHERE t.id=%s AND t.is_deleted=0 AND {visibility} FOR UPDATE', tuple([task_id, *params]))
            task = _dict_row(cursor, cursor.fetchone())
            if not task: raise PermissionError('政策不存在或无权跟进')
            cursor.execute(f"SELECT id,operator_id,detail_json FROM {table('smart_placement_operation_log')} WHERE task_id=%s AND action_code='ROUTE_FOLLOWUP' ORDER BY id DESC LIMIT 1 FOR UPDATE", (task_id,))
            previous = _dict_row(cursor, cursor.fetchone())
            if int(previous['id'] if previous else 0) != expected:
                if previous and int(previous['operator_id']) == actor[0] and json.loads(previous['detail_json']) == payload:
                    connection.commit()
                    return {'id': previous['id'], **payload, 'alreadySaved': True}
                raise PlacementChangeConflict('跟进记录已变化，请刷新后核对；本次未保存')
            service._log(cursor, task_id=task_id, action='ROUTE_FOLLOWUP', actor=actor, note=note, detail=payload)
            result = {'id': int(cursor.lastrowid), **payload, 'alreadySaved': False}
            connection.commit()
            return result
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception('Placement route followup failed')
            raise SmartPlacementUnavailable('跟进保存结果未能确认，请保留输入、刷新记录核对后重试') from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
