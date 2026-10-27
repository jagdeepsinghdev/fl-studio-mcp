# How the MCP server drives FL Studio's UI

Audience: a developer new to this repo who must understand, run, debug and extend the
UI automation. Read `CLAUDE.md` (repo root) first - it holds the hard rules. This file
explains the *mechanics*; skills (`skills/fl-melody`, `skills/fl-setup`) say *what to call*.
Paths below are relative to `fl-studio-mcp/` unless they start with `skills/`.

**Golden rule: never trust a success message.** FL's API and our tools happily report
success while nothing happened (step params on empty steps, `channels.selectOne` not
moving an open roll, a menu click that hit the background). Every step below has an
*oracle* (section 2) that proves it.

## 1. The five control layers (prefer the lowest number that can do the job)

| # | Layer | Used for | Code |
|---|---|---|---|
| 1 | **FL Python API via our MIDI controller** | everything the API exposes: transport, mixer, channels, patterns, step params, state reads | `fl_controller/device_FLStudioMCP.py` (runs inside FL); server side `src/fl_studio_mcp/utils/midi_connection.py` |
| 2 | **In-engine key events** (`ui.keySeq`) | arrows/enter inside FL's web-rendered piano roll (script menu) | controller action `ui.keySeq`; caller `tools/select_script.py::_send_keyseq` |
| 3 | **Native macOS menus/dialogs** (System Events / Accessibility, via `osascript`) | View > Piano roll toggle, Add > `<instrument>`, File menu, native Open panel | `utils/roll_session.py::_toggle_roll`, `utils/add_channel.py::_click_add_menu_item`, `tools/select_script.py::_open_roll_via_menu` |
| 4 | **Pixel clicks** (`cliclick`) | ONLY FL's self-drawn UI: the wrench, the roll's menu arrow and its menu rows | `tools/select_script.py::_click` / `_move` (`FL_CLICLICK`, default `/opt/homebrew/bin/cliclick`); `utils/import_midi.py::_dclick` |
| 5 | **Vision OCR** (read-only) | reading the roll title FL draws on screen, and **locating click targets by their text** (`--boxes`) | `scripts/ocr_text.swift` -> `.generated/bin/ocr_text`; `utils/roll_session.py::screen_roll_title`, `utils/import_midi.py::ocr_boxes` / `find` |

**Layer 1 mechanics.** `MIDIConnection.send_command(action, params)` writes
`mcp_command.json` (with a fresh `request_id` and protocol version) into
`~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`, sends a MIDI trigger to
the CoreMIDI port `FL Studio MCP`, and polls `mcp_response.json` for the reply echoing that
`request_id` (stale replies are never consumed). One command/response file pair means
**never fire two flstudio tool calls in parallel**. Every action is appended to
`mcp_audit.jsonl` (`_audit`; `FL_MCP_AUDIT=0` disables). `Unknown action` = the installed
controller is older than the server: sync the file and restart FL (CLAUDE.md section 1).

**Layer 2 mechanics.** Key events are dispatched *inside* FL, so they reach the web-rendered
roll (proven: `ui.up` changed the roll zoom). But **keys go to the FOCUSED form** - if the
FL Cloud browser panel has focus the keys silently miss (see CLAUDE.md "keySeq focus rule").
macOS-level keystrokes (CGEvent, pynput, System Events `keystroke`) do NOT reach FL's
custom-drawn UI (text fields, toolbar, script dropdown); native AppKit surfaces (menus,
file panels, confirm dialogs) DO accept them. The exception: **FL's own hotkey table** - the
script trigger Cmd+Opt+Y (`utils/fl_trigger.py::_trigger_macos`) and, since 2026-10-04, the
manual's shortcuts via `fl_shortcut` (F-keys, named keys, cmd/opt combos land; bare letters and
digits never do) - section 3.6. All need FL frontmost.

**Layer 5 mechanics.** `_ocr_bin()` compiles the Swift helper once (`swiftc -O`) when the
binary is missing or older than the source; if it cannot build, callers get `None` and
must refuse. `screen_roll_title()` runs `screencapture -x`, OCRs the PNG, and matches
`Piano roll - <name>` with `_TITLE_RE`. `.generated/` is git-ignored.

## 2. Oracles - how each step is verified

