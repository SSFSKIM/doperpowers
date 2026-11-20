# sminos threads, T2 — the wake: execution (2026-11-20)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **T2** (The wake). **Parent pin:** `main` `f7f51f6b`, that file's blob
> `71b820fd4c337661b538694b366ffd666a952fc1`. The child's section there is its
> spec, D2 its design (binding), X1, X3, X6 and X7 its contracts. This document
> carries the constraints and the milestones and nothing of the design. Read
> before M1: the composite's Purpose, Terms, D1 (the paragraphs Lifecycle and
> Verbs that start a process), D2 whole, D7, the engine facts E1 to E16, the T2
> section, X1 and X3, the Risks entry "The store has no writer in charge", and
> the Decision Log's entries of 2026-11-20; the two research notes
> `docs/doperpowers/research/2026-11-17-sminos-channels/wake-spike.md` and
> `wake-spike-2.md` (the engine, measured); T1's plan
> `docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`, its Interfaces §1
> (the record), §5 (the hold) and §6 (transitions, older copies); and
> `docs/doperpowers/TECH-DEBT.md`, section "sminos threads".

After this child a message addressed to a stopped session starts that session
again in the background, whoever opened it. A session its human opened in a
terminal and closed is woken under the same session id, in the permission
mode and on the model of its last turn, and is told in its first line that it
runs in the background and that its human is not watching; its human can
attach to it with `claude --resume <id>`. A message that cannot wake its
session is held, its sender is told why, and it is pushed as soon as a process
of that session runs. How to see it working is T2's acceptance in the
composite (G2, ten items), run as Concrete Steps gives it.

## Progress

- [x] (2026-11-20) The direction ruled by the owner (one wake path) and folded into the composite (PR #574).
- [ ] The engine facts read again on the engine of the day (`wake-spike-2.md`), folded into this plan.
- [ ] M1 — The engine's row, the last turn and the wake's words, with a stub engine that keeps rows.
- [ ] M2 — The wake itself: `resume_session` extended, the lock, the copy and the failure; a seat goes through it.
- [ ] M3 — Delivery wakes every stopped thread, and holds what it cannot wake with.
- [ ] M4 — The verbs, the direct send, and what a sender is told on any machine.
- [ ] The frontier review of M1 to M4 as one range, by the composite's holder, and its fixes.
- [ ] M5 — What sessions are told, older copies, several senders, and the acceptance on a real engine.

## Words this document adds

The composite's Terms define thread, seat, wake, deliver, the daemon and the
engine's row (E8). T1's plan defines spawned, human-opened, the seat store,
the thread store, stamped, the journal and the short id. Added here:

- **The wake lock** is the file `<thread id>.resume.lock` at the root of
  `$SMINOS_HOME`, locked with `flock`. `resume_session` takes it today for a
  seat, and the daemon's thread sweep holds it out while it marks a thread
  stopped or ends it (`resume_lock_out` in `sminos_daemon.py`).
- **The delivery lock** is `<project>/delivered/<session>.lock`, which every
  deliverer holds from choosing an event to settling it (`deliver_next`,
  `SendDelivery`).
- **A first wake** is one for a session that has no row; **a later wake**
  finds a row. A row is the engine's `jobs/<first eight of the id>/state.json`
  under the session's config directory, naming the session in `sessionId`.
- **Held** means owed and not pushed: the event stays in the log, its mark
  `[seq, thread]` is in the delivery record (T1), no attempt is counted, and
  it is pushed when a process of the thread takes it or settled when the
  thread ends.
- **A job** is a background session as the engine lists it
  (`claude agents --json --all`); its **short** is the id the launch prints.
- **The stub** is the `claude` stand-in of `sminos/tests/run-sminos-tests.sh`,
  which the shell suites put first on `PATH`; the Python suites patch
  `sminos.run_claude_bg` and `sminos.poll_uuid` instead.
- **`S/`** is `sminos/skills/sminos/scripts/`.

## Constraints that bind every milestone

- **The composite has one writer,** the session that holds it. This
  document's controller records decisions and discoveries here and sends that
  session whatever touches the child's purpose, its acceptance, a contract or
  a binding decision; it never edits the composite.
- **What binds, by id.** D2 whole, its paragraph "One path" first: how a
  thread was opened selects nothing in the wake or in what is held. D1's rule
  for a held message (owed until pushed to the thread's own process or the
  thread ends; a recorded decision per event, never read from a process's
  state or a clock). D7 whole. X1 (a field is added only through
  `sminos_threads.py`), X3 (T2 owns it; Interfaces §4 is its text), X6, X7.
- **One place starts a process for a stopped thread:** `resume_session`,
  extended. No second launcher is written beside it, for either kind of
  thread, and nothing calls `run_claude_bg` with `--resume` but it.
- **Everything a wake decides, it reads under the wake lock,** and every
  write a wake makes is made while it holds that lock (Interfaces §3). What
  was read before the lock was taken (the member, the record, whether a
  process holds the session, the row) chooses only whether to try; under the
  lock it is read again and that reading decides. T1's branch review found
  most of its 82 defects between a check and its write.
- **Lock order,** outermost first: the delivery lock; the seat's lifecycle
  lock (`lock_seat`, a record in the seat store only); the wake lock; a store
  lock (`.metalock`, `threads/.lock`); a log's lock. The wake lock is never
  waited for without a bound while a delivery lock is held: the sweep takes
  the wake lock first and a settlement's delivery lock under it, so the two
  orders meet only through `resume_lock_taken`'s bounded poll, whose expiry
  is a hold and not a failure.
- **Nothing is signalled that is not the session's own job.** `claude stop`
  and `claude rm` are run only on a short the engine lists for this session,
  or on a copy this wake's own launch just made. A session a terminal holds
  is delivered to or left; it is never stopped.
- **Older code on the same machine** keeps D7's two rules. A human-opened
  thread's record stays in the thread store, and a wake writes nothing about
  it into the seat store, so a copy from before T2 still starts no process
  for it. A copy at 1.51 holds what T2 would wake: the daemon, which runs
  the installed copy, wakes with what that copy marked.
- **No event kind is added,** and nothing about a thread's wake leaves the
  machine but the field `why` on its stopped `state` (Interfaces §4). What
  `sminos_outcomes.report_held` sends for an outside event keeps its shape.
- **`S/sminos.py` is one file of seventeen thousand lines.** The parts of the
  wake that read and compute (the row, the last turn, the flags, the line,
  the reasons) go in a new sibling module, `S/sminos_wake.py`; `sminos.py`
  gets the changed seams. `origin/main` is merged before M1 and before the
  final push.
- **The idle daemon stays cheap.** Whether a stopped thread is woken or held
  is computed from file stats and cached by them; a transcript's tail is read
  only when the transcript's stat changed. No per-tick duty launches
  anything, lists the engine's jobs for a thread nothing is owed to, or reads
  a transcript whole. The `sminos-idle` gate is the check.
- **Tests are hermetic,** as in T1: the stub, a temporary `HOME` and
  `SMINOS_HOME`, invented names. The repository is public: no hostname,
  account, project id or local path enters a test, a comment or this
  document.
- **Tests vary what T1's did not:** the number of senders (one, two and
  five), the three ways a message is sent (`say @alias`, `send`, and a
  message from another project), and the order of a wake against a sweep, a
  second wake and a reopening by hand. A guarantee tested with one sender is
  not tested.
