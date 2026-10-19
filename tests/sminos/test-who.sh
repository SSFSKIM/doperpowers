#!/usr/bin/env bash
#
# A session's address in what it writes, and `sminos who`, which reads it
# back. `who` alone (`--session`, the address mod's call) prints the line a
# session's commits and PRs carry, `Sminos-Session: <alias>#<short>
# (<project> on <machine>)`, and nothing for a session in no project, an
# internal fork, or one that is no member (a headless run). `who <commit>`
# reads the commit's trailer and says who that session is now: its alias
# (the current one when renamed), project, machine and state; the session it
# went on as when it went to the background (a hand-off); how to reach it,
# or to resume it once stopped. An address no session known here answers to
# is still said as the line says it. A commit without the line exits 4.
# Hermetic: HOME and SMINOS_HOME are temporary; the enrollment is a file
# written by hand; `gh` is never called (PRs are the mod's live check's).
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
SCRIPTS="${SMINOS_SCRIPTS:-$REPO_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smw.XXXXXX)"
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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export HOME="$T/home" SMINOS_HOME="$T/s" DAEMON_HOST=alpha DAEMON_BOOT_ID=boot-current SMINOS_DERIVE_EVERY=0
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME/daemon"
printf '{"hub":"http://127.0.0.1:9","org":"org-1","machine":"alpha"}\n' > "$SMINOS_HOME/daemon/hub.json"

transcript() { # session cwd — a transcript launched in cwd
  local sid=$1
  TX="$HOME/.claude/projects/p-$sid/$sid.jsonl"
  mkdir -p "$(dirname "$TX")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","message":{"role":"user","content":"go"}}\n' \
    "${sid:0:8}" "$sid" "$2" > "$TX"
}
record() { # name session cwd [entrypoint] [kind] [nameSource] — an engine record (a running process: this shell)
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"%s","kind":"%s","status":"idle","cwd":"%s","entrypoint":"%s"}\n' \
    "$$" "$2" "$1" "${6:-user}" "${5:-interactive}" "$3" "${4:-cli}" > "$HOME/.claude/sessions/$1.json"
}
who() { # args... — what `sminos who` prints (stdout), its exit code in RC
  set +e; OUT="$(cd "$REPO" && "$SMINOS" who "$@" 2>"$T/err")"; RC=$?; set -e
}
commit_with() { # message — a commit in REPO, its sha in SHA
  echo "$RANDOM" >> "$REPO/f"
  gitq -C "$REPO" add f
  gitq -C "$REPO" commit -q -m "$1"
  SHA="$(git -C "$REPO" rev-parse HEAD)"
}

REPO="$T/repo"
gitq init -q "$REPO"
python3 -c 'import json, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": "teamproj", "remote": "", "hub": {"org": "org-1"}}))' > "$REPO/.smns"
S1=1a000001-0000-4000-8000-000000000001
transcript "$S1" "$REPO"
record fixer "$S1" "$REPO"

echo "who alone: the line a member's commits carry"
who --session "$S1"
assert_equals "$OUT|$RC" "Sminos-Session: fixer#1a000001 (teamproj on alpha)|0" "alias#short (project on machine)"
OUT="$(cd "$REPO" && CLAUDE_CODE_SESSION_ID=$S1 "$SMINOS" who)"
assert_equals "$OUT" "Sminos-Session: fixer#1a000001 (teamproj on alpha)" "inside the session, from CLAUDE_CODE_SESSION_ID"
OUT="$(cd "$REPO" && SMNS_INTERNAL=1 "$SMINOS" who --session "$S1")"
assert_equals "$OUT" "" "an internal fork: nothing"
S5=5e000005-0000-4000-8000-000000000005
record headless "$S5" "$REPO" sdk-cli
who --session "$S5"
assert_equals "$OUT|$RC" "|0" "a headless run that is no member: nothing, exit 0"
NOPROJ="$T/noproj"
mkdir -p "$NOPROJ"
rm "$SMINOS_HOME/daemon/hub.json"
S6=6f000006-0000-4000-8000-000000000006
transcript "$S6" "$NOPROJ"
record stray "$S6" "$NOPROJ"
set +e; OUT="$(cd "$NOPROJ" && "$SMINOS" who --session "$S6" 2>/dev/null)"; RC=$?; set -e
assert_equals "$OUT|$RC" "|0" "a session in no project (unenrolled, no repository): nothing"
printf '{"hub":"http://127.0.0.1:9","org":"org-1","machine":"alpha"}\n' > "$SMINOS_HOME/daemon/hub.json"

