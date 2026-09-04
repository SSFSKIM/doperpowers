#!/usr/bin/env bash
# board-answer.sh — relay a human's answers to a parked worker's BOUND session.
#
# Usage:
#   board-answer.sh <number> <answers>    # post answers as an [answers] comment, then relay
#   board-answer.sh <number> --posted     # answers already commented by hand — relay a pointer (gh mode)
#   board-answer.sh <number> <answers> --to <state>   # API mode, UNBOUND park only: the disposition
#
# The wake ritual's needs-human path: park = pause, not death. The answers
# land on the TICKET first (the ticket is the record), the ticket returns to
# its parking lane's in-flight state (pre-park: meta; when absent, the bound
# worker's own lane from its registry meta — in-design for an Architect,
# in-review for a QAgent with the ticket's recorded pr: re-supplied,
# in-progress otherwise; a review-lane return with no pr: to re-supply is
# REFUSED and the ticket stays parked), and the bound session is resumed with
# the answers relayed verbatim — the worker keeps its orientation and
# re-states its gate verdict before proceeding. No judge is reintroduced:
# the relay is mechanical, the human is the author, the ticket is the record.
#
# API binding: the park-answer call IS the record (no separate comment), and
# the RETURN STATE IS THE SERVER'S — it reads the bound run's lane, so none of
# the pre-park / role derivation below applies. A park nobody is bound to has
# no lane to return to: the server answers `409 no-return-mapping` and the
# human re-runs naming a disposition with --to (which the server refuses on a
# bound park, `answer-target-not-allowed` — the disagreement is surfaced, never
# silently resolved).
#
# Fresh-dispatch fallback (this script refuses; do it by hand): no bound
# session, a dead/retired session, or answers that reshape the ticket's scope
# → comment the answers, then `board-transition.sh <n> ready-for-implementer
# (or ready-for-architect per the park discriminant)`.
#
# NEVER RUN IN THE FOREGROUND — the resume blocks for the worker's whole turn
# (same rule as `sminos resume --wait`): Monitor or background shell.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1"; shift
answers="" posted="" to=""
# One unconditional loop (board-comment.sh's parser): options are options
# wherever they sit, the first bare token is the answers, and anything else
# dies — a mistyped flag that became the answer text would relay cleanly.
while [ $# -gt 0 ]; do case "$1" in
  --posted) posted=1; shift ;;
  --to) _need_arg "$1" "${2:-}"; to="$2"; shift 2 ;;
  --*) die "unknown option: $1" ;;
  *) [ -z "$answers" ] || die "unexpected argument: $1"
     answers="$1"; shift ;;
esac; done
[ -z "$posted" ] || [ -z "$answers" ] || \
  die "--posted takes no answers text — it relays a pointer to what is already on the ticket"
[ -n "$posted" ] || [ -n "$answers" ] || die "empty answers"

# ---- API binding: the answer IS the record ---------------------------------
# Dual-principal, the one scripted exception to fixed-token-per-script: the
# answer leg speaks HUMAN (`park-answer` admits no other principal), the relay
# and its ack speak AUTOMATION (`unrelayed`/`ack-answer` admit no human).
if [ "$BOARD_BINDING" = api ]; then
  [ -z "$posted" ] || die "--posted is gh-mode-only: an API park-answer IS the record — pass the answers"
  T_ID="$tid" T_ANSWERS="$answers" T_TO="$to" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_ID"].lstrip("#")
# Name the park being answered. Unnamed, the server answers whichever question
# happens to be STANDING when the request lands — so a delayed answer lands as
# the human's reply to a question nobody wrote it for. The queue publishes the
# name; the species filter matters because one ticket can carry an sdk-decision
# park alongside its board park, and only the board one is answerable here.
def find_cid():
    return next((q["correlation_id"] for q in A.queue_decisions_all()
                 if str(q["ticket_id"]) == tid and q.get("species") == "board"),
                None)

cid = find_cid()
if cid is None:
    # A park COMMITTING while the walk ran is invisible to that walk (its
    # transaction-start raised_at can land behind an already-passed cursor).
    # A second walk, started after the first finished, must serve any park
    # committed before it began — that retry is the queue's action-grade
    # absence evidence (spec § Helper primitives). Still None after it, and
    # the refusal below is standing on ground as firm as the old whole read.
    cid = find_cid()
if cid is None:
    # No name, no answer. Sending it unnamed is exactly the failure the
    # comment above forbids — the server would bind it to whatever question
    # is standing when it lands, which is worst in this case: the ticket's
    # board park is already gone (answered, superseded, or never raised).
    A.die("#%s has no standing board park in the decisions queue — nothing to "
          "answer here. Re-read the queue (GET /queue/decisions, or "
          "board-list.sh needs-human) and answer the park it names." % tid)
