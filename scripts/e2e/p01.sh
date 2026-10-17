#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

expected='{"status":"ok","db":"ok"}'
now() { python3 -c 'import time; print(time.time())'; }

fetch_health() {
  local addr
  addr=$(docker compose port api 8000)
  curl -sS "http://localhost:${addr##*:}/health" 2>&1 || true
}

if [[ "${1:-}" == "--check-only" ]]; then
  body=$(fetch_health)
else
  docker compose down -v --remove-orphans
  docker compose build --quiet api

  start=$(now)
  docker compose up -d --wait --wait-timeout 60
  body=$(fetch_health)
  end=$(now)
  echo "START_SECONDS=$(python3 -c "print(f'{$end - $start:.1f}')")"
fi

echo "BODY=${body}"
if [[ "$body" != "$expected" ]]; then
  echo "HEALTH FAIL: expected ${expected}"
  exit 1
fi
echo "HEALTH OK"
