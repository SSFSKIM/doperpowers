# Question sheet, C2 — the sheet in sminos: execution (2026-11-23)

> **Composite:** `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`
> in the MAWS repository, child **C2** (The sheet in sminos). **Parent pin:**
> MAWS commit `be9a8b749` (the composite with this plan's first entries
> folded in at `d5cdf48b8`, §5.2 reworded, C0's verdicts written in and
> §2.4 ruled on after). **Ticket:** MAWS board #867, a child of #600. The child's section in the composite ("###
> C2: The sheet in sminos") is its spec; the composite's §1 to §7, §8.3,
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
  repairs the rest. A narrower review of what M1 freezes follows it.
- [x] (2026-11-23) C0's verdicts for P1 to P5 (engine 2.1.331) written
  in where each decision stood ("What the probes settled").
- [ ] M1 — The contracts, published (G1). Blocked by: that narrower
  review.
- [ ] M2 — The record: the step, the lock, the command's other verbs.
  Blocked by: M1.
- [ ] M3 — Asking: the start choice, the sheet's schema, a call. Blocked
  by: M2.
- [ ] M4 — Delivering: the routes, landing, a start, subagents. Blocked
  by: M3.
- [ ] M5 — The terminal's drawing, and the import of today's asks. Blocked
  by: M3.
- [ ] M6 — The other readers, and the sheet's end of life. Blocked by: M4.
- [ ] M7 — The description, what is written beside the code, the
  acceptance (G2, G3). Blocked by: M5, M6; C1.
- [ ] The merges (M1's alone and first; the rest as its gates hold).

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
  sheet where no page runs yet (C4 builds the page).

## Verification

- This document: one buildability review, then a narrower one of what M1
  freezes ("What M1 freezes", below), before M1 is dispatched.
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
  writer (X1). Vectors a later milestone needs go under
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
| `state.json`: structure without the input's bounds; `calls`; `log`; `import`; an outcome's `textFile` and `part`; the verdict of a key never seen | I2 |
| the inbox line and its bounds; the door's exits and output | I3 |
| what a reader computes, and that it stops at the last newline whatever a probe says | I4 |
| the first line of a call's result | I6 |
| the envelope: its budget, a long text's file, the block's `textCut`, `textFile` and `part`, and the published examples | I7 |
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
`taken` (the mod itself sends it to that subagent), `acrossStop`, and
`part` once a step has split its batch (I7). `ready` and `in flight` are
the mod's memory; on disk both are "in `pending`". In a MAWS-run session
an outcome whose recipient is `main` is MAWS's to deliver and leaves on a
`delivered` line.

**A call**, by its call id, while the mod has no answer for it:

    ordered ──its step commits──► committed (its result is in `calls`) ──acked──► forgotten
       └──────settle finds no result──► foreclosed (in `calls`) ──acked──► forgotten

A foreclosed id commits nothing, whenever its step runs.

### Transitions

**The drain** is §4.2's table, in this order, over the lines from the
recorded offset to the end of the inbox (the lock excludes the door, so
the tail is whole):

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

5. The offset moves to the end of the tail.

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
| `call`, a call id whose staging directory is gone | — | nothing; `gone` (the mod acked it, or a `start` cleared it) |
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
After its event a step composes the ready envelopes (I7); the first time
a batch must be split it writes each outcome's `part`, in the same
replace.

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
| the door | inside its write | a last line without its newline, or (a batch that spans pages) some whole lines of the batch | the next appender starts on a new line; the drain skips the torn line; the surface's resend completes the batch (U6) |
| the door | after its write | a line the surface has no answer for | the resend carries a key the record knows: the first verdict again |
| a step | before its replace | a `.tmp-` file; for a call, its staged input still there | the next step removes the file; the mod orders `settle`, then decides |
| a step | after its replace, its answer lost | a record ahead of the mod's view; for a call, its result in `calls` | a drain, a `landed`, a `reroute` and a `start` are ordered again and set what they set before; a call is settled: the mod reads its recorded result and answers the model with it |
| a step | it runs late, after the mod gave up on it | for a call: an id that `settle` foreclosed, or one the mod acked | the late step finds the id in `calls`, or its staging gone, and commits nothing |
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
- U2 (taken) · A line that is not JSON, has no key, fails the line's
  schema, or picks a label the question does not have at an equal
  revision is skipped: no verdict, `inbox.skipped` raised by one, and the
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
  `multiSelect` without options, a line range out of order) is refused
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
      .staging/<session>/     what the mod hands a step: <callId>/entry-<n>.json, <callId>/ref-<n>-<m>, start-<nonce>/ask-<n>.json
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
| `S/sminos_sheet.py` | the door, the reader, the step with its composer, the projection, removal, the surfaces' liveness, the command's `sheet` verbs | M1, M2, M6 |
| `H/sheet-model.tsx` | what takes no `$`: the input's schema and validation, the block's parser, the result's parser, the notices, the lines of the row and of the band | M3 to M5 |
| `H/sheet.tsx` | the hooks and everything that takes `$` | M3 to M6 |
| `sminos/types/sheet/` | the published set | M1 |
| `sminos/types/sminos.d.ts` | `SheetKept` (I8) and the snapshot's `sheet` field (I13) | M3, M6 |

