# Roadmapping Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the `roadmapping` skill (altitude-recursive parent-roadmap workflow above the Slice), its template, brainstorming's third route, and the sibling cross-references — then validate via the template dry-run and pressure scenarios.

**Architecture:** One new skill directory (`SKILL.md` + `references/roadmap-spec-template.md`), surgical edits to three existing skills (brainstorming: routing + traceability self-review item; organizing-sprints: one description sentence; writing-plans: one cross-reference sentence), then validation per the spec's acceptance.

**Tech Stack:** Markdown skill content; Agent-tool subagent dispatches for the dry-run and pressure scenarios.

**Spec:** `docs/doperpowers/specs/2026-07-19-roadmapping-design.md`

## Global Constraints

- Canonical ladder is exactly **Milestone → Epic → Slice → Task**; "Phase" is documented as a project-local alias only; the above-Milestone tier stays reserved/undesigned (spec Decision 1).
- One altitude per run; recursion is the skill re-run one level down; a roadmap never reaches below slice boundaries (spec Design).
- The parent never sketches a child's technical approach (spec Decision 3).
- Exactly ONE hard gate in the new skill: board materialization gated on the human approving the spec document. Everything else is ownership/outcomes language (repo golden rule).
- organizing-sprints: the description sentence is the ONLY change to that skill (spec Decision 6).
- Child-facing rules from the 2026-07-20 spec revision must appear verbatim in substance: child spec opening cites parent (path + child id); children read the parent's current state at dispatch; a Revision Note touching an in-flight child's contract flags that child; template carries Parent-Level Acceptance; tracking map + child status fields ARE the Progress record.

---

### Task 1: Create `skills/roadmapping/SKILL.md`

**Files:**
- Create: `skills/roadmapping/SKILL.md`

**Interfaces:**
- Produces: skill name `roadmapping`, referenced by Tasks 3-5; section `## The Derivation Contract` and template path `references/roadmap-spec-template.md`, consumed by Task 2.

- [ ] **Step 1: Write the file with exactly this content**

````markdown
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
doperpowers:brainstorming → spec → plans, doperpowers:execplan, or (for an
epic-sized child of a milestone) another roadmapping run one level down.

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
````

- [ ] **Step 2: Verify**

Run: `head -5 skills/roadmapping/SKILL.md && grep -c "HARD-GATE" skills/roadmapping/SKILL.md`
Expected: frontmatter with `name: roadmapping`; HARD-GATE count is 2 (open+close tags of the single gate).

- [ ] **Step 3: Commit**

```bash
git add skills/roadmapping/SKILL.md
git commit -m "feat(roadmapping): altitude-recursive parent-roadmap workflow above the Slice"
```

### Task 2: Create `skills/roadmapping/references/roadmap-spec-template.md`

**Files:**
- Create: `skills/roadmapping/references/roadmap-spec-template.md`

**Interfaces:**
- Consumes: Task 1's pipeline/derivation-contract section names (the template's slots must carry every element the SKILL.md derivation contract names: purpose, acceptance, edges, cross-child contracts, track hint).

- [ ] **Step 1: Write the file with exactly this content**

````markdown
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
````

- [ ] **Step 2: Verify the template carries every derivation-contract slot**

Run: `grep -n "Purpose\|Acceptance\|Edges\|Contracts\|track hint\|Tracking Map\|Parent-Level" skills/roadmapping/references/roadmap-spec-template.md | head -12`
Expected: hits for Parent-Level Acceptance, per-child Purpose/Acceptance/Edges/Contracts, track hint, Tracking Map.

- [ ] **Step 3: Commit**

```bash
git add skills/roadmapping/references/roadmap-spec-template.md
git commit -m "feat(roadmapping): roadmap spec template"
```

### Task 3: Brainstorming — third route + traceability self-review item

**Files:**
- Modify: `skills/brainstorming/SKILL.md` (three edits)

**Interfaces:**
- Consumes: skill name `roadmapping` (Task 1).

- [ ] **Step 1: Replace BOTH scope-assessment bullets**

