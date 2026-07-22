# Cloud-scale reference architecture — the board pipeline at enterprise fleet scale

## Purpose

Today the board pipeline (implementer workers + adversarial review workers
over a ticket board) runs on one Linux VM: workers are host processes in a
file-based registry, sessions live on a host volume, and the ticket board is
GitHub issues. That substrate is structurally the design Cursor measured at
one nine of reliability, and its arithmetic dies orders of magnitude below
the target this spec serves: **enterprise-internal operation, multiple large
projects, hundreds to thousands of implementer+reviewer runs per hour per
project, multi-host.**

After this architecture exists, an internal platform team can operate the
pipeline at that scale and a human can verify it: dispatch a thousand
tickets an hour into a project and watch them gate, build, review, and land
with no host being a pet, no worker holding a credential it could leak, no
illegal board transition ever observable, and a dead host costing only
lease-reclaim seconds — never work. The **semantic layer is frozen
throughout**: pre-code gate, park states, independent adversarial review,
tiered merge authority. This spec changes where those semantics run, not
what they are — with three explicit, human-approved amendments recorded in
the Decision Log (auto-land-under-watch tier, N-lens review under one
verdict, merge-resolver as a formal species).

**Evidence base.** All load math, vendor limits, prior-art numbers, and
rejected-alternative reasoning live in
`docs/doperpowers/2026-07-23-cloud-scale-research.md` (with ten full
reports under `docs/doperpowers/research/2026-07-23-cloud-scale/`). This
spec cites it as **[R §n]** and does not re-argue it.

**Terms of art** (defined once, used throughout):
- **run** — one worker execution against one ticket phase (gate, implement,
  review, land). **start rate** — runs begun per unit time. **concurrency**
  = start rate × mean run duration; the two are never interchangeable.
- **lease** — a time-bounded claim on a run held by a worker process,
  renewed by observable progress; expiry means the run is reclaimable by
  another process, never that work is lost.
- **fencing token** — a monotonic counter incremented on each claim of the
  same run, so a zombie process from an old lease cannot complete a newer
  attempt.
- **certified environment** — a snapshot of a repo's ready-to-work
  workspace plus the command contract (verification commands + expected
  outputs) that proved it works.

## Scale anchors

All sizing statements in this spec are made at named (start-rate ×
duration) points; "1,000 concurrent" is an anchor, not the envelope
[R §7.3].

| anchor | start rate | mean run | concurrency | engine actions/day |
|---|---|---|---|---|
| A1 (entry) | 0.3/sec (~1k runs/hr) | 30 min | ~500 | ~1M |
| A2 (mid) | 1.4/sec (~5k runs/hr) | ~20 min | ~1,000–1,700 | ~6M |
| A3 (top) | 6/sec (≈21.6k runs/hr) | 60 min | ~20,000 | ~26M |

The compute fleet scales linearly with concurrency; the dispatch and board
planes are sized for A3 from day one because their cost is fixed and small
[R §7.1–7.2].

## Architecture: three planes of truth, one compute substrate

