from fda_copilot.retrieval.hybrid import fuse


def test_fusion_ranks_rows_found_by_both_lists_first() -> None:
    keyword = ["21 CFR 312.32(c)(1)", "21 CFR 312.33", "21 CFR 312.40(b)(1)"]
    vector = ["21 CFR 312.40(b)(1)", "21 CFR 312.32(c)(1)", "21 CFR 812.150(a)(1)"]

    assert [citation for citation, _ in fuse([keyword, vector])] == [
        "21 CFR 312.32(c)(1)",
        "21 CFR 312.40(b)(1)",
        "21 CFR 312.33",
        "21 CFR 812.150(a)(1)",
    ]


def test_fusion_scores_are_summed_reciprocal_ranks() -> None:
    assert fuse([["a", "b"], ["b"]], k=1) == [("b", 1 / 3 + 1 / 2), ("a", 1 / 2)]


def test_fusion_breaks_score_ties_by_citation() -> None:
    assert [
        c
        for c, _ in fuse([["21 CFR 58.33", "21 CFR 58.15(b)"], ["21 CFR 58.15(b)", "21 CFR 58.33"]])
    ] == [
        "21 CFR 58.15(b)",
        "21 CFR 58.33",
    ]
