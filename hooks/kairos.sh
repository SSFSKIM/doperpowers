#!/usr/bin/env bash
# kairos — SessionStart hook. A session in proactive mode gets the kairos skill
# body injected at startup and again after every compaction, so the mode
# outlives the context that first carried it. Any other session gets nothing.
#
# Two things put a session in the mode, and they meet here:
#   - KAIROS=1 in the session's environment — a launcher that wants proactive
#     mode from the first turn. Per-session on purpose, never a machine-wide
#     flag: dispatched workers are sessions too, and one file would switch all
#     of them.
#   - a flag file named by the session id, written by kairos-toggle.sh when
#     the human types /kairos mid-session. Hooks are separate processes that
#     share nothing but the filesystem and the session id on stdin, so this is
#     the only carrier a mid-session switch has; the id survives compaction
#     and --resume (a fork gets a new id, and starts out of the mode).
#
# The body is read from the skill itself so `/kairos` and this hook can never
# drift apart. Flag files older than a week are swept whenever a body is
# injected — a finished session leaves its flag behind, and the sweep is
# cheaper than a SessionEnd hook.
set -euo pipefail

KAIROS_DIR="${KAIROS_DIR:-$HOME/.claude/kairos}"

on=""
case "${KAIROS:-}" in 1|true|on) on=1 ;; esac
if [ -z "$on" ]; then
  sid="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "")' 2>/dev/null || true)"
  [ -n "$sid" ] && [ -f "$KAIROS_DIR/$sid" ] && on=1
fi
[ -n "$on" ] || exit 0

skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/kairos/SKILL.md"
[ -f "$skill" ] || exit 0

[ -d "$KAIROS_DIR" ] && find "$KAIROS_DIR" -type f -mtime +7 -delete 2>/dev/null || true

# The body only: the frontmatter is the skill listing's, not the session's.
awk 'seen > 1 { print } /^---$/ { seen++ }' "$skill"
