"""Offline SQL table-reference discovery. Never connects or exports SQL/config values."""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REFERENCE = re.compile(
    r"\b(FROM|JOIN|INSERT\s+(?:INTO|OVERWRITE)(?:\s+TABLE)?|UPDATE|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?)"
    r"\s+((?:(?:`?[A-Za-z_][\w]*`?|\{\{\s*\w+\s*\}\}|\$\{?\w+\}?)\s*\.\s*)?`?[A-Za-z_][\w]*`?)", re.I,
)
SKIP = {".git", ".venv", "node_modules", "__pycache__", ".worktrees", ".test-artifacts"}


def references(root: Path):
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".py", ".sql", ".sh"} or not path.is_file():
            continue
        if any(part in SKIP for part in path.relative_to(root).parts):
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(content) if path.suffix == ".py" else None
        except (SyntaxError, UnicodeError, OSError):
            yield {"kind": "unparsed", "file": path.relative_to(root).as_posix()}
            continue
        # Strings are evidence candidates only: Python strings include unused SQL,
        # CTEs and templates. Do not infer execution, connection, existence or edges.
        chunks = [(node.value, node.lineno) for node in ast.walk(tree)
                  if isinstance(node, ast.Constant) and isinstance(node.value, str)] if tree else [(content, 1)]
        for sql, line in chunks:
            if not re.search(r"\b(?:SELECT|INSERT|UPDATE|CREATE\s+TABLE)\b", sql, re.I):
                continue
            sql = re.sub(r"/\*.*?\*/|--[^\n]*", lambda m: "\n" * m[0].count("\n"), sql, flags=re.S)
            sql = re.sub(r"'(?:''|[^'])*'", lambda m: "''" + "\n" * m[0].count("\n"), sql)
            for match in REFERENCE.finditer(sql):
                token = re.sub(r"\s|`", "", match[2])
                if token.lower() in {"select", "set", "if", "values"}:
                    continue
                parts = token.split(".")
                table = parts[-1]
                layer = re.match(r"^(ods|dwd|dws|ads|dim)_", table, re.I)
                yield {
                    "kind": "reference", "file": path.relative_to(root).as_posix(),
                    "line": line if tree else line + sql[:match.start()].count("\n"),
                    "location_kind": "python_string_start" if tree else "statement_line",
                    "database_candidate": parts[0] if len(parts) == 2 else "",
                    "table_candidate": table, "operation": match[1].upper(),
                    "layer_candidate": layer[1].upper() if layer else "UNKNOWN",
                    "instance": "UNRESOLVED", "status": "static_candidate",
                }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    rows, failures = [], []
    for item in references(root):
        (failures if item["kind"] == "unparsed" else rows).append(item)
    # Deduplicate only within identical source locations, never across instances.
    rows = list({json.dumps(row, sort_keys=True): row for row in rows}.values())
    args.output.mkdir(parents=True, exist_ok=True)
    fields = ["file", "line", "location_kind", "instance", "database_candidate", "table_candidate", "operation", "layer_candidate", "status"]
    with (args.output / "table_reference_candidates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Python static strings, SQL and shell text; dynamic identifiers and deployed jobs not inventoried",
        "reference_count": len(rows), "referencing_file_count": len({row["file"] for row in rows}),
        "layer_candidate_counts": dict(Counter(row["layer_candidate"] for row in rows)),
        "unparsed_files": failures, "confirmed_physical_tables": None, "confirmed_lineage_edges": None,
        "limitations": "CTEs, unused code and templates may appear; no instance resolution or live schema verification",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
