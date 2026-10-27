#!/usr/bin/env bash
#
# The uplink (DC4 M1 of the desk): `sminos daemon uplink`, the process `daemon
# run` keeps beside its tick loop, holding the stream down from the hub
# (hub_standin.py stands in for DX2). Pins DC4.G4: the stream is drained and
# an event from the hub reaches a local member within a second while the tick
# sits in a hung git fetch of a hub-less project, and while a derivation runs;
# a burst from the hub costs a few ticks, not a tick a frame, however slow
# each POST is; what fails its code or its shape never enters the log; the uplink and the
# tick loop restart and fail apart; a machine that leaves the hub (hub.json
# gone) stops its uplink and says so; the run lock holds, and a change of the
# daemon's code restarts it in place, the uplink back within seconds; an event the uplink imports while a tick is
# mid-delivery to the same member is delivered once; the machine's lease at the
# hub never lapses while the main thread is held, and lapses once the stream
# is silent.
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

# The hub stand-in, heartbeat every 2 s.
python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-1 secret-1 2000 & PIDS+=("$!")
until_true 100 test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"

# The test's hands on the stand-in: state, a send, a burst, and a send timed
# until its text reaches the inbox.
cat > "$T/ctl.py" <<'PY'
import http.client, json, sys, time
port = int(open(sys.argv[1]).read())

def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd = sys.argv[2]
if cmd == "generation":
    print(call("GET", "/control/state")[1]["generation"])
elif cmd == "send":
    status, body = call("POST", "/control/send", {"frames": [json.loads(sys.argv[3])]})
    print(status)
elif cmd == "burst":
    frame = {"t": "hb", "at": "2026-10-15T00:00:00.000Z", "pad": "x" * int(sys.argv[4])}
    status, body = call("POST", "/control/send", {"frames": [frame], "repeat": int(sys.argv[3])})
    print("%d %.2f" % (status, body.get("took", -1)))
elif cmd == "flow":  # an hb every 50 ms until the file named goes away, to whichever stream is open
    while __import__("os").path.exists(sys.argv[3]):
        try:
            call("POST", "/control/send", {"frames": [{"t": "hb", "at": "2026-10-15T00:00:00.000Z"}]})
        except OSError:
            pass
        time.sleep(0.05)
elif cmd == "fault":  # has fault — the next POST carrying a frame of `has` meets it
    call("POST", "/control/post-fault", {"faults": [{"has": sys.argv[3], "fault": sys.argv[4]}]})
elif cmd == "release":
    call("POST", "/control/release", {})
elif cmd == "post-delay":  # seconds — every frame POST waits this long from now on
    call("POST", "/control/post-delay", {"seconds": float(sys.argv[3])})
elif cmd == "opened":  # project — whether the stream opened last has it open
    d = call("GET", "/control/state")[1]
    print("yes" if d["projects"].get(sys.argv[3], {}).get("open", {}).get("testhost") == d["generation"] else "no")
elif cmd == "lease":  # testhost's current lease: its generation and whether it is online
    lease = call("GET", "/control/state")[1]["leases"].get("testhost")
    print("%s %s" % (lease["generation"], "online" if lease["online"] else "offline") if lease else "none")
elif cmd == "lapses":  # generation — how many times testhost's lease of that stream lapsed
    print(len([x for x in call("GET", "/control/state")[1]["lapses"]
               if x["machine"] == "testhost" and str(x["generation"]) == sys.argv[3]]))
elif cmd == "acks":  # generation — how many hb-acks of that stream testhost posted
    print(len([a for a in call("GET", "/control/state")[1]["hb_acks"]
               if a["machine"] == "testhost" and str(a["generation"]) == sys.argv[3]]))
elif cmd == "mute":
    call("POST", "/control/mute", {"machine": "testhost"})
elif cmd == "held":  # the generation of each POST held, in order
    print(" ".join(p["generation"] for p in call("GET", "/control/state")[1]["posted"] if p["status"] == "held"))
elif cmd == "after-held":  # POSTs of events on the generation of the last held one, after it
    posted = call("GET", "/control/state")[1]["posted"]
    i = max(i for i, p in enumerate(posted) if p["status"] == "held")
    print(len([p for p in posted[i + 1:] if p["generation"] == posted[i]["generation"] and '"t":"events"' in p["body"]]))
elif cmd == "deliver":
    inbox, text = sys.argv[4], sys.argv[5].encode()
    t0 = time.time()
    status, _ = call("POST", "/control/send", {"frames": [json.loads(sys.argv[3])]})
    while status == 200 and time.time() - t0 < 5:
        if text in open(inbox, "rb").read():
            print("%.2f" % (time.time() - t0))
            sys.exit(0)
        time.sleep(0.02)
    print("never")
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }

# Events as the hub would carry them: a web `human` to m, sealed with the org
# key under the hub project, and its forgeries.
cat > "$T/seal.py" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
variant, seq, text = sys.argv[1], int(sys.argv[2]), sys.argv[3]
project, other, member, session = os.environ["HP"], os.environ["OTHER_PROJECT"], os.environ["MEMBER"], os.environ["M"]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
draft = {"ts": ts, "writer": "hub/" + member, "seq": seq, "kind": "human", "from": "human", "member": member,
         "to": [{"session": session, "alias": "m"}], "text": text, "created": ts}
e = codes.seal(bytes(range(32)), "log", other if variant == "other-project" else project, draft,
               codes.b64url(os.urandom(16)))
if variant == "bad-code":
    e["text"] = text + " (changed on the way)"
elif variant == "moved":
    e["writer"] = "hub/0123456789abcdef0123456789abcdef"
elif variant == "via":
    e["via"] = "doperpowers-1e"
elif variant == "padded":
    e["mac"]["value"] += "="
print(json.dumps({"t": "events", "project": other if variant == "unknown-project" else project, "events": [e]}))
PY
export SCRIPTS
seal() { python3 "$T/seal.py" "$@"; }
deliver_time() { ctl deliver "$(seal ok "$1" "$2")" "$INBOX" "$2"; }

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

# ---- the credential
echo "the credential:"
run "$SMINOS" daemon uplink
assert_rc 0 "$RC" "with no credential, the uplink exits 0"
assert_contains "$(cat "$DLOG")" "uplink: no credential" "saying there is nothing to connect"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"
write_cred() { # hub-url
  printf '{"hub": "%s", "org": "org-1", "machine": "testhost", "client_id": "cid-1", "client_secret": "secret-1", "key": "%s"}\n' \
    "$1" "$KEY" > "$SMINOS_HOME/daemon/hub.json"
  chmod 600 "$SMINOS_HOME/daemon/hub.json"
}
write_cred "http://hub.example.com"
run "$SMINOS" daemon uplink
assert_rc 1 "$RC" "a hub over plain http off this machine is refused"
assert_contains "$OUT" "neither https nor on this machine" "saying why"
write_cred "$HUB"

