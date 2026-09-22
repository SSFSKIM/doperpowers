#!/usr/bin/env bash
# test-sweep-stall.sh — _sweep_api.sh phase 1b, the harness-error ladder.
#
# THE STATE THIS PHASE EXISTS FOR: a bound worker whose turn died on a
# harness-level error (a 429 out-of-plan, a hit usage limit, a 529) leaves a
# session that is alive and a seat that reads `idle`. Renewal keeps its lease
# fresh forever, so the server never reclaims the run, the run never reaches
# /runs/needing-resume, and the resume phase never sees it. Observed live for
# nine hours (dp#58).
#
# STALL pins: a candidate is a LIVE, IDLE seat whose latest turn IS a harness
# error — a busy seat, a gone seat, and a worker merely QUOTING an error are
# all left alone; the marker is stamped in the meta and keyed by RUN; a stated
# reset already in the past is due immediately while an unstated one waits the
# window; a nudge carries the run's OWN credentials (a `sminos wake` with no
# live socket falls through to a resume, and an empty bearer would hand the
# worker the configured human credentials instead of its fence); the ladder is
# three lifetime attempts and the fourth is never issued; and recovery — the
# seat idle again with ordinary prose — clears the ladder.
#
# THE HAND-OFF pins: once the ladder is spent, phase 1 ENDS the run and retires
# it locally. Merely withholding the lease is one word short — a run nothing
# calls renew for never answers 409 run-ended, so the meta keeps its run id and
# its run bearer forever, stays a relay delivery candidate on revoked
# credentials, and holds a dispatch slot for good. A failed end falls back to
# the withheld lease and is retried every tick until it lands.
#
# THE TICKET'S OWN LADDER pins the rung above that one: the per-run ladder
# resets on every successor, so a harness fault that outlives its worker cycles
# hourly and reaches nobody. Three exhausted ladders on one ticket register an
# env-issue and suppress it, and only a worker answering as itself clears the
# count.
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
# Renewal is interleaved ahead of every nudge, so every run in the registry is
# renewed repeatedly across this drill: none of these entries is `once`.
# Run ids are chosen so no one is a PREFIX of another — the mock matches paths
# by prefix, first match wins.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/71/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/72/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/73/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/74/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/75/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/76/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/78/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/80/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/81/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/82/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/84/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/85/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/86/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/87/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/88/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/89/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/90/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/91/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/92/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/71/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/79/end","status":500,"once":true,
  "body":{"error":{"code":"internal","message":"boom"}}},
 {"method":"POST","path":"/runs/79/end","status":200,"body":{"ended":true}},
 {"method":"POST","path":"/runs/79/renew","status":200,"body":{"renewed":true}},
 {"method":"GET","path":"/tickets/50","status":200,
  "body":{"id":50,"state":"in-progress","priority":"P1","title":"the stalled one"}},
 {"method":"POST","path":"/tickets","status":200,
  "body":{"id":99,"state":"needs-human"}},
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[{"id":50,"state":"in-progress","priority":"P1","title":"the stalled one"},
                   {"id":99,"state":"needs-human","priority":null,
                    "title":"stuck harness error: ticket #50 never gets a turn in"}],
          "next":null,"as_of":1}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"body":[]},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]}
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
REPLIES="$TDIR/replies"; mkdir -p "$REPLIES"
WAKE="$TDIR/wake.log"; : > "$WAKE"
TESTHOME="$TDIR/home"; mkdir -p "$TESTHOME/.claude/projects"

meta() { printf '%s\n' "$2" > "$DH/$1.json"; }
say()  { printf '%s\n' "$2" > "$REPLIES/$1.txt"; }   # what the seat last said

# THE SUBJECT: idle, alive, holding run 71, and its last turn is the 429 from
# the incident — with a reset time that has already passed, so the wait is over
# the moment this phase first looks.
meta u-stall '{"uuid":"u-stall","current":"u-stall","status":"idle","run_id":71,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"42",
               "run_bearer":"tok-71"}'
chmod 600 "$DH/u-stall.json"
say u-stall "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."

# Idle and alive, but its turn ended on ORDINARY PROSE. A worker that finished
# and is waiting is not a stalled one; nothing may be stamped on it.
meta u-ok '{"uuid":"u-ok","current":"u-ok","status":"idle","run_id":72,"fence":1,
            "lane":"implementer","bind_confirmed":true,"ticket":"43","run_bearer":"tok-72"}'