In the "Understanding the idea" section, replace these two bullets:

> - Before asking detailed questions, assess scope: if the request describes multiple independent subsystems (e.g., "build a platform with chat, file storage, billing, and analytics"), flag this immediately. Don't spend questions refining details of a project that needs to be decomposed first.
> - If the project is too large for a single spec, help the user decompose into sub-projects: what are the independent pieces, how do they relate, what order should they be built? Then brainstorm the first sub-project through the normal design flow. Each sub-project gets its own spec → plan → implementation cycle.

with this single bullet:

> - Before asking detailed questions, assess scope: if the request describes multiple independent purpose-units (e.g., "build a platform with chat, file storage, billing, and analytics"), flag this immediately. Work bigger than one slice belongs one altitude up: recommend doperpowers:roadmapping — it decomposes the initiative into children with acceptance and edges, and each child then returns through this skill (or execplan) with its parent section as pre-landed input. Confirm the route with your human partner before switching; don't drift into grilling slice details of an epic-scale request.

- [ ] **Step 2: Add the clarifying line at the terminal-state rule**

The paragraph beginning `**The terminal state is invoking writing-plans**` ends with `The ONLY skills you invoke after brainstorming are writing-plans (controlled track) and execplan (autonomous track, on your human partner's explicit choice).` Append to that paragraph:

> (One earlier exit exists at scope-assessment time, before any design: an initiative bigger than one slice routes to doperpowers:roadmapping — see the scope bullet above.)

- [ ] **Step 3: Add the traceability item to Spec Self-Review**

The "Spec Self-Review" numbered list ends with item `5. **Living tail:** …`. Append:

> 6. **Traceability:** For every load-bearing declaration in the Decision Log or design prose — anything that says the artifact must carry X — point to the concrete section, slot, or instruction that carries it. A declaration without a counterpart is a defect.

- [ ] **Step 4: Verify**

Run: `grep -n "roadmapping\|Traceability\|decompose into sub-projects" skills/brainstorming/SKILL.md`
Expected: roadmapping appears in the scope bullet and terminal-state note; Traceability appears as item 6; "decompose into sub-projects" has NO hits.

- [ ] **Step 5: Commit**

```bash
git add skills/brainstorming/SKILL.md
git commit -m "feat(brainstorming): route epic-scale requests to roadmapping; traceability self-review item"
```

### Task 4: Sibling cross-references (organizing-sprints, writing-plans)

**Files:**
- Modify: `skills/organizing-sprints/SKILL.md` (frontmatter description only)
- Modify: `skills/writing-plans/SKILL.md` (one sentence in Conditional Sub-Slicing)

**Interfaces:**
- Consumes: skill name `roadmapping` (Task 1).

- [ ] **Step 1: organizing-sprints description**

In the frontmatter `description:`, after `For a single idea use doperpowers:brainstorming; to register one already-understood ticket use doperpowers:issue-tracker.` append: ` For a deliberate top-down initiative use doperpowers:roadmapping.`

- [ ] **Step 2: writing-plans cross-reference**

In `skills/writing-plans/SKILL.md`, the Conditional Sub-Slicing section ends with `Sub-slicing is a judgment tool, not ceremony: the fewest boundaries that make each important invariant independently understandable and testable.` Append as a new paragraph:

> Above the Slice, the inverse question — decomposing an epic or milestone into slices — belongs to doperpowers:roadmapping; the two are the above-/below-Slice halves of the same doctrine.

- [ ] **Step 3: Verify**

Run: `grep -n "roadmapping" skills/organizing-sprints/SKILL.md skills/writing-plans/SKILL.md`
Expected: exactly one hit in each file.

- [ ] **Step 4: Commit**

```bash
git add skills/organizing-sprints/SKILL.md skills/writing-plans/SKILL.md
git commit -m "feat(roadmapping): sibling cross-references in organizing-sprints and writing-plans"
```

