# Tasks for the human: the Task Board (2026-11-27)

> **Parent:** root — the project's standing purpose (`CLAUDE.md`: a software-development methodology for coding agents, with sminos as the family that lets many sessions work for one owner). **Consumes:** the question sheet (MAWS's composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`, whose sminos part, its child C2, is on this repository's `main`: `sminos/skills/sminos/scripts/sminos_sheet.py`, `sminos_sheet_step.py`, `sminos/hooks/mods/sheet.tsx`, `sheet-model.tsx`, plan `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`); sminos's threads, wake and machine notices (`docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, closed, read and not amended); the ticket board's `task` plugin (`docs/doperpowers/specs/2026-11-24-ticket-board-design.md` on branch `ticket-board-spec`, not built). Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact opens by citing this document (path, child id, parent pin). B1 and B1a are built in this repository; B2, B3 and B4 are MAWS's, and their execution documents are written on MAWS's side by MAWS's holders.

## Purpose

The owner supervises many agent sessions. A session often needs the human to do something in the world: log in, grant a permission, rotate a key, buy, review and merge. Today that is a sentence in a message: nothing lists what the human was asked to do, what each item holds up, or tells the session when it is done. The owner named this as a pain ("나를 기다리는 일이 안 보임", 2026-11-20T05:06Z) and asked for a human to-do board triaged as blocking, must be done at some point, optional, with low latency and the result returned to the asking session.

**After this change.** An agent, or a subagent, assigns a task to the human in one command and keeps working. The human sees every open task of every session on the machine in one list, the blocking ones first, reads a task like a ticket (body, comments), comments on it, and completes or declines it. Whoever asked is told at once, with nobody relaying: the human's outcome and note arrive in the asker's conversation as an envelope, the way a question sheet's answers do. A task stays on the board until the human closes it, whatever became of the session that made it.

**How to see it working.** The scene in Parent-Level Acceptance: two tasks assigned in one command, the terminal closed, the blocking one completed from the board, the session back in the background with the note in its conversation.

**What it must not be.** Not the agents' backlog (R6). Not a question: a decision or an answer goes on the question sheet (D1). Not a blocking call: assigning a task never stops the agent. Not a record of the agents' progress. Not the human's own to-do app: only sessions add tasks. Not a second delivery system: the envelope travels by the sheet's routes, shared and not copied (D6), and a stopped asker is started by sminos's own wake.

## Progress

- [x] (2026-11-27T22:20Z) The owner approved the design ("승인한다, 스펙으로") with both open forks answered (R9, R10). The design of record was the session's design document, version 3; this document carries it whole.
- [x] (2026-11-27) This document and B1's execution document written and committed as the baseline.
- [ ] Independent review: the design and B1's execution document, one round, then one review of the repair.
- [ ] The owner's read of this document. Nothing is built, and no holder of another unit is asked for anything, before it. What the read is asked to settle is "For the owner's read".
- [ ] The sheet's holder agrees the extraction (D6). B1's M3 waits on it.
- [ ] Children: the Tracking Map.

## Terms

