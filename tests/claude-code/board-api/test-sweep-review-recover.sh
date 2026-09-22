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
 {"method":"POST","path":"/tickets/67/transition","status":200,
  "body":{"to":"needs-human","converged":false}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

# ---- the registry -----------------------------------------------------------
DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/sminos-stub"; mkdir -p "$DS"
RESUME="$TDIR/resume.log"; : > "$RESUME"
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
  python3 - "$DH/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
  exit 0 ;;
resume)
  # Records its ENVIRONMENT as well as its argv: the run credentials ride the
  # nudge that way and are observable nowhere else.
  [ "\${1:-}" != "--wait" ] || shift
  { echo "RESUME uuid=\$1"
    echo "PROMPT: \$2"
    env | grep '^BOARD_RUN_' | sort || true; } >> "$RESUME"
  exit 0 ;;
*) echo "stub sminos: unexpected verb '\$verb'" >&2; exit 2 ;;
esac
EOF
chmod +x "$DS/sminos"

SW() {  # one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$@" )
}
RECOVER() { SW "${@:2}" "$SCRIPTS/_sweep_api.sh" review-recover > "$1" 2>&1 || true; }

resumes()     { grep -c '^RESUME uuid=' "$RESUME" || true; }
resumes_for() { grep -c "^RESUME uuid=$1\$" "$RESUME" || true; }
mfield()      { python3 -c 'import json,sys
m = json.load(open(sys.argv[1]))
print(m.get(sys.argv[2], "<absent>"))' "$DH/$1.json" "$2"; }
posts()       { grep -c "\"path\": \"$1\"" "$FIX.log" || true; }

# =========================================================================
# One pass over the whole registry.
# =========================================================================
O1="$TDIR/t1.out"; RECOVER "$O1"

t  "idle owner with phase review and stale transcript → resume called" "RESUME uuid=u-rev" cat "$RESUME"
t  "the nudge names the review, not the build"  "SWEEP RECOVERY: your review of ticket #60's pull request has no live QA agent" cat "$RESUME"
t  "...and says what to do when no review is running" "dispatch doperpowers:qa-loop again per your protocol's Closing Artifact" cat "$RESUME"
t  "...and what to do when one already finished" "if the review already reached a park or a verdict, restate it" cat "$RESUME"
t  "the nudge carries the run's OWN bearer"      "BOARD_RUN_TOKEN=tok-61"   cat "$RESUME"
t  "the attempt is counted in its own key"       "1"                        mfield u-rev review_recoveries
t  "and the tick says what it did"               "review-recover: #60"      cat "$O1"

t  "working owner → untouched"                   "0"                        resumes_for u-work
t  "...and its count is never opened"            "<absent>"                 mfield u-work review_recoveries
t  "phase review-parked → untouched"             "0"                        resumes_for u-parked
t  "an owner still writing is inside the threshold" "0"                     resumes_for u-fresh

# THE TICKET IS THE AUTHORITY, not the seat's mark.
t  "server-parked: ticket needs-human with phase review → no resume" "0"    resumes_for u-server-park
t  "...and the meta is restamped review-parked"  "review-parked"            mfield u-server-park phase
t  "...and the tick says the board parked it"    "#64"                      cat "$O1"
t  "ticket done with phase review → no resume"   "0"                        resumes_for u-done
t  "...and the stale phase is removed"           "<absent>"                 mfield u-done phase

# Progress is a review artifact, not seat activity.
t  "a new review-trail event resets the count"   "RESUME uuid=u-trail"      cat "$RESUME"
t  "...so the attempt counts from zero again"    "1"                        mfield u-trail review_recoveries
t  "...and the trail it reset on is recorded"    "1"                        mfield u-trail review_trail_seen

# The cap.
t  "cap → POST /tickets/<id>/transition to needs-human" "/tickets/67/transition" cat "$FIX.log"
t  "...as a park"                                '\"to\": \"needs-human\"' cat "$FIX.log"
t  "...naming the exhausted ladder"              "needs-human"              cat "$O1"
t  "...and the owner is not nudged again"        "0"                        resumes_for u-cap
t  "...and the park leaves the seat review-parked" "review-parked"          mfield u-cap phase

t  "exactly two owners were nudged"              "2"                        resumes

# =========================================================================
# Idempotence — a second pass with nothing changed. The ladder advances by
# one per tick and nothing else moves; the repaired marks stay repaired.
# =========================================================================
O2="$TDIR/t2.out"; RECOVER "$O2"
t  "a second tick nudges the same owner once more" "2"                      resumes_for u-rev
t  "and the ladder advances by one"              "2"                        mfield u-rev review_recoveries
t  "a seat whose mark was repaired is no longer a candidate" "0"            resumes_for u-server-park
t  "nor is one whose mark was cleared"           "0"                        resumes_for u-done

# =========================================================================
# The phase is invocable alone and is part of the full tick.
# =========================================================================
t  "the phase is named in the usage line"        "review-recover"           bash -c "$SCRIPTS/_sweep_api.sh nonsense 2>&1 || true"

finish
