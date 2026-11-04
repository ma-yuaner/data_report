#!/usr/bin/env bash
# Run only on the existing data_report server checkout. Never touches other projects or removes volumes.
set -euo pipefail
repo_root="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
cd "$repo_root"
case "$(git remote get-url origin)" in
  */analytics/data_report.git|*/analytics/data_report) ;;
  *) echo "Unexpected origin; stop and verify this is the data_report checkout." >&2; exit 1 ;;
esac
if [ -n "$(git status --porcelain)" ]; then
  echo "Checkout has local changes. Preserve and review them before deployment; nothing was overwritten." >&2
  exit 1
fi
if [ "$(git branch --show-current)" != "main" ]; then
  echo "Expected main branch; stop and verify the release branch." >&2
  exit 1
fi
command -v docker >/dev/null
command -v curl >/dev/null
echo "Current commit: $(git rev-parse HEAD)"
git pull --ff-only origin main
docker compose config --quiet
if [ -n "$(docker compose ps -q api)" ]; then
  docker compose exec -T api python - <<'PY'
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
root = Path(os.getenv('RISK_VERIFICATION_ROOT', '/app/var/risk-verification'))
source = root / 'workflow.sqlite3'
if source.exists():
    target = root / 'backups' / ('before-release-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite3')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    reader = sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True)
    writer = sqlite3.connect(str(target))
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()
    target.chmod(0o600)
    print('Consistent risk-workflow backup saved in the existing data volume.')
else:
    print('No existing risk-workflow database; no backup needed for this new module.')
PY
fi
docker compose up -d --build api web
docker compose ps api web
curl --connect-timeout 3 --max-time 10 --retry 5 --retry-delay 3 --retry-connrefused -fsS http://127.0.0.1:5160/api/health
echo
echo "Released commit: $(git rev-parse HEAD)"
echo "Next: sign in as administrator and open /risk-verification on the existing web port."
echo "Health is not business acceptance. If any step failed, stop; never remove volumes or retry model calls blindly."
