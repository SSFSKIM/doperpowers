#!/usr/bin/env bash
# test-sweep-renew-relay.sh — _sweep_api.sh phases 1+2, against a real socket
# and a real registry.
#
# RENEW pins: every LIVE run's lease is renewed (an idle-but-parked worker
# included — it is waiting, not gone); a DEAD session's lease is NOT renewed,
# because letting it expire is how the server reclaims the run; a 409
# run-ended is routed to the resume path rather than failing the tick; and a
# meta whose bind the server never confirmed is repaired through board-bind.
#
# RELAY pins: the answer reaches the worker through daemon-resume with the run
# credentials re-injected from the meta (ENV, never argv — daemon-resume forks
# a fresh process from the caller's environment); the ack fires only on PROVEN
# delivery — the sentinel already in the transcript, or a resume that returned
# success; a dead-session or failed delivery acks NOTHING and breaks the drain
# loop instead of spinning on the same page.
#
# The transcript is resolved the way orchestrating-daemons' own tooling does
# (the CURRENT turn's session jsonl under $HOME/.claude/projects) — no meta
# here carries a fabricated `transcript` field, so the derivation is under
# test rather than assumed.
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
# A drain loop that fails to break would HANG the suite; bound the calls that
# exist to prove the break, so a regression fails loudly instead.
bounded() { python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[1:], timeout=30))
except subprocess.TimeoutExpired:
    print("TIMEOUT"); sys.exit(124)' "$@"; }

TDIR="$(mktemp -d)"
CREDS="$TDIR/creds.env"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"

