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
# a fresh process from the caller's environment); the resume's blocking wait is
# BOUNDED, because the whole tick holds the lock while it runs; the ack fires
# only on PROVEN delivery — the sentinel already in the transcript, or a resume
# that returned success; a dead-session or failed delivery acks NOTHING and
# breaks the drain loop instead of spinning on the same page.
#
# PRINCIPAL ISOLATION pins: an ambient BOARD_RUN_TOKEN — this tick launched
# from a worker's shell — never becomes the sweep's voice. The client's
# token() hands back the run token for ANY principal once one is in env, so
# without an explicit unset the tick would renew and ack as that worker, and a
# bind repair would stamp the foreign bearer into a DIFFERENT run's meta.
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
trap 'rm -rf "$TDIR"' EXIT
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
  "body":[{"answerEventId":123,"ticketId":12,"correlationId":"evt-105",
           "replies":["delivered, but the ack will not land"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":121,"ticketId":12,"correlationId":"evt-103",
           "replies":["try again"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":124,"ticketId":77,"correlationId":"evt-106",
           "replies":["for the forked session"]},
          {"answerEventId":125,"ticketId":78,"correlationId":"evt-107",
           "replies":["for the bearerless session"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,
  "body":[{"answerEventId":120,"ticketId":99,"correlationId":"evt-104",
           "replies":["still nobody"]}]},
 {"method":"POST","path":"/answers/118/ack","status":200,"body":{"acked":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; rm -rf "$TDIR"' EXIT
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
# The stub records its ENVIRONMENT, not just its argv: both the run
# credentials and the resume's wait bound are passed that way, and neither is
# observable any other place.
cat > "$DS/daemon-resume.sh" <<EOF
#!/usr/bin/env bash
{ echo "RESUME uuid=\$1"
  echo "ARGV: \$*"
  echo "DAEMON_TIMEOUT=\${DAEMON_TIMEOUT:-unset}"
  env | grep '^BOARD_' | sort || true; } >> "$RESUME_LOG"
[ -n "\${RESUME_MUST_FAIL:-}" ] && exit 1
printf '%s\n' "\$2" >> "$TX"   # delivery IS the transcript write
EOF
chmod +x "$DS/daemon-resume.sh"
# Liveness, as daemon-finalize actually reports it: `absent` when the session is
# gone from the harness, `noop` for an ALREADY-TERMINAL meta (idle or error —
# it never re-inspects one), `live` for a running turn. Driven off the meta the
# way the real script is, so a status the sweep writes is visible here.
cat > "$DS/daemon-finalize.sh" <<EOF
#!/usr/bin/env bash
[ "\$1" != u-4 ] || { echo absent; exit 0; }
python3 - "$DH/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
EOF
chmod +x "$DS/daemon-finalize.sh"

SW() {  # SW <phase> — one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" "$@" )
}
SWEVIL() {  # the same, but launched from a WORKER's environment: a run token
            # is already exported, as it would be for a tick started by hand
            # inside a dispatched session's shell.
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      BOARD_RUN_TOKEN=tok-evil "$SCRIPTS/_sweep_api.sh" "$@" )
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

# An ENDED run is over locally too. Left alone, the meta keeps its run id and
# its lane, and the dispatchers' local cap counts it — so a normally released
# run occupies a dispatch slot forever while never appearing in needing-resume.
# The lane deliberately STAYS (a successor inherits it); the run association is
# what goes, and the bearer with it.
slot_for() { python3 -c 'import json, sys
m = json.load(open(sys.argv[1]))
print("run=%s lane=%s bearer=%s" % (m.get("run_id") or "none", m.get("lane") or "none",
                                    "set" if m.get("run_bearer") else "none"))' "$DH/$1.json"; }
t "an ended run releases its local dispatch slot" "run=none lane=implementer bearer=none" \
  slot_for u-2
t "and the retirement is recorded"          "run_ended_at"             cat "$DH/u-2.json"
t "a live run keeps its slot"               "run=41 lane=implementer"  slot_for u-1

# =========================================================================
# Principal isolation — an inherited run token is not the sweep's voice.
# Two distinct harms, both pinned here: speaking on the wire as a worker that
# owns none of these runs (spec: "Renewal is dispatch automation, never worker
# prose"), and cross-run credential contamination — a bind repair for run 41
# writing the FOREIGN bearer into u-1's meta, after which every later resume
# of u-1 authenticates as the wrong run.
# =========================================================================
: > "$FIX.log"
# Re-arm the bind-repair path: the pass above already confirmed u-1.
meta u-1 '{"uuid":"u-1","current":"u-1","status":"working","run_id":41,"fence":3,
           "lane":"implementer","bind_confirmed":false,"ticket":"7"}'
SWEVIL renew > "$TDIR/renew-evil.out" 2>&1 || true
t  "renew still speaks as automation under an ambient run token" '"auth": "Bearer a"' cat "$FIX.log"
nt "an ambient run token never reaches the wire"  "tok-evil"     cat "$FIX.log"
# Report the field, never the meta: a bearer that leaked here would otherwise
# be printed by the failure path.
u1_bearer() { python3 -c 'import json, sys
print("run_bearer=%s" % (json.load(open(sys.argv[1])).get("run_bearer") or "none"))' "$DH/u-1.json"; }
t  "bind repair stamps no foreign bearer into the meta" "run_bearer=none" u1_bearer

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
# daemon-resume blocks for DAEMON_TIMEOUT/2 polls (default 18000 — hours)
# while THIS tick holds the whole-tick lock, so renewal would starve past the
# 15-minute lease and A1 would reclaim live runs. The relay bounds it.
t  "the resume's wait is bounded"      "DAEMON_TIMEOUT=300"                cat "$RESUME_LOG"
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
# This is also the degrade path for a resume whose bounded wait expires:
# daemon-resume injects the sentinel-bearing prompt BEFORE it blocks, so a
# timed-out resume exits nonzero and acks nothing this tick — and the NEXT
# tick lands exactly here, finding the sentinel and acking without
# re-delivering. Run hostile: the ack must speak automation too.
: > "$FIX.log"
before="$(grep -c "board-relay" "$TX")"
SWEVIL relay > "$TDIR/relay2.out" 2>&1 || true
after="$(grep -c "board-relay" "$TX")"
delta() { echo "delta=$((after - before))"; }
t "no double-resume on replay"          "delta=0"                    delta
t "the replay is recognized as delivered" "already delivered (sentinel)" cat "$TDIR/relay2.out"
t "and re-acks (ack is set-once)"       '"path": "/answers/118/ack"'  cat "$FIX.log"
t  "the ack speaks automation, not the ambient run token" '"auth": "Bearer a"' cat "$FIX.log"
nt "no ambient run token on the relay wire" "tok-evil"                cat "$FIX.log"

# ---- a failed ACK is not progress ------------------------------------------
# This whole phase runs behind `|| true` in the `all` case, which suspends
# errexit through its entire subtree — so a failed ack does not abort the loop,
# it falls THROUGH to the progress counter. Counted as progress, the level-
# triggered drain re-reads a feed still carrying the same unacked answer and
# re-reads it again, inside the whole-tick lock. There is no ack fixture for
# 123, so the mock answers 404.
: > "$FIX.log"
OUTACK="$TDIR/relay-ack.out"
SWB relay > "$OUTACK" 2>&1 || true
t  "the delivery itself landed"          "[board-relay answer:123]"  cat "$TX"
t  "a failed ack is reported"            "DELIVERED but the ack FAILED" cat "$OUTACK"
ack_feed_reads() { echo "reads=$(grep -c '"path": "/answers/unrelayed"' "$FIX.log")"; }
t  "and buys no further feed read"       "reads=1"                   ack_feed_reads
nt "and does not hang"                   "TIMEOUT"                   cat "$OUTACK"

# ---- a failed delivery acks nothing and stops the pass ---------------------
: > "$FIX.log"
OUT3="$TDIR/relay3.out"
RESUME_MUST_FAIL=1 SWB relay > "$OUT3" 2>&1 || true
t  "a failed resume is reported"        "resume FAILED"          cat "$OUT3"
nt "a failed delivery acks nothing"     "/answers/121/ack"       cat "$FIX.log"
nt "and the pass does not hang"         "TIMEOUT"                cat "$OUT3"

# ---- candidates the relay must REFUSE to speak to --------------------------
# Two shapes that read as "live and bound" to a naive selection loop and are
# not deliverable at all:
#
#   u-6  an UNRESOLVED FORK — daemon-resume launched a turn whose session uuid
#        never resolved, so it stamped status=error + pending_short and left
#        `current` on the superseded turn. The sentinel check then reads the
#        WRONG transcript, finds nothing, and resumes: a second zombie turn on
#        the same run, every tick, forever.
#   u-7  NO RUN BEARER — resuming it injects an EMPTY BOARD_RUN_TOKEN, and the
#        client falls back to the configured human/automation credentials the
#        moment the run token is blank, so the worker would speak with broader
#        authority than its own run and outside its fence.
meta u-6 '{"uuid":"u-6","current":"u-6","status":"error","pending_short":"fk01",
           "run_id":46,"fence":1,"lane":"implementer","bind_confirmed":true,
           "ticket":"77","run_bearer":"tok-w6"}'
meta u-7 '{"uuid":"u-7","current":"u-7","status":"idle","run_id":47,"fence":1,
           "lane":"implementer","bind_confirmed":false,"ticket":"78"}'
: > "$FIX.log"
OUTC="$TDIR/relay-candidates.out"
before_c="$(wc -l < "$RESUME_LOG")"
SWB relay > "$OUTC" 2>&1 || true
after_c="$(wc -l < "$RESUME_LOG")"
resumes_delta() { echo "delta=$((after_c - before_c))"; }
t  "an unresolved fork is refused, not re-forked" "UNRESOLVED FORK"   cat "$OUTC"
t  "a bearerless session is refused too"    "holds no run bearer"     cat "$OUTC"
t  "neither is resumed"                     "delta=0"                 resumes_delta
nt "and neither answer is acked"            "/answers/124/ack"        cat "$FIX.log"
nt "nor the other"                          "/answers/125/ack"        cat "$FIX.log"
rm -f "$DH/u-6.json" "$DH/u-7.json"

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
