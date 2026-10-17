import argparse
import base64
import gzip
import json
import os
import struct
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import psycopg
from corpus_snapshot import MIGRATIONS, read_pinned, write_pinned
from pydantic import BaseModel, ConfigDict

from fda_copilot.corpus.embed import DEFAULT_MODEL, MODELS, pending, to_pgvector

SNAPSHOTS = Path(__file__).parents[1] / "evals" / "retrieval"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SectionVector(_Frozen):
    citation: str
    effective_date: date
    text_hash: str
    vector: str


class QueryVector(_Frozen):
    query: str
    vector: str


class Snapshot(_Frozen):
    model: str
    sections: tuple[SectionVector, ...]
    queries: tuple[QueryVector, ...]


class StaleSnapshot(Exception):
    pass


class CorpusNotLoaded(Exception):
    pass


def snapshot_path(model: str) -> Path:
    return SNAPSHOTS / f"embeddings-{model}.json.gz"


def pack(pgvector: str) -> str:
    values = json.loads(pgvector)
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode()


def unpack(packed: str) -> str:
    data = base64.b64decode(packed)
    return to_pgvector(struct.unpack(f"<{len(data) // 4}f", data))


def dump(conn: psycopg.Connection, model: str, snapshot: Path) -> Snapshot:
    sections = conn.execute(
        "SELECT citation, effective_date, text_hash, embedding::text FROM section_embeddings"
        " WHERE model = %s ORDER BY citation, effective_date",
        (model,),
    ).fetchall()
    queries = conn.execute(
        "SELECT query, embedding::text FROM query_embeddings WHERE model = %s ORDER BY query",
        (model,),
    ).fetchall()
    result = Snapshot(
        model=model,
        sections=tuple(
            SectionVector(citation=c, effective_date=d, text_hash=h, vector=pack(v))
            for c, d, h, v in sections
        ),
        queries=tuple(QueryVector(query=q, vector=pack(v)) for q, v in queries),
    )
    write_pinned(snapshot, gzip.compress(result.model_dump_json().encode(), mtime=0))
    return result


def load(conn: psycopg.Connection, model: str, snapshot: Path) -> Snapshot:
    result = Snapshot.model_validate_json(gzip.decompress(read_pinned(snapshot)))
    if result.model != model:
        raise ValueError(f"{snapshot.name} holds {result.model} vectors, not {model}")
    with conn.transaction():
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text())
        orphans = conn.execute(
            "SELECT c FROM unnest(%s::text[], %s::date[]) AS rows(c, d)"
            " WHERE (c, d) NOT IN (SELECT citation, effective_date FROM reg_sections)"
            " ORDER BY c",
            ([s.citation for s in result.sections], [s.effective_date for s in result.sections]),
        ).fetchall()
        if orphans:
            raise CorpusNotLoaded(
                f"{snapshot.name}: {len(orphans)} vectors have no reg_sections row,"
                f" first {orphans[0][0]}. Run `scripts/corpus_snapshot.py load` first."
            )
        conn.execute("DELETE FROM section_embeddings WHERE model = %s", (model,))
        conn.execute("DELETE FROM query_embeddings WHERE model = %s", (model,))
        conn.execute(
            "INSERT INTO section_embeddings (citation, effective_date, model, text_hash, embedding)"
            " SELECT c, d, %s, h, v FROM unnest(%s::text[], %s::date[], %s::text[],"
            " %s::text[]::vector[]) AS rows(c, d, h, v)",
            (
                model,
                [s.citation for s in result.sections],
                [s.effective_date for s in result.sections],
                [s.text_hash for s in result.sections],
                [unpack(s.vector) for s in result.sections],
            ),
        )
        conn.execute(
            "INSERT INTO query_embeddings (model, query, embedding)"
            " SELECT %s, q, v FROM unnest(%s::text[], %s::text[]::vector[]) AS rows(q, v)",
            (model, [q.query for q in result.queries], [unpack(q.vector) for q in result.queries]),
        )
        stale, _ = pending(conn, model)
        if stale:
            raise StaleSnapshot(
                f"{snapshot.name}: {len(stale)} reg_sections rows have no {model} vector for"
                f" their current text, first {stale[0].citation}. Re-embed and dump again."
            )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump or load the pinned embedding snapshot.")
    parser.add_argument("action", choices=["dump", "load"])
    parser.add_argument("--model", choices=MODELS, default=DEFAULT_MODEL)
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args(argv)
    snapshot = args.snapshot or snapshot_path(args.model)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        result = (dump if args.action == "dump" else load)(conn, args.model, snapshot)
    print(
        f"{args.action}: {len(result.sections)} section and {len(result.queries)} query"
        f" vectors for {args.model}, {snapshot}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
