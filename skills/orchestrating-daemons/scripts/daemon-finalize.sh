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
state="$(claude agents --json --all 2>/dev/null | CUR="$cur" python3 -c '
import json, os, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    rows = []
for r in rows:
    if r.get("sessionId") == os.environ["CUR"]:
        print(r.get("state") or "")
        break
')"

case "$state" in
  "")              echo "absent" ;;
  working|blocked) echo "live" ;;
  done)
    _record_reply "$cur" "$uuid" "done"
    _meta_set "$uuid" status "idle" updated "$(_now)"
    echo "idle" ;;
  error|stopped)
    _record_reply "$cur" "$uuid" "$state"
    _meta_set "$uuid" status "error" updated "$(_now)"
    echo "error" ;;
  # unknown/new harness states: claim nothing, finalize nothing
  *)               echo "live" ;;
esac
