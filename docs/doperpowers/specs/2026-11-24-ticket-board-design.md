# The ticket board: items, labels, claims and the `task` CLI (2026-11-24)

The owner supervises many long-running Claude Code sessions across repositories and machines. Each repository's backlog, its **board**, is that repository's GitHub issues, and sessions write it through the scripts of the `issue-tracker` skill (`skills/issue-tracker/scripts/board-*.sh`). The scripts and their eleven states were cut for an unattended dispatch pipeline that has been dormant since 2026-10-18 (`docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md`), and two faults the owner named follow from that:

- **Work leaks between sessions.** A deferred item is taken up only if some session remembers it. The in-between states (`in-design`, `in-progress`, `in-review`) are moved by hand and tied to nothing, so a ticket a session took and left keeps saying someone has it: one open ticket of this repository has read `status:in-design` since 2026-10-21, the day the pull request that references it merged.
- **No whole picture.** Who holds which piece of future work is known only by reading specs and session lists.

After this change a ticket shows three things and nothing else until GitHub's close: what it needs before work can start (**readiness**), how far off it is (**horizon**), and whether a thread has it (**claimed**). A claim belongs to the thread that made it and is released by a write when that thread ends, so a claim never outlives its holder unseen. Agents work the board through one command, `task`, shipped in a plugin of its own; the `issue-tracker` scripts, their states and the dormant dispatch machinery leave the plugin for `archive/`.

To see it working, in a session of this repository: `task list --takeable` prints the tickets a session may take on its own initiative. `task claim 548` puts `claimed` on #548 with a visible record naming the claiming session; the same command from a second session exits 3 and names the holder. Retire the first session's thread (`sminos retire`), or leave it stopped for three days: after the daemon's next pass #548 is unclaimed again, with a record that says why, and it is back in `task list --takeable`. On the issue's page the owner reads `ready-to-work`, `expected`, `priority:P3`, `bug`, the record of who registered it, and the claim. In a checkout that carries an `upstream` remote, `task list` lists this repository's tickets and not the upstream project's.

This unit gives the whole picture its data (who holds what, and one ticket per initiative pointing at its spec); the view that draws it is a later unit (Out of scope).

## Progress

- [x] (2026-11-20 to 11-24) The design discussed with the owner; the unit confirmed on 2026-11-24 (R8).
- [ ] The owner reads this document. Nothing is built, no issue is relabelled and no skill is edited before that read; "For the owner's read" lists what waits on them.
- [ ] Spec review (`doperpowers:adversarial-reviewer`: the spec, and its execution section).
- [ ] M1 — the `task` plugin: tickets, labels and the relabel tool.
- [ ] M2 — claims.
- [ ] M3 — sminos calls the board at a thread's start, `/clear` and end.
- [ ] M4 — the skill, and this repository's cutover.
- [ ] M5 — the sibling repositories' cutover.
- [ ] M6 — the old scripts retire; acceptance.

## Terms

