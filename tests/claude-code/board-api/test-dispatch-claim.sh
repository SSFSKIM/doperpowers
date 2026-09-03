#!/usr/bin/env bash
# test-dispatch-claim.sh — execute-dispatch.sh's API branch: claim-based
# dispatch, the crash-recoverable claim journal, and the worker handover.
#
# Two halves, both against a real socket: what went on the wire (the fixture
# mock's request log) and what landed on disk (the claim journal, the
# assignment body, the registry meta, the environment the worker was spawned
# with). The daemon-spawn stub prints the REAL --no-wait banner line, because
# the uuid the dispatcher hands to board-bind is parsed out of it.
. "$(dirname "$0")/helpers.sh"

DISPATCH="$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh"

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
  printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$1" > "$d/.doperpowers/board.json"
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
          "body":"# assignment\nbuild it",
          "parentPin":{"parent_id":7,"parent_event_cursor":118}}},
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
 {"method":"POST","path":"/runs/99/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/78/end","status":200,"body":{"ended":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX2" "$PORT2" & MOCK2=$!
trap 'kill $MOCK $MOCK2 2>/dev/null' EXIT
wait_for_port "$PORT"  || { echo "FAIL mock server never listened on $PORT"; exit 1; }
wait_for_port "$PORT2" || { echo "FAIL mock server never listened on $PORT2"; exit 1; }

r="$(apirepo "$PORT")"
DH="$(mktemp -d)"   # pinned: a fall-through would read the operator's registry
OUT="$(mktemp)"
# A standing failed-cycle count for the ticket this claim will yield. Only the
# sweep's own resume reset it, so a ticket the DISPATCHER recovered kept the
# stale count and a much later, unrelated fault escalated early. A delivered
# recovery is a recovery, whichever phase delivered it.
mkdir -p "$DH/board-suppress"; echo 2 > "$DH/board-suppress/.attempts-12"
# A board-scripts overlay whose board-bind.sh SNAPSHOTS the claim journal at the
# instant it runs and then execs the real one. Ordering is only observable from
# INSIDE that window — after the fact every order looks the same.
BSOVL="$(mktemp -d)"
for _f in "$SCRIPTS"/*; do ln -s "$_f" "$BSOVL/$(basename "$_f")"; done
rm -f "$BSOVL/board-bind.sh"
cat > "$BSOVL/board-bind.sh" <<EOF
#!/usr/bin/env bash
cp -R "\$DAEMON_HOME/board-claims" "\$DAEMON_HOME/claims-at-bind" 2>/dev/null || true
exec "$SCRIPTS/board-bind.sh" "\$@"
EOF
chmod +x "$BSOVL/board-bind.sh"
# BOARD_RUN_TOKEN is set on the way in ON PURPOSE: a --sweep launched from a
# worker's own shell inherits that worker's run bearer, and the client hands
# BOARD_RUN_TOKEN back for ANY principal once it is in env — so every claim
# and every end below would speak as that one run instead of as automation.
( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" BOARD_SCRIPTS="$BSOVL" \
    BOARD_CREDENTIALS_FILE="$CREDS" IMPLEMENT_MAX_CONCURRENT=5 \
    BOARD_RUN_TOKEN=ambient-worker-bearer \
    DAEMON_CLAUDE_SETTINGS="$STUB/ambient-gateway.json" DAEMON_CLAUDE_EFFORT=high \
    "$DISPATCH" --sweep ) > "$OUT" 2>&1 || true

t "the granted claim is reported" "claimed #12 run=41 lane=architect" cat "$OUT"
nt "api dispatch never invokes gh" "GH-CALLED" cat "$MARKER"
attempts12() { [ -e "$DH/board-suppress/.attempts-12" ] && echo "count kept" || echo "count cleared"; }
t "a delivered dispatch clears the ticket's failed-cycle count" "count cleared" attempts12

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
# THE HANDOFF IS DONE ONLY AFTER THE BIND. Marked ahead of it, a crash in that
# window left a journal saying "handed off" over a meta holding no run
# credential and no locator — reconciliation skips a completed journal, so
# nothing ever renewed that lease and the still running worker overlapped the
# replacement the server's reclaim handed the ticket to.
t "the journal is still open while the bind runs" '"spawn_completed": false' \
  bash -c "cat '$DH'/claims-at-bind/*.json"
t "and the daemon name is already in it"          '"daemon": "12-api-architect"' \
  bash -c "cat '$DH'/claims-at-bind/*.json"

# --- the parent pin: a run-specific fact no worker read can reach -----------
# A1 hands `parentPin` back on the claim and stores it on the run; the worker's
# own bearer cannot read its parent's timeline, so this cursor travels with the
# dispatch or not at all.
t "the parent pin reaches the worker prompt" "#7 @ event 118" \
  cat "$DH/prompt-12-api-architect.md"
t "and lands in the registry meta"          '"parent_pin": "#7 @ event 118"' \
  bash -c "grep -l parent_pin '$DH'/*.json | head -1 | xargs cat"
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
# A CLAIM NAMES ITS REPO. /runs/claim is dispatch-shaped: an unscoped
# credential that names none is refused `repo-required` outright, and a scoped
# one that names a repo the token contradicts is refused `repo-mismatch` rather
# than handing this checkout a neighbouring repo's ticket to work.
t "the claim names the repo it dispatches for" '\"repo\": \"testrepo\"' cat "$FIX.log"
t "the local cap rides along as laneCap" '\"laneCap\": 1'        cat "$FIX.log"
t "the execution lane is tried"     '\"lane\": \"implementer\"'  cat "$FIX.log"
t "the spike lane is tried after it" '\"lane\": \"spike\"'       cat "$FIX.log"
# Three claims, not four and not an unbounded spin: architect (granted, then
# the lane is full), executor (empty), spike (empty) -> stop.
claim_posts() { echo "claims=$(grep -c '"path": "/runs/claim"' "$FIX.log")"; }
t "an empty lane stops the tick" "claims=3" claim_posts
t "the claim speaks as automation" '"auth": "Bearer a"' cat "$FIX.log"
# DISPATCH IS AUTOMATION, FULL STOP — the sweep's own doctrine, and the same
# reason it unsets this. A worker shell that runs --sweep directly would
# otherwise claim, and end runs, as its own run.
nt "an ambient worker bearer never reaches the wire" \
   "Bearer ambient-worker-bearer" cat "$FIX.log"

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
# The worker is oriented by the BOARD's name for the repo, the way a gh-mode
# worker is oriented by owner/name — not by whatever the checkout directory
# happens to be called, which is a fact about this machine and not about the
# board the ticket lives on.
t  "and the worker is oriented by the board's repo, not the checkout dir" \
  "\`REPO\`: testrepo" prompt
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
printf '{"lane": "architect", "run_id": 41, "spawn_completed": false, "ticket": "12"}\n' \
  > "$DH2/board-claims/nonce-c.json"
# ...and the delivery it confirms is where the ticket's failed-cycle count is
# cleared when the inline reset never ran. The reset sits one line ahead of the
# marker write, so THIS crash — bind landed, marker lost — is exactly the
# window that leaves a durable recovery beside a stale counter, and a much
# later unrelated fault would then escalate two rungs early.
mkdir -p "$DH2/board-suppress"; echo 2 > "$DH2/board-suppress/.attempts-12"
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
#     assignment an executor prompt; ending its run would strand the review
#     dispatcher's ticket. Anything outside architect|executor|spike is not
#     this script's to touch.
printf '{"lane": "qagent", "run_id": 66, "spawn_completed": false}\n' \
  > "$DH2/board-claims/nonce-f.json"
# (g) A REUSED DAEMON NAME IS NOT PROOF OF A SPAWN. Names are deterministic per
#     ticket and lane, and a retired daemon keeps its meta — so a HISTORICAL
#     entry into the same lane left a name that read as "spawned, live,
#     unbound" for the NEXT claim, closing its journal and leaving the run
#     ownerless until the lease expired. Only a RUNNING session is evidence.
printf '{"lane": "implementer", "run_id": 78, "spawn_completed": false, "ticket": "34", "daemon": "34-api-implementer"}\n' \
  > "$DH2/board-claims/nonce-g.json"
printf '{"uuid":"gggg0001","current":"gggg0001","name":"34-api-implementer","status":"retired"}' \
  > "$DH2/gggg0001.json"
# (h) A JOURNAL WHOSE WRITER IS STILL ALIVE IS NOT A CRASH. Nothing serializes
#     two dispatch processes, and a peer journals its nonce BEFORE the POST —
#     so replaying it while that response is in flight makes A1 rotate the
#     bearer under the peer and both callers spawn from their own answers.
#     This test's own shell is the live writer.
printf '{"lane": "implementer", "run_id": null, "spawn_completed": false, "pid": %s}\n' "$$" \
  > "$DH2/board-claims/nonce-h.json"

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
attempts12r() { [ -e "$DH2/board-suppress/.attempts-12" ] && echo "count kept" || echo "count cleared"; }
t "and the delivery it confirms clears the ticket's failed-cycle count" \
  "count cleared" attempts12r
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
# --- (g) a retired daemon's name proves nothing ----------------------------
t  "a run whose only witness is a RETIRED daemon is ended" '"path": "/runs/78/end"' cat "$FIX2.log"
t  "its journal is dropped"                     "gone" gone "$DH2/board-claims/nonce-g.json"
# --- (h) a peer's in-flight claim is left alone ----------------------------
nt "an in-flight nonce is not replayed"  '\"dispatchNonce\": \"nonce-h\"' cat "$FIX2.log"
t  "and it is reported as in flight"     "nonce-h is in flight"           cat "$OUT2"
t  "its journal stays open for its own writer" '"spawn_completed": false' \
  cat "$DH2/board-claims/nonce-h.json"
# Everything this tick was allowed to send, counted: the replayed claim, its
# bind, the stranded run's end, and the two empty execution lanes. A repaired
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
t "reconcile sends only what it must" "posts=6 ends41=0 arch=0" wire_summary

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
# Three empty lane claims and nothing else: architect, executor, spike.
t "a held run sends nothing" "posts=3 ends=0" held_wire

# =========================================================================
# Scenario 4 — A HOST WITHOUT uuidgen. uuidgen is declared nowhere in this
# toolkit and a minimal image ships none of util-linux; python3 is a hard
# dependency of every script here. Without a fallback `$(uuidgen)` expanded to
# nothing inside the errexit-suppressed loop condition, so the claim went out
# under an EMPTY dispatch nonce and its journal was filed as ".json" — a name
# the next claim on that path takes away, and with it a granted run's only
# recovery record.
# =========================================================================
PORT4="$(free_port)"
FIX4="$(mktemp)"; : > "$FIX4.log"
cat > "$FIX4" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":71,"ticketId":31,"fence":1,"bearer":"tok-n","plan":null,
          "body":"nonce work","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/71/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX4" "$PORT4" & MOCK4=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 2>/dev/null' EXIT
wait_for_port "$PORT4" || { echo "FAIL mock server never listened on $PORT4"; exit 1; }

# What a host with no uuidgen presents to `$(uuidgen)`: nothing on stdout.
NOUUID="$(mktemp -d)"
printf '#!/usr/bin/env bash\nexit 127\n' > "$NOUUID/uuidgen"
chmod +x "$NOUUID/uuidgen"

r4="$(apirepo "$PORT4")"
DH4="$(mktemp -d)"
OUT4="$(mktemp)"
( cd "$r4" && env PATH="$NOUUID:$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH4" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r4" \
    BOARD_CREDENTIALS_FILE="$CREDS" ARCHITECT_MAX_CONCURRENT=0 \
    "$DISPATCH" --sweep ) > "$OUT4" 2>&1 || true

nonce_len() {
  grep '"path": "/runs/claim"' "$FIX4.log" | head -1 |
    python3 -c 'import json, sys
b = json.loads(json.loads(sys.stdin.read())["body"])
print("nonce-len=%d" % len(b["dispatchNonce"]))'
}
t "the claim still goes out under a real nonce" "nonce-len=36" nonce_len
t "and the dispatch lands"                      "claimed #31 run=71" cat "$OUT4"
# The consequence, not just the symptom: every empty nonce names the SAME
# journal, so the next claim on that lane overwrote the granted run's record
# and then removed it when the lane answered empty. The one record that could
# have recovered run 71 was gone before the tick ended.
journal4() { cat "$DH4"/board-claims/*.json 2>/dev/null || echo "no journal survived"; }
t "the granted run keeps its recovery record" '"run_id": 71'          journal4
t "and that record says the handoff completed" '"spawn_completed": true' journal4

# The guard itself, at the seam: with NEITHER minter able to answer, the claim
# is refused before anything is journalled. There is no end-to-end form of this
# — python3 has to work for the dispatcher to run at all — so it is exercised
# where it lives.
NOMINT="$(mktemp -d)"
printf '#!/usr/bin/env bash\nexit 127\n' > "$NOMINT/uuidgen"
printf '#!/usr/bin/env bash\nexit 127\n' > "$NOMINT/python3"
chmod +x "$NOMINT/uuidgen" "$NOMINT/python3"
nonce_guard() {
  ( PATH="$NOMINT:$PATH"
    # shellcheck source=../../../skills/issue-tracker/scripts/_claim_journal.sh
    . "$SCRIPTS/_claim_journal.sh"
    local rc=0
    _claim_nonce || rc=$?
    # Bracketed: rc=127 (the helper missing entirely) contains "rc=1".
    echo "rc=[$rc]" )
}
t "with no minter at all the refusal is loud" "no claim nonce could be minted" nonce_guard
t "and it refuses rather than answering empty" "rc=[1]" nonce_guard

# =========================================================================
# Scenario 5 — AN UNCERTAIN IMPLEMENTER CLAIM DOES NOT FALL THROUGH TO SPIKE.
# A claim that dies on the wire may still have landed; its journal is kept and
# reconciliation replays it later. Reading that as "lane refused" and claiming
# a spike NOW puts two workers on the machine for one slot — the replayed
# executor and the spike — over the combined cap the loop exists to hold.
# =========================================================================
PORT5="$(free_port)"
FIX5="$(mktemp)"; : > "$FIX5.log"
cat > "$FIX5" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":503,"once":true,
  "body":{"error":{"code":"unavailable","message":"claim service is down"}}},
 {"method":"POST","path":"/runs/claim","status":200,
  "body":{"runId":81,"ticketId":41,"fence":1,"bearer":"tok-s","plan":null,
          "body":"spike work","parentPin":null}},
 {"method":"POST","path":"/runs/81/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX5" "$PORT5" & MOCK5=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 2>/dev/null' EXIT
wait_for_port "$PORT5" || { echo "FAIL mock server never listened on $PORT5"; exit 1; }

r5="$(apirepo "$PORT5")"
DH5="$(mktemp -d)"
OUT5="$(mktemp)"
( cd "$r5" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH5" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r5" \
    BOARD_CREDENTIALS_FILE="$CREDS" ARCHITECT_MAX_CONCURRENT=0 \
    "$DISPATCH" --sweep ) > "$OUT5" 2>&1 || true

t  "the uncertain claim keeps its journal for replay" \
   "kept for replay"                                   cat "$OUT5"
nt "and the spike lane is NOT claimed behind it" '\"lane\": \"spike\"' cat "$FIX5.log"
claim5() { echo "claims=$(grep -c '"path": "/runs/claim"' "$FIX5.log")"; }
t  "the tick stops on the uncertain claim"  "claims=1"     claim5
nt "so nothing is spawned this tick"        "ARGS name="   bash -c "cat '$DH5/spawn-capture.txt' 2>/dev/null || echo none"
journal5() { ls "$DH5/board-claims"/*.json >/dev/null 2>&1 && echo "journal kept" || echo "journal gone"; }
t  "the record the replay needs survives"   "journal kept" journal5

# =========================================================================
# Scenario 6 — THE SWEEP'S TICK DEADLINE BOUNDS THE DISPATCH PHASE FROM THE
# INSIDE. One budget check ahead of the whole phase admitted every loop here in
# full on one second of remaining budget, under the sweep's global lock. The
# deadline is checked before each FRESH claim; unset or unparseable is no gate
# at all, which is what a direct --sweep and the by-name `dispatch` phase get.
# =========================================================================
PORT6="$(free_port)"
FIX6="$(mktemp)"; : > "$FIX6.log"
cat > "$FIX6" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX6" "$PORT6" & MOCK6=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 2>/dev/null' EXIT
wait_for_port "$PORT6" || { echo "FAIL mock server never listened on $PORT6"; exit 1; }

r6="$(apirepo "$PORT6")"
DH6="$(mktemp -d)"
SWEEP6() {  # SWEEP6 [env...] — one dispatch tick against this board
  ( cd "$r6" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
      DAEMON_HOME="$DH6" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r6" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$@" "$DISPATCH" --sweep )
}
OUT6="$(mktemp)"
SWEEP6 BOARD_TICK_DEADLINE=1 > "$OUT6" 2>&1 || true
t  "a passed deadline stops the fresh claims" "tick deadline has passed" cat "$OUT6"
nt "and nothing goes on the wire"             '"path": "/runs/claim"'    cat "$FIX6.log"

: > "$FIX6.log"
OUT6B="$(mktemp)"
SWEEP6 > "$OUT6B" 2>&1 || true
t  "no deadline is no gate"    '"path": "/runs/claim"'   cat "$FIX6.log"
nt "and says nothing about one" "tick deadline"          cat "$OUT6B"

: > "$FIX6.log"
OUT6C="$(mktemp)"
SWEEP6 BOARD_TICK_DEADLINE=not-a-number > "$OUT6C" 2>&1 || true
t  "an unparseable deadline is no gate either" '"path": "/runs/claim"' cat "$FIX6.log"

# =========================================================================
# Scenario 7 — ONE RECOVERY ATTEMPT PER TICKET PER TICK REACHES THIS PHASE
# TOO. The sweep's resume phase records every ticket it attempted a recovery
# for this tick; phase 4 hands that ledger across the same way it hands the
# suppression directory. Without it an ordinary lane claim could pick the very
# ticket whose replay just faulted — a second attempt in the same tick, over
# the invariant the ledger exists to hold. The claim is how we learn WHICH
# ticket the server picked, so the refusal is a release, as suppression's is.
# =========================================================================
PORT7="$(free_port)"
FIX7="$(mktemp)"; : > "$FIX7.log"
cat > "$FIX7" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":71,"ticketId":33,"fence":1,"bearer":"tok-l","plan":null,
          "body":"ledgered work","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/71/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/71/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX7" "$PORT7" & MOCK7=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 2>/dev/null' EXIT
wait_for_port "$PORT7" || { echo "FAIL mock server never listened on $PORT7"; exit 1; }

r7="$(apirepo "$PORT7")"
DH7="$(mktemp -d)"
LEDGER7="$(mktemp)"; echo 33 > "$LEDGER7"
OUT7="$(mktemp)"
( cd "$r7" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH7" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r7" \
    BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RESUMED_LEDGER="$LEDGER7" \
    "$DISPATCH" --sweep ) > "$OUT7" 2>&1 || true

t  "a claim yielding a tick-ledgered ticket is released" \
   "#33 already had its one recovery attempt this tick"  cat "$OUT7"
t  "and that run is ended"          '"path": "/runs/71/end"'  cat "$FIX7.log"
nt "so no worker is spawned for it" "ARGS name=33"  \
   bash -c "cat '$DH7/spawn-capture.txt' 2>/dev/null || echo none"
journal7() { ls "$DH7/board-claims"/*.json >/dev/null 2>&1 && echo "journal kept" || echo "journal dropped"; }
t  "and the journal is dropped with it"  "journal dropped"  journal7

# =========================================================================
# Scenario 8 — THE RESET LANDS BEFORE THE SEAL. Reconciliation's `repaired`
# arm marks the journal spawn_completed, and a sealed journal is skipped by
# every later pass — so anything left to do AFTER that write is done once or
# never. With the failed-cycle reset on the far side of it, a crash in
# between left a durable recovery beside a stale counter with nothing that
# could ever revisit it: the early-escalation bug, one window later.
# Reset-then-seal is crash-safe instead — both steps are idempotent, and a
# crash between them leaves the journal open for the next pass to redo both.
# The seal is made to FAIL here (read-only journal), which is the same
# window: the reset must already be durable when the write does not land.
# =========================================================================
PORT8="$(free_port)"
FIX8="$(mktemp)"; : > "$FIX8.log"
cat > "$FIX8" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX8" "$PORT8" & MOCK8=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 2>/dev/null' EXIT
wait_for_port "$PORT8" || { echo "FAIL mock server never listened on $PORT8"; exit 1; }

r8="$(apirepo "$PORT8")"
DH8="$(mktemp -d)"; mkdir -p "$DH8/board-claims" "$DH8/board-suppress"
printf '{"uuid":"eeee0001","current":"eeee0001","name":"15-api-implementer","status":"working","run_id":43,"lane":"implementer","ticket":"15"}' \
  > "$DH8/eeee0001.json"
printf '{"lane": "implementer", "run_id": 43, "spawn_completed": false, "ticket": "15"}\n' \
  > "$DH8/board-claims/nonce-i.json"
chmod 444 "$DH8/board-claims/nonce-i.json"
echo 2 > "$DH8/board-suppress/.attempts-15"
OUT8="$(mktemp)"
( cd "$r8" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH8" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r8" \
    BOARD_CREDENTIALS_FILE="$CREDS" "$DISPATCH" --sweep ) > "$OUT8" 2>&1 || true
chmod 644 "$DH8/board-claims/nonce-i.json"

t  "a seal that never lands still leaves the count cleared" "count cleared" \
   bash -c "[ -e '$DH8/board-suppress/.attempts-15' ] && echo 'count kept' || echo 'count cleared'"
t  "and the unsealed journal is left for the next pass to redo" \
   '"spawn_completed": false'  cat "$DH8/board-claims/nonce-i.json"

# =========================================================================
# Scenario 9 — A RESET THAT FAILED IS NOT A RESET. Absent is the one benign
# outcome (nothing to clear); every other removal error — a read-only
# registry, a permission change, a full or unmounted volume — means the count
# is still standing, and sealing the journal on top of it hides that from
# every later pass. So the seal is skipped and the journal stays open: the
# next pass retries the pair, both steps being idempotent.
# =========================================================================
PORT9="$(free_port)"
FIX9="$(mktemp)"; : > "$FIX9.log"
cat > "$FIX9" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX9" "$PORT9" & MOCK9=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 $MOCK9 2>/dev/null' EXIT
wait_for_port "$PORT9" || { echo "FAIL mock server never listened on $PORT9"; exit 1; }

r9="$(apirepo "$PORT9")"
DH9="$(mktemp -d)"; mkdir -p "$DH9/board-claims" "$DH9/board-suppress"
printf '{"uuid":"eeee0002","current":"eeee0002","name":"16-api-implementer","status":"working","run_id":44,"lane":"implementer","ticket":"16"}' \
  > "$DH9/eeee0002.json"
printf '{"lane": "implementer", "run_id": 44, "spawn_completed": false, "ticket": "16"}\n' \
  > "$DH9/board-claims/nonce-j.json"
echo 2 > "$DH9/board-suppress/.attempts-16"
chmod 555 "$DH9/board-suppress"      # an unlink needs write on the DIRECTORY
OUT9="$(mktemp)"
( cd "$r9" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH9" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r9" \
    BOARD_CREDENTIALS_FILE="$CREDS" "$DISPATCH" --sweep ) > "$OUT9" 2>&1 || true
chmod 755 "$DH9/board-suppress"

t  "a failed reset leaves the journal open for the next pass" \
   '"spawn_completed": false'  cat "$DH9/board-claims/nonce-j.json"
t  "and says so, naming the ticket whose count still stands" \
   "failed-cycle reset failed"  cat "$OUT9"
t  "the count is still there to be retried" "count kept" \
   bash -c "[ -e '$DH9/board-suppress/.attempts-16' ] && echo 'count kept' || echo 'count cleared'"

# =========================================================================
# Scenario 10 — ENOENT ANSWERS TWO OPPOSITE QUESTIONS. os.remove says "no
# such file" both when the counter is already gone (benign: the reset is
# finished) and when the DIRECTORY it lives in cannot be seen at all — an
# operator BOARD_SUPPRESS_DIR whose volume unmounted, a path that moved.
# Sealing on the second reading is the same bug as swallowing EACCES: the
# mount returns carrying the stale count, and the journal that would have
# cleared it is closed forever.
#
# The two are told apart by REACHABILITY, not by the directory alone. The
# sweep creates that directory the first time it counts anything, so on a
# registry that has never had a failed cycle it legitimately does not exist —
# the common, healthy case, pinned second below. An absent directory whose
# PARENT is also gone is a path this process cannot see, where absence proves
# nothing.
# =========================================================================
PORT10="$(free_port)"
FIX10="$(mktemp)"; : > "$FIX10.log"
cat > "$FIX10" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX10" "$PORT10" & MOCK10=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 $MOCK9 $MOCK10 2>/dev/null' EXIT
wait_for_port "$PORT10" || { echo "FAIL mock server never listened on $PORT10"; exit 1; }
r10="$(apirepo "$PORT10")"

mkjrepaired() {  # mkjrepaired <registry> <ticket> <run> — one repaired-shaped journal
  mkdir -p "$1/board-claims"
  printf '{"uuid":"aaaa%s","current":"aaaa%s","name":"%s-api-implementer","status":"working","run_id":%s,"lane":"implementer","ticket":"%s"}' \
    "$2" "$2" "$2" "$3" "$2" > "$1/aaaa$2.json"
  printf '{"lane": "implementer", "run_id": %s, "spawn_completed": false, "ticket": "%s"}\n' \
    "$3" "$2" > "$1/board-claims/nonce-$2.json"
}
SWEEP10() {  # SWEEP10 <registry> [env...] — one dispatch tick against this board
  local dh="$1"; shift
  ( cd "$r10" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
      DAEMON_HOME="$dh" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r10" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$@" "$DISPATCH" --sweep )
}

# (a) the suppression path is UNREACHABLE — its parent does not exist either.
DHA10="$(mktemp -d)"; mkjrepaired "$DHA10" 17 45
OUTA10="$(mktemp)"
SWEEP10 "$DHA10" BOARD_SUPPRESS_DIR="$DHA10/gone-volume/board-suppress" \
  > "$OUTA10" 2>&1 || true
t  "an unreachable suppression path does not seal the journal" \
   '"spawn_completed": false'  cat "$DHA10/board-claims/nonce-17.json"
t  "and reports the reset it could not make" \
   "failed-cycle reset failed"  cat "$OUTA10"

# (b) ...and the registry that simply never counted anything still seals. The
#     sweep creates that directory on demand, so its absence under a live
#     registry is the healthy default, not a fault — reading it as one would
#     stall every repair on every fleet that has had no failed cycle.
DHB10="$(mktemp -d)"; mkjrepaired "$DHB10" 18 46
OUTB10="$(mktemp)"
SWEEP10 "$DHB10" > "$OUTB10" 2>&1 || true
t  "a registry with no suppression directory repairs normally" \
   '"spawn_completed": true'  cat "$DHB10/board-claims/nonce-18.json"
nt "and reports no failure" "failed-cycle reset failed" cat "$OUTB10"

finish
