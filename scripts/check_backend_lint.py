"""Fail new Ruff errors while keeping an exact, reviewed legacy finding list."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(item: dict) -> tuple[str, str, str, str]:
    return item["path"], item["code"], item["message"], item["source"]


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "backend", "scripts", "--output-format=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode not in (0, 1):
        print(result.stderr)
        return result.returncode
    baseline = Counter(
        fingerprint(item)
        for item in json.loads((ROOT / "scripts/backend-lint-baseline.json").read_text(encoding="utf-8"))
    )
    current: Counter = Counter()
    for item in json.loads(result.stdout):
        path = Path(item["filename"])
        source = path.read_text(encoding="utf-8-sig").splitlines()[item["location"]["row"] - 1].strip()
        key = (path.relative_to(ROOT).as_posix(), item["code"], item["message"], source)
        current[key] += 1
    unexpected = current - baseline
    stale = baseline - current
    for key in unexpected:
        print(f"NEW: {key[0]} {key[1]} {key[2]}\n  {key[3]}")
    for key in stale:
        print(f"REMOVE RESOLVED BASELINE: {key[0]} {key[2]}")
    print(f"Backend lint: {sum(current.values())} known findings; {sum(unexpected.values())} new")
    return int(bool(unexpected or stale))


if __name__ == "__main__":
    raise SystemExit(main())
