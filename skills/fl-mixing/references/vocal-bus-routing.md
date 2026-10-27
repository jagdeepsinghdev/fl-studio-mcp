# Vocal bus + send system (main vocal, reverb bus, delay bus)

How to wire the mixer so the dry vocal, the reverbs and the delays each have their own fader, can each be
soloed/EQ'd on their own, and new effects can be tried without touching the vocal's insert chain.
Insert chain → `references/vocal-chain.md`. Numbers are **from convention, not auditioned**.
Sources: ITM (In The Mix, `7OYx5Gm7O3w`) for the layout, TF (TRIFREEZE, `dtoTIR0m0is`) for the
sidechained reverb/delay and beat-bus tips (see `references/vocal-chain.md` for the transcript paths).

## 1. Layout (ITM)
```
playlist vocal clip ─► [Vocal]  (insert chain; Fruity Send ×N in its slots)
                          │ route ONLY to ─► [Vocal bus] ─► Master
                          ├─ Fruity Send ─► [Hall reverb]  ─┐
                          ├─ Fruity Send ─► [Plate reverb] ─┴► [Reverb bus] ─► Master
                          ├─ Fruity Send ─► [Delay 1]      ─┐
                          └─ Fruity Send ─► [Delay 2]      ─┴► [Delay bus]  ─► Master
```
- **3 buses:** Vocal bus (dry), Reverb bus, Delay bus. Effect tracks go **only** to their bus, never
  straight to the master; buses go to the master. Name + colour them (ITM: dark/light/lighter blue) and
  add separators so it's easy to read.
- **One "Vocal" track per vocal role** (verse, chorus, harmonies, ad-libs). Each one gets the same sends.
- **Effect tracks** = any parallel effect you want to blend in: 2 reverbs (hall + plate), 2 delays, and
  optionally a heavily compressed double or a bright, airy layer.

## 2. Wiring steps (ITM)
1. Playlist vocal → its "Vocal" insert.
2. On the Vocal track: right-click the routing arrow of **Vocal bus** → *Route to this track only*.
   Do the same for each reverb track → Reverb bus and each delay track → Delay bus.
3. From the Vocal track, *Sidechain to this track* on each effect track (makes the connection at 0 level).
4. In the Vocal track's slots add **Fruity Send** once per effect track, set each one's destination
   (rename the slot, e.g. "Send – Hall reverb", with a middle-click). Fruity Send sends **before the
   fader** and at **its position in the chain**: put it before or after the vocal's effects to choose
   whether the reverb gets the processed or the raw vocal. Muting the vocal fader doesn't stop the send.
5. On every effect track: **Dry 0%, Wet 100%.** If the dry signal is left up you get extra copies of
   the vocal, which sounds bad. ITM: Fruity Reverb 2 "Large hall"; a plate reverb you like; Fruity Delay 3 (dry down).
6. **EQ after each effect:** high-pass the reverbs (hall reverbs come out bright), maybe lift the highs a
   little. This doesn't affect the dry vocal.

Simpler version (TF): no Fruity Send. Link "Main vocals B" → a **Delay** track and → a **Reverb** track
with normal sends, the same dry 0 / wet 100 rule, and an EQ after each one.

## 3. Ducking the reverb/delay (both sources)
Put a **Fruity Limiter** on the reverb (or delay) track, COMP tab → **Sidechain** input = the vocal track's
number, a fairly high ratio, knee about halfway, **threshold very low**. The effect drops while the singer
sings and comes back up in the gaps. Delays then repeat the ends of phrases instead of blurring the
words, and Fruity Reverb sounds much cleaner. Use full-time delay only when you want that effect.

## 4. Why this layout helps
- Solo the effect tracks to hear only the reverb/delay (mute the dry vocal): too much low end?
  Do the two reverbs clash?
- One fader per family: turn all reverbs up or down without automating each track.
- Later "all the reverbs are too bright" = **one EQ on the Reverb bus** (or glue compression there).
- Keeps the vocal's own slots for de-ess/EQ/comp; the Fruity Sends use ~4 slots, which is usually fine.
- Reverb also changes how the vocal's tone comes across (TF): EQ it on its own track, and pull down any
  vocal resonance the reverb makes worse.

## 5. Make room in the beat (TF)
On the beat bus (with the beat soloed, then together with the vocal):
- **Fruity Limiter (LIMIT tab)**: ceiling just under the peaks, short attack/release/sustain → peaks
  trimmed, more room for loudness later (all at 0 = harder/more distorted; higher = cleaner).
- EQ: lower the high end a little *only* if the hats/claps are loud; lower the keys/strings where they
  clash with the vocal (or use the dynamic Maximus trick from `vocal-chain.md` §1 row 6); remove any boxiness in the beat too.
- Set reverb/delay levels **with the beat playing**, at the loudest and quietest parts of the song.

## 5b. SC variant (lead + hook doubles + backups; `W1tgWclKqwQ`)
- **Buses per family:** select the hook tracks, right-click an empty insert > Track routing > **Route
  selected to this track only**, name it "Hook bus"; the same for the backups ("Backup bus"). One fader per family.
- **Hook doubles:** tune each separately, pan the pair **hard opposite**; **Hyper Chorus** (stock) for a
  dreamy chorus, mix down a little, movement up. They can share the **lead's reverb send**, because they
  don't sing at the same time as the lead.
- **Backups:** high-pass at **~130-200 Hz** (less weight than the lead, but not thin; depends on the song),
  pan pairs opposite, a leveling compressor, breath/click/noise clean-up, and **their own reverb send**
  ("Backup reverb send") fed from the Backup bus.
- **Reverb send:** large room/hall, about **4.7 s decay, 75 ms pre-delay** (SC took both from a tempo-based
  reverb calculator for that song: recompute from the BPM, `music-theory` `rhythm.md` timing formula), an EQ on
  the return to remove reverb mud; brighter return EQ for a "trance-like" vocal.
- **Delay send:** ducked by the vocal (Fruity Limiter sidechain, §3), input raised until it is heard, a
  **"radio" EQ** (band-pass: lows and highs cut) on the return, **Fruity PanOMatic** (pan, spread) so the
  repeats move left-right, and the delay **sent into the reverb** for a wetter tail.

## 6. Doing it with MCP tools
| Step | Tool | Status |
|---|---|---|
| Route vocal → bus, effect → bus | `fl_mixer("route_only", track, to=bus)` | All other routes (master included) OFF, read back. Live-verified 2026-10-05. |
| Whole layout in one call | `fl_vocal("buses", recipe="vocal-buses", vocal, vocal_bus, reverb_bus, delay_bus, fx_tracks={"Hall Reverb": n, ...})` | Names, colours, route-only, send levels; `dry_run=true` lists the ops first. |
| Plain send at a level | `fl_mixer("sends", track, to, level)` | Verified; use this for the TF-style send layout. |
| Fruity Send / Fruity Limiter / reverb / delay | `fl_mixer("add_fx", track, plugin=…)` | Clicks; ask first. |
| Dry 0 / Wet 100, size, feedback | `fl_plugin("reverb"/"echo"/"set_param", …, slot_index=s)` | By knob NAME; read with `list_params` first. |
| Fruity Send destination, Limiter sidechain input | `fl_plugin("set_param", …)` | Unverified: `fl_vocal("learn", track, slot)` to record the knob names. |
| Name / colour of tracks | `fl_mixer("name")`, `("color")` | Built; separators remain a gap. |
| Bus levels, A/B | `fl_mixer("set_vol")`, `("fx_on")`, `("get_peaks")` | Verified. |
