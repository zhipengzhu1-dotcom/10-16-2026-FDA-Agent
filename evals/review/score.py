"""Score a reviewer's findings against the planted-violation gold set.

Matching rule. A finding matches a gold row when all three hold:
  1. the finding was returned for the gold row's protocol,
  2. the finding's domain equals the row's domain, and
  3. the finding's doc_section_id equals the row's section heading, ignoring case and
     runs of whitespace.
Each gold row matches at most one finding. The first finding in reviewer order wins, and
later findings on the same row are false positives. The citation is not part of the match,
so a finding in the right section with the wrong citation counts toward recall and
precision but not citation accuracy.

Metrics, rounded to four places:
  recall             matched gold rows / gold rows
  precision          matched findings / findings
  citation accuracy  matched findings citing the row's citation / findings
  faithfulness       findings whose every quote occurs in the stored text of its citation
                     (regtext.json, whitespace-normalized) / findings
Precision, citation accuracy, and faithfulness are None when there are no findings.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from fda_copilot.domain.models import Domain, Finding, RegCitation

HERE = Path(__file__).parent


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GoldViolation(_Frozen):
    protocol: str
    domain: Domain
    section: str
    citation: RegCitation
    quote: str
    issue: str
    held_out: bool


class FalsePositive(_Frozen):
    protocol: str
    finding: Finding


class Report(_Frozen):
    planted: int
    findings: int
    recall: float
    precision: float | None
    citation_accuracy: float | None
    faithfulness: float | None
    missed: tuple[GoldViolation, ...]
    false_positives: tuple[FalsePositive, ...]


class Reviewer(Protocol):
    def review(self, document: Path, domain: Domain) -> list[Finding]: ...


class NullReviewer:
    def review(self, document: Path, domain: Domain) -> list[Finding]:
        return []


REVIEWERS: dict[str, type[Reviewer]] = {"null": NullReviewer}


class Split(StrEnum):
    all = "all"
    tuning = "tuning"
    held_out = "held-out"


def _squash(text: str) -> str:
    return " ".join(text.split())


def _section_key(protocol: str, heading: str) -> tuple[str, str]:
    return protocol, _squash(heading).casefold()


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def score(
    gold: Sequence[GoldViolation],
    findings: Mapping[str, Sequence[Finding]],
    regtext: Mapping[str, str],
) -> Report:
    open_rows = {_section_key(row.protocol, row.section): row for row in gold}
    if len(open_rows) != len(gold):
        raise ValueError("two gold rows share a protocol section")
    stored = {_squash(citation): _squash(text) for citation, text in regtext.items()}

    hits: list[tuple[Finding, GoldViolation]] = []
    false_positives: list[FalsePositive] = []
    for protocol, batch in findings.items():
        for finding in batch:
            key = _section_key(protocol, finding.doc_section_id)
            row = open_rows.get(key)
            if row is not None and row.domain is finding.domain:
                del open_rows[key]
                hits.append((finding, row))
            else:
                false_positives.append(FalsePositive(protocol=protocol, finding=finding))

    every = [finding for batch in findings.values() for finding in batch]
    cited = sum(
        any(_squash(c.citation) == _squash(row.citation) for c in finding.citations)
        for finding, row in hits
    )
    faithful = sum(
        all(_squash(c.quote) in stored.get(_squash(c.citation), "") for c in finding.citations)
        for finding in every
    )
    remaining = set(open_rows.values())
    return Report(
        planted=len(gold),
        findings=len(every),
        recall=_ratio(len(hits), len(gold)) or 0.0,
        precision=_ratio(len(hits), len(every)),
        citation_accuracy=_ratio(cited, len(every)),
        faithfulness=_ratio(faithful, len(every)),
        missed=tuple(row for row in gold if row in remaining),
        false_positives=tuple(false_positives),
    )


def load_gold(split: Split = Split.all, domain: Domain | None = None) -> list[GoldViolation]:
    rows = [
        GoldViolation.model_validate_json(line)
        for line in (HERE / "gold.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return [
        row
        for row in rows
        if (split is Split.all or row.held_out == (split is Split.held_out))
        and (domain is None or row.domain is domain)
    ]


def load_regtext() -> dict[str, str]:
    data: dict[str, str] = json.loads((HERE / "regtext.json").read_text())
    return data


def review_all(reviewer: Reviewer, gold: Sequence[GoldViolation]) -> dict[str, list[Finding]]:
    protocols = {row.protocol: row.domain for row in gold}
    return {
        protocol: reviewer.review(HERE / "protocols" / f"{protocol}.docx", domain)
        for protocol, domain in protocols.items()
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a reviewer on the planted-violation set.")
    parser.add_argument("--reviewer", choices=sorted(REVIEWERS), required=True)
    parser.add_argument("--split", type=Split, choices=list(Split), default=Split.all)
    parser.add_argument("--domain", type=Domain, choices=list(Domain))
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    args = parser.parse_args(argv)

    gold = load_gold(args.split, args.domain)
    findings = review_all(REVIEWERS[args.reviewer](), gold)
    report = score(gold, findings, load_regtext())

    print(
        f"reviewer {args.reviewer}  split {args.split}  protocols {len(findings)}  "
        f"planted {report.planted}  findings {report.findings}"
    )
    print(f"recall {_fmt(report.recall)}")
    print(f"precision {_fmt(report.precision)}")
    print(f"citation accuracy {_fmt(report.citation_accuracy)}")
    print(f"faithfulness {_fmt(report.faithfulness)}")
    for row in report.missed:
        print(f"MISSED {row.protocol} | {row.section} | {row.citation}")
    for fp in report.false_positives:
        print(f"FALSE POSITIVE {fp.protocol} | {fp.finding.doc_section_id}")

    if args.out:
        payload = {
            "reviewer": args.reviewer,
            "split": args.split,
            "domain": args.domain,
            **report.model_dump(mode="json"),
        }
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
