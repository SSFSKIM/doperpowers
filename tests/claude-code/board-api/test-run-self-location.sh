#!/usr/bin/env bash
# test-run-self-location.sh — a worker finds its own run context (dp#35).
#
# The dispatchers hand a worker its run on a spawn env prefix. `claude --bg`
# drops that prefix before the worker's own Bash shells run (measured twice,
# harness v2.1.261), so the ONE thing a worker's shell reliably has is
# $CLAUDE_CODE_SESSION_ID — which is exactly the key the dispatcher already
# indexed the run by when it stamped the seat record. This suite pins the
# resolution order that follows from it:
#
#   1. an explicit BOARD_RUN_TOKEN in env wins, always
#   2. else this session's OWN seat record, if its bind confirmed, it holds a
#      bearer, and it was bound on THIS board
#   3. else exactly the pre-dp#35 behaviour — `auto` dies, the rest read the
#      credentials file
#
# Every rejection below has to land on 3 rather than on a 401: a run context
# taken from the wrong record is worse than none, because the verb then acts
# as a principal nobody chose.
. "$(dirname "$0")/helpers.sh"

PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
URL="http://127.0.0.1:$PORT"
BOARD="api:$URL"

FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/tickets/12/transition","status":200,
  "body":{"to":"in-review"}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
tries=200
while [ "$tries" -gt 0 ]; do
  python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $PORT)) == 0 else 1)" && break
  tries=$((tries - 1)); sleep 0.05
done
[ "$tries" -gt 0 ] || { echo "FAIL mock server never listened on $PORT"; exit 1; }

CREDS="$(mktemp)"
printf 'BOARD_AUTOMATION_TOKEN=auto-tok\nBOARD_HUMAN_TOKEN=human-tok\n' > "$CREDS"

# The session uuid a `claude --bg` worker's shells see, and the first 8 hex of
# it — the `short` sminos parses out of the launch banner and writes to the
# record before the full uuid is even known.
SESSION="abcd1234-0000-4000-8000-0000000000aa"
SHORT="abcd1234"
BEARER="seat-tok-secret"

CORE="import _board_api as A"
# A verb's process: no BOARD_RUN_TOKEN, no BOARD_RUN_ID, no BOARD_RUN_FENCE —
# the environment `claude --bg` actually leaves a worker's shell with.
as_session() {  # as_session <session-id> <python>
  PYTHONPATH="$SCRIPTS" BOARD_API_URL="$URL" BOARD_REPO=testrepo \
    BOARD_CREDENTIALS_FILE="$CREDS" CLAUDE_CODE_SESSION_ID="$1" python3 -c "$2"
}
last_log() { grep "$1" "$FIX.log" | tail -1; }
last_body() {
  grep "$1" "$FIX.log" | tail -1 |
    python3 -c 'import json, sys; print(json.loads(sys.stdin.read())["body"])'
}

