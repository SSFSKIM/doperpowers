#!/usr/bin/env bash
# test-register-transition.sh — the two write verbs' API branches, plus the
# verbs that still have no API-mode counterpart. Each verb leaves this file's
# refusal loop as its api branch lands (board-edge.sh → test-edge-verbs.sh).
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
# The `once` entries for one path are a QUEUE: the Nth registration in this
# file consumes the Nth unused /tickets fixture, so fixture order and the order
# of the register calls below must stay in lockstep.
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/tickets","status":200,
  "body":[{"id":8,"state":"in-design","priority":"P1","title":"a design pass",
           "owner_run":null,"plan":null,"pr_url":null},
          {"id":9,"state":"in-review","priority":"P1","title":"under review",
           "owner_run":null,"plan":null,"pr_url":null}]},
 {"method":"POST","path":"/tickets/9/transition","status":200,
  "body":{"ok":true,"to":"needs-human","converged":true},"once":true},
 {"method":"POST","path":"/tickets/9/transition","status":200,"body":{"ok":true,"to":"done"}},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":31,"state":"needs-human"},"once":true},
 {"method":"POST","path":"/tickets","status":500,
  "body":{"error":{"code":"internal","message":"upstream exploded"}},"once":true},
 {"method":"POST","path":"/tickets","status":409,
  "body":{"error":{"code":"illegal-birth","message":"spike may not be born ready-for-architect"}},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":32,"state":"needs-human"},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":33,"state":"ready-for-implementer"},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":34,"state":"ready-for-implementer"},"once":true},
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

EMPTY_BODY="$(mktemp)"   # a regular empty file, not /dev/null: the body-file
                         # guard is `[ -f ]`, which a character device fails
SPEC="$(mktemp)"; printf 'the spec' > "$SPEC"   # a real statement of work: a
                         # BODYLESS registration is no longer dispatchable (see
                         # the pre-spec rung at the end of this file), so every
                         # assertion about something else carries one

# The arkho#7 pointer is a claim about CANON — "this birth is illegal here" —
# and it may only ride the server saying exactly that. An outage on the same
# command (500, auth reject, connection refused) is the identical local shape:
# a SystemExit out of the client. Blaming canon divergence for a down service
# sends the reader to the wrong ticket.
OUTAGE_OUT="$(mktemp)"
V board-register.sh "probe 500" spike P2 --state ready-for-architect --body-file "$EMPTY_BODY" \
  > "$OUTAGE_OUT" 2>&1 || true
nt "a 500 on a spike birth does not blame arkho#7" "arkho/issues/7" cat "$OUTAGE_OUT"
t "a 500 on a spike birth still surfaces the failure" "internal" cat "$OUTAGE_OUT"
# ...and the same run pins the spike category pass-through whole: a typo in
# CATEGORY_MAP or a renamed birth key drops the lane silently otherwise.
t "spike category + explicit birth ride the payload whole" \
  '{"title": "probe 500", "category": "spike", "priority": "P2", "birth": "ready-for-architect"}' \
  last_register_body

# One refused birth, two things to check — and the 409 fixture is consumed on
# first use, so the run is captured once and both asserts read the capture.
SPIKE_OUT="$(mktemp)"; SPIKE_RC=0
V board-register.sh "probe x" spike P2 --state ready-for-architect --body-file "$EMPTY_BODY" \
  > "$SPIKE_OUT" 2>&1 || SPIKE_RC=$?
t "spike->architect surfaces 409 + arkho#7" "illegal-birth" cat "$SPIKE_OUT"
t "spike 409 carries the arkho#7 pointer" "arkho/issues/7" cat "$SPIKE_OUT"
t "a refused birth exits nonzero" "rc=1" echo "rc=$SPIKE_RC"

# An IMPLICIT birth is the case the requested-state gate cannot see. Here the
# SERVER inverts an env-issue to needs-human (E2), so this IS a park birth by
# outcome — and gh mode makes the note MANDATORY for exactly this command. The
# shell default `ready-for-implementer` is in no park tuple, so gating on the
# requested state discarded mandatory human input. Pinned whole-body: the note
# must be the body's opening line, and `env-issue` must survive the map.
V board-register.sh "disk is full" env-issue P1 --note "need ops to grow the volume" >/dev/null
t "implicit env-issue birth carries the note as the body head" \
  '{"title": "disk is full", "category": "env-issue", "priority": "P1", "body": "need ops to grow the volume"}' \
  last_register_body

# The other half of the rule, unchanged: an EXPLICIT non-park birth states a
# lane, so its --note is not a park question and stays off the body. Whole-body
# pin — the absence of a "body" key is the assertion, which a fix that simply
# prepended whenever --note is set would break.
V board-register.sh "wire it up" enhancement P2 --state ready-for-implementer --note "fyi only" \
  --body-file "$SPEC" >/dev/null
t "explicit non-park birth still keeps the note off the body" \
  '{"title": "wire it up", "category": "work", "priority": "P2", "birth": "ready-for-implementer", "body": "the spec"}' \
  last_register_body

# Edge keys are wire contract, and a camelCase slip drops an edge in silence —
# the server would accept the payload and just not draw the relation. Pinned
# whole, with both accepted ref spellings (`7` and `#8`) and a comma list.
V board-register.sh "edged one" enhancement P3 --parent 7 --spawned-by '#8' --blocked-by '9,#10' \
  --body-file "$SPEC" >/dev/null
t "edges ride as parent / spawnedBy / blockedBy integers" \
  '{"title": "edged one", "category": "work", "priority": "P3", "body": "the spec", "parent": 7, "spawnedBy": 8, "blockedBy": [9, 10]}' \
  last_register_body

