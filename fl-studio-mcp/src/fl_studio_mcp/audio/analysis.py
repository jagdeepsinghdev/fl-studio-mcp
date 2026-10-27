"""fl_audio analyze: tempo / key / chords in pure numpy (no ML models, no extra envs).

Server-side, dependency-light (numpy + the system ffmpeg for decoding):

  tempo   two independent estimators over one onset envelope (log spectral flux):
          ``autocorr`` (envelope autocorrelation) and ``tempogram`` (Fourier
          tempogram, fundamental + 2nd harmonic). Both carry a log-normal prior at
          120 BPM; when they disagree beyond half/double, the caller reports a gap.
  key     Krumhansl-Kessler profiles correlated with the clip's mean chroma
          (24 keys); ``strength`` = the Pearson r of the winner (< 0.5 = weak).
  chords  per-beat chroma vs major/minor triad templates (cosine); quiet windows
          are 'N'. Labels are Harte-style ('C:maj', 'A:min') for ``chord_name``.

These are estimates for a producer to check by ear, not ground truth: gaps are
reported by the caller, never hidden.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 22050
N_FFT = 2048
HOP = 512
FPS = SR / HOP
BPM_MIN, BPM_MAX = 60.0, 200.0
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Kessler key profiles (C major / C minor)
KK_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load(path: Path, seconds: float = 120.0) -> np.ndarray:
    """Mono float audio at SR, at most ``seconds`` long (any format/bit depth, via ffmpeg)."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-t", str(seconds),
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True, timeout=300).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def spectrogram(x: np.ndarray) -> np.ndarray:
    """|STFT|, shape (frames, N_FFT//2 + 1)."""
    if x.size < N_FFT:
        x = np.pad(x, (0, N_FFT - x.size))
    n = 1 + (x.size - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(x[idx] * np.hanning(N_FFT), axis=1))


def onset_envelope(mag: np.ndarray) -> np.ndarray:
    """Half-wave-rectified log spectral flux, local mean removed, peak = 1."""
    logm = np.log1p(100.0 * mag)
    flux = np.maximum(0.0, np.diff(logm, axis=0)).sum(axis=1)
    w = max(1, int(0.5 * FPS))
    flux = np.maximum(0.0, flux - np.convolve(flux, np.ones(w) / w, mode="same"))
    peak = flux.max() if flux.size else 0.0
    return flux / peak if peak > 0 else flux


def _prior(bpm: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * (np.log2(bpm / 120.0) / 1.0) ** 2)


def tempo_autocorr(env: np.ndarray) -> float | None:
    if env.size < 4 * FPS:
        return None
    e = env - env.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(e, n=2 * e.size)) ** 2)[: e.size]
    lags = np.arange(int(FPS * 60 / BPM_MAX), int(FPS * 60 / BPM_MIN) + 1)
    lags = lags[lags < ac.size - 1]
    if lags.size == 0 or ac[0] <= 0:
        return None
    score = ac[lags] / ac[0] * _prior(60 * FPS / lags)
    i = int(np.argmax(score))
    lag = float(lags[i])
    if 0 < i < lags.size - 1:              # parabolic refinement of the peak
        a, b, c = ac[lags[i] - 1], ac[lags[i]], ac[lags[i] + 1]
        den = a - 2 * b + c
        if den != 0:
            lag += 0.5 * (a - c) / den
    return 60 * FPS / lag


def tempo_tempogram(env: np.ndarray) -> float | None:
    if env.size < 4 * FPS:
        return None
    t = np.arange(env.size) / FPS
    e = env - env.mean()
    bpms = np.arange(BPM_MIN, BPM_MAX + 0.25, 0.25)

    def mag(f: np.ndarray) -> np.ndarray:
        return np.abs(np.exp(-2j * np.pi * f[:, None] * t[None, :]) @ e)

    f = bpms / 60.0
    score = (mag(f) + 0.5 * mag(2 * f)) * _prior(bpms)
    return float(bpms[int(np.argmax(score))])


def tempo(x: np.ndarray) -> dict:
    env = onset_envelope(spectrogram(x))
    a, b = tempo_autocorr(env), tempo_tempogram(env)
    agree = bool(a and b and min(abs(a - b), abs(a - 2 * b), abs(2 * a - b)) / max(a, b) < 0.04)
    bpm = a or b
    if agree:     # the tempogram is finer; the autocorrelation picks the octave better
        bpm = min((b / 2, b, b * 2), key=lambda v: abs(v - a))
    r1 = lambda v: round(float(v), 1) if v else None  # noqa: E731
    return {"bpm": r1(bpm), "bpm_alt": [r1(bpm / 2), r1(bpm * 2)] if bpm else [],
            "autocorr": r1(a), "tempogram": r1(b), "agree": agree}


def chroma(mag: np.ndarray) -> np.ndarray:
    """Per-frame pitch-class energy (frames, 12), 55 Hz - 4.2 kHz."""
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    band = (freqs >= 55) & (freqs <= 4200)
    pc = np.round(69 + 12 * np.log2(freqs[band] / 440.0)).astype(int) % 12
    proj = np.zeros((band.sum(), 12))
    proj[np.arange(pc.size), pc] = 1.0
    m = mag[:, band]
    peak = m.max() if m.size else 0.0
    if peak > 0:
        m = m / peak                     # level-independent compression
    return np.log1p(100.0 * m ** 2) @ proj


def key(x: np.ndarray) -> dict:
    c = chroma(spectrogram(x)).sum(axis=0)
    if c.sum() <= 0:
        return {"key": None, "scale": None, "strength": 0.0}
    best = (-2.0, 0, "major")
    for root in range(12):
        for scale, prof in (("major", KK_MAJ), ("minor", KK_MIN)):
            r = float(np.corrcoef(c, np.roll(prof, root))[0, 1])
            if r > best[0]:
                best = (r, root, scale)
    return {"key": NOTES[best[1]], "scale": best[2], "strength": round(best[0], 3)}


def chords(x: np.ndarray, bpm: float | None = None) -> list[dict]:
    """Chord per beat (or per 0.5 s without a tempo): [{chord, start, end, score}]."""
    ch = chroma(spectrogram(x))
    if ch.size == 0:
        return []
    win = max(1, int(round(FPS * (60.0 / bpm if bpm else 0.5))))
    tmpl = []
    for root in range(12):
        for q, iv in (("maj", (0, 4, 7)), ("min", (0, 3, 7))):
            v = np.zeros(12)
            v[[(root + i) % 12 for i in iv]] = 1.0
            tmpl.append((f"{NOTES[root]}:{q}", v / np.linalg.norm(v)))
    energy = [ch[i:i + win].sum() for i in range(0, ch.shape[0], win)]
    floor = 0.05 * float(np.median([e for e in energy if e > 0] or [0.0]))
    out = []
    for k, i in enumerate(range(0, ch.shape[0], win)):
        v = ch[i:i + win].mean(axis=0)
        start, end = i / FPS, min(i + win, ch.shape[0]) / FPS
        if energy[k] <= floor or not v.any():
            out.append({"chord": "N", "start": start, "end": end, "score": None})
            continue
        v = v - v.min()                  # drop the broadband floor before matching
        n = np.linalg.norm(v)
        if n == 0:
            out.append({"chord": "N", "start": start, "end": end, "score": None})
            continue
        lab, s = max(((lab, float(t @ v / n)) for lab, t in tmpl), key=lambda p: p[1])
        out.append({"chord": lab, "start": start, "end": end, "score": round(s, 3)})
    return out
