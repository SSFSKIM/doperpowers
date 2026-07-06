---
name: issue-tracker
description: Use when managing the issue board — registering tickets, dispatching background daemons to tickets, judging daemon state proposals, reconciling the board after time away, or asking what is in progress / blocked / dispatchable. The board IS the repo's GitHub issues; the toolkit lives in this skill's scripts/.
---

# Issue Tracker

A repo's issue board, stored where it cannot fork: **GitHub Issues is the
single source of truth.** Tickets are **purpose-units**: born as pre-specs
from `issue-register`, driven end-to-end (orient → size → method → build → PR)
by background daemons (`orchestrating-daemons`), tracked as GitHub issues with
typed edges (sub-issue = parent, dependency = blocked-by).

There is no local board file, nothing to sync, and no worktree restriction —
every script talks to GitHub directly (`gh` required, fail-loud) and may run
from any checkout. `doperpowers/issue-tracker/` in the consumer repo survives
only as a gitignored render cache for `board-map.sh`.

**You (the main session) are the orchestrator — the board's judge.** Daemons
never write the board beyond their own ticket's state; they end turns with
*proposal blocks* that you judge and apply. All writes go through the scripts
(the Hard Gate below).

## The Board Write Hard Gate (put this in the consumer CLAUDE.md)

> Board Write Hard Gate: issue creation and every state/edge change MUST go
> through the issue-tracker scripts — never raw `gh issue edit` for
> `status:*` labels or sub-issue/dependency edges. At registration, category +
> status + parent + blocked-by are each either set or consciously N/A —
> silence is not N/A.

The scripts are the schema: they enforce the state machine, mandatory notes,
PR gates, and cycle/deadlock checks that GitHub's API will not.
`board-lint.sh` catches what slips past (run it on wake; wire it to cron for
unattended repos).

## The two roles

| | writes the board? | how it talks |
|---|---|---|
| **Orchestrator** (main session — you) | yes, via scripts | runs the toolkit; judges proposals |
| **Worker** (daemon, one ticket each) | only its OWN ticket's state, via `board-transition.sh` | reads its issue; ends turns with a proposal block |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path.

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-agent` | open + `status:ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | open + `status:in-progress` | a daemon is driving it (an epic stays here while children run) | optional |
| `blocked` | open + `status:blocked` | non-ticket blockage: credentials / auth / human hand | **required** |
| `needs-info` | open + `status:needs-info` | waiting on knowledge: research or a human taste/product decision | **required** |
| `in-review` | open + `status:in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `done` | **closed — completed** | landed — verify the merge before flipping | optional |
| `wontfix` | **closed — not planned** | rejected | **required** |
| `deferred` | open + `status:deferred` | tracked, not now | optional |

Exactly one `status:*` label on every open issue; terminal states are the
close reason (no label). An issue outside this scheme is `untracked` (no
label) or `conflict` (2+ labels) — lint FAILs it; `board-transition.sh`
repairs it (any open state is reachable from either).

**Discriminant:** waiting on an *action/precondition* → `blocked`; waiting on
*knowledge/decision* → `needs-info`.

Ticket dependencies are **edges** (native GitHub dependencies), never states —
eligibility is computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Epics (issues with
sub-issues) are never dispatched; the sweep moves them automatically. Notes
land twice: the current note in the issue's `board:meta` body block, the audit
trail as `[board]` comments.

## Toolkit

Paths relative to this skill's `scripts/` directory. Ticket ids are issue
numbers (`42` or `#42`). Target repo = `$BOARD_REPO` (owner/name) or the
checkout's repo.

| script | does |
|---|---|
| `board-register.sh <title> <category> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; prints `<number> <url>` — then YOU flesh out the pre-spec body (`gh issue edit <n> --body-file …`) |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes + the in-review PR gate; runs the epic/unblock sweeps; repairs untracked/conflict issues |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-list.sh [state]` | board view; `ELIGIBLE` tag = dispatchable |
| `board-map.sh [--write]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered-DAG: pan/zoom, node detail, state filter, epic collapse) and **`BOARD.md`** (table) into the gitignored render dir. No argument prints the table |
| `board-show.sh <n>` | node + issue URL + bound daemon |
| `board-bind.sh <uuid> <n>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: unapplied proposals, orphaned tickets, dispatchables, then a lint pass |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required, no dependency cycles. `FAIL … FIX: …` lines, exit 1 |
| `board-migrate-gh.sh [--board FILE] [--apply]` | one-shot v6→v7 migration: push a legacy `board.json` into GitHub (dry-run by default) |

