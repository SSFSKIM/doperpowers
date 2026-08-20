#!/usr/bin/env bash
# board-search.sh — full-text ticket search for the pre-registration dedup /
# prior-art check (query by SEAM: file paths, function names, table names).
#
# Usage: board-search.sh <query> [--states s1,s2] [--bodies]
#
# API mode speaks the paged surface's ?q= (arkho#12): websearch grammar —
# unquoted terms AND, `or` = OR, `-` negation, quoted phrases — judged
# server-side. Rows print in SERVER order across ALL states (a done/wontfix
# hit is prior-art evidence). --states narrows via the promoted filter.
# --bodies hydrates the FIRST ≤20 hits (exactly one budgeted read) and
# prints each body indented under its row; hydration completes BEFORE any
# row prints, so a mid-hydration death leaves no half-printed listing.
# Claim-gated: a run context (BOARD_RUN_TOKEN) dies before any request —
# a run cannot search (its statement of work arrives in the claim payload).
#
# gh mode delegates to the proven spelling `gh issue list --state open
# --limit 200 -R "$BOARD_REPO" --search <query>` (the explicit --limit
# matters: the default caps at 30 and truncates silently; -R is
# unconditional — _lib.sh resolves BOARD_REPO from the checkout when unset,
# the board-comment.sh precedent). gh's search already matches bodies,
# so --bodies is a stderr note and the search proceeds; --states is refused
# (exit 2) — gh's OPEN/CLOSED is not the board's state vocabulary.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

query="" states="" bodies=0
while [ $# -gt 0 ]; do
  case "$1" in
    --states) [ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
              states="$2"; shift 2 ;;
    --bodies) bodies=1; shift ;;
    -*) usage_from_header "$0" >&2; exit 2 ;;
    *) [ -n "$query" ] && { usage_from_header "$0" >&2; exit 2; }
       query="$1"; shift ;;
  esac
done
# Trimmed BEFORE the check: a whitespace-only query is the same non-question
# an empty one is — the server's blank-q 400 is never the first line of
# defense for a caller this client can check itself.
query="$(printf '%s' "$query" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -n "$query" ] || { usage_from_header "$0" >&2; exit 2; }

if [ "$BOARD_BINDING" = api ]; then
  T_Q="$query" T_STATES="$states" T_BODIES="$bodies" _api_py - <<'PY'
import os
import _board_api as A

rows = A.tickets_search(os.environ["T_Q"],
                        states=os.environ["T_STATES"] or None,
                        principal="automation")
states = os.environ["T_STATES"]
print("# %d hit(s), server order, %s" %
      (len(rows), ("states=%s" % states) if states else "all states"))
hydrate = rows[:A._MAX_BODY_IDS]   # the first budgeted read's worth
bodies = {}
if os.environ["T_BODIES"] == "1" and hydrate:
    # Hydration completes BEFORE any row prints: a death here (budget 400,
    # transport) may not leave a half-printed listing.
    bodies = A.tickets_by_ids([t["id"] for t in hydrate],
                              principal="automation", include_body=True)
for t in rows:
    print("#%s %s %s %s" % (t["id"], t["state"],
                            t.get("priority") or "-", t["title"]))
    b = bodies.get(int(t["id"]))
    if b is not None:
        for line in (b.get("body") or "").split("\n"):
            print("    " + line)
if os.environ["T_BODIES"] == "1" and len(rows) > len(hydrate):
    print("# bodies: first %d of %d hits hydrated — narrow the query, or "
          "board-show the rest" % (len(hydrate), len(rows)))
PY
  exit 0
fi

# gh mode.
[ -z "$states" ] || { echo "board-search: --states is API-binding only — gh's OPEN/CLOSED is not the board's state vocabulary" >&2; exit 2; }
[ "$bodies" -eq 0 ] || echo "board-search: gh search already matches bodies — --bodies noted, proceeding" >&2
exec gh issue list --state open --limit 200 -R "$BOARD_REPO" --search "$query"
