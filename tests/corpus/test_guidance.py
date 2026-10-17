import hashlib
import os
from datetime import date
from pathlib import Path

import psycopg
import pytest
import yaml
from pydantic import ValidationError

from fda_copilot import cli
from fda_copilot.corpus import ecfr, guidance
from fda_copilot.corpus.guidance import Kind, Line, Source
from fda_copilot.domain.models import RegSource

MIGRATION = Path(__file__).parents[2] / "migrations" / "001_reg_sections.sql"
FIXTURE = (Path(__file__).parent / "fixtures" / "guidance.pdf").read_bytes()
SOURCE = Source(
    key="fixture",
    citation="FDA Test Guidance",
    source=RegSource.fda_guidance,
    title="Test Guidance",
    issued=date(2025, 12, 1),
    url="https://example.gov/media/1/download",
    sha256=hashlib.sha256(FIXTURE).hexdigest(),
    why="Exercises the chunker.",
    first_body_heading="I. INTRODUCTION",
    heading_ranks=((Kind.roman,), (Kind.capital,), (Kind.digit,)),
)


def test_chunks_the_fixture_by_its_numbered_headings() -> None:
    rows = guidance.parse(SOURCE, FIXTURE)

    assert [row.citation for row in rows] == [
        "FDA Test Guidance I",
        "FDA Test Guidance II",
        "FDA Test Guidance II.A",
        "FDA Test Guidance II.A.1",
        "FDA Test Guidance II.A.2",
        "FDA Test Guidance II.B",
        "FDA Test Guidance III",
    ]


def test_rows_cover_the_body_text_without_headers_page_numbers_or_contents() -> None:
    rows = guidance.parse(SOURCE, FIXTURE)

    assert " ".join(row.text for row in rows) == (
        "I. INTRODUCTION This guidance explains how sponsors report safety findings."
        " II. BACKGROUND FDA published the final rule in 2010."
        " A. Scope The rule covers every IND."
        " 1. A numbered list item in plain type is not a heading."
        " 1. Serious Events Report each serious and unexpected event within 15 calendar days."
        " 2. Fatal Events Report fatal events within 7 calendar days."
        " B. Exemptions Bioequivalence studies follow 21 CFR 320.31."
        " III. DISCUSSION C. Out of Sequence"
        " A heading that skips its first sibling stays body text."
    )


def test_a_row_carries_its_heading_page_and_issue_date() -> None:
    row = {row.citation: row for row in guidance.parse(SOURCE, FIXTURE)}["FDA Test Guidance II.A.1"]

    assert (row.source, row.title, row.text, row.effective_date, str(row.url)) == (
        RegSource.fda_guidance,
        "Serious Events",
        "1. Serious Events Report each serious and unexpected event within 15 calendar days.",
        date(2025, 12, 1),
        "https://example.gov/media/1/download#page=1",
    )


def e6(*lines: tuple[str, bool]) -> list[str]:
    source = next(s for s in guidance.load_sources() if s.key == "ich-e6r3")
    rows = guidance.chunk(source, [Line(1, text, styled) for text, styled in lines])
    return [row.citation for row in rows]


def test_e6r3_citations_name_annex_sections_by_number_and_principles_by_name() -> None:
    assert e6(
        ("I. INTRODUCTION", True),
        ("II. PRINCIPLES OF ICH GCP", True),
        ("1. Clinical trials should be conducted in accordance with ethics.", True),
        ("1.1 The rights, safety and well-being of the participants come first.", False),
        ("III. ANNEX 1", True),
        ("1. INSTITUTIONAL REVIEW BOARD/INDEPENDENT ETHICS COMMITTEE (IRB/IEC)", True),
        ("2. INVESTIGATOR", True),
        ("2.1 Qualifications and Training", True),
        ("2.1.1 The investigator should be qualified by education and training.", False),
        ("2.1.3 skips 2.1.2, so it stays text of 2.1.1", False),
        ("2.1.2 The investigator should be familiar with the product.", False),
        ("3. SPONSOR", True),
        ("3.1 Trial Design", True),
        ("3.1.1 Monitoring", True),
        ("3.1.1.1 Investigator Site Monitoring", True),
        ("3.1.1.2 Centralised Monitoring", True),
        ("3.1.1.3 Monitoring Plan", True),
        ("APPENDICES", True),
        ("Appendix A. INVESTIGATOR'S BROCHURE", True),
        ("A.1 Introduction", True),
        ("GLOSSARY", True),
    ) == [
        "ICH E6(R3) Introduction",
        "ICH E6(R3) Principle",
        "ICH E6(R3) Principle 1",
        "ICH E6(R3) Principle 1.1",
        "ICH E6(R3) III",
        "ICH E6(R3) 1",
        "ICH E6(R3) 2",
        "ICH E6(R3) 2.1",
        "ICH E6(R3) 2.1.1",
        "ICH E6(R3) 2.1.2",
        "ICH E6(R3) 3",
        "ICH E6(R3) 3.1",
        "ICH E6(R3) 3.1.1",
        "ICH E6(R3) 3.1.1.1",
        "ICH E6(R3) 3.1.1.2",
        "ICH E6(R3) 3.1.1.3",
        "ICH E6(R3) APPENDICES",
        "ICH E6(R3) Appendix A",
        "ICH E6(R3) A.1",
        "ICH E6(R3) Glossary",
    ]


def test_sources_list_both_ich_guidelines_and_at_most_eight_fda_documents() -> None:
    sources = guidance.load_sources()

    assert [s.key for s in sources if s.source is RegSource.ich] == ["ich-e6r3", "ich-m3r2"]
    assert len([s for s in sources if s.source is RegSource.fda_guidance]) == 8


