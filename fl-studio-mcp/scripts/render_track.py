#!/usr/bin/env python3
"""Render the current FL Studio project to WAV.

**DISCOVERY-ONLY — not routine FL control.** This predates the MCP server
and drives FL directly through the shared `mcp_*.json` command files plus a
raw rtmidi trigger. CLAUDE.md hard rule 1 routes routine FL control through
the `flstudio` MCP server (and rule 3 forbids two users of that command-file
pair at once) — so do NOT run this while the MCP server is in use. It exists
only as a reference for the render flow (stop → loop=song → arm master →
record → stop → ask where the file went).

Drives FL via the MIDI bridge:
  1. stop playback
  2. set loop mode to "song" so the whole timeline plays once
  3. arm the master track (0) for recording
  4. enable recording, then start playback
  5. stop recording after the estimated track length
  6. ask FL (fl_exec_python) where it saved the file
  7. disable recording, unarm the track

Alignment caveat: this records *live playback* (FL's own audio clock), so the
recorded timing is NOT deterministic — do not use it for exactly-labelled
training renders (use training/render.py instead; see training/SOUNDBANKS.md).
Needs only the stdlib plus rtmidi for the trigger line (see the open item in
training/DEV-TASKS.md to convert this into an MCP tool).

Usage:
  python3 render_track.py [name] [pattern]

  name      project/file base name          (default: render)
  pattern   index of the pattern to render  (default: 0)
"""
import json
import pathlib
import subprocess
import sys
import time

REQ = pathlib.Path("~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/mcp_request.json").expanduser()
CMD = pathlib.Path("~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/mcp_command.json").expanduser()
RESP = pathlib.Path("~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/mcp_response.json").expanduser()


def send(action, params, timeout=4.0):
    """Write a command into FL's command queue, trigger it via MIDI, wait for response."""
    CMD.write_text(json.dumps({"action": action, "params": params}))
    time.sleep(0.15)  # let FL's controller pick it up before the trigger
    subprocess.run(
        [sys.executable, "-c",
         "import rtmidi, time; o=rtmidi.MidiOut('FL MCP trigger'); o.openPort('FL Studio MCP'); o.send_message([0x90,127,127]); time.sleep(0.1)"],
        capture_output=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if RESP.exists():
            try:
                return json.loads(RESP.read_text())
            except Exception:
                pass
        time.sleep(0.05)
    return {"error": "timeout", "action": action}


def fl_exec(code, timeout=10.0):
    return send("fl_exec_python", {"code": code}, timeout)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "render"
    pattern = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    # 0. clear any queued notes
    send("fl_stop", {})
    send("fl_clear_request_queue", {})

    # 1. learn project facts
    r = fl_exec(
        "import transport, patterns, general\n"
        "print(json.dumps({'bpm': transport.getBpm() if hasattr(transport,'getBpm') else -1,\n"
        " 'numPatterns': patterns.getNumPatterns()}))"
    )
    print("state:", r)

    # get pattern length (beats) for the target pattern
    r = fl_exec(f"import patterns\nprint(patterns.getPatternLength({pattern}))")
    try:
        beats = float(r.get("output", "").strip() or 4)
    except Exception:
        beats = 4

    # get project bpm via the real API
    r = fl_exec("import mixer\nprint(mixer.getCurrentTempo()/1000)")
    try:
        bpm = float(r.get("output", "").strip() or 120)
    except Exception:
        bpm = 120

    sec_per_beat = 60.0 / bpm
    length = beats * sec_per_beat + 1.0  # +1s tail
    print(f"rendering: pattern={pattern} beats={beats} bpm={bpm} est={length:.1f}s")

    # 2. song mode (play the timeline once, not a 1-pattern loop)
    print("loop mode:", send("fl_set_loop_mode", {"mode": "song"}))

    # 3. arm master for recording
    print("arm master:", send("fl_arm_track", {"track": 0}))

    # 4. record + play
    print("record:", send("fl_record", {}))
    time.sleep(0.5)
    print("play:", send("fl_play", {}))

    time.sleep(length)

    print("stop record:", send("fl_stop", {}))
    time.sleep(0.3)
    print("record off:", send("fl_record", {}))
    print("unarm:", send("fl_arm_track", {"track": 0}))
    print("loop pattern:", send("fl_set_loop_mode", {"mode": "pattern"}))

    # 5. find the saved file
    r = fl_exec(
        "import general, os\n"
        "d = general.getSavePath() if hasattr(general,'getSavePath') else ''\n"
        "print(d)"
    )
    save_dir = (r.get("output") or "").strip()
    print("save path hint:", save_dir)

    # most recent .wav under the FL music directory
    candidates = []
    for base in [save_dir, "~/Music/FL Studio", "/"]:
        if not base:
            continue
        p = pathlib.Path(base).expanduser()
        if not p.exists():
            continue
        for f in p.rglob("*.wav"):
            candidates.append((f.stat().st_mtime, f))
    candidates.sort(reverse=True)
    if candidates:
        newest = candidates[0][1]
        dest = pathlib.Path(__file__).resolve().parents[2] / "rendered" / f"{name}.wav"   # <repo>/rendered (wav is git-ignored)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", str(newest), str(dest)])
        print(f"RENDERED: {dest}  (from {newest})")
    else:
        print("no .wav found — check FL's Audio export folder")


if __name__ == "__main__":
    main()
