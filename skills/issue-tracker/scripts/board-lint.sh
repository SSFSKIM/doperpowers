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
#   FAIL needs-human/needs-info/interactive-preferred without a note (board:meta)
#   FAIL open issue carrying the retired status:blocked label (v8 → needs-human)
#   FAIL open issue carrying the retired status:ready-for-agent label
#        (v9 → ready-for-architect / ready-for-implementer)
#   FAIL dependency cycle among blocked_by edges
#   WARN in-progress issue without an assignee
#   WARN open issue with no priority:* label (legacy — backfill gradually;
#        registration forces one on every new ticket)
#   WARN close candidate: open issue whose linked PRs all merged/closed with
#        at least one merged (skips in-progress/in-review — mid-flight tickets
#        legitimately have a part-1 PR merged). Verify & close, or re-scope.
#
# API mode drops every check above (the server enforces the schema at the write)
# and keeps one the server cannot make: a local daemon still bound to a ticket
# the board has closed or never had.
#
#   FAIL daemon <uuid> bound to closed/absent ticket #<n>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

# API mode collapses nearly all of the above: the board schema is a server
# invariant there (labels, note requirements, cycles and priority grades are
# enforced at the write, not repaired after the fact), so re-checking it from a
# client would only ever report the client's own misreading. What survives is
# the one thing no server can see — the LOCAL daemon registry drifting away
# from the board: a daemon still bound to a ticket the board has closed or
# never had.
if [ "$BOARD_BINDING" = api ]; then
  echo "# board schema is server-enforced in API mode; checking local registry drift only"
  T_DHOME="$DAEMON_HOME" _api_py - <<'PY'
import glob
import json
import os
import _board_api as A

# int() on the server's id, not a bare take: this is the one comparison in the
# check, and the local side of it is parsed out of a registry file as text. A
# type mismatch here would silently match nothing and report a clean board.
# The map keeps the CLOSED rows too, where the old open-only set dropped them:
# "the board closed it" and "the walk never served it" are different findings
# now, and only the second one has to be confirmed before it recommends.
walked = {int(t["id"]): t["state"]
          for t in A.tickets_all(principal="automation")}


def board_state(tid_int):
    """Walk absence is report-grade; a retire recommendation is an ACTION.
    A ticket missing from the walk (a concurrent reprioritization can hide
    a row from every page) is re-read by id — 404 is the authoritative
    absence the recommendation may stand on."""
    if tid_int in walked:
        return walked[tid_int]
    row = A.ticket(tid_int, principal="automation")
    return row["state"] if row else None


fails = 0
for p in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    tid = str(m.get("ticket", "")).lstrip("#")
    # run_id is the API-era binding (board-bind.sh writes it): a meta without
    # one predates the binding or names no run, and has no board claim to drift
    # from. A non-numeric `ticket` is registry garbage, not board drift.
    if not tid.isdigit() or not m.get("run_id"):
        continue
    st = board_state(int(tid))
    if st is None or st in ("done", "wontfix"):
        print("FAIL daemon %s bound to closed/absent ticket #%s FIX: daemon-retire"
              % (m.get("uuid", "?")[:8], tid))
        fails += 1
# The count is the WALK's: it is a report line about the board, and a row the
# walk missed is not one an operator is counting. Only the FAILs above needed
# the stronger evidence.
open_count = sum(1 for s in walked.values() if s not in ("done", "wontfix"))
print("board-lint: %d open ticket(s), %d FAIL" % (open_count, fails))
raise SystemExit(1 if fails else 0)
PY
  exit $?
fi

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

park_needs_note = [s for s in B.NOTE_REQUIRED if s in B.OPEN_STATES]

