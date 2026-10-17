import importlib
import sys
from collections import defaultdict
from pathlib import Path

from fda_copilot.domain.models import Citation, Domain, Finding, Severity

sys.path.insert(0, str(Path(__file__).parents[2] / "evals" / "review"))
score = importlib.import_module("score")


class GoldReviewer:
    def __init__(self, findings: dict[str, list[Finding]]) -> None:
        self.findings = findings

    def review(self, document: Path, domain: Domain) -> list[Finding]:
        return [f for f in self.findings.get(document.stem, []) if f.domain is domain]


def main() -> int:
    gold = score.load_gold()
    planted: dict[str, list[Finding]] = defaultdict(list)
    for row in gold:
        planted[row.protocol].append(
            Finding(
                doc_section_id=row.section,
                domain=row.domain,
                severity=Severity.major,
                issue=row.issue,
                citations=(Citation(citation=row.citation, quote=row.quote),),
                proposed_fix="Bring the section in line with the cited requirement.",
            )
        )

    findings = score.review_all(GoldReviewer(planted), gold)
    report = score.score(gold, findings, score.load_regtext())
    for name in ("recall", "precision", "citation_accuracy", "faithfulness"):
        print(f"{name} {getattr(report, name):.2f}")
    print(f"protocols {len(findings)} planted {report.planted} findings {report.findings}")
    perfect = (report.recall, report.precision, report.citation_accuracy, report.faithfulness)
    if perfect != (1.0, 1.0, 1.0, 1.0) or report.missed or report.false_positives:
        print("E2E FAIL: gold fed back as findings did not score 1.00")
        return 1
    print("E2E OK: gold fed back as findings scores 1.00 on every metric")
    return 0


if __name__ == "__main__":
    sys.exit(main())
