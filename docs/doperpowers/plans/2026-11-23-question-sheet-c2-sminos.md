# Question sheet, C2 — the sheet in sminos: execution (2026-11-23)

> **Composite:** `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`
> in the MAWS repository, child **C2** (The sheet in sminos). **Parent pin:**
> MAWS commit `ad4427f93`. **Ticket:** MAWS board #867, a child of #600. The
> child's section in the composite ("### C2: The sheet in sminos") is its
> spec; the composite's §1 to §7, §8.3, §9's import and §11 are its design,
> binding where the composite's "Grades" paragraph says; X1, X2, X3 (the
> block's schema and the terminal form), X4 (the schema), X6 and X7 are the
> contracts it owns. This document carries the constraints, the state
> machine, the interfaces and the milestones, and nothing of the design.
> Written against doperpowers `b43da6bcd` (sminos 1.56.0) and the engine's
> hook declarations of Claude Code 2.1.323
> (`sminos/.claude-plugin/types/claude-code/index.d.ts`, laid by the engine;
> the installed engine was 2.1.331). Read before M1: the composite whole;
> `sminos/hooks/mods/README.md`, its sections "ask" and "Developing";
> `sminos/hooks/mods/CLAUDE.md`, its first paragraph and the paragraph on
> lane B; `docs/doperpowers/specs/2026-10-13-ask-async-design.md`, "How the
> engine is reached".

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
back; after the resume the answer rides the first prompt, marked with its
age. Everything else in use today is as it was: with the setting off, or
no surface to answer on, the session has today's tool. How to see each of
these is Concrete Steps; what closes the child is its three gates in the
composite (G1, G2, G3), mapped to milestones under Plan of Work.

## Progress

- [x] (2026-11-23) This plan written against the composite at `ad4427f93`
  and doperpowers `b43da6bcd`.
- [ ] The plan's buildability review (Verification).
- [ ] M1 — The contracts, published (G1). Blocked by: nothing.
- [ ] M2 — The record: the step, the lock, the command's other verbs.
  Blocked by: M1.
- [ ] M3 — Asking: the start choice, the sheet's schema, a call. Blocked
  by: M2; C0's P3.
- [ ] M4 — Delivering: the routes, the envelope, a start, subagents.
  Blocked by: M3; C0's P2 (in a terminal) and P5.
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
- **The step** is the one operation that changes a record's
  `state.json`: `sminos sheet step` (I5). The mod orders it and nothing else calls it; it is the
  tool's hand on the file. **An event** is what a step is ordered to do
  (I5's list).
- **The door** is `sminos sheet put` (X2): the one operation that appends
  to a record's inbox.
- **A drain** is the part of every step that applies the inbox lines not
  yet applied (composite §4.2).
- **The view** is what a step answers the mod: the record cut to what the
  mod draws and delivers from (I5).
- **A route** is one way an envelope reaches the main conversation in a
  terminal session (I9): **idle** (a prompt the mod submits), **result**
  (context on the model's next tool result), **prompt** (context on the
  next prompt that enters). **A flight** is one envelope on a route, from
  the moment the mod hands it over until it lands or fails.
- **Landing** is the evidence that a conversation holds an envelope (I9).
- **Owed across a stop** describes an outcome that was pending when a
  process started, or was applied by that start's drain.
- **The published set** is `sminos/types/sheet/` as M1 merges it (I1).
- **The stand-in surface** is `sminos/tests/sheet_surface.py`, which
  writes and heartbeats a surface registration so a session offers the
  sheet where no page runs yet (C4 builds the page).

## Verification

- This document: one buildability review before M1 is dispatched.
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
  write is refused past 4 MiB. A question with previews and
  context can pass 100 KiB, so a record can pass what one read takes. This
  is why the record is read and written by the command, on the mod's
  order (K1), and why the mod never reads `state.json` itself.
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

- K1 · **One step, in the command.** Every change of `state.json` is one
  step: a read-modify-write of the file under the record's lock, run by
  the command on the mod's order, ending in an atomic replace. The mod
  holds no authoritative copy; it keeps the last view. The alternative, a
  mod that holds the sheet in memory and writes it through `$.fs`, cannot
  replace atomically, cannot share the door's lock, and loses an update
  when two processes hold one session id; it lost.
- K2 · **The published set is frozen at M1.** After M1 merges,
  `sminos/types/sheet/` changes only on a ruling of the composite's
  writer (X1). Vectors a later milestone needs go under
  `sminos/tests/sheet-vectors/`.
- K3 · **Today's tool is not edited beyond its yield** (M3), two exports
  (M4) and the definiteness of its transcript read (M5). Its behaviour in a session
  whose choice is not the sheet is unchanged, and `ask.test.ts` passes
  unedited but for cases those two changes add.
- K4 · **How a drain is triggered** (advisory in the composite, settled
  here). A drain is a step with no event of its own. The mod orders one:
  at each session start; when the door tells the bridge (`sheet`, I3);
  when its bridge's child says hello; when a subagent stops; and when a
  check finds the inbox longer than the view's offset. The check is one
  `$.fs.stat` of `inbox.jsonl`, made at every `tool.call`, `prompt.submit`
  and `turn.complete` the mod's hooks see and on a timer every 5 s
  (`$.clock.every`). The timer is there because a nudge can be lost (the
  bridge off by its seat rule, its child restarting) and an idle session
  dispatches no hook. Drains are single-flight: one runs, at most one
  more is remembered. Only the tool's own call and the nudge's answer
  wait for a step.
- K5 · **Counting characters.** Every "at most N characters" of the
  composite counts Unicode code points, the same in Python (`len`) and in
  the mod (`[...text].length`).
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

## The state machine

Fixed here before any milestone builds it. The composite gives the apply
table (§4.2) and the delivery rules (§5); this section adds who acts, the
complete event list, the states, the transitions the composite's table
does not carry, and the points at which a change is durable and visible.
I2 to I9 give the shapes these tables name.

### Who acts, and on which file

| actor | process | what it may change |
|---|---|---|
| the mod | the session's engine process (one per session; U8 for two) | nothing in a record: it orders steps, holds the view, the flights and the turn's state in memory, and writes a step's event and a call's captured bodies to the staging directory (I1) |
| a step | `sminos sheet step`, started by the mod, short-lived | `state.json`, `refs/` |
| the door | `sminos sheet put`, started by a surface or by the command's `answer`, `dismiss`, `retract`; any number at once | `inbox.jsonl`, by appending |
| a surface | the page's server, MAWS, the command line | `uploads/` (before the door names a file), its own registration |
| a reader | `sminos sheet show`, MAWS's reader, the page | nothing; it takes no lock |
| removal | `sminos sheet remove`, the daemon's sweep | deletes a whole record |

A step, the door and removal hold the record's lock (I1) for all they do
to the record. A reader holds none and follows I4's rule.

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
| E9 | a flight failed | the mod (a route's refusal) | nothing: the outcomes are held again, in memory |
| E10 | a subagent that is a recipient is not running, or a send to it was refused | the mod | the `agents` every step carries, or step `reroute` |
| E11 | a process starts a session (`startup`, `resume`, `fork`, the session after a `/clear`) | the classic SessionStart | step `start` |
| E12 | a compaction | the classic SessionStart, source `compact` | a drain; then I10's context |
| E13 | the module reloads | `session.start` with a kept choice | a drain, for a view |
| E14 | a subagent stops | the classic SubagentStop | a drain; a notice for the main conversation, in memory (I9) |
| E15 | `/clear` leaves a session | `session.end`, reason `clear` | removal of that session's record |
| E16 | a stopped session's record is removed | `sminos sheet remove`, the sweep | removal |

Every step drains first, whatever its event (§3: a call drains before it
applies its own entries; the same order for every event keeps one path).

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

A key's first verdict is final (§4.2's last row).

**A pending outcome**:

    held ──a route opens──► in flight ──lands──► gone from `pending`
      ▲                        │
      └────── fails ───────────┘

with three attributes a step sets: `recipient` (`main`, or a running
subagent), `taken` (the mod itself sends it to that subagent), and
`acrossStop`. `held` and `in flight` are the mod's memory; on disk both
are "in `pending`". In a MAWS-run session an outcome whose recipient is
`main` is MAWS's to deliver and leaves on a `delivered` line.

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
   | a key with a verdict | none | the retract `too-late` |
   | a retract or `delivered` line | none | the retract `too-late` |
   | a key the record has never seen (U1) | K is never applied, should it arrive | K `retracted`, the retract `retracted` |

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
`acrossStop` is true when the step's event is `start`.

**A step's own event**, after the drain:

| event | precondition | effect |
|---|---|---|
| `call`, an entry without `id` | fewer than 500 open (U7); every reference captured | a question `open(1)`, id `q<nextId>`, `nextId` + 1 |
| `call`, an entry with `id` | the id is open; the caller asked it; every reference captured | the entry replaces the question; revision + 1 |
| `call`, a `withdraw` id | the id is open; the caller asked it, or the caller is the main conversation | → withdrawn |
| `call`, any of the above refused | — | nothing for that entry; the reason joins the result (I6) |
| `call`, a `callId` the record has answered | — | nothing; the recorded result again |
| `landed`, keys | — | each key in `pending` leaves it; `closed[id].deliveredAt` |
| `reroute`, keys | — | each such outcome: `recipient: main`, `taken: false` |
| `start` | — | every pending outcome: `acrossStop: true`, `recipient: main`, `taken: false`; a new record takes its id floor and, for a fork, `import.never`; today's asks the event carries are imported (M2's rule) |
| any, with `agents` | — | a pending outcome whose recipient is not in `agents.running`: `recipient: main`, `taken: false` |

