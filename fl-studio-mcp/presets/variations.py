"""Rule-based variation engine (S2 Tier-1 of the pattern & sampling plan).

Pure Python — no FL, no MCP, no I/O. Deterministic: the same
``(base preset, style, seed)`` always yields byte-identical variation JSONs.

What a variation is
-------------------
A deep copy of a beat preset whose *skeleton is preserved* and whose
*mutable layers* are perturbed:

  * skeleton  — the base preset's ``kick`` and ``snare`` hits are NEVER
    removed or moved. This is what keeps the genre's kick relationship
    invariant (house 4-on-floor, trap/dubstep half-time, DnB 2-step, ...):
    whatever the base encodes is the skeleton, and it survives untouched.
  * density   — auxiliary parts (hat, clap, open hat, perc, ...) may gain
    or lose hits by per-style probability.
  * ghosts    — low-velocity hits (velocity 64-75, the NI "ghost" band) may
    be placed on empty steps adjacent to an existing sacred hit.
  * velocity  — every hit gets an explicit velocity (1..127); main parts
    jitter downward from 127, hat/roll hits sit around ~94 (trap-roll mids).
  * shift     — per-step shift value (0..127; 0 = none). FL's
    ``channels.setStepParameterByIndex`` param id + 6th-arg semantics are
    pinned down by probe P4 (S0.3) before this is applied live.
  * repeats   — per-step note repeat (0..8) on hat parts = rolls.
  * fills     — genre-family fill patterns replace the last 4 steps of a
    bar at bar boundaries.

Output schema (extension of the beat preset schema in ``presets/README.md``;
``presets/validate.py`` accepts the extra per-part arrays)::

    {
      "id": "trap-humanize-0",
      "name": "Trap (half-time) — humanize v0",
      "bpm": 140, "swing": 0.0,
      "variation": {"style": "humanize", "seed": 7, "from": "trap"},
      "channels": {
        "kick": {"name": "808 Kick",
                 "pattern":    [1,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0],
                 "velocities": [118,0,0,0,0,0,0,124,0,0,112,0,0,0,0,0],
                 "shifts":     [0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0],
                 "repeats":    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},
        ...
      }
    }

Non-hit steps carry velocity 0 / shift 0 / repeat 0 in the arrays so every
array has exactly ``len(pattern)`` entries (simple for the FL writer).

Grids
-----
16-step (one bar, the standard preset shape) and 64-step (four bars) bases
are both supported; longer bases up to the FL 512-step sequencer cap are
accepted. ``expand_to_64`` repeats a 16-step base into a 4-bar phrase with
bar-boundary variation.

Styles
------
  subtle      small velocity jitter, almost no density change, no fills
  humanize    the default: moderate jitter/shift/ghosts, occasional rolls
  spicy       high density change, frequent rolls, fill every 2nd bar
  genre_shift swap the auxiliary layers + BPM for another genre preset
              (``target`` arg); the base skeleton (kick/snare) is kept
  shuffle     like ``spicy`` but with a re-rolled, salted seed (each
              variation i uses ``seed * 7919 + i``)

``melody`` is not a beat style: melody presets pass through unchanged —
a variation only re-rolls the drums, the notes stay (that is what makes a
set of variations a *variation set* rather than a new song).
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Limits (FL sequencer: 512 steps max — manual; keep every array consistent)
# ---------------------------------------------------------------------------
MAX_STEPS = 512
VEL_MIN, VEL_MAX = 1, 127
GHOST_VEL_MIN, GHOST_VEL_MAX = 64, 75      # NI ghost-note band
HAT_ROLL_VEL = 94                          # trap-roll mids
SHIFT_MIN, SHIFT_MAX = 0, 127             # param semantics pending P4
REPEAT_MIN, REPEAT_MAX = 0, 8

#: Parts whose hits are NEVER removed or moved. ``kick``/``snare`` are the
#: genre skeleton for every family we know (house 4-on-floor, trap/dubstep
#: half-time, DnB 2-step, boom-bap, reggaeton — the dembow part is treated
#: as sacred for reggaeton-style presets because it IS the kick relationship).
SACRED_PARTS = ("kick", "snare", "dembow")

#: Parts eligible for density change / rolls / fills.
AUX_PARTS = ("hat", "open_hat", "clap", "perc", "rim", "shaker", "ride")

#: Velocity jitter (downward from 127) per part family.
_VELOCITY_JITTER = {
    "kick": 14, "snare": 12, "dembow": 10,
    "hat": 18, "open_hat": 18, "clap": 14, "perc": 16, "rim": 12,
    "shaker": 20, "ride": 16,
}
_DEFAULT_JITTER = 14


def _jitter(part: str) -> int:
    return _VELOCITY_JITTER.get(part, _DEFAULT_JITTER)


def _is_sacred(part: str) -> bool:
    return part.lower() in SACRED_PARTS


def _is_aux(part: str) -> bool:
    return part.lower() in AUX_PARTS or not _is_sacred(part)


# ---------------------------------------------------------------------------
# Style parameters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StyleSpec:
    """Probabilities/budgets for one variation style."""
    jitter: int = 10            # max downward velocity jitter, main parts
    aux_jitter: int = 16        # max downward jitter, auxiliary parts
    p_shift: float = 0.15       # per hit step: apply a small shift
    shift_range: tuple[int, int] = (1, 8)
    p_ghost: float = 0.10       # per sacred part: add a ghost hit on an
                                # empty adjacent step
    p_add_aux: float = 0.05     # per aux empty step: add a hit
    p_del_aux: float = 0.08     # per aux hit step: remove it
    p_roll: float = 0.10        # per hat hit step: set a repeat count
    roll_range: tuple[int, int] = (1, 3)
    fill_every_n_bars: int = 0  # 0 = no fills; n = at most 1 fill per n bars
    salt: int = 0               # seed salt for shuffle-style re-rolls


STYLES: dict[str, StyleSpec] = {
    "subtle": StyleSpec(jitter=5, aux_jitter=8, p_shift=0.06,
                        shift_range=(1, 4), p_ghost=0.03,
                        p_add_aux=0.02, p_del_aux=0.03, p_roll=0.03,
                        roll_range=(1, 1)),
    "humanize": StyleSpec(jitter=10, aux_jitter=16, p_shift=0.15,
                          shift_range=(1, 8), p_ghost=0.10,
                          p_add_aux=0.05, p_del_aux=0.08, p_roll=0.10,
                          roll_range=(1, 3), fill_every_n_bars=0),
    "spicy": StyleSpec(jitter=14, aux_jitter=20, p_shift=0.22,
                       shift_range=(1, 12), p_ghost=0.16,
                       p_add_aux=0.10, p_del_aux=0.14, p_roll=0.22,
                       roll_range=(1, 4), fill_every_n_bars=2),
    "shuffle": StyleSpec(jitter=16, aux_jitter=22, p_shift=0.25,
                         shift_range=(1, 14), p_ghost=0.18,
                         p_add_aux=0.12, p_del_aux=0.16, p_roll=0.25,
                         roll_range=(1, 5), fill_every_n_bars=2,
                         salt=7919),
    # mutation level for genre_shift: the aux layers/BPM come from the
    # target preset, then humanize-level mutation is applied to everything
    "genre_shift": StyleSpec(jitter=10, aux_jitter=16, p_shift=0.15,
                             shift_range=(1, 8), p_ghost=0.10,
                             p_add_aux=0.05, p_del_aux=0.08, p_roll=0.10,
                             roll_range=(1, 3), fill_every_n_bars=0),
}

#: Fill libraries per genre *family*. Each fill is a dict part -> 4 values
#: (applied to the LAST 4 steps of a bar). Values are hits (1) or the string
#: "ghost" (hit at ghost velocity) or "roll" (hit + repeat).
FILLS: dict[str, list[dict[str, Any]]] = {
    "four_on_floor": [
        {"hat": [0, 1, 1, 1], "snare": [0, 0, 0, "ghost"]},
        {"open_hat": [0, 0, 1, 1], "clap": [0, 0, 0, "ghost"]},
        {"hat": [1, "roll", 1, "roll"], "snare": [0, 0, "ghost", 1]},
    ],
    "half_time": [
        {"hat": [1, "roll", 1, "roll"], "snare": [0, 0, 0, 1]},
        {"open_hat": [0, 1, 1, 1], "clap": [0, 0, "ghost", "ghost"]},
        {"hat": [0, 1, "roll", 1], "kick": [0, 0, 0, "ghost"]},
    ],
    "dnb": [
        {"hat": [1, "roll", 1, "roll"], "snare": [0, "ghost", 1, 1]},
        {"open_hat": [0, 0, 1, "roll"], "rim": [0, 1, 0, 1]},
    ],
    "boom_bap": [
        {"hat": [0, 1, "roll", 1], "snare": [0, 0, "ghost", 1]},
        {"clap": [0, 1, 0, "ghost"], "hat": [1, 1, "roll", "roll"]},
    ],
    "dembow": [
        {"hat": [1, "roll", 1, "roll"], "clap": [0, 0, "ghost", 1]},
        {"shaker": [1, 1, 1, 1], "rim": [0, 1, 0, 1]},
    ],
    "default": [
        {"hat": [0, 1, "roll", 1], "snare": [0, 0, "ghost", 1]},
        {"clap": [0, 1, 0, "ghost"], "open_hat": [0, 0, 1, 1]},
    ],
}

#: Known preset ids -> genre family (for fill selection + genre_shift).
#: Unknown ids fall back to ``default`` fills and family ``default``.
FAMILY_BY_PRESET: dict[str, str] = {
    "house": "four_on_floor",
    "lofi": "boom_bap",
    "boom-bap": "boom_bap",
    "trap": "half_time",
    "drill": "half_time",
    "drill-displaced": "half_time",
    "reggaeton": "dembow",
    "punjabi-banger": "dembow",
}

#: Family -> representative preset id, used by ``genre_shift`` (aux layers +
#: BPM are taken from the representative of the target family).
FAMILY_REPRESENTATIVE: dict[str, str] = {
    "four_on_floor": "house",
    "half_time": "trap",
    "dnb": "drill",
    "boom_bap": "boom-bap",
    "dembow": "reggaeton",
}


def family_for(preset_id: str) -> str:
    return FAMILY_BY_PRESET.get(preset_id, "default")


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------
def _clamp_grid(length: int) -> None:
    if length < 1:
        raise ValueError(f"pattern length {length} < 1")
    if length > MAX_STEPS:
        raise ValueError(
            f"pattern length {length} exceeds the FL 512-step sequencer cap")


def expand_to_64(base: dict[str, Any]) -> dict[str, Any]:
    """Repeat a 16-step base into a 4-bar (64-step) phrase (deep copy)."""
    out = copy.deepcopy(base)
    for spec in out.get("channels", {}).values():
        pat = spec.get("pattern", [])
        if len(pat) == 16:
            spec["pattern"] = list(pat) * 4
    return out


# ---------------------------------------------------------------------------
# Core variation of one preset
# ---------------------------------------------------------------------------
def _make_rng(seed: int, index: int, salt: int) -> random.Random:
    return random.Random((seed * 1000003 + index * 7 + salt) % (2**32))


def _base_velocity(part: str, spec: dict[str, Any]) -> int:
    """The preset's own velocity for a hit step (explicit or default)."""
    per_step = spec.get("velocities")
    if isinstance(per_step, list) and len(per_step) == len(spec.get("pattern", [])):
        v = per_step
        # v may already carry 0 for non-hits; callers only ask for hits
        return int(v[0] or 127)
    return 127


