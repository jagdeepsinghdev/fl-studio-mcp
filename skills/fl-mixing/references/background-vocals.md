# Background vocals: stacks, whispers, diction, endings

How pop producers build and blend a background-vocal (BGV) stack. From "7 secrets Charlie Puth learned
from Benny Blanco, Max Martin, Skrillex & more" (youtu.be/c6qAPklUL3E; auto captions). The tips are
**heard (artist)**, credited as he credits them; the FL steps are **convention, not auditioned**.
Lead chain: `vocal-chain.md`; buses and sends: `vocal-bus-routing.md`; stem cleanup: `vocals.md`.

## 1. The four-voice stack (Babyface's tip)
For one background line ("come on"), record:
1. **A frontal, slightly nasal take**: the clear, forward voice that carries the words.
2. **A barely audible whisper** of the same line.
3. **A slightly noisier, breathier whisper** (half falsetto, "morphing your voice to support the
   other vocal").
4. Optionally one more take; the stack then "sounds like a crowd".

Then on the whispers: **one EQ band, a high-pass**, so they are only air. **Group** the stack, turn it
down and blend it under the lead. Compare with and without: the line sounds bigger without sounding louder.

**In FL:** one mixer insert per take, all routed to one BGV bus (`fl_mixer route` / `route_only`, then
`fl_mixer name` the bus). Whisper inserts: Parametric EQ 2 with the low cut high
(`fl_mixer("eq_preset", track, "high_pass_ish")`; needs controller v10.4h). Balance with
`fl_mixer set_vol` on the bus.

## 2. Thin the harmonies, add grit
- **Take lows out of a harmony** so it is thinner than the lead and doesn't cloud it (one tutorial's
  number: high-pass backups at ~130-200 Hz; pan pairs opposite; `vocal-bus-routing.md` §5b).
- **A little grit goes a long way:** a lo-fi/sample-rate plugin (AIR Lo-Fi; "you can hear this on a lot of
  Ariana Grande records") at a low amount on the vocals. FL stock: **Fruity Squeeze** or **Distructor**,
  low mix (`fl-plugins` `sound-craft.md` §4).

## 3. Diction: make split words readable
- When a word is split over notes, **over-pronounce** it so it doesn't get "lost in the sauce".
- **Over-smile while singing** (Ross Golan's tip): it pushes up the high-end sibilance, so consonants
  cut through. Then fix only harsh esses in the mix (de-esser, `vocal-chain.md`).

## 4. Tiny fades on every vocal clip
- Adjust each clip's end with a **minuscule fade** so tails don't click or bleed (the same habit as one note
  at a time, `fl-plugins` `sound-craft.md` §1). In FL: Edison fade, or the audio clip's declick setting.

## 5. End it unexpectedly
- **Cut the song off at the end a little early**, where it feels unexpected (a collaborator's tip; captions
  name them "L Bell"): the listener feels they missed something and plays it again (like the cut to black
  at the end of *The Sopranos*). Theory of endings and transitions: `music-theory` `form-and-arrangement.md`.

## Checklist
1. Is the BGV line a stack (front + two whispers), grouped on one bus and tucked under the lead?
2. Whispers high-passed to air only? Harmonies thinner than the lead?
3. Can every split word be understood?
4. A tiny fade on every clip end?
5. Does the ending leave the listener wanting the replay?
