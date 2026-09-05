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
#      and a registration whose response was lost meets `duplicate` on every
#      retry, so the env-issue is recovered by title out of a COMPLETE walk;
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
# /runs/claim-successor entry must precede the /runs/claim default — and every
# `/tickets?limit=200&ids=` entry must precede a bare `/tickets?limit=200` one.
# The board reads here are PAGED: `_check_lift` asks `ids=`, `_escalate` asks
# by id, and the duplicate-recovery scan walks. Prefix matching makes the exact
# id list in an `ids=` request irrelevant to which fixture answers, so the tests
# that care assert the requested ids out of the .log.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":44,"ticketId":12,"fence":4,"bearer":"tok-s","predecessorRun":41,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"parentPin":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":121,"ticketId":12,"correlationId":"evt-9","replies":["go"]}]},
 {"method":"POST","path":"/answers/121/ack","status":200,"body":{"acked":true}},
 {"method":"POST","path":"/runs/44/bind","status":200,"body":{"bound":true}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":44}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":43,"ticketId":12,"fence":5,"bearer":"tok-t","predecessorRun":44,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"parentPin":{"parent_id":7,"parent_event_cursor":118},
          "body":"work on"}},
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
          "plan":null,"parentPin":{"parent_id":9,"parent_event_cursor":205},
          "body":"the assignment text a successor cannot reach any other way"}},
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
 {"method":"GET","path":"/tickets/12","status":404,"once":true,
  "body":{"error":{"code":"not-found","message":"no such ticket: 12"}}},
 {"method":"GET","path":"/tickets/12","status":404,"once":true,
  "body":{"error":{"code":"not-found","message":"no such ticket: 12"}}},
 {"method":"GET","path":"/tickets?limit=1","status":200,"once":true,
  "body":{"items":[{"id":13,"state":"in-progress","priority":"P2",
                    "title":"a board #12 is not on"}],"next":null,"as_of":118}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":48}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"runId":50,"ticketId":12,"fence":9,"bearer":"tok-s6","predecessorRun":48,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
          "plan":null,"body":"work on"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,"body":[]},
 {"method":"POST","path":"/runs/50/end","status":200,"body":{"ended":true}},
 {"method":"GET","path":"/tickets/12","status":200,"once":true,
  "body":{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}},
 {"method":"POST","path":"/tickets","status":200,"once":true,
  "body":{"id":90,"state":"needs-human"}},

 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,"once":true,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
                   {"id":90,"state":"needs-human","priority":null,"title":"stuck resume"}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":50}]},

 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":60,"ticketId":14,"fence":1,"bearer":"tok-x",
          "body":"a ticket the sweep already gave up on"}},
 {"method":"POST","path":"/runs/60/end","status":200,"body":{"ended":true}},

 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
                   {"id":13,"state":"done","priority":"P2","title":"the moved one"},
                   {"id":90,"state":"done","priority":null,"title":"stuck resume"},
                   {"id":91,"state":"needs-human","priority":null,"title":"stuck resume 2"}],
           "next":null,"as_of":118}},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"POST","path":"/runs/claim-successor","status":200,
  "body":{"runId":70,"ticketId":16,"fence":1,"bearer":"tok-arch","predecessorRun":69,
          "sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-arch"},
          "plan":null,"body":"the architect assignment"}},
 {"method":"POST","path":"/runs/70/bind","status":200,"body":{"bound":true}},
 {"method":"POST","path":"/runs/99/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

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
DS="$TDIR/sminos-stub"; mkdir -p "$DS"
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
# ONE stub executable whose first argument selects the verb. Its `resume` arm
# COPIES THE REGISTRY RECORD at the instant it runs. That copy is the only way
# to observe persist-before-resume: after the fact every ordering looks the same.
cat > "$DS/sminos" <<EOF
#!/usr/bin/env bash
verb="\${1:-}"; shift || true
case "\$verb" in
migrate) exit 0 ;;
retire)  echo "retire \$*"; exit 0 ;;
sync)
  # Liveness as \`sminos sync\` actually reports it: \`noop\` for an ALREADY-
  # TERMINAL record (it never re-inspects one), \`live\` for a running turn.
  # Driven off the record the way the real verb is, so a status the resume path
  # writes — notably the status=error + pending_short an unresolved fork leaves
  # — is visible to the sweep's own liveness read.
  python3 - "$DH/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
  exit 0 ;;
spawn)
  name="\$1"; task="\$2"; shift 2
  cwd=""; wt=""; model=""
  while [ \$# -gt 0 ]; do
    case "\$1" in
      --cwd) cwd="\$2"; shift 2 ;;
      --worktree) wt="\$2"; shift 2 ;;
      --model) model="\$2"; shift 2 ;;
      --wait|--no-wait) shift ;;
      *) shift ;;
    esac
  done
  { echo "SPAWN name=\$name cwd=\$cwd worktree=\$wt model=\$model"
    env | grep '^BOARD_' | sort || true
    echo "---- prompt ----"; printf '%s\n' "\$task"; echo "---- end prompt ----"; } >> "$SPAWN_LOG"
  [ -n "\${SPAWN_MUST_FAIL:-}" ] && exit 1
  python3 -c 'import json, sys
json.dump({"uuid": sys.argv[2], "current": sys.argv[2], "status": "working",
           "name": sys.argv[3]}, open(sys.argv[1], "w"))' \\
    "$DH/$NEWUUID.json" "$NEWUUID" "\$name"
  echo "seat spawned: \$name  [abc1234 / $NEWUUID]  group=test  status=working  (reply: sminos reply abc1234)"
  exit 0 ;;
resume) ;;
*) echo "stub sminos: unexpected verb '\$verb'" >&2; exit 2 ;;
esac
if [ "\${1:-}" = "--wait" ]; then shift; fi
cp "$DH/u-old.json" "$DH/meta-at-resume.json" 2>/dev/null || true
env | grep '^BOARD_' | sort > "$DH/resume-env.txt" || true
{ echo "RESUME uuid=\$1"
  echo "ARGV: \$*"
  echo "DAEMON_TIMEOUT=\${DAEMON_TIMEOUT:-unset}"; } >> "$RESUME_LOG"
