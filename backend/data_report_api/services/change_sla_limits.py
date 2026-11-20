"""Shared SLA rule catalog. It is independent of the ERP SLA evaluator."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
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


def _rules_only(payload):
    return [{field: row.get(field, "") for field in ("platform", *RULES)} for row in json.loads(payload)]


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

    def _history(self):
        if not self.path.is_file():
            return []
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            try:
                entries = db.execute("""
                    SELECT revision, records, updated_at, updated_by FROM change_sla_limits_history
                    WHERE revision < (SELECT revision FROM change_sla_limits WHERE id=1)
                    UNION ALL
                    SELECT revision, records, updated_at, updated_by FROM change_sla_limits WHERE id=1
                    ORDER BY revision
                """).fetchall()
            except sqlite3.OperationalError as error:
                if str(error) == "no such table: change_sla_limits":
                    return []
                if str(error) != "no such table: change_sla_limits_history":
                    raise
                entries = db.execute("""
                    SELECT revision, records, updated_at, updated_by FROM change_sla_limits WHERE id=1
                """).fetchall()
        return [(revision, records, int(datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc).timestamp() * 1000), actor)
                for revision, records, updated_at, actor in entries]

    def export_rule_history(self):
        entries = self._history()
        if not entries:
            raise InvalidLimit("请先保存时限配置")
        return {
            "schemaVersion": 1,
            "versions": [
                {"revision": revision, "effectiveFromMs": effective_ms, "rows": _rules_only(records)}
                for revision, records, effective_ms, _ in entries
            ],
        }

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

        with self._edit() as (revision, records, persist):
            if body["revision"] != revision:
                raise LimitsChanged("配置已被他人更新，请刷新列表后再保存")
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
            persist(revision, records, str(actor))
        return {"revision": revision, "rows": records}

    @contextmanager
    def _edit(self):
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
            db.execute("""
                INSERT OR IGNORE INTO change_sla_limits_history (revision, records, updated_by, updated_at)
                SELECT revision, records, updated_by, updated_at FROM change_sla_limits WHERE id=1
            """)

            def persist(revision, records, actor):
                payload = json.dumps(records, ensure_ascii=False)
                db.execute("""
                    INSERT INTO change_sla_limits (id, revision, records, updated_by, updated_at)
                    VALUES (1, ?, ?, ?, STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
                    ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, records=excluded.records,
                        updated_by=excluded.updated_by, updated_at=excluded.updated_at
                """, (revision, payload, str(actor)))
                db.execute("""
                    INSERT INTO change_sla_limits_history (revision, records, updated_by, updated_at)
                    SELECT revision, records, updated_by, updated_at FROM change_sla_limits WHERE id=1
                """)

            yield revision, records, persist


class SharedChangeSlaLimits(ChangeSlaLimits):
    """BI is authoritative after copying the existing local catalog once."""

    _LATEST = """
        SELECT revision, records, effective_from_ms FROM bi_change_sla_rule_revision
        WHERE revision > 0 ORDER BY revision DESC LIMIT 1
    """
    _INSERT = """
        INSERT INTO bi_change_sla_rule_revision (revision, records, rules, effective_from_ms, updated_by)
        VALUES (%s, %s, %s, %s, %s)
    """

    def __init__(self, root, connect):
        super().__init__(root)
        self.connect_shared = connect

    def get(self):
        with closing(self.connect_shared()) as db, closing(db.cursor()) as cursor:
            cursor.execute(self._LATEST)
            row = cursor.fetchone()
        if row:
            return {"revision": row[0], "rows": json.loads(row[1])}
        with self._edit() as (revision, records, _):
            return {"revision": revision, "rows": records}

    def _history(self):
        self.get()  # Initialize the shared catalog if an existing local catalog needs copying.
        with closing(self.connect_shared()) as db, closing(db.cursor()) as cursor:
            cursor.execute("""
                SELECT revision, records, effective_from_ms, updated_by
                FROM bi_change_sla_rule_revision WHERE revision > 0 ORDER BY revision
            """)
            return cursor.fetchall()

    @contextmanager
    def _edit(self):
        with closing(self.connect_shared()) as db, closing(db.cursor()) as cursor:
            db.begin()
            try:
                cursor.execute("SELECT revision FROM bi_change_sla_rule_revision WHERE revision=0 FOR UPDATE")
                if cursor.fetchone() is None:
                    raise RuntimeError("改签规则台账缺少初始化锁行")
                cursor.execute(self._LATEST + " FOR UPDATE")
                latest = cursor.fetchone()
                if latest is None:
                    previous = super()._history()
                    for revision, payload, effective_ms, actor in previous:
                        cursor.execute(self._INSERT, (
                            revision, payload, json.dumps(_rules_only(payload), ensure_ascii=False), effective_ms, actor,
                        ))
                    if previous:
                        latest = previous[-1][:3]
                current_revision, payload, last_effective = latest or (0, "[]", 0)

                def persist(revision, records, actor):
                    cursor.execute("SELECT TIMESTAMPDIFF(MICROSECOND, '1970-01-01', UTC_TIMESTAMP(3)) DIV 1000")
                    effective_ms = max(cursor.fetchone()[0], last_effective)
                    payload = json.dumps(records, ensure_ascii=False)
                    cursor.execute(self._INSERT, (
                        revision, payload, json.dumps(_rules_only(payload), ensure_ascii=False), effective_ms, actor,
                    ))

                yield current_revision, json.loads(payload), persist
                db.commit()
            except BaseException:
                db.rollback()
                raise
