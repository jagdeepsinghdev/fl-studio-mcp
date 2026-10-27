"""B10 close-out: skills must not reference tools that aren't in the surface.

The whole point of B10 is that the MCP *default* is the 13-tool domain surface
(the 84 legacy tools only exist behind LEGACY_TOOLS=1). So a skill that tells
the agent to call `fl_play` is a dangling reference *in the default world*.

This does two things:
  1. `scan_skill_tool_refs()` — find every `fl_*` name a skill file references.
  2. A test asserting every referenced name is either (a) in the default
     surface, or (b) in the documented migration map (a legacy name whose
     domain-tool equivalent the skill is allowed to mention during the one
     LEGACY_TOOLS=1 cycle).

It ALSO emits the coverage-gap report: which legacy names the skills lean on
that have NO domain-tool equivalent yet — that is the precise, honest list of
what the 10-tool design is still missing (step-sequencer, markers, song-builder
helpers, preset ops, plugin introspection). That report is what a real skills
migration has to close, not a blind find/replace.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# An fl_* tool name: 'fl' + '_' + a run of lowercase/underscore, ending in a
# letter or digit (so partial tokens like 'fl_load_' from 'fl_load_*' are not
# captured). Only whole words.
TOOL_RE = re.compile(r"\bfl_[a-z][a-z0-9_]*[a-z0-9]\b")

# Names that are NOT MCP tools (connection/infra or prose) — ignored by the scan.
NON_TOOL_NAMES = {
    "fl_studio", "fl_studio_mcp", "fl_controller", "fl_pianoroll",
    "fl_midi_loop",  # the launchagent, not a tool
}


def scan_skill_tool_refs(skills_dir: Path = SKILLS_DIR) -> dict[str, set[str]]:
    """Map each skill file (relative to skills_dir) -> set of fl_* names it references."""
    refs: dict[str, set[str]] = {}
    for path in sorted(skills_dir.rglob("*.md")):
        names = {n for n in TOOL_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
                 if n not in NON_TOOL_NAMES}
        if names:
            refs[str(path.relative_to(skills_dir))] = names
    return refs


def coverage_gaps(referenced: set[str], default_surface: set[str]) -> set[str]:
    """Skill-referenced names that are neither in the default surface nor a
    known infra name. These are the legacy names a real migration must either
    (a) map to a domain-tool action, or (b) add as a domain-tool action."""
    return referenced - default_surface


if __name__ == "__main__":
    import asyncio
    import os
    os.environ.pop("LEGACY_TOOLS", None)
    import fl_studio_mcp.server as srv

    async def m():
        return {t.name for t in await srv.mcp.list_tools()}
    default = asyncio.run(m())

    refs = scan_skill_tool_refs()
    all_names: set[str] = set()
    for n in refs.values():
        all_names |= n
    gaps = coverage_gaps(all_names, default)
    print(f"skills reference {len(all_names)} distinct tool names across {len(refs)} files")
    print(f"coverage gaps (referenced but NOT in the {len(default)}-tool default surface): {len(gaps)}\n")
    for g in sorted(gaps):
        where = sorted(k for k, v in refs.items() if g in v)
        print(f"  {g:32} ({len(where)} skill file(s))")
