#!/usr/bin/env bash
# test-paged-reads.sh — _board_api.py's PAGED read surface over real HTTP
# (spec: docs/doperpowers/specs/2026-08-18-board-client-paged-reads-design.md).
#
# What this pins:
#   THE ENVELOPE OR NOTHING  a paged read must answer the complete
#                {items, next, as_of}. A bare array is a pre-read-surface
#                server; a dict with no `next` is a malformed page — and
#                reading a MISSING `next` as the contract's `next: null` ends
#                the walk early and hands the caller a partial board wearing
#                the shape of a complete one. Both die.
#   NO PARTIAL BOARD  a page that refuses, and a page whose transport dies
#                through every retry, both kill the walk. The drills print
#                only on success, so a partial result would show up as output.
#   CURSORS ARE OPAQUE  the fixtures carry real base64url tokens (arkho
#                `page.js` `encodeCursor`), and the log is asserted to prove
#                each one went back on the wire VERBATIM.
#   ABSENCE HAS TWO GRADES  a by-id 404 is authoritative absence (None) —
#                but only once the paged surface has been PROVEN in this
#                process, because a route-level 404 from a rolled-back server
#                answers the same stable `not-found` code and would otherwise
#                report every ticket on the board as missing.
#   THE DOCUMENTED CAPS  `limit=200` is the envelope opt-in; `ids=` chunks at
#                arkho API.md §1's 200-id cap; an empty `states=` is a server
#                refusal the client never sends.
#
# Every drill group gets its OWN fixture world (fresh file + server): the mock
# consumes `once` entries globally and matches by path PREFIX, so a single
# shared world would couple each drill's answer to the order the drills run in.
. "$(dirname "$0")/helpers.sh"

