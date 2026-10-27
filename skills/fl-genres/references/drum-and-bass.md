# Drum & Bass in FL Studio

Read `fl-studio` for the tool map and `fl-setup` if a call times out. Verify the connection first (`fl_state` must return a position).

**Tempo:** 170-176 BPM. Use `fl_transport("set_bpm")(<target BPM>)` to set the real tempo (the toolbar box updates). It's the only reliable tempo lever; `fl_transport("set_speed")` only plays faster/slower without changing the BPM.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` argument for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 11 | `[true, false, false, false, false, false, false, false, false, false, true, false, false, false, false, false]` |
| Snare | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Clap | (none) | `[false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false]` |
| Closed/open hat | 1, 3, 5, 7, 9, 11, 13, 15 | `[true, false, true, false, true, false, true, false, true, false, true, false, true, false, true, false]` |

**Feel:** Classic two-step: kick on 1 and the 'and' of 3 (step 11), snare on 2 and 4 (steps 5 and 13). Fast tempo makes it feel double-time. Hats/ride on 8ths, ghost snares on steps 8 and 16 for rolling feel.

**Swing:** `fl_transport  # swing (gap)(x)` sets FL's *global* swing (0.0–1.0). Keep it straight (`0.0`); the breakbeat pattern carries the groove. Its scale vs. the MPC-style percentages above is not calibrated: start there, listen, adjust; `fl_state  # swing (gap)` reads it back.

## Steps

1. `fl_state` and map channels by **name** (Kick, Snare/Clap, HiHat). Indexes are 0-based. Don't assume the order.
2. For each part with steps: `fl_channel("set_steps")(channel, pattern)` using the row above. Skip parts marked (none) or clear them by sending 16 `false`.
3. Read each channel back with `fl_channel("get_steps")` and confirm it matches before playing.
4. `fl_transport("loop")("pattern")`, then `fl_transport("play")`. Tell the user what you set, then adjust by ear together.
5. Mix: `fl_channel("set_vol")` (0-1) / `fl_channel("set_pan")`. Tight, bright snare; sub bass is a clean sine below 100 Hz and mono; mid bass (reese) sits above. Snare is loud.

## Variations
**Key/scale:** typically A, C or F# minor; liquid=Dorian, raw=minor. For exact MIDI notes, chord formulas and progressions read `fl-melody` → `references/scales.md`.


Amen-style breaks via chopped samples; add a snare fill on steps 13-16 every 4th bar.

## Caveats

- Patterns are the standard conventions for the genre, written from music knowledge. They were **not** auditioned in FL by the assistant; expect to tune by ear.
- Persistent notes need the step sequencer (`fl_channel("set_steps")` / `fl_channel("set_steps")  # one bit`). `fl_channel  # real-time trigger (gap)` is real-time only.
- Melody/bass: use the `fl-melody` skill (piano roll + ComposeWithLLM). It works; the script must be re-selected in the piano roll toolbar each FL session.
- Ask before overwriting a pattern the user may have made: read it with `fl_channel("get_steps")` first.
