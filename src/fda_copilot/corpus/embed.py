import hashlib
import json
import os
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, NamedTuple, Protocol, Self

import psycopg
from voyageai.client import Client

MODELS = ("voyage-4", "voyage-law-2")
DEFAULT_MODEL = "voyage-4"
InputType = Literal["document", "query"]

# voyage-law-2 accepts at most 120K tokens per request. Legal English runs about 4 characters a
# token, so 200K characters stays under that cap with room to spare.
MAX_BATCH_TEXTS = 128
MAX_BATCH_CHARS = 200_000

_SECTIONS = """
SELECT r.citation, r.effective_date, r.title, r.text, e.text_hash
FROM reg_sections r
LEFT JOIN section_embeddings e
    ON e.citation = r.citation AND e.effective_date = r.effective_date AND e.model = %s
ORDER BY r.citation, r.effective_date
"""

_UPSERT = """
INSERT INTO section_embeddings (citation, effective_date, model, text_hash, embedding)
SELECT c, d, %s, h, v FROM unnest(%s::text[], %s::date[], %s::text[], %s::text[]::vector[])
    AS rows(c, d, h, v)
ON CONFLICT (citation, effective_date, model) DO UPDATE
SET text_hash = EXCLUDED.text_hash, embedding = EXCLUDED.embedding
"""


class MissingApiKey(RuntimeError):
    pass


@dataclass(frozen=True)
class Embedded:
    vectors: list[list[float]]
    tokens: int


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    def embed(self, texts: Sequence[str], input_type: InputType) -> Embedded: ...


class VoyageEmbedder:
    def __init__(self, model: str, client: Client) -> None:
        self._model = model
        self._client = client

    @classmethod
    def from_env(cls, model: str) -> Self:
        key = os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise MissingApiKey(
                "VOYAGE_API_KEY is not set."
                f" Add it to .env or the environment to embed with {model}."
            )
        return cls(model, Client(api_key=key, max_retries=5))

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str], input_type: InputType) -> Embedded:
        vectors: list[list[float]] = []
        tokens = 0
        for batch in batches(texts, len):
            response = self._client.embed(
                list(batch), model=self._model, input_type=input_type, truncation=False
            )
            vectors.extend([float(x) for x in vector] for vector in response.embeddings)
            tokens += response.total_tokens
        return Embedded(vectors, tokens)


@dataclass(frozen=True)
class EmbedRun:
    embedded: int
    unchanged: int
    tokens: int


class Pending(NamedTuple):
    citation: str
    effective_date: date
    text_hash: str
    source: str


def batches[T](
    items: Sequence[T],
    chars: Callable[[T], int],
    max_texts: int = MAX_BATCH_TEXTS,
    max_chars: int = MAX_BATCH_CHARS,
) -> Iterator[Sequence[T]]:
    start = total = 0
    for end, item in enumerate(items):
        size = chars(item)
        if end > start and (end - start == max_texts or total + size > max_chars):
            yield items[start:end]
            start, total = end, 0
        total += size
    if start < len(items):
        yield items[start:]


def text_hash(embedded_text: str) -> str:
    return hashlib.sha256(embedded_text.encode()).hexdigest()


def to_pgvector(vector: Sequence[float]) -> str:
    return json.dumps(list(vector), separators=(",", ":"))


def pending(conn: psycopg.Connection, model: str) -> tuple[list[Pending], int]:
    rows = conn.execute(_SECTIONS, (model,)).fetchall()
    current = [
        (Pending(citation, effective_date, text_hash(source), source), stored_hash)
        for citation, effective_date, title, text, stored_hash in rows
        for source in [f"{title}\n\n{text}"]
    ]
    return [row for row, stored_hash in current if row.text_hash != stored_hash], len(rows)


def embed_corpus(conn: psycopg.Connection, embedder: Embedder) -> EmbedRun:
    stale, total = pending(conn, embedder.model)
    tokens = 0
    for batch in batches(stale, lambda row: len(row.source)):
        embedded = embedder.embed([row.source for row in batch], "document")
        tokens += embedded.tokens
        with conn.transaction():
            conn.execute(
                _UPSERT,
                (
                    embedder.model,
                    [row.citation for row in batch],
                    [row.effective_date for row in batch],
                    [row.text_hash for row in batch],
                    [to_pgvector(vector) for vector in embedded.vectors],
                ),
            )
    return EmbedRun(embedded=len(stale), unchanged=total - len(stale), tokens=tokens)


class QueryCache:
    def __init__(
        self, conn: psycopg.Connection, model: str, embedder: Callable[[], Embedder]
    ) -> None:
        self._conn = conn
        self._model = model
        self._embedder = embedder

    def __call__(self, query: str) -> list[float]:
        row = self._conn.execute(
            "SELECT embedding::text FROM query_embeddings WHERE model = %s AND query = %s",
            (self._model, query),
        ).fetchone()
        if row is None:
            [vector] = self._embedder().embed([query], "query").vectors
            row = self._conn.execute(
                "INSERT INTO query_embeddings (model, query, embedding)"
                " VALUES (%s, %s, %s::vector) RETURNING embedding::text",
                (self._model, query, to_pgvector(vector)),
            ).fetchone()
            assert row is not None
        stored: list[float] = json.loads(row[0])
        return stored