Entries apply in the call's order, then the withdrawals; an id occurs at
most once in a call (§2.1), so the order among them decides nothing.

### Where a change becomes durable and visible

| change | durable when | a reader then sees |
|---|---|---|
| a surface's act (E4 to E7) | the door's one `write` of the line or batch has returned and been synced | the line as queued |
| a verdict with all it causes (the question closing, the outcome pending, the offset) | the step's replace of `state.json`: one file, so all of it or none | accepted or refused; the question gone from the open list |
| an add, a revise, a withdrawal | the step's replace, which precedes the call's result | the question listed, changed, gone |
| a reference's body | written before the replace that names it | the reference with its body |
| a delivery | the replace of the `landed` step, which follows landing | delivered |
| the start choice (X6) | `$.state`, for the process | nothing |

The replace is the linearization point of every change of the sheet. The
mod acts on a change (opens a route, draws, tells the bridge's caller a
verdict) only from the view a step answered, so only after the replace.
Nothing the mod holds is durable: the view, the flights, the notices and
the turn's state are rebuilt from the record and the engine at a start.

### A process that dies between two steps

| who dies | where | what is left | what restores it |
|---|---|---|---|
| the door | before its write | nothing | the surface sends again, with the same keys |
| the door | inside its write | a last line without its newline, or (a batch that spans pages) some whole lines of the batch | the next appender starts on a new line; the drain skips the torn line; the surface's resend completes the batch (U6) |
| the door | after its write | a line the surface has no answer for | the resend carries a key the record knows: the first verdict again |
| a step | before its replace | a `.tmp-` file | the next step removes it; the mod orders the event again |
| a step | after its replace | a record ahead of the mod's view | the mod orders the event again: every event is idempotent (`call` by `callId`, the others by what they set) |
| the engine | after a call's step, before the model read its result | a question whose id the model never read | I10's context at the next start names it |
| the engine | an outcome held | the outcome in `pending` | the next start: owed across a stop |
| the engine | a flight in the air, or landed and the `landed` step not yet made | the outcome in `pending`; its row in the transcript or not | the next start searches the transcript for the envelope's keys (I9): found, `landed`; not found, owed across a stop |
| the module (a reload) | anywhere | flights and notices forgotten; `pending` whole | the new module drains and holds what is pending again. Landing is taken from evidence, never from the flight's bookkeeping, so a flight of the old module that lands is still taken as landed. A reload that falls between handing an envelope over and its landing can deliver it twice: today's limit, kept (`sminos/hooks/mods/README.md`, "ask", Known limits) |
| a nudge | lost on the way | a queued line | the timer's check (K4) |

### Cases the composite leaves undefined

Each is decided here once, in the composite's spirit, and listed again for
its writer in the last section.

- U1 · A retract whose target the record has never seen cancels it in
  advance: both keys read `retracted`, and the target is set aside if it
  arrives. A remote copy can deliver a retract before its target, and the
  human's last word was to take the answer back.
- U2 · A line that is not JSON, has no key, fails the line's schema, or
  picks a label the question does not have at an equal revision is
  skipped: no verdict, `inbox.skipped` raised by one, and the step's
  effects say so for the mod's debug log. The door refuses each of these
  it can see, so such a line did not come through the door.
- U3 · An answer or dismissal naming an id the record never assigned
  reads `closed` with `how: "unknown"`.
- U4 · A call in which nothing was done answers `Nothing done.` as its
  first line (I6), so a reader of the stored call always finds a first
  line of the grammar.
- U5 · A withdrawal makes no pending outcome and no delivery: the caller
  knows what it withdrew. A running subagent whose question the main
  conversation withdrew is not told; nothing waits on a sheet question.
- U6 · A door killed inside its one `write` can leave part of a batch.
  The surface's resend completes it under the same keys, and the parts
  may then reach the agent in two envelopes. The line's shape has no
  count that would let a drain hold back an incomplete batch (the last
  section proposes none: the window is one system call).
- U7 · A sheet holds at most 500 open questions; an add past that is
  refused with the reason. Like §1's twelve options it guards against a
  runaway call, and it bounds the view a step answers under the 4 MiB a
  process's output is cut at.
- U8 · Two processes holding one session id (a session resumed in two
  terminals) both order steps; the lock serializes them and no update is
  lost, but each delivers what it finds pending, so an answer can reach
  both. Not supported, and not made worse than today's.
- U9 · A headless process MAWS did not launch (a one-shot `claude -p`,
  with or without `--resume`) never takes the sheet, also when its
  session has one: it ends before any answer and may run beside the
  session's own process. The sheet waits for the next interactive or
  MAWS-run start.
- U10 · A `/clear` drops what was pending with the record: the
  conversation the answers were for is gone.
- U11 · What is owed across a stop rides the first prompt that enters,
  whoever submitted it (the human, a peer's message, a schedule): today's
  rule for a held answer, and none of these is a turn the tool started.
- U12 · `sminos sheet answer`, `dismiss` and `retract` refuse a session
  acting on its own sheet (`CLAUDE_CODE_SESSION_ID` naming the target):
  an agent does not answer its own questions. Another session's sheet it
  may write, as `sminos answer` answers another session today. The door
  itself refuses nobody: a daemon started from a session's shell inherits
  that variable and must still serve that session's page (§8.2 leaves a
  same-user process its trust).

## Interfaces and Dependencies

Paths are from the repository's root. `S/` is
`sminos/skills/sminos/scripts/`, `H/` is `sminos/hooks/mods/`, `T/` is
`sminos/tests/`.

### I1 · Files

    $SMINOS_HOME/sheet/
      <session>/              the record (composite §3): state.json, inbox.jsonl, refs/, uploads/
      <session>.lock          the record's lock: an empty file, flock'd exclusively
      .staging/<session>/     what the mod hands a step: its event, a call's captured bodies
      surfaces/<name>.json    a surface's registration (X4)

The lock sits beside the record and not in it, so removing a record never
removes a lock another process waits on; a waiter that gets the lock looks
for the record again. It is `fcntl.flock`, waited for at most 10 s, after
which the door exits 75 and a step answers `busy`. [PD1]

The staging directory is the one place the mod writes, with `$.fs.write`:
a file a step is given, which the step deletes once it has read it, with
any file there older than a day. No reader looks in it.

In the plugin:

| path | holds | from |
|---|---|---|
| `S/sminos_sheet.py` | the door, the reader, the step, removal, the surfaces' liveness, the command's `sheet` verbs | M1, M2 |
| `H/sheet-model.tsx` | what takes no `$`: the input's schema and validation, the envelope's text and its parser, the result's parser, the contexts, the lines of the row and of the band | M3 to M5 |
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
      examples/envelope.terminal.txt, examples/envelope.steer.txt, examples/surface.json
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
      "calls":     [ { "callId": "…", "result": "…" } ],   // the last 64 calls' results (idempotence)
      "import":    { "never": true, "calls": { "<today's call id>": ["q1", "q2"] } }
    }

    Question = §1's fields, and:
      "asker": "main" | { "agentId": "…", "name": "…" }
      "references": [ Reference ]
      "importedFrom": { "callId": "…", "index": 0 }          // only for an imported ask's question

    Reference = { "path": "<as the agent gave it>", "lines": [40, 80], "abs": "<resolved at capture>",
                  "sha256": "…", "bytes": 1234, "kind": "text" | "image", "mediaType": "image/png",
                  "size": 5678, "mtimeMs": 1763900000000, "cut": true }
                // sha256 and bytes are of refs/<sha256>; size and mtimeMs the file's at capture;
                // cut: Read's default cut what a reference without lines returned

    Outcome = { "key": "…", "kind": "answer" | "dismiss", "id": "q7", "revision": 2,
                "picks": ["OAuth"], "text": "…", "images": ["uploads/a.png"],
                "by": "page", "at": "<the line's>", "acceptedAt": "…", "batch": "…",
                "recipient": "main" | { "agentId": "…" }, "taken": false, "acrossStop": false,
                "question": { "asker": …, "header": "…", "question": "…", "options": ["OAuth", "Passkeys"],
                              "multiSelect": true, "askedAt": "…" } }

    Closed  = { "how": "answered" | "dismissed" | "withdrawn", "at": "…", "revision": 2,
                "asker": …, "header": "…", "question": "<its first 200 characters>",
                "receipt": "OAuth, Passkeys", "key": "…", "deliveredAt": "…" }
              // receipt: the picks joined by ", ", else the text's first 80 characters; none for withdrawn

    Verdict = { "verdict": "applied" | "stale" | "closed" | "retracted" | "too-late",
                "kind": "answer" | "dismiss" | "retract" | "delivered", "at": "…", "id": "q7",
                "current": 3, "how": "answered" | "dismissed" | "withdrawn" | "unknown", "target": "…" }
              // current with stale; how with closed; target with a retract's

