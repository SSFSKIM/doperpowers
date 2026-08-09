#!/usr/bin/env bash
# test-sweep-resume.sh — _sweep_api.sh phases 3+4, against a real socket, a
# real registry and the REAL dispatchers.
#
# RESUME-FIRST pins the recovery ladder the spec spells out (§ Dead-worker
# recovery policy), rung by rung:
#
#   1. resume the predecessor session on a freshly claimed SUCCESSOR run —
#      with the successor credentials injected into the resume, unrelayed
#      answers for that ticket folded into the prompt behind THE SAME
#      sentinel the relay uses, and the ack fired only after delivery;
#   2. PERSIST BEFORE RESUME — the successor run id, fence and bearer are in
#      the registry before any delivery attempt, or a crash between the two
#      leaves a granted run nothing local can ever speak for again. The stub
#      copies the meta at the instant it is invoked, so the ordering is
#      observed rather than assumed;
#   3. a failed resume falls back to a FRESH SPAWN on the same successor
#      bearer (a successor is a fresh run by contract — the session resume is
#      an optimization), and that bootstrap directs the worker to read its own
#      timeline, where the park/answer history the claim body cannot carry
#      lives;
#   3b. a resume that forked but never resolved a session uuid is AMBIGUOUS,
#      not failed — no fresh spawn, no cycle charged;
#   4. three failed cycles escalate: an env-issue ticket registered as
#      automation plus a suppression record. Automation has NO transition
#      authority in API mode, so the stuck ticket is never parked — the test
#      pins that no transition is ever attempted. An escalation that cannot
#      read the ticket's state does not happen at all: a record holding
#      `"state": ""` would self-lift on the next tick and spam the human;
#   5. a standing suppression skips the ticket in phase 3 and lifts when the
#      board state moved OR the env-issue closed — both halves pinned.
#
# DISPATCH pins the hand-off: phase 4 runs the real implement/review
# dispatchers in their API claim modes, and the suppression directory phase 3
# WRITES is the one phase 4 hands them — a claim that yields a suppressed
# ticket is released and its lane stands down.
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

TDIR="$(mktemp -d)"
trap 'rm -rf "$TDIR"' EXIT
CREDS="$TDIR/creds.env"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
NEWUUID="deadbeef-0000-4000-8000-00000000cafe"

# ---- the wire ---------------------------------------------------------------
# Fixtures are consumed in the order the eight invocations below make their
# calls; `once` entries are the script, the trailing defaults are the
# background. Ordering note: the mock matches on path PREFIX, so every
# /runs/claim-successor entry must precede the /runs/claim default.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":44,"ticketId":12,"fence":4,"bearer":"tok-s","predecessorRun":41,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":121,"ticketId":12,"correlationId":"evt-9","replies":["go"]}]},
 {"method":"POST","path":"/answers/121/ack","status":200,"body":{"acked":true}},
 {"method":"POST","path":"/runs/44/bind","status":200,"body":{"bound":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":44}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":43,"ticketId":12,"fence":5,"bearer":"tok-t","predecessorRun":44,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/43/bind","status":200,"body":{"bound":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":43}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":49,"ticketId":12,"fence":9,"bearer":"tok-amb","predecessorRun":43,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":49}]},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":49}]},
 {"method":"POST","path":"/runs/49/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":45,"ticketId":12,"fence":5,"bearer":"tok-s2","predecessorRun":49,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"the assignment text a successor cannot reach any other way"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/45/bind","status":200,"body":{"bound":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":45}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":46,"ticketId":12,"fence":6,"bearer":"tok-s3","predecessorRun":45,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":122,"ticketId":12,"correlationId":"evt-10","replies":["are you there"]}]},
 {"method":"POST","path":"/runs/46/end","status":200,"body":{"ended":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":46}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":47,"ticketId":12,"fence":7,"bearer":"tok-s4","predecessorRun":46,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/47/end","status":200,"body":{"ended":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":47}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":48,"ticketId":12,"fence":8,"bearer":"tok-s5","predecessorRun":47,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/48/end","status":200,"body":{"ended":true}},
 {"method":"GET","path":"/tickets","status":200,"once":true,
  "body":[{"id":13,"state":"in-progress","priority":"P2","title":"a listing #12 has fallen out of"}]},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":48}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":50,"ticketId":12,"fence":9,"bearer":"tok-s6","predecessorRun":48,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/50/end","status":200,"body":{"ended":true}},
 {"method":"GET","path":"/tickets","status":200,"once":true,
  "body":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}]},
 {"method":"POST","path":"/tickets","status":200,"once":true,
  "body":{"id":90,"state":"needs-human"}},

 {"method":"GET","path":"/tickets","status":200,"once":true,
  "body":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
          {"id":90,"state":"needs-human","priority":null,"title":"stuck resume"}]},
 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":50}]},

 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":60,"ticketId":14,"fence":1,"bearer":"tok-x",
          "body":"a ticket the sweep already gave up on"}},
 {"method":"POST","path":"/runs/60/end","status":200,"body":{"ended":true}},

 {"method":"GET","path":"/tickets","status":200,
  "body":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
          {"id":13,"state":"done","priority":"P2","title":"the moved one"},
          {"id":90,"state":"done","priority":null,"title":"stuck resume"},
          {"id":91,"state":"needs-human","priority":null,"title":"stuck resume 2"}]},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"

