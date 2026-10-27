#!/usr/bin/env bash
#
# fl-add.sh — add instrument channels to FL Studio (macOS) from the command line.
#
# FL's Python API can't create channels, so this drives the native "Add" menu bar
# via System Events (AppleScript). Requires:
#   - FL Studio 2026 running (process name "OsxFL")
#   - Accessibility permission for the TERMINAL / process running this script
#
# Usage:
#   ./fl-add.sh --list                 # list every instrument in the Add menu
#   ./fl-add.sh "FL Keys"              # add one
#   ./fl-add.sh FLEX "3x Osc" Sytrus   # add several in one go
#   ./fl-add.sh --dry-run "FLEX"       # show what would run, don't click
#
set -euo pipefail

PROC="OsxFL"   # FL Studio 2026 macOS process name

# --- helpers -------------------------------------------------------------

fl_running() {
  pgrep -x "$PROC" >/dev/null 2>&1
}

# Return the names of every top-level item in the "Add" menu bar item.
list_add_menu() {
  osascript - "$PROC" <<'APPLESCRIPT'
on run argv
  set procName to item 1 of argv
  tell application "System Events"
    tell process procName
      set itemNames to name of every menu item of menu 1 of menu bar item "Add" of menu bar 1
    end tell
  end tell
  return itemNames
end run
APPLESCRIPT
}

# Click a single menu item under "Add".
click_add_item() {
  local item="$1"
  # Escape backslashes and double-quotes for AppleScript string literal.
  local esc
  esc=${item//\\/\\\\}
  esc=${esc//\"/\\\"}
  osascript - "$PROC" "$esc" <<'APPLESCRIPT'
on run argv
  set procName to item 1 of argv
  set itemName to item 2 of argv
  tell application "System Events"
    tell process procName
      click menu item itemName of menu 1 of menu bar item "Add" of menu bar 1
    end tell
  end tell
end run
APPLESCRIPT
}

# --- arg parsing ---------------------------------------------------------

DRY_RUN=0
ITEMS=()
for a in "$@"; do
  case "$a" in
    --list)
      if ! fl_running; then echo "FL Studio ($PROC) is not running." >&2; exit 1; fi
      # Pretty-print the menu list.
      list_add_menu | tr ',' '\n' | sed 's/^ *//; s/ *$//'
      exit 0
      ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"; exit 0 ;;
    -*)
      echo "Unknown option: $a" >&2; exit 2 ;;
    *)
      ITEMS+=("$a") ;;
  esac
done

if [ ${#ITEMS[@]} -eq 0 ]; then
  echo "Usage: $0 [--list] [--dry-run] \"FL Keys\" [FLEX ...]" >&2
  echo "Run '$0 --list' to see available instruments." >&2
  exit 2
fi

if [ "$DRY_RUN" -eq 1 ]; then
  for i in "${ITEMS[@]}"; do
    echo "would add: $i"
  done
  exit 0
fi

if ! fl_running; then
  echo "FL Studio ($PROC) is not running. Start it first: open -a 'FL Studio 2026'" >&2
  exit 1
fi

# Make FL frontmost so the menu bar is its menu bar.
osascript -e 'tell application "FL Studio" to activate' >/dev/null 2>&1 || true
sleep 0.6

added=0
for i in "${ITEMS[@]}"; do
  if click_add_item "$i"; then
    echo "added: $i"
    added=$((added + 1))
  else
    echo "FAILED to add: $i (dialog open or item name wrong? try --list)" >&2
  fi
  sleep 0.3
done
echo "done: $added added."
