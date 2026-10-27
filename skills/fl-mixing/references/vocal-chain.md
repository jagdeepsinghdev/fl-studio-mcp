# Vocal insert chain with FL stock plugins

The effects that sit ON the vocal's own mixer track. Routing to buses and reverb/delay sends →
`references/vocal-bus-routing.md`; the master chain → `references/mastering-stock.md`.
All numbers are **from convention (two tutorials, below), not auditioned in FL** — set them, then the
owner's ears decide (we cannot hear).

Sources (private learning notes taken from these public videos; the transcripts are not in the repo):
- **TF** = TRIFREEZE, "How To Mix & Master ANY Vocals With Stock Plugins" (YouTube `dtoTIR0m0is`) —
  `vocal-mix-trifreeze.en.txt`. A full stock-plugin rap/R&B chain.
- **ITM** = In The Mix, "Vocal Processing in FL Studio" (YouTube `7OYx5Gm7O3w`) —
  `vocal-processing-inthemix.en.txt`. The bus/send system plus compressor know-how.
- **SC** = SC TUTS, "How to Get Modern Vocals in FL Studio" (YouTube `W1tgWclKqwQ`, Afrobeats lead + hook +
  backups, mostly third-party plugins) - `how-to-get-modern-vocals-in-fl-studio-vocal-mixing-and-maste.en.whisper.txt`.
  Its order and habits are below (§0b, §1b); its bus/send layout is in `vocal-bus-routing.md` §5b.

## 0. Before any plugin (TF)
1. **Clip gain first:** in the playlist, turn very loud phrases down and very quiet ones up so the
   take is roughly even. It doesn't need to be exact: the compressor does the rest.
2. **Trim dead air** between phrases; also remove coughs, clicks and breaths you don't want.
3. **Gate if needed:** Fruity Limiter → preset "Noise gate" in slot 1.
4. **Hiss under the singing = re-record.** No stock tool removes it transparently. (For separated stems,
   the offline ffmpeg denoise in `references/vocals.md` is the fallback.)
5. **Find the key** for the autotune: the 808 root of the first drop is usually the tonic
   (Edison → Regions → Detect pitch regions; or the analysis `tonal` step). Theory →
   `music-theory` skill.

## 0b. Habits from SC
- **Tune every vocal on its own insert, never on a bus:** tuners track one voice at a time; a stack confuses
  them. Copy the tuned settings to the other tracks instead (§1b).
- **Clean before you compress:** breaths, mouth clicks and background noise first (SC: RX Breath Control,
  Mouth De-click, Voice De-noise). Compression and other dynamics bring the noise back up. Stock: cut breaths
  and clicks by hand, Edison's noise removal on the clip, or the gate above.
- **Check the compressor on the most dynamic parts:** compare the loudest and the quietest section with
  it off and on; it should even them out. Too much or too little -> move the threshold only.
- **Resonance EQ starting points:** most vocals ring in similar ranges, so a saved EQ with narrow cuts in the
  usual spots, then nudged per voice and mic, saves the sweep each time (save one in Parametric EQ 2).
- **Air last:** after the de-esser, a high shelf/exciter for "excitement" (SC: Fresh Air, free; stock:
  Parametric EQ 2 high shelf, or Soundgoodizer at a low mix).
- **Fader trick:** pull the vocal fader all the way down, play the song, and bring it up slowly until the
  vocal just sits on top of the beat. Stop there.
- **Parallel compression lane:** send the lead to a new insert ("Parallel comp lead vox"), squash it hard
  (SC: an LA-2A style comp at about 20 dB of gain reduction; stock: Fruity Limiter COMP, high ratio, fast
  attack), then blend that insert in underneath. The lead keeps its dynamics; the squashed copy adds density.
- **Organise first:** link the beat to one insert and each vocal role to its own inserts (select channel,
  Ctrl/Cmd+L), leaving an empty insert between groups. It changes nothing in the sound; it makes the mix fast.

