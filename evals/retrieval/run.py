import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import mean, quantiles
from typing import Annotated, Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field

from fda_copilot.corpus.embed import (
    DEFAULT_MODEL,
    MODELS,
    MissingApiKey,
    QueryCache,
    VoyageEmbedder,
    pending,
)
from fda_copilot.domain.models import Citation, Domain
from fda_copilot.retrieval.citations import resolve, stored_texts
from fda_copilot.retrieval.hybrid import HybridRetriever
from fda_copilot.retrieval.keyword import KeywordRetriever
from fda_copilot.retrieval.retriever import Retriever

HERE = Path(__file__).parent
QUESTIONS = HERE / "questions.jsonl"
BASELINES = HERE.parent / "baselines.json"
K = 5


def _hybrid(conn: psycopg.Connection, model: str) -> Retriever:
    stale, total = pending(conn, model)
    if stale:
        raise SystemExit(
            f"{len(stale)} of {total} rows have no current {model} vector."
            f" Run `fda-copilot embed --model {model}` or load its embedding snapshot first."
        )
    return HybridRetriever(
        conn, model, QueryCache(conn, model, lambda: VoyageEmbedder.from_env(model))
    )


RETRIEVERS: dict[str, Callable[[psycopg.Connection, str], Retriever]] = {
    "keyword": lambda conn, _model: KeywordRetriever(conn),
    "hybrid": _hybrid,
}


class Question(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    domain: Domain
    question: str
    citations: Annotated[tuple[Citation, ...], Field(min_length=1)]


Resolved = tuple[frozenset[str], ...]


class UnresolvedLabels(Exception):
    pass


def load_questions(path: Path = QUESTIONS) -> list[Question]:
    return [Question.model_validate_json(line) for line in path.read_text().splitlines() if line]


def resolve_labels(questions: Sequence[Question], texts: Mapping[str, str]) -> dict[str, Resolved]:
    resolved: dict[str, Resolved] = {}
    problems = []
    for question in questions:
        rows = []
        for label in question.citations:
            holders = resolve(label.citation, texts)
            quoted = frozenset(holder for holder in holders if label.quote in texts[holder])
            if not holders:
                problems.append(f"{question.id}: {label.citation} resolves to no stored row")
            elif not quoted:
                problems.append(f"{question.id}: {label.citation} rows lack {label.quote!r}")
            rows.append(quoted)
        resolved[question.id] = tuple(rows)
    if problems:
        raise UnresolvedLabels("\n".join(problems))
    return resolved


def question_recall(labels: Resolved, retrieved: Sequence[str]) -> float:
    top = set(retrieved[:K])
    return sum(1 for holders in labels if holders & top) / len(labels)


def recall_at_k(
    questions: Sequence[Question],
    resolved: Mapping[str, Resolved],
    retrieved: Mapping[str, Sequence[str]],
) -> dict[str, float]:
    scores = {q.id: question_recall(resolved[q.id], retrieved[q.id]) for q in questions}
    by_domain = {
        domain.value: [scores[q.id] for q in questions if q.domain is domain] for domain in Domain
    }
    return {
        "overall": round(mean(scores.values()), 4),
        **{domain: round(mean(values), 4) for domain, values in by_domain.items() if values},
    }


def regressions(recall: Mapping[str, float], baseline: Mapping[str, float]) -> list[str]:
    return [
        f"{name}: recall@{K} {recall.get(name, 0.0):.4f} < baseline {floor:.4f}"
        for name, floor in baseline.items()
        if recall.get(name, 0.0) < floor
    ]


def gate(
    retriever: str, recall: Mapping[str, float], baselines: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    stored = {name: entry[f"recall_at_{K}"] for name, entry in baselines["retrieval"].items()}
    keyword = stored["keyword"]
    if retriever == "keyword":
        return regressions(recall, keyword)
    return (regressions(recall, stored["hybrid"]) if "hybrid" in stored else []) + [
        f"{name}: hybrid recall@{K} {recall.get(name, 0.0):.4f}"
        f" does not beat the keyword baseline {floor:.4f}"
        for name, floor in keyword.items()
        if recall.get(name, 0.0) <= floor
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Score recall@{K} on the retrieval eval set.")
    parser.add_argument("--retriever", choices=sorted(RETRIEVERS), required=True)
    parser.add_argument(
        "--embedding-model",
        choices=MODELS,
        default=DEFAULT_MODEL,
        help="query and corpus vectors for the hybrid retriever",
    )
    parser.add_argument("--baselines", type=Path, default=BASELINES)
    parser.add_argument("--json", type=Path, help="write the per-question report here")
    parser.add_argument(
        "--write-baseline", action="store_true", help="record this run as the new baseline"
    )
    args = parser.parse_args(argv)

    questions = load_questions()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        resolved = resolve_labels(questions, stored_texts(conn))
        retriever = RETRIEVERS[args.retriever](conn, args.embedding_model)
        retrieved: dict[str, list[str]] = {}
        latencies: list[float] = []
        for q in questions:
            start = time.perf_counter()
            try:
                hits = retriever.retrieve(q.question, K)
            except MissingApiKey:
                raise SystemExit(
                    f"The {args.embedding_model} query cache is missing {q.id}: {q.question!r}."
                    " Load a current embedding snapshot, or set VOYAGE_API_KEY to embed it."
                ) from None
            latencies.append((time.perf_counter() - start) * 1000)
            retrieved[q.id] = [hit.section.citation for hit in hits]
    recall = recall_at_k(questions, resolved, retrieved)
    latency = {
        "p50": round(quantiles(latencies, n=100)[49], 1),
        "p95": round(quantiles(latencies, n=100)[94], 1),
    }

    counts = Counter(q.domain.value for q in questions)
    counts["overall"] = len(questions)
    print(f"{'domain':<8} {'questions':>9} {'recall@' + str(K):>9}")
    for name, value in recall.items():
        print(f"{name:<8} {counts[name]:>9} {value:>9.4f}")
    print(f"latency ms p50 {latency['p50']} p95 {latency['p95']}")

    if args.json:
        report = {
            "retriever": args.retriever,
            "embedding_model": args.embedding_model if args.retriever == "hybrid" else None,
            "k": K,
            "recall": recall,
            "latency_ms": latency,
            "questions": [
                {
                    "id": q.id,
                    "domain": q.domain.value,
                    "recall": question_recall(resolved[q.id], retrieved[q.id]),
                    "labels": {
                        label.citation: sorted(holders)
                        for label, holders in zip(q.citations, resolved[q.id], strict=True)
                    },
                    "retrieved": retrieved[q.id],
                }
                for q in questions
            ],
        }
        args.json.write_text(json.dumps(report, indent=2) + "\n")

    baselines = json.loads(args.baselines.read_text())
    if args.write_baseline:
        baselines.setdefault("retrieval", {})[args.retriever] = {f"recall_at_{K}": recall}
        args.baselines.write_text(json.dumps(baselines, indent=2) + "\n")
        print(f"baseline written to {args.baselines}")
        return 0
    failures = gate(args.retriever, recall, baselines)
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"PASS recall@{K} clears every {args.retriever} gate in {args.baselines}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
