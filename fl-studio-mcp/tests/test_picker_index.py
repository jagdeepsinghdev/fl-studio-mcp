"""picker_index: OCR-tolerant matching + overlap merge (offline)."""
from fl_studio_mcp.utils import picker_index as pi


def test_match_tolerates_ocr_but_not_digits():
    assert pi._match("Fruity Parametric E02", "Fruity Parametric EQ 2")
    assert not pi._match("Fruity Parametric EQ", "Fruity Parametric EQ 2")
    assert not pi._match("Fruity Delay 2", "Fruity Delay 3")
    assert not pi._match("Patcher", "Pitcher")


def test_merge_skips_only_the_overlap():
    page1 = ["Maximus", "Patcher", "Pitch Shifter", "Pitcher"]
    page2 = ["Patcher", "Pitch Shifter", "Pitcher", "Soundgoodizer", "Fruity Delay 2", "Fruity Delay 3"]
    out = pi.merge(page1, page2)
    assert out == ["Maximus", "Patcher", "Pitch Shifter", "Pitcher", "Soundgoodizer",
                   "Fruity Delay 2", "Fruity Delay 3"]


def test_merge_absorbs_misread_overlap():
    page1 = ["Fruity Parametric EQ", "Fruity Parametric E02"]
    page2 = ["Fruity Parametric EQ", "truity Parametric EU2", "Fruity Reeverb 2"]
    assert pi.merge(page1, page2) == ["Fruity Parametric EQ", "Fruity Parametric E02", "Fruity Reeverb 2"]


def test_merge_overlap_with_one_misread_row():
    page1 = ["Fruity Phaser", "Fruity Reeverb", "Fruity Reeverb 2", "Fruity Scratcher", "Fruity Send"]
    page2 = ["Fruity Reeverb", "Fruity Reeverb 2", "Fruitv Scratchar", "Fruity Send", "Fruity Soft Clipper"]
    assert pi.merge(page1, page2) == page1 + ["Fruity Soft Clipper"]


def test_wrap_to_top_is_detected():
    order = ["Control Surface", "Distructor", "Edison", "Effector", "Emphasis", "Emphasizer",
             "EQUO", "Frequency Shifter", "Frequency Splitter", "Fruity 7 Band EQ", "Maximus",
             "Patcher", "Pitcher", "Soundgoodizer", "Vocodex", "Wave Candy"]
    top_again = ["Control Surface", "Distructor", "Edison", "Effector", "Emphasis"]
    assert pi.wrapped(order, top_again)
    assert not pi.wrapped(order, ["Soundgoodizer", "Vocodex", "Wave Candy", "Youlean"])
