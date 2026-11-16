#!/usr/bin/env bash
# Run on 247 from the existing data_report checkout after updating main.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(git -C "$script_dir/.." rev-parse --show-toplevel)"
if [ "$#" -ne 1 ]; then
  printf '%s\n' 'Usage: bash scripts/deploy_asset_inventory.sh /absolute/path/asset-inventory-seed' >&2
  exit 2
fi
seed_dir="$(cd -- "$1" && pwd -P)"
for file in tables columns lineage gaps databases keys indexes; do
  test -s "$seed_dir/inventory/$file.csv"
done
test -s "$seed_dir/expected.json"
cd "$repo_root"
docker compose config --quiet
docker compose build api web
# Initialize only the private asset volume. No ERP/MySQL/Hive calls are made.
docker compose run --rm --no-deps --user 0 api sh -ec 'mkdir -p /app/var/assets; chown -R appuser:appgroup /app/var/assets'
docker compose up -d api web
ready=0
for ((attempt=1; attempt<=60; attempt++)); do
  if docker compose exec -T api python -c 'import json,urllib.request; r=urllib.request.urlopen("http://127.0.0.1:5160/api/health",timeout=3); assert r.status==200 and json.load(r)["success"]' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  printf '%s\n' 'API health check failed. Inventory was not imported. Inspect docker compose logs --tail=100 api.' >&2
  exit 1
fi
import_dir="/tmp/asset-inventory-$(date +%s)-$$"
docker compose exec -T api mkdir -p "$import_dir"
docker compose cp "$seed_dir/." "api:$import_dir/"
docker compose cp "$script_dir/publish_asset_inventory.py" "api:$import_dir/publish_asset_inventory.py"
docker compose cp "$script_dir/verify_asset_inventory.py" "api:$import_dir/verify_asset_inventory.py"
docker compose exec -T api python "$import_dir/verify_asset_inventory.py" --input-dir "$import_dir/inventory" --expected-json "$import_dir/expected.json"
docker compose exec -T api python "$import_dir/publish_asset_inventory.py" --inventory-dir "$import_dir/inventory" --root /app/var/assets
docker compose exec -T api python "$import_dir/verify_asset_inventory.py" --root /app/var/assets --expected-json "$import_dir/expected.json"
printf '%s\n' 'PASS: API healthy; input counts verified; asset snapshot published and read back. Log in as an authorized user and verify /assets. Business freshness and runtime lineage remain unverified.'
