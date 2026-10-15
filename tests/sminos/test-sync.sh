#!/usr/bin/env bash
#
# Sync through the hub (DC4 M3 of the desk): two machines simulated on one
# Mac — two SMINOS_HOMEs, two enrolled names, alpha and beta — each with its
# `daemon run` and its uplink, against hub_standin.py's DX2 log plane. Pins
# DC4.G2: per-writer counts, last seq, and payloads identical on both machines
# and the hub after a burst of `say` on both, a daemon restart, a dropped
# connection, a POST the hub refused or whose answer was lost, and a stream
# gone silent; a fresh machine bootstraps the project from the hub; the
# daemon never runs git for a hub project; an event without a valid code
# never enters the log and is reported up as `rejected` — a forged say under
# another machine's writer, an authentic event of one project replayed into
# another's feed, a hub/ event carrying a field its code does not cover (via,
# msg_id) or a position its shape refuses, a nonce seen before, and what is
# no log event at all — while the writer's later events still arrive. Also:
# hello on every new stream before any upload, hb-ack, the machine's presence
# after every connect, a live member that joined under a former name joined
# again under the enrolled one, and the uplink restarted when hub.json changes.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$REPO_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/sms.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
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
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; }
until_true() { # tries command... — poll every 50 ms
  local tries="$1"; shift
  for _ in $(seq 1 "$tries"); do "$@" && return 0; sleep 0.05; done
  return 1
}
alive() { kill -0 "$1" 2>/dev/null; }
dead() { ! kill -0 "$1" 2>/dev/null; }
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
# One machine: its HOME, its SMINOS_HOME, its host name; the verbs after it run there.
as() { # a|b host
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
# ssh, as git calls it for the projects' remote: a hub project must never reach it.
cat > "$T/bin/fake-ssh" <<SSH
#!/bin/sh
: > "$T/ssh-entered"
exit 1
SSH
chmod +x "$T/bin/fake-ssh"
export PATH="$T/bin:$PATH" GIT_SSH_COMMAND="$T/bin/fake-ssh" GIT_SSH_VARIANT=simple

# A live session's inbox: appends each frame it receives and answers ok.
cat > "$T/inbox.py" <<'PY'
import socket, sys
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(sys.argv[1])
srv.listen(8)
while True:
    c, _ = srv.accept()
    buf = b""
    while True:
        chunk = c.recv(65536)
        if not chunk:
            break
        buf += chunk
    with open(sys.argv[2], "ab") as f:
        f.write(buf)
    try:
        c.sendall(b"ok\n")
    except OSError:
        pass
    c.close()
PY
inbox() { # name → INBOX_PID; the socket $T/<name>.sock, the frames in $T/<name>.received
  : > "$T/$1.received"
  python3 "$T/inbox.py" "$T/$1.sock" "$T/$1.received" & INBOX_PID=$!
  PIDS+=("$INBOX_PID")
  until_true 100 test -S "$T/$1.sock"
}

# The hub stand-in, a heartbeat every second.
python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-0 secret-0 1000 & PIDS+=("$!")
until_true 100 test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"
OTHER_PROJECT=0d9e8f7a-6b5c-4d3e-a2f1-0e9d8c7b6a59
MEMBER=4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c

cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, sys
port = int(open(sys.argv[1]).read())

def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd, args = sys.argv[2], sys.argv[3:]
if cmd == "token":
    print(call("POST", "/control/enrollment", {})[1]["token"])
elif cmd == "code":  # hub token machine key
    body = json.dumps(dict(zip(("hub", "org", "token", "machine", "key"), [args[0], "org-1", *args[1:4]])),
                      separators=(",", ":")).encode()
    print("smns-enroll-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
elif cmd == "state":  # a python expression over the state, d
    print(json.dumps(eval(args[0], {"d": call("GET", "/control/state")[1]})))
elif cmd == "save":  # the state, to a file
    json.dump(call("GET", "/control/state")[1], open(args[0], "w"))
elif cmd == "gen":
    print(call("GET", "/control/state")[1]["generations"].get(args[0], 0))
elif cmd == "inject":  # project events-json
    call("POST", "/control/inject", {"project": args[0], "events": json.loads(args[1])})
elif cmd == "drop":
    print(json.dumps(call("POST", "/control/drop", {"machine": args[0]} if args else {})[1]["dropped"]))
elif cmd == "send":  # machine frame-json (or a list of frames)
    frames = json.loads(args[1])
    print(call("POST", "/control/send", {"machine": args[0], "frames": frames if isinstance(frames, list) else [frames]})[0])
elif cmd == "mute":
    call("POST", "/control/mute", {"machine": args[0]})
elif cmd == "fault":  # machine has fault
    call("POST", "/control/post-fault", {"faults": [{"machine": args[0], "has": args[1], "fault": args[2]}]})
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }

# Events as a lying hub could hold them: sealed with the org key (or another),
# for this project (or another), then altered.
cat > "$T/seal.py" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
variant, writer, seq, text = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
to = [{"session": s, "alias": a} for s, a in zip(sys.argv[5::2], sys.argv[6::2])] or "*"
key, project = bytes(range(32)), os.environ["PID"]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
if writer.startswith("hub/"):
    draft = {"kind": "human", "from": "human", "member": writer[4:], "to": to, "text": text, "created": ts}
else:
    draft = {"ts": ts, "writer": writer, "seq": seq, "kind": "say", "from": "mallory", "to": to, "text": text}
if variant == "wrong-key":
    key = bytes([0xff] * 32)
if variant == "other-project":
    project = os.environ["OTHER_PROJECT"]
e = codes.seal(key, "log", project, draft, codes.b64url(os.urandom(16)))
if writer.startswith("hub/"):
    e = {"ts": ts, "writer": writer, "seq": seq, **e}
if variant in ("via", "msg_id"):
    e[variant] = "set by the hub"
elif variant == "ts":
    e["ts"] = ts[:-5] + "Z"
elif variant == "shapeless":
    e["seq"] = "the third"
print(json.dumps([e]))
PY
seal() { python3 "$T/seal.py" "$@"; }

# The log of the project as each machine and the hub hold it, writer by
# writer: counts, last seq, and payloads (each event's canonical form without
# its code: an event a machine wrote is stored without one), and every code a
# machine stored the same as the hub's. Writers under a prefix in $SKIP are
# left out (a former name's, which stay local).
cat > "$T/compare.py" <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
pid, state = sys.argv[1], json.load(open(sys.argv[2]))
skip = tuple(p for p in os.environ.get("SKIP", "").split(",") if p)
hub = {w: evs for w, evs in state["projects"].get(pid, {}).get("writers", {}).items()}
def local(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.jsonl")):
        evs = [json.loads(l) for l in open(p) if l.strip()]
        if evs:
            out[evs[0]["writer"]] = sorted(evs, key=lambda e: e["seq"])
    return out
sides = {"hub": hub, **{name: local(d) for name, d in zip(("alpha", "beta"), sys.argv[3:])}}
writers = sorted(w for w in set().union(*sides.values()) if not w.startswith(skip))
bad, n = [], 0
def payload(e):
    return codes.canonical({k: v for k, v in e.items() if k != "mac"})
for w in writers:
    views = {s: v.get(w, []) for s, v in sides.items()}
    shape = {s: (len(evs), evs[-1]["seq"] if evs else 0) for s, evs in views.items()}
    if len(set(shape.values())) != 1:
        bad.append("%s: (count, last) %s" % (w, shape))
        continue
    if len({tuple(map(payload, evs)) for evs in views.values()}) != 1:
        bad.append("%s: payloads differ" % w)
    for s in ("alpha", "beta"):
        for e, h in zip(views[s], views["hub"]):
            if "mac" in e and e["mac"] != h.get("mac"):
                bad.append("%s:%d: %s holds another code than the hub" % (w, e["seq"], s))
    n += shape["hub"][0]
print("identical: %d writers, %d events" % (len(writers), n) if not bad else "\n".join(bad))
sys.exit(1 if bad else 0)
PY
ALOG=""
BLOG=""
compare() { ctl save "$T/state.json" && python3 "$T/compare.py" "$PID" "$T/state.json" "$ALOG" "$BLOG"; }
identical() { compare >/dev/null 2>&1; }
settle() { # label — wait until the two machines and the hub hold the same log
  until_true 400 identical || true
  run compare
  if [[ "$RC" == 0 ]]; then pass "$1: identical on alpha, beta, and the hub ($OUT)"; else
    fail "$1: identical on alpha, beta, and the hub"; echo "    ${OUT:0:1500}"; fi
}
says() { # count label — `say` as the operator, from the working directory
  local i
  for i in $(seq 1 "$1"); do "$SMINOS" say "$2 $i" >/dev/null; done
}
start_daemon() { # → DAEMON_PID (of the machine `as` named last)
  "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & DAEMON_PID=$!
  PIDS+=("$DAEMON_PID")
}
uplink_pid() { sed -n 's/^pid \([0-9]*\) .*/\1/p' "$1/daemon/uplink.lock" 2>/dev/null || true; }
gen_above() { [ "$(ctl gen "$1")" -gt "$2" ]; }

# ---- alpha: enrolled, a hub project, a live session
echo "alpha:"
as a alpha
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
RA="$T/a/repo"
mkdir -p "$RA"
gitq init -q "$RA"
cd "$RA"
"$SMINOS" project init --name syncproj --hub --remote "ssh://archive$T/archive.git" >/dev/null
PID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RA/.smns")"
export PID OTHER_PROJECT
ALOG="$T/a/s/projects/$PID/log"
BLOG="$T/b/s/projects/$PID/log"
MA=5a000001-0000-4000-8000-0000000000a1
inbox ma
printf '{"pid":%s,"sessionId":"%s","name":"ma","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$MA" "$RA" "$T/ma.sock" > "$HOME/.claude/sessions/ma.json"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "ma"' "ma joins syncproj on alpha"
start_daemon
A_DAEMON=$DAEMON_PID
on_hub() { ctl state "d['projects'].get('$PID', {}).get('vector', {}).get('$1', 0)"; }
hub_has() { [ "$(on_hub "$1")" -ge "$2" ]; }
until_true 200 hub_has "alpha/$MA" 1 || true
assert_equals "$(ctl state "d['projects']['$PID']['writers']['alpha/$MA'][0]['kind']")" '"joined"' \
  "alpha's uplink opens the project and uploads ma's joined"

echo "a burst on alpha alone:"
says 10 "alpha alone"
CLAUDE_CODE_SESSION_ID=$MA says 5 "ma alone"
SKIP="betaold/"
export SKIP
compare_a() { ctl save "$T/state.json" && python3 - "$PID" "$T/state.json" "$ALOG" <<'PY'
import glob, json, sys
pid, state, d = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
hub = {w: [e["seq"] for e in evs] for w, evs in state["projects"][pid]["writers"].items()}
mine = {}
for p in glob.glob(d + "/*.jsonl"):
    evs = [json.loads(l) for l in open(p) if l.strip()]
    mine[evs[0]["writer"]] = [e["seq"] for e in evs]
sys.exit(0 if hub == mine else 1)
PY
}
until_true 200 compare_a || true
if compare_a; then pass "alpha's writers are on the hub, each event once"; else fail "alpha's writers are on the hub"; fi
assert_equals "$(python3 - "$ALOG" <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes, sminos_hublog as hublog
key, pid = bytes(range(32)), os.environ["PID"]
e = json.loads(open(glob.glob(sys.argv[1] + "/alpha.human.jsonl")[0]).readline())
once, again = hublog.seal(key, pid, e), hublog.seal(key, pid, dict(e))
print(once == again and codes.verifies(key, "log", pid, once) and "mac" not in e)
PY
)" True "an event this machine wrote is stored without a code, and seals to the same code at every upload"
assert_equals "$(python3 - "$ALOG" <<'PY'
import glob, hashlib, hmac, json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes, sminos_hublog as hublog
key, pid = bytes(range(32)), os.environ["PID"]
e = json.loads(open(glob.glob(sys.argv[1] + "/alpha.human.jsonl")[0]).readline())
# The derived form of DX1, written out here:smns-hub-nonce-v1 LF <project id> LF <JCS of the event without mac>.
want = codes.b64url(hmac.new(key, ("smns-hub-nonce-v1\n%s\n%s" % (pid, codes.canonical(e))).encode(), hashlib.sha256).digest()[:16])
n = hublog.nonce_for(key, pid, e)
print(json.dumps([n == want, hublog.seal(key, pid, e)["mac"]["nonce"] == n,
       hublog.nonce_for(key, pid, {**e, "mac": {"nonce": "x"}}) == n,
       hublog.nonce_for(key, pid, {**e, "seq": e["seq"] + 1}) != n,
       hublog.nonce_for(key, pid, {**e, "writer": "alpha/other"}) != n,
       hublog.nonce_for(key, os.environ["OTHER_PROJECT"], e) != n]))
PY
)" "[true, true, true, true, true, true]" \
  "the nonce is DX1's derived form: the same event gives the same nonce (a mac it carries aside), another position or another project another"

