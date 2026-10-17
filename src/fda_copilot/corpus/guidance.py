import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

import pymupdf
import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from fda_copilot.corpus import ecfr
from fda_copilot.domain.models import RegCitation, RegSection, RegSource

SOURCES = Path(__file__).parents[3] / "corpus" / "guidance_sources.yaml"
MAX_FDA_GUIDANCE = 8
_MARGIN = 0.12
_FURNITURE_PAGE_SHARE = 0.5


class Kind(StrEnum):
    roman = "roman"
    capital = "capital"
    digit = "digit"
    small = "small"
    decimal = "decimal"
    appendix = "appendix"
    named = "named"
    subpart = "subpart"
    section = "section"
    question = "question"


class Source(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]
    citation: Annotated[str, Field(pattern=r"\S")]
    source: Literal[RegSource.ich, RegSource.fda_guidance]
    title: str
    issued: date
    url: HttpUrl
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    why: Annotated[str, Field(pattern=r"\S")]
    first_body_heading: str
    heading_ranks: tuple[tuple[Kind, ...], ...]
    unstyled: tuple[Kind, ...] = ()
    named: tuple[str, ...] = ()
    rename: dict[str, str] = Field(default_factory=dict)


class _Sources(BaseModel):
    sources: list[Source]

    @model_validator(mode="after")
    def _bounded(self) -> "_Sources":
        keys = Counter(s.key for s in self.sources)
        if repeated := [key for key, count in keys.items() if count > 1]:
            raise ValueError(f"repeated source keys: {repeated}")
        fda = sum(s.source is RegSource.fda_guidance for s in self.sources)
        if fda > MAX_FDA_GUIDANCE:
            raise ValueError(f"{fda} FDA guidance documents listed, at most {MAX_FDA_GUIDANCE}")
        return self


def load_sources(path: Path = SOURCES) -> list[Source]:
    return _Sources(sources=yaml.safe_load(path.read_text())).sources