**The published set** (X1, X2, X3, X4, X7):

    sminos/types/sheet/
      README.md                      what each file is, and how the set is pinned
      MANIFEST.json                  { "v": 1, "files": { "<path>": "<sha256>" }, "digest": "<sha256>" }
      schema/state.schema.json       I2
      schema/inbox-line.schema.json  I3
      schema/show.schema.json        I4: what `sminos sheet show --json` prints
      schema/delivery.schema.json    I7: the <sheet-delivery> block, both forms
      schema/surface.schema.json     composite §7's file
      schema/tool-input.schema.json  composite §2.1 with §1's limits, without descriptions
      examples/envelope.terminal.txt        I7's first example
      examples/envelope.terminal.long.txt   a text carried by its head and its file
      examples/envelope.terminal.part-1.txt, part-2.txt   one Send split in two
      examples/envelope.steer.txt           I7's steer example
      examples/surface.json
      grammar/result.md              I6's grammar and the pattern a reader matches
      grammar/result.examples.json   stored calls: { "input", "result", "parsed" }
      fixtures/<case>/case.json      { "name", "covers", "session", "event", "verdicts" }
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
      "inbox": { "offset": 5321, "skipped": 0 },   // bytes applied; always at a line's start
      "questions": [ Question ],         // the open ones, by id ascending: the order asked
      "pending":   [ Outcome ],          // accepted, not delivered, in the order accepted
      "closed":    { "q3": Closed },     // every closed question, for the record's life
      "verdicts":  { "<key>": Verdict }, // every key's first verdict, for the record's life
      "calls":     [ { "callId": "…", "result": "…" } | { "callId": "…", "foreclosed": true } ],
      "log":       { "next": 18, "owed": [ { "n": 17, "kind": "question" | "answered", "src": "sheet:q7",
                                             "text": …, "choices": ["…"], "closed": "dismissed" } ] },
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
                "by": "page", "at": "<the line's>", "acceptedAt": "…", "batch": "…", "part": { "n": 1, "of": 2 },
                "recipient": "main" | { "agentId": "…" }, "taken": false, "acrossStop": false,
                "question": { "asker": …, "header": "…", "question": "…", "options": ["OAuth", "Passkeys"],
                              "multiSelect": true, "askedAt": "…" } }
              // textFile only for a text past 2,000 characters; part only once a step split the batch (I7)

    Closed  = { "how": "answered" | "dismissed" | "withdrawn", "at": "…", "revision": 2,
                "asker": …, "header": "…", "question": "<its first 200 characters>",
                "receipt": "OAuth, Passkeys", "key": "…", "deliveredAt": "…" }
              // receipt: the picks joined by ", ", else the text's first 80 characters; none for withdrawn

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
  options with one label, so a pick still names one option.
- **`calls`** holds the outcome of each call the mod has not yet
  acknowledged: its result text, or that `settle` foreclosed it. An entry
  leaves when the mod acknowledges that id, and all leave at a `start`.
  That horizon is enough because a call id is ordered only by the one
  hook dispatch that holds that call; it orders `call` and `settle` and
  nothing else for the id until it has an answer, and acknowledges only
  then; and a step of that id still on its way after the acknowledgement
  finds its staged input gone and commits nothing. A `start` is a new
  process, or a new session of the same one: no dispatch of the old
  conversation remains to order an old id.
- **`log.owed`** is what the project's log has not yet taken (I12). A
  reader ignores it.
- A question's order on a surface is its id's: a revise keeps the place.
  `askedAt` and `callId` are the current revision's, as §1 says.

### I3 · The inbox line, the door, the command

The line is §4.1's. The schema adds only bounds: `key` 8 to 128 of
`[A-Za-z0-9._:-]`; `text` at most 20,000 characters; `picks` at most 12;
`images` at most 8, each `uploads/<name>` with a name of `[A-Za-z0-9._-]`
ending in `png`, `jpg`, `jpeg`, `gif` or `webp`; a `delivered` line's
`keys` at most 200; a call of the door at most 50 lines. Required: `v`,
`key`, `kind`, `by`; with `answer`, `id`, `revision` and one of `picks`
and `text` non-empty; with `dismiss`, `id`; with `retract`, `target`; with
`delivered`, `keys`. The door fills `at` when absent and sets one `batch`
on the lines of a call of more than one line.

    sminos sheet put (<member> | --session <id>) [--no-wait]     lines on stdin, one JSON object each

The door, under the lock: the record must exist (else exit 3, `no sheet`);
every line must pass the schema, name images that exist under `uploads/`
as regular files, and, where it answers an open question at its current
revision, pick only that question's labels, one unless it is multi-select
(else exit 2, the reason on stderr, nothing appended: a call is appended
whole or not at all); a file that does not end in a newline gets one
first; then one `write` of all the lines, synced. After the lock: unless
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

    sminos sheet show    <who> [--json]                     the reader's model (I4), or its text
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

### I4 · What a reader computes

