#!/usr/bin/env bash
# test-register-transition.sh — the two write verbs' API branches, plus the
# four human-side verbs that have no API-mode counterpart yet.
#
# Every assertion rides a real socket against the fixture mock: the verb
# assembles the request, the mock records what arrived and answers a
# contract-shaped response, and the test reads back either what the verb
# printed or what the request log says went on the wire.
. "$(dirname "$0")/helpers.sh"

# A free port, not a fixed one: this file must survive running beside anything
# else on the machine (same reason as test-client-core.sh / test-comment.sh).
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
# Error bodies carry the NESTED envelope the service actually writes:
# {"error": {"code": ..., "message": ...}} (API.md §1).
# The mock matches a fixture path as a PREFIX, so `/tickets` also answers
# `/tickets/9/transition` — the transition route needs a standing fixture of
# its own after the `once` one, or a later transition eats a register fixture
# and every downstream response shifts by one.
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/tickets/9/transition","status":200,
  "body":{"ok":true,"to":"needs-human","converged":true},"once":true},
 {"method":"POST","path":"/tickets/9/transition","status":200,"body":{"ok":true,"to":"done"}},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":31,"state":"needs-human"},"once":true},
 {"method":"POST","path":"/tickets","status":409,
  "body":{"error":{"code":"illegal-birth","message":"spike may not be born ready-for-architect"}},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":30,"state":"ready-for-implementer"}}
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

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
V() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=rt "$SCRIPTS/$1" "${@:2}" ); }
# The log-reading asserts run their verb inside `bash -c`, which is a fresh
# shell: without these the callee would be an undefined command and every such
# assert would "fail" for the wrong reason.
export r CREDS SCRIPTS
export -f V

# The register payload as the verb actually serialized it, unwrapped out of the
# log line's JSON string escaping. `"path": "/tickets",` and not just /tickets:
# the transition route is /tickets/<n>/transition, which a looser match picks up.
last_register_body() {
  grep '"path": "/tickets",' "$FIX.log" | tail -1 |
    python3 -c 'import json, sys; print(json.loads(sys.stdin.read())["body"])'
}

t "transition prints SERVER to, not requested" "→ needs-human (converged)" \
  V board-transition.sh 9 in-review "note here"
t "fence rides env" '\"fence\": 3' \
  bash -c "cd '$r' && BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt BOARD_RUN_FENCE=3 \
    '$SCRIPTS/board-transition.sh' 9 done 2>/dev/null; cat '$FIX.log'"

t "park birth note prepends body" '\"body\": \"which color?' \
  bash -c "V board-register.sh 'pick color' enhancement P2 --state needs-human --note 'which color?' >/dev/null; cat '$FIX.log'"
# Whole-body pin, leading brace to trailing brace: a substring match on one key
# survives a payload that dropped the birth, renamed a key, or bolted an extra
# one on. This is the park-birth request from the assert above.
t "park birth body pins birth + note-as-body-head" \
  '{"title": "pick color", "category": "work", "priority": "P2", "birth": "needs-human", "body": "which color?"}' \
  last_register_body

# One refused birth, two things to check — and the 409 fixture is consumed on
# first use, so the run is captured once and both asserts read the capture.
SPIKE_OUT="$(mktemp)"; SPIKE_RC=0
EMPTY_BODY="$(mktemp)"   # a regular empty file, not /dev/null: the body-file
                         # guard is `[ -f ]`, which a character device fails
V board-register.sh "probe x" spike P2 --state ready-for-architect --body-file "$EMPTY_BODY" \
  > "$SPIKE_OUT" 2>&1 || SPIKE_RC=$?
t "spike->architect surfaces 409 + arkho#7" "illegal-birth" cat "$SPIKE_OUT"
t "spike 409 carries the arkho#7 pointer" "arkho/issues/7" cat "$SPIKE_OUT"
t "a refused birth exits nonzero" "rc=1" echo "rc=$SPIKE_RC"

t "category maps bug->work" '\"category\": \"work\"' \
  bash -c "V board-register.sh 'a bug' bug P1 >/dev/null; cat '$FIX.log'"
# ...and the map assert above passes on ANY earlier enhancement→work request in
# the log, so the bug birth is pinned whole too — including that an implicit
# birth state stays server-side (no "birth" key).
t "bug birth body pins the mapped category and omits birth" \
  '{"title": "a bug", "category": "work", "priority": "P1"}' \
  last_register_body

t "register prints id + url" "30 http://127.0.0.1:$PORT/tickets/30" \
  V board-register.sh "plain one" enhancement P2
for verb in board-edge.sh board-priority.sh board-relate.sh board-migrate-gh.sh; do
  t "$verb fails loud naming arkho#7" "arkho#7" V "$verb" 1 --block 2
done

# The binding constraint, asserted rather than assumed: in API mode gh is never
# invoked — with a stub on PATH that would announce itself if it were.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
nt "api register never invokes gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt \
    '$SCRIPTS/board-register.sh' 'no gh here' enhancement P2"
nt "api transition never invokes gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt \
    '$SCRIPTS/board-transition.sh' 9 done 'a note'"

finish
