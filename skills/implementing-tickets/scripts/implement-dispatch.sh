#!/usr/bin/env bash
# implement-dispatch.sh — mechanical implement/spike dispatcher (the dispatch
# ritual of doperpowers:issue-tracker, automated; no model, no judgment).
#
# Usage:
#   implement-dispatch.sh <issue-number>   triggered mode (issue event / manual)
#   implement-dispatch.sh --sweep          catch-up: every ELIGIBLE ticket in
#                                          dispatch order, up to the cap
#
# Per ticket: re-verify eligibility from a fresh board snapshot (a trigger is
# a hint, never inherited trust), dedupe against the registry, render the
# worker bootstrap with every dispatcher-owned binding, spawn the daemon
# --no-wait in its own worktree, and bind it to the ticket. The worker's
# first board write is its own gate verdict — this script writes nothing to
# the board beyond the binding.
#
# Dedupe and the concurrency cap read the REGISTRY first (bound metas in
# status working/blocked/error), the board second: a just-spawned worker's
# meta exists before its gate verdict moves the ticket off ready-for-agent,
# so board-state-only counting would double-dispatch inside that window.
# An IDLE bound session never blocks a dispatch — re-dispatch is fresh
# context by doctrine, and board-bind strips the stale owner.
#
# Env:
#   LOCAL_REPO      canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO      owner/name (default: resolved from LOCAL_REPO via gh)
#   IMPLEMENT_MAX_CONCURRENT  implement/spike worker slot cap (default 5);
#                   review-pr-*/land-pr-* workers never count against it
#   WORKER_ENGINE   model route codex|claude (default codex); an engine:*
#                   ticket label wins over the env
#   CLODEX_SETTINGS gateway settings file for the codex route
#                   (default ~/.claude/clodex-settings.json)
#   CLODEX_EFFORT   reasoning effort for the codex route (default xhigh)
#   IMPLEMENT_MODEL optional model override (codex route defaults to fable,
#                   claude route to inherit)
#   BOARD_SCRIPTS / DAEMON_SCRIPTS / DAEMON_HOME / IMPLEMENT_BOOTSTRAP_TEMPLATE
#                   overrides (tests)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
export DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)}"
BOOTSTRAP_TEMPLATE="${IMPLEMENT_BOOTSTRAP_TEMPLATE:-$SKILL_DIR/references/worker-bootstrap.md}"
SPIKE_PROTOCOL="$SKILL_DIR/references/spike-worker-protocol.md"
IMPLEMENT_PROTOCOL="$SKILL_DIR/SKILL.md"
DECOMPOSE_DOC="$SKILL_DIR/references/implement-decompose.md"
CAP="${IMPLEMENT_MAX_CONCURRENT:-5}"

die() { echo "error: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"
export BOARD_REPO

# Board facts for ticket <1>, shell-quoted (state, eligibility, title, url,
# category, engine label). _board.py is the single eligibility authority —
# the same predicate board-list.sh tags ELIGIBLE.
_ticket_exports() {
  T_ID="$1" BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import os, shlex, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
tid = os.environ["T_ID"]
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
if tid not in tickets:
    q("T_STATE", "missing"); q("T_ELIGIBLE", 0)
    raise SystemExit(0)
n = tickets[tid]
q("T_STATE", n["state"])
q("T_ELIGIBLE", 1 if B.eligible(tickets, tid) else 0)
q("T_TITLE", n["title"]); q("T_URL", n["url"]); q("T_CATEGORY", n["category"])
eng = "claude" if "engine:claude" in n["labels"] else ("codex" if "engine:codex" in n["labels"] else "")
q("T_ENGINE_LABEL", eng)
import re
slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n["title"].lower())).strip("-")[:32].rstrip("-")
q("T_SLUG", slug or "ticket")
PY
}

# Newest registry meta bound to ticket <1> → "uuid|status|name" (empty if none).
_bound_meta() {
  T_ID="$1" python3 - <<'PY'
import glob, json, os
best = None
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if str(m.get("ticket", "")).lstrip("#") == os.environ["T_ID"]:
        key = str(m.get("updated") or m.get("created") or "")
        if best is None or key > best[0]:
            best = (key, m)
if best:
    m = best[1]
    print("%s|%s|%s" % (m.get("uuid", ""), m.get("status", ""), m.get("name", "")))
PY
}

# Occupied implement/spike slots: bound metas in an active status whose
# ticket is still in an active lane (ready-for-agent covers the pre-gate
# window; in-progress covers the build). Review/land species excluded, and a
# stale `working` meta on an in-review or parked ticket never eats a slot —
# that worker's scope ended when the ticket moved on.
_slots_used() {
  BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
used = 0
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if name.startswith("review-pr-") or name.startswith("land-pr-"):
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if not tk or m.get("status") not in ("working", "blocked", "error"):
        continue
    if tickets.get(tk, {}).get("state") in ("ready-for-agent", "in-progress"):
        used += 1
print(used)
PY
}

