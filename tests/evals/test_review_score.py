import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fda_copilot.domain.models import Domain, Finding

REVIEW = Path(__file__).parents[2] / "evals" / "review"
sys.path.insert(0, str(REVIEW))
score = importlib.import_module("score")
build = importlib.import_module("build")

REGTEXT = {
    "21 CFR 50.25(a)(5)": "(5) A statement describing the extent, if any, to which confidentiality "
    "of records identifying the subject will be maintained and that notes the possibility that "
    "the Food and Drug Administration may inspect the records.",
    "21 CFR 50.25(a)(8)": "(8) A statement that participation is voluntary, that refusal to "
    "participate will involve no penalty or loss of benefits to which the subject is otherwise "
    "entitled",
}
HEADINGS = {
    "sec-1": "Confidentiality",
    "sec-2": "Voluntary Participation",
    "sec-3": "Research-Related Injury",
    "sec-4": "Benefits",
}
INSPECT = "the Food and Drug Administration may inspect the records"
VOLUNTARY = "statement that participation is voluntary"


def gold_row(section: str, citation: str) -> object:
    return score.GoldViolation(
        protocol="gcp-x",
        domain=Domain.GCP,
        section=section,
        citation=citation,
        quote="unused by the scorer",
        issue="planted",
        held_out=False,
    )


GOLD = [
    gold_row("Confidentiality", "21 CFR 50.25(a)(5)"),
    gold_row("Voluntary Participation", "21 CFR 50.25(a)(8)"),
    gold_row("Research-Related Injury", "21 CFR 50.25(a)(6)"),
]


def finding(section_id: str, *citations: tuple[str, str], domain: str = "GCP") -> Finding:
    return Finding.model_validate(
        {
            "doc_section_id": section_id,
            "domain": domain,
            "severity": "major",
            "issue": "missing consent element",
            "citations": [{"citation": c, "quote": q} for c, q in citations],
            "proposed_fix": "add the element",
        }
    )


def review(*findings: Finding, headings: dict[str, str] = HEADINGS) -> Any:
    return score.Review(headings=headings, findings=findings)


def test_two_findings_against_three_gold_rows() -> None:
    findings = review(
        finding("sec-1", ("21 CFR 50.25(a)(5)", INSPECT)),
        finding("sec-2", ("21 CFR 50.25(a)(5)", "FDA may look at your records")),
    )

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT.get)

    assert report.recall == 0.6667
    assert report.precision == 1.0
    assert report.citation_accuracy == 0.5
    assert report.faithfulness == 0.5
    assert [row.section for row in report.missed] == ["Research-Related Injury"]
    assert report.false_positives == ()


def test_section_match_ignores_case_and_spacing_but_not_domain_or_duplicates() -> None:
    headings = {
        "a": "  confidentiality ",
        "b": "Confidentiality",
        "c": "Voluntary  Participation",
        "d": "Benefits",
    }
    findings = review(
        finding("a", ("21 CFR 50.25(a)(5)", INSPECT)),
        finding("b", ("21 CFR 50.25(a)(5)", INSPECT)),
        finding("c", ("21 CFR 50.25(a)(8)", VOLUNTARY), domain="IND"),
        finding("d", ("21 CFR 50.25(a)(3)", "benefits to the subject or to others")),
        headings=headings,
    )

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT.get)

    assert report.recall == 0.3333
    assert report.precision == 0.25
    assert report.citation_accuracy == 0.25
    assert [(fp.finding.doc_section_id, fp.finding.domain) for fp in report.false_positives] == [
        ("b", Domain.GCP),
        ("c", Domain.IND),
        ("d", Domain.GCP),
    ]


def test_findings_match_on_the_heading_their_section_id_maps_to() -> None:
    findings = review(
        finding("sec-2", ("21 CFR 50.25(a)(8)", VOLUNTARY)),
        finding("Confidentiality", ("21 CFR 50.25(a)(5)", INSPECT)),
        finding("sec-9", ("21 CFR 50.25(a)(5)", INSPECT)),
    )

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT.get)

    assert (report.recall, report.precision, report.citation_accuracy) == (0.3333, 0.3333, 0.3333)
    assert [(s.finding.doc_section_id, s.heading, s.gold is not None) for s in report.scored] == [
        ("sec-2", "Voluntary Participation", True),
        ("Confidentiality", None, False),
        ("sec-9", None, False),
    ]


