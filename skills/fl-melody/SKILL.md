---
name: fl-melody
description: Write melodies, basslines, chords and any notes into FL Studio's piano roll (ComposeWithLLM queue, via fl_notes). Includes scales/keys, per-genre note recipes, and fixing "notes didn't land". Use when the user wants notes, a tune, chords or a bass line on any instrument.
---

# Melody, bass & chords (piano roll)

Owns: everything that writes/reads piano-roll **notes** — all through **`fl_notes`**
(`action` + params). Drums → `fl-patterns`; sounds → `fl-plugins`; whole track at once →
`fl-song-builder` (a `fl_notes` write in a `fl_batch`).

> **The §0 step (ComposeWithLLM selection) is AUTOMATIC.** The first note write in each FL
> process selects the script (FL forgets it on every launch). Writers given `channel_index`
> retarget the roll and prove it from the on-screen title (OCR), refusing otherwise.
> `note_count: 0` after a write = the script didn't run (call `fl_select_script(channel_index=…)`
> manually). Mechanics: `fl-studio-mcp/docs/UI-AUTOMATION.md`; summary: `references/piano-roll-setup.md`.

## Writing safely (the script hits whichever roll is OPEN — read this)
`fl_notes("write_steps", …)` is **refused unless you pass `open_roll_verified=True`**.
That flag is your attestation that you did the two steps below. It exists because the
script writes to whatever roll is open, and a wrong roll is the classic failure.

1. **Open the target's roll:** pass `channel_index=<target>` to the writer - the server selects
   the channel, re-opens its roll and proves the roll title on screen (else it refuses, and
   `open_roll_verified` is not needed). Without `channel_index`, open the roll yourself
   (select + F7) and attest with `open_roll_verified=True`. The script is selected
   automatically; `fl_select_script(channel_index=<target>)` does it by hand.
2. **Confirm the roll with a signature check:** `fl_notes("read_steps")` (it reads
   `piano_roll_state.json` with an mtime guard — if `stale` is true, trigger first). It must
   show the target's notes (an empty new channel = 0). If it shows another channel's notes, STOP.
3. **Then write:** `fl_notes("write_steps", notes=[…], mode="add"|"replace",
   target_pattern=0, open_roll_verified=True)`. If the queue is still pending afterwards the
   script didn't run — bring FL to the front (`osascript -e 'tell application "FL Studio 2026"
   to activate'`) and re-trigger. If you give up, `fl_notes("clear")` — never leave a write
   queued (it lands on whatever roll the user opens next; the response shows `notes_deleted`,
   use it as a check).
4. **Sample channels** (a wav loaded as its own channel) need ONE trigger note at FL's C5 =
   **MIDI 60**, as long as the sample: `beats = seconds × BPM / 60` (32.8 s at 117 BPM = 64
   beats). A shorter note plays only part of the sample.

## Workflow (do in this order)
1. **Verify the target channel:** `fl_state` → ONLY the target has `is_selected: true`
   (a select can say "selected" while another stays selected → notes land on the wrong
   channel). `fl_notes("clear")` clears whichever roll is open — clear *before* switching.
2. **Set pattern length first:** `fl_pattern("set_len", pattern=…, beats=…)`; the phrase must
   end within it.
3. **Pick notes:** key/scale/chords from `references/scales.md`; genre bass/chord ideas
   `references/genre-recipes.md`. Presets instead: `fl_notes("write_steps")` with the preset's
   note list (`fl-presets`).
4. **Write** (below) with `open_roll_verified=True`. **Feel first (owner, 2026-10-11): every write must sound played, not
   clicked.** `write_chords` and `melody=` tokens are **humanized by default** (strong bass, softer upper notes, light
   strum, accented bar starts, tiny timing drift; pass `humanize=false` for exact grid notes). For a hook that really
   sings, write explicit `notes=` (one peak, uneven rhythm, pickups, a quiet unresolved end): `references/melody-practice.md`.
   Explicit `notes=` are never altered by the server.
5. **Read back:** `fl_notes("read_steps")` → `note_count` = what you sent, notes span the whole
   phrase.
6. **Play:** `fl_state` first (play toggles), `fl_transport("loop", mode="pattern")`,
   `fl_transport("play")`.

## `fl_notes` actions
- `fl_notes("write_steps", notes, mode="add"|"replace", target_pattern=0, auto_trigger=True,
  open_roll_verified=True)` — `target_pattern` (existing pattern, 1-based) is selected first so
  notes land there; `0` = the active pattern. Notes: `{midi, duration (quarter notes), time
  (quarters), velocity 0–1}`. 60 = C4. **A chord is just several notes at the same `time`.**
