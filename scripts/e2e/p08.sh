#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

url="https://cdn.clinicaltrials.gov/large-docs/37/NCT02293837/Prot_000.pdf"
sha256="aaf4e3137249d7cf538d175dc2bfb07056c7d1cbfd2e9a9329010806ca4de883"
download_dir="${P08_PROTOCOL_DIR:-/tmp/p08-protocol}"
pdf="${download_dir}/NCT02293837_Prot_000.pdf"
sections=$(mktemp)
trap 'rm -f "$sections"' EXIT

mkdir -p "$download_dir"
[[ -f "$pdf" ]] || curl -sSfL -o "$pdf" "$url"
echo "PROTOCOL=${url}"
echo "${sha256}  ${pdf}" | shasum -a 256 -c -

uv run fda-copilot parse "$pdf" | tee "$sections"

uv run python -I - "$pdf" "$sections" <<'PY'
import sys
from itertools import pairwise
from pathlib import Path

import pymupdf

from fda_copilot.documents.parse import parse_document

pdf = Path(sys.argv[1])
printed = [
    tuple(int(n) for n in line.split("\t", 1)[0].split("-"))
    for line in Path(sys.argv[2]).read_text().splitlines()
]
with pymupdf.open(pdf) as document:
    pages = document.page_count
parsed = parse_document(pdf.name, pdf.read_bytes())
spans = [(section.span.start, section.span.end) for section in parsed.sections]
print(f"PAGES={pages} SECTIONS={len(spans)} TEXT_CHARS={len(parsed.text)}")
checks = {
    "at least 10 sections": len(spans) >= 10,
    "cli spans equal parse_document spans": printed == spans,
    "first span starts at 0": spans[0][0] == 0,
    "last span ends at the text end": spans[-1][1] == len(parsed.text),
    "no gap or overlap between spans": all(a[1] == b[0] for a, b in pairwise(spans)),
    "each section text equals its slice": all(
        section.text == parsed.text[section.span.start : section.span.end]
        for section in parsed.sections
    ),
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
if not all(checks.values()):
    sys.exit("E2E FAIL")
print("E2E OK")
PY
