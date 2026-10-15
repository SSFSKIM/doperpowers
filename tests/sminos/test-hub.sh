#!/usr/bin/env bash
#
# Enrollment and hub projects (DC4 M2 of the desk), against hub_standin.py's
# DX7 redemption. Pins DC4.G1: `sminos hub enroll` reads the code from stdin
# (or a hidden prompt; never argv, which it refuses unread), decodes it as
# the hub's decoder does (enroll_parity.py, over codes the hub's own encoder
# built), redeems it, and stores the credential at mode 0600 — the org key and
# the service token's secret never in any output or in daemon.log; every DX7
# error said with what to do; a second installation claiming an enrolled name
# is refused and told to pick another with --name; the enrolled name is the
# writer host, and a rename leaves this machine's seats and members its own
# while another machine enrolled under the old name stays another;
# `project init --hub` writes the field; a hub project, a malformed hub
# included, runs no git phase and `project attach` refuses it.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per installation;
# `claude` is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/sminos/scripts"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smh.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
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
# Every output of the CLI is kept, to be searched for secrets at the end.
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; printf '%s\n' "$OUT" >> "$T/all.out"; }
until_true() { # tries command... — poll every 50 ms
  local tries="$1"; shift
  for _ in $(seq 1 "$tries"); do "$@" && return 0; sleep 0.05; done
  return 1
}
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
json_get() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(json.dumps(eval(sys.argv[2], {"d": d})))' "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST
export SMINOS_DERIVE_EVERY=0
export DAEMON_BOOT_ID=boot-current
mkdir -p "$T/bin"
# One installation: its HOME, its SMINOS_HOME, its host name.
as() { # name host — the installation `name` is the one the verbs after it run as
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

# A stub `claude`: `agents` lists $STUB_STATE/agents.json; `stop` is recorded.
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
  stop) echo "$2" >> "$STUB_STATE/stops"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

# The hub stand-in: org-1, `testhost` already enrolled (cid-1 / secret-1).
python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-1 secret-1 2000 & PIDS+=("$!")
until_true 100 test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"

# The test's hands on the stand-in, and codes built as the browser builds them
# (encodeEnrollmentCode: JSON.stringify of {hub, org, token, machine, key}).
cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, sys
port = int(open(sys.argv[1]).read())

def call(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body),
              headers={"Content-Type": "application/json", **(headers or {})})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd = sys.argv[2]
if cmd == "token":  # [ttl_s]
    print(call("POST", "/control/enrollment", {"ttl_s": int(sys.argv[3])} if len(sys.argv) > 3 else {})[1]["token"])
elif cmd == "code":  # hub token machine key
    body = json.dumps(dict(zip(("hub", "org", "token", "machine", "key"), [sys.argv[3], "org-1", *sys.argv[4:7]])),
                      separators=(",", ":"), ensure_ascii=False).encode()
    print("smns-enroll-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
elif cmd == "fault":
    call("POST", "/control/fault", {"redeem": sys.argv[3:]})
elif cmd == "state":  # a python expression over the state, d
    print(json.dumps(eval(sys.argv[3], {"d": call("GET", "/control/state")[1]})))
elif cmd == "connect":  # hub.json — open the stream with its credential, read the welcome, close
    cred = json.load(open(sys.argv[3]))
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/machine/stream", headers={"CF-Access-Client-Id": cred["client_id"],
                                                 "CF-Access-Client-Secret": cred["client_secret"]})
    r = c.getresponse()
    print(r.status, r.readline().decode().strip() if r.status == 200 else r.read().decode())
    c.close()
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }
code_for() { # machine [ttl_s] — a fresh token's code proposing `machine`
  local token; token="$(ctl token ${2:+"$2"})"
  ctl code "$HUB" "$token" "$1" "$KEY"
}
redemptions() { ctl state 'len(d["redemptions"])'; }
cred() { echo "$SMINOS_HOME/daemon/hub.json"; }
# Every code is fed on stdin, as a human pastes it; each is kept, to be
# searched for in every output and log at the end.
enroll() { # code [args...]
  local code="$1"; shift
  printf '%s\n' "$code" >> "$T/codes"
  run "$SMINOS" hub enroll "$@" <<<"$code"
}
mode_of() { python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))' "$1"; }

