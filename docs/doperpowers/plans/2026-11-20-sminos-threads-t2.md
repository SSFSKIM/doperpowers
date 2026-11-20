# sminos threads, T2 — the wake: execution (2026-11-20)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **T2** (The wake). **Parent pin:** `main` `9f9475e5`, that file's blob
> `22a9ef4b376f1050fd8e41e4f8b591e55144f3c2`. The child's section there is its
> spec, D2 its design (binding), X1, X3, X6 and X7 its contracts. This document
> carries the constraints and the milestones and nothing of the design. Read
> before M1: the composite's Purpose, Terms, D1 (the paragraphs Lifecycle and
> Verbs that start a process), D2 whole, D7, the engine facts E1 to E24, the T2
> section, X1 and X3, the Risks entry "The store has no writer in charge", and
> the Decision Log's entries of 2026-11-20; the research notes
> `docs/doperpowers/research/2026-11-17-sminos-channels/wake-spike.md` and
> `wake-spike-2.md` (the engine, measured; the second is on the engine this is
> built for); T1's plan `docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`,
> its Interfaces §1 (the record), §5 (the hold) and §6 (transitions, older
> copies); and `docs/doperpowers/TECH-DEBT.md`, section "sminos threads".

After this child a message addressed to a stopped session starts that session
again in the background, whoever opened it. A session its human opened in a
terminal and closed is woken under the same session id and the same name, in
the permission mode and on the model of its last turn; the message then
reaches it as it reaches any running session, opened by a line saying that it
runs in the background and that its human is not watching. Its human can
attach to it with `claude --resume <id>`. A message that cannot wake its
session is held, its sender is told why, and it is pushed as soon as a
process of that session runs. How to see it working is T2's acceptance in the
composite (G2, eleven items), proved as Concrete Steps maps it.

## Progress

