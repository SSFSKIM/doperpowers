# Tasks for the human: the Task Board (2026-11-27)

> **Parent:** root — the project's standing purpose (`CLAUDE.md`: a software-development methodology for coding agents, with sminos as the family that lets many sessions work for one owner). **Consumes:** the question sheet (MAWS's composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`, whose sminos part, its child C2, is on this repository's `main`: `sminos/skills/sminos/scripts/sminos_sheet.py`, `sminos_sheet_step.py`, `sminos/hooks/mods/sheet.tsx`, `sheet-model.tsx`, plan `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`); sminos's threads, wake and machine notices (`docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, closed, read and not amended); the ticket board's `task` plugin (`docs/doperpowers/specs/2026-11-24-ticket-board-design.md` on branch `ticket-board-spec`, not built). Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact opens by citing this document (path, child id, parent pin). B1 and B1a are built in this repository; B2, B3 and B4 are MAWS's, and their execution documents are written on MAWS's side by MAWS's holders.

## Purpose

The owner supervises many agent sessions. A session often needs the human to do something in the world: log in, grant a permission, rotate a key, buy, review and merge. Today that is a sentence in a message: nothing lists what the human was asked to do, what each item holds up, or tells the session when it is done. The owner named this as a pain ("나를 기다리는 일이 안 보임", 2026-11-20T05:06Z) and asked for a human to-do board triaged as blocking, must be done at some point, optional, with low latency and the result returned to the asking session.

**After this change.** An agent, or a subagent, assigns a task to the human in one command and keeps working. The human sees every open task of every session on the machine in one list, the blocking ones first, reads a task like a ticket (body, comments), comments on it, and completes or declines it. Whoever asked is told at once, with nobody relaying: the human's outcome and note arrive in the asker's conversation as an envelope, the way a question sheet's answers do. A task stays on the board until the human closes it, whatever became of the session that made it.

**How to see it working.** The scene in Parent-Level Acceptance: two tasks assigned in one command, the terminal closed, the blocking one completed from the board, the session back in the background with the note in its conversation.

**What it must not be.** Not the agents' backlog (R6). Not a question: a decision or an answer goes on the question sheet (D1). Not a blocking call: assigning a task never stops the agent. Not a record of the agents' progress. Not the human's own to-do app: only sessions add tasks. Not a second delivery system: the envelope travels by the sheet's routes, shared and not copied (D6), and a stopped asker is started by sminos's own wake.

## Progress

- [x] (2026-11-27T22:20Z) The owner approved the design ("승인한다, 스펙으로") with both open forks answered (R9, R10). The design of record was the session's design document, version 3; this document carries it, and where review changed a mechanism of it the change is in "For the owner's read".
- [x] (2026-11-27) This document and B1's execution document written and committed as the baseline.
- [x] (2026-11-27) Independent review, round one: the design and B1's execution document, by `doperpowers:adversarial-reviewer`.
- [ ] One review of that round's repair.
- [ ] The owner's read of this document. Nothing is built before it. What the read is asked to settle is "For the owner's read".
- [ ] The sheet's holder agrees the extraction (D6). B1's M3 waits on it.
- [ ] Children: the Tracking Map.

## Terms

