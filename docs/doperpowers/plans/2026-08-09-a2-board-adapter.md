# A2 Plugin Board Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The issue-tracker toolkit and dispatch scripts speak the Arkho board
API as a per-repo binding (gh mode untouched and default), per
`docs/doperpowers/specs/2026-08-09-a2-board-adapter-design.md` v1.1.

**Architecture:** Verb-level thin client — each `board-*.sh` branches on
`BOARD_BINDING` at the top; in API mode the verb is a thin HTTP call through a
new stdlib-only client core (`_board_api.py`) and `_board.py`'s state-machine
half is never imported (the server enforces legality). The sweep becomes a
four-phase tick (renew → relay → resume-first → fresh claims); relay
idempotence rides a transcript sentinel; recovery escalates via env-issue +
registry suppression.

**Tech Stack:** bash + python3 stdlib (`urllib`, `json`) only. No new runtime
dependencies. Tests: the existing `tests/claude-code/` shell-test pattern; a
stdlib mock HTTP server for the unit tier; the arkho repo's `board-service/`
on local Postgres for the integration tier (gated by `ARKHO_DIR`).

## Global Constraints

- **The spec is the contract:** `docs/doperpowers/specs/2026-08-09-a2-board-adapter-design.md` (v1.1). The API contract is `$ARKHO_DIR/board-service/API.md` — when this plan and API.md disagree on a payload, API.md wins and the divergence goes in the spec's Revision Notes.
- Binding file: `.doperpowers/board.json` at the consumer repo root, shape `{"binding": "api", "url": "https://…"}`. Absent or `"binding": "gh"` → gh mode, byte-identical behavior to pre-A2.
- Credentials file: `~/.arkho-board/<repo-slug>.env` (override: `$BOARD_CREDENTIALS_FILE`), carrying `BOARD_AUTOMATION_TOKEN` and `BOARD_HUMAN_TOKEN`. Never checked in, never logged.
- Worker env contract (injected at spawn): `BOARD_RUN_TOKEN`, `BOARD_RUN_ID`, `BOARD_RUN_FENCE`, `BOARD_API_URL`.
- Principal fixed per script: sweep/dispatch/relay verbs → automation; interactive verbs → human; run token in env always wins. One exception: `board-answer.sh` is dual-principal (answer=human, relay/ack=automation).
- In API mode `gh` is NEVER invoked — any `gh` call reached under `BOARD_BINDING=api` is a bug.
- Relay sentinel, exact format: `[board-relay answer:<answerEventId>]` — mandatory in every delivery vehicle (sweep relay, successor fold, board-answer inline).
- API error identifiers (`illegal-transition`, `fence-mismatch`, `lost-race`, `nonce-consumed`, `stale-resume`, …) are surfaced verbatim in `die` messages.
- Lanes claimed: `architect`/`implementer`/`spike` by implement-dispatch, `qagent` by review-dispatch, `ops` by nobody.
- Retry policy: GETs + claim-family POSTs retry on transport failure; transitions/answers never blind-retried; `lost-race`/`superseded`/`stale-resume` are outcomes, not errors.
- Local caps enforced against the local registry BEFORE claiming (implement + spike share `IMPLEMENT_MAX_CONCURRENT`); `laneCap` passed with the same value as a server belt.
- Category map at register: `bug`→`work`, `enhancement`→`work`, `spike`/`env-issue` pass through. Spike born `ready-for-architect` in API mode: surface the server's `409 illegal-birth` verbatim plus one line naming arkho#7 (gh-only until ruled).
- Park-birth `--note` in API mode: prepended to `body` as its opening line, then also sent nowhere else (no API field exists; arkho#7 carries the contract fix).
- All new/edited shell passes `scripts/lint-shell.sh` (shellcheck baseline).
- Version bump at the end via `scripts/bump-version.sh` only — never hand-edit manifests.

## File Structure

| Path | Responsibility |
|---|---|
| `skills/issue-tracker/scripts/_lib.sh` | + binding resolution (`BOARD_BINDING`, `BOARD_API_URL`), credential-file path resolution; gh checks become gh-mode-only |
| `skills/issue-tracker/scripts/_board_api.py` | NEW — the only HTTP surface: request assembly, principal resolution, error mapping, retry, one helper per route |
| `skills/issue-tracker/scripts/board-comment.sh` | NEW verb, both modes (gh: `gh issue comment`; api: `POST /tickets/:id/comment` incl. typed E2 kinds) |
| `skills/issue-tracker/scripts/board-{register,transition,answer,list,show,bind,reconcile,lint,map,edge,priority,relate,migrate-gh}.sh` | API branch at top of each; gh path untouched below |
| `skills/issue-tracker/scripts/board-sweep.sh` | API-mode four-phase tick (delegates to `_sweep_api.sh`) |
| `skills/issue-tracker/scripts/_sweep_api.sh` | NEW — the four phases as functions (renew+bind-repair, relay, resume-first, dispatch hand-off), suppression records |
| `skills/implementing/scripts/implement-dispatch.sh` | API branch: claim-based dispatch (architect/implementer/spike), nonce lifecycle, env injection, spawn-completed marker |
| `skills/reviewing-prs/scripts/review-dispatch.sh` | API branch: qagent claims, same nonce/env pattern |
| `skills/implementing/references/worker-bootstrap.md` | API-mode substitution block (TICKET_ID, body file, credential env note) |
| `skills/implementing/SKILL.md:82`, `skills/architecting/SKILL.md:56`, `skills/reviewing-prs/SKILL.md:277` | raw `gh issue comment` → `board-comment.sh` (one mechanical substitution each) |
| `tests/claude-code/board-api/mock-server.py` | NEW — stdlib mock A1 (fixture-driven, records requests) |
| `tests/claude-code/board-api/test-*.sh` | NEW unit tier |
| `tests/claude-code/board-api/integration/*.sh` | NEW integration tier (ARKHO_DIR-gated): protocol walk, transcript diff, crash drill, resume-first, renewal, escalation |

Interfaces threaded through every task (fixed here, verbatim):

```
# _board_api.py — module-level functions (all die() on mapped API errors):
api_url() -> str
request(method, path, body=None, principal="auto", ok=(200,)) -> dict|list
#   principal: "auto" (run token if set, else die), "automation", "human"
claim(lane, nonce, lease_minutes=None, lane_cap=None) -> dict
claim_successor(ticket_id, nonce, lease_minutes=None) -> dict
needing_resume() -> list
unrelayed() -> list
ack(answer_event_id) -> dict
renew(run_id) -> dict                    # 409 run-ended -> raises RunEnded
bind(run_id, store_ns, project_key, session_id) -> dict
end_run(run_id, reason="completed") -> dict
register(payload: dict) -> dict          # {"id": N, "state": "..."}
transition(tid, to, note=None, pr=None, plan=None, branch=None, fence=None) -> dict
comment(tid, kind, text=None, body=None) -> dict   # {"eventId": N}
park_answer(tid, replies, to=None, correlation_id=None) -> dict
tickets(state=None, category=None) -> list
timeline(tid) -> dict                    # {"records": [...]}
queue_decisions() -> list
class RunEnded(Exception): ...
SENTINEL = "[board-relay answer:%s]"     # % answerEventId
```

```
# _lib.sh exports (after Task 1):
BOARD_BINDING            api | gh
BOARD_API_URL            set iff api (env override wins)
BOARD_CREDENTIALS_FILE   default ~/.arkho-board/$(basename "$BOARD_ROOT").env
_api_py                  like _py but also exports the three above
```

```
# Registry meta additions (daemon JSON, written by dispatch/sweep):
run_id, fence, nonce, spawn_completed (bool), bind_confirmed (bool),
resume_attempts (int)
# Claim journal: $DAEMON_HOME/board-claims/<nonce>.json
#   {"lane": "...", "run_id": N|null, "spawn_completed": bool}
# Suppression: $DAEMON_HOME/board-suppress/<ticket>.json
#   {"ticket": N, "state": "...", "env_issue": N}
```

---

### Task 1: Binding resolution in `_lib.sh`

**Files:**
- Modify: `skills/issue-tracker/scripts/_lib.sh:36-45` (the `BOARD_REPO` block)
- Test: `tests/claude-code/board-api/test-binding.sh`
- Create: `tests/claude-code/board-api/helpers.sh`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `skills/issue-tracker/scripts/_binding.sh` — a SIDE-EFFECT-FREE sourceable that resolves `BOARD_BINDING`, `BOARD_API_URL`, `BOARD_CREDENTIALS_FILE`, `BOARD_ROOT` and defines `_api_py`; it never touches gh. `_lib.sh` sources it; the dispatch scripts and `board-sweep.sh` (Tasks 7-9) source it EARLY — before any gh initialization — which is what makes their API branches reachable without gh installed.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/helpers.sh`:

```bash
#!/usr/bin/env bash
# helpers.sh — board-api test scaffolding. Source from every test in this dir.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
FAILS=0
t() {  # t <name> <expected-substring> -- cmd...
  local name="$1" want="$2"; shift 3 || { echo "t: bad call"; exit 2; }
  local out; out="$("$@" 2>&1)" || true
  if grep -qF -- "$want" <<<"$out"; then echo "ok   $name"
  else echo "FAIL $name — wanted '$want' in:"; sed 's/^/     /' <<<"$out"; FAILS=$((FAILS+1)); fi
}
mkrepo() {  # fresh throwaway git repo, prints its path
  local d; d="$(mktemp -d)"; git -C "$d" init -q; echo "$d"
}
finish() { [ "$FAILS" -eq 0 ] && echo "PASS $(basename "$0")" || { echo "FAIL $(basename "$0") ($FAILS)"; exit 1; }; }
```

`tests/claude-code/board-api/test-binding.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"

# probe prints what _lib.sh resolved
probe() { ( cd "$1" && bash -c ". '$SCRIPTS/_lib.sh'; echo \"\$BOARD_BINDING|\${BOARD_API_URL:-}|\$(basename \"\$BOARD_CREDENTIALS_FILE\")\"" ); }

r1="$(mkrepo)"                                   # no binding file -> gh
t "absent file is gh mode" "gh||" probe "$r1"

r2="$(mkrepo)"; mkdir -p "$r2/.doperpowers"
printf '{"binding":"api","url":"https://b.example"}' > "$r2/.doperpowers/board.json"
t "api binding resolves" "api|https://b.example|$(basename "$r2").env" probe "$r2"

r3="$(mkrepo)"; mkdir -p "$r3/.doperpowers"
printf '{"binding":"gh"}' > "$r3/.doperpowers/board.json"
t "explicit gh is gh mode" "gh||" probe "$r3"

r4="$(mkrepo)"; mkdir -p "$r4/.doperpowers"
printf '{"binding":"api"}' > "$r4/.doperpowers/board.json"   # api without url
t "api without url dies" "board.json names binding=api but no url" probe "$r4"

t "env url override wins" "api|https://o.example|" \
  env BOARD_API_URL=https://o.example probe "$r2"
finish
```

Note for the `t` helper: gh-mode probes run in repos with no `gh` remote —
`_lib.sh`'s gh-mode BOARD_REPO resolution must not die before printing. The
test relies on Step 3 moving that check out of load time for repos where it
already ran, so set `BOARD_REPO=o/r` in `probe`:

```bash
probe() { ( cd "$1" && BOARD_REPO=o/r bash -c ". '$SCRIPTS/_lib.sh'; echo \"\$BOARD_BINDING|\${BOARD_API_URL:-}|\$(basename \"\$BOARD_CREDENTIALS_FILE\")\"" ); }
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `bash tests/claude-code/board-api/test-binding.sh`
Expected: FAIL lines (BOARD_BINDING is unset today — probes print nothing matching).

- [ ] **Step 3: Implement**

Create `skills/issue-tracker/scripts/_binding.sh` — deliberately a separate
sourceable, NOT part of `_lib.sh`: the dispatch scripts (Tasks 7-9) must
resolve the binding before their gh-mode initialization runs, and sourcing all
of `_lib.sh` there would collide with their own `die`/env definitions. It must
be safe to source from any script (no `set` changes, no gh, computes
`BOARD_ROOT` itself if unset):

```bash
#!/usr/bin/env bash
# _binding.sh — per-repo board-binding resolution (A2). Side-effect-free:
# sourceable from ANY entry point BEFORE gh-mode initialization. Defines
# BOARD_BINDING, BOARD_API_URL, BOARD_CREDENTIALS_FILE, BOARD_ROOT, _api_py.
# .doperpowers/board.json selects the substrate: absent or {"binding":"gh"}
# -> gh mode, byte-identical to pre-A2; {"binding":"api","url":...} -> the
# toolkit speaks the Arkho board API and gh is neither required nor invoked.
BOARD_BINDING=gh
BOARD_API_URL="${BOARD_API_URL:-}"
if [ -z "${BOARD_ROOT:-}" ]; then
  BOARD_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || { echo "error: not inside a git repo" >&2; return 1 2>/dev/null || exit 1; }
fi
if [ -f "$BOARD_ROOT/.doperpowers/board.json" ]; then
  _binding_line="$(python3 - "$BOARD_ROOT/.doperpowers/board.json" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception as e:
    print("parse-error: %s" % e); sys.exit(0)
print("%s|%s" % (cfg.get("binding", "gh"), cfg.get("url", "")))
PY
)"
  case "$_binding_line" in
    parse-error*) echo "error: .doperpowers/board.json: ${_binding_line#parse-error: }" >&2
                  return 1 2>/dev/null || exit 1 ;;
    api\|*) BOARD_BINDING=api
            [ -n "$BOARD_API_URL" ] || BOARD_API_URL="${_binding_line#api|}"
            [ -n "$BOARD_API_URL" ] || { echo "error: .doperpowers/board.json names binding=api but no url" >&2
                                         return 1 2>/dev/null || exit 1; } ;;
  esac
fi
BOARD_CREDENTIALS_FILE="${BOARD_CREDENTIALS_FILE:-$HOME/.arkho-board/$(basename "$BOARD_ROOT").env}"
export BOARD_BINDING BOARD_API_URL BOARD_CREDENTIALS_FILE BOARD_ROOT

# Run an inline python3 board operation with the API client importable and the
# binding env visible. _BINDING_DIR: this file's own directory, so non-board
# entry points (dispatch scripts) get the right PYTHONPATH without BOARD_SCRIPTS.
_BINDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_api_py() { PYTHONPATH="$_BINDING_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
  python3 "$@"; }
```

Then in `_lib.sh`, replace lines 36-45 (the whole `BOARD_REPO` resolution
block) with:

```bash
# shellcheck source=_binding.sh
. "$BOARD_SCRIPTS/_binding.sh"

# The target repo (owner/name) — gh mode only: $BOARD_REPO wins, else the
# checkout's repo. Fail-loud when gh is missing/unauthenticated/offline.
if [ "$BOARD_BINDING" = gh ] && [ -z "${BOARD_REPO:-}" ]; then
  command -v gh >/dev/null 2>&1 || die "\`gh\` not found — the board lives on GitHub"
  BOARD_REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "cannot resolve the GitHub repo (gh auth status? set BOARD_REPO=owner/name)"
fi
export BOARD_REPO
```

(`BOARD_SCRIPTS` is defined a few lines above the replaced block; keep the
existing `_py`, `DAEMON_HOME`, render-cache and server-pid helpers exactly as
they are.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash tests/claude-code/board-api/test-binding.sh`
Expected: `PASS test-binding.sh`

Also run the existing suite to prove gh mode is untouched:
Run: `tests/claude-code/run-skill-tests.sh`
Expected: same pass set as on the parent commit.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_binding.sh skills/issue-tracker/scripts/_lib.sh tests/claude-code/board-api/
git commit -m "feat(a2): per-repo board binding resolution (_binding.sh, sourceable pre-gh)"
```

---

### Task 2: `_board_api.py` client core + mock server

**Files:**
- Create: `skills/issue-tracker/scripts/_board_api.py`
- Create: `tests/claude-code/board-api/mock-server.py`
- Test: `tests/claude-code/board-api/test-client-core.sh`

**Interfaces:**
- Consumes: `BOARD_API_URL`, `BOARD_CREDENTIALS_FILE`, `BOARD_RUN_TOKEN`/`BOARD_RUN_ID`/`BOARD_RUN_FENCE` env (Task 1's exports).
- Produces: every function in the File Structure interface block, exactly as named there. Later tasks import `_board_api as A` inside `_api_py` heredocs.

- [ ] **Step 1: Write the mock server** (fixture-driven; also the unit tier's backbone)

`tests/claude-code/board-api/mock-server.py`:

```python
#!/usr/bin/env python3
"""Fixture-driven mock of the A1 board API for the hermetic unit tier.

Usage: mock-server.py <fixtures.json> <port>
fixtures.json: [{"method": "POST", "path": "/tickets", "status": 200,
                 "body": {...}, "once": false}, ...]
First match wins; "once" entries are consumed. Every request is appended to
<fixtures.json>.log as {"method","path","auth","body"} — tests assert on it.
Responses are contract-shaped (API.md); awkward cases (409 bodies, empty
lists) come from the real service's observed output.
"""
import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FIXTURES = json.load(open(sys.argv[1]))
LOG = open(sys.argv[1] + ".log", "a")
LOCK = threading.Lock()

class H(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        with LOCK:
            LOG.write(json.dumps({"method": self.command, "path": self.path,
                                  "auth": self.headers.get("authorization", ""),
                                  "body": raw}) + "\n"); LOG.flush()
            for f in FIXTURES:
                if f.get("used"): continue
                if f["method"] == self.command and self.path.startswith(f["path"]):
                    if f.get("once"): f["used"] = True
                    body = json.dumps(f.get("body", {})).encode()
                    self.send_response(f.get("status", 200))
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                    self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.end_headers()
    do_GET = do_POST = do_PUT = _handle
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[2])), H).serve_forever()
```

- [ ] **Step 2: Write the failing test**

`tests/claude-code/board-api/test-client-core.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8471
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,
  "body":{"runId":41,"ticketId":12,"fence":3,"bearer":"tok-abc","plan":null,
          "body":"do the thing","parentPin":null}},
 {"method":"POST","path":"/tickets/12/transition","status":409,
  "body":{"error":"fence-mismatch","message":"fence 2 != 3"}},
 {"method":"GET","path":"/answers/unrelayed","status":200,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101","replies":["yes"]}]},
 {"method":"POST","path":"/runs/41/renew","status":409,
  "body":{"error":"run-ended","message":"run 41 has ended"}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3

CORE="import _board_api as A"
run_py() { PYTHONPATH="$SCRIPTS" BOARD_API_URL="http://127.0.0.1:$PORT" \
  BOARD_CREDENTIALS_FILE="$1" python3 -c "$2"; }

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=auto-tok\nBOARD_HUMAN_TOKEN=human-tok\n' > "$CREDS"

t "claim returns dict + auth header sent" "41" \
  run_py "$CREDS" "$CORE
print(A.claim('implementer','n-1')['runId'])"
t "automation token on claim" '"auth": "Bearer auto-tok"' cat "$FIX.log"
t "run token wins over files" "tok-999" \
  env BOARD_RUN_TOKEN=tok-999 run_py "$CREDS" "$CORE
import os; print(A.token('auto'))"
t "409 error mapped verbatim" "fence-mismatch" \
  run_py "$CREDS" "$CORE
try: A.transition(12, 'in-review', fence=2)
except SystemExit: pass" 
t "run-ended raises typed" "RunEnded" \
  run_py "$CREDS" "$CORE
try: A.renew(41)
except A.RunEnded: print('RunEnded')"
t "unrelayed returns list" "118" \
  run_py "$CREDS" "$CORE
print(A.unrelayed()[0]['answerEventId'])"
t "missing creds file dies loud" "board credentials file" \
  run_py "/nonexistent" "$CORE
A.claim('implementer','n-2')"
finish
```

- [ ] **Step 3: Run to verify it fails**

Run: `bash tests/claude-code/board-api/test-client-core.sh`
Expected: FAILs — `_board_api` doesn't exist yet.

- [ ] **Step 4: Implement `_board_api.py`**

```python
"""_board_api.py — the toolkit's ONLY HTTP surface for the Arkho board API.

Thin by design (spec: verb-level thin client): request assembly, principal
resolution, contract error mapping, retry. No state-machine logic — the
server enforces legality; _board.py's upper half is never imported in API
mode.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

SENTINEL = "[board-relay answer:%s]"
_RETRIES = 3          # transport-level, idempotent requests only
_RETRY_WAIT = 2.0


class RunEnded(Exception):
    """409 run-ended — the caller's run was reaped; callers route, not die."""


def die(msg):
    print("error: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def api_url():
    url = os.environ.get("BOARD_API_URL", "").rstrip("/")
    if not url:
        die("BOARD_API_URL is not set — is this repo bound to a board API? "
            "(.doperpowers/board.json)")
    return url


def _creds():
    path = os.environ.get("BOARD_CREDENTIALS_FILE", "")
    if not path or not os.path.isfile(path):
        die("board credentials file not found at %r — create it with "
            "BOARD_AUTOMATION_TOKEN=… and BOARD_HUMAN_TOKEN=… lines" % path)
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def token(principal):
    """principal: 'auto' (run token or die), 'automation', 'human'."""
    run_tok = os.environ.get("BOARD_RUN_TOKEN", "")
    if run_tok:                      # a run context always speaks as the run
        return run_tok
    if principal == "auto":
        die("no BOARD_RUN_TOKEN in env and the caller demanded the run "
            "principal — this verb is worker-context-only here")
    key = {"automation": "BOARD_AUTOMATION_TOKEN",
           "human": "BOARD_HUMAN_TOKEN"}[principal]
    val = _creds().get(key, "")
    if not val:
        die("%s missing from %s" % (key, os.environ.get("BOARD_CREDENTIALS_FILE")))
    return val


def request(method, path, body=None, principal="auto", ok=(200,), retry=None):
    """One HTTP exchange. Dies with the contract's error identifier on
    refusal; raises RunEnded on 409 run-ended (callers route on it)."""
    if retry is None:
        retry = method == "GET"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url() + path, data=data, method=method)
    req.add_header("authorization", "Bearer " + token(principal))
    if data is not None:
        req.add_header("content-type", "application/json")
    attempts = _RETRIES if retry else 1
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read().decode() or "{}"
                if resp.status in ok:
                    return json.loads(payload)
                die("%s %s answered %s: %s" % (method, path, resp.status, payload))
        except urllib.error.HTTPError as e:
            payload = e.read().decode() or "{}"
            try:
                err = json.loads(payload)
            except ValueError:
                err = {"error": "http-%s" % e.code, "message": payload[:400]}
            if err.get("error") == "run-ended":
                raise RunEnded(err.get("message", ""))
            # a refusal is an answer, never retried
            die("%s %s refused: %s — %s"
                % (method, path, err.get("error", e.code), err.get("message", "")))
        except (urllib.error.URLError, OSError) as e:
            last = e
            if i + 1 < attempts:
                time.sleep(_RETRY_WAIT)
    die("%s %s unreachable after %d attempts: %s" % (method, path, attempts, last))


# ---- route helpers (payload shapes verbatim from API.md) -------------------

def claim(lane, nonce, lease_minutes=None, lane_cap=None):
    body = {"lane": lane, "dispatchNonce": nonce}
    if lease_minutes is not None:
        body["leaseMinutes"] = lease_minutes
    if lane_cap is not None:
        body["laneCap"] = lane_cap
    return request("POST", "/runs/claim", body, "automation", retry=True)


def claim_successor(ticket_id, nonce, lease_minutes=None):
    body = {"ticketId": int(ticket_id), "dispatchNonce": nonce}
    if lease_minutes is not None:
        body["leaseMinutes"] = lease_minutes
    return request("POST", "/runs/claim-successor", body, "automation", retry=True)


def needing_resume():
    return request("GET", "/runs/needing-resume", principal="automation")


def unrelayed():
    return request("GET", "/answers/unrelayed", principal="automation")


def ack(answer_event_id):
    return request("POST", "/answers/%s/ack" % int(answer_event_id),
                   {}, "automation", retry=True)   # set-once idempotent


def renew(run_id):
    return request("POST", "/runs/%s/renew" % int(run_id), {}, "automation")


def bind(run_id, store_ns, project_key, session_id):
    return request("POST", "/runs/%s/bind" % int(run_id),
                   {"storeNs": store_ns, "projectKey": project_key,
                    "sessionId": session_id}, "automation")


def end_run(run_id, reason="completed"):
    return request("POST", "/runs/%s/end" % int(run_id),
                   {"reason": reason}, "automation")


def register(payload, principal="human"):
    return request("POST", "/tickets", payload, principal)


def transition(tid, to, note=None, pr=None, plan=None, branch=None,
               fence=None, principal="human"):
    body = {"to": to}
    for k, v in (("note", note), ("pr", pr), ("plan", plan),
                 ("branch", branch), ("fence", fence)):
        if v is not None:
            body[k] = v
    return request("POST", "/tickets/%s/transition" % int(tid), body, principal)


def comment(tid, kind="comment", text=None, body=None, principal="human"):
    payload = {"kind": kind}
    if text is not None:
        payload["text"] = text
    if body is not None:
        payload["body"] = body
    return request("POST", "/tickets/%s/comment" % int(tid), payload, principal)


def park_answer(tid, replies, to=None, correlation_id=None):
    body = {"replies": replies}
    if to is not None:
        body["to"] = to
    if correlation_id is not None:
        body["correlationId"] = correlation_id
    return request("POST", "/tickets/%s/park-answer" % int(tid), body, "human")


def tickets(state=None, category=None, principal="human"):
    qs = "&".join("%s=%s" % (k, v) for k, v in
                  (("state", state), ("category", category)) if v)
    return request("GET", "/tickets" + ("?" + qs if qs else ""),
                   principal=principal)


def timeline(tid, principal="human"):
    return request("GET", "/tickets/%s/timeline" % int(tid), principal=principal)


def queue_decisions():
    return request("GET", "/queue/decisions", principal="human")
```

Note on principals (Codex review F5): `token()` returns the env run token
FIRST whatever the principal argument — so the ticket-facing helpers
(`register`/`transition`/`comment`/`tickets`/`timeline`) default
`principal="human"`, which gives worker contexts the run principal
automatically and hand-run operator commands the human token instead of a
death. `"auto"` (die without a run token) remains for verbs that are
worker-only by contract. Sweep/dispatch call sites pass `"automation"`
explicitly. Add to the unit test (Step 2's file) an operator-context case —
no `BOARD_RUN_TOKEN` in env:

```bash
t "operator context falls back to human token" '"auth": "Bearer human-tok"' \
  bash -c "run_py() { PYTHONPATH='$SCRIPTS' BOARD_API_URL='http://127.0.0.1:$PORT' \
    BOARD_CREDENTIALS_FILE='\$1' python3 -c \"\$2\"; }; \
    run_py '$CREDS' 'import _board_api as A
A.comment(12, text=\"hello\")' >/dev/null 2>&1; grep comment '$FIX.log' | tail -1"
```

(plus a `POST /tickets/12/comment` fixture row; the implementer wires it into
the same fixtures file.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `bash tests/claude-code/board-api/test-client-core.sh`
Expected: `PASS test-client-core.sh`

- [ ] **Step 6: Commit**

```bash
git add skills/issue-tracker/scripts/_board_api.py tests/claude-code/board-api/
git commit -m "feat(a2): _board_api.py client core + fixture-driven mock server"
```

---

### Task 3: `board-comment.sh` (new verb, both modes) + protocol substitutions

**Files:**
- Create: `skills/issue-tracker/scripts/board-comment.sh`
- Modify: `skills/implementing/SKILL.md:82`, `skills/architecting/SKILL.md:56`, `skills/reviewing-prs/SKILL.md:277`
- Test: `tests/claude-code/board-api/test-comment.sh`

**Interfaces:**
- Consumes: `_lib.sh` binding env (Task 1), `_board_api.comment` (Task 2).
- Produces: `board-comment.sh <n> <text>` and `board-comment.sh <n> --kind <k> --json '<payload>'` — the ONLY comment vehicle worker protocols reference from here on.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-comment.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8472
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[{"method":"POST","path":"/tickets/12/comment","status":200,"body":{"eventId":77}}]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"

run_verb() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=run-tok "$SCRIPTS/board-comment.sh" "$@" ); }

t "plain comment posts kind=comment" "77" run_verb 12 "[gate] pass — one line"
t "kind=comment in request" '\"kind\": \"comment\"' cat "$FIX.log"
t "typed op carries body json" '\"closure-package\"' \
  bash -c "cd '$r' && BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=run-tok \
    '$SCRIPTS/board-comment.sh' 12 --kind closure-package --json '{\"evidence\":\"e\"}' >/dev/null; cat '$FIX.log'"
t "unknown kind refused client-side" "kind must be one of" \
  run_verb 12 --kind bogus --json '{}'
# gh mode: no server involved; assert it shells out to gh (stub gh on PATH)
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
r2="$(mkrepo)"
t "gh mode uses gh issue comment" "GH-CALLED issue comment" \
  bash -c "cd '$r2' && PATH='$gdir:$PATH' BOARD_REPO=o/r '$SCRIPTS/board-comment.sh' 12 'hello'"
finish
```

- [ ] **Step 2: Run to verify it fails** — `bash tests/claude-code/board-api/test-comment.sh` → FAIL (script absent).

- [ ] **Step 3: Implement `board-comment.sh`**

```bash
#!/usr/bin/env bash
# board-comment.sh — append a comment-family event to a ticket, either binding.
#
# Usage:
#   board-comment.sh <number> <text>                       # plain comment
#   board-comment.sh <number> --kind <k> --json '<payload>' [--text <text>]
#     k: parent-impact | closure-package | parent-impact-consumed
#
# gh mode: `gh issue comment` (typed kinds land as "[<kind>] <json>" marker
# comments — the sweep's IMPACT scan reads that convention). API mode:
# POST /tickets/:id/comment — the only carrier for the E2 typed event ops.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="${1#\#}"; shift
kind="comment" text="" json=""
if [ "${1:-}" != "--kind" ]; then text="$1"; shift
else
  while [ $# -gt 0 ]; do case "$1" in
    --kind) _need_arg "$1" "${2:-}"; kind="$2"; shift 2 ;;
    --json) _need_arg "$1" "${2:-}"; json="$2"; shift 2 ;;
    --text) _need_arg "$1" "${2:-}"; text="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac; done
fi
case "$kind" in
  comment|parent-impact|closure-package|parent-impact-consumed) ;;
  *) die "kind must be one of comment|parent-impact|closure-package|parent-impact-consumed" ;;
