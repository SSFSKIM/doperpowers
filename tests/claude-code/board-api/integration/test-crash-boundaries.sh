#!/usr/bin/env bash
# test-crash-boundaries.sh — spec acceptance 3, widened to the boundary the
# ledger actually worried about: every point where the machinery can die
# holding half a hand-off, and what the next tick does about it.
#
# SIX boundaries, three on each side of the relay/dispatch split. In every one
# the death is REAL — the stub exits 137 mid-delivery, or kills the dispatcher
# outright between the spawn and the bind — and the convergence is judged
# against the real service, not a fixture.
#
#   RELAY
#     a. dead before the injection      → nothing delivered, nothing acked, and
#                                         the answer is still on the feed.
#     b. dead after the injection       → the prompt landed exactly once and is
#                                         STILL unacked; the next tick acks it
#                                         off the transcript WITHOUT re-sending.
#     c. after the ack                  → the feed is empty and the sentinel
#                                         count never moves again.
#   DISPATCH
#     d. claim answered, response lost  → the journal replays THE SAME nonce and
#                                         the server hands back THE SAME run —
#                                         never a second claim on the ticket.
#     e. run claimed, never spawned     → the run is ended and the ticket goes
#                                         back to its queue rather than sitting
#                                         out a 15-minute lease.
#     f. spawned, never bound           → the run is NOT ended and no second
#                                         worker is spawned: a live session is
#                                         holding it, and killing that is how a
#                                         crash becomes two workers on one run.
#
# The sentinel count in the session transcript is the acceptance's own
# instrument: it is what "never lost, never double-resumed" is measured with.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"
DISPATCH="$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh"

BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

A ticket with a real body, so birth lands in the executor queue.

## Success criteria

The drill can dispatch it.
MD

register() {  # register <title> — prints the ticket id
  in_repo "$SCRIPTS/board-register.sh" "$1" enhancement P2 --body-file "$BODY" 2>&1 |
    awk 'END{print $1}'
}
sentinels() { printf 'sentinels=%s\n' \
  "$(grep -c 'board-relay answer:' "$1" 2>/dev/null || echo 0)"; }