# The residual double-spawn shape: the real resume LAUNCHED a fork but the uuid
# poll never yielded a usable session uuid, so it stamps status=error +
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
# The real resume forks the turn and INJECTS the prompt before it blocks, then
# exits 1 when its watcher bound expires. That is what a slow (i.e. ordinary)
# successor turn looks like from here.
[ -n "\${RESUME_WAIT_EXPIRES:-}" ] && exit 1
exit 0
EOF
chmod +x "$DS/sminos"

# The sweep's tick lock is keyed by BINDING, so a drill that plants or removes
# one has to name the same digest _sweep_api.sh computes:
# sha256("api:<url>|<repo>")[:16], url normalized the way the client's
# api_url() normalizes it. The same key names every per-board store under the
# registry root (_board_api.store_dir), and this is the independent mirror.
lock_key() {  # lock_key <repo-key>
  T_URL="http://127.0.0.1:$PORT" T_REPO="$1" python3 -c '
import hashlib, os
print(hashlib.sha256(("api:%s|%s" % (os.environ["T_URL"].rstrip("/"),
                                     os.environ["T_REPO"]))
                     .encode()).hexdigest()[:16])'
}
SW() {  # SW <phase> — one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
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
# A SUCCESSOR CLAIM IS A DISPATCH. The server resolves this route through the
# same dispatch rule /runs/claim uses, so an unscoped credential that names no
# repo is refused `repo-required` — and every reclaimed run would stick in the
# recovery loop rather than being handed to a successor. Naming the ticket is
# not naming the repo: the rule reads the credential and the request, not the
# row the ticket id points at.
t  "and the successor claim names its repo, as any dispatch must" \
  '\"repo\": \"testrepo\"' cat "$FIX.log"
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

# `sminos resume` forks a fresh process from the CALLER's env, so the successor
# credentials ride the invocation or the worker writes nothing.
t  "successor creds on resume env"         "BOARD_RUN_TOKEN=tok-s"     cat "$DH/resume-env.txt"
t  "with the successor run id"             "BOARD_RUN_ID=44"           cat "$DH/resume-env.txt"
t  "and its fence"                         "BOARD_RUN_FENCE=4"         cat "$DH/resume-env.txt"
# WHEREVER THE URL IS PINNED FOR A WORKER, THE REPO IS PINNED WITH IT. A worker
# checks out the head it was dispatched for, and a head predating the repo key
# carries a two-key board.json — so an unpinned sweep-driven turn dies on
# `binding=api but no repo`. The dispatcher pins it for the FIRST turn; without
# it here the worker loses the pin on every turn the sweep drives afterwards.
t  "and the repo the successor speaks for" "BOARD_REPO=testrepo"       cat "$DH/resume-env.txt"
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

# A NULL parentPin CARRIES NOTHING. This claim answered `"parentPin": null`
# (the ordinary shape for a run with no parent contract), so neither the meta
# key nor the prompt line may be invented — an empty pin rendered anyway reads
# as `#None @ event None` to the worker that acts on it.
nt "a null pin stamps no meta key"         '"parent_pin"'  cat "$DH/u-old.json"
nt "and adds no prompt line"               "Parent pin"    cat "$TRANSCRIPT"

# =========================================================================
# Phase 3, rung 2 — A BOUNDED WAIT IS NOT A FAILED DELIVERY. `sminos resume`
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
# THE PARENT PIN RIDES THE DELIVERY OR NOT AT ALL — no board read a worker may
# make hands the parent contract window over, so the claim's `parentPin` has to
# reach both the delivered meta and the orientation prompt. This is the
# RESUMED-SESSION leg: the stamp lands on the predecessor's own meta.
t  "the successor meta carries the flattened parent pin" \
   '"parent_pin": "#7 @ event 118"'                         cat "$DH/u-old.json"
t  "and the successor prompt carries the pin line" \
   "Parent pin (your run's parent-contract window): #7 @ event 118" cat "$TRANSCRIPT"

# =========================================================================
# Phase 3, rung 2b — AN AMBIGUOUS FORK IS NOT A FAILED DELIVERY EITHER.
# `sminos resume` can launch the fork and still exit 1 when the new session uuid
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
# is what "resolved" means to `sminos resume` and therefore to the sweep.
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
# WHEREVER THE URL IS PINNED FOR A WORKER, THE REPO IS PINNED WITH IT. A worker
# checks out the head it was dispatched for, and a head predating the repo key
# carries a two-key board.json — so an unpinned sweep-driven turn dies on
# `binding=api but no repo`. The dispatcher pins it for the FIRST turn; without
# it here the worker loses the pin on every turn the sweep drives afterwards.
t  "and the repo it speaks for"            "BOARD_REPO=testrepo"       cat "$SPAWN_LOG"
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
# ...and the FRESH-SPAWN leg, which _persist_successor never touches and
# board-bind writes no pin into: the one stamp point both legs share is the
# lane stamp, so the pin has to travel with it.
t  "the fresh worker's meta carries the parent pin too" \
   '"parent_pin": "#9 @ event 205"'                    cat "$DH/$NEWUUID.json"
t  "and the fresh bootstrap carries the pin line" \
   "Parent pin (your run's parent-contract window): #9 @ event 205" cat "$SPAWN_LOG"

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

# Cycle 3 reaches the escalation, but the by-id read answers not-found — the
# board has no such ticket, authoritatively (the client proves the paged
# surface with one probe before it believes that 404, or a rolled-back server
# answering 404 to an unknown ROUTE would read as "no ticket anywhere" — and
# then re-asks by id, since the probe dates the SURFACE and not the answer that
# preceded it, which is why this world carries two 404 fixtures for #12). The
# escalation defers all the same: a record written from that empty answer would
# say `"state": ""`, and the lift check — moved = current != recorded — then
# reads ANY value as movement, so the suppression would lift on the very next
# tick and the whole ladder would run again, spamming the human an env-issue
# every three cycles. An escalation that cannot name the state it froze does
# not happen at all; the counter stands and the next tick retries.
: > "$FIX.log"
OUT4B="$TDIR/resume4b.out"
RESUME_MUST_FAIL=1 SPAWN_MUST_FAIL=1 SW resume > "$OUT4B" 2>&1 || true
t  "cycle 3 is counted"                    "recovery cycle 3 of 3"     cat "$OUT4B"
t  "an escalation whose board state reads empty is refused" \
   "board state came back empty"                                       cat "$OUT4B"
t  "and it asked for that state by id"  '"path": "/tickets/12"'        cat "$FIX.log"
t  "probing the paged surface before believing the 404" \
   '"path": "/tickets?limit=1&repo=testrepo"'                                        cat "$FIX.log"
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
t  "phase 4 claims the executor lane"   '\"lane\": \"implementer\"' cat "$FIX.log"
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
mkdir "$DH/.sweep-api.$(lock_key testrepo).lock"
t  "a held lock skips the tick"  "holds the lock"  SW resume
nt "and sends nothing"           '"method"'        cat "$FIX.log"
rmdir "$DH/.sweep-api.$(lock_key testrepo).lock"

# =========================================================================
# THE PREDECESSOR'S LANE SURVIVES ITS RUN. By the time a ticket reaches this
# feed its predecessor's run is normally already RETIRED — the renew that
# answered 409 run-ended is what put it there — and _retire_run_locally strips
# run/bearer/fence while keeping ticket and lane. A lane read through the
# run-carrying registry scan therefore sees NO predecessor at all: every
# recovery fell back to a generic executor, so an architect's ticket got an
# executor's protocol on the executor's model. Here #16's predecessor is
# in exactly that shape: bound to the ticket, stamped `architect`, no run.
# =========================================================================
: > "$FIX.log"; : > "$SPAWN_LOG"
printf '%s\n' '{"uuid":"u-arch","current":"u-arch","status":"working",
 "lane":"architect","role":"ARCHITECT","ticket":"16","run_ended_at":"2026-08-09T00:00:00Z"}' \
 > "$DH/u-arch.json"
