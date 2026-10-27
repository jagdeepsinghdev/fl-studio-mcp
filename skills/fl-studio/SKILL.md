---
name: fl-studio
description: START HERE for any FL Studio task. Main index of the FL skill domains (setup, presets, patterns, melody, mixing, plugins, genres, song-builder), the hard rules, and which skill to open next. Use when the user asks to make, edit, play or mix anything in FL Studio.
---

# FL Studio — main index

All control is through the `flstudio` MCP server. **The default surface is 10 domain tools**
(`fl_state`, `fl_transport`, `fl_mixer`, `fl_channel`, `fl_pattern`, `fl_notes`, `fl_plugin`,
`fl_file`, `fl_help`, plus `fl_delete`/`fl_batch`) — each takes an `action` + params.
**`fl_help(domain)` returns the full param/action docs for any one domain — call it when in
doubt.** Read the repo-root `CLAUDE.md` hard rules first. Then open the ONE domain skill
below (each maps a need to the right domain tool + action).

> **Migration note (one cycle):** a few older references in this tree still name the legacy
> single-purpose tools (`fl_play`, `fl_set_bpm`, ...). Those still work *only* with
> `LEGACY_TOOLS=1` on the server. The domain tools are the current surface; the skills are
> being migrated to them. The migration map is `fl-studio-mcp/tests/test_skill_refs.py`.

## Domains (open the one that matches; each maps to its domain tool)

| Need | Domain skill | Domain tool(s) it drives |
|---|---|---|
| Connect / fix timeouts / ComposeWithLLM selection (automatic) | **`fl-setup`** | `fl_connect` + `fl_state` + `fl_select_script` |
| Ready-made beats & melodies (JSON presets) | **`fl-presets`** | `fl_notes` (write_steps) + preset loading |
| Drums, step sequencer, pattern length, song sections | **`fl-patterns`** | `fl_pattern` + step-sequencer actions |
| Notes: melody, bass, chords, scales | **`fl-melody`** | `fl_notes` (write_steps / read_steps) |
| Levels, pan, sends/buses, swing | **`fl-mixing`** | `fl_mixer` (+ `fl_transport` for swing/speed) |
| Instruments & sounds (add channel, plugin params, preset by name) | **`fl-plugins`** | `fl_channel` (add) + `fl_plugin` |
| A genre (16: trap, drill, hip-hop, lofi, r&b, pop, afrobeats, house, techno, future bass...) | **`fl-genres`** | **one call: `fl_genre("load", genre=...)`** (tempo, beat, Keys+Bass, chords, bass, levels) |
| Vocal chain / buses / mastering | **`fl-mixing`** | **one call: `fl_vocal("setup")`**; `fl_vocal("apply", recipe, track)`; plugin knobs/presets `fl_plugin` |
| Whole track in one call, any instrument | **`fl-song-builder`** | `fl_batch` (many actions in one trip) |
| **Theory: which notes/chords/rhythm and why, ragas, genre DNA, reading a song analysis** | **`music-theory`** | none (knowledge; feeds every domain above) |
| See FL's screen / read or click UI by text | (tool) | `fl_screen` (look, ocr, find, hint, click_text); before long jobs `fl_connect("doctor")` / `("recover")` / `("tidy")` |
| Audio files: a sample's tempo/key/chords/root note, cut a section, isolate L/R, load to a Sampler | (tool) | `fl_audio("analyze"|"extract"|"split"|"load", path, ...)` (tempo disagreements are reported) |
| Chords from TEXT ("Am F C G", "Cmaj7 | Fm9", "C/E"); dump what was PLAYED IN (score log) | **`fl-melody`** | `fl_notes("write_chords", text, channel_index)` · `fl_notes("capture", seconds)` |

## Golden rules (never skip)
1. `fl_state` before touching anything (the user edits FL live; indexes move). It returns
   channels, patterns, transport, selection — **and the piano-roll mtime guard** (a stale note
   list is flagged; re-trigger before trusting it). **Check `active_is_default`**: if true, the
   active pattern is FL's empty default — `get_steps` will read empty. Re-select the intended
   pattern before diagnosing "missing" drum steps.
2. Real tempo = `fl_transport(set_bpm)`; then `fl_transport(set_speed, 1.0)`. Set pattern
   length (`fl_pattern(set_len)`) before notes; drums, phrases and the pattern share one length.
3. Notes need **ComposeWithLLM** selected — **`fl_select_script(channel_index=…)`** (automatic on
   the first note write per FL process; manual call is the fallback). Confirm the target roll
   is the one you think it is (`fl_notes(write_steps, open_roll_verified=True)` refuses to write
   otherwise — §6b). Read back after every write (`fl_state` / `fl_notes(read_steps)`).
4. `fl_transport(play)` toggles — check `fl_state` first. Every write returns a same-trip
   `state_after`; trust that, not the success message.
5. Missing capability → add an MCP tool (CLAUDE.md rule 2), don't hack around it.

## Tool map
FL's own keyboard shortcuts (226, production-first, guarded): `fl_shortcut` →
`references/shortcuts.md`. Use them only where no domain tool action exists.
The 10 domain tools + `fl_delete`/`fl_batch`: see `INVENTORY.md` (auto-generated) or
`fl_help`. `references/transport-channels.md` has the transport/channel detail.

## References
- `references/transport-channels.md` — transport & channel-rack detail, general tips.
- `references/shortcuts.md` — `fl_shortcut`: which FL hotkeys land, guards, find/run/batch.

Skill-system rules (how to add/grow skills without bloat): `skills/README.md`.