# ---- beta: a machine that held its sessions under another name, then enrolls as beta
echo "beta, fresh, renamed:"
as b betaold
RB="$T/b/repo"
cp -R "$RA" "$RB"
cd "$RB"
MB=5b000001-0000-4000-8000-0000000000b1
NB=5b000002-0000-4000-8000-0000000000b2
inbox mb
MB_INBOX=$INBOX_PID
sleep 600 & NB_PID=$!
PIDS+=("$NB_PID")
printf '{"pid":%s,"sessionId":"%s","name":"mb","nameSource":"derived","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$MB_INBOX" "$MB" "$RB" "$T/mb.sock" > "$HOME/.claude/sessions/mb.json"
printf '{"pid":%s,"sessionId":"%s","name":"nb","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$NB_PID" "$NB" "$RB" > "$HOME/.claude/sessions/nb.json"
printf '[{"id": "mbshort", "sessionId": "%s", "state": "idle"}]\n' "$MB" > "$STUB_STATE/agents.json"
"$SMINOS" seat add syncproj mb --session "$MB" >/dev/null
run "$SMINOS" list --json
assert_contains "$OUT" '"machine": "betaold"' "the seat mb and the session nb join as betaold"
assert_equals "$(find "$BLOG" -name 'betaold.*.jsonl' | wc -l | tr -d ' ')" 2 "beta's log holds its own two writers, and nothing of alpha's"
run "$SMINOS" hub enroll --name beta <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")"
assert_contains "$OUT" "enrolled this machine as beta" "beta enrolls under a new name"
start_daemon
B_DAEMON=$DAEMON_PID
settle "a fresh machine bootstraps the project from the hub"
assert_equals "$(ctl state "sorted(w for w in d['projects']['$PID']['vector'] if w.startswith('beta'))")" \
  "[\"beta/$MB\", \"beta/$NB\"]" "the seat and the session that joined as betaold join again as beta, and only as beta"
