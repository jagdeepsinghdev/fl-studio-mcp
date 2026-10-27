"""Anti-bloat rules for skills/ (see skills/README.md)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
# Adding a domain is deliberate: edit this set, fl-studio/SKILL.md and skills/README.md together.
DOMAINS = {"fl-studio", "fl-setup", "fl-presets", "fl-patterns", "fl-melody",
           "fl-mixing", "fl-plugins", "fl-genres", "fl-song-builder", "music-theory"}
# Maintainer-only skills: git-ignored, may exist on a maintainer's disk, never shipped.
PRIVATE = {"splice-sample"}
REMOVED = ("fl-music", "fl-connect", "fl-scales", "fl-melody-apply", "fl-genre-")
SKILL_MAX, REF_MAX = 150, 300
# music-theory is the theory knowledge base: its references have no line cap (owner, 2026-10-03).
UNCAPPED_REFS = {"music-theory"}


def _fm(path: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path}: missing frontmatter"
    return dict(l.split(": ", 1) for l in m.group(1).split("\n") if ": " in l)


def test_only_known_domains():
    dirs = {p.name for p in SKILLS.iterdir() if p.is_dir()} - PRIVATE
    assert dirs == DOMAINS, f"unexpected skill dirs: {dirs ^ DOMAINS} (see skills/README.md rule 1)"


def test_frontmatter_and_size():
    for d in DOMAINS:
        f = SKILLS / d / "SKILL.md"
        fm = _fm(f)
        assert fm["name"] == d, f"{f}: name != dir"
        assert 20 < len(fm["description"]) <= 400, f"{f}: description length"
        n = len(f.read_text().split("\n"))
        assert n <= SKILL_MAX, f"{f}: {n} lines > {SKILL_MAX} (move detail to references/)"


def test_references_linked_and_sized():
    for d in DOMAINS:
        skill = (SKILLS / d / "SKILL.md").read_text()
        for ref in sorted((SKILLS / d / "references").glob("*.md")) if (SKILLS / d / "references").exists() else []:
            assert f"references/{ref.name}" in skill, f"{d}: {ref.name} not linked from SKILL.md"
            n = len(ref.read_text().split("\n"))
            assert d in UNCAPPED_REFS or n <= REF_MAX, f"{ref}: {n} lines > {REF_MAX}"


def test_no_stale_skill_names():
    docs = list(SKILLS.rglob("*.md")) + [ROOT / "README.md", ROOT / "CLAUDE.md",
                                          ROOT / "fl-studio-mcp" / "AGENT-SONG-BUILDER.md"]
    for f in docs:
        text = f.read_text()
        for old in REMOVED:
            assert old not in text, f"{f}: mentions removed skill '{old}'"


def test_domain_table_lists_every_domain():
    main = (SKILLS / "fl-studio" / "SKILL.md").read_text()
    for d in DOMAINS - {"fl-studio"}:
        assert f"`{d}`" in main, f"fl-studio/SKILL.md does not list {d}"
