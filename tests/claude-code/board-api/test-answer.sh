#!/usr/bin/env bash
# test-answer.sh — board-answer.sh under the API binding: the dual-principal
# answer + the inline relay, against a real socket and a real registry.
#
# What this pins:
#   PARK NAMED   the answer always carries `correlationId`, read from
#                GET /queue/decisions. Unnamed, the server answers whichever
#                question happens to be standing when the request lands — so a
#                delayed answer would be recorded against a question nobody
#                wrote it for. The lookup is species-scoped and ticket-scoped:
#                an `sdk-decision` park on the same ticket, and a `board` park
#                on a different one, are both decoys in the fixture.
#   TWO TOKENS   the answer leg speaks HUMAN (park-answer admits no other
#                principal), the ack leg speaks AUTOMATION (`ack-answer` admits
#                no human). One script, two principals — the one scripted
#                exception to fixed-token-per-script, so it is asserted on the
#                wire rather than assumed.
#   SERVER OWNS THE RETURN STATE  `returnedTo` is what prints. gh mode derives
#                the return state from the pre-park meta / the bound worker's
#                role; API mode never does — the server reads the bound run's
#                lane, which is why the gh half's role fallback has no API twin.
#   INLINE RELAY the human's answer wakes the worker NOW rather than next tick,
#                through the sweep's own relay pass (not a second copy of it).
#   REFUSALS     `--posted` is gh-mode-only here (an API park-answer IS the
#                record); an unbound park's `409 no-return-mapping` reaches the
#                human verbatim, and `--to` is the flag that answers it; a
#                `{"superseded": true}` answer dies and relays NOTHING.
. "$(dirname "$0")/helpers.sh"

free_port() { python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
wait_for_port() {  # poll rather than sleep — a fixed nap is a flake
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then return 0; fi
    tries=$((tries - 1)); sleep 0.05
  done
  return 1
}
# The inline relay drains a feed; a drain that failed to break would HANG the
# suite rather than fail it. Bound the invocation instead.
bounded() { python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[1:], timeout=60))
except subprocess.TimeoutExpired:
    print("TIMEOUT"); sys.exit(124)' "$@"; }

TDIR="$(mktemp -d)"
CREDS="$TDIR/creds.env"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"

