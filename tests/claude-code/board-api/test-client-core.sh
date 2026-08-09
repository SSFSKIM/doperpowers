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
  "body":{"error":"upstream is down"}}
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
  PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
    BOARD_CREDENTIALS_FILE="$1" python3 -c "$2"
}
run_py_run() {  # run_py_run <run-token> <credentials-file> <python> — worker context
  BOARD_RUN_TOKEN="$1" run_py "$2" "$3"
}
last_log() { grep "$1" "$FIX.log" | tail -1; }

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=auto-tok\nBOARD_HUMAN_TOKEN=human-tok\n' > "$CREDS"

t "claim returns dict + auth header sent" "41" \
  run_py "$CREDS" "$CORE
print(A.claim('implementer','n-1')['runId'])"
t "automation token on claim" '"auth": "Bearer auto-tok"' last_log runs/claim

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

finish