- **What a session reads keeps today's words** (X6): session, seat, member.
  "Thread" stays in code, records and event fields.
- **One change, one version.** The child merges as one pull request that
  leaves the repository releasable beside a machine on 1.51 (D7), with
  sminos's version bumped in it (`scripts/bump-version.sh --plugin sminos`,
  to 1.52.0 unless `main` has moved past it).

## Plan of Work

The wake is `resume_session` made to serve any thread. M1 builds what it
reads and says, as functions with no effect, and teaches the stub engine the
behaviour the functions rest on. M2 extends `resume_session` into the wake:
the steps, the lock, the copy and the failure, decided in one table, with a
seat's resume going through it at once. M3 changes delivery: a stopped
thread its human opened is woken where it was held, and what cannot be woken
is held for either kind. M4 brings the verbs and the direct send onto that
path and publishes why a thread is held. Between M4 and M5 the range is
reviewed whole by the composite's holder. M5 changes what sessions are told,
runs an older copy and several senders against the result, and runs the
acceptance on a real engine.

No release is cut between milestones: the branch merges once, after M5.

**The frontier review.** When M4's review is clean the controller pushes the
branch and returns to the composite's holder with the word `FRONTIER`, the
range (`git merge-base origin/main HEAD` to `HEAD`) and nothing else to
decide. The holder reviews that range through doperpowers:review-code at the
panel rung, with lenses given, not derived: lock order and what is read
outside a lock it is acted on under; an older copy on the same store; the
milestones' interactions (a wake against the sweep, an end, a hand-off, a
`/clear`, a refill); and what leaves the machine. Its confirmed findings are
fixed on the branch by the holder's fix wave, and the range is read whole a
second time if the first reading confirms more than ten. The controller is
then continued for M5.

### M1 — The engine's row, the last turn and the wake's words

**At its end:** `S/sminos_wake.py` exists and answers, for any session on
this machine, whether the engine holds a row for it, which mode and model its
last turn ran under, which flags a first wake passes, what the opening line
says, and for which reason, if any, the thread is not woken. Nothing calls it
from a delivery path yet, so no behaviour changes. The stub engine keeps
rows: a `--bg --resume` with flags on a session with no row continues the
same id and writes a row; with flags on a session that has one it starts a
copy and says so in the engine's words; `rm` removes a row and keeps the
transcript; a worker can be made to fail before it starts.

