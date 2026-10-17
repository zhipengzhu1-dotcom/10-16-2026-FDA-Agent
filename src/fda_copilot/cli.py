import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from fda_copilot.corpus import ecfr, guidance, store
from fda_copilot.documents.parse import UnsupportedDocument, parse_document


def main(argv: Sequence[str] | None = None) -> int | None:
    parser = argparse.ArgumentParser(prog="fda-copilot")
    commands = parser.add_subparsers(required=True)
    ingest = commands.add_parser("ingest").add_subparsers(required=True)
    ingest.add_parser("cfr", help="ingest 21 CFR Parts 50, 56, 58, 312, and 812").set_defaults(
        run=ingest_cfr
    )
    ingest_guidance_parser = ingest.add_parser(
        "guidance", help="ingest the ICH guidelines and FDA guidance PDFs in guidance_sources.yaml"
    )
    ingest_guidance_parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "fda-copilot"
        / "guidance",
        help="where downloaded PDFs are kept; they are untrusted input checked by SHA-256",
    )
    ingest_guidance_parser.set_defaults(run=ingest_guidance)
    _add_parse_command(commands)
    args = parser.parse_args(argv)
    exit_code: int | None = args.run(args)
    return exit_code


def ingest_cfr(args: argparse.Namespace) -> None:
    on = ecfr.latest_date()
    total_rows = total_changed = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for part in ecfr.PARTS:
            sections = ecfr.parse_part(
                ecfr.fetch_part(part, on), ecfr.fetch_effective_dates(part, on)
            )
            changed = store.upsert(conn, sections)
            conn.commit()
            total_rows += len(sections)
            total_changed += changed
            print(f"part {part}: {len(sections)} rows, {changed} changed", flush=True)
    print(f"total: {total_rows} rows, {total_changed} changed (eCFR as of {on})")


def ingest_guidance(args: argparse.Namespace) -> None:
    parsed = [
        (source, guidance.parse(source, guidance.fetch(source, args.pdf_dir)))
        for source in guidance.load_sources()
    ]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.transaction():
        changes = [(source, sections, store.upsert(conn, sections)) for source, sections in parsed]
    for source, sections, changed in changes:
        print(f"{source.citation}: {len(sections)} rows, {changed} changed")
    rows = sum(len(sections) for _, sections, _ in changes)
    print(f"total: {rows} rows, {sum(changed for _, _, changed in changes)} changed")


def _add_parse_command(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    command = commands.add_parser("parse", help="split a .docx or .pdf into sections")
    command.add_argument("file", type=Path)
    command.set_defaults(run=_parse)


def _parse(args: argparse.Namespace) -> int:
    path: Path = args.file
    try:
        document = parse_document(path.name, path.read_bytes())
    except (OSError, UnsupportedDocument) as error:
        print(f"fda-copilot parse: {error}", file=sys.stderr)
        return 1
    for section in document.sections:
        print(f"{section.span.start}-{section.span.end}\t{section.heading}")
    return 0
