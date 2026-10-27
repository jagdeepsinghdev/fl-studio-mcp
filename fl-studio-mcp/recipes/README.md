# Recipes (`fl_recipe`)

A recipe is a beat written as **numbered steps** that can be applied to FL
Studio, edited, re-applied one step at a time, undone one step at a time, and
checked against listening gates. Files live here as `<name>.json`; the tool
takes a path or a bare name (`levels-style-hook`).

Recipes hold only our own notes/patterns. Never put reference-song audio, MIDI
renders or analysis output in one (CLAUDE.md rules 9-10); `meta.reference` is a
private pointer, not content.

## Schema (version 1)

```json
{"name": "levels-style-hook", "version": 1,
 "meta": {"bpm": 85, "key": "D minor", "reference": "...", "notes": "..."},
 "channels": [{"role": "kick", "name": "808 Kick", "plugin": "template"}],
 "patterns": [{"pattern": 1, "name": "Hook", "beats": 16}],
 "steps": [{"id": "01", "title": "tempo", "do": "transport", "bpm": 85}]}
```

- `name`: letters, digits, `. _ -` (it names the journal folder).
- `channels[]`: `role` (unique handle used by steps), `name` (the FL channel
  name; **roles resolve to channels by NAME at apply time** via
  `channels.getAll`, so indexes may move; two channels with the same name are
  refused). `plugin`, `sample`, `preset_hint`, `index_hint` are informational
  (the tool does not create channels).
- `patterns[]`: `pattern` (1-based), `name`, `beats`. `beats` sets how many
  bars a `steps` row spans (`beats / 4`, default 16 beats).
- `steps[]`: `id` (unique string, run order = list order), `title`, optional
  `gate` (a label such as `G1`), and `do`.

### `do` values

| do | fields | goes through |
|---|---|---|
| `transport` | `bpm` and/or `speed` | `fl_transport set_bpm / set_speed` |
| `pattern` | `pattern`, `name` and/or `beats` | `fl_pattern create / rename / set_len` (a missing pattern is created only if it is the next free slot) |
| `steps` | `pattern`, `rows: {role: bars}` | `fl_channel set_steps` (S7 `bars=`: 1-based steps per bar, 16 per bar; a shorter list cycles to fill the pattern) |
| `notes` | `pattern`, `role`, `notes: [{midi,time,duration,velocity,slide?}]` **or** `melody` (+`step_beats`, `note_beats`, `velocity`; the S7 grid form) | `fl_notes write_steps(channel_index, mode=replace)`; S1 roll-title proof applies |
| `fx` | `role`, `effect` (`echo`/`reverb`/`chorus`), knobs `mix`, `feedback`, `time`, `on`, `decay`, `size`, `amount` (0-1), optional `slot_index` | `fl_plugin echo/reverb/chorus` |
| `eq` | `role`, `band`, `gain`/`freq`/`bw` (0-1) | `fl_mixer set_eq` on the role's mixer track |
| `mix` | `role`, `volume` (0-1) and/or `pan` (-1..1) | `fl_mixer set_vol / set_pan` on the role's mixer track (the channel must be routed to its own track, not the master) |

## The tool

`fl_recipe(action, path, ...)`:

- `validate` - schema, unknown `do`, unknown roles, bad rows/notes; with FL
  connected also "every role resolves to exactly one channel".
- `plan` - per step: `new`, `same` (identical to what the part ledger says is
  in FL for `steps`/`notes`, or to the last journaled application for the other
  kinds) or `changed`.
- `apply` - `step` (one id) or `from_step..to_step` (default all), in order,
  one FL call at a time. Before writing, each step snapshots what it will
  replace into the journal. Stops at the first failed or unverified step
  (a failed note write also clears the queue). `same` steps are skipped unless
  `force=True`. At the end of a gate it says `gate G2 reached: export the section,
  compare it with the reference (fl_audio analyze both) and listen before continuing`;
  `stop_at_gates=True` halts at every gate end inside a range.
- `status` - per step: applied, verified, gate, attempts, ledger state.
- `undo` - restores the `before` of that step's most recent application.
  Refused if a LATER applied step touched the same target (same channel +
  pattern for steps/notes; same effect for fx; same band for eq; same track
  for mix) unless `force=True`.
- `export` - builds a recipe from the part ledger (+ channel list) for
  `from_pattern..to_pattern`, written to `path`.

## Journal

`fl-studio-mcp/.generated/recipes/<recipe name>/<fl_pid>.journal.json` (git
ignored, one file per FL process, append-only):
`{step, at, seq, before, after, verified, verification, ok, wrote, sig, touches}`.
An undo appends an `undo: true` entry that points at the entry it reversed; it
never edits earlier lines.

## Limits

- The part ledger only knows what this server wrote, and only in this FL
  process; after an FL restart everything plans as `new`.
- Undo cannot delete a pattern a step created, restore a pattern name, or read
  playback speed (no getter). Notes written to a channel that had no ledger
  entry undo to an empty roll.
- Step EQ needs controller v10.4h deployed.
