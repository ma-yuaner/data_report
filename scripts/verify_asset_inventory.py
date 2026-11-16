"""Verify inventory input or published snapshot without opening business data sources."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path


def read_csv(directory, name):
    with (directory / (name + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify(expected, *, input_dir=None, root=None, backend_dir=None):
    if input_dir:
        tables, columns, edges = [read_csv(input_dir, name) for name in ("tables", "columns", "lineage")]
        actual = {"objectCount": len(tables), "fieldCount": len(columns), "edgeEvidenceCount": len(edges),
                  "matchedEvidenceCount": sum(row["endpoint_status"] == "both_exist" for row in edges),
                  "databaseObjects": dict(Counter(row["source"] + "/" + row["database"] for row in tables))}
        version = None
    else:
        sys.path.insert(0, str(backend_dir))
        from data_report_api.services.asset_inventory import AssetInventory
        summary = AssetInventory({"ASSET_INVENTORY_ROOT": str(root)}).summary()
        actual = {key: summary[key] for key in ("objectCount", "fieldCount", "edgeEvidenceCount", "matchedEvidenceCount")}
        actual["databaseObjects"] = {row["source"] + "/" + row["database"]: int(row["object_count"]) for row in summary["databases"]}
        version = summary["version"]
    for key, value in expected.items():
        if key not in actual or actual[key] != value:
            raise ValueError("Inventory verification mismatch: " + key)
    return {"status": "passed", "mode": "input" if input_dir else "published_snapshot", "version": version, **actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-json", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--root", type=Path, default=Path(os.getenv("ASSET_INVENTORY_ROOT") or "/app/var/assets"))
    local_backend = Path(__file__).resolve().parents[1] / "backend"
    parser.add_argument("--backend-dir", type=Path, default=local_backend if local_backend.is_dir() else Path("/app"))
    args = parser.parse_args()
    expected = json.loads(args.expected_json.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or set(expected) != {"objectCount", "fieldCount", "edgeEvidenceCount", "matchedEvidenceCount", "databaseObjects"}:
        raise ValueError("Expected manifest has invalid fields")
    print(json.dumps(verify(expected, input_dir=args.input_dir, root=args.root, backend_dir=args.backend_dir), ensure_ascii=True))


if __name__ == "__main__":
    main()
