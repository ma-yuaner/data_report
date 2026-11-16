"""Extract static Hive table dependencies, without running SQL or resolving instances."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import logging
import re
import sys
from pathlib import Path


def normalize(text):
    text = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"unresolved_\1", text)
    return re.sub(r"\$\{?(\w+)\}?", r"unresolved_\1", text)


def extract(text):
    import sqlglot
    from sqlglot import exp
    from sqlglot.optimizer.scope import build_scope
    edges, declarations = [], []
    current_database = ""
    for index, statement in enumerate(sqlglot.parse(normalize(text), read="hive")):
        if statement is None:
            continue
        if isinstance(statement, exp.Use):
            current_database = statement.this.name
            continue
        if not isinstance(statement, (exp.Insert, exp.Create)):
            continue
        target = statement.this
        if isinstance(target, exp.Schema):
            target = target.this
        if not isinstance(target, exp.Table):
            continue
        if isinstance(statement, exp.Create):
            declarations.append({"database_candidate": target.db or current_database, "table": target.name,
                                 "statement": index + 1, "status": "source_definition"})
        query = statement.expression
        if query is None:
            continue
        query = query.copy()
        if statement.args.get("with_"):
            query.set("with_", statement.args["with_"].copy())
        scope = build_scope(query)
        if scope is None:
            continue
        sources = set()
        for part in scope.traverse():
            for _, source in part.selected_sources.values():
                if isinstance(source, exp.Table):
                    sources.add((source.db or current_database, source.name))
        for database, table in sorted(sources):
            edges.append({"source_database_candidate": database, "source_table": table,
                          "target_database_candidate": target.db or current_database, "target_table": target.name,
                          "statement": index + 1, "instance": "UNRESOLVED",
                          "status": "static_dependency_not_execution"})
    return edges, declarations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.site_packages.resolve()))
    logging.disable(logging.CRITICAL)
    edges, declarations, coverage = [], [], []
    for path in sorted(args.root.rglob("*")):
        if path.suffix not in {".sql", ".sh"} or not path.is_file():
            continue
        relative = path.relative_to(args.root).as_posix()
        try:
            content = path.read_text(encoding="utf-8-sig")
            # Parse only explicit Hive -e double-quoted blocks in shell files;
            # other shell construction is unparsed, never interpreted or executed.
            if path.suffix == ".sh":
                assignments = [m[1] for m in re.finditer(r'(?m)^\w+\s*=\s*"((?:\\.|[^"\\])*)"', content, re.S)]
                literals = [m[1] for m in re.finditer(r'-e\s*"((?:\\.|[^"\\])*)"', content, re.S)]
                chunks = list(dict.fromkeys(chunk for chunk in assignments + literals
                    if re.search(r"\b(?:SELECT|INSERT|CREATE\s+TABLE)\b", chunk, re.I)))
            else:
                chunks = [content]
            state = {"file": relative, "sha256": hashlib.sha256(content.encode()).hexdigest(),
                     "chunk_count": len(chunks), "parsed_chunks": 0, "failed_chunks": 0,
                     "status": "no_supported_sql_block" if not chunks else "parsed"}
            for chunk in chunks:
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        found, defined = extract(chunk)
                    for row in found + defined:
                        row.update(file=relative, sha256=state["sha256"])
                    edges.extend(found)
                    declarations.extend(defined)
                    state["parsed_chunks"] += 1
                except Exception as error:
                    state["failed_chunks"] += 1
                    state.update(status="partial_or_failed", error_type=type(error).__name__)
            coverage.append(state)
        except (UnicodeError, OSError) as error:
            coverage.append({"file": relative, "status": "unreadable", "error_type": type(error).__name__})
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in [
        ("static_lineage", edges, ["file", "sha256", "statement", "instance", "source_database_candidate", "source_table", "target_database_candidate", "target_table", "status"]),
        ("declared_tables", declarations, ["file", "sha256", "statement", "database_candidate", "table", "status"]),
    ]:
        with (args.output / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    result = {"static_edge_evidence_count": len(edges), "declaration_evidence_count": len(declarations),
              "file_count": len(coverage), "coverage": coverage,
              "limitations": "Static INSERT/CTAS only; no runtime proof, instance resolution, field lineage or shell execution; dynamic names unresolved; parser success is not deployment proof"}
    (args.output / "lineage_coverage.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "coverage"}))


if __name__ == "__main__":
    main()
