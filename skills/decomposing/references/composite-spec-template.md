# [Goal Name] (YYYY-MM-DD)

> **Parent:** [path + child id of the parent this goal descends from, or
> "root — the project's standing purpose", citing the CLAUDE.md top-goal
> line / root spec]. **Level name:** [the project's own word for this
> node — "Milestone 5", "Phase 2", … — annotation only; delete if the
> project doesn't use one]. **Consumes:** [existing canon/upstream
> artifacts this unit builds on, if any — delete if none; an artifact
> that participates in this unit's contracts or edges is a CHILD
> (possibly already landed), not a Consumes entry]. Children dispatch
> per their track hint, each carrying its section as its spec; each
> child's artifact (plan, ExecPlan, findings, PR, ticket — or a composite
> child's own composite spec) opens by citing this document (path + child
> id + parent pin) — except a child that landed before this cut: it
> cannot cite forward, so the citation runs backward (its child section
> and the Tracking Map point at its artifact). For a coupled
> goal this document is doperpowers:brainstorming's approved design
> spec extended in place — design up top, roadmap below, one document.

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

## Design *(thin or absent for an uncoupled bundle)*

[The design as matured with everything in view — architecture,
components, shared data models, interaction surfaces, failure
semantics — at the depth the design session actually produced.
Sub-structure freely: this section scales with the design, not the
template. For a coupled goal this is doperpowers:brainstorming's
approved design carried whole; the children below are derived from it.
Grade the content: mark **[binding — <joint-view reason>]** on
decisions the whole picture settled — children never re-litigate
these. Everything unmarked is advisory inheritance a child may
overturn with evidence via a dated Revision Note. Empirical unknowns
the design could not answer are named here as delegated unknowns and
assigned to the child or spike that will answer them.]

## Children

### C1: [Child name] — [track hint: controlled | autonomous | direct | spike (findings, never a merge) | decomposing]

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
- **Design inheritance:** [the Design sections/decisions that bear on
  this child, by heading or decision id — authority grades travel with
  them; delete if the Design section is absent]
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
drops; on a board-run project these may also register as parked tickets
citing this composite spec, so overflow outlives this list. **Explicitly out
of scope (standing exclusions):** things this unit will never do; if
one is also an invariant, cross-reference its contract id.]

## Tracking Map

[child id → artifact (plan / ExecPlan / findings / composite spec / PR) or
ticket # / status. This map plus the children's Status fields IS this
unit's progress record — there is no separate Progress section. Keep it
current as children land; a landed child's row carries its closing
evidence, and that row plus its closing artifact is the child's
retrospective.]

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
