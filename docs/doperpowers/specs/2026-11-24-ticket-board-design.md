# The ticket board: items, labels, claims and the `task` CLI (2026-11-24)

The owner supervises many long-running Claude Code sessions across repositories and machines. Each repository's backlog, its **board**, is that repository's GitHub issues, and sessions write it through the scripts of the `issue-tracker` skill (`skills/issue-tracker/scripts/board-*.sh`). The scripts and their eleven states were cut for an unattended dispatch pipeline that has been dormant since 2026-10-18 (`docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md`), and two faults the owner named follow from that:

- **Work leaks between sessions.** A deferred item is taken up only if some session remembers it. The in-between states (`in-design`, `in-progress`, `in-review`) are moved by hand and tied to nothing, so a ticket a session took and left keeps saying someone has it: one open ticket of this repository has read `status:in-design` since 2026-10-21, the day the pull request that references it merged.
- **No whole picture.** Who holds which piece of future work is known only by reading specs and session lists.

After this change a ticket shows three things and nothing else until GitHub's close: what it needs before work can start (**readiness**), how far off it is (**horizon**), and whether a thread has it (**claimed**). A claim belongs to the thread that made it and is released by a write when that thread ends, so a claim does not outlive its holder unseen. Agents work the board through one command, `task`, shipped in a plugin of its own; the `issue-tracker` scripts, their states and the dormant dispatch machinery leave the plugin for `archive/`.

To see it working, in a session of this repository: `task list --takeable` prints the tickets a session may take on its own initiative. `task claim 548` puts `claimed` on #548 with a visible record naming the claiming session; the same command from a second session exits 3 and names the holder. Retire the first session's thread (`sminos retire`), or leave it stopped for three days: after the daemon's next pass #548 is unclaimed again, with a record that says why, and it is back in `task list --takeable`. On the issue's page the owner reads `ready-to-work`, `expected`, `priority:P3`, `bug`, the record of who registered it, and the claim. In a checkout that carries an `upstream` remote, `task list` lists this repository's tickets and not the upstream project's.

This unit gives the whole picture its data (who holds what, and one ticket per initiative pointing at its spec); the view that draws it is a later unit (Out of scope).

## Progress

- [x] (2026-11-20 to 11-24) The design discussed with the owner; the unit confirmed on 2026-11-24 (R8).
- [x] (2026-11-24) Spec review, `doperpowers:adversarial-reviewer`, one round: the design and its interfaces (seventeen findings), and the execution section's buildability (eleven). Folded in one closing pass; what was weighed and not taken is answered where the decision stands (D3 "What is accepted", D5, D6).
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
- **Record block, claim record, the fold, the index, settle, trusted.** Defined where they are designed: D2, D3 and D8.

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
- **The GitHub client resolves the wrong repository in a fork.** In a fresh repository with `origin` set to this fork and `upstream` set to the project it was forked from, `gh repo view` answered the upstream project and `gh issue list` listed its issues, with no warning (gh 2.97.0). This repository's main checkout answers correctly only because a default was once recorded there.
- **The old scripts.** `_binding.sh` reads the checkout's `.doperpowers/board.json`, and the main checkout's only when a linked worktree has no such file; it stops on any `binding` other than `gh` or `api`: `unknown binding "<x>" — expected "gh" or "api"`. `_board.py`'s `ensure_labels` creates the `status:*` labels again whenever a script needs them. Two skills call the scripts by name or tell sessions to make tickets of a spec's children: `skills/decomposing/SKILL.md` (its optional step 6) and `skills/organizing-sprints/SKILL.md` (Materialization, which names `board-register.sh`, `--state` values and `board-lint.sh`).
- **GitHub.** One GraphQL query returns, for an issue and each of its comments, the author, the last editor (`editor`), the comment's id (`databaseId`) and creation time (to the second), the pull requests that reference or close it, its linked branches, and its close and reopen events. The REST API lists an issue's comments in ascending id. A closed issue still takes comments. Nothing in the API writes an issue on a condition (no "only if unchanged"). Labels, native blocked-by and parent edges are written by the old scripts today through the same API.
- **sminos** (1.58.0). `sminos who` and `sminos who --thread=<name>` exist (the second since 1.53.0, one line of JSON: `thread`, `session`, `short`, `alias`, `opened`, `state`, `ended`, `local`, `machine`, `project`; exit 4 when nothing answers the name, exit 2 from an older sminos). A name that is a full session id or thread id answers for a live, a stopped and an ended thread; an ended thread its human opened answers to a full id only, and a purged one (`sminos retire --purge` deletes the record) to nothing. A thread's `ended` is written by its own machine: in the ending pass, or by a retire, whose end and purge are one journaled transition (`thread_transition`), with no step between them. A thread that returns loses its `ended` mark. A message addressed to a stopped thread wakes it. What a `/clear` left is known to the new session's start hooks only, through a note that is believed for a bounded time (`cleared_from` and `cleared_witness` in `sminos.py`); no record keeps it. sminos asks the devcloud plugin one question through its CLI (`find_devcloud` and `owned_by` in `sminos_threads.py`): found in a fixed list of places, held to a minimum version, bounded by a timeout, and no answer is never read as "none". A subagent's Bash runs with its parent session's id, and a plugin's `bin/` directory comes last on a session's `PATH`.

## Design

### D1. Items and labels

A ticket is a GitHub issue in its project's repository. Its labels:

| Axis | Labels | Rule |
|---|---|---|
| Readiness | `ready-to-work`, `need-design`, `need-input` | exactly one on every ticket |
| Horizon | `planned`, `expected`, `undecided` | exactly one on every ticket, kept through a claim |
| Claim | `claimed` | on while a thread holds the ticket (D3) |
| Priority | `priority:P0` … `priority:P3` | one, required at creation; unchanged from today |
| Category | `bug`, `enhancement`, `spike`, `env-issue` | one, required at creation; unchanged from today |
| Batch | `batch:<name>` | optional: a named set one agent takes whole |

**An open issue is on the board when it carries a readiness label.** No other label enrolls it: the issue templates put a category on whatever a visitor files, so a category says nothing about whose work an issue is. An open issue without a readiness label is *untracked*: the board's rules and `task lint` do not apply to it, and `task list --untracked` shows it.

- **Readiness** says what must exist before work can start (R4). `ready-to-work`: buildable from its body, or from the spec its record points at. `need-design`: its design comes first, with the owner, through doperpowers:brainstorming; it absorbs `interactive-preferred`. `need-input`: it waits on something that is neither design nor build (a decision or a real-world input only the owner holds, or research); it absorbs `needs-human` and `needs-info`, and its body says in prose what it waits on and what would unpark it. A request to the owner is not a ticket (R7), so no label marks a ticket as the owner's.
- **Horizon** says how far off the work is (R5). `planned`: its order is decided, and "after what" is a blocked-by edge. `expected`: it will be worked, in no decided order; the default. `undecided`: whether to do it at all is open.
- **The end** is GitHub's close: completed, or not planned. A closed ticket's labels mean nothing.
- **Nothing in between** (R4). Readiness and horizon stay as they were when a ticket is claimed: `need-design` with `claimed` reads "someone is designing it". When design ends the holder sets `ready-to-work` and the spec pointer; that is the one mid-life write, and it happens at a hand-over, not during work.

**What a session may take on its own initiative** (a *takeable* ticket). All of these hold, and anything unknown counts against:

1. it is open and unheld;
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

`registered-by` is the address of the session that created the ticket (absent when no session did); `for` the thread it was registered for (D1); `due` a date the work must be done by; `spec` a repository-relative path, optionally `@<sha>`, or a URL when the spec lives in another repository. Every key is optional, each value is one line, and the block is read only when it is the last thing in the body and the body is trusted (D8). It is a fenced block and not an HTML comment because the block it replaces, `board:meta`, was invisible on the issue's page, and a status note the owner cannot see is of no use to them.

The claim's holder is not in this block (D3 says why). Lineage that the old block carried (`spawned-by`, `relates-to`) is prose in the body: a mention of `#n` already cross-links both issues on GitHub.

Every body write by the CLI reads the body afresh, replaces the text above the block and keeps the block byte for byte. Two limits are accepted. A raw `gh issue edit --body` drops the block, and nothing can tell afterwards that it was there, so the skill sends every body edit through `task set` (M5). And the body is one string with no conditional write: two edits of one ticket's body within the same moment (its text and its `for`, say) leave the later one standing. These fields change at creation and at a hand-over, a few times in a ticket's life, which is why they may live in the body and the claim may not.

### D3. Claims

A claim says a thread has taken a ticket. It belongs to the thread, so it survives a compaction, a hand-off to a new session id and a stopped process, and it changes only by a write: a release by its holder, a release by the holder's machine when the thread ends, or a takeover. No reader infers that a claim has lapsed, because a thread that looks gone can return. There is no lease: a lease must be renewed, and renewal is bookkeeping in the middle of work (R4); a long-lived thread's claim would lapse under it while the thread works.

**The record.** Each change of a claim is one comment on the ticket, written by the CLI, holding one fenced block and, after it, any prose the writer adds (where the work stands, at a release):

