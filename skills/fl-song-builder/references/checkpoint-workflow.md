# Checkpoint workflow — build in the style of a reference, one gate at a time

Owner rule (2026-10-03): "stop at each step and check that what we build matches; even 20-30
steps with checks beat wasting time." Twice in one day a beat was built end to end before
anyone compared it (v1 Future-style: lead 3x too sparse, 808 an octave high; Levels-style v1:
piano layer 5x too sparse). Gates catch that after ONE layer.

**Rule: never build the next layer while the current gate has an open FAIL row** (fix it, or the
user explicitly accepts it — write the decision down in the recipe/handover).

## The gates
| Gate | Build | Numbers (tool) | Ears (user) |
|---|---|---|---|
| **G0** | nothing — analyse the reference | `fl_audio(action="analyze", path=ref)` → tempo, key, chord timeline, 808 root; densities/registers from a transcription if you have one (any external tool) | agree the **style sheet** (`music-theory/references/learning-from-references.md`) |
| **G1** | tempo + drums | `fl_notes(action="read_steps")` → our drum hits/bar per instrument vs the reference count | groove: solo `REF Drums` vs ours |
| **G2** | bass / 808 | our bass notes/bar, median register (octave errors FAIL here), roots vs the reference's root (`fl_audio analyze what=["note"]` on a bass hit) | weight: `REF Bass` vs our bass |
| **G3** | harmony + main layer (piano/arp/lead) | chord shares (`fl_audio analyze` chords on ref vs our export), layer notes/bar, register | vibe: `REF Other` vs our layer |
| **G4** | sounds (user picks presets) | after `fl_file export`: `fl_audio analyze` on our render vs the reference (key/chords agree, no tempo drift) | timbre |
| **G5** | arrangement (intro, drop, FX, stops) | section energy curve (per-pattern loudness) | flow |
| **G6** | mix | loudness, band balance, no clipping (`fl_mixer get_peaks`) | final listen |

## The loop at every gate
1. Build ONLY that gate's layer (recipe steps tagged with the gate — `fl_recipe apply to_step=<last step of the gate>`).
2. Verify the write (notes_added / active_steps / read-back) — mechanical correctness.
3. Compare the numbers in the table: ours from `fl_notes(action="read_steps")` (notes per bar,
   register, drum hits per row); after G3, export the pattern (`fl_file export`) and run
   `fl_audio analyze` on the render next to the reference's analysis.
4. A/B by ear with the muted REF channels (`fl-plugins/references/loading-samples.md` §4).
5. Decide: PASS → next gate. FAIL → edit the recipe step, re-apply that step only, repeat 2-4.
   Detector-limited rows (snare/hat counts, unsure chords — `music-theory/references/reading-analysis.md`)
   are decided by ear, not by the number.

## Commands (copy/paste, MCP calls)
```
fl_audio(action="analyze", path="~/refs/ref.wav")                     # G0: tempo, key, chords, root
fl_notes(action="read_steps")                                         # after each gate: what FL holds
fl_file(action="export", ...)                                         # G3+: render the pattern
fl_audio(action="analyze", path="<the exported wav>", what=["tempo","key","chords"])
```

## What a gate compare looks like (Levels-style Hook, 2026-10-03, after the piano rewrite)
| metric | reference | ours | verdict |
|---|---|---|---|
| tempo / key / top chords | 85.7 · D minor · Dm/Gm | 85 · D minor · Dm/Gm | PASS |
| bass notes/bar · median | 3.2 · G1 | 3.25 · A1 | PASS |
| layer notes/bar | 20.1 | 15.75 | PASS (was ~4/bar = FAIL before) |
| kick · hat hits/bar | 2.1 · 9.3 | 2.25 · 8.25 | PASS |
| snare hits/bar | 0.74 | 2.0 | FAIL → decide by ear (snare detector undercounts) |

## Style, not copy
The compare uses style metrics only (density, register, chord shares, drum density, band
energy) — never the reference's melody notes. Our parts are our own compositions; the reference
audio stays private in git-ignored folders and REF channels are muted/removed
before any export.
