#!/usr/bin/env bash
#
# The archive of a hub project (DC4 M4 of the desk): two machines simulated on
# one Mac — two SMINOS_HOMEs, two enrolled names, alpha and beta — each with
# its `daemon run` and its uplink, against hub_standin.py, the project's
# remote a bare git repository. Pins DC4.G3: the machine the hub designates
# (DX2's `have.archive`) writes the log to the remote on schedule, from a
# clone outside log/, each writer file of another machine copied whole as
# imported — the codes and the holes of spent positions kept — and its own up
# to the hub's vector in the `have` that confirmed the run; no other machine
# pushes it; a machine whose
# designation moves stops at its next schedule, and with none nobody pushes;
# what the remote holds never reaches the log (files the log lacks stay as the
# remote has them, and the log's copy wins over a writer file edited there);
# a push the remote rejected because it moved is retried from a fresh fetch.
# On DX2, a position the hub's policy registry could not check goes up again
# after the wait, with no reconnect and no further write (P5 O18 D5). On RL10
# (a third machine, gamma, cut over to endpoint_standin.py), the archive is
# the hub-admitted public projection (P5 O18 D6): no audience stream; an own
# event the endpoint's socket took but the hub has not admitted is not in it,
# though `taken` covers it; a position the hub withheld is its tombstone,
# whether the refusal reached the machine or was lost to a dropped
# connection; and a position refused `audience` here and voided since is a
# tombstone too, never the body the local file keeps.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/sma.XXXXXX)"
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
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST
# The archive's schedule: every 2 seconds here (15 minutes by default).
# A position the hub could not check goes up again 1.5 s after (30 s by default).
export SMINOS_DERIVE_EVERY=0 SMINOS_ARCHIVE_EVERY=2 SMINOS_ASK_MS=1500 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
as() { # a|b host — one machine: its HOME, its SMINOS_HOME, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = agents ] && { cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; }
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-0 secret-0 1000 & PIDS+=("$!")
until_true 100 test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"
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
elif cmd == "inject":  # project events-json
    call("POST", "/control/inject", {"project": args[0], "events": json.loads(args[1])})
elif cmd == "archive":  # project machine|null
    call("POST", "/control/archive", {"project": args[0], "machine": None if args[1] == "null" else args[1]})
elif cmd == "vector":  # project writer
    print(call("GET", "/control/state")[1]["projects"].get(args[0], {}).get("vector", {}).get(args[1], 0))
elif cmd == "policies":  # available(true|false) [rows-json]
    call("POST", "/control/policies", {"available": args[0] == "true", **({"rows": json.loads(args[1])} if args[1:] else {})})
elif cmd == "gen":  # machine — its current stream's generation
    print(call("GET", "/control/state")[1]["generations"].get(args[0], 0))
elif cmd == "stored":  # project writer seq — the event the hub holds there, as JSON
    evs = call("GET", "/control/state")[1]["projects"].get(args[0], {}).get("writers", {}).get(args[1], [])
    print(json.dumps(next((e for e in evs if e["seq"] == int(args[2])), None)))
elif cmd == "refusals":  # project reason — how many refusals of that reason its audit holds
    print(sum(1 for r in call("GET", "/control/state")[1]["projects"].get(args[0], {}).get("audit", [])
              if r.get("kind") == "refused" and r.get("reason") == args[1]))
elif cmd == "hellos":  # machine — the most projects one POST of its said hello to, and how many it said hello to
    sets = []
    for p in call("GET", "/control/state")[1]["posted"]:
        if p["machine"] == args[0]:
            pids = {f.get("project") for f in (json.loads(l) for l in p["body"].split("\n") if l.strip()) if f.get("t") == "hello"}
            sets += [pids] if pids else []
    print(max(map(len, sets), default=0), len(set().union(*sets)))
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }

# A web human as the hub holds it: sealed with the org key, or with another (a forgery).
cat > "$T/human.py" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
variant, seq, text, member = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
key = bytes(range(32)) if variant == "ok" else bytes([0xff] * 32)
draft = {"kind": "human", "from": "human", "member": member, "to": "*", "text": text, "created": ts}
print(json.dumps([{"ts": ts, "writer": "hub/" + member, "seq": seq,
                   **codes.seal(key, "log", os.environ["PID"], draft, codes.b64url(os.urandom(16)))}]))
PY
human() { python3 "$T/human.py" "$@" "$MEMBER"; }

