---
name: issue-tracker
description: Use when working with the board (a repo's ticket backlog, in GitHub issues or on an Arkho board service) — registering or searching tickets, taking a ticket your human partner named, recording its progress, or closing it out.
---

# Issue Tracker

The board is the state of future work: a backlog. A ticket is registered
when work is deferred out of a session or named for later — a scope-out, a
review's residue, something your human partner wants kept — and it waits
there until they say which tickets go. The record of work done is the
commits and the PRs, not the board; work that will be built now needs no
ticket.

Taking a ticket is not a dispatch. The session your human partner names it
to runs it like any other work, through the attended workflow: design where
it needs design (doperpowers:brainstorming, doperpowers:execspec), a
plan-executor or subagents to build, doperpowers:review-code to review, the
session to merge. The ticket records where the work stands.

**Automatic dispatch is dormant** (the owner's ruling of 2026-10-18,
[docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md](../../docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md)).
Nothing starts a session from the board: no sweep, no event trigger, no
Architect, Executor, spike or review stand-in seat, no QA agent owned by a
seat. Their protocols and scripts are still in this skill (Dormant
machinery, at the end) and describe nothing that runs. A ticket body,
comment or note that expects a worker to pick the ticket up is stale.

GitHub Issues or the board service is the single source of truth; every
script talks to it directly and may run from any checkout.
`doperpowers/issue-tracker/` in the consumer repo is only a gitignored
render cache for `board-map.sh`.

## The Board Write Hard Gate (put this in the consumer CLAUDE.md)

> Board Write Hard Gate: issue creation and every state/edge change MUST go
> through the issue-tracker scripts — never raw `gh issue edit` for
> `status:*` labels or sub-issue/dependency edges. At registration, category +
> status + parent + blocked-by are each either set or consciously N/A —
> silence is not N/A.

The scripts are the schema: they enforce the state machine, mandatory notes,
PR gates, and cycle/deadlock checks that GitHub's API will not.
`board-lint.sh` catches what slips past.

## Who writes the board

| writer | writes |
|---|---|
| **The session working a ticket** | that ticket's open states as the work moves (Taking a ticket, below), its comments, and new tickets for what it defers |
| **Your human partner** | everything else — priorities, park answers, `wontfix`, edge re-cuts, closes of non-PR work |
| **Board bookkeeping** (the scripts' own sweeps) | epic states nobody claims by hand: an epic pulled in-flight by its first active child, and returned to `ready-for-architect` when its last child lands (`[board-epic]` comments) |

## Categories

`bug` | `enhancement` | `spike` | `env-issue`. The first two are GitHub's
own labels; the board manages the other two. `spike` is exploration — its
deliverable is a findings comment, never a merge. `env-issue` is
environmental friction someone hit and routed around (missing tool in the
image, flaky registry, broken fixture), filed as its own ticket so the
report survives the session that found it.

An `env-issue` defaults to `needs-human` — its birth rule is INVERTED
from every other category's. Elsewhere unsure means
`ready-for-implementer`; here unsure means the human, because friction an
authorized agent could have cleared would usually already be cleared.
Registration on that default path REQUIRES `--note` naming the
intervention being asked for (register refuses without it). An explicit
`--state` is the registrar's claim that a concrete repair path exists for
an agent to execute. Filing is fire-and-continue: the reporter files it
and goes on with its own work.

## State vocabulary

The vocabulary was cut for the dispatch lanes, and the scripts and the
board service still enforce it, so an attended session walks the same
edges:

    ready-for-implementer → in-progress → in-review → done
    ready-for-architect → in-design → in-progress → in-review → done

(`ready-for-implementer` keeps its legacy spelling because live boards
depend on it.)

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-architect` | open + `status:ready-for-architect` | backlog: the work needs design before it is built. On an EPIC, its recomposition is due (Epics below) | — |
| `in-design` | open + `status:in-design` | a session is designing it. Exits to `in-progress` by the **build edge**, which pins what will be built: `--plan <path>@<sha>` (a spec pushed to the remote) or `--plan pre-spec` (the body is enough); to `ready-for-implementer` with the same pin when the build is left for later; or to a park. On an epic it also exits to `done`/`in-review` — the recomposition verdict; on a leaf those edges are refused | optional |
| `ready-for-implementer` | open + `status:ready-for-implementer` | backlog: buildable from its body, or from the plan pinned to it (`plan:`). The DEFAULT birth state | — |
| `in-progress` | open + `status:in-progress` | a session is building it | optional |
| `needs-human` | open + `status:needs-human` | parked for your human partner **as themselves**: a decision only they can make, or a real-world input only they hold (credentials, auth, production data) | **required** |
| `needs-info` | open + `status:needs-info` | rare: the spec is unambiguous but lacks depth, or core decisions need substantial research first | **required** |
| `interactive-preferred` | open + `status:interactive-preferred` | rare: the work's CORE needs live steering in a doperpowers:brainstorming session, not a question list | **required** |
| `in-review` | open + `status:in-review` | PR open (`--pr` required). A same-state transition carrying `--plan <path>@<sha>` **re-pins** a plan the review re-cut (without `--plan` the self-edge is refused as a no-op); `in-progress` with a repaired pin is the **rebuild** | PR link (epic: closure package) |
| `done` | **closed — completed** | landed — normally by the merge itself; a manual flip for non-PR work, after verifying it landed | optional |
| `wontfix` | **closed — not planned** | rejected | **required** |
| `deferred` | open + `status:deferred` | tracked, not now | optional |

**Park discriminant — who unparks it?** A session that needs your human
partner asks them in the conversation. A park is for a ticket left waiting
after the session moves on, and its state says who unparks it: a decision
or a real-world input only the human holds → `needs-human`, the note a
crisp question list, each with a recommended answer; knowledge work anyone
could do → `needs-info`, the note says what is missing; ongoing steering
of the work's core → `interactive-preferred` — but any ENUMERABLE set of
open decisions, however many, is `needs-human`. Missing design an agent
can author is not a park: it is `ready-for-architect`. The board counts
escalation edges into it: a second traversal of the same edge on one
ticket converts to `needs-human` mechanically.

Waiting on other tickets is NOT a park: dependencies are edges
(`board-edge.sh <n> --block <blocker>`), and the board re-surfaces the
ticket when its blockers land, which no park state does. `in-progress →
ready-for-implementer` is the dependency yield and is refused `not-blocked`
unless an unfinished blocker is already on record, so cut the edge first.
A blocker that goes unworked and silent past the dependency threshold, or
a ring of blockers that can never resolve, parks the waiting ticket
`needs-human` with the chain in its note. (`blocked` was retired in v8;
lint names any legacy label with the migration FIX.)

Exactly one `status:*` label on every open issue; terminal states are the
close reason (no label). An issue outside this scheme is `untracked` (no
label) or `conflict` (2+ labels) — lint FAILs it; `board-transition.sh`
repairs it (any open state is reachable from either).

Ticket dependencies are **edges** (native GitHub dependencies), never states —
eligibility is computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Notes
land twice: the current note in the issue's `board:meta` body block, the audit
trail as `[board]` comments.

**Epics** (issues with sub-issues) ride their children: the first active
child pulls the parent in-flight (`in-design` from `ready-for-architect`,
`in-progress` from `ready-for-implementer` or from a `needs-info` release),
and it stays there while they run. The other parks are never pulled. An
epic whose children are all terminal is never closed by bookkeeping: it
RETURNS to `ready-for-architect` (`recomposition-due`), and whoever holds
the parent's composite verifies the parent's own acceptance and closes it
— directly for a non-code parent, via `in-review` with a closure package
for a code-bearing one (doperpowers:decomposing). Bookkeeping writes on
epics post `[board-epic]` comments, a marker the convergence counter never
reads.

## API binding

A repo's board lives either in its GitHub issues (**gh binding**, the default)
or on an Arkho board service (**api binding**). `.doperpowers/board.json` says
which — it is committed, so every checkout and every linked worktree of the
repo resolves the same board (a linked worktree checked out at a head that
predates the file resolves the binding from its main checkout):

```json
{ "binding": "api", "url": "https://…", "repo": "doperpowers" }
```

`repo` is the name the **board service** knows this repository by. One service
serves several repositories out of one ticket namespace, and a request that
names none is not repo-neutral — the server picks: its founding repo on a
write, *every* repo on a list read. So the key is required. An api binding
without it dies before any verb runs rather than falling back to the server's
pick or to the checkout's directory name; neither is this repo's identity on
the board, and a wrong one is silent (a register run from a neighbouring
checkout filed its ticket here, and a list from there printed this board's
tickets as its own).

`$BOARD_REPO` overrides the file, and means a different thing per binding: on
the **api** binding it is the board's repo key (a bare name); on the **gh**
binding it is `owner/name`, which `_lib.sh` resolves from the checkout when
unset. It is the value the Toolkit table below calls the target repo.

Credentials never live in the repo. The client reads
`~/.arkho-board/<main-checkout-dirname>.env` (the *main* checkout's directory
name, so a worktree reads the same file), with two lines:

```
BOARD_AUTOMATION_TOKEN=…    # the dormant fleet: dispatch, claims, sweeps
BOARD_HUMAN_TOKEN=…         # your human partner: register, transition, answer
```

A session's writes go out as your human partner. (A dispatched worker spoke
as its claimed run, resolved from its sminos seat record; with dispatch
dormant there are no runs, and a verb that still finds one says so on
stderr.)

Every read narrows to the bound repo, and so does every write. The two **browse**
verbs — `board-list.sh` and `board-search.sh` — take `--all-repos` to widen back
to the whole service. A widened listing says so in its header line and carries
the repo as a second column (`#<id> <repo> <state> <priority> <title>`): ticket
numbers are repo-local, so `#12` from another board is a different ticket here,
and every id-targeted verb takes a bare number.

## Toolkit

Paths relative to this skill's `scripts/` directory. Ticket ids are issue
numbers (`42` or `#42`). Target repo = `$BOARD_REPO` — `owner/name` on the gh
binding (or the checkout's own repo), the board's repo key on the api binding
(see API binding above).

| script | does |
|---|---|
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; category is `bug`\|`enhancement`\|`spike`\|`env-issue` (Categories above owns their semantics — an `env-issue` with no explicit `--state` is born `needs-human` and is REFUSED without `--note`); priority (`P0`…`P3`, P0 = drop everything) is REQUIRED and becomes the managed `priority:*` label; author the body at register time via `--body-file` (The ticket body below — a skeleton birth is refused for a backlog state and demoted to `needs-info` otherwise); prints `<number> <url>` |
| `board-body.sh <n> --body-file F` | rewrite a ticket's statement of work (`F` may be `-` for stdin; an empty file clears it). The gh route splices the trailing `board:meta` block back byte-for-byte, which bare `gh issue edit` clobbers |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL] [--plan PATH@SHA\|pre-spec]` | apply a state change; enforces legality + notes + the in-review PR gate; `--plan` rides only the pin-minting edges (out of `in-design`, the rebuild, the re-pin), and a real pin is verified on the remote before anything is written; runs the epic/unblock sweeps; repairs untracked/conflict issues. Re-run `<n> done` on a merge-auto-closed ticket to **finalize** (strip the stale label + run the sweeps; idempotent). A ticket still bound to a worker session is fenced to that session — overrule a stale binding with `BOARD_OWNER_OVERRIDE="<why>"` |
| `board-comment.sh <n> <text>` / `<n> --kind K [--text T] [--json P]` | append a comment-family event. `K` is `comment`\|`parent-impact`\|`closure-package`\|`parent-impact-consumed`\|`review-trail` — the last records the review (reviewer, range, verdict), which the API board's evidence-gated `in-review → done` requires. gh renders a typed kind as a `[K] …` marker comment; put `--` ahead of comment text that starts with a dash |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-priority.sh <n> <P0..P3>` | re-prioritize: swap the `priority:*` label (repairs a double label); prints `#n: P2 → P0` |
| `board-surface.sh <n> --add NAME \| --remove NAME` | add/remove a `surface:*` label (Surfaces, under Dormant machinery) |
| `board-list.sh [--all-repos] [state]` | the backlog in priority order (P0 rows first, unprioritized last); `CLOSE?` tag = close candidate (Edge cases). API binding: rows in the server's own order (the header says so), and `--all-repos` widens past the bound repo |
| `board-search.sh [--states s1,s2] [--bodies] [--all-repos] [--] <query>` | full-text search for the pre-registration dedup / prior-art check (The ticket body). API binding: the board's `?q=` websearch (unquoted terms AND, `or`, `-` negation, quoted phrases) across ALL states; `--states` narrows; `--bodies` prints the first ≤20 hits' bodies; a query that leads with `-` rides behind `--`. gh binding: `gh issue list --state all --limit 200 -R <repo> --search` (`--states` refused; gh search already matches bodies) |
| `board-show.sh <n>` | one ticket in full: header row, the statement of work, then the timeline (gh binding: node JSON + issue URL) |
| `board-answer.sh <n> <answers> --to <state>` | API binding: answer a park and name where the ticket goes next — the server records the answers and moves it (gh binding: comment the answers, then `board-transition.sh` out of the park) |
| `board-map.sh [--write\|--serve\|--stop]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered DAG with a kanban toggle) and **`BOARD.md`** into the gitignored render dir; `--serve` also serves it on 127.0.0.1 (per-repo port; `$BOARD_PORT` overrides) with hot reload; `--stop` kills the server. No argument prints the table |
| `board-reconcile.sh` | read-only catch-up: parked tickets with their notes, orphaned in-flight tickets, the backlog, then a lint pass |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required, no dependency cycles, at most one priority label (missing priority is a WARN), retired labels named with their migration FIX; WARNs close candidates. `FAIL … FIX: …` lines, exit 1 |
| `board-migrate-gh.sh [--board FILE] [--apply]` | one-shot v6→v7 migration of a legacy `board.json` into GitHub (dry-run by default) |

## Taking a ticket

Your human partner names the tickets that go ("#92 진행", "do 81 and 83").
For each one:

1. `board-show.sh <n>` — the body is the statement of work; the comments
   carry what was learned since.
2. Move it as the work moves. A `ready-for-architect` ticket goes
   `in-design` while you design it, then crosses the build edge to
   `in-progress` with its pin; a `ready-for-implementer` ticket goes
   straight to `in-progress --branch <branch>`. `in-review --pr <url>` when
   the PR opens.
3. Run the work as you would without a ticket. The ticket changes nothing
   about how it is designed, built or reviewed.
4. Close it. On the gh binding the PR body's `Closes #<n>` closes it at the
   merge; then `board-transition.sh <n> done` finalizes. On the api binding
   a ticket number names no GitHub issue, so the PR carries no
   `Closes`/`Fixes` line: post the review as a `review-trail` comment, then
   `done` with the merge commit in the note.
5. What the work left behind goes on the board before you report it done
   (Scope-outs become tickets).

A ticket set down unfinished goes to `deferred` with a note on where it
stands, to `ready-for-architect` when its design is what changed, or to a
park when it waits on your human partner.

## The ticket body (pre-spec)

Before registering, run the pre-registration search — and search by
SEAM: the identifiers your ticket touches (file paths, function/RPC
names, table names). Title-keyword search may not be enough — different
authors word the same work differently. Query each seam identifier with
`board-search.sh "<function-or-file-name>"`. Where a title is not enough
to judge a hit, `--bodies` prints the first ≤20 hits' statements of work.
Then triage the hits:

- **Same defect or scope** → comment your evidence on the existing
  ticket instead of registering a duplicate.
- **Same seam, different defect** → register, and in the same breath
  `board-relate.sh` your new ticket to every open ticket on that seam.
- **Cluster tripwire**: if your registration would put a THIRD
  non-terminal ticket onto the same function or contract body, that
  seam has outgrown patch-wise work — separate rewrites of one body
  revert each other silently (different files, zero git conflicts).
  Parked tickets count; only `deferred` and closed tickets are out of
  the race. Register your finding, then raise consolidation: a ticket
  born `ready-for-architect` that names every member and owns the
  unified contract, with the members related. Each member is then
  re-cut as a slice of the unified contract or closed with a reason.

Whoever registers a ticket authors its body AT REGISTER TIME — write the
sections to a temp file and pass `--body-file` in the same step. The
registrar is the person who knows the most about the work at that moment;
"register now, fill in later" loses exactly that context (and register
refuses or demotes a skeleton anyway). Sections: Problem & intent /
Constraints / Success criteria / Open questions / Decision log — plus, on
a decomposed parent, Roadmap (the one sanctioned form of "ticket that
doesn't exist yet"). Write it for a reader with no context: the session
that takes it may be weeks away. A terminal outcome comment updates the
record at close. The trailing `<!-- board:meta … -->` block is
script-owned (spawned-by / relates-to / branch / pr / note) — edit around
it, never inside it. The meta block is an HTML comment, INVISIBLE on the
rendered issue page — `--note` is a one-line status summary, never the
spec's home.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, a
decomposition, a review, or a PR's residue — is registered on the board THE
MOMENT the deferral is decided, by whoever decided it, with its lineage as
edges:

- `--parent <epic>` — decomposition children (they ARE the parent's content,
  sliced) and work that belongs to an existing epic
- `--spawned-by <origin>` — scope-outs and follow-ups discovered during work
- `--blocked-by <numbers>` — what must land first

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket's Decision log
records *why* it was cut, so nobody re-litigates it later.

A PR that addresses its ticket but leaves work behind still closes the
ticket (done means the PR landed, not that every idea it surfaced died).
The residue is registered (`--spawned-by <n>`) before the work is reported
done — a follow-up not registered does not exist. A few-line residual
inside the PR's own diff is in-scope polish the PR absorbs, not residue.

## Remote board (hosted)

`board-map.sh --serve` renders locally on demand. For an always-current hosted
view, a workflow re-renders BOARD.html on every issue event (plus a cron safety
net — sub-issue/dependency edits fire no webhook) and deploys it. Hosted pages
hot-reload the same way served local tabs do. Two templates, pick by repo
visibility:

- **Public repo → GitHub Pages.** Copy `references/board-pages.yml` into
  `.github/workflows/` and set Pages → Source to "GitHub Actions". Note: a
  Pages site is *public* even for a private repo on non-Enterprise plans —
  and on Free/most org plans, private-repo Pages is unavailable entirely.
- **Private repo → Cloudflare Pages + Access.** Copy
  `references/board-cloudflare-pages.yml`: a private, team-authenticated URL.
  Read the template header: set up Access *before* the first deploy, or there
  is a window where issue titles are public.

## Edge cases

- A merged PR auto-closed its ticket (`Closes #N`) → the board already reads
  it `done`; the stale status label and unswept epics are what's left. Run
  `board-transition.sh <n> done` to finalize — reconcile's lint pass names
  these tickets.
- A merged PR did NOT close its ticket → the ticket is a **close
  candidate**: lint WARNs it, `board-list.sh` tags it `CLOSE?`, and the
  kanban view pulls it into a close-candidate column. Verify it landed and
  close it (`done`, or `wontfix "superseded by PR"`), or re-scope it; it is
  never auto-closed.
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <n> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- An issue labeled by hand (or by external automation) lands `untracked` /
  `conflict` → lint names it; `board-transition.sh` repairs it. A legacy
  `status:blocked` label is a special case of conflict — lint's FIX line
  carries the `needs-human` migration.
- Consumer label automation that already speaks `status:*` (e.g. assign →
  `status:in-progress`) is a legitimate board writer — same store, same
  vocabulary, no sync.

## Dormant machinery

Kept in place and tested, armed nowhere. Read it to understand old tickets
and comments, or as input to a redesign — if board-driven spawning returns,
it will most likely run the attended workflow above on a trigger rather
than wake this doctrine as written (the ruling).

- **Dispatch.** `scripts/execute-dispatch.sh` (the Architect/Executor/spike
  dispatcher), `scripts/review-dispatch.sh` (review seats for PRs),
  `scripts/board-sweep.sh` with `_sweep_api.sh` (the unattended tick:
  recovery, cancel, dispatch, land, relay), `scripts/board-bind.sh` (binds
  a worker session to its ticket), and `board-answer.sh <n> <answers>`
  without `--to` (relays answers to a bound worker and resumes it).
  Operator manuals: `references/execution-loop.md`,
  `references/sweep-setup.md`, `references/runner-setup.md`; event
  triggers: `references/issue-dispatch.yml`,
  `references/pr-review-dispatch.yml`.
- **Worker doctrine.** `references/worker-bootstrap.md`,
  `architect-worker-protocol.md`, `implement-worker-protocol.md`,
  `implement-decompose.md`, `spike-worker-protocol.md`, `ticket-gate.md`.
- **The seats' review loop.** `agents/qa-loop.md`,
  `references/review-loop.md`, `review-standin-protocol.md`,
  `review-standin-bootstrap.md`, `wave-board.md`.
- **Surfaces.** A consumer repo can declare contested code seams in
  `.doperpowers/surfaces.md` (read from the default branch); the board
  carries them as the closed `surface:<name>` label vocabulary (lint FAILs
  a label with no entry). Labels still arrive at registration and on entry
  to a backlog state; what they bought — at most one implement worker per
  surface, and the sweep registering a consolidation ticket when three
  pile onto one — ran in the dormant dispatcher. The cluster tripwire
  under The ticket body is the manual form that still applies.
