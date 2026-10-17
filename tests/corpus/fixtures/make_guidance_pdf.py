"""Regenerate guidance.pdf: uv run python tests/corpus/fixtures/make_guidance_pdf.py"""

from pathlib import Path

import pymupdf

PAGES = [
    [
        (40, "hebo", "Contains Nonbinding Recommendations"),
        (90, "hebo", "Guidance for Industry"),
        (120, "helv", "I. INTRODUCTION .................................. 1"),
        (160, "hebo", "I. INTRODUCTION"),
        (180, "helv", "This guidance explains how sponsors report safety findings."),
        (210, "hebo", "II. BACKGROUND"),
        (230, "helv", "FDA published the final rule in 2010."),
        (260, "hebo", "A. Scope"),
        (280, "helv", "The rule covers every IND."),
        (300, "helv", "1. A numbered list item in plain type is not a heading."),
        (330, "heit", "1. Serious Events"),
        (350, "helv", "Report each serious and unexpected event"),
        (750, "helv", "1"),
    ],
    [
        (40, "hebo", "Contains Nonbinding Recommendations"),
        (90, "helv", "within 15 calendar days."),
        (120, "heit", "2. Fatal Events"),
        (140, "helv", "Report fatal events within 7 calendar days."),
        (170, "hebo", "B. Exemptions"),
        (190, "helv", "Bioequivalence studies follow 21 CFR 320.31."),
        (220, "hebo", "III. DISCUSSION"),
        (240, "hebo", "C. Out of Sequence"),
        (260, "helv", "A heading that skips its first sibling stays body text."),
        (750, "helv", "2"),
    ],
]


def build() -> bytes:
    document = pymupdf.open()
    for lines in PAGES:
        page = document.new_page(width=612, height=792)
        for y, font, text in lines:
            page.insert_text((72, y), text, fontname=font, fontsize=11)
    data: bytes = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    return data


if __name__ == "__main__":
    (Path(__file__).parent / "guidance.pdf").write_bytes(build())
