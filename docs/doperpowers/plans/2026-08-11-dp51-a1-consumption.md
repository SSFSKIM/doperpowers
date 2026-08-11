# dp#51 A1 Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the arkho#7 board-service routes into the doperpowers client: three human verbs gain api branches, a new `board-body.sh` verb, register's real `note` field, the api-scale review variant, successor `parentPin` threading, and read parity in show/map.

**Architecture:** Every api-mode change follows the established thin-client pattern — an `if [ "$BOARD_BINDING" = api ]` branch ahead of the gh python block that assembles the payload via `_board_api.py` route helpers and prints what the server answered. Server guards are never re-adjudicated client-side. gh-mode halves stay untouched except the one new verb.

**Tech Stack:** bash + inline python3 heredocs (the toolkit's idiom), `_board_api.py` (urllib HTTP client), fixture mock server for the unit tier, real A1 service via `tests/claude-code/board-api/integration/harness.sh` for the integration tier.

**Spec:** `docs/doperpowers/specs/2026-08-11-dp51-a1-consumption-design.md` v1.1. Server contract: arkho `board-service/API.md` at `a05b1ac`.

## Global Constraints

- Thin client: api branches assemble requests and report answers; legality/guards live server-side. No client-side cycle/ancestor/ownership walks in api mode.
- gh-mode behavior byte-identical everywhere except the new `board-body.sh` verb.
- No `gh` invocation on any api path (the existing tests assert this with a PATH stub — keep them passing).
- Server refusals surface verbatim (`_board_api.py` already prints `<code> — <message>`; never swallow or rewrite).
- Mock fixtures use the NESTED error envelope `{"error": {"code": …, "message": …}}` and contract-shaped success bodies from API.md.
- Principals: edges/parent/relates/priority/body routes are `human`-only — every new route helper passes principal `"human"` (note: in a run context `token()` still speaks as the run; that is existing, deliberate behavior).
- Ticket refs accept `#N` and `N` spellings in every new verb (the register `ref()` idiom).
- Never commit, echo into fixtures, or log any board token/DSN; integration credentials come only from the harness's generated `.harness/creds.env`.
- Test commands: unit tier scripts run directly (`tests/claude-code/board-api/test-*.sh`); each prints `PASS <name>` on success. Shell lint: `scripts/lint-shell.sh`.
- Version bump at the end via `scripts/bump-version.sh minor` — never hand-edit manifests.

---

### Task 1: Route helpers in `_board_api.py`

**Files:**
- Modify: `skills/issue-tracker/scripts/_board_api.py` (append to the route-helpers section, after `queue_decisions()` at the end of the file)
- Test: `tests/claude-code/board-api/test-client-core.sh` (extend)

**Interfaces:**
- Produces (consumed by Tasks 2–4): `edge(tid, op, blocked_by)`, `set_parent(tid, parent)`, `relate(tid, op, other)`, `set_priority(tid, priority)`, `set_body(tid, body)` — all POST as principal `"human"`, all return the parsed response dict.

- [ ] **Step 1: Write the failing test.** Open `tests/claude-code/board-api/test-client-core.sh`, find its fixture JSON array and append five fixtures before the closing `]` (comma-separate from the previous entry — match the file's existing style):

```json
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true,"noop":true}},
 {"method":"POST","path":"/tickets/5/body","status":409,
  "body":{"error":{"code":"ticket-owned","message":"ticket 5 is owned by run 41"}}}
```

Then append asserts at the end of the file, before `finish` (adapt the file's existing invocation helper — it runs inline python with `_api_py`-equivalent env; follow the pattern of the nearest existing route-helper assert in that file):

```bash
t "edge helper posts op+blockedBy as human" '"blockedBy": 7' \
  bash -c "$PYRUN 'import _board_api as A; A.edge(5, \"add\", 7)'; cat '$FIX.log'"
t "parent helper posts null orphan" '"parent": null' \
  bash -c "$PYRUN 'import _board_api as A; A.set_parent(5, None)'; cat '$FIX.log'"
t "relate helper posts op+ticket" '"ticket": 9' \
  bash -c "$PYRUN 'import _board_api as A; A.relate(5, \"add\", 9)'; cat '$FIX.log'"
t "priority helper returns noop flag" "noop-yes" \
  bash -c "$PYRUN 'import _board_api as A; print(\"noop-yes\" if A.set_priority(5, \"P0\").get(\"noop\") else \"noop-no\")'"
t "body helper surfaces ticket-owned verbatim" "ticket-owned — ticket 5 is owned by run 41" \
  bash -c "$PYRUN 'import _board_api as A; A.set_body(5, \"x\")' 2>&1 || true"
```

If `test-client-core.sh` has no reusable `$PYRUN`, define one next to its existing helpers:

```bash
PYRUN="cd '$r' && BOARD_CREDENTIALS_FILE='$CREDS' BOARD_API_URL='http://127.0.0.1:$PORT' \
  PYTHONPATH='$SCRIPTS' python3 -c"
```

(and check how the file already invokes helpers — reuse its own idiom over this sketch; the assertions' substance is what is pinned, not the harness spelling. Note the helper tests must NOT set `BOARD_RUN_TOKEN` — these are human-principal calls and the auth header should carry the human token `h`.)

- [ ] **Step 2: Run to verify it fails.** `tests/claude-code/board-api/test-client-core.sh` — expect FAIL lines mentioning `AttributeError` (`edge` not defined).

- [ ] **Step 3: Implement.** Append to `skills/issue-tracker/scripts/_board_api.py`:

```python
def edge(tid, op, blocked_by):
    return request("POST", "/tickets/%s/edges" % int(tid),
                   {"op": op, "blockedBy": int(blocked_by)}, "human")


def set_parent(tid, parent):
    return request("POST", "/tickets/%s/parent" % int(tid),
                   {"parent": int(parent) if parent is not None else None},
                   "human")


def relate(tid, op, other):
    return request("POST", "/tickets/%s/relates" % int(tid),
                   {"op": op, "ticket": int(other)}, "human")


def set_priority(tid, priority):
    return request("POST", "/tickets/%s/priority" % int(tid),
                   {"priority": priority}, "human")


def set_body(tid, body):
    return request("POST", "/tickets/%s/body" % int(tid),
                   {"body": body}, "human")
```

- [ ] **Step 4: Run to verify it passes.** `tests/claude-code/board-api/test-client-core.sh` → `PASS test-client-core.sh`.

- [ ] **Step 5: Commit.** `git add -A skills/issue-tracker/scripts/_board_api.py tests/claude-code/board-api/test-client-core.sh && git commit -m "feat(board-api): route helpers for the five arkho#7 human routes"`

---

### Task 2: `board-edge.sh` api branch

**Files:**
- Modify: `skills/issue-tracker/scripts/board-edge.sh`
- Test: `tests/claude-code/board-api/test-edge-verbs.sh` (create)

**Interfaces:**
- Consumes: `A.edge`, `A.set_parent` (Task 1).

- [ ] **Step 1: Write the failing test.** Create `tests/claude-code/board-api/test-edge-verbs.sh` (mode 755), modeled on `test-register-transition.sh`'s scaffold (helpers.sh source, free port, fixture mock, `wait_for_port`, creds file, `mkrepo` + `board.json`, `V` runner, `finish` at the end):

```bash
#!/usr/bin/env bash
# test-edge-verbs.sh — the four arkho#7 human verbs' API branches: edge
# re-cuts, reparent/orphan, relates, priority. What went on the wire (the
# fixture log) and what the verb printed; refusals surface the server's
# message verbatim and exit nonzero.
. "$(dirname "$0")/helpers.sh"

PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/edges","status":409,
  "body":{"error":{"code":"edge-cycle","message":"#7 already waits on #5"}},"once":true},
 {"method":"POST","path":"/tickets/5/edges","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/parent","status":409,
  "body":{"error":{"code":"ancestor-blocker","message":"#5 is blocked by #3, an ancestor"}},"once":true},
 {"method":"POST","path":"/tickets/5/parent","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/relates","status":409,
  "body":{"error":{"code":"duplicate-edge","message":"#5 and #9 are already related"}},"once":true},
 {"method":"POST","path":"/tickets/5/relates","status":200,"body":{"ok":true}},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/priority","status":200,"body":{"ok":true,"noop":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
wait_for_port() {
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then return 0; fi
    tries=$((tries - 1)); sleep 0.05
  done
  return 1
}
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
V() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
export r CREDS SCRIPTS
export -f V

# ---- board-edge.sh ----
t "block posts add+blockedBy and prints the move" "#5: blocked_by += #7" \
  V board-edge.sh 5 --block 7
t "the block payload is op add, blockedBy int" '"blockedBy": 7' \
  bash -c "cat '$FIX.log'"
CYCLE_OUT="$(mktemp)"; CYCLE_RC=0
V board-edge.sh 5 --block 7 > "$CYCLE_OUT" 2>&1 || CYCLE_RC=$?
t "a cycle refusal surfaces the server message" "edge-cycle" cat "$CYCLE_OUT"
t "a refused edge exits nonzero" "rc=1" echo "rc=$CYCLE_RC"
t "unblock posts op cut" "#5: blocked_by -= #7" V board-edge.sh 5 --unblock 7
t "the unblock payload says cut" '"op": "cut"' bash -c "cat '$FIX.log'"
t "parent posts the id" "#5: parent = #3" V board-edge.sh 5 --parent 3
ANC_OUT="$(mktemp)"
V board-edge.sh 5 --parent 3 > "$ANC_OUT" 2>&1 || true
t "an ancestor-blocker refusal surfaces verbatim" "ancestor-blocker" cat "$ANC_OUT"
t "orphan posts parent null" "#5: parent cleared" V board-edge.sh 5 --orphan
t "the orphan payload is a null parent" '"parent": null' bash -c "cat '$FIX.log'"
t "hash refs are accepted" "related: #5 -- #9" V board-relate.sh '#5' '#9'
DUP_OUT="$(mktemp)"
V board-relate.sh 5 9 > "$DUP_OUT" 2>&1 || true
t "duplicate-edge surfaces verbatim" "duplicate-edge" cat "$DUP_OUT"
t "relate --cut posts op cut" "cut: #5 -- #9" V board-relate.sh 5 9 --cut
t "priority prints the grade" "#5: → P0" V board-priority.sh 5 P0
t "a noop re-grade says so" "(noop)" V board-priority.sh 5 P0
t "a junk grade dies client-side before the wire" "priority must be one of" \
  V board-priority.sh 5 P9

# In API mode gh is never invoked — asserted with a stub, as everywhere else.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
nt "api edge verbs never invoke gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' \
    '$SCRIPTS/board-edge.sh' 5 --block 7"

finish
```

(Note: this file also carries the Task 3 relate/priority asserts — write it whole now; Tasks 3's steps run it once their verbs exist. Adjust the printed-line expectations to exactly what Steps 3 below implement.)

- [ ] **Step 2: Run to verify it fails.** `tests/claude-code/board-api/test-edge-verbs.sh` — expect FAILs whose output contains `no API-mode counterpart yet` (the current refusal).

- [ ] **Step 3: Implement.** In `skills/issue-tracker/scripts/board-edge.sh`:

Delete the two lines:

```bash
# No API-mode counterpart yet (A1 route gap), so refuse rather than silently
# writing through a gh path that a board-API repo does not have.
_refuse_no_api_route "re-cutting parent / blocked-by edges"
```

After the argv loop ends (after `[ -n "$op" ] || { usage_from_header "$0" >&2; exit 2; }`), insert:

```bash
# API mode: the server owns every structural guard — self-edge, dependency
# and parent cycles, ancestor-blocker, duplicate/no-such-edge — and refuses
# with a message naming the state (API.md §4.2). The client sends the one
# edge op and prints the move that committed; the gh half's derived lines
# ("now eligible", epic pulls) are server-side sweeps here and are not
# re-derived.
if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_OP="$op" T_REF="$ref" _api_py - <<'PY'
import os
import _board_api as A

def ref(raw):
    n = raw.lstrip("#")
    if not n.isdigit():
        A.die("not an issue number: %s" % raw)
    return int(n)

tid = ref(os.environ["T_ID"])
op = os.environ["T_OP"]
other = ref(os.environ["T_REF"]) if os.environ["T_REF"] else None
if op == "block":
    A.edge(tid, "add", other)
    print("#%s: blocked_by += #%s" % (tid, other))
elif op == "unblock":
    A.edge(tid, "cut", other)
    print("#%s: blocked_by -= #%s" % (tid, other))
elif op == "parent":
    A.set_parent(tid, other)
    print("#%s: parent = #%s" % (tid, other))
else:  # orphan
    A.set_parent(tid, None)
    print("#%s: parent cleared" % tid)
PY
  _rerender_if_serving
  exit 0
fi
```

Update the header comment block: the sentence "Register-time edges can't form cycles … board-transition:" stays; append one line to the header: `In API mode the server enforces the same refusal set and this script only relays it.`

- [ ] **Step 4: Run.** `tests/claude-code/board-api/test-edge-verbs.sh` — the board-edge asserts pass; relate/priority asserts still FAIL (Task 3). Also run `tests/claude-code/board-api/test-register-transition.sh` — the `board-edge.sh fails loud naming arkho#7` assert now FAILS; fix it in this task: edit that loop in `test-register-transition.sh` to drop the migrated verbs:

```bash
for verb in board-migrate-gh.sh; do
  t "$verb fails loud naming arkho#7" "arkho#7" V "$verb" 1 --block 2
done
```

(board-surface.sh keeps its refusal but is not exercised in that loop's argv shape; leave it.) Re-run: PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(board-edge): api-mode binding for blocked-by and parent edges"`

---

### Task 3: `board-priority.sh` + `board-relate.sh` api branches

**Files:**
- Modify: `skills/issue-tracker/scripts/board-priority.sh`, `skills/issue-tracker/scripts/board-relate.sh`
- Test: `tests/claude-code/board-api/test-edge-verbs.sh` (written in Task 2)

- [ ] **Step 1: Verify the failing asserts.** `tests/claude-code/board-api/test-edge-verbs.sh` — the relate/priority asserts fail with `no API-mode counterpart yet`.

- [ ] **Step 2: Implement `board-priority.sh`.** Delete its `_refuse_no_api_route` line and the two comment lines above it. After the `[ $# -eq 2 ] || …` arity check, insert:

```bash
if [ "$BOARD_BINDING" = api ]; then
  # The grade set is checked client-side only because a bad argv should not
  # need a socket; the write itself — including the write-if-changed noop —
  # is the server's.
  case "$2" in P0|P1|P2|P3) : ;; *) die "priority must be one of P0|P1|P2|P3" ;; esac
  T_ID="$1" T_P="$2" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_ID"].lstrip("#")
out = A.set_priority(tid, os.environ["T_P"])
print("#%s: → %s%s" % (tid, os.environ["T_P"],
                       " (noop)" if out.get("noop") else ""))
PY
  _rerender_if_serving
  exit 0
fi
```

- [ ] **Step 3: Implement `board-relate.sh`.** Delete its `_refuse_no_api_route` line and the two comment lines above it. After the argv loop (after the `--cut` parsing `while` loop closes), insert:

```bash
# API mode: one call to endpoint A — the server stores the edge normalized
# (least, greatest) and both projections report it, so the gh half's
# two-issue write has no counterpart here. Self-edge and duplicate/no-such
# refusals are the server's, surfaced verbatim.
if [ "$BOARD_BINDING" = api ]; then
  T_A="$a" T_B="$b" T_CUT="$cut" _api_py - <<'PY'
import os
import _board_api as A

def ref(raw):
    n = raw.lstrip("#")
    if not n.isdigit():
        A.die("not an issue number: %s" % raw)
    return int(n)

a, b = ref(os.environ["T_A"]), ref(os.environ["T_B"])
if os.environ["T_CUT"] == "1":
    A.relate(a, "cut", b)
    print("cut: #%s -- #%s" % (a, b))
else:
    A.relate(a, "add", b)
    print("related: #%s -- #%s" % (a, b))
PY
  _rerender_if_serving
  exit 0
fi
```

Update both scripts' headers with one line each: priority — `API mode posts the re-grade and reports the server's noop flag.`; relate — `API mode writes the normalized server edge with one call.`

- [ ] **Step 4: Run.** `tests/claude-code/board-api/test-edge-verbs.sh` → `PASS test-edge-verbs.sh`. Also `scripts/lint-shell.sh` clean on both files.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(board-verbs): api-mode priority re-grade and relates binding"`

---

### Task 4: `board-body.sh` — new both-modes verb

**Files:**
- Create: `skills/issue-tracker/scripts/board-body.sh` (mode 755)
- Modify: `skills/issue-tracker/scripts/board-register.sh` (two comment updates)
- Test: `tests/claude-code/board-api/test-edge-verbs.sh` (extend) + a gh-mode splice test inside the new script's own test section below

- [ ] **Step 1: Write the failing tests.** Append to `tests/claude-code/board-api/test-edge-verbs.sh` before the gh-stub assert (add fixtures to the fixture array first):

```json
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true},"once":true},
 {"method":"POST","path":"/tickets/5/body","status":200,"body":{"ok":true,"noop":true},"once":true},
 {"method":"POST","path":"/tickets/5/body","status":409,
  "body":{"error":{"code":"ticket-owned","message":"ticket 5 is owned by run 41"}}}
```

```bash
# ---- board-body.sh (api half) ----
BF="$(mktemp)"; printf 'the sharpened statement' > "$BF"
t "body edit posts and reports" "#5: body rewritten" V board-body.sh 5 --body-file "$BF"
t "the body payload carries the text whole" '"body": "the sharpened statement"' \
  bash -c "cat '$FIX.log'"
t "a noop body edit says so" "(noop)" V board-body.sh 5 --body-file "$BF"
OWNED_OUT="$(mktemp)"; OWNED_RC=0
V board-body.sh 5 --body-file "$BF" > "$OWNED_OUT" 2>&1 || OWNED_RC=$?
t "ticket-owned surfaces naming the run" "ticket-owned — ticket 5 is owned by run 41" cat "$OWNED_OUT"
t "an owned refusal exits nonzero" "rc=1" echo "rc=$OWNED_RC"
EMPTYB="$(mktemp)"
```

And the gh-mode raw-splice test as its own unit block (no mock needed — stub `gh`). Append after the api block above:

```bash
# ---- board-body.sh (gh half): the raw meta splice ----
# The TRAILING board:meta block must survive BYTE-FOR-BYTE, noncanonical
# spelling and unknown future keys included — parse/render would canonicalize
# and drop. The stored prose deliberately QUOTES a marker-like example before
# the real trailing block: a first-marker find would splice from the quote
# and corrupt the body, so this fixture is the guard against that.
ghr="$(mkrepo)"
gstub="$(mktemp -d)"
cat > "$gstub/gh" <<'EOF'
#!/usr/bin/env bash
# issue view --json body → the stored body; issue edit --body-file - →
# capture stdin. The implementer aligns these match arms (and the repo-name
# resolution B.repo() makes) with the implementation's exact argv, answering
# each contract-shaped — the stub must satisfy every gh call the verb makes,
# because the assertion below pins the command's EXIT STATUS.
case "$*" in
  *"issue view"*) printf 'old prose quoting an example:\n<!-- board:meta\nfake: example\n-->\nmore old prose\n\n<!-- board:meta\nfuture-key: kept\n# a comment line\nbranch:   odd/spacing\n-->\n' ;;
  *"issue edit"*) cat > "$GH_BODY_CAPTURE" ;;
  *) echo '{}' ;;
esac
EOF
chmod +x "$gstub/gh"
NEWB="$(mktemp)"; printf 'new prose' > "$NEWB"
CAP="$(mktemp)"
GH_RC=0
( cd "$ghr" && PATH="$gstub:$PATH" GH_BODY_CAPTURE="$CAP" \
  "$SCRIPTS/board-body.sh" 12 --body-file "$NEWB" ) >/dev/null 2>&1 || GH_RC=$?
t "gh body edit exits zero (no swallowed stub failure)" "rc=0" echo "rc=$GH_RC"
t "gh body edit keeps the TRAILING meta block byte-for-byte" \
  '<!-- board:meta
future-key: kept
# a comment line
branch:   odd/spacing
-->' cat "$CAP"
t "gh body edit replaced the prose" "new prose" cat "$CAP"
nt "gh body edit did not keep the old prose" "old prose" cat "$CAP"
nt "the quoted marker example did not survive as a splice point" "fake: example" cat "$CAP"
```

(The implementer adjusts the `gh` stub's match arms to the exact `gh` argv the implementation uses — the pinned substance is: exit 0, the byte-identical TRAILING block, the replaced prose, and the quoted example NOT surviving.)

- [ ] **Step 2: Run to verify failure.** `tests/claude-code/board-api/test-edge-verbs.sh` — new asserts fail (`board-body.sh: No such file`).

- [ ] **Step 3: Implement.** Create `skills/issue-tracker/scripts/board-body.sh`:

```bash
#!/usr/bin/env bash
# board-body.sh — rewrite a ticket's statement of work.
#
# Usage:
#   board-body.sh <number> --body-file F     (F may be - for stdin; an empty
#                                             file is a legal edit — clearing
#                                             the statement of work)
#
# API mode posts the whole text to POST /tickets/:id/body. The server refuses
# `ticket-owned` while a run holds the ticket: the body IS the claim-time
# assignment, so an edit under an open run reaches nobody — for a bound park
# the enrichment channel is the park ANSWER, never the body. A no-change
# rewrite answers (noop).
#
# gh mode is a meta-preserving read-modify-write: the prose is replaced and
# the trailing `board:meta` block is spliced back BYTE-FOR-BYTE — never
# parsed, never re-rendered — so unknown keys, comments and noncanonical
# spacing survive an older client. This is the safe counterpart to editing
# the body with bare `gh issue edit`, which clobbers the block.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -eq 3 ] && [ "$2" = --body-file ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" body_file="$3"
if [ "$body_file" = - ]; then
  body_file="$(mktemp)"
  cat > "$body_file"
else
  [ -f "$body_file" ] || die "no such file: $body_file"
fi

if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_FILE="$body_file" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_ID"].lstrip("#")
out = A.set_body(tid, open(os.environ["T_FILE"]).read())
print("#%s: body rewritten%s" % (tid, " (noop)" if out.get("noop") else ""))
PY
  _rerender_if_serving
  exit 0
fi

T_ID="$tid" T_FILE="$body_file" _py - <<'PY'
import os
import _board as B

env = os.environ
tid = env["T_ID"].lstrip("#")
# A dedicated single-issue read, NOT B.snapshot(): the verb needs one body,
# and the snapshot's GraphQL sweep is unstubable overhead a body edit has no
# business paying.
old = B.gh(["issue", "view", tid, "-R", B.repo(), "--json", "body",
            "--jq", ".body"])
new = open(env["T_FILE"]).read()
# The raw splice: the TRAILING meta block's bytes are carried through
# unchanged. META_RE is used for its byte OFFSET only — it anchors at the
# end of the body, so a marker-like example quoted in the prose can never be
# mistaken for the block — and its match text is never parsed or re-rendered.
m = B.META_RE.search(old)
if m:
    new = new.rstrip("\n") + "\n" + old[m.start():]
B.set_body(tid, new)
print("#%s: body rewritten" % tid)
PY

_rerender_if_serving
```

`chmod 755 skills/issue-tracker/scripts/board-body.sh`.

Then two comment updates in `board-register.sh`:
1. Header line `#   gh issue edit <number> --body-file <file>` becomes:
   `#   board-body.sh <number> --body-file <file>   (meta-preserving; both bindings)`
2. In the api-path comment block, replace the sentence `A1's body IS the assignment the claim hands the worker, and this client has no body-edit route (arkho#7) — so seeding a skeleton would ship an assignment nobody can fill and, worse, make the park question the skeleton's own text.` with: `A1's body IS the assignment the claim hands the worker at claim time — so seeding a skeleton would make the park question the skeleton's own text and ship a dispatchable assignment that says nothing. (A body-edit route exists — board-body.sh — but a skeleton that must be edited before dispatch is a skeleton that should not be born.)`

- [ ] **Step 4: Run.** `tests/claude-code/board-api/test-edge-verbs.sh` → PASS. `scripts/lint-shell.sh` clean.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(board-body): both-modes body-edit verb — api route + gh raw meta splice"`

---

### Task 5: Register — `note` field + spike-note removal

**Files:**
- Modify: `skills/issue-tracker/scripts/board-register.sh` (api python block)
- Test: `tests/claude-code/board-api/test-register-transition.sh` (adjust three asserts, add two)

- [ ] **Step 1: Rewrite the failing tests.** In `test-register-transition.sh`:

Replace the assert `park birth note prepends body` and its whole-body pin with:

```bash
t "park birth sends the note as its own field" '\"note\": \"which color?' \
  bash -c "V board-register.sh 'pick color' enhancement P2 --state needs-human --note 'which color?' >/dev/null; cat '$FIX.log'"
t "park birth body pins birth + note field, body absent" \
  '{"title": "pick color", "category": "work", "priority": "P2", "birth": "needs-human", "note": "which color?"}' \
  last_register_body
```

Replace the implicit env-issue assert's expected payload with:

```bash
t "implicit env-issue birth carries the note as the note field" \
  '{"title": "disk is full", "category": "env-issue", "priority": "P1", "note": "need ops to grow the volume"}' \
  last_register_body
```

Replace the `explicit non-park birth still keeps the note off the body` assert with:

```bash
# A non-park note is not a park question, and the server refuses a `note`
# field on a non-park OUTCOME — but the argument must not be silently lost
# either (it was, before this pass). It rides the body head, exactly as the
# implicit path always did.
t "explicit non-park birth prepends the note to the body head" \
  '{"title": "wire it up", "category": "work", "priority": "P2", "birth": "ready-for-implementer", "body": "fyi only\n\nthe spec"}' \
  last_register_body
```

Replace the two spike-pointer asserts (`spike->architect surfaces 409 + arkho#7`, `spike 409 carries the arkho#7 pointer`) with:

```bash
t "spike->architect surfaces the 409 code" "illegal-birth" cat "$SPIKE_OUT"
nt "no arkho#7 divergence note anymore — R2 shipped" "arkho/issues/7" cat "$SPIKE_OUT"
```

(and the earlier `a 500 on a spike birth does not blame arkho#7` pair stays — it passes trivially now, which is fine: it pins that outages never gain a canon note back.)

Add one assert for the bodyless demotion (implicit, no body, non-env category → client demotes to needs-info and the auto-note goes in the `note` field):

```bash
t "bodyless demotion sends its auto-note as the note field" \
  '"note": "registered with no body' \
  bash -c "V board-register.sh 'no spec here two' enhancement P2 >/dev/null; cat '$FIX.log'"
```

(Fixture bookkeeping: the `once` register fixtures form a queue — recount the register calls this file now makes and adjust the fixture list so responses line up; the final standing `/tickets` fixture absorbs the rest.)

- [ ] **Step 2: Run to verify failures.** `tests/claude-code/board-api/test-register-transition.sh` — the rewritten asserts fail against current behavior.

- [ ] **Step 3: Implement.** In `board-register.sh`'s api python block:

Replace the line `if note and (not explicit or state in PARK_BIRTHS): body = note + ("\n\n" + body if body else "")` and the demotion's note-into-body path with note-field logic. The full edited region (from the `PARK_BIRTHS` tuple to the `payload` assembly) becomes:

```python
PARK_BIRTHS = ("needs-human", "needs-info", "interactive-preferred")
# A PARK IS A QUESTION, and a question with no text is not one. gh mode makes
# the note mandatory for every park birth and for the implicit env-issue
# inversion; A1 falls back to body then TITLE, so the same call produced a
# park whose standing question was a ticket name. Enforced here because the
# server cannot tell the two apart.
if explicit and state in PARK_BIRTHS and not note and not body:
    A.die("--note is required for state %s — it is the question the park stands "
          "on (or pass --body-file, whose head A1 reads as that question)" % state)
if (not explicit and env["T_CATEGORY"] == "env-issue"
        and not note and not body and not env["T_REPAIR"]):
    A.die("an env-issue defaults to needs-human and requires --note naming the "
          "requested intervention (or an explicit --state with --repair-path "
          "naming an agent-executable repair)")
if not body and not env["T_BODY_FILE"]:
    if explicit and state in ("ready-for-architect", "ready-for-implementer"):
        A.die("a ticket with no body cannot be born into a dispatchable lane "
              "state — pass --body-file with the spec, or birth it "
              "needs-info/needs-human")
    if not explicit and env["T_CATEGORY"] != "env-issue":
        state = "needs-info"
        explicit = True
        if not note:
            note = ("registered with no body — re-register with --body-file once "
                    "the spec exists, then board-transition.sh to its lane state")
# THE NOTE'S TRANSPORT DEPENDS ON THE OUTCOME, which this client already
# computes (the explicit/PARK_BIRTHS/env-issue logic above mirrors the
# server's birthState). A park-outcome birth sends the real `note` field
# (arkho#7): the question travels verbatim as park_note and the body stays
# the statement of work. A non-park note is `note-not-applicable` to the
# server — but silently losing the argument is worse than either answer, so
# it rides the body head, as the implicit path always did. NOT a follow-up
# comment: registration commits first (a failed comment loses the note
# behind `duplicate` on retry), and a run registering a child may not
# comment on it at all.
park_outcome = (state in PARK_BIRTHS if explicit
                else env["T_CATEGORY"] == "env-issue")
if note and not park_outcome:
    body = note + ("\n\n" + body if body else "")
```

And in the payload assembly, after `payload["birth"] = state`:

```python
if note and park_outcome:
    payload["note"] = note
```

Then the spike-note removal: delete the `err = io.StringIO()` block, the `try/except BaseException` wrapper, the stderr replay, and the `illegal-birth`/spike conditional print — the call site becomes:

```python
out = A.register(payload)
print("%s %s/tickets/%s" % (out["id"], os.environ["BOARD_API_URL"], out["id"]))
```

Remove the now-unused `import contextlib`, `import io`, `import sys` from the block head. Also delete the comment paragraph above the old call (`The pointer below is a claim about CANON…`).

Update the api-path comment that starts `# No API note field for the birth question (arkho#7): the body head carries it.` — replace that first sentence with `# The note rides the real API note field for park-outcome births (arkho#7 shipped it); a non-park note rides the body head (see below).`

- [ ] **Step 4: Run.** `tests/claude-code/board-api/test-register-transition.sh` → PASS. `scripts/lint-shell.sh` clean.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(board-register): real note field for park births; R2 divergence note retired"`

---

### Task 6: `api-scale` render mode — template + dispatcher split

**Files:**
- Modify: `skills/reviewing-prs/references/review-worker-bootstrap.md` (new mode block + bindings)
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh` (`_claim_one_with_nonce`)
- Modify: `skills/reviewing-prs/SKILL.md` (api-entry scale paragraph)
- Test: `tests/claude-code/board-api/test-review-dispatch-claim.sh` (extend)

**Interfaces:**
- Consumes: claim response `pr`/`branch` (server contract, live since a05b1ac).
- Produces: rendered prompt binding lines `CLOSURE_PACKAGE:` / `INTEGRATION_REF:` for api-scale claims.

- [ ] **Step 1: Write the failing test.** In `test-review-dispatch-claim.sh`, add TWO NEW ISOLATED SCENARIOS — do NOT splice fixtures into the file's existing once-queue (the dispatcher loops to its cap, so a prepended grant shifts every existing scenario's consumption; and the file's existing claim fixture carries no URL `pr`, so it exercises the empty-`pr` fallback, not URL classification). Each scenario gets its OWN mock instance (fresh fixture file + port + `DAEMON_HOME`, the file's scaffold re-run — or a fresh sub-scope of it), is **lifecycle-complete** (grant + standing `{"claimed": false}` + `/runs/<id>/bind` 200 + activity/renew standing fixtures as the dispatcher needs), and asserts the HANDOFF SUCCEEDED, not just prompt text.

Scenario A — scale claim:

```json
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"claimed":true,"runId":61,"ticketId":88,"fence":2,"bearer":"scale-bearer",
          "body":"epic assignment","pr":"3141","branch":"epic/e9-integration",
          "parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/61/bind","status":200,"body":{"ok":true}}
]
```

```bash
SCALE_PROMPT="$DAEMON_HOME/prompt-88-api-qagent.md"
t "the scale dispatch reports the handoff" "claimed #88 run=61" <the-dispatch-invocation>
t "the bind reached the wire" '"path": "/runs/61/bind"' bash -c "cat '$FIX.log'"
t "an event-id pr renders the api-scale block" "SCALE REVIEWER of recomposition epic #88" cat "$SCALE_PROMPT"
t "the closure package binding rides the prompt" '`CLOSURE_PACKAGE`: 3141' cat "$SCALE_PROMPT"
t "the integration ref binding rides the prompt" '`INTEGRATION_REF`: epic/e9-integration' cat "$SCALE_PROMPT"
t "the scale prompt orders the integration checkout" "git fetch origin epic/e9-integration" cat "$SCALE_PROMPT"
nt "the scale prompt carries no PR-resolution order" "UNRESOLVED-resolve-from-the-PR" cat "$SCALE_PROMPT"
nt "the scale prompt never went out as mode api" "board is the Arkho board API, not GitHub issues: every board read" cat "$SCALE_PROMPT"
```

Scenario B — URL claim (real HTTPS `pr`), same lifecycle shape with `"pr":"https://github.com/o/r/pull/9","branch":"feat/x"` and run/ticket ids of its own:

```bash
t "a URL pr renders the api block" "resolving what that PR MERGES INTO" cat "$DAEMON_HOME/prompt-<B-ticket>-api-qagent.md"
t "the URL dispatch reports its handoff" "claimed #<B-ticket>" <the-dispatch-invocation-capture>
```

(implementer: reuse the file's scaffold helpers for both scenarios; `<the-dispatch-invocation>` is the file's existing dispatch-run capture idiom. The existing scenarios stay byte-identical.)

- [ ] **Step 2: Run to verify failure.** `tests/claude-code/board-api/test-review-dispatch-claim.sh` — new asserts fail (no api-scale block exists; the scale claim renders the api block).

- [ ] **Step 3: Implement the template.** In `review-worker-bootstrap.md`, after the `<!-- /mode:api -->` line of the opening framing section, add:

```markdown
<!-- mode:api-scale -->
You are the SCALE REVIEWER of recomposition epic #{{ISSUE_NUMBER}} in
{{REPO}} — the aggregate review of an epic, NOT a PR review. There is no
PR: this epic's children are already merged, and your entry artifact is
the closure package at event {{CLOSURE_PACKAGE}} on your own ticket.

This repo's board is the Arkho board API, not GitHub issues: every board
read and write goes through the scripts at {{BOARD_SCRIPTS}}, which speak
for your run through the credentials already in your environment
(`BOARD_RUN_TOKEN`, `BOARD_RUN_ID`, `BOARD_RUN_FENCE`, `BOARD_API_URL`).
`git` still reaches GitHub exactly as before.

Your assignment is the ticket text as the claim delivered it, at
{{TICKET_BODY_FILE}} — read it first; there is no other route to it.

**If the `INTEGRATION_REF` binding below is EMPTY, stop here**: the claim
carried no integration ref, and there is nothing to derive one from —
park immediately with
`{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-human "scale review: the claim carried no integration ref"`
and end your turn. (An empty ref must never reach the fetch: bare
`git fetch origin` can SUCCEED by fetching configured refs, and the
failure would surface one step late, at a checkout of `origin/`.)

Your worktree starts on the repo's current head; positioning it is yours
to do, before ORIENT: `git fetch origin {{INTEGRATION_REF}}` and
`git checkout origin/{{INTEGRATION_REF}}` — the epic's integration
branch, where the composed result lives. A fetch that fails is a hard
stop, never a fallback: park with
`{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-human`
naming the ref that would not fetch. `BASE_REF` below is the repo's
default branch — what this epic merges into — and the manifest snapshots
were taken from it.

The scale-review section of the protocol governs your verdicts.
<!-- /mode:api-scale -->
```

In the Runtime bindings section, extend the existing scale bindings block's mode marker so api-scale carries the same two lines — replace:

```markdown
<!-- mode:scale -->
- `CLOSURE_PACKAGE`: {{CLOSURE_PACKAGE}}
- `INTEGRATION_REF`: {{INTEGRATION_REF}}
<!-- /mode:scale -->
```

with:

```markdown
<!-- mode:scale -->
- `CLOSURE_PACKAGE`: {{CLOSURE_PACKAGE}}
- `INTEGRATION_REF`: {{INTEGRATION_REF}}
<!-- /mode:scale -->
<!-- mode:api-scale -->
- `CLOSURE_PACKAGE`: {{CLOSURE_PACKAGE}}
- `INTEGRATION_REF`: {{INTEGRATION_REF}}
- `TICKET_BODY_FILE`: {{TICKET_BODY_FILE}}
<!-- /mode:api-scale -->
```

Audit every other `<!-- mode:api -->` block in the template (grep them all): each one that also applies to the scale variant gets a duplicated `<!-- mode:api-scale -->` copy or — where the text is identical — the worker-facing lines are checked for PR-only assumptions. (The renderer has no multi-mode block syntax; duplication is the mechanism, exactly as pr/scale already duplicate.)

**Renderer note:** `_render_prompt`'s block regex is `<!-- mode:(\w+) -->` — `\w` does not match `-`, so `api-scale` needs the regex widened. In `review-dispatch.sh`'s `_render_prompt`, change both occurrences of `(\w+)` in the mode-block regex to `([\w-]+)`:

```python
t = re.sub(r"<!-- mode:([\w-]+) -->\n(.*?)<!-- /mode:\1 -->\n",
           lambda m: m.group(2) if m.group(1) == mode else "", t, flags=re.S)
```

- [ ] **Step 4: Implement the dispatcher split.** In `_claim_one_with_nonce` (review-dispatch.sh), extend the claim exchange python to emit the bindings — after the `fields` loop add:

```python
q("C_PR", out.get("pr") or "")
q("C_BRANCH", out.get("branch") or "")
```

and declare them in the `local` line: `local C_CLAIMED=0 C_RUN_ID="" C_TICKET="" C_FENCE="" C_BEARER="" C_PARENT_PIN="" C_PR="" C_BRANCH=""`.

Then replace the single `prompt="$(P_REVIEW_MODE=api …)"` render call with the split. Before the render, compute the mode:

```bash
  # The variant is the dispatcher's call — it alone sees the claim response.
  # Shape, not Number(): the entry-edge guard (arkho#7) makes a leaf's pr
  # URL-shaped, so a URL is the PR variant and anything else non-empty is an
  # epic's closure-package event id — the scale variant. An epic claim with
  # no integration branch parks via the worker (the api-scale block's fetch
  # hard-stop), not here: the dispatcher refusing to spawn would strand the
  # ticket with no park note naming the gap.
  local mode=api
  case "$C_PR" in
    http://*|https://*) mode=api ;;
    ?*) mode=api-scale ;;
  esac
```

and the render call becomes (only the changed/new P_ lines shown — keep every other existing line verbatim):

```bash
  prompt="$(P_REVIEW_MODE="$mode" P_WORKER_NAME="$name" \
    P_CLOSURE_PACKAGE="$C_PR" P_INTEGRATION_REF="$C_BRANCH" \
    P_REPO="$BOARD_REPO" P_BASE_REF="$([ "$mode" = api-scale ] && echo "$DEFAULT_BRANCH" || echo UNRESOLVED-resolve-from-the-PR)" \
    …existing P_ lines unchanged… \
    _render_prompt)"
```

(For `mode=api`, `P_CLOSURE_PACKAGE`/`P_INTEGRATION_REF` render into no surviving block — harmless.)

- [ ] **Step 5: Implement the SKILL.md replacement.** In `skills/reviewing-prs/SKILL.md`, replace the bullet beginning `- **an event id, not a URL** → the ticket is an epic carrying a closure-package event, i.e. the scale review. That variant is NOT executable under an API board today: …` (through `…a scale review belongs on a gh-bound repo until the bindings exist.`) with:

```markdown
- **an event id, not a URL** → the ticket is an epic carrying a
  closure-package event: the scale review. Your dispatch carried the
  bindings the claim response holds — `CLOSURE_PACKAGE` (the event id
  your run was stamped with) and `INTEGRATION_REF` (the epic's
  integration branch) — and your bootstrap's positioning order (fetch
  and check out the integration ref; base is the default branch)
  applies before ORIENT. **Scale review (recomposition epics)** below
  governs your entry artifact and verdicts: `done` on clean — the
  qagent epic close, legal with your run's stamped package — or a
  corrective child plus `ready-for-architect`, every board write
  through {{BOARD_SCRIPTS}}.
```

- [ ] **Step 6: Run.** `tests/claude-code/board-api/test-review-dispatch-claim.sh` → PASS (both scenarios). `scripts/lint-shell.sh` clean.

- [ ] **Step 7: Commit.** `git add -A && git commit -m "feat(review-dispatch): api-scale variant — closure/integration bindings off the claim, worker-owned checkout"`

---

### Task 7: Successor `parentPin` threading

**Files:**
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (successor claim exchange, `_successor_prompt`, `_stamp_lane`, both `_stamp_lane` call sites)
- Test: `tests/claude-code/board-api/test-sweep-resume.sh` (extend)

- [ ] **Step 1: Write the failing test.** In `test-sweep-resume.sh`, find the `/runs/claim-successor` fixture(s). Extend one success fixture with a pin:

```json
"parentPin":{"parent_id":7,"parent_event_cursor":118}
```

Add asserts (following the file's existing meta/prompt assertion idiom — it already checks the successor prompt content and registry meta):

```bash
t "successor meta carries the flattened parent pin" '"parent_pin": "#7 @ event 118"' \
  cat "$DAEMON_HOME/<delivered-uuid>.json"
t "the successor prompt carries the pin line" "Parent pin (your run's parent-contract window): #7 @ event 118" \
  cat "<captured-successor-prompt>"
```

and for a second scenario whose fixture has `"parentPin":null`:

```bash
nt "a null pin stamps no meta key" '"parent_pin"' cat "$DAEMON_HOME/<uuid2>.json"
nt "a null pin adds no prompt line" "Parent pin" cat "<captured-prompt-2>"
```

The file's existing scenarios already exercise BOTH delivery branches (resumed session and fresh spawn) — attach the pin fixture to one of each so both branches are pinned. (implementer: use the file's real uuid/prompt capture paths.)

- [ ] **Step 2: Run to verify failure.** `tests/claude-code/board-api/test-sweep-resume.sh` — new asserts fail.

- [ ] **Step 3: Implement.** In `_sweep_api.sh`:

(a) The successor claim exchange python (`out = A.claim_successor(…)` block): after `q("C_BEARER", out["bearer"])` add:

```python
pin = out.get("parentPin") or {}
q("C_PIN",
  "#%s @ event %s" % (pin.get("parent_id"), pin.get("parent_event_cursor"))
  if pin.get("parent_id") is not None else "")
```

(b) `_successor_prompt` gains the pin as a fourth argument — signature comment becomes `# <ticket> <run> <folded answer text ('' if none)> <parent pin ('' if none)>` and the heredoc body gains, after the `Read your own ticket timeline FIRST…` paragraph:

```bash
${4:+Parent pin (your run's parent-contract window): $4 — the parent contract
snapshot your dispatch was cut against; no board read hands it over.}
```

Call site: `prompt="$(_successor_prompt "$tid" "$C_RUN" "$text" "$C_PIN")"`.

(c) `_stamp_lane` gains an optional pin argument — signature `# <uuid> <lane> <role> [parent-pin]`; pass it into the python env as `T_PIN="${4:-}"` and inside the python, after `m["role"] = env["T_ROLE"]`:

```python
    if env.get("T_PIN"):
        m["parent_pin"] = env["T_PIN"]
```

(d) The call site at the shared post-bind point becomes `_stamp_lane "$delivered" "$lane" "$role" "$C_PIN"`. (This is the ONE stamp point both delivery branches share — `_persist_successor` is deliberately not touched; see spec §7.)

- [ ] **Step 4: Run.** `tests/claude-code/board-api/test-sweep-resume.sh` → PASS. Also `tests/claude-code/board-api/test-sweep-renew-relay.sh` (shares the file under test) → PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(sweep): successor parentPin — stamped at _stamp_lane, delivered in the orientation prompt"`

---

### Task 8: Read parity — `board-show.sh` + `board-map.sh`

**Files:**
- Modify: `skills/issue-tracker/scripts/board-show.sh` (api header line)
- Modify: `skills/issue-tracker/scripts/board-map.sh` (`api_snapshot`)
- Test: `tests/claude-code/board-api/test-read-verbs.sh` (extend)

- [ ] **Step 1: Write the failing test.** In `test-read-verbs.sh`, extend the `GET /tickets` fixture rows with the new columns:

```json
"branch":"feat/x","blocked_by":[3,4],"relates":[9]
```

Add asserts:

```bash
t "show prints branch and both edge arrays" "branch=feat/x blocked_by=[3 4] relates=[9]" \
  V board-show.sh 12
t "empty arrays print as []" "blocked_by=[] relates=[]" V board-show.sh 13
```

(row 13 in the fixture carries `"blocked_by":[],"relates":[]`.) For the map: the file's existing map assert (if none exists, add one) runs `board-map.sh --write` and greps `BOARD.html`:

```bash
t "map draws the dependency edge" 'data-edge="blocked_by"' \
  bash -c "V board-map.sh --write >/dev/null; cat '$r/BOARD.html'"
# The cue has THREE consumers; assert each in the ARTIFACT, with fixture rows
# that would be eligible under gh rules (a ready-state leaf, no blockers) so a
# still-derived cue actually fires and the nt asserts discriminate:
nt "no serialized eligible:true on api nodes" '"eligible": true' bash -c "cat '$r/BOARD.html'"
nt "no s_elig card class on api nodes" 's_elig' bash -c "cat '$r/BOARD.html'"
t "the legend says eligibility is server-owned" "server-owned (API mode)" bash -c "cat '$r/BOARD.html'"
```

(implementer: read the renderer to confirm the real spellings of the edge markup, the serialized flag, the card class, and the label — pin the ACTUAL strings, and first verify each `nt` string DOES appear when the same fixture renders under the pre-change code, so the asserts fail against the parent commit rather than passing vacuously.)

- [ ] **Step 2: Run to verify failure.** `tests/claude-code/board-api/test-read-verbs.sh` — new asserts fail.

- [ ] **Step 3: Implement `board-show.sh`.** The api header print becomes:

```python
        print("#%s %s %s %s  owner_run=%s plan=%s pr=%s branch=%s "
              "blocked_by=[%s] relates=[%s]" %
              (t["id"], t["state"], t.get("priority") or "-", t["title"],
               t.get("owner_run"), t.get("plan"), t.get("pr_url"),
               t.get("branch"),
               " ".join(str(b) for b in t.get("blocked_by") or []),
               " ".join(str(x) for x in t.get("relates") or [])))
```

- [ ] **Step 4: Implement `board-map.sh`.** In `api_snapshot()`, the row mapping becomes:

```python
        out[str(row["id"])] = {
            "title": row.get("title") or "",
            "state": row.get("state") or "",
            "priority": row.get("priority"),
            "category": row.get("category"),
            "note": row.get("note"),
            "parent": str(row["parent"]) if row.get("parent") else None,
            "blocked_by": [str(b) for b in row.get("blocked_by") or []],
            "spawned_by": None,
            "relates_to": [str(x) for x in row.get("relates") or []],
            "branch": row.get("branch"), "pr": row.get("pr_url"), "prs": [],
            "close_candidate": False, "url": None,
            "created": "", "updated": "",
        }
```

Rewrite the docstring's degradation paragraph to:

```python
    """GET /tickets, normalized to the node shape the renderer below consumes.

    The projection now carries blocked_by / relates / branch (arkho#7), so
    dependency and relates edges render. What it still does not carry:
    spawned_by (those edges don't render), PR linkage, issue URL, and
    timestamps (nodes carry no links or ages). The ELIGIBLE cue stays OFF
    for api nodes: B.eligible's blocker rule (every blocker done) disagrees
    with the server's claim predicate (done|wontfix terminal, plus lane,
    epic and ownership terms no projection exposes) — a client-derived cue
    would tell an operator a claimable ticket is waiting. Eligibility is
    the server's answer here, as board-list.sh already says.
    """
```

Then kill the cue at ITS DERIVATION, not one consumer: `B.eligible` feeds THREE independent surfaces in `board-map.sh` — the Markdown label, the HTML card class (`s_elig`), and the serialized node's `eligible` flag. Grep every `B.eligible` call/derived field in the file and compute ONE api-aware value at each derivation point — `elig = (not API) and B.eligible(...)` — so all three consumers read the same answer; clearing only the node field would leave an api card visibly badged. The table/legend note for api boards says `eligibility: server-owned (API mode)`, placed where the existing degradation note lives.

- [ ] **Step 5: Run.** `tests/claude-code/board-api/test-read-verbs.sh` → PASS.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat(board-reads): projection parity — branch/blocked_by/relates in show and map; server-owned eligibility"`

---

### Task 9: Integration drills against the real service

**Files:**
- Modify: `tests/claude-code/board-api/integration/test-protocol-walk.sh` (extend) — or, if cleaner, create `tests/claude-code/board-api/integration/test-human-verbs.sh` following `drill-lib.sh`'s idiom
- Env: `ARKHO_DIR=/Users/new/Developer/GitHub/arkho` (the checkout sits at merged main `a05b1ac`), harness via `integration/harness.sh start`

- [ ] **Step 1: Read `drill-lib.sh` and one existing drill** (`test-protocol-walk.sh`) to absorb the harness idiom: env sourcing, principal tokens, drill assertions, teardown.

- [ ] **Step 2: Write the drill.** New file `test-human-verbs.sh` (755), covering in ONE flow (each step asserts on real service state — `GET /tickets` rows or refusal codes):

1. Register leaf A (with body) and leaf B; `board-edge.sh A --block B` → A's row shows `blocked_by:[B]`.
2. A qagent/implementer claim on A's lane does NOT draw A (blocked); `board-edge.sh A --unblock B` → the claim draws A. End that run (`abandoned`).
3. `board-priority.sh A P0` → row shows P0; re-run → `(noop)` printed.
4. `board-relate.sh A B` → both rows report each other; `board-relate.sh B A --cut` (the other endpoint) cuts it.
5. Register epic E; `board-edge.sh A --parent E` → row parent=E; `--orphan` clears.
6. `board-body.sh A --body-file <new>` succeeds; claim A (implementer lane), then `board-body.sh` again → stderr contains `ticket-owned`, exit nonzero; end the run, edit commits.
7. Register a park birth with `--note "q?" --body-file spec` → `GET /queue/decisions` (via `A.queue_decisions`) shows question `q?` and the ticket body is `the spec` (note NOT prepended).
8. Register a spike `--state ready-for-architect --body-file s` → succeeds (R2), output carries no `arkho/issues/7`.
9. **The R1 headline end-to-end:** register leaf L with body → transition `in-progress` (branch recorded) → transition `in-review --pr https://example.com/pr/1` → qagent claim draws L → as the run actor (`BOARD_RUN_TOKEN`/`BOARD_RUN_FENCE` from the claim), `board-transition.sh L done` → row shows `done`.

- [ ] **Step 3: Run the tier.** `ARKHO_DIR=/Users/new/Developer/GitHub/arkho tests/claude-code/board-api/integration/harness.sh start`, then the new drill, then the existing integration drills (`test-protocol-walk.sh`, `test-resume-first.sh`, `test-crash-boundaries.sh`, `test-lease-renewal.sh`, `test-escalation.sh`, `test-transcript-diff.sh`) — all must stay green; `harness.sh stop`. Expected: `PASS` per file.

- [ ] **Step 4: Commit.** `git add -A && git commit -m "test(integration): human-verb + R1 leaf-close drills against the real A1 service"`

---

### Task 10: Full-suite verification, live acceptance, version bump

**Files:**
- Modify: version manifests via `scripts/bump-version.sh` only
- No other source changes (fixes discovered here route back through review)

- [ ] **Step 1: Full local suites.**

```bash
for t in tests/claude-code/board-api/test-*.sh; do "$t" || echo "SUITE-FAIL $t"; done
ARKHO_DIR=/Users/new/Developer/GitHub/arkho tests/claude-code/board-api/integration/harness.sh start
for t in tests/claude-code/board-api/integration/test-*.sh; do "$t" || echo "SUITE-FAIL $t"; done
tests/claude-code/board-api/integration/harness.sh stop
tests/claude-code/run-skill-tests.sh
scripts/lint-shell.sh
```

Expected: no `SUITE-FAIL`, lint clean.

- [ ] **Step 2: Spec acceptance, as written.** Execute spec §Acceptance items 1–10 (most are covered by the suites above — check each off against the test that proves it; run any not yet covered by hand against the harness).

- [ ] **Step 3: Live acceptance (spec item 11), against production.** Source nothing into the repo; use the human credentials file the binding resolves for a scratch clone bound to `arkho-board-service.onrender.com`. Drive: register scratch leaf (body) → `in-progress` → `in-review` with a real-shaped `https://` pr → qagent claim (automation token) → run-actor `board-transition.sh <id> done` with the claim's fence → confirm `done` on `GET /tickets`. Then clean up: the ticket is terminal (done) — leave it; end any open run. Record the transcript of commands (not tokens) in the SDD ledger.

- [ ] **Step 4: Version bump + spec retrospective.**

```bash
scripts/bump-version.sh minor
```

Write the spec's `## Outcomes & Retrospective` (replacing "Pending — written at finish.") and update `## Revision Notes`. Commit: `git add -A && git commit -m "release: vX.Y.0 — dp#51 A1-route consumption (five human verbs, api-scale review, note field, parentPin, read parity)"` (substitute the real version).
