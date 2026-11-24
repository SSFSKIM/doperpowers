# Question sheet, C2 — the sheet in sminos: execution (2026-11-23)

> **Composite:** `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`
> in the MAWS repository, child **C2** (The sheet in sminos). **Parent pin:**
> MAWS commit `277d8a520` (the composite with C0's verdicts, the owner's
> ruling on §2.4, and the rulings on this plan's first review, in the
> shapes this plan gave them). **Ticket:** MAWS board #867, a child of
> #600. The child's section in the composite ("### C2: The sheet in
> sminos") is its spec; the composite's §1 to §7, §8.3,
> §9's import and §11 are its design, binding where the composite's
> "Grades" paragraph says; X1, X2, X3 (the block's schema and the terminal
> form), X4 (the schema), X6 and X7 are the contracts it owns. This
> document carries the constraints, the state machine, the interfaces and
> the milestones, and nothing of the design. Written against doperpowers
> `b43da6bcd` (sminos 1.56.0) and the engine's hook declarations of Claude
> Code 2.1.323 (`sminos/.claude-plugin/types/claude-code/index.d.ts`, laid
> by the engine; the installed engine was 2.1.331). Read before M1: the
> composite whole; `sminos/hooks/mods/README.md`, its sections "ask" and
> "Developing"; `sminos/hooks/mods/CLAUDE.md`, its first paragraph and the
> paragraph on lane B;
> `docs/doperpowers/specs/2026-10-13-ask-async-design.md`, "How the engine
> is reached".

After this child, a terminal session that has the setting on asks through
a sheet. The agent calls `mcp__sminos__AskUserQuestion` once with eight
questions, one naming a file; the call returns `Added q1, q2, q3, q4, q5,
q6, q7, q8.` at once and the terminal shows `8 open questions` above the
prompt. `sminos sheet show <session>` lists the eight with the file as it
was when asked. `sminos sheet answer` on three of them, sent as one batch,
reaches the agent as one message naming the three by id, at its next tool
result or at once when it is idle; five stay. The agent rewrites one and an
answer sent against the old wording is refused as stale. With the terminal
closed the questions can still be read, answered and the answer taken
back; after the resume the answer leaves with the first prompt, marked
with its age. Everything else in use today is as it was: with the setting
off, or no surface to answer on, the session has today's tool. How to see
each of these is Concrete Steps; what closes the child is its three gates
in the composite (G1, G2, G3), mapped to milestones under Plan of Work.

## Progress

- [x] (2026-11-23) This plan written against the composite at `ad4427f93`
  and doperpowers `b43da6bcd`; its entries for the composite's writer
  taken into the composite (`d5cdf48b8`).
- [x] (2026-11-23) The plan's buildability review: eighteen findings; the
  composite's writer ruled on what was the composite's, and this revision
  repairs the rest.
- [x] (2026-11-23) C0's verdicts for P1 to P5 (engine 2.1.331) written
  in where each decision stood ("What the probes settled").
- [x] (2026-11-23) The narrower review of what M1 freezes: twelve
  findings, ruled on and repaired in this revision. No third review of
  the document follows: M1's task review and the high-rung review of its
  pull request check the published set from here, and a change to the
  set after M1 is a ruling and a re-pin (K2).
