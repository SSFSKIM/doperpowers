# Ideadump Triage & Roadmap (2026-07-30)

> **What this is:** the umbrella record of the 2026-07-30 roadmapping
> session — a human ideadump (accumulated notes: council/roles, ticket
> board & ledger, cattle sessions, control plane, methodology) triaged
> against code and research reality, then matured epic-by-epic through
> grills. Adapted from doperpowers:organizing-sprints (phases 1–3 + the
> grill), with two deltas the human set: per-epic maturation instead of
> one sprint umbrella, and cloud-scale items folded into the research
> round instead of sprint tickets. **Governing context declared mid-
> session (recorded in memory `cloud-native-pipeline-pivot`):** the board
> SSOT moves from GitHub Issues to the Postgres AI-native board (GH and
> Linear become one-way mirrors), and doperpowers designs for the cloud
> runtime (k8s + gVisor + cc-harness) as a complete agent swarm system.

## Disposition summary (the cleanup)

Classes per organizing-sprints: [BUILT] already exists; [PARTIAL] delta
only; [SUPERSEDED] answered by later decisions; [TENSION] conflicted
with recorded doctrine (resolved in the epics); [NOT-BUILT] real work.

| ideadump item | disposition | where it landed |
|---|---|---|
| QAgent (review worker orchestrating codex rounds + fix waves) | [BUILT] | reviewing-prs v7.25 multi-lens engine; E1 adds the role name, the Opus-high pin, and the declared fix-wave agent |
| Implementer (Opus) + small-work fast path | [BUILT] | implementing-tickets DIRECT mode; C6 flips the default route |
| Architect (Fable plan author) | [NOT-BUILT] → **E1 spec** | 2026-07-30-implement-lane-split-design.md |
| Architect council / advisor subagent | [PARTIAL] | critique (v7.26) + plan-reviewer (v7.27) + spec-review pass; E1 scales council by artifact shape |
| Architect reviews implementer, then QAgent | [TENSION] → dropped | human correction: Architect ends at the plan; no-orchestrator-judge preserved |
| Batch grill | [BUILT] | the park format (numbered questions + recommended answers) + board-answer relay; no new reference file |
| XML-tag / SessionStart role injection | [SUPERSEDED] | the worker-bootstrap pattern (pinned ROLE + PROTOCOL_FILE, runtime-opened) is the mechanism; hooks stay removed |
| Self-compact policy | deferred | E1 Deferred (adopt when a policy hardens) |
| Frontmatter-markdown ticket board | [SUPERSEDED] | placeholder for "not GH"; the substrate answer is the Postgres board (pivot) — GH/Linear demoted to mirrors |
| Ticket field list ("anything more?") | [BUILT] | v8 schema covers it (incl. bound-session attach handle); E1 adds `plan:` meta + lane states |
| Report ledger replacing final-message reporting | [TENSION] → **E2 spec** | hybrid: authored decisions + derived read-only stream (2026-07-30-ticket-ledger-observability-design.md) |
| Branch topology = ticket topology; accountable-agent model | [BUILT] | worktree/branch per ticket; board-bind; subagents excluded from board writes (restated in E2) |
| Human attach/steer (ssh, PID) | [BUILT/DESIGNED] | local daemon attach + interactive-preferred lane; cloud doors recorded in the 07-30 pivot memory |
| Ticket rename | closed | "ticket" stays (E2); UI display naming deferred to the platform |
| Cross-pod agent messaging | [NOT-BUILT] | R-round material (appserver WS is the candidate seam) — E4 fold |
| Decoupled pod (session/bash/subagent), bg survival, subagent revive | [NOT-BUILT] → **E4 fold** | into R1 (runtime gap analysis) / R2 (platform) briefs; "every tool call a container" resolved against envelope asymmetry — decouple lifetime-asymmetric tools only |
| Code-exec sandbox need | [DECIDED] | gVisor + run-class egress + virtual keys (pivot); srt-inside-gVisor probe pending |
| Tree + kanban surfaces | [BUILT] | BOARD.html; ported onto the board API by **E3 spec** |
| Needs-human queue + answer-wakes-worker | [PARTIAL] → **E3 spec** | mechanics shipped (board-answer/sweep, appserver decisions-as-state); E3 adds the unified two-backend queue UI (2026-07-30-control-plane-product-design.md) |
| env-issue / friction report tool | [PARTIAL] → **E2 spec** | board-native `env-issue` category, fire-and-continue |
| Web UI + embedded terminal → macOS app | [NOT-BUILT] → **E3 spec** | human-fixed direction; web terminal over appserver WS; native ghostty at the app phase |
| Mature-first-then-decompose; spine-design path | [BUILT]/checked → **E5 verdict** | see below — no skill change |

