# Worked example — "Hook", a Future-style dark trap loop (built 2026-10-03)

Original composition for learning: the *style* was studied from a type-beat reference
(private analysis, not in the repo), no notes, samples
or 808 line taken from it (`music-theory/references/learning-from-references.md`).

## Style sheet
| Axis | Choice | Why (theory) |
|---|---|---|
| Tempo / feel | 122 BPM, half-time (clap on beat 3) | matches the reference's pulse; one backbeat per bar = heavy, slow feel |
| Key | C# minor (Aeolian), one-chord drone (i) | dark; all motion goes to the 808 and the lead |
| 808 | root C# (MIDI 37), octave bounce in bar 2, turnaround B → A → slide G# in bar 4 | the turnaround leads back to C# (G# = the 5th, a strong return); different from the reference's F# → D# → E |
| Lead | bells (FLEX, preset picked by ear), AAAB motif | 3× falling G# → E → C# (chord tones on strong beats), bar 4 answers with the b6 → 5 sigh (A → G#) |
| Drums | sparse kick on the 808 hits, clap + snare on step 9, 1/8 hats with 1/16 bursts at phrase ends | trap convention (`music-theory/references/rhythm.md`) |

## Channels (default template + one added)
| Index | Channel | Role |
|---|---|---|
| 0 | 808 Kick | kick |
| 1 | 808 Clap | backbeat |
| 2 | 808 HiHat | hats |
| 3 | 808 Snare | backbeat layer |
| 4 | 808 Astronomic (FLEX) | 808 bass |
| 5 | Bells (FLEX, added) | lead |

## Drums (1-based steps per bar, 4 bars)
| Row | Bar 1 | Bar 2 | Bar 3 | Bar 4 | Hits |
|---|---|---|---|---|---|
| Kick | 1 8 11 | 1 4 11 15 | 1 8 11 | 1 7 9 13 | 14 |
| Clap | 9 | 9 | 9 | 9 | 4 |
| Snare | 9 | 9 | 9 | 9 | 4 |
| Hat | odd steps 1-15 | odd + 14 16 | odd steps 1-15 | odd + 12 14 16 | 37 |

## 808 (channel 4; time and duration in beats; MIDI 60 = C4)
| Bar | Notes (midi @ time, duration) |
|---|---|
| 1 | 37 @0 ×1.5 · 37 @1.75 ×0.6 · 37 @2.5 ×1.4 |
| 2 | 37 @4 ×0.6 · **49** @4.75 ×1.5 (octave) · 37 @6.5 ×0.9 · 37 @7.5 ×0.5 |
| 3 | = bar 1, +8 beats |
| 4 | 37 @12 ×1.4 · 35 @13.5 ×0.5 · 33 @14 ×1 · 32 @15 ×1 **slide** |

## Bells (channel 5)
| Bar | Notes |
|---|---|
| 1 | 80 @0 ×0.5 · 76 @0.75 ×0.5 · 73 @1.5 ×1 · 75 @3 ×0.5 · 76 @3.5 ×0.5 |
| 2 | 80 @4 ×0.5 · 76 @4.75 ×0.5 · 73 @5.5 ×0.75 · 71 @6.5 ×1.5 |
| 3 | = bar 1, +8 beats |
| 4 | 81 @12 ×1 · 80 @13 ×1.5 · 78 @14.75 ×0.5 · 76 @15.25 ×0.75 |
Velocities 0.65-0.9 (strong-beat notes louder).

## v2 (same day) — after comparing with the reference's stems
The v1 numbers above sounded "not even close" (user). Running basic-pitch on the reference's
`other.wav` / `bass.wav` (`music-theory/references/reading-analysis.md` §3) showed why:

| | Reference | v1 | v2 (built) |
|---|---|---|---|
| 808 | C#1 (25), ~1.7 notes/bar, ~1.5-beat spacing | C#2 (37), 3-4/bar | **C#1**, 9 notes / 4 bars, dotted-quarter feel, F#1 passing, slide up to G#1 |
| Melody layer | 14.4 notes/bar, C#3-G6, root+5th arpeggio | 4.5/bar sung-style motif, G#4-A5 | **1/8 arp** C#4-G#4-C#5-E5 (+D#, F#, b5 G), C#6 sparkle, 34 notes |
| Sustain layer | present (polyphonic other.wav) | none | **Pad** C#3-G#3-E4 held 4 bars |

### v2 Hook (pattern 1)
- Kick (bar steps): `1 7 | 1 13 | 1 7 | 1 7 13` (9) — on every 808 start. Clap/snare/hats unchanged.
- 808 (ch 4): 25@0×1.4 · 25@1.5×2.4 · 25@4×2.9 · 30@7×0.9 · 25@8×1.4 · 25@9.5×2.4 · 25@12×1.4 · 25@13.5×1.4 · 32@15×1 slide.
- Bells (ch 5): per bar 1/8 notes `61 68 73 68 76 68 73 68` / `61 68 73 68 75 68 73 66` / bar 1 / `61 68 73 68 76 75 73 67`,
  duration 0.45, velocity 0.85 on beats 1 & 3, 0.55-0.6 between; plus 85@0 and 85@8 (vel 0.5).
- Pad (ch 6, new FLEX): 49, 56, 64 held 16 beats (vel 0.55-0.6).

### Intro (pattern 2, new)
- Discord (ch 7, new FLEX): bars 1-2 49+50+55 (C#3 D3 G3: b2 + tritone), bars 3-4 49+56 with 50 dropping
  out at beat 14 → a bare C#-G# fifth before the hook.
- Riser (ch 8, new FLEX): one note 60@12×4 (reverse cymbal preset) into the hook's beat 1.
- Percussion: hats `- | - | 1 5 9 13 | 1 3 5 7 9 11 13 14 15 16`, clap + snare on bar 4 step 9.

### Presets to pick (user, by ear)
808 Behemoth (ch 4) · Synpluck Musicbox (ch 5) · PAD SQDark (ch 6) · Creeper Drone (ch 7) · Rev Cymbal (ch 8).
The Bells channel's default preset had Tape 26 % + Detune 40 % (sounded out of tune) — set to 0 via `fl_plugin set_param`.

## What happened during the build (lessons)
- The auto path refused the 808 write: the small floating roll showed "808 Astro…", OCR couldn't
  match the full name. `fl_select_script` also missed the wrench on that layout (it clicked y=145; the
  floating roll's wrench was at y≈178) and toggled the roll. Fix: the user selected 0ComposeWithLLM
  in the wrench menu by hand; the write went through with `open_roll_verified=True` after a screenshot
  + state-file check (SKILL.md §4 Path B). Same for the Bells roll.
- A write queued before the script was selected sat in `mcp_request.json`; it was backed up and the
  queue emptied before any roll change (rule 6b).
- Result: 4/14/4/37 drum hits, 808 14/14 notes (slide kept), Bells 18/18, `notes_deleted` 0 each.

## Next steps for this beat (not built yet)
Hat rolls (1/32 and triplet notes on channel 2 in the roll), hat velocity accents, a verse pattern
(hats busier, 808 simpler), playlist arrangement Intro → Hook ×2 (no playlist tool yet: manual),
808 Drive, sidechain/levels (`fl-mixing`), export + re-compare with the same pipeline.
