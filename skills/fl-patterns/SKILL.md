---
name: fl-patterns
description: Drums and patterns in FL Studio - step sequencer, multi-bar drum rows, pattern length and phrase sync, song sections (multiple patterns), markers. Use for programming or fixing drums, "loop plays then goes silent", or building Intro/Verse/Chorus.
---

# Patterns & drums

Owns: step sequencer, pattern length, drum templates, sections. Melody notes → `fl-melody`;
whole track in one call → `fl-song-builder`.

## Fast path (multi-bar drums)
```
fl_channel("set_steps", index=<kick idx>, steps=[T,F,T,F, ...], pattern=1)   # per drum channel
fl_channel("set_steps", index=<snare idx>, steps=[...])
fl_channel("set_steps", index=<hat idx>,   steps=[...])
fl_pattern("set_len", pattern=1, beats=<phrase beats>)   # sync the phrase (see golden rule)
```
`fl_batch` can set several channels' steps in ONE trip. Templates for other styles:
`references/drum-templates.md`.

## Step-sequencer — `fl_channel` actions
- `fl_channel("set_steps", index, steps=[bool...], [pattern=1])` — write a channel's grid.
  `steps` may be longer than 16 (e.g. 64 = 4 bars, verified 2026-09-29). Writes go to the
  active pattern (the response names it); pass `pattern` (1-based) to target another.
- `fl_channel("get_steps", index, [steps=16], [pattern=1])` — read a channel's grid back.
  **Reads only the first 16 by default** — bars 2+ are not read back (a known limit).
- `fl_transport("play")` toggles; check `fl_state` first.
- Example (channel 0 = 808 Kick): kick on beats 1,3,5,7 →
  `steps=[1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]`.

## Quick drum pattern
1. `fl_state` → identify the drum channels (kick/snare/hat by name or plugin).
2. `fl_channel("set_steps", …)` for each with a 16-element boolean list.
3. `fl_pattern("set_len", pattern=1, beats=4)`, `fl_transport("loop", mode="pattern")`,
   `fl_transport("play")`.

## Pattern control — `fl_pattern`
- `fl_pattern("create", name="Verse", [length_beats], [color])` — next free slot, no jump
  (never `jumpToPattern` onto an empty one — it opens a blocking rename dialog).
- `fl_pattern("select", pattern=1)` — refuses non-existent patterns.
- `fl_pattern("rename", pattern=1, name="Chorus")` — **2-arg setPatternName** (3-arg crashes
  FL — C4).
- `fl_pattern("set_len", pattern, beats)` — **important:** a new FL pattern defaults to
  **16 beats**, not 4. A 4-beat pattern in a 16-beat pattern = 4 beats of sound + 12 of
  silence ("plays then goes empty"). Set it to 4 beats so the loop is tight.
- `fl_pattern("clone", pattern, [name])` — clones into slot+1 and **shifts later patterns
  up — re-list before addressing**.
- `fl_delete("pattern", …)` is the only way to remove a pattern (there is no non-destructive
  API; see the lessons below).

## Rules
- **Golden rule:** pattern length, drum loop and every melody phrase share ONE phrase length
  (a multiple of 4 beats). Details: `fl-studio-mcp/presets/README.md` → "The one golden rule".
- The step grid is 16 steps/bar; `set_steps` accepts 64 (4 bars) but `get_steps` reads back
  only 16 — bars 2+ are unverified by read-back.
- **Feel:** nudge some hits off the grid with the per-step shift
  (`fl_channel("set_step_param", index, step, param="pShift", value=)`, active steps only; it
  only delays) or `fl_variations(style="humanize")`; keep the main kick/snare on the grid.
  Why and how much: `skills/fl-plugins/references/sound-craft.md` §5.
- Never jump to an empty pattern (modal dialog blocks the bridge): `fl_pattern("create")`
  then `fl_pattern("select")`.

## Lessons (2026-09-29)
- `fl_pattern("clone")` can return a 128-beat clone: re-set the length with `set_len`. It
  shifts later patterns up: re-list with `fl_state`.
- **Deleting a pattern:** `fl_delete("pattern")` is the destructive path; if the user needs
  it, they can also do Playlist → pattern list → right-click → Delete. Don't create
  throw-away patterns.
- A select can report success while the active pattern drifts back to an empty default, so
  step reads looked empty. `fl_state` now returns **`active_pattern`** (the pattern FL is
  actually reading/writing, 1-based) and **`active_is_default`** (true when that pattern is
  a FL default/empty pattern — it won't appear in the `patterns` list because
  `_named_patterns()` skips defaults). If `active_is_default` is true, re-select the
  intended pattern before trusting empty step reads.
- **Diagnosing "beat not aligned" / empty step reads:** call `fl_state` and check
  `active_is_default`. If true, the active pattern is the empty default — your
  `set_steps` writes went to a different pattern than the one being read. Fix:
  `fl_pattern("select", pattern=<the pattern with your beat>)` then re-read.

## References
- **Rhythm theory (grid, half-time, swing, triplets, rolls, meter) and form:** `music-theory` skill → `skills/music-theory/references/rhythm.md`, `skills/music-theory/references/form-and-arrangement.md`.
- `references/drum-templates.md` — step templates per style.
- `references/sections.md` — patterns, markers, multi-section song workflow.
- **Hotkeys for arranging** (shift steps ←/→, clone/route channel, playlist duplicate / insert-delete space, zoom, next/prev pattern): `fl_shortcut` → `skills/fl-studio/references/shortcuts.md`.
