---
name: issue-tracker
description: What the board is and how it behaves — a repository's ticket backlog, in GitHub issues or on an Arkho board service, with its states, its commands, what they refuse and its conventions. For registering or searching tickets, taking a ticket, recording its progress, or closing it out.
---

# Issue Tracker

The board is a repository's backlog: the state of future work. A ticket
holds work deferred out of a session or named for later, and waits until a
session takes it. Work done is recorded by commits and PRs; work that will
be built now needs no ticket.

Taking a ticket is not a dispatch. Nothing starts a session from the board:
automatic dispatch is dormant by the owner's ruling of 2026-10-18
([the spec](../../docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md)).
A session takes a ticket because your human partner named it, or on its own
initiative when the ticket is ready to build, and runs the work as it would
without a ticket; the ticket records where the work stands. A body, comment
or note that expects a worker to pick the ticket up is stale.

## Where it lives

A repo's board is its GitHub issues (the **gh binding**, the default) or a
board on an Arkho board service (the **api binding**). The committed
`.doperpowers/board.json` says which, so every checkout and linked worktree
resolves the same board:

```json
{ "binding": "gh", "repo": "owner/name" }
{ "binding": "api", "url": "https://…", "repo": "doperpowers" }
```

- **gh `repo`** is optional. Without it the scripts take what `gh repo view`
  answers, which in a fork with an `upstream` remote and no
  `gh repo set-default` is the upstream project.
- **api `repo`** is the name the service knows this repository by, and the
  scripts die without it. One service keeps several repositories in one
  ticket namespace, and a request naming none gets the server's pick (its
  founding repo on a write, every repo on a read), so a wrong key files and
  lists another board's tickets without an error.
- `$BOARD_REPO` overrides the file's `repo`: `owner/name` on gh, the bare
  key on api.