````
```task-claim
op: claim
holder: builder#1a2b3c4d (doperpowers on laptop)
```
````

`op` is `claim`, `release` or `takeover`. A claim's **id** is the GitHub id of the comment that made it (a `claim` or a `takeover`). `release` carries `of: <claim id>` and `reason:` (`released`, `ended`, or `forced: <text>`); `takeover` carries `of:`, `holder:` and `reason:` (`cleared`, or `forced: <text>`). The holder is written as the claiming session's address: what every commit of that session already publishes, and nothing else of sminos's (no thread id, no project id). A subagent's claim is its session's, since its commands run with the parent session's id.

**The fold.** Who holds a ticket is computed the same way by every reader. A closed ticket is unheld. For an open one, take its comments in ascending id, keep those that carry a `task-claim` block, are trusted (D8) and were created in the ticket's current open interval (since its last reopening, or since its creation), and apply:

| Record | Ticket unheld | Ticket held by claim *c* |
|---|---|---|
| `claim` (comment *k*) | held by *k* | void |
| `release` of *x* | void | *x* = *c*: unheld; otherwise void |
| `takeover` of *x* (comment *k*) | void | *x* = *c*: held by *k*; otherwise void |

A void record changes nothing. A close ends every claim: a reopened ticket starts unheld, and a record that landed while the ticket was closed (a claim begun a moment before a merge closed it) lies outside the open interval.

**Arbitration.** `task claim` reads and folds; if the ticket is held it refuses; otherwise it appends its `claim`, reads and folds again, and holds the ticket only if the fold names its own comment. A writer that finds its record void deletes it and reports who won. The order GitHub gives the comments decides between two claims seconds apart, where today's scripts rewrite labels with nothing to arbitrate. This rests on one assumption GitHub does not document: that the confirming read shows every comment with a lower id. If a read ever misses one, two sessions believe they hold the ticket until either next touches it, when the fold names the lower id for both. That window is accepted. GitHub offers no conditional write to close it with, and the one primitive that would (an atomic creation of a git ref per claim) puts refs in every repository for a collision that needs two sessions, one ticket and the same second. M3 measures it (Delegated unknowns), and a measured violation stops M3.

*Alternative weighed: the holder as a field of the record block.* It lost on two counts. The body is one string, so a claim, a release and an edit of the ticket's text would overwrite one another, and a release lost that way leaves a ticket held by a thread that has ended. And a single field holds no history, while a takeover has to name the claim it supersedes so that a stale one is void. *Alternative: GitHub's assignee.* Every session writes as the one owner's account, so an assignee cannot tell two threads apart.

**The label.** `claimed` is what lists and the owner read; the fold is the truth. A claim's winner sets it after the fold confirms; a release takes it off before it writes its record. In that order a later claimant's label can never be removed by an earlier holder's release. Every settle makes the label of each ticket it visits agree with the fold, and `task claim` always decides by the fold, so a label left wrong by a crash can at worst offer a ticket whose claim is then refused, or hide one until the next settle that visits it.

**The index.** Each machine keeps, in the plugin's own directory, one row per claim it wrote that it has not yet seen end: the repository, the ticket, the claim's id, the claiming session and its thread (both private to the machine), when, and a `successor` once a `/clear` granted one. The row is written before the claim is appended, as *pending*, so that an append GitHub accepted and the process never heard about is found again: the next settle reads the ticket and either adopts the claim that carries the row's address or drops the row. The index exists so that the machine can answer "what does this thread hold" at a session's start without a network call, and can find a thread's claims when the thread ends without scanning every repository. It holds nothing of a ticket's content and decides nothing: every act reads the ticket again. *Alternative: no index, a scan of GitHub.* It lost because the start of every session would wait on the network, and because a machine would need a list of every board it ever wrote to, which is an index by another name.

**A row's thread** is one of three things, and they are not the same. A thread id: sminos named the claiming session's thread. Empty: sminos answered that the session is no thread (one the MAWS app launched); no lifecycle release applies (O4). Unknown: sminos gave no answer when the claim was made; settle asks again each time it runs, by the row's full session id, until it has one of the other two.

**Events, and who writes.** Every label the owner reads is kept true by a write from the machine that learns the fact first.

| Event | Writer | Written on GitHub | Index |
|---|---|---|---|
| A session claims | that session's `task claim` | `claim` record; `claimed` on | a pending row, then held |
| The holder sets the ticket down | its `task release` | label off; `release` (`released`) | row removed |
| The holder's thread ends (a retire, or three days stopped) | its machine: `task settle`, started by sminos (D5) | label off; `release` (`ended`) | row kept as *lapsed* |
| A `/clear` in the holder's process | sminos's guide in the new session (D5) | nothing: the claims stay with the thread that was left | its rows gain the new session as `successor` |
| The successor takes over | its `task takeover` | `takeover` (`cleared`) | the left thread's row turns lapsed; a row is added for the taker |
| Another session takes over | its `task takeover --force` | `takeover` (`forced: …`) | a row for the taker; the former holder's machine marks its row lapsed at its next settle |
| The ticket closes (a merge, or `task close`) | `task close`; else the holder's machine at its next settle | label off | row removed |
| GitHub is unreachable when a release is due | — | — | row marked *owed*; every later settle, and every later `task` verb on that machine that writes to GitHub, tries it again first |

**Settle** is the one routine that makes a machine's claims true. For each row (of one thread, or all) it reads the ticket once and acts on what it finds; a board it cannot reach is skipped and reported, and the other boards' rows go on.

- A pending row: adopt the claim that carries its address, or drop the row once it is older than an hour.
- The ticket is closed: label off, row removed.
- The fold does not name the row's claim: the row is lapsed. If it was owed, this machine's own release got through before a crash, and its reason stands; otherwise another session took the ticket over or released it by force. The label is made to agree with the fold as it now is, never taken off a later holder.
- The fold names it: the label is made to agree (on). Then, if the row's thread is unknown, sminos is asked again. If the row has a thread id and either sminos's caller said that thread has ended (`--ended`, D5) or sminos answers, for that exact thread id, that it has ended on this machine, the row is marked owed, the label taken off, the release written, and the row marked lapsed.
- sminos gives no answer about a thread: nothing changes, and the row is reported as unknown.

The plugin asks sminos about each thread, and sminos does not hand the plugin a list of what ended, because a crash between sminos writing an end and telling the plugin would lose the release for good, while a settle that failed is simply run again. A retire is the exception, since a purge leaves nothing to ask about: there sminos states the fact as it calls (D5).

**A thread that returns.** If its human reopens it before its machine's next settle, sminos no longer calls it ended and it keeps its claims, which is right: it is live and nothing was released. If it returns after, its claims were released and another session may hold the ticket; `task held` reports each lapsed row, with why, for seven days, so that its guide tells it to claim again before it continues. Reporting by age, and not once, means a start whose guide was lost does not lose the warning, and the rows of a thread that never asks again expire.

**Takeover.** `task takeover <n>` writes a `takeover` of the current claim. Without a stated reason it is open only along a `/clear`: the index holds a `successor` grant for this session on that claim. Everything else is `--force "<reason>"`, with the reason written in the record: taking a live thread's ticket means two sessions building one thing, and the one who decides that is the owner. An ended thread needs no takeover, because its machine has released its claim; a holder whose machine is gone, or whose row was lost, is exactly the case a person should look at. `task release` and `task close` follow the same rule: the holder acts on its own claim (the row is its thread's, or the record's address is its session's), and anyone else needs `--force "<reason>"`. The grant is not a lock against a session that misuses the CLI, which `--force` would serve as well: it is what lets the ordinary case go without a reason.

**What a reader is shown.** `task show` prints the holder's address, the claim's age, and the last activity on the pull requests and branches GitHub links to the ticket. With no lease, that is what lets a reader judge a claim that has gone quiet.

**What is accepted.** These are left as they are. The first four leave a claim that no machine will release; each is visible (the claim's age and linked activity on `task show`, the row in settle's `unknown`), and each ends with `task release --force` or a forced takeover.