- **Task**: one thing a session asks the human to do in the world. It is the human's to-do; the session that asked is its return address.
- **The board**: the list of this machine's tasks, as any surface draws it. "The board" in this document is never the agents' ticket board (GitHub issues, the `task` plugin's first destination) and never the engine's in-session to-do tools.
- **Asker**: who is told of a task's outcome: the thread that assigned it and, when a subagent assigned it, that subagent.
- **Thread**: sminos's record of one line of work on a machine (`sminos/skills/sminos/scripts/sminos_threads.py`): a spawned seat, or a session its human opened. It has a current session, is *stopped* when no process holds that session, and is *ended* by a retire or by the three-day rule. A `/clear` and a fork each begin a new thread; a resume continues one.
- **The sheet**: the question sheet. **The sheet's holder**: the session that holds its composite and rules on its published contract.
- **Envelope**: the text a delivery puts in a conversation: a head line beginning `[tasks v1]`, one line an outcome, and a `<task-delivery>` block a program reads.
- **Outcome**: one act of the human on a task (done, declined, a comment) as it is owed to the asker.
- **Route**: one way an envelope enters a conversation: as this plugin's prompt when the session is idle, as context on the model's next tool result, as context on the next prompt, or as a message sent to a running subagent.
- **Landed**: the envelope is known to be in the conversation the model reads, by the row that holds it.
- **The door**: the one command through which every surface performs the human's acts (`sminos task act`).
- **Surface**: anything that shows the board and takes the human's acts: the command line, the local page, the MAWS app, the phone.
- **Wake**: sminos starting a stopped thread in the background (`sminos.wake`, `claude --bg --resume`), which today only a message addressed to the thread causes.
- **Notice**: a message in a project's log from a program of the machine, not from a session or a person (`sminos say --notice <program>`, contract X8 of the channels-and-threads design); devcloud's hosts use it today.
- **Mod**: a plugin's function hooks (`sminos/hooks/mods/`), loaded only where the engine's function hooks are enabled. A shell hook (`sminos/hooks/*.sh`) runs everywhere.
- **MAWS-run session**: a session the MAWS app launched and steers (sminos's lane B). It has no thread record and sminos never wakes it.

## What the owner ruled

Each row is the owner's own wording, with the time the answer reached the design session (UTC). R1 to R8 are quoted from the design's "Decided by the owner"; R9 to R11 from the approval. What this document decides beyond them is the design's, marked in "For the owner's read" where the owner should see it.

| id | ruling | the owner's words |
|---|---|---|
| R1 | The structure runs parallel to the question sheet: a session creates a task for the user, it is added to the user's board, and when the user completes it the completion and the human's comment are pushed back to the session that assigned it | "task assigned to human도 question sheet를 만든 방식과 거의 마찬가지의 방법으로 만들어질 수 있지 않을까 … 특정 세션이 Task를 유저를 위해 create하면 유저의 Task Board에 더해지고, 유저가 해당 작업을 완료할때 완료 메시지와 인간 코멘트가 다시 해당 task를 assignn한 세션에 푸시해 전달되는것이다." (2026-11-24T12:08Z) |
| R2 | A subagent may assign; the completion goes to the subagent that asked, or to the main session when it has retired | "서브에이전트도 인간을 위한 Task를 만들 수 있으며 … 기본은 그 task를 인간에게 넘긴 서브에이전트에게, 해당 서브에이전트가 retire됐다면 메인 세션에게 돌아간다." (2026-11-24T12:08Z) |
| R3 | An agent adds, revises and comments; a task is like a ticket: body, comments, id, tags, which session, whether from a subagent | "기본은 Task보드에 새 task를 더하는 것이고, 기존 task 수정 및 댓글 등등도 가능하다 … 본문, 댓글, 등이 있으며 id, tags, which session, whether it's from subagent" (2026-11-24T12:08Z) |
| R4 | A task stays on the board after its session is cleared or has ended | "보드에 남는다 (Recommended)" (2026-11-24T12:17Z) |
| R5 | The human decides per task whether a stopped session is woken: a blocking task wakes by default, with "complete without waking" available; any other is delivered at the next resume by default, with "wake and deliver" available | "Task마다 인간이 정할 수 있게 -- blocking Task면 기본은 깨우기, 선택적으로 "깨우지 않고 Task 완수하기"도 가능. 그 밖의 Task는 다음 resume에 전달하는게 default, "깨우고 전달하기" 면 깨움." (2026-11-24T12:17Z) |
| R6 | The GitHub board stays the agents'; tasks for the human are not tickets | "GH 이슈트래커는 그냥 에이전트용으로 두고" (2026-11-24T12:08Z) |
| R7 | Agents assign with the `task` CLI, not a tool | "'task assignhuman' 과 같은 형태로 human task board에 쓰게하는건 어떨지?" (2026-11-24T12:25Z) |
| R8 | The board is a place of its own, apart from the sheet | "질문과 Task를 한 화면에서 같이 볼 필요는 아직 없다. 일단은 따로 둔다. Task board는 따로있는게 나을것같다" (2026-11-24T12:25Z) |
| R9 | The completion comes back as an envelope, as the sheet delivers. Chosen over the design's recommendation, a sminos notice that points at the task and leaves the agent to read it | "질문 시트처럼 봉투로" (2026-11-27T22:20Z) |
| R10 | A thread stopped with a blocking task open is not ended by the three-day rule | "뺀다 (Recommended)" (2026-11-27T22:20Z) |
| R11 | The design is approved and goes to a spec, shown again before anything is built | "승인한다, 스펙으로" (2026-11-27T22:20Z) |

Events and subscriptions are out of this scope ("이번에는 뺀다 (Recommended)", 2026-11-24T12:17Z). The triage of blocking, must be done at some point, optional is the owner's first brief (2026-11-19); it is a deliberate difference from the sheet, where no question marks a session as stopped on the human.

The option R9 chose was shown to the owner with this preview, which D5's envelope follows:

    [tasks v1] The human completed t7.
    Their note: "계정 B로 로그인했음"
    <task-delivery>{...}</task-delivery>

## Grounding Baseline

Read at this repository's `main` (`40b79a7d1`), MAWS's `question-sheet` (`cc9fd7ff3`) and `question-sheet-c5` (`2a8ef52ee`), and `ticket-board-spec` (`143552115`). Each line is a fact the design rests on.

1. **The sheet's delivery lives in a mod that runs only where the sheet is chosen.** `sheet.tsx` holds the routes (`deliver`, `submitIdle`, `sendTo`, `take`, `putBack`, `withResultRoute`, `endTurn`, the `session.append` landing hook) inside the state of a session that chose the sheet (`routable()`, `isStarted`); the sheet is off by default (`SHEET_DEFAULT`), and off for every session that is not interactive (`chooseStart`). A task's asker is any session. So "by the sheet's routes" needs the routes to run in a session that never chose the sheet: the routes become a module of their own (D6).
2. **An envelope's text is composed by the command, its routes are the mod's.** `sminos_sheet_step.py` composes (`envelope`, `envelope_text`, `block`; `BUDGET` 60,000 UTF-16 units, `ENVELOPE_KEYS` 200); the mod receives `ready: [{recipient, keys, text, wakes, more}]` and never composes. The budget's reason (the plan's I7): the engine hands the model one context entry whole only up to 100,000 characters.
3. **The sheet's published set is frozen.** `sminos/types/sheet/` (version 1) is what MAWS pins by digest; `sminos/tests/test_sheet_contract.py` and `test_sheet_step.py` hold the command to it, composing every published envelope.
4. **The sheet's routes are about to change once more.** The sheet's C5 has one pull request in this repository, its M1 (plan on MAWS's `question-sheet-c5`, `docs/doperpowers/plans/2026-11-27-question-sheet-c5-maws-run.md`, §S): in a MAWS-run session `take` carries notices and contexts, `withResultRoute` no longer returns early for the runner, and the `prompt.submit` hook adds a context when a prompt's text holds a delivery block. It is under review and not built.
5. **Only a message addressed to a thread wakes it.** The daemon's `deliver_owed` → `deliver_next` → `wake_member` → `wake` starts a stopped thread for a log event with a `to`; there is no registry of other things owed (`sminos_owed.py` is the uplink's). A program of the machine writes such an event with `sminos say --notice <program> "@alias …"`, run with no session. A sheet answer wakes nothing. No test shows a notice waking a thread: the path is read from the code (delegated unknown U2).
6. **A `/clear` does not continue a thread.** The session left stays the current session of its own thread, which stops and later ends; the new session is a thread of its own and takes the alias (`release_alias` writes `released: {alias, at}` on the left record; `released_alias` reads it). Nothing points from the left thread to the new one: the link is the alias. A fork is a thread of its own.
7. **The three-day rule and its one exemption.** `sweep_threads` (`sminos_daemon.py`) finds a thread due when its `stopped` mark is older than `thread_end_after()` (three days); `end_due` leaves it stopped while devcloud's census says it owns a host, saying so once in `daemon.log` (`holding`); `end_stopped` and `sminos.end_by_rule`'s guard decide again under the record's lock. An ended thread is not woken (`wake_of` answers `ended`); it returns only when a process holds its session again.
8. **A subagent's shell cannot say which subagent it is.** It carries its parent's `CLAUDE_CODE_SESSION_ID` and no agent id. A `tool.call` hook is told `e.agentId` (absent on the main loop; a subagent's is `a` and sixteen hex digits, a teammate's `<name>@<team>`), may hand a changed `command` to `next`, and the permission check judges the changed bytes (`devcloud/hooks/mods/secrets.tsx`; `hooks/mods/README.md`: "the permission check sees the restored bytes").
9. **No sminos mod rewrites a command today.** `backticks.tsx` has a real shell lexer and uses it only to refuse a call. The bridge compares the engine's input with what its own `tool.call` hook saw (`bridge-requests.tsx`, `isSeen`), and doperpowers' appeal keys a pass on the input as it saw it: a rewrite made beneath them breaks both for that call. sminos's module is seated outside every user-tier plugin's (`prependPlugins`), and within it registrations nest in order, the first outermost.
10. **A caller inside a session is known by `CLAUDE_CODE_SESSION_ID`.** `sminos channel lead` and `say --notice` are refused when it is set. An agent can unset it; only a typed confirmation on `/dev/tty` is beyond one (`sminos_visibility.confirmed`), and a page has no terminal.
11. **The `task` plugin does not exist yet.** The ticket board's spec makes it (its M1, the plugin's first release): Python, standard library only, importing nothing of sminos, finding `sminos` through `TASK_SMINOS`, the PATH, then the marketplace clone, each call bounded at 30 s; exits 0 done, 1 failed, 2 usage, 3 refused by a rule; body from `--body-file`; reading verbs take `--json`. Its dispatch keeps the Task Board's verbs unused, and `task assign-human` exits 2 saying the Task Board is not built.
12. **The line above the prompt and the start guide have precedent.** `registerSheetBand` draws through `ui.render` for `AbovePrompt`; `sminos guide` (`guide_text`, run by the shell hook `smns-guide.sh`) joins lines, an optional one only when it has something to say.

## Design

Grades: a decision marked **[binding — reason]** is one only the whole picture could settle, and a child does not reopen it. Everything unmarked is advisory inheritance: a child may overturn it with evidence, saying so in its own document and listing the sentence for this document's writer.

### D1. What is a task, and what is a question

In the session manager's four types of what a session needs from the owner: an **act** (something only the human can do in the world) is a task; a **decision** or an **answer** is a question on the sheet; a **judgment** is a task only when delivering it is itself an act in another system (review and merge a pull request), and otherwise a question. **[binding — every surface, the wording agents are taught and B5's tests draw the same line]**

| field | meaning |
|---|---|
| `id` | `t<n>`, assigned by the store, unique on its machine and never reused; shown with the machine's name wherever it leaves it |
| `revision` | 1 when added, +1 at each revise and each reopen |
| `askers` | who is told: the thread that assigned it (none for a session that has no thread), the session that ran the command, its alias then, and for a subagent its agent id and name. A list, so that a later version can add a second waiter; this version writes one |
| `project` | the asker's project when assigned |
| `title`, `body` | one line (at most 200 characters); Markdown (at most 20,000) saying what to do, why, and how the human knows it is done |
| `class` | `blocking` (the asker cannot go on without it), `needed` (must be done at some point), `optional` |
| `due` | optional date (`YYYY-MM-DD`) |
| `tags` | optional short labels the board can filter by (at most eight, each `[a-z0-9-]{1,32}`) |
| `comments` | a thread: each by the human or by an agent, with its time (a comment at most 10,000 characters) |
| state | **open**; **done** or **declined** (by the human); **withdrawn** (by an agent). The asker may **reopen** a done task with a comment, since "done" is the human's word about their step and the agent's check may fail |

