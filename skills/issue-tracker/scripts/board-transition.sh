#!/usr/bin/env bash
# board-transition.sh — move a ticket to a new state, enforcing the invariants.
#
# Usage:
#   board-transition.sh <number> <to-state> [note] [--branch NAME] [--pr URL]
#
# Enforces transition legality and mandatory notes (blocked/needs-info/wontfix),
# records branch/pr (board:meta), posts notes as [board] comments, and sweeps:
#   → in-progress : the first active child pulls its parent epic(s) to in-progress
#   → done/wontfix: an epic closes when every child is terminal and at least one
#                   is done; a done ticket prints its newly-eligible dependents
#
# Repair path: an issue whose labels are off-machine (zero or 2+ status:*
# labels — lint calls these untracked/conflict) may transition to any OPEN
# state; the write normalizes the label set.
#
# Finalize path: re-running `<n> done` (or wontfix) on an ALREADY-terminal
# issue is not an error — it finalizes a ticket that closed outside the
# machine (a PR's "Closes #N" auto-close): strips residual status labels and
# runs the terminal sweeps. Idempotent.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" to="$2"
shift 2
note="" branch="" pr=""
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then note="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) _need_arg "$1" "${2:-}"; branch="$2"; shift 2 ;;
    --pr) _need_arg "$1" "${2:-}"; pr="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" _py - <<'PY'
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
to, note = env["T_TO"], env["T_NOTE"]
n = tickets[tid]
cur = n["state"]

if to not in B.STATES:
    B.die("unknown state: %s" % to)
if to == cur:
    if cur not in B.TERMINAL:
        B.die("#%s is already %s" % (tid, cur))
    # Finalize: the issue reached this terminal state outside the machine
    # (e.g. a merged PR's "Closes #N" auto-close), so the label strip and the
    # terminal sweeps never ran. Run them now; safe to re-run.
    lines = []
    if n["status_labels"]:
        B.edit_labels(tid, remove=[B.STATUS_PREFIX + s for s in n["status_labels"]])
        n["status_labels"] = []
        lines.append("#%s: %s — stripped residual status labels" % (tid, cur))
    if note:
        B.comment(tid, "[board] %s: %s" % (to, note))
    B.close_epics(tickets, n.get("parent"), lines)
    out = (B.newly_eligible(tickets, tid) if to == "done" else []) + lines
    for ln in out:
        print(ln)
    if not out:
        print("#%s: already %s — nothing to finalize" % (tid, cur))
    raise SystemExit(0)
if cur in (B.UNTRACKED, B.CONFLICT):
    # repair: any open state is reachable; terminal still goes through the machine
    if to in B.TERMINAL:
        B.die("#%s is %s — repair it to an open state first (it has %d status labels)"
              % (tid, cur, len(n["status_labels"])))
elif to not in B.LEGAL[cur]:
    B.die("illegal transition: %s → %s (#%s)" % (cur, to, tid))
if to in B.NOTE_REQUIRED and not note:
    B.die("a note is required when moving to %s" % to)
if to == "in-review" and not env["T_PR"]:
    B.die("a PR link is required when moving to in-review (--pr URL)")

B.ensure_labels()
extra = {}
if env["T_BRANCH"]:
    extra["branch"] = env["T_BRANCH"]
if env["T_PR"]:
    extra["pr"] = env["T_PR"]
lines = [B.apply_state(tickets, tid, to, note, extra_meta=extra)]

# Sweep: first active child pulls its epic chain to in-progress.
if to == "in-progress":
    B.pull_epics(tickets, tid, lines)

# Sweep: a terminal child may close its epic chain.
if to in B.TERMINAL:
    B.close_epics(tickets, n.get("parent"), lines)

# Report dependents this `done` made eligible (derived, nothing written).
eligible_lines = B.newly_eligible(tickets, tid) if to == "done" else []

for ln in eligible_lines + lines:
    print(ln)
PY

