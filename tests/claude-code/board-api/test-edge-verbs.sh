#!/usr/bin/env bash
# test-edge-verbs.sh — the arkho#7 human verbs' API branches: board-edge.sh
# (blocked-by re-cuts, reparent, orphan), board-relate.sh, board-priority.sh;
# Task 4 appends its own fixtures and asserts for body to this file.
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
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/relates","status":409,
  "body":{"error":{"code":"duplicate-edge","message":"#5 and #7 are already related"}},"once":true},
 {"method":"POST","path":"/tickets/5/relates","status":409,
  "body":{"error":{"code":"self-edge","message":"a ticket cannot relate to itself"}},"once":true},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true,"noop":true},"once":true},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true,"noop":true},"once":true},
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true},"once":true},
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

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"
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

# ---- board-relate.sh ----
# One call, not two: the server stores the edge normalized and projects it on
# both tickets, so the gh half's write into BOTH issues' meta blocks has no
# counterpart here.
t "relate prints the edge it made" "related: #5 -- #7" V board-relate.sh 5 7
t "the relate payload is op add with an int ticket" '{"op": "add", "ticket": 7}' \
  last_body /tickets/5/relates
t "a relates write speaks as the human principal" '"auth": "Bearer h"' \
  last_line /tickets/5/relates

DUP_OUT="$(mktemp)"; DUP_RC=0
V board-relate.sh 5 7 > "$DUP_OUT" 2>&1 || DUP_RC=$?
t "a duplicate relate surfaces the server's identifier" "duplicate-edge" cat "$DUP_OUT"
t "a duplicate relate surfaces the server's message" "#5 and #7 are already related" \
  cat "$DUP_OUT"
t "a refused relate exits nonzero" "rc=1" echo "rc=$DUP_RC"

# Same sharpness as the board-edge self-edge case: the gh path refuses a
# self-relate in its own python, so this branch must NOT — it has to reach the
# wire. Third call on /tickets/5/relates, matching the third `once` fixture.
SELF_REL="$(mktemp)"
V board-relate.sh 5 5 > "$SELF_REL" 2>&1 || true
t "a self-relate is sent, not adjudicated locally" '{"op": "add", "ticket": 5}' \
  last_body /tickets/5/relates
t "the server's self-relate refusal surfaces" "a ticket cannot relate to itself" \
  cat "$SELF_REL"

t "--cut prints the cut" "cut: #5 -- #7" V board-relate.sh 5 7 --cut
t "the cut payload says cut" '{"op": "cut", "ticket": 7}' last_body /tickets/5/relates
t "hash refs are accepted on both relate ends" "related: #5 -- #7" \
  V board-relate.sh '#5' '#7'
t "a non-numeric relate ref dies like the gh path" "not an issue number: abc" \
  V board-relate.sh 5 abc
nt "a non-numeric relate ref raises no traceback" "Traceback" V board-relate.sh abc 5

# ---- board-priority.sh ----
# No old grade on the left: the client holds no snapshot in api mode, and the
# server's answer is the whole truth about what the write did.
t "priority prints the grade that committed" "#5: → P0" V board-priority.sh 5 P0
t "the priority payload is the grade alone" '{"priority": "P0"}' last_body /tickets/5/priority
t "a priority write speaks as the human principal" '"auth": "Bearer h"' \
  last_line /tickets/5/priority
# Write-if-changed is the server's; the flag is it saying nothing was recorded.
t "the server's noop flag is reported" "#5: → P0 (noop)" V board-priority.sh 5 P0
nt "a committed re-grade says nothing about noop" "(noop)" V board-priority.sh 5 P1

# A bad grade is bad argv, not a server matter — it must not need a socket.
t "a bad grade dies client-side" "priority must be one of P0|P1|P2|P3" \
  V board-priority.sh 5 P9
nt "a bad grade never reaches the wire" "P9" cat "$FIX.log"
t "a non-numeric priority ref dies like the gh path" "not an issue number: xyz" \
  V board-priority.sh xyz P0