- A session the MAWS app launched is not a thread: no machine learns that it ended for good (O4).
- A machine with no running daemon releases only at a retire.
- A purge whose call to settle was lost (the retire's process died in the instant after its end was written, or the plugin gave no answer within the bound) leaves rows about a thread sminos can no longer name. *Weighed: sminos keeping a replayable record of every end for the plugin to consume.* It lost: a new interface in sminos, with a cursor and an acknowledgement, for a fault that needs a manual `retire --purge` and a failure inside the same second.
- A holder's machine that is retired, or an index that is lost.
- `task close` checks the holder when it runs; a takeover in the same moment is not arbitrated against it.

**What the parts cost and buy** (O1). The fold is a table and one extra read per claim; it buys one winner between two sessions. Everything else here (the index, settle, sminos's calls) buys one thing: a claim does not outlive its thread, which is the fault this work opened with. Contention between two sessions is rare; a session that takes a ticket and is then closed for good is not.

### D4. The `task` CLI and its plugin

A new plugin, `task`, in this marketplace (`task/` at the repository's root, versioned on its own). Its command is `task` (R9), its skill `task:tickets`. It is a plugin of its own, and not part of doperpowers or sminos, so that it rides neither's releases: a board fix must not wait for, or force, a sminos release, and sminos must run without it.

**Two destinations, one built.** `task` is the agents' one command for tracked work (R9). Every verb this unit builds acts on tickets. Verbs that write to the human's Task Board (the owner's example: `task assign-human`) belong to the separate unit that designs it; the command's dispatch keeps one flat verb namespace with those names unused, and `task assign-human` exits 2 saying that the Task Board is not built.

**The repository is named, never resolved.** A board's repository is the `repo` of the checkout's committed `.doperpowers/board.json`, and every call to GitHub names it. The CLI never asks the GitHub client which repository a directory belongs to (see "What exists today": in a fork the client answers the upstream project). `repo` must be the repository of one of the checkout's own git remotes, or the CLI refuses: a branch checked out for review can change the file, and must not be able to point a session's writes at a repository of its author's choosing. `--repo owner/name` works a board from outside its checkout; its configuration is then read from that repository's default branch.

**The binding is the cutover switch.** `binding` in that file says which tool owns the board. `"task"`: this CLI. Anything else: every verb that works a board refuses, naming the file, except `task migrate plan`, which only reads. The old scripts refuse a binding they do not know, so one committed line moves a repository from one tool to the other in every checkout that has the commit (D7 says what happens in one that does not). Two verbs work no board and need no checkout: `task held` and `task settle` work from the machine's index, each row naming its own repository, and run from any directory, a service's included.

**Verbs.**

| Verb | Does |
|---|---|
| `task create <title> --category C --priority P --readiness R --body-file F` `[--horizon H] [--blocked-by N,…] [--parent N] [--batch NAME] [--due DATE] [--spec S] [--to THREAD]` | opens the ticket with its labels, edges and record block; prints `<number> <url>` |
| `task show <n>` | the ticket: labels, record, edges, the holder with its age and linked activity, the body, the comments, each marked with whether it is trusted |
| `task list` `[--takeable] [--readiness R] [--horizon H] [--claimed\|--unclaimed] [--batch NAME] [--untracked]` | tickets by priority, then number: readiness, horizon, priority, holder, blockers, `for`, `due`, title. `--untracked` lists the open issues that are not on the board instead |
| `task search <query> [--state open\|closed\|all] [--bodies]` | GitHub's issue search, held to the board's repository |
| `task set <n>` `[--readiness R] [--horizon H] [--priority P] [--category C] [--batch NAME\|--no-batch] [--due D\|--no-due] [--spec S\|--no-spec] [--to T\|--no-to] [--title T] [--body-file F] [--keep-record]` | changes labels, the record block, the title or the text above the block. Setting a readiness also takes any `status:*` label off the issue |
| `task edge <n> --block N \| --unblock N \| --parent N \| --orphan` | one edge; refuses a self-edge and a blocked-by cycle |
| `task comment <n> --body-file F` | a comment, so that no session needs a raw client call, which could resolve the wrong repository |
| `task claim <n>… \| --batch NAME`, `task release <n> [--body-file F] [--force R]`, `task takeover <n> [--force R]` | D3. Several tickets are claimed one by one, and the output says which were won. A ticket this session's thread already holds is "already yours", exit 0 |
| `task close <n> [--not-planned] [--body-file F] [--force R]` | closes it, completed unless told otherwise; refuses a ticket another thread holds, without `--force` |
| `task lint` | the invariants over the live board (Interfaces §6) |
| `task migrate plan`, `task migrate apply <plan>` | the one-time relabel (D6) |
| `task held`, `task settle` | what sminos calls (D5) |

`create` writes the readiness label last, after the issue and its edges exist, so that a ticket whose blocker could not be attached is never seen as ready; if an edge fails, the issue is left untracked and the output says so. `--to` names a thread sminos must resolve: when it cannot, `create` and `set` exit 1 and write nothing.

Every reading verb takes `--json`. Exit codes: 0 done; 1 failed (GitHub, the configuration, a sminos answer the verb cannot do without); 2 usage, or a verb this unit does not build; 3 refused by a rule of the board (held by another, not the holder, registered for another thread, a failed lint, a plan with undecided rows).

**It writes as the owner's account**, through the `gh` client's own credential, as the old scripts do. The session that wrote is named in the record.

### D5. The contract with sminos

Two plugins, one narrow contract in each direction, in the manner of sminos and devcloud: each side finds the other's CLI, asks one bounded question, and treats silence as no answer.

**`task` asks sminos** (nothing new in sminos; 1.53.0 or later):

| Call | For | Without an answer |
|---|---|---|
| `sminos who`, inside a session | the session's address: `holder`, `registered-by` | `claim` and `takeover` refuse (exit 1): a claim belongs to a session sminos knows. `create` writes no `registered-by` |
| `sminos who --thread=<the session's own id>` | the claiming session's thread, kept in the row: a thread id, or empty when sminos says the session is no thread | the row's thread is unknown, and settle asks again |
| `sminos who --thread=<a row's thread id>` | at settle: whether that thread has ended. Only an answer whose `thread` is that very id, with `local` and `ended` true, releases | the row is reported unknown |
| `sminos who --thread=<name>` | the thread `--to` names | `create --to` and `set --to` exit 1 |
| `sminos say "@<thread> <text>"` | the one message of `create --to` (O5) | the ticket exists, and the output prints the line to send |

Threads are always asked about by a full id, never by the short id in a public address: a short id can answer for another session, and an ended thread answers to its full id only.

**sminos calls `task`** (M4 adds these calls and nothing else):

| When | Call | sminos does |
|---|---|---|
| A thread's session starts (the guide) | `task held --session <session id> --thread <thread id> --json` | prints one guide line: what the thread holds, what lapsed, and what the conversation it cleared from still offers it |
| The same start, when sminos has a witness of a `/clear` | the same call with `--cleared-from <the thread left>`, which records the grant | prints what the conversation it left holds, and that `task takeover <n>` takes one over |
| A retire's end has been written and its transition has returned | `task settle --thread <thread id> --ended --json` | prints what was released, or that the board gave no answer |
| The daemon's ending pass, each time it runs | `task settle --json`, as a child the tick does not wait for | logs when the count of owed or unknown rows changes, and each distinct failure once |

sminos finds `task` as it finds devcloud (an override variable, the copy beside its own plugin, the marketplace clone, then `PATH`), reads the plugin's version from its manifest and asks nothing of one below the floor, bounds each call, and reads a missing plugin, an old one, a timeout or a non-zero exit as no answer. It never reads the plugin's files, and no session start, retire or pass fails or waits past its bound because of the board.

sminos is the caller at these moments because it alone knows them: it owns the guide, it holds the only witness of a `/clear`, and it writes every thread's end.

- **At a `/clear`** the grant is recorded while sminos has its witness in hand, because nothing keeps that witness afterwards. The new session is shown the offer at each of its starts until it takes the ticket over or the thread it left ends. No message is sent when that thread ends: a message to a stopped successor would wake it, and a machine waking a session over a ticket is what the ruling of 2026-10-18 ended.
- **At a retire** sminos calls after its own transition has returned and holds none of its locks, since the plugin may ask sminos questions of its own; `--ended` is sminos stating the fact, so the plugin does not ask about that thread, which after a purge no longer answers. The call is bounded at 30 seconds, and a retire that hears nothing says so and goes on.
- **In the ending pass** the daemon starts one settle each time the pass runs, so a thread ended by the three-day rule loses its claims within the pass that ended it.

### D6. The relabel

Existing issues are relabelled once per repository, by a plan a session reads before it is applied.

`task migrate plan` needs only a repository (the configuration's `repo`, or `--repo`), since it runs before a board has moved. It reads the open issues and writes a plan with three kinds of entry. An issue that carries an old status label gets a row: its old labels, the new readiness and horizon, and whether the row is **mechanical** (the old label decides it) or a **decision** (it does not). An issue with no status label that the trusted account authored gets a decision row whose outcome may be to leave it untracked. An issue anyone else authored is listed as incoming and never written: it stays untracked (D8).

`task migrate apply <plan>` refuses a plan made for another repository, and refuses while a decision row is undecided. For each row it compares the issue's labels as they are now: the row's target already reached, nothing to do; the plan's old labels still there, the row is written (new labels on, the old status label off, the body rewritten as below); anything else, the issue changed since the plan and the row is skipped and reported. So an apply that stopped halfway is run again and finishes, and a second apply writes nothing. It ends by listing every open issue that still carries an old status label (a skipped row, an issue opened since the plan), which is what a new plan is made for.

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
- **The `board:meta` block becomes visible.** Each key it carries is rewritten as a line of the body above the record block (a `note` as "Board note:", `relates-to` and `spawned-by` as mentions, a `branch` or `pr` as it stood), except a pinned `plan:`, which becomes the record's `spec:`. A `needs-human` ticket's note is its question list, so this is also what makes a `need-input` ticket say in prose what it waits on.
- **The retired service's banner goes.** A body that opens with the board service's mirror header ("Read-only. Edits here are reverted … The board is the source of truth") tells its reader that GitHub is not the ticket, against R1. The header is replaced by one line that keeps the old ticket's number; two open issues here carry it. Everything else in a body stays byte for byte, and each rewritten body is in the plan for whoever reads it.
- **Other labels are not touched**: `priority:*` and the four categories (an on-board issue without one is reported, never given one), `engine:claude`, and labels that were never the board's (`tech-debt`, the pull-request label `confident-ready`, `accessibility`, GitHub's defaults).

For this repository that is 30 mechanical rows and 23 decisions (O2).

### D7. Cutover and retirement

A repository moves in two steps.

**First, what sessions read is shipped and on the machines:** the `task` plugin with its skill; one sentence at the head of the old skill sending a repository whose binding is `task` to `task:tickets`; and the skills that send work to the board (`execspec`, `decomposing`, `organizing-sprints`, a line of the sminos skill) worded for both bindings. Two of them change behavior and not only a name. `decomposing`'s optional step 6 makes tickets of a composite's children, and `organizing-sprints`' Materialization makes a ticket per epic with its slices as child tickets and parks them in old states. Under D1 each keeps one ticket per initiative (for a sprint, per epic) pointing at its section of the spec, leaves the children in the spec, and still registers as tickets what the design defers out of it.

**Then the board flips, in one sitting.** The plan is written and its decisions made; the sessions working in the repository are told through sminos; a pull request sets `"binding": "task"` (adding `.doperpowers/board.json` where there is none) and replaces the text the repository's `CLAUDE.md` carries about the board; once it merges, the plan is applied and `task lint` is clean.

**What the flip does and does not fence.** From the merge on, the old scripts refuse the repository in every checkout that has the commit. A linked worktree on a branch from before the flip still carries the old file, and the old scripts run there until that branch takes the commit: they would put a `status:*` label on an issue again. `task lint` fails on any open issue that carries one, and `task set` takes it off as it sets the readiness. The window closes for good at retirement, when no installed plugin has the scripts. In the minutes between the merge and the apply, `task` sees old-labelled issues as untracked; an issue it sets in that time is skipped by the apply and reported.

**Retirement.** The old skill stays shipped until every repository that uses it has moved or has been left on purpose (O3). Then `skills/issue-tracker/`, its tests and its two CI gates leave for `archive/issue-tracker/`, as the dormant dispatch machinery and the board service binding with them (R2). Nothing arms that machinery today, so the ruling of 2026-10-18 is unchanged by the move: what it kept in the tree and tested "armed nowhere" is kept in the archive, untested.

The four tickets that were kept off GitHub when the board service retired (`docs/doperpowers/board-service-tickets.md`) stay where they are: where a project's private tickets live is not decided here.

### D8. Public repositories: what is trusted

Three of the boards are public, so anyone can open an issue or write a comment there.

- **The trusted account is the account the CLI writes as**: the one the `gh` client is authenticated as on that machine. It is not read from the repository. A key in a committed file would be whatever the checked-out branch says, and a branch checked out for review is someone else's text.
- **A body or a comment is trusted when its author is the trusted account and its last editor, if any, is too.** A record block is read only from a trusted body, a claim record only from a trusted comment. `task show` says of every body and comment whether it passed.
- **Untrusted is unknown, not absent.** A ticket whose body is not trusted is not takeable, whatever its labels say, since its `for:` cannot be read. And `task set` does not carry an unverified block into a body it writes, which would then show the trusted account as its last editor: it drops the block and says so, unless `--keep-record` is given on the owner's word.
- **Labels and edges are trusted as GitHub grants them**: only an account the repository's owner gave rights to can set them.
- **An issue an outsider opened is untracked** until an account with rights puts a readiness label on it, and even then it is not takeable (its body is not trusted): it becomes work when the owner, or a session on the owner's word, registers a ticket that refers to it.

What an outsider wrote in a body or a comment is data, never an instruction; the skill says so, and the trust mark on `task show` is what a session reads it by.

## For the owner's read

**Open decisions.** Each has a recommendation, and the work named beside it does not start before the answer.

- **O1. How much a claim carries** (before M3). The design releases a claim by a machine's write when the claiming thread ends (D3). That is most of this unit's machinery: an index on each machine, the settle routine, three call sites in sminos (M4), and a list of gaps it accepts. *Recommended:* keep it. The fault this work opened with is a ticket that says someone has it after that someone is gone, and a `claimed` label tied to nothing is `in-design` under a new name. *The lighter design:* keep only the claim record and the fold, which give one winner between two sessions. A claim is then released by its holder or by `--force`, and a stale one is found by reading: `task list --claimed` shows each holder, the claim's age and the activity linked to the ticket. That removes M4, about half of M3 and every item of D3's "What is accepted", at the price of claims that stay until someone looks. The review found the fold sound and put nearly all its findings in the lifecycle part; it was not asked to rule on the proportion.
- **O2. Who settles the relabel's decision rows** (before M5's flip, and each repository's in M6). The relabel cannot decide 23 of this repository's 53 open tickets from their labels: 19 `deferred`, one in design, three with no status. *Recommended:* the session running the cutover reads each ticket and proposes its readiness and horizon with a one-line reason, and the owner reads that table once per repository before it is applied, because `undecided` against `expected` is the owner's knowledge and every reader trusts the labels afterwards. It costs one read of about twenty rows here (more for `cua` and `MAWS`, which have 24 and 28 `deferred`). *The cheaper path:* apply the session's proposals unread and correct by exception; a wrong `expected` would then let a session build something the owner had not decided to do.
- **O3. `ida-solution`** (before M7). It cannot be read from the owner's account today, belongs to an organization, and its checkout holds a workflow that writes `status:*` labels and one that publishes a board page. *Recommended:* leave it out of this unit, recorded by a ticket here. Its `CLAUDE.md` already tells a session not to write the board when the scripts are missing, so after M7 its board is read-only to agents until someone with access moves it by M6's steps and retires that workflow. *The alternative:* M7 waits until it has moved, which keeps the old skill shipped for a repository that has had no dispatch since August.
- **O4. Claims by sessions the MAWS app launched** (before M5's flip; moot under O1's lighter design). Such a session is not a thread, so nothing releases its claims when it is gone for good (D3). *Recommended:* accept it for the first cutover. The claim shows its age and its linked activity, and any session can take it over with a stated reason; MAWS telling the board when it archives a session is registered as a ticket for MAWS at M5. *The alternative:* this repository's flip waits until MAWS does that and it has been seen to work.
- **O5. The message of `task create --to`** (before M1 ships the flag). Registering a ticket for a named thread sends that thread one message, and sminos wakes a stopped thread for any message addressed to it. This is the one place where filing a ticket can start a process, and the ruling of 2026-10-18 says nothing starts a session from the board. *Recommended:* keep the message. It is the owner handing work to a thread they named (R10), the same act as sending that thread a message, with the ticket as its record; nothing is sent on a trigger, and without it the ticket waits unseen. *The alternative:* `--to` records `for:` and sends nothing; the session that registers the ticket tells the thread itself, or does not.

**What needs the owner's hand.** After the plugin's first release (M1 to M3 merged), `task@doperpowers` is enabled on each machine that runs sessions (`/plugin install task@doperpowers`, or the owner's word that a session may edit the settings that list enabled plugins). M4's live checks and M5 wait on it. If M1 finds another program named `task` ahead of the plugin's on some kind of machine (Delegated unknowns), M5 waits on the owner's ruling for that kind.

**Where this document goes beyond the design as discussed.** These were decided while writing or in its review, each with its reason in the section named:

- The claim's holder is kept in appended claim records, not as a fourth field of the record block; the block keeps three of the four fields and gains `for` (D2, D3).
- Each machine keeps an index of the claims it wrote, and the release at a thread's end is a routine of the plugin, `task settle`, which sminos starts (D3, D5).
- A `/clear` grants its successor the takeover at the moment sminos sees the `/clear`. When the thread that was left ends, its successor is not sent a message; it is shown the offer at its own starts (D5).
- A takeover without a stated reason is open only along a `/clear`; every other is forced, with its reason written (D3).
- An issue is on the board when it carries a readiness label, and an outsider's issue is never takeable (D1, D8).
- A ticket is not takeable when it is `undecided`, when a blocker was closed as not planned, or when it is `planned` with no blocker (D1).
- `deferred` has no mechanical target in the relabel, an in-flight ticket gets no claim from it, and the old labels' definitions are left for the owner to delete later (D6).
- The trusted account is the one the CLI writes as, not a value in the repository; the `binding` value is the cutover switch, and it fences a checkout only once that checkout has the commit (D4, D7, D8).
- The rule that a composite's children are not tickets changes what two skills tell sessions to do: `decomposing`'s optional step 6 and `organizing-sprints`' Materialization (D7).

## Delegated unknowns

Each names the milestone that settles it and what each outcome changes.

- **Whether the confirming read of a claim sees every earlier comment** (M3). D3's arbitration assumes it, and GitHub does not document it. Acceptance 20 fires five claims at one ticket, twenty times. If every round has one winner, the assumption stands as measured and D3's accepted window stays as written. If any round has two, M3 stops and the question returns to this document's author with the evidence: D3 names the other primitive, and choosing it is a design decision.
- **Blocked-by across repositories** (M1). Several `deferred` tickets wait on another repository's work, and GitHub's documentation does not say whether a dependency may cross repositories. M1 tries one edge between two scratch issues in two scratch repositories. If it holds, `--blocked-by owner/name#n` is accepted. If not, such a wait is prose in the body and the ticket is `planned` with no edge, which D1 keeps from being takeable.
- **The `gh` client from the daemon** (M4). A settle the daemon starts must reach GitHub as the owner's account from a service's environment (a launch agent on a Mac, the supervisor on a Linux host). M4 checks each kind it can reach and says which it could not. Where `gh` does not work from the service, the rows stay owed and the next `task` verb a session runs on that machine writes them (D3): the release is late, not lost.
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

**In the plugin's suite** (the `task` gate; a stand-in `gh` that keeps issues, labels, comments, edges and their authors in a file and logs every call, and a stand-in `sminos`):

1. **The repository is named.** With `.doperpowers/board.json` naming a repository that is one of the checkout's remotes, every call the stand-in `gh` logs, `task comment`'s included, names that repository, and none asks the client to resolve one. A `repo` that matches no remote: exit 1. Without the file, or with a `binding` other than `task`, every verb that works a board exits 1 naming the file and the binding it found, and `migrate plan` runs. In a linked worktree without the file, the main checkout's is read. With `--repo`, outside any checkout, the configuration is read from that repository's default branch. `task held`, `task settle`, `task --help` and `task --version` run in a directory that is no repository.
2. **Create.** Without a category, a priority, a readiness or a body: exit 2. With them, the issue carries exactly one readiness, one horizon (`expected` unless given), the priority and the category; its body ends with a record block whose `registered-by` is the stand-in's address, and has none when no session id is set. `--blocked-by` and `--parent` write native edges, and the readiness label is the last write in the log; when the stand-in refuses the edge, the issue has no readiness label and the output says it was left untracked. `--to` a thread sminos resolves writes `for:` and sends exactly one `sminos say`; when the send fails the ticket exists and the output carries the line to send; `--to` a name sminos does not resolve exits 1 and no issue is created.
3. **Set and edge.** After any sequence of `task set`, a ticket has exactly one readiness and one horizon, and the log shows single-label adds and removes, never a replacement of the whole label set. Setting a readiness on an issue that carries a `status:*` label takes that label off. `--body-file` reads the body again before it writes and leaves a trusted record block byte for byte; on an untrusted body it drops the block and says so, and keeps it with `--keep-record`. `--due` and `--spec` change only the block. `task edge` refuses a self-edge and an edge that would close a blocked-by cycle (exit 3).
4. **Read.** `task list --json`, `show --json` and `search --json` give the shapes of Interfaces §5. `task list --takeable` holds exactly the tickets that meet D1's six conditions, with one absent case for each way of failing, each naming its reason in `not_takeable`: two readiness labels; `undecided`; an open blocker; a blocker closed as not planned; `planned` with no blocker; `claimed`; an untrusted body; `for:` another thread. `task list --untracked` shows an issue another account opened that carries only `bug`.
5. **Trust.** The trusted account is the login the stand-in `gh` is authenticated as, and an `account` key in the configuration changes nothing. A record block in a body whose author, or last editor, is another account is not read, and `task show` says so. A `task-claim` comment written by another account, or last edited by one, changes no holder.
6. **Migrate.** Over a fixture that holds every old label of D6's table, an unlabelled issue the trusted account authored, an issue another account authored that carries `bug`, a body with a `board:meta` block, a body with the retired service's banner, and a closed issue with a status label: `plan` marks each row mechanical or decision as the table says and lists the outsider's issue as incoming. `apply` exits 1 on a plan made for another repository and exits 3 while a decision row is undecided. After it, every row's issue has one readiness and one horizon and no status label; each `board:meta` key is a visible line, a pinned plan is the record's `spec:`, the banner is replaced, and the rest of each body is unchanged; the outsider's issue, a row decided "leave", the closed issue and every label definition are as they were. With the stand-in failing midway through a row, a second `apply` finishes that row; a further `apply` logs no write. An issue whose labels changed after the plan is skipped and named; an issue opened after the plan with an old status label is named in the closing list.
7. **Lint.** Each FAIL and WARN of Interfaces §6, one case each, and an untracked issue with a category label raises neither; exit 3 on any FAIL.
8. **The seam.** `task assign-human` exits 2 and says the Task Board is not built.
9. **The fold.** Each cell of D3's table, and: a closed ticket is unheld; a reopened ticket is unheld; a `claim` whose comment was created while the ticket was closed does not hold it after a reopening.
10. **Claim.** An unheld ticket: exit 0, and in the log's order a pending row, the `claim` record, the confirming read, `claimed` on, the row held with its thread id. A held one: exit 3 naming the holder, its age and the linked activity. A rival claim the stand-in inserts between the read and the append: exit 3, the loser's own comment deleted, no label written by it, its row removed. A ticket this session's thread already holds: exit 0, "already yours", no new record. A ticket whose `for:` names another thread: exit 3. A ticket that is not takeable: claimed, with the failing condition printed. No address from sminos: exit 1. No answer to `who --thread`: the row's thread is unknown; an answer with an empty `thread`: the row's thread is empty. The process killed after the append: the next settle adopts the claim into the pending row. `task claim --batch NAME` claims the batch's open tickets one by one and prints which were won.
11. **Release and close.** `task release` by the holder: in the log's order the label off, then the `release` record with `reason: released`; the row removed. By another session: exit 3 without `--force`; with it, `reason: forced: <text>`. `task close` by the holder closes the ticket, takes the label off and removes the row; of a ticket another thread holds it exits 3 without `--force`.
12. **Takeover.** With a `successor` grant for this session: exit 0, a `takeover` with `reason: cleared` naming the current claim, and the left thread's row lapsed. Without one: exit 3 unless `--force`, whose text is the reason. A takeover whose named claim is no longer current is void, deleted and reported.
13. **Settle.** (a) A row whose thread sminos says has ended, by an answer carrying that very thread id with `local` and `ended` true: label off, the `release` with `reason: ended`, the row lapsed. (b) An answer that carries another thread id, or `local` false: nothing written, the row in `unknown`. (c) `--thread T --ended`: T's rows are released without sminos being asked about T. (d) A row whose ticket is closed: label off, row removed. (e) No answer from sminos: nothing written, the row in `unknown`. (f) GitHub failing: `owed` above zero, and a second settle, or the next writing verb run on the machine, writes the release exactly once. (g) The process killed after the release was accepted and before the row was marked: the next settle marks it lapsed with `reason: ended`, leaves the label off and writes no second release. (h) A row with an empty thread is never released by settle; a row with an unknown thread is asked about again and filled in. (i) A row whose claim another session took over: lapsed, and the later holder's label left on. (j) A held row whose ticket has lost its label: the label put back. (k) Rows on two boards, one of which the stand-in refuses: the other's rows are settled and the refused board is reported. (l) All of it run from a directory that is no repository.
14. **Held.** `task held --session S --thread T --json` lists T's held rows, T's lapsed rows that are less than seven days old (on every call, not once) and, as offered, the held rows whose `successor` is S. With `--cleared-from L` it first sets `successor` to S on L's held rows and on no other thread's. It answers with the stand-in `gh` failing every call.

**In sminos's suite** (the `sminos` gates, with a stand-in `task`):

15. **The guide.** A thread's session start makes one `held` call with its session and thread and prints the line built from what is held, lapsed and offered; nothing held, lapsed or offered prints no line. A start with a `/clear` witness passes `--cleared-from <the thread left>` and prints that `task takeover <n>` takes a ticket over. With no plugin, one below the floor, one that exits non-zero and one slower than the bound, the start prints no board line and takes no longer than the bound.
16. **Retire.** For a thread its human opened, a spawned one, and a purge of each: `settle --thread <id> --ended` is called once, after the end's transition has returned; what it released is printed. A plugin that fails or is slower than the bound does not fail the retire, which says the board gave no answer.
17. **The ending pass.** Each pass starts one `settle`, never a second while one runs, and does not wait for it; a change in the count of owed or unknown rows is logged.

**Live, on scratch repositories** (`bash task/tests/live.sh <case>`, run with the worktree's own launcher against real GitHub; `TASK_LIVE_REPO` names a private scratch repository):

18. `fork` (M1): in a scratch clone whose `origin` is the scratch repository and whose `upstream` is another project, with no default recorded, `gh repo view` names the upstream project and `task list` lists the scratch repository's tickets.
19. `migrate` (M2): the scratch repository is seeded with one issue for each row of D6's table; `plan`, the decisions and `apply` leave `task lint` with no FAIL there, and a second `apply` writes nothing.
20. `race` (M3): twenty rounds of five `task claim` commands started together on one fresh ticket, each with its own invented address from the stand-in `sminos`. Each round has exactly one exit 0, and a fresh `task show --json` after it names that winner.

After M4's release is on a machine where the plugin is enabled (run by the session that holds this spec):

21. `end`: a spawned thread claims a scratch ticket and is retired: the retire prints the ticket, which then shows a `release` with `reason: ended` and no `claimed`. With `SMINOS_THREAD_END_AFTER` set short on a test home, a stopped thread's claim is released by the daemon's pass.
22. By hand, in an interactive session that holds a claim on a scratch ticket: `/clear`; the new session's guide names the ticket; `task takeover <n>` there exits 0 without `--force`; from a third session it exits 3.

**Receipts**, each taken once when its act is done and recorded in Progress with its evidence:

23. This repository's flip: the plan's counts before; after, `task lint` prints no FAIL, no open issue carries a `status:*` label, a ticket that had a hidden note shows it on its page, and the two issues that opened with the retired service's banner no longer say they are read-only.
24. An old script run against this repository after the flip (`board-list.sh`, from a plugin copy that still has it) exits non-zero with `unknown binding "task"`.
25. The skill's pressure tests: each scenario M5 lists, run without the skill and with it, recorded in the pull request that carries the skill.
26. After the first step of the cutover reaches a machine, a fresh session there lists `task:tickets`. After each board's flip, the first ticket a session registers there with `task create` is named.
27. Each sibling repository moved in M6: `task lint` there prints no FAIL, no open issue carries a `status:*` label, and its `CLAUDE.md` holds no "Board Write Hard Gate".

**Final, at M7**, repeatable:

28. `skills/issue-tracker/` is gone and `archive/issue-tracker/` holds it. No shipped skill, agent definition, `CLAUDE.md`, `README.md` or `docs/whats-inside.md` names `doperpowers:issue-tracker` or a `board-*.sh` as something to run; dated documents under `docs/doperpowers/` are not rewritten.
29. `ci-gate` on the last branch is GREEN with no `issue-tracker` or `board-api` gate, and `ci-gate --gates task` passes on it.
30. `task lint` on each moved board, which only reads, prints no FAIL.

## Execution

**Verification.** One independent review of this spec by `doperpowers:adversarial-reviewer`, and, the execution section having several milestones, that agent's buildability review of it in the same round. Each pull request is reviewed through `doperpowers:review-code`: the plugin's (M1 to M3) and sminos's (M4) at the high rung (`doperpowers:reviewer-high`), the first because it carries an arbitration rule and a trust rule for public repositories, the second because it touches the thread sweep, the retire paths and the start guide; M5's and M7's at the medium rung. M6's pull requests follow their own repositories' review.

**How it lands.** Not as one branch. M1 to M3 are one branch and one pull request, the plugin's first release. M4 is its own branch, cut from `main` when it starts, and a sminos release. M5 is two small pull requests here (what sessions read; then the flip) and a live relabel. M6 is one pull request in each sibling repository. M7 is one pull request here. A `doperpowers:plan-executor` can run M1 to M3 as one branch from this document, and M4 as another; M5 to M7 act on live boards and on other repositories and wait on the owner's answers, so the session that holds this spec runs them.

**What waits on whom.** O1 before M3 starts (the lighter design drops M4 and the lifecycle half of M3, and this document is revised before either is built). O5 before M1 ships `--to`. The plugin enabled on the machines before M4's live checks. O2 and O4 before M5's flip. O3 before M7.

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

**At its end:** `task` runs from the plugin's `bin/`. Against a board whose binding is `task`, `create`, `show`, `list`, `search`, `set`, `edge`, `comment`, `close` and `lint` behave as D1, D2, D4 and D8 say. The marketplace lists the plugin and CI runs its suite.

**Touches:** `task/` (new: `.claude-plugin/plugin.json`, `bin/task`, `cli/`, `tests/` with `run.sh`, `live.sh` and the two stand-ins, `CLAUDE.md`); `.claude-plugin/marketplace.json` (the plugin's entry); `.version-bump.json` (a `task` plugin with root `task`, its two version files and `unshipped` as sminos lists them; `task` added to doperpowers' `audit.exclude`); `.github/ci-kit.yml` (a `task` gate running `bash task/tests/run.sh`, on `task/**`); the root `CLAUDE.md` (a Repo map row for `task/`, and `--plugin task` where the other plugins' flags are named).

**Interfaces:** exposes §1, §2, §3, §5 and §6. Consumes §10 (the address for `registered-by`; the thread and the message of `--to`).

**Decisions:**

- All GitHub access sits in one module. `skills/issue-tracker/scripts/_board.py` (its snapshot query, its edge mutations) and `tests/issue-tracker/mock-gh/gh` show what the API takes and how a stand-in keeps state; they are references, not code to import or extend.
- Label writes are single-label adds and removes. A replacement of the whole set would drop a `claimed` another writer set a moment before.
- The trusted account is read from the `gh` client once per run (the authenticated login).
- `create` refuses an empty body and enforces no sections: what a body must carry is the skill's (M5). It writes a record block only when it has a key to put in it.
- A new label is created at first need, with a description that names its axis.
- `task --version` prints the version and that it is the task plugin of the doperpowers marketplace (the unknown about another `task` on `PATH`).
- sminos is found as devcloud finds it (`_sminos` in `devcloud/driver/context.py`): `TASK_SMINOS`, then `PATH`, then the marketplace clone; each call bounded at 30 seconds. The address is read from `sminos who`'s line as devcloud's `session_creator` reads it.
- The cross-repository edge is tried first, on two scratch issues in two scratch repositories (`TASK_LIVE_REPO`, `TASK_LIVE_REPO2`), and its verdict written under Delegated unknowns.
- Until M3, "unheld" is the absence of the `claimed` label, §5's `holder` is null, and `close` asks nothing about a holder.
- If O5 is answered against the message, `--to` writes `for:` and sends nothing, and acceptance 2's send is dropped.

**Does not touch:** `migrate` (M2); `claim`, `release`, `takeover`, `held`, `settle` and the index (M3); the skill (M5); the `issue-tracker` skill and its scripts; sminos's code; any issue of a real board.

**Proves:** acceptance 1 to 5, 7 without its claim rows, 8 and 18; the two unknowns it names.

### M2 — the relabel tool

**At its end:** `task migrate plan` and `task migrate apply` relabel a board as D6 says, and have done so once on a scratch repository against real GitHub.

**Touches:** `task/cli/`, `task/tests/`.

**Interfaces:** exposes §8. Consumes §1, §2 and §3.

**Decisions:**

- A row's state is read from the issue's labels at apply time (D6), never from a timestamp: the tool's own first write would change it.
- No label definition is deleted, and nothing on a closed issue or a pull request is written.
- The plan is written outside the repository's tree, readable by its owner only.
- The retired service's banner is recognized by its exact header lines and nothing looser; a body that does not match is not touched.
- Each rewritten body is carried in the plan (`body_after`), so that what the apply will write can be read first.
- `apply` needs binding `task` in the checkout like every writing verb, so it cannot run on a board the old scripts still own.

**Does not touch:** any real board; claims.

**Proves:** 6 and 19.

### M3 — claims

**At its end:** `task claim`, `release`, `takeover`, `held` and `settle` behave as D3 says, with the real sminos for identity. `show` and `list` print holders, and `close` respects one. No sminos code calls the plugin yet: `settle` is run by hand.

**Touches:** `task/cli/`, `task/tests/`, `task/CLAUDE.md` (the contract with sminos in both directions, which is where its detail lives).

**Interfaces:** exposes §4, §7 and §9; §9 is frozen at this milestone's review, since M4 builds against it. Consumes §1 to §3 and §10.

**Decisions:**

- It starts once O1 is answered. Under the lighter design this milestone is the record, the fold, `claim`, `release`, `takeover --force` and the holder in `show` and `list`; the index, `held` and `settle` are not built, and this document is revised first.
- Acceptance 20 is run first. A round with two winners stops the milestone (Delegated unknowns).
- The index is one JSON file, rewritten by atomic replace under a lock held across the read and the write: several sessions of one machine claim at once.
- Inside `claim` the order is: pending row, read and fold, append, read and fold, label, row held. Inside a release: label off, record, row. Inside a settle's release: row owed, label off, record, row lapsed. Each order is what makes the crash cases of acceptance 10, 11 and 13 come out as written.
- The thread id comes from `who --thread=<the session's own id>`: a thread id, an empty `thread` (the session is no thread), or no answer (unknown; asked again at settle).
- A board the settle cannot reach, or whose `gh` call fails, is reported in the answer and does not stop the other boards' rows.
- A lapsed row is dropped once it is seven days old, at any settle or `held`.

**Does not touch:** sminos's code; any real board; the skill.

**Proves:** 9 to 14, 7's claim rows, and 20.

### M4 — sminos calls the board at a thread's start, `/clear` and end

**At its end:** a thread's start guide lists what it holds, what lapsed and what is offered to it. After a `/clear`, the new session is told what the conversation it left holds and can take it over without force. A retire prints what it released. The daemon's ending pass starts a settle, so a thread the three-day rule ends loses its claims within that pass.

**Touches:** `sminos/skills/sminos/scripts/sminos_threads.py` (finding and asking `task`, beside `find_devcloud` and `owned_by`), `sminos_daemon.py` (the ending pass of `sweep_threads`), `sminos.py` (the guide; the `/clear` branch, where `cleared_witness` is read; the retire command, after `end_human`, `end_seat` or `end_and_stop` has returned); `sminos/tests/` (a stand-in `task`, as `devcloud_standin.py` stands in for devcloud, and the cases); `sminos/skills/sminos/scripts/CLAUDE.md` (a paragraph on the contract); the sminos version.

**Interfaces:** consumes §9. Exposes nothing: sminos gains no verb and no output key (D5).

**Decisions:**

- This milestone is for whoever holds sminos when it starts. Before branching, read what is in flight on the thread sweep, the retire paths and the start hooks, and tell its holder. At this writing that is the question sheet's sminos child (`docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`), which adds a sweep of its own to the daemon and changes the start hooks. The channels composite is not amended: every child of it has landed, and this is a change of its own to code it landed.
- The retire's call sits in the retire command after the end's transition has returned, never inside `thread_transition` and never under a thread's lock: the end and a purge are one journaled transition there, and the plugin may ask sminos questions while it runs. It is bounded at 30 seconds.
- The floor, `TASK_MIN`, is the plugin's first released version that has §9.
- The guide's call is bounded at two seconds, and a board line is printed only when something is held, lapsed or offered. The call passes the session id always and the thread id when the session has a thread record by then.
- The settle the daemon starts is run as the census is (the child process the ending pass starts to ask devcloud which threads own a machine: `start_census` in `sminos_daemon.py`): bounded, one at a time, and never waited for by the tick.
- Whether `gh` reaches GitHub from the daemon's environment is checked on each kind of machine within reach and written under Delegated unknowns.
- sminos reads nothing of the plugin's files, and the plugin nothing of sminos's.

**Does not touch:** the three-day rule's own decision (`end_due`, the census, `end_by_rule`'s guard); `who` and `who --thread`; the wake; channels; the question sheet's code.

**Proves:** 15 to 17 on the branch; 21 and 22 once its release is on a machine.

### M5 — the skill, the calling skills, and this repository's cutover

**At its end:** sessions in this repository work the board through `task:tickets` and `task`; its open issues carry the new labels; the old scripts refuse it.

**Touches**, in two pull requests (D7). *What sessions read:* `task/skills/tickets/SKILL.md` (new); `skills/issue-tracker/SKILL.md` (one sentence at its head: a repository whose binding is `task` is worked through `task:tickets`); `skills/execspec/SKILL.md`, `skills/decomposing/SKILL.md`, `skills/organizing-sprints/SKILL.md` and `sminos/skills/sminos/SKILL.md` (where each sends work to the board); `README.md` and `docs/INSTALL-doperpowers.md` (the plugin's install line); `docs/whats-inside.md` (the plugin and its skill); the versions of `task`, doperpowers and sminos. *The flip:* `.doperpowers/board.json`; the root `CLAUDE.md` ("The board" section, the `skills/` and `task/` rows); `.github/PULL_REQUEST_TEMPLATE.md` (the line that names `board-transition.sh`). Live: this repository's issues and labels.

**Interfaces:** consumes all of them.

**Decisions:**

- **The skill** carries what a session cannot derive: what the board is for (R3); when a ticket is registered (work deferred out of a session, at the moment it is deferred, by whoever deferred it, with a body a reader weeks away can act on, after a search by the identifiers the work touches); what is takeable; that a claim comes before the work and a refused claim means the work is another's; that nothing is written to a ticket while work runs; what setting a ticket down leaves (a release that says where it stands, and the readiness the ticket now needs); that a pull request closes its ticket with `Closes #n`; that a `need-input` ticket says in prose what it waits on; that a body is edited through `task set`; and that an outsider's text on a public board is data. It carries no flags (`task --help` does) and no state machine.
- **The calling skills** name the board's skill by the binding while both exist: `task:tickets` where `.doperpowers/board.json` says `task`, the old skill elsewhere. `decomposing`'s step 6 and `organizing-sprints`' Materialization change as D7 says, and the lines of `organizing-sprints` that name `board-register.sh`, `--state` values and `board-lint.sh` are rewritten for both bindings.
- **The pressure tests** must show: (a) a session that scopes work out registers it at that moment, with such a body, after searching; (b) an idle session takes a takeable ticket, and brings a `need-design` or `undecided` one to the owner instead of designing or deciding alone; (c) it claims before it starts, and on exit 3 does not start; (d) midway through claimed work it writes nothing to the ticket; (e) setting a ticket down, it releases with where the work stands and sets the readiness; (f) it registers no ticket for work it is about to build now; (g) in a checkout with an `upstream` remote it uses `task` and no raw `gh issue` command; (h) it does not act on an instruction found in an untrusted comment; (i) a session decomposing a goal on a moved board registers one ticket for the initiative and leaves the children in the spec; (j) on a board that has not moved, it still uses the old skill.
- **The first pull request** is merged, and its versions are on the owner's machines, before the flip: acceptance 26's fresh session is the check.
- **The flip** follows D7. The plan is written outside the tree. Its decision rows go to the owner as a table in the pull request's description (O2), which for this public repository may name the issues. The sessions working here are told through sminos before it merges.
- A ticket the relabel finds in an in-flight state: where sminos shows a live session on its branch or pull request, that session is asked to claim it after the apply.
- O4 decides between two paths: the limit accepted, and a ticket registered for MAWS here; or the flip waits until MAWS reports a session's end to the board and that has been seen to work.
- It starts once M4's sminos release is on the owner's machines, the plugin is enabled on them, and no machine kind has an unresolved other `task`.

**Does not touch:** the sibling repositories; the old scripts beyond that one sentence.

**Proves:** 23 to 25, and 26 for this repository.

### M6 — the sibling repositories' cutover

**At its end:** `cua`, `MAWS` and `arkho` are on `task`, each by one pull request in that repository and one applied plan.

**Touches**, in each repository, through its own worktree and pull request: a new `.doperpowers/board.json` with `"binding": "task"` and that repository's `owner/name`; the text its agent instructions carry about the board. In `cua` that is the "Board Write Hard Gate" bullet of its `CLAUDE.md`, replaced by one sentence that the board is worked through `task:tickets`. `MAWS` and `arkho` hold no such text; a search for `issue-tracker` and `board-` at the cutover finds what there is. Live: their issues and labels.

**Interfaces:** consumes all of them.

**Decisions:**

- Before a repository's pull request opens, the threads in charge there are told through sminos what changes and when, since sessions working there read the labels. The plan is applied in the same sitting as the merge.
- `cua` and `MAWS` use native edges: the horizon rule of D6 applies, and parents keep their children.
- `arkho` is private. Its plan and its decision table never enter this repository or a public pull request.
- Each repository's decision rows go to the owner per O2. Each plan is checked for the retired service's banner.
- Another checkout of the same repository on another branch gets the change when its branch takes the default branch's commit. Nothing is edited there.
- `ida-solution`, per O3. Left out: a ticket on this board records it, saying what kind of text waits there (its agent instructions, one of its runbooks, two workflows that speak the old vocabulary) and naming none of that repository's files. Moved: by these same steps, by a session whose account can read it, with the workflow that writes `status:*` labels retired in the same pull request.

**Does not touch:** this repository, beyond Progress.

**Proves:** 27, and 26 for each repository.

### M7 — the old scripts retire; the final verification

**At its end:** doperpowers no longer ships the `issue-tracker` skill, what referred to it refers to `task:tickets` alone, and the final checks have passed.

**Touches:** `skills/issue-tracker/` moves to `archive/issue-tracker/` (the skill, its scripts and references), with `tests/issue-tracker/` and `tests/claude-code/board-api/` beneath it, unwired; `.github/ci-kit.yml` (the `issue-tracker` and `board-api` gates, and those paths where other gates list them); `tests/claude-code/run-skill-tests.sh` and any test that reads the moved paths; `archive/CLAUDE.md` (what it was, and that `task:tickets` holds its surviving rules); the root `CLAUDE.md` ("The board" section; the `skills/` row and its count); the four calling skills (the old binding's branch removed); `README.md`, `docs/whats-inside.md`; `.gitignore` (the old render cache); `application-agents/triaging-feedback/` and `infra/` (the paths their documents give for the scripts, which then point into the archive; neither runs anywhere today); the versions of doperpowers and sminos.

**Interfaces:** none.

**Decisions:**

- It starts when `cua`, `MAWS` and `arkho` have moved (acceptance 27 recorded for each) and O3 has been carried out: the ticket that records leaving `ida-solution` out exists, or that repository has moved.
- Archived tests stay with what they test and are run by nothing, as `archive/experimental-context/` keeps its own.
- The final verification is acceptance 28 to 30 together with the suites (1 to 17, by `ci-gate`) and the scratch cases (18 to 20). The acts that happen once (23 to 27, and 21 and 22) are not repeated: their receipts in Progress are read and cited.

**Does not touch:** the `task` plugin's behavior; any dated document under `docs/doperpowers/`.

**Proves:** 28 to 30, and that every earlier item has a passing run or a receipt.

## Concrete Steps

From the repository's root, in the milestone's worktree. `task` below is the worktree's own launcher (`task/bin/task`) until the plugin is released.

The suites (acceptance 1 to 14 for the plugin, 15 to 17 for sminos), on the committed branch:

    ci-gate --gates task
    # PASS task … GREEN <run url>

    ci-gate
    # every gate the change touches; GREEN <run url>

    task/bin/task --version
    # task <the plugin's version> (the task plugin of the doperpowers marketplace)

The scratch cases, with a private scratch repository of the owner's account (a second one for `edge`):

    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh fork       # M1 (18)
    # gh names <the upstream project>; task lists <owner>/<scratch>
    TASK_LIVE_REPO=<owner>/<scratch> TASK_LIVE_REPO2=<owner>/<scratch2> bash task/tests/live.sh edge   # M1, the unknown
    # cross-repository blocked-by: held | refused: <GitHub's message>
    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh migrate    # M2 (19)
    # seeded <n> issues, one per row of D6's table; applied; lint: 0 FAIL; second apply: no writes
    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh race       # M3 (20)
    # 20/20 rounds: one winner each, show agrees
    # any other count: M3 stops (Delegated unknowns)

After M4's release, on a machine where the plugin is enabled (21; 22 is by hand, and `live.sh clear` prints its three steps):

    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh end
    # retire printed <owner>/<scratch>#<n>; release reason ended; label off

This repository's flip, M5 (receipts 23 and 24):

    task migrate plan --out <a file outside the tree>
    # 53 rows: 30 mechanical, 23 decisions; incoming: 0   (the counts of 2026-11-24)
    # … the decisions made, the owner's read (O2), the sessions told, the pull request merged …
    task migrate apply <that file>
    # relabelled 53, skipped 0; still carrying an old status label: none
    task lint
    # 0 FAIL
    task list --takeable
    # the ready, unclaimed, unblocked tickets, P1 first

The final checks, M7 (28 to 30):

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

`repo` is required and must be the repository of one of the checkout's git remotes. No other key is read.

**§2. Labels.** The names of D1's table, exactly; a batch is `batch:<name>`.

**§3. The record block.** The last thing in an issue's body: a fenced block whose opening line is three backticks and `task-record`, then lines `key: value`, then the closing fence, then nothing but whitespace. Keys: `registered-by`, `for` (addresses), `due` (`YYYY-MM-DD`), `spec`. An unknown key, a second such block, or one that is not last is not read, and in a trusted body is a lint FAIL.

**§4. The claim record.** A comment whose first fenced block opens with three backticks and `task-claim`. Keys: `op` (`claim`, `release`, `takeover`), `holder` (an address; on `claim` and `takeover`), `of` (a claim id; on `release` and `takeover`), `reason` (on `release`: `released`, `ended`, `forced: <text>`; on `takeover`: `cleared`, `forced: <text>`). A claim's id is the comment's numeric id. The fold is D3's table.

**§5. What the reading verbs give.** `task show <n> --json`:

    { "repo": "owner/name", "number": 548, "url": "…", "title": "…",
      "state": "open", "close_reason": null, "on_board": true,
      "readiness": "ready-to-work", "horizon": "expected", "priority": "P3",
      "category": "bug", "batch": null, "body_trusted": true,
      "record": { "registered-by": "…", "for": null, "due": null, "spec": null },
      "blocked_by": [ { "repo": "owner/name", "number": 12, "state": "open" } ],
      "parent": null, "children": [],
      "holder": { "address": "…", "claim": 2161234567, "since": "2026-11-25T03:12:09Z" },
      "linked": [ { "kind": "pr", "number": 640, "state": "open", "updated": "…" } ],
      "takeable": false, "not_takeable": [ "held" ],
      "body": "…",
      "comments": [ { "id": 1, "author": "login", "trusted": true, "created": "…", "body": "…" } ] }

A blocker's `state` is `open`, `completed` or `not-planned`. `readiness` and `horizon` are null when the issue carries none or more than one. `holder` is null for an unheld ticket. `not_takeable` names each of D1's conditions that fails: `closed`, `held`, `readiness`, `horizon`, `blocked`, `stuck` (a blocker closed as not planned), `planned-without-blocker`, `untrusted-body`, `for-another`. `task list --json` gives `{ "repo": …, "tickets": [ … ] }`, each ticket that object without `body` and `comments`. `task search --json` gives `{ "repo": …, "query": …, "hits": [ { "number", "title", "state", "url" } ] }`, each hit with `body` under `--bodies`.

**§6. Lint** reads the issues that are on the board (D1) and open issues that carry part of its vocabulary. FAIL: more than one readiness label; a ticket with no horizon label or more than one; a horizon label or `claimed` on an open issue that has no readiness label; two priorities, or two categories, on a ticket; a `status:*` label on any open issue; a blocked-by cycle; a malformed record block in a trusted body (§3). WARN: `claimed` on a ticket the fold says is unheld, or a held ticket without it; a `planned` ticket with no blocker; a ticket with a blocker closed as not planned; a ticket with no priority or no category. It also prints the number of untracked open issues, which it does not judge. Each line names the ticket and the command that repairs it. Exit 3 on any FAIL.

**§7. The index**, `claims.json` in the plugin's home (`TASK_HOME`, by default `~/.claude/task`):

    { "v": 1, "rows": [ {
        "repo": "owner/name", "number": 548, "title": "…", "url": "…",
        "claim": 2161234567, "session": "<session id>", "thread": "<thread id>",
        "address": "…", "since": "…", "successor": "",
        "state": "held", "reason": "", "at": "…", "tries": 0 } ] }

`thread` is a thread id, an empty string (sminos said the session is no thread) or null (no answer yet). `state` is `pending` (the row was written and the claim not yet confirmed; `claim` is null), `held`, `owed` (a release is due; `reason` says which) or `lapsed` (released or taken over; `reason` is `ended`, `taken-over` or `forced`). `at` is when the state last changed; a lapsed row is dropped seven days after it.

**§8. The plan file** of `task migrate plan`:

    { "v": 1, "repo": "owner/name", "read_at": "…",
      "rows": [ {
        "number": 548, "title": "…",
        "old": [ "status:ready-for-implementer", "priority:P3", "bug" ],
        "action": "relabel", "readiness": "ready-to-work", "horizon": "expected",
        "basis": "mechanical", "decided": true, "why": "",
        "body_after": null } ],
      "incoming": [ 601 ] }

`body_after` is the whole rewritten body where the apply will rewrite one (a `board:meta` block, the retired service's banner), else null. A decision row is written with `basis: "decision"`, D6's fallback values and `decided: false`; whoever settles it sets `action` (`relabel`, or `leave` for an issue that stays untracked), the two labels, `why` and `decided: true`. `incoming` lists the open issues another account authored, which the apply never writes.

**§9. What sminos calls.** Both run from any directory, print one JSON object, and exit 0 whenever they could answer, whatever the answer; exit 2 is a usage error, which is also what a plugin from before a verb or a flag gives.

`task held --session <session id> [--thread <thread id>] [--cleared-from <thread id>] --json`, which reads the index only and never the network:

    { "v": 1,
      "held":    [ { "repo", "number", "title", "url", "claim", "since" } ],
      "lapsed":  [ { "repo", "number", "title", "url", "reason", "at" } ],
      "offered": [ { "repo", "number", "title", "url", "claim", "since" } ] }

`held` and `lapsed` are the named thread's rows (empty without `--thread`); `offered` is the held rows whose `successor` is the named session. `--cleared-from` first sets `successor` to that session on the held rows of the thread it names.

`task settle [--thread <thread id> [--ended]] --json`:

    { "v": 1,
      "released":    [ { "repo", "number", "title", "url", "claim", "reason" } ],
      "closed":      [ { "repo", "number" } ],
      "lapsed":      [ { "repo", "number", "reason" } ],
      "owed": 0,
      "unknown":     [ { "repo", "number", "thread", "said" } ],
      "unreachable": [ { "repo", "said" } ] }

`--ended` is the caller stating that the named thread has ended; without it the plugin asks sminos about each row's thread. `owed` counts the rows still owed after this run.

**§10. What `task` asks of sminos** (1.53.0 or later; found through `TASK_SMINOS`, `PATH`, then the marketplace clone):

- `sminos who`, with the session's id in the environment: a line `Sminos-Session: <address>`, or nothing.
- `sminos who --thread=<name>`, always with a full session id or thread id except for the name `--to` was given: one line of JSON, of which `task` reads `thread`, `session`, `short`, `alias`, `machine`, `project.name`, `ended` and `local`. Exit 4: nothing answers the name. Exit 2: a sminos from before the flag.
- `sminos say "@<tag> <text>"`, for `create --to` only.

sminos finds the plugin through `SMINOS_TASK`, the copy beside its own plugin, the marketplace clone, then `PATH`, as `devcloud_places` orders devcloud's.

**Dependencies.** The `gh` client, authenticated as the owner's account, on every machine that runs `task`. No package beyond Python's standard library. For the scratch cases, two private scratch repositories named by `TASK_LIVE_REPO` and `TASK_LIVE_REPO2`.

## Outcomes & Retrospective

Pending — written at finish.
