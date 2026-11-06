#!/usr/bin/env bash
# Deprecated: analysis now runs as a standalone Python ETL on 216.
set -euo pipefail
cat >&2 <<'MESSAGE'
此247容器入口已停用。请在216的DolphinScheduler配置独立Shell：
export TZ=Asia/Shanghai
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_analytics_etl.py
先执行新增两表DDL及 --check-schema，正常任务每15分钟；不与旧247任务并行。
MESSAGE
exit 2