# ---- board-body.sh (api half) ----
# Four `once` 200s then a standing 409, and the calls below run in exactly that
# order: rewrite, noop rewrite, empty-file clear, stdin. Every call after those
# four is refused ticket-owned — which is what the owned asserts want.
BF="$(mktemp)"; printf 'the sharpened statement' > "$BF"
t "body edit posts and reports" "#5: body rewritten" V board-body.sh 5 --body-file "$BF"
t "the body payload carries the text whole" '{"body": "the sharpened statement"}' \
  last_body /tickets/5/body
# Body is a human-only route (API.md §4.2), like every other verb in this file.
t "a body write speaks as the human principal" '"auth": "Bearer h"' last_line /tickets/5/body
# Write-if-changed is the server's; the flag is it saying nothing was recorded.
t "a noop body edit says so" "#5: body rewritten (noop)" V board-body.sh 5 --body-file "$BF"

# An empty file is a legal edit — clearing the statement of work — not a caller
# mistake to refuse, and it must go out as an empty string rather than a
# dropped key (which the server would read as "no change asked for").
EMPTYB="$(mktemp)"; : > "$EMPTYB"
t "an empty body file is a legal edit" "#5: body rewritten" V board-body.sh 5 --body-file "$EMPTYB"
t "the cleared payload is an empty string, not a dropped key" '{"body": ""}' \
  last_body /tickets/5/body

# `-` is the documented stdin spelling; it must reach the wire whole.
STDIN_RC=0
( cd "$r" && printf 'piped statement' | BOARD_CREDENTIALS_FILE="$CREDS" \
  "$SCRIPTS/board-body.sh" 5 --body-file - ) >/dev/null 2>&1 || STDIN_RC=$?
t "a stdin body edit exits zero" "rc=0" echo "rc=$STDIN_RC"
t "a body read from stdin reaches the wire" '{"body": "piped statement"}' \
  last_body /tickets/5/body

