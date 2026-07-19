# [Unit Name] Roadmap — [Milestone | Epic] (YYYY-MM-DD)

> **Altitude:** [Milestone → Epics | Epic → Slices]. **Parent:** [path +
> unit id of the roadmap this unit belongs to, or "none — top of ladder
> for this project"]. **Consumes:** [existing canon/upstream artifacts
> this unit builds on, if any — delete if none]. Children dispatch per
> their track hint; each child spec opens by citing this document (path +
> child id).

## Purpose

[Why this unit exists — the outcome it buys, in the project's terms.
Purpose first; mechanics later.]

## Parent-Level Acceptance

[The observable state that closes this unit AS A WHOLE — not the sum of
child acceptances. What can a user/operator do, see, or rely on when this
unit is done? Behavior-phrased, checkable.]

## Grounding Baseline *(optional — delete if not measured)*

[The measured starting state the children's acceptances are relative to —
counts, coverage, error rates. This is where the pipeline's grounding
phase lands its numbers.]

## Children

### C1: [Child name] — [track hint: controlled | autonomous | roadmapping]

- **Purpose:** [one paragraph — the child's reason to exist]
- **Acceptance:** [observable behavior that closes the child — one line
  or a short gate checklist; a child may declare multiple named gates,
  each flagged required or conditional]
- **Edges:** [blocked-by: — | C_n; conditional-on: C_n's gate outcome,
  or external:<condition> when the precondition is not a sibling;
  blocks: C_m]
- **Contracts:** [which Cross-Child Contracts it participates in, by id]
- **Required:** [required for parent acceptance | conditional — state the
  condition; per-gate flags when the child declares multiple gates]
- **Status:** [not-dispatched | conditional | in-flight | landed | parked]

### C2: …

## Cross-Child Contracts

[X1, X2, … — each a shared interface, invariant, ordering rule, or
definition two or more children must agree on. Exact names and shapes
where known; a contract here is landed — children do not re-litigate it.]

## Ordering & Dependency Map

[The edges in one view — which children can run in parallel, which
sequence is forced, and why.]

## Risks & Mitigations *(optional — delete if none identified)*

[Anticipated failure modes at unit level and the mitigation each child or
contract carries. Not Surprises — those are discovered; these are
foreseen.]

## Deferred / Out of Scope

[Two kinds — keep them apart. **Deferred (may return):** work that
surfaced but belongs to the next unit — named reservations, not silent
drops. **Explicitly out of scope (standing exclusions):** things this
unit will never do; if one is also an invariant, cross-reference its
contract id.]

## Tracking Map

[child id → spec path / ticket # / status. This map plus the children's
Status fields IS this unit's progress record — there is no separate
Progress section. Keep it current as children land.]

## Decision Log

[Every landed decision with its rejected alternatives and why each lost.]

## Surprises & Discoveries

[Evidence-backed surprises from grounding and from children's flow-back.]

## Outcomes & Retrospective

Pending — written when the unit closes. [Children that close early keep
their own retrospectives where they lived (child spec / ExecPlan); the
Tracking Map points at them.]

## Revision Notes

[Dated changes to this document after v1. A note that touches an
in-flight child's contract flags that child.]
