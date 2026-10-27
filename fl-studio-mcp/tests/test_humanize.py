"""Humanize helpers + the default-on wiring in fl_notes (no FL needed)."""
from fl_studio_mcp.utils import chords as ch
from fl_studio_mcp.utils.humanize import humanize_chords, humanize_melody


def _flat(text="Gm Eb Bb F"):
    return ch.symbol_notes(text, 4.0, 4, 0.7, True)


def test_chords_keep_pitches_and_count():
    flat, hum = _flat(), humanize_chords(_flat(), "Gm Eb Bb F")
    assert len(hum) == len(flat)
    assert sorted(n["midi"] for n in hum) == sorted(n["midi"] for n in flat)


def test_chords_bass_strongest_strum_up_and_shorter():
    hum = humanize_chords(_flat(), "x")
    first = sorted((n for n in hum if n["time"] < 1), key=lambda n: n["midi"])
    assert first[0]["velocity"] > max(n["velocity"] for n in first[1:])
    assert first[0]["time"] == 0.0
    assert [n["time"] for n in first] == sorted(n["time"] for n in first)
    assert all(n["duration"] < 4.0 for n in hum)
    assert all(0.3 <= n["velocity"] <= 1.0 for n in hum)


def test_deterministic():
    assert humanize_chords(_flat(), "s") == humanize_chords(_flat(), "s")


def test_melody_keeps_bar_starts_and_pitches():
    grid = [{"midi": 70 + i, "time": float(t), "duration": 0.5, "velocity": 0.8}
            for i, t in enumerate([0, 0.5, 1.0, 2.0, 2.75, 4.0, 4.5])]
    hum = humanize_melody(grid, "m")
    assert [n["midi"] for n in hum] == [n["midi"] for n in grid]
    for g, h in zip(grid, hum):
        if g["time"] % 4 == 0:
            assert h["time"] == g["time"]
        assert abs(h["time"] - g["time"]) <= 0.03
    assert hum[0]["velocity"] > hum[1]["velocity"]          # bar start accented vs off-beat


def test_write_chords_default_humanizes_and_off_switch(monkeypatch):
    import fl_studio_mcp.tools.notes_v2 as nv
    seen = {}

    def spy(action, params):
        seen["notes"] = params.get("notes")
        seen["has_flag"] = "humanize" in params
        return ["stop here (test)"]
    monkeypatch.setattr(nv, "_validate", spy)
    nv.fl_notes("write_chords", text="Am F C G", channel_index=5)
    assert len({n["velocity"] for n in seen["notes"]}) > 1 and not seen["has_flag"]
    nv.fl_notes("write_chords", text="Am F C G", channel_index=5, humanize=False)
    assert {n["velocity"] for n in seen["notes"]} == {0.7}


def test_explicit_notes_never_touched(monkeypatch):
    import fl_studio_mcp.tools.notes_v2 as nv
    seen = {}
    monkeypatch.setattr(nv, "_validate", lambda a, p: seen.update(n=p.get("notes"), f="humanize" in p) or ["stop"])
    notes = [{"midi": 60, "time": 0.0, "duration": 1.0, "velocity": 0.8}]
    nv.fl_notes("write_steps", notes=notes, channel_index=1)
    assert seen["n"] == notes and not seen["f"]
