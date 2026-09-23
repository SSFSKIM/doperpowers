#!/usr/bin/env bash
# test-sweep-review-recover.sh — _sweep_api.sh phase 1c, the owner whose review
# stopped.
#
# THE STATE THIS PHASE EXISTS FOR: the seat that opened the PR owns its review
# — it dispatches ONE qa-loop agent and ends its turn. While that agent runs
# the seat is busy in the harness's eyes; when the agent dies, or returns an
# escalation into a session nobody wakes, the seat goes idle with the ticket
# still `in-review` and its run still open. Renewal keeps the lease fresh, the
# harness-error ladder sees ordinary prose, and no other phase owns it.
#
# THE SELECTOR pins: the candidate is a seat whose meta says `phase: review`,
# live, idle, and silent past BOARD_REVIEW_STALL_MIN — and the meta is only a
# CANDIDATE FILTER. The ticket itself is the authority, because a local
# `review` outlives the review whenever the server parked the ticket by itself
# (the convergence transmute, the reconciler's dependency-stall park): no
# client transition ran, so nothing restamped the seat. A `needs-human` ticket
# repairs the mark to `review-parked` and is left alone; any other state clears
# the mark; only `in-review` is nudged.
#
# THE LADDER pins the rest: it is bounded by the REVIEW's progress, not the
# seat's. A review that is moving records a `review-trail` event at every
# round's end, so a count above the one the seat last saw resets it; three
# nudges with no new event park the ticket for a human.
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

# ---- the wire ---------------------------------------------------------------
# The mock matches by method + path PREFIX, first match wins, so every
# `/tickets/<n>/timeline` entry is registered AHEAD of its `/tickets/<n>` row.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/tickets/60/timeline","status":200,"body":{"records":[
   {"source":"board","cursor":1,"kind":"transition","body":{"note":"opened"}}]}},
 {"method":"GET","path":"/tickets/64/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/65/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/66/timeline","status":200,"body":{"records":[
   {"source":"board","cursor":1,"kind":"transition","body":{"note":"opened"}},
   {"source":"board","cursor":2,"kind":"review-trail","body":{"text":"round 1 — level medium"}}]}},
 {"method":"GET","path":"/tickets/67/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/68/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/70/timeline","status":200,"body":{"records":[
   {"source":"board","cursor":1,"kind":"review-trail","body":{"text":"round 1 — level medium"}}]}},
 {"method":"GET","path":"/tickets/71/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/60","status":200,
  "body":{"id":60,"state":"in-review","priority":"P1","title":"the stalled review"}},
 {"method":"GET","path":"/tickets/64","status":200,
  "body":{"id":64,"state":"needs-human","priority":"P1","title":"parked by the server"}},
 {"method":"GET","path":"/tickets/65","status":200,
  "body":{"id":65,"state":"done","priority":"P1","title":"landed while the mark stood"}},
 {"method":"GET","path":"/tickets/66","status":200,
  "body":{"id":66,"state":"in-review","priority":"P1","title":"a review that moved"}},
 {"method":"GET","path":"/tickets/67","status":200,
  "body":{"id":67,"state":"in-review","priority":"P1","title":"a review that never moved"}},
 {"method":"GET","path":"/tickets/68","status":200,
  "body":{"id":68,"state":"in-review","priority":"P1","title":"a review still running"}},
 {"method":"GET","path":"/tickets/70","status":200,
  "body":{"id":70,"state":"in-review","priority":"P1","title":"a review whose reset will not persist"}},
 {"method":"GET","path":"/tickets/71","status":200,"once":true,
  "body":{"id":71,"state":"needs-human","priority":"P1","title":"parked, and answered mid-repair"}},
 {"method":"GET","path":"/tickets/71","status":200,
  "body":{"id":71,"state":"in-review","priority":"P1","title":"parked, and answered mid-repair"}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":69,"state":"in-review","priority":"P1","title":"the suppressed one"},
                   {"id":99,"state":"needs-human","priority":null,"title":"env issue for #69"}],
          "next":null,"as_of":1}},
 {"method":"GET","path":"/tickets/72/timeline","status":200,"body":{"records":[]}},
 {"method":"GET","path":"/tickets/72","status":200,
  "body":{"id":72,"state":"in-review","priority":"P1","title":"the whole tick's candidate"}},
 {"method":"POST","path":"/runs/72/renew","status":200,"body":{"renewed":true}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"body":[]},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]},
 {"method":"POST","path":"/tickets/67/transition","status":200,
  "body":{"to":"needs-human","converged":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
# The mock is REAPED inside the trap, with the reap's own output swallowed:
# a background job killed by a signal and reaped at shell exit makes bash print
# `Terminated: 15` AFTER the suite's verdict line, which reads like a failure.
trap 'kill $MOCK 2>/dev/null; { wait $MOCK; } 2>/dev/null || true; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

# ---- the registry -----------------------------------------------------------
DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/sminos-stub"; mkdir -p "$DS"
NUDGES="$TDIR/nudges.log"; : > "$NUDGES"
TESTHOME="$TDIR/home"; mkdir -p "$TESTHOME/.claude/projects/proj"

meta() { printf '%s\n' "$2" > "$DH/$1.json"; chmod 600 "$DH/$1.json"; }
# The turn-end clock this phase reads: the seat's own transcript.
stale() { touch "$TESTHOME/.claude/projects/proj/$1.jsonl"
          touch -t 202607170000 "$TESTHOME/.claude/projects/proj/$1.jsonl"; }
fresh() { touch "$TESTHOME/.claude/projects/proj/$1.jsonl"; }

# THE SUBJECT: idle, alive, holding run 61 on a ticket still in review, and
# silent since long before the threshold.
meta u-rev '{"uuid":"u-rev","current":"u-rev","status":"idle","run_id":61,
             "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"60",
             "run_bearer":"tok-61","phase":"review"}'
stale u-rev

# Mid-turn. Its QA agent is running and the seat is busy; nothing may touch it.
meta u-work '{"uuid":"u-work","current":"u-work","status":"working","run_id":62,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"62",
              "run_bearer":"tok-62","phase":"review"}'
