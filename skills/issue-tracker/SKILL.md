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
write only their OWN ticket's open states (self-descriptions and
escalations); terminal states are never theirs — `done` arrives via the PR
merge itself, `wontfix` and cross-ticket changes reach you as *proposal
blocks* you judge. All writes go through the scripts (the Hard Gate below).

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
| **Worker** (daemon, one ticket each) | only its OWN ticket's OPEN states, via `board-transition.sh` | reads its issue; escalates via its ticket's state + turn-end message; proposes anything else |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path.

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-agent` | open + `status:ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | open + `status:in-progress` | a daemon is driving it (an epic stays here while children run) | optional |
| `blocked` | open + `status:blocked` | non-ticket blockage: credentials / auth / human hand | **required** |
| `needs-info` | open + `status:needs-info` | waiting on knowledge: research or a human taste/product decision | **required** |
| `in-review` | open + `status:in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `done` | **closed — completed** | landed — normally arrives by the merge itself (PR body `Closes #N` auto-closes); manual flip for non-PR work only, verify it landed first | optional |
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
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; priority (`P0`…`P3`, P0 = drop everything) is REQUIRED and becomes the managed `priority:*` label; prints `<number> <url>` — then YOU flesh out the pre-spec body (`gh issue edit <n> --body-file …`) |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes + the in-review PR gate; runs the epic/unblock sweeps; repairs untracked/conflict issues. Re-run `<n> done` on a merge-auto-closed ticket to **finalize** (strip the stale label + run the sweeps; idempotent) |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-priority.sh <n> <P0..P3>` | re-prioritize: swap the `priority:*` label (repairs a double label); prints `#n: P2 → P0` |
| `board-list.sh [state]` | board view in dispatch order (P0 rows first, unprioritized last); `ELIGIBLE` tag = dispatchable, `CLOSE?` tag = close candidate (see The dispatch loop) |
| `board-map.sh [--write\|--serve\|--stop]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered-DAG: pan/zoom, node detail, state filter, epic collapse — plus a kanban view toggle) and **`BOARD.md`** (table) into the gitignored render dir. `--serve` additionally serves the render dir on 127.0.0.1 (per-repo port; `$BOARD_PORT` overrides) and opens the board over http — served tabs **hot-reload**: every later render (explicit `--write`, or the automatic one each mutating script fires while the server is up) appears without a manual refresh. `--stop` kills the server. No argument prints the table. Prefer `--serve` when a human will keep the board open |
| `board-show.sh <n>` | node + issue URL + bound daemon |
| `board-bind.sh <uuid> <n>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: unapplied proposals, orphaned tickets, dispatchables, then a lint pass |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required, no dependency cycles, at most one priority label (missing priority is a WARN — backfill legacy tickets with `board-priority.sh`). Also WARNs close candidates (below). `FAIL … FIX: …` lines, exit 1 |
| `board-migrate-gh.sh [--board FILE] [--apply]` | one-shot v6→v7 migration: push a legacy `board.json` into GitHub (dry-run by default) |

## Remote board (hosted)

`board-map.sh --serve` renders locally on demand. For an always-current hosted
view, a workflow re-renders BOARD.html on every issue event (plus a cron safety
net — sub-issue/dependency edits fire no webhook) and deploys it. Hosted pages
hot-reload the same way served local tabs do (the page polls its own caching
headers), so a browser left open tracks each redeploy. Two templates,
pick by repo visibility:

- **Public repo → GitHub Pages.** Copy `references/board-pages.yml` into
  `.github/workflows/` and set Pages → Source to "GitHub Actions". Zero external
  accounts. Note: a Pages site is *public* even for a private repo on
  non-Enterprise plans — and on Free/most org plans, private-repo Pages is
  unavailable entirely.
- **Private repo → Cloudflare Pages + Access.** Copy
  `references/board-cloudflare-pages.yml`. It deploys to Cloudflare Pages behind
  Cloudflare Access, giving a **private, team-authenticated URL** (the only way
  to host a private board below GitHub Enterprise). Read the template header:
  set up Access *before* the first deploy, or there is a window where issue
  titles are public.

## The dispatch loop

1. `board-list.sh` → pick the TOP `ELIGIBLE` ticket — rows already print in
   dispatch order (P0 before P1 before …; unprioritized last). A row tagged
   `CLOSE?` is a **close candidate**: every linked PR merged/closed (≥1
   merged) yet the issue is open — usually a PR that skipped `Closes #N`.
   Triage it before spawning anything: if the work landed, walk it to `done`
   (or `wontfix "superseded by PR"`); if work genuinely remains, dispatch as
   normal. Derived from GitHub PR state on every snapshot — never a label,
   never auto-closed.
2. Build a **self-contained spawn prompt**: the full issue body (`gh issue
   view <n>`) + the Worker Protocol block below.
3. `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>` (from
   `orchestrating-daemons` — always a worktree; workers write code).
