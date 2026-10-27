# Song sections — multiple patterns (Intro / Verse / Chorus)

- `fl_state` — named patterns (number, name, length) + which is active. Untouched slots are
  *default* and do not exist yet.
- `fl_pattern("create", name=…, [length_beats], [color])` — create in the first free slot.
  It does **not** switch to it.
- `fl_pattern("select", pattern=N)` — make an existing pattern active (step sequencer +
  piano roll write here). Refuses patterns that don't exist.
- `fl_pattern("clone", pattern=N, [name])` — copy a pattern (notes + steps) into the next
  slot; the clone becomes active and **later patterns shift up one number** — re-read
  `fl_state`.
- **Never select/jump to an empty pattern by other means** (a `jumpToPattern` via the gated
  `fl_exec_python`): FL opens a modal "Pattern N name" dialog and every MCP call times out
  until a human closes it.
- When to use: any song with more than one section, or when a variation should not overwrite
  the loop you already built. Pattern 1 is enough for a single loop.
- Label sections on the playlist timeline with a marker. **Markers are a documented coverage
  gap** (no domain action yet — the legacy `fl_add_marker`/`fl_list_markers` are only behind
  `LEGACY_TOOLS=1`). Markers are add-only: the API cannot delete/rename a marker, so add each
  once (bar N starts at beat (N-1)*4 in 4/4).
- **`chain` and step-only sections (2026-10-11):** `fl_pattern("chain")` now accepts sections that have only
  step-sequencer rows (drums, a Sampler loop; no roll notes needed), copies each hit's velocity and shift,
  and selects each section before reading its rows (a live read used to return the ACTIVE pattern for
  every section: the kick landed in the intro). It still refuses a section with no notes AND no steps.
- **Multi-bar beat presets:** a beat preset's rows may be 1-4 bars (16/32/48/64 steps; `velocities`/
  `shifts`/`repeats` the same length), and `load_beat(fill=false)` writes longer rows (e.g. 320 steps =
  20 bars) as given. Concatenating the section rows into one preset is the most reliable way to write a
  whole song's drums into one pattern; then audit per-section hit counts (`build-around-a-sample.md` §9).
- `getGridBit` (and so a quick audit) counts only unshifted steps; a shifted hit is not on the grid.
- Not possible: putting patterns on the playlist. There is no playlist-clip API, so sections
  are auditioned one pattern at a time (`fl_pattern("select")` + `fl_transport("play")` in
  pattern loop mode).

## Multi-section workflow
1. `fl_pattern("create", name="Intro", length_beats=8)`, `("create", name="Verse",
   length_beats=16)`, `("create", name="Chorus", length_beats=16)`; check with `fl_state`.
2. For each pattern: set its drum steps (`fl_channel("set_steps", …, pattern=N)`) or load a
   beat preset; select the piano channel; write the melody
   (`fl_notes("write_steps", …, target_pattern=N, open_roll_verified=True)`); then trigger
   the script and confirm with `fl_notes("read_steps")` **before** moving to the next
   pattern — queued notes are applied to whichever pattern is active when the script runs.
3. `fl_transport("set_bpm")` for tempo (swing is a coverage gap), then
   `fl_pattern("select", pattern=N)` + `fl_transport("play")` to audition each section.
4. **A A B A B C layout** (`music-theory` `hit-song-patterns.md` §4): only three patterns are needed,
   "Verse" (A), "Chorus" (B), "Bridge" (C, new chords). Make A thinner than B (addition/subtraction,
   `form-and-arrangement.md`), and give the second verse one small change (a hat variation or a
   counter-melody), so it is a clone (`fl_pattern("clone")`) rather than a fourth new idea. There is no
   playlist API, so the order Verse, Verse, Chorus, Verse, Chorus, Bridge is auditioned by selecting
   patterns in turn (or placed on the playlist by hand).
5. Status: the pattern + step + note tools are verified live; the full multi-pattern melody
   flow above has not been run end to end (it needs the ComposeWithLLM click).
