#!/usr/bin/env bash
# board-show.sh — one ticket in full. API mode: header, statement of work
# (body), timeline. gh mode: node JSON, issue URL, bound daemon.
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

tid = A.ref(os.environ["T_ID"])   # '#12' → 12, and a junk ref dies as a junk
                                  # ref rather than as a request nobody can build
run_ctx = bool(A.run_context())
# The body rides the by-id read for every non-run reader — "one ticket in
# full" finally includes the statement of work. A run context omits the
# opt-in (the server refuses the class; its body arrived in the claim
# payload) so the worker bootstrap's timeline read keeps working unchanged.
t = A.ticket(tid, principal="automation", include_body=not run_ctx)
if t is None:
    # A targeted 404 is AUTHORITATIVE absence: the ticket is not on this board.
    # The whole-board scan this replaces could only ever prove it was not in
    # the response it happened to read.
    A.die("no ticket #%s" % tid)
# The projection carries branch and both edge arrays (arkho#7); this header is
# the only place API mode shows them. No edges is an ordinary state, so an
# empty array prints as [] rather than dropping the column.
print("#%s %s %s %s  owner_run=%s plan=%s pr=%s branch=%s "
      "blocked_by=[%s] relates=[%s]" %
      (t["id"], t["state"], t.get("priority") or "-", t["title"],
       t.get("owner_run"), t.get("plan"), t.get("pr_url"),
       t.get("branch"),
       " ".join(str(b) for b in t.get("blocked_by") or []),
       " ".join(str(x) for x in t.get("relates") or [])))
print()
if run_ctx:
    print("body: claim-served (a run reads its statement of work from "
          "the claim payload)")
else:
    print(t.get("body") or "")
print()
# THE TIMELINE IS A FLAT READ. GET /tickets/:id/timeline has no paged form at
# all: arkho API.md §4.2 serves both halves whole and calls their cursors "the
# seam a paged read would grow from" — so there is no cap to page against and
# no envelope to walk. Sound at any per-ticket event count a board reaches
# today; a ticket whose history outgrows one response is arkho work.
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
