#!/usr/bin/env bash
# test-escalation.sh — spec acceptance 6: with every delivery vehicle broken,
# the sweep gives up in a way a human can act on, and STOPS.
#
# The ladder, rung by rung, against the real service:
#
#   1-3. three recovery cycles fail (the session resume fails AND the fresh
#        spawn fails), each one releasing the successor run it could not use
#        rather than letting it squat the ticket to its lease;
#   3.   the third registers an env-issue — born `needs-human` server-side,
#        naming the stuck ticket — and writes a suppression record. Automation
#        holds NO transition authority in API mode, so the stuck ticket is
#        never parked: the env-issue IS the signal, and the drill pins that the
#        ticket is left exactly where it was;
#   4.   the suppression is honoured by BOTH readers — the resume phase skips
#        the ticket, and a dispatcher that draws it out of a lane hands the run
#        straight back;
#   5.   closing the env-issue lifts it, and the very next tick resumes the
#        ticket normally.
#
# Each cycle needs a ticket the server has genuinely reclaimed, so each one is
# armed the same way: claim through the real route, bind a session so the
# successor has a locator to resume, age the lease in SQL, and wait for A1's
# own reconciler to reclaim it. The aging is fixture setup — the lease clock is
# drilled in test-lease-renewal.sh — and everything after it is the service.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"

BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

A ticket with a real body, so birth lands in the implementer queue.

## Success criteria

The drill can claim it.
MD
TID="$(in_repo "$SCRIPTS/board-register.sh" 'escalation — the unrevivable ticket' \
  enhancement P2 --body-file "$BODY" 2>&1 | awk 'END{print $1}')"
SESS=sess-escalation
T_DH="$DAEMON_HOME" T_U="$SESS" python3 - <<'PY'
import json, os
u = os.environ["T_U"]
json.dump({"uuid": u, "current": u, "name": "escalation-worker", "status": "working"},
          open(os.path.join(os.environ["T_DH"], u + ".json"), "w"))
PY
: >"$PROJECTS/$SESS.jsonl"

# Arm one recovery cycle: a fresh run on the ticket, bound to the session, then
# reclaimed by the service. Prints nothing; leaves the ticket on the feed.
CYCLE=0
arm_cycle() {
  local run fence bearer tk
  CYCLE=$((CYCLE + 1))
  IFS=$'\t' read -r run tk fence bearer <<<"$(claim_run implementer "escalation-$CYCLE")"
  [ "$tk" = "$TID" ] || { echo "FAIL $(basename "$0") — cycle $CYCLE claimed #$tk, not #$TID"; exit 1; }
  in_repo BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
    "$SCRIPTS/board-bind.sh" "$SESS" "$TID" >/dev/null
  # The ticket only has to be moved in-flight once; a claim is not a transition.
  [ "$(ticket_state "$TID")" = in-progress ] || \
    in_repo BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
      "$SCRIPTS/board-transition.sh" "$TID" in-progress >/dev/null
  sql >/dev/null <<SQL
update board.run set lease_expires_at = now() - interval '5 minutes', last_write_at = null
 where id = $run;
SQL
  # The token rides the ENVIRONMENT, never the command line: a `bash -c` string
  # holding it is visible in `ps` to every process on the box for as long as the
  # poll runs, and this loop runs for up to thirty seconds a cycle.
  wait_until 30 "the service to reclaim run $run (cycle $CYCLE)" \
    env T_TOK="$AUTOMATION_TOKEN" T_URL="$BOARD_API_URL" T_TID="$TID" bash -c \
      'curl -s -H "authorization: Bearer $T_TOK" "$T_URL/runs/needing-resume" \
         | grep -q "\"ticketId\":$T_TID[,}]"' || exit 1
}
broken_resume() { in_repo RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 "$SCRIPTS/_sweep_api.sh" resume; }
# `eol` because the record is JSON the drill did not author: `"env_issue": 9`
# ENDS its line, so only an explicit terminator keeps it from matching 90.
suppression() { eol "$DAEMON_HOME/board-suppress/$TID.json" 2>/dev/null || echo "no suppression record"; }

