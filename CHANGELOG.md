# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (while below 1.0, minor versions may change tools).

To release: add a section here, bump `version` in `fl-studio-mcp/pyproject.toml` and
`__version__` in `fl-studio-mcp/src/fl_studio_mcp/__init__.py`, and `version` (twice) in `server.json`, commit, then
`git tag vX.Y.Z && git push --tags` (the release workflow does the rest).

## [Unreleased]

## [0.1.0] - 2026-10-26

First public release: a fork of [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp)
(MIT) extended into a full FL Studio control server.

### Added
- 29 MCP tools by default (more behind `LEGACY_TOOLS=1`), each with several actions: transport, mixer, channels, patterns,
  piano-roll notes, plugins, presets, genres, vocal chains, audio files, file save/export,
  screen/OCR, FL keyboard shortcuts, Launchpad step sequencer. See `INVENTORY.md`.
- Safe note writing: the piano-roll handshake (roll title proven by OCR) before any write.
- `fl_audio analyze`: tempo (two estimators, disagreement reported), key and chords in pure numpy.
- `fl_preset load_song`: a song folder (`song.json` + presets) into FL in one call.
- `fl_genre`: 16 one-call genre packs (tempo, kit, beat, chords, bass, levels).
- Request-id protocol with audit log and controller rollback.
- Optional Claude skills (`skills/`, installed by `skills/install.sh`; none by default),
  including a standalone music-theory skill.
- `scripts/install-midi-loop.sh`: macOS LaunchAgent for the virtual MIDI ports.
- `server.json` + README `mcp-name` line for the official MCP Registry.
- Published on PyPI as **`mcp-flstudio`** (`uvx mcp-flstudio`); the command `fl-studio-mcp` still works.

### Notes
- macOS is the supported platform for the UI automation (OCR, System Events). Windows
  supports the original transport/mixer/channel/plugin tools only (untested).
- FL Studio's piano-roll script selection resets on every FL launch; the server redoes it.
