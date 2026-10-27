"""fl_audio: analysis (tempo/key/chords), chord names, root note, cut, L/R split (offline; ffmpeg)."""
import shutil
import subprocess
import wave

import numpy as np
import pytest

from fl_studio_mcp.tools import audio_v2 as a

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


@pytest.fixture(autouse=True)
def _tmp_out(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "OUT", tmp_path / "out")


def _tone(path, freqs, dur=2, stereo_split=False):
    if stereo_split:      # left = 220 Hz, right = silence
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}",
               "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={dur}",
               "-filter_complex", "[0][1]amerge=inputs=2", "-t", str(dur), str(path)]
    else:
        ins = []
        for f in freqs:
            ins += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={dur}"]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *ins,
               "-filter_complex", f"amix=inputs={len(freqs)},volume=3", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.mark.parametrize("lab,want", [("F:maj", "F"), ("A:min", "Am"), ("C:maj7", "Cmaj7"),
                                      ("G:7", "G7"), ("B:hdim7", "Bm7b5"), ("N", "-")])
def test_chord_names(lab, want):
    assert a.chord_name(lab) == want


SR = 22050


def _write(path, x, sr=SR):
    pcm = (np.clip(x / max(1e-9, np.abs(x).max()) * 0.8, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def _clicks(bpm, secs=10.0):
    x = np.zeros(int(secs * SR))
    n = int(0.01 * SR)
    burst = np.random.default_rng(0).standard_normal(n) * np.hanning(n)
    for t in np.arange(0, secs, 60 / bpm):
        i = int(t * SR)
        x[i:i + n] += burst[:x[i:i + n].size]
    return x


def _triad(root, minor, dur=1.0):
    t = np.arange(int(dur * SR)) / SR
    hz = [440 * 2 ** ((root + i - 69) / 12) for i in ((0, 3, 7) if minor else (0, 4, 7))]
    x = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) for f in hz)
    return x * np.minimum(1, np.minimum(t, dur - t) * 50)


C_AM_F_G = [(60, 0), (57, 1), (53, 0), (55, 0)]


@pytest.mark.parametrize("bpm", [70, 90, 120, 140, 174])
def test_tempo_of_a_click_track(bpm):
    from fl_studio_mcp.audio import analysis as an
    r = an.tempo(_clicks(bpm))
    assert r["agree"] and abs(r["bpm"] - bpm) / bpm < 0.02, r


def test_key_and_chords_of_a_progression():
    from fl_studio_mcp.audio import analysis as an
    x = np.concatenate([_triad(r, m) for r, m in C_AM_F_G] * 2)
    assert an.key(x)["key"] == "C" and an.key(x)["scale"] == "major"
    got = [c["chord"] for c in an.chords(x, bpm=60)]
    assert got == ["C:maj", "A:min", "F:maj", "G:maj"] * 2
    am = np.concatenate([_triad(r, m) for r, m in [(57, 1), (53, 0), (48, 0), (55, 0)]] * 2)
    assert (an.key(am)["key"], an.key(am)["scale"]) == ("A", "minor")


def test_analyze_end_to_end_reports_tempo_key_chords(tmp_path):
    prog = np.concatenate([_triad(r, m, dur=0.5) for r, m in C_AM_F_G] * 4)   # one chord per beat
    beat = _clicks(120, prog.size / SR)[:prog.size]
    r = a.fl_audio("analyze", path=str(_write(tmp_path / "loop.wav", prog + 0.5 * beat)),
                   what=["tempo", "key", "chords"])
    assert r["success"] and abs(r["tempo"]["bpm"] - 120) < 2
    assert r["key"]["key"] == "C major"
    assert [c["chord"] for c in r["chords"]][:4] == ["C", "Am", "F", "G"]


def test_silence_is_no_chord_and_no_key(tmp_path):
    from fl_studio_mcp.audio import analysis as an
    x = np.zeros(SR * 3)
    assert an.key(x)["key"] is None
    assert {c["chord"] for c in an.chords(x)} <= {"N"}


def test_root_note_of_an_808(tmp_path):
    r = a.root_note(_tone(tmp_path / "a1.wav", [55, 110]))
    assert r["note"] == "A1" and abs(r["cents_off"]) < 20


def test_extract_length(tmp_path):
    src = _tone(tmp_path / "t.wav", [440], dur=3)
    r = a.fl_audio("extract", path=str(src), start=1.0, end=2.5)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", r["file"]], capture_output=True, text=True).stdout)
    assert r["success"] and abs(dur - 1.5) < 0.05


def test_split_left_is_mono_and_keeps_the_left(tmp_path):
    src = _tone(tmp_path / "lr.wav", [], stereo_split=True)
    left = a.fl_audio("split", path=str(src), side="left")
    right = a.fl_audio("split", path=str(src), side="right")
    ch = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of", "csv=p=0",
                         left["file"]], capture_output=True, text=True).stdout.strip()
    assert ch == "1"
    vol = lambda f: subprocess.run(["ffmpeg", "-i", f, "-af", "volumedetect", "-f", "null", "-"],
                                   capture_output=True, text=True).stderr
    assert "-inf" not in vol(left["file"]).split("max_volume")[1][:20]
    assert "-91" in vol(right["file"]) or "-inf" in vol(right["file"])


def test_bad_inputs():
    assert not a.fl_audio("extract", path=__file__, start=3, end=1)["success"]
    assert not a.fl_audio("split", path=__file__, side="middle")["success"]
    assert not a.fl_audio("analyze")["success"]


def test_recorder_arms_existing_edison(monkeypatch):
    import fl_studio_mcp.tools.mixer_tracks as mt
    import fl_studio_mcp.tools.mixer_v2 as mv
    state = {"rec": 0.0}
    monkeypatch.setattr(mt, "list_fx", lambda conn, t: [{"slot": 0, "plugin": "Edison", "on": True}])

    def fake_exec(conn, code):
        if "setParamValue" in code:
            state["rec"] = float(code.split("setParamValue(")[1].split(",")[0])
            return "1"
        return str(state["rec"])
    monkeypatch.setattr(mv, "_exec", fake_exec)
    r = a.fl_audio("recorder", conn=object(), on=True)
    assert r["success"] and r["on"] and not r["inserted"]
    r = a.fl_audio("recorder", conn=object(), on=False)
    assert r["success"] and not r["on"]
