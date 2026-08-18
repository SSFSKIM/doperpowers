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
| `board-answer.sh` cid lookup | whole `/queue/decisions` → first match | `queue_decisions_all()` walk + same filter |

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
  other refusal dies exactly as `request()` does today.
- `tickets_by_ids(ids, principal=...)` → `GET /tickets?ids=` in chunks of
  ≤200 (the documented cap), concatenated. An id absent from a completed
  response is authoritatively absent (the filter answers found rows; it
  does not 404 on a missing id).
- `tickets_all(states=None, principal=...)` and `queue_decisions_all()` →
  cursor walks over the paged envelope (`limit=200` explicit — the opt-in),
  following `next` until `null`, concatenating `items`, **deduplicating by
  id keeping the later occurrence** (a keyset walk can re-serve a row whose
  priority moved mid-walk). THE CONTRACT: the walk returns only when the
  final page answered `next: null`; any page failure raises after
  `request()`'s existing per-page retries (3×2s on transport errors). A
  partial concatenation is never returned. This single property is what
  makes "absent from a paged response ≠ absent from the board" a hazard the
  call sites cannot re-introduce: absence is only observable in a value the
  helper has proven complete.

### Semantics preservation

Every site keeps its current absent-behavior (defer, die, skip) — what
changes is the evidence: "absent from the whole read" becomes "absent from
a completed walk" or "404 from a targeted read". `_check_lift`'s recorded
conservatism ("AN ABSENT ROW IS NOT A STATE") is preserved for transport
failures — the sweep tick fails as today — while a clean `ids=` response's
absence becomes authoritative, which is strictly better evidence than the
whole-read it replaces. The one deliberate behavior change is board-lint's
absence-confirm rule (above): it converts the last residual false-positive
path (a row moving mid-walk) into a targeted read, and is the only site
where walk-absence triggers an action rather than a report line.

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
  id dedupes to the later row; `tickets_by_ids` chunks at >200 ids.
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
   documented exceptions.)
2. `board-show <existing-id>` and `board-show <nonexistent-id>` answer
   correctly with the server's paged surface as the only read they perform
   (verified against the docker board by the integration drills).
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

Pending — written at finish.

## Revision Notes

- 2026-08-18: v1, authored from the patch-2 brainstorming round (2 grill
  rounds; design approved same day). Site map measured by exploration, not
  inherited from the parent's estimate.