say u-ok "Parked needs-human: the retention window is a product call. Orientation summary follows."

# A worker QUOTING an error inside a report. "Contains" would read this as a
# dead turn; the match is anchored at the start of the turn precisely so it
# does not.
meta u-quote '{"uuid":"u-quote","current":"u-quote","status":"idle","run_id":73,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"44",
               "run_bearer":"tok-73"}'
say u-quote "The daemon log shows API Error: Request rejected (429) at 09:31 — that is the failure I am reporting."

# MID-TURN. A running worker cannot have died on anything; the phase must not
# read its transcript as a verdict.
meta u-busy '{"uuid":"u-busy","current":"u-busy","status":"working","run_id":74,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"45",
              "run_bearer":"tok-74"}'
say u-busy "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."

# Stalled on a harness error, but the meta holds NO BEARER. `sminos wake` falls
# through to a resume when no socket answers, and a resume with an empty
# BOARD_RUN_TOKEN hands the worker the configured human/automation credentials
# instead of its own fence. Phase 1's bind repair owns this meta, not the nudge.
# Its reset is already past, so it reaches the NUDGE on the first tick — the
# refusal lives there, not at the marker.
meta u-nobearer '{"uuid":"u-nobearer","current":"u-nobearer","status":"idle","run_id":75,
                  "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"46"}'
say u-nobearer "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."

# A usage limit with NO machine-readable reset — the window governs, so nothing
# is nudged on the tick that first sees it.
meta u-window '{"uuid":"u-window","current":"u-window","status":"idle","run_id":76,
                "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"47",
                "run_bearer":"tok-76"}'
say u-window "API Error: 529 Overloaded. This is a server-side issue, usually temporary."

# The session is GONE from the harness. Its lease already expires on its own;
# the existing resume path owns it and this phase must not touch it.
meta u-gone '{"uuid":"u-gone","current":"u-gone","status":"idle","run_id":77,"fence":1,
              "lane":"implementer","bind_confirmed":true,"ticket":"48","run_bearer":"tok-77"}'
say u-gone "API Error: 529 Overloaded."

# THE HARNESS'S ACTUAL USAGE-LIMIT RENDERINGS, verbatim from the live corpus.
# None of them states a reset this tick can wait for, so each is MARKED and
# none is nudged — what they pin is that the tightened pattern still sees them.
meta u-weekly '{"uuid":"u-weekly","current":"u-weekly","status":"idle","run_id":84,
                "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"52",
                "run_bearer":"tok-84"}'
say u-weekly "You've hit your weekly limit · resets Aug 26 at 1pm (Asia/Seoul) · progress saved"

meta u-fable '{"uuid":"u-fable","current":"u-fable","status":"idle","run_id":85,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"53",
               "run_bearer":"tok-85"}'
say u-fable "You've reached your Fable 5 limit. Run /usage-credits to continue or switch models with /model."

meta u-credits '{"uuid":"u-credits","current":"u-credits","status":"idle","run_id":86,
                 "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"54",
                 "run_bearer":"tok-86"}'
say u-credits "You're out of usage credits. Run /usage-credits to keep using Fable 5 or /model to switch models."

# THE COUNTEREXAMPLE. `You've (hit|reached|out of)` as a bare sentence OPENER
# is perfectly ordinary worker prose, and a worker parked on a gate was nudged
# with an unsolicited order to continue its protocol. The limit noun is the
# discriminant, not the opener.
meta u-gate '{"uuid":"u-gate","current":"u-gate","status":"idle","run_id":87,
              "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"55",
              "run_bearer":"tok-87"}'
say u-gate "You've reached the review gate. Approval is needed."

# THE SAME COUNTEREXAMPLE, ONE ALTERNATION OVER. `failed to (authenticate|
# refresh)` opens ordinary worker prose just as readily as the limit openers
# did. Both harness renderings continue into a specific object (`Failed to
# authenticate: OAuth session expired …`, `Failed to refresh OAuth token: …`),
# so that object is the discriminant.
meta u-authprose '{"uuid":"u-authprose","current":"u-authprose","status":"idle","run_id":91,
                   "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"56",
                   "run_bearer":"tok-91"}'