- [x] (2026-11-20) The direction ruled by the owner (one wake path) and folded into the composite (PR #574).
- [x] (2026-11-20) The engine read again on 2.1.329 (`wake-spike-2.md`, E17 to E24) and this plan's first draft reviewed twice; the composite's D2 revised (the wake carries no message, PR #575) and this plan rewritten on it.
- [x] (2026-11-20 12:20Z) M1 — What a wake reads and says, the record's field, and a test engine that can be woken. Commits `94b98e29`..`2ac241c3`; three reviews, the last item read by the controller; gates GREEN on `2ac241c3`.
- [x] (2026-11-20 14:55Z) M2 — The wake: `resume_session` starts a process and pushes to it; transitions take the wake's lock. Commits `d52f01b0`..`e2fe7c64`; three reviews, the last fix read by the controller; gates GREEN on `e2fe7c64`.
- [x] (2026-11-20 19:35Z) M3 — Delivery wakes every stopped thread, and holds what it cannot push. Commits `ca38e7f7`..`b482b4ce`; three reviews, the last fix read by the controller; gates GREEN on `b482b4ce`.
- [ ] M4 — The verbs, what a sender is told on any machine, and the direct send.
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
- **The inbox** is the socket the engine serves for a running session
  (`messagingSocketPath` in the engine's record of the process), which
  `push_live` writes a frame to; a session is **live** when a process holds
  it and its inbox answers (`peer_for_session`).
- **A first wake** is one for a session that has no row; **a later wake**
  finds a row. A row is the engine's `jobs/<first eight of the id>/state.json`
  under the session's config directory, naming the session in `sessionId`.
- **Held** means owed and not pushed: the event stays in the log, its mark
  `[seq, thread]` is in the delivery record (T1), no attempt is counted, and
  it is pushed when a process of the thread takes it or settled when the
  thread ends.
- **A job** is a background session as the engine lists it
  (`claude agents --json --all`); its **short** is the id the launch prints.
- **The test engine** is §8's fixture: the `claude` stand-in of
  `sminos/tests/run-sminos-tests.sh` and its Python twin.
- **`S/`** is `sminos/skills/sminos/scripts/`.

## Constraints that bind every milestone

- **The composite has one writer,** the session that holds it. This
  document's controller records decisions and discoveries here and sends that
  session whatever touches the child's purpose, its acceptance, a contract or
  a binding decision; it never edits the composite.
- **What binds, by id.** D2 whole: "One path" (how a thread was opened
  selects nothing in the wake or in what is held) and "A wake starts the
  thread's process and carries no one's words". D1's rule for a held message
  (owed until pushed to the thread's own process or the thread ends; a
  recorded decision per event, never read from a process's state or a
  clock). D7 whole. X1 (a field is added only through `sminos_threads.py`),
  X3 (T2 owns it; Interfaces §5 is its text), X6, X7.
- **No launch carries a message.** Every `claude --bg --resume` sminos runs
  ends at the session id or at its flags. A message reaches a woken session
  through the path that delivers to a live one, and is settled as that path
  settles it; a wake settles nothing. From M2 the test engine records a
  launch that carried a message as a failure of the test that made it.
  A consequence, wanted: a message to a stopped session arrives as a message
  from outside, where until T2 a stopped seat read it as its launch's
  prompt, in its user's place.
- **One place starts a process for a stopped thread:** `resume_session`,
  extended. No second launcher is written beside it, for either kind of
  thread, and nothing calls `run_claude_bg` with `--resume` but it.
- **Everything a wake decides, it reads under the wake lock,** and every
  write a wake makes is made while it holds that lock and names the thread
  and the session it was decided for (Interfaces §3). What was read before
  the lock was taken (the member, the record, whether a process holds the
  session, the row) chooses only whether to try. T1's branch review found
  most of its 82 defects between a check and its write.
- **Lock order,** outermost first: the delivery lock; the seat's lifecycle
  lock (`lock_seat`, a record in the seat store only); the wake lock; a
  store lock (`.metalock`, `threads/.lock`); a log's lock. Two exceptions
  exist today and stay bounded, never blocking: a direct send to a seat
  takes the lifecycle lock before the delivery lock (`send_to_seat`), and
  the sweep takes the wake lock before a settlement's delivery lock. So,
  while a delivery lock is held, the lifecycle lock is only tried, and the
  wake lock is only polled for `resume_lock_taken`'s bounded wait; finding
  either busy is a hold with no attempt counted, never a failure.
- **Nothing is signalled that is not the session's own job.** `claude stop`
  and `claude rm` are run only on a short whose row names this session, or
  on a copy this wake's own launch just made. A session a terminal holds is
  delivered to or left; it is never stopped.
- **Older code on the same machine** keeps D7's two rules. A human-opened
  thread's record stays in the thread store, and a wake writes nothing about
  it into the seat store, so a copy from before T2 still starts no process
  for it. What an older copy may still do to what this code held is D7's
  accepted list, restated per version in M5; nothing here defends against
  it.
- **No event kind is added,** and nothing about a thread's wake leaves the
  machine but the field `why` on its stopped `state` (Interfaces §5). What
  `sminos_outcomes.report_held` sends for an outside event keeps its shape.
- **`S/sminos.py` is one file of seventeen thousand lines.** The parts of the
  wake that read and compute (the row, the last turn, the flags, the line,
  the reasons) go in a new sibling module, `S/sminos_wake.py`; `sminos.py`
  gets the changed seams. `origin/main` is merged before M1 and before the
  final push.
- **The idle daemon stays cheap.** Whether a stopped thread is woken or held
  is computed from file stats and cached by them; a transcript is read only
  when its stat changed, and only its tail. No per-tick duty launches
  anything, lists the engine's jobs for a thread nothing is owed to, or reads
  a transcript whole. The `sminos-idle` gate is the check.
- **Tests are hermetic,** as in T1: the test engine, a temporary `HOME` and
  `SMINOS_HOME`, invented names. The repository is public: no hostname,
  account, project id or local path enters a test, a comment or this
  document.
- **Tests vary what T1's did not:** the number of senders (one, two and
  five), the number of messages from one sender (one and three), the three
  ways a message is sent (`say` with a tag, `send`, and a message from
  another project), and the order of a wake against a sweep, a retire, a
  second wake and a reopening by hand. A guarantee tested with one sender
  and one message is not tested.
- **What a session reads keeps today's words** (X6): session, seat, member.
  "Thread" stays in code, records and event fields.
- **One change, one version.** No release is cut between milestones. The
  child merges as one pull request that leaves the repository releasable
  beside a machine on 1.51 (D7), with sminos's version bumped in it
  (`scripts/bump-version.sh --plugin sminos`, to 1.52.0 unless `main` has
  moved past it), and doperpowers's too, since M4 changes a script of that
  plugin (`skills/issue-tracker/scripts/_sweep_api.sh`).
- **Every milestone ends green.** The gates of Concrete Steps pass at each
  milestone's last commit. A test that pinned behaviour a milestone changes
  is changed in that milestone, to pin the new behaviour and never deleted
  for failing; a consumer of a function whose meaning a milestone changes is
  changed in the same milestone.

## Plan of Work

The wake is `resume_session` made to serve any thread, and made smaller: it
starts the session's process and hands over nothing. M1 builds what a wake
reads and says, as functions with no effect, and a test engine that can be
woken and pushed to. M2 makes `resume_session` the wake, for a seat first:
a seat's resume starts its process with no message and then pushes the
message as to a live session, and every transition that ends a thread or
changes its occupant takes the wake's lock. M3 changes delivery for every
thread: a stopped thread its human opened is woken where it was held, and
what cannot be pushed is held for either kind. M4 brings the verbs onto that
path, publishes why a thread is held, and closes the direct send's limit.
Between M4 and M5 the range is reviewed whole by the composite's holder. M5
changes what sessions are told, runs older copies and several senders
against the result, and runs the acceptance on a real engine.

**The frontier review.** When M4's review is clean the controller pushes the
branch and returns to the composite's holder with the word `FRONTIER`, the
range (`git merge-base origin/main HEAD` to `HEAD`) and nothing else to
decide. The holder reviews that range through doperpowers:review-code at the
panel rung, with lenses given, not derived: lock order and what is read
outside a lock it is acted on under; an older copy on the same store; the
milestones' interactions (a wake against the sweep, a retire, a hand-off, a
`/clear`, a refill); and what leaves the machine. Its confirmed findings are
fixed on the branch by the holder's fix wave, and the range is read whole a
second time if the first reading confirms more than ten. The controller is
then continued for M5.

### M1 — What a wake reads and says, and a test engine that can be woken

**At its end:** `S/sminos_wake.py` exists and answers, for any session on
this machine, whether the engine holds a row for it, which mode and model its
last turn ran under, which flags a first wake passes, what the opening line
says, and for which reason, if any, the thread is not woken. The thread
record can hold `waking` (§7), and a launch's capture notes the names of
options whose values it did not keep. Nothing calls any of it from a delivery
path, so no behaviour changes. The test engine (§8) can be woken with no
message: it starts a process the suites see as running the session, with an
inbox that records each frame pushed to it and can answer one. In M1 only
`test_wake.py` uses it that way; the shell stub still accepts a launch with
a message, which every resume makes until M2.

**Touches:** `S/sminos_wake.py` (new), `S/sminos_threads.py` (`waking` and
its writers; a new `launch_dropped` beside `launch_options`, whose list
contract its callers and tests keep; `launch_of`; `note_launch_of` and
`spawn_fresh` in `S/sminos.py` where they note a launch),
`sminos/tests/run-sminos-tests.sh` (the stub, and `run_suites`' list), a new
`sminos/tests/wake_engine.py` (the Python twin) and `sminos/tests/test_wake.py`
registered in the runner, `S/CLAUDE.md` for the new module.

**Interfaces:** exposes §1, §2, §7, §8. Consumes T1's record (`get`,
`thread_of`, `update`) and `sminos_policy.machine_policy()` (the ceiling,
resolved to a mode).

**Decisions:**

- The row is read with no lock and believed only for the moment; it is read
  again under the wake lock at each wake (D2, step 2). A file that does not
  parse, one whose `sessionId` is another session's, and a config directory
  with no `jobs` directory all read as `UNREADABLE`, never as "no row": the
  difference decides whether the copy answer is the fallback.
- The last turn is read from the transcript's tail, backwards. A reading
  bounded at 4 MiB, cached by the transcript's device, inode, size and
  mtime, serves the daemon's ticks; each of the mode and the model is then a
  value, `""` (the transcript was read to its start and holds none) or
  `None` (not found within the bound). A wake that is about to launch
  resolves a `None` by reading on to the start, once, and so does the
  sweep when it marks a thread stopped (what it publishes of the thread
  must be what a wake would decide); the whole reading is cached by the
  same stat, so no tick repeats it. A hook's row
  (`requestId` null, a `message.id` beginning `msg_hook_`) is no turn, and
  the mode is the `permissionMode` of the last prompt row, never a
  `permission-mode` metadata row (E14, `wake-spike-2.md` §3).
- The mode a wake would run under is the row's `--permission-mode` when a
  readable row has one, else the last turn's. A thread is not woken for
  `mode` when that mode or the last turn's asks for approval. The modes that
  ask are `default`, `manual`, `plan` and `acceptEdits`; any other value, an
  unknown one included, does not ask (the owner's ruling: modes are not
  guarded). A mode still `None` (a tick before the sweep's whole reading)
  does not ask; the whole reading decides.
- The flag's value for a transcript's mode is the mode itself, except that
  `default` is passed as `manual` (E24).
- The flags of a first wake, in this order: `--permission-mode`, `--model`,
  `--effort`, `--settings`. The mode is the last turn's, lowered to the
  policy ceiling when above it by `sminos.PERMISSION_MODES`' order (a mode
  not in that order is passed as it is), and `bypassPermissions` becomes
  `auto` unless the user's settings in the session's config directory hold
  `skipDangerousModePermissionPrompt: true` (E22); with no mode known, the
  launch's recorded `--permission-mode`, else no mode flag. The model is the
  last turn's, else the launch's, else none. `--effort` is the launch's.
  `--settings` is the launch's when its value is a file that exists, a
  relative path read against the launch's directory. Nothing else is
  passed: not `--add-dir` (E22), not `--output-style` (E12), no name. The
  vector has no positional argument after the session id.
- What was not carried is a list of option names, never values: every
  option of `launch.options` that was not passed, and every name in
  `launch.dropped`. T1's `launch_options` drops an option whose value is
  inline JSON or names a session, name and all; `launch_dropped(argv)`
  returns those names, kept as `launch.dropped` from M1 on. For a record
  with no `dropped` (written before M1) or no `options` (a launch that
  could not be read), the line says in general words that options of its
  launch may not be carried (§2).
- The reasons (`not_woken`) are checked in a fixed order and the first that
  holds is the answer: `config`, `transcript`, `cwd`, `protected`, `mode`.
  Each is a fact that stays until something outside sminos changes it.
  `read-only` is not among them: it is decided per event, for an outside
  event, where `deliver_next` decides it today. Nor is `failed`, which is a
  schedule (§4). `protected` holds on macOS alone, for a record whose
  `opened` is `human` and whose directory is in a protected folder
  (`protected_folder`), whichever process asks (D2: a launch there by the
  daemon stops at a system dialog). `cwd` is the record's launch directory,
  or for a record in the seat store `seat_cwd`, missing or not a directory;
  one this process may not look at (`read_refused`) is taken on its word, as
  `resume_session` does today.

**Does not touch:** `resume_session`, any delivery path, any sender's
output, the guide or the skill.

**Proves:** nothing of the acceptance alone. Its tests pin: a row found, not
found and unreadable in each of its three forms; the last turn read from a
tail that ends in hook rows and metadata rows, from a transcript whose last
prompt lies beyond the bound (`None` on the bounded reading, the value on
the full one), and from one with no turn; each mode's flag; the flags for a
launch with every kept option, with a settings file that is gone, with a
relative settings path, with a mode above the ceiling, with
`bypassPermissions` with and without the accepted disclaimer, and with
nothing recorded; the not-carried list with a dropped inline option;
each reason and their order, `protected` off macOS included; `wake_due` at
each count and time; `waking` ignored when it names another session; and the
test engine's behaviours of §8, each driven through the `claude` argument
vectors `wake-spike-2.md` records, its turn writer included (a frame
pushed, its marker in the transcript, a reply, idle).

### M2 — The wake

**At its end:** `resume_session` is the wake of §3. Called for a seat, as
every caller calls it today, it starts the seat's session with no message,
under the wake lock, with flags only on a first wake, and then pushes the
message to the process it started as to a live session, the opening line
first; a copy the engine made is removed, and a launch that failed is told
from one that succeeded. `sminos resume` and `fill --resume` record their
message as `send` records one before anything is launched. From this
milestone no launch in any suite carries a message. Called for a human-opened thread's record (by this
milestone's tests alone; no delivery path does yet), it wakes it under its
own id and name with a first wake's flags. A retire, an end, a hand-off,
an absorption, a refill and a return of a thread wait for a wake of it in
flight, and a wake finds what they wrote.

**Touches:** `S/sminos.py` (`resume_session` and its callers' handling of
what it answers: `push_member`'s seat branch, `send_to_seat`'s `resume`,
`cmd_resume`, `cmd_fill`; `copy_started`; `wait_socket_turn`;
`note_launch_of`; the `begin` callers `end_human`, `retire_member`,
`hand_off`, `refill_seat`, `join_seat`, `end_by_rule`),
`S/sminos_threads.py` (`begin`, `_hold`, `stop_seen`), `S/sminos_daemon.py`
(`resume_lock_out`, and the sweep's calls that begin an end under it),
`test_wake.py`, the tests that pin a seat's resumed prompt and
`resume_session`'s answers for a copy and a held session
(`run-sminos-tests.sh`'s resume and `fill --resume` cases,
`test_threads_stopped.py`'s resume against the sweep, `test_reach_gate.py`'s
resume, `test_threads_ended.py`'s returns), the shell stub's switch to
refusing a launch with a message, `S/CLAUDE.md`.

**Interfaces:** exposes §3 (the wake, its table, its results) and the lock
rule for transitions. Consumes §1, §2, §7, §8.

**Decisions:**

- `resume_session` takes a thread's record where it takes a seat today, or
  is split into a core that takes the record and thin callers; which is the
  executor's, under the constraint that one function launches. What is a
  seat's alone stays with the seat: its lifecycle lock, `meta_set`'s fields
  (`status`, `short`, `turns`, `pending_short`), `join_seat`, a retired
  seat's return by `fill --resume`. A human-opened thread's wake writes none
  of them: its process's own hooks restate it, as they do when its human
  reopens it.
- After the wake, the message a caller brought is pushed as a live push is
  made today (`push_live`, with its reach check, its bridge route for an
  owner's event and its outcomes), by the caller that brought it; the wake
  itself takes no message, no event and no `on_launched`. Before that push
  the caller reads the member again as a live delivery does at its start
  (its membership in effect, its thread's end, the session its thread
  holds): a retire or a hand-off may have begun since the wake returned.
- `sminos resume` and `fill --resume` bring a bare text today. From M2 each
  records it first as `send` records a message (`record_send`: an addressed
  event in the session's project log, with its id in the frame), so that it
  is durable before a launch and has an id a waiter can look for; it is then
  delivered as `send` delivers. In M2 a wake that does not make the seat
  live leaves that event as a failed `send` to a stopped seat leaves one
  today, and the verb exits as it does today; M3 and M4 give it the hold.
- **Waiting.** `--wait`, for a seat as for any session, waits for the
  message's id in the transcript and then for the turn that holds it to
  end, and prints the assistant text that follows that prompt up to the
  next one; a busy job alone is no evidence, since an idle woken job is
  listed before any turn. The seat's reply file and `status` are still
  written under their guard, for `sminos reply` and the list; the waiter
  does not print from that shared file. A seat's `turns` and its `working`
  status are written when a message was pushed, not when a process was
  started, and a wake writes no `pending_short`. `finish_turn` stays what a
  fresh `spawn` and `fill` use.
- The reach checks `resume_session` makes today before a launch stay ahead
  of the wake, and consume nothing: the endpoint's one-use permit is spent
  by the live push that follows.
- A verb's own steps stay ahead of the wake and are not part of it: the
  refusal of a vacant or retired seat, and the stop of a live background
  turn that `sminos resume` asks for. The wake itself stops only a job the
  session's own row names that the engine lists as not stopped while no
  process holds the session (§3, W3).
- A copy is removed with `claude rm`, and the removal is checked in the job
  list; one that cannot be removed is stopped (`claude stop`) and said in
  `daemon.log`. `copy_started` today stops the short and fails; §3's table
  replaces it.
- From delivery (`quiet`), a wake that does not make a seat's session live
  answers in M2 as a resume that failed answers today (`failed:` with its
  attempt counted, `held:` for `ResumeBusy`); M3 turns these into holds for
  every thread at once. So the suites that pin the attempt limit for a seat
  stay as they are in M2.
- **Transitions take the wake lock.** An operation that ends a thread or
  changes the session that fills it (end, advance, absorb, return) opens
  its journal entry under the record's wake lock, for either kind of
  record. A `release` at a `/clear` does neither and does not take it: a
  hook that skipped it has nothing that replays it.
  - *What is read with it.* A retire and an end record what they saw of the
    thread's process (`ended.pid`), and `returns` brings an ended thread
    back for any process an end did not see. So the caller takes the wake
    lock before it looks for that process and holds it through `begin`:
    reading first and locking only the write lets a wake start a process
    the end then says it never saw.
  - *The hold is passed, not taken twice.* `begin` takes the lock unless
    its caller hands it the hold it has (`flock` on a second descriptor of
    the same file blocks its own process): the sweep's `resume_lock_out`,
    a retire's own early hold, and the wake's W8 (below). The lock is
    released before anything is settled; a settlement waits for a delivery
    lock, and the wake lock is never held across that wait.
  - *An absorption touches two records.* The reservation it puts on the
    record it will delete (`_hold`) is written under that record's wake
    lock, as the absorber's entry is under its own. Two wake locks are
    held together only in ascending order of thread id.
  - *An operation queued behind an open entry* (`next`) starts while that
    entry is open, so a wake finds an entry at every moment between the
    two; it relies on the table's row for an open entry, not on the lock.
  - *Waiting.* The lock is waited for until the caller's deadline
    (`lock_until`, else `SWEEP_WAIT`). Busy past it: a hook leaves the
    transition for the next reconciliation, which finds the same evidence
    again (the engine's record of a hand-off, a process holding an ended
    thread's session), and a verb exits 1 saying a wake of the session is
    in flight and nothing was changed.
  - *The file.* It is created when absent, for a human-opened record too
    (`resume_lock_out` opens it as it does a seat's), so that the sweep and
    a first wake meet on one file. A sweep run from a copy at 1.51 before
    any wake made the file takes no lock for that record; what follows is
    an end that a process then returns, which D7 accepts of an older copy
    run by hand.
- **A retired seat's return.** `fill --resume` is the one caller that may
  wake an ended thread, and only a spawned one's seat it named (`returns`,
  §3). The return is journaled as today, after the process is live
  (`join_seat` with `returns`), inside the wake's W8 and with its hold; a
  launch that fails leaves the seat retired and writes nothing. The verb's
  message is recorded after the return's entry is begun, since a return
  settles what was addressed before it.
- The third signal of E5, the bridge's socket for the session, is read
  beside the engine's records and the job list before a launch. A signal
  that cannot be read (the job list failing) is a held session, never a
  free one.
- `note_launch_of` keeps the record's `options` and `dropped` when the
  process that started is a background one (the engine's record says `kind`
  `bg`): a wake is not a launch its human made, and the next first wake
  reads the terminal launch's options.

**Does not touch:** `push_member`'s branch for a session with no seat,
`hold_of`, `hold_now`, the marks, any sender's words, `SendDelivery`'s
batch. A human-opened thread is still held after M2, and a seat's failed
wake is still counted.

**Proves:** G2 items 3, 4, 7, 8 and 11 against the test engine, for a seat
through delivery and the verbs and for a human-opened record by direct
call. Its tests pin every row of §3's table for both kinds of record; that
no launch carried a message, in every test of the suite; a seat's message
arriving once through the inbox, opened by the line, after its wake; the
name kept; the two orders of a wake against the sweep's stop mark; a retire,
a hand-off and an absorption of the woken record each paused after the
wake's W2, and a wake paused after their `begin`, each checked again after
one more reconciliation (a retire that reported success stays a retire);
a retire begun between a wake's return and its caller's push, pushed
nothing; a retired seat returned by `fill --resume` with older debt
settled and its new task pushed, and left retired by a launch that failed;
a `/clear` in a woken process while its launcher still holds the lock,
its alias released; a wake against a reopening by hand (the engine's copy
answer, the copy removed and gone from the job list, nothing remembered,
the message delivered to the terminal's process); a copy that cannot be
removed; a wake that finds an open journal entry, and one that finds the
record gone or filled by another session; a second wake while the first
holds the lock, counted by the test engine's launch counter; a failed first
wake leaving no row, with and without flags, and the next wake passing
flags; a row that was there before the launch never removed (an unexpected
copy, a timeout, a non-zero exit, each with a row in place); an unreadable
row answered with a copy, the copy removed, the wake made again with no
flag, and the next wake passing none; a seat's `--wait` printing the reply
to its own message when another sender's is answered after it; the directory a first wake is issued from;
and a launch that timed out with a process holding the session read as
live.

### M3 — Delivery wakes every stopped thread

**At its end:** an addressed message to a stopped thread wakes it,
whichever way it was opened. With the test engine: `sminos say` with a tag,
and a plain `sminos send`, to a closed human-opened session start it under
its own id with a first wake's flags and push the message to it with the
opening line; a later message is pushed to the process that is still up, or
wakes it again with no flag once that process has ended. Two deliverers that
wake one thread together start one process, and both messages reach it
once. A thread that is not woken, a wake that failed and a process that
takes no push yet each leave the message held, with its mark, for a spawned
thread as for a human-opened one, and it is pushed when a process of the
thread takes it. The daemon tries a failed wake again on §4's schedule. A
sender reads §5's words for each of these on the thread's own machine.

**Touches:** `S/sminos.py` (`push_member`, `push_event`, `deliver_next`,
`deliver_verdict`, `deliver_reach`, `deliver_say`, `held_decided`,
`held_owed`, `human_owed`, `words_unanswered`, `words_due`, `reach_due`,
`hold_for`, `hold_now`, `bound_peer`, `PushHeld`, `send_to_member`,
`send_to_seat`'s branch for a session its human opened and its failure
branch, `_send`'s choice of `hold_verb` for `send --wait`, the two
`HELD_HUMAN` answers left in `resume_session`, `held_send`, `held_record`,
`held_line`, `derive_refusal`, `derive_line`, `refill_seat`,
`refill_launch`), `S/sminos_threads.py` (`hold_of`,
`hold_now`, `_live_index`, `awaits_seat`'s callers), `S/sminos_daemon.py`
(`deliver_owed`, `held_reads`, `all_held`, its memory of a held pass),
`S/sminos_uplink.py` (`ask_words`, `queue_asks`), `S/sminos_outcomes.py`
where it names the hold (`closed_sessions`, `report_held`), the tests that
pin the hold of a human-opened thread and a seat's attempt limit for a
failed resume (`test_threads_stopped.py`, `test_threads_branch_b.py`,
`test_words.py`, `test_owed.py`, the core suite's delivery cases and its
literal held line), `sminos/tests/test-older-cli.sh` (its fixture),
`test_wake.py`, `S/CLAUDE.md`.

**Interfaces:** exposes §4 (holds, the retry rule, the line's delivery) and
the local half of §5 (the words). Consumes §3 and §7.

**Decisions:**

- `push_member` has one branch for a thread: a live session is pushed to;
  one no process holds is woken when the event is addressed, and `recorded`
  when it is for the live alone; after a wake the session is delivered to
  exactly as one found live at the pass's start, receipts included
  (`holder_push`'s rules for a live process), and one whose inbox does not
  answer yet is `held:starting`. A session that is no thread (lane B, a
  member an older copy joined unstamped with no record) is delivered to as
  today.
- `hold_of` and `hold_now` answer `""` when this machine delivers to the
  session or would wake it now, and a reason when it holds: one of
  `not_woken`'s, or `failed` while a wake is not due (§4). Every caller that
  read a true answer as "push nothing, ask nothing" stays right, the
  uplink's questions to the endpoint among them. Every caller that read a
  false answer and a missing process as "not live, refuse" is changed to
  wake: `send_to_member` records its message and delivers it through
  `deliver_next`, where it exits today, and `send_to_seat` does the same
  for a session its human opened that an older copy seated, holding where
  it calls `delivery.fail()`. `_send` keeps `send --wait` to a stopped
  human-opened session on `hold_verb` (recorded, exit 4) by asking whether
  it is stopped, not whether it is held; M4 makes it wake and wait.
- **Who the schedule binds** (§4). `deliver_next` takes `due`. The daemon's
  passes and the uplink's deliveries pass it false and follow the schedule.
  A sender's own call (`say` with a tag, `send`) passes it true for the
  call that wrote the event: one attempt, whatever the schedule says, and
  only `failed` is passed over, never a reason of `not_woken`, a gate or
  `read-only`.
- The constant `HELD_HUMAN` goes, with every comparison against it
  (`deliver_say`'s among them); the outcome is `held:<reason>`.
- `derive` keeps T1's rule by a predicate of its own: no engine is forked
  for a stopped session its human opened. It read that from `hold_for`,
  whose meaning changes here.
- `hold_for` reads spawned threads too, so its index (`_live_index`) holds
  the seat store's records beside the thread store's, under the same stat
  key.
- `human_owed`'s rule becomes every thread's: a marked event of a session
  that is the current one of a thread that has not ended, of either kind,
  is owed until pushed. `held_decided` marks an event, and every addressed
  event of its writer behind it, on every `held:` outcome, with the thread
  the wake was decided for.
- A refill settles what was held for the session it displaces, in its
  journal entry, as a hand-off's advance does (`settle`): a seat given its
  earlier occupant again holds no debt from before.
- The young-background wait (`awaits_seat` with `own` false) does not apply
  to a session that is the current one of a thread: a woken human-opened
  thread is a background process with no seat (its engine record says `kind`
  `bg`, `wake-spike-2.md` §9), and nothing waits for a seat to claim it or
  withholds its `joined`.
- The daemon remembers a pass that left everything held only for the
  reasons that are facts (`not_woken`'s), with every input they read in the
  memory's key; a hold for `failed` is remembered until the wake is due;
  `starting`, `in flight`, `sweep` and `pending` are never remembered, since
  an inbox that begins to answer and a lock that is released change no
  file's stat.
- `test-older-cli.sh`'s closed session is given a last turn in `plan` mode,
  so that this code still holds it and the suite's expectations of the
  older copy stand; M5 adds the cases where this code wakes.

**Does not touch:** `resume`, `fill`, `send --wait` aimed at a human-opened
thread (they still record, start nothing and exit 4, and the daemon then
wakes it), `send_to_seat`, `SendDelivery`'s batch, what `lifecycle`
publishes in `state` beyond what `hold_for` now answers, a remote sender's
line, the guide.

**Proves:** G2 items 6, 9 and 10 against the test engine, and items 1 and 2
for `say` and a plain `send` on the thread's own machine. Its tests pin,
with one, two and five senders and with one and three messages from one
sender: a stopped thread of each kind woken by an addressed event and not
by one for the live alone; every message in the woken session's inbox
exactly once; the line on the first frame after a wake, where a second
project's sender pushes before the wake has returned, and on no frame
pushed to a terminal that reopened the session; two wakes together from one
project and from two, one launch; each reason held with its mark for each
kind it applies to (a spawned thread's directory gone, another config dir
and no transcript: held, where they were `recorded`; `protected` for a
human-opened thread and a spawned thread in the same folder woken);
`read-only` for an outside event refused and for a local one woken; a
process that holds the session with no inbox, held and then pushed with no
file written between; a live inbox pushed to while a reason not to wake
still reads true, and during a failed wake's wait; the schedule of §4 from
the first failure to the hour's cap, a second and a third message from the
same sender inside it, and the line in `daemon.log`; a sender's own call
trying before the wake is due, and the daemon's replay of that same event
waiting; a wake of a session that became lane B refused, and one whose
lane or record cannot be read held and not settled; a marked event of a
spawned thread settled when the thread ends; a hand-off and a refill settling what was held,
and the refilled seat given its old session again pushing nothing old;
nothing asked of the endpoint for a held event, from the pass and from the
uplink's own queue; one permit serving a wake and the push after it; no
fork by `derive` of a stopped human-opened session; and a tick that
launches nothing and lists no job for a thread nothing is owed to.

### M4 — The verbs, what a sender is told on any machine, and the direct send

**At its end:** the verbs do what §6's table says for a thread of either
kind: `sminos resume`, `fill --resume` and `send --wait` aimed at a stopped
session its human opened wake it and push their message, and with `--wait`
print its reply to that message; aimed at one that is not woken they record
the message, start nothing, say why and exit 4; a fresh `fill` of it is
still refused. A sender on another machine reads whether the session's
machine wakes it or holds it, and why. `sminos reply` reads a session with
no seat. A direct send no longer carries an event its sender was told went
to no one.

**Touches:** `S/sminos.py` (`cmd_resume`, `cmd_fill`, `_send`,
`send_to_seat`, `SendDelivery`, `hold_verb`, `refuse_wait`,
`wait_socket_turn`, `cmd_reply`, `woken_line`, `remote_line`, `wake_of`,
`lifecycle`, `_member`, `who_lines`, `resolve_seat_or_opened`, the module
docstring that is `sminos help`), `S/sminos_daemon.py` (`publish_state`),
`skills/issue-tracker/scripts/_sweep_api.sh` (`_resume_one`) and its test,
the tests that pin exit 4 and the held line for these verbs, `test_wake.py`,
`S/CLAUDE.md`, `sminos/CLAUDE.md`.

**Interfaces:** exposes §5's wire half (X3 as T2 fixes it) and §6.
Consumes §3 and §4.

**Decisions:**

- A verb aimed at a human-opened thread and one aimed at a seat reach the
  same wake and the same push. §6 says what each does before it; where the
  table is silent a verb exits and prints as it does today.
- `--wait` on a thread with no seat record waits as M2 made a seat's wait:
  by the message's id in the transcript, then for the turn that holds it to
  end (the engine's record of the process reading `idle`), and prints the
  assistant text that follows that prompt up to the next one. With no such
  text it prints `(no reply yet)`. A watcher that expires says the reply is
  read with `sminos reply <name>`, which from M4 resolves a session with no
  seat on this machine and prints its transcript's last reply. A message
  that was held is not waited for: the verb says so and exits 4.
- A verb that recorded its message and started nothing prints `recorded
  and held` in its first line and exits 4. The board's `_resume_one`, which
  takes a failed resume with no sign of delivery as a reason to start a
  fresh worker, reads that phrase as owed, not failed, and starts none: the
  daemon delivers the task it recorded. (The board's dispatch is dormant;
  its scripts and their tests stay true.)
- `SendDelivery` applies `stale_hold` under the delivery lock to each event
  its batch would carry: a stale one is left out of the text and settled
  `recorded` in the writer's order, never ahead of an owed event before it
  (the tech-debt row "A direct send carries its writer's stale held text",
  closed here and removed from the file).
- X3: `lifecycle` writes `wake` and, when it is `held`, `why`;
  `publish_state` writes the `state` again when either changed. `why` is
  `read-only` on a machine whose policy is read-only, whatever else holds
  (it is what a sender on another machine must be told, and a sender on the
  machine itself is not told it); else `not_woken`'s reason, from the whole
  reading of the last turn the sweep made when it marked the thread stopped
  (M1), so that what is published is what a wake decides; else `failed`
  while the record's `waking.failed` is above zero, due or not, so that the
  published value does not turn with the schedule.
- A thread's machine that published nothing, or `held` with no `why` (a
  machine on 1.51), is spoken of in 1.51's words.

**Does not touch:** the guide, the skill, the spawn preamble (M5), the two
stores, `seat add`, a fresh `fill`, `spawn`.

**Proves:** G2 items 2 and 5, and items 1, 3, 9 and 10 through the verbs
and in a remote sender's words. Its tests pin every cell of §6's table with
its exit code and its line, for both kinds of thread, a spawned thread in a
protected folder resumed among them; `--wait` printing the reply to its own
message when a second sender's message is answered after it, and saying
there is none when the session answered nothing; `sminos reply` for a
session with no seat; the line a remote sender reads for each published
value, and for `read-only` beside another reason, from a second registry
over the suite's git mirror; the `state` written again when `why` changes
and not when only the schedule turns; `mode` published for a thread whose
last prompt lies beyond the tail's bound; the board's `_resume_one`
starting no fresh worker after a resume that was recorded and held; and a direct send after a hand-off
leaving the stale event out and settling it in order.

### M5 — What sessions are told, older copies, several senders, and the acceptance

**At its end:** the guide, the skill, the spawn preamble, `sminos help` and
the nested `CLAUDE.md` files say what is true after T2: a stopped session is
woken by an addressed message, when it is not, and what a woken session is
told. Two older copies have been run against a store this code wrote, each
with the expectations of its version. The several-senders suite passes. The
acceptance has run on a real engine as Concrete Steps lists it. The version
is bumped.

**Touches:** `sminos/skills/sminos/SKILL.md`, the guide text and the spawn
preamble in `S/sminos.py`, `sminos/CLAUDE.md`, `S/CLAUDE.md`,
`sminos/README.md`, `docs/whats-inside.md` where it describes a stopped
session, `sminos/tests/test-older-cli.sh`, a new
`sminos/tests/test_wake_senders.py` registered in the runner,
`docs/doperpowers/TECH-DEBT.md`, the version files through
`scripts/bump-version.sh`.

**Interfaces:** consumes all of them; exposes none.

**Decisions:**

- The changed sentences and the opening line go through
  doperpowers:writing-skills with a small evaluation (X6): a woken session
  must act on the message, must not address its human as though they were
  watching, and must not treat the line as a peer's words. A word of §2's
  line or §5's lines that the evaluation changes is recorded in the Decision
  Log and sent to the composite's holder before the merge.
- **Older copies, per version** (D7). `test-older-cli.sh` builds two pinned
  copies by `git archive`, 1.27.10 (revision `aefb80aa`, its default today)
  and 1.51.0 (the revision of merge `0387f2b7`), and takes
  `--older <launcher>` for a third. Expected of both: no verb of theirs
  starts a process for a human-opened thread that copy did not itself give
  a seat (D7 accepts an old `seat add --session` and its resume). Expected of 1.51.0: a `say`
  and a `send` of its own to a stopped human-opened thread this code would
  wake are recorded and marked, start nothing, and this code's next pass
  wakes the thread and pushes them; its line to its sender is 1.51's.
  Accepted and asserted as it is, so that a change is seen: a pass of
  1.51.0 settles as `recorded` what this code held for a spawned thread
  (its rule for a seat); a copy from before threads drops every mark when
  it writes a delivery record; a refill by 1.51.0 leaves a `waking` that
  names the displaced session, which this code ignores (§7). The tech-debt
  row "An older copy's delivery write drops held marks" is extended with
  the spawned case.
- The several-senders suite is written from the scripts T1's verifier left
  (their shapes are in T1's plan, Decision Log, "The verification of the
  held path"): one store, and two registries over a git mirror; one, two
  and five senders, one and three messages each; `say`, `send` and a send
  from another project; each against a thread that is woken, one held for
  each reason, one whose wake fails once and then succeeds, and a hand-off,
  a `/clear`, a retire and a refill between the send and the wake. Each
  asserts every message in exactly one inbox exactly once, or held with its
  mark, or settled with the reason its sender was told. What is not
  promised is asserted as it is: a deliverer killed between an inbox's
  admission of a frame and the settlement leaves the event owed, and the
  next pass pushes it again (T1's limit for a live push; the wake adds no
  window of its own, since it settles nothing).
- The live pass runs under a scratch `HOME`, `CLAUDE_CONFIG_DIR` and
  `SMINOS_HOME`, in a terminal multiplexer of its own, on the cheapest
  model, with the engine's credentials passed through the environment and
  written nowhere, and removes every job it made (`claude rm`). What it
  cannot observe on one Mac is said as not verified, not passed.
- The tech-debt rows of "sminos threads" are read against the wake: the
  direct send's row leaves; each of the others gets a sentence saying
  whether a wake's push meets it. The row for a `/clear` between the last
  binding and the inbox write gains what the second spike found: the
  engine's inbox refuses a frame whose `session_id` is another session's
  (`wake-spike-2.md` §16), which sminos's frames do not carry yet; what a
  sender observes of such a refusal is not measured, and that measurement
  is the row's next step, outside T2.

**Does not touch:** behaviour. A defect the suites or the live pass find is
fixed in the milestone that owns the code, by that milestone's executor
continued, and reviewed there.

**Proves:** the acceptance as the proof map of Concrete Steps assigns it,
and parent acceptance line 8 as a comparison: every suite that passed on
the merge base passes, with the changed tests listed in the report beside
what each pinned before and pins now.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-threads-t2`).

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_wake.py
    python3 -B sminos/tests/test_threads_stopped.py
    python3 -B sminos/tests/test_threads_branch_b.py
    python3 -B sminos/tests/test_wake_senders.py
    bash sminos/tests/test-older-cli.sh

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. The shell file ends with its counts of passed
and failed and exits non-zero on any failure.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites,sminos-idle,sminos-mods,issue-tracker,board-api,shell-lint,repo-checks

and in M5 `version-bump` too. Expected: one `PASS` line per gate, then
`GREEN` and the run's address. A `FAIL` that the base also shows, or one a
recorded reason names, is not this change's; any other is diagnosed, not
run again.

**The proof map.** Where each acceptance item is proved. "Suite" is the
test engine; "live" is the real engine in M5's pass; an item with no live
column rests on the suite, and the report says so.

| Item | Suite (milestone) | Live (M5, step) |
|---|---|---|
| G2.1 same id, one process, mode and model, the line, attach | M2 (direct), M3 (`say`, `send`), M4 (verbs) | 1 |
| G2.2 each case not woken: no process, held, reason published and said, here and remotely | M3 (here), M4 (published, remote; `read-only` beside another reason) | 3 for `mode` and `cwd`; the others suite |
| G2.3 a held session is not woken; a copy removed, the message delivered | M2 | 4 for the held session; the race is suite |
| G2.4 flags by the row; the unreadable row's copy and second wake | M2 | 2 for the later wake; the unreadable row is suite |
| G2.5 the verbs; a spawned thread in a protected folder | M4 | 6 for `resume --wait` and the refused `fill`; the rest suite |
| G2.6 two wakes together | M2 (the launch counter), M3 (both messages once) | 5 |
| G2.7 a worker that fails before it starts | M2 | suite |
| G2.8 the thread's directory | M2 | 1 |
| G2.9 one path: a spawned thread held; no other launcher | M3, and M2's check that nothing else calls `run_claude_bg` with `--resume` | suite |
| G2.10 a failed wake held, published, tried again | M3, M4 (published) | suite |
| D2 step 3, the line: on the first frame after a wake, its words for a first and a later wake, never to a terminal | M2 (a seat), M3 (the race with a second sender), M5 (the evaluation) | 1, 2 and 3 |
| G2.11 no launch carries a message; the name kept | every suite, by the test engine's check; M2 (the name) | 1 |
| Parent 3 | as G2.1 | 1 |
| Parent 4 | as G2.2 `mode` | 3 |
| Parent 8 | the gates, compared with the merge base | — |

**M5, the acceptance on a real engine.** In a scratch tree `<scratch>`:
`HOME=<scratch>/home`, `CLAUDE_CONFIG_DIR=<scratch>/home/.claude`,
`SMINOS_HOME=<scratch>/sminos`, the engine's credentials passed through the
environment, the user settings in that config directory setting
`permissions.defaultMode` to `auto` (the machine's ceiling) and a model that
is not the one the sessions are launched on; the plugin loaded from the
worktree (`--plugin-dir <worktree>/sminos`) and `sminos` meaning
`<worktree>/sminos/skills/sminos/scripts/sminos` in every shell; two
scratch git repositories `<scratch>/a` and `<scratch>/b`; a multiplexer of
its own; and the scratch daemon, `sminos daemon run --interval 5`, in one of
its windows. A session is addressed by its short id (`@<first eight of its
session id>`), which reaches it from any project. Before each step the ids
under `<scratch>/home/.claude/projects` and the output of
`claude agents --json --all` are saved as the baseline.

1. In `<scratch>/b`: `claude -n bee --permission-mode auto --model <M>`,
   one turn, exit; call its id B and the model id its assistant row names
   `<M id>`. In `<scratch>/a`: a session A, one turn, left open. From a
   shell in `<scratch>/b`, `sminos list --stopped` shows `bee` `stopped`.
   Take the baseline now. From A's shell:
   `sminos say "@<B8> <nonce1>: reply with the word woken and the output of pwd"`.
   Expect within two minutes: A's output says the message was sent and B
   woken; the job list holds one job more than the baseline, its
   `sessionId` B, and `ps` shows one process for it; no session id exists
   under `projects` that the baseline lacks; the engine's record of that
   process names `bee`, `kind` `bg` and `<scratch>/b`; B's transcript holds
   exactly one new prompt row with `<nonce1>`, in which §2's line stands
   ahead of sminos's own header for the sender, inside the engine's wrapper
   for a message from outside; that row's `permissionMode` is `auto`; the
   assistant row that answers it names `<M id>` and its text holds
   `<scratch>/b`; B's row's `respawnFlags` hold `--permission-mode auto`
   and `--model <M>`. Then `claude --resume <B>` in a window: one process
   for B still, and a prompt typed there is answered in B's transcript.
   Detach.
2. `claude stop <B's short>`; wait for `bee` to read `stopped`. Send B a
   second message with `<nonce2>`. Expect the same id, no job and no
   session id beyond step 1's, and one prompt row with `<nonce2>`,
   answered, without §2's sentence about a first run.
3. In `<scratch>/b`: a session C in `plan` mode, one turn, exit. From A:
   `sminos say "@<C8> <nonce3> …"`. Expect: no job for C, and A's output is
   §5's line for `mode`. `claude --resume <C>` in a window: one prompt row
   with `<nonce3>`, and no line of §2 in it. Then a session D in
   `<scratch>/d`, exited, the directory moved away: A's output is the line
   for `cwd`, and no job. (What each machine publishes is the suite's, M4:
   a local project publishes no state.)
4. With B attached in a window (`claude --resume <B>` after step 2's wake),
   send B a message with `<nonce4>`. Expect one prompt row with it in that
   conversation and no new job.
5. `claude stop <B's short>`. From two shells at once:
   `sminos say "@<B8> <nonce5>"` and `sminos send <B8> "<nonce6>"`. Expect
   one job for B, no session id beyond the baseline's, and exactly one
   prompt row for each nonce in B's transcript.
6. `claude stop <B's short>`. `sminos resume <B8> "<nonce7>: reply with done" --wait`
   prints the reply to that message. `sminos fill <B8> "x"` is refused and
   starts nothing.

Afterwards every scratch job is removed (`claude rm`), the multiplexer and
the scratch daemon are stopped, and the report keeps what each step printed
beside the commands.

## Interfaces and Dependencies

### §1. What a wake reads (`S/sminos_wake.py`)

    UNREADABLE = object()
    def row_of(session) -> dict | None | UNREADABLE
        # The engine's row: <the session's config dir>/jobs/<first eight>/state.json whose
        # `sessionId` is the session. None: a `jobs` directory exists and holds no row for it.
    def row_options(row) -> list[str]            # the row's `respawnFlags`, [] when it has none
    def row_failed(row) -> bool                  # its `state` is "failed"
    def last_turn(session, whole=False) -> {"mode": str | None, "model": str | None}
        # "" when the transcript holds none; None when not found within the bound (never with `whole`)
    def asks(mode) -> bool                       # default, manual, plan, acceptEdits
    REASONS = ("config", "transcript", "cwd", "protected", "mode")
    def not_woken(record, session, whole=False) -> str      # "" or one of REASONS; takes no lock
    def wake_due(record, session, now=None) -> bool          # §4's schedule, from the record's `waking`

`not_woken` reads the record it is given and the files it names and nothing
else; it never reads the engine's job list.

### §2. What a first wake passes, and what a woken session reads

    def wake_argv(session, flags) -> list[str]     # ["--bg", "--resume", session] + flags; never a positional after
    def first_flags(record, turn, ceiling, accepted_bypass) -> (list[str], list[str])   # (flags, names not carried)
    def opening_line(note) -> str                  # from the record's `waking.line` (§7)

The opening line is one paragraph of sminos's own. Everything that reaches
a session through its inbox is, to the engine, a message from outside, so
the line cannot stand outside that: it is put ahead of the frame's own
first line (sminos's header naming the sender), followed by an empty line,
in the text handed to the one function that pushes to a live session (§4),
before a route is chosen; a route that adds a marker of its own (a
receipt's, the bridge's key) adds it as today. Its text:

    [sminos] A note from sminos on this machine, not from the sender below: you were woken in the background by this message, and your human is not watching this session unless they have attached to it since. You run in <mode> mode on <model>.

When the mode or the model is not known, that clause reads `under your saved
options`. A later wake whose row names another model than the last turn ran
on adds: ` Your last turn ran on <turn model>; a background run keeps the
options it last ran with in the background.` A first wake adds: ` This is
your first run outside the terminal you were opened in: the environment
variables of that terminal are not set here.` and then, when names were not
carried: ` Not carried from its launch: <option names, comma-separated>.`,
or, when the record does not say what was dropped: ` Other options of its
launch may not be carried.`

### §3. The wake

`resume_session`, or its core, is the wake: it makes a stopped thread's
session live and hands over nothing. Its caller may hold the delivery lock
of the session, and for a record in the seat store holds the seat's
lifecycle lock.

    wake(record, session, due=False, returns=False, on_live=None) -> WakeResult
        # .live: a process holds the session now (launched here or found); .why: "" or why not;
        # .short: the job's short when this call launched it

`record` is the thread the caller chose, by its id. `due` true is a
sender's or a verb's own call, which no schedule holds back. `returns` true
is `fill --resume` of the seat it names, the one caller for which an ended
record is woken. `on_live` is called at W8, under the wake lock and with
its hold, for what a caller must write once the process is live (a seat's
fields, a retired seat's return).

**Its steps,** in order:

| # | Step |
|---|---|
| W1 | Take the wake lock, by `resume_lock_taken`'s bounded poll. |
| W2 | Under it, read again, in this order: the record by its thread id; that it is the thread `thread_of` answers for the session now, its `current` the session, with no reservation on it; its end; its open entry; the session's lane; E5's three signals; `not_woken` with the last turn read whole; and, unless `due`, `wake_due`. |
| W3 | If the session's row exists and the engine lists that row's job as neither stopped nor failed while no process holds the session, stop that job (`claude stop <its short>`) and wait for it as `wait_stopped` does. |
| W4 | Read the row. A row: no flag. No row: `first_flags`. Unreadable: `first_flags`, unless the record's `waking.saved` is set or this is the pass after row 12. Then write `waking.line` for this wake, with an id of its own (§7). |
| W5 | Run `claude` with `wake_argv` from the thread's directory, with `launch_env` as today. |
| W6 | Read the answer: the exit status, the banner's short, the three notes of E14. |
| W7 | Wait, for `poll_uuid`'s bound, until the engine's record shows a process holding the session, or the job the banner named reads failed. |
| W8 | Write what the wake learned, each write made only while the record is still the thread and the session it was decided for: `waking`'s failure cleared and `saved` set when row 12 led here, the stop mark lifted (`stop_seen`), and the caller's `on_live`. |

**The table.** What is found, in the order it is looked for, and what
follows. Nothing in it is settled or pushed: the caller delivers to a
session that is live, and holds the event otherwise.

| # | Found | Done | Result |
|---|---|---|---|
| 1 | W1: the sweep or a transition holds the lock past the wait | nothing | live if a process holds the session and its inbox answers, else `sweep` |
| 2 | W1: another launch holds the lock | nothing | the same, else `in flight` |
| 3 | W2: the record or the session's lane cannot be read | nothing | not live, `unknown` |
| 3a | W2: no such record, or the session's thread is another now, or the record is reserved | nothing | not live, `gone` |
| 4 | W2: the thread ended, and the caller is not `returns` for this seat | nothing | not live, `ended` |
| 5 | W2: an open journal entry | nothing | not live, `pending` |
| 6 | W2: the session is positively not lane A | nothing | not live, `lane` |
| 7 | W2: a process holds the session | nothing | live |
| 8 | W2: a signal cannot be read | nothing | not live, `starting` |
| 9 | W2: a reason of `not_woken` | nothing | not live, that reason |
| 10 | W2: the wake is not due | nothing | not live, `failed` |
| 11 | W6: a copy, "is open in another Claude Code process" or "is already running in the background" | the copy removed; nothing remembered | as W2 finds it now: live, or `starting` |
| 12 | W6: a copy, "keeps its own saved options", flags having been passed | the copy removed; once more from W2 with no flag, and `waking.saved` set when that pass launches | as that pass ends |
| 13 | W6: a copy for any other cause, or a banner whose job names another session | that job removed | failed |
| 14 | W6: no banner, a non-zero exit or a timeout | — | live if a process holds the session now, else failed |
| 15 | W7: the banner's job reads failed and no process holds the session | the row removed when it is this launch's (below) | failed |
| 16 | W7: neither within the bound | — | not live, `starting` |
| 17 | W7: a process holds the session | W8 | live |

"Failed" is: the failure counted in `waking` (§7), `waking.line` of this
wake removed, and the result not live, `failed`. Nothing else is removed
on a failure, with one exception. **A row is removed only as this launch's
own:** W4 read that the session had no row (`None`, not `UNREADABLE`); the
job the banner named reads failed; and the row there now names the session,
reads failed, and its `detail` begins `exit 1 before init` (E20). Then
`claude rm <the banner's short>`, whether or not flags were passed, so that
the next wake is a first one again; a removal that fails is said in
`daemon.log`, and the next wake finds a row and passes no flag. A row that
was there before the launch, or whose failure is not that one, is never
removed: `rm` drops what else a row holds and can delete a worktree (E9).

A copy is a job this launch's banner named whose session is not the
thread's, or that one of the engine's notes names as the copy. It is
removed with `claude rm`, checked in the job list, stopped instead when
that fails, and said in `daemon.log` when it could not be removed. No
other job is ever removed as a copy.

What a caller does with a result that is not live: `gone` is the stale
hold, settled `recorded` and its sender told the session no longer fills
the thread; `ended` is settled as an end settles; `lane` is delivered as to
a session that is no thread; every other, `unknown` among them, is the
outcome `held:<why>`.

**Linearization points.** A wake is ordered against the sweep, an end, a
retire, a hand-off, an absorption, a refill, a return and another wake by
the wake lock: each of them opens its journal entry under it, and reads
under it what the entry records of the process (M2), so a wake sees the
record before the entry or with it, never between, and an end never
records that it saw no process while a wake's launch was under way. It is ordered against a
process that takes the session by the engine's own answer at W6 (rows 11
and 17 are the two orders). No message is ordered by a wake at all.

### §4. Delivery to a thread

An addressed event for a session, under its delivery lock, in this order:
what `deliver_next` decides today before a push (a noted push, a receipt, a
revoked signer, `read-only` for an outside event, a stale hold); then a
hold, when `hold_now` gives a reason, with nothing asked of the endpoint;
then the endpoint's gates as today; then the push. The push to a thread:

1. A live session is pushed to (`push_live`), and the outcome is today's.
2. Else `wake(record, session)`. Live: the session is delivered to as one
   found live at the pass's start, in the same call; an inbox that does not
   answer yet is `held:starting`.
3. Not live: the outcome of §3's last paragraph.

An event for the live alone (an `@all`, a broadcast) is never a wake's
cause and settles `recorded` for a stopped thread, as today.

**The line.** A wake writes `waking.line` before it launches (W4), with an
id of its own, so that the first frame pushed to the new process finds it
even when another sender's push arrives before the launcher has returned
(E18). The one function through which sminos hands a frame to a thread's
live session reads the record of that session: when it holds a `line`
naming the session and the process that holds the session is a background
one (the engine's record says `kind` `bg`), the frame is opened with
`opening_line`, and once the push returned as made the `line` is removed,
only if it still has that id. A `line` met for a process that is not a
background one (its human reopened the session in a terminal) is removed
and not sent. A push that fails leaves it for the next. Two frames pushed
at the same moment through two projects' delivery locks may both carry
it; none carries another session's or an earlier wake's.

**The retry rule** (`wake_due`). A wake is due when the record's `waking`
names no failure for this session, or once `WAKE_RETRY * 2 ** (failed - 1)`
seconds, at most `WAKE_RETRY_MAX`, have passed since `waking.at`.
`WAKE_RETRY = 60` and `WAKE_RETRY_MAX = 3600`, each read from an
environment variable of the same name with `SMINOS_` in front, for tests.
There is no bound on the count: a thread that cannot be woken ends by the
three-day rule, or is retired. At the fifth failure in a row the daemon
writes one line in `daemon.log` naming the thread and what failed. While a
wake is not due `hold_of` answers `failed`, so nothing is asked or launched
for the thread by the daemon's passes or the uplink. A sender's own call
and a verb pass `due`, for the event they wrote: the hold check and the
wake then pass over `failed` alone (M3).

**What is promised.** A message addressed to a thread is in the log and is
owed until it is pushed to a process of that thread or the thread ends. It
is pushed once, except that a deliverer that dies between an inbox's
admission of a frame and its settlement leaves it to be pushed again (T1's
limit for a live push, unchanged). A wake adds no case of its own to either
side: it carries nothing and settles nothing.

### §5. Whether a thread is woken, as its machine says it (X3)

On a stopped thread's `state` event: `wake`, `"woken"` or `"held"`, and with
`"held"` the field `why`, one of `config`, `transcript`, `cwd`, `protected`,
`mode`, `failed`, `read-only`. Read by `wake_of(member)`, which answers
`"woken"`, `"held"`, `"ended"` or `None` as today, and `why_of(member)`, the
reason or `""`.

What a sender reads for a held message, `<M>` the thread's machine when it
is another. Each line is `recorded and held[ on <M>]: the session is
stopped and is not woken: `, the reason below, and then `; it is pushed
when a process of it runs again before it ends (three days stopped, or a
retire), else it stays in the log`.

| `why` | The reason |
|---|---|
| `config` | `it runs under another config dir` |
| `transcript` | `no conversation of it is on that machine` |
| `cwd` | `its directory is gone` |
| `protected` | `its directory is in a folder macOS protects, where a background launch would stop at a prompt for its human` |
| `mode` | `a wake would run it in a mode that asks for approval`; on the thread's own machine, when the ceiling and not the thread's own mode is the cause (`mode_case` answers `ceiling`): `this machine's ceiling (<ceiling>) would start it in a mode that asks for approval; the ceiling is its owner's setting (sminos daemon policy shows it)` |
| `failed` | `waking it failed, and its machine tries again` |

For `read-only` the whole line is `recorded: <M> admits nothing from
another machine, and refuses it there`. For `held` with no `why`, 1.51's
`held_line`. For `woken` from another machine, `woken_line` as today. For a
hold that passes on its own (`starting`, `in flight`, `sweep`, `pending`)
the line is `recorded: its process is starting, and the daemon delivers it`.
On the thread's own machine a message pushed after a wake prints what a
push to a live session prints, with ` (woken)` after it.

### §6. The verbs

For a thread of either kind on this machine, unless a cell says otherwise.
"Push" is the live push; "wake" is §3 with `due`.

| The session is | `say` with a tag, `send` | `send --wait` | `resume` | `fill --resume` |
|---|---|---|---|---|
| live | push; exit 0 | push, wait for its reply | a background job: its turn stopped, wake, push (today's rule for a seat). In a terminal: push as `send` does, and say that a terminal holds it | refused as a filled seat is today, with today's exit code (2); a human-opened one in the same words |
| stopped, woken | wake, push; exit 0 | wake, push, wait | wake, push; with `--wait`, wait | wake, push; a retired seat returns (§3, `returns`) |
| stopped and not woken, or the wake failed | recorded and held, §5's line; exit 0 | recorded and held; `nothing was started: <reason>`; exit 4 | the same, exit 4 | the same, exit 4 |
| held for a moment (`starting` and the like) | recorded, §5's line; exit 0 | recorded; no reply is waited for; exit 4 | the same, exit 4 | the same, exit 4 |
| ended | exit 4 as today | exit 4 | exit 4 | a spawned thread returns as today; a human-opened one exits 4: it returns when its human reopens it |
| on another machine | recorded, §5's line by what its machine published; exit 0 | as today | exit 4 as today | exit 4 as today |

Every verb in the table records its message before it does anything else,
as `send` does. A fresh `fill`, a `spawn` onto the alias and a `seat add`
over it are refused for a human-opened thread as T1 refuses them.

### §7. The record's field (X1)

`waking`, absent or an object, on either kind of record, written only by
`sminos_threads.py` through `update`, under the wake lock:

| Key | Meaning |
|---|---|
| `session` | the session id the field was written for; a reader ignores the whole field when it is not the record's `current` |
| `saved` | `true` once the engine answered that the session keeps saved options where its row could not be read (§3, row 12) |
| `failed` | wakes failed in a row |
| `at` | when the last one failed |
| `line` | what the next pushed frame's opening line says, written before the launch: `{"id": str, "first": bool, "mode": str, "model": str, "turn_model": str, "not_carried": [names] or null}` |

    def wake_line(thread_id, session, line, lock_until=None)          # line set, before a launch
    def wake_failed(thread_id, session, line_id, lock_until=None)     # failed += 1, at; that line removed
    def wake_done(thread_id, session, saved=None, lock_until=None)    # failed and at removed; saved set when given
    def wake_line_sent(thread_id, session, line_id, lock_until=None)  # line removed, if it still has that id
    def wake_forget(thread_id, session, lock_until=None)              # saved removed: sminos removed the session's row

Each writes only while the record's `current` is `session`. `stop_seen`
removes `failed` and `at` with the stop mark. `sminos list --json` of this
code exports none of it; a copy at 1.51 exports a seat's unknown keys, so
nothing is kept in it that is not already in that row (no text of a
failure: that goes to `daemon.log`).

### §8. The test engine

One fixture in two forms that behave alike: the shell stub of
`run-sminos-tests.sh`, and `sminos/tests/wake_engine.py`, a `claude`
executable for the Python suites put first on `PATH` (so that the argument
vector, the banner, the notes and `rm` are exercised, where patches of
`run_claude_bg` and `poll_uuid` are not). Its state is a directory, and
each behaviour is switched by a file or a variable a test sets.

- **A wake.** `--bg --resume <id>` with no positional starts a helper
  process, writes the engine's record of it (`sessions/<pid>.json`: the
  session id, `kind` `bg`, the directory, the name kept, the inbox's path),
  serves the inbox, writes the job's entry and the row
  (`jobs/<first eight>/state.json` with `sessionId`, `cwd`,
  `respawnFlags`), and prints the engine's banner for an idle resume. Each
  frame pushed to the inbox is appended whole to `inputs/<session id>`,
  where the suites count a message's id and read a frame's layout.
- **A turn.** For each frame the helper writes a prompt row holding the
  frame's text to the session's transcript, marks the engine's record
  `busy`, then writes an assistant row (a reply naming the message's id,
  with a model and a `requestId`) and marks the record `idle`. Switches:
  no reply; a reply after a delay; a second frame answered before the
  first.
- **A positional after the id.** From M2 it is written to `violations` and
  the stub exits 2, and every suite's teardown fails on a non-empty
  `violations`; in M1 the fixture refuses it only where a test asks.
- **Rows.** Flags with no row: the same id, the row written with them.
  Flags with a row: a copy and the third note. No flag with a row: the same
  id and the engine's "woke session" note. `rm <short>` removes the row and
  the job; `stop <short>` ends the helper and leaves the row.
- **Switches:** a held session (the first or the second note, and a copy);
  a silent copy (another id, no note); a row the engine has and sminos
  cannot read (the row kept outside the config directory); a worker that
  fails before it starts (the banner, exit 0, a job that reads failed, a
  row that keeps the flags and the engine's `detail`, no helper); a job
  that fails otherwise, with a row in place before it; a copy that `rm`
  refuses; a late inbox (the helper's record written at once, the inbox
  served after a delay); a late process (no record of it until a delay
  longer than the wake's wait); the job list failing; a launch that never returns its banner
  while the helper starts; and a barrier (the launch blocks until a file is
  removed) with a counter of launches entered, for two deliverers at once.
- **The three signals of E5** are separate files a test can write or remove
  on their own: the engine's record of a process, the job list's entry, and
  the bridge's socket.

### Dependencies

No new library. The engine is Claude Code 2.1.329, the version
`wake-spike-2.md` was measured on; the row's layout is the engine's own and
is read defensively (§1). devcloud is not touched.

## Surprises & Discoveries

- Observation: a background resume with no message starts an idle process
  with its inbox and runs no turn, and a launch that carries a message
  cannot take it back from a copy.
  Evidence: `wake-spike-2.md` §14 to §16 (E17 to E19): the transcript
  unchanged after the launch; a copy's transcript holding the prompt 0.33 s
  after the command returned.
- Observation: a woken process does not exit on its own, so a thread woken
  once is live, not stopped, until something stops its process.
  Evidence: `wake-spike-2.md` §9: idle 24 minutes after its turn, its
  record and inbox in place.

- Observation: with no policy file and user settings that name no
  `defaultMode`, the machine's ceiling resolves to `default`, so by M1's
  rule every first wake on such a machine would pass `--permission-mode
  manual` and the woken session would stall at its first tool call (E6),
  whatever mode its last turn ran in. M5's live setup sets `defaultMode`
  to `auto`, which would have hidden it.
  Evidence: `sminos_policy.py`'s `load` and `settings_mode` (M1's report).
- Observation: a test engine written without its executable bit lets
  `PATH` fall through to the real `claude` under the test's temporary
  `HOME`. On M1's first run the real engine stopped at "Workspace not
  trusted" in every case and nothing started; the suites that put the test
  engine on `PATH` now fail unless `shutil.which("claude")` is the stand-in.
  Evidence: M1's report; no process or engine directory was left behind.

- Observation: an end's `begin` writes `ended` in the same write as its
  entry, so a wake inside a retire's open entry answers `ended` by §3's
  order, never `pending`; `pending` is met only inside an advance, an
  absorption or a return.
  Evidence: `test_wake_transitions.py`, the retire cases (M2).
- Observation: a copy of `sminos.py` loaded by a test through
  `spec_from_file_location` binds its siblings to another copy, so a
  registry of wake holds kept per module copy let an end's `begin` wait on
  its own flock. The registry is one per process.
  Evidence: the `sminos` gate's `CLOCK` block, red on M2's first push.
- Observation: on a machine with no `jobs` directory `row_of` is
  `UNREADABLE`, so row 15's clean-up of a failed first wake's own row never
  runs there; the first wake still passes flags, and the next reads the
  row the engine made.

- Observation: from M2 a wake reads the engine's job list on every call, and
  one rig that patched only the launch (`test_reach_gate.py`) let it run the
  real `claude agents` (under the test's temporary `HOME`; nothing
  launched). From M3 the preamble every Python suite runs
  (`devcloud_isolation.py`) puts `sminos/tests/no-engine/claude` first on
  `PATH`; a suite with its own engine puts that first and checks it.
- Observation: `test_threads_ended.py` reuses `test_threads_stopped.Rig`, so
  a fixture default in one changes the other.

## Decision Log

- 2026-11-20 — **Verification.** The plan is reviewed before it is handed
  over by the `doperpowers:adversarial-reviewer` agent, on the wake's design
  against the code and on buildability; a second round reads the rewrite,
  and there is no third before the build. Each milestone is reviewed at its
  close by the execution loop's reviewer, three reviews at most (the owner:
  "리뷰도 3회로 둬도됨"). The range M1 to M4 is reviewed whole by the
  composite's holder at the frontier, through doperpowers:review-code at
  the panel rung (xhigh) with the four lenses named in Plan of Work, a
  second whole reading if the first confirms more than ten, and three
  rounds at most. The branch's end has no further whole review: M5 adds
  text and tests, read by its own review. The held guarantee under the wake
  is attacked by M5's several-senders suite, written before the acceptance
  run.
- 2026-11-20 — **The first draft's review, and what it changed.** Two
  reviews returned 28 findings. The draft had the message ride in the
  launch, as a seat's resume does today; the largest group of findings
  followed from that (a copy that read the message, a replay after a
  sender's death, settlement on a launch nothing confirms, the endpoint's
  permit spent twice, a `--wait` that cannot find its reply), and the
  engine read again the same day showed a launch needs no message. The
  composite's D2 was revised and this plan rewritten: the wake starts the
  process, and delivery is the live path. The others, each fixed where
  named: a retire or a hand-off between a wake's check and its launch
  (transitions take the wake lock, M2; a record gone or refilled is a row
  of the table); a live session held because a reason not to wake still
  read true (the table's order); a session that became lane B woken (row
  6); a second message from one sender never tried (the schedule is the
  thread's, with no per-event attempt and no bound); a refill's debt
  becoming valid again (a refill settles, M3); a lock order the code does
  not have (the constraint names both exceptions); the daemon's memory
  keeping holds no file changes for (M3); `waking` passing to a new
  occupant through an older copy's refill (the field names its session);
  `read-only` published behind another reason (M4); milestones that did
  not end green (consumers moved with their producers; the constraint);
  `send` to a held session exiting 4 and `fill --resume` stopping a running
  seat (§6 restores both); a tail bound read as "no turn" (`None`, and a
  whole reading at the wake); inline options never reported (the dropped
  names); a stub that could not show a running conversation (§8); live
  steps that could not run (rewritten, with a proof map); and an absolute
  claim about older copies (per version, M5).
- 2026-11-20 — **Decided in this plan** (also in the composite's Decision
  Log, as T2's): the retry schedule (§4); `waking` on the record (§7); the
  reasons' order (§1); `--add-dir` not carried and `bypassPermissions`
  lowered where the engine refuses it; a launch whose answer is lost is
  read by whether a process holds the session (§3, row 14); the opening
  line rides on the first frame pushed after a wake. *Alternative rejected
  for the line: a frame of its own.* A frame pushed to an inbox runs a
  turn. *Alternative rejected: the daemon alone wakes, and a sender's CLI
  only records.* It loses `--wait`, the wake on a machine with no daemon,
  and D2's rule that a sender's CLI wakes under the lock; the lock and the
  table carry the same guarantee.

- 2026-11-20 — **The second review, and what it changed.** Both reviewers
  read the rewrite and said to keep the wake without a message. What they
  still found, each fixed where named: a retire reading the process before
  it takes the lock (read under it, M2); an absorption locking the other
  record (the reservation under the absorbed record's lock; W2 asks which
  thread holds the session now); a failure removing a row that was there
  before (the rule for a launch's own row, §3); the first frame arriving
  before the line was written (written before the launch, with an id); the
  line's place in a frame the engine marks as from outside (ahead of
  sminos's header, said as sminos's own, and the composite's wording
  changed to match); a retired seat that `fill --resume` could not return
  (`returns`, `on_live`); `resume` and `fill --resume` bringing a text no
  log held (recorded as `send` records); the board's caller taking a held
  resume for a failed one (M4); a `/clear`'s release left out of the lock;
  a line outliving its process (not sent to a terminal); a seat's waiter
  printing another's reply (waits by the message's id, M2); an unreadable
  record or lane read as a known one (`unknown`); a fixture switched on
  for every suite a milestone early (M2); two consumers of the changed
  hold left for M4 (moved to M3); a sender's own call held by the schedule
  (`due`); a bounded reading published as the wake's decision (the sweep's
  whole reading); a test engine with no turns (§8); and live steps that
  could not tell success from failure (rewritten). No third review of the
  plan precedes the build.

- 2026-11-20 — **A first wake's capped mode decides `mode`** (M1; confirmed
  by the composite's holder). The mode a first wake runs under is the last
  turn's lowered to the ceiling, so when that capped mode asks for approval
  the thread is not woken for `mode`, never started into a stall. The
  ceiling is what the policy says (the settings' `defaultMode`, else
  `default`, as `admit_spawn` reads it), never read as no cap. The rule is
  for a wake that would pass flags: no row, or a row that cannot be read; a
  thread with a readable row is untouched (no flag is passed). `why` stays
  `mode`, with no new value; the words a sender and `sminos list` read say
  when the ceiling, not the last turn's own mode, is the cause, and name the
  owner's remedy (`sminos daemon policy --ceiling`, or the settings'
  `defaultMode`). `not_woken` therefore reads the policy file and the user
  settings, and both are in the key of the daemon's memory of an all-held
  pass (M3), so a raised ceiling ends the hold at the next pass with nothing
  new sent. A suite case pins it (M3): ceiling `default`, last turn `auto`,
  no row: held for `mode`, no launch; the ceiling raised, the next pass
  wakes it.
- 2026-11-20 — **M1 as built.** The ceiling and the bypass rule apply to the
  launch's recorded `--permission-mode` as well as to the last turn's, and
  `manual` is compared as `default` in `sminos.PERMISSION_MODES`' order.
  `launch_dropped` names only `LAUNCH_OPTIONS` dropped for their value
  (inline JSON, a session id), once each. The `waking` writers compare and
  set through `update` (the field unchanged since read, `current` the
  session), so they hold without the wake lock too; `waking` is a
  `SEAT_KEYS` entry, hidden from `list --json` and dropped at a lane B
  repoint. `line_note` takes `first` from its caller (row 12's second pass
  is known only there). The test engine's switches are files in its state
  directory, so a daemon sees them; the shell stub hands a wake with no
  message to the Python twin, and `test_wake.py` runs the shared cases
  against both forms.

- 2026-11-20 — **M1's reviews, and what they moved.** `row_of` checks the
  row's `sessionId` on every lookup (its cache is keyed by a path that ids
  sharing a first eight share). A transcript the index found that is gone is
  looked up again, and no file reads as `transcript`, never as a turn
  unknown. `waking` is dropped whenever this code changes a record's
  `current` (`_apply`, `REPLACED_DROPS`, `OCCUPANT_MARKS`), so an earlier
  occupant given the thread again finds none of its old field. Model names
  are one model only when their whole ids match; a family alias (`haiku`)
  against an id is shown as both names (E10's measured case), never assumed
  the same. One function decides whether a wake passes flags, for both the
  `mode` reason and the launch, and W2 tells it (`flagless=True` to `not_woken` and `mode_case`) when it is row 12's flagless
  retry or `waking.saved` is set; the `mode` check reads the mode alone and
  never probes a `--settings` path. `mode_case` answers `own` or `ceiling`
  for the sender's words (M3, M4), and `policy_inputs` the files the ceiling
  is read from (M3's memory key). An unknown ceiling is read as `default`.
  The test engine signals only a helper whose command line it verifies as
  its own, at every signal.

- 2026-11-20 — **M2 as built, and what its reviews moved** (the holder
  accepted the first four). `wake()` is the core and `resume_session` the
  seat's thin caller; only `wake` and `spawn_fresh` call `run_claude_bg`,
  and `spawn_fresh` never with `--resume` (pinned by the source). Every M2
  caller passes `due`; the schedule is M3's. From delivery, a seat whose
  wake did not make it live answers `recorded` for `gone`, `lane` and
  `ended`, `held:<why>` with no attempt counted for what passes on its own
  or cannot be read (`sweep`, `in flight`, `starting`, `pending`,
  `unknown`), and `failed:` counted otherwise, until M3. `fill --resume` of
  a stopped seat records its task first; of a retired seat it wakes first
  (the return, journaled at W8) after every check that can refuse the task
  locally (its stream), and a seat whose project is not read here is
  refused its return before any process starts: whatever a verb must write
  once the process is live is checked writable before the launch. On a
  cut-over machine the endpoint's verdict on a returned seat's task comes
  after the process started; a refused task has woken it for nothing,
  accepted as the plan orders it. On a cut-over machine an operator's
  `resume` is recorded for the endpoint, as `send` is, and wakes nothing
  itself. A projectless desk-spawned resume test went: a resume's message is
  now a logged event. Copy evidence is only the engine's note, a whole line
  naming this session and the banner's job; a banner job owned by another
  session is a copy even when the session also came up; a failed job counts
  for row 15 only when it is this session's; a removal is confirmed only by
  a job list that reads; `waking.saved` is written as the flagless retry
  launches. Only a positively identified background job of the session is
  stopped (W3, `resume`'s stop), never a terminal's process; a stop is
  confirmed only by a listing that reads, and one that cannot be is
  `starting`, launching nothing. A retire and an end replay an open entry
  before they take the wake lock (`held_settled`), never under it; an
  absorption takes both wake locks before any store lock in ascending
  thread id, and whoever takes a hold releases it (a queued absorption's
  finisher too). W8's writes are bound to the thread and session decided
  on (`stop_seen(thread_id=…)`, the field's compare-and-set, the seat's
  write guarded on its occupant), and a launch that lost its banner while
  a background process of the session runs goes through W8. `--wait` reads
  the transcript incrementally and stops at the next prompt, writing the
  seat `idle` only while no later turn runs. `SMINOS_LAUNCH_TIMEOUT`
  (default 300) bounds a launch, for the timed-out row's test.
- 2026-11-20 — **For M4, from the holder on M2's decisions.** A `fill
  --resume` whose task the endpoint refuses after the seat's return says
  both facts, that the seat returned and that the task was refused, and does
  not exit as "retired". A `resume` held for the endpoint on a cut-over
  machine stops no turn (a consequence of recording first: the verb's
  message is the endpoint's to admit), so its line says the turn was not
  stopped and that the message follows on the endpoint's answer. And the
  general rule behind M2's last fix: whatever a verb must write once the
  process is live is checked writable before the launch (a retired seat
  whose project cannot be read is refused, not returned).

- 2026-11-20 — **The `mode` words** (the holder, on M3's draft). §5's `mode`
  reason reads `a wake would run it in a mode that asks for approval`, true
  whether the thread's own mode or the ceiling is the cause, since X3
  publishes `mode` alone and a remote reader cannot tell the two apart. On
  the thread's own machine (the sender's line there, and `list` there) the
  ceiling case names the ceiling's value and whose setting it is, never how
  to raise it: its reader is usually a session, and the policy is the
  owner's to change. `hold_verb`'s interim words in M3 stand until M4
  replaces the verb; M4 checks that T1's "only if its human reopens" phrase
  is gone from the tree.

- 2026-11-20 — **M3 as built, and what its reviews moved.** A hold of
  either kind of thread is one answer, `hold_of`, carrying the thread it
  was decided for (`Hold`, a `str` with `.thread`); every mark names that
  thread, never a stamp read again after the decision. `derive` keeps T1's
  rule by its own predicate (`stopped_human`). A plain `send` to a current
  thread with no answering peer is recorded and delivered as `say`'s
  (`deliver_sent`, `deliver_next(due=True)`), the thread's hold decided
  before any endpoint gate (words, reach) on a cut-over machine too; a
  recipient this machine already holds keeps T1's atomic `held_record`. A
  delivery's wake of a seat skips `resume_session`'s own config-dir and cwd
  refusals: the wake's `not_woken` decides them as holds. Every `held:`
  outcome marks, the passing ones (`starting`, `in flight`, `sweep`,
  `pending`, `unknown`, `busy`) included; the daemon remembers only the
  facts and `failed`, the latter until due, and its memory's key names a
  guarded directory (withheld, or a human-opened thread's in a protected
  folder) by path and answer, never by a stat inside it. A bounded reading
  that found no mode is no definitive answer: it is asked again until a
  whole reading answers. An event for the live alone settles `recorded` at
  the endpoint's late verdicts too. A thread whose own record is there and
  unreadable is `held:unknown` for that thread id: owed through a words
  timeout, asked of no endpoint, pushed nowhere; a stale mark settles
  `recorded` only when another thread positively holds the session, and an
  unknown binding defers. One deadline serves `wake_due` and the memory. The
  core suite's give-up at the 60th attempt now pins a wake that fails as
  held, never given up. `hold_verb`'s interim words stand until M4.

## Outcomes & Retrospective

Pending — written at finish.