- **The owner.** The person whose sessions these are. **The owner's account** is their GitHub account, which every session writes as: sessions have no GitHub identity of their own.
- **Board, ticket.** A board is one repository's GitHub issues read as a backlog. A ticket is an issue on a board.
- **`task`.** The command this unit builds. Three things share the word and are kept apart here: `task` is the CLI; a **ticket** is an item on a GitHub board; the owner's **Task Board** is the owner's own to-dos, a separate unit (R7, R9). The engine's in-session to-do tools are unrelated to all three.
- **Session, thread** (sminos; `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, D1). A session is one conversation with an id. A **thread** is a session's durable identity in sminos: every session the owner opens in a terminal or spawns is one. It has a record on its own machine and a thread id, stays a member when its process ends (it is then `stopped`), keeps its identity when the engine hands it to a new session id, and **ends** only by `sminos retire` or after three days stopped. A session the MAWS app launched is not a thread (sminos calls it lane B).
- **The daemon, the ending pass.** sminos's background service on each machine; once an hour its thread sweep ends the threads stopped for more than three days (`sweep_threads`, `end_due` and `end_stopped` in `sminos/skills/sminos/scripts/sminos_daemon.py`, `end_by_rule` in `sminos.py`).
- **The guide.** The lines sminos's start hook prints into a session when it starts: who it is, where it is filed, how to reach the others.
- **Address.** The line sminos puts on a session's commits and pull requests: `alias#short (project on machine)`, or `short (project on machine)` for an unnamed session, where `short` is the first eight characters of the session id. `sminos who`, run inside a session, prints it after the key `Sminos-Session: `.
- **Old vocabulary, old scripts.** The `status:*` labels and `skills/issue-tracker/scripts/`.
- **Record block, claim record, index, settle, the fold, trusted.** Defined where they are designed: D2, D3 and D8.

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

The ruling of 2026-10-18 stands: nothing starts a worker from a ticket. Nothing in this unit dispatches.

## What it must not become

- **A record of work in flight.** A session's own documents (spec, plan, pull request) hold progress (R3, R4). After a claim nothing is written to a ticket until it closes or is set down.
- **A dispatcher.** Nothing assigns work (R6). A ticket registered for a thread reaches it as an ordinary message, which the thread reads with its own judgment.
- **A second store.** GitHub is the one home of every ticket (R1, R2). No service of our own and no mirror: the retired board service mirrored tickets into GitHub issues marked read-only.
- **Bookkeeping in the middle of work**, by agents. What must be kept true while work runs is written by a machine at the moment it learns the fact (D3).
- **Typed tools for agents.** A CLI with JSON output; a tool only where the harness must draw something for the owner, which nothing here does.
- **A queue with leases**, or a channel that owns responsibilities.

## What exists today

Measured on 2026-11-24; the decisions below rest on these.

- **This repository's board.** 103 issues, 53 open, every one authored by the owner's account. On the open ones: `status:ready-for-implementer` 21, `status:deferred` 19, `status:ready-for-architect` 9, `status:in-design` 1, no status label 3; `priority:P3` 38, `P2` 11, `P1` 1, none 3; `bug` 26, `enhancement` 20, `spike` 1, no category 6. Eleven `status:*` labels exist, two of them legacy names (`status:ready-for-agent`, `status:confident-ready`); closed issues still carry eleven stale ones between them. 22 open issues carry a `board:meta` block with a note or a relation in it; the block is an HTML comment, invisible on the issue's page. No open issue has a native parent or blocked-by edge.
- **Sibling repositories.** Two public repositories of the owner's carry the old vocabulary: `cua` (214 open issues; 27 with a parent, 3 parents, 23 blocked) and `MAWS` (110 open; 9, 2, 25). The private `arkho` carries it too, and `ida-solution`, in an organization, cannot be read from the owner's account today. None of the three readable ones commits a `.doperpowers/board.json`, so each relies on the GitHub client's own resolution of the repository. The text "Board Write Hard Gate" stands in `cua`'s `CLAUDE.md`, and in `ida-solution`'s `CLAUDE.md`, one of its runbooks and, on some of its branches, its `AGENTS.md`; `ida-solution`'s checkout also holds a workflow that writes `status:*` labels and one that publishes a board page.
- **The GitHub client resolves the wrong repository in a fork.** In a fresh repository with `origin` set to this fork and `upstream` set to the project it was forked from, `gh repo view` answered the upstream project and `gh issue list` listed its issues, with no warning (gh 2.97.0). This repository's main checkout answers correctly only because a default was once recorded there.
- **The old scripts.** `_binding.sh` reads `.doperpowers/board.json` (from the main checkout when a linked worktree lacks the file) and stops on any `binding` other than `gh` or `api`: `unknown binding "<x>" — expected "gh" or "api"`. `_board.py`'s `ensure_labels` creates the `status:*` labels again whenever a script needs them.
- **GitHub.** One GraphQL query returns, for an issue and each of its comments, the author, the last editor (`editor`), the comment's id (`databaseId`) and creation time, the pull requests that reference or close it, its linked branches and its close events. Labels, native blocked-by and parent edges are written by the old scripts today through the same API.
- **sminos** (1.58.0). `sminos who` and `sminos who --thread=<name>` exist (the second since 1.53.0, one line of JSON: `thread`, `session`, `short`, `alias`, `opened`, `state`, `ended`, `local`, `machine`, `project`; exit 4 when nothing answers the name, exit 2 from an older sminos). A thread's `ended` is written by its own machine: in the ending pass, or by a retire. What a `/clear` left is known to the new session's start hooks only, through a note that is believed for a bounded time (`cleared_from` in `sminos.py`); no record keeps it. sminos asks the devcloud plugin one question through its CLI (`find_devcloud` and `owned_by` in `sminos_threads.py`): found in a fixed list of places, held to a minimum version, bounded by a timeout, and no answer is never read as "none". `sminos retire --purge` deletes a thread's record after ending it. A subagent's Bash runs with its parent session's id, and a plugin's `bin/` directory comes last on a session's `PATH`.

## Design

### D1. Items and labels

A ticket is a GitHub issue in its project's repository. Its labels:

| Axis | Labels | Rule |
|---|---|---|
| Readiness | `ready-to-work`, `need-design`, `need-input` | exactly one on every open ticket |
| Horizon | `planned`, `expected`, `undecided` | exactly one on every open ticket, kept through a claim |
| Claim | `claimed` | on while a thread holds the ticket (D3) |
| Priority | `priority:P0` … `priority:P3` | one, required at creation; unchanged from today |
| Category | `bug`, `enhancement`, `spike`, `env-issue` | one, required at creation; unchanged from today |
| Batch | `batch:<name>` | optional: a named set one agent takes whole |

- **Readiness** says what must exist before work can start (R4). `ready-to-work`: buildable from its body, or from the spec its record points at. `need-design`: its design comes first, with the owner, through doperpowers:brainstorming; it absorbs `interactive-preferred`. `need-input`: it waits on something that is neither design nor build (a decision or a real-world input only the owner holds, or research); it absorbs `needs-human` and `needs-info`, and its body says in prose what it waits on and what would unpark it. A request to the owner is not a ticket (R7), so no label marks a ticket as the owner's.
- **Horizon** says how far off the work is (R5). `planned`: its order is decided, and "after what" is a blocked-by edge. `expected`: it will be worked, in no decided order; the default. `undecided`: whether to do it at all is open.
- **The end** is GitHub's close: completed, or not planned. A closed ticket's labels mean nothing.
- **Nothing in between** (R4). Readiness and horizon stay as they were when a ticket is claimed: `need-design` with `claimed` reads "someone is designing it". When design ends the holder sets `ready-to-work` and the spec pointer; that is the one mid-life write, and it happens at a hand-over, not during work.

**What a session may take on its own initiative** (a *takeable* ticket): open, `ready-to-work`, horizon `expected` or `planned`, no open blocker, not claimed, authored by the trusted account (D8), and not registered for another thread. Any other ticket is taken on the owner's word. An `undecided` ticket is never takeable: whether to do it is the owner's call, which is what the label records. `task claim` does not enforce takeability, since the owner may name any ticket; `task list --takeable` is how a session finds the set.

**Edges** are GitHub's native ones, as today: blocked-by (a dependency) and parent (a sub-issue). `cua` and `MAWS` use both. The bookkeeping the old states carried on a parent (pulled in flight by its first active child, returned for "recomposition" when its last child lands) goes with those states: a parent is a ticket like any other, closed by whoever holds its work.

**An initiative** is at most one ticket whose record points at its spec. The children of a composite spec stay in the spec; they are not tickets, since the same fact written twice drifts (R3).

**A ticket registered for a thread.** When the owner gives work to a named thread and wants it tracked, the ticket's record names the thread (`for:`, D2), `task create --to <thread>` sends the thread one message naming the ticket, and the thread claims it when it takes it. It is not born claimed: a claim is written by its holder's own machine (D3), which is the only machine that can release it.

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

`registered-by` is the address of the session that created the ticket (absent when no session did); `for` the thread it was registered for (D1); `due` a date the work must be done by; `spec` a repository-relative path, optionally `@<sha>`, or a URL when the spec lives in another repository. Every key is optional, each value is one line, and the block is read only when it is the last thing in the body and its author is trusted (D8). It is a fenced block and not an HTML comment because the block it replaces, `board:meta`, was invisible on the issue's page, and a status note the owner cannot see is of no use to them.

The claim's holder is not in this block (D3 says why). Lineage that the old block carried (`spawned-by`, `relates-to`) is prose in the body: a mention of `#n` already cross-links both issues on GitHub.

Every body write by the CLI replaces the text above the block and keeps the block byte for byte. A raw `gh issue edit --body` drops it, and nothing can tell afterwards that it was there, so the skill sends every body edit through `task set` (M4).

### D3. Claims

A claim says a thread has taken a ticket. It belongs to the thread, so it survives a compaction, a hand-off to a new session id and a stopped process, and it changes only by a write: a release by its holder, a release by the holder's machine when the thread ends, or a takeover. No reader infers that a claim has lapsed, because a thread that looks gone can return: its human reopens it. There is no lease: a lease must be renewed, and renewal is bookkeeping in the middle of work (R4); a long-lived thread's claim would lapse under it while the thread works.

**The record.** Each change of a claim is one comment on the ticket, written by the CLI, holding one fenced block and, after it, any prose the writer adds (where the work stands, at a release):

````
```task-claim
op: claim
holder: builder#1a2b3c4d (doperpowers on laptop)
```
````

`op` is `claim`, `release` or `takeover`. A claim's **id** is the GitHub id of the comment that made it (a `claim` or a `takeover`). `release` carries `of: <claim id>` and `reason:` (`released`, `ended`, or `forced: <text>`); `takeover` carries `of:`, `holder:` and `reason:`. The holder is written as the claiming session's address: what every commit of that session already publishes, and nothing else of sminos's (no thread id, no project id). A subagent's claim is its session's, since its commands run with the parent session's id.

**The fold.** Who holds a ticket is computed the same way by every reader. Take the ticket's comments in GitHub's order (ascending id), keep those that carry a `task-claim` block, are trusted (D8) and were created after the ticket's last close, and apply:

| Record | Ticket unheld | Ticket held by claim *c* |
|---|---|---|
| `claim` (comment *k*) | held by *k* | void |
| `release` of *x* | void | *x* = *c*: unheld; otherwise void |
| `takeover` of *x* (comment *k*) | void | *x* = *c*: held by *k*; otherwise void |

A void record changes nothing. A close ends every claim: a reopened ticket starts unheld.

**The linearization point** of every change is GitHub's assignment of the comment's place in that order. So `task claim` reads and folds; if the ticket is held it refuses; otherwise it appends its `claim`, reads and folds again, and holds the ticket only if the fold names its own comment. A writer that finds its record void deletes it and reports who won. Two claims seconds apart therefore have exactly one winner, which today's scripts cannot promise (their claim rewrites labels with nothing to arbitrate).

*Alternative weighed: the holder as a field of the record block.* It lost on two counts. The body is one string with no partial update, so a claim, a release and an edit of the ticket's text would overwrite one another, and a release lost that way leaves a ticket held by a thread that has ended. And a single field holds no history, while a takeover has to name the claim it supersedes so that a stale one is void. *Alternative: GitHub's assignee.* Every session writes as the one owner's account, so an assignee cannot tell two threads apart.

**The label.** `claimed` is set by a claim's winner once the fold confirms it and removed by whoever writes the release. The fold is the truth; the label is what lists and the owner read, and each write that learns the two disagree repairs it (`task lint` reports it).

**The index.** Each machine keeps, in the plugin's own directory, one row per claim it wrote that it has not yet seen end: the repository, the ticket, the claim's id, the claiming session and its thread id (both private to the machine), when, and a `successor` once a `/clear` granted one. It exists so that the machine can answer "what does this thread hold" at a session's start without a network call, and can find a thread's claims when the thread ends without scanning every repository. It holds nothing of a ticket's content and decides nothing: every act reads the ticket again. If it is lost, the claims stay as they are on GitHub and their automatic release is lost with it; their holders can still release them, and anyone can take them over with a reason. *Alternative: no index, a scan of GitHub.* It lost because the start of every session would wait on the network, and because a machine would need a list of every board it ever wrote to, which is an index by another name.

**Events, and who writes.** Every label the owner reads is kept true by a write from the machine that learns the fact first.

| Event | Writer | Written on GitHub | Index |
|---|---|---|---|
| A session claims | that session's `task claim` | `claim` record; `claimed` on | row added |
| The holder sets the ticket down | its `task release` | `release` (`released`); label off | row removed |
| The holder's thread ends (a retire, or three days stopped) | its machine: `task settle`, started by sminos (D5) | `release` (`ended`); label off | row kept as *lapsed* until the thread next asks |
| A `/clear` in the holder's process | sminos's guide in the new session (D5) | nothing: the claims stay with the thread that was left | its rows gain the new session as `successor` |
| The successor takes over | its `task takeover` | `takeover` | the left thread's row turns lapsed; a row is added for the taker |
| Another session takes over | its `task takeover` | `takeover`, with the reason | a row for the taker; the former holder's machine marks its row lapsed at its next settle |
| The ticket closes (a merge, or `task close`) | `task close`; else the holder's machine at its next settle | label off | row removed |
| GitHub is unreachable when a release is due | — | — | row marked *owed*; every later settle, and every later `task` verb on that machine that writes to GitHub, tries it again first |
| The holder's machine is retired, or its index is lost | nobody | — | a takeover is the way out |

**Settle** is the one routine that makes a machine's claims true. For each row (of one thread, or all): if the fold no longer names the row's claim, mark it lapsed (taken over, or released by force); if the ticket is closed, take the label off and drop the row; if the row has a thread id and sminos says that thread has ended on this machine, mark the row owed, write the release, and tell a live successor; if sminos gives no answer, change nothing and report the row as unknown. The plugin asks sminos about each thread, and sminos does not hand the plugin a list of what ended, because a crash between sminos writing an end and telling the plugin would lose the release for good, while a settle that failed is simply run again. A purged thread, about which sminos no longer answers, is covered by sminos calling settle before the purge (D5). Every later `task` verb on the machine that writes to GitHub runs the owed rows first, so a release that failed does not wait for the next pass.

**Takeover.** `task takeover <n>` writes a `takeover` of the current claim. It is allowed without a stated reason in two cases: the index holds a `successor` grant for this session on that claim (the `/clear` path), or sminos answers that the holder has ended. Anything else, including no answer from sminos, needs `--force "<reason>"`, and the reason is written in the record: taking a live thread's ticket means two sessions building one thing, and the one who decides that is the owner. `task release` and `task close` follow the same rule: the holder acts on its own claim (the index row is its thread's, or the record's address is its session's), and anyone else needs `--force "<reason>"`.

