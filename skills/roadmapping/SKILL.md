---
name: roadmapping
description: Use when a deliberate initiative is bigger than one slice — an epic or milestone of planned work that must be decomposed into children before any single piece is designed — producing a parent roadmap spec whose children dispatch to their own tracks. For a single idea use doperpowers:brainstorming; for a pile of raw ungrounded observations use doperpowers:organizing-sprints.
---

# Roadmapping

## Overview

Plan ONE parent unit of work at ONE altitude above the Slice, decomposing
it into children exactly one level down. The product is a **parent roadmap
spec**: children with purpose, observable acceptance, and dependency
edges; the contracts that cross them; and a living tail that tracks the
unit to its retrospective. Children dispatch to their own tracks —
doperpowers:brainstorming → spec → plans, doperpowers:execplan, or another
roadmapping run one level down when the child itself needs decomposition
before any piece can be designed. Size alone doesn't force nesting: an
epic-sized child that is still one coherent, delegable unit can run as a
single execplan.

This is the deliberate, top-down sibling of doperpowers:organizing-sprints.
That skill turns raw *testimony* (an ideadump that may misread the code)
into a sprint; this one turns trusted *intent* (a planned initiative) into
a roadmap. Same output shape, different intake — here there is no
verification table, but grounding still matters (see the pipeline).

## The Ladder

**Milestone → Epic → Slice → Task.**

- A **Slice** is the unit of one spec or one ExecPlan. A **Task** is a
  plan task (controlled) or an ExecPlan milestone M_n (autonomous).
- Below the Slice this skill does not reach: decomposing inside a slice
  belongs to Conditional Sub-Slicing in doperpowers:writing-plans. The
  two are the above-/below-Slice halves of the same doctrine.
- **"Phase" is a project-local alias, not a canonical level.** Some
  projects run "Milestone 5 Phase 4" where Phase plays the Epic role;
  others use Phase as a strategic tier above Milestone (reserved,
  undesigned here). Translate a project's names onto the ladder; don't
  fight them.
- organizing-sprints' "epic" is an altitude-variable purpose-unit — often
  Epic-sized, sometimes Slice-sized. The ladder's Epic is strictly above
  Slice.
- Projects drop levels freely by size. Altitude count is an output, never
  a target: don't erect a Milestone→Epic ladder over three slices, and a
  roadmap with one child means you should be in brainstorming.

<HARD-GATE>
Materialization onto the issue board is gated on the human approving the
written roadmap spec. Registering a unit's worth of tickets is an
outward-facing batch action — do not touch the board before approval.
</HARD-GATE>

## The Pipeline

Create a task per phase; complete them in order.

1. **Ground the initiative** — explore the code and repo state the
   initiative touches. Intent is trusted here, but a question the codebase
   can answer is answered by reading, never asked.
2. **Tentative child cut** — propose children as purpose-units with
   ordering; get the human's reaction BEFORE deep grilling. Over-merging
   hides independent shippables; over-splitting loses coherence — ask when
   unsure. Check each tentative child against the code for already-built
   or partially-built reality: deliberate initiatives assume greenfield
   more often than the code is.
3. **Grill** — one question at a time, each with your recommended answer
   (doperpowers:brainstorming's grill protocol): child boundaries,
   dependency edges, cross-child contracts, and reservations that belong
   to the next unit rather than this one.
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
   projects — the tracking map is the handoff contract either way.
   (Reserved, undesigned: at Milestone altitude an epic-sized child
   ticket's track hint is another roadmapping run; how
   doperpowers:implementing-tickets gates that species is deferred until
   the Epic→Slice altitude is proven.)
7. **Dispatch and keep alive** — children go to their tracks per their
   track hint. As children land, the tracking map, Decision Log, and
   Surprises stay current; the retrospective closes the unit; the
   Deferred section seeds the next one.

## The Derivation Contract

Each child section of the roadmap fixes:

- **Purpose** — one paragraph, the child's reason to exist;
- **Observable acceptance** — behavior, not implementation;
- **Dependency edges** — what blocks it, what it blocks;
- **Cross-child contracts** — the shared interfaces, invariants, and
  ordering rules it participates in;
- **Track hint** — controlled, autonomous, or another roadmapping run.

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
| Running on a single idea | Wrong skill — doperpowers:brainstorming. |
| Running on a raw ungrounded ideadump | Wrong skill — doperpowers:organizing-sprints grounds testimony first. |
| A roadmap with one child | That's a slice with ceremony. Go to brainstorming. |
| Sketching child approaches in the parent | The parent fixes purpose/acceptance/edges; means belong to the child. |
| Reaching below slice boundaries | Sub-slice decomposition is writing-plans' Conditional Sub-Slicing. |
| Materializing before spec approval | Outward-facing batch action; hard-gated on the human's review. |
| Child quietly diverging from the parent | Contradictions flow back into the parent's Revision Notes; flagged, not silent. |
| Treating the ladder as a form to fill | Altitude count is an output. Drop levels the project doesn't need. |