- [x] (2026-11-24) M1 — The contracts, published (G1): merged to main as
  `2594002af` (pull request #628, head `a45f529ee`), sminos 1.57.0, set
  version 1, digest
  `594200ae4e539c0688c67b511968861d8ebf03c87d1c45b512903a538326e277`
  (21 cases, 6 examples). Its high-rung review ran two passes: eleven
  findings repaired, then seven, five repaired and two logged in
  `docs/doperpowers/TECH-DEBT.md` (#37, #38). MAWS pins this commit.
- [x] (2026-11-24) M2 — The record: the step, the lock, the command's
  other verbs. Commits `97218983c`, `09b485a94` (the I8 ruling on reading
  registrations), fix waves `17c2827c2` and `b204a4e56`; sminos 1.58.0
  (the one bump of this pull request). Task review: one Critical (a late
  call applying again across the acknowledgement's replace), six
  Important, three Minor, then one Critical of the first fix (a start's
  identity, now its nonce) and three Important, all repaired; clean on
  the third pass. Every published fixture and all seven envelopes replay
  byte for byte; `test_sheet_step: 79 passed`; gates GREEN (run
  45375809111). Also repaired: M1's reader printing a queued entry's
  field of another kind (the composite's writer's ruling).
- [ ] M3 — Asking: the start choice, the sheet's schema, a call. Blocked
  by: M2.
- [ ] M4 — Delivering: the routes, landing, a start, subagents. Blocked
  by: M3.
- [ ] M5 — The terminal's drawing, and the import of today's asks. Blocked
  by: M3.
- [ ] M6 — The other readers, and the sheet's end of life. Blocked by: M4.
- [ ] M7 — The description, what is written beside the code, the
  acceptance (G2, G3). Blocked by: M5, M6; C1.
- [ ] The merges (M1's alone and first: done, `2594002af`; the rest as
  its gates hold).

## Words this document adds

The composite's Terms define terminal session, MAWS-run session, the tool,
sheet, question, asker, surface, the page, the bridge, today's tool and
envelope. Added here:

- **The mod** is the sminos plugin's hooks module (`sminos/hooks/mods/`,
  loaded by the engine under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`); `$` is
  the engine interface a hook receives. **The command** is the `sminos`
  CLI (`sminos/skills/sminos/scripts/sminos`, Python).
- **The record** is one session's sheet directory (composite §3).
- **The step** is the one operation that changes what a record's
  `state.json` says of the sheet: `sminos sheet step` (I5). The mod
  orders it and nothing else does; it is the tool's hand on the file.
  **An event** is what a step is ordered to do (I5's list).
- **The door** is `sminos sheet put` (X2): the one operation that appends
  to a record's inbox.
- **A drain** is the part of every step that applies the inbox lines not
  yet applied (composite §4.2).
- **The view** is what a step answers the mod: the record cut to what the
  mod draws and routes from, bounded (I5). **A ready envelope** is the
  next envelope for one recipient, composed by the step and carried in
  the view.
- **The staging** is the directory where the mod leaves a step its large
  input (I1).
- **A route** is one way an envelope reaches the main conversation in a
  terminal session (I9): **idle** (a prompt the mod submits), **result**
  (context on the model's next tool result), **prompt** (context on the
  next prompt that enters). **A flight** is one envelope on a route, from
  the moment the mod hands it over until it lands or fails.
- **Landing** is the evidence that a conversation holds an envelope (I9).
- **Owed across a stop** describes an outcome that was pending when a
  process started, or was applied by that start's drain.
- **Owed to the log** describes a project-log event the record holds
  until the log has it (I12).
- **The published set** is `sminos/types/sheet/` as M1 merges it (I1).
- **The stand-in surface** is `sminos/tests/sheet_surface.py`, which
  writes and heartbeats a surface registration so a session offers the
  sheet where no page runs yet (C4 builds the page). As built: name
  `standin`, url `http://sheet.localhost:47590`, reach `local` by
  default; a heartbeat every 10 s (`--every`); written at 0600 from a
  temporary file, as `mawsd` writes; removed on SIGTERM and SIGINT;
  `--once` leaves a registration whose pid is gone.

## Verification

- This document: one buildability review, then a narrower one of what M1
  freezes ("What M1 freezes", below); both are done (Progress).
- Each milestone: the task review of doperpowers:subagent-driven-execution
  at its boundary. M1 (it freezes X1), M2 (the transition table) and M4
  (delivery) are reviewed before anything downstream starts on them.
- The branch: doperpowers:review-code at **high** (the composite's
  Verification: a fault here loses or duplicates the human's answer), once
  for M1's pull request and once for the rest.

## Constraints on every milestone

**Binding inheritance** (the composite's Execution, "Constraints on every
child" and "Grades"): the engine is unmodified and reached through
function hooks only; §1's shape; §2.1's ownership rule and the tool's
name; §3 (the directory, one writer, readers read the file); §4; §5.1;
§5.3; §6's routes; §7; §9; X1, X2, X3, X4, X6, X7. Nothing the owner uses
today stops working at any step: the sheet lands beside today's tool,
behind `SMINOS_QUESTION_SHEET`, whose default this child does not change.

**Facts of the environment** the design below rests on, each read from the
engine's declarations or measured:

- A hook has no rename, no append, no delete and no lock: `$.fs` reads
  a file, writes a whole text, lists, tests and stats, and one read or
  write is refused past 4 MiB. `$.process.run` returns at most 4 MiB of a
  child's output and says when it cut it. A question with previews and
  context can pass 100 KiB, so a record can pass what one read takes.
  This is why the record is read and written by the command, on the
  mod's order (K1), why the mod never reads `state.json` itself, and why
  everything that crosses between the two is bounded (I5).
- One entry of a hook's `context`, on a prompt or on a tool's result,
  reaches the model whole only up to 100,000 characters (200,000 for the
  entries together); past that the model reads a head and a path
  (`PromptSubmitInput.context`, the tool result's `context`). This is
  why an envelope has a budget (I7).
- `$.session.send` resolves for a message that was not delivered too:
  `{ isDelivered: false, reason }` when the recipient is gone or a hook
  refused (`SessionSendResult`).
- `session.append` hands a hook the row before it is stored; `next(e)`
  resolves with the row as stored, after any rewrite beneath. The event
  carries the row's `door` and `origin` (`hook-context` with `{ kind:
  'plugin', event }` for a context a plugin's hook attached; a prompt
  with `{ kind: 'plugin', name }` for one a plugin submitted).
- C0's verdicts (`spikes/protocol-probe/findings-qsheet-c0.txt` in MAWS,
  branch `question-sheet-c0` at `10f54e4d0`, engine 2.1.331) are facts of
  the same standing; "What the probes settled" lists what each fixed.
- `$` is followed only into functions of the file that received it, and
  is never kept in a variable; what another file needs of the engine it
  gets through a closure made inside a hook of the owning file (the `Out`
  pattern of `ask.tsx`). `claude plugin validate`, which
  `sminos/tests/mods/run.sh` runs, is the check; a module the loader
  refuses loads in no session whatever its tests say.
- A hook's budget is 10 s and does not run during its own `$` calls or
  `next`; it does run while the hook waits on anything else. So a hook
  never waits on another hook's work: a drain a hook only triggers is not
  awaited (K4).
- `session.start` is raised again when the module reloads; the classic
  `SessionStart` is raised once per session start (`startup`, `resume`,
  `fork`, `clear`, `compact`) and never at a reload.
- One `sminos` invocation costs about 0.3 s (measured on the owner's
  MacBook: the launcher imports `sminos.py` whole). A step happens when
  an agent calls the tool or a human answers, never per tool call (K4).
- `sminos <verb>` migrates the registry and waits on its lock before most
  verbs. `sheet` verbs given `--session` are dispatched before that, as
  `bridge` is in `main()` of `sminos.py`: they are called from inside a
  session's hooks and read no registry.

**Rules.**

- K1 · **One step, in the command.** Every change of the sheet in
  `state.json` is one step: a read-modify-write of the file under the
  record's lock, run by the command on the mod's order, ending in an
  atomic replace. The mod holds no authoritative copy; it keeps the last
  view. The alternative, a mod that holds the sheet in memory and writes
  it through `$.fs`, cannot replace atomically, cannot share the door's
  lock, and loses an update when two processes hold one session id; it
  lost. One other operation rewrites the file, under the same lock and
  the same way: the log's projection, which only takes away what it has
  written to the log (I12).
- K2 · **The published set is frozen at M1.** After M1 merges,
  `sminos/types/sheet/` changes only on a ruling of the composite's
  writer (X1); such a change raises the manifest's `version`, and MAWS
  pins again. Vectors a later milestone needs go under
  `sminos/tests/sheet-vectors/`.
- K3 · **Today's tool is not edited beyond its yield** (M3), its
  search's forms as a parameter (M4) and the definiteness of its
  transcript read (M5). Its behaviour in a session whose choice is not
  the sheet is unchanged, and `ask.test.ts` passes unedited but for
  cases those changes add.
- K4 · **How a drain is triggered** (settled here; the composite's §3
  now states it). A drain is a step with no event of its own. The mod
  orders one: at each session start; when the door tells the bridge
  (`sheet`, I3); when its bridge's child says hello; when a subagent
  stops; and when a check finds the inbox longer than the view's offset.
  The check is one `$.fs.stat` of `inbox.jsonl`, made at every
  `tool.call`, `prompt.submit` and `turn.complete` the mod's hooks see
  and on a timer every 5 s (`$.clock.every`). The timer is there because
  a nudge can be lost (the bridge off by its seat rule, its child
  restarting) and an idle session dispatches no hook. Drains are
  single-flight: one runs, at most one more is remembered. Only the
  tool's own call and the nudge's answer wait for a step. No step but
  `start` is ordered for a session before that session's `start` has
  answered (I8).
- K5 · **Counting characters.** Every "at most N characters" of the
  composite counts Unicode code points, the same in Python (`len`) and in
  the mod (`[...text].length`). The envelope's budget alone counts
  UTF-16 code units (I7).
- K6 · **Times** are UTC, ISO 8601 with milliseconds
  (`2026-11-23T14:05:09.120Z`), as `sminos.now(ms=True)` writes them.
- Names and copy: the tool keeps its name; the command's verbs are I3's;
  no new environment variable beyond the composite's two.
- Gates: `sminos/tests/mods/run.sh` (the mods) and
  `sminos/tests/run-sminos-tests.sh` (the command), on GitHub Actions
  through `ci-gate` (gates `sminos`, `sminos-suites-a` to `-c`,
  `sminos-mods`, `sminos-idle`, `version-bump`, `shell-lint`,
  `mods-types`). New Python suites go at the end of `run_suites_c`. The
  live checks spend model calls and run by hand on a Mac.
- Versions: `sminos/.claude-plugin/plugin.json` and the marketplace entry
  rise with every pull request that changes a shipped file (the
  `version-bump` gate; `types/` and `tests/` do not ship). M1 lands as
  the next minor version (1.57.0 against `b43da6bcd`).

**What M1 freezes.** Everything a second repository reads, each in one
place below, so it can be read before M1 is dispatched:

| frozen at M1 | where |
|---|---|
| the record's files and what a reader may look at | I1 |
| `state.json`: structure without the input's bounds; `calls`; `log`; `import`; an outcome's `textFile`; a closed question's `answer`; the verdict of a key never seen | I2 |
| the inbox line and its bounds; the door's exits and output | I3 |
| what a reader computes: that it stops at the last newline whatever a probe says; `closed`; a pending outcome's question | I4 |
| the three first lines of a call's result | I6 |
| the envelope: its two limits, a long text's file, the block's places for `picks`, its `textCut`, `textFile` and `more`, and the published examples with their inputs | I7 |
| the fixture cases | M1 |

## The state machine

Fixed here before any milestone builds it. The composite gives the apply
table (§4.2) and the delivery rules (§5); this section adds who acts, the
complete event list, the states, the transitions the composite's table
does not carry, and the points at which a change is durable and visible.
I2 to I9 give the shapes these tables name.

### Who acts, and on which file

| actor | process | what it may change |
|---|---|---|
| the mod | the session's engine process (one per session; U8 for two) | nothing in a record: it orders steps, holds the view, the flights and the turn's state in memory, and writes a step's large input to the staging (I1) |
| a step | `sminos sheet step`, started by the mod, short-lived | `state.json`, `refs/`, `texts/`; it empties the staging |
| the door | `sminos sheet put`, started by a surface or by the command's `answer`, `dismiss`, `retract`; any number at once | `inbox.jsonl`, by appending |
| the log's projection | `sminos sheet log`, started by the mod, by the Stop hook's `sminos record`, by removal | the project's log; in `state.json` only `log`, which it shortens |
| a surface | the page's server, MAWS, the command line | `uploads/` (before the door names a file), its own registration |
| a reader | `sminos sheet show`, MAWS's reader, the page | nothing; it takes no lock |
| removal | `sminos sheet remove`, the daemon's sweep | deletes a whole record |

A step, the door, the projection and removal hold the record's lock (I1)
for all they do to the record. A reader holds none and follows I4's rule.

### Events

| id | event | raised by | how it reaches the record |
|---|---|---|---|
| E1 | add: an entry of a call without `id` | the agent | step `call` |
| E2 | revise: an entry with `id` | the agent | step `call` |
| E3 | withdraw: an id in a call's `withdraw` | the agent | step `call` |
| E4 | an `answer` line | a surface | the door; applied by the next drain |
| E5 | a `dismiss` line | a surface | the same |
| E6 | a `retract` line | a surface | the same |
| E7 | a `delivered` line | MAWS, for a steer its journal shows the model read (§5.4) | the same |
| E8 | a flight landed | the mod, on I9's evidence | step `landed` |
| E9 | a flight failed | the mod (a route's refusal, or a turn's end without the row) | nothing: the envelope is ready again, in memory |
| E10 | a subagent that is a recipient is not running, or a send to it was not delivered | the mod | the `agents` every step carries, or step `reroute` |
| E11 | a process starts a session (`startup`, `resume`, `fork`, the session after a `/clear`) | the classic SessionStart | step `start` |
| E12 | a compaction | the classic SessionStart, source `compact` | a drain that also composes I10's context |
| E13 | the module reloads | `session.start` with a kept choice | a drain, for a view |
| E14 | a subagent stops | the classic SubagentStop | a drain; a notice for the main conversation, in memory (I9) |
| E15 | `/clear` leaves a session | `session.end`, reason `clear` | removal of that session's record |
| E16 | a stopped session's record is removed | `sminos sheet remove`, the sweep | removal |
| E17 | a call's step gave the mod no answer | the mod | step `settle`, which commits or forecloses that call id |
| E18 | the mod holds a call's answer | the mod | `acked` on its next step, of any event |
| E19 | the project's log took what it was owed | the projection | its own replace, which shortens `log` |

Every step drains first, whatever its event (§3: a call drains before it
applies its own entries; the same order for every event keeps one path).
Only `start` makes a record: any other event ordered on a session with no
record answers `no-record` and changes nothing.

### States

**A question** is `open` at a revision, then closed one of three ways:

    open(r) ──revise──► open(r+1)
    open(r) ──answer line applied──► answered ─┐
    open(r) ──dismiss line applied─► dismissed ─┤ owed (its outcome is in `pending`) ──landed──► delivered
    open(r) ──withdraw─────────────► withdrawn  (nothing owed)

An open question is in `questions`; a closed one is in `closed` for the
record's life, with how it closed. No transition leaves a closed state.

**A sent line**, by its key:

    appended (queued) ──drain──► applied ──(answer, dismiss)──► accepted ──landed──► delivered
                               ├─► stale | closed | retracted | too-late      (a verdict; final)
                               └─► skipped                                    (U2: no verdict)

A key's first verdict is final (§4.2's last row). A key can have a
verdict before any line carrying it arrives: U1.

**A pending outcome**:

    ready ──a route opens──► in flight ──lands──► gone from `pending`
      ▲                        │
      └────── fails ───────────┘

with attributes a step sets: `recipient` (`main`, or a running subagent),
`taken` (the mod itself sends it to that subagent) and `acrossStop`.
`ready` and `in flight` are
the mod's memory; on disk both are "in `pending`". In a MAWS-run session
an outcome whose recipient is `main` is MAWS's to deliver and leaves on a
`delivered` line.

**A call**, by its call id, while the mod has no answer for it:

    ordered ──its step commits──► committed (its result is in `calls`) ──acked──► forgotten
       └──────settle finds no result──► foreclosed (in `calls`) ──acked──► forgotten

A foreclosed id commits nothing, whenever its step runs.

### Transitions

**The drain** is §4.2's table, in this order, over the lines from the
recorded offset to the inbox's last newline. Bytes after the last newline
are a write that did not finish (a door killed inside it, which the lock
does not prevent): the drain leaves them, as a reader does (I4), and the
offset stays just past a newline.

1. A line that is not valid is skipped (U2).
2. A line whose key has a verdict, or occurred earlier in this tail, is
   set aside; its key keeps the first verdict.
3. Retracts are resolved over what remains, before anything is applied:

   | the retract's target K | effect | verdicts |
   |---|---|---|
   | an answer or dismiss line among the lines that remain, before or after the retract | K is not applied | K `retracted`, the retract `retracted` |
   | a key with a verdict, of any kind, a `retracted` one included | none | the retract `too-late` |
   | a retract or `delivered` line | none | the retract `too-late` |
   | a key the record has never seen (U1) | K is never applied, should it arrive | K `retracted` with `kind: "unseen"` and `by` the retract's key; the retract `retracted` |

4. What remains is applied in file order:

   | line | the question | effect | verdict |
   |---|---|---|---|
   | answer | open, revision equal | → answered; an outcome joins `pending` | `applied` |
   | answer | open, revision differs | none | `stale`, with `current` |
   | answer, dismiss | closed | none | `closed`, with `how` and when |
   | answer, dismiss | no such id, ever (U3) | none | `closed`, `how: "unknown"` |
   | dismiss | open, any revision | → dismissed; an outcome joins `pending` | `applied` |
   | delivered, keys K… | — | each K in `pending` leaves it; any other K is left alone | `applied` |

5. The offset moves to just past the last newline.

An outcome that joins `pending` takes: `recipient` the asker when the
asker is a subagent, the step's `agents.running` names it and
`agents.direct` is true, with `taken: true`; else `main`, `taken: false`.
`acrossStop` is true when the step's event is `start`. A text longer than
2,000 characters is written to `texts/` and the outcome names the file
(I7). An applied answer or dismissal adds the `answered` event the log is
owed (I12) in the same replace.

**A step's own event**, after the drain:

| event | precondition | effect |
|---|---|---|
| any, with `acked` ids | — | each id's entry leaves `calls`; its staging directory is deleted |
| `call`, a call id in `calls` | — | nothing; the recorded outcome again (its result, or foreclosed) |
| `call`, a call id whose staging directory is gone | — | nothing; `gone` (the mod acked it, or a `start` cleared it: every fresh call has one, I5) |
| `call`, an entry without `id` | fewer than 500 open (U7); the mod refused nothing of it | a question `open(1)`, id `q<nextId>`, `nextId` + 1; the `question` event the log is owed |
| `call`, an entry with `id` | the id is open; the caller asked it; the mod refused nothing of it | the entry replaces the question; revision + 1 |
| `call`, a `withdraw` id | the id is open; the caller asked it, or the caller is the main conversation | → withdrawn; the `answered` event the log is owed |
| `call`, any of the above refused | — | nothing for that entry; the reason joins the result (I6) |
| `call`, in every case that reaches the entries | — | `nextId` is first raised to the event's `floor` + 1 when the record has assigned no id; the result joins `calls` |
| `settle`, a call id in `calls` | — | nothing; the recorded outcome |
| `settle`, any other call id | — | the id joins `calls` as foreclosed |
| `landed`, keys | — | each key in `pending` leaves it; `closed[id].deliveredAt` |
| `reroute`, keys | — | each such outcome: `recipient: main`, `taken: false` |
| `start` | — | a record is made if there is none; `calls` and the session's staging are emptied; every pending outcome: `acrossStop: true`, `recipient: main`, `taken: false`; a new record takes its floor when the event has one and, for a fork, `import.never`; today's asks the event carries are imported (M2's rule) |
| any, with `agents` | — | a pending outcome whose recipient is not in `agents.running`: `recipient: main`, `taken: false` |

Entries apply in the call's order, then the withdrawals; an id occurs at
most once in a call (§2.1), so the order among them decides nothing.
After its event a step composes the ready envelopes (I7), which writes
nothing. A question that an answer closes gets its `answer` line, and
the oldest of more than 32 such lines is dropped, in the same replace.

### Where a change becomes durable and visible

| change | durable when | a reader then sees |
|---|---|---|
| a surface's act (E4 to E7) | the door's one `write` of the line or batch has returned and been synced | the line as queued |
| a verdict with all it causes (the question closing, the outcome pending, its text's file named, what the log is owed, the offset) | the step's replace of `state.json`: one file, so all of it or none | accepted or refused; the question gone from the open list |
| an add, a revise, a withdrawal, with what the log is owed for it and the call's result in `calls` | the step's replace, which precedes the call's result | the question listed, changed, gone |
| a reference's body, a long text's file | written before the replace that names it | the reference with its body; the outcome with its file |
| a delivery | the replace of the `landed` step, which follows landing | delivered |
| a log event written | the projection's replace, which follows the log's own append | nothing (a reader does not look at `log`) |
| the start choice (X6) | `$.state`, for the process | nothing |

The replace is the linearization point of every change of the sheet. The
mod acts on a change (opens a route, draws, tells the bridge's caller a
verdict) only from a view a step answered, so only after the replace, and
it adopts views in the record's order: every answer carries the record's
`seq`, and a view older than the one the mod holds for that session is
not adopted, though the answer's own effects (a call's result, the
verdicts asked for) are still used. Nothing the mod holds is durable: the
view, the flights, the notices and the turn's state are rebuilt from the
record and the engine at a start.

### A process that dies between two steps

| who dies | where | what is left | what restores it |
|---|---|---|---|
| the door | before its write | nothing | the surface sends again, with the same keys |
| the door | inside its write | bytes after the inbox's last newline, and before them (a batch that spans pages) perhaps some whole lines of the batch | no reader and no drain takes the unfinished bytes; the whole lines are applied. The next appender first ends the fragment with a newline, which makes it a line: not valid, it is skipped; a whole object that lacked only its newline is applied like any line. The surface's resend, under the same keys, completes the batch and reads the first verdict of what was applied (U6) |
| the door | after its write | a line the surface has no answer for | the resend carries a key the record knows: the first verdict again |
| a step | before its replace | a `.tmp-` file; for a call, its staged call still there | the next step removes the file; the mod orders `settle`, then decides |
| a step | after its replace, its answer lost | a record ahead of the mod's view; for a call, its result in `calls` | a drain, a `landed`, a `reroute` and a `start` are ordered again and set what they set before; a call is settled: the mod reads its recorded result and answers the model with it |
| a step | it runs late, after the mod gave up on it | for a call: an id that `settle` foreclosed, or one the mod acked | the late step finds the id in `calls`, or its staged call gone, and commits nothing |
| the engine | after a call's step, before the model read its result | a question whose id the model never read | I10's context at the next start names it |
| the engine | an outcome ready | the outcome in `pending` | the next start: owed across a stop |
| the engine | a flight to the main conversation in the air, or landed and the `landed` step not yet made | the outcome in `pending`; its row in the transcript or not | the next start searches the transcript for the envelope's keys (I9): found, `landed`; not found, owed across a stop |
| the engine | a send to a subagent delivered, the `landed` step not yet made | the outcome in `pending`, the subagent gone with the process | none: the next start gives it to the main conversation. Across a process death an answer to a subagent's question may reach the main conversation as well |
| the module (a reload) | anywhere | flights and notices forgotten; `pending` whole | the new module drains and has what is pending ready again. Landing is taken from evidence, never from the flight's bookkeeping, so a flight of the old module that lands is still taken as landed. A reload that falls between handing an envelope over and its landing can deliver it twice: today's limit, kept (`sminos/hooks/mods/README.md`, "ask", Known limits) |
| the projection | after the log's append, before its replace | an event in the log and still in `log` | the next projection appends it again, which `append_host`'s `(kind, src)` rule makes nothing |
| a nudge | lost on the way | a queued line | the timer's check (K4) |

### Cases the composite leaves undefined

Each is decided here once, in the composite's spirit. Those its writer
has since taken into the composite are marked; the rest are listed again
in the last section.

- U1 (taken; its shape is new) · A retract whose target the record has
  never seen cancels it in advance: a remote copy can deliver a retract
  before its target, and the human's last word was to take the answer
  back. The target's key gets a verdict of its own, `{ "verdict":
  "retracted", "kind": "unseen", "by": "<the retract's key>", "at": … }`,
  with no `id`: nothing is known of a line that never came. The retract
  reads `retracted` with its `target`. Should the target's line arrive,
  it is set aside and the verdict stands as written, `kind` included. A
  second retract of the same target finds a key with a verdict and reads
  `too-late`.
- U2 (taken) · A line that is not JSON (NaN and the infinities are not),
  has no key, fails the line's schema, holds a lone UTF-16 surrogate in a
  string, picks a label the question does not have at an equal revision,
  or makes two picks on a single-select question at an equal revision, is
  skipped: no verdict, `inbox.skipped` raised by one, and the
  step's effects say so for the mod's debug log. The door refuses each of
  these it can see, so such a line did not come through the door.
- U3 (taken) · An answer or dismissal naming an id the record never
  assigned reads `closed` with `how: "unknown"`.
- U4 (taken) · A call in which nothing was done answers `Nothing done.`
  as its first line (I6).
- U5 (taken) · A withdrawal makes no pending outcome and no delivery.
- U6 (taken) · A door killed inside its one `write` can leave part of a
  batch; the surface's resend completes it, and the parts may reach the
  agent in two envelopes.
- U7 (taken) · A sheet holds at most 500 open questions.
- U8 · Two processes holding one session id (a session resumed in two
  terminals) both order steps; the lock serializes them and no update is
  lost, but each delivers what it finds pending, so an answer can reach
  both. Not supported, and not made worse than today's.
- U9 (taken) · A headless process MAWS did not launch never takes the
  sheet, also when its session has one.
- U10 (taken) · A `/clear` drops what was pending with the record.
- U11 (taken, as §5.2 now words it) · What is owed across a stop never
  starts a turn by itself and leaves with whichever route opens first:
  usually the first prompt that enters, whoever submitted it, and
  otherwise the turn a fresh answer starts.
- U12 (taken) · `sminos sheet answer`, `dismiss` and `retract` refuse a
  session acting on its own sheet; the door refuses nobody.
- U13 · A row that lands an envelope is told by what the engine says of
  it (I9), and where the engine says nothing of authorship, by its form.
  A text that quotes a whole envelope in that form, with keys still
  pending, could only be written by a process that can read the record,
  which §8.2 already trusts as the user. It is a limit, named here, and
  no provenance is built beyond what the engine offers.
- U14 · An entry whose own content breaks a rule the schema cannot state
  (two options with one label, a preview on a multi-select question,
  `multiSelect` without options, a line range out of order, a string
  holding a lone UTF-16 surrogate) is refused
  alone, with the reason, and the others apply (§2.1: past the schema
  each entry stands alone).

## Interfaces and Dependencies

Paths are from the repository's root. `S/` is
`sminos/skills/sminos/scripts/`, `H/` is `sminos/hooks/mods/`, `T/` is
`sminos/tests/`.

### I1 · Files

    $SMINOS_HOME/sheet/
      <session>/              the record (composite §3): state.json, inbox.jsonl, refs/, uploads/, texts/
      <session>.lock          the record's lock: an empty file, flock'd exclusively; never removed
      .staging/<session>/     what the mod hands a step: <callId>/call.json, entry-<n>.json, ref-<n>-<m>; start-<nonce>/ask-<n>.json
      surfaces/<name>.json    a surface's registration (X4)

`texts/<sha256>.txt` holds a human's answer text longer than 2,000
characters, named by the hash of its UTF-8 bytes, written by the step that
accepts the answer and kept for the record's life (I7).

The lock sits beside the record and not in it, so removing a record never
removes a lock another process waits on; a waiter that gets the lock looks
for the record again. It is `fcntl.flock`, waited for at most 10 s, after
which the door exits 75 and a step answers `busy`. Nothing ever unlinks a
lock file: a process may hold the old inode open while another makes a
new file at the same path, and both would then be inside. An empty file a
session is what that costs. C0's P4 held this lock between two appenders
and a step over 1,801 locked sections with none overlapping.

The staging is the one place the mod writes, with `$.fs.write`, one file
for each large part of an event so that none nears the 4 MiB one write
takes: an entry of a call, a captured body, an ask to import. A step
reads its staged input under the lock. A call's staging directory stays
until the mod acknowledges that call (E18); a `start` empties the
session's staging; a step also deletes any staged file older than a day.
No reader looks in it.

In the plugin:

| path | holds | from |
|---|---|---|
| `S/sminos_sheet.py` | the door, the reader, the step's shell (lock, staging, replace), the projection, removal, the surfaces' liveness, the command's `sheet` verbs | M1, M2, M6 |
| `S/sminos_sheet_step.py` | the step as a pure function, `apply(state, tail, event, now, …)`, and its composers: the view, the envelopes, I10's context (M2) | M2 |
| `H/sheet-model.tsx` | what takes no `$`: the input's schema and validation, the block's parser, the result's parser, the notices, the lines of the row and of the band | M3 to M5 |
| `H/sheet.tsx` | the hooks and everything that takes `$` | M3 to M6 |
| `sminos/types/sheet/` | the published set | M1 |
| `sminos/types/sminos.d.ts` | `SheetKept` (I8) and the snapshot's `sheet` field (I13) | M3, M6 |

**The published set** (X1, X2, X3, X4, X7):

    sminos/types/sheet/
      README.md                      what each file is, and how the set is pinned
      MANIFEST.json                  { "v": 1, "version": 1, "files": { "<path>": "<sha256>" }, "digest": "<sha256>" }
      schema/state.schema.json       I2
      schema/inbox-line.schema.json  I3
      schema/show.schema.json        I4: what `sminos sheet show --json` prints
      schema/delivery.schema.json    I7: the <sheet-delivery> block, one for both forms
      schema/surface.schema.json     composite §7's file
      schema/tool-input.schema.json  composite §2.1 with §1's limits, without descriptions
      examples/<name>/…              I7's envelopes, each with the record it was composed from
      examples/surface.json
      grammar/result.md              I6's grammar and the pattern a reader matches
      grammar/result.examples.json   stored calls: { "input", "result", "parsed" }
      fixtures/<case>/case.json      { "name", "covers", "session", "now", "event", "verdicts" }
      fixtures/<case>/before/sheet/<session>/…   a $SMINOS_HOME before one step
      fixtures/<case>/after/sheet/<session>/…    the same after it
      fixtures/<case>/show.before.json, show.after.json

`digest` is the SHA-256 of the lines `<sha256>  <path>\n` of every file of
the set but `MANIFEST.json`, sorted by path. The schemas are JSON Schema
2020-12, held to the keywords `type`, `properties`, `required`,
`additionalProperties`, `enum`, `const`, `items`, `minItems`, `maxItems`,
`minLength`, `maxLength`, `minimum`, `pattern`, `oneOf` and `$ref` into
`$defs` of the same file, so the suite checks them with a small validator
of its own (`T/sheet_schema.py`; the runners have no schema library) and
MAWS with whichever it has.

A fixture's `now` is the step's clock, which stamps every `at` and
`acceptedAt` the step writes. A JSON document of the set is serialized as
Python's `json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False)`
and a newline, and a step's output is compared after the same
serialization; an inbox line is compact JSON, its keys in its writer's
order. A side of a fixture with no record has no directory, and its
`show.*.json` is `null`. A schema's `pattern` is ECMA-262 with no flags:
each is anchored `^...$` and `$` is the end of input, so a string with a
newline after it does not match; a Python reader matches the whole string
(`re.fullmatch`). A Python JSON Schema validator that reads `$` as
Python does lets such a string through; that is a known limit
(`docs/doperpowers/TECH-DEBT.md` #38): the README states the dialect, the
second implementer is TypeScript, and the door checks strictly. A verdict, an outcome and a closed question are
discriminated shapes: each variant a closed object with its own fields
required. The set's `README.md` lists these readings with the ones below,
in the same words.

**Published at one revision** means: M1's pull request merged to `main`.
The revision is that merge commit; M1's Progress line records it with the
sminos version and the digest. MAWS pins by copying the directory whole
into its tree beside a provenance note naming the three (the way it holds
`test/fixtures/lane-a/dx4-jobs.json` and its `PROVENANCE.md`: its gate's
runners have no plugin cache to read), and a test of its own recomputes
the digest over the copy. `T/test_sheet_contract.py` recomputes the
manifest from the files, so a changed file that left the manifest behind
fails here first.

### I2 · `state.json`

    {
      "v": 1,
      "session": "<engine session id>",
      "seq": 41,                         // + 1 at every replace
      "nextId": 12,                      // the n of the next q<n>
      "inbox": { "offset": 5321, "skipped": 0 },   // bytes applied; always just past a newline
      "questions": [ Question ],         // the open ones, by id ascending: the order asked
      "pending":   [ Outcome ],          // accepted, not delivered, in the order accepted
      "closed":    { "q3": Closed },     // every closed question, for the record's life
      "verdicts":  { "<key>": Verdict }, // every key's first verdict, for the record's life
      "calls":     [ { "callId": "…", "result": "…" } | { "callId": "…", "foreclosed": true } ],
      "log":       { "next": 18,
                     "owed": [ { "n": 17, "kind": "question" | "answered", "src": "sheet:<session>:q7",
                                 "text": …, "choices": ["…"], "closed": "dismissed" } ],
                     "projects": { "q7": "<the id of the project its question went to>" } },
      "import":    { "never": true, "calls": { "<today's call id>": ["q1", "q2"] } }
    }

    Question = §1's fields, and:
      "asker": "main" | { "agentId": "…", "name": "…" }
      "references": [ Reference ]
      "importedFrom": { "callId": "…", "index": 0 }          // only for an imported ask's question

    Reference = { "path": "<as the agent gave it>", "lines": [40, 80], "abs": "<resolved at capture>",
                  "sha256": "…", "bytes": 1234, "kind": "text" | "image", "mediaType": "image/png",
                  "startLine": 40, "numLines": 41, "totalLines": 212,
                  "size": 5678, "mtimeMs": 1763900000000 }
                // sha256 and bytes are of refs/<sha256>; startLine, numLines, totalLines are Read's own, for a text;
                // size and mtimeMs the file's at capture

    Outcome = { "key": "…", "kind": "answer" | "dismiss", "id": "q7", "revision": 2,
                "picks": ["OAuth"], "text": "…", "textFile": "texts/<sha256>.txt", "images": ["uploads/a.png"],
                "by": "page", "at": "<the line's>", "acceptedAt": "…", "batch": "…",
                "recipient": "main" | { "agentId": "…" }, "taken": false, "acrossStop": false,
                "question": { "asker": …, "header": "…", "question": "…", "options": ["OAuth", "Passkeys"],
                              "multiSelect": true, "askedAt": "…" } }
              // picks are labels, as the line gave them; textFile only for a text past 2,000 characters (I7)

    Closed  = { "how": "answered" | "dismissed" | "withdrawn", "at": "…", "revision": 2,
                "asker": …, "header": "…", "question": "<its first 200 characters>",
                "receipt": "OAuth, Passkeys", "places": [1, 2], "key": "…", "deliveredAt": "…", "answer": "…" }
              // receipt: the picks joined by ", ", else the text's first 80 characters; none for withdrawn;
              // places: an answered question's picks as integers from 1 among the answered revision's options;
              // answer: I7's line after the id, at most 2,000 characters, kept on the 32 questions answered last (I13)

    Verdict = { "verdict": "applied" | "stale" | "closed" | "retracted" | "too-late",
                "kind": "answer" | "dismiss" | "retract" | "delivered" | "unseen", "at": "…", "id": "q7",
                "current": 3, "how": "answered" | "dismissed" | "withdrawn" | "unknown", "target": "…", "by": "…" }
              // current with stale; how with closed; target with a retract's;
              // kind unseen, with by and without id, for a key a retract cancelled before any line carried it (U1)

- **The schema states structure, not the input's bounds.** §1's lengths,
  its twelve options and its rule that a preview needs a single-select
  question are rules of the tool's input, checked at the call
  (`tool-input.schema.json`, I6). `state.schema.json` types the fields
  and bounds none of them, so a question imported from today's tool is
  kept exactly as it was asked, marked by `importedFrom`: a
  2,001-character question, a 201-character label, a preview on a
  multi-select question are all valid in a record. A surface draws what
  the record holds. A later revise of such a question is a call like any
  other, under the input's rules. Today's tool already refuses two
  options with one label, so a pick still names one option. What leaves
  the record for the model is bounded where it is composed (I7), not
  here.
- **`calls`** holds the outcome of each call the mod has not yet
  acknowledged: its result text, or that `settle` foreclosed it. An entry
  leaves when the mod acknowledges that id, and all leave at a `start`.
  That horizon is enough because a call id is ordered only by the one
  hook dispatch that holds that call; it orders `call` and `settle` and
  nothing else for the id until it has an answer, and acknowledges only
  then; and a step of that id still on its way after the acknowledgement
  finds its staged call gone and commits nothing. A `start` is a new
  process, or a new session of the same one: no dispatch of the old
  conversation remains to order an old id.
- **`log`** is what the project's log has not yet taken, and where each
  question's events go (I12). A reader ignores it.
- A question's order on a surface is its id's: a revise keeps the place.
  `askedAt` and `callId` are the current revision's, as §1 says.
- **Always present.** `import` is `{never, calls}` and `log` is `{next,
  owed, projects}` in every record. An answer's outcome always carries
  `picks`, `text` and `images` (`[]`, `""`, `[]` when the line had none); a
  dismissal's carries none of the three, and its `revision` is the
  question's at the dismissal. A record a `start` makes has an empty
  `inbox.jsonl` beside `state.json`.
- **`Verdict.at`** is when the step gave the verdict, for every verdict;
  when a question closed is `closed[id].at`.
- **Cuts of data** are the first N characters with no mark:
  `Closed.question` (200), the receipt's text (80), `Closed.answer`
  (2,000). Only the envelope's prose marks a cut with `…` (I7).
- **What an answer leaves.** `Closed.answer` and the `answered` event the
  log is owed (I12) hold I7's line after the id in its full-text form, with
  no asker and no times, which belong to a delivery: the log's whole,
  `Closed.answer` its first 2,000 characters. `receipt` is written for an
  answered question only; a closed question keeps the `key` of the line
  that closed it.
- A `delivered` line sets `closed[id].deliveredAt` for each key it takes
  out of `pending`, as `landed` does. Only an answered or a dismissed
  question has a `deliveredAt`: a withdrawal is delivered to nobody (U5).
- An agent id (an asker's, a recipient's) is at most 128 characters, a
  bound of this contract (the engine's ids are far shorter), and is never
  cut; nor is a question's id, which is at most `q999999999` (`q` and 1
  to 9 digits) in every schema and at the door.

### I3 · The inbox line, the door, the command

The line is §4.1's. The schema adds only bounds: `key` 8 to 128 of
`[A-Za-z0-9._:-]`; `text` at most 20,000 characters; `picks` at most 12;
`images` at most 8, each `uploads/<name>` with a stem (the name before its
final dot) of 1 to 250 of `[A-Za-z0-9._-]` and then the extension `png`, `jpg`, `jpeg`, `gif` or `webp`; a `delivered` line's
`keys` at most 200; a call of the door at most 50 lines. Required: `v`,
`key`, `kind`, `by`; with `answer`, `id`, `revision` and one of `picks`
and `text` non-empty; with `dismiss`, `id`; with `retract`, `target`; with
`delivered`, `keys`. A pick is a label and has the label's length, which
for an imported question no bound limits. The door fills `at` when absent
and sets one `batch` on the lines of a call of more than one line.

    sminos sheet put (<member> | --session <id>) [--no-wait]     lines on stdin, one JSON object each

The door, under the lock: the record must exist (else exit 3, `no sheet`);
every line must pass the schema, name images that exist under `uploads/`
as regular files, and, where it answers an open question at its current
revision, pick only that question's labels, one unless it is multi-select
(else exit 2, the reason on stderr, nothing appended: a call is appended
whole or not at all). It also refuses, exit 2, what no other reader could
read: NaN or an infinity, and a lone UTF-16 surrogate in any string; such
a line that did not come through the door is skipped (U2); a file that does not end in a newline gets one
first, which turns what an unfinished write left into a line of its own
(the drain's rule decides it); then one `write` of all the lines, synced. Should the write come back
short, the rest is written while the lock is still held, so no drain sees
part of the call (a reader holds no lock, and can list the call's first
lines in the instant between a short write and the rest or a rollback:
a known limit, `docs/doperpowers/TECH-DEBT.md` #37, since a short write
of a small local append is itself rare and what it shows is a queued
line gone at the next read); should the file refuse more, it is cut back to its
length before the call and the door exits 1, nothing appended. After the lock: unless
`--no-wait`, it tells the session's bridge (`POST /command` on
`$SMINOS_HOME/bridge/<session>.sock`, `{"op": "sheet", "keys": [...]}`,
waiting 10 s) and prints what came back. Output, one JSON object:

    { "session": "…", "results": [ { "key": "…", "state": "queued" }
                                 | { "key": "…", "state": "applied" | "stale" | "closed" | "retracted" | "too-late", …the Verdict's fields } ] }

`queued` whenever no verdict came: no bridge, a bridge that does not know
the op, a session not under the sheet, no answer in time. Exit 0 once
appended, whatever the verdicts.

The bridge's `sheet` op: the mod orders a drain naming the keys and
answers `{ ok: true, result: { verdicts: { "<key>": Verdict } } }` from
the step's effects, `{ ok: false, code: "no-sheet" }` in a session whose
choice is not the sheet or whose `start` has not answered. It is no
control: an observer (a MAWS-run session's bridge) answers it, so it
joins `OPS` and stays out of `CONTROL_OPS` in `H/bridge.tsx`.

The other verbs (M2), each taking `<member>`, resolved as the control
verbs resolve one, or `--session <id>`, which reads no registry:

    sminos sheet show    <who> [--json [--keys <k,…>]]      the reader's model (I4), or its text
    sminos sheet answer  <who> <q>[@<revision>] [--pick <label|n>]... [--text <t>] [--image <file>]...
    sminos sheet dismiss <who> <q>...                       one call of the door: one batch
    sminos sheet retract <who> <key>
    sminos sheet remove  <who>                              a stopped session's record (refused while it runs)
    sminos sheet surfaces [--json]                          the registrations, with which are alive
    sminos sheet step    --session <id>                     the tool's own (I5); in no usage text
    sminos sheet probe   --session <id> [--remote]          the tool's own (I8); in no usage text
    sminos sheet log     --session <id>                     the projection (I12); in no usage text

**A question is named with the revision the human saw.** `show` prints
each question's handle, `q7` at revision 1 and `q7@2` after a revise.
`answer` takes a bare `q7` only while the question is at revision 1; at a
higher revision it refuses and says `q7 is at revision 3: show it again,
then answer q7@3`. A handle naming a revision that is no longer current
is refused the same way. Numbered picks are places among the options of
the named revision, which is then the current one, and the line carries
that revision, so a revise between the command's read and the drain still
reads `stale`. `dismiss` takes a bare id at any revision: §4.2 dismisses a
question whatever its revision.

`answer` builds one line (`by: "cli"`, a key of its own), copies each
`--image` into `uploads/` first, and calls the door; `dismiss` and
`retract` likewise. U12 binds these three.

X2's open point, C2's side of it: MAWS reaches the writer by running the
command. Nothing is served over the daemon's socket by this child.

**As built (M2).** The command's keys are `cli-` and 16 hex digits; an
`answer`'s image is copied to `uploads/cli-<16 hex>.<ext>` after the
refusals are checked. `answer` and `dismiss` refuse a question `show` does
not list (a queued dismissal still counts as listed for `dismiss`), so the
human hears it at once rather than as a `closed` verdict later. A `--pick`
number is ASCII decimal only, so a label such as `²` still matches as a
label. `remove` takes the lock, checks again under it that the session
does not run (unless `--cleared`), renames the staging and then the
record aside to `sheet/.removed-<epoch>-<uuid>` (renaming back what it
detached when a rename fails), deletes them after the lock, exits non-zero
naming what it could not delete, and deletes leftovers older than 60 s at
the next `remove`. `show --json` projects a queued `sent` entry by its
kind as the show schema's variants say, whatever extra field the line
carries (the composite's writer's ruling of 2026-11-24 on a defect of
M1's reader); the door still accepts the field.

### I4 · What a reader computes

One rule for `sminos sheet show`, MAWS's reader and the page; `show
--json` prints it and the fixtures' `show.*.json` pin it.

1. Read `state.json`, then the inbox from `inbox.offset` to its last
   newline, then `state.json` again; if `seq` moved, start over (three
   times at most; then the reader returns no pair it did not verify:
   `show` exits 75, and a reader reads again). Bytes after the last newline
   are a write that did not finish: a reader takes none of them, on every
   filesystem and whatever a probe observed, and so does a drain, so the
   two never disagree on where the inbox ends. C0's P4 saw no partial
   write on APFS, which is an observation and not a promise, and nothing
   published depends on it.
2. From the tail drop what is not valid, and every line whose key has a
   verdict or occurred earlier in the tail. Each line that remains is
   **queued**. A queued answer or dismissal that a queued retract names
   is also **cancelled**.
3. A question with a queued dismissal that is not cancelled is not
   listed (§3). A question with a queued answer that is not cancelled is
   listed carrying the first such line.
4. Every key the reader knows has one entry in `sent`, with one state:
   `queued` (step 2, with `cancelled: true` where it holds); `accepted`
   (its outcome is in `pending`); `delivered` (verdict `applied`, not in
   `pending`); else its verdict. A queued retract whose target is no
   line the reader has seen is `queued` like any other, and says nothing
   of its target; once a step has applied it, the target has an entry of
   its own, `kind: "unseen"`, state `retracted`, no `id`, and keeps it
   when its line arrives (U1).
5. A reference reads `changed: true` when the file at `abs` is missing or
   its size or modification time differs from the record's; `null` where
   the reader is not on the session's machine.
6. `closed` is the record's, by id: how each closed question closed, at
   which revision, and its receipt. It is what a call's row draws once
   the question has left the sheet (`q7 Auth method → OAuth`,
   `Withdrawn`): a withdrawal never passed through the inbox, and a
   delivered answer is in `pending` no longer.
7. A pending outcome carries its question as the record's snapshot has
   it, the question cut at 2,000 characters, its header at 60, each label
   at 200 and a subagent's name at 200, and an answer's picks cut at 200
   with `places` beside them, the picks as integers from 1 read from the
   whole snapshot before any label is cut (two imported labels can share
   their first 200 characters); a closed answered question carries the
   record's `places` (cuts only an imported question can need): what a deliverer needs to tell a
   conversation that does not hold the question what was asked and which
   option a place names (§5.4).

    show --json = { "v": 1, "session": "…", "seq": 41,
                    "open":   [ Question + { "handle": "q7@2",
                                             "queued": { "key", "kind": "answer", "picks", "text", "images", "revision", "by", "at" } } ],
                    "hidden": [ { "id": "q9", "key": "…" } ],            // open, with a queued dismissal
                    "sent":   [ { "key", "kind", "id", "state", "cancelled", …the Verdict's fields } ],
                    "pending": [ Outcome, its question bounded as in 7 ],
                    "closed":  { "q3": { "how", "at", "revision", "asker", "header", "receipt", "places", "deliveredAt" } } }

- `sent` lists the keys with a verdict, sorted by key (a JS reader would
  put an integer-like key of an object first), then the queued lines in
  inbox order. A queued retract carries its `target`; a `delivered` line's
  own key reads `delivered`.
- A line a reader drops in step 2 is one a drain skips: every case U2
  lists, and nothing else.
- A reader never fails on a record's strings: a lone UTF-16 surrogate in
  anything `show` prints is written as U+FFFD. A writer keeps them out:
  `put` refuses them in a line (I3), the step refuses an entry whose
  strings hold one (an entry's own refusal, U14), and an import replaces
  each with U+FFFD (M2).
- The show schema states step 7's cuts and the keyed form's; the state
  schema bounds none of the record's strings. A queued `sent` entry is
  discriminated by kind: an answer or dismissal carries its `id`, a
  retract its `target`, a `delivered` line neither. A handle's pattern
  bounds the question's id, not its revision.
- A session with no record: `show` exits 3, `no sheet`.

`show --json --keys <k1,k2,…>` (at most 50) prints the same with `pending`
and `sent` held to those keys and `open`, `hidden` and `closed` left out,
and each pending outcome's `text` held to its first 500 characters, with
`textCut: true` when it was longer and the record's `textFile` where it
has one (the block's rule, I7), every other string under the cuts of
step 7: about 20 KB an outcome whatever an imported question holds, so
fifty keys stay far under the 4 MiB a hook takes through
`$.process.run`. The unkeyed form, read by processes and
not hooks, carries texts whole.

### I5 · The step

    sminos sheet step --session <id>            one JSON object on stdin, one on stdout

    in  = { "event": "start" | "drain" | "call" | "settle" | "landed" | "reroute",
            "runner": "terminal" | "maws",
            "remote": false,                     // the session is under SSH_CONNECTION: only a surface of reach `remote` suits it
            "agents": { "running": ["<agentId>"], "direct": true },
            "acked": ["<callId>"],               // calls the mod now holds an answer for (E18)
            "keys": ["…"],                       // drain: the verdicts wanted; landed, reroute: the outcomes
            "context": "compact",                // a drain after a compaction: compose I10's context too
            "start": { "source": "startup" | "resume" | "fork" | "clear", "floor": 11,
                       "today": { "definite": true, "asks": [ { "file": "<a staged ask>" } ] } },
            "call":  { "callId": "toolu_…", "floor": 11 } }          // call and settle alike name the call by callId

    a staged ask (start.today.asks[].file), or one given inline =
          { "callId": "toolu_…", "askedAt": "…", "questions": [ today's tool's question objects, as it held them ] }

    <staging>/<callId>/call.json =
          { "asker": "main" | { "agentId": "…", "name": "…" },
            "entries": [ { "file": "entry-1.json", "captures": [ Capture ] } | { "refused": "<I6's clause>" } ],
            "withdraw": ["q3"] }

    Capture = { "ok": true, "abs": "…", "kind": "text", "file": "<a staged file: Read's result.file.content>",
                "startLine": 40, "numLines": 41, "totalLines": 212, "size": 5678, "mtimeMs": 1763900000000 }
            | { "ok": true, "abs": "…", "kind": "image", "file": "<a staged file: the bytes in base64>", "mediaType": "image/png", "size": …, "mtimeMs": … }

    out = { "ok": true, "seq": 42, "view": View, "effects": Effects }
        | { "ok": false, "code": "busy" | "bad-event" | "no-record" | "gone", "error": "…" }

    View    = { "seq", "offset", "nextId",
                "open":    [ { "id", "revision", "asker", "header", "question", "askedAt" } ],   // header cut at 60, question at 300
                "pending": [ { "key", "id", "kind", "recipient", "taken", "acrossStop" } ],      // the first 200, in order
                "pendingCount": 3, "owedAcrossStop": 2,
                "closed":  { "q3": { "how", "revision", "header", "receipt" } },                 // the 500 closed last
                "answered": [ { "id", "header", "question", "answer" } ], "answeredCount": 14,   // I13: the 32 answered last, question cut at 300;
                                                                                                 // the count is of every question ever answered
                "ready":   [ { "recipient": "main" | { "agentId": "…" }, "keys": ["…"], "text": "<an envelope, I7>",
                               "wakes": true, "more": false } ],                                 // at most 4 recipients
                "surface": { "name", "url", "reach" }, "surfaces": 2 }                           // the first alive that suits, or null; how many are alive
    Effects = { "applied": ["<key>"],            // outcomes that joined `pending` in this step
                "skipped": 0,                    // lines this drain skipped (U2)
                "verdicts": { "<key>": Verdict },                       // for `keys`
                "result": "<the call's result text, I6>", "foreclosed": true,     // call, settle
                "context": "<I10's text>",       // start, and a drain that asked for it
                "owed": 2,                       // events the log is owed after this step
                "start": { "empty": "fork" | "lost" | null, "before": ["<key>"],  // before: pending ahead of this step's drain
                           "imported": [ { "callId": "…", "ids": ["q1"] } ] } }

In order: take the lock; read the event's staged files; load the record
(none: `start` makes an empty one, anything else answers `no-record`);
drain; apply the acknowledgements, then the event; write each new
`refs/<sha256>` from its staged file (the bytes: a text's UTF-8, an
image's decoded) and each new `texts/` file; compose the ready envelopes
and, where asked, the context; replace `state.json` (a `.tmp-` file in
the record, synced, then `os.replace`) when anything changed; release the
lock; answer. C0's P4 read such a replace 26,743 times from a process
without the lock and never saw a torn or missing file, where a hook's own
`$.fs.write` in place tore 3 reads in 225,781.

**A call is staged before it is ordered, always.** The mod writes
`<callId>/call.json` for every call, also one that only withdraws or
whose entries it all refused, and beside it a file for each entry that
passed and each captured body. The event on stdin names the call by its
id and nothing more. So the staging directory is there for every fresh
call, and its absence means one thing: the mod acknowledged that id, or a
`start` cleared it.

**Everything that crosses is bounded.** Into the step: the event on stdin
is a few hundred bytes; `call.json` names its entries and holds none; an
entry at every bound of the input's schema is under 1 MiB as JSON (some
123,000 characters, at four bytes each or six as an escape), and a
captured text is at most the 256 KB Read itself returns. Out of the step:
nothing in the answer grows with what one step applied or with the
record's history. The view leaves out options, descriptions, previews,
context, reference bodies and answer texts; it cuts what it keeps and
counts what it leaves out; what a consumer needs of many things is a
count and the last few (`answered` and its count, `pendingCount`,
`surfaces`); and the step measures its answer before it writes it: past
3 MiB it leaves out ready envelopes from the last recipient back, then
`closed` entries from the oldest, until it is under, so the 4 MiB
`$.process.run` returns is never reached. Everything in the view is read
from the record, so an answer that was lost is had again from the next
step: nothing the mod needs exists only in one step's effects but a
call's result, which `calls` keeps. An event given inline (a shell, the
suite, a fixture's `case.json`) may hold a call's body, its entries and
a start's asks in place of files; the mod never does.

**A step never fails a session.** The mod reads `ok: false`, a process
that did not start, or output that is not JSON as "no answer". For a
drain, a `landed`, a `reroute` and a `start` it orders the event again at
the next trigger. For a call it orders `settle` for that id, at most
three times in the same dispatch: a recorded result is the call's answer
(the first step committed and its answer was lost); `foreclosed` lets the
mod answer that nothing was done; and if `settle` too gives no answer,
the mod answers that the outcome is not known yet (I6's two fixed
lines), goes on settling at every trigger, and sends the outcome as a
notice (I9). Only once it holds one of these does it acknowledge the id.

    sminos sheet probe --session <id> [--remote]     read-only, no lock; one JSON object
    { "record": true, "open": 3, "pending": 1, "queued": 0, "surface": { "name", "url", "reach" } | null, "surfaces": 2 }

**As built (M2), what the mod (M3, M4) relies on.**

- **A start's identity.** The `start` event carries `start.nonce`: one per
  actual start, unchanged on every retry of it (the same name as its
  `start-<nonce>/` staging; not starting with `.` or `start-`, no `/`).
  Before its replace a start writes `.staging/<session>/.start-receipt.json`,
  `{nonce, empty, imported}`; a start whose nonce equals the receipt's is
  a retry and answers the same `empty` and `imported`, so the fork, lost
  and import lines of its context read the same. Everything else, `before`
  and the context's list included, is recomputed every time. A start with
  no nonce (a shell's) is always new. A start keeps its own staged asks
  until the next start or the day's sweep; a staged ask an event names
  that is missing is `bad-event`.
- **`effects.start.before`** holds at most the first 200 keys, with
  `beforeCount` beside it; it is the trigger of I9's search, not its
  list (I9). It is what is pending ahead of the step's drain, so a
  retry's also names what the first attempt's drain applied.
- **The acknowledgement window.** What a replace makes the record forget
  (an acknowledged call's staging; at a start every call's and an earlier
  start's) is renamed to `.gone-<uuid>` before the replace and deleted
  after it, or by the next step's sweep. A late step of such a call
  answers `gone` on either side of a death. A call id may not begin with
  `.` or `start-`. `gone`, like `busy`, `no-record` and `bad-event`,
  changes nothing, the drain included.
- **Inline events.** Only a staged call can be told `gone`; an inline
  call (a shell, a test) ordered again after its acknowledgement applies
  again. The mod never orders inline. A `call` or `settle` whose id is in
  the same event's `acked` is `bad-event`; so is an event's `keys` over
  200, and an inline call of more than 20 entries.
- **Refusals.** A mod-refused entry's `call.json` holds `{"refused":
  "<clause>"}` without its `entry <n>, ` prefix; the step adds it. The
  step checks U14 itself too, with the same clauses, so an entry the mod
  missed is refused alone; a lone surrogate reads `a string holds a lone
  UTF-16 surrogate` (the door's words; `grammar/result.md`'s clause list
  does not carry it, the first-line grammar is unaffected). Each clause's
  free text is cut at its source: a path at 200, the engine's reason at
  500, a mod-written clause at 500, a subagent's name at 200; the
  withdrawals' clauses stop at 32,000 characters of the `Not done:` line
  and end `And N more withdrawals not done.` `never asked` has no time:
  `q9 is not open (never asked)`.
- **The floor** raises `nextId` to `max(nextId, floor + 1)` whenever the
  record has assigned no id (none open, none closed), at a `call` or a
  `start`. `effects.start.empty` is `fork` when a fork's start made the
  record, `lost` when a resume's start made it with a floor of at least
  1, else `null`.
- **The answer.** `step` exits 0 for every answer, `ok: false` included;
  the mod reads the JSON. Everything the answer needs is composed before
  the replace, so a composer's failure never follows a committed state.
  The whole serialized answer is held under 3 MiB, cutting in order
  `ready` (from the last recipient back), `closed` (oldest first), `open`
  (newest first), `answered`; a call's result has a fixed maximum.
- **Times.** A line's `at` that matches the pattern but is no calendar
  date (the door takes it: its behaviour is frozen) is tolerated by every
  composer: a time that does not parse is written as stored and its age
  left out. An outcome's `at` is the line's, or the step's clock for a
  line with none.
- **Order.** "Closed last" and "answered last" are by closing order, ties
  of one drain kept in the order the drain closed them. The view also
  cuts an asker's name at 200, a closed entry's header at 60 and its
  receipt at 200. `owedAcrossStop` counts dismissals too. A revise of an
  imported question drops `importedFrom`. `effects.verdicts` answers the
  event's `keys` whatever the event.

### I6 · A call: its input, its refusals, its result (X7)

The input is §2.1's, validated by the mod (the engine does not check a
plugin tool's input). Two kinds of rule:

- **The whole call**: `schema/tool-input.schema.json`, and the two rules
  of the call no schema of those keywords states: at least one of `ask`
  and `withdraw` non-empty, and an id at most once across both. A call
  that breaks any is denied whole, in the words `ask.tsx`'s `formatted`
  uses for today's tool (`InputValidationError: AskUserQuestion failed
  due to the following issue…`, one line an issue), and reaches no step.
  A denial is the engine's error result and has no first line of the
  grammar below.
- **One entry** (U14): labels unique within the entry; `preview` only
  without `multiSelect`; `multiSelect` only with options; `lines` as `[a,
  b]` with `1 <= a <= b`; every reference captured. An entry that breaks
  one is refused alone: the mod writes its clause in the entry's place in
  `call.json`, and the others apply. The published schema states none of
  these, nor the call's two rules above: a preview on a multi-select
  question passes it.

The result's first line is one of three, and a stored call that was not
denied always has one:

    first-line = sentences / "Nothing done." / "Outcome not known yet."
    sentences  = sentence *( " " sentence )
    sentence   = added / revised / withdrew              ; in this order, each at most once
    added      = "Added " item *( ", " item ) "."
    revised    = "Revised " ritem *( ", " ritem ) "."
    withdrew   = "Withdrew " id *( ", " id ) "."
    item       = id [ " (entry " n ")" ]
    ritem      = id " (" [ "entry " n ", " ] "revision " n ")"
    id         = "q" 1*DIGIT        n = 1*DIGIT

- **The sentences**, for a call that changed the sheet. Ids stand in the
  order of the call's entries; `n` is an entry's place in `ask`, from 1,
  and every `item` and `ritem` carries it exactly when some entry or
  withdrawal of the call was refused.
- **`Nothing done.`**, for a call every part of which was refused, and
  for a call that was foreclosed (I5): the sheet is as it was.
- **`Outcome not known yet.`**, for a call whose step and whose settling
  gave no answer. Its second line reads `The sheet did not answer. Do not
  repeat this call: what it did will be told to you.`, and the outcome
  reaches the model later as context (I9's notice). A reader of a stored
  call with this first line draws no ids for it and does not look for the
  notice: whatever the call added is on the sheet and in later calls and
  envelopes under its own ids.

A second line, present when anything was refused, reads `Not done: ` and
one clause per refusal, each closed by a period:

    entry <n>, the reference <path> could not be read: <reason>
    entry <n>, two options share the label "<label>"
    entry <n>, an option's preview needs a single-select question
    entry <n>, multiSelect needs options
    entry <n>, lines must be [a, b] with 1 <= a <= b
    entry <n>, <id> is not open (<how> at <HH:MM>)             how: answered, dismissed, withdrawn, never asked
    entry <n>, <id> was asked by <the main conversation | the subagent <name>>; only its asker revises it
    entry <n>, the sheet holds 500 open questions
    <id> is not open (<how> at <HH:MM>)
    <id> was asked by <…>; only its asker or the main conversation withdraws it
    the sheet could not be written (<why>); call again                 a foreclosed call's one clause

A label in a clause is cut at 200 characters. A reference's `<reason>` is
the engine's own: the check's when it did not allow the Read (a deny
rule's, a guard's, or, for a path outside the session's working
directories, that permission was not granted: C0's P3 found the check
answers `ask` there in every permission mode and opens no dialog, so such
a reference is always refused and the agent puts the excerpt in
`context`), and Read's when it failed (a missing file; a file over 256 KB
named without a range, whose reason tells the agent to name one).

A last line, when the step's view names no surface alive whose reach suits
the session (I8): `No surface can show these questions right now; they
wait on the sheet and show when one returns.`

The step writes every result but the two the mod must write because no
step answered: a foreclosed call's and `Outcome not known yet.`
`H/sheet-model.tsx` and MAWS parse the first line.

### I7 · The envelope (X3)

One envelope a recipient, composed by the step (`S/sminos_sheet.py`): it
alone has every text, and one composer serves the terminal's routes, the
send to a subagent and the fixtures. The terminal form:

    [sheet v1] The human answered questions on your sheet.
    q7 "Which auth method should the login use?" → OAuth, Passkeys. Their text: "passkeys only on mobile"
    [Image source: /Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e1/uploads/sketch.png]
    q8 (asked 2026-11-23 14:02, answered 2026-11-23 16:40, while this session was stopped) "What should the empty state say?" → their text: "Nothing waiting for you."
    q12 (from the subagent reviewer, a1b2c3, which has ended) "Ship the migration today?" → Yes.
    Dismissed: q9, q11.
    <sheet-delivery>{"v":1,"keys":["page-7f3a91c2","page-7f3a91c3","cli-20c41d07","page-7f3a91c4","page-7f3a91c5"],"answered":[{"id":"q7","revision":2,"picks":[1,2],"text":"passkeys only on mobile","images":["/Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e1/uploads/sketch.png"]},{"id":"q8","revision":1,"picks":[],"text":"Nothing waiting for you.","images":[]},{"id":"q12","revision":1,"picks":[1],"text":"","images":[]}],"dismissed":["q9","q11"]}</sheet-delivery>

- The head reads `[sheet v1] The human dismissed questions on your sheet;
  no answer will come for them.` when the envelope answers nothing. An
  envelope that does not carry everything now owed to its recipient ends
  its head line with ` More follows.` and its block holds `"more": true`.
  An envelope sent to a subagent opens, above the head, with `From the
  human, through the question tool, not from your coordinator: answers to
  questions you put on the sheet.`: the engine frames a plugin's send as
  the coordinator's (C0's P2), as it does the bridge's `TELL_LINE`.
- An answer's line: the id; then, when the recipient is the main
  conversation and the asker a subagent, the asker in parentheses (`which
  has ended`, or `which could not be sent it` for one still running whose
  send was not delivered); then, when the outcome is owed across a stop,
  its times in the machine's local time; then the question as a JSON
  string, cut at 200 characters with `…`; then `→` and the picked labels
  joined by `, ` with a period, each label cut at 200 characters with
  `…`, and `Their text: ` with the text as a JSON string (`→ their text:
  ` when nothing was picked). One `[Image source: <absolute path>]` line
  follows per image, the engine's own form for a picture known by its
  file.
- The block is the last line: compact JSON, its keys in the order shown,
  with `<`, `>`, `&`, U+2028 and U+2029 written as `\u` escapes, so
  neither the closing tag nor a system-reminder tag (the one thing the
  engine escapes inside a context: C0's P5) occurs inside, and the block
  is one line. `keys` holds the answered outcomes' keys in the order of
  `answered`, then the dismissed ones' in the order of `dismissed`: as
  many keys as the two lists have entries.
- **`picks` holds places**, integers from 1 among the question's options
  as the answered revision had them, in the terminal form and in the
  steer alike: one block for both, and a pick that is bounded whatever
  its label is. A label is at most 200 characters in every question the
  sheet's input accepted, so the prose's cut can only ever shorten a
  label today's tool let through, and there the place still names the
  option.
- A reader reads the block and nothing above it.
- Inside an envelope `answered` and `dismissed` each list their questions
  by the id's number (q8 before q12): the packing below decides which
  outcomes an envelope carries, and their order is the ids'. The block
  places `textCut` and `textFile` after `text` and `more` after
  `dismissed`. "Cut at N with `…`" in the prose is the first N characters
  and `…`.

**The budget** (the composite's §5.3 rule, in exact shapes). The engine
hands the model one context entry whole only up to 100,000 of its
characters.

- An envelope is at most **60,000** UTF-16 code units, the larger of the
  ways to count a string, so it is under the engine's cut however the
  engine counts, with room for a notice above it and the engine's own
  wrapper; and it carries at most **200** keys, what one `delivered` line
  can name (I3), so whoever delivered it can always say so in one line.
- A text longer than **2,000** characters has a file, `texts/<sha256>.txt`,
  from the moment its answer is accepted.
- The block's `text` is the text's first **500** characters, with
  `"textCut": true` when the text is longer and `"textFile": "<absolute
  path>"` when it has a file. So no text is in an envelope twice in full.
- A composer, the step's or MAWS's for its steer, makes a recipient's
  next envelope from what is pending for that recipient, batch by batch
  (an outcome with no `batch` is a batch of one). Batches that hold an
  outcome that wakes (I9) come first, in the order accepted; then the
  others, in the order accepted.
  1. Batches join whole, every text in full in the prose, while the
     envelope stays within both limits; the first that would pass one
     ends the envelope.
  2. If not even the first batch fits in full, its longest text that has
     a file is carried by its head and its file instead (`→ their text,
     20,000 characters, is in <absolute path> and begins: "<its first 500
     characters>…"`), then the next longest (of equal lengths, the
     earlier), until it fits. An envelope that came to this takes no
     second batch.
  3. If it still does not fit, the envelope takes that batch's outcomes
     in order while they fit. The rest stay pending and are packed later
     like anything else pending.
  `more` is true when anything stays pending for that recipient after
  the packing. Nothing about a packing is recorded: the next envelope is
  composed afresh from what is pending then.
  One outcome always fits alone: at every bound of the line it is under
  30,000 units.
- A route carries one envelope each time it opens; what remains leaves
  with the next opening.

The steer form (§5.4) is C5's to send, under the same two limits and
with the same block. Its prose holds no text a model wrote: places for
labels, no question, and a subagent named by its id. For the record of
the first example above:

    [sheet v1] The human answered questions on your sheet.
    q7 → option 1, option 2. Their text: "passkeys only on mobile"
    q8 → their text: "Nothing waiting for you."
    q12 (asked by the subagent a1b2c3, which has ended) → option 1.
    Dismissed: q9, q11.
    <sheet-delivery>{"v":1,"keys":["page-7f3a91c2","page-7f3a91c3","cli-20c41d07","page-7f3a91c4","page-7f3a91c5"],"answered":[{"id":"q7","revision":2,"picks":[1,2],"text":"passkeys only on mobile","images":["/Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e1/uploads/sketch.png"]},{"id":"q8","revision":1,"picks":[],"text":"Nothing waiting for you.","images":[]},{"id":"q12","revision":1,"picks":[1],"text":"","images":[]}],"dismissed":["q9","q11"]}</sheet-delivery>

**The published examples** each come with what they were composed from,
so a composer in either repository is held to bytes it can reproduce:

    examples/<name>/input/sheet/<session>/…    a record (state.json, and its texts/ and uploads/ where it has them)
    examples/<name>/case.json                  { "recipient": "main" | { "agentId": "…" }, "runner": "terminal", "tz": "UTC" }
    examples/<name>/envelope.txt               the envelope for that recipient, `{HOME}` standing for $SMINOS_HOME

| name | its record | what the envelope shows |
|---|---|---|
| `terminal` | the first example's five outcomes; also `steer.txt`, the steer for the same record | the plain form; an image; an outcome owed across a stop; an ended subagent's |
| `long` | one Send of four answers of 20,000 characters each | in full they pass the budget, and with one carried by its file still do: the first two are carried by head and file, the other two stand in full; each file's name is the hash of its text |
| `more` | five Sends of fifty dismissals each | four Sends, 200 keys; `More follows.` and `"more": true`; the fifth Send stays pending |
| `imported` | an answer that picks the 201-character label of an imported question | the label cut at 200 in the prose, its place in the block |
| `subagent` | one answer for a running subagent, `taken` | the opening line |
| `split` | one Send of forty answers of exactly 2,000 characters (no file can shrink it) | packing rule 3: twenty-two with `More follows.` and `"more": true`; then, in `split/then/` from the record once those landed, the other eighteen without them |

Times are composed in the zone `case.json` names; paths under the home
the composer is run with.

### I8 · The start choice (X6), and surfaces (X4)

Made at a process's first `session.start` and kept:

    SheetKept = { shape: 1, choice: 'sheet' | 'today' | 'none', runner?: 'terminal' | 'maws',
                  session: string, started?: string, left?: string }   // $.state, { plugin: 'sminos', key: 'sheet' }

    kept choice                                  → that choice (a reload, a /clear: the process's is one)
    no kept choice, a kept `ask` snapshot        → 'today' (a module before this one served today's tool here)
    SMNS_INTERNAL set                            → 'none'
    MAWS_QUESTION_SHEET equals the session's id  → 'sheet', runner 'maws'
    MAWS_NATIVE_TO_HUMAN set                     → 'none' (as today: MAWS serves its own ask)
    not interactive                              → 'none' (U9)
    the record has an open question, a pending
      outcome or a queued line                   → 'sheet', runner 'terminal'
    SMINOS_QUESTION_SHEET on, and a surface
      alive whose reach suits                    → 'sheet', runner 'terminal'
    otherwise                                    → 'today'

- **The proof for MAWS** (§7, C2's side, which waits on C5's agreement):
  MAWS sets `MAWS_QUESTION_SHEET` to the launch's session id, which it
  knows for every launch (`--session-id` for a new session and a fork,
  the resumed id otherwise: `buildLaunch` in MAWS's
  `src/engine-host/launch.ts`). The tool takes the variable as proof only
  when it equals the id of the session this process starts. The proof is
  in hand at once, needs no bridge and no registry record, and a `claude`
  a tool starts inside the session inherits the variable under another
  id. A variable that is set and does not match is ignored, with a debug
  line saying so.
- `SMINOS_QUESTION_SHEET` is on for `1`, `true`, `on`, `yes` and off for
  `0`, `false`, `off`, `no`, in any case; unset is the default, one
  constant in `H/sheet-model.tsx` that C7 changes.
- A surface is alive when its `heartbeatAt` is at most 30 s old and its
  `pid` is a running process (`S/sminos_sheet.py`, which `surfaces` and
  `probe` print and every step's view carries). Its reach suits a session
  unless `SSH_CONNECTION` is set there and its reach is `local`.
- **Reading the registrations** (the composite's writer's ruling of
  2026-11-24, from C4's plan, the registration's real writer). The writer
  (`mawsd`) makes `sheet/` and `sheet/surfaces/` at mode 0700 when absent,
  writes its file at 0600 by replacing it from a temporary file in the
  same directory whose name does not end in `.json`, registers as `mawsd`
  (or `mawsd-<12 hex>` for a daemon of another profile) and removes its
  file at a clean stop. So the reader takes only names ending in `.json`,
  never fails on a file that vanishes between the listing and the read,
  and reads a half-written or unparsable file as not alive. When more
  than one registration is alive and suits, the order is fixed: the name
  `mawsd` first, then the others by name, never the directory's listing
  order. The link is `<url>/s/<session>`: a surface registers `url` as an
  origin with no trailing slash, and the reader strips one trailing slash
  if present. Tests pin each of the three (M2: the reader and the view's
  `surface`; M3 and M5: the choice and the line read the same).
- The record and the surfaces are asked for with `probe` (I5), which
  answers a few hundred bytes whatever the record holds, and only where
  the table needs them: with no record and the setting off the choice
  costs two `$.env.get` and one `$.fs.exists`, and no process.
- 'sheet': the mod tells `ask.tsx` to yield (I11), registers the tool
  under the sheet's schema and description, withdraws the built-in
  (deferred, and a model's call of it denied with `Withdrawn in this
  session: ask through mcp__sminos__AskUserQuestion, which puts your
  questions on the session's sheet.`), and orders `start` at the classic
  SessionStart. 'today' and 'none': the sheet's hooks pass everything
  on, and `ask.tsx` does what it does in such a session today; only a
  stored call of the sheet's form is still drawn by the sheet (M5).
- **Started.** `started` is the session id whose `start` step has
  answered. Until it names the session the process is in, the mod orders
  no other step for it: a hello, a tick or a check that comes first does
  nothing, and a call that comes first (none can before the engine has
  run the session's start) is answered that the sheet is starting. A
  reloaded module reads `started` and goes on; a `/clear` sets it at the
  new session's `start`. So no drain can make a record ahead of the
  `start` that gives it its floor and, for a fork, `import.never`; the
  step refuses to, as well (`no-record`).

### I9 · Delivery in a terminal session

`H/sheet.tsx` holds, in memory: the view it last adopted; the flights;
the notices; and whether a main turn runs (`turn.start` and
`turn.complete` without an `agentId`, as `ask.tsx` tracks it). The view's
`ready` holds, for the main conversation, at most one envelope: its text,
its keys, whether it **wakes** (it holds an answer that is not owed
across a stop) and whether more is pending behind it. What wakes is
packed first (I7), so the ready envelope wakes exactly when anything
pending for the main conversation does: a fresh answer is never held
behind an envelope of old ones that starts no turn. An envelope is
**ready** when none of its keys is in a flight.

| trigger | condition | route |
|---|---|---|
| a view is adopted | no main turn runs, and the ready envelope wakes | idle: `$.prompt.submit` |
| a main turn completes with reason `answer` | the ready envelope wakes | idle |
| a `tool.call` of the model's main loop returns, not denied, not aborted | an envelope is ready, or a notice waits | result: `context` on that result |
| a prompt enters (`prompt.submit`, any origin) | an envelope is ready, or a notice waits | prompt: `context` on that prompt |

- A route takes the ready envelope in the same synchronous step that
  hands it over, so no two routes take it. It carries one envelope; when
  `more` is set, the view after its landing carries the next.
- A notice goes as a context entry of its own beside the envelope, or
  alone, on the result and prompt routes only: a notice starts no turn.
- A dismissal and an outcome owed across a stop never make an envelope
  wake; they leave with whichever route opens first, a fresh answer's
  idle turn included (§5.2, U11).
- **The idle route is opened from a `$.clock.after(0)` callback, never
  inside a hook's dispatch.** C0's P1: a submit made inside a `tool.call`
  hook is refused by the host, and a view can be adopted there (a check
  that found the inbox grown). A submit made outside every dispatch
  starts a turn and is not seen by this plugin's own `prompt.submit`
  hook, which is what the prompt route wants: it never attaches to the
  mod's own prompt.

**A flight fails** when its route says the envelope did not go: the
submit resolves `drop` or rejects; the prompt beneath resolves `drop`,
throws, or resolves with a `context` that no longer holds the envelope (a
hook beneath took it out; `PromptSubmitResult.context` is what entered).
The envelope is ready again, with today's toast.

**A flight lands** when the mod's `session.append` hook, after its
`next(e)` has resolved, finds in the row as stored a block whose `keys`
it then hands to a `landed` step. The row counts only when the engine
says it is one of the tool's own: of the main conversation (no
`agentId`), and either door `hook-context` with origin `{ kind: 'plugin',
event: 'tool.call' | 'prompt.submit' }`, or door `prompt` with origin `{
kind: 'plugin', name: 'sminos' }`. A human's prompt that quotes an
envelope has another origin and lands nothing; neither does MAWS's steer:
in a MAWS-run session only a `delivered` line moves an outcome (§5.4).
Landing is read from the row and never from the flight, so it also holds
for a row a module before a reload sent.

**A flight that has neither failed nor landed when the main turn it
belongs to completes** (the turn that was running for the result and
prompt routes, the turn the idle prompt started) is settled there, in
the running process: the mod reads `$.session.messages({ as: 'api' })`
and looks for the block's keys in the conversation the model holds.
Found, it orders `landed`; not found, the envelope is ready again. This
is the exit for a context a hook outside this plugin dropped on the
result route, which no return value reports.

**Which turn a flight belongs to** (a critic's pointer, relayed by the
composite's writer, 2026-11-24; M4 verifies it and records here what it
found). An idle submit can wait behind another prompt already queued (a
peer's message, a notice, another plugin's submit, the human typing):
that prompt's turn starts and completes before the mod's prompt has
entered. Taken as the flight's turn, its completion would find no block,
ready the envelope again and submit it a second time, and the first
submit would then land as well: the record right, the conversation
holding the answers twice. So an idle flight is settled only by its own
landing row, its submit's failure, or the completion of a turn that its
own prompt opened (known by the prompt's row having entered, or the
`turn.start` that follows it); a turn that completes while the flight's
prompt has not entered settles nothing and readies nothing. The result
and prompt routes are held to the same rule where a second turn can
interleave: a flight is settled at the completion of the turn its
context entered. Pinned by a test that queues a foreign prompt ahead of
the idle submit and asserts one envelope in the conversation, and by a
live case if a scripted one cannot show the ordering.

**At a `start`** whose effects name outcomes pending before its drain
(`start.before`), the mod searches the transcript for `<sheet-delivery>`
(the one `perl` pass of `ask.tsx`'s `searchArgs`, given this form) and
hands to `landed` the keys it finds in rows of the same two kinds, told
there by what the stored row holds: an attachment of type
`hook_additional_context` whose `hookName` is `tool.call` or
`prompt.submit`, or a user row whose origin is this plugin's. A search
that fails lands nothing, and the outcomes go again, owed across a stop.
Where the stored row says less than the live event did, its form
decides, which is U13's limit.

The search hands `landed` every key it finds in a stored block of those
kinds, not only the first 200 that `before` lists (`beforeCount` may be
larger): `landed` of a key that is not pending does nothing.

**To a subagent** (§6): the view's `ready` holds one envelope for each
running subagent with outcomes `taken`. The mod sends it with
`$.session.send({ to: { agentId }, text })`, from the same
`$.clock.after(0)` hop, and reads the answer: `isDelivered: true` is its
landing (the engine has queued it; C0's P2: the subagent reads it at its
next request); `isDelivered: false` and a rejection both order `reroute`.
The mod reads `$.agent.list()` before every step it orders while the view
holds a question or an outcome of a subagent, and passes those `running`;
an agent that ended since is rerouted by the step's `agents` rule. An
agent that ends between that list and the send is resumed by the engine
to read it: rare, and it costs one more run of that subagent and the turn
its hand-back starts in the main conversation. `direct` is true for both
runners (C0's P2).

**Notices**, each one line the mod composes from the view, never kept (a
start's context names every open question and its asker):

- a subagent that stops with questions open (E14): `[sheet v1] The
  subagent <name> (<agentId>) ended with questions still open on your
  sheet: q4 "…", q6 "…". Their answers will come to you; withdraw what you
  no longer need.`, each question's first 200 characters as a JSON
  string;
- a call whose outcome was not known when it was answered (I5): `[sheet
  v1] Your earlier call (<callId>) did change the sheet: <its result's
  first line>` or `… changed nothing; call again if you still need it.`

**In a MAWS-run session** the mod opens none of the four routes (a turn
the tool submits there is a turn MAWS did not send: C0's P1); it drains,
sends to running subagents, and takes `delivered` lines; the step
composes no envelope for the main conversation there. The context §5.4
has the tool add to a steer that carries an ended subagent's answer is
C5's to build; C0's P1 showed the hook sees the steer and can add to it,
and `show --json --keys` (I4) gives it each outcome's question and
labels, bounded.

### I10 · What the tool supplies at a start (§5.5)

Composed by the step (it holds the labels and the whole texts), returned
by the mod as the classic SessionStart's `additionalContext`, which C0's
P5 found reaches the model at a startup, a resume, a compaction, a fork
and a `/clear` in both kinds of session:

    [sheet v1] Your question sheet, after <a resume | a compaction>.
    Open: q7 (revision 2) "Auth method" — "Which auth method should the login use?" Options: 1. OAuth; 2. Passkeys; 3. Magic link.
    Open: q8 (revision 1), asked by the subagent reviewer (a1b2c3) — "…" No options: answered in text.
    Answered, the answer not yet delivered to you: q9 (revision 1) — "…" Options: 1. Yes; 2. No.
    New ids continue from q12.

It has the envelope's budget. When the whole would pass it, every
question is cut at 300 characters and every label at 80; when it still
would, the list stops where the budget does and ends `and 37 more open,
q41 to q97: sminos sheet show --session <id> prints them.`

Nothing when the sheet has no open question and nothing pending, but for
these, each one line:

- a fork: `[sheet v1] This conversation is a copy: its question sheet
  starts empty. Questions asked before the copy belong to the conversation
  it was copied from, and their answers will not come here; ask again
  what you still need.`, and `New ids start at q12.` when the floor is
  known at that moment;
- a record that was lost (a `resume` whose conversation holds stored
  calls of the sheet and whose record is absent): `[sheet v1] The question
  sheet's record was not found, so the sheet starts empty; questions asked
  earlier are no longer open. New ids start at q12.`
- an import (M5): `Moved onto the sheet from the earlier question tool:
  q1 "…" (call <id>, question 1), …`

**As built (M2).** The step composes the whole context, the import line
included (the step imports; M5 only stages the asks). Its first line reads
`after a resume` for a resume's start, `after a compaction` for a drain
with `context: compact`, and `after a start` for any other start. A
subagent asker follows the revision: `, asked by the subagent <name>
(<agentId>)`, the header after it as a JSON string. Only the main
conversation's pending outcomes are listed; a pending dismissal reads
`Dismissed, not yet told to you: q9 (revision 1) …`. The import line,
each question cut at 200 with `…`, stands before `New ids continue from
q<n>.`, which always ends the context, and has its own budget of 10,000
UTF-16 units, stopping with a count and the `sminos sheet show` pointer.
`and N more open` counts open and pending left out together; one left
out reads `q41`.

**The floor** of a record that has assigned no id, in a conversation that
may already have used some (§3): the highest `q<n>` the mod finds in the
conversation it holds: in the tool's stored results, in envelopes'
blocks, and in the `New ids … from q<n>` sentence above, which is why a
context states it. The conversation is read where it can be: for a
resumed terminal session and a `/branch`, from the transcript at the
start; for a fork made with `--fork-session` and for every MAWS-run
launch, C0's P5 found that at the first classic SessionStart the
transcript does not exist yet and `$.session.messages()` rejects, and
that both read at the mod's `session.start` after its `next` and at the
first prompt. So the floor travels on two events: `start` carries it when
the conversation could be read by then, and every `call` carries it while
the view's `nextId` is 1, read by then at the latest (a call follows a
prompt); the step raises `nextId` before it assigns the record's first
id. A module cannot learn which session a fork copied, so the parent's
record is not read.

### I11 · The mod's layout

`H/register.tsx` registers, in order: the bridge, the backtick guard,
`registerSheetBand` (from M5), `registerAskBand`, `registerSheet`,
`registerAsk`, the address, the name. The sheet's hooks are registered
before the ask's of the same event, so they are the outer ones: a hook of
the sheet's handles what is the sheet's and passes the rest on with
`next`.

What `registerSheet` registers, by the milestone that adds it:

| from | hooks |
|---|---|
| M3 | `session.start` (the choice, the registration, the timer); the classic `SessionStart` (`start`; a compaction's drain), `session.end` (`/clear`); `tool.describe` and `tool.call` for the tool and for the built-in; `tool.call`, `prompt.submit` and `turn.complete` without a matcher, for the check of K4 alone; the classic `SubagentStop` (a drain) |
| M4 | the routes on those three; `turn.start`; `session.append` (landing); the contexts returned from the classic `SessionStart`; the notice at `SubagentStop` |
| M5 | `ui.render` for `ToolUse` and `ToolResult` (the row), and `registerSheetBand`'s `AbovePrompt` |
| M6 | the snapshot's writes |

`H/sheet-model.tsx` gains its parts where they are first used: the
input's schema and validation in M3; the block's parser and the notices
in M4; the parser of a result's first line (I6's grammar, held to
`grammar/result.examples.json`) and the lines of the row and the band in
M5.

`H/ask.tsx` gains one switch, `yieldAsk()`, which the sheet's
`session.start` hook calls before its `next` when the choice is the
sheet. Yielded, `ask.tsx` registers no tool, describes nothing, withdraws
nothing, holds and delivers nothing, and draws no band and no open ask;
two things it still does: its row hooks draw a stored call of today's
form (its input has `questions`; §2.1) as they draw any answered or
declined one, and its SessionStart hook still reads a resumed
transcript's asks, which it hands to the sheet in place of adopting them
(M5). The switch is the module's own variable, so a reload starts
unyielded and the kept choice sets it again.

`H/sheet.tsx` exports, for `H/bridge.tsx`'s `sheet` op, `sheetNudge(keys):
Promise<Answer>`, which reaches the engine through the closure the
sheet's `session.start` made (`$` crosses no import: Constraints).

A stored call's form is told by its input: `ask` or `withdraw` is the
sheet's, `questions` today's. From M5 the sheet's row hook draws the
first in every session, whatever the choice, from the call's input and
result alone, with the view's `closed` for the receipts where a view
exists.

### I12 · The project log (§11)

What the log is owed is kept in the record and written from there, never
read out of the transcript: a subagent's call and an answer accepted
while the session was stopped are in no main transcript. A step adds
each event to `log.owed`, numbered, in the same replace as the change
that owes it:

| the change | the event owed |
|---|---|
| a question added (an import included) | `{ "kind": "question", "src": "sheet:<session>:<id>", "text": [<question>], "choices": [<labels>] }`; a revise owes nothing |
| an answer applied | `{ "kind": "answered", "src": "sheet:<session>:<id>", "text": <I7's line after the id> }` |
| a dismissal applied | `{ "kind": "answered", "src": …, "text": "dismissed", "closed": "dismissed" }` |
| a withdrawal | `…, "text": "withdrawn", "closed": "withdrawn"` |

- **The source names the session.** `q1` is every session's first
  question, and `append_host` files an `answered` whose question the
  session's own events do not hold under whichever other session of the
  machine holds that `src` (`_askers` in `S/sminos.py`). Within one
  project that lookup never runs for a sheet's answer, because the
  question is always written before its answer and to the same writer.
  It would run after a move to another project, and find another
  session's `q1` there; with the session in the source no other session
  can hold it.
- **A question's events go to the project its question went to.** When
  the projection writes a `question`, it records the project's id under
  the question's id (`log.projects`), in the replace that takes the event
  off `log.owed`; every later event of that question goes to that
  project, whatever project the session is in by then, as
  `close_questions` already closes a question where it was asked.

**The projection**, `sminos sheet log --session <id>` (M6): under the
lock it reads `log`; outside it, it appends each owed event for the
session's writer through `append_host`, which adds `from` and `to` and
whose `(kind, src)` rule appends nothing twice, a `question` to the
session's project as `sminos record` resolves it and any other event to
its question's recorded project; under the lock again it removes from
`log.owed` the numbers it wrote, records the projects, and replaces
`state.json`. The mod orders it, not awaited, after a step whose effects
say something is owed; the Stop hook's `sminos record` runs it for a
session that has a record; removal runs it first and then appends, for
each question still open, `…, "text": "removed with its sheet",
"closed": "removed"`. A question owed while its session is in no project
waits until the session has one or the record goes. `close_questions` in
`S/sminos.py` passes over a `src` that starts `sheet:`: a sheet question
outlives its process.

### I13 · The snapshot (§11)

In a session whose choice is the sheet, `H/sheet.tsx` writes the `ask`
key that `ask.tsx` writes elsewhere, still `shape: 2`, so doperpowers'
appeal and reload read it unchanged:

- `asks` holds the sheet's answered questions in the shape appeal's
  evidence reader already takes (`hooks/mods/appeal.tsx`, `evidence`: it
  reads `questions[].question` and `answer` of each ask whose `status` is
  `answered`): one ask a question, `{ id: "sheet:<id>", questions: [{
  question, header, options: [], multiSelect: false }], status:
  "answered", answer }`, from the view's `answered`: the 32 questions
  answered last, which the record keeps (`Closed.answer`), so a lost
  answer of a step, a reload and a resume all read the same. A dismissal
  is no answer and adds none.
- `answered` is the view's `answeredCount`, which only rises.
- `undelivered: []`, `isDialogUp: false` (the sheet raises no dialog),
  `isTurnRunning`.
- One field more, for the open ones:

      sheet?: { open: { id: string, revision: number, header?: string, question: string, asker: string }[], owed: number }

  `asker` is `main` or the agent's id; `owed` counts `pending`.

The choice between this and a new reader in appeal went to the
projection: the judge gets the question and the human's real answer
through the code it has, and no plugin but sminos changes.

## What the probes settled

C0 ran P1 to P5 against engine 2.1.331; each verdict is written where
its decision stands. What each fixed here:

| probe | settled | where |
|---|---|---|
| P4 | The lock (`fcntl.flock` on a file beside the record) and the replace (`os.replace` of a synced temporary file) hold as built; a hook's own write in place tears, which is K1's ground. A reader without the lock saw no partial write on APFS; I4 does not depend on it. | I1, I4, I5 |
| P3 | Capture is `$.tool.check` for a Read, and only on `allow` a `$.tool.call` of Read: both run the other plugins' guards and the settings' rules, and the guards' scrubbing reaches the caller. Read cuts nothing: a file comes back whole, or over 256 KB without a range it errors, so a reference has no "cut". A path outside the working directories is always refused. A plugin's Read enters the session's read state, so after a compaction the engine attaches the captured files to the model's context as if the model had read them: accepted by the composite's writer as a side effect, and a known limit (M7). The "unchanged since read" stub never fired; its refusal stays as a guard. | I5 (`Capture`), I6; M3 |
| P2 | The send to a running subagent works in both kinds of session and answers `isDelivered`; the engine frames it as the coordinator's, so the envelope says whose it is; an ended subagent is resumed by a send, so one is never sent to. | I7, I9; M4 |
| P5 | The SessionStart context arrives at every kind of start; the block arrives byte for byte in every context and in the row a `session.append` hook sees. At a MAWS-run launch's first SessionStart, and for a `--fork-session`, the conversation cannot be read yet, which moves when the floor is read. | I7, I9, I10; M3, M4 |
| P1 | A submit from inside a `tool.call` hook is refused, and one made outside every dispatch is not seen by the plugin's own `prompt.submit` hook: the idle route's hop. In a MAWS-run session the tool submits nothing. | I9; M4 |

Not shown by the probes, and so checked by the live check where it
bears: a real model reading a context; the owner's own secrets guard
(devcloud's) in the place of the probe's stand-in (M3's `secret` case);
an automatic compaction.

## Plan of Work

Seven milestones. M1 is the composite's G1 and is small on purpose: the
MAWS app (C3) waits on exactly what it publishes. M2 to M5 are G2, with
M6's log; M6 and M7 are G3. What blocks each is in Progress.

| gate | closed by |
|---|---|
| G1, the contracts published | M1 |
| G2, a terminal session | M2 (the record), M3 (asking), M4 (delivering), M5 (drawing, import), M6 (the log's line of Acceptance 6); run whole in M7 |
| G3, the other readers | M6 (the snapshot, the log), M7 (the description against C1) |

### M1 — The contracts, published (G1)

**At its end.** `sminos/types/sheet/` exists as I1 lays it out, and two
verbs of the command work on a record with no session running: `sminos
sheet put` appends what it is given and prints `queued`, and `sminos sheet
show --json` prints I4's model. Another repository can copy the set and
hold its own reader and components to it. The set is published when this
milestone's pull request merges; nothing else of the child is in that
pull request.

**Touches.** `sminos/types/sheet/` (new); `T/sheet-contract.gen.py` (the
generator that writes the set), `T/sheet_schema.py` (the validator),
`T/test_sheet_contract.py` (new; its line at the end of `run_suites_c` in
`T/run-sminos-tests.sh`); `S/sminos_sheet.py` (new); `S/sminos.py` (the
`sheet` parser, and its dispatch ahead of the migration when `--session`
is given); `S/CLAUDE.md` and `sminos/skills/sminos/SKILL.md` (the two
verbs); the version.

**Interfaces.** Exposes I1's set, I2, I3 (the line, the door, `put`,
`show`), I4, I6's grammar with its examples, I7's schema, budget and
examples, the surface's schema. Consumes nothing.

**Decisions.**

- The fixtures are written by the generator, by hand from §4.2 and this
  document's tables, and never computed by an implementation: the house
  rule of `T/dx4-jobs.gen.py`. The set is the contract the step (M2) and
  MAWS's reader are both held to, not the output of either. The generator
  is deterministic (session ids `5eed0000-0000-4000-8000-0000000000NN`,
  NN the case's place in the table below from 01; fixed times, fixed
  keys); the suite runs it into a scratch directory and compares bytes
  with the committed set.
- The cases, each a `before`, the one event that takes it to `after`
  (a `drain` unless said), the verdict each key ends with, and both
  `show` outputs. Every `after` carries what its step owes the log
  (`log.owed`):

  | case | covers |
  |---|---|
  | `empty` | a new record |
  | `answer-applied` | §4.2 row 1; a pick with text; an image |
  | `answer-stale` | row 2: an answer to revision 1 of a question at revision 2 |
  | `two-surfaces` | rows 1 and 3: two answers to one question in one tail, from `page` and `cli` |
  | `closed-withdrawn` | row 3: an answer and a dismissal for a withdrawn question; `show`'s `closed` reads `withdrawn` for a question no line ever touched |
  | `dismiss-applied` | row 4 |
  | `retract-queued` | row 5: a retract after its target (`cancelled` before the step), and an edit (a retract and a new answer) |
  | `retract-too-late` | row 6: the target applied by an earlier step; another refused as stale; a retract that names a retract, and one that names a `delivered` line |
  | `retract-unseen` | U1: a retract whose target no line carried; after it the target's own verdict, `kind: "unseen"`, and its entry in `sent` |
  | `retract-unseen-late` | U1, from the state above: the target's line arrives and is set aside, the verdict unchanged, its question still open; a second retract of the same target reads `too-late` |
  | `delivered-mixed` | row 7: one key pending, one delivered before, one unknown; after it `show`'s `closed` holds the delivered answer's receipt, and `pending` holds it no longer |
  | `resent-key` | row 8 |
  | `resent-then-retract` | a resent copy of an applied line, then a retract of it |
  | `batch` | one Send of three lines, two answers and a dismissal, a main recipient and a running subagent's (`taken`) |
  | `long-text` | an answer of 18,214 characters: its outcome's `textFile` and the file under `texts/` |
  | `stopped-queue` | event `start`: a queued answer, a queued dismissal (the question hidden), a queued answer retracted; after it, outcomes owed across a stop |
  | `imported-legacy` | event `start` carrying an ask valid only under today's tool: a 2,001-character question, a 201-character label, a preview on a multi-select question; after it the three as questions with `importedFrom`, unchanged |
  | `skipped-and-unknown` | U2, U3 |
  | `references` | a text reference with lines, one without, an image; their bodies under `refs/` |
  | `torn-tail` | an inbox that ends in bytes without a newline (a whole answer object that lacks only it): no reader lists it, the drain applies nothing and leaves the offset at the last newline |
  | `torn-tail-resent` | the same after the surface sent again: a newline, then the answer under the same key; the first copy is applied, the second set aside, one verdict |

  `grammar/result.examples.json` holds: a call that added eight; one that
  added, revised and withdrew; one that partly succeeded with an added
  and a revised entry and a refused one (the composite's own example);
  one whose entry was refused for two options with one label; one with a
  refused withdrawal only (`Nothing done.`); a foreclosed call (`Nothing
  done.` and its clause); and one whose outcome was not known (`Outcome
  not known yet.`), whose `parsed` holds no id.
- The envelope's examples are I7's six, each with its input record,
  whole and concrete: no key, entry or path is elided but for `{HOME}`,
  and each example's `answered` and `dismissed` name exactly the
  questions its prose does. The generator writes each `envelope.txt` by
  hand from I7's rules, as it writes the fixtures; it derives every
  `texts/` file's name from the text it wrote there.
- The door's telling of the bridge is built now, though no mod answers
  `sheet` before M3: a bridge that does not know the op reads as
  `queued`, which is what a surface must handle anyway. It reuses
  `post_command` and `endpoint` (`S/sminos_control.py`,
  `S/sminos_bridge.py`), imported only on that path, so `put` to a
  stopped session imports neither.
- `show` without `--json` prints, a question a block: its handle (`q7`,
  `q7@2`), the asker when a subagent, the header, the question, the
  options numbered with the recommended one marked, the references by
  path with `changed`, and a queued answer under it.
- `state.json` is only read in this milestone (the generator writes the
  fixtures'). `put` refuses a session without a record.

**Does not touch.** The mod, in any file. The step and the other verbs
(M2). No session behaves differently after this milestone.

**Proves.** G1. Tests pin: every file of the set validates against its
schema, the examples included; the manifest is the files'; the generator
reproduces the set; `show --json` over every `before` and `after` equals
the fixture's; each envelope example has as many keys as answered and
dismissed entries together, in that order, names in its block the ids
its prose names and no others, is at most 60,000 UTF-16 units and 200
keys, holds no text past 500 characters and no pick that is not a place
in its block, and names only outcomes pending for its recipient in its
input record; every `texts/` file is named by the hash of its bytes;
`more` is set exactly where the input record holds more for that
recipient than the envelope's keys; for `long`, the four texts in full,
and with one carried by its file, measure over the budget, and with two
under; for `more`, the fifth Send would make 250 keys; for `split`, the two
envelopes together name every key of the Send once, in order;
`state.schema.json` accepts the
`imported-legacy` record and `tool-input.schema.json` refuses the same
question as an entry; `put` to a fixture copy appends exactly its lines,
one batch id on a call of several, `at` filled, and prints `queued`; a
line that fails the schema, an image that is not there, a pick that is
no label at the current revision each exit 2 with nothing appended; a
session with no record exits 3; eight processes of twenty-five calls each
leave two hundred calls' lines whole, each call's lines together; a file
without a last newline gets one before the next line; `put` answers a
stand-in bridge's verdicts (`T/bridge_standin.py`).

### M2 — The record: the step, the lock, the command's other verbs

**At its end.** `sminos sheet step` makes every transition of "The state
machine" and composes what leaves the record, and a sheet can be driven
whole from a shell with no engine: order a `call`, read it with `show`,
`answer` it, order a `drain`, see the verdict, the pending outcome and
its ready envelope, order `landed`, see it delivered. Every published
fixture replays: the step applied to `before` gives `after`, byte for
byte once both are written in the generator's serialization, and the
envelope it composes from each example's input record is that example's
published text.

**Touches.** `S/sminos_sheet.py`; `S/sminos.py` (the parser's other
verbs); `T/test_sheet_step.py` (new), `T/sheet-vectors/` (new: vectors
for the events the published set does not carry: `call`, `settle`,
`landed`, `reroute`, the acknowledgement, the `agents` rule),
`T/sheet_surface.py` (the stand-in surface); `S/CLAUDE.md`, `SKILL.md`.

**Interfaces.** Exposes I5 whole (`step`, `probe`), I7's composer, I10's
composer, and I3's `answer`, `dismiss`, `retract`, `remove`, `surfaces`.
Consumes M1's.

**Decisions.**

- The step is a pure function, `step(state, tail, event, now) → (state,
  effects)`, inside a shell that owns the lock and the files. The tables
  are tested on the function; the lock, the replace, the staging and the
  deaths on the shell.
- Should the step and a published fixture disagree, §4.2 and this
  document's tables say which is wrong. A wrong fixture is reported to
  the composite's writer and corrected by a ruling (K2), never edited
  here.
- A death is tested in process: the replace made to raise, the write cut
  short, the process killed after the replace, each followed by what the
  mod would order next (the same event again, or `settle` for a call),
  which must leave the record as one clean step would. No fault switch
  ships in the command.
- `start`'s import (I2's `import`): with `today.definite`, each ask whose
  call id is not in `import.calls` becomes one question for each of its
  questions (asker `main`, revision 1, `importedFrom`, every field as
  today's tool held it, whatever its length, a lone UTF-16 surrogate in
  any string replaced with U+FFFD), and its ids are recorded
  under the call id; with `definite` false nothing is imported and
  nothing recorded, so the next start tries again; with `import.never`,
  set when a new record's first `start` has source `fork`, nothing ever.
- `remove` takes the lock, refuses a session that runs
  (`session_running`) unless `--cleared`, deletes the record and its
  staging, and leaves the lock file. From M6 it projects the log first.
- `answer` reads the handle as I3 says; its `--pick` takes a label in any
  case or a number, as `resolve_answer` in `S/sminos_control.py` reads an
  answer today.
- Refusal times and an envelope's times are the machine's local time,
  formatted by the step, so one clock and one zone word every time the
  model reads.

**Does not touch.** The mod. The projection and the sweep (M6); `log.owed`
is written from this milestone on and waits.

**Proves.** The tables, each row by a named vector; and at the record's
level Acceptance 3's refusal (a `stale` verdict with `current`),
Acceptance 6's queue (`show` reads `queued`, a retract takes it back, a
`start` applies what is left as owed across a stop) and Acceptance 19's
first half. Tests also pin:
- a drain, a `landed`, a `reroute` and a `start` ordered twice equal
  once; a `call` ordered twice answers the first result and adds nothing;
  `settle` after a committed call answers its result; `settle` first
  forecloses, and the call ordered after it commits nothing; a call
  ordered after its acknowledgement finds its staging gone and commits
  nothing; a `start` empties `calls` and the staging;
- any event but `start` on a session with no record answers `no-record`
  and makes none;
- `show`, then a revise, then `answer q2 --pick 1` is refused with the
  sentence naming `q2@2`; `answer q2@2 --pick 1` picks the new first
  option; a handle naming a revision no longer current is refused;
- a record at every bound (500 open questions of four-byte characters at
  the input's limits, 300 pending answers of 20,000, 2,000 closed)
  and 40 registered surfaces answers a step in under 3 MiB, and `probe`
  in under 4 KiB;
- the composer: for each published example, the envelope composed from
  its input record under its `case.json` is its `envelope.txt`, byte for
  byte once `{HOME}` is filled; a batch of fifty answers of 20,000
  characters leaves in envelopes none over the budget, each text whole
  or carried by head and file, no text twice in full, each but the last
  saying more follows, and nothing in the record changed by composing;
  what one envelope left packs with a batch accepted after it; two
  batches that fit together leave together; 201 keys leave as 200 and
  one; a fresh answer accepted after sixty old ones that fill an
  envelope is in the first envelope; the context cut and stopped at its
  budget;
- a `start` that applies 500 queued answers of 20,000 characters to
  questions at the input's bounds answers in under 3 MiB, and the step
  after it carries the same `answered` and `answeredCount`;
- a call that only withdraws, and one whose every entry the mod refused,
  each staged as `call.json` alone, apply; the same ordered again after
  its acknowledgement answers `gone`;
- an inbox ending in an unfinished write: the offset stops at the last
  newline, and the fixtures `torn-tail` and `torn-tail-resent` replay;
- a reader looping `show --json` through two hundred doors and fifty
  steps at once never reads a `state.json` that does not parse, sees
  `seq` only rise, and at the end every key has one verdict and every
  `applied` answer is pending or delivered; `put` with `--no-wait` and a
  step racing it lose no line; a record removed while a door waits on
  its lock makes that door exit 3, and the lock file is still there.

### M3 — Asking: the start choice, the sheet's schema, a call

**At its end.** A terminal session started with `SMINOS_QUESTION_SHEET`
on and the stand-in surface alive has the sheet's schema under the
tool's name. A call adds, revises and withdraws through a step and
answers I6's text; a referenced file is captured through the engine's
Read and a file the session may not read refuses its entry; a subagent
can call; `sminos sheet put` to the live session prints a verdict within
a second. A `/clear` removes the session's record; a fork starts with an
empty one whose ids begin past the conversation's. With the setting off,
no live registration, or `SSH_CONNECTION` and only a `local` surface,
the session has today's tool, untouched. Answers are accepted and not
yet delivered: that is M4, and the setting keeps the gap from anyone who
did not turn it on.

**Touches.** `H/sheet.tsx`, `H/sheet-model.tsx` (new); `H/register.tsx`;
`H/ask.tsx` (`yieldAsk` and nothing else); `H/bridge.tsx` (the `sheet`
op; a nudge at its child's hello); `sminos/types/sminos.d.ts`
(`SheetKept`); `T/mods/sheet-model.test.ts`, `T/mods/sheet.test.ts`
(new); `T/mods/test-sheet-step.sh` (new: bun runs the mod's pure
functions against the real command, as `test-ask-search.sh` does for the
search; its line in `T/mods/run.sh`); `T/mods/live-sheet-check.py` (new);
`H/README.md`, `H/CLAUDE.md`.

**Interfaces.** Exposes I8, I11's M3 row, `sheetNudge`. Consumes I5 and
I3's op.

**Decisions.**

- A call, in order: validate the whole call (I6); check each entry's own
  rules and capture its references, one after another, before any step,
  since a capture is slow and a step is not; stage the call (`call.json`
  always, and a file for each entry that passed and each body); read the
  running agents when the caller or the view has a subagent; order
  `call`; raise one `$.ui.notify` for a call that added something (its
  first added question, `(+N more)`), as today's tool announces an ask;
  answer the step's `result`. With no answer from the step the mod
  settles (I5) and then answers one of: the recorded result; a
  foreclosed call's `Nothing done.` with its clause; or `Outcome not
  known yet.` with its second line (I6). All three are results, not
  denials, so each stored call has a first line of the grammar.
- **Capture** (C0's P3): `$.tool.check({ tool: 'Read', input })`, and
  only on `allow` a `$.tool.call` of Read; `lines: [a, b]` is Read's
  `offset` a and `limit` b − a + 1. The body kept is `result.file.content`
  for a text, the field a guard's `tool.call` hook rewrites, with Read's
  `startLine`, `numLines` and `totalLines`; `result.file.base64` and its
  `type` for an image. `abs`, the size and the modification time are read
  with `$.fs.stat(path, { resolve: true })` after the check allowed the
  Read. A check that is not `allow`, a Read that errors, and a result
  that is the engine's "unchanged since read" stub (never seen on
  2.1.331; kept as a guard) each refuse the entry with the engine's
  reason. Each body is written to the staging as it is captured; nothing
  of a refused capture is.
- The asker is the call's `agentId`; its name is that agent's
  `description` in `$.agent.list()`, its `type` when that is empty.
  `SUBAGENT_REFUSAL` is today's tool's alone.
- The floor (I10) is this milestone's: the mod reads the conversation
  where C0's P5 says it can (at the start for a terminal's resume and a
  `/branch`; else at `session.start` after `next`, or at the first
  prompt) and sends it on `start` when it has it and on every `call`
  while the view's `nextId` is 1.
- The description the tool is registered under is
  `tests/output-styles/question-sheet/description-v3.md` as it stands on
  `main`, word for word: the owner's ruling on C1's baseline (§2.4 at the
  composite's `5f53131c5`: "ask when a question comes up, then keep
  working", the sentence on batching dropped). It is held as a constant in
  `H/sheet-model.tsx`, and a test holds the constant equal to the file.
  C1's two evals default to the same file; M7 ships it unless they fail
  on it.
  Each property's description is the one C1's stub registers for that
  field (`FIELD_DESCRIPTIONS` in `tests/output-styles/question_sheet.py`;
  `description-v3.md` sets none of its own), so the evals measure the
  tool as it ships.

  The schema the tool is registered under is the published
  `tool-input.schema.json` with a description on each property; a test
  holds the constant in `H/sheet-model.tsx` equal to the file once the
  descriptions are taken out (a mod loads no JSON: `H/bridge-routes.tsx`
  is the precedent).
- Views are adopted in the record's order (the durable points' rule):
  the mod keeps, for the session it is in, the highest `seq` it adopted,
  and drops the view of any answer below it or for another session.
- A `/clear` has three chances to remove the record it leaves: the
  `session.end` hook (reason `clear`), which is given little time and
  may not finish; the next SessionStart of source `clear`, which names
  only the new session (C0's P5) and so reads `left` from `SheetKept`;
  and M6's sweep of the cleared notes `sminos/hooks/smns-cleared.sh`
  already keeps. Each runs `sminos sheet remove --session <left>
  --cleared`.
- The timer of K4 starts at `session.start` and ends with the module.

**Does not touch.** The routes, landing, the contexts (M4): M3 orders
`start` and drains and uses nothing of a view's `ready`. The band and the
rows (M5): a call draws as the engine draws an MCP tool's, and
`registerSheetBand` is not registered. The snapshot (M6).

**Proves.** Acceptance 1's call and its result, 3's revise, 9, 15, 16's
ownership, 19's second half (the result's last line with the stand-in
stopped), and G2's line on a `claude -p` inside a MAWS-run session (the
choice, by its table, and the live case `nested`). Tests pin:
- every row of I8's table, the kept choice across a reload and a
  `/clear`, a kept `ask` snapshot without a kept choice reading 'today';
- `ask.test.ts` whole, unedited, in a session whose choice is 'today';
  yielded, `ask.tsx` registers no tool, describes and withdraws nothing,
  holds nothing and draws no band and no open ask, and still draws a
  stored answered call of today's form;
- the built-in denied with the sheet's sentence; a whole-call refusal for
  each of I6's first kind; an entry's refusal for each of its second
  kind, the others applied; a capture refused by the check (a deny, and
  the `ask` of a path outside the working directories), by a failing
  Read (a missing file, one over 256 KB without a range) and by the
  stub, with nothing of the file in the staging or under `refs/`;
- a step that commits and whose answer is lost: the mod settles and
  answers the model the recorded result, once; a step that never ran:
  foreclosed, the model answered `Nothing done.` with the clause, and
  that step run late commits nothing; `settle` unanswered three times:
  `Outcome not known yet.`, then the notice once a later settle answers;
  a call that only withdraws is staged and applied;
- an answer of an older `seq` arriving after a newer one changes no
  view, and its own result is still returned; a bridge hello and a tick
  that come before a fork's `start` order nothing, and the fork's record
  then has its floor and `import.never`;
- a call at every bound of the schema stages no file over 4 MiB; a
  second drain requested while one runs is one more step, not two; a
  hook that only triggers a drain returns before the step does.

### M4 — Delivering: the routes, landing, a start, subagents

**At its end.** An answer accepted in a terminal session reaches the
agent: at once when it is idle, on its next tool result while a turn
runs, with the next prompt after a turn the human stopped; three answers
of one Send in one envelope; a dismissal with the next envelope and never
by a turn of its own. A session resumed with answers given while it was
stopped reads them with whichever route opens first, each marked with its
age, once. After a compaction, a resume and in a fork the agent is told
its sheet (I10). A running subagent receives the answer to its own
question; an ended one's goes to the main conversation naming it; a
subagent that stops with questions open is named to the main
conversation. A Send larger than an envelope arrives whole, by its
files or in more than one envelope.

**Touches.** `H/sheet.tsx`, `H/sheet-model.tsx`; `H/ask.tsx`
(`searchArgs` takes the forms to search for; no behaviour of today's
tool changes); their tests; `T/mods/live-sheet-check.py`; `H/README.md`,
`H/CLAUDE.md`.

**Interfaces.** Exposes I9, and the mod's half of I10. Consumes I5's
`ready` and `context`, I7.

**Decisions.**

- The live check's first case, `rendering`, is run before the rest is
  built: an envelope sent by each route is read back at `session.append`
  after `next`, with the door and origin I9 names, and in the transcript
  with the fields the start's search reads; and the row of a prompt
  submitted from a timer is seen by the mod's own `session.append` hook
  (C0 showed its `prompt.submit` hook is not). Should that last not
  hold, the turn's end still settles the flight (I9).
- The idle route and a send are never awaited inside a hook, and are
  made from the `$.clock.after(0)` hop.
- After a `landed` step the mod redraws.
- A start composes in this order: the `start` step; the search and
  `landed` when `start.before` names keys; the context of the step that
  answered last. All of it inside the classic SessionStart hook, which
  waits only on its own `$` calls.
- The compaction's context (M3 left the seam: its drain is only queued,
  so that hook never waits behind another hook's step). The classic
  SessionStart of source `compact` orders its own step, a drain with
  `context: "compact"`, as its own `$.process.run` (awaiting its own `$`
  call is what K4 allows; the record's lock serializes it with any other
  step) and returns `effects.context` as `additionalContext`, the path
  C0's P5 showed reaches the model. Only when that step gives no answer,
  or when a start's SessionStart had to return before the start choice
  was made (M3's `sheet.early`), does the context go instead as a context
  entry on the next result or prompt route, once.

**Does not touch.** MAWS's steer and the context the tool adds to one
(C5). The band's count of answers that will go with the next message
(M5).

**Proves.** Acceptance 2, 4, 5, 6's resume, 8, 17, 18, and G2's line on
one Send that answers the main agent's question and a running
subagent's. Tests pin:
- each row of I9's table; an envelope that does not wake opens no idle
  route and leaves with the next that opens; an outcome owed across a
  stop and a fresh answer, before any prompt, leave together on the
  fresh answer's idle turn (§5.2); when the old ones fill an envelope
  and the fresh answer does not fit beside them, the first envelope
  holds the fresh answer and wakes; a view adopted inside a `tool.call`
  dispatch submits from the hop, not from the dispatch;
- a refused route makes its envelope ready again; a prompt whose
  resolved `context` lacks the envelope does too; a result route's
  envelope a hook above dropped is ready again at that turn's end, in
  the same process, and one the conversation holds is landed there;
- landing reads the stored row: a row a hook beneath rewrote without the
  block lands nothing; a human's prompt that quotes a whole envelope
  with its framing lands nothing (its origin); a steer lands nothing; a
  row a module before a reload sent lands;
- the start's search finding one of two pending outcomes, the other
  going owed across a stop; a failed search landing nothing;
- a send answering `isDelivered: false`, and one rejecting, each order
  `reroute` and land nothing; `isDelivered: true` lands; an agent gone
  from `$.agent.list()` before the step is never sent to;
- the block's parser on every published example, and on a text holding
  `</sheet-delivery>` and `<system-reminder>`.

### M5 — The terminal's drawing, and the import of today's asks

**At its end.** While a session has open questions the terminal shows one
line above the prompt, `3 open questions · <the surface's url>/s/<session>`,
and the to-human band draws under it. The row of a call lists its
questions and, after the outcome, their receipts. A session that had open
asks of today's tool and first starts under the sheet has them on the
sheet once, and is told.

**Touches.** `H/sheet.tsx` (`registerSheetBand`, the row hooks),
`H/sheet-model.tsx` (the parser of a result's first line; the lines);
`H/register.tsx` (the band's registration); `H/ask.tsx` (`readAsks`
answers whether its read was definite; yielded, its SessionStart hook
hands what it read to the sheet); their tests; `H/README.md`,
`H/CLAUDE.md`.

**Interfaces.** Exposes I11's M5 row and the result's parser. Consumes
the view, I6's grammar and its published examples, I5's `start.today`.

**Decisions.**

- The line (§8.3; its composing is advisory in the composite): drawn by
  an `AbovePrompt` hook of the sheet's that returns its line above what
  `next` drew, the place today's line has, so the to-human view, a
  plugin seated outside this one that draws under what the hooks beneath
  it return, stays under it; not drawn while `hasSurvey`. Its forms:

      3 open questions · http://sheet.localhost:47590/s/<session>
      3 open questions · the page is unreachable: sminos sheet show <session's first 8>
      3 open questions · <link> · 2 answers go with your next message
      2 answers go with your next message

  The link is the first alive, suiting surface's `url`. Between steps the
  timer re-reads the registrations' `heartbeatAt` every third tick, by
  `$.fs.read`, and judges by age alone; a step's view is the full rule.
  The count of answers is the view's `owedAcrossStop`.
- A row, from the stored call alone (I11): one line a question the call
  added or revised, `q7 Auth method — <the question's first sentence
  that ends in "?", else its first sentence>` (§8.1's rule, so a
  question reads the same in the terminal and in the app); no head line
  of the sheet's own: the engine's tool row has its head and its fold
  (the composite's writer's ruling of 2026-11-24 on §8.3). Then the
  receipt in the line's place: `q7 Auth method → OAuth`, `q7 Auth method
  · Dismissed`, `· Withdrawn`, and `· Revised below` when the question's
  revision is past the one this call set. A withdrawal the call made
  draws `q2 · Withdrawn`. A stored call whose first line is `Nothing
  done.` draws that; one whose first line is `Outcome not known yet.`
  draws `outcome not known` and no id, and is not matched to the notice
  that followed.
- Where a receipt comes from (the same ruling). While the record lives,
  from the view's `closed`. For a question the view does not hold (a
  session with no record: a fork, a record removed; one older than the
  500 `closed` keeps), from the `<sheet-delivery>` blocks this process's
  conversation holds: those the landing hook saw, and those of one read
  of `$.session.messages` at the start. A block's answered entry gives
  `→` and the picked labels, read by place from the call's own input at
  that revision, or `their text`; its dismissed ids give `· Dismissed`.
  No scan beyond that. This path only draws: a read that fails or is
  not available leaves the lines without receipts and touches nothing of
  the record, the drain or delivery, and it adds nothing the model sees.
  A question that neither the view nor those blocks know is drawn as its
  line with no receipt.
- A read is definite when the whole file was read, or the search ran and
  its output was not cut. Indefinite, the `start` event says so, nothing
  is imported or recorded, and the next start reads again. A fork's first
  start under the sheet sends no asks: the step records `import.never`.
  Each ask is staged as a file of its own.
- An imported ask's own row stays as `ask.tsx` draws a stored call.

**Does not touch.** Today's band and rows in a session whose choice is
'today'.

**Proves.** Acceptance 1's line, 16's row, the receipts of §8.3, a
line's sentence (a question that opens with a statement shows its first
sentence ending in "?"; one with none shows its first sentence), a row
with no record drawing its receipts from the blocks the conversation
holds and, where neither knows a question, its line bare, and
G2's three import statements (once, also after two resumes; kept when
the read was incomplete; a fork empty and staying empty). Tests pin the
line's four forms, each receipt, the parser on every published stored
call, a stored call drawn with no record, an import retried after an
indefinite read, and an ask only today's tool accepts imported as it
was.

### M6 — The other readers, and the sheet's end of life

**At its end.** doperpowers' appeal ends its passes when the human
answers a sheet question, and its judge reads that question and the
human's answer, as it does for today's asks. The project log holds one
`question` for each sheet question and one `answered` when it closes,
across a stop and a resume; the stop cleanup leaves a sheet question
open. A record whose session's transcript is gone is removed by the
daemon, with its questions closed in the log.

**Touches.** `H/sheet.tsx`, `sminos/types/sminos.d.ts` (I13);
`S/sminos_sheet.py` (the projection; `remove`'s closure);
`S/sminos.py` (`close_questions`; `run_record`'s call of the projection);
`S/sminos_daemon.py` (`sweep_sheets`, in `override_duty`);
`T/test_sheet_log.py` (new), `T/mods/sheet.test.ts`; a case in the
repository's `tests/mods/` on appeal's evidence; `S/CLAUDE.md`,
`H/README.md`.

**Interfaces.** Exposes I12's projection, I13. Consumes `log` and the
view's `answered`.

**Decisions.**

- The sweep removes a record when its session runs nowhere here, its
  transcript is gone as `transcripts_now` sees it, and `state.json` has
  not been touched for an hour (an index that misses a transcript for a
  moment must not cost a sheet); and a record a cleared note names, at
  once. It removes no lock file (I1).
- The projection resolves the session's project and alias as `sminos
  record` does.
- The sweep runs under `override_duty`'s spacing: the `sminos-idle`
  gate's count must hold.

**Does not touch.** MAWS's channel journal (C5). The bridge's own
requests: a sheet question is raised to no desk client by this child
(§8.4 is C6's). `hooks/mods/appeal.tsx`.

**Proves.** G3's first clause, and Acceptance 6's last. Tests pin: stop,
resume, answer leaves one `question` and one `answered` with the real
answer; a session that asks `q1` in one project, moves to another where
another session's `q1` is open, and is then answered: the answer is in
the first project under the asker's writer, and the other session's
question is untouched; two sessions of one project, each with a `q1`,
keep each its own answer; a projection run twice appends nothing; a
projection that fails
after a question was added, then a withdrawal, then a removal, still
leaves that question with its text and choices and its closing in the
log; a subagent's question and an answer accepted at a start are in the
log; `close_questions` closes a question of today's tool and passes a
sheet's; a removal closes what was open; appeal's `evidence`, run
against the snapshot a sheet session wrote, holds a particular sheet
question and the human's answer to it; the snapshot's `answered` rises
by the answers applied and not by a dismissal.

### M7 — The description, what is written beside the code, the acceptance

**At its end.** The tool ships the description that passes C1's
thresholds (automatic capture of context is out of scope: the owner's
ruling on C1's baseline, §10); the manuals say what the plugin now
does; G2 and G3 hold as the composite words them, run as written.

**Touches.** `H/sheet-model.tsx` (the description and the properties'
descriptions); `H/README.md` (a section "sheet" beside "ask"),
`H/CLAUDE.md`, `S/CLAUDE.md`, `sminos/CLAUDE.md`, `sminos/README.md`,
`sminos/hooks/hooks.json` (its description), `SKILL.md`; the version;
`docs/doperpowers/TECH-DEBT.md` (the limits accepted: U6, U8, U13; the
reload's double delivery; an answer to a subagent's question reaching
the main conversation as well across a process death; a captured file
attached to the model's context after a compaction; a rewind after a
delivery; and, logged at M1 as #37 and #38, a lock-free reader seeing a
short write's first lines before its rollback, and a Python validator's
looser `$`).

**Decisions.**

- The description is `description-v3.md` (M3; the owner's ruling,
  §2.4), tested with C1's two evals as C1 merged them under
  `tests/output-styles/`, the registered tool in the stub's place, by
  the one command each eval gives; the thresholds are the ones the owner
  set into the composite's Acceptance 14.
- The acceptance is run on a Mac with the installed engine, in scratch
  homes, by `T/mods/live-sheet-check.py`; Concrete Steps names its
  cases. A case that fails is a fault of M2 to M6 and is fixed there.

**Does not touch.** The default of `SMINOS_QUESTION_SHEET` (C7). Today's
tool.

**Proves.** G2 whole and G3's last clause.

## Concrete Steps

All from the repository's root. A gate is run with `ci-gate` from the
worktree (it tests the committed head); one focused file may be run on
the machine while iterating.

**M1.**

    python3 -B sminos/tests/sheet-contract.gen.py --check          # the committed set is the generator's
    python3 -B sminos/tests/test_sheet_contract.py
    ci-gate --gates sminos,sminos-suites-c,version-bump,shell-lint

and by hand, the door and the reader on a record nobody runs:

    export SMINOS_HOME="$(mktemp -d /tmp/sheet.XXXXXX)"
    cp -R sminos/types/sheet/fixtures/references/before/sheet "$SMINOS_HOME/"
    S=5eed0000-0000-4000-8000-000000000019
    sminos/skills/sminos/scripts/sminos sheet show --session "$S"
    printf '%s\n' '{"v":1,"key":"demo-0001","kind":"dismiss","id":"q1","by":"cli"}' \
      | sminos/skills/sminos/scripts/sminos sheet put --session "$S"

The last prints `{"session": "5eed0000-…", "results": [{"key":
"demo-0001", "state": "queued"}]}`, and `show` then no longer lists
`q1`. The test file ends `test_sheet_contract: N passed`; the generator
prints `sheet-contract: 21 cases, 6 examples, digest <sha256>`. After the merge,
M1's Progress line is completed with the merge commit, the sminos
version and that digest: the three things MAWS pins.

**M2.**

    python3 -B sminos/tests/test_sheet_step.py
    ci-gate --gates sminos,sminos-suites-c,sminos-idle

and by hand, a sheet with no engine:

    export SMINOS_HOME="$(mktemp -d /tmp/sheet.XXXXXX)"; S=5eed0000-0000-4000-8000-0000000000aa
    step() { sminos/skills/sminos/scripts/sminos sheet step --session "$S"; }
    echo '{"event":"start","runner":"terminal","start":{"source":"startup"}}' | step
    echo '{"event":"call","runner":"terminal","call":{"callId":"t1","asker":"main","entries":[{"question":"Ship today?","options":[{"label":"Yes"},{"label":"No"}]}]}}' | step
    sminos/skills/sminos/scripts/sminos sheet answer --session "$S" q1 --pick Yes --text "after the review"
    echo '{"event":"drain","runner":"terminal","acked":["t1"]}' | step

The call's `effects.result` is `Added q1.`; `answer` prints `queued`;
the drain's view holds one pending outcome for `q1` and one ready
envelope for `main` whose text names `q1`, `Yes` and the text; `show`
reads its key `accepted`. A `drain` ordered before the `start` answers
`no-record`.

**M3 to M6.**

    bash sminos/tests/mods/run.sh                                   # the mods' tests, validate, and test-sheet-step.sh
    tests/mods/typecheck.sh
    ci-gate --gates sminos-mods,mods-types,sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-idle

`run.sh` ends with the kit's own summary and no failure; `claude plugin
validate` prints no refusal for `sminos`.

**The live check** (M3 builds it, M4 to M6 add cases, M7 runs it whole).
It spends model calls (haiku), runs by hand on a Mac, starts each session
in a scratch `HOME` and `SMINOS_HOME` with the checkout's plugin
(`--plugin-dir sminos`), `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`,
`SMINOS_QUESTION_SHEET=1` and the stand-in surface, drives the terminal
through a pty as `T/pty_answer.py` does, and stops every process it
started. Its expectations are those of the engine C0 probed (2.1.331);
on an engine that answers a probe's question otherwise the case that
rests on it fails, and names the probe.

    python3 sminos/tests/mods/live-sheet-check.py                   # every case
    python3 sminos/tests/mods/live-sheet-check.py --case many       # one

| case | what it does and must observe | proves |
|---|---|---|
| `rendering` | sends one envelope by each route; reads it at `session.append` with its door and origin, and in the transcript | I9's evidence |
| `many` | asks for eight questions, one referencing a file; the result is `Added q1, q2, q3, q4, q5, q6, q7, q8.`; the line reads `8 open questions` and the stand-in's link; `show` lists eight and the file's text as captured, also after the file is edited (`changed`) | Acceptance 1 |
| `subset` | `put`s three answers as one call while a turn runs: one row of the transcript holds an envelope with three keys, the agent quotes the three, five remain; then three more while idle: a turn starts by itself and quotes them | Acceptance 2 |
| `max-send` | `put`s fifty answers of 20,000 characters each in one call: every envelope the model's requests hold is whole (the engine cut none to a head and a path), each text is there in full or by its head and a file that exists, every key lands, every envelope has at most 200 keys, and each but the last says more follows | I7's limits |
| `revise` | `show`, then has the agent revise `q2`; `answer q2 --pick 1` is refused and names `q2@2`; a line `put` with revision 1 prints `stale` with `current` 2; `answer q2@2 --pick 1` is applied to the new first option | Acceptance 3 |
| `note` | answers with a pick and a text; the agent repeats both | Acceptance 4 |
| `dismiss` | dismisses a question in an idle session: no turn starts within 20 s; after another answer the agent names the dismissal | Acceptance 5 |
| `stopped` | ends the session; `show` lists its questions; `answer` prints `queued`; `retract` takes one back; resumes; the first prompt's context carries the other with its two times; the project log has one `question` and one `answered` for it | Acceptance 6 |
| `subagent` | a subagent asks; `show` names it as asker; answered while it runs, the subagent's own transcript holds the envelope under its opening line and the main one does not; answered after it ended, the main conversation's does, naming it, and the subagent was not resumed | Acceptance 8 |
| `both` | one `put` answers the main agent's question and a running subagent's: each conversation holds an envelope with its own key only | G2 |
| `no-surface` | three starts: the setting off; on with no registration; on under `SSH_CONNECTION` with a `local` one: each has today's schema (`questions` in the tool's input) and the engine's dialog | Acceptance 9 |
| `nested` | a `claude -p` started with `MAWS_QUESTION_SHEET` set to another session's id (what a tool's child inherits inside a MAWS-run session): its tools hold no sheet schema, and its debug log says the variable did not match | G2; a real MAWS launch is C5's to observe |
| `secret` | references a `.env` the session's permissions deny, a path outside the working directories, and a file holding a token with the owner's secrets guard loaded (`--guard-plugin <dir>`, found at run time; without it that part is SKIP, never ok): the first two are refused, the result's `Not done:` naming each; the guard scrubs the third's Read rather than refusing it (observed at M3), so its stored body holds the guard's handle (§2.3: the guards' scrubbing reaches the caller); the token and the denied file's contents are nowhere under the sheet's files | Acceptance 15 |
| `withdraw` | the agent withdraws a question: `show` no longer lists it and the row reads `Withdrawn`; a subagent told to revise and to withdraw the main agent's question is refused both | Acceptance 16 |
| `compaction` | compacts, then asks the agent to list its open questions and their options without calling a tool: it names them | Acceptance 17 |
| `fork` | forks the session, by `/branch` and by `--fork-session`: `show` on each copy is empty, the copy's first context says so, and its next question's id is past every id the conversation holds | Acceptance 17 |
| `agent-open` | a subagent ends with a question open: the main agent's next tool result carries the notice | Acceptance 18 |
| `two-surfaces` | two `put`s answer one question: `applied`, then `closed`; then the stand-in is stopped, the agent asks again and its result ends with the no-surface sentence; the stand-in returns and `show` lists the question | Acceptance 19 |
| `import` | a session with two open asks of today's tool is resumed under the sheet: both are on the sheet, and are there once after two more resumes; with the transcript's search made to fail, nothing is imported and the next resume imports; a fork of such a session is empty after its own resume | G2 |

It ends `live-sheet-check: 19 passed` and exits 0; a failing case prints
`FAIL <case>: <what was observed>`.

**M7**, besides the live check:

    ci-gate                                                         # every gate the change's paths plan

then C1's two evals, each by the command its header gives, against the
shipped description; each must meet the threshold the composite's
Acceptance 14 then states.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

State, like Progress: each sentence of the composite, as it stands at
`277d8a520`, that this plan makes false or incomplete, with the
replacement proposed. Each entry gives a ruling on the second review its
exact shape, or names what a repair of this plan's own changed.

**What M1 freezes.**

1. §5.3, "`picks` holds labels in the terminal form and places (integers
   from 1) in the steer form". Proposed: "`picks` holds places (integers
   from 1 among the options of the answered revision) in both forms; in
   the terminal form's prose a picked label is cut at 200 characters,
   which can only shorten a label today's tool let through."
2. §5.3, "a batch that cannot fit alone is split across consecutive
   envelopes, each saying which part it is (`part`: the batch, n, of)",
   and §4.1, "it leaves in numbered parts (§5.3)". Proposed: "an envelope
   that does not carry everything now owed to its recipient says so, by
   `More follows.` at the end of its head line and `more` in its block;
   what it left stays pending and is packed later like anything else, and
   nothing of a packing is recorded." And in §4.1: "it leaves in more
   than one envelope, each but the last saying that more follows."
3. §5.3: a second limit. Proposed, beside the budget: "and at most 200
   keys, what one `delivered` line can name."
4. §5.3: the order of packing, which the idle route rests on. Proposed:
   "Batches that hold an answer that may start a turn are packed first,
   so a fresh answer is never behind an envelope that starts none."
5. §2.2, "Its first line has a fixed grammar (contract X7): the sentences
   …" and "When neither the call's step nor its settling (§3) gives an
   answer, the result says that what the call did is not yet known and
   will be told". Proposed: "The first line is one of three: the
   sentences; `Nothing done.`, which also answers a call that was
   foreclosed, with the reason on the next line; and `Outcome not known
   yet.`, for a call whose step and settling gave no answer, after which
   the outcome reaches the model as context. A reader of a stored call
   with that last line draws no ids for it and does not look for the
   later context."
6. §11, "The project log's events are written from the sheet's record
   …", and §3, "It holds, too, what the project log is owed". Proposed
   addition: "An event's source names the session and the question
   (`sheet:<session>:<id>`), since every session has a q1; and the record
   keeps, for each question, the project its `question` event went to,
   so its closing event goes there whatever project the session is in by
   then." The record's project is the one the session was in when the
   projection wrote the question, which follows the step that added it
   by a moment; resolving it inside the step would make every step read
   the registry.
7. §3, "It also keeps, for the directory's life, how each closed question
   closed (with its revision, header, first 200 characters and receipt
   …)". Proposed addition: "and, for the 32 questions answered last, the
   answer's line as the envelope words it (at most 2,000 characters),
   which the snapshot's answered asks are read from (§11)."
8. §4.2 and §3: where the inbox ends. Proposed, with §4.2's sentence on a
   drain: "A drain, like a reader, takes the inbox only through its last
   newline: what follows is a write that did not finish. The next writer
   starts on a new line, which makes that fragment a line of its own: not
   valid, it is skipped; a whole line that lacked only its newline is
   applied like any other."
9. §4.3 and X1, the reader's model. Proposed addition: "The model also
   carries how each closed question closed, with its receipt (a
   withdrawal never passed through the inbox), and, for a pending
   outcome, the question's text and option labels as the outcome's
   snapshot has them, cut at the input's bounds."
10. §5.4, "(built by C5, in the sminos plugin, from the view C2's step
    answers)". The step's view no longer holds a pending outcome's
    question. Proposed: "from the reader's model, asked for by key
    (`sminos sheet show --json --keys`)."
11. C2's Acceptance, G1, "an example of the envelope in its terminal form
    and in its steer form". Proposed: "examples of the envelope, each
    with the record it was composed from: the terminal form with its
    steer, a text carried by its file, an envelope that leaves more
    behind at 200 keys, an imported label, a subagent's"; and among the
    fixtures, a write that did not finish, before and after its resend,
    and stored calls for a foreclosed call and for one whose outcome was
    not known.
