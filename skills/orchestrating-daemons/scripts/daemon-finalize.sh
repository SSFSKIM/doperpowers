#!/usr/bin/env bash
# daemon-finalize.sh <short-or-full-uuid>
#
# Record a finished `--bg` turn's reply and terminal status into the registry.
# The codex species self-finalized (its runner wrote rc + reply when the exec
# ended); a claude-species --no-wait daemon has NO finisher — daemon-reply.sh
# only reads, so the meta stays status=working forever and a finished worker
# is indistinguishable from a live one to dispatch dedupe. Callers (e.g.
# review-dispatch.sh) invoke this before deciding skip/respawn.
#
# Prints ONE word describing the effective state:
#   noop    meta already terminal, or a codex-engine daemon (self-finalizing)
#   live    the current turn is still running or prompt-blocked (resumable)
#   absent  the session is gone from `claude agents` — meta left untouched
#           (the caller owns the dead-worker path)
#   idle    turn was done → reply recorded, meta finalized idle
#   error   turn errored/stopped → reply recorded, meta finalized error
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-finalize.sh <short-or-uuid>}")"
[ "$(_meta_get "$uuid" engine)" = "codex" ] && { echo "noop"; exit 0; }
status="$(_meta_get "$uuid" status)"
case "$status" in working|blocked) ;; *) echo "noop"; exit 0 ;; esac

cur="$(_meta_get "$uuid" current)"; [ -n "$cur" ] || cur="$uuid"
# `state` alone lies for a finished session whose harness process lingers —
# it stays "working" (observed live 2026-07-15 on a finished review worker)
# or "blocked" (observed live 2026-07-17 on a cleanly-parked gateway implement
# worker) indefinitely. `status` is the turn signal (busy while a turn runs,
# idle after); normalize both lingering shapes before the case table. An ended
# blocked-shape turn finalizes through the blocked reply renderer: when the
# transcript ends on a pending AskUserQuestion the question surfaces in the
# reply, otherwise the recorded reply is the turn text with the harness-prompt
# marker — either way the session is over and resumable.
state="$(claude agents --json --all 2>/dev/null | CUR="$cur" python3 -c '
import json, os, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    rows = []
for r in rows:
    if r.get("sessionId") == os.environ["CUR"]:
        st = r.get("state") or ""
        if r.get("status") == "idle" and st in ("working", "blocked"):
            st = "done" if st == "working" else "done-blocked"
        print(st)
        break
')"

case "$state" in
  "")              echo "absent" ;;
  working|blocked) echo "live" ;;
  done)
    _record_reply "$cur" "$uuid" "done"
    _meta_set "$uuid" status "idle" updated "$(_now)"
    echo "idle" ;;
  done-blocked)
    _record_reply "$cur" "$uuid" "blocked"
    _meta_set "$uuid" status "idle" updated "$(_now)"
    echo "idle" ;;
  error|stopped)
    _record_reply "$cur" "$uuid" "$state"
    _meta_set "$uuid" status "error" updated "$(_now)"
    echo "error" ;;
  # unknown/new harness states: claim nothing, finalize nothing
  *)               echo "live" ;;
esac
