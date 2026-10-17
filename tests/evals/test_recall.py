import importlib
import sys
from pathlib import Path

import pytest

from fda_copilot.domain.models import Citation

RETRIEVAL = Path(__file__).parents[2] / "evals" / "retrieval"
sys.path.insert(0, str(RETRIEVAL))
run = importlib.import_module("run")

TEXTS = {
    "21 CFR 312.32(c)(1)": "(c)(1) IND safety reports. The sponsor must notify FDA in no case "
    "later than 15 calendar days after the sponsor determines that the information qualifies.",
    "21 CFR 312.32(c)(2)": "(2) Unexpected fatal or life-threatening suspected adverse reaction "
    "reports. The sponsor must also notify FDA in no case later than 7 calendar days.",
    "21 CFR 56.111(a)(1)": "(1) Risks to subjects are minimized: (i) By using procedures which are "
    "consistent with sound research design and which do not unnecessarily expose subjects.",
    "21 CFR 58.33": "The study director has overall responsibility for the technical conduct of "
    "the study.",
    "21 CFR 58.35(a)": "(a) A testing facility shall have a quality assurance unit.",
}
QUESTIONS = [
    run.Question.model_validate(
        {
            "id": "ind-1",
            "domain": "IND",
            "question": "What are the sponsor's IND safety reporting obligations?",
            "citations": [{"citation": "21 CFR 312.32(c)", "quote": "IND safety reports"}],
        }
    ),
    run.Question.model_validate(
        {
            "id": "gcp-1",
            "domain": "GCP",
            "question": "Must the IRB check that procedures follow sound research design?",
            "citations": [{"citation": "21 CFR 56.111(a)(1)(i)", "quote": "sound research design"}],
        }
    ),
    run.Question.model_validate(
        {
            "id": "glp-1",
            "domain": "GLP",
            "question": "What is the study director responsible for?",
            "citations": [{"citation": "21 CFR 58.33", "quote": "overall responsibility"}],
        }
    ),
]
RETRIEVED = {
    "ind-1": ["21 CFR 312.32(c)(2)", "21 CFR 312.32(c)(1)"],
    "gcp-1": [
        "21 CFR 58.35(a)",
        "21 CFR 58.33",
        "21 CFR 312.32(c)(1)",
        "21 CFR 312.32(c)(2)",
        "21 CFR 58.33",
        "21 CFR 56.111(a)(1)",
    ],
    "glp-1": ["21 CFR 58.35(a)", "21 CFR 58.33"],
}


def test_recall_at_5_credits_rows_that_hold_the_label_and_ignores_rank_six() -> None:
    resolved = run.resolve_labels(QUESTIONS, TEXTS)

    assert run.recall_at_k(QUESTIONS, resolved, RETRIEVED) == {
        "overall": 0.6667,
        "IND": 1.0,
        "GLP": 1.0,
        "GCP": 0.0,
    }


def test_a_parent_label_credits_only_the_rows_that_hold_its_quote() -> None:
    texts = {
        "21 CFR 312.32(c)(1)": "(c)(1) IND safety reports. The sponsor must notify FDA and all "
        "participating investigators in an IND safety report of potential serious risks.",
        "21 CFR 312.32(c)(3)": "(3) Reporting format or frequency. FDA may require a sponsor to "
        "submit IND safety reports in a format or at a frequency different than that required.",
    }
    ind_04 = run.Question.model_validate(
        {
            "id": "ind-04",
            "domain": "IND",
            "question": "What are the sponsor's IND safety reporting obligations to FDA and to "
            "participating investigators?",
            "citations": [
                {
                    "citation": "21 CFR 312.32(c)",
                    "quote": "IND safety reports. The sponsor must notify FDA and all "
                    "participating investigators",
                }
            ],
        }
    )
    resolved = run.resolve_labels([ind_04], texts)

    assert run.recall_at_k([ind_04], resolved, {"ind-04": ["21 CFR 312.32(c)(3)"]}) == {
        "overall": 0.0,
        "IND": 0.0,
    }
    assert run.recall_at_k([ind_04], resolved, {"ind-04": ["21 CFR 312.32(c)(1)"]}) == {
        "overall": 1.0,
        "IND": 1.0,
    }


def test_a_label_without_a_stored_row_or_its_quote_fails_loudly() -> None:
    broken = [
        QUESTIONS[0].model_copy(
            update={
                "citations": (
                    Citation(citation="21 CFR 312.99", quote="anything"),
                    Citation(citation="21 CFR 58.33", quote="not in the text"),
                )
            }
        )
    ]

    with pytest.raises(run.UnresolvedLabels) as raised:
        run.resolve_labels(broken, TEXTS)

    assert str(raised.value) == (
        "ind-1: 21 CFR 312.99 resolves to no stored row\n"
        "ind-1: 21 CFR 58.33 rows lack 'not in the text'"
    )


def test_a_value_below_its_baseline_is_a_regression() -> None:
    recall = {"overall": 0.6842, "IDE": 0.4667}

    assert run.regressions(recall, {"overall": 0.6843, "IDE": 0.4667}) == [
        "overall: recall@5 0.6842 < baseline 0.6843"
    ]
