#!/usr/bin/env bash
# test-lease-renewal.sh — spec acceptance 5, in real time. This is the ONE
# drill in the tier whose subject is the clock, so nothing here is aged in SQL:
# four runs are claimed on a ONE-MINUTE lease and the drill then sits through
# more than three lease windows while the sweep's renew phase runs on a timer,
# exactly as the unattended tick does.
#
# Four runs, so that every claim has its own control:
#
#   A  live session, RENEWED     → never reclaimed. The renewal is doing it.
#   B  dead session, not renewed → reclaimed, and it surfaces in the resume
#                                  feed. A dead worker's lease is deliberately
#                                  left to expire; that expiry IS the signal.
#   C  parked (needs-human), live, renewed → renewal on a parked-but-live run
#                                  is LEGAL, and the run stays open across the
#                                  whole horizon.
#   D  parked (needs-human), dead, NOT renewed → still never reclaimed. A
#                                  bound-pause park is a wait, not a death, and
#                                  D is what proves that survival is the park
#                                  rule rather than a side effect of renewal.
#
# The verdicts are read through the worker-visible surface: a reclaimed run's
# bearer stops authenticating (the revocation and the reclaim are one commit),
# a live one keeps working. No assertion touches the database.
#
# COST: ~3.5 minutes of wall clock, and it cannot be less — the service's write
# freshness window is 120s and is not configurable, and the spec asks for three
# lease windows. Everything else in the tier is seconds.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"

HORIZON="${A2_RENEWAL_HORIZON_SECS:-200}"   # > 3 × the one-minute lease
BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

A ticket with a real body, so birth lands in the executor queue.

## Success criteria

The drill can claim it.
MD
register() {  # register <title> <priority> — the priority IS the pick order
  in_repo "$SCRIPTS/board-register.sh" "$1" enhancement "$2" --body-file "$BODY" 2>&1 |
    awk 'END{print $1}'
}

# Registered in the order the server will hand them out (priority, then age),
# so each claim below lands on the ticket this drill means it to.
T_A="$(register 'renewal — live and renewed' P0)"
T_B="$(register 'renewal — dead and unrenewed' P1)"
T_C="$(register 'renewal — parked and live' P2)"
T_D="$(register 'renewal — parked and dead' P3)"

# The one-minute lease is the whole point of claiming through the route rather
# than through the dispatcher, which has no flag for it.
IFS=$'\t' read -r RUN_A TK_A FENCE_A BEAR_A <<<"$(claim_run executor renewal-a 1)"
IFS=$'\t' read -r RUN_B TK_B FENCE_B BEAR_B <<<"$(claim_run executor renewal-b 1)"
IFS=$'\t' read -r RUN_C TK_C FENCE_C BEAR_C <<<"$(claim_run executor renewal-c 1)"
IFS=$'\t' read -r RUN_D TK_D FENCE_D BEAR_D <<<"$(claim_run executor renewal-d 1)"
t "the claims landed on the four registered tickets in priority order" \
  "$T_A $T_B $T_C $T_D" printf '%s %s %s %s\n' "$TK_A" "$TK_B" "$TK_C" "$TK_D"

seed_meta sess-a "$TK_A" "$RUN_A" "$FENCE_A" "$BEAR_A"
seed_meta sess-b "$TK_B" "$RUN_B" "$FENCE_B" "$BEAR_B"
seed_meta sess-c "$TK_C" "$RUN_C" "$FENCE_C" "$BEAR_C"
seed_meta sess-d "$TK_D" "$RUN_D" "$FENCE_D" "$BEAR_D"
printf 'sess-b\nsess-d\n' >"$DEAD_FILE"    # the two sessions that are gone

# Each worker's own first write, through the real verb — which is also what
# arms `last_write_at`, the second liveness source the sweep has to outlast.
as_run() { in_repo BOARD_RUN_TOKEN="$1" BOARD_RUN_ID="$2" BOARD_RUN_FENCE="$3" "${@:4}"; }
as_run "$BEAR_A" "$RUN_A" "$FENCE_A" "$SCRIPTS/board-transition.sh" "$TK_A" in-progress >/dev/null
as_run "$BEAR_B" "$RUN_B" "$FENCE_B" "$SCRIPTS/board-transition.sh" "$TK_B" in-progress >/dev/null
as_run "$BEAR_C" "$RUN_C" "$FENCE_C" "$SCRIPTS/board-transition.sh" "$TK_C" in-progress >/dev/null
as_run "$BEAR_C" "$RUN_C" "$FENCE_C" "$SCRIPTS/board-transition.sh" "$TK_C" needs-human "waiting" >/dev/null
as_run "$BEAR_D" "$RUN_D" "$FENCE_D" "$SCRIPTS/board-transition.sh" "$TK_D" in-progress >/dev/null
as_run "$BEAR_D" "$RUN_D" "$FENCE_D" "$SCRIPTS/board-transition.sh" "$TK_D" needs-human "waiting" >/dev/null

# Renewal on a PARKED but live run, asked of the server directly: the ledger
# left this one unsettled, and it is the precondition the whole bound-pause
# park rests on — the sweep goes on renewing a parked worker's run for as long
# as the human takes.
t "the server renews a parked-but-live run" '"renewed":true' \
  api automation POST "/runs/$RUN_C/renew" '{}'

# ---- the horizon -----------------------------------------------------------
start="$SECONDS"
RENEWS=0
while [ $((SECONDS - start)) -lt "$HORIZON" ]; do
  sweep renew >>"$DRILL_TMP/renew.log" 2>&1 || true
  RENEWS=$((RENEWS + 1))
  sleep 20
done
renew_count() {  # the exact number drifts with how long each tick takes
  if [ "$RENEWS" -ge 8 ]; then echo "renews=enough ($RENEWS ticks over ${HORIZON}s)"
  else echo "renews=too-few ($RENEWS ticks over ${HORIZON}s)"; fi
}
t "the sweep ran the renew phase across more than three lease windows" \
  "renews=enough" renew_count
nt "and never reported a renewal failure" "error" cat "$DRILL_TMP/renew.log"

# ---- the verdicts ----------------------------------------------------------
feed="$(needing_resume_ids)"
t  "the dead unrenewed run's ticket surfaces for resume" "$TK_B" printf '%s\n' "$feed"
nt "the renewed run's ticket does not"                   "$TK_A" printf '%s\n' "$feed"
nt "nor either parked ticket"                            "$TK_C" printf '%s\n' "$feed"
nt "(both of them)"                                      "$TK_D" printf '%s\n' "$feed"

# The bearer is the worker-visible half of the same fact: reclaim ends the run
# and revokes its token in one commit.
t  "the renewed worker can still write"        "\"id\":$TK_A" api "$BEAR_A" GET /tickets
t  "the reclaimed worker's bearer is revoked"  "unauthenticated"   api "$BEAR_B" GET /tickets
t  "the parked live worker is untouched"       "\"id\":$TK_C" api "$BEAR_C" GET /tickets
t  "and so is the parked dead one — the park is a wait, not a death" \
   "\"id\":$TK_D"                                                   api "$BEAR_D" GET /tickets

# The renewal precondition, from the other side: a reaped run cannot be
# renewed back to life, and the sweep learns of the reap through that refusal.
t "an ended run refuses renewal rather than resurrecting" "run-ended" \
  api automation POST "/runs/$RUN_B/renew" '{}'

nt "no phase of the tick invokes the gh CLI" "GH INVOKED" cat "$GH_LOG"

finish
