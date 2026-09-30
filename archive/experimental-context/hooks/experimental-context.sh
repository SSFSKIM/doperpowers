#!/usr/bin/env bash
# experimental-context — SessionStart hook. A session in the mode gets the
# skill body injected at startup and again after every compaction and on
# resume, followed by the session's live <revisit> entries: the latest value
# per key, read from the transcript the harness names in the payload
# (transcript_path is on every hook input). Any other session gets nothing.
#
# The transcript is the store on purpose: a compaction summary is lossy and
# a summary of a summary more so, while the transcript keeps every message
# verbatim for the life of the session id. Re-emitting a key supersedes its
# earlier value; a self-closing or `retired="true"` entry drops it. Sidechain
# rows (subagents) and fenced code are ignored so quoted examples never
# become entries.
#
# Same two carriers as kairos.sh: EXPERIMENTAL_CONTEXT=1 in the environment,
# or a flag file named by the session id under ~/.claude/experimental-context
# (written by experimental-context-toggle.sh on /experimental-context). Flags
# older than a week are swept whenever a body is injected.
set -euo pipefail

CONTEXT_DIR="${CONTEXT_DIR:-$HOME/.claude/experimental-context}"

input="$(cat 2>/dev/null || true)"
IFS=$'\t' read -r sid transcript < <(python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print((d.get("session_id") or "-") + "\t" + (d.get("transcript_path") or ""))' <<<"$input" 2>/dev/null || printf -- '-\t\n')

on=""
case "${EXPERIMENTAL_CONTEXT:-}" in 1|true|on) on=1 ;; esac
if [ -z "$on" ]; then
  [ "$sid" != "-" ] && [ -f "$CONTEXT_DIR/$sid" ] && on=1
fi
[ -n "$on" ] || exit 0

skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/experimental-context/SKILL.md"
[ -f "$skill" ] || exit 0

[ -d "$CONTEXT_DIR" ] && find "$CONTEXT_DIR" -type f -mtime +7 -delete 2>/dev/null || true

# The body only: the frontmatter is the skill listing's, not the session's.
awk 'seen > 1 { print } /^---$/ { seen++ }' "$skill"

[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

python3 - "$transcript" <<'PY'
import json, re, sys

path = sys.argv[1]
BUDGET = 6000  # chars of values before the injection falls back to summaries
fence = re.compile(r"```.*?```", re.S)
entry = re.compile(
    r'<revisit\s+key="([^"]+)"(?:\s+retired="true")?\s*(?:/>|>(.*?)</revisit>)', re.S)

live, order, compactions = {}, [], 0
with open(path, encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") == "system" and row.get("subtype") == "compact_boundary":
            compactions += 1
            continue
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [b.get("text") or "" for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
        else:
            continue
        for text in texts:
            for m in entry.finditer(fence.sub("", text)):
                key, value = m.group(1), m.group(2)
                if value is None:
                    live.pop(key, None)
                    continue
                if key not in order:
                    order.append(key)
                live[key] = (value.strip(), (row.get("timestamp") or "")[:10], compactions)

keys = [k for k in order if k in live]
if not keys:
    sys.exit(0)

total = sum(len(live[k][0]) for k in keys)
summary_only = total > BUDGET
print()
print("## Revisit entries — latest per key, from this session's transcript")
for k in keys:
    value, date, at = live[k]
    ago = compactions - at
    stamp = f"set {date or '?'}, {ago} compaction{'' if ago == 1 else 's'} ago"
    lines = value.splitlines() or [""]
    if summary_only:
        print(f"- {k} ({stamp}): {lines[0]}")
    else:
        print(f"- {k} ({stamp}): {lines[0]}")
        for extra in lines[1:]:
            print(f"  {extra}")
if summary_only:
    print()
    print(f"(Values exceed {BUDGET} chars, so only each entry's first line is shown. "
          f"Full value of KEY: grep -o '<revisit key=\"KEY\">[^<]*' '{path}' | tail -1)")
PY
