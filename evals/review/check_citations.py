"""Check every gold citation against the live eCFR and the ICH E6(R3) guideline.

Writes regtext.json (citation -> regulation text) for the scorer's faithfulness
metric, and check_citations.log as the audit trail. Needs network and pdftotext.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

HERE = Path(__file__).parent
ECFR = "https://www.ecfr.gov/api/versioner/v1"
ICH_PDF = (
    "https://database.ich.org/sites/default/files/ICH_E6%28R3%29_Step4_FinalGuideline_2025_0106.pdf"
)
CFR_RE = re.compile(r"^21 CFR (\d+)\.(\d+)((?:\([0-9A-Za-z]+\))+)$")
ICH_RE = re.compile(r"^ICH E6\(R3\) (\d+(?:\.\d+)*)$")
DESIGNATOR = re.compile(r"\((<I>)?([0-9A-Za-z]+)(</I>)?\)")
DESIGNATORS = r"((?:\((?:<I>)?[0-9A-Za-z]+(?:</I>)?\))+)"
LEAD = re.compile(rf"^\s*{DESIGNATORS}(?:\s*<I>[^<]*</I>\s*[—-]?\s*{DESIGNATORS})?")
ROMAN = re.compile(r"^(?=[ivxl]+$)l?x{0,3}(ix|iv|v?i{0,3})$")
ICH_HEADING = re.compile(r"^(\d+(?:\.\d+)+)\s+[A-Z]")

Path_ = tuple[str, ...]


def _get(client: httpx.Client, url: str) -> bytes:
    for attempt in range(20):
        response = client.get(url)
        if response.status_code == 200:
            return response.content
        time.sleep(1 + attempt)
    raise RuntimeError(f"{url} kept failing, last status {response.status_code}")


def _plain(xml: str) -> str:
    return " ".join("".join(ET.fromstring(f"<P>{xml}</P>").itertext()).split())


def _next_roman(prev: str) -> str:
    numerals = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]
    return numerals[numerals.index(prev) + 1] if prev in numerals[:-1] else ""


def _level(token: str, italic: bool, stack: list[tuple[int, str]]) -> int:
    if italic:
        return 5
    if token.isdigit():
        return 2
    if token.isupper():
        return 4
    current = dict(stack)
    if ROMAN.match(token) and (
        (token == "i" and current.get(1) != "h")
        or (token != "i" and _next_roman(current.get(3, "")) == token)
    ):
        return 3
    return 1


def cfr_paragraphs(section_xml: bytes) -> list[tuple[Path_, str]]:
    """Return each <P> of a section with its paragraph path, e.g. ("c", "1", "i")."""
    root = ET.fromstring(section_xml)
    stack: list[tuple[int, str]] = []
    out: list[tuple[Path_, str]] = []
    for p in root.iter("P"):
        raw = (p.text or "") + "".join(ET.tostring(child, encoding="unicode") for child in p)
        lead = LEAD.match(raw)
        if lead:
            tokens = DESIGNATOR.findall("".join(group or "" for group in lead.groups()))
            for open_i, token, _ in tokens:
                level = _level(token, bool(open_i), stack)
                stack = [entry for entry in stack if entry[0] < level] + [(level, token)]
        out.append((tuple(token for _, token in stack), _plain(raw)))
    return out


def cfr_text(section_xml: bytes, path: Path_) -> str:
    texts = [text for p_path, text in cfr_paragraphs(section_xml) if p_path[: len(path)] == path]
    return " ".join(texts)


def ich_sections(pdf_text: str) -> dict[str, str]:
    """Split pdftotext -layout output into numbered sections, dropping page furniture."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    body_started = False
    for line in pdf_text.splitlines():
        stripped = line.strip()
        if stripped == "ICH E6(R3) Guideline" or stripped.isdigit():
            continue
        heading = ICH_HEADING.match(stripped)
        if heading and "..." not in stripped:
            body_started = True
            current = sections.setdefault(heading.group(1), [])
        if body_started and current is not None:
            current.append(stripped)
    return {number: " ".join(" ".join(lines).split()) for number, lines in sections.items()}


def violations() -> list[dict[str, str]]:
    source = tomllib.loads((HERE / "protocols.toml").read_text())
    return [
        {"protocol": protocol["id"], **section["violation"]}
        for protocol in source["protocol"]
        for section in protocol["section"]
        if "violation" in section
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="eCFR issue date, default the latest title 21 issue")
    args = parser.parse_args()

    rows = violations()
    log: list[str] = []
    regtext: dict[str, str] = {}
    failures = 0
    with httpx.Client(headers={"Accept-Encoding": "gzip"}, timeout=60) as client:
        date = args.date or next(
            t["latest_issue_date"]
            for t in json.loads(_get(client, f"{ECFR}/titles.json"))["titles"]
            if t["number"] == 21
        )
        log.append(f"eCFR title 21 issue date {date}")
        sections: dict[str, bytes] = {}
        ich: dict[str, str] | None = None
        for row in rows:
            citation, quote = row["citation"], " ".join(row["quote"].split())
            if cfr := CFR_RE.match(citation):
                part, number, designators = cfr.groups()
                key = f"{part}.{number}"
                if key not in sections:
                    url = f"{ECFR}/full/{date}/title-21.xml?part={part}&section={key}"
                    sections[key] = _get(client, url)
                    log.append(f"GET {url}")
                path = tuple(token for _, token, _ in DESIGNATOR.findall(designators))
                text = cfr_text(sections[key], path)
            elif ich_match := ICH_RE.match(citation):
                if ich is None:
                    with tempfile.TemporaryDirectory() as tmp:
                        pdf = Path(tmp) / "e6r3.pdf"
                        pdf.write_bytes(_get(client, ICH_PDF))
                        log.append(f"GET {ICH_PDF}")
                        layout = subprocess.run(
                            ["pdftotext", "-layout", str(pdf), "-"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout
                    ich = ich_sections(layout)
                text = ich.get(ich_match.group(1), "")
            else:
                text = ""
            status = "OK" if quote in text else "QUOTE-NOT-FOUND" if text else "MISSING-PARAGRAPH"
            failures += status != "OK"
            log.append(f"{status} {row['protocol']} {citation} :: {quote}")
            if text:
                regtext[citation] = text

    log.append(f"{len(rows) - failures}/{len(rows)} citations verified")
    (HERE / "check_citations.log").write_text("\n".join(log) + "\n")
    (HERE / "regtext.json").write_text(json.dumps(dict(sorted(regtext.items())), indent=2) + "\n")
    print("\n".join(log))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