start_daemon() { # → DAEMON_PID (of the machine `as` named last)
  "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & DAEMON_PID=$!
  PIDS+=("$DAEMON_PID")
}
BARE="$T/archive.git"
gitq init -q --bare "$BARE"
on_remote() { git -C "$BARE" rev-parse --verify -q main >/dev/null 2>&1; }
# Every file of a machine's log as the remote's main holds it, byte for byte.
archive_is() { # log-dir — the remote's main holds each of its writer files exactly
  local f
  on_remote || return 1
  for f in "$1"/*.jsonl; do
    cmp -s "$f" <(git -C "$BARE" show "main:$(basename "$f")" 2>/dev/null) || return 1
  done
}
committers() { git -C "$BARE" log --format=%ce main 2>/dev/null | sort | uniq -c | awk '{print $2 "=" $1}' | tr '\n' ' '; }
commits_by() { git -C "$BARE" log --format=%ce main 2>/dev/null | grep -c "^sminos@$1\$" || true; }
# The designation the uplink recorded for the project, and when the hub last said it.
designation() { # side → "true 1760000000.1" | "false …" | "none"
  python3 - "$T/$1/s/projects/$PID/uplink.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    d = {}
print("%s %s" % (str(d["archive"]).lower(), d.get("archive_at")) if "archive" in d else "none")
PY
}
designated_as() { [ "$(designation "$1" | cut -d' ' -f1)" = "$2" ]; }
confirmed_after() { # side epoch — the hub answered a hello for the project after epoch
  python3 -c 'import sys; v = sys.argv[1].split(); sys.exit(0 if len(v) == 2 and v[1] != "None" and float(v[1]) > float(sys.argv[2]) else 1)' \
    "$(designation "$1")" "$2"
}
confirmations() { # side n — wait until the hub has answered n more hellos for the project
  local i at
  for i in $(seq 1 "$2"); do
    at="$(python3 -c 'import time; print(time.time())')"
    until_true 200 confirmed_after "$1" "$at" || return 1
  done
}

# ---- alpha and beta: enrolled, one hub project whose remote is the bare repository
echo "two machines, one hub project:"
as a alpha
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
RA="$T/a/repo"
mkdir -p "$RA"
gitq init -q "$RA"
cd "$RA"
"$SMINOS" project init --name archproj --hub --remote "$BARE" >/dev/null
PID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RA/.smns")"
export PID
ALOG="$T/a/s/projects/$PID/log"
BLOG="$T/b/s/projects/$PID/log"
start_daemon
A_DAEMON=$DAEMON_PID
for i in 1 2 3; do "$SMINOS" say "alpha $i" >/dev/null; done
as b beta
RB="$T/b/repo"
cp -R "$RA" "$RB"
cd "$RB"
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")" >/dev/null
start_daemon
B_DAEMON=$DAEMON_PID
for i in 1 2 3; do "$SMINOS" say "beta $i" >/dev/null; done
# A web human, a forgery the hub stored after it (refused on both machines: its
# position spent, a hole in the file), and another web human after the hole.
ctl inject "$PID" "$(human ok 1 "from the web 1")"
ctl inject "$PID" "$(human forged 2 "forged")"
ctl inject "$PID" "$(human ok 3 "from the web 3")"
seqs() { python3 -c 'import json, sys; print(",".join(str(json.loads(l)["seq"]) for l in open(sys.argv[1]) if l.strip()))' "$1" 2>/dev/null; }
holds() { [ "$(seqs "$1/hub.$MEMBER.jsonl")" = "1,3" ] && grep -q '"beta 3"' "$1/beta.human.jsonl" 2>/dev/null \
  && grep -q '"alpha 3"' "$1/alpha.human.jsonl" 2>/dev/null; }
until_true 300 holds "$ALOG" || true
until_true 300 holds "$BLOG" || true
if holds "$ALOG" && holds "$BLOG"; then pass "each machine holds both machines' says and the web humans, hub/<member> at 1 and 3 (2 spent)"; else
  fail "each machine holds both machines' says and the web humans"; fi

# ---- no designation: nobody pushes
echo "no machine designated:"
confirmations a 2 || true
confirmations b 2 || true
assert_equals "$(designation a | cut -d' ' -f1) $(designation b | cut -d' ' -f1)" "false false" \
  "each uplink records the hub's answer: not this machine's archive"
assert_equals "$(on_remote && echo pushed || echo empty)" empty "with no machine designated, two confirmations later nothing is pushed"
assert_equals "$(ls -d "$T"/[ab]/s/projects/"$PID"/archive 2>/dev/null | wc -l | tr -d ' ')" 0 "and no archive clone is made"
read -r most opened <<<"$(ctl hellos alpha)"
assert_equals "$most" 1 "each confirmation posts one project's hello per POST, as the handshake does (the hub fails a POST of many)"
if [ "$opened" -ge 2 ]; then pass "alpha confirms $opened projects"; else fail "alpha confirms more than one project (it confirmed $opened)"; fi

# ---- alpha designated
echo "alpha designated:"
ctl archive "$PID" alpha
until_true 200 designated_as a true || true
assert_equals "$(designation a | cut -d' ' -f1)" true "alpha's uplink learns it is the archive machine at its next hello, without a reconnect"
until_true 300 archive_is "$ALOG" || true
if archive_is "$ALOG"; then pass "alpha writes its log to the remote, every writer file byte for byte"; else
  fail "alpha writes its log to the remote"; git -C "$BARE" ls-tree --name-only main 2>&1 | head || true; fi
assert_equals "$(git -C "$BARE" show "main:hub.$MEMBER.jsonl" | python3 -c 'import json, sys
print([(e["seq"], "mac" in e) for e in map(json.loads, sys.stdin)])')" "[(1, True), (3, True)]" \
  "the archive keeps the hole of the spent position, and each imported event's code"
assert_equals "$(git -C "$BARE" show main:beta.human.jsonl | python3 -c 'import json, sys
print(sorted({"mac" in e for e in map(json.loads, sys.stdin)}))')" "[True]" "beta's events, as alpha imported them, keep their codes"
assert_equals "$(test -d "$T/a/s/projects/$PID/archive/.git" && echo clone)" clone "from a clone at the project's home, archive/"
assert_equals "$(test -e "$ALOG/.git" && echo git || echo none)" none "outside log/, which is no git working tree"
assert_equals "$(committers)" "sminos@alpha=$(commits_by alpha) " "every commit on the remote is alpha's"
assert_equals "$(test -d "$T/b/s/projects/$PID/archive" && echo clone || echo none)" none "beta makes no archive clone"
(cd "$RA" && as a alpha && "$SMINOS" say "alpha later" >/dev/null)
until_true 300 archive_is "$ALOG" || true
if archive_is "$ALOG" && git -C "$BARE" show main:alpha.human.jsonl | grep -q "alpha later"; then
  pass "a later say reaches the remote at a later run"; else fail "a later say reaches the remote at a later run"; fi
N=$(commits_by alpha)
confirmations a 2 || true
assert_equals "$(commits_by alpha)" "$N" "a run with nothing new to archive commits nothing"

# ---- the remote is never read into the log
echo "git never feeds the live log:"
gitq clone -q "$BARE" "$T/stranger"
printf '%s\n' '{"ts":"2026-10-15T00:00:00.000Z","writer":"stranger/x","seq":1,"kind":"say","from":"x","to":"*","text":"from git"}' \
  > "$T/stranger/stranger.x.jsonl"
printf '%s\n' '{"ts":"2026-10-15T00:00:00.000Z","writer":"alpha/human","seq":99,"kind":"say","from":"x","to":"*","text":"edited in git"}' \
  >> "$T/stranger/alpha.human.jsonl"
gitq -C "$T/stranger" add -A
gitq -C "$T/stranger" commit -q -m "a stranger's commit"
gitq -C "$T/stranger" push -q origin HEAD:main
STRANGER="$(git -C "$T/stranger" rev-parse HEAD)"
(cd "$RA" && as a alpha && "$SMINOS" say "alpha after the stranger" >/dev/null)
archived_after_stranger() { git -C "$BARE" show main:alpha.human.jsonl 2>/dev/null | grep -q "alpha after the stranger"; }
until_true 300 archived_after_stranger || true
until_true 100 archive_is "$ALOG" || true
if archive_is "$ALOG"; then pass "alpha's next run copies its log over the remote's, its writer file as the log holds it"; else
  fail "alpha's next run copies its log over the remote's"; fi
assert_not_contains "$(git -C "$BARE" show main:alpha.human.jsonl)" "edited in git" "the line edited in git is gone from the archive"
assert_equals "$(git -C "$BARE" show main:stranger.x.jsonl)" \
  '{"ts":"2026-10-15T00:00:00.000Z","writer":"stranger/x","seq":1,"kind":"say","from":"x","to":"*","text":"from git"}' \
  "a file the log lacks stays as the remote has it"
assert_equals "$(git -C "$BARE" merge-base --is-ancestor "$STRANGER" main && echo kept)" kept \
  "built on the remote's main: the stranger's commit stays in the history (no force)"
assert_equals "$(ls "$ALOG"/stranger* "$BLOG"/stranger* 2>/dev/null | wc -l | tr -d ' ')" 0 "no machine's log holds the stranger's file"
assert_not_contains "$(cat "$ALOG"/*.jsonl "$BLOG"/*.jsonl)" "edited in git" "nor the line edited in git"

# ---- a remote that would steer the copy: a symlink out of the clone, an ignore rule, conversions
echo "a remote that would steer the copy:"
gitq -C "$T/stranger" fetch -q origin
gitq -C "$T/stranger" reset -q --hard origin/main
rm "$T/stranger/alpha.human.jsonl"
ln -s ../log/beta.human.jsonl "$T/stranger/alpha.human.jsonl"   # from the archive clone: alpha's live beta writer
printf '*.jsonl\n' > "$T/stranger/.gitignore"
printf '*.jsonl ident text eol=crlf\n' > "$T/stranger/.gitattributes"
gitq -C "$T/stranger" add -A
gitq -C "$T/stranger" commit -q -m "a remote that would steer the copy"
gitq -C "$T/stranger" push -q origin HEAD:main
cp "$ALOG/beta.human.jsonl" "$T/beta-before"
# shellcheck disable=SC2016 # the dollar signs are the ident attribute's keyword, written as they are
(cd "$RA" && as a alpha && "$SMINOS" say 'ident probe $Id: kept as written $' >/dev/null)
(cd "$RA" && as a alpha && python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
sminos.log_append(sminos.resolve_project(os.getcwd()), "alpha/late-feed", "say", **{"from": "human", "to": "*", "text": "a writer file new after the ignore rule"})
PY
)
steered() { git -C "$BARE" cat-file -e main:alpha.late-feed.jsonl 2>/dev/null \
  && git -C "$BARE" show main:alpha.human.jsonl 2>/dev/null | grep -q "ident probe"; }
until_true 300 steered || true
assert_equals "$(cmp -s "$T/beta-before" "$ALOG/beta.human.jsonl" && echo unchanged)" unchanged \
  "the live log is unchanged: nothing was written through the remote's symlink"
assert_equals "$(git -C "$BARE" ls-tree main alpha.human.jsonl | cut -c1-6)" 100644 "the writer file is a regular file in the archive again"
until_true 100 archive_is "$ALOG" || true
if archive_is "$ALOG"; then pass "every writer file byte for byte, the remote's .gitattributes (ident, text, eol) notwithstanding"; else
  fail "every writer file byte for byte, the remote's .gitattributes notwithstanding"; fi
# shellcheck disable=SC2016
assert_contains "$(git -C "$BARE" show main:alpha.human.jsonl)" 'ident probe $Id: kept as written $' "the ident keyword kept as the log holds it"
assert_contains "$(git -C "$BARE" show main:alpha.late-feed.jsonl 2>&1)" "a writer file new after the ignore rule" \
  "a writer file the remote's .gitignore covers is archived all the same"
assert_equals "$(git -C "$BARE" show main:.gitignore) | $(git -C "$BARE" show main:.gitattributes)" \
  "*.jsonl | *.jsonl ident text eol=crlf" "the remote's own files stay as the remote has them"

# ---- the designation moves to beta
echo "the designation moves to beta:"
ctl archive "$PID" beta
until_true 200 designated_as a false || true
assert_equals "$(designation a | cut -d' ' -f1)" false "alpha learns it no longer is, at its next hello"
until_true 200 designated_as b true || true
by_beta() { [ "$(commits_by beta)" -ge 1 ]; }
until_true 300 by_beta || true
assert_equals "$(by_beta && echo yes)" yes "beta writes the archive"
assert_equals "$(git -C "$BARE" merge-base --is-ancestor "$STRANGER" main && echo kept)" kept "on top of the history alpha wrote"
# A run alpha began before it learned may still land: from here on, nothing more.
sleep 3
N=$(commits_by alpha)
(cd "$RA" && as a alpha && "$SMINOS" say "alpha after the move" >/dev/null)
moved() { git -C "$BARE" show main:alpha.human.jsonl 2>/dev/null | grep -q "alpha after the move"; }
until_true 300 moved || true
assert_equals "$(moved && echo yes)" yes "alpha's later say reaches the archive"
until_true 100 archive_is "$BLOG" || true
if archive_is "$BLOG"; then pass "as beta's log holds it"; else fail "as beta's log holds it"; fi
confirmations a 2 || true
assert_equals "$(commits_by alpha)" "$N" "alpha, no longer designated, pushes nothing at its next schedules"
assert_equals "$(git -C "$BARE" log -1 --format=%ce main)" "sminos@beta" "the archive's latest commit is beta's"

# ---- no machine designated again
echo "the designation cleared:"
ctl archive "$PID" null
until_true 200 designated_as b false || true
sleep 3
HEAD_BEFORE="$(git -C "$BARE" rev-parse main)"
(cd "$RB" && as b beta && "$SMINOS" say "beta after the clearing" >/dev/null)
confirmations a 2 || true
confirmations b 2 || true
assert_equals "$(git -C "$BARE" rev-parse main)" "$HEAD_BEFORE" "with the designation cleared, nobody pushes"

# ---- a position the hub's policy registry could not check (P5 O18 D5)
echo "a position the hub could not check, on a direct stream:"
DSID=6e000001-0000-4000-8000-0000000000d1
ctl policies true "{\"$DSID\": {\"machine\": \"delta\"}}"   # a session another machine exposed
GEN="$(ctl gen alpha)"
ctl policies false
ASEQ="$(cd "$RA" && as a alpha && python3 - "$DSID" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
e = sminos.log_append(sminos.resolve_project(os.getcwd()), "alpha/human", "say",
                      **{"from": "human", "to": [{"session": sys.argv[1], "alias": "d"}], "text": "to a session the registry checks"})
print(e["seq"])
PY
)"
refused_unavailable() { [ "$(ctl refusals "$PID" state-unavailable)" -ge 1 ]; }
until_true 200 refused_unavailable || true
assert_equals "$(refused_unavailable && echo yes)" yes "the hub refuses an event naming a session state-unavailable while its registry cannot be read"
assert_equals "$(ctl stored "$PID" alpha/human "$ASEQ")" null "and stores nothing at its position"
ctl policies true
landed() { ctl stored "$PID" alpha/human "$ASEQ" | grep -q "to a session the registry checks"; }
until_true 200 landed || true
assert_equals "$(landed && echo yes)" yes "once it can be read, the event lands, with no further write"
assert_equals "$(ctl gen alpha)" "$GEN" "and no reconnect: on the same stream"
assert_contains "$(cat "$T/a/s/daemon.log")" "alpha/human of archproj goes up again from $ASEQ, which the hub could not check" \
  "the retry, said in daemon.log"

kill "$A_DAEMON" "$B_DAEMON"
set +e; wait "$A_DAEMON" "$B_DAEMON"; set -e
for side in a b; do
  assert_not_contains "$(cat "$T/$side/s/daemon.log")" "Traceback" "nothing in $side's daemon.log is a traceback"
done

# ---- a push the remote rejected because it moved
echo "a push rejected because the remote moved:"
as b beta
cd "$RB"
OUT="$(python3 - "$T/stranger" <<'PY'
import os, subprocess, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_archive as archive, sminos_hublog as hublog
stranger = sys.argv[1]
project = sminos.resolve_project(os.getcwd())
e = sminos.log_append(project, "beta/human", "say", **{"from": "human", "to": "*", "text": "beta, raced"})
# The hub's have that confirms the run admits it (the archive copies an own writer up to that vector alone).
hublog.HubLog(project, {"key": bytes(range(32)), "machine": "beta"}).on_have(
    {"have": {"beta/human": e["seq"]}, "archive": True})
real, raced, answers = archive.push_once, [], []

def push_once(clone):
    # Between the fetch of this run and its push, another writer moves the remote.
    if not raced:
        raced.append(1)
        for args in (["fetch", "-q", "origin"], ["reset", "-q", "--hard", "origin/main"]):
            subprocess.run(["git", "-C", stranger, *args], check=True)
        with open(os.path.join(stranger, "stranger.x.jsonl"), "a") as f:
            f.write('{"ts":"2026-10-15T00:00:01.000Z","writer":"stranger/x","seq":2,"kind":"say","from":"x","to":"*","text":"raced"}\n')
        for args in (["add", "-A"], ["commit", "-q", "-m", "a race"], ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", stranger, *args], check=True)
    p = real(clone)
    answers.append("rejected" if p.returncode else "pushed")
    return p

archive.push_once = push_once
print("%s: %s" % ("pushed" if archive.run(project) else "nothing", " then ".join(answers)))
PY
)" || true
assert_equals "$OUT" "pushed: rejected then pushed" "the push the remote rejected is retried from a fresh fetch, and lands"
assert_contains "$(git -C "$BARE" show main:stranger.x.jsonl)" '"text":"raced"' "keeping the commit that raced it"
assert_contains "$(git -C "$BARE" show main:beta.human.jsonl)" "beta, raced" "with beta's log on top"

# ---- a hello repeated on an open stream refreshes the designation, and leaves the upload as it was
echo "a repeated hello:"
assert_equals "$(python3 - <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_hublog as hublog
hl = hublog.HubLog(sminos.resolve_project(os.getcwd()), {"key": bytes(range(32)), "machine": "beta"})
hl.on_have({"have": {"beta/human": 5, "alpha/human": 9}, "archive": False})
opened = [dict(hl.sent), sorted(hl.stuck)]
hl.stuck.add("beta/human")  # the hub refused it on this stream
hl.on_have({"have": {"beta/human": 3}, "archive": True})  # an older vector, answering a repeated hello
refreshed = [dict(hl.sent), sorted(hl.stuck), hl.archive]
hl.on_have({"have": {"beta/human": 7}, "archive": True})
ahead = dict(hl.sent)
hl.reset()  # a new stream
hl.on_have({"have": {"beta/human": 3}, "archive": False})
print(json.dumps([opened, refreshed, ahead, [dict(hl.sent), sorted(hl.stuck)]]))
PY
)" '[[{"beta/human": 5}, []], [{"beta/human": 5}, ["beta/human"], true], {"beta/human": 7}, [{"beta/human": 3}, []]]' \
  "its have moves what the hub holds only forward and keeps a refused writer stopped; a new stream starts both over"

# ---- RL10: the hub-admitted public projection (P5 O18 D6)
# gamma, cut over to its endpoint stand-in, which answers each hello with the
# hub's `have` as the endpoint passes it down: its archive designation, its
# vector (`admit` off holds the hub's admission back: an upload the socket
# took counts in no vector), its withheld positions.
echo "RL10, the archive machine's endpoint holding back the hub's admission:"
as c gamma
export MAWS_USER_DATA="$T/c/maws"
EPDIR="$MAWS_USER_DATA/mawsd/endpoint"
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" gamma "$KEY")" >/dev/null
RC="$T/c/repo"
BARE2="$T/rl10-archive.git"
gitq init -q --bare "$BARE2"
mkdir -p "$RC"
gitq init -q "$RC"
cd "$RC"
"$SMINOS" project init --name rlarch --hub --remote "$BARE2" >/dev/null
PID2="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RC/.smns")"
CLOG="$T/c/s/projects/$PID2/log"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPDIR" "{\"identity\": {\"org\": \"org-1\", \"hub\": \"$HUB\", \"name\": \"gamma\", \"former\": [], \"ref\": \"ref-gamma\", \"enrolled\": \"2026-11-05T00:00:00.000Z\"}, \"archive\": true}" &
PIDS+=("$!")
until_true 100 test -S "$EPDIR/ctl.sock"
ep() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPDIR" "$@" >/dev/null; }
epq() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPDIR" state \
  | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
start_daemon
C_DAEMON=$DAEMON_PID
opened_rl10() { [ "$(epq "any(f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$PID2' for f in d['received'])")" = true ]; }
until_true 300 opened_rl10 || true
assert_equals "$(opened_rl10 && echo yes)" yes "gamma is cut over, and opens the project on the endpoint's socket"
gsay() { (cd "$RC" && "$SMINOS" say "$1" >/dev/null); }
GW=gamma.human.jsonl
on_remote2() { git -C "$BARE2" show "main:$GW" 2>/dev/null; }
archived2() { on_remote2 | grep -Fq -- "$1"; }
seq_of() { python3 -c 'import json, sys; print(max((json.loads(l)["seq"] for l in open(sys.argv[1]) if sys.argv[2] in l), default=0))' "$CLOG/$GW" "$1"; }
taken_to() { python3 -c 'import json, sys
try: print(json.load(open(sys.argv[1])).get("taken", {}).get("gamma/human", 0))
except (OSError, ValueError): print(0)' "$T/c/s/projects/$PID2/uplink-taken.json"; }
taken_past() { [ "$(taken_to)" -ge "$1" ]; }
# An archive run that started after `epoch` and has finished (daemon.json's archive record).
run_after() { python3 -c 'import json, sys
try: a = json.load(open(sys.argv[1])).get("archive") or {}
except (OSError, ValueError): a = {}
sys.exit(0 if float(a.get("started") or 0) > float(sys.argv[2]) and ("pushed" in a or "error" in a) else 1)' \
  "$T/c/s/projects/$PID2/daemon.json" "$1"; }
tombstone_at() { on_remote2 | grep -Fqx -- "{\"writer\": \"gamma/human\", \"seq\": $1, \"withheld\": true}"; }

gsay "gamma, admitted"
# An operator stream: a writer of its own for an audience, which the archive never takes.
(cd "$RC" && python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
sminos.log_append(sminos.resolve_project(os.getcwd()), "gamma/human~" + sminos.audience_digest(["4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c"]),
                  "say", **{"from": "human", "to": "*", "text": "gamma, to an audience"})
PY
)
until_true 300 archived2 "gamma, admitted" || true
assert_equals "$(archived2 "gamma, admitted" && echo yes)" yes "an event the hub admitted reaches the archive"
assert_equals "$(ls "$CLOG"/*~*.jsonl | wc -l | tr -d ' ')" 1 "the log holds an audience stream"
assert_equals "$(git -C "$BARE2" ls-tree --name-only main | tr '\n' ' ')" "$GW " \
  "the commit holds the plain writer's file and no stream file"

ep set '{"admit": false}'
gsay "gamma, held back"
HELD="$(seq_of "gamma, held back")"
until_true 200 taken_past "$HELD" || true
assert_equals "$(taken_past "$HELD" && echo taken)" taken "the endpoint's socket took it: taken covers it"
AT="$(python3 -c 'import time; print(time.time())')"
until_true 300 run_after "$AT" || true
assert_equals "$(run_after "$AT" && echo ran)" ran "an archive runs after"
assert_not_contains "$(on_remote2)" "gamma, held back" "and does not hold it: the hub has not admitted it"
ep refuse "{\"project\": \"$PID2\", \"writer\": \"gamma/human\", \"seq\": $HELD}"
ep set "{\"withheld\": {\"$PID2\": {\"gamma/human\": [$HELD]}}, \"admit\": true}"
until_true 300 tombstone_at "$HELD" || true
assert_equals "$(tombstone_at "$HELD" && echo yes)" yes "after the hub's refusal and the next have, the archive holds its tombstone"
assert_not_contains "$(on_remote2)" "gamma, held back" "and not the body"
assert_contains "$(cat "$CLOG/$GW")" "gamma, held back" "which the local file keeps"

echo "  a refusal lost to a dropped connection:"
ep set '{"admit": false}'
gsay "gamma, its refusal lost"
LOST="$(seq_of "gamma, its refusal lost")"
until_true 200 taken_past "$LOST" || true
CONNS="$(epq 'd["conns"]')"
# The hub withholds it; the connection drops before any refusal reaches the machine.
ep set "{\"withheld\": {\"$PID2\": {\"gamma/human\": [$HELD, $LOST]}}, \"admit\": true}"
ep drop
reconnected() { [ "$(epq 'd["conns"]')" -gt "$CONNS" ] && [ "$(epq 'd["connected"]')" = true ]; }
until_true 300 reconnected || true
assert_equals "$(reconnected && echo yes)" yes "gamma reconnects"
until_true 300 tombstone_at "$LOST" || true
assert_equals "$(tombstone_at "$LOST" && echo yes)" yes "with no further write, the next archive holds the tombstone the have lists"
assert_not_contains "$(on_remote2)" "gamma, its refusal lost" "and not the body"

echo "  a position refused audience here, voided since:"
ep set '{"refuse_audience": ["gamma/human"]}'
gsay "gamma, a stale audience"
STALE="$(seq_of "gamma, a stale audience")"
dead_here() { python3 -c 'import json, sys; sys.exit(0 if "gamma/human" in json.load(open(sys.argv[1])).get("dead", {}) else 1)' \
  "$T/c/s/projects/$PID2/uplink.json" 2>/dev/null; }
until_true 200 dead_here || true
assert_equals "$(dead_here && echo dead)" dead "an audience refusal stops the writer, kept in uplink.json"
ep set '{"refuse_audience": []}'
gsay "gamma, current again"
voided_up() { [ "$(epq "any(e == {'ts': e.get('ts'), 'writer': 'gamma/human', 'seq': $STALE, 'kind': 'void', 'of': $STALE} for f in d['received'] if f['frame'].get('t') == 'events' for e in f['frame']['events'])")" = true ]; }
until_true 200 voided_up || true
assert_equals "$(voided_up && echo yes)" yes "an event written to it again revives it: a content-free void goes up at the refused position"
until_true 300 archived2 "gamma, current again" || true
assert_equals "$(archived2 "gamma, current again" && echo yes)" yes "the rest of the writer reaches the archive"
assert_equals "$(tombstone_at "$STALE" && echo yes)" yes "the voided position is its tombstone there"
assert_not_contains "$(on_remote2)" "gamma, a stale audience" "never the refused body"
assert_contains "$(cat "$CLOG/$GW")" "gamma, a stale audience" "which the local file keeps"
assert_equals "$(git -C "$BARE2" ls-tree --name-only main | grep -c '~' || true)" 0 "still no stream file"
kill "$C_DAEMON"
set +e; wait "$C_DAEMON"; set -e
assert_not_contains "$(cat "$T/c/s/daemon.log")" "Traceback" "nothing in gamma's daemon.log is a traceback"

# ---- RL10: the archive's designation, git never feeding the log, steering
# Re-proves on RL10 the DX2 cases above, from "no machine designated" to "the
# designation cleared", with the push raced and the repeated hello's
# in-process twins (uncoded) after them. One machine, delta, cut over to its
# endpoint stand-in by its identity.json alone: no hub enrollment, no
# hub.json, nothing of hub_standin. Its designation is the stand-in's
# `archive`, sent in each `have`; another machine's events (beta's says, the
# web humans, the hole of a position the endpoint spent) come down as RL10
# arrivals. Unported, being DX2's alone: the imported events' codes, one
# hello per POST, the direct stream's `state-unavailable` retry; and, on one
# machine, the other machine's half of each case (beta's clone, beta's push).
echo "RL10, the designation from the endpoint's have:"
as d delta
export MAWS_USER_DATA="$T/d/maws"
EPD="$MAWS_USER_DATA/mawsd/endpoint"
DID='{"org": "org-1", "hub": "http://127.0.0.1:9", "name": "delta", "former": [], "ref": "ref-delta", "enrolled": "2026-11-05T00:00:00.000Z"}'
# Cut over as a welcome leaves a machine: daemon/identity.json, the stand-in's
# identity (the same enrolment, so nothing waits for a head, #147).
mkdir -p "$SMINOS_HOME/daemon"
chmod 700 "$SMINOS_HOME" "$SMINOS_HOME/daemon"
python3 - "$SMINOS_HOME/daemon/identity.json" "$DID" <<'PY'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({**json.loads(sys.argv[2]), "former": {}, "cutover": "2026-11-05T00:00:01.000Z", "build": "b"}, f)
os.chmod(sys.argv[1], 0o600)
PY
RD="$T/d/repo"
BARE3="$T/rl10-designated.git"
gitq init -q --bare "$BARE3"
mkdir -p "$RD"
gitq init -q "$RD"
cd "$RD"
"$SMINOS" project init --name rldesig --hub --remote "$BARE3" >/dev/null
PID3="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RD/.smns")"
DLOG="$T/d/s/projects/$PID3/log"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPD" "{\"identity\": $DID, \"archive\": false, \"ask_legacy\": false}" &
PIDS+=("$!")
until_true 100 test -S "$EPD/ctl.sock"
ep_d() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPD" "$@" >/dev/null; }
epq_d() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPD" state \
  | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
# The frames the endpoint sends down for another machine's events: beta's
# says, and the web humans of $MEMBER at 1 and 3 with 2 spent between (the
# endpoint refused it for good: RL10's `spent`, where DX2 stored a forgery
# each machine refused). Each event wrapped {event, signer}, as it arrives.
cat > "$T/arrivals.py" <<'PY'
import json, sys, time
project, member = sys.argv[1], sys.argv[2]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
beta = {"kind": "machine", "ref": "ref-beta", "name": "beta", "keyId": "k-beta"}
device = {"kind": "device", "member": member, "device": "dev-1", "keyId": "k-dev-1"}
def human(seq, text):
    return {"event": {"ts": ts, "writer": "hub/" + member, "seq": seq, "kind": "human", "from": "human",
                      "member": member, "to": "*", "text": text}, "signer": device}
says = [{"event": {"ts": ts, "writer": "beta/human", "seq": i, "kind": "say", "from": "human", "to": "*",
                   "text": "beta %d" % i}, "signer": beta} for i in (1, 2, 3)]
print(json.dumps({"frames": [
    {"t": "events", "project": project, "events": says},
    {"t": "events", "project": project, "events": [human(1, "from the web 1")]},
    {"t": "spent", "project": project, "writer": "hub/" + member, "seq": 2, "reason": "bad-signature"},
    {"t": "events", "project": project, "events": [human(3, "from the web 3")]}]}))
PY
start_daemon
D_DAEMON=$DAEMON_PID
opened_d() { [ "$(epq_d "any(f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$PID3' for f in d['received'])")" = true ]; }
until_true 300 opened_d || true
assert_equals "$(opened_d && echo yes)" yes "delta, cut over by its identity.json alone, opens the project on the endpoint's socket"
for i in 1 2 3; do "$SMINOS" say "delta $i" >/dev/null; done
ep_d send "$(python3 "$T/arrivals.py" "$PID3" "$MEMBER")"
d_seqs() { python3 -c 'import json, sys; print(",".join(str(json.loads(l)["seq"]) for l in open(sys.argv[1]) if l.strip()))' "$1" 2>/dev/null; }
d_holds() { [ "$(d_seqs "$DLOG/hub.$MEMBER.jsonl")" = "1,3" ] && grep -q '"beta 3"' "$DLOG/beta.human.jsonl" 2>/dev/null \
  && grep -q '"delta 3"' "$DLOG/delta.human.jsonl" 2>/dev/null; }
until_true 300 d_holds || true
if d_holds; then pass "delta holds its says, beta's and the web humans the endpoint brought, hub/<member> at 1 and 3 (2 spent)"; else
  fail "delta holds its says, beta's and the web humans the endpoint brought"; fi
d_remote() { git -C "$BARE3" rev-parse --verify -q main >/dev/null 2>&1; }
d_archive_is() { # every writer file of delta's log as the remote's main holds it, byte for byte
  local f
  d_remote || return 1
  for f in "$DLOG"/*.jsonl; do
    cmp -s "$f" <(git -C "$BARE3" show "main:$(basename "$f")" 2>/dev/null) || return 1
  done
}
d_commits() { git -C "$BARE3" log --format=%ce main 2>/dev/null | grep -c "^sminos@delta\$" || true; }
d_committers() { git -C "$BARE3" log --format=%ce main 2>/dev/null | sort -u | tr '\n' ' '; }
d_designation() { # → "true <archive_at>" | "false …" | "none", as delta's uplink recorded the endpoint's have
  python3 - "$T/d/s/projects/$PID3/uplink.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    d = {}
print("%s %s" % (str(d["archive"]).lower(), d.get("archive_at")) if "archive" in d else "none")
PY
}
d_designated_as() { [ "$(d_designation | cut -d' ' -f1)" = "$1" ]; }
d_confirmed_after() { python3 -c 'import sys; v = sys.argv[1].split(); sys.exit(0 if len(v) == 2 and v[1] != "None" and float(v[1]) > float(sys.argv[2]) else 1)' \
  "$(d_designation)" "$1"; }
d_confirmations() { # n — wait until the endpoint has answered n more of delta's hellos for the project
  local i at
  for i in $(seq 1 "$1"); do
    at="$(python3 -c 'import time; print(time.time())')"
    until_true 200 d_confirmed_after "$at" || return 1
  done
}

echo "  no designation:"
# Two confirmations, about two archive periods: a push would have landed by
# then, and waiting longer proves no more.
d_confirmations 2 || true
assert_equals "$(d_designation | cut -d' ' -f1)" false "delta's uplink records the endpoint's answer: not this machine's archive"
assert_equals "$(d_remote && echo pushed || echo empty)" empty "with no machine designated, two confirmations later nothing is pushed"
assert_equals "$(test -e "$T/d/s/projects/$PID3/archive" && echo clone || echo none)" none "and no archive clone is made"

echo "  delta designated:"
CONNS_D="$(epq_d 'd["conns"]')"
ep_d set "{\"archive\": {\"$PID3\": true}}"
until_true 200 d_designated_as true || true
assert_equals "$(d_designation | cut -d' ' -f1)" true "delta's uplink learns it is the archive machine at its next hello"
assert_equals "$(epq_d 'd["conns"]')" "$CONNS_D" "without a reconnect"
until_true 300 d_archive_is || true
if d_archive_is; then pass "delta writes its log to the remote, every writer file byte for byte"; else
  fail "delta writes its log to the remote"; git -C "$BARE3" ls-tree --name-only main 2>&1 | head || true; fi
assert_equals "$(git -C "$BARE3" show "main:hub.$MEMBER.jsonl" | python3 -c 'import json, sys
print([(e["seq"], "verified" in e) for e in map(json.loads, sys.stdin)])')" "[(1, True), (3, True)]" \
  "the archive keeps the hole of the spent position, each imported event as the log holds it (its verified)"
assert_equals "$(git -C "$BARE3" show main:beta.human.jsonl | python3 -c 'import json, sys
print(sorted({e["verified"]["signer"]["name"] for e in map(json.loads, sys.stdin)}))')" "['beta']" \
  "beta's events, as delta imported them, keep the endpoint's verified"
assert_equals "$(test -d "$T/d/s/projects/$PID3/archive/.git" && echo clone)" clone "from a clone at the project's home, archive/"
assert_equals "$(test -e "$DLOG/.git" && echo git || echo none)" none "outside log/, which is no git working tree"
assert_equals "$(d_committers)" "sminos@delta " "every commit on the remote is delta's"
"$SMINOS" say "delta later" >/dev/null
until_true 300 d_archive_is || true
if d_archive_is && git -C "$BARE3" show main:delta.human.jsonl | grep -q "delta later"; then
  pass "a later say reaches the remote at a later run"; else fail "a later say reaches the remote at a later run"; fi
N=$(d_commits)
d_confirmations 2 || true
assert_equals "$(d_commits)" "$N" "a run with nothing new to archive commits nothing"

echo "  git never feeds the live log:"
DSTRANGER="$T/d/stranger"
gitq clone -q "$BARE3" "$DSTRANGER"
printf '%s\n' '{"ts":"2026-10-15T00:00:00.000Z","writer":"stranger/x","seq":1,"kind":"say","from":"x","to":"*","text":"from git"}' \
  > "$DSTRANGER/stranger.x.jsonl"
printf '%s\n' '{"ts":"2026-10-15T00:00:00.000Z","writer":"delta/human","seq":99,"kind":"say","from":"x","to":"*","text":"edited in git"}' \
  >> "$DSTRANGER/delta.human.jsonl"
gitq -C "$DSTRANGER" add -A
gitq -C "$DSTRANGER" commit -q -m "a stranger's commit"
gitq -C "$DSTRANGER" push -q origin HEAD:main
DSTRANGER_AT="$(git -C "$DSTRANGER" rev-parse HEAD)"
"$SMINOS" say "delta after the stranger" >/dev/null
d_after_stranger() { git -C "$BARE3" show main:delta.human.jsonl 2>/dev/null | grep -q "delta after the stranger"; }
until_true 300 d_after_stranger || true
until_true 100 d_archive_is || true
if d_archive_is; then pass "delta's next run copies its log over the remote's, its writer file as the log holds it"; else
  fail "delta's next run copies its log over the remote's"; fi
assert_not_contains "$(git -C "$BARE3" show main:delta.human.jsonl)" "edited in git" "the line edited in git is gone from the archive"
assert_equals "$(git -C "$BARE3" show main:stranger.x.jsonl)" \
  '{"ts":"2026-10-15T00:00:00.000Z","writer":"stranger/x","seq":1,"kind":"say","from":"x","to":"*","text":"from git"}' \
  "a file the log lacks stays as the remote has it"
assert_equals "$(git -C "$BARE3" merge-base --is-ancestor "$DSTRANGER_AT" main && echo kept)" kept \
  "built on the remote's main: the stranger's commit stays in the history (no force)"
assert_equals "$(ls "$DLOG"/stranger* 2>/dev/null | wc -l | tr -d ' ')" 0 "delta's log holds no stranger's file"
assert_not_contains "$(cat "$DLOG"/*.jsonl)" "edited in git" "nor the line edited in git"

echo "  a remote that would steer the copy:"
gitq -C "$DSTRANGER" fetch -q origin
gitq -C "$DSTRANGER" reset -q --hard origin/main
rm "$DSTRANGER/delta.human.jsonl"
ln -s ../log/beta.human.jsonl "$DSTRANGER/delta.human.jsonl"   # from the archive clone: delta's live beta writer
printf '*.jsonl\n' > "$DSTRANGER/.gitignore"
printf '*.jsonl ident text eol=crlf\n' > "$DSTRANGER/.gitattributes"
gitq -C "$DSTRANGER" add -A
gitq -C "$DSTRANGER" commit -q -m "a remote that would steer the copy"
gitq -C "$DSTRANGER" push -q origin HEAD:main
cp "$DLOG/beta.human.jsonl" "$T/d/beta-before"
# shellcheck disable=SC2016 # the dollar signs are the ident attribute's keyword, written as they are
"$SMINOS" say 'ident probe $Id: kept as written $' >/dev/null
python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
sminos.log_append(sminos.resolve_project(os.getcwd()), "delta/late-feed", "say", **{"from": "human", "to": "*", "text": "a writer file new after the ignore rule"})
PY
d_steered() { git -C "$BARE3" cat-file -e main:delta.late-feed.jsonl 2>/dev/null \
  && git -C "$BARE3" show main:delta.human.jsonl 2>/dev/null | grep -q "ident probe"; }
until_true 300 d_steered || true
assert_equals "$(cmp -s "$T/d/beta-before" "$DLOG/beta.human.jsonl" && echo unchanged)" unchanged \
  "the live log is unchanged: nothing was written through the remote's symlink"
assert_equals "$(git -C "$BARE3" ls-tree main delta.human.jsonl | cut -c1-6)" 100644 "the writer file is a regular file in the archive again"
until_true 100 d_archive_is || true
if d_archive_is; then pass "every writer file byte for byte, the remote's .gitattributes (ident, text, eol) notwithstanding"; else
  fail "every writer file byte for byte, the remote's .gitattributes notwithstanding"; fi
# shellcheck disable=SC2016
assert_contains "$(git -C "$BARE3" show main:delta.human.jsonl)" 'ident probe $Id: kept as written $' "the ident keyword kept as the log holds it"
assert_contains "$(git -C "$BARE3" show main:delta.late-feed.jsonl 2>&1)" "a writer file new after the ignore rule" \
  "a writer file the remote's .gitignore covers is archived all the same"
assert_equals "$(git -C "$BARE3" show main:.gitignore) | $(git -C "$BARE3" show main:.gitattributes)" \
  "*.jsonl | *.jsonl ident text eol=crlf" "the remote's own files stay as the remote has them"

echo "  the designation moved away, or cleared:"
# From this machine, a designation moved to another machine and one cleared
# are the same answer, the have's `archive` false: DX2's two cases are one here.
ep_d set '{"archive": false}'
until_true 200 d_designated_as false || true
assert_equals "$(d_designation | cut -d' ' -f1)" false "delta learns it no longer is, at its next hello"
# A run delta began before it learned may still land: counted from one
# confirmation on, nothing more.
d_confirmations 1 || true
N=$(d_commits)
HEAD_BEFORE_D="$(git -C "$BARE3" rev-parse main)"
"$SMINOS" say "delta after the move" >/dev/null
d_confirmations 2 || true
assert_equals "$(d_commits)" "$N" "delta, no longer designated, pushes nothing at its next schedules"
assert_equals "$(git -C "$BARE3" rev-parse main)" "$HEAD_BEFORE_D" "with the designation moved or cleared, nobody pushes"

# ---- the designation moved to this machine: the other half of DX2's "the
# designation moves to beta" (L332-353), where the new archiver starts on an
# archive another machine wrote. Another project, rlmoved, whose remote holds
# beta's archive commits before delta is ever designated for it: beta's
# writer, delta's own writer as beta held it (one position past what the
# endpoint has admitted of it to delta, which delta's run must not take back),
# and a third machine's file delta never held. Designated, delta fetches,
# commits on top and pushes fast-forward: every prior commit and file kept,
# no position the archive held lost, and no ref update ever a force.
echo "  the designation moved to delta, onto another archiver's history:"
RD2="$T/d/moved"
BARE4="$T/rl10-moved.git"
gitq init -q --bare "$BARE4"
UPDATES="$T/d/moved-updates"
: > "$UPDATES"
cat > "$BARE4/hooks/update" <<HOOK
#!/bin/sh
# Every ref update the remote takes, a fast-forward or not.
if [ "\$2" = 0000000000000000000000000000000000000000 ] || git merge-base --is-ancestor "\$2" "\$3"; then
  echo "ff \$1" >> "$UPDATES"
else
  echo "non-ff \$1" >> "$UPDATES"
fi
HOOK
chmod +x "$BARE4/hooks/update"
mkdir -p "$RD2"
gitq init -q "$RD2"
(cd "$RD2" && "$SMINOS" project init --name rlmoved --hub --remote "$BARE4" >/dev/null)
PID4="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RD2/.smns")"
DLOG4="$T/d/s/projects/$PID4/log"
opened_d4() { [ "$(epq_d "any(f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$PID4' for f in d['received'])")" = true ]; }
until_true 300 opened_d4 || true
d4_taken() { python3 -c 'import json, sys
try: print(json.load(open(sys.argv[1])).get("taken", {}).get("delta/human", 0))
except (OSError, ValueError): print(0)' "$T/d/s/projects/$PID4/uplink-taken.json"; }
d4_taken_past() { [ "$(d4_taken)" -ge "$1" ]; }
for i in 1 2; do (cd "$RD2" && "$SMINOS" say "delta moved $i" >/dev/null); done
until_true 200 d4_taken_past 2 || true
ep_d set '{"admit": false}'
(cd "$RD2" && "$SMINOS" say "delta moved 3" >/dev/null)
until_true 200 d4_taken_past 3 || true
ep_d send "$(python3 "$T/arrivals.py" "$PID4" "$MEMBER")"
d4_holds() { grep -q '"beta 3"' "$DLOG4/beta.human.jsonl" 2>/dev/null && [ "$(d_seqs "$DLOG4/delta.human.jsonl")" = "1,2,3" ]; }
until_true 300 d4_holds || true
assert_equals "$(d4_holds && echo yes)" yes "delta holds its three says in rlmoved, the endpoint's have admitting two, and beta's"
# beta's archive, as beta wrote it before the designation moved: its own
# writer, delta's as beta imported it (all three positions), a third
# machine's, in two commits.
BETA_ARCHIVE="$T/d/beta-archive"
gitq clone -q "$BARE4" "$BETA_ARCHIVE" 2>/dev/null
python3 - "$BETA_ARCHIVE/beta.human.jsonl" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    for i in (1, 2, 3):
        f.write(json.dumps({"ts": "2026-11-05T00:00:0%d.000Z" % i, "writer": "beta/human", "seq": i, "kind": "say",
                            "from": "human", "to": "*", "text": "beta %d" % i}) + "\n")
PY
gitq -C "$BETA_ARCHIVE" add -A
gitq -C "$BETA_ARCHIVE" -c user.name=sminos -c user.email=sminos@beta commit -q -m "sminos: beta archives rlmoved"
cp "$DLOG4/delta.human.jsonl" "$BETA_ARCHIVE/delta.human.jsonl"
printf '%s\n' '{"ts":"2026-11-05T00:00:00.000Z","writer":"gamma/human","seq":1,"kind":"say","from":"human","to":"*","text":"gamma, archived by beta"}' \
  > "$BETA_ARCHIVE/gamma.human.jsonl"
gitq -C "$BETA_ARCHIVE" add -A
gitq -C "$BETA_ARCHIVE" -c user.name=sminos -c user.email=sminos@beta commit -q -m "sminos: beta archives rlmoved"
gitq -C "$BETA_ARCHIVE" push -q origin HEAD:main
BETA_HEAD="$(git -C "$BARE4" rev-parse main)"
BETA_COMMITS="$(git -C "$BARE4" rev-list main | sort | tr '\n' ' ')"
cp "$BETA_ARCHIVE/gamma.human.jsonl" "$T/d/gamma-before"
ep_d set "{\"archive\": {\"$PID4\": true}}"
d4_pushed() { git -C "$BARE4" log --format=%ce main 2>/dev/null | grep -q "^sminos@delta\$"; }
until_true 300 d4_pushed || true
assert_equals "$(d4_pushed && echo yes)" yes "delta, designated for rlmoved, writes its archive"
assert_equals "$(git -C "$BARE4" merge-base --is-ancestor "$BETA_HEAD" main && echo on-top)" on-top \
  "on top of beta's history: beta's head is an ancestor of the new main"
assert_equals "$(comm -23 <(tr ' ' '\n' <<<"$BETA_COMMITS" | grep .) <(git -C "$BARE4" rev-list main | sort) | wc -l | tr -d ' ')" 0 \
  "every commit beta wrote stays in the history"
assert_equals "$(( $(grep -c '^ff ' "$UPDATES" || true) >= 2 )) $(grep -c '^non-ff' "$UPDATES" || true)" "1 0" \
  "the remote took beta's push and delta's, every ref update a fast-forward: no force"
assert_equals "$(git -C "$BARE4" show main:gamma.human.jsonl | cmp -s - "$T/d/gamma-before" && echo kept)" kept \
  "a file delta's log lacks stays as beta archived it"
assert_equals "$(git -C "$BARE4" show main:delta.human.jsonl | python3 -c 'import json, sys
print([e["seq"] for e in map(json.loads, sys.stdin)])')" "[1, 2, 3]" \
  "delta's writer keeps the position beta archived past what the endpoint has admitted to delta: the frontier never moves back"
assert_equals "$(git -C "$BARE4" show main:beta.human.jsonl | python3 -c 'import json, sys
print(sorted({"verified" in e for e in map(json.loads, sys.stdin)}))')" "[True]" \
  "and beta's writer as delta's log holds it, imported"
ep_d set '{"admit": true}'
kill "$D_DAEMON"
set +e; wait "$D_DAEMON"; set -e
assert_not_contains "$(cat "$T/d/s/daemon.log")" "Traceback" "nothing in delta's daemon.log is a traceback"

# The two in-process cases on an uncoded HubLog, delta's daemon stopped so no
# run of its own races them.
echo "  a push rejected because the remote moved (uncoded):"
OUT="$(python3 - "$DSTRANGER" <<'PY'
import os, subprocess, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_archive as archive, sminos_hublog as hublog
stranger = sys.argv[1]
project = sminos.resolve_project(os.getcwd())
e = sminos.log_append(project, "delta/human", "say", **{"from": "human", "to": "*", "text": "delta, raced"})
# The endpoint's have that confirms the run admits it (the archive copies an own writer up to that vector alone).
hublog.HubLog(project, {"key": None, "machine": "delta"}, coded=False).on_have(
    {"have": {"delta/human": e["seq"]}, "archive": True})
real, raced, answers = archive.push_once, [], []

def push_once(clone):
    # Between the fetch of this run and its push, another writer moves the remote.
    if not raced:
        raced.append(1)
        for args in (["fetch", "-q", "origin"], ["reset", "-q", "--hard", "origin/main"]):
            subprocess.run(["git", "-C", stranger, *args], check=True)
        with open(os.path.join(stranger, "stranger.x.jsonl"), "a") as f:
            f.write('{"ts":"2026-10-15T00:00:01.000Z","writer":"stranger/x","seq":2,"kind":"say","from":"x","to":"*","text":"raced"}\n')
        for args in (["add", "-A"], ["commit", "-q", "-m", "a race"], ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", stranger, *args], check=True)
    p = real(clone)
    answers.append("rejected" if p.returncode else "pushed")
    return p

archive.push_once = push_once
print("%s: %s" % ("pushed" if archive.run(project) else "nothing", " then ".join(answers)))
PY
)" || true
assert_equals "$OUT" "pushed: rejected then pushed" "the push the remote rejected is retried from a fresh fetch, and lands"
assert_contains "$(git -C "$BARE3" show main:stranger.x.jsonl)" '"text":"raced"' "keeping the commit that raced it"
assert_contains "$(git -C "$BARE3" show main:delta.human.jsonl)" "delta, raced" "with delta's log on top"

echo "  a repeated hello (uncoded):"
assert_equals "$(python3 - <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_hublog as hublog
hl = hublog.HubLog(sminos.resolve_project(os.getcwd()), {"key": None, "machine": "delta"}, coded=False)
hl.on_have({"have": {"delta/human": 5, "beta/human": 9}, "archive": False})
opened = [dict(hl.sent), sorted(hl.stuck)]
hl.stuck.add("delta/human")  # the endpoint refused it on this connection
hl.on_have({"have": {"delta/human": 3}, "archive": True})  # an older vector, answering a repeated hello
refreshed = [dict(hl.sent), sorted(hl.stuck), hl.archive]
hl.on_have({"have": {"delta/human": 7}, "archive": True})
ahead = dict(hl.sent)
hl.reset()  # a new connection
hl.on_have({"have": {"delta/human": 3}, "archive": False})
print(json.dumps([opened, refreshed, ahead, [dict(hl.sent), sorted(hl.stuck)]]))
PY
)" '[[{"delta/human": 5}, []], [{"delta/human": 5}, ["delta/human"], true], {"delta/human": 7}, [{"delta/human": 3}, []]]' \
  "its have moves what the hub holds only forward and keeps a refused writer stopped; a new stream starts both over"
unset MAWS_USER_DATA

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES archive assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) archive assertions FAILED"
  exit 1
fi
