# Task Board, B1 — the store, the door, the notice, the verbs: execution (2026-11-27)

> **Composite:** `docs/doperpowers/specs/2026-11-27-task-board-design.md`, child **B1**. **Parent pin:** `fe004c54c` (branch `task-board-spec`). The child's section in the composite ("### B1: …") is its spec; the composite's D1 to D5, D8 and D9 are its design, binding where they are marked, and X1 to X3, X5 and X6 the contracts it owns. This document carries the constraints, the decisions the composite did not carry, the interfaces and the milestones, and restates nothing of the design.
>
> **Written against:** this repository's `main` at `40b79a7d1` (sminos 1.59.0); `ticket-board-spec` at `143552115` (the `task` plugin specified, not built).
>
> **Read before M1:** the composite whole; `sminos/skills/sminos/scripts/CLAUDE.md`, the threads' paragraphs (the record, the wake, `/clear`) and the question sheet's (as the model of a per-machine record with a door and a published set); `sminos/types/sheet/README.md`, as the model of a published set; `sminos/hooks/CLAUDE.md`. Before M2: in `sminos/skills/sminos/scripts/sminos.py`, `cmd_say`, `say_into`, `deliver_say`, `deliver_next`'s docstring, `notice_of`; `sminos/tests/test_notice.py`.

## Progress

- [ ] M1 — The store, its commands, the door, the start line, the published set (gate G1). Built first.
- [ ] M2 — Telling the asker now: the notice, the subagent's message, the wake.
- [ ] M3 — The `task` verbs. Waits on the `task` plugin's first release.
- [ ] M4 — The session's side: the subagent's attribution, the terminal's line, the notification.
- [ ] M5 — What agents are told, what is written beside the code, the acceptance. Waits on B5.

## Words this document adds

