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
