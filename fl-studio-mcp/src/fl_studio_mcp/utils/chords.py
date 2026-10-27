"""Chord + bass generator for genre packs: key + Roman numerals -> piano-roll notes.

Pure music theory (no FL): the progressions in presets/genres/*.json are common,
generic shapes (i-VI-III-VII ...), not taken from any song. Theory owner:
skills/music-theory (harmony, voicing); this is the executable part.

  key        "G minor", "F# minor", "C major", "D dorian"
  numeral    i ii iii iv v vi vii (minor triad) / I II ... VII (major triad);
             suffix ° = diminished, + = augmented; quality "7" / "9" / "triad"
             adds the diatonic 7th / 9th (stacked thirds IN the scale)
  rhythm     whole | half | offbeat | stab | pulse8 (see RHYTHMS)
"""
from __future__ import annotations

import re

NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
        "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
        "Cb": 11, "Fb": 4, "E#": 5, "B#": 0}         # enharmonic spellings
MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "ionian": [0, 2, 4, 5, 7, 9, 11],
         "minor": [0, 2, 3, 5, 7, 8, 10], "aeolian": [0, 2, 3, 5, 7, 8, 10],
         "dorian": [0, 2, 3, 5, 7, 9, 10], "phrygian": [0, 1, 3, 5, 7, 8, 10],
         "harmonic minor": [0, 2, 3, 5, 7, 8, 11], "mixolydian": [0, 2, 4, 5, 7, 9, 10]}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}

#: per bar of 4 beats: (start, length) of each hit
RHYTHMS = {
    "whole": [(0.0, 4.0)],
    "half": [(0.0, 2.0), (2.0, 2.0)],
    "offbeat": [(0.5, 0.25), (1.5, 0.25), (2.5, 0.25), (3.5, 0.25)],     # house stabs
    "stab": [(0.0, 0.5), (1.5, 0.5), (3.0, 0.5)],                          # techno / dembow-ish
    "pulse8": [(i * 0.5, 0.4) for i in range(8)],                          # driving 8ths
    "sustain": [(0.0, 3.9)],                                               # 808 / sub
    "dembow": [(0.0, 0.5), (0.75, 0.5), (2.0, 0.5), (2.75, 0.5)],
}


def parse_key(key: str) -> tuple[int, list[int]]:
    m = re.match(r"\s*([A-Ga-g][#b]?)\s*(.*)$", key)
    if not m:
        raise ValueError(f"bad key {key!r}")
    tonic = NOTE[m.group(1)[0].upper() + m.group(1)[1:]]
    mode = (m.group(2) or "major").strip().lower()
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; have {sorted(MODES)}")
    return tonic, MODES[mode]