assert_contains "$(cat "$T/b/s/daemon.log")" "mb in syncproj joined again as beta (it had joined as betaold)" "saying so"
as a alpha
cd "$RA"
run "$SMINOS" list --json
members_of() { printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))'; }
assert_equals "$(members_of)" "[('ma', 'alpha', True), ('mb', 'beta', False), ('nb', 'beta', False)]" \
  "alpha sees mb and nb as beta's members"
as b beta
cd "$RB"
run "$SMINOS" list --json
assert_equals "$(members_of)" "[('ma', 'alpha', False), ('mb', 'beta', True), ('nb', 'beta', True)]" \
  "beta keeps mb and nb its own, and sees ma as alpha's"
SKIP="betaold/,hub/"
export SKIP

# ---- a burst on both, and messages across
echo "a burst on both:"
as a alpha
(cd "$RA" && says 20 "alpha burst" && CLAUDE_CODE_SESSION_ID=$MA "$SMINOS" say "@mb ping from ma" >/dev/null) & BURST_A=$!
as b beta
(cd "$RB" && says 20 "beta burst" && CLAUDE_CODE_SESSION_ID=$MB "$SMINOS" say "@ma pong from mb" >/dev/null) & BURST_B=$!
wait "$BURST_A" "$BURST_B"
settle "after a burst of say on both"
until_true 200 grep -q "ping from ma" "$T/mb.received" || true
assert_contains "$(cat "$T/mb.received")" "ping from ma" "ma's say reaches mb on beta through the hub"
until_true 200 grep -q "pong from mb" "$T/ma.received" || true
assert_contains "$(cat "$T/ma.received")" "pong from mb" "and mb's reaches ma on alpha"

