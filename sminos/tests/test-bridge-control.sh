#!/usr/bin/env bash
#
# The bridge's control verbs and delivery (DC2 M2, DX5): `sminos steer`,
# `interrupt`, `model`, `compact`, `read`, `command` through a session's
# endpoint, the desk's ops as the child relays them, what the child
# keeps across a module reload, and a delivery's last hop — for the owner's
# event the bridge, keyed by the log event, then the engine supervisor's
# `reply` for a --bg job with no bridge; for a peer's, and else, the inbox
# frame in the engine's peer envelope. A stand-in for the mod
# (fakemod) spawns the child and answers its command lines as the mod would;
# a stand-in inbox socket and a stand-in supervisor control socket record what
# reaches them. Hermetic: HOME and SMINOS_HOME are temporary (SMINOS_HOME
# short, for the socket's path), so the supervisor socket sminos computes is
# that temporary config's, never a real one. run-sminos-tests.sh runs this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smc.XXXXXX)"
PIDS=()
SUPDIR=""
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-0000000000c1" >/dev/null 2>&1 || break; sleep 0.05; done
  [ -n "$SUPDIR" ] && rm -rf "$SUPDIR"
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
field_of() { # json-text dotted.path
  python3 -c 'import json, sys
v = json.loads(sys.argv[1])
for k in sys.argv[2].split("."):
    v = v[int(k)] if isinstance(v, list) else v.get(k)
print(v if isinstance(v, str) else json.dumps(v))' "$1" "$2"
}
last_op() { # lines-file op → the last command line of that op
  python3 -c 'import json, sys
hits = [l for l in open(sys.argv[1]) if json.loads(l).get("op") == sys.argv[2]]
print(hits[-1].strip() if hits else "")' "$1" "$2"
}
event_of() { # events-file type phase id → the first such event, or {}
  python3 -c 'import json, sys
for line in open(sys.argv[1]):
    try:
        e = json.loads(line)
    except ValueError:
        continue
    if isinstance(e, dict) and (e.get("type"), e.get("phase"), e.get("id")) == tuple(sys.argv[2:5]):
        print(json.dumps(e))
        break
else:
    print("{}")' "$@"
}
has_event() { [ "$(event_of "$@")" != "{}" ]; }
count_event() { # events-file type phase id → how many
  python3 -c 'import json, sys
n = 0
for line in open(sys.argv[1]):
    try:
        e = json.loads(line)
    except ValueError:
        continue
    n += isinstance(e, dict) and (e.get("type"), e.get("phase"), e.get("id")) == tuple(sys.argv[2:5])
print(n)' "$@"
}
kept_rpc() { python3 -c 'import json, sys; print(json.dumps(json.load(open(sys.argv[1]))["rpcs"].get(sys.argv[2])))' "$KEPT" "$1"; }
count_op() { python3 -c 'import json, sys; print(sum(1 for l in open(sys.argv[1]) if json.loads(l).get("op") == sys.argv[2]))' "$1" "$2"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME MAWS_LANE CLAUDE_CONFIG_DIR
export HOME="$T/home"
export SMINOS_HOME="$T/s"
export DAEMON_HOST=testhost
mkdir -p "$HOME/.claude/sessions"
mkdir -m 700 "$SMINOS_HOME"
SID=5b000001-0000-4000-8000-0000000000c1
SOCK="$SMINOS_HOME/bridge/$SID.sock"
KEPT="$SMINOS_HOME/bridge/$SID.json"

cat > "$T/ctl.py" <<'PY'
import hashlib, http.client, json, os, socket, socketserver, subprocess, sys, threading, time

class Conn(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("bridge", timeout=10)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.path)

# The nonce each child named in its hello, kept by the stand-in that read it:
# a post of the mod's events carries it, as the mod's do (DX5's fence).
NONCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nonces")

def keep_nonce(hello):
    os.makedirs(NONCES, exist_ok=True)
    path = os.path.join(NONCES, os.path.basename(hello["socket"]))
    with open(path + ".tmp", "w") as f:
        f.write(hello["nonce"])
    os.replace(path + ".tmp", path)

def nonce_of(sock):
    try:
        with open(os.path.join(NONCES, os.path.basename(sock))) as f:
            return f.read()
    except OSError:
        return None

def request(path, method, url, body=None, nonce=None):
    headers = {"content-type": "application/json"}
    if method == "POST" and url == "/events":
        nonce = nonce if nonce is not None else nonce_of(path)
        if nonce:
            headers["X-Bridge-Nonce"] = nonce
    c = Conn(path)
    c.request(method, url, body=body, headers=headers)
    r = c.getresponse()
    return r.status, r.read().decode()

def post(sock, events):
    request(sock, "POST", "/events", json.dumps(events))

def serve_lines(path, out, answer):
    """A Unix socket that appends what each connection sent to `out` and
    answers it with answer(line) (None: no answer)."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    class H(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline()
            if not line.strip():   # a liveness probe: connected, sent nothing
                return
            with open(out, "a") as f:
                f.write(line.decode().rstrip("\n") + "\n")
            reply = answer(line)
            if reply is not None:
                self.wfile.write((json.dumps(reply) + "\n").encode())
    srv = socketserver.UnixStreamServer(path, H)
    srv.serve_forever()

op = sys.argv[1]
if op == "post":            # sock events-json
    print(request(sys.argv[2], "POST", "/events", sys.argv[3])[0])
elif op == "get":           # sock url
    status, text = request(sys.argv[2], "GET", sys.argv[3])
    print(status, text)
elif op == "postto":        # sock url body
    status, text = request(sys.argv[2], "POST", sys.argv[3], sys.argv[4])
    print(status, text)
elif op == "command":       # sock body-json → the child's answer to a command, as the daemon posts one
    status, text = request(sys.argv[2], "POST", "/command?wait=5000", sys.argv[3])
    print(status, text)
elif op == "inbox":         # path out — a session's inbox socket
    serve_lines(sys.argv[2], sys.argv[3], lambda line: None)
elif op == "supervisor":    # path out mode — the engine supervisor's control.sock: `reply` answered ok, or refused
    mode = sys.argv[4]
    def answer(line):
        req = json.loads(line)
        if mode == "refuse":
            return {"ok": False, "code": "ENOREPLY", "error": "job isn't accepting replies"}
        return {"ok": True, "op": req.get("op")}
    serve_lines(sys.argv[2], sys.argv[3], answer)
elif op == "supsock":       # home → where sminos looks for that config's supervisor
    cfg = os.path.abspath(os.path.join(sys.argv[2], ".claude"))
    print(os.path.join("/tmp", "cc-daemon-%d" % os.getuid(), hashlib.sha256(cfg.encode()).hexdigest()[:8], "control.sock"))
elif op == "fakemod":       # sminos session lines-file mode-file
    # Spawns the child as the mod does, and answers its command lines as the
    # mod would; mode-file says whether a turn is running ("busy"), the
    # session is idle ("idle"), or deliveries are refused ("refuse").
    sminos, session, out, modefile = sys.argv[2:6]
    CAPS = {"sminos": "1.7.0", "protocol": 2, "engine": "2.1.307", "ops": ["ping", "read", "command"],
            "reads": ["status"], "routes": {"measured": "2.1.307"}}
    # The child's stderr is the mod's debug log: kept beside the lines.
    # A module that holds the process's lane verdict tells each later child it (FAKEMOD_LANE).
    lane = ["--lane", os.environ["FAKEMOD_LANE"]] if os.environ.get("FAKEMOD_LANE") else []
    child = subprocess.Popen([sminos, "bridge", "--session", session] + lane, stdout=subprocess.PIPE,
                             stderr=open(out + ".err", "a"), text=True)
    sock = None
    delivered = {}
    with open(out, "a") as f:
        for line in child.stdout:
            f.write(line)
            f.flush()
            msg = json.loads(line)
            if msg.get("op") == "hello":
                sock = msg["socket"]
                keep_nonce(msg)
                delivered = dict((msg.get("kept") or {}).get("delivered") or {})
                post(sock, [{"type": "resync", "turns": [], "streaming": [], "agents": [], "capabilities": CAPS}])
                continue
            if msg.get("op") == "lane":   # the child's lane verdict, resolved after its hello (kept in the lines)
                continue
            mode = open(modefile).read().strip() if os.path.exists(modefile) else "busy"
            cid, o = msg["id"], msg["op"]
            events, result = [], None
            if mode == "observer" and o not in ("ping", "read"):
                # As an observer's bridge answers (a MAWS lane B session, O12 M3).
                result = {"ok": False, "error": "MAWS controls this session", "code": "lane-b"}
            elif mode == "unknown" and o in ("steer", "interrupt", "compact"):
                result = {"ok": False, "error": "turn state unknown since the bridge reloaded; retry after the next model request"}
            elif o == "steer":
                result = {"ok": False, "error": "no turn is running to steer: send it instead"} if mode == "idle" \
                    else {"ok": True, "result": {"row": "row-uuid-1"}}
            elif o == "interrupt":
                result = {"ok": True, "result": {"turnId": None, "stopped": [], "running": []}} if mode == "idle" \
                    else {"ok": True, "result": {"turnId": "t1", "stopped": ["b5y6zo7fe"], "running": ["stuck01"]}} \
                    if mode == "stuck" else {"ok": True, "result": {"turnId": "t1", "stopped": ["b5y6zo7fe"], "running": []}}
            elif o == "stop":
                result = {"ok": False, "error": "Task %s is not running (status: completed)" % msg.get("taskId")} \
                    if msg.get("taskId") == "bdone001" else {"ok": True, "result": {"taskId": msg.get("taskId")}}
            elif o == "model":
                pick = {"model": msg.get("model"), "effort": msg.get("effort")}
                events.append({"type": "model", **pick})
                result = {"ok": True, "result": pick}
            elif o == "compact":
                if mode == "idle":
                    result = {"ok": True, "result": {"started": True}}
                    later = [{"type": "compact", "phase": "start", "id": cid},
                             {"type": "compact", "phase": "end", "id": cid, "tokensBefore": 900, "tokensAfter": 100}]
                    threading.Timer(0.3, post, (sock, later)).start()
                else:
                    result = {"ok": True, "result": {"queued": True, "turnId": "t1"}}
            elif o == "deliver":
                key = msg["key"]
                # The mod's mark: per project, the bare writer for a key naming none.
                mark = "%s/%s" % (key["project"], key["writer"]) if "project" in key else key["writer"]
                if mode == "refuse":
                    result = {"ok": False, "error": "deliver needs key {project?, writer, seq} and text"}
                elif key["seq"] <= delivered.get(mark, 0):
                    events.append({"type": "delivered", "key": key, "outcome": "duplicate"})
                    result = {"ok": True, "result": {"duplicate": True}}
                else:
                    delivered[mark] = key["seq"]
                    events.append({"type": "delivered", "key": key, "outcome": "submitted"})
                    result = {"ok": True, "result": {"submitted": True}}
            elif o == "read":
                result = {"ok": True, "result": {"version": {"version": "2.1.307"}, "cwd": "/w"}} \
                    if msg.get("what") == "status" else {"ok": False, "error": "no read %s" % msg.get("what")}
            elif o == "btw":
                # As the bridge answers a side question: started at once, its
                # start and end following on the stream, the end's answer long.
                result = {"ok": True, "result": {"started": True, "id": cid}}
                later = [{"type": "btw", "phase": "start", "id": cid},
                         {"type": "btw", "phase": "end", "id": cid, "text": "\uac00" * 5000,
                          "usage": {"input": 12, "output": 34, "cacheRead": 5000, "cacheWrite": 7}}]
                threading.Timer(0.3, post, (sock, later)).start()
            elif o == "media":
                # As the bridge answers a desk upload: queued once held, its
                # attachment's states following on the stream, the upload
                # the RPC's nonce.
                up = msg.get("upload")
                result = {"ok": True, "result": {"queued": True, "upload": up}}
                said = lambda st, ph: {"type": "media", "id": up, "upload": up, "index": 0, "state": st, "phase": ph,
                                       "toolUseId": "toolu_sminos_1", "attachments": [{"index": 0, "state": st, "toolUseId": "toolu_sminos_1"}]}
                threading.Timer(0.3, post, (sock, [said("read", "start"), said("forwarded", "end")])).start()
            elif o == "command":
                # As the bridge answers a desk command: at once, the run's
                # start and end following on the stream (none for a panel).
                name, args = msg.get("name"), msg.get("args") or ""
                if name == "config":
                    result = {"ok": False, "error": "opens a panel in the terminal; it would hold the session's queue",
                              "code": "panel"}
                else:
                    result = {"ok": True, "result": {"queued": True, "route": "run", "id": cid}}
                    run = {"type": "run", "id": cid, "name": name, "args": args}
                    later = [{**run, "phase": "start"},
                             {**run, "phase": "end", "settled": {"ok": True},
                              "readback": {"how": "row", "text": "Session renamed to: %s" % args, "uuid": "row-r1"}}]
                    if name == "reload-plugins":
                        text = "Reloaded: 10 plugins · 23 skills · 17 agents · 13 hooks"
                        later[-1] = {**run, "phase": "end", "settled": {"ok": True, "text": text},
                                     "readback": {"how": "text", "text": text}}
                    threading.Timer(0.3, post, (sock, later)).start()
            else:
                result = {"ok": False, "error": "unknown op: %s" % o}
            post(sock, events + [{"type": "result", "id": cid, "op": o, **result}])
    child.wait()
PY
ctl() { python3 "$T/ctl.py" "$@"; }
answers() { ctl get "$1" /status 2>/dev/null | grep -q '"ready": true'; }
fakemod() { # session lines-file → starts the stand-in, which starts the child
  python3 "$T/ctl.py" fakemod "$SMINOS" "$1" "$2" "$T/mode" &
  FAKEMOD=$!
  PIDS+=("$FAKEMOD")
}
snapshot() { python3 -c 'import http.client, socket, sys
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.connect(sys.argv[1])
c = C("bridge"); c.request("GET", "/events"); print(c.getresponse().readline().decode().strip())' "$1"; }
mode() { printf '%s\n' "$1" > "$T/mode"; }

echo "what the child keeps:"
mode busy
fakemod "$SID" "$T/lines-a"
until_true 100 answers "$SOCK" || true
assert_equals "$(field_of "$(sed -n 1p "$T/lines-a")" kept)" '{"override": null, "delivered": {}}' "a first child's hello says it keeps nothing yet"
ctl post "$SOCK" '[{"type":"model","model":"sonnet","effort":"high"},
 {"type":"delivered","key":{"writer":"testhost/human","seq":3},"outcome":"submitted"},
 {"type":"delivered","key":{"writer":"testhost/human","seq":2},"outcome":"duplicate"}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": {"model": "sonnet", "effort": "high"}, "delivered": {"testhost/human": 3}}' \
  "the model chosen and the highest key delivered per writer are kept in <session>.json"
assert_equals "$(python3 -c 'import os, sys; print("%04o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$KEPT")" "0600" "owner-only"
assert_equals "$(field_of "$(snapshot "$SOCK")" override)" '{"model": "sonnet", "effort": "high"}' "the snapshot carries the session's model choice"
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"override":null,"delivered":{"testhost/human":3,"other/x":1}}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": null, "delivered": {"testhost/human": 3, "other/x": 1}}' "a resync replaces what is kept with the mod's own"
ctl post "$SOCK" '[{"type":"model","model":"opus","effort":null}]' >/dev/null

# A module reload kills the child with a signal while the session goes on:
# what was kept stays, and the next child's hello hands it back.
CHILD="$(ctl get "$SOCK" /status | python3 -c 'import json, sys; print(json.loads(sys.stdin.read().split(" ", 1)[1])["pid"])')"
kill -TERM "$CHILD"
until_true 100 test ! -e "$SOCK" || true
assert_equals "$([ -e "$KEPT" ] && echo kept || echo gone)" "kept" "a child stopped by a signal (a reload) leaves what it kept"
fakemod "$SID" "$T/lines-b"
until_true 100 answers "$SOCK" || true
assert_equals "$(field_of "$(sed -n 1p "$T/lines-b")" kept)" '{"override": {"model": "opus", "effort": null}, "delivered": {"testhost/human": 3, "other/x": 1}}' \
  "and the next child's hello carries it back to the mod"
# The first fakemod's parent role ended with its child; stop it.
kill "${PIDS[0]}" 2>/dev/null || true

# A write that fails is said on the stream, and not taken as kept: the next
# change writes the whole of what the mod handed over, the failed part included.
WATCHK="$T/wk"
"$SMINOS" watch "$SID" --json > "$WATCHK" 2>&1 &
PIDS+=("$!")
until_true 100 test -s "$WATCHK" || true
chmod 500 "$SMINOS_HOME/bridge"
ctl post "$SOCK" '[{"type":"model","model":"claude-fable-5","effort":"max"}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
until_true 100 grep -q '"type": "kept"' "$WATCHK" || true
KEPTEV="$(grep -m1 '"type": "kept"' "$WATCHK" || echo '{}')"
assert_equals "$(field_of "$KEPTEV" ok)" "false" "a write the child could not make is said on the stream as a kept event"
assert_contains "$(field_of "$KEPTEV" error)" "ermission denied" "with the reason"
assert_not_contains "$(cat "$KEPT")" "claude-fable-5" "and the file still holds what it held"
ctl post "$SOCK" '[{"type":"model","model":"claude-fable-5","effort":"max"}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"model": "claude-fable-5"' "the same choice sent again is written: a failed write was not taken as kept"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"testhost/human","seq":9},"outcome":"submitted"}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": {"model": "claude-fable-5", "effort": "max"}, "delivered": {"testhost/human": 9, "other/x": 1}}' \
  "the next change writes the model choice that failed to land as well"
# A delivery key whose write failed is written by the next event, though that
# event (a duplicate of it, a heartbeat) moves no key.
chmod 500 "$SMINOS_HOME/bridge"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":1},"outcome":"submitted"}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
assert_not_contains "$(cat "$KEPT")" "mac/human" "a delivery key whose write failed is not in the file"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":1},"outcome":"duplicate"}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"mac/human": 1' "the next event, a duplicate moving no key, writes it"
# $WATCHK fills asynchronously: the baseline below is taken only once the
# recovery just above has reached it. A recovery follows the failure it
# recovers from, so both are in then; the stream holds two recoveries by now
# (the model choice's and this key's).
kept_oks() { grep -c '"type": "kept", "ok": true' "$WATCHK" || true; }
kept_oks_reach() { [ "$(kept_oks)" -ge "$1" ]; }
until_true 100 kept_oks_reach 2 || true
assert_equals "$(kept_oks)" "2" "the stream has said the earlier recoveries before the failures are counted"
chmod 500 "$SMINOS_HOME/bridge"
FAILS="$(grep -c '"type": "kept", "ok": false' "$WATCHK" || true)"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":2},"outcome":"submitted"}]' >/dev/null
ctl post "$SOCK" '[{"type":"heartbeat","state":{}}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
until_true 100 bash -c '[ "$(grep -c "\"type\": \"kept\", \"ok\": false" "$1")" -gt "$2" ]' _ "$WATCHK" "$FAILS" || true
assert_equals "$(( $(grep -c '"type": "kept", "ok": false' "$WATCHK") - FAILS ))" "1" \
  "a failure that persists over several events is said once"
ctl post "$SOCK" '[{"type":"heartbeat","state":{}}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"mac/human": 2' "and a heartbeat writes it once the write can be made"
until_true 100 kept_oks_reach 3 || true
assert_equals "$(kept_oks)" "3" "the recovery is said on the stream too, once"
ctl post "$SOCK" '[{"type":"model","model":"opus","effort":null},
 {"type":"resync","turns":[],"streaming":[],"agents":[],"override":{"model":"opus","effort":null},"delivered":{"testhost/human":3,"other/x":1}}]' >/dev/null

echo "the control verbs, bridged:"
mode busy
run "$SMINOS" steer "$SID" "also print the date"
assert_rc 0 "$RC" "steer exits 0"
assert_contains "$OUT" "row-uuid-1" "naming the row it appended"
assert_equals "$(field_of "$(last_op "$T/lines-b" steer)" text)" "also print the date" "the text reached the mod as a steer"
mode idle
run "$SMINOS" steer "$SID" "anyone?"
assert_rc 1 "$RC" "a steer the session refuses (idle) exits 1"
assert_contains "$OUT" "no turn is running" "with the session's reason"
mode busy
run "$SMINOS" interrupt "$SID"
assert_rc 0 "$RC" "interrupt exits 0"
assert_contains "$OUT" "b5y6zo7fe" "naming the background task it stopped"
mode stuck
run "$SMINOS" interrupt "$SID"
assert_rc 1 "$RC" "an interrupt that left a background task running exits 1"
assert_contains "$OUT" "stuck01" "naming the task still running"
assert_contains "$OUT" "still running" "and saying so"
mode idle
run "$SMINOS" interrupt "$SID"
assert_contains "$OUT" "nothing to interrupt" "an idle session has nothing to interrupt, said so"
run "$SMINOS" stop "$SID" bsrv0001
assert_rc 0 "$RC" "stop exits 0"
assert_contains "$OUT" "bsrv0001" "naming the task it stopped"
assert_equals "$(field_of "$(last_op "$T/lines-b" stop)" taskId)" "bsrv0001" "the task reached the mod as a stop"
run "$SMINOS" stop "$SID" bdone001
assert_rc 1 "$RC" "a stop the engine refuses exits 1"
assert_contains "$OUT" "is not running (status: completed)" "in the engine's words"
# After a module reload, until the mod knows whether a turn runs, the verbs
# that need it are refused with the reason: never a false idle.
mode unknown
for VERB in "interrupt" "steer|and the date" "compact"; do
  IFS='|' read -r V ARG <<<"$VERB"
  if [ -n "$ARG" ]; then run "$SMINOS" "$V" "$SID" "$ARG"; else run "$SMINOS" "$V" "$SID"; fi
  assert_rc 1 "$RC" "$V while the turn state is unknown exits 1"
  assert_contains "$OUT" "turn state unknown since the bridge reloaded; retry after the next model request" "saying why ($V)"
done
mode idle
run "$SMINOS" model "$SID" sonnet --effort high
assert_rc 0 "$RC" "model exits 0"
assert_contains "$OUT" "sonnet" "saying the model in force"
L="$(last_op "$T/lines-b" model)"
assert_equals "$(field_of "$L" model)/$(field_of "$L" effort)" "sonnet/high" "the model and effort reached the mod"
run "$SMINOS" model "$SID" default
L="$(last_op "$T/lines-b" model)"
assert_equals "$(field_of "$L" model)/$(field_of "$L" effort)" "null/null" "default clears the choice"
run "$SMINOS" model "$SID" sonnet --effort turbo
assert_rc 2 "$RC" "an effort that is none is a usage error"
mode busy
run "$SMINOS" compact "$SID"
assert_rc 0 "$RC" "compact during a turn exits 0"
assert_contains "$OUT" "when the running turn ends" "saying it is queued for the turn's end"
mode idle
run "$SMINOS" compact "$SID" "keep the plan"
assert_rc 0 "$RC" "compact on an idle session exits 0"
assert_contains "$OUT" "900 → 100" "once it has run, with the counts"
assert_equals "$(field_of "$(last_op "$T/lines-b" compact)" instructions)" "keep the plan" "its instructions reached the mod"

echo "the desk's ops, bridged:"
# The mod's resync carries what it can do; the child answers it as its own.
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"override":{"model":"opus","effort":null},
 "delivered":{"testhost/human":3,"other/x":1},
 "capabilities":{"sminos":"1.7.0","protocol":2,"engine":"2.1.307","ops":["ping","read","command"],"reads":["status"],
                 "routes":{"measured":"2.1.307"}}}]' >/dev/null
STATUS="$(ctl get "$SOCK" /status)"
assert_equals "$(field_of "${STATUS#* }" capabilities.engine)" "2.1.307" "the child's status carries the capabilities the mod's resync posted"
assert_equals "$(field_of "$(snapshot "$SOCK")" capabilities.routes.measured)" "2.1.307" "and so does its snapshot"
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"override":{"model":"opus","effort":null},
 "delivered":{"testhost/human":3,"other/x":1}}]' >/dev/null
STATUS="$(ctl get "$SOCK" /status)"
assert_equals "$(field_of "${STATUS#* }" capabilities)" "null" "a resync without them (a mod from before) leaves none: the resync is the mod's whole state"
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"override":{"model":"opus","effort":null},
 "delivered":{"testhost/human":3,"other/x":1},
 "capabilities":{"sminos":"1.7.0","protocol":2,"engine":"2.1.307","ops":["ping","read","command"],"reads":["status"],
                 "routes":{"measured":"2.1.307"}}}]' >/dev/null
run "$SMINOS" read "$SID" status
assert_rc 0 "$RC" "read status exits 0"
assert_equals "$(field_of "$OUT" version.version)" "2.1.307" "printing the mod's answer as JSON"
assert_equals "$(field_of "$(last_op "$T/lines-b" read)" what)" "status" "the read reached the mod"
run "$SMINOS" read "$SID" usage --breakdown full
assert_rc 1 "$RC" "a read the mod does not serve exits 1"
assert_contains "$OUT" "no read usage" "in the mod's words"
assert_equals "$(field_of "$(last_op "$T/lines-b" read)" args.breakdown)" "full" "a read's args reach the mod (--breakdown)"
WATCHD="$T/wd"
"$SMINOS" watch "$SID" --json > "$WATCHD" 2>&1 &
PIDS+=("$!")
until_true 100 test -s "$WATCHD" || true
run "$SMINOS" command "$SID" rename desk-m0
assert_rc 0 "$RC" "command exits 0"
assert_contains "$OUT" "queued (run)" "saying the bridge queued it, and its route"
assert_contains "$OUT" "Session renamed to: desk-m0" "then the line read back once it ran"
assert_contains "$OUT" "by its row" "and how it was confirmed"
L="$(last_op "$T/lines-b" command)"
assert_equals "$(field_of "$L" name)/$(field_of "$L" args)" "rename/desk-m0" "the name and arguments reached the mod"
run "$SMINOS" command "$SID" config
assert_rc 1 "$RC" "a command the bridge refuses exits 1"
assert_contains "$OUT" "(panel)" "naming the refusal's code"
assert_contains "$OUT" "hold the session's queue" "and its reason"
# A desk RPC's command: its nonce is kept past the queued answer, on every
# run event of that command, until its end; the end is kept beside the answer.
OUTC="$(ctl command "$SOCK" '{"op":"command","name":"rename","args":"desk-m1","rpc":"nonce-q1"}')"
CID="$(field_of "${OUTC#* }" id)"
assert_equals "$(field_of "${OUTC#* }" result.queued)" "true" "the child answers a queued command at once"
until_true 100 has_event "$WATCHD" run end "$CID" || true
assert_equals "$(field_of "$(event_of "$WATCHD" run start "$CID")" rpc)" "nonce-q1" "its run's start, relayed, carries the RPC's nonce"
assert_equals "$(field_of "$(event_of "$WATCHD" run end "$CID")" rpc)" "nonce-q1" "and so does its end"
KR="$(kept_rpc nonce-q1)"
assert_equals "$(field_of "$KR" ok)/$(field_of "$KR" result.queued)/$(field_of "$KR" end.readback.how)" "true/true/row" \
  "the answer kept under the nonce, and the end beside it once it came"
# The mod posts an end again when it cannot tell the child took it (a lost
# post, a child replaced): the child relays an op's end once, and keeps the
# first beside the answer.
ctl post "$SOCK" "[{\"type\":\"run\",\"phase\":\"end\",\"id\":\"$CID\",\"name\":\"rename\",\"args\":\"desk-m1\",
 \"settled\":{\"ok\":true},\"readback\":{\"how\":\"none\"}},{\"type\":\"run\",\"phase\":\"start\",\"id\":\"after-$CID\",\"name\":\"color\",\"args\":\"red\"}]" >/dev/null
until_true 100 has_event "$WATCHD" run start "after-$CID" || true
assert_equals "$(count_event "$WATCHD" run end "$CID")" "1" "an op's end posted again is relayed once"
assert_equals "$(field_of "$(kept_rpc nonce-q1)" end.readback.how)" "row" "and the end kept is the first"
OUTR="$(ctl command "$SOCK" '{"op":"command","name":"config","rpc":"nonce-r1"}')"
assert_equals "$(field_of "${OUTR#* }" code)" "panel" "a refusal's code is in the child's answer"
assert_equals "$(field_of "$(kept_rpc nonce-r1)" code)" "panel" "and in the answer kept under the nonce"
# A desk RPC's side question: its nonce is kept past the started answer, on
# its start and its end, and let go at the end; the end is kept beside the
# answer, its text cut to what a kept end holds and said to be cut.
OUTB="$(ctl command "$SOCK" '{"op":"btw","prompt":"what now?","rpc":"nonce-b1"}')"
BID="$(field_of "${OUTB#* }" id)"
assert_equals "$(field_of "${OUTB#* }" result.started)" "true" "the child answers a side question started, at once"
until_true 100 has_event "$WATCHD" btw end "$BID" || true
assert_equals "$(field_of "$(event_of "$WATCHD" btw start "$BID")" rpc)" "nonce-b1" "its start, relayed, carries the RPC's nonce"
assert_equals "$(field_of "$(event_of "$WATCHD" btw end "$BID")" rpc)" "nonce-b1" "and so does its end"
KB="$(kept_rpc nonce-b1)"
assert_equals "$(field_of "$KB" result.started)/$(field_of "$KB" end.usage.output)/$(field_of "$KB" end.truncated)" "true/34/true" \
  "the answer kept under the nonce, and the end beside it, its text cut and said to be"
assert_equals "$(python3 -c 'import json, sys; print(len(json.loads(sys.argv[1])["end"]["text"]))' "$KB")" "4096" "to the kept end's bound"
ctl post "$SOCK" "[{\"type\":\"btw\",\"phase\":\"end\",\"id\":\"$BID\",\"reason\":\"aborted\"},{\"type\":\"btw\",\"phase\":\"start\",\"id\":\"after-$BID\"}]" >/dev/null
until_true 100 has_event "$WATCHD" btw start "after-$BID" || true
assert_equals "$(count_event "$WATCHD" btw end "$BID")" "1" "a side question's end posted again is relayed once"
assert_equals "$(field_of "$(kept_rpc nonce-b1)" end.usage.output)" "34" "and the end kept is the first"
# A desk upload: the answer is kept under the RPC's nonce, which is the
# upload; each `media` event is relayed carrying it as `rpc`, once by its
# (upload, index, state); the upload's end is kept beside the answer.
OUTM="$(ctl command "$SOCK" '{"op":"media","upload":"up-m1","root":"/w/.claude/desk-uploads/s","files":[],"rpc":"up-m1"}')"
assert_equals "$(field_of "${OUTM#* }" result.queued)/$(field_of "${OUTM#* }" result.upload)" "true/up-m1" "the child answers an upload queued, at once"
until_true 100 has_event "$WATCHD" media end up-m1 || true
assert_equals "$(field_of "$(event_of "$WATCHD" media start up-m1)" rpc)/$(field_of "$(event_of "$WATCHD" media start up-m1)" state)" "up-m1/read" \
  "an attachment's read, relayed, carries the upload as the RPC's nonce"
assert_equals "$(field_of "$(event_of "$WATCHD" media end up-m1)" rpc)/$(field_of "$(event_of "$WATCHD" media end up-m1)" index)" "up-m1/0" \
  "and so does the upload's end, its index the attachment's"
KM="$(kept_rpc up-m1)"
assert_equals "$(field_of "$KM" op)/$(field_of "$KM" result.queued)/$(field_of "$KM" end.state)/$(field_of "$KM" end.phase)" "media/true/forwarded/end" \
  "the answer kept under the nonce, and the upload's end beside it"
ctl post "$SOCK" '[{"type":"media","id":"up-m1","upload":"up-m1","index":0,"state":"read","phase":"start"},
 {"type":"media","id":"up-m1","upload":"up-m1","index":0,"state":"forwarded","phase":"end"},
 {"type":"media","id":"up-m2","upload":"up-m2","index":0,"state":"failed","phase":"end"}]' >/dev/null
until_true 100 has_event "$WATCHD" media end up-m2 || true
assert_equals "$(count_event "$WATCHD" media start up-m1)/$(count_event "$WATCHD" media end up-m1)" "1/1" "a state posted again is relayed once"
assert_equals "$(field_of "$(event_of "$WATCHD" media end up-m2)" rpc)" "up-m2" "an upload no RPC of this child's carried still names its nonce"
# A reload's start names the child that relays it, the one the reload replaces:
# the daemon finishes the op by another answering (from the CLI too, no nonce).
ctl post "$SOCK" '[{"type":"run","phase":"start","id":"rl-1","name":"reload-plugins","args":""}]' >/dev/null
until_true 100 has_event "$WATCHD" run start rl-1 || true
STATUS="$(ctl get "$SOCK" /status)"
WANT="[$(python3 -c 'import os, sys; print(os.stat(sys.argv[1]).st_ino)' "$SOCK"), $(field_of "${STATUS#* }" pid)]"
assert_equals "$(field_of "$(event_of "$WATCHD" run start rl-1)" child)" "$WANT" "a reload's start carries the relaying child: its socket's inode and its pid"
# A surviving module returns text: the same child relays and keeps its end.
OUTC="$(ctl command "$SOCK" '{"op":"command","name":"reload-plugins","rpc":"nonce-reload-text"}')"
CID="$(field_of "${OUTC#* }" id)"
until_true 100 has_event "$WATCHD" run end "$CID" || true
assert_equals "$(field_of "$(event_of "$WATCHD" run start "$CID")" child)" "$WANT" "the surviving reload uses the same child"
assert_equals "$(field_of "$(event_of "$WATCHD" run end "$CID")" rpc)" "nonce-reload-text" "the reload's text end carries its nonce"
KR="$(kept_rpc nonce-reload-text)"
assert_equals "$(field_of "$KR" end.readback.how)/$(field_of "$KR" end.settled.ok)" "text/true" "the surviving reload's text is kept for daemon recovery"
assert_contains "$(field_of "$KR" end.readback.text)" "Reloaded: 10 plugins" "the engine's line is kept verbatim"
assert_equals "$(count_event "$WATCHD" run end "$CID")" "1" "the child relayed one reload end"
ctl post "$SOCK" '[{"type":"run","phase":"start","id":"rn-1","name":"rename","args":"x"}]' >/dev/null
until_true 100 has_event "$WATCHD" run start rn-1 || true
assert_equals "$(field_of "$(event_of "$WATCHD" run start rn-1)" child)" "null" "another command's does not"

echo "the control verbs, no bridge:"
NOB=5c000002-0000-4000-8000-0000000000c2
for verb in interrupt stop model compact read command; do
  if [ "$verb" = model ]; then run "$SMINOS" model "$NOB" sonnet
  elif [ "$verb" = stop ]; then run "$SMINOS" stop "$NOB" bsrv0001
  elif [ "$verb" = read ]; then run "$SMINOS" read "$NOB" status
  elif [ "$verb" = command ]; then run "$SMINOS" command "$NOB" rename x
  else run "$SMINOS" "$verb" "$NOB"; fi
  assert_rc 4 "$RC" "$verb with no bridge exits 4"
  assert_contains "$OUT" "no bridge" "saying so"
done

echo "delivery:"
R="$T/repo"
mkdir -p "$R"
git -c init.defaultBranch=main init -q "$R"
(cd "$R" && "$SMINOS" project init --name ctldemo >/dev/null)
INBOX="$T/rover.sock"
python3 "$T/ctl.py" inbox "$INBOX" "$T/rover-inbox" &
PIDS+=("$!")
until_true 100 test -S "$INBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"rover","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$SID" "$R" "$INBOX" > "$HOME/.claude/sessions/rover.json"
mode busy
set +e; OUT="$(cd "$R" && "$SMINOS" say "@rover read the plan" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a human's say to a bridged member exits 0"
assert_contains "$OUT" "rover: sent" "reporting it sent"
L="$(last_op "$T/lines-b" deliver)"
assert_equals "$(field_of "$L" key.writer)" "testhost/human" "it went through the bridge, keyed by the event's writer"
SEQ="$(field_of "$L" key.seq)"
LOGSEQ="$(python3 -c 'import glob, json, sys
for p in glob.glob(sys.argv[1] + "/projects/*/log/testhost.human.jsonl"):
    for l in open(p):
        e = json.loads(l)
        if e.get("text") == "@rover read the plan":
            print(e["seq"])' "$SMINOS_HOME")"
assert_equals "$SEQ" "$LOGSEQ" "and its seq"
P1="$(field_of "$(cat "$R/.smns")" project)"
assert_equals "$(field_of "$L" key.project)" "$P1" "and its project's id"
# What the session kept holds the writer's bare mark, 3, from before keys
# named their project (#229): a project's own count starts under it.
assert_equals "$(( SEQ <= 3 ))" "1" "the event's seq is at or below the writer's bare mark the session kept"
assert_contains "$(cat "$KEPT")" "\"$P1/testhost/human\": $SEQ" "yet it was submitted: the child keeps the project's own mark"
assert_contains "$(cat "$KEPT")" '"testhost/human": 3' "beside the bare one, untouched"
assert_not_contains "$OUT" "already delivered" "and the sender was told of no duplicate"
# A duplicate is taken as delivered, but said, to the sender and in daemon.log.
set +e; OUT="$(PYTHONPATH="$PLUGIN_ROOT/skills/sminos/scripts" python3 -c 'import sys, sminos_control as C
print(C.deliver(sys.argv[1], sys.argv[2], {"writer": "testhost/human", "seq": int(sys.argv[3])}, "again"))' "$SID" "$P1" "$SEQ" 2>&1)"; set -e
assert_contains "$OUT" "True" "a key the bridge already submitted is taken as delivered"
assert_contains "$OUT" "the bridge of session $SID took testhost/human:$SEQ as already delivered" "and said to the sender"
assert_contains "$(cat "$SMINOS_HOME/daemon.log" 2>/dev/null)" "the bridge of session $SID took testhost/human:$SEQ as already delivered" \
  "and in daemon.log, naming the event and the session"
assert_contains "$(field_of "$L" text)" "[sminos chat ctldemo" "the text is the frame the inbox would carry"
assert_contains "$(field_of "$L" text)" "read the plan" "with the message"
assert_equals "$([ -s "$T/rover-inbox" ] && echo framed || echo none)" "none" "and nothing went to the inbox socket"
set +e; OUT="$(cd "$R" && "$SMINOS" send rover "check the tests" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "send to a bridged member exits 0"
L="$(last_op "$T/lines-b" deliver)"
assert_contains "$(field_of "$L" text)" "[sminos message from human id=" "send's own frame went through the bridge"
SENDSEQ="$(field_of "$L" key.seq)"
assert_equals "$(( SENDSEQ > SEQ ))" "1" "keyed by its own event"
# A peer's say or send to a bridged member is a peer message: never the
# bridge, but the inbox frame, in the engine's own peer envelope naming its
# sender, so the engine delivers it as another session's.
PEER_SID=5f000005-0000-4000-8000-0000000000c5
P1="$(field_of "$(cat "$R/.smns")" project)"
# The peer is a live member of the project (no inbox: it is reached as recorded).
printf '{"pid":%s,"sessionId":"%s","name":"peerone","nameSource":"user","kind":"interactive","status":"busy","cwd":"%s"}\n' \
  "$$" "$PEER_SID" "$R" > "$HOME/.claude/sessions/peerone.json"
N="$(count_op "$T/lines-b" deliver)"
set +e; OUT="$(cd "$R" && CLAUDE_CODE_SESSION_ID="$PEER_SID" "$SMINOS" say "@rover from a peer session" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a peer's say to a bridged member exits 0"
assert_contains "$OUT" "rover: sent" "reporting it sent"
assert_equals "$(count_op "$T/lines-b" deliver)" "$N" "and not through the bridge"
until_true 100 grep -q "from a peer session" "$T/rover-inbox" || true
FRAME="$(grep "from a peer session" "$T/rover-inbox" | tail -1)"
CONTENT="$(field_of "$FRAME" message.content)"
assert_equals "$(head -1 <<<"$CONTENT")" '<cross-session-message from-name="peerone">' \
  "but its inbox, in the engine's peer envelope naming the sender"
assert_contains "$(sed -n 2p <<<"$CONTENT")" "[sminos chat ctldemo 5f000005:" "around the frame the bridge would have carried"
REPLY_LINE="$(tail -2 <<<"$CONTENT" | head -1)"
assert_equals "$REPLY_LINE" "[To reply, run in Bash: $(cd "$(dirname "$SMINOS")" && pwd -P)/sminos say \"@$P1/5f000005 <your reply>\"]" \
  "its last line says how to answer the sending session: the CLI's path, the sender by project and short"
assert_equals "$(tail -1 <<<"$CONTENT")" "</cross-session-message>" "closed"
set +e; OUT="$(cd "$R" && CLAUDE_CODE_SESSION_ID="$PEER_SID" "$SMINOS" send rover "a peer's direct word" --from scout 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a peer's send to a bridged member exits 0"
assert_equals "$(count_op "$T/lines-b" deliver)" "$N" "and does not use the bridge either"
until_true 100 grep -q "direct word" "$T/rover-inbox" || true
CONTENT="$(field_of "$(grep "direct word" "$T/rover-inbox" | tail -1)" message.content)"
assert_contains "$CONTENT" $'<cross-session-message from-name="scout">\n[sminos message from scout id=' \
  "its inbox frame is named by the sender it signs as"

# The bridge refusing a delivery (it did not submit) leaves the inbox frame.
mode refuse
set +e; OUT="$(cd "$R" && "$SMINOS" say "@rover second try" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "rover: sent" "a delivery the bridge refuses still reaches the member"
until_true 100 test -s "$T/rover-inbox" || true
assert_contains "$(cat "$T/rover-inbox" 2>/dev/null)" "second try" "through its inbox socket"
assert_not_contains "$(grep "second try" "$T/rover-inbox")" "To reply" "with no reply line: the owner is answered in the session, not by say"
mode busy
# The mod's `inbox` event: the child writes the frame to the session's own
# inbox socket (the wake for a delivered row the session has not read while
# stopped), always as the bridge's own: a delivery's words go in as a row,
# never through the inbox, which the engine delivers as a peer's. A key on the
# event changes nothing.
: > "$T/rover-inbox"
ctl post "$SOCK" '[{"type":"inbox","text":"[sminos bridge]\nA message for you was added","key":{"project":"p9","writer":"testhost/human","seq":4}}]' >/dev/null
until_true 100 test -s "$T/rover-inbox" || true
FRAME="$(tail -1 "$T/rover-inbox" 2>/dev/null || true)"
[ -n "$FRAME" ] || FRAME='{}'
assert_equals "$(field_of "$FRAME" message.content)" "<cross-session-message from-name=\"sminos bridge\">
[sminos bridge]
A message for you was added
</cross-session-message>" "the child sends the mod's inbox event as a frame to the session's own socket, the bridge's own"
assert_equals "$(field_of "$FRAME" type)" "user" "as the inbox frame sminos sends"
# With no socket of the session answering, the wake goes nowhere and nothing
# is kept as a refusal: the delivery's row is in the conversation already.
mv "$HOME/.claude/sessions/rover.json" "$T/rover.json.aside"
ctl post "$SOCK" '[{"type":"inbox","text":"[sminos bridge]\nunheard","key":{"project":"p9","writer":"testhost/human","seq":5}}]' >/dev/null
until_true 100 grep -q "the wake did not go" "$T/lines-b.err" || true
assert_contains "$(cat "$T/lines-b.err" 2>/dev/null)" "no inbox socket of the session answers: the wake did not go" \
  "a wake no socket took is said in the mod's debug log"
assert_not_contains "$(cat "$KEPT")" '"p9"' "and kept as no refusal"
mv "$T/rover.json.aside" "$HOME/.claude/sessions/rover.json"
# One writer delivering to one session from two projects (#229): every
# project numbers the writer's events on its own, so the second project's
# event is below what the first delivered, and arrives all the same.
R2="$T/repo2"
mkdir -p "$R2"
git -c init.defaultBranch=main init -q "$R2"
(cd "$R2" && "$SMINOS" project init --name ctlsecond >/dev/null)
P2="$(field_of "$(cat "$R2/.smns")" project)"
printf '{"pid":%s,"sessionId":"%s","name":"rover","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$SID" "$R2" "$INBOX" > "$HOME/.claude/sessions/rover.json"
: > "$T/rover-inbox"
set +e; OUT="$(cd "$R2" && "$SMINOS" say "@rover from the second project" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a say to the same member from a second project exits 0"
L="$(last_op "$T/lines-b" deliver)"
assert_contains "$(field_of "$L" text)" "from the second project" "it went through the bridge"
assert_equals "$(field_of "$L" key.project)" "$P2" "keyed by the second project"
assert_equals "$(( $(field_of "$L" key.seq) < SENDSEQ ))" "1" "its seq below what the first project delivered from the writer"
assert_equals "$(field_of "$(cat "$KEPT")" "delivered.$P2/testhost/human")" "$(field_of "$L" key.seq)" \
  "and it was submitted: the child keeps the second project's mark"
assert_not_contains "$OUT" "already delivered" "with no duplicate said"
assert_equals "$([ -s "$T/rover-inbox" ] && echo framed || echo none)" "none" "and nothing went to the inbox socket"
printf '{"pid":%s,"sessionId":"%s","name":"rover","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$SID" "$R" "$INBOX" > "$HOME/.claude/sessions/rover.json"
# A peer of the second project speaking into the first: its frame's reply line
# names the peer in its own project, and runs as written from the recipient's.
printf '{"pid":%s,"sessionId":"%s","name":"peerone","nameSource":"user","kind":"interactive","status":"busy","cwd":"%s"}\n' \
  "$$" "$PEER_SID" "$R2" > "$HOME/.claude/sessions/peerone.json"
set +e; OUT="$(cd "$R2" && CLAUDE_CODE_SESSION_ID="$PEER_SID" "$SMINOS" say "@ctldemo/rover across projects" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a peer's say into another project exits 0"
until_true 100 grep -q "across projects" "$T/rover-inbox" || true
CONTENT="$(field_of "$(grep "across projects" "$T/rover-inbox" | tail -1)" message.content)"
REPLY_LINE="$(tail -2 <<<"$CONTENT" | head -1)"
assert_contains "$REPLY_LINE" "say \"@$P2/5f000005 <your reply>\"]" "its reply line names the sender's own project"
REPLY_CMD="${REPLY_LINE#\[To reply, run in Bash: }"
REPLY_CMD="${REPLY_CMD%\]}"
REPLY_CMD="${REPLY_CMD/<your reply>/the answer}"
set +e; OUT="$(cd "$R" && CLAUDE_CODE_SESSION_ID="$SID" bash -c "$REPLY_CMD" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "the reply line runs as written from the recipient's project"
assert_contains "$OUT" "in ctlsecond" "recorded in the sender's project"
assert_contains "$OUT" "peerone: recorded" "addressed to the sender"
rm -f "$HOME/.claude/sessions/peerone.json"

# A --bg job with no bridge: a human's event goes through the engine
# supervisor's control socket (`reply`, human-origin), else the inbox frame.
BG=5d000003-0000-4000-8000-0000000000c3
BGINBOX="$T/bg.sock"
python3 "$T/ctl.py" inbox "$BGINBOX" "$T/bg-inbox" &
PIDS+=("$!")
until_true 100 test -S "$BGINBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"bgone","nameSource":"user","kind":"bg","jobId":"0a1b2c3d","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$BG" "$R" "$BGINBOX" > "$HOME/.claude/sessions/bgone.json"
SUP="$(ctl supsock "$HOME")"
SUPDIR="$(dirname "$SUP")"
case "$SUPDIR" in /tmp/cc-daemon-*/????????) ;; *) echo "refusing an unexpected supervisor path: $SUPDIR"; exit 1 ;; esac
# The engine's own socket root is owner-only at every level; so is the stand-in's.
[ -d "$(dirname "$SUPDIR")" ] || mkdir -m 700 "$(dirname "$SUPDIR")"
mkdir -m 700 "$SUPDIR" "$HOME/.claude/daemon"
printf '0123456789abcdef0123456789abcdef' > "$HOME/.claude/daemon/control.key"
python3 "$T/ctl.py" supervisor "$SUP" "$T/sup-in" ok &
SUPPID=$!
PIDS+=("$SUPPID")
until_true 100 test -S "$SUP" || true
set +e; OUT="$(cd "$R" && "$SMINOS" say "@bgone pick up the review" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "bgone: sent" "a human's say to a --bg job with no bridge is sent"
REQ="$(tail -1 "$T/sup-in" 2>/dev/null)"
assert_equals "$(field_of "$REQ" op)" "reply" "through the supervisor's reply"
assert_equals "$(field_of "$REQ" short)" "0a1b2c3d" "to the job"
assert_equals "$(field_of "$REQ" auth)" "0123456789abcdef0123456789abcdef" "presenting the control key"
assert_equals "$(field_of "$REQ" nextTurn)" "true" "as queued input, never an answer to an open question"
assert_contains "$(field_of "$REQ" text)" "pick up the review" "carrying the frame"
assert_equals "$([ -s "$T/bg-inbox" ] && echo framed || echo none)" "none" "and not the inbox frame"
run "$SMINOS" steer "$BG" "stop after this file"
assert_rc 0 "$RC" "a steer to a --bg job with no bridge exits 0"
assert_contains "$OUT" "supervisor" "through the supervisor"
assert_contains "$(tail -1 "$T/sup-in")" "stop after this file" "which got the text"
# A peer's say is a peer message: the inbox frame.
set +e; OUT="$(cd "$R" && CLAUDE_CODE_SESSION_ID="$SID" "$SMINOS" say "@bgone from a peer" 2>&1)"; RC=$?; set -e
until_true 100 test -s "$T/bg-inbox" || true
assert_contains "$(cat "$T/bg-inbox" 2>/dev/null)" "from a peer" "a session's say to it is the inbox frame"
assert_not_contains "$(cat "$T/sup-in")" "from a peer" "not the supervisor's reply"
# The supervisor refusing: the inbox frame.
kill "$SUPPID"; wait "$SUPPID" 2>/dev/null || true
python3 "$T/ctl.py" supervisor "$SUP" "$T/sup-in" refuse &
PIDS+=("$!")
until_true 100 test -S "$SUP" || true
set +e; OUT="$(cd "$R" && "$SMINOS" say "@bgone refused then framed" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "bgone: sent" "a reply the supervisor refuses still reaches the job"
until_true 100 grep -q "refused then framed" "$T/bg-inbox" || true
assert_contains "$(cat "$T/bg-inbox")" "refused then framed" "as the inbox frame"
# A terminal session with no bridge: a steer goes as a cross-session frame.
TERM_SID=5e000004-0000-4000-8000-0000000000c4
TINBOX="$T/term.sock"
python3 "$T/ctl.py" inbox "$TINBOX" "$T/term-inbox" &
PIDS+=("$!")
until_true 100 test -S "$TINBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"termy","nameSource":"user","kind":"interactive","status":"busy","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$TERM_SID" "$R" "$TINBOX" > "$HOME/.claude/sessions/termy.json"
set +e; OUT="$(cd "$R" && "$SMINOS" steer termy "mind the tabs" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a steer to a terminal session with no bridge exits 0"
assert_contains "$OUT" "frame" "as a cross-session frame"
until_true 100 test -s "$T/term-inbox" || true
assert_contains "$(cat "$T/term-inbox" 2>/dev/null)" "mind the tabs" "which its inbox got"

echo "a MAWS lane B session (O12 M3): the child's verdict and the record's controller:"
# MAWS's engine host marks each `claude -p` it launches: MAWS_LANE=B beside
# SMNS_MEMBER, its own pid. The child (whose parent is the session, here the
# stand-in) says in its hello whether the session's parent is that pid, once
# the session's registry record and `ps` let it tell; and relays the lane to
# the session's record (O12 M1's controller), once the record exists.
LA=5b000001-0000-4000-8000-0000000000c7
LB=5b000001-0000-4000-8000-0000000000c8
LM=5b000001-0000-4000-8000-0000000000c9
LP=5b000001-0000-4000-8000-0000000000ca
lane_record() { # session [lane] → its session record, as the hook writes one (with that controller)
  python3 - "$SMINOS_HOME/session-records" "$1" "${2:-}" <<'PY2'
import json, os, sys
d, sid, lane = sys.argv[1:4]
os.makedirs(d, mode=0o700, exist_ok=True)
rec = {"session": sid, "source": "hook", "basis": "hook", "origin": {"kind": "maws"}, "owners": ["@machine"],
       "ownersProof": [], "principal": "@machine", "inference": {"kind": "slot", "configDir": "/c"},
       "created": "2026-10-27T00:00:00.000Z", "former": []}
if lane:
    rec["controller"] = {"lane": lane, "since": "2026-10-27T00:00:00.000Z"}
with open(os.path.join(d, sid + ".json"), "w") as f:
    json.dump(rec, f)
PY2
}
controller_of() { # session → its record's controller lane, or none
  python3 -c 'import json, sys
try:
    print((json.load(open(sys.argv[1])).get("controller") or {}).get("lane") or "none")
except OSError:
    print("none")' "$SMINOS_HOME/session-records/$1.json"
}
controller_is() { [ "$(controller_of "$1")" = "$2" ]; }
registry() { # pid session → the engine's registry record for the session's process
  printf '{"pid":%s,"sessionId":"%s","status":"busy","kind":"sdk-cli"}\n' "$1" "$2" > "$HOME/.claude/sessions/$1.json"
}
lanefake() { # session lines-file [env...] → the stand-in, under the given environment
  local sid="$1" out="$2"; shift 2
  env "$@" python3 "$T/ctl.py" fakemod "$SMINOS" "$sid" "$out" "$T/mode" &
  LANEFAKE=$!
  PIDS+=("$LANEFAKE")
}
lane_said() { grep -q '"op": "lane"' "$1"; }
lane_of_lines() { # lines-file → the last lane the child said: its hello's, or a later line's
  python3 -c 'import json, sys
lane = "absent"
for line in open(sys.argv[1]):
    m = json.loads(line)
    if m.get("op") in ("hello", "lane") and "lane" in m:
        lane = m["lane"]
print(lane)' "$1"
}
lane_is() { [ "$(lane_of_lines "$1")" = "$2" ]; }
hello_said() { test -s "$1"; }
mode busy

# Unmarked: no verdict, and the record says lane A.
lane_record "$LA"
lanefake "$LA" "$T/lines-la"
until_true 100 answers "$SMINOS_HOME/bridge/$LA.sock" || true
assert_equals "$(lane_of_lines "$T/lines-la")" "absent" "an unmarked session's hello carries no lane verdict"
assert_not_contains "$(ctl get "$SMINOS_HOME/bridge/$LA.sock" /status)" '"lane"' "nor its status"
until_true 100 controller_is "$LA" A || true
assert_equals "$(controller_of "$LA")" "A" "its record's controller is lane A"
kill "$LANEFAKE" 2>/dev/null || true

# Marked, the session's registry record not written yet: unresolved, then match
# once it is; the record, written after the verdict, gets lane B on a retry.
lanefake "$LB" "$T/lines-lb" MAWS_LANE=B SMNS_MEMBER=$$
until_true 100 hello_said "$T/lines-lb" || true
assert_equals "$(lane_of_lines "$T/lines-lb")" "unresolved" "a marked session whose pid is not in the registry yet: unresolved"
assert_equals "$(controller_of "$LB")" "none" "no controller is relayed while unresolved"
registry "$LANEFAKE" "$LB"
until_true 100 lane_said "$T/lines-lb" || true
assert_equals "$(lane_of_lines "$T/lines-lb")" "match" "once it is, the parent check resolves: match, said on its own line"
assert_contains "$(ctl get "$SMINOS_HOME/bridge/$LB.sock" /status)" '"lane": "match"' "and the status says it"
lane_record "$LB"
until_true 100 controller_is "$LB" B || true
assert_equals "$(controller_of "$LB")" "B" "a record written after the verdict gets lane B on the child's retry"
mode observer
run "$SMINOS" steer "$LB" "take over"
assert_rc 1 "$RC" "a steer an observer's bridge refuses exits 1"
assert_contains "$OUT" "lane-b" "naming the refusal's code"
assert_contains "$OUT" "MAWS controls this session" "and its reason"
mode busy
kill "$LANEFAKE" 2>/dev/null || true

# Marked, but the mark is another process (a `claude` started from a lane B
# session's Bash inherits both variables, its parent another): mismatch, lane A.
lane_record "$LM" B
lanefake "$LM" "$T/lines-lm" MAWS_LANE=B SMNS_MEMBER=2
registry "$LANEFAKE" "$LM"
until_true 100 lane_is "$T/lines-lm" mismatch || true
assert_equals "$(lane_of_lines "$T/lines-lm")" "mismatch" "a parent known and not the mark: mismatch"
until_true 100 controller_is "$LM" A || true
assert_equals "$(controller_of "$LM")" "A" "its record's controller moves to lane A"
kill "$LANEFAKE" 2>/dev/null || true

# Marked, `ps` failing: unresolved, controller unset, until ps answers.
mkdir -p "$T/psbin"
printf '#!/bin/sh\n[ -e "%s" ] && exec /bin/ps "$@"\nexit 1\n' "$T/ps-ok" > "$T/psbin/ps"
chmod +x "$T/psbin/ps"
lane_record "$LP"
lanefake "$LP" "$T/lines-lp" MAWS_LANE=B SMNS_MEMBER=$$ PATH="$T/psbin:$PATH"
registry "$LANEFAKE" "$LP"
until_true 100 hello_said "$T/lines-lp" || true
sleep 2.5   # past one retry (every 2 s): nothing to wait on but the retry's clock
assert_equals "$(lane_of_lines "$T/lines-lp")" "unresolved" "a session whose ps fails stays unresolved through a retry"
assert_equals "$(controller_of "$LP")" "none" "and its record's controller unset"
touch "$T/ps-ok"
until_true 100 lane_said "$T/lines-lp" || true
assert_equals "$(lane_of_lines "$T/lines-lp")" "match" "once ps answers, match"
until_true 100 controller_is "$LP" B || true
assert_equals "$(controller_of "$LP")" "B" "and lane B relayed"
kill "$LANEFAKE" 2>/dev/null || true

# A replacement child (a reload, a restart) after the host exited and the
# engine was re-parented: the parent check would now say mismatch, but the
# module tells it the process's verdict, which it keeps for its decision
# route and its relay; the record's lane B stands.
LR=5b000001-0000-4000-8000-0000000000cb
lane_record "$LR" B
lanefake "$LR" "$T/lines-lr" MAWS_LANE=B SMNS_MEMBER=2 FAKEMOD_LANE=match
registry "$LANEFAKE" "$LR"
until_true 100 answers "$SMINOS_HOME/bridge/$LR.sock" || true
assert_equals "$(lane_of_lines "$T/lines-lr")" "match" "a replacement child takes the verdict its module holds"
run ctl postto "$SMINOS_HOME/bridge/$LR.sock" /requests/toolu_x/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" '"code": "lane-b"' "its decision route stays refused"
sleep 2.5   # past one relay retry (every 2 s): nothing to wait on but its clock
assert_equals "$(controller_of "$LR")" "B" "and the record's lane B stands"
assert_equals "$(lane_of_lines "$T/lines-lr")" "match" "no later verdict line moves it"
kill "$LANEFAKE" 2>/dev/null || true

# A lane-A session later reopened by MAWS as lane B, under the same id: the
# new launch's verdict replaces the controller.
assert_equals "$(controller_of "$LA")" "A" "the session ran as lane A"
lanefake "$LA" "$T/lines-la2" MAWS_LANE=B SMNS_MEMBER=$$
registry "$LANEFAKE" "$LA"
until_true 100 controller_is "$LA" B || true
assert_equals "$(controller_of "$LA")" "B" "reopened by MAWS, its record's controller is lane B"
kill "$LANEFAKE" 2>/dev/null || true

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge control assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge control assertions FAILED"
  exit 1
fi
