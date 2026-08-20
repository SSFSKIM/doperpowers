#!/usr/bin/env bash
# test-agent-grade-reads.sh — the client side of arkho#12: tickets_search,
# include_body hydration, the claim-gate guard, board-search.sh, and
# board-show.sh's body (spec:
# docs/doperpowers/specs/2026-08-20-client-agent-grade-reads-design.md).
#
# What this pins:
#   THE WIRE SPELLING  q rides urlencoded (space = %20, never +) inside one
#                parameter; include=body appears iff requested; body
#                hydration chunks at the 20-id cap (a 21-id read is TWO
#                requests, split 20/1).
#   CLAIM-GATED  a run context (BOARD_RUN_TOKEN) dies BEFORE any request —
#                reqs=[0] is the assertion, not the message alone.
#   ONE ROW SPELLING  a hydrated row minus `body` deep-equals its plain twin.
. "$(dirname "$0")/helpers.sh"

free_port() { python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
wait_for_port() {
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
retire_mock() {
  if [ -n "$MOCK" ]; then
    kill "$MOCK" 2>/dev/null || true
    wait "$MOCK" 2>/dev/null || true
    MOCK=""
  fi
}
trap 'retire_mock; rm -rf "$TDIR"' EXIT

world() {  # world <name> — fixtures on stdin; retires the previous world
  retire_mock
  FIX="$TDIR/$1.json"; cat > "$FIX"; : > "$FIX.log"
  PORT="$(free_port)"
  python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
  wait_for_port "$PORT" || { echo "FAIL mock server never listened for world $1"; exit 1; }
}

run_py() { PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
  BOARD_CREDENTIALS_FILE="$CREDS" python3 -c "$1"; }
run_py_as_run() { PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
  BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=run-tok python3 -c "$1"; }
reqs() { echo "reqs=[$(grep -c '"method"' "$FIX.log" || true)]"; }
paths() { python3 -c 'import json, sys
print("paths=[%s]" % " ".join(json.loads(ln)["path"]
                              for ln in open(sys.argv[1]) if ln.strip()))' "$FIX.log"; }

row() {  # row <id> <state> <title> [body]  — one contract-shaped ticket row
  python3 -c 'import json, sys
r = {"id": int(sys.argv[1]), "title": sys.argv[3], "category": "work",
     "state": sys.argv[2], "priority": "P2", "owner_run": None,
     "parent": None, "plan": None, "pr_url": None, "branch": None,
     "blocked_by": [], "relates": []}
if len(sys.argv) > 4: r["body"] = sys.argv[4]
print(json.dumps(r))' "$@"
}

# ---- tickets_search: wire spelling + walk + dedupe ----
# A real-shaped cursor (unpadded base64url of a keyset triple). The client
# passes `next` back VERBATIM — the walk drill pins that, plus completeness.
# Fixture order is longest-prefix-first: the cursor-bearing entry goes FIRST,
# or the page-1 entry prefix-swallows the page-2 request.
SC="WyJQMSIsIjIwMjYtMDgtMTggMDQ6MTU6MDkuMTIzNDU2KzAwIiwiMyJd"
world search <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=alpha%20beta&cursor=$SC","status":200,
  "body":{"items":[$(row 7 ready-for-implementer "alpha beta now")],
          "next":null,"as_of":9}},
 {"method":"GET","path":"/tickets?limit=200&q=alpha%20beta","status":200,
  "body":{"items":[$(row 3 "done" "alpha beta prior art")],
          "next":"$SC","as_of":9}}
]
JSON
t "search walks every page and answers the hits" "[3, 7]" \
  run_py "import _board_api as A
print(sorted(t['id'] for t in A.tickets_search('alpha beta')))"
t "search urlencodes the space as %20" "q=alpha%20beta" paths
t "the walk followed the cursor: two pages" "reqs=[2]" reqs

world search-states <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=x&states=done","status":200,
  "body":{"items":[$(row 3 "done" "x archived")],"next":null,"as_of":4}}
]
JSON
run_py "import _board_api as A
A.tickets_search('x', states='done')" >/dev/null || true
t "states composes onto the search path" "states=done" paths