free_port() { python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
wait_for_port() {  # poll rather than sleep — a fixed nap is a flake
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then return 0; fi
    tries=$((tries - 1)); sleep 0.05
  done
  return 1
}

TDIR="$(mktemp -d)"
CREDS="$TDIR/creds.env"
printf 'BOARD_AUTOMATION_TOKEN=auto-tok\nBOARD_HUMAN_TOKEN=human-tok\n' > "$CREDS"
MOCK=""
# `wait` after the kill reaps the job here rather than letting bash announce
# "Terminated: 15" into the suite's output on its own schedule.
retire_mock() {
  if [ -n "$MOCK" ]; then
    kill "$MOCK" 2>/dev/null || true
    wait "$MOCK" 2>/dev/null || true
    MOCK=""
  fi
}
trap 'retire_mock; rm -rf "$TDIR"' EXIT

world() {  # world <name>  — fixtures on stdin; retires the previous world
  retire_mock
  FIX="$TDIR/$1.json"; cat > "$FIX"; : > "$FIX.log"
  PORT="$(free_port)"
  python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
  wait_for_port "$PORT" || { echo "FAIL mock server never listened for world $1"; exit 1; }
}

CORE="import _board_api as A"
run_py() { PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
  BOARD_CREDENTIALS_FILE="$CREDS" python3 -c "$1"; }
reqs() { echo "reqs=$(grep -c '"method"' "$FIX.log" || true)"; }
log() { cat "$FIX.log"; }

# Real cursors, produced by arkho's encodeCursor (base64url of the JSON keyset
# triple as SQL text). A synthetic "CURSOR-1" would pass a client that
# re-encoded or truncated the token; these do not.
C1="WyIyMDI2LTA4LTE4IDA0OjE1OjA5LjEyMzQ1NiswMCIsIjMiXQ"
C2="WyIyMDI2LTA4LTE4IDA0OjE1OjA5Ljk4NzY1NCswMCIsIjQiXQ"
Q1="WyIyMDI2LTA4LTE4IDAxOjAyOjAzLjQ1Njc4OSswMCIsImV2dC1hIl0"

# Expected substrings are always INTERPOLATED or %-formatted, never literals in
# the python snippet: a traceback echoes its own source line, so a literal would
# match the very crash the assertion exists to catch.

# ---- by-id reads: the authoritative absence, and its rollback guard ---------
world byid <<'JSON'
[
 {"method":"GET","path":"/tickets/7","status":200,"once":true,
  "body":{"id":7,"title":"the seventh","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null,
          "branch":"feat/seven","blocked_by":[],"relates":[]}},
 {"method":"GET","path":"/tickets/404000","status":404,"once":true,
  "body":{"error":{"code":"not-found","message":"no such ticket: 404000"}}},
 {"method":"GET","path":"/tickets?limit=1","status":200,"once":true,
  "body":{"items":[],"next":null,"as_of":118}}
]
JSON

t "a by-id read answers the one row" "id=7 state=in-progress branch=feat/seven" \
  run_py "$CORE
r = A.ticket(7)
print('id=%s state=%s branch=%s' % (r['id'], r['state'], r['branch']))"
t "and speaks as the human by default" '"auth": "Bearer human-tok"' log

# A 404 is absence — but only once this process has SEEN the paged surface.
t "a by-id 404 reports absence" "absent=True" \
  run_py "$CORE
print('absent=%s' % (A.ticket(404000) is None))"
t "and an unproven process probes the paged surface before trusting it" \
  '"path": "/tickets?limit=1"' log

# The probe answers a question about the SERVER, not about a ticket, so one
# answer settles it for the process. board-lint confirms every absent daemon
# ticket by id, and a probe per confirmation would double that round trip
# count. The probe fixture is `once`, so a second probe would find no fixture,
# take the mock's plain 404 and die — which is the discrimination here.
world probecache <<'JSON'
[
 {"method":"GET","path":"/tickets/404001","status":404,
  "body":{"error":{"code":"not-found","message":"no such ticket: 404001"}}},
 {"method":"GET","path":"/tickets?limit=1","status":200,"once":true,
  "body":{"items":[],"next":null,"as_of":118}},
 {"method":"GET","path":"/tickets/7","status":200,
  "body":{"id":7,"title":"the seventh","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null,
          "branch":"feat/seven","blocked_by":[],"relates":[]}}
]
JSON
t "the probe is spent once per process, not once per absent ticket" \
  "absent=TrueTrue" \
  run_py "$CORE
print('absent=%s%s' % (A.ticket(404001) is None, A.ticket(404001) is None))"
t "so two absent reads cost two requests and one probe" "reqs=3" reqs
# The other half: a successful by-id read proves the surface just as well as
# the probe does, so a 404 arriving after one never probes at all.
t "a successful read proves the surface for the 404s that follow it" \
  "found=7 absent=True" \
  run_py "$CORE
print('found=%s absent=%s' % (A.ticket(7)['id'], A.ticket(404001) is None))"

# The rollback: a server that predates the read surface answers the SAME stable
# `not-found` for an unknown ROUTE. Trusting that as absence would report every
# ticket on the board as missing — board-lint would recommend retiring the
# whole fleet. The probe's bare array is what tells the two apart.
world rollback <<'JSON'
[
 {"method":"GET","path":"/tickets/9","status":404,"once":true,
  "body":{"error":{"code":"not-found","message":"unknown route"}}},
 {"method":"GET","path":"/tickets?limit=1","status":200,"once":true,
  "body":[]}
]
JSON
RB_RC=0
RB_OUT="$(run_py "$CORE
r = A.ticket(9)
print('ABSENT=%s' % (r is None))" 2>&1)" || RB_RC=$?
t "a 404 from a pre-read-surface server dies instead of reporting absence" \
  "pre-read-surface server" echo "$RB_OUT"
nt "and never answers None on the way out" "ABSENT" echo "$RB_OUT"
t "the die exits nonzero" "rc=1" echo "rc=$RB_RC"

# ---- the cursor walk --------------------------------------------------------
# Cursor-bearing entries FIRST: the mock matches by path prefix, so a bare
# `/tickets?limit=200` entry listed first would swallow every cursor request.
world walk <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&cursor=$C2","status":200,"once":true,
  "body":{"items":[{"id":5,"title":"e","category":"work","state":"done",
                    "priority":"P2","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=200&cursor=$C1","status":200,"once":true,
  "body":{"items":[{"id":3,"title":"c","category":"work","state":"parked",
                    "priority":"P1","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]},
                   {"id":4,"title":"d","category":"work","state":"in-progress",
                    "priority":"P1","owner_run":42,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":"$C2","as_of":118}},
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":1,"title":"a","category":"work","state":"in-progress",
                    "priority":"P0","owner_run":41,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]},
                   {"id":2,"title":"b","category":"work","state":"in-progress",
                    "priority":"P0","owner_run":43,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]},
                   {"id":3,"title":"c-early","category":"work","state":"parked",
                    "priority":"P1","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":"$C1","as_of":118}}
]
JSON

# A row whose priority moves mid-walk is re-served on a later page. The walk
# collapses it to ONE row and keeps the LATER read's data — the earlier page's
# copy is the staler one by construction.
t "a three-page walk returns every row once, the later page's data winning" \
  "ids=[1, 2, 3, 4, 5] title3=c" \
  run_py "$CORE
rows = A.tickets_all()
print('ids=%s title3=%s' % (sorted(r['id'] for r in rows),
                            [r['title'] for r in rows if r['id'] == 3][0]))"
t "page 2 carried the first cursor back verbatim" "cursor=$C1" log
t "page 3 carried the second cursor back verbatim" "cursor=$C2" log
t "and the null next ended the walk" "reqs=3" reqs

# ---- a walk that cannot finish never answers -------------------------------
# (a) A REFUSAL mid-walk. Refusals are answers, so request() never retries one.
world refusal <<JSON
[
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":1,"title":"a","category":"work","state":"in-progress",
                    "priority":"P0","owner_run":41,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":"$C1","as_of":118}}
]
JSON
REF_OUT="$(run_py "$CORE
rows = A.tickets_all()
print('PARTIAL rows=%d' % len(rows))" 2>&1 || true)"
t "a refusal mid-walk kills the walk" "refused: http-404" echo "$REF_OUT"
nt "and no partial board escapes it" "PARTIAL" echo "$REF_OUT"

# (b) TRANSPORT loss mid-walk. Page 2's socket dies with no status line at all,
# three times over — one per attempt of request()'s transport retry.
world transport <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&cursor=$C1","disconnect":true,"once":true},
 {"method":"GET","path":"/tickets?limit=200&cursor=$C1","disconnect":true,"once":true},
 {"method":"GET","path":"/tickets?limit=200&cursor=$C1","disconnect":true,"once":true},
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":1,"title":"a","category":"work","state":"in-progress",
                    "priority":"P0","owner_run":41,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":"$C1","as_of":118}}
]
JSON
TR_OUT="$(run_py "$CORE
rows = A.tickets_all()
print('PARTIAL rows=%d' % len(rows))" 2>&1 || true)"
t "a transport loss mid-walk kills the walk after the retries" \
  "unreachable after 3 attempts" echo "$TR_OUT"
nt "and no partial board escapes it either" "PARTIAL" echo "$TR_OUT"
t "the walk spent one request on page 1 and three attempts on page 2" "reqs=4" reqs

# ---- what a final page is, and what it is not ------------------------------
# `next` is computed by over-fetching one row, so an exactly-full final page
# still answers null. A client that asked again "to be sure" would be coding
# against a contract this service does not have.
world exactfull <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":11,"title":"k","category":"work","state":"done",
                    "priority":"P2","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]},
                   {"id":12,"title":"l","category":"spike","state":"done",
                    "priority":"P2","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}}
]
JSON
t "a full final page with a null next is a complete answer" "ids=[11, 12]" \
  run_py "$CORE
print('ids=%s' % sorted(r['id'] for r in A.tickets_all()))"
t "and costs exactly one request" "reqs=1" reqs

# A page with NO `next` key is not a page that ended — it is a malformed or
# version-skewed answer, and reading it as `next: null` is the partial-board
# bug wearing a success code.
world malformed <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":1,"title":"a","category":"work","state":"in-progress",
                    "priority":"P0","owner_run":41,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "as_of":118}}
]
JSON
MAL_OUT="$(run_py "$CORE
rows = A.tickets_all()
print('PARTIAL rows=%d' % len(rows))" 2>&1 || true)"
t "a page missing next dies rather than passing as the end of the walk" \
  "no complete paged envelope" echo "$MAL_OUT"