**Touches:** `S/sminos_wake.py` (new), `S/sminos_threads.py` (the record's
`waking` field and its three writers, Interfaces §5; `LAUNCH_OPTIONS` if the
spike's facts add an option), `sminos/tests/run-sminos-tests.sh` (the stub),
a new `sminos/tests/test_wake.py` registered in the suite runner, and
`S/CLAUDE.md` for the new module.

**Interfaces:** exposes §1 (the readers), §2 (the flags and the line), §5
(the record's field), §6 (the stub). Consumes T1's record (`get`,
`thread_of`, `update`) and `sminos_policy.effective`.

**Decisions:**

- The row is read with no lock and believed only for the moment: it is read
  again under the wake lock at each wake (D2, step 2). A file that does not
  parse, one whose `sessionId` is another session's, and a config directory
  with no `jobs` directory all read as `UNREADABLE`, never as "no row": the
  difference decides whether the copy answer is the fallback (D2).
- The last turn is read from the transcript's tail, backwards, at most 4 MiB,
  and cached by the transcript's device, inode, size and mtime. A hook's row
  (`requestId` null, a `message.id` beginning `msg_hook_`) is no turn (E14).
  A session whose tail holds no prompt row with a mode has mode `""`, and one
  with no assistant row of its own has model `""`.
- The mode a wake would run under is the row's `--permission-mode` when a
  readable row has one, else the last turn's. A thread is not woken for
  `mode` when the last turn's mode or the row's asks for approval
  (composite, D2). The modes that ask are the transcript's `default`, `plan`
  and `acceptEdits` and the flag's `manual`; any other value, one sminos does
  not know included, is one that does not ask (the owner's ruling: modes are
  not guarded).
- The mapping between a transcript's mode and the flag's value is a table in
  `sminos_wake.py`, filled from `wake-spike-2.md` (question 3). A mode with
  no known flag value is passed as it is written.
- The flags of a first wake, in this order: `--permission-mode` (the last
  turn's mode, lowered to the policy ceiling when it is above it by
  `sminos.PERMISSION_MODES`' order; left out when the mode is `""` and the
  record's launch has none), `--model` (the last turn's model, else the
  launch's, else left out), then from the record's `launch.options` those
  the spike shows in effect on a first background resume: `--effort`,
  `--settings` when its value is a file that exists, `--add-dir` for each
  directory that exists. Nothing else is passed. `--output-style` is never
  passed (E12). Everything of `launch.options` that was not passed is
  returned as not carried, by option name and never by value.
- Where the message goes in the argument vector beside a variadic option is
  the spike's question 11; the vector is built in one function so that the
  answer is applied in one place.
- The reasons (`not_woken`) are checked in a fixed order and the first that
  holds is the answer: `config`, `transcript`, `cwd`, `protected`, `mode`.
  Each is a fact that stays until something outside sminos changes it.
  `read-only` is not among them: it is decided per event, for an outside
  event, where `deliver_next` decides it today. Nor is `failed`: a wake that
  failed is tried again, so it is a schedule (§3) and not a reason to stop
  asking. `protected` holds for a record whose `opened` is `human` and whose
  directory is in a protected folder (`protected_folder`), whichever process
  asks (D2: a launch there by the daemon stops at a system dialog). `cwd` is
  the record's launch directory, or for a record in the seat store
  `seat_cwd`, missing or not a directory; one this process may not look at
  (`read_refused`) is taken on its word, as `resume_session` does today.

**Does not touch:** `resume_session`, any delivery path, any sender's
output, the guide or the skill.

**Proves:** nothing of the acceptance alone. Its tests pin: a row found, not
found and unreadable in each of its three forms; the last turn read from a
tail that ends in hook rows, from a transcript larger than the tail bound,
and from one with no turn; each mode's mapping; the flags for a launch with
every kept option, with a settings file that is gone, with a mode above the
ceiling, and with nothing recorded; the not-carried list; each reason and
their order; `wake_due` at each count and time; and the stub's four behaviours, each through the real `claude`
argument vectors the spike recorded.

### M2 — The wake itself

**At its end:** `resume_session` is the wake of §3. Called for a seat, as
every caller calls it today, it runs steps W1 to W8: it reads the record,
the reasons and the three signals again under the wake lock, reads the row,
passes flags only on a first wake, opens the message with the line, removes
a copy the engine made, and tells a launch that failed from one that
succeeded. Called for a human-opened thread's record (by this milestone's
tests alone; no delivery path does yet), it wakes it under its own id with a
first wake's flags. A seat's resume from delivery that would have failed
because a process held the session now delivers to that process or leaves
the message owed.

**Touches:** `S/sminos.py` (`resume_session`, its `copy_started`,
`run_claude_bg` only if the argument order needs it, the seat branch of
`push_member` where it maps what `resume_session` answers, `note_launch_of`),
`S/sminos_daemon.py` (`resume_lock_out`), `test_wake.py`, the tests that pin
`resume_session`'s old answers for a copy and for a held session
(`run-sminos-tests.sh`'s resume cases, `test_threads_stopped.py`'s resume
against the sweep), `S/CLAUDE.md`.

**Interfaces:** exposes §3 (the wake, its table, its outcomes, the retry
rule). Consumes §1, §2, §5, §6.

**Decisions:**

- `resume_session` takes a thread's record where it takes a seat today, or
  is split into a core that takes the record and thin callers; which is the
  executor's, under the constraint that one function launches. What is a
  seat's alone stays with the seat: its lifecycle lock, `meta_set`'s fields
  (`status`, `short`, `turns`, `pending_short`), `join_seat`, a retired
  seat's return by `fill --resume`. A human-opened thread's wake writes none
  of them: its process's own hooks restate it, as they do when its human
  reopens it.
- A verb's own steps stay ahead of the wake and are not part of it: the
  reach checks, the refusal of a vacant or retired seat, and the stop of a
  live turn that `sminos resume` asks for. The wake itself stops nothing but
  a finished job's row the engine still lists for the session (W3, today's
  rule), under the constraint that only the session's own job is signalled.
- A copy is removed with `claude rm`, not left stopped (D2). `copy_started`
  today stops the short and fails; the table's rows 7 to 9 replace it.
- From delivery (`quiet`), every refusal the table names is its `held:`
  outcome and counts no attempt; a refusal that is a seat's alone (vacant,
  retired, a codex record) answers as today. From a verb, the same cases
  raise as today with the table's reason in the message; M4 gives the verbs
  their words.
