import hashlib
import math
import re
from collections.abc import Sequence

from fda_copilot.corpus.embed import Embedded, InputType

DIMENSIONS = 64


class FakeEmbedder:
    model = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], InputType]] = []

    def embed(self, texts: Sequence[str], input_type: InputType) -> Embedded:
        self.calls.append((list(texts), input_type))
        vectors = [self._vector(text) for text in texts]
        return Embedded(vectors, sum(len(text.split()) for text in texts))

    @staticmethod
    def _vector(text: str) -> list[float]:
        counts = [0.0] * DIMENSIONS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            counts[hashlib.sha256(word.encode()).digest()[0] % DIMENSIONS] += 1
        norm = math.sqrt(sum(c * c for c in counts)) or 1.0
        return [c / norm for c in counts]
