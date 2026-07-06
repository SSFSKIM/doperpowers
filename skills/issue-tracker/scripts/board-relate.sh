#!/usr/bin/env bash
# board-relate.sh — add or cut a symmetric relates edge between two tickets.
#
# Usage:
#   board-relate.sh <number-a> <number-b> [--cut]
#
# The edge is annotation only — it never affects eligibility. It is stored in
# BOTH issues' board:meta blocks (relates-to) so either ticket's board-show
# sees it; board-map dedupes the pair and renders it once as a dotted line.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
a="$1" b="$2"
shift 2
cut=0
while [ $# -gt 0 ]; do
  case "$1" in
    --cut) cut=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done

T_A="$a" T_B="$b" T_CUT="$cut" _py - <<'PY'
import os
import _board as B

env = os.environ
tickets = B.snapshot()
a = B.resolve(env["T_A"], tickets)
b = B.resolve(env["T_B"], tickets)
cut = env["T_CUT"] == "1"
if a == b:
    B.die("a ticket cannot relate to itself")

def write(t, rels):
    B.update_meta(t, tickets[t],
                  **{"relates-to": " ".join("#%s" % r for r in rels) or None})
    tickets[t]["relates_to"] = rels

ra, rb = tickets[a]["relates_to"], tickets[b]["relates_to"]
if cut:
    if b not in ra and a not in rb:
        B.die("no relates edge between #%s and #%s" % (a, b))
    if b in ra:
        write(a, [r for r in ra if r != b])
    if a in rb:
        write(b, [r for r in rb if r != a])
    print("cut: #%s -- #%s" % (a, b))
else:
    if b in ra or a in rb:
        B.die("#%s and #%s are already related" % (a, b))
    write(a, ra + [b])
    write(b, rb + [a])
    print("related: #%s -- #%s" % (a, b))
PY
