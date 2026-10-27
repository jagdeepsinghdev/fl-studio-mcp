"""S3.2: preset path resolution for fl_preset (the legacy fl_load_beat /
fl_load_melody were retired 2026-10-01).

A preset reference is either a registry id (``presets/<kind>/<id>.json``
or ``.generated/<kind>/<id>.json``) or an explicit file path. Explicit
paths are **restricted to the fl-studio-mcp work dir** so the MCP tool
surface cannot be used to read arbitrary files on the machine.

Pure function — unit-testable without FL.
"""

from __future__ import annotations

import json
from pathlib import Path


def work_root() -> Path:
    """The fl-studio-mcp project dir (contains presets/ and .generated/)."""
    return Path(__file__).resolve().parents[2]


def resolve_preset_path(path: str, root: Path | None = None) -> tuple[Path | None, str | None]:
    """Validate an explicit preset path. Returns (path, None) on success
    or (None, error) — the error string is user-facing."""
    root = root or work_root()
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None, f"no such preset file: {path}"
    if p.parent != root and root not in p.parents:
        return None, (f"path {path} is outside the work dir "
                      f"{root} (presets live under presets/ or .generated/)")
    return p, None


def load_preset_file(path: str, root: Path | None = None) -> tuple[dict, str | None]:
    """Resolve + parse. Returns ({}, None) when the path is invalid."""
    p, err = resolve_preset_path(path, root)
    if p is None:
        return {}, err
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return {}, f"cannot read {path}: {e}"
    if not isinstance(data, dict):
        return {}, f"{path} is not a JSON object"
    return data, None


# ---------------------------------------------------------------------------
# 2026-10-02: registry helpers moved here (used by the always-on fl_preset
# tool; the legacy fl_load_beat/fl_load_melody closures that shared them
# were retired 2026-10-01).
# ---------------------------------------------------------------------------

def list_presets(kind: str) -> list[str]:
    """Preset ids: registry (presets/<kind>/) + generated (.generated/<kind>/)."""
    root = work_root()
    ids: set[str] = set()
    for dd in (root / "presets" / kind, root / ".generated" / kind):
        if dd.is_dir():
            ids.update(p.stem for p in dd.glob("*.json"))
    return sorted(ids)


def load_preset(kind: str, preset_id: str) -> dict:
    """Load a preset by id (generated dir wins over the registry)."""
    root = work_root()
    p = (root / ".generated" / kind / f"{preset_id}.json")
    if not p.is_file():
        p = root / "presets" / kind / f"{preset_id}.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def resolve_preset(kind: str, preset_id: str,
                   path: str) -> tuple[dict, str | None]:
    """A preset reference is a registry id or an explicit work-dir path."""
    if path:
        data, err = load_preset_file(path)
        return (data, err) if data else ({}, err or f"no such preset file: {path}")
    data = load_preset(kind, preset_id)
    return (data, None) if data else ({}, None)
