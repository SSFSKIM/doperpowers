# Client Agent-Grade Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the board client the server's new agent-grade reads — a `board-search.sh` verb over `?q=`, body consumption in `board-show.sh` via `?include=body`, and the dedup-prose reroute onto the verb (spec `docs/doperpowers/specs/2026-08-20-client-agent-grade-reads-design.md` v1.1).

**Architecture:** Three helper additions in `_board_api.py` (a search walk, `include_body` arms on the two targeted reads, one claim-gate guard) reusing the existing fail-closed `_walk`/`_envelope` plumbing untouched; one new both-bindings verb; one edit to `board-show.sh`'s API arm; prose rerouted in SKILL.md. Tests ride the hermetic mock tier: fixture worlds + request-log assertions, per the paged-reads precedent.

**Tech Stack:** Python 3 stdlib (`urllib.parse`), bash verbs, `mock-server.py` fixture worlds, `tests/claude-code/board-api/helpers.sh` (`t`/`nt`/`mkrepo`/`finish`).

## Global Constraints

- A run context (`BOARD_RUN_TOKEN` set) NEVER sends `q` or `include=body`: the claim-gate guard dies client-side, before any request, with a message containing `claim-gated` (spec §1 — `token()` always speaks as the run, and the server 403s the class).
- Body hydration chunks at `_MAX_BODY_IDS = 20` (arkho API.md §1); plain `ids=` reads keep `_MAX_IDS = 200`. Rows carry `body` iff requested.
- `q` is urlencoded with `urllib.parse.quote(q, safe="")` — never `quote_plus` (space is `%20`, not `+`).
- The search verb's API arm spans ALL states by default, prints rows in server order as `#<id> <state> <priority> <title>`; `--bodies` hydrates the FIRST ≤20 hits in exactly one budgeted read, hydration completing BEFORE any row prints.
- gh arm: delegate spelling is exactly `gh issue list --state open --limit 200 [--repo …] --search "<query>"`; `--states` is refused (stderr note, exit 2); `--bodies` is a stderr note and the search proceeds.
- An empty, missing, or whitespace-only query (trimmed before the check) is a usage error: stderr usage, exit 2, zero requests.
- `mock-server.py` stays fixture-driven — no behavioral additions to the mock; new coverage is fixture worlds + request-log assertions in the new test file. Nothing asserts on the mock itself.
- Budget 400s pass through as the server's message — no fallback code (spec Decision Log).
- Every new drill must fail against the parent commit (naming signature — record which assertion discriminates).
- Commit style `feat(board-client): …` / `test(board-client): …` / `docs(skill): …`; NO `Co-Authored-By` or attribution lines.
- Prose edits are minimal reroutes (writing-skills bar); the spec §4 text governs.

---

### Task 1: Helpers — `tickets_search`, `include_body` arms, the claim-gate guard

**Files:**
- Modify: `skills/issue-tracker/scripts/_board_api.py` (imports; after `_MAX_IDS`; `ticket`; `tickets_by_ids`; after `tickets_all`)
- Test: `tests/claude-code/board-api/test-agent-grade-reads.sh` (new file)

**Interfaces:**
- Consumes: existing `_walk(base, principal)`, `_envelope`, `die`, `request`, `_PAGE_LIMIT`, `_MAX_IDS`.
- Produces (Tasks 2–3 rely on these exact signatures):
  - `tickets_search(q, states=None, principal="automation") -> list[dict]`
  - `ticket(tid, principal="human", include_body=False) -> dict | None`
  - `tickets_by_ids(ids, principal="human", include_body=False) -> dict[int, dict]`
  - `_MAX_BODY_IDS = 20`
  - `_claim_gated(what)` — internal; dies iff `BOARD_RUN_TOKEN` is set.

- [ ] **Step 1: Create the test file with its scaffolding and the Task-1 drills.** The scaffolding (world/run_py/reqs/paths/free_port/wait_for_port) is the file-local convention — each test file in this dir self-contains it (see `test-paged-reads.sh`). Write `tests/claude-code/board-api/test-agent-grade-reads.sh`:

