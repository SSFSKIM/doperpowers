# Task Board, B1 — the store, the door, the envelope and its delivery, the verbs: execution (2026-11-27)

> **Composite:** `docs/doperpowers/specs/2026-11-27-task-board-design.md`, child **B1**. **Parent pin:** `d0272fddf` (branch `task-board-spec`). The child's section in the composite ("### B1: …") is its spec; the composite's D1 to D6, D8 and D9 are its design, binding where they are marked, and X1 to X4, X6 and X7 the contracts it owns. This document carries the constraints, the decisions the composite did not carry, the interfaces and the milestones, and restates nothing of the design.
>
> **Written against:** this repository's `main` at `40b79a7d1` (the question sheet's C2 whole, sminos 1.59.0); `ticket-board-spec` at `143552115` (the `task` plugin specified, not built); MAWS's `question-sheet-c5` at `2a8ef52ee` (the sheet's C5 plan, whose M1 changes the routes M3 moves).
>
> **Read before M1:** the composite whole; `sminos/hooks/mods/README.md`, "sheet"; `sminos/skills/sminos/scripts/CLAUDE.md`, the question sheet's paragraph and the threads' (the record, the wake, `/clear`); in `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`, I7 (the envelope and its budget), I9 (delivery) and I11 (the mod's layout); `sminos/types/sheet/README.md`, as the model of a published set.

## Progress

- [ ] The owner's read of the composite (nothing starts before it).
- [ ] M1 — The store, its commands, the door, the start line, the published set (gate G1).
- [ ] M2 — The `task` verbs. Waits on the `task` plugin's first release.
- [ ] M3 — The routes, shared: `delivery.tsx`. Waits on the sheet's holder's agreement and on the sheet's C5 M1 pull request on `main`.
- [ ] M4 — What is owed: the envelope, the receipts, the wake.
- [ ] M5 — The session's side: the tasks' source, the subagent's attribution, the terminal's line, the notification.
- [ ] M6 — What agents are told, what is written beside the code, the acceptance. Waits on B5.

## Words this document adds

- **Target**: the session a task's outcomes go to now, with its thread, state and controller; computed at each read from the task's asker (§2), never stored.
- **Attempt**: one wake asked of sminos for an outcome, for one stop of its target (§5).
- **G1**: the gate M1 closes: the set `sminos/types/tasks/` published whole at version 1, which MAWS's children pin.
- **The tasks' module**: `sminos/skills/sminos/scripts/sminos_tasks.py`. **The tasks' mod**: `sminos/hooks/mods/tasks.tsx` with `tasks-model.tsx`.
- **H/**: `sminos/hooks/mods/`. **S/**: `sminos/skills/sminos/scripts/`. **T/**: `sminos/tests/`.

## Verification

This document had one `doperpowers:adversarial-reviewer` buildability review with the composite's design review, and one review of the repair. On the branches, through doperpowers:review-code: the pull request that holds M3 and the one that holds M4 and M5 at the **high** rung (a mistake in a route loses or doubles a delivery, in the sheet as well as here); M1, M2 and M6 at **medium**. M3's pull request is also read by the sheet's holder before it merges. Each milestone's own gate is in its entry; gates run through `ci-gate` on the committed head, never on this machine.

## How it lands

Five pull requests, each from a worktree of its own branched from `main`, each raising the version of every plugin whose shipped files it touched (`scripts/bump-version.sh --plugin sminos`, `--plugin task`; `scripts/bump-version.sh --since origin/main` before a push), each body ending with the session line.

| landing | holds | waits on | what a user has after it |
|---|---|---|---|
| L1 | M1 | the owner's read | tasks assigned with `sminos task assign`, listed and completed from a terminal; the asker is told of outcomes by its start line and reads and acknowledges them by command. Nothing is pushed, and the door says so: `told` is never `running` or `wake-asked`. G1. |
| L2 | M2 | L1; the `task` plugin on `main` | `task assign-human` and the other verbs |
| L3 | M3 | the holder's agreement; the sheet's C5 M1 on `main` | nothing new: the sheet delivers as before, from a shared module |
| L4 | M4, M5 | L1, L3 | the outcome arrives in the asker's conversation; a stopped asker is woken; a subagent's task names it; the terminal's line |
| L5 | M6 | L2, L4, B5 | the skill and the start guide's words; the acceptance run |

L4 needs nothing of the `task` plugin: every text the store composes names `sminos task`, and M5's attribution recognizes both commands. M4 touches nothing of the sheet's and may be built while L3 waits; it lands with M5. An outcome left owed under L1 is delivered by an envelope once L4 is installed, which at-least-once allows. A milestone that waits is not started early on a guess of what it waits for. The session that holds the composite dispatches a `doperpowers:plan-executor` for each landing as it becomes free.

## Constraints on every milestone

- **Python 3.9, standard library only**, as every sminos script is; the mods are TypeScript checked by `tests/mods/typecheck.sh` (the `mods-types` gate).
- **Only the command writes the store.** A hook can neither lock nor replace a file (the sheet's K1): the mod orders `sminos task …` through `$.process.run` and keeps what it answered.
- **The store's lock is a leaf, with one exception.** Whoever holds `tasks/.lock` takes no other lock of sminos's, reads thread records only through reads that write nothing (`sminos.member_row` and the threads' module's getters, never `members()` or `view_of()`, which finish journals and append), and appends to no log. The exception is the ending pass (B1a), which takes the store's lock and then a thread's record.
- **`$` crosses no import.** A mod reaches the engine through closures made inside its own hooks (the sheet's `Port` pattern in `H/sheet.tsx`), so a test hands its own.
- **Nothing submits a prompt inside a hook's dispatch** (the sheet's C0 P1): the idle route goes from a `$.clock.after(0)` hop. M3 moves this rule with the code; M5 adds no submit of its own.
- **A whole value is checked with `fullmatch`**, never `match` against `^…$` (`sminos/CLAUDE.md`).
- **Nothing new at the root of `$SMINOS_HOME`**: every sminos reads a `*.json` there as a seat. The store is the directory `tasks/`.
- **The sheet's published set is not touched** by any milestone: `python3 -B sminos/tests/sheet-contract.gen.py --check` passes at every landing.
- **The repository is public.** No hostname, address, account, project id, secret's name or value, local absolute path or session id in code, tests, fixtures, documents or commit messages. Fixtures use the sheet's stand-in ids (`5eed0000-…`) and `{HOME}`.
- **Version bumps** by `scripts/bump-version.sh` only, in the same commit as the change.
- **The composite's binding marks** bind here: D1's line and fields, D2's flag, D3's one store, D4's one door, D5's block and target, D6's nine rules.

## The store's steps

The composite's D5 table is the outcome's state machine; this is what the commands add to it. Every row is one step: take `tasks/.lock`, read `tasks/state.json`, refuse if its `version` is above this command's, change, replace, release; `seq` + 1 when anything changed, nothing written when nothing did. The version is judged on the file read under the lock, in every writing step, the mod's and the daemon's included.

| command | who | refused when | what it changes |
|---|---|---|---|
| `assign` | a session | no session (3); it would make 501 open (3); a field out of bounds (2) | a task at `nextId`, revision 1, open; its asker from the session, its thread and `--asker-agent` |
| `revise` | the asker (§2) | not the asker (3); not open (3); nothing given (2) | the fields given; revision + 1; `agentSeq` |
| `comment` | any session, or the human through the door | closed (3, or verdict `closed`); empty (2) | a comment; from an agent `agentSeq`; from the human an outcome `comment` |
| `withdraw` | the asker | not the asker (3); not open (3) | state withdrawn, `closed` |
| `reopen` | the asker | not the asker (3); not done (3); no comment (2); it would make 501 open (3) | state open; revision + 1; the comment; `agentSeq` |
| `act` `done`, `decline` | the human | a session (3); revision not current (`stale`); not open (`closed`); a key used for another line (`key-reused`) | state; `closed`; an outcome; the verdict kept by key |
| `act` `seen` | a surface | a session (3) | `seenSeq`, to the `seq` the line names when that is higher |
| `act` `delivered` | a deliverer | a session (3); a key that is not owed, or is a subagent's, is passed over | the keys' outcomes `landed`, by `delivered` |
| `ack` | the asker | not the asker (3); a key not owed is passed over | the keys' outcomes `landed`, by `ack` |
| `landed` (M4) | the mod | a key not owed to that session's target is passed over | the keys' outcomes `landed`, by `row` or `send` |
| `reroute` (M4) | the mod | as `landed` | the keys' outcomes' recipient `main`, `was` the agent |
| a wake attempt (M4) | the door, the daemon | §5's conditions, read again under the lock | the attempt on the outcome |
| the successor's pair | `sminos record`, at a witnessed `/clear` | no store yet: nothing is made | `successors[<session left>]` |

**Where a change becomes visible.** At the `os.replace`: a reader sees the state before or after, never between. The door computes a line's whole verdict, `told` included, before its replace, stores it under the act's key in the same replace, and prints it after, so the same line again reads the stored verdict and two callers of one key cannot be answered differently. **What a death leaves.** Before the replace, nothing (a `.tmp-` file the next step removes). After the replace and before a wake attempt, an outcome with an attempt due: the daemon's tick makes it. After a notice is appended and before its attempt is recorded: the next pass's append finds the notice's identity in the log, writes nothing, and records the attempt (§5). No step leaves the store between two of its own states.

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
                         "to": "main" | { "agentId": "…" }, "was": "<agent id>" | null, "acrossStop": true,
                         "wake": { "asked": true, "tries": [{ "session": "…", "stop": "<the stop mark>", "at": "<time>", "answer": "woken" | "held:<why>" | "gated" | "pending" | "failed" }] },
                         "landed": null | { "at": "<time>", "by": "row" | "send" | "delivered" | "ack" } }]
        }
      },
      "applied": { "<act key>": { "task": "t7", "at": "<time>", "digest": "<sha256 of the line as canonical JSON>", "verdict": { … } } },
      "successors": { "<session left>": { "session": "<session begun>", "at": "<time>" } }
    }

A time is ISO-8601 in UTC with milliseconds, for showing; order is by `seq`: `born` is the store's `seq` at the assign, an outcome's `seq` the one at its act, `agentSeq` the one at the last revise, comment or reopen by an agent. A row is "Updated" when `agentSeq` is above `seenSeq`. `acts` counts the human's acts on the task that make an outcome; an outcome's key is `<id>.<acts>` at its act. `project` and `alias` are null for a session sminos knows no project or name for. An object's unknown fields are kept by every writer (D3). The set's serialization, cuts and "always present" readings are fixed by M1's generator, in the manner of `sminos/types/sheet/README.md`'s "Readings fixed with the set".

### §2 · The asker and the target

    asker_of(session, agent=None) -> {thread, session, alias, agent}     # at an assign
    target_of(store, task) -> {session, thread, alias, project, state, runner, wake, why, via}
    is_asker(store, task, session) -> bool

`asker_of` reads the session's thread as `sminos_channels._self` does (`threads.current_record(session, fresh=True)`); a session with no record has `thread: null`.

`target_of` decides whom a task's outcomes go to now. Let `first` be the asker's thread's current session, or the asker's own session for a task with no thread; let the chain be `first`, then `successors[first].session`, then that one's successor, and so on (at most 32 links; a session met twice ends it).

1. `first`, when a process holds it. `via: "self"`.
2. Else the last session of the chain, past `first`, whose thread exists and has not ended. `via: "cleared"`.
3. Else `first`. `via: "self"`.

Then, for the session chosen: `runner` is `maws` when its lane is B (`sminos_records.lane_of` on its record), else `terminal`. `state` is `maws` for a lane B session; else `running` when a process holds it (the engine's records, read once a call and shared by every task of that call); else `ended` when its thread's record has ended; else `stopped` when the record carries a stop mark; else `not-reachable` (no thread, or no stop mark yet). For `stopped`, `wake` and `why` are this machine's own judgement, `sminos.wake_here`. A record that cannot be read gives `state: "unknown"`, which every consumer treats as not running and not to be woken. `target_of` reads with no lock and writes nothing; within one call a task's target is resolved once for each distinct asker.

`is_asker`: the session is `target_of(task).session`; or the task has a thread and the session is that thread's current session; or the task has no thread and the session is `askers[0].session`. Nothing else: not an equal `thread: null`, not a session that once filled the same seat, not a fork.

`sminos record`, where `cleared_witness` answers a session left, calls the tasks' module with the pair (the session left, the session recording); the pair is written when `tasks/state.json` exists and the pair is not already there.

### §3 · The commands (X2, X3, X6)

    sminos task assign --class C --title T [--body-file F|-] [--due D|--no-due] [--tag x]… [--asker-agent ID] [--asker-name N]
    sminos task revise <id> [--title T] [--body-file F|-] [--class C] [--due D|--no-due] [--tag x]… [--no-tags]
    sminos task comment <id> (--body-file F|- | "text")
    sminos task withdraw <id> [--reason "…"]
    sminos task reopen <id> --comment "…"
    sminos task show <id>[@<revision>] [--json]
    sminos task list [--closed|--all] [--mine] [--json]
    sminos task ack <key>…
    sminos task done <id>[@<revision>] [--note "…"] [--wake|--no-wake]
    sminos task decline <id>[@<revision>] --reason "…" [--wake|--no-wake]
    sminos task act                                   # the door: D4's lines on stdin, a verdict a line on stdout
    sminos task remind --session <id> [--source S]    # the start line (M1): what the SessionStart shell hook prints; nothing when there is nothing
    sminos task owed --session <id> [--agents a,b,…] --json        # M4: the mod's and MAWS's; in no usage text
    sminos task landed --session <id> --by row|send   # M4: the mod's: {"keys": […]} on stdin; answers {"v":1,"seq":n,"landed":[…]}
    sminos task reroute --session <id>                # M4: the mod's: {"keys": […]} on stdin; answers {"v":1,"seq":n,"rerouted":[…]}

Registered in `sminos.build_parser()` as `sheet` is (`sub.add_parser("task")`, its `fn` delegating to the tasks' module through `sibling_module`). The verbs given `--session` are dispatched ahead of the migration as the sheet's `--session` verbs are: a session's hooks call them.

- A verb's role is its caller's: `assign`, `revise`, `withdraw`, `reopen` and `ack` need `CLAUDE_CODE_SESSION_ID` (exit 3 without: only a session assigns); `done`, `decline` and `act` refuse it (exit 3); `comment`, `show` and `list` serve both, `comment` without a session going through the door as the human's. `done`, `decline` and the human's `comment` are the door's lines made for the caller, with a UUID the command mints, so the command line is a surface like any other.
- Exits: 0 done; 1 the store could not be read or written, or is of a newer `version` than this command writes; 2 usage or a field out of bounds; 3 refused by a rule, or no such task; 75 the lock not had in 10 s. `act` exits 0 when every line got a verdict.
- `list` without `--json`: one line a task, blocking first, then needed by due date (undated last), then optional, each `t7  blocking  "Log in to the console"  <project>  alpha (stopped, to be woken)  due 2027-01-05  Updated`. Text an agent wrote is printed as `sminos sheet show` prints a question's (control characters out, a line break a space) so no title reads as another row.
- `show` is a read and writes nothing, for any caller, and reads a store of a newer version too. Without `--json`: the head line, the body, then one history in the store's order: each comment with its author and time, and each act of the human with its outcome's key, its word, its text and whether it is still owed (`t7.3  done  "logged in with account B"  owed: sminos task ack t7.3`). The human's reading clears "Updated" through the door's `seen`, which the command line's `show` sends after printing when it has no session.
- `--json` prints X1's `list` and `show` models: the task as stored, and beside it `target` (`target_of`'s answer) and `updated` (a boolean).
- The verdict of the door: D4's shape. `told` is decided in the step that applies the act, from `target_of`: `maws`; `ended`; `not-reachable`; for `running`, `running`; for `stopped` or `unknown`, `wake-asked` when the outcome's `wake.asked` is true, else `next-resume`. **Until M4 is installed** nothing pushes and nothing wakes, so M1's door answers `next-resume` wherever M4's will answer `running` or `wake-asked`; the set's schema carries all six from G1.
- `remind` prints, for the session's own target: `Tasks you assigned to the human: 2 open (1 blocking).` and, for each outcome owed to it (first twenty, then a count), `Not yet delivered: t7.3 done. Read: sminos task show t7. Then: sminos task ack t7.3`; for `--source fork`, when the store holds any open task, D9's sentence. Nothing where there is nothing.

In the `task` plugin (M2), each of D2's verbs runs the matching `sminos task` verb (`assign-human` → `assign`; `list --human` → `list`), found as the ticket verbs find `sminos` (`TASK_SMINOS`, the PATH, the marketplace clone; 30 s), its stdin, stdout and stderr passed through, its exit kept when it is 0, 2 or 3 and 1 otherwise.

### §4 · What is owed (published at G1; built in M4)

`sminos task owed --session <id> [--agents <ids of the session's running subagents>] --json`:

    { "v": 1, "seq": 14, "session": "…", "runner": "terminal" | "maws",
      "ready": [{ "recipient": "main" | { "agentId": "…" }, "keys": ["t7.3"], "text": "…", "wakes": true, "more": false }],
      "outcomes": [{ "key": "t7.3", "seq": 13, "task": "t7", "revision": 1, "kind": "done", "text": "…", "at": "<time>",
                     "to": "main" | { "agentId": "…" }, "wakes": true, "acrossStop": false, "via": "self" | "cleared" }],   // every outcome owed to this session, first 200
      "owed": 1, "waking": 1,                                          // counts of all owed, and of those for the main conversation that wake
      "stranded": ["t3.1"],                                            // a subagent's outcomes whose agent is not among --agents
      "open": { "count": 2, "blocking": 1 },                          // this session's target's open tasks
      "mine": [{ "id": "t7", "class": "blocking", "title": "…", "born": 9 }],   // open blocking tasks this session assigned, newest 50
      "board": { "url": "…" } | null }

- An outcome is **for this session** when it is not landed and `target_of(its task).session` is the session.
- **Recipients.** An outcome whose `to` is an agent is ready only for that agent and only when `--agents` names it; otherwise it is listed in `stranded` and is nobody's until the mod reroutes it. A caller that gives no `--agents` (MAWS; the start line) therefore never sees a subagent's outcome as the main conversation's.
- **The main envelope** is composed only for `runner: "terminal"`; a MAWS-run session's main outcomes are in `outcomes` for MAWS's steer.
- An outcome **wakes** when it is a `done`, a `comment`, or a `declined` of a blocking task, and it is not `acrossStop` or its `wake.asked` is true.
- At most four recipients; an envelope packs what is owed to its recipient by `seq`, waking ones first, within D5's budget; composed to the published examples.
- `board` is the newest live registration under `tasks/surfaces/` (X5), chosen by the rule the command already has for the sheet's surfaces (heartbeat and pid), given the directory.
- The composer is a pure function of the store, the session, the targets as resolved, the agents, and a time zone; the published examples carry those inputs, so one store composes differently for two sessions and each is pinned.

The composer lives in the tasks' module and imports the sheet's measures (`units`, `jstr`, `mark` from `S/sminos_sheet_step.py`); `block(obj, element="sheet-delivery")` there is D6's one changed line, made in M3's pull request with the rest of what the holder agreed, so M4 uses a local copy only if it is built before L3 lands and drops it at L4.

### §5 · The wake's attempts and the daemon (M4; X7)

    attempts_due(store) -> [(task, outcome, target)]
    attempt(task id, key) -> answer | None          # tasks' module; called by the door after its replace, and by the tick
    notice_once(project, to_session, text, identity) -> answer      # S/sminos.py: factored from `say --notice`'s append

An attempt is **due** for an outcome when it is owed, `wake.asked`, its target is `stopped` with stop mark `S`, no entry of `wake.tries` has that session and `S`, and it has fewer than three. `attempt` resolves the target, calls `notice_once` with D5's text, the target's session and project, and the identity `tasks:<key>:<session>:<S>`, and then, under the store's lock, reads the outcome again and records the try with the answer when it is still owed and still has none for that pair. The append comes first and the record second, so a death between them repeats only the record.

`notice_once` is what the door and the daemon need of `cmd_say`'s notice path and nothing else: it appends one `human` event with `notice: "tasks"`, addressed to one session (by its id, never by resolving an alias again), carrying the identity as its `src`; it appends nothing when the writer's log already holds that `src`, checked and appended under the writer's log lock as `append_host` does for a host event; it prints nothing and never exits; it answers what the delivery said (`woken`, `held:<why>`, `gated`, `pending`) or raises. Whatever locks the delivery takes are taken with the store's lock not held. A machine or a project a notice cannot be written in answers `failed` with the reason, which is recorded as a try.

For a target that is `ended`, `attempt` writes D5's untagged line once, under the identity `tasks:<key>:ended`, and records a try with `stop: "ended"`.

`sminos_daemon.sweep_tasks()`, called from `tick_all`: it reads the store when the file changed since its last look, keeps the outcomes that asked for a wake and are still owed, and at every tick while it holds any, resolves their targets and calls `attempt` for each that is due. A target that stops changes no file, which is why the candidates are kept and looked at each tick and not only when the store changes. On `override_duty`'s hourly spacing it removes each closed task whose `closed.at` is more than 30 days old and none of whose outcomes is owed, with its `applied` keys, and each successor pair neither of whose sessions is a task's asker or in a task's chain. Any exception is a line in `daemon.log` and the next tick's work.

### §6 · The shared routes (M3)

The composite's D6: what moves, the lane and the `Source` seam, its nine binding rules. `H/delivery.tsx` exports `registerDelivery`, `openLane`, `retireLane`, `addSource`, `reconsider`, `resultRoute` and, for tests, the entry points its hooks use on a port of the test's own, as `sheetForTests` does. `H/delivery-model.tsx` exports `isRouteRow`, `contentTexts`, `PLUGIN` and, each taking a source's element and `keysOf`, `blocksOf`, `keysIn`, `heldKeys`, `landedSearchArgs`, `searchedKeys`.

The delivery's port (`DeliveryPort`) is the part of the sheet's `Port` the routes use: `submit`, `send`, `after`, `api`, `exec`, `log`, `toast`. A lane is opened by whichever source's start comes first for a session generation (`openLane` answers the lane already open for that session) and retired when that session leaves the process (a `/clear`, a fork); the sheet's `Gen` keeps what is the sheet's and holds its lane.

### §7 · The tasks' mod (M5)

    // H/tasks-model.tsx — no `$`
    export function attribute(command: string, agentId: string, name: string | undefined): string | undefined   // the changed command, or undefined for no change
    export function owedOf(stdout: string): Owed | undefined
    export function taskKeysOf(payload: unknown): string[] | undefined        // the tasks' block validator: `keys` and `outcomes` of one length, each key whole
    export function taskBandLine(open: { count: number; blocking: number }, board: { url: string } | null): string | undefined
    // H/tasks.tsx
    export function registerTaskAttribution(on: On): void     // first in H/register.tsx
    export function registerTaskBand(on: On): void            // beside registerSheetBand
    export function registerTasks(on: On): void               // after registerDelivery

`H/register.tsx` after M5 registers, in order: the attribution, the bridge, the backtick guard, the sheet's band, the tasks' band, the ask's band, the delivery, the sheet, the tasks, the ask, the address, the name.

## Plan of Work

### M1 — The store, its commands, the door, the start line, the published set (G1)

**At its end.** From a session's shell, `sminos task assign` puts a task in the machine's store and prints its id; `revise`, `comment`, `withdraw` and `reopen` change it under D2's rule of who may; from a terminal that is no session, `sminos task list` and `show` read the board with each task's target and its state, and `done`, `decline` and `comment` act through the door, which refuses a stale revision, applies an act once by its key, and refuses a session. Every human act leaves an outcome owed; the asker is told of it at its next start by a line of its own, reads it with `show` and settles it with `ack`. A `/clear` sminos witnessed makes the new session the task's target. `sminos/types/tasks/` is published whole at version 1 and the commands are held to it.

**Touches.** New `S/sminos_tasks.py`; `S/sminos.py` (the parser's `task` family, the early dispatch, the usage text, the call from the record hook's path where `cleared_witness` answers); `sminos/hooks/smns-guide.sh` or a sibling SessionStart shell hook and `sminos/hooks/hooks.json` (the start line); new `T/tasks-contract.gen.py`, `sminos/types/tasks/` (written by it), `T/test_tasks_contract.py`, `T/test_tasks.py`; `T/run-sminos-tests.sh` (the two suites, in the list with room); `S/CLAUDE.md` (a paragraph, as the sheet has one); `sminos/hooks/CLAUDE.md`; `sminos/CLAUDE.md` (one sentence and the pointer); sminos's version.

**Interfaces.** Exposes §1, §2, §3 (all but `owed`, `landed` and `reroute`), §4's schema and the store's steps to every later milestone, and X1, X2, X3 to B1a, B2 and B3. Consumes sminos's threads (`threads.current_record`, `get`, `thread_of`, `record_ended`), `sminos_records.lane_of`, `running_now`'s reading of the engine's records, `wake_here`, `cleared_witness`, `member_row`, `flocked`, `write_json`, `json_at`, all as built.

**Decisions.**
- The generator comes first and is written by hand from the composite and §1 to §4: schemas (`owed`'s answer among them), at least these fixtures (an assign that makes the store; a second; a revise; a done at the current revision; a done at an old one, `stale`; a decline; a comment by the human; the same line twice under one key; another line under that key, `key-reused`; a `seen` naming an older `seq` than a later revise, which stays Updated; a `delivered`; an `ack`; a withdraw; a reopen; an act on a closed task; an unknown field kept through a write, at the top and on a task; a successor's pair), and envelope examples, each with its inputs (one outcome; several with a declined and a comment; a subagent's; one rerouted to the main conversation; a successor's; one across a stop; a long note; one with `More follows.`; a MAWS-run session's answer, with outcomes and no main envelope; an answer with a stranded key). The examples are published now so that MAWS can pin them; M4 builds the composer to them.
- A writer never rebuilds a task from the fields it knows: it changes the parsed object in place.
- `target_of` is one function used by `list`, `show`, the door's `told`, `is_asker`, `remind`, and later `owed`, the attempts and B1a's predicate, so the card, the verdict, the rights and the delivery cannot disagree about whom a task answers to.
- The door reads all its lines and checks each against the line's schema before applying any: a call with one bad line applies nothing (exit 2). Each line's step is its own replace.
- The start line is the tasks' own and is not inside `guide_text`: the SessionStart shell hook runs `sminos task remind` when `tasks/state.json` exists and `SMNS_INTERNAL` is unset, whether or not the machine is enrolled and whether or not the session is a member, and prints what it answers into the session's context as the guide's text is printed. It starts no Python where there is no store.
- The lock is the sheet's kind (`fcntl.flock`, exclusive, 10 s, the file never unlinked); the replace is a synced temporary file in `tasks/` and `os.replace`.
- Pitfalls seen in the code: `S/sminos.py`'s `main` runs `migrate()` before most verbs, and a hook's call must not wait on it (§3's early dispatch); `members()` and `view_of()` write, so nothing here calls them; `running_now` reads the engine's records afresh at each call, so a `list` of many tasks reads them once and shares the reading.

**Does not touch.** The `task` plugin, any mod, the daemon, the sheet's files, the envelope's composer (only its published examples and schema), the notice, the ending pass.

**Proves.** The composite's A1, A2's list, A3 and A5 in their `sminos task` form (the verbs' names in `task` are M2's; the line and the notification are M5's), and X1 to X3. Its tests pin, beyond acceptance: two `assign`s at once from two processes get two ids and neither is lost; a kill between the temporary file and the replace leaves the store as it was; the same line twice changes nothing and answers the first verdict, `told` included, with the target's state changed between the two; a command of version 1 that waits for the lock behind a writer of version 2 refuses once it reads the file, and `show` and `list` still read it; `is_asker` true for the target and the thread's current session, false for a second session with no thread, for a fork, and for a session that filled the seat before; `target_of` for a running thread, a stopped one with and without a stop mark, a held one, an ended one, a cleared one with a running successor, with a stopped successor, with an ended successor, cleared twice, the left session opened again, a session that took the left one's alias and is no successor, a session with no thread, a lane B session with a thread record, and a record that cannot be read; a session at the door exits 3 and changes nothing; the 501st open task is refused, by `assign` and by `reopen`; two acts in one millisecond keep their order by `seq`; `show` prints a done's note and a decline's reason with their keys and writes nothing; `ack` by the asker lands exactly the keys named and by another session exits 3; `remind` for nothing, for open tasks, for an owed outcome, for a fork, and on a scratch home with no enrollment; every published fixture replays.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,version-bump`.

### M2 — The `task` verbs

**At its end.** `task assign-human`, `task show t7`, `task comment t7`, `task list --human`, `task revise`, `task withdraw` and `task reopen` do what the matching `sminos task` verbs do, from any directory; `task assign-human` no longer says the Task Board is not built.

**Touches.** In `task/`: the dispatch and its verbs' front (`task/cli/`), `task/tests/` (its stand-in `sminos` answers the `task` verbs), `task/CLAUDE.md`, the plugin's version.

**Interfaces.** Exposes X6's names in `task`. Consumes §3 from M1, and the `task` plugin's dispatch and its way of finding `sminos` as built.

**Decisions.**
- The human's forms are recognized first in the dispatch, before the ticket board's configuration is read or `gh` is looked for: `assign-human`, `revise`, `withdraw`, `reopen`; `show` and `comment` whose first argument is whole `t[1-9][0-9]*`; `list` with `--human`. The board is the machine's, so they work outside any repository and with the ticket board unconfigured.
- The three branches in the ticket verbs' dispatch are made as the ticket board's writer agreed them (X6); if that agreement names other verbs, the composite's writer rewrites D2 first and this milestone follows the rewrite.
- A heredoc's standard input reaches `sminos task` unchanged; the front reads none of it.

**Does not touch.** The store's commands' behaviour, the ticket verbs' own behaviour, sminos.

**Proves.** A1 in its `task` form. Its tests pin: each verb passes arguments, standard input, output and exit through and maps other exits to 1; where `sminos` is not found it exits 1 saying the human's board is kept by sminos; `task show t7` and `task assign-human` with a heredoc work in a directory that is no repository and with no board configured; `task show 7` is still the ticket's; `task revise 7` exits 2.

**Gate.** `ci-gate --gates task,version-bump`.

### M3 — The routes, shared: `delivery.tsx`

**At its end.** The question sheet delivers exactly as before, from a module that knows lanes and sources and not questions. Nothing a user can see has changed; what exists is the seam M5 plugs into, proved with a second source in a test.

**Touches.** New `H/delivery.tsx`, `H/delivery-model.tsx`; `H/sheet.tsx`, `H/sheet-model.tsx`, `H/register.tsx`; `S/sminos_sheet_step.py` (`block`'s second parameter); `T/mods/sheet-harness.ts`, `T/mods/test-sheet-step.sh` and the sheet tests' imports, where they reach the routes' state; new `T/mods/delivery.test.ts`, `T/mods/delivery-model.test.ts`; `H/README.md` (the sheet's Delivery paragraph names the module; a short section "delivery"); `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md` (I9's first paragraph and I11's layout, brought to where the code is); `docs/doperpowers/TECH-DEBT.md` rows 41 to 43 (the module's name); sminos's version.

**Interfaces.** Exposes §6. Consumes the sheet's routes as built on a `main` that holds the sheet's C5 M1.

**Decisions.**
- **It starts only when both conditions hold**: the sheet's holder has agreed D6 (and the composite carries what they changed), and the sheet's C5 M1 pull request is on `main`. If the holder rules the other order, the composite's writer rewrites D6's order paragraph and this milestone carries only what that paragraph then says.
- **Two commits a reader can take apart.** The first puts the routes behind the seam with the sheet as the only source and every sheet suite passing: it is not a move of lines alone, since the routes today close over the sheet's `Gen`, its port, `isStarted`, its stopped set and its main turn, and each of those becomes the lane's or is reached through the source. The second adds what more than one source needs (rule 2's total, rule 3's one source a prompt) with the stand-in source's tests.
- **Who owns each mixed hook** (rule 8). The catch-all `tool.call` hook and its result route are the delivery's; the sheet's own tool answers before it and calls `resultRoute` for its result, as it calls `withResultRoute` today. `session.append` is the delivery's: it orders the landing, then gives the row's texts to each source's `onRow` (the sheet fills its receipts there). `turn.start` and `turn.complete` are the delivery's and tell each source (`onMainTurn`: the sheet publishes its snapshot). The classic `SubagentStop` is the delivery's: it marks the agent stopped, then calls each source's `onAgentStop` in the same dispatch (the sheet queues its notice and orders its drain), before any route can open.
- The stopped set is one object, the lane's; `sheetForTests` gives the tests the same object they mutate today (`test-sheet-step.sh` sets it and drives the port with no hooks registered), not a second set kept in step.
- What C5's M1 added goes across with the rest, with the behaviour its tests pin: rule 7 for a MAWS-run session's notices and contexts, and the sheet source's `promptContext` for the context on a prompt whose text holds a block, which the prompt route awaits within the source's own bound and never holds the prompt past.
- `landed` and `rerouted` answering false keep their keys in flight (rule 6): this is `landOwed` and `rerouteOwed` as they are, seen from the delivery's side.
- `sheet.tsx` keeps exporting what other modules import today (`sheetNudge`, `isSheetChosen`, `sheetView`, `sheetNotices`, `askCall`, `registerSheet`, `registerSheetBand`, `resetSheet`, `TICK_MS`, `sheetForTests`).
- The toast and log lines keep their words for the sheet; the source's `name` stands where `sheet:` stood.
- No behaviour of the sheet is "improved" on the way. A defect found in the routes while moving them is written into `docs/doperpowers/TECH-DEBT.md` and told to the holder, not fixed here.

**Does not touch.** `S/sminos_sheet.py`; the step beyond `block`'s parameter; `sminos/types/sheet/`; the sheet's start choice, tool, floor readers, band, rows, snapshot; anything of the tasks'.

**Proves.** D6's nine rules, and A8's last clause. The sheet's suites pass with no assertion changed (`T/mods/sheet.test.ts`, `sheet-delivery.test.ts`, `sheet-drawing.test.ts`, `sheet-model.test.ts`, `test-sheet-step.sh`, `T/test_sheet_step.py`, `T/test_sheet_contract.py`); `git diff` of those test files shows import lines and the harness's registration only. `delivery.test.ts`, with a stand-in second source (its own element and validator) on the suite's fake port, pins: both sources ready at one tool result give the sheet's entries then the stand-in's, and each lands its own keys from its own element; a row holding one source's block lands nothing of the other's, and a block its own validator refuses lands nothing; a stand-in envelope that would take the plugin's entries past 150,000 units stays ready and the sheet's entries all ride; with both envelopes waking and the session idle, one prompt holds the sheet's envelope alone and the stand-in's leaves afterwards, and the sheet's floor readers read that prompt's row as they do today; a failed flight of one source leaves the other's as it was; with no source ready no hook adds or holds anything; a source whose `opensMain` is false gets no main flight while its notices, its context and its prompt context ride; a result dispatched before a session change carries nothing after it, and a source's `landed` that resolves after its lane retired changes nothing; keys handed to a `landed` that answers false are offered to no route and are handed again at the next look; at a subagent's stop the source's `onAgentStop` has run before the completion prompt's route takes its entries. `python3 -B sminos/tests/sheet-contract.gen.py --check` passes. `python3 sminos/tests/mods/live-sheet-check.py` is run once on the branch (it spends model calls) and its result is in the pull request.

**Gate.** `ci-gate --gates sminos-mods,mods-types,sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,version-bump`.

### M4 — What is owed: the envelope, the receipts, the wake

**At its end.** `sminos task owed --session <id>` answers the envelopes ready for a session, composed to the published examples, and every owed outcome's fields; `landed` and `reroute` record what the mod found; a done that asks for a wake writes sminos's notice once for a stopped target and records what sminos answered, the daemon making the attempt the door could not; an ended target's outcome leaves one line in its project's log; a closed task with nothing owed goes after 30 days. The door's `told` says `running` and `wake-asked`. No conversation receives an envelope yet: that is M5.

**Touches.** `S/sminos_tasks.py` (the composer, `owed`, `landed`, `reroute`, the attempts, the door's `told`); `S/sminos_daemon.py` (`sweep_tasks`, its place in `tick_all` and the hourly duty); `S/sminos.py` (`notice_once`, factored from `cmd_say`'s notice path so both use it); `T/test_tasks_owed.py`, `T/test_tasks_wake.py`; `T/run-sminos-tests.sh`; `S/CLAUDE.md`; sminos's version.

**Interfaces.** Exposes §4 and §5 to M5, B3 and the daemon. Consumes M1's store and `target_of`; the sheet's measures from `S/sminos_sheet_step.py`; `cmd_say`'s notice path and the delivery it calls; `wake_here`; the command's rule for a live surface registration.

**Decisions.**
- The composer is held to the published examples byte for byte, as the sheet's is to its set.
- `notice_once` is made by taking apart what `cmd_say` does for `--notice`, so that `say --notice` and the tasks' attempts append and deliver through one path; `cmd_say`'s own behaviour and `T/test_notice.py` stay as they are.
- U2's live check is made here, before M5 builds on it, on a machine whose installed sminos is this branch (below, "The live checks"): a spawned seat assigns a blocking task and is stopped; `sminos task done` answers `wake-asked`, and the task shows an attempt answered `woken` with the seat running, the notice its first message. Where a machine cut over to the reach and words gates is at hand, the same there, the attempt's answer read as it comes. A seat that a notice alone does not wake stops the milestone and goes to the composite's writer.
- Pitfall seen in the code: `say --notice` is refused when a session's id is in the environment and when the machine's name is not one a notice is read under. The door is never a session; the second case is a `failed` try with its reason (§5).

**Does not touch.** Any mod; the sheet's files (it imports the step's measures and changes nothing there); the ending pass (B1a's).

**Proves.** A4's verdict, attempt and log (not yet the envelope in the conversation), A9's `told: ended` and its line. Its tests pin: every published example composes from its inputs; a subagent's outcome is ready for it only while `--agents` names it, is stranded otherwise, and is never in a main envelope or a MAWS-run session's main outcomes until rerouted; `reroute` and `landed` move only keys owed to that session's target; `wakes` for each kind, class, `acrossStop` and `wake.asked`; an attempt is made once for one stop by the door and the tick together, by two ticks at once, and after a kill between the append and the record (one event in the log, one try recorded); a target that stops again unread gets a second attempt for its new stop mark and a fourth is never made; a tick with the store unchanged still makes the attempt for a target that stopped since; a target with no stop mark yet gets its attempt from the tick once the mark is there; `failed` is recorded with its reason on a machine that cannot write a notice; the ended line is written once; a closed task 31 days old with an owed outcome stays and one with none goes with its keys; two calls of `owed` for one session with different `--agents` each answer by their own list.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-idle,version-bump`.

### M5 — The session's side: the tasks' source, the subagent's attribution, the terminal's line, the notification

**At its end.** In a terminal session, an outcome owed to it arrives in the conversation by the first route that opens, a subagent's in the subagent's own; it is acknowledged when its row is stored; a resumed session does not receive again what its transcript already holds; a task a subagent assigns names the subagent, and the person approving the call sees the flag that says so; the line above the prompt counts the session's open tasks; a new blocking task raises one notification. A woken thread receives its envelope without anyone typing.

**Touches.** New `H/tasks.tsx`, `H/tasks-model.tsx`; `H/backticks.tsx` (the lexer keeps where a literal word starts and ends in the command); `H/register.tsx`; new `T/mods/tasks-model.test.ts`, `T/mods/tasks-attribution.test.ts`, `T/mods/tasks.test.ts`, `T/mods/tasks-delivery.test.ts` (on the sheet's harness pattern), `T/mods/live-tasks-check.py`; `sminos/types/sminos.d.ts` if a kept state is added; `H/README.md` ("tasks"); sminos's version.

**Interfaces.** Consumes §6 from M3, §3's `landed` and `reroute` and §4 from M4, `backticks.tsx`'s lexer. Exposes nothing later milestones consume.

**Decisions.**
- **One read at a time.** The mod runs one `sminos task owed` at a time for a lane; a look asked for while one runs makes exactly one more after it, with the inputs of that later moment. An answer is adopted only for the lane that asked and only if no later request has been adopted, so two answers of one `seq` and different agent lists cannot be taken in the wrong order.
- **When it looks.** At a start; at every tool call, prompt and turn's end the mod sees and on a 5 s timer, when one `$.fs.stat` of `tasks/state.json` differs from the stat of the last read that answered (a read that failed leaves that mark where it was); at a subagent's stop; after every `landed` and `reroute` it ordered; and every twelfth tick regardless, since a successor's pair, a surface's registration and a thread's state change without the file changing.
- **The source.** `element: 'task-delivery'`, `keysOf: taskKeysOf`; `ready` is the answer's; `opensMain` is false when the answer's `runner` is `maws`; `wake` answers the main envelope's keys no idle submit has failed on, and, where all of them have, opens once more when the answer's `waking` count is above what it was at the failure (a fresh waking outcome behind a full envelope of spent ones); `landed` orders `sminos task landed --by …` and answers true on its answer; `rerouted` orders `sminos task reroute` for those keys and answers true on its answer; `missed` spends the keys for the idle route as the sheet's does.
- **A subagent's outcome is the mod's to hand on.** For each key in `stranded` whose agent is not running and that no send is carrying, the mod orders `reroute`; a send that was not delivered reroutes its own keys through the source's `rerouted`. Nothing else makes a subagent's outcome the main conversation's, and a failed send to one task's subagent changes nothing for that agent's other tasks.
- **At a start, before any route of this source opens**: the lane holds the source closed until the start's search has answered or failed. The transcript's path is the classic `SessionStart`'s, which can come before or after `session.start`; whichever comes second finds the first's part done. With a transcript, the search looks for `task-delivery` blocks in rows of the routes' kinds for every key in the answer's `outcomes` (not only the first envelope's), and those found are ordered `landed`; if the answer's `owed` count is above the `outcomes` it lists, the search and the read repeat until a read lists every owed key or adds none. A search that fails, and a start with no transcript, open the source with nothing acknowledged: those outcomes go again.
- **The attribution.** `attribute` uses `backticks.tsx`'s lexer and no second one. The lexer today keeps a word's decoded text; it is taught to keep, for a word that is literal in the command (no quote, escape, expansion or continuation inside it), where it starts and ends in the command's bytes, in the outer command and inside a list, and nothing for a word inside a substitution or a heredoc's body. `attribute` finds each simple command whose command word's last path part is `task` followed by the literal word `assign-human`, or is `sminos` or `sminos.py` followed by `task` and `assign`, and inserts the flag after the verb's end, working from the command's end backwards so earlier positions stay true. A command the lexer gives up on, a verb that is not a literal word, and a command that already carries `--asker-agent` are returned unchanged. The hook acts only where `e.tool` is `Bash` and `e.agentId` is present and whole by D2's pattern; it calls `next({ ...e, command })` and returns what that returns; its `.catch` passes the call on unchanged, since a failure of the hook must never stop a command. The name comes from `$.agent.list()` at the call; a list that cannot be read gives the id alone.
- **The notification.** A task in the answer's `mine` whose `born` is above the `seq` of the first answer this process adopted for the lane raises `$.ui.notify` with its title, once a task. Nothing for tasks that were open at the start.
- **The line.** `registerTaskBand` draws `2 tasks for the human (1 blocking) · <address>` through `ui.render` for `AbovePrompt`, beneath the sheet's line, not while a survey holds the band; the address is the answer's `board.url`, else `sminos task list`.
- In a session where function hooks are off none of this runs; M1's start line and `ack` are what that session has (D5). A session marked `SMNS_INTERNAL` registers no source and draws no line.

**The live checks** (U1, U3, and M4's U2). `live-tasks-check.py`, in the manner of `live-sheet-check.py`: it drives real sessions and spends model calls, so it is run by hand and not in a gate. A background wake does not carry `--plugin-dir` (`sminos_wake.wake_argv`), so a scratch home with the branch loaded by flag proves nothing about a woken thread: the `woken` case, and U2, run on a machine whose installed sminos is this branch, with its daemon serving the home the check uses, and the check first shows that the woken process loaded this branch's module (a debug line with the plugin's version) and reports a setup that did not as its own failure, apart from the product's. It stops what it started. Cases: `idle` (an idle session, a done: a turn starts with the envelope), `result` (a done during a turn: the next tool result carries it), `resume` (a done while stopped without a wake: nothing starts; the envelope leaves with the first prompt, marked with its time), `woken` (A4 whole; which of U3's three questions held), `cleared` (A6), `subagent` (A7, with the envelope absent from the main conversation), `both` (A8), `attributed` (U1: a subagent's `task assign-human` or `sminos task assign` under an allow rule for the verb, one under a rule that names arguments, one with a classic `PreToolUse` hook that prints its input, and one whose command also holds a secret's handle, each observed and written down as found). What `woken` and `attributed` show is written beside D5 and D2 by the composite's writer. If no route opens in a woken thread, the milestone stops and the finding goes back (U3).

**Does not touch.** `H/delivery.tsx`'s rules (a need to change one goes to the composite's writer and the sheet's holder); the sheet's files; the store's commands.

**Proves.** A2's line and notification, A4, A6, A7 and A8. Its tests, on the suite's fake port, pin: an owed outcome leaves on the idle route when idle and on the result route during a turn, once; a declined non-blocking task's outcome opens no idle route and leaves with the next result; a subagent's envelope goes by a send whose delivered answer orders `landed --by send`, and a send not delivered orders `reroute` for its keys with no other write to wait for; two subagents each get their own and landing one's does not make the other's the main conversation's; the row that stores a task block orders `landed` for its keys and for no sheet key, and a block `taskKeysOf` refuses lands nothing; a failed idle submit is not retried by itself and a later waking outcome opens the route once; a reload of the module loses no outcome; two `owed` answers arriving out of order leave the later request's adopted; a failed read is tried again at the next look; a successor's pair written with the file's stat unchanged is found by the twelfth tick; a start whose search has not answered opens no route, with either start hook first, and a start with no transcript opens with nothing acknowledged; the notification once a new blocking task and never at a start; the band's text for none, open, blocking, and with a board's address. `attribute`: a plain call, one with a heredoc body, one in a list (`a && task assign-human … && b`), two assigns in one command (both changed), the verb's text repeated inside a quoted argument (only the command changed), a quoted `task assign-human` inside an `echo` (unchanged), a verb split by a quote or a continuation (unchanged), a trailing comment, a path-qualified `task`, a command inside `$( … )` (unchanged), an id that fails the pattern (unchanged), a teammate's id, a name with spaces and quotes (reduced), a command already carrying the flag (unchanged), and a command the lexer gives up on (unchanged); the hook on the main loop changes nothing; the hook's failure passes the call on.

**Gate.** `ci-gate --gates sminos-mods,mods-types,version-bump`, and `live-tasks-check.py`'s cases by hand, their result in the pull request.

### M6 — What agents are told, what is written beside the code, the acceptance

**At its end.** An agent that has never seen this feature learns from its start guide that the human's board exists and when to use it, and from the skill how; the repository's own accounts name the store, the door and the routes where their code is; the composite's A1 to A8 have been run as written on a Mac with the released plugins.

**Touches.** New `task/skills/human-tasks/SKILL.md` (through doperpowers:writing-skills); `S/sminos.py` (`guide_text`: the teaching line); `task`'s help text; `sminos/skills/sminos/SKILL.md` (one pointer); `docs/whats-inside.md` (the skill's row; sminos's row); `sminos/README.md`, `sminos/CLAUDE.md`, `task/CLAUDE.md`; the root `CLAUDE.md`'s `task/` row if the ticket board's landing did not already carry the human's board; both plugins' versions.

**Interfaces.** Consumes X8 from B5 (the words), and everything built.

**Decisions.**
- The skill's body, the guide's line and the help text carry the words B5 passed, unchanged. Where B5's result differs from the composite's D2 list, the composite's writer has rewritten D2 before this milestone starts.
- The skill follows the repository's rule for skills: only what the reading model cannot derive. The verbs' flags are the help text's, not the skill's.
- The teaching line is the guide's (`guide_text`), for a session that is a member on an enrolled machine; the facts of what is open and owed stay M1's start line, which needs neither.
- The sentence for the question tool's description is not shipped here: it is the sheet's holder's to place (D6's second ask).

**Does not touch.** Behaviour. A defect the acceptance finds goes back to the milestone that owns it, as a fix on a branch of its own.

**Proves.** A1 to A8, by Concrete Steps' acceptance run, on the released plugins.

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
    # t1  blocking  "Log in to the console"  …  (not-reachable)  due —
    sminos/bin/sminos task done t1 --note "logged in"
    # {"v":1,…,"task":"t1","verdict":"applied","revision":1,"state":"done","outcome":"t1.1","told":"not-reachable"}
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task done t1; echo $?
    # … an agent's session does not complete the human's task …   3
    sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # Not yet delivered: t1.1 done. Read: sminos task show t1. Then: sminos task ack t1.1
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task ack t1.1 && sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # (nothing)

**M2.**

    bash task/tests/run.sh

**M3.**

    bash sminos/tests/mods/run.sh
    python3 -B sminos/tests/test_sheet_step.py && python3 -B sminos/tests/test_sheet_contract.py
    python3 -B sminos/tests/sheet-contract.gen.py --check
    git diff origin/main -- sminos/tests/mods/sheet.test.ts sminos/tests/mods/sheet-delivery.test.ts sminos/tests/mods/sheet-drawing.test.ts sminos/tests/mods/sheet-model.test.ts   # import lines only
    python3 sminos/tests/mods/live-sheet-check.py            # spends model calls; once

**M4.**

    python3 -B sminos/tests/test_tasks_owed.py
    python3 -B sminos/tests/test_tasks_wake.py

**M5.**

    bash sminos/tests/mods/run.sh
    python3 sminos/tests/mods/live-tasks-check.py idle result resume cleared subagent both attributed    # spends model calls; by hand
    python3 sminos/tests/mods/live-tasks-check.py woken      # on a machine whose installed sminos is this branch

**The acceptance (M6)**, on a Mac whose daemon serves the home in use and whose installed plugins are the released ones, in a scratch project; none of it on a scratch store. Each step is the composite's item of the same number.

1. In a terminal session, ask the agent to run in one Bash call, each command under `time`:

        time task assign-human --class blocking --title "Log in to the console" --body-file - <<'EOF'
        Sign in to the cloud console. Done when the dashboard loads.
        EOF
        time task assign-human --class needed --due 2027-01-05 --title "Rotate the signing key"

    Expect two lines, `t<n> blocking "Log in to the console"` and `t<m> needed "Rotate the signing key"`, each `real` under one second, and the turn going on.
2. In another terminal: `sminos task list`. Expect the blocking row first, each with the project, the session's alias and `(running)`, and `due 2027-01-05` on the needed one. In the session's terminal, expect `2 tasks for the human (1 blocking) · sminos task list` above the prompt, and one notification on the machine, naming the blocking task.
3. Close the session's terminal and note the time. Run `sminos daemon tick` twice, then `sminos task list`: the blocking row reads `(stopped, to be woken)`.
4. `sminos task done t<n> --note "logged in with account B"`. Expect `"told":"wake-asked"`. Then `sminos task show t<n> --json` shows one try answered `woken`, `sminos list` shows the session running in the background, and after its turn `show --json` shows the outcome `landed` by `row`; the session's transcript holds one `[tasks v1]` envelope with the note; `sminos chat` for the project shows one `tasks` notice and not the note.
5. Tell the session (`sminos say @<alias> …`) that the console still asks for a login. Expect it to run `task reopen t<n> --comment "…"`; `sminos task list` shows `t<n>` open, `Updated`. `sminos task done t<n>` answers `stale` with revision 2.
6. In a second session: assign a needed task, `/clear`, go on in the same terminal. `sminos task show` of it names the new session as its target. Rename a third session to the cleared one's old alias. `sminos task done` of the task. Expect the envelope in the new conversation with `(assigned by the conversation this one replaced at a /clear)`, no background process for the cleared one, and nothing in the third session.
7. Have a session dispatch a subagent that assigns a task and keeps working. `sminos task show` names the subagent. `sminos task done` while it runs: the envelope is in the subagent's transcript and the main transcript holds no `task-delivery` block for that key. Repeat with the subagent ended: it is in the main conversation, naming the subagent.
8. In a session started with `SMINOS_QUESTION_SHEET=1` and a surface alive (`sminos/tests/sheet_surface.py`): put a question on the sheet and assign a task; while the model runs a long tool call, answer the question (`sminos sheet answer …`) and complete the task. Expect the tool's result to carry two context entries, the `[sheet v1]` one first and the `[tasks v1]` one after; `sminos sheet show --json` shows that answer's key delivered and `sminos task show --json` that outcome's key `landed`. Then, with the session idle, answer a second question and complete a second task together: two prompts follow one another, the sheet's first, neither holding the other's envelope.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

Nothing yet.
