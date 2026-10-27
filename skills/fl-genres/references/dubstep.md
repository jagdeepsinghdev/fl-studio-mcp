# Dubstep in FL Studio

Read `fl-studio` for the tool map and `fl-setup` if a call times out. Verify the connection first (`fl_state` must return a position).

**Tempo:** 140 (half-time) BPM. Use `fl_transport("set_bpm")(<target BPM>)` to set the real tempo (the toolbar box updates). It's the only reliable tempo lever; `fl_transport("set_speed")` only plays faster/slower without changing the BPM.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` argument for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 11 | `[true, false, false, false, false, false, false, false, false, false, true, false, false, false, false, false]` |
| Snare | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Clap | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Closed/open hat | 3, 7, 11, 15 | `[false, false, true, false, false, false, true, false, false, false, true, false, false, false, true, false]` |

**Feel:** Half-time: one snare on step 9. Kick on 1 and 11, lots of space so a wobble bass can occupy the gaps. Hats sparse.

**Swing:** `fl_transport  # swing (gap)(x)` sets FL's *global* swing (0.0–1.0). Keep it straight (`0.0`). Its scale vs. the MPC-style percentages above is not calibrated: start there, listen, adjust; `fl_state  # swing (gap)` reads it back.

## Steps

1. `fl_state` and map channels by **name** (Kick, Snare/Clap, HiHat). Indexes are 0-based. Don't assume the order.
2. For each part with steps: `fl_channel("set_steps")(channel, pattern)` using the row above. Skip parts marked (none) or clear them by sending 16 `false`.
3. Read each channel back with `fl_channel("get_steps")` and confirm it matches before playing.
4. `fl_transport("loop")("pattern")`, then `fl_transport("play")`. Tell the user what you set, then adjust by ear together.
5. Mix: `fl_channel("set_vol")` (0-1) / `fl_channel("set_pan")`. Sub sine mono below 100 Hz; mid bass heavily processed (distortion, multiband). Snare huge, layered clap + snare, with reverb tail.

## Variations
**Key/scale:** typically F, G or A minor; minor, half-time; wobble on the root. For exact MIDI notes, chord formulas and progressions read `fl-melody` → `references/scales.md`.


Sound design carries this genre: LFO-modulated bass. Drop the kick at the end of the phrase for a silence before the drop.

## Caveats

- Patterns are the standard conventions for the genre, written from music knowledge. They were **not** auditioned in FL by the assistant; expect to tune by ear.
- Persistent notes need the step sequencer (`fl_channel("set_steps")` / `fl_channel("set_steps")  # one bit`). `fl_channel  # real-time trigger (gap)` is real-time only.
- Melody/bass: use the `fl-melody` skill (piano roll + ComposeWithLLM). It works; the script must be re-selected in the piano roll toolbar each FL session.
- Ask before overwriting a pattern the user may have made: read it with `fl_channel("get_steps")` first.
