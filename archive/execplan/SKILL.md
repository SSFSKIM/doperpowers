---
name: execplan
description: Use when taking a well-scoped, delegable piece of work through the autonomous track — a relentless grill that exhausts ambiguity up front, then one self-contained ExecPlan. Invoke this only after doperpowers:brainstorming ran and routed here; never straight from a request.
---

# ExecPlan Track

> Retired 2026-09-12. The one-unit shape this skill served now lives in the living spec: `skills/brainstorming/references/living-spec.md` says what a spec that carries its own execution binds, brainstorming's step 9 and `agents/plan-executor.md` carry the execution contract, and the sections of PLANS.md that bind are quoted verbatim in living-spec.md — the vendored source itself is kept beside this file at `references/PLANS.md`. Kept for reference; not loaded by any harness. Design: `docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`.

## Overview

This repo has two development tracks. The controlled pipeline (doperpowers:brainstorming → living spec → doperpowers:writing-plans → doperpowers:subagent-driven-execution) keeps human involvement available as design judgment arises. This track front-loads that judgment in one grilling session, after which you author a single self-contained ExecPlan and execute it without interruption. It inherits brainstorming's approval boundary: unresolved product, taste, or substantive design decisions wait for your human partner; already-authorized technical scope proceeds once the grill closes. Autonomy is safe because the grill exhausted the ambiguity space.

## Which track?

Routing lives in doperpowers:brainstorming's track choice (its grill is this track's Step 1) — you normally arrive here with the grill done and its approval boundary satisfied, either by existing authorization for resolved technical work or by your human partner's approval of the product, taste, or substantive design decisions. The route itself needs no separate confirmation.

- **This track**: the work is delegable and the grill can resolve every open question up front. Fits long-running work and durable background daemons.
- **Controlled track**: taste-heavy, novel, or high-stakes work where design judgment keeps arising mid-flight → doperpowers:brainstorming.

## Step 1 — Grill

The grill and its three interview moves (sharpen fuzzy terms, stress-test with concrete scenarios, cross-reference with code) are vendored verbatim in doperpowers:brainstorming's clarification step — one vendor point, shared by both tracks. You normally arrive here with the grill already done. Entering this track directly? Run doperpowers:brainstorming's grill first — never author an ExecPlan from an un-grilled conversation.

Everything the grill resolves lands in the ExecPlan: term definitions inline where used, decisions (with the rejected alternatives and why) in its Decision Log. No CONTEXT.md, no ADRs — the ExecPlan is this track's only artifact.

## Step 2 — Author the ExecPlan

Read [../execplan/references/PLANS.md](../execplan/references/PLANS.md) in full and follow it **to the letter** — including the sections the living-spec adapter (doperpowers:brainstorming's references/living-spec.md) supersedes for the controlled track (Progress with timestamped checkboxes, narrative milestones, Concrete Steps, novice-grade self-containment). That is track separation, not contradiction: over there, machinery replaces those sections; here, the document IS the machinery.

Save to `docs/doperpowers/execplans/YYYY-MM-DD-<topic>.md` (omit the triple-backtick envelope per PLANS.md's file rule). The bar: a fresh session with no conversation history — or a daemon spawned with nothing but this file — can implement it end-to-end and see it working.

## Step 3 — Execute

In an isolated workspace ([../subagent-driven-execution/isolated-workspace.md](../subagent-driven-execution/isolated-workspace.md)). Follow PLANS.md's implementing contract as written: do not prompt your human partner for next steps; resolve ambiguities autonomously (the grill already exhausted the ones that needed a human); keep `Progress`, `Surprises & Discoveries`, and the `Decision Log` current at every stopping point; commit frequently.

This profile fits durable background sessions — seats spawned through doperpowers:sminos: the ExecPlan is exactly what a spawn prompt can carry, and it survives the seat's context death — the document is the memory.

## Exit gate

Exactly one, at the end. Before merging: dispatch the final whole-branch review through doperpowers:review-code against `<base-branch>` at the level the branch warrants (a rung agent, or the panel for a large branch), then write the ExecPlan's own `Outcomes & Retrospective` section (the ExecPlan is this track's spec-equivalent), commit it, and integrate the branch per the isolated-workspace reference's finish rules.