The asker is a return address, not the task's owner: the task is the human's to-do. **[binding — R4 follows from it: nothing that happens to a session removes a task]**

### D2. The agent's way in: the `task` CLI

`task` is the agents' one CLI for tracked work, with two destinations: tickets on the agents' GitHub board, and tasks on the human's board (R7). Why a CLI and not a tool: a tool only where the harness must draw something for the owner; no schema held in every session's context; any agent with a shell can use it.

**The verbs.** One creates, under the owner's own form; the rest take a task's id, and an id says which board it means: a ticket is a number, a task is `t<n>`.

    task assign-human --class blocking|needed|optional --title "…" [--body-file F|-] [--due YYYY-MM-DD] [--tag x]…
    task show t7 [--json]
    task list --human [--mine] [--json]
    task revise t7 [--title …] [--body-file F|-] [--class …] [--due …|--no-due] [--tag x]… [--no-tags]
    task comment t7 --body-file F|-        (or a short text as the last argument)
    task withdraw t7 [--reason "…"]
    task reopen t7 --comment "…"

`--body-file -` reads standard input, so a body rides a heredoc; the ticket verbs' `--body-file F` is kept, since one CLI has one way to give a body. `assign-human` prints the id and the line the human will see (`t7 blocking "Log in to the console"`); every verb returns at once and prints what it touched. `show` and `comment` are also ticket verbs: the `task` plugin's dispatch sends them to the human's board when their first argument is whole `t[1-9][0-9]*`, and `list` when it carries `--human`. `revise`, `withdraw` and `reopen` exist only for the human's board; given a ticket's number they exit 2. The alternative weighed: a `-human` form of every verb (seven names, nothing shared with the ticket dispatch). It lost because an agent would learn two vocabularies for the same acts while the id already says which board is meant; its cost is three branches in the ticket verbs' dispatch, which goes to the ticket board's writer (X6).

The verbs are a thin front over the store's commands in sminos (D3): each runs `sminos task <verb>` with the same arguments, passes its output and exit through, and where `sminos` is not found exits 1 saying that the human's board is kept by sminos and it is not installed. The store's commands are usable directly (`sminos task assign …`), which is what a session without the `task` plugin does and what B1 is tested through before the plugin exists.

**Who may change a task.** Any session comments on any task. `revise`, `withdraw` and `reopen` are the asker's: a session whose thread is the task's asker, or the successor a `/clear` gave it (D5), and for a task with no thread, the asker's session. Another session is refused, exit 3. Within a session any agent may change the session's tasks: a shell cannot tell them apart, and the subagent's attribution is a delivery hint, not an owner.

**Who asked.** The command learns the session from `CLAUDE_CODE_SESSION_ID` and its thread from sminos. It cannot learn which subagent ran it (baseline 8), so sminos's mod tells it: a `tool.call` hook on Bash, told `e.agentId`, finds each simple command that is `task assign-human` or `sminos task assign` and puts `--asker-agent <id> --asker-name <word>` directly after the verb. So the attribution is part of creation, and the person consents to the command as changed, which reads plainly. **[binding — the flag's names and its place are what the permission rules the owner writes will match]**

- The flag goes after the verb and not at the command's end, because a command can end in a heredoc, a comment or a list (`task … && echo ok`), and not before the command as a variable, because a leading assignment can stop an allow rule for the command from matching. The hook finds the command with `backticks.tsx`'s lexer; where the lexer gives up, or the agent's id is not whole `[A-Za-z0-9_.@-]{1,128}`, nothing is changed and the asker is the thread alone.
- The name is the agent's description or type as `$.agent.list()` gives it, reduced to `[A-Za-z0-9_.-]` (any other run a `-`, at most 64 characters), left out when nothing remains.
- The hook is sminos's, registered first in `sminos/hooks/mods/register.tsx`, so it is the module's outermost: the bridge and every plugin seated inside sminos see the command as changed, which keeps the bridge's `isSeen` and the appeal's pass whole for that call (baseline 9). In the `task` plugin it would sit in the user tier, beneath both and in no fixed order against devcloud's secrets guard.
- Where the mod is not loaded the asker is the thread alone. An agent that writes the flag itself is believed: it is a delivery hint.

**What agents are told.** In the plugin's skill (`task:human-tasks`), in one line of sminos's start guide, and in one sentence of the question tool's description (the sheet's holder's to agree; D6's second ask): D1's line between a task and a question; say in the body how the human knows it is done; mark `blocking` only what the work cannot continue without; the completion is pushed to you, so do not poll the list; a subagent that is blocked returns to its caller with the task's id; check the result yourself, and reopen with a comment when it fails. The words are B5's to settle before they ship (X8).

### D3. The store

One store per machine, under the sminos home (`$SMINOS_HOME/tasks/`), holding every task assigned on that machine. It is not the sheet's record and shares no file with it. **[binding — one store a machine is what lets a task outlive its session (R4) and the board list across sessions]**