def chord_pcs(key: str, numeral: str, quality: str = "triad") -> list[int]:
    """Pitch classes (semitones above C, unbounded) of a diatonic chord."""
    tonic, scale = parse_key(key)
    m = re.match(r"^(b|#)?([ivIV]+)(°|\+)?(7|9)?$", numeral.strip())
    if not m or m.group(2).lower() not in ROMAN:
        raise ValueError(f"bad numeral {numeral!r}")
    shift = {"b": -1, "#": 1}.get(m.group(1) or "", 0)
    degree = ROMAN[m.group(2).lower()] - 1
    q = m.group(4) or ("" if quality == "triad" else quality)
    n = {"": 3, "7": 4, "9": 5}[q]
    pcs = []
    for k in range(n):                                   # stack scale thirds
        idx = degree + 2 * k
        pcs.append(tonic + scale[idx % 7] + 12 * (idx // 7) + shift)
    # the numeral's case forces the third (borrowed chords): I -> major, i -> minor
    third = pcs[1] - pcs[0]
    if m.group(2).isupper() and third == 3:
        pcs[1] += 1
    if m.group(2).islower() and third == 4:
        pcs[1] -= 1
    if m.group(3) == "°":
        pcs[2] = pcs[0] + 6
    if m.group(3) == "+":
        pcs[2] = pcs[0] + 8
    return pcs


def voice(pcs: list[int], octave: int) -> list[int]:
    """Close voicing around `octave` (C4 = 60): root lands in that octave."""
    base = 12 * (octave + 1)
    root = base + pcs[0] % 12
    return [root + (p - pcs[0]) for p in pcs]


def chord_notes(key: str, progression: list[str], bars: int = 4, rhythm: str = "whole",
                quality: str = "triad", octave: int = 4, velocity: float = 0.7,
                chords_per_bar: int = 1) -> list[dict]:
    """Notes for `bars` bars, cycling the progression; chords_per_bar 1 or 2."""
    hits = RHYTHMS[rhythm]
    notes: list[dict] = []
    span = 4.0 / chords_per_bar
    for slot in range(bars * chords_per_bar):
        num = progression[slot % len(progression)]
        midi = voice(chord_pcs(key, num, quality), octave)
        start = slot * span
        for t, d in hits:
            if t >= span and chords_per_bar > 1:
                continue
            for p in midi:
                notes.append({"midi": p, "time": round(start + t, 4),
                              "duration": round(min(d, span - t), 4), "velocity": velocity})
    return notes


def bass_notes(key: str, progression: list[str], bars: int = 4, rhythm: str = "sustain",
               octave: int = 2, velocity: float = 0.85, chords_per_bar: int = 1) -> list[dict]:
    """The chord ROOTS in the bass register, in a genre rhythm."""
    hits = RHYTHMS[rhythm]
    span = 4.0 / chords_per_bar
    out = []
    for slot in range(bars * chords_per_bar):
        num = progression[slot % len(progression)]
        root = voice(chord_pcs(key, num), octave)[0]
        for t, d in hits:
            if t >= span and chords_per_bar > 1:
                continue
            out.append({"midi": root, "time": round(slot * span + t, 4),
                        "duration": round(min(d, span - t), 4), "velocity": velocity})
    return out


# ------------------------------------------------------------------ chord SYMBOLS
# "Am F C G", "Cmaj7 - Fm9 | G7sus4", "C/E" -> notes (the FL piano-roll script
# "Text to chord progression" idea, owner's tip 4 of the "10 things" video).

#: quality suffix -> intervals above the root (semitones)
QUALITIES = {
    "": [0, 4, 7], "maj": [0, 4, 7], "M": [0, 4, 7],
    "m": [0, 3, 7], "min": [0, 3, 7], "-": [0, 3, 7],
    "dim": [0, 3, 6], "°": [0, 3, 6], "aug": [0, 4, 8], "+": [0, 4, 8],
    "sus2": [0, 2, 7], "sus4": [0, 5, 7], "sus": [0, 5, 7],
    "5": [0, 7],
    "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9],
    "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11], "M7": [0, 4, 7, 11], "Δ": [0, 4, 7, 11],
    "m7": [0, 3, 7, 10], "min7": [0, 3, 7, 10], "-7": [0, 3, 7, 10],
    "m7b5": [0, 3, 6, 10], "ø": [0, 3, 6, 10], "dim7": [0, 3, 6, 9], "°7": [0, 3, 6, 9],
    "mmaj7": [0, 3, 7, 11], "7sus4": [0, 5, 7, 10],
    "9": [0, 4, 7, 10, 14], "maj9": [0, 4, 7, 11, 14], "m9": [0, 3, 7, 10, 14],
    "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14],
    "11": [0, 4, 7, 10, 14, 17], "m11": [0, 3, 7, 10, 14, 17],
    "13": [0, 4, 7, 10, 14, 21], "maj13": [0, 4, 7, 11, 14, 21],
}
_SYM = re.compile(r"^([A-Ga-g][#b]?)(.*?)(?:/([A-Ga-g][#b]?))?$")


def parse_symbol(sym: str) -> tuple[int, list[int], int | None]:
    """'F#m7' -> (6, [0,3,7,10], None); 'C/E' -> (0, [0,4,7], 4)."""
    m = _SYM.match(sym.strip())
    if not m:
        raise ValueError(f"bad chord {sym!r}")
    root = NOTE[m.group(1)[0].upper() + m.group(1)[1:]]
    q = m.group(2).strip()
    if q not in QUALITIES:
        raise ValueError(f"unknown chord quality {q!r} in {sym!r}; known: {sorted(QUALITIES)}")
    bass = NOTE[m.group(3)[0].upper() + m.group(3)[1:]] if m.group(3) else None
    return root, QUALITIES[q], bass


def split_symbols(text: str) -> list[str]:
    """'Am - F | C, G' -> ['Am', 'F', 'C', 'G'] (separators: space , | - with spaces)."""
    parts = re.split(r"[\s,|]+|\s-\s", text.strip())
    return [p for p in (x.strip(" -") for x in parts) if p]


def symbol_notes(text: str, beats_per_chord: float = 4.0, octave: int = 4,
                 velocity: float = 0.7, bass: bool = True) -> list[dict]:
    """Chord text -> notes: each chord held `beats_per_chord`; root in `octave`
    (C4 = 60); slash bass (or the root) an octave below when bass=True."""
    notes: list[dict] = []
    for i, sym in enumerate(split_symbols(text)):
        root, ints, slash = parse_symbol(sym)
        base = 12 * (octave + 1) + root
        t = round(i * beats_per_chord, 4)
        for iv in ints:
            notes.append({"midi": base + iv, "time": t, "duration": beats_per_chord,
                          "velocity": velocity})
        if bass:
            b = 12 * octave + (slash if slash is not None else root)
            notes.append({"midi": b, "time": t, "duration": beats_per_chord, "velocity": velocity})
    return notes