def test_findings_for_another_protocol_do_not_match() -> None:
    stray = review(finding("sec-1", ("21 CFR 50.25(a)(5)", INSPECT)))

    report = score.score(GOLD, {"gcp-y": stray}, REGTEXT.get)

    assert (report.recall, report.precision) == (0.0, 0.0)
    assert [fp.protocol for fp in report.false_positives] == ["gcp-y"]


def test_quotes_under_citations_missing_from_the_text_store_are_reported() -> None:
    benefits = "21 CFR 50.25(a)(3)"
    findings = review(
        finding("sec-1", ("21 CFR 50.25(a)(5)", INSPECT)),
        finding("sec-4", (benefits, "benefits to the subject or to others"), ("21 CFR 9", "x")),
    )
    store = {
        **REGTEXT,
        benefits: "(3) A description of any benefits to the subject or to others which may "
        "reasonably be expected from the research.",
    }

    with_regtext = score.score(GOLD, {"gcp-x": findings}, REGTEXT.get)
    with_store = score.score(GOLD, {"gcp-x": findings}, store.get)

    assert (with_regtext.faithfulness, with_regtext.unknown_citations) == (0.5, 2)
    assert [s.unknown_citations for s in with_regtext.scored] == [(), (benefits, "21 CFR 9")]
    assert (with_store.faithfulness, with_store.unknown_citations) == (0.5, 1)
    assert [s.unknown_citations for s in with_store.scored] == [(), ("21 CFR 9",)]


def test_null_reviewer_misses_every_planted_violation() -> None:
    gold = score.load_gold()
    reviews = score.review_all(score.NullReviewer(), gold)

    report = score.score(gold, reviews)

    assert report.recall == 0.0
    assert (report.precision, report.citation_accuracy, report.faithfulness) == (None, None, None)
    assert report.missed == tuple(gold)


def test_held_out_split_is_one_third_of_protocols() -> None:
    held_out = {row.protocol for row in score.load_gold(score.Split.held_out)}
    tuning = {row.protocol for row in score.load_gold(score.Split.tuning)}

    assert held_out == {"ind-03", "ide-03", "glp-03", "gcp-03"}
    assert len(tuning) == 8
    assert held_out.isdisjoint(tuning)


def test_cli_prints_recall_and_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "review-null.json"

    run = subprocess.run(
        [
            sys.executable,
            str(REVIEW / "score.py"),
            "--reviewer",
            "null",
            "--domain",
            "GLP",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "recall 0.00" in run.stdout.splitlines()
    assert "unknown citations 0" in run.stdout.splitlines()
    assert "MISSED glp-01 | Quality Assurance | 21 CFR 58.35(a)" in run.stdout.splitlines()
    saved = json.loads(out.read_text())
    assert (saved["recall"], saved["planted"], saved["findings"]) == (0.0, 10, 0)


def test_committed_protocols_and_gold_match_their_source() -> None:
    assert build.drift(build.render()) == set()


def test_citing_every_stored_regulation_with_a_one_word_quote_does_not_score() -> None:
    gold = score.load_gold()
    shotgun = [(citation, "the") for citation in score.load_regtext()]
    sections: dict[str, dict[str, str]] = {}
    findings: dict[str, list[Finding]] = {}
    for row in gold:
        section_id = f"sec-{len(sections.setdefault(row.protocol, {})) + 1}"
        sections[row.protocol][section_id] = row.section
        findings.setdefault(row.protocol, []).append(
            finding(section_id, *shotgun, domain=row.domain)
        )
    reviews = {p: review(*findings[p], headings=sections[p]) for p in findings}

    report = score.score(gold, reviews)

    assert (report.recall, report.precision) == (1.0, 1.0)
    assert report.citation_accuracy == 0.0217
    assert report.faithfulness == 0.0
    assert report.unknown_citations == 0


def test_a_quote_counts_only_with_five_words_from_its_own_citation() -> None:
    confidentiality = "21 CFR 50.25(a)(5)"
    findings = review(
        finding("sec-1", (confidentiality, "Food and Drug Administration may inspect")),
        finding("sec-1", (confidentiality, "Drug Administration may inspect")),
        finding("sec-1", (confidentiality, "refusal to participate will involve no")),
        finding("sec-2", ("21 CFR 50.25(a)(8)", VOLUNTARY), (confidentiality, "inspect")),
    )

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT.get)

    assert report.faithfulness == 0.25
    assert report.citation_accuracy == 0.5
