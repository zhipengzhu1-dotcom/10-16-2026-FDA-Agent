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


def stored_texts(conn: psycopg.Connection) -> dict[str, str]:
    rows = conn.execute(f"SELECT citation, text FROM ({LATEST_SECTIONS}) latest").fetchall()
    return {citation: text for citation, text in rows}


def resolve(citation: str, texts: Mapping[str, str]) -> tuple[str, ...]:
    if citation in texts:
        return (citation,)
    ancestor = citation
    while match := _TRAILING_PARAGRAPH.search(ancestor):
        ancestor = ancestor[: match.start()]
        if ancestor in texts and _holds(texts[ancestor], citation[len(ancestor) :]):
            return (ancestor,)
    return tuple(
        sorted(
            stored
            for stored in texts
            if stored.startswith(citation)
            and stored[len(citation) : len(citation) + 1] in _CHILD_SEPARATORS
        )
    )


def _marker(marker: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![\w)])(?<!paragraph )(?<!paragraphs ){re.escape(marker)}(?!\s*(?:of this|through)\b)"
    )


def _holds(text: str, paragraphs: str) -> bool:
    position = 0
    for marker in _PARAGRAPH.findall(paragraphs):
        found = _marker(marker).search(text, position)
        if found is None:
            return False
        position = found.end()
    return True
