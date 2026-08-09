#!/usr/bin/env bash
# test-resume-first.sh — spec acceptance 4: with BOTH a reclaimed in-flight
# ticket and a ready-queue ticket in front of it, one `_sweep_api.sh all` tick
# serves the RESUME before it starts anything new.
#
# The ordering is the property, and it is observed where it actually shows: the
# stubbed daemon layer records every spawn and every resume into one sequence
# log, so "the recovery ran first" is read off the same file the two events
# land in, in the order they happened — not inferred from the tick's prose.
#
# What else this drill pins, because a resume that arrives first but arrives
# WRONG is no better than a late one:
#
#   * the successor is a claim-SUCCESSOR, not a fresh lane claim — the
#     predecessor's own session is resumed, which is the whole reason A1 hands
#     back a session locator;
#   * it carries FENCE + 1, so the predecessor's writes are fenced out;
#   * the successor prompt directs the worker to its own timeline, where the
#     park/answer history the claim body cannot carry lives.
#
# THE RECLAIM IS THE SERVICE'S OWN. This drill ages one run's lease in SQL and
# then waits for A1's reconciler to notice — the aging is fixture setup (the
# lease clock is drilled in test-lease-renewal.sh, not here), but the reclaim
# itself, the marker it appends and the feed entry it produces are the real
# service acting on its own authority.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"
DISPATCH="$REPO_ROOT/skills/implementing/scripts/implement-dispatch.sh"

BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

A ticket with a real body, so birth lands in the implementer queue.

## Success criteria

The drill can dispatch it.
MD
register() {
  in_repo "$SCRIPTS/board-register.sh" "$1" enhancement P2 --body-file "$BODY" 2>&1 |
    awk 'END{print $1}'
}

# ---- the reclaimed in-flight ticket ---------------------------------------
STUCK="$(register 'resume-first — the reclaimed ticket')"
in_repo "$DISPATCH" --sweep >"$DRILL_TMP/d1.out" 2>&1 || true
IFS=$'\t' read -r UUID RUN FENCE BEARER <<<"$(meta_of_ticket "$STUCK")"
[ -n "$BEARER" ] || { echo "FAIL $(basename "$0") — #$STUCK was never dispatched"; exit 1; }
in_repo BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$FENCE" \
  "$SCRIPTS/board-transition.sh" "$STUCK" in-progress >/dev/null

# Fixture: age the lease past its window and drop the write watermark, then let
# the reconciler do its own work.
sql >/dev/null <<SQL
update board.run set lease_expires_at = now() - interval '5 minutes', last_write_at = null
 where id = $RUN;
SQL
feed_has_stuck() { needing_resume_ids | grep -qxF "$STUCK"; }
wait_until 30 "the service to reclaim run $RUN" feed_has_stuck || exit 1
t "the reclaimed ticket is on the resume feed" "$STUCK" needing_resume_ids
t "and the board shows it unowned, still in flight" "in-progress" ticket_state "$STUCK"

# ---- the fresh ticket waiting behind it -----------------------------------
FRESH="$(register 'resume-first — the ready-queue ticket')"
t "the fresh ticket is queued" "ready-for-implementer" ticket_state "$FRESH"

# ---- one tick, both phases -------------------------------------------------
: >"$SEQ_LOG"
OUT="$DRILL_TMP/tick.out"
sweep all >"$OUT" 2>&1 || true

t "the reclaimed run is routed to the resume path, not renewed" \
  "ended (run-ended) — resume path" cat "$OUT"
t "a successor is claimed for the reclaimed ticket" "resume: #$STUCK run " cat "$OUT"
t "and delivered by resuming the predecessor's own session" "→ resumed session $UUID" cat "$OUT"
t "the fresh ticket is claimed in the same tick" "claimed #$FRESH run=" cat "$OUT"

# THE ORDERING. Both events are in one log, in the order the stubs saw them.
order() { grep -E "^(resume $UUID|spawn $FRESH-api-implementer)$" "$SEQ_LOG" | head -2 | tr '\n' '|'; }
t "the resume is delivered BEFORE any fresh worker is started" \
  "resume $UUID|spawn $FRESH-api-implementer|" order

# ---- and the successor is a real successor ---------------------------------
SUCC_FENCE=$((FENCE + 1))
t "the successor carries fence + 1" "BOARD_RUN_FENCE=$SUCC_FENCE" cat "$RESUME_LOG"
nt "on a run that is not the reclaimed one" "BOARD_RUN_ID=$RUN" cat "$RESUME_LOG"
t "the successor is told to read its own timeline first" \
  "board-show.sh $STUCK" cat "$PROJECTS/$UUID.jsonl"
# The successor run id, read off the tick's own report, so the ownership
# assertion below names the run this tick actually opened.
SUCC_RUN="$(sed -n "s/^resume: #$STUCK run \([0-9][0-9]*\) .*/\1/p" "$OUT" | head -1)"
owner_line() { echo "owner=$(ticket_owner "$1")"; }
t "and the board hands the ticket to that successor" "owner=$SUCC_RUN" owner_line "$STUCK"
t "with the ticket still in flight — a resume is not a re-queue" \
  "in-progress" ticket_state "$STUCK"

nt "the tick never invokes the gh CLI" "GH INVOKED" cat "$GH_LOG"

finish