# A junk ref is a caller mistake, not a server matter: it must die with the gh
# path's message rather than an uncaught ValueError traceback.
t "a non-numeric parent dies like the gh path" "not an issue number: abc" \
  V board-register.sh "bad ref" enhancement P2 --parent abc
nt "a non-numeric parent raises no traceback" "Traceback" \
  V board-register.sh "bad ref" enhancement P2 --blocked-by 4,xyz

t "category maps bug->work" '\"category\": \"work\"' \
  bash -c "V board-register.sh 'a bug' bug P1 --body-file '$SPEC' >/dev/null; cat '$FIX.log'"
# ...and the map assert above passes on ANY earlier enhancement→work request in
# the log, so the bug birth is pinned whole too — including that an implicit
# birth state stays server-side (no "birth" key).
t "bug birth body pins the mapped category and omits birth" \
  '{"title": "a bug", "category": "work", "priority": "P1", "body": "the spec"}' \
  last_register_body

t "register prints id + url" "30 http://127.0.0.1:$PORT/tickets/30" \
  V board-register.sh "plain one" enhancement P2 --body-file "$SPEC"
for verb in board-priority.sh board-relate.sh board-migrate-gh.sh; do
  t "$verb fails loud naming arkho#7" "arkho#7" V "$verb" 1 --block 2
done

# The binding constraint, asserted rather than assumed: in API mode gh is never
# invoked — with a stub on PATH that would announce itself if it were.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
nt "api register never invokes gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt \
    '$SCRIPTS/board-register.sh' 'no gh here' enhancement P2 --body-file '$SPEC'"
nt "api transition never invokes gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt \
    '$SCRIPTS/board-transition.sh' 9 done 'a note'"

# =========================================================================
# A BODYLESS TICKET IS NEVER DISPATCHABLE. gh mode seeds a pre-spec skeleton
# when no --body-file is given, then refuses an EXPLICIT birth into a lane state
# and demotes the DEFAULT one to needs-info. A1 stores an empty body and
# defaults to ready-for-implementer, so the same call produced a dispatchable
# ticket with no statement of work — a claim would hand a worker an empty
# assignment. The ruling is mirrored; the skeleton is not (A1's body IS the
# assignment and this client has no body-edit route).
# =========================================================================
V board-register.sh "no spec here" enhancement P2 >/dev/null
t "a bodyless default birth is demoted out of the implement queue" \
  '"birth": "needs-info"' last_register_body
t "and says what to do about it" "re-register with --body-file" last_register_body
t "a bodyless EXPLICIT lane birth is refused" \
  "cannot be born into a dispatchable lane state" \
  V board-register.sh "no spec, named lane" enhancement P2 --state ready-for-implementer
# An explicitly EMPTY --body-file is the registrar saying so, exactly as in gh
# mode — the rule keys on "no body-file was given", not on an empty string.
nt "an explicitly empty body-file is still the registrar's call" \
  "cannot be born into a dispatchable lane state" \
  V board-register.sh "empty on purpose" enhancement P2 --state ready-for-implementer \
    --body-file "$EMPTY_BODY"

# A PARK IS A QUESTION. A1 falls back to the TITLE as the decision question when
# the body is empty, so a note-less park birth produced a standing question that
# was a ticket name; gh mode requires the note for exactly this reason.
t "a park birth with no note and no body is refused" \
  "--note is required for state needs-human" \
  V board-register.sh "silent park" enhancement P2 --state needs-human

# A1 requires repairPath for an env-issue explicitly born into an agent lane,
# and the CLI had no way to send it — so every documented invocation of that
# birth was rejected.
V board-register.sh "flaky runner" env-issue P1 --state ready-for-implementer \
  --repair-path "re-register the self-hosted runner" --body-file "$SPEC" >/dev/null
t "an env-issue agent-lane birth carries its repair path" \
  '"repairPath": "re-register the self-hosted runner"' last_register_body
t "and --repair-path is refused in gh mode" "api-binding-only" \
  bash -c "cd '$(mkrepo)' && BOARD_REPO=o/r '$SCRIPTS/board-register.sh' t enhancement P2 --repair-path x"

# =========================================================================
# A PLAN PIN IS A GATE, NOT A FIELD. It authorizes gate-free PLAN-EXECUTION,
# and A1 stores whatever primitive arrives on whatever legal edge — so the
# client is the only fence there is on this side. gh mode's checks, mirrored.
# =========================================================================
PIN_OUT="$(mktemp)"
V board-transition.sh 9 ready-for-implementer "n" --plan "docs/p.md@$(printf 'a%.0s' $(seq 40))" \
  > "$PIN_OUT" 2>&1 || true
t "a plan pin off the Architect handoff edge is refused" \
  "rides the Architect handoff edge" cat "$PIN_OUT"
nt "and never reaches the wire" '\"plan\": \"docs/p.md@aaa' cat "$FIX.log"
V board-transition.sh 8 ready-for-implementer "n" --plan "docs/p.md@deadbeef" \
  > "$PIN_OUT" 2>&1 || true
t "a short-sha pin is refused as mutable" "immutable pin" cat "$PIN_OUT"
V board-transition.sh 8 ready-for-implementer "n" --plan "docs/p.md@$(printf 'a%.0s' $(seq 40))" \
  > "$PIN_OUT" 2>&1 || true
t "a pin with no branch is refused" "needs a branch the sha is reachable from" cat "$PIN_OUT"
V board-transition.sh 8 ready-for-implementer "n" --branch nope \
  --plan "docs/p.md@$(printf 'a%.0s' $(seq 40))" > "$PIN_OUT" 2>&1 || true
t "an unverifiable branch fails CLOSED" "names no commit in this checkout" cat "$PIN_OUT"

finish
