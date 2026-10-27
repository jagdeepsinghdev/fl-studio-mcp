# AGENT GUIDE — build a drums + melody track in FL Studio (MCP)

> **Fastest path (2026-10-06):** `fl_genre(action="load", genre="<id>")` builds tempo + beat + Keys/Bass
> + chords + bass + levels in ONE call (16 genres; live-proven on trap: 0 misses, 58 s). Use this guide
> when you need custom parts beyond a genre pack.

For any AI agent. Read the repo-root `CLAUDE.md` hard rules first. Everything here uses the
`flstudio` MCP server's **default domain tools** (`fl_state`, `fl_transport`, `fl_channel`, `fl_pattern`,
`fl_notes`, `fl_select_script`, `fl_batch`, `fl_delete`, `fl_preset`). **Sequential calls only — never two in parallel.**
The old one-shot helpers (`fl_build_track`, `fl_write_drums`, `fl_write_melody`, ...) are legacy: they exist only with
`LEGACY_TOOLS=1` and this guide no longer uses them. Step-by-step mechanics: **`skills/fl-song-builder/SKILL.md`**
(the same flow, with the controller-name `fl_batch` trick and the refusal/Path-B notes).
Genre detail: `skills/fl-genres/references/trap.md` ("Drill/trap with guitar").

## What you supply vs. what the tools do

| You supply (the only variables) | The tools do automatically |
|---|---|
| `bpm`, bars | `fl_transport set_bpm` + `set_speed 1.0`, `fl_pattern set_len` = bars x 4 beats |
| drum **step numbers** 1-16 per bar (kick/snare/hat/clap) | `fl_channel set_steps bars=[[1,7,12],...]` builds the 16-per-bar bool row |
| melody **note names** per bar (`"A4"`, `"C#5"`, `"-"` rest, `"~"` hold, MIDI ints, a list = chord) | `fl_notes write_steps melody=[[...]], step_beats=0.5` converts them to notes, retargets + proves the roll, queues, triggers |

Any instrument works (piano, bass, pad, lead, guitar...).

## Preconditions (check, don't assume)
1. `fl_state` -> connected, bpm, playing?, patterns. `fl_channel(action="list")` -> what is loaded (don't clobber the user's session).
2. New tools missing? Reload: `mcp({ connect: "flstudio" })` (no FL restart). `fl_connect(action="status")` for connection problems.
3. A melody channel must exist: `fl_channel(action="add", plugin="FLEX", name="Guitar")` (returns its index).
4. The ComposeWithLLM selection is automatic on the first note write per FL process (CLAUDE.md §0); manual: `fl_select_script(channel_index=i)`.

## Recipe
```
fl_transport(action="set_bpm", bpm=140);  fl_transport(action="set_speed", speed=1.0)
fl_pattern(action="set_len", pattern=1, beats=16)                       # 4 bars
fl_channel(action="set_steps", index=0, pattern=1,                      # kick
           bars=[[1,7,12],[1,8,11],[1,7,15],[1,6,11]])                  # 1-based steps per bar
fl_channel(action="set_steps", index=1, pattern=1, bars=[[9],[13],[9],[13]], n_bars=4)   # snare
fl_notes(action="write_steps", channel_index=3, target_pattern=1, mode="replace", step_beats=0.5,
         melody=[["A4","E5","C5","E5","A4","E5","C5","B4"],
                 ["F4","C5","A4","C5","F4","C5","A4","G4"],
                 ["C5","G5","E5","G5","C5","G5","E5","D5"],
                 ["G4","D5","B4","D5","G4","D5","B4","E5"]])
fl_transport(action="loop", mode="pattern"); fl_transport(action="play")
```
`bars` shorter than `n_bars` cycles to fill it (default `n_bars` = number of lists; a flat list = the same bar every bar,
needs `n_bars`). A part left out is silent. Give `steps=` (a bool row) OR `bars=`, `notes=` OR `melody=` — never both.
`~` holds the previous note one step (808s); an 808 slide is a note dict with `"slide": true` via `notes=`.
Several rows in ONE trip: `fl_batch` with controller names (see the skill).

## Clean up / start over
- Drums: `fl_channel(action="set_steps", ..., bars=[[]], n_bars=N)` writes an empty row (melody untouched).
- Notes: open the channel's roll (writers with `channel_index` do it, with proof), then `fl_delete(target="roll_notes", ...)`
  or `fl_notes write_steps mode="replace"`. Stuck queue: `fl_notes(action="clear_queue")` (backs up, then empties).

## Long or repeated material (no pasting)
- A shorter `bars=` / `melody=` list repeats to fill (`n_bars` for steps; for `melody` pass a bar list of the full length,
  or repeat it in your own code).
- 300+ notes (e.g. a transcription from another tool): write a `.mid` and use
  `fl_notes(action="import_midi", channel_index=i, path=...)`. (The legacy `fl_write_notes_file` is `LEGACY_TOOLS=1` only.)
- One call for an analysed song: `fl_preset(action="load_song", song_dir=...)` — folder format in
  `docs/SONG-TO-FL.md`.

## Verify (mandatory before saying "done")
1. `fl_channel(action="set_steps")` result: `active_steps` equals the hits you planned.
2. `fl_notes(action="read_steps")` (or `fl_state` piano roll) -> note count equals what you wrote, last note time < bars x 4.
   Count 0 = the script was not selected -> `fl_select_script(channel_index=i)`.
3. `fl_state` -> pattern length == bars x 4 and `is_playing`.
4. `fl_channel(action="get_steps")` returns only the first 16 steps by default (pass `steps=N`); say what you could not confirm.

## Piano-roll handshake (mandatory before any note write)
Writers given `channel_index` select the channel, retarget the roll and prove the title by OCR; otherwise do it by hand
(select channel -> F7 -> screenshot the title -> empty trigger -> `fl_notes read_steps` shows the target's notes) and pass
`open_roll_verified=True`. Check `notes_added`/`notes_deleted`. Full steps: `skills/fl-melody`.
FLEX channels are renamed to their preset, so address channels by index.

## Known gaps / gotchas
- `fl_transport(action="play")` toggles from the user's view: check `fl_state` first.
- A FLEX channel isn't a guitar sound until a preset is chosen. Choosing by name (`fl_plugin(action="load_preset")`) is
  unverified in v45 (Sprint S8); the old `fl_list_preset_names` / `fl_find_preset` / `fl_get_preset_count` are legacy only
  (`LEGACY_TOOLS=1`). Ask the user to pick the preset in FLEX's browser, then re-list channels (the name changes).
- **The user edits FL live.** Channels can be deleted/renumbered between your calls; re-list with `fl_channel(action="list")`
  before any index-based call.
- Not possible: per-bar playlist arrangement (no clip placement in v45; use `fl_pattern(action="chain")`), deleting
  patterns, loading audio by API.
- Timeouts: MCP commands ~2 s by default (long step rows use 10 s). Foreground shell calls die at 120 s: run slow jobs in the background.
- After adding/removing tools or skills: `cd fl-studio-mcp && uv run python scripts/gen-inventory.py`, commit at repo root, push only when asked.

## Code
Domain tools: `src/fl_studio_mcp/tools/*_v2.py`. Legacy helpers (kept for the S7 input parsers): `src/fl_studio_mcp/tools/song_builder.py`,
tests `tests/test_song_builder.py`.
