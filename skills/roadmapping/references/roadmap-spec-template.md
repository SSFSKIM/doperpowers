# [Unit Name] Roadmap — [Milestone | Epic] (YYYY-MM-DD)

> **Altitude:** [Milestone → Epics | Epic → Slices]. **Parent:** [path +
> unit id of the roadmap this unit belongs to, or "none — top of ladder
> for this project"]. Children dispatch per their track hint; each child
> spec opens by citing this document (path + child id).

## Purpose

[Why this unit exists — the outcome it buys, in the project's terms.
Purpose first; mechanics later.]

## Parent-Level Acceptance

[The observable state that closes this unit AS A WHOLE — not the sum of
child acceptances. What can a user/operator do, see, or rely on when this
unit is done? Behavior-phrased, checkable.]

## Children

### C1: [Child name] — [track hint: controlled | autonomous | roadmapping]

- **Purpose:** [one paragraph — the child's reason to exist]
- **Acceptance:** [observable behavior that closes the child]
- **Edges:** [blocked-by: — | C_n; blocks: C_m]
- **Contracts:** [which Cross-Child Contracts it participates in, by id]
- **Status:** [not-dispatched | in-flight | landed | parked]

### C2: …

## Cross-Child Contracts

[X1, X2, … — each a shared interface, invariant, or ordering rule two or
more children must agree on. Exact names and shapes where known; a
contract here is landed — children do not re-litigate it.]

## Ordering & Dependency Map

[The edges in one view — which children can run in parallel, which
sequence is forced, and why.]

## Deferred / Next-Unit Reservations

[Work that surfaced but belongs to the next unit — named reservations,
not silent drops.]

## Tracking Map

[child id → spec path / ticket # / status. This map plus the children's
Status fields IS this unit's progress record — there is no separate
Progress section. Keep it current as children land.]

## Decision Log

[Every landed decision with its rejected alternatives and why each lost.]

## Surprises & Discoveries

[Evidence-backed surprises from grounding and from children's flow-back.]

## Outcomes & Retrospective

Pending — written when the unit closes.

## Revision Notes

[Dated changes to this document after v1. A note that touches an
in-flight child's contract flags that child.]
