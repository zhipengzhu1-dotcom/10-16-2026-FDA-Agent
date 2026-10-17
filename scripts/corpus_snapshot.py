import argparse
import gzip
import hashlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from fda_copilot.corpus import store
from fda_copilot.domain.models import RegSection

ROOT = Path(__file__).parents[1]
SNAPSHOT = ROOT / "evals" / "retrieval" / "corpus.jsonl.gz"
MIGRATIONS = ROOT / "migrations"


def digest_path(snapshot: Path) -> Path:
    return snapshot.with_name(snapshot.name + ".sha256")


def dump(conn: psycopg.Connection, snapshot: Path) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT citation, effective_date, source, title, text, url FROM reg_sections"
            " ORDER BY citation, effective_date"
        ).fetchall()
    lines = "".join(RegSection.model_validate(row).model_dump_json() + "\n" for row in rows)
    data = gzip.compress(lines.encode(), mtime=0)
    snapshot.write_bytes(data)
    digest_path(snapshot).write_text(hashlib.sha256(data).hexdigest() + "\n")
    return len(rows)


def load(conn: psycopg.Connection, snapshot: Path) -> int:
    data = snapshot.read_bytes()
    expected = digest_path(snapshot).read_text().strip()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"{snapshot.name}: sha256 {actual} but the pin is {expected}")
    sections = [RegSection.model_validate_json(line) for line in gzip.decompress(data).splitlines()]
    with conn.transaction():
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text())
        store.upsert(conn, sections)
    return len(sections)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump or load the reg_sections snapshot.")
    parser.add_argument("action", choices=["dump", "load"])
    parser.add_argument("snapshot", type=Path, nargs="?", default=SNAPSHOT)
    args = parser.parse_args(argv)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        count = (dump if args.action == "dump" else load)(conn, args.snapshot)
    print(f"{args.action}: {count} rows, {args.snapshot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