# ---- the code, as the hub decodes it
echo "the code:"
while IFS= read -r line; do
  case "$line" in "ok "*) pass "enroll parity: ${line#ok }" ;; *) fail "enroll parity: ${line#FAIL }" ;; esac
done < <(python3 "$SCRIPT_DIR/enroll_parity.py" "$SCRIPTS" "$SCRIPT_DIR/dx7-enroll-codes.json" 2>&1)

as a alpha
run "$SMINOS" hub show
assert_contains "$OUT" "not enrolled" "an installation that never enrolled says so"
CODE_P="$(code_for alpha)"
printf '%s\n' "$CODE_P" >> "$T/codes"
run "$SMINOS" hub enroll "$CODE_P"
assert_rc 2 "$RC" "a code given as an argument is refused"
assert_contains "$OUT" "never given on the command line" "saying the code belongs at the prompt"
assert_contains "$OUT" "Run sminos hub enroll with no code and paste it at the prompt" "and how to give it"
assert_not_contains "$OUT" "$CODE_P" "without echoing it"
run "$SMINOS" hub enroll --name alpha2 "$CODE_P" more words
assert_rc 2 "$RC" "with other words too"
assert_not_contains "$OUT" "$CODE_P" "still unechoed"
# However the words fall, no parse of them echoes one: stdout and stderr apart.
refused_unechoed() { # label words... (after `sminos hub`)
  local label="$1"; shift
  set +e; "$SMINOS" hub "$@" > "$T/hub.stdout" 2> "$T/hub.stderr" < /dev/null; RC=$?; set -e
  cat "$T/hub.stdout" "$T/hub.stderr" >> "$T/all.out"
  assert_rc 2 "$RC" "refused: $label"
  assert_not_contains "$(cat "$T/hub.stdout")" "$CODE_P" "the code not on stdout: $label"
  assert_not_contains "$(cat "$T/hub.stderr")" "$CODE_P" "nor on stderr: $label"
}
refused_unechoed "a word, then --name, then the code" enroll extra --name beta "$CODE_P"
refused_unechoed "an unknown option carrying the code" enroll --bogus "$CODE_P"
refused_unechoed "an unknown option=the code" enroll "--bogus=$CODE_P"
refused_unechoed "the code as --name" enroll --name "$CODE_P"
refused_unechoed "the code as --name=" enroll "--name=$CODE_P"
refused_unechoed "the code after --replace, --name with no value" enroll --replace "$CODE_P" --name
refused_unechoed "the code in place of the verb" "$CODE_P"
refused_unechoed "the code after show" show "$CODE_P"
refused_unechoed "the code before the verb's options" enroll "$CODE_P" --name=beta --replace
assert_equals "$(redemptions)" 0 "no request reaches the hub"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is written"
assert_equals "$(cat "$SMINOS_HOME/daemon.log" 2>/dev/null | wc -l | tr -d " ")" 0 "nor logged"
enroll "smns-enroll-v2.e30"
assert_rc 2 "$RC" "a code of another version is refused as usage"
assert_contains "$OUT" "enrollment code: not smns-enroll-v1" "in the hub decoder's words"
enroll "$(ctl code "http://desk.example.com" tok alpha "$KEY")"
assert_rc 2 "$RC" "a code naming a hub over plain http off this machine is refused"
assert_contains "$OUT" "enrollment code: the hub is not https" "saying why"
enroll "$(code_for alpha)" --name hub
assert_rc 2 "$RC" "--name hub is refused (the log's own prefix)"
assert_contains "$OUT" "--name takes an admitted machine name" "saying why, without repeating the value"
assert_equals "$(redemptions)" 0 "nothing refused by the CLI reaches the hub"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "and nothing is stored"

