# The ticket board: items, labels, claims and the `task` CLI (2026-11-24)

The owner supervises many long-running Claude Code sessions across repositories and machines. Each repository's backlog, its **board**, is that repository's GitHub issues, and sessions write it through the scripts of the `issue-tracker` skill (`skills/issue-tracker/scripts/board-*.sh`). The scripts and their eleven states were cut for an unattended dispatch pipeline that has been dormant since 2026-10-18 (`docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md`), and two faults the owner named follow from that:

- **Work leaks between sessions.** A deferred item is taken up only if some session remembers it. The in-between states (`in-design`, `in-progress`, `in-review`) are moved by hand and tied to nothing, so a ticket a session took and left keeps saying someone has it: one open ticket of this repository has read `status:in-design` since 2026-10-21, the day the pull request that references it merged.
- **No whole picture.** Who holds which piece of future work is known only by reading specs and session lists.

After this change a ticket shows three things and nothing else until GitHub's close: what it needs before work can start (**readiness**), how far off it is (**horizon**), and whether a thread has it (**claimed**). A claim belongs to the thread that made it and is released by a write when that thread ends, so a claim does not outlive its holder unseen. Agents work the board through one command, `task`, shipped in a plugin of its own; the `issue-tracker` scripts, their states and the dormant dispatch machinery leave the plugin for `archive/`.

To see it working, in a session of this repository: `task list --takeable` prints the tickets a session may take on its own initiative. `task claim 548` puts `claimed` on #548 with a visible record naming the claiming session; the same command from a second session exits 3 and names the holder. Retire the first session's thread (`sminos retire`), or leave it stopped for three days: once its machine next settles its claims (at the retire, in the daemon's hourly pass, or before the next `task list` there) #548 is unclaimed again, with a record that says why, and it is back in `task list --takeable`. On the issue's page the owner reads `ready-to-work`, `expected`, `priority:P3`, `bug`, the record of who registered it, and the claim. In a checkout that carries an `upstream` remote, `task list` lists this repository's tickets and not the upstream project's.

This unit gives the whole picture its data (who holds what, and one ticket per initiative pointing at its spec); the view that draws it is a later unit (Out of scope).

## Progress

- [x] (2026-11-20 to 11-24) The design discussed with the owner; the unit confirmed on 2026-11-24 (R8).
- [x] (2026-11-24) Spec review, `doperpowers:adversarial-reviewer`, one round: the design and its interfaces (seventeen findings), and the execution section's buildability (eleven). Folded in one closing pass; what was weighed and not taken is answered where the decision stands (D3 "What is accepted", D5, D6).
- [x] (2026-11-24) A second review, of that repair: fifteen findings, nine in the board's own rules (which repository a write reaches, the relabel plan, trust, the fold's interval, the label, the race check, the old scripts in a stale checkout, what each milestone proves) and six in the part that learns a thread's end. Folded: that part stands on one rule (D3, "An end is asked for, never stated"), M3 releases an ended thread's claims with no call from sminos, and O1 puts three answers to the owner.
- [ ] The owner reads this document. Nothing is built, no issue is relabelled and no skill is edited before that read; "For the owner's read" lists what waits on them.
- [ ] M1 — the `task` plugin and the ticket verbs.
- [ ] M2 — the relabel tool.
- [ ] M3 — claims.
- [ ] M4 — sminos calls the board at a thread's start, `/clear` and end.
- [ ] M5 — the skill, the calling skills, and this repository's cutover.
- [ ] M6 — the sibling repositories' cutover.
- [ ] M7 — the old scripts retire; the final verification.

## Terms