say u-authprose "Failed to authenticate against the fixture's mock server, so the drill asserts the refusal instead. Parked."

# ...and the real rendering, which must still be caught.
meta u-authreal '{"uuid":"u-authreal","current":"u-authreal","status":"idle","run_id":92,
                  "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"57",
                  "run_bearer":"tok-92"}'
say u-authreal "Failed to authenticate: OAuth session expired and could not be refreshed"

cat > "$DS/sminos" <<EOF
#!/usr/bin/env bash
verb="\${1:-}"; shift || true
case "\$verb" in
migrate) exit 0 ;;
sync)
  # As the real verb reports it: \`absent\` when the session is gone from the
  # harness, \`noop\` for an ALREADY-TERMINAL record (idle/error — it never
  # re-inspects one), \`live\` for a running turn. Driven off the record, so a
  # status the sweep writes is visible here.
  [ "\$1" != u-gone ] || { echo absent; exit 0; }
  python3 - "$DH/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
  exit 0 ;;
reply)
  # A read that DIES. The pipeline used to hide this status behind awk's, and
  # an empty string reads as ordinary prose — which clears a standing ladder.
  [ -z "\${REPLY_MUST_FAIL:-}" ] || exit 1
  # The real verb's shape: a header block, a fixed separator, then the turn.
  # The header carries the seat's TASK — which quotes an error here on purpose,
  # because only what follows the separator may decide this phase.
  echo "g/\$1  [\$1]  status=idle  turns=1  live=yes"
  echo "task: recover from API Error: Request rejected (429) if one happens"
  echo "--- latest reply ---"
  cat "$REPLIES/\$1.txt" 2>/dev/null || true
  exit 0 ;;
wake)
  # Records its ENVIRONMENT as well as its argv: the run credentials ride the
  # nudge that way and are observable nowhere else.
  { echo "WAKE uuid=\$1"
    echo "ARGV: \$*"
    env | grep '^BOARD_RUN_' | sort || true; } >> "$WAKE"
  [ -z "\${WAKE_MUST_FAIL:-}" ] || exit 1
  exit 0 ;;
*) echo "stub sminos: unexpected verb '\$verb'" >&2; exit 2 ;;
esac
EOF
chmod +x "$DS/sminos"

SW() {  # one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$@" )
}
STALL() { SW "${@:2}" "$SCRIPTS/_sweep_api.sh" stall > "$1" 2>&1 || true; }