# A `gh` stub earlier on PATH than any real gh: neither the api tick nor the
# api dispatchers it hands off to may reach it.
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
TESTHOME="$TDIR/home"; PROJ="$TESTHOME/.claude/projects/-tmp-consumer"
mkdir -p "$PROJ"
TRANSCRIPT="$PROJ/u-old.jsonl"; : > "$TRANSCRIPT"

# The predecessor: bound to #12, holding the run the server has since reaped.
printf '%s\n' '{"uuid":"u-old","current":"u-old","status":"working","run_id":41,
 "fence":3,"lane":"implementer","role":"IMPLEMENT","bind_confirmed":true,"ticket":"12"}' \
 > "$DH/u-old.json"
chmod 600 "$DH/u-old.json"

RESUME_LOG="$TDIR/resume.log"; : > "$RESUME_LOG"
SPAWN_LOG="$TDIR/spawn.log"; : > "$SPAWN_LOG"
# The resume stub COPIES THE REGISTRY META at the instant it runs. That copy is
# the only way to observe persist-before-resume: after the fact every ordering
# looks the same.
cat > "$DS/daemon-resume.sh" <<EOF
#!/usr/bin/env bash
cp "$DH/u-old.json" "$DH/meta-at-resume.json" 2>/dev/null || true
env | grep '^BOARD_' | sort > "$DH/resume-env.txt" || true
{ echo "RESUME uuid=\$1"
  echo "ARGV: \$*"
  echo "DAEMON_TIMEOUT=\${DAEMON_TIMEOUT:-unset}"; } >> "$RESUME_LOG"
# The residual double-spawn shape: the real daemon-resume LAUNCHED a fork but
# _poll_uuid never yielded a usable session uuid, so it stamps status=error +
# pending_short and exits 1 WITHOUT advancing \`current\`. The fork may well be
# alive on the run — nothing local can name its session yet.
if [ -n "\${RESUME_PENDING_SHORT:-}" ]; then
  python3 -c 'import json, sys
m = json.load(open(sys.argv[1]))
m["status"] = "error"; m["pending_short"] = sys.argv[2]
json.dump(m, open(sys.argv[1], "w"), indent=2)' "$DH/u-old.json" "\$RESUME_PENDING_SHORT"
  exit 1
fi
[ -n "\${RESUME_MUST_FAIL:-}" ] && exit 1
# A REAL transcript line: the delivery proof reads user-role JSONL entries whose
# content is a plain string (a delivered prompt), never the raw bytes.
T_P="$TRANSCRIPT" T_C="\$2" python3 - <<'PYX'
import json, os
with open(os.environ["T_P"], "a") as f:
    f.write(json.dumps({"type": "user",
                        "message": {"role": "user", "content": os.environ["T_C"]}}) + "\n")
PYX
# The real daemon-resume forks the turn and INJECTS the prompt before it
# blocks, then exits 1 when its watcher bound expires. That is what a slow
# (i.e. ordinary) successor turn looks like from here.
[ -n "\${RESUME_WAIT_EXPIRES:-}" ] && exit 1
exit 0
EOF
chmod +x "$DS/daemon-resume.sh"
cat > "$DS/daemon-spawn.sh" <<EOF
#!/usr/bin/env bash
shift                      # --no-wait
{ echo "SPAWN name=\$1 cwd=\$3 worktree=\$4 model=\$5"
  echo "ARGV: \$*"
  env | grep '^BOARD_' | sort || true
  echo "---- prompt ----"; printf '%s\n' "\$2"; echo "---- end prompt ----"; } >> "$SPAWN_LOG"