out = A.park_answer(tid, [os.environ["T_ANSWERS"]],
                    to=os.environ["T_TO"] or None, correlation_id=cid)
if out.get("superseded"):
    A.die("#%s: answer superseded — the standing question changed; re-read the queue" % tid)
print("answered #%s → %s" % (tid, out.get("returnedTo", "?")))
PY
  # Inline relay: the human's answer resumes the worker NOW, not on the next
  # tick — the same blocking feel as gh mode's direct resume. Delivery and its
  # delivery-gated ack are the sweep's, never a second copy of that logic here.
  #
  # A HELD TICK LOCK IS NOT A DELIVERY. The sweep exits 0 when another tick
  # holds it — correct for the sweep, and read as success here it told the
  # human their answer had been relayed when the wake had not run at all. The
  # promise is downgraded to what actually happened: the answer IS recorded
  # (that write already landed above), and the wake rides the next tick.
  _relay_out="$("$SCRIPT_DIR/_sweep_api.sh" relay 2>&1)" || true
  printf '%s\n' "$_relay_out"
  case "$_relay_out" in
    *"holds the lock"*)
      echo "note: another sweep tick holds the lock, so the inline wake did not run — #$tid's answer is recorded on the board and the next tick delivers it (that tick is the same relay, and the ack is delivery-gated either way)." ;;
  esac
  exit 0
fi
[ -z "$to" ] || die "--to is api-binding-only: in gh mode the return state comes from the ticket's pre-park meta (or the bound worker's lane)"

# SMINOS_CLI is resolved and the registry migrated by _lib.sh, sourced above:
# it fails closed there, once per process, before any script reads the root.
[ -x "$SMINOS_CLI" ] || die "the sminos CLI is not executable at $SMINOS_CLI (set SMINOS_CLI)"

# Normalize a lingering finished Claude owner before the status gate. A real
# mid-turn remains working (`sminos sync` returns live); a finished
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
  finalize_state="$("$SMINOS_CLI" sync "$bound_uuid" 2>/dev/null || true)"
  if [ "$finalize_state" = "absent" ]; then
    "$SMINOS_CLI" retire "$bound_uuid" >/dev/null 2>&1 || true
    die "#$tid's bound session ${bound_uuid:0:8} is gone — left needs-human; use the documented fresh-dispatch path"
  fi
  # A legacy codex-CLI worker has no resumable Claude session: the relay would
  # transition the ticket and then exec against a session that cannot be
  # continued. Refuse BEFORE any board write.
  if [ "$("$SMINOS_CLI" meta get "$bound_uuid" engine 2>/dev/null || true)" = "codex" ]; then
    die "#$tid is bound to a legacy codex worker ${bound_uuid:0:8} — retire it (sminos retire <id>) and use the fresh-dispatch path"
  fi
fi

# Validate the park + find the binding; post the [answers] comment only once
# the relay is certain to proceed (a refused relay posts nothing — the human
# can still comment by hand and take the fresh-dispatch path).
#
# A FUNCTION, not an inline "$(...)": bash 3.2 scans a command substitution
# with a matcher that does not understand the heredoc it contains, so every
# apostrophe in this prose — worker's, doesn't — toggles its quote state. At
# an ODD count the matcher is stuck in single-quote mode, stops counting
# parens, and the substitution fails to find its close. The old body survived
# on an even count; one more apostrophe of prose broke it. A function body
# goes through the real parser instead, so the prose here is free again.
_probe_binding() {
  T_ID="$tid" T_ANSWERS="$answers" T_DHOME="$DAEMON_HOME" _py - <<'PY' | tail -n 1
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
          "research into the body, then ready-for-implementer (or "
          "ready-for-architect per the park discriminant))" % (tid, state))
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
          "then board-transition.sh %s ready-for-implementer (or ready-for-architect "
          "per the park discriminant)" % (tid, tid))
status = meta.get("status") or ""
if status in ("working", "blocked"):
    B.die("#%s's bound session %s is mid-turn (status=%s) — nothing is waiting "
          "for answers; investigate with `sminos list`" %
          (tid, meta.get("uuid", "?"), status))
if status not in ("idle", "awaiting-human"):
    B.die("#%s's bound session %s is terminal (%s) — left needs-human; "
          "use the documented fresh-dispatch path" %
          (tid, meta.get("uuid", "?"), status or "unknown"))
if env["T_ANSWERS"]:
    B.comment(tid, "[answers] " + env["T_ANSWERS"])
