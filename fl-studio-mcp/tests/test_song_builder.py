import pytest

from fl_studio_mcp.tools.song_builder import expand_steps, melody_to_notes, parse_note


def test_parse_note():
    assert parse_note("A4") == 69
    assert parse_note("C#5") == 73
    assert parse_note("Bb3") == 58
    assert parse_note(60) == 60
    assert parse_note("-") is None
    with pytest.raises(ValueError):
        parse_note("H9")


def test_expand_steps_per_bar_and_repeat():
    row = expand_steps([[1, 7, 12], [1, 8, 11], [1, 7, 15], [1, 6, 11]], 4)
    assert len(row) == 64 and sum(row) == 12
    assert row[0] and row[16] and row[23] and row[58]
    assert sum(expand_steps([1, 3, 5], 4)) == 12
    assert sum(expand_steps(None, 4)) == 0


def test_expand_steps_errors():
    with pytest.raises(ValueError):
        expand_steps([[1], [2], [3]], 2)          # more lists than bars
    with pytest.raises(ValueError):
        expand_steps([17], 4)


def test_melody_to_notes_timing_and_rests():
    notes = melody_to_notes([["A4", "-"], ["C5"]], 0.5, None, 0.8)
    assert [(n["midi"], n["time"], n["duration"]) for n in notes] == [(69, 0.0, 0.5), (72, 4.0, 0.5)]


def test_scan_presets_finds_name_and_walks_back():
    from fastmcp import FastMCP

    from fl_studio_mcp.tools import plugins
    from fl_studio_mcp.utils import connection

    bank = ["PAD A", "LEAD B", "ACOUSTIC GUITAR", "BASS D"]
    state = {"i": 0, "calls": []}

    class Fake:
        def send_command(self, action, params=None, timeout=2.0):
            state["calls"].append(action)
            if action == "plugins.getPresetCount":
                return {"count": len(bank)}
            if action == "probe.exec":
                return {"stdout": bank[state["i"]] + "\n"}
            if action == "plugins.nextPreset":
                state["i"] = (state["i"] + 1) % len(bank)
                return {}
            if action == "plugins.prevPreset":
                state["i"] = (state["i"] - 1) % len(bank)
                return {}
            return {"error": "unknown"}

    plugins._STEP_PAUSE = 0
    connection.get_connection = lambda: Fake()
    mcp = FastMCP("t")
    plugins.register_plugin_tools(mcp)
    import asyncio
    find = asyncio.run(mcp.get_tool("fl_find_preset")).fn
    r = find(index=5, query="guitar")
    assert r["found"] and r["match"] == "ACOUSTIC GUITAR" and r["steps_from_start"] == 2 and r["selected"]
    state["i"] = 0
    r = find(index=5, query="banjo")
    assert not r["found"] and state["i"] == 0 and r["returned_to_start"]


def test_melody_chord_entries():
    notes = melody_to_notes([[["C4", "E4", "G4"], "-", "A4"]], 1.0, 4.0, 0.7)
    assert [(n["midi"], n["time"], n["duration"]) for n in notes] == [
        (60, 0.0, 4.0), (64, 0.0, 4.0), (67, 0.0, 4.0), (69, 2.0, 4.0)]


def test_expand_steps_cycle_repeats_and_truncates():
    row = expand_steps([[1], [5]], 5)             # 2-bar cycle over 5 bars: 1,5,1,5,1
    assert len(row) == 80
    assert [i for i, x in enumerate(row) if x] == [0, 20, 32, 52, 64]


def test_melody_hold_and_cycle():
    notes = melody_to_notes([["C2", "~", "~", "-"], ["G1", "-", "-", "-"]], 0.25, 0.25, 0.9, bars=4)
    got = [(n["midi"], n["time"], n["duration"]) for n in notes]
    assert got == [(36, 0.0, 0.75), (31, 4.0, 0.25), (36, 8.0, 0.75), (31, 12.0, 0.25)]
    with pytest.raises(ValueError):
        melody_to_notes([["C2"], ["C2"], ["C2"]], 0.25, None, 0.9, bars=2)


def test_write_notes_file_registered_and_validates(tmp_path):
    import asyncio

    from fastmcp import FastMCP

    from fl_studio_mcp.tools import song_builder

    mcp = FastMCP("t")
    song_builder.register_song_builder_tools(mcp)
    tool = asyncio.run(mcp.get_tool("fl_write_notes_file")).fn
    bad = tmp_path / "bad.json"
    bad.write_text('[{"midi": 36}]')
    assert "needs midi" in tool(str(bad), 4)["error"]
    assert "cannot read" in tool(str(tmp_path / "missing.json"), 4)["error"]
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    assert not tool(str(empty), 4)["ok"]
