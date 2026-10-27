# Phonk in FL Studio

**One call:** `fl_genre("load", genre="phonk")` (pack `fl-studio-mcp/presets/genres/phonk.json`).
**Tempo:** about 140 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.0.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 8, 11 | `[true, false, false, false, false, false, false, true, false, false, true, false, false, false, false, false]` |
| Snare | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Clap | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Closed/open hat | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | `[true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true]` |

**Feel:** Dark, driving: hard kick pattern, backbeat on 2 and 4, 16th hats (add a cowbell lead on top); the flat second gives the menace.

**Key/scale:** Phrygian or minor; the bII chord. Pack default: C phrygian, progression i - II (triad, stab rhythm); bass plays the roots (sustain).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.
