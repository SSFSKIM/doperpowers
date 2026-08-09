# A2: Plugin Board Adapter — Design

**Ticket:** [doperpowers#44](https://github.com/SSFSKIM/doperpowers/issues/44) ·
**Parent:** Arkho roadmap § A2
([SSFSKIM/arkho `docs/specs/2026-08-04-arkho-platform-roadmap.md` v1.2.1](https://github.com/SSFSKIM/arkho/blob/main/docs/specs/2026-08-04-arkho-platform-roadmap.md)) ·
**Track:** controlled (roadmap-pinned) · **Contracts:** X1 (consumer), X2
(run-bearer holder), X5 (owner), X6 (local-worker mechanics owner)

## Purpose

The substrate swap the E-cycle state machine was written to be neutral over:
the doperpowers issue-tracker toolkit and worker dispatch scripts speak the
Arkho board API instead of the gh CLI, as a **per-repo binding**. gh mode
remains a supported first-class substrate (X5 — consumer repos like
ida-solution never require a Postgres service). A worker's transcript must be
indistinguishable across bindings modulo transport: same scripts, same
arguments, same refusal vocabulary.

The counterparty is live: A1 (arkho#1, closed 2026-08-09) serves the full
worker protocol at `https://arkho-board-service.onrender.com`; the contract is
`board-service/API.md` in the arkho repo (18 routes, drill-pinned to source).
Operator credentials for a live drill live in `~/.arkho-board/secrets.env`.

## The structural premise

The two bindings have opposite thickness, and the design follows from
refusing to fight that:

- **gh mode is a thick client on a dumb store.** GitHub knows nothing;
  `_board.py`'s upper half (legality table, epic pulls, recomposition,
  eligibility) IS the state machine.
- **API mode is a thin client on a smart store.** A1 enforces legality,
  notes, PR gates, parks, pick order, birth classification, dedup, epic
  sweeps (reconciler), fences, and run scoping server-side.

So the adapter boundary is **verb-level**: each user-facing script keeps its
exact CLI and branches internally; in API mode the verb is a thin HTTP call
and `_board.py`'s state-machine half is never **exercised** — no legality
check, no mutation, no pick order runs client-side. The banned state is a
*divergent second client-side copy* of legality/pick-order, not the import
statement: a read verb that imports `_board` to reuse the one existing pure
derivation for display (`board-map.sh` calling `B.eligible` to label a node)
is the opposite of that hazard, since a re-implementation is exactly what
would drift. The X5 drift risk is fenced by the transcript-diff drill
(§ Testing) plus that single-source reuse, not by refusing to link the file.

## Design

### Binding resolution (`_lib.sh`)

One resolution step, run once per script invocation: read
`.doperpowers/board.json` at the consumer repo root.

```json
{ "binding": "api", "url": "https://arkho-board-service.onrender.com" }
```

- Present with `"binding": "api"` → `BOARD_BINDING=api`, `BOARD_API_URL`
  exported (env `BOARD_API_URL` overrides, for tests).
- Absent, or `"binding": "gh"` → `BOARD_BINDING=gh`; everything downstream
  behaves exactly as today. Existing consumer repos are untouched by default.
- Checked in deliberately: every worktree, worker, and dispatcher resolves
  the same binding, and the A5 flip becomes one atomic commit per repo.
- In API mode `gh` is not required and never invoked; the fail-loud
  dependency check becomes curl + binding file + resolvable credential.

### Credentials and principal resolution

Never checked in. Resolution lives in the shared client core so verb scripts
stay actor-blind:

1. **Run context wins:** `BOARD_RUN_TOKEN` set in env (injected by the
   dispatcher at spawn, alongside `BOARD_RUN_ID`, `BOARD_RUN_FENCE`,
   `BOARD_API_URL`) → speak as the run. Server-side `own-run` / `own-ticket`
   scoping and fence checks apply. **Resume rehydration:** `daemon-resume`
   forks a fresh process from the caller's environment, so every resume
   (relay, successor, inline) re-injects the `BOARD_RUN_*` set — sourced
   from the run's bearer stored in the daemon registry meta at bind time
   (local plaintext, file mode 0600; same exposure class as the session
   transcripts stored beside it, and the server holds only the hash).
2. **Operator context:** no run token → load
   `~/.arkho-board/<repo-slug>.env`, which carries `BOARD_AUTOMATION_TOKEN`
   (a `board.principal` of kind automation with `dispatch` + `sweep`
   capabilities) and `BOARD_HUMAN_TOKEN` (the human principal). Which token a
   script uses is fixed per script, never guessed: sweep/dispatch/relay verbs
   always automation; interactive verbs (hand-run transitions) default
   human. One scripted exception: `board-answer.sh` is dual-principal
   (§ Verb mapping) — human for the answer, automation for its inline
   relay leg.

### The API client core (`_board_api.py`)

A new sibling to `_board.py`, stdlib-only (`urllib`; curl in pure-shell
paths). It owns exactly four things:

- **Request assembly** — base URL + bearer + JSON body.
- **Principal resolution** — the precedence above.
- **Error mapping** — the API's error vocabulary (`illegal-transition`,
  `note-required`, `fence-mismatch`, `lost-race`, `nonce-consumed`,
  `stale-resume`, …) surfaced verbatim in `die` messages, so an API-mode
  refusal reads like the gh-mode guard that enforces the same rule.
- **Retry policy** — GETs and claim-family POSTs retry on transport failure
  (claims are nonce-idempotent by contract: a replay rotates the bearer and
  re-arms the lease — retrying is the designed path). Transitions and
  answers are never blind-retried: their 409s are answers, not failures.
  `lost-race`, `superseded`, `stale-resume` are outcomes — logged, not
  retried; the board moved, and re-reading is the next tick's job.

### Verb mapping

Each `board-*.sh` gets an API branch at the top; the gh path is untouched
below it.

| verb | API mode |
|---|---|
| `board-register.sh` | `POST /tickets` — lineage edges (`parent`/`spawnedBy`/`blockedBy`) ride the payload; birth classification, dedup, env-issue inversion, `repairPath` rules all server-side. Category map: `bug`/`enhancement` → `work`; `spike`/`env-issue` pass through. A park-state birth's `--note` (the question the human sees — gh mode requires it) has no API field: it is **prepended to `body`** as the opening line, and the contract-level fix (a question field rendered into the birth park) is a flow-back item on arkho#7. **Known divergence:** the API refuses `spike` born `ready-for-architect` (`409 illegal-birth`) while gh mode deliberately supports design-first spikes — the 409 is surfaced honestly, design-first spikes are gh-only until the flow-back ruling (§ Scope-outs) |
| `board-transition.sh` | `POST /tickets/:id/transition`; `fence` from `BOARD_RUN_FENCE` when the actor is a run; `pr`/`plan`/`branch` pass through. The script prints the **response's** `to` (and the `converged` flag), never the requested state — the server transmutes on convergence, and echoing the request would mislead the worker and break the transcript drill |
| `board-comment.sh` | **new verb, both modes** — gh: `gh issue comment`; API: `POST /tickets/:id/comment`. Default `kind: comment`; `--kind parent-impact\|closure-package\|parent-impact-consumed` with a typed `--body` JSON payload carries the E2 event ops (the comment route is their only API carrier; in gh mode these land as marker-prefixed comments). The worker protocols' raw `gh issue comment` call sites (implementing SKILL.md:82, architecting SKILL.md:56, reviewing-prs SKILL.md:277) are edited **once** to call this verb; after that substitution the prose is binding-neutral |
| `board-answer.sh` | `POST /tickets/:id/park-answer`, always naming `correlationId` from `GET /queue/decisions` (the contract's superseded-answer protection). Then runs the sweep's relay step inline once, so a hand-delivered answer resumes the worker immediately — the same blocking feel as gh mode. **Dual-principal by design** — the one scripted exception to fixed-token-per-script: the answer leg speaks human, the relay/ack leg speaks automation (`unrelayed`/`ack-answer` admit automation only) |
| `board-list.sh` / `board-show.sh` | `GET /tickets` (+ `GET /tickets/:id/timeline` for show). Human-facing dispatch-order ranking is rendered but informational — the server owns pick order |
| `board-map.sh` | a snapshot adapter feeds the same BOARD.html/BOARD.md renderer from `GET /tickets` + timelines; serve/hot-reload machinery unchanged |
| `board-reconcile.sh` | wake queue from `GET /queue/decisions`, orphans from `GET /runs/needing-resume`, dispatchables from `GET /tickets` |
| `board-lint.sh` | thin: the server enforces its own schema; API-mode lint checks only what the server cannot see — local registry↔board drift (bound runs whose daemon is gone; daemons bound to ended runs) |
| `board-bind.sh` | registry write as today, plus `POST /runs/:id/bind` with the local session locator |
| `board-edge.sh` / `board-priority.sh` / `board-relate.sh` | **fail loud** naming arkho#7 (§ Scope-outs) — never silent, never a gh fallback |
| `board-migrate-gh.sh` | gh-only by nature; refuses in API mode (import/cutover is A5's instrument) |

### Dispatch and the sweep — the four-phase tick

`board-sweep.sh` stays the one unattended tick (cron, ~5 min; no new
daemon). Its API branch, in order:

1. **Renew.** For each open run in the local daemon registry whose daemon is
   alive, `POST /runs/:id/renew` (15-minute default lease vs 5-minute tick =
   3× margin). Renewal is dispatch automation, never worker prose (X6).
   `409 run-ended` means the worker was reaped — route that run into the
   resume path, don't error. This phase also **repairs unconfirmed binds**:
   a registry run whose bind-confirmed flag is unset gets its
   `POST /runs/:id/bind` re-issued (a crash between resume and bind in
   phase 3 lands here next tick).
2. **Relay.** `GET /answers/unrelayed` → per answer: transcript-sentinel
   check → resume the bound session → `POST /answers/:id/ack`. Ack the page
   and read again to drain backlogs (500-row bound is contractual).
3. **Resume-first.** `GET /runs/needing-resume` → `POST /runs/claim-successor`
   (fresh nonce) → **persist the successor run id + session to the registry**
   → `daemon-resume` the predecessor's session with the successor's
   bearer/fence injected and any unrelayed answers for that ticket folded
   into the resume prompt (second relay vehicle, **same sentinel per answer
   id** — the sentinel is mandatory in every delivery vehicle) → ack those
   answers → `POST /runs/:id/bind` and set the registry's bind-confirmed
   flag. Crash analysis: before the registry persist, the successor claim's
   nonce replays next tick; between resume and ack, the folded answers are
   still unrelayed and phase 2's sentinel grep finds them delivered and
   acks; before bind, phase 1's bind repair finishes it. Resume-before-start
   bounds work in progress (roadmap obligation).
4. **Fresh claims, lane-disciplined.** `implement-dispatch.sh` claims
   `architect`, `implementer`, `spike`; `review-dispatch.sh` claims `qagent`;
   nobody claims `ops` (no plugin protocol runs that lane — lane discipline
   is exactly this line). **Cap semantics preserved:** the local dispatcher
   enforces its existing combined cap (implement + spike share
   `IMPLEMENT_MAX_CONCURRENT`) against its own registry **before** claiming,
   exactly as gh mode does; `laneCap` is additionally passed with the same
   value as a server-side belt (the server counts all dispatchers' open
   runs in the lane, so the belt is looser — the local check is what
   preserves single-host gh-mode concurrency). Each `POST /runs/claim`
   carries a fresh nonce. A yield spawns the worker via the same
   daemon-spawn ritual with run credentials in env and the claim's `body` —
   the assignment, by contract the only route a run has to its own ticket
   text — written into the bootstrap.

Triggered dispatch (`implement-dispatch.sh <n>`) is **gh-only**: the API
exposes no claim-by-ticket route (`claim-successor` serves reclaim markers,
not arbitrary targeting), so in API mode the `<n>` form fails loud naming
the gap — a targeted-claim route is a flow-back candidate recorded on
arkho#7. Hand-running any phase is legal — each mints fresh nonces, and a
persisted nonce is only ever replayed pre-spawn (see the nonce-lifecycle
entry in the Decision Log). The tick's phases are also individually
invokable for the drill.

### Relay idempotence — the transcript is the marker

The wake feed is level-triggered off durable state: an answer is served by
every `GET /answers/unrelayed` until acked (never lost), and the ack is
set-once idempotent. The client's one obligation is **never double-resume**
in the window between delivering to the session and committing the ack:

- The relay resume prompt opens with a fixed sentinel carrying the answer
  event id — `[board-relay answer:<answerEventId>]` — followed by **the same
  orientation preamble gh mode's relay carries** (re-state your gate verdict
  against the answers, or park fresh if they reshape the work's scope — X5:
  dropping it would change worker behavior across bindings) and the replies
  verbatim. The sentinel is mandatory in **every** delivery vehicle: the
  sweep's relay, phase 3's successor fold, and `board-answer.sh`'s inline
  run.
- Before resuming, the sweep greps the bound session's transcript (the
  registry knows its jsonl path) for the sentinel. Found → delivery already
  happened; skip to ack. Not found → resume, then ack.
- Crash analysis: before resume → no sentinel, still unrelayed, next tick
  retries. Between resume and ack → the sentinel is in the transcript
  (written by the same act that delivered the prompt); next tick skips the
  resume and acks. After ack → the feed no longer serves it.
- **The resume's wait is bounded** (`BOARD_RELAY_RESUME_TIMEOUT`, default 300
  → a `daemon-resume` watcher of ≤150 polls). `daemon-resume` otherwise
  blocks for `DAEMON_TIMEOUT/2` — hours at the 18000 default — while this
  tick holds the whole-tick lock, so one long worker turn would starve lease
  renewal past the 15-minute lease and A1 would reclaim runs that are alive.
  Bounding it costs nothing the delivery gate needs: `daemon-resume` advances
  the meta's `current` to the forked turn and injects the sentinel-bearing
  prompt **before** it blocks, so a timed-out resume exits nonzero, acks
  nothing, and lands on the row above — the next tick's sentinel grep finds
  the marker in the new transcript and acks **without re-delivering**. Only
  the ack is late; the answer is never lost and never doubled.

No new state file: the durable record of delivery is the delivery itself.

**Dead-session fallback:** the relay never acks-and-drops an undeliverable
answer. The sweep simply stops renewing the dead run's lease; A1's reclaim
ends the run and raises the resume marker; the successor claim becomes the
delivery vehicle (phase 3 folds unrelayed answers into the successor's
resume prompt, then acks). One relay mechanism, two vehicles.

### Dead-worker recovery policy

gh mode's sweep parks a thrice-failed worker `needs-human` — but in API mode
automation has **no transition authority** (the matrix admits transitions to
humans and runs only), and that constraint is obeyed, not worked around:

1. Resume-first with the predecessor's session (phase 3).
2. If `daemon-resume` fails, **fresh spawn on the same successor bearer** — a
   successor is a fresh run by contract; the session resume is an
   optimization, not the substance. The fresh-spawn bootstrap **directs the
   worker to read its own timeline before proceeding** (`board-show.sh` /
   the timeline read): the ticket's park/answer history — including answers
   already delivered to the dead session and acked — lives there, and the
   claim `body` alone would silently drop exactly the information the park
   existed to obtain.
3. Only when fresh spawns themselves keep dying (3 cycles, counted in the
   registry) does the sweep escalate: it **registers an env-issue ticket**
   (automation holds `register`; env-issues are born `needs-human`) naming
   the stuck ticket, and writes a **suppression record** to the registry —
   `{ticket id, board state at suppression, env-issue ticket id}`. While a
   suppression stands, phase 3 skips the ticket's resume entries; an
   ordinary claim (phase 4) cannot filter by ticket, so a claim that yields
   a suppressed ticket is immediately released (`POST /runs/:id/end`,
   reason `abandoned`) and that lane draws no further claims this tick.
   Suppression lifts when the ticket's board state no longer matches the
   recorded one (someone moved it) or the env-issue ticket closes — both
   checked each tick.

### Worker surface

The worker protocols (implementing / architecting / reviewing-prs SKILL.md)
change in exactly **one mechanical way**: their raw `gh issue comment` call
sites become `board-comment.sh` calls (§ Verb mapping) — after that
substitution the prose is binding-neutral, which is the X5 deliverable. The
bootstrap template gets
API-mode substitutions: `TICKET_ID` in place of issue number/URL, the
assignment body pinned to a file, and one line describing the credential env.
Workers call the same verbs with the same arguments; `own-ticket` scoping,
fence checks, and `run-ended` refusals arrive as ordinary script errors in
the server's vocabulary. Timeline reads (own ticket + direct children) cover
the reconciling Architect's and scale-review QAgent's canon flows.

### Session locator convention (local daemons)

`POST /runs/:id/bind` requires `{storeNs, projectKey, sessionId}` whole.
Local convention: `storeNs: "local:<hostname>"`, `projectKey: <repo-slug>`,
`sessionId: <claude session uuid>` (already in the registry), `pod` omitted.
No sessionStore feed exists for local sessions, so liveness rides the
renewed lease + authenticated writes (X6's pluggable source, server-side);
the locator's job is handing successors something `daemon-resume` can act on.

### Error handling posture

Fail-loud everywhere, no offline fallback (gh-mode doctrine carried over).
Transport failures on non-idempotent writes surface immediately, naming the
request. Server refusals print the API's own error vocabulary. The three
race outcomes (`lost-race`, `superseded`, `stale-resume`) log and stop —
re-reading is the next tick's job by construction.

## Scope-outs

- **Human board-management routes** — post-birth edge re-cut, priority
  change, relates, body edit — have no API counterpart (A1's matrix is
  worker-protocol-complete; these verbs aren't on the worker path). Flowed
  back to the arkho board as
  [arkho#7](https://github.com/SSFSKIM/arkho/issues/7) ("A1 follow-up:
  human board-management routes", spawned-by arkho#1), which also carries
  the spike-birth ruling and the birth-park question field (review F2/F8).
  API-mode `board-edge.sh` / `board-priority.sh` / `board-relate.sh` fail
  loud naming arkho#7.
- **Flipping the doperpowers board itself to API binding is A5**, not A2.
  A2's acceptance runs on drill repos/boards.
- **Design-first spike births** (`spike` → `ready-for-architect`) are
  refused by A1 (`409 illegal-birth`) but deliberately supported by gh mode
  — a canon divergence the fork's evolution created after A1 froze its
  vocabulary. Ruled on arkho#7 (flow-back item); until
  then, API-mode register surfaces the 409 and design-first spikes are
  gh-only. The birth-park question field (`--note` on park births has no
  API home) rides the same ticket; A2 interim-maps the note into the body
  head.
- **Per-ticket engine routing** (`engine:codex` label) has no API home
  (tickets carry no labels); API mode routes engine from `$WORKER_ENGINE`
  only. Recorded as a limitation; a body-meta convention can add it later if
  a real need appears.
- **Relay latency below the tick interval** (LISTEN wrapper / dedicated
  relay daemon): deliberately not built. NOTIFY is a latency hint by
  contract; the seam is confined to the sweep if a future need appears.

## Acceptance

Phrased as observable behavior; commands and expected output are pinned at
plan time.

1. **Full protocol walk (API binding, local instance):** a worker runs
   register → claim → gate verdict (`in-progress` + `[gate]` comment) →
   transitions → park → human answer → relay resume → terminal against a
   locally-launched A1 instance, entirely through the unchanged verb
   scripts. Every write lands via the API (the gh CLI is never invoked —
   asserted by the test harness).
2. **Transcript-diff drill:** the same scripted protocol walk run once in gh
   mode and once in API mode, diffed on the worker-visible surface (script
   invocations + stdout/refusals, transport-specific ids normalized) — the
   diff is empty. This is "indistinguishable modulo transport", executable.
3. **Crash-at-boundary drill:** the relay is killed at each boundary —
   before resume, between resume and ack, after ack — and in every case the
   answered park is re-polled, never lost, never double-resumed (asserted
   via the sentinel count in the session transcript and the ack state).
4. **Resume-first ordering:** with both a reclaimed in-flight ticket and a
   ready-queue ticket present, the sweep serves the resume before any fresh
   claim.
5. **Lease renewal:** a live local worker with no sessionStore feed is never
   reclaimed while the sweep renews (observed across ≥ 3 lease windows); a
   killed worker's run is reclaimed and surfaces in `needing-resume`.
6. **Recovery escalation:** with resumes and fresh spawns forced to fail,
   the third cycle registers an env-issue born `needs-human` naming the
   stuck ticket, and the sweep stops churning it.
7. **gh-mode regression:** the full existing gh-mode test suite passes
   unchanged; a repo with no binding file behaves byte-identically to
   pre-A2.
8. **Live smoke (deployed instance):** one full protocol walk against
   `https://arkho-board-service.onrender.com` with the operator credentials,
   throwaway tickets closed `wontfix` afterward — proving the real network
   path (Supavisor, Render, TLS). Completion additionally exercises A1.G3:
   the epic-recomposition drill (children terminal → parent returns to
   `ready-for-architect` → architect verdict) runs in the walk.

## Testing

- **Unit tier (hermetic, CI-always):** binding resolution, principal
  precedence, sentinel idempotence, category mapping, fail-loud verbs, error
  mapping — the existing `tests/claude-code/` shell-test pattern; HTTP mocks
  built from real captured responses (awkward-case raw output, per the
  mock-fidelity doctrine).
- **Integration tier (local live instance, the workhorse):** acceptance 1–7
  against the arkho repo's `board-service/` on a local Postgres (its own
  test suite already stands this up). Gated by `ARKHO_DIR` naming the arkho
  checkout; skipped with a loud notice when absent — the plugin repo never
  vendors the service.
- **Live smoke (once, at finish):** acceptance 8.
- **Read-scope audit (plan-time gate):** before declaring X5 held, audit the
  worker protocols for board reads outside own-ticket + direct children
  (grep for `board-list.sh` / `board-show.sh` / raw `gh issue view` in
  worker-executed prose) — a run bearer's reads are scoped, and any
  protocol read of an arbitrary ticket (a `blockedBy` target, a sibling)
  403s or filters-to-empty under the API binding. Each hit is either
  rewritten to an in-scope read or surfaced as a divergence before
  implementation.

## Decision Log

- **Adapter boundary: verb-level thin client** (2026-08-09, grill Q1).
  Rejected: transport-level swap inside `_board.py` (the API exposes
  semantic operations, not label primitives — no mapping exists, and it
  would run the state machine twice); parallel `board-api-*.sh` script set
  (mode-aware worker prose breaks transcript indistinguishability).
- **Binding: checked-in `.doperpowers/board.json`; credentials in
  `~/.arkho-board/<repo-slug>.env`** (grill Q2). Rejected: env-var-only
  binding (invisible to workers in fresh worktrees; turns the A5 flip into
  config management instead of one commit).
- **Sweep frame absorbs claim/renew/relay; no new daemon** (grill Q3).
  Rejected: dedicated long-running relay daemon (buys seconds of answer
  latency for a second process to keep alive and drill; NOTIFY is a latency
  hint by contract).
- **Relay delivery proof = transcript sentinel** (grill Q4). Rejected:
  registry marker written after resume (leaves a delivery→marker window
  where a crash double-resumes — two forks, two live workers on one
  ticket).
- **Principal resolution by env precedence inside the shared lib** (grill
  Q5). Rejected: per-actor script entry points (doubles the verb surface,
  breaks transcript parity).
- **Human board-management verbs scoped out; flow-back ticket on A1's
  board** (grill Q6). Rejected: extending A1 inside A2's slice (crosses the
  repo boundary mid-child; reopens a closed, reviewed service for routes
  the worker protocol never calls).
- **Tests: hermetic unit tier + local-instance integration tier + one live
  smoke** (grill Q7). Rejected: primary drilling against the deployed
  instance (pollutes a real board with crash residue; can't inject crashes
  at server boundaries).
- **Dead-worker recovery: resume → fresh-spawn fallback → env-issue
  escalation after 3 cycles** (design presentation, ⚑-marked, approved).
  Rejected: automation parking the ticket `needs-human` directly (automation
  has no transition authority in the matrix — the constraint is obeyed, not
  worked around).
- **`board-answer.sh` runs the relay step inline once** (design
  presentation, ⚑-marked, approved) — hand-delivered answers resume
  immediately, matching gh mode's blocking feel; the sweep remains the
  guarantee, the inline run is latency.
- **New `board-comment.sh` verb; protocols' raw `gh issue comment` sites
  substituted once** (independent review F1). Rejected: folding comments
  into another verb (comments are their own event family, and the E2 typed
  ops need a `--kind`/`--body` surface); leaving protocols on raw `gh`
  (breaks API mode outright — no comment lands, and acceptance 1's
  "gh never invoked" assertion could not hold).
- **Category collapse `bug`/`enhancement` → `work`** (silent decision,
  presented): dispatch keys on lanes/states, never on that distinction;
  A4's mirror owns any label round-trip.
- **Nonces minted per claim attempt and persisted to the registry before
  the request fires** (silent decision, presented; lifecycle sharpened by
  independent review F7): the registry records the nonce, then the claim
  response, then a **spawn-completed marker**. A persisted nonce is
  replayed **only when spawn is unrecorded** — recovering a claim whose
  response (or whose worker hand-off) was lost. After spawn-completed, the
  nonce is never replayed: a replay rotates the bearer by contract, which
  would revoke a live worker's credential mid-flight. Rejected: unqualified
  "replays are safe" (true only before hand-off).

## Surprises & Discoveries

- A1's API and schema have **no repo/namespace column** — a board instance
  is one board. The binding names an instance URL; ticket ids are
  board-local; the GH mapping belongs to A4's mirror. (Verified against
  `schema.sql` + `API.md` during the grill.)
- The route matrix gives automation **no transition authority** — which
  invalidated a straight port of gh-mode's park-on-failure recovery and
  produced the env-issue escalation design instead.
- **The toolkit had no comment verb** (independent review F1): worker
  protocols post comments via raw `gh issue comment`, invisible to a
  verb-level port until the reviewer caught it — and the comment route is
  the only API carrier for the E2 event ops (`closure-package`,
  `parent-impact`, `parent-impact-consumed`). Hence `board-comment.sh`.
- **The fork's board canon has drifted past what A1 froze** (review F2):
  gh mode deliberately supports design-first spike births that A1 refuses.
  First concrete instance of the X1 "upstream canon, not re-litigable"
  clause meeting a fork that kept evolving; resolved by flow-back ruling,
  not by either side silently winning.
- **The plan's error envelope was the wrong shape** (Task 2, implementation
  time): every fixture and the client's own error mapping assumed a flat
  `{"error": "fence-mismatch", "message": "…"}`, but API.md §1 and
  `src/server.js` both write it **nested** —
  `{"error": {"code": "…", "message": "…"}}`. API.md wins per the Global
  Constraints, so the client unwraps `error.code`. Two consequences worth
  carrying: the error identifier is what every `die` message and the
  `RunEnded` routing key on, so a flat reader would have degraded *every*
  contract refusal to an opaque `http-409` and never raised `RunEnded` at
  all; and the plan's later task bodies still carry flat-shaped 409
  fixtures, which are asserting against a shape the service never sends.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1.0 (2026-08-09): initial spec from the A2 brainstorming session
  (grill Q1–Q7 + one-pass design presentation, approved).
