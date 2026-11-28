# Task Board, B1 — the store, the door, the notice, the verbs: execution (2026-11-27)

> **Composite:** `docs/doperpowers/specs/2026-11-27-task-board-design.md`, child **B1**. **Parent pin:** `fa284a280` and the one commit after it, which revised this document and the composite's D4, D5, X2 and X3 together (branch `task-board-spec`). The child's section in the composite ("### B1: …") is its spec; the composite's D1 to D5, D8 and D9 are its design, binding where they are marked, and X1 to X3, X5 and X6 the contracts it owns. This document carries the constraints, the decisions the composite did not carry, the interfaces and the milestones, and restates nothing of the design.
>
> **Written against:** this repository's `main` at `40b79a7d1` (sminos 1.59.0); `ticket-board-spec` at `143552115` (the `task` plugin specified, not built).
>
> **Read before M1:** the composite whole; `sminos/skills/sminos/scripts/CLAUDE.md`, the threads' paragraphs (the record, the wake, `/clear`) and the question sheet's (as the model of a per-machine record with a door and a published set); `sminos/types/sheet/README.md`, as the model of a published set; `sminos/hooks/CLAUDE.md` and `sminos/hooks/smns-guide.sh`. Before M2: in `sminos/skills/sminos/scripts/sminos.py`, `cmd_say`, `say_into`, `deliver_say`, `deliver_next`'s docstring, `notice_of`; `sminos/tests/test_notice.py`.

## Progress

- [x] (2026-11-28T01:57Z) M1 — The store, its commands, the door, the start line, the published set (gate G1). Task review clean after two fix rounds; sminos 1.60.0; the set's digest is in `sminos/types/tasks/MANIFEST.json`.
- [ ] M2 — Telling the asker now: the notice, the subagent's message, the wake.
- [ ] M3 — The `task` verbs. Waits on the `task` plugin's first release.
- [ ] M4 — The session's side: the subagent's attribution, the terminal's line, the notification.
- [ ] M5 — What agents are told, what is written beside the code, the acceptance. Waits on B5.

## Words this document adds

