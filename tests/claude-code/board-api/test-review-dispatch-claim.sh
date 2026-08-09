#!/usr/bin/env bash
# test-review-dispatch-claim.sh — review-dispatch.sh's API branch: the qagent
# lane claimed off the board, the crash-recoverable claim journal, and the
# review worker's handover (spawn env, startup barrier, bind, lane stamp).
#
# Same two halves as the implement-side suite: what went on the wire (the
# fixture mock's request log) and what landed on disk (journal, assignment
# body, registry meta, the environment the worker was spawned with). The
# daemon-spawn stub prints the REAL --no-wait banner (the uuid handed to
# board-bind is parsed out of it) and plays the worker's half of the startup
# barrier, which the review protocol makes a hard gate.
. "$(dirname "$0")/helpers.sh"

DISPATCH="$REPO_ROOT/skills/reviewing-prs/scripts/review-dispatch.sh"

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

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"

# A `gh` stub earlier on PATH than any real gh: API-mode dispatch must never
# reach it — review-dispatch resolves BOARD_REPO and the default branch through
# gh in its gh-mode preamble, so the binding has to be decided ahead of both.
STUB="$(mktemp -d)"; MARKER="$STUB/gh-invoked"; : > "$MARKER"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH-CALLED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

# The daemon-spawn stub: registers a meta the way the real --no-wait spawn
# does, records the worker environment, and — in the background, as the real
# worker does — waits for the dispatcher-owned ready file and acknowledges it.
DS="$(mktemp -d)"
cat > "$DS/daemon-spawn.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"; wt="${4:-}"; model="${5:-}"
{ echo "ARGS name=$name cwd=$cwd worktree=$wt model=$model"
  env | grep '^BOARD_' | sort || true
  echo "GW settings=[${DAEMON_CLAUDE_SETTINGS-unset}] effort=[${DAEMON_CLAUDE_EFFORT-unset}]"
} >> "$DAEMON_HOME/spawn-capture.txt"
printf '%s' "$task" > "$DAEMON_HOME/prompt-$name.md"
n=$(cat "$DAEMON_HOME/.spawncount" 2>/dev/null || echo 0); n=$((n + 1))
echo "$n" > "$DAEMON_HOME/.spawncount"
uuid="$(printf 'bbbb%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "status": "working",
           "updated": "2026-08-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
# The worker's first protocol action is the BINDING BARRIER: wait for the
# dispatcher-owned ready file, check it names this worker, acknowledge. The
# dispatcher does not report success until that ack exists.
bind_ready="$(printf '%s\n' "$task" | grep '^- `BIND_READY_FILE`:' | cut -d' ' -f3- || true)"
wname="$(printf '%s\n' "$task" | sed -n 's/^- `WORKER_NAME`: \([^ ][^ ]*\).*/\1/p' | head -1)"
[ "$wname" = "$name" ] || bind_ready=""
if [ -n "$bind_ready" ]; then
  READY="$bind_ready" UUID="$uuid" python3 - <<'PY' >/dev/null 2>&1 &
import json, os, time
ready = os.environ["READY"]
for _ in range(500):
    if os.path.isfile(ready):
        ack = ready + ".ack"; tmp = ack + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"uuid": os.environ["UUID"]}, f)
        os.replace(tmp, ack)
        break
    time.sleep(0.01)
PY
fi
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working  (reply: daemon-reply.sh ${uuid%%-*})"
EOF
cat > "$DS/daemon-retire.sh" <<'EOF'
#!/usr/bin/env bash
echo "retire $*" >> "$DAEMON_HOME/spawn-capture.txt"
EOF
cat > "$DS/daemon-finalize.sh" <<'EOF'
#!/usr/bin/env bash
echo noop
EOF
chmod +x "$DS/daemon-spawn.sh" "$DS/daemon-retire.sh" "$DS/daemon-finalize.sh"

apirepo() {  # apirepo <port> — a fresh checkout bound to the mock on <port>
  local d; d="$(mkrepo)"; mkdir -p "$d/.doperpowers"
  printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$1" > "$d/.doperpowers/board.json"
  echo "$d"
}

# =========================================================================
# Scenario 1 — a fresh tick: one qagent claim granted, then the lane answers
# empty and the tick stops.
# =========================================================================
PORT="$(free_port)"
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":51,"ticketId":9,"fence":2,"bearer":"tok-q","plan":null,
          "body":"review it","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/51/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
