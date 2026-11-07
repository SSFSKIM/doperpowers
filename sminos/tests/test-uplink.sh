#!/usr/bin/env bash
#
# The uplink: `sminos daemon uplink`, the process `daemon run` keeps beside
# its tick loop, which speaks RL10 to the machine's endpoint once the machine
# is cut over (endpoint_standin.py stands in for mawsd's endpoint), and runs
# on nothing before: a machine with no identity.json starts no uplink,
# whatever a stray hub.json says. Pins DC4.G4 on RL10: what the endpoint
# sends is drained and an event reaches a local member within a second while
# the tick sits in a hung git fetch of a hub-less project, and while a
# derivation runs; what fails its shape never enters the log; the uplink and
# the tick loop restart and fail apart; the run lock holds, and a change of
# the daemon's code restarts it in place, the uplink back within seconds; an
# event the uplink imports while a tick is mid-delivery to the same member is
# delivered once. And the cutover itself: an endpoint probed while no uplink
# runs, a whole welcome cutting the machine over for good, and the cutover
# undone.
# Hermetic: HOME and SMINOS_HOME are temporary (short, for the inbox sockets),
# `claude` is a stub, and nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="$PLUGIN_ROOT/skills/sminos/scripts"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smu.XXXXXX)"
PIDS=()
cleanup() {
  rm -f "$T/ssh-gate" "$T/in-m.received.hold"
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
  # An uplink outlives no daemon run: wait for the last one to see its parent gone.
  for _ in $(seq 1 60); do pgrep -f "$T/" >/dev/null 2>&1 || break; sleep 0.05; done
  rm -rf "$T"
}
trap cleanup EXIT

pass() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL $1"; }
assert_equals() {
  if [[ "$1" == "$2" ]]; then pass "$3"; else
    fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
  if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:900}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi; }
assert_within() { # seconds bound label — seconds is a number, or "never"
  if [[ "$1" != never ]] && python3 -c 'import sys; sys.exit(float(sys.argv[1]) > float(sys.argv[2]))' "$1" "$2"; then
    pass "$3 (${1}s)"; else fail "$3"; echo "    took ${1}s, bound ${2}s"; fi
}
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; }
# Polls every 50 ms until the command holds. The leading count is kept for the
# call sites, but the ceiling is one liveness bound, 30 s, not a claim about the
# machine's speed (ci-kit §6): a loaded host is slow, not wrong.
until_true() { # tries command...
  local end=$((SECONDS + 30)); shift
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 0.05
  done
}
alive() { kill -0 "$1" 2>/dev/null; }
dead() { ! kill -0 "$1" 2>/dev/null; }
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME MAWS_USER_DATA SMINOS_RL10
export HOME="$T/home"
export SMINOS_HOME="$T/s"
export DAEMON_HOST=testhost
export SMINOS_DERIVE_EVERY=0
export STUB_STATE="$T/stub"
mkdir -p "$HOME/.claude/sessions" "$STUB_STATE" "$T/bin"
DLOG="$SMINOS_HOME/daemon.log"

# A stub `claude`: no fleet, and derive's headless fork answering after
# STUB_FORK_SLEEP seconds, marking its start and its end.
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) echo "[]"; exit 0 ;;
esac
case " $* " in
  *" --fork-session "*)
    : > "$STUB_STATE/fork-started"
    sleep "${STUB_FORK_SLEEP:-0}"
    : > "$STUB_STATE/fork-ended"
    printf '{"type": "result", "is_error": false, "result": "watches the hub", "session_id": "x"}\n'
    exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

# A live session's inbox (inbox_standin.py): appends each frame and answers
# nothing; while <received>.hold exists a frame is written and marked
# (<received>.held) and its close waits (a connection that sends nothing, a
# liveness probe, is closed at once).
INBOX="$T/in-m.received"
: > "$INBOX"
python3 "$SCRIPT_DIR/inbox_standin.py" "$T/in-m.sock" "$INBOX" & INBOX_PID=$!
PIDS+=("$INBOX_PID")
until_true 100 test -S "$T/in-m.sock"


# The hub the hub project names, as the endpoint's welcome names it too:
# nothing serves it, and nothing here dials it (the endpoint is the machine's
# one upstream).
HUB="http://127.0.0.1:9"
export SCRIPTS   # the scripts' directory, for the helpers below that import sminos

# ---- a hub project with one live member, m, and a hub-less project mirrored over a stand-in ssh
HPR="$T/hp"
mkdir -p "$HPR"
gitq init -q "$HPR"
(cd "$HPR" && "$SMINOS" project init --name hubproj >/dev/null)
python3 - "$HPR/.smns" "$HUB" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["hub"] = {"url": sys.argv[2], "org": "org-1"}
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
HP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project"])' "$HPR/.smns")"
export HP OTHER_PROJECT=0d9e8f7a-6b5c-4d3e-a2f1-0e9d8c7b6a59 MEMBER=4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c
HPLOG="$SMINOS_HOME/projects/$HP/log"
M=5a000001-0000-4000-8000-0000000000a1
export M
printf '{"pid":%s,"sessionId":"%s","name":"m","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$M" "$HPR" "$T/in-m.sock" > "$HOME/.claude/sessions/m.json"
mkdir -p "$HOME/.claude/projects/hp"
for i in 1 2 3 4 5 6 7 8 9 10; do
  printf '{"type":"user","message":{"role":"user","content":"prompt %s"}}\n' "$i" >> "$HOME/.claude/projects/hp/$M.jsonl"
done

cat > "$T/fake-ssh" <<'SSH'
#!/bin/sh
# ssh, as GIT_SSH_VARIANT=simple calls it (host, command): run the command here, after the gate lifts.
# SSH_ENTERED marks a call held at the gate, never one that passed before the gate was set.
if [ -n "${SSH_GATE:-}" ] && [ -f "$SSH_GATE" ]; then
  [ -z "${SSH_ENTERED:-}" ] || : > "$SSH_ENTERED"
  while [ -f "$SSH_GATE" ]; do sleep 0.05; done
fi
exec sh -c "$2"
SSH
chmod +x "$T/fake-ssh"
export GIT_SSH_COMMAND="$T/fake-ssh" GIT_SSH_VARIANT=simple SSH_GATE="$T/ssh-gate" SSH_ENTERED="$T/ssh-entered"
gitq init -q --bare "$T/stall.git"
SR="$T/sr"
mkdir -p "$SR"
gitq init -q "$SR"
(cd "$SR" && "$SMINOS" project init --name stall --remote "ssh://stall$T/stall.git" >/dev/null)
run "$SMINOS" daemon tick
assert_contains "$OUT" "stall: synced" "the hub-less project syncs over its remote"
assert_contains "$OUT" "hubproj: reconciled 1" "m joins the hub project"

