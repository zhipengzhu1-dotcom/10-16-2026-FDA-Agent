import importlib
import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
corpus_snapshot = importlib.import_module("corpus_snapshot")


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
