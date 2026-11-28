# Tasks for the human: the Task Board (2026-11-27)

> **Parent:** root — the project's standing purpose (`CLAUDE.md`: a software-development methodology for coding agents, with sminos as the family that lets many sessions work for one owner). **Consumes:** sminos's threads, wake, delivery and machine notices (`docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, closed, read and not amended; `sminos/skills/sminos/scripts/`); the ticket board's `task` plugin (`docs/doperpowers/specs/2026-11-24-ticket-board-design.md`; its M1 to M3, the plugin's first release, merged in pull request #639). The question sheet (MAWS's composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`) is this unit's sibling and model for its surfaces; nothing of its code is used or changed. Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact opens by citing this document (path, child id, parent pin). B1 and B1a are built in this repository; B2, B3 and B4 are MAWS's, and their execution documents are written on MAWS's side by MAWS's holders.

## Purpose

The owner supervises many agent sessions. A session often needs the human to do something in the world: log in, grant a permission, rotate a key, buy, review and merge. Today that is a sentence in a message: nothing lists what the human was asked to do, what each item holds up, or tells the session when it is done. The owner named this as a pain ("나를 기다리는 일이 안 보임", 2026-11-20T05:06Z) and asked for a human to-do board triaged as blocking, must be done at some point, optional, with low latency and the result returned to the asking session.

**After this change.** An agent, or a subagent, assigns a task to the human in one command and keeps working. The human sees every open task of every session on the machine in one list, the blocking ones first, reads a task like a ticket (body, comments), comments on it, and completes or declines it. Whoever asked is told at once, with nobody relaying: a notice from the board arrives in the asker's conversation naming the task and what the human did, and the asker reads the human's note with one command; and whatever became of that notice, the asker's next start names what the human did. A task stays on the board until the human closes it, whatever became of the session that made it.

**How to see it working.** The scene in Parent-Level Acceptance: two tasks assigned in one command, the terminal closed, the blocking one completed from the board, the session back in the background with the board's notice as its first message.

**What it must not be.** Not the agents' backlog (R6). Not a question: a decision or an answer goes on the question sheet (D1). Not a blocking call: assigning a task never stops the agent. Not a record of the agents' progress. Not the human's own to-do app: only sessions add tasks. Not a second delivery system: sminos already delivers, wakes, holds and explains, and the board hands it one message an act (D5).

## Progress

- [x] (2026-11-27T22:20Z) The owner approved the design ("승인한다, 스펙으로"), with the completion returned as an envelope the question sheet's way ("질문 시트처럼 봉투로").
- [x] (2026-11-27) This document and B1's execution document written, reviewed twice by `doperpowers:adversarial-reviewer` (the design and B1's execution; then the repair), each round folded.
- [x] (2026-11-27T23:39Z) The owner approved the spec ("승인한다, 구현 시작"), its open decisions as recommended, two answered in words (R12, R13). B1's M1 is built first.
- [x] (2026-11-27T23:41Z) The owner changed how a completion returns, having read what the envelope cost in this document ("sminos inbox로 바꾼다 (Recommended)", R9). D5 is the notice; the extraction of the sheet's routes and everything that served the envelope are gone from the design and from B1.
- [x] (2026-11-27) One `doperpowers:adversarial-reviewer` round on the rewritten delivery and on B1's re-cut execution, folded. Review stops here; what it changed since the owner's ruling is "Since the approval".
- [ ] Children: the Tracking Map.

## Terms

