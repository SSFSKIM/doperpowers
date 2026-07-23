# Agent-Native Swarm Campaign Roadmap (2026-07-23)

> **Parent:** root — the doperpowers fork's standing purpose
> (`CLAUDE.local.md`: customize the plugin to how the human actually works
> and evolve its methodology). **Level name:** none — the fork does not
> use level vocabulary. **Consumes:** the goal-gated decomposition design
> of record
> (`docs/doperpowers/specs/2026-07-21-goal-gated-decomposition-design.md`,
> v7.24.1) — the system under dogfood; Cursor's "Agent swarms and the new
> model economics" (2026-07-20) — the external design the experiment
> adapts; CC-Eng-Rev's `docs/replication/MASTER-ROADMAP.md` — the object
> program's own root, which this unit does NOT own (see X7). Children
> dispatch per their track hint; each child spec opens by citing this
> document (path + child id).

## Purpose

Dogfood the decomposition system at the scale it was designed for: run
CC-Eng-Rev's third replication campaign — the 87-capability `DISCOVERED`
frontier — as a fully agent-driven swarm with no human steering beyond
the gates the methodology already declares (roadmap-spec approval, board
materialization approval, CC-Eng-Rev's §9.5 checkpoints). The swarm
adapts Cursor's planner/worker architecture onto our own substrate: the
issue board is the shared task tree, GitHub Actions self-hosted runners
are the worker fleet, clodex gateway sessions are the engines, and
CC-Eng-Rev's deterministic evidence gates are the held-out grader. The
experiment's second product is measurement: reproduce the article's
economics analysis (tokens and cost per role, conflict concentration,
quality curve) for our stack, and flow every methodology lesson back
into the decomposing design of record.

## Parent-Level Acceptance

The unit closes when all of the following are observable:

1. At least two full swarm waves have landed on CC-Eng-Rev `main`
   through the wave protocol (X3) — dispatched from board eligibility,
   implemented by fleet workers, integrated serially, wave-reviewed —
   with **zero human interventions outside the declared gates**.
2. An economics report exists reproducing the article's axes for our
   stack: capability promotion curve over time, merge-conflict count and
   concentration, per-role token/cost split (planner vs worker vs
   review), and confirmed review findings per wave.
3. The dogfood lessons are recorded: the decomposing design of
   record carries a dated live-run note resolving (or renewing) its
   "first live run pending" watch item, and any observed skill failure
   has a written disposition.

All children landed is not this event — closure is verified against
these three statements (recomposition).

## Grounding Baseline

Measured 2026-07-23 from CC-Eng-Rev:

- 95 canonical capabilities; lifecycle: 87 `DISCOVERED`, 8
  `CANDIDATE_VERIFIED`. Criticality: 27 T0, 34 T1, 28 T2, 6 T3.
- Second campaign in flight on `replication-second-campaign` (another
  session's working tree — off-limits until it lands): 1 of 7 packets at
  F3, next selection `CAP-PERSIST-001`.
- Second-campaign ExecPlan history shows throughput dominated by the
  canonical-evidence-chain hardening loop: any source change stales the
  full 31-identity chain, forcing two-pass regeneration plus re-review.
  This is the predicted conflict hot-spot (the "megafile" analog).
- Runner precedent: one self-hosted runner registered for ida-solution
  (label-trap, PATH-trap, and resume-`--settings` lessons recorded in
  memory); its end-to-end dispatch is still unproven. CC-Eng-Rev is
  owned by the user's own account, so registration there is
  self-service. A single runner instance processes one job at a time —
  fleet width = number of registered instances.

## Children

### C1: Dispatch substrate — autonomous

- **Purpose:** the mechanical swarm floor: N runner instances registered
  on CC-Eng-Rev, a dispatch workflow that turns an ELIGIBLE board ticket
  (X2) into a worker job, and a worker bootstrap that gives each job an
  isolated checkout, the ticket body, the Field Guide (X5), and a clodex
  engine invocation per X1 — then pushes the worker's branch for the
  integrator lane.
- **Acceptance:** one dummy ticket travels the full loop — board
  `dispatchable` → Actions dispatch → clodex opus worker in an isolated
  checkout → branch pushed → integrator lane (C4) picks it up — with the
  job log carrying the X1 gateway probe. Fleet width is a tunable, and
  two instances demonstrably run two tickets concurrently.
- **Edges:** blocked-by: — (settings-level runner registration and
  branch-side workflow development touch no working tree the second
  campaign owns); blocks: C4, C5.
- **Contracts:** X1, X2 (implements the eligibility sync), X4, X5
  (injection side), X6 (emits timing/token records).
- **Required:** required.
- **Status:** not-dispatched (dispatchable now).

### C2: Campaign governance amendment — controlled

- **Purpose:** make CC-Eng-Rev's written contract true for a swarm:
  amend the campaign protocol's per-packet Codex step to the wave
  cadence (X3) — the human's decided change — map roadmap §9.3 WIP
  limits onto fleet semantics (one state-changing worker per deep
  module, enforced by X2), institute the Field Guide (X5), and define
  the integrator role. Governance text on a fail-closed evidence repo is
  taste-heavy; hence the controlled track.
- **Acceptance:** CC-Eng-Rev `CLAUDE.md` (and roadmap §9 where touched)
  states the wave protocol, fleet WIP mapping, Field Guide institution,
  and integrator role, with no contradiction against the untouched
  evidence/receipt contracts; the amendment lands on `main`.
- **Edges:** blocked-by: external:second-campaign-landed (the file is
  the other session's working tree until then); blocks: C3
  (materialization side), C5.
- **Contracts:** X3 (codifies), X4 (codifies), X5 (institutes).
- **Required:** required.
- **Status:** not-dispatched (waiting-external).

### C3: Third-campaign roadmap + board materialization — decomposing

- **Purpose:** the core dogfood: a decomposing run over the
  87-capability frontier producing CC-Eng-Rev's third-campaign roadmap
  spec and, after human approval, the materialized board. The skill's
  new test is ADOPTION: the tree already exists in materialized form
  (`capabilities.json` dependencies, module ownership, criticality
  lanes) — the run must adopt that substrate as its board and edges, not
  reinvent a registry. Its cut must also produce knowledge-children:
  most `DISCOVERED` capabilities need evidence-workflow stages
  (inventory → contract → candidate) before implementation, so evidence
  tickets are first-class children, not preamble.
- **Acceptance:** G1 (required): a third-campaign roadmap spec exists in
  CC-Eng-Rev citing its own root (MASTER-ROADMAP, per X7), wave-structured
  over the frontier, approved by the human. G2 (required): the board is
  materialized from it — tickets to the pre-spec bar, typed edges from
  the dependency spine, `board-lint` clean — after the approval
  hard-gate.
- **Edges:** blocked-by: external:second-campaign-landed (the frontier's
  ready-set depends on the second campaign's final receipts); G2
  additionally blocked-by C2 (the contract the tickets cite must exist);
  blocks: C5.
- **Contracts:** X2 (defines eligibility), X3 (wave structure), X7.
- **Required:** required.
- **Status:** not-dispatched (waiting-external).

### C4: Integrator and wave protocol — controlled

- **Purpose:** the serial spine the parallel fleet leans on — the
  article's neutral merge agent in our clothes. A single-concurrency
  integrator lane takes worker branches, merges or reconciles them,
  regenerates the canonical evidence chain ONCE per wave (the Grounding
  Baseline shows per-change regeneration would thrash), runs the wave
  gates, triggers the wave Codex review, and lands the wave. It also
  emits the conflict and finding counts X6 needs.
- **Acceptance:** a simulated wave of two concurrently-produced worker
  branches (from C1's dummy loop) lands through the integrator with one
  canonical regeneration, gates green, and per-wave metrics recorded.
- **Edges:** blocked-by: C1; blocks: C5.
- **Contracts:** X3 (owns), X6 (emits).
- **Required:** required.
- **Status:** not-dispatched (blocked-by C1).

### C5: The swarm run and economics report — autonomous

- **Purpose:** the experiment proper: run waves against the third
  campaign until the frontier is dry, a stop condition trips, or the
  human calls it; then write the economics report and the dogfood
  retrospective that Parent-Level Acceptance names. Model mix per the
  human's decision: planner/conductor = gateway `fable` effort xhigh,
  workers = gateway `opus` effort high (Claude harness, GPT engines —
  the article's hybrid axis on our quota structure).
- **Acceptance:** Parent-Level Acceptance items 1 and 2 hold; the report
  additionally states, with numbers, whether the canonical-chain serial
  section capped the parallel gain as predicted (the Amdahl question
  from Risks).
- **Edges:** blocked-by: C1, C2, C3, C4; blocks: —.
- **Contracts:** X1–X6 (obeys all; X6 report owner).
- **Required:** required.
- **Status:** not-dispatched (blocked-by C1–C4).

## Cross-Child Contracts

- **X1 — Worker invocation:** every fleet engine is invoked with
  explicit argv — `claude --settings ~/.claude/clodex-settings.json
  --model <alias> --effort <level>` — never via PATH shims; every job
  logs a deterministic gateway probe (`echo
  ${ANTHROPIC_BASE_URL:-unset}`); every resume/fork re-carries
  `--settings` AND `--model` (each omitted argv dimension silently
  reverts — observed failure, memory `clodex-gateway-wrapper`). Owner:
  C1; binds C4, C5.
- **X2 — Eligibility:** a ticket is ELIGIBLE iff CC-Eng-Rev's
  control-plane scheduler lists its capability dependency-ready and
  non-human-gated, AND its module ownership is disjoint from every
  in-flight ticket (roadmap §9.3), AND its board state is
  `dispatchable`. Definition owner: C3; sync implementation: C1; C5
  dispatches nothing outside it.
- **X3 — Wave protocol:** a wave is the set of worker branches the
  integrator lands as one serial batch: merge/reconcile → one canonical
  regeneration → gates → one Codex review on the integration branch →
  land. Conflicts and confirmed findings are logged per wave. Owner:
  C4; codified into governance by C2; obeyed by C5.
- **X4 — Safety envelope:** workers inherit CC-Eng-Rev's standing
  constraints verbatim (no official-target execution, no credentials or
  paid/live APIs, no external transmission, evidence privacy); the
  runner stays repo-scoped to the private repo; a worker writes only
  inside its own checkout and branch. Owner: C1 (mechanical), C2
  (written contract).
- **X5 — Field Guide (stigmergy):** `FIELD-GUIDE.md` in CC-Eng-Rev,
  owned by the workers, hard line budget (initial: 150 lines), injected
  into every worker prompt at dispatch; workers edit it in-branch and
  the integrator merges guide edits first-class. Seeded from the second
  campaign's trap inventory (leading `./` in bun test paths, short-root
  cold checkouts, frozen-lockfile materialization). Institutes: C2;
  injects: C1; usage measured by: C5.
- **X6 — Metrics ledger:** per-role token/cost from gateway logs; job
  timing from Actions; commits/conflicts from git; promotion curve from
  board + capability-status history; findings per wave from X3 logs.
  Emitters: C1, C4; report shape and ownership: C5.
- **X7 — Two-tree seam:** this spec is a node in the DOPERPOWERS tree
  (the experiment); the third-campaign roadmap C3 produces is a node in
  CC-ENG-REV's tree and cites MASTER-ROADMAP as its parent authority,
  not this document. Methodology lessons flow back here; replication
  program decisions flow back there. Neither document owns the other's
  domain. Owner: this spec; binds C3, C5.

## Ordering & Dependency Map

C1 is the only immediately dispatchable child and runs now, entirely on
runner settings + its own branches. C2 and C3's spec-authoring open the
moment the second campaign lands `main`
(external:second-campaign-landed); C3.G2 (materialization) additionally
waits for C2 and the human's approval. C4 follows C1 and can complete
against dummy waves before C3 materializes. C5 is the terminal child and
starts only when C1–C4 are green. Parallel span: C1 ∥ (waiting) → C2 ∥
C3.G1 ∥ C4 → C3.G2 → C5.

## Risks & Mitigations

- **Canonical-chain serialization (Amdahl):** the evidence chain is a
  forced serial section; fleet width past a small N may buy nothing.
  Mitigation: X3 batches regeneration per wave; C5's report must answer
  the question with numbers rather than assume either way.
- **Main-branch race with the second campaign:** its protocol verifies
  HEAD/main/origin-main equality before pushing. Mitigation: until
  external:second-campaign-landed, swarm work touches only runner
  settings and non-main branches (C1's edge rationale).
- **Gateway quota/cooldown thrash:** cliproxy holds cooldowns in memory
  and refuses without calling upstream after quota resets. Mitigation:
  X1 probe exposes it per job; fleet width is a tunable; known recovery
  is a cliproxy service restart (memory, ops gotcha).
- **Workflow-trigger mechanics:** `workflow_dispatch` requires the
  workflow file on the default branch, which C1 cannot touch yet.
  Mitigation: C1 may prove the loop on a disposable sandbox repo first
  (self-service on the user's account); means stay with the child.
- **Runner is login-session-bound:** jobs queue (≤24h) while the Mac is
  logged out. Accepted for the experiment's duration.
- **Nested-subagent cascade:** CC-Eng-Rev's standing caution; fleet
  workers marshal subagents freely but the dispatch layer itself never
  recurses (a worker cannot dispatch fleet jobs).

## Deferred / Out of Scope

- **Deferred (may return):** N×N engine-mix matrix (real Anthropic
  fable/opus vs gateway GPT aliases) — the article's full grid; one mix
  per the human's decision this run. Moving the fleet to the Hetzner
  worker VM (fresh runner token required). Sweep-style self-healing
  cron for the fleet (the standing sweep is OFF by the human's word;
  reactivation is theirs alone).
- **Explicitly out of scope:** replicating the article's custom VCS or
  commit-rate targets (our bottleneck is API quota and one Mac, not
  merge throughput); any weakening of CC-Eng-Rev's evidence, privacy, or
  human-gate contracts (X4 is an invariant, not a preference); public
  publication of the experiment.

## Tracking Map

| child | spec / artifact | status |
|---|---|---|
| C1 | (ExecPlan on dispatch, cites this doc + C1) | not-dispatched — dispatchable now |
| C2 | (CC-Eng-Rev governance diff, cites this doc + C2) | not-dispatched — waiting-external |
| C3 | (third-campaign roadmap in CC-Eng-Rev, cites MASTER-ROADMAP per X7) | not-dispatched — waiting-external |
| C4 | (ExecPlan on dispatch, cites this doc + C4) | not-dispatched — blocked-by C1 |
| C5 | (run log + economics report, cites this doc + C5) | not-dispatched — blocked-by C1–C4 |

## Decision Log

- **Swarm after the second campaign, not instead of it** (human,
  2026-07-23): the in-flight second campaign finishes sequentially in
  its own session and lands `main`; the swarm is the THIRD campaign over
  the 87-capability frontier. Rejected: absorbing the remaining six
  packets into the first wave (loses the sequential baseline the
  economics comparison wants); running the swarm on a disjoint
  capability set concurrently (splits the campaign manifest and doubles
  governance surface). Bonus: the second campaign becomes the
  experiment's sequential control group.
- **Fleet = unbounded eligible-ticket dispatch on self-hosted runners**
  (human, 2026-07-23): no fixed worker count — any ELIGIBLE ticket (X2)
  may receive a worker; width is bounded mechanically by registered
  runner instances and quota, not by protocol. Rejected: fixed 3-worker
  pilot (my recommendation — the human chose the agent-native full
  experiment; the conservative variant survives as a tunable, since
  width = instance count).
- **Engines: clodex gateway aliases — planner `fable` xhigh, workers
  `opus` high** (human, 2026-07-23): Claude harness (Task/Skill/resume
  machinery, doperpowers loaded) with GPT engines via the local gateway.
  This runs the article's hybrid economics axis on our quota structure
  and keeps Anthropic subscription quota out of the fleet's blast
  radius. Rejected: native Anthropic models for the fleet (quota risk;
  deferred to the engine-mix matrix).
- **Codex review moves to wave cadence** (human, 2026-07-23; my
  recommendation accepted): per-packet clean-tree Codex review would
  serialize the fleet behind one reviewer; per-wave review on the
  integration branch keeps the decorrelated lens (different vendor)
  while matching roadmap §9.3's "small bounded review batches". The
  deterministic verifiers and fresh-context review remain per-packet.
  Rejected: per-packet (throughput collapse); T0/T1-only per-packet
  split (rule complexity without evidence it buys assurance).
- **The experiment node lives in the doperpowers tree; the campaign
  node lives in CC-Eng-Rev's tree** (X7): a single spec owning both
  would make one repo's roadmap answer to another's authority — exactly
  the two-pictures-of-reality failure the article's design docs exist to
  prevent. Rejected: one merged spec; a third neutral location (no
  standing purpose to parent it).
- **This spec is itself the first live decomposing run** — the
  gate was applied to the experiment goal (WELL-DEFINED after the
  three-question grill; not WELL-SCOPED: two repos, four distinct state
  owners — GH infra, CC-Eng-Rev governance, board, metrics — with
  different verification strategies), producing a five-child cut, one
  level, frontier-lazy (C3 stays coarse until its own run).

## Surprises & Discoveries

- The coordination machinery the article built ad hoc — split-brain
  prevention, shared design docs with checked references, decorrelated
  review — already exists here as doctrine (single-parent tree +
  hoisting, citation chain + Revision-Note flow-back, argus/Codex/
  deterministic-verifier stack). The two genuinely missing organs were
  the neutral integrator (C4) and stigmergy (X5).
- CC-Eng-Rev's conflict hot-spot is predictable BEFORE the run: the
  canonical evidence chain, not source files — its second campaign
  spent most of its wall clock in stale-chain regeneration loops. The
  article found its hottest file empirically; our substrate lets us
  design for it in advance (X3).
- One self-hosted runner = one job at a time; "unbounded fleet" is
  physically the count of registered instances. Width is therefore an
  honest tunable, not a protocol constant.

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION
check: verify Parent-Level Acceptance as written — all children landed
is not the same event — then retrospect.

## Revision Notes

- 2026-07-23: v1, born landed — grounded against CC-Eng-Rev live state
  and the Cursor article; the three load-bearing forks grilled and
  decided by the human (campaign sequencing, fleet/engine mix, review
  cadence) before authoring.