4. `board-bind.sh <uuid> <n>` then `board-transition.sh <n> in-progress`.
5. When a daemon's turn ends, judge it (per `orchestrating-daemons`: answer /
   queue for the human / wake the human). Workers move their OWN ticket's
   open states themselves — what lands on you is their *questions*
   (blocked/needs-info notes), wontfix suggestions, and cross-ticket
   proposals; apply or refuse those with `board-transition.sh`.
6. `done` arrives by landing, not by claim: the worker's PR body says
   `Closes #<n>`, so the merge itself auto-closes the ticket — even a PR
   that leaves residual work behind closes it (the residue gets new tickets,
   not a reopened old one). Then finalize: `board-transition.sh <n> done`
   strips the stale in-review label and runs the epic/unblock sweeps (lint's
   FIX line says the same); register each item of the worker's FOLLOW-UPS
   list (`board-register.sh … --spawned-by <n>` — judging one down is fine,
   but the judgment is recorded, never the item silently dropped); append an
   outcome comment naming what landed and the follow-up tickets it spawned.
   A manual `done` flip remains for non-PR work; verify it landed first.

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
guess and do NOT proceed. BRAINSTORM IT: run doperpowers:brainstorming, move
your ticket to needs-info with the question as the note, and END YOUR TURN
stating it crisply; resume once you have the decision. Autonomy is earned
only where the brief is genuinely unambiguous — everywhere else, ask.

Your ticket's OPEN states are yours to write — your OWN ticket only, always
via the issue-tracker scripts (never raw gh): board-transition.sh <N>
in-progress when you start; in-review with --pr when your PR opens;
blocked / needs-info (note required) the moment you hit an escalation — set
the state yourself, then END YOUR TURN with the question stated crisply.

Opening your PR closes out your scope: that turn-end message MUST carry a
FOLLOW-UPS section — every piece of residual work the PR leaves behind
(non-blocking cleanups, larger work you discovered, success criteria the PR
only partially meets), one line each with why it was cut — or the literal
line "FOLLOW-UPS: none". The orchestrator registers these as new tickets at
finalize; a follow-up not on this list does not exist. The JSON proposal
block below is for state changes, not follow-ups.

You NEVER write a terminal state. done is not claimed, it is landed: your PR
body MUST say "Closes #<N>" so the merge itself closes the ticket. wontfix is
the orchestrator's call. To suggest either — or any change to ANOTHER
ticket — end your turn with a single-line JSON proposal block:
{"ticket":"<N>","from":"<current>","to":"<proposed>","reason":"…","evidence":"…"}

Escalation discriminant: waiting on an action/precondition (credentials,
access, another ticket's work) → blocked. Waiting on knowledge or a human
taste/product decision → needs-info. Never guess above your scope, never
expand it.
```

## The ticket body (pre-spec)

The issue body — seeded by register, fleshed out by YOU (register time, plus a
terminal outcome comment). Sections: Problem & intent / Constraints / Success
criteria / Open questions / Decision log. The trailing `<!-- board:meta … -->`
block is script-owned (spawned-by / relates-to / branch / pr / note) — edit
around it, never inside it.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, an
issue-register session, a worker's design phase, or a worker's FOLLOW-UPS
list at PR time — is registered on the board THE MOMENT the deferral is
decided, with its lineage as edges:

- `--spawned-by <origin>` — the ticket whose design session produced the cut
- `--blocked-by <numbers>` — what must land first (often the origin ticket
  itself, and/or the moving interface that forced the deferral)
- `--parent <epic>` — when the work belongs to an existing epic

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket's Decision log
records *why* it was cut, so nobody re-litigates it later.

PR landing is a deferral point like any other. A PR that addresses its
ticket but leaves work behind — non-blocking follow-ups, discovered larger
work, success criteria only partially met — still closes the ticket
(`Closes #N` stays in the body: done means the PR landed, not that every
idea it surfaced died). The residue rides the worker's FOLLOW-UPS list into
new tickets, `--spawned-by <n>`, registered at finalize before the outcome
comment — and the outcome comment names them, so the closed ticket points
at where its remainder went.

## Edge cases

- A merged PR auto-closed its ticket (`Closes #N`) → the board already reads
  it `done`; the stale status label and unswept epics are what's left. Run
  `board-transition.sh <n> done` to finalize — reconcile's lint pass names
  these tickets.
- A merged PR did NOT close its ticket (no `Closes #N`) → the ticket becomes
  a **close candidate**: lint WARNs it, `board-list.sh` tags it `CLOSE?`, and
  the kanban view pulls it into a close-candidate column (in-progress /
  in-review tickets stay put — a merged part-1 PR mid-flight is normal, they
  only carry the mark). Human/orchestrator verifies and closes; never
  auto-closed.
- `orphaned` in reconcile → the daemon died: respawn, re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <n> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- An issue labeled by hand (or by external automation) lands `untracked` /
  `conflict` → lint names it; `board-transition.sh` repairs it.
- Consumer label automation that already speaks `status:*` (e.g. assign →
  `status:in-progress`) is a legitimate board writer — same store, same
  vocabulary, no sync.