def fetch(source: Source, directory: Path) -> bytes:
    path = directory / f"{source.key}.pdf"
    if path.exists() and _sha256(cached := path.read_bytes()) == source.sha256:
        return cached
    pdf = ecfr.http_get(str(source.url))
    if (digest := _sha256(pdf)) != source.sha256:
        raise ValueError(
            f"{source.key}: {source.url} served sha256 {digest}, but the pin is {source.sha256}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(pdf)
    partial.replace(path)
    return pdf


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Line(NamedTuple):
    page: int
    text: str
    styled: bool


class _PdfLine(NamedTuple):
    top: float
    bottom: float
    left: float
    text: str
    styled: bool


def parse(source: Source, pdf: bytes) -> list[RegSection]:
    return chunk(source, body(source, pdf))


def body(source: Source, pdf: bytes) -> list[Line]:
    lines = read_lines(pdf)
    start = next(
        (i for i, line in enumerate(lines) if line.text == source.first_body_heading), None
    )
    if start is None:
        raise ValueError(f"{source.key}: no line reads {source.first_body_heading!r}")
    return lines[start:]


def read_lines(pdf: bytes) -> list[Line]:
    with pymupdf.Document(stream=pdf, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        pages = [(_pdf_lines(page), page.rect.height) for page in document]
    counts = Counter(
        shape
        for lines, height in pages
        for shape in {_shape(line.text) for line in lines if _in_margin(line, height)}
    )
    repeated = max(2, math.ceil(len(pages) * _FURNITURE_PAGE_SHARE))
    furniture = {shape for shape, count in counts.items() if count >= repeated}
    return [
        merged
        for number, (lines, height) in enumerate(pages, 1)
        for merged in _merge_rows(
            number,
            [ln for ln in lines if not (_in_margin(ln, height) and _shape(ln.text) in furniture)],
        )
    ]


def _pdf_lines(page: pymupdf.Page) -> list[_PdfLine]:
    text_page: dict[str, Any] = page.get_text(  # type: ignore[no-untyped-call]
        "dict", flags=pymupdf.TEXTFLAGS_TEXT
    )
    lines = []
    for block in text_page["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if spans:
                left, top, _, bottom = line["bbox"]
                bold_or_italic = spans[0]["flags"] & (
                    pymupdf.TEXT_FONT_BOLD | pymupdf.TEXT_FONT_ITALIC
                )
                text = " ".join("".join(s["text"] for s in line["spans"]).split())
                lines.append(_PdfLine(top, bottom, left, text, bool(bold_or_italic)))
    return lines


def _merge_rows(page: int, lines: list[_PdfLine]) -> list[Line]:
    rows: list[list[_PdfLine]] = []
    for line in sorted(lines):
        if rows and line.top - rows[-1][0].top <= 2:
            rows[-1].append(line)
        else:
            rows.append([line])
    return [
        Line(page, " ".join(line.text for line in row), row[0].styled)
        for row in (sorted(row, key=lambda line: line.left) for row in rows)
    ]


def _in_margin(line: _PdfLine, height: float) -> bool:
    return line.bottom < height * _MARGIN or line.top > height * (1 - _MARGIN)


def _shape(text: str) -> str:
    return re.sub(r"\d+", "#", text)


class _Grammar(NamedTuple):
    pattern: re.Pattern[str]
    first: Callable[[str, str | None], bool]
    follows: Callable[[str, str], bool]
    render: Callable[[str], str]
    sep: str
    titled: bool = False


def _roman(numeral: str) -> int:
    values = [{"I": 1, "V": 5, "X": 10}[c] for c in numeral]
    return sum(-v if v < after else v for v, after in zip(values, [*values[1:], 0], strict=True))


def _next_char(prev: str, label: str) -> bool:
    return ord(label) == ord(prev) + 1


def _next_int(prev: str, label: str) -> bool:
    return int(label) == int(prev) + 1


def _decimal_parts(label: str) -> tuple[str, int]:
    head, _, last = label.rpartition(".")
    return head, int(last)


def _next_decimal(prev: str, label: str) -> bool:
    (prev_head, prev_last), (head, last) = _decimal_parts(prev), _decimal_parts(label)
    return head == prev_head and last == prev_last + 1


def _first_decimal(label: str, parent: str | None) -> bool:
    return label == f"{parent}.1"


def _section_key(label: str) -> tuple[int, ...]:
    return tuple(int(part) for part in label.split("."))


def _any(label: str, parent: str | None) -> bool:
    return True


GRAMMAR: dict[Kind, _Grammar] = {
    Kind.roman: _Grammar(
        re.compile(r"([IVX]+)\.(?=\s|$)"),
        lambda label, _: label == "I",
        lambda prev, label: _roman(label) == _roman(prev) + 1,
        str,
        "",
    ),
    Kind.capital: _Grammar(
        re.compile(r"([A-Z])\.(?=\s|$)"),
        lambda label, _: label == "A",
        _next_char,
        str,
        ".",
    ),
    Kind.digit: _Grammar(
        re.compile(r"(\d{1,2})\.(?=\s|$)"),
        lambda label, _: label == "1",
        _next_int,
        str,
        ".",
    ),
    Kind.small: _Grammar(
        re.compile(r"([a-z])\.(?=\s|$)"),
        lambda label, _: label == "a",
        _next_char,
        str,
        ".",
    ),
    Kind.decimal: _Grammar(
        re.compile(r"((?:\d{1,2}|[A-Z])(?:\.\d{1,2})+)\.?(?=\s|$)"),
        _first_decimal,
        _next_decimal,
        str,
        ".",
    ),
    Kind.appendix: _Grammar(
        re.compile(r"Appendix ([A-Z])\.(?=\s|$)"),
        lambda label, _: label == "A",
        _next_char,
        lambda label: f"Appendix {label}",
        " ",
        titled=True,
    ),
    Kind.named: _Grammar(re.compile(r"(?!)"), _any, lambda prev, label: True, str, " "),
    Kind.subpart: _Grammar(
        re.compile(r"SUBPART ([A-Z])(?=\s|$)"),
        _any,
        lambda prev, label: label > prev,
        lambda label: f"Subpart {label}",
        " ",
        titled=True,
    ),
    Kind.section: _Grammar(
        re.compile(r"Section (\d+\.\d+)(?=\s)"),
        _any,
        lambda prev, label: _section_key(label) > _section_key(prev),
        str,
        " ",
        titled=True,
    ),
    Kind.question: _Grammar(
        re.compile(r"(\d{1,3})\.(?=\s|$)"),
        lambda label, _: label == "1",
        _next_int,
        lambda label: f"Q{label}",
        " ",
    ),
}


class _Node(NamedTuple):
    kind: Kind
    label: str
    rank: int
    title: str


@dataclass
class _Section:
    citation: str
    title: str
    page: int
    lines: list[str]


def chunk(source: Source, lines: Sequence[Line]) -> list[RegSection]:
    ranks = {kind: rank for rank, kinds in enumerate(source.heading_ranks) for kind in kinds}
    stack: list[_Node] = []
    last: dict[int, dict[Kind, str]] = {}
    sections: list[_Section] = []
    for line in lines:
        node = _heading(source, ranks, stack, last, line)
        if node is None:
            if not sections:
                raise ValueError(f"{source.key}: body starts with a non-heading {line.text!r}")
            sections[-1].lines.append(line.text)
            continue
        stack = [n for n in stack if n.rank < node.rank] + [node]
        last = {rank: labels for rank, labels in last.items() if rank <= node.rank}
        last.setdefault(node.rank, {})[node.kind] = node.label
        title = next((n.title for n in reversed(stack) if n.title), source.title)
        sections.append(_Section(_cite(source, stack), title, line.page, [line.text]))

    repeated = [c for c, n in Counter(s.citation for s in sections).items() if n > 1]
    if repeated:
        raise ValueError(f"{source.key}: repeated citations {repeated}")
    return [
        RegSection(
            citation=RegCitation(s.citation),
            source=source.source,
            title=s.title,
            text=" ".join(s.lines),
            effective_date=source.issued,
            url=HttpUrl(f"{source.url}#page={s.page}"),
        )
        for s in sections
    ]


def _heading(
    source: Source,
    ranks: dict[Kind, int],
    stack: list[_Node],
    last: dict[int, dict[Kind, str]],
    line: Line,
) -> _Node | None:
    for kind, base in ranks.items():
        grammar = GRAMMAR[kind]
        if kind is Kind.named:
            if line.text not in source.named:
                continue
            label, rest = line.text, line.text
        elif match := grammar.pattern.match(line.text):
            label, rest = match.group(1), line.text[match.end() :].strip(" -\u2013\u2014")
        else:
            continue
        rank = base + label.count(".") - 1 if kind is Kind.decimal else base
        parent = next((n.label for n in reversed(stack) if n.rank < rank), None)
        prev = last.get(rank, {}).get(kind)
        styled = line.styled or kind is Kind.named
        if not styled and kind not in source.unstyled:
            continue
        if grammar.first(label, parent) if prev is None else grammar.follows(prev, label):
            return _Node(kind, label, rank, rest if styled or grammar.titled else "")
    return None


def _cite(source: Source, stack: list[_Node]) -> str:
    nodes = [
        node
        for i, node in enumerate(stack)
        if not any(later.label.startswith(f"{node.label}.") for later in stack[i + 1 :])
    ]
    (_, head), *rest = [(GRAMMAR[n.kind].sep, GRAMMAR[n.kind].render(n.label)) for n in nodes]
    alias = source.rename.get(head)
    if alias is None:
        suffix = head + "".join(sep + text for sep, text in rest)
    elif not rest:
        suffix = alias or head
    else:
        tail = rest[0][1] + "".join(sep + text for sep, text in rest[1:])
        suffix = f"{alias} {tail}" if alias else tail
    return f"{source.citation} {suffix}"
