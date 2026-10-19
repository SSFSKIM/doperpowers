#!/usr/bin/env bash
#
# `sminos guide` (M7 of the sminos org directory,
# docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md §9): the text
# the SessionStart hook injects. It reads the hook's payload on stdin and
# prints nothing on a machine not enrolled at a desk hub, under SMNS_INTERNAL,
# or for a payload naming no session — the gate lives here, not in the hook —
# and otherwise names the session (alias [short]), its project and machine,
# and where that project comes from: the launch directory (a `cd` changes
# nothing), the machine's own project for a directory no .smns claims, or the
# session's own `join`. The CLI is named by its absolute path. Only the facts
# are pinned here; the wording is the evals' to settle.
# Hermetic: HOME and SMINOS_HOME are temporary; the enrollment is a file
# written by hand; nothing reaches a network.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
SCRIPTS="${SMINOS_SCRIPTS:-$REPO_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smg.XXXXXX)"
T="$(cd "$T" && pwd -P)"
trap 'rm -rf "$T"' EXIT

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
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export HOME="$T/home" SMINOS_HOME="$T/s" DAEMON_HOST=alpha DAEMON_BOOT_ID=boot-current SMINOS_DERIVE_EVERY=0
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME"

payload() { # session cwd [transcript] — a SessionStart payload
  printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","hook_event_name":"SessionStart","source":"startup"}' \
    "$1" "$2" "${3:-}"
}
guide() { # payload — what `sminos guide` prints, with its exit code in RC
  set +e; OUT="$(printf '%s' "$1" | "$SMINOS" guide 2>"$T/err")"; RC=$?; set -e
}
transcript() { # session cwd... — a transcript whose rows ran in each cwd in turn (the first: where it launched)
  local sid=$1; shift
  TX="$HOME/.claude/projects/p-$sid/$sid.jsonl"
  mkdir -p "$(dirname "$TX")"
  : > "$TX"
  local n=0
  for d in "$@"; do
    n=$((n + 1))
    printf '{"type":"user","uuid":"%s-u%d","isSidechain":false,"sessionId":"%s","cwd":"%s","message":{"role":"user","content":"step %d"}}\n' \
      "${sid:0:8}" "$n" "$sid" "$d" "$n" >> "$TX"
  done
}
record() { # name session cwd [entrypoint] — an engine record (a running process: this shell)
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","entrypoint":"%s"}\n' \
    "$$" "$2" "$1" "$3" "${4:-cli}" > "$HOME/.claude/sessions/$1.json"
}
write_smns() { # dir name — a hub .smns naming only the org
  python3 -c 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": "", "hub": {"org": "org-1"}}))' "$2" > "$1/.smns"
}

STRAY="$T/scratch"
mkdir -p "$STRAY"
S1=1a000001-0000-4000-8000-000000000001
transcript "$S1" "$STRAY"
record new-7e "$S1" "$STRAY"

echo "a machine not enrolled at a desk hub gets nothing:"
guide "$(payload "$S1" "$STRAY" "$TX")"
assert_equals "$OUT|$RC" "|0" "no enrollment: nothing printed, exit 0"

# The enrollment, as `hub enroll` writes it (the fields resolution reads).
mkdir -p "$SMINOS_HOME/daemon"
printf '{"hub":"http://127.0.0.1:9","org":"org-1","machine":"alpha"}\n' > "$SMINOS_HOME/daemon/hub.json"

echo "a stray: the machine's own project, said as such:"
guide "$(payload "$S1" "$STRAY" "$TX")"
assert_equals "$RC" "0" "exit 0"
first="$(head -1 <<<"$OUT")"
assert_contains "$first" "new-7e [1a000001]" "the first line names the session: alias [short]"
assert_contains "$first" "project alpha" "the first line names its project: the machine's own"
assert_contains "$first" "machine alpha" "and its machine"
assert_contains "$OUT" "$STRAY" "it names the launch directory"
assert_contains "$OUT" "no .smns" "and why the machine's project holds it: no .smns claims the directory"
assert_contains "$OUT" "$SCRIPTS/sminos " "the CLI is named by its absolute path"
for verb in "list" "--here" "--org" "who <commit|PR>" "@<short>" "@<project>/<alias>" "join <project>" "charge"; do
  assert_contains "$OUT" "$verb" "it names $verb"
