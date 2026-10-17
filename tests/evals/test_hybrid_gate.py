import importlib
import json
import os
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fakes import FakeEmbedder
from psycopg.conninfo import make_conninfo

from fda_copilot.corpus.embed import QueryCache, embed_corpus
from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "evals" / "retrieval"))
run = importlib.import_module("run")

GATE_DB = "fda_hybrid_gate"
TEXTS = {
    "21 CFR 312.32(c)(1)": "Report a serious unexpected adverse reaction to FDA within 15 days.",
    "21 CFR 58.31": "Testing facility management designates a replacement promptly.",
    "21 CFR 58.33": "The study director has overall responsibility for the nonclinical study.",
    "21 CFR 58.35(a)": "A quality assurance unit monitors each study.",
    "21 CFR 58.105": "Each test article in a study is characterized.",
    "21 CFR 58.120": "Each study has an approved written protocol.",
    "21 CFR 58.185": "A final report is prepared for each study.",
}
QUESTIONS = [
    run.Question.model_validate(
        {
            "id": "ind-1",
            "domain": "IND",
            "question": "Report an adverse reaction to FDA how fast?",
            "citations": [{"citation": "21 CFR 312.32(c)(1)", "quote": "15 days"}],
        }
    ),
    run.Question.model_validate(
        {
            "id": "glp-1",
            "domain": "GLP",
            "question": "Who has overall responsibility for a nonclinical study?",
            "citations": [{"citation": "21 CFR 58.33", "quote": "overall responsibility"}],
        }
    ),
    run.Question.model_validate(
        {
            "id": "glp-2",
            "domain": "GLP",
            "question": "Who steps in when a study director leaves a study?",
            "citations": [{"citation": "21 CFR 58.31", "quote": "designates a replacement"}],
        }
    ),
]


class Voyage4Fake(FakeEmbedder):
    model = "voyage-4"


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[psycopg.Connection]:
    admin_url = os.environ["DATABASE_URL"]
    url = make_conninfo(admin_url, dbname=GATE_DB)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {GATE_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {GATE_DB}")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr(run, "load_questions", lambda: QUESTIONS)
    with psycopg.connect(url, autocommit=True) as conn:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            conn.execute(migration.read_text())
        upsert(
            conn,
            [
                RegSection(
                    citation=citation,
                    source=RegSource.cfr,
                    title="Section.",
                    text=text,
                    effective_date=date(2024, 1, 1),
                    url="https://www.ecfr.gov/current/title-21",
                )
                for citation, text in TEXTS.items()
            ],
        )
        embed_corpus(conn, Voyage4Fake())
        yield conn
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE {GATE_DB} WITH (FORCE)")


def cache_queries(conn: psycopg.Connection, questions: list[str]) -> None:
    cache = QueryCache(conn, "voyage-4", Voyage4Fake)
    for question in questions:
        cache(question)


def write_baselines(path: Path, **recalls: dict[str, float]) -> Path:
    retrieval = {name: {"recall_at_5": recall} for name, recall in recalls.items()}
    path.write_text(json.dumps({"retrieval": retrieval}))
    return path


@pytest.mark.parametrize(
    ("baselines", "code", "err"),
    [
        (
            {"keyword": {"overall": 0.6, "IND": 0.9, "GLP": 0.4}},
            0,
            "",
        ),
        (
            {"keyword": {"overall": 0.6, "IND": 0.9, "GLP": 0.5}},
            1,
            "FAIL GLP: hybrid recall@5 0.5000 does not beat the keyword baseline 0.5000\n",
        ),
        (
            {
                "keyword": {"overall": 0.6, "IND": 0.9, "GLP": 0.4},
                "hybrid": {"overall": 0.7, "IND": 1.0, "GLP": 0.5},
            },
            1,
            "FAIL overall: recall@5 0.6667 < baseline 0.7000\n",
        ),
        (
            {
                "keyword": {"overall": 0.7, "IND": 1.0, "GLP": 0.4},
                "hybrid": {"overall": 0.6, "IND": 1.0, "GLP": 0.5},
            },
            1,
            "FAIL overall: hybrid recall@5 0.6667 does not beat the keyword baseline 0.7000\n"
            "FAIL IND: hybrid recall@5 1.0000 does not beat the keyword baseline 1.0000\n",
        ),
    ],
    ids=["beats-keyword", "ties-keyword", "below-hybrid", "hybrid-ok-keyword-not"],
)
def test_the_hybrid_gate_requires_beating_keyword_and_meeting_its_own_baseline(
    database: psycopg.Connection,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    baselines: dict[str, dict[str, float]],
    code: int,
    err: str,
) -> None:
    cache_queries(database, [q.question for q in QUESTIONS])
    path = write_baselines(tmp_path / "baselines.json", **baselines)

    assert run.main(["--retriever", "hybrid", "--baselines", str(path)]) == code
    assert capsys.readouterr().err == err


def test_a_question_missing_from_the_query_cache_is_named(
    database: psycopg.Connection, tmp_path: Path
) -> None:
    cache_queries(database, [QUESTIONS[0].question, QUESTIONS[2].question])
    path = write_baselines(tmp_path / "baselines.json", keyword={"overall": 0.5})

    with pytest.raises(SystemExit) as raised:
        run.main(["--retriever", "hybrid", "--baselines", str(path)])

    assert str(raised.value) == (
        "The voyage-4 query cache is missing glp-1:"
        " 'Who has overall responsibility for a nonclinical study?'."
        " Load a current embedding snapshot, or set VOYAGE_API_KEY to embed it."
    )
