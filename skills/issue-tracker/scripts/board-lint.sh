#!/usr/bin/env bash
# board-lint.sh — single-store invariant validation (replaces reconciliation).
#
# Usage: board-lint.sh
#
# GitHub is the only board store, so there is nothing to sync — but raw label
# edits can still break the board schema. This names every violation with a
# FIX command. Exit 1 when any FAIL is found (WARNs alone exit 0).
#
#   FAIL open issue with zero status:* labels (untracked)
#   FAIL open issue with 2+ status:* labels (conflict)
#   FAIL open issue with 2+ priority:* labels, or an invalid grade
#   FAIL closed issue still carrying status:* labels
#   FAIL blocked/needs-info without a note (board:meta)
#   FAIL dependency cycle among blocked_by edges
#   WARN in-progress issue without an assignee
#   WARN open issue with no priority:* label (legacy — backfill gradually;
#        registration forces one on every new ticket)
#   WARN close candidate: open issue whose linked PRs all merged/closed with
#        at least one merged (skips in-progress/in-review — mid-flight tickets
#        legitimately have a part-1 PR merged). Verify & close, or re-scope.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

_py - <<'PY'
import _board as B

tickets = B.snapshot()
fails = warns = 0

def fail(tid, msg, fix):
    global fails
    fails += 1
    print("FAIL #%s: %s" % (tid, msg))
    print("     FIX: %s" % fix)

def warn(tid, msg):
    global warns
    warns += 1
    print("WARN #%s: %s" % (tid, msg))

for tid in sorted(tickets, key=int):
    n = tickets[tid]
    if n["state"] == B.UNTRACKED:
        fail(tid, "open with no status:* label (untracked)",
             "board-transition.sh %s <state> — put it on the board machine" % tid)
    elif n["state"] == B.CONFLICT:
        fail(tid, "open with %d status:* labels: %s" %
             (len(n["status_labels"]), ", ".join(n["status_labels"])),
             "board-transition.sh %s <state> — the write normalizes the label set" % tid)
    if n["state"] in B.TERMINAL and n["status_labels"]:
        fail(tid, "closed but still labeled: %s" % ", ".join(n["status_labels"]),
             "board-transition.sh %s %s — finalize: strips labels + runs the terminal sweeps"
             % (tid, n["state"]))
    if n["state"] in ("blocked", "needs-info") and not n.get("note"):
        fail(tid, "%s without a note" % n["state"],
             "board-transition.sh %s %s \"<why>\" — or move it on" % (tid, n["state"]))
    if n["state"] == "in-progress" and not n["assignees"]:
        warn(tid, "in-progress with no assignee")
    # Priority: exactly one priority:* on every open ticket. Missing is WARN
    # only — legacy boards predate the axis and backfill gradually; a double
    # label is an invariant violation regardless of history.
    if n["state"] not in B.TERMINAL:
        if len(n["priority_labels"]) >= 2:
            valid = sorted(p for p in n["priority_labels"] if p in B.PRIORITIES)
            pick = valid[0] if valid else "P2"
            fail(tid, "%d priority:* labels: %s" %
                 (len(n["priority_labels"]), ", ".join(n["priority_labels"])),
                 "board-priority.sh %s %s — the write normalizes the label set"
                 % (tid, pick))
        elif n["priority_labels"] and n["priority_labels"][0] not in B.PRIORITIES:
            fail(tid, "invalid priority label: %s%s" %
                 (B.PRIORITY_PREFIX, n["priority_labels"][0]),
                 "board-priority.sh %s P2 — the write normalizes the label set" % tid)
        elif not n["priority_labels"]:
            warn(tid, "no priority label (backfill: board-priority.sh %s <P0..P3>)" % tid)
    # Close candidate (derived, never a label): every linked PR landed or died,
    # at least one merged, yet the issue is open — usually a PR that skipped
    # "Closes #N". A triage cue, not a violation: no one-line FIX exists
    # (ready-for-agent → done is deliberately not a legal transition), so the
    # judgment paths are named instead. ACTIVE states are normal mid-flight
    # shape and skipped (D4 in the ExecPlan).
    if n.get("close_candidate") and n["state"] not in B.ACTIVE:
        warn(tid, "all %d linked PR(s) merged/closed — verify & close "
             "(done if landed / wontfix if superseded), or re-scope"
             % len(n["prs"]))

# Dependency cycles (GitHub does not forbid mutual blocking).
color = {}
def visit(t, path):
    color[t] = 1
    for b in tickets[t]["blocked_by"]:
        if b not in tickets:
            continue
        if color.get(b) == 1:
            cyc = path[path.index(b):] if b in path else [b, t]
            fail(t, "dependency cycle: %s" % " → ".join("#%s" % x for x in cyc + [b]),
                 "board-edge.sh %s --unblock %s (or re-cut elsewhere in the cycle)" % (t, b))
        elif color.get(b) is None:
            visit(b, path + [b])
    color[t] = 2

for t in sorted(tickets, key=int):
    if color.get(t) is None:
        visit(t, [t])

print("board-lint: %d issue(s), %d FAIL, %d WARN" % (len(tickets), fails, warns))
raise SystemExit(1 if fails else 0)
PY