## The dispatch loop

1. `board-list.sh` → pick an `ELIGIBLE` ticket.
2. Build a **self-contained spawn prompt**: the full issue body (`gh issue
   view <n>`) + the Worker Protocol block below.
3. `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>` (from
   `orchestrating-daemons` — always a worktree; workers write code).
4. `board-bind.sh <uuid> <n>` then `board-transition.sh <n> in-progress`.
5. When a daemon's turn ends, judge its proposal block (per
   `orchestrating-daemons`: answer / queue for the human / wake the human),
   then apply or refuse with `board-transition.sh`.
6. On `done`: verify the PR actually landed first — `done` means *landed*,
   not "worker says finished". Append an outcome comment to the issue.

**Reconcile-on-wake:** been away? `board-reconcile.sh` first. It lists what
the daemons proposed while you were gone, what needs respawning, and any
schema drift (lint).

## Worker Protocol (embed VERBATIM in every spawn prompt)

```
You own ticket #<N> end-to-end in your worktree. Your ticket brief is below;
treat it as the source of truth.

ORIENT BEFORE YOU BUILD — do not open a source file until you have sized the
work against the brief and picked a method to match:
- Trivial / mechanical (one obvious change, no design fork) → do it inline, then PR.
- Well-scoped & delegable → doperpowers:execplan (front-load the grill against
  this brief, author one self-contained ExecPlan, execute it to the letter).
- Large, multi-part, or needs a living spec → doperpowers:execspec then
  doperpowers:writing-plans, then execute the plan.

Reliability and human-intent alignment come before speed, and you are NOT
unattended: every turn you end is read by an orchestrator who answers you or
elevates the question to a human. So the moment ANY part of the task is
ambiguous — intent, scope, a design/taste fork, an acceptance detail — do NOT
guess and do NOT proceed. BRAINSTORM IT: run doperpowers:brainstorming and
surface each open question by ending your turn with a "needs-info" proposal
stating the question crisply; resume once you have the decision. Autonomy is
earned only where the brief is genuinely unambiguous — everywhere else, ask.

You may move your OWN ticket only, via the issue-tracker scripts:
board-transition.sh <N> in-progress when you start; in-review with --pr when
your PR opens. Every other board change is a proposal — end your turn with a
single-line JSON proposal block:
{"ticket":"<N>","from":"<current>","to":"<proposed>","reason":"…","evidence":"…"}

Escalation: waiting on an action/precondition (credentials, access, another
ticket's work) → propose "blocked". Waiting on knowledge or a human
taste/product decision → propose "needs-info". State the question crisply and
END YOUR TURN — never guess above your scope, never expand it.
```

## The ticket body (pre-spec)

The issue body — seeded by register, fleshed out by YOU (register time, plus a
terminal outcome comment). Sections: Problem & intent / Constraints / Success
criteria / Open questions / Decision log. The trailing `<!-- board:meta … -->`
block is script-owned (spawned-by / relates-to / branch / pr / note) — edit
around it, never inside it.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, an
issue-register session, or a worker's design phase — is registered on the
board THE MOMENT the deferral is decided, with its lineage as edges:

- `--spawned-by <origin>` — the ticket whose design session produced the cut
- `--blocked-by <numbers>` — what must land first (often the origin ticket
  itself, and/or the moving interface that forced the deferral)
- `--parent <epic>` — when the work belongs to an existing epic

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket's Decision log
records *why* it was cut, so nobody re-litigates it later.

## Edge cases

- `orphaned` in reconcile → the daemon died: respawn, re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <n> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- An issue labeled by hand (or by external automation) lands `untracked` /
  `conflict` → lint names it; `board-transition.sh` repairs it.
- Consumer label automation that already speaks `status:*` (e.g. assign →
  `status:in-progress`) is a legitimate board writer — same store, same
  vocabulary, no sync.