# ---- a daemon restart
echo "a daemon restart:"
kill "$A_DAEMON"
set +e; wait "$A_DAEMON"; set -e
as a alpha
(cd "$RA" && says 5 "alpha while its daemon is down")
as b beta
(cd "$RB" && says 5 "beta while alpha's daemon is down")
as a alpha
A_GEN="$(ctl gen alpha)"
start_daemon
A_DAEMON=$DAEMON_PID
until_true 200 gen_above alpha "$A_GEN" || true
settle "after alpha's daemon restarts"

# ---- a dropped connection
echo "a dropped connection:"
B_GEN="$(ctl gen beta)"
assert_equals "$(ctl drop beta)" '["beta"]' "the hub drops beta's stream"
as a alpha
(cd "$RA" && says 3 "alpha while beta reconnects")
as b beta
(cd "$RB" && says 3 "beta while it reconnects")
until_true 200 gen_above beta "$B_GEN" || true
settle "after beta's connection drops"

# ---- POSTs the hub did not take, or whose answer was lost
echo "a POST refused, a POST's answer lost:"
B_GEN="$(ctl gen beta)"
ctl fault beta events 503
as b beta
(cd "$RB" && says 2 "beta, refused once")
until_true 200 gen_above beta "$B_GEN" || true
assert_contains "$(cat "$T/b/s/daemon.log")" "a POST was not delivered (the hub answered 503" "a 503 is not taken as delivered"
settle "after a POST answered 503"
B_GEN="$(ctl gen beta)"
ctl fault beta events apply-502
(cd "$RB" && says 2 "beta, answer lost")
until_true 200 gen_above beta "$B_GEN" || true
assert_contains "$(cat "$T/b/s/daemon.log")" "a POST was not delivered (the hub answered 502" "nor a 502 from a hub that applied it"
settle "after a POST applied but answered 502"
assert_equals "$(ctl state "[a for a in d['projects']['$PID']['audit'] if a['kind'] == 'refused']")" "[]" \
  "an upload sent again is the same payload: the hub refuses nothing"

