"""Versioned, read-only structural inventory plus independently revised business dictionary."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..time_utils import business_now
from .core_asset_registry import CORE_TABLES
from .data_source import TABLE_SPECS
from .asset_catalog import ASSETS

_LOCK = threading.RLock()
FIELDS = {"businessUse": 2000, "grain": 1000, "businessKey": 1000, "timeField": 500,
          "timeMeaning": 1000, "domain": 100, "owner": 200, "refreshSla": 1000}
GAP_LABELS = {"missing_business_table_comment": "物理表注释缺失", "missing_column_comments": "物理字段注释不完整",
              "no_declared_primary_key": "未声明物理主键", "layer_unclassified": "分层待分类",
              "lineage_endpoint_unresolved": "依赖端点待核对"}


class InventoryError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "ASSET_INVALID"):
        self.message, self.status, self.code = message, status, code


def integer(value: Any, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise InventoryError("分页、跳数与版本参数必须为非负整数")
    number = int(value)
    if number > maximum:
        raise InventoryError("参数超过允许范围")
    return number


@lru_cache(maxsize=2)
def _load(root: str, version: str):
    path = Path(root) / "snapshots" / (version + ".json")
    if path.stat().st_size > 100_000_000:
        raise InventoryError("资产快照超过读取上限", 503)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != version:
        raise InventoryError("资产快照校验失败，未替换当前事实", 503)
    data = json.loads(raw)
    objects = {row["asset_id"]: row for row in data["tables"]}
    columns, gaps, keys, indexes, adjacency = (defaultdict(list) for _ in range(5))
    for name, target in [("columns", columns), ("gaps", gaps), ("keys", keys), ("indexes", indexes)]:
        for row in data.get(name, []):
            target[row["asset_id"]].append(row)
    for row in data["edges"]:
        for asset_id in {row["source_asset_id"], row["target_asset_id"]} - {""}:
            adjacency[asset_id].append(row)
    return data, objects, columns, gaps, keys, indexes, adjacency


class AssetInventory:
    def __init__(self, config: dict[str, Any]):
        self.root = Path(config["ASSET_INVENTORY_ROOT"]).resolve()

    def snapshot(self, expected: str | None = None):
        try:
            pointer = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
            version = pointer["version"]
            if not re.fullmatch(r"[a-f0-9]{64}", version):
                raise ValueError("invalid snapshot pointer")
            if expected and expected != version:
                raise InventoryError("资产快照已更新，请重新查询后继续", 409, "ASSET_SNAPSHOT_CHANGED")
            return version, _load(str(self.root), version)
        except InventoryError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            raise InventoryError("尚未发布有效资产快照，请先由部署人导入盘点包", 503, "ASSET_NOT_SYNCED") from None

    @contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.root / "dictionary.sqlite3", timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE IF NOT EXISTS asset_dictionary_draft (asset_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, base_revision INTEGER NOT NULL, body TEXT NOT NULL, snapshot_version TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS asset_dictionary_revision (asset_id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, snapshot_version TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL, PRIMARY KEY(asset_id, revision))")
            with db:
                yield db
        finally:
            db.close()

    def dictionaries(self):
        path = self.root / "dictionary.sqlite3"
        if not path.exists():
            return {}
        with _LOCK, self._db() as db:
            rows = db.execute("SELECT r.* FROM asset_dictionary_revision r JOIN (SELECT asset_id, MAX(revision) revision FROM asset_dictionary_revision GROUP BY asset_id) v ON r.asset_id=v.asset_id AND r.revision=v.revision").fetchall()
        return {row["asset_id"]: {"revision": row["revision"], "values": json.loads(row["body"]), "updatedAt": row["updated_at"]} for row in rows}

    def _object(self, row, dictionaries, gap_index):
        published = dictionaries.get(row["asset_id"])
        source_key = "ERP" if row["source"] == "ERP_MYSQL" and row["database"] == "sibedb" else "中台" if row["source"] == "MYSQL" and row["database"] == "sibebid" else ""
        known = next((item for item in CORE_TABLES if item["source"] == source_key and item["table"] == row["table"]), None)
        context = {"purpose": known["purpose"], "grain": known["grain"], "evidence": "项目已登记核心表契约；结构与业务口径分别核验"} if known else None
        engine = "hive" if row["source"] == "HIVE" and row["database"] == "lywz" else "mysql" if source_key == "中台" else None
        if engine:
            key = next((key for key, spec in TABLE_SPECS[engine].items() if spec.table == row["table"]), None)
            definition = next((item for item in ASSETS if item["key"] == key), None)
            if definition:
                context = {"purpose": definition["domain"] + "经营报表源表；" + definition["condition"], "grain": "沿用原报表粒度，源唯一键待业务核验",
                           "timeField": TABLE_SPECS[engine][key].time_field, "metrics": definition["metrics"], "evidence": "既有经营报表登记；不是新增业务口径确认"}
        return {**row, "column_count": int(row["column_count"]), "partition_column_count": int(row["partition_column_count"]),
                "dictionary": published or {"revision": 0, "values": {}, "updatedAt": None},
                "registeredContext": context,
                "gapCount": len(gap_index[row["asset_id"]]), "businessFreshness": "not_verified"}

    def summary(self):
        version, (data, objects, _, gaps, *_) = self.snapshot()
        dictionaries = self.dictionaries()
        return {"version": version, "publishedAt": data["publishedAt"], "databases": data["databases"],
                "objectCount": len(objects), "fieldCount": len(data["columns"]),
                "dictionaryCount": sum(key in objects for key in dictionaries),
                "layers": dict(Counter(row["layer_candidate"] for row in objects.values() if row["source"] == "HIVE")),
                "gapCounts": dict(Counter(row["gap"] for row in data["gaps"])), "gapLabels": GAP_LABELS,
                "evidenceCounts": dict(Counter(row["edge_type"] for row in data["edges"])),
                "edgeEvidenceCount": len(data["edges"]), "uniqueDependencyCount": len({(row["source_asset_id"] or row["source_reference"], row["target_asset_id"] or row["target_reference"], row["edge_type"]) for row in data["edges"]}),
                "matchedEvidenceCount": sum(row["endpoint_status"] == "both_exist" for row in data["edges"]),
                "runtimeEvidenceStatus": "not_collected", "coverage": data.get("coverage", {}),
                "scopeNote": "当前配置账号可见范围，业务字典、物理结构和运行证据分别管理"}

    def objects(self, args):
        if args.get("dictionaryState", "") not in {"", "maintained", "missing"}:
            raise InventoryError("字典维护状态不合法")
        version, (_, objects, _, gaps, *_) = self.snapshot(args.get("version"))
        dictionaries = self.dictionaries()
        words = str(args.get("search", "")).strip().lower().split()
        if len(" ".join(words)) > 300:
            raise InventoryError("搜索内容不能超过300字符")
        rows = [self._object(row, dictionaries, gaps) for row in objects.values()]
        rows = [row for row in rows if (not args.get("database") or row["source"] + "/" + row["database"] == args["database"])
                and (not args.get("layer") or row["layer_candidate"] == args["layer"])
                and (not args.get("objectType") or row["object_type"] == args["objectType"])
                and (not args.get("dictionaryState") or bool(row["dictionary"]["revision"]) == (args["dictionaryState"] == "maintained"))
                and all(word in " ".join([row["source"], row["database"], row["table"], row["table_comment"], *row["dictionary"]["values"].values()]).lower() for word in words)]
        rows.sort(key=lambda row: (row["source"], row["database"], row["table"]))
        page, size = integer(args.get("page"), 1, 1000000), integer(args.get("pageSize"), 20, 100)
        if not page or not size:
            raise InventoryError("页码与每页条数必须大于0")
        return {"version": version, "total": len(rows), "page": page, "pageSize": size, "items": rows[(page - 1) * size:page * size]}

    def detail(self, asset_id, version, include_draft=False):
        version, (_, objects, columns, gaps, keys, indexes, _) = self.snapshot(version)
        if asset_id not in objects:
            raise InventoryError("对象不在当前快照中", 404)
        return {"version": version, "object": self._object(objects[asset_id], self.dictionaries(), gaps),
                "columns": columns[asset_id], "keys": keys[asset_id], "indexes": indexes[asset_id],
                "gaps": gaps[asset_id], "dictionaryState": self.dictionary_state(asset_id, include_draft)}

    def dictionary_state(self, asset_id, include_draft):
        if not (self.root / "dictionary.sqlite3").exists():
            return {"publishedRevision": 0, "published": {}, "draftRevision": 0, "draft": None, "history": []}
        with _LOCK, self._db() as db:
            revisions = db.execute("SELECT * FROM asset_dictionary_revision WHERE asset_id=? ORDER BY revision DESC", (asset_id,)).fetchall()
            draft = db.execute("SELECT * FROM asset_dictionary_draft WHERE asset_id=?", (asset_id,)).fetchone() if include_draft else None
        return {"publishedRevision": revisions[0]["revision"] if revisions else 0,
                "published": json.loads(revisions[0]["body"]) if revisions else {},
                "draftRevision": draft["revision"] if draft else 0, "draft": json.loads(draft["body"]) if draft else None,
                "history": [{"revision": row["revision"], "values": json.loads(row["body"]), "snapshotVersion": row["snapshot_version"], "updatedAt": row["updated_at"]} for row in revisions[:30]]}

    def save_dictionary(self, asset_id, body, user, publish=False):
        if not body.get("version"):
            raise InventoryError("维护字典必须指定当前快照版本")
        version, (_, objects, *_) = self.snapshot(body.get("version"))
        if asset_id not in objects:
            raise InventoryError("对象不在当前快照中", 404)
        expected = integer(body.get("draftRevision"), 0, 2**31 - 1)
        base = integer(body.get("publishedRevision"), 0, 2**31 - 1)
        values = body.get("values")
        if not publish:
            if not isinstance(values, dict) or set(values) - FIELDS.keys():
                raise InventoryError("字典字段不合法")
            if any(not isinstance(value, str) or len(value) > FIELDS[key] for key, value in values.items()):
                raise InventoryError("字典内容类型或长度不合法")
            values = {key: values.get(key, "").strip() for key in FIELDS}
        now = business_now().isoformat(timespec="seconds")
        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            draft = db.execute("SELECT * FROM asset_dictionary_draft WHERE asset_id=?", (asset_id,)).fetchone()
            current = db.execute("SELECT COALESCE(MAX(revision),0) FROM asset_dictionary_revision WHERE asset_id=?", (asset_id,)).fetchone()[0]
            if (draft["revision"] if draft else 0) != expected or current != base:
                raise InventoryError("字典已由其他操作更新，请重新载入后核对；当前输入未自动覆盖", 409, "ASSET_DICTIONARY_CONFLICT")
            if publish:
                if not draft or draft["base_revision"] != current or draft["snapshot_version"] != version:
                    raise InventoryError("请先保存当前版本草稿再发布", 409)
                values = json.loads(draft["body"])
                if not any(values.values()):
                    raise InventoryError("空字典不能发布")
                db.execute("INSERT INTO asset_dictionary_revision VALUES (?,?,?,?,?,?)", (asset_id, current + 1, draft["body"], version, now, str(user["id"])))
                db.execute("DELETE FROM asset_dictionary_draft WHERE asset_id=?", (asset_id,))
            else:
                db.execute("INSERT OR REPLACE INTO asset_dictionary_draft VALUES (?,?,?,?,?,?,?)", (asset_id, expected + 1, current, json.dumps(values, ensure_ascii=False), version, now, str(user["id"])))
        return {"version": version, **self.dictionary_state(asset_id, True)}

    def lineage(self, asset_id, args):
        version, (data, objects, _, _, _, _, adjacent) = self.snapshot(args.get("version"))
        if asset_id not in objects:
            raise InventoryError("对象不在当前快照中", 404)
        if args.get("scope", "definition") not in {"definition", "runtime"}:
            raise InventoryError("不支持的证据范围")
        if args.get("scope") == "runtime":
            return {"version": version, "runtimeEvidenceStatus": "not_collected", "edges": [], "impacts": [], "unresolvedFrontier": None, "truncated": False}
        depth_limit = integer(args.get("depth"), 5, 10)
        if not depth_limit:
            raise InventoryError("影响分析至少展开1跳")
        visited, impacts, frontier, cut = {asset_id}, [], [asset_id], False
        outgoing = defaultdict(set)
        for row in data["edges"]:
            if row["endpoint_status"] == "both_exist":
                outgoing[row["source_asset_id"]].add(row["target_asset_id"])
        for depth in range(1, depth_limit + 1):
            next_frontier = []
            for source in frontier:
                for target in sorted(outgoing[source] - visited):
                    if len(impacts) >= 500:
                        cut = True
                        break
                    visited.add(target); next_frontier.append(target)
                    impacts.append({"asset_id": target, "depth": depth, "table": objects[target]["table"], "source": objects[target]["source"], "database": objects[target]["database"]})
            frontier = next_frontier
            if cut or not frontier:
                break
        cut = cut or any(outgoing[node] - visited for node in frontier)
        return {"version": version, "runtimeEvidenceStatus": "not_collected", "edges": adjacent[asset_id], "impacts": impacts,
                "unresolvedFrontier": sum(row["source_asset_id"] in visited and row["endpoint_status"] != "both_exist" for row in data["edges"]), "truncated": cut}

    def gaps(self, args):
        version, (data, objects, *_) = self.snapshot(args.get("version"))
        rows = [row for row in data["gaps"] if not args.get("gap") or row["gap"] == args["gap"]]
        page, size = integer(args.get("page"), 1, 1000000), integer(args.get("pageSize"), 20, 100)
        if not page or not size:
            raise InventoryError("页码与每页条数必须大于0")
        return {"version": version, "total": len(rows), "items": [{**row, "canLocate": row["asset_id"] in objects} for row in rows[(page - 1) * size:page * size]]}
