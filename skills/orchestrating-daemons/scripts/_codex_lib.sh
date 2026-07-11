#!/usr/bin/env bash
# _codex_lib.sh — codex-engine helpers for the orchestrating-daemons toolkit.
# Sourced by codex-spawn.sh / codex-resume.sh AFTER _lib.sh.
#
# A codex daemon is a detached `codex exec --json` process. Unlike `claude
# --bg` there is no supervisor: WE detach it, WE record its pid, and a wrapper
# shell around the process finalizes the registry when the turn ends. The meta
# is the same JSON contract as claude daemons plus:
#   engine     "codex"
#   pid        codex process pid of the CURRENT turn (liveness: _pid_alive —
#              kill -0 gated on `host` matching this machine; a registry that
#              migrated on a state volume carries pids that are dead here)
#   effort     model_reasoning_effort
#   event_log  JSONL event stream of the current turn (--json stdout)
# The codex session id (thread.started) keys the registry, so board-bind.sh /
# _resolve_uuid prefix matching work unchanged. Codex sessions keep ONE id
# across resumes — `current` always equals `uuid`.

# Shared tail of every codex invocation: network/hooks/approvals config plus
# -m/effort. NEVER add --dangerously-bypass-approvals-and-sandbox / --yolo
# here or at call sites — sandbox + approvals reviewer IS the safety contract
# (mirror of the claude-side --dangerously-skip-permissions ban). Fills
# global CODEX_FLAGS (bash 3.2: no mapfile). Args after <model> <effort> are
# the sandbox-mode flag(s), which differ between a fresh spawn and a resume
# (see _codex_flags / _codex_resume_flags below).
_codex_flags_common() {  # <model> <effort> <sandbox-flag-word...>
  local model="$1" effort="$2"; shift 2
  # shellcheck disable=SC2034  # consumed by callers (codex-spawn.sh/codex-resume.sh) after sourcing
  CODEX_FLAGS=( --json "$@"
    -c 'sandbox_workspace_write.network_access=true'
    -c 'features.hooks=false'
    -c 'approval_policy=on-request'
    -c "approvals_reviewer=${CODEX_APPROVALS_REVIEWER:-auto_review}"
    -m "$model" -c "model_reasoning_effort=$effort" )
}

# Default flags for a FRESH `codex exec` turn (spawn or -o-only follow-up).
_codex_flags() {  # <model> <effort>
  _codex_flags_common "$1" "$2" --sandbox workspace-write
}