# Reached through reconciliation rather than the feed: a successor claim whose
# response was lost is replayed under its own nonce, and that replay runs the
# same recovery the feed does.
mkdir -p "$DH/board-claims"
printf '%s\n' '{"lane":"successor","run_id":null,"spawn_completed":false,"ticket":"16"}' \
  > "$DH/board-claims/n-lane.json"
OUTL="$TDIR/resume-lane.out"
RESUME_MUST_FAIL=1 SW resume > "$OUTL" 2>&1 || true
t  "the successor inherits a RETIRED predecessor's lane" \
   "SPAWN name=16-successor-architect"                  cat "$SPAWN_LOG"
t  "and that lane's own model"        "model=fable"     cat "$SPAWN_LOG"
t  "and that lane's own protocol"     "architecting/SKILL.md"  cat "$SPAWN_LOG"
t  "and that lane's own role"         "ARCHITECT."             cat "$SPAWN_LOG"
rm -f "$DH/u-arch.json" "$DH/board-claims/n-lane.json"

# =========================================================================
# A HISTORICAL DAEMON NAME IS NOT SPAWN PROOF, and successor names are
# deterministic per ticket and lane. `sminos retire` keeps the meta unless
# --purge, so a name left by an earlier recovery matched the new journal:
# reconciliation called the crash `orphaned`, closed the journal as complete,
# and left the run just claimed owning the ticket with nobody able to speak for
# it until the lease expired. Only a WORKING or BLOCKED session is evidence —
# the rule _claim_journal.sh already applies on the dispatchers' side.
#
# And beside it: a release that FAILS must keep its journal. It is the only
# retry handle there is; deleted, the run stays open, owns the ticket, and no
# later tick can retry — "retried next tick" was never true.
# =========================================================================
: > "$FIX.log"
printf '%s\n' '{"uuid":"u-hist","current":"u-hist","status":"idle",
 "name":"12-successor-retired"}' > "$DH/u-hist.json"
printf '%s\n' '{"lane":"successor","run_id":99,"spawn_completed":false,
 "ticket":"12","daemon":"12-successor-retired"}' > "$DH/board-claims/n-hist.json"
# No /runs/98/end fixture exists: the mock answers 404, which is what a
# transport or service outage looks like from here.
printf '%s\n' '{"lane":"successor","run_id":98,"spawn_completed":false,
 "ticket":"12"}' > "$DH/board-claims/n-fail.json"
OUTJ="$TDIR/resume-journal.out"
SW resume > "$OUTJ" 2>&1 || true
nt "a retired session's name is not read as a spawn" \
   "but never bound it"                                 cat "$OUTJ"
t  "so the undelivered run is released instead"  '"path": "/runs/99/end"' cat "$FIX.log"
journal_gone() { [ -e "$DH/board-claims/n-hist.json" ] && echo "journal kept" || echo "journal removed"; }
t  "and its journal is closed out"     "journal removed"  journal_gone
t  "a release that FAILED keeps its journal" \
   "the journal is KEPT so the next tick can retry"      cat "$OUTJ"
journal_kept() { [ -e "$DH/board-claims/n-fail.json" ] && echo "journal kept" || echo "journal removed"; }
t  "the retry handle survives on disk"  "journal kept"    journal_kept
rm -f "$DH/u-hist.json" "$DH/board-claims/n-fail.json"

# =========================================================================
# THE WHOLE-TICK BUDGET BOUNDS THE TICK, INCLUDING FRESH CLAIMS. Relay and
# resume stopped taking new items at the budget and then handed the tick to the
# dispatchers anyway — which claim fresh implement and review work, review
# barrier wait included, inside the same lock a spent tick is still holding.
# =========================================================================
: > "$FIX.log"
OUTB="$TDIR/budget.out"
BOARD_SWEEP_TICK_BUDGET=0 SW all > "$OUTB" 2>&1 || true
t  "an exhausted budget stops fresh dispatch" \
   "tick budget exhausted — fresh claims ride the next tick"  cat "$OUTB"