## 1. The chain, in order ("Main vocals A")
| # | Plugin | What it does | Starting point |
|---|---|---|---|
| 1 | **Pitcher** | Autotune | Key + major/minor of the beat (if unsure, try both; the wrong one is obvious). Retune speed fast for a hard effect, medium for natural. Leave gender/formant alone. |
| 2 | **Maximus**, preset "A" | Adds body: the top two bands come down | For an already deep voice, lower the low band a little. |
| 3 | **Fruity Parametric EQ 2** (#1) | Clean-up | High-pass up to the point where the voice starts losing body (plosives/rumble live below it), and remove the low-end Maximus added. |
| 4 | **Fruity Parametric EQ 2** (#2) | Remove "boxy"/muddy sound | Narrow band, boost, sweep the low-mids, cut where it sounds boxy. Scroll the wheel on a band to narrow it. |
| 5 | **Fruity Limiter** (COMP tab) | Main compressor | Ratio 3:1–4:1 (2:1 natural, up to 6:1 aggressive rap), knee ~50%, threshold down, gain back up. Attack 5–20 ms (see §2). |
| 6 | **Maximus**, preset "De-esser" | *Dynamic* harshness control, not a de-esser | Scan the top end for the frequencies that sting most and set the reduction there; it only acts when that range gets loud, so the vocal doesn't get dull. |
| 7 | **Parametric EQ 2** (#3) | Tone / style | Check more phrases for boxiness. Brighter (boost the top end) or darker (cut it) is taste. After big cuts, bring the gain back up so you compare at the same level. |
| 8 | **Fruity Limiter / Compressor** (glue) | Second, lighter compressor | Ratio about half the first (1.5–2:1), attack ~6 ms (2–5 ms = fewer S/T, ~30 ms = more natural). **Threshold must be below the vocal's peak** on the meter, or it does nothing. |
| 9 | **Patcher → "Intelligent De-Esser"** preset (press I in the preset list) | Real de-esser | "Leave highs" up fully. Sensitivity down → Inspect → move the band until you hear mostly S sounds → turn Range up → Inspect off → raise Sensitivity until the S sounds stop being sharp. |
| 10 | Parametric EQ 2 (×1–2) | Last resonance pass | Narrow boost, sweep, cut whatever jumps out. Parametric EQ 2 has 7 bands, so chain several. |

**When the 10 slots are full:** make a "Main vocals B" track, route A → B only, and continue there:
**Fruity Chorus** preset "Low enhance" with the amount almost fully down (adds width), then a final EQ
adjusted **with the beat playing**.

### Why de-ess late (TF), not first
Usually you de-ess before compression so the compressor doesn't bring the S sounds up. With a very
sibilant mic (e.g. AT2020) and heavy compression, though, S sounds an early de-esser missed come back
up later in the chain. Putting the de-esser after both compressors catches all of them. Either order is
fine: listen to which one leaves fewer harsh S sounds.

### Lighter chain (ITM)
De-ess → subtractive EQ → compressor → (remove harshness if it appears) → **exciter or saturation** to
bring back brightness and make the vocal sound open (Maximus/Soundgoodizer/Fruity Blood Overdrive as stock
stand-ins). "Less can be more": a de-esser, EQ and compressor get most vocals there. Don't de-ess so
much that the singer sounds like they have a lisp.

## 2. Compressor and EQ settings (ITM + TF)
- **Gain reduction:** aim for **3–10 dB** on the loud words. Ratio 3:1–6:1.
- **Attack** decides how much of the first consonant gets through. Too short and the start of each word
  disappears; medium-long keeps the start of each word forward and present. Harsh rap vocal → shorten it
  a little. 0 ms every time makes the vocal sound lifeless.
- **Release:** the compressor should **recover between words**. Too long and the next word starts quiet;
  too short and the vocal sounds jumpy and unnatural.
- **Output = match the input level** (makeup gain only). If the compressed version is louder, you'll
  prefer it just because it's louder, not because it sounds better.
- **Subtractive EQ technique:** narrow Q, boost ~5–6 dB, sweep, and cut any resonance you find by a
  few dB. The result is a few narrow notches. Then high-pass at **~100 Hz** (depends on the voice:
  some voices need low end *added*, not removed). Keep the EQ's range at ±6 dB so you can't over-cut.
- Always check EQ decisions on **several phrases** (resonances move), then with the beat playing.

## 1b. Copy one effect to many tracks (SC; FL UI)
Select the track that has the tuned effect, Ctrl/Cmd+Shift-click the destination tracks, open the effect's
menu > **Save preset as**, and drag the preset onto a mixer slot: every selected track gets it with the same
settings. A second copy lands on the source track; delete it. MCP: `fl_vocal("apply", recipe, track)` per
track does the same from a recipe; saving a track state is still a gap.

## 3. Ad-libs variant (TF)
Save the A chain (mixer track ▸ File ▸ Save mixer track state) and load it onto the ad-lib track,
then: + **Fruity Blood Overdrive** after the first Maximus (character), the first EQ with two cuts
in the middle of the range, + **Fruity Panomatic** (auto-pan), + a reverb *on the track itself*
(so you control its dry/wet), and route it to the shared delay.

## 4. Doing it with MCP tools
| Step | Tool | Status |
|---|---|---|
| Insert each plugin | `fl_mixer("add_fx", track, plugin="Pitcher")` | Clicks the native menu: ask the owner, FL in front, hands off; check `stray` and look at the screen. |
| Read knobs | `fl_plugin("list_params", index, slot_index=s)` | The names come from the plugin; always read before writing. |
| Set knobs by name | `fl_plugin("set_param", index, param="…", value=0–1, slot_index=s)` | Returns before/after `value_string`; refuses when a name is ambiguous. |
| A/B one plugin | `fl_mixer("fx_on", track, on=false)` → `on=true` | Verified. |
| EQ bands | `fl_mixer("set_eq"/"eq_preset", …)` | Needs controller v10.4h (see `references/eq-and-fx.md`). |
| Knobs in real units ("4:1", "10 ms", "Ping Pong") | `fl_plugin("dial", index=track, param, target, slot_index)` | Live-verified (Limiter, EQ, Pitcher, Delay 3, Reeverb 2). |
| Plugin presets ("a", "De-esser narrow-band", "Intelligent De-Esser") | `fl_plugin("restore", …)` snapshot (Maximus "a", 0.94 s) or `("preset_ui", …)` menu (Patcher, De-esser) | Live-verified; `apply` tries snapshot -> menu automatically. |
| Whole chain from a recipe | `fl_vocal("apply", recipe="vocal-clean-stock", track, [add_missing])` | Returns `misses` (knob names, preset menu items, plugin ORDER) to fix the recipe. |
| Everything in one call | `fl_vocal("setup")` | **Live 2026-10-06: empty inserts -> 0 misses, 184 s** (order, presets, knobs, routing verified). |
| Wrong plugin order | automatic inside `apply` (slot menu "Move up", verified per move) | **Live 2026-10-06: scrambled chain -> 1 move -> 0 misses.** |
| Save/load mixer track state | — | Gap (native menu only). |
| Level check | `fl_mixer("get_peaks")`, `fix_clipping` | Verified. |

## 5. The improvement loop (how recipes get good)
1. `fl_vocal("apply", recipe, track, dry_run=true)` — see what is loaded vs. missing.
2. `fl_vocal("apply", recipe, track, add_missing=true)` — inserts (clicks; ask first) + sets knobs.
3. Every `misses` entry → `fl_vocal("learn", track, slot)` writes the plugin's REAL knob names to
   `presets/vocal/knobs/<plugin>.json`; fix the recipe's `param` lists from it and re-apply.
4. A/B each stage with `fl_mixer("fx_on")`; the owner listens; move the recipe numbers.
5. Bounce, then `fl_vocal("loudness", path, reference)`. When a recipe sounds right, change its
   `status` to "auditioned <date>" — only then is it more than convention.