- v1.1 (2026-08-09): independent Fable review — all 12 findings adopted.
  New `board-comment.sh` verb (F1: no comment path existed; protocols'
  raw `gh issue comment` sites get one mechanical substitution); spike
  birth divergence surfaced + flow-back (F2); recovery suppression record
  specified (F3); `board-answer.sh` declared dual-principal (F4); sentinel
  mandated across all delivery vehicles + phase-3 crash analysis + bind
  repair in phase 1 (F5); fresh-spawn timeline read (F6); nonce replay
  lifecycle with spawn-completed marker (F7); park-birth note → body head
  + flow-back (F8); transition prints response `to` (F9); cap semantics
  pinned local-first (F10); relay prompt keeps gh orientation preamble
  (F11); plan-time read-scope audit gate (F12).
- v1.2 (2026-08-09): plan-time hostile read + Codex adversarial plan review
  (gpt-5.6-sol, 6/6 adopted). Two spec changes: **triggered dispatch is
  gh-only** — the API has no claim-by-ticket route, so the `<n>` form fails
  loud in API mode and targeted claim joins arkho#7 as a flow-back
  candidate (replaces "stays valid as a targeted claim"); **bearer-at-rest
  rehydration** — daemon-resume forks from the caller's env, so run
  credentials are stored in the daemon registry meta (0600) at bind time
  and re-injected on every resume. Plan-level adoptions (no spec change):
  ack gated on proven delivery + sweep lock; persist-before-resume enforced
  in code order; binding resolution as a pre-gh sourceable in every entry
  point; claim-journal startup reconciliation + real daemon-spawn output
  parsing; interactive verbs default to the human principal.
