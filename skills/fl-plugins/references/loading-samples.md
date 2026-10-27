# Loading samples into FL (step by step, junior-proof)

Verified live 2026-10-03 (FL 26.1.6 PE, controller v10.4h): 6 loads, 3 failures, all three
causes below. One `flstudio` call at a time (CLAUDE.md rule 3).

## 0. Before you start
- **Hands off the mouse and keyboard** while a load runs (~5-10 s). The tool drives FL's
  native Open panel; a moving cursor made the first load fail ("the native Open panel did not appear").
- FL must be the front app; the **Channel Rack** should be visible (F6).
- Use **.wav** files. FL's own packs also contain `.wv` (WavPack) files — the tool is built for WAV.

## 1. Find a sample
| Need | Where (installed with FL) |
|---|---|
| Drum one-shots (hats, open hats, toms, rims, cymbals, cowbell, tambourine) | `/Applications/FL Studio 2026.app/Contents/Resources/FL/Data/Patches/Packs/Drums/Kits/Thrower/*.wav` |
| More drums by type (`.wv`) | `.../Packs/Drums (ModeAudio)/{Hi Hats, Claps, Snares, Percussion, Rims, Cymbals, SFX}` |
| A song's own stems / hits | from your stem separator; hits cut with `fl_audio(action="extract")` (private learning only) |
| A reference section (A/B) | cut with ffmpeg, see §4 |
```bash
find "/Applications/FL Studio 2026.app/Contents/Resources/FL/Data/Patches/Packs" -iname "*open*hat*.wav"
```

**Many samples at once:** `fl_genre("load_kit", genre=...)` loads a whole genre kit with automatic
retries (stuck panel closed, plugin windows closed between tries) and skips samples already loaded in
this FL session (`fl-genres` skill).

## 2. Load it (two calls)
```
fl_channel(action="add", plugin="Sampler", name="Open Hat")      # → {"index": 5, "mixer_track": 6}
fl_channel(action="load_sample", index=5, path="/Applications/.../Thrower/slightly open hat 1.wav")
```
Success = `{"success": true, "file": ...}`. Then give it steps (drums) or notes (pitched):
```
fl_channel(action="set_steps", index=5, pattern=1, bars=[[8],[4],[8],[4]])
```
A Sampler plays its whole sample from ONE step — that is how a long clip (a reference section)
is triggered: `bars=[[1],[],[],[]]`.

## 3. When it fails (what happened, what to do)
| Error | Cause | Fix |
|---|---|---|
| `the native Open panel did not appear` | mouse moved / another window had focus | hands off, retry once |
| `the go-to sheet did not resolve the file` | typed path lost characters in the panel's "go to" sheet | **check for a stuck panel first** (below), then retry |
| `'Load sample file' button not found in the '<name>' editor` | an earlier attempt left the **Open panel open**, covering the editor | close the stuck panel (below), retry |
| same error, same channel every time | the editor never opened: full-screen OCR garbled the small rack label ("Kick AFRO" -> "KCKATRU", 2026-10-11) so its name button was not clicked | fixed: the rack-button lookup (`rack_name_button` in the server utils) retries with a 3x-zoomed OCR of the name column + fuzzy match |

Stuck-panel check and close (native AppKit panel — synthetic keys work here):
```bash
osascript -e 'tell application "System Events" to tell process "OsxFL" to get name of every window'
# "Open sound file(s), FL Studio 2026"  → a panel is stuck. Close it:
osascript -e 'tell application "System Events" to tell process "OsxFL" to set frontmost to true' \
          -e 'delay 0.3' -e 'tell application "System Events" to key code 53'   # Escape
# re-run the window list until it shows only "FL Studio 2026" (it can take a second)
```
The panel's Cancel button is NOT reachable as `button "Cancel" of window ...` (it sits in a
split group / sheet) — use Escape. If two retries fail, ask the user to drag the file onto the
channel (that worked on 2026-10-03) and continue; note the channel then takes the file's name.

## 4. Reference track A/B (compare our beat with the original, privately)
1. Cut a section that lines up with our pattern (start on a downbeat; length = bars × 240 / BPM s):
   ```
   fl_audio(action="extract", path="~/refs/song.wav", start=<start_s>, end=<start_s + len_s>)
   # and the same window from each stem you have (drums / bass / other)
   ```
   Pick `<start_s>` on a downbeat where the bar spacing is steady (bar = 240/BPM, BPM from
   `fl_audio analyze`). Clips go to `.generated/audio/` (git-ignored) — never commit them.
2. One Sampler per clip (`REF Mix`, `REF Drums`, `REF Bass`, `REF Other`), load, one step at bar 1.
3. **Mute them** (`fl_channel(action="mute", index, muted=True)`): the user toggles to A/B; solo
   a REF channel + our matching channel to compare one layer.
4. **Mute/remove REF channels before any export** — they must never end up in a render.
