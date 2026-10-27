"""Preset schema tests.

Two layers of validation, both of which run in CI:

1. **Every committed preset** in ``presets/beats/`` and ``presets/melodies/``
   must pass the schema in ``presets/validate.py``. This is the guardrail that
   catches a bad 16-step pattern, an out-of-range MIDI number, a missing field,
   or a bad length_beats before it reaches FL and "plays then goes empty."

2. **The validator itself** must actually reject known-bad shapes — proven with
   synthetic fixtures here, so a future edit that loosens the checks can't
   silently disable them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``presets/validate.py`` importable regardless of the CWD (the package is
# laid out with a top-level ``src/`` and this file sits under ``tests/``).
PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"
sys.path.insert(0, str(PRESETS_DIR))

from validate import (  # noqa: E402
    PresetError,
    validate_beat,
    validate_dir,
    validate_melody,
)

# ---------------------------------------------------------------------------
# Layer 1: every committed preset is valid
# ---------------------------------------------------------------------------

def _all_preset_files(kind: str) -> list[Path]:
    d = PRESETS_DIR / kind
    return sorted(d.glob("*.json"))


def test_beats_dir_has_presets():
    assert _all_preset_files("beats"), f"no beat presets in {PRESETS_DIR / 'beats'}"


def test_melodies_dir_has_presets():
    assert _all_preset_files("melodies"), f"no melody presets in {PRESETS_DIR / 'melodies'}"


def test_all_presets_valid():
    """Every beat and melody preset under presets/ passes its schema.

    validate_dir walks both subfolders and picks the right validator per file
    (beats -> step-sequencer schema, melodies -> note/chord schema) based on each
    file's nearest ancestor directory.
    """
    errs = validate_dir(PRESETS_DIR)
    assert errs == [], "invalid preset(s) under presets/:\n" + "\n".join(errs)


# ---------------------------------------------------------------------------
# Layer 2: the validator rejects known-bad shapes
# ---------------------------------------------------------------------------

def _beat_fixture() -> dict:
    return {
        "id": "test",
        "name": "Test beat",
        "bpm": 120,
        "channels": {
            "kick": {"name": "808 Kick", "pattern": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]},
        },
    }


def _melody_fixture() -> dict:
    return {
        "id": "test",
        "name": "Test tune",
        "key": "C",
        "length_beats": 4,
        "melody": [
            {"note": 60, "step": 0, "dur": 2, "vel": 80},
            {"note": 64, "step": 4, "dur": 2},
        ],
        "chords": [
            {"notes": [48, 52, 55, 60], "step": 0, "dur": 4},
        ],
    }


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("bpm"),
    lambda d: d.update(bpm=0),
    lambda d: d.update(swing=2.5),
    lambda d: d["channels"]["kick"].update(pattern=[1] * 8),            # not 16 steps
    lambda d: d["channels"]["kick"].update(pattern=[1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 2]),  # not 0/1
    lambda d: d.update(channels={}),                                     # empty channels
], ids=["no-bpm", "bpm-zero", "swing>1", "pattern-not-16", "pattern-not-01", "empty-channels"])
def test_beat_rejects_bad_shapes(mutate):
    d = _beat_fixture()
    mutate(d)
    with pytest.raises(PresetError):
        validate_beat(d)


def test_beat_accepts_valid_with_dhol_and_length():
    d = _beat_fixture()
    d["length_beats"] = 4
    d["channels"]["dhol"] = {"name": "Dhol", "pattern": [1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0]}
    assert validate_beat(d) == d


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.pop("melody"), "ok"),          # drops melody, keeps chords -> still valid
    (lambda d: d.update(melody=[]), "ok"),      # empty melody, keeps chords -> still valid
    (lambda d: d["melody"][0].update(note=128), "raise"),   # out of MIDI range
    (lambda d: d["melody"][0].update(step=-1), "raise"),
    (lambda d: d["melody"][0].update(dur=0), "raise"),
    (lambda d: d["melody"][0].update(vel=200), "raise"),
    (lambda d: d["chords"][0].update(notes=[60, 200]), "raise"),
    (lambda d: d.update(length_beats=0), "raise"),
], ids=["no-melody", "empty-melody", "note>127", "step<0", "dur=0", "vel>127", "chord-note>127", "length=0"])
def test_melody_rejects_bad_shapes(mutate, expect):
    d = _melody_fixture()
    mutate(d)
    if expect == "ok":
        validate_melody(d)  # must NOT raise: chords alone satisfy the requirement
    else:
        with pytest.raises(PresetError):
            validate_melody(d)


def test_melody_accepts_chords_only():
    d = _melody_fixture()
    del d["melody"]
    assert validate_melody(d) == d


def test_validator_catches_real_fixture_on_disk(tmp_path):
    """End-to-end: a deliberately broken JSON on disk is reported by validate_dir."""
    import json as _json
    broken = _beat_fixture()
    broken["channels"]["kick"]["pattern"] = [1] * 4  # wrong length
    beat_dir = tmp_path / "beats"
    beat_dir.mkdir()
    (beat_dir / "bad-beat.json").write_text(_json.dumps(broken))
    (tmp_path / "melodies").mkdir()
    (tmp_path / "melodies" / "good-melody.json").write_text(_json.dumps(_melody_fixture()))
    errs = validate_dir(tmp_path)
    assert any("bad-beat.json" in e and "16 steps per bar" in e for e in errs), errs
    # the valid melody in the same tree must not produce an error
    assert not any("good-melody.json" in e for e in errs), errs


def test_multi_bar_beats_accepted_and_bad_lengths_refused():
    d = _beat_fixture()
    d["channels"]["kick"]["pattern"] = [1, 0, 0, 0] * 16          # 4 bars
    validate_beat(d)
    d["channels"]["kick"]["velocities"] = [100] * 16               # arrays must match
    with pytest.raises(PresetError):
        validate_beat(d)
    d["channels"]["kick"].pop("velocities")
    d["channels"]["kick"]["pattern"] = [1] * 80                    # 5 bars: too long
    with pytest.raises(PresetError):
        validate_beat(d)