[ -n "\${SPAWN_MUST_FAIL:-}" ] && exit 1
python3 -c 'import json, sys
json.dump({"uuid": sys.argv[2], "current": sys.argv[2], "status": "working",
           "name": sys.argv[3]}, open(sys.argv[1], "w"))' \
  "$DH/$NEWUUID.json" "$NEWUUID" "\$1"
echo "daemon spawned (no-wait): \$1  [abc1234 / $NEWUUID]  status=working  (reply: daemon-reply.sh abc1234)"
EOF
chmod +x "$DS/daemon-spawn.sh"
# Liveness as daemon-finalize actually reports it: `noop` for an ALREADY-
# TERMINAL meta (it never re-inspects one), `live` for a running turn. Driven
# off the meta the way the real script is, so a status the resume path writes —
# notably the status=error + pending_short an unresolved fork leaves — is
# visible to the sweep's own liveness read.
cat > "$DS/daemon-finalize.sh" <<EOF
#!/usr/bin/env bash
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
cat > "$DS/daemon-retire.sh" <<'EOF'
#!/usr/bin/env bash
echo "retire $*"
EOF
chmod +x "$DS/daemon-retire.sh"

SW() {  # SW <phase> — one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" "$@" )
}

# =========================================================================
# Phase 3, rung 1 — a successor claim, the predecessor session resumed on it,
# the ticket's unrelayed answers folded into that one delivery.
# =========================================================================
OUT1="$TDIR/resume1.out"
SW resume > "$OUT1" 2>&1 || true

t  "successor claimed for the feed entry"  "/runs/claim-successor"     cat "$FIX.log"
t  "the claim names the ticket"            '\"ticketId\": 12'          cat "$FIX.log"
t  "the claim speaks automation"           '"auth": "Bearer a"'        cat "$FIX.log"
t  "folded answer delivered with sentinel" "[board-relay answer:121]"  cat "$TRANSCRIPT"
t  "with the reply verbatim"               "go"                        cat "$TRANSCRIPT"
t  "the successor is told to read its own timeline" "board-show.sh 12" cat "$TRANSCRIPT"
t  "folded answer acked"                   "/answers/121/ack"          cat "$FIX.log"
t  "successor bound"                       "/runs/44/bind"             cat "$FIX.log"
t  "the resume names the predecessor session" "RESUME uuid=u-old"      cat "$RESUME_LOG"

