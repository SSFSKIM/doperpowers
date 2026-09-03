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
 {"method":"POST","path":"/runs/46/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/40/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"reaped"}}},
 {"method":"POST","path":"/runs/50/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"reclaimed mid-tick"}}},
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
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

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
# alive, run 41, bind never confirmed by the server -> renew + bind repair.
# It holds its OWN bearer: the repair speaks as the run it is repairing, and a
# meta with no bearer at all is refused by board-bind rather than confirmed.
meta u-1 '{"uuid":"u-1","current":"u-1","status":"working","run_id":41,"fence":3,
           "lane":"implementer","bind_confirmed":false,"ticket":"7","run_bearer":"tok-w1"}'
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
# ANOTHER BINDING'S DAEMON, alive and renewable, sharing this registry. Two
# api-bound repos on one machine share $DAEMON_HOME and their `board` values are
# identical (one service, several repos), so the repo stamp is the only thing
# separating them. Unfiltered, this tick renewed a neighbour's run and — worse —
# re-bound it, overwriting that run's session locator with this repo's
# projectKey. Every meta above is UNSTAMPED on purpose: that is the legacy shape
# from before the stamp existed, and it must still be acted on.
meta u-6 '{"uuid":"u-6","current":"u-6","status":"working","run_id":46,"fence":1,
           "lane":"implementer","bind_confirmed":true,"ticket":"31",
           "board":"api:http://127.0.0.1:'"$PORT"'","board_repo":"otherrepo"}'

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
# A REAL transcript line. The delivery proof reads user-role JSONL entries
# whose content is a plain string — a delivered PROMPT — never the raw bytes:
# tool results ride the same \`user\` type as a content LIST, which is how
# arbitrary text (a file the worker cat-ed, a pasted answer) gets into the file.
T_P="$TX" T_C="\$2" python3 - <<'PYX'
import json, os
with open(os.environ["T_P"], "a") as f:
    f.write(json.dumps({"type": "user",
                        "message": {"role": "user", "content": os.environ["T_C"]}}) + "\n")
PYX
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

# The sweep's tick lock is keyed by BINDING (url + repo), so a drill that holds
# or inspects one has to name the same digest _sweep_api.sh computes.
lock_key() {  # lock_key <repo-key>
  T_URL="http://127.0.0.1:$PORT" T_REPO="$1" python3 -c '
import hashlib, os
print(hashlib.sha256(("%s|%s" % (os.environ["T_URL"], os.environ["T_REPO"]))
                     .encode()).hexdigest()[:16])'
}
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
t  "an UNSTAMPED meta is still this binding's" '"path": "/runs/41/renew"' cat "$FIX.log"
nt "but another binding's daemon is left alone" "/runs/46/renew"          cat "$FIX.log"
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
           "lane":"implementer","bind_confirmed":false,"ticket":"7","run_bearer":"tok-w1"}'
SWEVIL renew > "$TDIR/renew-evil.out" 2>&1 || true
t  "renew still speaks as automation under an ambient run token" '"auth": "Bearer a"' cat "$FIX.log"
nt "an ambient run token never reaches the wire"  "tok-evil"     cat "$FIX.log"
# Report the field, never the meta: a bearer that leaked here would otherwise
# be printed by the failure path.
u1_bearer() { python3 -c 'import json, sys
print("run_bearer=%s" % (json.load(open(sys.argv[1])).get("run_bearer") or "none"))' "$DH/u-1.json"; }
t  "bind repair keeps the meta's OWN bearer, not the ambient one" "run_bearer=tok-w1" u1_bearer

# ...and a meta with no bearer at all is not repairable: confirming that bind
# would declare it complete while every later resume of the run could not speak
# as it. Refused loudly, and the run is left for the lease to reclaim.
: > "$FIX.log"
meta u-1 '{"uuid":"u-1","current":"u-1","status":"working","run_id":41,"fence":3,
           "lane":"implementer","bind_confirmed":false,"ticket":"7"}'
SW renew > "$TDIR/renew-nobearer.out" 2>&1 || true
t  "a bearerless bind repair is refused"   "bind refused for run 41" cat "$TDIR/renew-nobearer.out"
t  "and the tick reports the failed repair" "bind repair FAILED"     cat "$TDIR/renew-nobearer.out"
nt "nothing is confirmed"                   '"bind_confirmed": true' cat "$DH/u-1.json"

# =========================================================================
# Phase 2 — relay
#
# The transcript is POISONED first: a tool-result entry carrying answer 118s
# sentinel as DATA — a worker that cat-ed a file, a human who pasted an earlier
# answer back. A fixed-string grep over the raw bytes reads that as proof of
# delivery and acks an answer nobody ever saw; only a user-role entry whose
# content is a plain STRING is a prompt that was actually injected.
# =========================================================================
python3 - "$TX" <<'PYPOISON'
import json, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content":
         "here is what the file said: [board-relay answer:118] ..."}]}}) + "\n")
PYPOISON
OUT2="$TDIR/relay.out"
SW relay > "$OUT2" 2>&1 || true

t "a sentinel quoted as tool-result data is not delivery proof" \
  "RESUME uuid=u-3"                                                        cat "$RESUME_LOG"
