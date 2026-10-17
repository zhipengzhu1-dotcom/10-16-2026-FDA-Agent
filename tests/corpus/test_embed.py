import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fakes import FakeEmbedder

from fda_copilot import cli
from fda_copilot.corpus.embed import EmbedRun, QueryCache, batches, embed_corpus
from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource

MIGRATIONS = sorted((Path(__file__).parents[2] / "migrations").glob("*.sql"))


def section(citation: str, text: str) -> RegSection:
    return RegSection(
        citation=citation,
        source=RegSource.cfr,
        title="Annual reports.",
        text=text,
        effective_date=date(2024, 1, 1),
        url="https://www.ecfr.gov/current/title-21/section-312.33",
    )


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for migration in MIGRATIONS:
            conn.execute(migration.read_text())
        conn.execute("DELETE FROM reg_sections")
        conn.execute("DELETE FROM query_embeddings")
        yield conn
        conn.rollback()


def test_a_second_run_embeds_only_rows_whose_text_changed(conn: psycopg.Connection) -> None:
    fake_embedder = FakeEmbedder()
    upsert(
        conn,
        [
            section("21 CFR 312.33", "Submit an annual report within 60 days."),
            section("21 CFR 312.33(a)", "Give the individual study information."),
        ],
    )

    first = embed_corpus(conn, fake_embedder)
    second = embed_corpus(conn, fake_embedder)
    upsert(conn, [section("21 CFR 312.33(a)", "Give a brief summary of each study.")])
    third = embed_corpus(conn, fake_embedder)

    assert (first, second, third) == (
        EmbedRun(embedded=2, unchanged=0, tokens=16),
        EmbedRun(embedded=0, unchanged=2, tokens=0),
        EmbedRun(embedded=1, unchanged=1, tokens=9),
    )
    assert fake_embedder.calls[-1] == (
        ["Annual reports.\n\nGive a brief summary of each study."],
        "document",
    )


def test_batches_split_on_text_count_and_on_characters() -> None:
    texts = ["aaaa", "bb", "cccccc", "d", "e", "f"]

    assert list(batches(texts, len, max_texts=3, max_chars=7)) == [
        ["aaaa", "bb"],
        ["cccccc", "d"],
        ["e", "f"],
    ]


def test_an_oversized_text_gets_a_batch_of_its_own() -> None:
    assert list(batches(["a", "x" * 10, "b"], len, max_texts=5, max_chars=4)) == [
        ["a"],
        ["x" * 10],
        ["b"],
    ]


def test_the_query_cache_embeds_a_query_once(conn: psycopg.Connection) -> None:
    fake_embedder = FakeEmbedder()
    cache = QueryCache(conn, "fake", lambda: fake_embedder)

    first = cache("annual report deadline")
    second = cache("annual report deadline")

    assert first == second
    assert fake_embedder.calls == [(["annual report deadline"], "query")]


def test_embed_without_a_key_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    assert cli.main(["embed", "--model", "voyage-law-2"]) == 1
    assert capsys.readouterr().err == (
        "fda-copilot embed: VOYAGE_API_KEY is not set."
        " Add it to .env or the environment to embed with voyage-law-2.\n"
    )