# Flags for `codex exec resume` — NOT the same sandbox flag as a fresh spawn:
# `codex exec resume` has no --sandbox option at all (confirmed live: rc=2,
# no JSON emitted, "error: unexpected argument '--sandbox' found" — see
# docs/doperpowers/specs/2026-07-10-codex-workers-design.md, Task 1 spike).
# Sandbox mode on resume goes through -c sandbox_mode=<mode> instead;
# everything else (network access, hooks, approvals, -m/effort) is identical.
_codex_resume_flags() {  # <model> <effort>
  _codex_flags_common "$1" "$2" -c 'sandbox_mode=workspace-write'
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

# Vendor doperpowers skills into <cwd> so the codex worker can read the full
# skill doctrine: codex scans <workspace>/.agents/skills/ and follows symlinks
# (verified live on codex-cli 0.144.1 — skills surface namespaced as
# doperpowers:<name>). This is the skills-parity seam the design spec noted
# ("Symphony vendors doperpowers there per-workspace"): claude workers get the
# plugin via the claude CLI; codex workers get this symlink. The exclude line
# goes to the repo's SHARED info/exclude (local, never committed) so the
# symlink is invisible to git status in every worktree — a worker can't
# accidentally commit it. Silently a no-op for non-git cwds and for repos
# that already have .agents/skills (tracked or previously vendored).
_codex_vendor_skills() {  # <cwd>
  local cwd="$1" lib skills_root ex
  git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1 || return 0
  if [ -e "$cwd/.agents/skills" ] || [ -L "$cwd/.agents/skills" ]; then return 0; fi
  lib="${CODEX_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
  skills_root="$(cd "$lib/../.." && pwd)"
  [ -d "$skills_root" ] || return 0
  mkdir -p "$cwd/.agents" 2>/dev/null || return 0
  ln -s "$skills_root" "$cwd/.agents/skills" 2>/dev/null || return 0
  ex="$(git -C "$cwd" rev-parse --git-path info/exclude 2>/dev/null)" || return 0
  case "$ex" in /*) ;; *) ex="$cwd/$ex" ;; esac
  mkdir -p "$(dirname "$ex")" 2>/dev/null || return 0
  grep -qxF '.agents/skills' "$ex" 2>/dev/null \
    || printf '%s\n' '.agents/skills' >> "$ex" 2>/dev/null || true
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

# Garbage-collect orphaned turn scratch under $DAEMON_HOME/runs. Each turn
# writes codex-run.XXXXXX.{task.txt,events.jsonl,reply.txt,err,pid,rc}; a resume
# points the meta's `event_log` at a NEW run, orphaning the previous one — so an
# actively-resumed daemon would otherwise grow the runs dir without bound. A run
# set is collectable when NO meta's `event_log` references its events.jsonl AND
# every file in the set is older than CODEX_RUNS_GC_AGE seconds (the age gate
# spares a run another spawn is still mid-registration on). Called
# opportunistically at spawn/resume; a no-op when runs/ is absent, and safe to
# call anytime.
_codex_gc_runs() {
  local runs="$DAEMON_HOME/runs"
  [ -d "$runs" ] || return 0
  DAEMON_HOME="$DAEMON_HOME" RUNS="$runs" AGE="${CODEX_RUNS_GC_AGE:-600}" python3 - <<'PY'
import glob, json, os, time
home = os.environ["DAEMON_HOME"]; runs = os.environ["RUNS"]
age = float(os.environ["AGE"]); now = time.time()
referenced = set()
for m in glob.glob(os.path.join(home, "*.json")):
    if m.endswith(".reply.json"):
        continue
    try:
        el = json.load(open(m)).get("event_log")
    except Exception:
        continue
    if el:
        referenced.add(os.path.realpath(el))
groups = {}
for f in glob.glob(os.path.join(runs, "codex-run.*")):
    parts = os.path.basename(f).split(".")
    prefix = os.path.join(runs, ".".join(parts[:2]))  # codex-run.XXXXXX
    groups.setdefault(prefix, []).append(f)
for prefix, files in groups.items():
    if os.path.realpath(prefix + ".events.jsonl") in referenced:
        continue
    try:
        newest = max(os.path.getmtime(f) for f in files)
    except OSError:
        continue
    if now - newest < age:
        continue
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass
PY
}

# Launch one detached codex turn: backgrounds codex inside a nohup'd wrapper
# that records the codex pid, waits for it, captures rc, and finalizes the
# registry (status + reply file) — the wrapper IS the watcher and survives the
# calling script. Args: <cwd> <taskfile> <run-prefix> then the codex argv after
# `codex` (e.g. exec --json ... or exec resume <id> ...). The -o/- redirection
# is appended here.
_codex_launch() {
  local cwd="$1" taskf="$2" run="$3"; shift 3
  # gh stores its token in the OS keychain, which codex's Seatbelt
  # workspace-write sandbox cannot read — so a worker's `gh` calls run
  # unauthenticated (HTTP 403) and the very first board write fails. Capture
  # the token HERE (the dispatcher's context has keychain access) and export
  # it as GH_TOKEN, which gh prefers over the keyring and the sandbox reads
  # from process env. This is auth parity with the un-sandboxed claude workers
  # (the standard CI pattern), and covers resume too since it shares this path.
  if [ -z "${GH_TOKEN:-}" ] && [ -z "${GITHUB_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
    local _tok; _tok="$(gh auth token 2>/dev/null || true)"
    if [ -n "$_tok" ]; then
      export GH_TOKEN="$_tok"
    else
      # Loud, not fatal: a worker without gh auth is doomed at its first
      # board write (or review-trail post), and that failure surfaces an
      # hour later. Warn the dispatcher now so it can abort/retry. Not an
      # abort: hermetic tests (fake HOME) and gh-less repos must still spawn.
      echo "codex-launch WARNING: no GitHub token captured (gh auth token empty) — the worker's gh calls will be unauthenticated" >&2
    fi
  fi
  # File-based TLS roots for the worker's children: a NESTED codex (e.g. the
  # review engine call) cannot reach the OS keychain/trustd under the
  # sandbox, so its rustls has no trust anchors and every connection dies
  # with `invalid peer certificate: UnknownIssuer`. /etc/ssl/cert.pem is the
  # sandbox-readable file bundle (verified live: nested exec fails without,
  # completes with). The outer codex itself is unsandboxed and unaffected.
  if [ -z "${SSL_CERT_FILE:-}" ] && [ -f /etc/ssl/cert.pem ]; then
    export SSL_CERT_FILE=/etc/ssl/cert.pem
  fi
  # A NESTED codex (e.g. review-engine.sh run by a codex worker) resolves
  # its code-mode command host to /usr/local/bin (absent here) instead of
  # ~/.local/bin — export the explicit path so nested engine calls can run
  # commands. Only when unset and the host binary exists.
  if [ -z "${CODEX_CODE_MODE_HOST_PATH:-}" ] && [ -x "$HOME/.local/bin/codex-code-mode-host" ]; then
    export CODEX_CODE_MODE_HOST_PATH="$HOME/.local/bin/codex-code-mode-host"
  fi
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
