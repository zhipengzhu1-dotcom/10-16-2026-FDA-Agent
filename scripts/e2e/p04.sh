#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-fda-e2e-p04}"

now() { python3 -c 'import time; print(time.time())'; }
psql_db() { docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fda -d fda -qAt "$@"; }

docker compose down -v --remove-orphans
docker compose up -d --wait db
for migration in migrations/*.sql; do psql_db < "$migration"; done
addr=$(docker compose port db 5432)
export DATABASE_URL="postgresql://fda:fda@localhost:${addr##*:}/fda"

uv run fda-copilot ingest cfr | tail -n 1
echo "ROWS before guidance: $(psql_db -c "SELECT source, count(*) FROM reg_sections GROUP BY source")"

pdf_dir=$(mktemp -d)
start=$(now)
uv run fda-copilot ingest guidance --pdf-dir "$pdf_dir"
end=$(now)
cold=$(python3 -c "print(f'{$end - $start:.1f}')")
echo "COLD_SECONDS=${cold}"

second=$(uv run fda-copilot ingest guidance --pdf-dir "$pdf_dir")
echo "$second"

fail=0
if [[ "$second" != *"total: "*" rows, 0 changed"* ]]; then echo "FAIL: second run changed rows"; fail=1; fi
if ! python3 -c "import sys; sys.exit(0 if $cold <= 300 else 1)"; then
  echo "FAIL: cold guidance ingest over 300s"; fail=1
fi
uv run python scripts/e2e/p04.py "$pdf_dir" || fail=1

if (( fail )); then exit 1; fi
echo "P04 E2E OK"
