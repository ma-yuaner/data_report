"""Shared SLA rule catalog. It is independent of the ERP SLA evaluator."""
from contextlib import closing
from pathlib import Path
from uuid import uuid4
import json
import sqlite3

FIELDS = (
    "platform", "owner", "department", "group", "channel", "auditMode",
    "auditVoluntary", "auditInvoluntary", "operationVoluntary", "operationInvoluntary",
)
RULES = FIELDS[-4:]
MAX_RECORDS = 1000


class InvalidLimit(ValueError):
    pass


class LimitsChanged(ValueError):
    pass


def _record(data):
    if not isinstance(data, dict):
        raise InvalidLimit("配置必须是对象")
    result = {}
    for field in FIELDS:
        raw = data.get(field, "")
        if not isinstance(raw, str) or len(raw) > 2000:
            raise InvalidLimit(f"配置字段无效或过长：{field}")
        result[field] = raw.strip()
    if not result["platform"] or not any(result[field] for field in RULES):
        raise InvalidLimit("请填写 OTA 平台及至少一项时限")
    if result["auditMode"] not in {"", "是", "手工", "否"}:
        raise InvalidLimit("审单方式必须为是、手工或否")
    return result


class ChangeSlaLimits:
    def __init__(self, root):
        self.path = Path(root) / "change-sla-limits.sqlite3"

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _read(db):
        row = db.execute("SELECT revision, records FROM change_sla_limits WHERE id=1").fetchone()
        return (row[0], json.loads(row[1])) if row else (0, [])

    def get(self):
        if not self.path.exists():
            return {"revision": 0, "rows": []}
        with closing(self._connect()) as db:
            try:
                revision, rows = self._read(db)
            except sqlite3.OperationalError as error:
                if str(error) != "no such table: change_sla_limits":
                    raise
                revision, rows = 0, []
        return {"revision": revision, "rows": rows}

    def save(self, body, actor):
        if not isinstance(body, dict) or type(body.get("revision")) is not int:
            raise InvalidLimit("配置版本无效，请刷新后重试")
        operation = body.get("action")
        if operation == "import":
            raw_rows = body.get("rows")
            if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= MAX_RECORDS:
                raise InvalidLimit("导入需要 1 至 1000 条配置")
            incoming = []
            for raw in raw_rows:
                row = _record(raw)
                source_row = raw.get("sourceRow")
                if type(source_row) is not int or not 1 <= source_row <= 1048576:
                    raise InvalidLimit("导入记录缺少有效的源表行号")
                incoming.append({"id": f"workbook-{source_row}", "sourceRow": source_row, **row})
            if len({row["id"] for row in incoming}) != len(incoming):
                raise InvalidLimit("导入文件有重复源表行号")
        elif operation == "upsert":
            raw = body.get("record")
            record = _record(raw)
            identifier = raw.get("id")
            if identifier is not None and (not isinstance(identifier, str) or not identifier):
                raise InvalidLimit("配置编号无效")
        else:
            raise InvalidLimit("不支持的配置操作")

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                CREATE TABLE IF NOT EXISTS change_sla_limits (
                    id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL,
                    records TEXT NOT NULL, updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS change_sla_limits_history (
                    revision INTEGER PRIMARY KEY, records TEXT NOT NULL,
                    updated_by TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            revision, records = self._read(db)
            if body["revision"] != revision:
                raise LimitsChanged("配置已被他人更新，请刷新列表后再保存")
            db.execute("""
                INSERT OR IGNORE INTO change_sla_limits_history (revision, records, updated_by, updated_at)
                SELECT revision, records, updated_by, updated_at FROM change_sla_limits WHERE id=1
            """)
            if operation == "import":
                current_ids = {row["id"] for row in records}
                additions = [row for row in incoming if row["id"] not in current_ids]
                if not additions:
                    return {"revision": revision, "rows": records}
                records.extend(additions)
            elif identifier is None:
                records.append({"id": uuid4().hex, **record})
            else:
                for index, old in enumerate(records):
                    if old["id"] == identifier:
                        records[index] = {**old, **record}
                        break
                else:
                    raise InvalidLimit("配置不存在，请刷新列表")
            if len(records) > MAX_RECORDS:
                raise InvalidLimit("配置数量不能超过 1000 条")
            revision += 1
            payload = json.dumps(records, ensure_ascii=False)
            db.execute("""
                INSERT INTO change_sla_limits (id, revision, records, updated_by)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, records=excluded.records,
                    updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
            """, (revision, payload, str(actor)))
            db.execute("""
                INSERT INTO change_sla_limits_history (revision, records, updated_by) VALUES (?, ?, ?)
            """, (revision, payload, str(actor)))
        return {"revision": revision, "rows": records}