# ---- daemon run keeps the uplink beside the tick loop
echo "daemon run and its uplink:"
env SMINOS_DERIVE_EVERY=1 STUB_FORK_SLEEP=8 "$SMINOS" daemon run --interval 1 > "$T/run.out" 2>&1 & RUN=$!
PIDS+=("$RUN")
gen_is() { [ "$(ctl generation)" = "$1" ]; }
until_true 200 gen_is 1 || true
assert_equals "$(ctl generation)" 1 "daemon run starts the uplink, which opens the stream with the service token"
uplink_pid() { sed -n 's/^pid \([0-9]*\) .*/\1/p' "$SMINOS_HOME/daemon/uplink.lock" 2>/dev/null || true; }
UP="$(uplink_pid)"
if [[ -n "$UP" && "$UP" != "$RUN" ]] && alive "$UP"; then pass "the uplink is a process of its own ($UP)"; else
  fail "the uplink is a process of its own"; echo "    uplink pid '$UP', run $RUN"; fi
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: running (pid $UP" "daemon status shows it"
run "$SMINOS" daemon run --interval 1
assert_rc 1 "$RC" "a second daemon run is refused"
assert_contains "$OUT" "a daemon already runs" "by the run lock"
run "$SMINOS" daemon uplink
assert_rc 1 "$RC" "a second uplink is refused"
assert_contains "$OUT" "an uplink already runs" "by the uplink lock"

# ---- while a derivation runs
echo "while a derivation runs:"
until_true 200 test -f "$STUB_STATE/fork-started" || true
assert_contains "$(cat "$DLOG")" "derive --all started" "the tick loop starts a derivation, whose fork sleeps"
TOOK="$(deliver_time 1 "said from the web during the derivation")"
assert_within "$TOOK" 1.0 "an event from the hub reaches m within a second while the derivation runs"
if [ ! -f "$STUB_STATE/fork-ended" ]; then pass "the derivation still runs"; else fail "the derivation still runs"; fi

# ---- while the tick sits in a hung fetch
echo "while a fetch hangs:"
rm -f "$T/ssh-entered"
touch "$T/ssh-gate" "$SMINOS_HOME/daemon/nudge"
until_true 200 test -f "$T/ssh-entered" || true
assert_equals "$(test -f "$T/ssh-entered" && echo in)" in "the tick loop is inside a fetch of the hub-less project that hangs"
TICKED="$(cat "$SMINOS_HOME/projects/$HP/daemon.json")"
read -r STATUS BURST_TOOK <<<"$(ctl burst 4000 1000)"
assert_equals "$STATUS" 200 "4 MB of frames from the hub are drained while the fetch hangs"
assert_within "$BURST_TOOK" 5.0 "promptly"
TOOK="$(deliver_time 2 "said from the web during the hung fetch")"
assert_within "$TOOK" 1.0 "an event from the hub reaches m within a second while the fetch hangs"
assert_contains "$(cat "$DLOG")" "uplink: delivered 1 in hubproj to m" "delivered by the uplink itself"
assert_contains "$(cat "$HPLOG/hub.$MEMBER.jsonl")" '"mac": {"nonce": "' "stored with the code it arrived with"
for variant in bad-code moved via padded other-project unknown-project; do
  ctl send "$(seal "$variant" 3 "forged: $variant")" >/dev/null
done
until_true 100 grep -q "events for project '$OTHER_PROJECT'" "$DLOG" || true
assert_not_contains "$(cat "$HPLOG"/*.jsonl)" "forged:" "no forged event enters the log"
assert_not_contains "$(cat "$INBOX")" "forged:" "or reaches m"
assert_contains "$(cat "$DLOG")" "in hubproj: its code does not verify" "a changed field fails the code, and is logged"
assert_contains "$(cat "$DLOG")" "uplink: refused 'hub/0123456789abcdef0123456789abcdef':3" "a hub/ event moved to another member's feed is refused"
assert_contains "$(cat "$DLOG")" "fails its shape" "by its shape, though its code verifies"
assert_contains "$(cat "$DLOG")" "its code or nonce is not the canonical base64url of 32 and 16 bytes" "a code in another spelling of its bytes is refused before any HMAC"
assert_equals "$(grep -c "its code does not verify" "$DLOG")" 3 "a changed field, an uncovered field (via), and an event of another project all fail the code"
assert_contains "$(cat "$DLOG")" "events for project '$OTHER_PROJECT', which is no hub project of org org-1 known here: ignored" "a frame for a project not known here is ignored"
assert_equals "$(cat "$SMINOS_HOME/projects/$HP/daemon.json")" "$TICKED" "the tick loop is still in the fetch all along"
if alive "$RUN"; then pass "and daemon run is alive"; else fail "and daemon run is alive"; fi
rm -f "$T/ssh-gate"
ticked_since() { [ "$(cat "$SMINOS_HOME/projects/$HP/daemon.json")" != "$1" ]; }
until_true 200 ticked_since "$TICKED" || true
if ticked_since "$TICKED"; then pass "released, the tick loop goes on"; else fail "released, the tick loop goes on"; fi

# ---- the uplink imports while a tick is mid-delivery to the same member
echo "an import during a tick's delivery:"
python3 - "$SCRIPTS/sminos.py" "$HP" "$M" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
mod.log_append(p, "testhost/0f000000-0000-4000-8000-0000000000f0", "say",
               **{"from": "k", "to": [{"session": sys.argv[3], "alias": "m"}], "text": "a say the tick delivers"})
PY
rm -f "$INBOX.held"
touch "$INBOX.hold" "$SMINOS_HOME/daemon/nudge"
until_true 200 test -f "$INBOX.held" || true
assert_contains "$(cat "$INBOX")" "a say the tick delivers" "a tick is pushing an owed say to m, its close held"
# Seq 4: the forgeries above spent hub/$MEMBER's position 3, a tombstone nothing is appended at.
ctl send "$(seal ok 4 "said from the web mid-delivery")" >/dev/null
until_true 100 grep -q "said from the web mid-delivery" "$HPLOG/hub.$MEMBER.jsonl" || true
assert_contains "$(cat "$HPLOG/hub.$MEMBER.jsonl")" "said from the web mid-delivery" "the uplink imports a human for m meanwhile"
sleep 0.5
assert_not_contains "$(cat "$INBOX")" "said from the web mid-delivery" "and waits on m's delivery lock"
rm -f "$INBOX.hold"
until_true 100 grep -q "said from the web mid-delivery" "$INBOX" || true
TICKED="$(cat "$SMINOS_HOME/projects/$HP/daemon.json")"
touch "$SMINOS_HOME/daemon/nudge"
until_true 200 ticked_since "$TICKED" || true
touch "$SMINOS_HOME/daemon/nudge"
TICKED="$(cat "$SMINOS_HOME/projects/$HP/daemon.json")"
until_true 200 ticked_since "$TICKED" || true
assert_equals "$(grep -o "said from the web mid-delivery" "$INBOX" | wc -l | tr -d ' ')" 1 "the human reaches m once, two ticks later"
assert_equals "$(grep -o "a say the tick delivers" "$INBOX" | wc -l | tr -d ' ')" 1 "and the say once"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d[sys.argv[2]], d[sys.argv[3]]["settled"])' \
  "$SMINOS_HOME/projects/$HP/delivered/$M.json" "hub/$MEMBER" "testhost/0f000000-0000-4000-8000-0000000000f0")" \
  "{'settled': 4, 'pending': None, 'attempts': 0} 1" "each writer's delivery settled at its event, nothing pending"