done
assert_equals "$(cat "$T/err")" "" "nothing on stderr"

echo "a session in a hub project, launched there, its shell since moved:"
REPO="$T/repo"
gitq init -q "$REPO"
write_smns "$REPO" teamproj
S2=2b000002-0000-4000-8000-000000000002
transcript "$S2" "$REPO" "$STRAY"
record fixer "$S2" "$STRAY"
guide "$(payload "$S2" "$STRAY" "$TX")"
first="$(head -1 <<<"$OUT")"
assert_contains "$first" "fixer [2b000002]" "it names the session"
assert_contains "$first" "project teamproj" "its project is its launch directory's, not where its shell is now"
assert_contains "$OUT" "$REPO" "the launch directory is named"
assert_contains "$OUT" "cd" "and that a cd does not change it"
assert_not_contains "$OUT" "no .smns" "a project its .smns names is not said to be the machine's"

echo "a session that joined another project:"
transcript "$S1" "$STRAY"
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)   # the project registered here, as any verb run in it does
(cd "$STRAY" && CLAUDE_CODE_SESSION_ID=$S1 "$SMINOS" join teamproj >/dev/null 2>&1)
guide "$(payload "$S1" "$STRAY" "$TX")"
first="$(head -1 <<<"$OUT")"
assert_contains "$first" "project teamproj" "the joined project is the session's"
assert_contains "$OUT" "join --cwd" "and the way back is named"
assert_contains "$OUT" "is in alpha;" "with the launch directory's own project"

echo "before the transcript exists the payload's directory stands in:"
S3=3c000003-0000-4000-8000-000000000003
record fresh "$S3" "$REPO"
guide "$(payload "$S3" "$REPO" "$T/none.jsonl")"
first="$(head -1 <<<"$OUT")"
assert_contains "$first" "fresh [3c000003]" "a session with no transcript yet is named"
assert_contains "$first" "project teamproj" "in the payload directory's project"

echo "only a session that is a member on sight, as the record hook decides it:"
S5=5e000005-0000-4000-8000-000000000005
record headless "$S5" "$REPO" sdk-cli
guide "$(payload "$S5" "$REPO" "$T/none.jsonl")"
assert_equals "$OUT|$RC" "|0" "a headless or SDK run (claude -p) gets nothing"
S6=6f000006-0000-4000-8000-000000000006
guide "$(payload "$S6" "$REPO" "$T/none.jsonl")"
assert_equals "$OUT|$RC" "|0" "a session the engine has not recorded gets nothing"
S7=7a000007-0000-4000-8000-000000000007
( sleep 0.5; record late "$S7" "$REPO" ) &
guide "$(payload "$S7" "$REPO" "$T/none.jsonl")"
wait
assert_contains "$(head -1 <<<"$OUT")" "late [7a000007]" "a record the engine writes a moment after the hook starts is waited for"

echo "a seat: no join line (a seat stays where it was spawned):"
S4=4d000004-0000-4000-8000-000000000004
record helper "$S4" "$REPO"
transcript "$S4" "$REPO"
(cd "$REPO" && "$SMINOS" seat add teamproj helper --session "$S4" >/dev/null 2>&1)
guide "$(payload "$S4" "$REPO" "$TX")"
assert_contains "$(head -1 <<<"$OUT")" "helper [4d000004]" "the seat is told who it is"
assert_not_contains "$OUT" "join <project>" "and not offered a join"
assert_contains "$OUT" 'charge "<line>"' "the rest stands"