| Oracle | Proves | Caveat |
|---|---|---|
| `ui.call isInPopupMenu` (`select_script._menu_open`) | a popup menu is open (so a wrench/arrow click really hit the toolbar, and the roll is open) | no focus dependency, but says nothing about *which* form gets the keys |
| `ui.getFocusedFormCaption` | which form has focus | the docked roll's caption is just `Piano roll -` (**no channel name**), so it can NOT identify the channel; a plugin window also fools focus proofs |
| `piano_roll_state.json` mtime (`roll_session.state_mtime` / `ran_since`) | the ComposeWithLLM script ran (it rewrites the file on every run, including at selection time) | stale mtime = selection did not take / trigger not consumed |
| Screen title via OCR (`screen_roll_title`) | which channel the roll is actually showing | FL redraws the title ~1 s late: settle before reading (`settle=1.5`) |
| Same-trip `state_after` read-back from the controller | the value really changed in FL | only for actions that implement it; check `_undo_missing` / read-back fields in results |

## 3. Automated flows (step by step, with failure behaviour)

### 3.1 ComposeWithLLM script selection (CLAUDE.md section 0) - automatic

FL forgets the selected roll script on every launch; nothing persists it. The selection is
per FL *process*, not per channel (verified: after one selection a different channel's roll
ran the script).

1. Every note write ends in `FLStudioTrigger.trigger()` (`utils/fl_trigger.py`), which calls
   `roll_session.ensure_script_selected()`.
2. If the pid in `Piano roll scripts/.mcp_script_session.json` equals `pgrep -x OsxFL`,
   do nothing. Otherwise stash `mcp_request.json` to `[]` (selection runs the script once;
   queued notes would otherwise apply twice), run `select_script.fl_select_script()`,
   `sleep 1`, check `ran_since(before)`, record the pid, restore the queue.
3. `fl_select_script` internals: select channel -> `_ensure_roll_open` -> locate wrench
   (pixel search, window-relative fallback) -> `_open_wrench_menu` (click, then
   `isInPopupMenu`; if no menu the roll was closed: View menu toggle, click again) ->
   **only if the menu is confirmed open**, `ui.keySeq(["up"]*6 + ["enter"])` (flat 27-item
   menu, `up` from empty wraps to the last item; 6 = `0ComposeWithLLM`) -> park the mouse.
4. Self-heal: if the trigger ran but the state mtime did not move, force one re-selection
   and trigger again. Failure is loud: `ok: False` plus `invalidate()` (deletes the session
   file so the next write retries).
5. `FL_AUTO_SELECT_SCRIPT=0` disables it; it is also off under pytest unless the env var
   is `1`. Manual: `fl_select_script(channel_index=N)`; `open_only=True` leaves the menu
   open for manual key driving (Escape closes it unchanged).

Refusals: no keys when the menu probe says closed; the tool never guesses.

### 3.2 Retargeting the roll to a channel (`open_roll_for_channel`)

Writers with `channel_index` (`fl_notes` in `tools/notes_v2.py`, presets in
`tools/preset_v2.py`, `tools/song_builder.py`) call it before writing.

*Why `channels.selectOne` is not enough:* it selects the channel in the rack but an
already-open roll stays on the old channel (seen: roll stayed on "Acoustic Piano"). Closing
and re-opening the roll via the native **View > Piano roll** toggle re-opens it on the
selected channel. The toggle also *focuses an unfocused roll first*, so one toggle may
only focus it; hence a loop, not a single click.

Steps: look up the channel name (`channels.getAll`) -> `channels.selectOne` -> refuse if
the OCR helper cannot build -> activate FL -> up to `max_toggles` (5) times: wait `settle`,
OCR the title, compare normalised to the channel name (`_norm` strips the drawn arrow),
return `{"ok": True, "proof": "screen title"}` on match, else toggle the View menu.
No match -> `{"ok": False, "titles_seen": [...]}` and the caller **refuses to write**
(CLAUDE.md rule 6b).

**2026-10-01 incident (why OCR):** the first proof was focus-based
(`getFocusedFormCaption`). Add > 3x Osc opened a plugin editor window; the focus check
"passed" while the roll still showed the 808 channel, and the written keys went into the
808. Fix commit `28aa106`: ground truth is the title FL actually draws. See DEV-TASKS
Sprint L, L-b.

### 3.3 Adding a channel (`utils/add_channel.py`, `fl_channel action=add`)

