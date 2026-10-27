# Chord practice in FL Studio (mood drills)

Hands-on drills for the progressions in `skills/music-theory/references/chord-emotion.md` (theory,
mood levers and the full table live there; this file only holds FL steps). Every `text=` below was
checked against `fl_studio_mcp.utils.chords.symbol_notes` (parses clean); the *sound* is from
convention and the producer walkthrough, not yet auditioned in FL.

## Setup (once)
1. `fl_state` first: never clobber the user's session (what is loaded, transport, bpm).
2. Add or pick a piano-like channel: `fl_channel(action="add", plugin="FLEX", name="Chords")`.
3. Pattern length matches the loop: 4 chords x 4 beats = 16 beats (default) -> `fl_pattern(action="set_len")` if not.
4. Writers with `channel_index` do the roll handshake for you (`fl_select_script` runs once per FL launch).
5. After each write: `fl_notes(action="read_steps")` shows the notes; hear them with `fl_transport(action="play")`.

## The one call
```
fl_notes(action="write_chords", text="G Bm D A", channel_index=<idx>, beats_per_chord=4, octave=4, bass=true)
```
`bass=true` adds the root an octave down (the "roots pulled down" move). `bass=false` for a thinner voicing.
Supported qualities: m, maj7, m7, 7, sus2, sus4, 7sus4, add9, 9, m9, 11, 13, dim, m7b5, slash chords
(`C/E`). **Not** supported as one symbol: a 7th *and* sus2 together (`B7sus2`): use `Bsus2` or `B7sus4`.

## Drills (play each at 80-110 bpm, loop the pattern)
| # | Mood | `text=` | Then try |
|---|---|---|---|
| 1 | Uplifting, sweet (B minor) | `G Bm D A` | add a long tonic note B (`fl_notes write_steps`, one note per bar on a second channel) |
| 2 | Groove funk (F# minor) | `F#m Amaj7 Bsus2` | `beats_per_chord=2` and a second pass with `bass=false` (compare grooves) |
| 3 | Dark cinematic | `Cm` | `beats_per_chord=16`, then add a sub-octave drone |
| 4 | Dark serious (C minor) | `Cm Cm Ab Fm Gm` (use 4 beats each; 5 chords = 20 beats, `set_len` first) | write it bare: roots only (`bass=true` and delete the thirds) |
| 5 | Pure joy (C major) | `Am F C Dm` | octave=3 for the roots, octave=5 for a top line |
| 6 | Happy (Bb) | `Gm Eb Bb F` | shorten chord 1 to 2.5 beats by writing it separately |
| 7 | Sad, neutral (A minor) | `Am G F G` | beats_per_chord=4 long, then the pivot below |
| 8 | Resolute pivot | `F G Am G` (6 7 1 7 of the same key) | compare to #7 by ear: what changed? |
| 9 | Sad, lush | `Am9 Fmaj7 Cmaj7 G7` | `beats_per_chord=8` (two-bar chords) + a tonic pedal on a second channel |
| 10 | Dreamy indie | `Am F C B` (ii-dim swapped for the major) | `beats_per_chord=2` half-note pace |
| 11 | Melancholic | `Am C Em` | add a held A on a second channel as the pedal |
| 12 | Euphoric | `Em F Am G` | double pedal: hold A and E together on a second channel |

## Humanized by default
**Chords alone only:** with a melody on top, lower the bass to about 0.55-0.65 and keep the melody loudest (`music-theory` `melody-layering.md` §4, "Balance").

`write_chords` now humanizes its output on the server (`utils/humanize.py`): lowest note strongest (about x1.15), upper
notes softer, a light upward strum (0.012 beats per voice), chords about 8% shorter than their slot, small deterministic
velocity jitter. Pitches never change. `humanize=false` gives exact grid notes (for tests or when you will edit by hand).

Do these by hand with `write_steps` + explicit `notes=` when you want more (the server never alters explicit notes):
- **Anticipate one change:** bring one chord in half a beat early (the third chord at beat 7.5) so the harmony leans into the lead.
- **Vary which voice leads**, drop an inner note on one chord, or shorten the first chord and push the next onto the upbeat.
- Keep the pitches unchanged: read back and compare to the plain `write_chords` result.

## Practice loops (what to do with each drill)
1. **Play it blind, then name the mood.** Have the chords written without looking at the table, then say which row it was.
2. **Revoice test.** Write it plain, listen, then apply the recipes in `chord-emotion.md` §4 one at a time. Note which one changed the feel most.
3. **Swap one lever.** Take #7 and swap one chord (major to minor, or add a seventh on one chord only). What mood did it move toward?
4. **Transpose.** Re-write the same drill in three keys; the mood stays, the colour of the sound does not.
5. **Same chords, other genre.** Load a beat (`fl_preset(action="load_beat", ...)`) under the drill and hear how the genre reshapes the mood.
6. **Ear drill.** Close the piano roll, have someone (or a script) pick a random drill, and name the mood and the progression.

## After practice
- Keep a short list of what worked for you in your own notes (not a new skill; `skills/README.md` rule 10).
- Pattern to remember: the mood is mostly **bass motion + minor/major mix + pedal + voicing**, not the chord names.