One rule for `sminos sheet show`, MAWS's reader and the page; `show
--json` prints it and the fixtures' `show.*.json` pin it.

1. Read `state.json`, then the inbox from `inbox.offset` to its last
   newline, then `state.json` again; if `seq` moved, start over (three
   times at most, then keep the last pair). A reader takes only what ends
   in a newline and reads the rest next time, on every filesystem and
   whatever a probe observed: C0's P4 saw no partial write on APFS, which
   is an observation and not a promise, and nothing published depends on
   it.
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

    show --json = { "v": 1, "session": "…", "seq": 41,
                    "open":   [ Question + { "handle": "q7@2",
                                             "queued": { "key", "kind": "answer", "picks", "text", "images", "revision", "by", "at" } } ],
                    "hidden": [ { "id": "q9", "key": "…" } ],            // open, with a queued dismissal
                    "sent":   [ { "key", "kind", "id", "state", "cancelled", …the Verdict's fields } ],
                    "pending": [ Outcome ] }

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
            "call":  { "callId": "toolu_…", "asker": "main" | { "agentId": "…", "name": "…" }, "floor": 11,
                       "entries": [ { "file": "<a staged entry>", "captures": [ Capture ] } | { "refused": "<I6's clause>" } ],
                       "withdraw": ["q3"] } }

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
                "ready":   [ { "recipient": "main" | { "agentId": "…" }, "keys": ["…"], "text": "<an envelope, I7>",
                               "wakes": true, "more": false } ],                                 // at most 4 recipients
                "surfaces": [ { "name", "url", "reach" } ] }                                     // alive at this step
    Effects = { "applied": ["<key>"],            // outcomes that joined `pending` in this step
                "accepted": [ { "id", "header", "question", "answer": "<I7's line after the id, at most 2,000 characters>" } ],
                                                 // the answers among them, for I13
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

**Everything that crosses is bounded.** Into the step: the event on stdin
names its large parts and holds none, so it stays in the tens of
kilobytes; an entry at every bound of the input's schema is under 1 MiB
as JSON (some 123,000 characters, at four bytes each or six as an
escape), and a captured text is at most the 256 KB Read itself returns.
Out of the step: the view leaves out options, descriptions, previews,
context, reference bodies and answer texts; it cuts what it keeps and
counts what it leaves out; and the step measures its answer before it
writes it: past 3 MiB it leaves out ready envelopes from the last
recipient back, then `closed` entries from the oldest, until it is
under, so the 4 MiB `$.process.run` returns is never reached. The mod
never needs more: it draws from `open` and `closed`, routes `ready`, and
the next view after a landing carries the next envelope. An event given inline (a shell, the suite, a fixture's
`case.json`) may hold its entries and asks in place of files; the mod
never does.

**A step never fails a session.** The mod reads `ok: false`, a process
that did not start, or output that is not JSON as "no answer". For a
drain, a `landed`, a `reroute` and a `start` it orders the event again at
the next trigger. For a call it orders `settle` for that id, at most
three times in the same dispatch: a recorded result is the call's answer
(the first step committed and its answer was lost); `foreclosed` lets the
mod tell the model the call changed nothing; and if `settle` too gives no
answer, the mod tells the model that what the call did is not yet known
and will be told to it, goes on settling at every trigger, and sends the
outcome as a notice (I9). Only once it holds one of these does it
acknowledge the id.

    sminos sheet probe --session <id> [--remote]     read-only, no lock; one JSON object
    { "record": true, "open": 3, "pending": 1, "queued": 0, "surfaces": [ { "name", "url", "reach" } ] }

### I6 · A call: its input, its refusals, its result (X7)

The input is §2.1's, validated by the mod (the engine does not check a
plugin tool's input). Two kinds of rule:

- **The whole call**: `schema/tool-input.schema.json`, and the two rules
  of the call no schema of those keywords states: at least one of `ask`
  and `withdraw` non-empty, and an id at most once across both. A call
  that breaks any is denied whole, in the words `ask.tsx`'s `formatted`
  uses for today's tool (`InputValidationError: AskUserQuestion failed
  due to the following issue…`, one line an issue), and reaches no step.
- **One entry** (U14): labels unique within the entry; `preview` only
  without `multiSelect`; `multiSelect` only with options; `lines` as `[a,
  b]` with `1 <= a <= b`; every reference captured. An entry that breaks
  one is refused alone: the mod hands the step its clause in the entry's
  place, and the others apply.

The result's first line:

    first-line = "Nothing done." / sentence *( " " sentence )
    sentence   = added / revised / withdrew              ; in this order, each at most once
    added      = "Added " item *( ", " item ) "."
    revised    = "Revised " ritem *( ", " ritem ) "."
    withdrew   = "Withdrew " id *( ", " id ) "."
    item       = id [ " (entry " n ")" ]
    ritem      = id " (" [ "entry " n ", " ] "revision " n ")"
    id         = "q" 1*DIGIT        n = 1*DIGIT

Ids stand in the order of the call's entries; `n` is an entry's place in
`ask`, from 1, and every `item` and `ritem` carries it exactly when some
entry or withdrawal of the call was refused. A second line, present then,
reads `Not done: ` and one clause per refusal, each closed by a period:

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

A reference's `<reason>` is the engine's own: the check's when it did not
allow the Read (a deny rule's, a guard's, or, for a path outside the
session's working directories, that permission was not granted: C0's P3
found the check answers `ask` there in every permission mode and opens
no dialog, so such a reference is always refused and the agent puts the
excerpt in `context`), and Read's when it failed (a missing file; a file
over 256 KB named without a range, whose reason tells the agent to name
one).

A last line, when the step's view names no surface alive whose reach suits
the session (I8): `No surface can show these questions right now; they
wait on the sheet and show when one returns.` The step writes the text;
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
    <sheet-delivery>{"v":1,"keys":["page-7f3a91c2","page-7f3a91c3","cli-20c41d07","page-7f3a91c4","page-7f3a91c5"],"answered":[{"id":"q7","revision":2,"picks":["OAuth","Passkeys"],"text":"passkeys only on mobile","images":["/Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e1/uploads/sketch.png"]},{"id":"q8","revision":1,"picks":[],"text":"Nothing waiting for you.","images":[]},{"id":"q12","revision":1,"picks":["Yes"],"text":"","images":[]}],"dismissed":["q9","q11"]}</sheet-delivery>

- The head reads `[sheet v1] The human dismissed questions on your sheet;
  no answer will come for them.` when the envelope answers nothing. An
  envelope sent to a subagent opens, above the head, with `From the human,
  through the question tool, not from your coordinator: answers to
  questions you put on the sheet.`: the engine frames a plugin's send as
  the coordinator's (C0's P2), as it does the bridge's `TELL_LINE`.
- An answer's line: the id; then, when the recipient is the main
  conversation and the asker a subagent, the asker in parentheses (`which
  has ended`, or `which could not be sent it` for one still running whose
  send was not delivered); then, when the outcome is owed across a stop,
  its times in the machine's local time; then the question as a JSON
  string, cut at 200 characters with `…`; then `→` and the picks joined
  by `, ` with a period, and `Their text: ` with the text as a JSON string
  (`→ their text: ` when nothing was picked). One `[Image source:
  <absolute path>]` line follows per image, the engine's own form for a
  picture known by its file.
- The block is the last line: compact JSON, its keys in the order shown,
  with `<`, `>`, `&`, U+2028 and U+2029 written as `\u` escapes, so
  neither the closing tag nor a system-reminder tag (the one thing the
  engine escapes inside a context: C0's P5) occurs inside, and the block
  is one line. `keys` holds the answered outcomes' keys in the order of
  `answered`, then the dismissed ones' in the order of `dismissed`: as
  many keys as the two lists have entries.
- A reader reads the block and nothing above it.

**The budget** (the composite's §5.3 rule, in exact shapes). The engine
hands the model one context entry whole only up to 100,000 of its
characters.

- An envelope is at most **60,000** UTF-16 code units, the larger of the
  ways to count a string, so it is under the engine's cut however the
  engine counts, with room for a notice above it and the engine's own
  wrapper.
- A text longer than **2,000** characters has a file, `texts/<sha256>.txt`,
  from the moment its answer is accepted.
- The block's `text` is the text's first **500** characters, with
  `"textCut": true` when the text is longer and `"textFile": "<absolute
  path>"` when it has a file. So no text is in an envelope twice in full.
