import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest

from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource
from fda_copilot.retrieval.keyword import KeywordRetriever

MIGRATION = Path(__file__).parents[2] / "migrations" / "001_reg_sections.sql"


def section(citation: str, text: str, effective: date = date(2024, 1, 1)) -> RegSection:
    return RegSection(
        citation=citation,
        source=RegSource.cfr,
        title="IND safety reporting.",
        text=text,
        effective_date=effective,
        url="https://www.ecfr.gov/current/title-21/section-312.32",
    )


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(MIGRATION.read_text())
        conn.execute("DELETE FROM reg_sections")
        yield conn
        conn.rollback()


def test_keyword_search_ranks_matching_rows_and_returns_only_the_latest_version(
    conn: psycopg.Connection,
) -> None:
    upsert(
        conn,
        [
            section(
                "21 CFR 312.32(c)(2)",
                "Report fatal reactions within 15 calendar days.",
                date(2010, 9, 28),
            ),
            section("21 CFR 312.32(c)(2)", "Report fatal reactions within 7 calendar days."),
            section("21 CFR 312.32(b)", "Review each fatal case promptly."),
            section("21 CFR 312.33", "Annual reports are due within 60 days."),
        ],
    )

    hits = KeywordRetriever(conn).retrieve("fatal reaction", 5)

    assert [(hit.section.citation, hit.section.text) for hit in hits] == [
        ("21 CFR 312.32(c)(2)", "Report fatal reactions within 7 calendar days."),
        ("21 CFR 312.32(b)", "Review each fatal case promptly."),
    ]


def test_a_query_without_words_retrieves_nothing(conn: psycopg.Connection) -> None:
    upsert(conn, [section("21 CFR 312.33", "Annual reports are due within 60 days.")])

    assert KeywordRetriever(conn).retrieve("?!", 5) == []
