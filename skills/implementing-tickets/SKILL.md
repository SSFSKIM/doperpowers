---
name: implementing-tickets
description: Use when dispatching implementation workers onto board tickets, gating a ticket before building (well-defined + well-scoped), parking tickets (needs-human / needs-info / interactive-preferred), decomposing an oversized ticket into child tickets, or choosing direct-vs-execplan execution — the implement-side autonomous loop; the inverse of doperpowers:reviewing-prs.
---

# Implementing Tickets — the autonomous implement loop

## Overview

The implement-side mirror of doperpowers:reviewing-prs: where the review
loop puts its rigor gate at the END of the pipeline (confident-ready before
merge), this loop puts its rigor gate at the START — **a worker may not
write code until the ticket passes the Ticket Gate**. There is NO
orchestrator: a worker's escalation targets are the board itself (states,
notes, comments) and the human on their next wake; turn-end messages are
audit trail, not requests. Full design + rationale:
`docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md`.

## The pieces

| piece | what |
|---|---|
| `references/implement-worker-protocol.md` | the Implement Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every spawn prompt |
| `references/engine-blocks/` | per-engine EXECUTION text (claude: TDD/execplan skills; codex: the same discipline inlined) — composed into the protocol at render time |
| The Ticket Gate | the pre-code pass/park verdict (below) |
| board schema + dispatch ritual | owned by doperpowers:issue-tracker (states, scripts, the mechanical ritual, the wake ritual) |
| `scripts/` | empty this phase — the auto-attach trigger (`implement-dispatch.sh` + workflow template) lands here next phase |

## The Ticket Gate

Runs during ORIENT, before any source file opens — brainstorming's grill in
absentia: every answer must come from the ticket body, the codebase, or
repo docs. Trivial lookups are orient work, never a park.

**Check 1 — well-defined.** Every fork the implementation will hit:

| fork class | who answers |
|---|---|
| mechanical/technical, one obvious best answer | the worker — parking these is a protocol violation, not caution |
| non-trivial architecture (subsystem boundary, data model, API shape) | ticket + codebase; unanswered → gate-fail |
| product design or taste, **major or minor** | the ticket; unanswered → gate-fail — even minor taste is never the worker's call |

**Check 2 — well-scoped.** Fits ~1–2 ExecPlans. Too big forks on ONE
question: *can the remainder be written as self-contained child pre-specs
right now?* Yes → decompose. No → `interactive-preferred`.

**The verdict is the worker's first board write.** Dispatch writes nothing;
`in-progress` + a `[gate]` comment = pass, a park state = fail.

## Park discriminant — who unparks it?

- **The human as themselves** (a decision only they can make, or a
  real-world input only they possess: credentials, auth, production data)
  → `needs-human`. Note = the question list, each with a recommended answer.
- **Knowledge work anyone could do** but substantial enough to be its own
  work-unit → `needs-info` (rare by design — the research threshold above
  keeps orient-work lookups out of it).
- **Ongoing steering, not one answer** → `interactive-preferred` — summons
  the human into a live doperpowers:brainstorming session; the note says
  which decision areas need steering.

## Decompose — the one scoping behavior

Children via `board-register.sh --parent <original>`; sibling ordering via
`--blocked-by` (a chain IS serialization — serial vs parallel is a
dependency shape, not a policy branch). `--spawned-by` stays reserved for
scope-outs/follow-ups discovered during work. Each child is gate-triaged
honestly at registration (`ready-for-agent` only if the worker believes it
passes the gate). Register only children specifiable as self-contained
pre-specs NOW; contingent phases live as a `## Roadmap` section in the
parent body — the worker finishing phase K registers phase K+1 at PR time.
The parent becomes an epic (never dispatched; the sweeps move it). The
decomposing worker writes no code. Recursion is emergent: each child's
worker re-runs the same gate; no depth machinery exists.

## Execution — two modes on gate pass

- **Direct** — the pre-spec is the plan: TDD, commit, PR.
- **ExecPlan** — doperpowers:execplan when the work has 2+ milestones or
  enough design sequencing that a fresh session would need the document to
  survive context death. The gate already served as execplan's grill.

There is no in-daemon execspec mode: work that wants a living spec with a
human at the gates is precisely `interactive-preferred`.

## Worker authority

Own ticket's open states via `board-transition.sh`; direct registration of
decomposition children (`--parent`) and follow-up tickets (`--spawned-by`).
NEVER: terminal states (`done` arrives by the PR's `Closes #N` merge;
`wontfix` is recommended via a `needs-human` park, decided by the human),
other tickets' states (cross-ticket observations are comments), scope
beyond the ticket. There is no proposal block — with no judge to receive
proposals, registration and comments are the only channels.

## Edge cases

- **Dispatched onto an epic** — refuse: epics are never dispatched; end the
  turn naming the mistake (the sweep owns epic states).
- **needs-human answered in comments** — the human flips the ticket back to
  `ready-for-agent`; the next dispatch re-runs the gate with the comments
  as ticket content. Answers belong in the body/comments, not in chat.
- **Worker dies mid-build** — `board-reconcile.sh` flags the orphaned
  `in-progress` ticket; respawn re-runs the gate from fresh context (prior
  `[gate]` comments are context, not inherited trust).
- **Gate-fail discovered mid-build** (a taste fork surfaces only once code
  exists) — same protocol, late: park (`in-progress → needs-human` /
  `interactive-preferred` are legal), commit WIP to the branch, state the
  park crisply, end the turn.

## Interim dispatch

Until the auto-attach trigger lands, dispatch is the mechanical ritual in
doperpowers:issue-tracker (render this skill's protocol → spawn → bind —
no board write, no judgment). The trigger phase replaces only who invokes
it.
