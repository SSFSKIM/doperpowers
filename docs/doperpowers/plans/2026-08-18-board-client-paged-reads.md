# Board Client Paged Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate every production board read in `skills/issue-tracker/scripts/` off the read-whole bare arrays onto arkho's paged surface (by-id, `ids=` batch, cursor walks), per spec `docs/doperpowers/specs/2026-08-18-board-client-paged-reads-design.md` **v1.1**.

**Architecture:** All sixteen read sites flow through one helper, `_board_api.py`; the migration adds four primitives there (`ticket`, `tickets_by_ids`, `tickets_all`, `queue_decisions_all` over a shared `_walk` generator) and moves eleven sites onto them. Five sites sit on routes with no paged form and gain cap-awareness comments only. The legacy `tickets()`/`queue_decisions()` helpers are deleted once the last caller moves.

**Tech Stack:** Python 3 stdlib (`urllib`) inside bash heredocs (`_api_py`); hermetic unit tier against `tests/claude-code/board-api/mock-server.py`; integration tier against the real board service (docker).

## Global Constraints

- Spec: `docs/doperpowers/specs/2026-08-18-board-client-paged-reads-design.md` **v1.1** — re-read your task's sections before implementing. The spec governs over this plan where they diverge.
- THE WALK CONTRACT (spec § Helper primitives, verbatim in behavior): (1) no partial results — a walk returns only when the final page answered `next: null`; any page failure dies after `request()`'s per-page retries. (2) walk absence is REPORT-grade, never ACTION-grade — action-grade absence is a targeted `ticket()` 404 (tickets) or a second walk started after the first finished (queue).
- Envelope shape: `{"items": [...], "next": "…"|null, "as_of": <int>}` on both `GET /tickets` and `GET /queue/decisions` paged forms. The page-size opt-in is `limit=200` explicit (`_PAGE_LIMIT`). `ids=` cap is 200 (`_MAX_IDS`). Queue rows have NO `id` — identity is `correlation_id`; the queue walk performs no dedupe (immutable keyset). The tickets walk dedupes by `id`, later occurrence's DATA winning (dict overwrite; position stays first-seen).
- by-id 404 (`not-found`) maps to `None` ONLY once the paged surface is proven for this process (any successful envelope read proves it; an unproven 404 triggers the one-shot `GET /tickets?limit=1` probe — a bare array answer dies naming a pre-read-surface server). Route-level and row-level 404 share one code; messages are unstable by contract — never parse them.
- Every migrated site keeps its current absent-behavior (defer / die / skip); only the evidence upgrades. board-lint and board-answer are the two sites with confirm steps (spec § Semantics preservation).
- No new dependencies: python3 stdlib only, bash 3.2-compatible shell. No `Date`-like lossy handling of cursors: the `next` token is passed back VERBATIM (it is base64url, URL-safe — never decoded, re-encoded, or url-quoted).
- Unit tests are hermetic: `tests/claude-code/board-api/test-*.sh` each boot `mock-server.py <fixtures.json> <port>`; fixtures are contract-shaped from the real service's observed output (mock-fidelity rule). The mock matches by PATH PREFIX, first unused `once` entry wins — multi-page walks are scripted as a QUEUE of `once` entries on the same path prefix, and cursor transmission is asserted from `<fixtures.json>.log`.
- Run a single unit file: `bash tests/claude-code/board-api/test-<name>.sh` (exit 0 = pass). Full suite: `bash tests/claude-code/run-skill-tests.sh`. Integration tier (Task 6/7 only): needs the arkho board service running locally — `ARKHO_DIR="$HOME/Developer/GitHub/arkho"` and follow `tests/claude-code/board-api/integration/README.md` / `harness.sh` (docker Postgres; NEVER any production DSN or URL).
- Under `set -o pipefail`, never `printf big | grep -q` in test helpers (SIGPIPE flake) — use herestrings.
- Commits: plain messages, no attribution lines. Version bumps ONLY via `scripts/bump-version.sh` (Task 7).

## File Structure

