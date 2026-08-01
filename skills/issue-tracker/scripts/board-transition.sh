#!/usr/bin/env bash
# board-transition.sh — move a ticket to a new state, enforcing the invariants.
#
# Usage:
#   board-transition.sh <number> <to-state> [note] [--branch NAME] [--pr URL] [--plan PATH@SHA|pre-spec]
#
# Enforces transition legality and mandatory notes (the park trio + wontfix),
# records branch/pr (board:meta), posts notes as [board] comments, and sweeps:
#   → in-progress : the first active child pulls its parent epic(s) to in-progress
#   → done/wontfix: an epic whose children are all terminal RETURNS to
#                   ready-for-architect for recomposition (E2) — epics are
#                   closed by an Architect's verdict, never by bookkeeping
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
note="" branch="" pr="" plan=""
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then note="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) _need_arg "$1" "${2:-}"; branch="$2"; shift 2 ;;
    --pr) _need_arg "$1" "${2:-}"; pr="$2"; shift 2 ;;
    --plan) _need_arg "$1" "${2:-}"; plan="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" T_PLAN="$plan" _py - <<'PY'
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
# Same ban as board-register.sh (Finding A): a spike has no legal exit
# from ready-for-architect (LEGAL["ready-for-architect"] has no
# in-progress edge, and the spike protocol's gate-pass write IS
# in-progress regardless of which lane queue dispatched it). Close every
# entry into the state, not just the birth one.
if to == "ready-for-architect" and n["category"] == "spike":
    B.die("#%s is a spike — it has no legal exit from ready-for-architect; "
          "it stays in its current lane" % tid)
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
    B.recompose_epics(tickets, n.get("parent"), lines)
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

if (cur, to) in B.EDGE_NOTE_REQUIRED and not note:
    B.die("a note is required on the %s → %s edge" % (cur, to))

if (cur, to) in B.CONVERGENCE_EDGES:
    # Convergence rule (E1 transition 6): count prior traversals of THIS
    # edge since the last [answers] comment; a second traversal converts
    # to a needs-human park. Comments are not in the snapshot — one
    # extra gh call, only on escalation edges.
    import json as _json
    comments = _json.loads(B.gh(["issue", "view", tid, "-R", B.repo(),
                                 "--json", "comments"])).get("comments") or []
    marker = "[board] %s → %s:" % (cur, to)
    count = 0
    for c in comments:
        # real gh (and the Step-3 mock handler) serve [{"body": ...}];
        # tolerate plain strings defensively
        body = ((c.get("body") if isinstance(c, dict) else c) or "").lstrip()
        if body.startswith("[answers]"):
            count = 0
        elif body.startswith(marker):
            count += 1
    if count >= 1:
        note = ("convergence: second traversal of %s → %s — no third "
                "mechanical bounce; this traversal's position: %s — see "
                "the comment trail for the first" % (cur, to, note))
        to = "needs-human"

if to in B.NOTE_REQUIRED and not note:
    B.die("a note is required when moving to %s" % to)
if to == "in-review" and not env["T_PR"] and not n.get("pr"):
    # A RETURN to in-review (the needs-human pre-park: E1 transition 7) never
    # re-supplies --pr — the ticket's board:meta already carries it from the
    # original entry. The invariant is "a ticket in in-review always has a
    # PR recorded", not "every entry carries the flag".
    B.die("a PR link is required when moving to in-review (--pr URL)")
if env["T_PLAN"]:
    import re as _re
    if to != "ready-for-implementer":
        B.die("--plan rides the Architect handoff edge (→ ready-for-implementer) only")
    if env["T_PLAN"] != "pre-spec" and not _re.match(r"^\S+@[0-9a-f]{40}$", env["T_PLAN"]):
        B.die("--plan must be <repo-path>@<full-40-hex-sha> (an immutable pin) or the literal pre-spec")
if to in B.DISPATCHABLE and "(pre-spec: fill in)" in (n.get("body") or ""):
    B.die("#%s is still a pre-spec skeleton — fill the body (gh issue edit "
          "%s --body-file <spec>) before a dispatchable lane state" % (tid, tid))

B.ensure_labels()
extra = {}
if env["T_BRANCH"]:
    extra["branch"] = env["T_BRANCH"]
if env["T_PR"]:
    extra["pr"] = env["T_PR"]
if env["T_PLAN"]:
    extra["plan"] = env["T_PLAN"]
elif to == "ready-for-architect" or (cur == "in-design" and to == "ready-for-implementer"):
    # The plan: pin is void by definition on these two edges — clear it so
    # a superseded pin can never survive into gate-free PLAN-EXECUTION
    # (a real pin authorizes gate-free execution; conflating it with the
    # unrelated `pre-spec` ruling value caused two defects on this branch,
    # so this clears the field outright rather than keying on "has a pin").
    # Entry into ready-for-architect always means the plan is being
    # re-cut (T_PLAN can only be set when to == ready-for-implementer —
    # validated above — so this branch never collides with a fresh pin
    # write). The Architect's own decompose exit
    # (in-design -> ready-for-implementer with no --plan) is a positive
    # "no plan" statement — a pin surviving it is stale by construction.
    # Deliberately NOT extended to other edges into ready-for-implementer:
    # a human unparking from needs-human should not silently void a
    # still-valid plan.
    extra["plan"] = None
if to == "needs-human" and cur in B.PRE_PARK:
    extra["pre-park"] = B.PRE_PARK[cur]
if cur == "needs-human" and to != "needs-human":
    extra["pre-park"] = None
lines = [B.apply_state(tickets, tid, to, note, extra_meta=extra)]

# Sweep: first active child pulls its epic chain to in-progress.
if to == "in-progress":
    B.pull_epics(tickets, tid, lines)

# Sweep: a terminal child may return its epic for recomposition.
if to in B.TERMINAL:
    B.recompose_epics(tickets, n.get("parent"), lines)

# Report dependents this `done` made eligible (derived, nothing written).
eligible_lines = B.newly_eligible(tickets, tid) if to == "done" else []

for ln in eligible_lines + lines:
    print(ln)
PY


_rerender_if_serving
