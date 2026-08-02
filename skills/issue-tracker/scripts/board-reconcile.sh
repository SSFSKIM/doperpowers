#!/usr/bin/env bash
# board-reconcile.sh — read-only catch-up report; NEVER writes anything.
#
# Usage: board-reconcile.sh
#
# Lists the human wake queue (parked tickets: needs-human / needs-info /
# interactive-preferred), flags in-progress/in-design tickets with no live
# bound daemon, lists dispatchable tickets, and finishes with a board-lint
# pass.
# There is no proposal scanner: v8 workers write their own ticket states and
# register child/follow-up tickets directly (doperpowers:implementing).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob
import json
import os
import re
import _board as B

env = os.environ
tickets = B.snapshot()

bound = {}   # ticket number -> daemon meta
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    tk = m.get("ticket")
    if not tk:
        continue
    uuid = m.get("uuid", os.path.basename(p)[:-5])
    # A meta whose `ticket` isn't a real issue (wrong format or unknown number)
    # must not poison the sorted views — flag it and skip. This is the wake-up
    # recovery path, so it stays alive through garbage.
    tk = str(tk).lstrip("#")
    if not re.match(r"^[0-9]+$", tk) or tk not in tickets:
        print("anomaly   daemon %s: bound to unknown ticket '%s'" % (uuid[:8], m.get("ticket")))
        continue
    m["_uuid"] = uuid
    bound[tk] = m

def by_id(items):
    return sorted(items, key=lambda kv: int(kv[0]))

# 1. The wake queue: parked tickets — every one waits on the human.
#    needs-human = a decision/real-world input only they have; needs-info =
#    research must precede gating; interactive-preferred = take it into a
#    live doperpowers:brainstorming session.
for t, n in by_id(tickets.items()):
    if n["state"] in ("needs-human", "needs-info", "interactive-preferred"):
        note = " ".join((n.get("note") or "(no note — lint FAILs this)").split())
        print("parked    #%s: %s — %s" % (t, n["state"], note))

# 2. in-progress/in-design tickets with a missing or terminal daemon — the
#    two in-flight worker states board-sweep.sh's RECOVER pass covers. An
#    orphaned in-design ticket is mid-design work with nothing local to
#    show for it (the plan lives only in the dead worker's context until
#    its next park/handoff) — the pipeline's most expensive in-flight
#    asset, so it must surface here exactly like an orphaned implementer.
for t, n in by_id(tickets.items()):
    if n["state"] not in ("in-progress", "in-design"):
        continue
    m = bound.get(t)
    if m is None:
        # A PULLED epic has no daemon by design and is not orphaned. A
        # corrective child going active drags its queued parent to in-design
        # (PRE_PARK) purely as bookkeeping — "the parent waits again" — so
        # telling the operator to respawn and bind a worker onto it invents
        # work and would put a second Architect on a live epic. The
        # discriminant is the children: any non-terminal child means they are
        # the ones working, and the epic is just parked in-flight. All
        # children terminal is the other shape — a recomposition claim that
        # SHOULD have a live Architect — and keeps the warning, as does any
        # childless in-design ticket (an ordinary leaf design).
        kids = B.children(tickets, t)
        if n["state"] == "in-design" and any(
                tickets[k]["state"] not in B.TERMINAL for k in kids):
            print("pulled    #%s: in-design with %d live child(ren) — bookkeeping, no worker expected"
                  % (t, sum(1 for k in kids if tickets[k]["state"] not in B.TERMINAL)))
            continue
        print("orphaned  #%s: %s but no bound daemon — respawn + board-bind, or transition" % (t, n["state"]))
    elif m.get("status") in ("error", "retired"):
        print("anomaly   #%s: bound daemon %s status=%s" % (t, m["_uuid"][:8], m["status"]))

# 3. Dispatchable tickets (same rule as board-list eligibility).
for t, n in by_id(tickets.items()):
    if B.eligible(tickets, t):
        print("dispatch  #%s: %s" % (t, " ".join(n["title"].split())))
PY

# 4. Schema invariants over the live board (read-only; FAILs listed with FIX
# lines). Non-fatal here — reconcile is a report, lint's exit code is its own.
"$SCRIPT_DIR/board-lint.sh" || true