nt "so the answer is not acked undelivered"  "already delivered (sentinel)" cat "$OUT2"
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
# WHEREVER THE URL IS PINNED FOR A WORKER, THE REPO IS PINNED WITH IT. A worker
# checks out the head it was dispatched for, and a head predating the repo key
# carries a two-key board.json — so an unpinned sweep-driven turn dies on
# `binding=api but no repo`. The dispatcher pins it for the FIRST turn; without
# it here the worker loses the pin on every turn the sweep drives afterwards.
t  "and the repo it speaks for"        "BOARD_REPO=testrepo"               cat "$RESUME_LOG"
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
delivered_content() { python3 -c 'import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    c = r.get("message", {}).get("content")
    if r.get("type") == "user" and isinstance(c, str):
        sys.stdout.write(c + "\n")' "$TX"; }
prompt_is_exact() { delivered_content | diff "$EXPECT" - && echo "prompt=exact"; }
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
ack_feed_reads() { echo "reads=$(grep -c '"path": "/answers/unrelayed?repo=testrepo"' "$FIX.log")"; }
t  "and buys no further feed read"       "reads=1"                   ack_feed_reads
nt "and does not hang"                   "TIMEOUT"                   cat "$OUTACK"

# ---- a failed delivery acks nothing and stops the pass ---------------------
: > "$FIX.log"
OUT3="$TDIR/relay3.out"
RESUME_MUST_FAIL=1 SWB relay > "$OUT3" 2>&1 || true
t  "a resume that reported no delivery is not called a failure" \
   "the resume returned no delivery"                              cat "$OUT3"
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
feed_reads() { echo "reads=$(grep -c '"path": "/answers/unrelayed?repo=testrepo"' "$FIX.log")"; }
t  "it re-reads the feed exactly once"     "reads=1"              feed_reads

# =========================================================================
# One tick at a time — a held lock skips the whole thing (the sentinel check
# and its resume must not interleave with another tick's).
# =========================================================================
: > "$FIX.log"
mkdir "$DH/.sweep-api.$(lock_key testrepo).lock"
t  "a held lock skips the tick"  "holds the lock"  SW all
nt "and sends nothing"           '"method"'        cat "$FIX.log"
rmdir "$DH/.sweep-api.$(lock_key testrepo).lock"

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

# =========================================================================
# THE LOCK OWNER IS A PROCESS, NOT A NUMBER. A stale lock is stolen only when
# its owner is provably gone — and a pid alone cannot say that: pids are
# recycled, and after a reboot the crashed sweep's number is very likely a live
# long-running process. `kill -0` then answers yes forever, nothing ever steals
# the lock, and every later api sweep exits at once (no renewal, no relay, no
# resume, no dispatch). The recorded process START TIME is what separates the
# owner from its number's next tenant.
# =========================================================================
: > "$FIX.log"
LK="$DH/.sweep-api.$(lock_key testrepo).lock"
lock_as() {  # lock_as <pid> <recorded start> — plant a lock and age it past stale
  rm -rf "$LK"; mkdir "$LK"
  printf '%s\n' "$1" > "$LK/owner"
  printf '%s\n' "$2" > "$LK/owner-start"
  touch -t 200001010000 "$LK"
}
# `lstart` is a RENDERED date — month and day names from the locale, clock from
# the zone — so the token is written and read under a pinned C/UTC and carries
# the FORMAT VERSION that pinning is. The prefix is spelled out here rather than
# read from the script: this suite is where the on-disk format is pinned, and a
# test that imported the constant would follow a silent change instead of
# catching it.
FMT=c1
started_now() { printf '%s:%s' "$FMT" \
  "$(LC_ALL=C TZ=UTC ps -p $$ -o lstart= | sed 's/^ *//;s/ *$//')"; }
# This test process is unquestionably alive, and its pid stands in for the
# recycled one: the recorded start belongs to the sweep that died, not to it.
lock_as "$$" "$FMT:Thu Jan  1 00:00:00 2000"
t  "a stale lock whose pid was recycled is stolen" \
   "stole a stale api sweep lock"                       SW renew
# ...and the live-owner half still holds: same pid, and this time the start
# time really is its own, so the lock is its and must not be taken.
lock_as "$$" "$(started_now)"
t  "a live owner is never robbed, however old its lock" \
   "another api sweep holds the lock"                   SW renew
# A lock from before the start file existed names no start: the pid answer is
# all the evidence there is, exactly as before.
rm -f "$LK/owner-start"
t  "a startless lock still obeys a live pid" \
   "another api sweep holds the lock"                   SW renew
# ...and `ps` has a THIRD answer: none at all. A hiccup, a process table read
# that loses a race, a ps that some later OS renders differently — the current
# start comes back EMPTY, and empty is not evidence of death. Compared as a
# plain string it reads as a mismatch, so the lock is stolen from an owner
# `kill -0` just said is alive, and two ticks then interleave the sentinel
# check with its resume: the exact double delivery this lock exists to prevent.
# UNKNOWN FAILS CLOSED — the stale-age rule alone never overrides a live pid.
cat > "$STUB/ps" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$STUB/ps"
lock_as "$$" "$FMT:Thu Jan  1 00:00:00 2000"
t  "an unreadable current start never steals from a live owner" \
   "another api sweep holds the lock"                   SW renew
rm -f "$STUB/ps"
# THE ROLLING UPGRADE, both directions. The sweep holding the lock right now may
# be a PREVIOUS shape of this script, which recorded a bare `lstart` — and a
# bare token has to be read, not waved through, because the two mistakes
# available here are opposite and both fatal.
#
# Read as a mismatch, a live owner is robbed mid-tick and two ticks interleave
# the sentinel check with its resume: the double delivery the lock prevents.
# Waved through as "unreadable", a RECYCLED pid under such a lock is believed
# alive forever — no renewal, no relay, no resume, no dispatch — which is the
# wedge the start time was recorded to prevent in the first place. So a bare
# token is compared against the renderings an earlier version could have
# written, and only a rendering this script cannot generate stays unknown.
#
# Live owner, bare token in the machine's OWN zone — what an unpinned writer
# produced. Held.
lock_as "$$" "$(LC_ALL=C ps -p $$ -o lstart= | sed 's/^ *//;s/ *$//')"
t  "a bare legacy token still recognizes its live owner" \
   "another api sweep holds the lock"                   SW renew
# Same bare format, but a start that is nobody's: the pid was recycled under a
# pre-versioning lock. This is the case the version prefix must NOT swallow.
lock_as "$$" "Thu Jan  1 00:00:00 2000"
t  "a bare legacy token whose pid was recycled is stolen" \
   "stole a stale api sweep lock"                       SW renew
# ...and the limit of that reading: a token rendered by a locale this script
# cannot reproduce is not evidence either way, so the owner keeps its lock.
lock_as "$$" "Do 1. Jan 00:00:00 2000"
t  "a rendering this script cannot reproduce stays unknown" \
   "another api sweep holds the lock"                   SW renew
rm -rf "$LK"

# =========================================================================
# A RENEWAL THAT ENDS THE CANDIDATE'S RUN CANCELS THE DELIVERY. The relay picks
# its candidate, then renews every lease ahead of a delivery that may block —
# and that renewal is exactly where a reclaimed run answers 409 run-ended and
# _retire_run_locally strips run, bearer and fence off this very meta. Resuming
# on the locals read before it forks the predecessor with REVOKED credentials,
# moments before the resume phase gives the ticket a real successor.
# =========================================================================
meta u-8 '{"uuid":"u-8","current":"u-8","status":"working","run_id":50,"fence":2,
           "lane":"implementer","bind_confirmed":true,"ticket":"99","run_bearer":"tok-w8"}'
