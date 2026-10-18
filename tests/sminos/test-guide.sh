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
record() { # name session cwd — an engine record (a running process: this shell)
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
    "$$" "$2" "$1" "$3" > "$HOME/.claude/sessions/$1.json"
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
for verb in "list" "--here" "--org" "find" "@<short>" "@<project>/<alias>" "join <project>" "charge"; do
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
assert_contains "$OUT" "alpha" "with the launch directory's own project"

echo "before the transcript exists the payload's directory stands in:"
S3=3c000003-0000-4000-8000-000000000003
guide "$(payload "$S3" "$REPO" "$T/none.jsonl")"
first="$(head -1 <<<"$OUT")"
assert_contains "$first" "[3c000003]" "a session with no record yet is named by its short"
assert_contains "$first" "project teamproj" "in the payload directory's project"

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
