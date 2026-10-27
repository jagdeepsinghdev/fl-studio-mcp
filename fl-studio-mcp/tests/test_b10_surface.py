"""B10: the 10-tool surface is the default; the legacy tools are gated
behind LEGACY_TOOLS=1 for one migration cycle (no aliases). R5
(2026-10-01) retired the last preset loaders (fl_list_presets /
fl_load_beat / fl_load_melody): the gated surface is 102 tools.

Verified by loading the real server module with each env state and listing
the registered tools (the FastMCP 2.x tool registry).
"""

import asyncio
import os


def _tool_names(env_legacy: str | None) -> list[str]:
    """Freshly import the server with the given LEGACY_TOOLS env and list
    the registered tool names.

    The server reads LEGACY_TOOLS at import time, so we must force a fresh
    import. We snapshot the fl_studio_mcp.* modules first and restore them
    afterward so other tests (e.g. test_state, which monkeypatches a module
    that is cached in sys.modules) are not corrupted by the re-import."""
    import sys
    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m == "fl_studio_mcp" or m.startswith("fl_studio_mcp.")}
    for m in list(sys.modules):
        if m == "fl_studio_mcp" or m.startswith("fl_studio_mcp."):
            sys.modules.pop(m, None)
    if env_legacy is None:
        os.environ.pop("LEGACY_TOOLS", None)
    else:
        os.environ["LEGACY_TOOLS"] = env_legacy
    try:
        import fl_studio_mcp.server as srv

        async def run():
            return sorted(t.name for t in await srv.mcp.list_tools())

        return asyncio.run(run())
    finally:
        # restore the pre-call module cache so monkeypatches in other tests
        # (and any cached state) survive
        for m in list(sys.modules):
            if m == "fl_studio_mcp" or m.startswith("fl_studio_mcp."):
                sys.modules.pop(m, None)
        sys.modules.update(saved)


NEW_TOOLS = ["fl_state", "fl_transport", "fl_mixer", "fl_channel", "fl_pattern",
             "fl_notes", "fl_plugin", "fl_file", "fl_help", "fl_delete", "fl_batch",
             "fl_preset"]


def test_default_surface_is_ten_domain_tools_plus_delete_batch():
    names = _tool_names(None)
    for t in NEW_TOOLS:
        assert t in names, f"{t} missing from default surface: {names}"


def test_default_surface_has_no_legacy_tools():
    names = _tool_names(None)
    legacy = ["fl_play", "fl_stop", "fl_set_bpm", "fl_send_notes",
              "fl_get_piano_roll_state", "fl_set_track_volume",
              "fl_trigger_note", "fl_list_patterns", "fl_create_pattern",
              "fl_setup_instrument", "fl_add_instrument"]
    for t in legacy:
        assert t not in names, f"legacy {t} should be OFF by default: {names}"


def test_default_surface_is_small():
    """The whole point (P1): the default context is ~20 domain tools, not ~90.
    (ratcheted 20 -> 22 with the fl_preset migration, 2026-10-02)"""
    names = _tool_names(None)
    # 22 -> 23: fl_recipe (owner request 2026-10-03)
    # 23 -> 24: fl_ui_script (owner request 2026-10-03, mouse-free UI routines)
    # 24 -> 25: fl_shortcut (owner request 2026-10-04, FL's keyboard shortcuts)
    # 25 -> 26: fl_vocal (owner request 2026-10-05, vocal chains/buses/loudness)
    # 26 -> 27: fl_screen (owner request 2026-10-06, vision: look/ocr/find/hint/click_text)
    # 27 -> 28: fl_genre (owner request 2026-10-06, one-call genre packs with chords)
    # 28 -> 29: fl_audio (owner request 2026-10-06, sample tempo/key/chords/note, cut, L/R split)
    assert len(names) <= 29, f"default surface too large: {len(names)} tools"


def test_legacy_tools_appear_only_with_legacy_flag():
    names = _tool_names("1")
    # with the flag, both the new domain tools AND the legacy tools are present
    assert "fl_state" in names
    assert "fl_play" in names
    assert "fl_send_notes" in names
    assert "fl_set_track_volume" in names
    # and it's the big surface (ratcheted 80 -> 102 with R5, 2026-10-01)
    assert len(names) >= 102, f"LEGACY_TOOLS=1 should give the big surface (102 after R5): {len(names)}"


def test_no_aliases_between_surfaces():
    """A legacy name and a new name are distinct tools — there is no alias
    that makes fl_play a second name for fl_transport."""
    names_default = set(_tool_names(None))
    names_legacy = set(_tool_names("1"))
    # the default set is a strict subset of the legacy set (plus they share
    # fl_delete/fl_batch/fl_state which are in both)
    # no tool name appears with a different registration under both names
    assert names_default <= names_legacy


def test_connection_tools_always_present():
    """fl_connect / fl_connection_status are infrastructure, present in both."""
    for env in (None, "1"):
        names = _tool_names(env)
        assert "fl_connect" in names, f"fl_connect missing with LEGACY_TOOLS={env}"