assert_not_contains "$(cat "$DLOG")" "out of order" "no deliverer settled out of order"

# ---- a tick that fails does not stop the uplink
echo "the two fail apart:"
# The running loop takes the derivation lock (a file) every tick, so it can come
# back between the rm and the mkdir: retried until the directory is in place.
derive_lock_is_a_dir() { rm -f "$SMINOS_HOME/daemon/derive.lock"; mkdir "$SMINOS_HOME/daemon/derive.lock" 2>/dev/null; }
until_true 200 derive_lock_is_a_dir || true
until_true 200 grep -q "tick failed" "$DLOG" || true
assert_contains "$(cat "$DLOG")" "tick failed: IsADirectoryError" "a tick fails (its derivation lock is a directory)"
TOOK="$(deliver_time 5 "said from the web while ticks fail")"
assert_within "$TOOK" 1.0 "the uplink still delivers within a second"
assert_equals "$(uplink_pid)" "$UP" "the same uplink"
rmdir "$SMINOS_HOME/daemon/derive.lock"
# A killed uplink is restarted, and the tick loop goes on.
kill -9 "$UP"
until_true 200 gen_is 2 || true
assert_equals "$(ctl generation)" 2 "a killed uplink is restarted, and opens a new stream"
NEW_UP="$(uplink_pid)"
if [[ -n "$NEW_UP" && "$NEW_UP" != "$UP" ]] && alive "$NEW_UP"; then pass "a new uplink process ($NEW_UP)"; else
  fail "a new uplink process"; echo "    uplink pid '$NEW_UP', was $UP"; fi
assert_contains "$(cat "$DLOG")" "uplink (pid $UP) exited on signal 9; restarting in 1s" "daemon.log says so"
TICKED="$(cat "$SMINOS_HOME/projects/$HP/daemon.json")"
until_true 200 ticked_since "$TICKED" || true
if ticked_since "$TICKED" && alive "$RUN"; then pass "the tick loop goes on"; else fail "the tick loop goes on"; fi
TOOK="$(deliver_time 6 "said from the web to the new uplink")"
assert_within "$TOOK" 1.0 "the new uplink delivers"

# ---- stopping
echo "stopping:"
kill "$RUN"
set +e; wait "$RUN"; set -e
until_true 100 dead "$NEW_UP" || true
if dead "$NEW_UP"; then pass "SIGTERM to daemon run stops its uplink"; else fail "SIGTERM to daemon run stops its uplink"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $NEW_UP)" "which says so"
"$SMINOS" daemon run --interval 1 > "$T/run2.out" 2>&1 & RUN=$!
PIDS+=("$RUN")
until_true 200 gen_is 3 || true
UP="$(uplink_pid)"
kill -9 "$RUN"
set +e; wait "$RUN" 2>/dev/null; set -e
until_true 100 dead "$UP" || true
if [[ -n "$UP" ]] && dead "$UP"; then pass "an uplink whose daemon run was killed ends on its own"; else
  fail "an uplink whose daemon run was killed ends on its own"; echo "    uplink pid '$UP'"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP): its daemon is gone" "saying its daemon is gone"