# ---- per-ticket dispatch -------------------------------------------------------
# Runs behind `||` in sweep mode (which suspends errexit through the call
# subtree), so every step is explicitly guarded and returns 1 on failure.
dispatch_one() {
  local n="$1" exports engine role protocol_file decompose prompt name spawn_out uuid meta status

  meta="$(_bound_meta "$n")"
  if [ -n "$meta" ]; then
    status="$(printf '%s' "$meta" | cut -d'|' -f2)"
    case "$status" in
      working|blocked|error)
        echo "skip #$n: bound worker ${meta%%|*} status=$status"
        return 0 ;;
    esac
  fi

  exports="$(_ticket_exports "$n")" \
    || { echo "#$n: board snapshot failed" >&2; return 1; }
  eval "$exports"
  if [ "${T_ELIGIBLE:-0}" != "1" ]; then
    echo "skip #$n: not eligible (state=${T_STATE:-unknown})"
    return 0
  fi

  if [ "$(_slots_used)" -ge "$CAP" ]; then
    echo "cap reached ($CAP): #$n stays queued for the next sweep"
    return 0
  fi

  engine="${T_ENGINE_LABEL:-}"
  [ -n "$engine" ] || engine="${WORKER_ENGINE:-codex}"

  if [ "$T_CATEGORY" = "spike" ]; then
    role="SPIKE"; protocol_file="$SPIKE_PROTOCOL"
    decompose="(none — spike lane)"
  else
    role="IMPLEMENT"; protocol_file="$IMPLEMENT_PROTOCOL"
    decompose="$DECOMPOSE_DOC"
  fi
  [ -f "$protocol_file" ] || { echo "#$n: protocol file missing: $protocol_file" >&2; return 1; }

  # The prompt carries bindings only — the worker reads its ticket (and the
  # repo's .doperpowers/repo-facts.md, if any) from gh / its own worktree.
  prompt="$(P_ROLE="$role" P_ISSUE_NUMBER="$n" P_ISSUE_URL="$T_URL" \
    P_REPO="$BOARD_REPO" P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
    P_ENGINE_NAME="$engine" P_PROTOCOL_FILE="$protocol_file" \
    P_DECOMPOSE_DOC="$decompose" \
    python3 - "$BOOTSTRAP_TEMPLATE" <<'PY'
import os, re, sys
t = open(sys.argv[1]).read()
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
out = re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), m.group(0)), t)
left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", out)))
if left:
    sys.stderr.write("unrendered placeholder(s): %s\n" % " ".join(left))
    sys.exit(1)
print(out)
PY
)" || { echo "#$n: prompt render failed (unrendered placeholder or template error)" >&2; return 1; }
  [ -n "$prompt" ] || { echo "#$n: empty prompt — not dispatching" >&2; return 1; }

  name="$n-$T_SLUG"
  # ONE worker harness, two model routes (same shape as review-dispatch):
  # codex = the clodex gateway settings (GPT models via the local proxy),
  # claude = plain Claude models.
  if [ "$engine" = "codex" ]; then
    spawn_out="$(DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" \
      DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "${IMPLEMENT_MODEL:-fable}")" \
      || { echo "#$n: worker spawn failed" >&2; return 1; }
  else
    spawn_out="$("$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "${IMPLEMENT_MODEL:-}")" \
      || { echo "#$n: worker spawn failed" >&2; return 1; }
  fi
  printf '%s\n' "$spawn_out"
  uuid="$(printf '%s\n' "$spawn_out" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
  [ -n "$uuid" ] || { echo "#$n: spawned worker UUID was not parseable" >&2; return 1; }

  local try=1 bound=""
  while [ "$try" -le "${IMPLEMENT_BIND_ATTEMPTS:-3}" ]; do
    if "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$n"; then bound=1; break; fi
    [ "$try" -lt "${IMPLEMENT_BIND_ATTEMPTS:-3}" ] && sleep "${IMPLEMENT_BIND_DELAY:-2}"
    try=$((try + 1))
  done
  if [ -z "$bound" ]; then
    "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
    echo "#$n: bind failed — worker retired (an unbindable worker cannot be answer-relayed)" >&2
    return 1
  fi
  echo "dispatched #$n → $name [$uuid] engine=$engine role=$role"
}

# ---- modes ---------------------------------------------------------------------
if [ "${1:-}" = "--sweep" ]; then
  BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY' |
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
def rank(tid):
    p = tickets[tid]["priority"]
    return (B.PRIORITIES.index(p) if p in B.PRIORITIES else len(B.PRIORITIES), int(tid))
for tid in sorted(tickets, key=rank):
    if B.eligible(tickets, tid):
        print(tid)
PY
  while IFS= read -r tid; do
    [ -n "$tid" ] || continue
    if [ "$(_slots_used)" -ge "$CAP" ]; then
      echo "cap reached ($CAP/$CAP): remaining eligible tickets stay queued"
      break
    fi
    dispatch_one "$tid" || echo "#$tid: dispatch error (continuing sweep)" >&2
  done
  exit 0
fi

[ $# -ge 1 ] || die "usage: implement-dispatch.sh <issue-number> | --sweep"
n="${1#\#}"
case "$n" in ""|*[!0-9]*) die "not an issue number: $1" ;; esac
dispatch_one "$n"
