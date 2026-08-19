# Board Client Paged Reads — Migrating 16 Read Sites off Read-Whole (2026-08-18)

> **Program:** patch 2 of the read-surface program (arkho#10 / arkho PR #11,
> live on production 2026-08-18). Parent spec:
> `arkho/docs/specs/2026-08-18-a1-read-surface-design.md` (§ Migration — this
> is its "client follow-up" patch, the dp#51-consumption species).
> **Successor:** patch 3 (arkho retirement: bare-array removal + SECURITY
> DEFINER append) starts only after this patch has soaked — the live sweep and
> cron running clean for days proves no unmigrated consumer remains.

## Purpose

Every board read this plugin performs today is read-whole: fetch the entire
`GET /tickets` (or `/queue/decisions`) bare array, then filter client-side —
six sites fetch the whole board to resolve ONE ticket id. That posture is
what arkho's paged surface was built to replace, and it carries a live
hazard class: the moment the server pages (patch 3 makes paging the only
read), "absent from the response" stops meaning "absent from the board".
Four sites turn that absence into actions — a false daemon-retire
recommendation (`board-lint`), "no such ticket" (`board-show`), and two
read-before-write gates (`board-transition --plan`, `board-answer`) that
would refuse a legal human action over a missed page.

This patch migrates every production read onto the paged surface so that:

1. Single-row questions cost single-row reads (`GET /tickets/:id`, `ids=`),
   and absence in their answers is **authoritative** for the first time.
2. Whole-board consumers ride a **completed cursor walk** whose contract
   makes the hazard inexpressible: a walk either completes (absence is then
   meaningful) or raises — a partial result never escapes.
3. No production read site depends on the bare arrays, unblocking patch 3.

## The site map (measured 2026-08-18, corrects the parent's "nine" to 16)

All sixteen production read sites live in `skills/issue-tracker/scripts/`
and flow through ONE helper — `_board_api.py` (urllib, `_binding.sh`
resolves `BOARD_API_URL` + credentials) — with zero inline curl. Dispatch
(`implement-dispatch.sh`, `review-dispatch.sh`) performs zero reads;
`board-gc` and `B.snapshot()` are gh-substrate, out of scope.

**Migrating — single-row resolution (5 sites):**

| site | today | becomes |
|---|---|---|
| `_sweep_api.sh` `_check_lift` | whole `/tickets` → `{id: state}` map, looks up 2 ids | `tickets_by_ids([tid, env_id])` |
| `_sweep_api.sh` `_escalate` state lookup | whole `/tickets` → first match by id | `ticket(tid)` |
| `board-show.sh` | whole `/tickets` → scan for one id, absent ⇒ die "no ticket" | `ticket(tid)`; 404 ⇒ same die, now authoritative |
| `board-transition.sh` `--plan` gate | whole `/tickets` (human principal default — preserved) → first match | `ticket(tid)`; 404 ⇒ same refusal |
| `_sweep_api.sh` `_escalate` duplicate recovery | whole `/tickets` → client-side **title** scan | `tickets_all()` full walk + client-side match (title is not a server predicate; category is demoted, not promoted) |

**Migrating — completeness reads (6 sites):**

| site | today | becomes |
|---|---|---|
| `board-map.sh` `api_snapshot` | whole `/tickets` → full graph render | `tickets_all()` walk |
| `board-lint.sh` | whole `/tickets` → open-id set; absent daemon ticket ⇒ FAIL/retire | `tickets_all()` walk + **absence-confirm rule**: retire recommendation only after `ticket(tid)` answers 404 |
| `board-reconcile.sh` dispatchables | whole `/tickets` → state/owner filter | `tickets_all(states='ready-for-architect,ready-for-implementer')` + client-side `owner_run is null` filter (null is not a server predicate) |
| `board-reconcile.sh` queue | whole `/queue/decisions` | `queue_decisions_all()` walk |
| `board-list.sh` | `/tickets?state=<arg>` bare | `tickets_all(states=<arg>)` (the promoted plural) |
| `board-answer.sh` cid lookup | whole `/queue/decisions` → first match | `queue_decisions_all()` walk + same filter; **on miss, one re-walk before refusing** (a park committing mid-walk is invisible to that walk; the retry, starting after it, must serve it) |

**Not migrating — no paged form exists server-side (5 sites, decision):**
`_sweep_api.sh` `_unrelayed_dump` + `_fold_answers` (`GET /answers/unrelayed`,
500 flat cap), `_sweep_api.sh` `phase_resume` + `board-reconcile.sh`
(`GET /runs/needing-resume`, 500 via FEED_LIMIT), `board-show.sh` timeline
(`GET /tickets/:id/timeline`). Each gains a cap-awareness comment naming the
documented bound (`arkho API.md` §1); `_fold_answers` — the one site that
filters the capped response for a single ticket — states explicitly that
>500 standing unrelayed answers would drop silently, and that the cap is an
arkho follow-up if the board ever approaches it. `GET /events` is also out:
patch 2 is a mechanical read migration, not a sweep re-architecture (grill
decision; the feed waits for a consumer that needs it, e.g. A3's UI).

## Design

### Helper primitives (`_board_api.py`)

Three additions beside the existing `tickets()`/`queue_decisions()` (which
remain until every caller is off them, then are deleted in this same patch):

- `ticket(tid, principal=...)` → `GET /tickets/{tid}`. `404 not-found`
  returns `None`; callers map it to their existing absent-handling. Any
  other refusal dies exactly as `request()` does today. **Rollback guard:**
  the server answers the same stable `not-found` code for a missing ticket
  and for an unknown ROUTE, so against a pre-read-surface server (an arkho
  rollback) every by-id read would masquerade as a missing ticket — lint
  would retire every daemon. On the first 404 in a process the helper
  probes once (`GET /tickets?limit=1`): an `{items, next, as_of}` envelope
  proves the paged surface exists — and the by-id read is then RE-ISSUED,
  because the probe dates the surface and not the answer that preceded it
  (a row rescues the 404; a second 404 is the authoritative one). A bare
  array, or any other incomplete envelope, means the server predates the
  surface and the helper dies naming that, never returning `None`. The
  probe result is cached per process, and the re-ask rides with it.
- `tickets_by_ids(ids, principal=...)` → `GET /tickets?ids=` in chunks of
  ≤200 (the documented cap), concatenated. An id absent from a completed
  response is authoritatively absent (the filter answers found rows; it
  does not 404 on a missing id).
- `tickets_all(states=None, principal=...)` and `queue_decisions_all()` →
  cursor walks over the paged envelope (`limit=200` explicit — the opt-in),
  following `next` until `null` and concatenating `items`. The ticket walk
  **deduplicates by `id`, keeping the later occurrence** (a keyset walk can
  re-serve a row whose priority moved mid-walk). The queue walk needs no
  dedupe: its keyset `(raised_at, correlation_id)` is immutable end to end,
  so a row can never move between pages — and queue rows carry no `id` at
  all; their identity is `correlation_id`. THE CONTRACT, in two halves:
  (1) *no partial results* — the walk returns only when the final page
  answered `next: null`; any page failure raises after `request()`'s
  existing per-page retries (3×2s on transport errors). (2) *walk absence
  is report-grade, not action-grade* — a completed walk contains every row
  whose sort position was stable while it ran, but a row whose keyset
  position moved (or was committed) behind an already-passed cursor during
  the walk is silently missing from every page: a mid-walk reprioritization
  hides a ticket, and a park transaction's start-time `raised_at` can land
  behind the queue cursor. A walk therefore proves completeness only as of
  a quiet board; absence that drives an ACTION needs stronger evidence —
  a targeted `ticket(tid)` read (its 404 is authoritative), or for the
  queue a **second walk started after the first finished** (misses only
  afflict writes concurrent with a walk, so any row committed before the
  retry began is guaranteed served).

### Semantics preservation

Every site keeps its current absent-behavior (defer, die, skip) — what
changes is the evidence: "absent from the whole read" becomes "absent from
a completed walk" or "404 from a targeted read". `_check_lift`'s recorded
conservatism ("AN ABSENT ROW IS NOT A STATE") is preserved for transport
failures — the sweep tick fails as today — while a clean `ids=` response's
absence becomes authoritative, which is strictly better evidence than the
whole-read it replaces. Two sites gain a deliberate confirm step because their
walk-absence triggers an action rather than a report line: board-lint's
absence-confirm rule (a retire recommendation stands on either grade of
authoritative evidence — the walk SERVING the ticket closed, or, for a row no
page carried, `ticket(tid)` answering 404; what it may never stand on is
walk-absence alone, because the targeted read outranks the walk) and
board-answer's re-walk-once rule (above). Report-only walk consumers (map, reconcile,
list) accept the transient: a row hidden by a concurrent move is re-read
on the next invocation. The escalate title-scan site self-heals the same
way — a transient miss costs one extra escalation cycle, and the
suppression it failed to write is retried on the next.

### Error surface

No new error taxonomy: `request()`'s existing behavior (transport retry
then die; HTTP refusal dies with the contract code) applies per page.
`invalid-cursor` 400 cannot occur in practice (the helper only ever sends
back tokens the server issued) and is not caught specially — a die with the
server's code is the correct surface for it.

