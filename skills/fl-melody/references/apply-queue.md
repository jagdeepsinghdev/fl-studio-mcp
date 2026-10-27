# FL Studio — Apply a Melody (Drain the Queue + Play)

Melody notes written via `fl_notes("write_steps", …)` (or a preset's note list) are
**queued**, not written. They only land when the **ComposeWithLLM** piano-roll script is
the *selected* script. This is the reliable path to make them land and play.

## Read first
`CLAUDE.md` (repo root) — sections 0 (this gotcha), 2 (timing), 5 (API facts).

## Why it often "doesn't work"
- `fl_notes("write_steps")` "succeeds", but `fl_notes("read_steps")` returns
  `note_count: 0` (or only a few old notes). Cause: **ComposeWithLLM is not the
  selected piano-roll script** — FL resets it to the default on **every launch**.
- The selection lives in a **web-rendered dropdown** (the wrench) with **no AX tree and
  no API** — but it is now **automated by `fl_select_script(channel_index=<target>)`**
  (OS-level coordinate clicks, the only layer that reaches it). **No manual click
  needed.** If a write still returns 0 after `fl_select_script`, the coordinates missed
  (layout shifted) — the tool tells you how to pass explicit `wrench_x`/`script_x`/`script_y`.
- The trigger is the keystroke **Cmd+Opt+Y** (macOS) / **Ctrl+Alt+Y** (Windows), which
  runs whatever piano-roll script is currently selected.

## Steps

1. **Confirm what's queued vs what's in the roll:**
   ```
   fl_notes("read_steps")        # what's actually in the pattern right now (mtime-guarded)
   ```
   Read `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/mcp_request.json`
   for what's waiting to be written. If the roll has few/old notes but the request file
   has many, the queue is not being drained.

2. **Select the script (automated):**
   ```
   fl_select_script(channel_index=<target>)     # opens the roll + picks ComposeWithLLM
   ```
   Re-run after each FL launch. If it reports the selection didn't take, follow its
   `wrench_x`/`script_x`/`script_y` hint (see `piano-roll-setup.md`).

3. **Drain the queue** — one of:
   ```
   # auto-trigger is on by default (write_steps sends Cmd+Opt+Y for you); if it didn't
   # land, bring FL to the front and trigger again:
   osascript -e 'tell application "FL Studio 2026" to activate'
   # or, from the terminal (auto-sends Cmd+Opt+Y and reports note count):
   fl-studio-mcp/apply-melody.sh
   ```

4. **Verify it landed** (must span the full phrase, not just bar 1):
   ```
   fl_notes("read_steps")
   ```
   Check `note_count` matches what you queued AND the notes span the expected beat range
   (e.g. a 5-bar melody should have notes out to ~beat 20, all ticks not crammed into bar
   1). If `note_count: 0` → the script still isn't selected.

5. **Set tight timing, then play:**
   ```
   fl_pattern("set_len", pattern=1, beats=<phrase beats>)   # match the phrase (e.g. 20 for 5 bars)
   fl_transport("set_bpm", bpm=<bpm>)                       # real tempo
   fl_transport("loop", mode="pattern")
   fl_transport("play")
   ```

## If it still doesn't sound right
- **Hears only 2-3 beats then silence:** notes are crammed into bar 1 → the queue wasn't
  drained (script not selected) OR `fl_pattern("set_len")` too short. Re-check the note
  tick range in `fl_notes("read_steps")`.
- **Right notes but wrong feel:** it's a **mix** problem, not a notes problem — raise the
  lead channel, duck the drums/chords (`fl_mixer("set_vol", …)`), so the melody sits on top.
- **BPM feels off:** `fl_transport("set_bpm")` sets real tempo; if a beat loader applied a
  speed multiplier, reset `fl_transport("set_speed", speed=1.0)`.

## Note
The **beat** (step sequencer) works with zero setup — only **piano-roll melody/chord
notes** need the ComposeWithLLM script selected.