# ---- cycles 1 and 2: counted, never escalated -----------------------------
arm_cycle
OUT1="$DRILL_TMP/cycle1.out"; broken_resume >"$OUT1" 2>&1 || true
t  "cycle 1 is counted"                         "recovery cycle 1 of 3"    cat "$OUT1"
t  "neither vehicle delivered"                  "neither vehicle delivered" cat "$OUT1"
t  "and the undeliverable successor is released, not left to squat" \
   "owner=[None]"                               owner_line "$TID"
nt "nothing is escalated yet"                   "env-issue"                cat "$OUT1"
t  "and no suppression record is written"       "no suppression record"    suppression

arm_cycle
OUT2="$DRILL_TMP/cycle2.out"; broken_resume >"$OUT2" 2>&1 || true
t  "cycle 2 is counted"                         "recovery cycle 2 of 3"    cat "$OUT2"
nt "and still escalates nothing"                "env-issue"                cat "$OUT2"

# ---- cycle 3: the escalation ----------------------------------------------
arm_cycle
OUT3="$DRILL_TMP/cycle3.out"; broken_resume >"$OUT3" 2>&1 || true
t "cycle 3 is counted"                          "recovery cycle 3 of 3"    cat "$OUT3"
t "and escalates to an env-issue"               "escalated #$TID → env-issue #" cat "$OUT3"
EID="$(sed -n "s/.*env-issue #\([0-9][0-9]*\).*/\1/p" "$OUT3" | head -1)"
t "the env-issue is born needs-human"           "#$EID needs-human"        in_repo "$SCRIPTS/board-list.sh"
t "and names the stuck ticket"                  "ticket #$TID cannot be revived" \
  in_repo "$SCRIPTS/board-list.sh"
t "the suppression record freezes the board state it stuck in" '"state": "in-progress",' suppression
t "and names the env-issue that lifts it"       "\"env_issue\": $EID;"     suppression
# Automation holds no transition authority — the ticket is left where it was.
t "the stuck ticket is NOT parked by automation" "in-progress"             ticket_state "$TID"

# ---- the suppression is honoured by both readers --------------------------
arm_cycle
OUT4="$DRILL_TMP/cycle4.out"; broken_resume >"$OUT4" 2>&1 || true
t  "a suppressed ticket is skipped by the resume phase" "suppressed — skipping #$TID" cat "$OUT4"
nt "and no cycle is charged for a ticket nobody tried"  "recovery cycle"   cat "$OUT4"
t  "so no successor is opened on it"                    "owner=[None]"     owner_line "$TID"

OUT5="$DRILL_TMP/dispatch.out"
sweep dispatch >"$OUT5" 2>&1 || true
t "a dispatcher that draws a suppressed ticket hands the run straight back" \
  "#$TID is suppressed — releasing run"          cat "$OUT5"
t "and that lane stands down for the tick"       "stands down this tick"   cat "$OUT5"
t "leaving the ticket unowned"                   "owner=[None]"            owner_line "$TID"

# ---- the human fixes the substrate and closes the env-issue ---------------
arm_cycle
t "the human closes the env-issue" "#$EID: → wontfix" \
  in_repo "$SCRIPTS/board-transition.sh" "$EID" wontfix "substrate repaired"
OUT6="$DRILL_TMP/lifted.out"
sweep resume >"$OUT6" 2>&1 || true
t "the suppression lifts on the closed env-issue" \
  "suppression lifted for #$TID — the env-issue closed"   cat "$OUT6"
t "and the very next tick resumes the ticket normally"    "→ resumed session $SESS" cat "$OUT6"
t "the record is gone"                                    "no suppression record"   suppression

nt "no rung of the ladder invokes the gh CLI" "GH INVOKED" cat "$GH_LOG"

finish
