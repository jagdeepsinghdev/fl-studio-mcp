# Timbre, orchestration and the frequency spectrum

Orchestration = choosing *which instrument plays which note* so every part is heard. In
production this merges with arrangement and mixing: most "mix problems" are orchestration problems.
Sources: Rimsky-Korsakov, Adler (*The Study of Orchestration*), film/production practice.

## 1. Instrument ranges (written in SPN; MIDI 60 = C4; FL shows C5)

| Instrument | Practical range | Sweet spot | Notes |
|---|---|---|---|
| 808 / sub bass | C1-C3 (MIDI 24-48) | C#1-G#1 (25-32) for trap | below ~E1 needs good speakers; distortion makes it audible on phones |
| Bass guitar (4-string) | E1-G3 (28-55) | E1-E2 | written an octave higher |
| Double bass | E1-G3 | | |
| Piano | A0-C8 (21-108) | C2-C6 | left hand ≥ C3 for chords |
| Guitar | E2-B5 (40-83) | | written an octave higher |
| Cello | C2-A5 (36-81) | | |
| Viola | C3-E6 (48-88) | | |
| Violin | G3-A7 (55-105) | G3-E6 | |
| Flute | C4-C7 (60-96) | G4-G6 | weak low register, bright high |
| Bansuri | ~G3-G6 (depends on size) | | breathy, bends easily (meend) |
| Clarinet (Bb) | D3-C7 (sounding) | | |
| Trumpet (Bb) | E3-C6 (sounding) | | |
| French horn | B1-F5 (sounding) | | |
| Trombone | E2-F5 | | |
| Tuba | D1-F4 | | |
| Harp | Cb1-G#7 | | |
| Sitar | ~C3-C6 (Sa usually ~C#3) | | sympathetic strings, meend |
| Bells / glockenspiel | G5-C8 (sounds 2 octaves above written) | | |
| Voices: soprano C4-A5, mezzo A3-F5, alto F3-D5, tenor C3-A4, baritone A2-F4, bass E2-E4 | | | pop vocals mostly A2-A4 (male), F3-F5 (female) |

## 2. The frequency spectrum (what lives where)

| Band | Range | Contents | Too much = | Too little = |
|---|---|---|---|---|
| Sub | 20-60 Hz | 808 fundamental, kick sub | rumble, headroom loss | no weight |
| Bass | 60-250 Hz | kick body, bass, low piano | boomy | thin |
| Low mids | 250-500 Hz | body of guitars, pads, vocals | **mud** (the most common problem) | hollow |
| Mids | 500 Hz-2 kHz | the melody/vocal core, snare body | honky, boxy | distant |
| Upper mids | 2-5 kHz | presence, articulation, ear sensitivity peak | harsh, fatiguing | dull |
| Presence/treble | 5-10 kHz | sibilance, hat/cymbal body, attack | sibilant, brittle | dark |
| Air | 10-20 kHz | sheen, breath | hiss | closed-in |

**Equal-loudness (Fletcher-Munson):** the ear is most sensitive around 2-5 kHz; bass and treble
sound quieter at low volumes. Check mixes at low volume; 808 levels judged loud only are too big.

## 3. Orchestration principles

1. **One idea per register.** The 808 owns the sub; the lead owns the 1-3 kHz zone; pads sit
   behind in the mids; hats own the top. Two parts in one register at once = masking.
2. **Contrast by timbre family:** plucked (fast decay) vs sustained (pad/strings) vs percussive
   (bells). A plucked lead over a sustained pad separates naturally.
3. **Doubling:**
   - Octave doubling (lead + an octave up) = brightness and size.
   - Unison doubling of different timbres (piano + bell; flute + violin) = a new hybrid colour.
   - Low octave doubling = weight (strings + low brass in film).
4. **Foreground / middleground / background:** the lead (melody/vocal), the countermelody/chords, the
   pads/textures. Only one foreground at a time.
5. **Call and response between instruments:** the lead phrase, then an answer on another
   instrument in the gap (a vocal line, then a bell answer).
6. **Density curve:** add instruments for energy (`form-and-arrangement.md`); remove them for contrast.

## 4. Synthesis and timbre (sound-design vocabulary)

| Element | Effect on timbre |
|---|---|
| **Waveform** | sine (pure, sub), triangle (soft, flute-like), square (hollow, odd harmonics: clarinet, chiptune), saw (bright, all harmonics: strings, brass, supersaw) |
| **Filter** | low-pass removes highs (darker, further away); cutoff + resonance; envelope on the cutoff = "pluck" or "wah" |
| **Envelope (ADSR)** | attack (fast = percussive; slow = swell), decay, sustain, release (tail) |
| **Unison/detune** | width and thickness (supersaw); too much = out of tune |
| **FM** | metallic, bell, electric piano (DX7) timbres |
| **Distortion/saturation** | adds harmonics: makes an 808 audible on small speakers, adds aggression |
| **Glide/portamento** | pitch slides between notes (808 slides, G-funk leads, meend) |
| **LFO** | periodic modulation: vibrato (pitch), tremolo (volume), wobble (filter) |

**808 specifics:** the 808 is a tuned sine/triangle with a pitch-drop envelope. Tune the sample:
find its root (pitch detector or by ear against a reference note), set it in the sampler so the
played MIDI note = the heard pitch; keep 808 notes inside the key. Distortion + a short pitch
envelope = the modern trap 808.

## 5. Mixing as applied theory (essentials only; FL commands in `fl-mixing`)
- **Kick vs 808:** either the same notes (layered) or sidechain the 808 to the kick; never two
  sustained low sounds at different pitches.
- **High-pass** everything that doesn't need lows (pads, leads, hats) at 100-200 Hz.
- **Panning** places parts side to side: bass, kick, snare and lead vocal centre; doubles, hats,
  percussion, pads wider.
- **Reverb/delay** push parts back (depth); short/dry = forward.
- **Volume balance before effects.** If a part can't be heard, change its register or timbre first,
  then EQ.

## 6. Film-scoring colour palette (useful for cinematic beats)
| Emotion | Typical scoring |
|---|---|
| Wonder, magic | Lydian, celesta/harp, chromatic mediants (C – E – Ab) |
| Heroic | major with bVI–bVII–I, French horns in 5ths/octaves, low strings ostinato |
| Threat, villain | Phrygian, tritones, low brass clusters, the minor-major 7 chord, hexatonic pole (C → Abm) |
| Sadness | minor iv, solo strings/piano, slow harmonic rhythm, suspensions resolving |
| Tension, suspense | pedal points, string tremolo, clusters, rising chromatic lines (Shepard tone) |
| Nostalgia | major 7/add9, solo piano, tape effects, Dorian/Mixolydian |
| Devotional, spiritual | drone, Bhairavi/Bhairav (Indian), modal choirs, open 5ths |