# ---- a stream gone silent
echo "a stream gone silent:"
A_GEN="$(ctl gen alpha)"
ctl mute alpha
START=$(date +%s)
until_true 200 gen_above alpha "$A_GEN" || true
TOOK=$(( $(date +%s) - START ))
if gen_above alpha "$A_GEN" && [ "$TOOK" -le 6 ]; then pass "alpha reconnects once its stream is silent for three heartbeats (${TOOK}s)"; else
  fail "alpha reconnects once its stream is silent for three heartbeats"; echo "    took ${TOOK}s"; fi
assert_contains "$(cat "$T/a/s/daemon.log")" "the stream closed: timed out" "saying the stream timed out"

# ---- hub.json changes
echo "hub.json changes:"
B_UP="$(uplink_pid "$T/b/s")"
B_GEN="$(ctl gen beta)"
python3 - "$T/b/s/daemon/hub.json" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1])); d["enrolled"] = "2026-10-15T00:00:00Z"
open(sys.argv[1] + ".tmp", "w").write(json.dumps(d)); os.chmod(sys.argv[1] + ".tmp", 0o600); os.replace(sys.argv[1] + ".tmp", sys.argv[1])
PY
restarted() { local p; p="$(uplink_pid "$T/b/s")"; [[ -n "$p" && "$p" != "$B_UP" ]] && alive "$p"; }
until_true 60 restarted || true
if restarted; then pass "the supervisor restarts the uplink within 3 s of hub.json changing"; else fail "the supervisor restarts the uplink when hub.json changes"; fi
until_true 100 gen_above beta "$B_GEN" || true
assert_contains "$(cat "$T/b/s/daemon.log")" "hub.json changed; restarting it" "saying why"

# ---- projects that stop being hub projects of this org
echo "projects that leave the hub:"
as a alpha
for q in q1 q2 q3; do
  mkdir -p "$T/a/$q"
  gitq init -q "$T/a/$q"
  (cd "$T/a/$q" && "$SMINOS" project init --name "$q" --hub >/dev/null && "$SMINOS" say "first in $q" >/dev/null)
done
qid() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$T/a/$1/.smns"; }
q_on_hub() { [ "$(ctl state "d['projects'].get('$(qid "$1")', {}).get('vector', {}).get('alpha/human', 0)")" = "$2" ]; }
qs_on_hub() { q_on_hub q1 1 && q_on_hub q2 1 && q_on_hub q3 1; }
until_true 200 qs_on_hub || true
if qs_on_hub; then pass "three more hub projects open and upload"; else fail "three more hub projects open and upload"; fi
A_GEN="$(ctl gen alpha)"
python3 - "$T/a" <<'PY'
import json, sys
for q, change in (("q1", lambda d: d.update(hub={"org": "org-1"})), ("q2", lambda d: d["hub"].update(org="org-2")),
                  ("q3", lambda d: d.pop("hub"))):
    path = "%s/%s/.smns" % (sys.argv[1], q)
    d = json.load(open(path)); change(d); json.dump(d, open(path, "w"))
PY
until_true 200 gen_above alpha "$A_GEN" || true
for q in q1 q2 q3; do
  (cd "$T/a/$q" && "$SMINOS" say "after $q left the hub" >/dev/null 2>&1)
done
# What alpha appends from here is uploaded; a say in syncproj after them marks the time.
(cd "$RA" && says 1 "alpha after the projects left")
settle "after three projects left the hub"
for q in q1 q2 q3; do
  if q_on_hub "$q" 1; then pass "$q's later say never reaches the hub"; else fail "$q's later say never reaches the hub"; fi
done
assert_contains "$(grep "no longer a hub project of org org-1" "$T/a/s/daemon.log")" "q1" "a malformed hub ends the project's sync, saying so"
assert_contains "$(grep "no longer a hub project of org org-1" "$T/a/s/daemon.log")" "q2" "so does a hub of another org"
assert_contains "$(grep "no longer a hub project of org org-1" "$T/a/s/daemon.log")" "q3" "and a .smns that names no hub"
assert_equals "$(ctl state "sorted(p for p, v in d['projects'].items() if v['open'].get('alpha') == d['generations']['alpha'] and p != '$PID')")" "[]" \
  "alpha's new stream opens none of them at the hub"

# ---- frames past a frame's bound travel as parts, both ways
echo "frames as parts:"
PARTS="$(python3 - "$MB" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
member = "0123456789abcdef0123456789abcdef"
draft = {"kind": "human", "from": "human", "member": member, "to": [{"session": sys.argv[1], "alias": "mb"}],
         "text": "in parts: héllo \U0001F600 " + "x" * 3000, "created": ts}
