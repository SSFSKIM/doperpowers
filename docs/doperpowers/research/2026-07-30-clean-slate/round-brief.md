# Clean-Slate Round Brief — R1–R4 (2026-07-30)

> **Status:** brief committed for the human's review; **the round does NOT
> launch from this document alone — it launches on the human's explicit
> go.** Trigger: the 2026-07-30 pivot (native-binary premise replaced by
> cc-harness co-design; both tiers k8s+gVisor human-fixed; board SSOT →
> Postgres). Reports land beside this file as `r1–r4-*.md`; the round
> closes with a synthesis reference-architecture spec authored
> interactively with the human (successor to both 2026-07-23 specs).

## Source ledger (human-confirmed 2026-07-30)

**Class A — binding inputs (the round may not re-litigate):**
the 07-30 pivot decisions (both tiers k8s+gVisor; runtime = cc-harness
co-designed with the environment; Postgres SSOT board; GitHub
Issues/Linear as one-way mirrors); the two governing principles (sidecar
necessity ∝ 1/credential-substitutability; decouple only across envelope
asymmetry); the roadmapping specs
`2026-07-30-implement-lane-split-design.md` (v1.2),
`2026-07-30-ticket-ledger-observability-design.md`,
`2026-07-30-control-plane-product-design.md`, and the triage umbrella;
the standing gates (A0 plan execution deferred; swarm campaign
approval-gated; E1/E2 implementation timing = human's call).

**Class B — citable external input (evidence; conclusions non-binding):**

- `research/2026-07-23-cloud-scale/` — all 10 files, used as-is
  (human-confirmed; its substrate conclusions align with the fixed
  direction — r2-sandbox-substrate already recommended the Agent
  Sandbox shape).
- `research/2026-07-23-startup-scale/` — all 5 files, retained with
  assigned roles: `zero-ops-economics-a0.md` = **R4's baseline
  counterfactual**; `sandbox-substrate-a0.md` = R2's
  rejected-alternatives record (managed market + flip triggers);
  `managed-postgres-core.md` = substrate-independent Postgres facts the
  board service sits on (SKIP LOCKED under transaction pooling;
  LISTEN/advisory need direct connections); `board-simplification-a0.md`
  = thin-board-service lineage (R2 seed with A0 Plan 1);
  `managed-agents-substrate.md` = R1's what-a-runtime-provides
  comparison prior. The Stack M headline conclusion is dead; the Linear
  one-way-mirror pattern survives, generalized to the GH mirror.
- The two 2026-07-23 specs (enterprise reference architecture incl. its
  DL entries; startup A0 profile incl. DL11–15) and the four A0 plans
  (Plan 1 board service = R2 seed; Plan 2 quota breaker ↔ cc-harness
  `limitState`).

**Class C — live-truth sources (never trusted from prose; re-verified at
use):** cc-harness `docs/parity/coverage.md` (the capability scorecard is
the source of truth) and `probes/` (live-probe-first: every "the SDK
can/can't X" claim is probe-run, never read off `sdk.d.ts`); GKE Agent
Sandbox upstream (CRD facts re-fetched at use); current vendor pricing
(07-23 numbers are stale by policy).

## The through-question (deliberately not pre-decided)

**Do A0 and enterprise unify into ONE architecture with two scale knobs,
or remain two designs?** The pivot fixed the substrate for both tiers;
whether that collapses the tier split entirely is the round's central
open question — R1–R3 supply the structural evidence, R4 the economic
verdict.

## R1 — Runtime gap analysis & co-design (cc-harness)

- **Questions:** which native-CC parity gaps matter for swarm workers
  (from the scorecard, claims re-verified live); run-state
  externalization beyond the sessionStore — bg-process registry,
  **subagent-as-detached-harness-session** (own transcript → revive or
  resume; the "6 shells + 5 subagents die with the session" case), and
  what state remains structurally unrecoverable; the exec-decoupling
  boundary applied per envelope asymmetry (bg Bash and Task decouple;
  Read/Write/Edit hot loop never); OTel/hook wiring sufficient for E2's
  derived ledger stream (which of the 17/30 headless hook events carry
  it); fleet auth (API-key/LLM-gateway virtual keys, never OAuth
  subscription); the appserver WS as the cross-pod agent↔agent seam.
- **Probes:** subagent-as-detached-session; pod footprint (Node+CLI
  memory/disk); cross-pod appserver reachability.
- **Deliverable:** `r1-runtime-gaps.md` — gap table
  (exists / needs-build / impossible) + co-design proposals for the
  cc-harness backlog.
- **Staffing:** fable researcher.

## R2 — Platform: k8s + Agent Sandbox + board service

- **Questions:** cluster shape (GKE Standard+CUD vs self-managed
  vs Autopilot; adopt the Agent Sandbox CRDs vs self-host the
  template/warm-pool/claim shape); warm-pool sizing vs claim latency;
  run-class egress enforcement; virtual-key brokering placement;
  srt-inside-gVisor viability; **board-service internals** — schema (E1
  lane states incl. `in-design`; E2 append-only events + mutable
  current-state + `env-issue` category), claim path on the
  managed-postgres-core facts, mirror writers (GH Issues, Linear),
  and one-Postgres convergence (board + sessionStore cohabitation:
  schemas, retention, load separation).
- **Probes:** srt-inside-gVisor (the morphed T2).
- **Deliverable:** `r2-platform.md` + a board-service schema draft (the
  E3 platform decomposing run's input).
- **Staffing:** fable lead (may dispatch opus subagents for schema
  drafting).

## R3 — Agent-operated ops (T5 absorbed)

- **Questions:** the ops-agent responder (substrate independent of the
  cluster it fixes — where it runs); its intake = the E2 `env-issue`
  lane + OTel alerts + board reclaim signals; runbook surface and
  authority boundaries (what it may restart/scale without a human); the
  tail-incident taxonomy (from `lessons-learned.md`); the MTTR spike:
  2–4 weeks of synthetic load on the R2 platform shape, promotion bar =
  ≤1 human intervention/week, MTTR ≤1 workday, ≥2× cheaper than the
  managed-sandbox band.
- **Deliverable:** `r3-agent-ops.md` + the spike plan (spike EXECUTION
  is separately gated — it spends real infra).
- **Staffing:** fable.

## R4 — Economics remeasure

- **Questions:** replace the crossover math's human-engineer constant
  with the agent-ops token cost (the $200–500/mo band, refined by R3);
  re-price the self-host vs managed bands at both tiers on live pricing;
  token:infra ratio check; rewritten flip triggers (under what
  conditions would managed RE-enter?); the economic half of the
  through-question verdict.
- **Baseline:** `zero-ops-economics-a0.md` — the remeasurement's
  counterfactual.
- **Deliverable:** `r4-economics.md`.
- **Staffing:** opus researcher (bounded remeasure against a fixed
  baseline), fable synthesis at round close.

## Sequencing & execution mode

Probes run FIRST at go (cheap, parallel, de-risking). Then **R1 ∥ R2**
(independent evidence bases; one contract — R1's runtime facts feed R2's
pod anatomy; reconciled at synthesis). **R3 after R2** (ops is designed
against the platform shape). **R4 last** (consumes all costs). Round
close: the synthesis reference-architecture spec, authored in an
interactive session with the human (grill + council per house
methodology), citing the r1–r4 reports as its base — the same
read-once-then-cite discipline as the 07-23 rounds. Researchers are
subagents dispatched from the orchestrating session (the 07-23 pattern),
bound by the live-probe-first rule.

## What the round does NOT do

No implementation. No cluster spend without the separate spike go. No
board migration. No re-litigation of Class A. Standing gates unchanged.

## Decision Log

- Decision: startup-scale folder retained as Class B with per-file
  roles.
  Rationale: R4 loses its counterfactual and R2 re-surveys the managed
  market without it; only the Stack M conclusion is dead. Rejected:
  discarding the folder.
  Date/Author: 2026-07-30, human ("그렇게 진행하도록 해" on the proposed
  ledger).
- Decision: cloud-scale folder used as-is.
  Rationale: its substrate conclusions already match the human-fixed
  direction.
  Date/Author: 2026-07-30, human.
- Decision: the through-question (one architecture, two knobs?) is left
  open for the round.
  Rationale: pre-deciding it would make R4 ceremony.
  Date/Author: 2026-07-30, session.
- Decision: probes precede research.
  Rationale: live-probe-first house discipline (the A1 lesson) — three
  cheap probes de-risk every downstream design claim.
  Date/Author: 2026-07-30, session.

## Surprises & Discoveries

- Observation: both local credentials were exhausted during the probe
  phase (OAuth subscription weekly limit, resets 2026-08-03; API key
  "Credit balance is too low"), so no probe completed a live model turn.
  The probes were re-cut into keyless evidence (real on-disk
  transcripts via the SDK read API, process-lifecycle tests through the
  spawnClaudeCodeProcess/sessionFactory DI seams, shipped-bundle source
  reads); each report lists what a credited/cluster environment must
  still verify. The failure itself became evidence: R1 adopts it as a
  live demonstration that subscription OAuth is a fleet-wide single
  point of failure — fleet auth must be API-key/virtual-key.
  Evidence: probes/p1–p3 reports, r1-runtime-gaps.md fleet-auth section.
- Observation: Agent Sandbox is no longer a GKE-only product — it is a
  vendor-neutral Kubernetes SIG-Apps subproject
  (kubernetes-sigs/agent-sandbox, agents.x-k8s.io/v1beta1), which
  collapses the 07-23 "adopt the product vs self-host the shape" fork
  into adopt-upstream.
  Evidence: r2-platform.md §CRDs.
- Observation: the durability boundary is the TURN, not the session —
  the engine writes transcripts only at turn boundaries, so a pod
  evicted mid-turn loses the in-flight turn in any store; parked
  decisions are in-process memory. Engine-owned, unfixable from
  outside; design-around only.
  Evidence: probes/p2 §4 (probe 71 + recorded probe 62), r1 gap table.
- Observation: R4 measured the whole self-host-vs-managed question at
  ~1% of all-in spend, while the E1 architect-lane mix (Fable ≈ 5× a
  Sonnet run) is worth 12–49× more per month — the model-mix dial
  dominates every infra decision. R4 also dissents from R2 on the
  Autopilot knob (≈ managed-vendor parity at A0 → recommends retiring
  it in favor of GKE Standard + Spot at both tiers).
  Evidence: r4-economics.md keyFindings.
- Observation: all four Rs independently converged on the
  through-question — one architecture, two knob-sets (procurement
  instrument, warm-pool size, sidecar presence, ops-catalog size) —
  from four different evidence bases.
  Evidence: the through-question sections of r1–r4.

## Outcomes & Retrospective

Round closed 2026-07-30 with the synthesis spec
`docs/doperpowers/specs/2026-07-30-swarm-reference-architecture-design.md`
(successor to both 2026-07-23 specs, banners added).

**Against the through-question: answered — one architecture, knob-set
tiers.** All four Rs converged independently (runtime forces no fork;
platform CRD layer identical; ops framework tier-invariant; one cost
function with procurement knobs), and the synthesis settled the three
queued forks with the human: Autopilot retired to break-glass (R4's
dissent adopted, reframed as the spike-failure fallback), promotion-bar
comparator pinned to the capability-parity managed band (making Spot a
spike design requirement), and run-class egress fixed as
credential-aligned three layers (the human's auto-mode challenge
reshaping R2's blanket default-deny; the 07-29 research-lane proxy
demoted to an enterprise hardening knob).

**What worked:** probes-first sequencing paid for itself — P2/P3
supplied the evidence R1 leaned hardest on, and even the probe-phase
*failure* (shared OAuth weekly limit) became the fleet-auth decision's
strongest evidence. The 3-class source ledger held: no Class A item was
re-litigated, and the startup-scale retention (R4 baseline) enabled the
like-for-like crossover remeasure that produced the round's biggest
number (crossover 300–500 → 5–8 concurrent).

**What remains:** the cc-harness backlog (T1–T13, pre-spike set
T5+T6+T12), the E3 platform decomposing run (now unblocked on
r2-board-schema.md), the separately-gated MTTR spike, and the in-cluster
verification lists (r1 §5, r2 §8, r3 §7) — every unverified claim stayed
tagged rather than smoothed over, which is the round's standing hygiene
for the cluster day it all gets tested.

## Revision Notes

- 2026-07-30: v1, authored on the human's source-ledger confirmation;
  awaiting the explicit go to launch.
- 2026-07-30: round EXECUTED on the human's go, as a background
  workflow (8 agents: probes P1–P4 = sonnet/opus/opus/sonnet; R1/R2/R3
  = fable; R4 = opus; ~1.48M subagent tokens, ~60 min). All
  deliverables landed: probes/p1–p4, r1-runtime-gaps.md,
  r2-platform.md + r2-board-schema.md, r3-agent-ops.md,
  r4-economics.md. Surprises recorded above. Remaining: the
  interactive synthesis reference-architecture spec with the human;
  queued human decisions at round close — R4-vs-R2 Autopilot knob
  (retire vs keep as A0 entry) and R3's promotion-bar comparator
  pinning (capability-parity managed sandboxes vs whole band).