- **Task**: one thing a session asks the human to do in the world. It is the human's to-do; the session that asked is its return address.
- **The board**: the list of this machine's tasks, as any surface draws it. "The board" in this document is never the agents' ticket board (GitHub issues, the `task` plugin's first destination) and never the engine's in-session to-do tools.
- **Asker**: who is told of a task's outcome: the thread that assigned it and, when a subagent assigned it, that subagent.
- **Thread**: sminos's record of one line of work on a machine (`sminos/skills/sminos/scripts/sminos_threads.py`): a spawned seat, or a session its human opened. It has a current session, is *stopped* when no process holds that session, and is *ended* by a retire or by the three-day rule. A `/clear` and a fork each begin a new thread; a resume continues one.
- **Successor**: the session a `/clear` began in the place of the one it left, as sminos witnessed it at the clear (`cleared_witness`).
- **Target**: the session a task's outcomes go to now: the asker's, or its successor (D5).
- **Outcome**: one act of the human on a task (done, declined, a comment) as the asker is to be told of it.
- **Notice**: a message in a project's log from a program of the machine, not from a session or a person (`sminos say --notice <program>`, contract X8 of the channels-and-threads design); devcloud's hosts use it today. sminos delivers an addressed one as it delivers any message.
- **The start line**: what a session is shown of its tasks when it starts, from the store, by a SessionStart shell hook. An outcome is **shown** once a start line has printed it to its target.
- **The door**: the one command through which every surface performs the human's acts (`sminos task act`).
- **Surface**: anything that shows the board and takes the human's acts: the command line, the local page, the MAWS app, the phone.
- **Wake**: sminos starting a stopped thread in the background (`sminos.wake`, `claude --bg --resume`), which an addressed message causes.
- **Mod**: a plugin's function hooks (`sminos/hooks/mods/`), loaded only where the engine's function hooks are enabled. A shell hook (`sminos/hooks/*.sh`) runs everywhere.
- **MAWS-run session**: a session whose controller is the MAWS app (sminos's lane B, `sminos_records.lane_of`). sminos never wakes it. Lane is the test, not the absence of a thread: a session MAWS adopted keeps its thread record, and a session with no thread need not be MAWS's.

## What the owner ruled

Each row is the owner's own wording, with the time the answer reached the design session (UTC).

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
| R9 | The completion comes back through sminos's inbox: a notice from the board, delivered as sminos delivers any message | "sminos inbox로 바꾼다 (Recommended)" (2026-11-27T23:41Z) |
| R10 | A thread stopped with a blocking task open is not ended by the three-day rule | "뺀다 (Recommended)" (2026-11-27T22:20Z) |
| R11 | The spec is approved and building starts, its open decisions as recommended | "승인한다, 구현 시작" (2026-11-27T23:39Z) |
| R12 | In an idle session a done, a comment and a decline of a blocking task start the agent's turn | "완료, 댓글, blocking 거절 (Recommended)" (2026-11-27T23:39Z) |
| R13 | After a `/clear`, the conversation that follows becomes the task's asker | "된다 (Recommended)" (2026-11-27T23:39Z) |
| R14 | What agents are given about the board describes what it is and what its verbs do, and leaves when and how to use them to the agent: direction at a high level, guidance only for failure modes observed or explicitly expected, no forced process | "when giving agent with tool, skills, whatever, we need to keep it lean. Avoid explaining how agents should use the tool, but instead, just describe to them what the tool does and let it figure out and judge how to use it. … At most we only need to provide high-level direction, add guidance to observed or explicitly expected failure modes … Nothing should be forced, and even doctrines like writing spec and registering tickets should be one existing conventions, not a forced process … so when we give agent task tool we have no forced process, just explain what the tool does and let it figure out what to do with it." (2026-11-27) |

Events and subscriptions are out of this scope ("이번에는 뺀다 (Recommended)", 2026-11-24T12:17Z). The triage of blocking, must be done at some point, optional is the owner's first brief (2026-11-19); it is a deliberate difference from the sheet, where no question marks a session as stopped on the human.

**What the approval settled** (R11), each as this document recommended it: the verbs' names (D2); a comment following a done's wake default for a stopped thread (D5); the three-day exemption also covering a wake still being tried (D7); the door refusing a session by its environment (D4); `devcloud vm down` naming a deleted machine's tasks deferred (Deferred); an outcome the asker has not been shown outliving the 30 days (D3). R12 and R13 answered two of them in words. Two of the decisions approved then concerned the envelope's receipts and its wake attempts, and left with it (R9).

**Since the approval**, decided in this document and not yet put to the owner; each stands unless the owner says otherwise.

- **Every act is named at the asker's next start, whether or not a notice was sent** (D5). The ruling's own form was that only an act with no notice is printed then. Review found that sminos's record cannot say a notice was read, and can settle one with nothing pushed; knowing more would take receipts of the board's own. The other way: only acts with no notice are printed, and a notice that went nowhere is lost.
- **An act that did not ask for a wake sends its notice for the live alone** (D5), so a session that stops before sminos pushes it is not started for it.
- **The notice names no alias** (D5), though one was allowed: the clause for a successor and for a subagent's thread says what is needed without one, and the ended line goes to a log others read.
- **A sending a dead door left is finished late, not retried at once** (D5): by the next call of the door on the machine or, within the hour, by the daemon. A notice once written is retried by sminos alone.
- **The three-day exemption's second half** (D7) is an act that asked for a wake, not yet shown at a start and younger than three days, from the moment it is applied.

## Grounding Baseline

Read at this repository's `main` (`40b79a7d1`) and `ticket-board-spec` (`143552115`). Each line is a fact the design rests on.

1. **A notice is delivered as any addressed message is, and is nobody's words.** `sminos say --notice <program>` appends a `human` event marked `notice` under the machine's own writer; it is refused inside a session (`cmd_say`). An event's `to` names recipients by session id (`_addressees`). `push_live`'s routes send a notice to the session's inbox as a peer's frame from `<program>@<machine>`, never through the bridge or the supervisor, whatever the endpoint's verdict (`sminos_control._routes`; `sminos/tests/test_notice.py`). What a member is told of an addressed message (`sminos/skills/sminos/SKILL.md`): an idle one starts a turn, a busy one reads it at its next tool round, a stopped one is woken to read it, or held where its machine does not wake it.
2. **One delivery operation, with a record.** `deliver_next`, under `delivered/<session>.lock`, pushes each writer's owed events in order and settles each; the record keeps, per writer, the settled prefix, what is pending and its attempts, and what is held (`delivered_entries`). A failure stays pending and is retried by the daemon's passes, given up after `DELIVERY_ATTEMPTS` (60). A sender's own call delivers at once (`deliver_say`), and the daemon's tick delivers what is owed (`deliver_owed`).
3. **A stopped thread is woken by the push, or held; an event for the live alone wakes nothing.** An event marked for the live alone (the mark an `@all` carries) reaches only a recipient whose process runs and settles `recorded` for any other. For any other addressed event to a session no process holds, at whatever later moment it comes to be pushed (after a wait for its writer's head, a gate's verdict, a failed push), `wake_member` wakes its thread (`sminos/tests/test_notice.py` shows an addressed notice doing so, once, its frame carrying the wake's line); a thread this machine does not wake is held with a reason (`held:<why>`: its mode asks for approval, its transcript or directory is gone, a wake failed), the event owed and tried again; sminos retries a failed wake on a schedule of its own. Whether this machine would wake a thread is `wake_here`; `wake_of` and `why_of` are what other machines are told.
4. **What sminos does not deliver.** An ended thread, a retired member and a lane B session whose process is gone settle `recorded`: nothing is pushed and nothing started (`wake_member`: `ended`, `gone`, `lane`). `sminos say --notice` tagged to an ended thread or to no member exits 4 with nothing appended. A recipient must be a member of the project the notice is written in.
5. **"Delivered" means the frame was written, and "settled" less than that.** For a peer's frame sminos settles when the inbox took it; the engine may still hold it for its user's approval (a session that bypasses permission prompts holds a peer's message that asserts no permission mode, as sminos's frame does) or drop it by its rate limit, unreported (`sminos_outcomes.py`). An event also settles with nothing pushed: when its thread ends or retires while it is held, when a gate refuses it, when it is given up. A settled entry keeps no word of which it was (`settled_already`). So sminos's record says an event is no longer owed, never that an agent read it. That an idle member starts a turn and a busy one reads at its next tool round is checked live for a peer's message (`sminos/tests/mods/live-peer-check.py`). A session MAWS runs settles later and more strictly: its process is recorded `gate`, the frame goes to its inbox under a receipt, and it is settled when the session's observer admits a model request that holds it (`sminos_holder_deliveries.py`).
6. **A message to a running subagent exists as a bridge op.** `tell` (`bridge-agent-ops.tsx`, `tellAgent`) sends text into a running subagent's conversation through `$.session.send`, opening with a line that says it is from the person and not the coordinator; it refuses an agent that ended or is unknown, and an observer (a MAWS-run session's bridge) refuses every control op. No command of sminos's posts it today but the desk's RPC; a command reaches a session's bridge socket as `sminos_sheet.nudge` does (`sminos_control.post_command`).
7. **Model-written text in a user-role message has been read as the person's consent.** MAWS's ticket 711: the engine's auto-mode classifier took text an agent wrote, arriving in a prompt, for the human's approval. A notice arrives in an idle session as a prompt.
8. **A `/clear` does not continue a thread.** The session left stays the current session of its own thread, which stops and later ends; the new session is a thread of its own. The clear is witnessed with both sessions in hand (`cleared_witness`, read by the record hook's release), but the record keeps only the released alias and the time: nothing stored points from the left thread to the new session, the new session need not be in the left one's project, and the alias can later be another session's. A fork is a thread of its own.
9. **The three-day rule and its one exemption.** `sweep_threads` (`sminos_daemon.py`) finds a thread due when its `stopped` mark is older than `thread_end_after()` (three days); `end_due` leaves it stopped while devcloud's census says it owns a host, saying so once in `daemon.log` (`holding`); `end_stopped` and `sminos.end_by_rule`'s guard decide again under the record's lock. An ended thread returns only when a process holds its session again.
10. **A subagent's shell cannot say which subagent it is.** It carries its parent's `CLAUDE_CODE_SESSION_ID` and no agent id. A `tool.call` hook is told `e.agentId` (absent on the main loop; a subagent's is `a` and sixteen hex digits, a teammate's `<name>@<team>`), may hand a changed `command` to `next`, and the permission check judges the changed bytes (`devcloud/hooks/mods/secrets.tsx`; `hooks/mods/README.md`: "the permission check sees the restored bytes").
11. **No sminos mod rewrites a command today.** `backticks.tsx` has a real shell lexer and uses it only to refuse a call; it keeps a word's decoded text, not where the word stands in the command. The bridge posts the input its `tool.call` hook received and offers a remote answerer the engine's permission suggestions only when the engine's input is exactly that (`bridge-requests.tsx`, `isSeen`); doperpowers' appeal keys a pass on the input as it saw it. A rewrite made beneath them loses both for that call, as a restored secret's handle already does. sminos's module is seated outside every user-tier plugin's (`prependPlugins`), and within it registrations nest in order, the first outermost.
12. **A caller inside a session is known by `CLAUDE_CODE_SESSION_ID`.** `sminos channel lead` and `say --notice` are refused when it is set. An agent can unset it; only a typed confirmation on `/dev/tty` is beyond one (`sminos_visibility.confirmed`), and a page has no terminal. A daemon started from a session's shell inherits the variable.
13. **The `task` plugin does not exist yet.** The ticket board's spec makes it (its M1, the plugin's first release): Python, standard library only, importing nothing of sminos, finding `sminos` through `TASK_SMINOS`, the PATH, then the marketplace clone, each call bounded at 30 s; exits 0 done, 1 failed, 2 usage, 3 refused by a rule; body from `--body-file`; reading verbs take `--json`. Its dispatch keeps the Task Board's verbs unused, and `task assign-human` exits 2 saying the Task Board is not built.
14. **The line above the prompt and the start guide have precedent.** The question sheet's band draws through `ui.render` for `AbovePrompt` (`sheet.tsx`, `registerSheetBand`); `sminos guide` (`guide_text`, run by the shell hook `smns-guide.sh`) joins lines, an optional one only when it has something to say; the hook exits before any Python on a machine that is not enrolled, and the text is empty for a session that is no member.

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
| `title`, `body` | one line (at most 200 characters); Markdown (at most 20,000), the task in the asker's words |
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

`--body-file -` reads standard input, so a body rides a heredoc; the ticket verbs' `--body-file F` is kept, since one CLI has one way to give a body. `assign-human` prints the id and the line the human will see (`t7 blocking "Log in to the console"`); every verb returns at once and prints what it touched. `show` and `comment` are also ticket verbs: the `task` plugin's dispatch sends them to the human's board when their first argument is whole `t[1-9][0-9]*`, and `list` when it carries `--human`, before anything of the ticket board is looked for (its configuration, `gh`): the human's board is the machine's and works outside any repository. `revise`, `withdraw` and `reopen` exist only for the human's board; given a ticket's number they exit 2. The alternative weighed: a `-human` form of every verb (seven names, nothing shared with the ticket dispatch). It lost because an agent would learn two vocabularies for the same acts while the id already says which board is meant; its cost is three branches in the ticket verbs' dispatch, which goes to the ticket board's writer (X5).

The verbs are a thin front over the store's commands in sminos (D3): each runs `sminos task <verb>` with the same arguments, passes its output and exit through, and where `sminos` is not found exits 1 saying that the human's board is kept by sminos and it is not installed. The store's commands are usable directly (`sminos task assign …`), which is what a session without the `task` plugin does and what B1 is tested through before the plugin exists. Every text the board itself writes for an agent (the notice, the start line) names `sminos task`, since the `task` plugin may not be installed where it is read.

**Who may change a task.** Any session comments on any task. `revise`, `withdraw` and `reopen` are the asker's: the session that is the task's target now (D5: the asker's thread's current session, or the successor a witnessed `/clear` gave it, R13), or the current session of the asker's thread; for a task with no thread, the asker's session itself and no other. Another session is refused, exit 3: a fork, a session that once filled the same seat, and a second session with no thread are all another session. Within a session any agent may change the session's tasks: a shell cannot tell them apart, and the subagent's attribution is a delivery hint, not an owner.

**Who asked.** The command learns the session from `CLAUDE_CODE_SESSION_ID` and its thread from sminos. It cannot learn which subagent ran it (baseline 10), so sminos's mod tells it: a `tool.call` hook on Bash, told `e.agentId`, finds each simple command that is `task assign-human` or `sminos task assign` and puts `--asker-agent <id> --asker-name <word>` directly after the verb. So the attribution is part of creation, and the person consents to the command as changed, which reads plainly. **[binding — the flag's names and its place are what the permission rules the owner writes will match]**

- The flag goes after the verb and not at the command's end, because a command can end in a heredoc, a comment or a list (`task … && echo ok`), and not before the command as a variable, because a leading assignment can stop an allow rule for the command from matching. The hook finds the command with `backticks.tsx`'s lexer, which must give it where the verb's word ends in the command's own bytes; the lexer keeps decoded words today, so it is taught to keep those positions for a literal command word and verb, and a command where it cannot (the verb reached through a quote's continuation, a variable or a substitution; a syntax it gives up on) is left unchanged. So is a call whose agent id is not whole `[A-Za-z0-9_.@-]{1,128}`. The asker is then the thread alone.
- The name is the agent's description or type as `$.agent.list()` gives it, reduced to `[A-Za-z0-9_.-]` (any other run a `-`, at most 64 characters), left out when nothing remains. It is shown to the human on the board and never put in a message to an agent (D5).
- The hook is sminos's, registered first in `sminos/hooks/mods/register.tsx`, so it is the module's outermost and what sminos's other hooks and the plugins seated inside sminos receive is the command as it will run. What each observer then sees: the bridge posts the command with the flag (it reports what ran, not what the model first wrote); the bridge's `isSeen` and the appeal's pass hold for the call as they hold today, which is to say not when a secret's handle is restored beneath them; `to-human`, seated outside sminos, and the engine's own record of the call keep the model's command. In the `task` plugin the hook would sit in the user tier, beneath the bridge and the appeal and in no fixed order against devcloud's secrets guard.
- A permission rule or a classic `PreToolUse` check that depends on the arguments after the verb sees one more argument. U1 looks at what the engine does with each; no rule is promised to match.
- Where the mod is not loaded the asker is the thread alone. An agent that writes the flag itself is believed: it is a delivery hint.

**What agents are told.** In the plugin's skill (`task:human-tasks`), in one line of sminos's start guide, and in one sentence of the question tool's description (the sheet's holder's to place; B5 hands them the sentence with its evidence). They describe the board and what its verbs do, and leave when and how to use them to the agent (R14). The definitions they carry: D1's line between a task, an act only the human can do in the world, and a question; what `blocking`, `needed` and `optional` mean; that the human's acts reach the asker as a notice naming the task and what the human did, and are named again at its next start, and that the human's words are read with `sminos task show`; that "done" is the human's word about their step, and a task can be reopened; that the door refuses any agent session, so the human's acts are the human's alone. What an agent does after assigning a task, or on being told of an act, is its own judgment, and nothing in them prescribes it. The words are B5's to settle before they ship (X7).

### D3. The store

One store per machine, under the sminos home (`$SMINOS_HOME/tasks/`), holding every task assigned on that machine. It is not the sheet's record and shares no file with it. **[binding — one store a machine is what lets a task outlive its session (R4) and the board list across sessions]**

- **One file, replaced whole.** `tasks/state.json` holds every open task and every closed one still kept, each task's history (its comments and the human's acts, each with the store's `seq` at its step), the acts already applied by key, and the successors witnessed at a `/clear`; a change reads it, changes it and replaces it (a synced temporary file and `os.replace`) under an exclusive lock on `tasks/.lock`, waited for at most 10 s (exit 75 past that, as the sheet's door). A reader takes no lock: a replace is whole, so one read is a consistent state, and `seq` (+1 at each change) orders two reads. The alternative, a file a task, was weighed for write cost; it lost because every reader wants the list, and the store is small (at most 500 open tasks; an `assign` or a `reopen` that would make 501 is refused, exit 3, saying how many are open).
- **Every change is one step under the lock, made by the command that causes it**: an agent's verb, or a human's act arriving through the door. There is no inbox, no drain and no daemon in the path of a write. Whoever holds the store's lock takes no other lock of sminos's and appends to no log while holding it: the notice an act causes is written after the step that applied the act, with the lock let go.
- **The contract carries a version.** `state.json` holds `version` (1). A command built for an older version than the file's refuses to write (exit 1, saying which plugin to update), deciding on the file as it reads it under the lock, and still reads what it understands; a writer keeps every field it does not know, on the store and on each task, since several plugin versions run on one machine at once. What another repository reads is the published set, `sminos/types/tasks/` (X1), made as the sheet's is: written by hand by a generator from this document's shapes, never by the code it holds to account.
- **Lifetime.** A `/clear`, a fork, a stop or an end of the asker removes nothing (R4). An open task leaves the board only by the human's done or decline or an agent's withdrawal. A closed task is kept 30 days, for reopening and for a read-only list of what was closed, and past that for as long as an outcome of it has not been shown to its asker at a start: the list of what was closed stops showing it, and the daemon's hourly duty removes it once it has. The history's limit never swallows a completion its asker was not shown.

### D4. What the human does, and the door

On a task: **comment** (it stays open), **done** with an optional note, **decline** with a reason. Every surface performs them through one command of sminos, the door, which applies the act at once and answers with its verdict. **[binding — one door is what makes every surface's act the same act, and is the only writer B2, B3 and B4 have]**

    sminos task act            # one JSON object a line on stdin, at most 50; one verdict a line on stdout

    {"v":1,"key":"<a UUID the surface mints for this act>","task":"t7","act":"done","revision":2,"text":"logged in with account B","wake":null}

- `act` is `done`, `decline`, `comment`, `seen` (the human opened the card: it clears the row's "Updated" up to the store's `seq` the card was drawn from, which the line names), or `shown` (a deliverer other than the start line says it told a session of a task's outcomes: the line names the task, the session that was told and the keys; MAWS, where its launch does not run sminos's start hook).
- A `done` or a `decline` names the revision the human read and is refused `stale` when the task was revised since, with the current revision, so the card can say so; a comment is never refused as stale. An act on a task no longer open answers `closed`; an unknown id, `unknown`.
- `wake` is the human's choice for a stopped asker (R5): `true`, `false`, or `null` for the default (D5).
- **An act is applied once.** A key is a UUID, so two surfaces never mint the same one. The door keeps every act's first verdict, whatever it was (`applied`, `stale`, `closed`, `unknown`), and a digest of its line, by its `key` for as long as the task is kept; the same line again answers the first verdict and changes nothing, and a different line under a key already used is refused (`key-reused`) and changes nothing. A surface that did not hear the verdict sends the same line again; an act tried again after a refusal (a `done` refused `stale`, made again at the current revision) is a new act under a new key, since the old key answers its first verdict for good.
- **The verdict is what the door decided, and does not change.** `{"v":1,"key":…,"task":"t7","verdict":"applied|stale|closed|unknown|refused","revision":2,"state":"done","outcome":"t7.3","told":"now|wake|next-start|ended|maws"}`: `told` is how the door, in the step that applied the act, decided the asker is to be told (D5); a refusal says why (`reason`). What then became of the telling is not the verdict's to say: the task shows what was sent and what sminos answered at that moment (`show --json`), which is a report of the sending and no proof of reading. A sending the door decided and did not finish is a state of its own beside the verdict, resolved by the next call of the door or by the daemon's hourly duty (D5).
- **The door refuses a caller that is a session** (`CLAUDE_CODE_SESSION_ID` set; exit 3): an agent does not complete the human's task. This guards a mistake, not an adversary (baseline 12); D9 says what is trusted. A surface that has authenticated its human runs the door with that variable removed from the child's environment, since a surface's daemon may have been started from a session's shell.

The command line is the first surface and goes through the door: `sminos task list`, `sminos task show t7`, `sminos task done t7@2 [--note "…"] [--wake|--no-wake]`, `sminos task decline t7@2 --reason "…"`, `sminos task comment t7 "…"`. The handle is the sheet's: `t7@2` names the revision read; a bare `t7` names revision 1.

### D5. Telling the asker (R9: sminos's inbox)

The asker is told twice over, by two things that do not depend on each other. **The notice** is the fast one: after the door applies a `done`, a `decline` or a `comment`, one notice from the board's program, `tasks`, is addressed to the target's session, and sminos's own delivery owns it from there. **The start line** is the sure one: at the target's next start, whatever became of any notice, the store names each act of the human the target has not been shown. **[binding — one message an act in sminos's hands, and one line at a start from the store, are the whole of the delivery: B3 and B4 build on them, and nothing here duplicates sminos's]**

    [tasks v1] The human marked t7 done, a task you assigned. Read it: sminos task show t7
    [tasks v1] The human declined t9, a task you assigned. Read it: sminos task show t9
    [tasks v1] The human commented on t4, a task you assigned. Read it: sminos task show t4

sminos delivers the notice as it delivers any addressed message (baseline 1 to 3): an idle session starts a turn with it, a busy one reads it at its next tool round, a stopped thread is woken or held with its reason and tried again. The board keeps no record of delivery and runs no route of its own: what sminos answered when the notice was sent is kept on the outcome for the card to show, as a report and not as evidence (baseline 5).

Why both. sminos's record cannot say an agent read a message, and can settle one with nothing pushed; to know more the board would need receipts of its own, which is the machinery R9 set aside. So the board does not try to know. Every outcome is printed once by a start line, and one that a notice already carried is then named a second time, at the session's next start or compaction, where the reminder costs a line and after a compaction is wanted.

**The notice carries nothing an agent wrote** (baseline 7): no title, no body, no agent's comment, no subagent's name, no alias. It carries the task's id, the outcome's word, and where it matters a subagent's id. The human's own note is not in it either: it stays on the machine, out of a log that syncs, and is read with `sminos task show`, which prints the task whole, the human's acts and their words in order. The start line keeps the same rule. **[binding — the notice is a prompt in an idle session, and its form is what B3 steers by too]**

- Where the asker differs from the reader the clause says so: `a task assigned by the conversation this one replaced at a /clear` for a successor; `a task your subagent a1b2c3d4e5f60718 assigned` when a subagent's outcome goes to its thread.

**Who it goes to: the target.** The store decides, from the task's asker, whom its outcomes go to now.

- **The asker's thread's current session**, unless a `/clear` gave it a successor.
- **A successor** (R13). At a `/clear` sminos witnesses the session left and the session begun (baseline 8); when the store exists, that pair is written into it before the left session's alias is released, by whichever of the new session's two start hooks runs first, and is bound to the successor's thread as soon as that thread has a record. The target is then the last link of that chain that is alive, running or stopped or only just begun, each link followed by its thread: where a successor went on in another session, that session; never a later process that merely reuses the successor's old id. The left thread is not woken while one exists. A successor that was retired or purged is not alive, and the outcome falls back to the one before it. A left session is the target again only when its human opened it after the clear (a process holds it that started after the pair was written). The link is the witnessed pair and never the alias, which another session can come to hold. A clear nobody witnessed (a seat's; a session that is no member) leaves the outcome with the conversation that was left, and so does a witnessed one whose pair neither writer could write (D9). **[binding — the same answer decides who is told, who may revise the task, and whom D7 keeps from ending]**
- **A session with no thread** when it assigned is its own asker by its session id, and only that session, whatever it later becomes: no successor is followed for it.
- **A subagent** (R2). When the task names a subagent, the target's process runs and the outcome is one that is sent now (below), and the target is the very session that assigned the task, the door first tells the subagent itself, through the bridge's message to a running agent (baseline 6), with the notice's text; the bridge's yes means the message was queued for it. A subagent's id means something only in the session that dispatched it, so a successor is never asked to tell one: it is sent the successor's notice. Where the bridge refuses, is not there, or does not answer, the outcome goes to the thread by the rules here, its clause naming the subagent by its id and claiming nothing about whether it still runs.

**When a notice is sent** (R5, R12). A notice to an idle session starts its turn, and a notice to a stopped thread wakes it; so one is sent only when the human's act should do that. The start line needs no such care and names every act.

| the target | a notice is sent | none is sent |
|---|---|---|
| a process holds it | a done; a comment; a decline of a blocking task; any act the human switched to wake | a decline of a task that is not blocking |
| stopped | the act asked for a wake: by default a blocking task's, by the human's switch any | every other |
| ended | never: one line goes to its project's log (below) | |
| MAWS-run, its process gone | never by sminos (baseline 4): MAWS brings the session up when the act asked for a wake (B3) | |
| no thread and no process; a member of no project | never | |

The human's choice is resolved when the act is applied (`wake`: the line's when given, else whether the task is blocking) and kept on the outcome. **The choice binds the notice for as long as it lives**: an act that did not ask for a wake sends its notice for the live alone (baseline 3), so that if the session stops before sminos comes to push it, however much later, nothing is started and the start line tells it. Only an act that asked for a wake sends a notice that can wake.

The card shows the target's state before the human acts: running; stopped and to be woken; stopped and held, with sminos's reason; ended; run by MAWS. It is this machine's own judgement (`wake_here`), read afresh when the card is drawn and again at intervals, since a session stops without the store changing (X3).

**The start line.** The SessionStart shell hook, from the store, whether or not the machine is enrolled and whether or not function hooks are on, names each act of the human on the target's tasks that no start line has shown it (`The human acted on tasks you assigned: marked t7 done; declined t9. Read one: sminos task show t7`), at a launch, a resume, a compaction and a successor's first start alike. The hook hands the lines to the engine first and marks after, and it marks exactly the outcomes it handed over, for the session it handed them to: so a start that fails between the two shows them again at the next, and an outcome another start or MAWS marked in the meantime is never stood in for by one this session was not shown. It is the engine's start context and no acknowledgement by the model: the board claims that the line was put there, not that it was read.

**An ended thread** cannot be woken: the verdict's `told` is `ended`, and one line with no addressee goes to the log of the project the thread ended in, naming the task and no session (`tasks: t7 was completed; the conversation that assigned it has ended. It is on the board: sminos task show t7`). If the thread returns (its human opens the session again) its start line names the act.

**A session MAWS runs.** While its process runs, sminos delivers the notice to it as to any member, under whatever settlement MAWS's process has (baseline 5): nothing more is needed. When its process is gone sminos starts nothing, whatever its thread's record says, so the door sends none; an act that asked for a wake is MAWS's to act on. It finds what waits (X3), brings the session up, and the session is told by its start line; where MAWS's launch does not run sminos's start hook, MAWS says the same words itself and tells the door so (`shown`, naming the session it told).

**The door's part, and a door that dies.** The door applies the act in one step of the store, marking a sending due where the table decides one; then, with the store's lock let go, it sends; then it records what it sent and what sminos answered, or that nothing could be written and why. A door that dies in between leaves the sending due. The act's verdict is stored and does not change; the due sending is resolved by whatever next calls the door on the machine (the surface's resend of the same line, or any other act) and, failing that, by the daemon's hourly duty, so a wake that was asked is late and not lost. Two callers can each resolve one due sending, and then two notices name one act: that is left as it is, since neither can wake against the human's choice. A notice once written is never written again by the board: sminos retries what it holds.

**The alternative weighed: an envelope the question sheet's way.** The owner first chose it ("질문 시트처럼 봉투로", 2026-11-27T22:20Z): the human's outcome and note inline in a `[tasks v1]` envelope with a `<task-delivery>` block, carried by the sheet's delivery routes, owed until its block was found in the conversation. Written out, it needed the sheet's routes extracted into a shared module (they run only where a session chose the sheet), a seam of nine rules agreed with the sheet's holder and ordered after the sheet's own next change, a composer and a budget, receipts for landing and rerouting, and a wake protocol beside sminos's. The owner read that cost in this document and chose the inbox ("sminos inbox로 바꾼다 (Recommended)", 2026-11-27T23:41Z). What the inbox gives up: the human's note is one command away instead of inline, and nothing proves the agent read the notice, which is why the start line stands behind it.

**The outcome's states and who moves them.** Every transition is one command under the store's lock.

| event | by | what changes on the outcome |
|---|---|---|
| a `done`, `decline` or `comment` applied | the door | it exists, its wake choice resolved, not shown, and a sending due where one is decided |
| the sending resolved (a subagent told, a notice written, or nothing writable) | the door, in the same call; any later call of the door; the daemon's hourly duty | what was sent, to whom, for the live alone or not, and sminos's answer then; or the refusal |
| the target's start line handed to the engine | the start hook's second call, for the keys it handed over | shown, to that session |
| `shown` naming its task, its session and its key | the door (MAWS's deliverer) | shown, to that session |
| its target ended, the line written to the project's log | the door | `endedLine` |
| shown, and its task closed 30 days | the daemon's hourly duty | gone with the task |

### D7. The three-day rule (R10)

A thread is not ended by the three-day rule while it is the target of an open blocking task (D5: the thread that would be woken, so a cleared conversation with a living successor is not kept for a task its successor now answers for). The change is in the ending pass and nowhere else: in `sweep_threads`'s test of what is due, where devcloud's census is not yet asked, and again in `sminos.end_by_rule`'s guard. A thread kept this way is said once in `daemon.log`, as a thread that owns a host is. **[binding — B1a's change must agree with the store B1 builds: what its predicate reads is X3's]**

- The exemption also holds while a wake that was asked may still be on its way: an outcome of one of the thread's tasks whose act asked for a wake, not yet shown at a start, its act less than three days old. It holds from the step that applied the act, before any notice is written, so no ending pass can run in between. Without it a blocking task completed on the fourth day closes the task, lifts the exemption, and the hourly pass can end the thread between a wake that failed and sminos's retry of it, which is the case R10 was asked about. Counted from the act, so a thread sminos holds for good is not kept for ever by one outcome; and a thread that was woken has been shown the outcome at its start.
- The predicate reads the store with no lock, and one instant is left open on purpose: a change that would protect a thread, landing after the guard's last look and before the end. For the human's act, the thread ends and the act's notice finds nobody: sminos pushes nothing, the card shows the thread ended at its next read, and the start line names the act if the thread returns. For an agent's change (a successor's reopen, a revise to blocking) nothing is sent at all, and the task's later completion answers `ended`. Serializing the two was weighed (the end taking the store's lock around the record's change) and not taken: it buys that instant at the price of a lock order across two subsystems.
- No store at all is no exemption: a machine that never had a task ends threads as today. A store that is there and cannot be read is no answer, and no answer keeps the thread: an end is not undone by the daemon.
- The channels-and-threads design says the rule applies to every thread, with the host exemption. That document is closed and is not amended; the rule as it stands is written where the code's own account is, `sminos/skills/sminos/scripts/CLAUDE.md`, and here.

### D8. Surfaces

- **The board**: the open tasks across sessions, blocking first, then needed by due date, then optional; each row its title, project, asker and the asker's state, due date, and "Updated" when an agent revised, commented or reopened since the human saw it. A card renders agent Markdown under the sheet's link policy (links limited to `http` and `https`, any other drawn as its text) and shows a link's host plainly.
- **A notice to the human**: a new blocking task raises a notification on the machine, as a question does today (`$.ui.notify` from the asker's session, when its mod sees its own new blocking task in the store); the phone's push comes with B4.
- **The command line**: `sminos task list|show|done|decline|comment` (D4). The first surface, and what remains when no page is reachable.
- **The terminal**: a line of its own above the prompt while the session has open tasks, `2 tasks for the human (1 blocking) · <the board>`, where `<the board>` is a live surface's board address (X4) or `sminos task list`.
- **The local page**: `mawsd`'s page server carries the board as a page of its own under the sheet page's origin, pairing and four rules (B2).
- **The MAWS app**: a native board of its own; how a blocking task marks its session there is the owner's, on drawn frames with the board's look (B3).
- **The phone and other machines**: after the sheet's own remote child (B4).

### D9. What is trusted, and the limits

- **Trust.** Every session on the machine runs as the owner and can write the store's file; the store's rules (who revises, the door refusing a session) keep agents that mean well from stepping on each other and are not a defence against one that does not. An agent that strips its environment to complete the human's task is misbehaving in the way one that edits the file is.
- **Nothing proves an agent read a notice.** sminos writes it to the session's inbox, and the engine can hold or drop a peer's frame without saying so (baseline 5); a thread woken for one can die before reading it. Nothing sends a notice a second time. The start line is what stands behind it, and it is the engine's start context, not a reading either.
- **An act is named twice** to a session that was told by a notice: once then, once at its next start or compaction.
- **A wake that was asked can be late**, by up to the daemon's hour, when the door dies between applying the act and sending; and **one act can be named by two notices** when two callers finish that sending at once.
- A machine that is off shows nothing elsewhere until B4. A machine that is deleted takes its open tasks with it; `devcloud vm down` naming them first is deferred work (Deferred).
- **A witnessed `/clear` can leave no pair.** The pair has two writers, `sminos record`'s clear path before the alias is released and the new session's `remind`, each waiting the store's lock its full 10 s. When both fail (each past its wait, or each raising), the alias is released and no pair is written: the outcomes, and the right to revise, stay with the conversation that was left, whose start line still names them. The alias release does not wait on the store, so that a start never hangs on the board.
- A fork's history says it assigned tasks that belong to the conversation it was forked from; at its start, when the store holds any open task, a sentence of its own in the published set's grammar (`sminos/types/tasks/grammar/texts.md`, `fork`) says so, and their outcomes go to that conversation.
- The human completes from a terminal, a page or the app, not from a session's own shell escape, which carries the session's id.
- A notice needs what any message needs: a project the target is a member of. A session that is in none is told at its next start.
- The session manager's ledger reads the store when the whole picture is built; until then it lists a task only where a session wrote about it.

### Delegated unknowns

| id | question | who answers | what decides |
|---|---|---|---|
| U1 | With the hook's changed command: what does the permission dialog show; which allow rules still match (a prefix rule for the verb; a rule that names arguments); what does a classic `PreToolUse` check receive; does a secret's handle in the same command still restore | B1, M4 (one live check, each case observed and none asserted beforehand) | A prefix rule that stops matching moves the flag's place before M4 lands; the rest is written beside D2 as found |
| U2 | sminos's own suite shows an addressed notice waking a thread its human opened, and its live check an idle peer starting a turn. Not shown: a notice alone waking a spawned seat; a notice for the live alone to one recipient, and how its frame reads; a machine cut over to the reach and words gates, where a notice can be gated or wait behind another event; what the engine does with a `tasks` frame in a session that bypasses permission prompts, which sminos's own account says it may hold | B1, M2 (one live check, each case observed and written down) | R12 is the result required for a frame the engine admits. A seat that a notice alone does not wake, or an engine that holds the frame where the owner's sessions run, goes to whoever holds sminos before M2 lands; the start line tells the asker in every case |
| U3 | How often do agents file an act as a question, or a decision as a task; do they flood the board with small wants | B5 | B5's thresholds, set in its ledger before its runs |
| U4 | Another `task` on the PATH (Taskwarrior, go-task) | the ticket board's M1 | its answer binds both destinations |

## Parent-Level Acceptance

The unit closes when this holds on one Mac with the released plugins, each line seen and not inferred. A1 to A8 need B1 and B1a; A9 to A11 add B2, B3 and B4 as each lands; A12 is B5's.

1. **Assign and go on.** In a terminal session, one Bash call runs `task assign-human --class blocking --title "Log in to the console" …` and `task assign-human --class needed --due <date> --title "Rotate the key" …`. Both print an id; each returns within a second, measured; the session's turn continues.
2. **The board lists both**, from a terminal that is no session: `sminos task list` prints the blocking one first, each with its project, its asker's alias and state, and the due date; the session's own terminal shows `2 tasks for the human (1 blocking) · …` above the prompt, and the machine raised one notification, for the blocking task.
3. **The terminal is closed.** Within two passes of the daemon, `sminos task list` shows the blocking task's asker as stopped and to be woken.
4. **Done, with a note, wakes it.** `sminos task done t1 --note "logged in with account B"` prints a verdict whose `told` is `wake`. The session starts in the background; its first message is the `tasks` notice, naming `t1` and done and nothing an agent wrote; its start context names the act too; `sminos task show t1`, run in it, prints the note. `sminos task show t1 --json` shows the notice sent, able to wake, with sminos's answer, and the outcome shown at that start. The project's log holds one notice and not the note.
5. **A check that fails reopens.** In that session `task reopen t1 --comment "the console still asks for a login"`; `sminos task list` shows `t1` open again, Updated, at revision 2. `sminos task done t1` (revision 1) is refused as stale, saying the current revision.
6. **A cleared session's task reaches its successor.** A second session assigns a needed task, is cleared, and its successor works in the same terminal. `sminos task show` names the successor as the task's target. `sminos task done --wake` of that task: the successor receives the notice, saying the task was assigned by the conversation it replaced; the cleared conversation is not started; a third session that takes the cleared one's old alias receives nothing.
7. **A subagent's task.** A subagent assigns a task; `sminos task show` names the subagent. Completed while the subagent runs, the notice is in the subagent's conversation and absent from the main one; completed after it ended, in the main conversation, naming the subagent by its id.
8. **What waits, waits; and three days.** A needed task completed with no wake while its session is stopped starts nothing; the session, opened again, is told by its start line and by no notice. An optional task declined while its session idles starts no turn. A needed task completed while its session runs and is busy, the session then stopped before it read: nothing starts it, and its next start names the act. With the period set short (`SMINOS_THREAD_END_AFTER`), a thread stopped past it with an open blocking task is not ended and `daemon.log` says why once; its task declined without a wake, the next ending pass ends it. A thread stopped past the period with only a needed task is ended as today, its task stays on the board, and its later completion answers `told: ended` with one line in the project's log; opened again by its human, its start line names the act.
9. **The local page** (B2): the board at the page server's origin, paired as the sheet's page is, lists what `sminos task list` lists, updates within two seconds of a change, and a card's Done with a note produces A4's effect.
10. **The MAWS app** (B3): its board lists the same tasks; a task assigned by a MAWS-run session, completed there while that session runs, reaches it as the notice; completed with a wake while its process is gone, a closed task among them, MAWS brings the session up and it is told at its start, once.
11. **Another machine** (B4): a task on a second machine is listed and completed from the phone, and applied once when the act is sent twice.
12. **Behaviour** (B5): its scenarios pass their thresholds with the wording that ships.

## Children

### B1: The store, the door, the notice, the verbs — plan (this repository)

- **Purpose:** Everything a terminal user needs for the unit's promise: the store and its published set, the door and the command line surface, the agents' verbs in sminos and in the `task` plugin, the notice and the start line, the subagent's attribution, the terminal's line, and what agents are told.
- **Acceptance:** A1 to A8 on a Mac (A8's three-day part with B1a), by the commands its execution document quotes; the published set (X1) at version 1 with its digest.
- **Edges:** blocked-by: nothing for its M1 and M2. Its M3 is blocked-by `external:` the ticket board's M1 (the `task` plugin's first release). Its M5 is blocked-by B5. blocks: B1a (by its M1), B2 and B3 (by its gate G1, the set published), B4.
- **Contracts:** owner of X1, X2, X3, X5, X6; reader of X4; ships X7.
- **Design inheritance:** D1 to D5, D8 (the command line, the terminal, the notice to the human), D9; U1, U2.
- **Required:** required.
- **Status:** M1 landed (G1 published); M2 dispatchable now. Its execution document is `docs/doperpowers/plans/2026-11-27-task-board-b1.md`.

### B1a: The three-day exemption — brief (this repository; whoever holds sminos)

- **Purpose:** A blocking task completed after three days still finds a thread to wake (R10).
- **Acceptance:** A8's three-day part. In `sminos/tests/test_threads_ended.py`'s form: a thread stopped past the period that is the target of an open blocking task is not ended and is said once; with the task closed and no wake-asked outcome that is unshown and younger than the period, it is ended; with one, not ended until the period has passed since the act, from the moment the act was applied and before any notice is written; with no store on the machine, ended as today; with the store unreadable, not ended; a thread with only needed or optional tasks is ended as today; a cleared thread whose successor lives is ended as today while the successor is kept.
- **Edges:** blocked-by: B1's M1 (the store, `target_of`, an outcome's wake choice and whether it was shown). blocks: nothing.
- **Contracts:** consumer of X3.
- **Design inheritance:** D7, binding. Advisory: the predicate is one function of the tasks' module over the store and `target_of` (B1's), called with no lock from `sweep_threads`'s test of what is due and from `end_by_rule`'s guard; the line in `daemon.log` follows `holding`'s form.
- **Required:** required.
- **Status:** built on branch `task-board-b1a`, one pull request, not merged; sminos 1.62.0. The predicate is `sminos_tasks.keeps(thread, period)`, over the store and `target_of`'s resolution without the state it describes; called from `sweep_threads`'s test of what is due and from `end_by_rule`'s guard, which now takes the rule's `period`; a kept thread said through `leaves`, `holding`'s line. The Acceptance's cases are `TaskBoard` in `sminos/tests/test_threads_ended.py`.

### B2: The board on the local page — plan (MAWS)

- **Purpose:** The board in a browser beside the terminal: `mawsd`'s page server carries it as a page of its own, with its model and components, so a terminal user completes a task without typing a command.
- **Acceptance:** A9. Every refusal of the page's four rules holds for the board's routes as for the sheet's. A card renders a task's Markdown under the link policy and shows a link's host. A done or a decline names the revision the card showed, and a stale verdict is shown on the card with the new text. The card shows the asker's state, read again while it is open (a session that stops while the card shows shows as stopped within five seconds, with no task written), and offers the wake choice for a stopped asker. An act sent twice under one key is applied once. The page's acts are applied when `mawsd` was started from inside a session. The registration (X4) exists while the server runs.
- **Edges:** blocked-by: B1.G1; `external:` the sheet's C4 (the page server, its pairing and four rules) and the sheet's C3 first landing (the components' ground). blocks: B4.
- **Contracts:** consumer of X1, X2, X3; writer of X4.
- **Design inheritance:** D4, D8, D9. Advisory: the page draws from `sminos task list --json` and `show --json`, which carry each asker's state as computed then, and not from the store's file, which does not hold it; it reads again when the file's `seq` moves and on its own interval; it writes only through the door.
- **Required:** required.
- **Status:** not-dispatched (B1.G1 met; its external edges). Its execution document is MAWS's.

### B3: The MAWS app's board, and sessions MAWS runs — plan (MAWS)

- **Purpose:** The board as a native place in the app, and the wake for the sessions sminos does not start.
- **Acceptance:** A10. The app's board lists what the store holds and acts through the door. A MAWS-run session that runs receives the notice by sminos's delivery, as it receives any peer's frame; MAWS adds nothing to that path. For one whose process is gone, whether or not sminos holds a thread record for it, MAWS finds the outcomes that wait and asked for a wake (`sminos task waiting --json`, X3, which lists them whatever their task's state or age) and brings the session up, for those alone (R5). The session is told at its start: by the start line where sminos's start hook runs in MAWS's launch, which marks them shown; and where it does not, by MAWS's own steer of the same words, after which MAWS marks them through the door (`shown`, a task and its session a line), so each is acted on once. How a blocking task marks its session in the app is settled with the owner on drawn frames before it is built.
- **Edges:** blocked-by: B1.G1 (the reader, the door's `shown`); B1's M2 for the notice to a running session. blocks: B4.
- **Contracts:** consumer of X1, X2, X3, X6.
- **Design inheritance:** D5 (a session MAWS runs; the notice carries nothing an agent wrote), D8. Advisory: a session MAWS runs is one whose lane is B when the store is read; a steer of MAWS's own keeps to the start line's form (an id, the outcome's word; no title).
- **Required:** required.
- **Status:** not-dispatched. Its execution document is MAWS's.

### B4: The phone and other machines — decomposing run at dispatch (MAWS)

- **Purpose:** A task on any machine is seen and completed from the phone and from the app on another machine.
- **Acceptance:** A11; a blocking task raises the phone's push; an act resent over the remote path is applied once (the door's key).
- **Edges:** blocked-by: B2, B3; `external:` the sheet's C6 (the remote path it builds).
- **Contracts:** consumer of X1, X2, X3.
- **Design inheritance:** D4's key, D8. Deliberately coarse: its cut is made when the sheet's remote child has landed.
- **Required:** required.
- **Status:** not-dispatched (deliberately late).

### B5: Behaviour, before the wording ships — brief (this repository)

- **Purpose:** The words agents are told (D2) are tested before they ship, against the failure modes the design expects of them: an act filed as a question or a decision filed as a task, and a board flooded with small wants.
- **Acceptance:** With the sheet's eval harness (`tests/output-styles/`, the sheet's C1), a stand-in `task` that records its calls, and the skill not preloaded (only the start guide's line and the command's help in context), three scenarios meet thresholds B5's ledger sets before its first run, each judged by what ends on the board and the sheet: a login wall, met by a subagent (a task, not a question); a decision the agent is blocked on (a question, not a task); a long job with many small wants (the board is not flooded). What an agent does around them, where it goes next, what it reads and when, is not judged. Its result is the wording of X7, and one sentence for the question tool's description with its evidence, handed to the sheet's holder.
- **Edges:** blocks: B1's M5.
- **Contracts:** owner of X7; consumer of X5, X6.
- **Design inheritance:** D1, D2 ("What agents are told"), D5's notice; U3.
- **Required:** required.
- **Status:** not-dispatched (dispatchable now; it needs no built store).

## Cross-Child Contracts

- **X1 — The published set.** `sminos/types/tasks/`: schemas for `state.json`, each act's line and each verdict, `list --json`, `show --json` and `waiting --json`; the notice's, the ended line's and the start line's texts as one grammar with examples; fixtures, one step each (`before/`, the command, `after/`, the verdict); a manifest with a digest. Written by a generator by hand from this document, never by the commands; `version` 1. Owner B1 (its gate G1 publishes it); B2, B3 and B4 pin it by digest. A change after G1 is a ruling of this document's writer and a new version.
- **X2 — The door.** `sminos task act`, D4's lines and verdicts as B1's execution document's §3 fixes them literally (a `shown` names one task, the session that was told and that task's keys); exits 0 when every line was answered, 2 for a line that is not the schema's (nothing applied), 3 for a caller that is a session, 75 for the lock not had in 10 s, 1 for a store it cannot write. Applied once by `key`, a UUID; a key reused for another line is refused. A surface runs it with `CLAUDE_CODE_SESSION_ID` removed. Owner B1; the only writer B2, B3 and B4 have.
- **X3 — The reader.** `sminos task list --json` and `show --json`: the model of X1, each task with its target, that target's state and `runner` as computed at the read, each outcome with its wake choice, what was sent with sminos's answer then, and whether a start has shown it. `sminos task waiting --json`: every outcome no start has shown, of open and closed tasks alike, each with its target. A reader writes nothing: "Updated" is cleared only by a `seen` a surface sends for the snapshot its human opened, never by a read. Two signals say when to read again: the store's `seq` for what was written, and the reader's own interval (five seconds while a board shows) for what changes without a write: a session stopping, a thread ending, a held wake freed. For D7: a task's state, class and target; an outcome's wake choice, its act's time and whether it was shown. Owner B1; consumers B1a, B2, B3, B4, and later the session manager.
- **X4 — The board's address.** A surface that shows the board registers under `$SMINOS_HOME/tasks/surfaces/<name>.json` with the fields of the sheet's surface schema (`v`, `name`, `url`, `reach`, `pid`, `heartbeatAt`), where `url` is the board's own complete address and not the origin it shares with the sheet's page. It is alive while its heartbeat is at most 30 s old and its pid runs, as the command judges it. Writer B2; reader B1.
- **X5 — The agents' verbs.** D2's names, flags and exits, in `task` and in `sminos task`. Owner B1. The three dispatch branches in the `task` plugin (`show` and `comment` by the id's form, `list --human`), taken before the ticket board's own preflight, and the sentence of the ticket board's D4 they replace ("with those names unused") go to the ticket board's writer before B1's M3.
- **X6 — The notice.** The program's name `tasks`; D5's texts, for the three outcomes, their clauses, the ended thread's line and the start line, as B1's execution document's §5 fixes them word for word; that a notice whose act asked for no wake is for the live alone; and the rule that none carries text an agent wrote. Owner B1; B3 keeps to it, and a reader of project logs may recognize it.
- **X7 — What agents are told.** The skill's body, the start guide's line, and the proposed sentence for the question tool's description: D2's definitions, and no prescribed act or sequence (R14). Owner B5; B1's M5 ships what B5 passed, and the sentence goes to the sheet's holder with its evidence.

## Ordering & Dependency Map

    B5 ───────────────────────────────────────────────┐
    B1.M1 (G1) ─┬─> B1.M2 ───> B1.M4 ─────────────────┴─> B1.M5
                ├─> B1a
                ├─> B1.M3  (also: the task plugin's first release) ──> B1.M5
                ├─> B2 (also: the sheet's C4, C3) ─┐
                └─> B3 (also: B1.M2 to run live) ──┴─> B4 (also: the sheet's C6)

B1's M1 waits on nothing: the store, its commands and the door, with every outcome named at the asker's next start, which stays true of every later landing. M2 is the push: the notice, the subagent's message and the wake. M3 is the `task` plugin's verbs, when that plugin exists. M4 is the session's side in the mod: the subagent's attribution, the terminal's line, the notification. M5 ships the words B5 passed. A terminal user has a working board from M1 and is told at once from M2. Nothing in this unit waits on the question sheet.

## Verification

- **This document**: reviewed twice in its first form (the design and B1's execution; then the repair), and once after the owner changed the delivery (R9), on the rewritten delivery and B1's re-cut execution; each round folded.
- **B1**: its execution document names its own; in short, M2's pull request (the notice and the wake) is reviewed at the *high* rung, since a mistake there wakes threads nobody asked to wake or tells nobody; the rest at *medium*.
- **B1a**: the medium rung.
- **B2, B3, B4**: MAWS's, by their own documents; B2's routes are served by the sheet's page server, whose serving code the sheet's composite reviews at its high rung.
- **Recomposition**: Parent-Level Acceptance run as written on one Mac, by the session that holds this document; a scale review, since B1 and B1a touch one daemon.

## Risks & Mitigations

- **A wake that sminos does not perform.** The wake rests on sminos's notice, which its own suite shows for a thread its human opened and nothing shows for a seat or behind the gates (U2). Mitigation: U2 is checked live in M2; the door never says a wake happened, only that one was asked; and the start line names the act whenever the session next starts.
- **A notice the agent does not act on.** The notice points and does not carry: an agent that does not read the task misses the human's note. Mitigation: the notice names the task and says the human acted, the start line names it again, and what agents are told says that the human's words are read with `sminos task show` (D2); the note inline is Deferred, should reading it by command prove a cost in use.
- **The board floods.** An agent that files every want as a task makes the board useless. Mitigation: B5's scenario of many small wants gates the wording; the store's cap of 500 open tasks is the backstop.
- **A changed command surprises the person.** The hook adds text to a command the model wrote. Mitigation: the flag reads plainly, goes only on the two assigning commands, and U1's live check looks at the dialog.
- **Turns started in many sessions at once.** One human clearing a backlog starts a turn in every idle asker. Each is one notice and one read; the non-blocking declines among them start none.

## Deferred / Out of Scope

**Deferred (may return):** a notice sent again when one is known not to have been pushed (sminos would have to say so; today the start line covers it). `devcloud vm down` naming the open tasks of the machine it removes (a third plugin; a ticket at materialization). The human's note inline in the notice, should reading it by command prove a cost in use. A second asker joining a task (the schema allows it). The human re-classing a task. Adoption of a task by another session. A board across machines on the local page. Captured file references in a task's body. The session manager's ledger reading the store.

**Explicitly out of scope:** the human adding tasks of their own; sync with GitHub issues (R6); events and subscriptions (the owner, 2026-11-24); merging a task's outcome into the sheet's delivery or the sheet's page (R8); any change to the question sheet's code or contract.

## Tracking Map

The owner approved the spec on 2026-11-27 (R11), as it read at `478da2969` with the repair then under review (folded at `8a59630fc`), and ruled R9 after it; the baseline from here is the commit that rewrote D5 for R9. Nothing is on the board yet.

| child | artifact | status |
|---|---|---|
| B1 | `docs/doperpowers/plans/2026-11-27-task-board-b1.md` | M1 landed, pull request #640: G1's set `sminos/types/tasks/` published at version 1, digest `9edb85d31c61efdaffa7ed4eff1b8bcfac9d6868a968d791bac8f061e82c21e6`; M2 next |
| B1a | its pull request (branch `task-board-b1a`) | built, in review: `sminos_tasks.keeps`, sminos 1.62.0; not merged |
| B2 | MAWS's execution document | not-dispatched (B1.G1 met; its external edges) |
| B3 | MAWS's execution document | not-dispatched (B1.G1 met) |
| B4 | its own cut at dispatch | not-dispatched (deliberately late) |
| B5 | ledger at dispatch | not-dispatched (dispatchable now) |

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a recomposition check: verify Parent-Level Acceptance as written — all children landed is not the same event — then retrospect.