wakes()      { grep -c '^WAKE uuid=' "$WAKE" || true; }       # total nudges so far
wakes_for()  { grep -c "^WAKE uuid=$1\$" "$WAKE" || true; }
mfield()     { python3 -c 'import json,sys
m = json.load(open(sys.argv[1]))
print(m.get(sys.argv[2], "<absent>"))' "$DH/$1.json" "$2"; }
# "the attempt window passed", without spending it in wall clock.
expire_due() { python3 -c 'import json,sys,time
p = sys.argv[1]; m = json.load(open(p))
m["stall_due"] = int(time.time()) - 1
json.dump(m, open(p, "w"))' "$DH/$1.json"; }

# =========================================================================
# Tick 1 — the marker is stamped and, because the stated reset has passed,
#          the first nudge goes out in the same pass.
# =========================================================================
O1="$TDIR/t1.out"; STALL "$O1"

t  "the stalled worker is nudged"        "nudged u-stall"                cat "$O1"
t  "the nudge names the attempt"         "attempt 1 of 3"                cat "$O1"
t  "and quotes the error it saw"         "out of plan usage"             cat "$O1"
t  "exactly one nudge left the tick"     "1"                             wakes
t  "the marker is keyed by RUN"          "71"                            mfield u-stall stall_run
t  "the attempt is counted in the meta"  "1"                             mfield u-stall stall_attempts
t  "the error is recorded with it"       "Request rejected (429)"        mfield u-stall stall_error
t  "the nudge carries the run's OWN bearer"    "BOARD_RUN_TOKEN=tok-71"  cat "$WAKE"
t  "and the run it speaks for"           "BOARD_RUN_ID=71"               cat "$WAKE"
t  "and its fence"                       "BOARD_RUN_FENCE=1"             cat "$WAKE"
t  "the nudge tells the worker what happened" "SWEEP RECOVERY"           cat "$WAKE"
t  "and that the ladder is counting"     "hand the ticket on"            cat "$WAKE"

# The population that must be left alone.
t  "an idle worker whose turn was ordinary prose is not marked" "<absent>" mfield u-ok stall_run
nt "and is never nudged"                 "WAKE uuid=u-ok"                cat "$WAKE"
t  "a worker QUOTING an error is not marked"  "<absent>"                 mfield u-quote stall_run
nt "and is never nudged"                 "WAKE uuid=u-quote"             cat "$WAKE"
t  "a worker mid-turn is not marked"     "<absent>"                      mfield u-busy stall_run
nt "and is never nudged"                 "WAKE uuid=u-busy"              cat "$WAKE"
t  "a session gone from the harness is not marked" "<absent>"            mfield u-gone stall_run
nt "and is never nudged (its lease already expires)" "WAKE uuid=u-gone"  cat "$WAKE"

# Marked, but held back.
t  "an error stating no reset waits the window" "0"                      mfield u-window stall_attempts
t  "and says so once"                    "marker stamped"                cat "$O1"
nt "and is not nudged yet"               "WAKE uuid=u-window"            cat "$WAKE"
t  "a bearerless meta is refused"        "holds no run bearer"           cat "$O1"
nt "and is never nudged"                 "WAKE uuid=u-nobearer"          cat "$WAKE"
# AN ATTEMPT IS SPENT WHERE A NUDGE IS ATTEMPTED, nowhere else. Stamping before
# the nudge is right where delivery is genuinely tried and its outcome unknown;
# this branch tries nothing, and a meta that is repeatedly bearerless burned its
# whole ladder on nudges that never existed and was handed off for it.
t  "and the refusal spends no attempt"   "0"                             mfield u-nobearer stall_attempts

# The harness's real renderings still read as harness errors...
t  "the weekly-limit rendering is a candidate"  "84"                     mfield u-weekly stall_run
t  "so is the per-model limit"           "85"                            mfield u-fable stall_run
t  "and the exhausted-credits one"       "86"                            mfield u-credits stall_run
# ...and prose that merely OPENS like one does not.
t  "a worker parked on a gate is not marked"    "<absent>"               mfield u-gate stall_run
nt "and is never nudged"                 "WAKE uuid=u-gate"              cat "$WAKE"
t  "nor is one reporting its own auth failure"  "<absent>"               mfield u-authprose stall_run
nt "and it is never nudged either"       "WAKE uuid=u-authprose"         cat "$WAKE"
t  "but the harness's own auth failure still is" "92"                    mfield u-authreal stall_run

# =========================================================================
# Tick 2 — nothing changed. The attempt window has NOT passed, so no second
#          nudge goes out, and the ladder does not advance.
# =========================================================================
O2="$TDIR/t2.out"; STALL "$O2"
t  "a second tick inside the window does not nudge again" "1"            wakes
t  "and the ladder does not advance"     "1"                             mfield u-stall stall_attempts
nt "and it says nothing about it"        "nudged u-stall"                cat "$O2"

# =========================================================================
# Ticks 3 and 4 — the window passes twice. Attempts 2 and 3.
# =========================================================================
expire_due u-stall; O3="$TDIR/t3.out"; STALL "$O3"
t  "past the window the nudge resumes"   "attempt 2 of 3"                cat "$O3"
t  "two nudges now"                      "2"                             wakes

expire_due u-stall; O4="$TDIR/t4.out"; STALL "$O4"
t  "and the third"                       "attempt 3 of 3"                cat "$O4"
t  "three nudges now"                    "3"                             wakes

# =========================================================================
# THE LAST NUDGE IS NOT WASTED. Three attempts are stamped, but the hand-off
# is NOT decided yet: the attempt is stamped BEFORE the nudge goes out, so a
# count at the cap says only "we tried", never "it failed". A worker that
# recovers on the last nudge must keep its run — so while it is mid-turn the
# lease is still renewed and nothing is handed off.
# =========================================================================
t  "the ladder at its cap is not yet a hand-off" "<absent>"              mfield u-stall stall_exhausted
python3 -c 'import json,sys
p = sys.argv[1]; m = json.load(open(p)); m["status"] = "working"
json.dump(m, open(p, "w"))' "$DH/u-stall.json"
: > "$FIX.log"
SW "$SCRIPTS/_sweep_api.sh" renew > /dev/null 2>&1 || true
t  "a worker mid-turn on its last nudge keeps its lease" '"path": "/runs/71/renew"' cat "$FIX.log"
python3 -c 'import json,sys
p = sys.argv[1]; m = json.load(open(p)); m["status"] = "idle"
json.dump(m, open(p, "w"))' "$DH/u-stall.json"

# =========================================================================
# Tick 5 — the nudges are gone and the turn is STILL the error. THE FOURTH IS
#          NEVER ISSUED, however long the window has passed; instead the run
#          is handed off.
# =========================================================================
expire_due u-stall; O5="$TDIR/t5.out"; STALL "$O5"
t  "the fourth nudge is never issued"    "3"                             wakes
t  "the count stands where the ladder ended" "3"                         mfield u-stall stall_attempts
nt "and no attempt 4 is logged"          "attempt 4"                     cat "$O5"
t  "the hand-off is announced once"      "handing the run to the successor path" cat "$O5"
t  "and stamped against the run it ends" "71"                            mfield u-stall stall_exhausted

O5b="$TDIR/t5b.out"; STALL "$O5b"
nt "and is not announced again"          "handing the run"               cat "$O5b"

# =========================================================================
# The hand-off — phase 1 withholds the lease from a spent ladder, and ONLY
# from that one. This is the terminal step: the server reclaims the run and
# the resume phase's successor path takes it from there.
# =========================================================================
: > "$FIX.log"
ORENEW="$TDIR/renew.out"
SW "$SCRIPTS/_sweep_api.sh" renew > "$ORENEW" 2>&1 || true
nt "a spent ladder's lease is left to expire"   "/runs/71/renew"         cat "$FIX.log"
t  "and the tick says why"               "harness-error ladder spent"    cat "$ORENEW"
t  "every other live run is still renewed"      '"path": "/runs/72/renew"' cat "$FIX.log"
t  "including one still climbing the ladder"    '"path": "/runs/76/renew"' cat "$FIX.log"
# AND THE RUN IS ENDED, not merely left to age out. A run nothing calls renew
# for never answers 409 run-ended, so _retire_run_locally never runs: the meta
# keeps its run id and its run bearer past the server's own reclaim, stays a
# live relay delivery candidate on revoked credentials (its post-renew run_id
# guard passes, because nothing ever changed the field), and holds a dispatch
# slot in the local cap for good.
t  "the spent run is ENDED"              '"path": "/runs/71/end"'        cat "$FIX.log"
t  "as abandoned"                        '\"reason\": \"abandoned\"'    cat "$FIX.log"
t  "and the meta stops naming it"        "<absent>"                      mfield u-stall run_id
t  "its bearer going with it"            "<absent>"                      mfield u-stall run_bearer
: > "$FIX.log"
SW "$SCRIPTS/_sweep_api.sh" renew > /dev/null 2>&1 || true
nt "a retired meta is out of the scan for good" "/runs/71/"              cat "$FIX.log"

# The retire above is the point of the change, and it takes run 71 off this
# meta. The recovery drill below is about the ladder's OTHER exit, so the seat
# is re-planted as one that still speaks for its run — which is exactly the
# shape a successor claimed onto this session has.
python3 -c 'import json,sys
p = sys.argv[1]; m = json.load(open(p))
m.update({"run_id": 71, "fence": 1, "run_bearer": "tok-71", "bind_confirmed": True})
json.dump(m, open(p, "w"))' "$DH/u-stall.json"

# =========================================================================
# Recovery — the seat answers as itself again. ONLY this clears the ladder:
# a marker is not cleared merely because the seat is busy, or the nudge that
# makes it busy would reset the count on every lap and the cap would never
# bind.
# =========================================================================
say u-stall "Re-stated the gate verdict and opened the PR; evidence is in the body."
O6="$TDIR/t6.out"; STALL "$O6"
t  "a recovered worker's ladder is cleared"     "ladder is cleared"      cat "$O6"
t  "and the marker is gone from the meta"       "<absent>"               mfield u-stall stall_run
t  "and so is the hand-off it had earned"      "<absent>"                mfield u-stall stall_exhausted
t  "no nudge rode the recovery"          "3"                             wakes

: > "$FIX.log"
SW "$SCRIPTS/_sweep_api.sh" renew > /dev/null 2>&1 || true
t  "and its lease is renewed again"      '"path": "/runs/71/renew"'      cat "$FIX.log"

# =========================================================================
# A ladder is PER RUN. A successor claimed onto the same seat is a new run and
# must not inherit a predecessor's exhaustion.
# =========================================================================
python3 -c 'import json,sys,time
p = sys.argv[1]; m = json.load(open(p))
m.update({"stall_run": "70", "stall_attempts": 3, "stall_due": int(time.time()) - 1,
          "stall_exhausted": "70", "stall_error": "API Error: 529 Overloaded."})
json.dump(m, open(p, "w"))' "$DH/u-stall.json"
say u-stall "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."
O7="$TDIR/t7.out"; STALL "$O7"
t  "a spent ladder from ANOTHER run is not inherited" "attempt 1 of 3"   cat "$O7"
t  "and the marker is re-keyed to this run"     "71"                     mfield u-stall stall_run

# =========================================================================
# A nudge that FAILS still spends its attempt — the direction stamping-before
# chooses, and the safe one: a nudge that half-lands and fails to report would
# otherwise spin the ladder forever.
# =========================================================================
expire_due u-stall
O8="$TDIR/t8.out"; STALL "$O8" WAKE_MUST_FAIL=1
t  "a failed nudge is reported as failed"       "the nudge of u-stall failed" cat "$O8"
t  "and its attempt is spent"            "2"                             mfield u-stall stall_attempts

# =========================================================================
# AN EMPTY OR FAILED READ IS NOT RECOVERY. `sminos reply` piped straight into
# awk handed back awk's exit status, so a read that DIED produced an empty
# string that succeeded — and an empty string matches no error, which is the
# `clear` verdict: one intermittent hiccup deleted a standing ladder and reset
# the cap. Absence of evidence is not evidence of recovery.
# =========================================================================
O9="$TDIR/t9.out"; STALL "$O9" REPLY_MUST_FAIL=1
t  "a failed read says so"               "could not be read"             cat "$O9"
nt "and clears nothing"                  "ladder is cleared"             cat "$O9"
t  "the marker still stands"             "71"                            mfield u-stall stall_run
t  "and the ladder is not reset"         "2"                             mfield u-stall stall_attempts

say u-stall ""
O10="$TDIR/t10.out"; STALL "$O10"
nt "an EMPTY turn clears nothing either" "ladder is cleared"             cat "$O10"
t  "the marker still stands"             "71"                            mfield u-stall stall_run
t  "and the ladder is still not reset"   "2"                             mfield u-stall stall_attempts
nt "and an unreadable turn is not an event to log" "u-stall"             cat "$O10"
say u-stall "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."

# =========================================================================
# A PROSE RESET IS DATED BY THE TURN THAT DIED, not by the scan that found it.
# This phase exists for errors first noticed hours later, and the usage-limit
# renderings state a wall clock with no date: resolved against scan time, a
# reset that passed long ago is pushed forward into today — a needless wait
# that sits under the ceiling, so nothing catches it — or rolled into tomorrow
# and abandoned for the window. The transcript's mtime is the turn-end clock.
# =========================================================================
mkdir -p "$TESTHOME/.claude/projects/proj"
: > "$TESTHOME/.claude/projects/proj/u-prose.jsonl"
python3 -c 'import os, sys, time
t = int(time.time()) - 2 * 86400
os.utime(sys.argv[1], (t, t))' "$TESTHOME/.claude/projects/proj/u-prose.jsonl"
meta u-prose '{"uuid":"u-prose","current":"u-prose","status":"idle","run_id":88,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"56",
               "run_bearer":"tok-88"}'
say u-prose "You've hit your session limit · resets 11:00pm (UTC)"
# The same message with NO transcript to date it: the scan clock is the
# fallback, which is the behaviour that was always there.
meta u-prose-nt '{"uuid":"u-prose-nt","current":"u-prose-nt","status":"idle","run_id":89,
                  "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"57",
                  "run_bearer":"tok-89"}'