- **One file, replaced whole.** `tasks/state.json` holds every open task and every closed one still kept, the outcomes owed, and the acts already applied by key; a change reads it, changes it and replaces it (a synced temporary file and `os.replace`) under an exclusive lock on `tasks/.lock`, waited for at most 10 s (exit 75 past that, as the sheet's door). A reader takes no lock: a replace is whole, so one read is a consistent state, and `seq` (+1 at each change) orders two reads. The alternative, a file a task, was weighed for write cost; it lost because every reader wants the list, and the store is small (at most 500 open tasks; an `assign` past that is refused, exit 3, saying how many are open).
- **Every change is one step under the lock, made by the command that causes it**: an agent's verb, or a human's act arriving through the door. There is no inbox, no drain and no daemon in the path of a write: the sheet needs an inbox because one session orders every step, and no session owns this store.
- **The contract carries a version.** `state.json` holds `version` (1). A command built for an older version than the file's refuses to write (exit 1, saying which plugin to update) and still reads what it understands; a writer keeps every field it does not know, on the store and on each task, since several plugin versions run on one machine at once. What another repository reads is the published set, `sminos/types/tasks/` (X1), made as the sheet's is: written by hand by a generator from this document's shapes, never by the code it holds to account.
- **Lifetime.** A `/clear`, a fork, a stop or an end of the asker removes nothing (R4). An open task leaves the board only by the human's done or decline or an agent's withdrawal. A closed task is kept 30 days, for reopening and for a read-only list of what was closed; the daemon's hourly duty removes it after that, with its outcomes.

### D4. What the human does, and the door

On a task: **comment** (it stays open), **done** with an optional note, **decline** with a reason. Every surface performs them through one command of sminos, the door, which applies the act at once and answers with its verdict. **[binding — one door is what makes every surface's act the same act, and is the only writer B2, B3 and B4 have]**

    sminos task act            # one JSON object a line on stdin, at most 50; one verdict a line on stdout

    {"v":1,"key":"<the surface's own id for this act, 8 to 64 of [A-Za-z0-9_-]>","task":"t7","act":"done","revision":2,"text":"logged in with account B","wake":null}

- `act` is `done`, `decline`, `comment`, `seen` (the human opened the card: it clears the row's "Updated") or `delivered` (X4: whoever delivered an envelope itself says so, naming `keys`).
- A `done` or a `decline` names the revision the human read and is refused `stale` when the task was revised since, with the current revision, so the card can say so; a comment is never refused as stale. An act on a task no longer open answers `closed`; an unknown id, `unknown`.
- `wake` is the human's choice for a stopped asker (R5): `true`, `false`, or `null` for the default (D5).
- **An act is applied once.** The door keeps each applied act's verdict by its `key` for as long as the task is kept; the same key again answers the first verdict and changes nothing. A surface that did not hear the verdict sends the act again.
- **The verdict** says what happened and what the asker will see: `{"v":1,"key":…,"task":"t7","verdict":"applied|stale|closed|unknown|refused","revision":2,"state":"done","outcome":"t7.3","told":"running|woken|held:<why>|next-resume|ended|not-reachable|maws"}`.
- **The door refuses a caller that is a session** (`CLAUDE_CODE_SESSION_ID` set; exit 3): an agent does not complete the human's task. This guards a mistake, not an adversary (baseline 10); D9 says what is trusted.

The command line is the first surface and goes through the door: `sminos task list`, `sminos task show t7`, `sminos task done t7@2 [--note "…"] [--wake|--no-wake]`, `sminos task decline t7@2 --reason "…"`, `sminos task comment t7 "…"`. The handle is the sheet's: `t7@2` names the revision read; a bare `t7` names revision 1.

### D5. Telling the asker (R9: an envelope)

After the door applies a `done`, a `decline` or a `comment`, an **outcome** is owed to the asker and delivered as a task envelope by the sheet's routes. It stays owed until it is known to have landed.

**The envelope.** One head line, one line an outcome, the command that reads a task's thread, and the block:

    [tasks v1] From the human, on tasks you assigned:
    t7 "Log in to the console" → done. Their note: "logged in with account B"
    t9 "Rotate the signing key" → declined. Their reason: "not before the audit"
    t4 "Buy the domain" → a comment: "which registrar?"
    Read a task's whole thread: task show t7
    <task-delivery>{"v":1,"keys":["t7.3","t9.2","t4.5"],"outcomes":[{"task":"t7","revision":1,"outcome":"done","note":"logged in with account B"},…]}</task-delivery>

- An outcome's key is `<task>.<n>`, `n` the task's count of acts. The block is one line of JSON with `<`, `>` and `&` escaped as the sheet's block escapes them; it lists what was done, declined and commented on and nothing else. **[binding — the block is what B3's steer carries unchanged and what a landing is read from]**
- A line names what the model needs to place the outcome: after the id, `(assigned by the subagent <name>, <id>, which has ended)` when a subagent's outcome goes to the main conversation, `(assigned by the conversation this one replaced at a /clear)` for a successor, and `(acted on <local time>, while this session was stopped)` for an outcome applied while no process held the session.
- To a subagent the envelope opens with a line saying it comes from the human through the task board and not from its coordinator, as the sheet's does: the engine credits a plugin's send to the coordinator.
- **The budget is the sheet's**: at most 60,000 UTF-16 units and 200 keys an envelope. A note is in the prose whole up to 2,000 characters; past that its first 500 and "the rest: `task show t7`"; the block's `note` is the first 500 with `noteCut`. What is owed to one recipient is packed in the order applied, what starts a turn first; when not all fits, the head says `More follows.` and the next envelope is composed afresh once this one landed.
- The command composes it (`sminos task owed`), from the store, to the published examples; the mod never composes. It answers the same shape the sheet's step gives its mod, `ready: [{recipient, keys, text, wakes, more}]`, which is what lets one set of routes carry both (D6).

**Who it goes to.** The store decides at each read, for the session that asks (`sminos task owed --session <id> --agents <running subagents>`):

- **A subagent that is running** gets its own envelope, sent to its own conversation; one that has ended, or a send that was not delivered, its main conversation, naming the subagent (R2).
- **The thread's current session** gets what its thread is owed.
- **A cleared conversation.** An outcome owed to a thread whose record holds a `released` alias goes to the live session that now holds that alias in that thread's project, its successor; the left thread is not woken while that session's thread has not ended. When the left session is opened again (a process started after the release holds it), it is told itself.
- **A session with no thread** (a MAWS-run session; a session on a machine sminos does not know as a member) is its own asker by its session id.

**When a turn starts for it.** In a running session the envelope leaves by the first route that opens: as the plugin's prompt when the session is idle, as context on the model's next tool result, or as context on the next prompt. Only some outcomes start a turn by themselves (open the idle route): a `done`, a `comment`, and a `decline` of a blocking task. A decline of a task that is not blocking starts no turn; it leaves with whichever route opens next and shows in `task list --human`. An outcome applied while the session was stopped starts no turn after the resume unless the human's choice was to wake (below): it leaves with the first route that opens, marked with its time.

**A stopped thread, and the human's choice** (R5). The card shows what sminos says of the asker before the human acts: running; stopped and will be woken; stopped and held, with the reason sminos publishes (`wake_of`, `why_of`); ended. For a stopped thread the act's `wake` applies: by default a blocking task's outcome wakes it and any other waits for the next resume, and either can be switched for that act. The default is evaluated when the act is applied, so a session that came back meanwhile is simply told.

- **The wake is sminos's.** The door writes one notice from the program `tasks`, addressed to the thread (`sminos say --notice tasks "@<alias> …"`, in the thread's project), and sminos's delivery owns it from there: the daemon starts the thread or holds it with its published reason, and tries again as it does for any message. The notice carries no outcome and no note, so the human's words stay on the machine and out of a synced log: `[tasks v1] The human acted on t7, a task this conversation assigned. The outcome is delivered here as a task envelope; if none follows, read it with: task show t7`. Once the thread runs, its mod reads what is owed and the routes deliver; an outcome whose act asked for a wake starts a turn like a fresh one.
- **The wake is tried again by the daemon, not the door.** The door writes the notice when no process holds the target session, and marks the outcome `notified`. A session that stopped in the moment after the door judged it running would otherwise be left: the daemon's tick writes the notice for any owed outcome that asked for a wake, has none, and whose target no process holds.
- The alternative R9 set aside, recorded once: the notice alone as the delivery, with the agent reading the task itself. The notice survives only as the wake's cause, because sminos wakes for nothing else (baseline 5).

**An ended thread** cannot be woken: the outcome stays on the board and stays owed, the verdict's `told` is `ended`, and the door records one untagged notice in the thread's project log (`tasks: t7 "…" was completed; its asker <alias> has ended. The outcome is on the board: task show t7`). If the thread returns (its human opens the session again) the outcome is delivered then.

**A session MAWS runs** is not a sminos thread: no route of its main conversation is this plugin's to open. Bringing it up and delivering is MAWS's part (B3), on MAWS's own steer, as for the sheet; MAWS says a steer reached the model with a `delivered` act (X4). Until B3 lands such an outcome is owed and read with `task show`.

**How an outcome stops being owed.** By its envelope landing: the mod finds the block in a stored row one of its routes wrote and orders `sminos task landed`. By a `delivered` act. Or by the asker reading the task: `task show t7` run in the asker's session prints the whole thread to the model, so it acknowledges that task's owed outcomes when the main conversation assigned it (a shell cannot say which subagent read, so a subagent's task is acknowledged only by its envelope). The last is what a session without function hooks has, where no task names a subagent: its start guide's line says how many outcomes wait and names the tasks, and reading them settles them. Delivery is at least once: an asker can be told twice of one outcome across a crash, by an envelope and by its own `show`.

**The outcome's states and who moves them.** Every transition is one command under the store's lock; the mod writes nothing to the store (a hook can neither lock nor replace a file, the sheet's K1).

| from | event | by | to |
|---|---|---|---|
| — | a `done`, `decline` or `comment` applied | the door | `owed`; `wake` resolved to a boolean; `acrossStop` set when no process held the target session |
| `owed` | target stopped, `wake` true, not `notified` | the door, at once; else the daemon's tick | `owed`, `notified` set (the notice is in the log) |
| `owed` | the envelope's block found in a row of the routes' kinds; or at a start, in the transcript | the mod's `sminos task landed --session <id>` with keys | `landed` |
| `owed` | `delivered` naming the key | the door (MAWS's deliverer) | `landed` |
| `owed` | `task show` of its task in the asker's session, the task's asker naming no subagent | the command | `landed` |
| `owed` | a send to a subagent not delivered, or the subagent ended | nothing is written: the mod stops naming that agent as running | `owed`, its recipient the main conversation at the next read |
| `landed` | the task's 30 days pass | the daemon's hourly duty | gone with the task |

A flight (an envelope on a route, until it lands or fails) is the mod's and in memory, exactly the sheet's: its states, the turn it belongs to and what settles it are D6's shared code and are not restated here.

### D6. The extraction: one set of routes for both envelopes (a proposal, waiting on the sheet's holder)

R9 makes the delivery the sheet's way, and copying its routes would put two modules in one process each submitting prompts, attaching contexts and reading rows for landings, with no order between them. So the routes are shared, and because they must run in a session that never chose the sheet (baseline 1), they leave `sheet.tsx` for a module of their own. The sheet's holder asked to be told before any extraction and rules on the sheet's contract; **nothing below is built until that holder agrees, and what they change, this section takes.** It is drawn as the smallest change that leaves the sheet's published contract untouched.

**What moves.** From `sminos/hooks/mods/sheet.tsx` to a new `sminos/hooks/mods/delivery.tsx`: everything that handles a flight and nothing that knows what a question is.

- The `Flight` type; the bookkeeping of the main turn (`mainTurn`, `turns`) and of stopped subagents; the notices queue and the one context a route carries.
- The routes: `deliver` (the idle route's opening and a send to each running subagent), `submitIdle`, `sendTo`, `take`, `putBack`, `withResultRoute`, the settling at a turn's end (`endTurn`), `failFlight` and `release`.
- The hooks that are routes: `tool.call` for any tool (the result route), `prompt.submit` (the prompt route), `turn.start`, `turn.complete`, `session.append` (landing), and the classic `SubagentStop`'s mark that an agent stopped.
- From `sheet-model.tsx` to a new `delivery-model.tsx`: `isRouteRow`, `contentTexts`, `PLUGIN`, and the parts of `blocksOf`, `keysIn`, `heldKeys`, `landedSearchArgs` and `searchedKeys` that find a block, given the block's element name. `sheet-model.tsx` keeps each under its own name, bound to `sheet-delivery`, so its exports and their tests stand.

**What stays the sheet's.** The start choice, the tool, the steps and the drain, the view, what may open the idle route for a sheet (`freshWake`, `isWaking`, the spent keys), the `landed` and `reroute` steps (`orderKeys`), the ended-subagent notice, the start's search of the transcript (which calls the shared search with its own element), the band, the rows, the snapshot, the removal at a `/clear`. All of `sminos_sheet.py`. All of `sminos_sheet_step.py` but one parameter (below).

**The seam.** `delivery.tsx` knows sources; the sheet is the first, the tasks the second.

    export type Ready = { recipient: 'main' | { agentId: string }; keys: string[]; text: string; wakes: boolean; more: boolean }
    export type Source = {
      name: 'sheet' | 'tasks'            // in log lines and the toast
      element: string                    // the block's element: 'sheet-delivery' | 'task-delivery'
      /** The envelopes ready now for the session, none of whose keys the source holds back. */
      ready: (session: string) => readonly Ready[]
      /** Whether this plugin opens the main conversation's routes for the session (false for the sheet in a MAWS-run session). */
      opensMain: (session: string) => boolean
      /** What may open the idle route for the main envelope now, or undefined; what a failed submit spends. */
      wake: (session: string, envelope: Ready) => { keys: string[]; spent?: unknown } | undefined
      /** Keys the evidence says landed. Ordered once per evidence, never awaited by a hook. */
      landed: (session: string, keys: readonly string[]) => Promise<void>
      /** A send to a subagent that was not delivered. */
      rerouted: (session: string, keys: readonly string[], agentId: string) => Promise<void>
      /** A route did not bring these to the model: they are ready again. */
      missed: (session: string, route: 'idle' | 'result' | 'prompt' | 'send', keys: readonly string[], why: string, woke?: unknown) => void
    }
    export function registerDelivery(on: On): void       // the routes' hooks, registered where registerSheet registers them today
    export function addSource(source: Source): void
    export function reconsider(): void                   // a source's view changed: the routes look again
    export function notice(session: string, text: string): void
    export function routeContext(session: string, text: string | undefined): void

The type's names are advisory; these are binding **[the joint view: both envelopes and the sheet's frozen behaviour depend on them]**:

1. **One flight an envelope, a source.** A key is a source's own; a landing is attributed by the element of the block that holds it, so a sheet key and a task key never meet.
2. **One composer.** Where a result or a prompt route opens, `take` reserves, in one synchronous step, the main envelope of every source that has one, and returns them as entries of their own: the sheet's, then the tasks', then the notices, then the context. Each envelope is within its own budget and is a context entry of its own, so each is handed to the model whole (baseline 2).
3. **One idle prompt.** The idle route opens when any source's main envelope wakes; its prompt's text is the notices, then the tasks' envelope, then the sheet's, a blank line between, so a sheet envelope still ends the text it is in, as today. The whole stays within one envelope's budget (60,000 units): envelopes are taken in that order while they fit, the waking one always; what is left stays ready. Each flight in it settles by its own keys.
4. **A source that has nothing costs nothing.** With no source ready the hooks pass everything on, as the sheet's do where it is not chosen.
5. **The sheet behaves as it does today.** Its envelope's bytes, its steps, its record, its landings and its failures are unchanged; its suites (`sminos/tests/mods/sheet*.test.ts`, `test-sheet-step.sh`, `test_sheet_step.py`, `test_sheet_contract.py`) pass with no assertion changed, an import's path apart, and `live-sheet-check.py` is run once on the result.

**What a reader of a sheet session can see differ.** One thing: this plugin's idle prompt, and a tool result or a prompt, may carry a task envelope beside a sheet envelope: above it in the prompt's text, where a notice stands today; a context entry of its own elsewhere. A reader that takes a row's `<sheet-delivery>` block by its element reads what it read before.

**What of the sheet's contract changes.** Nothing. `sminos/types/sheet/` is not touched: version 1 and its digest stand, and `python3 -B sminos/tests/sheet-contract.gen.py --check` passes. No event, view or record field of the step moves.

**The command's side.** Nothing is extracted. The tasks' composer imports the sheet's measures from `sminos_sheet_step` (`units`, `jstr`, `mark`, `BUDGET`, `ENVELOPE_KEYS`), and `block(obj)` there gains a second parameter, the element's name, defaulting to `sheet-delivery`, so one function escapes both blocks; its output for the sheet is the same bytes, which `test_sheet_step.py` proves by composing every published envelope. If the holder would rather the step were not touched at all, the tasks' module carries its own copy of those six lines and a test that feeds both the same objects.

**The order, with the sheet's C5.** The sheet's C5 M1 (baseline 4) changes `take`, `withResultRoute` and the `prompt.submit` hook, three of the things that move. B1's M3 is built from a `main` that holds that pull request, so its change is carried across once, in the shared code, and is never made twice: the MAWS-run branch of `take` and of `withResultRoute` becomes the sheet source's `opensMain`, and the context C5 adds to a prompt whose text holds a block becomes an optional member of the sheet's source (`promptContext`). B1's M1, M2 and M4 touch none of the sheet's files and do not wait. If that pull request were withdrawn or long delayed, the other order stands: the extraction lands first and C5's M1 is rebased onto `delivery.tsx`, its three changes made there; that is the holder's call, and this document's order is the first.

**What it touches of the holder's.** In this repository: `sminos/hooks/mods/sheet.tsx`, `sheet-model.tsx`, `register.tsx`, their tests' imports and `sminos/tests/mods/sheet-harness.ts`; one parameter in `sminos_sheet_step.py`; the paragraphs of `sminos/hooks/mods/README.md` ("sheet", Delivery) and of the C2 plan (I9's first paragraph, I11's layout) that name where the routes live; `docs/doperpowers/TECH-DEBT.md` rows 41 to 43, which name `sheet.tsx` for limits that become the shared module's. No branch of the holder's in MAWS is touched; C5's plan names `take`, `putBack`, `withResultRoute` and `keysIn` "as built" in `sheet.tsx`, which stays true while its M1 lands first.

**The second ask of the same holder**, apart from the extraction: one sentence in the question tool's description (`DESCRIPTION`, the sheet's C1 text) that sends an act to the task board. Its words are B5's result; the description is the holder's, so B5 hands them the sentence with its evidence.

### D7. The three-day rule (R10)

A thread is not ended by the three-day rule while it is the asker of an open blocking task. The change is in the ending pass and nowhere else: in `sweep_threads`'s test of what is due, where devcloud's census is not yet asked, and again in `sminos.end_by_rule`'s guard, under the record's lock. A thread kept this way is said once in `daemon.log`, as a thread that owns a host is. **[binding — B1a's change must agree with the store B1 builds: what its predicate reads is X3's]**

- A stopped thread assigns nothing, so its open blocking tasks only become fewer; the guard's second look is for the human's act arriving between the pass's read and the end.
- The exemption also holds while an outcome that asked for a wake is owed to the thread and is younger than the period. Without it a blocking task completed on the fourth day closes the task, lifts the exemption, and the hourly pass can end the thread between a wake that failed and its retry (sminos retries a failed wake after 60 s, doubling to an hour), which is the case R10 was asked about. Bounded by the period, so a thread sminos holds for good (its mode asks for approval) is not kept for ever by one outcome.
- A store that cannot be read is no answer, and no answer keeps the thread: an end is not undone by the daemon.
- The channels-and-threads design says the rule applies to every thread, with the host exemption. That document is closed and is not amended; the rule as it stands is written where the code's own account is, `sminos/skills/sminos/scripts/CLAUDE.md`, and here.

### D8. Surfaces

- **The board**: the open tasks across sessions, blocking first, then needed by due date, then optional; each row its title, project, asker and the asker's state, due date, and "Updated" when an agent revised, commented or reopened since the human saw it. A card renders agent Markdown under the sheet's link policy (links limited to `http` and `https`, any other drawn as its text) and shows a link's host plainly.
- **A notice to the human**: a new blocking task raises a notification on the machine, as a question does today (`$.ui.notify` from the asker's session, when its mod sees its own new blocking task in the store); the phone's push comes with B4.
- **The command line**: `sminos task list|show|done|decline|comment` (D4). The first surface, and what remains when no page is reachable.
- **The terminal**: a line of its own above the prompt while the session has open tasks, `2 tasks for the human (1 blocking) · <the board>`, where `<the board>` is a live surface's address (X5) or `sminos task list`.
- **The local page**: `mawsd`'s page server carries the board as a page of its own under the sheet page's origin, pairing and four rules (B2).
- **The MAWS app**: a native board of its own; how a blocking task marks its session there is the owner's, on drawn frames with the board's look (B3).
- **The phone and other machines**: after the sheet's own remote child (B4).

### D9. What is trusted, and the limits

- **Trust.** Every session on the machine runs as the owner and can write the store's file; the store's rules (who revises, the door refusing a session) keep agents that mean well from stepping on each other and are not a defence against one that does not. An agent that strips its environment to complete the human's task is misbehaving in the way one that edits the file is, and B5 tests that agents do not.
- A machine that is off shows nothing elsewhere until B4. A machine that is deleted takes its open tasks with it; `devcloud vm down` naming them first is deferred work (Deferred).
- A fork's history says it assigned tasks that belong to the conversation it was forked from; its start guide says so, and their outcomes go to that conversation.
- Delivery is at least once.
- The human completes from a terminal, a page or the app, not from a session's own shell escape, which carries the session's id.
- The session manager's ledger reads the store when the whole picture is built; until then it lists a task only where a session wrote about it.
- A session without function hooks is told by its start guide and its own `task show`, never by an envelope; a session MAWS runs, by `task show` until B3.

### Delegated unknowns

| id | question | who answers | what decides |
|---|---|---|---|
| U1 | With the hook's changed command: does the permission dialog show `--asker-agent`, does an allow rule written for `task assign-human` still match, and do a teammate's and a workflow agent's ids pass the id's pattern? | B1, M2 (one live check) | A rule that stops matching moves the flag's place before M2 lands; an id form that does not pass is left unattributed and said in the skill |
| U2 | Does a notice from the program `tasks`, tagged to a thread of the same machine, wake that stopped thread as a peer's message does, on a machine that is cut over to the reach and words gates too? | B1, M4 (one live check) | No: the wake's cause is rewritten before M4 lands, and the finding goes to whoever holds sminos |
| U3 | In a thread woken in the background: are the mods loaded, does the wake's own prompt raise `prompt.submit` (so the envelope rides it), and is the plugin's idle submit accepted there? | B1, M5 (the same live check) | Whatever route opens is the route; if none does, the notice's own text is the fallback (`task show`), and the finding is written beside D5 |
| U4 | How often do agents file an act as a question, or a decision as a task; does a blocked agent mark `blocking` and go on; does a subagent return with the id | B5 | B5's thresholds, set in its ledger before its runs |
| U5 | Another `task` on the PATH (Taskwarrior, go-task) | the ticket board's M1 | its answer binds both destinations |

## Parent-Level Acceptance

The unit closes when this holds on one Mac with the released plugins, each line seen and not inferred. A1 to A9 need B1 and B1a; A10 to A12 add B2, B3 and B4 as each lands; A13 is B5's.

1. **Assign and go on.** In a terminal session, one Bash call runs `task assign-human --class blocking --title "Log in to the console" …` and `task assign-human --class needed --due <date> --title "Rotate the key" …`. Both print an id; the call returns within a second each; the session's turn continues.
2. **The board lists both**, from a terminal that is no session: `sminos task list` prints the blocking one first, each with its project, its asker's alias and state, and the due date; the session's own terminal shows `2 tasks for the human (1 blocking) · …` above the prompt, and the machine raised one notification, for the blocking task.
3. **The terminal is closed.** Within two passes of the daemon, `sminos task list` shows the blocking task's asker as stopped and to be woken.
4. **Done, with a note, wakes it.** `sminos task done t1 --note "logged in with account B"` prints a verdict whose `told` is `woken`. The session starts in the background; its conversation holds one `[tasks v1]` envelope naming `t1`, done, and the note; `sminos task show t1 --json` shows the outcome landed. The project's log holds the notice and not the note.
5. **A check that fails reopens.** In that session `task reopen t1 --comment "the console still asks for a login"`; `sminos task list` shows `t1` open again, Updated, at revision 2. `sminos task done t1` (revision 1) is refused as stale, saying the current revision.
6. **A cleared session's task reaches its successor.** A second session assigns a needed task, is cleared, and its successor works in the same terminal under the same alias. `sminos task done` of that task: the successor's conversation receives the envelope, saying the task was assigned by the conversation it replaced; the cleared conversation is not started.
7. **A subagent's task.** A subagent assigns a task; `sminos task show` names the subagent. Completed while the subagent runs, the envelope is in the subagent's conversation and not the main one; completed after it ended, in the main conversation, naming the subagent.
8. **Both envelopes at once.** In a session that has the sheet, with a sheet answer and a task outcome both ready while the model's turn runs, the next tool result carries two context entries, the sheet's envelope and the tasks', each landing its own keys; the sheet's suites pass unchanged.
9. **Three days.** With the period set short (`SMINOS_THREAD_END_AFTER`), a thread stopped past it with an open blocking task is not ended and `daemon.log` says why once; its task declined without a wake, the next ending pass ends it. A thread stopped past the period with only a needed task is ended as today, its task stays on the board, and its later completion answers `told: ended` with one line in the project's log.
10. **The local page** (B2): the board at the page server's origin, paired as the sheet's page is, lists what `sminos task list` lists, updates within two seconds of a change, and a card's Done with a note produces A4's effect.
11. **The MAWS app** (B3): its board lists the same tasks; a task assigned by a MAWS-run session, completed there, reaches that session by MAWS's steer, and the store shows the outcome landed by a `delivered` act.
12. **Another machine** (B4): a task on a second machine is listed and completed from the phone, and applied once when the act is sent twice.
13. **Behaviour** (B5): its four scenarios pass their thresholds with the wording that ships.

## Children

### B1: The store, the door, the envelope and its delivery, the verbs — plan (this repository)

- **Purpose:** Everything a terminal user needs for the unit's promise: the store and its published set, the door and the command line surface, the agents' verbs in sminos and in the `task` plugin, the subagent's attribution, the routes shared with the sheet, the task envelope and its delivery with the wake, the terminal's line, and what agents are told.
- **Acceptance:** A1 to A8 on a Mac, by the commands its execution document quotes; the published set (X1) at version 1 with its digest; the sheet's suites unchanged (D6, rule 5).
- **Edges:** blocked-by: `external:` the owner's read of this document. Its M2 is blocked-by `external:` the ticket board's M1 (the `task` plugin's first release). Its M3 is blocked-by `external:` the sheet's holder agreeing D6, and `external:` the sheet's C5 M1 pull request on `main`. Its M6 is blocked-by B5. blocks: B1a (by its M1), B2 and B3 (by its gate G1, the set published), B4.
- **Contracts:** owner of X1, X2, X3, X4's terminal form, X6, X7; reader of X5; ships X8.
- **Design inheritance:** D1 to D6, D8 (the command line, the terminal, the notice to the human), D9; U1, U2, U3.
- **Required:** required.
- **Status:** not-dispatched (waiting-external: the owner's read). Its execution document is `docs/doperpowers/plans/2026-11-27-task-board-b1.md`.

### B1a: The three-day exemption — brief (this repository; whoever holds sminos)

- **Purpose:** A blocking task completed after three days still finds a thread to wake (R10).
- **Acceptance:** A9. In `sminos/tests/test_threads_ended.py`'s form: a thread stopped past the period with an open blocking task is not ended and is said once; with the task closed and no wake-asked outcome younger than the period, it is ended; with such an outcome, not ended until the period has passed since the act; with the store unreadable, not ended; a thread with only needed or optional tasks is ended as today.
- **Edges:** blocked-by: B1's M1 (the store and X3's predicate). blocks: nothing.
- **Contracts:** consumer of X3.
- **Design inheritance:** D7, binding. Advisory: the predicate is one function of the tasks' module that reads the store with no lock, called from `sweep_threads` and from `end_by_rule`'s guard; the line in `daemon.log` follows `holding`'s form.
- **Required:** required.
- **Status:** not-dispatched (blocked-by B1's M1). One pull request, sminos's version raised, reviewed at the medium rung.

### B2: The board on the local page — plan (MAWS)

- **Purpose:** The board in a browser beside the terminal: `mawsd`'s page server carries it as a page of its own, with its model and components, so a terminal user completes a task without typing a command.
- **Acceptance:** A10. Every refusal of the page's four rules holds for the board's routes as for the sheet's. A card renders a task's Markdown under the link policy and shows a link's host. A done or a decline names the revision the card showed, and a stale verdict is shown on the card with the new text. The card shows the asker's state and offers the wake choice only for a stopped asker. The registration (X5) exists while the server runs.
- **Edges:** blocked-by: B1.G1; `external:` the sheet's C4 (the page server, its pairing and four rules) and the sheet's C3 first landing (the components' ground). blocks: B4.
- **Contracts:** consumer of X1, X2, X3; writer of X5.
- **Design inheritance:** D4, D8, D9. Advisory: the page reads the store's file directly as the published schema describes it, or through `sminos task list --json`, and learns of a change from the file's `seq`; it writes only through the door.
- **Required:** required.
- **Status:** not-dispatched (blocked-by B1.G1). Its execution document is MAWS's.

### B3: The MAWS app's board, and sessions MAWS runs — plan (MAWS)

- **Purpose:** The board as a native place in the app, and delivery for the sessions sminos does not deliver to.
- **Acceptance:** A11. The app's board lists what the store holds and acts through the door. An outcome owed to a MAWS-run session is steered to it in the envelope's steer form (the same block), a released session brought up first as for the sheet, and acknowledged by a `delivered` act only when MAWS's journal shows the steer reached the model. How a blocking task marks its session in the app is settled with the owner on drawn frames before it is built.
- **Edges:** blocked-by: B1.G1; `external:` the sheet's C5 (the steer's form and the deliverer it reuses). blocks: B4.
- **Contracts:** consumer of X1, X2, X3; owner of X4's steer form.
- **Design inheritance:** D5 (a session MAWS runs), D8. Advisory: `sminos task owed --session <id>` gives a MAWS-run session's outcomes with no ready main envelope; the steer's text is MAWS's to compose from the outcome's fields, as the sheet's steer is.
- **Required:** required.
- **Status:** not-dispatched. Its execution document is MAWS's.

### B4: The phone and other machines — decomposing run at dispatch (MAWS)

- **Purpose:** A task on any machine is seen and completed from the phone and from the app on another machine.
- **Acceptance:** A12; a blocking task raises the phone's push; an act resent over the remote path is applied once (the door's key).
- **Edges:** blocked-by: B2, B3; `external:` the sheet's C6 (the remote path it builds).
- **Contracts:** consumer of X1, X2, X3.
- **Design inheritance:** D4's key, D8. Deliberately coarse: its cut is made when the sheet's remote child has landed.
- **Required:** required.
- **Status:** not-dispatched (deliberately late).

### B5: Behaviour, before the wording ships — brief (this repository)

- **Purpose:** The words agents are told (D2) are tested before they ship: that an agent files an act as a task and a decision as a question, checks a completion itself, and does not flood the board.
- **Acceptance:** With the sheet's eval harness (`tests/output-styles/`, C1's), a stand-in `task` that records its calls, and the skill not preloaded (only the start guide's line and the command's help in context), four scenarios meet thresholds B5's ledger sets before its first run: a login wall (a blocking task is assigned, the agent goes on with other work or stops cleanly, and does not poll); a decision the agent is blocked on (a question, not a task); a completion whose check fails (the agent reopens with a comment); a long job with many small wants (the board is not flooded: needs are batched or not filed). Its result is the wording of X8, and one sentence for the question tool's description with its evidence, handed to the sheet's holder.
- **Edges:** blocked-by: `external:` the owner's read (the verbs' names, X6). blocks: B1's M6.
- **Contracts:** owner of X8; consumer of X6.
- **Design inheritance:** D1, D2 ("What agents are told"); U4.
- **Required:** required.
- **Status:** not-dispatched (dispatchable after the owner's read; it needs no built store).

## Cross-Child Contracts

- **X1 — The published set.** `sminos/types/tasks/`: schemas for `state.json`, an act's line and its verdict, `list --json`, `show --json`, `owed`'s answer and the `<task-delivery>` block; envelope examples with the store they were composed from; fixtures, one step each (`before/`, the command, `after/`, the verdict); a manifest with a digest. Written by a generator by hand from this document, never by the commands; `version` 1. Owner B1 (its gate G1 publishes it); B2, B3 and B4 pin it by digest. A change after G1 is a ruling of this document's writer and a new version.
- **X2 — The door.** `sminos task act`, D4's line and verdict; exits 0 when every line was answered, 2 for a line that is not the schema's (nothing applied), 3 for a caller that is a session, 75 for the lock not had in 10 s, 1 for a store it cannot write. Applied once by `key`. Owner B1; the only writer B2, B3 and B4 have.
- **X3 — The reader.** `sminos task list --json` and `show --json` (the model of X1, each task with its asker's state as D5 says the card shows it), the store's `seq` as the change signal, and the fields D7's predicate reads (a task's state, class and askers; an outcome's `wake`, `at` and `landed`). Owner B1; consumers B1a, B2, B3, B4, and later the session manager.
- **X4 — The envelope.** The terminal form is B1's (D5); the steer form is B3's, with the same block. `delivered` through the door is how a deliverer other than this plugin says an outcome reached the model.
- **X5 — The board's address.** A surface that shows the board registers under `$SMINOS_HOME/tasks/surfaces/<name>.json` in the shape of the sheet's surface registration (name, url, reach, pid, heartbeat; alive while the heartbeat is at most 30 s old and the pid runs). Writer B2; reader B1's terminal line.
- **X6 — The agents' verbs.** D2's names, flags and exits, in `task` and in `sminos task`. Owner B1. The three dispatch branches in the `task` plugin (`show` and `comment` by the id's form, `list --human`) and the sentence of the ticket board's D4 they replace ("with those names unused") go to the ticket board's writer before B1's M2.
- **X7 — The wake's notice.** The program's name `tasks` and the two texts of D5 (the wake's, the ended thread's). Owner B1; a reader of project logs may recognize them.
- **X8 — What agents are told.** The skill's body, the start guide's line, and the proposed sentence for the question tool's description. Owner B5; B1's M6 ships what B5 passed.

## Ordering & Dependency Map

    the owner's read ─┬─> B5 ───────────────────────────────┐
                      └─> B1.M1 (G1) ─┬─> B1a               │
                                      ├─> B1.M2  (also: the task plugin's first release)
                                      ├─> B1.M4 ─┐          │
       holder agrees D6, C5.M1 on main ─> B1.M3 ─┴─> B1.M5 ─┴─> B1.M6
                                      ├─> B2 (also: the sheet's C4, C3) ─┐
                                      └─> B3 (also: the sheet's C5) ─────┴─> B4 (also: the sheet's C6)

B1's M1 waits only on the owner. After it, four things run side by side: B1a; M2 once the `task` plugin exists; M4 (what is owed and the wake, in the command); and M3 once the sheet's holder has agreed and C5's M1 is on `main`. M5 (the session's side) needs M3 and M4. M6 ships the words B5 passed. A terminal user has a working board, read with `task show`, from M1 and M2; the push from M5. MAWS's children start from G1 and their own sheet children.

## Verification

- **This document**: one `doperpowers:adversarial-reviewer` review of the design and one of B1's execution document, in one round; then one review of the repair's diff. Then the owner's read.
- **B1**: its execution document names its own; in short, M3's pull request (the extraction) and the pull request that holds M4 and M5 (delivery) are reviewed at the *high* rung, since a mistake there loses or doubles a delivery in the sheet as well; the rest at *medium*. The sheet's holder reads M3's pull request.
- **B1a**: the medium rung.
- **B2, B3, B4**: MAWS's, by their own documents; B2's routes are served by the sheet's page server, whose serving code the sheet's composite reviews at its high rung.
- **Recomposition**: Parent-Level Acceptance run as written on one Mac, by the session that holds this document; a scale review, since B1 and B1a touch one daemon and B1 touches the sheet's module.

## Risks & Mitigations

- **The extraction regresses the sheet.** The sheet's delivery is its most intricate code and is not this unit's. Mitigation: D6's rule 5 (its suites unchanged and the live check), a pull request of its own that holds nothing else, the holder's read, and the order after C5's M1.
- **The holder declines the extraction.** Then R9 cannot be met by shared routes. The fallback this document does not choose by itself: the tasks' outcomes ride the notice (the alternative R9 set aside) until the holder and the owner settle it. It goes back to the owner.
- **A wake that sminos never performs.** If U2's answer is no, D5's wake has no cause. Mitigation: U2 is checked live in M4, before the session's side is built on it.
- **The board floods.** An agent that files every want as a task makes the board useless. Mitigation: B5's fourth scenario gates the wording; the store's cap of 500 open tasks is the backstop.
- **A changed command surprises the person.** The hook adds text to a command the model wrote. Mitigation: the flag reads plainly, goes only on the two assigning commands, and U1's live check looks at the dialog.

## For the owner's read

What this document decides beyond the owner's words, with the choice taken; each stands unless the owner says otherwise.

- **O1. The verbs' names** (D2). `task assign-human` creates; `task show t7` and `task comment t7` are the ticket verbs given a task's id; `task list --human`; `task revise`, `withdraw`, `reopen`. Recommended as written. The other way: a `-human` form of every verb.
- **O2. A human's comment starts a turn** in an idle session, as a done does, and wakes a stopped thread by the same default as the task's class (D5). Recommended: a comment is the human's only way to ask the asker something, and an idle session that is not told sits. The other way: a comment never starts a turn and waits for the next route.
- **O3. The three-day exemption also covers a wake that is still being tried** (D7): a thread is kept while an outcome that asked for a wake is owed to it and is younger than three days. Recommended: without it, completing a blocking task on the fourth day can end the thread before a failed wake is retried. The other way: R10's words alone (an open blocking task), accepting that edge.
- **O4. The door refuses a session by its environment**, which an agent could remove (D4, D9). Recommended: as a guard against mistakes it costs nothing; a confirmation typed at a terminal is the only stronger check sminos has, and a page has no terminal. The other way: a typed confirmation on the command line surface for `done` and `decline`.
- **O5. `devcloud vm down` naming a deleted machine's open tasks is deferred** (Deferred). Recommended: register it as a ticket beside B4, when tasks on other machines become visible at all. The other way: build it in B1.
- **O6. Reading a task acknowledges its outcomes** (D5): the asker's own `task show t7` counts as delivery. Recommended: it is what a session without function hooks has, and it stops a second telling. The other way: only a landed envelope acknowledges, and such a session is reminded at every start.

## Deferred / Out of Scope

**Deferred (may return):** `devcloud vm down` naming the open tasks of the machine it removes (a third plugin; a ticket at materialization). A second asker joining a task (the schema allows it). The human re-classing a task. Adoption of a task by another session. A board across machines on the local page. Captured file references in a task's body. The session manager's ledger reading the store.

**Explicitly out of scope:** the human adding tasks of their own; sync with GitHub issues (R6); events and subscriptions (the owner, 2026-11-24); merging a task outcome into the sheet's envelope or the sheet's page (R8); starting a stopped session to deliver a sheet answer (the sheet's own exclusion, untouched).

## Tracking Map

The baseline is this document's first commit on branch `task-board-spec`. Nothing is on the board: materialization waits on the owner's read.

| child | artifact | status |
|---|---|---|
| B1 | `docs/doperpowers/plans/2026-11-27-task-board-b1.md` | not-dispatched (the owner's read) |
| B1a | ledger at dispatch | not-dispatched (B1's M1) |
| B2 | MAWS's execution document | not-dispatched (B1.G1) |
| B3 | MAWS's execution document | not-dispatched (B1.G1) |
| B4 | its own cut at dispatch | not-dispatched (deliberately late) |
| B5 | ledger at dispatch | not-dispatched (the owner's read) |

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a recomposition check: verify Parent-Level Acceptance as written — all children landed is not the same event — then retrospect.
