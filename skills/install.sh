#!/usr/bin/env bash
# Install the optional FL Studio MCP skills for Claude (none are installed by default).
#   skills/install.sh                         list the skills
#   skills/install.sh [--project DIR] [--copy] (--all | <skill>...)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
private="splice-sample"                       # maintainer-only, never installed by --all
dest="$HOME/.claude/skills"; mode=link; names=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) dest="$2/.claude/skills"; shift 2 ;;
    --copy) mode=copy; shift ;;
    --all) for d in "$here"/*/; do n="$(basename "$d")"; [[ " $private " == *" $n "* ]] || names+=("$n"); done; shift ;;
    -h|--help) sed -n 2,4p "$0"; exit 0 ;;
    *) names+=("$1"); shift ;;
  esac
done
if [ ${#names[@]} -eq 0 ]; then
  echo "Skills (install any; fl-studio is the index the FL skills assume):"
  for d in "$here"/*/; do
    n="$(basename "$d")"; [[ " $private " == *" $n "* ]] && continue
    desc="$(sed -n 's/^description: //p' "$d/SKILL.md" | cut -c1-90)"
    printf "  %-16s %s\n" "$n" "$desc"
  done
  exit 0
fi
mkdir -p "$dest"
for n in "${names[@]}"; do
  [ -f "$here/$n/SKILL.md" ] || { echo "no such skill: $n" >&2; exit 1; }
  if [ -e "$dest/$n" ] || [ -L "$dest/$n" ]; then echo "skip $n: $dest/$n exists"; continue; fi
  if [ "$mode" = copy ]; then cp -R "$here/$n" "$dest/$n"; else ln -s "$here/$n" "$dest/$n"; fi
  echo "installed $n -> $dest/$n ($mode)"
done
