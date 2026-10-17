import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest

from fda_copilot.corpus.ecfr import parse_part
from fda_copilot.corpus.store import upsert
from fda_copilot.domain.models import RegSection, RegSource

FIXTURES = Path(__file__).parent / "fixtures"
MIGRATIONS = Path(__file__).parents[2] / "migrations"
EFFECTIVE = date(2026, 9, 22)


def parse_fixture(name: str, section: str) -> dict[str, RegSection]:
    rows = parse_part((FIXTURES / name).read_bytes(), {section: EFFECTIVE})
    return {row.citation: row for row in rows}


def parse_xml(paragraphs: str) -> list[str]:
    xml = f'<DIV8 N="1.1"><HEAD>§ 1.1 Test.</HEAD>{paragraphs}</DIV8>'.encode()
    return [row.citation for row in parse_part(xml, {"1.1": EFFECTIVE})]


def test_parses_50_25_a_1() -> None:
    row = parse_fixture("part50_section25.xml", "50.25")["21 CFR 50.25(a)(1)"]

    assert row.text[:40] == "(1) A statement that the study involves "
    assert row.title == "Elements of informed consent."
    assert row.source is RegSource.cfr
    assert row.effective_date == EFFECTIVE
    assert str(row.url) == (
        "https://www.ecfr.gov/on/2026-09-22/title-21/section-50.25#p-50.25(a)(1)"
    )


def test_bare_2_belongs_to_the_last_lettered_paragraph() -> None:
    rows = parse_fixture("part312_section32.xml", "312.32")

    assert rows["21 CFR 312.32(c)(2)"].text.startswith(
        "(2) Unexpected fatal or life-threatening suspected adverse reaction reports."
    )
    assert rows["21 CFR 312.32(d)(2)"].text.startswith(
        "(2) Relevant followup information to an IND safety report"
    )


def test_combined_lead_marker_splits_into_two_levels() -> None:
    rows = parse_fixture("part312_section32.xml", "312.32")

    assert rows["21 CFR 312.32(c)(1)"].text.startswith("(c)(1) IND safety reports. The sponsor")
    assert "21 CFR 312.32(c)(1)(i)(A)" in rows
    assert rows["21 CFR 312.32(d)(1)"].text.startswith("(d) Followup. (1) The sponsor")


def test_unmarked_paragraphs_join_the_paragraph_above() -> None:
    definitions = parse_fixture("part312_section32.xml", "312.32")["21 CFR 312.32(a)"].text

    assert definitions.startswith("(a) Definitions.")
    assert "\n\nAdverse event means" in definitions
    assert "\n\nUnexpected adverse event or unexpected suspected adverse reaction." in definitions


def test_i_after_h_is_a_letter_unless_ii_follows() -> None:
    letter = parse_xml("<P>(h) H.</P><P>(1) One.</P><P>(i) I.</P><P>(j) J.</P>")
    roman = parse_xml("<P>(h) H.</P><P>(1) One.</P><P>(i) I.</P><P>(ii) Two.</P>")

    assert letter == ["21 CFR 1.1(h)", "21 CFR 1.1(h)(1)", "21 CFR 1.1(i)", "21 CFR 1.1(j)"]
    assert roman == [
        "21 CFR 1.1(h)",
        "21 CFR 1.1(h)(1)",
        "21 CFR 1.1(h)(1)(i)",
        "21 CFR 1.1(h)(1)(ii)",
    ]


def test_italic_markers_nest_below_roman() -> None:
    citations = parse_xml(
        "<P>(a) A.</P><P>(6) <I>Protocols.</I> (i) One.</P><P>(ii) Two.</P>"
        "<P>(<I>a</I>) Italic.</P><P>(7) Seven.</P>"
    )

    assert citations == [
        "21 CFR 1.1(a)",
        "21 CFR 1.1(a)(6)(i)",
        "21 CFR 1.1(a)(6)(ii)",
        "21 CFR 1.1(a)(6)(ii)(a)",
        "21 CFR 1.1(a)(7)",
    ]


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute((MIGRATIONS / "001_reg_sections.sql").read_text())
        conn.execute("DELETE FROM reg_sections")
        yield conn
        conn.rollback()


def test_second_upsert_changes_nothing(conn: psycopg.Connection) -> None:
    sections = list(parse_fixture("part312_section32.xml", "312.32").values())

    assert upsert(conn, sections) == len(sections)
    assert upsert(conn, sections) == 0
    edited = sections[0].model_copy(update={"text": "edited"})
    assert upsert(conn, [edited]) == 1