say u-prose-nt "You've hit your session limit · resets 11:00pm (UTC)"
O11="$TDIR/t11.out"; STALL "$O11"
t  "a reset dated by the dead turn has already passed" "nudged u-prose"  cat "$O11"
t  "so the nudge goes out on the first sighting" "1"                     wakes_for u-prose
t  "with no transcript the scan clock governs"  "0"                      mfield u-prose-nt stall_attempts
nt "and that one only waits the window"  "WAKE uuid=u-prose-nt"          cat "$WAKE"

# =========================================================================
# THE BUDGET GATE SPENDS NOTHING EITHER. A tick past its budget attempts no
# nudge at all, so a meta repeatedly reached there must not be charged for
# one — while marking and clearing, being two file operations, still land.
# =========================================================================
meta u-budget '{"uuid":"u-budget","current":"u-budget","status":"idle","run_id":90,
                "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"58",
                "run_bearer":"tok-90"}'
say u-budget "API Error: Request rejected (429) · This account is out of plan usage until 2020-01-01T00:00:00Z."
O12="$TDIR/t12.out"; STALL "$O12" BOARD_SWEEP_TICK_BUDGET=0
t  "a spent budget says so"              "tick budget exhausted"         cat "$O12"
t  "and nudges nothing"                  "0"                             wakes_for u-budget
t  "but the marker still lands"          "90"                            mfield u-budget stall_run
t  "and no attempt is spent on it"       "0"                             mfield u-budget stall_attempts