```bash
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
world search <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=alpha%20beta&cursor=","status":404},
 {"method":"GET","path":"/tickets?limit=200&q=alpha%20beta","status":200,
  "body":{"items":[$(row 3 done "alpha beta prior art"),
                   $(row 7 ready-for-implementer "alpha beta now")],
          "next":null,"as_of":9}}
]
JSON
t "search answers the hits" "3" \
  run_py "import _board_api as A
print(sorted(t['id'] for t in A.tickets_search('alpha beta')))"
t "search urlencodes the space as %20" "q=alpha%20beta" paths
t "search is one request" "reqs=[1]" reqs

world search-states <<JSON
[
 {"method":"GET","path":"/tickets?limit=200&q=x&states=done","status":200,
  "body":{"items":[$(row 3 done "x archived")],"next":null,"as_of":4}}
]
JSON
t "states composes onto the search path" "states=done" \
  bash -c 'PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:'"$PORT"'" \
    BOARD_CREDENTIALS_FILE="'"$CREDS"'" python3 -c "import _board_api as A
A.tickets_search(\"x\", states=\"done\")" >/dev/null 2>&1; '"'"'paths'"'"' 2>/dev/null || true; python3 -c "import json,sys
print(\"paths=[%s]\" % \" \".join(json.loads(l)[\"path\"] for l in open(sys.argv[1]) if l.strip()))" "'"$FIX"'.log"'

# ---- include_body: 20-chunk boundary + body-iff-requested parity ----
world hydrate < <(python3 - <<'PY'
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
)
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

finish
```

- [ ] **Step 2: Run the new file to verify it fails.**

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: FAIL lines — `tickets_search` raises `AttributeError` (function absent), the include_body drills fail with `TypeError: … unexpected keyword argument 'include_body'`, the guard drills fail (no `claim-gated` in output). The scaffolding itself must run (mock boots, worlds load); fix scaffolding errors now, before implementing.

- [ ] **Step 3: Implement the helpers in `skills/issue-tracker/scripts/_board_api.py`.**

(a) After `import urllib.error` add:

```python
import urllib.parse
```

(b) After the `_MAX_IDS = 200` line add:

```python
_MAX_BODY_IDS = 20  # include=body chunk cap (arkho API.md §1)
```

(c) Immediately before `def ticket(` add:

```python
def _claim_gated(what):
    """q and include=body are refused to run bearers server-side
    (arkho#12): a run's statement of work arrives in its claim payload,
    and a run's search would be a term-membership oracle over body text
    it cannot read. token() speaks as the run whenever BOARD_RUN_TOKEN
    is set, so the refusal is deterministic — die here, before any
    request, with the reason instead of a bare `forbidden`."""
    if os.environ.get("BOARD_RUN_TOKEN"):
        die("%s is claim-gated for runs (arkho#12): this process speaks "
            "as its run (BOARD_RUN_TOKEN is set) and the server refuses "
            "q/include=body to run bearers — a run reads its statement "
            "of work from the claim payload" % what)
```

(d) `ticket()` — change the signature line and the path build (the rest of the function, including the 404-probe re-read, is untouched; the re-read reuses `path` and so keeps the same `include=body`):

```python
def ticket(tid, principal="human", include_body=False):
```

and where `path` is built:

```python
    path = "/tickets/%s" % int(tid)
    if include_body:
        _claim_gated("include=body")
        path += "?include=body"
```

(e) `tickets_by_ids()` — replace the function with:

```python
def tickets_by_ids(ids, principal="human", include_body=False):
    """ids= batch read, chunked at the documented cap. Returns {int_id: row}.
    An id absent from the completed result is authoritatively absent — a
    targeted read, not a walk. (The board has no delete path today, so an
    absent id here means the id never named a ticket.)

    include_body hydrates each row's statement of work: the chunk cap
    drops to the server's 20-id bound and `include=body` rides each
    chunk's read. The 8 MiB serialized budget is not a reachable bound at
    this toolkit's body sizes (KBs) — a budget 400 passes through as the
    server's own message (spec Decision Log)."""
    if include_body:
        _claim_gated("include=body")
    ids = [int(i) for i in ids]
    out = {}
    cap = _MAX_BODY_IDS if include_body else _MAX_IDS
    for i in range(0, len(ids), cap):
        chunk = ids[i:i + cap]
        base = "/tickets?limit=%d&ids=%s" % (
            _PAGE_LIMIT, ",".join(str(c) for c in chunk))
        if include_body:
            base += "&include=body"
        for row in _walk(base, principal):
            out[int(row["id"])] = row
    return out
```

