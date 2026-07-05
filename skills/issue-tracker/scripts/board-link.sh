#!/usr/bin/env bash
# board-link.sh — link a ticket to its GitHub issue, or backfill links from titles.
#
# Usage:
#   board-link.sh <id> --gh N     set the ticket's GitHub issue number
#   board-link.sh --backfill      one-time: parse "(GH#NN)" from every title → gh
#                                  (only where gh is unset; never overwrites)
#
# After --backfill the board never depends on title text again.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 1 ] || { usage_from_header "$0" >&2; exit 2; }
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

if [ "$1" = "--backfill" ]; then
  T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, re
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
filled = 0
log = []
for tid in sorted(board["tickets"], key=lambda k: int(k[1:])):
    t = board["tickets"][tid]
    if t.get("gh"):
        continue
    m = re.search(r"GH#(\d+)", t.get("title", ""))
    if m:
        t["gh"] = int(m.group(1)); t["updated"] = env["T_TODAY"]; filled += 1
        log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "gh", "op": "set", "value": t["gh"]})
        print("%s: gh = %d (from title)" % (tid, t["gh"]))
tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in log:
        f.write(json.dumps(e) + "\n")
print("backfilled %d ticket(s)" % filled)
PY
  "$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
    || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
  exit 0
fi

# else: <id> --gh N — delegate to board-meta
tid="$1"; shift
[ "${1:-}" = "--gh" ] || { usage_from_header "$0" >&2; exit 2; }
_need_arg "$1" "${2:-}"
exec "$SCRIPT_DIR/board-meta.sh" "$tid" --gh "$2"
