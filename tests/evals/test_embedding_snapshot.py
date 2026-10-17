import gzip
import importlib
import os
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fakes import FakeEmbedder

from fda_copilot.corpus.embed import EmbedRun, QueryCache, embed_corpus
from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
embedding_snapshot = importlib.import_module("embedding_snapshot")
corpus_snapshot = importlib.import_module("corpus_snapshot")


def section(citation: str, text: str) -> RegSection:
    return RegSection(
        citation=citation,
        source=RegSource.cfr,
        title="Study director.",
        text=text,
        effective_date=date(2024, 1, 1),
        url="https://www.ecfr.gov/current/title-21/section-58.33",
    )


def stored(conn: psycopg.Connection) -> list[tuple[str, ...]]:
    return [
        *conn.execute(
            "SELECT citation, text_hash, embedding::text FROM section_embeddings"
            " WHERE model = 'fake' ORDER BY citation"
        ).fetchall(),
        *conn.execute(
            "SELECT query, embedding::text FROM query_embeddings WHERE model = 'fake'"
        ).fetchall(),
    ]


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            conn.execute(migration.read_text())
        conn.execute("DELETE FROM reg_sections")
        conn.execute("DELETE FROM query_embeddings")
        upsert(
            conn,
            [
                section("21 CFR 58.33", "The study director has overall responsibility."),
                section("21 CFR 58.35(a)", "A quality assurance unit monitors each study."),
            ],
        )
        embed_corpus(conn, FakeEmbedder())
        QueryCache(conn, "fake", FakeEmbedder)("who runs a GLP study?")
        yield conn
        conn.rollback()


def test_a_loaded_snapshot_restores_every_vector_bit_for_bit(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    snapshot = tmp_path / "embeddings-fake.json.gz"
    before = stored(conn)
    embedding_snapshot.dump(conn, "fake", snapshot)
    conn.execute("DELETE FROM section_embeddings")
    conn.execute("DELETE FROM query_embeddings")

    loaded = embedding_snapshot.load(conn, "fake", snapshot)

    assert (len(loaded.sections), len(loaded.queries)) == (2, 1)
    assert stored(conn) == before
    assert len(before) == 3


def test_a_snapshot_older_than_the_corpus_text_is_refused(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    snapshot = tmp_path / "embeddings-fake.json.gz"
    embedding_snapshot.dump(conn, "fake", snapshot)
    upsert(conn, [section("21 CFR 58.35(a)", "A quality assurance unit inspects each study.")])

    with pytest.raises(embedding_snapshot.StaleSnapshot) as raised:
        embedding_snapshot.load(conn, "fake", snapshot)

    assert str(raised.value) == (
        "embeddings-fake.json.gz: 1 reg_sections rows have no fake vector for their current text,"
        " first 21 CFR 58.35(a). Re-embed and dump again."
    )


def test_a_snapshot_for_another_model_is_refused(conn: psycopg.Connection, tmp_path: Path) -> None:
    snapshot = tmp_path / "embeddings-fake.json.gz"
    embedding_snapshot.dump(conn, "fake", snapshot)

    with pytest.raises(ValueError) as raised:
        embedding_snapshot.load(conn, "voyage-4", snapshot)

    assert str(raised.value) == "embeddings-fake.json.gz holds fake vectors, not voyage-4"


def vector_citations(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT citation FROM section_embeddings WHERE model = 'fake' ORDER BY citation"
    ).fetchall()
    return [citation for (citation,) in rows]


def test_reloading_the_corpus_snapshot_keeps_the_vectors_of_unchanged_rows(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    snapshot = tmp_path / "corpus.jsonl.gz"
    corpus_snapshot.dump(conn, snapshot)

    assert corpus_snapshot.load(conn, snapshot) == 2
    assert vector_citations(conn) == ["21 CFR 58.33", "21 CFR 58.35(a)"]
    assert embed_corpus(conn, FakeEmbedder()) == EmbedRun(embedded=0, unchanged=2, tokens=0)


def test_a_row_dropped_from_the_corpus_snapshot_loses_its_row_and_its_vectors(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    snapshot = tmp_path / "corpus.jsonl.gz"
    kept = section("21 CFR 58.33", "The study director has overall responsibility.")
    corpus_snapshot.write_pinned(snapshot, gzip.compress((kept.model_dump_json() + "\n").encode()))

    assert corpus_snapshot.load(conn, snapshot) == 1
    assert conn.execute("SELECT citation FROM reg_sections").fetchall() == [("21 CFR 58.33",)]
    assert vector_citations(conn) == ["21 CFR 58.33"]


def test_loading_embeddings_before_the_corpus_fails_clearly(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    snapshot = tmp_path / "embeddings-fake.json.gz"
    embedding_snapshot.dump(conn, "fake", snapshot)
    conn.execute("DELETE FROM reg_sections")

    with pytest.raises(embedding_snapshot.CorpusNotLoaded) as raised:
        embedding_snapshot.load(conn, "fake", snapshot)

    assert str(raised.value) == (
        "embeddings-fake.json.gz: 2 vectors have no reg_sections row, first 21 CFR 58.33."
        " Run `scripts/corpus_snapshot.py load` first."
    )
