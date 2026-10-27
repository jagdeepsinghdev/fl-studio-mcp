"""Deterministic humanization for GENERATED notes (chord text, token melodies).

A grid of equal-velocity notes sounds like a metronome. These helpers keep every pitch and
the bar structure, and change only velocity, tiny start offsets and durations. Output is
deterministic for the same input (seeded), so a re-write gives the same take.
Explicit `notes=[...]` from the caller are never touched. Theory: music-theory
`melody-layering.md` §4, `chord-emotion.md` §4; recipe: fl-melody `chord-practice.md`.
"""
from __future__ import annotations

import random
from collections import defaultdict


def _clamp(v: float, lo: float = 0.3, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def humanize_chords(notes: list[dict], seed: str = "") -> list[dict]:
    """Chord onsets (notes sharing a start time): lowest note strongest, upper notes softer,
    a light upward strum, and each chord a little shorter than its slot so it breathes."""
    rng = random.Random(f"chords:{seed}")
    groups: dict[float, list[dict]] = defaultdict(list)
    for n in notes:
        groups[n["time"]].append(n)
    out: list[dict] = []
    for t in sorted(groups):
        for rank, n in enumerate(sorted(groups[t], key=lambda x: x["midi"])):
            m = dict(n)
            base = float(n.get("velocity", 0.7))
            f = 1.15 if rank == 0 else 0.86 - 0.04 * min(rank, 4)
            m["velocity"] = round(_clamp(base * f + rng.uniform(-0.03, 0.03)), 3)
            m["time"] = round(t + (0.0 if rank == 0 else rank * 0.012 + rng.uniform(0, 0.006)), 4)
            dur = float(n["duration"])
            m["duration"] = round(max(0.1, dur * (0.92 + rng.uniform(-0.02, 0.02)) - 0.02 * rank), 4)
            out.append(m)
    return out


def humanize_melody(notes: list[dict], seed: str = "") -> list[dict]:
    """Single-line notes (4/4): accent bar start and beat 3, soften off-beats, drift off-beat
    starts by a few hundredths of a beat (never the first note of a bar), vary lengths slightly."""
    rng = random.Random(f"melody:{seed}")
    out: list[dict] = []
    for n in notes:
        m = dict(n)
        t = float(n["time"])
        pos, frac = t % 4, t % 1
        if abs(pos) < 1e-6:
            f = 1.12                    # bar start
        elif abs(pos - 2) < 1e-6:
            f = 1.04                    # beat 3
        elif abs(frac) < 1e-6:
            f = 0.95                    # other beats
        else:
            f = 0.82                    # off-beat
        base = float(n.get("velocity", 0.8))
        m["velocity"] = round(_clamp(base * f + rng.uniform(-0.04, 0.04)), 3)
        if abs(pos) >= 1e-6:
            m["time"] = round(max(0.0, t + rng.uniform(-0.02, 0.025)), 4)
        m["duration"] = round(max(0.05, float(n["duration"]) * rng.uniform(0.92, 1.0)), 4)
        out.append(m)
    return out