# ONE record in the registry at a time. The resolver scans the whole root, so a
# leftover from the previous case is a second candidate, and a suite whose
# cases silently compose proves nothing about any of them.
only_seat() {  # only_seat <seat-id> <json>
  rm -f "$DAEMON_HOME"/*.json
  printf '%s\n' "$2" > "$DAEMON_HOME/$1.json"
}
# The record board-bind.sh leaves behind: run id, fence, bearer, the confirmed
# bind, and the board/repo pair every registry scan adjudicates on.
bound_record() {  # bound_record <locator-key> <locator-value> [board]
  printf '{"uuid":"seat-a","%s":"%s","status":"working","ticket":"12",' "$1" "$2"
  printf '"run_id":41,"fence":3,"run_bearer":"%s","bind_confirmed":true,' "$BEARER"
  printf '"board":"%s","board_repo":"testrepo"}' "${3:-$BOARD}"
}

# What the process resolved, in one line, bearer included. Every knob this
# suite turns — the session id itself included — rides in as a leading
# VAR=VALUE word, so each case states the whole environment it is about.
REVEAL_PY="$CORE
c = A.run_context()
print('ctx=%s' % ('none' if c is None else
                  '%s/%s/%s' % (c['bearer'], c['run_id'], c['fence'])))"
reveal() {  # reveal [VAR=VALUE ...]
  env PYTHONPATH="$SCRIPTS" BOARD_API_URL="$URL" BOARD_REPO=testrepo \
    BOARD_CREDENTIALS_FILE="$CREDS" "$@" python3 -c "$REVEAL_PY"
}

# ---- rule 2: the session's own seat record ---------------------------------
# The `short` arm is the one that matters at spawn time: sminos writes the
# 8-hex short from the launch banner immediately and only fills `current` once
# the uuid poll returns, so a worker that starts fast has nothing else to
# match on.
only_seat seat-a "$(bound_record short "$SHORT")"
t "a short-prefix match speaks as the seat's run" "ctx=$BEARER/41/3" reveal CLAUDE_CODE_SESSION_ID="$SESSION"
t "and says so, naming the run and the seat, not the bearer" \
  "speaking as run 41 via seat seat-a" reveal CLAUDE_CODE_SESSION_ID="$SESSION"
nt "the resolution note never carries the bearer" "$BEARER" \
  as_session "$SESSION" "$CORE
A.run_context()"

# `current` is the full uuid, written once the poll resolves; it is the exact
# match and it wins over any prefix.
only_seat seat-a "$(bound_record current "$SESSION")"
t "a full-uuid \`current\` match resolves the same run" "ctx=$BEARER/41/3" reveal CLAUDE_CODE_SESSION_ID="$SESSION"

# A prefix is a PREFIX of the session id, not a substring of it and not the
# other way round: two seats' shorts are 8 hex apart, and a looser test would
# hand a worker its neighbour's bearer.
only_seat seat-a "$(bound_record short "ffff9999")"
t "a non-matching short is not this session's seat" "ctx=none" reveal CLAUDE_CODE_SESSION_ID="$SESSION"

# ---- rule 1: an explicit prefix still wins ---------------------------------
# The prefix is the DECLARED channel and stays correct wherever env survives —
# the sweep's per-command prefixes, a foreground harness. It is consulted
# first, so a stale record can never displace a bearer the caller just handed.
only_seat seat-a "$(bound_record current "$SESSION")"
t "an explicit BOARD_RUN_TOKEN wins over the record" "ctx=env-tok/99/7" \
  reveal BOARD_RUN_TOKEN=env-tok BOARD_RUN_ID=99 BOARD_RUN_FENCE=7 \
    CLAUDE_CODE_SESSION_ID="$SESSION"

# ---- rule 3: everything that is not this session's confirmed run -----------
# The registry is machine-global; a board is not. A session bound on another
# service is simply not this checkout's run, whatever it holds.
only_seat seat-a "$(bound_record current "$SESSION" "api:http://other.example")"
t "a record bound on another board is ignored" "ctx=none" reveal CLAUDE_CODE_SESSION_ID="$SESSION"

# bind_confirmed is board-bind's claim that the SERVER accepted the bind. An
# unconfirmed record may name a run the board never gave this session.
only_seat seat-a '{"uuid":"seat-a","current":"'"$SESSION"'","run_id":41,"fence":3,
  "run_bearer":"'"$BEARER"'","board":"'"$BOARD"'","board_repo":"testrepo"}'
t "an unconfirmed bind is not a run" "ctx=none" reveal CLAUDE_CODE_SESSION_ID="$SESSION"

# The end-of-run shape: _sweep_api.sh's _retire_run_locally pops run_id,
# run_bearer, fence and bind_confirmed the moment the run is ended, and stamps
# run_ended_at. That strip is what makes a finished worker fall back cleanly
# instead of authenticating with a revoked bearer on every verb.
only_seat seat-a '{"uuid":"seat-a","current":"'"$SESSION"'","status":"working",
  "ticket":"12","run_ended_at":"2026-09-05T00:00:00Z","board":"'"$BOARD"'",
  "board_repo":"testrepo"}'
t "a record whose run has ended carries nothing to speak as" "ctx=none" reveal CLAUDE_CODE_SESSION_ID="$SESSION"

# No session id at all: a cron shell, an operator's terminal, a harness that
# does not export one. Nothing to locate by, so nothing is located.
only_seat seat-a "$(bound_record current "$SESSION")"
t "without a session id there is no self-location" "ctx=none" reveal

# THE TICK IS AUTOMATION, FULL STOP. The dispatchers and the sweep drop an
# ambient run token so they cannot act as a worker; self-location is a second
# channel into the same hazard, and they close it the same way — one declared
# word, beside the unset.
only_seat seat-a "$(bound_record current "$SESSION")"
t "a process that declares itself not-the-run ignores the record" "ctx=none" \
  reveal BOARD_NO_SELF_LOCATE=1 CLAUDE_CODE_SESSION_ID="$SESSION"

# ---- the spawn-before-bind race --------------------------------------------
# The executor lane has no startup barrier: execute-dispatch.sh spawns the
# worker and binds it AFTERWARDS, so the worker's first board command can land
# between the two. `sminos spawn` has already written the record by then — with
# `short` off the launch banner — but board-bind.sh writes `board`, the repo,
# the run, the bearer and the confirmation in ONE later write, so mid-handover
# the record exists and says nothing about any board. That is the wait window,
# and it is the only one.
TIMED_OUT="" TIMED_SECS=0
run_timed() {  # run_timed <cmd...> — capture the output AND the wall clock
  local start=$SECONDS
  TIMED_OUT="$("$@" 2>&1)" || :
  TIMED_SECS=$((SECONDS - start))
}
said() { printf '%s\n' "$TIMED_OUT"; }
# Coarse on purpose: the point is "did it sit out a budget or not", and a
# second-resolution verdict cannot flake on a 0.5s poll interval.
waited() { [ "$TIMED_SECS" -ge 1 ] && echo "waited=yes" || echo "waited=no"; }

# The pre-bind shape sminos leaves behind: a launch, and nothing else.
unbound_record() {
  printf '{"uuid":"seat-a","short":"%s","status":"working","task":"do the thing"}' "$SHORT"
}

# A session with no record at all is an operator's shell, and it may not pay a
# millisecond for a race it is not in.
rm -f "$DAEMON_HOME"/*.json
run_timed reveal CLAUDE_CODE_SESSION_ID="$SESSION"
t "no record at all is still no run"      "ctx=none"  said
t "and costs nothing to find out"         "waited=no" waited

only_seat seat-a "$(unbound_record)"
run_timed reveal CLAUDE_CODE_SESSION_ID="$SESSION" BOARD_SEAT_BIND_WAIT=1
t "a bind that never lands falls through to no run" "ctx=none"   said
t "...having waited for it rather than giving up at once" "waited=yes" waited

# THE BUDGET IS THE RECORD'S, NOT THE CALLER'S. An operator's own joined seat
# looks exactly like a pre-bind one — sminos writes no board key for either —
# so the only thing separating "a bind is in flight" from "this seat is not a
# board worker" is when the record was last written. Anchored on the caller's
# clock instead, every verb run from a joined seat would sit out the whole
# budget.
only_seat seat-a "$(unbound_record)"
touch -t 200001010000 "$DAEMON_HOME/seat-a.json"
run_timed reveal CLAUDE_CODE_SESSION_ID="$SESSION"
t "a seat nobody is binding is not waited on" "waited=no" waited
t "and it is still no run"                    "ctx=none"  said

# And the window doing its job: the bind lands while the verb is waiting.
only_seat seat-a "$(unbound_record)"
# ATOMIC, like the write it stands in for: board-bind.sh renames a temp file
# into place under the registry lock, and a scan that caught a truncated one
# would skip it and read the absence as "the record went away".
( sleep 2
  printf '%s\n' "$(bound_record short "$SHORT")" > "$DAEMON_HOME/seat-a.tmp"
  mv "$DAEMON_HOME/seat-a.tmp" "$DAEMON_HOME/seat-a.json" ) &
LATE=$!
t "a bind that lands mid-wait is the run the verb speaks as" "ctx=$BEARER/41/3" \
  reveal CLAUDE_CODE_SESSION_ID="$SESSION"
wait "$LATE" 2>/dev/null || :

# ---- one service, several repos --------------------------------------------
# The board url names the SERVICE, and one instance serves several repos out of
# one ticket namespace — so a session bound for a NEIGHBOUR repo passes the url
# guard. This checkout knows which repo it speaks for, so it can say no.
only_seat seat-a "$(bound_record current "$SESSION")"
t "a record bound for another repo on the same service is not ours" "ctx=none" \
  reveal CLAUDE_CODE_SESSION_ID="$SESSION" BOARD_REPO=otherrepo BOARD_SEAT_BIND_WAIT=0
t "and the one bound for ours still is" "ctx=$BEARER/41/3" \
  reveal CLAUDE_CODE_SESSION_ID="$SESSION" BOARD_REPO=testrepo

# ---- the pre-dp#35 behaviours, unchanged -----------------------------------
rm -f "$DAEMON_HOME"/*.json
t "auto without any run context still dies naming it" "no BOARD_RUN_TOKEN" \
  as_session "$SESSION" "$CORE
A.token('auto')"
t "and the human default still reads the credentials file" "human-tok" \
  as_session "$SESSION" "$CORE
print(A.token('human'))"

# ---- end to end: a real verb, from a worker's own shell --------------------
# The point of the whole ticket. board-transition.sh is invoked exactly as a
# worker's bootstrap tells it to — no env prefix, no exported bearer — and the
# write has to land as the RUN, carrying the run's fence.
REPO="$(mkrepo)"; mkdir -p "$REPO/.doperpowers"
printf '{"binding":"api","url":"%s","repo":"testrepo"}\n' "$URL" \
  > "$REPO/.doperpowers/board.json"
only_seat "$SESSION" "$(bound_record current "$SESSION")"
TR_OUT="$(cd "$REPO" && env CLAUDE_CODE_SESSION_ID="$SESSION" \
  BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-transition.sh" 12 in-review drill 2>&1 || true)"

t "the transition reports the state the server wrote" "#12: → in-review" \
  echo "$TR_OUT"
t "it went out as the run, not as the human" "\"auth\": \"Bearer $BEARER\"" \
  last_log tickets/12/transition
t "carrying the run's fence off the record" \
  '{"to": "in-review", "note": "drill", "fence": 3}' last_body tickets/12/transition
t "and the transcript says which principal acted" \
  "speaking as run 41 via seat $SESSION" echo "$TR_OUT"
nt "the bearer never reaches stdout or stderr" "$BEARER" echo "$TR_OUT"
nt "nor does the human token this verb would otherwise have used" "human-tok" \
  echo "$TR_OUT"

finish
