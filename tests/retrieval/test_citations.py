from fda_copilot.retrieval.citations import resolve

TEXTS = {
    "21 CFR 56.111(a)": "(a) In order to approve research covered by these regulations the IRB "
    "shall determine that all of the following requirements are satisfied:",
    "21 CFR 56.111(a)(1)": "(1) Risks to subjects are minimized: (i) By using procedures which are "
    "consistent with sound research design and which do not unnecessarily expose subjects to "
    "risk, and (ii) whenever appropriate, by using procedures already being performed on the "
    "subjects for diagnostic or treatment purposes.",
    "21 CFR 312.32(b)": "(b) Review of safety information. The sponsor must promptly review all "
    "information relevant to the safety of the drug.",
    "21 CFR 312.32(c)(1)": "(c)(1) IND safety reports. The sponsor must notify FDA and all "
    "participating investigators in an IND safety report of potential serious risks.",
    "21 CFR 312.32(c)(1)(i)": "(i) Serious and unexpected suspected adverse reaction.",
    "21 CFR 312.32(c)(2)": "(2) Unexpected fatal or life-threatening suspected adverse reaction "
    "reports.",
    "21 CFR 312.30": "Once an IND is in effect, a sponsor shall amend it as needed. A change under "
    "paragraph (b) of this section is a protocol amendment.",
    "21 CFR 312.30(b)(1)": "(b) Changes in a protocol. (1) A sponsor shall submit a protocol "
    "amendment describing any change in a Phase 2 or 3 protocol.",
    "21 CFR 312.110(b)(2)": "(2) The drug has valid marketing authorization in Australia, and "
    "complies with the laws of the country to which it is being exported, section 802(b)(1)(A), "
    "(f), and (g) of the act, and § 1.101 of this chapter; or",
    "21 CFR 312.42(b)(4)(i)": "(i) Any of the conditions in paragraph (b)(1) or (b)(2) of this "
    "section apply; or",
    "21 CFR 312.8(d)(3)": "(3) To support its calculation for cost recovery, a sponsor must "
    "provide supporting documentation to show that the calculation is consistent with the "
    "requirements of paragraphs (d)(1) and, if applicable, (d)(2) of this section.",
    "21 CFR 58.43(a)": "(a) A testing facility shall have a sufficient number of animal rooms or "
    "areas, as needed, to assure proper: (1) Separation of species or test systems, (2) isolation "
    "of individual projects, (3) quarantine of animals, and (4) routine or specialized housing of "
    "animals.",
    "ICH E6(R3) 2.8.7": "2.8.7 Prior to trial participation, the informed consent form should be "
    "signed and dated by the participant.",
}


def test_a_stored_citation_resolves_to_its_own_row() -> None:
    assert resolve("21 CFR 312.32(c)(1)", TEXTS) == ("21 CFR 312.32(c)(1)",)


def test_an_inline_sub_paragraph_resolves_to_the_row_that_holds_its_marker() -> None:
    assert resolve("21 CFR 56.111(a)(1)(i)", TEXTS) == ("21 CFR 56.111(a)(1)",)
    assert resolve("21 CFR 56.111(a)(1)(ii)", TEXTS) == ("21 CFR 56.111(a)(1)",)
    assert resolve("21 CFR 58.43(a)(2)", TEXTS) == ("21 CFR 58.43(a)",)
    assert resolve("21 CFR 58.43(a)(4)", TEXTS) == ("21 CFR 58.43(a)",)


def test_a_parent_stored_in_its_first_child_resolves_to_its_children() -> None:
    assert resolve("21 CFR 312.32(c)", TEXTS) == (
        "21 CFR 312.32(c)(1)",
        "21 CFR 312.32(c)(1)(i)",
        "21 CFR 312.32(c)(2)",
    )


def test_a_cross_reference_in_an_ancestor_is_not_a_paragraph_marker() -> None:
    assert resolve("21 CFR 312.30(b)", TEXTS) == ("21 CFR 312.30(b)(1)",)


def test_an_item_in_a_cross_reference_list_is_not_a_paragraph_marker() -> None:
    assert resolve("21 CFR 312.110(b)(2)(f)", TEXTS) == ()
    assert resolve("21 CFR 312.110(b)(2)(g)", TEXTS) == ()
    assert resolve("21 CFR 312.42(b)(4)(i)(b)", TEXTS) == ()
    assert resolve("21 CFR 312.8(d)(3)(2)", TEXTS) == ()


def test_a_guidance_section_resolves_to_its_numbered_children() -> None:
    assert resolve("ICH E6(R3) 2.8", TEXTS) == ("ICH E6(R3) 2.8.7",)


def test_a_section_number_prefix_is_not_a_parent() -> None:
    assert resolve("21 CFR 312.3", TEXTS) == ()
    assert resolve("21 CFR 56.111(a)(1)(iii)", TEXTS) == ()


def test_a_row_own_marker_is_not_a_sub_paragraph_of_itself() -> None:
    assert resolve("21 CFR 56.111(a)(1)(1)", TEXTS) == ()
    assert resolve("21 CFR 58.43(a)(a)", TEXTS) == ()
