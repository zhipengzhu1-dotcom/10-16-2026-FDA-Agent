#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-fda-e2e-p03}"

now() { python3 -c 'import time; print(time.time())'; }
psql_db() { docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fda -d fda -qAt "$@"; }

docker compose down -v --remove-orphans
docker compose up -d --wait db
for migration in migrations/*.sql; do psql_db < "$migration"; done
addr=$(docker compose port db 5432)
export DATABASE_URL="postgresql://fda:fda@localhost:${addr##*:}/fda"

start=$(now)
uv run fda-copilot ingest cfr
end=$(now)
cold=$(python3 -c "print(f'{$end - $start:.1f}')")
echo "COLD_SECONDS=${cold}"

second=$(uv run fda-copilot ingest cfr)
echo "$second"

fail=0
for part in 50 56 58 312 812; do
  rows=$(psql_db -c "SELECT count(*) FROM reg_sections WHERE citation LIKE '21 CFR ${part}.%'")
  echo "ROWS part ${part}=${rows}"
  if (( rows < 20 )); then echo "FAIL: part ${part} stores fewer than 20 rows"; fail=1; fi
done

text=$(psql_db -c "SELECT text FROM reg_sections WHERE citation = '21 CFR 312.32(c)(1)'")
echo "QUERY 21 CFR 312.32(c)(1)=${text:0:160}"

if [[ "$second" != *"total: "*" rows, 0 changed"* ]]; then echo "FAIL: second run changed rows"; fail=1; fi
if [[ "$text" != *"IND safety report"* ]]; then echo "FAIL: query lacks 'IND safety report'"; fail=1; fi
if python3 -c "import sys; sys.exit(0 if $cold <= 180 else 1)"; then :; else echo "FAIL: cold ingest over 180s"; fail=1; fi

if (( fail )); then exit 1; fi
echo "P03 E2E OK"