e = {"ts": ts, "writer": "hub/" + member, "seq": 1,
     **codes.seal(bytes(range(32)), "log", os.environ["PID"], draft, codes.b64url(os.urandom(16)))}
text = json.dumps({"t": "events", "project": os.environ["PID"], "events": [e]}, ensure_ascii=False)
cut = [0, len(text) // 3, 2 * len(text) // 3, len(text)]
parts = [{"t": "part", "id": "set-1", "index": i, "count": 3, "data": text[cut[i]:cut[i + 1]]} for i in range(3)]
print(json.dumps([parts[2], parts[0], parts[1]]))
PY
)"
ctl send beta "$PARTS" >/dev/null
until_true 100 grep -q "in parts:" "$T/mb.received" || true
assert_contains "$(cat "$T/mb.received")" "in parts: h" "an events frame the hub sends as three parts, out of order, is joined, imported, and delivered"
as a alpha
python3 - "$PID" <<'PY'
import os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_codes as codes, sminos_hublog as hublog
p = sminos.find_project(sys.argv[1])
writer = sminos.writer_id()
with open(sminos.writer_path(p, writer), "rb") as f:
    seq = sminos._last_seq(f) + 1
probe = {"ts": sminos.now(ms=True), "writer": writer, "seq": seq, "kind": "say", "from": "human", "to": "*", "text": ""}
base = len(codes.canonical(hublog.seal(bytes(range(32)), p.id, probe)).encode())
# The event within the hub's bound for one event (1 MiB canonical), its frame past a frame's.
sminos.log_append(p, writer, "say", **{"from": "human", "to": "*", "text": "x" * ((1 << 20) - 30 - base)})
PY
settle "after an event whose frame is past 1 MiB"
assert_contains "$(ctl state "[p['body'][:60] for p in d['posted'] if p['machine'] == 'alpha' and '\"t\":\"part\"' in p['body']][:1]")" \
  '{\"t\":\"part\"' "alpha uploads it as parts"

# ---- what each stream carried
echo "what each stream carried:"
ctl save "$T/state.json"
assert_equals "$(python3 - "$T/state.json" "$PID" <<'PY'
import json, sys
d, pid = json.load(open(sys.argv[1])), sys.argv[2]
bad, streams = [], 0
for machine in ("alpha", "beta"):
    gens = {}
    for p in d["posted"]:
        if p["machine"] != machine or p["status"] != 200:
            continue
        frames = [json.loads(l) for l in p["body"].split("\n") if l.strip()]
        g = gens.setdefault(p["generation"], {"hello": False, "machine": False})
        for f in frames:
            if f["t"] == "hello" and f["project"] == pid:
                g["hello"] = True
            if f["t"] == "session" and f["message"]["kind"] == "machine" and f["message"]["project"] == pid:
                g["machine"] = True
                if not any(c["path"].endswith("/repo") and c["branch"] == "main" for c in f["message"]["body"]["checkouts"]):
                    bad.append("a machine presence without the checkout: %r" % f["message"]["body"])
            if f["t"] == "events" and not g["hello"]:
                bad.append("%s uploaded on stream %s before its hello" % (machine, p["generation"]))
    streams += len(gens)
    for g, seen in gens.items():
        if not (seen["hello"] and seen["machine"]):
            bad.append("%s's stream %s: %r" % (machine, g, seen))
print(bad or ("ok" if streams >= 8 else "only %d streams" % streams))
PY
)" "ok" "on each of the eight streams of both machines: hello and the machine's presence (its checkout and branch) before any upload"
acked() { [ "$(ctl state "sorted({a['machine'] for a in d['hb_acks'] if str(a['generation']) == str(d['generations'][a['machine']])})")" = '["alpha", "beta"]' ]; }
until_true 100 acked || true
if acked; then pass "each machine answers its current stream's heartbeats (hb-ack, with the generation)"; else
  fail "each machine answers its current stream's heartbeats"; fi
assert_equals "$(test -e "$T/ssh-entered" && echo fetched || echo never)" never "neither machine ever ran git against the project's remote"
assert_equals "$(test -e "$ALOG/.git" -o -e "$BLOG/.git" && echo git || echo none)" none "nor made its log a git working tree"

