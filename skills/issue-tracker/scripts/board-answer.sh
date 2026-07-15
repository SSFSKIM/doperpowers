#!/usr/bin/env bash
# board-answer.sh — relay a human's answers to a parked worker's BOUND session.
#
# Usage:
#   board-answer.sh <number> <answers>    # post answers as an [answers] comment, then relay
#   board-answer.sh <number> --posted     # answers already commented by hand — relay a pointer
#
# The wake ritual's needs-human path: park = pause, not death. The answers
# land on the TICKET first (the ticket is the record), the ticket returns to
# in-progress, and the bound session is resumed with the answers relayed
# verbatim — the worker keeps its orientation and re-states its gate verdict
# before proceeding. No judge is reintroduced: the relay is mechanical, the
# human is the author, the ticket is the record.
#
# Fresh-dispatch fallback (this script refuses; do it by hand): no bound
# session, a dead/retired session, or answers that reshape the ticket's scope
# → comment the answers, then `board-transition.sh <n> ready-for-agent`.
#
# NEVER RUN IN THE FOREGROUND — the resume blocks for the worker's whole turn
# (same rule as daemon-resume.sh / codex-resume.sh): Monitor or background
# shell.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" answers="$2" posted=""
if [ "$answers" = "--posted" ]; then posted=1 answers=""; fi
[ -n "$posted" ] || [ -n "$answers" ] || die "empty answers"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$SCRIPT_DIR/../../orchestrating-daemons/scripts}"
[ -d "$DAEMON_SCRIPTS" ] || die "orchestrating-daemons scripts not found at $DAEMON_SCRIPTS (set DAEMON_SCRIPTS)"

# Normalize a lingering finished Claude owner before the status gate. A real
# mid-turn remains working (`daemon-finalize` returns live); a finished
# state=working/status=idle turn becomes registry status=idle and is resumable.
bound_uuid="$(T_ID="$tid" T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob, json, os
for path in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if path.endswith(".reply.json"):
        continue
    try: meta=json.load(open(path))
    except Exception: continue
    if str(meta.get("ticket", "")).lstrip("#") == os.environ["T_ID"].lstrip("#"):
        print(meta.get("uuid") or "")
        break
PY
)"
finalize_state=""
if [ -n "$bound_uuid" ]; then
  finalize_state="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$bound_uuid" 2>/dev/null || true)"
  if [ "$finalize_state" = "absent" ]; then
    "$DAEMON_SCRIPTS/daemon-retire.sh" "$bound_uuid" >/dev/null 2>&1 || true
    die "#$tid's bound session ${bound_uuid:0:8} is gone — left needs-human; use the documented fresh-dispatch path"
  fi
fi

# Validate the park + find the binding; post the [answers] comment only once
# the relay is certain to proceed (a refused relay posts nothing — the human
# can still comment by hand and take the fresh-dispatch path).
info="$(T_ID="$tid" T_ANSWERS="$answers" T_DHOME="$DAEMON_HOME" _py - <<'PY' | tail -n 1
import glob
import json
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
state = tickets[tid]["state"]
if state != "needs-human":
    B.die("#%s is %s, not needs-human — board-answer relays needs-human parks only\n"
          "  (interactive-preferred -> attach/brainstorm; needs-info -> fold the "
          "research into the body, then ready-for-agent)" % (tid, state))
meta = None
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if str(m.get("ticket", "")).lstrip("#") == tid:
        meta = m
        break
if meta is None:
    B.die("#%s has no bound session — fresh dispatch instead: comment the answers, "
          "then board-transition.sh %s ready-for-agent" % (tid, tid))
status = meta.get("status") or ""
if status in ("working", "blocked"):
    B.die("#%s's bound session %s is mid-turn (status=%s) — nothing is waiting "
          "for answers; investigate with daemon-list.sh" %
          (tid, meta.get("uuid", "?"), status))
if status not in ("idle", "awaiting-human"):
    B.die("#%s's bound session %s is terminal (%s) — left needs-human; "
          "use the documented fresh-dispatch path" %
          (tid, meta.get("uuid", "?"), status or "unknown"))
if env["T_ANSWERS"]:
    B.comment(tid, "[answers] " + env["T_ANSWERS"])
print("%s\t%s\t%s\t%s" % (meta.get("uuid", ""), meta.get("engine", "claude"),
                          meta.get("status", "?"), meta.get("updated", "?")))
PY
)"
IFS=$'\t' read -r uuid engine status updated <<<"$info"
[ -n "$uuid" ] || die "binding lookup failed"
echo "relay: #$tid → $engine session ${uuid:0:8} (status=$status, last-updated=$updated)"

"$SCRIPT_DIR/board-transition.sh" "$tid" in-progress \
  "answers relayed — resuming bound session ${uuid:0:8}"

if [ -n "$posted" ]; then
  block="(already on the ticket — read the latest comments: gh issue view $tid --comments)"
else
  block="$answers"
fi
relay="Your needs-human park on ticket #$tid was answered by the human. The answers
live on the ticket — the ticket remains the record. Re-state your gate
verdict against them in ONE paragraph as a ticket comment (\"[gate] re-pass —
<one line>\", or a fresh park if the answers reshape the work's scope), then
proceed under your original protocol. Never build on momentum past an answer
that changed the work's shape.

---- answers (verbatim from the ticket) ----
$block"

case "$engine" in
  codex) exec "$DAEMON_SCRIPTS/codex-resume.sh" "$uuid" "$relay" ;;
  *)     exec "$DAEMON_SCRIPTS/daemon-resume.sh" "$uuid" "$relay" ;;
esac