# ---- enrollment under this machine's own name
echo "enrolling:"
enroll "$(code_for proposed-a)"
assert_rc 0 "$RC" "enrollment succeeds"
assert_contains "$OUT" "enrolled this machine as alpha" "under this machine's own name, not the one the code proposed"
assert_contains "$OUT" "code proposed proposed-a" "saying which name the code proposed"
assert_contains "$OUT" "--name proposed-a" "and how to claim it instead"
assert_not_contains "$OUT" "no longer as" "no rename: nothing is said of one"
assert_equals "$(mode_of "$(cred)")" "0o600" "the credential is stored at mode 0600"
assert_equals "$(json_get "$(cred)" '[d[k] for k in ("hub", "org", "machine", "key", "former")]')" \
  "[\"$HUB\", \"org-1\", \"alpha\", \"$KEY\", {}]" "with the hub, the org, the name, the key, and no former name"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "alpha"][0]')" \
  "the service token is the one the hub minted for alpha"
run ctl connect "$(cred)"
assert_contains "$OUT" "200 event: welcome" "the stored credential opens the stream"
assert_equals "$(ctl state '[e["state"] for e in d["enrollments"] if e["machine"] == "alpha"][0]')" '"confirmed"' \
  "and that first connection confirms the enrollment"
assert_contains "$(cat "$SMINOS_HOME/daemon.log")" "hub: enrolled as alpha at $HUB (org org-1)" "daemon.log records the enrollment"
run "$SMINOS" hub show
assert_contains "$OUT" "machine  alpha" "hub show names the machine"
assert_contains "$OUT" "hub      $HUB (org org-1)" "and its hub"
BEFORE="$(redemptions)"
enroll "$(code_for other-a)"
assert_rc 1 "$RC" "an enrolled installation refuses a new code"
assert_contains "$OUT" "already enrolled at $HUB as alpha" "saying what it is enrolled as"
assert_contains "$OUT" "--replace" "and how to replace it"
assert_equals "$(redemptions)" "$BEFORE" "without redeeming the code"
assert_equals "$(json_get "$(cred)" 'd["machine"]')" '"alpha"' "the identity is unchanged"

# ---- a second installation under the same host name
echo "a second installation named alpha:"
as b alpha
CODE_B="$(code_for alpha)"
enroll "$CODE_B"
assert_rc 1 "$RC" "claiming a name another machine holds is refused"
assert_contains "$OUT" "another machine of this org is enrolled as alpha" "saying the name is taken"
assert_contains "$OUT" "run sminos hub enroll --name <another name> and paste the same code at the prompt" \
  "and how to pick another with the same code"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is stored"
# Under another host name for once: from alpha, ALPHA differs only in case
# and is refused here before the hub is asked (below).
DAEMON_HOST=b-host enroll "$CODE_B" --name ALPHA
assert_rc 1 "$RC" "the name is taken whatever its case"
assert_contains "$OUT" "another machine of this org is enrolled as ALPHA" "the hub says so"

# ---- this installation's state under alpha, before it is renamed
echo "state before the rename:"
PB="$T/b/proj"
mkdir -p "$PB"
gitq init -q "$PB"
cd "$PB"
"$SMINOS" project init --name bproj >/dev/null
cat > "$T/inbox.py" <<'PY'
import socket, sys
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(sys.argv[1])
srv.listen(8)
while True:
    c, _ = srv.accept()
    buf = b""
    while chunk := c.recv(65536):
        buf += chunk
    with open(sys.argv[2], "ab") as f:
        f.write(buf)
    try:
        c.sendall(b"ok\n")
    except OSError:
        pass
    c.close()