S7=7a000007-0000-4000-8000-000000000007
transcript "$S7" "$REPO"
record "Create a file a.txt and commit it. Then use the Agent tool to create b.txt and commit that too, then reply done." \
  "$S7" "$REPO" cli bg auto   # a `claude --bg "<prompt>"` job: the harness names it by its prompt first
who --session "$S7"
assert_equals "$OUT" "Sminos-Session: 7a000007#7a000007 (teamproj on alpha)" "a name that is no name (a job's prompt): the short stands in"
rm "$HOME/.claude/sessions/Create a file a.txt and commit it. Then use the Agent tool to create b.txt and commit that too, then reply done..json"

echo "who <commit>: the session as it is now"
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)   # its membership in the log, as any verb run there reconciles it
LINE="Sminos-Session: fixer#1a000001 (teamproj on alpha)"
commit_with "$(printf 'fix: a thing\n\nBecause.\n\n%s' "$LINE")"
who "$SHA"
assert_equals "$RC" "0" "exit 0"
assert_contains "$OUT" "commit ${SHA:0:12}" "names what it read"
assert_contains "$OUT" "$LINE" "the line as the commit carries it"
assert_contains "$OUT" "now fixer#1a000001, teamproj on alpha: idle" "alias, project, machine, state"
assert_contains "$OUT" 'reach: sminos say "@1a000001' "how to reach it"

echo "renamed since: the alias it goes by now"
record fixer2 "$S1" "$REPO"
rm "$HOME/.claude/sessions/fixer.json"
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)
who "$SHA"
assert_contains "$OUT" "now fixer2#1a000001" "the current alias"
assert_contains "$OUT" "the line names it fixer; it goes by fixer2 now" "and the one the line names"

echo "stopped: how to resume it"
rm "$HOME/.claude/sessions/fixer2.json"
who "$SHA"
assert_contains "$OUT" ": stopped" "its state"
assert_contains "$OUT" "claude --resume $S1" "resume it by its id"
assert_not_contains "$OUT" 'reach: sminos say "@' "no @ for a closed seat-less session"

echo "sent to the background: the session it went on as"
S2=2b000002-0000-4000-8000-000000000002
S3=3c000003-0000-4000-8000-000000000003
transcript "$S2" "$REPO"
record handy "$S2" "$REPO"
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)
who --session "$S2"
LINE2="$OUT"
assert_equals "$LINE2" "Sminos-Session: handy#2b000002 (teamproj on alpha)" "the member's line before the hand-off"
commit_with "$(printf 'wip\n\n%s' "$LINE2")"
H_SHA="$SHA"
# The harness forks the job under a new id and leaves `continued-in` at the
# old transcript's end; the interactive process exits.
transcript "$S3" "$REPO"
record handyjob "$S3" "$REPO" cli bg auto   # the title the harness made up
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)
# The engine (2.1.303) writes `/background`'s empty output after the record:
# a command's row, never a turn.
printf '{"type":"continued-in","timestamp":"2026-10-18T10:00:00.000Z","sessionId":"%s","continuedInSessionId":"%s"}\n' \
  "$S2" "$S3" >> "$HOME/.claude/projects/p-$S2/$S2.jsonl"
printf '{"type":"user","message":{"role":"user","content":"<local-command-stdout>(no content)</local-command-stdout>"},"sessionId":"%s"}\n' \
  "$S2" >> "$HOME/.claude/projects/p-$S2/$S2.jsonl"
