"""Issue-date order-level rollups and drill-down; financial loss is not a review problem."""
from datetime import date, timedelta
import logging

from .risk_order_evidence import EvidenceError, _rows
from .risk_verification_catalog import RiskVerificationCatalog
from .risk_verification_flow import FlowError
from .risk_auto_verification import RiskAutoVerification
from .risk_child_loss import ANCILLARY_REASON, BET_REASONS, NORMAL_REASONS, SUPPORTED_REASONS
from .risk_query_contract import METRIC_JOIN, METRIC_FIELDS, METRIC_PROFIT, period as _period, positive_integer as _integer

LOGGER = logging.getLogger(__name__)
STATES = ("problem", "supported", "insufficient", "reviewing", "unchecked", "failed", "rule_pending", "outdated")
FIELDS = "o.order_id AS id,o.order_no,o.ota_order_no,o.ota_code,o.profit_reason_type,o.create_time,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date"
NOTES = [
    "读取中台ETL目录，不实时扫描ERP；按出票日期限定，跨日或多票均按内部订单ID去重。",
    "数据截止各日最近一次成功同步；查询、翻页和查看详情不触发ERP读取，只有独立清洗任务读取ERP，页面按钮加载已发布结果。",
    "按每日成功发布的当前核实事实统计，不依赖账号加载任务；自动通过可按需人工核实；问题进入案例认定，系统与人工结果分别留存。",
    "清洗读取出票及适用证据，页面不查ERP；相同证据重复清洗保留核实关联，规则或证据改变后旧结论只作历史参考。",
    "未核查、核查中和证据不足不等于没有问题；尚无自动核查结论。",
]


def _stamp(value):
    return None if value is None else str(value).replace(" ", "T")


def _metrics(total=0):
    return {"total": total, **{status: 0 for status in STATES}}


def published_category_counts(preparation, categories, first, last):
    """Single-day atomic ETL projection; old/multi-day results retain the existing reader."""
    reports=preparation.get('reports',[])
    if first!=last or len(reports)!=1 or str(reports[0].get('day'))!=first.isoformat():return None
    report=reports[0]
    if report.get('summaryVersion')!=1:return None
    counts=report.get('categoryStatuses');allowed={'supported','problem','insufficient','failed'}
    if not isinstance(counts,dict):raise EvidenceError('清洗分类汇总内容无效，请重新清洗',503)
    expected={key:row['total'] for key,row in categories.items() if key in SUPPORTED_REASONS and row['total']}
    if set(counts)!=set(expected):raise EvidenceError('清洗分类汇总与目录数量不一致，请重新清洗',503)
    totals={key:0 for key in allowed}
    for reason,values in counts.items():
        if not isinstance(values,dict) or set(values)-allowed or any(type(v) is not int or v<0 for v in values.values()) or sum(values.values())!=expected[reason]:
            raise EvidenceError('清洗分类汇总与目录数量不一致，请重新清洗',503)
        for key,value in values.items():totals[key]+=value
    if sum(totals.values())!=report.get('orders') or any(totals[key]!=report.get('statuses',{}).get(key,0) for key in allowed):
        raise EvidenceError('清洗分类汇总与日汇总不一致，请重新清洗',503)
    return counts


