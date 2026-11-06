"""Deterministic, owner-scoped automatic checks and independent human sampling."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import logging
import time
import uuid

from .risk_commission_rule import RULE_ID, evaluate_commission_loss
from .risk_child_loss import CHILD_REASON, BET_REASONS, NORMAL_REASONS, SUPPORTED_REASONS, ORDER_FIELDS, read_child_evidence, evaluate_child
from .risk_bet_loss import evaluate_bet, evaluate_normal
from .risk_historical_threshold import HistoricalThresholds
from .risk_order_evidence import RiskOrderEvidenceService, _rows, order_id
from .risk_verification_flow import FlowError, _owner
from .risk_auto_store import RiskAutoStore, StoreConflict

LOG = logging.getLogger(__name__)
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="risk-auto")
ZONE = timezone(timedelta(hours=8))
STATUSES = {"supported", "problem", "insufficient", "failed", "rule_pending"}


def stamp(value):
    return None if value is None else str(value).replace(" ", "T")


def now():
    return datetime.now(ZONE).isoformat(timespec="seconds")


def evaluate(evidence):
    """Only selected source fields, never raw logs or passenger information in results."""
    order = evidence["order"]
    if order.get("profit_reason_type") in NORMAL_REASONS:return evaluate_normal(evidence,RULE_ID)
    if order.get("profit_reason_type")==CHILD_REASON:return evaluate_child(evidence,RULE_ID)
    if order.get("profit_reason_type") in BET_REASONS:return evaluate_bet(evidence,RULE_ID)
    base = {"ruleVersion": RULE_ID, "status": "insufficient", "summary": "证据不足", "tickets": [],
            "platform": order.get("ota_code"), "stopLoss": None, "logReferences": [], "missing": []}
    if order.get("profit_reason_type") != "RLA013":
        return {**base, "status": "rule_pending", "summary": "该类型规则尚未接入"}
    if not order.get("ota_code"):
        return {**base, "missing": ["平台编码"], "summary": "平台缺失，无法判断去哪儿前提"}
    if order["ota_code"] != "QUNAR":
        return {**base, "status": "problem", "summary": "非去哪儿平台不得选择佣金、点击费亏损；平台条件优先，已判为有问题"}
    if not evidence.get("complete"):
        return {**base, "missing": ["出票明细读取不完整"], "summary": "证据截断或不完整，未执行通过判定"}
    issues = evidence.get("issues", [])
    if not issues:
        return {**base, "missing": ["出票明细"], "summary": "没有可核实的出票明细"}
    outcomes = []
    for issue in issues:
        configuration = issue.get("thresholdConfiguration") or {"status": "insufficient", "reason": "缺少出票时通用配置"}
        result = {"id": str(issue["id"]), "profit": issue.get("issue_profit"), "commission": issue.get("sale_commission_amount"),
                  "currency": issue.get("sale_currency"), "profitSource": "order_info_issue.issue_profit", "commissionSource": "order_info_issue.sale_commission_amount",
                  "segmentCount": issue.get("segmentCount"), "configuration": configuration,
                  "stopLoss": configuration.get("amount") if configuration.get("status") == "ready" else None}
        if configuration.get("status") != "ready":
            result.update(status="insufficient", explanation=configuration.get("reason") or "出票时配置无法可靠还原")
        elif issue.get("sale_currency") != "CNY":
            result.update(status="insufficient", explanation=f"销售佣金币种为{issue.get('sale_currency') or '缺失'}，未确认为CNY，不能混币相加")
        else:
            checked = evaluate_commission_loss(is_qunar=order.get("ota_code") == "QUNAR", single_ticket_profit=issue.get("issue_profit"),
                                               sales_commission=issue.get("sale_commission_amount"), stop_loss=result["stopLoss"])
            status = {"supported": "supported", "contradicted": "problem", "not_applicable": "problem"}.get(checked["status"], "insufficient")
            explanation = checked.get("calculation") or checked.get("prerequisite") or "缺少有效的出票利润、销售佣金或止损值"
            result.update(status=status, adjustedProfit=checked.get("adjustedProfit"), boundary=checked.get("boundary"), explanation=explanation)
        outcomes.append(result["status"])
        base["tickets"].append(result)
    thresholds = {row['stopLoss'] for row in base['tickets']}
    if len(thresholds) == 1:
        base['stopLoss'] = next(iter(thresholds))
    if "problem" in outcomes:
        base.update(status="problem", summary="至少一张票不符合选因条件，请查看逐票原因")
    elif "insufficient" in outcomes:
        base.update(status="insufficient", summary="部分票缺少必要证据，不能判为通过")
    else:
        base.update(status="supported", summary="全部出票明细符合已确认的佣金亏损选因规则")
    return base


def read_evidence(config, identifier):
    """Minimal fields in one consistent, read-only ERP snapshot."""
    values = dict(config)
    for key in ("CONNECT_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT"):
        values[f"ERP_MYSQL_{key}"] = min(int(values.get(f"ERP_MYSQL_{key}", 15)), 15)
    reader = RiskOrderEvidenceService(values)
    connection = cursor = None
    try:
        connection = reader._connect()
        cursor = connection.cursor()
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION READ ONLY")
        return read_evidence_cursor(cursor, identifier)
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                reader._close(cursor, connection)


def read_evidence_cursor(cursor, identifier, configuration_cache=None, _basic=False):
    cursor.execute("SELECT "+ORDER_FIELDS+" FROM order_info WHERE id=%s", (order_id(identifier),))
    orders = _rows(cursor)
    if len(orders) != 1:
        raise FlowError("订单不存在，需重新同步目录", 409)
    if not _basic and orders[0].get("profit_reason_type")==CHILD_REASON:
        return read_child_evidence(cursor,orders[0],configuration_cache if configuration_cache is not None else {},read_evidence_cursor)
    if not _basic and orders[0].get("profit_reason_type") == "RLA013" and orders[0].get("ota_code") != "QUNAR":
        return {"order": orders[0], "issues": [], "logs": [], "complete": True}
    if not _basic and orders[0].get('profit_reason_type') not in SUPPORTED_REASONS:
        return {'order': orders[0], 'issues': [], 'logs': [], 'complete': True}
    cursor.execute("""SELECT id,order_id,issue_profit,sale_commission_amount,sale_currency,issue_ticket_time,
      supplier_code,marketing_airline,issue_gds_channel,issue_office_no,issue_ticketing_office_no
      FROM order_info_issue WHERE order_id=%s ORDER BY id LIMIT 201""", (order_id(identifier),))
    issues = _rows(cursor)
    if any(str(row["order_id"]) != str(identifier) for row in issues):
        raise FlowError("取证订单关联不一致", 409)
    if issues:
        cache = configuration_cache if configuration_cache is not None else {}
        if 'reader' not in cache:
            cache['reader'] = HistoricalThresholds(cursor)
        for issue in issues[:200]:
            cursor.execute("""SELECT COUNT(*) AS link_count,
              COUNT(DISTINCT CASE WHEN s.airlift_flag IN (0,1) THEN s.id END) AS matched_segment_count,
              COUNT(DISTINCT CASE WHEN s.airlift_flag=1 THEN s.id END) AS segment_count
              FROM order_info_issue_segment i LEFT JOIN order_info_segment s ON s.id=i.segment_id
              AND s.order_id=%s WHERE i.issue_id=%s""", (order_id(identifier), issue['id']))
            counts = _rows(cursor)
            count = counts[0] if len(counts) == 1 else {}
            issue['segmentCount'] = int(count['segment_count']) if count.get('segment_count') and count.get('link_count') == count.get('matched_segment_count') else None
            from .risk_threshold_facts import enrich_matching_facts
            enrich_matching_facts(cursor, issue, orders[0], cache)
            issue['thresholdConfiguration'] = cache['reader'].resolve(issue, orders[0])
    return {"order": orders[0], "issues": issues[:200], "logs": [], "complete": len(issues) <= 200}


class RiskAutoVerification:
    def __init__(self, config):
        self.config = config
        self.store = RiskAutoStore(config)

    def db(self):
        return self.store.db()

    def latest(self, owner):
        with self.db() as db:
            rows = db.execute("SELECT body FROM auto_results WHERE owner=? AND rowid IN (SELECT MAX(rowid) FROM auto_results WHERE owner=? GROUP BY order_id) LIMIT 20001", (_owner(owner), _owner(owner))).fetchall()
        if len(rows) > 20000:
            raise FlowError("自动结果超过当前汇总上限，需归档；未返回截断统计", 413)
        return {item["orderId"]: item for item in (json.loads(row["body"]) for row in rows)}

    def latest_metadata(self, owner):
        fields = {"reasonCode": "reasonCode", "sourceUpdatedAt": "sourceUpdatedAt", "status": "status", "ruleVersion": "ruleVersion", "catalogRunId": "catalogRunId", "jobId": "jobId", "issueDate": "issueDate", "checkedAtEpoch": "checkedAtEpoch"}
        projection = ",".join(f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT(body,'$.{key}')),'null') AS {alias}" for key, alias in fields.items())
        with self.db() as db:
            rows = db.execute(f"SELECT id,order_id,{projection} FROM auto_results WHERE owner=? AND rowid IN (SELECT MAX(rowid) FROM auto_results WHERE owner=? GROUP BY order_id) LIMIT 20001", (_owner(owner), _owner(owner))).fetchall()
        if len(rows) > 20000:
            raise FlowError("自动结果超过当前汇总上限，需归档；未返回截断统计", 413)
        result = {}
        for row in rows:
            item = dict(row)
            item["checkedAtEpoch"] = float(item.get("checkedAtEpoch") or 0)
            result[str(item["order_id"])] = item
        return result

    def refresh_requests(self, owner):
        with self.db() as db:
            rows = db.execute("SELECT body,status FROM auto_jobs WHERE owner=? ORDER BY rowid DESC LIMIT 20001", (_owner(owner),)).fetchall()
        if len(rows) > 20000:
            raise FlowError("更新任务历史超过当前统计上限，需归档；未返回截断状态", 413)
        by_day = {}
        for row in rows:
            body = json.loads(row["body"])
            if body.get("mode") != "refresh_verify":
                continue
            day, last = date.fromisoformat(body["startDate"]), date.fromisoformat(body["endDate"])
            while day <= last:
                # Only the newest request for a day can invalidate a result.
                key = day.isoformat()
                if key not in by_day or body["createdAtEpoch"] > by_day[key]["createdAtEpoch"]:
                    by_day[key] = body
                day += timedelta(days=1)
        return by_day

    @classmethod
    def current(cls, result, row, requests):
        if not cls.matches(result, row):
            return False
        day = str(row.get("issue_date") or result.get("issueDate") or "")
        relevant = ([requests[day]] if day in requests else []) if isinstance(requests, dict) else requests
        for request in relevant:
            if (request["id"] != result.get("jobId")
                    and request.get("startDate", "") <= day <= request.get("endDate", "")
                    and request.get("createdAtEpoch", 0) >= result.get("checkedAtEpoch", 0)):
                return False
        return True

    def active(self, owner, reclaim=False):
        with self.db() as db:
            if reclaim:
                db.execute("UPDATE auto_jobs SET status='failed' WHERE owner=? AND status IN ('queued','running') AND updated<?", (_owner(owner), time.time() - 600))
            row = db.execute("SELECT body,status,updated FROM auto_jobs WHERE owner=? ORDER BY rowid DESC LIMIT 1", (_owner(owner),)).fetchone()
        if row is None:
            return None
        body = json.loads(row["body"])
        body["status"] = "failed" if row["status"] in {"queued", "running"} and row["updated"] < time.time() - 600 else row["status"]
        if body["status"] == "failed" and row["status"] != "failed":
            body.update(phase="failed", message="任务已中断或失去心跳，点击更新并核实可重新启动")
        body.pop("targets", None)
        return body

    def result(self, owner, identifier, issue_date=None):
        from .risk_prepared_facts import one
        from .risk_verification_catalog import RiskVerificationCatalog
        catalog=RiskVerificationCatalog(self.config);connection=cursor=None
        try:
            connection=catalog._connect();cursor=connection.cursor()
            def fetch(sql,args):cursor.execute(sql,args);return _rows(cursor)
            body=one(fetch,identifier,issue_date)
        finally:catalog._close(cursor,connection)
        if body:
            with self.db() as db:
                body['samples']=[json.loads(r['body']) for r in db.execute('SELECT body FROM auto_samples WHERE owner=? AND result_id=? ORDER BY rowid DESC',(_owner(owner),body['id']))]
            return body
        body=self._legacy_result(owner,identifier)
        if body:body['isCurrent']=False
        return body

    def _legacy_result(self, owner, identifier):
        with self.db() as db:
            row = db.execute("SELECT body FROM auto_results WHERE owner=? AND order_id=? ORDER BY rowid DESC LIMIT 1", (_owner(owner), str(order_id(identifier)))).fetchone()
            if not row:
                return None
            body = json.loads(row["body"])
            body["samples"] = [json.loads(item["body"]) for item in db.execute("SELECT body FROM auto_samples WHERE owner=? AND result_id=? ORDER BY rowid DESC", (_owner(owner), body["id"]))]
        from .risk_verification_catalog import RiskVerificationCatalog
        catalog = RiskVerificationCatalog(self.config)
        connection = cursor = None
        try:
            connection = catalog._connect(); cursor = connection.cursor()
            cursor.execute("SELECT order_id AS id,profit_reason_type,update_time,etl_run_id,issue_date FROM bi_risk_order_day WHERE order_id=%s ORDER BY issue_date DESC LIMIT 1", (order_id(identifier),))
            rows = _rows(cursor)
            body["isCurrent"] = bool(rows and self.current(body, rows[0], self.refresh_requests(owner)))
        finally:
            catalog._close(cursor, connection)
        return body

    def sampling(self, owner):
        with self.db() as db:
            rows = db.execute("SELECT result_id,body FROM auto_samples WHERE owner=? AND rowid IN (SELECT MAX(rowid) FROM auto_samples WHERE owner=? GROUP BY result_id)", (_owner(owner), _owner(owner))).fetchall()
        return {row["result_id"]: json.loads(row["body"])["outcome"] for row in rows}

    def sample(self, owner, identifier, expected_id, outcome, reason, issue_date=None):
        from .risk_prepared_facts import one
        if outcome not in ('confirmed','disputed') or not isinstance(reason,str) or not reason.strip() or len(reason)>2000:
            raise FlowError('抽查结果和说明必填，说明最多2000字')
        with self.db() as db:
            current=one(lambda sql,args:db.execute(sql,args).fetchall(),identifier,issue_date,lock=True)
            if not current or current['id']!=expected_id:raise FlowError('清洗结果已改变，请刷新后再抽查',409)
            body={'id':uuid.uuid4().hex,'resultId':expected_id,'outcome':outcome,'reason':reason.strip(),
                  'at':now(),'operator':_owner(owner),'issueDate':current['issueDate'],
                  'catalogRunId':current['catalogRunId'],'evidenceHash':current['evidenceHash']}
            db.execute('INSERT INTO auto_samples VALUES(?,?,?,?)',(body['id'],_owner(owner),expected_id,json.dumps(body,ensure_ascii=False)))
        return body

    def _legacy_sample(self, owner, identifier, expected_id, outcome, reason):
        from .risk_verification_catalog import RiskVerificationCatalog
        if not isinstance(outcome, str) or outcome not in {"confirmed", "disputed"} or not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise FlowError("抽查结果和说明必填，说明最多2000字")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT id,body FROM auto_results WHERE owner=? AND order_id=? ORDER BY rowid DESC LIMIT 1 FOR UPDATE", (_owner(owner), str(order_id(identifier)))).fetchone()
            if current is None or current["id"] != expected_id:
                raise FlowError("自动结果已改变，请刷新后再抽查", 409)
            catalog = RiskVerificationCatalog(self.config)
            connection = cursor = None
            try:
                connection = catalog._connect(); cursor = connection.cursor()
                cursor.execute("SELECT order_id AS id,profit_reason_type,update_time,etl_run_id,issue_date FROM bi_risk_order_day WHERE order_id=%s ORDER BY issue_date DESC LIMIT 1", (order_id(identifier),))
                rows = _rows(cursor)
                if not rows or not self.current(json.loads(current["body"]), rows[0], self.refresh_requests(owner)):
                    raise FlowError("源版本已改变，需重新核实后再抽查", 409)
            finally:
                catalog._close(cursor, connection)
            body = {"id": uuid.uuid4().hex, "resultId": expected_id, "outcome": outcome, "reason": reason.strip(), "at": now(), "operator": _owner(owner)}
            db.execute("INSERT INTO auto_samples VALUES(?,?,?,?)", (body["id"], _owner(owner), expected_id, json.dumps(body, ensure_ascii=False)))
        return body

    def submit(self, owner, start, end, reason=None, force=False):
        from .risk_verification_overview import _period
        _period(start, end)
        if reason is not None and (not isinstance(reason, str) or not reason or len(reason) > 120):
            raise FlowError("盈亏原因参数无效")
        if type(force) is not bool:
            raise FlowError("重新核实标记须为布尔值")
        active = self.active(owner, reclaim=True)
        if active and active["status"] in {"queued", "running"}:
            return active
        body = {"id": uuid.uuid4().hex, "status": "queued", "phase": "queued", "done": 0, "total": 0,
                "remaining": 0, "startDate": start, "endDate": end, "reason": reason, "force": force,
                "createdAt": now(), "createdAtEpoch": time.time(), "mode": "load_prepared", "refreshedRows": 0, "reused": 0}
        try:
            with self.db() as db:
                db.execute("INSERT INTO auto_jobs VALUES(?,?,?,?,?)", (body["id"], _owner(owner), "queued", time.time(), json.dumps(body, ensure_ascii=False)))
        except StoreConflict:
            return self.active(owner)
        EXECUTOR.submit(self.work, _owner(owner), body["id"])
        return body

    @staticmethod
    def matches(result, row):
        return bool(result and result["reasonCode"] == row["profit_reason_type"]
                    and stamp(result["sourceUpdatedAt"]) == stamp(row["update_time"])
                    and result["ruleVersion"] == RULE_ID
                    and result.get("catalogRunId") is not None
                    and result["catalogRunId"] == row.get("etl_run_id"))

    def work(self, owner, job_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM auto_jobs WHERE id=? AND owner=? AND status='queued'", (job_id, owner)).fetchone()
            if row is None:
                return
            body = json.loads(row["body"])
            if db.execute("UPDATE auto_jobs SET status='running',updated=? WHERE id=? AND status='queued' AND updated>=?", (time.time(), job_id, time.time() - 600)).rowcount != 1:
                return
        from .risk_prepared import consume
        try:
            body.update(phase='loading_prepared')
            with self.db() as db:
                db.execute("UPDATE auto_jobs SET updated=?,body=? WHERE id=? AND owner=? AND status='running'",(time.time(),json.dumps(body,ensure_ascii=False),job_id,owner))
            consume(self,owner,body,None)
        except Exception as error:
            LOG.exception('Prepared risk loading failed')
            message=str(error) if isinstance(error,FlowError) else '风控清洗结果未就绪，请检查新表、清洗批次及版本；不会回退ERP逐单核实'
            body.update(status='failed',phase='failed',message=message)
            with self.db() as db:
                db.execute("UPDATE auto_jobs SET status='failed',updated=?,body=? WHERE id=? AND owner=? AND status='running'",(time.time(),json.dumps(body,ensure_ascii=False),job_id,owner))