PY
S1=5b000001-0000-4000-8000-0000000000b1
S2=5b000002-0000-4000-8000-0000000000b2
: > "$T/inbox.received"
python3 "$T/inbox.py" "$T/in.sock" "$T/inbox.received" & INBOX=$!
PIDS+=("$INBOX")
until_true 100 test -S "$T/in.sock"
sleep 600 & SLEEPER=$!
PIDS+=("$SLEEPER")
printf '{"pid":%s,"sessionId":"%s","name":"s1","nameSource":"derived","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX" "$S1" "$PB" "$T/in.sock" > "$HOME/.claude/sessions/s1.json"
printf '{"pid":%s,"sessionId":"%s","name":"term","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$SLEEPER" "$S2" "$PB" > "$HOME/.claude/sessions/term.json"
printf '[{"id": "b1short", "sessionId": "%s", "state": "idle"}]\n' "$S1" > "$STUB_STATE/agents.json"
"$SMINOS" seat add bproj s1 --session "$S1" >/dev/null
machines() { printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))'; }
run "$SMINOS" list --json
assert_equals "$(machines)" "[('s1', 'alpha', True), ('term', 'alpha', True)]" "the seat and the session run on alpha"
BLOG="$SMINOS_HOME/projects/$(json_get "$PB/.smns" 'd["project"]' | tr -d '"')/log"
alpha_writers() { local n=0 f; for f in "$BLOG"/alpha.*.jsonl; do [ -e "$f" ] && n=$((n + 1)); done; echo "$n"; }
assert_equals "$(alpha_writers)" 2 "each joined under an alpha/ writer"

# ---- enrolling under another name
echo "the rename:"
enroll "$CODE_B" --name beta
assert_rc 0 "$RC" "the same code, under another name, enrolls"
assert_contains "$OUT" "enrolled this machine as beta" "as beta"
assert_contains "$OUT" "no longer as alpha" "saying this machine is renamed"
assert_contains "$OUT" "already written under alpha stay on this machine" "that what it wrote as alpha stays here"
assert_contains "$OUT" "never reach the hub" "and never reaches the hub or another machine"
assert_contains "$OUT" "DAEMON_HOST" "and that DAEMON_HOST is no longer read"
assert_equals "$(json_get "$(cred)" '[d["machine"], d["former"]]')" "[\"beta\", {\"alpha\": [\"$S1\", \"$S2\"]}]" \
  "hub.json records beta, and alpha as a former name with the sessions this installation held under it"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "s1"' "the seat is listed"
assert_equals "$(machines)" "[('s1', 'beta', True), ('term', 'beta', True)]" "the seat and the session are this machine's, on beta"
run "$SMINOS" send s1 "after the rename"
assert_rc 0 "$RC" "send reaches the seat"
until_true 100 grep -q "after the rename" "$T/inbox.received" || true
assert_contains "$(cat "$T/inbox.received")" "after the rename" "through its inbox"
kill "$SLEEPER"
set +e; wait "$SLEEPER" 2>/dev/null; set -e
run "$SMINOS" list --all --json
assert_contains "$(cat "$BLOG"/beta."$S2".jsonl 2>/dev/null)" '"reason": "ended"' \
  "a session that joined as alpha and ended is retired as this machine's own"
# A's own alpha session, as the hub would bring it here: A holds alpha now.
SA=5a00000a-0000-4000-8000-0000000000aa
python3 - "$SCRIPTS" "$SA" "$PB" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
p = sminos.resolve_project(sys.argv[3])
sminos.log_append(p, "alpha/" + sys.argv[2], "joined", session=sys.argv[2], alias="a-term", name_source="derived",
                  machine="alpha", cwd="/elsewhere", worktree="", role="", seat="", by="")
PY
run "$SMINOS" list --all --json
assert_contains "$(machines)" "('a-term', 'alpha', False)" "a session of the machine now enrolled as alpha is that machine's, not this one's"
run "$SMINOS" list --all --json
assert_equals "$(test -e "$BLOG/beta.$SA.jsonl" && echo there || echo none)" none "and this machine never retires it"
echo "[]" > "$STUB_STATE/agents.json"
run "$SMINOS" retire s1
assert_rc 0 "$RC" "retire acts on the seat"
assert_equals "$(cat "$STUB_STATE/stops" 2>/dev/null)" "b1short" "stopping the session it recorded on alpha"
run "$SMINOS" say "said as beta"
assert_contains "$(cat "$BLOG/beta.human.jsonl")" "said as beta" "new events are written under beta"
assert_equals "$(alpha_writers)" 3 "and no new alpha/ writer appears (two of this machine's, one of the other alpha's)"

