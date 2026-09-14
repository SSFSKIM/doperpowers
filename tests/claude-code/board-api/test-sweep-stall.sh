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
# THE HAND-OFF pins: once the ladder is spent, phase 1 WITHHOLDS the lease.
# That is the whole terminal step on this binding, because automation holds no
# transition authority: the lease expires, the server reclaims the run, and the
# resume phase's successor path takes over with its own ladder and its own
# env-issue escalation.
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
 {"method":"POST","path":"/runs/76/renew","status":200,"body":{"renewed":true}}
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
# The phase is addressable on its own, and named in the usage line.
# =========================================================================
rc 0 "stall runs as a phase of its own"  env HOME="$TESTHOME" DAEMON_HOME="$DH" \
  SMINOS_CLI="$DS/sminos" BOARD_CREDENTIALS_FILE="$CREDS" \
  sh -c "cd '$r' && '$SCRIPTS/_sweep_api.sh' stall"
t  "and an unknown phase names it"       "renew|stall|relay"             \
  env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
  BOARD_CREDENTIALS_FILE="$CREDS" sh -c "cd '$r' && '$SCRIPTS/_sweep_api.sh' nope"

finish
