#!/usr/bin/env bash
# _lib.sh — shared helpers for the orchestrating-daemons toolkit.
# Sourced by daemon-*.sh. Not meant to be run directly.
#
# A "daemon" is a durable background `claude` session spawned with `claude --bg`
# (so it is an independent process, visible in `claude agents`, and survives this
# orchestrator ending). It is continued IN PLACE with `claude -p --resume` after
# `claude stop` releases the bg ownership lock — same session id, no fork.
#
# Each daemon has one metadata file (<uuid>.json) and one latest-reply file
# (<uuid>.reply.txt, plain text) under the registry dir. One turn per daemon runs
# at a time, so per-daemon files never race.

set -euo pipefail

# Registry location — override with DAEMON_HOME for tests.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
mkdir -p "$DAEMON_HOME"

# Wall-clock backstop (seconds) for resume turns, and how long spawn's watcher
# waits for the first turn. Autonomous daemons do long work — this is a hang
# backstop, NOT a pacing tool. Default 5 hours; 0 disables it entirely.
# Override per-invocation with DAEMON_TIMEOUT.
DAEMON_TIMEOUT="${DAEMON_TIMEOUT:-18000}"

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

_meta_path()  { printf '%s/%s.json' "$DAEMON_HOME" "$1"; }
_reply_path() { printf '%s/%s.reply.txt' "$DAEMON_HOME" "$1"; }
_err_path()   { printf '%s/%s.err' "$DAEMON_HOME" "$1"; }

# Strip ANSI color codes (the `claude --bg` banner is colored even when piped).
_strip_ansi() { sed -E 's/\x1b\[[0-9;]*m//g'; }

# Portable timeout: macOS ships neither `timeout` nor `gtimeout` by default.
# secs=0 means no cap — run the command bare.
_timeout() {
  local secs="$1"; shift
  if [ "$secs" = "0" ]; then
    "$@"
  elif command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    "$@" &
    local pid=$!
    ( sleep "$secs"; kill -TERM "$pid" 2>/dev/null || true ) &
    local watcher=$!
    local rc=0
    wait "$pid" || rc=$?
    kill "$watcher" 2>/dev/null || true
    return "$rc"
  fi
}

# Merge key=value pairs into a daemon's metadata JSON (creates it if absent).
# Usage: _meta_set <uuid> field1 value1 [field2 value2 ...]
_meta_set() {
  local uuid="$1"; shift
  local path; path="$(_meta_path "$uuid")"
  DAEMON_META_PATH="$path" python3 - "$@" <<'PY'
import json, os, sys
path = os.environ["DAEMON_META_PATH"]
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
args = sys.argv[1:]
for i in range(0, len(args), 2):
    data[args[i]] = args[i + 1]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2)
os.replace(tmp, path)
PY
}

# Print one metadata field (empty string if missing).
_meta_get() {
  local uuid="$1" field="$2" path
  path="$(_meta_path "$uuid")"
  [ -f "$path" ] || { printf ''; return 0; }
  DAEMON_META_PATH="$path" python3 - "$field" <<'PY'
import json, os, sys
try:
    with open(os.environ["DAEMON_META_PATH"]) as f:
        print(json.load(f).get(sys.argv[1], ""))
except Exception:
    print("")
PY
}

# Print a daemon's latest reply (plain text), or a placeholder.
_reply_text() {
  local p; p="$(_reply_path "$1")"
  if [ -f "$p" ]; then cat "$p"; else printf '(no reply yet)'; fi
}

# Resolve a short id (or full UUID prefix) to a full UUID by matching registry
# metadata files. Prints the full UUID, or errors if zero / multiple matches.
_resolve_uuid() {
  local q="$1" match
  match="$(DAEMON_HOME="$DAEMON_HOME" python3 - "$q" <<'PY'
import glob, os, sys
home = os.environ["DAEMON_HOME"]; q = sys.argv[1]
hits = []
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    u = os.path.basename(p)[:-5]
    if u == q or u.startswith(q):
        hits.append(u)
if len(hits) == 1:
    print(hits[0])
elif not hits:
    sys.exit(3)
else:
    sys.stderr.write("ambiguous id '%s' matches: %s\n" % (q, ", ".join(hits)))
    sys.exit(4)
PY
)" || { echo "no daemon matching '$q'" >&2; return 1; }
  printf '%s' "$match"
}

# The on-disk transcript path for a daemon. Munging-agnostic: Claude Code mangles
# the cwd into the project-dir name (replacing both `/` and `.`), so instead of
# reproducing that rule we glob for the transcript by its unique UUID.
_transcript_path() {
  find "$HOME/.claude/projects" -name "$1.jsonl" 2>/dev/null | head -1
}

# Print the last assistant text turn from a daemon's transcript (how we read the
# reply of a `--bg` turn, since --bg returns no stdout result to us).
_transcript_reply() {
  local uuid="$1" f
  f="$(_transcript_path "$uuid")"
  [ -n "$f" ] && [ -f "$f" ] || { printf ''; return 0; }
  DAEMON_TX="$f" python3 - <<'PY'
import json, os
rows = [json.loads(l) for l in open(os.environ["DAEMON_TX"]) if l.strip()]
text = ""
for r in reversed(rows):
    if r.get("type") == "assistant":
        c = r.get("message", {}).get("content")
        t = " ".join(b.get("text", "") for b in c
                     if isinstance(b, dict) and b.get("type") == "text") if isinstance(c, list) else str(c)
        if t.strip():
            text = t.strip(); break
# A turn can end blocked on an AskUserQuestion tool call. The question lives in
# the tool_use INPUT, not in text — without rendering it here the reply would be
# empty and the orchestrator would have to dig the transcript by hand.
pending = []
last = next((r for r in reversed(rows) if r.get("type") == "assistant"), None)
if last:
    c = last.get("message", {}).get("content")
    for b in (c if isinstance(c, list) else []):
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
            for q in (b.get("input") or {}).get("questions", []):
                opts = " / ".join(o.get("label", "") for o in q.get("options", []) if isinstance(o, dict))
                pending.append("Q: %s%s" % (q.get("question", ""), ("\n   options: " + opts) if opts else ""))
if text:
    print(text)
if pending:
    print('[pending AskUserQuestion — daemon is blocked on it; answer with daemon-resume.sh <id> "<answer>"]')
    print("\n".join(pending))
PY
}

# Poll `claude agents` until short id <1> reaches a terminal/actionable state.
# Echoes "<full-uuid> <state> <cwd>" (cwd is the daemon's ACTUAL working dir —
# the worktree path when spawned with --worktree). Non-zero on timeout.
# max=0 polls with no iteration cap (pairs with DAEMON_TIMEOUT=0).
_poll_until_done() {
  local short="$1" max="${2:-120}" i=0 uuid state cwd
  while :; do
    read -r uuid state cwd < <(claude agents --json --all 2>/dev/null | DAEMON_SHORT="$short" python3 -c '
import json, os, sys
s = os.environ["DAEMON_SHORT"]
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
for a in d:
    if a.get("id") == s:
        print(a.get("sessionId", ""), a.get("state", ""), a.get("cwd", "")); break
') || true
    case "$state" in
      done | blocked | error) printf '%s %s %s' "$uuid" "$state" "$cwd"; return 0 ;;
    esac
    i=$((i + 1))
    if [ "$max" -gt 0 ] && [ "$i" -ge "$max" ]; then break; fi
    sleep 2
  done
  printf '%s %s %s' "${uuid:-}" "${state:-timeout}" "${cwd:-}"; return 1
}