nt "and answers nothing at all" "PARTIAL" echo "$MAL_OUT"

# The pre-read-surface server on the LIST route: a bare array is not one page.
world barearray <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":[{"id":1,"title":"a","category":"work","state":"in-progress",
           "priority":"P0","owner_run":41,"parent":null,"plan":null,
           "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}]}
]
JSON
BA_OUT="$(run_py "$CORE
rows = A.tickets_all()
print('PARTIAL rows=%d' % len(rows))" 2>&1 || true)"
t "a bare array from the list route dies naming the missing envelope" \
  "no complete paged envelope" echo "$BA_OUT"
nt "and never passes as a complete board" "PARTIAL" echo "$BA_OUT"

# ---- the promoted `states` filter ------------------------------------------
# Longest paths first — prefix matching would otherwise hand the non-empty
# filter the empty filter's refusal.
world states <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200&states=ready-for-architect,ready-for-implementer",
  "status":200,"once":true,
  "body":{"items":[{"id":21,"title":"u","category":"work","state":"ready-for-architect",
                    "priority":"P1","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=200&states=","status":400,
  "body":{"error":{"code":"invalid-argument",
                   "message":"states must be comma-separated state names, got empty"}}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[],"next":null,"as_of":118}}
]
JSON
run_py "$CORE
A.tickets_all(states='')" > /dev/null 2>&1 || true
nt "an empty states filter is never put on the wire" "states=" log
t "a non-empty states filter returns the server's filtered page" "ids=[21]" \
  run_py "$CORE