- The step composes a recipient's next envelope from that recipient's
  pending outcomes in the order accepted, batch by batch (an outcome
  with no `batch` is a batch of one):
  1. The first batch, every text in full in the prose. If it fits,
     following batches join it, each whole and in full, while the
     envelope still fits; the first that does not waits for the next
     envelope.
  2. If the first batch does not fit, its longest text that has a file
     is carried by its head and its file instead (`→ their text, 18,214
     characters, is in <absolute path> and begins: "<its first 500
     characters>…"`), then the next longest, until it fits.
  3. If it still does not fit, the batch is split: the envelope takes its
     outcomes in order while they fit, and the rest follow in the next
     envelopes. Each outcome's `part` is written to the record then, so
     later envelopes number themselves the same. A part's head ends
     `(part 1 of 2 of one Send; the rest follows)`, the last one's
     `(part 2 of 2 of one Send)`, and its block carries `"part": {
     "batch": "…", "n": 1, "of": 2 }`.
  One outcome always fits alone: at every bound of the line and of the
  question it is under 40,000 units.
- A route carries one envelope each time it opens; what remains leaves
  with the next opening.

A text carried by its file, and a Send split in two, as published:

    [sheet v1] The human answered questions on your sheet.
    q14 "Paste the error you see." → their text, 18,214 characters, is in /Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e2/texts/3f0c9a51d2e84b6f7a10c5d9e8b7a6f4c3d2e1f00112233445566778899aabbc.txt and begins: "Traceback (most recent call last):\n  File \"app.py\", line 12, in <module>…"
    <sheet-delivery>{"v":1,"keys":["page-88a0b1d4"],"answered":[{"id":"q14","revision":1,"picks":[],"text":"Traceback (most recent call last):\n  File \"app.py\", line 12, in <module>","textCut":true,"textFile":"/Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e2/texts/3f0c9a51d2e84b6f7a10c5d9e8b7a6f4c3d2e1f00112233445566778899aabbc.txt","images":[]}],"dismissed":[]}</sheet-delivery>

    [sheet v1] The human answered questions on your sheet (part 1 of 2 of one Send; the rest follows).
    q20 "Which regions first?" → EU, US.
    <sheet-delivery>{"v":1,"keys":["page-a1000001"],"answered":[{"id":"q20","revision":1,"picks":["EU","US"],"text":"","images":[]}],"dismissed":[],"part":{"batch":"b-5c1e77a0","n":1,"of":2}}</sheet-delivery>

    [sheet v1] The human answered questions on your sheet (part 2 of 2 of one Send).
    q21 "Who signs off?" → their text: "Dana, after the audit."
    Dismissed: q22.
    <sheet-delivery>{"v":1,"keys":["page-a1000002","page-a1000003"],"answered":[{"id":"q21","revision":1,"picks":[],"text":"Dana, after the audit.","images":[]}],"dismissed":["q22"],"part":{"batch":"b-5c1e77a0","n":2,"of":2}}</sheet-delivery>

