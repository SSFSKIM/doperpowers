#!/usr/bin/env bash
# board-reconcile.sh — read-only catch-up report; NEVER writes anything.
#
# Usage: board-reconcile.sh
#
# Scans daemon replies for proposal blocks the board hasn't applied, flags
# in-progress tickets with no live bound daemon, lists dispatchable tickets,
# and surfaces pending board<->GitHub sync conflicts from SYNC-REPORT.md (if
# board-sync has written one). Applying anything is the orchestrator's judge
# step, via board-transition.sh / the board-sync agent — this script only
# reports.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_DHOME="$DAEMON_HOME" T_BOARD_DIR="$BOARD_DIR" _py - <<'PY'
import glob, json, os, re, shlex

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
    tk = m.get("ticket")
    if not tk:
        continue
    uuid = m.get("uuid", os.path.basename(p)[:-5])
    # A meta whose `ticket` isn't a real board ticket (wrong format or unknown
    # id) must not poison the id-sorted views — flag it and skip. This is the
    # wake-up recovery path, so it stays alive through garbage.
    if not re.match(r"^T[0-9]+$", str(tk)) or tk not in tickets:
        print("anomaly   daemon %s: bound to unknown ticket '%s'" % (uuid[:8], tk))
        continue
    m["_uuid"] = uuid
    bound[tk] = m

def by_id(items):
    return sorted(items, key=lambda kv: int(kv[0][1:]))

# 1. Unapplied proposals in daemon replies (last block for the ticket wins).
STATES = {"ready-for-agent", "in-progress", "blocked", "needs-info",
          "in-review", "done", "wontfix", "deferred"}
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
    if not prop or not prop.get("to"):
        continue
    # `to` is daemon-controlled text headed for a paste-able command — states
    # are a closed set, so whitelist instead of quoting: an unknown state is
    # itself an anomaly (%r keeps the hostile value inert), and no hint prints.
    if prop["to"] not in STATES:
        print("anomaly   %s: daemon proposes unknown state %r" % (t, prop["to"]))
        continue
    if prop["to"] != cur:
        print("proposal  %s: %s → %s  (reason: %s; evidence: %s)" %
              (t, cur, prop["to"], prop.get("reason", "-"), prop.get("evidence", "-")))
        ev = prop.get("evidence")
        if prop["to"] == "in-review" and ev:
            # in-review is PR-gated: carry the proposal's evidence into the hint
            # as the required --pr value so the apply command runs as-printed.
            # shlex-quoted — evidence is semi-trusted daemon reply text, and a
            # `"`/$()/backtick payload must not inject into the printed command.
            print("          apply: board-transition.sh %s in-review --pr %s"
                  % (t, shlex.quote(str(ev))))
        else:
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
        print("dispatch  %s: %s" % (t, " ".join(str(n["title"]).split())))

# 4. Pending board<->GitHub sync conflicts (read-only surface of the board-sync
# agent's SYNC-REPORT.md, whose first line is always "board-sync conflicts: N").
report_path = os.path.join(env["T_BOARD_DIR"], "SYNC-REPORT.md")
if os.path.isfile(report_path):
    with open(report_path) as f:
        first_line = f.readline()
    m = re.match(r"board-sync conflicts:\s*(\d+)", first_line.strip())
    if m and int(m.group(1)) > 0:
        print("board-sync: %d conflict(s) pending (SYNC-REPORT.md)" % int(m.group(1)))
PY
