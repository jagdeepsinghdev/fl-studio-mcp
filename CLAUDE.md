# CLAUDE.md — ROUTER for the FL Studio MCP repo

_You are in the **FL Studio MCP** repo: **`fl-studio-mcp/`**
(the MCP server) + **`skills/`** (optional Claude skills for it). Pure MCP: nothing
here imports or runs another app. This file routes you to the right
doc/skill/file and states the hard rules. **Read it before doing anything.**_


---

## HARD RULES (enforce on every task)

### FL Studio control
1. **All FL Studio control goes through the `flstudio` MCP server** (`.mcp.json` at
   the repo root; `uv run fl-studio-mcp`). Raw `rtmidi` / `osascript` / `pynput`
   are **discovery-only** — never routine control.
2. **Missing capability → ADD A NEW TOOL to the MCP server**
   (`fl-studio-mcp/src/fl_studio_mcp/tools/*.py` + register in `server.py`).
   Then `mcp({ connect: "flstudio" })` reloads it — **no FL restart** for
   MCP-side changes.
   **Two MCP layers are enabled by default for this repo** (see `.mcp.json`):
   `flstudio` (control; project-scoped via `.mcp.json`) + **computer use** (the
   `pi-computer-use` native tools: `find_roots` / `observe_ui` / `act_ui` — enabled for this
   project via `.pi/settings.json` → `packages`, and also in the global pi settings).
   Use computer use to **observe/verify** FL's
   windows (screenshots of the Channel Rack, the piano-roll toolbar, the script
   dropdown) and for clicks in web-rendered areas (the toolbar has no AX tree).
   **Do not reach for playwright/chrome/mobile MCP for FL** — they are for
   browsers/devices, not desktop apps; the native computer-use tools are the
   right layer here.
3. **Never fire two `flstudio` MCP calls in parallel** — one shared
   command/response file pair (`mcp_command.json` / `mcp_response.json`).
   Sequential calls only.
4. **Controller changes** (`fl_controller/device_FLStudioMCP.py`) **DO need an FL
   restart**: sync the file to `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`,
   relaunch FL, verify (else `Unknown action`).
5. **The per-session ComposeWithLLM selection is AUTOMATED — call `fl_select_script(channel_index=<target>)`**
   once per FL session (it selects the channel, opens the roll, and clicks the script into
   place). No config file / API / Tools→Scripting menu persists it (verified), and there is
   no manual step left — the tool does the coordinate clicks. If it reports a miss (FL
   layout shifted), pass explicit `wrench_x`/`script_x`/`script_y`. A trigger keystroke only
   lands when FL is frontmost. See `skills/fl-melody` → `references/piano-roll-setup.md`.
6. **Don't clobber the user's FL session.** FL is often running with the user's
   own project. Check `fl_state` (transport / bpm) before assuming playback state;
   never clear patterns/channels without knowing what's loaded
   (`fl_state`, `fl_notes(action="read_steps")`, `fl_channel(action="list")`).
6b. **Never write notes without the roll handshake.** The ComposeWithLLM script applies queued notes to the piano roll that is
   OPEN, not the selected channel. Open the target's roll (select it, F7), confirm the title, run an empty script trigger
   (writers with `channel_index` do the retarget + OCR title proof for you) and check `fl_state` /
   `fl_notes(action="read_steps")` shows the target's notes (0 for an empty new channel) BEFORE
   `fl_notes(action="write_steps")`; afterwards check `mcp_response.json` (`notes_deleted`). Never leave a
   write queued: `fl_notes(action="clear_queue")` backs up `mcp_request.json` and empties it.
   Details: `skills/fl-melody`.
7. **FL 2026's built-in MCP (Image-Line "Gopher": `MCPTools.pyc`, ~44–50 tools
   incl. `run_piano_roll_script`)** is **in-process only on macOS** — verified
   2026-09-29: it is a `WKUserContentController` message handler on FL's own
   webview, with no network endpoint, no URL scheme, and no inspector hook
   (investigation notes, 2026-09-29). It is **not** practically reachable
   from outside; do not build on injection/CDP hacks. **2026-10-02 (PE) —
   CLOSED (negative):** live controller probe (`fl_probe(action="ilmcp")`, v45,
   v26.1.6 PE): **`ilmcp`, `flmcp`, `gopher`, `mcp`, `pianoroll`,
   `flpianoroll`, `notes` ALL raise `ModuleNotFoundError`** in the controller
   context. `flpianoroll.score` is the note API but is **context-injected into
   piano-roll script runs only** — the official docs
   (`pianoroll_scripting_api.htm`, `midi_scripting.htm`) document it under the
   roll-script context and list no other module for note writing. Gopher's
   backend is compiled privately into FL's webview process — **unreachable from
   outside, full stop; do not re-investigate.** The productive PE-era path is
   the **`ui` module (64 fns, callable — key events included; `screen` is
   quarantined)** — see §5. The per-session selection stands but is now
   MCP-automatable (see §0).

