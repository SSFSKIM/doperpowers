#!/usr/bin/env bash
# test-dispatch-claim.sh — implement-dispatch.sh's API branch: claim-based
# dispatch, the crash-recoverable claim journal, and the worker handover.
#
# Two halves, both against a real socket: what went on the wire (the fixture
# mock's request log) and what landed on disk (the claim journal, the
# assignment body, the registry meta, the environment the worker was spawned
# with). The daemon-spawn stub prints the REAL --no-wait banner line, because
# the uuid the dispatcher hands to board-bind is parsed out of it.
. "$(dirname "$0")/helpers.sh"

DISPATCH="$REPO_ROOT/skills/implementing/scripts/implement-dispatch.sh"

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
# reach it (that is the whole point of resolving the binding before the gh
# probe). It records into a FILE — a stub that only echoed would be invisible
# to a caller that captures its child's stdout.
STUB="$(mktemp -d)"; MARKER="$STUB/gh-invoked"; : > "$MARKER"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH-CALLED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

# The daemon-spawn stub, shared by both scenarios. It registers a meta the way
# the real --no-wait spawn does (board-bind and the lane stamp both resolve
# the worker through the registry) and echoes the genuine banner format.
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
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working  (reply: daemon-reply.sh ${uuid%%-*})"
EOF
cat > "$DS/daemon-retire.sh" <<'EOF'
#!/usr/bin/env bash
echo "retire $*" >> "$DAEMON_HOME/spawn-capture.txt"
EOF
chmod +x "$DS/daemon-spawn.sh" "$DS/daemon-retire.sh"

apirepo() {  # apirepo <port> — a fresh checkout bound to the mock on <port>
  local d; d="$(mkrepo)"; mkdir -p "$d/.doperpowers"
  printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$1" > "$d/.doperpowers/board.json"
  echo "$d"
}

# =========================================================================
# Scenario 1 — a fresh tick: one architect claim granted, then both implement
# lanes answer empty.
# =========================================================================
PORT="$(free_port)"
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":41,"ticketId":12,"fence":3,"bearer":"tok-w","plan":null,
          "body":"# assignment\nbuild it","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
PORT2="$(free_port)"
FIX2="$(mktemp)"; : > "$FIX2.log"
cat > "$FIX2" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":55,"ticketId":21,"fence":1,"bearer":"tok-r","plan":null,
          "body":"replayed work","parentPin":null}},
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
    BOARD_CREDENTIALS_FILE="$CREDS" IMPLEMENT_MAX_CONCURRENT=5 \
    DAEMON_CLAUDE_SETTINGS="$STUB/ambient-gateway.json" DAEMON_CLAUDE_EFFORT=high \
    "$DISPATCH" --sweep ) > "$OUT" 2>&1 || true

t "the granted claim is reported" "claimed #12 run=41 lane=architect" cat "$OUT"
nt "api dispatch never invokes gh" "GH-CALLED" cat "$MARKER"

# --- the worker's environment: the run credentials it cannot run without ----
t "worker got the run bearer"   "BOARD_RUN_TOKEN=tok-w"                cat "$DH/spawn-capture.txt"
t "worker got the run id"       "BOARD_RUN_ID=41"                      cat "$DH/spawn-capture.txt"
t "fence exported"              "BOARD_RUN_FENCE=3"                    cat "$DH/spawn-capture.txt"
t "api url exported"            "BOARD_API_URL=http://127.0.0.1:$PORT" cat "$DH/spawn-capture.txt"
# Same rule as the gh path's claude route: an ambient gateway settings/effort
# pair would be inherited by daemon-spawn AND persisted into the meta, so every
# later resume of this worker would silently ride the gateway.
t "gateway env cleared for the api route" "GW settings=[] effort=[]" cat "$DH/spawn-capture.txt"
t "architect route pins the architect model" "model=fable"            cat "$DH/spawn-capture.txt"

# --- the claim journal: the crash-recovery record --------------------------
t "claim journal marks the spawn complete" '"spawn_completed": true' \
  bash -c "cat '$DH'/board-claims/*.json"
t "claim journal carries the run id"       '"run_id": 41' \
  bash -c "cat '$DH'/board-claims/*.json"
t "claim journal carries the lane"         '"lane": "architect"' \
  bash -c "cat '$DH'/board-claims/*.json"
t "assignment body written beside it"      "build it" \
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
t "the claim names its lane"        '\"lane\": \"architect\"'    cat "$FIX.log"
t "the local cap rides along as laneCap" '\"laneCap\": 1'        cat "$FIX.log"
t "the implement lane is tried"     '\"lane\": \"implementer\"'  cat "$FIX.log"
t "the spike lane is tried after it" '\"lane\": \"spike\"'       cat "$FIX.log"
# Three claims, not four and not an unbounded spin: architect (granted, then
# the lane is full), implementer (empty), spike (empty) -> stop.
claim_posts() { echo "claims=$(grep -c '"path": "/runs/claim"' "$FIX.log")"; }
t "an empty lane stops the tick" "claims=3" claim_posts
t "the claim speaks as automation" '"auth": "Bearer a"' cat "$FIX.log"

