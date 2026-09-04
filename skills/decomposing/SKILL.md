---
name: decomposing
description: Use when a goal is too big for one agent to reliably own as one unit and its pieces must become child goals (a roadmap), or when tending a live goal tree as children land. A single ownable idea is doperpowers:brainstorming; a pile of raw observations is doperpowers:organizing-sprints.
---

# Decomposing

## Overview

Work is a tree of goals. Every node is a goal — a purpose with observable
acceptance — whatever the project calls it: milestone, epic, phase, slice,
ticket. doperpowers:brainstorming DEFINES one goal at a time, whatever its
size — and for a goal whose pieces interact, MATURES the joint design
before handing it here; this skill DIVIDES a goal that fails the gate
below into child goals one level down, and tends the tree as children
land; the tracks (brainstorming → spec → plans, or doperpowers:execplan)
EXECUTE the leaves. The product of one run is a **composite spec** per
`references/composite-spec-template.md` — the same species as any
living spec (doperpowers:execspec), not a separate document type:
design at the center, with the roadmap topology (children, edges,
ordering) embedded as sections. Composite carries its
Composite-pattern sense — a composite's child can itself be a
composite, at every altitude; decomposing yields this spec,
recomposition closes it. The document tree is the composite tree: one
spec per composite, none per leaf. A child's contract is its section
here; its own document is its execution artifact — a plan, an ExecPlan,
a spike's findings — or its own composite spec when it is a composite in
turn. The composite spec carries the matured design where one
exists; children with purpose, observable acceptance, and dependency
edges; the contracts that cross them; and a living tail that tracks the
unit to its retrospective.

This is the deliberate sibling of doperpowers:organizing-sprints. That
skill turns raw *testimony* (an ideadump that may misread the code) into a
sprint; this one divides trusted *intent*. Same output shape, different
intake — here there is no verification table, but grounding still matters
(see the pipeline).

## The Gate

One criterion decides division, at every altitude — the same two checks as
the board's ticket gate (doperpowers:issue-tracker
`references/ticket-gate.md` is its board rendering):

- **WELL-DEFINED** — every fork the work will hit has an owner or an
  answer: purpose stated, acceptance observable, load-bearing decisions
  made. Fails ⇒ what's missing is KNOWLEDGE — grill it
  (doperpowers:brainstorming) when a conversation can close it; make it a
  child whose deliverable is findings (a spike or research goal) when it
  needs real work.
- **WELL-SCOPED** — one agent can reliably own it as one unit. "One
  agent" means one accountable context: an owner may marshal subagent
  workers (an SDE plan's task workers, an ExecPlan's milestones) without
  that being decomposition — execution mechanics live below the tree's
  resolution. Fails ⇒ divide into work-children.

A goal that passes the gate is a LEAF whatever its size — it dispatches to
its track, and this skill's reach ends. Reliably-ownable is a moving
envelope, not a size class: big-but-coherent work that one context can
carry is one leaf (evidence: an epic-sized phase correctly ran as a single
ExecPlan). Depth is an output of the gate, never a target, and it is
asymmetric by nature: one branch bottoms out in a single ExecPlan while
its sibling divides twice more.

**Split signals** (any altitude): parts with different state owners,
invariants, failure modes, or verification strategies; acceptance you can
only phrase by chaining unrelated behaviors with "and"; grill forks whose
answers keep depending on other unanswered forks. **Keep together:**
splitting would create an invalid intermediate state; parts must land in
the same transaction or cutover; neither part is meaningful or verifiable
alone. Below the slice the same signals govern splitting inside one plan —
doperpowers:writing-plans' Conditional Sub-Slicing is this list applied
there.

## The Tree

- Decomposition is a TREE: every child has exactly one parent — its
  reason to exist and its flow-back address. A subgoal two parents need is
  hoisted to their common ancestor as its own child; the shared need
  becomes dependency edges, never a second parent.
