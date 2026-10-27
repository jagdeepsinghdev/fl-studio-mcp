# Trap in FL Studio

> Trap theory (harmony, 808 writing, hat language): `skills/music-theory/references/world-and-genre-theory.md` §1, `skills/music-theory/references/melody-and-808.md`, `skills/music-theory/references/rhythm.md`.

Read `fl-studio` for the tool map and `fl-setup` if a call times out. Verify the connection first (`fl_state` must return a position).

**Tempo:** 140 (half-time feel; many producers work at 70) BPM. Use `fl_transport("set_bpm")(<target BPM>)` to set the real tempo (the toolbar box updates). It's the only reliable tempo lever; `fl_transport("set_speed")` only plays faster/slower without changing the BPM.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` argument for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 8, 11 | `[true, false, false, false, false, false, false, true, false, false, true, false, false, false, false, false]` |
| Snare | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Clap | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Closed/open hat | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | `[true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true]` |

**Feel:** Half-time: the snare/clap lands on step 9 only. Kick is syncopated and sparse so the 808 bass can breathe. Hats run 16ths; add rolls by doubling density on steps 13-16.

**Swing:** `fl_transport  # swing (gap)(x)` sets FL's *global* swing (0.0–1.0). Keep it straight (`0.0`); use hat rolls for movement instead. Its scale vs. the MPC-style percentages above is not calibrated: start there, listen, adjust; `fl_state  # swing (gap)` reads it back.

## Steps

1. `fl_state` and map channels by **name** (Kick, Snare/Clap, HiHat). Indexes are 0-based. Don't assume the order.
2. For each part with steps: `fl_channel("set_steps")(channel, pattern)` using the row above. Skip parts marked (none) or clear them by sending 16 `false`.
3. Read each channel back with `fl_channel("get_steps")` and confirm it matches before playing.
4. `fl_transport("loop")("pattern")`, then `fl_transport("play")`. Tell the user what you set, then adjust by ear together.
5. Mix: `fl_channel("set_vol")` (0-1) / `fl_channel("set_pan")`. Kick/808 loud and centred; snare + clap layered (clap slightly lower); hats about 30% lower than snare, panned a little off-centre. Keep the low end mono.

## ⚠️ Phrase length sync (read before building anything)

Set the pattern length **before** writing any melody/bass/chord notes, and make
the drum loop, every piano-roll phrase, and the pattern share **one phrase
length L** (multiple of 4 beats). Details: **`fl-studio-mcp/presets/README.md`
→ "The one golden rule"**. Example: the `drill` beat preset (4-beat bar) pairs
with the `drill-c-minor` melody preset (8-beat phrase, `length_beats: 8` in
both files) — one `fl_channel("set_steps")("drill")` + `fl_notes("write_steps")("drill-c-minor")`
builds a fully in-sync loop.

## Variations
**Key/scale:** typically F#, G or A minor; harmonic minor / minor pentatonic, dark & sparse. For exact MIDI notes, chord formulas and progressions read `fl-melody` → `references/scales.md`.


Thin the hats (8ths) for verses, full 16ths + rolls for the hook. Drop the kick on step 8 for a lighter variant. Melody: dark minor, sparse.

## Beginner piano trap beat (walkthrough, 8 bars)
From Lollypopbeatz, "How To Make Beats For BEGINNERS (FL Studio)" (youtu.be/WKlBTH1aXlc; transcribed with
Whisper). Producer steps are **heard (tutorial)**; numbers are **convention, not auditioned**.

