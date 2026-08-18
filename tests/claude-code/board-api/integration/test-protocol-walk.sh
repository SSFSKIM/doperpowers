#!/usr/bin/env bash
# test-protocol-walk.sh — spec acceptance 1: the WHOLE worker protocol, once,
# through the unchanged verb scripts, against a real A1 board-service.
#
# What this drill PROVES that the unit tier cannot: every payload the fixture
# mock happily accepted is now judged by the real state machine, in sequence,
# with each step's legality resting on the state the previous step actually
# wrote. The walk is
#
#   register (human) → claim + spawn + bind (execute-dispatch, API mode)
#     → gate verdict (in-progress + [gate] comment, as the RUN)
#     → park needs-human → human answer → relay resume into the bound session
#     → in-review with a PR → the human's closing verdict → done
#
# and three server-side properties ride along, each of which the unit tier
# could only assume because a mock answers whatever it is told to:
#
#   * OWNER EXCLUSIVITY. While the run owns the ticket, a second claim on the
#     same lane is answered `claimed:false` — the mock had no owner concept.
#   * THE FENCE IS REAL. The worker's writes carry the fence the claim granted;
#     the server compares it against both the run and the ticket.
#   * THE PARK IS A PAUSE. needs-human keeps the run bound, which is what makes
#     the answer resume THIS session rather than dispatch a new one.
#
# And the acceptance's own assertion: the gh CLI is never invoked. A `gh` stub
# sits ahead of any real one on PATH for the whole walk and records every call
# it is given; the log must be empty at the end.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"
DISPATCH="$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh"

# ---- register (human) ------------------------------------------------------
BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

The protocol walk needs one ticket carrying a real body, so the server's
pre-spec demotion does not fire and the ticket is born dispatchable.

## Success criteria

The walk reaches `done` with every write going through the API.
MD
reg="$(in_repo "$SCRIPTS/board-register.sh" "protocol walk ticket" enhancement P1 \
  --body-file "$BODY" 2>&1)" || true
t "register reports the ticket and its API url" "$BOARD_API_URL/tickets/" printf '%s\n' "$reg"
TID="$(printf '%s\n' "$reg" | awk 'END{print $1}')"
t "born into the executor queue" "ready-for-implementer" ticket_state "$TID"

# ---- claim → spawn → bind --------------------------------------------------
OUT_D="$DRILL_TMP/dispatch.out"
in_repo "$DISPATCH" --sweep >"$OUT_D" 2>&1 || true
t "the executor lane claims the ticket" "claimed #$TID run=" cat "$OUT_D"
t "and hands it to a worker on its own lane" "lane=implementer" cat "$OUT_D"
t "the worker is spawned with the run bearer in env" "BOARD_RUN_TOKEN=" cat "$SPAWN_LOG"
t "and with the api url"  "BOARD_API_URL=$BOARD_API_URL" cat "$SPAWN_LOG"
t "the bootstrap points the worker at its delivered assignment" \
  "delivered by the claim that dispatched you" cat "$SPAWN_LOG"