stale u-work

# Already parked out of its review: the park owns the ticket and the human owns
# the park. A parked owner is never a candidate again until it is answered.
meta u-parked '{"uuid":"u-parked","current":"u-parked","status":"idle","run_id":63,
                "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"63",
                "run_bearer":"tok-63","phase":"review-parked"}'
stale u-parked

# THE STALE MARK, both directions. The seat still says `review` because no
# client transition stamped it — the SERVER parked #64 itself and #65 reached
# `done` some other way. Nudging either would wake a worker onto a ticket that
# is no longer in review at all.
meta u-server-park '{"uuid":"u-server-park","current":"u-server-park","status":"idle",
                     "run_id":64,"fence":1,"lane":"implementer","bind_confirmed":true,
                     "ticket":"64","run_bearer":"tok-64","phase":"review"}'
stale u-server-park
meta u-done '{"uuid":"u-done","current":"u-done","status":"idle","run_id":65,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"65",
              "run_bearer":"tok-65","phase":"review"}'
stale u-done

# Two nudges spent, and the review has posted a round since: the count starts
# over rather than running out on a review that is working.
meta u-trail '{"uuid":"u-trail","current":"u-trail","status":"idle","run_id":66,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"66",
               "run_bearer":"tok-66","phase":"review","review_recoveries":"2",
               "review_trail_seen":"0"}'
stale u-trail

# Three nudges, no new trail event between them: the review is not moving.
meta u-cap '{"uuid":"u-cap","current":"u-cap","status":"idle","run_id":67,
             "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"67",
             "run_bearer":"tok-67","phase":"review","review_recoveries":"3",
             "review_trail_seen":"0"}'
stale u-cap

