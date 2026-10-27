# Learning from a reference track (without copying it)

The goal is to learn the *style* and write your own *song*. Copying a sample, a melody or a
distinctive 808 line is copying, even if you replay it.

## Style (fine to take) vs expression (write your own)

| Take freely (style) | Write your own (expression) |
|---|---|
| tempo and feel (122 BPM, half-time) | the melody's notes plus rhythm |
| key and mode (C# minor, dark) | the exact 808 line / turnaround |
| harmonic idea (one-chord drone, i–VI) | a recognisable riff or hook |
| drum grid conventions (snare on 3, 1/8 hats, rolls) | samples cut from the song |
| form and bar counts | the producer tag, vocal chops |
| sound palette types (bells, flute, distorted 808) | the exact preset/sample chain if it is distinctive |
| mix approach (loud 808, dark lead, wide hats) | |

Chord progressions and drum grids are shared vocabulary: nobody owns i–VI or a snare on 3.
A melody is protectable.

## Transformation checklist (run before writing notes)
1. **Different motif rhythm.** Tap a new rhythm; don't start from theirs.
2. **Different contour.** If theirs goes up, try down or an arch.
3. **Different turnaround.** Same idea (walk into the root), different notes and timing.
4. **No 4+ note run in common** with the reference in the same rhythm. Compare your MIDI against
   the reference's melody (a transcription, or by ear): intervals, not absolute notes.
5. **Own sounds.** Pick bells/flute/808 from your library, not the stems.
6. **Change at least one style axis** as you get comfortable: tempo ±5, another minor key,
   add a chord change, swap the lead instrument.

## Privacy rules
- Use audio you own or may use (your own, CC-licensed, bought sample packs). Song-derived
  files from anything else are for **private learning** only: never commit or share the
  audio, stems, renders or samples; keep them in git-ignored folders.
- Analysis gaps get written down next to the style sheet, not "fixed" in the data.

## The analysis calls
```
fl_audio(action="analyze", path="~/refs/<name>.wav")    # tempo (+ agreement), key, chords, gaps
fl_audio(action="extract", path=..., start=32, end=48)  # cut the section you study
fl_audio(action="analyze", path=<a bass hit>, what=["note"])   # the 808's root note
```
Stems, beat grids and note transcriptions need an external tool (a stem separator, a
transcriber); everything below works without them, by ear where a number is missing.

**A producer/artist breakdown video (what they SAY, not the audio):** take notes, or use the
platform's captions. Distil the ideas into a reference here, never copy lyrics.
Then apply `reading-analysis.md` and write a **style sheet**:

```
Reference: <title> (private learning)
Tempo/feel:    122 BPM, half-time (snare once per bar)        [measured+inferred]
Key/mode:      C# minor (aeolian)                             [inferred; detector said G# major]
Harmony:       one-chord drone, i                              [measured]
808:           root-heavy, turnaround at phrase end            [measured notes]
Drums:         snare beat 3, 1/8 hats, kick follows the 808    [hats/kick inferred]
Form:          1-bar intro, 4-bar loop ×7, short end           [measured]
Palette:       <ask user: lead instrument? hat rolls? FX?>     [heard (user)]
My version:    <what I'll change: key? a chord? the lead sound? the form?>
```

## Ear-training drills
Run them with the user: `ear-training.md` §8 (producer drills) and §6 (transcription order).
