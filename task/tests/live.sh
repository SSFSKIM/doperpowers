#!/usr/bin/env bash
# The scratch cases, against real GitHub (the spec's acceptance 21 on):
#
#   TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh fork
#   TASK_LIVE_REPO=<owner>/<scratch> TASK_LIVE_REPO2=<owner>/<scratch2> bash task/tests/live.sh edge
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
  fork|edge) ;;
  *) echo "usage: live.sh fork|edge  (TASK_LIVE_REPO, and TASK_LIVE_REPO2 for edge)" >&2; exit 2 ;;
esac

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export TASK_HOME="$work/task-home"
export TASK_SMINOS=""
unset CLAUDE_CODE_SESSION_ID

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

case "$case" in
  fork)
    need TASK_LIVE_REPO
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
    case "$urls" in OTHER*) echo "fork: task returned another repository's issues" >&2; status=1 ;; esac
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
    need TASK_LIVE_REPO
    need TASK_LIVE_REPO2
    blocker="$(gh api "repos/$TASK_LIVE_REPO2/issues" -X POST -f title="live edge check: the blocker" \
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
    gh api "repos/$TASK_LIVE_REPO2/issues/$blocker" -X PATCH -f state=closed -f state_reason=not_planned > /dev/null
    echo "cross-repository blocked-by: $verdict"
    ;;
esac
