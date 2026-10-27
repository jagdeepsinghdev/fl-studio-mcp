#!/usr/bin/env python3
"""R3 / S4.2 / L16: the Edison flow from the command line.

Same steps as the fl_edison MCP tool (both call utils/edison_flow.py):
  1. open             — Add ▸ Effect ▸ More plugins… → double-click Edison
  2. load_regions     — the generic 0MCP-Workbench script loads --clip and
                        stamps one region per hit in --hits (OCR'd reply)
  3. send_to_channel  — Edison's send button → the --channel Sampler; the WAV
                        FL writes is parsed (regions) and copied to --out

Usage (from fl-studio-mcp/):
  uv run python scripts/edison_run.py --channel 5                 # all steps
  uv run python scripts/edison_run.py --stage 2 --until 2         # regions only
FL must be frontmost; don't touch the mouse while it runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fl_studio_mcp.utils import custom_menu as cm  # noqa: E402
from fl_studio_mcp.utils import edison_bridge as eb  # noqa: E402
from fl_studio_mcp.utils import edison_flow as flow  # noqa: E402


def log(msg: str) -> None:
    print("[edison]", msg, flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", type=int, default=1, help="first step (1-3)")
    ap.add_argument("--until", type=int, default=3, help="last step (1-3)")
    ap.add_argument("--clip", required=True, help="the audio to load into Edison")
    ap.add_argument("--hits", default="",
                    help="optional hits JSON (onset list) -> one Edison region per hit")
    ap.add_argument("--max-ms", type=float, default=300.0)
    ap.add_argument("--channel", type=int, default=None,
                    help="Sampler channel index (default: the selected one)")
    ap.add_argument("--out", default=".generated/edison/regions.wav",
                    help="where the region-marked WAV is saved (git-ignored)")
    a = ap.parse_args(argv)
    regions = eb.regions_from_json(Path(a.hits), max_ms=a.max_ms) if a.hits else []

    steps = {
        1: ("open", lambda: flow.open_edison(sink=log)),
        2: ("load_regions", lambda: flow.load_regions(a.clip, regions, sink=log)),
        3: ("send_to_channel", lambda: flow.send_to_channel(
            channel=a.channel, out=a.out, expected=len(regions) or None, sink=log)),
    }
    for n in range(a.stage, a.until + 1):
        name, fn = steps[n]
        log(f"{n}/3: {name}")
        res = fn()
        log(f"step {n} -> {'OK' if res['ok'] else 'FAILED: ' + str(res.get('error'))}")
        if not res["ok"]:
            cm.shot("/tmp/edison_fail.png")
            log("failure screenshot: /tmp/edison_fail.png")
            return 1
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