nt "so no fresh claim goes out"        '"path": "/runs/claim"' cat "$FIX.log"

# =========================================================================
# ...AND FROM THE INSIDE. The gate above is one check at the DOOR of the
# dispatch phase: a tick with a second left admitted both dispatchers in full,
# every lane loop and a review startup-barrier wait included, still holding the
# global lock. So the tick hands its own deadline across the process boundary
# and the dispatchers check it before each fresh claim (their half of that gate
# is pinned in test-dispatch-claim.sh). A phase asked for BY NAME is its own
# tick with its own clock and hands across nothing — which is what an empty
# value means to the dispatcher.
#
# Its own fixture world: by this point the script's board has spent the `once`
# grants a spawn needs, and the worker environment is where a variable crossing
# that boundary becomes observable.
# =========================================================================
DBOARD=""   # where deadline_board leaves the checkout it made
DMOCKS=""   # the mocks it started, to be killed once these two ticks are done
deadline_board() {  # deadline_board <port> <run-id> — one throwaway board
  # One `local` per name: bash 3.2 expands every word of a `local` statement
  # before applying any of them, so `local a=1 b=$a` leaves b empty (and, under
  # set -u, dies).
  local port="$1"
  local run="$2"
  local fix="$TDIR/fixd-$port.json"
  : > "$fix.log"
  DEADLINE_RUN="$run" python3 - "$fix" <<'PY'
import json, os, sys
run = int(os.environ["DEADLINE_RUN"])
json.dump([
  {"method": "POST", "path": "/runs/claim", "status": 200, "once": True,
   "body": {"runId": run, "ticketId": 66, "fence": 1, "bearer": "tok-d",
            "plan": None, "body": "deadline work", "parentPin": None}},
  {"method": "POST", "path": "/runs/claim", "status": 200,
   "body": {"claimed": False}},
  {"method": "POST", "path": "/runs/%d/bind" % run, "status": 200,
   "body": {"bound": True}},
], open(sys.argv[1], "w"))
PY
  python3 "$TESTS_DIR/mock-server.py" "$fix" "$port" &
  # Tracked so the pair can be torn down: a mock left running holds this
  # script's stdout open and a `| tail` at the call site never returns.
  DMOCKS="$DMOCKS $!"
  wait_for_port "$port" || { echo "FAIL mock server never listened on $port"; exit 1; }
  # Left in a global rather than echoed: mkrepo registers its directory for
  # cleanup in THIS shell, and a command substitution would do that in a
  # subshell nothing ever tidies.
  DBOARD="$(mkrepo)"
  mkdir -p "$DBOARD/.doperpowers"
  printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$port" > "$DBOARD/.doperpowers/board.json"
}
SWD() {  # SWD <repo> <registry> <phase>
  ( cd "$1" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$2" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
      LOCAL_REPO="$1" "$SCRIPTS/_sweep_api.sh" "$3" )
}
# The dispatcher's environment as the worker it spawns sees it — the only
# place a value crossing that process boundary becomes observable.
deadline_handed() {
  grep '^BOARD_TICK_DEADLINE=' "$SPAWN_LOG" | head -1 |
    python3 -c 'import sys, time
line = sys.stdin.read().rstrip("\n")
v = line.split("=", 1)[1] if "=" in line else "<absent>"
print("deadline=%s" % ("a future epoch" if v.isdigit() and int(v) > time.time()
                       else "[%s]" % v))'
}

deadline_board "$(free_port)" 77
DHA="$TDIR/dh-all"; mkdir -p "$DHA"
: > "$SPAWN_LOG"
SWD "$DBOARD" "$DHA" all > "$TDIR/deadline-all.out" 2>&1 || true
t  "an all tick hands its dispatchers a real deadline" \
   "deadline=a future epoch"  deadline_handed

deadline_board "$(free_port)" 78
DHN="$TDIR/dh-named"; mkdir -p "$DHN"
: > "$SPAWN_LOG"
SWD "$DBOARD" "$DHN" dispatch > "$TDIR/deadline-named.out" 2>&1 || true
t  "a phase asked for by name hands across none" \
   "deadline=[]"              deadline_handed
# shellcheck disable=SC2086  # DMOCKS is a deliberate word-split pid list
kill $DMOCKS 2>/dev/null || true

# =========================================================================
# BOARD_SUPPRESS_DIR IS THE OPERATOR'S. The header documents it as honored and
# both dispatchers already default-respect it at their _api_suppressed — but
# this phase overwrote it with the registry default, splitting one mechanism in
# two: the tick wrote suppression records where nobody read them, while the
# dispatchers read a directory nothing ever wrote to. The lift pass is the
# cheapest place to see which directory this phase is actually working in.
# =========================================================================
SUPD="$TDIR/operator-suppress"; mkdir -p "$SUPD"
# Env-issue 90 is `done` in this board's standing rows, so the lift fires on
# the closed-env-issue trigger without depending on any other scenario's
# leftovers. (An env-issue the board does not carry would NOT do: absent is
# unknown, not closed — see the absent-row scenarios at the end of this file.)
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$SUPD/12.json"
: > "$FIX.log"
OUTS="$TDIR/suppressdir.out"
( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
    DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
    BOARD_SUPPRESS_DIR="$SUPD" "$SCRIPTS/_sweep_api.sh" resume ) > "$OUTS" 2>&1 || true
t  "the configured directory is the one this phase reads" \
   "suppression lifted for #12"                           cat "$OUTS"
supd_record() { [ -e "$SUPD/12.json" ] && echo "still-there" || echo "gone"; }
t  "and the record it acted on was the operator's"  "gone"  supd_record

