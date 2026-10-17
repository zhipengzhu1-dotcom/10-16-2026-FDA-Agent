from collections.abc import Sequence

import psycopg

from fda_copilot.domain.models import RegSection

_UPSERT = """
INSERT INTO reg_sections (citation, effective_date, source, title, text, url)
SELECT * FROM unnest(%s::text[], %s::date[], %s::text[], %s::text[], %s::text[], %s::text[])
ON CONFLICT (citation, effective_date) DO UPDATE
SET source = EXCLUDED.source, title = EXCLUDED.title, text = EXCLUDED.text, url = EXCLUDED.url
WHERE (reg_sections.source, reg_sections.title, reg_sections.text, reg_sections.url)
    IS DISTINCT FROM (EXCLUDED.source, EXCLUDED.title, EXCLUDED.text, EXCLUDED.url)
"""


def upsert(conn: psycopg.Connection, sections: Sequence[RegSection]) -> int:
    columns = (
        [s.citation for s in sections],
        [s.effective_date for s in sections],
        [s.source.value for s in sections],
        [s.title for s in sections],
        [s.text for s in sections],
        [str(s.url) for s in sections],
    )
    with conn.cursor() as cur:
        cur.execute(_UPSERT, columns)
        return cur.rowcount
