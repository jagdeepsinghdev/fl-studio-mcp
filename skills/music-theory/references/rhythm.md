# Rhythm — tempo, grid, feel

Genre-specific drum grids (step numbers per part) live in `fl-genres/references/<genre>.md`.
This page is the theory that makes them readable and lets you invent your own.

## Tempo math

| BPM | beat (1/4) | 1/8 | 1/16 | 1/8 triplet | 1/16 triplet | 1/32 | bar (4/4) |
|---|---|---|---|---|---|---|---|
| 70 | 0.857 | 0.429 | 0.214 | 0.286 | 0.143 | 0.107 | 3.43 s |
| 90 | 0.667 | 0.333 | 0.167 | 0.222 | 0.111 | 0.083 | 2.67 s |
| 122 | 0.492 | 0.246 | 0.123 | 0.164 | 0.082 | 0.061 | 1.97 s |
| 140 | 0.429 | 0.214 | 0.107 | 0.143 | 0.071 | 0.054 | 1.71 s |
| 150 | 0.400 | 0.200 | 0.100 | 0.133 | 0.067 | 0.050 | 1.60 s |

Formula: beat = `60 / BPM`; divide by 2 (1/8), 4 (1/16), 3 (1/8 triplet), 6 (1/16 triplet), 8 (1/32).
Delay/reverb pre-delay synced to the beat use the same numbers (ms = s × 1000).

## Half-time, double-time, and counting
The same groove can be counted at two tempos:
- **Trap at 140** with the snare on beat 3 (step 9 of 16) = one snare per bar = **half-time feel**.
  The same audio counted at 70 BPM has the snare on 2 and 4 with 1/16 hats doubled to 1/32.
- The convention decides which number producers say: trap and drill say 140-150; boom-bap
  says 85-95; type beats in the ~120s are usually trap counted at that tempo with a half-time
  snare.
- **Detector octave errors are this same ambiguity.** Pick the count that matches the
  genre convention, then check: snare once per bar (half-time) or twice (normal backbeat).

## The 16-step grid (one bar of 4/4)

```
step:   1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
beat:   1           2           3           4
8ths:   1     &     2     &     3     &     4     &
16ths:  1  e  &  a  2  e  &  a  3  e  &  a  4  e  &  a
```
- Downbeats: steps 1, 5, 9, 13. Off-beat 8ths: 3, 7, 11, 15. "e" and "a" 16ths: the rest.
- Backbeat: **2 and 4 = steps 5 and 13** (pop, boom-bap, house clap); **half-time = step 9**.
- **Syncopation** = accents on weak positions (the "a" of a beat, steps 4/8/12/16, or the "&").
  Trap kicks love steps 1, 4 ("a" of 1), 8, 11 and 15: the bounce comes from the kick avoiding beats.
- Triplets don't fit 16 steps. A 1/16-triplet roll needs the piano roll (or a 24-step grid /
  FL's triplet snap), not the step sequencer.

## Swing and shuffle
- **Swing** delays every second 16th (or 8th). 50% = straight; ~54-58% = light groove
  (house, trap hats); ~60-66% = heavy shuffle (boom-bap, lo-fi). 66% ≈ triplet feel.
- Swing the **hats and percussion**; keep the kick and snare straight or lightly swung. Swinging
  everything just sounds late.
- FL: global swing via `fl_transport` (see `fl-mixing`); per-note offsets in the piano roll.

## Hi-hat language (trap/drill)
- **Base grid:** 1/8 (laid back), 1/16 (driving), or 1/8 triplet (bouncy/drill).
- **Rolls:** a short burst of 1/32 or 1/16-triplet notes, usually into beat 1 of the next bar
  or into the snare. 1-2 rolls per 2 bars; more sounds busy.
- **Ratchets:** 3-4 fast hits with velocities rising (crescendo) or falling.
- **Pitch rolls:** the roll's notes pitched up/down a few semitones: a signature modern trap sound.
- **Velocity pattern:** accent the 8ths (100), soften the in-between 16ths (60-80); without it,
  1/16 hats sound like a machine gun.
- **Gaps:** dropping the hats for half a bar before a hook makes the return hit harder.
- **Open hat:** on an off-beat (the "&"), choked by the next closed hat.

## Kick and 808 relationship
- In trap the 808 often **is** the kick's tail: kick and 808 start on the same steps; the
  808 sustains the pitch.
- When the kick and 808 are separate, start them together or leave the kick alone where the
  808 sustains; two low sounds overlapping at different pitches = mud and phase problems.
- Leave space: an 808 note that ends just before the next kick makes that kick punch.

