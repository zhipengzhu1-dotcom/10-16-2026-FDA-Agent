from collections.abc import Callable, Sequence

import psycopg
from psycopg.rows import dict_row

from fda_copilot.corpus.embed import to_pgvector
from fda_copilot.domain.models import Domain, RegSection
from fda_copilot.retrieval.citations import LATEST_SECTIONS
from fda_copilot.retrieval.keyword import KeywordRetriever
from fda_copilot.retrieval.retriever import RetrievalResult

RRF_K = 60
DEPTH = 50
# The keyword leg cannot filter by domain in SQL, so it over-fetches and filters here.
KEYWORD_FETCH = 500

_HUMAN_SUBJECTS = frozenset({Domain.IND, Domain.IDE, Domain.GCP})

DOCUMENT_DOMAINS: dict[str, frozenset[Domain]] = {
    "21 CFR 50.": _HUMAN_SUBJECTS,
    "21 CFR 56.": _HUMAN_SUBJECTS,
    "21 CFR 58.": frozenset({Domain.GLP}),
    "21 CFR 312.": frozenset({Domain.IND}),
    "21 CFR 812.": frozenset({Domain.IDE}),
    "ICH E6(R3) ": frozenset({Domain.GCP}),
    "ICH M3(R2) ": frozenset({Domain.IND, Domain.GLP}),
    "FDA GLP Q&A (1981) ": frozenset({Domain.GLP}),
    "FDA IDE Decisions Guidance (2014) ": frozenset({Domain.IDE}),
    "FDA SR and NSR Device Studies Guidance (2006) ": frozenset({Domain.IDE}),
    "FDA IRB Continuing Review Guidance (2012) ": _HUMAN_SUBJECTS,
    "FDA Informed Consent Guidance (2023) ": _HUMAN_SUBJECTS,
    "FDA Investigator Responsibilities Guidance (2009) ": frozenset({Domain.IND, Domain.GCP}),
    "FDA Investigator Safety Reporting Guidance (2025) ": frozenset({Domain.IND, Domain.IDE}),
    "FDA Sponsor Safety Reporting Guidance (2025) ": frozenset({Domain.IND}),
}

_NEAREST = f"""
WITH latest AS ({LATEST_SECTIONS})
SELECT latest.*, 1 - (e.embedding <=> %(vector)s::vector) AS score
FROM latest JOIN section_embeddings e USING (citation, effective_date)
WHERE e.model = %(model)s
    AND (%(prefixes)s::text[] IS NULL OR latest.citation ^@ ANY(%(prefixes)s::text[]))
ORDER BY e.embedding <=> %(vector)s::vector, latest.citation
LIMIT %(depth)s
"""


def domains_of(citation: str) -> frozenset[Domain]:
    return next(
        (domains for prefix, domains in DOCUMENT_DOMAINS.items() if citation.startswith(prefix)),
        frozenset(),
    )


def fuse[C: str](rankings: Sequence[Sequence[C]], k: int = RRF_K) -> list[tuple[C, float]]:
    scores: dict[C, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class HybridRetriever:
    def __init__(
        self,
        conn: psycopg.Connection,
        model: str,
        embed_query: Callable[[str], Sequence[float]],
        domain: Domain | None = None,
    ) -> None:
        self._conn = conn
        self._model = model
        self._embed_query = embed_query
        self._domain = domain
        self._keyword = KeywordRetriever(conn)

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        keyword = [
            hit.section
            for hit in self._keyword.retrieve(query, KEYWORD_FETCH)
            if self._domain is None or self._domain in domains_of(hit.section.citation)
        ][:DEPTH]
        vector = self._nearest(self._embed_query(query))
        sections = {section.citation: section for section in keyword + vector}
        fused = fuse([[s.citation for s in keyword], [s.citation for s in vector]])
        return [RetrievalResult(sections[citation], score) for citation, score in fused[:k]]

    def _nearest(self, vector: Sequence[float]) -> list[RegSection]:
        prefixes = (
            None
            if self._domain is None
            else [prefix for prefix, domains in DOCUMENT_DOMAINS.items() if self._domain in domains]
        )
        with self._conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                _NEAREST,
                {
                    "vector": to_pgvector(vector),
                    "model": self._model,
                    "prefixes": prefixes,
                    "depth": DEPTH,
                },
            ).fetchall()
        return [
            RegSection.model_validate({k: v for k, v in row.items() if k != "score"})
            for row in rows
        ]
