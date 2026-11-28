---
name: organizing-sprints
description: Verified guidance on turning a pile of raw observations or half-formed ideas — an ideadump, a walkthrough, a meeting transcript — into the next sprint of work, especially when the notes may misread the code. A single idea is doperpowers:brainstorming; a deliberate goal that needs dividing is doperpowers:decomposing.
disable-model-invocation: true
---

# Organizing Sprints

## Overview

Turn a raw multi-observation note into one **umbrella sprint spec**, then
materialize that spec onto the issue board as tickets with typed edges.
The note is testimony; the codebase is truth. Every observation is grounded
in code reality before it becomes work, every open question is landed by
grilling before the spec is authored (born landed beats revised), and the
spec — not the board — is the primary artifact: tickets, dependency edges,
the plans derived from it, and the next milestone's reservations all flow
from it, and its living sections track the sprint through to retrospective.

A single idea, however fuzzy, is doperpowers:brainstorming's: one
observation has nothing to cluster or cut.

## The pipeline

1. **Ingest & atomize** — parse the note into discrete atomic observations.
   Lose none; merge none silently. When the note is itself a digest of
   richer primary material (a transcript, a recording), atomize from the
   primary material — a summary is someone else's lossy atomization. Where
   each observation came from (who said it, seeing what) rides along — it
   becomes the epic's context line. For ideas and proposals, two more
   things ride along: the concrete shape they were pitched in (the
   sketched interaction, the worked example — the form is part of the
   idea, not packaging around it) and their conversational status
   (endorsed, rejected, floated in passing, illustrative). Status is
   testimony too: record it, and leave ruling on it to the grill.
2. **Ground every observation in code** — fan out parallel explorations by
   area (native subagents) and classify each
   observation against code reality (see The verification table below).
3. **Tentative decomposition** — cut streams and epics. An epic is an
   independently shippable purpose-unit; two observations share an epic
   only if they share a problem or outcome, not merely a topic or a page.
   Unsure whether two observations are one epic or two? Ask — over-merging
   hides independent shippables; over-splitting loses coherence. Present
   the tentative map and get a reaction before deep grilling.
4. **Grill until every question lands** — batched frontier rounds, full
   record into the Decision Log (see The grill below). Milestone boundaries
   are grill questions too: work that outgrows this sprint is landed as a
   named reservation for the next milestone, not silently absorbed or
   dropped.
5. **Author the umbrella spec** — per `references/sprint-spec-template.md`,
   born landed: v1 already carries the grill's decisions. Acceptance
   criteria are observable behavior. No per-epic plans of work —
   a big epic's plan is derived when the epic is taken, from this document.
6. **Self-review, then your human partner's approval** — check that
   every atomized observation maps to an epic, a maintenance bundle, a
   deferral, or an explicit park. Commit the spec and ask them to review
   it. Tickets are registered from the approved spec: a sprint's worth of
   issues cut from a draft has to be closed one by one.
7. **Materialize onto the board** — see Materialization below. Often a
   separate session: the spec's tracking-map section is the handoff
   contract.
8. **Hand off, keep the spec alive** — show the board; tickets are taken
   per doperpowers:issue-tracker, named by your human partner or picked up
   when ready to build. During the sprint the spec's Progress /
   Decision Log / Surprises stay current; the retrospective closes it; its
   Deferred section seeds the next organizing run.

## The verification table

The heart of the grounding phase and the section the rest of the spec
builds on. Classify every observation:

| class | meaning | what it demands |
|---|---|---|
| `[BUG]` | confirmed real defect | a diagnosis — cause, not just symptom — with evidence at the depth the claim needs (a surprising or contested row cites file:line; an obvious one doesn't) |
| `[MISREAD]` | observation contradicts code reality | correct the record AND extract the real requirement hiding under the misread — a wrong observation usually points at a real want, stated wrongly |
| `[BUILT]` / `[PARTIAL]` | already exists, fully or partly | no work, or the delta only — name where it lives |
| `[NOT-BUILT]` | absent | the sprint's real work |

A misread trusted as written ships the reverse of the actual requirement,
and a feature assumed built but never checked becomes invisible sprint
scope.

## The grill

The interview protocol, adapted from doperpowers:brainstorming's grill:

- Batched frontier rounds per doperpowers:brainstorming's grill, each
  question with your recommended answer: multiple-choice questions ride
  AskUserQuestion where the options are enumerable; open-ended is fine
  as prose.
- A question the codebase can answer is answered by reading, never asked.
- Sharpen fuzzy terms; stress-test with concrete scenarios; cross-reference
  the human's claims about current behavior with the code.
- Triage: grill what is fuzzy or important; don't grind already-clear notes
  to death across a large dump.

Three moves specific to this skill:

- **Auto-landed decisions** — when grounding dissolves every alternative,
  record the decision as `[DECIDED-AUTO]` with the code fact that killed
  the alternatives. It enters the Decision Log like any other decision,
  without spending a question on it.
- **Externally-owned questions** — a question only a specific person can
  answer (copy sign-off, business input) does not block authoring: record
  it in Open Questions with owner + deadline and keep moving.
- **Ambiguous-status ideas** — an idea the source neither adopted nor
  killed (a sketch, an aside, an example that might be a requirement) is a
  grill question: present it with its context and your recommended
  disposition, and let the human rule it in, out, or deferred. Dropping it
  during atomization or grounding is a silent drop.

Every landed decision is logged with its rejected alternatives and why each
lost.

## Materialization

From the approved spec, often in a fresh session (the spec is
self-contained). A sprint already on the board is not run through this
skill again: answer on its tickets and register only the deltas.

- One ticket per epic via `board-register.sh` (doperpowers:issue-tracker):
  priority always; slices as `--parent` children; ordering as
  `--blocked-by`; grill-flagged parks at birth (`--state needs-human` for
  an externally-owned decision, `--state interactive-preferred` for
  product-core work, `--state deferred` for next-milestone reservations —
  notes required).
- Ticket bodies are fleshed to the pre-spec bar: self-contained, so a
  fresh-context session can take it from the body alone. Carry the epic's
  decisions and acceptance criteria into the body, and cite the spec's epic
  section (path + epic id) for surrounding context — the citation is
  context, not a substitute for self-containment.
- Milestone and epic labels via raw `gh` are fine; states and edges go
  through the issue-tracker scripts, which keep the board's schema.
- **Disposition every pre-existing open ticket the sprint touches** —
  absorb into an epic, defer with a note, re-cut milestone/labels, or flag
  as a close candidate. A sprint that only adds tickets leaves the board
  lying.
- Deferred-section reservations are registered as `deferred` tickets now:
  a scope-out becomes a ticket when the deferral is decided
  (issue-tracker's deferral convention).
- Finish with `board-lint.sh` at 0 FAIL, and write the record (epic → issue
  number, edges, dispositions) back into the spec's tracking-map section.

## Scale

The dump sets the scale — a handful of loose observations or a quarter's
worth of accumulated notes both run the same phases; only the artifacts
compress or grow. Epic count, ticket count, and document length are
outputs of the shape rules (purpose-unit epics, gate-passing tickets),
never targets: no floor, no ceiling. What every scale keeps: the
verification table, observable acceptance criteria, the Decision Log with
rejected alternatives, the tracking map, and the Deferred section.