esac

if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_KIND="$kind" T_TEXT="$text" T_JSON="$json" _api_py - <<'PY'
import json, os
import _board_api as A
env = os.environ
body = json.loads(env["T_JSON"]) if env["T_JSON"] else None
out = A.comment(env["T_ID"], kind=env["T_KIND"],
                text=env["T_TEXT"] or None, body=body)
print(out["eventId"])
PY
else
  if [ "$kind" = comment ]; then
    gh issue comment "$tid" -R "$BOARD_REPO" --body "$text"
  else
    gh issue comment "$tid" -R "$BOARD_REPO" --body "[$kind] ${text:+$text }${json}"
  fi
fi
_rerender_if_serving
```

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-comment.sh` → `PASS`.

- [ ] **Step 5: Substitute the three raw call sites** (exact edits)

`skills/implementing/SKILL.md:82` — replace

```
gh issue comment {{ISSUE_NUMBER}} --body "[gate] pass — {{ENGINE_NAME}}/<mode>: <one line>"
```

with

```
{{BOARD_SCRIPTS}}/board-comment.sh {{ISSUE_NUMBER}} "[gate] pass — {{ENGINE_NAME}}/<mode>: <one line>"
```

`skills/architecting/SKILL.md:56` — replace

```
  gh issue comment {{ISSUE_NUMBER}} --body "[gate] pass — architect: <one line>"
```