### Audio and song material
9. **No audio / MIDI renders / model weights in git** (`.gitignore` covers them; test
   fixtures are generated in the tests).
10. **Song-derived material is for private learning only**: note the source, keep it
    private, never commit or share the audio, stems, renders or song-derived presets.
12b. **Analysis gaps are REPORTED, not hidden or auto-fixed**: `fl_audio analyze` returns
    them in `gaps` (estimators disagree, weak key, unsure chords).

### Repo hygiene
13. Commit at the **repo root** for the MCP + skills.
14. Push only when the owner asks.
15. **`INVENTORY.md` is auto-generated, not hand-edited.** After adding/removing/renaming a
    tool (`fl-studio-mcp/src/fl_studio_mcp/tools/*.py`), skill (`skills/*/`), or preset
    (`fl-studio-mcp/presets/*/`), re-run
    `cd fl-studio-mcp && uv run python scripts/gen-inventory.py` and commit the result. Never
    hand-edit the generated tables.

---

## ROUTER — where to look for what

| You want to… | Go to |
|---|---|
| Understand the whole system / find a file / see all MCP tools | **`README.md`** (architecture map) |
| Do FL Studio work right now (manual step, timing, gotchas, API facts) | **this file** (§0–§3) |
| Build drums + melody (any instrument) in one call | **`skills/fl-song-builder`** + agent guide **`fl-studio-mcp/AGENT-SONG-BUILDER.md`** |
| **One click per GENRE (16: trap, drill, hip-hop, lofi, r&b, pop, afrobeats, house, techno, future bass, dnb, dubstep...): tempo + genre drum KIT + beat + Keys/Bass + chords + bass + levels; drum kit alone = `load_kit`** | **`fl_genre("load", genre=...)`** / **`fl_genre("load_kit", genre=...)`** + `skills/fl-genres` (packs `fl-studio-mcp/presets/genres/*.json`, kits `presets/kits/*.json`) |
| **One click VOCAL setup (buses + 9-plugin chain + reverb/delay), chains/presets/knobs in real units, mastering** | **`fl_vocal("setup")`** / `fl_vocal("apply", ...)` + `skills/fl-mixing` (recipes `fl-studio-mcp/presets/vocal/`) |
| **A sample/song file: tempo (2 estimators, disagreement flagged), key, chords, 808 root note; cut a section; isolate left/right; load to a new Sampler** | **`fl_audio`** (analysis is numpy in-process, `src/fl_studio_mcp/audio/analysis.py`) |
| **Chords typed as text ("Am F C G", slash chords) -> piano roll; rescue what you PLAYED (score log -> pattern)** | **`fl_notes("write_chords")`** / **`fl_notes("capture")`** (empty-log warning auto-dismissed) |
| Build a track fast | `README.md` §4, or `fl-studio-mcp/build-track.sh list` |
| Add a new beat / melody preset (FL) | `fl-studio-mcp/presets/README.md` — drop a JSON, no code |
| **Launchpad / 8×8 grid → step sequencer (setup + use + troubleshooting)** | **`fl-studio-mcp/docs/LAUNCHPAD-SETUP.md`** + `fl_launchpad` tool (status/map/calibrate/apply/light; v10.1 input monitor feeds it) |
| **Music theory — the main brain** (which notes/chords/rhythm and why, ragas incl. Bhairavi, genre DNA, ear training, reading a song analysis, learning from a reference without copying) | **`skills/music-theory`** (topic index in its `SKILL.md`) |
| **Any FL task — start here** (domain index) | **`skills/fl-studio`** → then one domain skill (`fl-setup`, `fl-presets`, `fl-patterns`, `fl-melody`, `fl-mixing`, `fl-plugins`, `fl-genres`, `fl-song-builder`) |
| A genre (trap, reggaeton, lofi, …) or a melody recipe | `skills/fl-genres` (per-genre references) / `skills/fl-melody` (`references/genre-recipes.md`) |
| **The 0ComposeWithLLM piano-roll script selection (§0 — automatic on the first note write per FL process)** | **§0 above**; manual fallback `fl_select_script(channel_index=N)` → `skills/fl-melody` → `references/piano-roll-setup.md`; mechanics `fl-studio-mcp/docs/UI-AUTOMATION.md` §3.1 |
| **Adding / changing skills (anti-bloat rules)** | **`skills/README.md`** — enforced by `fl-studio-mcp/tests/test_skills.py` |
| **FL Studio control: sprints/tasks in flight (dispatcher refactor, 10 domain tools)** | **`fl-studio-mcp/DEV-TASKS.md`** |
| Add an instrument channel (native Add-menu mechanics) | `fl_channel add` — `fl-studio-mcp/docs/UI-AUTOMATION.md` |
| **How the server drives FL's UI (5 layers, oracles, flows, add-a-new-automation checklist, debugging)** | **`fl-studio-mcp/docs/UI-AUTOMATION.md`** |
| **Press FL's own keyboard shortcuts (226 from the manual, guarded: focus proof, collisions, confirm tier)** | **`fl_shortcut`** + catalog `fl-studio-mcp/shortcuts/catalog.json`; mechanics `fl-studio-mcp/docs/UI-AUTOMATION.md` §3.6 |
| **See the screen + drive the mouse by hand or in code (OCR-anchored clicks, custom menus, stuck-mouse fixes)** | **`fl_screen`** MCP tool (look/ocr/find/hint/click_text) + **`fl-studio-mcp/docs/SCREEN-CONTROL.md`** + CLI `fl-studio-mcp/scripts/screen.py`; FL stuck -> `fl_connect("doctor"/"recover"/"tidy")` |
| **Any song → FL ready to edit (one command; steps, checks, troubleshooting)** | **`fl-studio-mcp/docs/SONG-TO-FL.md`** + `fl-studio-mcp/scripts/song_to_fl.py` / `fl_preset(action="load_song")` |

