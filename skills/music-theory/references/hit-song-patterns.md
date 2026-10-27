# Hit-song patterns: what research says hits share

What studies of chart hits report about sound, structure, melody and lyrics, and how to use that
when writing. Distilled from a producer's research walkthrough ("The Scientific Way to Make Hit
Songs", youtu.be/97IK5cE1ugc, auto captions). **The study numbers below are the video's claims, not
checked against the papers**; treat them as a direction, not a formula. Form vocabulary is in
`form-and-arrangement.md`; style-vs-copying rules in `learning-from-references.md`.

## 1. The headline (and its limits)
- Algorithms trained on audio features reportedly predict Billboard Hot 100 hits **75-88%** of the time;
  people (fans, producers, even fMRI studies) guess at about **chance (~50%)**.
- Hits are **simple, repetitive, a mix of predictable and surprising, and they make you feel something**.
- What the data does not cover: marketing, social media, trends, playlist placement. A song that fits
  every number can still miss, and a song outside them can hit.

## 2. The audio features (Spotify-style descriptors, 0-1)
These are the inputs those algorithms used. Use them as a vocabulary for describing a reference and a target.

| Feature | Means | Moved by |
|---|---|---|
| **Danceability** | how easy to dance to | tempo, beat strength, how steady the rhythm is |
| **Energy** | calm vs exciting | loudness, bright/dense timbre, how busy the arrangement is |
| **Speechiness** | spoken vs sung | rap and talky vocals high; sung ballads low; podcasts near 1 |
| **Valence** | happy vs sad | major/minor chords, lyrics, instrument choice (`chord-emotion.md`) |
| **Acousticness** | raw vs produced | one voice + acoustic guitar = high; dense production = low |
| Liveness, instrumentalness | audience in the recording; no vocals | |
| Popularity | play count and recency | an outcome, not something you can write |

What the hit data showed (per the video): **valence is spread everywhere** (sad and happy songs both chart);
**acousticness skews low** (most hits are highly produced); danceability and energy sit in the middle-to-high range.
No exact target values were given; the producer averaged two datasets (about 600 songs) into ranges.

**Measuring them here:** we do not have Spotify's numbers. `fl_audio analyze`
gives tempo, key and chords (**measured**); danceability/energy/valence would be **inferred** proxies at best.
For a reference song's values, look the song up by name on a site that shows Spotify audio features.

## 3. The reference-song method
1. Pick the target genre (pop leads worldwide; hip-hop and R&B lead the US market).
2. Take the hit ranges for each feature, then **find one or two real songs that sit at each target**
   (e.g. one song for the valence target, one for energy, one for danceability).
3. Listen to those to learn what "0.6 danceability" actually sounds like, then write your own (no copying;
   `learning-from-references.md`).
4. Normally keep the references to **three or fewer**; more than that blurs the direction.

## 4. Structure: predictable + surprising (A A B A B C)
- **Pleasure = the right mix of uncertainty and surprise.** A study of tens of thousands of chords in 745
  Billboard pop songs (the captions say "880,000"; likely 80,000) found listeners like an **unexpected chord inside a simple progression**, and
  a **predictable moment inside a complex one**. So: if the loop is simple, add one surprise; if it is busy, resolve plainly.
- **Attention test (Huron's experiment with rats, as told in the video):** A A A loses attention by the
  third A; A A B keeps it. The shortest pattern that held attention throughout: **A A B A B C**.
- Map it onto a song: **A = verse, B = chorus, C = bridge** -> verse, verse, chorus, verse, chorus, bridge
  (then usually a final chorus). That is one of the most common pop layouts (`form-and-arrangement.md`).
- The same shape works inside a hook: motif, motif, answer, motif, answer, new ending
  (drill: `fl-melody/references/melody-practice.md`).

## 5. Melody
- **Melody conveys emotion more than lyrics** (per a study the video cites).
- **Hit melodies have become simpler over time**, probably because everything else got more complex:
  faster tempos, more vocal layers, better production, richer timbre. Simple line, rich production.
- Repetition of melodic patterns (and drum grooves) is part of the hook. Keep the line singable;
  put the interest in rhythm, register and one peak note (`melody-and-808.md`, `melody-layering.md`).

## 6. Lyrics (for the songwriter; Claude never copies song lyrics)
- Simpler and less complex over time; **repetition** raises "processing fluency" and chart success.
- **More rhyme** and easy readability chart higher.
- More **personal pronouns** (I, me); positive-emotion words like "love" used less; lyrics trending **angrier**.
- **Sad lyrics make sad songs sadder; happy lyrics don't make happy songs much happier** -> match lyric mood
  to a sad track; a happy track leans on the music.
- Method from the video: brainstorm a **word palette** first (simple, a bit negative, personal), then fit
  syllables to the existing melody so it stays as danceable as the references.

## 7. Checklist before calling a track finished
1. Can you name its danceability / energy / valence / acousticness target, and a reference for each?
2. Is the structure A A B A B C-like (something returns, something new arrives late)?
3. Simple loop -> where is the one surprise? Busy section -> where is the plain resolution?
4. Is the melody simple enough to hum after one listen, with production carrying the complexity?
5. Does it repeat (hook, groove, title line)?
6. Does it make you feel one clear thing?

## See also
`form-and-arrangement.md` (forms, energy curve) · `chord-emotion.md` (valence via chords) ·
`melody-and-808.md` (motif, hook) · `learning-from-references.md` (references without copying) ·
`world-and-genre-theory.md` (genre DNA)
