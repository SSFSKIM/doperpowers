# [Goal Name] Roadmap (YYYY-MM-DD)

> **Parent:** [path + child id of the parent this goal descends from, or
> "root — the project's standing purpose", citing the CLAUDE.md top-goal
> line / root spec]. **Level name:** [the project's own word for this
> node — "Milestone 5", "Phase 2", … — annotation only; delete if the
> project doesn't use one]. **Consumes:** [existing canon/upstream
> artifacts this unit builds on, if any — delete if none; an artifact
> that participates in this unit's contracts or edges is a CHILD
> (possibly already landed), not a Consumes entry]. Children dispatch
> per their track hint; each child spec opens by citing this document
> (path + child id) — except a child that landed before this roadmap
> was cut: it cannot cite forward, so the citation runs backward (its
> child section and the Tracking Map point at its spec).

## Purpose

[Why this unit exists — the outcome it buys, in the project's terms.
Purpose first; mechanics later.]

## Parent-Level Acceptance

[The observable state that closes this unit AS A WHOLE — not the sum of
child acceptances. What can a user/operator do, see, or rely on when this
unit is done? Behavior-phrased, checkable. May include disjunctions over
child gates ("gate G2 passes OR the conditional spike's findings are
recorded") — state the disjunction here; the children's Required fields
carry its sides.]

## Grounding Baseline *(optional — delete if not measured)*

[The measured starting state the children's acceptances are relative to —
counts, coverage, error rates. This is where the pipeline's grounding
phase lands its numbers.]

## Children

### C1: [Child name] — [track hint: controlled | autonomous | spike (findings, never a merge) | decomposing]

- **Purpose:** [one paragraph — the child's reason to exist]
- **Acceptance:** [observable behavior that closes the child — one line
  or a short gate checklist; a child may declare multiple named gates,
  each flagged required or conditional — a conditional gate names when
  it becomes evaluable and what its failure triggers. A
  decomposing child may stay coarse: its precise gates emerge
  from its own cut]
- **Edges:** [blocked-by: — | C_n | C_n.G_k (gate-level when a child's
  gates diverge) | external:<condition> (a start-time gate — the child
  still runs); conditional-on: C_n's gate outcome or
  external:<condition> when WHETHER it runs is contingent; blocks: C_m]
- **Contracts:** [which Cross-Child Contracts it participates in, by id]
- **Required:** [required for parent acceptance | conditional — state the
  condition; per-gate flags when the child declares multiple gates]
- **Status:** [not-dispatched (annotate which: dispatchable now |
  blocked-by C_n | waiting-external | deliberately late — see Ordering) |
  conditional | in-flight | landed | parked]

### C2: …

## Cross-Child Contracts

[X1, X2, … — each a shared interface, invariant, ordering rule, or
definition two or more children must agree on. Exact names and shapes
where known. What is landed here is the AUTHORITY — who owns the
contract and whom it binds; content may be delegated to the owner child
(name the owner and the gate that delivers the content). Children
re-litigate neither. A contract — or a named clause of one — written to
outlive this unit says so; promoting it to the parent / root canon is a
closing-time action recorded in Outcomes.]

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
Progress section. Keep it current as children land. Children that close
early keep their retrospectives where they lived (child spec /
ExecPlan); this map points at them.]

## Decision Log

[Every landed decision with its rejected alternatives and why each lost.]

## Surprises & Discoveries

[Evidence-backed surprises from grounding and from children's flow-back.]

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check:
verify Parent-Level Acceptance as written — all children landed is not the
same event — then retrospect.

## Revision Notes

[Dated changes to this document after v1. A note that touches an
in-flight child's contract flags that child.]
