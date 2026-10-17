"""Usage: p04.py PDF_DIR. Reads DATABASE_URL. Exits 1 on any failure.

The expected text comes from poppler's pdftotext (pymupdf's plain text when poppler is missing),
and furniture is found without the chunker's rules: a line among the first or last few lines of
a page whose digit-normalized form repeats on enough pages, peeled from the page edges inward.
"""

import math
import os
import random
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import psycopg
import pymupdf

from fda_copilot.corpus import guidance

EDGE_LINES = 3
REPEAT_SHARE = 0.3
GOLD = {
    "ICH E6(R3) 3.11.4.3": "The sponsor should develop a monitoring plan that is tailored to the "
    "identified potential safety risks",
    "ICH E6(R3) 2.8.7": "and by the investigator or delegated investigator site staff who "
    "conducted the informed consent discussion",
}


def page_lines(path: Path) -> list[list[str]]:
    if shutil.which("pdftotext"):
        layout = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True
        ).stdout
        pages = layout.split("\f")[:-1]
    else:
        with pymupdf.open(path) as document:
            pages = [page.get_text("text") for page in document]
    return [
        [" ".join(line.split()) for line in page.splitlines() if line.strip()] for page in pages
    ]


def shape(line: str) -> str:
    return re.sub(r"\d+", "#", line)


def furniture(pages: list[list[str]]) -> set[str]:
    counts = Counter(
        repeated
        for lines in pages
        for repeated in {shape(line) for line in lines[:EDGE_LINES] + lines[-EDGE_LINES:]}
    )
    needed = max(3, math.ceil(len(pages) * REPEAT_SHARE))
    return {repeated for repeated, count in counts.items() if count >= needed}


def strip_edges(lines: list[str], removed: set[str]) -> list[str]:
    top = 0
    while top < min(EDGE_LINES, len(lines)) and shape(lines[top]) in removed:
        top += 1
    bottom = len(lines)
    while bottom > max(top, len(lines) - EDGE_LINES) and shape(lines[bottom - 1]) in removed:
        bottom -= 1
    return lines[top:bottom]


def characters(text: str) -> Counter[str]:
    return Counter(c for c in text if not c.isspace())


def starts_on_page(words: list[str], page: str, after: str) -> bool:
    text, at = page + after, page.find(words[0])
    for word in words[1:]:
        if at < 0:
            return False
        at = text.find(word, at + 1)
    return at >= 0


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
        pages = page_lines(pdf_dir / f"{source.key}.pdf")
        removed = furniture(pages)
        bodies = [strip_edges(lines, removed) for lines in pages]
        start = min(page_of(url) for _, _, url in rows)
        first = next(
            i
            for i, line in enumerate(bodies[start - 1])
            if line.startswith(source.first_body_heading)
        )
        bodies[start - 1] = bodies[start - 1][first:]
        expected = characters(" ".join(" ".join(lines) for lines in bodies[start - 1 :]))
        stored = characters(" ".join(text for _, text, _ in rows))
        dropped, extra = expected - stored, stored - expected
        print(
            f"COVERAGE {source.key}: {len(rows)} rows, {sum(expected.values())} body characters,"
            f" {sum(dropped.values())} dropped, {sum(extra.values())} not in the body;"
            f" removed as furniture: {sorted(removed)}"
        )
        if dropped:
            failures.append(f"{source.key} dropped characters {dict(dropped.most_common(20))}")
        if extra:
            failures.append(f"{source.key} stored characters not in the body {dict(extra)}")
        for citation, text, url in rows:
            words = text.split()[:12]
            page = page_of(url)
            on_page = "".join("".join(bodies[page - 1]).split())
            next_page = "".join("".join(bodies[page]).split()) if page < len(bodies) else ""
            ok = starts_on_page(words, on_page, next_page)
            checked.append((citation, " ".join(words), url, ok))

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
