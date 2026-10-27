"""fl_preset — the always-on preset loader (list / load_beat / load_melody).

Covers: preset id listing (registry + .generated), the load_beat channel
resolution + clear pass + per-step param writes (S2.3) + optional tempo,
and the load_melody queue flow (step->time conversion, chord stacking,
the ComposeWithLLM request file). All FL access is mocked — no MIDI trips.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fl_studio_mcp import preset_paths  # noqa: E402
from fl_studio_mcp.tools import preset_v2 as pv2  # noqa: E402


class _RecConn:
    def __init__(self, channels=None):
        self.calls = []
        self._channels = channels if channels is not None else [
            {"index": 0, "name": "808 Kick"},
            {"index": 1, "name": "808 Snare"},
            {"index": 2, "name": "808 Clap"},
            {"index": 3, "name": "808 HiHat"},
            {"index": 4, "name": "FLEX Piano"},
        ]

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "channels.getAll":
            return {"success": True, "channels": self._channels}
        return {"success": True}


def _calls(conn, action):
    return [p for a, p in conn.calls if a == action]


PRESET = {
    "name": "test-beat",
    "bpm": 140,
    "channels": {
        "kick": {"name": "808 Kick",
                 "pattern": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                 "velocities": [120, 0, 0, 0, 64, 0, 0, 0, 110, 0, 0, 0, 70, 0, 0, 0]},
        "hat": {"name": "808 HiHat",
                "pattern": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                "shifts": [0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0],
                "repeats": [3, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0]},
        "ghost": {"name": "Nonexistent Drum",
                  "pattern": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
    },
}


class _PresetFixture:
    """Writes a preset into the .generated dir (work-dir restricted loader)
    and cleans it up."""

    def __init__(self, data, id_="pv2-test", kind="beats"):
        self.id = id_
        self.path = (preset_paths.work_root() / ".generated" / kind
                     / f"{id_}.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


class TestList(unittest.TestCase):
    def test_lists_registry_and_generated(self):
        with _PresetFixture(PRESET):
            r = pv2.preset_list("beats")
        self.assertTrue(r["ok"])
        self.assertIn("trap", r["presets"])          # registry
        self.assertIn("pv2-test", r["presets"])      # generated

    def test_bad_kind_refused(self):
        r = pv2.preset_list("drums")
        self.assertFalse(r["ok"])


class TestLoadBeat(unittest.TestCase):
    def _load(self, **kw):
        conn = _RecConn()
        with mock.patch.object(pv2, "get_connection", return_value=conn):
            r = pv2.load_beat(**kw)
        return r, conn

    def test_writes_sequence_and_step_params(self):
        with _PresetFixture(PRESET):
            r, conn = self._load(preset="pv2-test", target_pattern=2)
        self.assertTrue(r["ok"])
        # sequences: clear pass (5 drum-ish channels: kick/snare/clap/hat;
        # '808' matches all four) + 2 matched parts
        seqs = _calls(conn, "channels.setStepSequence")
        self.assertGreaterEqual(len(seqs), 6)
        # every write targets pattern 2
        self.assertTrue(all(p.get("target_pattern") == 2 for p in seqs))
        # kick (ch 0): velocities 120/64/110/70 at steps 0/4/8/12
        params = _calls(conn, "channels.setStepParameter")
        by = {(p["channel"], p["step"], p["param"]): p["value"] for p in params}
        self.assertEqual(by[(0, 0, "pVelocity")], 120)
        self.assertEqual(by[(0, 4, "pVelocity")], 64)
        self.assertEqual(by[(0, 8, "pVelocity")], 110)
        self.assertEqual(by[(0, 12, "pVelocity")], 70)
        # hat (ch 3): shifts at steps 3 and 8
        self.assertEqual(by[(3, 3, "pShift")], 8)
        self.assertEqual(by[(3, 13, "pShift")], 5)
        # pRepeat (v45 constant 8, P4-CLOSED) IS applied now (known issue #1):
        # hat repeats [3,0,…,3,…] on the all-active hat part = 2 pRepeat writes
        self.assertEqual(by[(3, 0, "pRepeat")], 3)
        self.assertEqual(by[(3, 8, "pRepeat")], 3)
        self.assertIn("repeats", r)
        self.assertIn("applied as pRepeat", r["repeats"])
        self.assertNotIn("repeats_failed", r)
        # the unmatched part is reported
        self.assertTrue(any("Nonexistent" in s for s in r["skipped"]))
        self.assertTrue(any("step-params" in w for w in r["written"]))

    def test_base_bpm_zero_leaves_tempo(self):
        with _PresetFixture(PRESET):
            _, conn = self._load(preset="pv2-test", base_bpm=0.0)
        self.assertEqual(_calls(conn, "transport.setPlaybackSpeed"), [])

    def test_base_bpm_sets_speed_multiplier(self):
        with _PresetFixture(PRESET):
            r, conn = self._load(preset="pv2-test", base_bpm=130.0)
        speeds = _calls(conn, "transport.setPlaybackSpeed")
        self.assertEqual(len(speeds), 1)
        self.assertAlmostEqual(speeds[0]["multiplier"], 140 / 130, places=4)
        self.assertIn("tempo", r)

    def test_unknown_preset_lists_available(self):
        r, _ = self._load(preset="no-such-beat-xyz")
        self.assertFalse(r["ok"])
        self.assertIn("available", r["error"])


class TestLoadMelody(unittest.TestCase):
    def test_queues_notes_and_chords(self):
        mel = {
            "name": "test-melody",
            "melody": [{"note": 60, "step": 0, "dur": 2, "vel": 100},
                       {"note": 64, "step": 4, "dur": 4, "vel": 80}],
            "chords": [{"step": 8, "dur": 8, "notes": [48, 52, 55]}],
        }
        with _PresetFixture(mel, id_="pv2-test-melody", kind="melodies"):
            with mock.patch.object(pv2, "get_connection",
                                   return_value=_RecConn()), \
                 mock.patch("fl_studio_mcp.tools.piano_roll._write_request") as wr, \
                 mock.patch("fl_studio_mcp.tools.piano_roll.trigger_fl_studio",
                            return_value=True), \
                 mock.patch("fl_studio_mcp.utils.roll_session.ran_since",
                            return_value=True):
                r = pv2.load_melody(preset="pv2-test-melody", target_pattern=3,
                                    auto_trigger=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["script_ran"])
        self.assertEqual(r["notes_queued"], 5)  # 2 melody + 3 chord
        req = wr.call_args[0][0]
        self.assertEqual(req[0]["action"], "clear")
        notes = req[1]["notes"]
        by_time = {}
        for n in notes:
            by_time.setdefault(round(n["time"], 3), []).append(n["midi"])
        # step 0 -> 0.0 qn ; step 4 -> 1.0 ; chord at step 8 -> 2.0
        self.assertEqual(by_time[0.0], [60])
        self.assertEqual(by_time[1.0], [64])
        self.assertEqual(by_time[2.0], [48, 52, 55])

    def test_empty_preset_refused(self):
        with mock.patch.object(pv2, "get_connection", return_value=_RecConn()):
            r = pv2.load_melody(preset="nope-empty-xyz")
        self.assertFalse(r["ok"])


class TestDispatch(unittest.TestCase):
    def test_unknown_action(self):
        r = pv2._preset_dispatch("explode")
        self.assertFalse(r["ok"])
        self.assertIn("unknown action", r["error"])

    def test_list_via_dispatch(self):
        r = pv2._preset_dispatch("list", kind="beats")
        self.assertTrue(r["ok"])
        self.assertIn("presets", r)


if __name__ == "__main__":
    unittest.main()


class TestLoadMelodyScriptDidNotRun(unittest.TestCase):
    """2026-10-02: 'triggered: true' while [clear, add_notes] sat in the queue."""

    def test_clears_the_queue_and_fails(self):
        mel = {"name": "m", "melody": [{"note": 60, "step": 0, "dur": 2, "vel": 100}]}
        with _PresetFixture(mel, id_="pv2-test-melody2", kind="melodies"):
            with mock.patch.object(pv2, "get_connection", return_value=_RecConn()), \
                 mock.patch("fl_studio_mcp.tools.piano_roll._write_request") as wr, \
                 mock.patch("fl_studio_mcp.tools.piano_roll.trigger_fl_studio",
                            return_value=True), \
                 mock.patch("fl_studio_mcp.utils.roll_session.ran_since",
                            return_value=False):
                r = pv2.load_melody(preset="pv2-test-melody2", auto_trigger=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["script_ran"])
        self.assertIn("queue was cleared", r["error"])
        self.assertEqual(wr.call_args_list[-1][0][0], [])      # emptied last


class _LenConn(_RecConn):
    def __init__(self, length_beats):
        super().__init__()
        self.length_beats = length_beats

    def send_command(self, action, params=None, timeout=None):
        if action == "patterns.getLength":
            self.calls.append((action, dict(params or {})))
            return {"success": True, "length_beats": self.length_beats}
        return super().send_command(action, params, timeout)


class TestLoadBeatFill(unittest.TestCase):
    """2026-10-02: a 1-bar beat in a 4-bar pattern played bar 1 + 3 bars of
    silence under the 3-bar melody."""

    BEAT = {"name": "fill-test", "channels": {
        "kick": {"name": "808 Kick", "pattern": [1, 0, 0, 0] * 4,
                 "velocities": [127, 0, 0, 0] * 4}}}

    def _load(self, length_beats, **kw):
        conn = _LenConn(length_beats)
        with _PresetFixture(self.BEAT, id_="pv2-fill"), \
             mock.patch.object(pv2, "get_connection", return_value=conn):
            r = pv2.load_beat(preset="pv2-fill", target_pattern=2, **kw)
        return r, conn

    def test_tiles_to_the_pattern_length(self):
        r, conn = self._load(16)
        self.assertEqual(r["filled_to_steps"], 64)
        self.assertEqual(_calls(conn, "patterns.getLength"), [{"index": 1}])
        kick = [p for p in _calls(conn, "channels.setStepSequence")
                if p["channel"] == 0 and any(p["pattern"])][-1]["pattern"]
        self.assertEqual(len(kick), 64)
        self.assertEqual(sum(kick), 16)                      # 4 hits x 4 bars
        vel_steps = [p["step"] for p in _calls(conn, "channels.setStepParameter")
                     if p["param"] in ("pVelocity", 1)]
        self.assertEqual(len(vel_steps), 16)                 # velocities tiled too
        self.assertIn(60, vel_steps)

    def test_fill_off_keeps_one_bar(self):
        r, conn = self._load(16, fill=False)
        self.assertIsNone(r["filled_to_steps"])
        kick = [p for p in _calls(conn, "channels.setStepSequence")
                if p["channel"] == 0 and any(p["pattern"])][-1]["pattern"]
        self.assertEqual(len(kick), 16)


class TestAutoLevel(unittest.TestCase):
    """Owner 2026-10-02: clipping fix 'automated' after every load."""

    BEAT = {"name": "lvl", "channels": {"kick": {"name": "808 Kick", "pattern": [1, 0, 0, 0] * 4}}}

    def _load(self, **kw):
        calls = []
        with _PresetFixture(self.BEAT, id_="pv2-lvl"), \
             mock.patch.object(pv2, "get_connection", return_value=_RecConn()), \
             mock.patch.object(pv2, "_auto_level",
                               side_effect=lambda conn: calls.append(1) or {"changed": True}):
            r = pv2.load_beat(preset="pv2-lvl", fill=False, **kw)
        return r, calls

    def test_load_runs_the_level_check(self):
        r, calls = self._load()
        self.assertEqual(calls, [1])
        self.assertEqual(r["auto_level"], {"changed": True})

    def test_auto_level_false_skips_it(self):
        r, calls = self._load(auto_level=False)
        self.assertEqual(calls, [])
        self.assertNotIn("auto_level", r)