### Task 5: Final verification — template dry-run + pressure scenarios + record

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-19-roadmapping-design.md` (record results; template frictions also fix Task 2's file)

**Interfaces:**
- Consumes: all files from Tasks 1-4 at their repo paths.

- [ ] **Step 1: Template dry-run against a real ida-solution milestone**

Dispatch a fresh subagent (model `opus`) with this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/roadmapping/SKILL.md and /Users/new/Developer/GitHub/doperpowers/skills/roadmapping/references/roadmap-spec-template.md. Then explore /Users/new/Developer/GitHub/ida-solution (a Next.js+Supabase tutoring product) — its planning documents (look for milestone/sprint specs under docs/, e.g. M4.5/M5 sprint specs) and recent git log — and pick its most recent coherent milestone of work. Re-express that milestone as a roadmap spec using the template, at whichever altitude fits (Milestone→Epics or Epic→Slices). Write the result to /Users/new/.claude/jobs/2c06ef07/tmp/ida-dryrun-roadmap.md. Then answer: (1) did every piece of the real milestone find a natural slot in the template? (2) list every friction — a slot that didn't fit, a section you had to contort, information the template had no home for — as concrete template-change suggestions; (3) verdict: fits-without-contortion YES/NO.

PASS: verdict YES, or NO with frictions that are template fixes (apply them to `references/roadmap-spec-template.md`, note each in the spec's Revision Notes, and re-run the dry-run once).

- [ ] **Step 2: Pressure scenario P1 — epic-scale prompt routes up**

Dispatch a fresh subagent (model `sonnet`) with this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/brainstorming/SKILL.md and follow it as if a session just started. Your human partner's first message is: "Let's build the school-operations suite: a teacher scheduling module, a parent billing portal, an attendance analytics dashboard, and a notification center." Show your first response to the human. Do not actually explore any codebase; this is a routing exercise.

PASS: the response flags multi-unit scope and recommends doperpowers:roadmapping with a confirmation question. FAIL: it starts grilling feature details of one module or proposes designing all four in one spec.

- [ ] **Step 3: Pressure scenario P2 — slice-scale prompt does NOT route up**

Dispatch a fresh subagent (model `sonnet`) with this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/brainstorming/SKILL.md and follow it as if a session just started. Your human partner's first message is: "Add CSV export to the attendance report page." Show your first response to the human. Do not actually explore any codebase; this is a routing exercise.

PASS: normal brainstorming behavior (context exploration/grill), no mention of routing to roadmapping. FAIL: routes up.

- [ ] **Step 4: Pressure scenario P3 — child section is pre-landed input**

Dispatch a fresh subagent (model `sonnet`) with this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/brainstorming/SKILL.md. You are brainstorming a slice that was dispatched from a parent roadmap. The parent's child section reads: "C2: Parent billing portal — controlled. Purpose: parents view and pay monthly invoices online, replacing bank-transfer chasing. Acceptance: a parent can open the portal, see the current invoice with line items, pay by card, and the payment reconciles to the ledger within 5 minutes. Edges: blocked-by C1 (ledger API). Contracts: X1 — all money amounts flow as integer KRW; X2 — portal reads the ledger only through the C1 read API, never the DB. Track: controlled." List the questions you would grill the human on for this slice. Then state which topics you would NOT ask about and why.

PASS: does not re-litigate landed items (payment method card, KRW integers, ledger-API-only access, the 5-minute reconciliation bound); grills residue (e.g. card provider choice, invoice dispute flow, notification wording, auth); names the parent section as the reason topics are settled. FAIL: re-opens landed contract decisions as questions.

- [ ] **Step 5: Record results in the spec and commit**

In the roadmapping spec's `## Outcomes & Retrospective`, record: dry-run verdict + applied template fixes (if any), each scenario's PASS/FAIL with one line of verbatim evidence. Any FAIL: fix the responsible wording, re-run that scenario, record both rounds. Then:

```bash
git add docs/doperpowers/specs/2026-07-19-roadmapping-design.md skills/roadmapping/references/roadmap-spec-template.md
git commit -m "docs(specs): roadmapping acceptance results"
```
