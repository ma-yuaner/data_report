"""Shared administrator problem taxonomy; never changes ERP or automatic results."""
import hashlib
import json
import unicodedata
import uuid

from .risk_auto_store import RiskAutoStore
from .risk_order_evidence import order_id
from .risk_verification_flow import FlowError, _owner


def text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise FlowError(f"{label}必填，最多{limit}字")
    return value.strip()


class RiskProblemTags:
    def __init__(self, config):
        self.store = RiskAutoStore(config)

    def types(self):
        with self.store.db() as db:
            rows = db.execute("SELECT id,name,created_by,created_at FROM bi_risk_problem_types ORDER BY name_key,id LIMIT 1001").fetchall()
        if len(rows) > 1000:
            raise FlowError("问题类型超过1000项，请先治理类型目录", 413)
        return [dict(row) for row in rows]

    def create(self, owner, name):
        name = text(name, 60, "问题类型")
        key = unicodedata.normalize('NFKC', name).casefold()
        if len(key) > 120 or any(ord(char) < 32 for char in name):
            raise FlowError("问题类型名称过长或包含控制字符")
        with self.store.db() as db:
            db.execute("INSERT INTO bi_risk_problem_types (id,name,name_key,created_by) VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE name_key=VALUES(name_key)",
                       (uuid.uuid4().hex, name, key, _owner(owner)))
            row = db.execute("SELECT id,name,created_by,created_at FROM bi_risk_problem_types WHERE name_key=?", (key,)).fetchone()
        return dict(row)

    def list(self, identifier):
        with self.store.db() as db:
            rows = db.execute("SELECT id,order_id,type_id,type_name,reason,created_by,created_at FROM bi_risk_order_problem_tags WHERE order_id=? ORDER BY created_at DESC,id DESC LIMIT 501", (str(order_id(identifier)),)).fetchall()
        if len(rows) > 500:
            raise FlowError("订单标签超过500条，请联系管理员核对历史", 413)
        return [dict(row) for row in rows]

    def save(self, owner, identifier, type_ids, reason):
        owner, identifier = _owner(owner), str(order_id(identifier))
        reason = text(reason, 2000, "备注原因")
        if not isinstance(type_ids, list) or not 1 <= len(type_ids) <= 10 or any(not isinstance(item, str) or len(item) != 32 for item in type_ids) or len(set(type_ids)) != len(type_ids):
            raise FlowError("请选择1至10个不重复的问题类型")
        with self.store.db() as db:
            source = db.execute("SELECT profit_reason_type,update_time,etl_run_id FROM bi_risk_order_day WHERE order_id=? ORDER BY issue_date DESC LIMIT 1", (identifier,)).fetchone()
            if not source:
                raise FlowError("订单不在已同步风控目录中，不能保存标签", 409)
            types = db.execute("SELECT id,name FROM bi_risk_problem_types WHERE id IN (" + ','.join('?' for _ in type_ids) + ")", tuple(type_ids)).fetchall()
            if len(types) != len(type_ids):
                raise FlowError("问题类型已改变，请刷新后选择", 409)
            snapshot = json.dumps(dict(source), ensure_ascii=False, default=str)
            for item in types:
                digest = hashlib.sha256(json.dumps([owner, identifier, item['id'], reason, snapshot], ensure_ascii=False).encode()).hexdigest()[:32]
                db.execute("INSERT INTO bi_risk_order_problem_tags (id,order_id,type_id,type_name,reason,created_by,source_snapshot) VALUES(?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE id=id",
                           (digest, identifier, item['id'], item['name'], reason, owner, snapshot))
        return self.list(identifier)
