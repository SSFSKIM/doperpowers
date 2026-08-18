#!/usr/bin/env bash
# test-review-dispatch-claim.sh — review-dispatch.sh's API branch: the qagent
# lane claimed off the board, the crash-recoverable claim journal, and the
# Reviewer worker's handover (spawn env, startup barrier, bind, lane stamp).
#
# Same two halves as the execution-side suite: what went on the wire (the
# fixture mock's request log) and what landed on disk (journal, assignment
# body, registry meta, the environment the worker was spawned with). The
# daemon-spawn stub prints the REAL --no-wait banner (the uuid handed to
# board-bind is parsed out of it) and plays the worker's half of the startup
# barrier, which the review protocol makes a hard gate.
. "$(dirname "$0")/helpers.sh"

DISPATCH="$REPO_ROOT/skills/qa-loops/scripts/review-dispatch.sh"

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
import json, os, shutil, time
ready = os.environ["READY"]
home = os.environ["DAEMON_HOME"]
for _ in range(500):
    if os.path.isfile(ready):
        # The claim journal AT THE INSTANT BEFORE THE ACK. The handoff is not
        # durable until this ack exists, so the dispatcher may not have marked
        # it done yet — and after the fact every order looks the same.
        snap = os.path.join(home, "claims-at-ack")
        if not os.path.exists(snap):
            shutil.copytree(os.path.join(home, "board-claims"), snap)
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
# A standing failed-cycle count for the ticket this claim will yield. Only the
# sweep's own resume reset it, so a ticket the DISPATCHER recovered kept the
# stale count and a much later, unrelated fault escalated early. A delivered
# recovery is a recovery, whichever phase delivered it.
mkdir -p "$DH/board-suppress"; echo 2 > "$DH/board-suppress/.attempts-9"
# BOARD_RUN_TOKEN is set on the way in ON PURPOSE: a --sweep launched from a
# worker's own shell inherits that worker's run bearer, and the client hands
# BOARD_RUN_TOKEN back for ANY principal once it is in env — so every claim
# and every end below would speak as that one run instead of as automation.
( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    BOARD_RUN_TOKEN=ambient-worker-bearer \
    DAEMON_CLAUDE_SETTINGS="$STUB/ambient-gateway.json" \
    "$DISPATCH" --sweep ) > "$OUT" 2>&1 || true

t "the granted claim is reported" "claimed #9 run=51 lane=qagent" cat "$OUT"
nt "api review dispatch never invokes gh" "GH-CALLED" cat "$MARKER"
attempts9() { [ -e "$DH/board-suppress/.attempts-9" ] && echo "count kept" || echo "count cleared"; }
t "a delivered dispatch clears the ticket's failed-cycle count" "count cleared" attempts9

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
# THE HANDOFF IS DURABLE ONLY AFTER THE WORKER ACKS. Marked at the bind, a
# crash before the barrier was published left a journal saying "handed off"
# over a reviewer that can never start: it waits out its 120-second barrier
# bound, ends without reviewing, and the ticket stays owned by a session
# nothing will ever wake. The control dir travels in the journal because the
# ack file inside it is the only thing reconciliation can tell those apart by.
t "the journal is still open when the worker acks" '"spawn_completed": false' \
  bash -c "cat '$DH'/claims-at-ack/*.json"
