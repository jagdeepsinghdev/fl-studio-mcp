"""S4.1: audio slicing — onset boundaries → slice files + manifest.

Server-side, no MIDI. Pipeline:

  1. read the audio (wav via stdlib; anything else decoded to mono float
     with the system ffmpeg)
  2. onset detection (half-wave-rectified flux peak-picking — the same
     class as librosa's superflux,
     implemented in pure numpy so the MCP server stays dependency-light)
  3. boundaries: ``onset`` grid = detected onsets (min-gap merged);
     ``16``/``32`` grid = uniform 16th/32nd-note steps at the given BPM
  4. each slice is extracted, **declicked** (3 ms raised-cosine edge
     fades) and written as a 16-bit mono wav under
     ``fl-studio-mcp/.generated/slices/<song>/`` (git-ignored, rule 9/10)
  5. manifest JSON: per-slice start/len (seconds + samples), energy →
     velocity (40..127, relative to the loudest slice), a coarse
     key guess (chroma mode over the whole clip), and the grid cell.

The manifest is the contract for S4.3 (``fl_load_slices``) and S4.2
(Edison region scripts): one entry per slice, in order.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff", ".aif"}

#: slices shorter than this (seconds) are merged into their neighbour
MIN_SLICE_S = 0.06
HOP_S = 0.005          # 5 ms analysis hop (~882 frames/s at 44.1k)
MIN_GAP_S = 0.08       # hits closer than this keep the stronger


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_mono(path: Path, sr: int = 44100) -> np.ndarray:
    """Return the file as mono float64 in [-1, 1] at ``sr``."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as w:
            n_ch, sw, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(w.getnframes())
        if sw == 2:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        elif sw == 1:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
                    - 128.0) / 128.0
        else:
            raise ValueError(f"unsupported wav bit depth {sw * 8}")
        if n_ch > 1:
            data = data.reshape(-1, n_ch).mean(axis=1)
        if fr != sr:
            data = _resample(data, fr, sr)
        return data
    # non-wav: decode with ffmpeg to raw f32le mono
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "decoded.raw"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-ar", str(sr),
             "-f", "f32le", "-c:a", "pcm_f32le", str(tmp)],
            check=True, capture_output=True)
        data = np.fromfile(str(tmp), dtype=np.float32).astype(np.float64)
    return data


def _resample(x: np.ndarray, sr0: int, sr1: int) -> np.ndarray:
    if sr0 == sr1:
        return x
    n = int(len(x) * sr1 / sr0)
    if n == 0:
        return x
    xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    xq = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(xq, xp, x)


# ---------------------------------------------------------------------------
# Onsets (HWR flux peak-picking)
# ---------------------------------------------------------------------------
def onset_times(audio: np.ndarray, sr: int,
                min_gap_s: float = MIN_GAP_S,
                threshold_pct: float = 50.0) -> list[float]:
    """Onset times (seconds) via half-wave-rectified flux peak-picking.

    The threshold is the higher of the flux mean and the ``threshold_pct``
    percentile of the (0..1 normalised) flux. A pure mean+k·std threshold
    is dominated by the loudest transients (kicks) and starves the quiet
    ones (hats); the percentile floor adapts to the instrument mix. Raise
    ``threshold_pct`` for dense, noisy material.
    """
    hop = max(1, int(sr * HOP_S))
    pad = (-len(audio)) % hop
    if pad:
        audio = np.concatenate([audio, np.zeros(pad)])
    n_frames = len(audio) // hop
    if n_frames < 1:
        return []
    frames = np.asarray([audio[i * hop:(i + 1) * hop]
                         for i in range(n_frames)], dtype=np.float64)
    # half-wave rectification
    hwr = np.maximum(0.0, frames)
    diff = np.diff(hwr, axis=0, prepend=hwr[:1])
    flux = diff.sum(axis=1) / max(1, hwr.shape[1])
    if len(flux) < 3 or flux.max() < 1e-6:
        return []
    flux = flux / flux.max()
    mean = float(flux.mean())
    thresh = max(mean, float(np.percentile(flux, threshold_pct)))
    cand: list[tuple[float, float]] = []
    for i in range(1, len(flux) - 1):
        if flux[i] > thresh and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]:
            cand.append((i * HOP_S, float(flux[i])))
    # min-gap: keep the stronger of overlapping candidates
    cand.sort(key=lambda c: c[0])
    out: list[float] = []
    last_t = -1e9
    for t, e in cand:
        if t - last_t >= min_gap_s:
            out.append(round(t, 3))
            last_t = t
    return out


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------
def boundaries(duration_s: float, grid: str = "onset", bpm: float = 0.0,
               onsets: list[float] | None = None,
               min_slice_s: float = MIN_SLICE_S) -> tuple[list[float], dict]:
    """Slice boundary times (start with 0.0, end with duration).

    grid: ``onset`` (detected, min-gap merged), ``16`` (16th notes at bpm),
    ``32`` (32nd notes at bpm).
    """
    if grid == "onset":
        raw = [0.0] + sorted(t for t in (onsets or []) if 0 < t < duration_s)
        if not raw or raw[-1] < duration_s:
            raw.append(round(duration_s, 3))
        merged = [raw[0]]
        for t in raw[1:]:
            if t - merged[-1] >= min_slice_s:
                merged.append(t)
            # else: drop the closer onset (merged into the previous slice)
        if merged[-1] < duration_s:
            merged[-1] = round(duration_s, 3)
        meta = {"grid": "onset", "n_onsets": len(onsets or [])}
        return merged, meta
    if grid in ("16", "32"):
        if not bpm:
            raise ValueError(f"grid={grid!r} needs bpm")
        bpm = float(bpm)
        div = 4 if grid == "16" else 8
        step = 60.0 / bpm / div
        out = [0.0]
        t = step
        while t < duration_s - 1e-6:
            out.append(round(t, 3))
            t += step
        out.append(round(duration_s, 3))
        meta = {"grid": grid, "bpm": bpm, "step_s": round(step, 5)}
        return out, meta
    raise ValueError(f"unknown grid {grid!r} (onset|16|32)")