# ---- a name that differs only in case
# DX7 compares machine names without case, and a file system that ignores case
# would put Kappa.human.jsonl and kappa.human.jsonl in one file.
echo "a name that differs only in case:"
as k Kappa
PK="$T/k/proj"
mkdir -p "$PK"
gitq init -q "$PK"
cd "$PK"
"$SMINOS" project init --name kproj >/dev/null
"$SMINOS" say "said as Kappa" >/dev/null
KLOG="$SMINOS_HOME/projects/$(json_get "$PK/.smns" 'd["project"]' | tr -d '"')/log"
BEFORE="$(redemptions)"
enroll "$(code_for kappa)" --name kappa
assert_rc 2 "$RC" "a name that differs from this machine's own only in case is refused"
assert_contains "$OUT" "differs from Kappa, the name this machine writes under, only in case" "saying so"
assert_contains "$OUT" "--name Kappa" "and how to keep its name"
assert_equals "$(redemptions)" "$BEFORE" "before anything is redeemed"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is stored"
"$SMINOS" say "said after the refusal" >/dev/null
assert_equals "$(python3 -c 'import glob, json, sys
print(sorted(json.loads(l)["writer"] for p in glob.glob(sys.argv[1] + "/*.jsonl") for l in open(p) if l.strip()))' "$KLOG")" \
  "['Kappa/human', 'Kappa/human']" "this machine still writes as Kappa"
as b alpha
enroll "$(code_for beta)" --name Alpha --replace
assert_rc 2 "$RC" "a name that differs from a former name only in case is refused"
assert_contains "$OUT" "differs from alpha, a name this machine wrote under before, only in case" "saying so"
assert_equals "$(redemptions)" "$BEFORE" "before anything is redeemed"
assert_equals "$(json_get "$(cred)" 'd["machine"]')" '"beta"' "the enrollment is unchanged"
cd "$T"

# ---- what the hub answers, said with what to do
echo "the hub's answers:"
as c gamma
ctl fault lose
enroll "$(code_for gamma)"
assert_rc 0 "$RC" "a lost answer is redeemed again, and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "gamma"][0]')" \
  "with the credential of the second redemption, the one the hub holds"
run ctl connect "$(cred)"
assert_contains "$OUT" "200 event: welcome" "which opens the stream"
as c2 gamma2
ctl fault truncate
enroll "$(code_for gamma2)"
assert_rc 0 "$RC" "a 200 cut short of its length is redeemed again, and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "gamma2"][0]')" \
  "with the rotated credential the hub holds"
as c3 gamma3
CODE_C3="$(code_for gamma3)"
ctl fault truncate truncate truncate
enroll "$CODE_C3"
assert_rc 1 "$RC" "answers cut short every time end the command"
assert_contains "$OUT" "short of its length" "saying how the answer came back"
assert_contains "$OUT" "run the same command again" "and to run it again"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing stored"
enroll "$CODE_C3"
assert_rc 0 "$RC" "run again, it enrolls"
as d delta
CODE_D="$(code_for delta)"
ctl fault lose lose lose
enroll "$CODE_D"
assert_rc 1 "$RC" "answers lost every time end the command"
assert_contains "$OUT" "run the same command again" "saying to run it again"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing stored"
assert_equals "$(ctl state 'len(d["faults"])')" 0 "after three attempts"
enroll "$CODE_D"
assert_rc 0 "$RC" "the same command, run again, rotates the credential and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "delta"][0]')" \
  "storing the rotated one"