# ===========================================================================
# RELAY BOUNDARIES — one ticket, parked and answered, killed at each point.
# ===========================================================================
T1="$(register 'crash drill — relay boundaries')"
in_repo "$DISPATCH" --sweep >"$DRILL_TMP/d1.out" 2>&1 || true
IFS=$'\t' read -r UUID RUN FENCE BEARER <<<"$(meta_of_ticket "$T1")"
[ -n "$BEARER" ] || { echo "FAIL $(basename "$0") — #$T1 was never dispatched"; exit 1; }
TRANSCRIPT="$PROJECTS/$UUID.jsonl"
worker() { in_repo BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$FENCE" "$@"; }
worker "$SCRIPTS/board-transition.sh" "$T1" in-progress >/dev/null
worker "$SCRIPTS/board-transition.sh" "$T1" needs-human "which db?" >/dev/null

# ---- (a) dead BEFORE the injection ----------------------------------------
OUT_A="$DRILL_TMP/relay-a.out"
in_repo RESUME_DIE_BEFORE=1 "$SCRIPTS/board-answer.sh" "$T1" "sqlite" >"$OUT_A" 2>&1 || true
t  "the human's answer is recorded even though the relay dies" \
   "answered #$T1 → in-progress"                       cat "$OUT_A"
t  "the failed delivery is reported, not swallowed"    "returned no delivery"   cat "$OUT_A"
t  "an undelivered answer stays on the feed"           "\"ticketId\":$T1," \
   api automation GET "/answers/unrelayed?repo=$(drill_repo_key)"
t  "and nothing reached the worker"                    "sentinels=0"     sentinels "$TRANSCRIPT"

# ---- (b) dead AFTER the injection, before the ack -------------------------
OUT_B="$DRILL_TMP/relay-b.out"
in_repo RESUME_DIE_AFTER=1 "$SCRIPTS/_sweep_api.sh" relay >"$OUT_B" 2>&1 || true
t  "a death after the injection still reports a failed resume" \
   "returned no delivery"                                     cat "$OUT_B"
t  "the prompt landed exactly once"                    "sentinels=1"     sentinels "$TRANSCRIPT"
t  "and the answer is STILL unacked — never ack-and-drop" "\"ticketId\":$T1," \
   api automation GET "/answers/unrelayed?repo=$(drill_repo_key)"

OUT_B2="$DRILL_TMP/relay-b2.out"
in_repo "$SCRIPTS/_sweep_api.sh" relay >"$OUT_B2" 2>&1 || true
t  "the next tick sees the sentinel and acks off it"   "already delivered (sentinel)" cat "$OUT_B2"
t  "WITHOUT re-delivering — no double resume"          "sentinels=1"     sentinels "$TRANSCRIPT"
t  "the feed is drained"                               "[]"              api automation GET "/answers/unrelayed?repo=$(drill_repo_key)"

# ---- (c) after the ack -----------------------------------------------------
OUT_C="$DRILL_TMP/relay-c.out"
in_repo "$SCRIPTS/_sweep_api.sh" relay >"$OUT_C" 2>&1 || true
nt "an acked answer is never served again"             "$T1 answer"      cat "$OUT_C"
t  "and the transcript is untouched"                   "sentinels=1"     sentinels "$TRANSCRIPT"

# ===========================================================================
# DISPATCH BOUNDARIES — the claim journal is the crash record; each case is
# the state a death at that point leaves behind, and what the next tick does.
# ===========================================================================
CLAIMS="$DAEMON_HOME/board-claims"

# ---- (d) the claim landed; its response did not ---------------------------
# The dispatcher journals the nonce BEFORE the POST, so this is exactly what a
# death between the two leaves: a nonce with no run id, beside a run the server
# has already granted.
T2="$(register 'crash drill — lost claim response')"
NONCE_D="crash-drill-lost-response"
RUN_D="$(api automation POST /runs/claim \
  "{\"lane\":\"implementer\",\"dispatchNonce\":\"$NONCE_D\",\"repo\":\"$(drill_repo_key)\"}" | jget runId)"
mkdir -p "$CLAIMS"
printf '{"lane": "implementer", "run_id": null, "spawn_completed": false}\n' \
  >"$CLAIMS/$NONCE_D.json"
OUT_D="$DRILL_TMP/dispatch-d.out"
in_repo "$DISPATCH" --sweep >"$OUT_D" 2>&1 || true
t  "the orphaned nonce is replayed, not re-claimed"    "never reached a run — replaying the claim" cat "$OUT_D"
t  "and the server answers the SAME run"               "BOARD_RUN_ID=$RUN_D;" eol "$SPAWN_LOG"
t  "so the ticket still has exactly one owner"         "owner=[$RUN_D]" owner_line "$T2"

# ---- (e) the run was claimed and never spawned ----------------------------
T3="$(register 'crash drill — claimed but never spawned')"
NONCE_E="crash-drill-never-spawned"
RUN_E="$(api automation POST /runs/claim \
  "{\"lane\":\"implementer\",\"dispatchNonce\":\"$NONCE_E\",\"repo\":\"$(drill_repo_key)\"}" | jget runId)"
printf '{"lane": "implementer", "run_id": %s, "spawn_completed": false, "ticket": "%s"}\n' \
  "$RUN_E" "$T3" >"$CLAIMS/$NONCE_E.json"
OUT_E="$DRILL_TMP/dispatch-e.out"
in_repo "$DISPATCH" --sweep >"$OUT_E" 2>&1 || true
t  "a run nothing local can vouch for is ended"        "claimed run $RUN_E but never spawned — ending it" cat "$OUT_E"
t  "and the freed ticket is dispatched afresh"         "claimed #$T3 run=" cat "$OUT_E"
nt "on a NEW run — the ended one never reaches a worker" "owner=[$RUN_E]" owner_line "$T3"

# ---- (f) spawned, and the dispatcher died before the bind -----------------
# SPAWN_KILL_PARENT makes the stub kill the dispatcher after the session is
# registered — a detached worker is already alive, holding the run, and no bind
# has landed. This is the one boundary where doing something is worse than
# doing nothing.
T4="$(register 'crash drill — spawned but never bound')"
OUT_F1="$DRILL_TMP/dispatch-f1.out"
in_repo SPAWN_KILL_PARENT=1 "$DISPATCH" --sweep >"$OUT_F1" 2>&1 || true
RUN_F="$(api automation GET /tickets | T_ID="$T4" python3 -c '
import json, os, sys
print(next((str(t["owner_run"]) for t in json.load(sys.stdin) if str(t["id"]) == os.environ["T_ID"]), ""))')"
[ -n "$RUN_F" ] || { echo "FAIL $(basename "$0") — #$T4 was never claimed; case (f) has no boundary to test"; exit 1; }
before_f="$(grep -c "SPAWN name=$T4-api-implementer" "$SPAWN_LOG" || true)"
OUT_F2="$DRILL_TMP/dispatch-f2.out"
in_repo "$DISPATCH" --sweep >"$OUT_F2" 2>&1 || true
t  "a spawned-but-unbound session is reported"         "but never bound it" cat "$OUT_F2"
t  "and explicitly NOT ended"                          "is NOT being ended" cat "$OUT_F2"
t  "the live run still owns its ticket"                "owner=[$RUN_F]" owner_line "$T4"
after_f="$(grep -c "SPAWN name=$T4-api-implementer" "$SPAWN_LOG" || true)"
t  "and no second worker is spawned onto it"           "spawns=[$before_f]" \
   printf 'spawns=[%s]\n' "$after_f"

nt "no boundary case ever reached the gh CLI"          "GH INVOKED"      cat "$GH_LOG"

finish
