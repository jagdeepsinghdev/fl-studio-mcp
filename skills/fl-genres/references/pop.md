# Pop in FL Studio

**One call:** `fl_genre("load", genre="pop")` (pack `fl-studio-mcp/presets/genres/pop.json`).
**Tempo:** about 118 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.0.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 5, 9, 13 | `[true, false, false, false, true, false, false, false, true, false, false, false, true, false, false, false]` |
| Snare | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Clap | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Closed/open hat | 3, 7, 11, 15 | `[false, false, true, false, false, false, true, false, false, false, true, false, false, false, true, false]` |

**Feel:** Four-on-the-floor or steady kick, clap on 2 and 4, off-beat hats; the I-V-vi-IV loop under a vocal hook.

**Key/scale:** major keys (C, G, D). Pack default: C major, progression I - V - vi - IV (triad, half rhythm); bass plays the roots (pulse8).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.
