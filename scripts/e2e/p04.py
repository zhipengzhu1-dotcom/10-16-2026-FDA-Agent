"""Check stored guidance rows against the source PDFs, independently of the chunker.

Usage: p04.py PDF_DIR. Reads DATABASE_URL. Exits 1 on any failure.

The oracle reads each PDF with PyMuPDF's sorted plain-text mode, removes running headers,
footers, and page numbers (a line repeated in the top or bottom 12% of at least half the
pages), and starts at the source's first body heading. The stored rows must hold exactly
those words, and each row's first words must appear on the page its URL names.
"""

import math
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

import psycopg
import pymupdf

from fda_copilot.corpus import guidance

MARGIN = 0.12
GOLD = {
    "ICH E6(R3) 3.11.4.3": "The sponsor should develop a monitoring plan that is tailored to the "
    "identified potential safety risks",
    "ICH E6(R3) 2.8.7": "and by the investigator or delegated investigator site staff who "
    "conducted the informed consent discussion",
}


def normalize(text: str) -> str:
    return " ".join(text.split())


def shape(text: str) -> str:
    return re.sub(r"\d+", "#", normalize(text))


class PdfLine(NamedTuple):
    top: float
    bottom: float
    text: str


def page_lines(page: Any) -> list[PdfLine]:
    return [
        PdfLine(line["bbox"][1], line["bbox"][3], text)
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        if (text := normalize("".join(span["text"] for span in line["spans"])))
    ]


def in_margin(line: PdfLine, height: float) -> bool:
    return line.bottom < height * MARGIN or line.top > height * (1 - MARGIN)


def furniture(document: Any) -> set[str]:
    counts: Counter[str] = Counter()
    for page in document:
        height = page.rect.height
        counts.update({shape(ln.text) for ln in page_lines(page) if in_margin(ln, height)})
    repeated = max(2, math.ceil(document.page_count / 2))
    return {text for text, count in counts.items() if count >= repeated}


def body_words(document: Any, start: int, starts_at: str, removed: set[str]) -> Counter[str]:
    words: Counter[str] = Counter()
    for number in range(start, document.page_count + 1):
        page = document[number - 1]
        lines = [
            ln
            for ln in page_lines(page)
            if not (in_margin(ln, page.rect.height) and shape(ln.text) in removed)
        ]
        if number == start:
            top = min(ln.top for ln in lines if starts_at.startswith(ln.text.split()[0] + " "))
            lines = [ln for ln in lines if ln.top >= top - 1]
        words.update(word for ln in lines for word in ln.text.split())
    return words


def page_body(page: Any, furniture: set[str]) -> str:
    lines = page.get_text("text", sort=True).splitlines()
    return normalize(" ".join(line for line in lines if shape(line) not in furniture))


def page_of(url: str) -> int:
    return int(url.rsplit("#page=", 1)[1])


def main() -> int:
    pdf_dir = Path(sys.argv[1])
    failures: list[str] = []
    rows_by_source: dict[str, list[tuple[str, str, str]]] = {}
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for source in guidance.load_sources():
            rows_by_source[source.key] = conn.execute(
                "SELECT citation, text, url FROM reg_sections WHERE url LIKE %s AND source = %s",
                (f"{source.url}#page=%", source.source.value),
            ).fetchall()
        gold = dict(
            conn.execute(
                "SELECT citation, text FROM reg_sections WHERE citation = ANY(%s)", (list(GOLD),)
            ).fetchall()
        )

    for citation, quote in GOLD.items():
        text = gold.get(citation)
        print(f"GOLD {citation} :: {text}")
        if text is None or quote not in text:
            failures.append(f"gold {citation} missing or lacks {quote!r}")

    checked: list[tuple[str, str, str, bool]] = []
    for source in guidance.load_sources():
        rows = rows_by_source[source.key]
        with pymupdf.Document(pdf_dir / f"{source.key}.pdf") as document:
            removed = furniture(document)
            start = min(page_of(url) for _, _, url in rows)
            pages = {
                number: page_body(document[number - 1], removed)
                for number in range(start, document.page_count + 1)
            }
            body = body_words(document, start, source.starts_at, removed)
        stored: Counter[str] = Counter(word for _, text, _ in rows for word in text.split())
        dropped, invented = body - stored, stored - body
        print(
            f"COVERAGE {source.key}: {len(rows)} rows, {sum(body.values())} body words,"
            f" {sum(dropped.values())} dropped, {sum(invented.values())} not in the body;"
            f" removed as furniture: {sorted(removed)}"
        )
        if dropped:
            failures.append(f"{source.key} dropped body words {dict(dropped.most_common(20))}")
        if invented:
            failures.append(f"{source.key} stored words not in the body {dict(invented)}")
        for citation, text, url in rows:
            first_words = " ".join(text.split()[:12])
            nearby = f"{pages[page_of(url)]} {pages.get(page_of(url) + 1, '')}"
            checked.append((citation, first_words, url, first_words in nearby))

    misses = [citation for citation, _, _, ok in checked if not ok]
    print(f"FIRST LINES {len(checked) - len(misses)}/{len(checked)} rows match their source page")
    if misses:
        failures.append(f"first lines not on their source page: {misses}")
    seed = int(os.environ.get("P04_SEED", random.SystemRandom().randrange(10**6)))
    print(f"SEED {seed}")
    for citation, first_words, url, ok in random.Random(seed).sample(checked, 5):
        print(f"{'MATCH' if ok else 'MISMATCH'} {citation} :: {first_words} ({url})")

    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
