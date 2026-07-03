# Living Specs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `living-specs` skill (adapter over the vendored `references/PLANS.md`) plus four one-point hooks so every spec carries a maintained living tail — Decision Log with rejected alternatives, Surprises & Discoveries, Outcomes & Retrospective, Revision Notes — from brainstorm to merge.

**Architecture:** One new skill directory `skills/living-specs/` holds the doctrine; `references/PLANS.md` (already committed, char-for-char vendor) is scripture, `SKILL.md` is the adapter saying what binds, what is superseded, and the four update triggers. Four existing skills each gain a small insertion referencing `superpowers:living-specs` at the exact lifecycle moment they own.

**Tech Stack:** Markdown only. No code, no scripts, no new tests (verification is grep-based; behavioral acceptance happens on the next real feature).

**Spec:** `docs/superpowers/specs/2026-07-03-living-specs-design.md` — read it before starting; its Disposition map is the authority on what PLANS.md content binds.

## Global Constraints

- `skills/living-specs/references/PLANS.md` is vendored char-for-char and MUST NOT be modified by any task. At the end, `git log --oneline -- skills/living-specs/references/PLANS.md` shows exactly one commit (the spec commit `9496bde`).
- Files touched: create `skills/living-specs/SKILL.md`; modify only `skills/brainstorming/SKILL.md`, `skills/writing-plans/SKILL.md`, `skills/subagent-driven-development/SKILL.md`, `skills/finishing-a-development-branch/SKILL.md`. Nothing else.
- The living-tail headings are exactly: `## Decision Log`, `## Surprises & Discoveries`, `## Outcomes & Retrospective`, `## Revision Notes`.
- Every hook names the skill as `superpowers:living-specs` (that literal string is what the verification greps for).
- Any PLANS.md guidance quoted in SKILL.md must be verbatim from `references/PLANS.md` — no rewording (spec Decision Log, decision 3).
- Skill frontmatter: `name: living-specs`; description begins "Use when" (repo convention).
- Commit after every task. No `Co-Authored-By` / attribution lines in commit messages.

## File Structure

```
skills/living-specs/
  SKILL.md                                  # the adapter (Task 1)
  references/PLANS.md                       # vendored — already committed, untouched
skills/brainstorming/SKILL.md               # hook: write specs in this shape (Task 2)
skills/writing-plans/SKILL.md               # hook: fix spec drift found while planning (Task 3)
skills/subagent-driven-development/SKILL.md # hook: route discoveries into the spec (Task 4)
skills/finishing-a-development-branch/SKILL.md  # hook: retrospective before merge options (Task 5)
```

---

### Task 1: `skills/living-specs/SKILL.md` — the adapter

**Files:**
- Create: `skills/living-specs/SKILL.md`

**Interfaces:**
- Produces: the skill name `superpowers:living-specs` that Tasks 2-5 reference; the four living-tail headings (`## Decision Log`, `## Surprises & Discoveries`, `## Outcomes & Retrospective`, `## Revision Notes`); the "Pending — written at finish." placeholder convention; the two entry formats (`Decision:/Rationale:/Date/Author:` and `Observation:/Evidence:`).
- Consumes: `references/PLANS.md` (already on disk at `skills/living-specs/references/PLANS.md`).

- [ ] **Step 1: Write the file**

Create `skills/living-specs/SKILL.md` with exactly this content:

````markdown
---
name: living-specs
description: Use when writing, revising, or closing out a design spec (docs/superpowers/specs/) — the living-spec doctrine, vendored from Codex ExecPlans: Decision Log with rejected alternatives, Surprises & Discoveries with evidence, retrospective at finish, revision notes, behavior-phrased acceptance
---

# Living Specs

## Overview

A spec is not a snapshot of an approval — it is the design's single source of truth for the whole life of its feature. Decisions carry their rationale and their rejected alternatives, discoveries made while planning and building flow back into the document, and the feature closes with a retrospective.

The norms come from Codex's ExecPlan doctrine, vendored char-for-char at [references/PLANS.md](references/PLANS.md). That file is the source; this file is the adapter that says which parts bind at the spec layer, which are superseded by superpowers machinery, and when the spec gets updated. Where a section binds, follow the original text — details die in paraphrase.

