#!/usr/bin/env bash
# Audits what the interim-notification filter (hooks/mods/interim.ts) dropped and let through,
# over every main-session transcript on this machine touched since a UTC time.
#   tests/mods/interim-audit/run.sh 2026-10-18T08:00     # since that time
# Writes sessions.txt and drops.json under $AUDIT_OUT (default: a fresh temp dir) and prints three reports.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AUDIT_SINCE="${1:?usage: run.sh <since, UTC, e.g. 2026-10-18T08:00>}"
export AUDIT_OUT="${AUDIT_OUT:-$(mktemp -d)}"
mkdir -p "$AUDIT_OUT"
# The file filter only narrows the scan; the scripts cut every row at AUDIT_SINCE themselves.
ref="$AUDIT_OUT/.since"; touch "$ref"
python3 -c 'import os, sys, datetime; t = datetime.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=datetime.timezone.utc).timestamp(); os.utime(sys.argv[2], (t, t))' "$AUDIT_SINCE" "$ref"
(cd ~/.claude/projects && find . -maxdepth 2 -name '*.jsonl' -newer "$ref") > "$AUDIT_OUT/sessions.txt"
echo "# $(wc -l < "$AUDIT_OUT/sessions.txt" | tr -d ' ') transcripts touched since $AUDIT_SINCE; output in $AUDIT_OUT"
echo; echo "## Every dropped prompt";                 python3 "$here/drops.py"
echo; echo "## Checks on each interim drop";          python3 "$here/drop-checks.py"
echo; echo "## Interim notices that were let in";     python3 "$here/passes.py"