# ---------------------------------------------------------------------------
# Per-slice features
# ---------------------------------------------------------------------------
def slice_features(s: np.ndarray, sr: int, rmax: float) -> dict:
    rms = float(np.sqrt(np.mean(np.square(s)))) if len(s) else 0.0
    vel = 40 + int(round(87 * min(1.0, rms / rmax))) if rmax > 0 else 80
    return {"rms": round(rms, 5), "velocity": int(min(127, max(40, vel)))}


def estimate_key(audio: np.ndarray, sr: int) -> str | None:
    """Coarse key guess: 12-bin chroma mode over the whole clip."""
    if len(audio) < sr:
        return None
    x = np.ascontiguousarray(audio[: min(len(audio), sr * 30)])
    n = len(x)
    fft = np.fft.rfft(x * np.hanning(n))
    mag = np.abs(fft)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    bins = np.zeros(12)
    for f, m in zip(freqs, mag):
        if f < 60 or f > 5000:
            continue
        midi = round(69.0 + 12.0 * np.log2(f / 440.0))
        if midi < 0:
            continue
        bins[midi % 12] += m
    if bins.max() <= 0:
        return None
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return names[int(bins.argmax())]


def _declick(a: np.ndarray, sr: int, ms: float = 3.0) -> np.ndarray:
    n = int(sr * ms / 1000)
    a = a.copy()
    if n * 2 < len(a) and n > 0:
        fade = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
        a[:n] *= fade
        a[-n:] *= fade[::-1]
    return a


def write_wav16(path: Path, a: np.ndarray, sr: int) -> None:
    pcm = np.clip(a, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def slice_audio(path: Path, out_root: Path, song: str,
                grid: str = "onset", bpm: float = 0.0,
                sr: int = 44100) -> dict[str, Any]:
    """Run the whole pipeline; returns the manifest dict and writes
    slice wavs + manifest.json under ``out_root/song/``."""
    audio = read_mono(path, sr)
    duration = len(audio) / sr
    onsets = onset_times(audio, sr)
    bounds, meta = boundaries(duration, grid=grid, bpm=bpm, onsets=onsets)

    out_dir = out_root / song
    out_dir.mkdir(parents=True, exist_ok=True)

    slices = []
    rmax = 0.0
    segs = []
    for i in range(len(bounds) - 1):
        s0, s1 = int(bounds[i] * sr), int(min(len(audio), bounds[i + 1] * sr))
        seg = audio[s0:s1]
        r = float(np.sqrt(np.mean(np.square(seg)))) if len(seg) else 0.0
        rmax = max(rmax, r)
        segs.append((seg, s0, s1))
    for i, (seg, s0, s1) in enumerate(segs):
        clean = _declick(seg, sr)
        fname = f"slice_{i:03d}.wav"
        write_wav16(out_dir / fname, clean, sr)
        feat = slice_features(seg, sr, rmax)
        slices.append({
            "index": i,
            "file": fname,
            "start_s": round(s0 / sr, 3),
            "len_s": round(max(0, s1 - s0) / sr, 3),
            "start_sample": s0,
            "len_samples": max(0, s1 - s0),
            "velocity": feat["velocity"],
            "rms": feat["rms"],
        })
    manifest: dict[str, Any] = {
        "song": song,
        "source": str(path),
        "sr": sr,
        "duration_s": round(duration, 3),
        "grid": meta.get("grid", grid),
        "bpm": meta.get("bpm", bpm or 0),
        "key_guess": estimate_key(audio, sr),
        "n_slices": len(slices),
        "slices": slices,
        "note": ("Generated by fl_slice_audio; private learning material — "
                 "not for shared datasets (rule 10)."),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    manifest["manifest_path"] = str(out_dir / "manifest.json")
    return manifest