class RiskVerificationOverview:
    def __init__(self, config, source=None):
        self.config = config
        self.reader = RiskVerificationCatalog(config, source)

    @staticmethod
    def _scope(first, last, reason=None):
        sql = """o.issue_date >= %s AND o.issue_date <= %s
                 AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer
                     WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date
                       AND newer.issue_date<=%s)"""
        values = [first.isoformat(), last.isoformat(), last.isoformat()]
        if reason is not None:
            if not isinstance(reason, str) or not reason or len(reason) > 120:
                raise EvidenceError("盈亏原因分类参数无效")
            sql += " AND o.profit_reason_type=%s"
            values.append(reason)
        return sql, values

    def _statuses(self, cursor, owner, scope, parameters):
        from .risk_prepared_facts import statuses
        return statuses(cursor,scope,parameters)

    def summary(self, owner, start, end):
        first, last = _period(start, end)
        scope, values = self._scope(first, last)
        connection = cursor = None
        try:
            connection = self.reader._connect()
            cursor = connection.cursor()
            freshness = self.reader.coverage(cursor, first, last, require_complete=False)
            from .risk_prepared_facts import coverage
            freshness['preparation']=coverage(cursor,first,last)
            labels, freshness["reasonDictionaryVersion"] = self.reader.reason_labels(cursor)
            cursor.execute(f"SELECT o.profit_reason_type AS reason_code,COUNT(*) AS order_count FROM bi_risk_order_day o WHERE {scope} GROUP BY o.profit_reason_type", tuple(values))
            groups = _rows(cursor)
            categories = {}
            for row in groups:
                reason = str(row["reason_code"])
                total = int(row["order_count"])
                known = reason in SUPPORTED_REASONS
                categories[reason] = {"reasonCode": reason,
                    "reasonLabel": labels.get(reason) or f"{reason}（字典名称缺失）",
                    "ruleStatus": ("整单出票利润加同OTA订单号增值利润，对照出票时通用配置止损值" if reason == ANCILLARY_REASON else "正常业务逐票出票利润对照出票时通用配置止损值，不加佣金；自动通过即闭环，可人工抽查" if reason in NORMAL_REASONS else "逐票原始出票利润对照出票时单票止损值，不加佣金或预期收益" if reason in BET_REASONS else "儿童/婴儿前提＋综合平均单票出票利润对照当前单止损配置（不加佣金）" if reason=="RLA040" else "去哪儿出票利润加回销售佣金，对照出票时配置止损值") if known else "规则未接入，不自动放行",
                    **_metrics(total), "unchecked": total if known else 0, "rule_pending": 0 if known else total}
            samples = RiskAutoVerification(self.config).sampling(owner)
            compact = published_category_counts(freshness['preparation'],categories,first,last) if not samples else None
            statuses = {} if compact is not None else self._statuses(cursor, owner, scope, values)
            if compact is not None:
                for reason,counts in compact.items():
                    categories[reason]['unchecked']=0
                    for key,value in counts.items():categories[reason][key]=value
            for item in statuses.values():
                if item["status"] != "unchecked":
                    initial = "unchecked" if item["reasonCode"] in SUPPORTED_REASONS else "rule_pending"
                    if item["reasonCode"] not in categories or categories[item["reasonCode"]][initial] <= 0:
                        raise EvidenceError("源订单在汇总期间发生变化，请重新查询", 409)
                    category = categories[item["reasonCode"]]
                    category[initial] -= 1
                    category[item["status"]] += 1
            metrics = _metrics()
            for item in categories.values():
                for key in metrics:
                    metrics[key] += item[key]
            sampled = [samples[item["resultId"]] for item in statuses.values() if item["status"] != "outdated" and item["resultId"] in samples]
            return {"period": {"startDate": first.isoformat(), "endDate": last.isoformat()}, "sampling": {"sampled": len(sampled), "disputed": sampled.count("disputed")},
                    "dateBasis": "issue_ticket_time", "metrics": metrics,
                    "categories": sorted(categories.values(), key=lambda row: (-row["total"], row["reasonCode"])),
                    "notes": NOTES + ([] if labels else ["盈亏原因字典尚未同步，暂展示原始编码；可仅同步字典，无需重读订单。"]), "dataFreshness": freshness}
        except (EvidenceError, FlowError):
            raise
        except Exception:
            LOGGER.exception("Risk verification overview failed")
            raise EvidenceError("风控核对汇总失败，请检查sibebid目录表、同步批次及核查存储", 503) from None
        finally:
            self.reader._close(cursor, connection)

    @staticmethod
    def enrich_metric(row):
        import json
        raw = row.pop('metric_body', None)
        body = json.loads(raw) if raw else {}
        if not isinstance(body, dict):
            raise EvidenceError('订单指标内容无效，请重新清洗', 503)
        row['airlines'] = body.get('airlines', [])
        row['departments'] = body.get('departments', [])
        row['metricsReady'] = bool(raw)
        row['total_profit'] = str(row['total_profit']) if row.get('total_profit') is not None else None
        return row

    def analytics(self, owner, start, end):
        from .risk_workflow_analytics import analytics
        return analytics(self, owner, start, end)

    def orders(self, owner, start, end, reason=None, status="all", page=1, page_size=50, order_no=None, platform=None, airline=None, sort="profit_asc"):
        first, last = _period(start, end)
        page = _integer(page, "页码", 1000000)
        page_size = _integer(page_size, "每页条数", 100)
        if not isinstance(status, str) or status not in {"all", *STATES}:
            raise EvidenceError("不支持的核查状态")
        scope, values = self._scope(first, last, reason)
        if sort not in ('profit_asc', 'profit_desc'):
            raise EvidenceError('利润排序参数无效')
        for field, value, limit in (('订单号', order_no, 128), ('平台', platform, 64), ('航司', airline, 16)):
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise EvidenceError(field + '筛选值无效')
        if order_no:
            scope += ' AND o.ota_order_no=%s'
            values.append(order_no.strip())
        if platform:
            scope += ' AND o.ota_code=%s'
            values.append(platform.strip())
        if airline:
            scope += """ AND EXISTS (SELECT 1 FROM bi_risk_order_metric_day fm JOIN bi_risk_order_metric_day_ready fr
                ON fr.issue_date=fm.issue_date AND fr.catalog_run_id=fm.catalog_run_id
                WHERE fm.issue_date=o.issue_date AND fm.order_id=o.order_id AND fm.catalog_run_id=o.etl_run_id
                AND JSON_CONTAINS(JSON_EXTRACT(fm.body,'$.airlines'),JSON_QUOTE(%s)))"""
            values.append(airline.strip())
        connection = cursor = None
        try:
            connection = self.reader._connect()
            cursor = connection.cursor()
            freshness = self.reader.coverage(cursor, first, last, require_complete=False)
            from .risk_prepared_facts import coverage
            freshness['preparation']=coverage(cursor,first,last)
            labels, freshness["reasonDictionaryVersion"] = self.reader.reason_labels(cursor)
            # The ordinary reason drill-down needs statuses only for its page.
            # Filtering by a status still happens across the complete scope,
            # before COUNT/sorting/pagination, preserving the existing contract.
            statuses = self._statuses(cursor, owner, scope, values) if status != 'all' else {}
            selected = [identifier for identifier, item in statuses.items() if item["status"] == status]
            if status != "all":
                if status == "unchecked":
                    scope += " AND o.profit_reason_type IN (" + ','.join(['%s']*len(SUPPORTED_REASONS)) + ")"
                    values.extend(SUPPORTED_REASONS)
                    excluded = [identifier for identifier, item in statuses.items() if item["status"] != "unchecked"]
                    if excluded:
                        scope += " AND o.order_id NOT IN (" + ",".join(["%s"] * len(excluded)) + ")"
                        values.extend(excluded)
                elif status == "rule_pending":
                    scope += " AND o.profit_reason_type NOT IN (" + ','.join(['%s']*len(SUPPORTED_REASONS)) + ")"
                    values.extend(SUPPORTED_REASONS)
                elif selected:
                    scope += " AND o.order_id IN (" + ",".join(["%s"] * len(selected)) + ")"
                    values.extend(selected)
                else:
                    scope += " AND 1=0"
            cursor.execute(f"SELECT COUNT(*) AS order_count FROM bi_risk_order_day o WHERE {scope}", tuple(values))
            total = int(_rows(cursor)[0]["order_count"])
            direction = 'ASC' if sort == 'profit_asc' else 'DESC'
            cursor.execute(f"SELECT {FIELDS}{METRIC_FIELDS} FROM bi_risk_order_day o {METRIC_JOIN} WHERE {scope} ORDER BY ({METRIC_PROFIT}) IS NULL,({METRIC_PROFIT}) {direction},o.order_id DESC LIMIT %s OFFSET %s", (*values, page_size, (page - 1) * page_size))
            rows = _rows(cursor)
            if status == 'all' and rows:
                ids = [str(row['id']) for row in rows]
                page_scope = scope + ' AND o.order_id IN (' + ','.join(['%s'] * len(ids)) + ')'
                statuses = self._statuses(cursor, owner, page_scope, [*values, *ids])
            for row in rows:
                self.enrich_metric(row)
                review = statuses.get(str(row["id"]), {})
                row.update(verificationStatus=review.get("status", "unchecked" if row["profit_reason_type"] in SUPPORTED_REASONS else "rule_pending"), caseId=review.get("caseId"), profit_reason_name=labels.get(row["profit_reason_type"]))
            return {"items": rows, "total": total, "page": page, "pageSize": page_size,
                    "period": {"startDate": first.isoformat(), "endDate": last.isoformat()}, "dateBasis": "issue_ticket_time", "dataFreshness": freshness}
        except (EvidenceError, FlowError):
            raise
        except Exception:
            LOGGER.exception("Risk verification order drilldown failed")
            raise EvidenceError("风控核对订单读取失败，请检查sibebid目录表、同步批次及核查存储", 503) from None
        finally:
            self.reader._close(cursor, connection)