- **Intention**: how the door means to tell the asker of an outcome, recorded on the outcome in the step that applies the act: `tell` (a running subagent), `notice`, or `start` (it waits for the start line).
- **G1**: the gate M1 closes: the set `sminos/types/tasks/` published at version 1, which MAWS's children pin.
- **The tasks' module**: `sminos/skills/sminos/scripts/sminos_tasks.py`. **The tasks' mod**: `sminos/hooks/mods/tasks.tsx` with `tasks-model.tsx`.
- **H/**: `sminos/hooks/mods/`. **S/**: `sminos/skills/sminos/scripts/`. **T/**: `sminos/tests/`.

## Verification

This document was reviewed by `doperpowers:adversarial-reviewer` in its first form (twice) and once after the delivery changed to sminos's inbox. On the branches, through doperpowers:review-code: M2's pull request at the **high** rung (a mistake there wakes a thread nobody asked to wake, or tells nobody); M1, M3, M4 and M5 at **medium**. Each milestone's own gate is in its entry; gates run through `ci-gate` on the committed head, never on this machine.

## How it lands

One pull request a milestone, each from a worktree of its own branched from `main`, each raising the version of every plugin whose shipped files it touched (`scripts/bump-version.sh --plugin sminos`, `--plugin task`; `scripts/bump-version.sh --since origin/main` before a push), each body ending with the session line.

| landing | waits on | what a user has after it |
|---|---|---|
| M1 | nothing | tasks assigned with `sminos task assign`, listed and completed from a terminal; the asker is told of every outcome at its next start, by its start line. Nothing is pushed, and the door says so: `told` is `next-start` or `ended`. G1. |
| M2 | M1 | the asker is told at once: an idle session starts a turn, a stopped thread is woken per the human's choice, a running subagent is told itself |
| M3 | M1; the `task` plugin on `main` | `task assign-human` and the other verbs |
| M4 | M2 | a subagent's task names it; the terminal's line; the notification |
| M5 | M3, M4, B5 | the skill and the start guide's words; the acceptance run |

M3 and M4 may be built side by side. A milestone that waits is not started early on a guess of what it waits for. The session that holds the composite dispatches each as it becomes free; a single milestone is worked by one executor.

## Constraints on every milestone

- **Python 3.9, standard library only**, as every sminos script is; the mods are TypeScript checked by `tests/mods/typecheck.sh` (the `mods-types` gate).
- **Only the command writes the store.** A hook can neither lock nor replace a file: the mod runs `sminos task …` through `$.process.run` and keeps what it answered.
- **The store's lock is a leaf.** Whoever holds `tasks/.lock` takes no other lock of sminos's, reads thread records only through reads that write nothing (`sminos.member_row` and the threads' module's getters, never `members()` or `view_of()`, which finish journals and append), and appends to no log. A notice is written with the store's lock let go.
- **`$` crosses no import.** A mod reaches the engine through closures made inside its own hooks (the `Port` pattern in `H/sheet.tsx`), so a test hands its own.
- **A whole value is checked with `fullmatch`**, never `match` against `^…$` (`sminos/CLAUDE.md`).
- **Nothing new at the root of `$SMINOS_HOME`**: every sminos reads a `*.json` there as a seat. The store is the directory `tasks/`.
- **Nothing of the question sheet's is touched**: not `S/sminos_sheet*.py`, not `H/sheet*.tsx`, not `sminos/types/sheet/`.
- **No text an agent wrote goes into a message to an agent**: the notice, the subagent's message and the start line are built from the fixed words of §5, a task's id, the outcome's word, an alias and an agent's id, and nothing else (D5).
- **The repository is public.** No hostname, address, account, project id, secret's name or value, local absolute path or session id in code, tests, fixtures, documents or commit messages. Fixtures use stand-in ids (`5eed0000-…`) and `{HOME}`.
- **Version bumps** by `scripts/bump-version.sh` only, in the same commit as the change.
- **The composite's binding marks** bind here: D1's line and fields, D2's flag, D3's one store, D4's one door, D5's one message an act, its content rule and its target.

## The store's steps

The composite's D5 table is the outcome's state machine; this is what the commands add to it. Every row is one step: take `tasks/.lock`, read `tasks/state.json`, refuse if its `version` is above this command's, change, replace, release; `seq` + 1 when anything changed, nothing written when nothing did. The version is judged on the file read under the lock, in every writing step, the daemon's included.

| command | who | refused when | what it changes |
|---|---|---|---|
| `assign` | a session | no session (3); it would make 501 open (3); a field out of bounds (2) | a task at `nextId`, revision 1, open; its asker from the session, its thread and `--asker-agent` |
| `revise` | the asker (§2) | not the asker (3); not open (3); nothing given (2) | the fields given; revision + 1; `agentSeq` |
| `comment` | any session, or the human through the door | closed (3, or verdict `closed`); empty (2) | a comment; from an agent `agentSeq`; from the human an outcome `comment` |
| `withdraw` | the asker | not the asker (3); not open (3) | state withdrawn, `closed` |
| `reopen` | the asker | not the asker (3); not done (3); no comment (2); it would make 501 open (3) | state open; revision + 1; the comment; `agentSeq` |
| `act` `done`, `decline` | the human | a session (3); revision not current (`stale`); not open (`closed`); a key used for another line (`key-reused`) | state; `closed`; an outcome with its wake choice and its intention; the verdict kept by key |
| `act` `seen` | a surface | a session (3) | `seenSeq`, to the `seq` the line names when that is higher |
| the telling's result (M2) | the door; the daemon | the outcome no longer intends what was done | `announced` on the outcome, or its intention changed |
| the ended line (M2) | the door; the daemon | already marked | `endedLine` on the outcome |
| the start line | `remind`, after printing | — | each outcome it printed: `announced`, by `start` |
| the successor's pair | `sminos record` and `remind`, at a witnessed `/clear` | no store yet: nothing is made; the pair already there: nothing changes | `successors[<session left>]` |

**Where a change becomes visible.** At the `os.replace`: a reader sees the state before or after, never between. The door computes a line's whole verdict, `told` included, before its replace, stores it under the act's key in the same replace, and prints it after, so the same line again reads the stored verdict and two callers of one key cannot be answered differently. **What a death leaves.** Before the replace, nothing (a `.tmp-` file the next step removes). After the replace and before the telling, or after the telling and before its result is recorded: an outcome whose intention has no result. The daemon's tick finishes it (§5); the notice's identity makes a second writing of it write nothing. A `remind` that dies after printing and before marking prints the same outcomes at the next start.

## Interfaces and Dependencies

### §1 · `state.json` (X1)

    {
      "v": 1, "version": 1, "seq": 14, "nextId": 8,
      "tasks": {
        "t7": {
          "id": "t7", "revision": 2, "state": "open",              // open | done | declined | withdrawn
          "class": "blocking", "title": "…", "body": "…", "due": null, "tags": [],
          "project": "<project id>" | null,
          "askers": [{ "thread": "<thread id>" | null, "session": "<session id>", "alias": "alpha" | null,
                       "agent": { "id": "a1b2c3d4e5f60718", "name": "reviewer" } | null }],
          "born": 9, "createdAt": "<time>", "agentSeq": 12, "seenSeq": 9,
          "comments": [{ "n": 1, "by": "human" | { "session": "…", "alias": "…", "agent": {…} | null }, "at": "<time>", "text": "…" }],
          "closed": null | { "how": "done" | "declined" | "withdrawn", "at": "<time>", "text": "…" },
          "acts": 3,
          "outcomes": [{ "key": "t7.3", "seq": 13, "kind": "done" | "declined" | "comment", "at": "<time>", "revision": 1, "text": "…",
                         "wake": true,                                  // the human's choice, resolved at the act
                         "intends": "tell" | "notice" | "start" | null, // null once announced
                         "intendedAt": "<time>",
                         "announced": null | { "by": "tell" | "notice" | "start", "at": "<time>", "session": "<whom>",
                                               "answer": "<sminos's answer for a notice>" | null },
                         "endedLine": null | "<time>" }]
        }
      },
      "applied": { "<act key>": { "task": "t7", "at": "<time>", "digest": "<sha256 of the line as canonical JSON>", "verdict": { … } } },
      "successors": { "<session left>": { "session": "<session begun>", "at": "<time>" } }
    }

A time is ISO-8601 in UTC with milliseconds, for showing; order is by `seq`: `born` is the store's `seq` at the assign, an outcome's `seq` the one at its act, `agentSeq` the one at the last revise, comment or reopen by an agent. A row is "Updated" when `agentSeq` is above `seenSeq`. `acts` counts the human's acts on the task that make an outcome; an outcome's key is `<id>.<acts>` at its act. An outcome is **unannounced** while `announced` is null. `project` and `alias` are null for a session sminos knows no project or name for. An object's unknown fields are kept by every writer (D3). The set's serialization, cuts and "always present" readings are fixed by M1's generator, in the manner of `sminos/types/sheet/README.md`'s "Readings fixed with the set".

### §2 · The asker and the target

    asker_of(session, agent=None) -> {thread, session, alias, agent}     # at an assign
    target_of(store, task) -> {session, thread, alias, project, state, runner, wake, why, via}
    is_asker(store, task, session) -> bool
    cleared(session, source) -> None                                     # registers a witnessed clear's pair

`asker_of` reads the session's thread as `sminos_channels._self` does (`threads.current_record(session, fresh=True)`); a session with no record has `thread: null`.

`target_of` decides whom a task's outcomes go to now. For a task whose asker has no thread the target is the asker's own session and nothing below applies: no successor is followed for it. Otherwise let `first` be the asker's thread's current session, and the chain `first`, then `successors[first].session`, then that one's successor, and so on to its end; a session met twice ends the chain there (no count cuts it short).

1. `first`, when a process holds it. `via: "self"`.
2. Else the last session of the chain, past `first`, whose thread exists and has not ended. `via: "cleared"`.
3. Else `first`. `via: "self"`.

Then, for the session chosen: `runner` is `maws` when its lane is B (`sminos_records.lane_of(records.read(session))`, as `sminos_channels` reads it), else `terminal`; `project` and `alias` are those of its membership now, null when it is a member of no project. `state` is `running` when a process holds it (the engine's records, read once a call and shared by every task of that call); else `ended` when its thread's record has ended; else `stopped` when it has a thread; else `gone` (no thread and no process). For `stopped`, `wake` and `why` are this machine's own judgement, `sminos.wake_here`. A record that cannot be read gives `state: "unknown"`, which every consumer treats as stopped and not to be told now. `target_of` reads with no lock and writes nothing; within one call a task's target is resolved once for each distinct asker.

`is_asker`: the session is `target_of(task).session`; or the task has a thread and the session is that thread's current session; or the task has no thread and the session is `askers[0].session`. Nothing else: not an equal `thread: null`, not a session that once filled the same seat, not a fork.

`cleared`: where `cleared_witness` answers a session left for this start, and `tasks/state.json` exists, and the pair is not already there, it writes the pair, in a step of its own after every thread lock is released. `sminos record` calls it at a clear, and so does `remind` before it prints, since either start hook can run first and the record hook's own work can be cut short; both read the same witness, which stays until the daemon sweeps it.

### §3 · The commands (X2, X3, X5)

    sminos task assign --class C --title T [--body-file F|-] [--due D|--no-due] [--tag x]… [--asker-agent ID] [--asker-name N]
    sminos task revise <id> [--title T] [--body-file F|-] [--class C] [--due D|--no-due] [--tag x]… [--no-tags]
    sminos task comment <id> (--body-file F|- | "text")
    sminos task withdraw <id> [--reason "…"]
    sminos task reopen <id> --comment "…"
    sminos task show <id>[@<revision>] [--json]
    sminos task list [--closed|--all] [--mine] [--json]
    sminos task done <id>[@<revision>] [--note "…"] [--wake|--no-wake]
    sminos task decline <id>[@<revision>] --reason "…" [--wake|--no-wake]
    sminos task act                                   # the door: D4's lines on stdin, a verdict a line on stdout
    sminos task remind --session <id> [--source S]    # the start line: what the SessionStart shell hook prints; nothing when there is nothing
    sminos task status --session <id> --json          # M4: the mod's own; in no usage text

Registered in `sminos.build_parser()` as `sheet` is (`sub.add_parser("task")`, its `fn` delegating to the tasks' module through `sibling_module`). The verbs given `--session` are dispatched ahead of the migration as the sheet's `--session` verbs are: a session's hooks call them.

- A verb's role is its caller's: `assign`, `revise`, `withdraw` and `reopen` need `CLAUDE_CODE_SESSION_ID` (exit 3 without: only a session assigns); `done`, `decline` and `act` refuse it (exit 3); `comment`, `show` and `list` serve both, `comment` without a session going through the door as the human's. `done`, `decline` and the human's `comment` are the door's lines made for the caller, with a UUID the command mints, so the command line is a surface like any other.
- Exits: 0 done; 1 the store could not be read or written, or is of a newer `version` than this command writes; 2 usage or a field out of bounds; 3 refused by a rule, or no such task; 75 the lock not had in 10 s. `act` exits 0 when every line got a verdict.
- `list` without `--json`: one line a task, blocking first, then needed by due date (undated last), then optional, each `t7  blocking  "Log in to the console"  <project>  alpha (stopped, to be woken)  due 2027-01-05  Updated`. Text an agent wrote is printed as `sminos sheet show` prints a question's (control characters out, a line break a space) so no title reads as another row.
- `show` is a read: it changes no task and no outcome, for any caller, and reads a store of a newer version too. Without `--json`: the head line, the body, then one history in the store's order: each comment with its author and time, and each act of the human with its word and its text (`done  2026-11-27 16:40  "logged in with account B"`). The human's reading clears "Updated": the command line's `show`, when it has no session, sends the door's `seen` after printing, a separate step.
- `--json` prints X1's `list` and `show` models: the task as stored, and beside it `target` (`target_of`'s answer) and `updated` (a boolean).
- `remind` first registers a witnessed clear's pair (§2). Then it prints, for the session's own target: `Tasks you assigned to the human: 2 open (1 blocking).` and, for each unannounced outcome whose intention is `start` or is older than a minute (first twenty, then a count), one line of §5's start form; for `--source fork`, when the store holds any open task, D9's sentence. Then it marks what it printed announced, by `start`. Nothing where there is nothing.

**The door's decision** (the composite's D5 table, as code reads it). The outcome's `wake` is resolved in the step that applies the act: the line's `wake` when it is not null, else whether the task is blocking. Let `urgent` be: the act is a `done` or a `comment`, or a `decline` of a blocking task, or the line's `wake` is true. From `target_of`:

| the target | condition | `intends` | `told` |
|---|---|---|---|
| `running` | `urgent`, and it is a member of a project | `tell` when the task names a subagent, the target's `runner` is `terminal` and its bridge socket is there; else `notice` | `now` |
| `running` | otherwise | `start` | `next-start` |
| `stopped`, `runner` `terminal` | the outcome's `wake` is true, and it is a member of a project | `notice` | `wake` |
| `stopped`, `runner` `terminal` | otherwise | `start` | `next-start` |
| `stopped` or `gone`, `runner` `maws` | the outcome's `wake` is true | `start` | `maws` |
| `ended` | — | `start` | `ended` |
| anything else (`gone`, `unknown`, `maws` without a wake) | — | `start` | `next-start` |

**Until M2 is installed** nothing is pushed: M1's door records `start` for every outcome and answers `next-start`, or `ended` for an ended target. The set's schema carries all five `told` values and all three intentions from G1.

In the `task` plugin (M3), each of D2's verbs runs the matching `sminos task` verb (`assign-human` → `assign`; `list --human` → `list`), found as the ticket verbs find `sminos` (`TASK_SMINOS`, the PATH, the marketplace clone; 30 s), its stdin, stdout and stderr passed through, its exit kept when it is 0, 2 or 3 and 1 otherwise.

### §4 · What the mod reads (M4)

`sminos task status --session <id> --json`:

    { "v": 1, "seq": 14,
      "open": { "count": 2, "blocking": 1 },                          // this session's target's open tasks
      "mine": [{ "id": "t7", "title": "…", "born": 9 }],              // open blocking tasks this session assigned, newest 50
      "board": { "url": "…" } | null }

`board` is the newest live registration under `tasks/surfaces/` (X4), chosen by the rule the command already has for the sheet's surfaces (heartbeat and pid), given the directory. This answer is the mod's own and is not in the published set.

### §5 · The telling (M2; X6)

The texts, each one line, `<id>` a task's id, `<word>` one of `marked <id> done`, `declined <id>`, `commented on <id>`:

    [tasks v1] The human <word>, a task you assigned. Read it: sminos task show <id>
    [tasks v1] The human <word>, a task assigned by the conversation this one replaced at a /clear. Read it: sminos task show <id>
    [tasks v1] The human <word>, a task your subagent <agent id> assigned; it has ended. Read it: sminos task show <id>
    Since you were last here the human <word>. Read it: sminos task show <id>                                  (the start line's form)
    tasks: <id> was <completed|declined|commented on>; its asker <alias> has ended. The outcome is on the board: sminos task show <id>     (the ended line)

    announce(task id, key) -> None                  # tasks' module; called by the door after its replace, and by the tick
    notice_once(project, to_session | None, text, identity) -> answer      # S/sminos.py: factored from `say --notice`'s path
    tell_agent(session, agent id, text) -> True | False | None             # tasks' module, over sminos_control.post_command

`announce` does what the outcome intends, with the store's lock not held, then records the result in one step that first reads the outcome again and changes it only if it still intends the same:

- **`tell`**: `tell_agent` posts the bridge's `tell` op (`{"op": "tell", "agentId": …, "resolvedAgentId": …, "text": …}`) to the session's bridge socket, as `sminos_sheet.nudge` posts its op, bounded at 10 s. True (the bridge answered ok): `announced`, by `tell`. False (it refused: the agent ended or is unknown, the session's bridge is an observer's) or None (no socket, no answer in time): the intention becomes `notice`, its text the subagent-ended form, and `announce` goes on with it in the same call. A `tell` that got no answer may have been delivered: the subagent and its thread can both be told, once each.
- **`notice`**: `notice_once` with the text, the target's session and project, and the identity `tasks:<key>`. Its answer is kept. `sent`, `woken`, a `held:<why>` and an answer that the event is owed (gated, pending behind another) all mean sminos has it: `announced`, by `notice`. An answer that sminos will not deliver it (`recorded`: the thread ended, the member retired, a lane B session whose process went) or could not write it (`failed:<why>`) sets `intends: "start"`.
- **`start`**: nothing to do; `remind` prints it.
- **The ended line**, for an outcome whose target is `ended` and whose `endedLine` is null: `notice_once` with the ended line's text, no recipient, the target's project and the identity `tasks:<key>:ended`; then `endedLine` is set. Where the target has no project it is marked with nothing written.

`notice_once` is what the door and the daemon need of `cmd_say`'s notice path and nothing else. It appends one `human` event with `notice: "tasks"` in `project`, addressed to one session by its id (never by resolving an alias) or to nobody, carrying the identity as its `src`; under the writer's log lock it looks for that `src` in the writer's log and in its queue of events waiting for the writer's head (a newly enrolled machine's writer queues instead of appending), and writes nothing when either holds it. For an addressed one it then delivers as a sender's own call does (`deliver_next(..., due=True)`), and answers that delivery's outcome for the event; `sent` when the identity was already there. It prints nothing and never exits; what `cmd_say` would die for (no writer a notice is read under, a recipient that is no member of the project, a log that refuses) it answers as `failed:<why>`. Whatever locks the delivery takes are taken with the store's lock not held.

`sminos_daemon.sweep_tasks()`, called from `tick_all`: it reads the store when the file changed since its last look and keeps the outcomes whose intention is `tell` or `notice` and has no result, and those due an ended line. At each tick it calls `announce` for each such outcome whose `intendedAt` is more than a minute old (a `tell`'s goes as a notice to the thread: the door that meant to tell is gone). On `override_duty`'s hourly spacing it also looks for outcomes due an ended line (a thread's end changes no file here), removes each closed task whose `closed.at` is more than 30 days old and none of whose outcomes is unannounced, with its `applied` keys, and removes each successor pair that is in no task's chain. Any exception is a line in `daemon.log` and the next tick's work.

### §6 · The tasks' mod (M4)

    // H/tasks-model.tsx — no `$`
    export function attribute(command: string, agentId: string, name: string | undefined): string | undefined   // the changed command, or undefined for no change
    export function statusOf(stdout: string): Status | undefined
    export function taskBandLine(open: { count: number; blocking: number }, board: { url: string } | null): string | undefined
    // H/tasks.tsx
    export function registerTaskAttribution(on: On): void     // first in H/register.tsx
    export function registerTaskBand(on: On): void            // beside registerSheetBand
    export function registerTasks(on: On): void               // after registerSheet

`H/register.tsx` after M4 registers, in order: the attribution, the bridge, the backtick guard, the sheet's band, the tasks' band, the ask's band, the sheet, the tasks, the ask, the address, the name.

## Plan of Work

### M1 — The store, its commands, the door, the start line, the published set (G1)

**At its end.** From a session's shell, `sminos task assign` puts a task in the machine's store and prints its id; `revise`, `comment`, `withdraw` and `reopen` change it under D2's rule of who may; from a terminal that is no session, `sminos task list` and `show` read the board with each task's target and its state, and `done`, `decline` and `comment` act through the door, which refuses a stale revision, applies an act once by its key, and refuses a session. Every human act leaves an outcome, and the asker is told of it at its next start by a line of its own, then reads the human's words with `show`. A `/clear` sminos witnessed makes the new session the task's target. `sminos/types/tasks/` is published at version 1 and the commands are held to it.

**Touches.** New `S/sminos_tasks.py`; `S/sminos.py` (the parser's `task` family, the early dispatch, the usage text, the call from the record hook's path where `cleared_witness` answers); a new SessionStart shell hook beside `sminos/hooks/smns-guide.sh`, and `sminos/hooks/hooks.json`; new `T/tasks-contract.gen.py`, `sminos/types/tasks/` (written by it), `T/test_tasks_contract.py`, `T/test_tasks.py`; `T/run-sminos-tests.sh` (the two suites, in the list with room); `S/CLAUDE.md` (a paragraph, as the sheet has one); `sminos/hooks/CLAUDE.md`; `sminos/CLAUDE.md` (one sentence and the pointer); sminos's version.

**Interfaces.** Exposes §1, §2, §3 (all but `status`) and the store's steps to every later milestone, and X1, X2, X3 to B1a, B2 and B3. Consumes sminos's threads (`threads.current_record`, `get`, `thread_of`, `record_ended`), `sminos_records.lane_of`, `running_now`'s reading of the engine's records, `wake_here`, `cleared_witness`, `member_row`, `flocked`, `write_json`, `json_at`, all as built.

**Decisions.**
- The generator comes first and is written by hand from the composite and §1 to §3 and §5's texts: schemas, the texts' grammar with an example of each form, and at least these fixtures (an assign that makes the store; a second; a revise; a done at the current revision; a done at an old one, `stale`; a decline; a comment by the human; the same line twice under one key; another line under that key, `key-reused`; a `seen` naming an older `seq` than a later revise, which stays Updated; a withdraw; a reopen; an act on a closed task; an unknown field kept through a write, at the top and on a task; a successor's pair; a `remind` that prints and marks; an outcome for each `told` and each intention, so the shapes M2 fills are frozen now).
- A writer never rebuilds a task from the fields it knows: it changes the parsed object in place.
- `target_of` is one function used by `list`, `show`, the door's decision, `is_asker`, `remind`, and later the telling and B1a's predicate, so the card, the verdict, the rights and the telling cannot disagree about whom a task answers to.
- The door reads all its lines and checks each against the line's schema before applying any: a call with one bad line applies nothing (exit 2). Each line's step is its own replace.
- The start line is the tasks' own and is not inside `guide_text`: a SessionStart shell hook of its own, beside `smns-guide.sh` and not behind its enrollment test, runs `sminos task remind` with the payload's session and source when `tasks/state.json` exists and `SMNS_INTERNAL` is unset, whether or not the machine is enrolled and whether or not the session is a member, and prints what it answers, which the engine adds to the session's context as it adds the guide's. It starts no Python where there is no store, prints nothing on any failure, and never blocks a start.
- `remind` prints first and marks after, so a death between the two tells twice and never loses. It prints an outcome that intends `tell` or `notice` only when that intention is more than a minute old, so it does not race a door that is about to tell.
- The lock is `fcntl.flock`, exclusive, 10 s, the file never unlinked (the sheet's kind); the replace is a synced temporary file in `tasks/` and `os.replace`.
- Pitfalls seen in the code: `S/sminos.py`'s `main` runs `migrate()` before most verbs, and a hook's call must not wait on it (§3's early dispatch); `members()` and `view_of()` write, so nothing here calls them; `running_now` reads the engine's records afresh at each call, so a `list` of many tasks reads them once and shares the reading.

**Does not touch.** The `task` plugin, any mod, the daemon, `notice_once`, the bridge, the ending pass, anything of the sheet's.

**Proves.** The composite's A1, A2's list, A3, A5 and A8's first sentence in their `sminos task` form (the verbs' names in `task` are M3's; the line and the notification are M4's), and X1 to X3. Its tests pin, beyond acceptance: two `assign`s at once from two processes get two ids and neither is lost; a kill between the temporary file and the replace leaves the store as it was; the same line twice changes nothing and answers the first verdict, `told` included, with the target's state changed between the two; a command of version 1 that waits for the lock behind a writer of version 2 refuses once it reads the file, and `show` and `list` still read it; `is_asker` true for the target and the thread's current session, false for a second session with no thread, for a fork, and for a session that filled the seat before; `target_of` for a running thread, a stopped one, a held one, an ended one, a cleared one with a running successor, with a stopped successor, with an ended successor, cleared twice, cleared forty times in a row (the last living one), a pair that loops, the left session opened again, a session that took the left one's alias and is no successor, a session with no thread, a session that assigned with no thread, later became a member and was cleared (its successor is neither the target nor the asker), a lane B session with a thread record, and a record that cannot be read; the pair is written once whichever of `sminos record` and `remind` runs first, and by `remind` alone when the record hook was cut short; a session at the door exits 3 and changes nothing; the 501st open task is refused, by `assign` and by `reopen`; two acts in one millisecond keep their order by `seq`; `show` prints a done's note and a decline's reason and writes nothing; `remind` for nothing, for open tasks, for an unannounced outcome (printed once, not at the next start), for a fork, on a scratch home with no enrollment, and killed after printing (printed again); no text `remind` prints holds a task's title or body; every published fixture replays.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,version-bump`.

### M2 — Telling the asker now: the notice, the subagent's message, the wake

**At its end.** A done, a comment or a decline of a blocking task reaches a running asker at once: sminos delivers the board's notice, an idle session starting a turn with it and a busy one reading it at its next tool round. A stopped thread is woken for it when the human's choice says so, or held with sminos's reason, and otherwise waits for its start line. A running subagent that assigned the task is told itself. An ended thread's outcome leaves one line in its project's log. The door's `told` says `now` and `wake`, and the task shows what sminos answered. A closed task whose asker has been told goes after 30 days.

**Touches.** `S/sminos_tasks.py` (the door's decision, `announce`, `tell_agent`, what `show --json` adds); `S/sminos.py` (`notice_once`, factored from `cmd_say`'s notice path so both use it); `S/sminos_daemon.py` (`sweep_tasks`, its place in `tick_all` and the hourly duty); `T/test_tasks_telling.py`; `T/run-sminos-tests.sh`; `S/CLAUDE.md`; sminos's version.

**Interfaces.** Exposes §5 to M4 (the `tell` path is exercised live there), to B1a (an outcome's notice and its act's time) and to B3. Consumes M1's store, `target_of` and the frozen shapes; `cmd_say`'s notice path, `deliver_next`, `wake_here`; `sminos_control.post_command` and the bridge's `tell` op as built.

**Decisions.**
- `notice_once` is made by taking apart what `cmd_say` does for `--notice`, so that `say --notice` and the board's notices append and deliver through one path; `cmd_say`'s own behaviour and `T/test_notice.py` stay as they are.
- The board keeps no record of delivery beyond sminos's answer at the moment of sending: whether a held notice was later delivered is sminos's delivery record's to say, and `show --json` reads it from there for the card (the event's place in the writer's settled prefix) and does not copy it.
- A `tell` is tried only for an outcome the table sends now, to a subagent of a running `terminal` session; everything else about a subagent's outcome is the thread's.
- U2's live check is made here, by hand, on a machine whose installed sminos is this branch (a background wake does not carry `--plugin-dir`, so a scratch home with the branch loaded by flag proves nothing about a woken thread): (a) an idle session whose task is completed starts a turn whose first message is the notice; (b) a spawned seat assigns a blocking task and is stopped, `sminos task done` answers `wake`, and the seat runs with the notice its first message; (c) a session that bypasses permission prompts receives the notice without the engine holding it for approval; (d) where a machine cut over to the reach and words gates is at hand, the same, the answer read as it comes. The check reports a setup that did not load this branch as its own failure, apart from the product's. A seat that a notice alone does not wake, or a frame the engine holds, stops the milestone and goes to the composite's writer.
- Pitfalls seen in the code: `say --notice` is refused when a session's id is in the environment and when the machine's name is not one a notice is read under; the door is never a session, and the second is a `failed` answer. `say --notice` tagged to an ended thread exits 4 with nothing appended, which is why the ended line is untagged. A notice's recipient must be a member of the project it is written in: the project is the target's membership now, not the task's `project` at its assign.

**Does not touch.** Any mod; the bridge's `tell` op itself; `deliver_next`; the ending pass (B1a's); anything of the sheet's.

**Proves.** A4 (the verdict, the notice in the log without the note, sminos's answer on the task), A6 and A8's second and last sentences in their command form, and X6. Its tests pin: the door's decision for each row of §3's table, each kind and class, and each of `wake` true, false and null; the notice's text for each form, and that none holds the task's title, body, an agent's comment or a subagent's name; an addressed notice wakes a stopped thread once and the outcome keeps `woken`; a held thread keeps `held:<why>` and stays announced; an answer of `recorded` makes the outcome unannounced again and `remind` prints it; a notice is written once by the door and the tick together, by two ticks at once, and after a kill before and after the writing (one event in the log); two writers of one identity while the writer's log waits for its head leave one queued event; a `tell` the stand-in bridge accepts announces by `tell` and writes no notice; a `tell` it refuses, one with no socket, and one that times out each go on to the notice with the subagent's id in it; a `tell` is not tried for a MAWS-run session or for an outcome that waits; an intention left by a killed door is finished by the tick after a minute and not before; the ended line is written once, for a needed task completed with no wake asked too, and by the tick when the door was killed; a closed task 31 days old with an unannounced outcome stays and one with none goes with its keys; `say --notice` behaves as before (`T/test_notice.py` unchanged).

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-idle,version-bump`.

### M3 — The `task` verbs

**At its end.** `task assign-human`, `task show t7`, `task comment t7`, `task list --human`, `task revise`, `task withdraw` and `task reopen` do what the matching `sminos task` verbs do, from any directory; `task assign-human` no longer says the Task Board is not built.

**Touches.** In `task/`: the dispatch and its verbs' front (`task/cli/`), `task/tests/` (its stand-in `sminos` answers the `task` verbs), `task/CLAUDE.md`, the plugin's version.

**Interfaces.** Exposes X5's names in `task`. Consumes §3 from M1, and the `task` plugin's dispatch and its way of finding `sminos` as built.

**Decisions.**
- The human's forms are recognized first in the dispatch, before the ticket board's configuration is read or `gh` is looked for: `assign-human`, `revise`, `withdraw`, `reopen`; `show` and `comment` whose first argument is whole `t[1-9][0-9]*`; `list` with `--human`. The board is the machine's, so they work outside any repository and with the ticket board unconfigured.
- The three branches in the ticket verbs' dispatch are made as the ticket board's writer agreed them (X5); if that agreement names other verbs, the composite's writer rewrites D2 first and this milestone follows the rewrite.
- A heredoc's standard input reaches `sminos task` unchanged; the front reads none of it.

**Does not touch.** The store's commands' behaviour, the ticket verbs' own behaviour, sminos.

**Proves.** A1 in its `task` form. Its tests pin: each verb passes arguments, standard input, output and exit through and maps other exits to 1; where `sminos` is not found it exits 1 saying the human's board is kept by sminos; `task show t7` and `task assign-human` with a heredoc work in a directory that is no repository and with no board configured; `task show 7` is still the ticket's; `task revise 7` exits 2.

**Gate.** `ci-gate --gates task,version-bump`.

### M4 — The session's side: the subagent's attribution, the terminal's line, the notification

**At its end.** A task a subagent assigns names the subagent, and the person approving the call sees the flag that says so; completed while that subagent runs, the subagent itself is told. The line above the prompt counts the session's open tasks; a new blocking task raises one notification on the machine.

**Touches.** New `H/tasks.tsx`, `H/tasks-model.tsx`; `H/backticks.tsx` (the lexer keeps where a literal word starts and ends in the command); `H/register.tsx`; `S/sminos_tasks.py` (`status`); new `T/mods/tasks-model.test.ts`, `T/mods/tasks-attribution.test.ts`, `T/mods/tasks.test.ts`, `T/mods/live-tasks-check.py`; `T/test_tasks.py` (`status`); `H/README.md` (a section "tasks"); sminos's version.

**Interfaces.** Consumes §3 and §5 from M1 and M2, `backticks.tsx`'s lexer. Exposes nothing later milestones consume.

**Decisions.**
- **The attribution.** `attribute` uses `backticks.tsx`'s lexer and no second one. The lexer today keeps a word's decoded text; it is taught to keep, for a word that is literal in the command (no quote, escape, expansion or continuation inside it), where it starts and ends in the command's bytes, in the outer command and inside a list, and nothing for a word inside a substitution or a heredoc's body. `attribute` finds each simple command whose command word's last path part is `task` followed by the literal word `assign-human`, or is `sminos` or `sminos.py` followed by `task` and `assign`, and inserts the flag after the verb's end, working from the command's end backwards so earlier positions stay true. A command the lexer gives up on, a verb that is not a literal word, and a command that already carries `--asker-agent` are returned unchanged. The hook acts only where `e.tool` is `Bash` and `e.agentId` is present and whole by D2's pattern; it calls `next({ ...e, command })` and returns what that returns; its `.catch` passes the call on unchanged, since a failure of the hook must never stop a command. The name comes from `$.agent.list()` at the call; a list that cannot be read gives the id alone.
- **When the mod reads.** At a start; at every tool call, prompt and turn's end the mod sees and on a 5 s timer, when one `$.fs.stat` of `tasks/state.json` differs from the stat of the last read that answered; and every twelfth tick regardless, since a surface's registration changes without the file changing. One `sminos task status` at a time; a read asked for while one runs makes one more after it.
- **The notification.** A task in the answer's `mine` whose `born` is above the `seq` of the first answer this process adopted raises `$.ui.notify` with its title, once a task (it is shown to the human, as a question's is, and to no agent). Nothing for tasks that were open at the start.
- **The line.** `registerTaskBand` draws `2 tasks for the human (1 blocking) · <address>` through `ui.render` for `AbovePrompt`, beneath the sheet's line, not while a survey holds the band; the address is the answer's `board.url`, else `sminos task list`.
- In a session where function hooks are off none of this runs: a task there names no subagent, and its outcomes are told as any are. A session marked `SMNS_INTERNAL` registers nothing.
- **The live checks** (U1, and A7). `live-tasks-check.py`, in the manner of the other `live-*` checks: it drives real sessions and spends model calls, so it is run by hand and not in a gate. Cases: `attributed` (U1: a subagent's `task assign-human` or `sminos task assign` under an allow rule for the verb, one under a rule that names arguments, one with a classic `PreToolUse` hook that prints its input, and one whose command also holds a secret's handle, each observed and written down as found), `subagent` (A7: completed while the subagent runs, the message is in the subagent's transcript and absent from the main one; completed after it ended, the notice in the main conversation names its id). What `attributed` shows is written beside D2 by the composite's writer.

**Does not touch.** The store's rules; the door; `notice_once`; the bridge; anything of the sheet's beyond reading how its band is drawn.

**Proves.** A2's line and notification, and A7. Its tests pin: `attribute` on a plain call, one with a heredoc body, one in a list (`a && task assign-human … && b`), two assigns in one command (both changed), the verb's text repeated inside a quoted argument (only the command changed), a quoted `task assign-human` inside an `echo` (unchanged), a verb split by a quote or a continuation (unchanged), a trailing comment, a path-qualified `task`, a command inside `$( … )` (unchanged), an id that fails the pattern (unchanged), a teammate's id, a name with spaces and quotes (reduced), a command already carrying the flag (unchanged), and a command the lexer gives up on (unchanged); the hook on the main loop changes nothing; the hook's failure passes the call on; the notification once a new blocking task and never at a start; the band's text for none, open, blocking, and with a board's address; a failed read is tried again at the next look.

**Gate.** `ci-gate --gates sminos,sminos-mods,mods-types,version-bump`, and `live-tasks-check.py`'s cases by hand, their result in the pull request.

### M5 — What agents are told, what is written beside the code, the acceptance

**At its end.** An agent that has never seen this feature learns from its start guide that the human's board exists and when to use it, and from the skill how; the repository's own accounts name the store, the door and the notice where their code is; the composite's A1 to A8 have been run as written on a Mac with the released plugins.

**Touches.** New `task/skills/human-tasks/SKILL.md` (through doperpowers:writing-skills); `S/sminos.py` (`guide_text`: the teaching line); `task`'s help text; `sminos/skills/sminos/SKILL.md` (one pointer); `docs/whats-inside.md` (the skill's row; sminos's row); `sminos/README.md`, `sminos/CLAUDE.md`, `task/CLAUDE.md`; the root `CLAUDE.md`'s `task/` row if the ticket board's landing did not already carry the human's board; both plugins' versions.

**Interfaces.** Consumes X7 from B5 (the words), and everything built.

**Decisions.**
- The skill's body, the guide's line and the help text carry the words B5 passed, unchanged. Where B5's result differs from the composite's D2 list, the composite's writer has rewritten D2 before this milestone starts.
- The skill follows the repository's rule for skills: only what the reading model cannot derive. The verbs' flags are the help text's, not the skill's.
- The teaching line is the guide's (`guide_text`), for a session that is a member on an enrolled machine; the facts of what is open and what the human did stay M1's start line, which needs neither.
- The sentence for the question tool's description is not shipped here: it is the sheet's holder's to place.

**Does not touch.** Behaviour. A defect the acceptance finds goes back to the milestone that owns it, as a fix on a branch of its own.

**Proves.** A1 to A8, by Concrete Steps' acceptance run, on the released plugins (A8's three-day part once B1a has landed).

**Gate.** `ci-gate` whole, from the worktree.

## Concrete Steps

Every command runs from the repository's root in the milestone's worktree unless it says otherwise. The suites below are one focused file each, for iterating; a commit is verified by its milestone's `ci-gate` line. A scratch store: `export SMINOS_HOME="$(mktemp -d)"`.

**M1.** The generator, then the suites:

    python3 -B sminos/tests/tasks-contract.gen.py            # writes sminos/types/tasks/
    python3 -B sminos/tests/tasks-contract.gen.py --check    # exit 0: the set is the generator's
    python3 -B sminos/tests/test_tasks_contract.py
    python3 -B sminos/tests/test_tasks.py

By hand, with a scratch store and a stand-in session id:

    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task assign --class blocking --title "Log in to the console" --body-file - <<'EOF'
    Open the console and sign in. Done when the dashboard loads.
    EOF
    # t1 blocking "Log in to the console"
    sminos/bin/sminos task list
    # t1  blocking  "Log in to the console"  …  (gone)  due —
    sminos/bin/sminos task done t1 --note "logged in"
    # {"v":1,…,"task":"t1","verdict":"applied","revision":1,"state":"done","outcome":"t1.1","told":"next-start"}
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task done t1; echo $?
    # … an agent's session does not complete the human's task …   3
    sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # Since you were last here the human marked t1 done. Read it: sminos task show t1
    sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # (nothing: it was said)
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task show t1
    # … done  <time>  "logged in"

**M2.**

    python3 -B sminos/tests/test_tasks_telling.py
    python3 -B sminos/tests/test_notice.py                   # unchanged, and passing

**M3.**

    bash task/tests/run.sh

**M4.**

    bash sminos/tests/mods/run.sh
    python3 sminos/tests/mods/live-tasks-check.py attributed subagent    # spends model calls; by hand

**The acceptance (M5)**, on a Mac whose daemon serves the home in use and whose installed plugins are the released ones, in a scratch project; none of it on a scratch store. Each step is the composite's item of the same number.

1. In a terminal session, ask the agent to run in one Bash call, each command under `time`:

        time task assign-human --class blocking --title "Log in to the console" --body-file - <<'EOF'
        Sign in to the cloud console. Done when the dashboard loads.
        EOF
        time task assign-human --class needed --due 2027-01-05 --title "Rotate the signing key"

    Expect two lines, `t<n> blocking "Log in to the console"` and `t<m> needed "Rotate the signing key"`, each `real` under one second, and the turn going on.
2. In another terminal: `sminos task list`. Expect the blocking row first, each with the project, the session's alias and `(running)`, and `due 2027-01-05` on the needed one. In the session's terminal, expect `2 tasks for the human (1 blocking) · sminos task list` above the prompt, and one notification on the machine, for the blocking task.
3. Close the session's terminal. Run `sminos daemon tick` twice, then `sminos task list`: the blocking row reads `(stopped, to be woken)`.
4. `sminos task done t<n> --note "logged in with account B"`. Expect `"told":"wake"`. Then `sminos list` shows the session running in the background; its transcript's first new message is the `tasks` notice (`[tasks v1] The human marked t<n> done, a task you assigned. …`) and holds no title; the session runs `sminos task show t<n>` and its output holds the note; `sminos task show t<n> --json` shows the outcome announced by `notice` with the answer `woken`; `sminos chat` for the project shows one `tasks` notice and not the note.
5. Tell the session (`sminos say @<alias> …`) that the console still asks for a login. Expect it to run `task reopen t<n> --comment "…"`; `sminos task list` shows `t<n>` open, `Updated`. `sminos task done t<n>` answers `stale` with revision 2.
6. In a second session: assign a needed task, `/clear`, go on in the same terminal. `sminos task show` of it names the new session as its target. Rename a third session to the cleared one's old alias. `sminos task done --wake` of the task. Expect the notice in the new conversation with `a task assigned by the conversation this one replaced at a /clear`, no background process for the cleared one, and nothing in the third session.
7. Have a session dispatch a subagent that assigns a task and keeps working. `sminos task show` names the subagent. `sminos task done` while it runs: the message is in the subagent's transcript and the main transcript holds no `[tasks v1]` line for that task. Repeat with the subagent ended: the notice is in the main conversation, naming the subagent's id.
8. Stop a session that has a needed task and complete the task with no flag: `"told":"next-start"`, no background process; open the session again: its first context holds `Since you were last here the human marked t<k> done`, and no notice arrives. In an idle session, decline an optional task: no turn starts. Then, with B1a landed and `SMINOS_THREAD_END_AFTER` set to a minute: a stopped thread with an open blocking task is still there after an ending pass (`sminos daemon tick`), with one line in `daemon.log`; decline the task with `--no-wake` and the next pass ends it; a stopped thread with only a needed task is ended, and completing that task answers `"told":"ended"` with one `tasks:` line in the project's log.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

Nothing yet.