# ---- the wire ---------------------------------------------------------------
# The decisions queue carries four parks. Only ONE of them is the standing
# `board` question on #12; a species-blind or ticket-blind lookup picks a decoy
# and the assertions below catch it.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/queue/decisions","status":200,
  "body":[{"correlation_id":"evt-301","ticket_id":99,"species":"board",
           "state":"needs-human","raised_at":"2026-08-09T01:00:00Z"},
          {"correlation_id":"sdk-777","ticket_id":12,"species":"sdk-decision",
           "state":"needs-human","raised_at":"2026-08-09T02:00:00Z"},
          {"correlation_id":"evt-101","ticket_id":12,"species":"board",
           "state":"needs-human","raised_at":"2026-08-09T03:00:00Z"},
          {"correlation_id":"evt-201","ticket_id":13,"species":"board",
           "state":"needs-human","raised_at":"2026-08-09T04:00:00Z"},
          {"correlation_id":"evt-401","ticket_id":14,"species":"board",
           "state":"needs-human","raised_at":"2026-08-09T05:00:00Z"},
          {"correlation_id":"sdk-888","ticket_id":15,"species":"sdk-decision",
           "state":"needs-human","raised_at":"2026-08-09T06:00:00Z"},
          {"correlation_id":"evt-501","ticket_id":16,"species":"board",
           "state":"needs-human","raised_at":"2026-08-09T07:00:00Z"}]},
 {"method":"POST","path":"/tickets/16/park-answer","status":200,
  "body":{"answered":true,"returnedTo":"in-progress","answerEventId":161}},
 {"method":"POST","path":"/tickets/12/park-answer","status":200,
  "body":{"answered":true,"returnedTo":"in-progress","answerEventId":118}},
 {"method":"POST","path":"/tickets/13/park-answer","status":409,"once":true,
  "body":{"error":{"code":"no-return-mapping",
                   "message":"unbound park: name the human's disposition"}}},
 {"method":"POST","path":"/tickets/13/park-answer","status":200,
  "body":{"answered":true,"returnedTo":"ready-for-implementer","answerEventId":131}},
 {"method":"POST","path":"/tickets/14/park-answer","status":200,
  "body":{"superseded":true}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101",
           "replies":["ship it"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"body":[]},
 {"method":"POST","path":"/answers/118/ack","status":200,"body":{"acked":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"

# A `gh` stub earlier on PATH than any real gh: the API path must never reach
# it. It records to a FILE — a stub that only echoed would be invisible.
STUB="$TDIR/stub"; mkdir -p "$STUB"; MARKER="$TDIR/gh-invoked"; : > "$MARKER"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH-CALLED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

# ---- the registry: #12 is bound to a live, parked worker --------------------
DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/daemon-scripts"; mkdir -p "$DS"
# HOME is pinned: the relay's transcript derivation reads $HOME/.claude/projects,
# and a fall-through would search the operator's real sessions.
TESTHOME="$TDIR/home"; PROJ="$TESTHOME/.claude/projects/-tmp-consumer"
mkdir -p "$PROJ"
TX="$PROJ/u-9-cur.jsonl"; : > "$TX"
cat > "$DH/u-9.json" <<'META'
{"uuid":"u-9","current":"u-9-cur","status":"idle","run_id":43,"fence":1,
 "lane":"executor","bind_confirmed":true,"ticket":"12","run_bearer":"tok-w9"}
META
chmod 600 "$DH/u-9.json"

cat > "$DS/daemon-resume.sh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$2" >> "$TX"   # delivery IS the transcript write
EOF
chmod +x "$DS/daemon-resume.sh"
# `noop` is what daemon-finalize answers for an already-terminal (idle) meta —
# it means the session is still there.
cat > "$DS/daemon-finalize.sh" <<'EOF'
#!/usr/bin/env bash
echo noop
EOF
chmod +x "$DS/daemon-finalize.sh"

ANS() {  # ANS <args...> — one board-answer.sh run against this fixture world
  ( cd "$r" || exit 1
    export PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS"
    bounded "$SCRIPTS/board-answer.sh" "$@" )
}

# =========================================================================
# The bound park: answer, then relay, in one blocking call.
# =========================================================================
OUT="$TDIR/answer.out"
rc=0; ANS 12 "ship it" > "$OUT" 2>&1 || rc=$?
show_rc() { echo "rc=$rc"; }

t  "the server's disposition is what prints" "answered #12 → in-progress" cat "$OUT"
t  "and the call succeeds"                   "rc=0"                       show_rc
nt "the answer never hangs"                  "TIMEOUT"                    cat "$OUT"

# The park is NAMED. (The mock logs the request body as a JSON string, so the
# needle is the escaped form — an unescaped one would pass against nothing.)
t  "the standing park's correlationId is sent" '\"correlationId\": \"evt-101\"' cat "$FIX.log"
nt "a same-ticket sdk-decision park is not it" "sdk-777"                     cat "$FIX.log"
nt "another ticket's board park is not it"     "evt-301"                     cat "$FIX.log"
t  "the answer rides as a one-element replies list" '\"replies\": [\"ship it\"]' cat "$FIX.log"
# A bound park's return state is the server's; naming `to` would be a
# disagreement (409 answer-target-not-allowed), so the client sends none.
nt "no disposition is smuggled onto a bound park" '\"to\":'                   cat "$FIX.log"

# Two principals, one script — asserted per leg.
answer_leg() { grep park-answer "$FIX.log"; }
ack_leg()    { grep '/answers/118/ack' "$FIX.log"; }
queue_leg()  { grep 'queue/decisions' "$FIX.log"; }
t  "the answer leg speaks human"      '"auth": "Bearer h"' answer_leg
nt "and never automation"             '"auth": "Bearer a"' answer_leg
t  "the queue read speaks human too"  '"auth": "Bearer h"' queue_leg
t  "the ack leg speaks automation"    '"auth": "Bearer a"' ack_leg
nt "and never the human token"        '"auth": "Bearer h"' ack_leg

# The relay ran INLINE — the worker is awake before this command returned.
t "the sentinel reached the bound worker" "[board-relay answer:118]" cat "$TX"
t "with the answer verbatim"              "ship it"                  cat "$TX"
t "and the protocol instruction"          "Re-state your gate verdict" cat "$TX"
t "the answer is acked after delivery"    '"path": "/answers/118/ack"' cat "$FIX.log"
nt "the API path never invokes gh"        "GH-CALLED"                cat "$MARKER"

# =========================================================================
# --posted: gh-mode-only. An API park-answer IS the record, so there is no
# "already commented by hand" to point at.
# =========================================================================
: > "$FIX.log"
t  "--posted is refused in API mode" "gh-mode-only"  ANS 12 --posted
nt "and never touches the wire"      '"method"'      cat "$FIX.log"
t  "--posted with answers is refused too" "--posted takes no answers text" \
   ANS 12 "ship it" --posted

# =========================================================================
# The unbound park: the server's 409 is the honest surface, and --to answers it.
# =========================================================================
: > "$FIX.log"
OUT13U="$TDIR/answer13-unbound.out"
ANS 13 "go with B" > "$OUT13U" 2>&1 || true
t  "an unbound park surfaces the server's code verbatim" "no-return-mapping" cat "$OUT13U"
t  "with the server's own guidance"   "name the human's disposition"         cat "$OUT13U"
nt "and a refused answer relays nothing" "/answers/unrelayed"                cat "$FIX.log"

: > "$FIX.log"
OUT13="$TDIR/answer13.out"
ANS 13 "go with B" --to ready-for-implementer > "$OUT13" 2>&1 || true
t "--to rides as the disposition"          '\"to\": \"ready-for-implementer\"' cat "$FIX.log"
t "a disposition answer still names its park" '\"correlationId\": \"evt-201\"'  cat "$FIX.log"
t "and the server's returnedTo is what prints" "answered #13 → ready-for-implementer" cat "$OUT13"

# =========================================================================
# Superseded: the standing question changed under the human. Nothing moved on
# the board, so nothing may be relayed either.
# =========================================================================
: > "$FIX.log"
OUT14="$TDIR/answer14.out"
rc14=0; ANS 14 "late answer" > "$OUT14" 2>&1 || rc14=$?
show_rc14() { echo "rc14=$rc14"; }
t  "a superseded answer dies"            "answer superseded"   cat "$OUT14"
t  "naming the queue as the way back"    "re-read the queue"   cat "$OUT14"
t  "and exits nonzero"                   "rc14=1"              show_rc14
nt "a superseded answer relays nothing"  "/answers/unrelayed"  cat "$FIX.log"

# =========================================================================
# Decoy-only queue: #15 carries a park, but not a `board` one — there is no
# name to send. An unnamed answer is the one thing this leg may never do (the
# server would bind it to whatever question is standing when it lands), so the
# refusal is CLIENT-SIDE: nothing goes on the wire past the queue read.
# =========================================================================
: > "$FIX.log"
OUT15="$TDIR/answer15.out"
rc15=0; ANS 15 "answer to a question nobody is asking" > "$OUT15" 2>&1 || rc15=$?
show_rc15() { echo "rc15=$rc15"; }
t  "no standing board park is refused" "no standing board park" cat "$OUT15"
t  "pointing at the decisions queue"   "GET /queue/decisions"    cat "$OUT15"
t  "and exits nonzero"                 "rc15=1"                  show_rc15
t  "after reading the queue as the human" '"auth": "Bearer h"'   cat "$FIX.log"
nt "no unnamed answer reaches the wire"   "park-answer"          cat "$FIX.log"
nt "and nothing is relayed"               "/answers/unrelayed"   cat "$FIX.log"

# =========================================================================
# A HELD TICK LOCK IS NOT A DELIVERY. The sweep exits 0 when another tick holds
# its lock — correct for the sweep, and read as success here it told the human
# their answer had been relayed when the inline wake never ran at all. The
# answer IS on the board either way; what changes is what this command claims.
# =========================================================================
: > "$FIX.log"
mkdir "$DH/.sweep-api.lock"
OUTLOCK="$TDIR/answer-lockheld.out"
ANS 16 "under a held lock" > "$OUTLOCK" 2>&1 || true
t  "a held sweep lock is surfaced, not swallowed" "the inline wake did not run" cat "$OUTLOCK"
t  "and the answer is still reported as recorded" "recorded on the board"       cat "$OUTLOCK"
nt "no delivery is claimed"                       "delivered to"                cat "$OUTLOCK"
rmdir "$DH/.sweep-api.lock"

# =========================================================================
# gh mode is untouched: --to has no gh half, and says so instead of being
# silently dropped onto a path that derives its return state from the meta.
# =========================================================================
ghrepo="$(mkrepo)"
gh_mode() { ( cd "$ghrepo" && PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
                BOARD_REPO=o/r HOME="$TESTHOME" DAEMON_HOME="$DH" \
                "$SCRIPTS/board-answer.sh" "$@" ); }
t "--to is refused in gh mode" "api-binding-only" gh_mode 12 "answer" --to deferred
t "a mistyped option dies rather than becoming the answer" "unknown option: --postd" \
  gh_mode 12 --postd

finish
