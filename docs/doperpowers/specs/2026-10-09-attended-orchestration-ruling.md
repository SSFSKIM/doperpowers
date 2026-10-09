# Attended orchestration: the owner's ruling and the MAWS evidence (2026-10-09)

## Ruling (owner, 2026-10-09)

Fully unattended operation is not a target. A human's sense has to join
the gaps in agent work: no design articulates the intent in a human's head
well enough for agents to run it to the end, and MAWS — with three readable
reference apps narrowing nearly every taste fork — still needed its owner.
What follows from that is not park → resume. When a human is needed, the
faster form is mediation through the orchestrator: the owner talks to the
interactive session that holds the design, and that session relays, rules,
and dispatches. Tickets keep tracking work and its state, but the regime
that was actually used is "tickets as the backlog, the owner saying which
ones may go, the orchestrator dispatching bounded subagents" — the
implementer auto-dispatch replaced by the main session acting on the
owner's word.

## Evidence A — MAWS, session e3ce7feb (2026-09-25 → 10-09)

A macOS Electron workstation built from an empty directory: 3,512 commits in
eleven days; three composites (the P0 charter C1–C12 with contracts X1–X8,
the UX-fundamentals wave loop, the P1 extension E0–E13); the owner's daily
driver from 2026-10-01. The session's own ledger: $7,298 (opus $4,512 for
executors and workers, fable $2,061 for the main session, astra $494, sol
$229).

Shape: one interactive fable session as the architect for the whole span —
7,909 API calls, 52 compactions, the charter's tracking map, Decision Log
and the children's ledgers as its memory across them. Under it a subagent
tree of 1,017 agents, depth ≤ 3: 29 plan-executor dispatches (each 4–16
hours, each marshalling 8–43 task-executors, task-reviewers and
whole-branch reviewers), at most five executors and fifteen depth-1 agents
live at once. No sminos seat and no board for the product itself. The
main session sent 546 messages to its agents (rulings, cross-child
interface asks decided on the spot, owner notes relayed, worker hand-backs
relayed) and received 482 task notifications.

The owner: 195 prompts in thirteen days (about 150 distinct). Roughly 45
product and taste judgments with screenshots ("follow Codex / Claude
Desktop unless my notes override"); about 30 AskUserQuestion answers,
twenty-two of them in one hour at the charter; seven "resume the agents,
nested ones too" after outages; about twenty manual `/compact` before the
self-compact mod took over on 10-07; about twelve status probes; nine
model-routing rulings; two phase transitions. About a quarter of the
owner's messages tended the machinery rather than the product — and each
of those classes is now owned in-harness (a resume script and a coming
harness fix, `hooks/mods/compact.tsx`, `hooks/mods/agents.tsx`), not by a
different orchestration substrate.

What made it work: contracts fixed before dispatch (wave 2 ran five
executors in parallel by construction); probe-before-design (engine facts
as fixtures); two to three adversarial review rounds on each child's
execution document before its executor started (24 adversarial reviews on
09-28/29; execution-time design forks escalated to the owner about six
times across P0); a narrow design space (three reference sources, taste
decided as "that one, with this screenshot"); debt fixed in waves after
each merge; the owner as the acceptance oracle through daily use.

Cost of the shape, accepted: per-child reviews do not replace the scale
review (79 defects after every child reviewed clean — known, and run
anyway); the owner's Mac as the build farm (load 70–436, a shared-slot
wrapper, quiet e2e mode) — taken for the parallelism.

## Evidence B — cua, session 1ea561bc (2026-10-05 → 10-09)

The board used as the ruling describes. `board-register` 30 times, zero
`execute-dispatch`/`review-dispatch`, 71 subagent dispatches by the main
session on the owner's calls ("#6 #8 #9 진행", "82진행", "97 98 93 94
바로진행"), each ticket a bounded general-purpose or plan-executor
subagent, a reviewer-medium per PR, 51 `gh pr merge` by the main session.
116 owner prompts in four days, most of them "go", "what's left in the
backlog", "is #N done". The owner once announced seven to eight hours
away; the session continued on what it could do and queued the rest for
the owner's return — mediation, not parking.

## What this settles

1. `doperpowers:decomposing` loses "a leaf may also run as a sminos child
   seat … when the dispatching agent judges a live, addressable session
   worth its cost" (v7.141.3). No observed use; the executor of a
   composite child is a subagent of the session that holds the design,
   however many hours it runs.
2. `doperpowers:sminos` keeps the role its "Where work goes" already
   states — the process substrate for work with no live root session (the
   board pipeline's workers, standing daemons such as the feedback
   triage poller) and the operator's fleet tools — and is not an executor
   form inside an attended composite. The proposal from this analysis to
   run hours-long plan-executors as child seats is rejected: the costs it
   targeted are owned in-harness (above).
3. Open: `doperpowers:issue-tracker` frames the board around "no
   orchestrator-judge" — mechanical dispatch, park states, the wake
   ritual. The regime in use has an orchestrator-judge (the interactive
   session) and the owner mediating through it; the board is its backlog
   and state ledger. Whether that framing is re-cut, and how far (the
   autonomous loop kept as an option for the edge-ticket and triage
   cases, or demoted), is the owner's scope decision, not taken here.

## Sources

MAWS: `~/.claude/projects/-Users-new-Developer-GitHub-MAWS/e3ce7feb-….jsonl`
and its `subagents/*.meta.json`; `docs/charter.md` §17 and §20,
`docs/doperpowers/plans/2026-10-01-ux-fundamentals-waves.md` §7,
`docs/doperpowers/plans/2026-10-05-p1-extension.md` §13–§15 in the MAWS
repository. cua: session `1ea561bc-….jsonl` in the same project directory.