- The retry rule of §3 is applied where delivery calls the wake for a seat,
  so that a seat whose wake fails is not launched again at every pass; M3
  applies it to every thread. The rule needs the event's mark, so
  `held_decided` marks an event on each `held:` outcome of the table, as it
  marks T1's hold. What a mark means for a spawned thread beyond that (owed
  through `recorded` and `failed`) is M3's.
- The third signal of E5, the bridge's socket for the session, is read
  beside the engine's records and the job list before a launch. A signal
  that cannot be read (the job list failing) is a held session, never a
  free one.
- `note_launch_of` keeps the record's `options` when the process that
  started is a background one: a wake is not a launch its human made, and
  the next first wake (after a failed one removed the row, or the engine's
  clean-up lapsed it) reads the terminal launch's options.
- The sweep opens the wake lock's file for a human-opened record as it does
  for a seat's (created when absent), so that a first wake and the sweep
  meet on one file.

**Does not touch:** `push_member`'s branch for a session with no seat,
`hold_of`, `hold_now`, the marks, the verbs' output, `SendDelivery`. A
human-opened thread is still held after M2.

**Proves:** G2 items 3, 4, 7 and 8 against the stub, for a seat through
delivery and for a human-opened record by direct call. Its tests pin every
row of §3's table for both kinds of record; the two orders of a wake
against the sweep's stop mark and against an end; a wake against a
reopening by hand (the engine's copy answer, the copy removed, nothing
remembered); a wake that finds an open journal entry; a second wake while
the first holds the lock; a failed first wake leaving no row, and the next
wake passing flags; an unreadable row answered with a copy, the copy
removed, the wake made again with no flag, and the next wake passing none;
the directory a first wake is issued from; and the line a seat's resumed
prompt now opens with.

### M3 — Delivery wakes every stopped thread

**At its end:** an addressed message to a stopped thread wakes it,
whichever way it was opened. With the stub: `sminos say "@alias …"` to a
closed human-opened session resumes it under its own id with a first wake's
flags and the opening line, and a later message resumes it with no flag.
Two deliverers that wake one thread together start one process, and both
messages reach it. A thread that is not woken, a wake that failed and a
process that takes no push yet each leave the message held, with its mark,
for a spawned thread as for a human-opened one, and it is pushed when a
process of the thread takes it. The daemon tries a failed wake again on
§3's schedule and stops at its bound.