# =========================================================================
# THE END IS THE PLAN; THE WITHHELD LEASE IS THE FALLBACK. An end that cannot
# reach the server must not strand the meta either: the lease is still withheld
# (it expires on its own), the flag stands, and the next tick retries the end
# until one lands.
# =========================================================================
meta u-endfail '{"uuid":"u-endfail","current":"u-endfail","status":"idle","run_id":79,
                 "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"51",
                 "run_bearer":"tok-79","stall_run":"79","stall_attempts":3,
                 "stall_exhausted":"79","stall_error":"API Error: 529 Overloaded."}'
: > "$FIX.log"
OEF1="$TDIR/endfail1.out"
SW "$SCRIPTS/_sweep_api.sh" renew > "$OEF1" 2>&1 || true
t  "a failed end is reported"            "ending the run failed"         cat "$OEF1"
nt "and the lease is withheld anyway"    "/runs/79/renew"                cat "$FIX.log"
t  "the meta keeps its run until an end lands" "79"                      mfield u-endfail run_id
: > "$FIX.log"
OEF2="$TDIR/endfail2.out"
SW "$SCRIPTS/_sweep_api.sh" renew > "$OEF2" 2>&1 || true
t  "the next tick retries the end"       '"path": "/runs/79/end"'        cat "$FIX.log"
t  "and this one lands"                  "run ended so the successor path" cat "$OEF2"
t  "so the meta is retired at last"      "<absent>"                      mfield u-endfail run_id