| # | Her step | Our call / status |
|---|---|---|
| 1 | Empty project, **150 BPM** | `fl_transport("set_bpm", bpm=150)` |
| 2 | **FL Keys** piano, a simple 4-bar idea; copy it to 8 bars (notes never past bar 9) and change **one or two notes** in bars 5-8, so it is less repetitive | `fl_channel("add", plugin="FL Keys", name="Keys")`, `fl_pattern("set_len", beats=32)`, `fl_notes("write_steps", ...)` with explicit `notes=` |
| 3 | **High-pass every non-drum sound**: Parametric EQ 2, band 1 order "steep 8", cutoff ~100 Hz | `fl_mixer("add_fx", track, plugin="Fruity Parametric EQ 2")` then `set_eq`/`eq_preset "high_pass_ish"` (v10.4h) |
| 4 | A **FLEX pad** under the piano (her pick: "Haunting Hour"): one long note per half, ended where the next piano note starts (ghost notes show where); turn the patch's reverb/delay and release down so tails don't smear; high-pass it too (it also removed a click) | `fl_channel("add", plugin="FLEX")`, `fl_plugin("find_preset", index, query="Haunting Hour")`, `fl_plugin("echo"/"reverb", ...)` |
| 5 | **Clap on step 9** (beat 3), full volume | `fl_channel("set_steps")` with the Clap row above |
| 6 | **Hats:** step-sequencer right-click > *Fill each 2 steps* (8ths), then **rolls** in the piano roll with short notes (a quick triplet after the third hit), the bar copied across | 8ths = `steps=[1,0]*8`; rolls = `fl_notes("write_steps", channel_index=<hat>, notes=...)` |
| 7 | A **filler snare** on an off-beat for bounce, same place in each half | one extra step / note |
| 8 | **808** (Spinz-style): Sampler envelope **all down except Hold full** (a square: no fade), saved as an envelope preset "808"; **Cut itself** on, so a new 808 note stops the last one | **gap**: no MCP action for the Sampler envelope or Cut itself; set once in FL and save the channel preset |
| 9 | **Fruity Soft Clipper** on the master, slot 10, default settings: "makes it hit hard" | `fl_mixer("add_fx", 0, plugin="Fruity Soft Clipper")` (clicks; ask first) |
| 10 | 808 notes on the **piano's notes** (in key; here C), long notes, velocity max then the **channel volume** down; slice one note with the slice tool for a bouncy second hit | `fl_notes("write_steps", channel_index=<808>, notes=...)`; `fl_channel("set_vol")`; 808 theory: `music-theory` `melody-and-808.md` |
| 11 | **Arrange:** playlist > pattern > *Split by channel*, song mode; intro = piano only, then everything; cut the drums for the last beat(s) before the drop | no playlist API (gap): one pattern per section + `fl_pattern("chain")`, `fl-patterns` `sections.md`; drop-out = `music-theory` `form-and-arrangement.md` Transitions |
| 12 | **Save constantly** (Ctrl+S after every change) | `fl_file(action="save")` (a new project needs a name first). Learned the hard way 2026-10-11: an unsaved session was lost when FL closed |

Her closing advice: practise by copying a tutorial exactly, then watch advanced producers work without explanations.

## Drill/trap with guitar — 4-bar session recipe (2026-09-29)

Built end-to-end with MCP tools only: 140 BPM, 16-beat pattern, guitar riff
(Am–F–C–G, 8 eighth-notes/bar, MIDI in the `fl-melody` skill) + per-bar drums.

```
fl_transport("set_bpm")(140); fl_transport("set_speed")(1.0)
fl_pattern("set_len")(1, 16)                 # 4 bars
fl_channel("add")("FLEX", "Guitar")        # new channel (index 5 here)
# drums: pass a 64-step array (4 bars x 16) — the tool accepted it
fl_channel("set_steps")(0, <64 bools>)          # kick  bar1 1,7,12 | bar2 1,8,11 | bar3 1,7,15 | bar4 1,6,11
fl_channel("set_steps")(3, <64 bools>)          # snare 9 | 13 | 9 | 13
fl_channel("set_steps")(2, <64 bools>)          # hat odd steps; bar4 also 14,16
fl_channel("set_steps")(1, [false]*64)          # clap off
fl_state  # + a channel select(5)                     # THEN verify (see gaps), THEN
fl_notes("write_steps")(<32 guitar notes>, mode="replace")
```



### FAST PATH
Use the song-builder tools — full templates, chords/bass/multi-instrument examples and
clean-drums steps live in **`fl-song-builder`** (agent guide: `fl-studio-mcp/AGENT-SONG-BUILDER.md`).
This drill riff is one call: `fl_batch  # many actions in one trip(bpm=140, bars=4, melody_channel="Guitar", drums={...}, melody=[...])`.

#### Manual version (same result, tool by tool)

### EASY CHECKLIST — drums + guitar together (follow top to bottom, one call at a time)