### Testing

- **Unit (fixture fake server):** envelope fixtures captured from the LOCAL
  board service's raw output per the mock-fidelity rule — awkward cases
  included: exact-full final page (`next: null` with a full page), cursor
  round-trip, multi-page walk, `not-found` by-id, empty `states=` → 400.
  New drills: a 3-page walk equals the whole read; a mid-walk transport
  failure raises with no partial result observable; a cross-page duplicate
  id dedupes to the later row; `tickets_by_ids` chunks at >200 ids; a
  scripted walk that HIDES a row (present in the board, absent from every
  served page) drives board-answer's retry — the second scripted walk
  serves it and the answer posts; by-id 404 against a bare-array (pre-
  read-surface) fake dies naming the rollback, and against an envelope
  fake returns `None`; a multi-page multi-question queue walk preserves
  every distinct `correlation_id`.
- **Integration (docker board, `tests/claude-code/board-api/`):** existing
  suites keep passing; `drill-lib.sh`'s `ticket_state()`/`ticket_owner()`
  move to by-id so the test substrate exercises the same reads production
  does.
- **Live:** after merge, one observed sweep tick on production starts the
  soak that gates patch 3.

## Acceptance

1. `grep` proves no production script calls the bare list forms: every
   `/tickets` read is by-id, `ids=`, or a cursor walk; every
   `/queue/decisions` read is a walk. (The five flat-route sites are the
   documented exceptions. So is the helper's own one-shot rollback probe,
   `GET /tickets?limit=1` at the choke point — a fourth read kind, on the
   paged surface and not a bare listing, spent at most once per process; item
   2 names it too.)
