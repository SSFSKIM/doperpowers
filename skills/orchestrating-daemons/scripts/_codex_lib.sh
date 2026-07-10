#!/usr/bin/env bash
# _codex_lib.sh — codex-engine helpers for the orchestrating-daemons toolkit.
# Sourced by codex-spawn.sh / codex-resume.sh AFTER _lib.sh.
#
# A codex daemon is a detached `codex exec --json` process. Unlike `claude
# --bg` there is no supervisor: WE detach it, WE record its pid, and a wrapper
# shell around the process finalizes the registry when the turn ends. The meta
# is the same JSON contract as claude daemons plus:
#   engine     "codex"
#   pid        codex process pid of the CURRENT turn (liveness: kill -0)
#   effort     model_reasoning_effort
#   event_log  JSONL event stream of the current turn (--json stdout)
# The codex session id (thread.started) keys the registry, so board-bind.sh /
# _resolve_uuid prefix matching work unchanged. Codex sessions keep ONE id
# across resumes — `current` always equals `uuid`.

# Default flags for every codex worker. NEVER add
# --dangerously-bypass-approvals-and-sandbox / --yolo here or at call sites —
# sandbox + approvals reviewer IS the safety contract (mirror of the
# claude-side --dangerously-skip-permissions ban). Fills global CODEX_FLAGS
# (bash 3.2: no mapfile).
_codex_flags() {  # <model> <effort>
  # shellcheck disable=SC2034  # consumed by callers (codex-spawn.sh) after sourcing
  CODEX_FLAGS=( --json --sandbox workspace-write
    -c 'sandbox_workspace_write.network_access=true'
    -c 'features.hooks=false'
    -c 'approval_policy=on-request'
    -c "approvals_reviewer=${CODEX_APPROVALS_REVIEWER:-auto_review}"
    -m "$1" -c "model_reasoning_effort=$2" )
}

# If <cwd> is a LINKED worktree, echo the main repo root — its real .git lives
# there, outside the sandbox's workspace root, so it must be --add-dir'ed for
# commits to work (Spike B). Empty for a normal checkout / non-repo.
_codex_main_root() {
  local gd cd_
  gd="$(git -C "$1" rev-parse --git-dir 2>/dev/null)" || { printf ''; return 0; }
  cd_="$(git -C "$1" rev-parse --git-common-dir 2>/dev/null)" || { printf ''; return 0; }
  gd="$(cd "$1" 2>/dev/null && cd "$gd" 2>/dev/null && pwd -P)"
  cd_="$(cd "$1" 2>/dev/null && cd "$cd_" 2>/dev/null && pwd -P)"
  if [ -n "$gd" ] && [ -n "$cd_" ] && [ "$gd" != "$cd_" ]; then
    git -C "$cd_/.." rev-parse --show-toplevel 2>/dev/null || printf ''
  else
    printf ''
  fi
}

# Session/thread id from a --json event log (thread.started). Field names per
# Spike A; tolerant of drift (thread_id, then id).
_codex_thread_id() {
  [ -f "$1" ] || { printf ''; return 0; }
  python3 - "$1" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") == "thread.started":
        print(d.get("thread_id") or d.get("id") or "")
        break
PY
}

# Last agent_message text from an event log — the live "reply so far", and the
# reply fallback when -o was never written (killed turn).
_codex_last_message() {
  [ -f "$1" ] || { printf ''; return 0; }
  python3 - "$1" <<'PY'
import json, sys
text = ""
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    item = d.get("item") or {}
    if isinstance(item, dict) and item.get("type") == "agent_message":
        t = item.get("text") or item.get("content") or ""
        if isinstance(t, list):
            t = " ".join(b.get("text", "") for b in t if isinstance(b, dict))
        if str(t).strip():
            text = str(t).strip()
print(text)
PY
}

# Terminal status for a finished turn: rc wins; a turn.failed event also means
# error even on rc 0 (belt and suspenders — payloads drift across versions).
_codex_final_status() {  # <rc> <event_log>
  if [ "$1" != "0" ]; then printf 'error'; return 0; fi
  if [ -f "$2" ] && grep -q '"type"[[:space:]]*:[[:space:]]*"turn.failed"' "$2"; then
    printf 'error'; return 0
  fi
  printf 'idle'
}

# Launch one detached codex turn: backgrounds codex inside a nohup'd wrapper
# that records the codex pid, waits for it, captures rc, and finalizes the
# registry (status + reply file) — the wrapper IS the watcher and survives the
# calling script. Args: <cwd> <taskfile> <run-prefix> then the codex argv after
# `codex` (e.g. exec --json ... or exec resume <id> ...). The -o/- redirection
# is appended here.
_codex_launch() {
  local cwd="$1" taskf="$2" run="$3"; shift 3
  nohup bash -c '
    set -u
    DIR="$1"; cwd="$2"; taskf="$3"; run="$4"; shift 4
    # shellcheck source=/dev/null
    source "$DIR/_lib.sh"; source "$DIR/_codex_lib.sh"
    cd "$cwd" || { echo 127 > "$run.rc"; exit 0; }
    codex "$@" -o "$run.reply.txt" - < "$taskf" > "$run.events.jsonl" 2> "$run.err" &
    cpid=$!
    echo "$cpid" > "$run.pid"
    rc=0; wait "$cpid" || rc=$?
    uuid="$(_codex_thread_id "$run.events.jsonl")"
    if [ -z "$uuid" ]; then echo "$rc" > "$run.rc"; exit 0; fi   # never produced a session — spawn fails loud instead
    status="$(_codex_final_status "$rc" "$run.events.jsonl")"
    if [ -s "$run.reply.txt" ]; then
      cp "$run.reply.txt" "$(_reply_path "$uuid")"
    else
      _codex_last_message "$run.events.jsonl" > "$(_reply_path "$uuid")"
    fi
    _meta_set "$uuid" status "$status" updated "$(_now)"
    echo "$rc" > "$run.rc"   # completion barrier — written LAST, after all finalization
  ' _ "$CODEX_LIB_DIR" "$cwd" "$taskf" "$run" "$@" >/dev/null 2>&1 &
}
