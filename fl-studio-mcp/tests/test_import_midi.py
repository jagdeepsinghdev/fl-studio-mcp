"""C3 import_midi: fl_notes wiring + utils/import_midi helpers (all FL/UI mocked)."""

from __future__ import annotations

import mido
import pytest

from fl_studio_mcp.tools import notes_v2
from fl_studio_mcp.utils import import_midi as im
from fl_studio_mcp.utils import roll_session as rs


def test_write_midi_round_trips_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_MIDI_DIR", tmp_path)
    p = im.write_midi([{"midi": 67, "time": 0, "duration": 0.5, "velocity": 0.9},
                       {"midi": 74, "time": 1, "duration": 2, "velocity": 0.75}],
                      name="t 1/x", bpm=140)
    assert p.parent == tmp_path and p.name == "t-1-x.mid"
    mf = mido.MidiFile(str(p))
    ons = [m for m in mf.tracks[0] if m.type == "note_on" and m.velocity]
    assert [(m.note, m.velocity) for m in ons] == [(67, 114), (74, 95)]
    assert notes_v2._midi_note_count(p) == 2


def test_find_prefers_nearest_match():
    boxes = [{"text": "File", "cx": 100, "cy": 10}, {"text": "File", "cx": 1020, "cy": 237},
             {"text": "Import MIDI file...", "cx": 1222, "cy": 302}]
    assert im.find(boxes, r"^file$", near=(1010, 214))["cx"] == 1020
    assert im.find(boxes, r"import midi file")["cy"] == 302
    assert im.find(boxes, r"^file$", below_y=300) is None


class _Conn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "probe.patterns":
            return {"success": True, "active_pattern": 3}
        return {"success": True, "undo_saved": "u", "state_after": {}}


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_MIDI_DIR", tmp_path)
    calls = {"import": [], "roll": []}
    monkeypatch.setattr(im, "import_midi_file",
                        lambda ch, p: calls["import"].append((ch, p)) or
                        {"ok": True, "steps": ["imported"]})
    monkeypatch.setattr(rs, "open_roll_for_channel",
                        lambda ch: calls["roll"].append(ch) or {"ok": True})
    return calls


def _fake_readback(monkeypatch, count, fresh=True):
    from fl_studio_mcp.tools import state
    monkeypatch.setattr(state, "_read_piano_roll",
                        lambda fs, max_notes=None: {"note_count": count, "summary": {}})
    monkeypatch.setattr(rs, "ran_since", lambda before: fresh)


def test_import_from_notes_verifies_and_restores_pattern(ui, monkeypatch):
    _fake_readback(monkeypatch, 2)
    conn = _Conn()
    r = notes_v2.fl_notes("import_midi", conn=conn, channel_index=5, target_pattern=6,
                          notes=[{"midi": 60, "duration": 1}, {"midi": 64, "time": 1,
                                                               "duration": 1}])
    assert r["success"] and r["verified"] and r["expected_notes"] == 2
    assert ui["import"][0][0] == 5 and ui["roll"] == [5]
    selects = [p["pattern"] for a, p in conn.calls if a == "patterns.select"]
    assert selects[0] == 6 and selects[-1] == 3 and r["active_restored"] == 3


def test_import_unconfirmed_readback_is_a_failure(ui, monkeypatch):
    _fake_readback(monkeypatch, 0)
    r = notes_v2.fl_notes("import_midi", conn=_Conn(), channel_index=5,
                          notes=[{"midi": 60, "duration": 1}])
    assert r["success"] is False and "did not confirm" in r["error"]


def test_import_stale_state_file_is_not_trusted(ui, monkeypatch):
    _fake_readback(monkeypatch, 1, fresh=False)  # right count, but an OLD export
    r = notes_v2.fl_notes("import_midi", conn=_Conn(), channel_index=5,
                          notes=[{"midi": 60, "duration": 1}])
    assert r["success"] is False


def test_import_path_outside_work_dir_is_refused(ui, tmp_path):
    f = tmp_path / "x.mid"
    f.write_bytes(b"MThd")
    r = notes_v2.fl_notes("import_midi", conn=_Conn(), channel_index=5, path=str(f))
    assert r["success"] is False and "outside the work dir" in r["error"]
    assert ui["import"] == []


def test_ui_failure_is_reported_and_pattern_still_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "_MIDI_DIR", tmp_path)
    monkeypatch.setattr(im, "import_midi_file",
                        lambda ch, p: {"ok": False, "error": "Open panel did not appear",
                                       "steps": []})
    conn = _Conn()
    r = notes_v2.fl_notes("import_midi", conn=conn, channel_index=5, target_pattern=6,
                          notes=[{"midi": 60, "duration": 1}])
    assert r["success"] is False and "Open panel" in r["error"]
    assert [p["pattern"] for a, p in conn.calls if a == "patterns.select"][-1] == 3
