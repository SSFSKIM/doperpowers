#!/usr/bin/env bash
# board-show.sh — one ticket in full: node JSON, issue URL, bound daemon.
#
# Usage: board-show.sh <number>
#
# The daemon binding lives in the daemon registry (a `ticket` key in the
# daemon's meta JSON — see board-bind.sh), never on the issue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
# The arity guard sits ahead of the binding branch so both bindings answer a
# bad invocation the same way (usage on stderr, exit 2).
[ $# -eq 1 ] || { usage_from_header "$0" >&2; exit 2; }

if [ "$BOARD_BINDING" = api ]; then
  # API mode prints the ticket row followed by its server-side timeline, one
  # record per line as `[<source>:<cursor>] <kind> <note-or-empty>` — the
  # timeline IS the ticket's history there, so there is nothing else to show.
  # This note is indented into the branch rather than sitting in the header
  # block on purpose: usage_from_header echoes every column-0 `#` line, and a
  # bad invocation should print the usage, not the binding essay.
  T_ID="$1" _api_py - <<'PY'
import os
import _board_api as A

tid = os.environ["T_ID"].lstrip("#")
for t in A.tickets(principal="automation"):
    if str(t["id"]) == tid:
        print("#%s %s %s %s  owner_run=%s plan=%s pr=%s" %
              (t["id"], t["state"], t.get("priority") or "-", t["title"],
               t.get("owner_run"), t.get("plan"), t.get("pr_url")))
        break
else:
    A.die("no ticket #%s" % tid)
for r in A.timeline(tid, principal="automation")["records"]:
    note = (r.get("body") or {}).get("note") or ""
    print("[%s:%s] %s %s" % (r["source"], r["cursor"], r["kind"], note))
PY
  exit 0
fi

T_ID="$1" T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob
import json
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
n = dict(tickets[tid])
n.pop("body", None)   # the issue body is one `gh issue view` away — keep this scannable
n.pop("id", None)
print(json.dumps({"#" + tid: n}, indent=2))
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if str(m.get("ticket", "")).lstrip("#") == tid:
        print("daemon: %s  status=%s  cwd=%s  worktree=%s" %
              (m.get("uuid", os.path.basename(p)[:-5]), m.get("status"),
               m.get("cwd"), m.get("worktree") or "-"))
        break
else:
    print("daemon: (none bound)")
PY
