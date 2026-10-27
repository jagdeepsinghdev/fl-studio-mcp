# Skills (optional add-on for the FL Studio MCP server)

The MCP server works on its own: every tool is described in its MCP schema, so any MCP client
can use it **without these skills**. The skills are an **optional** knowledge pack for
Claude (Claude Code, Claude Desktop, or any agent that reads `SKILL.md` folders): workflows,
gotchas, genre recipes and music theory that make the agent better at using the tools.
**Nothing is installed by default.** Pick the ones you want.

## What each skill gives you

| Skill | Gives the agent | Install it if… |
|---|---|---|
| `fl-studio` | the **start-here index**: which skill to open for a task, the golden rules (one MCP call at a time, verify every write) | you install any FL skill (the others assume it) |
| `fl-setup` | connecting to FL, the MIDI bridge, timeouts, Accessibility / Screen Recording permissions, the piano-roll script selection | first-time setup or "FL tools time out" |
| `fl-presets` | ready-made beat + melody JSON presets and the one-call track loaders | you want a quick track from presets |
| `fl-patterns` | step sequencer, multi-bar drums, pattern length vs phrase length, song sections | you program drums or build Intro/Verse/Chorus |
| `fl-melody` | writing notes into the piano roll safely (the roll handshake), scales, per-genre note recipes, "notes didn't land" fixes | you want melodies, chords or bass lines |
| `fl-mixing` | levels, pan, send buses, EQ/FX, vocal chains, stock-plugin mastering to a LUFS target | you mix or master |
| `fl-plugins` | adding instruments, plugin parameters, finding presets by name, loading samples | you need a specific sound or instrument |
| `fl-genres` | per-genre recipes + one-call genre packs (trap, drill, lofi, house, afrobeats, dnb, …): tempo, grid, kit, chords | you name a genre or style |
| `fl-song-builder` | building a whole multi-bar track with any instrument, layer by layer with checkpoints | "make a beat + a melody", full songs |
| `music-theory` | **the theory brain, not FL-specific**: scales/modes, harmony, voice leading, rhythm, 808 writing, form, ragas, ear training, reading analysis output, learning from a reference without copying | you want the agent to explain *why* or write original parts in a style (useful even without FL) |

## Install

```bash
skills/install.sh                       # list the skills
skills/install.sh fl-studio fl-melody   # install those into ~/.claude/skills (symlinks)
skills/install.sh --all                 # every public skill
skills/install.sh --project ~/my-proj fl-studio music-theory   # into <project>/.claude/skills
skills/install.sh --copy music-theory   # copy instead of symlink
```

Uninstall = delete the folder or symlink from `~/.claude/skills/`. For other agents, point
them at the skill folders (each is self-contained: `SKILL.md` + `references/`).

---

## Maintaining skills — structure & rules (read before adding or changing a skill)

**One main index → a fixed set of domains → expert knowledge lives in each domain's `references/`.**
Skills grow by adding *reference files inside a domain*, not by adding skills.

```
skills/
  fl-studio/        MAIN index. Domain table, golden rules, transport/channel tools.
  fl-setup/         connect, MIDI bridge, Accessibility, once-per-launch manual step
  fl-presets/       ready-made beat & melody JSON presets
  fl-patterns/      drums, step sequencer, pattern length, sections   (references/: drum-templates, sections)
  fl-melody/        piano-roll notes                                   (references/: scales, genre-recipes, ...)
  fl-mixing/        levels, pan, sends/buses, swing
  fl-plugins/       add instruments, plugin params, preset-by-name     (references/: instruments)
  fl-genres/        per-genre recipes                                  (references/: trap, house, lofi, ...)
  fl-song-builder/  workflow: whole track, any instrument (fl_batch & co)
  music-theory/     THE THEORY BRAIN (not FL-specific): harmony, rhythm, melody, form, ragas, genres,
                    ear training, reading analysis output   (references/: one file per topic)
```

## Rules (enforced by `fl-studio-mcp/tests/test_skills.py`)
1. **Only the domains above exist.** A new *skill directory* requires a genuinely new domain (not a topic) and
   an edit to `DOMAINS` in the test **plus** a row in `fl-studio/SKILL.md` and this file. Default answer: no.
2. **New topic / genre / plugin / technique = a new `references/<topic>.md` in the owning domain**, linked from
   that domain's `SKILL.md` "References" list. (New genre → `fl-genres/references/<genre>.md` + table row.
   New plugin expertise → `fl-plugins/references/<plugin>.md`. New mixing recipe → `fl-mixing/references/`.)
3. **One owner per fact.** Theory (why / which notes / style) is owned by `music-theory`; FL domains link to it. Before writing, grep for the fact. If it exists, link to it, don't copy it.
   (Tool signatures live in the domain that owns them; workflows link to tools, not restate them.)
4. **Size caps:** `SKILL.md` ≤ 150 lines (it is a router + the essential workflow); a reference ≤ 300 lines
   (split by topic when longer). **Exception:** `music-theory/references/` has no line cap (owner decision,
   2026-10-03: it is the knowledge base); still one topic per file.
5. **Frontmatter:** `name` = directory name; `description` = what + "Use when …" trigger, ≤ 400 chars.
6. **Every `references/*.md` is linked from its `SKILL.md`**, and no doc may mention a removed skill name.
7. **Names:** `fl-<domain>` for FL domains (`music-theory` is the one non-FL domain); references are
   lowercase-kebab topic names. No dates in names.
8. **Tool changes:** adding/removing an MCP tool → update the owning domain skill, then
   `cd fl-studio-mcp && uv run python scripts/gen-inventory.py` (INVENTORY.md is generated, never hand-edited).
9. **Verified vs. conventional:** mark genre/mix numbers "from convention, not auditioned" until tested in FL.
10. Session logs / one-off incident write-ups go to the maintainer's notes (not a skill) or the domain's `gotchas`
    reference — never a new skill.