else:
    # --posted: the human already commented on the ticket by hand — post a
    # marker anyway. The convergence rule (board-transition.sh) resets its
    # escalation count at the last comment starting with "[answers]"; with
    # no marker here that reset never fires on the sweep's relay path, and
    # a resumed worker's authorized retry of the same edge gets bounced
    # right back to needs-human (the exact bounce the human just answered).
    B.comment(tid, "[answers] relayed — see the human's comment on the "
                   "ticket (gh issue view %s --comments)" % tid)
pre_park = B.parse_meta(tickets[tid]["body"]).get("pre-park")
if pre_park:
    ret = pre_park
else:
    # No recorded pre-park: the park entered needs-human from a state
    # PRE_PARK doesn't cover (needs-info / interactive-preferred /
    # deferred — see _board.py's PRE_PARK). Fall back on the BOUND
    # WORKER's own lane, persisted into the registry meta at spawn time
    # (execute-dispatch.sh), rather than hardcoding in-progress: an
    # Architect resumed there would land in a state its protocol cannot
    # exit (LEGAL["in-progress"] has no ready-for-implementer edge).
    # Workers spawned by a route that stamps no role fall through to
    # in-progress, matching prior behavior — the default is only ever wrong
    # for a lane whose protocol cannot exit in-progress.
    role = (meta.get("role") or "").upper()
    if not role and str(meta.get("name") or "").startswith(("review-pr-",
                                                            "review-epic-")):
        # Reviewers bound before the role stamp: the deterministic worker
        # name is the only role record they carry.
        role = "QAGENT"
    if role == "ARCHITECT":
        ret = "in-design"
    elif role == "QAGENT":
        ret = "in-review"
    else:
        ret = "in-progress"
pr = ""
if ret == "in-review":
    # in-review is the one return state board-transition will not write on
    # trust: the ticket must carry a PR link, so the link is re-supplied from
    # the ticket's own pr: meta.
    pr = B.parse_meta(tickets[tid]["body"]).get("pr") or ""
    if not pr:
        # AND WHEN THERE IS NONE, THE PARK HOLDS. Demoting to in-progress and
        # resuming looked like the gentle fallback and was the stranding this
        # whole return exists to prevent: the reviewer wakes on a ticket in a
        # lane it owns no branch in and cannot exit, review-dispatch's
        # stale-reviewer arm retires its meta once idle, and the ticket sits
        # in-progress with no PR and nobody bound. A reviewer-lane ticket with
        # no pr: is an anomaly — the in-review entry gate stamps it — and an
        # anomaly pauses rather than guessing. The park is the safe state: the
        # answers are already posted (that comment lands before this), so the
        # human loses nothing by fixing the meta and re-running.
        B.die("#%s returns to the review lane but the ticket carries no pr: "
              "meta — the relay is REFUSED and #%s stays parked at "
              "needs-human. Your answers are already on the ticket, so "
              "nothing is lost: restore the pr: link in the body's "
              "board:meta block (board-body.sh splices that block through "
              "byte-for-byte, so edit it there), then re-run "
              "`board-answer.sh %s --posted`." % (tid, tid, tid))
print("%s\t%s\t%s\t%s\t%s\t%s" % (meta.get("uuid", ""), meta.get("engine", "claude"),
                                  meta.get("status", "?"), meta.get("updated", "?"),
                                  ret, pr))
PY
}
info="$(_probe_binding)"
IFS=$'\t' read -r uuid engine status updated ret pr <<<"$info"
[ -n "$uuid" ] || die "binding lookup failed"
echo "relay: #$tid → $engine session ${uuid:0:8} (status=$status, last-updated=$updated, return=$ret)"

# ret=in-review implies a non-empty pr (the python refuses the relay
# otherwise), so the flag arm never passes an empty link.
if [ "$ret" = in-review ]; then
  "$SCRIPT_DIR/board-transition.sh" "$tid" "$ret" \
    "answers relayed — resuming bound session ${uuid:0:8}" --pr "$pr"
else
  "$SCRIPT_DIR/board-transition.sh" "$tid" "$ret" \
    "answers relayed — resuming bound session ${uuid:0:8}"
fi

if [ -n "$posted" ]; then
  block="(already on the ticket — read the latest comments: gh issue view $tid --comments)"
else
  block="$answers"
fi
relay="Your needs-human park on ticket #$tid was answered by the human. The answers
live on the ticket — the ticket remains the record. Re-state your gate
verdict against them in ONE paragraph as a ticket comment (\"[gate] re-pass —
<one line>\" — PLAN-EXECUTION, which ran no gate, restates plan-execution
status instead), or a fresh park if the answers reshape the work's scope,
then proceed under your original protocol. Never build on momentum past an
answer that changed the work's shape.

---- answers (verbatim from the ticket) ----
$block"

exec "$SMINOS_CLI" resume --wait "$uuid" "$relay"