as e epsilon
CODE_E="$(code_for epsilon)"
ctl fault busy
enroll "$CODE_E"
assert_rc 1 "$RC" "busy ends the command"
assert_contains "$OUT" "in flight" "saying a redemption is in flight"
assert_contains "$OUT" "run the same command again" "and to run it again"
ctl fault mint-failed
enroll "$CODE_E"
assert_rc 1 "$RC" "mint-failed ends the command"
assert_contains "$OUT" "could not mint" "saying the mint failed"
assert_contains "$OUT" "run the same command again" "and to run it again"
enroll "$CODE_E"
assert_rc 0 "$RC" "the same command then enrolls"
as f zeta
enroll "$CODE_E" --name zeta
assert_rc 1 "$RC" "a token bound to another name is refused"
assert_contains "$OUT" "bound to the machine \"epsilon\"" "naming the name it is bound to"
assert_contains "$OUT" "new code" "and saying to ask for a new code"
as e epsilon
ctl connect "$(cred)" >/dev/null
as f zeta
enroll "$CODE_E" --name epsilon
assert_rc 1 "$RC" "a spent token is refused"
assert_contains "$OUT" "spent" "saying so"
as g eta
CODE_X="$(code_for eta 1)"
sleep 1.2
enroll "$CODE_X"
assert_rc 1 "$RC" "an expired token is refused"
assert_contains "$OUT" "expired" "saying so"
enroll "$(ctl code "$HUB" never-minted eta "$KEY")"
assert_rc 1 "$RC" "a token the hub never issued is refused"
assert_contains "$OUT" "does not know this code's token" "saying so"
ctl fault other-org
enroll "$(code_for eta)"
assert_rc 1 "$RC" "an answer for another org than the code's is refused"
assert_contains "$OUT" "nothing is stored" "and nothing is stored"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "indeed"
as h 'not a name'
enroll "$(code_for theta)"
assert_rc 0 "$RC" "a host name the hub would not admit leaves the code's name"
assert_contains "$OUT" "enrolled this machine as theta" "which is claimed"

# ---- hub projects
echo "hub projects:"
as a alpha
gitq init -q --bare "$T/archive.git"
gitq init -q --bare "$T/archive-h.git"
PH="$T/a/hp"
mkdir -p "$PH"
gitq init -q "$PH"
cd "$PH"
run "$SMINOS" project init --hub --name hubproj --remote "$T/archive-h.git"
assert_rc 0 "$RC" "project init --hub makes a hub project"
assert_equals "$(json_get "$PH/.smns" 'd["hub"]')" "{\"url\": \"$HUB\", \"org\": \"org-1\"}" ".smns names the hub and the org"
assert_contains "$OUT" "a hub project of $HUB" "and says so"
run "$SMINOS" project show
assert_contains "$OUT" "hub      $HUB (org org-1)" "project show names the hub"
PG="$T/a/gp"
mkdir -p "$PG"
gitq init -q "$PG"
cd "$PG"
"$SMINOS" project init --name gitproj --remote "$T/archive.git" >/dev/null
"$SMINOS" say "before the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: synced" "a hub-less project syncs through its remote"
SMNS_BEFORE="$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub on an existing .smns adds the field"
assert_equals "$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')" "$SMNS_BEFORE" "keeping every other field"
assert_equals "$(json_get "$PG/.smns" 'd["hub"]["url"]')" "\"$HUB\"" "with the hub"
assert_contains "$OUT" "no longer synced" "saying its remote is no longer the live path"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub again changes nothing"
assert_contains "$OUT" "already a hub project" "and says so"
run "$SMINOS" project init --hub --name renamed
assert_rc 2 "$RC" "--hub on an existing .smns changes nothing else"
REMOTE_HEAD="$(git -C "$T/archive.git" rev-parse main)"
"$SMINOS" say "after the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: reconciled" "the hub project ticks"
assert_not_contains "$OUT" "gitproj: synced" "with no git phase"
assert_not_contains "$OUT" "hubproj: synced" "nor for the project made a hub project at init"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote is not pushed"
assert_equals "$(test -d "$SMINOS_HOME/projects/$(json_get "$PH/.smns" 'd["project"]' | tr -d '"')/log/.git" && echo git || echo none)" none \
  "a hub project's log is never made a git working tree, though its .smns names a remote"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses a hub project"