echo "after a compaction or a resume: the roster of the peers it exchanged messages with, from the logs:"
emit() { # project-dir writer kind fields-json minutes-ago — one log event, as sminos appends it, at a given age
  python3 - "$SCRIPTS" "$@" <<'PY'
import json, sys, time
sys.path.insert(0, sys.argv[1])
import sminos
p = sminos.resolve_project(sys.argv[2])
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 60 * float(sys.argv[6])))
sminos.log_append_batch(p, sys.argv[3], [dict(json.loads(sys.argv[5]), kind=sys.argv[4], ts=ts)])  # a field may be `project`
PY
}
member() { # project-dir session alias machine minutes-ago — a member's joined, as its own writer wrote it
  emit "$1" "$4/$2" joined "{\"session\":\"$2\",\"alias\":\"$3\",\"name_source\":\"user\",\"machine\":\"$4\",\"cwd\":\"$REPO\"}" "$5"
}
say() { # project-dir writer to-json from minutes-ago [extra-json] — a say event
  emit "$1" "$2" say "{\"from\":\"$4\",\"to\":$3,\"text\":\"hi\"${6:+,$6}}" "$5"
}
OTHER="$T/other"
gitq init -q "$OTHER"
write_smns "$OTHER" otherproj
OTHER_ID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$OTHER/.smns")"
ME=e0000e00-0000-4000-8000-0000000000e0
A=e1000e01-0000-4000-8000-0000000000e1   # here, running; its message to me is unanswered
B=e2000e02-0000-4000-8000-0000000000e2   # another machine's, busy, with an in-charge line; I answered it
C=e3000e03-0000-4000-8000-0000000000e3   # in another project, written through the copy my log keeps
D=e4000e04-0000-4000-8000-0000000000e4   # its session ended
E=e5000e05-0000-4000-8000-0000000000e5   # handed off to E2
E2=e6000e06-0000-4000-8000-0000000000e6
F=e7000e07-0000-4000-8000-0000000000e7   # spoke only untagged, and @all
record me "$ME" "$REPO"
record peer-a "$A" "$REPO"
transcript "$ME" "$REPO"
ME_TX="$TX"
member "$REPO" "$ME" me alpha 120
member "$REPO" "$A" peer-a alpha 120
member "$REPO" "$B" peer-b beta 120
emit "$REPO" "beta/$B" state "{\"session\":\"$B\",\"state\":\"busy\"}" 1
emit "$REPO" "beta/$B" in-charge "{\"session\":\"$B\",\"text\":\"the CI gate\",\"source\":\"set\"}" 100
member "$OTHER" "$C" peer-c beta 120
member "$REPO" "$D" peer-d alpha 120
emit "$REPO" "alpha/$D" retired "{\"session\":\"$D\",\"reason\":\"ended\"}" 25
member "$REPO" "$E" peer-e beta 120
emit "$REPO" "beta/$E" retired "{\"session\":\"$E\",\"reason\":\"continued\",\"to\":\"$E2\"}" 35
member "$REPO" "$E2" peer-e beta 34
member "$REPO" "$F" peer-f alpha 120
say "$REPO" "alpha/$A" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" peer-a 5
say "$REPO" "alpha/$ME" "[{\"session\":\"$B\",\"alias\":\"peer-b\"}]" me 10
say "$REPO" "beta/$B" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" peer-b 20
say "$REPO" "alpha/$ME" "[{\"session\":\"$C\",\"alias\":\"peer-c\",\"project\":\"$OTHER_ID\"}]" me 15 "\"copy\":\"$OTHER_ID:alpha/$ME:1\""
say "$REPO" "alpha/$D" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" peer-d 30
say "$REPO" "alpha/$ME" "[{\"session\":\"$E\",\"alias\":\"peer-e\"}]" me 40
say "$REPO" "alpha/$F" '"*"' peer-f 2
say "$REPO" "alpha/$F" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" peer-f 3 '"wake":true'
say "$REPO" "alpha/$A" "[{\"session\":\"$B\",\"alias\":\"peer-b\"}]" peer-a 1
compact="$(payload "$ME" "$REPO" "$ME_TX" | sed 's/"startup"/"compact"/')"
guide "$compact"
roster="$(sed -n '/who you exchanged sminos messages with/,$p' <<<"$OUT")"
assert_contains "$roster" "as the logs hold them now" "a compaction's guidance ends with the roster"
assert_equals "$(tail -n +2 <<<"$roster" | grep -o 'peer-[a-f] \[' | tr -d ' [' | tr '\n' ' ')" \
  "peer-a peer-b peer-c peer-d peer-e " "the peers it exchanged messages with, newest exchange first, and no one else"