# ---- forgeries, as a lying hub would hold them
echo "refused before the log:"
F=5f000000-0000-4000-8000-0000000000f1
ctl inject "$PID" "$(seal wrong-key "alpha/$F" 1 "forged: a say under alpha's writer" "$MB" mb)"
ctl inject "$PID" "$(seal ok "hub/$MEMBER" 1 "from the web, first" "$MB" mb)"
ctl inject "$PID" "$(seal other-project "hub/$MEMBER" 2 "forged: replayed from another project" "$MB" mb)"
ctl inject "$PID" "$(seal via "hub/$MEMBER" 3 "forged: via added" "$MB" mb)"
ctl inject "$PID" "$(seal msg_id "hub/$MEMBER" 4 "forged: msg_id added" "$MB" mb)"
ctl inject "$PID" "$(seal ts "hub/$MEMBER" 5 "forged: a position its shape refuses" "$MB" mb)"
FIRST="$(ctl state "d['projects']['$PID']['writers']['hub/$MEMBER'][0]")"
REPLAY="$(python3 -c 'import json, sys; e = json.loads(sys.argv[1]); e["seq"] = 6; print(json.dumps([e]))' "$FIRST")"
ctl inject "$PID" "$REPLAY"
# What no hub could store, the lying hub sends as it is.
SHAPELESS="$(seal shapeless "hub/$MEMBER" 7 "forged: no seq a log holds" "$MB" mb)"
for m in alpha beta; do
  ctl send "$m" "{\"t\": \"events\", \"project\": \"$PID\", \"events\": $SHAPELESS}" >/dev/null
done
ctl inject "$PID" "$(seal ok "hub/$MEMBER" 7 "from the web, after the forgeries" "$MB" mb)"
rejections() { ctl state "len([a for a in d['projects']['$PID']['audit'] if a['kind'] == 'rejected'])"; }
rejected_all() { [ "$(rejections)" -ge 14 ]; }
until_true 200 rejected_all || true
until_true 200 grep -q "after the forgeries" "$T/mb.received" || true
for side in a b; do
  assert_not_contains "$(cat "$T/$side/s/projects/$PID/log/"*.jsonl)" "forged:" "no forged event enters $side's log"
done
assert_not_contains "$(cat "$T/mb.received")" "forged:" "or reaches mb"
assert_contains "$(cat "$T/mb.received")" "from the web, first" "the authentic web human before them reaches mb"
assert_contains "$(cat "$T/mb.received")" "from the web, after the forgeries" "and so does the one after them: a refused position holds back no later event"
ctl save "$T/state.json"
reported() { # machine writer seq reason — how many rejected reports name it so
  python3 - "$T/state.json" "$PID" "$@" <<'PY'
import json, sys
d, pid, machine, writer, seq, reason = json.load(open(sys.argv[1])), *sys.argv[2:]
print(len([a for a in d["projects"][pid]["audit"] if a["kind"] == "rejected" and a["machine"] == machine
           and a["reason"] == reason and (a["event"] == {"writer": writer, "seq": int(seq)} if writer else a["event"] is None)
           and isinstance(a.get("nonce"), str)]))
PY
}
for m in alpha beta; do
  assert_equals "$(reported $m "alpha/$F" 1 bad-code)" 1 "$m reports the say forged under alpha's writer: bad-code, with its position and nonce"
  assert_equals "$(reported $m "hub/$MEMBER" 2 bad-code)" 1 "$m reports the event replayed from another project: bad-code"
  assert_equals "$(reported $m "hub/$MEMBER" 3 bad-code)" 1 "$m reports the hub/ event carrying via: bad-code"
  assert_equals "$(reported $m "hub/$MEMBER" 4 bad-code)" 1 "$m reports the hub/ event carrying msg_id: bad-code"
  assert_equals "$(reported $m "hub/$MEMBER" 5 bad-code)" 1 "$m reports the hub/ event whose ts its shape refuses: bad-code"
  assert_equals "$(reported $m "hub/$MEMBER" 6 seen-nonce)" 1 "$m reports the web human replayed at another seq: seen-nonce"
  assert_equals "$(reported $m "" 0 bad-shape)" 1 "$m reports what is no log event: bad-shape, its event null, its nonce kept"
done
assert_contains "$(cat "$T/b/s/daemon.log")" "its code does not verify for project $PID" "beta's daemon.log says why"
assert_equals "$(ctl state "d['projects']['$PID']['vector']['hub/$MEMBER']")" 7 "the hub holds hub/$MEMBER to 7"
# Every reader takes the hole of the spent positions in its stride: delivery, the chat, the record of what is settled.
ctl inject "$PID" "$(seal ok "hub/$MEMBER" 8 "from the web, later still" "$MB" mb)"
until_true 200 grep -q "later still" "$T/mb.received" || true
assert_contains "$(cat "$T/mb.received")" "from the web, later still" "a later web human is delivered past the spent positions"
as b beta
run "$SMINOS" chat syncproj -n 400
assert_contains "$OUT" "from the web, after the forgeries" "beta's chat shows the human after the hole"
assert_contains "$OUT" "from the web, later still" "and the one after it"
assert_not_contains "$OUT" "forged:" "and nothing forged"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$BLOG/../delivered/$MB.json" "hub/$MEMBER")" \
  "{'settled': 8, 'pending': None, 'attempts': 0}" "mb's delivery record settles hub/$MEMBER at 8, past the hole, nothing pending"
