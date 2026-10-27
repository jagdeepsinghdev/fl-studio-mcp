# Afrobeats in FL Studio

**One call:** `fl_genre("load", genre="afrobeats")` (pack `fl-studio-mcp/presets/genres/afrobeats.json`).
**Tempo:** about 104 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.12.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 7, 11 | `[true, false, false, false, false, false, true, false, false, false, true, false, false, false, false, false]` |
| Snare | 12 | `[false, false, false, false, false, false, false, false, false, false, false, true, false, false, false, false]` |
| Clap | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Closed/open hat | 3, 7, 11, 15 | `[false, false, true, false, false, false, true, false, false, false, true, false, false, false, true, false]` |

**Feel:** Syncopated kick (1, 7, 11), rim/snare on step 12, clap on 2 and 4, off-beat shakers/hats; bouncy, swung slightly.

**Key/scale:** major keys with bright, simple chords. Pack default: A major, progression I - IV - vi - V (triad, offbeat rhythm); bass plays the roots (offbeat).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.
