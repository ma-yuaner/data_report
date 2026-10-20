"""Ensure the new architecture gate rejects the regressions it is meant to catch."""
import runpy
from pathlib import Path


CHECKS = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/check_architecture.py"))


def test_cycle_check_reports_a_real_cycle_and_accepts_a_diamond():
    find_cycles = CHECKS["find_cycles"]
    assert find_cycles({"a": {"b"}, "b": {"a"}}) == ["a -> b -> a"]
    assert find_cycles({"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}) == []


def test_local_import_check_resolves_relative_private_imports(tmp_path):
    path = tmp_path / "consumer.py"
    path.write_text("from ..shared.periods import _private\n", encoding="utf-8")
    edges, errors = CHECKS["dependencies"](
        "data_report_api.services.consumer", path, {"data_report_api.shared.periods"}
    )
    assert edges == {"data_report_api.shared.periods"}
    assert errors == ["data_report_api.services.consumer:1: cross-module private import _private"]
