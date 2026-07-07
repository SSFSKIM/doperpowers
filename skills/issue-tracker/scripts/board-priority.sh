#!/usr/bin/env bash
# board-priority.sh — set a ticket's priority (managed priority:* label swap).
#
# Usage:
#   board-priority.sh <number> <P0|P1|P2|P3>
#
# Swaps the ticket's priority:* label set to exactly the given grade (also
# repairs a double label). Prints the move: "#12: P2 → P0" — "none" on the
# left when the ticket had no priority yet. Re-running with the same grade
# is a no-op that still reports.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }

T_ID="$1" T_P="$2" _py - <<'PY'
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
to = env["T_P"]
if to not in B.PRIORITIES:
    B.die("priority must be one of %s" % "|".join(B.PRIORITIES))

n = tickets[tid]
old = n["priority"] or ("+".join(n["priority_labels"]) if n["priority_labels"] else "none")
B.ensure_labels()
B.set_priority_label(tid, n, to)
print("#%s: %s → %s" % (tid, old, to))
PY

_rerender_if_serving
