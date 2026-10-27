---
name: fl-song-builder
description: Build a whole multi-bar track in FL Studio with ANY instrument (drums + 808 + lead/keys/pad) using the default domain tools (fl_state, fl_transport, fl_pattern, fl_channel, fl_notes, fl_batch). Use for "make a beat + <instrument> melody", adding a second instrument, or rebuilding drums.
---

# Song builder — drums + 808 + any instrument (current tools)

All control is the `flstudio` MCP, **one call at a time** (CLAUDE.md rule 3). Theory (which notes,
which groove, why) comes from the `music-theory` skill; this page is the *mechanics*.
Verified end to end on 2026-10-03 (122 BPM C# minor "Hook": 4 drum rows, 14-note 808 with a
slide, 18-note FLEX lead), FL Studio Producer Edition v26.1.6.

## 0. Look before touching (rule 6)
```
fl_state                      # bpm, patterns, channels, playing?, piano-roll freshness
fl_channel(action="list")     # names + indexes (the user edits live; re-list before index calls)
fl_channel(action="get_steps", index=i)   # first 16 steps only — enough to see if a row is in use
```
An untitled project with empty rows is safe to build in; anything else, ask first.

## 1. Tempo, pattern, length
```
fl_transport(action="set_bpm", bpm=122)
fl_transport(action="set_speed", speed=1)          # BPM and speed stack (CLAUDE.md §2.1)
fl_pattern(action="set_len", pattern=1, beats=16)  # 4 bars = 16 beats; drums+notes share it
fl_pattern(action="rename", pattern=1, name="Hook")
```
Sections = one pattern each: `fl_pattern(action="create", name="Verse")` (never jump onto an empty
pattern: §2.4).

## 2. Drums (step sequencer)
One row per channel, **16 steps per bar × bars** booleans (64 for 4 bars), 1/16 resolution:
```
fl_channel(action="set_steps", index=0, pattern=1, steps=[true,false,...])   # 64 bools
```
Build the rows with a tiny script (bar lists of 1-based steps → bools) instead of typing them.
**All rows in ONE trip** with the controller action names (verified):
```
fl_batch(items=[
  {"action":"channels.setStepSequence","params":{"channel":0,"target_pattern":1,"pattern":[...64 bools]}},
  {"action":"channels.setStepSequence","params":{"channel":1,"target_pattern":1,"pattern":[...]}},
  {"action":"channels.getStepSequence","params":{"channel":0}}])
```
`fl_batch` takes controller names (`channels.*`, `transport.setBPM`, `patterns.setLength` …), **not**
`channel.get_steps`-style tool names (that fails "unknown action"). Reads return the first 16 steps.
Check each write's `active_steps` against your plan. Step templates: `fl-patterns/references/drum-templates.md`.
Triplets / 1/32 hat rolls don't fit the 16-step grid: write them as piano-roll notes on the hat channel.

## 3. Instruments
```
fl_channel(action="add", plugin="FLEX", name="Bells")   # native Add menu; returns index + mixer track
```
- **Presets are picked by the user, by ear** (`fl_plugin load_preset` is unverified in v45). FLEX opens
  its browser on add. Picking a preset **renames the channel** to the preset; re-list before name-based steps.
- The default template's **`808 Astronomic`** channel is a FLEX 808 (Drive = param 11): use it as the 808.
- `fl_plugin(action="list_params", index=i)` tells you what a channel is (FLEX params: Tone, Drive, …).

