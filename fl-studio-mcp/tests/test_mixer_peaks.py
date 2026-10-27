"""L17: fl_mixer get_peaks — fake controller, no FL."""

from __future__ import annotations

import json

from fl_studio_mcp.tools import mixer_v2 as mx


class _Conn:
    """Answers mixer.getPeaks from a script of frames (or 'Unknown action')."""

    def __init__(self, frames, native=True):
        self.frames = iter(frames)
        self.native = native
        self.calls = []

    def send_command(self, action, params=None, **kw):
        self.calls.append(action)
        if action == "mixer.getPeaks":
            if not self.native:
                return {"success": False, "error": "Unknown action: mixer.getPeaks"}
            return {"success": True, **next(self.frames)}
        if action == "probe.exec":
            assert "getTrackPeaks" in params["code"]           # the fixed snippet
            return {"success": True, "stdout": json.dumps(next(self.frames)) + "\n"}
        raise AssertionError(action)


def _f(peaks, playing=True, last=(0.0, 0.0)):
    return {"peaks": peaks, "master_last": list(last), "playing": playing}


def test_keeps_the_max_over_the_window_and_flags_clipping():
    conn = _Conn([_f([[0, 0.2, 0.3], [1, 0.9, 0.8]]),
                  _f([[0, 1.05, 0.7], [1, 0.1, 0.1]]),
                  _f([[0, 0.1, 0.1], [1, 0.0, 0.0]])])
    r = mx.get_peaks(conn, None, window=0.2, sleep=lambda s: None)
    assert r["success"] and r["samples"] == 3 and r["via"] == "mixer.getPeaks"
    master, ch1 = r["tracks"]
    assert (master["track"], master["peak"], master["clipping"]) == (0, 1.05, True)
    assert master["dbfs"] == 0.42
    assert (ch1["peak"], ch1["clipping"], ch1["dbfs"]) == (0.9, False, -0.92)
    assert r["clipping"] is True


def test_all_tracks_lists_only_sounding_ones_plus_master():
    conn = _Conn([_f([[0, 0.0, 0.0], [1, 0.0, 0.0], [5, 0.4, 0.4]])])
    r = mx.get_peaks(conn, None, window=0.0, sleep=lambda s: None)
    assert [t["track"] for t in r["tracks"]] == [0, 5]


def test_silence_while_stopped_says_so():
    conn = _Conn([_f([[0, 0.0, 0.0]], playing=False)])
    r = mx.get_peaks(conn, 0, window=0.0, sleep=lambda s: None)
    assert r["tracks"][0]["dbfs"] is None and "not playing" in r["note"]


def test_falls_back_to_probe_exec_on_a_v10_4f_controller():
    conn = _Conn([_f([[0, 0.5, 0.5]])], native=False)
    r = mx.get_peaks(conn, 0, window=0.0, sleep=lambda s: None)
    assert r["via"] == "probe.exec" and r["tracks"][0]["peak"] == 0.5
    assert conn.calls == ["mixer.getPeaks", "probe.exec"]


def test_validation():
    assert "window" in mx.fl_mixer("get_peaks", window=9)["error"]
    assert "track" in mx.fl_mixer("get_peaks", track=-1)["error"]
    conn = _Conn([_f([[3, 0.25, 0.5]])])
    r = mx.fl_mixer("get_peaks", conn=conn, track=3, window=0.0)
    assert r["success"] and r["tracks"][0]["right"] == 0.5


class _LagFL:
    """Fake FL, as measured live 2026-10-02: setTrackVolume applies only AFTER
    the trip, the fader->dB curve is monotonic, and the track meter is
    PRE-fader (the fader does not change what getTrackPeaks reports)."""

    def __init__(self, fader=0.8, peak_at_0db=1.06):     # +0.5 dBFS
        self.fader, self.pending, self.base = fader, None, peak_at_0db
        self.playing = False

    @staticmethod
    def db(v):
        import math
        return 40 * math.log10(v / 0.8) if v > 0 else float("-inf")

    def send_command(self, action, params=None, **kw):
        import json
        import re
        if self.pending is not None:                    # the previous trip's set
            self.fader, self.pending = self.pending, None
        if action == "state.snapshot":
            return {"success": True, "state": {"transport": {"is_playing": self.playing}}}
        if action in ("transport.start", "transport.stop"):
            self.playing = action == "transport.start"
            return {"success": True}
        if action.startswith("transport."):
            self.calls = getattr(self, "calls", []) + [action]
            return {"success": True}
        if action == "mixer.getPeaks":
            pk = self.base                                   # pre-fader meter
            return {"success": True, "peaks": [[0, pk, pk]], "master_last": [0, 0],
                    "playing": self.playing}
        code = params["code"]
        m = re.search(r"setTrackVolume\(0, ([0-9.e-]+)\)", code)
        if m:
            self.pending = float(m.group(1))                 # NOT visible this trip
            return {"success": True, "stdout": ""}
        return {"success": True, "stdout": json.dumps(
            {"fader": self.fader, "db": self.db(self.fader)}) + "\n"}


def test_fix_clipping_survives_the_same_trip_read_lag():
    fl = _LagFL()                                        # pre-fader +0.51 dBFS
    r = mx.fix_clipping(fl, 0, -1.0, window=0.5, sleep=lambda s: None)
    assert r["success"] and r["changed"] and r["verified"]
    assert r["prefader_peak_dbfs"] == 0.51 and r["output_peak_before_dbfs"] == 0.51
    assert -1.2 <= r["output_peak_after_dbfs"] <= -1.0   # just under the target
    assert -1.75 <= r["gain_change_db"] <= -1.5          # the 1.51 dB excess, not silence
    assert fl.playing is False                           # stopped again (was stopped)
    assert "transport.setPosition" in fl.calls           # each pass = from the top


def test_fix_clipping_leaves_a_quiet_track_alone():
    fl = _LagFL(peak_at_0db=0.5)                         # -6 dBFS
    r = mx.fix_clipping(fl, 0, -1.0, window=0.5, sleep=lambda s: None)
    assert r["changed"] is False and fl.fader == 0.8


def test_fix_clipping_counts_an_already_lowered_fader():
    """Pre-fader +0.51 with the fader already at -4 dB = output -3.5: no change."""
    import math
    fl = _LagFL(fader=0.8 * 10 ** (-4 / 40))
    r = mx.fix_clipping(fl, 0, -1.0, window=0.5, sleep=lambda s: None)
    assert r["changed"] is False and math.isclose(r["output_peak_before_dbfs"], -3.49, abs_tol=0.02)