for tid in sorted(tickets, key=int):
    n = tickets[tid]
    if n["state"] == B.UNTRACKED:
        fail(tid, "open with no status:* label (untracked)",
             "board-transition.sh %s <state> — put it on the board machine" % tid)
    elif n["state"] == B.CONFLICT:
        if n["status_labels"] == ["blocked"]:
            fail(tid, "retired state: status:blocked (v8 folded it into needs-human)",
                 "board-transition.sh %s needs-human \"<carried note>\" — the write swaps the label" % tid)
        elif n["status_labels"] == ["ready-for-agent"]:
            fail(tid, "retired state: status:ready-for-agent (v9 split it into "
                      "ready-for-architect / ready-for-implementer)",
                 "board-transition.sh %s ready-for-implementer \"<carried note>\" — the write "
                 "swaps the label (ready-for-architect instead, per the birth rule, if the "
                 "work is design-heavy)" % tid)
        else:
            fail(tid, "open with %d status:* labels: %s" %
                 (len(n["status_labels"]), ", ".join(n["status_labels"])),
                 "board-transition.sh %s <state> — the write normalizes the label set" % tid)
    if n["state"] in B.TERMINAL and n["status_labels"]:
        fail(tid, "closed but still labeled: %s" % ", ".join(n["status_labels"]),
             "board-transition.sh %s %s — finalize: strips labels + runs the terminal sweeps"
             % (tid, n["state"]))
    if n["state"] in park_needs_note and not n.get("note"):
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
    # (a dispatchable lane state → done is deliberately not a legal transition), so the
    # judgment paths are named instead. ACTIVE states are normal mid-flight
    # shape and skipped (D4 in the ExecPlan).
    if n.get("close_candidate") and n["state"] not in B.ACTIVE:
        warn(tid, "all %d linked PR(s) merged/closed — verify & close "
             "(done if landed / wontfix if superseded), or re-scope"
             % len(n["prs"]))

# Surfaces (closed vocabulary — inert when no registry exists).
reg = B.surfaces_registry()
if reg is not None:
    for bad in sorted(n for n in reg if not B.SURFACE_NAME_RE.match(n) or len(n) > 40):
        fails += 1
        print("FAIL surfaces.md entry %r: name must be kebab-case, <= 40 chars "
              "(it becomes the surface:%s label)" % (bad, bad))
        print("     FIX: rename the entry in .doperpowers/surfaces.md")
    depth = {}
    for tid in sorted(tickets, key=int):
        n = tickets[tid]
        for s in n["surfaces"]:
            if s not in reg:
                fail(tid, "surface label with no registry entry: %s%s"
                     % (B.SURFACE_PREFIX, s),
                     "board-surface.sh %s --remove %s — or land a "
                     ".doperpowers/surfaces.md entry for it" % (tid, s))
            if n["state"] not in B.TERMINAL:
                depth[s] = depth.get(s, 0) + 1
        # Drift: a labeled ticket whose linked PR diffs never touch the
        # surface's paths — stale over-declaration (add-only labeling never
        # removes; a human clears it). Only tickets WITH linked PRs are
        # checkable, and only fetched here, so cost is bounded by the
        # labeled set.
        if n["surfaces"] and n["prs"] and n["state"] not in B.TERMINAL:
            paths = []
            for pr in n["prs"]:
                try:
                    import json as _json
                    pages = _json.loads(B.gh(["api", "--paginate", "--slurp",
                                              "repos/%s/pulls/%s/files"
                                              % (B.repo(), pr["num"])]))
                    files = [f for page in pages or [] for f in page or []]
                    for f in files:
                        paths.append(f.get("filename") or "")
                        if f.get("previous_filename"):
                            paths.append(f["previous_filename"])
                except (SystemExit, ValueError):
                    paths = None
                    break
            if paths is not None:
                for s in n["surfaces"]:
                    if s in reg and reg[s]["paths"] \
                            and not B.match_paths({s: reg[s]}, paths):
                        warn(tid, "surface:%s declared but no linked PR diff "
                             "touches its paths (stale? board-surface.sh %s "
                             "--remove %s)" % (s, tid, s))
    for s in sorted(depth):
        print("SURFACE %s: %d open ticket(s)" % (s, depth[s]))

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
