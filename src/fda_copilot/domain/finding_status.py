from collections.abc import Mapping
from enum import Enum, StrEnum
from typing import Final


class FindingStatus(Enum):
    proposed = "proposed"
    verified = "verified"
    discarded = "discarded"
    accepted = "accepted"
    rejected = "rejected"


class FindingEvent(StrEnum):
    verify = "verify"
    discard = "discard"
    accept = "accept"
    reject = "reject"


class IllegalTransition(Exception):
    def __init__(self, status: FindingStatus, event: str) -> None:
        super().__init__(f"no transition from {status.value} on '{event}'")


TRANSITIONS: Final[Mapping[tuple[FindingStatus, FindingEvent], FindingStatus]] = {
    (FindingStatus.proposed, FindingEvent.verify): FindingStatus.verified,
    (FindingStatus.proposed, FindingEvent.discard): FindingStatus.discarded,
    (FindingStatus.verified, FindingEvent.accept): FindingStatus.accepted,
    (FindingStatus.verified, FindingEvent.reject): FindingStatus.rejected,
}


def transition(status: FindingStatus, event: FindingEvent) -> FindingStatus:
    try:
        return TRANSITIONS[(status, event)]
    except KeyError:
        raise IllegalTransition(status, event) from None
