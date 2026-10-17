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
    return _bytes(document)


HEADER = "Guidance on Nonclinical Safety Studies"
TABLE = [
    [("Dose to be", "Administered"), ("Start and", "Maximum Doses")],
    [("Total dose", "under 100 ug"), ("Maximal and", "starting doses")],
]


def build_rotated() -> bytes:
    document = pymupdf.open()
    for number, heading in [(1, "1. INTRODUCTION"), (2, None), (3, "2. SCOPE")]:
        page = document.new_page(width=612, height=792)
        if heading is None:
            page.set_rotation(90)
        _upright_text(page, 72, 78, HEADER)
        _upright_text(page, 300, page.rect.height - 40, str(number))
        if heading is not None:
            _upright_text(page, 72, 140, heading, "hebo")
            _upright_text(page, 72, 160, f"Body of {heading.split()[1].lower()}.")
            continue
        for row, cells in enumerate(TABLE):
            for col, lines in enumerate(cells):
                left, top = 72 + col * 200, 140 + row * 50
                cell = pymupdf.Rect(left, top, left + 200, top + 50)
                page.draw_rect(cell * page.derotation_matrix)
                for i, line in enumerate(lines):
                    _upright_text(page, left + 6, top + 18 + i * 14, line)
    return _bytes(document)


def _upright_text(page: pymupdf.Page, x: float, y: float, line: str, font: str = "helv") -> None:
    at = pymupdf.Point(x, y) * page.derotation_matrix
    page.insert_text(at, line, fontname=font, fontsize=11, rotate=page.rotation)


def _bytes(document: pymupdf.Document) -> bytes:
    data: bytes = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    return data


if __name__ == "__main__":
    fixtures = Path(__file__).parent
    (fixtures / "guidance.pdf").write_bytes(build())
    (fixtures / "rotated.pdf").write_bytes(build_rotated())
