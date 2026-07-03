#!/usr/bin/env bash
# _lib.sh — shared helpers for the orchestrating-daemons toolkit.
# Sourced by daemon-*.sh. Not meant to be run directly.
#
# A "daemon" is a durable background `claude` session spawned with `claude --bg`
# (so it is an independent process, visible in `claude agents`, and survives this
# orchestrator ending). It is CONTINUED BY FORKING: each resume runs `claude stop`
# on the current turn, then `claude --bg --resume` to spawn a fresh bg agent that
# carries the full context forward. So every turn — the first and every resume —
# is a native background agent visible in `claude agents`.
#
# Each daemon has one metadata file (<uuid>.json) and one latest-reply file
# (<uuid>.reply.txt, plain text) under the registry dir. The meta is keyed by the
# daemon's ORIGINAL session uuid (its stable identity); the `current` field chains
# to the latest turn's session, so the human-visible short id changes each turn but
# the daemon's id does not. One turn per daemon runs at a time, so per-daemon files
# never race.

set -euo pipefail

# Registry location — override with DAEMON_HOME for tests.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
mkdir -p "$DAEMON_HOME"

# How long the spawn/resume WATCHER polls `claude agents` for a turn to finish —
# a wait bound only, NOT a turn budget. The toolkit never kills a turn: every turn
# is an independent `--bg` process that keeps running regardless. Default 5 hours;
# 0 = watch forever. Override per-invocation with DAEMON_TIMEOUT.
DAEMON_TIMEOUT="${DAEMON_TIMEOUT:-18000}"

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

_meta_path()  { printf '%s/%s.json' "$DAEMON_HOME" "$1"; }
_reply_path() { printf '%s/%s.reply.txt' "$DAEMON_HOME" "$1"; }
_err_path()   { printf '%s/%s.err' "$DAEMON_HOME" "$1"; }

# Strip ANSI color codes (the `claude --bg` banner is colored even when piped).
_strip_ansi() { sed -E 's/\x1b\[[0-9;]*m//g'; }

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

# Resolve a query to a daemon's stable uuid (the meta FILENAME) by matching, in
# order, the meta filename prefix, then the meta's `short` and `current` fields.
# After a resume forks a new turn, the human copies the CURRENT turn's short id
# from `claude agents` — that short lives in the meta, not in the filename, so we
# have to read each meta to find it. Prints the daemon uuid, or errors if zero /
# multiple daemons match.
_resolve_uuid() {
  local q="$1" match rc
  match="$(DAEMON_HOME="$DAEMON_HOME" python3 - "$q" <<'PY'
import glob, json, os, sys
home = os.environ["DAEMON_HOME"]; q = sys.argv[1]
hits = set()
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    u = os.path.basename(p)[:-5]
    if u == q or u.startswith(q):
        hits.add(u); continue
    try:
        with open(p) as f:
            m = json.load(f)
    except Exception:
        continue
    for field in ("short", "current"):
        v = str(m.get(field, ""))
        if v and (v == q or v.startswith(q)):
            hits.add(u); break
hits = sorted(hits)
if len(hits) == 1:
    print(hits[0])
elif not hits:
    sys.exit(3)
else:
    sys.stderr.write("ambiguous id '%s' matches: %s\n" % (q, ", ".join(hits)))
    sys.exit(4)
PY
)" || {
    rc=$?
    # Distinguish python's exit codes: 3 = no match (explain here); 4 = ambiguous
    # (python already wrote the specific "ambiguous id ..." line to stderr, so
    # also printing "no daemon matching" would double up the error).
    [ "$rc" -eq 3 ] && echo "no daemon matching '$q'" >&2
    return 1
  }
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

# Purge a superseded turn's session once its forked successor is CONFIRMED.
# `claude rm <short>` is the native deregister — it removes the session from
# the supervisor's control plane AND the jobs dir. Deleting the files alone is
# NOT enough: the supervisor re-materializes state.json from its own record on
# the next `claude attach` (observed live — a purged turn resurrected as a
# ghost "working" dashboard entry when the human attached to it).
# `claude rm` also deletes the session's worktree WHEN CLEAN (dirty worktrees
# are kept) — and the daemon's FIRST turn owns the shared worktree that every
# later turn still runs in. So when the daemon is worktree'd, callers pass the
# worktree path and we make it dirty with a sentinel file for the duration of
# the rm. rm does not remove transcripts; delete explicitly — safe because a
# fork physically copies the full conversation into the successor's transcript
# (verified live). Failure paths must NEVER call this — the old session is the
# only recovery point when a fork goes wrong.
_session_purge() {
  local short="$1" uuid="$2" wt="${3:-}" tx guard=""
  case "$short" in
    "" | *[!0-9a-f]*) : ;;  # jobs dirs are 8-hex shorts; never touch odd input
    *)
      if [ "${#short}" -eq 8 ]; then
        if [ -n "$wt" ] && [ -d "$wt" ]; then
          guard="$wt/.daemon-turn-live"
          touch "$guard" 2>/dev/null || guard=""
        fi
        claude rm "$short" >/dev/null 2>&1 || true
        rm -rf "$HOME/.claude/jobs/$short"  # belt-and-suspenders for CLIs without `rm`
        [ -n "$guard" ] && rm -f "$guard"
      fi ;;
  esac
  case "$uuid" in
    "" | *[!0-9a-f-]*) : ;;
    *)
      tx="$(_transcript_path "$uuid")"
      [ -n "$tx" ] && rm -f "$tx" ;;
  esac
  return 0
}

# Write a turn's reply to the daemon's reply file, annotating the one blocked
# shape _transcript_reply cannot see: state=blocked with NO pending
# AskUserQuestion in the transcript. That is a harness-level prompt (observed
# live: a permission prompt holding a tool call that never reached the
# transcript) — without the marker the reply reads like a finished statement
# and the orchestrator has nothing to act on.
# Usage: _record_reply <turn-uuid> <daemon-uuid> <state>
_record_reply() {
  local out
  out="$(_transcript_reply "$1")"
  if [ "$3" = "blocked" ] && ! printf '%s' "$out" | grep -q '\[pending AskUserQuestion'; then
    out="$out
[blocked on a harness prompt — no pending AskUserQuestion in the transcript, most likely a permission prompt holding a tool call. Resume with an answer/instruction (the pending call is interrupted), or 'claude attach' the session to approve it interactively.]"
  fi
  printf '%s\n' "$out" > "$(_reply_path "$2")"
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
    # A row with an empty sessionId is unusable (and would jumble the whitespace
    # parsing downstream) — keep polling until the uuid materializes.
    if a.get("id") == s and a.get("sessionId"):
        print(a.get("sessionId"), a.get("state", ""), a.get("cwd", "")); break
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
