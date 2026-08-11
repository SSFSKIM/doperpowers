#!/usr/bin/env bash
# test-edge-verbs.sh — the arkho#7 human verbs' API branches. Task 2 covers
# board-edge.sh (blocked-by re-cuts, reparent, orphan); Tasks 3–4 append their
# own fixtures and asserts for relate / priority / body to this file.
#
# Two things are pinned per call: what went on the wire (the fixture log) and
# what the verb printed. Server refusals surface the service's own message
# verbatim and exit nonzero — the client re-adjudicates nothing.
. "$(dirname "$0")/helpers.sh"

# A free port, not a fixed one: this file must survive running beside anything
# else on the machine (same reason as test-register-transition.sh).
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
# Error bodies carry the NESTED envelope the service actually writes:
# {"error": {"code": ..., "message": ...}} (API.md §1).
# The `once` entries for one path are a QUEUE, so fixture order and call order
# below must stay in lockstep; the trailing standing entry answers every later
# call on that path (without it, an extra call falls through to 404).
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/edges","status":409,
  "body":{"error":{"code":"edge-cycle","message":"#7 already waits on #5"}},"once":true},
 {"method":"POST","path":"/tickets/5/edges","status":409,
  "body":{"error":{"code":"self-edge","message":"a ticket cannot block itself"}},"once":true},
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/parent","status":409,
  "body":{"error":{"code":"ancestor-blocker","message":"#5 is blocked by #3, an ancestor"}},"once":true},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true}}
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
# No BOARD_RUN_TOKEN: these routes are human-principal, and a run token in the
# environment would speak as the run and hide which principal the verb asked for.
V() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }

last_line() {  # <path> — the log line for the most recent call on that route
  grep -F "\"path\": \"$1\"" "$FIX.log" | tail -1
}
# The payload as the verb serialized it, unwrapped out of the log line's own
# JSON string escaping. Pinned whole, brace to brace: a substring match on one
# key survives a payload that renamed a key or bolted an extra one on.
last_body() {  # <path>
  last_line "$1" | python3 -c 'import json, sys; print(json.loads(sys.stdin.read())["body"])'
}

# ---- board-edge.sh ----
t "block prints the move that committed" "#5: blocked_by += #7" \
  V board-edge.sh 5 --block 7
t "the block payload is op add with an int blockedBy" '{"op": "add", "blockedBy": 7}' \
  last_body /tickets/5/edges
# Edges are a human-only route (API.md §4.2): the automation token on this wire
# would be refused by the real service, and the mock would never notice.
t "an edge write speaks as the human principal" '"auth": "Bearer h"' \
  last_line /tickets/5/edges

# The server owns every structural guard; the client's whole job on a refusal is
# to relay it unrewritten and fail.
CYCLE_OUT="$(mktemp)"; CYCLE_RC=0
V board-edge.sh 5 --block 7 > "$CYCLE_OUT" 2>&1 || CYCLE_RC=$?
t "a cycle refusal surfaces the server's identifier" "edge-cycle" cat "$CYCLE_OUT"
t "a cycle refusal surfaces the server's message" "#7 already waits on #5" cat "$CYCLE_OUT"
t "a refused edge exits nonzero" "rc=1" echo "rc=$CYCLE_RC"

# The sharpest form of the same property: the gh path rejects a self-edge in
# its own code, so this branch must NOT — `--block 5` on #5 has to reach the
# wire and come back refused. Its fixture is a `once` entry, and first-unused
# wins, so this call has to be the third on /tickets/5/edges; parked any later
# the standing 200 below would answer it.
SELF_OUT="$(mktemp)"
V board-edge.sh 5 --block 5 > "$SELF_OUT" 2>&1 || true
t "a self-edge is sent, not adjudicated locally" '{"op": "add", "blockedBy": 5}' \
  last_body /tickets/5/edges
t "the server's self-edge refusal surfaces" "self-edge" cat "$SELF_OUT"

t "unblock prints the cut" "#5: blocked_by -= #7" V board-edge.sh 5 --unblock 7
t "the unblock payload says cut" '{"op": "cut", "blockedBy": 7}' \
  last_body /tickets/5/edges

t "parent prints the new parent" "#5: parent = #3" V board-edge.sh 5 --parent 3
t "the parent payload is an int" '{"parent": 3}' last_body /tickets/5/parent
ANC_OUT="$(mktemp)"
V board-edge.sh 5 --parent 3 > "$ANC_OUT" 2>&1 || true
t "an ancestor-blocker refusal surfaces verbatim" "ancestor-blocker" cat "$ANC_OUT"

t "orphan says the parent is gone" "#5: parent cleared" V board-edge.sh 5 --orphan
t "the orphan payload is an explicit null parent" '{"parent": null}' \
  last_body /tickets/5/parent

# Both ref spellings, as in every other verb.
t "hash refs are accepted on both ends" "#5: blocked_by += #7" \
  V board-edge.sh '#5' --block '#7'
# A junk ref is a caller mistake, not a server matter: it dies with the gh
# path's message rather than an uncaught traceback or a request on the wire.
t "a non-numeric ref dies like the gh path" "not an issue number: abc" \
  V board-edge.sh 5 --block abc
nt "a non-numeric ref raises no traceback" "Traceback" V board-edge.sh 5 --parent xyz

# In API mode gh is never invoked — asserted with a stub, as everywhere else.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
nt "api edge verbs never invoke gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' \
    '$SCRIPTS/board-edge.sh' 5 --block 7"

finish
