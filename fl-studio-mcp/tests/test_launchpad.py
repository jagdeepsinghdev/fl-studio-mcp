"""Tests for fl_launchpad (LP grid ↔ step-sequencer bridge).

All file access is monkeypatched to a tmp dir; no FL, no MIDI, no real
hardware directory. The pure mapping math is the heart of the tool.
"""
import json

import pytest

from fl_studio_mcp.tools import launchpad as lp


@pytest.fixture(autouse=True)
def _tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "HARDWARE_DIR", tmp_path)
    monkeypatch.setattr(lp, "MAPPING_FILE", tmp_path / "lp_mapping.json")
    monkeypatch.setattr(lp, "STATE_FILE", tmp_path / "lp_state.json")
    monkeypatch.setattr(lp, "INPUT_LOG", tmp_path / "input_notes.jsonl")
    yield tmp_path


# ---------------------------------------------------------------------------
# pure mapping math
# ---------------------------------------------------------------------------


def test_pad_to_cell_row_major():
    assert lp.pad_to_cell(0, 0, 8, 8) == (0, 0)
    assert lp.pad_to_cell(7, 0, 8, 8) == (0, 7)
    assert lp.pad_to_cell(8, 0, 8, 8) == (1, 0)
    assert lp.pad_to_cell(63, 0, 8, 8) == (7, 7)
    assert lp.pad_to_cell(64, 0, 8, 8) is None
    assert lp.pad_to_cell(-1, 0, 8, 8) is None


def test_pad_to_cell_offset_first_note():
    # MK1-style grids start at 36
    assert lp.pad_to_cell(36, 36, 8, 8) == (0, 0)
    assert lp.pad_to_cell(99, 36, 8, 8) == (7, 7)
    assert lp.pad_to_cell(35, 36, 8, 8) is None


def test_cell_to_pad_inverse():
    for note in (0, 7, 8, 55, 63):
        cell = lp.pad_to_cell(note, 0, 8, 8)
        assert lp.cell_to_pad(*cell, 0, 8) == note


def test_resolve_target_pattern_row_first():
    m = {"rows": 8, "cols": 8, "first_note": 0,
         "pattern_row": 0, "channels": [0, 1, 2, 3]}
    assert lp.resolve_target((0, 0), m) == ("pattern", 1, 0)
    assert lp.resolve_target((0, 7), m) == ("pattern", 8, 0)


def test_resolve_target_step_rows_skip_pattern_row():
    m = {"rows": 8, "cols": 8, "first_note": 0,
         "pattern_row": 0, "channels": [10, 20, 30]}
    # row 1 -> channels[0] (first non-pattern row)
    assert lp.resolve_target((1, 3), m) == ("step", 10, 3)
    assert lp.resolve_target((2, 0), m) == ("step", 20, 0)
    assert lp.resolve_target((3, 5), m) == ("step", 30, 5)
    with pytest.raises(ValueError):
        lp.resolve_target((4, 0), m)  # only 3 channels mapped


def test_resolve_target_pattern_row_not_zero():
    m = {"rows": 4, "cols": 4, "first_note": 0,
         "pattern_row": 3, "channels": [0, 1, 2]}
    assert lp.resolve_target((3, 2), m) == ("pattern", 3, 0)
    assert lp.resolve_target((0, 0), m) == ("step", 0, 0)
    assert lp.resolve_target((2, 1), m) == ("step", 2, 1)


def test_note_to_action_only_note_on_with_velocity():
    m = {"rows": 8, "cols": 8, "first_note": 0,
         "pattern_row": 0, "channels": [0, 1]}
    assert lp.note_to_action({"status": 0x90, "note": 5, "vel": 0}, m) is None
    assert lp.note_to_action({"status": 0x80, "note": 5, "vel": 0}, m) is None
    assert lp.note_to_action({"status": 0x90, "note": 200, "vel": 100}, m) is None
    # note 13 = row 1 (first step row), col 5 → channels[0]=0, step 5
    a = lp.note_to_action({"status": 0x90, "note": 13, "vel": 100}, m)
    assert a == {"kind": "step", "channel": 0, "step": 5}
    # note 2 = row 0 = pattern row, col 2 → pattern 3 (1-based)
    p = lp.note_to_action({"status": 0x90, "note": 2, "vel": 100}, m)
    assert p == {"kind": "pattern", "pattern": 3}


# ---------------------------------------------------------------------------
# persistence + actions (tmp files)
# ---------------------------------------------------------------------------


def test_map_persists_and_status_reports(tmp_path):
    out = lp.fl_launchpad("map", rows=4, cols=4, first_note=36,
                          pattern_row=0, channels=[0, 1])
    assert out["success"]
    m = json.loads((tmp_path / "lp_mapping.json").read_text())
    assert m["rows"] == 4 and m["first_note"] == 36
    st = lp.fl_launchpad("status")
    assert st["mapping"]["rows"] == 4
    assert st["input_log"]["exists"] is False
    assert st["pending_note_ons"] == 0


def test_calibrate_anchors_first_note(tmp_path):
    log = tmp_path / "input_notes.jsonl"
    log.write_text(
        json.dumps({"ts": 1, "status": 0x90, "note": 36, "vel": 100}) + "\n"
        + json.dumps({"ts": 2, "status": 0x80, "note": 36, "vel": 0}) + "\n"
        + json.dumps({"ts": 3, "status": 0x90, "note": 54, "vel": 60}) + "\n")
    out = lp.fl_launchpad("calibrate")
    assert out["success"]
    assert out["first_note"] == 54  # last note-ON wins
    m = json.loads((tmp_path / "lp_mapping.json").read_text())
    assert m["first_note"] == 54


def test_calibrate_with_no_input_fails_cleanly(tmp_path):
    out = lp.fl_launchpad("calibrate")
    assert out["success"] is False
    assert "no note-ONs" in out["error"]


def test_pending_count_counts_only_grid_note_ons(tmp_path):
    lp.fl_launchpad("map", rows=8, cols=8, first_note=0,
                    pattern_row=0, channels=[0, 1])
    log = tmp_path / "input_notes.jsonl"
    log.write_text(
        json.dumps({"status": 0x90, "note": 3, "vel": 100}) + "\n"   # pad
        + json.dumps({"status": 0x80, "note": 3, "vel": 0}) + "\n"   # release
        + json.dumps({"status": 0x90, "note": 200, "vel": 100}) + "\n"  # off-grid
    )
    st = lp.fl_launchpad("status")
    assert st["pending_note_ons"] == 1


def test_status_with_input_log(tmp_path):
    (tmp_path / "input_notes.jsonl").write_text("{}\n")
    st = lp.fl_launchpad("status")
    assert st["input_log"]["exists"] is True
    assert st["input_log"]["bytes"] >= 0


def test_unknown_action_lists_valid(tmp_path):
    out = lp.fl_launchpad("warp")
    assert out["success"] is False
    assert set(out["valid_actions"]) == set(lp.ACTIONS)


def test_map_ignores_none_kwargs(tmp_path):
    # the MCP gateway passes every declared param (None when omitted)
    out = lp.fl_launchpad("map", rows=None, cols=None, first_note=None,
                          pattern_row=None, channels=[0, 1])
    assert out["success"]
    m = json.loads((tmp_path / "lp_mapping.json").read_text())
    assert m["rows"] == 8 and m["channels"] == [0, 1]