**Touches:** `S/sminos.py` (`push_member`, `push_event`, `deliver_next`,
`deliver_verdict`, `deliver_reach`, `held_decided`, `held_owed`,
`human_owed`, `words_unanswered`, `hold_for`, `hold_now`, `bound_peer`),
`S/sminos_threads.py` (`hold_of`, `hold_now`, `awaits_seat`'s callers),
`S/sminos_daemon.py` (`deliver_owed` and its memory of a held pass),
`S/sminos_outcomes.py` only where it names the hold, the tests of
`test_threads_stopped.py`, `test_threads_branch_b.py` and `test_words.py`
that pin the hold of a human-opened thread (changed to pin the wake),
`test_wake.py`, `S/CLAUDE.md`.

**Interfaces:** exposes the changed `hold_of` (§1). Consumes §3 and §5.

**Decisions:**

- `push_member` has one branch for a thread: the session a live inbox
  answers for is pushed to; one a process holds with no inbox is
  `held:starting`; one no process holds is woken when the event is addressed
  and `recorded` when it is for the live alone. A session that is no thread
  (lane B, a member an older copy joined unstamped with no record) is
  delivered to as today.
- `hold_of` and `hold_now` answer `""` when this machine delivers to the
  session or would wake it, and one of `not_woken`'s reasons when it holds.
  Every caller that read a true answer as "push nothing, ask nothing" stays
  right; every caller that read a false answer and a missing peer as "not
  live" is changed to wake. The constant `HELD_HUMAN` goes; the outcome is
  `held:<reason>`.
- A wake that is not due (§3) is decided where a hold is decided, before any
  question about the event is put to the endpoint (the words gate, the
  reach gate): the outcome is `held:failed` and nothing is asked.
- `human_owed`'s rule becomes every thread's: a marked event of a session
  that is the current one of a thread that has not ended, of either kind,
  is owed until pushed. An event marked for a thread the session no longer
  fills is the stale hold, as today, which a refill makes of whatever was
  held for the occupant it replaced.
- The young-background wait (`awaits_seat` with `own` false: another process
  treats a background session younger than the spawner's bound as a spawn's
  child that has no seat yet) must not apply to a session that is already
  the current one of a thread: a woken human-opened thread is a background
  process with no seat, and nothing may wait for a seat to claim it or
  withhold its `joined`. `wake-spike-2.md`'s question 9 has what the
  engine's record of such a process holds.
- `deliver_owed`'s memory of a pass that left everything held
  (`_HELD_PASSES`) includes every input the reasons read, and a pass held
  for a wake that is not due is remembered only until that wake is due.
- A wake carries one event's frame, the one delivery was pushing; what else
  is held for the thread is pushed by the pass that follows (the daemon is
  nudged) to the process the wake started. No second account of what is
  owed is kept (composite, T2's inheritance).

**Does not touch:** the verbs (`resume`, `fill`, `send`), `send_to_seat`,
`send_to_member`, `SendDelivery`, `hold_verb`, `held_send`, `held_line`,
what `lifecycle` publishes in `state`, the guide. After M3 a `send` to a
stopped human-opened thread still records and holds it in its own words,
and the daemon's next pass wakes it.

**Proves:** G2 items 6, 9 and 10 against the stub, and item 1 as far as
`say` goes. Its tests pin, each with one, two and five senders: a stopped
thread of each kind woken by an addressed event and not by one for the live
alone; two wakes together from one project and from two; each reason held
with its mark for each kind (a spawned thread's directory gone, another
config dir and no transcript: held, where they were `recorded`); a held
event pushed after a later wake succeeded; a process that holds the session
with no inbox, held and then pushed; the retry schedule, a new message as
an attempt inside it, and the bound with its one line in `daemon.log`; a
hand-off and a refill making a stale hold of what was held; nothing asked
of the endpoint for a held event; and the daemon's pass costing no launch
and no job listing for a thread nothing is owed to.

### M4 — The verbs, the direct send, and what a sender is told

**At its end:** `sminos resume`, `fill --resume` and `send` (with and
without `--wait`) aimed at a stopped session its human opened wake it, and
with `--wait` print its reply; aimed at one that is not woken they record
the message, start nothing, say why and exit 4. A fresh `fill` of it is
still refused. `sminos say "@alias …"` and `send` print, when they send,
whether the session was woken or is held and why, on the session's own
machine and from another machine by what that machine published. A direct
send no longer carries an event its sender was told went to no one.

**Touches:** `S/sminos.py` (`cmd_resume`, `cmd_fill`, `_send`,
`send_to_seat`, `send_to_member`, `SendDelivery`, `hold_verb`, `held_send`,
`held_record`, `held_line`, `woken_line`, `remote_line`, `wake_of`,
`deliver_say`, `lifecycle`, `_member`, `who_lines`, `resolve_seat_or_opened`,
`finish_turn` or a sibling of it, the module docstring that is `sminos
help`), `S/sminos_daemon.py` (`publish_state`), the tests that pin exit 4
and the held line for these verbs, `test_wake.py`, `S/CLAUDE.md`,
`sminos/CLAUDE.md`.

**Interfaces:** exposes §4 (X3 as T2 fixes it, and the words). Consumes §3.

**Decisions:**

- A verb aimed at a human-opened thread and one aimed at a seat reach the
  same wake. `resume` and `fill --resume` stop a live background turn of the
  session first, for either kind, and never a terminal's process; aimed at a
  session a terminal holds they deliver the message to it as `send` does
  and say so.
- `--wait` on a thread with no seat record watches the job the wake started
  (`poll_until_done` on its short) and prints the reply from the session's
  transcript (`transcript_reply`), writing no seat record. A watcher that
  expires says how to read the reply later, as for a seat.
- `SendDelivery` applies `stale_hold` under the delivery lock to each event
  its batch would carry: a stale one is left out of the text and settled
  `recorded` in the writer's order, never ahead of an owed event before it
  (the tech-debt row "A direct send carries its writer's stale held text",
  closed here and removed from the file).
- X3: `lifecycle` writes `wake` and, when it is `held`, `why`;
  `publish_state` writes the `state` again when either changed. `why` is
  the reason `hold_for` answers, else `failed` while the record's
  `waking.failed` is above zero, else, on a machine whose policy is
  read-only, `read-only`: that last is what a sender on another machine
  must be told, and a sender on the machine itself is not told it.
- A sender's words are §4's, and a thread's machine that published nothing,
  or `held` with no `why` (a machine on 1.51), is spoken of in 1.51's words.

**Does not touch:** the guide, the skill, the spawn preamble (M5), the two
stores, `seat add`, a fresh `fill`, `spawn`.

**Proves:** G2 items 2 and 5, and items 1, 3, 9 and 10 through the verbs
and in a sender's words. Its tests pin: each verb against a stopped, a
running, a not-woken (each reason) and an ended thread of each kind, with
its exit code and its line; `--wait` printing the woken session's reply;
the line a remote sender reads for each published value, from a second
registry over the suite's git mirror; a direct send after a hand-off
leaving the stale event out; and the three send paths with two and five
senders onto one stopped thread, every message in the woken session exactly
once.

### M5 — What sessions are told, older copies, several senders, and the acceptance

**At its end:** the guide, the skill, the spawn preamble, `sminos help` and
the nested `CLAUDE.md` files say what is true after T2: a stopped session is
woken by an addressed message, when it is not, and what a woken session is
told. sminos 1.51.0 and 1.27.10, run from a plugin cache against a store
this code wrote, start no process for a human-opened thread and lose no
message this code held. The reproductions of T1's attack on the held
guarantee, carried over to the wake, pass. The acceptance has run on a real
engine. The version is bumped.

**Touches:** `sminos/skills/sminos/SKILL.md`, the guide text and the spawn
preamble in `S/sminos.py`, `sminos/CLAUDE.md`, `S/CLAUDE.md`,
`sminos/README.md`, `docs/whats-inside.md` where it describes a stopped
session, `sminos/tests/test-older-cli.sh`, a new
`sminos/tests/test_wake_senders.py`, `docs/doperpowers/TECH-DEBT.md`, the
version files through `scripts/bump-version.sh`.

**Interfaces:** consumes all of them; exposes none.

**Decisions:**

- The changed sentences and the opening line go through
  doperpowers:writing-skills with a small evaluation (X6): a woken session
  must act on the message, must not address its human as though they were
  watching, and must not treat the line as a peer's words. A word of §2's
  line or §4's lines that the evaluation changes is recorded in the Decision
  Log and in the composite's holder's hands before the merge.
- The several-senders suite is written from the scripts T1's verifier left
  (their shapes are in T1's plan, Decision Log, "The verification of the
  held path"): one store and two registries over a git mirror; one, two and
  five senders; `say`, `send` and a send from another project; each against
  a thread that is woken, one that is held for each reason, one whose wake
  fails once and then succeeds, a hand-off and a `/clear` between the send
  and the wake. Each asserts every message in exactly one conversation
  exactly once, or held with its mark, or settled with the reason its sender
  was told.
- The live pass runs under a scratch `HOME` and a scratch `SMINOS_HOME`
  (sminos reads the engine's session records under the home directory beside
  the configured one), in a terminal multiplexer of its own, on the cheapest
  model, and removes every job it made (`claude rm`). What it cannot observe
  on one Mac is said as not verified, not passed.
- The tech-debt rows of "sminos threads" are read against the wake: the
  direct send's row leaves; each of the others gets a sentence saying
  whether a wake's push meets it.

**Does not touch:** behaviour. A defect the suites or the live pass find is
fixed in the milestone that owns the code, by that milestone's executor
continued, and reviewed there.

**Proves:** G2 items 1 to 10 on a real engine as Concrete Steps lists them,
parent acceptance lines 3 and 4, and that every suite that passed before
passes (parent line 8) with the tests that pinned the hold of a human-opened
thread changed to pin its wake.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-threads-t2`).

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_wake.py
    python3 -B sminos/tests/test_threads_stopped.py
    python3 -B sminos/tests/test_threads_branch_b.py
    python3 -B sminos/tests/test_wake_senders.py
    bash sminos/tests/test-older-cli.sh <path to an older sminos launcher>

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites,sminos-idle,sminos-mods,issue-tracker,board-api,shell-lint,repo-checks

and in M5 `version-bump` too. Expected: one `PASS` line per gate, then
`GREEN` and the run's address. A `FAIL` that the base also shows, or one a
recorded reason names, is not this change's; any other is diagnosed, not
run again.

**M5, the acceptance on a real engine.** In a scratch tree, with `HOME`,
`CLAUDE_CONFIG_DIR` and `SMINOS_HOME` inside it, the plugin loaded from the
worktree, two scratch repositories A and B, and a scratch daemon
(`sminos daemon run --interval 5`):

1. Open B in a terminal on a model that is not the settings' default and in
   `auto` mode, run one turn, exit. `sminos list --stopped` shows B
   `stopped`. From A: `sminos say "@B reply with the word woken"`. Expect A's
   output to say B was woken; within two minutes `claude agents --json --all`
   lists one job whose `sessionId` is B's; B's transcript holds one new
   prompt that begins with the opening line and names the mode and the
   model of B's last turn; no other session id exists under the scratch
   config directory. `claude --resume <B>` in a terminal attaches to that
   process (one process by `ps`). (G2.1, G2.8 when A and B are different
   directories.)
2. Send B a second message after its process has ended. Expect a wake with
   no flag in the engine's argument vector (the stub's log in the suite; the
   job's row unchanged here) and the same id. (G2.4)
3. Open C in `plan` mode, run a turn, exit. `sminos say "@C …"` from A.
   Expect: no job for C, A's output saying C is stopped and not woken
   because its last turn ran in a mode that asks for approval, and the
   message in C's next turn when C is reopened by hand. Repeat with C's
   directory moved away (the `cwd` line). (G2.2, parent line 4)
4. With B open in a terminal, send B a message. Expect it in that terminal's
   conversation and no new job. (G2.3)
5. From two shells at once: `sminos say "@B one"` and `sminos send B two`
   while B is stopped. Expect one job, no copy, and both messages in B's
   transcript. (G2.6)
6. `sminos resume B "…" --wait` while B is stopped. Expect B's reply
   printed. `sminos fill B "…"` (fresh) is refused. (G2.5)
7. A worker that fails before it starts. In the suite this is the stub's
   `STUB_FAIL_WORKER`. On the real engine it is run only if
   `wake-spike-2.md` (question 5) names an option among those `first_flags`
   passes that makes a worker fail before it starts; expect then the message
   held with `failed`, no row for B afterwards, and the daemon's next
   attempt passing flags. Otherwise G2.7 rests on the suite and the report
   says so. (G2.7, G2.10)

What each step printed is kept in the controller's report beside the
commands.

## Interfaces and Dependencies

### §1. What the wake reads (`S/sminos_wake.py`)

    UNREADABLE = object()
    def row_of(session) -> dict | None | UNREADABLE
        # The engine's row of the session: <its config dir>/jobs/<first eight>/state.json whose
        # `sessionId` is the session. None: a `jobs` directory exists and holds no row for it.
    def row_options(row) -> list[str]          # the row's `respawnFlags`, [] when it has none
    def last_turn(session) -> {"mode": str, "model": str}     # "" for what the tail does not hold
    def asks(mode) -> bool                      # default, manual, plan, acceptEdits
    WHY = ("config", "transcript", "cwd", "protected", "mode", "failed", "read-only")
    def not_woken(record, session) -> str       # "" or one of the first five of WHY; no lock taken
    def wake_due(record, marked, now=None) -> bool   # §3's retry rule, from the record's `waking`

`not_woken` reads the record it is given and the files it names and nothing
else; it never reads the engine's job list. `sminos_threads.hold_of(session,
fresh)` is its one caller in delivery: `""` when a process holds the session
or the thread would be woken, else the reason.

### §2. What a first wake passes, and what a woken session reads

    def wake_argv(session, text, flags) -> list[str]
        # ["--bg", "--resume", session, ...] with the message where wake-spike-2.md's question 11 puts it
    def first_flags(record, turn, ceiling) -> (list[str], list[str])   # (flags, option names not carried)
    def opening_line(first, mode, model, turn_model, not_carried, human) -> str

The opening line is one paragraph, followed by an empty line and then the
frame the caller built, unchanged. Its text:

    [sminos] You were woken in the background by the message below. Your human is not watching this session. You run in <mode> mode on <model>.

When the mode or the model is not known, that clause reads `under your saved
options`. A later wake whose row names another model than the last turn ran
on adds: ` Your last turn ran on <turn_model>; a background run keeps the
model it was first started with.` A first wake of a human-opened thread
adds: ` This is your first run outside the terminal you were opened in: the
environment variables of that terminal are not set here.` and, when
something was not carried: ` Not carried from its launch: <option names,
comma-separated>.`

### §3. The wake

`resume_session` (or its core) is the wake. Called with the delivery lock of
the addressed session held by its caller when the message is a log event.

**Its steps,** in order, with what each reads:

| # | Step | Under |
|---|---|---|
| W1 | Take the wake lock, `resume_lock_taken`'s bounded poll | — |
| W2 | Read again: the record (its `current` is the session, not ended, no open entry), `not_woken`, and E5's three signals for the session | the wake lock |
| W3 | Stop a finished job's row the engine still lists for the session (today's rule) | the wake lock |
| W4 | Read the row. A row: no flag. No row, or unreadable without `waking.saved`: `first_flags`. Unreadable with `waking.saved`: no flag | the wake lock |
| W5 | Launch from the thread's directory with `launch_env` as today | the wake lock |
| W6 | Read the engine's answer (the banner and the three notes of E14) | the wake lock |
| W7 | Confirm: the job's row names the session and has not failed | the wake lock |
| W8 | Settle (`on_launched`), lift the stop mark (`stop_seen`), clear `waking`'s failure, and for a seat write its launch fields | the wake lock |

**The table.** What W2, W6 and W7 find, and what follows. "Deliver live" is
the caller's push to the process that holds the session, when its inbox
answers, else `held:starting`.

| # | Found | Done | Outcome |
|---|---|---|---|
| 1 | W1: the sweep holds the lock past the wait | nothing | `held:sweep` |
| 2 | W1: another launch holds the lock | nothing | `held:in flight` |
| 3 | W2: the thread ended | nothing | `recorded` (its end settles it) |
| 4 | W2: an open journal entry | nothing | `held:pending` |
| 5 | W2: a reason of `not_woken` | nothing | `held:<reason>` |
| 5a | W2: the wake is not due (the retry rule below) | nothing | `held:failed` |
| 6 | W2: a process holds the session, or a signal cannot be read | nothing | deliver live |
| 7 | W6: a copy, "is open in another Claude Code process" or "is already running in the background" | `claude rm` the copy; nothing remembered | deliver live |
| 8 | W6: a copy, "keeps its own saved options", flags having been passed | `claude rm` the copy; set `waking.saved`; from W2 once more, with no flag | as that second pass ends |
| 9 | W6: no short, a non-zero exit, a copy for any other cause, or row 8 a second time | a copy removed; `waking` failure noted | `held:failed` |
| 10 | W7: the job failed and no process holds the session | on a first wake `claude rm` the job (E9); `waking` failure noted | `held:failed` |
| 11 | W7: no row for the short within the poll | as today (`pending_short` for a seat) | `woken?`, settled |
| 12 | W7: the row names the session and has not failed | W8 | `woken`, settled |

Every outcome that begins `held:` leaves the event owed with no attempt
counted, and `held_decided` marks it and every addressed event of its writer
behind it, as T1 marks a hold. `held:sweep`, `held:in flight`,
`held:pending` and `held:starting` end at the next pass that finds them
gone; the daemon is nudged.

**Linearization points.** A wake is ordered against a sweep, an end and
another wake by the wake lock's acquisition; against a process that takes
the session by the engine's own answer at W6 (rows 7 and 12 are the two
orders); and its message is settled, under the delivery lock its caller
holds, only at W8 or row 11.

**The retry rule** (`wake_due`). A wake is due when the record's
`waking.failed` is zero or absent; or when the event that would be pushed
has no mark yet (a new message is one attempt, whatever `waking` says); or
when `failed` is below `WAKE_TRIES` and `WAKE_RETRY * 2 ** (failed - 1)`
seconds, at most `WAKE_RETRY_MAX`, have passed since `waking.at`. A verb a
person or a session runs on purpose (`resume`, `fill --resume`, `send`) is
always due. So the daemon's passes are what the schedule bounds. `WAKE_RETRY = 60`, `WAKE_RETRY_MAX = 3600`, `WAKE_TRIES = 5`,
each read from an environment variable of the same name with `SMINOS_` in
front, for tests. At `WAKE_TRIES` the daemon writes one line in
`daemon.log` naming the thread and the last failure.

### §4. Whether a thread is woken, as its machine says it (X3)

On a stopped thread's `state` event: `wake`, `"woken"` or `"held"`, and with
`"held"` the field `why`, one of `WHY`. Read by `wake_of(member)`, which
answers `"woken"`, `"held"`, `"ended"` or `None` as today, and
`why_of(member)`, the reason or `""`.

What a sender reads, `<M>` the thread's machine when it is another:

| `why` | The line, after `recorded and held[ on <M>]: the session is stopped and is not woken: ` |
|---|---|
| `config` | `it runs under another config dir` |
| `transcript` | `no conversation of it is on that machine` |
| `cwd` | `its directory is gone` |
| `protected` | `its directory is in a folder macOS protects, where a background launch would stop at a prompt for its human` |
| `mode` | `it runs in a mode that asks for approval` |
| `failed` | `waking it failed, and its machine tries again` |

each followed by `; it is pushed when a process of it runs again before it
ends (three days stopped, or a retire), else it stays in the log`. For
`read-only` the whole line is `recorded: <M> admits nothing from another
machine, and refuses it there`. For `held` with no `why`, 1.51's
`held_line`. For `woken` from another machine, `woken_line` as today. On the
thread's own machine a wake that succeeded prints the outcome word `woken`
where `sent` is printed for a live session, and `resume`, `fill --resume`
and `send` print the line they print for a seat today.

A verb that starts nothing exits 4 after `nothing was started: ` and the
same reason.

### §5. The record's field (X1)

`waking`, absent or an object, on either kind of record, written only by
`sminos_threads.py` through `update`:

| Key | Meaning |
|---|---|
| `saved` | `true` once the engine answered that the session keeps saved options where its row could not be read (table row 8) |
| `failed` | wakes failed in a row |
| `at` | when the last one failed |
| `said` | the last failure in a few words, for `daemon.log` and nothing else |

    def wake_failed(thread_id, said, lock_until=None)   # failed += 1, at, said
    def wake_done(thread_id, saved=None, lock_until=None)   # failed, at, said removed; saved set when given
    def wake_forget(thread_id, lock_until=None)   # the whole field removed: sminos ran `claude rm` on the session's row

`stop_seen` (a process holds the session) removes `failed`, `at` and `said`
with the stop mark. `waking` belongs to the occupant: it is dropped when the
thread's current session changes, as `stopped` is. `sminos list --json`
exports none of it.

### §6. The stub

The stub of `run-sminos-tests.sh` keeps a row per background session under
`$STUB_STATE/jobs/<first eight>/state.json` with `sessionId`, `cwd` and
`respawnFlags`, and the tests' config directory points there. `--bg --resume
<id>` with flags and no row: the same id, the row written with the flags.
With flags and a row: a copy, and the engine's third note. `rm <short>`
removes the row. `STUB_HELD=<id>` makes a resume of that id answer with the
first note and a copy. `STUB_FAIL_WORKER=1` answers the banner, exits 0 and
leaves a failed job with a row that has no flags. The Python suites get a
helper of the same four behaviours over `run_claude_bg` and `poll_uuid`.

### Dependencies

No new library. The engine is Claude Code 2.1.329 or the version
`wake-spike-2.md` was measured on; the row's layout is the engine's own and
is read defensively (§1). devcloud is not touched.

## Surprises & Discoveries

None yet.

## Decision Log

- 2026-11-20 — **Verification.** The plan is reviewed before it is handed
  over by the `doperpowers:adversarial-reviewer` agent, once for the design
  it fixes (the table, the locks, older copies) and once for buildability.
  Each milestone is reviewed at its close by the execution loop's reviewer,
  three reviews at most (the owner: "리뷰도 3회로 둬도됨"). The range M1 to M4
  is reviewed whole by the composite's holder at the frontier, through
  doperpowers:review-code at the panel rung (xhigh) with the four lenses
  named in Plan of Work, a second whole reading if the first confirms more
  than ten, and three rounds at most. The branch's end has no further whole
  review: M5 adds text and tests, read by its own review. The held guarantee
  under the wake is attacked by M5's several-senders suite, written before
  the acceptance run.
- 2026-11-20 — **Decided in this plan** (also in the composite's Decision
  Log, as T2's): the daemon's retry schedule and bound (§3); `waking` on the
  record (§5); a wake's uncertain confirmation is settled as today (table
  row 11), since a second launch of a message the engine accepted can
  deliver it twice or start a copy, and the case needs the job list to lag
  the launch by the whole poll; the reasons' order (§1); a thread whose
  transcript holds no turn is woken with what its launch recorded, or with
  no mode and no model flag, and its line says `under your saved options`.
  *Alternative rejected for the retry: none, a failed wake waiting for the
  next message or its human.* A message from another machine has no sender
  watching the failure. *Alternative rejected: the daemon alone wakes, and a
  sender's CLI only records.* It would put every write behind one process,
  and it loses `--wait`, the wake on a machine with no daemon, and D2's
  rule that a sender's CLI wakes under the lock; the lock and the table
  carry the same guarantee.

## Outcomes & Retrospective

Pending — written at finish.