def _variant_part(part: str, base_spec: dict[str, Any], rng: random.Random,
                  style: StyleSpec) -> dict[str, Any]:
    """Apply the mutable layers to one part; sacred hits are preserved."""
    pat = [1 if x else 0 for x in base_spec.get("pattern", [0] * 16)]
    n = len(pat)
    if n == 0:
        n = 16
        pat = [0] * n
    _clamp_grid(n)
    sacred = _is_sacred(part)

    # 1) density (aux parts only)
    if not sacred:
        for i in range(n):
            if pat[i] and rng.random() < style.p_del_aux:
                pat[i] = 0
            elif not pat[i] and rng.random() < style.p_add_aux:
                pat[i] = 1

    # 2) ghosts on sacred parts: empty step adjacent (±1, ±2) to a hit
    if sacred and style.p_ghost > 0:
        for i, v in enumerate(pat):
            if v and rng.random() < style.p_ghost:
                j = i + rng.choice((-1, 1, -2, 2))
                if 0 <= j < n and not pat[j]:
                    pat[j] = 1  # one ghost per sacred hit, at most

    # 3) per-step arrays
    velocities = [0] * n
    shifts = [0] * n
    repeats = [0] * n
    jitter = style.jitter if sacred else style.aux_jitter
    is_hat = part.lower() in ("hat", "open_hat", "ride", "shaker")
    for i, v in enumerate(pat):
        if not v:
            continue
        if _is_ghost_candidate(part, base_spec, i):
            velocities[i] = rng.randint(GHOST_VEL_MIN, GHOST_VEL_MAX)
        elif is_hat:
            velocities[i] = max(VEL_MIN, HAT_ROLL_VEL + rng.randint(-jitter, 0))
        else:
            velocities[i] = max(VEL_MIN, 127 - rng.randint(0, jitter))
        if rng.random() < style.p_shift:
            shifts[i] = rng.randint(*style.shift_range)
        if is_hat and rng.random() < style.p_roll:
            repeats[i] = rng.randint(*style.roll_range)

    out = dict(base_spec)
    out["pattern"] = pat
    out["velocities"] = velocities
    out["shifts"] = shifts
    out["repeats"] = repeats
    return out


