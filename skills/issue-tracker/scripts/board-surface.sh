#!/usr/bin/env bash
# board-surface.sh — add or remove a ticket's surface:<name> label.
#
# Usage:
#   board-surface.sh <number> --add <name>      label the ticket (name must
#                                               exist in .doperpowers/surfaces.md
#                                               on the default branch)
#   board-surface.sh <number> --remove <name>   unlabel — never validated, so
#                                               it is also the cleanup path for
#                                               an orphaned label whose registry
#                                               entry was deleted, and the
#                                               escape hatch for a false-positive
#                                               identifier match
#
# The ONLY sanctioned write path for surface:* labels outside the automatic
# matching moments (register, lane-entry transition, sweep SURFACE pass) —
# the Board Write Hard Gate covers this family like status:*/priority:*.
# A surface label serializes dispatch: one in-flight Executor worker per
# surface (see execute-dispatch.sh).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

_refuse_no_api_route "editing a surface label"

[ $# -ge 3 ] || { usage_from_header "$0" >&2; exit 2; }
n="$1" op="$2" name="$3"
case "$op" in --add|--remove) ;; *) die "unknown operation: $op" ;; esac

T_N="$n" T_OP="$op" T_NAME="$name" _py - <<'PY'
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_N"], tickets)
name = env["T_NAME"]
label = B.SURFACE_PREFIX + name
if env["T_OP"] == "--add":
    reg = B.surfaces_registry()
    if reg is None:
        B.die("no surfaces registry (.doperpowers/surfaces.md on the default "
              "branch) — surface labels are a closed vocabulary")
    if name not in reg:
        B.die("unknown surface %r — registry entries: %s"
              % (name, ", ".join(sorted(reg)) or "(none)"))
    if name in tickets[tid]["surfaces"]:
        print("#%s: already carries %s" % (tid, label))
    else:
        B.ensure_surface_label(name)
        B.edit_labels(tid, add=(label,))
        print("#%s: surface += %s" % (tid, name))
else:
    if name not in tickets[tid]["surfaces"]:
        B.die("#%s does not carry %s" % (tid, label))
    B.edit_labels(tid, remove=(label,))
    print("#%s: surface -= %s" % (tid, name))
PY

_rerender_if_serving