- **The owner.** The person whose sessions these are. **The owner's account** is their GitHub account, which every session writes as: sessions have no GitHub identity of their own.
- **Board, ticket.** A board is one repository's GitHub issues read as a backlog. A ticket is an issue on a board (D1 says which issues are on it).
- **`task`.** The command this unit builds. Three things share the word and are kept apart here: `task` is the CLI; a **ticket** is an item on a GitHub board; the owner's **Task Board** is the owner's own to-dos, a separate unit (R7, R9). The engine's in-session to-do tools are unrelated to all three.
- **Session, thread** (sminos; `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, D1). A session is one conversation with an id. A **thread** is a session's durable identity in sminos: every session the owner opens in a terminal or spawns is one. It has a record on its own machine and a thread id, stays a member when its process ends (it is then `stopped`), keeps its identity when the engine hands it to a new session id, and **ends** only by `sminos retire` or after three days stopped. An ended thread **returns** when its human reopens its session. A session the MAWS app launched is not a thread (sminos calls it lane B).
- **The daemon, the ending pass.** sminos's background service on each machine; once an hour its thread sweep ends the threads stopped for more than three days (`sweep_threads`, `end_due` and `end_stopped` in `sminos/skills/sminos/scripts/sminos_daemon.py`, `end_by_rule` in `sminos.py`).
- **The guide.** The lines sminos's start hook prints into a session when it starts: who it is, where it is filed, how to reach the others.
- **Address.** The line sminos puts on a session's commits and pull requests: `alias#short (project on machine)`, or `short (project on machine)` for an unnamed session, where `short` is the first eight characters of the session id. `sminos who`, run inside a session, prints it after the key `Sminos-Session: `.
- **Old vocabulary, old scripts.** The `status:*` labels and `skills/issue-tracker/scripts/`.
- **Record block, claim record, the fold, the index, settle, the designated remote, trusted.** Defined where they are designed: D2, D3, D4 and D8.

## What the owner ruled

These bind the design. Each is quoted as written, with its time (UTC) and an English reading. Everything in Design that cites no ruling is the design's: settled in the design discussion and reported to the owner, or decided while writing this document, which "For the owner's read" lists.

| Id | Ruling | The owner's words |
|---|---|---|
| R1 | GitHub issues are the tickets' original; the board service is no longer used. | 2026-11-20 05:06: "우선 보드 서비스 arkho는 더이상 쓰지 않으며 github issue가 티켓원본이다." |
| R2 | One store, GitHub; one new CLI replaces the `issue-tracker` scripts. | 2026-11-20 07:14, to where items are stored: "GitHub 하나 (Recommended)"; to what becomes of the scripts: "새 CLI 하나로 대체 (Recommended)". The option chosen was described as setting down the stopped dispatch machinery and its states. |
| R3 | The board holds the longer view, not work in flight: short-lived or local work is kept in the documents sessions already write. | 2026-11-20 07:23: "지금 누군가 하고 있거나 묶음에서 할 일을 굳이 보드에 둘 필요가 있을지? 애초에 단기적이거나 국소적 작업들은 알아서 세션이 쓰는 문서로 관리되게 만들고 작업보드는 더 장기적인 관점 (언젠간 할일, 할지도 모르는 일, 곧 할 예정인 일 등등)을 생각했던것인데" |
| R4 | New labels; no in-between states; a ticket shows its first state, `claimed`, and its end. `needs-human` and `needs-info` merge; `interactive-preferred` is `need-design`. | 2026-11-20 07:27: "라벨도 바꿔야함. ready-to-work need-design deferred in design이랑 in progress는 필요 없지 않을지? 그냥 need-design이 끝나면 ready to work이 되고 in progress가 되는거다. needs human이랑 need info도 그냥 합치자. interactive preferred는 거의 need-design이랑 같다. … 작업 중간에 티켓을 계속해서 관리할 그런 노력의 가치가 있을지? 첫 상태와, 'claimed', 그리고 끝 상태만 표시하면 되지는 않을지에 대해" |
| R5 | A horizon axis for what outlives sessions: work that will be done a little later, work deferred because whether to do it is open, work whose order is fixed but far. No "soon": a session remembers that itself. | 2026-11-20 07:34: "보드는 마치 세션을 초월한 컨텍스트 같은 역할을 하기에, 지평은 약간 나중이지만 작업될 일, 할지 말지 몰라 defer한 일, 순서는 정해졌으나 거리가 있는 일 등등을 표현하면 좋겠다"; the names, 07:37: "planned / expected / undecided (Recommended)". |
| R6 | Nothing assigns work or binds a responsibility; whether to act is the agent's judgment. | 2026-11-20 05:06: "스레드가 '이 종류는 내 담당' 선언 자체가 필요없다. 무언가를 담당하고 말고는 그냥 에이전트가 알아서 판단하면 되고" |
| R7 | The GitHub board is the agents' side. What agents ask of the owner, and the owner's to-dos, are a Task Board built beside the question sheet, designed separately. | 2026-11-24 12:08: "GH 이슈트래커는 그냥 에이전트용으로 두고" |
| R8 | This unit is confirmed: the board work, the relabel (readiness, horizon, claimed, priority) and the CLI. Events and subscriptions are not in it. | 2026-11-24 12:12: "전체적인 보드작업과 재라벨링 (준비상태, 지평, claimed, 우선순위 등) seems good, so is task CLI."; on events, the same message: "이건 이번 스코프에 include할지 모르겠다", and 12:17, to whether they are in this scope: "이번에는 뺀다 (Recommended)". |
| R9 | The CLI is `task`, the agents' one command for tracked work, with two destinations: tickets on the GitHub board (this unit) and the human's Task Board (a separate unit, built later on a store in sminos). | 2026-11-24 12:25: "'task assignhuman' 과 같은 형태로 human task board에 쓰게하는건 어떨지? … Task board는 따로있는게 나을것같다"; reported settled by the session that holds the design discussion. |
| R10 | Work the owner gives to a named thread may be kept as a tracked item: the thread is given it as a prompt, and the item stays on the board. Who does it is always the owner's choice. | 2026-11-20 07:14, to whether work the owner gives an agent should stay as a tracked item: "대상을 정해 남긴다 (Recommended)". |

The ruling of 2026-10-18 stands: nothing starts a session from the board. One act in this design touches it, and it is put to the owner as O5.

## What it must not become

- **A record of work in flight.** A session's own documents (spec, plan, pull request) hold progress (R3, R4). After a claim nothing is written to a ticket until it closes or is set down.
- **A dispatcher.** Nothing assigns work (R6), and no machine sends a thread a message because of a ticket.
- **A second store.** GitHub is the one home of every ticket (R1, R2). No service of our own and no mirror: the retired board service mirrored tickets into GitHub issues marked read-only.
- **Bookkeeping in the middle of work**, by agents. What must be kept true while work runs is written by a machine at the moment it learns the fact (D3).
- **Typed tools for agents.** A CLI with JSON output; a tool only where the harness must draw something for the owner, which nothing here does.
- **A queue with leases**, or a channel that owns responsibilities.

## What exists today

Measured on 2026-11-24; the decisions below rest on these.

- **This repository's board.** 103 issues, 53 open, every one authored by the owner's account. On the open ones: `status:ready-for-implementer` 21, `status:deferred` 19, `status:ready-for-architect` 9, `status:in-design` 1, no status label 3; `priority:P3` 38, `P2` 11, `P1` 1, none 3; `bug` 26, `enhancement` 20, `spike` 1, no category 6. Eleven `status:*` labels exist, two of them legacy names (`status:ready-for-agent`, `status:confident-ready`). Eleven closed issues still carry a status label, and one merged pull request carries `engine:claude`. 22 open issues carry a `board:meta` block with a note or a relation in it; the block is an HTML comment, invisible on the issue's page. Two open issues open with the retired board service's banner ("Read-only. Edits here are reverted … The board is the source of truth"). No open issue has a native parent or blocked-by edge. The repository's issue templates put `bug` or `enhancement` on whatever a visitor files.
- **Sibling repositories.** Two public repositories of the owner's carry the old vocabulary: `cua` (214 open issues; 27 with a parent, 3 parents, 23 blocked) and `MAWS` (about 110 open; 9, 2, 25). The private `arkho` carries it too, and `ida-solution`, in an organization, cannot be read from the owner's account today. None of the three readable ones commits a `.doperpowers/board.json`, so each relies on the GitHub client's own resolution of the repository. The text "Board Write Hard Gate" stands in `cua`'s `CLAUDE.md`, and in `ida-solution`'s `CLAUDE.md`, one of its runbooks and, on some of its branches, its `AGENTS.md`; `ida-solution`'s checkout also holds a workflow that writes `status:*` labels and one that publishes a board page.
- **The GitHub client resolves the wrong repository in a fork.** In a fresh repository with `origin` set to this fork and `upstream` set to the project it was forked from, `gh repo view` answered the upstream project and `gh issue list` listed its issues, with no warning (gh 2.97.0). This repository's main checkout answers correctly only because a default was once recorded there. Every checkout of this repository carries both remotes: `origin` for the fork, `upstream` for the project it was forked from.
- **The old scripts.** They run from the installed plugin, whatever branch a checkout is on. `_binding.sh` reads the checkout's `.doperpowers/board.json`, and the main checkout's only when a linked worktree has no such file; it stops on any `binding` other than `gh` or `api`: `unknown binding "<x>" — expected "gh" or "api"`. `board-body.sh` replaces a body's text and splices back only a trailing `board:meta` block. `_board.py`'s `ensure_labels` creates the `status:*` labels again whenever a script needs them. Two skills call the scripts by name or tell sessions to make tickets of a spec's children: `skills/decomposing/SKILL.md` (its optional step 6) and `skills/organizing-sprints/SKILL.md` (Materialization, which names `board-register.sh`, `--state` values and `board-lint.sh`).
- **GitHub.** One GraphQL query returns, for an issue and each of its comments, the author, the last editor (`editor`), the comment's id (`databaseId`) and creation time (to the second), the pull requests that reference or close it, its linked branches, and its close and reopen events. A reopening is dated to the second as a comment is, and nothing documented orders the two within one second. The REST API lists an issue's comments in ascending id. A closed issue still takes comments. Nothing in the API writes an issue on a condition (no "only if unchanged"). Labels, native blocked-by and parent edges are written by the old scripts today through the same API.
- **sminos** (1.58.0). `sminos who` and `sminos who --thread=<name>` exist (the second since 1.53.0, one line of JSON: `thread`, `session`, `short`, `alias`, `opened`, `state`, `ended`, `local`, `machine`, `project`; exit 2 from an older sminos). A name that is a full session id or thread id answers for a live, a stopped and an ended thread; an ended thread its human opened answers to a full id only. A session id answers for the thread whose current session it is and, failing that, for a thread that once had it. A session its thread handed off, reopened by its human, becomes a thread of its own (`ensure` in `sminos_threads.py`), so one session id names different threads over time; the answer's `session` is the current session of the thread that answered. Exit 4 means nothing answered the name, or several did. The lookup walks the project logs registered on the machine (`find_target` in `sminos.py`), so a thread whose record was deleted (`sminos retire --purge`, `sminos remove`) and a thread sminos cannot see from where it runs answer alike: on 1.58.0 a live thread's own id, asked under an empty state directory, gave exit 4 and `no seat or member matching`, word for word what an id no record carries gives. A thread's `ended` is written by its own machine: in the ending pass, or by a retire, whose end and purge are one journaled transition (`thread_transition`), with no step between them. The end is written before anything is stopped, so a session that retires itself can be stopped before its command returns. A thread that returns loses its `ended` mark. A message addressed to a stopped thread wakes it. What a `/clear` left is known to the new session's start hooks only, through a note that is believed for sixty seconds and that no record keeps. `cleared_from` (in `sminos.py`) reads the note and names the session left, for either start hook, in either order. `cleared_witness` is narrower: it answers only while the session left still holds the name its process goes by, which the record hook takes from it (`release_alias`), so it answers the guide's hook only when that hook runs before the record hook, and never for an unnamed session. sminos asks the devcloud plugin one question through its CLI (`find_devcloud` and `owned_by` in `sminos_threads.py`): found in a fixed list of places, held to a minimum version, bounded by a timeout, and no answer is never read as "none". A subagent's Bash runs with its parent session's id, and a plugin's `bin/` directory comes last on a session's `PATH`.

## Design

### D1. Items and labels

A ticket is a GitHub issue in its project's repository. Its labels:

| Axis | Labels | Rule |
|---|---|---|
| Readiness | `ready-to-work`, `need-design`, `need-input` | exactly one on every ticket |
| Horizon | `planned`, `expected`, `undecided` | exactly one on every ticket, kept through a claim |
| Claim | `claimed` | shown while a thread holds the ticket; what decides is the fold (D3) |
| Priority | `priority:P0` … `priority:P3` | one, required at creation; unchanged from today |
| Category | `bug`, `enhancement`, `spike`, `env-issue` | one, required at creation; unchanged from today |
| Batch | `batch:<name>` | optional: a named set one agent takes whole |

**An open issue is on the board when it carries a readiness label.** No other label enrolls it: the issue templates put a category on whatever a visitor files, so a category says nothing about whose work an issue is. An open issue without a readiness label is *untracked*: the board's rules and `task lint` do not apply to it, and `task list --untracked` shows it.

- **Readiness** says what must exist before work can start (R4). `ready-to-work`: buildable from its body, or from the spec its record points at. `need-design`: its design comes first, with the owner, through doperpowers:brainstorming; it absorbs `interactive-preferred`. `need-input`: it waits on something that is neither design nor build (a decision or a real-world input only the owner holds, or research); it absorbs `needs-human` and `needs-info`, and its body says in prose what it waits on and what would unpark it. A request to the owner is not a ticket (R7), so no label marks a ticket as the owner's.
- **Horizon** says how far off the work is (R5). `planned`: its order is decided, and "after what" is a blocked-by edge. `expected`: it will be worked, in no decided order; the default. `undecided`: whether to do it at all is open.
- **The end** is GitHub's close: completed, or not planned. A closed ticket's labels mean nothing.
- **Nothing in between** (R4). Readiness and horizon stay as they were when a ticket is claimed: `need-design` with `claimed` reads "someone is designing it". When design ends the holder sets `ready-to-work` and the spec pointer; that is the one mid-life write, and it happens at a hand-over, not during work.

**What a session may take on its own initiative** (a *takeable* ticket). All of these hold, and anything unknown counts against:

1. it is open and unheld, by the fold (D3);
2. its only readiness label is `ready-to-work`;
3. its only horizon label is `expected` or `planned`;
4. every blocker is closed as completed, and a `planned` ticket has at least one blocker (a blocker closed as not planned leaves the ticket *stuck*, for a person to cut the edge or drop the ticket, as the old scripts had it; a `planned` ticket with no edge says its order is decided and nothing says after what);
5. its body is trusted (D8);
6. it is not registered for another thread.

Any other ticket is taken on the owner's word. An `undecided` ticket is never takeable: whether to do it is the owner's call, which is what the label records. `task claim` does not enforce takeability, since the owner may name any ticket; it prints which condition fails and claims. `task list --takeable` is how a session finds the set.

**Edges** are GitHub's native ones, as today: blocked-by (a dependency) and parent (a sub-issue). `cua` and `MAWS` use both. The bookkeeping the old states carried on a parent (pulled in flight by its first active child, returned for "recomposition" when its last child lands) goes with those states: a parent is a ticket like any other, closed by whoever holds its work.

**An initiative** is at most one ticket whose record points at its spec. The children of a composite spec stay in the spec; they are not tickets, since the same fact written twice drifts (R3). Two skills tell sessions otherwise today and change with the cutover (D7).

**A ticket registered for a thread** (R10). When the owner gives work to a named thread and wants it tracked, the ticket's record names the thread (`for:`, D2), and `task create --to <thread>` sends that thread one message naming the ticket (O5). The thread claims it when it takes it. It is not born claimed: a claim is written from its holder's own machine (D3), the only machine that can release it. A ticket registered for one thread is claimed by another only after the record is changed (`task set <n> --to …` or `--no-to`), which is a visible act on the owner's word.

**Categories** keep their four names. `env-issue` loses its inverted birth rule (born `needs-human` unless a state was given): readiness is stated at every creation, so there is no default to invert.

### D2. What is text: the record block

GitHub holds labels, edges, the pull requests and branches linked to an issue, and the close. Four facts have no native home and are text the CLI parses, in one visible block that ends the issue's body:

````
```task-record
registered-by: builder#1a2b3c4d (doperpowers on laptop)
for: reviewer#5e6f7a8b (doperpowers on laptop)
due: 2027-01-05
spec: docs/doperpowers/specs/2026-11-24-ticket-board-design.md
```
````

`registered-by` is the address of the session that created the ticket (absent when no session did); `for` the thread it was registered for (D1); `due` a date the work must be done by; `spec` a repository-relative path, optionally `@<sha>`, or a URL when the spec lives in another repository. A fifth line, `adopted:`, is written by one act only (D8). Every key is optional, each value is one line, and the block is read only when it is the last thing in the body and the body is trusted (D8). It is a fenced block and not an HTML comment because the block it replaces, `board:meta`, was invisible on the issue's page, and a status note the owner cannot see is of no use to them.

The claim's holder is not in this block (D3 says why). Lineage that the old block carried (`spawned-by`, `relates-to`) is prose in the body: a mention of `#n` already cross-links both issues on GitHub.

Every body write by the CLI reads the body afresh, replaces the text above the block and keeps the block byte for byte; it writes only a body it trusts (D8). Two limits are accepted. A raw `gh issue edit --body` drops the block, and nothing can tell afterwards that it was there, so the skill sends every body edit through `task set` (M5); the old scripts' body writer drops it the same way, which D7 fences. And the body is one string with no conditional write: two edits of one ticket's body within the same moment (its text and its `for`, say) leave the later one standing. These fields change at creation and at a hand-over, a few times in a ticket's life, which is why they may live in the body and the claim may not.

### D3. Claims

A claim says a thread has taken a ticket. It belongs to the thread, so it survives a compaction, a hand-off to a new session id and a stopped process, and it changes only by a write: a release by its holder, a release by the holder's machine when the thread ends, or a takeover. No reader infers that a claim has lapsed, because a thread that looks gone can return. There is no lease: a lease must be renewed, and renewal is bookkeeping in the middle of work (R4); a long-lived thread's claim would lapse under it while the thread works.

**The record.** Each change of a claim is one comment on the ticket, written by the CLI, holding one fenced block and, after it, any prose the writer adds (where the work stands, at a release):

````
```task-claim
op: claim
holder: builder#1a2b3c4d (doperpowers on laptop)
attempt: 9f2c41d07a3b5e68
```
````

`op` is `claim`, `release` or `takeover`. A claim's **id** is the GitHub id of the comment that made it (a `claim` or a `takeover`). `release` carries `of: <claim id>` and `reason:` (`released`, `ended`, or `forced: <text>`); `takeover` carries `of:`, `holder:` and `reason:` (`cleared`, or `forced: <text>`). A `claim` and a `takeover` also carry `attempt:`, a random token minted for that one try: it is how the machine that wrote a record finds it again when it never learned the comment's id (the index, below), since an address repeats across a session's claims and a token does not. The holder is written as the claiming session's address: what every commit of that session already publishes, and nothing else of sminos's (no thread id, no project id). A subagent's claim is its session's, since its commands run with the parent session's id.

**The fold.** Who holds a ticket is computed the same way by every reader. A closed ticket is unheld. For an open one, take its comments in ascending id, keep those that carry a `task-claim` block, are trusted (D8) and were created in the ticket's current open interval, and apply:

| Record | Ticket unheld | Ticket held by claim *c* |
|---|---|---|
| `claim` (comment *k*) | held by *k* | void |
| `release` of *x* | void | *x* = *c*: unheld; otherwise void |
| `takeover` of *x* (comment *k*) | void | *x* = *c*: held by *k*; otherwise void |

A void record changes nothing. The open interval begins at the ticket's last reopening, or at its creation when it was never closed. A close ends every claim: a reopened ticket starts unheld, and a record that landed while the ticket was closed (a claim begun a moment before a merge closed it) lies outside the interval. GitHub dates a comment and a reopening to the second and documents no order between two of the same second, so a record dated the second of the last reopening is outside the interval, whichever of the two came first: its writer finds it void, deletes it and claims again. *Weighed: the place of the two in GitHub's timeline of comments and events.* It lost: it rests on an order GitHub does not document for two entries of one second, and every fold would read a second listing to settle a tie that costs its loser one retry.

**Arbitration.** `task claim` reads and folds; if the ticket is held it refuses; otherwise it appends its `claim`, reads and folds again, and holds the ticket only if the fold names its own comment. A writer that finds its record void deletes it, and reports who won; when the fold names no one (the tie above) it claims once more, after that second has passed. The order GitHub gives the comments decides between two claims seconds apart, where today's scripts rewrite labels with nothing to arbitrate. This rests on one assumption GitHub does not document: that the confirming read shows every comment with a lower id. If a read ever misses one, two sessions believe they hold the ticket until either next touches it, when the fold names the lower id for both. That window is accepted. GitHub offers no conditional write to close it with, and the one primitive that would (an atomic creation of a git ref per claim) puts refs in every repository for a collision that needs two sessions, one ticket and the same second. M3 measures it (Delegated unknowns); a measurement is not a proof, and a measured violation stops M3.

*Alternative weighed: the holder as a field of the record block.* It lost on two counts. The body is one string, so a claim, a release and an edit of the ticket's text would overwrite one another, and a release lost that way leaves a ticket held by a thread that has ended. And a single field holds no history, while a takeover has to name the claim it supersedes so that a stale one is void. *Alternative: GitHub's assignee.* Every session writes as the one owner's account, so an assignee cannot tell two threads apart.

**The label.** `claimed` is a display: what the owner reads on the issue's page. It converges on the fold and decides nothing. Whether a ticket is held, by whom, and so whether it is takeable, is read from the fold by every verb: `task list` and `task show` fold each ticket they print (one paged query returns a board's open tickets with their comments), and no verb reads the label to decide. Every writer of a claim record ends the same way: it reads the ticket again and writes the label to what the fold then says, and looks once more, correcting the label if the fold moved under its write. No order of label writes keeps the label right by itself. Two releases of one claim (its holder's, and its machine's settle) can interleave with a later claim so that the second release takes the new holder's label off; the look after the write is what puts it back. A writer killed between its record and its label leaves the label wrong until a verb next folds that ticket: `task list` and `task show` write the label of a ticket they find disagreeing with its fold, settle does so for the tickets in its rows, and `task lint` reports it. So a wrong label is repaired by the next `task list` on that board, from any machine, whether or not a settle ever visits the ticket.

**The index.** Each machine keeps, in the plugin's own directory, one row per claim it wrote that it has not yet seen end: the repository, the ticket, the claim's id, its attempt token, the claiming session and its thread (both private to the machine), when, and a `successor` once a `/clear` granted one. A `claim` and a `takeover` are the two operations that make a holder, and both write their row before they append, as *pending*, with the token the record will carry. An append GitHub accepted and the process never heard about is then found again: the next settle reads the ticket and adopts the record that carries the row's token. The index exists so that the machine can answer "what does this thread hold" at a session's start without a network call, and can find a thread's claims when the thread ends without scanning every repository. It holds nothing of a ticket's content and decides nothing: every act reads the ticket again. *Alternative: no index, a scan of GitHub.* It lost because the start of every session would wait on the network, and because a machine would need a list of every board it ever wrote to, which is an index by another name.

**A row's thread is established when the claim is made, or never.** Before it writes anything, a `claim` or a `takeover` asks sminos which thread the claiming session is, by the session's full id, and takes only a definite answer: one that names that very session as its current one, on this machine. The answer's thread is then a thread id, or empty, which is sminos saying the session is no thread (one the MAWS app launched); no lifecycle release applies to such a row (O4). Without a definite answer the verb exits 1 and writes nothing. A row's thread is never asked for afterwards. A session id names different threads over time (a session its thread handed off, reopened by its human, is a thread of its own), so a question put after the claim can attach the row to a thread that never made it, and that thread's end would then release a claim it does not hold.

**Events, and who writes.** Each change of a claim is written by the machine that learns the fact first. "The label" below is the label made to agree with the fold, as above.

| Event | Writer | Written on GitHub | Index |
|---|---|---|---|
| A session claims | that session's `task claim` | `claim` record; the label | a pending row, then held |
| The holder sets the ticket down | its `task release` | `release` (`released`); the label | row removed |
| The holder's thread ends (a retire, or three days stopped) | its machine, at its next settle | `release` (`ended`); the label | row kept as *lapsed* |
| A `/clear` in the holder's process | sminos's guide in the new session (D5) | nothing: the claims stay with the thread that was left | its rows gain the new session as `successor` |
| The successor takes over | its `task takeover` | `takeover` (`cleared`); the label | a pending row for the taker, then held; the left thread's row turns lapsed |
| Another session takes over | its `task takeover --force` | `takeover` (`forced: …`); the label | a pending row for the taker, then held; the former holder's machine marks its row lapsed at its next settle |
| The ticket closes (a merge, or `task close`) | `task close`; else the holder's machine at its next settle | the label off | row removed |
| GitHub is unreachable when a release is due | — | — | row marked *owed*; every later settle, and every later `task` verb on that machine that writes to GitHub, tries it again first |

**Settle** is the one routine that makes a machine's claims true. For each row (of one thread, or all) it reads the ticket once and acts on what it finds; a board it cannot reach is skipped and reported, and the other boards' rows go on.

