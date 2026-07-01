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

# Per-turn wall-clock cap (seconds) for resume turns; and how long to wait for a
# spawned daemon's first turn to finish. Override with DAEMON_TIMEOUT.
DAEMON_TIMEOUT="${DAEMON_TIMEOUT:-900}"

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

_meta_path()  { printf '%s/%s.json' "$DAEMON_HOME" "$1"; }
_reply_path() { printf '%s/%s.reply.txt' "$DAEMON_HOME" "$1"; }
_err_path()   { printf '%s/%s.err' "$DAEMON_HOME" "$1"; }

# Strip ANSI color codes (the `claude --bg` banner is colored even when piped).
_strip_ansi() { sed -E 's/\x1b\[[0-9;]*m//g'; }

# Portable timeout: macOS ships neither `timeout` nor `gtimeout` by default.
_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
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

# The on-disk transcript path for a daemon in a given cwd.
_transcript_path() {
  local uuid="$1" cwd="$2" munged
  munged="$(printf '%s' "$cwd" | sed 's#/#-#g')"
  printf '%s/.claude/projects/%s/%s.jsonl' "$HOME" "$munged" "$uuid"
}

# Print the last assistant text turn from a daemon's transcript (how we read the
# reply of a `--bg` turn, since --bg returns no stdout result to us).
_transcript_reply() {
  local uuid="$1" cwd="$2" f
  f="$(_transcript_path "$uuid" "$cwd")"
  [ -f "$f" ] || { printf ''; return 0; }
  DAEMON_TX="$f" python3 - <<'PY'
import json, os
rows = [json.loads(l) for l in open(os.environ["DAEMON_TX"]) if l.strip()]
for r in reversed(rows):
    if r.get("type") == "assistant":
        c = r.get("message", {}).get("content")
        t = " ".join(b.get("text", "") for b in c
                     if isinstance(b, dict) and b.get("type") == "text") if isinstance(c, list) else str(c)
        if t.strip():
            print(t.strip()); break
PY
}

# Poll `claude agents` until short id <1> reaches a terminal/actionable state.
# Echoes "<full-uuid> <state>". Returns non-zero on timeout (echoes best-known).
_poll_until_done() {
  local short="$1" max="${2:-120}" i uuid state
  for ((i = 0; i < max; i++)); do
    read -r uuid state < <(claude agents --json --all 2>/dev/null | DAEMON_SHORT="$short" python3 -c '
import json, os, sys
s = os.environ["DAEMON_SHORT"]
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
for a in d:
    if a.get("id") == s:
        print(a.get("sessionId", ""), a.get("state", "")); break
') || true
    case "$state" in
      done | blocked | error) printf '%s %s' "$uuid" "$state"; return 0 ;;
    esac
    sleep 2
  done
  printf '%s %s' "${uuid:-}" "${state:-timeout}"; return 1
}