rm "$HOME/.claude/sessions/handy.json"
(cd "$REPO" && "$SMINOS" list >/dev/null 2>&1)
who "$H_SHA"
assert_contains "$OUT" "$LINE2" "the line as the commit carries it"
assert_contains "$OUT" "went on as handy#3c000003 (bg), teamproj on alpha: idle" "the successor, under the member's alias"
assert_contains "$OUT" 'reach: sminos say "@3c000003' "reached at the successor's short"
who --session "$S3"
assert_equals "$OUT" "Sminos-Session: handy#3c000003 (teamproj on alpha)" "the job's own commits carry its new short"

echo "an address no session here answers to: what the line says"
commit_with "$(printf 'chore\n\nSminos-Session: ghost#deadbeef (elsewhere on mini)')"
who "$SHA"
assert_contains "$OUT" "no session deadbeef" "said as unknown"
assert_contains "$OUT" "ghost in project elsewhere on machine mini" "with the line's fields"

echo "a commit with no line, and no commit: exit 4"
commit_with "plain"
who "$SHA"
assert_equals "$RC" "4" "no line: exit 4"
assert_contains "$(cat "$T/err")" "carries no Sminos-Session line" "and says so"
who nosuchref
assert_equals "$RC" "4" "no such commit: exit 4"

echo "a line in the body, not the trailers, is not the commit's address"
commit_with "$(printf 'docs\n\nSee Sminos-Session: x#0badc0de (p on m) for the form.\n\nSigned-off-by: t <t@t>')"
who "$SHA"
assert_equals "$RC" "4" "only a trailer counts"

echo "a pull request (gh, a stub here): its body's last line, else its commits' trailers"
mkdir -p "$T/bin"
cat > "$T/bin/gh" <<'GH'
#!/usr/bin/env bash
# gh pr view <n> --json number,body,commits: the PR this test's GH_PR file holds
[[ "$1 $2" == "pr view" ]] || exit 2
case "$3" in 12|https://github.com/o/r/pull/12) cat "$GH_PR" ;; *) echo "no pull request $3" >&2; exit 1 ;; esac
GH
chmod +x "$T/bin/gh"
export GH_PR="$T/pr.json"
pr() { # body commit-body... — the PR the stub answers
  python3 - "$@" > "$GH_PR" <<'PY'
import json, sys
print(json.dumps({"number": 12, "body": sys.argv[1],
                  "commits": [{"oid": "%040d" % i, "messageHeadline": "c", "messageBody": b} for i, b in enumerate(sys.argv[2:])]}))
PY
}
who_pr() { set +e; OUT="$(cd "$REPO" && PATH="$T/bin:$PATH" "$SMINOS" who "$@" 2>"$T/err")"; RC=$?; set -e; }
pr "$(printf 'Summary.\n\n%s' "$LINE2")" "$(printf 'x\n\nSminos-Session: other#0badc0de (p on m)')"
who_pr 12
assert_contains "$OUT" "pull request #12's body:" "the body's line is read first"
assert_contains "$OUT" "went on as handy#3c000003" "and resolved"
assert_not_contains "$OUT" "0badc0de" "its commits are not read when the body has the line"
who_pr https://github.com/o/r/pull/12
assert_contains "$OUT" "pull request #12's body:" "a PR's URL is read the same"
pr "No line here." "$(printf 'one\n\n%s' "$LINE")" "$(printf 'two\n\n%s' "$LINE")" "$(printf 'three\n\nSminos-Session: ghost#deadbeef (elsewhere on mini)')"
who_pr '#12'
assert_contains "$OUT" "pull request #12's commits:" "no line in the body: its commits' trailers"
assert_equals "$(grep -c '^Sminos-Session:' <<<"$OUT")" "2" "each distinct session once"
pr "nothing" "plain"
who_pr 12
assert_equals "$RC" "4" "a PR with no line anywhere: exit 4"
who_pr 13
assert_equals "$RC" "1" "a PR gh cannot read: exit 1"

echo
echo "who: $PASSES passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ]
