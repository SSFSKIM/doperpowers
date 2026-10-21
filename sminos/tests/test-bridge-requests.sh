#!/usr/bin/env bash
#
# Requests from outside and their settlement (DC2 M3, DX5): the endpoint's
# pending set and recent settlements, the mod's long-poll for a decision, a
# client's decision and its refusals, the session record as the terminal's
# answer, a background subagent's window, an async question relayed to the
# mod, and `sminos decide` / `sminos answer`. A stand-in for the mod
# (fakemod) spawns the child as the mod does and, like the mod, polls for
# each permission request it raised and settles it with what the engine
# would have used; the test raises requests by posting the mod's events.
# Hermetic: HOME and SMINOS_HOME are temporary (SMINOS_HOME short, for the
# socket's path); the session record is a file the test writes.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smq.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-0000000000d1" >/dev/null 2>&1 || break; sleep 0.05; done
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
# Polls every 50 ms until the command holds. The ceiling is a liveness bound,
# generous and uniform, not a claim about the machine's speed (ci-kit §6).
LIVENESS_SECONDS=30
until_true() { # command...
  local end=$((SECONDS + LIVENESS_SECONDS))
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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME CLAUDE_CONFIG_DIR
export HOME="$T/home"
export SMINOS_HOME="$T/s"
mkdir -p "$HOME/.claude/sessions"
mkdir -m 700 "$SMINOS_HOME"
SID=5b000001-0000-4000-8000-0000000000d1
SOCK="$SMINOS_HOME/bridge/$SID.sock"

cat > "$T/ctl.py" <<'PY'
import http.client, json, os, socket, subprocess, sys, threading, time

class Conn(http.client.HTTPConnection):
    def __init__(self, path, timeout=30):
        super().__init__("bridge", timeout=timeout)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
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

WINNER = {"cli": "other", "terminal": "terminal", "bridge": "other"}

op = sys.argv[1]
if op == "post":            # sock events-json
    print(request(sys.argv[2], "POST", "/events", sys.argv[3])[0])
elif op == "get":           # sock url
    status, text = request(sys.argv[2], "GET", sys.argv[3])
    print(status, text)
elif op == "postto":        # sock url body
    status, text = request(sys.argv[2], "POST", sys.argv[3], sys.argv[4])
    print(status, text)
elif op == "fakemod":       # sminos session lines-file decisions-file mode-file
    # The mod's stand-in. Spawns the child, answers its command lines (an
    # async question's `answer`), and for every permission request it is
    # told of (a `raised` on the stream that is not async) polls the child as
    # the mod's hook does, then settles it as the engine would have:
    # the decision handed out wins, unless the mode file says the terminal
    # answered first ("terminal"); a poll the child ends because the terminal
    # answered settles it as the terminal's.
    sminos, session, out, decisions, modefile = sys.argv[2:7]
    child = subprocess.Popen([sminos, "bridge", "--session", session], stdout=subprocess.PIPE,
                             stderr=open(out + ".err", "a"), text=True)
    sock = None
    polled = set()

    def settle(rid, outcome, by):
        post(sock, [{"type": "settled", "request": rid, "winner": WINNER.get(by, "web"), "outcome": outcome, "by": by}])

    def poll(raised):
        rid = raised["request"]
        while True:
            try:
                status, text = request(sock, "GET", "/requests/%s/wait?ms=2000" % rid)
            except OSError:
                return
            if status == 200:
                got = json.loads(text)
                with open(decisions, "a") as f:
                    f.write(json.dumps({"request": rid, **got}) + "\n")
                mode = open(modefile).read().strip() if os.path.exists(modefile) else ""
                while mode == "hold":   # the engine has the answer and has not settled it yet
                    time.sleep(0.05)
                    mode = open(modefile).read().strip() if os.path.exists(modefile) else ""
                d = got["decision"]
                if mode == "terminal":
                    settle(rid, "allow", "terminal")
                elif raised.get("tool") == "AskUserQuestion" and d["behavior"] == "allow":
                    settle(rid, "answered", got["by"])
                else:
                    settle(rid, d["behavior"], got["by"])
                return
            if status == 410:
                if json.loads(text).get("reason") == "terminal":
                    with open(decisions, "a") as f:
                        f.write(json.dumps({"request": rid, "closed": "terminal"}) + "\n")
                    settle(rid, "allow", "terminal")
                return

    def follow():
        while sock is None:
            time.sleep(0.05)
        c = Conn(sock, timeout=None)
        c.request("GET", "/events")
        r = c.getresponse()
        for raw in r:
            e = json.loads(raw)
            for raised in (e.get("pending") or []) if e.get("type") == "snapshot" else [e]:
                if raised.get("type", "raised") == "raised" and "request" in raised and not raised.get("async") \
                        and raised["request"] not in polled:
                    polled.add(raised["request"])
                    threading.Thread(target=poll, args=(raised,), daemon=True).start()

    threading.Thread(target=follow, daemon=True).start()
    with open(out, "a") as f:
        for line in child.stdout:
            f.write(line)
            f.flush()
            msg = json.loads(line)
            if msg.get("op") == "hello":
                keep_nonce(msg)
                post(msg["socket"], [{"type": "resync", "turns": [], "streaming": [], "agents": []}])
                sock = msg["socket"]
                continue
            cid, o = msg["id"], msg["op"]
            if o == "answer":
                result = {"ok": True, "result": {"answered": True}}
                events = [{"type": "settled", "request": msg["request"], "winner": WINNER.get(msg["by"], "web"),
                           "outcome": "answered", "by": msg["by"]}]
            else:
                result, events = {"ok": False, "error": "unknown op: %s" % o}, []
            post(sock, events + [{"type": "result", "id": cid, "op": o, **result}])
    child.wait()
PY
ctl() { python3 "$T/ctl.py" "$@"; }
answers() { ctl get "$1" /status 2>/dev/null | grep -q '"ready": true'; }
snapshot() { python3 -c 'import http.client, socket, sys
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.connect(sys.argv[1])
c = C("bridge"); c.request("GET", "/events"); print(c.getresponse().readline().decode().strip())' "$1"; }
presence() { # status → the session record the engine would write for the child's parent
  printf '{"pid":%s,"sessionId":"%s","status":"%s","kind":"interactive"}\n' "$FAKEMOD" "$SID" "$1" \
    > "$HOME/.claude/sessions/$FAKEMOD.json"
}
mode() { printf '%s\n' "$1" > "$T/mode"; }
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }
past_ms() { [ "$(now_ms)" -gt "$1" ]; }
# A dialog's close is read as the terminal's answer only once the bridge has
# read the session record as `waiting` since the request was raised. Its
# watcher reads the record every 0.25 s and exposes no sign of having done
# so, so this wait alone is on the clock: eight reads long, where the product
# gives no event to wait on. (A 0.5 s gap failed 2 of 20 runs on a loaded
# macOS runner: the watcher never saw `waiting`, and the close went unseen.)
seen_waiting() { sleep 2; }
decision_of() { # request → the last decision line the stand-in got for it
  python3 -c 'import json, sys
hits = [l for l in open(sys.argv[1]) if json.loads(l).get("request") == sys.argv[2]] if __import__("os").path.exists(sys.argv[1]) else []
print(hits[-1].strip() if hits else "")' "$T/decisions" "$1"
}
raise_bash() { # request [extra-json-fields]
  ctl post "$SOCK" '[{"type":"raised","request":"'"$1"'","tool":"Bash","input":{"command":"rm -rf /tmp/x"},"agentId":null'"${2:-}"'}]' >/dev/null
}
QUESTIONS='{"questions":[{"question":"Which fruit?","header":"Fruit","options":[{"label":"Apple","description":"a"},{"label":"Mango","description":"m"}],"multiSelect":false},{"question":"Which sides?","header":"Sides","options":[{"label":"Fries","description":"f"},{"label":"Salad","description":"s"},{"label":"Soup","description":"o"}],"multiSelect":true}]}'

mode engine
python3 "$T/ctl.py" fakemod "$SMINOS" "$SID" "$T/lines" "$T/decisions" "$T/mode" &
FAKEMOD=$!
PIDS+=("$FAKEMOD")
until_true answers "$SOCK" || true
presence waiting

echo "the pending set:"
raise_bash toolu_perm01
SNAP="$(snapshot "$SOCK")"
assert_equals "$(field_of "$SNAP" pending.0.request)" "toolu_perm01" "a raised request is pending in the snapshot"
assert_equals "$(field_of "$SNAP" pending.0.tool)" "Bash" "with its tool"
assert_equals "$(field_of "$SNAP" pending.0.input.command)" "rm -rf /tmp/x" "and its input"
run ctl get "$SOCK" /requests/toolu_perm01
assert_contains "$OUT" "200 " "the request's route answers while it is pending"
assert_equals "$(field_of "${OUT#200 }" session)" "$SID" "naming the session"
assert_equals "$(field_of "${OUT#200 }" input.command)" "rm -rf /tmp/x" "with the content a decision is checked against"
run ctl get "$SOCK" /requests
assert_equals "$(field_of "${OUT#200 }" pending.0.request)" "toolu_perm01" "the requests route lists it"
run ctl get "$SOCK" /requests/toolu_nothing
assert_contains "$OUT" "404 " "a request nobody raised is 404"

echo "a decision from outside:"
run ctl postto "$SOCK" /requests/toolu_perm01/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" "200 " "a client's decision on a pending request is accepted"
until_true grep -q toolu_perm01 "$T/decisions" || true
D="$(decision_of toolu_perm01)"
assert_equals "$(field_of "$D" decision.behavior)" "allow" "the mod's poll receives it"
assert_equals "$(field_of "$D" by)" "cli" "with who decided"
run ctl postto "$SOCK" /requests/toolu_perm01/decision '{"behavior":"deny","by":"cli"}'
assert_contains "$OUT" "409 " "a second decision on the same request is refused"
until_true bash -c '[ "$(python3 "$1/ctl.py" get "$2" /requests/toolu_perm01 | cut -c1-3)" = 410 ]' _ "$T" "$SOCK" || true
run ctl get "$SOCK" /requests/toolu_perm01
assert_contains "$OUT" "410 " "once the mod settled it, the request's route says settled (410)"
assert_equals "$(field_of "${OUT#410 }" settled.winner)" "other" "naming the winner"
assert_equals "$(field_of "${OUT#410 }" settled.by)" "cli" "and who answered"
run ctl postto "$SOCK" /requests/toolu_perm01/decision '{"behavior":"deny","by":"cli"}'
assert_contains "$OUT" "409 " "a decision after the settlement is refused"
assert_equals "$(field_of "${OUT#409 }" settled.outcome)" "allow" "naming the settlement"
SNAP="$(snapshot "$SOCK")"
assert_equals "$(field_of "$SNAP" pending)" "[]" "a subscriber arriving after the settlement sees nothing pending"
assert_equals "$(field_of "$SNAP" settled.0.request)" "toolu_perm01" "and the request settled"
assert_equals "$(field_of "$SNAP" settled.0.outcome)" "allow" "with its outcome"
run ctl get "$SOCK" "/requests/toolu_perm01/wait?ms=200"
assert_contains "$OUT" "410 " "a poll for a settled request ends at once (410)"

echo "a second decision while the first is taken and not yet settled:"
mode hold
raise_bash toolu_perm09
run ctl postto "$SOCK" /requests/toolu_perm09/decision '{"behavior":"allow","by":"m-first"}'
assert_contains "$OUT" "200 " "the first decision is taken"
until_true grep -q toolu_perm09 "$T/decisions" || true
run ctl postto "$SOCK" /requests/toolu_perm09/decision '{"behavior":"deny","by":"cli"}'
assert_contains "$OUT" "409 " "a second one is refused"
assert_equals "$(field_of "${OUT#409 }" by)" "m-first" "naming who answered first, as a field"
assert_equals "$(field_of "${OUT#409 }" winner)" "null" "and no winner: nothing is settled yet"
mode engine
until_true bash -c '[ "$(python3 "$1/ctl.py" get "$2" /requests/toolu_perm09 | cut -c1-3)" = 410 ]' _ "$T" "$SOCK" || true

echo "decisions refused:"
raise_bash toolu_perm02
run ctl postto "$SOCK" /requests/toolu_perm02/decision '{"behavior":"maybe","by":"cli"}'
assert_contains "$OUT" "400 " "a behavior that is neither allow nor deny is refused"
run ctl postto "$SOCK" /requests/toolu_perm02/decision '{"behavior":"allow"}'
assert_contains "$OUT" "400 " "a decision that says nobody decided is refused"
run ctl postto "$SOCK" /requests/toolu_perm02/decision '{"behavior":"allow","by":"terminal"}'
assert_contains "$OUT" "400 " "a client cannot answer as the terminal"
run ctl postto "$SOCK" /requests/toolu_perm02/decision '{"behavior":"allow","by":"cli","updatedInput":{"command":"rm -rf /"}}'
assert_contains "$OUT" "400 " "a permission is allowed as asked: a rewritten input is refused"
run ctl postto "$SOCK" /requests/toolu_nothing/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" "404 " "a decision on a request nobody raised is 404"

echo "the terminal answering first:"
# The stand-in's poll on toolu_perm02 is open; the session record leaving
# `waiting` is the terminal's answer: the poll ends, and the request settles
# as the terminal's.
seen_waiting
presence busy
until_true grep -q '"request": "toolu_perm02", "closed": "terminal"' "$T/decisions" || true
assert_contains "$(cat "$T/decisions")" '"request": "toolu_perm02", "closed": "terminal"' \
  "the session record leaving waiting ends the mod's poll, saying the terminal answered"
until_true bash -c '[ "$(python3 "$1/ctl.py" get "$2" /requests/toolu_perm02 | cut -c1-3)" = 410 ]' _ "$T" "$SOCK" || true
run ctl postto "$SOCK" /requests/toolu_perm02/decision '{"behavior":"deny","by":"cli"}'
assert_contains "$OUT" "409 " "the CLI answering after the terminal did is refused"
assert_equals "$(field_of "${OUT#409 }" settled.winner)" "terminal" "as settled by the terminal"
# A decision that reaches the child after the dialog closed, before its
# record was read, is refused there too: the record is read at the decision.
presence waiting
raise_bash toolu_perm03
seen_waiting
presence idle
run ctl postto "$SOCK" /requests/toolu_perm03/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" "409 " "a decision for a dialog the terminal has closed is refused"
assert_contains "$OUT" "terminal" "saying the terminal answered it"
# Under load the watcher may settle the request before the decision lands:
# the refusal is then "already settled", its winner under `settled`.
WON=$(field_of "${OUT#409 }" winner); BY=$(field_of "${OUT#409 }" by)
if [ "$WON" = null ]; then WON=$(field_of "${OUT#409 }" settled.winner); BY=$(field_of "${OUT#409 }" settled.by); fi
assert_equals "$WON" "terminal" "the terminal won, as a field"
assert_equals "$BY" "terminal" "and decided, as a field"
presence waiting

echo "a background subagent's window:"
# A window open for the whole case and one already past, rather than one
# window whose closing the case races: the deadline is an event to wait for.
OPEN_DL=$(( $(now_ms) + 600000 ))
ctl post "$SOCK" '[{"type":"raised","request":"toolu_bg01","tool":"Bash","input":{"command":"make"},"agentId":"a9","deadline":'"$OPEN_DL"'}]' >/dev/null
presence busy   # no dialog is drawn while the window is open: busy says nothing
sleep 0.4       # a window to see the busy record misread; a slow machine only shortens it
run ctl get "$SOCK" /requests/toolu_bg01
assert_contains "$OUT" "200 " "a busy record does not close a window still open"
assert_equals "$(field_of "${OUT#200 }" deadline)" "$OPEN_DL" "the request carries its deadline"
DL=$(( $(now_ms) + 300 ))
ctl post "$SOCK" '[{"type":"raised","request":"toolu_bg03","tool":"Bash","input":{"command":"make"},"agentId":"a9","deadline":'"$DL"'}]' >/dev/null
until_true past_ms "$DL" || true
run ctl postto "$SOCK" /requests/toolu_bg03/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" "409 " "after the deadline a decision is refused"
assert_contains "$OUT" "terminal" "the prompt is the terminal's now"
assert_equals "$(field_of "${OUT#409 }" terminalOnly)" "true" "terminal only, as a field"
run ctl get "$SOCK" /requests/toolu_bg03
assert_contains "$OUT" "200 " "and the request stays pending until the terminal answers"
DL="$OPEN_DL"
ctl post "$SOCK" '[{"type":"raised","request":"toolu_bg02","tool":"Bash","input":{"command":"make"},"agentId":"a9","deadline":'"$DL"'}]' >/dev/null
run ctl postto "$SOCK" /requests/toolu_bg02/decision '{"behavior":"deny","by":"m-123"}'
assert_contains "$OUT" "200 " "inside the window a decision is accepted, whatever the record says"
until_true grep -q toolu_bg02 "$T/decisions" || true
assert_equals "$(field_of "$(decision_of toolu_bg02)" by)" "m-123" "and handed to the mod with its decider"
ctl post "$SOCK" '[{"type":"settled","request":"toolu_bg01","winner":"terminal","outcome":"allow","by":"terminal"},{"type":"settled","request":"toolu_bg03","winner":"terminal","outcome":"allow","by":"terminal"}]' >/dev/null
presence waiting

echo "questions:"
ctl post "$SOCK" '[{"type":"raised","request":"toolu_plugin_q1","tool":"AskUserQuestion","input":'"$QUESTIONS"',"agentId":null}]' >/dev/null
run ctl postto "$SOCK" /requests/toolu_plugin_q1/decision '{"behavior":"allow","by":"cli"}'
assert_contains "$OUT" "400 " "a question allowed without answers is refused"
run ctl postto "$SOCK" /requests/toolu_plugin_q1/decision '{"behavior":"allow","by":"cli","updatedInput":{"answers":{"Which veg?":"Kale"}}}'
assert_contains "$OUT" "400 " "an answer to a question it does not ask is refused"
run "$SMINOS" answer "$SID" toolu_plugin_q1 Apple
assert_rc 2 "$RC" "answer with fewer answers than questions is a usage error"
assert_contains "$OUT" "2 questions" "saying how many it asks"
run "$SMINOS" answer "$SID" toolu_plugin_q1 2 "fries, 3"
assert_rc 0 "$RC" "answer exits 0 once the session settled the question as answered from here"
assert_contains "$OUT" "answered" "saying so"
D="$(decision_of toolu_plugin_q1)"
assert_equals "$(field_of "$D" decision.updatedInput.answers)" '{"Which fruit?": "Mango", "Which sides?": "Fries, Soup"}' \
  "an option's number and a label in any case name the option; multi-select labels are joined"
ctl post "$SOCK" '[{"type":"raised","request":"toolu_plugin_q2","tool":"AskUserQuestion","input":'"$QUESTIONS"',"agentId":null}]' >/dev/null
run "$SMINOS" answer "$SID" toolu_plugin_q2 "a pear, please" "Salad"
D="$(decision_of toolu_plugin_q2)"
assert_equals "$(field_of "$D" decision.updatedInput.answers)" '{"Which fruit?": "a pear, please", "Which sides?": "Salad"}' \
  "an answer that names no option goes as typed"

echo "an async question:"
ctl post "$SOCK" '[{"type":"raised","request":"toolu_async1","tool":"mcp__doperpowers__AskUserQuestion","input":'"$QUESTIONS"',"agentId":null,"async":true}]' >/dev/null
run ctl postto "$SOCK" /requests/toolu_async1/decision '{"behavior":"deny","by":"cli"}'
assert_contains "$OUT" "400 " "an async question is answered, never denied"
run "$SMINOS" answer "$SID" toolu_async1 Apple Soup
assert_rc 0 "$RC" "answer reaches an async question too"
L="$(grep '"op": "answer"' "$T/lines" | tail -1)"
assert_equals "$(field_of "$L" request)" "toolu_async1" "relayed to the mod as an answer command"
assert_equals "$(field_of "$L" answers)" '{"Which fruit?": "Apple", "Which sides?": "Soup"}' "with the answers"
assert_equals "$(field_of "$L" by)" "cli" "and who answered"

echo "sminos decide:"
raise_bash toolu_perm04
run "$SMINOS" decide "$SID" toolu_perm04 deny --message "not that directory"
assert_rc 0 "$RC" "decide exits 0 once the session settled the request with its decision"
assert_contains "$OUT" "deny" "saying the outcome"
D="$(decision_of toolu_perm04)"
assert_equals "$(field_of "$D" decision.message)" "not that directory" "the deny's message reached the mod"
raise_bash toolu_perm05_abcdef
run "$SMINOS" decide "$SID" toolu_perm05 allow
assert_rc 0 "$RC" "a request may be named by a unique prefix of its id"
run "$SMINOS" decide "$SID" toolu_perm04 allow
assert_rc 1 "$RC" "deciding a settled request exits 1"
assert_contains "$OUT" "already settled" "saying it was already settled"
mode terminal
raise_bash toolu_perm06
run "$SMINOS" decide "$SID" toolu_perm06 deny
assert_rc 1 "$RC" "a decision the engine did not use (the terminal's answer won) exits 1"
assert_contains "$OUT" "terminal" "naming the side that won"
mode engine
run "$SMINOS" decide "$SID" toolu_perm99 allow
assert_rc 1 "$RC" "a request the session never raised exits 1"
run "$SMINOS" decide "$SID" toolu_perm07 perhaps
assert_rc 2 "$RC" "a decision that is neither allow nor deny is a usage error"
run "$SMINOS" decide 5c000002-0000-4000-8000-0000000000d2 toolu_x allow
assert_rc 4 "$RC" "decide on a session with no bridge exits 4"

echo "the stream, in the human view:"
"$SMINOS" watch "$SID" > "$T/h1" 2>&1 &
PIDS+=("$!")
until_true grep -q "watching" "$T/h1" || true
raise_bash toolu_perm08
ctl post "$SOCK" '[{"type":"settled","request":"toolu_perm08","winner":"terminal","outcome":"deny","by":"terminal"}]' >/dev/null
until_true grep -q "settled" "$T/h1" || true
HV="$(cat "$T/h1")"
assert_contains "$HV" "toolu_perm08" "a raised request is printed with its id"
assert_contains "$HV" "rm -rf /tmp/x" "and what it asks"
assert_contains "$HV" "deny (terminal)" "and its settlement with who answered"

echo "a resync that sent questions ahead of it:"
# Whole questions alone past the engine's limit on a body: the mod sends them
# ahead of the resync, each as its own raise, and the resync names them
# (pendingAhead). The child keeps each as that raise left it, so the question
# is still pending and its answers still match it; a name it never got a
# raise for is not made up.
ctl post "$SOCK" '[{"type":"raised","request":"toolu_ahead1","tool":"AskUserQuestion","input":'"$QUESTIONS"',"agentId":null}]' >/dev/null
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"truncated":true,
 "pending":[{"request":"toolu_kept2","tool":"Bash","input":{"command":"ls"},"agentId":null}],
 "pendingAhead":["toolu_ahead1","toolu_never1"],"settled":[]}]' >/dev/null
SNAP="$(snapshot "$SOCK")"
assert_equals "$(python3 -c 'import json, sys; print(" ".join(p["request"] for p in json.loads(sys.argv[1])["pending"]))' "$SNAP")" \
  "toolu_kept2 toolu_ahead1" "the resync's own request and the question sent ahead are pending, and nothing else"
assert_equals "$(field_of "$SNAP" pending.1.input)" "$(python3 -c 'import json, sys; print(json.dumps(json.loads(sys.argv[1])))' "$QUESTIONS")" \
  "the question as its raise carried it, whole"
run "$SMINOS" answer "$SID" toolu_ahead1 Apple Soup
assert_rc 0 "$RC" "it is answered as any question"
assert_equals "$(field_of "$(decision_of toolu_ahead1)" decision.updatedInput.answers)" '{"Which fruit?": "Apple", "Which sides?": "Soup"}' \
  "its answers matched against its questions"

echo "a resync:"
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],
 "pending":[{"request":"toolu_kept1","tool":"Bash","input":{"command":"ls"},"agentId":null}],
 "settled":[{"request":"toolu_old1","winner":"web","outcome":"deny","by":"m-7"}]}]' >/dev/null
SNAP="$(snapshot "$SOCK")"
assert_equals "$(field_of "$SNAP" pending.0.request)" "toolu_kept1" "a resync replaces the pending set with the mod's own"
assert_contains "$(field_of "$SNAP" settled)" '"toolu_old1"' "and brings the mod's recent settlements"
assert_contains "$(field_of "$SNAP" settled)" '"toolu_perm08"' "beside the child's own"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge request assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge request assertions FAILED"
  exit 1
fi
