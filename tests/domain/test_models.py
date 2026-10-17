from datetime import date

import pytest
from pydantic import ValidationError

from fda_copilot.domain.finding_status import FindingStatus
from fda_copilot.domain.models import (
    Citation,
    DocSection,
    Domain,
    Finding,
    RegSection,
    RegSource,
    Severity,
)

FINDING = {
    "doc_section_id": "sec-4.2",
    "domain": "IND",
    "severity": "major",
    "issue": "No 15-day safety report timeline.",
    "citations": [{"citation": "21 CFR 312.32(c)(1)", "quote": "within 15 calendar days"}],
    "proposed_fix": "State the 15-day IND safety report deadline.",
}


def test_finding_parses_and_starts_proposed() -> None:
    finding = Finding.model_validate(FINDING)

    assert finding.domain is Domain.IND
    assert finding.severity is Severity.major
    assert finding.status is FindingStatus.proposed
    assert finding.citations == (
        Citation(citation="21 CFR 312.32(c)(1)", quote="within 15 calendar days"),
    )


def test_finding_rejects_empty_citations() -> None:
    with pytest.raises(ValidationError, match="citations\n  Tuple should have at least 1 item"):
        Finding.model_validate({**FINDING, "citations": []})


def test_citation_rejects_empty_quote() -> None:
    with pytest.raises(ValidationError, match="quote"):
        Citation.model_validate({"citation": "21 CFR 312.32(c)(1)", "quote": ""})


def test_domain_is_the_four_regulatory_areas() -> None:
    assert [d.value for d in Domain] == ["IND", "IDE", "GLP", "GCP"]


def test_reg_section_parses_source_date_and_url() -> None:
    section = RegSection.model_validate(
        {
            "citation": "21 CFR 312.32(c)(1)",
            "source": "cfr",
            "title": "IND safety reporting",
            "text": "The sponsor must notify FDA ... within 15 calendar days.",
            "effective_date": "2011-03-28",
            "url": "https://www.ecfr.gov/current/title-21/section-312.32",
        }
    )

    assert section.source is RegSource.cfr
    assert section.effective_date == date(2011, 3, 28)
    assert str(section.url) == "https://www.ecfr.gov/current/title-21/section-312.32"


def test_doc_section_rejects_reversed_span() -> None:
    with pytest.raises(ValidationError, match="span end precedes start"):
        DocSection.model_validate(
            {"id": "sec-1", "heading": "Intro", "text": "x", "span": {"start": 10, "end": 2}}
        )
