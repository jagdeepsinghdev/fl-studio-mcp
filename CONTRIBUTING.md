# Contributing

Thanks for helping. The short version:

```bash
cd fl-studio-mcp
uv sync --extra dev
uv run ruff check .          # must pass
uv run pytest -q             # must pass (no FL Studio needed: FL calls are mocked)
```

- **Missing capability?** Add it as a new tool or an action of an existing domain tool in
  `fl-studio-mcp/src/fl_studio_mcp/tools/`, register it in `server.py`, and test it with the FL
  and OS calls mocked (see `tests/test_song_loader.py` for the pattern).
- **After adding or renaming a tool, skill or preset:** `cd fl-studio-mcp && uv run python scripts/gen-inventory.py`
  and commit `INVENTORY.md` (never hand-edit it).
- **Skills** (`skills/`): read `skills/README.md` first; its rules are enforced by `tests/test_skills.py`.
- **Presets** are plain JSON in `fl-studio-mcp/presets/`; see `fl-studio-mcp/presets/README.md`.
- No audio, renders, or model weights in git; song-derived material stays private.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for user-visible changes.
