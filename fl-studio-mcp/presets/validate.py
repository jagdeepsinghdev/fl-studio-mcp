"""Preset schema validator for the FL Studio MCP presets.

This is the single source of truth for the preset schema described in
``presets/README.md``. It is used by the pytest suite (which runs in CI) and
can also be run directly from a terminal::

    python3 presets/validate.py            # validate presets in this dir
    python3 presets/validate.py /some/dir  # validate an explicit directory

Why this file exists
--------------------
The presets are the *actual* product of this repo — they are JSON data that the
MCP server reads at runtime (``fl_preset`` in
``src/fl_studio_mcp/tools/preset_v2.py``) and that ``fl_set_step_sequence`` /
the piano-roll request queue consume. A typo in a pattern length or an out-of-range
MIDI number would make a preset silently misbehave ("plays then goes empty") or
silently drop notes. Nothing else in the repo validates this, so this module is
the guardrail.

The checks mirror the documented schema exactly:

Beat presets (``beats/*.json``)
    required: id, name, bpm, channels
    optional: swing, length_beats
    channels: dict of {part: {"name": str, "pattern": [0|1 x 16]}}
        - pattern MUST be 16 ints in {0, 1}  (a 4-beat / one-bar step sequencer)
        - every part must carry a "name" that resolves to a real channel

Melody presets (``melodies/*.json``)
    required: id, name, (melody OR chords)
    optional: key, bpm, scale, channel, length_beats, notes
    melody: list of {note, step, dur, vel?}
        - note  : int 0..127
        - step  : int >= 0   (16th-note grid: 4 per beat)
        - dur   : int > 0
        - vel   : int 0..127 (default 80)
    chords: list of {notes: [int], step, dur}
        - each note 0..127, step >= 0, dur > 0
    length_beats: int >= 1 (beats, not steps)

Validation is intentionally *strict* for structure but does NOT require every
optional field, so adding a preset stays low-friction (drop a JSON, done).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MIDI_MIN = 0
MIDI_MAX = 127
VEL_MIN = 0
VEL_MAX = 127
BEAT_PATTERN_LEN = 16  # one bar of 16th-note steps
BEAT_MAX_BARS = 4      # multi-bar beats (bars that differ: fills, ghost notes) up to 4 bars


class PresetError(ValueError):
    """Raised when a preset object violates the schema."""


def _require_int(obj: dict, field: str, ctx: str, *, ge: int | None = None,
                 gt: int | None = None) -> int:
    if field not in obj:
        raise PresetError(f"{ctx}: missing required field '{field}'")
    val = obj[field]
    if isinstance(val, bool) or not isinstance(val, int):
        raise PresetError(f"{ctx}: '{field}' must be an int, got {type(val).__name__}")
    if ge is not None and val < ge:
        raise PresetError(f"{ctx}: '{field}' must be >= {ge}, got {val}")
    if gt is not None and val <= gt:
        raise PresetError(f"{ctx}: '{field}' must be > {gt}, got {val}")
    return val


def _require_str(obj: dict, field: str, ctx: str) -> str:
    if field not in obj:
        raise PresetError(f"{ctx}: missing required field '{field}'")
    val = obj[field]
    if not isinstance(val, str) or not val.strip():
        raise PresetError(f"{ctx}: '{field}' must be a non-empty string")
    return val


def _midis(obj: dict, field: str, ctx: str) -> list[int]:
    """Validate a list of MIDI note numbers (used by chords)."""
    if field not in obj or not isinstance(obj[field], list) or not obj[field]:
        raise PresetError(f"{ctx}: '{field}' must be a non-empty list of ints")
    out = []
    for i, n in enumerate(obj[field]):
        if isinstance(n, bool) or not isinstance(n, int):
            raise PresetError(f"{ctx}: '{field}[{i}]' must be an int")
        if not (MIDI_MIN <= n <= MIDI_MAX):
            raise PresetError(f"{ctx}: '{field}[{i}]'={n} out of MIDI range {MIDI_MIN}-{MIDI_MAX}")
        out.append(n)
    return out


# ---------------------------------------------------------------------------
# Beat presets
# ---------------------------------------------------------------------------

def validate_beat(data: dict, source: str = "<preset>") -> dict:
    """Validate a beat preset object. Returns the (unchanged) object on success."""
    if not isinstance(data, dict):
        raise PresetError(f"{source}: top-level JSON must be an object")

    _require_str(data, "id", source)
    _require_str(data, "name", source)
    _require_int(data, "bpm", source, ge=1)

    # swing is optional; if present it must be a fraction 0..1 (e.g. 0.05)
    if "swing" in data:
        sw = data["swing"]
        if isinstance(sw, bool) or not isinstance(sw, (int, float)):
            raise PresetError(f"{source}: 'swing' must be a number 0..1")
        if not (0.0 <= sw <= 1.0):
            raise PresetError(f"{source}: 'swing' must be in 0..1, got {sw}")

    # length_beats (beats, not steps) — optional, must be >= 1
    if "length_beats" in data:
        _require_int(data, "length_beats", source, ge=1)

    channels = data.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise PresetError(f"{source}: 'channels' must be a non-empty object")

    for part, spec in channels.items():
        ctx = f"{source}: channels['{part}']"
        if not isinstance(spec, dict):
            raise PresetError(f"{ctx}: must be an object")
        _require_str(spec, "name", ctx)
        pattern = spec.get("pattern")
        if not isinstance(pattern, list):
            raise PresetError(f"{ctx}: 'pattern' must be a list")
        if len(pattern) % BEAT_PATTERN_LEN or not (
                BEAT_PATTERN_LEN <= len(pattern) <= BEAT_PATTERN_LEN * BEAT_MAX_BARS):
            raise PresetError(
                f"{ctx}: 'pattern' must have {BEAT_PATTERN_LEN} steps per bar, 1-{BEAT_MAX_BARS} "
                f"bars (16/32/48/64), got {len(pattern)}"
            )
        for arr in ("velocities", "shifts", "repeats"):
            if arr in spec and len(spec[arr]) != len(pattern):
                raise PresetError(f"{ctx}: '{arr}' must match the pattern length ({len(pattern)})")
        for i, step in enumerate(pattern):
            if isinstance(step, bool) or step not in (0, 1):
                raise PresetError(
                    f"{ctx}: 'pattern[{i}]' must be 0 or 1, got {step!r}"
                )

    return data


# ---------------------------------------------------------------------------
# Melody presets
# ---------------------------------------------------------------------------

def _validate_melody_note(n: dict, ctx: str) -> None:
    if not isinstance(n, dict):
        raise PresetError(f"{ctx}: each melody note must be an object")
    note = _require_int(n, "note", ctx, ge=MIDI_MIN)
    if note > MIDI_MAX:
        raise PresetError(f"{ctx}: 'note'={note} out of MIDI range {MIDI_MIN}-{MIDI_MAX}")
    _require_int(n, "step", ctx, ge=0)
    _require_int(n, "dur", ctx, gt=0)
    if "vel" in n:
        vel = n["vel"]
        if isinstance(vel, bool) or not isinstance(vel, int):
            raise PresetError(f"{ctx}: 'vel' must be an int")
        if not (VEL_MIN <= vel <= VEL_MAX):
            raise PresetError(f"{ctx}: 'vel'={vel} out of range {VEL_MIN}-{VEL_MAX}")


def _validate_chord(c: dict, ctx: str) -> None:
    if not isinstance(c, dict):
        raise PresetError(f"{ctx}: each chord must be an object")
    _midis(c, "notes", ctx)
    _require_int(c, "step", ctx, ge=0)
    _require_int(c, "dur", ctx, gt=0)


def validate_melody(data: dict, source: str = "<preset>") -> dict:
    """Validate a melody preset object. Returns the (unchanged) object on success."""
    if not isinstance(data, dict):
        raise PresetError(f"{source}: top-level JSON must be an object")

    _require_str(data, "id", source)
    _require_str(data, "name", source)

    if "bpm" in data:
        _require_int(data, "bpm", source, ge=1)
    if "length_beats" in data:
        _require_int(data, "length_beats", source, ge=1)

    melody = data.get("melody", [])
    chords = data.get("chords", [])
    if not melody and not chords:
        raise PresetError(f"{source}: must define a non-empty 'melody' or 'chords' list")

    if not isinstance(melody, list):
        raise PresetError(f"{source}: 'melody' must be a list")
    for i, n in enumerate(melody):
        _validate_melody_note(n, f"{source}: melody[{i}]")

    if not isinstance(chords, list):
        raise PresetError(f"{source}: 'chords' must be a list")
    for i, c in enumerate(chords):
        _validate_chord(c, f"{source}: chords[{i}]")

    return data


# ---------------------------------------------------------------------------
# File-level driver
# ---------------------------------------------------------------------------

def _is_beat_dir(dirpath: Path) -> bool:
    return dirpath.name.lower() == "beats"


def validate_file(path: Path) -> list[str]:
    """Validate a single preset JSON file; return a list of error strings (empty = OK)."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return [f"{path.name}: invalid JSON: {e}"]

    try:
        if _is_beat_dir(path.parent):
            validate_beat(data, path.name)
        else:
            # assume melodies; a melodies/ dir is the standard location
            validate_melody(data, path.name)
        return []
    except PresetError as e:
        return [f"{path.name}: {e}"]