- `skills/issue-tracker/scripts/_board_api.py` — the only file gaining logic: `_PAGE_LIMIT`, `_MAX_IDS`, `_SURFACE` cache, `_envelope()`, `_walk()`, `ticket()`, `tickets_by_ids()`, `tickets_all()`, `queue_decisions_all()`; `request()` gains `absent=()`; legacy `tickets()`/`queue_decisions()` deleted in Task 6.
- `skills/issue-tracker/scripts/_sweep_api.sh` — `_check_lift`, `_escalate` (2 reads), cap comments on `_unrelayed_dump`, `_fold_answers`, `phase_resume`.
- `skills/issue-tracker/scripts/board-show.sh`, `board-transition.sh`, `board-list.sh`, `board-lint.sh`, `board-reconcile.sh`, `board-map.sh`, `board-answer.sh` — call-site swaps.
- `tests/claude-code/board-api/test-paged-reads.sh` — NEW: helper-level drills.
- Existing unit test files whose `/tickets`-GET fixtures must become envelopes: whichever files exercise the migrated callers (find by running them — `_envelope()` dies loudly on a bare array). Known: `test-sweep-resume.sh`, `test-read-verbs.sh`, `test-answer.sh`, `test-register-transition.sh` (check the rest by running the full suite).
- `tests/claude-code/board-api/integration/drill-lib.sh` — `ticket_state()`/`ticket_owner()` move to by-id (Task 6).

---

### Task 1: Helper primitives + paged-read unit drills

**Files:**
- Modify: `skills/issue-tracker/scripts/_board_api.py` (`request()` at ~line 118; new functions after `queue_decisions()` at ~line 246)
- Create: `tests/claude-code/board-api/test-paged-reads.sh`

**Interfaces:**
- Consumes: existing `request(method, path, body, principal, ok, retry, obsolete_codes)`, `die()`.
- Produces (later tasks call these EXACT signatures):
  - `ticket(tid, principal="human") -> dict | None`
  - `tickets_by_ids(ids, principal="human") -> dict[int, dict]` (keyed by int id; absent id = absent key, authoritative)
  - `tickets_all(states=None, principal="human") -> list[dict]`
  - `queue_decisions_all() -> list[dict]`

- [ ] **Step 1: Write the failing drills.** Create `tests/claude-code/board-api/test-paged-reads.sh`, modeled on `test-client-core.sh`'s boot pattern (mock-server on a free port, `BOARD_API_URL` pointed at it, `BOARD_CREDENTIALS_FILE` pointing at a temp creds file — copy the exact harness lines from `test-client-core.sh`, which is the reference for env setup, port pick, server spawn/kill, and the `fail()` helper). Fixtures and drills, all driven through `python3 -c 'import _board_api as A; ...'` with `PYTHONPATH=skills/issue-tracker/scripts`:

Fixture file (one JSON array; note the QUEUE of `once` entries per path prefix — the mock serves them in order):

```json
[
 {"method":"GET","path":"/tickets/7","status":200,"once":true,
  "body":{"id":7,"title":"t7","category":"work","state":"in-progress","priority":"P1",
          "owner_run":null,"parent":null,"plan":null,"pr_url":null,"branch":null,
          "note":null,"blocked_by":[],"relates":[]}},
 {"method":"GET","path":"/tickets/404000","status":404,"once":true,
  "body":{"error":{"code":"not-found","message":"no such ticket: 404000"}}},

 {"method":"GET","path":"/tickets?limit=200&cursor=CURSOR-2","status":200,"once":true,
  "body":{"items":[{"id":5,"state":"done","title":"e","priority":"P2"}],"next":null,"as_of":44}},
 {"method":"GET","path":"/tickets?limit=200&cursor=CURSOR-1","status":200,"once":true,
  "body":{"items":[{"id":3,"state":"parked","title":"c","priority":"P1"},
                    {"id":4,"state":"in-progress","title":"d","priority":"P1"}],
          "next":"CURSOR-2","as_of":44}},
 {"method":"GET","path":"/tickets?limit=200","status":200,"once":true,
  "body":{"items":[{"id":1,"state":"in-progress","title":"a","priority":"P0"},
                    {"id":2,"state":"in-progress","title":"b","priority":"P0"},
                    {"id":3,"state":"parked","title":"c-early","priority":"P1"}],
          "next":"CURSOR-1","as_of":44}},

 {"method":"GET","path":"/queue/decisions?limit=200&cursor=QC-1","status":200,"once":true,
  "body":{"items":[{"ticket_id":9,"correlation_id":"cid-b","species":"board","state":"parked","question":{"note":"q2"}}],
          "next":null,"as_of":44}},
 {"method":"GET","path":"/queue/decisions?limit=200","status":200,"once":true,
  "body":{"items":[{"ticket_id":8,"correlation_id":"cid-a","species":"board","state":"parked","question":{"note":"q1"}}],
          "next":"QC-1","as_of":44}}
]
```

IMPORTANT mock quirk: the mock matches `self.path.startswith(f["path"])`, so the `cursor=`-bearing entries must be listed BEFORE the bare `/tickets?limit=200` entry (a bare-prefix entry listed first would swallow the cursor requests). Keep the order above. Simplest discipline: give each drill group its OWN fixture world (fresh fixtures.json + server, as test-answer.sh does per scenario) rather than one shared world — `once` consumption across drills otherwise couples drill order to fixture order.

