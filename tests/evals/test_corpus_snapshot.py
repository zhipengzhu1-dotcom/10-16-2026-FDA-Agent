import gzip
import hashlib
import importlib
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
corpus_snapshot = importlib.import_module("corpus_snapshot")
MIGRATION = Path(__file__).parents[2] / "migrations" / "001_reg_sections.sql"


def section(citation: str, text: str, effective: date) -> RegSection:
    return RegSection(
        citation=citation,
        source=RegSource.cfr,
        title="IND safety reporting.",
        text=text,
        effective_date=effective,
        url="https://www.ecfr.gov/current/title-21/section-312.32",
    )


def test_a_snapshot_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    snapshot = tmp_path / "corpus.jsonl.gz"
    snapshot.write_bytes(b"tampered")
    (tmp_path / "corpus.jsonl.gz.sha256").write_text("0" * 64 + "\n")

    with (
        psycopg.connect(os.environ["DATABASE_URL"]) as conn,
        pytest.raises(ValueError) as raised,
    ):
        corpus_snapshot.load(conn, snapshot)

    assert str(raised.value) == (
        "corpus.jsonl.gz: sha256 d121be3103007b41edf96f8262925f8c7d61894afe9a041843b631f69445bc57"
        " but the pin is " + "0" * 64
    )


def test_loading_a_snapshot_replaces_every_row_with_exactly_the_snapshot(tmp_path: Path) -> None:
    pinned = section("21 CFR 312.32(c)(2)", "Report within 7 calendar days.", date(2024, 1, 1))
    data = gzip.compress((pinned.model_dump_json() + "\n").encode(), mtime=0)
    snapshot = tmp_path / "corpus.jsonl.gz"
    snapshot.write_bytes(data)
    (tmp_path / "corpus.jsonl.gz.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(MIGRATION.read_text())
        upsert(
            conn,
            [
                section("21 CFR 312.32(c)(2)", "Report within 5 calendar days.", date(2027, 1, 1)),
                section("21 CFR 312.33", "Annual reports are due in 60 days.", date(2024, 1, 1)),
            ],
        )

        assert corpus_snapshot.load(conn, snapshot) == 1
        rows = conn.execute(
            "SELECT citation, effective_date, text FROM reg_sections ORDER BY citation"
        ).fetchall()
        conn.rollback()

    assert rows == [("21 CFR 312.32(c)(2)", date(2024, 1, 1), "Report within 7 calendar days.")]
