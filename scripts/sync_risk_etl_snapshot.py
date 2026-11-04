"""Export the reviewed standalone ETL as a pinned API runtime dependency (offline)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = "etl_scripts/automation/risk_verification_order_day_etl.py"
TARGET = ROOT / "backend/data_report_api/services/risk_order_sync_generated.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, default=ROOT.parent / "data-team-repo")
    args = parser.parse_args()
    repo = args.source_repo.resolve()
    git = ["git", "-c", "safe.directory=" + str(repo).replace("\\", "/"), "-C", str(repo)]
    if subprocess.check_output(git + ["status", "--porcelain", "--", RELATIVE]):
        raise SystemExit("Canonical ETL has uncommitted changes; commit and verify it before exporting")
    commit = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    source = subprocess.check_output(git + ["show", commit + ":" + RELATIVE]).decode("utf-8").replace("\r\n", "\n")
    digest = hashlib.sha256(source.encode()).hexdigest()
    header = "# Generated offline from data-team-repo@" + commit + ":" + RELATIVE + "\n# Canonical SHA256: " + digest + "; do not edit this runtime copy.\n"
    TARGET.write_text(header + source, encoding="utf-8")
    TARGET.with_suffix(".meta.json").write_text(json.dumps({"repository": "data-team-repo", "commit": commit, "path": RELATIVE, "sha256": digest}, indent=2), encoding="utf-8")
    print("Pinned canonical risk ETL runtime snapshot exported; no database/network access")


if __name__ == "__main__":
    main()