def _is_ghost_candidate(part: str, base_spec: dict[str, Any], i: int) -> bool:
    """A step is a ghost when the base preset already marked it one, or the
    base had no hit there (i.e. this engine just added it as a ghost)."""
    base_pat = base_spec.get("pattern", [])
    base_vel = base_spec.get("velocities")
    if isinstance(base_vel, list) and i < len(base_vel) and 0 < base_vel[i] <= GHOST_VEL_MAX:
        return True
    if i < len(base_pat) and not base_pat[i]:
        # added by density/ghost pass -> treat as ghost only for sacred parts
        return part.lower() in SACRED_PARTS
    return False


def _apply_fills(specs: dict[str, dict], n: int, family: str,
                 rng: random.Random, style: StyleSpec) -> None:
    """Replace the last 4 steps of selected bars with a genre-family fill.
    Bar = 16 steps. Fills never delete sacred hits outside the bar they
    replace; inside the replaced 4 steps a sacred hit may be overwritten
    only by a fill marked for that part (skeleton beats of the bar are
    protected: a fill step for a sacred part keeps any pre-existing hit)."""
    if style.fill_every_n_bars <= 0 or n % 16 != 0:
        return
    libs = FILLS.get(family, FILLS["default"])
    bars = n // 16
    for bar in range(bars):
        if rng.random() > (1.0 / style.fill_every_n_bars) * 0.5:
            continue
        fill = rng.choice(libs)
        for part, seq in fill.items():
            if part not in specs:
                continue
            spec = specs[part]
            pat = spec["pattern"]
            for k, token in enumerate(seq):
                i = bar * 16 + (12 + k)
                if i >= n:
                    break
                hit = 1 if token in (1, "ghost", "roll") else 0
                if token == 0:
                    # only clear non-sacred hits (keep the skeleton)
                    if not _is_sacred(part) and pat[i]:
                        pat[i] = 0
                        spec["velocities"][i] = 0
                        spec["shifts"][i] = 0
                        spec["repeats"][i] = 0
                    continue
                was_hit = bool(pat[i])
                pat[i] = 1
                if token == "ghost" or (was_hit == False and _is_sacred(part)):
                    # new hits on sacred parts stay ghost-velocity (the
                    # skeleton invariant: added sacred hits are soft fills)
                    spec["velocities"][i] = rng.randint(GHOST_VEL_MIN, GHOST_VEL_MAX)
                elif token == "roll":
                    spec["velocities"][i] = rng.randint(HAT_ROLL_VEL - 6, HAT_ROLL_VEL + 6)
                    spec["repeats"][i] = max(spec["repeats"][i],
                                            rng.randint(1, 3))
                else:
                    spec["velocities"][i] = max(VEL_MIN,
                                               spec["velocities"][i] or 127)