- Dependencies are EDGES, not structure: typed (`blocked-by`,
  `conditional-on`, `external:<condition>`), cross-branch allowed,
  acyclic. The tree says what adds up to what; the edges say what waits
  for what.
- Levels have no canonical names. Milestone, Epic, Phase, Sprint are
  project vocabulary — annotate nodes with the project's words; never make
  the doctrine speak them.
- The ROOT is the project's standing purpose. Convention: CLAUDE.md
  states the top-level goal as short prose; a project that keeps a
  standing root spec routes to it from that line. Every new goal enters
  the tree by being situated against the root or an existing node —
  brainstorming's job, not this skill's.
- No OR-branches: the tree records the chosen division; alternatives live
  in the Decision Log.
- NO NEW SUBSTRATE: the tree is not a registry file. It IS the citation
  chain (each child's artifact — plan header, ExecPlan, PR body, ticket,
  or a composite child's own spec — opens by citing its parent), the
  board's typed edges, and the composite specs' tracking maps.

## The Frontier

The frontier governs COMMITMENT, not capture. Divide one level per run,
and cut a branch only as it nears execution: child boundaries, gates,
and binding contracts drawn today for far-off work go stale as landed
siblings move them, and an undivided branch is cheap to re-cut. A child
whose own division can wait carries the track hint "decomposing run at
dispatch" and nothing more. Design prose is the opposite case — whatever
the joint view produced about a distant branch stays in the parent at
the depth it was produced, as advisory inheritance (see the Derivation
Contract): expected to be revised by the time the branch nears dispatch,
and cheap to revise precisely because it was written down. A composite
spec is BINDING near the frontier and advisory in the distance;
staleness in advisory content costs a Revision Note, while an
uncaptured insight is unrecoverable.

## Recomposition

All children green does not close a parent. The parent declares its own
acceptance at cut time — the observable state that closes the unit AS A
WHOLE, not the sum of child acceptances — and when the children have
landed, closing the parent is a VERIFICATION event against that acceptance
(integration seams, end-to-end behavior). Only then does the retrospective
write.

On the board that verification is a dispatch. When the last child goes
terminal the parent RETURNS to `ready-for-architect` (`recomposition-due`)
instead of closing — the only state an epic is dispatchable in — and an
Architect issues the verdict. A non-code parent closes on its
verification evidence directly. A code-bearing one — children that
touched one executable surface, cross-child invariants, multi-repo
composition, or a composite spec that marks review required — posts a closure
package and goes to `in-review` for a SCALE REVIEW, whose clean verdict
closes the parent and whose defects become corrective children (the
parent waits and recomposes again). The shape of the unit gates which
path runs; nothing about it is a status flip.

<HARD-GATE>
Materialization onto the issue board is gated on the human approving the
written composite spec. Registering a unit's worth of tickets is an
outward-facing batch action — do not touch the board before approval.
</HARD-GATE>

## Upward Revision

Children read the parent's current state at dispatch — the dispatch
machinery stamps `parent-pin:` (the parent, plus a hash of the parent's
body as the child received it) into the child
so "what contract did this child execute" is always answerable. A child
revises its own means freely — and overturning advisory inheritance is
revising means: the child records the overturn itself as a dated
Revision Note on the parent (evidence in a line) and moves on, no
reconciliation. Discovery that touches a parent-owned end — purpose,
acceptance, a cross-child contract, an edge, a BINDING design decision,
the division itself — becomes a `[parent-impact]` comment on the child's
own ticket (evidence + affected clauses; binding content the child
never edits). The sweep returns the parent to `ready-for-architect`
(`reconciliation-due`); the reconciling Architect judges materiality,
updates the parent's living tail, and flags affected in-flight
children. Purpose changes and material acceptance reductions go to the
human. At final recomposition the Architect runs the lineage check:
every child's pin against the final parent revision — incorporated,
explicitly irrelevant, or a corrective child.

## The Pipeline

Create a task per phase; complete them in order.

Intake has two shapes. A COUPLED goal arrives as a matured, approved
design — doperpowers:brainstorming matured it precisely because its
pieces interact; that design document is this run's primary input, and
the roadmap sections extend it in place (one document: design up top,
roadmap below). An UNCOUPLED bundle arrives undesigned — its pieces
share no design surface, so there was nothing to mature jointly; phases
2–3 do the defining work here, and the design sections stay thin.

1. **Ground the goal** — explore the code and repo state it touches.
   Intent is trusted here, but a question the codebase can answer is
   answered by reading, never asked. For matured intake, verify the
   design's load-bearing code claims rather than re-deriving them.
2. **Derive or propose the cut** — from a matured design, derive
   children along its natural seams and grade each design decision's
   authority (binding with its joint-view reason; advisory otherwise —
   see the Derivation Contract). For an uncoupled bundle, propose
   tentative children as goals with ordering and get the human's
   reaction BEFORE deep grilling. Either way, check each child against
   the code for already-built or partially-built reality: deliberate
   initiatives assume greenfield more often than the code is.
   Over-merging hides independent shippables; over-splitting loses
   coherence — ask when unsure.
3. **Grill the residue** — batched frontier rounds, each question with
   your recommended answer (doperpowers:brainstorming's grill protocol):
   child boundaries, dependency edges, cross-child contracts, authority
   grades, and reservations that belong to a later cut rather than this
   one. A matured design has already answered its architectural
   questions — don't re-grill them; an uncoupled bundle needs each
   piece's purpose and acceptance grilled here.
4. **Author the composite spec** — per `references/composite-spec-template.md`,
   born landed: v1 already carries the design and the grill's decisions,
   with the living tail of doperpowers:execspec. For matured intake,
   extend the approved design spec in place rather than opening a
   second document.
5. **Self-review, then the human gate** — scan for placeholders and
   contradictions, and run the traceability check: every load-bearing
   declaration in the Decision Log has a counterpart slot in the children,
   contracts, or acceptance sections. Commit the spec; the human's
   approval opens phase 6. (A design already approved in brainstorming
   needs their eyes only on what this run added — the cut, the grades,
   the contracts.)
6. **Materialize onto the board (optional)** — when the project runs the
   board pipeline: children as tickets with typed edges via
   doperpowers:issue-tracker scripts, bodies fleshed to the pre-spec bar
   and citing this composite spec (path + child id). Deferred entries that
   are real work may register as parked tickets citing this composite spec, so
   overflow from the design session keeps a durable home beyond the
   Deferred list. Skip for document-only
   projects — the tracking map is the handoff contract either way. (A
   dispatched worker that finds its ticket gate-failing on scope runs this
   same division at board altitude — doperpowers:executing's
   decompose procedure is this skill's move in worker clothes.)
7. **Dispatch and tend** — children go to their tracks per their track
   hint, each carrying its section as pre-landed design and writing no
   spec of its own: a controlled leaf grills only its residue and goes to
   doperpowers:writing-plans, an autonomous leaf authors its ExecPlan, a
   spike writes findings, and a composite child runs this skill at its
   own dispatch. Residue decisions a leaf makes land in this Decision Log
   under the child's id; a leaf's retrospective is its tracking-map row
   and its closing artifact. As children land, the tracking map, Decision
   Log, and Surprises stay current; when the children are all in, close
   the parent by RECOMPOSITION — verify the parent's own acceptance, then
   write the retrospective; the Deferred section seeds the next cut.

## The Derivation Contract

Each child section of the composite spec fixes:

- **Purpose** — one paragraph, the child's reason to exist;
- **Observable acceptance** — behavior, not implementation;
- **Dependency edges** — what blocks it, what it blocks;
- **Cross-child contracts** — the shared interfaces, invariants, and
  ordering rules it participates in;
- **Design inheritance** — the parent design content that bears on this
  child, each piece carrying its authority grade;
- **Track hint** — controlled, autonomous, spike (deliverable is
  findings, never a merge), or another decomposing run at
  dispatch.

Everything the parent hands a child carries one of two authority
grades:

- **Binding** — what only the joint view could settle: purpose,
  acceptance, edges, cross-child contracts, and any design decision
  that would come out differently without the whole picture in view
  (shared data models, interface shapes, failure semantics that span
  children). Children never re-litigate binding content; discovery that
  contradicts it flows back as `[parent-impact]` (see Upward Revision),
  never a local override.
- **Advisory** — the parent's best full-picture thinking on matters
  local to one child: approach sketches, sequencing suggestions,
  anticipated pitfalls. The child inherits it as pre-landed grill
  input — it starts there instead of from a blank page — and may
  overturn it with evidence; the overturn lands as a dated Revision
  Note on the parent, written by the child, not a reconciliation event.

Advisory is the default grade; content is binding because the composite
spec marks it so, with the joint-view reason attached. Capture is not
commitment: the parent records everything the design session produced —
the spec is the only durable memory this org has, and a stale written
decision is detectably wrong at child time while an uncaptured insight
is silently gone — but it binds only what the joint view actually
settled. A parent that binds child-local means converts every child
discovery into reconciliation traffic; a parent that withholds design
to "let the child figure it out" throws away decisions that were only
makeable with everything on the table.

At dispatch, the child treats its section and its design inheritance as
pre-landed grill input: it grills only the residue and never re-litigates
landed decisions. Its section IS its spec. Design the child produces for
itself expands that section in place; a leaf whose design will not fit a
section is a composite in disguise and gets its own composite spec
instead. The child's artifact — its plan, ExecPlan, PR, or ticket — opens
by citing this composite spec (path + child id + parent pin); that
citation is what keeps the flow-back channel alive when there is no
board. Children read the parent document's *current* state at dispatch,
never a frozen snapshot; when a Revision Note lands that touches an
in-flight child's contract, flag that child. When a child's work contradicts the parent, the
discovery flows back into the parent's Revision Notes — never silent
divergence. This is the doperpowers:execspec discipline one level up.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Running on a goal that passes the gate | That's a leaf with ceremony. Define it in doperpowers:brainstorming and dispatch it to its track. |
| Running on a raw ungrounded ideadump | Wrong skill — doperpowers:organizing-sprints grounds testimony first. |
| A cut that yields one child | A gate misfire: either the goal was already a leaf (ceremony), or the cut found no seam where children land independently. Back to the gate. |
| Forcing division because a goal is big | The gate asks reliably-ownable, not small. Big-but-coherent is one leaf. |
| Dividing branches far from the frontier | Distant CUTS go stale — commitments stay coarse until near execution. Captured design prose stays, graded advisory. |
| Withholding design so the child can "figure it out" | Joint-view insight uncaptured is unrecoverable; write it down as advisory inheritance. Staleness flows back; loss doesn't. |
| Binding child-local means | Advisory is the default grade; binding needs a joint-view reason. Flat bindingness turns every child discovery into reconciliation traffic. |
| Cutting a coupled goal undesigned | The interaction surface is designable only with everything in view — doperpowers:brainstorming matures it first. Early routing is for uncoupled bundles. |
| Treating level names as structure | Milestone/Epic/Phase are project annotations. The gate is the only law; depth is an output. |
| Closing a parent by bookkeeping | Recomposition is verification against the parent's own acceptance, not a status flip. |
| Inventing a tree registry | The tree is citations + edges + tracking maps. No new substrate. |
| Materializing before spec approval | Outward-facing batch action; hard-gated on the human's review. |
| Child quietly diverging from the parent | Contradictions flow back into the parent's Revision Notes; flagged, not silent. |
| Writing a spec for a leaf child | Its section is its spec; its document is its execution artifact. A leaf that needs a spec of its own is a composite in disguise — cut it. |