(f) After `tickets_all()` add:

```python
def tickets_search(q, states=None, principal="automation"):
    """Complete cursor walk of /tickets?q= — the server's websearch filter
    over title+body (arkho#12: unquoted terms AND, `or`, `-` negation,
    quoted phrases; the grammar is the server's to judge). Report-grade
    completeness and id-keyed dedupe, same as tickets_all. The query
    rides urlencoded inside ONE parameter — quote(q, safe=""), never
    quote_plus, whose space-as-+ is a different wire spelling."""
    _claim_gated("search (?q=)")
    base = "/tickets?limit=%d&q=%s" % (
        _PAGE_LIMIT, urllib.parse.quote(q, safe=""))
    if states:
        base += "&states=%s" % states
    seen = {}
    for row in _walk(base, principal):
        seen[int(row["id"])] = row
    return list(seen.values())
```

- [ ] **Step 4: Run the file to verify it passes.**

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: every `ok` line, `PASS test-agent-grade-reads.sh`.

- [ ] **Step 5: Regression check the sibling read suites** (the two files that exercise the functions whose signatures changed):

Run: `bash tests/claude-code/board-api/test-paged-reads.sh && bash tests/claude-code/board-api/test-read-verbs.sh`
Expected: both PASS (the new parameters default off; no caller changed).

- [ ] **Step 6: Commit.**

```bash
git add skills/issue-tracker/scripts/_board_api.py tests/claude-code/board-api/test-agent-grade-reads.sh
git commit -m "feat(board-client): tickets_search, include_body hydration, and the claim-gate guard"
```

---

### Task 2: The verb — `board-search.sh`, both bindings

**Files:**
- Create: `skills/issue-tracker/scripts/board-search.sh` (mode 755)
- Test: `tests/claude-code/board-api/test-agent-grade-reads.sh` (append the verb drills before `finish`)

**Interfaces:**
- Consumes: `tickets_search(q, states=None, principal="automation")`, `tickets_by_ids(ids, principal="automation", include_body=True)`, `_MAX_BODY_IDS` semantics (first-20 bound) from Task 1; `_lib.sh` conventions (`usage_from_header`, `BOARD_BINDING`, `_api_py`).
- Produces: the operator-facing output contract Task 4's Toolkit row describes.

- [ ] **Step 1: Write the verb.** Create `skills/issue-tracker/scripts/board-search.sh`, `chmod 755`:

```bash
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
# --limit 200 --search <query>` (the explicit --limit matters: the default
# caps at 30 and truncates silently). gh's search already matches bodies,
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
hydrate = rows[:20]   # the first budgeted read's worth (MAX_BODY_IDS)
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
exec gh issue list --state open --limit 200 ${BOARD_REPO:+-R "$BOARD_REPO"} --search "$query"
```

- [ ] **Step 2: Append the verb drills** to `tests/claude-code/board-api/test-agent-grade-reads.sh`, before `finish`:

```bash
# ---- board-search.sh: API arm ----
# A stub gh on PATH for every API-arm call: "API mode never invokes gh" is
# asserted, not assumed (test-read-verbs.sh precedent).
GHSTUB="$TDIR/ghbin"; mkdir -p "$GHSTUB"
printf '#!/usr/bin/env bash\necho "GH-INVOKED: $*"\n' > "$GHSTUB/gh"
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
  "body":{"items":[$(row 4 done "walker prior art"),
                   $(row 9 in-progress "walker live")],"next":null,"as_of":7}}
]
JSON
t "verb prints rows in server order with state visible" "#4 done" verb walker
t "verb header says all states" "all states" verb walker
nt "API arm never invokes gh" "GH-INVOKED" verb walker

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

world verb-run-ctx <<JSON
[]
JSON
t "run context dies claim-gated before any request" "claim-gated" \
  verb_as_run walker
t "the run-context die made no request" "reqs=[0]" reqs

# ---- board-search.sh --bodies: first-20 bound, one budgeted read ----
world verb-bodies < <(python3 - <<'PY'
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
)
t "--bodies indents the hydrated statement under its row" \
  "    statement 1" verb crowded --bodies
