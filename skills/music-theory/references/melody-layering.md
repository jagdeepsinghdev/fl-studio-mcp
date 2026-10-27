# Melody layering — building a full melody from a bass, chords, a hook and accents

How to turn one idea into an arranged melody section. `melody-and-808.md` covers how to write
the *line* (motif, note choice, counter-melody, 808); this page covers the *stack*: what layers
exist, in what order to build them, how to make them human, and how to vary them across sections.
Concepts are general production practice distilled from a producer walkthrough; FL steps and drills
are in `fl-melody/references/melody-practice.md`.

## 1. The four layers (think of a pizza)

| Layer | Role | Typical content |
|---|---|---|
| **Foundation** | the bass pattern everything else sits on | sub bass, 808, bass line, or the bass register of the instrument |
| **Core** | the identity of the piece | chord progression + the melody inside and over it + how the chords are placed |
| **Support** | fills the body behind the core | pads, strings, a second instrument doubling the chords |
| **Toppings** | detail and surprise | counter-melodies, accents, textures, vocals, phrases, risers |

A melody that sounds thin or basic is usually missing a layer, not notes. A melody that sounds
cluttered usually has two layers doing the same job.

## 2. Build order (and where to spend time)

1. **Pick a clear sound** (a piano is easiest: you hear every note) and a rough tempo for the genre. Both can change later.
2. **Core first.** Chords, then the hook, in one scale. Spend most of the time here: if the first idea is wrong, every layer you add
   inherits the problem.
3. **Foundation** from the chord roots (see §3).
4. **Support layer** (pad/strings/second instrument) copying the chords, no counter-melody.
5. **Toppings** last: counter-melody, call and response, texture, accents.
6. **Sound design and space** (reverb, delay, pan) only once the notes are right.

## 3. Foundation and the "few roots" rule

- **Reverse-engineer songs you love:** loop a track, find the *bass notes*, and build chords on top of them.
  That teaches the progressions people actually use faster than any list.
- **Few different root notes = dark and unresolved.** One chord, or two roots, feels tense because nothing
  resolves. **Four different roots** gives room for a melodic, more resolved progression. Choose on purpose.
- The same chord can be placed differently (inversion, octave, doubled root, a dropped middle note,
  a note pulled down to a comfortable hand position). That is voicing, and it is where a plain progression becomes yours
  (`chords.md` §7, mood recipes in `chord-emotion.md`).

## 4. Make it sound played, not clicked

- **Velocity:** lower overall velocity gives a softer, more human instrument (most good instruments are velocity-sensitive);
  then vary it from note to note.
- **Timing:** move some notes slightly off the grid; nobody plays a perfect grid.
- **Arpeggiated or broken chords** feel more like a guitar than all notes struck at once.
- **Randomize a little, then fix by hand:** a randomize tool gives a base; adjust the notes that matter.
- **Balance (melody leads):** when a melody plays over chords, the top line is the loudest voice (velocity ~0.75-0.9), inner chord notes sit
  lowest (~0.5-0.55), and the bass is a steady foundation quieter than the melody (~0.55-0.65, not held under everything). The "bass strongest"
  rule in `fl-melody` `chord-practice.md` is for chords alone; once a hook is on top, turn the bass down.
- **Playability:** if a note sits far from the rest of a chord, an instrument player would play it elsewhere. Move it an octave.

## 5. Counter-melody sources (there is no single rule: it is taste)

1. **Freestyle in the scale:** a few notes in the scale placed in the gaps of the lead; change the ending to keep it interesting.
2. **Reuse chord tones:** the notes already in the current chord (the root and fifth are safest).
3. **Call and response:** one voice (vocal, lead) plays, another (flute, pluck) answers in the gap, with some notes changed.
   Leave gaps; you don't have to fill every bar.
4. **Change register or pan** so the answer sits apart from the lead. **Double-track** a simple part (play
   it twice, pan the takes left and right) for width; bury a rhythmic acoustic guitar low for motion
   (`idea-to-record.md` §3).
5. **Snap to the scale** while playing a keyboard (scale-lock features), so you cannot hit a wrong note.

## 6. Pairing layers (convention, not rules)

| Main instrument | Good partners |
|---|---|
| Guitar (nylon, picked) | flute, pad, strings, vocals, soft piano doubling |
| Piano (dark) | violins, vocal phrases, synth bass, plucks |
| All-synth stack | synth keys, a lead, synth bass, plucks, pads |

Add a real-sounding bass (electric, upright) when the chord instrument's own bass is thin. Lower the chord
instrument's bass so they do not fight.

## 7. Energy and arrangement without new melodies

- **Hook = add layers** (strings/pad on the chords, counter-melody, vocals up an octave).
- **Verse = remove layers** after a big hook (drop the strings, vocal, and counter-melody; leave space for a vocalist).
- **Octave shifts per section:** the same part an octave lower in one half and higher in the next keeps the listener interested.
- **Bring the bass in and out** with EQ automation or by muting it, so a new bass or an 808 can take over.
- **Thin out when fills arrive:** remove percussion and layers at the end of a section so the next one hits.
- More on form: `form-and-arrangement.md`.

## 8. Resampling for texture

- **Render the whole melody** (without the bass: stretched bass sounds odd), re-pitch it to a new key, and use that as
  a sampled-sounding layer. Pitching up two semitones, or down, changes the colour.
- **Texture layer:** copy the melody, pitch it far up, time-stretch it back down, filter, add grains, reverb and
  autopan, render, then chop or reverse it. Use it as an extra layer, not a replacement.
- **Tape-style saturation** (wobble, light distortion) sells the "sampled" vibe.

## 9. Pre-flight checklist

1. Which of the four layers are present? Which job is doubled?
2. How many different roots are there, and does that match the mood?
3. Are velocities and timings varied?
4. Is there a gap for the vocal?
5. What changes between hook and verse (layers, octave, bass)?
6. Is there one distinct accent (call and response, texture, riser)?

## See also
`melody-and-808.md` (motif, note choice, contour) · `chords.md` (voicing) · `chord-emotion.md` (mood levers)
· `form-and-arrangement.md` (sections) · `timbre-and-orchestration.md` (instrument ranges)
