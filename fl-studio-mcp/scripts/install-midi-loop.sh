#!/bin/bash
# Install the MIDI loop (fl_controller/fl_midi_loop.py) as a macOS LaunchAgent:
# it creates the "FL Studio MCP" virtual CoreMIDI ports at login and keeps them
# forwarded (no IAC Driver needed). Run once, then pick "FL Studio MCP Bus" as
# FL's MIDI input (Options > MIDI settings).
#
#   scripts/install-midi-loop.sh              install + start (label below)
#   scripts/install-midi-loop.sh --uninstall  stop + remove
#   FL_MIDI_LOOP_LABEL=com.me.fl-midi-loop scripts/install-midi-loop.sh   custom label
#
# Restarting the loop while FL is open makes FL's MIDI input stale: click
# "Refresh device list" in FL's MIDI settings afterwards.
set -euo pipefail

[ "$(uname)" = Darwin ] || { echo "macOS only (Windows: use loopMIDI, see README)"; exit 1; }
LABEL="${FL_MIDI_LOOP_LABEL:-com.flstudiomcp.fl-midi-loop}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

PY="$PROJECT_DIR/.venv/bin/python"
[ -x "$PY" ] || { echo "no $PY - run 'uv sync' in $PROJECT_DIR first"; exit 1; }
if [ -e "$PLIST" ]; then
  echo "$PLIST already exists - remove it with --uninstall first"; exit 1
fi

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>$PY</string>
		<string>$PROJECT_DIR/fl_controller/fl_midi_loop.py</string>
	</array>
	<key>EnvironmentVariables</key>
	<dict>
		<key>FL_MIDI_LOOP_LABEL</key>
		<string>$LABEL</string>
	</dict>
	<key>WorkingDirectory</key>
	<string>$PROJECT_DIR</string>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>StandardOutPath</key>
	<string>/tmp/fl_midi_loop.out.log</string>
	<key>StandardErrorPath</key>
	<string>/tmp/fl_midi_loop.err.log</string>
</dict>
</plist>
EOF
plutil -lint "$PLIST" >/dev/null
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "installed $LABEL ($PLIST); logs: /tmp/fl_midi_loop.{out,err}.log"
echo "check: launchctl print $DOMAIN/$LABEL | grep state"