# The stdin spelling has to mktemp, and what it spools there is the ticket's
# FULL statement of work — left behind, it accumulates in the temp directory
# for anyone who shares it. The probe is a content search, not a file count:
# TMPDIR is not honored by every mktemp (BSD's ignores it), so the only
# portable question is whether THIS run's text is still on disk anywhere the
# spool could have landed. A unique sentinel keeps a parallel run out of it.
# It deliberately runs on the REFUSAL path — this call lands past the
# fixture's four 200s — since a hard exit must clean up too.
LEAK_SENTINEL="spool-leak-probe-$$-$RANDOM"
LEAK_TMPD="$(dirname "$(mktemp -u)")"
# A MARKER FILE, not a pre-listing to diff against. The shared temp directory
# holds six figures of entries on a long-lived machine, and `grep -vxF -f` over
# two listings that size is quadratic — tens of minutes for a probe that is
# looking for at most one file. Anything the verb spooled is newer than a file
# stamped immediately before it ran. The fixture log is the one exception the
# pre-listing used to absorb for free: the call reaches the wire, so the mock
# records the sentinel body there — the harness's own transcript, not a spool.
LEAK_MARK="$(mktemp)"
( cd "$r" && printf 'statement %s\n' "$LEAK_SENTINEL" | \
  BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-body.sh" 5 --body-file - ) >/dev/null 2>&1 || true
leak_probe() {
  local f n=0
  while IFS= read -r f; do
    grep -qF "$LEAK_SENTINEL" "$f" 2>/dev/null && n=$((n + 1))
  done < <(find "$LEAK_TMPD" -maxdepth 1 -type f -newer "$LEAK_MARK" \
             ! -path "$FIX.log" 2>/dev/null || true)
  printf 'leftover-spools=%s\n' "$n"
}
t "the stdin spool file does not outlive the run" "leftover-spools=0" leak_probe

# The body IS the assignment a claim hands the worker, so the server refuses an
# edit while a run holds the ticket. The client relays that, unrewritten.
OWNED_OUT="$(mktemp)"; OWNED_RC=0
V board-body.sh 5 --body-file "$BF" > "$OWNED_OUT" 2>&1 || OWNED_RC=$?
t "ticket-owned surfaces naming the run" "ticket-owned — ticket 5 is owned by run 41" \
  cat "$OWNED_OUT"
t "an owned refusal exits nonzero" "rc=1" echo "rc=$OWNED_RC"

t "a non-numeric body ref dies like the gh path" "not an issue number: abc" \
  V board-body.sh abc --body-file "$BF"
t "a missing body file is a caller error, not a request" "no such file: /nope/nope" \
  V board-body.sh 5 --body-file /nope/nope

# In API mode gh is never invoked — asserted with a stub, as everywhere else.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
_no_gh() {  # <verb> <args...> — same call, but with a gh that announces itself
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' \
    '$SCRIPTS/$1' ${*:2}"
}
nt "api edge verbs never invoke gh" "GH-CALLED" _no_gh board-edge.sh 5 --block 7
nt "api relate never invokes gh" "GH-CALLED" _no_gh board-relate.sh 5 7 --cut
nt "api priority never invokes gh" "GH-CALLED" _no_gh board-priority.sh 5 P2
nt "api body never invokes gh" "GH-CALLED" _no_gh board-body.sh 5 --body-file "$BF"

# ---- board-body.sh (gh half): the raw meta splice ----
# The TRAILING board:meta block must survive BYTE-FOR-BYTE, noncanonical
# spelling and unknown future keys included — parse/render would canonicalize
# and drop. The stored prose deliberately QUOTES a marker-like example before
# the real trailing block: META_RE is leftmost-first and its `.*?` spans from
# the quote clear through to the real `-->`, so a first-match splice keeps the
# prose it was told to replace. This fixture is the guard against that.
ghr="$(mkrepo)"
gstub="$(mktemp -d)"
cat > "$gstub/gh" <<'EOF'
#!/usr/bin/env bash
# Every gh call the verb makes, answered contract-shaped:
#   repo view  --json nameWithOwner --jq .nameWithOwner  → _lib.sh's BOARD_REPO
#   issue view <n> -R <repo> --json body --jq .body      → the stored body
#   issue edit <n> -R <repo> --body-file -               → capture stdin
# Anything else fails loud rather than returning a plausible `{}`: the assert
# below pins this command's EXIT STATUS, so an unanticipated call must show up
# as a failure and not as a silently swallowed stub answer.
case "$*" in
  *"repo view"*) echo 'acme/board' ;;
  *"issue view"*) printf 'old prose quoting an example:\n<!-- board:meta\nfake: example\n-->\nmore old prose\n\n<!-- board:meta\nfuture-key: kept\n# a comment line\nbranch:   odd/spacing\n-->\n' ;;
  *"issue edit"*) cat > "$GH_BODY_CAPTURE" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
EOF
chmod +x "$gstub/gh"
NEWB="$(mktemp)"; printf 'new prose' > "$NEWB"
CAP="$(mktemp)"
GH_RC=0
( cd "$ghr" && PATH="$gstub:$PATH" GH_BODY_CAPTURE="$CAP" \
  "$SCRIPTS/board-body.sh" 12 --body-file "$NEWB" ) >/dev/null 2>&1 || GH_RC=$?
t "gh body edit exits zero (no swallowed stub failure)" "rc=0" echo "rc=$GH_RC"

# Byte-for-byte means byte-for-byte: a substring match would pass on a block
# that had been reparsed and re-rendered line by line, so compare the tail of
# what was written against the stored block's exact bytes.
WANT_META="$(mktemp)"
printf '<!-- board:meta\nfuture-key: kept\n# a comment line\nbranch:   odd/spacing\n-->\n' \
  > "$WANT_META"
meta_tail_check() {
  local n; n=$(( $(wc -c < "$WANT_META") ))
  if cmp -s <(tail -c "$n" "$CAP") "$WANT_META"; then echo meta-intact
  else echo "meta-DIFFERS — the body that was written:"; cat "$CAP"; fi
}
t "gh body edit keeps the TRAILING meta block byte-for-byte" "meta-intact" meta_tail_check
t "gh body edit replaced the prose" "new prose" cat "$CAP"
nt "gh body edit did not keep the old prose" "old prose" cat "$CAP"
nt "the quoted marker example did not survive as a splice point" "fake: example" cat "$CAP"

finish
