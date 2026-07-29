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

(none yet — filled during the round)

## Outcomes & Retrospective

Pending — written at round close, against the through-question.

## Revision Notes

- 2026-07-30: v1, authored on the human's source-ledger confirmation;
  awaiting the explicit go to launch.
