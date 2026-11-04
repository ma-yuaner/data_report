"""Deterministic, owner-scoped automatic checks and independent human sampling."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import time
import uuid

from .risk_commission_rule import RULE_ID, evaluate_commission_loss, parse_stop_loss_log
from .risk_order_evidence import RiskOrderEvidenceService, _rows, order_id
from .risk_verification_flow import FlowError, _owner

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
    base = {"ruleVersion": RULE_ID, "status": "insufficient", "summary": "证据不足", "tickets": [],
            "platform": order.get("ota_code"), "stopLoss": None, "logReferences": [], "missing": []}
    if order.get("profit_reason_type") != "RLA013":
        return {**base, "status": "rule_pending", "summary": "该类型规则尚未接入"}
    if not evidence.get("complete"):
        return {**base, "missing": ["出票或止损日志读取不完整"], "summary": "证据截断或不完整，未执行通过判定"}
    issues = evidence.get("issues", [])
    if not issues:
        return {**base, "missing": ["出票明细"], "summary": "没有可核实的出票明细"}
    if not order.get("ota_code"):
        return {**base, "missing": ["平台编码"], "summary": "平台缺失，无法判断去哪儿前提"}
    parsed = []
    for log in evidence.get("logs", []):
        records = parse_stop_loss_log(log.get("operator_content"))["records"]
        if not records:
            return {**base, "missing": ["可解析的止损日志"], "summary": "存在无法解析的止损日志，不能忽略后自动通过"}
        for item in records:
            parsed.append(item)
            base["logReferences"].append({"id": str(log["id"]), "at": stamp(log.get("operator_datetime")), **item})
    if not parsed or any(not row["amountsConsistent"] for row in parsed):
        return {**base, "missing": ["金额自洽的止损日志"], "summary": "缺止损日志或日志金额不自洽"}
    from decimal import Decimal
    thresholds = {Decimal(row["stopLoss"]) for row in parsed}
    if len(thresholds) != 1:
        return {**base, "missing": ["唯一一致的日志止损值"], "summary": "订单止损值存在冲突，不能自动选择某一条"}
    base["stopLoss"] = format(next(iter(thresholds)), "f")
    outcomes = []
    for issue in issues:
        result = {"id": str(issue["id"]), "profit": issue.get("issue_profit"), "commission": issue.get("sale_commission_amount"),
                  "currency": "CNY", "profitSource": "order_info_issue.issue_profit", "commissionSource": "order_info_issue.sale_commission_amount"}
        if issue.get("sale_currency") != "CNY":
            result.update(status="insufficient", explanation=f"销售佣金币种为{issue.get('sale_currency') or '缺失'}，未确认为CNY，不能混币相加")
        else:
            checked = evaluate_commission_loss(is_qunar=order.get("ota_code") == "QUNAR", single_ticket_profit=issue.get("issue_profit"),
                                               sales_commission=issue.get("sale_commission_amount"), stop_loss=base["stopLoss"])
            status = {"supported": "supported", "contradicted": "problem", "not_applicable": "problem"}.get(checked["status"], "insufficient")
            explanation = checked.get("calculation") or checked.get("prerequisite") or "缺少有效的出票利润、销售佣金或止损值"
            result.update(status=status, adjustedProfit=checked.get("adjustedProfit"), boundary=checked.get("boundary"), explanation=explanation)
        outcomes.append(result["status"])
        base["tickets"].append(result)
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
        cursor.execute("SELECT id,ota_code,profit_reason_type,update_time FROM order_info WHERE id=%s", (order_id(identifier),))
        orders = _rows(cursor)
        if len(orders) != 1:
            raise FlowError("订单不存在，需重新同步目录", 409)
        cursor.execute("SELECT id,order_id,issue_profit,sale_commission_amount,sale_currency FROM order_info_issue WHERE order_id=%s ORDER BY id LIMIT 201", (order_id(identifier),))
        issues = _rows(cursor)
        cursor.execute("SELECT id,order_id,operator_datetime,LEFT(operator_content,20001) AS operator_content FROM order_info_operator_log WHERE order_id=%s AND operator_content LIKE %s ORDER BY id LIMIT 201", (order_id(identifier), "%止损值配置为%"))
        logs = _rows(cursor)
        if any(str(row["order_id"]) != str(identifier) for row in issues + logs):
            raise FlowError("取证订单关联不一致", 409)
        return {"order": orders[0], "issues": issues[:200], "logs": logs[:200], "complete": len(issues) <= 200 and len(logs) <= 200}
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                reader._close(cursor, connection)


class RiskAutoVerification:
    def __init__(self, config):
        self.config = config
        root = Path(config.get("RISK_VERIFICATION_ROOT") or "/app/var/risk-verification").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "workflow.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS auto_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,status TEXT NOT NULL,updated REAL NOT NULL,body TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS auto_active_owner ON auto_jobs(owner) WHERE status IN ('queued','running');
                CREATE TABLE IF NOT EXISTS auto_results(id TEXT PRIMARY KEY,owner TEXT NOT NULL,order_id TEXT NOT NULL,created REAL NOT NULL,body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS auto_result_owner_order ON auto_results(owner,order_id,created);
                CREATE TABLE IF NOT EXISTS auto_samples(id TEXT PRIMARY KEY,owner TEXT NOT NULL,result_id TEXT NOT NULL,body TEXT NOT NULL);
            """)

    def db(self):
        from contextlib import closing
        # sqlite Connection context alone does not close; use an explicit managed context.
        from contextlib import contextmanager
        @contextmanager
        def managed():
            with closing(sqlite3.connect(str(self.path), timeout=10)) as db:
                db.row_factory = sqlite3.Row
                with db:
                    yield db
        return managed()

    def latest(self, owner):
        with self.db() as db:
            rows = db.execute("SELECT body FROM auto_results WHERE owner=? AND rowid IN (SELECT MAX(rowid) FROM auto_results WHERE owner=? GROUP BY order_id) LIMIT 20001", (_owner(owner), _owner(owner))).fetchall()
        if len(rows) > 20000:
            raise FlowError("自动结果超过当前汇总上限，需归档；未返回截断统计", 413)
        return {item["orderId"]: item for item in (json.loads(row["body"]) for row in rows)}

    def active(self, owner):
        with self.db() as db:
            db.execute("UPDATE auto_jobs SET status='failed' WHERE owner=? AND status IN ('queued','running') AND updated<?", (_owner(owner), time.time() - 600))
            row = db.execute("SELECT body,status FROM auto_jobs WHERE owner=? ORDER BY rowid DESC LIMIT 1", (_owner(owner),)).fetchone()
        if row is None:
            return None
        body = json.loads(row["body"])
        body["status"] = row["status"]
        body.pop("targets", None)
        return body

    def result(self, owner, identifier):
        with self.db() as db:
            row = db.execute("SELECT body FROM auto_results WHERE owner=? AND order_id=? ORDER BY rowid DESC LIMIT 1", (_owner(owner), str(order_id(identifier)))).fetchone()
            if not row:
                return None
            body = json.loads(row["body"])
            body["samples"] = [json.loads(item["body"]) for item in db.execute("SELECT body FROM auto_samples WHERE owner=? AND result_id=? ORDER BY rowid DESC", (_owner(owner), body["id"]))]
        return body

    def sampling(self, owner):
        with self.db() as db:
            rows = db.execute("SELECT result_id,body FROM auto_samples WHERE owner=? AND rowid IN (SELECT MAX(rowid) FROM auto_samples WHERE owner=? GROUP BY result_id)", (_owner(owner), _owner(owner))).fetchall()
        return {row["result_id"]: json.loads(row["body"])["outcome"] for row in rows}

    def sample(self, owner, identifier, expected_id, outcome, reason):
        from .risk_verification_catalog import RiskVerificationCatalog
        if not isinstance(outcome, str) or outcome not in {"confirmed", "disputed"} or not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise FlowError("抽查结果和说明必填，说明最多2000字")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT id,body FROM auto_results WHERE owner=? AND order_id=? ORDER BY rowid DESC LIMIT 1", (_owner(owner), str(order_id(identifier)))).fetchone()
            if current is None or current["id"] != expected_id:
                raise FlowError("自动结果已改变，请刷新后再抽查", 409)
            catalog = RiskVerificationCatalog(self.config)
            connection = cursor = None
            try:
                connection = catalog._connect(); cursor = connection.cursor()
                cursor.execute("SELECT order_id AS id,profit_reason_type,update_time FROM bi_risk_order_day WHERE order_id=%s ORDER BY issue_date DESC LIMIT 1", (order_id(identifier),))
                rows = _rows(cursor)
                if not rows or not self.matches(json.loads(current["body"]), rows[0]):
                    raise FlowError("源版本已改变，需重新核实后再抽查", 409)
            finally:
                catalog._close(cursor, connection)
            body = {"id": uuid.uuid4().hex, "resultId": expected_id, "outcome": outcome, "reason": reason.strip(), "at": now(), "operator": _owner(owner)}
            db.execute("INSERT INTO auto_samples VALUES(?,?,?,?)", (body["id"], _owner(owner), expected_id, json.dumps(body, ensure_ascii=False)))
        return body

    def submit(self, owner, start, end, reason=None, force=False):
        from .risk_verification_catalog import RiskVerificationCatalog
        from .risk_verification_overview import RiskVerificationOverview, _period
        if reason is not None and (not isinstance(reason, str) or reason != "RLA013"):
            raise FlowError("当前类型规则未接入，不能自动套用佣金规则")
        if type(force) is not bool:
            raise FlowError("重新核实标记须为布尔值")
        first, last = _period(start, end)
        active = self.active(owner)
        if active and active["status"] in {"queued", "running"}:
            return active
        catalog = RiskVerificationCatalog(self.config)
        connection = cursor = None
        try:
            connection = catalog._connect(); cursor = connection.cursor()
            catalog.coverage(cursor, first, last)
            scope, values = RiskVerificationOverview._scope(first, last, "RLA013")
            # Explicit capacity gate: never label a truncated candidate set complete.
            cursor.execute(f"SELECT o.order_id AS id,o.profit_reason_type,o.update_time FROM bi_risk_order_day o WHERE {scope} ORDER BY o.order_id LIMIT 2001", tuple(values))
            rows = _rows(cursor)
            if len(rows) > 2000:
                raise FlowError("当前范围超过2000单，请缩小出票日期后自动核实", 413)
        finally:
            catalog._close(cursor, connection)
        latest = self.latest(owner)
        if force and len(rows) > 200:
            raise FlowError("单次重新核实最多200单，请缩小日期范围", 413)
        targets = rows if force else [row for row in rows if not self.matches(latest.get(str(row["id"])), row)]
        remaining = max(0, len(targets) - 200)
        targets = targets[:200]
        if not targets:
            return {"id": None, "status": "complete", "done": 0, "total": 0, "remaining": 0}
        body = {"id": uuid.uuid4().hex, "status": "queued", "done": 0, "total": len(targets), "remaining": remaining, "startDate": start, "endDate": end, "createdAt": now(), "targets": targets}
        try:
            with self.db() as db:
                db.execute("INSERT INTO auto_jobs VALUES(?,?,?,?,?)", (body["id"], _owner(owner), "queued", time.time(), json.dumps(body, ensure_ascii=False)))
        except sqlite3.IntegrityError:
            return self.active(owner)
        EXECUTOR.submit(self.work, _owner(owner), body["id"])
        return {key: value for key, value in body.items() if key != "targets"}

    @staticmethod
    def matches(result, row):
        return bool(result and result["reasonCode"] == row["profit_reason_type"] and stamp(result["sourceUpdatedAt"]) == stamp(row["update_time"]) and result["ruleVersion"] == RULE_ID)

    def work(self, owner, job_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM auto_jobs WHERE id=? AND owner=? AND status='queued'", (job_id, owner)).fetchone()
            if row is None:
                return
            body = json.loads(row["body"])
            if db.execute("UPDATE auto_jobs SET status='running',updated=? WHERE id=? AND status='queued'", (time.time(), job_id)).rowcount != 1:
                return
        try:
            for target in body["targets"]:
                result = {"id": uuid.uuid4().hex, "orderId": str(target["id"]), "reasonCode": target["profit_reason_type"], "sourceUpdatedAt": target["update_time"], "checkedAt": now(), "ruleVersion": RULE_ID, "jobId": job_id}
                try:
                    evidence = read_evidence(self.config, target["id"])
                    if evidence["order"]["profit_reason_type"] != target["profit_reason_type"] or stamp(evidence["order"].get("update_time")) != stamp(target["update_time"]):
                        computed = {"status": "insufficient", "summary": "ERP源版本已改变，请先同步目录再重新核实", "tickets": [], "missing": ["同版本目录"]}
                    else:
                        computed = evaluate(evidence)
                    result.update(computed)
                    result["evidenceHash"] = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                except FlowError as error:
                    result.update(status="insufficient", summary=str(error), tickets=[], missing=["有效的同单证据"])
                except Exception:
                    LOG.exception("Automatic risk evidence/check failed")
                    result.update(status="failed", summary="自动取证或核算失败，请重试或联系管理员查看服务日志", tickets=[], missing=[])
                with self.db() as db:
                    # A reclaimed/failed job must not publish late results.
                    active = db.execute("SELECT status FROM auto_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
                    if active is None or active["status"] != "running":
                        return
                    db.execute("INSERT INTO auto_results VALUES(?,?,?,?,?)", (result["id"], owner, result["orderId"], time.time(), json.dumps(result, ensure_ascii=False)))
                    body["done"] += 1
                    db.execute("UPDATE auto_jobs SET updated=?,body=? WHERE id=?", (time.time(), json.dumps(body, ensure_ascii=False), job_id))
            with self.db() as db:
                db.execute("UPDATE auto_jobs SET status='complete',updated=? WHERE id=? AND status='running'", (time.time(), job_id))
        except Exception:
            LOG.exception("Automatic risk job failed")
            with self.db() as db:
                db.execute("UPDATE auto_jobs SET status='failed',updated=? WHERE id=?", (time.time(), job_id))