# Its ticket is SUPPRESSED: a human already holds an env-issue saying the
# substrate under this ticket is broken, and no more recovery is spent here
# until they clear it — this ladder included.
meta u-supp '{"uuid":"u-supp","current":"u-supp","status":"idle","run_id":69,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"69",
              "run_bearer":"tok-69","phase":"review"}'
stale u-supp
SUPD="$TDIR/suppress"; mkdir -p "$SUPD"
# The documented record shape — `_check_lift` reads `env_issue`, and the whole
# tick walks these records, so an invented shape dies there rather than here.
printf '{"ticket":69,"state":"in-review","env_issue":99}' > "$SUPD/69.json"

# THE RESET THAT DID NOT PERSIST. The timeline records a round this seat has
# not seen, so the count starts over — but the write recording that fails, and
# the count in hand (3) says the opposite of what was just observed. Parking on
# it would park a review that had just posted a round. The injection is a
# crashed tick's leftover: a DIRECTORY where the meta writer puts its tmp file,
# which no *.json scan sees and every write trips over.
meta u-block '{"uuid":"u-block","current":"u-block","status":"idle","run_id":70,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"70",
               "run_bearer":"tok-70","phase":"review","review_recoveries":"3",
               "review_trail_seen":"0"}'
stale u-block
mkdir -p "$DH/u-block.json.tmp"

# THE ANSWER LANDING MID-REPAIR. #71 reads needs-human when the decision is
# made and in-review when the repair re-reads it under the lock — the exact
# interleaving a park answered by board-answer produces, and the one where a
# blind write would overwrite the answer's own `review` stamp with
# `review-parked`, excluding the seat from this ladder for good.
meta u-race '{"uuid":"u-race","current":"u-race","status":"idle","run_id":71,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"71",
              "run_bearer":"tok-71","phase":"review"}'
stale u-race

# Idle between agent rounds, but it wrote moments ago — inside the threshold,
# which is what tells a pause from a stall.
meta u-fresh '{"uuid":"u-fresh","current":"u-fresh","status":"idle","run_id":68,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"68",
               "run_bearer":"tok-68","phase":"review"}'
fresh u-fresh

cat > "$DS/sminos" <<EOF
#!/usr/bin/env bash
verb="\${1:-}"; shift || true
case "\$verb" in
migrate) exit 0 ;;
sync)
  # As the real verb reports it: \`noop\` for an ALREADY-TERMINAL record (idle),
  # \`live\` for a running turn. Driven off the record, so a status this phase
  # writes is visible here.
  # The registry the TICK is pointed at, not a baked one: the whole-tick drill
  # below runs against a second DAEMON_HOME, and a stub that always read the
  # first would answer \`absent\` for its seat.
  python3 - "\${DAEMON_HOME:-$DH}/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
  exit 0 ;;
resume|wake)
  # Records the VERB, and its ENVIRONMENT as well as its argv: the run
  # credentials ride the nudge that way and are observable nowhere else.
  w=""; [ "\${1:-}" != "--wait" ] || { w=" --wait"; shift; }
  { echo "\$(printf %s "\$verb" | tr a-z A-Z) uuid=\$1"
    echo "VERB: \$verb\$w"
    [ "\${3:-}" != "--from" ] || echo "FROM: \${4:-}"
    echo "PROMPT: \$2"
    env | grep '^BOARD_RUN_' | sort || true; } >> "\${NUDGE_LOG:-$NUDGES}"
  exit 0 ;;
*) echo "stub sminos: unexpected verb '\$verb'" >&2; exit 2 ;;
esac
EOF
chmod +x "$DS/sminos"

SW() {  # one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
      BOARD_SUPPRESS_DIR="$SUPD" BOARD_CREDENTIALS_FILE="$CREDS" "$@" )
}
RECOVER() { SW "${@:2}" "$SCRIPTS/_sweep_api.sh" review-recover > "$1" 2>&1 || true; }

