---
name: issue-tracker
description: Use when managing the local issue board — registering tickets, dispatching background daemons to tickets, judging daemon state proposals, reconciling the board after time away, or asking what is in progress / blocked / dispatchable. The board lives in doperpowers/issue-tracker/ in the repo.
---

# Issue Tracker

A local, repo-portable issue board. Tickets are **purpose-units**: born as
pre-specs from `issue-register`, driven end-to-end (brainstorm → spec → plan →
build → PR) by background daemons (`orchestrating-daemons`), tracked as nodes
in `doperpowers/issue-tracker/map.json`.

**You (the main session) are the orchestrator — the board's only writer.**
Daemons never touch the board; they end turns with *proposal blocks* that you
judge and apply. All writes go through the scripts, from the MAIN checkout
only (they refuse worktrees).

## The two roles

| | writes the board? | how it talks |
|---|---|---|
| **Orchestrator** (main session — you) | yes, sole writer, via scripts | runs the toolkit; judges proposals |
| **Worker** (daemon, one ticket each) | never | reads its ticket md; ends turns with a proposal block |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path.

| state | meaning | note |
|---|---|---|
| `ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | a daemon is driving it (an epic stays here while children run) | optional |
| `blocked` | non-ticket blockage: credentials / auth / human hand | **required** |
| `needs-info` | waiting on knowledge: research or a human taste/product decision | **required** |
| `in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `done` | landed — verify the merge before flipping | optional |
| `wontfix` | rejected | **required** |
| `deferred` | tracked, not now | optional |

**Discriminant:** waiting on an *action/precondition* → `blocked`; waiting on
*knowledge/decision* → `needs-info`.

Ticket dependencies are **edges** (`blocked_by`), never states — eligibility is
computed. Epics (nodes with children) are never dispatched; the sweep moves
them automatically.

## Toolkit

Paths relative to this skill's `scripts/` directory. Use them — don't hand-edit
`map.json`.

| script | does |
|---|---|
| `board-register.sh <title> <category> [--state S] [--note N] [--parent T] [--blocked-by T,T] [--spawned-by T]` | add a node; prints `<id> <md-relpath>` — then YOU write that markdown (pre-spec) |
| `board-transition.sh <id> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes; runs the epic/unblock sweeps |
| `board-list.sh [state]` | board view; `ELIGIBLE` tag = dispatchable |
| `board-map.sh [--write]` | human telemetry: the board DAG as a Mermaid flowchart (state colors, epic boxes, block/lineage edges); `--write` saves `MAP.md` for the human — refresh it after transitions |
| `board-show.sh <id>` | node + md path + bound daemon |
| `board-bind.sh <uuid> <id>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: unapplied proposals, orphaned tickets, dispatchables |

## The dispatch loop

1. `board-list.sh` → pick an `ELIGIBLE` ticket.
2. Build a **self-contained spawn prompt**: the full ticket md content + the
   Worker Protocol block below.
3. `daemon-spawn.sh "<id>-<slug>" "<prompt>" <repo> <worktree-name>` (from
   `orchestrating-daemons` — always a worktree; workers write code).
4. `board-bind.sh <uuid> <id>` then `board-transition.sh <id> in-progress`.
5. When a daemon's turn ends, judge its proposal block (per
   `orchestrating-daemons`: answer / queue for the human / wake the human),
   then apply or refuse with `board-transition.sh`.
6. On `done`: verify the PR actually landed first — `done` means *landed*,
   not "worker says finished". Append an outcome summary to the ticket md.

**Reconcile-on-wake:** been away? `board-reconcile.sh` first. It lists what
the daemons proposed while you were gone and what needs respawning.

## Worker Protocol (embed VERBATIM in every spawn prompt)

```
You own ticket <ID> end-to-end: brainstorm → spec → plan → build → PR, in your
worktree. Your ticket brief is below; treat it as the source of truth.

The issue board is READ-ONLY for you. To change your ticket's state, end your
turn with a single-line JSON proposal block:
{"ticket":"<ID>","from":"<current>","to":"<proposed>","reason":"…","evidence":"…"}

Escalation: waiting on an action/precondition (credentials, access, another
ticket's work) → propose "blocked". Waiting on knowledge or a human
taste/product decision → propose "needs-info". State the question crisply and
END YOUR TURN — never guess above your scope, never expand it.
```

## Ticket markdown

`doperpowers/issue-tracker/tickets/<id>-<slug>.md` — written by YOU (register
time, plus a terminal outcome summary). Frontmatter `id/title/category` only —
state lives in the map alone. Body: Problem & intent / Constraints / Success
criteria / Open questions / Decision log.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, an
issue-register session, or a worker's design phase — is registered on the
board THE MOMENT the deferral is decided, with its lineage as edges:

- `--spawned-by <origin>` — the ticket whose design session produced the cut
- `--blocked-by <ids>` — what must land first (often the origin ticket itself,
  and/or the moving interface that forced the deferral)
- `--parent <epic>` — when the work belongs to an existing epic
- If the repo tracks work on GitHub, file the GH issue in the same breath and
  cross-reference it from the ticket md.

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket md's Decision
log records *why* it was cut, so nobody re-litigates it later.

## Edge cases

- `orphaned` in reconcile → the daemon died: respawn, re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the `blocked_by` edge or
  wontfix the dependent; that is a human call.
- `map.json` corrupted → restore from git history.
- Never run board scripts from a worktree (they refuse; work from the main checkout).
