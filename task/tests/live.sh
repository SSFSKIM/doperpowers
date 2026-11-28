#!/usr/bin/env bash
# The scratch cases, against real GitHub (the spec's acceptance 21 on):
#
#   TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh fork
#   TASK_LIVE_REPO=<owner>/<scratch> TASK_LIVE_REPO2=<owner>/<scratch2> bash task/tests/live.sh edge
#   TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh migrate
#   TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh race
#   TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh lapse
#
# TASK_LIVE_REPO names a private scratch repository whose default branch
# carries .doperpowers/board.json saying binding "task" and naming itself;
# TASK_LIVE_REPO2 a second one, for `edge`. Each case runs this worktree's
# own launcher with a TASK_HOME of its own, as no session (no registered-by,
# no sminos asked), and never touches a repository it was not given (fork
# reads TASK_LIVE_UPSTREAM, a public project, `cli/cli` by default, and
# writes nothing there).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
task="$here/../bin/task"
case="${1:-}"

need() {
  if [ -z "${!1:-}" ]; then
    echo "live.sh $case: $1 is unset: it names a private scratch repository (owner/name); nothing was run" >&2
    exit 2
  fi
}

case "$case" in
  fork|edge|migrate|race|lapse) ;;
  *) echo "usage: live.sh fork|edge|migrate|race|lapse  (TASK_LIVE_REPO, and TASK_LIVE_REPO2 for edge)" >&2; exit 2 ;;
esac

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export TASK_HOME="$work/task-home"
export TASK_SMINOS=""
unset CLAUDE_CODE_SESSION_ID

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# A case writes to its repositories only once github.com has said each is private: the last one checked has its
# full name, in lower case, in `resolved` (a renamed repository's answer is its new name).
scratch() {
  need "$1"
  local seen
  if ! seen="$(gh api --hostname github.com "repos/${!1}" -q '[.full_name, (.private | tostring)] | join(" ")')"; then
    echo "live.sh $case: $1 could not be read on github.com; nothing was run" >&2
    exit 2
  fi
  if [ "${seen##* }" != true ]; then
    echo "live.sh $case: $1 is not a private repository; nothing was run" >&2
    exit 2
  fi
  resolved="$(lower "${seen% *}")"
}

# A case that seeds or clears issues by hand does so only on a board whose default branch says binding "task" and
# names that repository: a scratch repository given by mistake is never written to.
board_of_task() {
  local content
  if ! content="$(gh api --hostname github.com "repos/${!1}/contents/.doperpowers/board.json" -q .content)" ||
    ! python3 -c '
import base64, json, sys
data = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
sys.exit(0 if isinstance(data, dict) and data.get("binding") == "task"
         and str(data.get("repo", "")).lower() == sys.argv[2].lower() else 1)' "$content" "${!1}" 2> /dev/null; then
    echo "live.sh $case: $1's default branch has no .doperpowers/board.json saying binding \"task\" and naming it;" \
      "nothing was run" >&2
    exit 2
  fi
}

case "$case" in
  fork)
    scratch TASK_LIVE_REPO
    upstream="${TASK_LIVE_UPSTREAM:-cli/cli}"
    gh repo clone "$TASK_LIVE_REPO" "$work/clone" -- -q
    git -C "$work/clone" remote add upstream "https://github.com/$upstream.git"
    # No default recorded for the client: the state the fault was seen in.
    for remote in $(git -C "$work/clone" remote); do
      git -C "$work/clone" config --unset "remote.$remote.gh-resolved" || true
    done
    gh_names="$(cd "$work/clone" && gh repo view --json nameWithOwner -q .nameWithOwner)"
    (cd "$work/clone" && "$task" list --json) > "$work/list.json"
    (cd "$work/clone" && "$task" list --untracked --json) > "$work/untracked.json"
    task_lists="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo"])' "$work/list.json")"
    # Every ticket returned is the scratch repository's own, by its URL (none open makes this check say so).
    urls="$(python3 - "$TASK_LIVE_REPO" "$work/list.json" "$work/untracked.json" <<'PY'
