"""Read current rule candidates only. Not a historical rule-matching engine."""
from .risk_order_evidence import RiskOrderEvidenceService, EvidenceError, _rows
from .risk_loss_threshold_config import identify_thresholds
from .risk_rule_priority import priority, priority_key, conditions, TEXT_FIELDS, VALUE_FIELDS


class RiskIssueRuleConfigs:
    def __init__(self, config):
        self.config = config

    def read(self, platform=None, group=None, rule_id=None, airline=None, page=None, page_size='20'):
        import re
        platform = platform.strip() or None if isinstance(platform, str) else platform or None
        airline = airline.strip() or None if isinstance(airline, str) else airline or None
        rule_id = rule_id.strip() or None if isinstance(rule_id, str) else rule_id
        group = group or '出票盈亏配置'
        if platform is not None and (not isinstance(platform,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',platform)):
            raise EvidenceError("平台须为有效编码")
        if group is not None and group != '出票盈亏配置':
            raise EvidenceError("不支持的规则大类")
        if airline is not None and (not isinstance(airline,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',airline)):
            raise EvidenceError('航司须为有效编码')
        if rule_id is not None:
            from .risk_order_evidence import order_id
            try:rule_id = str(order_id(rule_id))
            except EvidenceError:raise EvidenceError('规则ID须为有效的正整数标识，不支持名称或模糊匹配') from None
        from .risk_verification_overview import _integer
        number = _integer(page, '页码', 100000) if page is not None else None
        size = _integer(page_size, '每页数量', 100)
        clauses = ''
        params = ['RB01','SYS_RULE_GROUP_TYPE_ISSUE']
        groups = ('出票盈亏配置',)
        params.extend(groups)
        if platform:
            clauses = " AND (r.ota_code REGEXP %s OR r.ota_code='' OR r.ota_code IS NULL)"
            params.append(f'(^|[,;/|]){platform}($|[,;/|])')
        if airline:
            clauses += " AND (r.airline REGEXP %s OR r.airline='' OR r.airline IS NULL)"
            params.append(f'(^|[,;/|]){airline}($|[,;/|])')
        if rule_id:
            clauses += ' AND r.id=%s'
            params.append(rule_id)
        reader = RiskOrderEvidenceService(self.config)
        connection = cursor = None
        try:
            connection = reader._connect()
            cursor = connection.cursor()
            cursor.execute("SET time_zone='+08:00'")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SELECT "+','.join('r.'+field for field in (*TEXT_FIELDS,*VALUE_FIELDS,'flight_number'))+""",r.id,r.rule_name,r.rule_type,r.rule_group_type,r.status,
                r.start_time,r.end_time,r.update_time,r.version,
                LEFT(r.rule_notes,8001) AS rule_notes,LEFT(r.ext_json,8001) AS ext_json
                FROM base_issue_match_rule r
                WHERE r.rule_business_type=%s AND r.status=1 AND (r.start_time IS NULL OR r.start_time<=CURRENT_TIMESTAMP) AND (r.end_time IS NULL OR r.end_time>=CURRENT_TIMESTAMP) AND EXISTS (
                  SELECT 1 FROM system_com_type_det d WHERE d.det_code=r.rule_group_type
                    AND d.parent_code=%s AND d.det_cname IN (""" + ','.join(['%s']*len(groups)) + "))" + clauses + " ORDER BY r.update_time DESC,r.id DESC LIMIT 1001", tuple(params))
            rows = _rows(cursor)
            if len(rows) > 1000:
                raise EvidenceError("当前有效出票盈亏配置超过1000条，需先明确筛选范围；不返回截断规则集",413)
            for row in rows:
                row['id']=str(row['id'])
                try:
                    priority_key(row)
                    row.update(priority(row));row['conditions']=conditions(row)
                    row['priorityStatus']='ready'
                except (ValueError,TypeError,AttributeError):
                    row.update(weight=None,weightFields=[],conditions=[],priorityStatus='invalid')
                row['contentTruncated'] = any(len(str(row.get(key) or '')) > 8000 for key in ('rule_notes','ext_json'))
                row['segmentThresholds'] = identify_thresholds(row.get('rule_type'),row.get('ext_json')) if not row['contentTruncated'] else {'status':'truncated','values':{},'usedForCalculation':False}
                for key in ('rule_notes','ext_json'):
                    if row.get(key): row[key] = str(row[key])[:8000]
            ready=[row for row in rows if row['priorityStatus']=='ready']
            ready.sort(key=priority_key,reverse=True)
            invalid=[row for row in rows if row['priorityStatus']!='ready']
            rows=ready+invalid
            for index,row in enumerate(ready,1):row['priorityPosition']=index
            total=len(rows)
            return {'items':rows[(number-1)*size:number*size] if number is not None else rows,'total':total,'page':number,'pageSize':size,'useForCalculation':False,'scope':{'platform':platform,'airline':airline,'ruleId':rule_id,'group':group,'status':1,'effectiveNow':True},
                    'notice':'仅展示当前启用且在有效期内的出票盈亏配置，按ERP权重、更新时间、规则ID降序。候选顺序不代表某张票实际命中；盈利规则不参与亏损阈值计算。自动核实另按出票时配置、单票段数和匹配范围取值；历史或条件无法可靠还原时证据不足，不用当前值顶替。此候选查询不读取订单或配置变更日志。'}
        finally:
            if connection is not None:
                try: connection.rollback()
                finally: reader._close(cursor,connection)

    def read_identifiers(self, identifiers):
        """Exact original rule identities, including disabled/expired rows; observation only."""
        from .risk_order_evidence import order_id
        from .risk_historical_threshold import SAFE_FIELDS
        ids = sorted({str(order_id(value)) for value in identifiers})
        if not ids or len(ids)>100:
            raise EvidenceError('最新值观察需要1至100个明确关联的规则ID')
        reader=RiskOrderEvidenceService(self.config); connection=cursor=None
        try:
            connection=reader._connect();cursor=connection.cursor()
            cursor.execute("SET time_zone='+08:00'")
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute('SELECT CURRENT_TIMESTAMP(6) AS observed_at')
            observed=_rows(cursor)[0]['observed_at']
            cursor.execute('SELECT '+','.join('r.'+field for field in SAFE_FIELDS if field!='ext_json')+
                           ',LEFT(r.ext_json,8001) AS ext_json FROM base_issue_match_rule r WHERE r.rule_business_type=%s AND r.id IN ('+','.join('%s' for _ in ids)+')', ('RB01',*ids))
            rows=_rows(cursor)
            for row in rows:
                row['id']=str(row['id'])
                row['contentTruncated']=len(str(row.get('ext_json') or ''))>8000
                if row['contentTruncated']:row['ext_json']=None
            return {'observedAt':str(observed),'source':'ERP.base_issue_match_rule','items':rows}
        finally:
            if connection is not None:
                try:connection.rollback()
                finally:reader._close(cursor,connection)