# =========================================================================
# THE TICKET'S OWN LADDER. `sminos resume` reports success when it has merely
# DELIVERED a prompt, so a successor whose very first turn dies on the same
# harness error looks like a clean recovery: _resume_one resets the per-run
# ladder, the ticket cycles hourly, and no three failed cycles ever accumulate
# anywhere. A `Login expired` or a multi-day weekly limit churns forever and
# reaches nobody. This count is per TICKET, survives successors, and ends where
# the resume path's does — an env-issue plus a suppression record.
# =========================================================================
SUP="$(store_dir "$DH" board-suppress "$PORT")"
cycles() { cat "$SUP/.stall-cycles-50" 2>/dev/null || echo "<absent>"; }
# A successor is a fresh run on the same seat, which is exactly what re-keying
# the marker onto a new run id is. Each plant is one ladder at its last rung.
spend_ladder() {  # <run>
  python3 -c 'import json, sys, time
p, run = sys.argv[1], sys.argv[2]; m = json.load(open(p))
m.update({"run_id": int(run), "stall_run": run, "stall_attempts": 3,
          "stall_due": int(time.time()) - 1,
          "stall_error": "Login expired - please run /login"})
m.pop("stall_exhausted", None)
json.dump(m, open(p, "w"))' "$DH/u-cycle.json" "$1"
}
meta u-cycle '{"uuid":"u-cycle","current":"u-cycle","status":"idle","run_id":80,
               "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"50",
               "run_bearer":"tok-80"}'
