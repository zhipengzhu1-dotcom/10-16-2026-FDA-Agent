#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-fda-e2e-p06}"
model="${1:-voyage-4}"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
: "${VOYAGE_API_KEY:?is not set. P06 embeds the corpus with Voyage AI.}"

docker compose down -v --remove-orphans
docker compose up -d --wait db
addr=$(docker compose port db 5432)
export DATABASE_URL="postgresql://fda:fda@localhost:${addr##*:}/fda"

uv run python scripts/corpus_snapshot.py load
uv run fda-copilot embed --model "$model"
second=$(uv run fda-copilot embed --model "$model")
echo "$second"
if [[ "$second" != "$model: 0 embedded,"* ]]; then
  echo "FAIL: the second embed run re-embedded unchanged rows"; exit 1
fi

uv run python - "$model" <<'EOF'
import os, sys
import psycopg
from fda_copilot.corpus.embed import QueryCache, VoyageEmbedder
from fda_copilot.domain.models import Domain
from fda_copilot.retrieval.hybrid import HybridRetriever, domains_of

model = sys.argv[1]
queries = {
    Domain.IND: "How long after FDA receives an IND may a clinical investigation begin?",
    Domain.IDE: "Who decides whether a device study is significant risk?",
    Domain.GLP: "What must the quality assurance unit of a testing facility inspect?",
    Domain.GCP: "Which elements must an informed consent form give each subject?",
}
failed = 0
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    cache = QueryCache(conn, model, lambda: VoyageEmbedder.from_env(model))
    for domain, query in queries.items():
        [top] = HybridRetriever(conn, model, cache).retrieve(query, 1)
        ok = domain in domains_of(top.section.citation)
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {domain}: {query} -> {top.section.citation}")
sys.exit(1 if failed else 0)
EOF
echo "P06 E2E OK"