---

## §0. The ComposeWithLLM script selection (per FL process — AUTOMATIC since 2026-10-01)

> **FL's piano-roll script selector resets to NONE on every launch — and nothing
> persists it.** Verified empirically 2026-10-02 on a *fresh* process: the wrench
> menu showed no selection; a trigger with no selection ran nothing (no
> ScriptDialog, no side effects). Grep of the entire `~/Documents/Image-Line` tree
> finds no persistence store (only our own controller files). There is also **no
> native menu route** (the Tools menu has no "Piano roll scripts" item — the
> wrench is the only door). So once-per-session selection is an **FL design
> fact**, but it is now **fully automatable with MCP calls** — no user clicking.

**How the selection is committed (v10.4d — ONE call, proven on a fresh
process):** `fl_select_script(channel_index=N)` does the whole thing:
1. selects the channel;
2. clicks the wrench and **probes `ui.isInPopupMenu`** (a proven safe-read:
   1 = menu open). The wrench glyph only exists in the roll toolbar, so this
   one probe both opens the menu AND detects the roll's state — no blind
   toggles (the roll is web-docked and **invisible to System Events**, so
   window-list/pixel detection can't be trusted); if the first click opens
   nothing, it opens the roll via the native View menu and clicks once;
3. sends `ui.keySeq(["up"]×6 + ["enter"])` — ONE controller trip that
   navigates the flat 27-item menu (19 built-ins + 8 scripts; `up` from the
   empty state wraps to the LAST item; 6 ups = **0ComposeWithLLM**; `enter`
   commits). Key events are **never sent unless the menu probe confirmed the
   menu is open** (they would otherwise land on whatever form has focus —
   e.g. the user's browser panel). `getHintMsg` is a STALE slot and does NOT
   track the highlighted item — a screenshot is the highlight oracle if you
   re-count by hand.
4. Handshake: the **script runs once at selection time** —
   `piano_roll_state.json` mtime updates on `enter` (plus again on any
   trigger). `fl_state` / the state file (`noteCount`) confirm.

The script file was renamed **`ComposeWithLLM.pyscript` → `0ComposeWithLLM.pyscript`**
(sorts FIRST in the merged user+factory list — shortest/stable target; the old
name is an alias in `fl_select_script`). Factory scripts live in
`/Applications/FL Studio 2026.app/Contents/Resources/FL/System/Config/Piano roll
scripts/` (Arpeggiator, Euclidean, Humanize, Note repeater sprinkler, Select by
velocity and more); user scripts in
`~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/`.

- **AUTOMATIC since 2026-10-01 (`utils/roll_session.py`):** every queue write goes
  through `trigger_fl_studio()`, which selects the script once per FL **pid**
  (queue stashed to `[]` during the selection run; recorded in
  `Piano roll scripts/.mcp_script_session.json`) and self-heals once if a
  trigger doesn't update the state file. Live-verified: the selection
  **survives channel switches** (one per FL process, not per channel).
  **`channels.selectOne` does NOT retarget an already-open roll** — writers
  with `channel_index` (`fl_preset load_melody`, `fl_notes write_steps`) call
  `open_roll_for_channel`: select, then toggle View > Piano roll until the roll
  title **as drawn on screen** (`Piano roll - <name>`, read by macOS Vision OCR,
  `scripts/ocr_text.swift` → `.generated/bin/ocr_text`) equals the channel
  name, else refuse. **Do not trust the engine for this:** the docked roll's
  `ui.getFocusedFormCaption` is just `'Piano roll -'`, and a focus-based
  close→reopen proof is fooled by any plugin window (2026-10-01: after
  `fl_channel add 3x Osc` opened its editor, a retarget to ch5 "passed" while
  the roll stayed on '808' — the keys were written into the 808 and wiped by
  the next write). FL also redraws the title ~1 s late (settle before OCR).
  Disable with `FL_AUTO_SELECT_SCRIPT=0`. Manual call below stays available.
  **Known limit:** the match is screen-title == channel name; a roll title
  showing a name the channel no longer carries refuses after 5 toggles (safe,
  a false refusal). Needs Screen Recording permission for the server process.
- **C3 PASSED (2026-10-01):** the piano roll's own **File > Import MIDI file...**
  imports a `.mid` into the roll's current channel + pattern (4/4 notes exact). Route
  + gotchas (native Open panel: set the go-to field via accessibility — typed
  keystrokes drop digits) in `fl-studio-mcp/DEV-TASKS.md` C3. This can replace the
  ComposeWithLLM queue for note writing once wired as `fl_notes import_midi`.
- **keySeq focus rule:** in-engine keys go to the FOCUSED form. If another web
  panel (e.g. the FL Cloud browser) holds focus, the menu probe can say "open"
  while up×6+enter silently miss. A View > Piano roll toggle re-focuses the
  roll (observed 14:37 miss → 14:43 success, 2026-10-01).
- **Manual fallback (normally not needed — the first note write does it):**
  `fl_select_script(channel_index=N)` — ONE
  MCP call (controller v10.4d: `ui.keySeq` ships the key sequence in one
  trip). Params: `method="keys"` (default) / `"click"` (trial-era row-click
  fallback — 30 px row model, misses on the PE layout — last resort only),
  `up_steps` (default 6 = 0ComposeWithLLM; re-count if scripts are
  added/removed), `open_only` (manual key driving). If the menu probe
  fails twice the tool fails loudly and sends NO keys.
- **Ran-oracle:** `~/Documents/Image-Line/FL Studio/Settings/Piano roll
  scripts/piano_roll_state.json` mtime updates on EVERY run (selection and
  trigger). Stale mtime = the selection didn't take.
- All note-writing tools (`fl_notes` write_steps/clear, the legacy
  and `fl_preset(action="load_melody")` — the legacy `fl_send_notes`/
  `fl_send_chord` exist only behind `LEGACY_TOOLS=1`; `fl_load_melody`/`fl_load_beat` were retired 2026-10-01)
  funnel through this
  one script — there is no direct FL Python API for writing piano-roll notes (only
  the `flpianoroll`/`flp` script context, reached via the trigger). The built-in
  MCP `run_piano_roll_script` (Gopher) would make this obsolete if reachable —
  see hard rule 7 (resolved: it is not, from our context).
- A trigger keystroke only lands when FL is **frontmost**.
- See `skills/fl-melody` → `references/piano-roll-setup.md` and the §5 API facts.

## §1. MCP-first control and reload semantics

- **MCP-side change** (new tool, server code): edit `src/fl_studio_mcp/` →
  `mcp({ connect: "flstudio" })` → done, no FL restart.
- **Controller change** (`fl_controller/device_FLStudioMCP.py`): sync to
  `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/` → **FL
  restart** → verify (else `Unknown action`).
- Raw command probe (discovery only): write `{"action":"...","params":{}}` to
  `mcp_command.json`, send MIDI `[0x90,127,127]` to CoreMIDI port
  `FL Studio MCP` via rtmidi, read `mcp_response.json`.

## §2. Timing gotchas (why tracks "play for a bit then go empty")

1. **Real BPM vs speed multiplier.** `fl_transport(action="set_bpm", bpm=N)` sets the **real** tempo
   (`mixer.setCurrentTempo(bpm*1000)`). `fl_transport(action="set_speed", speed=X)` only plays
   faster/slower *without* changing the BPM — they stack; reset speed to `1.0`
   after setting BPM. `fl_preset(action="load_beat", base_bpm=N)` applies a speed multiplier only when `base_bpm>0` (default: don't touch).
2. **Pattern length.** A new FL pattern is **16 beats**, not 4. A 4-beat beat in
   a 16-beat pattern = 4 beats of sound + 12 of silence. Fix:
   `fl_pattern(action="set_len", pattern=N, beats=B)`.
3. **Named channels (dhol, tabla, …).** `fl_preset(action="load_beat")` matches drum parts **by
   channel name** and clears all drums first. To add a dhol:
   `fl_channel(action="add", plugin="Sampler", name="Dhol")`, then a `"dhol": {"name":"Dhol","pattern":[...]}`
   part in the beat preset. Sound comes from whatever sample the Sampler holds.
4. **Creating patterns — never `jumpToPattern` onto an empty one** (it opens a
   modal "Pattern N name" dialog that blocks the whole controller). Use
   `fl_pattern(action="create", name=...)` (names the next free slot, no jump), then
   `fl_pattern(action="select", pattern=N)` (refuses non-existent patterns).
   `fl_pattern(action="clone", pattern=N)` clones into slot+1 and **shifts later patterns up** — re-list before
   addressing. Note writers take `target_pattern` and select it first.

## §3. Building a track (the 3+1 recipe)

**From a song folder — ONE call:**
`fl_preset(action="load_song", song_dir="<folder with song.json>", label="MySong")`
= tempo + beat (tiled to the pattern) + melody on '<label> Melody' (FLEX) + the bass line
on '<label> Bass' (a Sampler holding the song's own bass hit, else FLEX) + `fix_clipping`.
Folder format: `fl-studio-mcp/docs/SONG-TO-FL.md` (any tool can write it). Channels are
created when missing. Needs FL frontmost + mouse
untouched (~2 min).

```
fl_channel(action="add", plugin="FLEX", name="Piano")   # add+route+rename+select piano
fl_preset(action="load_beat", preset="<beat-preset>")            # step-sequencer drums (+ per-step params if a variation)
fl_transport(action="set_bpm", bpm=120)          # REAL tempo
fl_transport(action="set_speed", speed=1.0)
fl_pattern(action="set_len", pattern=1, beats=20) # match phrase length (beats)
fl_select_script(channel_index=<piano idx>)       # select ComposeWithLLM + open the roll (was the manual step)
fl_preset(action="load_melody", preset="<melody-preset>")        # queued via ComposeWithLLM + auto-trigger
# (each fl_preset load also runs fl_mixer fix_clipping on the master — auto_level)
fl_transport(action="loop", mode="pattern")
fl_transport(action="play")
```

**Multi-section song** (one pattern per section; no playlist API):
```
fl_pattern(action="create", name="Verse", length_beats=16); fl_pattern(action="create", name="Chorus", length_beats=16)
fl_preset(action="load_beat", preset="trap", target_pattern=1)
fl_preset(action="load_beat", preset="trap", target_pattern=2)
fl_preset(action="load_melody", preset="a-minor-pop", target_pattern=1, channel_index=<piano idx>)
fl_preset(action="load_melody", preset="a-minor-pop", target_pattern=2)
fl_transport(action="set_swing", swing=0.2)
# markers: legacy only (fl_add_marker, LEGACY_TOOLS=1) — no domain action yet
fl_pattern(action="select", pattern=1); fl_transport(action="play")   # audition one section at a time
```

Any beat × any melody preset mix; new preset = drop a JSON in
`fl-studio-mcp/presets/{beats,melodies}/`.

## §4. Key paths

| Thing | Path |
|---|---|
| **Inventory (all tools/skills/presets)** | `INVENTORY.md` (repo root) (auto-generated; regenerate with `cd fl-studio-mcp && uv run python scripts/gen-inventory.py`) |
| MCP config | `.mcp.json` (repo root) |
| Skills | `skills/` (optional; `skills/install.sh`) |
| Controller (source / installed) | `fl-studio-mcp/fl_controller/device_FLStudioMCP.py` / `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/` |
| Piano-roll script | `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/ComposeWithLLM.pyscript` |
| Runtime JSON | same dir: `mcp_request.json`, `mcp_response.json`, `piano_roll_state.json` |
| FL presets | `fl-studio-mcp/presets/{beats,melodies}/*.json` |
| MIDI loop (bridge) | LaunchAgent `com.flstudiomcp.fl-midi-loop` (`fl-studio-mcp/scripts/install-midi-loop.sh`; other label: `FL_MIDI_LOOP_LABEL`) |

## §5. API facts (discovered; don't re-discover)

- **Swing:** `channels.getSwing()/setSwing(x)` — no channel arg (global, 0–1).
- **Sends:** `mixer.getRouteSendActive/getRouteToLevel/setRouteTo/setRouteToLevel(src,dst)`;
  raises "Index out of range" when `src == dst`.
- **BPM:** `mixer.getCurrentTempo()/setCurrentTempo()` — **BPM×1000**.
  `transport`/`general` have no bpm accessor.
- **Pattern length:** `patterns.getPatternLength(idx)/setPatternLength(idx, beats)` —
  `idx` **0-based** (Pattern 1 = 0), unit **beats**.
- **Step parameters** (S2.3, live-verified 2026-10-02 on v10.4d): the official
  `midi` stubs define exactly 8 types — pPitch=0 … pShift=7; **there is NO
  pRepeat** (the channel-rack "step repeat" UI has no Python API in v45).
  Writes via `setStepParameterByIndex` never raise; **persistence is
  per-channel-instance** in the 808-rack session: velocity stuck on all 5
  channels; shift/pan stuck on ch0/ch4 but silently dropped (read-back -1)
  on ch1/ch2/ch3. GET calls use `useGlobalIndex=False`, SET uses `True` —
  open root cause (v10.4e candidate: symmetric flag + same-trip read-back
  re-verification in the dispatch). `patterns.clearPattern(idx)` EXISTS in
  live v45 (missing from the stubs); there is no pattern delete (FL cannot
  remove pattern slots — clearing is the deletion).
- **No `channels.add()`** — adding a channel needs the native Add menu
  (automated by `fl_channel(action="add")`; the legacy `fl_add_instrument` / `fl_setup_instrument` need `LEGACY_TOOLS=1`).
- **Tool params:** `fl_transport(action="set_speed")` takes **`speed`**;
  `fl_channel(action="route")` takes **`index`** + **`to`** (the legacy
  `fl_route_channel_to_mixer` took `channel_index`).
- **Synthetic input (pynput/CGEvent) does NOT reach FL's custom-drawn UI** (pattern/channel name fields,
  roll toolbar, script dropdown) — 4 attempts; it likely reads keys below CGEvent level.
  **Karabiner virtualHID** (appears as a real keyboard) is the open test → `fl-studio-mcp/DEV-TASKS.md` C5.
  Native AppKit surfaces (file panels, confirm dialogs, menus) DO accept synthetic input fine.
  **Correction (live 2026-10-04): FL's own HOTKEY table DOES take System Events keystrokes** while
  FL is frontmost — F-keys, named keys (PgUp/PgDn, Backspace, arrows, Space) and cmd/opt combos
  land (⌘L legato, ⌘↑ octave, ⌥W wave view, F5–F9); **bare/shift-only letters and digits never
  do** (tool letters, L, R, mixer S). The custom-drawn TEXT FIELDS above remain unreachable.
  → `fl_shortcut` (catalog `fl-studio-mcp/shortcuts/catalog.json`, UI-AUTOMATION §3.6).
  **Focus facts (same day):** `ui.setFocused` / `ui.showWindow` on a VISIBLE window, a View-menu
  toggle and a title-bar click do NOT move focus; **hide+show** does. After any Browser key,
  `getFocused`/`getFocusedFormCaption` stick on "Browser" (even hidden) while keys go elsewhere —
  escape: hide Browser → hide+show channel rack → hide+show the target.
  **`fl_notes read_steps` after a shortcut returns the PRE-shortcut export** (same mtime) —
  re-trigger (empty queue) first; `fl_shortcut` roll edits do this and return `roll.before/after`.
  Mac caveat: **F2 = brightness** unless "Use F1, F2 as standard function keys" is on (fn+F2 works;
  FL manual lists F2 = Rename-and-color). **Renaming patterns does NOT need the UI:**
  `patterns.setPatternName(index, name)` — **2-arg in live v45** (verified 2026-10-01: 2-arg
  renames; a 3-arg call with `flags` CRASHES FL 26.1.6.5406 — EAccessViolation, log in
  Support/Logs/Crash). Earlier note "3-arg in v45" came from misreading `general.saveUndo`'s
  "missing required argument 'flags' (pos 2)" error.
- **Meters + faders (live 2026-10-02):** `mixer.getTrackPeaks(t, mode)` = LINEAR
  (1.0 = 0 dBFS), decays in ~0.2 s, and is **PRE-fader** (a 5 dB master cut moved it
  ~1 dB = noise). `mixer.setTrackVolume` is applied AFTER the script trip — a read in
  the same trip returns the previous value (a one-trip fader search drove the master to
  0 = silence; also makes `fl_mixer set_vol`'s same-trip state_after stale). Set in one
  trip, read in the next. `getTrackVolume(t, 1)` = fader in dB (0.8 = 0.0 dB). Clipping
  is fixed by `fl_mixer fix_clipping` (pre-fader peak + fader dB = target) and runs
  automatically after every `fl_preset` load (`auto_level`, -1.5 dBFS).
- **Effect slot on/off (live 2026-10-03):** `mixer.setPluginMuteState(t, s, v)` is ONE-WAY
  in v45 - it switched slots OFF, but 0/1/True never switched them back ON. Use the
  documented REC event: `general.processRECEvent(mixer.getTrackPluginId(t, s) +
  midi.REC_Plug_Mute, 1|0, midi.REC_UpdateValue | midi.REC_UpdateControl)` (1 = ON);
  read back with `getPluginMuteState` (1 = ON, despite the name). Wrapped as
  `fl_mixer(action="fx_on", track, on, [slot])`. `ui.showPicker` (undocumented) opens nothing.
- **No remove-plugin API** (plugins/mixer: mute, mix level, colour only) — effects are
  added/removed through FL's own picker / slot menu (`fl_mixer add_fx`,
  `fl_delete target=fx`), both verified by the slot read-back.
- **Undo:** `general.saveUndo(name, flags)` — 2-arg, **flags required** (pos 2); verified 2026-10-01
  (`saveUndo(name, 0)` OK, `getUndoHistoryCount()` grew). **Undo-history cap = 100 levels**
  (C0, probed 2026-10-01 on trial: count stopped at 100 after 97 new levels) → one saveUndo per
  trip is safe (100 trips before eviction).
- **`device` module IS importable from any script context** (v45/macOS, probed 2026-10-02) — the
  MIDI-controller-script module. 35 callables, all **output/dispatch/link** oriented:
  `midiOutMsg/midiOutNewMsg/midiOutSysex` (send MIDI out on the device's port),
  `dispatch/sendMsgGeneric/forwardMIDICC` (route received events),
  `getDeviceID/getName/getPortNumber/isAssigned/isMidiOutAssigned` (identity getters),
  linked-param control (`getLinked*`, `linkToLastTweaked`, `setMasterSync`, …).
  **No input-port setter anywhere in the entire importable API** (swept general/patterns/
  channels/mixer/midi/device — only getter is `channels.getChannelMidiInPort`). Selecting
  which input device FL listens on lives only in the web-rendered MIDI-settings screen →
  one-time manual pick (persists across restarts) or coordinate-click automation (P3-class).
- **No clone / delete-channel API** (v45, live 2026-10-02: `channels.deleteChannel` raises
  AttributeError). Both go through the channel button's menu (Clone / Delete… + FL's
  "about to be deleted" confirm): `fl_channel(clone)`, `fl_delete(channel, index, name)` —
  identity by name before any click, proof = the channel list. FL inserts a clone right
  after its source and shifts later channels (re-read indices).
- **No importable channel-creation API** (v45): the only Python-level creator is `ilmcp.addChannel`
  — compiled in, in-process-only (Gopher's `add_channel` calls it). The native Add menu remains the
  creation path; the deferred bridge plugin is the only route to `ilmcp`. (**2026-10-02 correction:**
  `import ilmcp` fails — ModuleNotFoundError from the controller; the pyc string was misleading. If
  `flmcp`/`gopher`/`mcp` never probe out either, the native Add menu stays the only creation path.)
- **Step parameters (P4 CLOSED 2026-10-02):** official API per image-line manual
  (`midi_scripting.htm` #stepParams): `channels.setStepParameterByIndex(index, patNum, step, param,
  value, useGlobalIndex)` + getter `channels.getCurrentStepParam(index, step, param, useGlobalIndex)`.
  Constants: pPitch=0, **pVelocity=1**, pRelease=2, pFinePitch=3, pPan=4, pModX=5, pModY=6,
  pShift=7, pRepeat=8 (the fl-bridge 'SPT_*' names do not exist in v45; a 4-arg
  `getStepParameterByIndex` does not exist either — live AttributeError). **A step parameter can
  only be set on an ACTIVE step** (grid bit on): on an empty step the set reports success but the
  read-back stays -1 ("unset") — P5 "success messages lie" again. patNum = active 1-based
  `patterns.patternNumber()` (verified working; 0/1-base question moot — it works).
- **`ui`/`screen` modules (PE era — CRASH-MAPPED 2026-10-02):** both import
  safely from the controller on PE (the trial build aborted FL on any such
  *call* — libLicenceEngine; PE imports fine). **But the first live call —
  `screen.menuShowing()` (no args) — killed FL: `EAccessViolation`,
  *side thread*, in `FLEngine_x64.dylib`** (crash log `Crash 2026-10-01_155324`;
  FL auto-exited after the error dialog; session restored from autosave).
  **Treat `screen.*` as QUARANTINED end-to-end** (v10.4b refuses it at both
  layers) until functions are proven one at a time — a no-arg call into native
  menu code faults instead of raising, so "the exception text is the signature
  oracle" does NOT apply to `screen.*`. `ui.*` is being expanded from a
  **pure-getter subset only** (getProgTitle/getVersion/getFocused*/getHint*/
  getSnapMode/getStepEditMode/getVisible/is* — 17 fns) via MCP
  `fl_ui_screen(module="ui", action=<getter>)`; the write set (enter/yes/no/
  jog/navigateBrowser/…) stays on the controller allowlist but gated. `ui`
  total = 64 fns (enter/escape/yes/no, up/down/left/right, jog/jog2,
  strip/stripJog/stripHold, getFocused*/setFocused, selectWindow/nextWindow,
  navigateBrowser/selectBrowserMenuItem/toggleBrowserNode, openEventEditor,
  showPicker, …); `screen` = 25 fns (menuItemClick/menuNext/menuPrev/
  menuShowing/hideMenu, displayText, fillRect, setup/init/deInit, …) — full
  dump in the EOD-3 handover. `pianoroll` is NOT a module name (`flpianoroll`
  is). **Controller v10.4b-uisafe (built, NOT yet installed; one restart to
  deploy):** `ui.call`/`screen.call` actions, screen quarantined, ui
  safe-read gated. **Deployed state (2026-10-02): v10.4g-peaks is installed (md5 fd0f94a9;
  lastgood = v10.4f-rack md5 0eaa1922 — promote after a stable session; verify md5s
  before any deploy).** v10.4g adds `mixer.getPeaks` (L17; `fl_mixer get_peaks`). v10.4e (built `6b0e09f`, deployed + live-verified 2026-10-01):
  symmetric `useGlobalIndex` on step params + `read_back`/`persisted` on SET
  (S2.3 closed: the old per-channel shift/pan drops WERE the flag asymmetry —
  30/30 persist in both flag domains on all channels), `delete.pattern_data`
  → `patterns.clearPattern(idx)`, L3 batch read payloads, L13 setTimesig
  handler, L14 volume mode/pickup args, L15 file save/saveAs/export handlers.
  Matrix results + v10.4f candidates: `fl-studio-mcp/DEV-TASKS.md` (Sprint L).
- **`patterns.clearPattern(idx)` (v45, 0-based): EXISTS and runs, but does NOT
  clear the channel-rack step grid** (live: 23 grid bits remained after the
  call; the user's rack groove survived it). What it actually clears is
  unknown (candidate: pattern-owned roll notes). Rack-clear = the per-channel
  `channels.setGridBit(c, i, 0, useGlobal)` loop scoped to the target pattern.
- **v45 timesig = `general.setNumerator(n)` / `general.setDenominator(d)`**
  (both call clean; SETTERS ONLY — no getter in general/patterns/midi/transport,
  so read-back is "set, no getter"). `transport.setTimesig` does not exist.
- **v45 has NO importable file API** (general has no save/saveAs/export;
  no flp/file/project modules; ilmcp unimportable). Save/export = OS-level
  `fl_connect save` (AppleScript File>Save).
  **KEY EVENTS ARE PROVEN (the session's headline):** `ui.up` on a focused
  piano roll changed the zoom by 10,051 px; `ui.down` restored it exactly —
  **in-engine key events DO reach the web-rendered piano roll** (the gap
  CGEvents could never cross in the trial era). Consequence: the §0 script
  selection is now key-navigation based — wrench click (one pixel dep) +
  `up`×6 + `enter` (flat 27-item menu: 19 built-ins then 8 scripts; `up` from
  the empty state wraps to the LAST item; 6 ups = **0ComposeWithLLM**).
  **`getHintMsg` is a STALE slot** (returns the last generic hint, not the
  highlighted menu item) — screenshot is the highlight oracle. PE menu row
  pitch ≈ 16–27 px (the old 30 px row model from the trial layout MISSES).
  **v10.4d (deployed, md5 a876a499; lastgood = v10.4c):** `ui.keySeq` action
  (bounded 12-key sequence in one trip, validated before dispatch, stops on
  first fault) — the §0 selection is now one MCP call. Two more proven
  oracles: **`ui.isInPopupMenu`** (1 while any popup menu is open — no
  focus dependency; the wrench probe in `fl_select_script`) and
  **`ui.getFocusedFormCaption`** (the focused form's title, e.g.
  'Piano roll - 808 Kick' / 'Browser' — note the roll is web-docked and
  INVISIBLE to the System Events window list, so OS-side window detection
  cannot see it).
  **Taint note (happened TWICE — v10.1 and v10.4):** the open-time lastgood
  refresh can taint lastgood with a controller that crashes *seconds after
  ready*; the guard only prevents *future* refreshes. After ANY crash, restore
  `device_FLStudioMCP.lastgood.py` manually from git before the next open.
- **Step pitch (pPitch=0) WORKS as a no-UI note writer — with limits** (live 2026-10-01):
  `set_steps` + `set_step_param(param="pPitch", value=<midi>)` on the 808 channel → the
  roll read back exactly 48/51/44/43 at beats 0-3. But step notes have **length 0** (no
  duration control) and **no slides** → good for drums/short stabs, NOT sustained/sliding
  808 lines (use `fl_notes write_steps` or `import_midi`).
- **`general.dumpScoreLog(n, bool)`** (v45): works; **an empty score log pops a modal**
  ("The score log is empty. That means you haven't input any notes yet.") — and modals
  block the controller thread (25 s timeouts, not crashes). The score log records INPUT
  notes only. Dismiss via `fl_connect(action="dismiss_modal")` (focus-war-safe activate →
  key → verify).
- **MCP protocol v2** (2026-09-30): command JSON carries `request_id` + `protocol_version`; the
  response must echo the id (stale replies are never consumed; pre-v2 controllers are tolerated,
  flagged `_legacy_response`). Every dispatched action is appended to `mcp_audit.jsonl`
  (`FL_MCP_AUDIT=0` to disable). The controller half (echo + same-trip read-back) ships with the
  dispatcher refactor (A2 in `fl-studio-mcp/DEV-TASKS.md`) — that controller sync needs one FL restart.

## §6. When stuck, in order

1. `fl_notes(action="read_steps")` / `fl_state` → `noteCount: 0` with a full `mcp_request.json`?
   → ComposeWithLLM not selected (§0).
2. Track sounds right but "gaps"? → `fl_state` (pattern lengths) (§2.2).
3. Tempo feels wrong? → `fl_state` (bpm) vs `fl_transport set_speed` (§2.1).
4. New MCP tool not showing? → `mcp({ connect: "flstudio" })`.
5. Controller action → `Unknown action`? → FL restart (§1).
6. Bridge / MIDI problems → `skills/fl-setup/SKILL.md`.
