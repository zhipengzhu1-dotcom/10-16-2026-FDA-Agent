#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

expected='{"status":"ok","db":"ok"}'
now() { python3 -c 'import time; print(time.time())'; }

docker compose down -v --remove-orphans
docker compose build --quiet api

start=$(now)
docker compose up -d --wait --wait-timeout 60
body=$(curl -fsS "http://localhost:${API_PORT:-8000}/health")
end=$(now)

echo "START_SECONDS=$(python3 -c "print(f'{$end - $start:.1f}')")"
echo "BODY=${body}"
if [[ "$body" != "$expected" ]]; then
  echo "HEALTH FAIL: expected ${expected}"
  exit 1
fi
echo "HEALTH OK"
