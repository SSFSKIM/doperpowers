---
name: decomposing
description: Use when a goal is too big for one agent to reliably own as one unit — a deliberate initiative, epic, or milestone whose pieces must become child goals (a roadmap) before any single piece is designed — or when tending a live goal tree: a landed child contradicts the plan, a coarse branch nears execution, a parent's children are all done. For defining or sharpening a single ownable idea use doperpowers:brainstorming; for a pile of raw ungrounded observations use doperpowers:organizing-sprints.
---

# Decomposing

## Overview

Work is a tree of goals. Every node is a goal — a purpose with observable
acceptance — whatever the project calls it: milestone, epic, phase, slice,
ticket. doperpowers:brainstorming DEFINES one goal at a time, whatever its
size; this skill DIVIDES a goal that fails the gate below into child goals
one level down, and tends the tree as children land; the tracks
(brainstorming → spec → plans, or doperpowers:execplan) EXECUTE the leaves.
The product of one run is a parent **roadmap spec** per
`references/roadmap-spec-template.md`: children with purpose, observable
acceptance, and dependency edges; the contracts that cross them; and a
living tail that tracks the unit to its retrospective.

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
  workers (an SDD plan's task workers, an ExecPlan's milestones) without
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
  chain (each child spec opens by citing its parent), the board's typed
  edges, and the parent specs' tracking maps.

## The Frontier

Divide at need in time as well as in size: one level per run, and a branch
is divided only as it nears execution. Distant branches stay coarse — a
child whose own division can wait carries the track hint "decomposing
run at dispatch" and nothing more. The cut you would draw today for
far-off work goes stale the same way approach sketches do; an undivided
branch is cheap to re-cut when a landed sibling's discoveries move it. A
roadmap is precise near the frontier and coarse in the distance — keep it
that way.

## Recomposition

All children green does not close a parent. The parent declares its own
acceptance at cut time — the observable state that closes the unit AS A
WHOLE, not the sum of child acceptances — and when the children have
landed, closing the parent is a VERIFICATION event against that acceptance
(integration seams, end-to-end behavior). Only then does the retrospective
write.

<HARD-GATE>
Materialization onto the issue board is gated on the human approving the
written roadmap spec. Registering a unit's worth of tickets is an
outward-facing batch action — do not touch the board before approval.
</HARD-GATE>

## The Pipeline

Create a task per phase; complete them in order.

1. **Ground the goal** — explore the code and repo state it touches.
   Intent is trusted here, but a question the codebase can answer is
   answered by reading, never asked.
2. **Tentative child cut** — propose children as goals with ordering; get
   the human's reaction BEFORE deep grilling. Over-merging hides
   independent shippables; over-splitting loses coherence — ask when
   unsure. Check each tentative child against the code for already-built
   or partially-built reality: deliberate initiatives assume greenfield
   more often than the code is.
3. **Grill** — one question at a time, each with your recommended answer
   (doperpowers:brainstorming's grill protocol): child boundaries,
   dependency edges, cross-child contracts, and reservations that belong
   to a later cut rather than this one.
4. **Author the roadmap spec** — per `references/roadmap-spec-template.md`,
   born landed: v1 already carries the grill's decisions, with the living
   tail of doperpowers:execspec.
5. **Self-review, then the human gate** — scan for placeholders and
   contradictions, and run the traceability check: every load-bearing
   declaration in the Decision Log has a counterpart slot in the children,
   contracts, or acceptance sections. Commit the spec; the human's
   approval opens phase 6.
6. **Materialize onto the board (optional)** — when the project runs the
   board pipeline: children as tickets with typed edges via
   doperpowers:issue-tracker scripts, bodies fleshed to the pre-spec bar
   and citing this roadmap (path + child id). Skip for document-only
   projects — the tracking map is the handoff contract either way. (A
   dispatched worker that finds its ticket gate-failing on scope runs this
   same division at board altitude — doperpowers:implementing-tickets'
   decompose procedure is this skill's move in worker clothes.)
7. **Dispatch and tend** — children go to their tracks per their track
   hint. As children land, the tracking map, Decision Log, and Surprises
   stay current; when the children are all in, close the parent by
   RECOMPOSITION — verify the parent's own acceptance, then write the
   retrospective; the Deferred section seeds the next cut.

## The Derivation Contract

Each child section of the roadmap fixes:

- **Purpose** — one paragraph, the child's reason to exist;
- **Observable acceptance** — behavior, not implementation;
- **Dependency edges** — what blocks it, what it blocks;
- **Cross-child contracts** — the shared interfaces, invariants, and
  ordering rules it participates in;
- **Track hint** — controlled, autonomous, spike (deliverable is
  findings, never a merge), or another decomposing run at
  dispatch.

At dispatch, the child treats its section as pre-landed grill input: it
grills only the residue and never re-litigates landed decisions. The
child's own spec opens by citing this roadmap (path + child id) — that
citation is what keeps the flow-back channel alive when there is no
board. Children read the parent document's *current* state at dispatch,
never a frozen snapshot; when a Revision Note lands that touches an
in-flight child's contract, flag that child.

The parent fixes ends, never means: no technical-approach sketches for
children — high-altitude approach sketches miss the depth the child will
discover and go stale as earlier children land. When a child's work
contradicts the parent, the discovery flows back into the parent's
Revision Notes — never silent divergence. This is the
doperpowers:execspec discipline one level up.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Running on a goal that passes the gate | That's a leaf with ceremony. Define it in doperpowers:brainstorming and dispatch it to its track. |
| Running on a raw ungrounded ideadump | Wrong skill — doperpowers:organizing-sprints grounds testimony first. |
| A cut that yields one child | A gate misfire: either the goal was already a leaf (ceremony), or the cut found no seam where children land independently. Back to the gate. |
| Forcing division because a goal is big | The gate asks reliably-ownable, not small. Big-but-coherent is one leaf. |
| Dividing branches far from the frontier | Distant cuts go stale. Coarse until near execution. |
| Sketching child approaches in the parent | The parent fixes purpose/acceptance/edges; means belong to the child. |
| Treating level names as structure | Milestone/Epic/Phase are project annotations. The gate is the only law; depth is an output. |
| Closing a parent by bookkeeping | Recomposition is verification against the parent's own acceptance, not a status flip. |
| Inventing a tree registry | The tree is citations + edges + tracking maps. No new substrate. |
| Materializing before spec approval | Outward-facing batch action; hard-gated on the human's review. |
| Child quietly diverging from the parent | Contradictions flow back into the parent's Revision Notes; flagged, not silent. |