## 4. Notes (piano roll) — the handshake is mandatory (CLAUDE.md §6b)
Note format (beats from the pattern start; MIDI 60 = C4 here = **C5 in FL's labels**):
```
{"midi": 37, "time": 0, "duration": 1.5, "velocity": 0.9}            # velocity 0-1
{"midi": 32, "time": 15, "duration": 1, "velocity": 0.9, "slide": true}   # 808 slide
```
**Path A (automatic):** `fl_notes(action="write_steps", channel_index=i, target_pattern=1, mode="replace", notes=[...])`
— the server opens the roll on channel i, proves it by OCR of the roll title, selects ComposeWithLLM
once per FL process, writes.
**Path B (when A refuses)** — known refusals: a small floating roll truncates the title ("808 Astro…")
so OCR can't match a long channel name; `fl_select_script` can't find the wrench on that layout either.
1. The user opens the target's roll and selects **0ComposeWithLLM** in the roll's wrench menu (one click
   each; once per FL session — they may need to do it once per roll they open).
2. Prove the target yourself: screenshot (`screencapture -x shot.png`, read it) shows the roll title;
   `piano_roll_state.json` mtime just updated and `noteCount` = the target's current notes (0 if new);
   `mcp_request.json` is `[]`.
3. `fl_notes(action="write_steps", open_roll_verified=True, target_pattern=1, mode="replace", notes=[...])`.
Never use `open_roll_verified=True` without that proof: the script writes to whichever roll is OPEN.
**Fast variant of Path B (used for 5 writes on 2026-10-03):** call the write with `channel_index` first —
on the floating-roll layout it *does* select the channel, switch the roll and set the pattern, then refuses
on the OCR step (titles `''`). Screenshot: if the roll title is the target, re-send the same notes with
`open_roll_verified=True` + `target_pattern`. The ComposeWithLLM selection persists for the FL process.

## 5. Verify before "done"
- `fl_state(fresh_seconds=120)` → `piano_roll.note_count` = notes sent, `stale: false`, pitches/times match.
- `mcp_response.json` → `notes_added` = sent, `notes_deleted` = what you meant to replace (0 for a new part).
- `mcp_request.json` must be `[]` (never leave a write queued). There is no clear-queue domain tool:
  if a write must be abandoned, back the file up and write `[]` to it.
- Drums: each `active_steps` = planned hit count; `fl_pattern set_len` = bars × 4.
- `fl_transport(action="play")` **toggles**: check `fl_state.transport.is_playing` first.

## 6. Clean / redo
- One drum row: `set_steps` with all `false`.
- One instrument: `write_steps` again with `mode="replace"` (handshake again).
- Whole roll of a channel: `fl_delete(target="roll_notes", …)` (destructive tier; see `fl_help("delete")`).

## Legacy tools (not on the default surface)
`fl_build_track`, `fl_write_drums`, `fl_write_melody` (bar lists, `step_beats`, note names like "C#5") exist
only when the server runs with `LEGACY_TOOLS=1` (one-cycle migration). Don't plan around them.

## Gotchas
- Never two `flstudio` calls in parallel (one command/response file pair).
- A FLEX/plugin window opening steals focus; in-engine keys go to the focused form (`fl-melody` → `references/piano-roll-setup.md`).
- The roll title redraws ~1 s late; screenshot after a short wait.
- Long material (hundreds of notes, e.g. a transcription from another tool): `fl_notes(action="import_midi", channel_index, path=.mid)`
  (FL's own Import MIDI, ~15 s, verified read-back; replaces that channel's notes in the pattern).

## References
- **Theory (which chords, bass and melody to write; form; learning from a reference):** `music-theory` skill → `skills/music-theory/references/harmony.md`, `skills/music-theory/references/melody-and-808.md`, `skills/music-theory/references/form-and-arrangement.md`, `skills/music-theory/references/learning-from-references.md`, `skills/music-theory/references/reading-analysis.md`.
- **`references/build-around-a-sample.md` — one sample (Splice loop/melody/guitar) to a full 20-bar song: measure it, genre kit, one melody, hybrid double, sections, glued mix, audit.**
- An analysed song as one call: `fl_preset(action="load_song", song_dir=...)` — the `song.json` folder format is in `fl-studio-mcp/docs/SONG-TO-FL.md`.
- **`references/checkpoint-workflow.md` — build in a reference's style gate by gate (G0-G6): build one layer, compare its numbers (`fl_notes read_steps`, `fl_audio analyze`), A/B with muted REF channels, only then continue.**
- `references/layers-by-style.md` — which roles to build (808, arp, lead, pad, discord, riser, percussion…) per style, with installed FLEX preset names and how to write each.
- Worked example: `references/future-style-hook.md` (the 2026-10-03 build, v1 → v2, every note and step).