Skills used: **`fl-genres`** (this one: drums + whole recipe) → **`fl-melody`**
(guitar notes; `references/apply-queue.md` if notes don't appear).
Every step is an `flstudio` MCP tool. Never run two at once.

| # | Do this | MCP tool | Check it worked |
|---|---|---|---|
| 1 | See what is in FL first | `fl_state`, `fl_state` | list shows channels; note if playing |
| 2 | Set tempo | `fl_transport("set_bpm")(140)` then `fl_transport("set_speed")(1.0)` | reply says "BPM set to 140.0" |
| 3 | Make the loop 4 bars | `fl_pattern("set_len")(1, 16)` | `fl_pattern("set_len")(1)` = 16 |
| 4 | Add a guitar channel | `fl_channel("add")("FLEX", "Guitar")` | reply gives its `index` (e.g. 5) |
| 5 | Drums: kick, snare, hat, clap | `fl_channel("set_steps")(channel, 64 true/false)` x4 | reply says `N/64 active` |
| 6 | **User:** pick "ComposeWithLLM" in the piano-roll dropdown (once per FL launch) | (manual) | — |
| 7 | Select ONLY the guitar | `fl_state  # + a channel select(index)` | `fl_state`: only Guitar `is_selected: true` |
| 8 | Write guitar notes | `fl_notes("write_steps")(notes, mode="replace")` | `fl_notes("read_steps")`: 32 notes, beats 0-16 |
| 9 | Loop and play | `fl_transport("loop")("pattern")`, check `fl_state`, then `fl_transport("play")` | `is_playing: true` |

Wrong channel got the notes? `fl_notes("clear")` first, fix step 7, redo step 8.
Want only drums? Do steps 1-5 and 9. Want only guitar? Do steps 1-4 and 6-9.

### Gaps found (read before repeating)
1. **Notes landed on the wrong channel.** `fl_state  # + a channel select(5)` said
   "Guitar selected" but `fl_state` still returned the 808
   (index 4); notes went into the 808 twice. **Always** check
   `fl_state` (only the target has `is_selected: true`) *before*
   `fl_notes("write_steps")`. If wrong: `fl_notes("clear")` (clears the *open* channel),
   fix selection, rewrite.
2. **Drums were 1 bar in a 16-beat pattern** (grid defaults to 16 steps). Fix:
   write a 64-step array. `fl_channel("set_steps")` reports `N/64 active`, but
   `fl_channel("get_steps")` read-back only returns the first 16 steps — bars 2–4
   are **unverified by read-back** (confirm by ear / piano-roll view).
3. **`fl_transport("play")` is a toggle** — check `fl_state` first or you
   pause a running loop.
4. **The 808 channel's name kept changing** (Astronomic → Growler → Heavy Atom →
   Rumbler → Behemoth) after script triggers/selection calls. Cause unknown
   (something is cycling its preset). Match channels by **index**, re-list
   with `fl_state` after every trigger.
5. **FLEX "Guitar" is not a guitar sound by default** — use
   `fl_plugin  # find_preset (gap)(index, "guitar")` / `fl_plugin  # list_presets (gap)(index)` (name lookup
   by stepping; walks back if no match). None found = no guitar content in FLEX.
   The user may edit the rack live: re-list channels before index-based calls.
6. **Not done:** 808 root line (A F C G) and slides (`fl_notes("write_steps")  # 808 slide notes`).

### Clean the drum section (start over)
Sequential calls only (never parallel). Clear all four drum rows, 64 steps each:
```
fl_channel("set_steps")(0, [false]*64)   # 808 Kick
fl_channel("set_steps")(1, [false]*64)   # 808 Clap
fl_channel("set_steps")(2, [false]*64)   # 808 HiHat
fl_channel("set_steps")(3, [false]*64)   # 808 Snare
fl_channel("get_steps")(<ch>)            # spot-check (first 16 only)
```
Or reset in one call with a preset: `fl_channel("set_steps")("drill")` — it clears all
drums first, then writes 1 bar and sets BPM (re-run `fl_transport("set_bpm")(140)`,
`fl_transport("set_speed")(1.0)`, and `fl_pattern("set_len")(1, 16)` after).
Clear the guitar separately: select it, then `fl_notes("clear")`.

## Caveats

- Patterns are the standard conventions for the genre, written from music knowledge. They were **not** auditioned in FL by the assistant; expect to tune by ear.
- Persistent notes need the step sequencer (`fl_channel("set_steps")` / `fl_channel("set_steps")  # one bit`). `fl_channel  # real-time trigger (gap)` is real-time only.
- Melody/bass: use the `fl-melody` skill (piano roll + ComposeWithLLM). It works; the script must be re-selected in the piano roll toolbar each FL session.
- Ask before overwriting a pattern the user may have made: read it with `fl_channel("get_steps")` first.