- A pending row: the record that carries the row's token is looked for among the ticket's trusted records. Found, and the fold names it: the row is held, with that record's id. Found, and void: the record is deleted and the row dropped. Not found: the row is dropped once it is an hour old.
- The ticket is closed: the label is taken off and the row removed.
- The fold does not name the row's claim: the row is lapsed. If it was owed, this machine's own release got through before a crash, and its reason stands; otherwise another session took the ticket over or released it by force. The label is made to agree with the fold as it now is.
- The fold names it: the label is made to agree. Then, if the row has a thread id, sminos is asked about that id, and only an answer that carries the very id, of this machine, and says it has ended releases: the row is marked owed, the release written, the label made to agree, the row marked lapsed.
- Any other answer about a thread, or none: nothing changes, and the row is reported as unknown, with what sminos said.

**An end is asked for, never stated.** Settle takes no caller's word that a thread has ended. It asks sminos, at the moment it runs, about each thread id its rows carry. So every call to settle is only a trigger, "settle now", and a trigger that comes late, twice or not at all changes nothing: the next settle asks the same question and gets the answer of that moment. *Weighed: the caller stating the end as it calls* (a flag on settle, for a retire, which has the fact in hand and is the only one that does after a purge). It lost on what a statement does when it is not acted on at once. Arriving after the thread returned and claimed again, it releases the new claim. Lost with the retire's process, or never made because the session that retired was stopped by its own end, it is not made again. And delivered while GitHub is down, it has to be kept until the release can be written, as the only proof of an end that, after a purge, nobody can ask about again. *Weighed: sminos handing the plugin a list of what ended.* It lost the same way: a crash between sminos writing an end and telling the plugin loses the release for good, while a settle that failed is simply run again.

**When settle runs.** Before `task list` and `task claim` answer, they run a settle of the machine's rows, unless one ran there in the last ten minutes. It is bounded, and a settle that fails or runs out of time does not fail the verb. That alone releases an ended thread's claims, with nothing changed in sminos, by the time a session on that machine next looks for work or takes some. Ten minutes because a session looking for work lists several times in a row, and a settle costs one read per row and one question per thread. sminos adds promptness (D5): a retire starts a settle of the retired thread's rows, and the daemon's ending pass starts one each time it runs, which also reaches a machine where no session runs `task`. `task settle` run by hand is the same routine.

**A thread that returns.** If its human reopens it before its machine's next settle, sminos no longer calls it ended and it keeps its claims, which is right: it is live and nothing was released. If it returns after, its claims were released and another session may hold the ticket. `task held` reports each lapsed row, with why, for seven days, so that the thread's guide tells it to claim again before it continues; `task list` and `task claim` print the same for the rows the calling session made, which is what a returning session reads where sminos does not call the plugin. Reporting by age, and not once, means a start whose guide was lost does not lose the warning, and the rows of a thread that never asks again expire.

**Takeover.** `task takeover <n>` writes a `takeover` of the current claim, in the order a claim is made: the thread asked for, the pending row, the append, the confirming fold. Without a stated reason it is open only along a `/clear`: the index holds a `successor` grant for this session on that claim. Everything else is `--force "<reason>"`, with the reason written in the record: taking a live thread's ticket means two sessions building one thing, and the one who decides that is the owner. An ended thread needs no takeover, because its machine releases its claim; a holder whose machine is gone, or whose row was lost, is exactly the case a person should look at. `task release` and `task close` follow the same rule: the holder acts on its own claim (the row is its thread's, or the record's address is its session's), and anyone else needs `--force "<reason>"`. The grant is not a lock against a session that misuses the CLI, which `--force` would serve as well: it is what lets the ordinary case go without a reason.

**What a reader is shown.** `task show` prints the holder's address, the claim's age, and the last activity on the pull requests and branches GitHub links to the ticket. With no lease, that is what lets a reader judge a claim that has gone quiet.

**What is accepted.** These are left as they are. Each that leaves a claim no machine will release is visible (the claim's age and linked activity on `task show`, the row in settle's `unknown`) and ends with `task release --force` or a forced takeover.

