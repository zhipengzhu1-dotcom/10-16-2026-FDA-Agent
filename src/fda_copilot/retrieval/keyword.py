import re
from collections.abc import Sequence

import psycopg
from psycopg.rows import dict_row

from fda_copilot.domain.models import RegSection
from fda_copilot.retrieval.citations import LATEST_SECTIONS
from fda_copilot.retrieval.retriever import RetrievalResult

_SEARCH = f"""
WITH latest AS ({LATEST_SECTIONS}),
scored AS (
    SELECT latest.*,
        ts_rank(to_tsvector('english', title || ' ' || text), to_tsquery('english', %(query)s), 1)
            AS score
    FROM latest
    WHERE to_tsvector('english', title || ' ' || text) @@ to_tsquery('english', %(query)s)
        AND (%(prefixes)s::text[] IS NULL OR latest.citation ^@ ANY(%(prefixes)s::text[]))
)
SELECT * FROM scored ORDER BY score DESC, citation LIMIT %(k)s
"""

_WORD = re.compile(r"[A-Za-z0-9]+")


class KeywordRetriever:
    def __init__(self, conn: psycopg.Connection, prefixes: Sequence[str] | None = None) -> None:
        self._conn = conn
        self._prefixes = None if prefixes is None else list(prefixes)

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        words = _WORD.findall(query)
        if not words:
            return []
        with self._conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                _SEARCH, {"query": " | ".join(words), "k": k, "prefixes": self._prefixes}
            ).fetchall()
        return [
            RetrievalResult(
                section=RegSection.model_validate({k: v for k, v in row.items() if k != "score"}),
                score=row["score"],
            )
            for row in rows
        ]