def vary_beat(base: dict[str, Any], style: str = "humanize",
              seed: int = 0, index: int = 0,
              target_preset: dict[str, Any] | None = None) -> dict[str, Any]:
    """One variation of ``base``.

    ``target_preset`` is only used by the ``genre_shift`` style: the
    auxiliary layers and BPM come from it, the base's sacred skeleton and
    the caller's melody are kept.
    """
    if style not in STYLES:
        raise ValueError(f"unknown style '{style}'; known: {sorted(STYLES)}")
    spec = STYLES[style]
    rng = _make_rng(seed, index, spec.salt)

    src = dict(base)
    if style == "genre_shift":
        if target_preset is None:
            raise ValueError("genre_shift needs a target preset")
        # keep the skeleton parts + melody-ish metadata from base, take aux
        # layers and BPM from the target family representative
        for part, s in list(src.get("channels", {}).items()):
            if _is_sacred(part):
                continue
            t = target_preset.get("channels", {}).get(part)
            if t is not None:
                src["channels"][part] = dict(t)
        if target_preset.get("bpm"):
            src["bpm"] = target_preset["bpm"]

    out = copy.deepcopy(src)
    family = family_for(str(base.get("id", "")))
    channels = out.setdefault("channels", {})
    for part, s in channels.items():
        channels[part] = _variant_part(part, s, rng, spec)
    if len(channels):
        n = max(len(s.get("pattern", [])) for s in channels.values())
        _apply_fills(channels, n, family, rng, spec)

    out["id"] = f"{base.get('id', 'base')}-{style}-{index}"
    out["name"] = f"{base.get('name', 'Variation')} — {style} v{index}"
    out["variation"] = {
        "style": style,
        "seed": seed,
        "index": index,
        "from": base.get("id"),
        "target": (target_preset or {}).get("id"),
    }
    return out


def make_variations(base: dict[str, Any], count: int = 2,
                    style: str = "humanize", seed: int = 1,
                    target_preset: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """``count`` variations of ``base``; deterministic in (base, style, seed)."""
    if count < 1:
        raise ValueError("count must be >= 1")
    if style == "genre_shift" and target_preset is None:
        raise ValueError("genre_shift needs a target preset")
    return [vary_beat(base, style=style, seed=seed, index=i,
                      target_preset=target_preset) for i in range(count)]


# ---------------------------------------------------------------------------
# File helpers (used by the MCP tool; kept here so the engine + I/O share
# one schema definition)
# ---------------------------------------------------------------------------
def preset_dir(kind: str = "beats") -> Path:
    return Path(__file__).resolve().parent / kind


def load_preset(kind: str, preset_id: str) -> dict[str, Any] | None:
    p = preset_dir(kind) / f"{preset_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def generated_dir(kind: str = "beats") -> Path:
    d = Path(__file__).resolve().parent.parent / ".generated" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_generated(variation: dict[str, Any], kind: str = "beats") -> Path:
    d = generated_dir(kind)
    p = d / f"{variation['id']}.json"
    p.write_text(json.dumps(variation, indent=2) + "\n")
    return p