The single-host doctrine ("the durable log is the identity of the work;
compute is disposable") survives intact and splits into three authorities
[R §1]. **On conflict about ticket state, the board wins.**

| plane | owns | carrier |
|---|---|---|
| Board service | ticket state, transitions, the durable human-answer record | small Postgres service (§1) |
| Dispatch plane | run ownership: claims, leases, retries, admission order | same Postgres + reconcile controller (§2) |
| Session store | run history: append-only event log per run, resume context | Postgres event-log tables v1 (§4) |

Compute (§3) is cattle under all three: per-run sandboxes, provisioned from
recipes, never repaired.

### §1 Board service — ticket SSOT with server-side semantics

A deliberately small service: Postgres plus a ~6-endpoint API — `claim`,
`transition`, `comment`, `park`, `query`, `reconcile`.

- **The legal-transition graph is enforced server-side as conditional
  UPDATEs**: `UPDATE ticket SET state='in-progress', owner=$run WHERE
  id=$id AND state='ready-for-agent'` is the legality check and the claim
  lock in one atomic statement; zero rows affected = lost race, surfaced
  as a 409-style error the client must re-fetch on (the Kubernetes
  API-server pattern) [R §7.1]. An illegal state is never observable by
  any reader.
- **History is append-only and retained permanently** — this table IS the
  durable human-answer record (Linear's 90-day audit retention is one of
  the reasons Linear cannot be the SSOT [R §7.1]).
- **Linear is the human-facing mirror, never truth.** A one-way sync
  worker coalesces machine-tempo writes into human-relevant updates
  (~hundreds of Linear writes/hour — inside one OAuth actor's budget);
  human actions taken in Linear (park answers, priority edits) flow back
  as *events into* the board service, which remains the only writer of
  record. Linear's own GitHub PR automations (merged → Done) are disabled
  per team — they are an uncoordinated second writer that would fight
  tiered merge authority [R §7.1].
- **Availability posture**: Postgres with WAL archiving + a standby
  (streaming replication); recovery point objective = zero committed
  transitions lost. **Workers fail closed when the board is unreachable**:
  a worker that cannot write a transition finishes its local step, parks
  its output durably in the session store, and stops — it never proceeds
  past a state boundary on assumption.
- Load at A3 is ~3–6 TPS/project — ≥100× headroom on one node [R §7.1].

### §2 Dispatch plane — same Postgres, resident reconcile controller

The dispatch plane owns which execution owns a ticket right now. It shares
the board service's Postgres **by design, not convenience**: the board
mirror row and the claim row commit in one transaction, which is the only
construction in which the engine *structurally cannot* become a second
ticket-state authority [R §7.2, §8.2]. This same-transaction property is
the tiebreaker that eliminated Hatchet and Temporal Cloud (Decision Log).

- **Claims**: `SELECT … FOR UPDATE SKIP LOCKED` over a run-queue table,
  with a fencing token incremented per claim.
- **Leases are minutes-scale and progress-refreshed**: every session-store
  append by the worker renews its lease (progress-as-heartbeat — the
  Anthropic `reclaim_older_than_ms` pattern writ large [R §7.2]). Never
  size the lease to the run. Expiry ⇒ the run returns to the queue;
  **reclaim resumes from the durable session log — it never restarts the
  run.**
- **Admission fairness**: per-tenant (team/project) concurrency caps +
  pick-next = lowest-recent-usage tenant first (Kueue's admission-fair-
  sharing semantics in SQL — trivial at ≤6 starts/sec) [R §7.2].
- **The controller is resident, level-triggered, and stateless**: a
  reconcile loop whose desired state is the board ("tickets that should
  have a run but don't"), run as an HA pair with leader election; all
  state in Postgres, restart costs nothing. The old "no resident
  orchestrator" rule is formally retired; the level-triggered reconcile
  doctrine it protected survives [R §2.1]. The symphony sweep-tick
  functions (transient auto-resume with exponential backoff, stall
  detection → kill+park, board-driven cancel, dispatch-until-cap, startup
  recovery) become controller logic. Board-driven cancellation closes
  FD-8: a ticket leaving the active states cancels its run within one
  reconcile pass.
- **Worker idempotency protocol** (engine-independent; part of the worker
  contract): every run attempt derives one stable attempt key
  (`ticket-run-fence`), stamps it on branch names, PR bodies, and board
  comments, and wraps every non-idempotent side effect in check-then-act
  (before push: does the remote ref already contain this SHA; before PR
  creation: does a PR with this attempt key exist) [R §7.2]. This — not
  the engine — is what prevents the duplicate-push-after-crash.

### §3 Compute plane — per-run gVisor sandboxes on local-NVMe hosts

- **Isolation**: one gVisor (`runsc` RuntimeClass) pod per run, warm pools
  ahead of demand, exit-and-replace after (the GKE Agent Sandbox shape;
  adopt that product if the org lands on GCP) [R §7.3]. The controls the
  prompt-injection threat model actually demands are **egress
  deny-by-default with a domain allowlist, workspace-scoped writes, and
  per-run scoped credentials** — the hypervisor is not the control.
  Kata/separate-kernel only for repo classes with a hard compliance
  mandate. Teams separate by namespace + NetworkPolicy (+ node pools where
  required).
- **Workers dial outbound-only** to the dispatch plane over long-lived
  HTTPS; no inbound ports on any worker host; adding a host = one command
  + a pool token. Readiness doubles as the claim signal (`/readyz` 503
  while busy); **busy workers are never terminated** by scaling or
  rolling updates [R §2.2].
- **Pools are labeled and species-split**: reserved non-spoofable labels
  (`repo=` auto-derived, `pool=` named); implementer and reviewer fleets
  are separate pools. **Reviewer sandboxes: fresh, never inherited from
  the implementer; read-only repo mount with full build/test execution;
  no push credentials** [R §5].
- **Warm state is a disk problem, not a memory-snapshot problem**
  [R §7.3]: pinned toolchain image (SOCI-indexed if large) → post-install
  workspace snapshot as a content-addressed disk artifact on a node-local
  NVMe cache, backfilled from object storage → overlayfs clone per run.
  No Firecracker memory snapshots (clock/RNG/TCP resume defects buy
  milliseconds that are 0.3% of a run).
- **Hosts**: bare-metal-class with local NVMe scratch (network volumes
  fail the I/O economics ~20× over); ~80–110 runs/host RAM-packed with
  CPU oversubscribed 2–4× (agents idle on tokens); scratch is ephemeral
  and dies with the pod. Fleet at anchors: A2 ≈ 12–16 hosts at its
  1,000-concurrent point (up to ~28 at the band's 1,700 top);
  A3 ≈ 230–330 hosts — linear in concurrency [R §7.3]. Per-host density
  is validated by spike S1 before any fleet purchase.

### §3b Environment layer — certification, registry, drift-by-construction

A new durable artifact class beside the three planes: the **environment
registry** — per (repo, environment key) → certified snapshot + command
contract. It is a cache with a certificate, never identity: losing it
costs one re-certification run [R §2.3].

- **Environment-as-code in-repo**: `build` (Dockerfile, toolchain only —
  never COPY the project; the platform owns checkout) / `install`
  (idempotent) / `start`; repo → team resolution; no per-worker overrides.
- **Certification gate (autoinstall pattern)**: a specifier agent fixes N
  verification commands + expected outputs *before* a separate executor
  agent must make a sampled subset pass; bounded fresh retries; on
  exhaustion the repo **parks as a needs-human infrastructure ticket**
  (never silently degrades — Cursor's flagship failure mode is silent
  fleet-wide quality loss from incomplete environments).
- **Drift is impossible, not detected**: environment key =
  hash(env-spec) ⊕ hash(lockfiles) ⊕ toolchain-image digest. Exact hit →
  restore + run one contract command as a smoke probe (the certificate
  doubles as the drift detector); any miss → rebuild through the full
  gate; TTL/GC 30–90 idle days as the backstop for non-hermetic inputs
  [R §7.3].
- **Environment readiness is a dispatcher precondition**, checked before a
  worker is launched — not a clause added to the pre-code gate skill. (The
  boundary is porous by design: probe failures *route into* the existing
  gate/park machinery.)
- **Mock fence (protects a frozen invariant)**: certification may mock
  dev-service sidecars (fake DBs, MinIO-for-S3, mock users) but never the
  system under test, and **every mock is declared in the environment
  manifest, which is surfaced to the review worker** — otherwise green
  tests against fakes hollow out adversarial review [R §2.3].
- **Provenance**: every PR records the environment key its run used.

### §4 Session store — append-only run history

v1 is event-log tables in the same Postgres (append-only writes through
the board-service API; ranged reads; **compaction never rewrites the log**
— summaries are derived views) [R §1]. This is the one plane with no
dedicated research track behind it [R §8.8]; v1 is therefore deliberately
the boring option, with a declared promotion trigger: when session-write
volume or retention pressure measurably degrades board/dispatch latency
(spike S4 defines the threshold), promote to object store +
content-addressed segments with a streaming tail (Cursor's S3+Redis
shape), keeping the append-only API unchanged. The dispatch plane's
lease-renewal hook reads this store's append stream — the two are coupled
by design.

### §5 Credentials — structural unreachability over scoping

Scoping decays as models improve; the durable posture is tokens the
generated code *cannot reach* [R §2.4].

- **Git: auth bundled with the resource** — a short-lived, repo-scoped
  token is wired into the remote at sandbox init; the agent never sees it.
- **Per-claim credentials**: minted at dispatch, STS-style ~1 h expiry,
  auto-refresh, scoped to the run's environment; build secrets scoped to
  the build step; rotation via re-read token files, never restarts.
- **Merge-capable credentials exist only on the landing path** — the
  credential topology mirrors tiered merge authority. Implementers can
  open PRs; only the land worker can merge.
- **Service credentials behind the enterprise's existing secrets manager +
  egress proxy** keyed by run identity (the vault/proxy previously
  rejected at single-host scale; adopted scoped [R §3]).
- Honest boundary, documented: with external model APIs, the model context
  window is an egress path no data-plane design closes [R §2.4].

### §6 Review & merge plane

Human-approved amendments to the semantic layer are marked ★.

- **★ Review = one verdict, N decorrelated lenses, ALL blind.** Lenses
  vary by model and evidence diet but **every lens stays
  implementation-blind** (no ticket/spec/transcript input) — the evidence
  boundary today's single-engine reviewer enforces is preserved lens-by-
  lens; what changes is plurality plus an aggregation stage. The
  **verifier stage is a named, load-bearing component with its own
  false-escalation SLO**: findings pass through verification/severity-
  ranking before any human sees them (the Cursor/Anthropic converged
  shape; an unfiltered finding stream can DoS the human tier) [R §7.4].
- **★ Merge authority gains a fourth tier — auto-land-under-watch.**
  Tiers: (1) auto-land: a **whitelist of machine-verifiable change
  classes** with per-class guardrail chains (the only precedented form —
  Rosie patterns, Renovate classes, TestGen-LLM guardrails); (2)
  auto-land-under-watch: medium-risk classes land conditional on canary
  verdict — score → promote / route-to-human / auto-revert (Kayenta
  shape); (3) human tier; (4) never-auto: schema/data/security/config
  changes take full review regardless of size [R §7.4]. Unclassifiable ⇒
  not auto-landable, by definition.
- **Merge queue is chosen per repo risk class** (human decision,
  2026-07-23): low-risk repo classes run TAP-style batching + automatic
  bisection (per-change verification traded for throughput); high-risk
  classes keep per-change verification via SubmitQueue-style speculation +
  build-target independence. Hosted queues (GitHub ≤100 concurrency,
  drop-and-rebuild) serve only low-rate repos [R §7.4]. The queue owns a
  flake policy (retry + quarantine + never blame the innocent PR).
- **★ The merge-resolver is a formally recognized third species** (hybrid
  model, human decision 2026-07-23): it runs at merge-queue tempo with no
  pre-code gate and no authority of its own — its output always re-enters
  the existing review path. All other maintenance work (doc reconciliation,
  megafile decomposition) is absorbed as auto-registered board tickets.
  Planning number: ~40% conflict probability at just 16 concurrent
  in-flight changes — the resolver is steady-state, not an edge case.
- **Human tier design**: escalations arrive small, pre-verified,
  severity-ranked, routed to a dedicated approver rotation by ownership,
  under a first-response SLO (Google-calibrated: 1-business-day max,
  sub-hour median achievable) [R §7.4]. **Park queues get the same
  treatment**: routed, batched, notified, SLO'd — park states survive
  scale only with queue infrastructure behind them [R §4.1].

### §7 Observability & circuit breakers

- **Fleet gauges**: queue depth (autoscaling), pending = claimed-not-acked
  (stall detection), workers-polling (liveness) [R §2.1].
- **Session-end reason taxonomy** per worker (clean / stream-error /
  closed / error / timeout / aborted) — distinguishes infra failure
  (re-dispatch) from agent failure (park) mechanically [R §2.2].
- **Contention circuit breakers**: per-repo conflict rate, hottest-file
  contention, PR-rework rate, commit-churn ratio; acceleration trips an
  automatic dispatch pause for that repo. Volume metrics are vanity;
  conflict acceleration is health [R §2.5]. Megafile machinery rides the
  same feed: flag → merge-queue freeze → auto-registered decomposition
  ticket.
- **Failure-boundary separation**: harness/dispatch logs live outside
  data-bearing sandboxes, so harness bug / transport drop / sandbox death
  are distinguishable without entering user-data environments [R §2.5].

### §8 Economics & model routing

- **Model tier is a per-phase routing decision**: frontier models at
  decision points (gate, decomposition, park/escalate, review verdicts),
  cheap models for implementation bulk; gate/planner models are evaluated
  on total downstream run cost, not their own bill. Per-model prompt
  profiles are versioned substrate config [R §2.6].
- **Token spend dominates**: infra at A2 is ~$5–15k/mo self-hosted, but
  token spend at fleet tempo plausibly exceeds it by 10–100× — spike S3
  replaces this Fermi with measured numbers, and provider
  rate-limit/quota architecture is a first-class design input, not an
  afterthought [R §8.13].
- **Aggregate ops budget** (the honest bill for Bundle A): the platform
  team owns board service + mirror sync, dispatch controller, k8s/gVisor
  NVMe fleet, environment registry + certification, session store,
  vault/egress proxy, contention telemetry, merge queue. This list is the
  standing argument for the phased adoption path below — nothing is built
  before the phase that needs it [R §8.12].

### §9 Code-host load plan

The arithmetic that disqualified GitHub-as-board applies to the PR plane:
PR creation, review comments, and verdict comments are content-generating
requests under the same 500/hr-per-actor secondary limit — plausibly
8–14× over at A2–A3 per project [R §8.11]. Mitigations, applied in order:
**verdict/finding traffic moves onto the board service** (PRs carry a
link, not the transcript of findings); review submissions are batched
(one review with N comments = one content request); per-installation
actor sharding for what remains; GHES with configurable limits as the
escape hatch if the org runs it. The spec's conformance load test (§
Acceptance) exercises this plane explicitly.

## Adoption path

Phases gate on observed pressure, not calendar. Each phase is
independently valuable and reversible-cheap.

- **P0 — planes on one box.** Board service + dispatch tables + session
  store on one Postgres; controller replaces cron sweeps; workers still
  local processes. Proves the same-transaction core and the worker
  idempotency protocol at A1 rates. (The current single-host pipeline
  migrates onto it; the file registry retires.)
- **P1 — compute plane.** k8s + gVisor pools on 2–3 NVMe hosts; outbound
  workers; environment registry + certification for the first repos.
  Includes the **density spike** (below) before any fleet sizing.
- **P2 — review/merge plane at tempo.** N-lens + verifier, auto-land
  whitelist v1, merge queue per risk class, merge-resolver, park-queue
  SLOs.
- **P3 — scale-out.** Fleet growth toward A2/A3 anchors, canary tier
  (auto-land-under-watch), contention breakers armed org-wide.

**Prototyping milestones (spikes)** — unknowns the research could not
close; each declares its promote/discard criterion:

- **S1 (host density; gates P1's fleet sizing)**: one NVMe host,
  synthetic run mix at target I/O duty; promote the ~80–110 runs/host
  figure only if measured p95 build latency holds; otherwise re-derive
  fleet math before purchase.
- **S2 (Linear mirror under load; runs during P0)**: sustained A2-rate
  synthetic transitions through the coalescing mirror; promote if Linear
  stays under one actor's budget with <60 s human-visible staleness;
  discard → mirror to a cheaper surface (dashboard only).
- **S3 (token Fermi → measurement; runs during P1)**: 100 real runs
  metered end-to-end per phase tier; output replaces §8's 10–100× Fermi
  and sets the provider-quota architecture.
- **S4 (session-store pressure; runs during P1–P2)**: measure
  board/dispatch latency vs session-write volume; output defines §4's
  promotion threshold number.

## Acceptance

A conforming implementation demonstrates each of these as observable
behavior (the conformance drill list; exact commands land in the
implementation plans, but each line names its observation):

1. **No pet hosts**: kill a worker host mid-run (`kubectl drain` /
   power-off) → every affected run is reclaimed within one lease window
   and resumes from its session log on another host; **zero duplicate
   PRs, zero duplicate pushes** (verified by attempt-key audit), zero
   lost ticket transitions.
2. **No observable illegal state**: fire concurrent conflicting
   transitions (two claimants, one ticket) from N clients → exactly one
   wins; the loser gets the 409-style rejection; the board history shows
   only legal edges. A fuzzer running arbitrary transition requests for
   an hour produces zero illegal rows.
3. **Board-driven cancel**: move an in-progress ticket out of the active
   states in the board (or via the Linear mirror's back-edge) → its
   worker is terminated within one reconcile pass, the worktree survives
   as a committed branch, and a termination comment lands on the ticket.
4. **Fail closed**: partition the board service away from a running
   worker → the worker completes its current step, persists output to
   the session store, stops at the state boundary, and its lease expiry
   parks the run — it never writes code-host state past the boundary.
5. **Environment honesty**: corrupt a lockfile hash (simulate drift) →
   the next dispatch refuses the stale snapshot, rebuilds through
   certification, and the run's PR provenance shows the new environment
   key. Exhaust certification retries → a needs-human infrastructure
   ticket appears; no worker ever starts on an uncertified sandbox.
6. **Credential unreachability**: from inside a worker sandbox, no
   process can read a git token (it lives only in the remote config as a
   short-lived credential), reach a non-allowlisted domain, or merge a
   PR; the landing path alone can merge. A red-team prompt-injection run
   confirms the blast radius is board comments + its own branch.
7. **Merge tempo with safety**: at A2-rate synthetic PR load on a
   batch-class repo, the queue sustains the landing rate with mainline
   staying green (failing batches bisect automatically; innocent PRs are
   never rejected for others' flakes); a seeded under-watch-class
   regression auto-reverts on canary verdict without human action.
8. **Human tier under SLO**: seeded escalations arrive pre-verified and
   severity-ranked; first-response SLO metrics exist and alert; a seeded
   burst of low-quality findings is absorbed by the verifier stage
   (false-escalation SLO holds) rather than reaching humans.
9. **Code-host headroom**: the A2 conformance load test records
   content-generating request rates per actor against the code host and
   shows sustained operation below secondary-limit thresholds with the
   §9 mitigations active.
10. **Circuit breaker**: a synthetic conflict storm on one repo trips its
    dispatch pause automatically; other repos' throughput is unaffected.

## Decision Log

- Decision: Bundle A — "Sovereign Postgres Core": board service + dispatch
  plane share one Postgres; k8s+gVisor+NVMe compute; Postgres session
  store v1; Linear as mirror; GitHub keeps PRs.
  Rationale: the same-transaction property (board mirror row + claim row
  commit atomically) is the only construction where the dispatch engine
  structurally cannot fork ticket authority — the doctrinal tiebreaker
  [R §8.2]. Rejected: **Bundle B (adopt-heavy: Hatchet + GKE Agent
  Sandbox)** — lowest build cost, but Hatchet writes through its own
  engine connection, killing the same-transaction guarantee, and adds
  young-project risk; reopen if platform-team capacity proves
  insufficient to own ~1–3k lines of lease/fairness code. **Bundle C
  (Temporal Cloud, Cursor-shaped)** — the right answer at 10×+ growth;
  loses today on the permanent determinism/versioning tax, ticket-state
  gravity, and a top-of-envelope bill of ~$39k/mo pre-discount; reopen on
  sustained growth toward anchor A3. **Self-hosted Temporal** —
  eliminated on ops grounds (irreversible shard sizing, 4 services +
  Cassandra/ES, headcount) [R §7.2].
  Date/Author: 2026-07-23 / brainstorm (human-confirmed).
- Decision: Ticket SSOT is a thin self-owned board service; Linear is
  mirror-only; GitHub issues retire as the board.
  Rationale: GitHub breaks first on content-creation secondary limits
  (12× over, hidden shared buckets); Linear is ~2× over per actor on
  total ops with no transition enforcement, no CAS, and 90-day audit
  retention; a Postgres service has ≥100× headroom and makes illegal
  states unobservable. Rejected: **Linear-as-SSOT (sharded)** — recorded
  as the no-service fallback with accepted claim races; **GitHub
  app-sharding** — adversarial to the vendor's abuse system [R §7.1].
  This is a NEW decision; FD-2's schema-vs-config granularity question
  stays deferred on its original trigger.
  Date/Author: 2026-07-23 / research round 2.
- Decision: Retire "no resident orchestrator"; keep level-triggered
  reconcile as the controller doctrine.
  Rationale: the symphony §9 objections (in-RAM claims, evaporating retry
  queue, unwatched failure domain) are answered by durable state in
  Postgres + stateless HA controller; fleet scale adds sub-cadence needs
  (seconds-to-minutes lease reclaim, continuous admission ordering) that
  batch cron honestly cannot serve [R §2.1].
  Date/Author: 2026-07-23 / research synthesis (review-corrected).
- Decision: gVisor per-run pods on local NVMe; no Firecracker memory
  snapshots; warm state as content-addressed disk artifacts.
  Rationale: millisecond restores are 0.3% of a run and carry clock/RNG/
  TCP correctness defects; disk I/O density is the binding constraint and
  network storage loses ~20× on cost; drift closes by hash-keying, not
  detection. Rejected: **SaaS sandboxes** (~$73–104k/mo at 1k concurrent
  vs ~$5–15k self-hosted), **Kata default** (overhead without a mandated
  boundary), **CRIU** (30–60 s class) [R §7.3].
  Date/Author: 2026-07-23 / research round 2.
- Decision: Merge-queue verification semantics chosen per repo risk class
  (batch+bisect for low-risk; speculation per-change for high-risk).
  Rationale: the only two publicly proven mechanisms at target tempo;
  uniform choice either overpays (speculation everywhere) or weakens
  gating where it matters (batching everywhere).
  Date/Author: 2026-07-23 / human decision at brainstorm.
- Decision: ★ Auto-land = machine-verifiable change-class whitelist, plus
  a formal fourth authority tier (auto-land-under-watch, canary-verdict
  conditional).
  Rationale: every published auto-land precedent is class-bounded; canary
  three-way verdicts (promote/human/revert) are what every reference org
  runs in substance; naming the tier is honest semantics rather than
  hidden substrate. Acknowledged: human-free merge of *general* agent
  code exceeds all public precedent — the safety case is our guardrail
  design, not industry practice [R §7.4, §4.7–4.10].
  Date/Author: 2026-07-23 / human decision (semantic-layer amendment).
- Decision: ★ Review becomes one verdict over N decorrelated lenses with
  a named verifier stage — and every lens stays implementation-blind.
  Rationale: lens decorrelation is the review multiplier and the verifier
  is what keeps recall affordable; rejecting the transcript-aware lens
  preserves the evidence boundary the current reviewer enforces by
  design. Rejected: **transcript-aware lens** (crosses the boundary;
  reopen only with eval evidence that blind lenses miss a class of
  defects it catches); **single-engine status quo** (leaves measured
  recall on the table at fleet tempo) [R §7.4, §4.4].
  Date/Author: 2026-07-23 / human decision (semantic-layer amendment).
- Decision: ★ Hybrid third-species model: merge-resolver formally
  recognized (queue tempo, no gate, no self-authority, output re-enters
  review); other maintenance agents absorbed as auto-registered tickets.
  Rationale: the resolver cannot absorb a gate+review cycle per conflict
  at ~40%-conflict/16-in-flight tempo; everything else fits ticket shape.
  Rejected: **all-tickets** (queue latency), **full third species**
  (larger semantic change than the evidence demands) [R §4.3].
  Date/Author: 2026-07-23 / human decision (semantic-layer amendment).
- Decision: Session store v1 = Postgres event-log tables behind the board
  API, with a measured promotion trigger to object-store segments.
  Rationale: the one SSOT plane with no research track behind it — take
  the boring option, instrument it (spike S4), and keep the API stable so
  promotion is an implementation swap [R §8.8].
  Date/Author: 2026-07-23 / brainstorm.
- Decision: Non-imports reaffirmed — custom VCS, planner-tree topology
  replacing the board, per-commit error budgeting without humans,
  Managed Agents as the substrate, brain-in-cloud split, harness-shrinkage
  applied to semantic gates.
  Rationale: recorded with reopen triggers in [R §2.7]; not duplicated
  here.
  Date/Author: 2026-07-23 / research synthesis.

## Surprises & Discoveries

- Observation: The two strongest architecture constraints were invisible
  to every individual research track — the same-transaction coupling
  between board and dispatch, and the PR plane falling under the same
  GitHub secondary limits that disqualified GitHub-as-board.
  Evidence: both surfaced only in the cross-track review pass of the
  research synthesis [R §8.2, §8.11]; each track's scope ended exactly
  where the interaction began.
- Observation: Throughput and concurrency were silently conflated in
  early sizing — "1,000 concurrent" is a mid-band anchor, while the
  envelope's top implies ~20,000 concurrent at hour-long runs.
  Evidence: review of the synthesis caught the fleet being sized at one
  point of the (start-rate × duration) curve; the Scale anchors table
  now pins three named points.
- Observation: Drift detection — the #1 open question after round 1 —
  dissolved rather than resolved: no credible operator patches stale
  environments; all key snapshots by content hash and rebuild on miss.
  Evidence: DevPod hash-keyed prebuilds, Fly invalidate-on-deploy,
  GitHub-Actions lockfile-hash cache keys [R §7.3].
- Observation: The certification gate bought its drift probe for free —
  the command contract that certifies an environment is the same artifact
  that smoke-tests a restored snapshot.
  Evidence: [R §7.3] synthesis; no additional component needed.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-23: Initial spec, written from
  `docs/doperpowers/2026-07-23-cloud-scale-research.md` after its
  correction pass; Bundle A and four human decisions (merge semantics per
  risk class, auto-land whitelist + under-watch tier, N blind lenses +
  verifier, hybrid third species) fixed at brainstorm.
