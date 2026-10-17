import gzip
import http.client
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from enum import StrEnum
from typing import NamedTuple

from pydantic import HttpUrl

from fda_copilot.domain.models import RegCitation, RegSection, RegSource

PARTS = (50, 56, 58, 312, 812)

API = "https://www.ecfr.gov/api/versioner/v1"
_ATTEMPTS = 5
_TRANSIENT = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)


class Kind(StrEnum):
    letter = "letter"
    digit = "digit"
    roman = "roman"
    capital = "capital"


class Marker(NamedTuple):
    kind: Kind
    italic: bool
    label: str


class _Token(NamedTuple):
    italic: bool
    label: str


_LEAD = re.compile(r"\(([0-9]{1,3}|[a-z]{1,5}|[A-Z]{1,3})\)")
_HEADING = re.compile(r"\s*([^\u2014]+?)(?:\.\s*|\u2014)(?=\()")
_ROMAN = {
    "x" * tens + ones: tens * 10 + value
    for tens in range(4)
    for value, ones in enumerate(("", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix"))
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    for attempt in range(_ATTEMPTS):
        delay = float(2**attempt)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body: bytes = response.read()
                gzipped = response.headers.get("Content-Encoding") == "gzip"
            return gzip.decompress(body) if gzipped else body
        except urllib.error.HTTPError as error:
            if (error.code != 429 and error.code < 500) or attempt == _ATTEMPTS - 1:
                raise
            retry_after = error.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = float(retry_after)
        except _TRANSIENT:
            if attempt == _ATTEMPTS - 1:
                raise
        time.sleep(delay)
    raise AssertionError("unreachable")


def latest_date() -> date:
    titles = json.loads(_get(f"{API}/titles.json"))["titles"]
    title_21 = next(t for t in titles if t["number"] == 21)
    return date.fromisoformat(title_21["up_to_date_as_of"])


def fetch_part(part: int, on: date) -> bytes:
    return _get(f"{API}/full/{on.isoformat()}/title-21.xml?part={part}")


def fetch_effective_dates(part: int, on: date) -> dict[str, date]:
    versions = json.loads(_get(f"{API}/versions/title-21.json?part={part}"))["content_versions"]
    dates: dict[str, date] = {}
    for version in versions:
        effective = date.fromisoformat(version["date"])
        if effective <= on and not version["removed"]:
            section = version["identifier"]
            dates[section] = max(effective, dates.get(section, effective))
    return dates


def parse_part(xml: bytes, effective_dates: Mapping[str, date]) -> list[RegSection]:
    root = ET.fromstring(xml)
    return [
        reg_section
        for div in root.iter("DIV8")
        for reg_section in _parse_section(div, effective_dates[div.attrib["N"]])
    ]


def _parse_section(div: ET.Element, effective_date: date) -> Iterator[RegSection]:
    number = div.attrib["N"]
    title = _text(div.find("HEAD")).removeprefix(f"§ {number}").strip()
    paragraphs = list(div.iter("P"))
    leads = [_lead_tokens(p) for p in paragraphs]
    upcoming = [token for tokens in leads for token in tokens]

    texts: dict[tuple[Marker, ...], list[str]] = {}
    stack: tuple[Marker, ...] = ()
    for paragraph, tokens in zip(paragraphs, leads, strict=True):
        for token in tokens:
            upcoming.pop(0)
            stack = _push(stack, token, upcoming)
        texts.setdefault(stack, []).append(_text(paragraph))

    for markers, parts in texts.items():
        anchor = number + "".join(f"({m.label})" for m in markers)
        yield RegSection(
            citation=RegCitation(f"21 CFR {anchor}"),
            source=RegSource.cfr,
            title=title,
            text="\n\n".join(parts),
            effective_date=effective_date,
            url=HttpUrl(
                f"https://www.ecfr.gov/on/{effective_date.isoformat()}"
                f"/title-21/section-{number}#p-{anchor}"
            ),
        )


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _lead_tokens(paragraph: ET.Element) -> list[_Token]:
    runs = [(paragraph.text or "", False)]
    for child in paragraph:
        runs += [("".join(child.itertext()), child.tag == "I"), (child.tail or "", False)]
    head = "".join(text for text, _ in runs)
    italic = [flag for text, flag in runs for _ in text]
    tokens = []
    position = 0
    while match := _LEAD.match(head, position):
        tokens.append(_Token(italic=italic[match.start(1)], label=match.group(1)))
        position = match.end()
        heading = _HEADING.match(head, position)
        if (
            heading
            and all(italic[heading.start(1) : heading.end(1)])
            and _LEAD.match(head, heading.end())
        ):
            position = heading.end()
    return tokens


def _push(
    stack: tuple[Marker, ...], token: _Token, upcoming: Sequence[_Token]
) -> tuple[Marker, ...]:
    marker = Marker(_kind(stack, token, upcoming), token.italic, token.label)
    for depth, open_marker in enumerate(stack):
        if (open_marker.kind, open_marker.italic) == (marker.kind, marker.italic):
            return (*stack[:depth], marker)
    return (*stack, marker)


def _kind(stack: tuple[Marker, ...], token: _Token, upcoming: Sequence[_Token]) -> Kind:
    label = token.label
    if label.isdigit():
        return Kind.digit
    if label.isupper():
        return Kind.capital
    if len(label) > 1:
        return Kind.roman
    open_roman = next((m for m in stack if (m.kind, m.italic) == (Kind.roman, token.italic)), None)
    if open_roman is not None and _ROMAN.get(open_roman.label, -1) + 1 == _ROMAN.get(label):
        return Kind.roman
    if label == "i" and _opens_roman(stack, token.italic, upcoming):
        return Kind.roman
    return Kind.letter


def _opens_roman(stack: tuple[Marker, ...], italic: bool, upcoming: Sequence[_Token]) -> bool:
    if Marker(Kind.letter, italic, "h") not in stack:
        return True
    for token in upcoming:
        if token.italic == italic and token.label in ("i", "ii", "j"):
            return token.label == "ii"
    return False
