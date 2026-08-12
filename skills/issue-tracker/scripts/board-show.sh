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
  T_ID="$1" _api_py - <<'PY'
import json
import os
import _board_api as A

tid = os.environ["T_ID"].lstrip("#")
for t in A.tickets(principal="automation"):
    if str(t["id"]) == tid:
        # The projection carries branch and both edge arrays (arkho#7); this
        # header is the only place API mode shows them. No edges is an ordinary
        # state, so an empty array prints as [] rather than dropping the column.
        print("#%s %s %s %s  owner_run=%s plan=%s pr=%s branch=%s "
              "blocked_by=[%s] relates=[%s]" %
              (t["id"], t["state"], t.get("priority") or "-", t["title"],
               t.get("owner_run"), t.get("plan"), t.get("pr_url"),
               t.get("branch"),
               " ".join(str(b) for b in t.get("blocked_by") or []),
               " ".join(str(x) for x in t.get("relates") or [])))
        break
else:
    A.die("no ticket #%s" % tid)
for r in A.timeline(tid, principal="automation")["records"]:
    # A1's event bodies are TYPED, not one `note` field: an answer carries
    # `replies` (a list), the E2 comment kinds carry their own payload keys, a
    # claim carries its lane and run. Rendering `note` alone printed every
    # successor-visible human answer, every parent impact and every closure
    # package BLANK — and "read your own ticket timeline FIRST" is the first
    # instruction a successor is given, with this as the only place that
    # history exists.
    body = r.get("body")
    if not isinstance(body, dict):
        text = "" if body is None else str(body)
    else:
        parts = [str(body[k]) for k in ("note", "text") if body.get(k)]
        parts += [str(x) for x in (body.get("replies") or [])]
        rest = {k: v for k, v in body.items()
                if k not in ("note", "text", "replies")}
        if rest:
            parts.append(json.dumps(rest, sort_keys=True))
        text = "\n".join(parts)
    head = "[%s:%s] %s" % (r["source"], r["cursor"], r["kind"])
    # One record, one entry — but a reply is multi-line by nature, so the tail
    # is INDENTED under its header rather than run together or truncated. An
    # unindented continuation would read as another record.
    lines = text.split("\n")
    print("%s %s" % (head, lines[0]))
    for extra in lines[1:]:
        print("    " + extra)
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