- **Task**: one thing a session asks the human to do in the world. It is the human's to-do; the session that asked is its return address.
- **The board**: the list of this machine's tasks, as any surface draws it. "The board" in this document is never the agents' ticket board (GitHub issues, the `task` plugin's first destination) and never the engine's in-session to-do tools.
- **Asker**: who is told of a task's outcome: the thread that assigned it and, when a subagent assigned it, that subagent.
- **Thread**: sminos's record of one line of work on a machine (`sminos/skills/sminos/scripts/sminos_threads.py`): a spawned seat, or a session its human opened. It has a current session, is *stopped* when no process holds that session (the record's stop mark, set by the daemon's sweep), and is *ended* by a retire or by the three-day rule. A `/clear` and a fork each begin a new thread; a resume continues one.
- **Successor**: the session a `/clear` began in the place of the one it left, as sminos witnessed it at the clear (`cleared_witness`).
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
- **MAWS-run session**: a session whose controller is the MAWS app (sminos's lane B, `sminos_records.lane_of`). MAWS delivers to it and sminos never wakes it. Lane is the test, not the absence of a thread: a session MAWS adopted keeps its thread record, and a session with no thread need not be MAWS's.

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

1. **The sheet's delivery lives in a mod that runs only where the sheet is chosen.** `sheet.tsx` holds the routes (`deliver`, `submitIdle`, `sendTo`, `take`, `putBack`, `withResultRoute`, `endTurn`, the `session.append` landing hook) inside the state of a session that chose the sheet (`routable()`, `isStarted`); the sheet is off by default (`SHEET_DEFAULT`), and, a MAWS launch that carries the sheet's marker apart, off for every session that is not interactive (`chooseStart`). A task's asker is any session. So "by the sheet's routes" needs the routes to run in a session that never chose the sheet: the routes become a module of their own (D6).
2. **An envelope's text is composed by the command, its routes are the mod's.** `sminos_sheet_step.py` composes (`envelope`, `envelope_text`, `block`; `BUDGET` 60,000 UTF-16 units, `ENVELOPE_KEYS` 200); the mod receives `ready: [{recipient, keys, text, wakes, more}]` and never composes. The budget's reason (the C2 plan's I7 and its engine measurement): the engine hands the model one context entry whole only up to 100,000 characters, and the entries of one result or prompt together only up to 200,000. The readers that find the highest question id a conversation holds (`floorOfSheetText`, the transcript's floor search) accept a delivery block only in a text that opens with the sheet's head, known one-line notices apart.
3. **The sheet's published set is frozen.** `sminos/types/sheet/` (version 1) is what MAWS pins by digest; `sminos/tests/test_sheet_contract.py` and `test_sheet_step.py` hold the command to it, composing every published envelope.
4. **The sheet's routes are about to change once more.** The sheet's C5 has one pull request in this repository, its M1 (plan on MAWS's `question-sheet-c5`, `docs/doperpowers/plans/2026-11-27-question-sheet-c5-maws-run.md`, §S): in a MAWS-run session `take` carries notices and contexts, `withResultRoute` no longer returns early for the runner, and the `prompt.submit` hook adds a context when a prompt's text holds a delivery block. It is under review and not built.
5. **Only a message addressed to a thread wakes it.** The daemon's `deliver_owed` → `deliver_next` → `wake_member` → `wake` starts a stopped thread for a log event with a `to`; there is no registry of other things owed (`sminos_owed.py` is the uplink's). A program of the machine writes such an event with `sminos say --notice <program> "@alias …"`, run with no session; `sminos/tests/test_notice.py` shows an addressed notice waking a stopped thread its human opened, once, with its frame. A sheet answer wakes nothing. What sminos publishes of a thread (`wake_of`, `why_of`) is its eligibility as other machines read it; whether this machine would wake it is `wake_here`. A notice's delivery can also answer gated, pending behind another event, or held (`deliver_say`), so a notice written is not a thread woken.
6. **A `/clear` does not continue a thread.** The session left stays the current session of its own thread, which stops and later ends; the new session is a thread of its own and takes the alias (`release_alias` writes `released: {alias, at}` on the left record; `released_alias` reads it). The clear is witnessed with both sessions in hand (`cleared_witness`, read by the record hook's release), but the record keeps only the alias and the time: nothing stored points from the left thread to the new session, the new session need not be in the left one's project, and the alias can later be another session's. A fork is a thread of its own.
7. **The three-day rule and its one exemption.** `sweep_threads` (`sminos_daemon.py`) finds a thread due when its `stopped` mark is older than `thread_end_after()` (three days); `end_due` leaves it stopped while devcloud's census says it owns a host, saying so once in `daemon.log` (`holding`); `end_stopped` and `sminos.end_by_rule`'s guard decide again under the record's lock. An ended thread is not woken (`wake_of` answers `ended`); it returns only when a process holds its session again.
8. **A subagent's shell cannot say which subagent it is.** It carries its parent's `CLAUDE_CODE_SESSION_ID` and no agent id. A `tool.call` hook is told `e.agentId` (absent on the main loop; a subagent's is `a` and sixteen hex digits, a teammate's `<name>@<team>`), may hand a changed `command` to `next`, and the permission check judges the changed bytes (`devcloud/hooks/mods/secrets.tsx`; `hooks/mods/README.md`: "the permission check sees the restored bytes").
9. **No sminos mod rewrites a command today.** `backticks.tsx` has a real shell lexer and uses it only to refuse a call. The bridge posts the input its `tool.call` hook received and offers a remote answerer the engine's permission suggestions only when the engine's input is exactly that (`bridge-requests.tsx`, `isSeen`); doperpowers' appeal keys a pass on the input as it saw it. A rewrite made beneath them loses both for that call, as a restored secret's handle already does. sminos's module is seated outside every user-tier plugin's (`prependPlugins`), and within it registrations nest in order, the first outermost.
10. **A caller inside a session is known by `CLAUDE_CODE_SESSION_ID`.** `sminos channel lead` and `say --notice` are refused when it is set. An agent can unset it; only a typed confirmation on `/dev/tty` is beyond one (`sminos_visibility.confirmed`), and a page has no terminal. A daemon started from a session's shell inherits the variable, which is why the sheet's low-level door does not test it.
11. **The `task` plugin does not exist yet.** The ticket board's spec makes it (its M1, the plugin's first release): Python, standard library only, importing nothing of sminos, finding `sminos` through `TASK_SMINOS`, the PATH, then the marketplace clone, each call bounded at 30 s; exits 0 done, 1 failed, 2 usage, 3 refused by a rule; body from `--body-file`; reading verbs take `--json`. Its dispatch keeps the Task Board's verbs unused, and `task assign-human` exits 2 saying the Task Board is not built.
12. **The line above the prompt and the start guide have precedent.** `registerSheetBand` draws through `ui.render` for `AbovePrompt`; `sminos guide` (`guide_text`, run by the shell hook `smns-guide.sh`) joins lines, an optional one only when it has something to say; the hook exits before any Python on a machine that is not enrolled, and the text is empty for a session that is no member.

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

`--body-file -` reads standard input, so a body rides a heredoc; the ticket verbs' `--body-file F` is kept, since one CLI has one way to give a body. `assign-human` prints the id and the line the human will see (`t7 blocking "Log in to the console"`); every verb returns at once and prints what it touched. `show` and `comment` are also ticket verbs: the `task` plugin's dispatch sends them to the human's board when their first argument is whole `t[1-9][0-9]*`, and `list` when it carries `--human`, before anything of the ticket board is looked for (its configuration, `gh`): the human's board is the machine's and works outside any repository. `revise`, `withdraw` and `reopen` exist only for the human's board; given a ticket's number they exit 2. The alternative weighed: a `-human` form of every verb (seven names, nothing shared with the ticket dispatch). It lost because an agent would learn two vocabularies for the same acts while the id already says which board is meant; its cost is three branches in the ticket verbs' dispatch, which goes to the ticket board's writer (X6).

The verbs are a thin front over the store's commands in sminos (D3): each runs `sminos task <verb>` with the same arguments, passes its output and exit through, and where `sminos` is not found exits 1 saying that the human's board is kept by sminos and it is not installed. The store's commands are usable directly (`sminos task assign …`), which is what a session without the `task` plugin does and what B1 is tested through before the plugin exists.

**Who may change a task.** Any session comments on any task. `revise`, `withdraw` and `reopen` are the asker's: the session that is the task's target now (D5: the asker's thread's current session, or the successor a witnessed `/clear` gave it), or the current session of the asker's thread; for a task with no thread, the asker's session itself and no other. Another session is refused, exit 3: a fork, a session that once filled the same seat, and a second session with no thread are all another session. Within a session any agent may change the session's tasks: a shell cannot tell them apart, and the subagent's attribution is a delivery hint, not an owner.

**Who asked.** The command learns the session from `CLAUDE_CODE_SESSION_ID` and its thread from sminos. It cannot learn which subagent ran it (baseline 8), so sminos's mod tells it: a `tool.call` hook on Bash, told `e.agentId`, finds each simple command that is `task assign-human` or `sminos task assign` and puts `--asker-agent <id> --asker-name <word>` directly after the verb. So the attribution is part of creation, and the person consents to the command as changed, which reads plainly. **[binding — the flag's names and its place are what the permission rules the owner writes will match]**

- The flag goes after the verb and not at the command's end, because a command can end in a heredoc, a comment or a list (`task … && echo ok`), and not before the command as a variable, because a leading assignment can stop an allow rule for the command from matching. The hook finds the command with `backticks.tsx`'s lexer, which must give it where the verb's word ends in the command's own bytes; the lexer keeps decoded words today, so it is taught to keep those positions for a literal command word and verb, and a command where it cannot (the verb reached through a quote's continuation, a variable or a substitution; a syntax it gives up on) is left unchanged. So is a call whose agent id is not whole `[A-Za-z0-9_.@-]{1,128}`. The asker is then the thread alone.
- The name is the agent's description or type as `$.agent.list()` gives it, reduced to `[A-Za-z0-9_.-]` (any other run a `-`, at most 64 characters), left out when nothing remains.
- The hook is sminos's, registered first in `sminos/hooks/mods/register.tsx`, so it is the module's outermost and what sminos's other hooks and the plugins seated inside sminos receive is the command as it will run. What each observer then sees: the bridge posts the command with the flag (it reports what ran, not what the model first wrote); the bridge's `isSeen` and the appeal's pass hold for the call as they hold today, which is to say not when a secret's handle is restored beneath them; `to-human`, seated outside sminos, and the engine's own record of the call keep the model's command. In the `task` plugin the hook would sit in the user tier, beneath the bridge and the appeal and in no fixed order against devcloud's secrets guard.
- A permission rule or a classic `PreToolUse` check that depends on the arguments after the verb sees one more argument. U1 looks at what the engine does with each; no rule is promised to match.
- Where the mod is not loaded the asker is the thread alone. An agent that writes the flag itself is believed: it is a delivery hint.

**What agents are told.** In the plugin's skill (`task:human-tasks`), in one line of sminos's start guide, and in one sentence of the question tool's description (the sheet's holder's to agree; D6's second ask): D1's line between a task and a question; say in the body how the human knows it is done; mark `blocking` only what the work cannot continue without; the completion is pushed to you, so do not poll the list; a subagent that is blocked returns to its caller with the task's id; check the result yourself, and reopen with a comment when it fails; the human's acts are the human's, so never complete or decline a task yourself. The words are B5's to settle before they ship (X8).

### D3. The store

One store per machine, under the sminos home (`$SMINOS_HOME/tasks/`), holding every task assigned on that machine. It is not the sheet's record and shares no file with it. **[binding — one store a machine is what lets a task outlive its session (R4) and the board list across sessions]**

- **One file, replaced whole.** `tasks/state.json` holds every open task and every closed one still kept, the outcomes owed, the acts already applied by key, and the successors witnessed at a `/clear`; a change reads it, changes it and replaces it (a synced temporary file and `os.replace`) under an exclusive lock on `tasks/.lock`, waited for at most 10 s (exit 75 past that, as the sheet's door). A reader takes no lock: a replace is whole, so one read is a consistent state, and `seq` (+1 at each change) orders two reads. The alternative, a file a task, was weighed for write cost; it lost because every reader wants the list, and the store is small (at most 500 open tasks; an `assign` or a `reopen` that would make 501 is refused, exit 3, saying how many are open).
- **Every change is one step under the lock, made by the command that causes it**: an agent's verb, or a human's act arriving through the door. There is no inbox, no drain and no daemon in the path of a write: the sheet needs an inbox because one session orders every step, and no session owns this store. Whoever holds the store's lock takes no other lock of sminos's and appends to no log while holding it; the one place that needs the store and a thread's record together, the ending pass, takes the store's lock first (D7).
- **The contract carries a version.** `state.json` holds `version` (1). A command built for an older version than the file's refuses to write (exit 1, saying which plugin to update), deciding on the file as it reads it under the lock, and still reads what it understands; a writer keeps every field it does not know, on the store and on each task, since several plugin versions run on one machine at once. What another repository reads is the published set, `sminos/types/tasks/` (X1), made as the sheet's is: written by hand by a generator from this document's shapes, never by the code it holds to account.
- **Lifetime.** A `/clear`, a fork, a stop or an end of the asker removes nothing (R4). An open task leaves the board only by the human's done or decline or an agent's withdrawal. A closed task is kept 30 days, for reopening and for a read-only list of what was closed, and past that for as long as an outcome of it is owed: the list of what was closed stops showing it, and the daemon's hourly duty removes it once nothing of it is owed. A delivery is never ended by the history's limit.

### D4. What the human does, and the door

On a task: **comment** (it stays open), **done** with an optional note, **decline** with a reason. Every surface performs them through one command of sminos, the door, which applies the act at once and answers with its verdict. **[binding — one door is what makes every surface's act the same act, and is the only writer B2, B3 and B4 have]**

    sminos task act            # one JSON object a line on stdin, at most 50; one verdict a line on stdout

    {"v":1,"key":"<a UUID the surface mints for this act>","task":"t7","act":"done","revision":2,"text":"logged in with account B","wake":null}

- `act` is `done`, `decline`, `comment`, `seen` (the human opened the card: it clears the row's "Updated" up to the store's `seq` the card was drawn from, which the line names) or `delivered` (X4: whoever delivered an envelope itself says so, naming `keys`).
- A `done` or a `decline` names the revision the human read and is refused `stale` when the task was revised since, with the current revision, so the card can say so; a comment is never refused as stale. An act on a task no longer open answers `closed`; an unknown id, `unknown`.
- `wake` is the human's choice for a stopped asker (R5): `true`, `false`, or `null` for the default (D5).
- **An act is applied once.** A key is a UUID, so two surfaces never mint the same one. The door keeps each applied act's verdict, and a digest of its line, by its `key` for as long as the task is kept; the same line again answers the first verdict and changes nothing, and a different line under a key already used is refused (`key-reused`) and changes nothing. A surface that did not hear the verdict sends the act again.
- **The verdict is what the door decided, and does not change.** `{"v":1,"key":…,"task":"t7","verdict":"applied|stale|closed|unknown|refused","revision":2,"state":"done","outcome":"t7.3","told":"running|wake-asked|next-resume|ended|not-reachable|maws"}`: `told` is the door's judgement of the asker in the same step that applied the act. Whether a wake that was asked for has happened is not the verdict's to say: it is read, and read again, from the task (`show --json`: each outcome's wake attempts and what sminos answered for each).
- **The door refuses a caller that is a session** (`CLAUDE_CODE_SESSION_ID` set; exit 3): an agent does not complete the human's task. This guards a mistake, not an adversary (baseline 10); D9 says what is trusted. A surface that has authenticated its human runs the door with that variable removed from the child's environment, since a surface's daemon may have been started from a session's shell.

The command line is the first surface and goes through the door: `sminos task list`, `sminos task show t7`, `sminos task done t7@2 [--note "…"] [--wake|--no-wake]`, `sminos task decline t7@2 --reason "…"`, `sminos task comment t7 "…"`. The handle is the sheet's: `t7@2` names the revision read; a bare `t7` names revision 1.

### D5. Telling the asker (R9: an envelope)

After the door applies a `done`, a `decline` or a `comment`, an **outcome** is owed to the asker and delivered as a task envelope by the sheet's routes. It stays owed until there is evidence it reached the asker.

**The envelope.** One head line, one line an outcome, the command that reads a task's thread, and the block:

    [tasks v1] From the human, on tasks you assigned:
    t7 "Log in to the console" → done. Their note: "logged in with account B"
    t9 "Rotate the signing key" → declined. Their reason: "not before the audit"
    t4 "Buy the domain" → a comment: "which registrar?"
    Read a task's whole thread: sminos task show t7
    <task-delivery>{"v":1,"keys":["t7.3","t9.2","t4.5"],"outcomes":[{"task":"t7","revision":1,"outcome":"done","note":"logged in with account B"},…]}</task-delivery>

- An outcome's key is `<task>.<n>`, `n` the task's count of acts. The block is one line of JSON with `<`, `>` and `&` escaped as the sheet's block escapes them; it lists what was done, declined and commented on and nothing else, one entry of `outcomes` a key, in the keys' order. **[binding — the block is what B3's steer carries unchanged and what a landing is read from]**
- A line names what the model needs to place the outcome: after the id, `(assigned by the subagent <name>, <id>, which has ended)` when a subagent's outcome goes to the main conversation, `(assigned by the conversation this one replaced at a /clear)` for a successor, and `(acted on <local time>, while this session was stopped)` for an outcome applied while no process held the session.
- To a subagent the envelope opens with a line saying it comes from the human through the task board and not from its coordinator, as the sheet's does: the engine credits a plugin's send to the coordinator.
- The command it names is `sminos task show`, the store's own, because the envelope is composed wherever the store is and the `task` plugin may not be installed there.
- **The budget is smaller than the sheet's**: at most 20,000 UTF-16 units and 50 keys an envelope, so that a task envelope beside a full sheet envelope and a full context stays under what the engine hands over whole (baseline 2; D6, rule 2). A note is in the prose whole up to 2,000 characters; past that its first 500 and "the rest: `sminos task show t7`"; the block's `note` is the first 500 with `noteCut`. What is owed to one recipient is packed in the order applied (each outcome carries the store's `seq` of its act), what starts a turn first; when not all fits, the head says `More follows.` and the next envelope is composed afresh once this one landed.
- The command composes it (`sminos task owed`), from the store, to the published examples; the mod never composes. It answers the same shape the sheet's step gives its mod, `ready: [{recipient, keys, text, wakes, more}]`, which is what lets one set of routes carry both (D6).

**Who it goes to: the target.** The store decides at each read, from the task's asker, whom its outcomes go to now.

- **The asker's thread's current session**, when a process holds it. A cleared conversation that its human opened again is told itself.
- **Otherwise a successor.** At a `/clear` sminos witnesses the session left and the session begun (baseline 6); when the store exists, the record hook writes that pair into it. The target is then the last session of that chain whose thread has not ended, running or stopped; the left thread is not woken while one exists. The link is the witnessed pair and never the alias, which another session can come to hold. A clear nobody witnessed (a seat's; a session that is no member) leaves the outcome with the conversation that was left. **[binding — the same answer decides whom the human's note is shown to, who may revise the task, and whom D7 keeps from ending]**
- **Otherwise the asker's thread's current session**, stopped or ended.
- **A session with no thread** is its own asker by its session id, and only that session.
- **A subagent.** An outcome of a task a subagent assigned is that subagent's (R2) until the session's mod says otherwise: only the mod sends to a subagent, and only the mod hands such an outcome to the main conversation, by a step in the store (`reroute`), when the subagent has ended or the send was not delivered. So a second deliverer reading the same store (MAWS, for a session it runs) never takes an outcome a send is carrying.

**Who delivers.** The target's controller, which is not the same question as whether it has a thread: for a MAWS-run session (lane B), MAWS, on its own steer, as for the sheet (B3); for every other, this plugin's routes. The answer `owed` gives says which (`runner`), and carries each owed outcome's fields beside the ready envelopes, so MAWS composes its steer from the same read.

**When a turn starts for it.** In a running session the envelope leaves by the first route that opens: as the plugin's prompt when the session is idle, as context on the model's next tool result, or as context on the next prompt. Only some outcomes start a turn by themselves (open the idle route): a `done`, a `comment`, and a `decline` of a blocking task. A decline of a task that is not blocking starts no turn in a running session; it leaves with whichever route opens next and shows in `task list --human`. An outcome applied while the session was stopped starts no turn after the resume unless its act asked for a wake: it leaves with the first route that opens, marked with its time.

**A stopped thread, and the human's choice** (R5). The card shows the asker's state before the human acts: running; stopped and to be woken; stopped and held, with sminos's reason; ended; run by MAWS. It is this machine's own judgement (`wake_here`), read afresh when the card is drawn and again at intervals, since a session stops without the store changing (X3). For a stopped target the act's `wake` applies: by default a blocking task's outcome asks for a wake and any other waits for the next resume, and either can be switched for that act, a decline of a task that is not blocking included. The default is evaluated when the act is applied, so a session that came back meanwhile is simply told.

- **The wake is sminos's.** For an outcome that asked for one, a notice from the program `tasks` is addressed to the target's session, in its project, and sminos's delivery owns it from there: it starts the thread, or holds it with its reason and tries again as it does for any message. The notice carries no outcome and no note, so the human's words stay on the machine and out of a synced log: `[tasks v1] The human acted on t7, a task this conversation assigned. The outcome is delivered here as a task envelope; if none follows, read it with: sminos task show t7`. Once the thread runs, its mod reads what is owed and the routes deliver; an outcome whose act asked for a wake starts a turn like a fresh one.
- **One attempt a stop, written once.** An attempt belongs to one stop of the target: the pair of its session and the stop mark its record carries. A notice is due when the outcome is owed, asked for a wake, the target is stopped, and no attempt is recorded for that pair. It is appended under an identity made of the outcome's key and that pair, by a helper that appends nothing when the log already holds that identity, and only then recorded on the outcome with what sminos answered (woken, held and why, gated, pending). So a death between the two writes makes the next pass find the notice already in the log and only record it; a thread that was woken, died before reading and stopped again gets a second attempt for its new stop; and an outcome gets at most three, after which it waits for the next resume and its card says so.
- **The door tries at once, the daemon after.** The door makes the attempt in the same call when the target's stop mark is there; the daemon's tick makes any attempt that is due: for a target that had no stop mark yet, for a new stop, for a door that died. With the daemon down, what is due stays due.
- The alternative R9 set aside, recorded once: the notice alone as the delivery, with the agent reading the task itself. The notice survives only as the wake's cause, because sminos wakes for nothing else (baseline 5).

**An ended thread** cannot be woken: the outcome stays on the board and stays owed, the verdict's `told` is `ended`, and one untagged notice goes to the thread's project log, written once by its identity as an attempt is (`tasks: t7 "…" was completed; its asker <alias> has ended. The outcome is on the board: sminos task show t7`). If the thread returns (its human opens the session again) the outcome is delivered then.

**How an outcome stops being owed.** Only by evidence that it reached the asker:

- its envelope **landed**: the mod found the block in a stored row one of its routes wrote, or a send to the subagent answered delivered, and ordered `sminos task landed`;
- a **`delivered`** act, from a deliverer other than this plugin (X4);
- the asker **acknowledged** it by key: `sminos task ack t7.3`, run in the asker's session.

Reading a task acknowledges nothing: `show` is a read, since a command run is not a model that read it (a sibling subagent runs in the same session; output can be cut or redirected). The acknowledgement is what a session without function hooks has. Its start line, printed by the SessionStart shell hook from the store whether or not the machine is enrolled, names each outcome still owed with the commands that read and acknowledge it, and names them again at each start until they are acknowledged. Delivery is at least once: an asker can be told twice of one outcome across a crash.

**The outcome's states and who moves them.** Every transition is one command under the store's lock; the mod writes nothing to the store (a hook can neither lock nor replace a file, the sheet's K1).

| from | event | by | to |
|---|---|---|---|
| — | a `done`, `decline` or `comment` applied | the door | `owed`; its recipient the asker's subagent, else the main conversation; `wake.asked` resolved to a boolean; `acrossStop` set when no process held the target session |
| `owed` | a wake attempt due (above) | the door in its call; else the daemon's tick | `owed`, the attempt recorded with sminos's answer |
| `owed`, a subagent's | the subagent has ended, or a send to it was not delivered | the mod's `sminos task reroute` with keys | `owed`, its recipient the main conversation |
| `owed` | the envelope's block found in a row of the routes' kinds, or at a start in the transcript; a send answered delivered | the mod's `sminos task landed` with keys | `landed` |
| `owed`, the main conversation's | `delivered` naming the key | the door (MAWS's deliverer) | `landed` |
| `owed` | `sminos task ack` naming the key, in the asker's session | the command | `landed` |
| `landed` | its task closed 30 days and nothing of the task owed | the daemon's hourly duty | gone with the task |

A flight (an envelope on a route, until it lands or fails) is the mod's and in memory, exactly the sheet's: its states, the turn it belongs to and what settles it are D6's shared code and are not restated here.

### D6. The extraction: one set of routes for both envelopes (a proposal, waiting on the sheet's holder)

R9 makes the delivery the sheet's way, and copying its routes would put two modules in one process each submitting prompts, attaching contexts and reading rows for landings, with no order between them. So the routes are shared, and because they must run in a session that never chose the sheet (baseline 1), they leave `sheet.tsx` for a module of their own. The sheet's holder asked to be told before any extraction and rules on the sheet's contract; **nothing below is built until that holder agrees, and what they change, this section takes.** It is drawn as the smallest change that leaves the sheet's published contract untouched and the sheet's behaviour as it is.

**What moves.** From `sminos/hooks/mods/sheet.tsx` to a new `sminos/hooks/mods/delivery.tsx`: everything that handles a flight and nothing that knows what a question is.

- The `Flight` type; the bookkeeping of the main turn (`mainTurn`, `turns`) and of stopped subagents; the queue of notices and the one context a route carries.
- The routes: `deliver` (the idle route's opening and a send to each running subagent), `submitIdle`, `sendTo`, `take`, `putBack`, `withResultRoute`, the settling at a turn's end (`endTurn`), `failFlight` and `release`.
- The hooks that are routes: `tool.call` for any tool (the result route), `prompt.submit` (the prompt route), `turn.start`, `turn.complete`, `session.append` (landing), and the classic `SubagentStop`.
- From `sheet-model.tsx` to a new `delivery-model.tsx`: `isRouteRow`, `contentTexts`, `PLUGIN`, and the frame of `blocksOf`, `keysIn`, `heldKeys`, `landedSearchArgs` and `searchedKeys` that finds a block of a given element and hands its payload to that element's own validator. The sheet's validator (its `answered` and `dismissed` held against `keys`) stays the sheet's, in the live reader and in the transcript's search alike, so what counts as a sheet landing does not widen. `sheet-model.tsx` keeps each function under its own name, bound to its element and validator, so its exports and their tests stand.

**What stays the sheet's.** The start choice, the tool, the steps and the drain, the view, what may open the idle route for a sheet (`freshWake`, `isWaking`, the spent keys), the `landed` and `reroute` steps (`orderKeys`), the ended-subagent notice, the start's search of the transcript (which calls the shared search with its own element and validator), the floor's readers, the band, the rows and their receipts, the snapshot, the removal at a `/clear`. All of `sminos_sheet.py`. All of `sminos_sheet_step.py` but one parameter (below).

**The seam.** `delivery.tsx` knows lanes and sources. A lane is one session generation's delivery state, as the sheet's `Gen` is today: made at a start, retired at a session change. The sheet is the first source, the tasks the second.

    export type Ready = { recipient: 'main' | { agentId: string }; keys: string[]; text: string; wakes: boolean; more: boolean }
    export type Source = {
      name: 'sheet' | 'tasks'            // in log lines and the toast
      element: string                    // the block's element: 'sheet-delivery' | 'task-delivery'
      /** The keys of a well-formed block of this element, or undefined: the element's own validator. */
      keysOf: (payload: unknown) => string[] | undefined
      /** The envelopes ready now, none of whose keys the delivery holds in flight. */
      ready: () => readonly Ready[]
      /** Whether this plugin opens the main conversation's routes for this source's envelopes. */
      opensMain: () => boolean
      /** What may open the idle route for the main envelope now, or undefined; what a failed submit spends. */
      wake: (envelope: Ready) => { keys: string[]; spent?: unknown } | undefined
      /** Keys the evidence says landed. True once recorded; false leaves them in flight, asked again at the next look. */
      landed: (keys: readonly string[], by: 'row' | 'send') => Promise<boolean>
      /** A send to a subagent that was not delivered. True once the source has made them the main conversation's. */
      rerouted: (keys: readonly string[], agentId: string) => Promise<boolean>
      /** A route did not bring these to the model: they are ready again. */
      missed: (route: 'idle' | 'result' | 'prompt' | 'send', keys: readonly string[], why: string, woke?: unknown) => void
      /** This source's notices waiting for a route, and a context owed once. */
      notices: string[]
      context?: string
      /** A context for a prompt whose text is given, bounded by the source; the prompt is never held past that bound (the sheet's C5 M1). */
      promptContext?: (text: string) => Promise<string | undefined>
      /** What the mixed hooks tell a source, in the hook's own dispatch, before any route opens. */
      onAgentStop?: (agentId: string) => void
      onRow?: (texts: readonly string[]) => void
      onMainTurn?: (event: 'start' | 'complete') => void
    }
    export function registerDelivery(on: On): void       // the routes' hooks, registered where registerSheet registers them today
    export function openLane(session: string, port: DeliveryPort): Lane
    export function retireLane(lane: Lane): void
    export function addSource(lane: Lane, source: Source): void
    export function reconsider(lane: Lane): void         // a source's view changed: the routes look again
    export function resultRoute<R extends object>(lane: Lane | undefined, agentId: string | undefined, origin: { plugin: string }, signal: AbortSignal, result: R): R   // for a tool that answers its own call, as the sheet's does

The type's names are advisory; these are binding **[the joint view: both envelopes and the sheet's unchanged behaviour depend on them]**:

1. **One flight an envelope, a source.** A key is a source's own. A row's landing is attributed by the element of the block that holds it and counted only when that element's validator takes the block; a send's delivered answer is the subagent route's landing. A sheet key and a task key never meet.
2. **One composer, one total.** Where a result or a prompt route opens, `take` reserves in one synchronous step what rides, in this order: the sheet's envelope, its notices and its context; then the tasks' envelope, only while everything this plugin adds to that result or prompt stays within 150,000 UTF-16 units together. Each is a context entry of its own. What does not fit stays ready and nothing of the sheet's is ever left behind for a task's.
3. **One idle prompt, one source.** An idle prompt carries one source's envelope with that source's notices above it, as the sheet's does today; when both sources have an envelope that wakes, the sheet's goes first, and the tasks' leaves on that turn's first tool result or, after the turn, on the idle route. No text that holds a sheet envelope holds anything of another source, so the sheet's floor readers find the head they require (baseline 2).
4. **A source that has nothing costs nothing.** With no source ready the hooks pass everything on, as the sheet's do where it is not chosen.
5. **A lane is a generation.** A result dispatched in a lane that has retired carries nothing of the lane after it, and a source's answer that arrives after its lane retired changes nothing.
6. **A key stays in flight until its receipt is recorded.** Handed to `landed` or `rerouted`, it is unavailable to every route until the source answers true, across the source's own retries; a subagent's keys belong to that send from the hand-over until then.
7. **Closing the main routes closes envelopes only.** A source whose `opensMain` is false still has its notices, its context and its prompt context carried (the sheet in a MAWS-run session, after its C5 M1).
8. **The mixed hooks keep their order.** At a subagent's stop the source hears of it before any route opens (the sheet queues its notice ahead of the completion prompt and orders its drain); at a stored row the landing is ordered and then the row's texts go to the source (the sheet's receipts); a main turn's start and completion reach the source (the sheet's snapshot).
9. **The sheet behaves as it does today.** Its envelope's bytes, its steps, its record, its landings, its failures and their toast are unchanged; its suites (`sminos/tests/mods/sheet*.test.ts`, `test-sheet-step.sh`, `test_sheet_step.py`, `test_sheet_contract.py`) pass with no assertion changed, an import's path apart, and `live-sheet-check.py` is run once on the result.

**What a reader of a sheet session can see differ.** One thing: a tool result or a prompt may carry a task envelope as one more context entry, after the sheet's. No text the sheet wrote changes, and no prompt of this plugin's holds both.

**What of the sheet's contract changes.** Nothing. `sminos/types/sheet/` is not touched: version 1 and its digest stand, and `python3 -B sminos/tests/sheet-contract.gen.py --check` passes. No event, view or record field of the step moves.

**The command's side.** Nothing is extracted. The tasks' composer imports the sheet's measures from `sminos_sheet_step` (`units`, `jstr`, `mark`), and `block(obj)` there gains a second parameter, the element's name, defaulting to `sheet-delivery`, so one function escapes both blocks; its output for the sheet is the same bytes, which `test_sheet_step.py` proves by composing every published envelope. If the holder would rather the step were not touched at all, the tasks' module carries its own copy of those six lines and a test that feeds both the same objects.

**The order, with the sheet's C5.** The sheet's C5 M1 (baseline 4) changes `take`, `withResultRoute` and the `prompt.submit` hook, three of the things that move. B1's M3 is built from a `main` that holds that pull request, so its change is carried across once, in the shared code, with the behaviour its tests and probe pinned, and is never made twice: the MAWS-run branches of `take` and `withResultRoute` become rule 7, and the context it adds to a prompt whose text holds a block becomes the sheet source's `promptContext`. B1's M1, M2 and M4 touch none of the sheet's files and do not wait. If that pull request were withdrawn or long delayed, the other order stands: the extraction lands first and C5's M1 is rebased onto `delivery.tsx`, its three changes made there; that is the holder's call, and this document's order is the first.

**What it touches of the holder's.** In this repository: `sminos/hooks/mods/sheet.tsx`, `sheet-model.tsx`, `register.tsx`, their tests' imports and `sminos/tests/mods/sheet-harness.ts` and `test-sheet-step.sh` where they reach the routes' state; one parameter in `sminos_sheet_step.py`; the paragraphs of `sminos/hooks/mods/README.md` ("sheet", Delivery) and of the C2 plan (I9's first paragraph, I11's layout) that name where the routes live; `docs/doperpowers/TECH-DEBT.md` rows 41 to 43, which name `sheet.tsx` for limits that become the shared module's. No branch of the holder's in MAWS is touched; C5's plan names `take`, `putBack`, `withResultRoute` and `keysIn` "as built" in `sheet.tsx`, which stays true while its M1 lands first.

**The second ask of the same holder**, apart from the extraction: one sentence in the question tool's description (`DESCRIPTION`, the sheet's C1 text) that sends an act to the task board. Its words are B5's result; the description is the holder's, so B5 hands them the sentence with its evidence.

### D7. The three-day rule (R10)

A thread is not ended by the three-day rule while it is the target of an open blocking task (D5: the thread that would be woken, so a cleared conversation with a living successor is not kept for a task its successor now answers for). The change is in the ending pass and nowhere else: in `sweep_threads`'s test of what is due, where devcloud's census is not yet asked, and again where the end is committed. A thread kept this way is said once in `daemon.log`, as a thread that owns a host is. **[binding — B1a's change must agree with the store B1 builds: what its predicate reads is X3's]**

- **The last look and the end are one step against the store.** A task can come to protect a stopped thread while it is stopped: its successor reopens a task or revises one to blocking, or the human completes a needed task and asks for a wake. So `end_by_rule` takes the store's lock, then the record's, looks again, and commits the end before letting the store's lock go; a store writer holds no other lock (D3), so the order is fixed and nothing can wait in a ring. An act therefore lands wholly before the end, and keeps the thread, or wholly after it, and its verdict says `ended`. A lock not had in time ends nothing this pass.
- The exemption also holds while an outcome that asked for a wake is owed to the thread and its act is younger than the period. Without it a blocking task completed on the fourth day closes the task, lifts the exemption, and the hourly pass can end the thread between a wake that failed and its retry, which is the case R10 was asked about. Bounded by the period, counted from the act and never from an attempt, so a thread sminos holds for good is not kept for ever by one outcome.
- A store that cannot be read is no answer, and no answer keeps the thread: an end is not undone by the daemon.
- The channels-and-threads design says the rule applies to every thread, with the host exemption. That document is closed and is not amended; the rule as it stands is written where the code's own account is, `sminos/skills/sminos/scripts/CLAUDE.md`, and here.

### D8. Surfaces

- **The board**: the open tasks across sessions, blocking first, then needed by due date, then optional; each row its title, project, asker and the asker's state, due date, and "Updated" when an agent revised, commented or reopened since the human saw it. A card renders agent Markdown under the sheet's link policy (links limited to `http` and `https`, any other drawn as its text) and shows a link's host plainly.
- **A notice to the human**: a new blocking task raises a notification on the machine, as a question does today (`$.ui.notify` from the asker's session, when its mod sees its own new blocking task in the store); the phone's push comes with B4.
- **The command line**: `sminos task list|show|done|decline|comment` (D4). The first surface, and what remains when no page is reachable.
- **The terminal**: a line of its own above the prompt while the session has open tasks, `2 tasks for the human (1 blocking) · <the board>`, where `<the board>` is a live surface's board address (X5) or `sminos task list`.
- **The local page**: `mawsd`'s page server carries the board as a page of its own under the sheet page's origin, pairing and four rules (B2).
- **The MAWS app**: a native board of its own; how a blocking task marks its session there is the owner's, on drawn frames with the board's look (B3).
- **The phone and other machines**: after the sheet's own remote child (B4).

### D9. What is trusted, and the limits

- **Trust.** Every session on the machine runs as the owner and can write the store's file; the store's rules (who revises, the door refusing a session) keep agents that mean well from stepping on each other and are not a defence against one that does not. An agent that strips its environment to complete the human's task is misbehaving in the way one that edits the file is; B5's login-wall scenario records the door and fails if an agent calls it.
- A machine that is off shows nothing elsewhere until B4. A machine that is deleted takes its open tasks with it; `devcloud vm down` naming them first is deferred work (Deferred).
- A fork's history says it assigned tasks that belong to the conversation it was forked from; its start line says so, and their outcomes go to that conversation.
- Delivery is at least once.
- The human completes from a terminal, a page or the app, not from a session's own shell escape, which carries the session's id.
- The session manager's ledger reads the store when the whole picture is built; until then it lists a task only where a session wrote about it.
- A session without function hooks is told by its start line and acknowledges by key, never by an envelope; a session MAWS runs is told by MAWS from B3 on, and until then reads and acknowledges the same way.
- A wake needs what any message's wake needs: a machine and a project a notice can be written in, and a thread sminos will start. Where it cannot be had the outcome waits for the next resume, and the task says which.

### Delegated unknowns

| id | question | who answers | what decides |
|---|---|---|---|
| U1 | With the hook's changed command: what does the permission dialog show; which allow rules still match (a prefix rule for the verb; a rule that names arguments); what does a classic `PreToolUse` check receive; does a secret's handle in the same command still restore | B1, M5 (one live check, each case observed and none asserted beforehand) | A prefix rule that stops matching moves the flag's place before M5 lands; the rest is written beside D2 as found |
| U2 | sminos's own suite shows an addressed notice waking a thread its human opened. Not shown: a notice alone waking a spawned seat; a machine cut over to the reach and words gates, where a notice can be gated or wait behind another event | B1, M4 (one live check) | A seat that a notice alone does not wake, or a gate that holds a `tasks` notice, goes to whoever holds sminos before M4 lands; the wake's cause is not replaced on the strength of a gated delivery |
| U3 | In a thread woken in the background: are the mods loaded, does the wake's own prompt raise `prompt.submit` (so the envelope rides it), and is the plugin's idle submit accepted there | B1, M5 (the same live check) | Whatever route opens is the route. If none opens in a woken thread, R9 is not met there: the milestone stops and it goes back to the owner, the notice's own text being all such a thread then gets |
| U4 | How often do agents file an act as a question, or a decision as a task; does a blocked agent mark `blocking` and go on; does a blocked subagent return to its caller with the id; does any agent complete a task itself | B5 | B5's thresholds, set in its ledger before its runs |
| U5 | Another `task` on the PATH (Taskwarrior, go-task) | the ticket board's M1 | its answer binds both destinations |

## Parent-Level Acceptance

The unit closes when this holds on one Mac with the released plugins, each line seen and not inferred. A1 to A9 need B1 and B1a; A10 to A12 add B2, B3 and B4 as each lands; A13 is B5's.

1. **Assign and go on.** In a terminal session, one Bash call runs `task assign-human --class blocking --title "Log in to the console" …` and `task assign-human --class needed --due <date> --title "Rotate the key" …`. Both print an id; each returns within a second, measured; the session's turn continues.
2. **The board lists both**, from a terminal that is no session: `sminos task list` prints the blocking one first, each with its project, its asker's alias and state, and the due date; the session's own terminal shows `2 tasks for the human (1 blocking) · …` above the prompt, and the machine raised one notification, for the blocking task.
3. **The terminal is closed.** Within two passes of the daemon, `sminos task list` shows the blocking task's asker as stopped and to be woken.
4. **Done, with a note, wakes it.** `sminos task done t1 --note "logged in with account B"` prints a verdict whose `told` is `wake-asked`. The session starts in the background; `sminos task show t1 --json` shows one wake attempt answered `woken` and then the outcome landed; the session's conversation holds one `[tasks v1]` envelope naming `t1`, done, and the note. The project's log holds one notice and not the note.
5. **A check that fails reopens.** In that session `task reopen t1 --comment "the console still asks for a login"`; `sminos task list` shows `t1` open again, Updated, at revision 2. `sminos task done t1` (revision 1) is refused as stale, saying the current revision.
6. **A cleared session's task reaches its successor.** A second session assigns a needed task, is cleared, and its successor works in the same terminal. `sminos task show` names the successor as the task's target. `sminos task done` of that task: the successor's conversation receives the envelope, saying the task was assigned by the conversation it replaced; the cleared conversation is not started; a third session that takes the cleared one's old alias receives nothing.
7. **A subagent's task.** A subagent assigns a task; `sminos task show` names the subagent. Completed while the subagent runs, the envelope is in the subagent's conversation and absent from the main one; completed after it ended, in the main conversation, naming the subagent.
8. **Both envelopes at once.** In a session that has the sheet, with a sheet answer and a task outcome both ready while the model's turn runs, the next tool result carries two context entries, the sheet's envelope first and the tasks' after it, each landing its own keys in its own record; with both ready while the session is idle, two prompts follow one another, the sheet's first, and neither text holds the other's envelope. The sheet's suites pass unchanged.
9. **Three days.** With the period set short (`SMINOS_THREAD_END_AFTER`), a thread stopped past it with an open blocking task is not ended and `daemon.log` says why once; its task declined without a wake, the next ending pass ends it. A thread stopped past the period with only a needed task is ended as today, its task stays on the board, and its later completion answers `told: ended` with one line in the project's log; opened again by its human, it receives that outcome's envelope.
10. **The local page** (B2): the board at the page server's origin, paired as the sheet's page is, lists what `sminos task list` lists, updates within two seconds of a change, and a card's Done with a note produces A4's effect.
11. **The MAWS app** (B3): its board lists the same tasks; a task assigned by a MAWS-run session, completed there, reaches that session by MAWS's steer, and the store shows the outcome landed by a `delivered` act.
12. **Another machine** (B4): a task on a second machine is listed and completed from the phone, and applied once when the act is sent twice.
13. **Behaviour** (B5): its four scenarios pass their thresholds with the wording that ships.

## Children

### B1: The store, the door, the envelope and its delivery, the verbs — plan (this repository)

- **Purpose:** Everything a terminal user needs for the unit's promise: the store and its published set, the door and the command line surface, the agents' verbs in sminos and in the `task` plugin, the subagent's attribution, the routes shared with the sheet, the task envelope and its delivery with the wake, the terminal's line, and what agents are told.
- **Acceptance:** A1 to A8 on a Mac, by the commands its execution document quotes; the published set (X1) at version 1 with its digest; the sheet's suites unchanged (D6, rule 9).
- **Edges:** blocked-by: `external:` the owner's read of this document. Its M2 is blocked-by `external:` the ticket board's M1 (the `task` plugin's first release). Its M3 is blocked-by `external:` the sheet's holder agreeing D6, and `external:` the sheet's C5 M1 pull request on `main`. Its M6 is blocked-by B5. blocks: B1a (by its M1), B2 and B3 (by its gate G1, the set published), B4.
- **Contracts:** owner of X1, X2, X3, X4's terminal form, X6, X7; reader of X5; ships X8.
- **Design inheritance:** D1 to D6, D8 (the command line, the terminal, the notice to the human), D9; U1, U2, U3.
- **Required:** required.
- **Status:** not-dispatched (waiting-external: the owner's read). Its execution document is `docs/doperpowers/plans/2026-11-27-task-board-b1.md`.

### B1a: The three-day exemption — brief (this repository; whoever holds sminos)

- **Purpose:** A blocking task completed after three days still finds a thread to wake (R10).
- **Acceptance:** A9. In `sminos/tests/test_threads_ended.py`'s form: a thread stopped past the period that is the target of an open blocking task is not ended and is said once; with the task closed and no wake-asked outcome younger than the period, it is ended; with such an outcome, not ended until the period has passed since the act; with the store unreadable, or its lock not had, not ended; a thread with only needed or optional tasks is ended as today; a cleared thread whose successor lives is ended as today while the successor is kept; and an act that asks for a wake, started while the end holds the store's lock, answers `ended` and one started before it keeps the thread.
- **Edges:** blocked-by: B1's M1 (the store and X3's predicate). blocks: nothing.
- **Contracts:** consumer of X3.
- **Design inheritance:** D7, binding, its lock order included. Advisory: the predicate is one function of the tasks' module over the store and `target_of` (B1's), called with no lock from `sweep_threads`'s test of what is due and under the store's lock around `end_by_rule`'s transition; the line in `daemon.log` follows `holding`'s form.
- **Required:** required.
- **Status:** not-dispatched (blocked-by B1's M1). One pull request, sminos's version raised, reviewed at the medium rung.

### B2: The board on the local page — plan (MAWS)

- **Purpose:** The board in a browser beside the terminal: `mawsd`'s page server carries it as a page of its own, with its model and components, so a terminal user completes a task without typing a command.
- **Acceptance:** A10. Every refusal of the page's four rules holds for the board's routes as for the sheet's. A card renders a task's Markdown under the link policy and shows a link's host. A done or a decline names the revision the card showed, and a stale verdict is shown on the card with the new text. The card shows the asker's state, read again while it is open (a session that stops while the card shows shows as stopped within five seconds, with no task written), and offers the wake choice for a stopped asker. An act sent twice under one key is applied once. The page's acts are applied when `mawsd` was started from inside a session. The registration (X5) exists while the server runs.
- **Edges:** blocked-by: B1.G1; `external:` the sheet's C4 (the page server, its pairing and four rules) and the sheet's C3 first landing (the components' ground). blocks: B4.
- **Contracts:** consumer of X1, X2, X3; writer of X5.
- **Design inheritance:** D4, D8, D9. Advisory: the page draws from `sminos task list --json` and `show --json`, which carry each asker's state as computed then, and not from the store's file, which does not hold it; it reads again when the file's `seq` moves and on its own interval; it writes only through the door.
- **Required:** required.
- **Status:** not-dispatched (blocked-by B1.G1). Its execution document is MAWS's.

### B3: The MAWS app's board, and sessions MAWS runs — plan (MAWS)

- **Purpose:** The board as a native place in the app, and delivery for the sessions sminos does not deliver to.
- **Acceptance:** A11. The app's board lists what the store holds and acts through the door. An outcome owed to the main conversation of a MAWS-run session is steered to it in the envelope's steer form (the same block), whether or not that launch took the sheet, and acknowledged by a `delivered` act only when MAWS's journal shows the steer reached the model; an outcome still a subagent's is never steered. A session whose process is gone is brought up for an outcome only when its act asked for a wake (R5), which is narrower than the sheet's rule for an answer. How a blocking task marks its session in the app is settled with the owner on drawn frames before it is built.
- **Edges:** blocked-by: B1.G1; `external:` the sheet's C5 (the steer's form and the deliverer it reuses). blocks: B4.
- **Contracts:** consumer of X1, X2, X3; owner of X4's steer form.
- **Design inheritance:** D5 (who delivers; the subagent's ownership), D8. Advisory: `sminos task owed --session <id>` answers `runner: maws`, no main envelope, and each owed outcome's fields with its recipient; the steer's text is MAWS's to compose from them under the sheet's rule for a steer (no text a model wrote: a task's id, the outcome's word, the human's text as a JSON string), so a title stays out of it. The sheet's C5 steer is written for a launch that took the sheet; a launch that did not is this child's to add.
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
- **Acceptance:** With the sheet's eval harness (`tests/output-styles/`, C1's), a stand-in `task` that records its calls, and the skill not preloaded (only the start guide's line and the command's help in context), four scenarios meet thresholds B5's ledger sets before its first run: a login wall, met by a subagent, with a door that records its calls (a blocking task is assigned; the subagent returns to its caller with the task's id; the agent goes on with other work or stops cleanly, does not poll, and never calls the door); a decision the agent is blocked on (a question, not a task); a completion whose check fails (the agent reopens with a comment); a long job with many small wants (the board is not flooded: needs are batched or not filed). Its result is the wording of X8, and one sentence for the question tool's description with its evidence, handed to the sheet's holder.
- **Edges:** blocked-by: `external:` the owner's read (the verbs' names, X6). blocks: B1's M6.
- **Contracts:** owner of X8; consumer of X6.
- **Design inheritance:** D1, D2 ("What agents are told"); U4.
- **Required:** required.
- **Status:** not-dispatched (dispatchable after the owner's read; it needs no built store).

## Cross-Child Contracts

- **X1 — The published set.** `sminos/types/tasks/`: schemas for `state.json`, an act's line and its verdict, `list --json`, `show --json`, `owed`'s answer and the `<task-delivery>` block; envelope examples, each with the store and the inputs it was composed from (the session, its runner, the targets as resolved, the running subagents, the time zone); fixtures, one step each (`before/`, the command, `after/`, the verdict); a manifest with a digest. Written by a generator by hand from this document, never by the commands; `version` 1. Owner B1 (its gate G1 publishes it whole, `owed`'s answer included); B2, B3 and B4 pin it by digest. A change after G1 is a ruling of this document's writer and a new version.
- **X2 — The door.** `sminos task act`, D4's line and verdict; exits 0 when every line was answered, 2 for a line that is not the schema's (nothing applied), 3 for a caller that is a session, 75 for the lock not had in 10 s, 1 for a store it cannot write. Applied once by `key`, a UUID; a key reused for another line is refused. A surface runs it with `CLAUDE_CODE_SESSION_ID` removed. Owner B1; the only writer B2, B3 and B4 have.
- **X3 — The reader.** `sminos task list --json` and `show --json`: the model of X1, each task with its target and that target's state as computed at the read, each outcome with its recipient and its wake attempts. Two signals say when to read again: the store's `seq` for what was written, and the reader's own interval (five seconds while a board shows) for what changes without a write: a session stopping, a thread ending, a held wake freed. For D7: a task's state, class and target; an outcome's `wake`, `at` and `landed`. Owner B1; consumers B1a, B2, B3, B4, and later the session manager.
- **X4 — The envelope.** The terminal form is B1's (D5); the steer form is B3's, with the same block. `owed` says who delivers (`runner`) and gives a deliverer the outcomes' fields. `delivered` through the door is how a deliverer other than this plugin says a main-conversation outcome reached the model; a subagent's outcome is this plugin's mod's until it is rerouted.
- **X5 — The board's address.** A surface that shows the board registers under `$SMINOS_HOME/tasks/surfaces/<name>.json` with the fields of the sheet's surface schema (`v`, `name`, `url`, `reach`, `pid`, `heartbeatAt`), where `url` is the board's own complete address and not the origin it shares with the sheet's page. It is alive while its heartbeat is at most 30 s old and its pid runs, as the command judges it; the terminal's line shows what `owed` answers. Writer B2; reader B1.
- **X6 — The agents' verbs.** D2's names, flags and exits, in `task` and in `sminos task`. Owner B1. The three dispatch branches in the `task` plugin (`show` and `comment` by the id's form, `list --human`), taken before the ticket board's own preflight, and the sentence of the ticket board's D4 they replace ("with those names unused") go to the ticket board's writer before B1's M2.
- **X7 — The wake's notice.** The program's name `tasks`, the two texts of D5 (the wake's, the ended thread's), and the identity each is written once under. Owner B1; a reader of project logs may recognize them.
- **X8 — What agents are told.** The skill's body, the start guide's line, and the proposed sentence for the question tool's description. Owner B5; B1's M6 ships what B5 passed.

## Ordering & Dependency Map

    the owner's read ─┬─> B5 ───────────────────────────────┐
                      └─> B1.M1 (G1) ─┬─> B1a               │
                                      ├─> B1.M2  (also: the task plugin's first release)
                                      ├─> B1.M4 ─┐          │
       holder agrees D6, C5.M1 on main ─> B1.M3 ─┴─> B1.M5 ─┴─> B1.M6
                                      ├─> B2 (also: the sheet's C4, C3) ─┐
                                      └─> B3 (also: the sheet's C5) ─────┴─> B4 (also: the sheet's C6)

B1's M1 waits only on the owner. After it, four things run side by side: B1a; M2 once the `task` plugin exists; M4 (what is owed and the wake, in the command); and M3 once the sheet's holder has agreed and C5's M1 is on `main`. M5 (the session's side, the subagent's attribution with it) needs M3 and M4 and nothing of the `task` plugin. M6 ships the words B5 passed. A terminal user has a working board from M1, read and acknowledged by command; `task`'s verbs from M2; the push from M5. Until M5 lands the door says of every act that the asker will read it (`next-resume`), and promises no wake. MAWS's children start from G1 and their own sheet children.

## Verification

- **This document**: one `doperpowers:adversarial-reviewer` review of the design and one of B1's execution document, in one round; then one review of the repair's diff. Then the owner's read.
- **B1**: its execution document names its own; in short, M3's pull request (the extraction) and the pull request that holds M4 and M5 (delivery) are reviewed at the *high* rung, since a mistake there loses or doubles a delivery in the sheet as well; the rest at *medium*. The sheet's holder reads M3's pull request.
- **B1a**: the medium rung.
- **B2, B3, B4**: MAWS's, by their own documents; B2's routes are served by the sheet's page server, whose serving code the sheet's composite reviews at its high rung.
- **Recomposition**: Parent-Level Acceptance run as written on one Mac, by the session that holds this document; a scale review, since B1 and B1a touch one daemon and B1 touches the sheet's module.

## Risks & Mitigations

- **The extraction regresses the sheet.** The sheet's delivery is its most intricate code and is not this unit's. Mitigation: D6's rule 9 (its suites unchanged and the live check), a pull request of its own that holds nothing else, the holder's read, and the order after C5's M1.
- **The holder declines the extraction.** Then R9 cannot be met by shared routes. The fallback this document does not choose by itself: the tasks' outcomes ride the notice (the alternative R9 set aside) until the holder and the owner settle it. It goes back to the owner.
- **A wake that sminos never performs.** The wake rests on sminos's notice, which its own suite shows for a thread its human opened and nothing shows for a seat or behind the gates (U2). Mitigation: U2 is checked live in M4, before the session's side is built on it; the door never says a wake happened, only that one was asked, and the task shows each attempt's answer.
- **A woken thread that no route reaches.** If U3 finds none, the envelope cannot reach a woken thread and R9 is not met there. It goes back to the owner; nothing is shipped that calls the notice a delivery.
- **The board floods.** An agent that files every want as a task makes the board useless. Mitigation: B5's fourth scenario gates the wording; the store's cap of 500 open tasks is the backstop.
- **A changed command surprises the person.** The hook adds text to a command the model wrote. Mitigation: the flag reads plainly, goes only on the two assigning commands, and U1's live check looks at the dialog.

## For the owner's read

What this document decides beyond the owner's words, with the choice taken; each stands unless the owner says otherwise.

- **O1. The verbs' names** (D2). `task assign-human` creates; `task show t7` and `task comment t7` are the ticket verbs given a task's id; `task list --human`; `task revise`, `withdraw`, `reopen`. Recommended as written. The other way: a `-human` form of every verb.
- **O2. What starts a turn** (D5). In an idle running session a done, a comment and a decline of a blocking task start a turn; a decline of a task that is not blocking does not (the approved design's rule). For a stopped thread a comment follows the same default as a done: a blocking task's asks for a wake, any other's waits, and the human's switch overrides either way, for any act. Recommended: a comment is the human's only way to ask the asker something, and an idle session that is not told sits. The other way: a comment never starts a turn or a wake by itself.
- **O3. The three-day exemption also covers a wake that is still being tried** (D7): a thread is kept while an outcome that asked for a wake is owed to it and its act is younger than three days. Recommended: without it, completing a blocking task on the fourth day can end the thread before a failed wake is retried. The other way: R10's words alone (an open blocking task), accepting that edge.
- **O4. The door refuses a session by its environment**, which an agent could remove (D4, D9). Recommended: as a guard against mistakes it costs nothing; a confirmation typed at a terminal is the only stronger check sminos has, and a page has no terminal. The other way: a typed confirmation on the command line surface for `done` and `decline`.
- **O5. `devcloud vm down` naming a deleted machine's open tasks is deferred** (Deferred). Recommended: register it as a ticket beside B4, when tasks on other machines become visible at all. The other way: build it in B1.
- **O6. Only evidence acknowledges** (D5): a landed envelope, a deliverer's `delivered`, or the asker's own `sminos task ack` by key. Reading a task does not. Recommended: a command run is not a model that read it, and a wrongly acknowledged outcome is lost for good, while one acknowledged late is only named again at the next start. The other way: reading a task counts, which is simpler for a session without function hooks and can silently drop the human's note.
- **O7. A cleared conversation's successor answers for its tasks** (D2, D5): it receives the outcome with the human's note, as the approved design says, and it may also revise, withdraw and reopen them. The successor is the session sminos witnessed taking the cleared one's place; the approved design said the session that holds the alias the cleared one released, and an alias can pass to an unrelated session, which would then be shown the note. Recommended: the conversation that receives a failed check is the one that must be able to reopen. The other way: the successor is told and only the conversation that assigned may change the task, which after a `/clear` is nobody.
- **O8. An undelivered outcome outlives the 30 days** (D3): a closed task leaves the list of what was closed after 30 days and is kept, unseen, until its outcome is delivered or acknowledged. Recommended: R1 promises the completion comes back, and a needed task completed without a wake may wait long for its session. The other way: everything expires at 30 days, said on the card.
- **O9. At most three wake attempts an outcome** (D5), one for each time the thread stops again without having read it. Recommended: enough for a process that died once or twice, and a bound on a thread that dies every time it is started. The other way: one attempt only.

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
