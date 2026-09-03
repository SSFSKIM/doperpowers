#!/usr/bin/env bash
# test-client-core.sh — _board_api.py over real HTTP against the fixture mock.
# Every assertion here rides an actual socket: the client assembles a request,
# the mock records what arrived (method, path, Authorization, body) and answers
# a contract-shaped response, and the test reads back either the client's
# return value or the mock's request log.
. "$(dirname "$0")/helpers.sh"

# A free port, not a fixed one: this file must survive running beside anything
# else on the machine.
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
# Error bodies carry the NESTED envelope the service actually writes:
# {"error": {"code": ..., "message": ...}} (API.md §1, src/server.js).
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,
  "body":{"runId":41,"ticketId":12,"fence":3,"bearer":"tok-abc","plan":null,
          "body":"do the thing","parentPin":null}},
 {"method":"POST","path":"/tickets/12/transition","status":409,
  "body":{"error":{"code":"fence-mismatch","message":"fence 2 != 3"}}},
 {"method":"POST","path":"/tickets/12/comment","status":200,
  "body":{"eventId":118}},
 {"method":"GET","path":"/answers/unrelayed","status":200,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101","replies":["yes"]}]},
 {"method":"POST","path":"/runs/41/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"run 41 has ended"}}},
 {"method":"POST","path":"/runs/99/renew","status":502,
  "body":{"error":"upstream is down"}},
 {"method":"POST","path":"/runs/41/bind","status":200,
  "body":{"ok":true}},
 {"method":"POST","path":"/tickets/12/park-answer","status":200,
  "body":{"eventId":200}},
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/priority","status":200,
  "body":{"ok":true,"noop":true}},
 {"method":"POST","path":"/tickets/5/body","status":409,
  "body":{"error":{"code":"ticket-owned","message":"ticket 5 is owned by run 41"}}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT

wait_for_port() {  # poll rather than sleep — a fixed nap is a flake
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then
      return 0
    fi
    tries=$((tries - 1))
    sleep 0.05
  done
  return 1
}
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

CORE="import _board_api as A"
run_py() {  # run_py <credentials-file> <python>  — operator context, no run token
  # BOARD_REPO stands in for the api binding's declared `repo`: _binding.sh
  # resolves it from .doperpowers/board.json and _api_py hands it to python3,
  # and the client refuses the repo-dimensioned routes without one.
  PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
    BOARD_REPO="${BOARD_REPO_OVERRIDE-testrepo}" \
    BOARD_CREDENTIALS_FILE="$1" python3 -c "$2"
}
run_py_run() {  # run_py_run <run-token> <credentials-file> <python> — worker context
  BOARD_RUN_TOKEN="$1" run_py "$2" "$3"
}
last_log() { grep "$1" "$FIX.log" | tail -1; }
# The request body as the client actually serialized it, unwrapped out of the
# log line's JSON string escaping — so a body assertion reads as the wire bytes
# ({"storeNs": ...}) rather than as backslash soup ({\"storeNs\": ...}).
last_body() {
  grep "$1" "$FIX.log" | tail -1 |
    python3 -c 'import json, sys; print(json.loads(sys.stdin.read())["body"])'
}

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=auto-tok\nBOARD_HUMAN_TOKEN=human-tok\n' > "$CREDS"

t "claim returns dict + auth header sent" "41" \
  run_py "$CREDS" "$CORE
print(A.claim('implementer','n-1')['runId'])"
t "automation token on claim" '"auth": "Bearer auto-tok"' last_log runs/claim

# What the client PUTS ON THE WIRE, not what it returns. The service reads
# camelCase keys; a typo in one of them is invisible to every return-value
# assertion in this file and fails only on first contact with the real API.
# Each body is pinned whole (leading brace to trailing brace), so an extra,
# renamed, or reordered key fails the match.
run_py "$CREDS" "$CORE
A.claim('implementer', 'n-7', lease_minutes=45)" > /dev/null 2>&1 || true
t "claim body pins dispatchNonce and leaseMinutes" \
  '{"lane": "implementer", "dispatchNonce": "n-7", "leaseMinutes": 45, "repo": "testrepo"}' \
  last_body runs/claim

# A bind speaks as the RUN, not as automation: it is only ever posted for a run
# whose bearer the caller holds, and a bind posted as the fleet would confirm an
# ownership no later resume could exercise.
run_py_run tok-w "$CREDS" "$CORE
A.bind(41, 'ns-a', 'proj-b', 'sess-c')" > /dev/null 2>&1 || true
t "bind body pins storeNs, projectKey and sessionId" \
  '{"storeNs": "ns-a", "projectKey": "proj-b", "sessionId": "sess-c"}' \
  last_body runs/41/bind
t "the bind speaks as the run" '"auth": "Bearer tok-w"' last_log runs/41/bind
BIND_NO_RUN="$(run_py "$CREDS" "$CORE
A.bind(41, 'ns-a', 'proj-b', 'sess-c')" 2>&1 || true)"
t "and refuses to fall back to a fleet credential" \
  "the caller demanded the run principal" echo "$BIND_NO_RUN"

run_py "$CREDS" "$CORE
A.park_answer(12, ['yes'], correlation_id='evt-101')" > /dev/null 2>&1 || true
t "park-answer body pins correlationId" \
  '{"replies": ["yes"], "correlationId": "evt-101"}' \
  last_body park-answer

t "run token wins over files" "tok-999" \
  run_py_run tok-999 "$CREDS" "$CORE
print(A.token('auto'))"
t "auto principal without a run token dies" "no BOARD_RUN_TOKEN" \
  run_py "$CREDS" "$CORE
A.token('auto')"

# The identifier and the diagnostic both, unwrapped out of the envelope — a
# looser 'fence-mismatch' substring also matches a stringified envelope dict,
# so it would pass against a client that never unwrapped anything.
t "409 error mapped verbatim" "refused: fence-mismatch — fence 2 != 3" \
  run_py "$CREDS" "$CORE
try: A.transition(12, 'in-review', fence=2)
except SystemExit: pass"
nt "a refusal never leaks a token" "human-tok" \
  run_py "$CREDS" "$CORE
try: A.transition(12, 'in-review', fence=2)
except SystemExit: pass"

# transition's optional arguments are omitted, not sent as null: the service
# distinguishes "no fence supplied" from "fence: null", so the two halves of
# this pair — present when given, absent when None — must both hold.
t "transition body carries an optional argument when given" \
  '{"to": "in-review", "fence": 2}' last_body transition
run_py "$CREDS" "$CORE
try: A.transition(12, 'in-review', note='hi')
except SystemExit: pass" > /dev/null 2>&1 || true
t "transition body omits every None argument" \
  '{"to": "in-review", "note": "hi"}' last_body transition

# A body that is not the contract envelope (a proxy's 502, an empty 404) must
# still die diagnostically. Unwrapping it blind raises AttributeError on the
# str, which reaches the operator as a traceback instead of an error line.
t "a non-envelope error body degrades, never crashes" "refused: http-502" \
  run_py "$CREDS" "$CORE
try: A.renew(99)
except SystemExit: pass"
nt "a non-envelope error body raises no traceback" "Traceback" \
  run_py "$CREDS" "$CORE
try: A.renew(99)
except SystemExit: pass"

t "run-ended raises typed" "RunEnded" \
  run_py "$CREDS" "$CORE
try: A.renew(41)
except A.RunEnded: print('RunEnded')"
t "unrelayed returns list" "118" \
  run_py "$CREDS" "$CORE
print(A.unrelayed()[0]['answerEventId'])"

# The two principal-resolution paths on one ticket-facing verb (Codex F5): the
# same default principal="human" must reach the wire as the human token from an
# operator shell and as the run token from a worker shell.
run_py "$CREDS" "$CORE
A.comment(12, text='hello')" > /dev/null 2>&1 || true
t "operator context falls back to human token" '"auth": "Bearer human-tok"' \
  last_log comment
run_py_run tok-999 "$CREDS" "$CORE
A.comment(12, text='hello')" > /dev/null 2>&1 || true
t "worker context speaks as the run on a human-default verb" '"auth": "Bearer tok-999"' \
  last_log comment

t "missing creds file dies loud" "board credentials file" \
  run_py "/nonexistent" "$CORE
A.claim('implementer','n-2')"

# The five human-only routes (arkho#7). Each body is pinned whole, because a
# renamed camelCase key reaches the wire silently and fails only against the
# real service; and the principal is checked once — these are the operator's
# verbs, so an operator shell must present the human token, not automation's.
run_py "$CREDS" "$CORE
A.edge(5, 'add', 7)" > /dev/null 2>&1 || true
t "edge body pins op and blockedBy" '{"op": "add", "blockedBy": 7}' \
  last_body tickets/5/edges
t "the edge speaks as the human" '"auth": "Bearer human-tok"' last_log tickets/5/edges

# An orphan is written as an explicit null, not an omitted key. The service
# reads absent and null alike, so the null is for legibility and robustness —
# it says "no parent" outright and survives a tightening of the contract.
run_py "$CREDS" "$CORE
A.set_parent(5, None)" > /dev/null 2>&1 || true
t "parent body sends an explicit null to orphan" '{"parent": null}' \
  last_body tickets/5/parent
# The other half of the same verb: a real parent must reach the wire as an int
# under the same key, or reparenting silently orphans instead.
run_py "$CREDS" "$CORE
A.set_parent(5, 3)" > /dev/null 2>&1 || true
t "parent body pins the new parent id" '{"parent": 3}' \
  last_body tickets/5/parent

run_py "$CREDS" "$CORE
A.relate(5, 'add', 9)" > /dev/null 2>&1 || true
t "relates body pins op and ticket" '{"op": "add", "ticket": 9}' \
  last_body tickets/5/relates

# The server answers a no-change priority write with noop; the helper hands
# that flag back rather than flattening every answer to success. The expected
# string is INTERPOLATED, never a literal in the snippet: a traceback echoes
# its own source line, so a literal 'noop-yes' in there would match the very
# crash this assert exists to catch.
t "priority returns the server's noop flag" "noop=True" \
  run_py "$CREDS" "$CORE
print('noop=%s' % A.set_priority(5, 'P0').get('noop'))"

t "body surfaces a ticket-owned refusal verbatim" \
  "ticket-owned — ticket 5 is owned by run 41" \
  run_py "$CREDS" "$CORE
try: A.set_body(5, 'x')
except SystemExit: pass"

finish