say u-cycle "Login expired - please run /login"

spend_ladder 80; OC1="$TDIR/c1.out"; STALL "$OC1"
t  "a spent ladder charges the TICKET"   "harness-error cycle 1 of 3"    cat "$OC1"
t  "and the count is on disk"            "1"                             cycles
nt "one cycle escalates nothing"         "escalated #50"                 cat "$OC1"

spend_ladder 81; OC2="$TDIR/c2.out"; STALL "$OC2"
t  "a successor run does not reset it"   "harness-error cycle 2 of 3"    cat "$OC2"
nt "and two still escalate nothing"      "escalated #50"                 cat "$OC2"

spend_ladder 82; OC3="$TDIR/c3.out"; STALL "$OC3"
t  "the third reaches a human"    "escalated #50 → env-issue #99 (suppressed)" cat "$OC3"
t  "the env-issue names the harness"  "stuck harness error: ticket #50"  cat "$FIX.log"
nt "not a stuck resume"               "stuck resume: ticket #50"         cat "$FIX.log"
t  "the ticket is suppressed"            '"ticket": 50'                  cat "$SUP/50.json"
t  "against the state it stuck in"       '"state": "in-progress"'        cat "$SUP/50.json"
t  "and the count survives the escalation"  "3"                          cycles

spend_ladder 82; OC4="$TDIR/c4.out"; STALL "$OC4"
t  "a suppressed ticket spends no further cycle" \
   "suppressed; the harness-error ladder stands untouched"               cat "$OC4"
t  "so the count does not move"          "3"                             cycles
nt "and nothing is escalated a second time" "escalated #50"              cat "$OC4"

# Recovery is the ONE event that clears it — not a successor being delivered to.
rm -f "$SUP/50.json"
say u-cycle "Re-read the ticket and re-stated the gate verdict; the work stands where it was."
OC5="$TDIR/c5.out"; STALL "$OC5"
t  "a worker answering as itself clears the ticket's cycles" "ladder is cleared" cat "$OC5"
t  "and the count is gone"               "<absent>"                      cycles

# The bearerless meta rode every tick of this drill and never spent a rung.
t  "a bearerless meta never climbs the ladder"  "0"                      mfield u-nobearer stall_attempts
t  "and is never handed off for it"      "<absent>"                      mfield u-nobearer stall_exhausted

# =========================================================================
# THE REAL TICK REACHES IT. A phase that works when called by name and is
# never reached by `all` is the whole feature silently missing in production —
# the tick launchd runs is `_sweep_api.sh all`, nothing else. Driven with the
# budget at zero so the dispatch phase (which claims and spawns) is gated out
# and the empty relay/resume feeds return at once; marking a fresh meta needs
# no budget, so it still proves the phase ran.
# =========================================================================
meta u-allcheck '{"uuid":"u-allcheck","current":"u-allcheck","status":"idle","run_id":78,
                  "fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"49",
                  "run_bearer":"tok-78"}'
say u-allcheck "API Error: 529 Overloaded. This is a server-side issue, usually temporary."
OALL="$TDIR/all.out"
SW env BOARD_SWEEP_TICK_BUDGET=0 "$SCRIPTS/_sweep_api.sh" all > "$OALL" 2>&1 || true
t  "the whole-tick run reaches the stall phase" "#49 run 78"             cat "$OALL"
t  "and stamps the meta it found"        "78"                            mfield u-allcheck stall_run

# =========================================================================
# The phase is addressable on its own, and named in the usage line.
# =========================================================================
rc 0 "stall runs as a phase of its own"  env HOME="$TESTHOME" DAEMON_HOME="$DH" \
  SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
  sh -c "cd '$r' && '$SCRIPTS/_sweep_api.sh' stall"
# The needle stops where the list starts: a phase added in the middle of it
# (review-recover) is not this drill's business, and pinning the whole line
# made the usage message fail a test about the stall phase.
t  "and an unknown phase names it"       "usage: _sweep_api.sh [renew|stall" \
  env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
  BOARD_CREDENTIALS_FILE="$CREDS" sh -c "cd '$r' && '$SCRIPTS/_sweep_api.sh' nope"

finish
