# Task Board, B1 — the store, the door, the envelope and its delivery, the verbs: execution (2026-11-27)

> **Composite:** `docs/doperpowers/specs/2026-11-27-task-board-design.md`, child **B1**. **Parent pin:** `5e6f0d8be` (branch `task-board-spec`). The child's section in the composite ("### B1: …") is its spec; the composite's D1 to D6, D8 and D9 are its design, binding where they are marked, and X1 to X4, X6 and X7 the contracts it owns. This document carries the constraints, the decisions the composite did not carry, the interfaces and the milestones, and restates nothing of the design.
>
> **Written against:** this repository's `main` at `40b79a7d1` (the question sheet's C2 whole, sminos 1.59.0); `ticket-board-spec` at `143552115` (the `task` plugin specified, not built); MAWS's `question-sheet-c5` at `2a8ef52ee` (the sheet's C5 plan, whose M1 changes the routes M3 moves).
>
> **Read before M1:** the composite whole; `sminos/hooks/mods/README.md`, "sheet"; `sminos/skills/sminos/scripts/CLAUDE.md`, the question sheet's paragraph and the threads' (the record, the wake, `/clear`); in `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`, I7 (the envelope and its budget), I9 (delivery) and I11 (the mod's layout); `sminos/types/sheet/README.md`, as the model of a published set.

## Progress

- [ ] The owner's read of the composite (nothing starts before it).
- [ ] M1 — The store, its commands, the door, the published set (gate G1).
- [ ] M2 — The `task` verbs, and the subagent's attribution. Waits on the `task` plugin's first release.
- [ ] M3 — The routes, shared: `delivery.tsx`. Waits on the sheet's holder's agreement and on the sheet's C5 M1 pull request on `main`.
- [ ] M4 — What is owed: the envelope, the acknowledgement, the wake.
- [ ] M5 — The session's side: the tasks' source, the terminal's line, the notification.
- [ ] M6 — What agents are told, what is written beside the code, the acceptance. Waits on B5.

## Words this document adds

- **Target**: the session an outcome is delivered to now, with its thread and state; computed at each read from the task's asker (§2), never stored.
- **G1**: the gate M1 closes: the set `sminos/types/tasks/` published at version 1, which MAWS's children pin.
- **The tasks' module**: `sminos/skills/sminos/scripts/sminos_tasks.py`. **The tasks' mod**: `sminos/hooks/mods/tasks.tsx` with `tasks-model.tsx`.
- **H/**: `sminos/hooks/mods/`. **S/**: `sminos/skills/sminos/scripts/`. **T/**: `sminos/tests/`.

## Verification

This document had one `doperpowers:adversarial-reviewer` buildability review with the composite's design review, and one review of the repair. On the branches, through doperpowers:review-code: the pull request that holds M3 and the one that holds M4 and M5 at the **high** rung (a mistake in a route loses or doubles a delivery, in the sheet as well as here); M1, M2 and M6 at **medium**. M3's pull request is also read by the sheet's holder before it merges. Each milestone's own gate is in its entry.

## How it lands

Five pull requests, each from a worktree of its own branched from `main`, each raising the version of every plugin whose shipped files it touched (`scripts/bump-version.sh --plugin sminos`, `--plugin task`; `scripts/bump-version.sh --since origin/main` before a push), each body ending with the session line.

| landing | holds | waits on | what a user has after it |
|---|---|---|---|
| L1 | M1 | the owner's read | tasks assigned with `sminos task assign`, listed, completed from a terminal; the asker reads with `sminos task show`. G1. |
| L2 | M2 | L1; the `task` plugin on `main` | `task assign-human` and the other verbs; a subagent's task names the subagent |
| L3 | M3 | the holder's agreement; the sheet's C5 M1 on `main` | nothing new: the sheet delivers as before, from a shared module |
| L4 | M4, M5 | L1, L3 | the outcome arrives in the asker's conversation; a stopped asker is woken; the terminal's line |
| L5 | M6 | L2, L4, B5 | the skill and the guide's words; the acceptance run |

M4 touches nothing of the sheet's and may be built while L3 waits; it lands with M5. A milestone that waits is not started early on a guess of what it waits for. The session that holds the composite dispatches a `doperpowers:plan-executor` for each landing as it becomes free.

## Constraints on every milestone

- **Python 3.9, standard library only**, as every sminos script is; the mods are TypeScript checked by `tests/mods/typecheck.sh` (the `mods-types` gate).
- **Only the command writes the store.** A hook can neither lock nor replace a file (the sheet's K1): the mod orders `sminos task …` through `$.process.run` and keeps what it answered.
- **`$` crosses no import.** A mod reaches the engine through closures made inside its own hooks (the sheet's `Port` pattern in `H/sheet.tsx`), so a test hands its own.
- **Nothing submits a prompt inside a hook's dispatch** (the sheet's C0 P1): the idle route goes from a `$.clock.after(0)` hop. M3 moves this rule with the code; M5 adds no submit of its own.
- **A whole value is checked with `fullmatch`**, never `match` against `^…$` (`sminos/CLAUDE.md`).
- **Nothing new at the root of `$SMINOS_HOME`**: every sminos reads a `*.json` there as a seat. The store is the directory `tasks/`.
- **The sheet's published set is not touched** by any milestone: `python3 -B sminos/tests/sheet-contract.gen.py --check` passes at every landing.
- **The repository is public.** No hostname, address, account, project id, secret's name or value, local absolute path or session id in code, tests, fixtures, documents or commit messages. Fixtures use the sheet's stand-in ids (`5eed0000-…`) and `{HOME}`.
- **Version bumps** by `scripts/bump-version.sh` only, in the same commit as the change.
- **The composite's binding marks** bind here: D1's line and fields, D2's flag, D3's one store, D4's one door, D5's block, D6's five rules.

## The store's steps

The composite's D5 table is the outcome's state machine; this is what the commands add to it. Every row is one read, change and replace of `tasks/state.json` under `tasks/.lock`, `seq` + 1 when anything changed, nothing written when nothing did.

| command | who | refused when | what it changes |
|---|---|---|---|
| `assign` | a session | no session (3); 500 open (3); a field out of bounds (2) | a task at `nextId`, revision 1, open; its asker from the session, its thread and `--asker-agent` |
| `revise` | the asker (§2) | not the asker (3); not open (3); nothing given (2) | the fields given; revision + 1; `agentAt` |
| `comment` | any session, or the human through the door | closed (3, or verdict `closed`); empty (2) | a comment; from an agent `agentAt`; from the human an outcome `comment` |
| `withdraw` | the asker | not the asker (3); not open (3) | state withdrawn, `closed` |
| `reopen` | the asker | not the asker (3); not done (3); no comment (2) | state open; revision + 1; the comment; `agentAt` |
| `act` `done`, `decline` | the human | a session (3); revision not current (`stale`); not open (`closed`) | state; `closed`; an outcome |
| `act` `seen` | a surface | a session (3) | `seenAt` |
| `act` `delivered` | a deliverer | a session (3); a key not owed is passed over | the keys' outcomes `landed`, by `delivered` |
| `landed` | the mod | — | the keys' outcomes `landed`, by `row`, when owed to that session's target |
| `show` in the asker's session | an agent | — | that task's owed outcomes `landed`, by `show`, when the task's asker has no `agent` (M4) |

**Where a change becomes visible.** At the `os.replace`: a reader sees the state before or after, never between. The door prints a line's verdict only after its replace returned, so a surface that reads the store after a verdict sees the act. **What a death leaves.** Before the replace, nothing (a `.tmp-` file the next step removes). After the replace and before the notice (M4), an outcome with `wake` true and no `notified`: the daemon's tick writes the notice. After the notice and before `notified` is written, the tick writes a second notice: accepted, since a notice carries no outcome and delivery is at least once.

## Interfaces and Dependencies

### §1 · `state.json` (X1)

    {
      "v": 1, "version": 1, "seq": 14, "nextId": 8,
      "tasks": {
        "t7": {
          "id": "t7", "revision": 2, "state": "open",              // open | done | declined | withdrawn
          "class": "blocking", "title": "…", "body": "…", "due": null, "tags": [],
          "project": "<project id>",
          "askers": [{ "thread": "<thread id>" | null, "session": "<session id>", "alias": "alpha",
                       "agent": { "id": "a1b2c3d4e5f60718", "name": "reviewer" } | null }],
          "createdAt": "<time>", "agentAt": "<time>", "seenAt": "<time>" | null,
          "comments": [{ "n": 1, "by": "human" | { "session": "…", "alias": "…", "agent": {…} | null }, "at": "<time>", "text": "…" }],
          "closed": null | { "how": "done" | "declined" | "withdrawn", "at": "<time>", "text": "…" },
          "acts": 3,
          "outcomes": [{ "key": "t7.3", "kind": "done" | "declined" | "comment", "at": "<time>", "revision": 1, "text": "…",
                         "wake": true, "acrossStop": true, "notified": "<time>" | null,
                         "landed": null | { "at": "<time>", "by": "row" | "delivered" | "show" } }]
        }
      },
      "applied": { "<act key>": { "task": "t7", "at": "<time>", "verdict": { … } } }
    }

A time is ISO-8601 in UTC with milliseconds (`2026-11-27T22:20:10.593Z`). `acts` counts the human's acts on the task that make an outcome; an outcome's key is `<id>.<acts>` at its act. A row is "Updated" when `agentAt` is later than `seenAt`, or than `createdAt` where `seenAt` is null. An object's unknown fields are kept by every writer (D3). The set's serialization, cuts and "always present" readings are fixed by M1's generator, in the manner of `sminos/types/sheet/README.md`'s "Readings fixed with the set".

### §2 · The asker and the target

    asker_of(session, agent=None) -> {thread, session, alias, agent}     # at an assign
    target_of(task) -> {session, thread, alias, project, state, wake, why, via}

`asker_of` reads the session's thread as `sminos_channels._self` does (`threads.current_record(session, fresh=True)`); a session with no record has `thread: null`.

`target_of` decides whom a task's outcomes go to now, in this order:

1. No thread: the asker's session itself; `state` is `running` when a process holds it, else `not-reachable`; a lane B session's is `maws`.
2. The thread's record holds `released` and that release is not outlived (`sminos_threads.release_outlived`): the live member of the thread's project whose alias is the released one, when its thread is another and has not ended. `via: "cleared"`. That member's session and thread are the target.
3. Otherwise the thread's current session. `via: "self"`.

`state` is `running` (a process holds the target session, by the engine's records read afresh, `running_now`), `stopped`, or `ended` (`record_ended`); for `stopped`, `wake` and `why` are what `sminos.wake_here` answers for it (`woken`, or `held` with the published reason). A record that cannot be read gives `state: "unknown"`, which every consumer treats as not running and not to be woken.

"Is the caller the asker" (`revise`, `withdraw`, `reopen`; the acknowledgement by `show`): the caller's session is the task's `askers[0].session`, or its thread is `askers[0].thread`, or it is `target_of(task).session`.

### §3 · The commands (X2, X3, X6)

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
    sminos task owed --session <id> [--agents a,b,…] [--json]      # the mod's own (M4); in no usage text
    sminos task landed --session <id>                 # the mod's own (M4): {"keys": […]} on stdin; answers as `owed` does

Registered in `sminos.build_parser()` as `sheet` is (`sub.add_parser("task")`, its `fn` delegating to the tasks' module through `sibling_module`). `owed` and `landed`, given `--session`, are dispatched ahead of the migration as the sheet's `--session` verbs are: a session's hooks call them.

- A verb's role is its caller's: `assign`, `revise`, `withdraw`, `reopen` need `CLAUDE_CODE_SESSION_ID` (exit 3 without: only a session assigns); `done`, `decline` and `act` refuse it (exit 3); `comment`, `show` and `list` serve both, `comment` without a session going through the door as the human's. `done`, `decline` and the human's `comment` are the door's lines made for the caller, with a key the command mints, so the command line is a surface like any other.
- Exits: 0 done; 1 the store could not be read or written, or is of a newer `version` than this command writes; 2 usage or a field out of bounds; 3 refused by a rule, or no such task; 75 the lock not had in 10 s. `act` exits 0 when every line got a verdict.
- `list` without `--json`: one line a task, blocking first, then needed by due date (undated last), then optional, each `t7  blocking  "Log in to the console"  <project>  alpha (stopped, will be woken)  due 2027-01-05  Updated`. Text an agent wrote is printed as `sminos sheet show` prints a question's (control characters out, a line break a space) so no title reads as another row.
- `show` without `--json`: the head line, the body, then the comments in order, each with its author and time. `show` by a caller with no session sets `seenAt` (it is the human reading), through the door's `seen`.
- `--json` prints X1's `list` and `show` models: the task as stored, and beside it `asker` (`target_of`'s answer) and `updated` (a boolean).
- The verdict of the door: D4's shape. `told` from M1 is `running`, `next-resume`, `ended`, `not-reachable` or `maws`; M4 adds `woken` and `held:<why>` when it writes the notice.

In the `task` plugin (M2), each of D2's verbs runs the matching `sminos task` verb (`assign-human` → `assign`; `list --human` → `list`), found as the ticket verbs find `sminos` (`TASK_SMINOS`, the PATH, the marketplace clone; 30 s), its stdout and stderr passed through, its exit kept when it is 0, 2 or 3 and 1 otherwise.

### §4 · What is owed (M4)

`sminos task owed --session <id> --agents <ids of the session's running subagents> --json`:

    { "v": 1, "seq": 14, "session": "…", "runner": "terminal" | "maws",
      "ready": [{ "recipient": "main" | { "agentId": "…" }, "keys": ["t7.3"], "text": "…", "wakes": true, "more": false }],
      "open": [{ "id": "t7", "class": "blocking", "title": "…" }],        // this session's target's open tasks, first 50
      "counts": { "open": 2, "blocking": 1, "owed": 1 } }

- An outcome is **for this session** when it is not landed and `target_of(its task).session` is the session.
- Its **recipient** is the asker's agent when that id is among `--agents`, else `main`. A lane B session (`runner: "maws"`) gets no `main` envelope: MAWS delivers there (B3).
- It **wakes** when it is a `done`, a `comment`, or a `declined` of a blocking task, and it is not `acrossStop` or its `wake` is true.
- At most four recipients; an envelope packs what is owed to its recipient in the order applied, waking ones first, within D5's budget; composed to the published examples.
- `landed` marks the keys it is given that are owed to this session's target and answers what `owed` would.

The composer lives in the tasks' module and imports the sheet's measures (`units`, `jstr`, `mark`, `BUDGET`, `ENVELOPE_KEYS` from `S/sminos_sheet_step.py`); `block(obj, element="sheet-delivery")` there is D6's one changed line, made in M3's pull request with the rest of what the holder agreed, so M4 uses a local copy only if it is built before L3 lands and drops it at L4.

### §5 · The wake's notice and the daemon (M4; X7)

    notify(task, outcome) -> "woken" | "held:<why>" | None        # tasks' module; called by the door after its replace, and by the tick

Writes the notice only when the outcome's `wake` is true, it is owed and not `notified`, and the target is `stopped`: the text of D5, from the program `tasks`, tagged to the target's alias, in the target's project, through the function `sminos say --notice` appends with (its `human` event with `notice`, addressed), then sets `notified` under the store's lock. One notice a stop: when another outcome for the same target is already `notified` and not landed, this one takes that time and no second notice is written. For an `ended` target it writes D5's untagged line once an outcome. A machine that cannot write a notice (not enrolled, a machine name a notice is not read under) gives `None`; the verdict's `told` is then `next-resume`.

`sminos_daemon.sweep_tasks()`, called from `tick_all`: when `tasks/state.json` changed since its last look, or its last look left a wake unwritten, it calls `notify` for each outcome that qualifies. On `override_duty`'s hourly spacing it removes each closed task whose `closed.at` is more than 30 days old, with its `applied` keys. Any exception is a line in `daemon.log` and the next tick's work.

### §6 · The shared routes (M3)

The composite's D6: what moves, the `Source` seam, its five binding rules. `H/delivery.tsx` exports `registerDelivery`, `addSource`, `reconsider`, `notice`, `routeContext` and, for tests, the entry points its hooks use on a port of the test's own, as `sheetForTests` does. `H/delivery-model.tsx` exports `isRouteRow`, `contentTexts`, `PLUGIN` and, each taking the block's element, `blocksOf`, `keysIn`, `heldKeys`, `landedSearchArgs`, `searchedKeys`.

### §7 · The tasks' mod (M2, M5)

    // H/tasks-model.tsx — no `$`
    export function attribute(command: string, agentId: string, name: string | undefined): string | undefined   // the changed command, or undefined for no change
    export function owedOf(stdout: string): Owed | undefined
    export function taskBandLine(counts: { open: number; blocking: number }, surface: Surface | null): string | undefined
    // H/tasks.tsx
    export function registerTaskAttribution(on: On): void     // M2: first in H/register.tsx
    export function registerTaskBand(on: On): void            // M5: beside registerSheetBand
    export function registerTasks(on: On): void               // M5: after registerDelivery

`H/register.tsx` after M5 registers, in order: the attribution, the bridge, the backtick guard, the sheet's band, the tasks' band, the ask's band, the delivery, the sheet, the tasks, the ask, the address, the name.

## Plan of Work

### M1 — The store, its commands, the door, the published set (G1)

**At its end.** From a session's shell, `sminos task assign` puts a task in the machine's store and prints its id; `revise`, `comment`, `withdraw` and `reopen` change it under D2's rule of who may; from a terminal that is no session, `sminos task list` and `show` read the board with each asker's state, and `done`, `decline` and `comment` act through the door, which refuses a stale revision, applies an act once by its key, and refuses a session. Every human act leaves an outcome owed. `sminos/types/tasks/` is published at version 1 and the commands are held to it.

**Touches.** New `S/sminos_tasks.py`; `S/sminos.py` (the parser's `task` family, the early dispatch, the usage text); new `T/tasks-contract.gen.py`, `sminos/types/tasks/` (written by it), `T/test_tasks_contract.py`, `T/test_tasks.py`; `T/run-sminos-tests.sh` (the two suites, in the list with room); `S/CLAUDE.md` (a paragraph, as the sheet has one); `sminos/CLAUDE.md` (one sentence and the pointer); sminos's version.

**Interfaces.** Exposes §1, §2, §3 (all but `owed` and `landed`) and the store's steps to every later milestone, and X1, X2, X3 to B1a, B2 and B3. Consumes sminos's threads (`threads.current_record`, `get`, `record_ended`, `release_outlived`), `running_now`, `wake_here`, alias resolution in a project, `flocked`, `write_json`, `json_at`, all as built.

**Decisions.**
- The generator comes first and is written by hand from the composite and §1 to §3: schemas, at least these fixtures (an assign that makes the store; a second; a revise; a done at the current revision; a done at an old one, `stale`; a decline; a comment by the human; the same key twice; a `seen`; a `delivered`; a withdraw; a reopen; an act on a closed task; an unknown field kept through a write), and envelope examples (one outcome; several with a declined and a comment; a subagent's; one rerouted to the main conversation; a successor's; one across a stop; a long note; one with `More follows.`) with the store each was composed from. The envelope examples are published now so that MAWS can pin them; M4 builds the composer to them.
- A writer never rebuilds a task from the fields it knows: it changes the parsed object in place. Pinned by the unknown-field fixture, at the store's top level and on a task.
- A store whose `version` is above this command's: every writing verb exits 1 naming the plugin to update, before the lock is taken; reading verbs read.
- `target_of` is one function used by `list`, `show`, the door's `told`, and later `owed` and `notify`, so the card, the verdict and the delivery cannot disagree about whom an outcome goes to.
- The door reads all its lines and checks each against the line's schema before applying any: a call with one bad line applies nothing (exit 2).
- The lock is the sheet's kind (`fcntl.flock`, exclusive, 10 s, the file never unlinked); the replace is a synced temporary file in `tasks/` and `os.replace`.
- Pitfall seen in the code: `S/sminos.py`'s `main` runs `migrate()` before most verbs; a hook's call must not wait on it (§3's early dispatch).

**Does not touch.** The `task` plugin, any mod, the daemon, the sheet's files, the envelope's composer (only its published examples), the notice.

**Proves.** The composite's A1, A2's list, A3 and A5 in their `sminos task` form (the verbs' names in `task` are M2's; the line and the notification are M5's), and X1 to X3. Its tests pin, beyond acceptance: two `assign`s at once from two processes get two ids and neither is lost; a kill between the temporary file and the replace leaves the store as it was; the same key twice changes nothing and answers the first verdict; `revise` by a session that is not the asker exits 3, and by the successor of a cleared asker exits 0; `target_of` for a running thread, a stopped one, a held one, an ended one, a cleared one with a live successor, a cleared one whose successor ended, a session with no thread, and a record that cannot be read; a session at the door exits 3 and changes nothing; a newer store refuses a write and still lists; the 500th open task is refused; every published fixture replays.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,version-bump`.

### M2 — The `task` verbs, and the subagent's attribution

**At its end.** `task assign-human`, `task show t7`, `task comment t7`, `task list --human`, `task revise`, `task withdraw` and `task reopen` do what the matching `sminos task` verbs do; `task assign-human` no longer says the Task Board is not built. A task a subagent assigns, through either command, names the subagent, and the person approving the call sees the flag that says so.

**Touches.** In `task/`: the dispatch and its verbs' front (`task/cli/`), `task/tests/` (its stand-in `sminos` answers the `task` verbs), `task/CLAUDE.md`, the plugin's version. In sminos: new `H/tasks-model.tsx` (`attribute`), new `H/tasks.tsx` (`registerTaskAttribution`), `H/backticks.tsx` (what `attribute` needs of its lexer, exported), `H/register.tsx`, new `T/mods/tasks-model.test.ts` and `T/mods/tasks-attribution.test.ts`, `H/README.md` (a section "tasks"), sminos's version.

**Interfaces.** Exposes X6's names in `task` and §7's `attribute` and `registerTaskAttribution`. Consumes §3 from M1, the `task` plugin's dispatch and its way of finding `sminos` as built, `backticks.tsx`'s lexer.

**Decisions.**
- `attribute` uses `backticks.tsx`'s lexer and no second one: it finds each simple command whose command word's last path part is `task` followed by the word `assign-human`, or is `sminos` or `sminos.py` followed by `task` and `assign`, and inserts the flag after the verb's word, in the command's own bytes. A command it cannot lex whole, a verb reached through a variable or a substitution, and a command that already carries `--asker-agent` are returned unchanged.
- The hook acts only where `e.tool` is `Bash`, `e.agentId` is present and whole by D2's pattern, and `attribute` answers a change; it calls `next({ ...e, command })` and returns what that returns. Its `.catch` passes the call on unchanged: a failure of the hook must never stop a command.
- It is registered first so that the bridge and the plugins inside sminos see the command as it runs (the composite's baseline 9). `to-human`, seated outside sminos, sees the model's own command; nothing there compares the two.
- The name comes from `$.agent.list()` at the call; a list that cannot be read gives the id alone.
- The three dispatch branches in the `task` plugin are made as the ticket board's writer agreed them (X6); if that agreement names other verbs, the composite's writer rewrites D2 first and this milestone follows the rewrite.
- U1's live check is made here, by hand, once: a subagent runs `task assign-human` in a session with a permission rule for it; the dialog (or the allowed call) shows the flag, the rule matches, and the store names the subagent. Its finding is written beside D2 by the composite's writer.

**Does not touch.** The store's commands' behaviour, the ticket verbs' own behaviour, the routes, the sheet.

**Proves.** A1 in its `task` form, and A7's first sentence (the task names the subagent). Its tests pin: `attribute` on a plain call, one with a heredoc body, one in a list (`a && task assign-human … && b`), two assigns in one command (both changed), a quoted `task assign-human` inside an `echo` (unchanged), a trailing comment, a path-qualified `task`, an id that fails the pattern (unchanged), a name with spaces and quotes (reduced), a command already carrying the flag (unchanged), and a command the lexer gives up on (unchanged); the hook on the main loop changes nothing; the hook's failure passes the call on; each `task` verb passes arguments, output and exit through, maps other exits to 1, and says what is missing where `sminos` is not found.

**Gate.** `ci-gate --gates task,sminos-mods,mods-types,version-bump`.

### M3 — The routes, shared: `delivery.tsx`

**At its end.** The question sheet delivers exactly as before, from a module that knows sources and not questions. Nothing a user can see has changed; what exists is the seam M5 plugs into, proved with a second source in a test.

**Touches.** New `H/delivery.tsx`, `H/delivery-model.tsx`; `H/sheet.tsx`, `H/sheet-model.tsx`, `H/register.tsx`; `S/sminos_sheet_step.py` (`block`'s second parameter); `T/mods/sheet-harness.ts` and the sheet tests' imports; new `T/mods/delivery.test.ts`, `T/mods/delivery-model.test.ts`; `H/README.md` (the sheet's Delivery paragraph names the module; a short section "delivery"); `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md` (I9's first paragraph and I11's layout, brought to where the code is); `docs/doperpowers/TECH-DEBT.md` rows 41 to 43 (the module's name); sminos's version.

**Interfaces.** Exposes §6. Consumes the sheet's routes as built on a `main` that holds the sheet's C5 M1.

**Decisions.**
- **It starts only when both conditions hold**: the sheet's holder has agreed D6 (and the composite carries what they changed), and the sheet's C5 M1 pull request is on `main`. If the holder rules the other order, the composite's writer rewrites D6's order paragraph and this milestone carries only what that paragraph then says.
- **Move, then generalize, in separate commits.** First the code moves with its names and behaviour unchanged and the sheet as the only caller; then the seam is drawn. A reviewer, and the holder, read the first commit as a move and the second as the design.
- What C5's M1 added goes across with the rest: the MAWS-run branches of `take` and `withResultRoute` become the sheet source's `opensMain` answering false while notices and contexts still ride; the context it adds to a prompt whose text holds a block becomes an optional member of the sheet's source that the prompt route calls.
- `sheet.tsx` keeps exporting what other modules import today (`sheetNudge`, `isSheetChosen`, `sheetView`, `sheetNotices`, `askCall`, `registerSheet`, `registerSheetBand`, `resetSheet`, `TICK_MS`, `sheetForTests`).
- The toast and log lines keep their words for the sheet; the source's `name` stands where `sheet:` stood.
- The delivery's state is per session generation, as the sheet's `Gen` is: a `/clear` or a fork in the same process begins a new one, and a call that ran across the change carries nothing of the session after it (the rule `withResultRoute` has today).
- No behaviour of the sheet is "improved" on the way. A defect found in the routes while moving them is written into `docs/doperpowers/TECH-DEBT.md` and told to the holder, not fixed here.

**Does not touch.** `S/sminos_sheet.py`; the step beyond `block`'s parameter; `sminos/types/sheet/`; the sheet's start choice, tool, band, rows, snapshot; anything of the tasks'.

**Proves.** D6's five rules, and A8's last clause. The sheet's suites pass with no assertion changed (`T/mods/sheet.test.ts`, `sheet-delivery.test.ts`, `sheet-drawing.test.ts`, `sheet-model.test.ts`, `test-sheet-step.sh`, `T/test_sheet_step.py`, `T/test_sheet_contract.py`); `git diff` of those test files shows import lines only. `delivery.test.ts`, with a stand-in second source on the suite's fake port, pins: both sources ready at one tool result give two context entries in D6's order and each lands its own keys from its own element; a row holding one source's block lands nothing of the other's; an idle prompt holds the stand-in's envelope above the sheet's and the sheet's ends the text; two envelopes that together pass 60,000 units put only the waking one in the idle prompt and leave the other ready; a failed flight of one source leaves the other's flight as it was; with no source ready no hook adds or holds anything; a source whose `opensMain` is false gets no main flight while its notices still ride. `python3 -B sminos/tests/sheet-contract.gen.py --check` passes. `python3 sminos/tests/mods/live-sheet-check.py` is run once on the branch (it spends model calls) and its result is in the pull request.

**Gate.** `ci-gate --gates sminos-mods,mods-types,sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,version-bump`.

### M4 — What is owed: the envelope, the acknowledgement, the wake

**At its end.** `sminos task owed --session <id>` answers the envelopes ready for a session, composed to the published examples; `landed` and the asker's own `show` acknowledge; a done that asks for a wake writes sminos's notice for a stopped asker and the daemon starts the thread; an ended asker's outcome leaves one line in its project's log; closed tasks older than 30 days go. No conversation receives an envelope yet: that is M5.

**Touches.** `S/sminos_tasks.py` (the composer, `owed`, `landed`, the acknowledgement in `show`, `notify`, the door's `told`); `S/sminos_daemon.py` (`sweep_tasks`, its place in `tick_all` and the hourly duty); `S/sminos.py` (the start guide's line in `guide_text`; what `notify` needs of `say --notice`'s append, as a function); `T/test_tasks_owed.py`, `T/test_tasks_wake.py`; `T/run-sminos-tests.sh`; `S/CLAUDE.md`; sminos's version.

**Interfaces.** Exposes §4 and §5 to M5, B3 and the daemon. Consumes M1's store and `target_of`; the sheet's measures from `S/sminos_sheet_step.py`; sminos's notice (`say --notice`'s append and addressing), `wake_here`; `guide_text`.

**Decisions.**
- The composer is held to the published examples byte for byte, as the sheet's is to its set.
- The start guide's line, where the session's target has anything: `Tasks you assigned to the human: 2 open (1 blocking). Outcomes not yet delivered: t7, t9 (read one with: task show t7).` Nothing where there is nothing. A fork's start adds the composite's D9 sentence when the store holds any open task. These are facts and counts; the words that teach when to assign are M6's.
- U2's live check is made here, before M5 builds on it: on a Mac with the daemon, a session assigns a blocking task and its terminal is closed; after the stop pass `sminos task done` answers `told: woken`, and the thread runs in the background with the notice as its first message. A machine cut over to the reach and words gates is tried too where one is at hand. A no stops the milestone and goes to the composite's writer.
- `notify` appends through sminos's own function for a machine's notice, never by running `sminos say` as a child from inside the door: the door may itself be run by a surface with a short bound.
- Pitfall seen in the code: `say --notice` is refused when a session's id is in the environment and when the machine's name is not one a notice is read under. The door is never a session; the second case answers `None` (§5).

**Does not touch.** Any mod; the sheet's files (it imports the step's measures and changes nothing there); the ending pass (B1a's).

**Proves.** A4's verdict and log (not yet the envelope in the conversation), A9's last sentence (`told: ended` and the log's line). Its tests pin: every published envelope example composes; the recipient is the subagent only while it is named running; `wakes` for each kind, class, `acrossStop` and `wake`; a lane B session gets no main envelope; `landed` moves only keys owed to that session's target; `show` in the asker's session acknowledges a main-assigned task's outcomes and not a subagent-assigned one's; a notice is written once a stop for two outcomes; the tick writes the notice the door could not, and a tick that finds `notified` set writes none; a 31-day-old closed task goes with its keys and a 29-day-old one stays; the guide's line for none, open only, and owed.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-idle,version-bump`.

### M5 — The session's side: the tasks' source, the terminal's line, the notification

**At its end.** In a terminal session, an outcome owed to it arrives in the conversation by the first route that opens, a subagent's in the subagent's own; it is acknowledged when its row is stored; a resumed session does not receive again what its transcript already holds; the line above the prompt counts the session's open tasks; a new blocking task raises one notification. A woken thread receives its envelope without anyone typing.

**Touches.** `H/tasks.tsx` (`registerTasks`, `registerTaskBand`), `H/tasks-model.tsx`, `H/register.tsx`; new `T/mods/tasks.test.ts`, `T/mods/tasks-delivery.test.ts` (on the sheet's harness pattern), `T/mods/live-tasks-check.py`; `sminos/types/sminos.d.ts` if a kept state is added; `H/README.md` ("tasks"); sminos's version.

**Interfaces.** Consumes §6 from M3, §4 from M4, `surfaceOf` from `H/sheet-model.tsx` (for X5's registrations, read from `tasks/surfaces/`). Exposes nothing later milestones consume.

**Decisions.**
- **The check.** At every tool call, prompt and turn's end the mod sees, and on a 5 s timer, one `$.fs.stat` of `tasks/state.json`; when its size or time changed, at `session.start`, after a compaction, and at a subagent's stop, one `sminos task owed`, adopted when its `seq` is not older than the one held; then `reconsider()`. The answer is the tasks' source's `ready`.
- **The source.** `element: 'task-delivery'`; `opensMain` is false when the answer's `runner` is `maws`; `wake` answers the keys of the main envelope when it `wakes` and no idle submit has failed on them; `landed` orders `sminos task landed` and adopts its answer; `rerouted` adds the agent to a set the next `owed` leaves out of `--agents`; `missed` keeps the keys from opening the idle route again, as the sheet's does, until a new outcome arrives.
- **At a resume**, before the first envelope leaves: the transcript is searched for `task-delivery` blocks in rows of the routes' kinds (`landedSearchArgs` with the element) for the keys ready, and those found are ordered `landed`. A search that fails lands nothing, and those outcomes go again.
- **The notification.** When an answer's `open` holds a blocking task the mod has not seen in this process and whose asker's session is this one, `$.ui.notify` with its title, once a task. Nothing at a start for tasks that were already open.
- **The line.** `registerTaskBand` draws `2 tasks for the human (1 blocking) · <address>` through `ui.render` for `AbovePrompt`, beneath the sheet's line, not while a survey holds the band; the address is a live registration's URL under `tasks/surfaces/` (X5), else `sminos task list`.
- In a session where function hooks are off none of this runs; M4's guide line and `show` are what that session has (D5). A session marked `SMNS_INTERNAL` (sminos's own forks) registers no source and draws no line.
- U3's live check is `live-tasks-check.py`, in the manner of `live-sheet-check.py`: it drives real sessions and spends model calls, so it is run by hand and not in a gate. Cases: `idle` (an idle session, a done: a turn starts with the envelope), `result` (a done during a turn: the next tool result carries it), `resume` (a done while stopped without a wake: nothing starts; the envelope leaves with the first prompt, marked with its time), `woken` (A4 whole), `cleared` (A6), `subagent` (A7), `both` (A8). What `woken` shows of the three questions in U3 is written beside D5 by the composite's writer; if no route opens in a woken thread, the milestone stops there and the finding goes back, since the notice's own text is then all a woken thread gets.

**Does not touch.** `H/delivery.tsx`'s rules (a need to change one goes to the composite's writer and the sheet's holder); the sheet's files; the store's commands.

**Proves.** A2's line and notification, A4, A6, A7 and A8. Its tests, on the suite's fake port, pin: an owed outcome leaves on the idle route when idle and on the result route during a turn, once; a declined non-blocking task's outcome opens no idle route and leaves with the next result; a subagent's envelope goes by a send and, not delivered, is the main conversation's at the next read; the row that stores a task block orders `landed` for its keys and for no sheet key; a failed idle submit is not retried by itself; a reload of the module loses no outcome (what is not landed is ready again); the notification once a new blocking task and never at a start; the band's text for none, open, blocking, and with a live registration.

**Gate.** `ci-gate --gates sminos-mods,mods-types,version-bump`, and `live-tasks-check.py`'s cases by hand, their result in the pull request.

### M6 — What agents are told, what is written beside the code, the acceptance

**At its end.** An agent that has never seen this feature learns from its start guide that the human's board exists and when to use it, and from the skill how; the repository's own accounts name the store, the door and the routes where their code is; the composite's A1 to A8 have been run as written on a Mac with the released plugins.

**Touches.** New `task/skills/human-tasks/SKILL.md` (through doperpowers:writing-skills); `S/sminos.py` (`guide_text`: the teaching line); `task`'s help text; `sminos/skills/sminos/SKILL.md` (one pointer); `docs/whats-inside.md` (the skill's row; sminos's row); `sminos/README.md`, `sminos/CLAUDE.md`, `task/CLAUDE.md`; the root `CLAUDE.md`'s `task/` row if the ticket board's landing did not already carry the human's board; both plugins' versions.

**Interfaces.** Consumes X8 from B5 (the words), and everything built.

**Decisions.**
- The skill's body, the guide's line and the help text carry the words B5 passed, unchanged. Where B5's result differs from the composite's D2 list, the composite's writer has rewritten D2 before this milestone starts.
- The skill follows the repository's rule for skills: only what the reading model cannot derive. The verbs' flags are the help text's, not the skill's.
- The sentence for the question tool's description is not shipped here: it is the sheet's holder's to place (D6's second ask).

**Does not touch.** Behaviour. A defect the acceptance finds goes back to the milestone that owns it, as a fix on a branch of its own.

**Proves.** A1 to A8, by Concrete Steps' acceptance run, on the released plugins.

**Gate.** `ci-gate` whole, from the worktree.

## Concrete Steps

Every command runs from the repository's root in the milestone's worktree unless it says otherwise. A scratch store: `export SMINOS_HOME="$(mktemp -d)"`.

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

**M2.**

    bash task/tests/run.sh
    bash sminos/tests/mods/run.sh

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
    python3 sminos/tests/mods/live-tasks-check.py idle result resume woken cleared subagent both    # spends model calls; by hand

**The acceptance (M6)**, on a Mac with the daemon running and the released plugins, in a scratch project. Each step is the composite's item of the same number.

1. In a terminal session, ask the agent to run in one Bash call:

        task assign-human --class blocking --title "Log in to the console" --body-file - <<'EOF'
        Sign in to the cloud console. Done when the dashboard loads.
        EOF
        task assign-human --class needed --due 2027-01-05 --title "Rotate the signing key"

    Expect two lines, `t<n> blocking "Log in to the console"` and `t<m> needed "Rotate the signing key"`, and the turn going on.
2. In another terminal: `sminos task list`. Expect the blocking row first, each with the project, the session's alias and `(running)`. In the session's terminal, expect `2 tasks for the human (1 blocking) · sminos task list` above the prompt, and one notification on the machine.
3. Close the session's terminal. `sminos task list` until the blocking row reads `(stopped, will be woken)`.
4. `sminos task done t<n> --note "logged in with account B"`. Expect `"told":"woken"`. Then `sminos list` shows the session running in the background; `sminos task show t<n> --json` shows the outcome's `landed`; the session's transcript holds one `[tasks v1]` envelope with the note; `sminos chat` for the project shows the `tasks` notice and not the note.
5. Tell the session (`sminos say @<alias> …`) that the console still asks for a login. Expect it to run `task reopen t<n> --comment "…"`; `sminos task list` shows `t<n>` open, `Updated`. `sminos task done t<n>` answers `stale` with revision 2.
6. In a second session: assign a needed task, `/clear`, go on in the same terminal. `sminos task done` of it. Expect the envelope in the new conversation with `(assigned by the conversation this one replaced at a /clear)`, and no background process for the cleared one.
7. Have a session dispatch a subagent that assigns a task and keeps working. `sminos task show` names the subagent. `sminos task done` while it runs: the envelope is in the subagent's transcript. Repeat with the subagent ended: it is in the main conversation, naming the subagent.
8. In a session started with `SMINOS_QUESTION_SHEET=1` and a surface alive (`sminos/tests/sheet_surface.py`): put a question on the sheet and assign a task; while the model runs a long tool call, answer the question (`sminos sheet answer …`) and complete the task. Expect the tool's result to carry two context entries, one `[sheet v1]` and one `[tasks v1]`, and both `sminos sheet show --json` and `sminos task show --json` to show them delivered.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

Nothing yet.