assert_not_contains "$(cat "$T/b/s/daemon.log")" "out of order" "no deliverer finds the hole out of order"
# A spent position is a tombstone: an event that verifies, arriving there later, is refused too.
ctl send beta "{\"t\": \"events\", \"project\": \"$PID\", \"events\": $(seal wrong-key "hub/$MEMBER" 9 "forged: at 9" "$MB" mb)}" >/dev/null
ctl send beta "{\"t\": \"events\", \"project\": \"$PID\", \"events\": $(seal ok "hub/$MEMBER" 9 "valid, at a spent position" "$MB" mb)}" >/dev/null
# A lying hub's lone surrogates, escaped in its JSON: one in a writer, one in a nonce.
SURROGATES="$(python3 - "$(seal ok "hub/$MEMBER" 10 "forged: a surrogate in the writer" "$MB" mb)" \
  "$(seal ok "hub/$MEMBER" 11 "forged: a surrogate in the nonce" "$MB" mb)" <<'PY'
import json, sys
a, b = json.loads(sys.argv[1])[0], json.loads(sys.argv[2])[0]
a["writer"] += "\ud800"
b["mac"]["nonce"] = "\udfff" + b["mac"]["nonce"][1:]
print(json.dumps([a, b]))
PY
)"
ctl send beta "{\"t\": \"events\", \"project\": \"$PID\", \"events\": $SURROGATES}" >/dev/null
rejected_beta() { [ "$(rejections)" -ge 18 ]; }
until_true 200 rejected_beta || true
ctl save "$T/state.json"
assert_equals "$(reported beta "hub/$MEMBER" 9 bad-code)" 2 "beta refuses both events at 9: the forgery, then the valid one at its tombstone"
assert_not_contains "$(cat "$BLOG/hub.$MEMBER.jsonl")" "valid, at a spent position" "nothing is appended at a spent position"
assert_contains "$(ctl state "[a['message'] for a in d['projects']['$PID']['audit'] if a['kind'] == 'rejected' and a['event'] == dict(writer='hub/$MEMBER', seq=9)]")" \
  "was refused here before" "saying it was refused there before"
assert_equals "$(ctl state "sorted((a['reason'], a['event']['seq'] if a['event'] else None, (a['event'] or {}).get('writer', '').endswith(chr(0xd800)), a.get('nonce', '').startswith(chr(0xdfff))) for a in d['projects']['$PID']['audit'] if a['kind'] == 'rejected' and a['machine'] == 'beta' and a['event'] and a['event']['seq'] in (10, 11))")" \
  '[["bad-code", 11, false, true], ["bad-shape", 10, true, false]]' \
  "a writer and a nonce carrying a lone surrogate are reported up as they came"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(sorted((w.endswith(chr(0xd800)), ss) for w, ss in d["spent"].items() if w.startswith(sys.argv[2])))' "$BLOG/../uplink.json" "hub/$MEMBER")" \
  "[(False, [2, 3, 4, 5, 6, 9, 11]), (True, [10])]" "and their positions spent, kept in beta's uplink.json as they came"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("unreported"))' "$BLOG/../uplink.json")" "[]" "every report delivered"
# The positions refused are spent: a new stream does not ask for them again, nor report them twice.
A_GEN="$(ctl gen alpha)"
B_GEN="$(ctl gen beta)"
ctl drop >/dev/null
until_true 200 gen_above alpha "$A_GEN" || true
until_true 200 gen_above beta "$B_GEN" || true
as a alpha
(cd "$RA" && says 1 "alpha after the forgeries")
SKIP="betaold/,hub/,alpha/$F"
settle "after the forgeries, every machine writer"
assert_equals "$(rejections)" 18 "reconnected, neither machine reports a refused event again"
last_of() { python3 -c 'import json, sys; print(json.loads(open(sys.argv[1]).read().splitlines()[-1])["seq"])' "$1"; }
assert_equals "$(last_of "$ALOG/hub.$MEMBER.jsonl") $(last_of "$BLOG/hub.$MEMBER.jsonl")" "8 8" \
  "hub/$MEMBER's last seq is 8 on both machines, as on the hub"
assert_equals "$(wc -l < "$BLOG/hub.$MEMBER.jsonl" | tr -d ' ')" 3 "holding the three authentic events of its eight"

# ---- stopping
kill "$A_DAEMON" "$B_DAEMON"
set +e; wait "$A_DAEMON" "$B_DAEMON"; set -e
for side in a b; do
  assert_not_contains "$(cat "$T/$side/s/daemon.log")" "Traceback" "nothing in $side's daemon.log is a traceback"
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES sync assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) sync assertions FAILED"
  exit 1
fi
