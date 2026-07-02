#!/usr/bin/env bash
# board-reconcile.sh — read-only catch-up report; NEVER writes anything.
#
# Usage: board-reconcile.sh
#
# Scans daemon replies for proposal blocks the board hasn't applied, flags
# in-progress tickets with no live bound daemon, and lists dispatchable
# tickets. Applying anything is the orchestrator's judge step, via
# board-transition.sh — this script only reports.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob, json, os, re

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

bound = {}   # ticket id -> daemon meta
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if m.get("ticket"):
        m["_uuid"] = m.get("uuid", os.path.basename(p)[:-5])
        bound[m["ticket"]] = m

def by_id(items):
    return sorted(items, key=lambda kv: int(kv[0][1:]))

# 1. Unapplied proposals in daemon replies (last block for the ticket wins).
for t, m in by_id(bound.items()):
    reply = os.path.join(env["T_DHOME"], "%s.reply.txt" % m["_uuid"])
    if not os.path.exists(reply):
        continue
    with open(reply) as f:
        blocks = re.findall(r'\{[^{}]*"ticket"[^{}]*\}', f.read())
    prop = None
    for raw in reversed(blocks):
        try:
            cand = json.loads(raw)
        except ValueError:
            continue
        if cand.get("ticket") == t:
            prop = cand
            break
    cur = tickets.get(t, {}).get("state")
    if prop and prop.get("to") and prop["to"] != cur:
        print("proposal  %s: %s → %s  (reason: %s; evidence: %s)" %
              (t, cur, prop["to"], prop.get("reason", "-"), prop.get("evidence", "-")))
        print("          apply: board-transition.sh %s %s" % (t, prop["to"]))

# 2. in-progress tickets with a missing or terminal daemon.
for t, n in by_id(tickets.items()):
    if n["state"] != "in-progress":
        continue
    m = bound.get(t)
    if m is None:
        print("orphaned  %s: in-progress but no bound daemon — respawn + board-bind, or transition" % t)
    elif m.get("status") in ("error", "retired"):
        print("anomaly   %s: bound daemon %s status=%s" % (t, m["_uuid"][:8], m["status"]))

# 3. Dispatchable tickets (same rule as board-list eligibility).
epics = {n["parent"] for n in tickets.values() if n.get("parent")}
for t, n in by_id(tickets.items()):
    if n["state"] == "ready-for-agent" and t not in epics \
       and all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", [])):
        print("dispatch  %s: %s" % (t, n["title"]))
PY