: > "$FIX.log"
before_8="$(wc -l < "$RESUME_LOG")"
OUTR="$TDIR/relay-renew-retired.out"
SWB relay > "$OUTR" 2>&1 || true
after_8="$(wc -l < "$RESUME_LOG")"
resumes_8() { echo "delta=$((after_8 - before_8))"; }
t  "a run ended by the pre-delivery renewal cancels the relay" \
   "ended under the renewal that preceded this delivery"  cat "$OUTR"
t  "the retirement did land on that meta"  "run_ended_at"  cat "$DH/u-8.json"
t  "and the session is not resumed on revoked credentials" "delta=0" resumes_8
nt "nor is the answer acked"               "/answers/120/ack"        cat "$FIX.log"
nt "and the pass does not hang"            "TIMEOUT"                 cat "$OUTR"
rm -f "$DH/u-8.json"

# ---- the tick lock is PER BINDING, not per machine -------------------------
# Two api-bound repos on one machine share $DAEMON_HOME, so a single
# `.sweep-api.lock` made their timers mutually exclusive: the loser exited
# without renewing, relaying, resuming or dispatching for a whole tick — longer
# than a lease, on runs the winner's board knows nothing about. The lock's job
# is to serialize ticks against ONE board's state, and two boards share none.
SECOND="$(mkrepo)"; mkdir -p "$SECOND/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"otherrepo"}' "$PORT" \
  > "$SECOND/.doperpowers/board.json"
SW2() {  # a tick for the SECOND binding, same registry, same mock
  ( cd "$SECOND" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" "$@" )
}
# Hold one binding's lock by hand — the shape a mid-tick neighbour presents —
# and prove the other binding is unaffected while the SAME binding still backs
# off. Written as a live owner (this shell) so the staleness rule cannot steal
# it and turn a real exclusion into a pass.
hold_lock() {  # hold_lock <repo-key>
  local d; d="$DH/.sweep-api.$(lock_key "$1").lock"
  mkdir -p "$d"; echo "$$" > "$d/owner"
  printf '%s
' "$(ps -o lstart= -p $$ 2>/dev/null | tr -s ' ')" > "$d/owner-start"
}
hold_lock testrepo
nt "a second binding's tick is not blocked by the first's lock" \
  "another api sweep holds the lock" SW2 renew
t  "and the same binding still excludes itself" \
  "another api sweep holds the lock" SW renew
rm -rf "$DH/.sweep-api.$(lock_key testrepo).lock"

finish
