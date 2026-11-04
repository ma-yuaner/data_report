#!/usr/bin/env bash
# Run only on the existing data_report server checkout. Never touches other projects or removes volumes.
set -euo pipefail
trap 'printf "部署在第%s行失败，已停止。请保留错误信息，不要清库、删卷或盲目重试。\n" "$LINENO" >&2' ERR
repo_root="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
cd "$repo_root"
case "$(git remote get-url origin)" in
  */analytics/data_report.git|*/analytics/data_report) ;;
  *) echo "Unexpected origin; stop and verify this is the data_report checkout." >&2; exit 1 ;;
esac
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked files have local changes. Preserve and review them before deployment; nothing was overwritten." >&2
  exit 1
fi
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Untracked files will be preserved. Git will stop if an update would overwrite them."
fi
if [ "$(git branch --show-current)" != "main" ]; then
  echo "Expected main branch; stop and verify the release branch." >&2
  exit 1
fi
command -v docker >/dev/null
command -v curl >/dev/null
echo "[1/5] 检查Docker Compose与发布配置（不输出密钥）"
docker compose version >/dev/null
docker compose config --quiet
echo "Current commit: $(git rev-parse HEAD)"
echo "[2/5] 更新main分支"
git pull --ff-only origin main
docker compose config --quiet
echo "[3/5] 备份已有风控核查记录"
docker compose run --rm --no-deps --user 0:0 --entrypoint python api - <<'PY'
import os
from pathlib import Path
root = Path('/app/var/risk-verification')
if root.is_symlink() or str(root.resolve()) != '/app/var/risk-verification':
    raise SystemExit('Unexpected risk storage path; stopped without changing permissions.')
root.mkdir(parents=True, exist_ok=True)
os.chown(root, 1000, 1000)
root.chmod(0o700)
for name in ('workflow.sqlite3', 'workflow.sqlite3-wal', 'workflow.sqlite3-shm', 'workflow.sqlite3-journal'):
    target = root / name
    if target.is_symlink():
        raise SystemExit('Unexpected symbolic link in risk storage; stopped.')
    if target.exists():
        if not target.is_file():
            raise SystemExit('Unexpected non-file in risk storage; stopped.')
        os.chown(target, 1000, 1000)
        target.chmod(0o600)
print('Risk storage ownership checked for application UID 1000; no database contents changed.')
PY
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
echo "[4/5] 构建并更新api、web（保留所有数据卷）"
docker compose up -d --build api web
docker compose ps api web
echo "[5/5] 检查服务健康与配置就绪状态"
curl --connect-timeout 3 --max-time 10 --retry 5 --retry-delay 3 --retry-connrefused -fsS http://127.0.0.1:5160/api/health
echo
curl --connect-timeout 3 --max-time 10 --retry 5 --retry-delay 3 --retry-connrefused -fsS -o /dev/null http://127.0.0.1:1818/risk-verification
docker compose exec -T api python - <<'PY'
import os
erp = all(bool(os.getenv('ERP_MYSQL_' + key, '').strip()) for key in ('HOST', 'DATABASE', 'USER', 'PASSWORD'))
enabled = os.getenv('RISK_AI_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
model = bool(os.getenv('RISK_AI_MODEL', '').strip() and os.getenv('RISK_AI_KEY', '').strip())
print('ERP显式配置：' + ('已填写，实际读取仍待验收' if erp else '未填写完整，请在本项目.env补齐ERP_MYSQL配置后重新执行脚本'))
print('风控AI：' + ('已启用并已填写，真实调用仍待验收' if enabled and model else '未启用或未填写完整；可以先验收取证与人工确认'))
print('以上只检查配置是否存在，未查询订单或调用模型；未输出任何配置值。')
PY
echo "Released commit: $(git rev-parse HEAD)"
echo "部署和健康检查完成。管理员访问现有1818端口的 /risk-verification 验收。"
echo "健康成功不等于取证、AI或业务验收通过；配置缺项按上方提示补齐。"
