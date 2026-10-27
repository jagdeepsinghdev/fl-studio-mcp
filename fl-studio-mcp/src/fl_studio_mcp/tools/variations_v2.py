"""S2.2: fl_variations — rule-based variation sets for beat presets.

Pure local work: reads a beat preset, runs the variation engine
(``presets/variations.py``), writes the result JSONs to
``fl-studio-mcp/.generated/beats/`` (git-ignored, rule 10), validates them
with the preset schema validator, and returns the new ids. **No MIDI trip,
no FL contact** — applying the variations to live patterns is
``fl_preset load_beat`` + the per-step param actions (P4/S0.3, S2.3).

The engine keeps the genre skeleton (kick/snare hits of the base) and
perturbs the mutable layers (density, velocity, shift, rolls, fills).
Same (base_id, style, seed) → identical output files.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

_PRESETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "presets"
_GENERATED_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".generated"


def _load_module(name: str, path: Path):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look up sys.modules[cls.__module__]
    spec.loader.exec_module(mod)
    return mod


def _engine():
    return _load_module("fl_variations_engine", _PRESETS_DIR / "variations.py")


def _validator():
    return _load_module("fl_presets_validate", _PRESETS_DIR / "validate.py")


def fl_variations(base_id: str = "trap", count: int = 2, style: str = "humanize",
                  seed: int = 1, target: str = "") -> dict[str, Any]:
    """Generate N rule-based variations of a beat preset.

    Skeleton (kick/snare of the base) is preserved; density, velocity,
    shift, rolls and fills are perturbed. Deterministic in
    (base_id, style, seed). Results are written to
    fl-studio-mcp/.generated/beats/ as schema-validated JSON and returned
    as ids you can load with fl_preset(action="load_beat", preset=<id>).

    Args:
        base_id: beat preset id (fl_list_presets("beats")).
        count: how many variations (>= 1).
        style: subtle | humanize | spicy | shuffle | genre_shift.
            genre_shift needs ``target`` = another beat preset id; the aux
            layers + BPM come from the target, the base skeleton stays.
        seed: PRNG seed (same seed → same variations).
        target: beat preset id for genre_shift (e.g. base=house,
            target=trap → house skeleton with trap hats at trap BPM).
    """
    eng = _engine()
    base = eng.load_preset("beats", base_id)
    if base is None:
        return {"ok": False,
                "error": f"no beat preset '{base_id}'"}
    target_preset = None
    if style == "genre_shift":
        if not target:
            return {"ok": False,
                    "error": "genre_shift needs target=<beat preset id>"}
        target_preset = eng.load_preset("beats", target)
        if target_preset is None:
            return {"ok": False,
                    "error": f"no target beat preset '{target}'"}

    try:
        variations = eng.make_variations(base, count=count, style=style,
                                         seed=seed, target_preset=target_preset)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    val = _validator()
    written, errors = [], []
    d = _GENERATED_DIR / "beats"
    d.mkdir(parents=True, exist_ok=True)
    for v in variations:
        try:
            val.validate_beat(v, f"generated:{v['id']}")
        except val.PresetError as e:
            errors.append(f"{v['id']}: {e}")
            continue
        p = d / f"{v['id']}.json"
        p.write_text(json.dumps(v, indent=2) + "\n")
        written.append({"id": v["id"], "path": str(p),
                        "bpm": v.get("bpm"),
                        "steps": len(next(iter(v.get("channels", {}).values()) or {}).get("pattern", []))})

    if not written:
        return {"ok": False, "error": "; ".join(errors) or "no variations written"}
    return {"ok": True, "base": base_id, "style": style, "seed": seed,
            "ids": [w["id"] for w in written], "written": written,
            "errors": errors,
            "hint": "load any id with fl_preset(action='load_beat', preset=<id>, target_pattern=N) (the preset "
                    "loader checks .generated/ first); the per-step "
                    "velocities/shifts/repeats arrays are applied live as FL step "
                    "parameters (S2.3, via P4's setStepParameter)."}


def fl_list_generated() -> dict[str, Any]:
    """List generated variation presets (fl-studio-mcp/.generated/)."""
    out: dict[str, list[str]] = {"beats": [], "melodies": []}
    for kind in out:
        d = _GENERATED_DIR / kind
        if d.is_dir():
            out[kind] = sorted(p.stem for p in d.glob("*.json"))
    return {"ok": True, **out}


def register_variations_tools(mcp: FastMCP) -> None:
    """Register the S2 variation tools (pure local; no MIDI trip)."""
    from fl_studio_mcp.tools.variations_v2 import fl_list_generated as _impl_flg
    from fl_studio_mcp.tools.variations_v2 import fl_variations as _impl_fv

    @mcp.tool()
    def fl_variations(base_id: str = "trap", count: int = 2,
                      style: str = "humanize", seed: int = 1,
                      target: str = "") -> dict:
        """Generate N rule-based variations of a beat preset (deterministic;
        skeleton preserved; written to .generated/beats/)."""
        return _impl_fv(base_id, count, style, seed, target)

    @mcp.tool()
    def fl_list_generated() -> dict:
        """List generated variation presets (.generated/{beats,melodies}/)."""
        return _impl_flg()
