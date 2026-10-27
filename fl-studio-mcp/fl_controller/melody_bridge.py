#!/usr/bin/env python3
"""Melody/bass bridge: runs FL's ComposeWithLLM piano-roll script directly.

The normal path needs the user to select ComposeWithLLM in the Piano Roll
scripts dropdown and press Cmd+Opt+Y (FL only runs scripts that are
selected there). This script bypasses that: it execs the installed
pyscript in FL's own piano-roll Python (the `flpianoroll` module is
available here), so no dropdown selection and no keystroke are needed.

Usage:
  .venv/bin/python fl_controller/melody_bridge.py            # process queue + export state
  .venv/bin/python fl_controller/melody_bridge.py --notes    # also show the exported notes

Request queue: ~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/mcp_request.json
State output:  ~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/piano_roll_state.json
(both formats are identical to what ComposeWithLLM.pyscript uses, so the
existing MCP piano-roll tools keep working unchanged.)
"""
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path.home() / "Documents" / "Image-Line/FL Studio/Settings/Piano roll scripts"
PYS = SCRIPTS_DIR / "ComposeWithLLM.pyscript"

if not PYS.exists():
    src = Path(__file__).resolve().parent.parent / "scripts" / "ComposeWithLLM.pyscript"
    if not src.exists():
        print(f"melody_bridge: {PYS} not found (and no {src})", file=sys.stderr)
        sys.exit(1)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    PYS.write_bytes(src.read_bytes())

code = PYS.read_text()
ns = {}
exec(compile(code, str(PYS), "exec"), ns)

# Same entry point the Cmd+Opt+Y hotkey calls.
result = ns.get("apply")
if result is None:
    print("melody_bridge: no apply() in ComposeWithLLM.pyscript", file=sys.stderr)
    sys.exit(1)
out = result()
print("melody_bridge:", json.dumps(out) if out else "ok")

if "--notes" in sys.argv:
    state_file = SCRIPTS_DIR / "piano_roll_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        print(f"notes ({state.get('noteCount')}):")
        for n in state.get("notes", []):
            print(f"  midi={n['midi']:>3}  time={n['time']:>7.3f}  dur={n['duration']:>7.3f}  vel={n['velocity']}")
