"""Match DataX configuration endpoints against collected schemas without exporting secrets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--inventory-root", type=Path, required=True)
    p.add_argument("--site-packages", type=Path, required=True)
    args = p.parse_args()
    sys.path.append(str(args.site_packages.resolve()))
    sys.path.append(str((args.inventory_root / "deps").resolve()))
    from dotenv import dotenv_values
    env = dotenv_values(args.env_file)
    endpoints = {(env.get(source + "_HOST", "").lower(), int(env.get(source + "_PORT") or 3306)): source
                 for source in ["MYSQL", "ERP_MYSQL"]}
    snapshot = json.loads((args.inventory_root / "env_metadata/HIVE.json").read_text(encoding="utf-8"))
    locations = {}
    for db in snapshot["metadata"]["databases"]:
        for table in db["tables"]:
            properties = table["properties"]
            if "location_path_sha256" in properties:
                key = (properties["storage_root_sha256"], properties["location_path_sha256"])
                locations[key] = (db["database"], table["table"])
    rows, coverage = [], []
    for path in sorted(args.root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            count = 0
            for content in data["job"]["content"]:
                reader, writer = content["reader"], content["writer"]
                if reader["name"] == "mysqlreader" and writer["name"] in {"mysqlwriter", "hdfswriter"}:
                    from asset_metadata_collect import view_dependencies
                    for rc in reader["parameter"]["connection"]:
                        reader_url = rc["jdbcUrl"]
                        reader_url = reader_url[0] if isinstance(reader_url, list) else reader_url
                        reader_uri = urlsplit(reader_url.removeprefix("jdbc:"))
                        reader_db = reader_uri.path.strip("/")
                        reader_key = endpoints.get(((reader_uri.hostname or "").lower(), reader_uri.port or 3306), "UNRESOLVED_CONNECTION")
                        source_tables = {(reader_db, table) for table in rc.get("table", [])}
                        for sql in rc.get("querySql", []):
                            parsed = view_dependencies({"TABLE_SCHEMA": reader_db, "TABLE_NAME": "datax_query", "VIEW_DEFINITION": sql})
                            source_tables.update((dep["database"], dep["table"]) for dep in parsed.get("dependencies", []))
                        targets = []
                        if writer["name"] == "mysqlwriter":
                            for wc in writer["parameter"]["connection"]:
                                writer_url = wc["jdbcUrl"]
                                writer_url = writer_url[0] if isinstance(writer_url, list) else writer_url
                                writer_uri = urlsplit(writer_url.removeprefix("jdbc:"))
                                writer_key = endpoints.get(((writer_uri.hostname or "").lower(), writer_uri.port or 3306), "UNRESOLVED_CONNECTION")
                                targets.extend((writer_key, writer_uri.path.strip("/"), table) for table in wc["table"])
                        else:
                            wp = writer["parameter"]
                            fs = urlsplit(wp["defaultFS"])
                            value = PurePosixPath(urlsplit(wp["path"]).path.rstrip("/"))
                            matches = [locations[(digest(fs.scheme + "://" + fs.netloc), digest(str(parent)))]
                                for parent in [value, *value.parents] if (digest(fs.scheme + "://" + fs.netloc), digest(str(parent))) in locations]
                            targets = [("HIVE", *matches[0])] if matches else [("UNRESOLVED_CONNECTION", "", "UNRESOLVED_HDFS_LOCATION")]
                        for source_db, source_table in sorted(source_tables):
                            for target_key, target_db, target_table in targets:
                                rows.append({"file": path.name, "sha256": digest(path.read_text(encoding="utf-8-sig")),
                                    "source_asset_id": reader_key + "/" + source_db + "/" + source_table if reader_key != "UNRESOLVED_CONNECTION" else "",
                                    "source_reference": source_db + "." + source_table,
                                    "target_connection": target_key, "target_database": target_db, "target_table": target_table,
                                    "target_asset_candidate": target_key + "/" + target_db + "/" + target_table if target_key != "UNRESOLVED_CONNECTION" else "",
                                    "evidence": "DataX reader/writer configuration", "runtime_status": "not_verified"})
                                count += 1
                    continue
                if reader["name"] != "hdfsreader" or writer["name"] != "mysqlwriter":
                    continue
                rp, wp = reader["parameter"], writer["parameter"]
                fs = urlsplit(rp["defaultFS"])
                storage_root = digest(fs.scheme + "://" + fs.netloc)
                paths = rp["path"] if isinstance(rp["path"], list) else [rp["path"]]
                sources = set()
                for reader_path in paths:
                    path_url = urlsplit(reader_path)
                    root_hash = digest(path_url.scheme + "://" + path_url.netloc) if path_url.netloc else storage_root
                    value = PurePosixPath(path_url.path.rstrip("/"))
                    for parent in [value, *value.parents]:
                        match = locations.get((root_hash, digest(str(parent))))
                        if match:
                            sources.add(match)
                            break
                for connection in wp["connection"]:
                    jdbc = connection["jdbcUrl"]
                    jdbc = jdbc[0] if isinstance(jdbc, list) else jdbc
                    uri = urlsplit(jdbc.removeprefix("jdbc:"))
                    source_key = endpoints.get(((uri.hostname or "").lower(), uri.port or 3306), "UNRESOLVED_CONNECTION")
                    target_db = uri.path.strip("/")
                    for target in connection["table"]:
                        for source_db, source_table in sorted(sources or {("", "UNRESOLVED_HDFS_LOCATION")}):
                            rows.append({"file": path.name, "sha256": digest(path.read_text(encoding="utf-8-sig")),
                                "source_asset_id": "HIVE/" + source_db + "/" + source_table if source_db else "",
                                "source_reference": source_db + "." + source_table,
                                "target_connection": source_key, "target_database": target_db, "target_table": target,
                                "target_asset_candidate": source_key + "/" + target_db + "/" + target if source_key != "UNRESOLVED_CONNECTION" else "",
                                "evidence": "DataX reader storage hashes / writer JDBC endpoint", "runtime_status": "not_verified"})
                            count += 1
            coverage.append({"file": path.name, "edge_count": count, "status": "parsed" if count else "unsupported_plugin_or_no_mapping"})
        except Exception as error:
            coverage.append({"file": path.name, "status": "failed", "error_type": type(error).__name__})
    with (args.inventory_root / "datax_lineage.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = list(rows[0]) if rows else ["file", "source_asset_id", "target_asset_candidate"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"files": coverage, "edge_count": len(rows), "hdfs_source_matches": sum(row["source_asset_id"].startswith("HIVE/") for row in rows),
               "mysql_connection_matches": sum(row["target_connection"] in {"MYSQL", "ERP_MYSQL"} for row in rows)}
    (args.inventory_root / "datax_coverage.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "files"}))


if __name__ == "__main__":
    main()
