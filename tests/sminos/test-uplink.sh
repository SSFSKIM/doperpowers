#!/usr/bin/env bash
#
# The uplink (DC4 M1 of the desk): `sminos daemon uplink`, the process `daemon
# run` keeps beside its tick loop, holding the stream down from the hub
# (hub_standin.py stands in for DX2). Pins DC4.G4: the stream is drained and
# an event from the hub reaches a local member within a second while the tick
# sits in a hung git fetch of a hub-less project, and while a derivation runs;
# what fails its code or its shape never enters the log; the uplink and the
# tick loop restart and fail apart; the run lock and the exit on a change of
# the daemon's own code still hold; an event the uplink imports while a tick is
# mid-delivery to the same member is delivered once.
# Hermetic: HOME and SMINOS_HOME are temporary (short, for the inbox sockets),
# `claude` is a stub, and nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/sminos/scripts"
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
until_true() { # tries command... — poll every 50 ms
  local tries="$1"; shift
  for _ in $(seq 1 "$tries"); do "$@" && return 0; sleep 0.05; done
  return 1
}
alive() { kill -0 "$1" 2>/dev/null; }
dead() { ! kill -0 "$1" 2>/dev/null; }
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME
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

# A live session's inbox: appends each frame; while <received>.hold exists a
# frame is written and marked (<received>.held) and its ack waits (a
# connection that sends nothing, a liveness probe, is answered at once).
cat > "$T/inbox.py" <<'PY'
import os, socket, sys, time
path, out = sys.argv[1], sys.argv[2]
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(path)
srv.listen(8)
while True:
    c, _ = srv.accept()
    buf = b""
    while True:
        chunk = c.recv(65536)
        if not chunk:
            break
        buf += chunk
    with open(out, "ab") as f:
        f.write(buf)
    if buf and os.path.exists(out + ".hold"):  # a liveness probe sends nothing: never held
        open(out + ".held", "w").close()
        while os.path.exists(out + ".hold"):
            time.sleep(0.02)
    try:
        c.sendall(b"ok\n")
    except OSError:
        pass
    c.close()
PY
INBOX="$T/in-m.received"
: > "$INBOX"
python3 "$T/inbox.py" "$T/in-m.sock" "$INBOX" & INBOX_PID=$!
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
[ -z "${SSH_ENTERED:-}" ] || : > "$SSH_ENTERED"
while [ -n "${SSH_GATE:-}" ] && [ -f "$SSH_GATE" ]; do sleep 0.05; done
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
assert_contains "$(cat "$INBOX")" "a say the tick delivers" "a tick is pushing an owed say to m, its ack held"
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
rm -f "$SMINOS_HOME/daemon/derive.lock"
mkdir "$SMINOS_HOME/daemon/derive.lock"
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

# ---- daemon run exits on a change to its own code, the uplink's and the codes' included
echo "a change of code:"
CACHE="$T/cache"
mkdir -p "$CACHE"
cp -R "$REPO_ROOT/skills/sminos" "$CACHE/"
GEN=3
for changed in sminos_uplink.py sminos_codes.py; do
  GEN=$((GEN + 1))
  "$CACHE/sminos/scripts/sminos" daemon run --interval 1 > "$T/run-code.out" 2>&1 & RUNC=$!
  PIDS+=("$RUNC")
  until_true 200 gen_is "$GEN" || true
  UP="$(uplink_pid)"
  sleep 1.2
  touch "$CACHE/sminos/scripts/$changed"
  until_true 200 dead "$RUNC" || true
  if alive "$RUNC"; then fail "run exits once $changed changes"; kill "$RUNC"; else
    set +e; wait "$RUNC"; RUNC_RC=$?; set -e
    assert_rc 0 "$RUNC_RC" "run exits 0 once $changed changes"
  fi
  assert_contains "$(cat "$T/run-code.out")" "its code changed" "saying why"
  if [[ -n "$UP" ]] && dead "$UP"; then pass "its uplink ($UP) is stopped with it"; else fail "its uplink is stopped with it"; fi
done

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

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES uplink assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) uplink assertions FAILED"
  exit 1
fi
