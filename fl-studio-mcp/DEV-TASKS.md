# DEV-TASKS.md — FL Studio control: tasks & sprints

Owner- and senior-approved (2026-09-30, after a senior design review).
**A task is done when its `verify`
passes AND it is committed with tests.**

**Architecture:** ~10 domain tools, each with an `action` enum + discriminated
params; one server-side dispatcher owns lock, protocol, validation, safety
tiers, auto-undo, identity verify, confirm flow, method routing, same-trip
read-back, audit. `fl_delete` is separate (permission-gateable).

**Sprints A, B and most of C/L are DONE** — the full done-list with verify
commands is in the **Appendix: done** below (detail lives in the git log).
Everything still open:

---

## Open — Sprint C (file I/O, IAC, key experiments)

- [ ] **C1** `fl_file.open`/save-as/export round-trip on a **scratch project**
  (v45 has no importable file API — matrix-pinned; `fl_connect save` (OS-level)
  is the proven save path; export needs the native ⌘R dialog = S9).
- [ ] **C2** IAC Bus 2: create, bind as FL MIDI input, 2-note-in test,
  **automation-record test**. Re-scoped 2026-10-02: a **self-created virtual
  port** (`MidiIn().open_virtual_port("FL Notes Out")` — rtmidi 1.5.8: MidiIn
  creates a DESTINATION) is now **persistent** (created in the `fl_connect`
  open flow) and appears in FL's MIDI inputs — only the one-time selection
  click in the native MIDI-settings form remains (candidate: `ui.navigateBrowser`
  tier).
- [ ] **C5** Karabiner **virtualHID** test (appears as a real keyboard to
  macOS). If FL's custom-drawn text fields accept it: all "manual-only" text
  fields become automatable. Hotkeys already land via System Events (F-keys,
  named keys, cmd/opt; bare letters/digits never) — `fl_shortcut` covers those.
- [ ] **C6** restore the 808-rack project from the latest autosave
  (`Project_2/Backup/...13h15...flp`); owner decides on the missing snare.

## Open — Sprint D (feedback loop + long tail)

- [ ] **D1** render→analyze loop: 1-bar export → `fl_audio analyze` features
  → agent context (= S9 below is its export half).
- [ ] **D2** `fl_add_effect` (Add menu + plugin picker, per-channel/per-track)
  (= L16).
- [ ] **D3** deferred (only if needed): FLP read-only parser (pyflp fork;
  `monadgroup/FLParser` reference) · bridge plugin (`ilmcp` is in-process-only
  — Gopher's `add_channel`; the native Add menu stays the creation path) ·
  VST3 MIDI-out · external DAW.

## Open — Sprint S (song assembly without repeated hand steps, 2026-10-03)

- [~] **S1 Roll title check on floating rolls** (blocks S5 live + S2). Code +
  fixture tests done 2026-10-03 (`roll_title_from_boxes`,
  `tests/test_roll_title.py`); **live check pending** — OCR read `''` ×6 on
  2026-10-03 although the roll was correct. Find the title row by OCR
  anywhere in the window frame (not the docked crop); accept a truncated
  title (`808 Astro…`) only when the prefix matches exactly one channel.
- [ ] **S2 `fl_select_script` finds the wrench on a floating roll** — anchor
  on the roll title's OCR box (wrench = first toolbar icon left of it;
  2026-10-03 at x≈768, y≈178 — the tool clicked y=145).
- [ ] **S3 `fl_notes(action="clear_queue")`** — back up `mcp_request.json`
  (timestamped) then write `[]`; return the number of queued requests dropped.
- [ ] **S6 Multi-channel note write** — `fl_notes(action="write_parts",
  parts=[{channel_index, notes}], target_pattern)` runs the per-channel
  handshake in sequence; stops at the first failure with nothing queued.
