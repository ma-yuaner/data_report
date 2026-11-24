#!/usr/bin/env bash
# Source update for T43. Default: checks only. --update fetches main/builds/deploys.
set -euo pipefail
umask 077
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
mode=${1:---check}
[[ $# -le 1 && ( $mode == --check || $mode == --update || $mode == --rollback ) ]] ||
  die 'Usage: bash update-t43.sh [--check|--update|--rollback]'
[[ $(hostname) == ali-pro-data-monitor && $EUID -eq 0 ]] || die 'Run as root on T43 only'
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
app=/data/data_report
store=/data/data_report-updates
repo_url=${T43_REPO_URL:-https://git.ndccloud.com/analytics/data_report.git}
checker=sha256:50f644a6a0338ec01b82d9d7586807a180c2183f0fd1820a96e3eda181dd0ec3
for command in docker git curl flock mountpoint tar; do command -v "$command" >/dev/null || die "Missing tool: $command"; done
for file in update-t43-helper.py reviewed-backend.json build-args.t43.yml; do
  [[ -f $bundle/$file && ! -L $bundle/$file ]] || die "Missing or symlinked helper: $file"
done
[[ -f $app/.env && $(stat -c '%a:%u' "$app/.env") == 600:0 ]] || die '.env must be root-owned, mode 600'
mountpoint -q /data || die '/data is not mounted'
[[ $(docker info --format '{{.DockerRootDir}}') == /data/docker ]] || die 'Unexpected Docker data root'
docker image inspect "$checker" >/dev/null

# One execution at a time. A host lock is not an application/data modification.
exec 9>/run/lock/data-report-t43-update.lock
flock -n 9 || die 'Another T43 update is running'

helper() {
  docker run --rm -i --network none --read-only --user 0:0 --entrypoint python \
    -v "$bundle:/bundle:ro" "$checker" /bundle/update-t43-helper.py "$@"
}
dc() {
  env -i PATH="$PATH" HOME="$HOME" COMPOSE_PROFILES= \
    docker compose --project-directory "$app" --env-file "$app/.env" -p data_report "$@"
}
base=(-f "$app/docker-compose.yml" -f "$app/docker-compose.hr-mail.yml" -f "$app/docker-compose.t43.yml")
check_workers() {
  local names name
  names=$(docker ps --filter label=com.docker.compose.project=data_report --format '{{.Names}}')
  while IFS= read -r name; do
    [[ -z $name || $name == data_report-api-1 || $name == data_report-web-1 ]] ||
      die "Unexpected running container: $name; not stopped automatically"
  done <<< "$names"
}
check_workers
for suffix in asset_inventory_data risk_upload_data comprehensive_export_data adm_data \
  data_workbench_data hr_mail_data risk_verification_data; do
  docker volume inspect "data_report_$suffix" >/dev/null || die "Missing volume: $suffix"
done
dc "${base[@]}" -f "$bundle/build-args.t43.yml" config --format json | helper validate-source

if [[ $mode == --check ]]; then
  echo 'CHECK PASSED: required tools/config/images/volumes available; no Git fetch/build/deploy performed.'
  exit 0
fi

health() {
  curl --noproxy '*' --fail --silent --show-error --max-time 10 -o /dev/null http://127.0.0.1:1818/ &&
  curl --noproxy '*' --fail --silent --show-error --max-time 10 http://127.0.0.1:1818/api/health |
    helper validate-health
}
apply_runtime() {
  local runtime=$1
  helper validate-runtime < "$runtime" || return 1
  dc -f "$runtime" up -d --no-deps --no-build --pull never --wait --wait-timeout 180 api web || return 1
  health || return 1
  check_workers
}

install -d -m 700 "$store" "$store/releases"
if [[ $mode == --rollback ]]; then
  [[ -f $store/rollback.json ]] || die 'No previous release configuration saved'
  apply_runtime "$store/rollback.json" || die 'Rollback failed; inspect containers, no data rollback attempted'
  cp -- "$store/rollback.json" "$store/active.json.tmp"
  mv -- "$store/active.json.tmp" "$store/active.json"
  echo 'ROLLBACK PASSED: application images/config restored; database and volumes untouched.'
  exit 0
fi

# Keep the server .env and original working tree unchanged; fetch into a dedicated cache.
if [[ ! -d $store/repository.git ]]; then git init --bare "$store/repository.git"; fi
if git --git-dir="$store/repository.git" remote get-url origin >/dev/null 2>&1; then
  [[ $(git --git-dir="$store/repository.git" remote get-url origin) == "$repo_url" ]] || die 'Repository URL mismatch'
else
  git --git-dir="$store/repository.git" remote add origin "$repo_url"
fi
git --git-dir="$store/repository.git" fetch --no-tags --depth=1 origin refs/heads/main
commit=$(git --git-dir="$store/repository.git" rev-parse 'FETCH_HEAD^{commit}')
run=$(date -u +%Y%m%dT%H%M%SZ)-${commit:0:12}-$$
release=$store/releases/$run
mkdir -m 700 "$release" "$release/source"
printf '%s\n' "$commit" > "$release/commit.txt"
git -c core.autocrlf=false -c core.eol=lf --git-dir="$store/repository.git" archive "$commit" | tar -x -C "$release/source"
[[ ! -e $release/source/.env && ! -L $release/source/.env ]] || die 'Tracked .env is forbidden'

# Check without importing the candidate application. Backend changes need a new reviewed baseline.
docker run --rm --network none --read-only --user 0:0 --entrypoint python \
  -v "$bundle:/bundle:ro" -v "$release/source:/candidate:ro" \
  "$checker" /bundle/update-t43-helper.py verify-backend

candidate=(-f "$release/source/docker-compose.yml" -f "$release/source/docker-compose.hr-mail.yml"
  -f "$app/docker-compose.t43.yml" -f "$release/source/scripts/deploy/t43/build-args.t43.yml")
dc "${candidate[@]}" config --format json > "$release/candidate.json"
helper validate-source < "$release/candidate.json"
pilot=$(helper pilot-volume < "$release/candidate.json")
if [[ $pilot == enabled ]]; then
  docker volume inspect data_report_airline_rebate_pilot_data >/dev/null ||
    die 'Pilot enabled but dedicated volume missing: data_report_airline_rebate_pilot_data'
fi
mirror=$(helper build-mirror < "$release/candidate.json")
pip_text=$(helper build-pip-settings < "$release/candidate.json")
mapfile -t pip_settings <<< "$pip_text"
[[ ${#pip_settings[@]} -eq 3 ]] || die 'Invalid pip build settings'
pip_index=${pip_settings[0]}
pip_timeout=${pip_settings[1]}
pip_retries=${pip_settings[2]}
printf 'API build pip index: %s (timeout=%s, retries=%s)\n' "$pip_index" "$pip_timeout" "$pip_retries"

# Sequential builds keep peak resource usage lower. No current container is stopped here.
api_tag=data-report-t43/api:$run
web_tag=data-report-t43/web:$run
docker build --build-arg "DOCKERHUB_MIRROR=$mirror" \
  --build-arg "PIP_INDEX_URL=$pip_index" --build-arg "PIP_TIMEOUT=$pip_timeout" \
  --build-arg "PIP_RETRIES=$pip_retries" -t "$api_tag" "$release/source/backend"
docker build --build-arg "DOCKERHUB_MIRROR=$mirror" -t "$web_tag" "$release/source/frontend"
api_id=$(docker image inspect "$api_tag" --format '{{.Id}}')
web_id=$(docker image inspect "$web_tag" --format '{{.Id}}')
helper render "$api_id" "$web_id" < "$release/candidate.json" > "$release/runtime.json"
helper validate-runtime < "$release/runtime.json"
if [[ $pilot == enabled ]]; then
  docker run --rm --network none --entrypoint sh \
    --mount type=volume,source=data_report_airline_rebate_pilot_data,target=/app/var/airline-rebates \
    "$api_id" -ec 'test -w /app/var/airline-rebates' ||
    die 'Pilot volume is not writable by the API service user'
fi

# Snapshot live images, not mutable tags. Save configuration privately, never dump credentials.
old_api=$(docker inspect data_report-api-1 --format '{{.Image}}')
old_web=$(docker inspect data_report-web-1 --format '{{.Image}}')
if [[ -f $store/active.json ]]; then
  helper render "$old_api" "$old_web" < "$store/active.json" > "$release/previous-template.json"
else
  dc "${base[@]}" config --format json | helper render "$old_api" "$old_web" > "$release/previous-template.json"
fi
# The first migration may have no saved active descriptor. Capture actual live env,
# rather than assuming an edited .env still equals the environment of running containers.
docker inspect data_report-api-1 data_report-web-1 |
  docker run --rm -i --network none --read-only --user 0:0 --entrypoint python \
    -v "$bundle:/bundle:ro" -v "$release:/release:ro" "$checker" \
    /bundle/update-t43-helper.py capture-live /release/previous-template.json > "$release/previous.json"
helper validate-runtime < "$release/previous.json"
cp -- "$release/previous.json" "$store/rollback.json"
check_workers
if apply_runtime "$release/runtime.json"; then
  cp -- "$release/runtime.json" "$store/active.json.tmp"
  mv -- "$store/active.json.tmp" "$store/active.json"
  echo "UPDATE PASSED: main commit $commit; API/web only."
else
  echo 'Update failed; attempting previous API/web release once.' >&2
  if apply_runtime "$release/previous.json"; then
    cp -- "$release/previous.json" "$store/active.json.tmp"
    mv -- "$store/active.json.tmp" "$store/active.json"
    echo 'Previous application release restored; update remains FAILED.' >&2
  else
    echo 'ROLLBACK FAILED. Stop and inspect; no database/volume rollback or cleanup performed.' >&2
  fi
  exit 1
fi