t "--bodies stops at the first 20 and says so" \
  "first 20 of 21 hits hydrated" verb crowded --bodies
t "--bodies is one hydration read beside the search walk" "reqs=[2]" reqs

# ---- board-search.sh: gh arm ----
GH_REPO="$(mkrepo)"   # no board.json → gh binding
# env -u BOARD_REPO: the spelling drill pins the bare form; a BOARD_REPO in
# the suite's environment would legitimately add `-R <repo>` and break it.
ghverb() { (cd "$GH_REPO" && env -u BOARD_REPO PATH="$GHSTUB:$PATH" "$SCRIPTS/board-search.sh" "$@"); }
t "gh arm delegates with the proven spelling" \
  "GH-INVOKED: issue list --state open --limit 200 --search walker" \
  ghverb walker
t "gh arm --bodies notes and proceeds" "noted, proceeding" \
  ghverb walker --bodies
t "gh arm --bodies still runs the search" "GH-INVOKED" ghverb walker --bodies
t "gh arm --states is refused" "API-binding only" ghverb walker --states done
nt "gh arm --states never reaches gh" "GH-INVOKED" ghverb walker --states done
```

- [ ] **Step 3: Run to verify the new drills fail** (verb absent):

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: Task-1 drills still `ok`; every verb drill FAILs with `No such file or directory` for `board-search.sh`.

- [ ] **Step 4: `chmod 755 skills/issue-tracker/scripts/board-search.sh`, re-run, verify all pass.**

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: `PASS test-agent-grade-reads.sh`.

- [ ] **Step 5: Shellcheck the new verb.**

Run: `scripts/lint-shell.sh`
Expected: no new findings (the file follows the sibling verbs' idioms).

- [ ] **Step 6: Commit.**

```bash
git add skills/issue-tracker/scripts/board-search.sh tests/claude-code/board-api/test-agent-grade-reads.sh
git commit -m "feat(board-client): board-search — the ?q= verb, both bindings"
```

---

### Task 3: `board-show.sh` — the body joins the read

**Files:**
- Modify: `skills/issue-tracker/scripts/board-show.sh` (the API-mode python block only)
- Test: `tests/claude-code/board-api/test-agent-grade-reads.sh` (append before `finish`)

**Interfaces:**
- Consumes: `ticket(tid, principal="automation", include_body=…)` from Task 1.
- Produces: the API-arm output contract — header line, blank line, body (or the claim-served line), blank line, timeline records.

- [ ] **Step 1: Append the show drills** before `finish`:

```bash
# ---- board-show.sh: body between header and timeline ----
world show-body <<JSON
[
 {"method":"GET","path":"/tickets/12/timeline","status":200,
  "body":{"records":[{"source":"board","cursor":"5","observedAt":"t",
    "sourceTime":null,"runId":1,"kind":"transition",
    "body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}}]}},
 {"method":"GET","path":"/tickets/12?include=body","status":200,
  "body":{"id":12,"title":"T one","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,
          "pr_url":null,"branch":"feat/x","blocked_by":[],"relates":[],
          "body":"## The statement\nof work"}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"title":"T one","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,
          "pr_url":null,"branch":"feat/x","blocked_by":[],"relates":[]}}
]
JSON
show() { (cd "$API_REPO" && PATH="$GHSTUB:$PATH" \
    BOARD_API_URL="http://127.0.0.1:$PORT" \
    BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-show.sh" "$@"); }
show_as_run() { (cd "$API_REPO" && PATH="$GHSTUB:$PATH" \
    BOARD_API_URL="http://127.0.0.1:$PORT" BOARD_RUN_TOKEN=run-tok \
    BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-show.sh" "$@"); }
t "show prints the statement of work" "## The statement" show 12
t "show still prints the header row" "#12 in-progress" show 12
t "show still prints the timeline" "transition" show 12
t "the body ride is on the wire" "include=body" paths

world show-run <<JSON
[
 {"method":"GET","path":"/tickets/12/timeline","status":200,
  "body":{"records":[{"source":"board","cursor":"5","observedAt":"t",
    "sourceTime":null,"runId":1,"kind":"transition",
    "body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}}]}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"title":"T one","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,
          "pr_url":null,"branch":"feat/x","blocked_by":[],"relates":[]}}
]
JSON
t "a run context degrades to the claim-served line" "claim-served" \
  show_as_run 12
nt "a run context sends no include=body" "include=body" paths
```

(Fixture ORDER matters in the show-body world: `/tickets/12/timeline` before `/tickets/12?include=body` before `/tickets/12` — the mock prefix-matches, so the bare `/tickets/12` entry goes last or it swallows both.)

- [ ] **Step 2: Run to verify the show drills fail.**

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: earlier drills `ok`; `show prints the statement of work` FAILs (no body printed today), `a run context degrades` FAILs (no claim-served line).

- [ ] **Step 3: Edit `skills/issue-tracker/scripts/board-show.sh`'s API-mode python block.** Two changes. First, the fetch (currently `t = A.ticket(tid, principal="automation")`):

```python
run_ctx = bool(os.environ.get("BOARD_RUN_TOKEN"))
# The body rides the by-id read for every non-run reader — "one ticket in
# full" finally includes the statement of work. A run context omits the
# opt-in (the server refuses the class; its body arrived in the claim
# payload) so the worker bootstrap's timeline read keeps working unchanged.
t = A.ticket(tid, principal="automation", include_body=not run_ctx)
```

Second, between the header `print(...)` and the timeline `for` loop insert:

```python
print()
if run_ctx:
    print("body: claim-served (a run reads its statement of work from "
          "the claim payload)")
else:
    print(t.get("body", ""))
print()
```

Also update the file's header comment (line 2): `# board-show.sh — one ticket in full: node JSON, issue URL, bound daemon.` → `# board-show.sh — one ticket in full. API mode: header, statement of work (body), timeline. gh mode: node JSON, issue URL, bound daemon.`

- [ ] **Step 4: Run to verify all pass.**

Run: `bash tests/claude-code/board-api/test-agent-grade-reads.sh`
Expected: `PASS test-agent-grade-reads.sh`.

- [ ] **Step 5: Regression: the read-verbs suite pins show's old output.**

Run: `bash tests/claude-code/board-api/test-read-verbs.sh`
Expected: PASS — but if a show drill there asserts on exact line adjacency (header directly followed by timeline) it now legitimately fails; update THAT drill's expectation to the new contract (header, blank, body/claim-line, blank, timeline) rather than weakening this task. Its fixture `/tickets/12` entry also needs an `?include=body` twin (the mock 404s unmatched paths — show's new read would die). Record in your report which of the two cases you hit.

- [ ] **Step 6: Commit.**

```bash
git add skills/issue-tracker/scripts/board-show.sh tests/claude-code/board-api/test-agent-grade-reads.sh tests/claude-code/board-api/test-read-verbs.sh
git commit -m "feat(board-client): board-show serves the statement of work; runs degrade to claim-served"
```

---

### Task 4: SKILL.md — the dedup reroute and the Toolkit rows

**Files:**
- Modify: `skills/issue-tracker/SKILL.md` (§Toolkit table; §The ticket body)

**Interfaces:**
- Consumes: the Task 2 verb's exact flags and per-binding semantics; Task 3's show output.
- Produces: prose — no code consumer.

- [ ] **Step 1: Reroute the pre-registration search.** In §The ticket body, replace exactly this text:

```
authors word the same work differently. GitHub issue search hits
bodies, so query each seam identifier
(`gh issue list --state open --limit 200 --search "<function-or-file-name>"`
— the explicit `--limit` matters: the default caps at 30 and truncates
silently). This search is a gh-binding route; an API-bound repo has no
client search verb yet — rely on the server's registration-time dedupe
until one lands (the arkho#7 route family). Then triage the hits:
```

with:

```
authors word the same work differently. Query each seam identifier with
`board-search.sh "<function-or-file-name>"` — one route, both bindings
(the verb owns the branch: gh-bound repos ride gh's body-matching issue
search, API-bound repos the board's `?q=` full-text filter). Where a
title is not enough to judge a hit, `--bodies` prints the first ≤20
hits' statements of work. A worker in a run context cannot search
(claim-gated by design) — there the server's registration-time dedupe
stays the guard. Then triage the hits:
```

- [ ] **Step 2: Toolkit table.** Insert a new row directly after the `board-list.sh` row:

```
| `board-search.sh <query> [--states s1,s2] [--bodies]` | full-text search for the pre-registration dedup / prior-art check (see The ticket body). API binding: the board's `?q=` websearch (unquoted terms AND, `or`, `-` negation, quoted phrases) across ALL states in server order; `--states` narrows; `--bodies` prints the first ≤20 hits' bodies (one budgeted read). gh binding: `gh issue list --state open --limit 200 --search` (`--states` refused; `--bodies` a stderr note — gh search already matches bodies). Claim-gated: a run context is refused before any request |
```

and replace the `board-show.sh` row (`| `board-show.sh <n>` | node + issue URL + bound daemon |`) with:

```
| `board-show.sh <n>` | one ticket in full. API binding: header row, the statement of work (body), then the server-side timeline — a run context sees `body: claim-served` (its body arrived in the claim payload). gh binding: node JSON + issue URL + bound daemon |
```

- [ ] **Step 3: Sanity greps** (the reroute is complete and nothing stale remains):

Run: `grep -n "no client search verb" skills/issue-tracker/SKILL.md; grep -c "board-search.sh" skills/issue-tracker/SKILL.md`
Expected: first grep empty (exit 1); second ≥ 3 (table row, ticket-body prose, and the row's cross-reference).

- [ ] **Step 4: Commit.**

```bash
git add skills/issue-tracker/SKILL.md
git commit -m "docs(skill): pre-registration search rides board-search on both bindings"
```

---

### Task 5: Final verification — acceptance walk, full suite, version bump

**Files:**
- Modify: `package.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` (via `scripts/bump-version.sh` only — never by hand)

- [ ] **Step 1: Full plugin test suite.**

Run: `tests/claude-code/run-skill-tests.sh`
Expected: PASS overall; the board-api integration tier may SKIP via exit 77 (no local docker) — a SKIP is not a failure; any FAIL is yours to investigate before proceeding.

- [ ] **Step 2: Walk the spec's Acceptance section as written** (spec `docs/doperpowers/specs/2026-08-20-client-agent-grade-reads-design.md` §Acceptance, seven items). For each item name the drill(s) in `test-agent-grade-reads.sh` that prove it and confirm they ran green in Step 1; where an item is proven by inspection rather than a drill, say so explicitly in your report:

1. "On an API-bound repo, `board-search.sh <word>` prints one row per ticket the server's `q` filter answers, state visible on every row, exit 0; an empty result exits 0 with the header only." — drills `verb prints rows in server order with state visible`, `verb header says all states`, `an empty result is the header only, exit 0`.
2. "`--bodies` … first ≤20 hits … exactly one hydration read; a hit beyond 20 stays rows-only and the output says so." — drills `--bodies indents…`, `--bodies stops at the first 20…`, `--bodies is one hydration read…`.
3. "In a run context board-search dies before any request…; board-show still succeeds, printing the claim-served line." — drills `run context dies claim-gated…`, `the run-context die made no request`, `a run context degrades to the claim-served line`.
4. "board-show prints header, body, timeline; the body byte-identical to what board-body.sh last wrote." — drills `show prints the statement of work` + parity drill (Task 1); the byte-identity-to-board-body half is by inspection (the mock returns what the fixture carries; the server-side identity is arkho's drill territory) — say so.
5. "gh-bound repo delegation spelling; --bodies notes and proceeds; --states refused exit 2." — the four gh-arm drills.
6. "SKILL.md names board-search.sh as the one route; the old sentence gone; run-context clause present." — Task 4 Step 3's greps.
7. "Full mock-tier suite and run-skill-tests.sh green; version bumped." — Steps 1 and 3–4 of this task.

- [ ] **Step 3: Version bump.**

Run: `scripts/bump-version.sh --check` (note the current version), then `scripts/bump-version.sh <next-minor>` (e.g. current `7.57.1` → `7.58.0`; if the branch base moved, next-minor from whatever --check prints), then `scripts/bump-version.sh --audit`
Expected: all declared files at the new version; audit clean.

- [ ] **Step 4: Commit.**

```bash
git add -A
git commit -m "chore: v7.58.0 — client agent-grade reads (board-search, body consumption)"
```
