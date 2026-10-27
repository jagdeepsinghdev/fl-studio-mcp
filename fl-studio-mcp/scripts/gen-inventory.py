#!/usr/bin/env python3
"""Generate INVENTORY.md — a single source-of-truth list of everything in this repo.

Parses the ACTUAL code (not hand-copied docs):
  - MCP tools  : every @mcp.tool()-decorated `def fl_*` in src/fl_studio_mcp/
  - skills     : every skills/<name>/SKILL.md (name + description from frontmatter)
  - presets    : every fl-studio-mcp/presets/{beats,melodies}/*.json
  - scripts    : shell/python helpers at fl-studio-mcp/ and fl-studio-mcp/scripts/

Run:   uv run python scripts/gen-inventory.py          (or: python3 scripts/gen-inventory.py)
Output: writes <repo>/INVENTORY.md

The file is AUTO-GENERATED. Do not hand-edit it — change the code, then re-run.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent   # the repo root
FL_PKG = REPO_ROOT / "fl-studio-mcp" / "src" / "fl_studio_mcp"
SKILLS_DIR = REPO_ROOT / "skills"
PRESETS_DIR = REPO_ROOT / "fl-studio-mcp" / "presets"
OUT = REPO_ROOT / "INVENTORY.md"


def _visible(paths: list[Path]) -> list[Path]:
    """Drop git-ignored paths (local song-derived presets, private skills) so the
    committed inventory lists only what the repo ships."""
    if not paths:
        return paths
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "--stdin"],
                       input="\n".join(str(p) for p in paths), capture_output=True, text=True)
    ignored = {Path(line) for line in r.stdout.splitlines()}
    return [p for p in paths if p not in ignored]


# --------------------------------------------------------------------------- tools
def parse_tools() -> list[dict]:
    """Return [{name, group, file, doc}] for every @mcp.tool() function.

    group = the register_* function the tool is nested in (or the filename for
    top-level tools in server.py).
    """
    tools: list[dict] = []

    def walk(node: ast.AST, group: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # is this func @mcp.tool()?
                is_tool = any(
                    (isinstance(d, ast.Call) and _is_mcp_tool(d)) for d in child.decorator_list
                )
                if is_tool and child.name.startswith("fl_"):
                    doc = ast.get_docstring(child) or ""
                    first = doc.strip().splitlines()[0] if doc.strip() else ""
                    tools.append({
                        "name": child.name,
                        "group": group,
                        "doc": first,
                    })
                # recurse into the function body regardless (nested defs)
                walk(child, group)
            else:
                walk(child, group)

    for py in sorted(FL_PKG.rglob("*.py")):
        rel = py.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(py.read_text(), filename=rel)
        # server.py top-level tools -> group by file; tool files group by register fn
        base_group = "connection" if py.name == "server.py" else _file_group(py.name)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("register_"):
                    walk(node, node.name.replace("register_", "").replace("_tools", "").replace("_", " "))
                else:
                    # top-level: check for @mcp.tool directly
                    walk(ast.Module(body=[node], type_ignores=[]), base_group)
    # de-dup preserving order
    seen = set()
    out = []
    for t in tools:
        if t["name"] in seen:
            continue
        seen.add(t["name"])
        out.append(t)
    out.sort(key=lambda t: (t["group"], t["name"]))
    return out


def _is_mcp_tool(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr == "tool"
    if isinstance(f, ast.Name):
        return f.id == "tool"
    return False


def _file_group(fname: str) -> str:
    m = re.match(r"register_(?P<g>.+)_tools\.py", fname)
    if m:
        return m.group("g").replace("_", " ")
    return "misc"


# -------------------------------------------------------------------------- skills
def parse_skills() -> list[dict]:
    skills = []
    for d in _visible(sorted(SKILLS_DIR.iterdir())):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue
        name, desc = d.name, ""
        m = re.match(r"^---\n(.*?)\n---", skill_md.read_text(), re.S)
        if m:
            fm = m.group(1)
            nm = re.search(r"^name:\s*(.+)$", fm, re.M)
            dm = re.search(r"^description:\s*(.+)$", fm, re.M)
            if nm:
                name = nm.group(1).strip()
            if dm:
                desc = dm.group(1).strip()
        refs = sorted(r.stem for r in (d / "references").glob("*.md")) if (d / "references").is_dir() else []
        skills.append({"name": name, "dir": d.name, "desc": desc, "refs": refs})
    return skills


# -------------------------------------------------------------------------- presets
def parse_presets(kind: str) -> list[dict]:
    rows = []
    pdir = PRESETS_DIR / kind
    if not pdir.exists():
        return rows
    for jf in _visible(sorted(pdir.glob("*.json"))):
        try:
            data = json.loads(jf.read_text())
        except Exception as e:  # noqa: BLE001
            rows.append({"id": jf.stem, "name": f"(invalid json: {e})", "bpm": "", "swing": "", "key": "", "extra": ""})
            continue
        rows.append({
            "id": data.get("id", jf.stem),
            "name": data.get("name", ""),
            "bpm": data.get("bpm", ""),
            "swing": (f"{data['swing']*100:.0f}%" if isinstance(data.get("swing"), (int, float)) and data.get("swing") else ""),
            "key": data.get("key", ""),
            "extra": (f"{data['length_beats']} beats" if data.get("length_beats") else ""),
        })
    return rows


# ----------------------------------------------------------------------------- main
def main() -> None:
    tools = parse_tools()
    skills = parse_skills()
    beats = parse_presets("beats")
    melodies = parse_presets("melodies")

    # group tools
    by_group: dict[str, list[dict]] = {}
    for t in tools:
        by_group.setdefault(t["group"], []).append(t)

    # shell scripts
    scripts = []
    for p in _visible(sorted((REPO_ROOT / "fl-studio-mcp").glob("*.sh"))):
        scripts.append((p.name, (p.parent.name)))
    for p in _visible(sorted((REPO_ROOT / "fl-studio-mcp" / "scripts").glob("*"))):
        if p.suffix in (".sh", ".ps1", ".py", ".pyscript"):
            scripts.append((p.name, "scripts/"))

    L: list[str] = []
    a = L.append
    a("# INVENTORY — single source of truth for the FL Studio MCP workspace")
    a("")
    a(f"> **AUTO-GENERATED** by `fl-studio-mcp/scripts/gen-inventory.py` on {date.today().isoformat()}. ")
    a("> Do not hand-edit — change the code, then re-run the script. This exists so the tool/skill/preset lists can never drift from reality.")
    a("")
    a(f"- **MCP tools:** {len(tools)} across {len(by_group)} groups")
    a(f"- **Skills:** {len(skills)}")
    a(f"- **Beat presets:** {len(beats)} · **Melody presets:** {len(melodies)}")
    a("")

    a("---")
    a("## MCP tools")
    a("")
    for group in sorted(by_group):
        a(f"### {group} ({len(by_group[group])})")
        a("")
        a("| Tool | What it does |")
        a("|------|--------------|")
        for t in by_group[group]:
            a(f"| `{t['name']}` | {t['doc']} |")
        a("")

    a("---")
    a("## Skills")
    a("")
    a("Structure: one main index (`fl-studio`) -> domains -> `references/` inside each domain. Rules: `skills/README.md`.")
    a("")
    a("| Skill (domain) | Description | References |")
    a("|----------------|-------------|------------|")
    for s in skills:
        refs = ", ".join(f"`{r}`" for r in s["refs"]) or "-"
        a(f"| `{s['dir']}` | {s['desc']} | {refs} |")
    a("")
    a("> Registered project-wide by `.pi/settings.json` (`\"skills\": [\"skills\"]`).")
    a("")

    a("---")
    a("## Beat presets (`fl-studio-mcp/presets/beats/`)")
    a("")
    a("| id | name | bpm | swing |")
    a("|----|------|-----|-------|")
    for b in beats:
        a(f"| `{b['id']}` | {b['name']} | {b['bpm']} | {b['swing']} |")
    a("")
    a("## Melody presets (`fl-studio-mcp/presets/melodies/`)")
    a("")
    a("| id | name | key | bpm | notes |")
    a("|----|------|-----|-----|-------|")
    for m in melodies:
        a(f"| `{m['id']}` | {m['name']} | {m['key']} | {m['bpm']} | {m['extra']} |")
    a("")

    a("---")
    a("## Scripts (`fl-studio-mcp/`)")
    a("")
    a("| Script | Where |")
    a("|--------|-------|")
    for name, where in scripts:
        a(f"| `{name}` | `{where}` |")
    a("")

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"  tools={len(tools)} skills={len(skills)} beats={len(beats)} melodies={len(melodies)} scripts={len(scripts)}")


if __name__ == "__main__":
    main()