- v1.2.1 (2026-08-09): contract-conformance record, no design change —
  Task 2 found the plan's error envelope flat where API.md §1 and the
  shipped `src/server.js` write it nested (`{"error": {"code", "message"}}`).
  Logged under Surprises; `_board_api.py` unwraps `error.code`, and the
  remaining task bodies' flat 409 fixtures need the same correction.
- v1.2.2 (2026-08-10): premise wording precision from Task 5 implementation
  contact, no design change — the structural premise said `_board.py` "is
  never imported in API mode", which the read verbs break for a legitimate
  reason (`board-map.sh` imports `_board` to reuse the one existing pure
  display derivation, `B.eligible`). Reworded to the invariant actually
  meant: the state-machine half is never *exercised*, and the banned state
  is a divergent second client-side copy of legality/pick-order —
  imported-for-pure-display is the opposite of that hazard.
- v1.2.3 (2026-08-10): Task 9 review — **the relay's resume wait is bounded**
  (`BOARD_RELAY_RESUME_TIMEOUT`, default 300). The plan had the sweep call
  `daemon-resume` synchronously with the daemon toolkit's own unbounded
  default, which blocks for `DAEMON_TIMEOUT/2` (hours) while the tick holds
  its whole-tick lock: renewal starves past the 15-minute lease and A1
  reclaims live runs. Sentinel-ack-next-tick is the named degrade path — the
  prompt and the meta's `current` are both committed before the wait, so a
  timed-out resume acks nothing and the next tick acks off the sentinel
  without re-delivering (see the Relay idempotence section). Also recorded, no
  design change: the tick **unsets `BOARD_RUN_TOKEN`** at entry, since
  `token()` returns any run token in env for every principal — a tick
  inherited from a worker shell would otherwise renew/ack as that worker
  (violating "Renewal is dispatch automation, never worker prose") and a bind
  repair would stamp the foreign bearer into another run's meta.
