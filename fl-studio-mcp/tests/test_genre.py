"""fl_genre packs + chord theory (offline)."""

import pytest

from fl_studio_mcp.tools import genre_v2 as g
from fl_studio_mcp.utils import chords as ch

N = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def names(midis):
    return [N[m % 12] for m in midis]


@pytest.mark.parametrize("key,num,q,want", [
    ("A minor", "i", "triad", ["A", "C", "E"]),
    ("A minor", "VI", "triad", ["F", "A", "C"]),
    ("G minor", "V", "triad", ["D", "F#", "A"]),          # borrowed major dominant
    ("D dorian", "i9", "9", ["D", "F", "A", "C", "E"]),
    ("D dorian", "IV9", "9", ["G", "B", "D", "F", "A"]),
    ("C major", "V7", "7", ["G", "B", "D", "F"]),
    ("C major", "vii°", "triad", ["B", "D", "F"]),
])
def test_chords_follow_theory(key, num, q, want):
    assert names(ch.voice(ch.chord_pcs(key, num, q), 4)) == want


def test_bass_is_roots_low():
    b = ch.bass_notes("A minor", ["i", "VI"], 2, "sustain", 2)
    assert [n["midi"] for n in b] == [45, 41] and all(n["midi"] < 48 for n in b)


def test_every_pack_is_valid_and_plans():
    packs = g.list_packs()
    assert {p["id"] for p in packs} >= {"trap", "drill", "boom-bap", "lofi", "house", "techno",
                                        "reggaeton", "drum-and-bass", "dubstep", "hip-hop", "future-bass",
                                        "rnb", "pop", "afrobeats", "phonk", "punjabi"}
    from fl_studio_mcp.preset_paths import resolve_preset
    for p in packs:
        pack = g.load_pack(p["id"])
        assert "convention" in pack["status"]
        data, err = resolve_preset("beats", pack["beat"], "")  # beat preset exists
        assert err is None and data, (pack["id"], err)
        chords, bass = g.plan_notes(pack)
        bars = pack["bars"]
        assert chords and bass
        assert max(n["time"] + n["duration"] for n in chords) <= bars * 4 + 1e-6
        assert all(0 < n["midi"] < 128 for n in chords + bass)


def test_dry_run_needs_no_fl():
    r = g.fl_genre("load", genre="house", dry_run=True)
    assert r["success"] and r["dry_run"] and "124 BPM" in r["plan"][0]


def test_unknown_genre_lists_available():
    r = g.fl_genre("show", genre="polka")
    assert not r["success"] and "trap" in r["error"]


# ------------------------------------------------------------- chord symbols (tip 4)

@pytest.mark.parametrize("sym,want", [
    ("Am", ["A", "C", "E"]), ("F", ["F", "A", "C"]), ("Cmaj7", ["C", "E", "G", "B"]),
    ("Fm9", ["F", "G#", "C", "D#", "G"]), ("G7sus4", ["G", "C", "D", "F"]),
    ("Bm7b5", ["B", "D", "F", "A"]), ("F#m", ["F#", "A", "C#"]), ("Ebmaj7", ["D#", "G", "A#", "D"]),
])
def test_chord_symbols(sym, want):
    root, ints, _ = ch.parse_symbol(sym)
    assert names([60 + root + i for i in ints]) == want


def test_progression_text_and_slash_bass():
    assert ch.split_symbols("Am - F | C, G") == ["Am", "F", "C", "G"]
    notes = ch.symbol_notes("C/E G", beats_per_chord=2)
    first = [n for n in notes if n["time"] == 0]
    assert min(n["midi"] for n in first) == 52            # E3 = the slash bass
    assert {n["time"] for n in notes} == {0, 2}


def test_bad_chord_symbol_is_refused():
    with pytest.raises(ValueError):
        ch.parse_symbol("Hmaj7")
    with pytest.raises(ValueError):
        ch.parse_symbol("Cblorp")


def test_write_chords_becomes_write_steps(monkeypatch):
    """write_chords converts text -> notes and takes the write_steps path."""
    import fl_studio_mcp.tools.notes_v2 as nv
    seen = {}
    real_validate = nv._validate

    def spy(action, params):
        seen["action"], seen["n"] = action, len(params.get("notes") or [])
        return ["stop here (test)"]
    monkeypatch.setattr(nv, "_validate", spy)
    r = nv.fl_notes("write_chords", text="Am F C G", channel_index=5)
    assert seen == {"action": "write_steps", "n": 16} and not r["success"]
    monkeypatch.setattr(nv, "_validate", real_validate)
    assert not nv.fl_notes("write_chords", text="")["success"]


def test_enharmonic_roots():
    assert ch.parse_symbol("Cb")[0] == 11 and ch.parse_symbol("E#m")[0] == 5


# ------------------------------------------------------------- score log capture (tip 8)

class _Conn:
    def __init__(self, script):
        self.script = list(script)

    def send_command(self, action, params, timeout=None):
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _ok(v):
    return {"success": True, "stdout": f"{v}\n"}


def test_capture_success_needs_an_undo_step(monkeypatch):
    from fl_studio_mcp.utils import score_log as sl
    from fl_studio_mcp.utils import ui_guard as g
    monkeypatch.setattr(g, "fl_window_titles", lambda: ["FL Studio 2026"])
    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    r = sl.capture(_Conn([_ok(4), _ok(1), _ok(5)]), 30)          # undo 4 -> 5
    assert r["success"] and r["undo_delta"] == 1
    r = sl.capture(_Conn([_ok(4), _ok(1), _ok(4)]), 30)          # nothing happened
    assert not r["success"] and r["empty"]


def test_capture_timeout_means_warning_and_is_dismissed(monkeypatch):
    import fl_studio_mcp.tools.lifecycle_v2 as lc
    from fl_studio_mcp.utils import score_log as sl
    from fl_studio_mcp.utils import ui_guard as g
    monkeypatch.setattr(g, "fl_window_titles", lambda: ["FL Studio 2026"])   # no OS window!
    monkeypatch.setattr(g, "wait_for_front", lambda **k: {"front": True})
    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    called = {}
    monkeypatch.setattr(lc, "_action_dismiss_modal",
                        lambda t, k, a: called.setdefault("t", t) and {"success": True})
    r = sl.capture(_Conn([_ok(4), RuntimeError("Timeout waiting for FL Studio response")]), 1)
    assert not r["success"] and r["empty"] and called["t"] == "Warning"