line() { grep -F "$1 [" <<<"$roster"; }
assert_contains "$(line peer-a)" "@peer-a " "a peer in its project is reached by its alias"
assert_contains "$(line peer-a)" "it wrote you" "the last exchange's direction"
assert_contains "$(line peer-a)" "unanswered" "a message to the session it has not answered"
assert_contains "$(line peer-b)" "teamproj on beta, busy" "another machine's peer, with its project, machine and state"
assert_contains "$(line peer-b)" 'in charge: "the CI gate"' "and its in-charge line"
assert_contains "$(line peer-b)" "you wrote it" "the session's own reply is the last exchange"
assert_not_contains "$(line peer-b)" "unanswered" "an answered message is not called unanswered"
assert_contains "$(line peer-c)" "@otherproj/peer-c " "a peer in another project is tagged with its project"
assert_contains "$(line peer-d)" "its session ended, no tag reaches it" "a peer whose session ended is named so"
assert_contains "$(line peer-e)" "[${E2:0:8}]" "a handed-off peer is the session it continues in"
resumed="$(payload "$ME" "$REPO" "$ME_TX" | sed 's/"startup"/"resume"/')"
guide "$resumed"
assert_contains "$OUT" "who you exchanged sminos messages with" "a resume reads the roster too"
for src in startup clear fork; do
  guide "$(payload "$ME" "$REPO" "$ME_TX" | sed "s/\"startup\"/\"$src\"/")"
  assert_not_contains "$OUT" "who you exchanged sminos messages with" "$src: no roster"
done
guide "$(payload "$A" "$REPO" "$T/none.jsonl" | sed 's/"startup"/"compact"/')"
assert_contains "$(sed -n '/who you exchanged/,$p' <<<"$OUT")" "peer-b [" "each session's own roster"

echo "the roster across projects, moves, hand-offs, a shared alias and a project name with a space:"
REPO_ID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$REPO/.smns")"
ME2=f0000f00-0000-4000-8000-0000000000f0   # launched in teamproj, since joined otherproj
G=f1000f01-0000-4000-8000-0000000000f1    # in otherproj; wrote me2 while me2 was in teamproj
record me2 "$ME2" "$REPO"
transcript "$ME2" "$REPO"
ME2_TX="$TX"
member "$REPO" "$ME2" me2 alpha 60
member "$OTHER" "$G" peer-g beta 60
# The delivering event in teamproj's log (its writer's first there: seq 1), and its copy in otherproj's.
say "$REPO" "beta/$G" "[{\"session\":\"$ME2\",\"alias\":\"me2\"}]" peer-g 8 "\"from_project\":\"$OTHER_ID\""
say "$OTHER" "beta/$G" "[{\"session\":\"$ME2\",\"alias\":\"me2\",\"project\":\"$REPO_ID\"}]" peer-g 8 \
  "\"copy\":\"$REPO_ID:beta/$G:1\""