# =========================================================================
# A CLAIM FAILURE IS NOT ONE KIND OF EVENT. Both claim exits used to bypass
# the recovery counter, so a ticket whose claim errored churned forever — and
# the kept journal was re-classified `replay` next tick while the feed ALSO
# re-served the ticket: two claims and a leaked journal per tick.
#
# Counting every claim failure is the wrong fix, because arkho answers two
# typed 409s that mean THIS JOURNAL is obsolete, not that the substrate is
# sick: `nonce-consumed` (the predecessor's run ended, so replaying its nonce
# is doomed forever) and `stale-resume` (the ticket moved after the feed
# read). Those drop the journal uncharged and let the next tick re-serve the
# ticket on a fresh nonce. Everything else on that exit — transport death,
# 5xx, an untyped refusal — IS a fault: charged, journal kept.
#
# `claimed:false` stays uncharged on purpose: it is the server's backpressure,
# and a suppression written from it would remove a HEALTHY ticket from both
# the resume and the dispatch phase until a human closed an env-issue.
#
# Its own fixture world, with a fresh registry per scenario — a kept journal
# and the attempt counter must not leak from one scenario into the next.
# =========================================================================
CFIX="$TDIR/fix-claim.json"; : > "$CFIX.log"
cat > "$CFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,"once":true,
  "body":{"error":{"code":"internal","message":"boom"}}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":409,"once":true,
  "body":{"error":{"code":"nonce-consumed",
                   "message":"a nonce on an ended run is spent, not replayable"}}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":409,"once":true,
  "body":{"error":{"code":"stale-resume",
                   "message":"ticket moved since the feed read"}}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"once":true,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":200,"once":true,
  "body":{"claimed":false}},

 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]}
]
JSON
CPORT="$(free_port)"
python3 "$TESTS_DIR/mock-server.py" "$CFIX" "$CPORT" & CMOCK=$!
wait_for_port "$CPORT" || { echo "FAIL mock server never listened on $CPORT"; exit 1; }
CREPO="$(mkrepo)"; mkdir -p "$CREPO/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$CPORT" > "$CREPO/.doperpowers/board.json"
CSW() {  # CSW <registry> — one resume tick against the claim-failure board
  ( cd "$CREPO" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$1" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" resume )
}
journals() {  # journals <registry> — how many claim journals it is holding
  local n=0 f
  for f in "$1"/board-claims/*.json; do [ -e "$f" ] || continue; n=$((n + 1)); done
  echo "journals=$n"
}

CDHA="$TDIR/dh-claim-fault"; mkdir -p "$CDHA"
OUTCA="$TDIR/claim-fault.out"
CSW "$CDHA" > "$OUTCA" 2>&1 || true
t  "a claim that FAULTS charges a recovery cycle" "recovery cycle 1 of 3" cat "$OUTCA"
t  "and the journal is kept as the replay handle" "journals=1" journals "$CDHA"

CDHB="$TDIR/dh-claim-nonce"; mkdir -p "$CDHB"
OUTCB="$TDIR/claim-nonce.out"
CSW "$CDHB" > "$OUTCB" 2>&1 || true
t  "a nonce-consumed claim names the journal obsolete" \
   "journal is obsolete (nonce-consumed)"            cat "$OUTCB"
nt "and is not reported as a fault"    "successor claim failed"  cat "$OUTCB"
nt "so no recovery cycle is charged"   "recovery cycle"          cat "$OUTCB"
t  "the spent journal is dropped"      "journals=0"  journals "$CDHB"

CDHC="$TDIR/dh-claim-stale"; mkdir -p "$CDHC"
OUTCC="$TDIR/claim-stale.out"
CSW "$CDHC" > "$OUTCC" 2>&1 || true
t  "a stale-resume claim names the journal obsolete too" \
   "journal is obsolete (stale-resume)"              cat "$OUTCC"
nt "and is not reported as a fault either" "successor claim failed" cat "$OUTCC"
nt "so no recovery cycle is charged for it" "recovery cycle"        cat "$OUTCC"
t  "and that journal is dropped as well"   "journals=0"  journals "$CDHC"

CDHD="$TDIR/dh-claim-none"; mkdir -p "$CDHD"
OUTCD="$TDIR/claim-none.out"
CSW "$CDHD" > "$OUTCD" 2>&1 || true
t  "backpressure is a wait state, not a failure" \
   "the board granted no successor"                  cat "$OUTCD"
nt "it charges no recovery cycle"      "recovery cycle"  cat "$OUTCD"
t  "and leaves no journal behind"      "journals=0"  journals "$CDHD"
kill $CMOCK 2>/dev/null || true

# =========================================================================
# ONE RECOVERY ATTEMPT PER TICKET PER TICK, AND A SUPPRESSION THAT FREEZES
# THE JOURNAL TOO.
#
# A kept fault journal is re-classified `replay` by reconciliation while the
# feed ALSO re-serves the same ticket, so one ticket bought two successor
# claims, two charged cycles and a second journal every tick: the documented
# three-cycle ladder fired in two ticks and journals grew for as long as the
# fault lasted. Reconciliation now records the tickets it claimed for, and the
# feed loop skips them.
#
# Reconciliation also replayed straight THROUGH a suppression — spending the
# recovery the suppression exists to stop, and re-escalating every third cycle.
# Each re-escalation rewrote the suppression record with the state read seconds
# earlier in the SAME tick, so _check_lift's `moved` compared a state against
# itself and the "move the ticket" half of the escalation's own instructions
# could never lift anything. The journal is now left standing while suppressed,
# and the lift pass runs BEFORE reconciliation — which is also what keeps a
# suppression lifting mid-tick from stranding its journal: the just-lifted
# ticket replays its own nonce rather than the feed minting a fresh one beside
# it.
#
# Each scenario gets its own board and its own registry: a standing journal, an
# attempt counter and a suppression record all have to start from a known state.
# =========================================================================
RMOCKS=""
rboard() {  # rboard <fixtures-file> — a throwaway board; sets RREPO and RLOG
  local port; port="$(free_port)"
  RLOG="$1.log"; : > "$RLOG"
  python3 "$TESTS_DIR/mock-server.py" "$1" "$port" &
  RMOCKS="$RMOCKS $!"
  wait_for_port "$port" || { echo "FAIL mock server never listened on $port"; exit 1; }
  RREPO="$(mkrepo)"; mkdir -p "$RREPO/.doperpowers"
  printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$port" > "$RREPO/.doperpowers/board.json"
}
RSW() {  # RSW <registry> — one resume tick against the current rboard
  ( cd "$RREPO" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
      DAEMON_HOME="$1" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
      "$SCRIPTS/_sweep_api.sh" resume )
}
claims() {  # claims <log> — successor-claim POSTs that reached the wire
  echo "claims=$(grep -c '"path": "/runs/claim-successor"' "$1" || true)"
}
standing_journal() {  # standing_journal <registry> — which journals are on disk
  # A glob rather than `ls`: an EXISTING but empty directory makes ls print
  # nothing at all, which would pass an absence assertion by accident.
  local f n=0
  for f in "$1"/board-claims/*; do
    [ -e "$f" ] || continue
    basename "$f"; n=$((n + 1))
  done
  [ "$n" -gt 0 ] || echo "no journals"
}
mkjournal() {  # mkjournal <registry> <nonce> <ticket> — an unfinished claim
  mkdir -p "$1/board-claims"
  printf '{"lane":"successor","run_id":null,"spawn_completed":false,"ticket":"%s"}\n' \
    "$3" > "$1/board-claims/$2.json"
}

# ---- a standing journal AND the same ticket on the feed, one tick ---------
AFIX="$TDIR/fix-once.json"
cat > "$AFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"POST","path":"/tickets","status":200,"once":true,
  "body":{"id":93,"state":"needs-human"}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
                   {"id":93,"state":"needs-human","priority":null,
                    "title":"stuck resume: ticket #12 cannot be revived"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$AFIX"
ADH="$TDIR/dh-once"; mkdir -p "$ADH"
mkjournal "$ADH" n-standing 12
OUTO1="$TDIR/once-tick1.out"
RSW "$ADH" > "$OUTO1" 2>&1 || true
t  "a replayed journal and the feed are ONE attempt" "claims=1" claims "$RLOG"
t  "the ticket the replay already spent is skipped on the feed" \
   "already replayed this tick"                       cat "$OUTO1"
t  "so exactly one cycle is charged"   "recovery cycle 1 of 3"  cat "$OUTO1"
nt "not two"                           "recovery cycle 2 of 3"  cat "$OUTO1"
t  "and no second journal is minted"   "journals=1"  journals "$ADH"

OUTO2="$TDIR/once-tick2.out"
RSW "$ADH" > "$OUTO2" 2>&1 || true
t  "the ladder advances exactly one rung per tick" \
   "recovery cycle 2 of 3"                            cat "$OUTO2"
nt "and no rung beyond it"             "recovery cycle 3 of 3"  cat "$OUTO2"
nt "so the second tick escalates nothing"  "escalated #12"      cat "$OUTO2"
t  "and still holds one journal"       "journals=1"  journals "$ADH"

OUTO3="$TDIR/once-tick3.out"
RSW "$ADH" > "$OUTO3" 2>&1 || true
t  "the THIRD tick is the one that escalates" \
   "escalated #12 → env-issue #93 (suppressed)"        cat "$OUTO3"
t  "three ticks of a claim fault cost three claims"  "claims=3" claims "$RLOG"

# ---- the ticket MOVED: the lift must be able to see it -------------------
# Re-escalation rewrites the suppression record with the state read moments
# earlier, so a reconcile that runs first makes `moved` structurally unable to
# fire — the operator does exactly what the env-issue body says and nothing
# happens. The counter starts at 2 so this tick's single charge reaches the
# rung that re-escalates.
BFIX="$TDIR/fix-moved.json"
cat > "$BFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"POST","path":"/tickets","status":200,
  "body":{"id":90,"state":"needs-human"}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"state":"needs-human","priority":"P1","title":"the stuck one"}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"needs-human","priority":"P1","title":"the stuck one"},
                   {"id":90,"state":"needs-human","priority":null,
                    "title":"stuck resume: ticket #12 cannot be revived"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$BFIX"
BDH="$TDIR/dh-moved"; mkdir -p "$BDH/board-suppress"
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$BDH/board-suppress/12.json"
printf '2\n' > "$BDH/board-suppress/.attempts-12"
mkjournal "$BDH" n-moved 12
OUTM="$TDIR/moved.out"
RSW "$BDH" > "$OUTM" 2>&1 || true
t  "a suppression whose ticket moved lifts before any replay can rewrite it" \
   "suppression lifted for #12 — the ticket moved"     cat "$OUTM"

# ---- a suppressed ticket's journal is frozen too -------------------------
CFIX2="$TDIR/fix-frozen.json"
cat > "$CFIX2" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
                   {"id":90,"state":"needs-human","priority":null,"title":"stuck resume"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$CFIX2"
FDH="$TDIR/dh-frozen"; mkdir -p "$FDH/board-suppress"
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$FDH/board-suppress/12.json"
mkjournal "$FDH" n-frozen 12
OUTF="$TDIR/frozen.out"
RSW "$FDH" > "$OUTF" 2>&1 || true
t  "a suppressed ticket's journal is left where it is" \
   "the journal stands untouched"                      cat "$OUTF"
t  "and buys no successor claim"       "claims=0"    claims "$RLOG"
nt "and charges no recovery cycle"     "recovery cycle"  cat "$OUTF"
t  "the retry handle survives the suppression"  "n-frozen.json" \
   standing_journal "$FDH"

# ---- a suppression that lifts THIS tick replays its own journal ----------
DFIX="$TDIR/fix-lifting.json"
cat > "$DFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"},
                   {"id":90,"state":"done","priority":null,"title":"stuck resume"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$DFIX"
LDH="$TDIR/dh-lifting"; mkdir -p "$LDH/board-suppress"
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$LDH/board-suppress/12.json"
mkjournal "$LDH" n-lifted 12
OUTLF="$TDIR/lifting.out"
RSW "$LDH" > "$OUTLF" 2>&1 || true
t  "the suppression lifts on the closed env-issue" \
   "suppression lifted for #12 — the env-issue closed" cat "$OUTLF"
t  "and the just-lifted ticket costs exactly one claim" "claims=1" claims "$RLOG"
t  "which carries the STANDING journal's nonce, not a fresh one" \
   '\"dispatchNonce\": \"n-lifted\"'                   cat "$RLOG"
t  "so no second journal is stranded beside it"  "journals=1"  journals "$LDH"
t  "and the one on disk is still the original"   "n-lifted.json" \
   standing_journal "$LDH"

# ---- two standing journals for ONE ticket are still one attempt ----------
# The ledger closed the reconcile→feed door; this is the reconcile→reconcile
# one. Reconciliation walks a row per journal file, so two unfinished successor
# journals naming the same ticket were two claims and two ladder rungs inside a
# single tick — the very shape this task exists to close. Not a steady state
# (a replay reuses its own nonce and overwrites its own file), but the
# intermediate commit on this branch minted an extra journal per tick during a
# claim fault, so a registry that ticked on it arrives holding several and this
# pass must not charge through them.
EFIX="$TDIR/fix-twojournals.json"
cat > "$EFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$EFIX"
TDH="$TDIR/dh-two-journals"; mkdir -p "$TDH"
mkjournal "$TDH" n-a 12
mkjournal "$TDH" n-b 12
OUTT="$TDIR/two-journals.out"
RSW "$TDH" > "$OUTT" 2>&1 || true
t  "a second journal for the same ticket waits its turn" \
   "#12 already had its one recovery attempt this tick"  cat "$OUTT"
t  "so two journals still cost one claim"  "claims=1"  claims "$RLOG"
t  "and one ladder rung"               "recovery cycle 1 of 3"  cat "$OUTT"
nt "not two"                           "recovery cycle 2 of 3"  cat "$OUTT"
t  "the waiting journal is left untouched"  "n-b.json"  standing_journal "$TDH"

# ---- AN ABSENT ROW IS NOT A STATE ----------------------------------------
# The lift check reads the two rows the record names BY ID (`ids=`), so absence
# in a completed answer is authoritative and the hazard this guard was written
# against — a truncated whole-board listing lifting every suppression it could
# not see — is gone. The rule stands on the absence that is left: the board has
# no delete path, so a record naming an id the board does not carry is a record
# from a corrupt registry or a foreign board. Reading that missing row as a
# value would still fire BOTH lift triggers on it — `moved` because None is not
# the recorded state, `closed` because None sat in the closed tuple — re-running
# the whole ladder and minting the human a fresh env-issue every three cycles.
# Absent is UNKNOWN on both sides, and the suppression keeps waiting.
suppression_present() {  # suppression_present <registry> <ticket>
  if [ -e "$1/board-suppress/$2.json" ]; then echo "still-there"; else echo "gone"; fi
}
tick_exit() {  # tick_exit <registry> <out> — run a tick, record its exit status
  if RSW "$1" > "$2" 2>&1; then echo "tick exit=0" >> "$2"
  else echo "tick exit=$?" >> "$2"; fi
}

GFIX="$TDIR/fix-absent-ticket.json"
cat > "$GFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":90,"state":"needs-human","priority":null,"title":"stuck resume"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$GFIX"
GDH="$TDIR/dh-absent-ticket"; mkdir -p "$GDH/board-suppress"
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$GDH/board-suppress/12.json"
OUTG="$TDIR/absent-ticket.out"
tick_exit "$GDH" "$OUTG"
t  "a suppression whose ticket the board does not carry is not lifted" \
   "still-there"                        suppression_present "$GDH" 12
nt "and the tick says nothing about lifting it"  "suppression lifted"  cat "$OUTG"
t  "and the tick still succeeds"        "tick exit=0"                 cat "$OUTG"
# Prefix matching answers any `ids=` request from that one fixture, so the
# REQUEST is where the targeting is visible: both ids the record names, and no
# whole-board read beside them. The trailing quote is the delimiter — a bare
# `ids=12,90` would also be satisfied by `ids=12,900`.
asked_ids() { grep -o '"path": "/tickets?[^"]*"' "$1" || echo "no /tickets read"; }
t  "and it asked for exactly the two ids the record names" \
   '"path": "/tickets?limit=200&ids=12,90&repo=testrepo"'   asked_ids "$RLOG"
reads() { echo "ticket-reads=[$(grep -c '"path": "/tickets' "$1" || true)]"; }
t  "in one targeted read, with no whole-board listing beside it" \
   "ticket-reads=[1]"                   reads "$RLOG"

# The env-issue half of the same read. `closed` alone must not fire on absence:
# an env-issue nobody can see is not an env-issue somebody closed.
HFIX="$TDIR/fix-absent-env.json"
cat > "$HFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$HFIX"
HDH="$TDIR/dh-absent-env"; mkdir -p "$HDH/board-suppress"
printf '%s\n' '{"ticket": 12, "state": "in-progress", "env_issue": 90}' \
  > "$HDH/board-suppress/12.json"
OUTH="$TDIR/absent-env.out"
tick_exit "$HDH" "$OUTH"
t  "an env-issue the board does not carry is not a closed env-issue" \
   "still-there"                        suppression_present "$HDH" 12
nt "so nothing is lifted on it"         "suppression lifted"          cat "$OUTH"
t  "and that tick succeeds too"         "tick exit=0"                 cat "$OUTH"
# ---- THE TICK LEDGER REACHES PHASE 4 -------------------------------------
# One recovery attempt per ticket per tick is an invariant of the TICK, not of
# phase 3. The ledger travelled no further than phase_resume, so after a replay
# FAULT left the ticket unowned an ordinary lane claim could pick that same
# ticket seconds later — a second attempt inside the tick the ledger exists to
# hold to one. It rides to the dispatchers exactly as BOARD_SUPPRESS_DIR does.
IFIX="$TDIR/fix-ledger-dispatch.json"
cat > "$IFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":70,"ticketId":12,"fence":1,"bearer":"tok-x","plan":null,
          "body":"work on","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/70/end","status":200,"body":{"ended":true}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$IFIX"
IDH="$TDIR/dh-ledger-dispatch"; mkdir -p "$IDH"
mkjournal "$IDH" n-led 12
OUTI="$TDIR/ledger-dispatch.out"
( cd "$RREPO" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
    DAEMON_HOME="$IDH" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
    "$SCRIPTS/_sweep_api.sh" all ) > "$OUTI" 2>&1 || true
t  "phase 3 spends the ticket's one attempt on the replay" \
   "replaying it for #12"                                  cat "$OUTI"
t  "and phase 4 refuses the same ticket on the same tick" \
   "#12 already had its one recovery attempt this tick"    cat "$OUTI"
t  "releasing the run it was handed"   '"path": "/runs/70/end"'  cat "$RLOG"
nt "so nothing is spawned for it"      "SPAWN name=12"           cat "$SPAWN_LOG"

# ---- ...AND THE FEED PATH IS AN ATTEMPT TOO ------------------------------
# The ledger recorded only the tickets reconciliation replayed for. A ticket
# served by the ORDINARY feed whose recovery then faulted (or released) is
# equally unowned and equally spent, and phase 4 could claim and spawn it in
# the same tick — the same double attempt through the other door.
JFIX="$TDIR/fix-ledger-feed.json"
cat > "$JFIX" <<'JSON'
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":13,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":72,"ticketId":13,"fence":1,"bearer":"tok-y","plan":null,
          "body":"work on","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/72/end","status":200,"body":{"ended":true}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[{"id":13,"state":"in-progress","priority":"P1","title":"the stuck one"}],
          "next":null,"as_of":118}}
]
JSON
rboard "$JFIX"
JDH="$TDIR/dh-ledger-feed"; mkdir -p "$JDH"
OUTJL="$TDIR/ledger-feed.out"
( cd "$RREPO" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" HOME="$TESTHOME" \
    DAEMON_HOME="$JDH" SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
    "$SCRIPTS/_sweep_api.sh" all ) > "$OUTJL" 2>&1 || true
t  "the feed spends the ticket's one attempt as surely as a replay" \
   "recovery cycle 1 of 3"                                 cat "$OUTJL"
t  "and phase 4 refuses the same ticket on the same tick" \
   "#13 already had its one recovery attempt this tick"    cat "$OUTJL"
t  "releasing the run it was handed"   '"path": "/runs/72/end"'  cat "$RLOG"
nt "so nothing is spawned for it"      "SPAWN name=13"           cat "$SPAWN_LOG"

# ---- A DUPLICATE REFUSAL IS THE ESCALATION, AND FINDING IT WALKS ---------
# The registration is not atomic with the suppression record it authorizes: A1
# can commit the env-issue and the response still be lost, after which every
# retry meets the server's dedup on this deterministic title — `409 duplicate`
# forever, no suppression record ever written, and the ticket escalating again
# every three cycles for as long as it lives. The refusal names the existing
# ticket, so the env-issue is read back out of it by TITLE, and that scan is
# the one production caller of the multi-page cursor walk: an env-issue filed
# days ago sits behind whatever the board has accumulated since, so a scan that
# reads only the first page finds nothing and raises.
#
# The page-1 decoy is a SUPERSTRING of the deterministic title: a scan matching
# on containment rather than equality answers #88 off page 1 and never asks for
# page 2 at all. The counter starts at 2 so this tick's single charge lands on
# the rung that escalates.
KC="WyJQMSIsIjIwMjYtMDgtMTggMDQ6MTU6MDkuMjQ2ODEwKzAwIiwiMTIiXQ"
KFIX="$TDIR/fix-dup-walk.json"
cat > "$KFIX" <<JSON
[
 {"method":"GET","path":"/runs/needing-resume","status":200,
  "body":[{"ticketId":12,"state":"in-progress","predecessorRunId":41}]},
 {"method":"POST","path":"/runs/claim-successor","status":500,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"state":"in-progress","priority":"P1","title":"the stuck one"}},
 {"method":"POST","path":"/tickets","status":409,
  "body":{"error":{"code":"duplicate","message":"existing ticket 94"}}},
 {"method":"GET","path":"/tickets?limit=200&repo=testrepo&cursor=$KC","status":200,
  "body":{"items":[{"id":94,"state":"needs-human","priority":null,
                    "title":"stuck resume: ticket #12 cannot be revived"}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[{"id":88,"state":"needs-human","priority":null,
                    "title":"stuck resume: ticket #12 cannot be revived (superseded)"}],
          "next":"$KC","as_of":118}}
]
JSON
rboard "$KFIX"
KDH="$TDIR/dh-dup-walk"; mkdir -p "$KDH/board-suppress"
printf '2\n' > "$KDH/board-suppress/.attempts-12"
OUTK="$TDIR/dup-walk.out"
RSW "$KDH" > "$OUTK" 2>&1 || true
t  "a lost registration's duplicate refusal still escalates" \
   "escalated #12 → env-issue #94 (suppressed)"        cat "$OUTK"
t  "the suppression names the env-issue the walk found on PAGE 2" \
   '"env_issue": 94'                cat "$KDH/board-suppress/12.json"
nt "not the page-1 row whose title merely CONTAINS the real one" \
   '"env_issue": 88'                cat "$KDH/board-suppress/12.json"
# The trailing quote is the delimiter: without it the first-page assertion is
# also satisfied by the cursor request, and both pages would collapse into one.
t  "the scan read the first page"       '"path": "/tickets?limit=200&repo=testrepo"'  cat "$RLOG"
t  "and asked for the second carrying the cursor verbatim" \
   "\"path\": \"/tickets?limit=200&repo=testrepo&cursor=$KC\""       cat "$RLOG"

# shellcheck disable=SC2086  # RMOCKS is a deliberate word-split pid list
kill $RMOCKS 2>/dev/null || true

finish
