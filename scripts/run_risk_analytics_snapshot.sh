#!/usr/bin/env bash
# 仅分析sibebid已发布事实；不读取ERP、不执行DDL、不启动API内逐单任务。
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${1:-}" == "--print-cron" ]]; then
  if [[ "$repo_dir" == *'%'* || "$repo_dir" == *$'\n'* ]]; then echo 'Unsupported deployment path for cron' >&2; exit 2; fi
  bash_bin="$(type -P bash)"
  printf -v cron_command 'cd -- %q && mkdir -p var/log && exec %q scripts/run_risk_analytics_snapshot.sh >> var/log/risk-analytics-snapshot.log 2>&1' "$repo_dir" "$bash_bin"
  printf '*/15 * * * * %q -c %q\n' "$bash_bin" "$cron_command"
  echo '# 用现有可运行docker compose的部署账号，把上面一行加入 crontab -e。'
  exit 0
fi
cd -- "$repo_dir"
mkdir -p var/log
# 数据库命名锁防止多机/重复启动。普通执行先门禁，不自动建表。
exec docker compose run -T --rm --no-deps --entrypoint python api \
  -m data_report_api.services.risk_analytics_snapshot "$@"