def validate_dir(dirpath: Path) -> list[str]:
    """Validate every ``*.json`` under a preset directory (recursively).

    ``presets/`` holds ``beats/`` and ``melodies/`` subfolders. Each file is
    classified by a ``beats``/``melodies`` component in its ABSOLUTE path (beats use
    the step-sequencer schema, everything else the melody schema), so classification
    stays correct no matter which ancestor directory the walk starts from. Returns a
    flat list of all error strings (empty == all valid).
    """
    dirpath = dirpath.resolve()
    if not dirpath.is_dir():
        return [f"{dirpath}: not a directory"]
    errors: list[str] = []
    for f in sorted(dirpath.rglob("*.json")):
        parts = {p.lower() for p in f.parts}
        if "vocal" in parts or "genres" in parts or "kits" in parts:   # own schemas (test_vocal / test_genre / test_drumkits)
            continue
        kind = "beats" if "beats" in parts else "melodies"
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"{f.name}: invalid JSON: {e}")
            continue
        validator = validate_beat if kind == "beats" else validate_melody
        try:
            validator(data, f.name)
        except PresetError as e:
            errors.append(f"{f.name}: {e}")
    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Usage: ``python3 presets/validate.py [preset_dir]``.

    With no argument, validates the ``presets/`` directory containing this file
    (both ``beats/`` and ``melodies/`` subfolders). With a path argument, validates
    that directory (or that single file). Exits 0 if everything is valid, 1
    otherwise.
    """
    argv = argv if argv is not None else sys.argv[1:]
    base = Path(argv[0]) if argv else Path(__file__).resolve().parent

    targets = [base.parent] if base.is_file() else [base]

    all_errors: list[str] = []
    checked = 0
    for d in targets:
        errs = validate_dir(d)
        all_errors.extend(errs)
        checked += len(list(d.rglob("*.json")))

    if all_errors:
        print(f"\u274c {len(all_errors)} preset error(s) across {checked} file(s):")
        for e in all_errors:
            print(f"   - {e}")
        return 1
    print(f"\u2705 All {checked} preset(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