wakes()       { grep -c '^WAKE uuid=' "$NUDGES" || true; }
wakes_for()   { grep -c "^WAKE uuid=$1\$" "$NUDGES" || true; }
# The value, BRACKETED. `t` is a substring match, so a bare `review` needle is
# satisfied by `review-parked` — which is precisely the two values the repair
# drills have to tell apart.
mfieldq()     { printf '[%s]\n' "$(mfield "$1" "$2")"; }
mfield()      { python3 -c 'import json,sys
m = json.load(open(sys.argv[1]))
print(m.get(sys.argv[2], "<absent>"))' "$DH/$1.json" "$2"; }
posts()       { grep -c "\"path\": \"$1\"" "$FIX.log" || true; }

# =========================================================================
# One pass over the whole registry.
# =========================================================================
O1="$TDIR/t1.out"; RECOVER "$O1"

t  "idle owner with phase review and stale transcript → woken" "WAKE uuid=u-rev" cat "$NUDGES"
# The candidate is IDLE by this phase's own predicate — a live seat whose turn
# ended. `sminos resume` on it has no turn to stop and the harness starts a
# copy; `wake` delivers over the seat's socket (and resumes a dead one itself).
t  "...by wake --wait"                           "VERB: wake --wait"        cat "$NUDGES"
nt "...never by resume"                          "VERB: resume"             cat "$NUDGES"
t  "...signed by the sweep"                      "FROM: sweep"              cat "$NUDGES"
t  "the nudge names the review, not the build"  "SWEEP RECOVERY: your review of ticket #60's pull request has no live QA agent" cat "$NUDGES"
t  "...and says what to do when no review is running" "dispatch doperpowers:qa-loop again per your protocol's Closing Artifact" cat "$NUDGES"
t  "...and what to do when one already finished" "if the review already reached a park or a verdict, restate it" cat "$NUDGES"
t  "the nudge carries the run's OWN bearer"      "BOARD_RUN_TOKEN=tok-61"   cat "$NUDGES"
t  "the attempt is counted in its own key"       "1"                        mfield u-rev review_recoveries
t  "and the tick says what it did"               "review-recover: #60"      cat "$O1"

t  "working owner → untouched"                   "0"                        wakes_for u-work
t  "...and its count is never opened"            "<absent>"                 mfield u-work review_recoveries
t  "phase review-parked → untouched"             "0"                        wakes_for u-parked
t  "an owner still writing is inside the threshold" "0"                     wakes_for u-fresh

# THE TICKET IS THE AUTHORITY, not the seat's mark.
t  "server-parked: ticket needs-human with phase review → no nudge" "0"     wakes_for u-server-park
t  "...and the meta is restamped review-parked"  "[review-parked]"          mfieldq u-server-park phase
t  "...and the tick says the board parked it"    "#64"                      cat "$O1"
t  "ticket done with phase review → no nudge"    "0"                        wakes_for u-done
t  "...and the stale phase is removed"           "[<absent>]"               mfieldq u-done phase

# Progress is a review artifact, not seat activity.
t  "a new review-trail event resets the count"   "WAKE uuid=u-trail"        cat "$NUDGES"
t  "...so the attempt counts from zero again"    "1"                        mfield u-trail review_recoveries
t  "...and the trail it reset on is recorded"    "1"                        mfield u-trail review_trail_seen

# The cap.
t  "cap → POST /tickets/<id>/transition to needs-human" "/tickets/67/transition" cat "$FIX.log"
t  "...as a park"                                '\"to\": \"needs-human\"' cat "$FIX.log"
t  "...naming the exhausted ladder"              "needs-human"              cat "$O1"
t  "...and the owner is not nudged again"        "0"                        wakes_for u-cap
t  "...and the park leaves the seat review-parked" "[review-parked]"        mfieldq u-cap phase

# The reset that did not persist: nothing is spent on that candidate at all.
t  "a reset that failed to persist nudges nobody"  "0"                      wakes_for u-block
nt "...and parks nobody either, though the count in hand is at the cap" "/tickets/70/transition" cat "$FIX.log"
t  "...leaving the ladder exactly where it was"  "3"                        mfield u-block review_recoveries
t  "...and the tick says so"                     "the meta write failed"    cat "$O1"

# The answer landing mid-repair: the repair re-reads under the lock and writes
# nothing, so the stamp board-answer just made is the one that stands.
t  "a ticket answered mid-repair keeps the answer's mark" "[review]"        mfieldq u-race phase
t  "...and the tick says the ticket moved under it" "left needs-human while its seat's mark was being repaired" cat "$O1"
nt "...and nothing was nudged on that pass"      "WAKE uuid=u-race"         cat "$O1"

t  "a suppressed ticket freezes this ladder too"  "0"                       wakes_for u-supp
t  "...and the tick says why"                     "suppressed"               cat "$O1"
nt "...without reading the ticket at all"         "/tickets/69"              cat "$FIX.log"

t  "exactly two owners were nudged"              "2"                        wakes

# =========================================================================
# Idempotence — a second pass with nothing changed. The ladder advances by
# one per tick and nothing else moves; the repaired marks stay repaired.
# =========================================================================
O2="$TDIR/t2.out"; RECOVER "$O2"
t  "a second tick nudges the same owner once more" "2"                      wakes_for u-rev
t  "and the ladder advances by one"              "2"                        mfield u-rev review_recoveries
t  "a seat whose mark was repaired is no longer a candidate" "0"            wakes_for u-server-park
t  "...while the one the answer returned to review is nudged on the next tick" "WAKE uuid=u-race" cat "$NUDGES"
t  "nor is one whose mark was cleared"           "0"                        wakes_for u-done

# =========================================================================
# The phase is invocable alone, named in the usage line — and REACHED BY THE
# WHOLE TICK. The last one needs a budget the tick has not spent (the arms
# stop taking new items without one) and a registry of its own, so the
# candidate cannot be confused with the drills above.
# =========================================================================
t  "the phase is named in the usage line"        "review-recover"           bash -c "$SCRIPTS/_sweep_api.sh nonsense 2>&1 || true"

DH2="$TDIR/registry-all"; mkdir -p "$DH2"
NUDGES2="$TDIR/nudges-all.log"; : > "$NUDGES2"
printf '%s\n' '{"uuid":"u-all","current":"u-all","status":"idle","run_id":72,
                 "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"72",
                 "run_bearer":"tok-72","phase":"review"}' > "$DH2/u-all.json"