assert_contains "$OUT" "syncs through its hub" "saying why"
cd "$T"
mv "$PG" "$PG.moved"
"$SMINOS" say --in gitproj "while its checkout is gone" >/dev/null
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "gitproj: synced" "a hub project whose checkout is gone still gets no git phase"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote still not pushed"
cd "$T"
gitq init -q --bare "$T/archive-n.git"
PN="$T/a/np"
mkdir -p "$PN"
gitq init -q "$PN"
cd "$PN"
"$SMINOS" project init --name nullhub --remote "$T/archive-n.git" >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = None; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PN/.smns"
"$SMINOS" say "under a null hub" >/dev/null 2>&1
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "nullhub: synced" "a .smns whose hub is null gets no git phase"
assert_contains "$OUT" "its hub is not {url, org}" "with a warning"
assert_equals "$(git -C "$T/archive-n.git" rev-parse --verify -q main || echo none)" none "its remote is never pushed"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses it"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "--hub does not overwrite a malformed hub"
assert_contains "$OUT" "fix its .smns by hand" "saying to fix it by hand"
PO="$T/a/op"
mkdir -p "$PO"
gitq init -q "$PO"
cd "$PO"
"$SMINOS" project init --name orgonly >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = {"org": "org-1"}; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PO/.smns"
"$SMINOS" say "under an org-only hub" >/dev/null 2>&1
importable() { # project dir — whether the uplink would import an events frame for it, for org-1
  python3 - "$SCRIPTS" "$1" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import sminos_uplink
pid = json.load(open(os.path.join(sys.argv[2], ".smns")))["project"]
print("imports" if sminos_uplink.hub_project(pid, {"org": "org-1"}) else "refuses")
PY
}
assert_equals "$(importable "$PO" 2>/dev/null)" refuses "the uplink imports nothing into a project whose hub carries only an org"
assert_equals "$(importable "$PH" 2>/dev/null)" imports "and imports into a well-formed hub project of its org"
cd "$T"

