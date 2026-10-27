# Screen control playbook — seeing the screen and driving the mouse

How the agent controls FL Studio's mouse-only surfaces (Edison, plugin
windows, right-click menus), written so anyone can do it the same way with
one tool: **`scripts/screen.py`** (on top of `src/fl_studio_mcp/utils/custom_menu.py`).

> **Use this last.** Prefer, in order: an MCP tool → the controller API →
> native macOS menus/panels (System Events) → *then* screen + mouse.
> The layer map is in [`UI-AUTOMATION.md`](UI-AUTOMATION.md) §1. Screen
> control is for surfaces nothing else can reach (FL's custom-drawn UI has
> no accessibility tree).

---

## 0. Setup (once per machine)

```bash
brew install cliclick                       # mouse + named keys
cd fl-studio-mcp
swiftc -O scripts/ocr_text.swift -o .generated/bin/ocr_text   # Vision OCR (Xcode CLT)
uv run python scripts/screen.py front       # prints the frontmost app
```

macOS permissions for **the terminal app you run it from** (System Settings ▸
Privacy & Security): **Accessibility** (clicks/keys) and **Screen Recording**
(screenshots/OCR). Without Screen Recording, screenshots come back as an empty
desktop and OCR finds nothing, with no error.

Coordinates are **screen points, top-left origin** (this machine: 1920×1080).
`screencapture` and `cliclick` both use points, so OCR output can be clicked
directly.

---

## 1. The loop: LOOK → READ → LOCATE → ACT → VERIFY

Do this every time. Never click a coordinate you haven't just read off the
screen: windows move, menus open in different places, and the owner uses the
machine at the same time.

```bash
S="uv run python scripts/screen.py"

$S look                         # 1 LOOK: /tmp/screen.png; open it (or Read it) and look
$S ocr --grep edison            # 2 READ: text boxes + their click centers
$S find "Edison (Master" --dim  # 3 LOCATE: center of the best match
$S click 555 544 --right        # 4 ACT
$S look                         # 5 VERIFY: did the expected thing appear?
```

Rules:
- **Look at the picture, not just the OCR.** OCR tells you *where text is*;
  the screenshot tells you *what state the app is in* (a dialog, a stray
  window, the wrong app in front).
- **One action, then verify.** Chaining blind clicks is how a menu miss ends up
  hitting an item you never meant to click.
- **`--dry-run` first** on anything new: it locates and prints, but doesn't click.

### 1b. Hints learned live (2026-10-03, NFAK session)

| Want | Do this | Why |
|---|---|---|
| **See FL while the terminal is in front** | `$S look --fl-window` | captures only FL's window (CGWindow id); no focus change, no click. Window-relative Retina pixels → for LOOKING; take click coords from a full `look` |
| Select a mixer track / open the mixer **without clicks** | `fl_ui_script(action="steps", steps=[{"call":"ui.showWindow","args":[0]}, {"call":"mixer.setTrackNumber","args":[N]}])` | in-engine calls (controller v10.4i). `setTrackNumber` moves the **insert panel** ("Mixer - Insert N") |
| Prove which track a mixer action will hit | `ui.getFocusedFormCaption` (via `fl_ui_script` `read`) or OCR the panel title | **Add ▸ Effect inserts into the panel's track, not the engine selection**: `setActiveTrack(8)` alone left the panel on Insert 7 and Reeverb 2 landed there. `select_track` now calls both |
| Press an FL hotkey (zoom, legato, octave, window F-keys, snap) | `fl_shortcut(action="run", id=..., focus=True)` / `batch` | guarded keystrokes (FL frontmost, focus proof, collisions); bare letters/digits never land - UI-AUTOMATION 3.6 |
| Focus an FL window that is already visible | hide + show it (`ui.hideWindow(w)`, `ui.showWindow(w)`) | `setFocused`/`showWindow` on a visible window, View-menu toggle, title click: no focus change (2026-10-04). Browser-stuck focus: hide Browser, hide+show rack, then target |
| Confirm where a plugin landed | its window title says `<Plugin> (Insert N)`; `fl_mixer get_info` / slot read-back | `add_fx` now reports `stray` when a plugin lands on another track |
| Close a stuck popup | `ui.escape` (in-engine) | **careful: escape also closes the focused WINDOW** (it closed the mixer) - re-open with `ui.showWindow(0)` |
| Load an effect | `fl_mixer add_fx` (clicks the native Add menu + picker) | no plugin-load API exists; `ui.showPicker(1|1,0|1,1)` opens nothing visible |