with

```
  {{BOARD_SCRIPTS}}/board-comment.sh {{ISSUE_NUMBER}} "[gate] pass — architect: <one line>"
```

`skills/reviewing-prs/SKILL.md:277` — replace the parenthetical
`(gh issue comment {{TECH_DEBT_ISSUE}})` with
`({{BOARD_SCRIPTS}}/board-comment.sh {{TECH_DEBT_ISSUE}})`.

(`{{BOARD_SCRIPTS}}` is already a bootstrap-substituted placeholder in all
three protocols — verify with `grep -n BOARD_SCRIPTS` in each file; if a file
renders it under a different name, use that file's existing placeholder.)

Then sweep for stragglers (Codex review F3): `grep -rn "gh issue comment" skills/*/SKILL.md skills/*/references/*.md`
— every WORKER-executed hit (the spike protocol's findings/gate comments
included) gets the same `board-comment.sh` substitution; dispatcher- or
human-context hits (wake-ritual prose, `gh issue view --comments` guidance)
are left for Task 14's read-scope audit to classify.

- [ ] **Step 6: Run the full existing suite** — `tests/claude-code/run-skill-tests.sh` → same pass set (protocol text changes must not break bootstrap render tests).

- [ ] **Step 7: Commit**

```bash
git add skills/issue-tracker/scripts/board-comment.sh tests/claude-code/board-api/test-comment.sh \
  skills/implementing/SKILL.md skills/architecting/SKILL.md skills/reviewing-prs/SKILL.md
git commit -m "feat(a2): board-comment verb (both modes); protocols drop raw gh issue comment"
```

---

### Task 4: register + transition + fail-loud verbs, API branches

**Files:**
- Modify: `skills/issue-tracker/scripts/board-register.sh` (branch after option parsing, line ~52), `board-transition.sh` (branch after arg parsing, before the `_py` block at line 47), `board-edge.sh`, `board-priority.sh`, `board-relate.sh`, `board-migrate-gh.sh` (guard at top of each, right after sourcing `_lib.sh`)
- Test: `tests/claude-code/board-api/test-register-transition.sh`

**Interfaces:**
- Consumes: `_board_api.register/transition` (Task 2), binding env (Task 1).
- Produces: unchanged CLIs. Register prints `<id> <BOARD_API_URL>/tickets/<id>` in API mode (keeps the `<number> <url>` output contract callers parse). Transition prints `#<n>: → <server-returned to>` plus `(converged)` when flagged.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-register-transition.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8473
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/tickets/9/transition","status":200,
  "body":{"ok":true,"to":"needs-human","converged":true},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":31,"state":"needs-human"},"once":true},
 {"method":"POST","path":"/tickets","status":409,
  "body":{"error":"illegal-birth","message":"spike may not be born ready-for-architect"},"once":true},
 {"method":"POST","path":"/tickets","status":200,"body":{"id":30,"state":"ready-for-implementer"}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
V() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=rt "$SCRIPTS/$1" "${@:2}" ); }

t "transition prints SERVER to, not requested" "→ needs-human (converged)" \
  V board-transition.sh 9 in-review "note here"
t "fence rides env" '\"fence\": 3' \
  bash -c "cd '$r' && BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=rt BOARD_RUN_FENCE=3 \
    '$SCRIPTS/board-transition.sh' 9 done 2>/dev/null; cat '$FIX.log'"
t "park birth note prepends body" '\"body\": \"which color?' \
  bash -c "V board-register.sh 'pick color' enhancement P2 --state needs-human --note 'which color?' >/dev/null; cat '$FIX.log'"
t "spike->architect surfaces 409 + arkho#7" "illegal-birth" \
  V board-register.sh "probe x" spike P2 --state ready-for-architect --body-file /dev/null
t "category maps bug->work" '\"category\": \"work\"' \
  bash -c "V board-register.sh 'a bug' bug P1 >/dev/null; cat '$FIX.log'"
t "register prints id + url" "30 http://127.0.0.1:$PORT/tickets/30" \
  V board-register.sh "plain one" enhancement P2
for verb in board-edge.sh board-priority.sh board-relate.sh board-migrate-gh.sh; do
  t "$verb fails loud naming arkho#7" "arkho#7" V "$verb" 1 --block 2
done
finish
```

- [ ] **Step 2: Run to verify it fails** — all API-branch asserts FAIL (scripts go down their gh paths / die on gh).

- [ ] **Step 3: Implement**

**3a. Fail-loud guard** — insert immediately after `. "$SCRIPT_DIR/_lib.sh"` in
`board-edge.sh`, `board-priority.sh`, `board-relate.sh`, `board-migrate-gh.sh`:

```bash
[ "$BOARD_BINDING" != api ] || die "this verb has no API-mode counterpart yet — \
edge re-cut/priority/relates/body edits are A1 follow-up routes, tracked as arkho#7 \
(https://github.com/SSFSKIM/arkho/issues/7); until it lands, run these against a gh-bound repo only"
```

**3b. `board-register.sh`** — insert after the option-parsing loop (after line 51, before the `T_TITLE=…` heredoc), the whole API branch; the gh path stays as the `else` body (wrap the existing heredoc block):

```bash
if [ "$BOARD_BINDING" = api ]; then
  T_TITLE="$title" T_CATEGORY="$category" T_PRIORITY="$priority" T_STATE="$state" \
  T_STATE_EXPLICIT="$state_explicit" T_NOTE="$note" T_PARENT="$parent" \
  T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" T_BODY_FILE="$body_file" _api_py - <<'PY'
import os
import _board_api as A
env = os.environ
title = " ".join(env["T_TITLE"].split())
CATEGORY_MAP = {"bug": "work", "enhancement": "work",
                "spike": "spike", "env-issue": "env-issue"}
if env["T_CATEGORY"] not in CATEGORY_MAP:
    A.die("category must be %s" % "|".join(CATEGORY_MAP))
body = open(env["T_BODY_FILE"]).read() if env["T_BODY_FILE"] else ""
note = env["T_NOTE"]
state = env["T_STATE"]
if note and state in ("needs-human", "needs-info", "interactive-preferred"):
    # No API note field for the birth question (arkho#7): body head carries it.
    body = note + ("\n\n" + body if body else "")
payload = {"title": title, "category": CATEGORY_MAP[env["T_CATEGORY"]],
           "priority": env["T_PRIORITY"]}
if env["T_STATE_EXPLICIT"] == "1":
    payload["birth"] = state
if body:
    payload["body"] = body
if env["T_PARENT"]:
    payload["parent"] = int(env["T_PARENT"].lstrip("#"))
if env["T_SPAWNED"]:
    payload["spawnedBy"] = int(env["T_SPAWNED"].lstrip("#"))
if env["T_BLOCKED"]:
    payload["blockedBy"] = [int(b.lstrip("#")) for b in env["T_BLOCKED"].split(",") if b]
try:
    out = A.register(payload)
except SystemExit:
    # A spike birth into ready-for-architect is a known canon divergence:
    # the server's 409 illegal-birth already printed; add the pointer.
    if env["T_CATEGORY"] == "spike" and state == "ready-for-architect":
        print("note: design-first spikes are gh-only until the arkho#7 ruling "
              "(https://github.com/SSFSKIM/arkho/issues/7)", flush=True)
    raise
print("%s %s/tickets/%s" % (out["id"], os.environ["BOARD_API_URL"], out["id"]))
PY
  _rerender_if_serving
  exit 0
fi
```

(Birth default: an *implicit* state stays server-side — the payload omits
`birth`, so the server applies its own default + env-issue inversion. The
client-side env-issue/note refusals in the gh path do not run in API mode; the
server's `repair-path-required` etc. answer instead. `--note` on non-park
births is ignored in API mode with the server's classification intact.)

**3c. `board-transition.sh`** — after arg parsing (before line 47's `_py` heredoc):

```bash
if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" T_PLAN="$plan" _api_py - <<'PY'
import os
import _board_api as A
env = os.environ
fence = os.environ.get("BOARD_RUN_FENCE") or None
out = A.transition(env["T_ID"].lstrip("#"), env["T_TO"],
                   note=env["T_NOTE"] or None, pr=env["T_PR"] or None,
                   plan=env["T_PLAN"] or None, branch=env["T_BRANCH"] or None,
                   fence=int(fence) if fence else None)
# Print the state the server WROTE — convergence can transmute the target.
suffix = " (converged)" if out.get("converged") else ""
print("#%s: → %s%s" % (env["T_ID"].lstrip("#"), out["to"], suffix))
PY
  _rerender_if_serving
  exit 0