A question's order on a surface is its id's: a revise keeps the place.
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
choice is not the sheet. It is no control: an observer (a MAWS-run
session's bridge) answers it, so it joins `OPS` and stays out of
`CONTROL_OPS` in `H/bridge.tsx`.

The other verbs (M2), each taking `<member>`, resolved as the control
verbs resolve one, or `--session <id>`, which reads no registry:

    sminos sheet show    <who> [--json]                     the reader's model (I4), or its text
    sminos sheet answer  <who> <qid> [--pick <label|n>]... [--text <t>] [--image <file>]...
    sminos sheet dismiss <who> <qid>...                     one call of the door: one batch
    sminos sheet retract <who> <key>
    sminos sheet remove  <who>                              a stopped session's record (refused while it runs)
    sminos sheet surfaces [--json]                          the registrations, with which are alive
    sminos sheet step    --session <id>                     the tool's own (I5); in no usage text

`answer` builds one line (`by: "cli"`, a key of its own, the question's
current revision), copies each `--image` into `uploads/` first, and calls
the door; `dismiss` and `retract` likewise. U12 binds these three.

X2's open point, C2's side of it: MAWS reaches the writer by running the
command. Nothing is served over the daemon's socket by this child.

### I4 · What a reader computes

One rule for `sminos sheet show`, MAWS's reader and the page; `show
--json` prints it and the fixtures' `show.*.json` pin it.

1. Read `state.json`, then the inbox from `inbox.offset` to its last
   newline, then `state.json` again; if `seq` moved, start over (three
   times at most, then keep the last pair).
2. From the tail drop what is not valid, and every line whose key has a
   verdict or occurred earlier in the tail. A retract whose target is
   among what remains removes both; any other retract is dropped. What
   remains of `answer` and `dismiss` is **queued**.
3. A question with a queued dismissal is not listed (§3). A question
   with a queued answer is listed carrying the first such line.
4. Every key the reader knows has one state: `queued` (step 2);
   `accepted` (its outcome is in `pending`); `delivered` (verdict
   `applied`, not in `pending`); else its verdict.
5. A reference reads `changed: true` when the file at `abs` is missing or
   its size or modification time differs from the record's; `null` where
   the reader is not on the session's machine.

    show --json = { "v": 1, "session": "…", "seq": 41,
                    "open":   [ Question + { "queued": { "key", "kind": "answer", "picks", "text", "images", "revision", "by", "at" } } ],
                    "hidden": [ { "id": "q9", "key": "…" } ],            // open, with a queued dismissal
                    "sent":   [ { "key", "kind", "id", "state", …the Verdict's fields } ],
                    "pending": [ Outcome ] }

### I5 · The step

    sminos sheet step --session <id> [--event <file>]     one JSON object in (the file, else stdin), one on stdout

    in  = { "event": "drain" | "start" | "call" | "landed" | "reroute",
            "runner": "terminal" | "maws",
            "remote": false,                     // the session is under SSH_CONNECTION: only a surface of reach `remote` suits it
            "agents": { "running": ["<agentId>"], "direct": true },
            "keys": ["…"],                       // drain: the verdicts wanted; landed, reroute: the outcomes
            "start": { "source": "startup" | "resume" | "fork" | "clear", "floor": 11,
                       "today": { "definite": true, "asks": [ { "callId": "…", "questions": [ … ] } ] } },
            "call":  { "callId": "toolu_…", "asker": "main" | { "agentId": "…", "name": "…" },
                       "entries": [ Entry + { "captures": [ Capture ] } ], "withdraw": ["q3"] } }

    Capture = { "ok": true, "abs": "…", "kind": "text", "file": "<a staging file: the body as text>", "size": 5678, "mtimeMs": 1763900000000, "cut": false }
            | { "ok": true, "abs": "…", "kind": "image", "file": "<a staging file: the bytes in base64>", "mediaType": "image/png", "size": …, "mtimeMs": … }
            | { "ok": false, "reason": "permission denied" }

    out = { "ok": true, "seq": 42, "view": View, "effects": Effects }
        | { "ok": false, "code": "busy" | "bad-event", "error": "…" }

    View    = { "seq", "offset",
                "open":    [ { "id", "revision", "asker", "header", "question", "labels": ["…"], "multiSelect", "askedAt" } ],
                "pending": [ Outcome, its images made absolute, + "local": { "askedAt": "2026-11-23 14:02", "at": "2026-11-23 16:40" } ],
                "closed":  { "q3": { "how", "revision", "header", "receipt" } },
                "surfaces": [ { "name", "url", "reach" } ] }           // the registrations alive at this step
    Effects = { "applied": ["<key>"],            // outcomes that joined `pending` in this step
                "skipped": 0,                    // lines this drain skipped (U2)
                "answers": 2,                    // answer lines applied in this step (I13's count)
                "verdicts": { "<key>": Verdict },                       // for `keys`
                "result": "<the call's result text, I6>",
                "start": { "empty": "fork" | "lost" | null, "nextId": 12, "before": ["<key>"],     // before: pending ahead of this step's drain
                           "imported": [ { "callId": "…", "ids": ["q1"] } ] } }

In order: take the lock; load the record (none: an empty one, and for
`start` its floor); drain; apply the event; write each new `refs/<sha256>`
from its staging file (the bytes: a text's UTF-8, an image's decoded);
replace `state.json`
(a `.tmp-` file in the record, synced, then `os.replace`) when anything
changed; release the lock; from M6, project the log (I12); answer. The
view leaves out descriptions, previews, context and reference bodies, so
with U7 it stays well under what `$.process.run` returns (4 MiB of
stdout). A step never fails a session: the mod reads `ok: false`, a
process that did not start, or output that is not JSON as "not done",
orders it again at the next trigger, and for a call answers the model
that the sheet could not be written and why.

The mod hands every event as a staging file (`--event`); stdin is for a
shell and the suite. A call's event can pass 2 MiB at the schema's bounds
(twenty entries with twelve previews each), and a captured body is what
Read returned, up to its own bound: each travels as a file of its own,
under the 4 MiB one `$.fs.write` takes, and never through a pipe whose
bound the engine's declarations do not state. A body `$.fs.write` refuses
for its size refuses its entry (`the reference <path> could not be read:
larger than a sheet keeps`).

### I6 · A call: its input, its refusals, its result (X7)

The input is §2.1's, validated by the mod against
`schema/tool-input.schema.json` (the engine does not check a plugin
tool's input) plus the rules a schema of those keywords cannot say: at
least one of `ask` and `withdraw` non-empty; an id at most once across
both; labels unique within an entry; `preview` only without
`multiSelect`; `multiSelect` only with options; `lines` as `[a, b]` with
`1 <= a <= b`. A call that breaks any is denied whole, in the words
`ask.tsx`'s `formatted` uses for today's tool (`InputValidationError:
AskUserQuestion failed due to the following issue…`, one line an issue),
and reaches no step.

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
    entry <n>, <id> is not open (<how> at <HH:MM>)             how: answered, dismissed, withdrawn, never asked
    entry <n>, <id> was asked by <the main conversation | the subagent <name>>; only its asker revises it
    entry <n>, the sheet holds 500 open questions
    <id> is not open (<how> at <HH:MM>)
    <id> was asked by <…>; only its asker or the main conversation withdraws it

A last line, when the step's view names no surface alive whose reach suits
the session (I8): `No surface can show these questions right now; they
wait on the sheet and show when one returns.` The step writes the text;
`H/sheet-model.tsx` and MAWS parse the first line.

### I7 · The envelope (X3)

The terminal form, one envelope a recipient:

    [sheet v1] The human answered questions on your sheet.
    q7 "Which auth method should the login use?" → OAuth, Passkeys. Their text: "passkeys only on mobile"
    [Image source: /Users/me/.claude/sminos/sheet/<session>/uploads/a.png]
    q8 (asked 2026-11-23 14:02, answered 2026-11-23 16:40, while this session was stopped) "…" → their text: "…"
    q12 (from the subagent reviewer, a1b2c3, which has ended) "…" → Yes.
    Dismissed: q9, q11.
    <sheet-delivery>{"v":1,"keys":["…"],"answered":[{"id":"q7","revision":2,"picks":["OAuth","Passkeys"],"text":"…","images":["/Users/…/a.png"]}],"dismissed":["q9","q11"]}</sheet-delivery>

- The head reads `[sheet v1] The human dismissed questions on your sheet;
  no answer will come for them.` when the envelope answers nothing.
- An answer's line: the id; then, when the recipient is the main
  conversation and the asker a subagent, the asker in parentheses; then,
  when the outcome is owed across a stop, its times in the machine's local
  time; then the question as a JSON string, cut at 200 characters with
  `…`; then `→` and the picks joined by `, ` with a period, and `Their
  text: ` with the text as a JSON string (`→ their text: ` when nothing
  was picked). One `[Image source: <absolute path>]` line follows per
  image, the engine's own form for a picture known by its file.
- The block is the last line: compact JSON, its keys in the order shown,
  with `<`, `>`, `&`, U+2028 and U+2029 written as `\u` escapes, so the
  closing tag occurs nowhere inside and the block is one line. `keys`
  holds the answered outcomes' keys in the order of `answered`, then the
  dismissed ones' in the order of `dismissed`.
- A reader reads the block and nothing above it.

The steer form (§5.4) is C5's to send; the set publishes the block's
schema for both (`picks` holds labels in the terminal form and places,
integers from 1, in the steer form) and this example:

    [sheet v1] The human answered questions on your sheet.
    q7 → option 1, option 2. Their text: "passkeys only on mobile"
    q8 → their text: "…"
    Dismissed: q9, q11.
    <sheet-delivery>{"v":1,"keys":["…"],"answered":[{"id":"q7","revision":2,"picks":[1,2],"text":"…","images":["/Users/…/a.png"]}],"dismissed":["q9","q11"]}</sheet-delivery>

### I8 · The start choice (X6), and surfaces (X4)

Made at a process's first `session.start` and kept:

    SheetKept = { shape: 1, choice: 'sheet' | 'today' | 'none', runner?: 'terminal' | 'maws',
                  session: string, left?: string }            // $.state, { plugin: 'sminos', key: 'sheet' }

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

- **The proof for MAWS** (§7 leaves its form to C2 and C5): MAWS sets
  `MAWS_QUESTION_SHEET` to the launch's session id, which it knows for
  every launch (`--session-id` for a new session and a fork, the resumed
  id otherwise: `buildLaunch` in MAWS's `src/engine-host/launch.ts`). The
  tool takes the variable as proof only when it equals the id of the
  session this process starts. The proof is in hand at once, needs no
  bridge and no registry record, and a `claude` a tool starts inside the
  session inherits the variable under another id. The bridge's parent
  check lost: it can read `unresolved` for a minute at a start, the very
  moment the schema is fixed. A variable that is set and does not match
  is ignored, with a debug line saying so.
- `SMINOS_QUESTION_SHEET` is on for `1`, `true`, `on`, `yes` and off for
  `0`, `false`, `off`, `no`, in any case; unset is the default, one
  constant in `H/sheet-model.tsx` that C7 changes.
- A surface is alive when its `heartbeatAt` is at most 30 s old and its
  `pid` is a running process (`S/sminos_sheet.py`, which `surfaces`
  prints and every step's view carries). Its reach suits a session unless
  `SSH_CONNECTION` is set there and its reach is `local`.
- What the choice costs a session that does not take the sheet: with no
  record and the setting off, two `$.env.get` and one `$.fs.exists`, and
  no process.
- 'sheet': the mod tells `ask.tsx` to yield (I11), registers the tool
  under the sheet's schema and description, withdraws the built-in
  (deferred, and a model's call of it denied with `Withdrawn in this
  session: ask through mcp__sminos__AskUserQuestion, which puts your
  questions on the session's sheet.`), and orders `start` at the classic
  SessionStart. 'today' and 'none': the sheet's hooks pass everything
  on, and `ask.tsx` does what it does in such a session today; only a
  stored call of the sheet's form is still drawn by the sheet (M5).

### I9 · Delivery in a terminal session

`H/sheet.tsx` holds, in memory: the view; the flights; the notices; and
whether a main turn runs (`turn.start` and `turn.complete` without an
`agentId`, as `ask.tsx` tracks it). **Held** is the view's pending
outcomes whose recipient is `main` and that are in no flight, with the
notices. An outcome **wakes** when it is an answer and not owed across a
stop.

| trigger | condition | route |
|---|---|---|
| a step's view arrives with outcomes newly pending | no main turn runs, and something held wakes | idle: `$.prompt.submit`, not awaited |
| a main turn completes with reason `answer` | something held wakes | idle |
| a `tool.call` of the model's main loop returns, not denied, not aborted | anything is held | result: `context` on that result |
| a prompt enters (`prompt.submit`, any origin but the mod's own) | anything is held | prompt: `context` on that prompt |

A route takes everything held in one synchronous step, as one envelope (a
notice goes above the envelope's head as a line of its own, and alone
when nothing else is held, on the result and prompt routes only: a notice
starts no turn). A dismissal and an outcome owed across a stop never open
the idle route; they ride whichever opens (§5.2, U11).

A flight **fails** when its route refuses: the submit resolves `drop` or
rejects; the prompt beneath resolves `drop` or throws. Its outcomes are
held again, ahead of any accepted since, with today's toast. A flight
**lands** when the mod sees, at `session.append`, a row of the main
conversation that one of its own routes writes (a hook's context, or a
prompt under this plugin's framing: the two kinds `ask.tsx`'s
`deliveryTexts` reads from a stored row, exported for the start's search)
carrying a block whose `keys` it then hands to a `landed` step. Landing is read from the row and never from the flight, so
it also holds for a row a module before a reload sent. A human's own
prompt that quotes an envelope is no such row, and neither is MAWS's
steer: in a MAWS-run session only a `delivered` line moves an outcome
(§5.4). At a `start` whose effects name outcomes pending before its
drain (`start.before`), the mod searches the transcript for `<sheet-delivery>` (the one `perl` pass
of `ask.tsx`'s `searchArgs`, with this one form) and hands the keys it
finds in rows of those two kinds to `landed` before it composes anything;
a search that fails lands nothing, and the outcomes go again, owed across
a stop. [PD5 for the rendering a hook reads]

**To a subagent** (§6): an outcome with `taken: true` goes by
`$.session.send({ to: { agentId }, text })`, one envelope an agent, not
awaited inside a hook. The send resolving is its landing (the engine has
queued it; the subagent reads it at its next tool round); the send
rejecting orders `reroute`. The mod reads `$.agent.list()` before every
step it orders while the view holds a question or an outcome of a
subagent, and passes those `running`; an agent that ended since its
outcome was taken is rerouted by the step's `agents` rule. `direct` is
one constant a runner: true for both. [PD3, PD4]

**A subagent that stops with questions open** (E14): the mod makes a
notice, `[sheet v1] The subagent <name> (<agentId>) ended with questions
still open on your sheet: q4 "…", q6 "…". Their answers will come to you;
withdraw what you no longer need.`, each question as in I7. A notice is
not kept: a start's context (I10) names every open question and its
asker.

**In a MAWS-run session** the mod opens none of the four routes; it
drains, sends to running subagents, and takes `delivered` lines. The
context §5.4 has the tool add to a steer that carries an ended subagent's
answer is C5's to build on P1's verdict; the view holds what it needs.

### I10 · What the tool supplies at a start (§5.5)

Returned as the classic SessionStart's `additionalContext` [PD5], after
the `start` step (a drain, for `compact`):

    [sheet v1] Your question sheet, after <a resume | a compaction>.
    Open: q7 (revision 2) "Auth method" — "Which auth method should the login use?" Options: 1. OAuth; 2. Passkeys; 3. Magic link.
    Open: q8 (revision 1), asked by the subagent reviewer (a1b2c3) — "…" No options: answered in text.
    Answered, the answer not yet delivered to you: q9 (revision 1) — "…" Options: 1. Yes; 2. No.
    New ids continue from q12.

Nothing when the sheet has no open question and nothing pending, but for
these, each one line with the same last sentence:

- a fork: `[sheet v1] This conversation is a copy: its question sheet
  starts empty. Questions asked before the copy belong to the conversation
  it was copied from, and their answers will not come here; ask again
  what you still need. New ids start at q12.`
- a record that was lost (a `resume` whose conversation holds stored
  calls of the sheet and whose record is absent): `[sheet v1] The question
  sheet's record was not found, so the sheet starts empty; questions asked
  earlier are no longer open. New ids start at q12.`
- an import (M5): `Moved onto the sheet from the earlier question tool:
  q1 "…" (call <id>, question 1), …`

**The floor** of a new record in a conversation that already used ids
(§3): the highest `q<n>` the mod finds in the conversation it holds: in
the tool's stored results, in envelopes' blocks, and in the `New ids …
from q<n>` sentence above, which is why every context states it. For a
`resume` the mod searches the transcript for those forms; for a `fork`,
whose transcript is unwritten, it reads `$.session.messages()` in both
forms, as `ask.tsx`'s `historyAsks` does. A module cannot learn which
session a fork copied (`ask.tsx`, `historyAsks`), so the parent's record
is not read.

### I11 · The mod's layout

`H/register.tsx` registers, in order: the bridge, the backtick guard,
`registerSheetBand`, `registerAskBand`, `registerSheet`, `registerAsk`,
the address, the name. The sheet's hooks are registered before the ask's
of the same event, so they are the outer ones: a hook of the sheet's
handles what is the sheet's and passes the rest on with `next`.

`H/ask.tsx` gains one switch, `yieldAsk()`, which the sheet's
`session.start` hook calls before its `next` when the choice is the
sheet. Yielded, every hook of `ask.tsx` passes its event on untouched,
with two exceptions: its row hooks still draw a stored call of today's
form (its input has `questions`; §2.1), and its SessionStart hook still
reads a resumed transcript's asks, which it hands to the sheet in place
of adopting them (M5). The switch is the module's own variable, so a
reload starts unyielded and the kept choice sets it again.

`H/sheet.tsx` exports, for `H/bridge.tsx`'s `sheet` op, `sheetNudge(keys):
Promise<Answer>`, which reaches the engine through the closure the
sheet's `session.start` made (`$` crosses no import: Constraints).

A stored call's form is told by its input: `ask` or `withdraw` is the
sheet's, `questions` today's. The sheet's row hook draws the first in
every session, whatever the choice, from the call's input and result
alone, with the view's `closed` for the receipts where a view exists.

### I12 · The project log (§11)

The log is a projection of the record, made by `S/sminos_sheet.py` from
`state.json` and the inbox, never read out of the transcript: a
subagent's call and an answer accepted while the session was stopped are
in no main transcript. For the session's writer, through `append_host`
(whose `(kind, src)` rule makes it idempotent):

| the record | the event |
|---|---|
| a question, open or closed | `{ "kind": "question", "to": "host", "src": "sheet:<id>", "text": [<question>], "choices": [<labels>] }`, as first projected; a revise appends nothing |
| a key with verdict `applied`, kind `answer` | `{ "kind": "answered", "src": "sheet:<id>", "text": <I7's line after the id, from the inbox line> }` |
| the same, kind `dismiss` | `{ "kind": "answered", "src": "sheet:<id>", "text": "dismissed", "closed": "dismissed" }` |
| `closed`, `how: "withdrawn"` | `…, "text": "withdrawn", "closed": "withdrawn"` |
| a record removed with the question open | `…, "text": "removed with its sheet", "closed": "removed"` |

It runs after a step that changed a question or a verdict (outside the
lock, its failure logged and never the step's), from the Stop hook's
`sminos record` for a session that has a record, and before a removal.
`close_questions` in `S/sminos.py` passes over a `src` that starts
`sheet:`: a sheet question outlives its process.

### I13 · The snapshot (§11)

In a session whose choice is the sheet, `H/sheet.tsx` writes the `ask`
key that `ask.tsx` writes elsewhere, still `shape: 2`, so doperpowers'
appeal and reload read it unchanged: `asks: []`, `undelivered: []`,
`isDialogUp: false` (the sheet raises no dialog), `isTurnRunning`,
`answered` raised by each step's `effects.answers`, and one field more:

    sheet?: { open: { id: string, revision: number, header?: string, question: string, asker: string }[], owed: number }

`asker` is `main` or the agent's id; `owed` counts `pending`.

## Decisions a probe's verdict can change

Written against the composite's stated design; each is corrected here,
and the places named follow.

| id | probe | the decision as written | what a contrary verdict changes | where |
|---|---|---|---|---|
| PD1 | P4 | The lock is `fcntl.flock` on `sheet/<session>.lock`; the replace is `os.replace` of a synced temporary file, made by the command. P4 as the composite words it asks about "the tool's" replace: under K1 that is the command's, and a hook's `$.fs.write` is not used. | Another lock, or another replace, in the door and the step. Nothing in the tables. | I1, I5; M1, M2 |
| PD2 | P3 | A reference is captured in the tool's hook: `$.tool.check` for a Read of the path, and only on `allow` a `$.tool.call` of Read with the range. The body kept is the text Read returned; `cut` when Read's default bound cut it; an image is kept as its bytes. A check that is not `allow`, a Read that errors, and a result that is the engine's "unchanged since read" stub each refuse the entry with the reason. | Guards that do not run on a plugin's Read: capture is refused outright, every reference an entry's refusal. A stub: the verdict's way around it, or the refusal stays. A Read that changes what the model is taken to have read: the same choice. The image's returned shape: `Capture`'s image arm. | I5 (`Capture`), I6; M3 |
| PD3 | P2, terminal | A running subagent gets its answers by `$.session.send`; the send resolving is the landing; an ended one is never sent to. | No direct route: `direct` false for the runner, every subagent's outcome goes to the main conversation naming the asker. A later proof of reading: the landing moves to it. | I9; M4 |
| PD4 | P2, MAWS-run | `direct` is true in a MAWS-run session too. | False: the step gives every such outcome to `main`, and MAWS steers it (C5). One constant. | I9; M4 |
| PD5 | P5 | I10's context is the classic SessionStart's `additionalContext`, for `resume`, `compact` and `fork`. A hook's context reaches the model, and a `session.append` hook, with `<sheet-delivery>` as written. | A source whose context does not arrive: for that source the same text rides the first prompt that enters, as hook context. A rendering that escapes the tag: I9's reader matches the escaped form too, and X3's readers are told. | I9, I10; M4 |

P1 decides nothing here (I9's last paragraph).

## Plan of Work

Seven milestones. M1 is the composite's G1 and is small on purpose: the
MAWS app (C3) waits on exactly what it publishes. M2 to M5 are G2, with
M6's log; M6 and M7 are G3. What blocks each is in Progress; a milestone
blocked by a probe is written against the composite's design, and the
table above says what its verdict can move.

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
`show`), I4, I6's grammar with its examples, I7's schema with both
examples, the surface's schema. Consumes nothing.

**Decisions.**

- The fixtures are written by the generator, by hand from §4.2 and this
  document's tables, and never computed by an implementation: the house
  rule of `T/dx4-jobs.gen.py`. The set is the contract the step (M2) and
  MAWS's reader are both held to, not the output of either. The generator
  is deterministic (session ids `5eed0000-0000-4000-8000-0000000000NN`,
  NN the case's place in the table below from 01; fixed times, fixed
  keys); the suite runs it into a scratch directory
  and compares bytes with the committed set.
- The cases, each a `before`, the one event that takes it to `after`
  (a `drain` unless said), the verdict each key ends with, and both
  `show` outputs:

  | case | covers |
  |---|---|
  | `empty` | a new record |
  | `answer-applied` | §4.2 row 1; a pick with text; an image |
  | `answer-stale` | row 2: an answer to revision 1 of a question at revision 2 |
  | `two-surfaces` | rows 1 and 3: two answers to one question in one tail, from `page` and `cli` |
  | `closed-withdrawn` | row 3: an answer and a dismissal for a withdrawn question |
  | `dismiss-applied` | row 4 |
  | `retract-queued` | row 5: a retract after its target, and an edit (a retract and a new answer) |
  | `retract-too-late` | row 6: the target applied by an earlier step; another refused as stale |
  | `delivered-mixed` | row 7: one key pending, one delivered before, one unknown |
  | `resent-key` | row 8 |
  | `resent-then-retract` | a resent copy of an applied line, then a retract of it |
  | `batch` | one Send of three lines, two answers and a dismissal, a main recipient and a running subagent's (`taken`) |
  | `stopped-queue` | event `start`: a queued answer, a queued dismissal (the question hidden), a queued answer retracted; after it, outcomes owed across a stop |
  | `undefined` | U1, U2, U3 |
  | `references` | a text reference with lines, one that Read cut, an image; their bodies under `refs/` |

  `grammar/result.examples.json` holds: a call that added eight; one that
  added, revised and withdrew; one that partly succeeded with an added
  and a revised entry and a refused one (the composite's own example);
  one with a refused withdrawal only (`Nothing done.`).
- The door's telling of the bridge is built now, though no mod answers
  `sheet` before M3: a bridge that does not know the op reads as
  `queued`, which is what a surface must handle anyway. It reuses
  `post_command` and `endpoint` (`S/sminos_control.py`,
  `S/sminos_bridge.py`), imported only on that path, so `put` to a
  stopped session imports neither.
- `show` without `--json` prints, a question a block: its id and
  revision, the asker when a subagent, the header, the question, the
  options numbered with the recommended one marked, the references by
  path with `changed`, and a queued answer under it.
- `state.json` is only read in this milestone (the generator writes the
  fixtures'). `put` refuses a session without a record.

**Does not touch.** The mod, in any file. The step and the other verbs
(M2). No session behaves differently after this milestone.

**Proves.** G1. Tests pin: every file of the set validates against its
schema, the examples included; the manifest is the files'; the generator
reproduces the set; `show --json` over every `before` and `after` equals
the fixture's; `put` to a fixture copy appends exactly its lines, one
batch id on a call of several, `at` filled, and prints `queued`; a line
that fails the schema, an image that is not there, a pick that is no
label at the current revision each exit 2 with nothing appended; a
session with no record exits 3; eight processes of twenty-five calls each
leave two hundred calls' lines whole, each call's lines together; a file
without a last newline gets one before the next line; `put` answers a
stand-in bridge's verdicts (`T/bridge_standin.py`).

### M2 — The record: the step, the lock, the command's other verbs

**At its end.** `sminos sheet step` makes every transition of "The state
machine", and a sheet can be driven whole from a shell with no engine:
order a `call`, read it with `show`, `answer` it, order a `drain`, see
the verdict and the pending outcome, order `landed`, see it delivered.
Every published fixture replays: the step applied to `before` gives
`after`, byte for byte once both are written in the generator's
serialization.

**Touches.** `S/sminos_sheet.py`; `S/sminos.py` (the parser's other
verbs); `T/test_sheet_step.py` (new), `T/sheet-vectors/` (new: vectors
for the events the published set does not carry: `call`, `landed`,
`reroute`, `start` with an import, the `agents` rule), `T/sheet_surface.py`
(the stand-in surface); `S/CLAUDE.md`, `SKILL.md`.

**Interfaces.** Exposes I5 whole, and I3's `answer`, `dismiss`,
`retract`, `remove`, `surfaces`. Consumes M1's.

**Decisions.**

- The step is a pure function, `step(state, tail, event, now) → (state,
  effects)`, inside a shell that owns the lock and the files. The tables
  are tested on the function; the lock, the replace and the deaths on the
  shell.
- Should the step and a published fixture disagree, §4.2 and this
  document's tables say which is wrong. A wrong fixture is reported to
  the composite's writer and corrected by a ruling (K2), never edited
  here.
- A death is tested in process: the replace made to raise, the write cut
  short, the process killed after the replace, each followed by the same
  event again, which must leave the record as one clean step would. No
  fault switch ships in the command.
- `start`'s import (I2's `import`): with `today.definite`, each ask whose
  call id is not in `import.calls` becomes one question for each of its
  questions (asker `main`, revision 1, `importedFrom`, today's `label`,
  `description`, `preview`, `multiSelect`), and its ids are recorded
  under the call id; with `definite` false nothing is imported and
  nothing recorded, so the next start tries again; with `import.never`,
  set when a new record's first `start` has source `fork`, nothing ever.
- `remove` takes the lock, refuses a session that runs
  (`session_running`) unless `--cleared`, deletes the record and leaves
  the lock file. From M6 it projects the log first.
- `answer`'s `--pick` takes a label in any case or a number, as
  `resolve_answer` in `S/sminos_control.py` reads an answer today.
- Refusal times are the machine's local `HH:MM`; a view's pending
  outcomes carry their two times formatted the same way (`local`), so
  one clock and one zone word every time the model reads.

**Does not touch.** The mod. The log and the sweep (M6).

**Proves.** The tables, each row by a named vector; and at the record's
level Acceptance 3's refusal (a `stale` verdict with `current`),
Acceptance 6's queue (`show` reads `queued`, a retract takes it back, a
`start` applies what is left as owed across a stop) and Acceptance 19's
first half. Tests also pin: every event twice equals once; a `call`
repeated under its `callId` answers the first result and adds nothing;
a reader looping `show --json` through two hundred doors and fifty steps
at once never reads a `state.json` that does not parse, sees `seq` only
rise, and at the end every key has one verdict and every `applied`
answer is pending or delivered; `put` with `--no-wait` and a step racing
it lose no line; a record removed while a door waits on its lock makes
that door exit 3.

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

**Interfaces.** Exposes I8, I11, `sheetNudge`. Consumes I5 and I3's op.

**Decisions.**

- A call, in order: validate (I6); capture every reference, one after
  another, before any step, since a capture is slow and a step is not
  [PD2]; read the running agents when the caller or the view has a
  subagent; order `call`; raise one `$.ui.notify` for a call that added
  something (its first added question, `(+N more)`), as today's tool
  announces an ask; answer the step's `result`. A step that is not done
  answers a deny: `The sheet could not be written (<why>); nothing
  changed. Call again.`
- A reference's path is the caller's, resolved by Read; `lines: [a, b]`
  is Read's `offset` a and `limit` b − a + 1. `abs`, the size and the
  modification time are read with `$.fs.stat(path, { resolve: true })`
  after the check allowed the Read. Each body is written to the staging
  directory as it is captured; nothing of a refused capture is.
- The floor (I10's last paragraph) is this milestone's, since `start`
  takes it; the context sentences that state it are M4's, so until M4 a
  floor is read from stored results and envelopes alone.
- The asker is the call's `agentId`; its name is that agent's
  `description` in `$.agent.list()`, its `type` when that is empty.
  `SUBAGENT_REFUSAL` is today's tool's alone.
- The description the tool is registered under until M7:

      Puts questions to the human on this session's question sheet and returns at once; nothing waits on them. The human answers any of them, in any order, when they get to it, and each answer reaches you later in a message that names its question by id. Go on with work that does not depend on the answers.

      Ask everything you have in one call: `ask` takes up to 20 entries. To change a question you already asked, send an entry with its `id`: it replaces the question in place. Do not ask a second question that overrides the first. To take a question back, name it in `withdraw`.

      The human sees only the card. Put in `context` what they need to judge the question, name in `references` the files it is about (each is shown as it is now), and mark an option `recommended` when you have a recommendation. Options are optional: a question without them is answered in text, and every question has a text field.

  The schema the tool is registered under is the published
  `tool-input.schema.json` with a description on each property; a test
  holds the constant in `H/sheet-model.tsx` equal to the file once the
  descriptions are taken out (a mod loads no JSON: `H/bridge-routes.tsx`
  is the precedent).
- The record is looked at, and the surfaces asked for, only where I8
  needs them: `show --json --session` when the record exists, `surfaces
  --json` when the setting is on.
- A `/clear` has three chances to remove the record it leaves: the
  `session.end` hook (reason `clear`), which is given little time and
  may not finish; the next SessionStart of source `clear`, which reads
  `left` from `SheetKept`; and M6's sweep of the cleared notes
  `sminos/hooks/smns-cleared.sh` already keeps. Each runs `sminos sheet
  remove --session <left> --cleared`.
- The timer of K4 starts at `session.start` and ends with the module.

**Does not touch.** The routes, the envelope, the contexts (M4): M3
orders `start` and drains but composes nothing for the model beyond a
call's result. The band and the rows (M5): a call draws as the engine
draws an MCP tool's. The snapshot (M6).

**Proves.** Acceptance 1's call and its result, 3's revise, 9, 15, 16's
ownership, 19's second half (the result's last line with the stand-in
stopped), and G2's line on a `claude -p` inside a MAWS-run session (the
choice, by its table). Tests pin: every row of I8's table, the kept
choice across a reload and a `/clear`, a kept `ask` snapshot without a
kept choice reading 'today'; `ask.test.ts` whole, unedited, in a session
whose choice is 'today'; yielded, none of `ask.tsx`'s hooks registers,
describes, holds or draws; the built-in denied with the sheet's
sentence; validation's whole-call refusals; a call at every bound of the
schema makes an event file under 4 MiB; a capture refused by the
check, by a failing Read and by the stub, each an entry's refusal with
the others applied and nothing of the file under `refs/`; a second drain
requested while one runs is one more step, not two; a hook that only
triggers a drain returns before the step does.

### M4 — Delivering: the routes, the envelope, a start, subagents

**At its end.** An answer accepted in a terminal session reaches the
agent: at once when it is idle, on its next tool result while a turn
runs, with the next prompt after a turn the human stopped; three answers
of one Send in one envelope; a dismissal with the next envelope and never
by a turn of its own. A session resumed with answers given while it was
stopped reads them with its first prompt, each marked with its age, once.
After a compaction, a resume and in a fork the agent is told its sheet
(I10). A running subagent receives the answer to its own question; an
ended one's goes to the main conversation naming it; a subagent that
stops with questions open is named to the main conversation.

**Touches.** `H/sheet.tsx`, `H/sheet-model.tsx`; `H/ask.tsx` (exports
`deliveryTexts`, and `searchArgs` taking the forms to search for; no
behaviour of today's tool changes); their tests;
`T/mods/live-sheet-check.py`; `H/README.md`, `H/CLAUDE.md`.

**Interfaces.** Exposes I9, I10. Consumes I5, I7.

**Decisions.**

- Before anything else is built, the live check's first case shows what
  PD5 turns on: an envelope sent as a tool result's context and as a
  prompt's, read back at `session.append` and from the transcript, with
  `<sheet-delivery>` as written. `H/bridge-rows.tsx` reads today's
  deliveries from the same hook and shows the rendering (`CONTEXT_OPEN`,
  the plugin's framing).
- Held outcomes are taken in the same synchronous step that builds the
  envelope, so no two routes take one outcome (today's `takeHeld`).
- The idle route is never awaited inside a hook: the turn it waits for
  may be the hook's own.
- After a `landed` step the mod redraws; a flight that never lands keeps
  its outcomes out of every later route for the life of the module, and
  the next start's search settles them.
- A start composes in this order: `start` step; the search and `landed`
  when outcomes were pending before the drain; the context from the view
  that results. All of it inside the classic SessionStart hook, which
  waits only on its own `$` calls.

**Does not touch.** MAWS's steer and the context the tool adds to one
(C5). The band's count of answers that will go with the next message
(M5).

**Proves.** Acceptance 2, 4, 5, 6's resume, 8, 17, 18, and G2's line on
one Send that answers the main agent's question and a running
subagent's. Tests pin: each row of I9's table; a dismissal alone, and an
outcome owed across a stop alone, open no idle route and ride the next
that opens; a refused route puts its outcomes back ahead of later ones;
a tool result that resolves while a submit is in the air carries none of
the submit's outcomes; landing from a row of each kind, and none from a
human's prompt quoting an envelope or from a steer; a reload between
handing over and landing; the search finding one of two pending
outcomes, the other going owed across a stop; a failed search landing
nothing; the envelope's every form of line and its block parsing back to
the outcomes; a block whose text holds `</sheet-delivery>`; each context
of I10 and the floor read back from each of its three sources; a send
that rejects ordering `reroute`; an agent gone from `$.agent.list()`
before the step.

### M5 — The terminal's drawing, and the import of today's asks

**At its end.** While a session has open questions the terminal shows one
line above the prompt, `3 open questions · <the surface's url>/s/<session>`,
and the to-human band draws under it. The row of a call lists its
questions and, after the outcome, their receipts. A session that had open
asks of today's tool and first starts under the sheet has them on the
sheet once, and is told.

**Touches.** `H/sheet.tsx` (`registerSheetBand`, the row hooks),
`H/sheet-model.tsx`; `H/ask.tsx` (`readAsks` answers whether its read
was definite; yielded, its SessionStart hook hands what it read to the
sheet); their tests; `H/README.md`, `H/CLAUDE.md`.

**Interfaces.** Consumes the view, I6's parser, I5's `start.today`.

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
  The count of answers is the held outcomes owed across a stop.
- A row, from the stored call alone (I11): one line a question the call
  added or revised, `q7 Auth method — <the question's first sentence>`;
  then, where a view knows the question, the receipt in the line's
  place: `q7 Auth method → OAuth`, `q7 Auth method · Dismissed`, `·
  Withdrawn`, and `· Revised below` when the question's revision is past
  the one this call set. A withdrawal the call made draws `q2 ·
  Withdrawn`. A session with no record (a fork, a record removed) draws
  the lines without receipts.
- A read is definite when the whole file was read, or the search ran and
  its output was not cut. Indefinite, the `start` event says so, nothing
  is imported or recorded, and the next start reads again. A fork's first
  start under the sheet sends no asks: the step records `import.never`.
- An imported ask's own row stays as `ask.tsx` draws a stored call.

**Does not touch.** Today's band and rows in a session whose choice is
'today'.

**Proves.** Acceptance 1's line, 16's row, the receipts of §8.3, and
G2's three import statements (once, also after two resumes; kept when
the read was incomplete; a fork empty and staying empty). Tests pin the
line's four forms, each receipt, a stored call drawn with no record, and
an import retried after an indefinite read.

### M6 — The other readers, and the sheet's end of life

**At its end.** doperpowers' appeal ends its passes when the human
answers a sheet question, as it does for today's asks. The project log
holds one `question` for each sheet question and one `answered` when it
closes, across a stop and a resume; the stop cleanup leaves a sheet
question open. A record whose session's transcript is gone is removed by
the daemon, with its questions closed in the log.

**Touches.** `H/sheet.tsx`, `sminos/types/sminos.d.ts` (I13);
`S/sminos_sheet.py` (the projection; `remove`'s closure);
`S/sminos.py` (`close_questions`; `run_record`'s call of the projection);
`S/sminos_daemon.py` (`sweep_sheets`, in `override_duty`);
`T/test_sheet_log.py` (new), `T/mods/sheet.test.ts`; a case in the
repository's `tests/mods/` that appeal's reader takes the sheet's
snapshot; `S/CLAUDE.md`, `H/README.md`.

**Interfaces.** Exposes I12, I13. Consumes the record.

**Decisions.**

- The sweep removes a record when its session runs nowhere here, its
  transcript is gone as `transcripts_now` sees it, and `state.json` has
  not been touched for an hour (an index that misses a transcript for a
  moment must not cost a sheet); a record a cleared note names, at once;
  and a lock file with no record.
- The projection resolves the session's project and alias as `sminos
  record` does, and does nothing for a session in no project.
- The sweep runs under `override_duty`'s spacing: the `sminos-idle`
  gate's count must hold.

**Does not touch.** MAWS's channel journal (C5). The bridge's own
requests: a sheet question is raised to no desk client by this child
(§8.4 is C6's).

**Proves.** G3's first clause, and Acceptance 6's last. Tests pin: stop,
resume, answer leaves one `question` and one `answered` with the real
answer; a projection run twice appends nothing; a subagent's question
and an answer accepted at a start are in the log; `close_questions`
closes a question of today's tool and passes a sheet's; a removal closes
what was open; the snapshot's `answered` rises by the answers applied
and not by a dismissal.

### M7 — The description, what is written beside the code, the acceptance

**At its end.** The tool ships the description that passes C1's
thresholds; if the owner ruled for automatic capture of context (§10),
it is built and passes with it; the manuals say what the plugin now
does; G2 and G3 hold as the composite words them, run as written.

**Touches.** `H/sheet-model.tsx` (the description and the properties'
descriptions); `H/README.md` (a section "sheet" beside "ask"),
`H/CLAUDE.md`, `S/CLAUDE.md`, `sminos/CLAUDE.md`, `sminos/README.md`,
`sminos/hooks/hooks.json` (its description), `SKILL.md`; the version;
`docs/doperpowers/TECH-DEBT.md` (the limits accepted: U6, U8, the
reload's double delivery, a rewind after a delivery).

**Decisions.**

- The description is tested with C1's two evals as C1 merged them under
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
    S=5eed0000-0000-4000-8000-000000000015
    sminos/skills/sminos/scripts/sminos sheet show --session "$S"
    printf '%s\n' '{"v":1,"key":"demo-0001","kind":"dismiss","id":"q1","by":"cli"}' \
      | sminos/skills/sminos/scripts/sminos sheet put --session "$S"

The last prints `{"session": "5eed0000-…", "results": [{"key":
"demo-0001", "state": "queued"}]}`, and `show` then no longer lists
`q1`. The test file ends `test_sheet_contract: N passed`; the generator
prints `sheet-contract: 15 cases, digest <sha256>`. After the merge,
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
    echo '{"event":"drain","runner":"terminal"}' | step

The call's `effects.result` is `Added q1.`; `answer` prints `queued`;
the drain's view holds one pending outcome for `q1` and `show` reads its
key `accepted`.

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
started.

    python3 sminos/tests/mods/live-sheet-check.py                   # every case
    python3 sminos/tests/mods/live-sheet-check.py --case many       # one

| case | what it does and must observe | proves |
|---|---|---|
| `rendering` | sends one envelope by each route; reads it at `session.append` and in the transcript | PD5's second sentence |
| `many` | asks for eight questions, one referencing a file; the result is `Added q1, q2, q3, q4, q5, q6, q7, q8.`; the line reads `8 open questions` and the stand-in's link; `show` lists eight and the file's text as captured, also after the file is edited (`changed`) | Acceptance 1 |
| `subset` | `put`s three answers as one call while a turn runs: one row of the transcript holds an envelope with three keys, the agent quotes the three, five remain; then three more while idle: a turn starts by itself and quotes them | Acceptance 2 |
| `revise` | has the agent revise `q2`; an answer sent with revision 1 prints `stale` with `current` 2; `show` has the new text at revision 2 | Acceptance 3 |
| `note` | answers with a pick and a text; the agent repeats both | Acceptance 4 |
| `dismiss` | dismisses a question in an idle session: no turn starts within 20 s; after another answer the agent names the dismissal | Acceptance 5 |
| `stopped` | ends the session; `show` lists its questions; `answer` prints `queued`; `retract` takes one back; resumes; the first prompt's context carries the other with its two times; the project log has one `question` and one `answered` for it | Acceptance 6 |
| `subagent` | a subagent asks; `show` names it as asker; answered while it runs, the subagent's own transcript holds the envelope and the main one does not; answered after it ended, the main conversation's does, naming it | Acceptance 8 |
| `both` | one `put` answers the main agent's question and a running subagent's: each conversation holds an envelope with its own key only | G2 |
| `no-surface` | three starts: the setting off; on with no registration; on under `SSH_CONNECTION` with a `local` one: each has today's schema (`questions` in the tool's input) and the engine's dialog | Acceptance 9 |
| `secret` | references a `.env` the session's permissions deny: the result's `Not done:` names it; `refs/` is empty | Acceptance 15 |
| `withdraw` | the agent withdraws a question: `show` no longer lists it and the row reads `Withdrawn`; a subagent told to revise and to withdraw the main agent's question is refused both | Acceptance 16 |
| `compaction` | compacts, then asks the agent to list its open questions and their options without calling a tool: it names them | Acceptance 17 |
| `fork` | forks the session: `show` on the copy is empty, the copy's first context says so, and its next question's id is past the original's highest | Acceptance 17 |
| `agent-open` | a subagent ends with a question open: the main agent's next tool result carries the notice | Acceptance 18 |
| `two-surfaces` | two `put`s answer one question: `applied`, then `closed`; then the stand-in is stopped, the agent asks again and its result ends with the no-surface sentence; the stand-in returns and `show` lists the question | Acceptance 19 |
| `import` | a session with two open asks of today's tool is resumed under the sheet: both are on the sheet, and are there once after two more resumes; with the transcript's search made to fail, nothing is imported and the next resume imports; a fork of such a session is empty after its own resume | G2 |

It ends `live-sheet-check: 17 passed` and exits 0; a failing case prints
`FAIL <case>: <what was observed>`.

**M7**, besides the live check:

    ci-gate                                                         # every gate the change's paths plan

then C1's two evals, each by the command its header gives, against the
shipped description; each must meet the threshold the composite's
Acceptance 14 then states.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

State, like Progress: each sentence of the composite this child's work
makes false or incomplete, with the replacement proposed. A binding
sentence stands until its writer rules; where this plan builds on a
reading of one, the entry says what changes if the ruling goes the other
way.

**Binding sentences.**

1. §3, "`state.json` the sheet; written only by the tool, by atomic
   replace" and "Only the tool writes `state.json`." This plan reads "the
   tool" as the tool's process acting through the plugin's own step (K1):
   a hook has no rename, no lock and no append, and cannot read a file
   past 4 MiB. Proposed: "written only on the tool's order, by the
   plugin's step (`sminos sheet step`) under the record's lock, by atomic
   replace." A ruling that the hook itself must write changes I5 and M2,
   and gives up the lock shared with the door.
2. §3, Lifetime, "starts its ids past the highest it can find, in the
   parent's directory for a fork and otherwise in the transcript's stored
   calls (X7)". No module can learn which session a fork copied
   (`ask.tsx`, `historyAsks`). Proposed: "past the highest it can find in
   the conversation it holds: its stored calls (X7), its envelopes, and
   the SessionStart context, which states the next id (I10)."
3. §4.2's table. Four cases it does not carry, decided as U1 to U3 and
   in the drain's step 3; proposed as rows: a retract whose target the
   record never saw (both `retracted`, the target set aside if it comes);
   a retract naming a retract or a `delivered` line (`too-late`); an
   answer or dismissal for an id never assigned (`closed`, `how:
   unknown`); and under the table, "a line that is not valid is skipped
   without a verdict; the door refuses what it can see."
4. §4.1, "so three answers of one Send never reach an agent as one and
   then two." True but for U6 (a door killed inside its one `write`).
   Proposed: add "save a door killed inside its write, whose resend
   completes the batch." Closing it needs a count on the line, which this
   plan does not propose.
5. §5.1, "An outcome leaves `pending` when its delivery is known, not
   when it was sent." The composite says what "known" is for MAWS (§5.4)
   and not for the tool. Proposed, in §5.2: "For the tool, a delivery is
   known when it sees a row one of its own routes wrote, carrying the
   envelope's keys, kept in the conversation; at a start it reads the
   transcript for the same. For a subagent, when the engine has queued
   the send."
6. §5.3, the block. Fixed within the shape, for the schema: `keys` holds
   the answered outcomes' keys in the order of `answered`, then the
   dismissed ones'; `picks` holds labels in the terminal form and places
   (integers from 1) in the steer form; the JSON writes `<`, `>` and `&`
   as escapes and is one line.
7. X2, "Whether MAWS calls the command or the same code over the sminos
   daemon's socket is settled by C2 and C3 and recorded here." C2's side:
   "MAWS runs the command: `sminos sheet put`, lines on standard input,
   one JSON object of results on standard output (I3); nothing is served
   over the daemon's socket." It waits on C3's agreement.
8. X6 and §7, "How the proof is had is C2's and C5's to settle (…)".
   C2's side: "MAWS sets `MAWS_QUESTION_SHEET` to the launch's session
   id; the tool honours it only when it equals the id of the session the
   process starts, and ignores a value that does not." It waits on C5's.
9. X3, "*Readers:* the tool, MAWS's reader of arrivals, the project
   log's export", and §5.3's "by the project log's export". The log is
   projected from the record (I12): a subagent's call and an answer
   accepted at a start are in no main transcript. Proposed: drop the
   export from both lists.
10. §9, "A fork or a copy imports nothing … and that decision is recorded
    so a later resume of the fork does not import them either." Holds for
    a fork whose first start is under the sheet (`import.never`).
    Proposed: add "A fork first started under today's tool holds its
    parent's open asks as its own, as it does today, and a later start
    under the sheet imports them."

**Open or advisory points, settled here.**

11. C2's Acceptance, G1, "a JSON Schema for `state.json`, the inbox line,
    the surface registration and the `<sheet-delivery>` block". Two more
    are published: the tool's input (X7; C1's stub and MAWS read it) and
    what `sminos sheet show --json` prints (X2). Proposed: name both.
12. C2's Edges, "blocked-by: C0 (P2 in a terminal, P3, P4, P5) for G2".
    Proposed: "C0's P3 for M3 and P2, P5 for M4 of C2's plan; M2, the
    record's step, consumes no verdict and follows M1 (P4 confirms it)."
13. §12, P4, "Is the tool's atomic replace of `state.json` atomic to a
    reader in another process; does the inbox's locked append hold under
    two concurrent writers?" Under K1 neither is a hook's. Proposed: "Is
    `os.replace` of a synced temporary file atomic to a reader in another
    process; does `fcntl.flock` on a file beside the record hold between
    two doors and a step; can a reader that holds no lock see part of one
    `write` of several lines?" The last decides only how a reader without
    the lock (MAWS's) treats a tail.
14. §12, P5 (or P1): one observation more, which PD5 names: whether a
    hook's context reaches the model and a `session.append` hook with
    `<sheet-delivery>` as written, or with its `<` escaped as the engine
    escapes a reminder's tag in a hook's context
    (`sminos/hooks/mods/bridge-rows.tsx`, `ESCAPED`).
15. §5.4, "for the main conversation receiving a subagent's answer as
    hook context on that prompt." No child is named for it. Proposed:
    "built by C5, in the sminos plugin, on P1's verdict, from the view
    C2's step answers."
16. §8.3, the command. Added: `retract` (a queued answer can otherwise be
    taken back from no command line) and `surfaces`; and U12: `answer`,
    `dismiss` and `retract` refuse a session acting on its own sheet.
17. §11, "the `AskSnapshot` the ask mod keeps". It stays `shape: 2` with
    one optional field, `sheet` (I13), so no reader changes.
18. §3, "The directory of a stopped session is removed by the sminos
    daemon's sweep once its transcript is gone". Proposed: add "and the
    record has not been touched for an hour; and at once where a note of
    a `/clear` names its session."

**Cases the composite does not carry, decided in "The state machine".**

19. U4, for §2.2 and X7: a call in which nothing was done answers
    `Nothing done.`
20. U5, for §6: a withdrawal is delivered to nobody; a running subagent
    whose question the main conversation withdrew is not told.
21. U7, for §1: at most 500 open questions on a sheet.
22. U8: two processes on one session id lose no update and may both
    deliver.
23. U9, for §7: a headless process MAWS did not launch never takes the
    sheet, also when its session has one.
24. U10, for §3: a `/clear` drops what was pending.
25. U11, for §5.2, "rides the human's first prompt as context".
    Proposed: "rides the first prompt that enters".
26. I3, for §4.1: the line's bounds (`text` 20,000 characters, 12 picks,
    8 images, 200 keys, 50 lines a call), and that the door fills `at`
    and assigns `batch`.
27. I2, for §1 and §2.3: a stored reference also holds `abs`, `kind`,
    `mediaType`, `bytes` and `cut`; a closed question keeps `how`, its
    revision, its header, its first 200 characters and its receipt for
    the record's life, which the terminal's rows and `closed` verdicts
    read.
