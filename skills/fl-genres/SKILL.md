---
name: fl-genres
description: Genre recipes + one-call packs (trap, drill, hip-hop, boom-bap, lofi, r&b, pop, afrobeats, phonk, punjabi, house, techno, future bass, dnb, dubstep, reggaeton) - tempo, grid, key, chords. Use when the user names a genre or style.
---

# Genres

Pick the genre, open ONE reference, then build with `fl-song-builder` (tools) or `fl-presets` (ready JSON).
BPM/keys below are typical; the reference has the exact grid and mix notes. Patterns are conventions,
not auditioned — tune by ear.

| Genre | BPM | Key | Feel | Reference |
|---|---|---|---|---|
| trap | 140 (half-time) | F#, G or A minor | sparse kick, snare on 9, 16th hats; includes the 4-bar drill + guitar recipe | `references/trap.md` |
| reggaeton | 90-98 | A or C minor | dembow | `references/reggaeton.md` |
| boom-bap | 85-95 | A or E minor | swung, soul 7th chords | `references/boom-bap.md` |
| lofi | 70-85 | D, F or A minor (Dorian) | sparse, swung, jazzy 9ths | `references/lofi.md` |
| house | 120-128 | A minor, C or F | four-on-the-floor, off-beat stabs | `references/house.md` |
| techno | 128-140 | A or D minor | minimal, repetitive | `references/techno.md` |
| drum-and-bass | 170-176 | A, C or F# minor | fast breaks, 16th bass | `references/drum-and-bass.md` |
| dubstep | 140 (half-time) | F, G or A minor | half-time, wobble on the root | `references/dubstep.md` |
| hip-hop | 85-100 | A, E or D minor | punchy kick, backbeat 2 & 4, 8th hats | `references/hip-hop.md` |
| future-bass | 140-160 (half-time) | F, C or G major | half-time drums, chopped 7th-chord stabs | `references/future-bass.md` |
| r&b | 70-95 | Eb/major with 7ths | laid-back half-time, lush 7ths | `references/rnb.md` |
| pop | 100-125 | C, G or D major | steady kick, clap 2 & 4, I-V-vi-IV | `references/pop.md` |
| afrobeats | 98-110 | A or G major | syncopated kick, off-beat hats, bouncy | `references/afrobeats.md` |
| phonk | 130-145 | C Phrygian / minor | dark, 16th hats, bII | `references/phonk.md` |
| punjabi | 90-100 | A minor | bhangra bounce (owner's punjabi-banger beat) | `references/punjabi.md` |

## One call per genre (2026-10-06)
`fl_genre("load", genre="trap")` sets the real tempo (speed 1.0) and swing, sizes pattern 1,
loads the genre's beat, creates **Keys** + **Bass** (FLEX) when missing, writes a chord
progression in the pack's key on Keys and the roots on Bass, then fixes master clipping.
Packs: `fl-studio-mcp/presets/genres/<id>.json` (trap, drill, boom-bap, lofi, house, techno,
reggaeton, drum-and-bass, dubstep, hip-hop, future-bass, rnb, pop, afrobeats, phonk, punjabi) — edit `key` / `progression` / `rhythm` there; `dry_run=true`
shows the plan, `list` / `show` read packs. Chords come from `utils/chords.py` (Roman numerals ->
notes; theory: `music-theory`). Convention, not auditioned.

## Genre drum kits, one call (2026-10-11; never the default 808 kit)
`fl_genre("load_kit", genre="afrobeats")` = one **Sampler per role** ("Kick AFRO", "Snare AFRO",
"Shaker AFRO", "Perc AFRO"...), created when missing, each loaded with the kit's sample (auto-retry
on the Open panel), then the genre beat routed onto them (`load_beat(channel_map=...)`) + the
kit's own shaker/perc/rim/open-hat parts. `fl_genre load` now does this as its drum step
(`kit=false` = old behaviour). `variant=1,2...` = next-best samples; `dry_run=true` lists the picks.
FL in front, hands off, about 10 s per sample.
Kits: `fl-studio-mcp/presets/kits/<genre>.json`, built offline by
`cd fl-studio-mcp && uv run python scripts/build_drumkits.py` from FL's bundled one-shots
(1,487 decodable; FL's compressed WAVs are skipped). Each file is measured (length, brightness,
beater click) and ranked against the genre's profile + ModeAudio family hints (HouseGen = house,
Downstream = lo-fi...; inferred from names) + keywords (conga, timbale...). Each role lists 3
`alternatives`: swap the `file` by hand after listening. Rules: `utils/drumkits.py` `PROFILES`.
Picks are measured, not auditioned.
`beat="<preset id>"` swaps the groove (a 4-bar "feel" groove with accents, pushes and a fill, then Intro/Verse/Break
presets written the same way; `build-around-a-sample.md`). A beat's own shaker/perc rows play instead of the kit's
generic ones. The first run takes 4-8 min (about 50 s per sample); an incomplete run is finished by running
`load_kit` again (it remembers what is loaded in this FL process; `reload=true` forces all).

## Adding a genre
New genre = new file `references/<genre>.md` + a row in the table above. **Not** a new skill.
Same structure as the others: tempo, drum grid (steps per part), feel, swing, mix, caveats.

## References
- **Genre theory (harmony, melody, rhythm DNA of each style, plus world styles and ragas):** `music-theory` skill → `skills/music-theory/references/world-and-genre-theory.md`, `skills/music-theory/references/indian-classical-ragas.md`.
- `references/trap.md`
- `references/reggaeton.md`
- `references/boom-bap.md`
- `references/lofi.md`
- `references/house.md`
- `references/techno.md`
- `references/drum-and-bass.md`
- `references/dubstep.md`
- `references/hip-hop.md`
- `references/future-bass.md`
- `references/rnb.md`
- `references/pop.md`
- `references/afrobeats.md`
- `references/phonk.md`
- `references/punjabi.md`