t "and it names the control dir the barrier lives in" '"control"' \
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
# DISPATCH IS AUTOMATION, FULL STOP — the sweep's own doctrine, and the same
# reason it unsets this. A worker shell that runs --sweep directly would
# otherwise claim, and end runs, as its own run.
nt "an ambient worker bearer never reaches the wire" \
   "Bearer ambient-worker-bearer" cat "$FIX.log"

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
# ...and stored 0600, the way board-bind wrote it. Every bookkeeping stamp that
# touches this meta afterwards has to hold that line: one rewrite at the umask
# default republishes the run bearer world-readable, and the api path's own
# stamp then faithfully preserves the widened mode.
meta_mode() {
  python3 -c 'import glob, os, sys
print("%o" % (os.stat(glob.glob(sys.argv[1])[0]).st_mode & 0o777))' "$DH/bbbb0001-*.json"
}
t "the bearer meta is not world-readable" "600" meta_mode
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
# `REVIEW_MODE`: api is a prefix of api-scale, so the positive assert alone
# cannot tell the two variants apart — the pair can.
nt "and it is not the api-scale variant"         '`REVIEW_MODE`: api-scale' prompt
t  "the assignment file is pinned in the prompt" "$DH/board-claims/" prompt
t  "the board scripts, not gh, are the board"    "board-show.sh 9"   prompt
t  "the barrier file is bound"                   '`BIND_READY_FILE`: ' prompt
nt "no PR framing reaches an api reviewer"       "You are a REVIEW worker for PR" prompt
nt "no scale framing either"                     "SCALE REVIEWER"     prompt
nt "nothing was left unrendered"                 "{{"                 prompt
# THE BASE OF AN API REVIEW IS NOT KNOWABLE AT CLAIM TIME. The board carries no
# PR — the ticket's `pr` value is read by the WORKER — so binding the default
# branch as BASE_REF was not a safe default but a wrong answer: a PR stacked
# onto an integration branch then had the engine run `--base origin/<default>`,
# reviewing the whole stack instead of its own commits, against manifests from
# the wrong ref. The binding says UNRESOLVED (a sentinel that is not a ref, so a
# worker that skipped the resolution gets `fatal: bad revision`, never a quietly
# wrong range) and the prompt hands the worker the resolution.
t  "the base binding says it is unresolved"      '`BASE_REF`: UNRESOLVED' prompt
t  "the worker is told to read the base off the PR" "gh pr view <n> --json" prompt
t  "the manifests name the ref they came from"   '`MANIFEST_REF`: '   prompt
# The bindings an api reviewer cannot function without, pinned on the VALUE
# side: a `NAME`: assertion passes just as well against a rendered blank, which
# is the shape a call site that stopped supplying a placeholder used to take.
bound() {  # bound <NAME> <prompt-file> — reads the rendered roster line shape
  local v; v="$(sed -n "s/^- \`$1\`: \(.*\)$/\1/p" "$2" | head -1)"
  [ -n "$v" ] && echo "$1 bound: $v" || echo "$1 UNBOUND"
}
skill_pin() {  # skill_pin <prompt-file> — SKILL_FILE renders in prose, not on the roster
  local v; v="$(sed -n 's/.*dispatcher-pinned copy at `\([^`]*\)`.*/\1/p' "$1" | head -1)"
  [ -n "$v" ] && echo "SKILL_FILE bound: $v" || echo "SKILL_FILE UNBOUND"
}
API_PROMPT="$DH/prompt-9-api-qagent.md"
t "the barrier file binding carries a value"     "BIND_READY_FILE bound" bound BIND_READY_FILE "$API_PROMPT"
t "the implement contract carries a value"       "IMPLEMENT_PROTOCOL_FILE bound" bound IMPLEMENT_PROTOCOL_FILE "$API_PROMPT"
t "the board scripts binding carries a value"    "BOARD_SCRIPTS bound" bound BOARD_SCRIPTS "$API_PROMPT"
t "the assignment file binding carries a value"  "TICKET_BODY_FILE bound" bound TICKET_BODY_FILE "$API_PROMPT"
t "the pinned protocol path carries a value"     "SKILL_FILE bound" skill_pin "$API_PROMPT"

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
printf '{"lane": "qagent", "run_id": 51, "spawn_completed": false, "ticket": "9"}\n' \
  > "$DH2/board-claims/nonce-c.json"
# ...and the delivery it confirms is where the ticket's failed-cycle count is
# cleared when the inline reset never ran. The reset sits one line ahead of the
# marker write, so THIS crash — bind landed, marker lost — is exactly the
# window that leaves a durable recovery beside a stale counter, and a much
# later unrelated fault would then escalate two rungs early.
mkdir -p "$DH2/board-suppress"; echo 2 > "$DH2/board-suppress/.attempts-9"
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
attempts9r() { [ -e "$DH2/board-suppress/.attempts-9" ] && echo "count kept" || echo "count cleared"; }
t "and the delivery it confirms clears the ticket's failed-cycle count" \
  "count cleared" attempts9r
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

# =========================================================================
# Scenario 4 — THE HANDOFF WINDOW'S REMAINING CRASH POINT, and the release
# that fails. The journal is marked only once the worker has acked the startup
# barrier, which leaves one shape a crash can produce: a bound meta under an
# open journal. Two of those are indistinguishable by the run alone —
#   (s) bound, barrier never published: the reviewer waited out its 120-second
#       bound and ended. Repairing the marker would leave the ticket owned by
#       a session that can never start and a lease this tick renews forever.
#   (t) bound, barrier crossed, only the marker write lost: a working reviewer
#       that must not be touched.
# — and the ack file inside the journalled control dir is what separates them.
# Beside them, (u): a release that FAILS keeps its journal. It is the only
# retry handle there is; dropped, the run stays open owning its ticket and no
# later tick can retry, so "it retries next tick" was never true.
# =========================================================================
PORT4="$(free_port)"
FIX4="$(mktemp)"; : > "$FIX4.log"
cat > "$FIX4" <<'JSON'
[
 {"method":"POST","path":"/runs/70/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/72/end","status":503,
  "body":{"error":{"code":"unavailable","message":"the board is down"}}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX4" "$PORT4" & MOCK4=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 2>/dev/null' EXIT
wait_for_port "$PORT4" || { echo "FAIL mock server never listened on $PORT4"; exit 1; }

r4="$(apirepo "$PORT4")"
DH4="$(mktemp -d)"; mkdir -p "$DH4/board-claims"
# (s) the stranded reviewer: a control dir with no ack in it.
CTL_S="$DH4/41-api-qagent-control.stranded"; mkdir -p "$CTL_S"
printf '{"uuid": "ffff0001", "ticket": "41", "ledger": "x"}\n' > "$CTL_S/bind-ready.json"
printf '{"uuid":"ffff0001","current":"ffff0001","name":"41-api-qagent","status":"working","run_id":70,"lane":"qagent","ticket":"41"}' \
  > "$DH4/ffff0001.json"
printf '{"lane": "qagent", "run_id": 70, "spawn_completed": false, "ticket": "41", "daemon": "41-api-qagent", "control": "%s"}\n' \
  "$CTL_S" > "$DH4/board-claims/nonce-s.json"
printf 'stranded review assignment\n' > "$DH4/board-claims/nonce-s.body.md"
# (t) the same shape with the ack present — a reviewer already at work.
CTL_T="$DH4/42-api-qagent-control.acked"; mkdir -p "$CTL_T"
printf '{"uuid": "ffff0002", "ticket": "42", "ledger": "x"}\n' > "$CTL_T/bind-ready.json"
printf '{"uuid": "ffff0002"}\n' > "$CTL_T/bind-ready.json.ack"
printf '{"uuid":"ffff0002","current":"ffff0002","name":"42-api-qagent","status":"working","run_id":71,"lane":"qagent","ticket":"42"}' \
  > "$DH4/ffff0002.json"
printf '{"lane": "qagent", "run_id": 71, "spawn_completed": false, "ticket": "42", "daemon": "42-api-qagent", "control": "%s"}\n' \
  "$CTL_T" > "$DH4/board-claims/nonce-t.json"
# (u) claimed, never handed off, and the release will fail.
printf '{"lane": "qagent", "run_id": 72, "spawn_completed": false}\n' \
  > "$DH4/board-claims/nonce-u.json"
printf 'undelivered review assignment\n' > "$DH4/board-claims/nonce-u.body.md"
# (v) THE SAME SHAPE AS (s) WITH A LIVE WRITER: bound, no ack, and the process
#     that claimed it is still running — a peer between its bind and the ack it
#     is waiting for. That handover legitimately outlives any mtime grace (the
#     bound is 120 seconds), so liveness is the only thing that separates it
#     from (s). It is NOT a completed delivery: if that reviewer never acks,
#     the peer retires it and releases the run. Reading it as "marker lost"
#     seals a journal somebody else is still writing and — the reason it is
#     pinned here — clears the ticket failed-cycle ladder for a delivery that
#     may be about to be undone.
CTL_V="$DH4/43-api-qagent-control.inflight"; mkdir -p "$CTL_V"
printf '{"uuid": "ffff0003", "ticket": "43", "ledger": "x"}\n' > "$CTL_V/bind-ready.json"
printf '{"uuid":"ffff0003","current":"ffff0003","name":"43-api-qagent","status":"working","run_id":73,"lane":"qagent","ticket":"43"}' \
  > "$DH4/ffff0003.json"
printf '{"lane": "qagent", "run_id": 73, "spawn_completed": false, "ticket": "43", "daemon": "43-api-qagent", "control": "%s", "pid": %s}\n' \
  "$CTL_V" "$$" > "$DH4/board-claims/nonce-v.json"
mkdir -p "$DH4/board-suppress"; echo 2 > "$DH4/board-suppress/.attempts-43"

OUT4="$(mktemp)"
( cd "$r4" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH4" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r4" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT4" 2>&1 || true

# --- (s) a reviewer that can never start is not left owning its ticket -----
t  "the barrier-less handoff is reported" "startup barrier never opened" cat "$OUT4"
t  "its worker is retired"                "retire ffff0001"  cat "$DH4/spawn-capture.txt"
t  "and its run ended so the ticket requeues" '"path": "/runs/70/end"' cat "$FIX4.log"
t  "ended as abandoned"                   '\"reason\": \"abandoned\"'  cat "$FIX4.log"
gone4() { [ -e "$1" ] && echo "still-there" || echo "gone"; }
t  "the journal is dropped"               "gone" gone4 "$DH4/board-claims/nonce-s.json"
# --- (v) a delivery still waiting on its ack is not a delivery -------------
t  "a bound handover under a live writer is left in flight" \
   "is in flight under a live dispatcher"     cat "$OUT4"
attempts43() { [ -e "$DH4/board-suppress/.attempts-43" ] && echo "count kept" || echo "count cleared"; }
t  "and its ticket keeps its failed-cycle count until the ack lands" \
   "count kept"                               attempts43
t  "its journal is left open for the peer to mark" '"spawn_completed": false' \
   cat "$DH4/board-claims/nonce-v.json"
nt "and its run is not ended"    '"path": "/runs/73/end"'   cat "$FIX4.log"

# --- (t) a reviewer that DID cross its barrier is left alone ---------------
nt "an acked reviewer's run is never ended" '"path": "/runs/71/end"' cat "$FIX4.log"
nt "and its worker is never retired"        "retire ffff0002"  \
   bash -c "cat '$DH4/spawn-capture.txt' 2>/dev/null || echo none"
t  "its marker is simply repaired"          '"spawn_completed": true' \
   cat "$DH4/board-claims/nonce-t.json"
# --- (u) the retry handle survives a failed release ------------------------
t  "a release that FAILED keeps its journal" \
   "the journal is KEPT so the next tick can retry"  cat "$OUT4"
t  "the record stays open on disk"          '"spawn_completed": false' \
   cat "$DH4/board-claims/nonce-u.json"
t  "and its assignment body is not dropped" "still-there" gone4 "$DH4/board-claims/nonce-u.body.md"

# =========================================================================
# Scenario 5 — THE MANIFEST SNAPSHOTS COME FROM A CURRENT TRACKING REF. The
# PR path fetches head and base before its own two `git show` calls; this path
# fetched nothing, so a clone whose origin/<default> was stale — or, in a fresh
# clone, absent — handed the worker an empty or outdated risk-surface and
# repo-facts policy and then told it to KEEP those copies whenever its resolved
# base matches MANIFEST_REF. git only: this dispatcher never invokes gh.
# =========================================================================
PORT5="$(free_port)"
FIX5="$(mktemp)"; : > "$FIX5.log"
cat > "$FIX5" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":90,"ticketId":50,"fence":1,"bearer":"tok-m","plan":null,
          "body":"manifest review","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/90/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX5" "$PORT5" & MOCK5=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 2>/dev/null' EXIT
wait_for_port "$PORT5" || { echo "FAIL mock server never listened on $PORT5"; exit 1; }

# The remote carries both manifests on its default branch...
UP="$(mkrepo)"
git -C "$UP" symbolic-ref HEAD refs/heads/main
mkdir -p "$UP/.doperpowers"
printf 'RISK-SURFACE-FROM-ORIGIN\n' > "$UP/.doperpowers/risk-surfaces.md"
printf 'REPO-FACTS-FROM-ORIGIN\n'   > "$UP/.doperpowers/repo-facts.md"
git -C "$UP" add -A
git -C "$UP" -c user.email=t@example.com -c user.name=t commit -qm manifests
# ...and the dispatching clone has the remote configured but has never fetched
# it, which is exactly a fresh clone or a long-idle daemon host.
r5="$(apirepo "$PORT5")"
git -C "$r5" remote add origin "$UP"
DH5="$(mktemp -d)"
OUT5="$(mktemp)"
( cd "$r5" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH5" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r5" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT5" 2>&1 || true

prompt5() { cat "$DH5/prompt-50-api-qagent.md"; }
t  "the risk-surface snapshot is the remote's"  "RISK-SURFACE-FROM-ORIGIN" prompt5
t  "so is the repo-facts snapshot"              "REPO-FACTS-FROM-ORIGIN"   prompt5
nt "neither degrades to the empty fallback"     "no repo risk-surface manifest" prompt5
nt "the fetch is git, never gh"                 "GH-CALLED" cat "$MARKER"

# =========================================================================
# Scenario 6 — THE SCALE VARIANT. A claim whose `pr` is not URL-shaped is an
# epic's closure-package event id, and its `branch` the integration ref: the
# aggregate review of a recomposition epic, which has no PR at all. The
# dispatcher is the only party that sees the claim response, so it — not the
# worker — picks the render mode, and the two bindings ride the prompt because
# no board read hands them over.
# =========================================================================
PORT6="$(free_port)"
FIX6="$(mktemp)"; : > "$FIX6.log"
cat > "$FIX6" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":61,"ticketId":88,"fence":2,"bearer":"scale-bearer",
          "body":"epic assignment","pr":"3141","branch":"epic/e9-integration",
          "parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/61/bind","status":200,"body":{"ok":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX6" "$PORT6" & MOCK6=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 2>/dev/null' EXIT
wait_for_port "$PORT6" || { echo "FAIL mock server never listened on $PORT6"; exit 1; }

r6="$(apirepo "$PORT6")"
DH6="$(mktemp -d)"
OUT6="$(mktemp)"
( cd "$r6" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH6" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r6" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT6" 2>&1 || true

SCALE_PROMPT="$DH6/prompt-88-api-qagent.md"
t "the scale dispatch reports the handoff" "claimed #88 run=61" cat "$OUT6"
t "the bind reached the wire" '"path": "/runs/61/bind"' cat "$FIX6.log"
t "an event-id pr renders the api-scale block" \
  "SCALE REVIEWER of recomposition epic #88" cat "$SCALE_PROMPT"
t "the closure package binding rides the prompt" '`CLOSURE_PACKAGE`: 3141' cat "$SCALE_PROMPT"
t "the integration ref binding rides the prompt" \
  '`INTEGRATION_REF`: epic/e9-integration' cat "$SCALE_PROMPT"
t "the assignment file still rides an api-scale prompt" '`TICKET_BODY_FILE`: ' cat "$SCALE_PROMPT"
# The value side on the api-scale call site too — the same P_* block serves
# both api modes, but only the api render was pinned on values before.
t "the api-scale barrier file carries a value"   "BIND_READY_FILE bound" bound BIND_READY_FILE "$SCALE_PROMPT"
t "the api-scale implement contract carries a value" "IMPLEMENT_PROTOCOL_FILE bound" bound IMPLEMENT_PROTOCOL_FILE "$SCALE_PROMPT"
t "the api-scale board scripts carry a value"    "BOARD_SCRIPTS bound" bound BOARD_SCRIPTS "$SCALE_PROMPT"
t "the api-scale assignment file carries a value" "TICKET_BODY_FILE bound" bound TICKET_BODY_FILE "$SCALE_PROMPT"
t "the api-scale protocol pin carries a value"   "SKILL_FILE bound" skill_pin "$SCALE_PROMPT"
t "the scale prompt orders the integration checkout" \
  "git fetch origin epic/e9-integration" cat "$SCALE_PROMPT"
# THE CHECKOUT NAMES THE REF THE FETCH JUST WROTE. `git fetch origin <ref>` on a
# single-branch clone — the shape `git clone --single-branch` and every worktree
# cut from one leaves behind — updates no remote-tracking ref, because the
# configured refspec does not cover that branch; only FETCH_HEAD moves. A worker
# ordered onto `origin/<ref>` then reviews an absent or stale ref, silently.
t "the scale checkout uses the ref the fetch wrote" \
  "git checkout --detach FETCH_HEAD" cat "$SCALE_PROMPT"
nt "and never the remote-tracking ref the fetch may not have moved" \
  "checkout --detach origin/" cat "$SCALE_PROMPT"
# THE WORKER RESOLVES ITS OWN BASE, AUTHORITATIVELY. The dispatcher's
# DEFAULT_BRANCH ladder can settle on a stale local origin/HEAD or, with no
# network and no gh, on the literal `main` — and an epic reviewed (and closed)
# against a branch it does not merge into is the wrong range, silently, because
# every fetch still succeeds. Origin's own HEAD symref is the one answer that
# can be neither stale-local nor guessed, and the worker has the network to ask
# for it, so the rendered binding is an echo and `ls-remote` is the authority.
t "the scale prompt resolves the base from the remote itself" \
  "git ls-remote --symref origin HEAD" cat "$SCALE_PROMPT"
t "and fetches the resolved base, not the rendered one" \
  'git fetch origin "+refs/heads/$BASE:refs/remotes/origin/$BASE"' cat "$SCALE_PROMPT"
# THE GUARD IS STRUCTURAL, NOT PROSE. Three unconditional lines let an
# unresolved base sail through: the base fetch goes out with an empty refspec
# and the integration fetch/checkout still succeeds on its own, so the sequence
# exits 0 and the worker positions itself against an unverified base instead of
# parking. Everything below the resolution therefore hangs off one `&&` chain.
t "the base resolution gates the fetches structurally" \
  '[ -n "$BASE" ]' cat "$SCALE_PROMPT"
t "the base fetch is chained behind that gate" \
  '&& git fetch origin "+refs/heads/$BASE' cat "$SCALE_PROMPT"
t "and so is the integration fetch that follows it" \
  "&& git fetch origin epic/e9-integration" cat "$SCALE_PROMPT"
nt "the rendered base is never baked into the fetch" \
  "+refs/heads/main:refs/remotes/origin/main" cat "$SCALE_PROMPT"
nt "and never the bare form that may write no tracking ref" \
  "git fetch origin main" cat "$SCALE_PROMPT"
# THE ECHO IS NOT A FALLBACK. An ls-remote that cannot answer leaves the base
# unverifiable, which is precisely the wrong-range risk the resolution removes;
# the run parks rather than reviewing against a guess.
t "an unresolvable base parks instead of falling back" \
  'needs-human "scale review: could not resolve the repo default branch from origin"' \
  cat "$SCALE_PROMPT"
t "and the rendered binding is named as the echo it is" \
  "best-effort echo" cat "$SCALE_PROMPT"
# The binding still rides the prompt as context (and as MANIFEST_REF, the ref
# the two snapshots really came from).
t "the scale base binding still echoes the default branch" '`BASE_REF`: main' cat "$SCALE_PROMPT"
# THE EMPTY-REF PARK MUST NOT PRECEDE THE BINDING BARRIER. Parking and ending
# the turn unacknowledged makes the dispatcher's ack wait time out, retire the
# worker, and end the run abandoned UNDER AN ALREADY-PARKED TICKET — the one
# state no operator is told about. The check still precedes any fetch; only the
# action changes.
t "the empty-ref stop crosses the binding barrier before parking" \
  "Cross the BINDING BARRIER first" cat "$SCALE_PROMPT"
nt "the scale prompt carries no PR-resolution order" \
  "UNRESOLVED-resolve-from-the-PR" cat "$SCALE_PROMPT"
nt "the scale prompt never went out as mode api" \
  "resolving what that PR MERGES INTO" cat "$SCALE_PROMPT"
nt "nothing was left unrendered on the scale prompt" "{{" cat "$SCALE_PROMPT"

# =========================================================================
# Scenario 7 — the same split from the other side: a URL-shaped `pr` is a
# leaf's pull request (the entry-edge guard makes leaf `pr` values URLs), so
# the unchanged api PR variant renders.
# =========================================================================
PORT7="$(free_port)"
FIX7="$(mktemp)"; : > "$FIX7.log"
cat > "$FIX7" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":63,"ticketId":92,"fence":1,"bearer":"leaf-bearer",
          "body":"leaf assignment","pr":"https://github.com/o/r/pull/9",
          "branch":"feat/x","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/63/bind","status":200,"body":{"ok":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX7" "$PORT7" & MOCK7=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 2>/dev/null' EXIT
wait_for_port "$PORT7" || { echo "FAIL mock server never listened on $PORT7"; exit 1; }

r7="$(apirepo "$PORT7")"
DH7="$(mktemp -d)"
OUT7="$(mktemp)"
( cd "$r7" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH7" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r7" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT7" 2>&1 || true

LEAF_PROMPT="$DH7/prompt-92-api-qagent.md"
t "the URL dispatch reports its handoff" "claimed #92" cat "$OUT7"
t "a URL pr renders the api block" "resolving what that PR MERGES INTO" cat "$LEAF_PROMPT"
t  "the api mode is the one rendered" '`REVIEW_MODE`: api' cat "$LEAF_PROMPT"
nt "and a leaf is not the api-scale variant" '`REVIEW_MODE`: api-scale' cat "$LEAF_PROMPT"
nt "no scale framing reaches a leaf reviewer" "SCALE REVIEWER" cat "$LEAF_PROMPT"

# =========================================================================
# Scenario 8 — THE DEFAULT BRANCH IS A FACT, NOT A GUESS. In API mode there is
# no gh to ask, and an api-scale run PROMOTES the answer to BASE_REF: the ref
# the engine ranges the epic against and the ref both manifests are read from.
# A clone with no origin/HEAD (every `git clone --single-branch`, every
# worktree cut from one) used to fall straight through to the literal `main`,
# so a repo whose default branch is anything else got its epic reviewed — and
# closed — against a branch it does not merge into. The remote knows, and
# ls-remote asks it without gh.
# =========================================================================
UPSTREAM="$(mkrepo)"
git -C "$UPSTREAM" checkout -q -b trunk
git -C "$UPSTREAM" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$UPSTREAM" symbolic-ref HEAD refs/heads/trunk

PORT8="$(free_port)"
FIX8="$(mktemp)"; : > "$FIX8.log"
cat > "$FIX8" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":71,"ticketId":77,"fence":1,"bearer":"trunk-bearer",
          "body":"epic assignment","pr":"5150","branch":"epic/e7-integration",
          "parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/71/bind","status":200,"body":{"ok":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX8" "$PORT8" & MOCK8=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 2>/dev/null' EXIT
wait_for_port "$PORT8" || { echo "FAIL mock server never listened on $PORT8"; exit 1; }

r8="$(apirepo "$PORT8")"
# An origin that HAS a default branch, and a clone that has never learned it:
# no fetch, so refs/remotes/origin/HEAD does not exist locally.
git -C "$r8" remote add origin "$UPSTREAM"
[ -z "$(git -C "$r8" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null || true)" ] \
  || { echo "FAIL scenario 8 precondition: the clone already knows origin/HEAD"; exit 1; }
DH8="$(mktemp -d)"
OUT8="$(mktemp)"
( cd "$r8" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH8" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r8" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT8" 2>&1 || true

TRUNK_PROMPT="$DH8/prompt-77-api-qagent.md"
t "the dispatch ran" "claimed #77 run=71" cat "$OUT8"
t "the remote's default branch becomes the epic's base" '`BASE_REF`: trunk' cat "$TRUNK_PROMPT"
nt "the literal main guess never reaches the worker" '`BASE_REF`: main' cat "$TRUNK_PROMPT"
t "and the worker is still ordered to resolve the base for itself" \
  "git ls-remote --symref origin HEAD" cat "$TRUNK_PROMPT"
nt "so no rendered branch name is baked into the base fetch" \
  "+refs/heads/trunk:refs/remotes/origin/trunk" cat "$TRUNK_PROMPT"
t "the manifests are read from that same ref" '`MANIFEST_REF`: trunk' cat "$TRUNK_PROMPT"
nt "and none of it went through gh" "GH-CALLED" cat "$MARKER"

# =========================================================================
# Scenario 9 — AN EPIC CLAIM WITH NO INTEGRATION BRANCH STILL DISPATCHES, and
# its INTEGRATION_REF binding renders PRESENT AND EMPTY. This is the one place
# where an empty rendered value is the contract rather than a defect: the
# dispatcher deliberately does not refuse the spawn (refusing strands the
# ticket with no park note naming the gap), so the empty binding is what the
# api-scale block's own empty-ref check reads to park the epic itself, with a
# note. Now that an unsupplied placeholder hard-fails the render, that
# distinction lives one line away from the check — a later "reject empty
# values too" tightening would look obviously right, pass every other test,
# and silently convert a worker-parks-with-a-note into a stranded ticket.
# =========================================================================
PORT9="$(free_port)"
FIX9="$(mktemp)"; : > "$FIX9.log"
cat > "$FIX9" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":81,"ticketId":95,"fence":1,"bearer":"noref-bearer",
          "body":"branch-less epic assignment","pr":"5150","branch":null,
          "parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/81/bind","status":200,"body":{"ok":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX9" "$PORT9" & MOCK9=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 $MOCK9 2>/dev/null' EXIT
wait_for_port "$PORT9" || { echo "FAIL mock server never listened on $PORT9"; exit 1; }

r9="$(apirepo "$PORT9")"
DH9="$(mktemp -d)"
OUT9="$(mktemp)"
( cd "$r9" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH9" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r9" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    "$DISPATCH" --sweep ) > "$OUT9" 2>&1 || true

NOREF_PROMPT="$DH9/prompt-95-api-qagent.md"
binding_shape() {  # binding_shape <NAME> <prompt-file> — absent / empty / valued
  local v
  if ! grep -q "^- \`$1\`:" "$2"; then echo "LINE-ABSENT"; return; fi
  v="$(sed -n "s/^- \`$1\`: \{0,1\}\(.*\)\$/\1/p" "$2" | head -1)"
  [ -n "$v" ] && echo "PRESENT-WITH-VALUE" || echo "PRESENT-AND-EMPTY"
}
t "a branch-less epic claim still reaches a worker" "claimed #95 run=81" cat "$OUT9"
nt "the empty integration ref does not fail the render closed" \
  "unrendered placeholders" cat "$OUT9"
t "the api-scale variant is still the one rendered" \
  "SCALE REVIEWER of recomposition epic #95" cat "$NOREF_PROMPT"
t "the integration ref renders present and empty, not missing" \
  "PRESENT-AND-EMPTY" binding_shape INTEGRATION_REF "$NOREF_PROMPT"
t "and the WORKER is the party that parks it, with a note" \
  'needs-human "scale review: the claim carried no integration ref"' cat "$NOREF_PROMPT"

# =========================================================================
# Scenario 10 — ONE RECOVERY ATTEMPT PER TICKET PER TICK REACHES THIS PHASE
# TOO. The sweep's resume phase records every ticket it attempted a recovery
# for this tick; phase 4 hands that ledger across the same way it hands the
# suppression directory. Without it the review lane could claim the very
# ticket whose replay just faulted — a second attempt in the same tick, over
# the invariant the ledger exists to hold. The claim is how we learn WHICH
# ticket the server picked, so the refusal is a release, as suppression's is.
# =========================================================================
PORT10="$(free_port)"
FIX10="$(mktemp)"; : > "$FIX10.log"
cat > "$FIX10" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":71,"ticketId":33,"fence":1,"bearer":"tok-l","plan":null,
          "body":"ledgered review","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/71/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/71/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX10" "$PORT10" & MOCK10=$!
trap 'kill $MOCK $MOCK2 $MOCK3 $MOCK4 $MOCK5 $MOCK6 $MOCK7 $MOCK8 $MOCK9 $MOCK10 2>/dev/null' EXIT
wait_for_port "$PORT10" || { echo "FAIL mock server never listened on $PORT10"; exit 1; }

r10="$(apirepo "$PORT10")"
DH10="$(mktemp -d)"
LEDGER10="$(mktemp)"; echo 33 > "$LEDGER10"
OUT10="$(mktemp)"
( cd "$r10" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
    DAEMON_HOME="$DH10" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r10" \
    BOARD_CREDENTIALS_FILE="$CREDS" REVIEW_MAX_CONCURRENT=2 \
    REVIEW_ACK_POLLS=400 REVIEW_ACK_DELAY=0.02 \
    BOARD_RESUMED_LEDGER="$LEDGER10" \
    "$DISPATCH" --sweep ) > "$OUT10" 2>&1 || true

t  "a claim yielding a tick-ledgered ticket is released" \
   "#33 already had its one recovery attempt this tick"  cat "$OUT10"
t  "and that run is ended"          '"path": "/runs/71/end"'  cat "$FIX10.log"
nt "so no reviewer is spawned for it" "ARGS name=33"  \
   bash -c "cat '$DH10/spawn-capture.txt' 2>/dev/null || echo none"
journal10() { ls "$DH10/board-claims"/*.json >/dev/null 2>&1 && echo "journal kept" || echo "journal dropped"; }
t  "and the journal is dropped with it"  "journal dropped"  journal10

finish