- [ ] **S7 Friendlier inputs** — `fl_channel set_steps` accepts
  `bars=[[1,7],…]`; `fl_notes write_steps` accepts
  `melody=[["C#4","G#4",…]]` + `step_beats` / `"~"` holds / note names
  (reuse `tools/song_builder.py` `expand_steps`/`melody_to_notes`/`parse_note`).
- [ ] **S8 FLEX preset by name** — `fl_plugin(action="load_preset", index,
  preset)` via the FLEX browser search box (OCR-verified rename);
  `fl_plugin(action="list_presets", query)` from the `.flexpack` indexes.
- [ ] **S9 Export for the compare loop (= D1)** — `fl_file export` through
  the native ⌘R dialog (path + Pattern mode + Start, AX-verified file on
  disk), then `fl_audio analyze` on the render.
- [ ] **S10 Playlist arrangement** — probed: no clip placement in v45
  (`playlist` has track name/colour/mute/solo/live-clip only). S5 chain is
  the supported route; playlist painting via UI automation only if asked.

## Open — Sprint L (live-check fixes, 2026-10-01)

- [ ] **L16** native-menu paths still unbuilt: `fl_mixer add_fx`,
  `fl_channel clone`, `fl_plugin load_preset` (server-side; pattern =
  `utils/add_channel.py`).

---

## Done (ledger)

Full detail in the git log; verify commands still runnable as written.

**Sprint A (2026-10-01, all live-verified):**
- **A1** module-level lock around the MIDI JSON channel — `tests/test_midi_lock.py`
- **A1b** protocol v2 server half: `request_id` + `protocol_version` echo; stale
  replies never consumed; `mcp_audit.jsonl` audit (`FL_MCP_AUDIT=0` off) — `tests/test_protocol.py`
- **A2** dispatcher core (`dispatcher.py`: registry, pydantic discriminated
  unions, per-action timeout table) + **protocol v2 controller half** (v4;
  `state_after` same-trip read-back; live-verified) + **`fl_exec_python` gate**
  (off unless `FL_ALLOW_EXEC=1`; audit-logged) — `tests/test_dispatcher.py`,
  `tests/test_controller_proto2.py`, `tests/test_exec_gate.py`
- **A3** safety tiers (`safety.py`: read/write/destructive; one
  `general.saveUndo(name, 0)` per WRITE trip; scratch = `SCRATCH_` title AND
  folder; first-destructive-per-session confirm; identity verify before
  destructive) + controller v5/v6 `_safe_exec` (live: `setBPM 131` +
  `undo_saved`) — `tests/test_safety.py`, `tests/test_controller_safety.py`
- **C0** FL undo-history cap = **100 levels** (probed; one saveUndo/trip is
  safe for 100 trips; `saveUndo(name, flags)` is 2-arg-required)
- **A4** `fl_delete` (channel|pattern|pattern_data|fx|roll_notes; 5
  controller `delete.*` handlers via `_safe_exec`) — `tests/test_delete.py`
- **A5** `fl_batch` (N actions in ONE MIDI trip; one saveUndo; rejects
  destructive; stop-on-fail; `rollback: true` best-effort) — `tests/test_batch.py`
- **A6** oneOf pilot: 20 scripted prompts → **20/20 valid first-try = PASS
  (≥95%)** → ship the discriminated-union surface — `tests/test_pilot_a6.py`

**Sprint B (2026-10-01, built + unit-tested; live-verified 8/10 the same day):**
- **B1** `fl_state` (+ roll-state mtime guard; the 11.8 h incident = fixture)
- **B2** `fl_transport` (8 actions incl. real-BPM `set_bpm` vs `set_speed`)
- **B3** `fl_mixer` (set_vol/pan/route/sends/add_fx; remove_fx → fl_delete)
- **B4** `fl_channel` (set_vol/pan/rename/route/mute/solo/clone/add; add =
  native Add menu — the only creation path; clone via the channel menu)
- **B5** `fl_pattern` (create/select/rename/set_len/clone; **2-arg**
  `setPatternName` — C4; 3-arg crashed FL)
