"""S4.1: fl_slice_audio — onset slicing, grids, manifest, declick.

Hermetic: a synthetic 120 BPM two-bar beat (4-on-floor kicks, backbeat
snares, 16th hats) is rendered in numpy to a tmp wav and run through the
slicer; assertions cover onset count, 16/32-grid boundaries, manifest
schema, declicked edges and the key estimator.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from fl_studio_mcp.audio.slicer import boundaries, estimate_key, onset_times, read_mono, slice_audio
from fl_studio_mcp.tools.slice_v2 import fl_slice_audio

SR = 44100


def _kick(t0: float, sr: int, dur: float = 0.25) -> tuple[np.ndarray, int]:
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * 14)
    return np.sin(2 * np.pi * 65.4 * t) * env, int(t0 * sr)


def _hat(t0: float, sr: int, dur: float = 0.05) -> tuple[np.ndarray, int]:
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * 60)
    rng = np.random.default_rng(int(t0 * 1000))
    return rng.standard_normal(n) * env * 0.3, int(t0 * sr)


def _snare(t0: float, sr: int, dur: float = 0.15) -> tuple[np.ndarray, int]:
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * 25)
    rng = np.random.default_rng(int(t0 * 1000) + 7)
    tone = np.sin(2 * np.pi * 190 * t) * 0.5
    return (rng.standard_normal(n) * 0.6 + tone) * env, int(t0 * sr)


def _fixture_wav(tmp_path: Path) -> Path:
    """Two bars @120bpm (4 s): 8 kicks, 4 snares, 32 hats."""
    audio = np.zeros(int(4.0 * SR))
    for i in range(8):            # 4-on-floor
        s, o = _kick(i * 0.5, SR)
        audio[o:o + len(s)] += s
    for bar in range(2):
        for off in (0.5, 1.5):    # backbeat: beat 2 & 4 of each bar
            s, o = _snare(bar * 2.0 + off, SR)
            audio[o:o + len(s)] += s
    for i in range(32):           # 16th hats
        s, o = _hat(i * 0.125, SR)
        audio[o:o + len(s)] += s
    p = tmp_path / "fixture-beat.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
        w.writeframes(pcm.tobytes())
    return p


# ---------------------------------------------------------------------------
# Onsets
# ---------------------------------------------------------------------------
def test_onset_count_on_fixture_beat(tmp_path):
    audio = read_mono(_fixture_wav(tmp_path), SR)
    onsets = onset_times(audio, SR)
    # 44 true transients; detector tolerance ±30%
    assert 32 <= len(onsets) <= 56, f"got {len(onsets)} onsets"
    assert all(0 <= a < b < 4.0 for a, b in zip(onsets, onsets[1:]))
    # the 8 kick onsets must be found near the true beat times
    kick_times = [i * 0.5 for i in range(8)]
    found = sum(1 for k in kick_times
                if any(abs(o - k) < 0.04 for o in onsets))
    assert found >= 6, "most kick onsets missing"


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------
def test_grid_16_boundaries():
    b, meta = boundaries(4.0, grid="16", bpm=120.0)
    assert meta["grid"] == "16" and meta["bpm"] == 120.0
    assert b[0] == 0.0 and b[-1] == 4.0
    assert len(b) == 33                       # 32 16ths + terminus
    assert all(abs((y - x) - 0.125) < 1e-3 for x, y in zip(b, b[1:]))


def test_grid_32_boundaries():
    b, meta = boundaries(2.0, grid="32", bpm=120.0)
    assert len(b) == 33                       # 32 32nds in 2 s @120
    assert all(abs((y - x) - 0.0625) < 1e-3 for x, y in zip(b, b[1:]))


def test_grid_16_requires_bpm():
    with pytest.raises(ValueError):
        boundaries(4.0, grid="16")
    with pytest.raises(ValueError):
        boundaries(4.0, grid="bogus")


def test_onset_grid_merges_too_close():
    b, meta = boundaries(1.0, grid="onset", onsets=[0.1, 0.12, 0.5],
                         min_slice_s=0.06)
    assert b[0] == 0.0
    assert 0.1 in b and 0.12 not in b          # 20 ms gap merged
    assert b[-1] == 1.0


# ---------------------------------------------------------------------------
# Manifest + files
# ---------------------------------------------------------------------------
def _manifest_fixture(tmp_path: Path) -> dict:
    return slice_audio(_fixture_wav(tmp_path), tmp_path / "gen", "fixture",
                       grid="onset", sr=SR)


def test_manifest_schema(tmp_path):
    m = _manifest_fixture(tmp_path)
    for k in ("song", "source", "sr", "duration_s", "grid", "bpm",
              "key_guess", "n_slices", "slices", "manifest_path"):
        assert k in m, k
    assert m["song"] == "fixture" and m["grid"] == "onset"
    assert m["n_slices"] == len(m["slices"]) >= 10
    prev = 0.0
    for s in m["slices"]:
        assert 40 <= s["velocity"] <= 127
        assert s["start_s"] >= prev - 1e-6
        assert s["len_s"] > 0
        assert abs(s["len_s"] - s["len_samples"] / m["sr"]) < 1e-3
        prev = s["start_s"]
    # manifest file on disk matches
    disk = json.loads(Path(m["manifest_path"]).read_text())
    assert disk["n_slices"] == m["n_slices"]


def test_slice_files_exist_and_declicked(tmp_path):
    m = _manifest_fixture(tmp_path)
    out = Path(m["manifest_path"]).parent
    for s in m["slices"]:
        p = out / s["file"]
        assert p.exists()
        with wave.open(str(p), "rb") as w:
            assert w.getframerate() == SR
            data = np.frombuffer(w.readframes(w.getnframes()),
                                 dtype="<i2").astype(np.float64) / 32768
        assert len(data) > 100
        # 3 ms fade-in/out → first/last samples near silence
        edge = 10
        assert abs(data[0]) < 0.01 and abs(data[-1]) < 0.01
        assert max(np.abs(data[:edge]).max(), np.abs(data[-edge:]).max()) \
            < max(0.05, np.abs(data).max() * 0.2)


def test_grid_16_slice_count(tmp_path):
    m = slice_audio(_fixture_wav(tmp_path), tmp_path / "gen16", "fixture",
                    grid="16", bpm=120.0, sr=SR)
    assert m["n_slices"] == 32
    assert m["grid"] == "16" and m["bpm"] == 120.0


# ---------------------------------------------------------------------------
# Key estimator + tool guards
# ---------------------------------------------------------------------------
def test_estimate_key_pure_c_note():
    t = np.arange(SR) / SR                    # 1 s of C4 (261.63 Hz)
    x = np.sin(2 * np.pi * 261.63 * t)
    assert estimate_key(x, SR) == "C"


def test_tool_rejects_non_audio(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello")
    r = fl_slice_audio(str(p))
    assert r["ok"] is False and "not a known audio file" in r["error"]


def test_tool_missing_file():
    r = fl_slice_audio("/nonexistent/nope.wav")
    assert r["ok"] is False and "no such file" in r["error"]


def test_tool_end_to_end(tmp_path, monkeypatch):
    import fl_studio_mcp.tools.slice_v2 as sv
    monkeypatch.setattr(sv, "_GENERATED", tmp_path / "gen")
    p = _fixture_wav(tmp_path)
    r = fl_slice_audio(str(p), grid="16", bpm=120.0)
    assert r["ok"], r
    assert r["n_slices"] == 32
    assert Path(r["manifest"]).exists()
    first = Path(r["out_dir"]) / r["slices"][0]["file"]
    assert first.exists()