# --- the handover: bind, and the local half a later resume rehydrates from --
t "the run is bound to its session" '"path": "/runs/41/bind"' cat "$FIX.log"
meta() { cat "$DH"/bbbb0001-*.json; }
t "the meta records the lane"   '"lane": "architect"' meta
t "the meta records the nonce"  '"nonce"'             meta
t "the meta records the role"   '"role": "ARCHITECT"' meta
t "the meta records the ticket" '"ticket": "12"'      meta
# Without the bearer at rest every later relay/resume of this worker has no
# token to speak with — the sweep reads it back out of exactly this field.
t "the bearer is stored at rest" '"run_bearer": "tok-w"' meta

# --- the prompt the worker actually woke up with ---------------------------
prompt() { cat "$DH/prompt-12-api-architect.md"; }
t  "the worker is told its role and ticket" "ARCHITECT worker for ticket #12" prompt
t  "the ticket url points at the board api" "http://127.0.0.1:$PORT/tickets/12" prompt
t  "the assignment file is pinned in the prompt" "$DH/board-claims/" prompt
t  "the api block replaces the gh ticket read" "delivered by the claim that dispatched you" prompt
nt "nothing was left unrendered" "{{" prompt

# --- the triggered form: gh-only, and it says so ---------------------------
triggered() {
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
      DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$DISPATCH" 12 )
}
t "a targeted dispatch fails loud naming the gap" "arkho#7" triggered
t "and says what to use instead"                  "--sweep" triggered

# =========================================================================
# Scenario 2 — startup reconciliation. Three journals a crash could leave,
# one of each shape, on a second board.
# =========================================================================
r2="$(apirepo "$PORT2")"
DH2="$(mktemp -d)"; mkdir -p "$DH2/board-claims"
# (a) nonce persisted, response lost: no run_id was ever recorded, so the
#     claim may or may not have landed — replaying the SAME nonce is the one
#     legal replay.
printf '{"lane": "implementer", "run_id": null, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-a.json"
# (b) claimed but never handed off: a run exists, no session ever did.
printf '{"lane": "implementer", "run_id": 99, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-b.json"
printf 'orphaned assignment\n' > "$DH2/board-claims/nonce-b.body.md"
# (c) the spawn DID complete — its worker is right there in the registry —
#     and only the marker write was lost.
printf '{"lane": "architect", "run_id": 41, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-c.json"
printf '{"uuid":"cccc0001","current":"cccc0001","name":"12-api-architect","status":"working","run_id":41,"lane":"architect","ticket":"12"}' \
  > "$DH2/cccc0001.json"
# (d) THE SPAWN LANDED, THE BIND DID NOT — a crash inside daemon-spawn uuid
#     poll window, which is seconds wide and leaves the session detached and
#     running. The run id reaches a meta only via board-bind, so this journal
#     is byte-for-byte the shape of (b) except for the daemon name written
#     before the spawn — and that name is in the registry, alive. Ending this
#     run would kill a live worker and hand its ticket to a second one.
printf '{"lane": "implementer", "run_id": 77, "spawn_completed": false, "ticket": "33", "daemon": "33-api-implementer"}\n' \
  > "$DH2/board-claims/nonce-d.json"
printf 'live assignment\n' > "$DH2/board-claims/nonce-d.body.md"
printf '{"uuid":"dddd0001","current":"dddd0001","name":"33-api-implementer","status":"working"}' \
  > "$DH2/dddd0001.json"
# (e) a journal no reader can parse — a half-written file, or the truncated
#     record a crash mid-write leaves. Skipping it silently hid a claimed run
#     forever, every tick, with nothing on any log to say so.
printf '{"lane": "implementer", "run_id": 88, "spawn_' > "$DH2/board-claims/nonce-e.json"
# (f) THE REVIEW DISPATCHER'S JOURNAL. The claims directory is shared, and every
#     entry names its lane. Replaying a qagent nonce here would hand a review
#     assignment an implementer prompt; ending its run would strand the review
#     dispatcher's ticket. Anything outside architect|implementer|spike is not
#     this script's to touch.
printf '{"lane": "qagent", "run_id": 66, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-f.json"

OUT2="$(mktemp)"
( cd "$r2" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH2" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r2" \
    BOARD_CREDENTIALS_FILE="$CREDS" IMPLEMENT_MAX_CONCURRENT=5 \
    "$DISPATCH" --sweep ) > "$OUT2" 2>&1 || true

