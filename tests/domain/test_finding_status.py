from itertools import product

import pytest

from fda_copilot.domain.finding_status import (
    FindingEvent,
    FindingStatus,
    IllegalTransition,
    transition,
)

ALLOWED = {
    (FindingStatus.proposed, FindingEvent.verify): FindingStatus.verified,
    (FindingStatus.proposed, FindingEvent.discard): FindingStatus.discarded,
    (FindingStatus.verified, FindingEvent.accept): FindingStatus.accepted,
    (FindingStatus.verified, FindingEvent.reject): FindingStatus.rejected,
}


@pytest.mark.parametrize(("status", "event", "expected"), [(*k, v) for k, v in ALLOWED.items()])
def test_allowed_move(status: FindingStatus, event: FindingEvent, expected: FindingStatus) -> None:
    assert transition(status, event) is expected


def test_event_accepts_plain_string() -> None:
    assert transition(FindingStatus.proposed, "verify") is FindingStatus.verified


def test_proposed_cannot_be_accepted() -> None:
    with pytest.raises(IllegalTransition, match="no transition from proposed on 'accept'"):
        transition(FindingStatus.proposed, FindingEvent.accept)


@pytest.mark.parametrize(
    ("status", "event"),
    [pair for pair in product(FindingStatus, FindingEvent) if pair not in ALLOWED],
)
def test_every_other_move_is_illegal(status: FindingStatus, event: FindingEvent) -> None:
    with pytest.raises(IllegalTransition):
        transition(status, event)


def test_unknown_event_is_illegal() -> None:
    with pytest.raises(IllegalTransition):
        transition(FindingStatus.accepted, "propose")
