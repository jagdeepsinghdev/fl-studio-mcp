# Piano-roll setup (ComposeWithLLM selection - automatic)

FL resets the active piano-roll **script** on every launch and nothing persists it. The
server now handles this itself: the first note write in each FL process selects
**0ComposeWithLLM** (the old `ComposeWithLLM` name is an alias), then remembers the FL pid
(`Piano roll scripts/.mcp_script_session.json`). You do not need a manual step.

Mechanics, oracles and failure behaviour live in one place:
**`fl-studio-mcp/docs/UI-AUTOMATION.md`** (sections 3.1 selection, 3.2 roll retarget).
This page is only the "what do I call" summary.

## What you call

- **Normal path:** `fl_notes(action="write_steps", channel_index=<target>, ...)` (or
  `fl_preset(action="load_melody", channel_index=...)`). The server retargets the roll to
  that channel, **proves it by reading the roll title drawn on screen (Vision OCR)**,
  selects the script if this FL process has not had it selected, then writes. If it cannot
  prove the roll shows the target channel it **refuses** and writes nothing
  (CLAUDE.md rule 6b). No `open_roll_verified` attestation needed with `channel_index`.
- **Explicit / recovery:** `fl_select_script(channel_index=<target>)`. Params that matter:
  `method="keys"` (default; wrench click + one `ui.keySeq` of up x6 + enter),
  `up_steps` (6 = 0ComposeWithLLM in the 27-item menu; re-count if scripts are added or
  removed), `open_only` (open the menu and stop, for manual key driving),
  `wrench_x` (pixel override if the toolbar layout shifted). `method="click"` is a
  trial-era last resort that misses on the PE layout.
- **Disable the automatic selection:** `FL_AUTO_SELECT_SCRIPT=0` (it is also off under
  pytest, so tests never click a live FL).

## Verify

- `piano_roll_state.json` mtime moves on every script run (selection included);
  `fl_state` / `fl_notes("read_steps")` show `note_count` (0 on an empty new channel).
- After a write, `note_count` must change. `note_count: 0` after a write = the script did
  not run: delete `.mcp_script_session.json` (forces re-selection) or call
  `fl_select_script`, then retry. The queue file persists until consumed, so retries are
  safe. To abandon a stuck write (no clear-queue action in the default tools): back up
  `mcp_request.json` (same folder) and write `[]` to it — **before** any roll changes, or the
  queued notes land on whichever roll opens next (CLAUDE.md §6b).

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| write refused, "could not confirm the roll shows ..." | OCR title did not match after 5 toggles (plugin window in front, roll closed, Screen Recording missing) | close plugin editors, grant Screen Recording (see `skills/fl-setup`), retry |
| write refused, "OCR helper failed to build" | `swiftc` missing | install Xcode command line tools |
| "the wrench did not open the script menu" | roll closed / wrench mislocated | tool sent NO keys; pass `wrench_x`, check a screenshot |
| menu "open" but selection did not take | another form (e.g. FL Cloud browser) holds focus; keys go to the focused form | View > Piano roll toggle re-focuses the roll; retry |
| trigger sent, state file stale | trigger hotkey (Cmd+Opt+Y) only lands when FL is frontmost | the server self-heals once; else bring FL to front and retry |

Accessibility (System Events, cliclick, trigger keystroke) and Screen Recording (OCR)
permissions are documented once in `skills/fl-setup/SKILL.md`.

## Legacy

Opening the roll by hand: `View > Piano roll` is a **toggle** (process name `OsxFL`); never
click it blind - it can close an open roll. Selecting the script by hand: roll toolbar
wrench -> Scripts -> 0ComposeWithLLM.