(The published `long` example's block holds the text's first 500
characters; it is shortened here. The published split is of a Send whose
answers do not fit one envelope; these two show the form.)

The steer form (§5.4) is C5's to send, under the same budget and with the
same block; in it `picks` holds places, integers from 1, where the
terminal form holds labels. The set publishes this example, the same
outcomes as the first one above:

    [sheet v1] The human answered questions on your sheet.
    q7 → option 1, option 2. Their text: "passkeys only on mobile"
    q8 → their text: "Nothing waiting for you."
    q12 → option 1.
    Dismissed: q9, q11.
    <sheet-delivery>{"v":1,"keys":["page-7f3a91c2","page-7f3a91c3","cli-20c41d07","page-7f3a91c4","page-7f3a91c5"],"answered":[{"id":"q7","revision":2,"picks":[1,2],"text":"passkeys only on mobile","images":["/Users/me/.claude/sminos/sheet/5eed0000-0000-4000-8000-0000000000e1/uploads/sketch.png"]},{"id":"q8","revision":1,"picks":[],"text":"Nothing waiting for you.","images":[]},{"id":"q12","revision":1,"picks":[1],"text":"","images":[]}],"dismissed":["q9","q11"]}</sheet-delivery>

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
across a stop) and whether more is pending behind it. An envelope is
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
and a step's view and `probe` are what it reads.

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
| a question added (an import included) | `{ "kind": "question", "src": "sheet:<id>", "text": [<question>], "choices": [<labels>] }`; a revise owes nothing |
| an answer applied | `{ "kind": "answered", "src": "sheet:<id>", "text": <I7's line after the id> }` |
| a dismissal applied | `{ "kind": "answered", "src": "sheet:<id>", "text": "dismissed", "closed": "dismissed" }` |
| a withdrawal | `…, "text": "withdrawn", "closed": "withdrawn"` |

**The projection**, `sminos sheet log --session <id>` (M6): under the
lock it reads `log.owed`; outside it, it appends those events for the
session's writer through `append_host`, which adds `from` and `to` and
whose `(kind, src)` rule appends nothing twice; under the lock again it
removes from `log.owed` the numbers it wrote and replaces `state.json`.
The mod orders it, not awaited, after a step whose effects say something
is owed; the Stop hook's `sminos record` runs it for a session that has a
record; removal runs it first and then appends, for each question still
open, `…, "text": "removed with its sheet", "closed": "removed"`. A
session in no project keeps what it is owed until it has one or the
record goes. `close_questions` in `S/sminos.py` passes over a `src` that
starts `sheet:`: a sheet question outlives its process.

### I13 · The snapshot (§11)

In a session whose choice is the sheet, `H/sheet.tsx` writes the `ask`
key that `ask.tsx` writes elsewhere, still `shape: 2`, so doperpowers'
appeal and reload read it unchanged:

- `asks` holds the sheet's answered questions in the shape appeal's
  evidence reader already takes (`hooks/mods/appeal.tsx`, `evidence`: it
  reads `questions[].question` and `answer` of each ask whose `status` is
  `answered`): one ask a question, `{ id: "sheet:<id>", questions: [{
  question, header, options: [], multiSelect: false }], status:
  "answered", answer }`, `answer` being I7's line after the id, from the
  step's `effects.accepted`. The 32 answered last are kept; a reloaded
  module takes them up from the kept snapshot. A dismissal is no answer
  and adds none.