- **api credentials** are in `~/.arkho-board/<main-checkout-dirname>.env`
  (a worktree reads its main checkout's file): `BOARD_HUMAN_TOKEN`, under
  which a session's writes go out as your human partner, and
  `BOARD_AUTOMATION_TOKEN`, the dormant fleet's.
- Reads and writes narrow to the bound repo. `board-list.sh` and
  `board-search.sh` take `--all-repos`, which adds a repo column: ticket
  numbers are repo-local, so `#12` from another board is another ticket.

The store is the single source of truth and the scripts reach it from any
checkout; `doperpowers/issue-tracker/` in a consumer repo is only
`board-map.sh`'s gitignored render cache.

The scripts keep the schema GitHub's API will not: one `status:*` label on
an open issue, legal edges, required notes, the script-owned meta block, no
dependency cycles. A raw `gh issue edit` of a label or a body bypasses
them. `board-lint.sh` reports what results (`untracked`, no status label;
`conflict`, two or more), and a `board-transition.sh` to any open state
repairs it.

## States

    ready-for-implementer → in-progress → in-review → done
    ready-for-architect → in-design → in-progress → in-review → done

The vocabulary was cut for the dispatch lanes, and the scripts and the
board service still enforce it. On the gh binding an open state is the
label `status:<state>` on an open issue; `done` is a close as completed and
`wontfix` a close as not planned, with no label.

| state | meaning | note |
|---|---|---|
| `ready-for-architect` | backlog: needs design before it is built. On an epic, its recomposition is due | |
| `in-design` | a session is designing it | |
| `ready-for-implementer` | backlog: buildable from its body, or from the plan pinned to it. The default birth state (a legacy spelling live boards depend on) | |
| `in-progress` | a session is building it | |
| `in-review` | its PR is open | |
| `needs-human` | parked for your human partner as themselves: a decision only they can make, or an input only they hold (credentials, auth, production data) | required: the questions, each with a recommended answer |
| `needs-info` | parked on knowledge work anyone could do: the spec lacks depth, or research comes first | required: what is missing |
| `interactive-preferred` | parked because the work's core needs live steering in a design session. Decisions that can be listed, however many, are `needs-human` | required |
| `deferred` | tracked, not now | |
| `done` | landed: by the merge, or by hand for work with no PR | |
| `wontfix` | rejected | required |

A park is for a ticket left waiting after the session moves on; a session
that needs your human partner now asks them in the conversation. Design an
agent can write is not a park: that ticket is `ready-for-architect`.

What `board-transition.sh` requires beyond a legal edge:

- **Into `in-review`**: `--pr <url>`.
- **The build edge, `in-design → in-progress`**: a note, `--branch`, and
  the pin of what will be built: `--plan <path>@<sha>` (a spec pushed on
  that branch, verified on the remote) or `--plan pre-spec` (the body is
  the plan). The gh binding refuses the edge without all three, and
  refuses it to an epic.
- **Out of `in-design` otherwise**: `ready-for-implementer` takes a note,
  and the pin when a design was written. No edge leads back to
  `ready-for-architect`; `deferred` does.
- **Back toward design**: `ready-for-implementer`, `in-progress` or
  `in-review` `→ ready-for-architect`, and `in-review → in-progress`, each
  take a note. On the gh binding a second traversal of the same one of
  these edges on a ticket lands in `needs-human` instead; a comment opening
  `[answers]` resets the count. The api board counts only a worker's
  traversals.
- **`in-progress → ready-for-implementer`** is the dependency yield alone:
  it takes a note and is refused `not-blocked` unless an unfinished blocker
  is already on record.
- **Into either backlog state**: refused while the body is still the
  registration skeleton.

**Waiting on other tickets is an edge, not a state**
(`board-edge.sh <n> --block <m>`): the board re-surfaces the ticket when
its blockers land, which no park state does. On the api binding the
service bounds the wait: a blocker unworked and silent past its threshold
(48 hours by default), or a ring of blockers that cannot resolve, parks
the waiting ticket `needs-human` with the chain in its note. On the gh
binding nothing watches (that pass lived in the dormant sweep):
`board-list.sh` tags the ticket `waiting:#<m>`, and `STUCK` once a blocker
is `wontfix`.

**Epics** (issues with sub-issues) are moved by bookkeeping, which posts
`[board-epic]` comments. The first active child pulls its parent in-flight:
`in-design` from `ready-for-architect`, `in-progress` from
`ready-for-implementer` or `needs-info`. The other parks are never pulled.
When the last child lands the epic is not closed: it returns to
`ready-for-architect`, a return the escalation count ignores, and whoever
takes it goes `in-design`, verifies the parent's own acceptance and closes
it (doperpowers:decomposing): `done` for a non-code parent; for a
code-bearing one, `board-comment.sh <n> --kind closure-package` and
`in-review` with the package's URL as `--pr`.

**Closing.** On the gh binding a PR body's `Closes #<n>` closes the ticket
at the merge and leaves a stale label and unswept epics;
`board-transition.sh <n> done` finalizes it (idempotent). A merged PR that
did not close its ticket makes it a close candidate (`CLOSE?` in the list,
a lint warning); nothing closes it automatically. On the api binding a
ticket number names no GitHub issue, so the PR carries no `Closes` line:
`in-review → done` needs a `review-trail` comment first, and the note
carries the merge commit.

## Categories

`bug` | `enhancement` | `spike` | `env-issue`. A `spike` is exploration: its
deliverable is a findings comment, not a merge. An `env-issue` is
environmental friction someone hit and routed around (a tool missing from
the image, a flaky registry, a broken fixture), filed so the report
outlives the session that found it. It defaults to `needs-human`, since
friction an agent could clear would usually be cleared already, and
register refuses that default without a `--note` naming the intervention
asked for. An explicit `--state` says an agent can repair it.

## Commands

In this skill's `scripts/`. A ticket id is its number (`42` or `#42`).

| script | does |
|---|---|
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | opens a ticket with its labels and edges and prints `<number> <url>`. Priority `P0`…`P3` (P0 = drop everything) is required. Without `--body-file` the body is a skeleton: refused for an explicit backlog `--state`, born `needs-info` otherwise |
| `board-body.sh <n> --body-file F` | rewrites the statement of work (`-` reads stdin; an empty file clears it), keeping the meta block that a bare `gh issue edit` clobbers |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL] [--plan PATH@SHA\|pre-spec]` | moves a ticket under the requirements in States, runs the epic bookkeeping, repairs an `untracked` or `conflict` issue; `<n> done` on an already closed ticket finalizes it |
| `board-comment.sh <n> <text>` / `<n> --kind K [--text T] [--json P]` | appends a comment. Kinds: `comment`, `parent-impact`, `closure-package`, `parent-impact-consumed`, `review-trail` (reviewer, range, verdict). gh renders a kind as a `[K] …` marker comment; `--` goes ahead of text that starts with a dash |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cuts one edge per call: a dependency, or the epic a ticket sits under. Rejects self-edges, cycles and ancestor-epic blockers |
| `board-relate.sh <a> <b> [--cut]` | a symmetric "relates" annotation, drawn on the map; no effect on eligibility |
| `board-priority.sh <n> <P0..P3>` | swaps the `priority:*` label |
| `board-surface.sh <n> --add NAME \| --remove NAME` | adds or removes a `surface:*` label (What may surprise you) |
| `board-list.sh [--all-repos] [state]` | the backlog in priority order (api: the server's order). Tags: `ELIGIBLE` (gh: no unfinished blocker holds the row; on api read `blocked_by` in `board-show.sh`), `waiting:#n`, `STUCK`, `CLOSE?` |
| `board-search.sh [--states s1,s2] [--bodies] [--all-repos] [--] <query>` | full-text search across all states. api: websearch syntax (terms AND, `or`, `-` negation, quoted phrases); `--states` narrows, `--bodies` prints the first ≤20 hits' bodies, a query that leads with `-` goes behind `--`. gh: `gh issue list --search` over 200 issues, bodies included; `--states` is refused |
| `board-show.sh <n>` | one ticket in full: header, statement of work, timeline |
| `board-answer.sh <n> <answers> --to <state>` | api only: records your human partner's answers to a `needs-human` park and moves the ticket to a queue, another park or a close (an in-flight `<state>` is refused when no worker is bound). On gh an answer is a comment opening `[answers]`, then a transition |
| `board-map.sh [--write\|--serve\|--stop]` | the board for your human partner to look at: `--write` renders `BOARD.html` and `BOARD.md` into the render cache, `--serve` also serves it on 127.0.0.1 with hot reload (`$BOARD_PORT`), no argument prints the table |
| `board-reconcile.sh` | read-only catch-up: parked tickets with their notes, orphaned in-flight tickets, the backlog, a lint pass |
| `board-lint.sh` | checks the schema over the live board; `FAIL … FIX: …` lines, exit 1 |