# ---- daemon run restarts in place on a change to its code: the same pid on
# the new code, never an exit a service manager would throttle, and the uplink
# back within seconds. What a change brings is seen: each changed script
# marks, as it is imported, which process imported it.
echo "a change of code:"
CACHE="$T/cache"
mkdir -p "$CACHE"
cp -R "$PLUGIN_ROOT/skills/sminos" "$CACHE/"
CODE="$CACHE/sminos/scripts"
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
gap() { # pid — seconds from its last restart in place to the next stream its uplink opened
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
"$CACHE/sminos/scripts/sminos" daemon run --interval 1 > "$T/run-code.out" 2>&1 & RUNC=$!
PIDS+=("$RUNC")
GEN=4
until_true 200 gen_is "$GEN" || true
UP="$(uplink_pid)"
# A marketplace update re-clones the marketplace: every script a new file with
# a new mtime, the same bytes where sminos did not change. Nothing restarts,
# and the uplink keeps its stream.
for f in "$CODE"/*.py; do cp "$f" "$f.new" && mv "$f.new" "$f"; done
sleep 4  # a tick (1 s) and the settle (1 s) would have restarted it by now
if alive "$RUNC" && [ "$(started_in "$RUNC")" = 1 ] && [ "$(uplink_pid)" = "$UP" ] && gen_is "$GEN"; then
  pass "scripts re-made with the same bytes restart nothing: the uplink ($UP) keeps its stream"; else
  fail "scripts re-made with the same bytes restart nothing"
  echo "    starts: $(started_in "$RUNC"), uplink $UP -> '$(uplink_pid)', generation $(ctl generation)"; fi
# sminos_jobs.py: imported by the uplink alone (through the plane and the
# RPCs), and once missing from the daemon's list of its own code.
change sminos_jobs.py
GEN=5
until_true 200 gen_is "$GEN" || true
NEW_UP="$(uplink_pid)"
if alive "$RUNC" && [ "$(started_in "$RUNC")" = 2 ]; then pass "run restarts in place once sminos_jobs.py changes (pid $RUNC)"; else
  fail "run restarts in place once sminos_jobs.py changes"; echo "    alive: $(alive "$RUNC" && echo yes || echo no), starts: $(started_in "$RUNC")"; fi
assert_contains "$(cat "$T/run-code.out")" "its code changed: restarting in place" "saying why"
if [[ "$NEW_UP" != "$UP" ]] && dead "$UP" && grep -Fq "uplink: stopped (pid $UP)" "$DLOG" && imported sminos_jobs "$NEW_UP"; then
  pass "its uplink ($UP) ended on its SIGTERM, and a new one ($NEW_UP) runs the new code"; else
  fail "its uplink ended on its SIGTERM, and a new one runs the new code"; echo "    uplink $UP -> '$NEW_UP'"; fi
assert_within "$(gap "$RUNC")" 5 "the uplink is back on a new stream within seconds of the restart"
# A pull in progress: the daemon's own script first, the uplink's last, a
# script every quarter second between. It restarts once, after the last.
UP="$NEW_UP"
change sminos_daemon.py
for f in sminos_codes.py sminos_hublog.py sminos_plane.py sminos_rpc.py sminos_bridge.py sminos_policy.py; do
  sleep 0.25; printf '\n' >> "$CODE/$f"
done
sleep 0.25; change sminos_uplink.py
PULLED="$(python3 -c 'import time; print("%.3f" % time.time())')"
GEN=6
until_true 200 gen_is "$GEN" || true
NEW_UP="$(uplink_pid)"
AT="$(restarts "$RUNC" | sed -n 2p)"
if alive "$RUNC" && imported sminos_daemon "$RUNC" && [ "$(started_in "$RUNC")" = 3 ]; then
  pass "a pull restarts it in place again, the same pid on the new code"; else
  fail "a pull restarts it in place again, the same pid on the new code"
  echo "    alive: $(alive "$RUNC" && echo yes || echo no), starts: $(started_in "$RUNC")"; fi
if [[ -n "$AT" ]] && python3 -c 'import sys; sys.exit(float(sys.argv[1]) < float(sys.argv[2]))' "$AT" "$PULLED"; then
  pass "once, after the pull's last script"; else fail "once, after the pull's last script"; echo "    at '$AT', pulled $PULLED"; fi
if [[ "$NEW_UP" != "$UP" ]] && dead "$UP" && imported sminos_uplink "$NEW_UP"; then
  pass "a new uplink ($NEW_UP) on the pull's code"; else fail "a new uplink on the pull's code"; echo "    uplink $UP -> '$NEW_UP'"; fi
assert_within "$(gap "$RUNC")" 5 "back on a new stream within seconds"
run "$SMINOS" daemon status
assert_contains "$OUT" "daemon: running (pid $RUNC " "the restarted loop holds the run lock again"
kill "$RUNC"
set +e; wait "$RUNC"; RUNC_RC=$?; set -e
assert_rc 0 "$RUNC_RC" "and SIGTERM ends it as before"
until_true 100 dead "$NEW_UP" || true
if dead "$NEW_UP"; then pass "its uplink with it"; else fail "its uplink with it"; fi
assert_equals "$(restarts "$RUNC" | wc -l | tr -d ' ')" 2 "two restarts in place in all: the pull cost one"

# ---- an uplink whose supervisor died while it started
# The supervisor names itself at spawn: a parent that is gone before the
# uplink could look (orphaned in its startup, imports, or credential read) is
# never mistaken for the supervisor, so the orphan neither serves nor holds
# uplink.lock.
echo "orphaned while it starts:"
cat > "$T/launch.py" <<'PY'
import os, subprocess, sys
# daemon run's spawn of its uplink, then gone at once.
p = subprocess.Popen([sys.argv[1], "daemon", "uplink"], env={**os.environ, "SMINOS_UPLINK_PARENT": str(os.getpid())},
                     stdin=subprocess.DEVNULL, stdout=open(sys.argv[2], "a"), stderr=subprocess.STDOUT)
print(p.pid)
PY
GEN_BEFORE="$(ctl generation)"
ORPHAN="$(python3 "$T/launch.py" "$SMINOS" "$T/orphan.out")"
until_true 100 dead "$ORPHAN" || true
if [[ -n "$ORPHAN" ]] && dead "$ORPHAN"; then pass "an uplink whose supervisor is gone before it looked ends at once"; else
  fail "an uplink whose supervisor is gone before it looked ends at once"; echo "    uplink pid '$ORPHAN'"
  kill "$ORPHAN" 2>/dev/null || true; fi
assert_equals "$(ctl generation)" "$GEN_BEFORE" "without opening a stream"
assert_contains "$(cat "$DLOG")" "uplink: not started (pid $ORPHAN): its daemon (pid" "saying its daemon is gone"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: not running" "and uplink.lock is free"

# ---- an uplink ends promptly under a stream that never pauses
echo "ending under steady traffic:"
start_run() { # → RUN, UP: a daemon run whose uplink holds a new stream
  local gen; gen=$(( $(ctl generation) + 1 ))
  "$SMINOS" daemon run --interval 1 >> "$T/run3.out" 2>&1 & RUN=$!
  PIDS+=("$RUN")
  until_true 200 gen_is "$gen" || true
  UP="$(uplink_pid)"
}
uplink_free() { "$SMINOS" daemon status | grep -q "uplink: not running"; }
start_run
touch "$T/flowing"
ctl flow "$T/flowing" & FLOW=$!
PIDS+=("$FLOW")
sleep 0.5
kill -9 "$RUN"
set +e; wait "$RUN" 2>/dev/null; set -e
until_true 40 dead "$UP" || true
if [[ -n "$UP" ]] && dead "$UP"; then pass "with an hb every 50 ms, the orphan of a killed daemon run ends within 2 s"; else
  fail "with an hb every 50 ms, the orphan of a killed daemon run ends within 2 s"; echo "    uplink pid '$UP'"; fi
until_true 40 uplink_free || true
if uplink_free; then pass "and releases uplink.lock"; else fail "and releases uplink.lock"; fi
OLD_UP="$UP"
start_run
if [[ -n "$UP" && "$UP" != "$OLD_UP" ]] && alive "$UP"; then pass "a new daemon run's uplink takes the stream ($UP)"; else
  fail "a new daemon run's uplink takes the stream"; echo "    uplink pid '$UP', was $OLD_UP"; fi
kill "$UP"
until_true 20 dead "$UP" || true
if dead "$UP"; then pass "SIGTERM ends the uplink within a second under the same flow"; else
  fail "SIGTERM ends the uplink within a second under the same flow"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP)" "on its own, not by the supervisor's kill"
assert_contains "$(cat "$DLOG")" "uplink (pid $UP) exited with 0" "the supervisor saw it exit cleanly"
restarted_after() { local p; p="$(uplink_pid)"; [[ -n "$p" && "$p" != "$1" ]] && alive "$p"; }
until_true 100 restarted_after "$UP" || true
UP="$(uplink_pid)"
kill "$RUN"
set +e; wait "$RUN"; set -e
if dead "$UP"; then pass "SIGTERM to daemon run under the flow ends its uplink"; else fail "SIGTERM to daemon run under the flow ends its uplink"; fi
assert_contains "$(cat "$DLOG")" "uplink: stopped (pid $UP)" "which stopped on the supervisor's SIGTERM, before any kill"
rm -f "$T/flowing"
set +e; wait "$FLOW"; set -e

# ---- the machine leaves the hub: hub.json removed under a running supervisor
# (`sminos hub leave`) stops the uplink for good, and daemon.log says the
# machine left rather than that the uplink restarts; an enrollment (hub.json
# written again) brings it back. A change of hub.json that keeps a credential
# keeps its own line (test-sync.sh pins it).
echo "the machine leaves the hub:"
LEFT="this machine left the hub (hub.json is gone): the uplink stays stopped until the machine is enrolled again"
start_run
rm "$SMINOS_HOME/daemon/hub.json"
until_true 100 dead "$UP" || true
if [[ -n "$UP" ]] && dead "$UP"; then pass "with hub.json gone, the supervisor stops the uplink"; else
  fail "with hub.json gone, the supervisor stops the uplink"; echo "    uplink pid '$UP'"; fi
assert_contains "$(cat "$DLOG")" "uplink (pid $UP): $LEFT" "daemon.log says the machine left the hub and the uplink stays stopped"
assert_not_contains "$(grep -F "(pid $UP)" "$DLOG")" "restarting" "not that it restarts the uplink"
GEN="$(ctl generation)"
sleep 2
run "$SMINOS" daemon status
assert_contains "$OUT" "daemon: running" "two seconds on, daemon run goes on"
assert_not_contains "$OUT" "uplink: running" "with no uplink"
assert_equals "$(ctl generation)" "$GEN" "and no stream was opened"
write_cred "$HUB"
until_true 200 gen_is $((GEN + 1)) || true
OLD_UP="$UP"
UP="$(uplink_pid)"
if [[ -n "$UP" && "$UP" != "$OLD_UP" ]] && alive "$UP"; then pass "enrolled again, the uplink is back on a new stream"; else
  fail "enrolled again, the uplink is back on a new stream"; echo "    uplink pid '$UP', was $OLD_UP"; fi
# Gone while the uplink ends on its own: whichever the supervisor sees first,
# it says the machine left, and restarts nothing.
rm "$SMINOS_HOME/daemon/hub.json"
kill -9 "$UP"
said_left() { grep -F "(pid $UP)" "$DLOG" | grep -Fq "$LEFT"; }
until_true 100 said_left || true
if said_left; then pass "hub.json gone as the uplink is killed: daemon.log says the machine left"; else
  fail "hub.json gone as the uplink is killed: daemon.log says the machine left"; grep -F "(pid $UP)" "$DLOG" || true; fi
GEN="$(ctl generation)"
sleep 2
assert_not_contains "$(grep -F "(pid $UP)" "$DLOG")" "restarting" "and no restart"
assert_equals "$(ctl generation)" "$GEN" "no stream opened"
kill "$RUN"
set +e; wait "$RUN"; set -e
write_cred "$HUB"

# ---- a burst from the hub while every POST is slow
# A loaded machine's tick is slow (its POSTs, a ps for each live session),
# and an import was a tick of its own, so a burst of one-event frames queued
# for minutes: what is queued is now one batch, delivered once, then a tick.
echo "a burst from the hub while every POST is slow:"
cat > "$T/burst.py" <<'PY'
import http.client, json, os, re, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
port, first, n, log_path, inbox, bound = (int(open(sys.argv[1]).read()), int(sys.argv[2]), int(sys.argv[3]),
                                          sys.argv[4], sys.argv[5], float(sys.argv[6]))
project, member, session = os.environ["HP"], os.environ["MEMBER"], os.environ["M"]
frames = []
for seq in range(first, first + n):  # one event a frame, as the hub fans a live sender's events out
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    draft = {"ts": ts, "writer": "hub/" + member, "seq": seq, "kind": "human", "from": "human", "member": member,
             "to": [{"session": session, "alias": "m"}], "text": "burst <%d>" % seq, "created": ts}
    frames.append({"t": "events", "project": project,
                   "events": [codes.seal(bytes(range(32)), "log", project, draft, codes.b64url(os.urandom(16)))]})
last = ("burst <%d>" % (first + n - 1)).encode()
t0 = time.time()
c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
c.request("POST", "/control/send", json.dumps({"frames": frames}), {"Content-Type": "application/json"})
took = "never"
if c.getresponse().status == 200:
    while time.time() - t0 < bound:
        if last in open(log_path, "rb").read() and last in open(inbox, "rb").read():
            took = "%.2f" % (time.time() - t0)
            break
        time.sleep(0.05)
got = [int(x) for x in re.findall(rb"burst <(\d+)>", open(inbox, "rb").read())]
print(took, len(got), len(set(got)), "ordered" if got == sorted(got) else "unordered")
PY
start_run
opened() { [ "$(ctl opened "$HP")" = yes ]; }
until_true 200 opened || true
ctl post-delay 0.5
# Seqs 7 on (hub/$MEMBER's 1-6 are taken above); one tick a frame would take
# 300 × 0.5 s at least.
read -r TOOK GOT DISTINCT ORDER <<<"$(python3 "$T/burst.py" "$T/hub.port" 7 300 "$HPLOG/hub.$MEMBER.jsonl" "$INBOX" 30)"
ctl post-delay 0
assert_within "$TOOK" 30 "300 one-event frames with every POST taking 0.5 s are all imported and delivered in a few ticks, not 150 s"
assert_equals "$(grep -c '"text": "burst <' "$HPLOG/hub.$MEMBER.jsonl")" 300 "each imported once"
assert_equals "$GOT $DISTINCT $ORDER" "300 300 ordered" "and each pushed to m once, in seq order"
kill "$RUN"
set +e; wait "$RUN"; set -e

# ---- ending while the hub holds a POST's answer, a backlog still to go
echo "ending during a held POST:"
backlog() { # label — three events of 300 KB under testhost/human, each its own upload
  python3 - "$SCRIPTS/sminos.py" "$HP" "$1" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
for i in range(3):
    mod.log_append(p, mod.writer_id(), "human", **{"from": "human", "to": "*", "text": "%s %d " % (sys.argv[3], i) + "x" * 300000})
PY
}
held_count() { local h; h="$(ctl held)"; [ "$(wc -w <<<"$h" | tr -d ' ')" -ge "$1" ]; }
HELD=0
# The hub holds the answer: sending no byte of it (hold), half its status head
# (stall-headers), or its head and one byte of a ten-byte body (stall-body).
for fault in hold stall-headers stall-body; do
  for ending in SIGTERM "a killed daemon run"; do
    start_run
    ctl fault events "$fault"
    backlog "backlog under $fault"
    HELD=$((HELD + 1))
    until_true 200 held_count "$HELD" || true
    if held_count "$HELD"; then pass "$fault: the hub stalls the answer to the first upload of a backlog of three"; else
      fail "$fault: the hub stalls an upload's answer"; fi
    UP="$(uplink_pid)"
    if [[ "$ending" == SIGTERM ]]; then
      kill "$UP"
      until_true 20 dead "$UP" || true
      if dead "$UP"; then pass "$fault, $ending: the uplink ends within a second"; else
        fail "$fault, $ending: the uplink ends within a second"; fi
      until_true 60 restarted_after "$UP" || true
      if restarted_after "$UP"; then pass "$fault, $ending: its lock is free at once (the supervisor's next uplink holds it)"; else
        fail "$fault, $ending: its lock is free at once"; fi
      kill "$RUN"
      set +e; wait "$RUN"; set -e
    else
      kill -9 "$RUN"
      set +e; wait "$RUN" 2>/dev/null; set -e
      until_true 40 dead "$UP" || true
      if [[ -n "$UP" ]] && dead "$UP"; then pass "$fault, $ending: the orphan ends within 2 s"; else
        fail "$fault, $ending: the orphan ends within 2 s"; echo "    uplink pid '$UP'"; fi
      until_true 40 uplink_free || true
      if uplink_free; then pass "$fault, $ending: uplink.lock is released"; else fail "$fault, $ending: uplink.lock is released"; fi
    fi
    assert_equals "$(ctl after-held)" 0 "$fault, $ending: no later batch of the backlog is posted on that stream"
    ctl release
  done
done
if [ "$(grep -c "the uplink is ending during a POST" "$DLOG")" -ge 6 ]; then pass "each of the six says it ended during a POST"; else
  fail "each of the six says it ended during a POST"; grep "ending" "$DLOG" | tail -8; fi

# ---- the lease while the main thread is held
# The hub renews the machine's lease only with an hb-ack of the stream's
# generation, and lapses it three heartbeats (here 6 s) after the last. A
# lane can be held far longer than that in a POST the hub holds, and the main
# thread in a delivery to a session slow to take its frames, or a slow tick.
# The stream is answered meanwhile; a stream that is really dead still goes
# offline.
echo "the lease while the main thread is held:"
lease_is() { [ "$(ctl lease)" = "$1" ]; }
acks_since() { echo $(( $(ctl acks "$1") - $2 )); }
start_run
until_true 200 opened || true
GEN="$(ctl generation)"
until_true 200 lease_is "$GEN online" || true
assert_equals "$(ctl lease)" "$GEN online" "the stream's hello starts its lease"
ACKS="$(ctl acks "$GEN")"
ctl fault events hold
backlog "held while the heartbeats go on"
HELD=$((HELD + 1))
until_true 200 held_count "$HELD" || true
if held_count "$HELD"; then pass "the hub holds the answer to an upload: the log lane waits in that POST"; else
  fail "the hub holds the answer to an upload"; fi
sleep 10
assert_equals "$(ctl lapses "$GEN") $(ctl lease)" "0 $GEN online" "10 s into the held POST, the stream's lease never lapsed"
if [ "$(acks_since "$GEN" "$ACKS")" -ge 3 ]; then pass "its heartbeats were answered meanwhile"; else
  fail "its heartbeats were answered meanwhile"; echo "    $(acks_since "$GEN" "$ACKS") hb-acks"; fi
ctl release
GEN=$((GEN + 1))
until_true 200 lease_is "$GEN online" || true
assert_equals "$(ctl lease)" "$GEN online" "released and refused, the POST ends the stream, and the next one's lease starts"
ACKS="$(ctl acks "$GEN")"
rm -f "$INBOX.held"
touch "$INBOX.hold"
# Seqs 307 on: hub/$MEMBER's 1-306 are taken above. m's inbox holds each
# frame's close, which a push waits 5 s for: three take the main thread 15 s.
for seq in 307 308 309; do ctl send "$(seal ok "$seq" "said while m holds its frames, $seq")" >/dev/null; done
until_true 200 test -f "$INBOX.held" || true
assert_equals "$(test -f "$INBOX.held" && echo held)" held "a delivery to m waits on m's inbox"
sleep 10
assert_equals "$(ctl lapses "$GEN") $(ctl lease)" "0 $GEN online" "10 s into that delivery, the stream's lease never lapsed"
if [ "$(acks_since "$GEN" "$ACKS")" -ge 3 ]; then pass "its heartbeats were answered meanwhile"; else
  fail "its heartbeats were answered meanwhile"; echo "    $(acks_since "$GEN" "$ACKS") hb-acks"; fi
rm -f "$INBOX.hold"
until_true 200 grep -q "said while m holds its frames, 309" "$INBOX" || true
assert_contains "$(cat "$INBOX")" "said while m holds its frames, 309" "and the delivery goes through"
ctl mute
has_lapsed() { [ "$(ctl lapses "$1")" -ge 1 ]; }
until_true 200 has_lapsed "$GEN" || true
assert_equals "$(ctl lapses "$GEN")" 1 "a half-open stream (no heartbeat, nothing closed): its lease lapses"
until_true 200 gen_is $((GEN + 1)) || true
assert_equals "$(ctl generation)" $((GEN + 1)) "the uplink gives the silent stream up and opens another"
kill "$RUN"
set +e; wait "$RUN"; set -e

# ---- a position of this machine's own writer, refused, and what it writes next
# A lying hub holds a forgery at testhost/<session>:1, which this machine
# refuses, spending the position. Its own next event there takes 2, which it
# uploads past the hub's 1, and whose echo it imports as present.
echo "a refused position of this machine's own writer:"
OWN="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import sminos, sminos_codes as codes, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
key = bytes(range(32))
hl = hublog.HubLog(p, {"key": key, "machine": "testhost"})
w = "testhost/5a000002-0000-4000-8000-0000000000b2"
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
forged = codes.seal(bytes(32), "log", p.id, {"ts": ts, "writer": w, "seq": 1, "kind": "say", "from": "x", "to": "*",
                                             "text": "forged"}, codes.b64url(os.urandom(16)))
_, refused = hl.take([forged])
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
hl.have, hl.sent = {w: 1}, {w: 1}
uploaded = [e["seq"] for frame, _ in hl.uploads() for e in frame["events"] if e["writer"] == w]
appended, echoed = hl.take([hublog.seal(key, p.id, mine)])
print(json.dumps([[f["reason"] for f in refused], mine["seq"], uploaded, appended, [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$OWN" '[["bad-code"], 2, [2], 0, []]' \
  "the forgery is refused, the machine's next event takes the position after it, uploads past the hub's 1, and its echo imports as present"

# A writer under this machine's prefix that it never allocates is no file the
# allocator can open: the frame still yields its rejection and the valid event.
echo "a refused position under this machine's prefix that it does not allocate:"
LONG="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import sminos, sminos_codes as codes, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
key = bytes(range(32))
hl = hublog.HubLog(p, {"key": key, "machine": "testhost"})
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
junk = codes.seal(bytes(32), "log", p.id, {"ts": ts, "writer": "testhost/" + "x" * 300, "seq": 1, "kind": "say",
                                           "from": "x", "to": "*", "text": "junk"}, codes.b64url(os.urandom(16)))
good = hublog.seal(key, p.id, {"ts": ts, "writer": "other/5a000003-0000-4000-8000-0000000000c3", "seq": 1,
                               "kind": "say", "from": "o", "to": "*", "text": "valid"})
appended, refused = hl.take([junk, good])
print(json.dumps([[f["reason"] for f in refused], appended]))
PY
)"
assert_equals "$LONG" '[["bad-code"], 1]' \
  "an unusable writer under the machine's prefix is refused as bad-code and the valid event after it in the frame is appended"

# A malformed event at a position this machine's own event holds is refused
# bad-shape, but its position is coordinated like any own-writer refusal: it is
# not tombstoned over the genuine event, whose echo imports as present.
echo "a malformed event at a position this machine's own event holds:"
HELD="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
key = bytes(range(32))
hl = hublog.HubLog(p, {"key": key, "machine": "testhost"})
w = "testhost/5a000004-0000-4000-8000-0000000000d4"
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
_, refused = hl.take([{"writer": w, "seq": mine["seq"], "ts": None, "kind": "say"}])
appended, echoed = hl.take([hublog.seal(key, p.id, mine)])
print(json.dumps([mine["seq"], [f["reason"] for f in refused], appended, [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$HELD" '[1, ["bad-shape"], 0, []]' \
  "the malformed event is refused bad-shape, and the genuine event's echo imports as present, not refused as spent"

# An event whose code verifies, at a position another event holds here, is
# refused `conflict` (DX2): its code is good, its position taken. The position
# stays the held event's, whose echo still imports as present.
echo "an event that verifies, at a position another event holds:"
CONFLICT="$(python3 - "$SCRIPTS" "$HP" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_hublog as hublog
p = sminos.find_project(sys.argv[2])
key = bytes(range(32))
hl = hublog.HubLog(p, {"key": key, "machine": "testhost"})
w = "testhost/5a000005-0000-4000-8000-0000000000e5"
mine = sminos.log_append(p, w, "say", **{"from": "k", "to": "*", "text": "this machine's own"})
other = hublog.seal(key, p.id, {**mine, "text": "another event at the same position"})
appended, refused = hl.take([other])
echo_appended, echoed = hl.take([hublog.seal(key, p.id, mine)])
print(json.dumps([mine["seq"], appended, [[f["reason"], f["event"]] for f in refused], echo_appended,
                  [f["reason"] for f in echoed]]))
PY
)"
assert_equals "$CONFLICT" '[1, 0, [["conflict", {"writer": "testhost/5a000005-0000-4000-8000-0000000000e5", "seq": 1}]], 0, []]' \
  "a different event that verifies at a held position is refused conflict, not bad-code, and the held event's echo imports as present"

# ---- RL10: the machine cuts over to its endpoint (O12 M5)
# The endpoint stand-in (endpoint_standin.py) writes rl10.json where
# MAWS_USER_DATA puts it. One that names no endpoint (mode 644) is said once.
# One that does is probed beside the hub's stream, never in its place: a
# welcome without the whole identity (an endpoint not enrolled yet), a wrong
# token and a refusal each leave the hub's uplink as it was. Only a whole
# welcome cuts the machine over, for good: no connection to the hub stand-in
# after it, with hub.json replaced or the endpoint gone. The endpoint's
# policy is the machine's, which delivery reads.
echo "RL10, the endpoint (local-only):"
export MAWS_USER_DATA="$T/maws"
EPDIR="$MAWS_USER_DATA/mawsd/endpoint"
IDENTITY="{\"org\": \"org-1\", \"hub\": \"$HUB\", \"name\": \"testhost\", \"former\": [], \"ref\": \"ref-testhost\", \"enrolled\": \"2026-10-27T00:00:00.000Z\"}"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPDIR" "{\"identity\": {\"name\": \"testhost\", \"hub\": \"$HUB\", \"former\": []}}" &
PIDS+=("$!")
until_true 100 test -S "$EPDIR/ctl.sock"
ep() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPDIR" "$@"; }
epq() { ep state | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
hubq() { python3 - "$T/hub.port" "$1" <<'PY'
import http.client, json, sys
c = http.client.HTTPConnection("127.0.0.1", int(open(sys.argv[1]).read()), timeout=30)
c.request("GET", "/control/state")
print(json.dumps(eval(sys.argv[2], {"d": json.loads(c.getresponse().read())})))
PY
}
hub_seen() { hubq '[d["generation"], len(d["posted"]), len(d["requests"])]'; }
next_seq() { python3 -c 'import json, sys; print(max(json.loads(l)["seq"] for l in open(sys.argv[1]) if l.strip()) + 1)' "$HPLOG/hub.$MEMBER.jsonl"; }
cut_over() { test -f "$SMINOS_HOME/daemon/identity.json"; }
probed() { grep -Fq "uplink: the endpoint, probed: $1" "$DLOG"; }
dx2_holds() { # label — the hub's uplink is the one start_run began, its stream open, and a web event reaches m
  local took
  if [[ "$(uplink_pid)" == "$UP" ]] && alive "$UP" && [ "$(ctl opened "$HP")" = yes ]; then
    pass "$1: the hub's uplink runs on, its stream open"; else fail "$1: the hub's uplink runs on, its stream open"; fi
  took="$(deliver_time "$(next_seq)" "said from the web: $1")"
  assert_within "$took" 5.0 "$1: an event from the hub still reaches m"
  assert_equals "$(cut_over && echo there || echo none)" none "$1: no identity.json"
}
ep rl10 '{"mode": "644"}' >/dev/null
NOEP="is mode 644, not 600"
start_run
assert_equals "$(test -n "$UP" && alive "$UP" && echo up)" up "with an rl10.json of mode 644, the uplink holds the hub's stream as before"
sleep 2
assert_equals "$(grep -c "rl10: no endpoint: .*$NOEP" "$DLOG")" 1 "that rl10.json is no endpoint, said once in daemon.log"
assert_equals "$(epq 'd["conns"]')" 0 "and nothing dials its socket"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: running (pid $UP" "daemon status shows the hub's uplink"

echo "  an endpoint not enrolled, a wrong token, a refusal:"
ep rl10 '{}' >/dev/null
until_true 200 probed "present but not enrolled" || true
assert_equals "$(probed "present but not enrolled" && echo said)" said \
  "a welcome without the identity's org and ref is an endpoint not enrolled (daemon.log)"
dx2_holds "an endpoint not enrolled"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: running (pid $UP" "daemon status shows the hub's uplink"
assert_contains "$OUT" "endpoint: present at $EPDIR/rl10.json but not enrolled" "and the endpoint present but not enrolled"
ep set "{\"identity\": $IDENTITY}" >/dev/null
ep rl10 '{"token": "0000000000000000000000000000000000000000000000000000000000000000"}' >/dev/null
until_true 200 probed "it did not welcome this machine (the endpoint closed the socket" || true
assert_equals "$(probed "it did not welcome this machine (the endpoint closed the socket" && echo said)" said \
  "a wrong token: the endpoint closes the socket (daemon.log)"
dx2_holds "a wrong token"
ep set '{"refuse_reason": "not-listed"}' >/dev/null
ep rl10 '{"token": "1111111111111111111111111111111111111111111111111111111111111111"}' >/dev/null
until_true 200 probed "it did not welcome this machine (the endpoint refused the hello: not-listed)" || true
assert_equals "$(probed "it did not welcome this machine (the endpoint refused the hello: not-listed)" && echo said)" said \
  "a refusal (daemon.log)"
dx2_holds "a refusal"
assert_equals "$(epq '[f["frame"]["t"] for f in d["received"]]')" "$(epq '["hello"] * len(d["hellos"])')" \
  "the probes sent the endpoint nothing but their hellos"
ep set '{"refuse_reason": null}' >/dev/null

echo "  the cutover:"
HELLOS="$(epq 'len(d["hellos"])')"
ep rl10 '{}' >/dev/null
until_true 200 cut_over || true
assert_equals "$(cut_over && echo there)" there "a whole welcome to the probe writes identity.json"
moved() { grep -Fq "uplink (pid $UP): the endpoint welcomed this machine, which is cut over: restarting it on RL10 (local-only)" "$DLOG"; }
until_true 200 moved || true
assert_equals "$(moved && echo said)" said "and only then is the hub's uplink stopped, the uplink restarted on RL10 (daemon.log)"
until_true 100 dead "$UP" || true
assert_equals "$(dead "$UP" && echo gone)" gone "the hub's uplink is gone"
assert_equals "$(python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))' "$SMINOS_HOME/daemon/identity.json")" \
  0o600 "identity.json is mode 600"
on_rl10() { [ "$(epq 'len(d["hellos"])')" -ge $((HELLOS + 2)) ]; }
until_true 200 on_rl10 || true
assert_equals "$(epq "[len(d['hellos']) - $HELLOS, all(h['hello']['token'] == d['token'] for h in d['hellos'][$HELLOS:])]")" "[2, true]" \
  "the probe's hello and then the RL10 uplink's, each with rl10.json's token"
NEWUP() { p="$(uplink_pid)"; [[ -n "$p" && "$p" != "$UP" ]] && alive "$p"; }
until_true 100 NEWUP || true
UP="$(uplink_pid)"
sleep 1
SEEN="$(hub_seen)"
run "$SMINOS" daemon status
assert_contains "$OUT" "uplink: RL10 (local-only), running (pid $UP" "daemon status prints uplink: RL10 (local-only)"
rl10_hello() { [ "$(epq "any(f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$HP' for f in d['received'])")" = true ]; }
until_true 200 rl10_hello || true
assert_equals "$(rl10_hello && echo yes)" yes "the hub project is opened on the endpoint's socket"
run "$SMINOS" hub show
assert_contains "$OUT" "cut over" "hub show prints the identity, cut over"

echo "  the endpoint's policy, which delivery reads:"
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
last = max(json.loads(l)["seq"] for l in open(path) if l.strip())
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
e = {"ts": ts, "writer": w, "seq": last + 1, "kind": "human", "from": "human", "member": os.environ["MEMBER"],
     "to": [{"session": os.environ["M"], "alias": "m"}], "text": sys.argv[1], "created": ts}
print(hublog.append_verbatim(p, e))
PY
assert_equals "$(python3 "$T/outside.py" "said from outside while read-only")" appended "an event from outside is in the log"
refused_ro() { grep -rqF "refused-read-only" "$SMINOS_HOME/projects/$HP/" 2>/dev/null; }
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
assert_equals "$(uplink_pid)" "$UP" "a fresh DX7 credential in hub.json after the cutover restarts nothing"
assert_equals "$(hub_seen)" "$SEEN" "and since the cutover nothing has reached the hub stand-in: no stream, no POST, no request"
ep unlink-rl10 >/dev/null
until_true 100 dead "$UP" || true
if dead "$UP"; then pass "with rl10.json removed, the uplink child exits"; else fail "with rl10.json removed, the uplink child exits"; fi
assert_contains "$(cat "$DLOG")" "uplink (pid $UP): rl10.json is gone, and this machine is cut over: no uplink runs until the endpoint does" \
  "daemon.log says why"
assert_contains "$(cat "$DLOG")" "uplink: this machine is cut over to its endpoint, which is not running" "and that it waits for the endpoint"
sleep 2
run "$SMINOS" daemon status
assert_not_contains "$OUT" "uplink: running" "no DX2 uplink starts in its place"
assert_contains "$OUT" "uplink: cut over; the endpoint is not running" "daemon status says cut over; the endpoint is not running"
assert_equals "$(hub_seen)" "$SEEN" "the hub stand-in still saw nothing"
CUTOVER="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["cutover"])' "$SMINOS_HOME/daemon/identity.json")"
HELLOS="$(epq 'len(d["hellos"])')"
ep rl10 '{}' >/dev/null
again() { [ "$(epq 'len(d["hellos"])')" -gt "$HELLOS" ]; }
until_true 200 again || true
sleep 1
assert_equals "$(epq "len(d['hellos']) - $HELLOS")" 1 "rl10.json back: the uplink speaks to the endpoint again, once"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["cutover"])' "$SMINOS_HOME/daemon/identity.json")" \
  "$CUTOVER" "the cutover's time is kept"
kill "$RUN"
set +e; wait "$RUN"; set -e
assert_not_contains "$(cat "$DLOG")" "$KEY" "the DX1 key handed to the endpoint is in no log line"
assert_equals "$(epq 'd["legacy"]["key"]')" "\"$KEY\"" "the endpoint holds it"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES uplink assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) uplink assertions FAILED"
  exit 1
fi
