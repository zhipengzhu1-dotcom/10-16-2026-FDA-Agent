import sys

from fda_copilot.domain.finding_status import (
    FindingEvent,
    FindingStatus,
    IllegalTransition,
    transition,
)
from fda_copilot.domain.models import Finding


def advance(finding: Finding, event: FindingEvent) -> Finding:
    moved = finding.model_copy(update={"status": transition(finding.status, event)})
    print(f"ALLOWED {finding.status.value} --{event}--> {moved.status.value}")
    return moved


def main() -> int:
    finding = Finding.model_validate(
        {
            "doc_section_id": "sec-4.2",
            "domain": "IND",
            "severity": "major",
            "issue": "No 15-day safety report timeline.",
            "citations": [{"citation": "21 CFR 312.32(c)(1)", "quote": "within 15 calendar days"}],
            "proposed_fix": "State the 15-day IND safety report deadline.",
        }
    )
    print(f"BUILT finding status={finding.status.value} citations={len(finding.citations)}")

    finding = advance(finding, FindingEvent.verify)
    finding = advance(finding, FindingEvent.accept)

    blocked = 0
    for event in FindingEvent:
        try:
            transition(finding.status, event)
        except IllegalTransition as err:
            print(f"IllegalTransition {err}")
            blocked += 1
    if blocked != len(FindingEvent) or finding.status is not FindingStatus.accepted:
        print("E2E FAIL: accepted is not terminal")
        return 1
    print("E2E OK: accepted cannot move back to proposed or anywhere else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
