#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-fda-e2e-p05}"

docker compose down -v --remove-orphans
docker compose up -d --wait db
addr=$(docker compose port db 5432)
export DATABASE_URL="postgresql://fda:fda@localhost:${addr##*:}/fda"

uv run python scripts/corpus_snapshot.py load

raised=$(mktemp)
trap 'rm -f "$raised"' EXIT
uv run python - evals/baselines.json "$raised" <<'EOF'
import json, sys
baselines = json.load(open(sys.argv[1]))
floor = baselines["retrieval"]["keyword"]["recall_at_5"]
floor["overall"] = round(floor["overall"] + 0.01, 4)
json.dump(baselines, open(sys.argv[2], "w"))
print(f"raised overall baseline to {floor['overall']}")
EOF

fail=0
if uv run python evals/retrieval/run.py --retriever keyword --baselines "$raised"; then
  echo "FAIL: check 1 passed against a baseline above the measured recall"; fail=1
else
  echo "CHECK 1 FAILED as expected: recall@5 is below the raised baseline"
fi

if uv run python evals/retrieval/run.py --retriever keyword; then
  echo "CHECK 2 PASSED: recall@5 meets evals/baselines.json"
else
  echo "FAIL: check 2 failed against the stored baseline"; fail=1
fi

if (( fail )); then exit 1; fi
echo "P05 E2E OK"