(cd "$REPO" && CLAUDE_CODE_SESSION_ID=$ME2 "$SMINOS" join otherproj >/dev/null 2>&1)
guide "$(payload "$ME2" "$REPO" "$ME2_TX" | sed 's/"startup"/"compact"/')"
roster="$(sed -n '/who you exchanged sminos messages with/,$p' <<<"$OUT")"
assert_contains "$(head -1 <<<"$OUT")" "project otherproj" "me2 is in otherproj by its join, so that log is read first"
assert_contains "$(line peer-g)" "it wrote you" "a message from another project is the peer's, its copy read first"
assert_contains "$(line peer-g)" "unanswered" "and is unanswered"
M=f2000f02-0000-4000-8000-0000000000f2    # moved from teamproj to otherproj
J=f3000f03-0000-4000-8000-0000000000f3    # handed off to J2; both exchanged with me
J2=f4000f04-0000-4000-8000-0000000000f4
W=f5000f05-0000-4000-8000-0000000000f5    # shares its alias with W2, joined here too
W2=f6000f06-0000-4000-8000-0000000000f6
Q=f7000f07-0000-4000-8000-0000000000f7    # in a project whose name has a space
member "$REPO" "$M" peer-m beta 60
say "$REPO" "alpha/$ME" "[{\"session\":\"$M\",\"alias\":\"peer-m\"}]" me 6
emit "$REPO" "beta/$M" retired "{\"session\":\"$M\",\"reason\":\"moved\",\"project\":\"$OTHER_ID\"}" 5
member "$OTHER" "$M" peer-m beta 5
member "$REPO" "$J" peer-j beta 60
say "$REPO" "beta/$J" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" peer-j 9
emit "$REPO" "beta/$J" retired "{\"session\":\"$J\",\"reason\":\"continued\",\"to\":\"$J2\"}" 8
member "$REPO" "$J2" peer-j beta 8
say "$REPO" "alpha/$ME" "[{\"session\":\"$J2\",\"alias\":\"peer-j\"}]" me 7
member "$REPO" "$W" twin alpha 60
member "$REPO" "$W2" twin beta 60
say "$REPO" "alpha/$W" "[{\"session\":\"$ME\",\"alias\":\"me\"}]" twin 3
SPACED="$T/spaced"
gitq init -q "$SPACED"
write_smns "$SPACED" "team proj"
SPACED_ID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$SPACED/.smns")"
member "$SPACED" "$Q" peer-q beta 60
say "$SPACED" "alpha/$ME" "[{\"session\":\"$Q\",\"alias\":\"peer-q\"}]" me 2 "\"from_project\":\"$REPO_ID\""
say "$REPO" "alpha/$ME" "[{\"session\":\"$Q\",\"alias\":\"peer-q\",\"project\":\"$SPACED_ID\"}]" me 2 \
  "\"copy\":\"$SPACED_ID:alpha/$ME:1\""
guide "$compact"
roster="$(sed -n '/who you exchanged sminos messages with/,$p' <<<"$OUT")"
assert_contains "$(line peer-m)" "otherproj on beta" "a peer that moved is named in the project it moved to"
assert_contains "$(line peer-m)" "@otherproj/peer-m " "and tagged with that project"
assert_equals "$(grep -c 'peer-j \[' <<<"$roster")" "1" "two sessions of one peer, both exchanged with: one row"
assert_contains "$(line peer-j)" "[${J2:0:8}]" "the session it continues in"
assert_contains "$(line peer-j)" "@peer-j " "an alias no other joined member holds takes no #short"
assert_contains "$(line twin)" "@twin#${W:0:8} " "an alias another joined member holds takes #short"
tag="$(python3 -c 'import sys; print(sys.argv[1].strip().split("  ")[0])' "$(line peer-q)")"
assert_equals "$tag" '@"team proj/peer-q"' "a project name with a space is quoted"
assert_equals "$(python3 - "$SCRIPTS" "$tag" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
print(" ".join("%s|%s|%s" % (t["project"], t["name"], t["short"]) for t in sminos.leading_tags(sys.argv[2])))
PY
)" "team proj|peer-q|" "and the tag parses back to its project and name"

echo "nothing for an internal fork, or a payload naming no session:"
OUT="$(printf '%s' "$(payload "$S1" "$STRAY" "$TX")" | SMNS_INTERNAL=1 "$SMINOS" guide 2>&1)"
assert_equals "$OUT" "" "SMNS_INTERNAL: nothing"
guide '{"cwd":"/tmp","hook_event_name":"SessionStart"}'
assert_equals "$OUT|$RC" "|0" "no session_id: nothing, exit 0"
guide 'not json'
assert_equals "$OUT|$RC" "|0" "a payload that is not JSON: nothing, exit 0"
guide ''
assert_equals "$OUT|$RC" "|0" "no payload: nothing, exit 0"
guide "$(payload "not-a-session" "$STRAY")"
assert_equals "$OUT|$RC" "|0" "a session id that is no uuid: nothing, exit 0"

echo
echo "guide: $PASSES passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ]
