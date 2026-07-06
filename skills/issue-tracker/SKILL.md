---
name: issue-tracker
description: Use when managing the local issue board — registering tickets, dispatching background daemons to tickets, judging daemon state proposals, reconciling the board after time away, or asking what is in progress / blocked / dispatchable. The board lives in doperpowers/issue-tracker/ in the repo.
---

# Issue Tracker

A local, repo-portable issue board. Tickets are **purpose-units**: born as
pre-specs from `issue-register`, driven end-to-end (brainstorm → spec → plan →
build → PR) by background daemons (`orchestrating-daemons`), tracked as nodes
in `doperpowers/issue-tracker/board.json`.

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
computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Epics (nodes with
children) are never dispatched; the sweep moves them automatically.

## Toolkit

Paths relative to this skill's `scripts/` directory. Use them — don't hand-edit
`board.json`.

| script | does |
|---|---|
| `board-register.sh <title> <category> [--state S] [--note N] [--parent T] [--blocked-by T,T] [--spawned-by T]` | add a node; prints `<id> <md-relpath>` — then YOU write that markdown (pre-spec) |
| `board-transition.sh <id> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes; runs the epic/unblock sweeps |
| `board-edge.sh <id> --block T \| --unblock T \| --parent T \| --orphan` | re-cut edges after birth (one op per call): add/cut a `blocked_by`, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric `relates_to` annotation — rendered by board-map, no effect on eligibility |
| `board-list.sh [state]` | board view; `ELIGIBLE` tag = dispatchable |
| `board-map.sh [--write]` | human telemetry. `--write` renders two caches of `board.json`: **`BOARD.html`** — an interactive, crossing-minimized layered-DAG (pan/zoom, click a node for its detail, filter by state, collapse epics), the primary view, opened in a browser; and **`BOARD.md`** — a minimal node/state table, the GitHub-inline fallback. No argument prints the table to stdout. Both auto-refresh on every register/transition |
| `board-show.sh <id>` | node + md path + bound daemon |
| `board-bind.sh <uuid> <id>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: unapplied proposals, orphaned tickets, dispatchables |
| `board-link.sh <id> --gh N` \| `--backfill` | link a ticket to its GitHub issue; `--backfill` populates `gh` from the `(GH#NN)` marker in every title, once |
| `board-meta.sh <id> [--gh N] [--add-label L] [--rm-label L]` | writer for the `gh` link and free `labels[]` (atomic, re-renders) |
| `board-gh-plan.sh [--gh-json FILE]` | **read-only**: emit the board↔GitHub reconcile plan (state facet) as JSON |
| `board-gh-apply.sh [--plan FILE] [--dry-run] [--no-github]` | apply a plan's (stdin or `--plan`) `auto` non-conflict actions (board via scripts, GitHub via `gh`) and refresh `.sync-state.json` from the plan |

## GitHub sync (board-sync)

`board-sync` (a subagent; `/board-sync`) keeps the board and GitHub issues in
step. It links tickets to issues (`gh` node field; `board-link.sh --backfill`
migrates existing boards from the `(GH#NN)` title marker), then reconciles state
both ways against a `.sync-state.json` watermark: board `done`↔closed/completed,
`wontfix`↔closed/not_planned, everything else↔open. Unambiguous changes apply
automatically; **anything it can't safely auto-apply — divergent state (both
sides moved), a missing linked issue, or an ambiguous single-side mapping (e.g. a
reopened issue, or a GitHub-completed ticket the board never started) — is written
to `SYNC-REPORT.md`, never auto-resolved**. Cron runs are conservative — state
only, no counterpart creation. Run from the main checkout with `gh` authenticated.

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
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <id> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- `board.json` corrupted → restore from git history.
- Bulk board scripts (register, board-gh sync, reconcile) refuse to run from a worktree — run those from the main checkout. The single-ticket `board-transition.sh` is the one exception: the worker that owns a ticket may move its OWN ticket (in-progress / in-review) from its isolated worktree, committing `board.json` on its branch. Merges and `board-gh-sync` reconcile the rest.