# ---- include_body: 20-chunk boundary + body-iff-requested parity ----
# NOT process substitution: bash 3.2 (the suite's runtime) brace-expands the
# heredoc body while scanning <( … ) and a dict literal's comma breaks it.
python3 - > "$TDIR/hydrate.src" <<'PY'
import json
def row(i, body=None):
    r = {"id": i, "title": "T%d" % i, "category": "work",
         "state": "ready-for-implementer", "priority": "P2",
         "owner_run": None, "parent": None, "plan": None, "pr_url": None,
         "branch": None, "blocked_by": [], "relates": []}
    if body is not None: r["body"] = body
    return r
first = ",".join(str(i) for i in range(1, 21))
print(json.dumps([
  {"method": "GET",
   "path": "/tickets?limit=200&ids=%s&include=body" % first, "status": 200,
   "body": {"items": [row(i, "B%d" % i) for i in range(1, 21)],
            "next": None, "as_of": 30}},
  {"method": "GET", "path": "/tickets?limit=200&ids=21&include=body",
   "status": 200,
   "body": {"items": [row(21, "B21")], "next": None, "as_of": 30}},
  {"method": "GET", "path": "/tickets?limit=200&ids=21", "status": 200,
   "body": {"items": [row(21)], "next": None, "as_of": 30}}
]))
PY
world hydrate < "$TDIR/hydrate.src"
t "21 hydrated ids come back whole" "B21" \
  run_py "import _board_api as A
out = A.tickets_by_ids(range(1, 22), include_body=True)
print(out[21]['body'])"
t "the hydration split into two chunks at 20" "reqs=[2]" reqs
t "include=body rode each chunk" "ids=21&include=body" paths
t "a hydrated row minus body equals its plain twin" "parity-ok" \
  run_py "import _board_api as A
fat = A.tickets_by_ids([21], include_body=True)[21]
plain = A.tickets_by_ids([21])[21]
assert 'body' not in plain, plain
thin = {k: v for k, v in fat.items() if k != 'body'}
assert thin == plain, (thin, plain)
print('parity-ok')"

# ---- the claim-gate guard: dies pre-request ----
world gated <<JSON
[]
JSON
t "search in a run context dies claim-gated" "claim-gated" \
  run_py_as_run "import _board_api as A
A.tickets_search('x')"
t "hydration in a run context dies claim-gated" "claim-gated" \
  run_py_as_run "import _board_api as A
A.tickets_by_ids([1], include_body=True)"
t "by-id include_body in a run context dies claim-gated" "claim-gated" \
  run_py_as_run "import _board_api as A
A.ticket(1, include_body=True)"
t "no gated call reached the wire" "reqs=[0]" reqs

# ---- board-search.sh: API arm ----
# A stub gh on PATH for every API-arm call: "API mode never invokes gh" is
# asserted, not assumed (test-read-verbs.sh precedent).
GHSTUB="$TDIR/ghbin"; mkdir -p "$GHSTUB"
# The stub answers `gh repo view` (which _lib.sh calls to resolve BOARD_REPO
# in gh mode) with a fixed slug, and echoes everything else — so the spelling
# drill sees a deterministic `-R o/r`.
cat > "$GHSTUB/gh" <<'STUB'
#!/usr/bin/env bash
if [ "$1 $2" = "repo view" ]; then echo "o/r"; else echo "GH-INVOKED: $*"; fi
STUB
chmod +x "$GHSTUB/gh"

API_REPO="$(mkrepo)"
mkdir -p "$API_REPO/.doperpowers"
printf '{"binding":"api","url":"http://example.invalid"}\n' > "$API_REPO/.doperpowers/board.json"
# BOARD_API_URL (env) overrides board.json's url, so one repo serves every
# world — the port travels in the environment.
verb() {  # verb <args…> — board-search.sh in the api-bound repo, gh stubbed
  (cd "$API_REPO" && PATH="$GHSTUB:$PATH" \
     BOARD_API_URL="http://127.0.0.1:$PORT" \
     BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-search.sh" "$@")
}
verb_as_run() {  # same, speaking as a run
  (cd "$API_REPO" && PATH="$GHSTUB:$PATH" \
     BOARD_API_URL="http://127.0.0.1:$PORT" BOARD_RUN_TOKEN=run-tok \
     BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-search.sh" "$@")
}

world verb-search <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=walker","status":200,
  "body":{"items":[$(row 4 "done" "walker prior art"),
                   $(row 9 "in-progress" "walker live")],"next":null,"as_of":7}}
]
JSON
t "verb prints rows in server order with state visible" "#4 done" verb walker
t "verb header says all states" "all states" verb walker
nt "API arm never invokes gh" "GH-INVOKED" verb walker

