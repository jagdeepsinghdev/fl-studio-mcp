# Indian classical music — swaras, thaats, ragas, tala (Hindustani focus)

Ragas are **melodic frameworks**, not just scales: a note set *plus* rules of movement,
emphasis, ornament, mood and time. Mapping a raga to a Western mode gives you the notes;
the phrases and ornaments make it sound like the raga. Facts here follow the Bhatkhande
system (the standard Hindustani textbook framework); gharanas (schools) differ in details.

## 1. Swaras (the 12 notes) — Sa is movable (Sa = your key's tonic)

| Semitones from Sa | Swara | Written | Type | Western (Sa = C) |
|---|---|---|---|---|
| 0 | Shadja | **S** (Sa) | fixed (achal) | C |
| 1 | komal Rishabh | **r** (re) | flat | Db |
| 2 | shuddha Rishabh | **R** (Re) | natural | D |
| 3 | komal Gandhar | **g** (ga) | flat | Eb |
| 4 | shuddha Gandhar | **G** (Ga) | natural | E |
| 5 | shuddha Madhyam | **m** (Ma) | natural | F |
| 6 | tivra Madhyam | **M** (Ma#, "tivra Ma") | sharp | F# |
| 7 | Pancham | **P** (Pa) | fixed (achal) | G |
| 8 | komal Dhaivat | **d** (dha) | flat | Ab |
| 9 | shuddha Dhaivat | **D** (Dha) | natural | A |
| 10 | komal Nishad | **n** (ni) | flat | Bb |
| 11 | shuddha Nishad | **N** (Ni) | natural | B |

Notation conventions vary. This file: lower case = komal; **M** = tivra Ma.
**Octaves (saptak):** mandra (low; a dot below or underline: n̲), madhya (middle), taar (high;
a dot above or ′: S′).
**Sa and Pa never change** (achal swaras); the drone (tanpura) plays Sa + Pa (or Sa + Ma,
or Sa + Ni, when the raga omits Pa).
**Shruti:** classical theory divides the octave into 22 microtonal shrutis; ragas use slightly
different intonations of the same swara (Darbari's ga is lower than Bhairavi's ga). 12-TET
synths approximate these; pitch bends/meend recover some of it.

## 2. The 10 thaats (parent scales) ↔ Western modes

| Thaat | Notes | Semitones | Western equivalent |
|---|---|---|---|
| Bilawal | S R G m P D N | 0 2 4 5 7 9 11 | Ionian (major) |
| Kalyan | S R G M P D N | 0 2 4 6 7 9 11 | Lydian |
| Khamaj | S R G m P D n | 0 2 4 5 7 9 10 | Mixolydian |
| Kafi | S R g m P D n | 0 2 3 5 7 9 10 | Dorian |
| Asavari | S R g m P d n | 0 2 3 5 7 8 10 | Aeolian (natural minor) |
| **Bhairavi** | S r g m P d n | 0 1 3 5 7 8 10 | **Phrygian** |
| Bhairav | S r G m P d N | 0 1 4 5 7 8 11 | double harmonic major ("Byzantine") |
| Purvi | S r G M P d N | 0 1 4 6 7 8 11 | (double harmonic with #4; no Western name) |
| Marwa | S r G M P D N | 0 1 4 6 7 9 11 | (Lydian b2; no common name) |
| Todi | S r g M P d N | 0 1 3 6 7 8 11 | (no Western name; ≈ "Phrygian #4 ♮7") |

Carnatic music organises all 72 heptatonic scales as **melakartas**. Hindustani Bhairavi thaat
= Carnatic **Hanumatodi** (mela 8). **Carnatic "Bhairavi" is a different raga** (from the
natural-minor mela Natabhairavi, with a ♮6 in the ascent). Always say "Hindustani Bhairavi"
when it matters.

## 3. Raga grammar (what a raga specifies)

| Term | Meaning | Producer translation |
|---|---|---|
| **Aroh / Avroh** | ascending / descending note order (may skip or zig-zag) | allowed melodic directions |
| **Varjit** | omitted note(s) | notes to avoid entirely (or in one direction) |
| **Jati** | note count: audav 5, shadav 6, sampurna 7 (e.g. "audav-sampurna" = 5 up, 7 down) | pentatonic vs full scale |
| **Vadi** | the most important note (the "king") | land phrases on it, hold it, accent it |
| **Samvadi** | the second most important (usually a 4th/5th from the vadi) | secondary resting note |
| **Pakad** | the catch phrase that identifies the raga | the "hook DNA": reuse and vary it |
| **Chalan** | typical movement / phrase patterns | stylistic phrasing |
| **Nyas** | resting notes for phrase ends | cadence notes |
| **Samay** | time of day (prahar) | mood context (morning, evening, night) |
| **Rasa / bhava** | emotion | karuna (pathos), shringar (love), bhakti (devotion), veer (heroic), shanta (peace) |

## 4. Ornaments (alankar) — what makes it sound Indian

| Ornament | What it is | How to do it in a DAW / guitar |
|---|---|---|
| **Meend** | a slow glide from one note to another (often several notes) | pitch-bend automation, portamento/glide (FL: slide notes or porta), guitar slide/bend |
| **Kan (kan swar)** | a quick grace note touching the main note | a 1/32 or 1/64 note just before, low velocity |
| **Andolan** | slow oscillation around a note (not vibrato: wider, slower) | slow pitch LFO ±20-40 cents, 1-3 Hz; famous on Bhairav's r and d |
| **Gamak** | heavy, forceful oscillation between notes | fast alternation/trill or a pitch LFO with a larger depth |
| **Murki** | a quick ornamental turn (3-4 notes) | a fast 1/32 turn: upper note, note, lower note, note |
| **Khatka** | a fast cluster of notes around a note | fast run with an accent |
| **Zamzama** | rapid repeated pairs | 1/32 alternation |

Rule: **ornaments carry the raga identity more than the notes do.** A Phrygian scale
played straight sounds Spanish; the same notes with meend and kan on re/ga sound like Bhairavi.

## 5. Performance form (useful as arrangement templates)

| Section | Hindustani (vocal/instrumental) | Arrangement analogue |
|---|---|---|
| **Alap** | slow, unmetred exploration over the drone | ambient intro, pads + solo instrument, no drums |
| **Jor** (instrumental) | a steady pulse enters, no tabla | intro with a pulse (plucks, hats only) |
| **Jhala** | fast, rhythmic climax | the build/drop before the beat |
| **Bandish / gat** | the composed piece with tabla in a tala; sthayi (theme) + antara (higher part) | verse (sthayi, lower register) + hook (antara, higher) |
| **Vilambit → madhya → drut** | slow → medium → fast laya (tempo) | tempo or energy increasing through the track |
| **Tihai** | a phrase played 3 times, landing on sam | the fill that lands on beat 1 of the drop |

## 6. Tala (rhythm cycles)

| Tala | Beats (matras) | Divisions | Theka (tabla bols) |
|---|---|---|---|
| **Teentaal** | 16 | 4+4+4+4 | Dha Dhin Dhin Dha · Dha Dhin Dhin Dha · Dha Tin Tin Ta · Ta Dhin Dhin Dha |
| **Keherwa** | 8 | 4+4 | Dha Ge Na Ti · Na Ka Dhi Na |
| **Dadra** | 6 | 3+3 | Dha Dhi Na · Dha Ti Na |
| **Rupak** | 7 | 3+2+2 | Tin Tin Na · Dhi Na · Dhi Na (sam is khali) |
| **Jhaptaal** | 10 | 2+3+2+3 | Dhi Na · Dhi Dhi Na · Ti Na · Dhi Dhi Na |
| **Ektaal** | 12 | 2+2+2+2+2+2 | Dhin Dhin · DhaGe TiRaKiTa · Tu Na · Kat Ta · DhaGe TiRaKiTa · Dhi Na |

- **Sam** = beat 1 (the strongest; phrases resolve here: X in notation). **Khali** = the "empty"
  wave section (0): Teentaal beat 9, played with open/dry strokes. **Tali** = clapped sections.
- DAW mapping: **Keherwa = a 4/4 bar of 8ths** (the pulse of most Bollywood/Punjabi pop and
  bhangra); **Dadra = 6/8**; **Teentaal** = 4 bars of 4/4 counted as one cycle; **Rupak** = 7/8.
- Tabla bols ↔ drum kit: Dha/Ge (bass, bayan) ≈ kick; Na/Ta/Tin (treble, dayan) ≈ snare/rim;
  Ti/Ra/Ki/Ta ≈ hats/fills. Dhol (Punjabi): dagga (bass side) ≈ kick, tilli (thin stick) ≈ snare/hats.

## 7. Raga Bhairavi (Hindustani) — in depth

| Attribute | Bhairavi |
|---|---|
| Thaat | Bhairavi (it is the thaat's namesake raga) |
| Notes | S r g m P d n: all four of re, ga, dha, ni komal; Sa, Ma, Pa natural |
| Western | **Phrygian** (C D♭ E♭ F G A♭ B♭) |
| Jati | sampurna–sampurna (7 up, 7 down) |
| Aroh | S r g m P d n S′ |
| Avroh | S′ n d P m g r S |
| Vadi / samvadi | **Ma / Sa** (Bhatkhande) |
| Samay | morning; by convention also the **closing raga of a concert**, sung at any hour |
| Rasa | karuna (pathos), bhakti (devotion), longing |
| Genres | thumri, dadra, bhajan, ghazal, kirtan, many film songs ("Babul Mora", K. L. Saigal) |
| Pakad (commonly taught) | m g r g, S r S, d̲ n̲ S |
| Freedom | in light-classical Bhairavi, artists freely touch all 12 notes (shuddha Re, tivra Ma…) as colour; classical renditions stay closer to the 7 |

**Phrasing that makes it Bhairavi, not just Phrygian:**
- Resting points on **Sa** and **Ma**; phrases often descend **m → g → r → S**.
- The komal **re** is approached by a meend from ga or a kan from Sa, and resolves to Sa.
  That half-step **r → S** is the emotional centre (Western: the b2 → 1 "Phrygian sigh").
- Lower-octave approach **d̲ n̲ S** (A♭ B♭ C below Sa) before settling.
- Don't run straight up and down the scale (that's the Spanish/metal Phrygian sound); use short
  motifs, repeats and returns to Sa.
- **Pa is often lightly touched or skipped in ascent** in some styles (S r g m d n S′).

### Bhairavi in C (Sa = C4 = MIDI 60; FL labels it C5)
| Swara | S | r | g | m | P | d | n | S′ |
|---|---|---|---|---|---|---|---|---|
| Note | C | D♭ | E♭ | F | G | A♭ | B♭ | C |
| MIDI | 60 | 61 | 63 | 65 | 67 | 68 | 70 | 72 |
Transpose by the key's offset (`fl-melody/references/scales.md`). For a C# Sa (e.g. over a
C# minor beat): +1 to every number.

### Guitar: Bhairavi with Sa = C (frets computed for standard tuning)
Position III (Sa = 5th string, fret 3 = C3):

| String | Frets → swara |
|---|---|
| 6 (E) | 3 = P̲ (G) · 4 = d̲ (A♭) · 6 = n̲ (B♭) |
| 5 (A) | **3 = S (C)** · 4 = r (D♭) · 6 = g (E♭) |
| 4 (D) | 3 = m (F) · 5 = P (G) · 6 = d (A♭) |
| 3 (G) | 3 = n (B♭) · **5 = S′ (C)** · 6 = r′ (D♭) |
| 2 (B) | 4 = g′ (E♭) · 6 = m′ (F) |
| 1 (E) | 3 = P′ (G) · 4 = d′ (A♭) · 6 = n′ (B♭) |

Position VIII (Sa = 6th string fret 8): 6th 8 S · 9 r · 11 g; 5th 8 m · 10 P · 11 d;
4th 8 n · 10 S′ · 11 r′; 3rd 8 g′ · 10 m′; 2nd 8 P′ · 9 d′ · 11 n′; 1st 8 S″ · 9 r″ · 11 g″.

Aroh (S r g m P d n S′):
```text
e|-----------------|
B|-----------------|
G|-------------3-5-|
D|-------3-5-6-----|
A|-3-4-6-----------|
E|-----------------|
```
Avroh (S′ n d P m g r S):
```text
e|-----------------|
B|-----------------|
G|-5-3-------------|
D|-----6-5-3-------|
A|-----------6-4-3-|
E|-----------------|
```
Pakad (m g r g · S r S · d̲ n̲ S):
```text
e|---------------------|
B|---------------------|
G|---------------------|
D|-3-------------------|
A|---6-4-6-3-4-3-----3-|
E|---------------4-6---|
```
Lower approach (n̲ S r g r S):
```text
e|-------------|
B|-------------|
G|-------------|
D|-------------|
A|---3-4-6-4-3-|
E|-6-----------|
```
Upper phrase (m P d P m · g m g r S):
```text
e|---------------------|
B|---------------------|
G|---------------------|
D|-3-5-6-5-3---3-------|
A|-----------6---6-4-3-|
E|---------------------|
```
Practice: a C drone (tanpura app, or the open low string retuned), slow (60-80 BPM or free
time), slide fret 4 → 3 on the A string for the r → S meend; bend the g (A string, fret 6)
slightly flat-to-pitch when approaching it from above.

### Bhairavi in a beat (convention, not auditioned)
- **Drone/harmony:** a Sa–Pa drone (C + G) or a Cm pad; Phrygian chords for movement:
  **i (Cm) – bII (D♭)** is the signature; also bVII (B♭m), iv (Fm), bVI (A♭). Avoid a major V
  (G major is not in Bhairavi).
- **808:** on Sa; turnaround **r → S** (D♭ → C) with a slide is pure Bhairavi.
- **Lead:** bansuri (flute), sarangi, santoor, sitar, harmonium or a vocal chop; add meend
  (glide 80-200 ms) and kan grace notes.
- **Tempo/feel:** lo-fi/ghazal 70-90 BPM (Keherwa or Dadra feel), trap 130-150 half-time,
  Punjabi pop 90-100 with a dhol pattern (`fl-genres` references).

## 8. Other ragas producers use most (Sa = C; komal = lower case)

| Raga | Thaat | Aroh / Avroh (short) | Western ≈ | Vadi/Samvadi | Time | Mood / use |
|---|---|---|---|---|---|---|
| **Yaman** | Kalyan | N̲ R G M D N S′ / S′ N D P M G R S | Lydian | G / N | early night | romantic, serene; film love songs (see the repo's `raga-yaman` preset) |
| **Bhairav** | Bhairav | S r G m P d N S′ / S′ N d P m G r S | double harmonic major | d / r | dawn | solemn, devotional; andolan on r and d |
| **Ahir Bhairav** | Bhairav (mixed) | S r G m P D n S′ | Mixolydian b2 | m / S | morning | gentle devotion |
| **Kafi** | Kafi | S R g m P D n S′ | Dorian | P / S | night (flexible) | folk, Holi, Punjabi/Sufi |
| **Bhimpalasi** | Kafi | n̲ S g m P n S′ / S′ n D P m g R S | Dorian (pentatonic up) | m / S | afternoon | yearning |
| **Bageshri** | Kafi | S g m D n S′ / S′ n D m g R S | Dorian (Pa weak) | m / S | late night | longing, romantic |
| **Khamaj** | Khamaj | S G m P D N S′ / S′ n D P m G R S | Mixolydian (♮7 up) | G / N | night | playful; thumri |
| **Desh** | Khamaj | S R m P N S′ / S′ n D P m G R G S | Mixolydian (pentatonic up) | R / P | monsoon night | patriotic, monsoon |
| **Asavari** | Asavari | S R m P d S′ / S′ n d P m g R S | Aeolian | d / g | late morning | sombre |
| **Jaunpuri** | Asavari | S R m P d n S′ / S′ n d P m g R S | Aeolian (no g up) | d / g | late morning | serious |
| **Darbari Kanada** | Asavari | S R g m P d n S′ (ati-komal g, d with andolan) | Aeolian | R / P | midnight | grave, regal |
| **Todi (Miyan ki)** | Todi | S r g M d N S′ | — (0 1 3 6 7 8 11) | d / g | morning | intense, pathos |
| **Marwa** | Marwa | S r G M D N (no Pa) | Lydian b2, Pa omitted | r / D | sunset | restless, tense |
| **Purvi** | Purvi | S r G M P d N (both Ma in practice) | — (0 1 4 6 7 8 11) | G / N | sunset | contemplative |
| **Bhupali** | Kalyan | S R G P D S′ | major pentatonic | G / D | evening | peaceful, devotional |
| **Durga** | Bilawal | S R m P D S′ | 0 2 5 7 9 (suspended pentatonic) | m / S | night | joyful, folk |
| **Malkauns** | Bhairavi | S g m d n S′ | 0 3 5 8 10 (no Pa, no Re) | m / S | late night | meditative, dark |
| **Megh / Megh Malhar** | Kafi | S R m P n S′ | 0 2 5 7 10 | S / P | monsoon | rain, longing |
| **Pahadi** | Bilawal | folk-flexible, major pentatonic core | major pentatonic + colours | — | any | folk, Kashmiri/hill songs, film |
| **Shivranjani** | Kafi | S R g P D S′ | 0 2 3 7 9 (minor with ♮6, pentatonic) | P / R | night | sad, film melancholy |
| **Kirwani** (Carnatic origin) | — | S R g m P d N S′ | harmonic minor | — | any | romantic, dramatic |
| **Charukeshi** (Carnatic origin) | — | S R G m P d n S′ | Mixolydian b6 | — | any | bittersweet |

Vadi/samvadi follow Bhatkhande; some sources and gharanas differ. Check a raga reference
before calling any of it "authentic".

## 9. Raga ↔ beat-making quick map

| Want | Raga / mode |
|---|---|
| dark, devotional trap / sad R&B | Bhairavi (Phrygian), Malkauns, Darbari |
| menacing drill | Bhairav/Todi colours (b2 + ♮7), Phrygian dominant |
| romantic, cinematic | Yaman (Lydian), Kirwani (harmonic minor) |
| Punjabi / folk / bhangra | Kafi (Dorian), Pahadi, Khamaj (Mixolydian), Bilawal (major) |
| lo-fi chill | Kafi, Bageshri, Shivranjani |
| monsoon / nostalgic | Desh, Megh |

**Harmonising ragas** (fusion practice): ragas are conceived over a drone, so keep harmony
static or slow; use only chords built from the raga's notes, and keep the vadi/samvadi strong in
the top line. Avoid chords whose notes contradict the raga's direction rules (e.g. a Pa-heavy
chord in Malkauns, which omits Pa).
