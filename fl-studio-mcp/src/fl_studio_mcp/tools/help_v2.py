"""B9: fl_help(domain) — on-demand full param/action docs.

The 10 domain tools keep their MCP schemas SHORT (the A6 oneOf / P1 point:
86 verbose schemas in context is exactly the failure mode). fl_help is how
the agent gets the FULL detail for one domain on demand — every action, its
params with types/ranges/defaults, the tier (read/write/destructive), the
transport method (controller action vs queue vs native menu), and the known
API gaps.

Read-only: no MIDI trip, no undo, no FL contact. It's a local knowledge base.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

# The 10 domain tools (B1-B8 + help itself + delete/batch from Sprint A).
DOMAINS = (
    "state", "transport", "mixer", "channel", "pattern",
    "notes", "select_script", "plugin", "file", "help", "connect", "delete", "batch",
    "recipe",
)

_DOCS: dict[str, dict[str, Any]] = {
    "state": {
        "tool": "fl_state",
        "summary": "One-trip read-only session snapshot (the guard against acting on stale context).",
        "tier": "read",
        "transport": "controller: state.snapshot (one MIDI trip) + local piano-roll state file",
        "actions": [
            {"action": "(no action — single call)",
             "params": "fresh_seconds (int, default 600; 0=always stale)",
             "returns": "bpm, transport, patterns, selected_pattern, channel_count, "
                        "selected_channel, fl_version, project, and piano_roll with "
                        "mtime + age + STALE flag"},
        ],
        "gaps": [],
    },
    "transport": {
        "tool": "fl_transport",
        "summary": "Playback and tempo.",
        "tier": "write",
        "transport": "controller: transport.*",
        "actions": [
            {"action": "play", "params": "—"},
            {"action": "stop", "params": "—"},
            {"action": "record", "params": "armed (bool, default False)"},
            {"action": "set_bpm", "params": "bpm (float, 20-300) — the REAL tempo"},
            {"action": "set_timesig", "params": "numerator, denominator (int, 1-32)"},
            {"action": "set_speed", "params": "speed (float, 0.25-4.0) — speed multiplier, does NOT change BPM"},
            {"action": "set_swing", "params": "swing (float, 0.0-1.0) — GLOBAL project swing (typical 0.1-0.3)"},
            {"action": "loop", "params": "mode (pattern|song)"},
            {"action": "position", "params": "value (float >=0), unit (seconds|beats|minutes, default seconds)"},
        ],
        "gaps": ["set_speed is a speed multiplier; reset to 1.0 after setting real BPM (CLAUDE.md §2.1)."],
    },
    "mixer": {
        "tool": "fl_mixer",
        "summary": "Mixer-track control.",
        "tier": "write",
        "transport": "controller: mixer.*",
        "actions": [
            {"action": "set_vol", "params": "track (int>=0), volume (float 0-1)"},
            {"action": "set_pan", "params": "track (int>=0), pan (float -1..1)"},
            {"action": "route", "params": "track, to (int>=0) — full-level send; src!=dst"},
            {"action": "sends", "params": "track, to, level (float 0-1); src!=dst"},
            {"action": "add_fx", "params": "track, plugin (str) — native Add > Effect > More plugins picker; slot read-back verified, a wrong row is taken back out"},
            {"action": "get_info", "params": "track", "returns": "name, volume (0-1, dB), pan, mute/solo/arm"},
            {"action": "get_sends", "params": "track", "returns": "[{to, level}] active sends"},
            {"action": "get_peaks", "params": "[track] (omit = all sounding tracks + master 0), [window=0.5 s, 0-5]",
             "returns": "tracks [{track, peak (linear, 1.0 = 0 dBFS), left, right, dbfs, clipping (>1.0)}], "
                        "clipping, playing, via (mixer.getPeaks | probe.exec)"},
            {"action": "fix_clipping", "params": "[track=0], [target_db=-1.0], [window=one loop]",
             "returns": "prefader_peak_dbfs, output_peak_before/after_dbfs, fader_after_db, changed; "
                        "runs automatically after every fl_preset load (auto_level, -1.5 dBFS)"},
            {"action": "get_eq", "params": "track",
             "returns": "band_count, bands [{band, gain, gain_db, freq, freq_hz, bw}] (normalized 0-1 + real units); "
                        "needs controller v10.4h deployed (FL restart), else a clear 'not deployed' error"},
            {"action": "set_eq", "params": "track, band, [gain], [freq], [bw] (0-1 normalized) — before/after read in separate trips"},
            {"action": "eq_preset", "params": "track, preset (cut_mud|high_pass_ish|air|reset) — solved via the dB/Hz getters; convention, not auditioned"},
        ],
        "gaps": [
            "get_eq/set_eq/eq_preset: v10.4h EQ handlers are UNVERIFIED live (signatures reported in `errors`).",
            "get_peaks meters decay within ~0.2 s: it samples every 0.1 s over `window` and keeps the max; "
            "silence (nothing playing) reads 0.",
            "remove_fx is NOT here — it is destructive → fl_delete(target=fx).",
            "Track meters are PRE-fader and setTrackVolume is not readable in the same trip (live 2026-10-02).",
        ],
    },
    "channel": {
        "tool": "fl_channel",
        "summary": "Instrument (channel) control.",
        "tier": "write",
        "transport": "controller: channels.*",
        "actions": [
            {"action": "set_vol", "params": "index, volume (float 0-1)"},
            {"action": "set_pan", "params": "index, pan (float -1..1)"},
            {"action": "rename", "params": "index, name (str)"},
            {"action": "route", "params": "index, to (int) — target mixer track"},
            {"action": "mute", "params": "index, muted (bool, default True)"},
            {"action": "solo", "params": "index, solo (bool, default True)"},
            {"action": "clone", "params": "index, name — no importable clone API in v45 (native-menu)"},
            {"action": "add", "params": "plugin, name — the native Add menu (the ONLY channel-creation path; server-side System Events click, then routes to a free mixer track, renames, selects). plugin = exact Add-menu name: '3x Osc', 'FLEX', 'Sytrus', 'Fruit Kick', 'Sampler'…"},
            {"action": "set_steps", "params": "index, steps (list[bool]), [pattern (1-based)] — the step sequencer (drums)"},
            {"action": "get_steps", "params": "index, [steps (count, default 16)], [pattern] — read a channel's step grid"},
        ],
        "gaps": [
            "add = native Add menu (no importable channels.add() — hard rule).",
            "clone = no importable API in v45 (native-menu).",
            "set_vol (channels.setVolume) was accepted but did not change the dB read-back on the 808 channel during live E2E (2026-10-01) — use fl_exec_python channels.setChannelVolume as a fallback.",
        ],
    },
    "pattern": {
        "tool": "fl_pattern",
        "summary": "Pattern control.",
        "tier": "write",
        "transport": "controller: patterns.*",
        "actions": [
            {"action": "create", "params": "name, [length_beats], [color] — next free slot, no jump (no dialog)"},
            {"action": "select", "params": "pattern (int>=1) — refuses non-existent (jumping to empty opens a blocking dialog)"},
            {"action": "rename", "params": "pattern, name — 2-arg setPatternName (3-arg CRASHES FL, C4)"},
            {"action": "set_len", "params": "pattern, beats (int>=1)"},
            {"action": "clone", "params": "pattern, [name] — into slot+1 (later patterns shift up — re-list)"},
        ],
        "gaps": [
            "clear is NOT here — destructive → fl_delete(target=pattern_data).",
            "C4: setPatternName is 2-arg in live v45; 3-arg crashes FL.",
        ],
    },
    "notes": {
        "tool": "fl_notes",
        "summary": "Piano-roll note control (the queue + ComposeWithLLM trigger path).",
        "tier": "write",
        "transport": "queue file (mcp_request.json) + ComposeWithLLM script trigger (NOT a controller action)",
        "actions": [
            {"action": "write_steps", "params": "notes [{midi, duration, time?, velocity?, slide?}], mode (add|replace), "
                                                "[target_pattern], [channel_index], [auto_trigger=True], [open_roll_verified=False]",
             "note": "REFUSED unless channel_index is given (the server switches the roll to it and proves it) or open_roll_verified=True (you confirmed the open roll — §6b)"},
            {"action": "read_steps", "params": "— (mtime-guarded piano roll via fl_state)"},
            {"action": "import_midi", "params": "channel_index, notes [{midi, duration, time?, velocity 0-1?}] OR path (.mid in the work dir), [target_pattern], [bpm]",
             "note": "C3 (proven 2026-10-01): FL's own piano-roll File > Import MIDI file into an EXISTING channel. REPLACES that channel's notes in the pattern. No ComposeWithLLM queue. UI steps located on screen by Vision OCR and verified (fl-studio-mcp/docs/UI-AUTOMATION.md); the roll is read back and compared -> 'verified'. ~15 s; the previously active pattern is restored. Needs Accessibility + Screen Recording for the server."},
            {"action": "live_play", "params": "notes — NOT WIRED (real-time note-on/off)"},
            {"action": "quantize", "params": "step, [range] — NOT WIRED (the roll's quantize menu)"},
        ],
        "gaps": [
            "cut_all is NOT here — destructive → fl_delete(target=roll_notes).",
            "THE handshake (§6b): never write notes without confirming the open roll.",
            "note_count: 0 after a write = ComposeWithLLM is not the selected script → run fl_select_script(channel_index=<target>) then retry.",
            "live_play / quantize are unverified; import_midi is proven (C3) but slow — use write_steps for small edits.",
        ],
    },
    "recipe": {
        "tool": "fl_recipe",
        "summary": "A beat as numbered, replayable, undoable steps (recipes/<name>.json; schema in recipes/README.md).",
        "tier": "write",
        "transport": "in-process: reuses fl_transport / fl_pattern / fl_channel / fl_notes / fl_plugin / fl_mixer (one FL call at a time); journal in .generated/recipes/<name>/<fl_pid>.journal.json",
        "actions": [
            {"action": "validate", "params": "path, [offline=False]", "note": "schema + `do` values + every role resolves to exactly one channel by NAME (skipped offline / no FL)"},
            {"action": "plan", "params": "path", "note": "per step vs the part ledger (steps, notes) or the journal (others): new | same | changed"},
            {"action": "apply", "params": "path, [step] | [from_step], [to_step], [force=False], [stop_at_gates=False]", "note": "in order, stops at the first failed/unverified step, journals the previous state, skips `same` steps unless force. Reports 'gate Gn reached' at a gate end: run the compare + listen before continuing"},
            {"action": "status", "params": "path", "note": "per step: applied / verified / gate / ledger state"},
            {"action": "undo", "params": "path, step, [force=False]", "note": "restores that step's journal `before`; refuses if a LATER applied step touched the same target (lists them)"},
            {"action": "export", "params": "path, [from_pattern], [to_pattern], [name]", "note": "write a recipe from the part ledger (hand-built beat -> replayable)"},
        ],
        "gaps": [
            "Step kinds (`do`): transport, pattern, steps, notes, fx, eq, mix.",
            "Notes steps go through fl_notes write_steps(channel_index=...) so the S1 roll-title proof (6b) applies; verified by the roll read-back, queue cleared on failure.",
            "Journals are per FL pid: after an FL restart a recipe has no applied steps (plan shows new).",
            "Undo cannot remove a pattern a step created, restore a pattern name, or read playback speed.",
        ],
    },
    "select_script": {
        "tool": "fl_select_script",
        "summary": "Select the active piano-roll script (default: ComposeWithLLM) — automates the §0 manual step, for ANY channel.",
        "tier": "write",
        "transport": "OS-level: cliclick mouse into the web-rendered roll toolbar (wrench) + script list. In-process screen/ui crash the trial build; there is no API/pref to set the script.",
        "actions": [
            {"action": "select", "params": "[script=ComposeWithLLM], [channel_index], [ensure_open=True], [verify=False], [wrench_x], [script_x], [script_y]",
             "note": "Selects a channel (channel_index) and opens its roll, then clicks the wrench and the script. Coordinate-based; pass explicit coords if the layout shifted."},
        ],
        "gaps": [
            "The dropdown is web-rendered: no AX tree, no in-process API (ui/screen crash the trial build). This is the only layer that reaches it.",
            "Coordinates are fractions of the live FL window frame (machine-independent); explicit wrench_x/script_x/script_y are honored verbatim — re-run with them (the tool prints them from a failure screenshot) if FL's internal layout shifts.",
        ],
    },
    "plugin": {
        "tool": "fl_plugin",
        "summary": "Plugin (FX) control — FLEX-family primary target.",
        "tier": "write",
        "transport": "controller: plugins.*",
        "actions": [
            {"action": "list_params", "params": "index, [slot_index] — the plugin's params"},
            {"action": "set_param", "params": "index, param (int>=0 OR a knob NAME, exact case/space-insensitive; Not Used/empty/ambiguous refuse with candidates), value (number), [slot_index] — a write; a name call returns resolved_index + read-back value_string"},
            {"action": "echo", "params": "index, [slot_index], [on], [mix], [feedback], [time] — FLEX knobs 'Delay'/'Delay mix'/'Delay feedback'/'Delay time' (mixer-slot FX by keyword, refuses if ambiguous); 0-1 values; only given fields change; returns before/after value_string"},
            {"action": "reverb", "params": "index, [slot_index], [on], [mix], [decay], [size] — 'Reverb', 'Reverb mix/decay/size'"},
            {"action": "chorus", "params": "index, [slot_index], [amount] — the 'Chorus' knob"},
            {"action": "get_fx", "params": "index, [slot_index]", "returns": "{echo|reverb|chorus: {field: value_string}} for the knobs that exist"},
            {"action": "load_preset", "params": "index, preset, [slot_index] — NOT VERIFIED (no importable preset-load in v45)"},
        ],
        "gaps": [
            "808-type params are often invisible to the param API.",
            "load_preset: only getPresetCount/nextPreset/prevPreset were probed; native-menu method.",
        ],
    },
    "file": {
        "tool": "fl_file",
        "summary": "Project file / export.",
        "tier": "write (open=destructive)",
        "transport": "native File menu (the flp file API is unprobed in v45)",
        "actions": [
            {"action": "save", "params": "[path] — write"},
            {"action": "save_as", "params": "path — write"},
            {"action": "export", "params": "path, format (wav|mp3|stems) — write"},
            {"action": "open", "params": "path — DESTRUCTIVE (replaces the session; strands on a trial) → confirm flow"},
        ],
        "gaps": [
            "No controller file/export handler yet (flp unprobed / File menu is native) — all report not_verified_yet.",
            "open is destructive and goes through the owner-confirm flow.",
        ],
    },
    "connect": {
        "tool": "fl_connect",
        "summary": "Bring FL up / down / reconnect (the process, not a domain).",
        "tier": "write (force=destructive, open can strand on trial)",
        "transport": "OS-level: launch via `open -a`, dismiss native AppKit dialogs (Welcome/Confirm) via AX + cliclick, reconnect via MIDI",
        "actions": [
            {"action": "(none) / reconnect", "params": "—",
             "returns": "ok / error — the original reconnection behavior"},
            {"action": "open", "params": "[wait_ready=True] [timeout=60]",
             "returns": "state (ready|launching|launch_failed|not_ready_in_time|died_during_startup|already_running)"},
            {"action": "close", "params": "[confirm=no]  (no=don't save, yes=save, cancel=stay)",
             "returns": "state (closed_cleanly|closed_after_dialog|still_up)"},
            {"action": "force", "params": "[confirm=yes]",
             "returns": "killed, note"},
        ],
        "gaps": [
            "Native macOS dialogs (Confirm/Welcome/Problem Reporter) are AppKit windows with NO AX tree: FL's in-process ui/screen cannot reach them (verified 2026-09-30). Dismissed via AX (find window by exact process name OsxFL) + cliclick coordinate / Escape.",
            "Trial build: saving a brand-new untitled project is blocked; closing can re-prompt a save dialog (handled by the dismiss path).",
            "Save lives on fl_file(action='save'); session state reads live on fl_state — intentionally not duplicated here.",
        ],
    },
    "edison": {
        "tool": "fl_edison",
        "summary": "Edison: load a clip, stamp one region per onset, send clip+regions to a Sampler channel (S4.2/L16).",
        "tier": "write (UI-driven: OCR-located clicks; FL frontmost, mouse untouched)",
        "transport": "OS-level: macOS menu bar + OCR-anchored clicks on Edison's custom UI; "
                     "payload baked into Settings/Audio scripts/Workbench/0MCP-Workbench.pyscript",
        "actions": [
            {"action": "status", "params": "—", "returns": "edison_open, anchor"},
            {"action": "open", "params": "— (opens on the selected mixer insert; no-op if open)"},
            {"action": "load_regions",
             "params": "[clip] (audio path; else the loaded clip), hits_json (analysis drums.json) "
                       "or regions [{name,start_s,end_s}], [max_ms=300], [clear_regions=True]",
             "returns": "request_id, reply {id, ok, loaded, added, count, len}"},
            {"action": "send_to_channel", "params": "channel (Sampler index), [out] (.wav copy inside the repo)",
             "returns": "wav (FL's Audio/Sliced audio/<name>_N.wav), region_count, first_regions"},
            {"action": "run", "params": "all of the above", "returns": "steps {open, load_regions, send_to_channel}"},
        ],
        "gaps": [
            "Edison's Python has NO file I/O: requests ride inside the script, replies come back as an OCR'd dialog.",
            "The send renames the target channel after the sample (e.g. 'drums') and writes a new <name>_N.wav each time.",
            "Needs Screen Recording + Accessibility permission for the server process; ~30-60 s for run.",
        ],
    },
    "delete": {
        "tool": "fl_delete",
        "summary": "The single destructive tool (A4). Every destructive action in the system routes here.",
        "tier": "destructive",
        "transport": "controller: delete.* (all wrapped by _safe_exec: undo + identity verify)",
        "actions": [
            {"action": "channel", "params": "index, name (identity verify)"},
            {"action": "pattern", "params": "pattern, name"},
            {"action": "pattern_data", "params": "pattern, name — clears the notes/data in a pattern (keep the pattern)"},
            {"action": "fx", "params": "track, slot — remove an insert (this is mixer remove_fx)"},
            {"action": "roll_notes", "params": "notes — delete specific notes via the ComposeWithLLM queue"},
        ],
        "gaps": [
            "Silent only in a verified scratch session (title prefix SCRATCH_ AND path under the scratch folder); "
            "outside scratch the owner confirms the first destructive of the session.",
            "The native confirm dialog stays in the loop (can't be skipped).",
        ],
    },
    "batch": {
        "tool": "fl_batch",
        "summary": "Many actions in one call — domain in ONE MIDI trip, plus optional open/close/force interleaved (A5).",
        "tier": "read/write (domain NEVER destructive; close/force are process-level)",
        "transport": "domain: controller batch.run (one trip, one undo before first write, stop-on-fail); "
                     "lifecycle: server-side (open/close/force), flushed around the trip in item order",
        "actions": [
            {"action": "(a list of {action, params})",
             "params": "items: list, [rollback: bool]. Domain items use domain.verb names; "
                       "lifecycle items use open/close/force (or connect.open/...), run outside the "
                       "trip in item order. Destructive domain items REJECTED; stop-on-fail; "
                       "one undo per domain trip.",
             "note": "So one call can do: open -> [config trip] -> close. "
                     "rollback is best-effort restoreUndoLevel — NOT transactional."},
        ],
        "gaps": [
            "Domain items can NEVER be destructive (no delete-by-stealth).",
            "rollback is non-transactional: partial batch state may remain.",
            "Lifecycle (open/close/force) items are OS-level, not controller actions — they cannot be "
             "combined into a single MIDI trip with domain items, but run in the requested order.",
        ],
    },
    "help": {
        "tool": "fl_help",
        "summary": "On-demand full param/action docs for one domain (keeps the schemas short). No arg → list of ALL domains.",
        "tier": "read",
        "transport": "local (no MIDI trip, no FL contact)",
        "actions": [
            {"action": "(no arg) / (domain)",
             "params": "[domain (state|transport|mixer|channel|pattern|notes|select_script|plugin|file|help|edison|delete|connect|batch)] — omit to get the domain index",
             "returns": "domain index (name + tool + tier + summary per domain), or the full per-action docs for one domain"},
        ],
        "gaps": [],
    },
}


def fl_help(domain: str | None = None) -> dict:
    """Get the full param/action docs for one domain tool.

    The domain tools keep short MCP schemas (P1: 86 verbose schemas in
    context is the failure mode); this is how the agent gets the full
    detail for one domain on demand — every action, params with
    types/ranges, the tier, the transport method, and the known API gaps.

    Read-only: no MIDI trip, no undo, no FL contact.

    Args:
        domain: one of state|transport|mixer|channel|pattern|notes|select_script|
            plugin|file|help|delete|batch|connect. Omit (or pass empty) to
            get the index of ALL domains with a one-line summary each.
    """
    if domain is None or not str(domain).strip():
        # Discovery index: the entry point for an LLM that sees the 14-tool
        # surface and doesn't yet know the action details live here.
        index = [
            {"domain": d, "tool": _DOCS[d]["tool"], "tier": _DOCS[d]["tier"],
             "summary": _DOCS[d]["summary"]}
            for d in DOMAINS if d in _DOCS
        ]
        return {"success": True, "domains": index,
                "hint": "call fl_help(domain=<name>) for the full per-action docs"}
    d = (domain or "").lower().strip()
    if d not in _DOCS:
        return {"success": False,
                "error": f"unknown domain {domain!r}. Valid: {', '.join(DOMAINS)}"}
    return {"success": True, "domain": d, **_DOCS[d]}


def register_help_tools_v2(mcp: FastMCP) -> None:
    """Register the B9 fl_help tool."""
    from fl_studio_mcp.tools.help_v2 import fl_help as _impl

    @mcp.tool()
    def fl_help(domain: str | None = None) -> dict:
        """Get the full param/action docs for one FL domain tool.

        Domains: state | transport | mixer | channel | pattern | notes |
        select_script | plugin | file | help | delete | connect | batch.

        Omit domain to get the index of ALL domains (one-line summary each).
        Read-only (no MIDI trip, no FL contact). Use this when you need
        the full detail for a domain — the tool schemas stay short.
        """
        return _impl(domain)