print('ids=%s' % sorted(r['id'] for r in
      A.tickets_all(states='ready-for-architect,ready-for-implementer')))"
t "and reached the wire as given" \
  "states=ready-for-architect,ready-for-implementer" log
t "and the server's refusal of the empty one is surfaced verbatim" \
  "refused: invalid-argument" \
  run_py "$CORE
try: A.request('GET', '/tickets?limit=200&states=', principal='human')
except SystemExit: pass"

# ---- the ids= batch --------------------------------------------------------
# The filter answers the rows it found; it does not 404 on an id it did not.
# So an id missing from a COMPLETED response is authoritatively absent — which
# is what makes this a targeted read rather than a walk.
world byids <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200&ids=7,8,9","status":200,"once":true,
  "body":{"items":[{"id":7,"title":"g","category":"work","state":"in-progress",
                    "priority":"P1","owner_run":41,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]},
                   {"id":9,"title":"i","category":"work","state":"parked",
                    "priority":"P1","owner_run":null,"parent":null,"plan":null,
                    "pr_url":null,"branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}}
]
JSON
t "an ids batch keys by int, and an id the server did not return has no key" \
  "keys=[7, 9] absent8=True" \
  run_py "$CORE
out = A.tickets_by_ids([7, 8, 9])
print('keys=%s absent8=%s' % (sorted(out), 8 not in out))"
t "and rode a single request" "reqs=1" reqs

# 200 ids per call is a documented BOUND (arkho API.md §1): 201 is a 400, not a
# truncated answer, so the chunking is the contract and not an optimization.
world chunk <<'JSON'
[
 {"method":"GET","path":"/tickets?limit=200&ids=","status":200,
  "body":{"items":[],"next":null,"as_of":118}}
]
JSON
run_py "$CORE
A.tickets_by_ids(range(1, 402))" > /dev/null 2>&1 || true
t "401 ids chunk into three requests" "reqs=3" reqs
ids_range() { python3 -c "print('ids=' + ','.join(str(i) for i in range($1, $2)))"; }
t "the first chunk stops at the 200-id cap" "$(ids_range 1 201)\"" log
t "the second chunk takes the next 200" "$(ids_range 201 401)\"" log
t "the third carries the remainder" "$(ids_range 401 402)\"" log

# ---- the decisions queue walk ----------------------------------------------
# Queue rows carry no `id` at all — identity is correlation_id — and the
# (raised_at, correlation_id) keyset is immutable, so a row can never move
# between pages. Hence no dedupe, and order is the order served.
world queue <<JSON
[
 {"method":"GET","path":"/queue/decisions?limit=200&cursor=$Q1","status":200,"once":true,
  "body":{"items":[{"correlation_id":"evt-204","ticket_id":9,"run_id":44,
                    "species":"board","question":{"note":"the second question"},
                    "raised_at":"2026-08-18T02:00:00Z","state":"needs-human",
                    "category":"work"}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/queue/decisions?limit=200","status":200,"once":true,
  "body":{"items":[{"correlation_id":"evt-118","ticket_id":8,"run_id":41,
                    "species":"board","question":{"note":"the first question"},
                    "raised_at":"2026-08-18T01:00:00Z","state":"needs-human",
                    "category":"work"}],
          "next":"$Q1","as_of":118}}
]
JSON
t "a two-page queue walk keeps every correlation id, in the order served" \
  "cids=['evt-118', 'evt-204']" \
  run_py "$CORE
print('cids=%s' % [r['correlation_id'] for r in A.queue_decisions_all()])"
t "the queue cursor went back verbatim too" "cursor=$Q1" log

finish
