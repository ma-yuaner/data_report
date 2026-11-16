"""Build reviewable asset tables and evidence-level lineage from collected metadata."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    tables, columns, keys, indexes, views, databases, gaps = [], [], [], [], [], [], []
    snapshots = []
    for name in ["MYSQL", "ERP_MYSQL", "HIVE"]:
        snapshot = json.loads((root / "env_metadata" / (name + ".json")).read_text(encoding="utf-8"))
        if snapshot["status"] != "collected":
            raise ValueError("metadata collection incomplete: " + name)
        snapshots.append(snapshot)
        for database in snapshot["metadata"]["databases"]:
            db = database["database"]
            section = database.get("sections", {})
            listed = section.get("tables", database.get("tables", []))
            databases.append({"source": name, "instance_id": snapshot["instance_id"], "database": db,
                              "object_count": len(listed), "status": database["status"], "collected_at": snapshot["generated_at"]})
            for table in listed:
                hive = name == "HIVE"
                table_name = table["table"] if hive else table["TABLE_NAME"]
                asset_id = name + "/" + snapshot["instance_id"] + "/" + db + "/" + table_name
                if hive:
                    cols = [{**col, "is_partition": 0} for col in table["columns"]] + [{**col, "is_partition": 1} for col in table["partition_columns"]]
                    comment = table["properties"].get("comment", "")
                    kind = table["properties"].get("Table Type", "UNKNOWN")
                else:
                    cols = [{"name": col["COLUMN_NAME"], "type": col["COLUMN_TYPE"], "comment": col["COLUMN_COMMENT"],
                             "nullable": col["IS_NULLABLE"], "key": col["COLUMN_KEY"], "is_partition": 0}
                            for col in section["columns"] if col["TABLE_NAME"] == table_name]
                    comment, kind = table["TABLE_COMMENT"], table["TABLE_TYPE"]
                prefix = re.match(r"^(ods|dwd|dws|ads|dim)_", table_name, re.I)
                layer = prefix[1].upper() if hive and prefix else ("UNCLASSIFIED" if hive else "NOT_ASSIGNED")
                no_comment = not comment or comment == "VIEW"
                obj = {"asset_id": asset_id, "source": name, "instance_id": snapshot["instance_id"], "database": db,
                    "table": table_name, "object_type": kind, "table_comment": comment, "column_count": len(cols),
                    "partition_column_count": sum(col["is_partition"] for col in cols), "layer_candidate": layer,
                    "layer_evidence": "name_prefix_only" if prefix and hive else "requires_review",
                    "missing_column_comment_count": sum(not col["comment"] for col in cols),
                    "schema_status": table.get("status", "complete"), "collected_at": snapshot["generated_at"],
                    "business_grain": "待确认", "owner": "待确认", "runtime_lineage_status": "not_collected"}
                tables.append(obj)
                if no_comment:
                    gaps.append({"asset_id": asset_id, "gap": "missing_business_table_comment", "detail": "表用途待补"})
                if obj["missing_column_comment_count"]:
                    gaps.append({"asset_id": asset_id, "gap": "missing_column_comments", "detail": obj["missing_column_comment_count"]})
                if hive and layer == "UNCLASSIFIED":
                    gaps.append({"asset_id": asset_id, "gap": "layer_unclassified", "detail": "不根据名称猜层级"})
                for position, col in enumerate(cols, 1):
                    columns.append({"asset_id": asset_id, "ordinal": position, **col})
                if not hive:
                    table_keys = [row for row in section["keys"] if row["TABLE_NAME"] == table_name]
                    keys.extend({"asset_id": asset_id, **row} for row in table_keys)
                    indexes.extend({"asset_id": asset_id, **row} for row in section["indexes"] if row["TABLE_NAME"] == table_name)
                    if kind == "BASE TABLE" and not any(row["CONSTRAINT_NAME"] == "PRIMARY" for row in table_keys):
                        gaps.append({"asset_id": asset_id, "gap": "no_declared_primary_key", "detail": "不代表没有业务唯一键"})
            views.extend({"source": name, **view} for view in section.get("views", []))
    lookup = {(row["source"], row["database"], row["table"]): row["asset_id"] for row in tables}
    edges = []
    for row in csv.DictReader((root / "static_lineage.csv").open(encoding="utf-8-sig")):
        source = lookup.get(("HIVE", row["source_database_candidate"], row["source_table"]), "")
        target = lookup.get(("HIVE", row["target_database_candidate"], row["target_table"]), "")
        edges.append({"source_asset_id": source, "target_asset_id": target,
                      "source_reference": row["source_database_candidate"] + "." + row["source_table"],
                      "target_reference": row["target_database_candidate"] + "." + row["target_table"],
                      "edge_type": "etl_static", "evidence": row["file"] + "#statement=" + row["statement"],
                      "sha256": row["sha256"], "endpoint_status": "both_exist" if source and target else "unresolved_or_missing",
                      "runtime_status": "not_verified"})
    for view in views:
        if view["status"] != "definition_parsed":
            gaps.append({"asset_id": view["source"] + "/" + view["database"] + "/" + view["table"], "gap": "view_definition_unresolved", "detail": view["status"]})
        for dep in view.get("dependencies", []):
            source = lookup.get((view["source"], dep["database"], dep["table"]), "")
            target = lookup.get((view["source"], view["database"], view["table"]), "")
            edges.append({"source_asset_id": source, "target_asset_id": target,
                "source_reference": dep["database"] + "." + dep["table"], "target_reference": view["database"] + "." + view["table"],
                "edge_type": "live_view_definition", "evidence": "information_schema.VIEWS", "sha256": view["definition_sha256"],
                "endpoint_status": "both_exist" if source and target else "unresolved_or_missing", "runtime_status": "not_verified"})
    datax_file = root / "datax_lineage.csv"
    if datax_file.exists():
        for row in csv.DictReader(datax_file.open(encoding="utf-8-sig")):
            source_parts, target_parts = row["source_asset_id"].split("/"), row["target_asset_candidate"].split("/")
            source = lookup.get(tuple(source_parts), "") if len(source_parts) == 3 else ""
            target = lookup.get(tuple(target_parts), "") if len(target_parts) == 3 else ""
            edges.append({"source_asset_id": source, "target_asset_id": target,
                "source_reference": row["source_reference"], "target_reference": row["target_database"] + "." + row["target_table"],
                "edge_type": "datax_config", "evidence": "src/dml/datax/" + row["file"], "sha256": row["sha256"],
                "endpoint_status": "both_exist" if source and target else "unresolved_or_missing", "runtime_status": "not_verified"})
    foreign_keys = []
    for key in keys:
        if key.get("REFERENCED_TABLE_NAME"):
            source_key = key["asset_id"].split("/")[0]
            target = lookup.get((source_key, key["REFERENCED_TABLE_SCHEMA"], key["REFERENCED_TABLE_NAME"]), "")
            foreign_keys.append({"asset_id": key["asset_id"], "column": key["COLUMN_NAME"], "constraint": key["CONSTRAINT_NAME"],
                "referenced_asset_id": target, "referenced_column": key["REFERENCED_COLUMN_NAME"], "relationship_type": "declared_foreign_key_not_etl"})
    for edge in edges:
        if edge["endpoint_status"] != "both_exist":
            gaps.append({"asset_id": edge["target_asset_id"] or edge["target_reference"], "gap": "lineage_endpoint_unresolved", "detail": edge["evidence"]})
    output = root / "inventory"
    output.mkdir(exist_ok=True)
    for name, rows, fields in [
        ("databases", databases, list(databases[0])), ("tables", tables, list(tables[0])),
        ("columns", columns, ["asset_id", "ordinal", "name", "type", "comment", "nullable", "key", "is_partition"]),
        ("keys", keys, list(keys[0]) if keys else ["asset_id"]),
        ("indexes", indexes, list(indexes[0]) if indexes else ["asset_id"]),
        ("lineage", edges, list(edges[0]) if edges else ["source_asset_id", "target_asset_id"]),
        ("gaps", gaps, ["asset_id", "gap", "detail"]),
        ("foreign_keys", foreign_keys, list(foreign_keys[0]) if foreign_keys else ["asset_id", "referenced_asset_id"]),
    ]:
        write_csv(output / (name + ".csv"), rows, fields)
    coverage = json.loads((root / "lineage_coverage.json").read_text(encoding="utf-8"))
    summary = {"database_count": len(databases), "object_count": len(tables), "column_count_including_partitions": len(columns),
        "database_objects": {row["source"] + "/" + row["database"]: row["object_count"] for row in databases},
        "hive_layer_candidates": dict(Counter(row["layer_candidate"] for row in tables if row["source"] == "HIVE")),
        "mysql_object_types": dict(Counter(row["object_type"] for row in tables if row["source"] != "HIVE")),
        "view_definition_status": dict(Counter(row["status"] for row in views)),
        "lineage_evidence_by_type": dict(Counter(row["edge_type"] for row in edges)),
        "lineage_endpoint_status": dict(Counter(row["endpoint_status"] for row in edges)),
        "gap_counts": dict(Counter(row["gap"] for row in gaps)),
        "declared_foreign_key_column_count": len(foreign_keys),
        "sql_file_coverage": dict(Counter(row["status"] for row in coverage["coverage"])),
        "limitations": ["current account visible scope only", "layer prefix is candidate", "source definitions are not runtime lineage", "owners, grain, refresh SLA and deployed schedules not verified", "no business row scans or writes"]}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
