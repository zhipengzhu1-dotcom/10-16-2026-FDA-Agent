import importlib
import json
import subprocess
import sys
from pathlib import Path

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


def finding(section: str, citation: str, quote: str, domain: str = "GCP") -> Finding:
    return Finding.model_validate(
        {
            "doc_section_id": section,
            "domain": domain,
            "severity": "major",
            "issue": "missing consent element",
            "citations": [{"citation": citation, "quote": quote}],
            "proposed_fix": "add the element",
        }
    )


def test_two_findings_against_three_gold_rows() -> None:
    findings = [
        finding(
            "Confidentiality",
            "21 CFR 50.25(a)(5)",
            "the Food and Drug Administration may inspect the records",
        ),
        finding("Voluntary Participation", "21 CFR 50.25(a)(5)", "FDA may look at your records"),
    ]

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT)

    assert report.recall == 0.6667
    assert report.precision == 1.0
    assert report.citation_accuracy == 0.5
    assert report.faithfulness == 0.5
    assert [row.section for row in report.missed] == ["Research-Related Injury"]
    assert report.false_positives == ()


def test_section_match_ignores_case_and_spacing_but_not_domain_or_duplicates() -> None:
    findings = [
        finding("  confidentiality ", "21 CFR 50.25(a)(5)", "may inspect the records"),
        finding("Confidentiality", "21 CFR 50.25(a)(5)", "may inspect the records"),
        finding(
            "Voluntary Participation", "21 CFR 50.25(a)(8)", "participation is voluntary", "IND"
        ),
        finding("Benefits", "21 CFR 50.25(a)(3)", "benefits"),
    ]

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT)

    assert report.recall == 0.3333
    assert report.precision == 0.25
    assert report.citation_accuracy == 0.25
    assert [(fp.finding.doc_section_id, fp.finding.domain) for fp in report.false_positives] == [
        ("Confidentiality", Domain.GCP),
        ("Voluntary Participation", Domain.IND),
        ("Benefits", Domain.GCP),
    ]


def test_findings_for_another_protocol_do_not_match() -> None:
    stray = finding("Confidentiality", "21 CFR 50.25(a)(5)", "may inspect the records")

    report = score.score(GOLD, {"gcp-y": [stray]}, REGTEXT)

    assert (report.recall, report.precision) == (0.0, 0.0)
    assert [fp.protocol for fp in report.false_positives] == ["gcp-y"]


def test_null_reviewer_misses_every_planted_violation() -> None:
    gold = score.load_gold()
    findings = score.review_all(score.NullReviewer(), gold)

    report = score.score(gold, findings, score.load_regtext())

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
    assert "MISSED glp-01 | Quality Assurance | 21 CFR 58.35(a)" in run.stdout.splitlines()
    saved = json.loads(out.read_text())
    assert (saved["recall"], saved["planted"], saved["findings"]) == (0.0, 10, 0)


def test_committed_protocols_and_gold_match_their_source() -> None:
    assert build.drift(build.render()) == set()


def test_citing_every_stored_regulation_with_a_one_word_quote_does_not_score() -> None:
    gold = score.load_gold()
    regtext = score.load_regtext()
    shotgun = [{"citation": citation, "quote": "the"} for citation in regtext]
    findings: dict[str, list[Finding]] = {}
    for row in gold:
        findings.setdefault(row.protocol, []).append(
            Finding.model_validate(
                {
                    "doc_section_id": row.section,
                    "domain": row.domain,
                    "severity": "major",
                    "issue": "something is wrong",
                    "citations": shotgun,
                    "proposed_fix": "fix it",
                }
            )
        )

    report = score.score(gold, findings, regtext)

    assert (report.recall, report.precision) == (1.0, 1.0)
    assert report.citation_accuracy == 0.0217
    assert report.faithfulness == 0.0


def test_a_quote_counts_only_with_five_words_from_its_own_citation() -> None:
    confidentiality = "21 CFR 50.25(a)(5)"
    findings = [
        finding("Confidentiality", confidentiality, "Food and Drug Administration may inspect"),
        finding("Confidentiality", confidentiality, "Drug Administration may inspect"),
        finding("Confidentiality", confidentiality, "refusal to participate will involve no"),
        Finding.model_validate(
            {
                "doc_section_id": "Voluntary Participation",
                "domain": "GCP",
                "severity": "major",
                "issue": "penalty for leaving",
                "citations": [
                    {"citation": "21 CFR 50.25(a)(8)", "quote": "statement that participation is voluntary"},
                    {"citation": confidentiality, "quote": "inspect"},
                ],
                "proposed_fix": "remove the penalty",
            }
        ),
    ]

    report = score.score(GOLD, {"gcp-x": findings}, REGTEXT)

    assert report.faithfulness == 0.25
    assert report.citation_accuracy == 0.5