def test_more_than_eight_fda_documents_are_rejected(tmp_path: Path) -> None:
    entry = SOURCE.model_dump(mode="json")
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump([{**entry, "key": f"doc-{i}"} for i in range(9)]))

    with pytest.raises(ValidationError, match="9 FDA guidance documents listed, at most 8"):
        guidance.load_sources(path)


def test_fetch_refuses_a_pdf_whose_hash_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ecfr, "http_get", lambda url: b"%PDF-1.7 tampered")

    with pytest.raises(ValueError, match=f"but the pin is {SOURCE.sha256}"):
        guidance.fetch(SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_fetch_reuses_a_verified_copy_without_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fixture.pdf").write_bytes(FIXTURE)

    def offline(url: str) -> bytes:
        raise AssertionError(f"downloaded {url}")

    monkeypatch.setattr(ecfr, "http_get", offline)

    assert guidance.fetch(SOURCE, tmp_path) == FIXTURE


def test_fetch_replaces_a_cached_copy_that_no_longer_matches_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fixture.pdf").write_bytes(b"%PDF-1.7 stale")
    monkeypatch.setattr(ecfr, "http_get", lambda url: FIXTURE)

    assert guidance.fetch(SOURCE, tmp_path) == FIXTURE
    assert (tmp_path / "fixture.pdf").read_bytes() == FIXTURE


def test_a_wrong_pin_on_the_last_source_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = SOURCE.model_copy(update={"key": "tampered", "sha256": "0" * 64})
    monkeypatch.setattr(guidance, "load_sources", lambda: [SOURCE, tampered])
    monkeypatch.setattr(ecfr, "http_get", lambda url: FIXTURE)
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute(MIGRATION.read_text())
        conn.execute("DELETE FROM reg_sections WHERE citation LIKE 'FDA Test Guidance%'")

        with pytest.raises(ValueError, match="tampered: .* but the pin is 0000"):
            cli.main(["ingest", "guidance", "--pdf-dir", str(tmp_path)])
        written = conn.execute(
            "SELECT count(*) FROM reg_sections WHERE citation LIKE 'FDA Test Guidance%'"
        ).fetchone()
        monkeypatch.setattr(guidance, "load_sources", lambda: [SOURCE])
        cli.main(["ingest", "guidance", "--pdf-dir", str(tmp_path)])
        after_a_good_run = conn.execute(
            "SELECT count(*) FROM reg_sections WHERE citation LIKE 'FDA Test Guidance%'"
        ).fetchone()
        conn.execute("DELETE FROM reg_sections WHERE citation LIKE 'FDA Test Guidance%'")

    assert (written, after_a_good_run) == ((0,), (7,))


def test_an_integer_heading_that_skips_a_number_stays_body_text() -> None:
    lines = [
        Line(1, "I. INTRODUCTION", True),
        Line(1, "1. First", True),
        Line(1, "3. Third", True),
        Line(1, "2. Second", True),
    ]

    rows = guidance.chunk(SOURCE, lines)

    assert [(row.citation, row.text) for row in rows] == [
        ("FDA Test Guidance I", "I. INTRODUCTION"),
        ("FDA Test Guidance I.1", "1. First 3. Third"),
        ("FDA Test Guidance I.2", "2. Second"),
    ]


def test_a_line_ending_in_a_hyphen_joins_the_next_line_and_keeps_the_hyphen() -> None:
    lines = [
        Line(1, "I. INTRODUCTION", True),
        Line(1, "Studies in non-", False),
        Line(1, "rodent species use trial-", False),
        Line(2, "related data. A spaced dash -", False),
        Line(2, "stays spaced.", False),
    ]

    rows = guidance.chunk(SOURCE, lines)

    assert [row.text for row in rows] == [
        "I. INTRODUCTION Studies in non-rodent species use trial-related data."
        " A spaced dash - stays spaced."
    ]


def fixture_source(name: str, **fields: object) -> tuple[Source, bytes]:
    pdf = (Path(__file__).parent / "fixtures" / name).read_bytes()
    update = {"key": name.removesuffix(".pdf"), "sha256": hashlib.sha256(pdf).hexdigest()}
    return SOURCE.model_copy(update={**update, **fields}), pdf


def test_a_rotated_page_drops_its_running_header_and_reads_its_table_cell_by_cell() -> None:
    source, pdf = fixture_source(
        "rotated.pdf",
        citation="ICH Test",
        first_body_heading="1. INTRODUCTION",
        heading_ranks=((Kind.digit,),),
    )

    rows = guidance.parse(source, pdf)

    assert [(row.citation, row.text) for row in rows] == [
        (
            "ICH Test 1",
            "1. INTRODUCTION Body of introduction."
            " Dose to be Administered Start and Maximum Doses"
            " Total dose under 100 ug Maximal and starting doses",
        ),
        ("ICH Test 2", "2. SCOPE Body of scope."),
    ]


def test_footnotes_follow_the_section_that_cites_them_and_a_marker_in_the_top_margin_counts() -> (
    None
):
    source, pdf = fixture_source("footnoted.pdf")

    rows = guidance.parse(source, pdf)

    assert [(row.citation, row.text) for row in rows] == [
        (
            "FDA Test Guidance I",
            "I. INTRODUCTION The rule applies to drugs1 and the sentence runs onto the next page.2"
            " 1 The first footnote. 2 The second footnote.",
        ),
        ("FDA Test Guidance II", "II. DISCUSSION Closing text."),
    ]
