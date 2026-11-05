"""Issue-date order-level rollups and drill-down; financial loss is not a review problem."""
from datetime import date, timedelta
import logging

from .risk_order_evidence import EvidenceError, _rows
from .risk_verification_catalog import RiskVerificationCatalog
from .risk_verification_flow import FlowError
from .risk_auto_verification import RiskAutoVerification
from .risk_child_loss import BET_REASONS, SUPPORTED_REASONS

LOGGER = logging.getLogger(__name__)
STATES = ("problem", "supported", "insufficient", "reviewing", "unchecked", "failed", "rule_pending", "outdated")
FIELDS = "o.order_id AS id,o.order_no,o.ota_order_no,o.ota_code,o.profit_reason_type,o.create_time,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date"
NOTES = [
    "读取中台ETL目录，不实时扫描ERP；按出票日期限定，跨日或多票均按内部订单ID去重。",
    "数据截止各日最近一次成功同步；查询、翻页和查看详情不触发ERP读取，只有独立清洗任务读取ERP，页面按钮加载已发布结果。",
    "按每日成功发布的当前核实事实统计，不依赖账号加载任务；通过无须人工确认，个人抽查独立留痕。",
    "清洗读取出票及适用证据，页面不查ERP；相同证据重复清洗保留抽查关联，规则或证据改变后旧结论只作历史参考。",
    "未核查、核查中和证据不足不等于没有问题；尚无自动核查结论。",
]


def _period(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise EvidenceError("请提供YYYY-MM-DD格式的起止日期") from None
    if first > last or (last - first).days > 30 or last == date.max:
        raise EvidenceError("按出票日期查询，范围须为1至31天")
    return first, last


def _integer(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit():
        raise EvidenceError(f"{name}必须为正整数")
    value = int(value)
    if not 1 <= value <= maximum:
        raise EvidenceError(f"{name}超出允许范围")
    return value


def _stamp(value):
    return None if value is None else str(value).replace(" ", "T")


def _metrics(total=0):
    return {"total": total, **{status: 0 for status in STATES}}


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
                    "ruleStatus": ("逐票原始出票利润对照出票时单票止损值，不加佣金或预期收益" if reason in BET_REASONS else "儿童/婴儿前提＋综合平均单票出票利润对照当前单止损配置（不加佣金）" if reason=="RLA040" else "去哪儿出票利润加回销售佣金，对照出票时配置止损值") if known else "规则未接入，不自动放行",
                    **_metrics(total), "unchecked": total if known else 0, "rule_pending": 0 if known else total}
            statuses = self._statuses(cursor, owner, scope, values)
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
            samples = RiskAutoVerification(self.config).sampling(owner)
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

    def orders(self, owner, start, end, reason=None, status="all", page=1, page_size=50):
        first, last = _period(start, end)
        page = _integer(page, "页码", 1000000)
        page_size = _integer(page_size, "每页条数", 100)
        if not isinstance(status, str) or status not in {"all", *STATES}:
            raise EvidenceError("不支持的核查状态")
        scope, values = self._scope(first, last, reason)
        connection = cursor = None
        try:
            connection = self.reader._connect()
            cursor = connection.cursor()
            freshness = self.reader.coverage(cursor, first, last, require_complete=False)
            from .risk_prepared_facts import coverage
            freshness['preparation']=coverage(cursor,first,last)
            labels, freshness["reasonDictionaryVersion"] = self.reader.reason_labels(cursor)
            statuses = self._statuses(cursor, owner, scope, values)
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
            cursor.execute(f"SELECT {FIELDS} FROM bi_risk_order_day o WHERE {scope} ORDER BY o.order_id DESC LIMIT %s OFFSET %s", (*values, page_size, (page - 1) * page_size))
            rows = _rows(cursor)
            for row in rows:
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