fi
```

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-register-transition.sh` → `PASS`. Then `tests/claude-code/run-skill-tests.sh` → unchanged pass set.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-register.sh skills/issue-tracker/scripts/board-transition.sh \
  skills/issue-tracker/scripts/board-edge.sh skills/issue-tracker/scripts/board-priority.sh \
  skills/issue-tracker/scripts/board-relate.sh skills/issue-tracker/scripts/board-migrate-gh.sh \
  tests/claude-code/board-api/test-register-transition.sh
git commit -m "feat(a2): register/transition API branches; orphaned human verbs fail loud naming arkho#7"
```

---

### Task 5: read verbs — list / show / reconcile / lint / map

**Files:**
- Modify: `board-list.sh`, `board-show.sh`, `board-reconcile.sh`, `board-lint.sh`, `board-map.sh` (API branch each, after `_lib.sh`)
- Test: `tests/claude-code/board-api/test-read-verbs.sh`

**Interfaces:**
- Consumes: `_board_api.tickets/timeline/queue_decisions/needing_resume` (Task 2).
- Produces: `board-list.sh` API-mode row format `#<id> <state> <priority> <title>` (server order, marked informational in the header line `# dispatch order is server-owned in API mode`); `board-show.sh` prints the ticket row + its timeline records one per line `[<source>:<cursor>] <kind> <note-or-empty>`; `board-map.sh --write` renders the same `BOARD.html`/`BOARD.md` from an API snapshot.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-read-verbs.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8474
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/tickets/12/timeline","status":200,
  "body":{"records":[{"source":"board","cursor":"5","observedAt":"t","sourceTime":null,
    "runId":1,"kind":"transition","body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}}]}},
 {"method":"GET","path":"/tickets","status":200,
  "body":[{"id":12,"title":"T one","category":"work","state":"in-progress",
           "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null}]},
 {"method":"GET","path":"/queue/decisions","status":200,
  "body":[{"correlation_id":"evt-9","ticket_id":12,"run_id":41,"species":"board",
           "question":{"note":"pick one"},"raised_at":"t","state":"needs-human","category":"work"}]},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
V() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }

t "list renders server rows" "#12 in-progress P1 T one" V board-list.sh
t "show prints timeline record" "[board:5] transition n1" V board-show.sh 12
t "reconcile shows wake queue" "pick one" V board-reconcile.sh
t "map --write renders BOARD.md" "T one" \
  bash -c "V board-map.sh --write >/dev/null; cat '$r/doperpowers/issue-tracker/BOARD.md'"
t "lint API mode reports thin scope" "server-enforced" V board-lint.sh
finish
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — each verb gets a branch after `_lib.sh`:

`board-list.sh`:

```bash
if [ "$BOARD_BINDING" = api ]; then
  T_STATE="${1:-}" _api_py - <<'PY'
import os
import _board_api as A
rows = A.tickets(state=os.environ["T_STATE"] or None, principal="automation")
print("# dispatch order is server-owned in API mode")
for t in rows:
    print("#%s %s %s %s" % (t["id"], t["state"], t.get("priority") or "-", t["title"]))
PY
  exit 0
fi
```

`board-show.sh`:

```bash
if [ "$BOARD_BINDING" = api ]; then
  T_ID="${1:?usage: board-show.sh <n>}" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_ID"].lstrip("#")
for t in A.tickets(principal="automation"):
    if str(t["id"]) == tid:
        print("#%s %s %s %s  owner_run=%s plan=%s pr=%s" %
              (t["id"], t["state"], t.get("priority") or "-", t["title"],
               t.get("owner_run"), t.get("plan"), t.get("pr_url")))
        break
else:
    A.die("no ticket #%s" % tid)
for r in A.timeline(tid, principal="automation")["records"]:
    note = (r.get("body") or {}).get("note") or ""
    print("[%s:%s] %s %s" % (r["source"], r["cursor"], r["kind"], note))
PY
  exit 0
fi
```

`board-reconcile.sh`:

```bash
if [ "$BOARD_BINDING" = api ]; then
  _api_py - <<'PY'
import _board_api as A
print("== wake queue (standing parks) ==")
for q in A.queue_decisions():
    print("#%s [%s] %s" % (q["ticket_id"], q["state"], (q.get("question") or {}).get("note") or ""))
print("== needing resume ==")
for e in A.needing_resume():
    print("#%s %s (predecessor run %s)" % (e["ticketId"], e["state"], e["predecessorRunId"]))
print("== dispatchables ==")
for t in A.tickets(principal="automation"):
    if t["state"] in ("ready-for-architect", "ready-for-implementer") and not t.get("owner_run"):
        print("#%s %s %s %s" % (t["id"], t["state"], t.get("priority") or "-", t["title"]))
PY
  exit 0
fi
```

`board-lint.sh` — API mode checks only local drift (server owns its schema):

```bash
if [ "$BOARD_BINDING" = api ]; then
  echo "# board schema is server-enforced in API mode; checking local registry drift only"
  T_DHOME="$DAEMON_HOME" _api_py - <<'PY'
import glob, json, os
import _board_api as A
open_ids = {t["id"] for t in A.tickets(principal="automation")
            if t["state"] not in ("done", "wontfix")}
owned = {t["id"]: t.get("owner_run") for t in A.tickets(principal="automation")}
fails = 0
for p in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    tid = str(m.get("ticket", "")).lstrip("#")
    if not tid or not m.get("run_id"): continue
    if int(tid) not in open_ids:
        print("FAIL daemon %s bound to closed/absent ticket #%s FIX: daemon-retire" % (m.get("uuid","?")[:8], tid)); fails += 1
raise SystemExit(1 if fails else 0)
PY
  exit $?
fi
```

`board-map.sh` — inside its snapshot-building step, branch the data source: in
API mode build the same normalized structure the renderer consumes from
`A.tickets(principal="automation")` (fields: id, title, state, priority,
parent, plan, pr_url; edges: parent only — `blocked-by` edges are not exposed
by `GET /tickets` v1, so the DAG renders parent edges and the table notes
`blocked-by: (not exposed by API v1)`). Reuse the existing template-write code
path unchanged; BOARD.md rows come from the same rows as board-list.

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-read-verbs.sh` → `PASS`; full suite unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-{list,show,reconcile,lint,map}.sh \
  tests/claude-code/board-api/test-read-verbs.sh
git commit -m "feat(a2): read verbs speak the API — list/show/reconcile/lint/map"
```

---

### Task 6: `board-bind.sh` locator + registry run fields

**Files:**
- Modify: `skills/issue-tracker/scripts/board-bind.sh`
- Test: `tests/claude-code/board-api/test-bind.sh`

**Interfaces:**
- Consumes: `_board_api.bind` (Task 2); daemon registry meta JSON at `$DAEMON_HOME/<name>.json` (existing shape + Task's new fields).
- Produces: API mode `board-bind.sh <uuid> <n>` additionally requires `BOARD_RUN_ID` in env (the dispatcher exports it); writes `run_id`, `fence` (from `BOARD_RUN_FENCE`), `bind_confirmed: true` into the registry meta after a `POST /runs/:id/bind` with locator `{storeNs: "local:<hostname>", projectKey: <basename BOARD_ROOT>, sessionId: <uuid>}`.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-bind.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8475
FIX="$(mktemp)"; : > "$FIX.log"
printf '[{"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}}]' > "$FIX"
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
DH="$(mktemp -d)"
printf '{"uuid":"u-1234","name":"w","status":"working"}' > "$DH/w.json"

( cd "$r" && DAEMON_HOME="$DH" BOARD_CREDENTIALS_FILE="$CREDS" \
  BOARD_RUN_ID=41 BOARD_RUN_FENCE=3 BOARD_RUN_TOKEN=tok-w "$SCRIPTS/board-bind.sh" u-1234 12 )
t "bind hits the API with locator" '\"storeNs\": \"local:' cat "$FIX.log"
t "registry meta gains run fields" '"run_id": 41' cat "$DH/w.json"
t "bind_confirmed recorded" '"bind_confirmed": true' cat "$DH/w.json"
finish
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — in `board-bind.sh`, after the existing registry-meta
update logic (keep it — both modes record ticket/uuid), append:

```bash
if [ "$BOARD_BINDING" = api ]; then
  [ -n "${BOARD_RUN_ID:-}" ] || die "API mode bind needs BOARD_RUN_ID in env (the dispatcher exports it)"
  T_UUID="$uuid" T_RUN="$BOARD_RUN_ID" T_FENCE="${BOARD_RUN_FENCE:-}" \
  T_DHOME="$DAEMON_HOME" _api_py - <<'PY'
import glob, json, os, socket
import _board_api as A
env = os.environ
A.bind(env["T_RUN"], "local:" + socket.gethostname(),
       os.path.basename(os.environ.get("BOARD_ROOT") or os.getcwd()),
       env["T_UUID"])
for p in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    if m.get("uuid") == env["T_UUID"]:
        m["run_id"] = int(env["T_RUN"])
        if env["T_FENCE"]: m["fence"] = int(env["T_FENCE"])
        if os.environ.get("BOARD_RUN_TOKEN"):
            # Bearer at rest for resume rehydration (Codex review F2):
            # daemon-resume forks a fresh process from the CALLER's env, so
            # every later resume (relay, successor, inline) re-injects
            # BOARD_RUN_* from this meta. Local plaintext, 0600 — same
            # posture as the session transcripts beside it.
            m["run_bearer"] = os.environ["BOARD_RUN_TOKEN"]
        m["bind_confirmed"] = True
        json.dump(m, open(p, "w"), indent=1)
        os.chmod(p, 0o600)
        break
PY
fi
```

Add to the test: the spawn env includes `BOARD_RUN_TOKEN=tok-w`; assert
`'"run_bearer": "tok-w"'` lands in the meta and the file mode is 600
(`stat -f %Lp` on darwin / `stat -c %a` on linux — the helper picks by
`uname`).

Also export `BOARD_ROOT` from `_lib.sh` (one line: `export BOARD_ROOT` after it
is computed) so the heredoc above can read it.

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-bind.sh` → `PASS`.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-bind.sh skills/issue-tracker/scripts/_lib.sh \
  tests/claude-code/board-api/test-bind.sh
git commit -m "feat(a2): board-bind posts the session locator and records run fields"
```

---

### Task 7: claim-based dispatch in `implement-dispatch.sh`

**Files:**
- Modify: `skills/implementing/scripts/implement-dispatch.sh` (new API top-level branch: `--sweep` and `<n>` both route to `dispatch_api` when `BOARD_BINDING=api`)
- Modify: `skills/implementing/references/worker-bootstrap.md` (API-mode block)
- Test: `tests/claude-code/board-api/test-dispatch-claim.sh`

**Interfaces:**
- Consumes: `_board_api.claim/end_run` (Task 2), `board-bind.sh` (Task 6), daemon-spawn (stubbed in tests via `DAEMON_SCRIPTS`).
- Produces: claim journal `$DAEMON_HOME/board-claims/<nonce>.json` `{"lane","run_id","spawn_completed"}`; worker env injection `BOARD_RUN_TOKEN/BOARD_RUN_ID/BOARD_RUN_FENCE/BOARD_API_URL` via `DAEMON_EXTRA_ENV` (daemon-spawn already forwards `DAEMON_*`-prefixed env; if not, pass via the spawn wrapper the test stubs — the implementer verifies `daemon-spawn.sh`'s env forwarding and uses its existing mechanism, adding one if absent as part of this task); assignment body written to `$DAEMON_HOME/board-claims/<nonce>.body.md` and its path substituted into the bootstrap.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-dispatch-claim.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8476
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/claim","status":200,"once":true,
  "body":{"runId":41,"ticketId":12,"fence":3,"bearer":"tok-w","plan":null,
          "body":"# assignment\nbuild it","parentPin":null}},
 {"method":"POST","path":"/runs/claim","status":200,"body":{"claimed":false}},
 {"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
DH="$(mktemp -d)"
DS="$(mktemp -d)"   # stub daemon-spawn: records its env + args, prints a uuid line
cat > "$DS/daemon-spawn.sh" <<'EOF'
#!/usr/bin/env bash
{ echo "ARGS $*"; env | grep '^BOARD_' | sort; } > "$DAEMON_HOME/spawn-capture.txt"
echo "uuid: stub-uuid-1"
EOF
chmod +x "$DS/daemon-spawn.sh"

( cd "$r" && DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" LOCAL_REPO="$r" \
  BOARD_CREDENTIALS_FILE="$CREDS" IMPLEMENT_MAX_CONCURRENT=5 \
  "$REPO_ROOT/skills/implementing/scripts/implement-dispatch.sh" --sweep )

t "worker got run creds in env" "BOARD_RUN_TOKEN=tok-w" cat "$DH/spawn-capture.txt"
t "fence exported" "BOARD_RUN_FENCE=3" cat "$DH/spawn-capture.txt"
t "claim journal spawn_completed" '"spawn_completed": true' \
  bash -c "cat '$DH'/board-claims/*.json | head -1"
t "assignment body written" "build it" bash -c "cat '$DH'/board-claims/*.body.md"
t "empty lanes stop claiming" '"claimed": false' cat "$FIX.log"
finish
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `dispatch_api`** — add to `implement-dispatch.sh` before
its mode dispatch at line ~411, and route both entry modes to it when
`BOARD_BINDING=api` (the `<n>` triggered form claims once per invocation; a
number argument is advisory in API mode — the server picks):

```bash
# ---- API-mode dispatch: claim-based, lane-disciplined (spec § four-phase) ---
# EARLY BINDING BOOTSTRAP (Codex review F3): source _binding.sh at the TOP of
# implement-dispatch.sh — immediately after SCRIPT_DIR/SKILL_DIR are computed
# and BEFORE any gh probe or gh-derived env resolution — and route to the API
# path right there:
#     . "$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)/_binding.sh"
#     if [ "$BOARD_BINDING" = api ]; then
#       # (the dispatch_api definitions below are loaded; then:)
#       case "${1:-}" in
#         --sweep) dispatch_api; exit 0 ;;
#         ''|--*)  die "usage: implement-dispatch.sh <issue-number> | --sweep" ;;
#         *) die "API-mode dispatch is claim-based — the server owns pick order, \
# and the contract has no claim-by-ticket route; use --sweep. Targeted claim is \
# a flow-back candidate recorded on arkho#7 (spec Revision Notes v1.2)." ;;
#       esac
#     fi
# The gh-mode body (including its `command -v gh` checks) runs only below this
# branch. Same pattern in review-dispatch.sh (Task 8).
_api_registry_count() {  # open bound workers by lane-set, from registry metas
  T_DHOME="$DAEMON_HOME" T_LANES="$1" python3 - <<'PY'
import glob, json, os
lanes = set(os.environ["T_LANES"].split(","))
n = 0
for p in glob.glob(os.path.join(os.environ["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    if m.get("lane") in lanes and m.get("status") in ("working", "blocked", "idle"):
        n += 1
print(n)
PY
}

_claim_one() {  # _claim_one <lane> <lane_cap> — claims + spawns one worker; rc 1 = lane empty
  local lane="$1" cap="$2" nonce claims_dir="$DAEMON_HOME/board-claims"
  mkdir -p "$claims_dir"
  nonce="$(uuidgen)"
  printf '{"lane": "%s", "run_id": null, "spawn_completed": false}\n' "$lane" > "$claims_dir/$nonce.json"
  local resp
  resp="$(T_LANE="$lane" T_NONCE="$nonce" T_CAP="$cap" _api_py - <<'PY'
import json, os
import _board_api as A
out = A.claim(os.environ["T_LANE"], os.environ["T_NONCE"],
              lane_cap=int(os.environ["T_CAP"]))
print(json.dumps(out))
PY
)"
  if [ "$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("claimed", True))')" = "False" ]; then
    rm -f "$claims_dir/$nonce.json"; return 1
  fi
  local run_id ticket fence bearer body_file
  run_id="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])')"
  ticket="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticketId"])')"
  fence="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["fence"])')"
  bearer="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["bearer"])')"
  body_file="$claims_dir/$nonce.body.md"
  printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("body") or "")' > "$body_file"
  printf '{"lane": "%s", "run_id": %s, "spawn_completed": false}\n' "$lane" "$run_id" > "$claims_dir/$nonce.json"

  local role protocol name prompt
  case "$lane" in
    architect) role=ARCHITECT protocol="$ARCHITECT_PROTOCOL" ;;
    spike)     role=SPIKE     protocol="$SPIKE_PROTOCOL" ;;
    *)         role=IMPLEMENT protocol="$IMPLEMENT_PROTOCOL" ;;
  esac
  name="$ticket-api-$lane"
  prompt="$(render_bootstrap_api "$ticket" "$role" "$protocol" "$body_file")"
  local uuid spawn_out
  spawn_out="$(BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run_id" BOARD_RUN_FENCE="$fence" \
          BOARD_API_URL="$BOARD_API_URL" \
          "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
          "$([ "$lane" = architect ] && echo "${ARCHITECT_MODEL:-fable}" || echo "${IMPLEMENT_MODEL:-opus}")")"
  # UUID extraction (Codex review F4): daemon-spawn does NOT print "uuid: …" —
  # extract it EXACTLY the way this script's gh-mode body already does (see the
  # spawn block around implement-dispatch.sh:348-370 and reuse that parsing
  # verbatim; if it resolves via the registry rather than stdout, do the same
  # here). The test stub must then emit the REAL daemon-spawn output format —
  # copy a genuine `daemon-spawn.sh --no-wait` output line into the stub.
  uuid="$(extract_spawn_uuid <<<"$spawn_out")"   # the helper the gh path uses / this task factors out
  [ -n "$uuid" ] || die "could not extract uuid from daemon-spawn output for #$ticket: $spawn_out"
  printf '{"lane": "%s", "run_id": %s, "spawn_completed": true}\n' "$lane" "$run_id" > "$claims_dir/$nonce.json"
  BOARD_RUN_ID="$run_id" BOARD_RUN_FENCE="$fence" "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$ticket"
  # stamp lane into the registry meta for cap-counting and the answer relay
  T_UUID="$uuid" T_LANE="$lane" T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    if m.get("uuid") == os.environ["T_UUID"]:
        m["lane"] = os.environ["T_LANE"]; json.dump(m, open(p, "w"), indent=1); break
PY
  echo "claimed #$ticket run=$run_id lane=$lane → $uuid"
}

_reconcile_claims() {  # startup pass (Codex review F4): finish or release
  local f                # journals a crash left with spawn_completed=false
  for f in "$DAEMON_HOME"/board-claims/*.json; do
    [ -e "$f" ] || continue
    local done run_id nonce lane
    done="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["spawn_completed"])' "$f")"
    [ "$done" = "False" ] || continue
    nonce="$(basename "$f" .json)"
    run_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("run_id") or "")' "$f")"
    if [ -n "$run_id" ] && _registry_has_run "$run_id"; then
      # spawn actually completed, only the marker write was lost — repair it
      python3 -c 'import json,sys; p=sys.argv[1]; m=json.load(open(p)); m["spawn_completed"]=True; json.dump(m, open(p,"w"))' "$f"
    elif [ -n "$run_id" ]; then
      # claimed but never handed off: the lease would strand until reclaim —
      # end the run now and drop the journal (never replay: the response was
      # received, so a replay would rotate nothing useful)
      T_RUN="$run_id" _api_py - <<'PY' || true
import os
import _board_api as A
try: A.end_run(os.environ["T_RUN"], "abandoned")
except A.RunEnded: pass
PY
      rm -f "$f" "${f%.json}.body.md"
    else
      # nonce persisted, response lost: replay recovers the claim (pre-spawn
      # replay is the ONLY legal replay); route it through _claim_one's spawn
      lane="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["lane"])' "$f")"
      rm -f "$f"
      _claim_one_with_nonce "$lane" "$nonce" || true
    fi
  done
}

# _claim_one is factored as _claim_one_with_nonce "$lane" "$(uuidgen)" so the
# reconciliation replay path and the fresh path share one body.
_registry_has_run() { _registry_metas 2>/dev/null | awk -F'\t' -v r="$1" '$2 == r {found=1} END {exit !found}'; }

dispatch_api() {
  mkdir -p "$DAEMON_HOME/board-claims"
  _reconcile_claims
  local impl_cap="${IMPLEMENT_MAX_CONCURRENT:-5}" arch_cap="${ARCHITECT_MAX_CONCURRENT:-1}"
  # local cap first (registry), server laneCap as belt — spec § tick phase 4
  while [ "$(_api_registry_count architect)" -lt "$arch_cap" ]; do
    _claim_one architect "$arch_cap" || break
  done
  while [ "$(_api_registry_count implementer,spike)" -lt "$impl_cap" ]; do
    _claim_one implementer "$impl_cap" || _claim_one spike "$impl_cap" || break
  done
}
```

(`_registry_metas` here is the same helper Task 9 defines for `_sweep_api.sh`
— this script defines its own copy; the two-line duplication beats a shared
lib neither script has today.)

`render_bootstrap_api` renders the SAME bootstrap template with API-mode
substitutions: `{{ISSUE_NUMBER}}` → the ticket id, `{{ISSUE_URL}}` →
`$BOARD_API_URL/tickets/<id>`, and the template's "read your own ticket" line
resolved by the new block added to `worker-bootstrap.md`:

```markdown
<!-- API binding: the dispatcher substitutes this block in place of the
     gh-mode ticket-read instruction. -->
Your assignment (the ticket body, delivered by the claim that dispatched you)
is pinned at: {{TICKET_BODY_FILE}} — read it first; it is your statement of
work. Your board credentials are already in this session's environment; the
board scripts use them automatically. Your board reads reach your own ticket
and its direct children only.
```

Routing lives at the TOP of the script (the early-bootstrap comment block at
the head of this step): binding resolved before any gh probe, `--sweep` →
`dispatch_api`, a bare `<n>` → fail loud naming the arkho#7-recorded gap.
`ARCHITECT_PROTOCOL` is the existing architecting SKILL.md path variable — if
the script names it differently, reuse its name.

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-dispatch-claim.sh` → `PASS`; full suite unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/implementing/scripts/implement-dispatch.sh \
  skills/implementing/references/worker-bootstrap.md \
  tests/claude-code/board-api/test-dispatch-claim.sh
git commit -m "feat(a2): claim-based API dispatch — nonce journal, env injection, spawn-completed marker"
```

---

### Task 8: `review-dispatch.sh` qagent claims

**Files:**
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh` (API branch, same pattern as Task 7)
- Test: `tests/claude-code/board-api/test-review-dispatch.sh`

**Interfaces:**
- Consumes: Task 7's `_claim_one` pattern (replicated with lane `qagent`; review-dispatch has its own bootstrap/protocol variables — reuse them).
- Produces: qagent claims with `REVIEW_MAX_CONCURRENT` (existing knob; if the script's cap variable is named differently, use its name) as both local cap and `laneCap`.

- [ ] **Step 1: Write the failing test** — copy `test-dispatch-claim.sh` mutatis mutandis:
fixture claims lane `qagent` once (`{"runId":51,"ticketId":9,"fence":2,"bearer":"tok-q","plan":null,"body":"review it","parentPin":null}`, then `{"claimed":false}`; plus `/runs/51/bind`); stub `daemon-spawn.sh` the same way; invoke `review-dispatch.sh --sweep` from the API-bound repo; assert `BOARD_RUN_TOKEN=tok-q` in the spawn capture and `"lane": "qagent"` in the claim journal.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — port Task 7's `_api_registry_count`/`_claim_one`/`dispatch_api` trio into `review-dispatch.sh` with: lane fixed to `qagent`, cap from the script's existing review cap knob, role/protocol from its existing review-worker bootstrap variables, and the same claim-journal + bind + lane-stamp steps. Route `[ "$BOARD_BINDING" = api ] && { dispatch_api; exit 0; }` before its gh-mode body. (The duplication with Task 7 is deliberate — the two scripts have no shared lib today; extracting one is out of scope.)

- [ ] **Step 4: Run tests** — new test `PASS`; full suite unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/reviewing-prs/scripts/review-dispatch.sh tests/claude-code/board-api/test-review-dispatch.sh
git commit -m "feat(a2): review-dispatch claims the qagent lane in API mode"
```

---

### Task 9: `_sweep_api.sh` — phases 1+2 (renew + bind-repair, sentinel relay)

**Files:**
- Create: `skills/issue-tracker/scripts/_sweep_api.sh`
- Modify: `skills/issue-tracker/scripts/board-sweep.sh` (top: `[ "$BOARD_BINDING" = api ] && exec "$SCRIPT_DIR/_sweep_api.sh"`)
- Test: `tests/claude-code/board-api/test-sweep-renew-relay.sh`

**Interfaces:**
- Consumes: `_board_api.renew/unrelayed/ack/RunEnded/SENTINEL` (Task 2), registry metas with `run_id`/`bind_confirmed`/`lane` (Tasks 6-7), `daemon-resume.sh` (stubbed in tests).
- Produces: `_sweep_api.sh` runs phases in order and is also invokable per phase: `_sweep_api.sh renew|relay|resume|dispatch|all` (default `all`). Phase functions `phase_renew`, `phase_relay` here; `phase_resume`, `phase_dispatch` in Task 10. Relay prompt builder `_relay_prompt <answer_id> <replies_text>` producing EXACTLY:

```
[board-relay answer:<id>] Your needs-human park on this ticket was answered by
the human. Re-state your gate verdict against the answers in ONE paragraph as
a ticket comment ("[gate] re-pass — <one line>" — PLAN-EXECUTION, which ran no
gate, restates plan-execution status instead), or park fresh if the answers
reshape the work's scope, then proceed under your original protocol. Never
build on momentum past an answer that changed the work's shape.

---- answers (verbatim) ----
<replies_text>
```

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-sweep-renew-relay.sh`:

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"
PORT=8477
FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/41/renew","status":200,"body":{"renewed":true}},
 {"method":"POST","path":"/runs/40/renew","status":409,"body":{"error":"run-ended","message":"reaped"}},
 {"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}},
 {"method":"GET","path":"/answers/unrelayed","status":200,"once":true,
  "body":[{"answerEventId":118,"ticketId":12,"correlationId":"evt-101","replies":["ship it"]}]},
 {"method":"GET","path":"/answers/unrelayed","status":200,"body":[]},
 {"method":"POST","path":"/answers/118/ack","status":200,"body":{"acked":true}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" $PORT & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 0.3
CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
DH="$(mktemp -d)"; DS="$(mktemp -d)"
# alive worker on run 41, unconfirmed bind; dead one on run 40; bound session for ticket 12
TRANSCRIPT="$DH/sess-12.jsonl"; : > "$TRANSCRIPT"
cat > "$DH/w1.json" <<EOF
{"uuid":"u-1","status":"working","run_id":41,"fence":3,"lane":"implementer","bind_confirmed":false,"ticket":"7","transcript":"$TRANSCRIPT"}
EOF
cat > "$DH/w2.json" <<EOF
{"uuid":"u-2","status":"working","run_id":40,"fence":2,"lane":"implementer","bind_confirmed":true,"ticket":"8"}
EOF
cat > "$DH/w3.json" <<EOF
{"uuid":"u-3","status":"idle","run_id":43,"fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"12","transcript":"$TRANSCRIPT"}
EOF
cat > "$DS/daemon-resume.sh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$2" >> "$TRANSCRIPT"   # delivery IS the transcript write
EOF
chmod +x "$DS/daemon-resume.sh"
# stub daemon liveness: w1/w3 alive, w2 dead
cat > "$DS/daemon-finalize.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in u-2) echo absent ;; *) echo live ;; esac
EOF
chmod +x "$DS/daemon-finalize.sh"

SW() { ( cd "$r" && DAEMON_HOME="$DH" DAEMON_SCRIPTS="$DS" BOARD_CREDENTIALS_FILE="$CREDS" \
  "$SCRIPTS/_sweep_api.sh" "$1" ); }

SW renew
t "alive run renewed" "POST\", \"path\": \"/runs/41/renew" cat "$FIX.log"
t "unconfirmed bind repaired" "/runs/41/bind" cat "$FIX.log"
t "run-ended routes to resume, not error" "run 40: ended (reaped) — resume path" SW renew
SW relay
t "relay delivered with sentinel" "[board-relay answer:118]" cat "$TRANSCRIPT"
t "answer acked after delivery" "/answers/118/ack" cat "$FIX.log"
# idempotence: sentinel already in transcript -> second relay call acks without resuming
cp "$FIX" "$FIX.2"; : > "$FIX.log"
before=$(grep -c "board-relay" "$TRANSCRIPT")
SW relay
after=$(grep -c "board-relay" "$TRANSCRIPT")
t "no double-resume on replay" "0" bash -c "echo \$(( after - before ))" 
finish
```

(The idempotence assert re-serves answer 118 by resetting fixtures: implementer
adjusts the `once` markers or re-generates `$FIX` before the second call —
the intent is fixed: same answer served again + sentinel present → resume NOT
called again, ack still fired.)

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `_sweep_api.sh`** (phases 1-2; 10 stubs `phase_resume`/`phase_dispatch` arrive in Task 10):

```bash
#!/usr/bin/env bash
# _sweep_api.sh — the API-binding unattended tick (spec § four-phase tick):
#   renew → relay → resume-first → fresh claims. Each phase independently
#   guarded; each invokable alone: _sweep_api.sh [renew|relay|resume|dispatch|all]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_binding.sh
. "$SCRIPT_DIR/_binding.sh"
[ "$BOARD_BINDING" = api ] || { echo "error: _sweep_api.sh runs only under an api binding" >&2; exit 1; }
die() { echo "error: $*" >&2; exit 1; }
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$SCRIPT_DIR/../../orchestrating-daemons/scripts}"

# One sweep at a time (Codex review F1): overlapping ticks would race the
# sentinel check between its grep and its resume.
exec 9>"$DAEMON_HOME/.sweep-api.lock"
flock -n 9 || exit 0

_registry_metas() {  # prints "uuid<TAB>run_id<TAB>bind_confirmed<TAB>ticket<TAB>bearer<TAB>fence<TAB>lane<TAB>status<TAB>path"
  T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
for p in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    if not m.get("run_id"): continue
    print("\t".join(str(m.get(k, "")) for k in
          ("uuid", "run_id", "bind_confirmed", "ticket", "run_bearer", "fence", "lane", "status")), end="")
    print("\t" + p)
PY
}

# Transcript path for a session (Codex review F1): the registry meta has NO
# transcript field — resolve it the way orchestrating-daemons' own tooling
# does. IMPLEMENTER: read daemon-resume.sh / daemon-list.sh and factor their
# session-jsonl path derivation (the daemon's project dir + current session
# uuid) into this helper; the unit-test fixtures must then use the SAME
# convention (a meta whose derived path exists), never a fabricated
# `transcript` field.
_transcript_for_uuid() { :; }  # implemented from the real convention, above

_alive() { [ "$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$1" 2>/dev/null || echo absent)" != absent ]; }

phase_renew() {
  local uuid run bindc ticket bearer fence lane status path
  while IFS=$'\t' read -r uuid run bindc ticket bearer fence lane status path; do
    [ -n "$run" ] || continue
    if _alive "$uuid"; then
      if T_RUN="$run" _api_py - <<'PY'
import os, sys
import _board_api as A
try:
    A.renew(os.environ["T_RUN"])
except A.RunEnded as e:
    print("run %s: ended (%s) — resume path" % (os.environ["T_RUN"], e))
    sys.exit(3)
PY
      then
        if [ "$bindc" != "True" ] && [ "$bindc" != "true" ]; then
          BOARD_RUN_ID="$run" "$SCRIPT_DIR/board-bind.sh" "$uuid" "$ticket" || true
        fi
      fi
    fi
  done < <(_registry_metas)
}

_relay_prompt() {  # $1=answer id, $2=replies text
  cat <<EOF
[board-relay answer:$1] Your needs-human park on this ticket was answered by
the human. Re-state your gate verdict against the answers in ONE paragraph as
a ticket comment ("[gate] re-pass — <one line>" — PLAN-EXECUTION, which ran no
gate, restates plan-execution status instead), or park fresh if the answers
reshape the work's scope, then proceed under your original protocol. Never
build on momentum past an answer that changed the work's shape.

---- answers (verbatim) ----
$2
EOF
}

_meta_for_ticket() {  # prints uuid<TAB>bearer<TAB>run_id<TAB>fence for the bound meta of ticket $1
  _registry_metas | awk -F'\t' -v t="$1" '$4 == t { print $1 "\t" $5 "\t" $2 "\t" $6; exit }'
}

phase_relay() {
  local page acked_this_pass
  while :; do
    page="$(_api_py - <<'PY'
import json
import _board_api as A
print(json.dumps(A.unrelayed()))
PY
)"
    [ "$page" != "[]" ] || break
    acked_this_pass=0
    local n
    n="$(printf '%s' "$page" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
    local i=0
    while [ "$i" -lt "$n" ]; do
      local aid tid replies
      aid="$(printf '%s' "$page" | python3 -c "import json,sys; print(json.load(sys.stdin)[$i]['answerEventId'])")"
      tid="$(printf '%s' "$page" | python3 -c "import json,sys; print(json.load(sys.stdin)[$i]['ticketId'])")"
      replies="$(printf '%s' "$page" | python3 -c "import json,sys; print('\n'.join(json.load(sys.stdin)[$i]['replies']))")"
      local uuid bearer run fence transcript
      IFS=$'\t' read -r uuid bearer run fence < <(_meta_for_ticket "$tid")
      if [ -z "$uuid" ] || ! _alive "$uuid"; then
        echo "relay: #$tid answer $aid — no live bound session; successor path will deliver"
      else
        transcript="$(_transcript_for_uuid "$uuid")"
        # Ack is gated on PROVEN delivery (Codex review F1): sentinel already
        # present, or a resume call that returned success. A failed resume
        # acks nothing — the answer stays on the feed for the next tick.
        if [ -n "$transcript" ] && grep -qF "[board-relay answer:$aid]" "$transcript" 2>/dev/null; then
          echo "relay: #$tid answer $aid already delivered (sentinel) — acking"
        elif BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
             BOARD_API_URL="$BOARD_API_URL" \
             "$DAEMON_SCRIPTS/daemon-resume.sh" "$uuid" "$(_relay_prompt "$aid" "$replies")"; then
          :  # delivered
        else
          echo "relay: #$tid answer $aid — resume FAILED; not acked, retried next tick"
          i=$((i+1)); continue
        fi
        _api_py - <<PY
import _board_api as A
A.ack($aid)
PY
        acked_this_pass=$((acked_this_pass+1))
      fi
      i=$((i+1))
    done
    # level-triggered drain: re-read only while progress is being made —
    # a pass that acked nothing (all entries dead-session/failed) must break
    # or this loop spins on the same page forever
    [ "$acked_this_pass" -gt 0 ] || break
  done
}

phase_resume() { :; }    # Task 10
phase_dispatch() { :; }  # Task 10

case "${1:-all}" in
  renew) phase_renew ;;
  relay) phase_relay ;;
  resume) phase_resume ;;
  dispatch) phase_dispatch ;;
  all) phase_renew || true; phase_relay || true; phase_resume || true; phase_dispatch || true ;;
  *) die "usage: _sweep_api.sh [renew|relay|resume|dispatch|all]" ;;
esac
```

And at the very TOP of `board-sweep.sh` — before its own env/gh
initialization, mirroring the dispatch scripts (Codex review F3):

```bash
. "$SCRIPT_DIR/_binding.sh"
if [ "$BOARD_BINDING" = api ]; then exec "$SCRIPT_DIR/_sweep_api.sh" all; fi
```

Test-fixture honesty (Codex review F1): the Task-9 test's registry metas must
NOT carry a fabricated `transcript` field — set up each fake session so that
`_transcript_for_uuid` (the real derivation) resolves to the test's transcript
file, i.e. create the file at the path the orchestrating-daemons convention
derives for that uuid. Adjust the test scaffolding shown in Step 1
accordingly when implementing the helper. The undeliverable/dead-session
branch acks nothing by design (never ack-and-drop) — the drain loop breaks on
a zero-ack pass, as coded above.

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-sweep-renew-relay.sh` → `PASS`.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_sweep_api.sh skills/issue-tracker/scripts/board-sweep.sh \
  tests/claude-code/board-api/test-sweep-renew-relay.sh
git commit -m "feat(a2): sweep phases 1-2 — lease renew + bind repair, sentinel relay"
```

---

### Task 10: sweep phases 3+4 — resume-first, suppression, recovery, dispatch hand-off

**Files:**
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (fill `phase_resume`/`phase_dispatch`)
- Test: `tests/claude-code/board-api/test-sweep-resume.sh`

**Interfaces:**
- Consumes: `_board_api.needing_resume/claim_successor/register/end_run` (Task 2); `implement-dispatch.sh`/`review-dispatch.sh` API modes (Tasks 7-8); suppression files `$DAEMON_HOME/board-suppress/<ticket>.json` `{"ticket": N, "state": "...", "env_issue": N}`.
- Produces: `phase_resume` — per feed entry: skip if suppressed; claim-successor; fold unrelayed answers for that ticket into the resume prompt (sentinels included) and ack them after delivery; on `daemon-resume` failure fall back to fresh spawn on the same successor bearer, bootstrap directing the worker to read its own timeline first; count `resume_attempts` in the registry; at 3 failed cycles register the env-issue + write the suppression file. `phase_dispatch` — invoke `implement-dispatch.sh --sweep` and `review-dispatch.sh --sweep` (their API modes claim); suppression check on every claimed ticket (end run + stop lane on hit); lift suppression when state moved or env-issue closed.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-sweep-resume.sh` (same scaffolding pattern as Task 9; fixtures and asserts):

```bash
# fixtures:
#  GET /runs/needing-resume -> once: [{"ticketId":12,"state":"in-progress","predecessorRunId":41}], then []
#  POST /runs/claim-successor -> {"runId":44,"ticketId":12,"fence":4,"bearer":"tok-s",
#    "predecessorRun":41,"sessionLocator":{"storeNs":"local:h","projectKey":"r","sessionId":"u-old"},
#    "plan":null,"body":"work on"}
#  GET /answers/unrelayed -> once: [{"answerEventId":121,"ticketId":12,"correlationId":"evt-9","replies":["go"]}], then []
#  POST /answers/121/ack -> {"acked":true}
#  POST /runs/44/bind -> {"bound":true}
#  POST /tickets (env-issue escalation) -> {"id":90,"state":"needs-human"}
# registry: meta for u-old with transcript file; daemon-resume stub SUCCEEDS
# asserts:
t "successor claimed for the feed entry" "/runs/claim-successor" cat "$FIX.log"
t "folded answer delivered with sentinel" "[board-relay answer:121]" cat "$TRANSCRIPT"
t "folded answer acked" "/answers/121/ack" cat "$FIX.log"
t "successor bound" "/runs/44/bind" cat "$FIX.log"
# persist-before-resume: the resume stub CAPTURES the registry meta at the
# moment it runs (copy the meta file inside the stub); assert the copy already
# carries run_id 44, the successor bearer, and bind_confirmed false
t "registry persisted before resume" '"run_id": 44' cat "$DH/meta-at-resume.json"
# env injection: the resume stub also dumps its BOARD_* env
t "successor creds on resume env" "BOARD_RUN_TOKEN=tok-s" cat "$DH/resume-env.txt"
# failure path: point daemon-resume at 'exit 1', re-serve the feed 3x with
# fresh successor claims (runIds 45,46,47) and a fresh-spawn stub that also fails;
# after cycle 3:
t "escalation registers env-issue" '\"category\": \"env-issue\"' cat "$FIX.log"
t "suppression file written" '"ticket": 12' cat "$DH/board-suppress/12.json"
# suppressed: serve the feed with ticket 12 again ->
t "suppressed ticket skipped" "suppressed — skipping #12" SW resume
# lift: env-issue closed in fixtures (GET /tickets returns 90 done) ->
t "suppression lifts on env-issue close" "suppression lifted for #12" SW resume
```

The implementer writes this test fully in the Task 9 scaffolding style — every
fixture body shown above verbatim, stubs as in Task 9, `t` asserts as listed.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — replace the two stubs in `_sweep_api.sh`:

```bash
SUPPRESS_DIR="$DAEMON_HOME/board-suppress"

_suppressed() { [ -f "$SUPPRESS_DIR/$1.json" ]; }

_check_lift() {  # lift suppression for ticket $1 if state moved or env-issue closed
  T_TID="$1" T_DIR="$SUPPRESS_DIR" _api_py - <<'PY'
import json, os
import _board_api as A
path = os.path.join(os.environ["T_DIR"], os.environ["T_TID"] + ".json")
if not os.path.exists(path): raise SystemExit
rec = json.load(open(path))
rows = {t["id"]: t["state"] for t in A.tickets(principal="automation")}
moved = rows.get(rec["ticket"]) != rec["state"]
closed = rows.get(rec["env_issue"]) in (None, "done", "wontfix")
if moved or closed:
    os.remove(path)
    print("suppression lifted for #%s" % rec["ticket"])
PY
}

_fold_answers() {  # $1=ticket; prints "ids<TAB>text" of unrelayed answers for it
  T_TID="$1" _api_py - <<'PY'
import os
import _board_api as A
tid = int(os.environ["T_TID"])
mine = [a for a in A.unrelayed() if a["ticketId"] == tid]
ids = ",".join(str(a["answerEventId"]) for a in mine)
text = "\n\n".join(A.SENTINEL % a["answerEventId"] + "\n" + "\n".join(a["replies"]) for a in mine)
print(ids + "\t" + text.replace("\n", "\\n"))
PY
}

phase_resume() {
  mkdir -p "$SUPPRESS_DIR"
  for f in "$SUPPRESS_DIR"/*.json; do
    [ -e "$f" ] && _check_lift "$(basename "$f" .json)"
  done
  local feed tid
  feed="$(_api_py - <<'PY'
import json
import _board_api as A
print(json.dumps(A.needing_resume()))
PY
)"
  local n i=0
  n="$(printf '%s' "$feed" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  while [ "$i" -lt "$n" ]; do
    tid="$(printf '%s' "$feed" | python3 -c "import json,sys; print(json.load(sys.stdin)[$i]['ticketId'])")"
    i=$((i+1))
    if _suppressed "$tid"; then echo "suppressed — skipping #$tid"; continue; fi
    _resume_one "$tid" || true
  done
}

_resume_one() {  # claim successor + deliver; returns nonzero only on total failure
  local tid="$1" nonce resp
  nonce="$(uuidgen)"
  mkdir -p "$DAEMON_HOME/board-claims"
  printf '{"lane": "successor", "run_id": null, "spawn_completed": false}\n' > "$DAEMON_HOME/board-claims/$nonce.json"
  resp="$(T_TID="$tid" T_NONCE="$nonce" _api_py - <<'PY'
import json, os
import _board_api as A
print(json.dumps(A.claim_successor(os.environ["T_TID"], os.environ["T_NONCE"])))
PY
)" || return 1
  [ "$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("claimed", True))')" != "False" ] || return 0
  local run fence bearer sess ids text
  run="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])')"
  fence="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["fence"])')"
  bearer="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["bearer"])')"
  sess="$(printf '%s' "$resp" | python3 -c 'import json,sys; l=json.load(sys.stdin).get("sessionLocator"); print(l["sessionId"] if l else "")')"
  printf '{"lane": "successor", "run_id": %s, "spawn_completed": false}\n' "$run" > "$DAEMON_HOME/board-claims/$nonce.json"
  IFS=$'\t' read -r ids text < <(_fold_answers "$tid")
  text="$(printf '%b' "${text//\\n/\\n}")"
  local prompt="You are the successor run for ticket #$tid — your predecessor was reclaimed.
Read your own ticket timeline first (board-show.sh $tid): the park/answer
history there is part of your assignment. Then continue under your original
protocol.${text:+

$text}"
  local delivered=""
  # Persist BEFORE resume (spec + Codex review F2): the successor's run
  # identity must be durable before any delivery attempt — a crash after
  # resume but before bind is repaired by phase 1 only if the registry
  # already names run_id/bearer/fence. Update the predecessor session's meta
  # in place (it is the session being resumed).
  if [ -n "$sess" ]; then
    T_UUID="$sess" T_RUN="$run" T_FENCE="$fence" T_BEARER="$bearer" T_TID="$tid" \
    T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
env = os.environ
for p in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"): continue
    try: m = json.load(open(p))
    except Exception: continue
    if m.get("uuid") == env["T_UUID"]:
        m.update(run_id=int(env["T_RUN"]), fence=int(env["T_FENCE"]),
                 run_bearer=env["T_BEARER"], ticket=env["T_TID"],
                 bind_confirmed=False)
        json.dump(m, open(p, "w"), indent=1); os.chmod(p, 0o600)
        break
PY
  fi
  # daemon-resume forks a fresh process from OUR env (Codex review F2): the
  # successor credentials ride the invocation or the worker writes nothing.
  if [ -n "$sess" ] && BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" \
       BOARD_RUN_FENCE="$fence" BOARD_API_URL="$BOARD_API_URL" \
       "$DAEMON_SCRIPTS/daemon-resume.sh" "$sess" "$prompt" 2>/dev/null; then
    delivered="$sess"
  else
    # fresh spawn on the same successor bearer — session resume is optimization
    local body_file="$DAEMON_HOME/board-claims/$nonce.body.md"
    printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("body") or "")' > "$body_file"
    local uuid
    if uuid="$(BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" BOARD_API_URL="$BOARD_API_URL" \
        "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$tid-succ" "$prompt" "${LOCAL_REPO:-$BOARD_ROOT}" "$tid-succ" \
        "${IMPLEMENT_MODEL:-opus}" | sed -n 's/^uuid: //p')" && [ -n "$uuid" ]; then
      delivered="$uuid"
    fi
  fi
  if [ -n "$delivered" ]; then
    printf '{"lane": "successor", "run_id": %s, "spawn_completed": true}\n' "$run" > "$DAEMON_HOME/board-claims/$nonce.json"
    [ -z "$ids" ] || T_IDS="$ids" _api_py - <<'PY'
import os
import _board_api as A
for aid in os.environ["T_IDS"].split(","):
    if aid: A.ack(aid)
PY
    BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" "$SCRIPT_DIR/board-bind.sh" "$delivered" "$tid" || true
    _bump_attempts "$tid" reset
  else
    _bump_attempts "$tid" fail "$run"
  fi
}

_bump_attempts() {  # $1=ticket $2=reset|fail $3=run-to-end-on-escalate
  local f="$DAEMON_HOME/board-suppress/.attempts-$1"
  if [ "$2" = reset ]; then rm -f "$f"; return 0; fi
  local n; n="$(( $(cat "$f" 2>/dev/null || echo 0) + 1 ))"; echo "$n" > "$f"
  # the failed successor run must not squat the ticket
  [ -z "${3:-}" ] || T_RUN="$3" _api_py - <<'PY' || true
import os
import _board_api as A
try: A.end_run(os.environ["T_RUN"], "abandoned")
except A.RunEnded: pass
PY
  if [ "$n" -ge 3 ]; then
    local eid state
    state="$(T_TID="$1" _api_py - <<'PY'
import os
import _board_api as A
tid = int(os.environ["T_TID"])
print(next((t["state"] for t in A.tickets(principal="automation") if t["id"] == tid), ""))
PY
)"
    eid="$(T_TID="$1" _api_py - <<'PY'
import os
import _board_api as A
out = A.register({"title": "stuck resume: ticket #%s worker cannot be revived" % os.environ["T_TID"],
                  "category": "env-issue",
                  "body": "3 resume/fresh-spawn cycles failed for ticket #%s. The sweep has "
                          "suppressed it; investigate the session/daemon substrate, then move "
                          "the ticket (any transition) or close this env-issue to lift "
                          "suppression." % os.environ["T_TID"]},
                 principal="automation")
print(out["id"])
PY
)"
    printf '{"ticket": %s, "state": "%s", "env_issue": %s}\n' "$1" "$state" "$eid" > "$SUPPRESS_DIR/$1.json"
    rm -f "$f"
    echo "escalated #$1 → env-issue #$eid (suppressed)"
  fi
}

phase_dispatch() {
  local impl="$SCRIPT_DIR/../../implementing/scripts/implement-dispatch.sh"
  local revw="$SCRIPT_DIR/../../reviewing-prs/scripts/review-dispatch.sh"
  BOARD_SUPPRESS_DIR="$SUPPRESS_DIR" "$impl" --sweep || true
  BOARD_SUPPRESS_DIR="$SUPPRESS_DIR" "$revw" --sweep || true
}
```

And in Task 7's `_claim_one` (this task edits it): after a successful claim,
before spawning, check suppression —

```bash
  if [ -n "${BOARD_SUPPRESS_DIR:-}" ] && [ -f "$BOARD_SUPPRESS_DIR/$ticket.json" ]; then
    T_RUN="$run_id" _api_py - <<'PY'
import os
import _board_api as A
A.end_run(os.environ["T_RUN"], "abandoned")
PY
    rm -f "$claims_dir/$nonce.json" "$body_file"
    echo "claim yielded suppressed #$ticket — released; lane paused this tick"
    return 1
  fi
```

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-sweep-resume.sh` → `PASS`; re-run Tasks 7/9 tests (this task edited their files) → `PASS`.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_sweep_api.sh skills/implementing/scripts/implement-dispatch.sh \
  tests/claude-code/board-api/test-sweep-resume.sh
git commit -m "feat(a2): sweep phases 3-4 — resume-first with answer fold, suppression + env-issue escalation"
```

---

### Task 11: `board-answer.sh` API mode (dual-principal, inline relay)

**Files:**
- Modify: `skills/issue-tracker/scripts/board-answer.sh` (API branch after arg parsing, line ~34)
- Test: `tests/claude-code/board-api/test-answer.sh`

**Interfaces:**
- Consumes: `_board_api.queue_decisions/park_answer` (Task 2), `_sweep_api.sh relay` (Task 9).
- Produces: API mode `board-answer.sh <n> "<answers>"` → look up the standing park's `correlation_id` from the queue, `park_answer` (human principal; replies = the answers as a single-element list; NO `to` — the bound/unbound discriminator is the server's), print `answered #<n> → <returnedTo>`, then run `_sweep_api.sh relay` once inline. `--posted` is gh-mode-only (API answers ARE the record) — refuse with guidance.

- [ ] **Step 1: Write the failing test**

`tests/claude-code/board-api/test-answer.sh` (Task 9 scaffolding style):

```bash
# fixtures:
#  GET /queue/decisions -> [{"correlation_id":"evt-101","ticket_id":12,...,"state":"needs-human",...}]
#  POST /tickets/12/park-answer -> {"answered":true,"returnedTo":"in-progress","answerEventId":118}
#  GET /answers/unrelayed -> once [{"answerEventId":118,"ticketId":12,"correlationId":"evt-101","replies":["ship it"]}], then []
#  POST /answers/118/ack -> {"acked":true}
# registry meta binds ticket 12 to a live stubbed session (as Task 9)
# asserts:
t "correlationId sent" '\"correlationId\": \"evt-101\"' cat "$FIX.log"
t "human token on answer leg" '\"auth\": \"Bearer h\"' bash -c "grep park-answer '$FIX.log'"
t "automation token on ack leg" '\"auth\": \"Bearer a\"' bash -c "grep ack '$FIX.log'"
t "inline relay delivered" "[board-relay answer:118]" cat "$TRANSCRIPT"
t "prints server disposition" "answered #12 → in-progress" ...
t "--posted refused in API mode" "gh-mode-only" ...
```

(Write it out fully with the Task 9 fixture/stub scaffolding.)

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — insert after line 33 (`[ -n "$posted" ] || …`):

```bash
if [ "$BOARD_BINDING" = api ]; then
  [ -z "$posted" ] || die "--posted is gh-mode-only: an API park-answer IS the record — pass the answers"
  T_ID="$tid" T_ANSWERS="$answers" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_ID"].lstrip("#")
cid = next((q["correlation_id"] for q in A.queue_decisions()
            if str(q["ticket_id"]) == tid and q["species"] == "board"), None)
out = A.park_answer(tid, [os.environ["T_ANSWERS"]], correlation_id=cid)
if out.get("superseded"):
    A.die("#%s: answer superseded — the standing question changed; re-read the queue" % tid)
print("answered #%s → %s" % (tid, out["returnedTo"]))
PY
  # inline relay: the human's answer resumes the worker now, not next tick
  "$SCRIPT_DIR/_sweep_api.sh" relay
  exit 0
fi
```

(Unbound parks: the server answers `409 no-return-mapping` — the die message
carries it verbatim; the human re-runs with a disposition via a direct
`park_answer` call is NOT scripted here. Instead extend the branch: accept an
optional `--to <state>` flag parsed alongside the existing args and passed as
`to=` — the server refuses it on bound parks with `answer-target-not-allowed`,
which is the honest surface. Add `--to` to the usage header.)

- [ ] **Step 4: Run tests** — `bash tests/claude-code/board-api/test-answer.sh` → `PASS`; full suite unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-answer.sh tests/claude-code/board-api/test-answer.sh
git commit -m "feat(a2): board-answer API mode — correlation-pinned answer + inline relay"
```

---

### Task 12: integration harness — local A1 instance

**Files:**
- Create: `tests/claude-code/board-api/integration/harness.sh`
- Test: `tests/claude-code/board-api/integration/test-harness-smoke.sh`

**Interfaces:**
- Consumes: `$ARKHO_DIR` naming an arkho checkout (skip loudly when absent); the board service's own dev-run knowledge: `cd $ARKHO_DIR/board-service && npm ci` once, then `node src/main.js` with `DATABASE_URL`/`DIRECT_DATABASE_URL`/`MIGRATION_DATABASE_URL` pointed at a local scratch Postgres database and `ADMIN_TOKEN` a test constant (the service's test suite documents the env contract; `board-service/API.md` § Operating notes has the boot order).
- Produces: `harness.sh start` → launches Postgres db (createdb a scratch db, all three URLs = same local DSN, which the service accepts — pooling niceties don't apply locally), boots the service on `127.0.0.1:8917`, waits for `/healthz` 200, mints one automation principal (capabilities dispatch+sweep) and one human principal via the admin API, writes `BOARD_CREDENTIALS_FILE` + a ready-to-source env block to `$HARNESS_DIR/env.sh`. `harness.sh stop` tears down. Every integration test sources `env.sh` and gets: `BOARD_API_URL`, `BOARD_CREDENTIALS_FILE`, `ADMIN_TOKEN`.

- [ ] **Step 1: Write the smoke test**

```bash
#!/usr/bin/env bash
. "$(dirname "$0")/../helpers.sh"
[ -n "${ARKHO_DIR:-}" ] || { echo "SKIP: ARKHO_DIR not set (integration tier needs the arkho checkout)"; exit 0; }
H="$(dirname "$0")/harness.sh"
"$H" start
trap '"$H" stop' EXIT
. "$(dirname "$0")/.harness/env.sh"
t "healthz green" '"ok":true' curl -s "$BOARD_API_URL/healthz"
t "automation can list" "[" curl -s -H "authorization: Bearer $(grep BOARD_AUTOMATION_TOKEN "$BOARD_CREDENTIALS_FILE" | cut -d= -f2)" "$BOARD_API_URL/tickets"
finish
```

- [ ] **Step 2: Run** — with `ARKHO_DIR` unset expect the loud SKIP; with it set expect FAIL (no harness yet).

- [ ] **Step 3: Implement `harness.sh`** — `start`: `createdb board_a2_test_$$` (die with a clear message if `createdb`/Postgres absent); export the three URLs as `postgresql://localhost/board_a2_test_$$`; `ADMIN_TOKEN="a2-test-$(openssl rand -hex 16)"`; `(cd "$ARKHO_DIR/board-service" && [ -d node_modules ] || npm ci)`; `node src/main.js` backgrounded with PORT=8917, pid + dbname recorded under `.harness/`; poll `/healthz` up to 30s; mint principals through the service's admin surface (the implementer reads `board-service/API.md` § Identity and § Operating notes for the exact admin route/shape — it is A1's delivery, drill-pinned there) and write `.harness/env.sh` exporting `BOARD_API_URL=http://127.0.0.1:8917`, `BOARD_CREDENTIALS_FILE=$PWD/.harness/creds.env`. `stop`: kill pid, `dropdb`. Both idempotent.

- [ ] **Step 4: Run** — `ARKHO_DIR=~/developer/github/arkho bash tests/claude-code/board-api/integration/test-harness-smoke.sh` → `PASS`.

- [ ] **Step 5: Commit**

```bash
git add tests/claude-code/board-api/integration/
git commit -m "test(a2): integration harness — local A1 instance on scratch Postgres"
```

---

### Task 13: integration drills — protocol walk, transcript diff, crash-at-boundary, resume-first, renewal, escalation

**Files:**
- Create: `tests/claude-code/board-api/integration/test-protocol-walk.sh`
- Create: `tests/claude-code/board-api/integration/test-transcript-diff.sh`
- Create: `tests/claude-code/board-api/integration/test-crash-boundaries.sh`
- Create: `tests/claude-code/board-api/integration/test-resume-first.sh`
- Create: `tests/claude-code/board-api/integration/test-lease-renewal.sh`
- Create: `tests/claude-code/board-api/integration/test-escalation.sh`

All are `ARKHO_DIR`-gated (same SKIP line as Task 12) and use the harness. All
worker sessions are SCRIPTED (a fake `daemon-spawn.sh`/`daemon-resume.sh` that
executes a scripted sequence of verb calls with the injected env and appends
prompts to a transcript file) — no model calls anywhere in the tier.

**Interfaces:**
- Consumes: everything prior.
- Produces: acceptance evidence for spec acceptance items 1-7.

- [ ] **Step 1: `test-protocol-walk.sh`** (spec acceptance 1) — against the harness:
register a ticket (automation), `implement-dispatch.sh --sweep` with the
scripted spawn stub; the stub, as the worker, runs with the captured env:
`board-transition.sh <t> in-progress` + `board-comment.sh <t> "[gate] pass — scripted"`,
`board-transition.sh <t> needs-human "which db?"`; then the test as the human:
`board-answer.sh <t> "sqlite"` (bg, per header) — assert the scripted resume
received the sentinel prompt; the worker continues: `in-review` with
`--pr https://example.test/pr/1`, then human `confident-ready` → `done` via
transitions. Assert at the end: `GET /tickets` shows `done`; a `PATH` shim
directory containing a `gh` script that does `echo "GH INVOKED $*" >> $GH_LOG; exit 97`
is prepended for the WHOLE walk and `$GH_LOG` must be empty at the end
("the gh CLI is never invoked — asserted by the test harness").

- [ ] **Step 2: `test-transcript-diff.sh`** (acceptance 2) — run the same scripted
worker sequence twice: once against a gh-mode scratch repo with a stubbed `gh`
(the stub answers the minimal `gh issue view/list/comment/edit` calls from a
state file — reuse the stub approach in `tests/claude-code/test-helpers.sh` if
one exists; else the stub keeps a JSON state file), once against the harness
in API mode. Capture each worker-visible surface: the argv of every board
script call + its stdout. Normalize ids (`s/#[0-9]+/#N/g`, timestamps, urls,
uuids), then `diff` the two captures. Expected: empty diff. KNOWN normalization
allowances (from the spec, transport-modulo): register's printed url differs
(normalized), transition echo format is identical by construction (Task 4
matched the gh-mode `#N: → state` output shape — verify against
`board-transition.sh`'s gh-mode print and align the API-mode format to it
exactly as part of this task if they differ).

- [ ] **Step 3: `test-crash-boundaries.sh`** (acceptance 3) — three cases on a
parked+answered ticket with a live scripted session:
(a) kill relay BEFORE resume: run `_sweep_api.sh relay` with `daemon-resume.sh`
stubbed to `exit 137` (simulates dying mid-delivery with nothing written);
assert answer still unrelayed (`GET /answers/unrelayed` non-empty), no ack.
(b) crash BETWEEN resume and ack: stub `daemon-resume.sh` writes the prompt to
the transcript then `exit 137`; sweep run dies (set `-e` path) before ack;
assert transcript has the sentinel exactly once and the answer is STILL served;
run `_sweep_api.sh relay` again with a healthy stub; assert transcript still
has exactly ONE sentinel (no double-resume) and the answer is now acked.
(c) after ack: run relay again; assert feed empty, transcript sentinel count
still 1.

- [ ] **Step 4: `test-resume-first.sh`** (acceptance 4) — seed one reclaimed
in-flight ticket (claim, let the lease expire — claim with `leaseMinutes: 1`
is still 60s; instead reclaim via the service's sweep by ending the worker
daemon stub and waiting for the service reclaim pass with a 1-minute lease;
the harness's reconcile interval is seconds) and one ready ticket. Run
`_sweep_api.sh all` and assert order: the `claim-successor` request appears in
the service's request log (or: the successor run exists) BEFORE any fresh
`POST /runs/claim` yields the ready ticket.

- [ ] **Step 5: `test-lease-renewal.sh`** (acceptance 5) — claim with
`leaseMinutes: 1`; run `_sweep_api.sh renew` every 20s for 3.5 minutes
(loop in the test) with a live stub daemon; assert the run is never reclaimed
(`GET /runs/needing-resume` stays empty for that ticket). Then stop renewing
(mark the stub dead), wait one lease window + the service's reclaim pass;
assert the ticket appears in `needing-resume`.

- [ ] **Step 6: `test-escalation.sh`** (acceptance 6) — force both
`daemon-resume.sh` and `daemon-spawn.sh` stubs to fail; run
`_sweep_api.sh resume` three times (each after re-reaping the successor via
service reclaim or `end_run`); assert: an `env-issue` ticket exists born
`needs-human` naming the stuck ticket; the suppression file exists; a fourth
`resume` run prints `suppressed — skipping`; then close the env-issue (human
transition `wontfix` with note) and assert the next run prints
`suppression lifted`.

- [ ] **Step 7: Run the tier** — `ARKHO_DIR=… bash` each test → all `PASS`.
Run `scripts/lint-shell.sh` → clean.

- [ ] **Step 8: Commit**

```bash
git add tests/claude-code/board-api/integration/
git commit -m "test(a2): integration drills — protocol walk, transcript diff, crash boundaries, resume-first, renewal, escalation"
```

---

### Task 14: read-scope audit + final verification + live smoke

**Files:**
- Modify: `docs/doperpowers/specs/2026-08-09-a2-board-adapter-design.md` (Outcomes; Revision Notes if drift found)
- Test: everything.

- [ ] **Step 1: Read-scope audit** (spec § Testing, plan-time gate) — run:

```bash
grep -n "board-list.sh\|board-show.sh\|gh issue view\|gh issue list" \
  skills/implementing/SKILL.md skills/architecting/SKILL.md skills/reviewing-prs/SKILL.md \
  skills/implementing/references/*.md skills/reviewing-prs/references/*.md
```

For each hit, classify: worker-executed read of an ARBITRARY ticket (out of
own+children scope) → rewrite the protocol line to an in-scope read or flag it
in the spec's Surprises as a divergence with its consequence; own-ticket /
dispatcher-context / human-context reads → fine, note "audited: in scope".
Record the audit outcome (hits + dispositions) in the spec's
`## Surprises & Discoveries`.

- [ ] **Step 2: Full unit tier** — `for t in tests/claude-code/board-api/test-*.sh; do bash "$t"; done` → all `PASS`.

- [ ] **Step 3: Full existing suite** — `tests/claude-code/run-skill-tests.sh` → pass set identical to the parent commit of Task 1 (gh-mode regression = spec acceptance 7). Also `scripts/lint-shell.sh` → clean.

- [ ] **Step 4: Integration tier** (spec acceptance 1-6):

```bash
ARKHO_DIR="$HOME/developer/github/arkho" bash tests/claude-code/board-api/integration/test-harness-smoke.sh
for t in tests/claude-code/board-api/integration/test-*.sh; do
  ARKHO_DIR="$HOME/developer/github/arkho" bash "$t"
done
```

Expected: every script prints `PASS <name>`.

- [ ] **Step 5: Live smoke** (spec acceptance 8, verbatim): against
`https://arkho-board-service.onrender.com` with the operator credentials in
`~/.arkho-board/secrets.env` — bind a scratch repo
(`.doperpowers/board.json` → the live URL; credentials file assembled from
secrets.env: the admin bearer serves as the human token; mint an automation
principal via the admin surface if none exists yet), then run the scripted
protocol walk ONCE including the epic-recomposition drill (register a parent +
child; walk the child to `done`; assert the parent returns to
`ready-for-architect` — the reconciler's recomposition return, exercising
A1.G3). Close every drill ticket `wontfix` with note "A2 live smoke". Record
outputs (healthz, walk transcript, recomposition observation) in the spec's
Outcomes section.

- [ ] **Step 6: Version bump + spec Outcomes**

```bash
scripts/bump-version.sh minor
```

Write the spec's `## Outcomes & Retrospective` (what shipped vs the spec's
purpose, acceptance evidence per item 1-8, gaps, lessons); commit.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(a2): final verification — acceptance 1-8 evidence, read-scope audit, version bump"
```

---

## Self-Review (author's pass)

- **Spec coverage:** binding (T1), client core+errors+retry (T2), comment verb + protocol substitution (T3), register/transition + fail-loud + spike-409 + park-note (T4), read verbs incl. map/lint thinning (T5), bind/locator (T6), claim dispatch + nonce lifecycle + env injection + bootstrap (T7), qagent (T8), renew+bind-repair+relay sentinel (T9), resume-first + fold + suppression + escalation + phase-4 wiring (T10), board-answer dual-principal + inline relay + `--to` disposition (T11), local instance (T12), acceptance drills 1-6 (T13), read-scope audit + acceptance 7-8 + Outcomes (T14). Engine-routing limitation and A5 non-flip are scope-outs — no task, correctly.
- **Known intentional gaps:** `board-map.sh` API mode renders parent edges only (`GET /tickets` v1 exposes no blocked-by) — noted in T5 and honest in the render; `board-list.sh` API mode drops `ELIGIBLE`/`CLOSE?` tags (server owns pick; close candidacy is a gh-PR concept) — the transcript drill only covers worker-visible surface, and workers don't call list in protocols.
- **Type consistency:** `_board_api` function names/signatures fixed in File Structure and used identically in T4-T13; registry field names (`run_id`, `bind_confirmed`, `lane`, `spawn_completed`) consistent across T6/T7/T9/T10; sentinel format single-sourced as `A.SENTINEL` and the literal in `_relay_prompt` (T9) — implementer keeps them equal.
- **Spec drift found while planning:** one — the spec's "triggered dispatch stays valid as a targeted claim" is not implementable: the API exposes no claim-by-ticket route (`claim-successor` serves reclaim markers only). Resolved: API-mode `implement-dispatch.sh <n>` fails loud naming the gap; targeted claim recorded as a flow-back candidate on arkho#7; spec Revision Notes v1.2 carries the change. Also pinned by review: `board-answer --posted` refusal (consistent with spec text, no revision).
- **Codex adversarial review (gpt-5.6-sol) folded in:** all 6 findings adopted — ack gated on proven delivery + zero-ack drain break + sweep flock (F1); persist-before-resume + credential env injection on every resume + bearer-at-rest in registry meta 0600 (F2); `_binding.sh` sourceable pre-gh in every entry point + raw `gh issue view`/spike-protocol audit extended (F3); real daemon-spawn output parsing + claim-journal startup reconciliation (F4); interactive helpers default `principal="human"` + operator-context tests (F5); triggered dispatch fails loud, spec revised (F6).

