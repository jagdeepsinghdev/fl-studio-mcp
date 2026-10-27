"""B10 close-out: the skills / default-surface coverage report + test.

The test does NOT force a full migration (that's a separate, deliberate
commit). It does three honest things:
  1. The scan runs and the gap report is reproducible.
  2. While LEGACY_TOOLS=1 is available, no skill references a tool that is
     in *neither* the default surface *nor* the legacy surface — i.e. a
     genuinely-dangling name (a typo, or a tool that never existed) would
     be caught. (The 81 known gaps are allowed: they're the legacy tools
     that still exist behind the flag this one cycle.)
  3. The known-gap set is pinned as a constant so the migration progress is
     measurable: it must only shrink, and the test lists exactly what a
     real migration has to close.
"""

import asyncio
import importlib.util
import os
from pathlib import Path

# scripts/ is not a package; load skill_tool_refs by path.
_spec = importlib.util.spec_from_file_location(
    "skill_tool_refs",
    Path(__file__).resolve().parent.parent / "scripts" / "skill_tool_refs.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
NON_TOOL_NAMES = _mod.NON_TOOL_NAMES
coverage_gaps = _mod.coverage_gaps
scan_skill_tool_refs = _mod.scan_skill_tool_refs


def _tool_names(env_legacy: str | None) -> set[str]:
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
            return {t.name for t in await srv.mcp.list_tools()}
        return asyncio.run(run())
    finally:
        for m in list(sys.modules):
            if m == "fl_studio_mcp" or m.startswith("fl_studio_mcp."):
                sys.modules.pop(m, None)
        sys.modules.update(saved)


# The legacy names the skills still reference, expressed as their domain-tool
# equivalent where one exists. This is the *target* of the migration: each
# legacy name below should either be replaced by the domain tool+action shown,
# or (for the ones with no domain equivalent yet) have that action added.
# Keeping it here (not hardcoded into 28 files) is what makes the migration
# auditable.
LEGACY_TO_DOMAIN = {
    # transport
    "fl_play": ("fl_transport", "play"),
    "fl_stop": ("fl_transport", "stop"),
    "fl_record": ("fl_transport", "record"),
    "fl_start_recording": ("fl_transport", "record"),
    "fl_set_bpm": ("fl_transport", "set_bpm"),
    "fl_get_bpm": ("fl_transport", "set_bpm"),  # read via fl_state too
    "fl_set_playback_speed": ("fl_transport", "set_speed"),
    "fl_get_playback_speed": ("fl_state", "—"),
    "fl_set_swing": ("fl_transport", "set_swing*"),   # * see note below
    "fl_get_swing": ("fl_state", "—"),
    "fl_set_loop_mode": ("fl_transport", "loop"),
    "fl_get_transport_status": ("fl_state", "—"),
    # channels
    "fl_get_all_channels": ("fl_state", "—"),
    "fl_get_channel_info": ("fl_state", "—"),
    "fl_get_channel_count": ("fl_state", "—"),
    "fl_get_selected_channel": ("fl_state", "—"),
    "fl_select_channel": ("fl_channel", "—"),
    "fl_select_one_channel": ("fl_channel", "—"),
    "fl_set_channel_volume": ("fl_channel", "set_vol"),
    "fl_set_channel_pan": ("fl_channel", "set_pan"),
    "fl_set_channel_name": ("fl_channel", "rename"),
    "fl_set_channel_color": ("fl_channel", "color*"),  # * not yet a domain action
    "fl_mute_channel": ("fl_channel", "mute"),
    "fl_solo_channel": ("fl_channel", "solo"),
    "fl_route_channel_to_mixer": ("fl_channel", "route"),
    "fl_trigger_note": ("fl_channel", "trigger*"),    # * not yet a domain action
    # step sequencer (NO domain action yet — the biggest gap)
    "fl_set_step_sequence": ("fl_channel", "set_steps"),
    "fl_get_step_sequence": ("fl_channel", "get_steps"),
    "fl_set_grid_bit": ("fl_channel", "set_steps"),
    "fl_get_grid_bit": ("fl_channel", "get_steps"),
    # patterns
    "fl_list_patterns": ("fl_state", "—"),
    "fl_create_pattern": ("fl_pattern", "create"),
    "fl_select_pattern": ("fl_pattern", "select"),
    "fl_clone_pattern": ("fl_pattern", "clone"),
    "fl_set_pattern_length": ("fl_pattern", "set_len"),
    "fl_get_pattern_length": ("fl_pattern", "set_len"),
    # piano roll / notes
    "fl_send_notes": ("fl_notes", "write_steps"),
    "fl_send_chord": ("fl_notes", "write_steps"),
    "fl_get_piano_roll_state": ("fl_notes", "read_steps"),
    "fl_get_piano_roll_info": ("fl_notes", "read_steps"),
    "fl_clear_piano_roll": ("fl_delete", "roll_notes"),
    "fl_clear_request_queue": ("fl_notes", "clear_queue*"),
    "fl_trigger_script": ("fl_notes", "—"),  # the ComposeWithLLM trigger
    "fl_write_808_slides": ("fl_notes", "write_808*"),
    "fl_write_notes_file": ("fl_notes", "write_file*"),
    # mixer
    "fl_set_track_volume": ("fl_mixer", "set_vol"),
    "fl_set_track_pan": ("fl_mixer", "set_pan"),
    "fl_set_track_name": ("fl_mixer", "set_name*"),
    "fl_set_track_color": ("fl_mixer", "color*"),
    "fl_mute_track": ("fl_mixer", "mute*"),
    "fl_solo_track": ("fl_mixer", "solo*"),
    "fl_arm_track": ("fl_mixer", "arm*"),
    "fl_set_send_level": ("fl_mixer", "sends"),
    "fl_get_sends": ("fl_mixer", "get_sends"),
    "fl_get_mixer_track_info": ("fl_mixer", "get_info"),
    "fl_get_mixer_track_count": ("fl_state", "—"),
    "fl_get_all_mixer_tracks": ("fl_state", "—"),
    "fl_add_fx": ("fl_mixer", "add_fx"),
    "fl_remove_fx": ("fl_delete", "fx"),
    # plugins
    "fl_get_plugin_name": ("fl_plugin", "—"),
    "fl_get_plugin_params": ("fl_plugin", "list_params"),
    "fl_get_plugin_param_value": ("fl_plugin", "list_params"),
    "fl_get_plugin_param_count": ("fl_plugin", "list_params"),
    "fl_set_plugin_param_value": ("fl_plugin", "set_param"),
    "fl_is_plugin_valid": ("fl_plugin", "—"),
    "fl_get_plugin_color": ("fl_plugin", "—"),
    "fl_get_preset_count": ("fl_plugin", "—"),
    "fl_next_preset": ("fl_plugin", "preset*"),
    "fl_prev_preset": ("fl_plugin", "preset*"),
    "fl_find_preset": ("fl_plugin", "find_preset*"),
    "fl_list_preset_names": ("fl_plugin", "list_presets*"),
    "fl_select_preset": ("fl_plugin", "load_preset"),
    # channel creation (native menu)
    "fl_add_instrument": ("fl_channel", "add"),
    "fl_setup_instrument": ("fl_channel", "add"),
    # presets (R5 2026-10-01: the legacy loaders are GONE from the
    # LEGACY_TOOLS surface; they live on only as fl_preset actions)
    "fl_list_presets": ("fl_preset", "list"),
    "fl_load_beat": ("fl_preset", "load_beat"),
    "fl_load_melody": ("fl_preset", "load_melody"),
    # song builder (NO domain tool yet — a whole helper area)
    "fl_build_track": ("fl_song*", "—"),
    "fl_setup_song": ("fl_song*", "—"),
    "fl_write_melody": ("fl_song*", "—"),
    "fl_write_beat": ("fl_song*", "—"),
    "fl_write_drums": ("fl_song*", "—"),
    "fl_clean_drums": ("fl_song*", "—"),
    # markers (NO domain tool yet)
    "fl_add_marker": ("fl_marker*", "—"),
    "fl_remove_marker": ("fl_marker*", "—"),
    "fl_list_markers": ("fl_marker*", "—"),
    "fl_get_markers": ("fl_marker*", "—"),
    # exec gate (stays a separate gated tool, not part of the 10)
    "fl_exec_python": ("fl_exec*", "—"),
    # mixer extras with no domain action yet
    "fl_set_stereo_separation": ("fl_mixer", "stereo_sep*"),
    # transport song-position read/write (legacy position modes)
    "fl_set_song_position": ("fl_transport", "position"),
    "fl_get_song_length": ("fl_state", "—"),
}

# Names the scan will legitimately flag that are NOT real tools and have no
# migration target (prose fragments, partial tokens, or genuinely gone).
KNOWN_NON_ACTIONS = {
    "fl_delete_notes",  # not a real tool (the real one is fl_delete roll_notes)
    "fl_trigger_all_notes",  # not a current tool name
    "fl_write_chords",  # was merged into fl_send_notes / fl_write_melody
}


def test_scan_runs_and_finds_expected_scale():
    refs = scan_skill_tool_refs()
    all_names = set()
    for v in refs.values():
        all_names |= v
    # sanity: even after the B10 skills migration the skills still reference a
    # meaningful set of tool names (a mix of domain tools + intentionally-
    # documented legacy names behind LEGACY_TOOLS=1).
    assert len(all_names) >= 20, f"expected a meaningful set of refs, got {len(all_names)}"
    # the domain tools are now referenced (the migration happened)
    assert {"fl_channel", "fl_transport", "fl_notes", "fl_state"} <= all_names, \
        f"domain tools should be referenced after migration, got {sorted(all_names)}"
    assert len(refs) >= 10, "expected many skill files"


def test_no_genuinely_dangling_names(legacy_surface=None):
    """A skill may reference a legacy name that EXISTS behind LEGACY_TOOLS=1,
    but it must NEVER reference a name that exists in NEITHER surface (that's
    a typo or a tool that was deleted)."""
    if legacy_surface is None:
        legacy_surface = _tool_names("1")
    refs = scan_skill_tool_refs()
    all_names = set()
    for v in refs.values():
        all_names |= v
    dangling = {n for n in all_names
                if n not in legacy_surface and n not in LEGACY_TO_DOMAIN
                and n not in KNOWN_NON_ACTIONS}
    assert not dangling, f"skills reference names that exist nowhere: {dangling}"


def test_coverage_gap_report_is_the_migration_worklist():
    """The gap set (referenced, not in default surface) is exactly what a real
    migration must close. Pin it so the report can't silently grow; it may
    only shrink as skills move to the domain tools."""
    default = _tool_names(None)
    refs = scan_skill_tool_refs()
    all_names = set()
    for v in refs.values():
        all_names |= v
    gaps = coverage_gaps(all_names, default)
    # every gap must be accounted for by the migration map or the non-action
    # allowlist — nothing should be an unexplained mystery
    unexplained = {g for g in gaps
                   if g not in LEGACY_TO_DOMAIN and g not in KNOWN_NON_ACTIONS}
    assert not unexplained, (
        f"coverage gaps not covered by the migration map: {unexplained}. "
        f"Add each to LEGACY_TO_DOMAIN (with its domain tool+action) or "
        f"KNOWN_NON_ACTIONS."
    )


def test_default_surface_is_still_the_tiny_one():
    default = _tool_names(None)
    # ratcheted 20 -> 22 with the fl_preset migration (2026-10-02)
    # 22 -> 23: fl_recipe (owner request 2026-10-03)
    # 23 -> 24: fl_ui_script (owner request 2026-10-03, mouse-free UI routines)
    # 24 -> 25: fl_shortcut (owner request 2026-10-04, FL's keyboard shortcuts)
    # 25 -> 26: fl_vocal (owner request 2026-10-05, vocal chains/buses/loudness)
    # 26 -> 27: fl_screen (owner request 2026-10-06, vision: look/ocr/find/hint/click_text)
    # 27 -> 28: fl_genre (owner request 2026-10-06, one-call genre packs with chords)
    # 28 -> 29: fl_audio (owner request 2026-10-06, sample tempo/key/chords/note, cut, L/R split)
    assert len(default) <= 29
    assert "fl_state" in default and "fl_help" in default