- `undelivered: []`, `isDialogUp: false` (the sheet raises no dialog),
  `isTurnRunning`, and `answered` raised by the answers each step's
  effects name.
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
  | `closed-withdrawn` | row 3: an answer and a dismissal for a withdrawn question |
  | `dismiss-applied` | row 4 |
  | `retract-queued` | row 5: a retract after its target (`cancelled` before the step), and an edit (a retract and a new answer) |
  | `retract-too-late` | row 6: the target applied by an earlier step; another refused as stale |
  | `retract-unseen` | U1: a retract whose target no line carried; after it the target's own verdict, `kind: "unseen"`, and its entry in `sent` |
  | `retract-unseen-late` | U1, from the state above: the target's line arrives and is set aside, the verdict unchanged, its question still open; a second retract of the same target reads `too-late` |
  | `delivered-mixed` | row 7: one key pending, one delivered before, one unknown |
  | `resent-key` | row 8 |
  | `resent-then-retract` | a resent copy of an applied line, then a retract of it |
  | `batch` | one Send of three lines, two answers and a dismissal, a main recipient and a running subagent's (`taken`) |
  | `long-text` | an answer of 18,214 characters: its outcome's `textFile` and the file under `texts/` |
  | `stopped-queue` | event `start`: a queued answer, a queued dismissal (the question hidden), a queued answer retracted; after it, outcomes owed across a stop |
  | `imported-legacy` | event `start` carrying an ask valid only under today's tool: a 2,001-character question, a 201-character label, a preview on a multi-select question; after it the three as questions with `importedFrom`, unchanged |
  | `skipped-and-unknown` | U2, U3 |
  | `references` | a text reference with lines, one without, an image; their bodies under `refs/` |

  `grammar/result.examples.json` holds: a call that added eight; one that
  added, revised and withdrew; one that partly succeeded with an added
  and a revised entry and a refused one (the composite's own example);
  one whose entry was refused for two options with one label; one with a
  refused withdrawal only (`Nothing done.`).
- The envelope's examples are I7's, whole and concrete: no key, entry or
  path is elided, and each terminal example's `answered` and `dismissed`
  name exactly the questions its prose does.
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
its prose names and no others, is at most 60,000 UTF-16 units, holds no
text past 500 characters in its block, and the two parts name one batch
and number themselves 1 and 2 of 2; `state.schema.json` accepts the
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
envelopes it composes for the examples' records are the published texts.

**Touches.** `S/sminos_sheet.py`; `S/sminos.py` (the parser's other
verbs); `T/test_sheet_step.py` (new), `T/sheet-vectors/` (new: vectors
for the events the published set does not carry: `call`, `settle`,
`landed`, `reroute`, the acknowledgement, the `agents` rule, a split),
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
  today's tool held it, whatever its length), and its ids are recorded
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
  answers a step in under 3 MiB, and `probe` in under 4 KiB;
- the composer: a batch of fifty answers of 20,000 characters leaves in
  envelopes none over the budget, each text whole or carried by head and
  file, no text twice in full, the parts numbered and recorded; two
  batches that fit together leave together, two that do not leave apart;
  the context cut and stopped at its budget;
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
  since a capture is slow and a step is not; stage what passed; read the
  running agents when the caller or the view has a subagent; order
  `call`; raise one `$.ui.notify` for a call that added something (its
  first added question, `(+N more)`), as today's tool announces an ask;
  answer the step's `result`. With no answer from the step the mod
  settles (I5) and then answers one of: the recorded result; `The sheet
  could not be written (<why>); nothing changed. Call again.`; or `The
  sheet did not answer, so what this call did is not known yet. Do not
  repeat it: you will be told.`
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
- The description the tool is registered under until M7 (§2.4 as the
  owner ruled it; C1's baseline compares this wording with "put every
  question you have in one call", and M7 takes the one it reports):

      Puts questions to the human on this session's question sheet and returns at once; nothing waits on them. The human answers any of them, in any order, when they get to it, and each answer reaches you later in a message that names its question by id.

      Ask when a question comes up, not at the end of your turn, and put every question you have at that moment in the one call (`ask` takes up to 20 entries); then go on with work that does not depend on the answers. To change a question you already asked, send an entry with its `id`: it replaces the question in place. Do not ask a second question that overrides the first. To take a question back, name it in `withdraw`.

      The human sees only the card. Put in `context` what they need to judge the question, name in `references` the files it is about (each is shown as it is now; a file outside your working directories cannot be shown, so quote what matters from it in `context`), and mark an option `recommended` when you have a recommendation. Options are optional: a question without them is answered in text, and every question has a text field.

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
  foreclosed, the model told nothing changed, and that step run late
  commits nothing; `settle` unanswered three times: the third sentence,
  then the notice once a later settle answers;
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
conversation. A Send larger than an envelope arrives whole, in parts or
by its files.

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

**Does not touch.** MAWS's steer and the context the tool adds to one
(C5). The band's count of answers that will go with the next message
(M5).

**Proves.** Acceptance 2, 4, 5, 6's resume, 8, 17, 18, and G2's line on
one Send that answers the main agent's question and a running
subagent's. Tests pin:
- each row of I9's table; an envelope that does not wake opens no idle
  route and leaves with the next that opens; an outcome owed across a
  stop and a fresh answer, before any prompt, leave together on the
  fresh answer's idle turn (§5.2); a view adopted inside a `tool.call`
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
  added or revised, `q7 Auth method — <the question's first sentence>`;
  then, where a view knows the question, the receipt in the line's
  place: `q7 Auth method → OAuth`, `q7 Auth method · Dismissed`, `·
  Withdrawn`, and `· Revised below` when the question's revision is past
  the one this call set. A withdrawal the call made draws `q2 ·
  Withdrawn`. A session with no record (a fork, a record removed), and a
  question older than the 500 a view's `closed` holds, draw the lines
  without receipts.
- A read is definite when the whole file was read, or the search ran and
  its output was not cut. Indefinite, the `start` event says so, nothing
  is imported or recorded, and the next start reads again. A fork's first
  start under the sheet sends no asks: the step records `import.never`.
  Each ask is staged as a file of its own.
- An imported ask's own row stays as `ask.tsx` draws a stored call.

**Does not touch.** Today's band and rows in a session whose choice is
'today'.

**Proves.** Acceptance 1's line, 16's row, the receipts of §8.3, and
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

**Interfaces.** Exposes I12's projection, I13. Consumes `log.owed` and
`effects.accepted`.

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
answer; a projection run twice appends nothing; a projection that fails
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
thresholds; if the owner ruled for automatic capture of context (§10),
it is built and passes with it; the manuals say what the plugin now
does; G2 and G3 hold as the composite words them, run as written.

**Touches.** `H/sheet-model.tsx` (the description and the properties'
descriptions); `H/README.md` (a section "sheet" beside "ask"),
`H/CLAUDE.md`, `S/CLAUDE.md`, `sminos/CLAUDE.md`, `sminos/README.md`,
`sminos/hooks/hooks.json` (its description), `SKILL.md`; the version;
`docs/doperpowers/TECH-DEBT.md` (the limits accepted: U6, U8, U13; the
reload's double delivery; an answer to a subagent's question reaching
the main conversation as well across a process death; a captured file
attached to the model's context after a compaction; a rewind after a
delivery).

**Decisions.**

- The description is the wording C1's baseline reports of the two it
  compares (§2.4), tested with C1's two evals as C1 merged them under
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
prints `sheet-contract: 19 cases, digest <sha256>`. After the merge,
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
| `max-send` | `put`s fifty answers of 20,000 characters each in one call: every envelope the model's requests hold is whole (the engine cut none to a head and a path), each text is there in full or by its head and a file that exists, every key lands, and the parts are numbered | I7's budget |
| `revise` | `show`, then has the agent revise `q2`; `answer q2 --pick 1` is refused and names `q2@2`; a line `put` with revision 1 prints `stale` with `current` 2; `answer q2@2 --pick 1` is applied to the new first option | Acceptance 3 |
| `note` | answers with a pick and a text; the agent repeats both | Acceptance 4 |
| `dismiss` | dismisses a question in an idle session: no turn starts within 20 s; after another answer the agent names the dismissal | Acceptance 5 |
| `stopped` | ends the session; `show` lists its questions; `answer` prints `queued`; `retract` takes one back; resumes; the first prompt's context carries the other with its two times; the project log has one `question` and one `answered` for it | Acceptance 6 |
| `subagent` | a subagent asks; `show` names it as asker; answered while it runs, the subagent's own transcript holds the envelope under its opening line and the main one does not; answered after it ended, the main conversation's does, naming it, and the subagent was not resumed | Acceptance 8 |
| `both` | one `put` answers the main agent's question and a running subagent's: each conversation holds an envelope with its own key only | G2 |
| `no-surface` | three starts: the setting off; on with no registration; on under `SSH_CONNECTION` with a `local` one: each has today's schema (`questions` in the tool's input) and the engine's dialog | Acceptance 9 |
| `nested` | a `claude -p` started with `MAWS_QUESTION_SHEET` set to another session's id (what a tool's child inherits inside a MAWS-run session): its tools hold no sheet schema, and its debug log says the variable did not match | G2; a real MAWS launch is C5's to observe |
| `secret` | references a `.env` the session's permissions deny, and one the owner's secrets guard (devcloud's) denies: the result's `Not done:` names each; nothing of either is in the staging or under `refs/` | Acceptance 15 |
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
`be9a8b749`, that this plan makes false or incomplete, with the
replacement proposed. A binding sentence stands until its writer rules;
the rulings already given on the buildability review are cited where an
entry only gives them their exact shape.

**What M1 freezes** (X1, X3; settle these before the set is published).

1. §5.3, the envelope: it states no bound. By the writer's ruling on the
   review's first finding, in the shapes of I7. Proposed, after "it does
   not repeat what is still open": "An envelope is at most 60,000 UTF-16
   code units, under the 100,000 characters past which the engine hands
   the model only a head and a path. A text longer than 2,000 characters
   is kept as a file in the record (`texts/<sha256>.txt`) from the moment
   it is accepted. A human's text stands in the prose in full while the
   envelope fits; when it does not, the longest texts that have a file
   are carried, one by one, as their first 500 characters and the file's
   absolute path. The block's `text` is at most the first 500 characters,
   with `textCut` when the text is longer and `textFile` when it has a
   file, so no text is in an envelope twice in full. Distinct batches
   share an envelope only while they fit; a batch that cannot fit alone
   is split across consecutive envelopes, each saying which part it is
   (`part`: the batch, n, of)." And in §3's directory: `texts/`.
2. §4.1, "(The one exception is a writer killed inside its single write
   …)". A second exception, by the same ruling: "and a Send too large for
   one envelope, which leaves in numbered parts (§5.3)."
