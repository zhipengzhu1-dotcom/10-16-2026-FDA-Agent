import gzip
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fakes import FakeEmbedder

from fda_copilot.corpus.embed import QueryCache, embed_corpus
from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import Domain, RegSection, RegSource
from fda_copilot.retrieval.hybrid import HybridRetriever, domains_of

ROOT = Path(__file__).parents[2]
MIGRATIONS = sorted((ROOT / "migrations").glob("*.sql"))
EVAL = ROOT / "evals" / "retrieval"


def section(citation: str, title: str, text: str) -> RegSection:
    return RegSection(
        citation=citation,
        source=RegSource.cfr,
        title=title,
        text=text,
        effective_date=date(2024, 1, 1),
        url="https://www.ecfr.gov/current/title-21",
    )


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for migration in MIGRATIONS:
            conn.execute(migration.read_text())
        conn.execute("DELETE FROM reg_sections")
        conn.execute("DELETE FROM query_embeddings")
        upsert(
            conn,
            [
                section(
                    "21 CFR 312.32(c)(1)",
                    "IND safety reports.",
                    "Report a serious unexpected adverse reaction to FDA within 15 days.",
                ),
                section(
                    "21 CFR 812.150(a)(1)",
                    "Investigator reports.",
                    "Report an unanticipated adverse device effect to the sponsor within 10 days.",
                ),
                section(
                    "21 CFR 58.33",
                    "Study director.",
                    "The study director has overall responsibility for the nonclinical study.",
                ),
            ],
        )
        embed_corpus(conn, FakeEmbedder())
        yield conn
        conn.rollback()


def retriever(conn: psycopg.Connection, domain: Domain | None = None) -> HybridRetriever:
    return HybridRetriever(conn, "fake", QueryCache(conn, "fake", FakeEmbedder), domain)


def test_hybrid_retrieval_ranks_the_row_both_legs_agree_on_first(
    conn: psycopg.Connection,
) -> None:
    hits = retriever(conn).retrieve("report an adverse reaction to FDA", 5)

    assert [hit.section.citation for hit in hits] == [
        "21 CFR 312.32(c)(1)",
        "21 CFR 812.150(a)(1)",
        "21 CFR 58.33",
    ]


def test_a_domain_filter_keeps_only_rows_from_that_domain(conn: psycopg.Connection) -> None:
    hits = retriever(conn, Domain.IDE).retrieve("report an adverse reaction to FDA", 5)

    assert [hit.section.citation for hit in hits] == ["21 CFR 812.150(a)(1)"]


def test_every_stored_row_belongs_to_at_least_one_domain() -> None:
    with gzip.open(EVAL / "corpus.jsonl.gz") as corpus:
        unmapped = {
            json.loads(line)["citation"]
            for line in corpus
            if not domains_of(json.loads(line)["citation"])
        }

    assert unmapped == set()


def test_every_eval_label_is_in_its_question_domain() -> None:
    questions = [json.loads(line) for line in (EVAL / "questions.jsonl").read_text().splitlines()]

    outside = [
        (question["id"], label["citation"])
        for question in questions
        for label in question["citations"]
        if Domain(question["domain"]) not in domains_of(label["citation"])
    ]

    assert outside == []


def test_a_domain_filter_keeps_in_domain_keyword_hits_that_rank_below_500_others(
    conn: psycopg.Connection,
) -> None:
    upsert(
        conn,
        [section(f"21 CFR 312.{n}", "Study.", "study study study") for n in range(600)]
        + [section(f"21 CFR 58.90({n})", "Animal care.", "Records are kept.") for n in range(60)],
    )
    embed_corpus(conn, FakeEmbedder())
    animal_care = FakeEmbedder().embed(["Animal care.\n\nRecords are kept."], "query").vectors[0]
    glp = HybridRetriever(conn, "fake", lambda _query: animal_care, Domain.GLP)

    hits = glp.retrieve("study", 3)

    assert [hit.section.citation for hit in hits] == [
        "21 CFR 58.33",
        "21 CFR 58.90(0)",
        "21 CFR 58.90(1)",
    ]