- `fl_notes("read_steps")` — the open roll's notes with the mtime guard (`stale` flag).
- `fl_notes("clear")` — clear the current roll's notes (via the queue).
- `fl_delete("roll_notes", …)` — delete specific notes by match (the destructive path).
- `fl_notes("import_midi", channel_index, notes|path, [target_pattern], [bpm])` - imports via the
  roll's own File > Import MIDI (no ComposeWithLLM queue). **REPLACES that channel's notes in the
  pattern**, ~15 s: use for whole phrases / complex MIDI or when the script path is unavailable;
  prefer `write_steps` for small edits. UI steps: `fl-studio-mcp/docs/UI-AUTOMATION.md` section 3.4.
- The ComposeWithLLM trigger is automatic (`auto_trigger`) and so is the once-per-FL-process script
  selection. Setup & how it works: `references/piano-roll-setup.md`.

> The legacy `fl_send_notes` / `fl_send_chord` / `fl_get_piano_roll_state` / `fl_clear_piano_roll`
> / `fl_trigger_script` / `fl_clear_request_queue` are the same operations behind `LEGACY_TOOLS=1`;
> prefer the `fl_notes` actions above.

### Single melody / bassline (raw notes)

```
fl_notes("write_steps",
  notes = [
    {"midi": 36, "duration": 0.5, "time": 0.0, "velocity": 1.0},
    {"midi": 36, "duration": 0.5, "time": 0.5, "velocity": 0.8},
    {"midi": 40, "duration": 0.5, "time": 1.0, "velocity": 0.9},
    {"midi": 36, "duration": 1.0, "time": 1.5, "velocity": 1.0},
  ],
  mode = "replace",            # clears existing notes first; "add" keeps them
  open_roll_verified = True    # you did the F7 + read_steps confirmation above
)
```

- `midi`: 36 = C1 (bass range), 48 = C2, 60 = C4 (middle C), 72 = C5
- `duration`: in **quarter notes** (1.0 = one beat, 0.5 = eighth note, 2.0 = half note)
- `time`: start position in quarter notes (0.0 = start of bar 1)
- `velocity`: 0.0–1.0

### Chords (several notes at the same time)

```
fl_notes("write_steps",
  notes = [
    {"midi": 60, "duration": 2.0, "time": 0.0, "velocity": 0.8},  # C4
    {"midi": 64, "duration": 2.0, "time": 0.0, "velocity": 0.8},  # E4
    {"midi": 67, "duration": 2.0, "time": 0.0, "velocity": 0.8},  # G4
  ],
  open_roll_verified = True
)
```


## References (open only what you need)
- **Theory first (which notes and why):** `music-theory` skill: scales/modes `skills/music-theory/references/scales-and-modes.md`, chords and voicings `skills/music-theory/references/chords.md`, progressions `skills/music-theory/references/harmony.md`, melody/808 writing `skills/music-theory/references/melody-and-808.md`, ragas `skills/music-theory/references/indian-classical-ragas.md`.
- `references/piano-roll-setup.md` — one-time setup, opening the piano roll on the right channel (computer use).
- `references/apply-queue.md` — queued notes not landing; drain the queue + play.
- `references/scales.md` — MIDI note lists, scales, chord formulas, progressions, keys per genre.
- `references/genre-recipes.md` — bass/chord/melody ideas per genre.
- `references/melody-practice.md` — layered-build drill (chords, bass, hook, counter-melody tokens), humanizing, hook vs verse; theory in `music-theory` `melody-layering.md`.
- `references/chord-practice.md` — mood chord drills (`write_chords` texts, revoice/pivot practice loops); theory in `music-theory` `chord-emotion.md`.
- `references/gotchas.md` — timeouts, race conditions, bar overflow, caveats.
- **Fast roll edits after a write** (quick legato/quantize/chop, glue, octave ±, duplicate right, nudge): `fl_shortcut` → `skills/fl-studio/references/shortcuts.md` (selection-based; open the right roll first, read back after).

## Chords from text + rescuing a played take (2026-10-06)
- `fl_notes("write_chords", text="Am F C G" | "Cmaj7 - Fm9 | G7sus4" | "C/E", channel_index,
  [beats_per_chord=4], [octave=4], [bass=true], [humanize=true])` - chord names -> notes, **humanized by default** (slash bass, 6/7/9/11/13,
  sus, dim, m7b5, add9). Goes through `write_steps`, so the roll handshake applies.
- `fl_notes("capture", [seconds=120], [target_pattern])` - FL's score log (notes PLAYED IN on a
  MIDI keyboard/pads) into the pattern. An empty log makes FL show a blocking Warning: it is
  dismissed automatically and reported as "empty"; success needs one new undo step.