The API has no channel creator. `add_instrument(name)` snapshots `channels.getAll`, clicks
`Add > <name>` through System Events, then polls up to ~5 s for the channel count to grow;
`setup_instrument` additionally routes to the next free mixer track, renames and selects.
Failure: `osascript` error/timeout ("is a dialog open?"), or "clicked ... but no channel
appeared". Needs Accessibility. Some instruments open a plugin editor window that steals
focus - re-prove the roll before any later write.

### 3.4 Import MIDI into an existing channel (C3) - `fl_notes(action="import_midi")`

Proven live 2026-10-01 (4/4, 2/2 and 3/3 notes exact). One call:

```
fl_notes(action="import_midi", channel_index=5, target_pattern=6,
         notes=[{"midi": 67, "time": 0, "duration": 0.5, "velocity": 0.9}, ...])
# or path="<a .mid inside fl-studio-mcp/>" instead of notes; optional bpm
```

**Import REPLACES** that channel's notes in the target pattern (live: 4 notes ->
exactly the 2 imported). No ComposeWithLLM queue is used for the write. ~15 s, so
prefer `write_steps` for small edits. Code: `tools/notes_v2.py::_import_midi` (tool
side: pattern select/restore, read-back) + `utils/import_midi.py` (the UI steps):

1. `write_midi()` -> `.generated/midi/<name>.mid` (mido; velocity 0-1 -> 1-127).
2. `open_roll_for_channel()` (3.2) - import goes into the roll's current channel.
3. `ocr_boxes()` (Vision with `--boxes`, converted to screen points incl. Retina
   scale) finds the roll title; the **menu arrow is clicked at title.x - 329**
   (`TITLE_TO_ARROW_DX`, PE layout). Accepted only if `isInPopupMenu` = 1 **and** OCR
   sees "Target channel" (= the roll menu, not the wrench menu); else Escape + refuse.
4. OCR finds **File** (nearest to the arrow) -> hover; OCR finds **Import MIDI file**
   -> slide right along the File row, then click (moving diagonally closes submenus).
5. Wait for the native window "Open" (System Events). Cmd+Shift+G opens the go-to
   sheet; **set the path by accessibility** and read it back. Then **double-click the
   LAST row** of the sheet's suggestion table (row 1 is the "Go to:" header; a single
   click did nothing) -> the sheet closes with the file selected -> click the OCR'd
   **Open** button next to "Cancel". Any failure: Esc closes the panel, refuse.
6. Read-back: reopen the roll (proven), run the script on an empty queue, require a
   **fresh** state file (`ran_since`) and `note_count == notes in the .mid` ->
   `verified: true`. The previously active pattern is restored.

Leads not yet built: the roll menu's **Paste from MIDI clipboard** (no file dialog).

### 3.5 Mouse-free routines - `fl_ui_script` (controller v10.4i, built 2026-10-03, NOT live-tested)

Why: FL's Python API has **no plugin-loading call** (`mixer` 75 fns / `plugins` 13 fns probed
live 2026-10-03; the il-group API stubs agree), so `fl_mixer add_fx` clicks. The `ui` module can
still drive FL from inside the engine (key events, focus, browser, the **undocumented**
`ui.showPicker` - present live, absent from the stubs, signature unknown).