import json, sys
home = "https://github.com/%s/issues/" % sys.argv[1].lower()
tickets = [t for f in sys.argv[2:] for t in json.load(open(f))["tickets"]]
other = [t["url"] for t in tickets if not t["url"].lower().startswith(home)]
print("%d of %d" % (len(tickets) - len(other), len(tickets)) if not other else "OTHER " + " ".join(other))
PY
)"
    echo "gh names $gh_names; task lists $task_lists; its open issues' URLs are the scratch repository's: $urls"
    status=0
    case "$urls" in
      OTHER*) echo "fork: task returned another repository's issues" >&2; status=1 ;;
    esac
    if [ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["tickets"]))' "$work/list.json")" = 0 ]; then
      echo "fork: the scratch board listed no ticket, so the URL check read nothing: it needs a standing open" \
        "ticket there (need-input, undecided, never takeable)" >&2
      status=1
    fi
    if [ "$(lower "$gh_names")" != "$(lower "$upstream")" ]; then
      echo "fork: the client did not name the upstream project here, so the case shows nothing about it" >&2
      status=1
    fi
    if [ "$(lower "$task_lists")" != "$(lower "$TASK_LIVE_REPO")" ]; then
      echo "fork: task listed $task_lists, not the clone's own board" >&2
      status=1
    fi
    exit "$status"
    ;;
  edge)
    scratch TASK_LIVE_REPO
    first="$resolved"
    scratch TASK_LIVE_REPO2
    if [ "$first" = "$resolved" ]; then
      echo "live.sh edge: TASK_LIVE_REPO and TASK_LIVE_REPO2 are one repository; the case needs two" >&2
      exit 2
    fi
    blocker="$(gh api --hostname github.com "repos/$TASK_LIVE_REPO2/issues" -X POST -f title="live edge check: the blocker" \
      -f body="A scratch issue of task/tests/live.sh edge; closed by it." -q .number)"
    printf 'A scratch ticket of task/tests/live.sh edge, waiting on %s#%s; closed by it.\n' \
      "$TASK_LIVE_REPO2" "$blocker" > "$work/body.md"
    set +e
    made="$("$task" create "live edge check: the blocked" --repo "$TASK_LIVE_REPO" --category spike --priority P3 \
      --readiness need-input --horizon undecided --body-file "$work/body.md" \
      --blocked-by "$TASK_LIVE_REPO2#$blocker" 2> "$work/create.err")"
    code=$?
    set -e
    number="${made%% *}"
    verdict=""
    if [ "$code" = 0 ]; then
      held="$("$task" show "$number" --repo "$TASK_LIVE_REPO" --json | python3 -c '
import json, sys
want = (sys.argv[1].lower(), int(sys.argv[2]))
print(any((b["repo"].lower(), b["number"]) == want for b in json.load(sys.stdin)["blocked_by"]))' \
        "$TASK_LIVE_REPO2" "$blocker")"
      [ "$held" = True ] && verdict="held" || verdict="refused: the create passed, and the edge is not on the ticket"
    else
      verdict="refused: $(tail -n 1 "$work/create.err")"
    fi
    if [ -n "$number" ]; then
      "$task" close "$number" --not-planned --repo "$TASK_LIVE_REPO" > /dev/null
    fi
    gh api --hostname github.com "repos/$TASK_LIVE_REPO2/issues/$blocker" -X PATCH -f state=closed -f state_reason=not_planned > /dev/null
    echo "cross-repository blocked-by: $verdict"
    ;;
  migrate)
    # Seeds one `live migrate: …` issue per row of D6's table, plans, settles the decisions (every row of an issue
    # it did not make is "leave"), applies twice and lints; its issues are closed at the end, and at the start
    # when an earlier run left them open. The fork case's standing ticket is on the board already: no row.
    scratch TASK_LIVE_REPO
    board_of_task TASK_LIVE_REPO
    helper="$here/live_migrate.py"
    python3 "$helper" clear "$TASK_LIVE_REPO"
    # On a failure the work directory (the plan, each step's output) is kept and named.
    status=0 rc=0
    trap 'rc=$?; python3 "$helper" clear "$TASK_LIVE_REPO" || true
          if [ "$rc" = 0 ]; then rm -rf "$work"; else echo "migrate: its outputs are kept in $work" >&2; fi' EXIT
    seeded="$(python3 "$helper" seed "$TASK_LIVE_REPO" "$task")"
    count="$(python3 -c 'import json,sys; print(len(json.loads(sys.argv[1])))' "$seeded")"
    "$task" migrate plan --repo "$TASK_LIVE_REPO" --out "$work/plan.json" > "$work/plan.out"
    sed -n 2p "$work/plan.out"
    python3 "$helper" settle "$work/plan.json" "$seeded"
    "$task" migrate apply "$work/plan.json" --repo "$TASK_LIVE_REPO" > "$work/apply1.out" 2>&1 || status=1
    tail -n 2 "$work/apply1.out"
    "$task" migrate apply "$work/plan.json" --repo "$TASK_LIVE_REPO" > "$work/apply2.out" 2>&1 || status=1
    second="$(grep -o 'writes: [0-9]*' "$work/apply2.out" || echo 'writes: unknown')"
    lint_code=0
    "$task" lint --repo "$TASK_LIVE_REPO" > "$work/lint.out" 2>&1 || lint_code=$?
    fails="$(grep -c '^FAIL ' "$work/lint.out" || true)"
    python3 "$helper" check "$TASK_LIVE_REPO" "$task" "$seeded" || status=1
    echo "seeded $count issues, one per row of D6's table; applied; lint: $fails FAIL, exit $lint_code; second apply: $second"
    if [ "$lint_code" != 0 ] || [ "$fails" != 0 ]; then cat "$work/lint.out" >&2; status=1; fi
    if [ "$second" != "writes: 0" ]; then cat "$work/apply2.out" >&2; status=1; fi
    if [ "$status" != 0 ]; then cat "$work/apply1.out" >&2; fi
    exit "$status"
    ;;
  race)
    # Twenty rounds of five claimants on fresh tickets (live_race.py says how); each ticket is closed at its
    # round's end. Any count but one winner a round and no missed claim stops M3 (the spec's Delegated unknowns).
    scratch TASK_LIVE_REPO
    python3 "$here/live_race.py" "$TASK_LIVE_REPO" "$task" "${TASK_LIVE_ROUNDS:-20}"
    ;;
  lapse)
    # A spawned thread claims a fresh scratch ticket with this launcher and is retired; nothing in sminos calls
    # the plugin, so the release comes from the settle a later `task list` of that board runs on this machine. The
    # real sminos is used (TASK_LIVE_SMINOS, else PATH, else the marketplace clone), with this case's TASK_HOME.
    scratch TASK_LIVE_REPO
    sm="${TASK_LIVE_SMINOS:-$(command -v sminos || echo "$HOME/.claude/plugins/marketplaces/doperpowers/sminos/skills/sminos/scripts/sminos")}"
    if [ ! -x "$sm" ]; then echo "live.sh lapse: no sminos CLI found (set TASK_LIVE_SMINOS)" >&2; exit 2; fi
    printf 'A scratch ticket of task/tests/live.sh lapse: a spawned thread claims it and is retired; closed by it.\n' \
      > "$work/body.md"
    made="$("$task" create "live lapse check" --repo "$TASK_LIVE_REPO" --category spike --priority P3 \
      --readiness ready-to-work --horizon expected --body-file "$work/body.md")"
    number="${made%% *}"
    trap '"$task" close "$number" --repo "$TASK_LIVE_REPO" --not-planned --force "live lapse check done" \
      > /dev/null 2>&1 || true; rm -rf "$work"' EXIT
    alias="task-lapse-$(date +%s)"
    # Every word of the command quoted for a shell, a path or a name with a quote or a space in it staying one
    # word; the assignments are env's arguments, since a quoted assignment is no assignment to the shell.
    command="$(python3 -c 'import shlex, sys; print(shlex.join(sys.argv[1:]))' env "TASK_HOME=$TASK_HOME" \
      "TASK_SMINOS=$sm" "$task" claim "$number" --repo "$TASK_LIVE_REPO")"
    "$sm" spawn "$alias" "Run exactly this one command with your Bash tool and reply with its output and nothing \
else: $command" > "$work/spawn.txt" 2>&1 || true
    # The seat works in the background: its claim is seen in this case's index, within ten minutes.
    held="$(python3 - "$TASK_HOME/claims.json" "$number" <<'PY'