Drills (each a `python3` invocation whose stdout the shell asserts; follow the file's fail-fast style):
1. `A.ticket(7)` → dict with `id == 7`.
2. `A.ticket(404000)` after drill 1 (surface NOT yet proven — no envelope read has run; the 404 must trigger the probe): add a probe fixture `{"method":"GET","path":"/tickets?limit=1","status":200,"once":true,"body":{"items":[],"next":null,"as_of":44}}` and assert the result is `None` AND the `.log` shows the probe request happened.
3. Rollback guard: a SECOND mock world (fresh fixtures file) where `/tickets/9` answers route-style `{"error":{"code":"not-found","message":"unknown route"}}` and `/tickets?limit=1` answers a BARE ARRAY `[]` (status 200) — `A.ticket(9)` must die (`SystemExit`), stderr naming the pre-read-surface server; assert exit code 1 and the message.
4. `A.tickets_all()` on the 3-page fixture: returns exactly ids `[1,2,3,4,5]` (5 rows — the duplicate id 3 collapsed), and the id-3 row's title is `"c"` (the LATER page's data won). Assert from the `.log` that request 2 carried `cursor=CURSOR-1` and request 3 `cursor=CURSOR-2` VERBATIM.
5. Mid-walk failure, both flavors, each proving death-not-partial (the drill's python prints only on success):
   (a) REFUSAL mid-walk: page 1 answers `next:"CURSOR-X"` and no fixture matches the cursor request (the mock answers a plain 404) — `tickets_all()` dies (refusals are never retried).
   (b) TRANSPORT loss mid-walk: extend `mock-server.py` with a disconnect fixture — in `_handle`, before the normal matching, `if f.get("disconnect"): f["used"]=True; self.wfile.close(); return` (match it like any entry, `once` respected) — page 1 normal, the cursor request hits `{"method":"GET","path":"/tickets?limit=200&cursor=CURSOR-X","disconnect":true,"once":true}` THREE queued copies; `tickets_all()` dies after the transport retries, and the `.log` shows 1 + 3 requests (page 1, then three attempts on page 2).
5b. Exact-full final page: a single-page world whose one envelope carries `next: null` with a NON-EMPTY items list — `tickets_all()` returns exactly those rows (pins that null-next on a full page is a legal, complete answer — the server's exact-full contract).
5c. Malformed envelope: a world where page 1 is `{"items":[…]}` with NO `next` key — `tickets_all()` must DIE, not answer the one page (missing-next masquerading as null-next is the partial-board bug).
5d. Empty promoted filter refused server-side: `/tickets?limit=200&states=` answering the contract 400 `{"error":{"code":"invalid-argument",…}}` — `tickets_all(states="")` never sends it (empty states falls through to no filter client-side: assert from the `.log` the request had no `states=`), so instead drive `request("GET", "/tickets?limit=200&states=", principal=...)` raw and assert the die carries `invalid-argument` (pins the server refusal shape our fixtures encode).
6. `A.tickets_by_ids([7,8,9])` against a fixture `{"method":"GET","path":"/tickets?limit=200&ids=7,8,9","status":200,...,"body":{"items":[{"id":7,...},{"id":9,...}],"next":null,"as_of":44}}` (the implementation sends `limit=` BEFORE `ids=` — the fixture path must be a prefix of the real request) → returns keys `{7, 9}` only; absent 8 is an absent key. Chunking: `A.tickets_by_ids(range(1, 402))` must issue 3 requests (assert from `.log`: `ids=1,…,200`, `ids=201,…,400`, `ids=401`) — fixtures can answer empty item lists.
7. `A.queue_decisions_all()` on the 2-page queue fixture → both `correlation_id`s present, order `["cid-a","cid-b"]`.
8. Bare-array walk refusal: `tickets_all()` against a world where `/tickets?limit=200` answers a bare `[]` → dies naming the missing envelope.

- [ ] **Step 2: Run to verify failure.** `bash tests/claude-code/board-api/test-paged-reads.sh` → FAIL (AttributeError: module has no attribute 'ticket' or similar).

- [ ] **Step 3: Implement in `_board_api.py`.**

3a. `request()` gains `absent=()` — insert between the `obsolete_codes` check and the die in the HTTPError branch:

```python
            if code in obsolete_codes:
                raise ClaimObsolete(code, message) from None
            if code in absent:
                return None
```

and add `absent=()` to the signature after `obsolete_codes=()`.

3b. New section after `queue_decisions()`:

```python
# ---- paged read surface (spec: board-client-paged-reads v1.1) --------------

_PAGE_LIMIT = 200   # explicit limit= is the envelope opt-in
_MAX_IDS = 200      # documented ids= cap (arkho API.md §1)
_SURFACE = {"proven": False}   # per-process: has any envelope read succeeded?


def _envelope(payload, path):
    """A paged read must answer the COMPLETE envelope. A bare array means
    the server predates the read surface; a dict missing `next` (or carrying
    a wrong-typed member) is a malformed or version-skewed page — and
    treating a MISSING `next` like the contract's `next: null` would end the
    walk early and hand the caller a partial board as if complete. Strict or
    dead: no partial result may escape."""
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("items"), list)
            or "next" not in payload
            or not (payload["next"] is None or isinstance(payload["next"], str))
            or not isinstance(payload.get("as_of"), int)):
        die("GET %s answered no complete paged envelope "
            "({items, next, as_of}) — a pre-read-surface or malformed "
            "server; refusing to guess" % path)
    _SURFACE["proven"] = True
    return payload


def _walk(base, principal):
    """Yield every row of a complete cursor walk. The `next` token is passed
    back VERBATIM. Never yields from a walk that cannot finish: a failed page
    dies inside request(), so consumers that materialize (all callers do)
    never observe a partial board."""
    cursor = None
    while True:
        path = base + ("&cursor=%s" % cursor if cursor else "")
        page = _envelope(request("GET", path, principal=principal), path)
        for row in page["items"]:
            yield row
        cursor = page["next"]   # _envelope proved the key present
        if cursor is None:
            return


def ticket(tid, principal="human"):
    """GET /tickets/{id}. None = the ticket does not exist, and that answer
    is AUTHORITATIVE (action-grade) — unlike walk absence, which is
    report-grade (spec § Helper primitives). Rollback guard: route-level and
    row-level 404 share one stable code, so an unproven process probes the
    paged surface once before trusting a 404 as a real absence."""
    out = request("GET", "/tickets/%s" % int(tid), principal=principal,
                  absent=("not-found",))
    if out is None and not _SURFACE["proven"]:
        probe = request("GET", "/tickets?limit=1", principal=principal)
        if not isinstance(probe, dict) or "items" not in probe:
            die("GET /tickets/%s answered not-found, and the server serves "
                "no paged surface — this is a pre-read-surface server "
                "(route-level 404), not a missing ticket" % int(tid))
        _SURFACE["proven"] = True
    if out is not None:
        _SURFACE["proven"] = True
    return out


def tickets_by_ids(ids, principal="human"):
    """ids= batch read, chunked at the documented cap. Returns {int_id: row}.
    An id absent from the completed result is authoritatively absent — a
    targeted read, not a walk. (The board has no delete path today, so an
    absent id here means the id never named a ticket.)"""
    ids = [int(i) for i in ids]
    out = {}
    for i in range(0, len(ids), _MAX_IDS):
        chunk = ids[i:i + _MAX_IDS]
        base = "/tickets?limit=%d&ids=%s" % (
            _PAGE_LIMIT, ",".join(str(c) for c in chunk))
        for row in _walk(base, principal):
            out[int(row["id"])] = row
    return out


def tickets_all(states=None, principal="human"):
    """Complete cursor walk of /tickets. REPORT-grade completeness: contains
    every row whose sort position was stable while the walk ran; a row
    reprioritized behind an already-passed cursor mid-walk is missing from
    every page. Absence that drives an ACTION needs ticket() instead.
    Dedupe: a moved row can also be re-served — later data wins, first-seen
    position kept (dict overwrite)."""
    base = "/tickets?limit=%d" % _PAGE_LIMIT
    if states:
        base += "&states=%s" % states
    seen = {}
    for row in _walk(base, principal):
        seen[int(row["id"])] = row
    return list(seen.values())


def queue_decisions_all():
    """Complete cursor walk of /queue/decisions. Identity is correlation_id
    (queue rows carry no `id`); the keyset (raised_at, correlation_id) is
    immutable so re-serves are impossible — no dedupe. Walk absence is
    report-grade here too: a park COMMITTING during the walk can land behind
    the cursor — action-grade absence is a second walk started after the
    first finished (board-answer's retry)."""
    return list(_walk("/queue/decisions?limit=%d" % _PAGE_LIMIT, "human"))
```

- [ ] **Step 4: Register the new file in the full-suite runner.** `tests/claude-code/run-skill-tests.sh` runs an EXPLICIT `tests=(...)` array (~line 78) — an unregistered file is silently skipped by every later "full suite green" gate. Add `"board-api/test-paged-reads.sh"` to the array beside the other board-api entries.

- [ ] **Step 5: Run to verify pass.** `bash tests/claude-code/board-api/test-paged-reads.sh` → PASS. Also `bash tests/claude-code/board-api/test-client-core.sh` → still PASS (request() signature growth is additive). Confirm the runner picks the new file up: `bash tests/claude-code/run-skill-tests.sh 2>&1 | grep paged-reads` shows it executing.

- [ ] **Step 6: Commit.**
```bash
git add skills/issue-tracker/scripts/_board_api.py tests/claude-code/board-api/test-paged-reads.sh tests/claude-code/board-api/mock-server.py tests/claude-code/run-skill-tests.sh
git commit -m "feat(board-api): paged read primitives — walks, by-id, ids batch"
```

---

### Task 2: Sweep migration — _check_lift, _escalate, flat-route cap comments

**Files:**
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (`_check_lift` ~740-775; `_escalate` ~1507-1580; comments at `_unrelayed_dump` ~585, `_fold_answers` ~780-800, `phase_resume` ~1605)
- Test: whichever sweep unit files stub these reads — run `bash tests/claude-code/board-api/test-sweep-resume.sh` and `bash tests/claude-code/board-api/test-sweep-renew-relay.sh` first to find the fixtures (any `/tickets` GET fixture serving a bare array to a migrated path must become an envelope or a by-id/ids fixture).

**Interfaces:**
- Consumes: `A.tickets_by_ids(ids, principal="automation")`, `A.ticket(tid, principal="automation")`, `A.tickets_all(principal="automation")` from Task 1.

- [ ] **Step 1: Migrate `_check_lift`.** Replace the whole-board map read (`rows = {str(t["id"]): t["state"] for t in A.tickets(principal="automation")}` and its two lookups) with:

```python
rows = A.tickets_by_ids([rec["ticket"], rec["env_issue"]],
                        principal="automation")
row = rows.get(int(rec["ticket"]))
cur = row["state"] if row else None
moved = cur is not None and cur != rec["state"]
env_row = rows.get(int(rec["env_issue"]))
env = env_row["state"] if env_row else None
closed = env in ("done", "wontfix")
```

Rewrite the big `AN ABSENT ROW IS NOT A STATE` comment (keep the heading line) to say: this is now a TARGETED `ids=` read — absence in a completed answer is authoritative, not truncation. The conservative rule stands anyway: the board has no delete path, so an absent id here names a record pointing at a ticket that never existed (registry corruption, a foreign board) — keep waiting rather than lift, exactly as before. The failure mode the old comment feared (a short read lifting every suppression) is now structurally impossible: `tickets_by_ids` either completes or dies.

- [ ] **Step 2: Migrate `_escalate`'s two reads.** The state lookup heredoc becomes:

```python
import os
import _board_api as A
row = A.ticket(os.environ["T_TID"], principal="automation")
print(row["state"] if row else "")
```

(The shell's `[ -n "$state" ]` deferred-escalation contract is unchanged — but update its comment: the empty answer is now an authoritative not-found, not a maybe-truncated listing; deferral is still right because a suppression record needs a state it can name.)

The duplicate-recovery listing scan swaps one call: `A.tickets(principal="automation")` → `A.tickets_all(principal="automation")`, and its comment gains one clause: a transient mid-walk miss costs one extra escalation cycle and self-heals (the `raise` path already retries next tick) — spec § Semantics preservation.

- [ ] **Step 3: Cap-awareness comments (no code change).** At `_unrelayed_dump` and `_fold_answers` (`A.unrelayed()`) add: `GET /answers/unrelayed` is a FLAT route capped at 500 rows (arkho API.md §1 Boundary bounds); the drain loop re-reads until empty so a full page just costs another lap — but `_fold_answers` filters this capped read for ONE ticket, so >500 standing unrelayed answers could hide this ticket's replies until the backlog drains; paging it is an arkho follow-up if the board ever approaches the cap. At `phase_resume` (`A.needing_resume()`): flat cap 500 via `FEED_LIMIT` — a longer backlog is served next tick.

- [ ] **Step 4: Update sweep test fixtures and run.** Run both sweep unit files; every fixture that served `GET /tickets` a bare array to `_check_lift`/`_escalate` paths now serves the new shapes: `_check_lift` needs `{"method":"GET","path":"/tickets?limit=200&ids=","status":200,"body":{"items":[…the two rows…],"next":null,"as_of":N}}` (prefix-match makes the exact id list irrelevant — but assert the requested `ids=` from the `.log` where the test already reads it); `_escalate`'s state lookup needs `/tickets/<tid>` by-id fixtures; the duplicate-recovery scan needs an envelope on `/tickets?limit=200`. Expected: PASS.

- [ ] **Step 5: Full unit tier green, then commit.**
```bash
bash tests/claude-code/run-skill-tests.sh
git add -A skills/issue-tracker/scripts/_sweep_api.sh tests/claude-code/board-api/
git commit -m "feat(sweep): lift checks and escalation read the paged surface"
```

---

### Task 3: The single-row gates — board-show, board-transition --plan, board-list

**Files:**
- Modify: `skills/issue-tracker/scripts/board-show.sh` (~lines 24-40), `skills/issue-tracker/scripts/board-transition.sh` (~63-71), `skills/issue-tracker/scripts/board-list.sh` (~28-38)
- Test: `tests/claude-code/board-api/test-read-verbs.sh`, `test-register-transition.sh` (find the exact fixture entries by running them)

**Interfaces:** consumes `A.ticket`, `A.tickets_all` (Task 1 signatures).

- [ ] **Step 1: board-show.** Replace the `for t in A.tickets(...)` / `else: A.die(...)` scan with:

```python
t = A.ticket(tid, principal="automation")
if t is None:
    A.die("no ticket #%s" % tid)
```

(then the same header `print` on `t`, unindented out of the loop). The timeline read below it is unchanged; add its cap comment: the timeline is a FLAT read (no paged form; arkho API.md documents the routes' bounds) — fine at any plausible per-ticket event count today.

- [ ] **Step 2: board-transition `--plan` gate.** Replace the heredoc body:

```python
import os
import _board_api as A
row = A.ticket(os.environ["T_ID"])   # human-default principal preserved:
                                     # the gate reads as whoever transitions
print(row["state"] if row else "")
```

Both shell-side checks (`|| die …unreadable…` and `[ -n "$_cur" ] || die …not in a listing…`) keep working: `ticket()`'s 404→None prints `""` exactly like the old first-match miss; adjust the second die message to name the sharper evidence: `"--plan: #$tid does not exist on this board — the handoff edge cannot be checked"`.

- [ ] **Step 3: board-list.** `rows = A.tickets(state=… or None, principal="automation")` becomes `rows = A.tickets_all(states=os.environ["T_STATE"] or None, principal="automation")`. NOTE the parameter RENAME state→states and that the value passes through verbatim (a single state name is a one-element `states=` list server-side; the arg was always a single state here).

- [ ] **Step 4: Fixtures + run.** `test-read-verbs.sh` (show/list paths): show's fixture becomes a `/tickets/<id>` by-id entry (200 row / 404 not-found for the no-ticket drill); list's becomes an envelope on `/tickets?limit=200&states=…` — mind the mock's prefix-match ordering (cursor/specific entries above bare prefixes). `test-register-transition.sh`: the `--plan` gate fixture becomes by-id. Run both files → PASS.

- [ ] **Step 5: Commit.**
```bash
git add -A skills/issue-tracker/scripts tests/claude-code/board-api/
git commit -m "feat(verbs): show and the plan gate read by id; list walks states"
```

---

### Task 4: The completeness reports — board-lint, board-reconcile, board-map

**Files:**
- Modify: `skills/issue-tracker/scripts/board-lint.sh` (~50-80), `skills/issue-tracker/scripts/board-reconcile.sh` (~29-46), `skills/issue-tracker/scripts/board-map.sh` (`api_snapshot`, ~124-135)
- Test: `tests/claude-code/board-api/test-read-verbs.sh` (or wherever these three stub `/tickets` — run to find)

**Interfaces:** consumes `A.tickets_all`, `A.queue_decisions_all`, `A.ticket`.

- [ ] **Step 1: board-lint — walk + the absence-confirm rule (spec § Semantics preservation).** Replace the `open_ids` set with a state map plus an action-grade fallback:

```python
walked = {int(t["id"]): t["state"]
          for t in A.tickets_all(principal="automation")}

def board_state(tid_int):
    """Walk absence is report-grade; a retire recommendation is an ACTION.
    A ticket missing from the walk (a concurrent reprioritization can hide
    a row from every page) is re-read by id — 404 is the authoritative
    absence the recommendation may stand on."""
    if tid_int in walked:
        return walked[tid_int]
    row = A.ticket(tid_int, principal="automation")
    return row["state"] if row else None
```

and where the loop tested `int(tid) not in open_ids`, it now computes `st = board_state(int(tid))` and fails the daemon only when `st is None or st in ("done", "wontfix")` — same recommendation text as today. (Keep the `int()` comment; it still earns its place.)

- [ ] **Step 2: board-reconcile.** `A.queue_decisions()` → `A.queue_decisions_all()`; the dispatchables loop becomes

```python
for t in A.tickets_all(states="ready-for-architect,ready-for-implementer",
                       principal="automation"):
    if not t.get("owner_run"):
```

with a one-line comment: `owner_run` filters by id only server-side — "unowned" stays a client-side predicate. `A.needing_resume()` keeps its flat read + gains the 500-cap comment (same wording as Task 2 Step 3).

- [ ] **Step 3: board-map.** `rows = A.tickets(principal="automation")` → `rows = A.tickets_all(principal="automation")`. `TOPOLOGY_PROJECTED` logic is untouched (it reasons over the materialized list). No other change.

- [ ] **Step 4: Fixtures + run.** Envelope fixtures for the three (lint's drill that exercises a daemon pointing at a missing ticket needs a by-id 404 fixture beside the walk envelope — assert from the `.log` that the confirm read actually fired). Run the touched test files → PASS.

- [ ] **Step 5: Commit.**
```bash
git add -A skills/issue-tracker/scripts tests/claude-code/board-api/
git commit -m "feat(reports): lint, reconcile and map walk the envelope; lint confirms absence by id"
```

---

### Task 5: board-answer — queue walk with the re-walk-once rule

**Files:**
- Modify: `skills/issue-tracker/scripts/board-answer.sh` (~67-83)
- Test: `tests/claude-code/board-api/test-answer.sh`

**Interfaces:** consumes `A.queue_decisions_all`.

- [ ] **Step 1: Migrate the cid lookup.** Replace the single `next((... for q in A.queue_decisions() ...))` with:

```python
def find_cid():
    return next((q["correlation_id"] for q in A.queue_decisions_all()
                 if str(q["ticket_id"]) == tid and q.get("species") == "board"),
                None)

cid = find_cid()
if cid is None:
    # A park COMMITTING while the walk ran is invisible to that walk (its
    # transaction-start raised_at can land behind an already-passed cursor).
    # A second walk, started after the first finished, must serve any park
    # committed before it began — that retry is the queue's action-grade
    # absence evidence (spec § Helper primitives). Still None after it, and
    # the refusal below is standing on ground as firm as the old whole read.
    cid = find_cid()
```

The `A.die(...)` refusal below is unchanged.

- [ ] **Step 2: The hide-a-row drill (codex-mandated, spec § Testing).** In `test-answer.sh`, add a fixture world where the FIRST queue walk hides the park and the SECOND serves it — with the mock's once-queue this is natural:

```json
[
 {"method":"GET","path":"/queue/decisions?limit=200","status":200,"once":true,
  "body":{"items":[{"ticket_id":99,"correlation_id":"cid-other","species":"board","state":"parked"}],"next":null,"as_of":10}},
 {"method":"GET","path":"/queue/decisions?limit=200","status":200,"once":true,
  "body":{"items":[{"ticket_id":99,"correlation_id":"cid-other","species":"board","state":"parked"},
                    {"ticket_id":12,"correlation_id":"cid-12","species":"board","state":"parked"}],"next":null,"as_of":11}},
 {"method":"POST","path":"/tickets/12/park-answer","status":200,"once":true,
  "body":{"ok":true,"returnedTo":"in-progress"}}
]
```

Drive `board-answer.sh 12 "the answer"` against it: expect success, and assert from the `.log` that TWO `GET /queue/decisions` requests ran before the POST, and that the POST body carries `"correlationId": "cid-12"`. Also keep/adjust the existing no-park refusal drill: it now needs TWO empty-queue fixtures (the retry reads twice before refusing) — assert both were consumed.

- [ ] **Step 3: Update the rest of `test-answer.sh`'s queue fixtures** to envelopes (every existing `GET /queue/decisions` entry serving a bare array). Run: `bash tests/claude-code/board-api/test-answer.sh` → PASS.

- [ ] **Step 4: Commit.**
```bash
git add -A skills/issue-tracker/scripts/board-answer.sh tests/claude-code/board-api/test-answer.sh
git commit -m "feat(answer): the cid lookup walks the queue and retries once before refusing"
```

---

### Task 6: Legacy removal + integration drill-lib by-id

**Files:**
- Modify: `skills/issue-tracker/scripts/_board_api.py` (delete `tickets()` ~line 239 and `queue_decisions()` ~line 250)
- Modify: `tests/claude-code/board-api/integration/drill-lib.sh` (`ticket_state()` ~189, `ticket_owner()` ~193)
- Test: full unit tier + integration tier

- [ ] **Step 1: Delete the legacy helpers.** Remove `tickets()` and `queue_decisions()` from `_board_api.py`. Then prove nothing calls them:
```bash
grep -rn 'A\.tickets(\|A\.queue_decisions(' skills/ && echo "CALLERS REMAIN — fix first" || echo clean
```
Expected: `clean`. (`tickets_all`/`tickets_by_ids`/`queue_decisions_all` don't match those patterns — the `(` pins the bare names.)

- [ ] **Step 2: drill-lib by-id.** `ticket_state()`/`ticket_owner()` (drill-lib.sh ~189-197) currently `GET /tickets` and filter one id in python with an `"(absent)"` fallback — the exact production hazard this epic removes. Their OUTPUT CONTRACTS are asserted across the integration suites and must be preserved to the byte: `ticket_state` prints the state or `(absent)`; `ticket_owner` prints `str(t["owner_run"])` — a null owner prints the Python string `None` (test-escalation.sh asserts on it), the field is `owner_run` (there is no `.owner`). Rewrite both on drill-lib's `api()` wrapper against `/tickets/$1`; `api()` exposes no HTTP status, so absence is detected from the STABLE error envelope: a body whose `error.code == "not-found"` prints `(absent)` (never parse `error.message` — messages are unstable by contract). E.g. for `ticket_state`:

```sh
ticket_state() { api automation GET "/tickets/$1" | python3 -c '
import json, sys
t = json.load(sys.stdin)
if isinstance(t, dict) and isinstance(t.get("error"), dict) \
        and t["error"].get("code") == "not-found":
    print("(absent)")
else:
    print(t["state"])'; }
```

(`ticket_owner` identical but printing `str(t["owner_run"])`.) CHECK FIRST that `api()` passes non-2xx bodies through rather than dying — if it dies on 404, thread a tolerant variant for these two helpers rather than weakening `api()` for every caller.

- [ ] **Step 3: Run the unit tier fully.** `bash tests/claude-code/run-skill-tests.sh` → green.

- [ ] **Step 4: Run the integration tier** against a local board (docker; `ARKHO_DIR="$HOME/Developer/GitHub/arkho"`, per `tests/claude-code/board-api/integration/` docs — NEVER a production URL/DSN): at minimum `test-harness-smoke.sh`, `test-protocol-walk.sh` (leans on `ticket_state`), and `test-escalation.sh` (asserts `ticket_owner`'s `None` rendering — the contract most at risk in Step 2). Expected: green. If the harness cannot boot in this environment, report the exact blocker in your task report instead of skipping silently.

- [ ] **Step 5: Commit.**
```bash
git add -A skills/issue-tracker/scripts/_board_api.py tests/claude-code/board-api/integration/drill-lib.sh
git commit -m "feat(board-api): the bare-array readers are gone; drills read by id"
```

---

### Task 7: Final verification — spec acceptance as written + version bump

**Files:** none (verification); Modify: version manifests via `scripts/bump-version.sh` only.

- [ ] **Step 1: Spec acceptance, item by item** (spec `## Acceptance`, v1.1 — run each, record output in your report):
1. `grep -rn 'A\.tickets(\|A\.queue_decisions(' skills/` → no hits; every `/tickets` read in `skills/issue-tracker/scripts/` is `ticket(`, `tickets_by_ids(`, or `tickets_all(`; every `/queue/decisions` read is `queue_decisions_all(`. The five flat-route sites (`unrelayed` ×2, `needing_resume` ×2, timeline) are the documented exceptions — verify each carries its cap comment.
2. board-show against the integration board: an existing id prints the header + timeline; a nonexistent id dies `no ticket #N` — and the drill-lib/`.log` evidence shows only by-id + timeline reads (no bare listing).
3. The mid-walk-failure unit drill (Task 1 drill 5) is green — a walk interrupted at page 2 dies with no partial observable.
4. `bash tests/claude-code/run-skill-tests.sh` fully green; integration suites from Task 6 green.
5. The arkho parent spec carries the sixteen-site Revision Note (v1.10 — already committed on arkho main as c11b079; verify it is there: `grep -n 'sixteen' "$HOME/Developer/GitHub/arkho/docs/specs/2026-08-18-a1-read-surface-design.md"`).

- [ ] **Step 2: Version bump.** The script takes an EXPLICIT version only (`Usage: bump-version.sh <new-version> | --check | --audit`). Read the current version from `.claude-plugin/plugin.json`, bump the MINOR (a feature release — e.g. 7.55.0 if current is 7.54.x; recompute from what main actually says at execution time), then:
```bash
scripts/bump-version.sh <X.Y.0>
scripts/bump-version.sh --check
```
Never hand-edit manifests (`.version-bump.json` lists them). Commit as the script directs.

- [ ] **Step 3: Report** — suite counts, acceptance walk results, and any spec drift you had to reconcile (flow it into the spec's Revision Notes rather than diverging silently).