PORT2="$(free_port)"
FIX2="$(mktemp)"; : > "$FIX2.log"
cat > "$FIX2" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":55,"ticketId":21,"fence":1,"bearer":"tok-r","plan":null,
          "body":"replayed review","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/55/bind","status":200,"body":{"bound":true}},
 {"method":"POST","path":"/runs/99/end","status":200,"body":{"ended":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX2" "$PORT2" & MOCK2=$!
trap 'kill $MOCK $MOCK2 2>/dev/null' EXIT
wait_for_port "$PORT"  || { echo "FAIL mock server never listened on $PORT"; exit 1; }
wait_for_port "$PORT2" || { echo "FAIL mock server never listened on $PORT2"; exit 1; }

r="$(apirepo "$PORT")"
DH="$(mktemp -d)"   # pinned: a fall-through would read the operator's registry
OUT="$(mktemp)"
( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    DAEMON_CLAUDE_SETTINGS="$STUB/ambient-gateway.json" \
    "$DISPATCH" --sweep ) > "$OUT" 2>&1 || true

t "the granted claim is reported" "claimed #9 run=51 lane=qagent" cat "$OUT"
nt "api review dispatch never invokes gh" "GH-CALLED" cat "$MARKER"

# --- the worker's environment: the run credentials it cannot review without -
t "worker got the run bearer" "BOARD_RUN_TOKEN=tok-q"                cat "$DH/spawn-capture.txt"
t "worker got the run id"     "BOARD_RUN_ID=51"                      cat "$DH/spawn-capture.txt"
t "fence exported"            "BOARD_RUN_FENCE=2"                    cat "$DH/spawn-capture.txt"
t "api url exported"          "BOARD_API_URL=http://127.0.0.1:$PORT" cat "$DH/spawn-capture.txt"
# An ambient gateway settings file would be inherited by daemon-spawn AND
# persisted into the meta, so every later resume of this reviewer would ride
# the gateway while the log said claude. The QAgent tier is opus/high.
t "gateway settings cleared, review effort pinned" "GW settings=[] effort=[high]" \
  cat "$DH/spawn-capture.txt"
t "the reviewer runs in its own worktree off the repo" \
  "ARGS name=9-api-qagent cwd=$r worktree=9-api-qagent model=opus" cat "$DH/spawn-capture.txt"

# --- the claim journal: the crash-recovery record --------------------------
t "claim journal marks the spawn complete" '"spawn_completed": true' \
  bash -c "cat '$DH'/board-claims/*.json"
t "claim journal carries the run id"       '"run_id": 51' \
  bash -c "cat '$DH'/board-claims/*.json"
t "claim journal carries the lane"         '"lane": "qagent"' \
  bash -c "cat '$DH'/board-claims/*.json"
t "assignment body written beside it"      "review it" \
  bash -c "cat '$DH'/board-claims/*.body.md"
# The journal filename IS the nonce that went on the wire — that identity is
# the whole reconciliation mechanism, so pin it rather than assume it.
nonce_on_wire() {
  grep '"path": "/runs/claim"' "$FIX.log" | head -1 |
    python3 -c 'import json, sys; print(json.loads(json.loads(sys.stdin.read())["body"])["dispatchNonce"])'
}
NONCE="$(nonce_on_wire || true)"
t "the journal is filed under the nonce that went on the wire" "journal=yes" \
  bash -c "[ -f '$DH/board-claims/$NONCE.json' ] && echo journal=yes || echo journal=no"

# --- the wire: lane discipline and the server-side belt --------------------
t "the claim names the qagent lane"      '\"lane\": \"qagent\"' cat "$FIX.log"
t "the local cap rides along as laneCap" '\"laneCap\": 2'       cat "$FIX.log"
nt "no other lane is claimed from here"  '\"lane\": \"implementer\"' cat "$FIX.log"
claim_posts() { echo "claims=$(grep -c '"path": "/runs/claim"' "$FIX.log")"; }
t "an empty lane stops the tick" "claims=2" claim_posts
t "the claim speaks as automation" '"auth": "Bearer a"' cat "$FIX.log"

# --- the handover: bind, barrier, and the local half of a later resume -----
t "the run is bound to its session" '"path": "/runs/51/bind"' cat "$FIX.log"
meta() { cat "$DH"/bbbb0001-*.json; }
t "the meta records the lane"   '"lane": "qagent"' meta
t "the meta records the nonce"  '"nonce"'          meta
t "the meta records the role"   '"role": "QAGENT"' meta
t "the meta records the ticket" '"ticket": "9"'    meta
# Without the bearer at rest every later relay/resume of this reviewer has no
# token to speak with — the sweep reads it back out of exactly this field.
t "the bearer is stored at rest" '"run_bearer": "tok-q"' meta
barrier() {
  local f; f="$(find "$DH" -name bind-ready.json -type f -print | head -1)"
  [ -n "$f" ] || { echo "no-barrier"; return; }
  [ -f "$f.ack" ] && echo "barrier=published ack=yes" || echo "barrier=published ack=no"
}
t "the startup barrier opened and the worker acknowledged it" \
  "barrier=published ack=yes" barrier

# --- the prompt the reviewer actually woke up with -------------------------
prompt() { cat "$DH/prompt-9-api-qagent.md"; }
t  "the reviewer is told it is the qagent lane on its ticket" \
   "ticket #9" prompt
t  "the api review mode is the one rendered"     '`REVIEW_MODE`: api' prompt
t  "the assignment file is pinned in the prompt" "$DH/board-claims/" prompt
t  "the board scripts, not gh, are the board"    "board-show.sh 9"   prompt
t  "the barrier file is bound"                   '`BIND_READY_FILE`: ' prompt
nt "no PR framing reaches an api reviewer"       "You are a REVIEW worker for PR" prompt
nt "no scale framing either"                     "SCALE REVIEWER"     prompt
nt "nothing was left unrendered"                 "{{"                 prompt

# --- the triggered form: gh-only, and it says so ---------------------------
triggered() {
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$DISPATCH" 5 )
}
t "a targeted dispatch fails loud naming the gap" "arkho#7" triggered
t "and says what to use instead"                  "--sweep" triggered

# =========================================================================
# Scenario 2 — startup reconciliation, and lane ownership: this dispatcher
# owns the qagent journals and NOTHING else. The implement dispatcher's
# journals share the directory and must be left exactly alone.
# =========================================================================
r2="$(apirepo "$PORT2")"
DH2="$(mktemp -d)"; mkdir -p "$DH2/board-claims"
# (a) nonce persisted, response lost: no run id was ever recorded, so the
#     claim may or may not have landed — replaying the SAME nonce is the one
#     legal replay.
printf '{"lane": "qagent", "run_id": null, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-a.json"
# (b) claimed but never handed off: a run exists, no session ever did.
printf '{"lane": "qagent", "run_id": 99, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-b.json"
printf 'orphaned assignment\n' > "$DH2/board-claims/nonce-b.body.md"
# (c) the spawn DID complete — its worker is right there in the registry —
#     and only the marker write was lost.
printf '{"lane": "qagent", "run_id": 51, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-c.json"
printf '{"uuid":"cccc0001","current":"cccc0001","name":"9-api-qagent","status":"working","run_id":51,"lane":"qagent","ticket":"9"}' \
  > "$DH2/cccc0001.json"
# (d) another dispatcher's journal, mid-handoff. Replaying it here would spawn
#     an IMPLEMENT assignment with a reviewer's prompt; ending it would strand
#     that dispatcher's ticket. Neither is this script's business.
printf '{"lane": "implementer", "run_id": 77, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-d.json"
# (e) THE SPAWN LANDED, THE BIND DID NOT — a crash inside the spawn/ack window,
#     which is many seconds wide and leaves the session detached and running.
#     The run id reaches a meta only via board-bind, so this journal is
#     byte-for-byte the shape of (b) except for the daemon name written before
#     the spawn — and that name is in the registry, alive. Ending this run
#     would kill a live reviewer and hand its ticket to a second one.
printf '{"lane": "qagent", "run_id": 66, "spawn_completed": false, "ticket": "33", "daemon": "33-api-qagent"}\n' \
  > "$DH2/board-claims/nonce-e.json"
printf 'live review assignment\n' > "$DH2/board-claims/nonce-e.body.md"
printf '{"uuid":"dddd0001","current":"dddd0001","name":"33-api-qagent","status":"working"}' \
  > "$DH2/dddd0001.json"
# (f) a journal no reader can parse — a half-written file, or the truncated
#     record a crash mid-write leaves. Skipping it silently hides a claimed run
#     forever, every tick, with nothing on any log to say so.
printf '{"lane": "qagent", "run_id": 88, "spawn_' > "$DH2/board-claims/nonce-f.json"

OUT2="$(mktemp)"
( cd "$r2" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH2" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r2" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT2" 2>&1 || true

t "a lost response is replayed under its own nonce" '\"dispatchNonce\": \"nonce-a\"' cat "$FIX2.log"
t "the replay reaches a run and completes"          '"run_id": 55' cat "$DH2/board-claims/nonce-a.json"
t "the replayed claim is spawned"                   '"spawn_completed": true' cat "$DH2/board-claims/nonce-a.json"
t "a stranded claim ends its run"                   '"path": "/runs/99/end"' cat "$FIX2.log"
t "and ends it as abandoned"                        '\"reason\": \"abandoned\"' cat "$FIX2.log"
gone() { [ -e "$1" ] && echo "still-there" || echo "gone"; }
t "the stranded journal is dropped"       "gone" gone "$DH2/board-claims/nonce-b.json"
t "so is its orphaned assignment body"    "gone" gone "$DH2/board-claims/nonce-b.body.md"
t "a lost marker is repaired, not replayed" '"spawn_completed": true' cat "$DH2/board-claims/nonce-c.json"
t "another lane's journal is left untouched" '"run_id": 77, "spawn_completed": false' \
  cat "$DH2/board-claims/nonce-d.json"
# --- (e) a spawned-but-unbound run is never ended --------------------------
nt "a live unbound run is NOT ended" '"path": "/runs/66/end"' cat "$FIX2.log"
t  "its journal is kept, closed to replay" '"spawn_completed": true' \
  cat "$DH2/board-claims/nonce-e.json"
t  "and the orphaned session is reported by name" "33-api-qagent" cat "$OUT2"
t  "the report says the run was not ended"        "is NOT being ended" cat "$OUT2"
# The ticket must not reach a second reviewer: no end means the server lease
# still holds #33, and reconcile itself spawns nothing for it.
nt "the ticket is not re-dispatched" "name=33-api-qagent" cat "$DH2/spawn-capture.txt"
# --- (f) a corrupt journal is loud, not invisible ---------------------------
t "an unparseable journal is reported" "unreadable json at" cat "$OUT2"
t "it names the file"                  "nonce-f.json"       cat "$OUT2"
t "and is left on disk for repair"     "still-there" gone "$DH2/board-claims/nonce-f.json"
# Everything this tick was allowed to send, counted: the replayed claim, its
# bind, and the stranded run's end. Nothing more — the reconciled worker plus
# the replayed one fill the cap of 2, so the fresh-claim loop never opens. A
# repaired marker sends nothing (no end for its live run 51), and no foreign
# lane appears on the wire at all.
wire_summary() {
  printf 'posts=%s ends51=%s ends77=%s foreign=%s\n' \
    "$(grep -c '"method"' "$FIX2.log" || true)" \
    "$(grep -c '/runs/51/end' "$FIX2.log" || true)" \
    "$(grep -c '/runs/77/end' "$FIX2.log" || true)" \
    "$(grep -cF '\"lane\": \"implementer\"' "$FIX2.log" || true)"
}
t "reconcile sends only what it must" "posts=3 ends51=0 ends77=0 foreign=0" wire_summary

# =========================================================================
# Scenario 3 — a REGISTRY meta nobody can read. A meta is the only evidence
# that a session exists, so one unreadable meta means no absence of a session
# can be proven anywhere: every end this tick downgrades to a hold and the
# server's lease reclaim — not this dispatcher — resolves the run.
# =========================================================================
PORT3="$(free_port)"
FIX3="$(mktemp)"; : > "$FIX3.log"
cat > "$FIX3" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/99/end","status":200,"body":{"ended":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX3" "$PORT3" & MOCK3=$!
trap 'kill $MOCK $MOCK2 $MOCK3 2>/dev/null' EXIT
wait_for_port "$PORT3" || { echo "FAIL mock server never listened on $PORT3"; exit 1; }

r3="$(apirepo "$PORT3")"
DH3="$(mktemp -d)"; mkdir -p "$DH3/board-claims"
# The same shape as scenario 2's (b) — claimed, no session, nothing to prove it
# alive — which on a readable registry is ended. Here it must NOT be.
printf '{"lane": "qagent", "run_id": 99, "spawn_completed": false}\n' \
  > "$DH3/board-claims/nonce-g.json"
printf 'held review assignment\n' > "$DH3/board-claims/nonce-g.body.md"
printf '{"uuid":"eeee0001","current":"eeee0001","name":"70-api-qage' \
  > "$DH3/eeee0001.json"

OUT3="$(mktemp)"
( cd "$r3" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH3" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r3" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT3" 2>&1 || true

nt "a run is NOT ended while a meta is unreadable" '"path": "/runs/99/end"' cat "$FIX3.log"
t  "the hold is reported"         "holding it"           cat "$OUT3"
t  "and names who owns it"        "server lease reclaim" cat "$OUT3"
t  "the unreadable meta is named" "eeee0001.json"        cat "$OUT3"
t  "the held journal stays on disk, open" '"spawn_completed": false' \
  cat "$DH3/board-claims/nonce-g.json"
t  "and its assignment body is not dropped" "still-there" gone "$DH3/board-claims/nonce-g.body.md"
held_wire() {
  printf 'posts=%s ends=%s\n' \
    "$(grep -c '"method"' "$FIX3.log" || true)" \
    "$(grep -c '/end' "$FIX3.log" || true)"
}
# One empty qagent claim and nothing else.
t "a held run sends nothing" "posts=1 ends=0" held_wire

finish
