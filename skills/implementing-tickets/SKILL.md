---
name: implementing-tickets
description: Use when dispatching implementation workers onto board tickets, gating a ticket before building (well-defined + well-scoped), parking tickets (needs-human / needs-info / interactive-preferred), decomposing an oversized ticket into child tickets, choosing direct-vs-execplan execution, or running the spike lane (category `spike` — exploration tickets whose deliverable is findings, never a merge) — the implement-side autonomous loop; the inverse of doperpowers:reviewing-prs.
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
| `references/spike-worker-protocol.md` | the Spike Worker Protocol — rendered instead when the ticket's category is `spike` (the exploration lane below) |
| `references/engine-blocks/` | per-engine EXECUTION text (claude: TDD/execplan skills; codex: the same discipline via the vendored `.agents/skills` doctrine) — both mandate in-thread solo execution; composed into the protocol at render time (implement protocol only — spikes are exploration, not TDD) |
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

**Check 2 — well-scoped.** Fits ~1–2 ExecPlans — big-but-atomic work that
cannot land halfway still counts as ONE unit (that is what ExecPlan mode
exists for); decompose only work whose children could land on main
independently. Too big forks on ONE question: *can the remainder be
written as self-contained child pre-specs right now?* Yes → decompose.
No → `interactive-preferred`.

**The verdict is the worker's first board write.** Dispatch writes nothing;
`in-progress` + a `[gate]` comment = pass, a park state = fail.

## Park discriminant — who unparks it?

- **The human as themselves** (a decision only they can make, or a
  real-world input only they possess: credentials, auth, production data)
  → `needs-human`. Note = the question list, each with a recommended answer.
- **Knowledge work anyone could do** but substantial enough to be its own
  work-unit → `needs-info` (rare by design — the research threshold above
  keeps orient-work lookups out of it).
- **Ongoing steering of the work's core, not one answer** — an
  architecture spine or product-core design whose decisions are so
  entangled that each answer reshapes the next question (a question list
  cannot carry them) → `interactive-preferred` — summons the human into a
  live doperpowers:brainstorming session; the note says which decision
  areas need steering. Any *enumerable* set of open decisions, however
  many and whatever the ticket's size, is `needs-human` — in practice
  this state is rare and marks genuinely architecture-heavy or
  taste-shaped work.

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

- **Direct** — the pre-spec is the plan: evidence-first execution
  (testable logic → TDD; UI → build + verify rendered behavior;
  config/docs → the relevant check passes), commit, PR.
- **ExecPlan** — doperpowers:execplan when the work needs the document to
  survive context death: multiple sequenced milestones, or big-but-atomic
  work that cannot land halfway. The gate already served as execplan's
  grill.

There is no in-daemon execspec mode: work that wants a living spec with a
human at the gates is precisely `interactive-preferred`.

**No live progress mirror.** Status writes happen only where a scope ends:
the PR body is the closing artifact (`Closes #N`, `## Validation Evidence`
— cross-checked by the review worker, `## Confusions` when warranted,
FOLLOW-UPS), and a park comment carries the questions plus a 3–6 line
orientation summary. Mid-flight visibility is the board's state label —
watching a worker work is supervision, which this pipeline removed.

## The spike lane (category `spike`)

The board's second lane, for exploration: the gate's value scales with the
cost of a wrong PR, a spike's value scales with the cost of NOT trying
ideas — they coexist on one board but never in one lane. A spike ticket's
deliverable is **information** (a structured `[findings]` comment), never a
merge; failures discard at the cost of reading a comment. Dispatch renders
`references/spike-worker-protocol.md` instead of the implement protocol —
same ritual, same binding, no EXECUTION_BLOCK.

What changes and what doesn't:

- **Gate variant** — Check 1 asks that the worker ESTABLISH a crisp
  question (what do we want to learn / how would we recognize an answer /
  where to start), not that every fork be answered. Vague briefs are
  normal — where a reasonable reading exists the worker supplies the
  missing piece itself and records the interpretation in the `[gate]`
  comment (the contract its findings answer); it parks only when no
  reasonable reading yields all three. Taste forks met during exploration
  are findings content ("this fork exists; A and B look like this"),
  never parks. Check 2 survives: too-big questions decompose into
  narrower child spikes.
- **Merge bar is free** — the optional evidence PR is a DRAFT (never
  `Closes #N`, never marked ready): review dispatch skips drafts and land
  dispatch refuses them, so spike code cannot enter the merge lane by
  construction.
- **End state reuses the board** — a finished spike parks
  `needs-human "findings ready: <one-line answer>"`: no new state, no
  worker terminal-state authority, and the findings land exactly where the
  human already looks (the wake queue). The human closes (`done` — the
  manual flip for non-PR work), relays a follow-up question
  (`board-answer.sh` resumes the bound session, which explores and
  re-parks), or graduates.
- **Graduation** — production work the findings clearly justify is
  registered `--spawned-by <spike>` with honest gate-triage against the
  IMPLEMENT gate; murkier outcomes stay a Recommendation line for the
  human.
- Research-heavy spikes often want `engine:claude` (web reach); the label
  mechanism is unchanged.
- Category labels are plain words by design (`bug`/`enhancement` always
  were) — in a consumer repo that already used a descriptive `spike`
  label, existing tickets carrying it now read as spike-lane tickets:
  re-label them before dispatching there.

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
- **needs-human answered** — preferred path: the wake ritual relays the
  answers to the still-bound session (issue-tracker's `board-answer.sh` —
  park = pause, not death); the resumed worker re-states its gate verdict
  against the answers before proceeding. Fallback (no/dead session, or
  scope-reshaping answers): flip back to `ready-for-agent`; the next
  dispatch re-runs the gate with the comments as ticket content. Either
  way, answers belong in the body/comments, not in chat.
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
