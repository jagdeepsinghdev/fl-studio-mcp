"""Sprint S: S2 wrench point, S3 clear_queue, S7 friendlier inputs."""
import json
from pathlib import Path
from unittest import mock

import pytest

from fl_studio_mcp.tools import channel_v2, notes_v2
from fl_studio_mcp.tools.select_script import wrench_point_from_boxes
from fl_studio_mcp.utils.roll_session import parse_ocr_boxes

FIX = Path(__file__).parent / "fixtures" / "roll_title"
CHANNELS = ["808 Kick", "808 Clap", "808 HiHat", "808 Snare", "808 Astronomic",
            "Bells", "Pad", "Discord", "Riser"]


# ---- S2 ----
@pytest.mark.parametrize("fixture", ["bells", "pad", "riser", "discord",
                                     "808-astronomic-truncated"])
def test_wrench_point_from_fixture(fixture):
    pt = wrench_point_from_boxes(parse_ocr_boxes((FIX / f"{fixture}.txt").read_text()),
                                 CHANNELS)
    assert pt is not None and not pt["docked"]
    assert abs(pt["y"] - 178) <= 6
    assert abs(pt["x"] - 768) <= 6


@pytest.mark.parametrize("fixture", ["playlist-front-no-roll", "roll-closed-playlist"])
def test_wrench_refuses_without_roll_title(fixture):
    assert wrench_point_from_boxes(
        parse_ocr_boxes((FIX / f"{fixture}.txt").read_text()), CHANNELS) is None


def test_wrench_docked_title():
    b = [{"x": 1363, "y": 100, "w": 200, "h": 14, "text": "Piano roll - 808 Kick"}]
    pt = wrench_point_from_boxes(b, CHANNELS)
    assert pt["docked"] and pt["y"] == 107 and pt["x"] == 1363 - 332


# ---- S3 ----
def test_clear_queue_backs_up_and_empties(tmp_path):
    f = tmp_path / "mcp_request.json"
    f.write_text(json.dumps([{"action": "clear"}, {"action": "add_notes", "notes": []}]))
    with mock.patch("fl_studio_mcp.tools.piano_roll._get_request_file", return_value=f):
        r = notes_v2.fl_notes("clear_queue")
        r2 = notes_v2.fl_notes("clear_queue")
    assert r["success"] and r["dropped"] == 2
    assert json.loads(Path(r["backup"]).read_text())[0] == {"action": "clear"}
    assert json.loads(f.read_text()) == []
    assert r2["dropped"] == 0 and r2["backup"] != r["backup"]


def test_clear_queue_no_file(tmp_path):
    f = tmp_path / "mcp_request.json"
    with mock.patch("fl_studio_mcp.tools.piano_roll._get_request_file", return_value=f):
        r = notes_v2.fl_notes("clear_queue")
    assert r["dropped"] == 0 and r["backup"] is None and f.read_text() == "[]"


# ---- S7 ----
def test_bars_kick_roundtrip():
    p = {"index": 0, "bars": [[1, 7], [1, 13], [1, 7], [1, 7, 13]]}
    assert channel_v2.validate("set_steps", p) == []
    row = p["steps"]
    assert len(row) == 64
    assert [i for i, v in enumerate(row) if v] == [0, 6, 16, 28, 32, 38, 48, 54, 60]


def test_bars_cycle_and_conflicts():
    p = {"index": 0, "bars": [[1], [5]], "n_bars": 4}
    assert channel_v2.validate("set_steps", p) == []
    assert [i for i, v in enumerate(p["steps"]) if v] == [0, 20, 32, 52]
    assert channel_v2.validate("set_steps", {"index": 0, "steps": [True], "bars": [[1]]})
    assert channel_v2.validate("set_steps", {"index": 0})
    assert channel_v2.validate("set_steps", {"index": 0, "bars": [[17]]})
    assert channel_v2.validate("set_steps", {"index": 0, "steps": [True, False]}) == []


def test_melody_roundtrip():
    p = {"melody": [["C#4", "G#4", "C#5", "G#4", "E5", "G#4", "C#5", "G#4"]],
         "step_beats": 0.5}
    assert notes_v2._melody_to_params(p) is None
    assert [n["midi"] for n in p["notes"]] == [61, 68, 73, 68, 76, 68, 73, 68]
    assert [n["time"] for n in p["notes"]] == [0, .5, 1, 1.5, 2, 2.5, 3, 3.5]


def test_melody_holds_chords_and_errors():
    p = {"melody": [[["C4", "E4"], "~", "-", "G4"]], "step_beats": 1, "velocity": 0.5}
    assert notes_v2._melody_to_params(p) is None
    assert [(n["midi"], n["duration"]) for n in p["notes"]] == [(60, 2), (64, 2), (67, 1)]
    assert notes_v2._melody_to_params({"melody": [["H9"]]})
    r = notes_v2.fl_notes("write_steps", melody=[["C4"]], notes=[{"midi": 60, "duration": 1}],
                          open_roll_verified=True)
    assert not r["success"] and "not both" in r["error"]