# The claim response is by contract the only route a run has to its own ticket
# text, and the API path delivers it as a file rather than inline.
claim_body() { cat "$DAEMON_HOME"/board-claims/*.body.md; }
t "and that assignment is the ticket body the human registered" \
  "The protocol walk needs one ticket carrying a real body" claim_body

IFS=$'\t' read -r UUID RUN FENCE BEARER <<<"$(meta_of_ticket "$TID")"
[ -n "$BEARER" ] || { echo "FAIL $(basename "$0") — no run bearer at rest; the walk cannot speak as the run"; exit 1; }
bind_confirmed() { T_P="$DAEMON_HOME/$UUID.json" python3 -c '
import json, os
print("bind_confirmed=%s" % json.load(open(os.environ["T_P"])).get("bind_confirmed"))'; }
t "the bind is confirmed by the SERVER, not assumed locally" "bind_confirmed=True" bind_confirmed
t "the server records the run as the ticket's owner" "owner=[$RUN]" owner_line "$TID"

# OWNER EXCLUSIVITY, server-side: a second dispatch tick finds nothing to take.
OUT_D2="$DRILL_TMP/dispatch2.out"
in_repo "$DISPATCH" --sweep >"$OUT_D2" 2>&1 || true
nt "an owned ticket is not claimed a second time" "claimed #$TID run=" cat "$OUT_D2"
t  "a bare claim on the lane answers empty" '"claimed":false' \
   api automation POST /runs/claim '{"lane":"implementer","dispatchNonce":"walk-exclusivity-probe"}'

# ---- the worker's own writes, as the RUN -----------------------------------
worker() { in_repo BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$FENCE" "$@"; }

t "the gate verdict moves the ticket in-flight" "#$TID: → in-progress" \
  worker "$SCRIPTS/board-transition.sh" "$TID" in-progress
worker "$SCRIPTS/board-comment.sh" "$TID" "[gate] pass — scripted" >/dev/null 2>&1 || true
t "the worker's gate comment lands on the ticket's ledger" "[gate] pass — scripted" \
  api automation GET "/tickets/$TID/timeline"
t "a write carrying the WRONG fence is refused" "fence-mismatch" \
  in_repo BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$((FENCE + 7))" \
    "$SCRIPTS/board-transition.sh" "$TID" needs-human "wrong fence"
t "the park is written" "#$TID: → needs-human" \
  worker "$SCRIPTS/board-transition.sh" "$TID" needs-human "which db?"
t "the park keeps its run bound — it is a pause, not a death" "owner=[$RUN]" owner_line "$TID"
t "and the question reaches the decisions queue" "\"ticket_id\":$TID," \
  api human GET /queue/decisions

# THE PARK IS THE HUMAN'S TO ANSWER — and nothing local enforces that.
# board-answer.sh does NOT unset BOARD_RUN_TOKEN on its human legs, so a worker
# that ran the verb from inside its own run context speaks as the RUN on every
# one of them. The whole safety of that rests on the server, which is what these
# two probes confirm live rather than taking on API.md's word.
t "the answer verb run as the RUN is refused, not quietly re-signed" \
  "refused: forbidden" worker "$SCRIPTS/board-answer.sh" "$TID" "I answer my own park"
# The verb dies on its first human leg — the decisions queue admits no run
# either — so the route the deferral actually named is probed head-on. A refused
# call writes nothing: no answer event, no ack, no state change.
t "and park-answer itself admits no run principal" "run may not park-answer" \
  api "$BEARER" POST "/tickets/$TID/park-answer" '{"replies":["I answer my own park"]}'
t "so the park still stands, unanswered" "needs-human" ticket_state "$TID"

# ---- the human answers; the relay resumes the BOUND session ----------------
OUT_A="$DRILL_TMP/answer.out"
in_repo "$SCRIPTS/board-answer.sh" "$TID" "sqlite" >"$OUT_A" 2>&1 || true
t "the answer returns the ticket to the parking lane's in-flight state" \
  "answered #$TID → in-progress" cat "$OUT_A"
t "the relay delivers into the session that was parked" "delivered to $UUID" cat "$OUT_A"
TRANSCRIPT="$PROJECTS/$UUID.jsonl"
t "the resumed worker sees the relay sentinel" "[board-relay answer:" cat "$TRANSCRIPT"
t "with the human's answer verbatim" "sqlite" cat "$TRANSCRIPT"
t "and is told to re-state its gate verdict" "Re-state your gate verdict" cat "$TRANSCRIPT"
t "a delivered answer is acked — the feed drains" "[]" api automation GET /answers/unrelayed

# ---- the worker finishes; the human closes ---------------------------------
t "in-review requires the artifact and takes it" "#$TID: → in-review" \
  worker "$SCRIPTS/board-transition.sh" "$TID" in-review --pr https://example.test/pr/1
# The crossing ENDED the run server-side, and the bearer died with the commit.
t "the ended run's bearer is revoked" "unauthenticated" \
  api "$BEARER" GET /tickets
# THE VERDICT IS THE CLOSE. `confident-ready` was retired from this fork's
# state machine (the Reviewer worker merges what it is confident about, and the
# merge closes the ticket), so the walk takes `in-review → done` — the one
# in-review exit both canons still hold. A1's LEGAL_ROWS keeps a
# `in-review → confident-ready` row it no longer has a client for; that
# divergence is booked as the legality-drift follow-up, and a drill whose
# purpose is cross-binding parity must not walk an edge only one side knows.
t "the human's verdict closes the ticket" "#$TID: → done" \
  in_repo "$SCRIPTS/board-transition.sh" "$TID" "done"

t "the board shows the ticket done" "#$TID done" in_repo "$SCRIPTS/board-list.sh"
# The timeline is the ticket's history in API mode — the whole walk is in it.
SHOW="$DRILL_TMP/show.out"
in_repo "$SCRIPTS/board-show.sh" "$TID" >"$SHOW" 2>&1 || true
t "the timeline records the claim"     "] claim"   cat "$SHOW"
t "the gate comment"                   "] comment" cat "$SHOW"
t "the human's answer"                 "] answer"  cat "$SHOW"
t "and the release when the run ended" "] release" cat "$SHOW"

# ---- the acceptance's own assertion ---------------------------------------
nt "the gh CLI is never invoked across the whole walk" "GH INVOKED" cat "$GH_LOG"

finish