2. `board-show <existing-id>` and `board-show <nonexistent-id>` answer
   correctly and neither performs a bare listing: the ticket comes from
   `GET /tickets/{id}`, its history from the documented flat timeline route,
   and a 404 on a not-yet-proven server spends one `GET /tickets?limit=1`
   rollback probe (verified against the docker board) and then one re-issued
   `GET /tickets/{id}` — the probe dates the surface, not the answer that
   preceded it (§ Decision Log 2026-08-19; pinned by unit drill).
3. A walk interrupted at page 2 (fixture server kills the connection)
   surfaces as a failure — no caller observes a partial board.
4. The unit and integration suites are green; the plugin version is bumped
   via `scripts/bump-version.sh`.
5. The arkho parent spec carries a Revision Note correcting "nine read
   sites" to sixteen with this spec's path.

## Rollout

The server keeps its bare arms until patch 3, so mixed plugin versions are
risk-free during rollout. Patch 3's gate: days of clean live sweep/cron
operation after this patch ships (grill decision — soak, then retire).

## Decision Log

- **Feed (`GET /events`) excluded** (grill, 2026-08-18): patch 2 swaps read
  calls; adopting the feed means re-architecting the sweep into a replica —
  rejected as scope creep with no present consumer need.
- **Flat routes stay unmigrated** (grill): `/answers/unrelayed`,
  `/runs/needing-resume`, timeline have no paged form; adding one is arkho
  work. Rejected: filing arkho paging issues now (nothing approaches the
  caps), including server work in this epic (cross-repo scope).
- **Soak before patch 3** (grill): rejected immediate back-to-back
  retirement — production proving no unmigrated consumer remains is cheap
  and the retirement cutover is irreversible for stray consumers.
- **Walk-completes-or-raises in the helper** (design): rejected returning
  `(rows, complete_flag)` — a flag every caller must check is the hazard
  restated; an exception is unignorable.
- **Absence-confirm rule for board-lint only** (design): rejected applying
  it to every walk consumer — report-only sites lose nothing to a missed
  row that the next invocation re-reads, and the confirm read costs a
  round-trip; lint is the sole site where walk-absence drives an action.