"Computer use" in this repo = these layers (`fl_ui_script` → `fl_mixer add_fx` / `screen.py`).
The desktop-app computer-use MCP tools are not connected in a terminal Claude Code session.
Before ANY click run: tell the owner, FL in front, hands off the mouse ~30 s; after it, LOOK.

---

## 2. Reading the screen (OCR)

| Situation | Command | Why |
|---|---|---|
| Big, high-contrast text | `ocr` | full screen, 1× |
| Small text: menus, buttons ("OK"), labels | `ocr --region x,y,w,h` | crops **and upscales 3×** before OCR |
| Dimmed text (unfocused window titles) | `ocr --dim` / `find … --dim` | full screen upscaled 2× |
| Just one word | `ocr --grep WORD` | filter rows |

Measured on 2026-10-01: Edison's right-click menu over a spectrogram read
"Tools" as `nnis` at 1×. At 3× in a region, every row was read correctly. The
tiny "OK" on FL dialogs is only found with a tight `--region` around the dialog.
FL's faint plugin logos (Edison's "edison", top right) need **3×**; 2× misses
them. Anchor toolbar buttons on such a logo, then **confirm with `hint` before
clicking** (the Edison send button = logo + (62, 69), hint "Send to playlist…").

**Anchor on unique text.** Locating Edison by "Edison" matched a *channel*
named "Edison Regions"; match the window title "Edison (" instead.

**OCR quirks the matcher handles for you** (`custom_menu.match_box`):
- `0` ↔ `O`: "0MCP-Workbench" is read as `OMCP-Workbench`; both sides are folded.
- Submenu arrows (`>`, `›`) are stripped.
- **Exact match wins over substring.** Looking for "Workbench" must click the
  folder `Workbench >`, not the sibling `Edit last script: 0MCP-Workbench`
  (that row opens the script in TextEdit; this happened, twice).
- Substring matching never picks `Edit …` rows, and short names (≤4 chars)
  must match exactly.

**What is this button?** Hover it and read FL's hint bar (top-left, under the
user name). It costs nothing and can't click anything:

```bash
$S hint 910 711        # -> "View regions / markers / loop"
```

---

## 3. Acting

| Goal | Command | Notes |
|---|---|---|
| Click text | `click-text OK --region 700,470,520,170` | locate + click in one step |
| Click a coordinate | `click X Y [--right] [--double]` | only coords you just read |
| Walk a custom menu | `menu X Y Tools "Run script" Workbench 0MCP-Workbench` | right-click at X,Y, then OCR-locate each level |
| Native menu bar (File/Add/…) | `menubar Add Sampler Sampler` | System Events, no OCR needed; most reliable |
| Close an FL custom menu | `dismiss` | **Esc does not close them** |
| Named key | `key esc` / `key return` / `key arrow-down` | cliclick names |
| Type text | `type edison` | US layout; fine in the plugin picker's Find field |
| Bring FL forward | `focus` | |

**Safety built in:** every click/type command refuses unless FL Studio is the
frontmost app (it tries `focus` once). Pass `--any-app` only when you mean to
drive another app.

### Walking a custom menu (the Edison example)

```bash
$S find "Edison (Master" --dim                 # e.g. 295 214 → clip center ≈ (+260, +330)
$S menu 555 544 Tools "Run script" Workbench 0MCP-Workbench
```