- **Shown**: an outcome a start line has been handed to the engine for, by the session it was handed to (`shown`). **Waiting**: not yet.
- **Due**: a sending the door decided and has not resolved (`send.state`).
- **Addressable**: a session that is a member of a project on this machine now, so a notice can be written to it there.
- **G1**: the gate M1 closes: the set `sminos/types/tasks/` published at version 1, which MAWS's children pin.
- **The tasks' module**: `sminos/skills/sminos/scripts/sminos_tasks.py`. **The tasks' mod**: `sminos/hooks/mods/tasks.tsx` with `tasks-model.tsx`.
- **H/**: `sminos/hooks/mods/`. **S/**: `sminos/skills/sminos/scripts/`. **T/**: `sminos/tests/`.

## Verification

This document was reviewed by `doperpowers:adversarial-reviewer` in its first form (twice) and once after the delivery changed to sminos's inbox. On the branches, through doperpowers:review-code: M2's pull request at the **high** rung (a mistake there wakes a thread nobody asked to wake, or sends nothing); M1, M3, M4 and M5 at **medium**. Each milestone's own gate is in its entry; gates run through `ci-gate` on the committed head, never on this machine.

## How it lands

One pull request a milestone, each from a worktree of its own branched from `main` (M1 excepted: it is built on `task-board-spec` itself, whose pull request carries this document and the composite with it), each raising the version of every plugin whose shipped files it touched (`scripts/bump-version.sh --plugin sminos`, `--plugin task`; `scripts/bump-version.sh --since origin/main` before a push), each body ending with the session line.

| landing | waits on | what a user has after it |
|---|---|---|
| M1 | nothing | tasks assigned with `sminos task assign`, listed and completed from a terminal; the asker's next start names every act of the human, and `sminos task show` gives their words. Nothing is pushed, and the door says so: `told` is `next-start`, `ended` or `maws`, and no outcome has a sending. G1. |
| M2 | M1 | the asker is also told at once: an idle session starts a turn, a stopped thread is woken per the human's choice, a running subagent is told itself |
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
- **No text an agent wrote goes into a message to an agent**: the notice, the subagent's message and the start line are built from the fixed words of §5, a task's id, the outcome's word and an agent's id, and nothing else (D5).
- **The repository is public.** No hostname, address, account, project id, secret's name or value, local absolute path or session id in code, tests, fixtures, documents or commit messages. Fixtures use stand-in ids (`5eed0000-…`) and `{HOME}`.
- **Version bumps** by `scripts/bump-version.sh` only, in the same commit as the change.
- **The composite's binding marks** bind here: D1's line and fields, D2's flag, D3's one store, D4's one door, D5's two tellings, its content rule and its target.

## The store's steps

Every row is one step: take `tasks/.lock`, read `tasks/state.json`, refuse if its `version` is above this command's, change, replace, release; `seq` + 1 when anything changed, nothing written when nothing did. The version is judged on the file read under the lock, in every writing step, the daemon's included. Every entry a step adds to a task's history (a comment, an outcome) carries the store's `seq` of that step.

| command | who | refused when | what it changes |
|---|---|---|---|
| `assign` | a session | no session (3); it would make 501 open (3); a field out of bounds (2) | a task at `nextId`, revision 1, open; its asker from the session, its thread and `--asker-agent` |
| `revise` | the asker (§2) | not the asker (3); not open (3); nothing given (2) | the fields given; revision + 1; `agentSeq` |
| `comment` | any session, or the human through the door | closed (3, or verdict `closed`); empty (2) | a comment; from an agent `agentSeq`; from the human also an outcome `comment`, the comment naming its key |
| `withdraw` | the asker | not the asker (3); not open (3) | state withdrawn, `closed` |
| `reopen` | the asker | not the asker (3); not done (3); no comment (2); it would make 501 open (3) | state open; `closed` null; revision + 1; the comment; `agentSeq` |
| `act` `done`, `decline` | the human | a session (3); revision not current (`stale`); not open (`closed`); a key used for another line (`refused`, `key-reused`) | state; `closed`; an outcome with its wake choice; the verdict kept by key |
| `act` `seen` | a surface | a session (3) | `seenSeq`, to the `seq` the line names when that is higher |
| `act` `shown` | a deliverer | a session (3); a key that is not the line's task's, is already shown, or whose target is not the line's `session` is passed over | `shown` on each outcome it took |
| a sending resolved (M2) | the door, in the act's call; any later call of the door; the daemon's hourly duty | not `due` any more | `send` on the outcome: `sent`, or `none` with why |
| the ended line (M2) | the door | already marked | `endedLine` on the outcome |
| `shown --keys` | the start hook | a key already shown, or whose target is not this session now, is passed over and never replaced by another | `shown` on each outcome it took |
| the successor's pair | `sminos record` and `remind`, at a witnessed `/clear` | no store yet: nothing is made; a pair already there naming the same session begun (the clear's other writer): nothing changes | `successors[<session left>]`, replacing, unbound, a pair that names another session begun (a session opened again after a clear, then cleared again) |
| the pair's thread | any step the session begun takes (`remind`, `shown`, a verb), the record hook once its join has made the thread, and the hourly duty | already bound; no live record has that session as its current one | `successors[…].thread` |

**Where a change becomes visible.** At the `os.replace`: a reader sees the state before or after, never between. The door computes a line's whole verdict, `told` included, before its replace, stores it under the act's key in the same replace, and prints it after, so the same line again reads the stored verdict and two callers of one key cannot be answered differently. **What a death leaves.** Before the replace, nothing (a `.tmp-` file the next step removes). After the replace and before the sending is resolved (M2): an outcome whose `send` is `due`. The act's verdict is stored and never changes; the sending is its own state, and whatever next calls the door on this machine, a resend of the same line included, first resolves every sending that has been due for more than a minute, as does the daemon's hourly duty. So a wake that was asked is late, not lost; and two callers that both find one due can each send, so one act can be named by two notices (neither can wake against the human's choice, which the notice itself carries). A start hook that dies between handing the lines to the engine and marking them prints them again at the next start.

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
          "comments": [{ "n": 1, "seq": 11, "by": "human" | { "session": "…", "alias": "…", "agent": {…} | null },
                         "at": "<time>", "text": "…", "outcome": "t7.2" | null }],
          "closed": null | { "how": "done" | "declined" | "withdrawn", "seq": 13, "at": "<time>", "text": "…" },
          "acts": 3,
          "outcomes": [{ "key": "t7.3", "seq": 13, "kind": "done" | "declined" | "comment", "at": "<time>", "revision": 1, "text": "…",
                         "wake": true,                          // the human's choice, resolved at the act
                         "shown": null | { "at": "<time>", "session": "<the session it was shown to>" },
                         "send": null                                           // the door decided to send nothing
                               | { "state": "due", "since": "<time>" }           // M2: decided, not resolved yet
                               | { "state": "sent", "how": "tell" | "notice", "at": "<time>", "session": "<to whom>", "agent": "<agent id>" | null,
                                   "liveOnly": true, "project": "<project id>" | null, "answer": "<what sminos or the bridge answered then>" }
                               | { "state": "none", "at": "<time>", "why": "<the refusal: not-addressable, no-writer, log-refused>" },
                         "endedLine": null | "<time>" }]
        }
      },
      "applied": { "<act key>": { "task": "t7", "at": "<time>", "digest": "<sha256 of the line as canonical JSON>", "verdict": { … } } },
      "successors": { "<session left>": { "session": "<session begun>", "thread": "<its thread id>" | null, "at": "<time>" } }
    }

A time is ISO-8601 in UTC with milliseconds, for showing; order is by `seq`, on a comment, an outcome and a closing alike, so a task's history is the merge of `comments` and `outcomes` by `seq` (a human's comment and its outcome share one). `born` is the store's `seq` at the assign; `agentSeq` the one at the last revise, comment or reopen by an agent. A row is "Updated" when `agentSeq` is above `seenSeq`. `acts` counts the human's acts on the task that make an outcome; an outcome's key is `<id>.<acts>` at its act. A task is closed when its `state` is not `open`; `closed` is null on an open task. An outcome is **waiting** while `shown` is null. `send` has four values and they are not interchangeable: null (nothing was to be sent), `due` (a sending was decided and is not resolved: in progress, or interrupted), `sent`, and `none` (the sending was tried and nothing could be appended, with the refusal). `send.answer` is a report of the sending and is never read as proof that anything arrived. `project` and `alias` are null for a session sminos knows no project or name for. An object's unknown fields are kept by every writer (D3). The set's serialization, cuts and "always present" readings are fixed by M1's generator, in the manner of `sminos/types/sheet/README.md`'s "Readings fixed with the set".

### §2 · The asker and the target

    asker_of(session, agent=None) -> {thread, session, alias, agent}     # at an assign
    target_of(store, task) -> {session, thread, project, state, runner, wake, why, via}
    is_asker(store, task, session) -> bool
    cleared(left, begun) -> None                                         # writes a witnessed clear's pair
    bind(store, session) -> None                                         # binds the pair that names this session to its thread

`asker_of` reads the session's thread as `sminos_channels._self` does (`threads.current_record(session, fresh=True)`); a session with no record has `thread: null`.

`target_of` decides whom a task's outcomes go to now. For a task whose asker has no thread the target is the asker's own session and nothing below applies: no successor is followed for it. Otherwise let `first` be the current session of the asker's thread, read from its record wherever that is kept (an ended record too: `threads.get`); when the record is gone (a retire that purged it), `first` is the asker's session. The chain is `first`, then the session `successors[first]` leads to, then the one that session's pair leads to, and so on to its end; a session met twice ends the chain there (no count cuts it short). **A pair leads to its thread, not to its session id**: once the pair's `thread` is bound, it leads to that thread's current session, read from the thread's record by its id, so a successor that handed off to another session is followed there, and a later process that reuses the successor's old id (which sminos gives a thread of its own) is not the continuation. An unbound pair leads to its `session`.

1. `first` has no successor: `first`. `via: "self"`.
2. `first` has one, and a process holds `first` that started after its pair's `at` (its human opened it again after the clear): `first`. `via: "self"`.
3. Else the last link of the chain, past `first`, that is alive. A bound link is alive while its thread's record is there and has not ended; a bound thread whose record is gone was purged, which is an end. An unbound link (a session only just begun, whose record is not made yet) is alive while a process holds it, and not when its project's log shows its retirement (`retired_in_log`) or nothing holds it. `via: "cleared"`.
4. Else `first`. `via: "self"`.

Then, for the session chosen, in this order:

- `runner`: `maws` when its lane is B (`sminos_records.lane_of(records.read(session))`, as `sminos_channels` reads it), else `terminal`. A record that cannot be read (`records.unreadable`) gives `state: "unknown"` and no more is asked.
- `state`: for `runner` `maws`, `running` when a process holds it, else `gone`, whatever a thread record says (MAWS reopens its own sessions). For `terminal`: `ended` when its thread's record has ended (even while a process still holds the session: an end is deliberate); else `running` when a process holds it (the engine's records, read once a call and shared by every task of that call); else `stopped` when it has a thread, whether or not the sweep has set its stop mark yet; else `gone`. A thread record that cannot be read gives `unknown`.
- `project`: the project its membership puts it in now, with a row for it there (`member_project_now`, `member_row`), else null: it is **addressable** when this is not null.
- For `stopped`, `wake` and `why` are this machine's own judgement, `sminos.wake_here`.

`unknown` is treated by every consumer as stopped and not to be sent to. `target_of` reads with no lock and writes nothing; within one call a task's target is resolved once for each distinct asker.

`is_asker`: the session is `target_of(task).session`; or the task has a thread and the session is that thread's current session; or the task has no thread and the session is `askers[0].session`. Nothing else: not an equal `thread: null`, not a session that once filled the same seat, not a fork.

**The pair.** `cleared(left, begun)` writes `successors[left]` when `tasks/state.json` exists and the pair is not already there, in a step of its own with no thread lock held. Its `thread` is bound, once, as soon as a live thread record has the session begun as its current one: by that session's own steps (`remind`, the start hook's `shown`, any `sminos task` verb it runs) and by the hourly duty. A successor that hands off before any of those ran is followed by its session id alone, and its predecessor's tasks then stay with that id. It is called where the witness is in hand and still whole: in `sminos record`'s clear path, after `cleared_witness` has answered and **before** `release_alias` (the release renames the session left, after which the witness no longer answers); and in `remind`, which asks `cleared_witness` itself when its `--source` is `clear`, since either start hook can run first and the record hook's own work can be cut short. A clear with no witness writes nothing.

### §3 · The commands (X2, X3, X5)

    sminos task assign --class C --title T [--body-file F|-] [--due D|--no-due] [--tag x]… [--asker-agent ID] [--asker-name N]
    sminos task revise <id> [--title T] [--body-file F|-] [--class C] [--due D|--no-due] [--tag x]… [--no-tags]
    sminos task comment <id> (--body-file F|- | "text")
    sminos task withdraw <id> [--reason "…"]
    sminos task reopen <id> --comment "…"
    sminos task show <id> [--json]
    sminos task list [--closed|--all] [--mine] [--json]
    sminos task waiting [--mine] [--json]              # every outcome no start has shown, whatever its task's state or age
    sminos task done <id>[@<revision>] [--note "…"] [--wake|--no-wake] [--key UUID]
    sminos task decline <id>[@<revision>] --reason "…" [--wake|--no-wake] [--key UUID]
    sminos task act                                    # the door: lines on stdin, a verdict a line on stdout
    sminos task remind --session <id> [--source S]     # the start hook's first call: prints the keys it shows, then the start line
    sminos task shown --session <id> --keys k,…        # the start hook's second call: marks those keys, for that session
    sminos task status --session <id> --json           # M4: the mod's own; in no usage text

Registered in `sminos.build_parser()` as `sheet` is (`sub.add_parser("task")`, its `fn` delegating to the tasks' module through `sibling_module`). The verbs given `--session` are dispatched ahead of the migration as the sheet's `--session` verbs are: a session's hooks call them.

**Roles and exits.** A verb's role is its caller's: `assign`, `revise`, `withdraw` and `reopen` need `CLAUDE_CODE_SESSION_ID` (exit 3 without: only a session assigns); `done`, `decline` and `act` refuse it (exit 3); `comment`, `show`, `list` and `waiting` serve both, `comment` without a session going through the door as the human's. Exits: 0 done; 1 the store could not be read or written, or is of a newer `version` than this command writes; 2 usage or a field out of bounds; 3 refused by a rule, or no such task; 75 the lock not had in 10 s. `act` exits 0 when every line got a verdict, whatever the verdicts. `done`, `decline` and the human's `comment` are the door's lines made for the caller. Each takes `--key <uuid>` (the human's `comment` too) and mints one when it is not given; it prints `key <uuid>` on standard error before it applies anything, then the verdict's line on standard output, and exits 0 for `applied`, 3 for `stale`, `closed`, `unknown` and `refused`. A caller that did not see the verdict runs the same command again with that key, which answers the first verdict and applies nothing; without the key it is a new act, and nothing is ever taken for a repeat by its text. The first verdict is kept by its key whatever it was (`applied`, `stale`, `closed`, `unknown`; not `refused`, which answers a key already kept), so a human who acts again after a refusal does so under a new key, which these verbs mint when none is given. A bare `<id>` on `done` and `decline` names revision 1.

**The door's lines** (each one JSON object on its own line; a field not listed for an act is refused):

    {"v":1,"key":"<uuid>","act":"done",    "task":"t7","revision":2,"text":"<note, may be empty>","wake":true|false|null}
    {"v":1,"key":"<uuid>","act":"decline", "task":"t7","revision":2,"text":"<reason, not empty>","wake":true|false|null}
    {"v":1,"key":"<uuid>","act":"comment", "task":"t7","text":"<not empty>","wake":true|false|null}
    {"v":1,"key":"<uuid>","act":"seen",    "task":"t7","seq":14}
    {"v":1,"key":"<uuid>","act":"shown",   "task":"t7","session":"<the session that was told>","keys":["t7.3","t7.4"]}

**The verdicts** (always `v`, `key`, `act`, `verdict`; then by verdict):

    {"v":1,"key":…,"act":"done","verdict":"applied","task":"t7","revision":2,"state":"done","outcome":"t7.3","told":"next-start"}
    {"v":1,"key":…,"act":"comment","verdict":"applied","task":"t7","revision":2,"state":"open","outcome":"t7.4","told":"now"}
    {"v":1,"key":…,"act":"seen","verdict":"applied","task":"t7","revision":2,"state":"open"}
    {"v":1,"key":…,"act":"shown","verdict":"applied","task":"t7","revision":2,"state":"done","keys":["t7.3"]}   // the keys it marked, of those named
    {"v":1,"key":…,"act":"done","verdict":"stale","task":"t7","revision":3,"state":"open"}   // the current revision
    {"v":1,"key":…,"act":"done","verdict":"closed","task":"t7","revision":2,"state":"declined"}
    {"v":1,"key":…,"act":"done","verdict":"unknown","task":"t99"}
    {"v":1,"key":…,"act":"done","verdict":"refused","reason":"key-reused"}

**The readers.**

    list --json     {"v":1,"seq":14,"tasks":[ <task>, … ]}
    show --json     {"v":1,"seq":14,"task": <task>}
    waiting --json  {"v":1,"seq":14,"waiting":[{"key":"t7.3","task":"t7","state":"done","kind":"done","seq":13,"at":"<time>","wake":true,
                                                "send": null | {…}, "target": <target>}, … ]}
    <task>   = the task as stored (§1), and beside it "target": <target>, "updated": true|false
    <target> = {"session":…,"thread":…|null,"project":…|null,"state":"running|stopped|ended|gone|unknown","runner":"terminal|maws",
                "wake":"woken"|"held"|null,"why":"…","via":"self|cleared"}

**A reader has no side effects**: `list`, `waiting` and `show`, with `--json` or without, write nothing, so a page that reads again on every change of `seq` does not make one. `seen` is sent by a surface for the snapshot the human opened, naming that snapshot's `seq`; on the command line that is `sminos task show` in its text form with no session, which sends the door's `seen` after printing, a separate step, and never `show --json`. `list` gives open tasks; `--closed` the closed ones still within their 30 days; `--all` both; `--mine` those whose target is the caller's session. `waiting` is not bounded by a task's state or age; `--mine` gives the caller's session's, and its text form is one line an outcome (`t7.3  marked t7 done  2026-11-27 16:40`).

- `list` without `--json`: one line a task, blocking first, then needed by due date (undated last), then optional, each `t7  blocking  "Log in to the console"  <project>  alpha (stopped, to be woken)  due 2027-01-05  Updated`; the state in brackets is `running`, `stopped, to be woken`, `stopped, held: <why>`, `ended`, `gone`, `run by MAWS`. Text an agent wrote is printed as `sminos sheet show` prints a question's (control characters out, a line break a space) so no title reads as another row.
- `show` reads a store of a newer version too. Without `--json`: the head line, the body, then the history by `seq`: each agent's comment with its author and time, and each act of the human with its word and its text (`done  2026-11-27 16:40  "logged in with account B"`).
- `remind` registers a witnessed clear's pair when its source is `clear`, and binds the pair that names its session (§2). It then prints, on a line of its own, the keys of the outcomes it is about to name, separated by spaces (an empty line for none), and after it the start line for the session's own target (§5): the count of its open tasks, and the first twenty waiting outcomes of its tasks by `seq`, with how many more wait. It marks nothing. For `--source fork`, when the store holds any open task, D9's sentence.
- `shown --session <id> --keys k,…` marks `shown` on each key named that is still waiting and whose target is that session now, and on no other: a key another start or MAWS has marked since, or one that is no longer this session's, is passed over, and nothing takes its place.
- The door's `shown` is bound the same way: one task a line, the session that was told, and that task's keys; it marks those of them that are waiting and whose target is that session.

**The door's decision** (the composite's D5 table, as code reads it). The outcome's `wake` is resolved in the step that applies the act: the line's `wake` when it is not null, else whether the task is blocking. Let `urgent` be: the act is a `done` or a `comment`, or a `decline` of a blocking task, or the line's `wake` is true. From `target_of`:

| the target | condition | sending | `told` |
|---|---|---|---|
| `running` | `urgent` | a `tell` to the subagent where the task names one, the target is the very session that assigned it (`askers[0].session`) and the `runner` is `terminal`; else, and where the `tell` did not take, a notice where the target is addressable | `now` |
| `running` | not `urgent` | none | `next-start` |
| `stopped` | the outcome's `wake` is true and the target is addressable | a notice | `wake` |
| `gone`, `runner` `maws` | the outcome's `wake` is true | none (MAWS's, B3) | `maws` |
| `ended` | — | the ended line | `ended` |
| anything else | — | none | `next-start` |

A notice is **for the live alone** unless the outcome's `wake` is true (D5). `told` is the decision; where a notice that was decided cannot be written (the target not addressable for a `running` one, a writer that refuses), the sending resolves to `none` with the refusal, and the start line stands. A subagent's id means something only in the session that dispatched it: a target that is another session (a successor, or the session a hand-off went on in) is never sent a `tell`, since an unrelated subagent there could hold the same id.

**Until M2 is installed** nothing is sent: M1's door writes `send: null` on every outcome and answers `next-start` wherever M2's will answer `now` or `wake`, and `ended` and `maws` as M2 will. The set's schema carries all five `told` values and all four values of `send` from G1.

In the `task` plugin (M3), each of D2's verbs runs the matching `sminos task` verb (`assign-human` → `assign`; `list --human` → `list`), found as the ticket verbs find `sminos` (`TASK_SMINOS`, the PATH, the marketplace clone; 30 s), its stdin, stdout and stderr passed through, its exit kept when it is 0, 2 or 3 and 1 otherwise.

### §4 · What the mod reads (M4)

`sminos task status --session <id> --json`:

    { "v": 1, "seq": 14,
      "open": { "count": 2, "blocking": 1 },                          // this session's target's open tasks
      "mine": [{ "id": "t7", "title": "…", "born": 9 }],              // open blocking tasks this session assigned, newest 50
      "board": { "url": "…" } | null }

`board` is the newest live registration under `tasks/surfaces/` (X4), chosen by the rule the command already has for the sheet's surfaces (heartbeat and pid), given the directory. This answer is the mod's own and is not in the published set.

### §5 · The texts (frozen at G1; X6) and the sending (M2)

`<id>` is a task's id; `<word>` is `marked <id> done`, `declined <id>` or `commented on <id>`. These are the only forms; the composite's examples are instances of them.

    A  notice, to the asker's own session:      [tasks v1] The human <word>, a task you assigned. Read it: sminos task show <id>
    B  notice, to a successor:                  [tasks v1] The human <word>, a task assigned by the conversation this one replaced at a /clear. Read it: sminos task show <id>
    C  notice, a subagent's task to its thread: [tasks v1] The human <word>, a task your subagent <agent id> assigned. Read it: sminos task show <id>
    message to a running subagent:              form A
    the start line:                          Tasks you assigned to the human: <n> open (<b> blocking).
                                             The human acted on tasks you assigned: <word>; <word>; … (and <k> more: sminos task waiting --mine). Read one: sminos task show <id>
    the ended line:                          tasks: <id> was <completed|declined|commented on>; the conversation that assigned it has ended. It is on the board: sminos task show <id>

The start line's first sentence is printed when the target has open tasks, its second when outcomes wait, each alone or both; the `<id>` after "Read one" is the first outcome's task.

Which form a notice takes is decided by the target and the task, in this order: the target was reached through a successor's pair (`via: "cleared"`): B, whether or not a subagent assigned the task; else the task names a subagent: C (the `tell` did not take, or the target is not the session that assigned it); else A.

    send(task id, key) -> None                                   # tasks' module; called by the door after its replace
    tell_agent(session, agent id, text) -> "queued" | "refused:<why>" | "unanswered"     # tasks' module, over sminos_control.post_command
    board_notice(session | None, project, text, live_only) -> ("sent", answer) | ("none", why)      # S/sminos.py

`send` resolves a sending that is `due` (the act's own replace sets it so, where §3's table decided one), with the store's lock not held, and then records the result in a step that changes the outcome only if its `send` is still `due`:

- **`tell`**: `tell_agent` posts the bridge's `tell` op (`{"op": "tell", "agentId": <id>, "resolvedAgentId": <id>, "text": …}`) to the session's bridge socket, as `sminos_sheet.nudge` posts its op, bounded at 10 s; it needs no project. `queued` (the bridge answered ok: the message is queued for the subagent, not read): `send` is `sent`, how `tell`. `refused` (the agent ended or is unknown, the bridge is an observer's) or `unanswered` (no socket, no answer in time): `send` reads the target again and goes on to the notice by §3's table as it stands then, in the subagent's-thread form. A `tell` that got no answer may have been queued: the subagent and its thread can both be told.
- **A notice**: `board_notice` with the text, the target's session and project, and whether it is for the live alone. An answer makes `send` `sent`, the answer kept as given; a refusal makes it `none` with the refusal's word. A target that is not addressable is `none`, `not-addressable`, with nothing tried.
- **The ended line**: `board_notice` with the ended line's text, no recipient, and the project the thread ended in (`last_project` of its session, as `end_by_rule` reads it; else the task's `project` when this machine knows it); `endedLine` is set only when something was appended.

`board_notice` is new and leaves `cmd_say` as it is. It shares with `say --notice` the one thing both need, the append of a `human` event marked `notice` under the machine's own writer with its receipt, which M2 factors out of `say_into` as a function both call; validation, tag resolution, audiences, `--pools`, output and exits stay `cmd_say`'s. `board_notice` writes one event with `notice: "tasks"`: to one recipient given as `{session, alias}` from that session's own row in the project (`member_row`; no alias is resolved), marked for the live alone when asked (the mark an `@all` carries, with one recipient); or to nobody. For an addressed one it then delivers as a sender's own call does (`deliver_next(..., due=True)`) and answers that call's outcome for the event, or `owed` when the call gave none for it (it waits for its writer's head, a gate, an earlier event). It prints nothing and never exits: a session that is no member (`not-addressable`), a machine whose name no notice is read under (`no-writer`) and a log that refuses (`log-refused`) answer `none` with that word, and in each nothing was appended. It takes no lock of the store's.

`sminos_daemon`'s hourly duty (`override_duty`) calls the tasks' module's `hourly()`: it resolves each sending that has been due for more than a minute, binds each pair it can (§2), and removes each task whose `state` is not `open`, whose closing is more than 30 days old and none of whose outcomes is waiting, with its `applied` keys, and each successor pair that is in no task's chain. Any exception is a line in `daemon.log`. Nothing else of the daemon's touches the store.

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

**At its end.** From a session's shell, `sminos task assign` puts a task in the machine's store and prints its id; `revise`, `comment`, `withdraw` and `reopen` change it under D2's rule of who may; from a terminal that is no session, `sminos task list` and `show` read the board with each task's target and its state, and `done`, `decline` and `comment` act through the door, which refuses a stale revision, applies an act once by its key, and refuses a session. Every act of the human is named to the asker at its next start, by a line of its own, once; the asker reads the human's words with `show`. A `/clear` sminos witnessed makes the new session the task's target. `sminos/types/tasks/` is published at version 1 and the commands are held to it.

**Touches.** New `S/sminos_tasks.py`; `S/sminos.py` (the parser's `task` family, the early dispatch, the usage text, the call in the record hook's clear path before `release_alias`); a new SessionStart shell hook `sminos/hooks/smns-tasks.sh` beside `smns-guide.sh`, and `sminos/hooks/hooks.json`; new `T/tasks-contract.gen.py`, `sminos/types/tasks/` (written by it), `T/test_tasks_contract.py`, `T/test_tasks.py`, `T/test-tasks-hook.sh`; `T/run-sminos-tests.sh` (the suites, in the list with room); `S/CLAUDE.md` (a paragraph, as the sheet has one); `sminos/hooks/CLAUDE.md`; `sminos/CLAUDE.md` (one sentence and the pointer); sminos's version.

**Interfaces.** Exposes §1, §2, §3 (all but `status`), §5's texts and the store's steps to every later milestone, and X1, X2, X3 to B1a, B2 and B3. Consumes sminos's threads (`threads.current_record`, `get`, `record_ended`), `sminos_records.lane_of` and `unreadable`, the engine's records as `running_now` reads them and a process's start time (`process_started`), `wake_here`, `cleared_witness`, `member_project_now`, `member_row`, `last_project`, `flocked`, `write_json`, `json_at`, all as built.

**Decisions.**
- The generator comes first and is written by hand from the composite and §1 to §3 and §5: the schemas, the texts' grammar with an example of each form, and at least these fixtures: an assign that makes the store; a second; a revise; a done at the current revision; a done at an old one, `stale`; a decline; a comment by the human; the same line twice under one key; another line under that key, `refused`; a `seen` naming an older `seq` than a later revise, which stays Updated; a `shown` for a task, some of its keys taken and one passed over as another session's; a withdraw; a reopen (its `closed` null again); an act on a closed task; an unknown id; an unknown field kept through a write, at the top and on a task; a successor's pair, unbound and bound; a successor that handed off; a purged successor; a `remind` and the `shown --keys` that follows it; and a store holding an outcome for each `told` and for each value of `send` (null, `due`, `sent` by `tell`, `sent` by a notice for the live alone and by one that may wake, `none` for each refusal), so what M2 fills is frozen now. The generator's own check (`--check`) is what the contract suite runs.
- A writer never rebuilds a task from the fields it knows: it changes the parsed object in place.
- `target_of` is one function used by `list`, `show`, `waiting`, the door's decision, `is_asker`, `remind`, and later the sending and B1a's predicate, so the card, the verdict, the rights and the telling cannot disagree about whom a task answers to.
- The door reads all its lines and checks each against its act's line before applying any: a call with one bad line applies nothing (exit 2). Each line's step is its own replace.
- **The start hook is two calls with the engine between them.** `smns-tasks.sh` is a hook of its own, not behind `smns-guide.sh`'s enrollment test: when `tasks/state.json` exists and `SMNS_INTERNAL` is unset it runs `sminos task remind` with the payload's session and source, takes the first line as the keys, prints the rest (which the engine adds to the session's context as it adds the guide's), and only then runs `sminos task shown --keys` with exactly those keys (and with none, still, so that the session's pair is bound). It starts no Python where there is no store, prints nothing when `remind` fails, never blocks a start, and exits 0 on every path. Printing first and marking second means a failure between them shows the same acts again at the next start, and a failure of the mark alone does too; it cannot mean the model read them, and nothing here says it does.
- The lock is `fcntl.flock`, exclusive, 10 s, the file never unlinked (the sheet's kind); the replace is a synced temporary file in `tasks/` and `os.replace`.
- Pitfalls seen in the code: `S/sminos.py`'s `main` runs `migrate()` before most verbs, and a hook's call must not wait on it (§3's early dispatch); `members()` and `view_of()` write, so nothing here calls them; `running_now` reads the engine's records afresh at each call, so a `list` of many tasks reads them once and shares the reading; `threads.current_record` leaves out ended records and `thread_of` can answer a record that only once held the session, so `target_of` reads the asker's thread by its id and checks its current session; `lane_of(None)` answers A for a record that is missing and for one that cannot be read, so the second is asked for first; `cleared_witness` stops answering once the alias is released, which is why the pair is written before it.

**Does not touch.** The `task` plugin, any mod, the daemon, `cmd_say` and the notice path, the bridge, the ending pass, anything of the sheet's.

**As built** (what later milestones consume; the readings the set fixes are in `sminos/types/tasks/README.md`, "Readings fixed with the set"). In `S/sminos_tasks.py`: `step(change, create=False, wait=…)` is the store's one writing step; `target_of(store, task, memo=None)` and `is_asker(store, task, session, memo=None)` share a memo, one per call (the door makes one for all its lines); `bind(state, session)` is §2's in-place bind, for use inside a step (M2's hourly duty), and `bind_step(session)` its locked wrapper; `cleared(left, begun)`; `told_of(target, outcome)` is M1's stand-in for §3's table, never answering `now` or `wake` and writing `send: null`, which M2 replaces with the table and `send: due`. Readings M1 settled: every line's first verdict is kept by its key, `applied`, `stale`, `closed` and `unknown` alike (the last under the id the line named), so the same line again answers it and changes nothing, and `refused`/`key-reused` is not kept; a door line where no store exists makes the store, so its `unknown` is kept too (re-judging a refusal was tried and dropped: a keyed comment refused `closed` would apply after a reopen, and a `done` on an id not yet made would apply once the id was); refusals in the order key used, `unknown`, `closed`, `stale`; `seen` only raises `seenSeq`, never past the store's `seq`; a new task is not Updated; every field a line lists is required, `wake` included, and types are checked strictly before anything applies (exit 2); the id is D2's `t[1-9][0-9]*` with no cap, everywhere. The readers (`list`, `show`, `waiting`) are dispatched ahead of the migration, as `remind` and `shown` are, and leave the whole home unchanged. `remind`'s bind waits at most 3 s and is skipped on a busy lock; its pair write on `--source clear` waits the full 10 s, as the record hook's does, whose 5 s alarm and wall-clock deadline are both moved by the time the pair write took, so the alias release keeps its budget; the start hook's timeout is 30 s. D9's fork sentence has its own frozen text in the grammar. The record hook's pair write is unbound at first (the new session's thread record is made after the release), and bound by the record hook once its join has made the thread (best-effort, after the release), and by the new session's own next step. `cleared` keeps a pair naming the same session begun and replaces one naming another. The door's memo is emptied when a step reads other pairs than it was filled under. The set holds 23 fixtures and `examples/rejected.json`: lines the schema admits and the door refuses (an integer with a fraction or exponent; a text with a lone surrogate), the two wire rules the README states beside the schema.

**Proves.** The composite's A1, A2's list, A3, A5 and A8's first sentence in their `sminos task` form (the verbs' names in `task` are M3's; the line and the notification are M4's), and X1 to X3. Its tests pin, beyond acceptance: two `assign`s at once from two processes get two ids and neither is lost; a kill between the temporary file and the replace leaves the store as it was; the same line twice changes nothing and answers the first verdict, `told` included, with the target's state changed between the two; a command of version 1 that waits for the lock behind a writer of version 2 refuses once it reads the file, and `show`, `list` and `waiting` still read it; `is_asker` true for the target and the thread's current session, false for a second session with no thread, for a fork, and for a session that filled the seat before; `target_of` for a running thread, a stopped one with and without a stop mark, a held one, an ended one, an ended one whose process still runs, a retired and purged one, a cleared one with a running successor, with a stopped successor, with a successor that has no thread record yet and runs, with an ended successor, with a purged successor (bound: its record gone; unbound: its retirement in the log), with a successor that handed off to a third session (that session is the target and may revise; the successor's old id, opened again as a thread of its own, is neither), cleared twice, cleared forty times in a row (the last living one), a pair that loops, the left session opened again after the clear and the left session still held by the clearing process (not opened again), a session that took the left one's alias and is no successor, a session with no thread, a session that assigned with no thread, later became a member and was cleared (its successor is neither the target nor the asker), a lane B session with a thread record whose process is gone (`gone`, `maws`), a lane record that cannot be read, and a thread record that cannot be read; the pair is written before the alias is released, once whichever of `sminos record` and `remind` runs first, and by `remind` alone when the record hook was cut short before its release; a session at the door exits 3 and changes nothing; the 501st open task is refused, by `assign` and by `reopen`; a done, a reopen with a comment and a second done within one millisecond print in that order; a reopened task is not pruned as closed; `show` prints a done's note and a decline's reason; `list --json`, `show --json` and `waiting --json` run twice over an unchanged store leave the file's bytes and `seq` as they were, and only the text `show` with no session sends a `seen`; `waiting` lists an unshown outcome of a task closed 40 days ago, and `waiting --mine` lists the twenty-first of 21 closed tasks' outcomes that the start line's count points at; `done` exits 3 on a stale revision and prints the verdict; `done --key K` twice applies once and prints the same verdict, a comment with the same text and no key twice makes two comments, and the key is printed before anything is applied; `remind` for nothing (an empty first line), for open tasks, for waiting outcomes, for more than twenty (the count, and the rest at the next start), for a fork, and on a scratch home with no enrollment; with 25 waiting, `remind` names 1 to 20, another start (and, apart, a door's `shown`) marks 1 to 20 first, and this start's `shown --keys` then marks nothing more: 21 to 25 still wait; `shown` for a session that is no longer a key's target marks nothing; `test-tasks-hook.sh` runs the real hook: its output is the start line without the keys' line, the outcomes are marked after it and not when `remind` fails, when the hook is killed between its two calls, or when the mark fails; no text `remind` prints holds a task's title or body; every published fixture replays.

**Gate.** `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,shell-lint,version-bump`.

### M2 — Telling the asker now: the notice, the subagent's message, the wake

**At its end.** A done, a comment or a decline of a blocking task reaches a running asker at once: sminos delivers the board's notice, an idle session starting a turn with it and a busy one reading it at its next tool round. A stopped thread is woken for it when the human's choice says so, or held with sminos's reason; an act that did not ask is never the cause of a start, however late its notice comes to be pushed. A running subagent that assigned the task is told itself. An ended thread's act leaves one line in the log of the project it ended in. The door's `told` says `now` and `wake`, and the task shows what was sent and what sminos answered then. A closed task whose acts have all been shown goes after 30 days.

**Touches.** `S/sminos_tasks.py` (the door's sending, `send`, `tell_agent`, `hourly`); `S/sminos.py` (`board_notice`, and the append it shares with `say_into`); `S/sminos_daemon.py` (the hourly duty's call); `T/test_tasks_telling.py`; `T/run-sminos-tests.sh`; `S/CLAUDE.md`; sminos's version.

**Interfaces.** Exposes §5's sending to M4 (the `tell` path is exercised live there) and to B3. Consumes M1's store, `target_of` and the frozen shapes; `say_into`'s append of a notice, `deliver_next`, `wake_here`, `last_project`; `sminos_control.post_command` and the bridge's `tell` op as built.

**Decisions.**
- The append shared with `say_into` is taken out as it is, stream choice and receipt included, and `say_into` calls it; `cmd_say`'s behaviour, its output and its exits do not move, and `T/test_notice.py` passes unchanged.
- **A notice for the live alone to one recipient** is the mark an `@all` carries (`wake` true on the event, in sminos's sense: it reaches only a recipient whose process runs and settles `recorded` otherwise) with a `to` of one. No command writes that today. M2 checks what a one-recipient event of that kind makes of its frame's target (`frame_of`, `target_label`) and, where it would read as a broadcast, gives it the addressed label there, in a change of its own with a test in `T/test_notice.py`'s manner.
- The board keeps what sminos answered at the sending and reads nothing of sminos's delivery record afterwards. `send.answer` is shown on the card as "what was sent"; the card's "stopped, held" comes from `target_of` at the read.
- The hourly duty's prune also removes `applied` keys of ids that name no task (M1 keeps an `unknown` verdict by its key) once they are 30 days old: they belong to no task, so the prune of a closed task with its keys never reaches them.
- A `tell` is tried only for an outcome the table sends now, to a subagent of a running `terminal` session, whether or not the session is addressable.
- **A due sending is resolved by whoever comes next.** Every call of the door, before its own lines, resolves each sending on this machine that has been due for more than a minute; the hourly duty does the same. The act's verdict is not touched by it. Two that find one due can both send: two notices then name one act, which is stated and not prevented, since neither can wake against the human's choice.
- U2's live check is made here, by hand, on a machine whose installed sminos is this branch (a background wake does not carry `--plugin-dir`, so a scratch home with the branch loaded by flag proves nothing about a woken thread), with nothing else owed to the sessions used. Each case is observed and written down, and R12 is what is required of a frame the engine admits: (a) an idle session whose task is completed starts a turn with the notice; (b) a busy one reads it at its next tool round; (c) a needed task completed while its session runs, the session stopped before the notice is pushed (a held writer will do): nothing starts; (d) a spawned seat assigns a blocking task and is stopped, `sminos task done` answers `wake`, and the seat runs with the notice; (e) a session that bypasses permission prompts: whether the engine holds the frame, as sminos's own account says it may; (f) where a machine cut over to the reach and words gates is at hand, the same, the answer read as it comes. The check reports a setup that did not load this branch as its own failure. A seat that a notice alone does not wake, or an engine that holds the frame in the mode the owner's sessions run in, stops the milestone and goes to the composite's writer; the start line tells the asker in every case.
- Pitfalls seen in the code: `say --notice` is refused when a session's id is in the environment and when the machine's name is not one a notice is read under; the door is never a session, and the second answers `none`, `no-writer`. `say --notice` tagged to an ended thread exits 4 with nothing appended, which is why the ended line has no addressee. A thread ended by the rule is a member of no project any more (`member_project_now` gives none), which is why the ended line's project is the one it ended in. A notice's recipient must be a member of the project it is written in: the project is the target's membership now, not the task's `project` at its assign. An addressed event that is not for the live alone wakes a stopped thread whenever it comes to be pushed, by the daemon or the uplink, long after the door: only the event's own mark prevents it.

**Does not touch.** Any mod; the bridge's `tell` op itself; `deliver_next`; `cmd_say`'s behaviour; the ending pass (B1a's); anything of the sheet's.

**Proves.** A4 (the verdict, the notice in the log without the note, what the task shows), A6 and A8 in their command form, and X6. Its tests pin: the door's decision for each row of §3's table, each kind and class, and each of `wake` true, false and null; each text's form, and that none holds the task's title, body, an agent's comment, an alias or a subagent's name; an addressed notice that may wake wakes a stopped thread once; a notice for the live alone whose recipient has stopped before the push settles with nothing started, and with the push delayed behind a held writer too; a held thread's answer is kept as given; a `tell` the stand-in bridge queues writes no notice; a `tell` it refuses, one with no socket, and one that times out each go on to the notice in the subagent's-thread form, by the table as the target then stands; a `tell` is not tried for a MAWS-run session, for an outcome that is not sent, or for a target that is not the session that assigned the task (a successor is sent form B, a session a hand-off went on in form C, and a subagent there with the same id is told nothing); a session that is a member of no project resolves to `none`, `not-addressable`, and the verdict still says `now`; a door killed after its replace leaves `due`, the same line again answers the stored verdict and resolves the sending once the minute has passed and not before, another task's act resolves it too, and so does the hourly duty with no act at all; a refusal resolves to `none` and is not tried again; the ended line is written to the project the thread ended in, with no session's name in it, once, and `endedLine` stays null when nothing could be appended; a closed task 31 days old with a waiting outcome stays and one with none goes with its keys, a `shown`'s key among them; `say --notice` behaves as before (`T/test_notice.py` unchanged).

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
- In a session where function hooks are off none of this runs: a task there names no subagent, and its acts are told as any are. A session marked `SMNS_INTERNAL` registers nothing.
- **The live checks** (U1, and A7). `live-tasks-check.py`, in the manner of the other `live-*` checks: it drives real sessions and spends model calls, so it is run by hand and not in a gate. Cases: `attributed` (U1: a subagent's `task assign-human` or `sminos task assign` under an allow rule for the verb, one under a rule that names arguments, one with a classic `PreToolUse` hook that prints its input, and one whose command also holds a secret's handle, each observed and written down as found), `subagent` (A7: completed while the subagent runs, the message is in the subagent's transcript and absent from the main one; completed after it ended, the notice in the main conversation names its id). What `attributed` shows is written beside D2 by the composite's writer.

**Does not touch.** The store's rules; the door; `board_notice`; the bridge; anything of the sheet's beyond reading how its band is drawn.

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
    bash sminos/tests/test-tasks-hook.sh

By hand, with a scratch store and a stand-in session id:

    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task assign --class blocking --title "Log in to the console" --body-file - <<'EOF'
    Open the console and sign in. Done when the dashboard loads.
    EOF
    # t1 blocking "Log in to the console"
    sminos/bin/sminos task list
    # t1  blocking  "Log in to the console"  …  (gone)  due —
    sminos/bin/sminos task done t1 --note "logged in"
    # key 5eed0000-…            (on standard error, before anything is applied)
    # {"v":1,"key":…,"act":"done","verdict":"applied","task":"t1","revision":1,"state":"done","outcome":"t1.1","told":"next-start"}
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task done t1; echo $?
    # … an agent's session does not complete the human's task …   3
    sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # t1.1
    # The human acted on tasks you assigned: marked t1 done. Read one: sminos task show t1
    sminos/bin/sminos task shown --session 5eed0000-0000-4000-8000-0000000000a1 --keys t1.1
    sminos/bin/sminos task remind --session 5eed0000-0000-4000-8000-0000000000a1
    # (an empty line: nothing waits)
    CLAUDE_CODE_SESSION_ID=5eed0000-0000-4000-8000-0000000000a1 sminos/bin/sminos task show t1
    # … done  <time>  "logged in"

**M2.**

    python3 -B sminos/tests/test_tasks_telling.py
    python3 -B sminos/tests/test_notice.py                   # passing, its existing cases unchanged

**M3.**

    bash task/tests/run.sh

**M4.**

    bash sminos/tests/mods/run.sh
    python3 sminos/tests/mods/live-tasks-check.py attributed subagent    # spends model calls; by hand

**The acceptance (M5)**, on a Mac whose daemon serves the home in use and whose installed plugins are the released ones, in a scratch project, with nothing else owed to the sessions used; none of it on a scratch store. Each step is the composite's item of the same number.

1. In a terminal session, ask the agent to run in one Bash call, each command under `time`:

        time task assign-human --class blocking --title "Log in to the console" --body-file - <<'EOF'
        Sign in to the cloud console. Done when the dashboard loads.
        EOF
        time task assign-human --class needed --due 2027-01-05 --title "Rotate the signing key"

    Expect two lines, `t<n> blocking "Log in to the console"` and `t<m> needed "Rotate the signing key"`, each `real` under one second, and the turn going on.
2. In another terminal: `sminos task list`. Expect the blocking row first, each with the project, the session's alias and `(running)`, and `due 2027-01-05` on the needed one. In the session's terminal, expect `2 tasks for the human (1 blocking) · sminos task list` above the prompt, and one notification on the machine, for the blocking task.
3. Close the session's terminal. Run `sminos daemon tick` twice, then `sminos task list`: the blocking row reads `(stopped, to be woken)`.
4. `sminos task done t<n> --note "logged in with account B"`. Expect `"told":"wake"`. Then `sminos list` shows the session running in the background; its transcript holds the `tasks` notice (`[tasks v1] The human marked t<n> done, a task you assigned. …`) and its start context the start line naming the same act, neither with a title; the session runs `sminos task show t<n>` and its output holds the note; `sminos task show t<n> --json` shows the outcome's `send` as `sent`, how `notice`, not for the live alone, and its `shown` naming the session; `sminos chat` for the project shows one `tasks` notice and not the note.
5. Tell the session (`sminos say @<alias> …`) that the console still asks for a login. Expect it to run `task reopen t<n> --comment "…"`; `sminos task list` shows `t<n>` open, `Updated`. `sminos task done t<n>` answers `stale` with revision 2 and exits 3.
6. In a second session: assign a needed task, `/clear`, go on in the same terminal. `sminos task show` of it names the new session as its target. Rename a third session to the cleared one's old alias. `sminos task done --wake` of the task. Expect the notice in the new conversation with `a task assigned by the conversation this one replaced at a /clear`, no background process for the cleared one, and nothing in the third session.
7. Have a session dispatch a subagent that assigns a task and keeps working. `sminos task show` names the subagent. `sminos task done` while it runs: the message is in the subagent's transcript and the main transcript holds no `[tasks v1]` line for that task. Repeat with the subagent ended: the notice is in the main conversation, naming the subagent's id.
8. Stop a session that has a needed task and complete the task with no flag: `"told":"next-start"`, no background process; open the session again: its start context holds `The human acted on tasks you assigned: marked t<k> done`, and no notice arrives. In an idle session, decline an optional task: no turn starts. Then, with B1a landed and `SMINOS_THREAD_END_AFTER` set to a minute: a stopped thread with an open blocking task is still there after an ending pass (`sminos daemon tick`), with one line in `daemon.log`; decline the task with `--no-wake` and the next pass ends it; a stopped thread with only a needed task is ended, and completing that task answers `"told":"ended"` with one `tasks:` line in the project's log.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

- **D5, a successor** ("A successor (R13)…"): a witnessed `/clear`'s pair has two writers, `sminos record`'s clear path before `release_alias` and `remind --source clear`, each waiting the store's full 10 s lock; when both fail (each past its wait, or each raising), the alias is released and no pair is written, so the outcomes and the revise rights stay with the conversation left, whose start line still names them. The alias release is deliberately not made to wait on the store (the composite's writer accepted the limit, 2026-11-27). D5 should state it as a limit, in D9's manner.
- **D9, a fork**: the fork's sentence at its start is frozen in the published set's grammar (`sminos/types/tasks/grammar/texts.md`), with its own fixed words; D9's wording describes it and no longer stands alone.