- **Dedupe keeps the later occurrence** (design): later page = later read;
  rejected first-occurrence (would prefer staler data on the one row known
  to have moved).
- **by-id 404 returns None from the helper** (design): rejected raising a
  typed exception — every caller has an existing absent-branch; None maps
  onto it with the least ceremony.
- **Walk absence demoted to report-grade** (codex spec review, adopted):
  the v1 contract claimed a completed walk proves absence; a mid-walk
  reprioritization (or a park committing behind the cursor) hides a row
  from EVERY page of a completed walk. Rejected keeping the claim with
  dedupe alone — dedupe only cures the duplicate-producing direction.
  Action-grade absence now requires by-id (tickets) or re-walk-once
  (queue).
- **Queue walk carries no dedupe** (codex spec review, adopted): queue rows
  have no `id` — identity is `correlation_id` — and the immutable keyset
  makes duplicates impossible; a literal by-id dedupe would have crashed on
  any nonempty queue.
- **404 rollback guard** (codex spec review, adopted): route-level and
  row-level `not-found` share one stable code, and messages are unstable by
  contract; a server-side capability endpoint was rejected as cross-repo
  scope — the one-probe client guard closes the same hole.
- **The probe dates the surface, not the 404 before it** (codex whole-branch
  review round 3, 2026-08-19 — adopted in part): a 404 answered BEFORE the
  proof is not evidence of absence. During a service version transition the
  404 and the probe can be served by different instances — the old one
  without the read surface, the new one with it — and a probe read as proof
  would then authenticate a route-level 404 as a missing ticket, which is
  the exact hazard the guard exists for. Adopted: once the probe validates,
  `ticket()` re-issues the by-id read and returns THAT answer — a row
  rescues the false absence, and a second 404, now observed with the surface
  proven in-process, is the authoritative one. Rejected, from the same
  finding: re-probing on every 404, or invalidating an earlier in-process
  proof when a later 404 arrives. A client process here is one script
  invocation living seconds, and the deployed board is a single instance, so
  a mixed-fleet window is a one-off deploy race rather than steady state;
  meanwhile every consumer of a residual false absence is loud or
  recommendation-only — `board-show` and `board-transition` die visibly and
  are rerunnable, `board-lint` emits a recommendation a human executes, and
  the sweep's deferred contract tolerates an empty answer. Per-404 re-probing
  would double the round trips on every drifted-fleet lint run to close a
  window nothing silently consumes.
- **Controlled track** (grill): live production sweep + per-site semantics
  decisions warranted the full spec → plan → reviewed-SDD pipeline.

## Surprises & Discoveries

- The parent spec's "nine read sites" was an undercount: sixteen, measured
  2026-08-18 (the estimate predated `_sweep_api.sh`'s growth). Six of the
  nine `/tickets` calls are single-ticket lookups; two are read-before-write
  gates the parent's sketch did not name.
- Zero inline curl: every production read already flows through
  `_board_api.py`, so the migration has exactly one choke point — the
  helper's contract IS the epic.
- `category` is a demoted (bare-only) filter on the paged surface, so the
  one title-scan site cannot narrow server-side and keeps a full walk.
- `owner_run` filters by id only — "unowned" is not a server predicate —
  so the dispatchables read filters client-side atop a `states=` walk.

## Outcomes & Retrospective

Shipped 2026-08-19 as v7.55.0 on `board-client-paged-reads` (fork point
64967f79), 19 commits. Everything the purpose named is done: all sixteen read
sites are accounted for — eleven migrated onto the four paged helpers through
the `_board_api.py` choke point, five flat-route sites carry cap-awareness
comments naming their documented bounds — the legacy whole-board readers are
deleted with a clean caller grep, the integration drills read by id with their
output contracts preserved to the byte, and the acceptance section was walked
item by item with measured wire evidence (a logging proxy in front of a live
local board, not a re-reading of the code).

Review shape: seven task reviews (every one running a real mutation battery;
several vacuous-assertion classes were caught and fixed this way) plus four
codex whole-branch rounds. All four rounds' findings were the same family —
the walk contract's fail-closed edges against malformed or version-skewed
servers: a probe accepting a half envelope, an empty-string cursor looping the
walk, a repeated cursor looping it unboundedly, and a 404 classified by a probe
that dated the surface, not the 404. Each got a choke-point fix and a bounded
drill; round four was clean.

Lessons worth keeping: measured evidence beats read-through (the acceptance's
"only read" claim survived every reading and fell to the first wire capture);
`nt`-style negative assertions pass vacuously unless paired with a positive
from the same world; fail-closed contracts are only as strong as their
weakest shape-check, and adversarial cross-model review found a new hole per
round precisely there; `BOARD_BINDING` as an environment variable does not
override the binding file — a mis-bound probe briefly opened a real GitHub
issue (deleted within a minute, no residue; the probe was rebuilt against a
scratch repo with a stubbed `gh`).

Residue, all recorded: the accepted-Minor list and its rationale live in the
SDE ledger; two follow-up ticket candidates (the runner counting integration
exit-77 skips as failures, and the junk-ref-without---plan ValueError
asymmetry); the rollout's soak gate stands — patch 3 (arkho's bare-array
retirement) only after days of clean live operation on this client.