# ---- the conversion against a tick that syncs the project through git
# A tick read each project when it began; `project init --hub` may land while
# it waits on the remote. The conversion takes the mirror's sync lock, and
# each git phase reads .smns again under that lock, so what is left of the
# tick neither integrates nor pushes, and no git event enters the hub log.
echo "a conversion during a tick's sync:"
cat > "$T/race.py" <<'PY'
import json, os, subprocess, sys, threading
scripts, root, mode = sys.argv[1:4]
sys.path.insert(0, scripts)
import sminos, sminos_daemon as daemon
project = sminos.resolve_project(root)  # as the tick read it: no hub yet
convert = [os.path.join(scripts, "sminos"), "project", "init", "--hub"]
report = {}
if mode == "held":
    # The tick's fetch waits until the conversion has started and had a second
    # to finish; the tick's delivery waits for the conversion to end, so its
    # push comes after the switch.
    entered, gate, proc = threading.Event(), threading.Event(), []
    real_fetch, real_deliver = daemon.fetch, daemon.deliver_owed
    def held_fetch(log):
        entered.set()
        gate.wait(60)
        real_fetch(log)
    def deliver_after(project_, view):
        proc[0].wait(60)
        return real_deliver(project_, view)
    daemon.fetch, daemon.deliver_owed = held_fetch, deliver_after
    out = {}
    t = threading.Thread(target=lambda: out.update(daemon.tick(project)))
    t.start()
    entered.wait(60)
    proc.append(subprocess.Popen(convert, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said during the held fetch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    try:
        proc[0].wait(1.0)
    except subprocess.TimeoutExpired:
        pass
    report["converted during the fetch"] = proc[0].poll() is not None
    gate.set()
    t.join(120)
    report["tick"] = out
else:  # "stale": the switch landed between the tick's read and its sync of the project
    subprocess.run(convert, cwd=root, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said after the switch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    report["tick"] = daemon.tick(project)
print(json.dumps(report))
PY
other_pushes() { # bare-remote text — another machine's git event, pushed to the remote
  rm -rf "$T/other-clone"
  gitq clone -q "$1" "$T/other-clone" 2>/dev/null
  printf '{"ts": "2026-10-15T00:00:00.000Z", "writer": "other/human", "seq": 1, "kind": "say", "from": "human", "to": "*", "text": "%s"}\n' \
    "$2" > "$T/other-clone/other.human.jsonl"
  gitq -C "$T/other-clone" add other.human.jsonl
  gitq -C "$T/other-clone" commit -qm other
  gitq -C "$T/other-clone" push -q origin HEAD:main
}
mirrored_project() { # name → a checkout under $T/a/<name> of a git-mirrored project, synced once
  gitq init -q --bare "$T/$1.git"
  mkdir -p "$T/a/$1"
  gitq init -q "$T/a/$1"
  cd "$T/a/$1"
  "$SMINOS" project init --name "$1" --remote "$T/$1.git" >/dev/null
  "$SMINOS" say "before the switch" >/dev/null
  run "$SMINOS" daemon tick
  assert_contains "$OUT" "$1: synced" "$1 syncs through git before the switch"
  cd "$T"
}
log_of() { echo "$SMINOS_HOME/projects/$(json_get "$T/a/$1/.smns" 'd["project"]' | tr -d '"')/log"; }
as a alpha
mirrored_project heldproj
HELD_HEAD="$(git -C "$T/heldproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/heldproj" held
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["converted during the fetch"])')" \
  False "a conversion started while a tick fetches waits for that sync to end"
assert_equals "$(json_get "$T/a/heldproj/.smns" 'd["hub"]["url"]')" "\"$HUB\"" "then converts the project"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["tick"]["pushed"])')" \
  False "the rest of the tick, after the switch, pushes nothing"
assert_equals "$(git -C "$T/heldproj.git" rev-parse main)" "$HELD_HEAD" "the remote is where it was"
assert_contains "$(cat "$(log_of heldproj)/alpha.human.jsonl")" "said during the held fetch" \
  "though the log holds what was said meanwhile"
mirrored_project staleproj
STALE_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
other_pushes "$T/staleproj.git" "a git event after the switch"
OTHER_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/staleproj" stale
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; t = json.load(sys.stdin)["tick"]; print([t["integrated"], t["pushed"]])')" \
  "[False, False]" "a tick that read the project before the switch neither integrates nor pushes it after"
assert_equals "$(test -e "$(log_of staleproj)/other.human.jsonl" && echo there || echo none)" none \
  "no git event enters the hub project's log"
assert_equals "$(git -C "$T/staleproj.git" rev-parse main)" "$OTHER_HEAD" "nothing of this machine is pushed"
[[ "$OTHER_HEAD" != "$STALE_HEAD" ]] || fail "the other machine's push moved the remote"
cd "$T"
as b2 beta2
P0="$T/b2/p"
mkdir -p "$P0"
gitq init -q "$P0"
cd "$P0"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "project init --hub on a machine not enrolled is refused"
assert_contains "$OUT" "sminos hub enroll" "saying to enroll first"
assert_equals "$(test -e "$P0/.smns" && echo there || echo none)" none "and writes no .smns"
cd "$T"

# ---- no secret anywhere
echo "secrets:"
SECRETS="$(python3 - "$T" <<'PY'
import glob, json, sys
for p in glob.glob(sys.argv[1] + "/*/s/daemon/hub.json"):
    print(json.load(open(p))["client_secret"])
PY
)"
for f in "$T"/*/s/daemon.log "$T/all.out"; do
  [ -f "$f" ] || continue
  assert_not_contains "$(cat "$f")" "$KEY" "the org key is not in ${f#"$T"/}"
  while IFS= read -r c; do
    if grep -Fq -- "$c" "$f"; then fail "an enrollment code is in ${f#"$T"/}"; echo "    ${c:0:40}…"; fi
  done < "$T/codes"
  for s in $SECRETS; do
    assert_not_contains "$(cat "$f")" "$s" "no service token secret is in ${f#"$T"/}"
  done
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES hub assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) hub assertions FAILED"
  exit 1
fi