# ---- the helpers the cases below share
uplink_pid() { sed -n 's/^pid \([0-9]*\) .*/\1/p' "$SMINOS_HOME/daemon/uplink.lock" 2>/dev/null || true; }
# The loop marks each tick's end on daemon/ticked's mtime; a quiet project's record is not written.
ticked() { python3 -c 'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$SMINOS_HOME/daemon/ticked" 2>/dev/null || true; }
ticked_since() { [ "$(ticked)" != "$1" ]; }
# The running loop takes the derivation lock (a file) every tick, so it can come
# back between the rm and the mkdir: retried until the directory is in place.
derive_lock_is_a_dir() { rm -f "$SMINOS_HOME/daemon/derive.lock"; mkdir "$SMINOS_HOME/daemon/derive.lock" 2>/dev/null; }
# daemon run restarts in place on a change to its code: the same pid on the
# new code, never an exit a service manager would throttle, and the uplink
# back within seconds. What a change brings is seen: each changed script
# (under $CODE, a copy of the code) marks, as it is imported, which process
# imported it.
change() { # script — new code in it, marking each import
  printf '\nopen("%s/imported-%%s-%%d" %% (__name__, os.getpid()), "w").close()\n' "$T" >> "$CODE/$1"
}
imported() { [[ -n "$2" && -e "$T/imported-$1-$2" ]]; }
restarts() { # pid — the epoch time of each of its restarts in place, one a line
  python3 - "$DLOG" "$1" <<'PY'
import calendar, sys, time
mark = "daemon run (pid %s): its code changed; restarting in place" % sys.argv[2]
for line in open(sys.argv[1]):
    if mark in line:
        stamp, ms = line.split(" ", 1)[0].rstrip("Z").split(".")
        print("%.3f" % (calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S")) + int(ms) / 1000))
PY
}
gap() { # pid — seconds from its last restart in place to the next connection its uplink opened
  python3 - "$DLOG" "$1" <<'PY'
import datetime, sys
lines = open(sys.argv[1]).read().splitlines()
mark = "daemon run (pid %s): its code changed; restarting in place" % sys.argv[2]
i = max(i for i, line in enumerate(lines) if mark in line)
j = next((j for j in range(i + 1, len(lines)) if "uplink: connected to" in lines[j]), None)
at = lambda line: datetime.datetime.strptime(line.split(" ", 1)[0], "%Y-%m-%dT%H:%M:%S.%fZ")
print("never" if j is None else "%.2f" % (at(lines[j]) - at(lines[i])).total_seconds())
PY
}
started_in() { grep -Fc "daemon run started (pid $1," "$DLOG" || true; }
# An uplink whose supervisor died while it started: the supervisor names
# itself at spawn, so a parent gone before the uplink could look (orphaned in
# its startup or imports) is never mistaken for it, and the orphan neither
# serves nor holds uplink.lock.
cat > "$T/launch.py" <<'PY'
import os, subprocess, sys
# daemon run's spawn of its uplink, then gone at once.
p = subprocess.Popen([sys.argv[1], "daemon", "uplink"], env={**os.environ, "SMINOS_UPLINK_PARENT": str(os.getpid())},
                     stdin=subprocess.DEVNULL, stdout=open(sys.argv[2], "a"), stderr=subprocess.STDOUT)
print(p.pid)
PY
restarted_after() { local p; p="$(uplink_pid)"; [[ -n "$p" && "$p" != "$1" ]] && alive "$p"; }
status_has() { "$SMINOS" daemon status | grep -Fq "$1"; }
run_started() { grep -Fq "daemon run started (pid $RUN," "$DLOG"; }
start_run() { # → RUN: a daemon run, its start said in daemon.log
  "$SMINOS" daemon run --interval 1 >> "$T/run.out" 2>&1 & RUN=$!
  PIDS+=("$RUN")
  until_true 200 run_started || true
}
# The uplink child of the daemon run that is RUN, if one runs.
uplink_child() { pgrep -P "$RUN" -f "daemon uplink" || true; }

# ---- a machine not cut over: no uplink, whatever a stray hub.json says (#153)
# Before the cutover there is nothing to connect to: the uplink exits at once,
# and daemon run's supervisor starts none (it waits, probing an endpoint when
# rl10.json names one). A hub.json, which enrolled a machine at the desk hub
# before RL10, is no credential: it holds the DX1 key the endpoint may ask for
# (legacy-key?, below), and nothing reads it as an enrollment.
echo "a machine not cut over:"
"$SMINOS" daemon uplink > "$T/uplink-none.out" 2>&1 & LONE=$!
until_true 100 dead "$LONE" || true
if dead "$LONE"; then pass "with no identity.json, the uplink exits at once"; else fail "with no identity.json, the uplink exits at once"; kill "$LONE"; fi
set +e; wait "$LONE"; RC=$?; set -e
assert_rc 0 "$RC" "with 0"
assert_contains "$(cat "$DLOG")" "uplink: this machine is not cut over to an endpoint (no $SMINOS_HOME/daemon/identity.json): nothing to connect" \
  "saying there is nothing to connect"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"
printf '{"hub": "%s", "org": "org-1", "machine": "testhost", "client_id": "cid-1", "client_secret": "secret-1", "key": "%s"}\n' \
  "$HUB" "$KEY" > "$SMINOS_HOME/daemon/hub.json"
chmod 600 "$SMINOS_HOME/daemon/hub.json"
"$SMINOS" daemon uplink > "$T/uplink-stray.out" 2>&1 & LONE=$!
until_true 100 dead "$LONE" || true
if dead "$LONE"; then pass "with a stray hub.json and no identity.json, the uplink still exits at once"; else
  fail "with a stray hub.json and no identity.json, the uplink still exits at once"; kill "$LONE"; fi
set +e; wait "$LONE"; RC=$?; set -e
assert_rc 0 "$RC" "with 0"
assert_equals "$(grep -c "uplink: this machine is not cut over to an endpoint" "$DLOG")" 2 "saying again that there is nothing to connect"
MARK=$(( $(wc -l < "$DLOG") + 1 ))
start_run
TICKED="$(ticked)"
until_true 200 ticked_since "$TICKED" || true
sleep 2
run "$SMINOS" daemon status
assert_contains "$OUT" "daemon: running (pid $RUN " "daemon run runs on a machine with a stray hub.json and no identity.json"
assert_not_contains "$OUT" "uplink" "its supervisor waits: daemon status names no uplink"
assert_equals "$(uplink_child)" "" "and no uplink child runs"
assert_not_contains "$(tail -n +"$MARK" "$DLOG")" "uplink" "daemon.log says nothing of one: none started, none exited"
assert_equals "$(test -f "$SMINOS_HOME/daemon/identity.json" && echo there || echo none)" none "nothing cut the machine over"
kill "$RUN"
set +e; wait "$RUN"; set -e

# ---- a position of this machine's own writer, refused, and what it writes next
# In-process, on the log plane as the endpoint feeds it (each event wrapped
# `{event, signer}`, #153 M6). A lying upstream sends a malformed event at
# testhost/<session>:1, which this machine refuses, spending the position. Its
# own next event there takes 2, which it uploads past the upstream's 1, and
# whose echo it imports as present.
echo "a refused position of this machine's own writer:"
OWN="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys, time
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
hl = hublog.HubLog(p, {"machine": "testhost"})
signer = {"kind": "machine", "name": "testhost"}
w = "testhost/5a000002-0000-4000-8000-0000000000b2"
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
forged = {"event": {"ts": ts, "writer": w, "seq": 1, "from": "x", "to": "*", "text": "forged"}, "signer": signer}
_, refused = hl.take([forged])
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
hl.have, hl.sent = {w: 1}, {w: 1}
uploaded = [e["seq"] for frame, _ in hl.uploads() for e in frame["events"] if e["writer"] == w]
appended, echoed = hl.take([{"event": mine, "signer": signer}])
print(json.dumps([[f["reason"] for f in refused], mine["seq"], uploaded, appended, [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$OWN" '[["bad-shape"], 2, [2], 0, []]' \
  "the malformed event is refused, the machine's next event takes the position after it, uploads past the upstream's 1, and its echo imports as present"

# A writer under this machine's prefix that it never allocates is no file the
# allocator can open: the frame still yields its rejection and the valid event.
echo "a refused position under this machine's prefix that it does not allocate:"
LONG="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys, time
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
hl = hublog.HubLog(p, {"machine": "testhost"})
signer = {"kind": "machine", "name": "other"}
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
junk = {"event": {"ts": ts, "writer": "testhost/" + "x" * 300, "seq": 1, "from": "x", "to": "*", "text": "junk"},
        "signer": signer}
good = {"event": {"ts": ts, "writer": "other/5a000003-0000-4000-8000-0000000000c3", "seq": 1, "kind": "say",
                  "from": "o", "to": "*", "text": "valid"}, "signer": signer}
appended, refused = hl.take([junk, good])
print(json.dumps([[f["reason"] for f in refused], appended]))
PY
)"
assert_equals "$LONG" '[["bad-shape"], 1]' \
  "an unusable writer under the machine's prefix is refused and the valid event after it in the frame is appended"

# A malformed event at a position this machine's own event holds is refused
# bad-shape, but its position is coordinated like any own-writer refusal: it is
# not tombstoned over the genuine event, whose echo imports as present.
echo "a malformed event at a position this machine's own event holds:"
HELD="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
hl = hublog.HubLog(p, {"machine": "testhost"})
signer = {"kind": "machine", "name": "testhost"}
w = "testhost/5a000004-0000-4000-8000-0000000000d4"
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
_, refused = hl.take([{"event": {"writer": w, "seq": mine["seq"], "ts": None, "kind": "say"}, "signer": signer}])
appended, echoed = hl.take([{"event": mine, "signer": signer}])
print(json.dumps([mine["seq"], [f["reason"] for f in refused], appended, [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$HELD" '[1, ["bad-shape"], 0, []]' \
  "the malformed event is refused bad-shape, and the genuine event's echo imports as present, not refused as spent"

# An event at a position another event holds here is refused `conflict`: its
# shape is good, its position taken. The position stays the held event's,
# whose echo still imports as present.
echo "an event at a position another event holds:"
CONFLICT="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
hl = hublog.HubLog(p, {"machine": "testhost"})
signer = {"kind": "machine", "name": "testhost"}
w = "testhost/5a000005-0000-4000-8000-0000000000e5"
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
other = {"event": {**mine, "text": "another event at the same position"}, "signer": signer}
appended, refused = hl.take([other])
echo_appended, echoed = hl.take([{"event": mine, "signer": signer}])
print(json.dumps([mine["seq"], appended, [[f["reason"], f["event"]] for f in refused], echo_appended,
                  [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$CONFLICT" '[1, 0, [["conflict", {"writer": "testhost/5a000005-0000-4000-8000-0000000000e5", "seq": 1}]], 0, []]' \
  "a different event at a held position is refused conflict, and the held event's echo imports as present"

# ---- RL10: the machine cuts over to its endpoint (O12 M5)
# The endpoint stand-in (endpoint_standin.py) writes rl10.json where
# MAWS_USER_DATA puts it. One that names no endpoint (mode 644) is said once.
# One that does is probed while no uplink runs: a welcome without the whole
# identity (an endpoint not enrolled yet), a wrong token and a refusal each
# leave the machine as it was, not cut over and with no uplink. Only a whole
# welcome cuts the machine over, for good: a hub.json written after it, or the
# endpoint gone, starts nothing else. The endpoint's policy is the machine's,
# which delivery reads. The stray hub.json above stays: the endpoint's
# legacy-key? reads its DX1 key, and nothing else reads it.
echo "RL10, the endpoint (local-only):"
export MAWS_USER_DATA="$T/maws"
EPDIR="$MAWS_USER_DATA/mawsd/endpoint"
IDENTITY="{\"org\": \"org-1\", \"hub\": \"$HUB\", \"name\": \"testhost\", \"former\": [], \"ref\": \"ref-testhost\", \"enrolled\": \"2026-10-27T00:00:00.000Z\"}"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPDIR" "{\"identity\": {\"name\": \"testhost\", \"hub\": \"$HUB\", \"former\": []}}" &
PIDS+=("$!")
until_true 100 test -S "$EPDIR/ctl.sock"
ep() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPDIR" "$@"; }
epq() { ep state | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
cut_over() { test -f "$SMINOS_HOME/daemon/identity.json"; }
probed() { grep -Fq "uplink: the endpoint, probed: $1" "$DLOG"; }
no_uplink() { # label — the machine is not cut over, and no uplink runs
  assert_equals "$(cut_over && echo there || echo none)" none "$1: no identity.json"
  assert_equals "$(uplink_child)" "" "$1: no uplink runs"
}
ep rl10 '{"mode": "644"}' >/dev/null
NOEP="is mode 644, not 600"
start_run
sleep 2
assert_equals "$(grep -c "rl10: no endpoint: .*$NOEP" "$DLOG")" 1 "an rl10.json of mode 644 is no endpoint, said once in daemon.log"
assert_equals "$(epq 'd["conns"]')" 0 "and nothing dials its socket"
no_uplink "with an rl10.json of mode 644"

echo "  an endpoint not enrolled, a wrong token, a refusal:"
ep rl10 '{}' >/dev/null
until_true 200 probed "present but not enrolled" || true
assert_equals "$(probed "present but not enrolled" && echo said)" said \
  "a welcome without the identity's org and ref is an endpoint not enrolled (daemon.log)"
no_uplink "an endpoint not enrolled"
run "$SMINOS" daemon status
assert_contains "$OUT" "endpoint: present at $EPDIR/rl10.json but not enrolled: no complete welcome yet, so this machine is not cut over" \
  "daemon status shows the endpoint present but not enrolled"
assert_not_contains "$OUT" "uplink" "and no uplink"
ep set "{\"identity\": $IDENTITY}" >/dev/null
ep rl10 '{"token": "0000000000000000000000000000000000000000000000000000000000000000"}' >/dev/null
until_true 200 probed "it did not welcome this machine (the endpoint closed the socket" || true
assert_equals "$(probed "it did not welcome this machine (the endpoint closed the socket" && echo said)" said \
  "a wrong token: the endpoint closes the socket (daemon.log)"
no_uplink "a wrong token"
ep set '{"refuse_reason": "not-listed"}' >/dev/null
ep rl10 '{"token": "1111111111111111111111111111111111111111111111111111111111111111"}' >/dev/null
until_true 200 probed "it did not welcome this machine (the endpoint refused the hello: not-listed)" || true
assert_equals "$(probed "it did not welcome this machine (the endpoint refused the hello: not-listed)" && echo said)" said \
  "a refusal (daemon.log)"
no_uplink "a refusal"
assert_equals "$(epq '[f["frame"]["t"] for f in d["received"]]')" "$(epq '["hello"] * len(d["hellos"])')" \
  "the probes sent the endpoint nothing but their hellos"
ep set '{"refuse_reason": null}' >/dev/null

echo "  the cutover:"
HELLOS="$(epq 'len(d["hellos"])')"
ep rl10 '{}' >/dev/null
until_true 200 cut_over || true
assert_equals "$(cut_over && echo there)" there "a whole welcome to the probe writes identity.json"
rl10_up() { local p; p="$(uplink_child)"; [[ -n "$p" ]] && grep -Fq "uplink: started (pid $p) for the endpoint (RL10, local-only)" "$DLOG"; }
until_true 200 rl10_up || true
assert_equals "$(rl10_up && echo up)" up "and only then does an uplink start, on RL10 (daemon.log)"
UP="$(uplink_child)"
assert_equals "$(python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))' "$SMINOS_HOME/daemon/identity.json")" \
  0o600 "identity.json is mode 600"
on_rl10() { [ "$(epq 'len(d["hellos"])')" -ge $((HELLOS + 2)) ]; }
until_true 200 on_rl10 || true
assert_equals "$(epq "[len(d['hellos']) - $HELLOS, all(h['hello']['token'] == d['token'] for h in d['hellos'][$HELLOS:])]")" "[2, true]" \
  "the probe's hello and then the RL10 uplink's, each with rl10.json's token"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: RL10 (local-only), running (pid $UP" "daemon status prints uplink: RL10 (local-only)"
rl10_hello() { [ "$(epq "any(f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$HP' for f in d['received'])")" = true ]; }
until_true 200 rl10_hello || true
assert_equals "$(rl10_hello && echo yes)" yes "the hub project is opened on the endpoint's socket"
run "$SMINOS" hub show
assert_contains "$OUT" "cut over" "hub show prints the identity, cut over"

echo "  the endpoint's policy, which delivery reads:"
# The endpoint's policy changed and sent (its own, which its answer to a policy-set applies the change to: the
# hello's, ceiling "settings", until then).
ep set '{"policy": {"read_only": true, "ceiling": "default"}}' >/dev/null
ep send '{"frames": [{"t": "policy", "read_only": true, "ceiling": "default"}]}' >/dev/null
read_only_is() { "$SMINOS" daemon policy | grep -q "read-only: $1"; }
until_true 200 read_only_is yes || true
assert_equals "$(read_only_is yes && echo yes)" yes "a policy frame from the endpoint makes the machine read-only"
cat > "$T/outside.py" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_hublog as hublog
p = sminos.find_project(os.environ["HP"])
w = "hub/" + os.environ["MEMBER"]
path = os.path.join(p.home, "log", w.replace("/", ".") + ".jsonl")
try:
    held = [json.loads(l)["seq"] for l in open(path) if l.strip()]
except FileNotFoundError:
    held = []
last = max(held, default=0)
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
e = {"ts": ts, "writer": w, "seq": last + 1, "kind": "human", "from": "human", "member": os.environ["MEMBER"],
     "to": [{"session": os.environ["M"], "alias": "m"}], "text": sys.argv[1], "created": ts}
print(hublog.append_verbatim(p, e))
PY
assert_equals "$(python3 "$T/outside.py" "said from outside while read-only")" appended "an event from outside is in the log"
# Settled refused-read-only: the outcome kept in the project's outbox, or, once the uplink has sent it (and
# dropped it from the outbox, at any moment), the `delivery` outcome the endpoint received.
refused_ro() {
  grep -rqF "refused-read-only" "$SMINOS_HOME/projects/$HP/" 2>/dev/null \
    || [ "$(epq "any(f['frame'].get('t') == 'session' and f['frame']['message'].get('kind') == 'delivery' and f['frame']['message']['body'].get('outcome') == 'refused-read-only' for f in d['received'])")" = true ]
}
until_true 200 refused_ro || true
assert_equals "$(refused_ro && echo yes)" yes "delivery settles it refused-read-only"
assert_not_contains "$(cat "$INBOX")" "said from outside while read-only" "and m never gets it"
run "$SMINOS" daemon policy --read-only off
assert_contains "$OUT" "This machine's policy is its endpoint's" "daemon policy says the endpoint decides"
asked() { [ "$(epq "any(f['frame'] == {'t': 'policy-set', 'read_only': False} for f in d['received'])")" = true ]; }
until_true 200 asked || true
assert_equals "$(asked && echo yes)" yes "the uplink asks the endpoint for the change (policy-set)"
until_true 200 read_only_is no || true
assert_equals "$(python3 -c 'import json, sys; print(json.dumps(json.load(open(sys.argv[1]))))' "$SMINOS_HOME/daemon/policy.json")" \
  '{"read_only": false, "ceiling": "default", "endpoint": {"read_only": false, "ceiling": "default"}}' \
  "and the policy settles on the endpoint's answer"
# A person's words from outside are delivered on the endpoint's verdict (O12 M6): it answers words.
ep set '{"verdict": "words"}' >/dev/null
python3 "$T/outside.py" "said from outside after read-only" >/dev/null
until_true 200 grep -q "said from outside after read-only" "$INBOX" || true
assert_contains "$(cat "$INBOX")" "said from outside after read-only" "an event from outside is delivered again"
assert_equals "$(epq "any(f['frame'].get('t') == 'words?' and f['frame']['event'].get('text') == 'said from outside after read-only' for f in d['received'])")" true \
  "on the endpoint's verdict, asked with words?"


echo "  for good:"
printf '{"hub": "%s", "org": "org-1", "machine": "testhost", "client_id": "cid-1", "client_secret": "secret-1", "key": "%s", "enrolled": "%s"}\n' \
  "$HUB" "$KEY" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$SMINOS_HOME/daemon/hub.json"
sleep 2
assert_equals "$(uplink_child)" "$UP" "a fresh DX7 credential in hub.json after the cutover restarts nothing"
ep unlink-rl10 >/dev/null
until_true 100 dead "$UP" || true
if dead "$UP"; then pass "with rl10.json removed, the uplink child exits"; else fail "with rl10.json removed, the uplink child exits"; fi
assert_contains "$(cat "$DLOG")" "uplink (pid $UP): rl10.json is gone, and this machine is cut over: no uplink runs until the endpoint does" \
  "daemon.log says why"
assert_contains "$(cat "$DLOG")" "uplink: this machine is cut over to its endpoint, which is not running" "and that it waits for the endpoint"
sleep 2
assert_equals "$(uplink_child)" "" "no other uplink starts in its place"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: cut over; the endpoint is not running" "daemon status says cut over; the endpoint is not running"
CUTOVER="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["cutover"])' "$SMINOS_HOME/daemon/identity.json")"
HELLOS="$(epq 'len(d["hellos"])')"
ep rl10 '{}' >/dev/null
again() { [ "$(epq 'len(d["hellos"])')" -gt "$HELLOS" ]; }
until_true 200 again || true
sleep 1
assert_equals "$(epq "len(d['hellos']) - $HELLOS")" 1 "rl10.json back: the uplink speaks to the endpoint again, once"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["cutover"])' "$SMINOS_HOME/daemon/identity.json")" \
  "$CUTOVER" "the cutover's time is kept"
assert_equals "$(epq 'd["legacy"]["key"]')" "\"$KEY\"" "the endpoint holds the DX1 key"

# ---- the cutover undone (O12 M7c, O14's undo): which order the two local
# steps take decides where the machine ends. identity.json removed while the
# endpoint still serves RL10 cuts it over again at once, through the probe;
# the endpoint taken out first (rl10.json and its socket gone, as `mawsd
# endpoint unenroll` leaves it), then identity.json, leaves RL10 for good: no
# uplink runs, a stray hub.json there or not, as on a machine never enrolled.
echo "  the cutover undone:"
cutover_at() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["cutover"])' "$SMINOS_HOME/daemon/identity.json"; }
until_true 200 status_has "uplink: RL10 (local-only), running" || true
UP="$(uplink_child)"
CUTOVER="$(cutover_at)"
rm "$SMINOS_HOME/daemon/identity.json"
until_true 200 cut_over || true
assert_equals "$(cut_over && echo there || echo none)" there \
  "identity.json removed while the endpoint serves RL10: the probe cuts the machine over again"
assert_contains "$(cat "$DLOG")" \
  "uplink (pid $UP): identity.json is gone, which undoes the cutover: no uplink runs until a probe's welcome cuts this machine over again" \
  "the supervisor stopped the RL10 uplink first (daemon.log)"
if [ "$(cutover_at)" != "$CUTOVER" ]; then pass "at a new cutover time"; else fail "at a new cutover time"; fi
back_on_rl10() { local p; p="$(uplink_child)"; [[ -n "$p" && "$p" != "$UP" ]] && status_has "uplink: RL10 (local-only), running (pid $p"; }
until_true 200 back_on_rl10 || true
UP="$(uplink_child)"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: RL10 (local-only), running (pid $UP" "and the uplink is back on RL10"
cp "$SMINOS_HOME/daemon/identity.json" "$T/identity.kept"

ep stop >/dev/null
until_true 100 dead "$UP" || true
if dead "$UP"; then pass "the endpoint taken out (rl10.json and its socket gone): the RL10 uplink exits"; else
  fail "the endpoint taken out (rl10.json and its socket gone): the RL10 uplink exits"; fi
until_true 200 status_has "uplink: cut over; the endpoint is not running" || true
assert_equals "$(status_has "uplink: cut over; the endpoint is not running" && echo yes)" yes \
  "daemon status: cut over; the endpoint is not running"
MARK=$(( $(wc -l < "$DLOG") + 1 ))
rm "$SMINOS_HOME/daemon/identity.json"
sleep 2
# Acceptance 4 of #153, the supervisor's clause: hub.json is there, identity.json is not.
assert_equals "$(test -f "$SMINOS_HOME/daemon/hub.json" && echo there)" there "then identity.json removed, a stray hub.json left in place"
assert_equals "$(uplink_child)" "" "the supervisor waits: no uplink runs"
run "$SMINOS" daemon status
assert_not_contains "$OUT" "uplink" "daemon status names none, as on a machine never enrolled"
assert_not_contains "$(tail -n +"$MARK" "$DLOG")" "uplink: started" "and none started since the cutover was undone"
assert_equals "$(cut_over && echo there || echo none)" none "nothing cuts it over again: no endpoint is there to probe"

mv "$SMINOS_HOME/daemon/hub.json" "$T/hub.kept"
cp "$T/identity.kept" "$SMINOS_HOME/daemon/identity.json"
until_true 200 status_has "uplink: cut over; the endpoint is not running" || true
assert_equals "$(status_has "uplink: cut over; the endpoint is not running" && echo yes)" yes \
  "cut over again with no hub.json and no endpoint: the endpoint is not running"
rm "$SMINOS_HOME/daemon/identity.json"
sleep 2
run "$SMINOS" daemon status
assert_not_contains "$OUT" "uplink" "then identity.json removed with no hub.json: no uplink runs, local-only, as on a machine never enrolled"
assert_equals "$(cut_over && echo there || echo none)" none "and nothing cuts it over again"
kill "$RUN"
set +e; wait "$RUN"; set -e
assert_not_contains "$(cat "$DLOG")" "$KEY" "the DX1 key handed to the endpoint is in no log line"

# ---- RL10: the uplink child's supervision (board #153 M3c)
# The uplink child as daemon run keeps it, on a machine cut over to its
# endpoint: the child speaks RL10 to endpoint_standin.py, and nothing of the
# hub is in reach (no hub.json). The machine cuts over as a new
# one does, through `daemon probe` and the endpoint's whole welcome. A web
# human for m comes down the socket as the endpoint relays one, wrapped and
# verified ({event, signer}), and reaches m on the endpoint's `words` verdict,
# which the uplink asks for (O12 M6): the import, the ask and the push are all
# the uplink's, the tick loop's nowhere in them.
echo "RL10, the uplink child's supervision:"
DLOG_AT=$(( $(wc -l < "$DLOG") + 1 ))   # daemon.log from here on is this block's
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPDIR" \
  "{\"identity\": $IDENTITY, \"verdict\": \"words\", \"ask_legacy\": false}" &
PIDS+=("$!")
until_true 100 test -S "$EPDIR/ctl.sock"
run "$SMINOS" daemon probe
assert_contains "$OUT" "welcomed as testhost of org org-1: this machine is cut over" \
  "with no hub.json, daemon probe's whole welcome cuts the machine over"
assert_equals "$(test -e "$SMINOS_HOME/daemon/hub.json" && echo there || echo none) $(cut_over && echo cut || echo not)" "none cut" \
  "identity.json is written, and no hub.json is there"
# The test's hands on the endpoint stand-in's ctl socket: a web human for m
# down the socket (a send, or one timed until its text reaches the inbox),
# a burst of frames, and a frame every 50 ms while a file exists.
cat > "$T/epctl.py" <<'PY'
import json, os, socket, sys, time
directory, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]

def ctl(op, arg=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(os.path.join(directory, "ctl.sock"))
    s.sendall((json.dumps({"op": op, "arg": arg or {}}) + "\n").encode())
    data = b""
    while True:
        chunk = s.recv(1 << 16)
        if not chunk:
            break
        data += chunk
    s.close()
    return json.loads(data or b"{}")

def human(seq, text, signer=True, **changes):
    member = os.environ["MEMBER"]
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    e = {"ts": ts, "writer": "hub/" + member, "seq": seq, "kind": "human", "from": "human", "member": member,
         "to": [{"session": os.environ["M"], "alias": "m"}], "text": text, "created": ts, **changes}
    wrapped = {"event": e}
    if signer:
        wrapped["signer"] = {"kind": "device", "member": member, "device": "dev-1", "keyId": "k-dev-1"}
    return wrapped

def events(project, *wrapped):
    return {"t": "events", "project": project, "events": list(wrapped)}

hp = os.environ["HP"]
if cmd == "send":  # seq text — a web human for m
    print(json.dumps(ctl("send", {"frames": [events(hp, human(int(args[0]), args[1]))]})))
elif cmd == "deliver":  # seq text inbox — seconds until the text is in the inbox, or never
    inbox, text = args[2], args[1].encode()
    t0 = time.time()
    answer = ctl("send", {"frames": [events(hp, human(int(args[0]), args[1]))]})
    while answer.get("ok") and time.time() - t0 < 5:
        if text in open(inbox, "rb").read():
            print("%.2f" % (time.time() - t0))
            sys.exit(0)
        time.sleep(0.02)
    print("never")
elif cmd == "forged":  # seq — what no log takes, each at that position of hub/<member> or of no hub project here
    seq = int(args[0])
    print(json.dumps(ctl("send", {"frames": [
        events(hp, human(seq, "forged: no signer", signer=False)),
        events(hp, human(seq, "forged: a verified key of its own", verified={"signer": {"kind": "device"}})),
        events(hp, human(seq, "forged: a writer no log holds", writer="hub")),
        events(os.environ["OTHER_PROJECT"], human(seq, "forged: another project's")),
    ]})))
elif cmd == "burst":  # frames bytes — that many frames the uplink passes by, in sends under the ctl line's bound
    n, size = int(args[0]), int(args[1])
    frame = {"t": "noise", "pad": "x" * size}
    per = max(1, (1 << 19) // (size + 32))
    t0, status = time.time(), "ok"
    for i in range(0, n, per):
        if not ctl("send", {"frames": [frame] * min(per, n - i)}).get("ok"):
            status = "failed"
    print("%s %.2f" % (status, time.time() - t0))
elif cmd == "flow":  # path — a frame every 50 ms until the file goes away, to whichever connection is up
    while os.path.exists(args[0]):
        try:
            ctl("send", {"frames": [{"t": "noise"}]})
        except OSError:
            pass
        time.sleep(0.05)
PY
epctl() { python3 "$T/epctl.py" "$EPDIR" "$@"; }
# The positions of hub/$MEMBER from here on: one past every one held or spent here.
RSEQ="$(python3 - "$HPLOG/hub.$MEMBER.jsonl" "$SMINOS_HOME/projects/$HP/uplink.json" "hub/$MEMBER" <<'PY'
import json, sys
held = [json.loads(l)["seq"] for l in open(sys.argv[1]) if l.strip()]
try:
    spent = json.load(open(sys.argv[2])).get("spent", {}).get(sys.argv[3], [])
except (OSError, ValueError):
    spent = []
print(max(held + spent) + 1)
PY
)"
rl10_deliver() { # text → TOOK: the next position's web human, timed to m's inbox
  TOOK="$(epctl deliver "$RSEQ" "$1" "$INBOX")"
  RSEQ=$((RSEQ + 1))
}
ep_hellos() { epq 'len(d["hellos"])'; }
hp_open_now() { # the connection up now has said hello for the hub project
  [ "$(epq "any(f['conn'] == d['current'] and f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$HP' for f in d['received'])")" = true ]; }
hellos_above() { [ "$(ep_hellos)" -gt "$1" ]; }
rl10_running() { status_has "uplink: RL10 (local-only), running (pid $(uplink_pid)"; }
rl10_free() { status_has "uplink: RL10 (local-only), not running"; }
start_run_rl10() { # [env...] → RUN, UP: a daemon run whose RL10 uplink holds a new connection
  local before; before="$(ep_hellos)"
  env "$@" "$SMINOS" daemon run --interval 1 >> "$T/run-rl10.out" 2>&1 & RUN=$!
  PIDS+=("$RUN")
  until_true 200 hellos_above "$before" || true
  until_true 200 rl10_running || true
  UP="$(uplink_pid)"
}

echo "  daemon run and its uplink:"
# m2: a second member of hubproj, its model's ten tool calls enough for a derivation to fork.
M2=5a000002-0000-4000-8000-0000000000a2
sleep 600 & M2_PID=$!
PIDS+=("$M2_PID")
printf '{"pid":%s,"sessionId":"%s","name":"m2","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$M2_PID" "$M2" "$HPR" > "$HOME/.claude/sessions/m2.json"
for i in 1 2 3 4 5 6 7 8 9 10; do
  printf '{"type":"assistant","uuid":"m2%06d","isSidechain":false,"message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_m2%06d","name":"Bash","input":{}}]}}\n' "$i" "$i"
done > "$HOME/.claude/projects/hp/$M2.jsonl"
rm -f "$STUB_STATE/fork-started" "$STUB_STATE/fork-ended"
HELLOS="$(ep_hellos)"
start_run_rl10 SMINOS_DERIVE_EVERY=1 STUB_FORK_SLEEP=8
assert_equals "$(epq "[len(d['hellos']) - $HELLOS, d['hellos'][-1]['hello']['token'] == d['token']]")" "[1, true]" \
  "RL10: daemon run starts the uplink, which says hello on the endpoint's socket with rl10.json's token"
if [[ -n "$UP" && "$UP" != "$RUN" ]] && alive "$UP"; then pass "RL10: the uplink is a process of its own ($UP)"; else
  fail "RL10: the uplink is a process of its own"; echo "    uplink pid '$UP', run $RUN"; fi
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: RL10 (local-only), running (pid $UP" "RL10: daemon status shows it"
run "$SMINOS" daemon run --interval 1
assert_rc 1 "$RC" "RL10: a second daemon run is refused"
assert_contains "$OUT" "a daemon already runs" "RL10: by the run lock"
run "$SMINOS" daemon uplink
assert_rc 1 "$RC" "RL10: a second uplink is refused"
assert_contains "$OUT" "an uplink already runs" "RL10: by the uplink lock"
until_true 200 hp_open_now || true

echo "  while a derivation runs:"
until_true 200 test -f "$STUB_STATE/fork-started" || true
assert_contains "$(tail -n +"$DLOG_AT" "$DLOG")" "derive --all started" "RL10: the tick loop starts a derivation"
assert_equals "$(test -f "$STUB_STATE/fork-started" && echo started)" started "RL10: whose fork (m2's) sleeps"
rl10_deliver "RL10: said from the web during the derivation"
assert_within "$TOOK" 1.0 "RL10: a web human the endpoint sends reaches m within a second while the derivation runs"
if [ ! -f "$STUB_STATE/fork-ended" ]; then pass "RL10: the derivation still runs"; else fail "RL10: the derivation still runs"; fi

echo "  while a fetch hangs:"
rm -f "$T/ssh-entered"
touch "$T/ssh-gate" "$SMINOS_HOME/daemon/nudge"
until_true 200 test -f "$T/ssh-entered" || true
assert_equals "$(test -f "$T/ssh-entered" && echo in)" in "RL10: the tick loop is inside a fetch of the hub-less project that hangs"
TICKED="$(ticked)"
read -r STATUS BURST_TOOK <<<"$(epctl burst 4000 1000)"
assert_equals "$STATUS" ok "RL10: 4 MB of frames from the endpoint are drained while the fetch hangs"
assert_within "$BURST_TOOK" 5.0 "RL10: promptly"
WORDS_BEFORE="$(epq "len([f for f in d['received'] if f['frame'].get('t') == 'words?'])")"
rl10_deliver "RL10: said from the web during the hung fetch"
assert_within "$TOOK" 1.0 "RL10: a web human reaches m within a second while the fetch hangs"
assert_equals "$(epq "[f['frame']['event']['text'] for f in d['received'] if f['frame'].get('t') == 'words?'][$WORDS_BEFORE:]")" \
  '["RL10: said from the web during the hung fetch"]' "RL10: delivered by the uplink itself, on the verdict it asked for (words?)"
assert_contains "$(grep -F "RL10: said from the web during the hung fetch" "$HPLOG/hub.$MEMBER.jsonl")" \
  '"verified": {"signer": {"kind": "device"' "RL10: stored with the endpoint's verification, as it arrived"
FSEQ=$RSEQ
RSEQ=$((RSEQ + 1))
epctl forged "$FSEQ" >/dev/null
until_true 100 grep -q "events for project '$OTHER_PROJECT'" "$DLOG" || true
until_true 100 grep -q "its writer is not one a log holds" "$DLOG" || true
assert_not_contains "$(cat "$HPLOG"/*.jsonl)" "forged:" "RL10: nothing refused enters the log"
assert_not_contains "$(cat "$INBOX")" "forged:" "RL10: or reaches m"
assert_contains "$(cat "$DLOG")" "in hubproj: it carries no signer" "RL10: an event the endpoint did not wrap with its signer is refused, and logged"
assert_contains "$(cat "$DLOG")" "in hubproj: its event carries a verified key of its own" "RL10: so is one claiming a verification of its own"
assert_contains "$(cat "$DLOG")" "in hubproj: its writer is not one a log holds" "RL10: and one whose writer fails its shape"
assert_contains "$(cat "$DLOG")" "events for project '$OTHER_PROJECT', which is no hub project of org org-1 known here: ignored" \
  "RL10: a frame for a project not known here is ignored"
reported_up() { [ "$(epq "len([f for f in d['received'] if f['frame'].get('t') == 'rejected' and f['frame'].get('event') == {'writer': 'hub/$MEMBER', 'seq': $FSEQ}])")" -ge 2 ]; }
until_true 100 reported_up || true
assert_equals "$(reported_up && echo up)" up "RL10: each refusal at a position is reported up to the endpoint (rejected)"
assert_equals "$(ticked)" "$TICKED" "RL10: the tick loop is still in the fetch all along"
if alive "$RUN"; then pass "RL10: and daemon run is alive"; else fail "RL10: and daemon run is alive"; fi
rm -f "$T/ssh-gate"
until_true 200 ticked_since "$TICKED" || true
if ticked_since "$TICKED"; then pass "RL10: released, the tick loop goes on"; else fail "RL10: released, the tick loop goes on"; fi

echo "  an import during a tick's delivery:"
SAYER=testhost/0f000000-0000-4000-8000-0000000000f1
python3 - "$SCRIPTS/sminos.py" "$HP" "$M" "$SAYER" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
mod.log_append(p, sys.argv[4], "say", **{"from": "k", "to": [{"session": sys.argv[3], "alias": "m"}], "text": "RL10: a say the tick delivers"})
PY
rm -f "$INBOX.held"
touch "$INBOX.hold" "$SMINOS_HOME/daemon/nudge"
until_true 200 test -f "$INBOX.held" || true
assert_contains "$(cat "$INBOX")" "RL10: a say the tick delivers" "RL10: a tick is pushing an owed say to m, its close held"
MSEQ=$RSEQ
epctl send "$RSEQ" "RL10: said from the web mid-delivery" >/dev/null
RSEQ=$((RSEQ + 1))
until_true 100 grep -q "RL10: said from the web mid-delivery" "$HPLOG/hub.$MEMBER.jsonl" || true
assert_contains "$(cat "$HPLOG/hub.$MEMBER.jsonl")" "RL10: said from the web mid-delivery" "RL10: the uplink imports a human for m meanwhile"
sleep 0.5
assert_not_contains "$(cat "$INBOX")" "RL10: said from the web mid-delivery" "RL10: and waits on m's delivery lock"
rm -f "$INBOX.hold"
until_true 100 grep -q "RL10: said from the web mid-delivery" "$INBOX" || true
TICKED="$(ticked)"
touch "$SMINOS_HOME/daemon/nudge"
until_true 200 ticked_since "$TICKED" || true
touch "$SMINOS_HOME/daemon/nudge"
TICKED="$(ticked)"
until_true 200 ticked_since "$TICKED" || true
assert_equals "$(grep -o "RL10: said from the web mid-delivery" "$INBOX" | wc -l | tr -d ' ')" 1 "RL10: the human reaches m once, two ticks later"
assert_equals "$(grep -o "RL10: a say the tick delivers" "$INBOX" | wc -l | tr -d ' ')" 1 "RL10: and the say once"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d[sys.argv[2]], d[sys.argv[3]]["settled"])' \
  "$SMINOS_HOME/projects/$HP/delivered/$M.json" "hub/$MEMBER" "$SAYER")" \
  "{'settled': $MSEQ, 'pending': None, 'attempts': 0} 1" "RL10: each writer's delivery settled at its event, nothing pending"
assert_not_contains "$(cat "$DLOG")" "out of order" "RL10: no deliverer settled out of order"

echo "  the two fail apart:"
until_true 200 derive_lock_is_a_dir || true
FAILS="$(grep -c "tick failed: IsADirectoryError" "$DLOG" || true)"
failed_again() { [ "$(grep -c "tick failed: IsADirectoryError" "$DLOG" || true)" -gt "$FAILS" ]; }
until_true 200 failed_again || true
assert_equals "$(failed_again && echo failed)" failed "RL10: a tick fails (its derivation lock is a directory)"
rl10_deliver "RL10: said from the web while ticks fail"
assert_within "$TOOK" 1.0 "RL10: the uplink still delivers within a second"
assert_equals "$(uplink_pid)" "$UP" "RL10: the same uplink"
rmdir "$SMINOS_HOME/daemon/derive.lock"
HELLOS="$(ep_hellos)"
kill -9 "$UP"
until_true 200 hellos_above "$HELLOS" || true
assert_equals "$(epq "len(d['hellos']) - $HELLOS")" 1 "RL10: a killed uplink is restarted, and says hello on a new connection"
NEW_UP="$(uplink_pid)"
if [[ -n "$NEW_UP" && "$NEW_UP" != "$UP" ]] && alive "$NEW_UP"; then pass "RL10: a new uplink process ($NEW_UP)"; else
  fail "RL10: a new uplink process"; echo "    uplink pid '$NEW_UP', was $UP"; fi
assert_contains "$(cat "$DLOG")" "uplink (pid $UP) exited on signal 9; restarting in 1s" "RL10: daemon.log says so"
TICKED="$(ticked)"
until_true 200 ticked_since "$TICKED" || true
if ticked_since "$TICKED" && alive "$RUN"; then pass "RL10: the tick loop goes on"; else fail "RL10: the tick loop goes on"; fi
until_true 200 hp_open_now || true
rl10_deliver "RL10: said from the web to the new uplink"
assert_within "$TOOK" 1.0 "RL10: the new uplink delivers"

echo "  stopping:"
kill "$RUN"
set +e; wait "$RUN"; set -e
until_true 100 dead "$NEW_UP" || true
if dead "$NEW_UP"; then pass "RL10: SIGTERM to daemon run stops its uplink"; else fail "RL10: SIGTERM to daemon run stops its uplink"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $NEW_UP)" "RL10: which says so"
start_run_rl10
kill -9 "$RUN"
set +e; wait "$RUN" 2>/dev/null; set -e
until_true 100 dead "$UP" || true
if [[ -n "$UP" ]] && dead "$UP"; then pass "RL10: an uplink whose daemon run was killed ends on its own"; else
  fail "RL10: an uplink whose daemon run was killed ends on its own"; echo "    uplink pid '$UP'"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP): its daemon is gone" "RL10: saying its daemon is gone"

echo "  a change of code:"
# change, imported, restarts, gap and started_in (above), on a fresh copy of the code.
CACHE="$T/cache-rl10"
mkdir -p "$CACHE"
cp -R "$PLUGIN_ROOT/skills/sminos" "$CACHE/"
CODE="$CACHE/sminos/scripts"
before_run="$(ep_hellos)"
"$CODE/sminos" daemon run --interval 1 > "$T/run-code-rl10.out" 2>&1 & RUNC=$!
PIDS+=("$RUNC")
until_true 200 hellos_above "$before_run" || true
until_true 200 rl10_running || true
UP="$(uplink_pid)"
HELLOS="$(ep_hellos)"
for f in "$CODE"/*.py; do cp "$f" "$f.new" && mv "$f.new" "$f"; done
sleep 4  # a tick (1 s) and the settle (1 s) would have restarted it by now
if alive "$RUNC" && [ "$(started_in "$RUNC")" = 1 ] && [ "$(uplink_pid)" = "$UP" ] && [ "$(ep_hellos)" = "$HELLOS" ]; then
  pass "RL10: scripts re-made with the same bytes restart nothing: the uplink ($UP) keeps its connection"; else
  fail "RL10: scripts re-made with the same bytes restart nothing"
  echo "    starts: $(started_in "$RUNC"), uplink $UP -> '$(uplink_pid)', hellos $HELLOS -> $(ep_hellos)"; fi
change sminos_jobs.py
until_true 200 hellos_above "$HELLOS" || true
up_moved() { local p; p="$(uplink_pid)"; [[ -n "$p" && "$p" != "$1" ]] && alive "$p"; }
until_true 200 up_moved "$UP" || true
NEW_UP="$(uplink_pid)"
if alive "$RUNC" && [ "$(started_in "$RUNC")" = 2 ]; then pass "RL10: run restarts in place once sminos_jobs.py changes (pid $RUNC)"; else
  fail "RL10: run restarts in place once sminos_jobs.py changes"; echo "    alive: $(alive "$RUNC" && echo yes || echo no), starts: $(started_in "$RUNC")"; fi
assert_contains "$(cat "$T/run-code-rl10.out")" "its code changed: restarting in place" "RL10: saying why"
if [[ "$NEW_UP" != "$UP" ]] && dead "$UP" && grep -Fq "uplink: stopped (pid $UP)" "$DLOG" && imported sminos_jobs "$NEW_UP"; then
  pass "RL10: its uplink ($UP) ended on its SIGTERM, and a new one ($NEW_UP) runs the new code"; else
  fail "RL10: its uplink ended on its SIGTERM, and a new one runs the new code"; echo "    uplink $UP -> '$NEW_UP'"; fi
assert_within "$(gap "$RUNC")" 5 "RL10: the uplink is back on a new connection within seconds of the restart"
UP="$NEW_UP"
HELLOS="$(ep_hellos)"
change sminos_daemon.py
for f in sminos_rl10.py sminos_hublog.py sminos_plane.py sminos_rpc.py sminos_bridge.py sminos_policy.py; do
  sleep 0.25; printf '\n' >> "$CODE/$f"
done
sleep 0.25; change sminos_uplink.py
PULLED="$(python3 -c 'import time; print("%.3f" % time.time())')"
until_true 200 hellos_above "$HELLOS" || true
until_true 200 up_moved "$UP" || true
NEW_UP="$(uplink_pid)"
AT="$(restarts "$RUNC" | sed -n 2p)"
if alive "$RUNC" && imported sminos_daemon "$RUNC" && [ "$(started_in "$RUNC")" = 3 ]; then
  pass "RL10: a pull restarts it in place again, the same pid on the new code"; else
  fail "RL10: a pull restarts it in place again, the same pid on the new code"
  echo "    alive: $(alive "$RUNC" && echo yes || echo no), starts: $(started_in "$RUNC")"; fi
if [[ -n "$AT" ]] && python3 -c 'import sys; sys.exit(float(sys.argv[1]) < float(sys.argv[2]))' "$AT" "$PULLED"; then
  pass "RL10: once, after the pull's last script"; else fail "RL10: once, after the pull's last script"; echo "    at '$AT', pulled $PULLED"; fi
if [[ "$NEW_UP" != "$UP" ]] && dead "$UP" && imported sminos_uplink "$NEW_UP"; then
  pass "RL10: a new uplink ($NEW_UP) on the pull's code"; else fail "RL10: a new uplink on the pull's code"; echo "    uplink $UP -> '$NEW_UP'"; fi
assert_within "$(gap "$RUNC")" 5 "RL10: back on a new connection within seconds"
run "$SMINOS" daemon status
assert_contains "$OUT" "daemon: running (pid $RUNC " "RL10: the restarted loop holds the run lock again"
kill "$RUNC"
set +e; wait "$RUNC"; RUNC_RC=$?; set -e
assert_rc 0 "$RUNC_RC" "RL10: and SIGTERM ends it as before"
until_true 100 dead "$NEW_UP" || true
if dead "$NEW_UP"; then pass "RL10: its uplink with it"; else fail "RL10: its uplink with it"; fi
assert_equals "$(restarts "$RUNC" | wc -l | tr -d ' ')" 2 "RL10: two restarts in place in all: the pull cost one"

echo "  orphaned while it starts:"
HELLOS="$(ep_hellos)"
ORPHAN="$(python3 "$T/launch.py" "$SMINOS" "$T/orphan-rl10.out")"
until_true 100 dead "$ORPHAN" || true
if [[ -n "$ORPHAN" ]] && dead "$ORPHAN"; then pass "RL10: an uplink whose supervisor is gone before it looked ends at once"; else
  fail "RL10: an uplink whose supervisor is gone before it looked ends at once"; echo "    uplink pid '$ORPHAN'"
  kill "$ORPHAN" 2>/dev/null || true; fi
assert_equals "$(ep_hellos)" "$HELLOS" "RL10: without saying hello to the endpoint"
assert_contains "$(cat "$DLOG")" "uplink: not started (pid $ORPHAN): its daemon (pid" "RL10: saying its daemon is gone"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: RL10 (local-only), not running" "RL10: and uplink.lock is free"

echo "  ending under steady traffic:"
start_run_rl10
touch "$T/flowing"
epctl flow "$T/flowing" & FLOW=$!
PIDS+=("$FLOW")
sleep 0.5
kill -9 "$RUN"
set +e; wait "$RUN" 2>/dev/null; set -e
until_true 40 dead "$UP" || true
if [[ -n "$UP" ]] && dead "$UP"; then pass "RL10: with a frame every 50 ms, the orphan of a killed daemon run ends within 2 s"; else
  fail "RL10: with a frame every 50 ms, the orphan of a killed daemon run ends within 2 s"; echo "    uplink pid '$UP'"; fi
until_true 40 rl10_free || true
if rl10_free; then pass "RL10: and releases uplink.lock"; else fail "RL10: and releases uplink.lock"; fi
OLD_UP="$UP"
start_run_rl10
if [[ -n "$UP" && "$UP" != "$OLD_UP" ]] && alive "$UP"; then pass "RL10: a new daemon run's uplink takes the connection ($UP)"; else
  fail "RL10: a new daemon run's uplink takes the connection"; echo "    uplink pid '$UP', was $OLD_UP"; fi
kill "$UP"
until_true 20 dead "$UP" || true
if dead "$UP"; then pass "RL10: SIGTERM ends the uplink within a second under the same flow"; else
  fail "RL10: SIGTERM ends the uplink within a second under the same flow"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP)" "RL10: on its own, not by the supervisor's kill"
assert_contains "$(cat "$DLOG")" "uplink (pid $UP) exited with 0" "RL10: the supervisor saw it exit cleanly"
until_true 100 restarted_after "$UP" || true
UP="$(uplink_pid)"
kill "$RUN"
set +e; wait "$RUN"; set -e
if dead "$UP"; then pass "RL10: SIGTERM to daemon run under the flow ends its uplink"; else fail "RL10: SIGTERM to daemon run under the flow ends its uplink"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP)" "RL10: which stopped on the supervisor's SIGTERM, before any kill"
rm -f "$T/flowing"
set +e; wait "$FLOW"; set -e
assert_not_contains "$(tail -n +"$DLOG_AT" "$DLOG")" "Traceback" "RL10: nothing daemon.log says of this block is a traceback"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES uplink assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) uplink assertions FAILED"
  exit 1
fi