chmod 600 "$DH2/u-all.json"
stale u-all
OALL="$TDIR/all.out"
( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH2" SMINOS_CLI="$DS/sminos" \
    NUDGE_LOG="$NUDGES2" BOARD_SUPPRESS_DIR="$SUPD" BOARD_CREDENTIALS_FILE="$CREDS" \
    BOARD_SWEEP_TICK_BUDGET=900 "$SCRIPTS/_sweep_api.sh" all ) > "$OALL" 2>&1 || true
t  "the whole-tick run reaches the review-recover phase" "review-recover: #72" cat "$OALL"
t  "...and nudges its candidate"                 "WAKE uuid=u-all"        cat "$NUDGES2"
t  "...having renewed that run first"            '"path": "/runs/72/renew"' cat "$FIX.log"

# =========================================================================
# THE REAL OVERLAP. The two-read drill above pins what the repair does with a
# ticket that moved; this one pins the ORDERING between two live processes,
# which is where the defect actually lived: the repair held the registry lock
# across its board read, and the answer's own stamp derived its difference
# OUTSIDE that lock. Reading `phase=review` while the repair was mid-flight,
# the stamp concluded there was nothing to write — and the repair then wrote
# `review-parked` last, onto a ticket that was back in review.
#
# The board read is what holds the window open: this server answers the
# REPAIR's re-read (the second GET) only once the gate file appears, so the
# repair provably holds the lock while the stamp runs.
# =========================================================================
PORT2="$(free_port)"
MARK="$TDIR/in-reread"; GATE="$TDIR/gate"
cat > "$TDIR/blocking-server.py" <<'PYS'
import http.server, json, os, sys, time
port, mark, gate = int(sys.argv[1]), sys.argv[2], sys.argv[3]


class H(http.server.BaseHTTPRequestHandler):
    n = 0

    def do_GET(self):
        H.n += 1
        if H.n >= 2:            # the repair's re-read, inside the lock
            open(mark, "w").close()
            while not os.path.exists(gate):
                time.sleep(0.02)
        body = json.dumps({"id": 80, "state": "needs-human", "priority": "P1",
                           "title": "parked, and answered mid-repair"}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
PYS
python3 "$TDIR/blocking-server.py" "$PORT2" "$MARK" "$GATE" & BLOCKER=$!
trap 'kill $MOCK $BLOCKER 2>/dev/null; { wait $MOCK $BLOCKER; } 2>/dev/null || true; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT2" || { echo "FAIL blocking server never listened on $PORT2"; exit 1; }

r3="$(mkrepo)"; mkdir -p "$r3/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT2" > "$r3/.doperpowers/board.json"
DH3="$TDIR/registry-race"; mkdir -p "$DH3"
printf '%s\n' '{"uuid":"u-overlap","current":"u-overlap","status":"idle","run_id":80,
                 "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"80",
                 "run_bearer":"tok-80","phase":"review"}' > "$DH3/u-overlap.json"
chmod 600 "$DH3/u-overlap.json"
stale u-overlap

( cd "$r3" && env HOME="$TESTHOME" DAEMON_HOME="$DH3" SMINOS_CLI="$DS/sminos" \
    NUDGE_LOG="$TDIR/nudges-race.log" BOARD_CREDENTIALS_FILE="$CREDS" \
    "$SCRIPTS/_sweep_api.sh" review-recover ) > "$TDIR/race.out" 2>&1 &
REPAIR=$!
# The repair is now inside its re-read, holding the registry lock.
until [ -f "$MARK" ]; do sleep 0.02; done

# THE ANSWER'S HALF, as board-answer and board-transition run it: the ticket is
# back in-review server-side and the seat is stamped for that state.
# EXPORTED, not an assignment prefix: bash honours a prefix on a special
# builtin (`.`) only in POSIX mode, so `DAEMON_HOME=… . _lib.sh` left the
# suite's own registry in place and the stamp scanned the wrong one — which
# looks exactly like the lock working.
( : > "$TDIR/stamp-started"
  cd "$r3" || exit 1
  export DAEMON_HOME="$DH3" BOARD_CREDENTIALS_FILE="$CREDS"
  . "$SCRIPTS/_lib.sh" && _phase_stamp 80 in-review
  : > "$TDIR/stamp-done" ) > "$TDIR/stamp.out" 2>&1 &
STAMP=$!
until [ -f "$TDIR/stamp-started" ]; do sleep 0.02; done
# Give it every chance to finish if it is going to: the point of the assertion
# below is that it CANNOT while the repair holds the lock.
tries=100
while [ "$tries" -gt 0 ] && [ ! -f "$TDIR/stamp-done" ]; do tries=$((tries - 1)); sleep 0.02; done
nt "the answer's stamp waits for the repair's lock" "yes" \
  bash -c "[ -f '$TDIR/stamp-done' ] && echo yes || echo no"

: > "$GATE"          # the repair's re-read returns; it writes and releases
wait $REPAIR $STAMP 2>/dev/null || true
t  "...and writes last, so the answer's mark stands" "[review]" \
  bash -c "python3 -c 'import json,sys; print(\"[%s]\" % json.load(open(sys.argv[1])).get(\"phase\", \"<absent>\"))' '$DH3/u-overlap.json'"
t  "...the repair having written its own mark first" "review-parked" cat "$TDIR/race.out"

finish
