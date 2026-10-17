from itertools import pairwise
from pathlib import Path

import pymupdf
import pytest

from fda_copilot.cli import main
from fda_copilot.documents.parse import ParsedDocument, UnsupportedDocument, parse_document

FIXTURES = Path(__file__).parent / "fixtures"
DOCX = FIXTURES / "protocol.docx"
PDF = FIXTURES / "protocol.pdf"


def parse(path: Path) -> ParsedDocument:
    return parse_document(path.name, path.read_bytes())


def outlined_pdf() -> bytes:
    with pymupdf.open(PDF) as document:
        document.set_toc(
            [[1, "Introduction", 1], [1, "Informed Consent and Participant Rights", 2]]
        )
        return document.tobytes()


def test_docx_headings() -> None:
    assert [section.heading for section in parse(DOCX).sections] == [
        "",
        "Example Protocol EX-001",
        "1. Introduction",
        "1.1 Background",
        "2. Informed Consent",
        "3. Safety Reporting",
    ]


def test_docx_section_text_includes_table_rows() -> None:
    consent = parse(DOCX).sections[4]
    assert consent.text == (
        "2. Informed Consent\nRisk\tLevel\nHeadache\tLow\n"
        "Each participant signs the form before dosing.\n"
    )


def test_pdf_font_size_headings() -> None:
    assert [section.heading for section in parse(PDF).sections] == [
        "",
        "Example Protocol EX-001",
        "Contents",
        "1. Introduction",
        "1.1 Background",
        "2. Informed Consent and Participant Rights",
        "3. Safety Reporting",
    ]


def test_pdf_outline_headings_win_over_font_sizes() -> None:
    sections = parse_document("outlined.pdf", outlined_pdf()).sections
    assert [section.heading for section in sections] == [
        "",
        "Introduction",
        "Informed Consent and Participant Rights",
    ]
    assert sections[1].text.startswith("1. Introduction\nThis study tests drug X")


@pytest.mark.parametrize(
    "document",
    [parse(DOCX), parse(PDF), parse_document("outlined.pdf", outlined_pdf())],
    ids=["docx", "pdf-font", "pdf-outline"],
)
def test_spans_slice_back_and_tile_the_text(document: ParsedDocument) -> None:
    spans = [(section.span.start, section.span.end) for section in document.sections]
    assert spans[0][0] == 0
    assert spans[-1][1] == len(document.text)
    assert all(end == next_start for (_, end), (next_start, _) in pairwise(spans))
    for section in document.sections:
        assert section.text == document.text[section.span.start : section.span.end]
        assert section.text


def test_parsed_document_refuses_spans_that_leave_a_gap() -> None:
    first = parse(DOCX).sections[0]
    with pytest.raises(ValueError, match="cover the whole text"):
        ParsedDocument(text=first.text + "orphan\n", sections=(first,))


def test_section_ids_are_unique() -> None:
    sections = parse(PDF).sections
    assert len({section.id for section in sections}) == len(sections)


@pytest.mark.parametrize(
    ("filename", "data"),
    [("notes.txt", b"hello"), ("scan.pdf", b"not a pdf"), ("protocol.docx", b"not a zip")],
)
def test_rejects_other_files(filename: str, data: bytes) -> None:
    with pytest.raises(UnsupportedDocument):
        parse_document(filename, data)


def test_cli_prints_one_line_per_section(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["parse", str(DOCX)]) == 0
    assert capsys.readouterr().out == (
        "0-24\t\n"
        "24-48\tExample Protocol EX-001\n"
        "48-105\t1. Introduction\n"
        "105-151\t1.1 Background\n"
        "151-242\t2. Informed Consent\n"
        "242-309\t3. Safety Reporting\n"
    )


def test_cli_reports_unsupported_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    assert main(["parse", str(notes)]) == 1
    assert capsys.readouterr().err == (
        "fda-copilot parse: notes.txt: only .docx and .pdf are supported\n"
    )