**The bar (recalibrated from PLANS.md's novice standard):** a fresh session with no conversation history can pick up the spec and continue the work — decisions, their whys, and everything learned so far included. Define terms of art; reference repo common knowledge instead of duplicating it.

## What binds — read these PLANS.md sections as written

- **"Purpose and intent come first"** (Requirements, paragraph after the non-negotiables): the spec opens with why the work matters from a user's perspective — what someone can do after this change that they could not do before, and how to see it working.
- **Non-negotiables** (Requirements): the spec is a living document, revised as progress is made and discoveries occur; "define every term of art in plain language or do not use it"; the work must "produce a demonstrably working behavior, not merely code changes to 'meet a definition'".
- **"Self-containment and plain language are paramount"** (Guidelines): define jargon on first use; name files with full repository-relative paths.
- **"Anchor the plan with observable outcomes"** (Guidelines): acceptance is phrased as behavior a human can verify, with exact commands and expected output — never internal attributes.
- **"Living plans and design decisions"** — all five bullets, with the spec as the target document (Progress excepted; see below).
- **"Prototyping milestones and parallel implementations"**: when unknowns are large, the spec declares spike milestones — how to run and observe results, and "the criteria for promoting or discarding the prototype". superpowers:writing-plans turns them into spike tasks.

## What does NOT bind — superseded, do not import

| PLANS.md directive | Superseded by |
|---|---|
| "do not prompt the user for 'next steps'…Resolve ambiguities autonomously" | Human gates: design approval and spec review in superpowers:brainstorming |
| Single fenced code block, prose-first, no tables or checklists | Specs are files, not chat payloads; use tables/JSON/diagrams wherever they beat prose for precision |
| Mandatory `Progress` section with timestamped checkboxes | The SDD ledger + git + plan checkboxes — externally verifiable, not self-report |
| Milestones narrative, Concrete Steps, Interfaces and Dependencies | superpowers:writing-plans, with complete code and exact commands |
| Idempotence and Recovery section | Worktree isolation + git |
| Self-contained "for a complete novice" | The fresh-session bar in the Overview above |

These rejections carry rationale — read the Decision Log in `docs/superpowers/specs/2026-07-03-living-specs-design.md` before re-proposing one.

## The living tail

Every spec ends with these four sections, in this order, headed exactly as shown.

**`## Decision Log`** — every design decision, in PLANS.md's skeleton format:

    - Decision: …
      Rationale: …
      Date/Author: …

Seed it at brainstorm time with the chosen approach AND each rejected alternative with why it lost — the approaches step already generated them; capturing them is free and stops re-proposals. Extend it whenever course changes mid-feature.

**`## Surprises & Discoveries`** — in PLANS.md's skeleton format:

    - Observation: …
      Evidence: …

For anything that changed design understanding: an assumption that proved false, a measured behavior, a constraint discovered during planning or execution. Short evidence snippets — test output is ideal. Incidental implementation noise belongs in commit messages, not here.

**`## Outcomes & Retrospective`** — until finish, exactly the line "Pending — written at finish." At finish (superpowers:finishing-a-development-branch triggers this), summarize what was achieved against the spec's original purpose, what remains, and lessons learned.

**`## Revision Notes`** — one dated line per spec revision describing what changed and why (PLANS.md's bottom-note rule: "you must write a note at the bottom of the plan describing the change and the reason why"). When you revise, keep the whole document consistent — reflect the change across sections, not just where convenient.

## Update triggers

- **Brainstorm end** (superpowers:brainstorming): spec written in this shape, Decision Log seeded, committed.
- **Plan-writing** (superpowers:writing-plans Self-Review): planning is the first hostile read of the spec. If a spec statement proved wrong, fix the spec now and add a Revision Note — never let the plan silently diverge.
- **Execution** (superpowers:subagent-driven-development bookkeeping): task reports that change design understanding get routed into Surprises & Discoveries or the Decision Log in the same message as the ledger append.
- **Finish** (superpowers:finishing-a-development-branch): write Outcomes & Retrospective and commit it before presenting merge options.

Whoever drives the session maintains the spec. There are no writer rules — in practice one spec has one working agent.

## Front of the spec

Untemplated on purpose: across this repo's existing specs no heading structure repeats, and that variance is a feature — form fits problem (state tables for state machines, JSON for schemas, prose for concepts). Only three things are required: the purpose-first opening, an acceptance section phrased as observable behavior, and the living tail.
````

- [ ] **Step 2: Verify**

Run: `head -4 skills/living-specs/SKILL.md`
Expected: frontmatter with `name: living-specs`.

Run: `grep -c '^## ' skills/living-specs/SKILL.md`
Expected: `6` (Overview, What binds, What does NOT bind, The living tail, Update triggers, Front of the spec).

Run: `git status --short skills/living-specs/references/PLANS.md`
Expected: no output (vendored file untouched).

- [ ] **Step 3: Commit**

```bash
git add skills/living-specs/SKILL.md
git commit -m "living-specs: adapter skill over vendored ExecPlan doctrine"
```

---

### Task 2: brainstorming hook — specs are born living

**Files:**
- Modify: `skills/brainstorming/SKILL.md` (three insertions: checklist item 6, Documentation bullets, Spec Self-Review item 5)

**Interfaces:**
- Consumes: `superpowers:living-specs` (Task 1) and the living-tail heading names.

- [ ] **Step 1: Update checklist item 6**

Replace:

```markdown
6. **Write design doc** — save to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit
```

with:

```markdown
6. **Write design doc** — in living-spec shape per superpowers:living-specs (purpose-first opening, behavior-phrased acceptance, living tail with the Decision Log seeded from step 4's alternatives); save to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit
```

- [ ] **Step 2: Update the Documentation bullets**

Replace:

```markdown
- Write the validated design (spec) to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
  - (User preferences for spec location override this default)
- Use elements-of-style:writing-clearly-and-concisely skill if available
- Commit the design document to git
```

with:

```markdown
- Write the validated design (spec) to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
  - (User preferences for spec location override this default)
- Shape it per superpowers:living-specs: purpose-first opening, acceptance phrased as observable behavior, and the living tail (`## Decision Log`, `## Surprises & Discoveries`, `## Outcomes & Retrospective` reading "Pending — written at finish.", `## Revision Notes`)
- Seed the Decision Log with the chosen approach and each rejected alternative from the approaches step, with why it lost — they are already generated; capturing them is free
- Use elements-of-style:writing-clearly-and-concisely skill if available
- Commit the design document to git
```

- [ ] **Step 3: Add Spec Self-Review item 5**

Replace:

```markdown
4. **Ambiguity check:** Could any requirement be interpreted two different ways? If so, pick one and make it explicit.
```

with:

```markdown
4. **Ambiguity check:** Could any requirement be interpreted two different ways? If so, pick one and make it explicit.
5. **Living tail:** Are `## Decision Log` (with at least one rejected alternative), `## Surprises & Discoveries`, `## Outcomes & Retrospective` ("Pending — written at finish."), and `## Revision Notes` all present?
```

- [ ] **Step 4: Verify and commit**

Run: `grep -c "living-specs" skills/brainstorming/SKILL.md`
Expected: `2` (checklist + Documentation).

Run: `grep -n "Living tail" skills/brainstorming/SKILL.md`
Expected: one hit in Spec Self-Review.

```bash
git add skills/brainstorming/SKILL.md
git commit -m "brainstorming: write specs in living-spec shape, seed the Decision Log"
```

---

### Task 3: writing-plans hook — planning is the first hostile read

**Files:**
- Modify: `skills/writing-plans/SKILL.md` (one insertion in Self-Review)

**Interfaces:**
- Consumes: `superpowers:living-specs` (Task 1), Revision Notes convention.

- [ ] **Step 1: Add Self-Review check 4**

Replace:

```markdown
**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.
```

with:

```markdown
**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

**4. Spec drift:** Planning is the first hostile read of the spec. If planning revealed a spec statement that is wrong — an argument that is actually an output, an infeasible constraint, a misnamed path — fix the spec now and add a line to its `## Revision Notes` (see superpowers:living-specs). Never let the plan silently diverge from the spec.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.
```

- [ ] **Step 2: Verify and commit**

Run: `grep -n "Spec drift" skills/writing-plans/SKILL.md`
Expected: one hit in Self-Review.

```bash
git add skills/writing-plans/SKILL.md
git commit -m "writing-plans: self-review check 4 — fix spec drift found while planning"
```

---

### Task 4: subagent-driven-development hook — discoveries flow back during execution

**Files:**
- Modify: `skills/subagent-driven-development/SKILL.md` (one bullet in Durable Progress)

**Interfaces:**
- Consumes: `superpowers:living-specs` (Task 1), Surprises & Discoveries / Decision Log headings.

- [ ] **Step 1: Add the routing bullet**

Replace:

```markdown
- When a task's review comes back clean, append one line to the ledger in
  the same message as your other bookkeeping:
  `Task N: complete (commits <base7>..<head7>, review clean)`.
```

with:

```markdown
- When a task's review comes back clean, append one line to the ledger in
  the same message as your other bookkeeping:
  `Task N: complete (commits <base7>..<head7>, review clean)`.
- In that same bookkeeping message, route anything from the task's report
  that changed design understanding — an assumption that proved false, a
  constraint discovered, a mid-course design decision — into the spec's
  `## Surprises & Discoveries` or `## Decision Log`
  (superpowers:living-specs). Implementation noise stays in commit
  messages, not the spec.
```

- [ ] **Step 2: Verify and commit**

Run: `grep -n "living-specs" skills/subagent-driven-development/SKILL.md`
Expected: one hit in Durable Progress.

```bash
git add skills/subagent-driven-development/SKILL.md
git commit -m "sdd: route design-relevant discoveries into the spec at bookkeeping time"
```

---

### Task 5: finishing hook — the retrospective rides the branch

**Files:**
- Modify: `skills/finishing-a-development-branch/SKILL.md` (core principle line + Step 1 tests-pass line)

**Interfaces:**
- Consumes: `superpowers:living-specs` (Task 1), Outcomes & Retrospective convention.

- [ ] **Step 1: Update the core principle line**

Replace:

```markdown
**Core principle:** Verify tests → Detect environment → Present options → Execute choice → Clean up.
```

with:

```markdown
**Core principle:** Verify tests → Write retrospective → Detect environment → Present options → Execute choice → Clean up.
```

- [ ] **Step 2: Update the tests-pass line**

Replace:

```markdown
**If tests pass:** Continue to Step 2.
```

with:

```markdown
**If tests pass:** Write the spec's `## Outcomes & Retrospective` entry — what was achieved against the spec's original purpose, gaps, lessons learned (superpowers:living-specs) — replacing its "Pending — written at finish." line, and commit it so the retrospective rides the branch into the merge. Then continue to Step 2.
```

- [ ] **Step 3: Verify and commit**

Run: `grep -n "Outcomes & Retrospective" skills/finishing-a-development-branch/SKILL.md`
Expected: one hit in Step 1.

```bash
git add skills/finishing-a-development-branch/SKILL.md
git commit -m "finishing: write the spec retrospective before presenting merge options"
```

---

### Task 6: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Structural checks (from the spec's Verification section)**

Run: `ls skills/living-specs/`
Expected: `SKILL.md  references`

Run: `grep -l "living-specs" skills/brainstorming/SKILL.md skills/writing-plans/SKILL.md skills/subagent-driven-development/SKILL.md skills/finishing-a-development-branch/SKILL.md`
Expected: all four paths printed.

Run: `git log --oneline -- skills/living-specs/references/PLANS.md`
Expected: exactly one commit (`9496bde spec: living-specs — vendor ExecPlan doctrine into the spec layer`) — the vendored file was never touched again.

- [ ] **Step 2: The first living spec conforms to the doctrine it ships**

Run: `grep -n '^## Decision Log\|^## Surprises & Discoveries\|^## Outcomes & Retrospective\|^## Revision Notes' docs/superpowers/specs/2026-07-03-living-specs-design.md`
Expected: four hits, in that order.

- [ ] **Step 3: Nothing else changed**

Run: `git status --short`
Expected: clean (every task committed its own files).
