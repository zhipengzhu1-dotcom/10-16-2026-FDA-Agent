from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from fda_copilot.domain.models import RegSection


@dataclass(frozen=True)
class RetrievalResult:
    section: RegSection
    score: float


class Retriever(Protocol):
    def retrieve(self, query: str, k: int) -> Sequence[RetrievalResult]: ...
