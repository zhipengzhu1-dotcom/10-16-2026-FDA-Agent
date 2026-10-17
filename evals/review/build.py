"""Build protocols/*.docx and gold.jsonl from protocols.toml.

Run with --check to fail when the committed files differ from what the source builds.
"""

import argparse
import io
import json
import sys
import tomllib
import zipfile
from collections import Counter
from pathlib import Path
from typing import Annotated, Self
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fda_copilot.domain.models import Domain, RegCitation

HERE = Path(__file__).parent
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


class _Source(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Violation(_Source):
    citation: RegCitation
    quote: str
    issue: str


class Section(_Source):
    heading: str
    text: str
    violation: Violation | None = None


class Protocol(_Source):
    id: str
    domain: Domain
    held_out: bool
    title: str
    section: tuple[Section, ...]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        headings = [s.heading for s in self.section]
        if len(set(headings)) != len(headings):
            raise ValueError(f"{self.id}: section headings must be unique")
        planted = sum(s.violation is not None for s in self.section)
        if not 2 <= planted <= 5:
            raise ValueError(f"{self.id}: {planted} violations, need 2 to 5")
        return self


class EvalSet(_Source):
    protocol: Annotated[tuple[Protocol, ...], Field(min_length=12)]

    @model_validator(mode="after")
    def _split(self) -> Self:
        per_domain = Counter(p.domain for p in self.protocol)
        held_out = Counter(p.domain for p in self.protocol if p.held_out)
        for domain in Domain:
            if per_domain[domain] < 3 or held_out[domain] * 3 != per_domain[domain]:
                raise ValueError(f"{domain}: need 3+ protocols with one third held out")
        return self


def gold_rows(protocol: Protocol) -> list[dict[str, object]]:
    return [
        {
            "protocol": protocol.id,
            "domain": protocol.domain.value,
            "section": section.heading,
            "citation": section.violation.citation,
            "quote": section.violation.quote,
            "issue": section.violation.issue,
            "held_out": protocol.held_out,
        }
        for section in protocol.section
        if section.violation is not None
    ]


def _paragraph(text: str, style: str | None = None) -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/'
    'vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
STYLES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
    "</w:style>"
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
    '<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
    "</w:styles>"
)


def docx(protocol: Protocol) -> bytes:
    body = [
        _paragraph(protocol.title, "Title"),
        _paragraph("Synthetic document for evaluation. It describes no real study."),
    ]
    for section in protocol.section:
        body.append(_paragraph(section.heading, "Heading1"))
        body += [_paragraph(p.strip()) for p in section.text.strip().split("\n\n")]
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}>'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": PACKAGE_RELS,
        "word/_rels/document.xml.rels": DOCUMENT_RELS,
        "word/document.xml": document,
        "word/styles.xml": STYLES,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(zipfile.ZipInfo(name, ZIP_EPOCH), content)
    return buffer.getvalue()


def render() -> dict[Path, bytes]:
    """Every generated file, keyed by its path relative to evals/review."""
    source = EvalSet.model_validate(tomllib.loads((HERE / "protocols.toml").read_text()))
    files = {Path("protocols") / f"{p.id}.docx": docx(p) for p in source.protocol}
    rows = [json.dumps(row, ensure_ascii=False) for p in source.protocol for row in gold_rows(p)]
    files[Path("gold.jsonl")] = ("\n".join(rows) + "\n").encode()
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift, write nothing")
    args = parser.parse_args()

    files = render()
    if not args.check:
        (HERE / "protocols").mkdir(exist_ok=True)
        for path, data in files.items():
            (HERE / path).write_bytes(data)
        print(f"wrote {len(files)} files")
        return 0
    stale = sorted(str(p) for p in drift(files))
    print("\n".join(f"STALE {p}" for p in stale) or f"OK {len(files)} files match protocols.toml")
    return 1 if stale else 0


def drift(files: dict[Path, bytes]) -> set[Path]:
    """Paths whose committed bytes differ from the build, including orphan protocols."""
    changed = {
        p
        for p, data in files.items()
        if not (HERE / p).is_file() or (HERE / p).read_bytes() != data
    }
    orphans = {p.relative_to(HERE) for p in (HERE / "protocols").glob("*.docx")} - files.keys()
    return changed | orphans


if __name__ == "__main__":
    sys.exit(main())
