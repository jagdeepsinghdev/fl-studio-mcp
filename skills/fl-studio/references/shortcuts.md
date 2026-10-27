# FL keyboard shortcuts via MCP (`fl_shortcut`)

FL's own hotkeys, pressed by the MCP server (macOS System Events keystrokes while FL is
frontmost). The catalog — 226 key-only entries from the manual's shortcut page, Mac-mapped
(Ctrl→cmd, Alt→opt) — is `fl-studio-mcp/shortcuts/catalog.json`; mechanics and the live log are
in `fl-studio-mcp/docs/UI-AUTOMATION.md` §3.6.

## When to use it (and when not)
- **API first.** If an entry has `prefer` (play/stop, save, clone channel, route, rename,
  set_timesig…), call that domain tool: it is verified same-trip and saves a named undo.
- **Shortcuts fill the gaps the API can't reach:** piano-roll edits (quick legato, quick
  quantize, glue, quick chop, octave transpose, duplicate right, nudge), playlist editing
  (duplicate, delete/insert space, mute selection), channel-rack shift-steps, mixer
  link-channels, window layout (F5–F9), snap / step-edit toggles, zoom.
- **Never while the user is typing or using the mouse** — FL is brought to the front and
  the keys go to whatever FL window is focused.

## Find → run (token-cheap)
```
fl_shortcut(action="list")                                  # top 10, production-first
fl_shortcut(action="list", query="legato")                  # word match on id + action
fl_shortcut(action="list", context="piano_roll", offset=10) # next page; limit=0 = all
fl_shortcut(action="run", id="piano_roll.quick_legato", focus=True)
fl_shortcut(action="batch", items=[{"id": "piano_roll.select_all", "focus": True},
                                   "piano_roll.quick_quantize", "piano_roll.deselect"])
```
`priority`: 1 = core beat/song-making speed (listed first), 2 = useful, 3 = rare / dialog /
unreachable. `verified: true` = landed in a live test (oracle or screen diff).

## Guards (each refuses before any key is sent)
1. `reach: no` — **bare or shift-only letters/digits never reach FL** from macOS (live
   2026-10-04: `d`, `y`, `shift+1` did nothing, also with the typing keyboard toggled). So
   tool letters (P/B/D/E…), `L`, `R`, mixer `S`, digits are out. F-keys, named keys
   (PgUp/PgDn, Backspace, arrows, Space) and **cmd/opt combos do land**.
2. `risk: confirm` — dialogs, deletes, renders, open/save-as: needs `confirm=true` (a modal
   blocks the controller thread; prefer the API tool).
3. FL must be frontmost.
4. **Focus proof** — the focused FL window must match the entry's context (S/Cmd+L/Cmd+B
   mean different things per window). `focus=true` brings it there: hide+show the window
   (showing a hidden window is the only thing that reliably moves focus). If the Browser
   holds focus it is hidden and the channel rack is used as a stepping stone (side effect:
   rack visible).
5. **Collisions** — a global key refuses inside a window that redefines it (Cmd+M =
   metronome, but Import MIDI in the roll).
6. **Oracle** — where a ui getter exists (window visibility, snap, step edit) it must change,
   else `success: false`. Other entries return `unverified`: check `fl_state` / a screenshot.

## Edits on notes (verified recipe, 2026-10-04)
Roll edit shortcuts act on the **selection in the OPEN roll** (nothing selected = no change).
```
fl_notes(write_steps, channel_index=N, ...)        # opens + OCR-proves N's roll
fl_shortcut(batch, items=[{"id": "piano_roll.select_all", "focus": True},
                          "piano_roll.quick_legato", "piano_roll.deselect"])
```
- Each roll **edit** re-exports the open roll before and after (an empty ComposeWithLLM
  trigger) and returns `roll.before/after`; it **fails if the notes did not change** and
  **refuses if the script queue holds notes** (the trigger would apply them).
- **A plain `fl_notes(read_steps)` after a shortcut shows the OLD export** (same mtime) — it
  made a working legato look like a no-op. Trust `roll.after`, or re-trigger first.
- Live results: quick legato 4×0.25 → 4×1.0 beat; octave ± 60,62,64,65 ↔ 72,74,76,77.
- Undo = `fl_shortcut(run, id="undo")` (Cmd+Z). Mark the entry's `status` when verified.

## Checklist (mistakes made once — don't repeat)
1. **FL must be in front for every key AND for roll writes.** Raw `osascript keystroke` /
   `cliclick` without activating FL typed into iTerm; a covering terminal made the roll-title
   OCR see nothing (writer refused). Always go through `fl_shortcut` (it activates + checks).
2. **Never send keys outside `fl_shortcut`** — it is the only path with the focus proof.
3. **Test on a throwaway channel** (`fl_channel add` → test → `fl_delete channel` by name),
   never on the user's channels. Afterwards restore: `fl_state` (stopped? same selected
   channel? same channel count?), window layout (`ui.getVisible` 0-4), the roll's tool.
4. **Check `fl_state` after any test run** — a stray click/key once started playback
   (stop with `fl_transport(stop)`).
5. **Browser keys make focus readings stick on "Browser"** — `focus=true` escapes it (rack
   stepping stone); without it every later context check refuses.
6. **Toggles in pairs** (snap, step edit, wave view, F-key windows) so state ends where it
   started; F11 song info does not toggle closed.
7. Window F-keys on a visible-but-unfocused window FOCUS it instead of hiding it.
