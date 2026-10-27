"""S2.1: variation engine — deterministic rule-based beat variations.

Verified offline (no FL, no MIDI):
  - determinism: same (base, style, seed) → identical output; different seed
    → different output
  - skeleton invariant: kick/snare hits of the base are never removed or
    moved (the genre kick relationship survives every style)
  - velocity/shift/repeat bounds (ghost 64-75, hat rolls ~94, shift 0..127)
  - 16- and 64-step grids; 512-step FL cap enforced
  - genre_shift swaps BPM + aux layers while keeping the skeleton
  - fills land on bar boundaries; 64-step phrases get bar fills
  - schema: every generated preset passes presets/validate.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PRESETS = Path(__file__).resolve().parent.parent / "presets"


def _mod(name: str, fname: str):
    import sys
    spec = importlib.util.spec_from_file_location(name, _PRESETS / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m  # required: dataclasses look up sys.modules[cls.__module__]
    spec.loader.exec_module(m)
    return m


var = _mod("variations_test", "variations.py")
val = _mod("validate_test", "validate.py")


def _base(beat_id: str = "trap") -> dict:
    return json.loads((_PRESETS / "beats" / f"{beat_id}.json").read_text())


def _hits(spec: dict) -> list[int]:
    return [i for i, v in enumerate(spec["pattern"]) if v]


def _all_parts(v: dict) -> list[tuple[str, dict]]:
    return list(v["channels"].items())


def _skeleton(v: dict, part: str) -> list[int]:
    return _hits(v["channels"][part])


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_same_seed_same_output():
    base = _base()
    a = var.make_variations(base, 3, "humanize", seed=42)
    b = var.make_variations(base, 3, "humanize", seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_different_seed_different_output():
    base = _base()
    a = var.make_variations(base, 1, "spicy", seed=1)
    b = var.make_variations(base, 1, "spicy", seed=999)
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)


def test_shuffle_is_seeded_reproducible():
    base = _base()
    a = var.make_variations(base, 2, "shuffle", seed=7)
    b = var.make_variations(base, 2, "shuffle", seed=7)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# Skeleton invariant
# ---------------------------------------------------------------------------
def _assert_skeleton_preserved(base: dict, out: dict):
    for part in ("kick", "snare", "dembow"):
        if part not in base.get("channels", {}):
            continue
        base_hits = set(_skeleton(base, part))
        out_spec = out["channels"][part]
        out_hits = set(_skeleton(out, part))
        # every original hit survives (never removed, never moved)
        assert base_hits <= out_hits, \
            f"{part} skeleton lost hits: base {sorted(base_hits)} vs out {sorted(out_hits)}"
        # any ADDED hit on a sacred part must be a ghost (64-75)
        for i in out_hits - base_hits:
            vel = out_spec["velocities"][i]
            assert var.GHOST_VEL_MIN <= vel <= var.GHOST_VEL_MAX, \
                f"{part} step {i}: added hit vel {vel} outside ghost band"


@pytest.mark.parametrize("beat", ["trap", "house", "reggaeton", "boom-bap", "lofi"])
def test_skeleton_preserved_per_genre(beat):
    base = _base(beat)
    for v in var.make_variations(base, 2, "spicy", seed=3):
        _assert_skeleton_preserved(base, v)


def test_skeleton_preserved_on_64step():
    base = var.expand_to_64(_base("house"))
    for v in var.make_variations(base, 2, "spicy", seed=5):
        _assert_skeleton_preserved(base, v)


def test_64step_grid_length():
    base = var.expand_to_64(_base("trap"))
    for part, spec in base["channels"].items():
        assert len(spec["pattern"]) == 64
    v = var.make_variations(base, 1, "humanize", seed=1)[0]
    for part, spec in v["channels"].items():
        assert len(spec["pattern"]) == 64
        for arr in ("velocities", "shifts", "repeats"):
            assert len(spec[arr]) == 64


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------
def test_velocity_bounds_all_parts():
    for v in var.make_variations(_base("trap"), 2, "spicy", seed=11):
        for part, spec in v["channels"].items():
            for i, vel in enumerate(spec["velocities"]):
                if spec["pattern"][i]:
                    assert var.VEL_MIN <= vel <= var.VEL_MAX, (part, i, vel)
                else:
                    assert vel == 0, (part, i, vel)


def test_ghost_velocity_band():
    base = _base("trap")
    v = var.make_variations(base, 6, "spicy", seed=1234)[0]
    ghosts = 0
    for part, spec in v["channels"].items():
        for i, vel in enumerate(spec["velocities"]):
            if spec["pattern"][i] and var.GHOST_VEL_MIN <= vel <= var.GHOST_VEL_MAX:
                ghosts += 1
    assert ghosts >= 1, "spicy should have produced at least one ghost note"


def test_shift_bounds_and_default_zero():
    v = var.make_variations(_base("house"), 1, "spicy", seed=2)[0]
    for part, spec in v["channels"].items():
        for i, s in enumerate(spec["shifts"]):
            assert var.SHIFT_MIN <= s <= var.SHIFT_MAX
            if spec["pattern"][i] == 0:
                assert s == 0


def test_repeat_bounds_hat_only():
    v = var.make_variations(_base("trap"), 4, "spicy", seed=33)[0]
    for part, spec in v["channels"].items():
        for i, r in enumerate(spec["repeats"]):
            assert var.REPEAT_MIN <= r <= var.REPEAT_MAX
            if part not in ("hat", "open_hat", "ride", "shaker"):
                assert r == 0, f"repeats only on hat-family parts, got {part}"


# ---------------------------------------------------------------------------
# 512-step cap
# ---------------------------------------------------------------------------
def _long_base(n: int) -> dict:
    return {"id": "long", "name": "Long", "bpm": 120,
            "channels": {"kick": {"name": "K", "pattern": [1] * n},
                         "hat": {"name": "H", "pattern": [1] * n}}}


def test_512_step_cap_ok():
    v = var.make_variations(_long_base(512), 1, "subtle", seed=1)[0]
    assert len(v["channels"]["kick"]["pattern"]) == 512


def test_over_512_rejected():
    with pytest.raises(ValueError, match="512"):
        var.make_variations(_long_base(513), 1, "subtle", seed=1)


# ---------------------------------------------------------------------------
# Genre shift
# ---------------------------------------------------------------------------
def test_genre_shift_swaps_bpm_and_keeps_skeleton():
    base = _base("house")          # four-on-floor skeleton, ~120s BPM
    target = _base("trap")         # half-time, 140
    v = var.make_variations(base, 1, "genre_shift", seed=1,
                            target_preset=target)[0]
    assert v["bpm"] == target["bpm"]
    _assert_skeleton_preserved(base, v)   # house kick/snare survive
    assert v["variation"]["target"] == "trap"


def test_genre_shift_requires_target():
    with pytest.raises(ValueError):
        var.make_variations(_base("house"), 1, "genre_shift", seed=1)


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------
def _clean_64(base: dict, part: str) -> dict:
    p = base["channels"][part]["pattern"]
    if len(p) == 16:
        p = p * 4
    return {"name": "X", "pattern": list(p),
            "velocities": [127 if x else 0 for x in p],
            "shifts": [0] * len(p), "repeats": [0] * len(p)}


def test_fills_only_touch_bar_tail_windows():
    base = _base("house")
    style = var.STYLES["spicy"]
    # find a seed that actually fires at least one fill (deterministic scan)
    chosen, before = None, None
    for s in range(30):
        rng = var.random.Random(s)
        specs = {part: _clean_64(base, part) for part in base["channels"]}
        before = {part: list(sp["pattern"]) for part, sp in specs.items()}
        var._apply_fills(specs, 64, "four_on_floor", rng, style)
        if any(specs[p]["pattern"] != before[p] for p in specs):
            chosen, specs = s, specs
            break
    assert chosen is not None, "no fill fired in seeds 0..29 (fill prob too low?)"
    for part, sp in specs.items():
        b = before[part]
        for bar in range(4):
            # outside the last-4 window of each bar: untouched
            for i in range(bar * 16, bar * 16 + 12):
                assert sp["pattern"][i] == b[i], f"fill leaked at {part}:{i}"
    print(f"(fill fired on seed {chosen})")


def test_fills_never_clear_sacred_hits():
    base = _base("house")
    style = var.STYLES["spicy"]
    rng = var.random.Random(5)
    specs = {part: _clean_64(base, part) for part in base["channels"]}
    before = {part: list(s["pattern"]) for part, s in specs.items()}
    var._apply_fills(specs, 64, "four_on_floor", rng, style)
    for part in ("kick", "snare"):
        for i, b in enumerate(before[part]):
            if b:
                assert specs[part]["pattern"][i] == 1, \
                    f"fill cleared a sacred {part} hit at {i}"


# ---------------------------------------------------------------------------
# Style behavior + schema
# ---------------------------------------------------------------------------
def test_subtle_changes_less_than_spicy():
    """Total mutation volume (added+removed hits, shifts, rolls, ghosts)
    must be higher for spicy than subtle — measured against the base."""
    base = _base("trap")
    seeds = range(1, 6)

    def mutation_volume(v: dict, base: dict) -> int:
        vol = 0
        for part, s in v["channels"].items():
            b = base["channels"].get(part, {}).get("pattern", [])
            for i, on in enumerate(s["pattern"]):
                was = bool(b[i]) if i < len(b) else False
                if on != was:
                    vol += 1
                if on:
                    vol += (1 if s["shifts"][i] else 0) + (1 if s["repeats"][i] else 0)
            vol += sum(1 for vel in s["velocities"] if 0 < vel <= var.GHOST_VEL_MAX)
        return vol

    sub = sum(mutation_volume(var.make_variations(base, 1, "subtle", seed=s)[0], base)
              for s in seeds)
    spi = sum(mutation_volume(var.make_variations(base, 1, "spicy", seed=s)[0], base)
              for s in seeds)
    assert spi > sub, f"spicy mutation volume ({spi}) should exceed subtle ({sub})"


def test_generated_passes_schema_validator():
    base = _base("trap")
    for v in var.make_variations(base, 3, "spicy", seed=8):
        val.validate_beat(v, f"test:{v['id']}")


def test_ids_unique_and_named():
    vs = var.make_variations(_base("lofi"), 4, "humanize", seed=1)
    ids = [v["id"] for v in vs]
    assert len(set(ids)) == 4
    assert all(i.startswith("lofi-humanize-") for i in ids)


def test_variations_tool_end_to_end(tmp_path, monkeypatch):
    """S2.2: fl_variations writes schema-valid JSONs to .generated/."""
    import fl_studio_mcp.tools.variations_v2 as vv
    vv._GENERATED_DIR = tmp_path / ".generated"
    r = vv.fl_variations(base_id="trap", count=2, style="humanize", seed=9)
    assert r["ok"], r
    assert len(r["ids"]) == 2
    for w in r["written"]:
        p = Path(w["path"])
        assert p.exists()
        data = json.loads(p.read_text())
        val.validate_beat(data, w["id"])
    r2 = vv.fl_list_generated()
    assert r2["ok"] and set(r["ids"]) <= set(r2["beats"])
