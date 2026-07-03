---
name: execplan
description: Use when taking a well-scoped, delegable piece of work through the autonomous track — a relentless grill that exhausts ambiguity up front, then one self-contained ExecPlan authored and executed to the letter of PLANS.md with no mid-flight human gates. Alternative to the brainstorming→spec→plan pipeline.
---

# ExecPlan Track

## Overview

This repo has two development tracks. The controlled pipeline (doperpowers:brainstorming → living spec → doperpowers:writing-plans → doperpowers:subagent-driven-development) places human gates throughout. This track places one: a grilling session that front-loads ALL human judgment, after which you author a single self-contained ExecPlan and execute it without interruption. The gate is moved, not removed — autonomy is safe only because the grill exhausted the ambiguity space while your human partner was present.

## Which track?

- **This track**: the work is delegable and a grill can resolve every open question up front. Fits long-running work and durable background daemons.
- **Controlled track**: taste-heavy, novel, or high-stakes work where design judgment keeps arising mid-flight → doperpowers:brainstorming.

Test during the grill: if you keep hitting "we can't know until we try" on *taste* questions, stop and route to the controlled track. (Feasibility unknowns are fine here — they become prototyping milestones in the ExecPlan.)

## Step 1 — Grill

Vendored verbatim from Matt Pocock's `grilling` skill:

> Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.
>
> Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering.
>
> If a question can be answered by exploring the codebase, explore the codebase instead.

Three moves to use throughout (kept from his `domain-modeling` skill; its artifacts are not used here):

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

Everything the grill resolves lands in the ExecPlan: term definitions inline where used, decisions (with the rejected alternatives and why) in its Decision Log. No CONTEXT.md, no ADRs — the ExecPlan is this track's only artifact.

## Step 2 — Author the ExecPlan

Read [../execplan/references/PLANS.md](../execplan/references/PLANS.md) in full and follow it **to the letter** — including the sections the execspec adapter supersedes for the controlled track (Progress with timestamped checkboxes, narrative milestones, Concrete Steps, novice-grade self-containment). That is track separation, not contradiction: over there, machinery replaces those sections; here, the document IS the machinery.

Save to `docs/doperpowers/execplans/YYYY-MM-DD-<topic>.md` (omit the triple-backtick envelope per PLANS.md's file rule). The bar: a fresh session with no conversation history — or a daemon spawned with nothing but this file — can implement it end-to-end and see it working.

## Step 3 — Execute

In an isolated workspace (doperpowers:using-git-worktrees). Follow PLANS.md's implementing contract as written: do not prompt your human partner for next steps; resolve ambiguities autonomously (the grill already exhausted the ones that needed a human); keep `Progress`, `Surprises & Discoveries`, and the `Decision Log` current at every stopping point; commit frequently.

This profile fits durable background daemons (doperpowers:orchestrating-daemons): the ExecPlan is exactly what a spawn prompt can carry, and it survives the daemon's context death — the document is the memory.

## Exit gate

Exactly one, at the end. Before merging: dispatch the final whole-branch review per doperpowers:requesting-code-review, then finish with doperpowers:finishing-a-development-branch. Its retrospective step writes into the ExecPlan's own `Outcomes & Retrospective` section — the ExecPlan is this track's spec-equivalent.
