#!/usr/bin/env bash
# board-search.sh — full-text ticket search for the pre-registration dedup /
# prior-art check (query by SEAM: file paths, function names, table names).
#
# Usage: board-search.sh [--states s1,s2] [--bodies] [--all-repos] [--] <query>
#
# --all-repos (API binding only) widens the search past the repo the binding
# speaks for, to every repo the board service holds — prior art is prior art
# wherever it was filed. The header says when it is on. Off by default, and
# every non-browse verb in the toolkit always narrows.
#
# API mode speaks the paged surface's ?q= (arkho#12): websearch grammar —
# unquoted terms AND, `or` = OR, `-` negation, quoted phrases — judged
# server-side. A query that LEADS with the negation `-` rides behind `--`
# (board-search.sh -- "-deprecated migration"); without it the leading dash
# reads as a flag. Rows print in SERVER order across ALL states (a done/wontfix
# hit is prior-art evidence). --states narrows via the promoted filter (an
# empty value is a usage error, not a silent widening back to all states).
# --bodies hydrates the FIRST ≤20 hits (exactly one budgeted read) and
# prints each body indented under its row; hydration completes BEFORE any
# output at all, so a mid-hydration death leaves no partial listing.
# Claim-gated: a run context (BOARD_RUN_TOKEN) dies before any request —
# a run cannot search (its statement of work arrives in the claim payload).
#
# gh mode delegates to `gh issue list --state all --limit 200
# -R "$BOARD_REPO" --search <query>`. --state all because a closed hit IS the
# prior-art evidence this verb exists to find — the same reason the API arm
# spans every state. The explicit --limit matters: the default caps at 30 and
# truncates silently; -R is unconditional — _lib.sh resolves BOARD_REPO from
# the checkout when unset, the board-comment.sh precedent. gh's search already
# matches bodies, so --bodies is a stderr note and the search proceeds;
# --states is refused (exit 2) — gh's OPEN/CLOSED is not the board's state
# vocabulary.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

query="" states="" bodies=0 all_repos=0
while [ $# -gt 0 ]; do
  case "$1" in
    # An empty value is refused with the missing one: `--states ""` is
    # indistinguishable from "flag absent" once assigned, and silently
    # widening back to all states is not what that caller asked for.
    --states) [ $# -ge 2 ] && [ -n "$2" ] || { usage_from_header "$0" >&2; exit 2; }
              states="$2"; shift 2 ;;
    --bodies) bodies=1; shift ;;
    --all-repos) all_repos=1; shift ;;
    # End of options — the one route to a query that leads with the `-`
    # negation, which the arm below would otherwise read as a flag.
    --) shift
        [ $# -eq 1 ] && [ -z "$query" ] || { usage_from_header "$0" >&2; exit 2; }
        query="$1"; shift ;;
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
  T_Q="$query" T_STATES="$states" T_BODIES="$bodies" T_ALL_REPOS="$all_repos" _api_py - <<'PY'
import os
import _board_api as A

all_repos = os.environ["T_ALL_REPOS"] == "1"
rows = A.tickets_search(os.environ["T_Q"],
                        states=os.environ["T_STATES"] or None,
                        principal="automation", all_repos=all_repos)
states = os.environ["T_STATES"]
hydrate = rows[:A._MAX_BODY_IDS]   # the first budgeted read's worth
bodies = {}
if os.environ["T_BODIES"] == "1" and hydrate:
    # Hydration completes BEFORE anything prints — the header included: a
    # death here (budget 400, transport) leaves NO listing rather than a
    # partial one, which is why the header waits below.
    # The hydration carries the SAME scope as the search that produced the
    # ids: narrowed by default, and widened when the search was — otherwise a
    # widened search would list foreign hits and then silently print no body
    # for any of them.
    bodies = A.tickets_by_ids([t["id"] for t in hydrate],
                              principal="automation", include_body=True,
                              all_repos=all_repos)
print("# %d hit(s), server order, %s%s" %
      (len(rows), ("states=%s" % states) if states else "all states",
       " — all repos" if all_repos else ""))
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
[ "$all_repos" -eq 0 ] || { echo "board-search: --all-repos is API-binding only — a gh board is one repo" >&2; exit 2; }
[ "$bodies" -eq 0 ] || echo "board-search: gh search already matches bodies — --bodies noted, proceeding" >&2
exec gh issue list --state all --limit 200 -R "$BOARD_REPO" --search "$query"
