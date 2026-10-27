"""S3.2: preset path resolution — explicit paths restricted to the work dir.

Hermetic: uses a tmp work root + the real repo layout for the negative
cases (paths outside fl-studio-mcp must be rejected, so the MCP surface
cannot read arbitrary files).
"""

from __future__ import annotations

import json

from fl_studio_mcp.preset_paths import load_preset_file, resolve_preset_path, work_root


def test_work_root_is_fl_studio_mcp():
    r = work_root()
    assert r.name == "fl-studio-mcp"
    assert (r / "presets").is_dir()


def test_resolve_inside_work_dir(tmp_path):
    (tmp_path / "presets").mkdir()
    p = tmp_path / "presets" / "x.json"
    p.write_text("{}")
    resolved, err = resolve_preset_path(str(p), tmp_path)
    assert err is None and resolved == p
    # relative paths resolve against cwd, not the string — a relative path
    # outside the root is rejected
    (tmp_path / "escape.json").write_text("{}")
    resolved, err = resolve_preset_path(str(tmp_path / "escape.json"), tmp_path)
    assert err is None  # it IS inside the root
    # but a sibling dir of the root is not
    sib = tmp_path.parent / f"{tmp_path.name}-sib"
    sib.mkdir(exist_ok=True)
    sp = sib / "x.json"
    sp.write_text("{}")
    resolved, err = resolve_preset_path(str(sp), tmp_path)
    assert resolved is None and "outside the work dir" in err


def test_resolve_missing_file(tmp_path):
    resolved, err = resolve_preset_path(str(tmp_path / "nope.json"), tmp_path)
    assert resolved is None and "no such preset file" in err


def test_resolve_traversal_rejected(tmp_path):
    (tmp_path / "presets").mkdir()
    # "presets/../../escape.json" resolves to tmp_path.parent/escape.json
    # — outside the root — and must be rejected after resolve()
    esc = tmp_path.parent / f"{tmp_path.name}-escape.json"
    esc.write_text("{}")
    p = tmp_path / "presets" / ".." / ".." / f"{tmp_path.name}-escape.json"
    resolved, err = resolve_preset_path(str(p), tmp_path)
    assert resolved is None and "outside the work dir" in err


def test_load_preset_file_roundtrip(tmp_path):
    (tmp_path / "gen").mkdir()
    p = tmp_path / "gen" / "trap-var.json"
    p.write_text(json.dumps({"id": "trap-var", "channels": {}}))
    data, err = load_preset_file(str(p), tmp_path)
    assert err is None and data["id"] == "trap-var"


def test_load_preset_file_bad_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json {")
    data, err = load_preset_file(str(p), tmp_path)
    assert data == {} and err


def test_real_work_root_rejects_repo_root_files():
    """Against the REAL work root: a repo-root file (e.g. CLAUDE.md) is
    outside fl-studio-mcp and must be rejected."""
    repo = work_root().parent
    target = repo / "CLAUDE.md"
    resolved, err = resolve_preset_path(str(target))
    assert resolved is None and "outside the work dir" in err
    # but a real preset file is accepted
    preset = work_root() / "presets" / "beats" / "trap.json"
    data, err = load_preset_file(str(preset))
    assert err is None and data.get("id") == "trap"
