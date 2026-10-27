"""L16 / S4.2: fl_edison — Edison regions into a Sampler, one MCP call.

Actions (live-proven 2026-10-01; mechanics in utils/edison_flow.py):
  status           is an Edison window visible? (read-only, OCR)
  open             open Edison on the selected mixer insert (skips if open)
  load_regions     load `clip` and stamp one region per onset from
                   `hits_json` (analysis drums.json) — or `regions` given
                   directly — via the generic 0MCP-Workbench script
  send_to_channel  clip + regions replace channel `channel`'s Sampler sample;
                   returns the WAV FL wrote (cue/labl regions, verified)
  run              open → load_regions → send_to_channel

These drive FL's custom-drawn UI with OCR-located clicks: FL must be the
frontmost app and nobody should use the mouse while a call runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fl_studio_mcp.preset_paths import work_root
from fl_studio_mcp.utils import edison_bridge as eb

ACTIONS = ("status", "open", "load_regions", "send_to_channel", "run")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}


def _flow():
    from fl_studio_mcp.utils import edison_flow
    return edison_flow


def _check_out(out: str | None) -> tuple[str | None, str | None]:
    """`out` (a copy of the sent WAV) must be a .wav inside the repo."""
    if not out:
        return None, None
    p = Path(out).expanduser().resolve()
    repo = work_root().parent
    if p.suffix.lower() != ".wav":
        return None, f"out must be a .wav path (got {out})"
    if repo not in p.parents:
        return None, f"out must be inside the repo {repo} (got {p})"
    return str(p), None


def _regions(hits_json: str | None, regions: list[dict] | None,
             max_ms: float) -> tuple[list[dict] | None, str | None]:
    if regions:
        for r in regions:
            if not isinstance(r, dict) or "start_s" not in r:
                return None, "each region needs at least start_s (seconds)"
        return regions, None
    if not hits_json:
        return None, "load_regions needs hits_json (analysis drums.json) or regions"
    p = Path(hits_json).expanduser()
    if p.suffix.lower() != ".json" or not p.is_file():
        return None, f"hits_json must be an existing .json file (got {hits_json})"
    try:
        return eb.regions_from_json(p, max_ms=max_ms), None
    except (ValueError, KeyError) as e:
        return None, f"bad hits_json: {e}"


def fl_edison(action: str, clip: str | None = None,
              hits_json: str | None = None,
              regions: list[dict] | None = None, max_ms: float = 300.0,
              clear_regions: bool = True, channel: int | None = None,
              out: str | None = None) -> dict[str, Any]:
    """See the module docstring. Returns {"ok", "action", ..., "log"}."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"unknown action {action!r}; one of {ACTIONS}"}
    if sys.platform != "darwin":
        return {"ok": False, "error": "fl_edison drives the macOS UI (darwin only)"}

    if action == "status":
        where = _flow().locate()
        return {"ok": True, "action": action, "edison_open": where is not None,
                "anchor": where and where["anchor"]}

    if clip is not None:
        c = Path(clip).expanduser()
        if c.suffix.lower() not in AUDIO_EXTS or not c.is_file():
            return {"ok": False, "error": f"clip must be an existing audio file "
                                          f"{sorted(AUDIO_EXTS)} (got {clip})"}
        clip = str(c.resolve())
    out_p, err = _check_out(out)
    if err:
        return {"ok": False, "error": err}
    regs = None
    if action in ("load_regions", "run"):
        regs, err = _regions(hits_json, regions, max_ms)
        if err:
            return {"ok": False, "error": err}
    if action in ("send_to_channel", "run") and channel is None:
        return {"ok": False, "error": "send_to_channel needs channel (a Sampler "
                                      "channel index; add one with fl_channel add)"}

    flow = _flow()
    steps: dict[str, dict] = {}
    if action in ("open", "run"):
        steps["open"] = flow.open_edison()
        if action == "open" or not steps["open"]["ok"]:
            return _done(action, steps)
    if action in ("load_regions", "run"):
        steps["load_regions"] = flow.load_regions(clip, regs,
                                                  clear_regions=clear_regions)
        if action == "load_regions" or not steps["load_regions"]["ok"]:
            return _done(action, steps)
    expected = len(regs) if regs is not None else None
    steps["send_to_channel"] = flow.send_to_channel(channel=channel, out=out_p,
                                                    expected=expected)
    return _done(action, steps)


def _done(action: str, steps: dict[str, dict]) -> dict[str, Any]:
    last = list(steps.values())[-1]
    res: dict[str, Any] = {"ok": all(s["ok"] for s in steps.values()),
                           "action": action}
    if len(steps) == 1:
        res.update({k: v for k, v in last.items() if k != "ok"})
    else:
        res["steps"] = steps
        if not res["ok"]:
            failed = next(n for n, s in steps.items() if not s["ok"])
            res["error"] = f"{failed}: {steps[failed].get('error')}"
    return res


def register_edison_tools(mcp) -> None:
    """Register fl_edison."""
    from fl_studio_mcp.tools.edison_v2 import fl_edison as _impl

    @mcp.tool()
    def fl_edison(action: str, clip: str | None = None,
                  hits_json: str | None = None,
                  regions: list[dict] | None = None, max_ms: float = 300.0,
                  clear_regions: bool = True, channel: int | None = None,
                  out: str | None = None) -> dict:
        """Edison: load a clip, stamp onset regions, send clip+regions to a Sampler.

        Actions: status | open | load_regions | send_to_channel | run
          status          — is Edison visible? (read-only)
          open            — open Edison on the selected mixer insert (no-op if open)
          load_regions    — clip (audio path, optional: else the loaded clip) +
                            hits_json (analysis drums.json: one region per hit,
                            named '<type> <n>', ≤ max_ms long) or regions
                            [{name, start_s, end_s}]; clear_regions first (default)
          send_to_channel — channel (Sampler index): clip + regions replace its
                            sample; returns the WAV FL wrote + region count;
                            out = optional .wav copy inside the repo
          run             — open → load_regions → send_to_channel

        Drives FL's custom UI by OCR-located clicks: FL must be frontmost and
        the mouse untouched while it runs (~30-60 s for run). Add the Sampler
        first: fl_channel(action="add", plugin="Sampler").
        """
        return _impl(action=action, clip=clip, hits_json=hits_json,
                     regions=regions, max_ms=max_ms,
                     clear_regions=clear_regions, channel=channel, out=out)