3. §3, "and the results of the last 64 calls by call id, so a call
   ordered twice answers the same result." Proposed: "and, for each call
   the mod has not yet acknowledged, its outcome: its result, or that it
   was foreclosed. Before the tool tells the model a call failed it
   settles that call id under the lock, which answers a result already
   committed or forecloses the id, so a step of it that runs late commits
   nothing; the mod then acknowledges the id, and its staged input and
   its outcome go together. A start forgets them all." Why this horizon
   is enough is I2's.
4. §2.2: a result the composite does not have. When neither the call's
   step nor its settling gives an answer, the tool's result says that
   what the call did is not yet known and will be told, and the outcome
   follows as a line of context. Proposed: one sentence saying so.
5. §3, "`state.json` holds the open questions with every field of §1",
   and §9, "those asks are imported once as sheet questions". By the
   ruling on the third finding. Proposed, in §1: "The lengths, the twelve
   options and the rule on previews are rules of the tool's input,
   checked at the call; the record's schema states structure and not
   these bounds." And in §9: "each kept as it was asked, marked as
   imported, also where today's tool allowed what the sheet's input does
   not; a later revise of it is a call under the input's rules."
6. §3, "`state.json` holds …", and "**One writer.** `state.json` changes
   only on the tool's order, and each change is one *step*". By the
   ruling on the fourth finding, the file also holds what the project's
   log is owed, added in the same replace as the change that owes it; and
   one other operation rewrites the file, under the same lock: the log's
   projection, which removes what it has written to the log and changes
   nothing else. Proposed: both, as two sentences; and in §11, after "are
   written from the sheet's record": "which keeps each until the log has
   it."
