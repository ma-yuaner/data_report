#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
required_commit="${1:?Usage: bash scripts/deploy_adm.sh REQUIRED_COMMIT}"

if [[ "$(git branch --show-current)" != main ]] || [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo 'Deploy from a clean main checkout.' >&2
  exit 1
fi

git fetch origin main
git merge-base --is-ancestor "$required_commit" FETCH_HEAD
git merge --ff-only FETCH_HEAD
git merge-base --is-ancestor "$required_commit" HEAD

docker compose build api web admwf-worker
if [[ "${ADM_APPLY_OPERATIONS_SCHEMA:-0}" == 1 ]]; then
  docker compose run --rm --no-deps -T api python -m data_report_api.admwf_schema --apply
else
  docker compose run --rm --no-deps -T api python -m data_report_api.admwf_schema
fi
docker compose up -d --no-deps --wait --wait-timeout 120 api web admwf-worker
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:5160/api/health
printf '\n'
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:1818/api/health
printf '\nDeployed revision: '
git rev-parse --short HEAD
docker compose ps api web admwf-worker
