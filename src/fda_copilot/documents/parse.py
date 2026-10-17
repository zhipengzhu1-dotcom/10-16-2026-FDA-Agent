import hashlib
import io
import re
import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, NamedTuple

import docx
import pymupdf
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from fda_copilot.domain.models import CharSpan, DocSection, DocSectionId


class UnsupportedDocument(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    """The parse of one uploaded file.

    `text` is the canonical extracted text: every extracted line in document order, each
    followed by one newline. A PDF line is one pymupdf text line, a DOCX line is one body
    paragraph or one table row with cells joined by tabs. Every section's span indexes into
    `text`, its `text` equals that slice, and the spans tile `text` in order with no gap and
    no overlap. Text before the first heading is a section whose heading is empty.
    """

    text: str
    sections: tuple[DocSection, ...]

    def __post_init__(self) -> None:
        position = 0
        for section in self.sections:
            start, end = section.span.start, section.span.end
            if start != position or section.text != self.text[start:end]:
                raise ValueError(f"section {section.id} breaks the span contract")
            position = end
        if position != len(self.text):
            raise ValueError("sections do not cover the whole text")


@dataclass(frozen=True)
class _Line:
    text: str
    heading: str | None = None


class _Style(NamedTuple):
    font: str
    size: float
    bold: bool


@dataclass(frozen=True)
class _PdfLine:
    text: str
    page: int
    style: _Style | None


_SECTION_NUMBER = re.compile(r"\s*(\d+(?:\.\d+)*\.?)(?:\s+|$)")
_TOC_LEADER = re.compile(r"\.{5,}|…{2,}")
_MAX_HEADING_CHARS = 200


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".pdf":
        lines = _pdf_lines(filename, data)
    elif suffix == ".docx":
        lines = _docx_lines(filename, data)
    else:
        raise UnsupportedDocument(f"{filename}: only .docx and .pdf are supported")
    return _assemble(lines, hashlib.sha256(data).hexdigest()[:12])


def _assemble(lines: Sequence[_Line], doc_key: str) -> ParsedDocument:
    if not lines:
        return ParsedDocument(text="", sections=())
    text = "".join(f"{line.text}\n" for line in lines)
    starts: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        if line.heading is not None:
            starts.append((offset, line.heading))
        offset += len(line.text) + 1
    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, ""))
    ends = [start for start, _ in starts[1:]] + [len(text)]
    sections = tuple(
        DocSection(
            id=DocSectionId(f"{doc_key}-{index:04d}"),
            heading=heading,
            text=text[start:end],
            span=CharSpan(start=start, end=end),
        )
        for index, ((start, heading), end) in enumerate(zip(starts, ends, strict=True))
    )
    return ParsedDocument(text=text, sections=sections)


def _docx_lines(filename: str, data: bytes) -> list[_Line]:
    try:
        document = docx.Document(io.BytesIO(data))
    except (zipfile.BadZipFile, PackageNotFoundError, KeyError, ValueError) as error:
        raise UnsupportedDocument(f"{filename}: not a readable .docx file") from error
    lines: list[_Line] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text
            heading = _squash(text) if _is_heading_style(block) else ""
            lines.append(_Line(text, heading or None))
        elif isinstance(block, Table):
            lines.extend(_Line("\t".join(cell.text for cell in row.cells)) for row in block.rows)
    return lines


def _is_heading_style(paragraph: Paragraph) -> bool:
    name = (paragraph.style.name if paragraph.style is not None else None) or ""
    return name == "Title" or name.startswith("Heading")


def _pdf_lines(filename: str, data: bytes) -> list[_Line]:
    try:
        document = pymupdf.Document(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except pymupdf.FileDataError as error:
        raise UnsupportedDocument(f"{filename}: not a readable .pdf file") from error
    with document:
        if document.needs_pass:
            raise UnsupportedDocument(f"{filename}: the PDF is encrypted")
        lines: list[_PdfLine] = []
        for page_number, page in enumerate(document.pages(), start=1):
            page_text: dict[str, Any] = page.get_text(  # type: ignore[no-untyped-call]
                "dict", flags=pymupdf.TEXTFLAGS_TEXT
            )
            lines.extend(
                _pdf_line(line, page_number)
                for block in page_text["blocks"]
                for line in block["lines"]
            )
        toc: list[list[Any]] = document.get_toc()
    headings = _outline_headings(toc, lines) or _font_headings(lines)
    return [_Line(line.text, headings.get(index)) for index, line in enumerate(lines)]


def _pdf_line(line: dict[str, Any], page: int) -> _PdfLine:
    spans: list[dict[str, Any]] = line["spans"]
    inked = [span for span in spans if any(char.isalnum() for char in span["text"])]
    style = None
    if inked:
        bold = all(
            span["flags"] & pymupdf.TEXT_FONT_BOLD or "bold" in span["font"].lower()
            for span in inked
        )
        style = _Style(str(inked[0]["font"]), round(max(float(s["size"]) for s in inked), 1), bold)
    return _PdfLine("".join(span["text"] for span in spans), page, style)


def _outline_headings(toc: Sequence[Sequence[Any]], lines: Sequence[_PdfLine]) -> dict[int, str]:
    headings: dict[int, str] = {}
    cursor = 0
    for _level, raw_title, page, *_ in toc:
        title = _squash(str(raw_title))
        wanted = _title_key(title)
        if not wanted:
            continue
        for index in range(cursor, len(lines)):
            line = lines[index]
            if line.page < page:
                continue
            if line.page > page + 1:
                break
            got = _title_key(line.text)
            if got == wanted or (len(got) >= 4 and wanted.startswith(got)):
                start = index - 1 if index > cursor and _is_bare_number(lines[index - 1]) else index
                headings[start] = title
                cursor = start + 1
                break
    return headings


def _is_bare_number(line: _PdfLine) -> bool:
    number = _SECTION_NUMBER.match(line.text)
    return number is not None and number.end() == len(line.text)


def _title_key(text: str) -> str:
    number = _SECTION_NUMBER.match(text)
    return _squash(text[number.end() :] if number else text).casefold()


def _font_headings(lines: Sequence[_PdfLine]) -> dict[int, str]:
    sizes: Counter[float] = Counter()
    for line in lines:
        if line.style:
            sizes[line.style.size] += len(line.text.strip())
    if not sizes:
        return {}
    body_size = sizes.most_common(1)[0][0]

    def starts_heading(line: _PdfLine) -> bool:
        if line.style is None:
            return False
        number = _SECTION_NUMBER.match(line.text)
        dotted_number = number is not None and "." in number.group(1)
        return line.style.size >= body_size + 0.5 or (line.style.bold and dotted_number)

    headings: dict[int, str] = {}
    index = 0
    while index < len(lines):
        first = lines[index]
        if not starts_heading(first):
            index += 1
            continue
        end = index + 1
        while (
            end < len(lines)
            and lines[end].style == first.style
            and lines[end].page == first.page
            and not _SECTION_NUMBER.match(lines[end].text)
        ):
            end += 1
        heading = _squash(" ".join(line.text for line in lines[index:end]))
        if (
            len(heading) <= _MAX_HEADING_CHARS
            and any(char.isalpha() for char in heading)
            and not _TOC_LEADER.search(heading)
        ):
            headings[index] = heading
        index = end
    return headings


def _squash(text: str) -> str:
    return " ".join(text.split())