`menu` right-clicks, then for each level OCRs (upscaled) the area right of and
below the click, clicks the match, and waits. If a level isn't found it
**saves `/tmp/fl_menu_fail.png`, prints everything OCR saw, and dismisses the
menu safely**. Read that dump: the fix is usually a different label
("Run script", not "Scripting", which is a section header) or a wait.

In code, use `custom_menu.menu_cascade(x, y, chain, region=…)`. Pass
`region` to keep FL's own menu bar (it has a "Tools" at y≈14) out of the search.

---

## 4. Troubleshooting (real incidents, 2026-10-01)

| Symptom | Cause | Fix |
|---|---|---|
| A click "worked" but nothing happened in FL | another app (Chrome) was in front | the frontmost guard; check `front` |
| **FL ignores every click, but MCP calls still answer** | FL thinks a mouse drag is still in progress (a `dd:`/drag with no matching mouse-up) | `screen.py mouse-up`; then `key esc`, click empty grey; if FL was "Finalizing" a download, wait for it |
| The menu click hit FL's top **Tools** menu | OCR matched the menu bar's "Tools" first | restrict the region (the `menu` command does) |
| Dismissing a menu clicked a menu item ("Vocal denoiser – download?") | dismissed by clicking a window title bar that an open submenu covered | `dismiss` clicks the empty toolbar strip (1650,60) |
| Script opened in TextEdit | substring match hit "Edit last script: …" | exact-first matching (built in) |
| A window "won't move/close" | FL's plugin windows are web-docked: invisible to System Events, so `move_window` can't see them | close/move via FL itself (channel button toggles its editor); don't drag |
| OCR finds nothing at all | no Screen Recording permission (blank capture) | grant it to your terminal, restart the terminal |

**Don't drag** (`cliclick dd:/du:`) in FL unless you must. A lost mouse-up
leaves FL ignoring clicks (what happened above). If you must drag, always
follow it with `mouse-up`.

---

### Incidents 2026-10-05 (vocal-chain session) - now handled by `utils/ui_guard.py`
- **Everything says "Operation unsafe"** -> a picker, FL dialog or menu is up: `fl_connect(action="doctor")`, then `("recover")`.
- **Preset menu will not close with Escape** -> `ui.closeActivePopupMenu` (in-engine), check `ui.isInPopupMenu()`.
- **Single-letter menu items / preset names not read** -> OCR the strip zoomed 3x with ~8 px padding (`plugin_preset_ui.zoom_row`).
- **Screenshot shows the terminal, not FL** -> the owner is working: wait (idle-aware focus), never click blind.
- **FL "hangs" after preset stepping** -> queued async loads; watch `sample` + the audit log, do not pile on commands.
- **Plugin picker rows unreachable (window taller than the screen, Find under the Dock)** -> select by index (`utils/picker_index.py`), never by scrolling line by line.
- **Mixer shows only its toolbar after a restart** -> `ensure_mixer_panel` maximises it via the hint-confirmed button.
- **OCR cannot read a 1-letter label** -> verify through FL's API (knob fingerprint), not the screen.

## 5. Turning a manual sequence into code

1. Do it by hand with `screen.py`, one command at a time, `look` after each.
2. Write down which labels you matched and which waits you needed.
3. Move it into a staged script (see `scripts/edison_run.py`: `--stage N
   --until M`, each stage logs and saves a failure screenshot).
4. Read results back from the app, never assume: the Edison script reports
   `MCP-EDISON … added=331` via a dialog the driver OCRs.
5. Unit-test the logic with the OS mocked (`tests/test_custom_menu.py`
   mocks cliclick/screencapture/OCR), then promote it to an MCP tool.

Related: [`UI-AUTOMATION.md`](UI-AUTOMATION.md) (all layers, oracles, the
add-a-new-automation checklist) · `EDISON-HANDOVER.md` (the Edison flow).
