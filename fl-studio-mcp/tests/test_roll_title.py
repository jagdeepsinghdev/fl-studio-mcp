"""S1: roll-title detection on real OCR fixtures (floating + docked roll)."""
from pathlib import Path

import pytest

from fl_studio_mcp.utils.roll_session import parse_ocr_boxes, roll_title_from_boxes

FIX = Path(__file__).parent / "fixtures" / "roll_title"
CHANNELS = ["808 Kick", "808 Clap", "808 HiHat", "808 Snare", "808 Astronomic",
            "Bells", "Pad", "Discord", "Riser"]


def _boxes(name):
    return parse_ocr_boxes((FIX / name).read_text())


@pytest.mark.parametrize("fixture,expected", [
    ("bells.txt", "Bells"),
    ("808-astronomic-truncated.txt", "808 Astronomic"),
    ("pad.txt", "Pad"),
    ("riser.txt", "Riser"),
    ("discord.txt", "Discord"),
    ("playlist-front-no-roll.txt", None),
    ("roll-closed-playlist.txt", None),
])
def test_fixture_titles(fixture, expected):
    assert roll_title_from_boxes(_boxes(fixture), CHANNELS) == expected


def _b(x, y, text, w=60, h=12):
    return {"x": x, "y": y, "w": w, "h": h, "text": text}


def test_docked_form():
    assert roll_title_from_boxes([_b(500, 10, "Piano roll - 808 Kick")],
                                 CHANNELS) == "808 Kick"


def test_ambiguous_truncation_is_none():
    assert roll_title_from_boxes([_b(1000, 170, "808 …› - • x")],
                                 CHANNELS) is None
    # even a long-enough prefix that fits several channels is refused
    assert roll_title_from_boxes([_b(1000, 170, "808 .› - • x")],
                                 CHANNELS) is None


def test_plugin_title_alone_is_none():
    assert roll_title_from_boxes([_b(900, 100, "Bells (Insert 6)")], CHANNELS) is None
    assert roll_title_from_boxes([_b(900, 100, "Insert 6")], CHANNELS) is None


def test_rack_only_is_none():
    rack = [_b(125, 170, "808 Kick"), _b(125, 199, "808 Clap"),
            _b(109, 287, "808 Astronomic", 77), _b(136, 317, "Bells", 27),
            _b(137, 347, "Pad", 21)]
    assert roll_title_from_boxes(rack, CHANNELS) is None


def test_name_ending_in_x_is_kept():
    assert roll_title_from_boxes([_b(1000, 170, "Sax •")], ["Sax", "Kick"]) == "Sax"


@pytest.mark.parametrize("seen", ["Keysr", "Keys y", "Keys h"])
def test_title_with_ocr_icon_tail(seen):
    """Live 2026-10-11: the floating 'Keys •' title OCR'd as 'Keysr' / 'Keys y' -> chain refused."""
    assert roll_title_from_boxes([_b(900, 300, seen)], ["Keys", "Kick AFRO", "Guitar"]) == "Keys"


def test_icon_tail_never_picks_between_two_names():
    # 'Keys 2' exists: 'Keys 2x' must not resolve to plain 'Keys'
    assert roll_title_from_boxes([_b(900, 300, "Keys 2x")], ["Keys", "Keys 2"]) == "Keys 2"


@pytest.mark.parametrize("seen", ["Piano roll - Bass r", "Piano roll - Bassr", "Piano roll - Bass"])
def test_docked_title_with_ocr_icon_tail(seen):
    """Live 2026-10-11: the DOCKED title 'Piano roll - Bass' OCR'd as '... Bass r' -> write refused."""
    assert roll_title_from_boxes([_b(500, 10, seen)], ["Bass", "Keys", "Nylon Guitar"]) == "Bass"