## Ghost notes and groove
- **Ghost snare:** quiet (vel 30-50) snare or rim hits on 16ths next to the main snare (e.g.
  steps 8 and 15). Boom-bap and drill live on these.
- **Humanize:** ±5-15 ms timing and ±10-20 velocity on hats/percussion, not on the kick/snare.
- **Pocket:** a slightly late snare (5-20 ms) feels lazy/heavy; slightly early feels urgent.

## Phrase lengths and fills
- Music moves in **4-bar phrases**, grouped into 8 and 16 bars. Change something at every
  4-bar boundary; change a lot at 8/16 (`form-and-arrangement.md`).
- **Fill** = the last beat (or half bar) of a phrase: a hat roll, a snare roll, a tom run,
  an 808 slide, or a drop-out (silence). Fills announce "something new is coming".

## Meter (the theory behind the grid)

| Meter | Type | Beat unit | Grouping | Where |
|---|---|---|---|---|
| 4/4 | simple quadruple | quarter | 4 beats, each split in 2 | almost all pop, hip-hop, EDM |
| 2/4, 2/2 (cut time) | simple duple | quarter / half | 2 | marches, samba, reggaeton felt in 2 |
| 3/4 | simple triple | quarter | 3 | waltz, some ballads |
| 6/8 | compound duple | dotted quarter | 2 beats × 3 eighths | Dadra, Irish jigs, R&B/gospel ballads, Afro 12/8 feel |
| 9/8 | compound triple | dotted quarter | 3 × 3 | slip jigs |
| 12/8 | compound quadruple | dotted quarter | 4 × 3 | blues shuffle, doo-wop, Afrobeat feel, "triplet trap" |
| 5/4, 5/8 | irregular | | 3+2 or 2+3 | "Take Five", film, progressive |
| 7/8 | irregular | | 2+2+3, 3+2+2 (Rupak) | Balkan, prog, Rupak tala |
| 9/8 aksak | irregular | | 2+2+2+3 | Turkish/Balkan |
| 10/8, 11/8 | irregular | | 3+3+2+2; 2+2+3+2+2 | Jhaptaal-like, Balkan |

- **Simple vs compound:** in simple meter each beat divides into 2; in compound into 3.
  A 4/4 bar of straight 1/8 triplets is the same as 12/8; trap's triplet hats briefly imply 12/8 over 4/4.
- **Accent hierarchy (metric weight):** beat 1 > beat 3 > beats 2 and 4 > the "&"s > the 16ths. Placing
  important events on weak positions = syncopation; placing them on strong ones = stability.
- **Hypermeter:** bars group into 2-, 4- and 8-bar "hyper-measures"; bar 1 of a 4-bar group is
  "strong" (where chords change, where sections start). A phrase of 3 or 5 bars feels unexpected.
- **Anacrusis (pickup):** notes before the first downbeat; melodies often start on a pickup.

## Advanced rhythmic devices

| Device | What | Example / use |
|---|---|---|
| **Hemiola** | 3 against 2 at the bar level: two 3/4 bars felt as three 2/4 bars | baroque cadences, Afro/Latin 6/8 ↔ 3/4 |
| **Cross-rhythm / polyrhythm** | two different pulse divisions at once: 3:2, 4:3, 5:4 | West African bells, jazz drums, triplet hats over straight drums |
| **Polymeter** | patterns of different lengths cycling together (a 3-step and a 4-step loop meet every 12) | techno, IDM, Steve Reich phasing |
| **Metric modulation** | a subdivision of the old tempo becomes the new beat (triplet 8th → new quarter: tempo × 1.5) | Elliott Carter, prog, a trap hat-grid switch that changes the feel |
| **Tresillo (3+3+2)** | an 8-unit grouping | dembow, Afrobeats, trap hat and 808 rhythms, pop syncopation |
| **Clave** | 2-bar asymmetric timeline | Afro-Cuban music; `world-and-genre-theory.md` |
| **Additive rhythm** | groups of 2s and 3s (2+2+3) | Indian tala, Balkan, Philip Glass |
| **Rubato / free time** | flexible tempo | alap, intros, ballad endings |
| **Groove templates** | microtiming offsets (MPC swing, Dilla "drunk" feel) | lo-fi, neo-soul; FL groove/swing |

## Polyrhythm and displacement (advanced)
- **3 over 4:** a pattern that repeats every 3 steps (or 3 eighths) against the 4/4 bar,
  e.g. a melody note every 3 sixteenths. It creates rolling, hypnotic motion.
- **Displacement:** shift a part by one 16th (drill's displaced snare/kick is exactly this;
  see `fl-genres` drill notes).