- **Controller `ui.steps`**: up to 16 allowlisted calls in one trip (ui getters/keys/navigation,
  mixer track selection, plugin-slot getters), validated before dispatch, stops at the first
  exception (FL's TypeError text = the signature oracle). Only a NEW FUNCTION on that allowlist
  needs an FL restart.
- **MCP `fl_ui_script`**: sequencing - vars, `wait`, `read`, `expect` (retrying oracle), `on_fail`
  cleanup (default `ui.escape`). Routines are JSON in `fl-studio-mcp/ui_routines/` - edit or add one
  and call again, no restart. Guard: key events (enter/up/down/...) are refused until an `expect`
  has passed in the same run (the section 0 focus rule); `escape` is always allowed.
- Routines: `select-mixer-track` (untested), `probe-show-picker` (EXPERIMENT: learns what
  `showPicker(args)` opens; reads focus/popup state, escapes, never sends enter). An `add-fx`
  routine gets written only after the probe shows a picker that keys can drive.
- **Live results (v10.4i deployed 2026-10-03, FL behind the terminal):** `ui.steps` works.
  `showPicker()` -> `TypeError: takes at least 1 argument`; `showPicker(1)`, `(1, 0)`, `(1, 1)`
  run clean but **nothing visible opens** (window capture `screencapture -l<FL window id>`,
  `isInPopupMenu` 0, focus unchanged). Not yet tried: FL frontmost, other arg values.
  Proven useful: `mixer.setTrackNumber(7)` selects Insert 7 and focuses it
  ("Mixer - Insert 7"); `ui.showWindow(0)` opens the mixer. **`ui.escape` closes the
  focused window** (it closed the mixer) - so the default `on_fail` escape can hide a panel.

### 3.6 FL's own keyboard shortcuts - `fl_shortcut` (live-verified 2026-10-04, no controller change)

FL's hotkey table DOES receive macOS keystrokes (System Events `keystroke` / `key code`) while FL
is frontmost - the same path the Cmd+Opt+Y trigger has always used. What keystrokes can't reach
is FL's custom-drawn *text fields* (so F2-rename is useless). The manual's shortcut page
(`basics_shortcuts.htm`) is data in `shortcuts/catalog.json`: 226 key-only entries, Mac-mapped
(Ctrl->cmd, Alt->opt), each with a `context`, a `risk` and, where one exists, a `prefer` API tool.

Guards, in order (each refuses without sending a key): risk (`confirm` tier = dialogs, deletes,
renders - a modal blocks the controller - needs `confirm=true`) -> FL frontmost -> the focused
form caption matches the context (`focus=true` runs `ui.showWindow`+`ui.setFocused` first) ->
global keys refuse inside a window where they mean something else (`not_in`; Cmd+M = metronome
but Import MIDI in the roll) -> optional oracle (`verify.changes`: a ui getter must read
differently afterwards).

Live 2026-10-04 (PE 26.1.6): F5/F6/F7/F9 (`ui.getVisible`), Backspace snap (`getSnapMode` 0<->3),
Cmd+E step edit (`getStepEditMode`) all landed, each toggled back. F5-F9 on a visible but
*unfocused* window focus it instead of hiding it (`verify.or_focused`). Focus path, collision
and confirm refusals all verified.

Second session (same day, screen-diff oracle, every pair reversed exactly):
- **Bare / shift-only letters and digits never land** (`d`, `y`, `shift+1`; also with Cmd+T
  typing-keyboard toggled). F-keys, named keys (PgUp/PgDn zoom, Backspace, arrows) and
  cmd/opt combos (`opt+w` wave view) do. 61 entries carry `reach: no` and are refused.
- **Focus:** `ui.setFocused` and `ui.showWindow` on a *visible* window don't move focus, nor
  did a View-menu toggle or a title-bar click; **hide+show** always does. After a Browser key,
  focus sticks on the Browser (`getFocused(4)` = 1 even while hidden; keys went to the rack):
  only hide Browser -> hide+show **channel rack** -> hide+show target escapes it (3/3, then
  8/8 in one `batch`).
- F11 (song info) opens Project settings and a second F11 does not close it.
- `list` returns 10 entries by default, production-first (`priority` 1-3), unreachable hidden;
  `batch` runs up to 30 ids in one call through the same guards.
- Note edits (throwaway FLEX channel, deleted after): select all + quick legato turned 4x0.25
  into 4x1.0 beats; octave up/down 60.. <-> 72.. . Roll edit shortcuts now re-export the roll
  before+after (empty ComposeWithLLM trigger, refused if the queue holds notes) and fail on no
  change - `read_steps` alone returns the pre-shortcut export.
Most entries are still `untested` - mark `status` after a live run. Prefer the API tool whenever an entry has `prefer`; shortcuts are for the gaps
(roll tools: glue/legato/chop/quantize/transpose, playlist zoom/tools, window layout).

### 3.7 The UI guard - `utils/ui_guard.py` (built + live-diagnosed 2026-10-05)

Every screen-driving helper (`add_effect`, `remove_effect`, `plugin_preset_ui`) starts with
`ensure_ready(conn, need_front=...)`; `fl_vocal apply/buses/run` retry once through
`recover` when FL answers "Operation unsafe" or times out. One-call checks for humans/agents:
`fl_connect(action="doctor")` (read-only) and `fl_connect(action="recover")`.

| Rule (each from a live failure on 2026-10-05) | Enforced by |
|---|---|
| A leftover **plugin picker** makes FL refuse every `probe.exec` ("Operation unsafe") | `close_picker()` in a `finally`; `diagnose` lists it; `recover` closes it |
| An FL **"Error" dialog** ("no empty effect slot ...") blocks the same way | `diagnose` reads FL's OS window titles; `recover` sends Enter (FL frontmost only) |
| **Escape does NOT close FL's preset menu**; a leftover menu overlapped the editor title row and the next OCR clicked a menu item | `close_popups()` = `ui.closeActivePopupMenu` until `ui.isInPopupMenu() == 0` |
| **Add > Effect inserts into the PANEL's track**; with a plugin editor focused, `setTrackNumber` did not move the panel (Reeverb 2 landed on 12, not 16) | `select_track`: hide+show+focus the mixer, then require focused form `Mixer - ...` |
| **Picker Return does not confirm** on PE 26.1.6; a second double-click on the re-verified row does | `pick_from_picker` |
| **OCR drops spaces / lone letters** ("Fruity Parametric EQ2", preset "a") | `_key()` alnum match; `zoom_ocr` / `zoom_row` (3x, ~8 px padding) |
| **API preset stepping is ASYNC**: 176 next + 176 prev on Patcher queued ~350 patch loads, main thread 100 % in `Patcher_x64.dylib` for minutes | `find_preset` waits per step, `BUDGET`, `HEAVY_PRESETS` refuse; menu route via `preset_ui` |
| **The owner switches apps mid-run** - blind clicks would land in their terminal | `require_fl_front` waits; brings FL forward only after ~3 s user idle (`HIDIdleTime`) |
| A **success message without read-back** (Limiter knee "ok" but unchanged) | `apply` value writes re-read, retry in-engine once, else a `write` miss |
| FL idles at ~120 % CPU with heavy plugins loaded: CPU alone is not "busy" | `diagnose` calls it busy only together with a controller timeout |
| **After an FL restart the mixer opened COLLAPSED** (toolbar strip only, no insert panel) | `add_effect.ensure_mixer_panel`: hover the toolbar row until FL's hint says "Maximize / Restore", click, re-check |
| `ui.hideWindow(widMixer)` hides it for real but `ui.showWindow` did NOT redraw it; `ui.getVisible` said 1 while nothing was drawn | never hide the mixer; the oracle is the on-screen panel title `Mixer - <track>`; only View > Mixer shows it |
| Track renamed ("Vocal") broke the delete's `Insert N` title match; OCR read "Hall Reverh" | match by the API track name + `names_match` (>= 90 %, digits must agree: "Insert 1" != "Insert 10") |
| **The picker opened 975 px tall, ignored resizing, its Find field sat under the Dock** -> rows past the first screen unreachable | `utils/picker_index.py`: select BY INDEX with in-engine `ui.down` (N downs = row N), verify the blue highlighted row before `ui.enter` (in-engine Enter confirms; System Events Return never did) |
| The picker list order is NOT FL's plugin-database folders (79 / 228 files vs 114 rows) | order read from the picker itself, cached in `.generated/picker_order.json`; rebuilt when a name is missing |
| `ui.down` WRAPS from the last row to the first; OCR misreads re-read rows ("E02", "truity ... EU2") | `wrapped()` stops the scan; `merge()` skips only the page OVERLAP (>= 80 % rows); Q/0 folded in `_pk` |
| **A maximised plugin editor** put the preset name at the far right; the window buttons were read as the label | `preset_label` skips glyph boxes and the last 70 px; `zoom_row` scans the full row |
| A lone grey preset name ("a") is unreadable even 6x zoomed + inverted | **knob fingerprint**: `record_fingerprint` once (confirmed on screen), then verify by FL's own param values (`matches_fingerprint`) |
| With another app in front, screen checks read THAT app (a View > Mixer toggle fired blind) | `select_track` / `ensure_mixer_panel` return False unless FL is frontmost |
| **Tools left 3-4 plugin editor windows open** (`mixer.focusEditor` opens, nothing closed) | `close_editor` (focusEditor + in-engine `ui.escape`) in a `finally` of every editor-opening tool; `fl_connect("tidy")` closes all (25 plugins, 0 titles left, live) |
| A preset menu OCR'd before FL finished drawing it (Patcher, inside a long setup run) | re-read the menu once after a settle; `apply` retries a missed preset / insert once |
| **Add > Effect inserts into the SELECTED slot**, not the first free one (Pitcher landed in slot 10) | `apply` proves the recipe ORDER (`what: "order"` miss); a fresh FL session has no slot selected |
| `focusEditor` on an EMPTY slot raises "Index out of range"; clicking an empty slot opens the full-screen visual plugin browser | no API to select an empty slot; do not rely on that browser |
| **Escape (in-engine `ui.escape` or a key) closes the MIXER window** when it has focus | never Escape out of mixer-adjacent overlays; close menus with `ui.closeActivePopupMenu` |
| `ui.isInPopupMenu` DOES report plugin preset menus (= 1 when open) | `_open_preset_menu` uses it as the opened-proof before any keys |
| **Importing AppKit (`NSScreen`) turned our Python into a GUI app** (Dock rocket "Python") that stole FL's focus | screen size via CoreGraphics `CGDisplayBounds`, Dock edge via System Events; never AppKit in-process |
| Dense 4-column preset menu (Patcher): Vision dropped lines; tall zoom strips skip lines; "LITE" fragments made a fake column | column = >= 5 rows at one x; zoom each column in ~150 px overlapping tiles; wait for the menu to stop changing (`settled_shot`) |
| 1-letter preset ("a") unreadable even zoomed; menu re-open shifts rows | **knob snapshot via API** (`restore_fingerprint`): 59 knobs in one trip, read-back proof |
| Owner deleted all inserts -> nothing free for setup | `fl_mixer add_tracks` ("+" next to "Wide", hint-confirmed, `trackCount` proof); `setup` calls it |
| **Wrong plugin order is fixable**: a mixer SLOT's own menu (row arrow, hint "FX slot N options") has **Move up / Move down** | `plugin_options.move_slot` (read-back proves the swap, ~10 s/move); `apply` auto-`reorder`s when the order proof fails (**live 2026-10-06: Pitcher scrambled to slot 1 -> one MCP apply moved it back, 0 misses**) |
| A plugin editor's "Plugin options" menu is the ▸ arrow ~26 px left of the title (hint "Plugin options"); the gear between is "Detailed settings" (a toggle, NOT a menu) | `plugin_options.read_menu`: hint-confirmed arrow, column-zoom read, ALWAYS closes menu + editor (`finally`) |
| Exploration scripts that crashed mid-way left a menu open (blocks FL) | every UI helper closes what it opened in `finally`; `fl_connect("recover")` if in doubt |
| **A live test played notes on the owner's channel 1 (808 Kick)** via `channels.midiNoteOn(0, ...)`; `capture` then dumped C-E-G onto the Kick (the owner heard an extra kick) | live tests that create notes/audio use a dedicated SCRATCH channel and remove what they made; never `midiNoteOn` / write notes on a channel the owner did not name |
| `general.dumpScoreLog(t, 1)`: "silent" does NOT stop the empty-log Warning; the Warning may have no OS window | `fl_notes capture`: a dump timeout = the Warning -> proven `dismiss_modal`; success only with +1 undo step |
| Edison's API exposes only Play/pause, Record, Live selection (3 params) | its record mode ("On input") and loop length need Edison's own UI |

Diagnosing a hang without touching FL: `mcp_audit.jsonl` (last actions + counts) and
`sample $(pgrep -x OsxFL) 3` (which library holds the main thread; mostly `mach_msg` = idle).

## 4. Gotchas

- Native dialogs: typed keystrokes **drop digits** -> set text fields via accessibility;
  Return and a single click do not confirm the Go-to sheet -> double-click the LAST
  suggestion row, then press Open (3.4).
- Prefer locating FL's self-drawn targets **by OCR text** (`import_midi.find`) over fixed
  pixel offsets; keep any remaining offset relative to an OCR'd anchor.
- View > Piano roll is a **toggle** that first focuses an unfocused roll; never toggle
  blindly - detect (menu probe / OCR title) first.
- Plugin editor windows steal focus (breaks focus-based proofs and keySeq targets).
- Another web panel (FL Cloud browser) holding focus makes keySeq miss while the menu
  probe still says "open".
- **`screen.*` is quarantined**: `screen.menuShowing()` crashed FL (EAccessViolation).
  `ui.*` only via the gated allowlist (`fl_ui_screen`).
- **Never two flstudio MCP calls in parallel** (single command/response pair).
- Modal dialogs freeze the controller (timeouts, not crashes); dismiss with
  `fl_connect(action="dismiss_modal")`.
- Layout-dependent pixels (wrench x, menu arrow) shift with FL layout/display scale;
  `select_script.py` derives them from the live window frame and accepts `wrench_x`.
- Permissions for the process that runs the server (usually the terminal): **Accessibility**
  (System Events, cliclick), **Screen Recording** (`screencapture` for OCR; without it the
  capture is blank and OCR finds no title -> a false refusal), `swiftc` (Xcode CLT) to build
  the OCR helper, and `cliclick` installed (`brew install cliclick`).
- FL is often running the owner's project: check state before assuming anything.

## 5. Checklist: adding a new UI automation

0. Start with `ui_guard.ensure_ready(conn, need_front=True)`; close anything you open in a
   `finally`; never send a key/click without `cm.require_fl_front()` right before it.

1. **Pick the lowest layer**: API (1) > in-engine keys (2) > native AX (3) > pixel clicks (4).
   Pixels only for self-drawn widgets with no AX tree.
2. **Probe-gate**: verify the precondition before keys/clicks (menu open? roll showing the
   right channel? focus where expected?). Send nothing if the probe fails.
3. **Verify after** with an oracle (section 2), never the tool's own success flag.
4. **Refuse rather than guess**: unproven -> `{"success": False, "error": ...}`; never write
   "best effort". Every pixel click is followed by an oracle check.
5. **Tests never touch live FL.** `tests/conftest.py` has an autouse fixture
   `_isolate_from_live_fl`: temp piano-roll-scripts dir, temp controller dir, no real MIDI
   port (`MIDIConnection.connect` fails on purpose), no-op trigger keystroke. (Born from the
   2026-10-01 incident where a test wrote a real note into the user's open roll on each
   run.) Mock the UI layer (`subprocess.run`, `_click`, `screen_roll_title`, `_menu_open`);
   tests that need a connection inject a fake `_port`.
6. **Controller action involved?** Add its entry to `tests/test_controller_key_drift.py`
   (it cross-checks that each tool sends only keys the controller handler reads - an unread
   key never raises, the handler just uses its default).
7. Same change: tool docstring + `fl_help` (`src/fl_studio_mcp/tools/help_v2.py`) + owning
   skill (`skills/README.md` rules) + this doc + `DEV-TASKS.md`.
8. Tools added/removed -> `uv run python scripts/gen-inventory.py` (never hand-edit
   `INVENTORY.md`).

## 6. Debugging recipe

Hands-on screen/mouse work (OCR-anchored clicks, custom menus, the stuck-mouse
fix) has its own playbook and CLI: [`SCREEN-CONTROL.md`](SCREEN-CONTROL.md) ·
`scripts/screen.py`.


- **Audit log:** `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/mcp_audit.jsonl`
  (one line per dispatched action: what was sent, what came back).
- **Runtime files:** `.../Hardware/FLStudioMCP/mcp_command.json` / `mcp_response.json`;
  `.../Settings/Piano roll scripts/`: `mcp_request.json` (note queue - must be `[]` when
  idle; clear with the `fl_clear_request_queue` tool), `piano_roll_state.json` (script output;
  `noteCount`, mtime = ran-oracle), `.mcp_script_session.json` (pid of the last selection;
  delete to force re-selection).
- **See what OCR sees (read-only, does not touch FL, but the user's screen is captured):**
  ```
  screencapture -x /tmp/s.png && fl-studio-mcp/.generated/bin/ocr_text /tmp/s.png | grep -i "piano roll"
  ```
  Build the helper by hand: `swiftc -O scripts/ocr_text.swift -o .generated/bin/ocr_text`.
  Empty output usually = Screen Recording not granted.
- **Roll write went to the wrong channel?** Check OCR title, then `fl_state`, then the
  audit log for the `channels.selectOne` that preceded it.
- **`note_count: 0` after a write:** script not selected/ran - delete
  `.mcp_script_session.json`, retry; compare the state-file mtime.
- **Crash discipline:** after ANY FL crash, restore
  `device_FLStudioMCP.lastgood.py` (it lives in the installed `.../Hardware/FLStudioMCP/`
  dir, not in git) from the committed `fl_controller/device_FLStudioMCP.py` before the next open - the
  open-time lastgood refresh has tainted it with a crashing controller twice (CLAUDE.md
  section 5). Crash logs: `~/Documents/Image-Line/FL Studio/Support/Logs/Crash/`.
- Controller edits need sync + FL restart; MCP-side edits only need the MCP server
  reloaded: `/mcp` -> reconnect `flstudio` in Claude Code (`mcp({connect:"flstudio"})` in pi).