import json, sys, time
deadline = time.time() + 600
while True:
    try:
        rows = json.load(open(sys.argv[1]))["rows"]
    except (OSError, ValueError):
        rows = []
    mine = [r for r in rows if r["number"] == int(sys.argv[2]) and r["state"] == "held" and r["thread"]]
    if mine or time.time() > deadline:
        break
    time.sleep(5)
print(mine[0]["thread"] if mine else "")
PY
)"
    if [ -z "$held" ]; then
      echo "lapse: the spawned thread did not hold #$number within ten minutes; its spawn and reply:" >&2
      cat "$work/spawn.txt" >&2
      "$sm" reply "$alias" >&2 || true
      "$sm" retire "$alias" > /dev/null 2>&1 || true
      exit 1
    fi
    "$sm" retire "$alias" > "$work/retire.txt" 2>&1
    # Another session of this machine: an invented session id of its own.
    CLAUDE_CODE_SESSION_ID="0000a11c-0000-4000-8000-$(printf '%012d' "$$")" TASK_SMINOS="$sm" TASK_SETTLE_EVERY=1 \
      "$task" list --repo "$TASK_LIVE_REPO" --json > "$work/list.json"
    "$task" show "$number" --repo "$TASK_LIVE_REPO" --json > "$work/show.json"
    verdict="$(python3 - "$work/list.json" "$work/show.json" "$number" <<'PY'
import json, sys
listed = [t for t in json.load(open(sys.argv[1]))["tickets"] if t["number"] == int(sys.argv[3])]
show = json.load(open(sys.argv[2]))
ended = [c for c in show["comments"] if c["trusted"] and c["body"].startswith("```task-claim\nop: release\n")
         and "\nreason: ended\n" in c["body"]]
ok = listed and listed[0]["holder"] is None and show["holder"] is None and "claimed" not in show["labels"] and ended
print("%s listed unheld: %s; release reason ended: %d; label off: %s" % (
    "ok" if ok else "FAIL", bool(listed) and listed[0]["holder"] is None, len(ended), "claimed" not in show["labels"]))
PY
)"
    echo "a spawned thread ($alias) claimed $TASK_LIVE_REPO#$number and was retired; task list: $verdict"
    case "$verdict" in ok*) ;; *) exit 1 ;; esac
    ;;
esac