# Persist-before-resume: the meta copied AT the resume already names the
# successor run, and says the bind has not landed yet.
t  "registry persisted before resume"      '"run_id": 44'              cat "$DH/meta-at-resume.json"
t  "with the successor fence"              '"fence": 4'                cat "$DH/meta-at-resume.json"
t  "and the bind still unconfirmed"        '"bind_confirmed": false'   cat "$DH/meta-at-resume.json"
bearer_at_rest() { python3 -c 'import json, sys
print("run_bearer=%s" % (json.load(open(sys.argv[1])).get("run_bearer") or "none"))' "$1"; }
t  "and the successor bearer at rest"      "run_bearer=tok-s" bearer_at_rest "$DH/meta-at-resume.json"
meta_mode() { python3 -c 'import os, sys; print("mode=%o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$1"; }
t  "the bearer meta stays 0600"            "mode=600" meta_mode "$DH/u-old.json"

# daemon-resume forks a fresh process from the CALLER's env, so the successor
# credentials ride the invocation or the worker writes nothing.
t  "successor creds on resume env"         "BOARD_RUN_TOKEN=tok-s"     cat "$DH/resume-env.txt"
t  "with the successor run id"             "BOARD_RUN_ID=44"           cat "$DH/resume-env.txt"
t  "and its fence"                         "BOARD_RUN_FENCE=4"         cat "$DH/resume-env.txt"
argv_only() { grep '^ARGV:' "$RESUME_LOG"; }
nt "the bearer never rides on argv"        "tok-s"                     argv_only
# The whole tick holds the lock while this resume blocks — an unbounded wait
# would starve lease renewal past the 15-minute lease, exactly as in phase 2.
t  "the successor resume wait is bounded"  "DAEMON_TIMEOUT=300"        cat "$RESUME_LOG"
journal() { cat "$DH"/board-claims/*.json 2>/dev/null || echo "no journal"; }
t  "the successor claim is journalled"     '"ticket": "12"'            journal
t  "under a lane neither dispatcher owns"  '"lane": "successor"'       journal
t  "and marked handed off"                 '"spawn_completed": true'   journal
nt "the api tick never invokes gh"         "GH-CALLED"                 cat "$MARKER"

# =========================================================================
# Phase 3, rung 2 — A BOUNDED WAIT IS NOT A FAILED DELIVERY. daemon-resume
# forks the turn and injects the prompt BEFORE it blocks, then exits 1 when
# its watcher bound expires — and a successor turn routinely runs longer than
# the bound this tick needs in order not to starve lease renewal, so this is
# the ORDINARY outcome, not a corner. Reading it as failure would fresh-spawn
# a second worker onto a run the first one is actively holding.
# =========================================================================
: > "$FIX.log"
# Truncated HERE, not relied on being pristine: the no-second-worker assert
# below is only meaningful against a log this rung alone could have written,
# and a rung added ahead of it later would otherwise silently defang it.
: > "$SPAWN_LOG"
OUTW="$TDIR/resume-wait.out"
RESUME_WAIT_EXPIRES=1 SW resume > "$OUTW" 2>&1 || true
t  "an expired wait whose delivery landed is not a failure" \
   "the resume wait expired but the delivery landed"        cat "$OUTW"
nt "so no second worker is spawned onto the live run"       "SPAWN"  cat "$SPAWN_LOG"
t  "and the successor is bound as delivered"                "/runs/43/bind" cat "$FIX.log"
nt "and no recovery cycle is charged"                       "recovery cycle" cat "$OUTW"

# =========================================================================
# Phase 3, rung 2b — AN AMBIGUOUS FORK IS NOT A FAILED DELIVERY EITHER.
# daemon-resume can launch the fork and still exit 1 when the new session uuid
# never resolves: it stamps status=error + pending_short and deliberately keeps
# `current` on the OLD turn. The marker check then reads the predecessor's
# transcript, finds nothing, and — before this guard — fresh-spawned a SECOND
# worker onto a run a live fork may already be holding. The delivery is
# unknown, so this tick does nothing and charges nothing; the next tick's
# marker/current resolution settles it.
# =========================================================================
: > "$FIX.log"
: > "$SPAWN_LOG"
OUTA="$TDIR/resume-ambiguous.out"
RESUME_PENDING_SHORT=amb01 SW resume > "$OUTA" 2>&1 || true
t  "an unresolved fork is reported as ambiguous" "delivery is AMBIGUOUS"  cat "$OUTA"
nt "and no second worker is spawned onto the held run" "SPAWN" cat "$SPAWN_LOG"
nt "no recovery cycle is charged for an unknown delivery" "recovery cycle" cat "$OUTA"
nt "and the successor run is not released out from under the fork" \
   '"path": "/runs/49/end"'                                 cat "$FIX.log"

# =========================================================================
# Phase 3, rung 2c — AND THE NEXT TICK MUST NOT RE-FORK IT. `current` still
# names the superseded turn, so every transcript read lands on the old one:
# resuming again forks a SECOND zombie turn onto the same run, and the tick
# before this guard did exactly that on every pass — a fresh unresolved fork
# and a fresh successor claim per tick, forever. The ticket is skipped before
# any successor is claimed, nothing is released out from under the possibly
# live fork, and no cycle is charged (nothing was attempted).
# =========================================================================
: > "$FIX.log"
: > "$SPAWN_LOG"
before_2c="$(wc -l < "$RESUME_LOG")"
OUT2C="$TDIR/resume-fork-guard.out"
SW resume > "$OUT2C" 2>&1 || true
after_2c="$(wc -l < "$RESUME_LOG")"
resumes_2c() { echo "delta=$((after_2c - before_2c))"; }
t  "an unresolved fork blocks the next recovery" "UNRESOLVED FORK"   cat "$OUT2C"
nt "no second successor is claimed for it"  "/runs/claim-successor"  cat "$FIX.log"
t  "and the stranded successor journal is held, not released" \
   "HELD"                                                            cat "$OUT2C"
nt "so its run is not ended under the fork"  '"path": "/runs/49/end"' cat "$FIX.log"
t  "the session is not resumed again"       "delta=0"                resumes_2c
nt "and no second worker is spawned"        "SPAWN"                  cat "$SPAWN_LOG"
nt "no recovery cycle is charged"           "recovery cycle"         cat "$OUT2C"

# The operator (or the fork resolving itself) clears it: status back off `error`
# is what "resolved" means to daemon-resume and therefore to the sweep.
python3 -c 'import json, sys
m = json.load(open(sys.argv[1])); m["status"] = "working"; m.pop("pending_short", None)
json.dump(m, open(sys.argv[1], "w"), indent=2)' "$DH/u-old.json"

# =========================================================================
# Phase 3, rung 3 — the resume fails with NOTHING delivered; the SAME
# successor run is delivered by a fresh spawn instead. The session resume was
# the optimization, not the substance.
# =========================================================================
: > "$FIX.log"
OUT2="$TDIR/resume2.out"
RESUME_MUST_FAIL=1 SW resume > "$OUT2" 2>&1 || true

t  "a failed resume falls back to a fresh spawn" "SPAWN name=12-successor" cat "$SPAWN_LOG"
t  "the fresh spawn rides the same successor bearer" "BOARD_RUN_TOKEN=tok-s2" cat "$SPAWN_LOG"
t  "with the successor run id"             "BOARD_RUN_ID=45"           cat "$SPAWN_LOG"
t  "the fresh worker is told to read its timeline first" "Read your own ticket timeline" cat "$SPAWN_LOG"
# The claim body is by contract the only route a run has to its own ticket
# text; a fresh session has never seen it.
t  "the assignment rides the fresh bootstrap" \
   "the assignment text a successor cannot reach any other way" cat "$SPAWN_LOG"
# The fold was EMPTY this pass. An empty id column ahead of multi-line text is
# exactly the field collapse the 0x1f row layout exists to avoid — here it
# would forge an answers block out of nothing.
nt "an empty fold adds no answers block"   "answers relayed with this resume" cat "$SPAWN_LOG"
t  "the fresh worker is bound to the ticket" "/runs/45/bind"           cat "$FIX.log"
new_bearer() { bearer_at_rest "$DH/$NEWUUID.json"; }
t  "and its bearer lands at rest for the next relay" "run_bearer=tok-s2" new_bearer
nt "a delivered cycle ends no run"         '"path": "/runs/45/end"'    cat "$FIX.log"

# =========================================================================
# Phase 3, rung 4 — cycles where NEITHER vehicle delivers. The failed
# successor run is released each time (it must not squat the ticket), nothing
# is acked, and the third cycle escalates — unless the board cannot name the
# state it is freezing, in which case the escalation waits for a cycle that
# can (the empty-read rung below).
# =========================================================================
: > "$FIX.log"
OUT3="$TDIR/resume3.out"
RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 SW resume > "$OUT3" 2>&1 || true
t  "cycle 1 is counted"                    "recovery cycle 1 of 3"     cat "$OUT3"
t  "the undeliverable successor run is released" '"path": "/runs/46/end"' cat "$FIX.log"
t  "released as abandoned"                 '\"reason\": \"abandoned\"' cat "$FIX.log"
nt "a failed delivery acks nothing"        "/answers/122/ack"          cat "$FIX.log"
nt "and escalates nothing yet"             "env-issue"                 cat "$OUT3"

OUT4="$TDIR/resume4.out"
RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 SW resume > "$OUT4" 2>&1 || true
t  "cycle 2 is counted"                    "recovery cycle 2 of 3"     cat "$OUT4"
nt "and still escalates nothing"           "env-issue"                 cat "$OUT4"

# Cycle 3 reaches the escalation, but the board answers with a listing this
# ticket has fallen out of. A record written from that empty read would say
# `"state": ""`, and the lift check — moved = current != recorded — then reads
# ANY value as movement, so the suppression would lift on the very next tick
# and the whole ladder would run again, spamming the human an env-issue every
# three cycles. An escalation that cannot name the state it froze does not
# happen at all; the counter stands and the next tick retries.
: > "$FIX.log"
OUT4B="$TDIR/resume4b.out"
RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 SW resume > "$OUT4B" 2>&1 || true
t  "cycle 3 is counted"                    "recovery cycle 3 of 3"     cat "$OUT4B"
t  "an escalation whose board state reads empty is refused" \
   "board state came back empty"                                       cat "$OUT4B"
nt "it registers no env-issue"             '\"category\": \"env-issue\"' cat "$FIX.log"
suppression_for() { cat "$DH/board-suppress/$1.json" 2>/dev/null || echo "no suppression record"; }
t  "and writes no suppression record"      "no suppression record"     suppression_for 12

: > "$FIX.log"
OUT5="$TDIR/resume5.out"
RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 SW resume > "$OUT5" 2>&1 || true
t  "escalation registers env-issue"        '\"category\": \"env-issue\"' cat "$FIX.log"
t  "the env-issue names the stuck ticket"  '#12'                       cat "$FIX.log"
t  "registered as automation"              '"auth": "Bearer a"'        cat "$FIX.log"
t  "the escalation is reported"            "escalated #12 → env-issue #90 (suppressed)" cat "$OUT5"
t  "suppression file written"              '"ticket": 12'              cat "$DH/board-suppress/12.json"
t  "recording the board state it was stuck in" '"state": "in-progress"' cat "$DH/board-suppress/12.json"
t  "and the env-issue that lifts it"       '"env_issue": 90'           cat "$DH/board-suppress/12.json"
# Automation holds no transition authority in API mode (the matrix admits
# humans and runs only) — the env-issue IS the park, and the ticket is left
# exactly where it was.
nt "automation never transitions the stuck ticket" "/transition"       cat "$FIX.log"

# =========================================================================
# Phase 3, rung 5a — a standing suppression skips the ticket entirely.
# =========================================================================
: > "$FIX.log"
OUT6="$TDIR/resume6.out"
SW resume > "$OUT6" 2>&1 || true
t  "suppressed ticket skipped"             "suppressed — skipping #12" cat "$OUT6"
nt "and no successor is claimed for it"    "/runs/claim-successor"     cat "$FIX.log"

# =========================================================================
# Phase 4 — the hand-off. The real dispatchers claim; the suppression
# directory phase 3 wrote is the one they read, so a claim that yields a
# suppressed ticket is released and that lane stands down.
# =========================================================================
: > "$FIX.log"
mkdir -p "$DH/board-suppress"
printf '%s\n' '{"ticket": 14, "state": "in-progress", "env_issue": 92}' \
  > "$DH/board-suppress/14.json"
OUT7="$TDIR/dispatch.out"
SW dispatch > "$OUT7" 2>&1 || true
t  "phase 4 claims the architect lane"     '\"lane\": \"architect\"'   cat "$FIX.log"
t  "phase 4 claims the implementer lane"   '\"lane\": \"implementer\"' cat "$FIX.log"
t  "phase 4 claims the qagent lane"        '\"lane\": \"qagent\"'      cat "$FIX.log"
nt "and nobody claims the ops lane"        '\"lane\": \"ops\"'         cat "$FIX.log"
t  "a claim yielding a suppressed ticket is released" \
   "#14 is suppressed — releasing run 60"  cat "$OUT7"
t  "and that run is ended"                 '"path": "/runs/60/end"'    cat "$FIX.log"
nt "phase 4 never invokes gh"              "GH-CALLED"                 cat "$MARKER"
rm -f "$DH/board-suppress/14.json"

# =========================================================================
# Phase 3, rung 5b — suppression lifts on EITHER trigger, both checked each
# tick: #12's env-issue closed, #13's own board state moved.
# =========================================================================
printf '%s\n' '{"ticket": 13, "state": "in-progress", "env_issue": 91}' \
  > "$DH/board-suppress/13.json"
: > "$FIX.log"
OUT8="$TDIR/resume7.out"
SW resume > "$OUT8" 2>&1 || true
t  "suppression lifts on env-issue close"  "suppression lifted for #12" cat "$OUT8"
t  "suppression lifts when the ticket moved" "suppression lifted for #13" cat "$OUT8"
lifted() { ls "$DH/board-suppress"/*.json 2>/dev/null || echo "no suppression records"; }
t  "and the records are gone"              "no suppression records"    lifted

# =========================================================================
# A held lock skips phases 3+4 too — the successor claim and its delivery
# must not interleave with another tick's.
# =========================================================================
: > "$FIX.log"
mkdir "$DH/.sweep-api.lock"
t  "a held lock skips the tick"  "holds the lock"  SW resume
nt "and sends nothing"           '"method"'        cat "$FIX.log"
rmdir "$DH/.sweep-api.lock"

finish