- **A session the MAWS app launched** is not a thread: no machine learns that it ended for good (O4).
- **A thread whose record is deleted keeps its claims.** `sminos retire --purge` and `sminos remove` delete a thread's record in the same transition that ends it, and afterwards sminos answers for that thread id as for one it never had: exit 4, `no seat or member matching`. That is also what it answers for a thread it cannot see from where it runs (another state directory, a project whose registration it cannot read), so the answer does not say "deleted", and a release on it would take a live thread's claims whenever sminos misread its own store. Settle therefore reports such a row as unknown and writes nothing. The retire that purged prints the tickets that thread still holds and the command that releases each (D5); a session that removes its own seat is stopped before it prints anything. *Weighed: sminos keeping the ids of the threads it purged, so that it could answer "ended" for one.* Not taken in this unit: it changes what a purge leaves behind and what `who --thread` answers, which is a decision about sminos, and what it would buy here is the release of a claim that meanwhile shows its age.
- **A thread that returns between settle's question and its release.** sminos answered "ended", the thread's human reopened it in the same seconds, and the release is written over a live thread. The thread learns of it at its next start or its next `task list`, and another session may claim the ticket meanwhile. The window is two calls of one settle; closing it would take a lock held across both plugins, for a reopening timed to those seconds.
- **A machine where nothing starts a settle**: one where no session runs `task list` or `task claim` again and, before M4 or with no daemon running, nothing else does. After M4 a retire still starts one there.
- **A holder's machine that is retired, or an index that is lost.**
- **A `/clear` whose grant was not recorded** (the plugin slower than the guide's bound, or the note of what was left older than sminos believes it): the new session takes over with `--force` and a reason.
- **`task close` checks the holder when it runs**; a takeover in the same moment is not arbitrated against it.
- **A label left wrong by a killed writer** stays wrong until the next verb that folds its ticket (above).

**What the parts cost and buy** (O1). The fold is a table, one extra read per claim, and the comments of every ticket a list prints; it buys one winner between two sessions. Everything else here (the index, settle, sminos's calls) buys one thing: a claim does not outlive its thread, which is the fault this work opened with. The plugin's half alone releases at the next `task list` or `task claim` on the holder's machine; sminos's calls make the release prompt and reach a machine where nothing runs `task`. Contention between two sessions is rare; a session that takes a ticket and is then closed for good is not.

### D4. The `task` CLI and its plugin

A new plugin, `task`, in this marketplace (`task/` at the repository's root, versioned on its own). Its command is `task` (R9), its skill `task:tickets`. It is a plugin of its own, and not part of doperpowers or sminos, so that it rides neither's releases: a board fix must not wait for, or force, a sminos release, and sminos must run without it.

**Two destinations, one built.** `task` is the agents' one command for tracked work (R9). Every verb this unit builds acts on tickets. Verbs that write to the human's Task Board (the owner's example: `task assign-human`) belong to the separate unit that designs it; the command's dispatch keeps one flat verb namespace with those names unused, and `task assign-human` exits 2 saying that the Task Board is not built.

**The repository is the designated remote's, never resolved.** A checkout's board is the repository of one git remote, the *designated remote*: `origin`, or the remote that `git config task.remote` names. That setting lives in the repository's git configuration, which is outside the tree, shared by every linked worktree and carried by no branch. Every call to GitHub names that repository, read from the remote's URL, and the CLI never asks the GitHub client which repository a directory belongs to (see "What exists today": in a fork the client answers the upstream project). The committed `.doperpowers/board.json` names the same repository in `repo`, and the CLI refuses when the two differ. The file cannot choose the repository by itself, even among the checkout's remotes: a branch checked out for review is someone else's text, this repository's checkouts carry `upstream` beside `origin`, and a file naming the upstream project would send `task comment` to another project's issue. *Weighed: reading the file from the designated remote's default branch instead of the checkout.* It lost as the larger rule: the remote alone already fixes where a write goes, and the checkout's file is what makes one commit the cutover switch (below). `--repo owner/name` works a board from outside its checkout: every call names that repository and no other, its configuration is read from that repository's default branch, and the checkout the command happens to run in, its file and its remotes, are not consulted.

**The binding is the cutover switch.** `binding` in that file says which tool owns the board. `"task"`: this CLI. Anything else: every verb that works a board refuses, naming the file, except `task migrate plan`, which only reads. The old scripts refuse a binding they do not know, so one committed line moves a repository from one tool to the other in every checkout that has the commit; in a checkout that does not, the old scripts refuse once the designated remote's default branch says `task` (D7 says what that reaches and what it leaves). Two verbs work no board and need no checkout: `task held` and `task settle` work from the machine's index, each row naming its own repository, and run from any directory, a service's included.

**Verbs.**

| Verb | Does |
|---|---|
| `task create <title> --category C --priority P --readiness R --body-file F` `[--horizon H] [--blocked-by N,…] [--parent N] [--batch NAME] [--due DATE] [--spec S] [--to THREAD]` | opens the ticket with its labels, edges and record block; prints `<number> <url>` |
| `task show <n>` | the ticket: labels, record, edges, the holder with its age and linked activity, the body with its digest, the comments, each marked with whether it is trusted |
| `task list` `[--takeable] [--readiness R] [--horizon H] [--claimed\|--unclaimed] [--batch NAME] [--untracked]` | tickets by priority, then number: readiness, horizon, priority, holder, blockers, `for`, `due`, title. `--untracked` lists the open issues that are not on the board instead |
| `task search <query> [--state open\|closed\|all] [--bodies]` | GitHub's issue search, held to the board's repository |
| `task set <n>` `[--readiness R] [--horizon H] [--priority P] [--category C] [--batch NAME\|--no-batch] [--due D\|--no-due] [--spec S\|--no-spec] [--to T\|--no-to] [--title T] [--body-file F]` | changes labels, the record block, the title or the text above the block; it changes no body it does not trust (D8). Setting a readiness also takes any `status:*` label off the issue |
| `task adopt <n> --digest D` | makes a body that another account edited trusted, on the owner's word, after it was read whole (D8) |
| `task edge <n> --block N \| --unblock N \| --parent N \| --orphan` | one edge; refuses a self-edge and a blocked-by cycle |
| `task comment <n> --body-file F` | a comment, so that no session needs a raw client call, which could resolve the wrong repository |
| `task claim <n>… \| --batch NAME`, `task release <n> [--body-file F] [--force R]`, `task takeover <n> [--force R]` | D3. Several tickets are claimed one by one, and the output says which were won. A ticket this session's thread already holds is "already yours", exit 0 |
| `task close <n> [--not-planned] [--body-file F] [--force R]` | closes it, completed unless told otherwise; refuses a ticket another thread holds, without `--force` |
| `task lint` | the invariants over the live board (Interfaces §6) |
| `task migrate plan`, `task migrate apply <plan>` | the one-time relabel (D6) |
| `task held`, `task settle` | what a machine holds, and the routine that makes its claims true (D3); what sminos calls (D5) |

`create` writes the readiness label last, after the issue and its edges exist, so that a ticket whose blocker could not be attached is never seen as ready; if an edge fails, the issue is left untracked and the output says so. `--to` names a thread sminos must resolve: when it cannot, `create` and `set` exit 1 and write nothing.

Every reading verb takes `--json`. Two of them are not free of writes: `list` runs D3's settle first, and `list` and `show` correct a `claimed` label that disagrees with the fold. `search` and `lint` only read. Exit codes: 0 done; 1 failed (GitHub, the configuration, a sminos answer the verb cannot do without); 2 usage, or a verb this unit does not build; 3 refused by a rule of the board (held by another, not the holder, registered for another thread, an untrusted body, a failed lint, a plan with undecided rows).

**It writes as the owner's account**, through the `gh` client's own credential, as the old scripts do. The session that wrote is named in the record.

### D5. The contract with sminos

Two plugins, one narrow contract in each direction, in the manner of sminos and devcloud: each side finds the other's CLI, asks one bounded question, and treats silence as no answer.

**`task` asks sminos** (nothing new in sminos; 1.53.0 or later):

| Call | For | Without an answer |
|---|---|---|
| `sminos who`, inside a session | the session's address: `holder`, `registered-by` | `claim` and `takeover` refuse (exit 1): a claim belongs to a session sminos knows. `create` writes no `registered-by` |
| `sminos who --thread=<the session's own id>` | at a claim or a takeover, before anything is written: the session's thread, kept in the row. Only an answer whose `session` is that id and whose `local` is true is taken; its `thread` is a thread id, or empty when sminos says the session is no thread | `claim` and `takeover` exit 1 and write nothing |
| `sminos who --thread=<a row's thread id>` | at settle: whether that thread has ended. Only an answer whose `thread` is that very id, with `local` and `ended` true, releases | the row is reported unknown. Exit 4 is no answer: sminos gives it for a deleted record and for one it cannot see alike (D3, "What is accepted") |
| `sminos who --thread=<name>` | the thread `--to` names | `create --to` and `set --to` exit 1 |
| `sminos say "@<thread> <text>"` | the one message of `create --to` (O5) | the ticket exists, and the output prints the line to send |

Threads are always asked about by a full id, never by the short id in a public address: a short id can answer for another session, and an ended thread answers to its full id only. A session's id is asked about only while that session is claiming, when it is running and the answer can be checked against it; every later question about a row uses the thread id the row recorded then (D3).

**sminos calls `task`** (M4 adds these calls and nothing else):

| When | Call | sminos does |
|---|---|---|
| A thread's session starts (the guide) | `task held --session <session id> --thread <thread id> --json` | prints one guide line: what the thread holds, what lapsed, and what the conversation it cleared from still offers it |
| The same start, when it follows a `/clear` and the session left is a thread of this machine | the same call with `--cleared-from <that thread's id>`, which records the grant | prints what the conversation it left holds, and that `task takeover <n>` takes one over |
| A retire or a remove has returned | `task settle --thread <thread id> --json` | prints what was released, and each ticket that thread still holds with the command that releases it; or that the board gave no answer |
| The daemon's ending pass, each time it runs | `task settle --json`, as a child the tick does not wait for | logs when the count of owed or unknown rows changes, and each distinct failure once |

Both settle calls are triggers and carry no fact (D3): the plugin asks sminos about each thread itself, at the moment it runs. A trigger that is never delivered (a session that retires itself is stopped by its own end before its command returns; a timeout; a plugin that is not there) loses nothing but time, since the next settle on that machine asks again.

sminos finds `task` as it finds devcloud (an override variable, the copy beside its own plugin, the marketplace clone, then `PATH`), reads the plugin's version from its manifest and asks nothing of one below the floor, bounds each call, and reads a missing plugin, an old one, a timeout or a non-zero exit as no answer. It never reads the plugin's files, and no session start, retire or pass fails or waits past its bound because of the board.

sminos is the caller at these moments because it alone knows them: it owns the guide, it holds the only note of a `/clear`, and it is where a thread's end is written.

- **At a `/clear`** the grant is recorded at the new session's start, because the note of what was left is believed for a minute and nothing keeps it afterwards. The guide reads the note itself, finds the thread whose current session is the one left, and passes that thread's id. It does not wait for, or depend on, the hand-over of the session's name, which the other start hook performs in an order nothing fixes and which an unnamed session never has (M4). The new session is shown the offer at each of its starts until it takes the ticket over or the thread it left ends. No message is sent when that thread ends: a message to a stopped successor would wake it, and a machine waking a session over a ticket is what the ruling of 2026-10-18 ended.
- **At a retire** sminos calls after its own transition has returned and holds none of its locks, since the plugin asks sminos about the thread while it runs. After a plain retire the question finds the thread ended, and its claims are released and printed. After a purge or a remove the question finds nothing (D3, "What is accepted"): the answer lists that thread's rows as unknown, and the retire prints each ticket with `task release <n> --force "<reason>"`, for the person or the session that purged to run. The call is bounded at 30 seconds, and a retire that hears nothing says so and goes on.
- **In the ending pass** the daemon starts one settle each time the pass runs, so a thread ended by the three-day rule loses its claims within the pass that ended it, on a machine where no session runs `task` as well.

### D6. The relabel

Existing issues are relabelled once per repository, by a plan a session reads before it is applied.

`task migrate plan` needs only a repository (the designated remote's, or `--repo`), since it runs before a board has moved. It reads the open issues and writes a plan with three kinds of entry. An issue that carries an old status label gets a row: its old labels, the new readiness and horizon, and whether the row is **mechanical** (the old label decides it) or a **decision** (it does not). An issue with neither a status label nor a readiness label that the trusted account authored gets a decision row whose outcome may be to leave it untracked; one already on the board gets a row only when its body still holds a `board:meta` block or the retired service's banner, and that row rewrites the body and no label. An issue anyone else authored is listed as incoming and never written: it stays untracked (D8). Each row also records what its proposal was computed from: a digest of the body, that the issue was open, its labels, and each blocker with its state, which the horizon rule reads.

`task migrate apply <plan>` refuses a plan made for another repository, and refuses while a decision row is undecided. It writes what was reviewed, onto what was read, or nothing. For each row it reads the issue again. A row's writes go in one order: the body, where the row rewrites one; the horizon label on; the readiness label on; the old status labels off. The body goes first so that a ticket is never on the board, and takeable, with its note still hidden; the old status label comes off last so that an interrupted row still carries it and is found by anyone who lists that label. A row is done only when its body and its labels are both at their targets. An issue whose body is the one the plan read or the one it proposed, and whose labels stand somewhere along that order, is the plan's own row, untouched or unfinished, and the apply takes it from where it stands. Anything else has changed since the plan was read (its text edited, the issue closed, a blocker closed or added, a label moved off that path): the row is skipped and listed for a new plan. So an apply never writes a body computed from text that is no longer there, an apply that stopped halfway is run again and finishes, and a second apply writes nothing. It ends by listing every skipped row and every open issue that still carries an old status label (an issue opened since the plan among them), which is what a new plan is made for.

The old labels' definitions are left in the repository, and closed issues keep whatever they carry. Deleting a definition is the one act here that cannot be taken back (it strips the label from every closed issue and from the merged pull request that carries `engine:claude`), and nothing depends on it: the board's rules read open issues only. Once every board has moved, deleting the dead definitions is a one-line act the owner can ask for.

*Alternative weighed: keep the old labels and translate them when reading.* It lost to R4: the owner reads the labels on GitHub itself, where nothing translates.

The mapping covers every status label in use on the four repositories' boards; the counts are this repository's open issues.

| Old label | Open here | Readiness | Horizon | Row |
|---|---|---|---|---|
| `status:ready-for-implementer` | 21 | `ready-to-work` | by rule | mechanical |
| `status:ready-for-architect` | 9 | `need-design` | by rule | mechanical |
| `status:interactive-preferred` | 0 | `need-design` | by rule | mechanical |
| `status:needs-human`, `status:needs-info`, legacy `status:blocked` | 0 | `need-input` | by rule | mechanical |
| legacy `status:ready-for-agent` | 0 | `ready-to-work` | by rule | mechanical |
| `status:deferred` | 19 | by reading; else `need-design` | by reading; else `undecided` | decision |
| `status:in-design` | 1 | `need-design` | by rule | decision: is a session still on it? |
| `status:in-progress`, `status:in-review`, legacy `status:confident-ready` | 0 | `ready-to-work` | by rule | decision: is a session still on it? |
| two status labels | 0 | by reading | by reading | decision |
| no status label, authored by the trusted account | 3 | by reading, or left untracked | by reading | decision |

*Horizon by rule:* `planned` when the issue has an open blocker, else `expected`.

- **`deferred` has no mechanical target.** It said "tracked, not now", which mixed work that will be done later with work that may never be, and it hid whether the ticket needs design. Each is read. Where reading does not settle it, the fallback is `need-design` and `undecided`: the pair that keeps a session from building it on its own initiative until someone has looked.
- **A ticket in an in-flight state gets no claim from the relabel.** A claim is written from its holder's machine. The plan lists such tickets; where a live session is found to be on one, it is asked to claim it after the cutover, and otherwise the ticket returns to the backlog with a visible line saying which state, branch and pull request it had.
- **The `board:meta` block becomes visible.** Each key it carries is rewritten as a line of the body above the record block (a `note` as "Board note:", `relates-to` and `spawned-by` as mentions, a `branch` or `pr` as it stood), except a pinned `plan:`, which becomes the record's `spec:`. A `needs-human` ticket's note is its question list, so this is also what makes a `need-input` ticket say in prose what it waits on. A body that is not trusted is not rewritten (D8): its row is relabelled and its block stays as it is, hidden, until the body is adopted.
- **The retired service's banner goes.** A body that opens with the board service's mirror header ("Read-only. Edits here are reverted … The board is the source of truth") tells its reader that GitHub is not the ticket, against R1. The header is replaced by one line that keeps the old ticket's number; two open issues here carry it. Everything else in a body stays byte for byte; each rewritten body is in the plan for whoever reads it, and that reviewed text is what the apply writes.
- **Other labels are not touched**: `priority:*` and the four categories (an on-board issue without one is reported, never given one), `engine:claude`, and labels that were never the board's (`tech-debt`, the pull-request label `confident-ready`, `accessibility`, GitHub's defaults).

For this repository that is 30 mechanical rows and 23 decisions (O2).

### D7. Cutover and retirement

A repository moves in two steps.

**First, what sessions read is shipped and on the machines:** the `task` plugin with its skill; one sentence at the head of the old skill sending a repository whose binding is `task` to `task:tickets`; the old scripts' refusal of a board that has moved (below); and the skills that send work to the board (`execspec`, `decomposing`, `organizing-sprints`, a line of the sminos skill) worded for both bindings. Two of them change behavior and not only a name. `decomposing`'s optional step 6 makes tickets of a composite's children, and `organizing-sprints`' Materialization makes a ticket per epic with its slices as child tickets and parks them in old states. Under D1 each keeps one ticket per initiative (for a sprint, per epic) pointing at its section of the spec, leaves the children in the spec, and still registers as tickets what the design defers out of it.

**Then the board flips, in one sitting.** The plan is written and its decisions made; the sessions working in the repository are told through sminos; a pull request sets `"binding": "task"` (adding `.doperpowers/board.json` where there is none) and replaces the text the repository's `CLAUDE.md` carries about the board; once it merges, each clone of the repository on the owner's machines is fetched, the plan is applied and `task lint` is clean.

**What the flip does and does not fence.** From the merge on, the old scripts refuse the repository in every checkout that has the commit. That does not reach far enough alone. The old scripts run from the installed plugin whatever branch a worktree is on, and a linked worktree on a branch from before the flip still carries the old file. There the old body writer would replace a moved ticket's body and keep only a `board:meta` block, so the record block (`for:`, `due:`, `spec:`) would vanish with no label changed and `task lint` clean, and a transition would put a `status:*` label back. So the first step ships one more refusal in the old scripts: before any of them acts, it reads `.doperpowers/board.json` on the designated remote's default branch, as the clone's remote-tracking refs hold it, and refuses when that says `task`, whatever the worktree's own file says. Linked worktrees share those refs, so one fetch anywhere in a clone fences every worktree of it, which is why the flip's sitting fetches each clone. Three things stay open until retirement, when no installed plugin has the scripts: a clone that has not fetched since the flip, a clone whose refs name no default branch for the remote, and a machine whose installed plugin predates the first step. In each, an old script can still write a moved board. `task lint` fails on a `status:*` label that comes back, and `task set` takes it off as it sets the readiness; a record block erased there cannot be detected afterwards (D2), which is why the first step is on the machines before any board flips. In a worktree that still carries the old file `task` refuses as well, naming the file: a session there takes the default branch's commit, or works the board with `--repo`. In the minutes between the merge and the apply, `task` sees old-labelled issues as untracked; an issue it sets in that time is skipped by the apply and reported.

**Retirement.** The old skill stays shipped until every repository that uses it has moved or has been left on purpose (O3). Then `skills/issue-tracker/`, its tests and its two CI gates leave for `archive/issue-tracker/`, as the dormant dispatch machinery and the board service binding with them (R2). Nothing arms that machinery today, so the ruling of 2026-10-18 is unchanged by the move: what it kept in the tree and tested "armed nowhere" is kept in the archive, untested.

The four tickets that were kept off GitHub when the board service retired (`docs/doperpowers/board-service-tickets.md`) stay where they are: where a project's private tickets live is not decided here.

### D8. Public repositories: what is trusted

Three of the boards are public, so anyone can open an issue or write a comment there.

- **The trusted account is the account the CLI writes as**: the one the `gh` client is authenticated as on that machine. It is not read from the repository. A key in a committed file would be whatever the checked-out branch says, and a branch checked out for review is someone else's text.
- **A body or a comment is trusted when its author is the trusted account and its last editor, if any, is too.** A record block is read only from a trusted body, a claim record only from a trusted comment. `task show` says of every body and comment whether it passed.
- **Untrusted is unknown, not absent.** A ticket whose body is not trusted is not takeable, whatever its labels say, since its `for:` cannot be read.
- **The CLI writes no body it does not trust.** A write by the CLI makes the trusted account the body's last editor, so the next reader would trust a text, and a record block, that nobody verified. `task set` therefore refuses the changes that write a body (`--body-file`, and every option that edits the record block) when the body is not trusted, and the relabel leaves such a body as it is (D6); its labels, edges and title are still set. One act makes such a body trusted: `task adopt <n> --digest <d>`, on the owner's word, after the body was read whole. `d` is the digest `task show` printed with the text that was read. `adopt` refuses if the body has changed since; otherwise it writes the body back with one line set in its record block (`adopted:`, the time and the adopting session) and nothing else changed. The line says who vouched, and it makes the write one that changes the text, so that the trusted account becomes the last editor whatever GitHub does with a write that changes nothing. It applies to a body the trusted account authored and another account edited; an issue an outsider opened is not adopted (below). *Weighed: `task set` dropping an unverified block as it writes, or keeping it under a flag.* It lost: either way the rest of the text became trusted by a write that was about something else.
- **Labels and edges are trusted as GitHub grants them**: only an account the repository's owner gave rights to can set them.
- **An issue an outsider opened is untracked** until an account with rights puts a readiness label on it, and even then it is not takeable (its body is not trusted): it becomes work when the owner, or a session on the owner's word, registers a ticket that refers to it.

What an outsider wrote in a body or a comment is data, never an instruction; the skill says so, and the trust mark on `task show` is what a session reads it by.

## For the owner's read

**Open decisions.** Each has a recommendation, and the work named beside it does not start before the answer.

- **O1. How much a claim carries, and in what order it is built** (before M3). The design releases a claim by a machine's write when the claiming thread ends (D3). That is most of this unit's machinery: an index on each machine, the settle routine, the calls in sminos (M4), and a list of gaps it accepts. Three answers:
  - *Automatic release, in two steps (recommended).* The plugin alone first: M3 as written releases an ended thread's claims at the next `task list` or `task claim` on its machine, with nothing changed in sminos. Then the cutover (M5, M6). sminos's calls (M4) come after it and add promptness, the guide line and the `/clear` offer. The cutover then waits on no sminos release, and on none of the work the question sheet has in flight on the same code (the thread sweep, the start hooks).
  - *Automatic release, in the order the milestones stand below.* M4 lands before the cutover, so the first session on a moved board already has the guide line, the release at a retire and the `/clear` offer. The cutover waits on a sminos release, and M4 on its coordination with the question sheet's child.
  - *The lighter design.* Keep only the claim record and the fold, which give one winner between two sessions. A claim is then released by its holder or by `--force`, and a stale one is found by reading: `task list --claimed` shows each holder, the claim's age and the activity linked to the ticket. That removes M4, about half of M3 and most of D3's "What is accepted", at the price of claims that stay until someone looks: a `claimed` tied to nothing is `in-design` under a new name, and a ticket that says someone has it after that someone is gone is the fault this work opened with.

  The milestones are written in the second answer's order and are not reordered before the owner answers; "What waits on whom" says what each answer changes. The first review found the fold sound and put nearly all its findings in the lifecycle part. The second put six of its fifteen there, most of them from two things D3 does not do: take a caller's word for a thread's end, and learn a thread's identity after the claim. Neither was asked to rule on the proportion.
- **O2. Who settles the relabel's decision rows** (before M5's flip, and each repository's in M6). The relabel cannot decide 23 of this repository's 53 open tickets from their labels: 19 `deferred`, one in design, three with no status. *Recommended:* the session running the cutover reads each ticket and proposes its readiness and horizon with a one-line reason, and the owner reads that table once per repository before it is applied, because `undecided` against `expected` is the owner's knowledge and every reader trusts the labels afterwards. It costs one read of about twenty rows here (more for `cua` and `MAWS`, which have 24 and 28 `deferred`). *The cheaper path:* apply the session's proposals unread and correct by exception; a wrong `expected` would then let a session build something the owner had not decided to do.
- **O3. `ida-solution`** (before M7). It cannot be read from the owner's account today, belongs to an organization, and its checkout holds a workflow that writes `status:*` labels and one that publishes a board page. *Recommended:* leave it out of this unit, recorded by a ticket here. Its `CLAUDE.md` already tells a session not to write the board when the scripts are missing, so after M7 its board is read-only to agents until someone with access moves it by M6's steps and retires that workflow. *The alternative:* M7 waits until it has moved, which keeps the old skill shipped for a repository that has had no dispatch since August.
- **O4. Claims by sessions the MAWS app launched** (before M5's flip; moot under O1's lighter design). Such a session is not a thread, so nothing releases its claims when it is gone for good (D3). *Recommended:* accept it for the first cutover. The claim shows its age and its linked activity, and any session can take it over with a stated reason; MAWS telling the board when it archives a session is registered as a ticket for MAWS at M5. *The alternative:* this repository's flip waits until MAWS does that and it has been seen to work.
- **O5. The message of `task create --to`** (before M1 ships the flag). Registering a ticket for a named thread sends that thread one message, and sminos wakes a stopped thread for any message addressed to it. This is the one place where filing a ticket can start a process, and the ruling of 2026-10-18 says nothing starts a session from the board. *Recommended:* keep the message. It is the owner handing work to a thread they named (R10), the same act as sending that thread a message, with the ticket as its record; nothing is sent on a trigger, and without it the ticket waits unseen. *The alternative:* `--to` records `for:` and sends nothing; the session that registers the ticket tells the thread itself, or does not.

**What needs the owner's hand.** After the plugin's first release (M1 to M3 merged), `task@doperpowers` is enabled on each machine that runs sessions (`/plugin install task@doperpowers`, or the owner's word that a session may edit the settings that list enabled plugins). M4's live checks and M5 wait on it. If M1 finds another program named `task` ahead of the plugin's on some kind of machine (Delegated unknowns), M5 waits on the owner's ruling for that kind.

**Where this document goes beyond the design as discussed.** These were decided while writing or in its review, each with its reason in the section named:

- The claim's holder is kept in appended claim records, not as a fourth field of the record block; the block keeps three of the four fields and gains `for` (D2, D3).
- Each machine keeps an index of the claims it wrote, and the release at a thread's end is a routine of the plugin, `task settle`, which asks sminos whether each thread has ended and takes no caller's word for it; it runs before `task list` and `task claim` answer, and sminos starts it as well (D3, D5).
- A claim whose thread's record was purged or removed is released by no machine: sminos cannot say "deleted" apart from "not seen", so the retire prints what stays held (D3, "What is accepted").
- `claimed` is a display that every verb corrects from the fold; lists and takeability read the fold (D3).
- A `/clear` grants its successor the takeover at the moment sminos sees the `/clear`. When the thread that was left ends, its successor is not sent a message; it is shown the offer at its own starts (D5).
- A takeover without a stated reason is open only along a `/clear`; every other is forced, with its reason written (D3).
- An issue is on the board when it carries a readiness label, and an outsider's issue is never takeable (D1, D8).
- A ticket is not takeable when it is `undecided`, when a blocker was closed as not planned, or when it is `planned` with no blocker (D1).
- `deferred` has no mechanical target in the relabel, an in-flight ticket gets no claim from it, and the old labels' definitions are left for the owner to delete later (D6).
- The trusted account is the one the CLI writes as, not a value in the repository, and the CLI rewrites no body it does not trust: `task adopt` is the one act that makes an edited body trusted (D8).
- A checkout's board is the repository of one designated remote, which the committed file must agree with. The `binding` value is the cutover switch; the old scripts also refuse a board whose default branch has moved, which reaches a stale worktree once its clone has fetched (D4, D7).
- The rule that a composite's children are not tickets changes what two skills tell sessions to do: `decomposing`'s optional step 6 and `organizing-sprints`' Materialization (D7).

## Delegated unknowns

Each names the milestone that settles it and what each outcome changes.

- **Whether the confirming read of a claim sees every earlier comment** (M3). D3's arbitration assumes it, and GitHub does not document it. Acceptance 23 measures it: rounds in which five claimants, each held at a barrier after a first read that found the ticket unheld, append in competition, and each records which claim comments its confirming read saw. Five processes merely started together can run one after another and show nothing. The result is reported as a measurement (so many rounds on one day, so many confirming reads that missed a lower-numbered claim), not as a proof. With one winner in every round and no missed claim, the assumption stands as measured and D3's accepted window stays as written. A round with two winners, or any missed claim, stops M3, and the question returns to this document's author with the evidence: D3 names the other primitive, and choosing it is a design decision.
- **Blocked-by across repositories** (M1). Several `deferred` tickets wait on another repository's work, and GitHub's documentation does not say whether a dependency may cross repositories. M1 tries one edge between two scratch issues in two scratch repositories. If it holds, `--blocked-by owner/name#n` is accepted. If not, such a wait is prose in the body and the ticket is `planned` with no edge, which D1 keeps from being takeable.
- **The `gh` client from the daemon** (M4). A settle the daemon starts must reach GitHub as the owner's account from a service's environment (a launch agent on a Mac, the supervisor on a Linux host). M4 checks each kind it can reach and says which it could not. Where `gh` does not work from the service, the daemon's settle reports the board unreachable and the release waits for the settle that the next `task list` or `task claim` runs in a session on that machine (D3): late, not lost.
- **Another `task` on `PATH`** (M1). A plugin's `bin/` comes last on a session's `PATH`, and two widely installed tools (Taskwarrior, go-task) install a command of this name. None of the owner's Macs has one today. M1 runs `command -v task` and `task --version` on every kind of machine the owner runs sessions on. Where another program answers, it is reported and M5 waits on the owner's ruling for that kind of machine; the name is the owner's (R9).

## Out of scope

- **Requests to the owner and the owner's to-dos**: the Task Board (R7, R9). `task` leaves its verbs unused (D4).
- **Events and subscriptions** (R8).
- **The view of the whole picture**: which initiatives are in flight and who holds them, drawn from claims, specs and sessions. A later unit, in sminos's session manager.
- **Agents with a GitHub identity of their own.** D8 ties trust to the account the CLI writes as, which is where a second identity would be added.
- **A private repository for tickets that cannot be public** (D7).
- **The board map** (`board-map.sh`, the hosted board pages): it draws the old states and is archived with them.
- **Deleting the old labels' definitions** (D6).

## Acceptance

Each item names the milestone that proves it, and no item is proved in part by an earlier milestone: where a verb gains behavior in a later one (who holds a ticket, in what `show`, `list`, `lint` and `close` do), that behavior is an item of the later one.

**In the plugin's suite** (the `task` gate; a stand-in `gh` that keeps issues, labels, comments, edges, their authors and their times in a file and logs every call, and a stand-in `sminos`):

1. **The repository is the designated remote's** (M1). In a checkout whose `origin` is repository A and whose file names A, every call the stand-in `gh` logs, `task comment`'s included, names A, and none asks the client to resolve one. In a checkout with two remotes, `origin` for A and `upstream` for B, whose file names B: every verb that works a board exits 1 naming both repositories, and the log holds no call. The same checkout with `git config task.remote upstream`: the calls name B. A file naming a repository no remote has, and a designated remote whose URL is no GitHub repository: exit 1. With `--repo R`, run inside that two-remote checkout and outside any checkout: every logged call names R, and the configuration is read from R's default branch. Without the file, or with a `binding` other than `task`, every verb that works a board exits 1 naming the file and the binding it found. In a linked worktree without the file, the main checkout's is read. `task --help` and `task --version` run in a directory that is no repository.
2. **Create** (M1). Without a category, a priority, a readiness or a body: exit 2. With them, the issue carries exactly one readiness, one horizon (`expected` unless given), the priority and the category; its body ends with a record block whose `registered-by` is the stand-in's address, and has none when no session id is set. `--blocked-by` and `--parent` write native edges, and the readiness label is the last write in the log; when the stand-in refuses the edge, the issue has no readiness label and the output says it was left untracked. `--to` a thread sminos resolves writes `for:` and sends exactly one `sminos say`; when the send fails the ticket exists and the output carries the line to send; `--to` a name sminos does not resolve exits 1 and no issue is created.
3. **Set, edge and close** (M1). After any sequence of `task set`, a ticket has exactly one readiness and one horizon, and the log shows single-label adds and removes, never a replacement of the whole label set. Setting a readiness on an issue that carries a `status:*` label takes that label off. `--body-file` reads the body again before it writes and leaves a trusted record block byte for byte. `--due` and `--spec` change only the block. `task edge` refuses a self-edge and an edge that would close a blocked-by cycle (exit 3). `task close` closes the issue as completed, and as not planned with `--not-planned`.
4. **Read** (M1). `task list --json`, `show --json` and `search --json` give the shapes of Interfaces §5, with `holder` null. `task list --takeable` holds exactly the tickets that meet D1's conditions 2 to 6, with one absent case for each way of failing, each naming its reason in `not_takeable`: two readiness labels; `undecided`; an open blocker; a blocker closed as not planned; `planned` with no blocker; an untrusted body; `for:` another thread. `task list --untracked` shows an issue another account opened that carries only `bug`.
5. **Trust** (M1). The trusted account is the login the stand-in `gh` is authenticated as, and an `account` key in the configuration changes nothing. A record block in a body whose author, or last editor, is another account is not read, and `task show` says so. On a body the trusted account authored and another account edited, `task set` with `--body-file`, `--due`, `--spec` or `--to` exits 3 and the log holds no write, and the `task show` after it still marks the body untrusted and reads no record; `task set --readiness` on the same ticket writes its label. `task adopt` with the digest that `show` printed writes the body back with an `adopted:` line in its record block and nothing else changed, and the `task show` after it marks the body trusted and reads the record; with the digest of an earlier text it exits 3 and writes nothing; on an issue another account opened it exits 3.
6. **Lint** (M1). Each FAIL of Interfaces §6 and each WARN that needs no fold, one case each, and an untracked issue with a category label raises neither; exit 3 on any FAIL; the log holds no write.
7. **The seam** (M1). `task assign-human` exits 2 and says the Task Board is not built.
8. **Migrate** (M2). Over a fixture that holds every old label of D6's table, an unlabelled issue the trusted account authored, an issue another account authored that carries `bug`, a body with a `board:meta` block, a body with the retired service's banner, a body with a `board:meta` block that another account last edited, an issue already on the board whose body still holds a `board:meta` block, and a closed issue with a status label: `plan` runs on a board whose binding is not `task`, marks each row mechanical or decision as the table says, records for each what it read (§8's `seen`), and lists the outsider's issue as incoming. `apply` exits 1 on a plan made for another repository and exits 3 while a decision row is undecided. After it, every row's issue has one readiness and one horizon and no status label; each `board:meta` key of a trusted body is a visible line, a pinned plan is the record's `spec:`, the banner is replaced, and the rest of each body is unchanged; the body another account edited is byte for byte as it was, and `task show` still marks it untrusted; the issue already on the board has its body rewritten and no label written; the outsider's issue, a row decided "leave", the closed issue and every label definition are as they were. For a row that rewrites a body, the stand-in is made to fail after each of the row's writes in turn (the body, the horizon label, the readiness label, the old status label's removal): after each, a second `apply` finishes that row from where it stood and the log shows no write repeated. A row found with its labels at target and its body still at the source is not done: `apply` writes the body. A further `apply` logs no write. An issue changed after the plan is skipped and named, once for each kind of change: its body edited (the plan's `body_after` is not written over the edit), the issue closed, a blocker closed, a board label moved. An issue opened after the plan with an old status label is named in the closing list.
9. **The fold** (M3). Each cell of D3's table, and: a closed ticket is unheld; a reopened ticket is unheld; a `claim` whose comment was created while the ticket was closed does not hold it after a reopening; a `claim` dated the second of the last reopening does not hold it, with the stand-in placing the comment before the reopening and after it; a `task-claim` comment written by another account, or last edited by one, changes no holder.
10. **Claim** (M3). An unheld ticket: exit 0, and in the log's order the question to sminos about the session's thread, a pending row with its attempt token, the `claim` record carrying that token, the confirming read, the label write and the look after it, the row held with its thread id and the record's id. A held one: exit 3 naming the holder, its age and the linked activity. A rival claim the stand-in inserts between the read and the append: exit 3, the loser's own comment deleted, its row removed, and the label left agreeing with the fold. Its own record void with no holder (the same-second tie): the record deleted and one more claim made, which holds. A ticket this session's thread already holds: exit 0, "already yours", no new record. A ticket whose `for:` names another thread: exit 3. A ticket that is not takeable: claimed, with the failing condition printed. No address from sminos: exit 1. The thread question unanswered, answered with exit 4, or answered for another session than the one claiming: exit 1, with no row and no record written. An answer with an empty `thread`: the row's thread is empty. The process killed after the append: the next settle adopts the record that carries the row's token, on a ticket that also holds an earlier, released `claim` of the same address. `task claim --batch NAME` claims the batch's open tickets one by one and prints which were won.
11. **Release, close and the label** (M3). `task release` by the holder: the `release` record with `reason: released`, then the label made to agree; the row removed. By another session: exit 3 without `--force`; with it, `reason: forced: <text>`. `task close` by the holder closes the ticket, takes the label off and removes the row; of a ticket another thread holds it exits 3 without `--force`. Two releases of one claim interleaved with a new claim, in the order the stand-in forces (the second release reads the ticket unheld, the new claim is made and labelled, then the second release writes the label off): its look after the write finds the new holder, and the label ends on. A writer killed between its record and its label: the label is wrong until the next `task list`, which writes it.
12. **Takeover** (M3). With a `successor` grant for this session: exit 0, and in the log's order the question about the session's thread, a pending row with its token, a `takeover` with `reason: cleared` naming the current claim and carrying the token, the confirming read, the label, the row held; the left thread's row lapsed. Without a grant: exit 3 unless `--force`, whose text is the reason. A takeover whose named claim is no longer current is void, deleted and reported, and its row removed. The process killed after the append: the next settle adopts the takeover into its pending row.
13. **Holders in what is read** (M3). `task show` and `task list` give §5's `holder` from the fold. A ticket whose fold names a holder and whose label is off: both name the holder, `--takeable` leaves it out with `held` in `not_takeable`, and the label is written on. A ticket with the label and no holder in the fold: both give no holder, `--takeable` holds it, and the label is taken off. `task lint` reports each of the two as a WARN and writes nothing.
14. **Settle** (M3). (a) A row whose thread sminos says has ended, by an answer carrying that very thread id with `local` and `ended` true: the `release` with `reason: ended`, the label made to agree, the row lapsed. (b) An answer that carries another thread id, `local` false or `ended` false: nothing written, and for the first two the row in `unknown`. (c) Exit 4 for the row's thread id, as after a purge: nothing written, the row in `unknown` with what sminos said. (d) `--thread T` settles T's rows and no others, and asks sminos about T as any settle does: a T that has returned by then keeps its claims, the one it made since included. (e) A row whose ticket is closed: label off, row removed. (f) No answer from sminos: nothing written, the row in `unknown`. (g) GitHub failing: `owed` above zero, and a second settle, or the next writing verb run on the machine, writes the release exactly once. (h) The process killed after the release was accepted and before the row was marked: the next settle marks it lapsed with `reason: ended` and writes no second release. (i) A row with an empty thread is never released by settle, and sminos is not asked about it. (j) A row whose claim another session took over: lapsed, and the label left agreeing with the later holder. (k) A held row whose ticket has lost its label: the label put back. (l) Rows on two boards, one of which the stand-in refuses: the other's rows are settled and the refused board is reported. (m) A pending row: its record found by the token and named by the fold, the row held; found and void, the record deleted and the row dropped; not found, the row kept until it is an hour old and then dropped. (n) Before `task list` and `task claim`: with the last settle more than ten minutes old the verb settles first, and a ticket whose holder's thread has ended is listed unheld; within ten minutes no settle runs; two verbs started together run one settle; a settle that fails does not fail the verb. (o) All of it run from a directory that is no repository.
15. **Held** (M3). `task held --session S --thread T --json` lists T's held rows, T's lapsed rows that are less than seven days old (on every call, not once) and, as offered, the held rows whose `successor` is S. With `--cleared-from L` it first sets `successor` to S on L's held rows and on no other thread's. It answers with the stand-in `gh` failing every call, and from a directory that is no repository. `task list` and `task claim` end with a line for each lapsed row, less than seven days old, that the calling session made.

**In sminos's suite** (the `sminos` gates, with a stand-in `task`):

16. **The guide** (M4). A thread's session start makes one `held` call with its session and thread and prints the line built from what is held, lapsed and offered; nothing held, lapsed or offered prints no line. With no plugin, one below the floor, one that exits non-zero and one slower than the bound, the start prints no board line and takes no longer than the bound.
17. **The `/clear` grant** (M4). A start whose source is `clear`, with the note of the session left in place and that session the current one of a thread of this machine: the `held` call carries `--cleared-from <that thread's id>`, and the guide prints that `task takeover <n>` takes a ticket over. It does so with the guide's hook run before the record hook and after it, when the session left has already given up its name, and for a session left that is unnamed. A note older than sminos believes it, a session left that is no thread, and a start of any other source: no `--cleared-from`.
18. **Retire** (M4). For a thread its human opened and a spawned one: `settle --thread <id>` is called once, after the end's transition has returned, with no argument that states an end, and what it released is printed. For a purge of each, and a `remove`: the same call, and each ticket the answer lists as unknown for that thread is printed with the command that releases it. A plugin that fails or is slower than the bound does not fail the retire, which says the board gave no answer.
19. **The ending pass** (M4). Each pass starts one `settle`, never a second while one runs, and does not wait for it; a change in the count of owed or unknown rows is logged.

**In the old scripts' suite** (the `issue-tracker` gate, while the scripts ship):

20. **The old scripts refuse a moved board** (M5). In a fixture clone whose worktree's file says `gh`, or that has none, and whose remote-tracking ref for the designated remote's default branch holds a file saying `task`: `board-body.sh`, `board-transition.sh` and `board-list.sh` exit non-zero with the line of M5, and the stand-in `gh` logs no call. With that ref's file saying `gh`, with no file there, and with no such ref, the scripts run as before.

**Live, on scratch repositories** (`bash task/tests/live.sh <case>`, run with the worktree's own launcher against real GitHub; `TASK_LIVE_REPO` names a private scratch repository):

21. `fork` (M1): in a scratch clone whose `origin` is the scratch repository and whose `upstream` is another project, with no default recorded, `gh repo view` names the upstream project and `task list` lists the scratch repository's tickets. The case only reads.
22. `migrate` (M2): the scratch repository is seeded with one issue for each row of D6's table; `plan`, the decisions and `apply` leave `task lint` with no FAIL there, and a second `apply` writes nothing.
23. `race` (M3): twenty rounds, each on one fresh ticket. In a round five `task claim` processes run at once, each with a session id, a thread id and an address of its own from the stand-in `sminos`, and an index of its own. Each is held at a barrier after its first read has found the ticket unheld, and the five are let go together, so that every round has five appends made in competition; a round in which any claimant did not reach the barrier is run again and not counted. Each claimant records which claim comments its confirming read saw. The case prints, as a measurement: the rounds, the exit 0s in each, and the confirming reads that missed a claim comment with a lower id than the reader's own. Twenty rounds with one exit 0 each, no missed comment, and a fresh `task show --json` naming each round's winner is the result on which M3 goes on.
24. `lapse` (M3): on a machine whose sminos makes no call to the plugin, a spawned thread claims a scratch ticket with the worktree's launcher and is retired. A `task list` run afterwards in another session of that machine, the settle interval set short, lists the ticket unheld, and the ticket shows a `release` with `reason: ended` and no `claimed`.

After M4's release is on a machine where the plugin is enabled (run by the session that holds this spec):

25. `end` (M4): a spawned thread claims a scratch ticket and is retired: the retire prints the ticket, which then shows a `release` with `reason: ended` and no `claimed`. With `SMINOS_THREAD_END_AFTER` set short on a test home, a stopped thread's claim is released by the daemon's pass. A spawned thread that claims and is then removed: the remove prints the ticket as still held, with the command that releases it.
26. By hand (M4), in an interactive session that holds a claim on a scratch ticket: `/clear`; the new session's guide names the ticket; `task takeover <n>` there exits 0 without `--force`; from a third session it exits 3.

**Receipts**, each taken once when its act is done and recorded in Progress with its evidence:

27. This repository's flip (M5): the plan's counts before; after, `task lint` prints no FAIL, no open issue carries a `status:*` label, a ticket that had a hidden note shows it on its page, and the two issues that opened with the retired service's banner no longer say they are read-only.
28. An old script against this repository after the flip (M5): from a linked worktree on a branch that predates the flip, whose own file still says `gh`, after one fetch in that clone, `board-list.sh` and then the old body writer (`board-body.sh`), both from the installed plugin, exit non-zero with the line of M5. The body writer is aimed at a ticket registered for this check, whose body and record block are read unchanged afterwards.
29. The skill's pressure tests (M5): each scenario M5 lists, run without the skill and with it, recorded in the pull request that carries the skill.
30. After the first step of the cutover reaches a machine, a fresh session there lists `task:tickets`. After each board's flip, the first ticket a session registers there with `task create` is named (M5 for this repository, M6 for each sibling).
31. Each sibling repository moved in M6: `task lint` there prints no FAIL, no open issue carries a `status:*` label, and its `CLAUDE.md` holds no "Board Write Hard Gate".

**Final, at M7**, repeatable:

32. `skills/issue-tracker/` is gone and `archive/issue-tracker/` holds it. No shipped skill, agent definition, `CLAUDE.md`, `README.md` or `docs/whats-inside.md` names `doperpowers:issue-tracker` or a `board-*.sh` as something to run; dated documents under `docs/doperpowers/` are not rewritten.
33. `ci-gate` on the last branch is GREEN with no `issue-tracker` or `board-api` gate, and `ci-gate --gates task` passes on it.
34. `task lint` on each moved board, which only reads, prints no FAIL.

## Execution

**Verification.** Two independent reviews of this spec: `doperpowers:adversarial-reviewer` on the design and, the execution section having several milestones, on its buildability in the same round; then a second reviewer on the repair of that round. Each pull request is reviewed through `doperpowers:review-code`: the plugin's (M1 to M3) and sminos's (M4) at the high rung (`doperpowers:reviewer-high`), the first because it carries an arbitration rule and a trust rule for public repositories, the second because it touches the thread sweep, the retire paths and the start guide; M5's and M7's at the medium rung. M6's pull requests follow their own repositories' review.

**How it lands.** Not as one branch. M1 to M3 are one branch and one pull request, the plugin's first release. M4 is its own branch, cut from `main` when it starts, and a sminos release. M5 is two small pull requests here (what sessions read, with the old scripts' refusal; then the flip) and a live relabel. M6 is one pull request in each sibling repository. M7 is one pull request here. A `doperpowers:plan-executor` can run M1 to M3 as one branch from this document, and M4 as another; M5 to M7 act on live boards and on other repositories and wait on the owner's answers, so the session that holds this spec runs them.

**What waits on whom.** O1 before M3 starts, and its answer also says where M4 stands:

- *Two steps.* M5 and M6 start once the plugin's first release (M1 to M3) is enabled on the machines; M4 runs after them or beside them and gates nothing. Between a board's flip and M4's release, a claim of an ended thread is released at the next `task list` or `task claim` on its machine and not at the retire (on a machine where no session runs `task`, not at all), a thread that returns reads what lapsed from `task list` and not from its guide, and a takeover after a `/clear` is forced, with a reason. Acceptance 25 and 26 are taken when M4's release is on a machine, the boards having moved.
- *The milestones' order.* M5 starts once M4's sminos release is on the machines, and M4 is agreed with whoever holds the question sheet's child before it branches.
- *The lighter design.* M4 and the lifecycle half of M3 are dropped (the index, `held`, `settle`, the settle before `list` and `claim`); acceptance 14 to 19 and 24 to 26 go with them, as does the index's part of 10 to 12, and this document is revised before M3 is built.

O5 before M1 ships `--to`. The plugin enabled on the machines before M5 and before M4's live checks. O2 and O4 before M5's flip. O3 before M7.

**Binding on every milestone.**

- This repository is public: no hostnames, IPs, accounts, project ids, secret names or values, or local absolute paths in code, comments, committed fixtures, documents or commit messages. Fixtures use invented addresses, as this document's examples do. Nothing about a private repository's issues, or about the inside of a repository the owner's account cannot read, is written here or on this board.
- The `task` plugin is Python 3.9, standard library only, as sminos's CLI is; it imports nothing of doperpowers or sminos, and reaches GitHub only through `gh api` with the repository named in the call.
- No issue or label of a real board is written before M5's flip. M1 to M4 run against the stand-ins and scratch repositories.
- No machine sends a thread a message because of a ticket; the one message this unit sends is `create --to`'s, by a session, if O5 keeps it.
- Verify a commit with `ci-gate` from the worktree (`ci-gate --gates task` for the plugin's suite); do not run a gate's command locally as the verification. One focused test file while iterating is fine.
- Versions move in the commit that changes a shipped file: `scripts/bump-version.sh --plugin task` (the plugin is created at 0.1.0; a new plugin directory with readable manifests passes the `version-bump` gate), `--plugin sminos` in M4 and wherever the sminos skill's text changes, doperpowers' own in M5 and M7.
- A new plugin reaches a machine by the owner enabling it there once; after that the marketplace updates it by version number.
- Skill text (M5's new skill and its changes to four others, M7's removals) goes through doperpowers:writing-skills.
- A Repo map row in the root `CLAUDE.md` orients in a sentence or two; the plugin's detail is in `task/CLAUDE.md`. `README.md` and `docs/whats-inside.md` follow the tree in the same change.
- Dated documents under `docs/doperpowers/` are history and are not rewritten; `docs/doperpowers/board-service-tickets.md` stays as it is.

### M1 — the `task` plugin and the ticket verbs

**At its end:** `task` runs from the plugin's `bin/`. Against a board whose binding is `task`, `create`, `show`, `list`, `search`, `set`, `adopt`, `edge`, `comment`, `close` and `lint` behave as D1, D2, D4 and D8 say, in everything but who holds a ticket, which M3 builds. The marketplace lists the plugin and CI runs its suite.

**Touches:** `task/` (new: `.claude-plugin/plugin.json`, `bin/task`, `cli/`, `tests/` with `run.sh`, `live.sh` and the two stand-ins, `CLAUDE.md`); `.claude-plugin/marketplace.json` (the plugin's entry); `.version-bump.json` (a `task` plugin with root `task`, its two version files and `unshipped` as sminos lists them; `task` added to doperpowers' `audit.exclude`); `.github/ci-kit.yml` (a `task` gate running `bash task/tests/run.sh`, on `task/**`); the root `CLAUDE.md` (a Repo map row for `task/`, and `--plugin task` where the other plugins' flags are named).

**Interfaces:** exposes §1, §2, §3, §5 with `holder` null, and §6 without the WARN that needs the fold. Consumes §10 (the address for `registered-by` and `adopted`; the thread and the message of `--to`).

**Decisions:**

- All GitHub access sits in one module. `skills/issue-tracker/scripts/_board.py` (its snapshot query, its edge mutations) and `tests/issue-tracker/mock-gh/gh` show what the API takes and how a stand-in keeps state; they are references, not code to import or extend.
- Label writes are single-label adds and removes. A replacement of the whole set would drop a `claimed` another writer set a moment before.
- The trusted account is read from the `gh` client once per run (the authenticated login).
- `create` refuses an empty body and enforces no sections: what a body must carry is the skill's (M5). It writes a record block only when it has a key to put in it.
- A new label is created at first need, with a description that names its axis.
- `task --version` prints the version and that it is the task plugin of the doperpowers marketplace (the unknown about another `task` on `PATH`).
- sminos is found as devcloud finds it (`_sminos` in `devcloud/driver/context.py`): `TASK_SMINOS`, then `PATH`, then the marketplace clone; each call bounded at 30 seconds. The address is read from `sminos who`'s line as devcloud's `session_creator` reads it.
- The cross-repository edge is tried first, on two scratch issues in two scratch repositories (`TASK_LIVE_REPO`, `TASK_LIVE_REPO2`), and its verdict written under Delegated unknowns.
- Nothing in this milestone reads the `claimed` label or a claim record, and none of its acceptance items is about a holder: `show` and `list` give `holder: null`, takeability is D1's conditions 2 to 6, and `close` asks nothing about a holder. M3 adds the fold to each of them and proves it there.
- The designated remote is `git config --get task.remote`, else `origin`. Its repository is read from the remote's URL in the forms git writes a GitHub repository (`https://github.com/owner/name`, `git@github.com:owner/name`, `ssh://git@github.com/owner/name`, with or without `.git`) and compared with the file's `repo` without regard to case; any other URL is refused.
- A body's digest is `sha256:` and the hex SHA-256 of the body's bytes as the API returns them, the same in `show`, `adopt` and M2's plan.
- If O5 is answered against the message, `--to` writes `for:` and sends nothing, and acceptance 2's send is dropped.

**Does not touch:** `migrate` (M2); `claim`, `release`, `takeover`, `held`, `settle`, the fold and the index (M3); the skill (M5); the `issue-tracker` skill and its scripts; sminos's code; any issue of a real board.

**Proves:** acceptance 1 to 7 and 21; the two unknowns it names.

### M2 — the relabel tool

**At its end:** `task migrate plan` and `task migrate apply` relabel a board as D6 says, and have done so once on a scratch repository against real GitHub.

**Touches:** `task/cli/`, `task/tests/`.

**Interfaces:** exposes §8. Consumes §1, §2 and §3.

**Decisions:**

- A row's state is read at apply time from the issue itself (its labels, its body's digest and its blockers, against §8's `seen`), never from a timestamp: the tool's own first write would change it.
- No label definition is deleted, and nothing on a closed issue or a pull request is written.
- The plan is written outside the repository's tree, readable by its owner only.
- The retired service's banner is recognized by its exact header lines and nothing looser; a body that does not match is not touched.
- Each rewritten body is carried in the plan (`body_after`), so that what the apply will write can be read first. The apply writes that text and computes none: a rewrite made again at apply time could differ from the one that was read.
- `apply` needs binding `task` in the checkout like every writing verb, so it cannot run on a board the old scripts still own.

**Does not touch:** any real board; claims.

**Proves:** 8 and 22.

### M3 — claims

**At its end:** `task claim`, `release`, `takeover`, `held` and `settle` behave as D3 says, with the real sminos for identity. `show` and `list` name holders from the fold and correct the label, and `close` respects a holder. A claim whose thread has ended is released by the settle that runs before the next `task list` or `task claim` on its machine. No sminos code calls the plugin yet, and none is needed for that.

**Touches:** `task/cli/`, `task/tests/`, `task/CLAUDE.md` (the contract with sminos in both directions, which is where its detail lives).

**Interfaces:** exposes §4, §7 and §9, §5's `holder` and §6's WARN that needs the fold; §9 is frozen at this milestone's review, since M4 builds against it. Consumes §1 to §3 and §10.

**Decisions:**

- It starts once O1 is answered. Under the lighter design this milestone is the record, the fold, `claim`, `release`, `takeover --force` and the holder in `show` and `list`; the index, `held` and `settle` are not built, and this document is revised first.
- Acceptance 23 is run first. A round with two winners, or a confirming read that missed a lower-numbered claim, stops the milestone (Delegated unknowns). Its barrier and its trace are test seams of `claim`, off unless their variables are set: `TASK_CLAIM_BARRIER` names a file the claim waits for, at most a minute, after a first read that found the ticket unheld, and `TASK_TRACE` a file that receives what each of its reads saw.
- The index is one JSON file, rewritten by atomic replace under a lock held across the read and the write: several sessions of one machine claim at once. The lock is never held across a call to GitHub or to sminos.
- Inside `claim` and `takeover` the order is: the session's thread asked, pending row, read and fold, append, read and fold, the label and the look after it, row held. Inside a release: record, the label and the look, row. Inside a settle's release: row owed, record, the label and the look, row lapsed. Each order is what makes the crash cases of acceptance 10, 11, 12 and 14 come out as written.
- The thread comes from `who --thread=<the session's own id>`, taken only when the answer's `session` is that id and `local` is true: a thread id, or an empty `thread` (the session is no thread). Anything else, exit 4 included, is no answer, and the verb exits 1 (D3).
- The attempt token is sixteen hex digits from the system's random source, minted for each try and derived from nothing.
- The settle before `list` and `claim` takes its turn under the index's lock: the time of the last settle is in the index and is written before the settle starts, so two verbs started together run one. It is bounded at 20 seconds; its failure goes to stderr and fails nothing. `TASK_SETTLE_EVERY` (seconds) replaces the ten minutes, for tests.
- `list` reads a board's open tickets with their comments in one paged query and folds each; a ticket with more comments than one page holds is read on.
- Settle asks sminos once for each distinct thread id among its rows, each question bounded as M1's are.
- A board the settle cannot reach, or whose `gh` call fails, is reported in the answer and does not stop the other boards' rows.
- A lapsed row is dropped once it is seven days old, at any settle or `held`. The lapsed rows `list` and `claim` report for the calling session are matched by its session id, which needs no question to sminos, and go to stderr, one line each, outside `--json`.

**Does not touch:** sminos's code; any real board; the skill.

**Proves:** 9 to 15, 23 and 24.

### M4 — sminos calls the board at a thread's start, `/clear` and end

**At its end:** a thread's start guide lists what it holds, what lapsed and what is offered to it. After a `/clear`, the new session is told what the conversation it left holds and can take it over without force. A retire releases the retired thread's claims as it returns and prints them; after a purge or a remove it prints what stays held. The daemon's ending pass starts a settle, so a thread the three-day rule ends loses its claims within that pass, on a machine where no session runs `task` as well.

**Touches:** `sminos/skills/sminos/scripts/sminos_threads.py` (finding and asking `task`, beside `find_devcloud` and `owned_by`), `sminos_daemon.py` (the ending pass of `sweep_threads`), `sminos.py` (the guide, and in it the grant at a `/clear`, read from `cleared_from`; the retire and remove commands, after `end_human`, `end_seat` or `end_and_stop` has returned); `sminos/tests/` (a stand-in `task`, as `devcloud_standin.py` stands in for devcloud, and the cases); `sminos/skills/sminos/scripts/CLAUDE.md` (a paragraph on the contract); the sminos version.

**Interfaces:** consumes §9. Exposes nothing: sminos gains no verb and no output key (D5).

**Decisions:**

- This milestone is for whoever holds sminos when it starts. Before branching, read what is in flight on the thread sweep, the retire paths and the start hooks, and tell its holder. At this writing that is the question sheet's sminos child (`docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`), which adds a sweep of its own to the daemon and changes the start hooks. The channels composite is not amended: every child of it has landed, and this is a change of its own to code it landed.
- Every call to settle is a trigger (D3). sminos passes nothing that states an end, and nothing in sminos depends on a call having been delivered or answered.
- The retire's call sits in the retire and remove commands after the end's transition has returned, never inside `thread_transition` and never under a thread's lock: the end and a purge are one journaled transition there, and the plugin asks sminos about the thread while it runs. It is bounded at 30 seconds. A session that retires or removes itself is stopped by its own end before the call is made; the next settle on the machine does that work.
- The grant at a `/clear` is made by the guide from `cleared_from`, the note of the session left, and not from `cleared_witness`. That one answers only while the session left still holds the name its process goes by: the record hook takes the name from it, nothing fixes which start hook runs first, and an unnamed session never has one, so a grant read from it would be made on some starts and not on others. The guide resolves the session left to the thread whose current session it is (one its human opened, of this machine, not ended) and passes that thread's id; a session left that is no such thread gets no grant. The suite runs the guide's hook before the record hook and after it, and with a session left that is unnamed (acceptance 17).
- The floor, `TASK_MIN`, is the plugin's first released version that has §9.
- The guide's call is bounded at two seconds, and a board line is printed only when something is held, lapsed or offered. The call passes the session id always and the thread id when the session has a thread record by then.
- The settle the daemon starts is run as the census is (the child process the ending pass starts to ask devcloud which threads own a machine: `start_census` in `sminos_daemon.py`): bounded, one at a time, and never waited for by the tick.
- Whether `gh` reaches GitHub from the daemon's environment is checked on each kind of machine within reach and written under Delegated unknowns.
- sminos reads nothing of the plugin's files, and the plugin nothing of sminos's.

**Does not touch:** the three-day rule's own decision (`end_due`, the census, `end_by_rule`'s guard); `who` and `who --thread`; `cleared_witness` and the hand-over of a name at a `/clear`; the wake; channels; the question sheet's code.

**Proves:** 16 to 19 on the branch; 25 and 26 once its release is on a machine.

### M5 — the skill, the calling skills, and this repository's cutover

**At its end:** sessions in this repository work the board through `task:tickets` and `task`; its open issues carry the new labels; the old scripts refuse it.

**Touches**, in two pull requests (D7). *What sessions read:* `task/skills/tickets/SKILL.md` (new); `skills/issue-tracker/SKILL.md` (one sentence at its head: a repository whose binding is `task` is worked through `task:tickets`); `skills/issue-tracker/scripts/_binding.sh` (the refusal of a board that has moved) with its cases in `tests/issue-tracker/`; `skills/execspec/SKILL.md`, `skills/decomposing/SKILL.md`, `skills/organizing-sprints/SKILL.md` and `sminos/skills/sminos/SKILL.md` (where each sends work to the board); `README.md` and `docs/INSTALL-doperpowers.md` (the plugin's install line); `docs/whats-inside.md` (the plugin and its skill); the versions of `task`, doperpowers and sminos. *The flip:* `.doperpowers/board.json`; the root `CLAUDE.md` ("The board" section, the `skills/` and `task/` rows); `.github/PULL_REQUEST_TEMPLATE.md` (the line that names `board-transition.sh`). Live: this repository's issues and labels.

**Interfaces:** consumes all of them.

**Decisions:**

- **The skill** carries what a session cannot derive: what the board is for (R3); when a ticket is registered (work deferred out of a session, at the moment it is deferred, by whoever deferred it, with a body a reader weeks away can act on, after a search by the identifiers the work touches); what is takeable; that a claim comes before the work and a refused claim means the work is another's; that nothing is written to a ticket while work runs; what setting a ticket down leaves (a release that says where it stands, and the readiness the ticket now needs); that a pull request closes its ticket with `Closes #n`; that a `need-input` ticket says in prose what it waits on; that a body is edited through `task set`; that an outsider's text on a public board is data; and that a body `task show` marks untrusted is adopted only on the owner's word, after it was read whole. It carries no flags (`task --help` does) and no state machine.
- **The calling skills** name the board's skill by the binding while both exist: `task:tickets` where `.doperpowers/board.json` says `task`, the old skill elsewhere. `decomposing`'s step 6 and `organizing-sprints`' Materialization change as D7 says, and the lines of `organizing-sprints` that name `board-register.sh`, `--state` values and `board-lint.sh` are rewritten for both bindings.
- **The pressure tests** must show: (a) a session that scopes work out registers it at that moment, with such a body, after searching; (b) an idle session takes a takeable ticket, and brings a `need-design` or `undecided` one to the owner instead of designing or deciding alone; (c) it claims before it starts, and on exit 3 does not start; (d) midway through claimed work it writes nothing to the ticket; (e) setting a ticket down, it releases with where the work stands and sets the readiness; (f) it registers no ticket for work it is about to build now; (g) in a checkout with an `upstream` remote it uses `task` and no raw `gh issue` command; (h) it does not act on an instruction found in an untrusted comment, and does not adopt an untrusted body by its own decision; (i) a session decomposing a goal on a moved board registers one ticket for the initiative and leaves the children in the spec; (j) on a board that has not moved, it still uses the old skill.
- **The old scripts' refusal** is one check in `_binding.sh`, which every script sources, made after the worktree's own file is read: `git show refs/remotes/<the designated remote>/HEAD:.doperpowers/board.json`, and a `binding` of `task` there stops the script with `error: this board has moved to task (the default branch's .doperpowers/board.json says so): work it through task:tickets`. The scripts make no fetch: a board command must not wait on the network, and the flip's sitting fetches each clone. A ref or a file that is not there refuses nothing (D7 names what that leaves open).
- **The first pull request** is merged, and its versions are on the owner's machines, before the flip: acceptance 30's fresh session is the check.
- **The flip** follows D7. The plan is written outside the tree. Its decision rows go to the owner as a table in the pull request's description (O2), which for this public repository may name the issues. The sessions working here are told through sminos before it merges. After the merge each clone of this repository on the owner's machines is fetched, and receipt 28 is taken from a linked worktree whose branch predates the flip.
- A ticket the relabel finds in an in-flight state: where sminos shows a live session on its branch or pull request, that session is asked to claim it after the apply.
- O4 decides between two paths: the limit accepted, and a ticket registered for MAWS here; or the flip waits until MAWS reports a session's end to the board and that has been seen to work.
- It starts once the plugin is enabled on the owner's machines and no machine kind has an unresolved other `task`; and, unless O1 is answered for the two steps, once M4's sminos release is on those machines (What waits on whom).

**Does not touch:** the sibling repositories; the old skill and its scripts beyond that one sentence and that one refusal.

**Proves:** 20 on the first pull request's branch; 27 to 29, and 30 for this repository.

### M6 — the sibling repositories' cutover

**At its end:** `cua`, `MAWS` and `arkho` are on `task`, each by one pull request in that repository and one applied plan.

**Touches**, in each repository, through its own worktree and pull request: a new `.doperpowers/board.json` with `"binding": "task"` and that repository's `owner/name`; the text its agent instructions carry about the board. In `cua` that is the "Board Write Hard Gate" bullet of its `CLAUDE.md`, replaced by one sentence that the board is worked through `task:tickets`. `MAWS` and `arkho` hold no such text; a search for `issue-tracker` and `board-` at the cutover finds what there is. Live: their issues and labels.

**Interfaces:** consumes all of them.

**Decisions:**

- Before a repository's pull request opens, the threads in charge there are told through sminos what changes and when, since sessions working there read the labels. The plan is applied in the same sitting as the merge, after each clone of that repository on the owner's machines has been fetched, as in M5.
- `cua` and `MAWS` use native edges: the horizon rule of D6 applies, and parents keep their children.
- `arkho` is private. Its plan and its decision table never enter this repository or a public pull request.
- Each repository's decision rows go to the owner per O2. Each plan is checked for the retired service's banner.
- Another checkout of the same repository on another branch gets the change when its branch takes the default branch's commit. Nothing is edited there.
- `ida-solution`, per O3. Left out: a ticket on this board records it, saying what kind of text waits there (its agent instructions, one of its runbooks, two workflows that speak the old vocabulary) and naming none of that repository's files. Moved: by these same steps, by a session whose account can read it, with the workflow that writes `status:*` labels retired in the same pull request.

**Does not touch:** this repository, beyond Progress.

**Proves:** 31, and 30 for each repository.

### M7 — the old scripts retire; the final verification

**At its end:** doperpowers no longer ships the `issue-tracker` skill, what referred to it refers to `task:tickets` alone, and the final checks have passed.

**Touches:** `skills/issue-tracker/` moves to `archive/issue-tracker/` (the skill, its scripts and references), with `tests/issue-tracker/` and `tests/claude-code/board-api/` beneath it, unwired; `.github/ci-kit.yml` (the `issue-tracker` and `board-api` gates, and those paths where other gates list them); `tests/claude-code/run-skill-tests.sh` and any test that reads the moved paths; `archive/CLAUDE.md` (what it was, and that `task:tickets` holds its surviving rules); the root `CLAUDE.md` ("The board" section; the `skills/` row and its count); the four calling skills (the old binding's branch removed); `README.md`, `docs/whats-inside.md`; `.gitignore` (the old render cache); `application-agents/triaging-feedback/` and `infra/` (the paths their documents give for the scripts, which then point into the archive; neither runs anywhere today); the versions of doperpowers and sminos.

**Interfaces:** none.

**Decisions:**

- It starts when `cua`, `MAWS` and `arkho` have moved (acceptance 31 recorded for each) and O3 has been carried out: the ticket that records leaving `ida-solution` out exists, or that repository has moved.
- Archived tests stay with what they test and are run by nothing, as `archive/experimental-context/` keeps its own.
- The final verification is acceptance 32 to 34 together with the suites (1 to 19, by `ci-gate`) and the scratch cases (21 to 24). The acts that happen once (27 to 31, and 25 and 26) are not repeated: their receipts in Progress are read and cited. Item 20 leaves with the scripts it tests, and its last passing run before the archive is cited.

**Does not touch:** the `task` plugin's behavior; any dated document under `docs/doperpowers/`.

**Proves:** 32 to 34, and that every earlier item has a passing run or a receipt.

## Concrete Steps

From the repository's root, in the milestone's worktree. `task` below is the worktree's own launcher (`task/bin/task`) until the plugin is released.

The suites (acceptance 1 to 15 for the plugin, 16 to 19 for sminos, 20 for the old scripts while they ship), on the committed branch:

    ci-gate --gates task
    # PASS task … GREEN <run url>

    ci-gate
    # every gate the change touches (sminos's in M4, issue-tracker in M5's first pull request); GREEN <run url>

    task/bin/task --version
    # task <the plugin's version> (the task plugin of the doperpowers marketplace)

The scratch cases, with a private scratch repository of the owner's account (a second one for `edge`):

    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh fork       # M1 (21)
    # gh names <the upstream project>; task lists <owner>/<scratch>
    TASK_LIVE_REPO=<owner>/<scratch> TASK_LIVE_REPO2=<owner>/<scratch2> bash task/tests/live.sh edge   # M1, the unknown
    # cross-repository blocked-by: held | refused: <GitHub's message>
    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh migrate    # M2 (22)
    # seeded <n> issues, one per row of D6's table; applied; lint: 0 FAIL; second apply: no writes
    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh race       # M3 (23)
    # measured: 20 rounds, 5 appends in competition each; one winner in 20; confirming reads that missed a lower claim: 0; show agrees
    # any other count: M3 stops (Delegated unknowns)
    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh lapse      # M3 (24)
    # a spawned thread claimed <owner>/<scratch>#<n> and was retired; task list: #<n> unheld; release reason ended; label off

After M4's release, on a machine where the plugin is enabled (25; 26 is by hand, and `live.sh clear` prints its three steps):

    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh end
    # retire printed <owner>/<scratch>#<n>; release reason ended; label off
    # remove printed <owner>/<scratch>#<m> as still held, with: task release <m> --force "<reason>"

This repository's flip, M5 (receipts 27 and 28):

    task migrate plan --out <a file outside the tree>
    # 53 rows: 30 mechanical, 23 decisions; incoming: 0   (the counts of 2026-11-24)
    # … the decisions made, the owner's read (O2), the sessions told, the pull request merged …
    git fetch origin               # once in each clone of this repository on the owner's machines
    task migrate apply <that file>
    # relabelled 53, skipped 0; still carrying an old status label: none
    task lint
    # 0 FAIL
    task list --takeable
    # the ready, unclaimed, unblocked tickets, P1 first

Receipt 28, in a linked worktree on a branch that predates the flip (its own file still says `gh`), with the installed plugin's scripts and a ticket registered for the check:

    <the plugin's root>/skills/issue-tracker/scripts/board-list.sh
    <the plugin's root>/skills/issue-tracker/scripts/board-body.sh <n> --body-file <a file>
    # each: error: this board has moved to task (the default branch's .doperpowers/board.json says so): work it through task:tickets
    # each exits 1; task show <n>: the body and its record block unchanged

The final checks, M7 (32 to 34):

    ls skills/issue-tracker
    # No such file or directory
    git grep -l 'doperpowers:issue-tracker\|board-[a-z]*\.sh' -- skills agents sminos/skills task CLAUDE.md README.md docs/whats-inside.md
    # no output
    ci-gate && ci-gate --gates task
    # GREEN, no issue-tracker or board-api gate; PASS task
    task lint                      # here, and with --repo for each moved sibling
    # 0 FAIL

## Interfaces and Dependencies

**§1. The configuration**, `.doperpowers/board.json`, committed at a repository's root; read from the checkout, and from the main checkout when a linked worktree lacks it:

    { "binding": "task", "repo": "owner/name" }

`repo` is required and must be the repository of the checkout's designated remote: `origin`, or the remote that `git config task.remote` names (D4). No other key is read. Under `--repo` the file is read from the named repository's default branch, and no checkout is consulted.

**§2. Labels.** The names of D1's table, exactly; a batch is `batch:<name>`.

**§3. The record block.** The last thing in an issue's body: a fenced block whose opening line is three backticks and `task-record`, then lines `key: value`, then the closing fence, then nothing but whitespace. Keys: `registered-by`, `for` (addresses), `due` (`YYYY-MM-DD`), `spec`, and `adopted` (a UTC time to the second, then ` by ` and the adopting session's address when a session adopted; written by `task adopt` alone, D8). An unknown key, a second such block, or one that is not last is not read, and in a trusted body is a lint FAIL.

**§4. The claim record.** A comment whose first fenced block opens with three backticks and `task-claim`. Keys: `op` (`claim`, `release`, `takeover`), `holder` (an address; on `claim` and `takeover`), `attempt` (sixteen hex digits; on `claim` and `takeover`), `of` (a claim id; on `release` and `takeover`), `reason` (on `release`: `released`, `ended`, `forced: <text>`; on `takeover`: `cleared`, `forced: <text>`). A claim's id is the comment's numeric id. The fold is D3's table, over the trusted records of the ticket's open interval: all of them for a ticket never closed, else those dated after the second of its last reopening.

**§5. What the reading verbs give.** `task show <n> --json`:

    { "repo": "owner/name", "number": 548, "url": "…", "title": "…",
      "state": "open", "close_reason": null, "on_board": true,
      "readiness": "ready-to-work", "horizon": "expected", "priority": "P3",
      "category": "bug", "batch": null, "body_trusted": true, "body_digest": "sha256:…",
      "record": { "registered-by": "…", "for": null, "due": null, "spec": null },
      "blocked_by": [ { "repo": "owner/name", "number": 12, "state": "open" } ],
      "parent": null, "children": [],
      "holder": { "address": "…", "claim": 2161234567, "since": "2026-11-25T03:12:09Z" },
      "linked": [ { "kind": "pr", "number": 640, "state": "open", "updated": "…" } ],
      "takeable": false, "not_takeable": [ "held" ],
      "body": "…",
      "comments": [ { "id": 1, "author": "login", "trusted": true, "created": "…", "body": "…" } ] }

A blocker's `state` is `open`, `completed` or `not-planned`. `readiness` and `horizon` are null when the issue carries none or more than one. `holder` is read from the fold, never from the label, and is null for an unheld ticket. `body_digest` is what `task adopt --digest` takes. `not_takeable` names each of D1's conditions that fails: `closed`, `held`, `readiness`, `horizon`, `blocked`, `stuck` (a blocker closed as not planned), `planned-without-blocker`, `untrusted-body`, `for-another`. `task list --json` gives `{ "repo": …, "tickets": [ … ] }`, each ticket that object without `body` and `comments`. `task search --json` gives `{ "repo": …, "query": …, "hits": [ { "number", "title", "state", "url" } ] }`, each hit with `body` under `--bodies`.

**§6. Lint** reads the issues that are on the board (D1) and open issues that carry part of its vocabulary. FAIL: more than one readiness label; a ticket with no horizon label or more than one; a horizon label or `claimed` on an open issue that has no readiness label; two priorities, or two categories, on a ticket; a `status:*` label on any open issue; a blocked-by cycle; a malformed record block in a trusted body (§3). WARN: `claimed` on a ticket the fold says is unheld, or a held ticket without it; a `planned` ticket with no blocker; a ticket with a blocker closed as not planned; a ticket with no priority or no category. It also prints the number of untracked open issues, which it does not judge. Each line names the ticket and the command that repairs it; for a label that disagrees with the fold that is `task show <n>`, which writes it. Lint itself writes nothing. Exit 3 on any FAIL.

**§7. The index**, `claims.json` in the plugin's home (`TASK_HOME`, by default `~/.claude/task`):

    { "v": 1, "settled": "…", "rows": [ {
        "repo": "owner/name", "number": 548, "title": "…", "url": "…",
        "claim": 2161234567, "attempt": "9f2c41d07a3b5e68",
        "session": "<session id>", "thread": "<thread id>",
        "address": "…", "since": "…", "successor": "",
        "state": "held", "reason": "", "at": "…", "tries": 0 } ] }

`settled` is when a settle of every row last started on this machine (D3, "When settle runs"). `thread` is a thread id, or an empty string when sminos said the session is no thread; it is written with the row and never changed. `attempt` is the token the row's record carries (§4), and `successor` the session a `/clear` granted the takeover to. `state` is `pending` (the row was written and its record not yet confirmed; `claim` is null), `held`, `owed` (a release is due; `reason` says which) or `lapsed` (released or taken over; `reason` is `ended`, `taken-over` or `forced`). `at` is when the state last changed; a lapsed row is dropped seven days after it.

**§8. The plan file** of `task migrate plan`:

    { "v": 1, "repo": "owner/name", "read_at": "…",
      "rows": [ {
        "number": 548, "title": "…",
        "seen": { "state": "open",
                  "labels": [ "status:ready-for-implementer", "priority:P3", "bug" ],
                  "body": "sha256:…", "body_trusted": true,
                  "blockers": [ { "repo": "owner/name", "number": 12, "state": "open" } ] },
        "action": "relabel", "readiness": "ready-to-work", "horizon": "expected",
        "basis": "mechanical", "decided": true, "why": "",
        "body_after": null } ],
      "incoming": [ 601 ] }

`seen` is what the row's proposal was computed from, as the plan read it. `body_after` is the whole rewritten body where the apply will rewrite one (a `board:meta` block, the retired service's banner), else null; it is null for a body that is not trusted. `action` is `relabel`; `body`, for a ticket already on the board whose body alone is rewritten; or `leave`, for an issue that stays untracked and is never written. A decision row is written with `basis: "decision"`, D6's fallback values and `decided: false`; whoever settles it sets `action`, the two labels, `why` and `decided: true`. `incoming` lists the open issues another account authored, which the apply never writes.

At apply each row's issue is read again and is one of three things. Of its labels only the board's are compared: the `status:*` labels, the readiness and the horizon. A row's target labels are its readiness and its horizon with no status label (for `body`, the labels as seen); its target body is `body_after`, or the body as seen where that is null.

- **Done**: the body and the labels are both at their targets. Nothing is written.
- **The plan's own row**: the issue is open, its blockers are as seen, its body is as seen or at its target, and its labels are as seen, or as seen with the horizon added, or with the horizon and the readiness added, or the two new labels with some of the seen status labels still on. The apply writes what remains, in D6's order.
- **Changed**: anything else. The row is skipped and named, with what differs.

**§9. What sminos calls.** Both run from any directory, print one JSON object, and exit 0 whenever they could answer, whatever the answer; exit 2 is a usage error, which is also what a plugin from before a verb or a flag gives.

`task held --session <session id> [--thread <thread id>] [--cleared-from <thread id>] --json`, which reads the index only and never the network:

    { "v": 1,
      "held":    [ { "repo", "number", "title", "url", "claim", "since" } ],
      "lapsed":  [ { "repo", "number", "title", "url", "reason", "at" } ],
      "offered": [ { "repo", "number", "title", "url", "claim", "since" } ] }

`held` and `lapsed` are the named thread's rows (empty without `--thread`); `offered` is the held rows whose `successor` is the named session. `--cleared-from` first sets `successor` to that session on the held rows of the thread it names.

`task settle [--thread <thread id>] --json`:

    { "v": 1,
      "released":    [ { "repo", "number", "title", "url", "claim", "reason" } ],
      "closed":      [ { "repo", "number" } ],
      "lapsed":      [ { "repo", "number", "reason" } ],
      "owed": 0,
      "unknown":     [ { "repo", "number", "title", "url", "thread", "said" } ],
      "unreachable": [ { "repo", "said" } ] }

A call states nothing about any thread: with or without `--thread`, the plugin asks sminos about each row's thread as it runs, and `--thread` only limits the run to that thread's rows. `unknown` lists the held rows whose thread sminos gave no usable answer about, `said` being what it gave (`exit 4`, `timeout`, `another thread`, `not local`, `no sminos`); a row whose thread is answered as live is in no list. `owed` counts the rows still owed after this run.

**§10. What `task` asks of sminos** (1.53.0 or later; found through `TASK_SMINOS`, `PATH`, then the marketplace clone):

- `sminos who`, with the session's id in the environment: a line `Sminos-Session: <address>`, or nothing.
- `sminos who --thread=<name>`, always with a full session id or thread id except for the name `--to` was given: one line of JSON, of which `task` reads `thread`, `session`, `short`, `alias`, `machine`, `project.name`, `ended` and `local`. Exit 4: nothing answers the name, several do, or sminos cannot see the record; `task` reads it as no answer, never as "ended" and never as "no thread". Exit 2: a sminos from before the flag. An answer about the claiming session's own id is taken only when its `session` is that id and `local` is true; an answer about a row's thread only when its `thread` is that id and `local` is true.
- `sminos say "@<tag> <text>"`, for `create --to` only.

sminos finds the plugin through `SMINOS_TASK`, the copy beside its own plugin, the marketplace clone, then `PATH`, as `devcloud_places` orders devcloud's.

**Dependencies.** The `gh` client, authenticated as the owner's account, on every machine that runs `task`. No package beyond Python's standard library. For the scratch cases, two private scratch repositories named by `TASK_LIVE_REPO` and `TASK_LIVE_REPO2`.

## Outcomes & Retrospective

Pending — written at finish.
