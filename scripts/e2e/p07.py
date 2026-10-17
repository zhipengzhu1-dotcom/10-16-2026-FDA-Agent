import importlib
import sys
from collections import defaultdict
from pathlib import Path

from fda_copilot.domain.models import Citation, DocSectionId, Domain, Finding, Severity

sys.path.insert(0, str(Path(__file__).parents[2] / "evals" / "review"))
score = importlib.import_module("score")


class GoldReviewer:
    def __init__(self, reviews: dict[str, object]) -> None:
        self.reviews = reviews

    def review(self, document: Path, domain: Domain) -> object:
        return self.reviews[document.stem]


def main() -> int:
    gold = score.load_gold()
    headings: dict[str, dict[DocSectionId, str]] = defaultdict(dict)
    planted: dict[str, list[Finding]] = defaultdict(list)
    for row in gold:
        section_id = DocSectionId(f"sec-{len(headings[row.protocol]) + 1}")
        headings[row.protocol][section_id] = row.section
        planted[row.protocol].append(
            Finding(
                doc_section_id=section_id,
                domain=row.domain,
                severity=Severity.major,
                issue=row.issue,
                citations=(Citation(citation=row.citation, quote=row.quote),),
                proposed_fix="Bring the section in line with the cited requirement.",
            )
        )
    reviews = {p: score.Review(headings=headings[p], findings=planted[p]) for p in planted}

    report = score.score(gold, score.review_all(GoldReviewer(reviews), gold))
    for name in ("recall", "precision", "citation_accuracy", "faithfulness"):
        print(f"{name} {getattr(report, name):.2f}")
    print(f"protocols {len(reviews)} planted {report.planted} findings {report.findings}")
    print(f"unknown_citations {report.unknown_citations}")
    perfect = (report.recall, report.precision, report.citation_accuracy, report.faithfulness)
    if perfect != (1.0, 1.0, 1.0, 1.0) or report.missed or report.false_positives:
        print("E2E FAIL: gold fed back as findings did not score 1.00")
        return 1
    print("E2E OK: gold fed back under sec-<n> section ids scores 1.00 on every metric")
    return 0


if __name__ == "__main__":
    sys.exit(main())