## Epic outcomes

- **E1 — Implement lane split** →
  `docs/doperpowers/specs/2026-07-30-implement-lane-split-design.md`
  (v1.1 after independent fable review; all 8 findings adopted).
  Relay: `ready-for-architect` → `in-design` → `ready-for-implementer`
  → `in-progress` → review loop. Plan authorship exclusive to Fable;
  no intake gate; convergence tie-breakers; three-address park
  discriminant; skill split `architecting` + `implementing`; QAgent =
  ONE Opus high + fix-wave agent (Opus medium). X4 narrowing
  (architect dispatch exempt from `engine:*`) human-confirmed
  2026-07-30.
- **E2 — Ticket ledger & observability** →
  `docs/doperpowers/specs/2026-07-30-ticket-ledger-observability-design.md`.
  Hybrid ledger; append-only events + mutable current-state; write
  authority; `env-issue` lane; "ticket" kept.
- **E3 — Control-plane product** →
  `docs/doperpowers/specs/2026-07-30-control-plane-product-design.md`.
  Standalone repo; four surfaces; unified queue; web terminal over
  appserver WS; macOS app phase. Division gated on the research round.
- **E4 — Cattle runtime** → no separate spec. Folds into the clean-slate
  round briefs: R1 carries run-state externalization beyond the
  sessionStore (bg-process registry, subagent-as-detached-harness-
  session with own transcript → revive/resume), R2 carries the pod
  anatomy and cross-pod messaging seam. **The round still awaits the
  human's explicit go.**
- **E5 — Methodology ordering check** → **no change.** The armed
  one-sentence fix on `archive/decomposing-gate-synthesis` ("The checks
  run in order: an unclear goal is never divided — WELL-DEFINED failures
  resolve first…") is exactly the ideadump's doctrine, and it stays
  archived because its trigger ("live use shows a fuzzy goal carved into
  children") has not been observed: the review-stack roadmap's C1 spike
  front-loaded the unknown (the emergent ordering working), C3's
  rescission was evidence-driven flow-back, the swarm roadmap is
  undispatched, and the cloud program did spine-first correctly without
  a clause. Spine-design codification declined on the same
  no-observed-failure ground (writing-skills bar + constraint
  minimization). The contingency remains armed with its trigger.

## Implementation routing & standing gates

Nothing in this session implemented anything — five documents and one
verdict landed. Routing:

- **E1 + E2 implementation** = doperpowers skill/script work (migration
  surfaces inventoried in the specs), sequenced with review-stack C5/C6
  so dispatch scripts are touched once. The state machine is
  substrate-neutral: **implementable on the interim GH board now, or
  deferred to the Postgres board — the human's call at dispatch.**
- **E3 implementation** = the new platform repo, gated on the research
  round (R2 fixes board-service internals; then the platform decomposing
  run cuts children).
- **E4** rides the round briefs.
- Standing gates unchanged: A0 plan execution deferred; swarm campaign
  approval-gated; **R1–R4 clean-slate round awaits the explicit go**.

## Decision Log

Per-epic decisions live in the epic specs (single copies). This umbrella
records only its own:

- Decision: per-epic maturation through brainstorming grills instead of
  one organizing-sprints umbrella spec + board materialization.
  Rationale: the dump mixed plugin-maturation items with a product/cloud
  program mid-pivot; one sprint umbrella would have chained unrelated
  acceptances and materialized tickets onto a board whose substrate is
  itself changing.
  Date/Author: 2026-07-30, human ("/organizing-sprints style but not
  exactly").
- Decision: cloud-scale items fold into the existing R1–R4 round rather
  than becoming epics here.
  Rationale: the round already owns runtime/platform research; duplicate
  epics would fork the program's spine.
  Date/Author: 2026-07-30, session, per the pivot memory.

## Surprises & Discoveries

- Observation: more than half the dump was already built, superseded, or
  deliberately decided — the notes predate the v7.26–7.28 landings
  (critique, plan-reviewer, multi-lens, skill diet) and the 07-30 cloud
  pivot. The triage's main value was mapping each note to where its
  intent already lives.
  Evidence: the disposition table above.
- Observation: two ideadump tensions dissolved without loss by finding
  the third option — the ledger (derived view instead of authored prose
  vs. silence) and the architect review (relay phase instead of judge
  vs. no hot-context review at all).
  Evidence: E2 Decision Log; E1 Decision Log ("Architect ends at the
  plan").

## Outcomes & Retrospective

Pending — written when the epics' implementations land and the round
completes.

## Revision Notes

- 2026-07-30: v1, closing artifact of the roadmapping session (triage →
  E1 → E2 → E5 → E3, with E4 folded).
