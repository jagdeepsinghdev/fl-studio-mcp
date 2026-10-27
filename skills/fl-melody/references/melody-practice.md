# Melody practice in FL Studio (layered build drill)

Hands-on build for the layers in `skills/music-theory/references/melody-layering.md` (theory) and the
line-writing rules in `melody-and-808.md`. Every token list below was checked offline with
`song_builder.melody_to_notes` (parses clean); the *sound* is from convention, not yet auditioned in FL.

## Setup
1. `fl_state` first: don't clobber the user's session. Pattern length 16 beats = 4 bars of 4 beats (default).
2. Three instrument channels: `fl_channel(action="add", plugin="FLEX", name="Chords")`, `... name="Lead"`, `... name="Bass"`
   (reuse existing ones; `fl_channel(action="list")` first).
3. Writers with `channel_index` run the roll handshake; write one channel at a time, then read it back with
   `fl_notes(action="read_steps", channel_index=N)`.
4. Token format for `melody=`: one inner list per bar, **16 tokens per bar at `step_beats=0.25`**; a note name or MIDI
   int = a note, `"-"` = rest, `"~"` = hold the previous note one more step, a list = a chord.

## The D-minor 4-layer drill (i - VI - III - VII = Dm - Bb - F - C)
Layer 1, **core (chords):**
`fl_notes(action="write_chords", text="Dm Bb F C", channel_index=<Chords>, beats_per_chord=4, octave=4, bass=false)`

Layer 2, **foundation (bass roots, whole notes):**
```
fl_notes(action="write_steps", channel_index=<Bass>, step_beats=0.25, melody=[
 ["D2"]+["~"]*15, ["Bb1"]+["~"]*15, ["F2"]+["~"]*15, ["C2"]+["~"]*15 ])
```
(Write the lists out in full when calling; shown here shortened. A bar must be 16 tokens.)

Layer 3, **hook (lead, AAAB-style: state, vary, sequence, resolve on the root):**
```
bar1 (Dm): F5 ~ - A5 ~ G5 F5 - D5 ~ ~ ~ - - - -
bar2 (Bb): D5 ~ - F5 ~ D5 C5 - Bb4 ~ ~ ~ - - - -
bar3 (F):  C5 ~ - F5 ~ A5 G5 - F5 ~ ~ ~ - - - -
bar4 (C):  G5 ~ - E5 ~ D5 C5 - D5 ~ ~ ~ - - - -
```
Same rhythm each bar, new pitches; the last bar answers and lands on D5 (the root).

Layer 4, **topping (counter-melody in the lead's gaps, chord tones, one octave apart):**
```
bar1: 12 rests, A4 - F4 -   |  bar2: 12 rests, F4 - D4 -
bar3: 12 rests, A4 - C5 -   |  bar4: 12 rests, G4 - E4 -
```

## Token lists give the skeleton, not the feeling
`melody=` puts every note on the 16th grid. The server now humanizes token melodies by default (accented bar starts and
beat 3, softer off-beats, tiny drift, slightly varied lengths; `humanize=false` to turn off), but that only removes the
metronome: it cannot invent phrasing. Use tokens to sketch, then rewrite with explicit `notes=[{midi,time,duration,velocity}]` (beats, velocity 0-1). A hook with feeling has:
- **one peak** (highest and loudest note, held longest, around bar 3 of 4) and a calm landing after it;
- **uneven rhythm**: a long note, then short off-beat notes, a rest, a pickup note just before the next chord;
- **accents**: strong beats about 0.85-1.0, weak/passing notes 0.55-0.7, the tail quieter;
- **tiny timing drift**: off-beat notes 0.01-0.03 beats late or early, never the bar's first note;
- **varied lengths** (0.2 to 1.4 beats), not every note filling its step;
- **an unresolved last note** (a chord 5th) that pulls back into bar 1 of the loop.

Worked example over Gm - Eb - Bb - F (Bb major): bar 1 D5 held, off-beat F5, G5 accent, pickup C5 into bar 2;
bar 2 Bb4 held, Eb5, G5 accent, pickup D5; bar 3 F5, A5, **Bb5 peak (vel 1.0, 1.4 beats)**, falling G5 F5; bar 4
D5, C5, A4, then a quiet C5 held to the loop point. Written live 2026-10-11; the sound is from convention.

## Then make it human and shape the section
1. **Velocity:** write with `velocity=0.6` for the support layers and vary per note (send `notes` with individual velocities for the hook).
2. **Randomize:** FL's Randomize tool is `fl_shortcut` id `piano_roll.randomize` (opt+R, confirm tier; catalog status **untested**, so open the dialog and read the result before keeping it).
3. **Hook vs verse:** copy the pattern; in the verse remove the counter-melody and the support layer (clear the channel in the verse pattern with `fl_delete`), keep the bass.
4. **Octave shift** one layer between halves; hear that the section changes without writing a new melody.
5. **Change key in one move:** select all and transpose; the scale shape stays the same, so the melody just moves key. `fl_shortcut` ids: `piano_roll.octave_up` / `octave_down` (⌘↑/⌘↓, **verified**); `piano_roll.move_up` / `move_down` (shift+↑/↓, per the video one semitone per press, catalog status **untested**: read the roll back after). Or rewrite with `write_chords` / `write_steps` in the new key.

## A A B A B C hook drill (predictable + surprise)
Theory: `music-theory` `hit-song-patterns.md` §4. One bar per letter: 6 bars = 24 beats
(`fl_pattern(action="set_len", beats=24)`), chords extended to 6 bars (`text="Dm Bb F C Dm Bb"`):
1. **A** = a 1-bar motif (3-5 notes, chord tones). **A** again, unchanged.
2. **B** = an answer: same rhythm, different pitches, ends on a non-root chord tone.
3. **A**, then **B** again (the listener now expects it).
4. **C** = the surprise: a new rhythm or the peak note, landing on the root.
Write it with explicit `notes=` (phrasing, `Token lists give the skeleton` above), loop it, then compare
with A A A A (same motif four times) and hear where attention drops.

## Practice loops
1. **Rebuild from the bass:** pick a song you like, find its bass notes (`fl_audio analyze what=["note"]` on its bass hits, or by ear), then build chords on them.
2. **Same chords, three hooks:** write three different 4-bar hooks over the drill's chords; keep the rhythm identical, change the pitches only.
3. **Remove one layer at a time** and say what is lost (weight, interest, space).
4. **Call and response:** copy the hook to a second channel, change some notes, play it in the lead's rests, pan it.
5. **Resample:** render a loop, repitch it two semitones, and compare.

## Gotchas
- 16 tokens per bar, always: a short bar silently shifts every later bar.
- Names use `b` for flats (`Bb1`, `Eb5`) and `#` for sharps.
- Write one channel at a time and read back; never queue a second write before the first has landed (see `gotchas.md`).
