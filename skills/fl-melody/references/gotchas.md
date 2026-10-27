# Piano-roll gotchas & caveats

## Notes & gotchas

- **⚠️ Verify the target channel before writing.** A channel select can report
  success while FL keeps another channel selected (seen 2026-09-29: notes went into
  the 808 instead of "Guitar", twice). Check `fl_state` → only the target has
  `is_selected: true`, then write. `fl_notes("clear")` clears whichever roll is open,
  so clear *before* switching. See `fl-genres` (`references/trap.md`) → "Drill/trap with
  guitar" for the full log. **This is why `fl_notes("write_steps")` requires
  `open_roll_verified=True`.**
- **⚠️ Set the pattern length FIRST, before writing any notes**
  (`fl_pattern("set_len", pattern, beats)`), then `fl_notes("write_steps")`. The piano
  roll only plays notes inside the pattern length — notes written past it never sound,
  and if you change the length *after* writing, the phrase and the drum loop drift out of
  phase. If you already wrote notes into a wrong-length pattern: `fl_notes("clear")`,
  set the length, rewrite. The full sync rules live in **`fl-studio-mcp/presets/README.md`
  → "The one golden rule — phrase length must match"** (pattern length, drum loop, and
  every phrase must share the same total phrase length; drums repeat per bar, phrases span
  the whole phrase; last note `time + duration ≤ L`).
- **Pattern length gotcha:** a new FL pattern defaults to **16 beats** (or 16 beats *again*
  after an FL restart clears a fresh project). If your melody is one bar (4 beats / 16
  steps), call `fl_pattern("set_len", pattern=1, beats=4)` first so it loops without
  trailing silence. Verify with `fl_state` (it reports each pattern's length).
- **MCP 2-second timeouts are common** on this MIDI bridge — a timeout is not a failure.
  Re-issue the same call, then verify with the readback below. Never assume a timed-out
  call did (or did not) land. (Seen repeatedly with the step-sequencer legacy tools; the
  *set* usually lands even when the read times out.)
- **Tempo:** `fl_transport("set_bpm", bpm=…)` sets the real project tempo (the toolbar box
  updates). FL's default base is 130 BPM.
- **Bar overflow:** don't let the last note run past step 15 of a 16-step bar — notes that
  start at step 15 with a length of 2 will clip at the loop point and glitch. Keep the
  final note within the bar.

- **Never clear a melodic channel with `fl_channel("set_steps")`.** Piano-roll notes that sit on the grid
  show as steps, and an all-false step row DELETES them (the guitar was wiped twice, 2026-10-11).
- **`fl_notes("clear")` takes `target_pattern`** (it used to ignore it and empty the ACTIVE pattern); the
  reply now names `cleared_pattern`. Check it.
- **A refusal "could not confirm the roll shows '<name>'"** with titles like `Bass r` / `Keys y`: OCR read
  the title-bar icon as a stray letter. Names followed by 1-2 stray characters are accepted now (docked
  and floating titles); needs an MCP reconnect (`/mcp`) after updating the server.
- **`read_steps` can return a stale export** (`age_seconds` large, same `state_file_mtime` as before):
  a write re-exports the roll, so write (or `fl_select_script`) then read. One channel per write call.
- **Write refused with BLANK titles (`['', '', ...]`) or a mixer insert's name (`['Flute Half', ...]`):** the roll is not readable.
  A maximized mixer/browser hides it (hide them: the mixer shortcut F9 toggles, so check `ui.getVisible`), and a
  floating roll can sit mostly off-screen to the right so its title is cut. Fix: View > Arrange windows > Realign,
  then drag the roll by its **title text** ("Piano roll - <name>", not a toolbar icon: dragging an icon selects a
  tool) back onto the screen. The title must show the channel name before any write.
- A write replaces only that channel's notes in that pattern (`mode="replace"`), so a whole song's
  melodic part can be written once, with absolute beats.

## Caveats

- **FL forgets the ComposeWithLLM script selection on quit** - the server re-selects it
  automatically on the first write in each FL process (see `piano-roll-setup.md`). If
  `fl_notes("read_steps")` says "no piano roll state" or a write leaves `note_count: 0`,
  the script did not run: call `fl_select_script(channel_index=<target>)`.
- **Accessibility permission** is required for the Cmd+Opt+Y auto-trigger. Without it, the
  user must press the hotkey manually.
- **Race condition (verified):** the auto-trigger can fire before the piano roll window
  has focus, so the request file gets written but the script doesn't process it (state file
  stays stale). **Workaround:** if `fl_notes("read_steps")` doesn't change after a write,
  click in the piano roll window (computer use) and trigger again. The request file
  persists until the script consumes it, so the retry is safe.
- The piano roll writes to the **active pattern** (same as the step sequencer). `fl_notes`
  writes to whatever pattern the open piano roll is showing (or `target_pattern` if you
  pass one).
- Notes are written in **quarter-note** timing (1.0 = one beat). FL's internal PPQ (ticks
  per quarter, default 96) is handled by the script.
- `duration: 0` in `fl_notes("read_steps")` means the note is a **step-sequencer** note
  (from the channel rack grid), not a piano-roll note. Only notes with `duration > 0` are
  real piano-roll notes you can see in the piano roll grid.
- Read back after every write (`fl_notes("read_steps")`) to confirm.
- The piano roll toolbar is web-rendered (no AX tree); how the server drives it (key events,
  one pixel click, OCR proof) is in `fl-studio-mcp/docs/UI-AUTOMATION.md`. Writers given a
  `channel_index` prove the roll's channel from its on-screen title and refuse otherwise.
