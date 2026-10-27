"""S4.1: fl_slice_audio — server-side audio slicing (no MIDI trip).

Reads an audio file, detects onsets (or builds a uniform 16/32 grid at a
BPM), splits the clip into declicked slice wavs under
``fl-studio-mcp/.generated/slices/<song>/`` (git-ignored; rule 9/10 —
audio never committed) and writes a manifest.json that S4.3
(``fl_load_slices``) and the Edison region generator (S4.2) consume.

The input path is any readable audio file (the user points it there
explicitly — unlike preset loading, no work-dir restriction), but the
extension must be a known audio type as a guard against misuse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.audio.slicer import AUDIO_EXTS, slice_audio

_GENERATED = Path(__file__).resolve().parent.parent.parent.parent / ".generated"


def fl_slice_audio(path: str, grid: str = "onset", bpm: float = 0.0,
                   sr: int = 44100) -> dict[str, Any]:
    """Slice an audio file into per-onset (or per-grid-step) sample slices.

    Writes declicked mono slice wavs + a manifest (per-slice start/len in
    seconds and samples, energy→velocity, grid cell, clip key guess) to
    fl-studio-mcp/.generated/slices/<song>/ (not committed).

    Args:
        path: audio file to slice (wav/mp3/m4a/flac/ogg/aiff).
        grid: "onset" (detected onsets) | "16" (16th notes) | "32" (32nds).
            16/32 require bpm.
        bpm: tempo for the 16/32 grids (and recorded in the manifest).
        sr: slice sample rate (default 44100).
    """
    p = Path(path).expanduser()
    if p.suffix.lower() not in AUDIO_EXTS:
        return {"ok": False,
                "error": f"not a known audio file ({p.suffix}); expected one "
                         f"of {sorted(AUDIO_EXTS)}"}
    if not p.is_file():
        return {"ok": False, "error": f"no such file: {path}"}
    song = p.stem
    try:
        manifest = slice_audio(p, _GENERATED / "slices", song,
                               grid=grid, bpm=bpm, sr=sr)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # ffmpeg failure, corrupt file, ...
        return {"ok": False, "error": f"slicing failed: {e}"}
    return {
        "ok": True,
        "song": song,
        "out_dir": str(Path(manifest["manifest_path"]).parent),
        "manifest": manifest["manifest_path"],
        "grid": manifest["grid"],
        "bpm": manifest["bpm"],
        "duration_s": manifest["duration_s"],
        "n_slices": manifest["n_slices"],
        "key_guess": manifest["key_guess"],
        "slices": manifest["slices"],
        "hint": ("next: fl_load_slices (S4.3) or the Edison region "
                 "generator (scripts/edison_regions.py --mode onsets)"),
    }


def register_slice_tools(mcp: FastMCP) -> None:
    """Register fl_slice_audio (pure local; no MIDI trip)."""
    from fl_studio_mcp.tools.slice_v2 import fl_slice_audio as _impl

    @mcp.tool()
    def fl_slice_audio(path: str, grid: str = "onset", bpm: float = 0.0,
                       sr: int = 44100) -> dict:
        """Slice an audio file into per-onset or per-grid-step sample
        slices + manifest (server-side, no FL contact)."""
        return _impl(path, grid, bpm, sr)
