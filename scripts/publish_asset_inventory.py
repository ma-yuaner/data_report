"""Validate and atomically publish a locally reviewed inventory; never connects to a DB."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".asset-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish(inventory, root):
    data = {"publishedAt": datetime.now(timezone.utc).isoformat(), "formatVersion": 1}
    for name, filename in [("tables", "tables"), ("columns", "columns"), ("edges", "lineage"), ("gaps", "gaps"), ("databases", "databases"), ("keys", "keys"), ("indexes", "indexes")]:
        with (inventory / (filename + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
            data[name] = list(csv.DictReader(stream))
    ids = {row["asset_id"] for row in data["tables"]}
    if not ids or len(ids) != len(data["tables"]):
        raise ValueError("missing or duplicate object identities")
    if any(row["asset_id"] != "/".join([row["source"], row["instance_id"], row["database"], row["table"]]) for row in data["tables"]):
        raise ValueError("object identity does not match source instance")
    if any(row["asset_id"] not in ids for row in data["columns"]):
        raise ValueError("orphan column")
    if sum(int(row["column_count"]) for row in data["tables"]) != len(data["columns"]):
        raise ValueError("field coverage mismatch")
    for kind in ["databases", "tables"]:
        if any(row.get("status", row.get("schema_status", "")) != "complete" for row in data[kind]):
            raise ValueError("incomplete metadata cannot replace the published snapshot")
    counts = {(row["source"], row["database"]): int(row["object_count"]) for row in data["databases"]}
    for key, count in counts.items():
        if sum((row["source"], row["database"]) == key for row in data["tables"]) != count:
            raise ValueError("database coverage mismatch")
    for number, row in enumerate(data["edges"]):
        if row["endpoint_status"] == "both_exist" and (row["source_asset_id"] not in ids or row["target_asset_id"] not in ids):
            raise ValueError("matched dependency has missing endpoints")
        if row["runtime_status"] != "not_verified":
            raise ValueError("static inventory cannot publish runtime success")
        row["evidence_id"] = "e" + str(number)
    for number, row in enumerate(data["gaps"]):
        row["gap_id"] = "g" + str(number)
    coverage_file = inventory.parent / "lineage_coverage.json"
    if coverage_file.exists():
        coverage = json.loads(coverage_file.read_text(encoding="utf-8"))
        data["coverage"] = {"sqlFiles": coverage["file_count"], "parsed": sum(row["status"] == "parsed" for row in coverage["coverage"]),
                            "partialOrFailed": sum(row["status"] == "partial_or_failed" for row in coverage["coverage"]),
                            "unsupported": sum(row["status"] == "no_supported_sql_block" for row in coverage["coverage"])}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    version = hashlib.sha256(raw).hexdigest()
    atomic_write(root / "snapshots" / (version + ".json"), raw)
    atomic_write(root / "current.json", json.dumps({"version": version}).encode())
    return {"version": version, "objectCount": len(ids), "columnCount": len(data["columns"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.inventory_dir.resolve(), args.root.resolve())))


if __name__ == "__main__":
    main()