t "a lost response is replayed under its own nonce" '\"dispatchNonce\": \"nonce-a\"' cat "$FIX2.log"
t "the replay reaches a run and completes"          '"run_id": 55' cat "$DH2/board-claims/nonce-a.json"
t "the replayed claim is spawned"                   '"spawn_completed": true' cat "$DH2/board-claims/nonce-a.json"
t "a stranded claim ends its run"                   '"path": "/runs/99/end"' cat "$FIX2.log"
t "and ends it as abandoned"                        '\"reason\": \"abandoned\"' cat "$FIX2.log"
gone() { [ -e "$1" ] && echo "still-there" || echo "gone"; }
t "the stranded journal is dropped"      "gone" gone "$DH2/board-claims/nonce-b.json"
t "so is its orphaned assignment body"   "gone" gone "$DH2/board-claims/nonce-b.body.md"
t "a lost marker is repaired, not replayed" '"spawn_completed": true' cat "$DH2/board-claims/nonce-c.json"
# --- (d) a spawned-but-unbound run is never ended --------------------------
nt "a live unbound run is NOT ended" '"path": "/runs/77/end"' cat "$FIX2.log"
t  "its journal is kept, closed to replay" '"spawn_completed": true' \
  cat "$DH2/board-claims/nonce-d.json"
t  "and the orphaned session is reported by name" "33-api-implementer" cat "$OUT2"
t  "the report says the run was not ended"        "is NOT being ended"  cat "$OUT2"
# The ticket must not reach a second worker: no end means the server lease
# still holds #33, and reconcile itself spawns nothing for it.
nt "the ticket is not re-dispatched" "name=33-api-implementer" cat "$DH2/spawn-capture.txt"
# --- (e) a corrupt journal is loud, not invisible ---------------------------
t "an unparseable journal is reported" "unreadable json at" cat "$OUT2"
t "it names the file"                  "nonce-e.json"       cat "$OUT2"
t "and is left on disk for repair"     "still-there" gone "$DH2/board-claims/nonce-e.json"
# --- (f) another dispatcher's lane is not this script's to reconcile --------
nt "a foreign lane's run is never ended" '"path": "/runs/66/end"' cat "$FIX2.log"
t  "a foreign lane's journal is left byte-identical" \
  '{"lane": "qagent", "run_id": 66, "spawn_completed": false}' cat "$DH2/board-claims/nonce-f.json"
nt "and no foreign lane is claimed from here" '\"lane\": \"qagent\"' cat "$FIX2.log"
# Everything this tick was allowed to send, counted: the replayed claim, its
# bind, the stranded run's end, and the two empty implement lanes. A repaired
# marker sends nothing (no end for its live run 41), and the architect lane —
# already full in the registry, by the very meta that proved run 41 live —
# claims nothing on top of it.
ARCH_ON_WIRE='\"lane\": \"architect\"'
wire_summary() {
  printf 'posts=%s ends41=%s arch=%s\n' \
    "$(grep -c '"method"' "$FIX2.log" || true)" \
    "$(grep -c '/runs/41/end' "$FIX2.log" || true)" \
    "$(grep -cF "$ARCH_ON_WIRE" "$FIX2.log" || true)"
}
t "reconcile sends only what it must" "posts=5 ends41=0 arch=0" wire_summary

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
printf '{"lane": "implementer", "run_id": 99, "spawn_completed": false}\n' \
  > "$DH3/board-claims/nonce-g.json"
printf 'held assignment\n' > "$DH3/board-claims/nonce-g.body.md"
printf '{"uuid":"eeee0001","current":"eeee0001","name":"70-api-imple' \
  > "$DH3/eeee0001.json"

OUT3="$(mktemp)"
( cd "$r3" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH3" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r3" \
    BOARD_CREDENTIALS_FILE="$CREDS" IMPLEMENT_MAX_CONCURRENT=5 \
    "$DISPATCH" --sweep ) > "$OUT3" 2>&1 || true

nt "a run is NOT ended while a meta is unreadable" '"path": "/runs/99/end"' cat "$FIX3.log"
t  "the hold is reported"        "holding it"        cat "$OUT3"
t  "and names who owns it"       "server lease reclaim" cat "$OUT3"
t  "the unreadable meta is named" "eeee0001.json"    cat "$OUT3"
t  "the held journal stays on disk, open" '"spawn_completed": false' \
  cat "$DH3/board-claims/nonce-g.json"
t  "and its assignment body is not dropped" "still-there" gone "$DH3/board-claims/nonce-g.body.md"
held_wire() {
  printf 'posts=%s ends=%s\n' \
    "$(grep -c '"method"' "$FIX3.log" || true)" \
    "$(grep -c '/end' "$FIX3.log" || true)"
}
# Three empty lane claims and nothing else: architect, implementer, spike.
t "a held run sends nothing" "posts=3 ends=0" held_wire

finish
