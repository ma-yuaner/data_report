"""Read current rule candidates only. Not a historical rule-matching engine."""
from .risk_order_evidence import RiskOrderEvidenceService, EvidenceError, _rows
from .risk_loss_threshold_config import identify_thresholds


class RiskIssueRuleConfigs:
    def __init__(self, config):
        self.config = config

    def read(self, platform=None, group=None):
        import re
        platform = platform or None
        group = group or None
        if platform is not None and (not isinstance(platform,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',platform)):
            raise EvidenceError("平台须为有效编码")
        if group is not None and group not in ('出票盈亏配置','出票规则配置'):
            raise EvidenceError("不支持的规则大类")
        clauses = ''
        params = ['RB01','SYS_RULE_GROUP_TYPE_ISSUE']
        groups = (group,) if group else ('出票盈亏配置','出票规则配置')
        params.extend(groups)
        if platform:
            clauses = " AND (r.ota_code REGEXP %s OR r.ota_code='' OR r.ota_code IS NULL)"
            params.append(f'(^|[,;/|]){platform}($|[,;/|])')
        reader = RiskOrderEvidenceService(self.config)
        connection = cursor = None
        try:
            connection = reader._connect()
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("""SELECT r.id,r.rule_name,r.ota_code,r.ota_site_code,r.rule_type,r.rule_group_type,
                r.start_time,r.end_time,r.update_time,r.version,
                LEFT(r.rule_notes,8001) AS rule_notes,LEFT(r.ext_json,8001) AS ext_json
                FROM base_issue_match_rule r
                WHERE r.rule_business_type=%s AND r.status=1 AND EXISTS (
                  SELECT 1 FROM system_com_type_det d WHERE d.det_code=r.rule_group_type
                    AND d.parent_code=%s AND d.det_cname IN (""" + ','.join(['%s']*len(groups)) + "))" + clauses + " ORDER BY r.update_time DESC,r.id DESC LIMIT 201", tuple(params))
            rows = _rows(cursor)
            if len(rows) > 200:
                raise EvidenceError("当前配置超过200条，需先明确筛选范围；不返回截断规则集",413)
            for row in rows:
                row['contentTruncated'] = any(len(str(row.get(key) or '')) > 8000 for key in ('rule_notes','ext_json'))
                row['segmentThresholds'] = identify_thresholds(row.get('rule_type'),row.get('ext_json')) if not row['contentTruncated'] else {'status':'truncated','values':{},'usedForCalculation':False}
                for key in ('rule_notes','ext_json'):
                    if row.get(key): row[key] = str(row[key])[:8000]
            return {'items':rows,'useForCalculation':False,'scope':{'platform':platform,'group':group},
                    'notice':'这里只展示当前启用配置候选，不代表某张票实际命中。自动核实另按出票时配置、单票段数和匹配范围取值；历史或条件无法可靠还原时证据不足，不用当前值顶替。此候选查询不读取订单或配置变更日志。'}
        finally:
            if connection is not None:
                try: connection.rollback()
                finally: reader._close(cursor,connection)
