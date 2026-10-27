# Layers by style — which parts to build, which FLEX sound, how to write them

A track is a stack of **roles**. Pick the style, build the roles in the order below, one channel
per role. Notes/rhythm theory: `skills/music-theory/references/` (`melody-and-808.md`, `rhythm.md`,
`form-and-arrangement.md`, `world-and-genre-theory.md`). FLEX preset names below are installed on
this Mac (packs in `/Applications/FL Studio 2026.app/Contents/Resources/FL/Data/Patches/Packs/FLEX/Packs/`);
the **user picks the preset** (no verified preset-load API) — tell them the exact name.

## The roles (what each layer does)

| Role | Job | Register (MIDI, 60 = C4) | How to write it | FLEX presets (installed) |
|---|---|---|---|---|
| **808 / sub** | weight + groove; often IS the kick's tail | 24-36 (C1-C2) | roots, long notes, kick on every 808 start, 1-2 slides per 4 bars | Core 808s: 808 Behemoth, 808 Cavernous, 808 Astronomic · Tuned 808 Bass: 808 Distorted, 808 Driven, 808 Clean |
| **Arp / ostinato** | constant motion over a static harmony | 60-85 | 1/8 or 1/16 stream of root + 5th (+ 3rd, passing tones), accent beats 1 & 3, one colour note per phrase | Mobile Synth Pluck: Synpluck Musicbox, Synpluck Crystal, Synpluck Glass · GM: Music Box, Celeste, Glockenspeil, Kalimba |
| **Lead / hook** | the memorable line | 60-90 | motif + variation (AAAB, call/response), chord tones on strong beats | GM: Flute, Pan Flute, Tubular Bells · Synpluck *, Lucky Pluck |
| **Pad** | glue, harmony bed, width | 48-72 | hold the chord (root-5th-3rd spread), 1-4 bars per chord, low velocity | Olbaid: PAD SQDark, PAD Deep Space · GM: Atmosphere, Sweep Pad, Synth Strings 1 |
| **Discord / tension texture** | unease, horror, "something's wrong" (intros, breaks) | 48-75 | clusters with a b2 + tritone (C#-D-G), slow; resolve toward the key's i at the section end | Creeper Drone, Dark Resonance, Bowed Glass, Goblin, Sci-Fi |
| **Riser / transition FX** | pull into the next section | any | ONE long note over the last 1-2 bars, ending on the next section's beat 1 | GM: Rev Cymbal, Seashore, Wind · Burst Noise, SFX Noise Case, Echo Drop |
| **Percussion** | rhythm identity, energy curve | step sequencer | intro: sparse → quarter → 1/8 → roll; hook: full; verse: busier hats, lighter melody | the template's 808 Kick/Clap/HiHat/Snare; GM percussion via FLEX GM kit presets |
| **Counter-melody** | answers the lead in its gaps | an octave from the lead | long notes or simple arpeggio, contrary motion | Strings 1, Tremolo Strings, Choir Aahs |
| **Ear candy / FX hits** | surprise at section starts | any | single hits on beat 1 (impact, reverse swell, vocal chop) | SFX Crasha, SFX Kit, Gunshot (drill) |

## Style recipes (roles to build, in order; convention, not auditioned except where marked)

| Style | Hook / main | Intro | Break / verse |
|---|---|---|---|
| **Dark trap / Future type** (built 2026-10-03, see `future-style-hook.md`) | 808 at C#1 (sparse, slides), 1/8 arp root+5th, pad drone, kick on 808, clap on 3, 1/8 hats + rolls | discord cluster + sparse percussion + reverse cymbal into the hook | drop the arp to the pad only, hats busier, 808 simpler |
| **Drill** | sliding 808 that changes notes often, piano/strings melody in harmonic minor, displaced snare, triplet hats | tremolo strings + discord, riser | 808 only + hats |
| **Lo-fi** | Rhodes/piano m9 chords, simple bass, swung boom-bap drums, vinyl texture | filtered chords | drums out, chords + texture |
| **R&B** | extended-chord keys, soft pad, sub bass, sparse drums, counter-melody | pad + keys | keys alone |
| **House** | four-on-the-floor, chord stabs, off-beat bass, pad | filtered loop + percussion build | breakdown: pad + riser |
| **Punjabi / bhangra pop** | dhol pattern, tumbi riff (pluck, Mixolydian/Kafi), 808 or bass, pad | tumbi alone + riser | dhol + vocal space |
| **Cinematic / ambient** | pad + counter-melody + slow percussion | discord + riser | pad alone |

## Order of building (why)
1. **Tempo + pattern length** (everything locks to it).
2. **Drums + 808** together (they share rhythm: kick on each 808 start).
3. **Harmony bed** (pad or chords), then **arp/lead** on top, an octave+ above the pad.
4. **Intro/transition layers last** (discord, riser, percussion build), in their own pattern
   (`fl_pattern(action="create", name="Intro", length_beats=16)`; drum rows with `target_pattern=2`).
5. Compare with the reference (`learning-from-references.md`): density per bar, register, band energy.

## Gotchas learned building these
- A preset with **Tape/Detune/Chorus** (FLEX default "LED Analogia": Tape 26 %, Detune 40 %) sounds
  out of tune; `fl_plugin(action="set_param", index, param=11/12, value=0)` fixes Tape/Detune on that
  FLEX family (check `list_params` names first — param indexes differ per preset).
- A **held pad + a b9 above it** clashes (A over the pad's G#): check melody notes against held pad notes.
- Each new channel is a new FLEX with the default sound: tell the user which preset to pick *before*
  judging the part.