world verb-search-states <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=walker&states=done","status":200,
  "body":{"items":[$(row 4 "done" "walker prior art")],"next":null,"as_of":7}}
]
JSON
t "--states narrows the header" "server order, states=done" \
  verb walker --states "done"
t "--states rode the wire beside q" "q=walker&states=done" paths

world verb-none <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=nothing","status":200,
  "body":{"items":[],"next":null,"as_of":2}}
]
JSON
t "an empty result is the header only, exit 0" "0 hit(s)" verb nothing

world verb-empty <<JSON
[]
JSON
t "an empty query is usage" "Usage:" verb ""
t "a whitespace-only query is usage" "Usage:" verb "   "
t "no usage error reached the wire" "reqs=[0]" reqs

# ---- `--` ends the options: the ?q= negation grammar stays reachable ----
world verb-dash <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=-alpha%20beta","status":200,
  "body":{"items":[],"next":null,"as_of":3}}
]
JSON
verb -- "-alpha beta" >/dev/null || true
t "-- carries a negation-leading query to the wire" "q=-alpha%20beta" paths

world verb-refusals <<JSON
[]
JSON
t "a dash-leading query without -- is still usage" "Usage:" verb "-alpha beta"
t "an empty --states value is usage, not a silent widening" "Usage:" \
  verb walker --states ""
t "neither refusal reached the wire" "reqs=[0]" reqs

world verb-run-ctx <<JSON
[]
JSON
t "run context dies claim-gated before any request" "claim-gated" \
  verb_as_run walker
t "the run-context die made no request" "reqs=[0]" reqs

# ---- board-search.sh --bodies: first-20 bound, one budgeted read ----
python3 - > "$TDIR/verb-bodies.src" <<'PY'
import json
def row(i, state="ready-for-implementer", body=None):
    r = {"id": i, "title": "hit %d" % i, "category": "work", "state": state,
         "priority": "P2", "owner_run": None, "parent": None, "plan": None,
         "pr_url": None, "branch": None, "blocked_by": [], "relates": []}
    if body is not None: r["body"] = body
    return r
ids21 = list(range(1, 22))
first20 = ",".join(str(i) for i in ids21[:20])
print(json.dumps([
  {"method": "GET",
   "path": "/tickets?limit=200&ids=%s&include=body" % first20,
   "status": 200,
   "body": {"items": [row(i, body="statement %d" % i) for i in ids21[:20]],
            "next": None, "as_of": 40}},
  {"method": "GET", "path": "/tickets?limit=200&q=crowded", "status": 200,
   "body": {"items": [row(i) for i in ids21], "next": None, "as_of": 40}}
]))
PY
world verb-bodies < "$TDIR/verb-bodies.src"
t "--bodies indents the hydrated statement under its row" \
  "    statement 1" verb crowded --bodies
t "--bodies stops at the first 20 and says so" \
  "first 20 of 21 hits hydrated" verb crowded --bodies
# reqs counts the CUMULATIVE world log — reset it and run once silently, or
# the two verb calls above make this count 6, not 2. `|| true` for the same
# reason the states setup above carries it: a broken verb must fail the
# reqs= drill below, not abort the file before the gh arm ever runs.
: > "$FIX.log"
verb crowded --bodies >/dev/null || true
t "--bodies is one hydration read beside the search walk" "reqs=[2]" reqs

# ---- board-search.sh: gh arm ----
GH_REPO="$(mkrepo)"   # no board.json → gh binding
# env -u BOARD_REPO: the spelling drill pins the bare form; a BOARD_REPO in
# the suite's environment would legitimately add `-R <repo>` and break it.
ghverb() { (cd "$GH_REPO" && env -u BOARD_REPO PATH="$GHSTUB:$PATH" "$SCRIPTS/board-search.sh" "$@"); }
t "gh arm delegates across all states" \
  "GH-INVOKED: issue list --state all --limit 200 -R o/r --search walker" \
  ghverb walker
t "gh arm --bodies notes and proceeds" "noted, proceeding" \
  ghverb walker --bodies
t "gh arm --bodies still runs the search" "GH-INVOKED" ghverb walker --bodies
t "gh arm --states is refused" "API-binding only" ghverb walker --states "done"
nt "gh arm --states never reaches gh" "GH-INVOKED" ghverb walker --states "done"

finish
