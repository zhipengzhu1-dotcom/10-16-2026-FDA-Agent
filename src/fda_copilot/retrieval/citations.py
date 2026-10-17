import re
from collections.abc import Mapping

import psycopg

LATEST_SECTIONS = """
SELECT DISTINCT ON (citation) citation, effective_date, source, title, text, url
FROM reg_sections
ORDER BY citation, effective_date DESC
"""

_TRAILING_PARAGRAPH = re.compile(r"\([^()]+\)$")
_PARAGRAPH = re.compile(r"\([^()]+\)")
_CHILD_SEPARATORS = ("(", ".", " ")
_OPENING_RUN = re.compile(
    r"(?:^|[.:;—]|(?<![)\s,])(?:,|,?\s(?:and|or)))\s*((?:\([^()\s]+\))++)(?!\s*(?:of|through)\b)"
)


def stored_texts(conn: psycopg.Connection) -> dict[str, str]:
    rows = conn.execute(f"SELECT citation, text FROM ({LATEST_SECTIONS}) latest").fetchall()
    return {citation: text for citation, text in rows}


def resolve(citation: str, texts: Mapping[str, str]) -> tuple[str, ...]:
    if citation in texts:
        return (citation,)
    ancestor = citation
    while match := _TRAILING_PARAGRAPH.search(ancestor):
        ancestor = ancestor[: match.start()]
        if ancestor in texts and _holds(texts[ancestor], ancestor, citation[len(ancestor) :]):
            return (ancestor,)
    return tuple(
        sorted(
            stored
            for stored in texts
            if stored.startswith(citation)
            and stored[len(citation) : len(citation) + 1] in _CHILD_SEPARATORS
        )
    )


def _opening_markers(text: str) -> list[str]:
    return [marker for run in _OPENING_RUN.finditer(text) for marker in _PARAGRAPH.findall(run[1])]


def _holds(text: str, holder: str, paragraphs: str) -> bool:
    opening = iter(_opening_markers(text))
    path = _PARAGRAPH.findall(holder)[-1:] + _PARAGRAPH.findall(paragraphs)
    return all(marker in opening for marker in path)