- **B6** `fl_notes` (write_steps with the §6b handshake; read_steps;
  **import_midi** — C3, live-verified; live_play/quantize)
- **B7** `fl_plugin` (list_params/set_param; load_preset = native-menu gap → L16)
- **B8** `fl_file` (open = destructive tier; save/export = no v45 API →
  `fl_connect save`)
- **B9** `fl_help(domain)` (11-domain knowledge base carrying the gotchas)
- **B10** 86 legacy tools gated behind `LEGACY_TOOLS=1`; 13-tool default
  surface; skills migration done (`scripts/skill_tool_refs.py` self-check);
  legacy fl_load_beat/melody/list_presets RETIRED into `fl_preset` (R5)

**Sprint C (done):**
- **C3 PASSED live 2026-10-01 (PE):** the roll's own **File > Import MIDI
  file...** imports into the roll's current channel + pattern; wired as
  `fl_notes import_midi` (commit `c32626d`) — import REPLACES the
  channel's notes in the pattern; go-to field set by accessibility (typed
  keystrokes drop digits) — mechanics: `docs/UI-AUTOMATION.md` §3.4
- **C4** `patterns.setPatternName` is **2-arg** in live v45 (3-arg crashed
  FL); `general.saveUndo(name, flags)` is the 2-arg-required one

**Sprint L (2026-10-01; all but L16):**
- **L-a…L-e** test-suite FL isolation (`tests/conftest.py`) · roll retarget
  via **Vision OCR of the on-screen title** · key-drift guard test (every
  MCP action: handler must exist and read every key it sends) · read
  payloads surfaced · real `fl_channel add` / `set_swing` / `fl_notes
  channel_index` / preset slides
- **L1/L2/L4–L12/L18** MCP-side fixes (route keeps send level; add_fx refuses
  before FL; dB read-back labels; tier fixes; bounded dumps; fl_version from
  `ui.getVersion`; clone no longer switches pattern; position read-back;
  docstring fixes; `fl_channel list`; **L18: a state file older than the
  running FL's start = always stale**)
- **L3/L13/L14/L15** via **v10.4e** (deployed + live matrix 2026-10-01):
  batch read payloads lifted · `setTimesig` (absent; real API
  `general.setNumerator/setDenominator`, no getter) · channel volume linear
  read-backs (dB-mode flag fixed) · file save/saveAs/export handlers
  (matrix pinned: **no importable file API in v45** → honest refusal pointing
  at `fl_connect save`)
- **S2.3 closed (same matrix):** symmetric `useGlobalIndex` — 30/30 step
  params persisted cross-trip, both flag domains, all 5 channels (the old
  per-channel drops were the SET/GET flag asymmetry)
- **L17 peak meters:** `fl_mixer get_peaks` live — `getTrackPeaks(t, mode)`
  = linear (1.0 = 0 dBFS, decays ~0.2 s); **v10.4g-peaks deployed 2026-10-02**
  (dedicated `mixer.getPeaks` action)

**Controller versions (deployed history, newest first):**
v10.4g-peaks (installed, md5 fd0f94a9) ← v10.4f-rack (lastgood, 0eaa1922:
grid-loop-first rack-clear + `remaining_grid_bits`, `set_timesig` →
`general.setNumerator/setDenominator`, honest no-API file refusals) ←
v10.4e-sym (useGlobalIndex symmetry + read-back re-verification, clearPattern,
L3/L13/L14/L15) ← v10.4d (`ui.keySeq` — the §0 one-call selection) ←
v10.4b/c (screen quarantined; ui getter+key-event allowlist) ← v10.3 (Gopher
probe; step-param constants) ← v10.1 → v9-patterns → v8-state → v7-batch →
v6/v5 (protocol v2 + `_safe_exec`).
**Crash discipline:** after ANY crash restore `device_FLStudioMCP.lastgood.py`
from git before the next open; v10-stepparams and v10.4 (212ce1ea) =
crashing builds — never redeploy.