**A returned thread.** A thread that ended and is reopened by its human does not get its claims back: they were released, and another session may hold the ticket. Its first `task held` reports each lapsed row once, with why, so its guide can tell it to claim again before it continues.

**What a reader is shown.** `task show` prints the holder's address, the claim's age, and the last activity on the pull requests and branches GitHub links to the ticket. With no lease, that is what lets a reader judge a claim that has gone quiet.

**Stated limits.** A session the MAWS app launched is not a thread: no machine learns that it ended for good, so its claims are released only by itself or by a forced takeover (O3). A claim written from a machine with no running daemon is released only at a retire.

### D4. The `task` CLI and its plugin

A new plugin, `task`, in this marketplace (`task/` at the repository's root, versioned on its own). Its command is `task` (R9), its skill `task:tickets`. It is a plugin of its own, and not part of doperpowers or sminos, so that it rides neither's releases: a board fix must not wait for, or force, a sminos release, and sminos must run without it.

**Two destinations, one built.** `task` is the agents' one command for tracked work (R9). Every verb this unit builds acts on tickets. Verbs that write to the human's Task Board (the owner's example: `task assign-human`) belong to the separate unit that designs it; the command's dispatch keeps one flat verb namespace with those names unused, and `task assign-human` exits 2 saying that the Task Board is not built.

**The repository is named, never resolved.** A board's repository is the `repo` of the checkout's committed `.doperpowers/board.json`, and every call to GitHub names it. The CLI never asks the GitHub client which repository a directory belongs to (see "What exists today": in a fork the client answers the upstream project). `--repo owner/name` works a board from outside its checkout; its configuration is then read from that repository's default branch.

**The binding is the cutover switch.** `binding` in that file says which tool owns the board. `"task"`: this CLI. Anything else: every verb but `task migrate plan` refuses, naming the file. The old scripts already refuse a binding they do not know, so one committed line moves a repository from one tool to the other, in every checkout and every installed version at once (D7).

**Verbs.**

| Verb | Does |
|---|---|
| `task create <title> --category C --priority P --readiness R --body-file F` `[--horizon H] [--blocked-by N,…] [--parent N] [--batch NAME] [--due DATE] [--spec S] [--to THREAD]` | opens the ticket with its labels, edges and record block; prints `<number> <url>` |
| `task show <n>` | the ticket: labels, record, edges, the holder with its age and linked activity, the body, the comments, each marked with whether a trusted account wrote it |
| `task list` `[--takeable] [--readiness R] [--horizon H] [--claimed\|--unclaimed] [--batch NAME] [--untracked]` | open tickets by priority, then number: readiness, horizon, priority, holder, open blockers, `for`, `due`, title. `--untracked` lists the open issues that carry no readiness label instead |
| `task search <query> [--state open\|closed\|all] [--bodies]` | GitHub's issue search, held to the board's repository |
| `task set <n>` `[--readiness R] [--horizon H] [--priority P] [--category C] [--batch NAME\|--no-batch] [--due D\|--no-due] [--spec S\|--no-spec] [--to T\|--no-to] [--title T] [--body-file F]` | changes labels, the record block, the title or the text above the block |
| `task edge <n> --block N \| --unblock N \| --parent N \| --orphan` | one edge; refuses a self-edge and a blocked-by cycle |
| `task comment <n> --body-file F` | a comment, so that no session needs a raw client call, which could resolve the wrong repository |
| `task claim <n>… \| --batch NAME`, `task release <n> [--body-file F] [--force R]`, `task takeover <n> [--force R]` | D3. Several tickets are claimed one by one, and the output says which were won |
| `task close <n> [--not-planned] [--body-file F] [--force R]` | closes it, completed unless told otherwise; refuses a ticket another thread holds, without `--force` |
| `task lint` | the invariants over the live board (Interfaces §6) |
| `task migrate plan`, `task migrate apply <plan>` | the one-time relabel (D6) |
| `task held`, `task settle` | what sminos calls (D5); a session may run either by hand |

Every reading verb takes `--json`. Exit codes: 0 done; 1 failed (GitHub, the configuration, a sminos answer the verb cannot do without); 2 usage, or a verb this unit does not build; 3 refused by a rule of the board (held by another, not the holder, a failed lint, a plan with undecided rows).

**It writes as the owner's account**, through the `gh` client's own credential, as the old scripts do. The session that wrote is named in the record.

### D5. The contract with sminos

Two plugins, one narrow contract in each direction, in the manner of sminos and devcloud: each side finds the other's CLI, asks one bounded question, and treats silence as no answer.

**`task` asks sminos** (nothing new in sminos; 1.53.0 or later):

| Call | For | Without an answer |
|---|---|---|
| `sminos who`, inside a session | the session's address: `holder`, `registered-by` | `claim` and `takeover` refuse (exit 1): a claim belongs to a thread sminos knows. `create` writes no `registered-by` |
| `sminos who --thread=<session or thread id>` | the calling session's thread id, kept in the index; whether a holder or a row's thread has ended; the thread `--to` names | the row has no thread id and no lifecycle release; a takeover needs `--force`; settle reports the row unknown |
| `sminos say "@<thread> <text>"` | the message to the thread of `--to`; the message to a live successor at a lapse (a machine's notice, `--notice task`, when no session runs it) | the output says the message was not sent and prints the line to send |

**sminos calls `task`** (M3 adds these four calls and nothing else):

| When | Call | sminos does |
|---|---|---|
| A thread's session starts (the guide) | `task held --thread <thread id> --json` | prints one guide line: what the thread holds, and what lapsed |
| A session starts with a witness of a `/clear` | `task held --thread <the thread left> --grant <the new session id> --json` | prints what the conversation it left holds, and that `task takeover <n>` takes one over |
| A retire has written a thread's `ended`, before any purge | `task settle --thread <thread id> --json` | prints what was released |
| The daemon's ending pass, each time it runs | `task settle --json`, as a child the tick does not wait for | logs a failure once per distinct failure |

sminos finds `task` as it finds devcloud (an override variable, the copy beside its own plugin, the marketplace clone, then `PATH`), reads the plugin's version from its manifest and asks nothing of one below the floor, bounds each call, and reads a missing plugin, an old one, a timeout or a non-zero exit as no answer: no line, nothing printed. It never reads the plugin's files, and no session start, retire or pass fails or waits past its bound because of the board.

sminos is the caller at these moments because it alone knows them: it owns the guide, it holds the only witness of a `/clear`, and it writes every thread's end. The grant is recorded at the moment sminos has its witness in hand, because nothing keeps that witness afterwards; so the takeover that follows needs no question to sminos.

The release at a thread's end happens within the pass that ended it (the daemon starts settle each pass), and its live successor is told in the same settle. Whether the message goes out before or after the release makes no difference to the successor, which acts at its next turn either way.

### D6. The relabel

Existing issues are relabelled once per repository, by a plan a session reads before it is applied.

`task migrate plan` needs only a repository (the configuration's `repo`, or `--repo`), since it runs before a board has moved. It reads the live issues and writes a plan: one row per open issue with its old labels, the new readiness and horizon, and whether the row is **mechanical** (the old label decides it) or a **decision** (it does not). `task migrate apply <plan>` refuses while a decision row is undecided; then it creates the new labels, relabels each open issue, makes each `board:meta` block visible, and last deletes the old labels from the repository, which also takes them off closed issues. A row whose issue changed since the plan was written is skipped and reported; a second apply changes nothing. The plan file names every issue with its old labels, so it is the record a reversal would work from; it is kept outside the repository's tree (a private repository's titles must not land in this public one).

*Alternative weighed: keep the old labels and translate them when reading.* It lost to R4: the owner reads the labels on GitHub itself, where nothing translates.

The mapping covers every label in use on the four repositories' boards; the counts are this repository's open issues.

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
| no status label, or two | 3 | by reading | by reading | decision |

*Horizon by rule:* `planned` when the issue has an open blocker, else `expected`.

- **`deferred` has no mechanical target.** It said "tracked, not now", which mixed work that will be done later with work that may never be, and it hid whether the ticket needs design. Each is read. Where reading does not settle it, the fallback is `need-design` and `undecided`: the pair that keeps a session from building it on its own initiative until someone has looked.
- **A ticket in an in-flight state gets no claim from the relabel.** A claim is written by its holder's machine. The plan lists such tickets; where a live session is found to be on one, it is asked to claim it after the cutover, and otherwise the ticket returns to the backlog with a visible line saying which state, branch and pull request it had.
- **The `board:meta` block becomes visible.** Each key it carries is rewritten as a line of the body above the record block (a `note` as "Board note:", `relates-to` and `spawned-by` as mentions, a `branch` or `pr` as it stood), except a pinned `plan:`, which becomes the record's `spec:`. Everything else in the body stays byte for byte. A `needs-human` ticket's note is its question list, so this is also what makes a `need-input` ticket say in prose what it waits on.
- **Other labels.** `priority:*` and the four categories are kept; an issue without one is reported, never given one. `engine:claude` (the dormant dispatch's worker route) and any `surface:*` label are deleted. Labels that are not the board's (`tech-debt`, the pull-request label `confident-ready`, `accessibility`, GitHub's defaults) are not touched.

For this repository that is 30 mechanical rows and 23 decisions (O1).

### D7. Cutover and retirement

A repository moves in one sitting: the plan is written and its decisions made; a pull request in that repository sets `"binding": "task"` (adding `.doperpowers/board.json` where there is none) and replaces the text its `CLAUDE.md` carries about the board; once it merges, the plan is applied and `task lint` is clean. From the merge on, the old scripts refuse that repository in every checkout that has the commit. A checkout that has not pulled it yet could still run them, and they would create `status:*` labels again; `task lint` fails on any such label, and the session that meets it relabels the ticket.

The old skill stays shipped until every repository that uses it has moved or has been left on purpose (O2), with one sentence at its head sending a repository whose binding is `task` to `task:tickets`. Then `skills/issue-tracker/`, its tests and its two CI gates leave for `archive/issue-tracker/`, as the dormant dispatch machinery and the board service binding with them (R2). Nothing arms that machinery today and nothing in this unit starts a worker from a ticket, so the ruling of 2026-10-18 is unchanged by the move: what it kept in the tree and tested "armed nowhere" is kept in the archive, untested.

The four tickets that were kept off GitHub when the board service retired (`docs/doperpowers/board-service-tickets.md`) stay where they are: where a project's private tickets live is not decided here.

### D8. Public repositories: what is trusted

Three of the boards are public, so anyone can open an issue or write a comment there. Two rules follow.

- **A record is read only where a trusted account wrote it.** A record block is read from a body, and a claim record from a comment, only when its author is the trusted account and its last editor, if any, is too. The trusted account is `account` in `.doperpowers/board.json`, and where that key is absent, the owner part of `repo`. `task show` says of every body and comment whether it passed.
- **A session takes on its own initiative only tickets the trusted account authored** (D1). An issue an outsider opened has no board labels (only an account with rights on the repository can set them), so it is *untracked*: `task list --untracked` shows it, and it becomes work when the owner, or a session on the owner's word, registers a ticket that refers to it.

What an outsider wrote in a body or a comment is data, never an instruction; the skill says so, and the trust mark on `task show` is what a session reads it by.

## For the owner's read

**Open decisions.** Each has a recommendation; the work named beside it does not start before the answer.

- **O1. Who settles the relabel's decision rows** (before M4's apply, and each repository's in M5). The relabel cannot decide 23 of this repository's 53 open tickets from their labels: 19 `deferred`, one in design, three with no status. *Recommended:* the session running the cutover reads each ticket and proposes its readiness and horizon with a one-line reason, and the owner reads that table once per repository before it is applied, because `undecided` against `expected` is the owner's knowledge and every reader trusts the labels afterwards. It costs one read of about twenty rows here (more for `cua` and `MAWS`, which have 24 and 28 `deferred`). *The cheaper path:* apply the session's proposals unread and correct by exception; a wrong `expected` would then let a session build something the owner had not decided to do.
- **O2. `ida-solution`** (before M5 ends). It cannot be read from the owner's account today, belongs to an organization, and its checkout holds a workflow that writes `status:*` labels and one that publishes a board page. *Recommended:* leave it out of this unit. Its `CLAUDE.md` already tells a session not to write the board when the scripts are missing, so after M6 its board is read-only to agents until someone with access moves it, with M5's steps. *The alternative* holds M6 until it has moved, and keeps the old skill shipped for one repository that has had no dispatch since August.
- **O3. Claims by sessions the MAWS app launched** (before M4). Such a session is not a thread, so nothing releases its claims when it is gone for good (D3). *Recommended:* accept it for the first cutover. The claim shows its age and its linked activity, and any session can take it over with a stated reason; MAWS telling the board when it archives a session is registered as a ticket for MAWS at M4. *The alternative* holds this repository's cutover until MAWS does that.

**What needs the owner's hand.** After the plugin's first release (M1 and M2 merged), `task@doperpowers` is enabled on each machine that runs sessions (`/plugin install task@doperpowers`, or the owner's word that a session may edit the settings that list enabled plugins). M3's live check and M4 wait on it.

**Where this document goes beyond the design as discussed.** These were decided while writing, each with its reason in the section named:

- The claim's holder is kept in appended claim records, not as a fourth field of the record block; the block keeps three of the four fields and gains `for` (D2, D3).
- Each machine keeps an index of the claims it wrote (D3).
- The release at a thread's end is done by a routine of the plugin, `task settle`, which sminos starts and which asks sminos about each thread (D3, D5).
- A `/clear` grants its successor the takeover at the moment sminos sees the `/clear`, since sminos keeps no lasting record of which session a `/clear` left (D5).
- `deferred` has no mechanical target in the relabel, and an in-flight ticket gets no claim from it (D6).
- The `binding` value is the cutover switch (D4, D7).
- An `undecided` ticket is never takeable (D1).

## Delegated unknowns

Each names the milestone that settles it. None changes a decision above; each changes how often a fallback is used.

- **Blocked-by across repositories** (M1). Several `deferred` tickets wait on another repository's work, and GitHub's documentation does not say whether a dependency may cross repositories. M1 tries one edge between two scratch issues in two repositories. If it holds, `--blocked-by owner/name#n` is accepted and such a ticket is `planned`; if not, the wait is prose in the body and `task lint` only warns about a `planned` ticket without a blocker.
- **Comment order under concurrent appends** (M2). The fold assumes every reader sees one order. Acceptance 18 fires parallel claims at one ticket and requires one winner that every reader agrees on.
- **The `gh` client from the daemon** (M3). A settle the daemon starts must reach GitHub as the owner's account from a service's environment (a launch agent on a Mac, the supervisor on a Linux host). M3 checks both. Where it cannot, the rows stay owed and the next `task` verb a session runs on that machine writes them (D3), so the release is late, not lost.
- **What sminos answers about a holder named by its short id from another machine** (M2): for a stopped holder, one ended by the rule, and one on a retired machine. The takeover rule holds whatever the answers are; they decide how often `--force` is needed.
- **Another `task` on `PATH`** (M1). A plugin's `bin/` comes last on a session's `PATH`, and two widely installed tools (Taskwarrior, go-task) install a command of this name. None of the owner's Macs has one today. M1 checks every kind of machine the owner runs sessions on (`command -v task`), and `task --version` says which program answered. Where another `task` is found it is reported to the owner before M4; the name is the owner's (R9).

## Out of scope

- **Requests to the owner and the owner's to-dos**: the Task Board (R7, R9). `task` leaves its verbs unused (D4).
- **Events and subscriptions** (R8).
- **The view of the whole picture**: which initiatives are in flight and who holds them, drawn from claims, specs and sessions. A later unit, in sminos's session manager.
- **Agents with a GitHub identity of their own.** D8 names the trusted account in configuration so that it can become more than one.
- **A private repository for tickets that cannot be public** (D7).
- **The board map** (`board-map.sh`, the hosted board pages): it draws the old states and is archived with them.

## Acceptance

In the plugin's suite (`bash task/tests/run.sh`; a stand-in `gh` that keeps issues, labels, comments and edges in a file and logs every call, and a stand-in `sminos`):

1. **The repository is named.** With `.doperpowers/board.json` naming a repository, every call the stand-in `gh` logs, `task comment`'s included, names that repository, and none asks the client to resolve one. Without the file, or with a `binding` other than `task`, every verb but `migrate plan` exits 1 naming the file and the binding it found. In a linked worktree without the file, the main checkout's is read. With `--repo`, outside any checkout, the configuration is read from that repository's default branch.
2. **Create.** `task create` without a category, a priority, a readiness or a body exits 2. With them, the issue carries exactly one readiness, one horizon (`expected` unless given), the priority and the category; its body ends with a record block whose `registered-by` is the stand-in's address, and has none when no session id is set. `--blocked-by` and `--parent` write native edges. `--to` writes `for:` and sends exactly one `sminos say`; when that fails the ticket exists and the output carries the line to send.
3. **Set.** After any sequence of `task set`, an open ticket has exactly one readiness and one horizon, and the log shows single-label adds and removes, never a replacement of the whole label set. `--body-file` leaves the record block byte for byte; `--due` and `--spec` change only the block. `task edge` refuses a self-edge and an edge that would close a blocked-by cycle (exit 3).
4. **Read.** `task list --json`, `show --json` and `search --json` give the shapes of Interfaces §5. `task list --takeable` holds exactly the tickets that meet D1's seven conditions, each condition's failing case shown absent.
5. **Trust.** A record block in a body whose author, or last editor, is not the trusted account is not read, and `task show` says so. A `task-claim` comment by another account changes no holder.
6. **The fold.** Each cell of D3's table, and: records created before the ticket's last close are ignored; a reopened ticket is unheld.
7. **Claim.** An unheld ticket: exit 0, the `claim` record, `claimed` on, an index row with the thread id. A held one: exit 3 naming the holder, its age and the linked activity. A rival claim the stand-in inserts between the read and the append: exit 3, the loser's own comment deleted, no label written by it, no row. A ticket whose `for:` names another thread: exit 3 without `--force`. No address from sminos: exit 1. `task claim --batch NAME` claims the batch's open tickets one by one and prints which were won.
8. **Release and close.** `task release` by the holder: the `release` record with `reason: released`, label off, row removed. By another session: exit 3 without `--force`; with it, `reason: forced: <text>`. `task close` by the holder closes the ticket, takes the label off and removes the row; of a ticket another thread holds it exits 3 without `--force`.
9. **Takeover.** With a `successor` grant for this session: exit 0, a `takeover` naming the current claim. With sminos answering that the holder ended: the same. Otherwise exit 3 without `--force`. A takeover whose named claim is no longer current is void, deleted, and reported.
10. **Settle.** A row whose thread sminos says ended, locally: the `release` (`ended`), label off, the row lapsed, one message to a successor sminos says is live. A row whose ticket is closed: label off, row removed. No answer from sminos: nothing written, the row in `unknown`. GitHub failing: `owed` above zero, and a second settle, or the next writing verb run on the machine, writes the release exactly once. A row without a thread id is never released by settle. A row whose claim the fold no longer names: lapsed, nothing written.
11. **Held.** `task held --thread T --json` lists T's rows and its lapsed rows, the lapsed ones once only. `--grant S` sets `successor` on T's rows and on no other thread's. Both answer with the stand-in `gh` failing every call.
12. **Lint.** Each FAIL and WARN of Interfaces §6, one case each; exit 3 on any FAIL.
13. **Migrate.** Over a fixture holding every old label of D6's table: `plan` marks each row mechanical or decision as the table says; `apply` exits 3 while a decision row is undecided; then every open issue has one readiness and one horizon, each `board:meta` key is a visible line and the rest of each body is unchanged, a pinned plan is the record's `spec:`, no `status:*` label exists, and the labels D6 leaves alone are as they were. A second `apply` logs no write. A row whose issue changed after the plan is skipped and named.
14. **The seam.** `task assign-human` exits 2 and says the Task Board is not built.

In sminos's suite (`sminos/tests/run-sminos-tests.sh`, with a stand-in `task`):

15. **The guide.** A thread's session start prints the line built from `held`; a `/clear` start calls `held` for the thread left with `--grant <the new session's id>` and prints the takeover line. With no plugin, one below the floor, one that exits non-zero and one slower than the bound, the start prints no board line and takes no longer than the bound.
16. **Retire.** `settle --thread <id>` is called after the thread's `ended` is written and before a purge; what it released is printed; a failing plugin does not fail the retire.
17. **The ending pass.** Each pass starts one `settle`, never a second while one runs, and does not wait for it.

Live, on a private scratch repository named by `TASK_LIVE_REPO`, with real GitHub and real sminos (`bash task/tests/live.sh`):

18. Twenty rounds of five `task claim` commands started together on one fresh ticket: each round has exactly one exit 0, and `task show --json` run after each round from two machines names the same holder.
19. A spawned thread claims a ticket and is retired: the retire prints the ticket, which then shows a `release` with `reason: ended` and no `claimed`. With `SMINOS_THREAD_END_AFTER` set short on a test home, a stopped thread's claim is released by the daemon's pass with `reason: ended`.
20. In an interactive session that holds a claim, `/clear`: the new session's guide names the ticket; `task takeover <n>` there exits 0 without `--force`; from a third session it exits 3.
21. In a scratch clone whose `origin` is the scratch repository and whose `upstream` is another project, with no default recorded, `gh repo view` names the upstream project and `task list` lists the scratch repository's tickets.

On this repository, after M4:

22. `task lint` prints no FAIL. Every open issue that had a status label has exactly one readiness and one horizon; no `status:*` label exists (`gh label list` on the repository named in `.doperpowers/board.json`); the number of open tickets equals the plan's rows; a ticket that had a hidden note shows it on its page.
23. An old script run against this repository from a plugin copy that still has it (`board-list.sh`) exits non-zero with `unknown binding "task"`.
24. The skill's pressure tests show the behaviors M4 lists.

On each sibling repository moved in M5:

25. `task lint` there prints no FAIL, no `status:*` label exists, its `CLAUDE.md` holds no "Board Write Hard Gate", and a session started there after the merge registers a ticket with `task create`.

After M6:

26. `skills/issue-tracker/` is gone and `archive/issue-tracker/` holds it. No shipped skill, agent definition, `CLAUDE.md`, `README.md` or `docs/whats-inside.md` names `doperpowers:issue-tracker` or a `board-*.sh` as something to run; history under `docs/doperpowers/` is not rewritten.
27. `ci-gate` on the last branch is GREEN, with the `task` gate in it and the `issue-tracker` and `board-api` gates gone.

## Execution

**Verification.** One independent review of this spec by `doperpowers:adversarial-reviewer`, and, the execution section having six milestones, that agent's buildability review of it in the same round. Each pull request is reviewed through `doperpowers:review-code`: the plugin's (M1 and M2) and sminos's (M3) at the high rung (`doperpowers:reviewer-high`), the first because it carries a concurrency rule and a trust rule for public repositories, the second because it touches the thread sweep, the retire paths and the start guide; M4's and M6's at the medium rung. M5's pull requests follow their own repositories' review.

**How it lands.** Not as one branch. M1 and M2 are one branch and one pull request, the plugin's first release. M3 is its own branch, cut from `main` when it starts, and a sminos release. M4 is a small pull request here and a live relabel. M5 is one pull request in each sibling repository. M6 is one pull request here. A `doperpowers:plan-executor` can run M1 and M2 as one branch from this document, and M3 as another once the plugin is released and enabled; M4 to M6 act on live boards and on other repositories and wait on the owner's answers (O1 to O3), so the session that holds this spec runs them.

**Binding on every milestone.**

- This repository is public: no hostnames, IPs, accounts, project ids, secret names or values, or local absolute paths in code, comments, committed fixtures, documents or commit messages. Fixtures use invented addresses, as this document's examples do.
- The `task` plugin is Python 3.9, standard library only, as sminos's CLI is; it imports nothing of doperpowers or sminos, and reaches GitHub only through `gh api` with the repository named in the call.
- No issue or label of a real board is written before M4. M1 to M3 run against the stand-ins and the scratch repository of `TASK_LIVE_REPO`.
- Nothing starts a worker from a ticket (the ruling of 2026-10-18).
- Verify a commit with `ci-gate` from the worktree; do not run the gates' commands locally. One focused test file while iterating is fine.
- Versions move in the commit that changes a shipped file: `scripts/bump-version.sh --plugin task` (the plugin is created at 0.1.0), `--plugin sminos` once in M3, doperpowers' own in M4 and M6.
- Skill text (M4's new skill, M6's reference swaps) goes through doperpowers:writing-skills.
- A Repo map row in the root `CLAUDE.md` orients in a sentence or two; the plugin's detail is in `task/CLAUDE.md`. `README.md` and `docs/whats-inside.md` follow the tree in the same change.
- Dated documents under `docs/doperpowers/` are history and are not rewritten; `docs/doperpowers/board-service-tickets.md` stays as it is.

### M1 — the `task` plugin: tickets, labels and the relabel tool

**At its end:** on a machine where the plugin is enabled, `task` runs in every session. Against a board whose binding is `task`, `create`, `show`, `list`, `search`, `set`, `edge`, `comment`, `close` and `lint` behave as D1, D2, D4 and D8 say; `task migrate plan` and `apply` relabel a board as D6 says. The marketplace lists the plugin and CI runs its suite.

**Touches:** `task/` (new: `.claude-plugin/plugin.json`, `bin/task`, `cli/`, `tests/` with `run.sh`, `live.sh` and the two stand-ins, `CLAUDE.md`); `.claude-plugin/marketplace.json` (the plugin's entry); `.version-bump.json` (a `task` plugin with root `task`, its two version files and `unshipped` as sminos lists them; `task` added to doperpowers' `audit.exclude`); `.github/ci-kit.yml` (a `task` gate running `bash task/tests/run.sh`, on `task/**`); the root `CLAUDE.md` (a Repo map row for `task/`, and `--plugin task` where the other plugins' flags are named).

**Interfaces:** exposes §1, §2, §3, §5, §6 and §8. Consumes none.

**Decisions:**

- All GitHub access sits in one module. `skills/issue-tracker/scripts/_board.py` (its snapshot query, its edge mutations) and `tests/issue-tracker/mock-gh/gh` show what the API takes and how a stand-in keeps state; they are references, not code to import or extend.
- Label writes are single-label adds and removes. A replacement of the whole set would drop a `claimed` another writer set a moment before.
- `create` refuses an empty body and enforces no sections: what a body must carry is the skill's (M4). It writes a record block only when it has a key to put in it.
- A new label is created at first need, with a description that names its axis.
- `migrate apply` needs binding `task` in the checkout like every writing verb, so it cannot run on a board the old scripts still own.
- `task --version` prints the version and that it is the task plugin of the doperpowers marketplace (the unknown about another `task` on `PATH`).
- The cross-repository edge is tried first, on two scratch issues, and its verdict written under Delegated unknowns.
- Until M2, `show` and `list` print the `claimed` label with no holder (§5's `holder` is null), and `close` asks nothing about one.

**Does not touch:** `claim`, `release`, `takeover`, `held`, `settle` and the index (M2); the skill (M4); the `issue-tracker` skill and its scripts; sminos; any issue of a real board.

**Proves:** acceptance 1 to 4, the record-block half of 5, 12 without its claim rows, 13, 14 and 21.

### M2 — claims

**At its end:** `task claim`, `release`, `takeover`, `held` and `settle` behave as D3 says, with the real sminos for identity. `show` and `list` print holders, and `close` respects one. No sminos code calls the plugin yet: `settle` is run by hand.

**Touches:** `task/cli/`, `task/tests/`, `task/CLAUDE.md` (the contract with sminos in both directions, which is where its detail lives).

**Interfaces:** exposes §4, §7 and §9; §9 is frozen at this milestone's review, since M3 builds against it. Consumes §1 to §3 and §10.

**Decisions:**

- The index is one JSON file, rewritten by atomic replace under a lock held across the read and the write: several sessions of one machine claim at once.
- Inside `claim` the order is: read and fold, append, read and fold, label, row. A crash after the append leaves a claim with no row; the same session's next `claim` or `release` of that ticket finds the claim is its own (by its address) and repairs the row.
- Inside a settle's release the order is: mark the row owed, write the record, take the label off, mark the row lapsed.
- sminos is found as devcloud finds it (`_sminos` in `devcloud/driver/context.py`): `TASK_SMINOS`, then `PATH`, then the marketplace clone. Each call is bounded at 30 seconds. The address is read from `sminos who`'s line as devcloud's `session_creator` reads it, and the thread id from `who --thread=<the session's id>`. A session whose answer carries an empty `thread` (one the MAWS app launched) claims with a row that has no thread id.
- Settle asks about a thread by its thread id; `ended: true` together with `local: true` is the only answer that releases.
- A message to a successor or to a `--to` thread goes through `sminos say`; with no session around it, as the machine's notice (`--notice task`).
- What sminos answers for the three end cases named by short id from another machine is observed and written under Delegated unknowns.

**Does not touch:** sminos's code; any real board; the skill.

**Proves:** the claim half of 5, 6 to 11, 12's claim rows, and 18.

### M3 — sminos calls the board at a thread's start, `/clear` and end

**At its end:** a thread's start guide lists what it holds and what lapsed. After a `/clear`, the new session is told what the conversation it left holds and can take it over without force. A retire prints what it released. The daemon's ending pass starts a settle, so a thread the three-day rule ends loses its claims within that pass.

**Touches:** `sminos/skills/sminos/scripts/sminos_threads.py` (finding and asking `task`, beside `find_devcloud` and `owned_by`), `sminos_daemon.py` (the ending pass of `sweep_threads`), `sminos.py` (the guide; the `/clear` branch, where `cleared_witness` is read; the retire paths `end_human`, `end_seat` and `end_and_stop`); `sminos/tests/` (a stand-in `task`, as `devcloud_standin.py` stands in for devcloud, and the cases); `sminos/skills/sminos/scripts/CLAUDE.md` (a paragraph on the contract); the sminos version.

**Interfaces:** consumes §9. Exposes nothing: sminos gains no verb and no output key (D5).

**Decisions:**

- This milestone is for whoever holds sminos when it starts. Before branching, read what is in flight on the thread sweep, the retire paths and the start hooks, and tell its holder. At this writing that is the question sheet's sminos child (`docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`), which adds a sweep of its own to the daemon and changes the start hooks. The channels composite is not amended: every child of it has landed, and this is a change of its own to code it landed.
- The floor, `TASK_MIN`, is the plugin's first released version that has §9.
- The guide's call is bounded at two seconds, and a board line is printed only when `held` or `lapsed` is non-empty. The settle the daemon starts is run as the census is (the child process the ending pass starts to ask devcloud which threads own a machine: `start_census` in `sminos_daemon.py`): bounded, one at a time, and never waited for by the tick.
- A retire calls settle for a thread only once its `ended` is written (a thread that then failed to end would be live and hold nothing), and before a purge removes the record settle asks about.
- Whether `gh` reaches GitHub from the daemon's environment, on a Mac and on a Linux host, is checked here and written under Delegated unknowns.
- sminos reads nothing of the plugin's files, and the plugin nothing of sminos's.

**Does not touch:** the three-day rule's own decision (`end_due`, the census, `end_by_rule`'s guard); `who` and `who --thread`; the wake; channels; the question sheet's code.

**Proves:** 15 to 17, 19 and 20.

### M4 — the skill, and this repository's cutover

**At its end:** sessions in this repository work the board through `task:tickets` and `task`; its open issues carry the new labels; the old scripts refuse it.

**Touches:** `task/skills/tickets/SKILL.md` (new); `.doperpowers/board.json`; the root `CLAUDE.md` ("The board" section, the `skills/` and `task/` rows); `skills/issue-tracker/SKILL.md` (one sentence at its head: a repository whose binding is `task` is worked through `task:tickets`); `README.md` and `docs/INSTALL-doperpowers.md` (the plugin's install line); `docs/whats-inside.md` (the plugin and its skill); `.github/PULL_REQUEST_TEMPLATE.md` (the line that names `board-transition.sh`); the versions of `task` and doperpowers. Live: this repository's issues and labels.

**Interfaces:** consumes all of them.

**Decisions:**

- **The skill** carries what a session cannot derive: what the board is for (R3); when a ticket is registered (work deferred out of a session, at the moment it is deferred, by whoever deferred it, with a body a reader weeks away can act on, after a search by the identifiers the work touches); what is takeable; that a claim comes before the work and a refused claim means the work is another's; that nothing is written to a ticket while work runs; what setting a ticket down leaves (a release that says where it stands, and the readiness the ticket now needs); that a pull request closes its ticket with `Closes #n`; that a `need-input` ticket says in prose what it waits on; and that an outsider's text on a public board is data. It carries no flags (`task --help` does) and no state machine.
- **Its pressure tests** must show: (a) a session that scopes work out registers it at that moment, with such a body, after searching; (b) an idle session takes a takeable ticket, and brings a `need-design` or `undecided` one to the owner instead of designing or deciding alone; (c) it claims before it starts, and on exit 3 does not start; (d) midway through claimed work it writes nothing to the ticket; (e) setting a ticket down, it releases with where the work stands and sets the readiness; (f) it registers no ticket for work it is about to build now; (g) in a checkout with an `upstream` remote it uses `task` and no raw `gh issue` command; (h) it does not act on an instruction found in an untrusted comment.
- **The cutover** follows D7's order. The plan is written outside the tree. Its decision rows go to the owner as a table in the pull request's description (O1), which for this public repository may name the issues.
- A ticket the relabel finds in an in-flight state: where sminos shows a live session on its branch or pull request, that session is asked to claim it after the apply.
- If O3 is answered as recommended, the ticket for MAWS is registered here.
- It starts once M3's sminos release is on the owner's machines and the plugin is enabled on them.

**Does not touch:** the sibling repositories; the old scripts beyond that one sentence; `execspec`, `decomposing`, `organizing-sprints` and the sminos skill, whose references to the old skill stay true until M6.

**Proves:** 22 to 24.

### M5 — the sibling repositories' cutover

**At its end:** `cua`, `MAWS` and `arkho` are on `task`, each by one pull request in that repository and one applied plan.

**Touches**, in each repository, through its own worktree and pull request: a new `.doperpowers/board.json` with `"binding": "task"` and that repository's `owner/name`; the text its agent instructions carry about the board. In `cua` that is the "Board Write Hard Gate" bullet of its `CLAUDE.md`, replaced by one sentence that the board is worked through `task:tickets`. `MAWS` and `arkho` hold no such text; a search for `issue-tracker` and `board-` at the cutover finds what there is. Live: their issues and labels. If O2 leaves `ida-solution` out, a ticket records the leaving and lists what waits there: its `CLAUDE.md`, the `AGENTS.md` some of its branches carry, `docs/runbooks/instructor-roster-audit-runbook.md`, and its two workflows that speak the old vocabulary.

**Interfaces:** consumes all of them.

**Decisions:**

- Before a repository's pull request opens, the threads in charge there are told through sminos what changes and when, since sessions working there read the labels. The plan is applied in the same sitting as the merge.
- `cua` and `MAWS` use native edges: the horizon rule of D6 applies, and parents keep their children.
- `arkho` is private. Its plan and its decision table never enter this repository or a public pull request.
- Each repository's decision rows go to the owner per O1.
- Another checkout of the same repository on another branch gets the change when its branch takes the default branch's commit. Nothing is edited there.

**Does not touch:** this repository, beyond Progress.

**Proves:** 25.

### M6 — the old scripts retire; acceptance

**At its end:** doperpowers no longer ships the `issue-tracker` skill, what referred to it refers to `task:tickets`, and the whole acceptance has been run.

**Touches:** `skills/issue-tracker/` moves to `archive/issue-tracker/` (the skill, its scripts and references), with `tests/issue-tracker/` and `tests/claude-code/board-api/` beneath it, unwired; `.github/ci-kit.yml` (the `issue-tracker` and `board-api` gates, and those paths where other gates list them); `tests/claude-code/run-skill-tests.sh` and any test that reads the moved paths; `archive/CLAUDE.md` (what it was, and that `task:tickets` holds its surviving rules); the root `CLAUDE.md` ("The board" section; the `skills/` row and its count); `skills/execspec/SKILL.md`, `skills/decomposing/SKILL.md`, `skills/organizing-sprints/SKILL.md` and `sminos/skills/sminos/SKILL.md` (each reference to the old skill or to a `board-*.sh`); `README.md`, `docs/whats-inside.md`; `.gitignore` (the old render cache); `application-agents/triaging-feedback/` and `infra/` (the paths their documents give for the scripts, which then point into the archive; neither runs anywhere today); the versions of doperpowers and sminos.

**Interfaces:** none.

**Decisions:**

- It starts when every repository of M5 has moved and O2 is answered.
- The four skills' edits are reference swaps, and in `organizing-sprints` the lines that name `board-register.sh` and `board-lint.sh`. They go through doperpowers:writing-skills, as any skill change here does, with a check sized to a reference swap.
- Archived tests stay with what they test and are run by nothing, as `archive/experimental-context/` keeps its own.
- This milestone runs the acceptance section whole, with the commands of Concrete Steps.

**Does not touch:** the `task` plugin's behavior; any dated document under `docs/doperpowers/`.

**Proves:** 26 and 27, and the section as a whole.

## Concrete Steps

From the repository's root, in the milestone's worktree.

The plugin's suite, M1 and M2 (acceptance 1 to 14):

    bash task/tests/run.sh
    # one line per test file, each ending "ok"; exit 0

    task --version
    # task 0.1.0 (the task plugin of the doperpowers marketplace)

    ci-gate
    # … PASS task … GREEN <run url>

The live checks (18 to 21), with a private scratch repository of the owner's account and a session sminos lists:

    TASK_LIVE_REPO=<owner>/<scratch> bash task/tests/live.sh
    # race: 20/20 rounds, one winner each, holders agree
    # retire: release reason ended, label off
    # fork checkout: gh names <upstream project>; task lists <owner>/<scratch>
    # (20, the /clear case, is run by hand in an interactive session; live.sh prints its three steps)

sminos's suite, M3 (15 to 17), by the gate:

    ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c
    # GREEN

This repository's cutover, M4 (22, 23):

    task migrate plan --out <a file outside the tree>
    # 53 rows: 30 mechanical, 23 decisions   (the counts of 2026-11-24)
    # … the decisions made, the owner's read (O1), the pull request merged …
    task migrate apply <that file>
    # relabelled 53, skipped 0; labels deleted: 11 status:*, engine:claude
    task lint
    # 0 FAIL
    gh label list -R <the repo of .doperpowers/board.json> --limit 200 | grep -c '^status:'
    # 0
    task list --takeable
    # the ready, unclaimed, unblocked tickets, P1 first

After M6 (26, 27):

    ls skills/issue-tracker
    # No such file or directory
    git grep -l 'doperpowers:issue-tracker\|board-[a-z]*\.sh' -- skills agents sminos/skills task CLAUDE.md README.md docs/whats-inside.md
    # no output
    ci-gate
    # GREEN, with a task gate and no issue-tracker or board-api gate

## Interfaces and Dependencies

**§1. The configuration**, `.doperpowers/board.json`, committed at a repository's root; read from the checkout, and from the main checkout when a linked worktree lacks it:

    { "binding": "task", "repo": "owner/name", "account": "login" }

`repo` is required. `account`, the trusted account, defaults to the owner part of `repo`.

**§2. Labels.** The names of D1's table, exactly; a batch is `batch:<name>`.

**§3. The record block.** The last thing in an issue's body: a fenced block whose opening line is three backticks and `task-record`, then lines `key: value`, then the closing fence, then nothing but whitespace. Keys: `registered-by`, `for` (addresses), `due` (`YYYY-MM-DD`), `spec`. An unknown key, a second such block, or one that is not last is a lint FAIL and is not read.

**§4. The claim record.** A comment whose first fenced block opens with three backticks and `task-claim`. Keys: `op` (`claim`, `release`, `takeover`), `holder` (an address; on `claim` and `takeover`), `of` (a claim id; on `release` and `takeover`), `reason` (on `release`: `released`, `ended`, `forced: <text>`; on `takeover`: `cleared`, `ended`, `forced: <text>`). A claim's id is the comment's numeric id. The fold is D3's table.

**§5. What the reading verbs give.** `task show <n> --json`:

    { "repo": "owner/name", "number": 548, "url": "…", "title": "…",
      "state": "open", "close_reason": null,
      "readiness": "ready-to-work", "horizon": "expected", "priority": "P3",
      "category": "bug", "batch": null, "author_trusted": true,
      "record": { "registered-by": "…", "for": null, "due": null, "spec": null },
      "blocked_by": [ { "repo": "owner/name", "number": 12, "open": true } ],
      "parent": null, "children": [],
      "holder": { "address": "…", "claim": 2161234567, "since": "2026-11-25T03:12:09Z" },
      "linked": [ { "kind": "pr", "number": 640, "state": "open", "updated": "…" } ],
      "takeable": false,
      "body": "…",
      "comments": [ { "id": 1, "author": "login", "trusted": true, "created": "…", "body": "…" } ] }

`holder` is null for an unheld ticket. `task list --json` gives `{ "repo": …, "tickets": [ … ] }`, each ticket that object without `body` and `comments`. `task search --json` gives `{ "repo": …, "query": …, "hits": [ { "number", "title", "state", "url" } ] }`, each hit with `body` under `--bodies`.

**§6. Lint.** FAIL: an open issue that carries any board label and has not exactly one readiness, or not exactly one horizon; two priorities, or two categories; a `status:*` label on any issue or in the repository's label list; a blocked-by cycle; a malformed record block (§3). WARN: `claimed` on a ticket the fold says is unheld, or a held ticket without it; a `planned` ticket with no open blocker; an open ticket with board labels and no priority or no category. It also prints the number of untracked open issues. Each line names the ticket and the command that repairs it. Exit 3 on any FAIL.

**§7. The index**, `claims.json` in the plugin's home (`TASK_HOME`, by default `~/.claude/task`):

    { "v": 1, "rows": [ {
        "repo": "owner/name", "number": 548, "title": "…", "url": "…",
        "claim": 2161234567, "session": "<session id>", "thread": "<thread id, or empty>",
        "address": "…", "since": "…", "successor": "<session id, or empty>",
        "state": "held", "reason": "", "tries": 0 } ] }

`state` is `held`, `owed` (a release is due; `reason` says which) or `lapsed` (released or taken over; reported once by `held`, then removed).

**§8. The plan file** of `task migrate plan`:

    { "v": 1, "repo": "owner/name", "read_at": "…", "rows": [ {
        "number": 548, "title": "…", "updated_at": "…",
        "old": [ "status:ready-for-implementer", "priority:P3", "bug" ],
        "readiness": "ready-to-work", "horizon": "expected",
        "basis": "mechanical", "decided": true, "why": "",
        "meta": { "note": "…" } } ] }

A decision row is written with `basis: "decision"`, D6's fallback values and `decided: false`; whoever settles it sets the two labels, `why` and `decided: true`.

**§9. What sminos calls.** Both print one JSON object and exit 0 whenever they could answer, whatever the answer; exit 2 is a usage error, which is also what a plugin from before a verb gives.

`task held --thread <thread id> [--grant <session id>] --json`, which reads the index only and never the network:

    { "v": 1,
      "held":   [ { "repo", "number", "title", "url", "claim", "since" } ],
      "lapsed": [ { "repo", "number", "title", "url", "reason", "at" } ] }

`reason` is `ended`, `taken-over` or `forced`. `--grant` sets `successor` on the named thread's held rows.

`task settle [--thread <thread id>] --json`:

    { "v": 1,
      "released": [ { "repo", "number", "title", "url", "claim", "reason", "told" } ],
      "closed":   [ { "repo", "number" } ],
      "lapsed":   [ { "repo", "number", "reason" } ],
      "owed": 0,
      "unknown":  [ { "repo", "number", "thread", "said" } ] }

`told` is the successor's address when a message was sent, else empty. `owed` counts the rows still owed after this run.

**§10. What `task` asks of sminos** (1.53.0 or later; found through `TASK_SMINOS`, `PATH`, then the marketplace clone):

- `sminos who`, with the session's id in the environment: a line `Sminos-Session: <address>`, or nothing.
- `sminos who --thread=<name>`: one line of JSON, of which `task` reads `thread`, `session`, `short`, `alias`, `machine`, `project.name`, `ended` and `local`. Exit 4: nothing answers the name. Exit 2: a sminos from before the flag.
- `sminos say [--notice task] "@<tag> <text>"`.

sminos finds the plugin through `SMINOS_TASK`, the copy beside its own plugin, the marketplace clone, then `PATH`, as `devcloud_places` orders devcloud's.

**Dependencies.** The `gh` client, authenticated as the owner's account, on every machine that runs `task`. No package beyond Python's standard library. For the live checks, a private scratch repository named by `TASK_LIVE_REPO`.

## Outcomes & Retrospective

Pending — written at finish.