A hosted, always-current map is a workflow in the consumer repo:
`references/board-pages.yml` (GitHub Pages, which is public even for a
private repo below Enterprise) or `references/board-cloudflare-pages.yml`
(Cloudflare Pages behind Access). Each template's header carries its setup.

## What may surprise you

- **The first move is the claim, and on the gh binding it is visible, not
  exclusive.** That move is `in-progress --branch <branch>`, or `in-design`
  for a design. A ticket already taken refuses it:
  `#<n> is already in-progress` on gh,
  `refused: illegal-transition — in-progress → in-progress` on api. The api
  service checks and writes under the ticket's row lock, so of two claims
  the second is refused. The gh script reads the ticket, then rewrites its
  labels and branch with nothing to arbitrate: two claims seconds apart can
  both succeed, and the later branch stands. `board-show.sh <n>` after the
  claim shows whose branch the ticket records.
- **A surface can refuse the build edge** (gh). A repo may declare
  contested code seams in `.doperpowers/surfaces.md`; tickets get
  `surface:<name>` labels at registration and on entry to a backlog state,
  by matching identifiers, and lint fails a label the file does not
  declare. While another open leaf with the same label is `in-design`,
  `in-progress` or `in-review`, the edge is refused:
  `surface <name> is occupied by #<m> — hand off instead: ready-for-implementer with the same --plan`.
  The queue that handoff feeds is dormant, so it only shelves the build.
  `SURFACE_OVERRIDE=1` takes the edge and names the occupant on stderr.
- **The meta block is script-owned and invisible.** A trailing
  `<!-- board:meta … -->` comment in the issue body holds spawned-by,
  relates-to, branch, pr, plan and the current note; the trail of notes is
  the `[board]` comments. It does not render on the issue page, so a note
  is a one-line status and never the spec's home.
- **Label automation that speaks `status:*`** (assign →
  `status:in-progress`) is a legitimate writer: same store, same
  vocabulary.

## Conventions

- **Who takes what.** A `ready-for-implementer` ticket needs nobody's
  go-ahead. A `ready-for-architect` ticket's design is presented to your
  human partner before it is built, as any design is, so it is brought to
  them and not designed alone. Priorities and `wontfix` are your human
  partner's calls.
- **Deferred work has two homes, told apart by what the residue is.** Work
  that should be done later (a scope-out, a follow-up a review or a PR left
  behind) goes on the board with its lineage as edges: `--parent` for work
  that belongs to an epic, `--spawned-by` for what another ticket's work
  turned up, `--blocked-by` for what must land first. Its Decision log says
  why it was cut. A flaw accepted as it is ("ship with it") is not future
  work and goes to the repository's tech-debt tracker
  (`tech-debt-tracker.md` or its tech-debt issue) as one line with the
  reason. Both exist because a decision held only in a conversation is lost
  when the session ends. A PR that leaves residue still closes its ticket:
  `done` means the PR landed.
- **Search by seam before registering**: the file, function, RPC or table
  names the work touches. Authors word the same work differently, so a
  title search misses it. A hit on the same defect gets your evidence as a
  comment instead of a duplicate ticket; a hit on the same seam gets
  related (`board-relate.sh`). Tickets that each rewrite one function or
  contract body revert each other silently (different files, no git
  conflict), so a pile-up on one body wants a consolidating
  `ready-for-architect` ticket that owns the unified contract and names its
  members.
- **The body (the pre-spec) is written at registration**, when the
  registrar knows the most about the work, for a reader with no context who
  may come weeks later. Sections: Problem & intent / Constraints / Success
  criteria / Open questions / Decision log, plus Roadmap on a decomposed
  parent.

## Dormant machinery

The dispatch pipeline is kept in this skill, tested and armed nowhere:
`scripts/execute-dispatch.sh`, `scripts/review-dispatch.sh`,
`scripts/board-sweep.sh`, `scripts/board-bind.sh`, `board-answer.sh`
without `--to`, and every file under `references/` except the two hosted
map templates. None of it describes how work runs today; the ruling lists
each file. It explains an old ticket or comment, and is input to a
redesign.
