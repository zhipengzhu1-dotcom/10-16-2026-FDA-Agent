"""Score a reviewer's findings against the planted-violation gold set.

A reviewer returns one Review per protocol: its findings, plus the map from each
doc_section_id it uses to that section's heading text.

Matching rule. A finding matches a gold row when all three hold:
  1. the finding was returned for the gold row's protocol,
  2. the finding's domain equals the row's domain, and
  3. the heading its doc_section_id maps to equals the row's section heading, ignoring
     case and runs of whitespace. An id missing from the map matches nothing.
Each gold row matches at most one finding. The first finding in reviewer order wins, and
later findings on the same row are false positives. The citation is not part of the match.

Metrics, rounded to four places:
  recall             matched gold rows / gold rows
  precision          matched findings / findings
  citation accuracy  matched findings whose primary (first) citation is the row's
                     citation / findings
  faithfulness       findings whose every quote has at least 5 words and occurs in the
                     stored text of its own citation (whitespace-normalized) / findings
Precision, citation accuracy, and faithfulness are None when there are no findings.

Regulation text comes from a lookup, citation -> text, or None when the store has no such
citation. A quote under an unknown citation is not faithful, and the report counts those
citations as unknown_citations and lists them per finding. The default lookup reads
regtext.json, which check_citations.py fetched for the gold citations only. P09 must pass
a lookup over the stored RegSection rows instead, so that faithfulness checks the same
text the verifier and the user see.
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from fda_copilot.domain.models import DocSectionId, Domain, Finding, RegCitation

HERE = Path(__file__).parent
MIN_QUOTE_WORDS = 5

Lookup = Callable[[str], str | None]


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


class Review(_Frozen):
    headings: dict[DocSectionId, str]
    findings: tuple[Finding, ...]


class ScoredFinding(_Frozen):
    protocol: str
    finding: Finding
    heading: str | None
    gold: GoldViolation | None
    faithful: bool
    unknown_citations: tuple[RegCitation, ...]


class Report(_Frozen):
    planted: int
    findings: int
    recall: float
    precision: float | None
    citation_accuracy: float | None
    faithfulness: float | None
    unknown_citations: int
    missed: tuple[GoldViolation, ...]
    scored: tuple[ScoredFinding, ...]

    @property
    def false_positives(self) -> tuple[ScoredFinding, ...]:
        return tuple(s for s in self.scored if s.gold is None)


class Reviewer(Protocol):
    def review(self, document: Path, domain: Domain) -> Review: ...


class NullReviewer:
    def review(self, document: Path, domain: Domain) -> Review:
        return Review(headings={}, findings=())


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


def load_regtext() -> dict[str, str]:
    data: dict[str, str] = json.loads((HERE / "regtext.json").read_text())
    return data


@cache
def _regtext_by_citation() -> dict[str, str]:
    return {_squash(citation): text for citation, text in load_regtext().items()}


def regtext(citation: str) -> str | None:
    return _regtext_by_citation().get(_squash(citation))


def score(
    gold: Sequence[GoldViolation],
    reviews: Mapping[str, Review],
    lookup: Lookup = regtext,
) -> Report:
    open_rows = {_section_key(row.protocol, row.section): row for row in gold}
    if len(open_rows) != len(gold):
        raise ValueError("two gold rows share a protocol section")

    scored: list[ScoredFinding] = []
    for protocol, review in reviews.items():
        for finding in review.findings:
            heading = review.headings.get(finding.doc_section_id)
            row = None
            if heading is not None:
                key = _section_key(protocol, heading)
                if key in open_rows and open_rows[key].domain is finding.domain:
                    row = open_rows.pop(key)
            texts = [(c, lookup(c.citation)) for c in finding.citations]
            scored.append(
                ScoredFinding(
                    protocol=protocol,
                    finding=finding,
                    heading=heading,
                    gold=row,
                    faithful=all(
                        text is not None
                        and len(c.quote.split()) >= MIN_QUOTE_WORDS
                        and _squash(c.quote) in _squash(text)
                        for c, text in texts
                    ),
                    unknown_citations=tuple(c.citation for c, text in texts if text is None),
                )
            )

    hits = [(s.finding, s.gold) for s in scored if s.gold is not None]
    cited = sum(
        _squash(finding.citations[0].citation) == _squash(row.citation) for finding, row in hits
    )
    remaining = set(open_rows.values())
    return Report(
        planted=len(gold),
        findings=len(scored),
        recall=_ratio(len(hits), len(gold)) or 0.0,
        precision=_ratio(len(hits), len(scored)),
        citation_accuracy=_ratio(cited, len(scored)),
        faithfulness=_ratio(sum(s.faithful for s in scored), len(scored)),
        unknown_citations=sum(len(s.unknown_citations) for s in scored),
        missed=tuple(row for row in gold if row in remaining),
        scored=tuple(scored),
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


def review_all(reviewer: Reviewer, gold: Sequence[GoldViolation]) -> dict[str, Review]:
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
    reviews = review_all(REVIEWERS[args.reviewer](), gold)
    report = score(gold, reviews)

    print(
        f"reviewer {args.reviewer}  split {args.split}  protocols {len(reviews)}  "
        f"planted {report.planted}  findings {report.findings}"
    )
    print(f"recall {_fmt(report.recall)}")
    print(f"precision {_fmt(report.precision)}")
    print(f"citation accuracy {_fmt(report.citation_accuracy)}")
    print(f"faithfulness {_fmt(report.faithfulness)}")
    print(f"unknown citations {report.unknown_citations}")
    for row in report.missed:
        print(f"MISSED {row.protocol} | {row.section} | {row.citation}")
    for fp in report.false_positives:
        print(f"FALSE POSITIVE {fp.protocol} | {fp.finding.doc_section_id} | {fp.heading}")
    for s in report.scored:
        for citation in s.unknown_citations:
            print(f"UNKNOWN CITATION {s.protocol} | {s.finding.doc_section_id} | {citation}")

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
