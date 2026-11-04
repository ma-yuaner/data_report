"""Single-host durable risk cases, versioned human decisions and published knowledge."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .risk_verification_ai import RiskAI, RiskAIError

ZONE = timezone(timedelta(hours=8))
RULE_VERSION = "profit-reason-present-v1"
FORMULA_WARNING = "汇率亏损公式、比较基准和舍入标准尚未确认；AI不得据此自动认定亏损成立或责任。"
SAFE_NUMBERS = {"policy_tax", "policy_ticket_price", "policy_exchange_rate", "policy_ticket_price_cny", "policy_tax_cny",
                "issue_exchange_rate", "issue_ticket_price", "issue_tax", "issue_ticket_price_cny", "issue_tax_cny",
                "issue_cost_amount", "issue_cost_amount_cny", "sale_exchange_rate", "sale_ticket_price", "sale_tax",
                "sale_ticket_price_cny", "sale_tax_cny", "order_profit", "reward_amount", "issue_total_amount", "issue_total_amount_cny",
                "sale_total_amount", "sale_total_amount_cny", "finance_total_amount", "finance_total_amount_cny", "finance_exchange_rate", "issue_profit"}
SAFE_CODES = {"policy_currency", "issue_currency", "sale_currency", "finance_currency"}
IDENTITY_KEYS = {"id", "erpOrderId", "order_no", "ota_order_no", "passenger_name", "passenger_mobile", "cert_no", "issue_ticket_no",
                 "operator_name", "operator", "operator_content", "profit_remark"}


class FlowError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.now(ZONE).isoformat(timespec="seconds")


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _owner(value):
    if type(value) not in {int, str} or not re.fullmatch(r"[0-9]{1,19}", str(value)):
        raise FlowError("无效的操作人标识", 403)
    return str(value)


def _text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise FlowError(f"{label}不能为空且不能超过{limit}字")
    return value.strip()


def _version(value):
    if type(value) is not int or value < 1:
        raise FlowError("请提交当前整数版本")
    return value


def _sensitive(value):
    return bool(re.search(r"(?i)(?:bearer\s+|sk-[a-z0-9]{8,}|password\s*[:=]|api[_-]?key\s*[:=]|secret\s*[:=]|webhook|https?://)|(?<![0-9])1[3-9][0-9]{9}(?![0-9])|(?<![0-9])[0-9]{15,18}[0-9Xx]?(?![0-9])|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value))


def sanitized_payload(evidence):
    """No free-text logs, names, order IDs, ticket numbers or contact details leave this boundary."""
    items = []
    order = evidence.get("order") or {}
    value = order.get("profit_reason_type")
    category = "" if value is None else str(value).strip(" ")
    if not category or len(category) > 120 or _sensitive(category) or any(ord(char) < 32 for char in category):
        raise FlowError("盈亏原因分类为空或不适合外发，请人工核对", 400)
    items.append({"id": "order:classification", "kind": "classification", "profitReasonType": category})
    missing = []
    for key, block in (evidence.get("blocks") or {}).items():
        if not isinstance(block, dict):
            continue
        status = block.get("status")
        if status not in {"ready", "empty"} or block.get("complete") is not True:
            missing.append({"block": key, "status": status})
        if status not in {"ready", "truncated"}:
            continue
        for index, row in enumerate(block.get("records") or []):
            if not isinstance(row, dict):
                continue
            numbers, codes = {}, {}
            for field, value in row.items():
                if field in SAFE_NUMBERS and value is not None and not isinstance(value, bool) and re.fullmatch(r"-?[0-9]{1,30}(?:\.[0-9]{1,30})?", str(value)):
                    numbers[field] = str(value)
                if field in SAFE_CODES and isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value):
                    codes[field] = value
            if numbers or codes:
                items.append({"id": f"{key}:{index + 1}", "kind": key, "amounts": numbers, "currencies": codes})
    return {"ruleVersion": RULE_VERSION, "rule": "profit_reason_type非空仅表示待核查，不能判错",
            "formulaStatus": "unknown", "formulaWarning": FORMULA_WARNING, "evidence": items,
            "completeness": {"complete": evidence.get("complete") is True, "missing": missing},
            "privacy": "只发送白名单金额/币种/汇率及分类；身份、日志原文和订单号留在中台"}


class RiskVerificationFlow:
    def __init__(self, config):
        self.config = config
        root = Path(config.get("RISK_VERIFICATION_ROOT") or "/app/var/risk-verification").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.db = root / "workflow.sqlite3"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS risk_cases(id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS risk_case_owner ON risk_cases(owner);
                CREATE TABLE IF NOT EXISTS risk_knowledge(id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS risk_knowledge_owner ON risk_knowledge(owner);
                CREATE TABLE IF NOT EXISTS risk_calls(id TEXT PRIMARY KEY, owner TEXT NOT NULL, case_id TEXT NOT NULL, operation TEXT NOT NULL, day TEXT NOT NULL, status TEXT NOT NULL);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(str(self.db), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _load(db, table, owner, identifier):
        row = db.execute(f"SELECT body FROM {table} WHERE id=? AND owner=?", (identifier, _owner(owner))).fetchone()
        if row is None:
            raise FlowError("记录不存在或无权访问", 404)
        return json.loads(row["body"])

    @staticmethod
    def _expect(body, version):
        if body["version"] != _version(version):
            raise FlowError("记录已更新，请刷新后重试", 409)
        if body.get("activeOperation"):
            raise FlowError("当前已有AI操作进行中，请稍后刷新", 409)

    @staticmethod
    def _save(db, table, owner, body):
        db.execute(f"UPDATE {table} SET version=?,body=? WHERE id=? AND owner=?", (body["version"], _dump(body), body["id"], _owner(owner)))

    def create(self, owner, evidence):
        owner = _owner(owner)
        if not isinstance(evidence, dict) or not isinstance(evidence.get("order"), dict) or not isinstance(evidence.get("blocks"), dict):
            raise FlowError("必须提供服务端取得的订单证据包")
        identifier = str(evidence.get("erpOrderId") or "")
        if not re.fullmatch(r"[1-9][0-9]{0,18}", identifier) or str(evidence["order"].get("id")) != identifier:
            raise FlowError("订单证据身份不匹配")
        category = evidence["order"].get("profit_reason_type")
        if category is None or not str(category).strip(" "):
            raise FlowError("该订单没有盈亏原因分类，不满足当前待核查规则")
        for block in evidence["blocks"].values():
            if not isinstance(block, dict):
                raise FlowError("证据结构无效")
            for row in block.get("records") or []:
                if not isinstance(row, dict) or "order_id" in row and str(row["order_id"]) != identifier:
                    raise FlowError("子业务证据与主订单身份不匹配")
        try:
            raw = _dump(evidence)
        except (TypeError, ValueError):
            raise FlowError("证据不能序列化，请保留十进制金额字符串") from None
        if len(raw.encode("utf-8")) > 2_000_000:
            raise FlowError("证据包超过2MB，请缩小证据范围", 413)
        frozen = json.loads(raw)
        now = _now()
        body = {"id": uuid.uuid4().hex, "version": 1, "state": "evidence_ready", "evidence": frozen,
                "evidenceFingerprint": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "ruleVersion": RULE_VERSION,
                "formulaStatus": "unknown", "warnings": [FORMULA_WARNING], "reviews": [], "confirmation": None,
                "confirmationHistory": [], "analyses": [], "knowledgeIds": [], "failures": [], "activeOperation": None,
                "createdAt": now, "updatedAt": now}
        with self._db() as db:
            db.execute("INSERT INTO risk_cases VALUES(?,?,?,?)", (body["id"], owner, 1, _dump(body)))
        return body

    def list_cases(self, owner):
        with self._db() as db:
            rows = db.execute("SELECT body FROM risk_cases WHERE owner=? ORDER BY rowid DESC LIMIT 200", (_owner(owner),)).fetchall()
        result = []
        for row in rows:
            case = json.loads(row["body"])
            result.append({key: case[key] for key in ("id", "version", "state", "createdAt", "updatedAt", "activeOperation")}
                          | {"erpOrderId": case["evidence"]["erpOrderId"], "profitReasonType": case["evidence"]["order"]["profit_reason_type"]})
        return result

    def get(self, owner, identifier):
        with self._db() as db:
            return self._load(db, "risk_cases", owner, identifier)

    def list_knowledge(self, owner):
        with self._db() as db:
            rows = db.execute("SELECT body FROM risk_knowledge WHERE owner=? ORDER BY rowid DESC LIMIT 200", (_owner(owner),)).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def _retrieve(self, owner, evidence):
        category = (evidence.get("order") or {}).get("profit_reason_type")
        query = "" if category is None else str(category).strip(" ")
        terms = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2}", query))
        if not terms:
            return []
        matches = []
        for knowledge in self.list_knowledge(owner):
            if knowledge["status"] != "published":
                continue
            try:
                source = self.get(owner, knowledge["caseId"])
            except FlowError:
                continue
            if not source.get("confirmation") or knowledge["confirmationFingerprint"] != hashlib.sha256(_dump(source["confirmation"]).encode()).hexdigest():
                continue
            haystack = " ".join(knowledge[key] for key in ("title", "content", "scope"))
            score = sum(term in haystack for term in terms)
            if score:
                matches.append((score, knowledge))
        return [item for _, item in sorted(matches, key=lambda pair: (-pair[0], pair[1]["id"]))[:5]]

    def preview(self, owner, identifier):
        case = self.get(owner, identifier)
        knowledge = self._retrieve(owner, case["evidence"])
        payload = sanitized_payload(case["evidence"])
        payload["knowledge"] = [{key: item[key] for key in ("id", "version", "title", "content", "scope", "source")} for item in knowledge]
        return {"payload": payload, "retrievedKnowledge": [{key: item[key] for key in ("id", "version", "title")} for item in knowledge],
                "notice": "可预览本次允许外发的内容；知识仅检索本人已发布版本，未发送请求"}

    @staticmethod
    def _validate_result(result, payload):
        if not isinstance(result, dict):
            raise FlowError("模型结果必须为对象", 502)
        summary = _text(result.get("summary"), "模型摘要", 3000)
        outcome = result.get("outcome")
        if outcome not in {"supported", "contradicted", "insufficient"}:
            raise FlowError("模型结果状态无效", 502)
        evidence_ids = {item["id"] for item in payload["evidence"]}
        knowledge_ids = {item["id"] for item in payload.get("knowledge", [])}
        findings = result.get("findings")
        if not isinstance(findings, list) or len(findings) > 20:
            raise FlowError("模型发现列表无效", 502)
        clean_findings = []
        for finding in findings:
            if not isinstance(finding, dict):
                raise FlowError("模型发现结构无效", 502)
            text = _text(finding.get("text"), "模型发现", 2000)
            citations = finding.get("citations")
            if not isinstance(citations, list) or not citations or len(citations) > 30 or any(not isinstance(value, str) or value not in evidence_ids for value in citations):
                raise FlowError("模型引用了本次证据之外的内容，未保存成功结果", 502)
            clean_findings.append({"text": text, "citations": list(dict.fromkeys(citations))})
        missing = result.get("missingEvidence")
        references = result.get("knowledgeCitations")
        if not isinstance(missing, list) or len(missing) > 20 or any(not isinstance(text, str) or not text.strip() or len(text) > 1000 for text in missing):
            raise FlowError("模型缺失证据列表无效", 502)
        if not isinstance(references, list) or len(references) > 10 or any(not isinstance(value, str) or value not in knowledge_ids for value in references):
            raise FlowError("模型引用了未发布或本次未检索知识", 502)
        return {"summary": summary, "modelOutcome": outcome, "effectiveOutcome": "insufficient",
                "findings": clean_findings, "missingEvidence": missing, "knowledgeCitations": list(dict.fromkeys(references)),
                "warnings": [FORMULA_WARNING], "humanConfirmationRequired": True}

    def _ai(self, owner, identifier, version, operation):
        owner = _owner(owner)
        # Fail before reserving a call when disabled. Never use an old project's config or key.
        gateway = RiskAI(self.config)
        if not gateway.status()["enabled"] or not gateway.status()["configured"]:
            raise FlowError("风控AI尚未启用或未配置，请由管理员配置本项目模型连接", 503)
        token = uuid.uuid4().hex
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            case = self._load(db, "risk_cases", owner, identifier)
            self._expect(case, version)
            if operation == "analyze" and case.get("confirmation") is None:
                raise FlowError("请先人工确认当前审核结论，再进行分析", 409)
            if len(case.get("failures") or []) >= 3:
                raise FlowError("该证据版本已失败3次，请核对配置或重新取得证据后再建案例", 409)
            day = datetime.now(ZONE).date().isoformat()
            used = db.execute("SELECT COUNT(*) FROM risk_calls WHERE day=?", (day,)).fetchone()[0]
            daily_limit = max(1, min(1000, int(self.config.get("RISK_AI_DAILY_CALL_LIMIT", 40))))
            if used >= daily_limit:
                raise FlowError("今日风控AI调用预算已用完，未发送请求", 429)
            payload = self.preview(owner, identifier)["payload"]
            if operation == "analyze":
                payload["humanConfirmation"] = {key: case["confirmation"][key] for key in ("conclusion", "override", "warnings")}
                # Human free text may contain identity or sensitive data: it stays in the local case.
            case["activeOperation"] = {"id": token, "operation": operation, "startedAt": _now()}
            self._save(db, "risk_cases", owner, case)
            db.execute("INSERT INTO risk_calls VALUES(?,?,?,?,?,?)", (token, owner, identifier, operation, day, "running"))
        try:
            run = gateway.call(operation, payload)
            clean = self._validate_result(run["result"], payload)
            run["result"] = clean
        except Exception as error:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._load(db, "risk_cases", owner, identifier)
                if (current.get("activeOperation") or {}).get("id") == token:
                    current["activeOperation"] = None
                    current["version"] += 1
                    current["updatedAt"] = _now()
                    current["failures"].append({"operation": operation, "at": _now(), "code": getattr(error, "code", "AI_RESULT_REJECTED")})
                    self._save(db, "risk_cases", owner, current)
                db.execute("UPDATE risk_calls SET status='failed' WHERE id=?", (token,))
            if isinstance(error, (RiskAIError, FlowError)):
                raise FlowError(str(error), error.status) from None
            raise FlowError("模型处理失败，未保存成功结果；请刷新后核对状态", 503) from None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._load(db, "risk_cases", owner, identifier)
            if current["version"] != version or (current.get("activeOperation") or {}).get("id") != token:
                db.execute("UPDATE risk_calls SET status='stale' WHERE id=?", (token,))
                raise FlowError("审核期间记录发生变化，请刷新；未覆盖现有结果", 409)
            run.update({"at": _now(), "evidenceFingerprint": current["evidenceFingerprint"], "retrievedKnowledge": [{"id": item["id"], "version": item["version"]} for item in payload.get("knowledge", [])]})
            current["reviews" if operation == "review" else "analyses"].append(run)
            current["state"] = "reviewed" if operation == "review" else "analyzed"
            if operation == "review" and current.get("confirmation"):
                current["confirmationHistory"].append(current["confirmation"])
                current["confirmation"] = None
            current["activeOperation"] = None
            current["version"] += 1
            current["updatedAt"] = _now()
            self._save(db, "risk_cases", owner, current)
            db.execute("UPDATE risk_calls SET status='succeeded' WHERE id=?", (token,))
        return current

    def review(self, owner, identifier, version):
        return self._ai(owner, identifier, version, "review")

    def analyze(self, owner, identifier, version):
        return self._ai(owner, identifier, version, "analyze")

    def recover(self, owner, identifier, version):
        """Explicitly release an interrupted call after its maximum network lifetime.

        Does not retry, refund budget, or pretend that a provider never received the request.
        A late response cannot overwrite the recovered version/token.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            case = self._load(db, "risk_cases", owner, identifier)
            if case["version"] != _version(version):
                raise FlowError("记录已更新，请刷新后重试", 409)
            operation = case.get("activeOperation")
            if not operation:
                return case
            try:
                age = (datetime.now(ZONE) - datetime.fromisoformat(operation["startedAt"])).total_seconds()
            except (ValueError, TypeError):
                raise FlowError("操作时间记录无效，请管理员核查存储", 409) from None
            if age < 180:
                raise FlowError("AI操作仍在有效等待时间内，请稍后刷新；不会自动重试", 409)
            case["failures"].append({"operation": operation["operation"], "at": _now(), "code": "AI_INTERRUPTED_RESULT_UNKNOWN"})
            case["activeOperation"] = None
            case["version"] += 1
            case["updatedAt"] = _now()
            self._save(db, "risk_cases", owner, case)
            db.execute("UPDATE risk_calls SET status='unknown' WHERE id=?", (operation["id"],))
        return case

    def confirm(self, owner, identifier, version, conclusion, reason):
        if conclusion not in {"supported", "contradicted", "insufficient"}:
            raise FlowError("人工结论只支持证据支持、证据矛盾或证据不足")
        reason = _text(reason, "人工确认依据", 4000)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            case = self._load(db, "risk_cases", owner, identifier)
            self._expect(case, version)
            if case.get("confirmation"):
                case["confirmationHistory"].append(case["confirmation"])
            case["confirmation"] = {"conclusion": conclusion, "reason": reason, "owner": _owner(owner), "at": _now(),
                                    "override": conclusion != "insufficient", "warnings": [FORMULA_WARNING],
                                    "reviewRunId": case["reviews"][-1]["runId"] if case["reviews"] else None,
                                    "evidenceFingerprint": case["evidenceFingerprint"]}
            case["state"] = "confirmed"
            case["version"] += 1
            case["updatedAt"] = _now()
            self._save(db, "risk_cases", owner, case)
        return case

    @staticmethod
    def _knowledge_content(case, title, content, scope, source):
        fields = {"title": _text(title, "知识标题", 120), "content": _text(content, "知识内容", 6000),
                  "scope": _text(scope, "适用范围", 1000), "source": _text(source, "人工确认来源", 1000)}
        combined = "\n".join(fields.values())
        if _sensitive(combined):
            raise FlowError("知识只能保存人工确认的规则摘要，不能包含凭据、链接或联系方式")
        def identities(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in IDENTITY_KEYS and isinstance(item, (str, int)):
                        text = str(item).strip()
                        if len(text) >= (2 if key in {"passenger_name", "operator_name", "operator"} else 6):
                            yield text
                    yield from identities(item)
            elif isinstance(value, list):
                for item in value:
                    yield from identities(item)
        if any(value in combined for value in identities(case["evidence"])):
            raise FlowError("知识内容包含本单身份或原始日志，请改为不含原始订单的通用规则摘要")
        return fields

    def draft_knowledge(self, owner, identifier, version, title, content, scope, source):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            case = self._load(db, "risk_cases", owner, identifier)
            self._expect(case, version)
            if not case.get("confirmation"):
                raise FlowError("请先人工确认本案例，再沉淀知识草稿", 409)
            fields = self._knowledge_content(case, title, content, scope, source)
            knowledge = {"id": uuid.uuid4().hex, "version": 1, "status": "draft", **fields, "caseId": identifier,
                         "caseVersion": case["version"], "confirmationFingerprint": hashlib.sha256(_dump(case["confirmation"]).encode()).hexdigest(),
                         "createdAt": _now(), "publishedAt": None}
            db.execute("INSERT INTO risk_knowledge VALUES(?,?,?,?)", (knowledge["id"], _owner(owner), 1, _dump(knowledge)))
            case["knowledgeIds"].append(knowledge["id"])
            case["version"] += 1
            case["updatedAt"] = _now()
            self._save(db, "risk_cases", owner, case)
        return knowledge

    def publish_knowledge(self, owner, identifier, version):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self._load(db, "risk_knowledge", owner, identifier)
            self._expect(item, version)
            if item["status"] != "draft":
                raise FlowError("仅草稿可以发布，已发布知识不可原地改写", 409)
            case = self._load(db, "risk_cases", owner, item["caseId"])
            if item["confirmationFingerprint"] != hashlib.sha256(_dump(case.get("confirmation")).encode()).hexdigest():
                raise FlowError("知识来源结论已变化，请根据当前确认重新建立草稿", 409)
            self._knowledge_content(case, item["title"], item["content"], item["scope"], item["source"])
            item.update(status="published", version=item["version"] + 1, publishedAt=_now(), publishedBy=_owner(owner))
            self._save(db, "risk_knowledge", owner, item)
        return item