# ---- the wire ---------------------------------------------------------------
# The unrelayed feed is level-triggered until ack, so the fixture serves it
# once per pass, in the order the four relay invocations below consume it:
#   1. two answers — one deliverable (#12), one whose ticket has no session
#   2. []                                  -> pass 2 sees nothing, drains
#   3. answer 118 again, sentinel now in the transcript (replay/idempotence)
#   4. []
#   5. answer 121 — delivery FAILS (the resume stub exits nonzero)
#   6. (default, never consumed) answer 120 for a session-less ticket: a
#      broken zero-ack break would spin on it forever
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/41/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/43/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/40/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"reaped"}}},
 {"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101",
           "replies":["ship it","and squash the fixups"]},
          {"answerEventId":119,"ticketId":99,"correlationId":"evt-102",
           "replies":["nobody home"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101",
           "replies":["ship it","and squash the fixups"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":121,"ticketId":12,"correlationId":"evt-103",
           "replies":["try again"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,
  "body":[{"answerEventId":120,"ticketId":99,"correlationId":"evt-104",
           "replies":["still nobody"]}]},
 {"method":"POST","path":"/answers/118/ack","status":200,"body":{"acked":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"

# A `gh` stub earlier on PATH than any real gh: the api tick must never reach
# it. It records to a FILE — a stub that only echoed would be invisible.
STUB="$TDIR/stub"; mkdir -p "$STUB"; MARKER="$TDIR/gh-invoked"; : > "$MARKER"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH-CALLED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

# ---- the registry -----------------------------------------------------------
DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/daemon-scripts"; mkdir -p "$DS"
# HOME is pinned: the transcript derivation reads $HOME/.claude/projects, and
# a fall-through would search (and match against) the operator's real sessions.
TESTHOME="$TDIR/home"; PROJ="$TESTHOME/.claude/projects/-tmp-consumer"
mkdir -p "$PROJ"
# u-3 has FORKED at least once: its stable uuid is u-3, its live turn (and so
# its transcript) is u-3-cur. Deriving from the stable uuid alone would find
# nothing here — which is the point.
TX="$PROJ/u-3-cur.jsonl"; : > "$TX"

meta() {  # meta <uuid> <json>
  printf '%s\n' "$2" > "$DH/$1.json"
}
# alive, run 41, bind never confirmed by the server -> renew + bind repair
meta u-1 '{"uuid":"u-1","current":"u-1","status":"working","run_id":41,"fence":3,
           "lane":"implementer","bind_confirmed":false,"ticket":"7"}'
# alive, but the server already reaped run 40 -> routed, not fatal
meta u-2 '{"uuid":"u-2","current":"u-2","status":"working","run_id":40,"fence":2,
           "lane":"implementer","bind_confirmed":true,"ticket":"8"}'
# parked on #12 with its turn ended: still alive, still holds run 43, and it
# is the relay target. The bearer at rest is what the relay speaks with.
meta u-3 '{"uuid":"u-3","current":"u-3-cur","status":"idle","run_id":43,"fence":1,
           "lane":"implementer","bind_confirmed":true,"ticket":"12","run_bearer":"tok-w3"}'
chmod 600 "$DH/u-3.json"
# the session is GONE — its lease must expire, not be renewed
meta u-4 '{"uuid":"u-4","current":"u-4","status":"working","run_id":44,"fence":1,
           "lane":"implementer","bind_confirmed":true,"ticket":"9"}'
# no run at all (a gh-era or review-species meta) — nothing to renew, no crash
meta u-5 '{"uuid":"u-5","current":"u-5","status":"working","name":"review-pr-3"}'

RESUME_LOG="$TDIR/resume.log"; : > "$RESUME_LOG"
cat > "$DS/daemon-resume.sh" <<EOF
#!/usr/bin/env bash
{ echo "RESUME uuid=\$1"
  echo "ARGV: \$*"
  env | grep '^BOARD_' | sort || true; } >> "$RESUME_LOG"
[ -n "\${RESUME_MUST_FAIL:-}" ] && exit 1
printf '%s\n' "\$2" >> "$TX"   # delivery IS the transcript write
EOF
chmod +x "$DS/daemon-resume.sh"
# Liveness, as daemon-finalize reports it: `noop` is what an already-terminal
# (idle) meta answers, and it means the session is still there.
cat > "$DS/daemon-finalize.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in u-4) echo absent ;; u-3) echo noop ;; *) echo live ;; esac
EOF
chmod +x "$DS/daemon-finalize.sh"

SW() {  # SW <phase> — one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" "$@" )
}
SWB() {  # the same, time-bounded (used where a hang is the failure mode)
  ( cd "$r" || exit 1
    export PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS"
    bounded "$SCRIPTS/_sweep_api.sh" "$@" )
}

# =========================================================================
# Phase 1 — renew
# =========================================================================
OUT1="$TDIR/renew.out"
rc=0; SW renew > "$OUT1" 2>&1 || rc=$?
show_rc() { echo "rc=$rc"; }

t  "a live run's lease is renewed"          '"path": "/runs/41/renew"' cat "$FIX.log"
t  "a parked-but-live run is renewed too"   '"path": "/runs/43/renew"' cat "$FIX.log"
nt "a dead session's lease is left to expire" "/runs/44/renew"         cat "$FIX.log"
t  "renew speaks as automation"             '"auth": "Bearer a"'       cat "$FIX.log"
t  "run-ended routes to resume, not error"  "run 40: ended (reaped) — resume path" cat "$OUT1"
t  "and the phase still exits clean"        "rc=0"                     show_rc
t  "an unconfirmed bind is repaired"        '"path": "/runs/41/bind"'  cat "$FIX.log"
t  "the repair records the confirmation"    '"bind_confirmed": true'   cat "$DH/u-1.json"
nt "a confirmed bind is not re-bound"       "/runs/43/bind"            cat "$FIX.log"
nt "the api tick never invokes gh"          "GH-CALLED"                cat "$MARKER"

# =========================================================================
# Phase 2 — relay
# =========================================================================
OUT2="$TDIR/relay.out"
SW relay > "$OUT2" 2>&1 || true

t "the sentinel reaches the worker"    "[board-relay answer:118]"          cat "$TX"
t "so does the protocol instruction"   "Re-state your gate verdict"        cat "$TX"
t "and the answers, verbatim"          "---- answers (verbatim) ----"      cat "$TX"
t "every reply line is carried"        "and squash the fixups"             cat "$TX"
t "the answer is acked after delivery" '"path": "/answers/118/ack"'        cat "$FIX.log"
t "the resume names the bound session" "RESUME uuid=u-3"                   cat "$RESUME_LOG"
# daemon-resume forks a fresh process from the CALLER's env, so the run
# credentials have to be re-injected from the meta on every resume.
t  "the run bearer is re-injected"     "BOARD_RUN_TOKEN=tok-w3"            cat "$RESUME_LOG"
t  "with its run id"                   "BOARD_RUN_ID=43"                   cat "$RESUME_LOG"
t  "and its fence"                     "BOARD_RUN_FENCE=1"                 cat "$RESUME_LOG"
t  "and the board url"                 "BOARD_API_URL=http://127.0.0.1:$PORT" cat "$RESUME_LOG"
argv_only() { grep '^ARGV:' "$RESUME_LOG"; }
nt "the bearer never rides on argv"    "tok-w3"                            argv_only
# #99 has no bound session: never ack-and-drop — the successor path delivers.
t  "a session-less answer is reported" "no live bound session"             cat "$OUT2"
nt "and is not acked"                  "/answers/119/ack"                  cat "$FIX.log"

# The prompt is a pinned contract, not prose: the sentinel is what makes a
# replay detectable, and the instruction is what keeps a worker from building
# on momentum past an answer that reshaped the work. Byte-exact, whole.
EXPECT="$TDIR/expected-prompt.txt"
cat > "$EXPECT" <<'EOF'
[board-relay answer:118] Your needs-human park on this ticket was answered by
the human. Re-state your gate verdict against the answers in ONE paragraph as
a ticket comment ("[gate] re-pass — <one line>" — PLAN-EXECUTION, which ran no
gate, restates plan-execution status instead), or park fresh if the answers
reshape the work's scope, then proceed under your original protocol. Never
build on momentum past an answer that changed the work's shape.

---- answers (verbatim) ----
ship it
and squash the fixups
EOF
prompt_is_exact() { diff "$EXPECT" "$TX" && echo "prompt=exact"; }
t "the delivered prompt is byte-exact" "prompt=exact" prompt_is_exact

# ---- replay: the same answer served again, sentinel already present --------
: > "$FIX.log"
before="$(grep -c "board-relay" "$TX")"
SW relay > "$TDIR/relay2.out" 2>&1 || true
after="$(grep -c "board-relay" "$TX")"
delta() { echo "delta=$((after - before))"; }
resumes() { grep -c "RESUME uuid=" "$RESUME_LOG"; }
t "no double-resume on replay"          "delta=0"                    delta
t "the replay is recognized as delivered" "already delivered (sentinel)" cat "$TDIR/relay2.out"
t "and re-acks (ack is set-once)"       '"path": "/answers/118/ack"'  cat "$FIX.log"

# ---- a failed delivery acks nothing and stops the pass ---------------------
: > "$FIX.log"
OUT3="$TDIR/relay3.out"
RESUME_MUST_FAIL=1 SWB relay > "$OUT3" 2>&1 || true
t  "a failed resume is reported"        "resume FAILED"          cat "$OUT3"
nt "a failed delivery acks nothing"     "/answers/121/ack"       cat "$FIX.log"
nt "and the pass does not hang"         "TIMEOUT"                cat "$OUT3"

# ---- a pass that acks nothing at all breaks the drain loop -----------------
# The feed now answers with the same undeliverable page forever; only the
# zero-progress break ends this call.
: > "$FIX.log"
OUT4="$TDIR/relay4.out"
SWB relay > "$OUT4" 2>&1 || true
nt "a zero-ack pass breaks the drain loop" "TIMEOUT"              cat "$OUT4"
feed_reads() { echo "reads=$(grep -c '"path": "/answers/unrelayed"' "$FIX.log")"; }
t  "it re-reads the feed exactly once"     "reads=1"              feed_reads

# =========================================================================
# One tick at a time — a held lock skips the whole thing (the sentinel check
# and its resume must not interleave with another tick's).
# =========================================================================
: > "$FIX.log"
mkdir "$DH/.sweep-api.lock"
t  "a held lock skips the tick"  "holds the lock"  SW all
nt "and sends nothing"           '"method"'        cat "$FIX.log"
rmdir "$DH/.sweep-api.lock"

# =========================================================================
# The entry point: board-sweep.sh hands an api-bound repo straight to this
# tick, BEFORE its own gh probe (the stub gh would fail the BOARD_REPO
# resolution, so reaching it at all is a visible failure).
# =========================================================================
: > "$FIX.log"; : > "$MARKER"
BS() {
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      LOCAL_REPO="$r" SWEEP_LOG="$TDIR/sweep.log" "$SCRIPTS/board-sweep.sh" )
}
BS > "$TDIR/board-sweep.out" 2>&1 || true
t  "board-sweep runs the api tick"        '"path": "/runs/41/renew"' cat "$FIX.log"
nt "without ever probing gh"              "GH-CALLED"                cat "$MARKER"
nt "and without the gh tick's passes"     "RECOVER:"                 cat "$TDIR/board-sweep.out"

# =========================================================================
# Wrong binding: this script has no gh half to fall back to.
# =========================================================================
ghrepo="$(mkrepo)"
wrong_binding() { ( cd "$ghrepo" && HOME="$TESTHOME" DAEMON_HOME="$DH" "$SCRIPTS/_sweep_api.sh" renew ); }
t "a gh-bound repo is refused loudly" "runs only under an api binding" wrong_binding

finish