7. §4.2, the row "retract with target K | the record has never seen K".
   Its verdict column needs the target's shape, which no line supplies:
   proposed, "`retracted` for the retract; for K a verdict of its own,
   kind `unseen`, naming the retract and no question, which stands when
   K's line arrives; a second retract of K reads `too-late`." And §4.3:
   a queued answer or dismissal that a queued retract names reads
   `queued` and `cancelled`.
8. §3, "A stored reference holds, beside §2.3's fields, its absolute
   path, its kind and media type, its byte count and whether Read cut
   it." Read cuts nothing (P3). Proposed: "… its byte count and, for a
   text, Read's start line, line count and the file's total lines." What
   is kept is `result.file.content`, the field a guard's hook rewrites.
9. C2's Acceptance, G1: the fixture list and the examples. Added: a
   retract of a key never seen and the late arrival of its line; an
   answer whose text has a file; an import valid only under today's
   tool; an envelope carrying a text by its file, and a Send in two
   parts. Proposed: name them.

**Delivery.**

10. §5.2, "For the tool a delivery is known when it sees, stored in the
    main conversation, a row one of its own routes wrote that carries the
    envelope's keys". Proposed addition: "It tells such a row by what the
    engine says of it, its door and its origin, read once the row is
    stored; a flight still unsettled when its turn ends is settled there
    against the conversation the model holds. Where the engine says
    nothing of a row's author, its form decides: a text quoting a whole
    envelope with keys still pending could only be written by a process
    that can read the record, which §8.2 already trusts."
11. §5.2, "For a subagent it is known when the engine has queued the
    send (§6)." Proposed: "when the send answers that it was delivered";
    a send that answers otherwise, or rejects, goes to the main
    conversation.
12. §6 (or §5.1), by the ruling on the sixth finding. Proposed: "Across a
    process death an answer to a subagent's question may reach the main
    conversation as well: a send the engine delivered just before the
    process died is owed again at the next start, and the subagent is
    gone."
13. §5.2, "a prompt the plugin submits when the session is idle", and
    "Outcomes accepted together go in one envelope." Two details P1 and
    the budget add: the prompt is submitted from outside every hook's
    dispatch (inside a `tool.call` hook the host refuses it); and a route
    carries one envelope each time it opens, the rest leaving with the
    next opening.
14. §5.5: the context has the envelope's budget (I10 cuts each question
    and label, then stops the list and names what is left); and a fork's
    context states the next id only when the conversation could be read
    by then, which over the wire it cannot (P5): the floor then reaches
    the record with the first call.

**The call and the command.**

15. §1, "Option labels are unique within a question, checked at add and
    at revise as today's tool checks them". Today's tool refuses the
    whole call; under §2.1 this is one entry's own fault. Proposed:
    "checked at add and at revise; an entry that breaks it is refused
    alone", and the same for a preview on a multi-select question,
    `multiSelect` without options and a line range out of order (U14).
16. §8.3, "`answer`, `dismiss` and `retract` append a line". By the
    ruling on the tenth finding. Proposed: "`answer` names the question
    with the revision the human saw, `q7` or `q7@2`: a bare id is taken
    only while the question is at revision 1, and at a higher one the
    command refuses and says to show it again; numbered picks are places
    in the named revision."
17. §3, "The tool drains the inbox at session start, …". Proposed
    addition: "Only a session's start makes its record: a drain ordered
    before it changes nothing."
18. §3: nothing says a lock file is never removed. Proposed, with the
    sweep's sentence: "The lock file beside a record is left when the
    record goes: unlinking it would let two holders in."

**The other readers.**

19. §11, "The snapshot keeps its shape and gains one optional field for
    the sheet, so its readers need no change." True for the counter; the
    appeal's judge reads the human's answers from the snapshot's answered
    asks. Proposed: "… and carries the sheet's answered questions as
    answered asks in today's shape, so the appeal's judge reads them."

**Still open from before.**

20. U8: two processes holding one session id lose no update and may both
    deliver. Not in the composite; proposed as one sentence of §3's "One
    writer".
21. C2's Edges and Status: C0's verdicts are in, so nothing of G2 waits
    on a probe; M1 waits on the narrower review of what it freezes.
