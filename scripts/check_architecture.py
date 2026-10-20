"""Check Python dependency boundaries without importing application code."""

from __future__ import annotations

import ast
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "backend/data_report_api"


def module_name(path: Path, package: Path) -> str:
    parts = path.relative_to(package.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def dependencies(name: str, path: Path, known: set[str]) -> tuple[set[str], list[str]]:
    edges: set[str] = set()
    errors = []
    parent = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.Import):
            edges.update(alias.name for alias in node.names if alias.name in known)
        elif isinstance(node, ast.ImportFrom):
            prefix = parent.split(".")[: len(parent.split(".")) - node.level + 1] if node.level else []
            base = ".".join(prefix + ([node.module] if node.module else []))
            for alias in node.names:
                target = f"{base}.{alias.name}" if f"{base}.{alias.name}" in known else base
                if target not in known:
                    continue
                edges.add(target)
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    errors.append(f"{name}:{node.lineno}: cross-module private import {alias.name}")
    return edges, errors


def find_cycles(graph: dict[str, set[str]]) -> list[str]:
    done: set[str] = set()
    active: list[str] = []
    errors = []

    def visit(name: str) -> None:
        if name in active:
            errors.append(" -> ".join(active[active.index(name) :] + [name]))
            return
        if name in done:
            return
        active.append(name)
        for target in sorted(graph.get(name, set())):
            visit(target)
        active.pop()
        done.add(name)

    for name in sorted(graph):
        visit(name)
    return errors


def check_python() -> list[str]:
    modules = {module_name(path, PACKAGE): path for path in PACKAGE.rglob("*.py")}
    graph = {}
    errors = []
    entrypoints = {
        "data_report_api",
        "data_report_api.routes",
        "data_report_api.auth_routes",
        "data_report_api.target_management_daily",
        "data_report_api.target_management_scheduler",
        "data_report_api.risk_upload_worker",
    }
    for name, path in sorted(modules.items()):
        targets, private_errors = dependencies(name, path, set(modules))
        graph[name] = targets
        errors.extend(private_errors)
        for target in targets:
            restricted = target in entrypoints or target.startswith("data_report_api.api")
            if name.startswith(("data_report_api.services.", "data_report_api.jobs.")) and restricted:
                errors.append(f"{name}: depends on HTTP/entrypoint {target}")
            if name.startswith("data_report_api.shared.") and (
                restricted
                or target.startswith(("data_report_api.services", "data_report_api.jobs"))
                or target == "data_report_api.config"
            ):
                errors.append(f"{name}: shared contract depends on {target}")
            if name.startswith("data_report_api.api.") and target.startswith("data_report_api.api."):
                if target != "data_report_api.api.common":
                    errors.append(f"{name}: HTTP domains depend on each other via {target}")
    errors.extend(f"Python cycle: {cycle}" for cycle in find_cycles(graph))
    print(f"Python architecture: {len(modules)} modules checked")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-only", action="store_true", help="Check Python without Node dependencies")
    args = parser.parse_args()
    errors = check_python()
    if errors:
        print("\n".join(errors))
    if args.python_only:
        return int(bool(errors))
    frontend = subprocess.run(["node", "frontend/scripts/check-architecture.mjs"], cwd=ROOT, check=False)
    return int(bool(errors) or frontend.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())