## Revision Notes

- 2026-08-19: `ticket()` re-issues the by-id read after a rollback probe
  validates and returns that second answer, so an authoritative `None` always
  rests on a 404 observed with the paged surface proven in-process (§ Decision
  Log, same date; § Helper primitives and § Acceptance item 2 now describe the
  re-ask). A behavior change, not a wording one — drilled in
  `test-paged-reads.sh`. No version change: the `ticket()` contract callers
  code against (`None` = absent, action-grade) is what it always was; what
  moved is the evidence the helper demands before it says `None`.
- 2026-08-19: § Acceptance item 2 claimed the paged surface was "the only
  read" `board-show` performs. The acceptance walk measured it and found
  three: the by-id read, the flat timeline route (§ site map's own
  documented exception), and — on a 404 from a server whose paged surface is
  not yet proven — the one-shot rollback probe. The claim that carries the
  design is the absence of a bare listing, so item 2 now names all three
  reads instead. No behavior change; the shipped code was already correct.
  Measurement method, on record so the inventory is reproducible: a logging
  reverse proxy in front of the harness board service, with every request the
  verb issued read off the proxy log rather than inferred from the source.
- 2026-08-19: § Acceptance item 1 said every `/tickets` read is by-id, `ids=`
  or a walk, which item 2 already contradicted by naming the rollback probe.
  Item 1 now names the probe as the fourth documented read kind. Wording
  alignment between two clauses about the same shipped behavior.
- 2026-08-19: § Acceptance item 4's "the unit and integration suites are
  green" is discharged as: every deterministic suite green, and the
  integration tier green separately with `ARKHO_DIR` set. Recorded because
  `tests/claude-code/run-skill-tests.sh` prints `STATUS: FAILED` on a machine
  with no `ARKHO_DIR` — measured 18 passed / 7 failed, and all seven
  "failures" are integration drills reporting the tier's own exit-77 skip
  gate (`drill-lib.sh`, introduced on main in d52eee66), which the runner
  counts as a nonzero exit like any other. `test-harness-smoke.sh` skips with
  its own inline gate and exits 0, which is why the count is seven and not
  eight. That accounting predates this branch — a runner follow-up
  candidate (teach it 77), not a defect of this work.
- 2026-08-19 (post-merge follow-up): the runner quirk above is resolved.
  `run-skill-tests.sh` now counts exit 77 as a SKIP (surfacing the gate's
  printed reason), and `test-harness-smoke.sh` propagates 77 instead of
  exiting 0 — the eight integration suites tally as Skipped on a machine
  without `ARKHO_DIR`, not seven failures and a phantom pass.
- 2026-08-19: § Semantics preservation now names both grades of retire
  evidence (the walk serving the ticket closed, OR a by-id 404) instead of
  reading as if only the 404 counted. Task 4's reviewer caught the divergence
  between this sentence and the plan's binding constraint; the plan text (and
  the shipped code, which follows it) governs. No version change — wording
  alignment, not a design change.
- 2026-08-18: v1.1, codex adversarial spec review (2 high, 1 medium — all
  adopted): the walk-completeness claim was demoted to report-grade with
  per-site action-grade evidence rules (by-id / re-walk-once); queue dedupe
  removed (no `id` field, immutable keyset); by-id 404 gained the
  pre-read-surface rollback probe. Acceptance and unit drills extended to
  pin all three.
- 2026-08-18: v1, authored from the patch-2 brainstorming round (2 grill
  rounds; design approved same day). Site map measured by exploration, not
  inherited from the parent's estimate.
