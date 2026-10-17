from datetime import date
from enum import StrEnum
from typing import Annotated, NewType, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, NonNegativeInt, model_validator

from fda_copilot.domain.finding_status import FindingEvent, FindingStatus, transition

RegCitation = NewType("RegCitation", str)
DocSectionId = NewType("DocSectionId", str)
NonEmptyCitation = Annotated[RegCitation, Field(min_length=1)]


class Domain(StrEnum):
    IND = "IND"
    IDE = "IDE"
    GLP = "GLP"
    GCP = "GCP"


class RegSource(StrEnum):
    cfr = "cfr"
    ich = "ich"
    fda_guidance = "fda_guidance"


class Severity(StrEnum):
    critical = "critical"
    major = "major"
    minor = "minor"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RegSection(_Frozen):
    citation: NonEmptyCitation
    source: RegSource
    title: str
    text: str
    effective_date: date
    url: HttpUrl


class CharSpan(_Frozen):
    start: NonNegativeInt
    end: NonNegativeInt

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("span end precedes start")
        return self


class DocSection(_Frozen):
    id: DocSectionId
    heading: str
    text: str
    span: CharSpan


class Citation(_Frozen):
    citation: NonEmptyCitation
    quote: Annotated[str, Field(min_length=1)]


class Finding(_Frozen):
    doc_section_id: DocSectionId
    domain: Domain
    severity: Severity
    issue: str
    citations: Annotated[tuple[Citation, ...], Field(min_length=1)]
    proposed_fix: str
    status: FindingStatus = FindingStatus.proposed

    def apply(self, event: FindingEvent) -> Self:
        return self.model_copy(update={"status": transition(self.status, event)})
