# sminos threads, T1 — identity and lifecycle: execution (2026-11-17, revised 2026-11-18)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **T1** (Threads: identity and lifecycle — plan). **Parent pin:** `main`
> `8393570c`, that file's blob `d21cf69123c465a9251facd64644ebada7c6a2e0`.
> The child's section there is its spec, D1 and D7 its design, X1, X2, X3, X6,
> X7 and X9 its contracts. This document carries the constraints and the
> milestones and nothing of the design. Read before M1: the composite's
> Purpose, Grounding Baseline (the sminos part and its table), Terms, D1, D7,
> D2's "Not woken" and D4's paragraphs on ownership (what T2 and EN build on
> what T1 leaves), the T1 section, the Cross-Child Contracts (X9 holds
> devcloud's command as built), its Decision Log's last entries, and
> `docs/doperpowers/research/2026-11-17-sminos-channels/clear-compact-experiment.md`
> (what the engine does at a `/clear`, an in-session `/resume`, a fork and a
> compaction). The
> code map the composite cites
> (`docs/doperpowers/research/2026-11-17-sminos-channels/code-map.md`, §1 and
> §5) locates most of what changes; its line numbers have moved, its function
> names mostly have not.

After this child a session its human opened no longer leaves its project when
its terminal closes. It stays, listed `stopped`, under its name and its
in-charge line; what is sent to it waits and reaches it when its human opens
it again. It ends only when it is retired or has been stopped for more than
three days, and it comes back as itself when it is reopened. Nothing wakes
such a session yet (T2 does), and a sender is told so as it sends. A session
sminos spawned is woken as today. How to see it working is T1's acceptance in
the composite, run as Concrete Steps gives it.

## Progress

- [x] (2026-11-17) The plan written against the code at `main` 279bb44a.
- [x] (2026-11-18) Revised for its adversarial review (fourteen findings, each checked in the code) and the composite holder's rulings, at the pin above.
- [x] (2026-11-18) Revised again for the confirm pass (eight findings) and the holder's second rulings: transitions are journaled in the record.
- [ ] M1 — Every member has a thread record, and its events say which thread
- [ ] M2 — One thread across its session ids: hand-off, refill, and what is another thread
- [ ] M3 — A closed session stays: stopped, held, and its sender told
- [ ] M4 — A thread ends, and returns
- [ ] M5 — A thread that owns a VM is neither retired nor ended
- [ ] M6 — What sessions are told, an older sminos beside this one, the shared vectors, and the acceptance run

## Words this document adds

The composite's Terms define thread, seat, member, lane, wake and the daemon.
Added here, each used below without further explanation:

- **Spawned** and **human-opened**: how a thread was opened, the two values
  of its record's `opened` (Interfaces §1). A spawned thread is today's seat.
- **The seat store** is `$SMINOS_HOME/*.json`, where a seat's record lives
  today and where every released sminos looks for seats (`record_files` in
  `sminos/skills/sminos/scripts/sminos.py`). **The thread store** is
  `$SMINOS_HOME/threads/`, which no released sminos reads.
- **Stamped**: carrying the field `thread` as a non-empty string. An event
  is stamped; a `joined` or a `retired` written by a sminos from before
  threads is unstamped.
- **In effect**: a session's membership in effect is its latest own `joined`
  or `retired` once the events the reader rule passes by are left out,
  as the one reducer of Interfaces §3 answers it. "A member" below means
  a session whose membership in effect is a `joined`.
- **The journal**: a record's `pending` entry, which says what a
  transition still owes after its record was written (Interfaces §6). An
  entry is **open** until it is cleared.
- **Episode**: one stretch of a session's events under one thread id. A
  session that leaves a thread and later runs again under another has two.
- **Short id**: the first eight characters of a session id, what `@short`
  and `alias#short` carry and what devcloud keeps of a VM's creator.
- **The hold**: what happens to a message addressed to a stopped
  human-opened thread until T2 ships. It is recorded, stays owed, and
  starts no process.
- **The thread sweep**: the daemon's pass over this machine's threads (M3,
  M4), run by `sminos daemon run` and by `sminos daemon tick`.
- **The census**: the one question to devcloud that the thread sweep's
  ending pass rests on, asked by a child process of the daemon (M5).
- **The engine**: Claude Code, the `claude` CLI. Its **session record** is
  the file it keeps per running process under its config directory
  (`peer_records` reads them); sminos's own **session record** is
  `sminos_records.py`'s, which holds a session's owners and reach. Where
  the two could be confused the text says whose.
- **The driver**: devcloud's VM driver, `devcloud vm …`, which runs on a
  Mac that holds a seed key and nowhere else.
- **Cut over**: a machine whose sminos is enrolled at a MAWS endpoint
  (`daemon/identity.json`). There a person's words, and where the endpoint
  says so a peer's, are delivered only on the endpoint's verdict
  (`WordsGate`, `ReachGate` in `sminos.py`).

## Constraints that bind every milestone

- **The composite has one writer,** the session that holds it. This
  document's controller records decisions and discoveries here and sends
  that session whatever touches the child's purpose, its acceptance, an
  edge, a contract or a binding decision; it never edits the composite.
- **What binds, by id.** D1's paragraphs marked binding (every lane A member
  is a thread; naming a thread; continuation and refill; a `/clear` starts
  another thread; lifecycle; verbs that start a process) and D7 whole. X1
  and X2, whose names Interfaces fixes: a change to one of those names after
  M1's review is a Decision Log entry and a message to the composite's
  holder before T2 or CH starts. X3 (the first values only; the contract is
  T2's). X6, X7, X9.
- **A wrong continuation cannot be undone** (D1): it hands one session's
  record owners and reach to another. The one continuation is the engine's
  hand-off to a background job, read from the record the engine leaves, as
  today. Where that evidence is missing or doubtful, the new session is
  another thread. A missed continuation costs a name; a wrong one is a
  privacy fault.
- **Two relations, never merged.** *Continues* (a `retired` with reason
  `continued` and `to`) carries record owners and reach, and is what
  `lineage_provenance`, `ensure_record` and `_member`'s owners read. *Same
  thread* (the `thread` field) carries the name, the alias and the
  in-charge line, and nothing of reach. A refill is in the second relation
  only, and so is whatever a witness other than the engine's hand-off
  record shows (the session a `/clear` left, M3).
- **A thread id names no session.** A human-opened thread's id is minted;
  nothing an event carries in `thread` tells a reader of one audience the
  id of a session written for another.
- **Lane B keeps today's rules entirely** (D1). Whether a session is lane A
  is read by one function, the one the endpoint's `member` frame is built
  with, so a session is a thread exactly when sminos tells the endpoint it
  is lane A.
- **Older code on the same machine** is defended by D7's two rules and
  nothing else: a human-opened thread's record is in the thread store, and
  every reader that knows threads passes by an unstamped `retired` with
  reason `ended` for a session whose latest `joined` is stamped. What D7
  lists as accepted is not defended. There is no store version and no
  fence. The three rules that read an older copy's writes (Interfaces §6)
  apply only to a record with no open entry.
- **The record is written first, and it journals what it owes.** Every
  transition that writes a record and an event writes the record first, as
  `_retire_one` orders a retire today, and that one write carries a
  `pending` entry naming the events and the clean-up still to come
  (Interfaces §6). A process can die at any point after it. A
  reconciliation that meets an open entry finishes exactly that entry, and
  nothing else is done to a record while its entry is open. Nothing is
  inferred from how a record and the log compare; no transition has a step
  that only its own process can complete; and nothing is deleted or moved
  out of the live scan before its entry's last step.
- **What a session reads keeps today's words** (X6): the guide, the skill,
  the spawn preamble, `sminos help` and a verb's output say session, seat
  and member. "Thread" appears in code, in records and in the event field.
  The rewrite into the new words, and the manager's skill, are CH's. Each
  milestone writes the lines its verbs print; M6 evaluates them with the
  skill.
- **`sminos/skills/sminos/scripts/sminos.py` is one file of some fourteen
  thousand lines,** and T2 changes the same functions after this child.
  New logic goes in `sminos_threads.py`; `sminos.py` gets calls at seams.
  `origin/main` is merged before M1, before M5 and before the final push.
- **Nothing new at the root of `$SMINOS_HOME`.** `record_files` reads every
  `*.json` there as a seat, in this code and in every older one. A new file
  goes in a directory of its own.
- **The hook is bounded** (`run_record`, 5 s). A thread-record write made
  from the hook waits for its lock only until the hook's deadline and is
  skipped past it, for reconciliation to make later.
- **The idle daemon stays cheap.** Thread records are read as seat records
  are (`_seat_at`: again only when a file's stat changed), the plane's idle
  read counts them among its inputs (`Plane.stale`, `inputs` in
  `sminos_plane.py`), and stopped threads now stay members for up to three
  days, so every per-member duty of the tick loops over more of them. No
  per-tick duty reads an ended thread's record, runs devcloud, or reads the
  whole log for a thread that is held. The `sminos-idle` gate is the check.
- **Tests are hermetic.** The suite's stub `claude`, its temporary `HOME`
  and `SMINOS_HOME` stay the only engine and store a test meets. No test
  reaches a real devcloud driver: the suite's shared setup points the
  lookup (M5) at a stand-in. Fixtures use invented names; the repository is
  public, so no hostname, account name, project id or local path enters a
  test, a comment or this document.
- **The manager's command imports the CLI's modules**
  (`sminos/skills/manager/scripts/`). It reads `Member.former` as the
  transcripts of one conversation, so that field keeps today's meaning. Its
  tests pass after every milestone and its skill is not touched; a sentence
  of its scripts' `CLAUDE.md` that a milestone makes false is corrected in
  that milestone.
- **One change, one version.** The child merges as one pull request that
  leaves the repository releasable beside an older sminos on another
  machine (D7), with sminos's version bumped in it
  (`scripts/bump-version.sh --plugin sminos`). It adds no event kind: an
  older reader meets new fields only (`thread`, `wake`, `closed`), which it
  does not read.

## Plan of Work

T1 changes one state machine: a thread's record on its machine and the
lifecycle events that machine writes about it. M1 gives every member the
record and the stamp, under today's rules, with the journal that finishes
a transition its process died in. M2 says which session ids are one thread
and makes any of them reach the current one. M3 replaces "its process ended,
so it left" with `stopped` and the hold. M4 adds the two ways a thread ends
and the two ways it returns. M5 puts devcloud's answer in front of every
path that ends one. M6 changes what sessions are told, checks an older
sminos against the new store, checks the vectors shared with MAWS against
its master, and runs
the acceptance.

Each milestone ends with the suites green for what it touched and with the
nested `CLAUDE.md` beside the code it changed, and `sminos help`'s text
(the module docstring of `sminos.py`), true again. The skill, the preamble
and their evaluation are M6's.

**One unit.** The composite sees one unit with one verification strategy, and
so does this plan after its review: one state owner (the thread's machine),
one store, one hermetic suite, to which the review added one kind of test (a
failure injected at each step of a journaled transition). Two parts are
verified differently (M5's question to another program, M6's evaluation
of text and its pass on a real engine), and each is small and cannot land
without the rest: M4 without M5 would end the owners of VMs, and M3 without
M4 would keep every closed session forever. If the unit had to be cut, the
seam is after M2: the record, the stamp and the naming change nothing a
session sees and are what T2, CH and EN read, and M3 to M6 are the
lifecycle. M3 is the largest milestone; if its diff is more than one review
pass holds, it is cut after the hold: the verbs that start a process and the
closing of questions can follow it, since until they land those verbs find
no seat for a human-opened session and refuse.

### M1 — Every member has a thread record, and its events say which thread

**What exists at its end.** Every lane A session of this machine that is a
member has a thread record from its first join: a spawned one in its seat
record, a human-opened one in the thread store under an id of its own.
Members and seats that existed before are adopted the first time this code
reconciles them, with every session id they have had. Every lifecycle event
sminos writes for such a session is stamped, and `sminos list --json` shows
each member's `thread`. A reader that knows threads still counts a member
after an unstamped `ended`. The record and the log agree under today's
rules, and a transition whose process died is finished by the next
reconciliation: a human-opened session still leaves when its process ends, now by a
stamped `ended` its record holds too, and comes back when it runs again. A
member whose lane changes is told gone to the endpoint before its new frame.

**What it touches.** New: `sminos/skills/sminos/scripts/sminos_threads.py`;
`sminos/tests/test_threads.py`, registered in `run_suites` of
`sminos/tests/run-sminos-tests.sh`; `channel-rule.json` and its pin under
`sminos/tests/vectors/maws/`, with `sync.sh` there taking the file's name.
In `sminos.py`: `lifecycle` (the stamp, and the record's copy of the alias),
`join_on_sight`, `joinable`, `join_seat`, `spawn_fresh` and `cmd_seat_add`
(the record at first join), `_reconcile` (adoption, the journal's replay, an older copy's writes),
`cmd_retire`, `_retire_one` and `cmd_remove` (the
record before the event, for a human-opened session too), the readers of
membership below, `_member`, `Member` and `member_json` (`thread`,
`opened`), `cmd_record` and `record_session` (the launch's options, and a
launch's child). In `sminos_records.py`: `lane_of`, which `member_frame` in
`sminos_uplink.py` then calls. In `sminos_uplink.py`:
`publish_members` (`gone` at a lane change). `Plane.stale` and `inputs` in
`sminos_plane.py`.

**Interfaces.** Exposes the thread record (X1, Interfaces §1), the stamp
(§2), the reducer and the reader rule (X7, §3), the journal and the
transitions of §6 that are in force under today's lifecycle, and `lane_of`
(§8). Consumes
nothing.

**Decisions.**

- *Two stores, one module.* A spawned thread's record is its seat record,
  where it is, with keys added; a human-opened thread's is a file in the
  thread store. Reason: D7 needs the second where older code reads no
  seat, and the seat record is also the board pipeline's, which reads and
  writes it directly under `.metalock`, so moving it would break a second
  consumer. The module gives both one view. Existing writers of a seat's
  own fields (`meta_set` callers, the pipeline) go on writing them; the
  module reads a seat record that lacks the new keys with defaults, as
  `load_seat` does for older records, and repairs `sessions` on read when
  `current` moved without it (an older CLI's refill, the pipeline).
  *Alternative: one new store for every thread, beside the seat record.*
  It lost because a spawned thread would then have two records that can
  disagree on `current`.
- *The thread id* (the holder's ruling on the review, which changes D1's
  lean). A spawned thread's is its seat id, which its `joined` events
  already publish in `seat`. A human-opened thread's is a UUID minted when
  its record is made, never a session id: the stamp rides every later
  session's events, and under a refill or a change of reach those are
  written for another audience than the first session's. Nothing needs the
  id to be a session's: a name recorded before threads existed (a
  `Sminos-Session` line, a VM's creator tag) names a session, and a session
  id resolves to its thread (M2).
- *Transitions are journaled in the record* (the holder's ruling on the
  second review). An end, a return, an advance, an absorption and the
  release of an alias (Interfaces §6) each begin with one write of the
  record that makes its change and adds `pending`: the operation, the
  events it owes with their fields, and what follows them. The events are
  appended, each carrying the entry's id, so that one already in the log is
  not appended twice; what follows is done; and `pending` is cleared last,
  in the same write that sets a record aside or deletes it. A
  reconciliation that meets an open entry finishes it, and a transition
  that meets one finishes it before its own. Not journaled, because a rule
  that exists already finishes each: a first join and an adoption (a
  record whose session has no `joined` in effect is joined on sight, as a
  seat with no membership event is today), and the stop mark, which owes
  no event. *Alternative: rules that tell an unfinished transition from
  how the record and the log compare* (this plan's first revision, eight
  of them). It lost in review twice over: a return cut short could not be
  told from an end cut short, and a stamp does not prove who wrote an
  event in a project a git mirror merges.
- *An ended human-opened record moves aside,* into `threads/ended/`, as
  the last step of its end (§6). Reason: D1 keeps an ended thread's
  record, every closed terminal session becomes one, and nothing bounds
  their number, while the daemon reads the live ones at every tick. No view
  lists from that directory; it is read when a session of an ended thread
  runs again.
- *`opened` is fixed when the record is first made, and no verb changes
  it.* A record that begins as a seat (a `spawn`, a `seat add`) is
  `spawned`; one that begins on sight is `human`. Every seat that exists
  when this code first runs is `spawned`, so nothing that is resumed today
  stops being resumed.
- *A spawn's child is never recorded `human`.* `spawn_fresh` starts the
  engine before it writes the seat's record and learns the session's id
  only by polling, and today the child's own first hook joins it as a
  seat-less background session before its seat names it. The child's
  environment carries its launch's token (`SMINOS_LAUNCH`), and the token
  decides, whatever became of the binding file a hook writes for it
  (`claim_launch` swallows a failure to write one). A hook whose
  environment carries a token makes no record and writes no `joined` for a
  session no seat holds, while the launch is still pending (its provenance
  waits to be claimed) or the session's process is younger than the
  spawner's own bound (Interfaces §8). Its seat joins it when the launcher
  learns its id. The token stops counting when the launch is positively
  gone: it is bound to another session (a `claude` started from a seat's
  shell inherits the variable), or it is neither pending nor young (the
  launcher failed: on a banner it cannot read it drops the pending launch,
  the engine already started, and makes no seat). Then the session joins
  as any session with no seat does, as today. A reconciliation in another
  process sees no token, so it makes no first record for a seat-less
  session the engine records as `bg` whose process is younger than that
  bound; a background job that continues another session is not delayed,
  since it gets no record of its own (M2). When a launcher that was slower
  than the bound learns its session's id and finds a human-opened record
  holding that session alone, the seat absorbs it (M2's operation).
- *`seat add --session` aimed at a session that already is a human-opened
  thread is refused,* saying that its record already keeps it. Reason: D1
  says such a thread does not take a seat's fixed alias and project, a
  thread has one record, and the seat would be the way around D1's rule
  that no verb but the wake starts a process for it. For a session with no
  thread the verb does what it does today: the core suite makes most of
  its seats this way, around invented sessions. Where an older CLI gave
  such a session a seat anyway (D7), `thread_of` answers the human-opened
  record: it wins.
- *Adoption is lazy and writes one event.* The first reconciliation by
  this code of a local lane A session whose membership in effect is an
  unstamped `joined` makes the record and joins it again, stamped, as
  `publish_owners` joins a member again (`joined_again` gives the fields).
  Only a membership in effect qualifies: a session whose latest `joined` is
  unstamped and that was since retired, moved, continued or replaced is
  left as it is. The same rule stamps again a member an older copy joined
  since: a session started before the update runs the older hooks for as
  long as it lives, and their `refresh_joined` and `publish_owners` write
  an unstamped `joined`, after which the older code's `ended` would be
  honoured. A stamped `joined` followed only by an older copy's `ended`
  needs nothing: the event is passed by.
- *Adoption rebuilds `sessions` from what exists.* A human-opened member's:
  its continuation chain in this machine's log (`lineage_of`), oldest
  first, then itself. A seat's: the sessions its `history` holds, the
  sessions whose `joined` in the project's log carries the seat's id in
  `seat`, the hand-offs among them, then `current`. Reason: M5 asks
  devcloud about `sessions`, and a VM made by an earlier occupant of a
  refilled seat, or by an earlier session of a chain, names only that
  session. Nothing of provenance is read or written here.
- *A thread record is evidence of membership,* as a seat is: `joinable`
  answers yes for a session whose human-opened thread has not ended,
  whether or not a process runs it. The first join keeps today's test (the
  engine records it `interactive` or `bg`, no headless run unless marked).
- *One reducer reads membership* (Interfaces §3). `in_effect` answers the
  event that decides a session's membership, with its reason and its
  destination (a `moved`'s project, a `continued`'s successor), and every
  reader goes through it, none left on the raw last event:
  `latest_membership` and every guard built on it (so an older CLI's
  unstamped `ended` neither makes this code join the member again nor
  stops a later event of its own), `_memberships`, `_projection`,
  `_lineage_scan`, `recorded_project`, `last_project`, `moved_here`,
  `handed_to`, `hand_off`'s reread after its append, `retirement_holds`,
  `closed_sessions` in `sminos_outcomes.py`, `rejoin_former`,
  `publish_titles` and `restate_withheld` in `sminos_daemon.py`,
  `sminos_visibility.py`'s snapshot, and `owed_in`. Reason for no
  exception: a reader of the raw last event answers the source project for
  a session that moved and whose older copy then wrote `ended`, and loses
  a `continued` behind such an `ended` (the vectors' fifth case). The
  executor finds any other reader by what it reads (`MEMBERSHIP`, a
  `retired` event's `kind`) and gives it the same.
- *The rule's cases are MAWS's file,* `channel-rule.json`, whose `retired`
  list this milestone's test runs through the reducer and through each
  reader named above.
  The copy is made by `sync.sh` from MAWS's master at
  `8a7f308ffc7b7ef6f2179d9e97fd4935a80d2707`, where the file is at version 1
  with five `retired` cases (sha256
  `7cd64b2dbd5a97c28e8640f3e5e44c5574a9f2377d8ac0765788b0227b748f52`), and
  pinned to it. One pin per vendored file (`channel-rule.PIN.json` beside
  `PIN.json`, which `project_rule_parity.py` reads as it is), so that
  vendoring this file does not move the project rule's pin. The check
  fails on a copy whose hash is not its pin's.
- *What `launch` holds* (X1's "the launch's options", which T2 reads): the
  launch directory, and the options of the engine process that last
  started the thread's current session, kept only for the option names in
  one list in the module and never a value that is inline JSON, so that no
  secret enters a record (`sminos_records.py`'s rule). For a spawned
  thread they are what `claude_args` passed; for a human-opened one they
  are read from the process's own argument list at each `SessionStart`
  whose source is `startup` or `resume` (the hook's `CLAUDE_PID`), with
  exact argument boundaries: the kernel's argument vector on macOS, as
  `_darwin_start` already asks the kernel for a start time, and
  `/proc/<pid>/cmdline` on Linux, never `ps`'s joined line, in which a
  path holding a space is two values. Where the arguments cannot be read,
  or the process is one of the engine's pre-started background ones, whose
  arguments are not the session's, `options` is absent, which a reader
  takes as unknown, never as none. Reason: a session that stops before T2
  ships would otherwise have nothing for T2's first wake to carry or to
  name as not carried. The mode and the model are not recorded apart (the
  composite's Decision Log); T2 reads them from the transcript.
- *`gone` before a frame whose lane differs from the one last sent,* in
  `publish_members`, so the endpoint withdraws the old listing before it
  takes the new one. MAWS's endpoint will withdraw it on its own when a
  `member` frame states the other lane (its child MW); sminos's `gone`
  stays, and is harmless beside it.

**What it does not touch.** Which sessions are one thread, and how a
former id resolves (M2). `_reconcile`'s `ended` for a process that is gone,
beyond writing the record with it (M3). Delivery, the daemon's duties.
What sessions are taught. The alias and project rules of either kind of
thread: a spawned one's alias stays fixed and `join` stays refused for it;
a human-opened one is named and moved as today. The `channels` field
beyond creating it empty and carrying it.

**What it proves.** Acceptance 7's first half (the stamp); the reader half
of acceptance 10; the lane half of 8; 11 for its surface. Its tests pin:

- a session that joins on sight has a record in the thread store under an
  id that is no session's, and none in the seat store; a spawned one has
  the thread keys in its seat record and nothing in the thread store; a
  lane B session has neither and its events are unstamped;
- a spawn's child, with the launcher paused before it learns the session's
  id: its own hook, and a reconciliation from another process, each make
  no record and write no `joined`; when the launcher goes on there is one
  seat record, one `joined` stamped with the seat's id, and nothing in the
  thread store. The same when the hook's binding cannot be written. With
  a banner the launcher cannot read after the engine started: no record
  while the process is young, then joined as a session with no seat is.
  With the launcher paused past the bound: the human-opened record made
  meanwhile is absorbed when it goes on;
- a member and a seat from before threads are adopted at the first
  reconciliation, with one stamped `joined`, and no second one at the next;
  an unstamped `joined` written after it is stamped again, once;
- a session whose latest `joined` is unstamped and that was then retired by
  hand, or moved by `join`, is not joined again by adoption, in either
  project;
- an adopted, already refilled seat's `sessions` hold its earlier
  occupants, and an adopted member's hold its continuation chain;
- the `retired` cases of the vectors through the reducer and through each
  reader named above; a session that moved, its destination's `joined` not
  yet written, then an older copy's `ended`: every reader answers the
  destination; a session continued, then an older copy's `ended`: its
  successor is still found. A guard under a writer file's lock reads
  through the reducer: after an unstamped `ended`, a later event of the
  session's own is still appended;
- record and log agree after each of today's transitions: its process
  gone (ended, the record set aside), run again (returned), retired by
  hand, moved by `join`;
- the journal, for an end and for a return, with the process killed after
  the record's write, after the event, and after the settlement: the next
  reconciliation finishes the entry, appends no event twice, and a second
  one does nothing; a second registry that holds only the log reads the
  same membership as the first; a record with an open entry is never set
  aside or deleted;
- an older copy's unstamped `retire` of a thread ends its record; a new
  process then reopens the session and is killed before its `joined`: the
  return is finished as a return, and the record is not ended again. An
  older copy's unstamped `ended` after a stamped `joined` changes nothing;
- `seat add --session` on a human-opened thread is refused, and on a
  session with no thread makes the seat as today; a session with both a
  human-opened record and a seat an older copy made answers as
  human-opened;
- a record write from the hook that cannot have its lock in time is
  skipped and made by the next reconciliation;
- launch options: a path with a space is one value, an inline JSON value,
  an option outside the list and any value that names a session are not
  recorded, and an unreadable argument list leaves `options` absent;
- a lane change sends `gone` first;
- the plane's idle read sees a member's row move when only its thread
  record changed.

### M2 — One thread across its session ids: hand-off, refill, and what is another thread

**What exists at its end.** A session the engine hands to a background job
goes on as the same thread, a human-opened one as a seat does today: the
same thread id, alias and in-charge line, with the record owners, access and
shares the old session had. A refill (`sminos fill` without `--resume`, a
`spawn` onto the alias) keeps the thread id, alias and in-charge line and
takes its owners and reach from its own launch. A tag, a verb's target or
`sminos who` that names the thread id or any session id the thread has had
(`@short`, `@alias#short`, a full id) reaches its current session, on a
machine that only reads the log too, and for a session id from before
threads. A `/clear`, a fork and an in-session `/resume` each leave the new
session id with a thread of its own and no link to the session it came from,
and a fork's start guide says it is a copy with an identity of its own.

**What the engine does at these starts is settled** (the composite's
`clear-compact-experiment.md`, engine 2.1.327), and the milestone runs no
check of its own. A compaction keeps the session id, so it is no
continuation and nothing is built for it (the composite's Delegated
unknown, discarded). A `/clear` ends the old session and starts the new one
in the same process, and by the new session's start nothing the engine
offers names the old one. An in-session `/resume` starts its target while
the process's engine record still names the session it left. A fork is a
copy in another process, with nothing naming its original.

**What it touches.** In `sminos.py`: `hand_off` and `follow_seat` (the
record advances with the session, for a human-opened thread as for a
seat), `join_on_sight` (a job that joined before its hand-off was
written), `spawn_fresh` and `cmd_seat_add` (a refill advances the thread),
`_projection`, `lineage` and `_member` (episodes, `thread_sessions`),
`retirement_holds` (the process that handed off), `match_members`,
`find_target`, `_resolve_tag`, `alias_reach`, `who_matches` and `who_lines`
(a former id, and the thread id, as names), `guide_text` (the fork line).
`sminos/tests/test_threads.py`, `sminos/tests/test-guide.sh`,
`sminos/tests/test-who.sh` and the core suite's hand-off and occupancy
cases.

**Interfaces.** Consumes M1's journal, `thread_of`, `ensure` and the
stamp. Exposes the advance and the absorption (Interfaces §6), the
continuation and refill event shapes (§2), the resolution rule and the episode rule (X2, §4), and
`Member.thread_sessions` (§8).

**Decisions.**

- *The continuation is today's, and nothing is added to its evidence.*
  `continued_in`, `predecessor` and `handed_to` decide that one session
  continues another; `hand_off` records it, and already carries the cursor
  and the join override, moves a seat, retires the old session
  `continued` and renames the new one. Its record write becomes the
  journaled advance: the thread's record names the new session and owes
  the old one's `continued` and the new one's `joined` under the thread's
  stamp, so a hand-off cut short is finished from the entry, the new
  session's `joined` too when the old retirement is already in the log.
  A hand-off whose log part an older copy wrote is finished the same way.
  The one call that carries reach stays `ensure_record(…, former=[old])`;
  nothing else passes `former`.
- *A job that joined before its hand-off was written is absorbed.* The
  engine may write its hand-off record after the job's first hook, and
  `_reconcile` finishes such a hand-off later, as today. By then M1 has
  given the job a human-opened record of its own. The absorption is an
  advance whose entry also names that record: the thread takes the job as
  its current session, the job is joined again under the thread's stamp,
  and the job's own record is deleted as the entry's last step and by
  nothing else. It lives in the record of the thread that goes on, so a
  seat that absorbs a human-opened record writes under one lock at a time.
  The guards are read before anything is carried: the job's record is
  human-opened, has not ended, holds that one session and has no open
  entry. When they fail the hand-off is not recorded at all:
  `ensure_record(…, former=[old])` is not called, nothing of reach moves,
  the two stay two threads, and `daemon.log` says so once. Nothing of
  reach is merged in an absorption either, because a thread record holds
  none: the job's sminos session record gets its predecessor's provenance
  by that one call and no other way. What becomes of a channel membership
  the job gained meanwhile is CH's (the composite); T1's records hold
  none.
- *A refill keeps today's event:* `retired`, reason `replaced`, stamped,
  with no `to` (the composite took this from the plan's first version).
  A `to` is a reference to another session, and only under reason
  `continued` is it one the two repositories guard: `session_refs` in
  `sminos_audience.py`, pinned to MAWS's `sessionRefs` by
  `sminos/tests/audience-vectors.json`, is what `redact` nulls for an
  audience that may not reach the session named and what the hub checks.
  The stamp links the two sessions without either naming the other.
- *A session belongs to the thread its latest `joined` is stamped with,*
  and a thread's name, alias, in-charge line, status and worktree are read
  from the episodes stamped with its id, never from everything a session
  ever wrote (Interfaces §4). Reason: a session that leaves a thread can
  run again under another, and `_projection` holds one row per session
  today, so the second thread's in-charge line would become the first's.
  An event that carries no stamp of its own (another writer's line about
  the session, an event from before threads) belongs to the episode its
  time falls in. Owners stay read along the continuation chain alone.
- *`Member.former` keeps today's meaning,* the continuation chain: the
  manager reads it as the transcripts of one conversation. The other
  sessions of a member's thread (a refill's predecessors) are
  `Member.thread_sessions`. A name is matched against both.
- *A name's order.* A name that is a member's current alias or current
  session comes before one that only matches a former session or alias,
  as `match_members` orders a former alias today. The thread id is matched
  like a session id, in full or by its first eight characters. Session ids
  stay what addresses a message: the event names the current session.
- *A session id from before threads resolves.* Its events carry no stamp:
  an unstamped `joined` that names a seat in `seat` reads, for naming
  alone, as that seat's thread, and an unstamped session with no seat
  resolves through its `continued` chain as today. So a VM's creator tag or
  a commit's `Sminos-Session` line that names an earlier session of an
  adopted thread reaches its current one, on any machine. The reader rule
  (§3) never reads `seat` as a stamp.
- *A former session that runs again is another thread.* The cases: an
  interactive session resumed by id after it was handed to a job, and a
  replaced session of a seat resumed in a terminal. Today's code already
  makes the first its own member and drops the link (`_projection`: a
  `joined` after its own `continued` clears `to`). It gets a human-opened
  record of its own; the thread that went on keeps the session in
  `sessions`, and `thread_of(session)` answers the thread whose current
  session it is before one that only had it. The process that handed the
  session off is not such a return: it lives on for a moment as it exits,
  and `retirement_holds` suppresses its re-join today from the `pid` its
  `continued` recorded. That test stays, for `continued` and `replaced`
  alike: only a process that is not the one the retirement saw, or that
  started after it, makes the new thread.
- *A `/clear`, a fork and an in-session `/resume` are pinned, not built.*
  Nothing in the code links them today, and nothing is added: each new id
  joins on sight (M1) and gets its record owners from its own evidence.
  At an in-session `/resume` the process's engine record names the
  session that was left while the target starts, so nothing here takes
  the session a process's record names for the session a hook is
  starting: the hook's session is its payload's. `_hook_engine` stays
  what it is, a stand-in the guide alone reads, and lends no lineage.
  The tests below hold that line.
- *What the fork line must say* (the copy is M6's, with its evaluation;
  `guide_text` already has a sentence for source `fork`): that this
  session is a copy of another, with a session id and a name of its own;
  that every sminos line above it in its context was written for the
  session it was copied from; and that messages addressed to that session
  are not for it.

**What it does not touch.** How the engine's hand-off is read
(`continued_in`, `predecessor`). `lineage_provenance`'s order of evidence.
A lane B session's continuation (`bind_launched` in `sminos_records.py`,
`session_evidence`'s `former`). That the session a `/clear` left is listed
`stopped`, and who holds its alias (M3). The wake.

**What it proves.** Acceptance 3, but for the `stopped` listing and the
alias of the session a `/clear` left (M3); acceptance 7's second half. Its
tests pin:

- a human-opened session handed to a background job: the record names
  the job as current with both ids in `sessions`, one stamp on both
  sessions' events, the job's record has the old one's owners, access and
  shares, the member lists once under the alias and in-charge line it had;
- a hand-off and a refill, each killed after the record's write and after
  the old session's retirement: finished by the next reconciliation, no
  event twice, nothing done by the one after; a hand-off whose `continued`
  an unstamped writer wrote is finished the same way;
- the engine's hand-off record appended after the job's first join, for a
  human-opened predecessor and for a seat: one thread afterwards, the
  job's own record gone, its latest `joined` stamped with the thread it
  continues, and its owners its predecessor's by the continuation alone.
  Killed before the old retirement, after it, before the job's record is
  deleted and after: each finished the same, and the job's record is there
  until the entry's last step;
- an absorption whose guards fail (the job's record has ended, or holds
  another session): no `continued`, no owner, access or share of the old
  session on the job's record, two threads;
- the process that handed a session off, still running: no record and no
  `joined` of its own; the same session resumed by a new process: a thread
  of its own;
- a refill: one thread id across both sessions, `retired` `replaced`
  stamped and without `to`, the new session's owners from its own launch
  and never its predecessor's (read on another machine's copy of the log
  too), the alias and the in-charge line kept;
- the thread id, and each former session id, as `@short`, `@alias#short`
  and a full id, reach the current session after a hand-off and after a
  refill, from another machine's copy of the log, for `say`, `send` and
  `who`;
- an adopted member and an adopted, refilled seat, each named by the short
  id of a session that has no stamped event: the name reaches the current
  session, from another machine's copy of the log too;
- a handed-off session resumed by id, and a replaced seat session resumed
  in a terminal: each a human-opened thread of its own; from a second
  registry that holds only the log, its full id and its short id name it
  and not the thread that went on, and a rename and an in-charge line it
  writes afterwards change nothing the first thread shows;
- a human-opened thread whose reach changed between two of its sessions:
  a reader allowed only the later stream finds no id of an earlier session
  in any `thread` it can read; a refilled seat's `thread` is what its
  `seat` field already publishes, and nothing else;
- a `SessionStart` of source `clear` under a new id in the process that
  held a thread's session: two thread ids, no `continued` event, no owner,
  access or share carried from the old session's record;
- an in-session `/resume` of another session (source `resume`, same
  process): two threads, no `continued` event, the resumed session keeps
  its own owners, and with the process's engine record still naming the
  session it left, nothing is written for that session under the
  target's id or the reverse;
- a fork (source `fork`, another process): a thread of its own whose
  record owners come from its own evidence, no `continued` event, and
  the guide's fork line;
- a start of source `compact`: the same session id, the same thread,
  nothing written.

### M3 — A closed session stays: stopped, held, and its sender told

**What exists at its end.** A session opened in a terminal and then exited
is listed `stopped` by `sminos list --stopped` and folded by `sminos list`,
under its alias and in-charge line; a new session with its name is told
apart from it as two live ones are today. Reopened with `claude --resume`,
it is live again under the same alias, and what was addressed to it
meanwhile arrives at the next delivery pass. After a `/clear` the new
session holds the alias, as today, and the session that was left is listed
`stopped`, is reached by `alias#short` and its short id, and comes back when
its id is resumed. While a session is stopped an addressed message is
recorded and held, on a cut-over machine too, and the sender's line says the
session is stopped and is not woken because its human opened it, with the
machine it waits on when that is another one. `sminos send` to it is held
the same way; `sminos resume`, `fill --resume` and `send --wait` aimed at it
record their message, start no process and say so; a fresh `fill` of it, or
a `spawn` onto its alias, is refused. A spawned session is resumed exactly
as today. A stopped session's open asynchronous questions are closed in its
project's log.

**What it touches.** In `sminos.py`: `_reconcile` (no `ended` for a
thread), `deliver_next`, `words_due`, `reach_due`, `words_unanswered`,
`deliver_verdict`, `deliver_reach`, `push_member` and `push_event` (the
hold), `resume_session` and
`spawn_fresh` (the two places a process is started for a seat),
`resolve_seat`, `cmd_resume`, `cmd_fill`, `_send`, `send_to_member`,
`deliver_say` (the sender's line), `lifecycle` (X3's field on a `state`),
`cmd_record`, `record_session`, `guide_text` and `held_alias`'s callers
(the alias at a `/clear`), `unreachable_hint`, `who_lines`,
`derive_refusal`. In `sminos_daemon.py`: `publish_state`, `deliver_owed`,
`sweep_threads` (new), `owed_in`. In `sminos_outcomes.py`:
`closed_sessions`, `of_push`. In `sminos_uplink.py`: `expire_asks`,
`on_words`, `ask_peer`. New: `sminos/hooks/smns-cleared.sh`, registered
for `SessionEnd` in `sminos/hooks/hooks.json` and described in
`sminos/hooks/CLAUDE.md`. The
tests that pin `ended` for a session its human opened, in the core suite
and in the suites that hold the word (`test_owed.py`,
`test_session_plane.py`, `test_manager.py`, `test_idle_reads.py`,
`test_scale.py`, `test_holder.py`, `test-uplink.sh`, `test-sync.sh`,
`test-guide.sh`), the sentence of `sminos/skills/manager/scripts/CLAUDE.md`
that says sminos retires such a session once its process ends, and a new
section of `docs/doperpowers/TECH-DEBT.md` (below).

**Interfaces.** Consumes M1's record (`opened`), `thread_of` and the reader
reducer, M1's journal, M2's episodes. Exposes `hold_of`, X3's first two
values and `wake_of` (Interfaces §5), the hold's outcome, `cleared_from`
and the note it reads (§8), the release (§6), the closing
event (§2), and the record's `stopped` mark, which M4's clock reads.

**Decisions.**

- *What ends with its process, and what does not.* Reconciliation writes
  `ended` only for a session that is not a thread: a lane B session, as
  today. A lane B session that has a thread record from an earlier lane A
  life gets that `ended` stamped, so every reader honours it, with its
  record ended first (Interfaces §6, row 13). From here on an older copy's
  unstamped `ended` over an unstamped `joined` of a stopped thread is
  undone by a stamped `joined`, where M1 ended the record to match (§6,
  "An older copy's writes").
- *One predicate says whether this machine holds delivery for a session,*
  `hold_of` (Interfaces §5): a human-opened thread that has not ended,
  whose current session no process holds. An ended thread is not held:
  what is owed to it is settled (M4).
- *The hold stops pushing and asking, and nothing else.* For a held
  session `deliver_next` runs as today, under the session's delivery lock,
  and everything in it that settles without a push still settles: a push
  already noted, a receipt the session's process admitted before it
  exited, a revoked signer, the read-only refusal, and an event that only
  reaches the live (an `@all` or a broadcast that selected the session
  while it ran, which settles `recorded` as for a stopped seat today).
  Where the next step for a writer's head would be a push, or a question
  to the endpoint about one, the outcome is `held:human`, in the `held:`
  family that `_conclude` already leaves owed with no attempt counted, and
  that writer stops there, on the sender's fast path and the daemon's
  alike. When the session runs again the event meets the gates as any
  owed event does.
- *The hold comes before the gates, and on every path that asks.* On a
  cut-over machine the words and reach gates come before the push, and
  the uplink walks the same rows, so a held event would be asked about at
  every pass, and a `words?` the endpoint does not answer in time is a
  failed attempt that settles the event after the attempt limit
  (`expire_asks`, `words_unanswered`, `_conclude`). So `words_due` and
  `reach_due` leave a held session out; an ask outstanding when its
  session stopped counts nothing when it expires or comes back naming no
  verdict; a late `peer` verdict asks no `reach?` for it (`ask_peer`); a
  late verdict that calls for a push pushes nothing and leaves the event
  owed; and a late refusal, of words or of reach, settles as today, since
  it pushes nothing. `push_member` holds too, as the last line: today it
  answers `recorded` for a member with no seat and no process and the
  caller settles the event, which would lose it for the reopened session;
  it survives today only because a closed session is no member, so
  delivery never sees it.
- *An outside sender is told `recorded` once and the event stays owed,* as
  `report_closed` does today for a closed terminal session:
  `closed_sessions` becomes "this machine's sessions `hold_of` holds", with
  today's reading kept for a session that ended before threads. A
  read-only machine settles what comes from outside as it does today.
- *What a held backlog costs.* The tick may pass a held session by without
  `deliver_next`, but only on the memory of a pass that ran: one in which
  every writer came out `held:human` and nothing was settled, and only
  while nothing that pass read has changed (the events addressed to the
  session, its delivery record, its receipts, the revocation set, the
  machine's policy). So a writer's head the skip passes by is always an
  addressed event for which a full pass found nothing to settle. A tick
  then pays for a held session that one comparison, and no read of the
  log, no lock and no ask. The backlog is bounded by M4: at three days the
  thread ends and what is held is settled. `daemon owed` counts an event
  held for a session among those waiting for closed sessions, which is not
  a debt and does not make it exit 1: `owed_in` decides that before it
  counts a member's owed events as deliveries or words, where today it
  tests membership first.
- *A held event does not follow a continuation.* A stopped session
  reopened and handed to a background job before the next delivery pass
  leaves the event addressed to the old session id. `_owed` reads no
  lineage, and everything after it is keyed by the addressed session (the
  delivery record and its lock, receipts, the reach gate's decision, the
  outcome): following it would deliver to one session under a decision
  made for another. The event stays in the log, the job reads it at its
  next `chat` through the cursor `hand_off` carries, and nothing counts it
  as owed, as for a live session handed off with something owed today.
  Logged in `docs/doperpowers/TECH-DEBT.md`, in a section for this child,
  with the window (a reopen and a hand-off inside one daemon interval) as
  what would promote it. Never across a refill.
- *Two places start a process for a seat, and both hold for `human`.* D1
  says every such path ends in `resume_session`; a fresh fill does not: it
  goes from `cmd_fill` or `cmd_spawn` to `spawn_fresh`. Each checks, under
  the seat's lock, the session the seat holds: when a human-opened record
  names it (an older CLI gave such a session a seat, D7), `resume_session`
  holds and `spawn_fresh` refuses, whatever the seat says. T2 replaces the
  hold in `resume_session` with the wake at the same place. `manager
  query`'s and `derive`'s `headless_fork` are outside the rule: each starts
  a headless copy under a session id of its own, marked internal, and no
  process for the thread.
- *The verbs.* `send` to a stopped human-opened session does what a tagged
  `say` does: recorded, held, exit 0. `resume`, `fill --resume` and
  `send --wait` record their message as an addressed one, which is held
  like one (D1), say that nothing was started and why, and exit 4, the
  code for a target a verb cannot reach now: what they were asked for (a
  process, a reply) did not happen, and a script must not read it as
  done. A fresh `fill`, and a `spawn` onto the alias, are refused and
  record nothing. For these verbs `resolve_seat` has to find a thread that
  has no seat; it answers through `find_target`'s rules, so a name that is
  ambiguous for `send` is ambiguous here.
- *X3's value is built where every `state` of a session's own is written,*
  in `lifecycle`, as a `joined`'s publication is built there today: a
  `state` whose word is `stopped` gets `wake` from `hold_of`, whoever asked
  for the event. Reason: `publish_state` is one of four writers of a
  session's state (`sminos_visibility.py`'s snapshot for a newly admitted
  audience, `rejoin_former`, `restate_withheld`), and a value added by one
  is lost when another restates. `publish_state` writes the event again
  when the value changes while the word does not. A sender reads it with
  `wake_of`; where the thread's machine published none (an older sminos
  there), the sender is told what it is told today (D7).
- *The sweep marks the stop.* A thread whose current session no process
  holds gets `stopped` (a time) in its record once that has held for two
  consecutive passes, and loses it when a process holds the session again.
  Two passes, and never while the thread's resume lock is held, because a
  resume stops one process and starts another: one pass between them must
  not read as the session having stopped (`publish_state` gives a word the
  same persistence, and keeps its candidate between ticks the same way).
  "No process holds it" is the test for the session a `/clear` left too:
  its process lives on under another id.
- *Questions are closed while a thread is stopped, not at the moment it
  stops.* At each pass, a thread whose record says `stopped` and whose
  `swept` is not that same time has each `question` of its sessions with
  no `answered` for its `src` closed, and then `swept` set: an `answered`
  appended through `append_host` (which chooses the store and the asker's
  writer, and drops a second copy), with the text and the marker
  Interfaces §2 gives. A pass that dies between the mark and the closing
  is finished by the next, and a thread that is asked again and stops
  again is swept again. A closing is final in the log: the log admits one
  answer per ask, so nothing reopens it.
- *At a `/clear` the alias goes with the process* (D1). The engine keeps
  the session's name, and the session that was left is now a stopped
  member holding that name, so `held_alias` would refuse it to the new
  session (`shadowing`). By the new session's start nothing of the
  engine's names the old one; what does is the `SessionEnd` the engine
  fires first, in the same process, with reason `clear` and the old id
  (the experiment).
  - *The note.* A new hook on `SessionEnd`, `smns-cleared.sh`, keeps that
    payload when its reason is `clear`, as
    `$SMINOS_HOME/cleared/<the engine's pid>.json`, by one write and a
    rename and without starting Python: an ending session's hooks are
    given little time. Nothing in an internal fork.
  - *Who believes it.* `cleared_from` answers the old session only for a
    start whose source is `clear`, from the note the hook's own
    `CLAUDE_PID` names, when the note is younger than a minute (the two
    hooks were half a second apart in the experiment, on an idle machine),
    was written after that process started, and names another session
    than the one starting. It is read and left: the record hook and the
    guide hook both read it, in either order. The daemon's sweep of
    per-session leftovers removes a note whose process is gone.
  - *The transfer.* With a witness, and only when the session it names is
    a human-opened member of this machine whose alias is the engine's name
    for the process, the record hook releases the alias before it joins
    the new session: a journaled operation on the old thread's record that
    sets `released` (the alias, and when) and owes a `renamed` to the old
    session's short id. `released` is what makes the two steps one
    transfer: while it stands, alias selection refuses that name to the
    old session wherever `held_alias` is asked, so a tick between the
    release and the new session's join cannot put the name back, and
    `shadowing` does not count the old session as its holder. It is
    cleared when a process that started after it holds the old session.
    The new session takes the name by today's rule, in the same hook or at
    whichever join comes first, and `guide_text` reads the same witness so
    that its first line names the new session by the alias whichever hook
    runs first.
  - *Afterwards.* The session left is reached by `alias#short`, as a
    former alias is (`alias_reach`), and by its short id; run again while
    the new one is live it keeps its short id, as the second of two live
    sessions of one name does today; and it takes the name back by today's
    rule when nobody holds it.
  - *Its limits.* The witness is used for the name alone: it is never
    `former` to `ensure_record`, and it is never inferred from two
    sessions sharing a name. With no note (the hook was cut off, a session
    whose plugin is from before this one) nothing is released and the new
    session goes by its short id, as a shadowed name does today. A spawned
    thread's alias is its seat's and does not move.
- *`derive` does not fork a stopped human-opened session.* `derive --all`
  forks every local member with enough activity and no line; today a
  closed terminal session is no member, so it is never forked. Keeping it
  that way keeps the daemon from starting an engine in a closed session's
  directory, which for a protected folder is the fault D2 names.

**What it does not touch.** The wake's steps and its other exclusions
(T2). The three-day rule and `retire` (M4). How a spawned thread is
resumed, the protected-folder rule for it included. `sminos decide`.
Whether a machine is on.

**What it proves.** Acceptance 1 and 2; the rest of 3; the question half
of 8; 11 (the tests that pinned `ended` for a session its human opened now
pin `stopped`). Its tests pin:

- its process gone: no `retired`, `stopped` in `list --stopped`, folded in
  `list`; reopened: live under the same alias and in-charge line, and what
  was owed is pushed, in order, at the next pass;
- a `SessionEnd` of reason `clear` and then a `SessionStart` of source
  `clear` in one process: the new session is a member under the alias; the
  session left is `stopped` under its short id with its in-charge line, is
  reached by `alias#short` and by its short id, and a bare `@alias` reaches
  the new one; resumed while the new one is live it keeps its short id; no
  `continued` event and nothing of the old record's owners on the new one;
- the same with the guide hook run before the record hook, and after it;
  with `publish_renames` run between the release and the new session's
  join, over an engine record that still names the old session: the name
  does not go back; with the hook killed after the record's write: the
  `renamed` is finished from the journal;
- no transfer, and the new session under its short id, when there is no
  note, when the note is older than a minute, when it is another
  process's, when it names the starting session, and when its reason is
  not `clear` (an in-session `/resume` leaves none);
- a lane B session still leaves with its process, unstamped when it never
  was a thread, stamped and with its record ended when it was;
- an older copy's unstamped `ended` for a stopped thread: `list --stopped`
  still shows it and reconciliation writes nothing; after an unstamped
  `joined` and that `ended`: joined again, stamped, once. An older tick, a
  tick of this code, an older tick, a tick of this code, over a stopped
  thread and over a reopened one: the count of events stops growing after
  the first round;
- an addressed `say` to it: recorded, still owed after daemon passes with
  no attempt counted, the sender's line as above; from another local
  sender the same; an outside sender's outcome is `recorded`, once;
- what settles without a push still settles for a held session: a receipt
  its process admitted before it exited is settled as sent at the next
  pass; a broadcast that selected the session a moment before it exited is
  settled `recorded` and wakes nothing; a revoked signer's event and a
  read-only machine's outside event settle as today;
- on a cut-over machine whose endpoint gives no verdict: a person's words
  addressed to a stopped session are never asked about and never counted a
  failed attempt, through more passes than the attempt limit; an ask
  outstanding when the session stopped expires with no attempt counted. A
  verdict that arrives after the stop: `words`, `peer` and `deliver` push
  nothing, ask nothing more and leave the event owed; `refuse`, of words
  and of reach, settles as today. Reopened, the event is asked about and
  delivered on the verdict;
- a tick over a stopped session with many held events, after one full
  pass, takes no delivery lock and reads the log no more often than a tick
  over none; a new event for it, or an admitted receipt, ends the skip for
  one pass; `daemon owed` lists the held events as waiting for a closed
  session and exits 0;
- `send`, `resume`, `fill --resume`, `send --wait`, a fresh `fill` and a
  `spawn` onto the alias, each as decided above, with no `claude` call in
  the stub's log;
- a human-opened session that also has a seat record is held, and neither
  filled nor spawned onto;
- the spawned cases of the suite pass unchanged;
- a `state` event for a stopped thread carries the value whichever of its
  four writers wrote it, a newly admitted audience's snapshot among them;
  it is written again when only the value changes; a sender on another
  machine reports it with the machine, and with none published reports
  today's line;
- an open asynchronous question is closed after two passes, once, not
  during a resume's stop and relaunch; a pass killed after the stop was
  marked leaves it to the next pass; a later answer in the reopened
  session appends nothing;
- `derive --all` forks no stopped human-opened session.

### M4 — A thread ends, and returns

**What exists at its end.** A thread stopped for more than three days (a
period a test can set) is ended by an event its machine's daemon writes:
`sminos list` and `--stopped` no longer show it, `--all` does, and a message
addressed to it is refused saying it has ended and how it returns.
`sminos retire` ends a thread, run by another session or by the session
itself, and the end holds after its process exits. Reopened by its human,
an ended thread is listed again under the alias and in-charge line it had;
a spawned one returns when it is filled. A thread on a retired machine
counts as ended on every other machine.

**What it touches.** In `sminos.py`: `cmd_retire`, `_retire_one`,
`cmd_remove`, `unlink_seat_files`' callers (a purge after its event),
`join_on_sight` and `joinable` (the return), `retirement_holds` (its
`retire` half goes: the record says it), `view_of`, `View` and `cmd_list`
(rows for ended threads), `_member` and `Member` (`end`), `has_ended`,
`unreachable_hint` and `no_member` (what a sender is told), `cmd_resume`,
`resume_session` and `send_to_seat` (an ended spawned thread). In
`sminos_daemon.py`: `sweep_threads`' ending pass. In `sminos_outcomes.py`:
`report_closed` (what was held for a thread that ended).

**Interfaces.** Consumes the record's `stopped` (M3) and M1's journal.
Exposes the end events (Interfaces §2), X3's `ended` (§5), `Member.end`
and `has_ended` (§8), which CH's rosters read on a machine that holds no
record.

**Decisions.**

- *An end is one journaled operation with a fixed order* (Interfaces §6).
  The record is marked ended where it is, and for a spawned thread the
  seat's `status` is set to `retired`, the form older code reads as a
  retired seat (D7); the stamped `retired` is appended; what is held for
  the thread is settled; and only then, as the entry's last step and
  after the settlement has succeeded, is a human-opened record set aside,
  or a purged one deleted with its files. The entry says which of the
  two. The explicit retire keeps reason `retire`; the three-day rule
  writes reason `ended`, which the shared vectors already call a stamped
  `ended`.
- *`retire --purge` and `remove` keep their evidence until the retirement
  is published and what was held is settled.* Today the files are unlinked
  before the event. Here they go last, so an interrupted purge is finished
  and never leaves a session joined in the log with nothing on the machine
  that says why. They apply to every thread (D1): for a human-opened one
  they end it and delete its record.
- *A session that retires itself is recorded before it is stopped.*
  `_retire_one` stops the process first today; run by the session being
  stopped, that can end the caller before the record and the event exist.
  A self-retire writes both, then stops what there is to stop.
- *"Reopened" is a process holding the thread's current session that the
  end did not see.* When the end recorded a process (a retire of a running
  session, a self-retire), that is a process with another pid, or one
  started after the end, as `retirement_holds` tests it from the event
  today: the process that ran when the thread was retired does not return
  it, however long it runs on in its terminal. When the end recorded none
  (the three-day rule, a retire of a stopped thread), any process holding
  the session returns it. Reason for the second half: a process that
  started a moment before the end, and that the end's check did not yet
  see, must not stay ended while it runs. A former session that runs again
  is another thread (M2).
- *What returns a spawned thread.* A fill, fresh or `--resume`, and its
  human reopening its session. `send`, `resume` and a tagged message do
  not: they are refused or reported as for a retired seat today, naming
  `fill`. D1 binds "nothing else returns it"; today `resume` revives a
  retired seat (`resume_session` ends in `join_seat`), and that goes.
- *The clock* runs from the record's `stopped` mark, not from the
  transcript's last write: an idle session whose terminal stayed open for
  days and then closed has been stopped for minutes, and a seat that was
  stopped long before this code ran is given three days from its first
  sweep. The period is three days, with an override in seconds for tests
  (Interfaces §8), as `SMINOS_DERIVE_EVERY` is one. Only the sweep ends a
  thread by the rule, on a spacing of its own (hourly; M5 puts a question
  to devcloud in front of it), so no reading verb or hook writes an end.
  On a machine with no daemon a thread stays `stopped` until
  `sminos daemon tick` runs, which is also when anything else of the
  daemon's would happen there.
- *The end is written only for the stop it was decided for.* Under the
  record's lock the ending pass reads the record again and ends the thread
  only when `stopped` is the very time the decision was made for, the
  current session is the same, and no process holds that session by the
  engine's records read afresh (`running_now`), not by the tick's copy of
  them. Only the sweep removes `stopped`, a pass later, so the mark alone
  would let a session that reopened meanwhile be ended.
- *At an end, what is held for the thread is settled,* as it is for a
  retired target today: `recorded`. The events stay in the project's log,
  which a returned thread reads at its next `chat`; nothing is delivered
  again on a return. This bounds the held backlog at three days. An event
  from outside that reaches the log after the end is reported `recorded`
  and settled the same way.
- *The word in lists is `retired`* for an ended thread of either kind,
  today's word for a membership that ended and already in the chart's, the
  TUI's and `--state`'s vocabularies; where a line has room it says why
  (ended after three days stopped, retired by whom). A thread on a retired
  machine keeps today's `gone`, which the views and their tests pin, and
  is counted as ended by everything that asks: a tag naming it is refused
  saying its machine was retired, and it is not woken.
- *Ended is read from the log, by every machine the same way.* A session
  has ended when its membership in effect is a `retired` with reason
  `retire` or `ended`, whoever wrote it, or when its machine is retired in
  the org's state. An older copy's unstamped `retire` therefore counts on
  every reader, as it does on the thread's own machine (§6, "An older
  copy's writes").
  `has_ended` takes the reader's projected row and needs no record;
  `Member.end` holds which of the three it was. `--all` shows an ended
  thread from the log, on its own machine as on any other, and a spawned
  one as a retired seat shows today. No horizon is put on them (the
  composite: Deferred).
- *A message addressed to an ended thread* is refused when it is sent, as
  a tag naming a retired member is today.

**What it does not touch.** The wake. A VM's notice. The channel
memberships beyond keeping the field through an end and a return. The
three-day clock on a machine that is off (the composite's Delegated
unknown, observed after T1).

**What it proves.** Acceptance 4, 5 and 9. Its tests pin:

- with the period set short: a stamped `retired` `ended` from the sweep,
  the thread out of `list` and `--stopped` and in `--all`, a tag refused
  saying it ended; not ended a moment before the period; the clock starts
  again after a process held the session in between; a reading verb and a
  hook end nothing;
- a process that takes the session after the pass decided and before it
  writes: not ended; one the pass's cached records do not show but fresh
  ones do: not ended;
- what was held for the thread is settled `recorded` at its end and is
  not pushed when it returns; `daemon owed` no longer lists it;
- reopened by a new process: `joined` again under the same thread id,
  alias and in-charge line, the record back in the thread store with its
  `channels` as they were; a thread the rule ended with no process seen is
  returned by a process that had started a moment before the end;
- after a self-retire the same process's hooks do not join it again, and
  a new process does; a spawned session's self-retire leaves the record
  and the event written even when the stop ends the caller;
- the journal, for the rule's end, a retire, a `retire --purge`, a
  `remove` and a return, with the process killed after the record's
  write, after the event and after the settlement: each finished by the
  next reconciliation and by none after it, no event twice, a record
  neither set aside nor deleted while its entry is open, a purged record
  gone only once its retirement is in the log and what was held is
  settled, and the same membership read from a second registry that holds
  only the log;
- a spawned thread ended: its seat reads `retired` to this code and to the
  seat store's older readers; `fill` and `fill --resume` return it; `send`,
  `resume` and a tagged `say` do not;
- an older copy's unstamped `retire`: `has_ended` is true from the log
  alone, `--all` shows it, and a tag naming it is refused;
- a member of a retired machine: a tag naming it is refused saying so, its
  word in `list --all` is `gone`, and `has_ended` is true on a registry
  that holds no record of it.

### M5 — A thread that owns a VM is neither retired nor ended

devcloud 0.17.2 is on `main` at this plan's pin: for `vm owned-by` its
launcher answers exit 6 without an interpreter on confirmed evidence alone
(a devcloud host, a copy without the driver, a seed key confirmed absent),
and a driver that is present and fails to import, or a seed that cannot be
looked up, is exit 1. The command, its answer, its exits and its matching
rule are the composite's X9, with an example of each answer in DV's ledger
(`docs/doperpowers/ledgers/2026-11-17-DV.md`); this document repeats none of
it, and the milestone reads both as they stand when it runs.

**What exists at its end.** `sminos retire` of a thread that devcloud names
as a host's creator is refused, naming each host, and the three-day rule
leaves such a thread stopped. The same holds when devcloud gives no answer
it stands behind, and the refusal then names what could not be asked. Where
devcloud says its driver does not run, threads retire and end as M4 left
them. A person at a terminal can retire a thread whose answer is unknown,
with a flag that nothing else accepts. The daemon's tick never waits for
devcloud.

**What it touches.** `sminos_threads.py` (`owned_by`, the one function that
runs devcloud, and `owned_vms`); `sminos.py`: `cmd_retire`, `_retire_one`,
`cmd_remove`, the `retire` parser; `sminos_daemon.py`: `sweep_threads`'
ending pass, the census and its verb (`cmd_daemon`'s table), `service_env`;
`sminos_visibility.py`'s `confirmed`, made usable with another prompt; the
suite's shared setup (the stand-in).

**Interfaces.** Consumes X9. Exposes `owned_by`, `owned_vms` and the
census's file (Interfaces §7), which EN's handover and `channel show` also
read.

**Decisions.**

- *Where each guard runs.* The retire guard runs in the process running
  the verb, a session's Bash tool or a person's terminal, and waits for
  the answer there. The three-day guard is the daemon's, whose environment
  is the one its service file recorded at install (`service_env`): its
  `PATH` need not hold devcloud's `bin/`, and it has none of a session's
  variables.
- *The daemon asks off its tick.* The question takes seconds and a
  network, and the tick is what delivers messages and keeps the machine's
  connection. The ending pass starts the census as a child process it does
  not wait for, as `derive_duty` starts `derive --all`: one in flight on
  the machine, under a lock of its own, with its run's state (its pid,
  when it started) in a file of its own and its answer written whole to
  another (Interfaces §7): neither is a file another duty rewrites under
  another lock. A later pass takes the answer up, for each thread whose `stopped`
  and current session are the ones it was asked about, and no older than
  one spacing of the ending pass; any other thread is asked about again. A
  thread ends two passes after it falls due at the soonest. *Alternative: a
  thread of the daemon's process.* It lost because a hung call there holds
  the interpreter's own shutdown and shares the tick's caches, and the
  daemon already has the child's whole pattern, reaping included.
- *What a hung question costs, and how it is stopped.* `owned_by` bounds
  its one call (Interfaces §8), in the verb and in the census alike. Past
  the bound it sends the driver SIGTERM, which the driver handles by
  taking its provider's process group down with it; after a short grace
  it kills the driver and every process then descended from it, read from
  the process table before the kill, since the driver starts a provider
  in a session of its own that a kill of the caller's group does not
  reach. The answer is then unknown. A census still running after twice
  the bound is stopped the same way by the pass that finds it, and
  `daemon.log` says so once. Meanwhile nothing on the machine ends by the
  rule, and nothing else waits. A census the daemon holds no handle on
  (the daemon restarted in place) is reaped as `derive_running` reaps its
  own.
- *How the CLI is found,* in this order, the first that exists being the
  one asked:

  | Where | Why there |
  |---|---|
  | the path in `SMINOS_DEVCLOUD` | the suite's stand-in; an operator's override |
  | `devcloud/bin/devcloud` beside the running sminos plugin's root | the copy in the same clone or checkout: where the daemon runs from (`installed_cli`), and never older than this sminos |
  | the same file in the doperpowers marketplace clone, found as `installed_cli` finds the clone | what a CLI running from the plugin cache has, where the cache holds sminos alone |
  | `devcloud` on `PATH` | last, because a long-lived session's `PATH`, or a service's recorded one, can name the cache directory of a devcloud from before 0.17.2 |

  The driver needs a Python 3.11 on `PATH`, sminos runs on 3.10, and the
  driver finds a provider's own tool (`hcloud`, `gcloud`) on the `PATH` it
  is given: the call puts the directory of sminos's own interpreter first
  on the child's `PATH` and changes nothing else of it.
- *What each way of getting no answer means.* Only devcloud's own word
  that the driver does not run here is read as none:

  | What came back | Read as | Why |
  |---|---|---|
  | exit 0, `answer` `owned` | owned | the hosts in `vms`; whatever is in `unknown` is named too |
  | exit 0, `answer` `none` | none | every configured account was listed in full |
  | exit 0, `answer` `unknown` | unknown | `unknown` says what could not be asked |
  | exit 6, from a devcloud of 0.17.2 or later | none | devcloud says the driver does not run on this machine (a devcloud host, a copy without the driver, or no seed key) |
  | the copy found is older than 0.17.2 (the version in the plugin manifest beside it), whatever it answered | unknown | before 0.17.2 a broken driver answers 6 and a machine with no interpreter for it answers 1; the refusal names the version and the copy |
  | no copy of the CLI found | unknown | nothing on this machine said the driver does not run: the CLI ships beside sminos, so its absence is a broken install; the refusal says where it looked |
  | any other exit, a timeout, exit 0 with output that is not the JSON object, a launcher that cannot be run | unknown | the refusal gives the exit code and the first line of what it printed (a seed key with no Python 3.11 for the driver is one of these) |

  A copy named by `SMINOS_DEVCLOUD` has no manifest to read and is taken
  at its word. A provider tool missing from the daemon's `PATH` comes back
  from devcloud as `unknown` with its reason, so it holds the thread and
  is named.
- *Exit 6 is only as good as the environment it was asked in.* devcloud
  finds its seed and its profile under `HOME` unless `DEVCLOUD_SEED_FILE`
  or `DEVCLOUD_PROFILE` is set. `service_env` records those two for the
  daemon when the installing environment sets them, as it records the
  gateway's keys. Two wrong nones are left, both in the composite's D4 as
  accepted: a Mac that lost its seed key, and a Mac whose sessions set one
  of the two variables after its service file was written. In either the
  VM's notices still go on to the project's live members, and the ended
  thread returns when reopened.
- *The names asked about* are the short ids of every session id the
  thread has had (`sessions`, which adoption rebuilt for a thread from
  before this code, M1), bare: X9 matches a short id whole, and nothing
  through an alias. A thread with no session (a vacant seat) is not asked
  about, since devcloud refuses a question with no name: its answer is
  none.
- *One question per census, and none when no thread is due.* The census
  asks once for every thread that is due and reads each thread's answer
  from the one reply (Interfaces §7). A thread that is owned or unknown is
  asked about again by the next census, and `daemon.log` gets a line when
  its answer changes, not at every pass.
- *An answer does not end a thread by itself.* The end is written under
  M4's check: the stop the answer was asked for, the same current session,
  and no process by fresh evidence.
- *Every path that ends a thread on purpose asks:* `retire`,
  `retire --purge`, `remove`, by another session or by itself. A refill
  and a continuation do not: the thread goes on.
- *What a refusal names.* For owned: each host by name with its provider
  and account, an adopted machine as an adopted machine (X9: account
  `adopted`, no provider, `adopted` true), and for a VM
  `devcloud vm down <name>` as the way on (EN adds the handover). For
  unknown: each entry of devcloud's `unknown`, or the row of the table
  above that applied. A refusal never gives exit 6's meaning as a reason:
  exit 6 refuses nothing.
- *The residue the composite left: a terminal may pass an unknown.*
  `sminos retire <member> --owner-unknown` retires a thread whose answer
  is unknown, and only that: an owned answer is refused with the flag too.
  It is accepted from a person at a terminal alone, as widening reach is:
  refused inside a session (`CLAUDE_CODE_SESSION_ID` is set), and
  confirmed by a typed yes on the controlling terminal (`confirmed`'s
  check, with a prompt that names the thread and what could not be asked),
  refused where there is none. Reason, the composite's: a provider account
  that stopped working would otherwise hold every thread of that Mac
  forever. The three-day rule has no such pass: the thread stays stopped
  until a person retires it.

**What it does not touch.** devcloud. `devcloud vm owner` and the notice
(EN). A copy in sminos of what a thread owns: there is none (D4); the
census's file is an answer to one question about threads that are due, and
nothing reads it as what a thread owns.

**What it proves.** Acceptance 6. Its tests, against the stand-in unless
they say otherwise, pin:

- owned: `retire` refused naming the host, an adopted machine named as
  one, the thread still a member; the ending pass leaves it stopped and
  says so once;
- each row of the second table that reads unknown: refused naming it, and
  the pass leaves the thread stopped;
- none and exit 6: the retire and the end go through;
- the lookup's order, against a made-up plugin layout whose root the test
  controls (changing `HOME` and `PATH` does not hide the worktree's own
  devcloud beside sminos): each place found when the ones before it are
  absent, and a manifest older than 0.17.2 read as unknown, named;
- the real launcher, once, under a `HOME` that holds no seed key: exit 6,
  read as none;
- the names passed are the short ids of every session the thread has had;
  a seat adopted after it was refilled, whose host names only its first
  occupant, is refused; a vacant seat is retired with no question asked;
- `--owner-unknown`: refused from a session, refused with no terminal,
  retires on unknown at a terminal after a typed yes, refused on owned;
- the pass that finds threads due returns before the stand-in answers,
  and delivery goes on in the ticks between; the answer is taken up by a
  later pass; one call for all due threads, each thread's answer its own,
  and no child when none is due;
- a stand-in driver that never answers and has started a child of its
  own in a new session: past the bound both are gone, the answer is
  unknown, there is one line in `daemon.log`, the thread is still stopped,
  and no second census runs beside the first;
- a thread that reopened during the question, and one that reopened and
  stopped again, are not ended by the answer.

### M6 — What sessions are told, an older sminos beside this one, the shared vectors, and the acceptance run

**What exists at its end.** The skill, the spawn preamble, the guide and
`sminos help` say what is now true, in today's words, with an evaluation
that shows the change in behavior. A script shows that sminos 1.27.10, the
oldest still in a plugin cache on the owner's machines, run against a store
this code wrote, resumes no human-opened session and that the `ended` it
writes changes nothing for this code. The vectors shared with MAWS are
still what MAWS's master holds. The acceptance has been
run as Concrete Steps gives it, the version is bumped, and the branch is
ready for its review.

**What it touches.** `sminos/skills/sminos/SKILL.md`,
`sminos/skills/sminos/references/spawn-preamble.md`, `guide_text`'s fork
line and the lines M3 to M5 made their verbs print; `sminos/CLAUDE.md`,
`sminos/skills/sminos/scripts/CLAUDE.md` and `sminos/hooks/CLAUDE.md`
wherever a milestone left a sentence behind; `docs/whats-inside.md` only if
a row's sentence became false; a new `sminos/tests/test-older-cli.sh`;
the version
files `scripts/bump-version.sh --plugin sminos` writes.

**Interfaces.** Consumes everything above. Exposes nothing.

**Decisions.**

- *Which text, and only that* (X6). In `SKILL.md`: the state list's
  `stopped` (a seat is resumed by a message; a session its human opened
  waits for them); the delivery table's `@alias` row; "A closed
  interactive session cannot be tagged", which is now false; the paragraph
  on `send` to a session that is not live; that a session closing for good
  says so with `sminos retire` on itself; that a session stopped for more
  than three days ends, and what returns it; that `retire` is refused for
  a session that made a VM, and that the refusal is reported, not worked
  around. In the preamble: "@alias delivers to that member, starting its
  turn or resuming it". The words seat, member and session stay.
- *The evaluation* runs through doperpowers:writing-skills, with a
  baseline on the text as it is and a run on the edit, on four behaviors:
  a session asked to tell something to a peer that `list --stopped` shows
  stopped and human-opened tags it once and reports that it waits for the
  peer's human, without retrying and without reaching for `resume` or
  `fill`; a session told its work is finished for good retires itself; a
  fork asked who it is answers with its own short id and leaves a message
  addressed to its original alone; a session whose `retire` is refused
  naming a VM reports it and does not force it. A line the baseline
  already produces is cut.
- *The older CLI is 1.27.10,* the revision `aefb80aa` of this repository
  set that version. `test-older-cli.sh` takes the path of an older `sminos`
  launcher, so it runs against a cached copy on a machine; in the suite it
  runs against that revision extracted from this repository's history
  (`git archive`). The gates check out one commit (ci-kit's default depth),
  so the script fetches that one revision from `origin` by its id when the
  clone lacks it, and fails when it cannot have it: it never passes on a
  line saying it was skipped. If a gate's runner cannot fetch it, the
  script leaves `run_suites`, is run on a full clone, and acceptance 10 is
  reported as an open item with what was run, never as green. It drives
  this code and the older one against one registry with the suite's stub
  engine: this code makes a human-opened thread, stops it and holds a
  message for it; the older CLI then runs every verb that reads the store
  (`list`, `say` with its tag, `send`, `resume`, `fill`, `daemon tick`);
  the stub's log holds no `--resume` of that session; then this code's
  `list --stopped` still shows it. What that revision does is asserted as
  it is, so a change is seen: its first reading verb reconciles the
  session, which has no process and no seat, to an unstamped `ended`; it
  resumes nothing; and it reports what is owed as `recorded` and settles
  nothing, since a closed session is no member to its delivery. The
  settlement by a stale deliverer that D7 accepts needs a member snapshot
  taken before the session exits, which this fixture does not make, and is
  left out.
- *The vectors' pin is checked, not moved.* The copy M1 pinned is compared
  with `apps/org-protocol/vectors/channel-rule.json` on MAWS's master as
  it is when the milestone runs. A difference is a change of contract:
  the copy is synced again by `sync.sh`, the `retired` cases are made to
  pass on it, and the composite's holder is told.
- *The live pass.* Two acceptance items rest on what the real engine does
  at a session's start and end (1, and 3's `/clear`, fork and in-session
  `/resume`), which the stub only models. They are run once on a real
  engine against a scratch store, every session of the pass loading the
  sminos plugin from the worktree in place of the installed copy (Concrete
  Steps). If the two copies cannot be kept apart on the machine the
  milestone runs on, that pass is run on the released version as the first
  step of the parent's acceptance, and is an open item reported with the
  branch (the holder accepted this).

**What it does not touch.** The words thread and channel in anything a
session reads, and the manager's skill (CH). MAWS.

**What it proves.** Acceptance 10 and 11, and every item of T1's
acceptance once more, as observed in the run.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-threads-t1`), unless it says otherwise.

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_threads.py
    bash sminos/tests/test-guide.sh
    bash sminos/tests/test-who.sh
    python3 -B sminos/tests/test_owed.py
    bash sminos/tests/test-older-cli.sh <path to an older sminos launcher>

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. A shell file ends with its counts of passed and
failed and exits non-zero on any failure. A case of `test_threads.py` is
named by the behavior it pins, in the words of the milestone's "What it
proves".

**At each milestone's end, and before the branch's review,** the gates, on
the pushed commit (`.github/ci-kit.yml`; they run on GitHub Actions and
test the committed HEAD, so commit and push first):

    ci-gate --gates sminos,sminos-suites,sminos-idle,sminos-mods,issue-tracker,board-api,shell-lint,repo-checks

and from M6 on, `version-bump` too. Expected: one `PASS` line per gate, then
`GREEN` and the run's address. `sminos` is the core suite, `sminos-suites`
the files `run_suites` lists (`test_threads.py` and `test-older-cli.sh`
among them once registered), `sminos-idle` the daemon's idle cost, and
`issue-tracker` and `board-api` the board scripts that call the sminos CLI
and write seat records. A `FAIL` line gives the path of the gate's log.

**M1: the vectors.** With a checkout of MAWS that holds the commit:

    sminos/tests/vectors/maws/sync.sh <MAWS checkout> 8a7f308ffc7b7ef6f2179d9e97fd4935a80d2707 channel-rule.json
    python3 -B sminos/tests/test_threads.py

The first prints the file's name, the commit and the copy's sha256
(`7cd64b2d…748f52`, whole in M1), and writes the copy and
`channel-rule.PIN.json`; the second passes the five `retired` cases on that
copy. **M6** compares the copy with master's file:

    git -C <MAWS checkout> fetch origin
    git -C <MAWS checkout> show origin/master:apps/org-protocol/vectors/channel-rule.json | shasum -a 256

The hash is the pin's.

**M6: the version.**

    scripts/bump-version.sh --plugin sminos <the next minor version>
    scripts/bump-version.sh --since origin/main

The second lists the plugins whose shipped files changed since `origin/main`
and exits 0 once sminos's version is above the base's.

**M6: the acceptance run.** T1's acceptance in the composite, item by item.
Each item is shown by the suite's cases named for it, run through the gates
above; the table says which, and what a person sees. Items 1 and 3 are also
run live, below.

| Item | Shown by | What is seen |
|---|---|---|
| 1 | M3's cases "its process gone" and "reopened"; the live pass | `sminos list --stopped` holds the closed session's row with the word `stopped`; after `claude --resume` and a `sminos daemon tick`, `sminos list` holds it live under the same alias and in-charge line, and the held message is in its context |
| 2 | M3's hold and verb cases | the sender's line says recorded, stopped, not woken, opened by its human; the stub's log holds no `claude --bg --resume` for it; `fill` of it exits non-zero and says its sessions are its human's to open; a spawned one's line says `woken` as today |
| 3 | M2's hand-off, refill, `clear`, fork and `/resume` cases; M3's `/clear` cases; the live pass | `sminos list --stopped --json` gives the session a `/clear` left and the new one two `thread` values, the alias on the new one, and `sminos say "@<alias>#<old short> …"` is held for the old one; a hand-off and a refill give one `thread` |
| 4 | M4's three-day cases, with `SMINOS_THREAD_END_AFTER` set short | after two `sminos daemon tick`s past the period (the first asks devcloud, the second reads the answer): gone from `list` and `--stopped`, in `--all` as `retired`; `sminos say "@<alias> …"` exits 4 saying it ended |
| 5 | M4's self-retire cases | the session's own `sminos retire <itself>` prints the retirement; its row stays out of `list` after its process exits and through later hooks of that process |
| 6 | M5's cases against the stand-in | `sminos retire` exits non-zero naming the host; with the stand-in answering unknown, naming the account that could not be asked; with it exiting 6, the retire goes through |
| 7 | M1's stamp cases, M2's naming cases | every `joined`, `retired` and `state` of a thread in the log carries `thread`, and no human-opened thread's is a session id; `sminos say "@<former short> …"` is delivered to the current session, from a second registry that only holds the log |
| 8 | M3's question cases, M1's lane case | the project's host events hold an `answered` with `closed` for the open question; the endpoint stand-in receives `gone` before the frame of the other lane |
| 9 | M4's retired-machine case | on another registry, `list --all` shows the member `gone` and a tag naming it is refused saying its machine was retired |
| 10 | `test-older-cli.sh` against 1.27.10; the vectors' `retired` cases | no `--resume` of the human-opened session in the stub's log after every older verb; `list --stopped` of this code still shows it |
| 11 | the `sminos` and `sminos-suites` gates | `GREEN` |

**M6: the live pass,** on a real engine, against a scratch store:

1. A scratch git repository in a scratch directory, a scratch
   `SMINOS_HOME` exported, and a terminal multiplexer's own server. The
   scratch store is enrolled by hand, as the Python suites enroll one
   (`write_identity` in `sminos/tests/rl10_identity.py`: an identity whose
   hub address nothing listens on), since the guide prints nothing on a
   machine that is not enrolled. No daemon runs against it; delivery is
   `sminos daemon tick`, run by hand where a step says so.
2. Every session of the pass, at its first launch and at every relaunch
   and resume, is started so that the sminos it loads is the worktree's
   and not the installed copy (`claude --plugin-dir <worktree>/sminos`,
   with the installed sminos plugin disabled for that launch); inside it,
   `command -v sminos` names the worktree. If it names the installed copy,
   stop: the pass cannot be run here (M6's decision says what then).
3. Session S: give it a name and one prompt, have it run
   `sminos charge "<a line>"`, then `/exit`. From the scratch repository,
   with the worktree's CLI: `sminos list --stopped` shows S `stopped` under
   its name and that line. A second session P of the same repository runs
   `sminos say "@<name> hello"` (a peer's message: on an enrolled machine a
   person's words from a terminal wait for an endpoint this store has
   none of); its line says S is stopped and not woken, and
   `claude agents --json` shows no process for S.
4. `claude --resume <S's id>`, then `sminos daemon tick`. `sminos list`
   shows S live under the same name and line; its transcript holds the
   message's frame.
5. In S, type `/clear`. `sminos list --stopped --json` shows two members
   beside P: the new id live under the name, the old id `stopped` under its
   short id with the in-charge line, with different `thread` values, and
   the old one's events hold no `retired`. From P,
   `sminos say "@<name>#<old short> again"` is held for the old one.
   Resume the old id in a second pane: it is live under its short id.
6. Fork a session (the engine's own command for a copy). The copy's guide
   line carries the fork sentence, and `list --json` gives it a `thread`
   of its own.
7. In a session, `/resume` into another session of the directory. Both are
   members with their own `thread`, and no `retired` with reason
   `continued` was written for either.
8. What was seen, with the engine's version, goes to Surprises &
   Discoveries; the scratch store and directories are removed.

## Interfaces and Dependencies

T2, CH and EN are built against the names in this section. `S/` is
`sminos/skills/sminos/scripts/`.

### §1. The thread record (X1)

One module, `S/sminos_threads.py`, loaded as the CLI's other sibling
modules are (`sibling_module("sminos_threads")`). Every read and write of a
thread's record goes through it. The seat's own fields keep their writers
(`meta_set`, `meta_set_if`, the board pipeline), under the lock they take
today.

**On disk,** under `$SMINOS_HOME`:

| Path | Holds | Lock |
|---|---|---|
| `<seat id>.json` | a spawned thread: its seat record, with the stored keys below added | `.metalock` |
| `threads/<thread id>.json` | a human-opened thread that has not ended, or whose end still has an open entry | `threads/.lock` |
| `threads/ended/<thread id>.json` | a human-opened thread whose end is finished; the end's last step moves it here and a return brings it back | `threads/.lock` |

Each file is one JSON object, mode 0600, written by atomic replace.

**The record,** as the module returns it for either kind:

| Field | Type | Meaning |
|---|---|---|
| `thread` | string | the thread id: a spawned thread's seat id; a human-opened thread's own UUID, minted when the record is made and never a session's id |
| `opened` | `"spawned"` or `"human"` | fixed when the record is made |
| `sessions` | list of strings | every session id the thread has had, oldest first; its last is `current` whenever there is one. Rebuilt at adoption for a thread from before this code (M1) |
| `current` | string | the session that fills it now; `""` for a vacant spawned thread |
| `alias` | string | a spawned thread's seat alias; for a human-opened one, the alias its latest `joined` or `renamed` carried: a copy for readers without the log, whose own events decide the alias |
| `launch` | `{"cwd": string, "options": list of strings, "at": timestamp}` | the directory and the options of the engine process that last started `current`; `options` is option tokens in order, kept for `LAUNCH_OPTIONS` alone, and is absent when they could not be read |
| `channels` | list of strings | declared channel ids. T1 makes it `[]` and carries it through an end and a return; CH writes it |
| `stopped` | timestamp, or absent | since when the thread sweep has found no process holding `current` |
| `swept` | timestamp, or absent | the `stopped` for which the sweep has closed the thread's open questions |
| `ended` | `{"at": timestamp, "reason": "retire" or "ended", "by": string, "pid": integer or null}`, or absent | the end: who retired it (`by`, `""` for the rule) and the process seen then |
| `released` | `{"alias": string, "at": timestamp}`, or absent | the name the thread gave up at a `/clear` (M3): alias selection refuses it to the thread until a process started after `at` holds its session |
| `pending` | object, or absent | the journal: the one open entry of a transition that is not finished (§6) |
| `created`, `updated` | timestamps | |

A human-opened file holds exactly these, and `"v": 1`. A seat record gains
the stored keys `opened`, `sessions`, `launch`, `channels`, `stopped`,
`swept`, `ended`, `released` and `pending`; `thread`, `current` and `alias` are read from what it
already holds, and its `status` is `retired` whenever `ended` is set. A seat
record without the keys reads as `opened: "spawned"`, `sessions: [current]`
until adoption rebuilds it, `launch: {"cwd": <its cwd>}`, `channels: []`.
One whose `status` is `retired` and that holds no `ended` (a seat retired
before this code, or by an older copy) reads as ended at its `updated`.
Timestamps are `sminos.now()`'s.

**The functions:**

    OPENED = ("spawned", "human")
    LAUNCH_OPTIONS = (...)     # the option names launch.options keeps; T2 extends it

    def all_threads(ended=False) -> list[dict]
        # this machine's threads of both stores; those set aside only on request
    def get(thread_id) -> dict | None
    def thread_of(session) -> dict | None
        # in this order: the thread whose open entry makes the session its current one; the
        # thread whose current session it is, a human-opened one before a seat; one that had
        # it, those set aside included
    def stamp(session) -> str
        # the thread id an event of this session carries; "" for a session that is no thread
    def ensure(session, seat=None, project=None, events=None, lock_until=None) -> dict | None
        # the record of the thread the session fills, made when there is none (project and
        # events: the log an adopted thread's sessions are rebuilt from); None for lane B and
        # for a spawn's child that no seat holds yet
    def update(thread_id, fields, remove=(), guard=None, lock_until=None) -> bool
        # a change that owes no event (the stop mark, `swept`, a launch noted, CH's channels):
        # a merge under the store's lock, applied only if guard(record) holds; it never
        # writes the keys a journaled operation owns (`current`, `sessions`, `ended`,
        # `released`, `pending`)
    def begin(thread_id, op, project, events, fields=None, remove=(), guard=None,
              lock_until=None, **more) -> dict | None
        # the one way a journaled operation starts (§6): under the store's lock, when the
        # record has no open entry and guard(record) holds, the record's change and the
        # entry in one write; the entry as written, None when nothing was
    def finish(thread_id) -> bool
        # carries out the record's open entry from where it stands and clears it (§6); True
        # when the record has none left. Any process may call it, any number of times
    def note_launch(thread_id, cwd, options=None) -> bool
    def record_ended(record) -> bool        # this machine's record says ended
    def hold_of(session) -> str             # §5
    def set_channels(thread_id, channels) -> bool          # CH's writer

`lock_until` is the hook's deadline: past it the write raises `LockBusy`
and nothing is written, as `meta_set` does. A child adds a field through
`update`, or an operation through `begin`, and names it here.

### §2. Events T1 adds to or changes

No kind is new. Every event below is written by the thread's machine,
under the session's own writer, in its project's log. An event a
journaled operation owes also carries `"op": <its entry's id>` (§6).

| Event | Shape | When |
|---|---|---|
| the stamp | `"thread": <thread id>` on every event `lifecycle` appends for a session that is a thread, whatever its kind (`joined`, `retired`, `renamed`, `state`, `titled`, `in-charge`, `status`) | from the session's first `joined` by this code |
| continuation | `retired`, `"reason": "continued"`, `"to": <new session>`, `"pid"` when a process was seen, stamped: today's event | the engine's hand-off (`hand_off`) |
| refill | `retired`, `"reason": "replaced"`, `"by"`, stamped; no `to` | `spawn_fresh` onto a seat, `seat add` over a held one |
| end by a retire | `retired`, `"reason": "retire"`, `"by": <who>`, `"pid"` when a process was seen, stamped | `retire`, `retire --purge`, `remove` |
| end by the rule | `retired`, `"reason": "ended"`, `"by": ""`, stamped | the sweep, after three days stopped; and a lane B session's process ending, when it has a thread record |
| return | `joined`, stamped with the thread id it had | a reopened or filled ended thread |
| whether it is woken | a `state` whose `"state"` is `"stopped"` carries `"wake": "woken"` or `"wake": "held"`, built in `lifecycle` for every writer of a session's state | whenever such a `state` is written, and again by `publish_state` when the value changes |
| a question closed | `answered`, `"src": <the question's>`, `"from": <the asker's alias>`, `"text": "closed: the session stopped before this was answered"`, `"closed": "stopped"` | the sweep, while the thread is stopped |
| the alias released at a `/clear` | `renamed`, `"alias": <the session's short id>`, `"name_source": "derived"`, stamped | the record hook of the session that took its place, on `cleared_from`'s witness |

A `moved` retirement and the `joined` that follows it in the other log are
today's, stamped. The reasons a reader meets on a `retired` are `ended`,
`moved`, `continued`, `retire` and `replaced`.

### §3. The reducer and the reader rule (X7)

    def stamped(event) -> bool
        # its `thread` is a non-empty string
    def passed_by(event, latest_joined) -> bool
        # event is a `retired` with reason `ended` that is not stamped, and latest_joined,
        # the latest `joined` of the same session before it in its own writer's order, is stamped
    def in_effect(events) -> dict | None
        # the one reducer: among one session's own events, in its writer's order, the latest
        # `joined` or `retired` that is not passed by; None for a session with none

An event that is passed by is absent to every reader: the membership in
effect is what the events before and after it say. Every other `retired`
takes effect, whoever wrote it. A reader asks `in_effect` and reads from
its answer what it needs: the `kind`, the `reason`, a `moved`'s `project`,
a `continued`'s `to`. No reader of membership reads a session's raw last
event. The rule's cases are the `retired` list of
`sminos/tests/vectors/maws/channel-rule.json`, MAWS's file, at its version
1:

| Case | One session's own events, in order | A member after each |
|---|---|---|
| 1 | stamped `joined`; unstamped `retired` `ended` | yes; yes |
| 2 | case 1, then unstamped `retired` `moved` | yes; yes; no |
| 3 | case 1, then stamped `retired` `ended` | yes; yes; no |
| 4 | unstamped `joined`; unstamped `retired` `ended` | yes; no |
| 5 | stamped `joined`; unstamped `retired` `moved`; unstamped `retired` `ended` | yes; no; no |

The fifth catches a reader that keeps one latest `retired` per session and
lets the one it passes by displace the one it honours.

### §4. Naming a thread, and what a thread's row reads (X2)

On any machine, from the log as that machine may read it.

- **Which thread a session is in.** The thread its latest `joined` is
  stamped with. For naming alone, an unstamped `joined` that carries a
  seat's id in `seat` counts as stamped with it, and an unstamped session
  with no seat is in no thread and resolves through its `continued` chain,
  as today.
- **A thread's sessions** are the sessions in it by that rule. Its
  **current session** is the one among them whose membership is in effect;
  when none is (it has ended), or more than one is (a refill whose
  retirement is not yet written), the one whose `joined` is latest.
- **A name.** The thread id, or the id of any session of the thread, or of
  any session a session of it continues, in the forms a session id takes
  today (`@short`, `@alias#short`, a full id), resolves to the thread's
  current session. Where a name is one member's current session or alias
  and another's former one, the first is the match, as a former alias is
  ordered today. An event that addresses a message names the current
  session's id.
- **Episodes.** A session's events are read in episodes, each beginning at
  a `joined` whose stamp differs from the one before it. A thread's row
  (alias, in-charge line, status, `by`, worktree) is read from the
  episodes stamped with its id, of its current session and of its other
  sessions. An event with no stamp of its own belongs to the episode of
  its session that its time falls in. Owners are read along the
  continuation chain and nowhere else.

### §5. Whether a thread is held or woken (X3, the first values)

    def hold_of(session) -> str          # S/sminos_threads.py, on the thread's own machine
        # "" when this machine delivers to the session or wakes it; "human" when it holds:
        # a human-opened thread that has not ended, whose current session no process
        # holds. T2 adds its reasons.
    def wake_of(member) -> str | None    # S/sminos.py, on any machine
        # "woken" | "held" | "ended", or None when its machine published nothing

| Value | Thread | Read from |
|---|---|---|
| `woken` | spawned and stopped: an addressed message resumes it, as today | on its own machine, `hold_of`; elsewhere, `wake` on its latest `state` |
| `held` | human-opened and stopped: recorded and held until its human reopens it. T1 writes this value and T2 retires it for the reasons of its own list | the same |
| `ended` | ended by a retire or by the rule, or on a retired machine | `has_ended` (§8) |

A sender's CLI reads it when it sends and says it with the machine the
message waits on. With `None` (an older sminos on that machine) it says
what it says today.

### §6. Transitions and the journal

A thread is `live` (a process holds `current`), `stopped` (none does),
`ended` (its record says so) or, spawned only, `vacant`. The record's
write, under its store's lock, is each transition's linearization point.

| # | What happens | Guard | The record's write | The events owed, then what follows |
|---|---|---|---|---|
| 1 | a lane A session with no thread is seen for the first time (its hook, a reconciliation) | joinable as today, and no spawn's child (M1) | `ensure`: a human-opened record under a minted id | `joined`, stamped |
| 2 | `spawn` makes a seat; `seat add` | as today | the seat record, with the thread keys | `joined`, stamped |
| 3 | a member or seat from before threads, or a member an older copy joined | this machine's, lane A, its membership in effect an unstamped `joined` | `ensure`, its `sessions` rebuilt | `joined` again, stamped |
| 4 | the engine hands a session to a background job | `continued_in`'s evidence, as today | **advance**: `current` old to new, new added to `sessions` | `hand_off`'s own steps (the reach by `ensure_record(new, former=[old])`, the cursor, the override), then `retired` `continued` on the old and `joined` or `renamed` on the new, one stamp |
| 5 | the same, when the job already has a record of its own; a launcher that learns its session after the bound | that record is human-opened, not ended, holds the one session and has no open entry (read before row 4's reach is carried) | **absorb**: as an advance, the entry naming that record | as row 4, the new session's `joined` under the stamp of the thread that goes on; then that record is deleted |
| 6 | a refill | the seat's lock, as today; refused when a human-opened record names the seat's session | **advance**; an ended seat's `ended` lifted in the same write | `retired` `replaced` on the old, `joined` on the new, one stamp |
| 7 | no process holds `current` | two consecutive sweep passes, no resume lock held | `update`: `stopped` set | none; `state` `stopped` with `wake`, as `publish_state` finds it |
| 8 | a process holds `current` again | — | `update`: `stopped` and `swept` removed, and `released` when the process started after it | none; what was held is delivered at the next pass |
| 9 | `retire`, by another or by itself | M5's answer is none, or unknown with the terminal's flag | **end**: `ended` with reason `retire` and the process seen | `retired` `retire`, stamped; what is held is settled; the record set aside. The verb then stops the process where sminos can |
| 10 | stopped for more than the period | the sweep's ending pass, under the lock: `stopped` is the time decided for, `current` the same, no process by fresh evidence, M5's answer for that stop is none | **end**: `ended` with reason `ended` | `retired` `ended`, stamped; what is held is settled; the record set aside |
| 11 | `retire --purge`, `remove` | as row 9 | **end**, its entry marked to purge | `retired` `retire`, stamped; what is held is settled; the record, and a seat's files, deleted |
| 12 | an ended thread's session is held by a process the end did not see (M4) | the record's `ended`, its time and pid | **return**: `ended`, `stopped` and `swept` removed, a record set aside brought back | `joined`, stamped |
| 13 | a thread's session becomes lane B | `lane_of` | none; when its process ends, **end** with reason `ended` | `gone` to the endpoint before the new frame; at its process's end `retired` `ended`, stamped. Reopened as lane A it returns by row 12 |
| 14 | a `join`, or a directory that resolves elsewhere | as today | none | `retired` `moved` and `joined`, today's, stamped |
| 15 | a former session of a thread runs again | a process holds it that is not the one its retirement saw, or that started after it | `ensure`: a human-opened record of its own | `joined`, stamped with the new id |
| 16 | a `/clear` (M3) | `cleared_from` names a human-opened member of this machine whose alias is the engine's name for the process | **release**, on the thread of the session left: `released` set | `renamed` to its short id on the session left. The new session is row 1 |

A `/clear`, a fork and an in-session `/resume` are rows 1 and 7: the new
id is seen for the first time, and the session left has no process.

**The journal.** The five operations in bold write a record and owe
events. Each is started by `begin` and carried out by `finish`, and by
nothing else. The entry:

    "pending": {"id": <minted>, "op": "advance" | "absorb" | "end" | "return" | "release",
                "at": <timestamp>, "project": <the project whose log the events go to>,
                "events": [<each event owed, whole and in order: its kind, its session, its fields>],
                "settle": <session>,        # end: what is held for it is settled `recorded`
                "last": "aside" | "purge",  # end: what becomes of the record (absent for a seat that stays)
                "other": <thread id>}       # absorb: the record deleted last

1. *Begin.* One write, under the store's lock: the record's change and
   the entry. It is refused while the record has an open entry; the caller
   finishes that one and begins again.
2. *The events.* Each is appended through `lifecycle` with the entry's id
   in `op`, under its writer file's lock, with the guard that the
   session's own events hold none of that kind with that `op`. An event
   the log already holds is thereby skipped, whichever process appended
   it. Whatever `lifecycle` reads again under the lock (a `joined`'s
   publication of its owners) is read then; the rest is the entry's. For
   an advance out of `hand_off`, that function's steps that come before
   its events (the reach, the cursor, the override) are run first, each of
   which is safe to repeat.
3. *What follows the events:* for an end, what is held for `settle` is
   settled.
4. *The last step,* one write: `pending` is removed, and in that same
   write an end's record is moved aside or deleted as `last` says, after
   its settlement has succeeded; for an absorption the other record is
   deleted first.
5. *Replay.* A reconciliation that finds a record of this machine with an
   open entry for its project calls `finish`, which runs steps 2 to 4 from
   the entry, and does nothing else to that record in that pass. Any
   transition does the same before its own `begin`.
6. *While an entry is open,* nothing else sets the record aside, deletes
   it, or reads it as finished: the rules below pass it by, and
   `thread_of` answers the entry's thread for the session it makes
   current.

Rows 1 to 3, 7, 8, 14 and 15 are not journaled: each is finished by a rule
that exists already (a record whose session has no `joined` in effect is
joined on sight, as a seat with no membership event is today), or owes no
event. The sweep's closing of questions is finished by `swept` (M3).

**An older copy's writes.** Three rules, applied by a reconciliation to a
record of this machine that has no open entry, for the record's current
session in its project (D7). Nothing else an older copy leaves is
repaired.

| An older copy wrote | The record says | What is done |
|---|---|---|
| an unstamped `retired` `retire`, in effect | not ended | an **end** that owes no event, with the event's `by`, `pid` and time: the settlement and the last step as for any end |
| an unstamped `retired` `ended` after a stamped `joined` | not ended | nothing: it is passed by |
| an unstamped `joined` and then an unstamped `retired` `ended`, in effect | not ended | until M3, with no process holding the session: an **end** with reason `ended` that owes no event. From M3: `joined` again, stamped, as adoption writes one |

A thread ended by the first rule returns by row 12 like any other, and a
return cut short is finished from its own entry: no rule reads an open
entry's record.

### §7. Which hosts a thread owns (X9, as consumed)

    class Owned(NamedTuple):
        answer: str        # "owned" | "none" | "unknown"
        vms: list          # devcloud's `vms` entries
        unknown: list      # devcloud's `unknown` entries, or one entry sminos makes for no answer
        asked: list        # the short ids asked about

    def owned_by(shorts) -> Owned          # the one function that runs devcloud; no shorts: none, unasked
    def owned_vms(thread) -> Owned         # owned_by for the short ids of thread["sessions"]

`owned_by` runs `devcloud vm owned-by <short>...` as M5 finds and reads
it. The command's exact form and answer are X9's in the composite, read
again when M5 runs; nothing else in sminos runs devcloud or reads its
output. One reply answers for many threads: a thread owns the hosts of
`vms` whose `creator` is `@` and one of its short ids; a thread that owns
none is unknown when `unknown` is not empty, and none otherwise. An entry
sminos makes for no answer has devcloud's keys, with `account` and
`provider` null, `failed` `"query"` and the reason in `reason`.

The census is `sminos daemon census`, a verb the daemon runs as a child
and no person runs. It asks `owned_by` once for the threads due and writes
`$SMINOS_HOME/daemon/census.json` whole:

    {"at": <timestamp>,
     "threads": [{"thread": <id>, "current": <session>, "stopped": <timestamp>, "shorts": [...]}],
     "answer": "owned" | "none" | "unknown", "vms": [...], "unknown": [...]}

The ending pass reads a thread's answer from it only when `current` and
`stopped` are the record's and `at` is within one spacing of the pass. The
run's own state (`{"pid", "start", "started"}`) is
`$SMINOS_HOME/daemon/census-run.json`, written under
`daemon/census.lock` and by nothing but the census's start and its
reaping.

### §8. Other names

- `S/sminos_records.py`: `lane_of(record) -> "A" | "B"`, the rule
  `member_frame` holds today, moved there; `record` may be `None`.
- The spawner's bound, which a spawn's child with no seat is given before
  it joins as any session does (M1): twice `poll_uuid`'s own span (its
  iterations times `poll_interval`: 60 s as shipped, so 120 s), counted
  from the start of the session's process.
- `Member` (the view's row) gains `thread` (the thread id, `""` for none),
  `opened` (`"spawned"`, `"human"` or `""`), `thread_sessions` (the other
  sessions of its thread that its continuation chain does not hold, newest
  first) and `end` (`""`, or why it has ended: `"retire"`, `"ended"`, or
  `"machine"` for a retired machine). `former` is unchanged: the
  continuation chain. `member_json` prints `thread`.
- `S/sminos.py`: `has_ended(member) -> bool`, true when `member.end` is
  set: read from the log and the org's state alone, on any machine. `View`
  gains `ended`, the rows of the project's ended threads.
- `S/sminos.py`: `cleared_from(session, source) -> str`, the session the
  process of a `SessionStart` hook left at a `/clear`, `""` for none,
  read from the note `sminos/hooks/smns-cleared.sh` keeps of the
  engine's `SessionEnd`: `$SMINOS_HOME/cleared/<pid>.json`, the hook's
  payload as it came, believed for 60 s.
- `S/sminos_daemon.py`: `sweep_threads()`, called by the daemon's loop and
  by `daemon tick`: the stop pass at every call, the ending pass on its
  spacing and when a census has landed since the last.
- The hold's outcome from `deliver_next` and `push_member` is
  `"held:human"`.
- `sminos retire <member> --owner-unknown`.
- Environment, each read where its default is defined:
  `SMINOS_THREAD_END_AFTER` (seconds; default three days),
  `SMINOS_THREAD_END_EVERY` (seconds between ending passes; default 3600),
  `SMINOS_DEVCLOUD` (the devcloud CLI to run),
  `SMINOS_DEVCLOUD_TIMEOUT` (seconds one question may take; default 60;
  the grace before the driver is killed is 5 s).

### §9. Dependencies

- Python's standard library alone, at sminos's floor (3.10).
- devcloud 0.17.2 or later (on `main` at this plan's pin) for
  `devcloud vm owned-by` and for what its exit 6 means. An older copy
  reads as unknown, named (M5).
- The engine: the facts the code already rests on (`continued_in`'s
  record, the session record per process, `CLAUDE_PID` in a hook's
  environment), and those of the composite's `clear-compact-experiment.md`
  (engine 2.1.327): a `/clear` fires `SessionEnd` with reason `clear` and
  the old id, then `SessionStart` with source `clear`, in one process; an
  in-session `/resume` starts its target while the process's record names
  the session it left; a compaction keeps the session id. M6's live pass
  records the version it ran on.
- MAWS, none that blocks: the vectors' file is on its master (M1 pins
  it); its endpoint's own
  withdrawal at a lane change and its app's reader rule are MW's and are
  wanted by this child's release without holding it.

## Surprises & Discoveries

Found while the plan was written and reviewed against the code; the
executor adds its own below.

- Observation: a `to` on a `retired` is guarded only under reason
  `continued`. Under another reason it is neither redacted for an audience
  that may not reach the session named nor checked by the hub.
  Evidence: `session_refs` and `redact` in `S/sminos_audience.py`; MAWS's
  `sessionRefs` (`apps/org-protocol/src/audience.ts`), pinned by
  `sminos/tests/audience-vectors.json`.
- Observation: a message addressed to a closed terminal session survives
  today only because that session is no member. Once it stays a member,
  the delivery operation would settle the message as `recorded`.
  Evidence: `push_member`'s branch for a member with no seat; `report_closed`
  and `refuse_owed` in `S/sminos_outcomes.py` ("a closed session is no
  member, so deliver_next never sees it").
- Observation: on a cut-over machine the words and reach gates come before
  the push, and the uplink asks about the same rows; an unanswered `words?`
  is a failed attempt, and attempts settle an event.
  Evidence: `deliver_next`'s order; `ask_words`, `expire_asks` in
  `S/sminos_uplink.py`; `words_unanswered` and `_conclude` in `S/sminos.py`.
- Observation: `daemon owed` exits 1 for an event owed to a member and 0
  for one waiting for a closed session, and it tests membership first.
  Evidence: `owed_in` and `cmd_owed` in `S/sminos_daemon.py`.
- Observation: a session's `state` has four writers.
  Evidence: `publish_state`, `rejoin_former` and `restate_withheld` in
  `S/sminos_daemon.py`; `snapshot` in `S/sminos_visibility.py`. All pass
  `lifecycle`.
- Observation: a spawn's child is joined today by its own first hook, as a
  seat-less background session, before its seat names it: the engine is
  started before the seat's record is written, and the session's id is
  learned by polling.
  Evidence: `spawn_fresh` (`run_claude_bg`, then the record, then
  `poll_uuid`); `record_session` and `session_evidence`, which take a
  pending launch's child with no seat as joinable.
- Observation: a fresh fill starts a process without passing
  `resume_session`.
  Evidence: `cmd_fill` without `--resume` and `cmd_spawn` onto an existing
  alias both call `spawn_fresh`.
- Observation: a seat from before this code knows its earlier occupants
  only by its `history` (the last ten) and by the `seat` field of their
  `joined` events.
  Evidence: `spawn_fresh`'s re-fill branch; `joined_fields`.
- Observation: any JSON file at the root of `$SMINOS_HOME` reads as a seat.
  Evidence: `record_files` globs `*.json` there, and `load_seat` gives
  every missing field a default.
- Observation: the reader rule does not cover a session whose latest
  `joined` an older copy wrote, and a session started before an update
  writes such a `joined` from its own hooks for as long as it lives.
  Evidence: `refresh_joined` and `publish_owners` append a `joined` built
  by `joined_fields`; the vectors' fourth case.
- Observation: at a `/clear` nothing the engine offers at the new
  session's start names the session that was left; the `SessionEnd` it
  fires just before, in the same process, does. sminos registers no hook
  for `SessionEnd` today.
  Evidence: the composite's `clear-compact-experiment.md` (engine 2.1.327,
  two trials); `sminos/hooks/hooks.json`.
- Observation: at an in-session `/resume` the process's engine record
  still names the session that was left while the target's `SessionStart`
  hooks run, and the guide's stand-in for a session no record names yet
  takes that record's name with it. The name is refused only because the
  session left still holds it.
  Evidence: the same experiment; `_hook_engine` and `guide_text`
  (`held_alias` under `shadowing`). Not changed by this child.
- Observation: delivery settles, before any push, an event whose push was
  already noted and one whose receipt the recipient's process admitted;
  both can be true of a session that has since exited.
  Evidence: `deliver_next`, `holder_owed` in `S/sminos.py`.
- Observation: a spawn's binding can fail to be written without anyone
  being told, and a launcher that cannot read the engine's banner drops
  the pending launch after the engine has started.
  Evidence: `claim_launch` (it logs and goes on); `spawn_fresh`
  (`drop_pending` when no background id is parsed).
- Observation: devcloud's driver starts a provider in a process session of
  its own, and takes it down only when it is itself interrupted or
  terminated.
  Evidence: `Client.call` in `devcloud/driver/provider.py`; `_terminate`
  in `devcloud/driver/cli.py`.
- Observation: sminos 1.27.10, given a session with no process and no
  seat, reconciles it to `ended` at its first reading verb and from then
  on delivers nothing to it and settles nothing for it.
  Evidence: that revision's `_reconcile`, `deliver_owed` (it walks the
  view's members) and `report_closed`.
- Observation: `sminos resume` returns a retired seat to its project
  today.
  Evidence: `resume_session`'s `launched` calls `join_seat`, whose guard is
  only that the latest membership is not `joined`.
- Observation: the driver needs a Python 3.11 where sminos runs on 3.10,
  and runs a provider's own tool from the `PATH` it is given.
  Evidence: `devcloud/bin/devcloud`; `MIN_PYTHON` in `S/sminos.py`.
- Observation: the gates check out one commit, so a test that needs an
  older revision of this repository must fetch it.
  Evidence: ci-kit's `setup.fetch_depth`, default 1, unset in
  `.github/ci-kit.yml`.
- Observation: on an enrolled machine a person's words from a terminal are
  delivered only on an endpoint's verdict, so a scratch store enrolled by
  hand delivers a session's message and never a person's.
  Evidence: `WordsGate` and `words_route` in `S/sminos.py`.
- Observation: every closed terminal session becomes an ended thread whose
  record D1 keeps, and a `/clear` makes one each time. Nothing bounds
  their number.
  Evidence: D1's lifecycle; the thread store's layout in Interfaces §1 is
  the answer for the daemon's cost, and `list --all` has none (the
  composite: Deferred).

## Decision Log

- 2026-11-17 — **Verification.** This plan gets one
  `doperpowers:adversarial-reviewer` pass before it is executed (done
  2026-11-18, below). Execution is by one `doperpowers:plan-executor`,
  which runs the milestones and the review at each milestone's boundary
  before the next consumes it. The branch gets doperpowers:review-code at
  the high rung, as the composite's Decision Log sets for T1: it changes
  who stays a member, with privacy consequences.
- 2026-11-17 to 11-18 — **The pin moved four times** as the composite
  took its children's results and this plan's reviews: blob `8c29b665`
  (`main` `88e771ba`), `681c0075` (`279bb44a`: a `/clear` is no
  continuation, X9 as built), `135fb0f4` (`ca9b6df4`: the first fold of
  this plan), `d21cf691` (`8393570c`: both reviews' rulings).
- 2026-11-18 — **The first review and the holder's rulings.** The
  adversarial reviewer read the plan at `b45a5172` against the code and
  returned fourteen findings; each was checked in the code again. What the
  holder ruled, all of it in the composite at this plan's pin: a
  human-opened thread's id is minted and never a session's; at a `/clear`
  the alias goes with the new session (the first version had left it with
  the session that was left); at an end, what is held for a thread is
  settled; an older copy's unstamped `retire` counts as ended for every
  reader; `Member.former` keeps today's meaning; devcloud's minimum is
  0.17.2; the vectors have a fifth case; the oldest sminos to test against
  is 1.27.10.
- 2026-11-18 — **The confirm pass and the second rulings,** on `1623e50d`:
  six findings closed, eight left, each checked in the code again. This
  was the last round on the plan; what remains is found on real code, by
  the milestone reviews, the failure-injection tests and the branch's
  review.
  - Decision: transitions are journaled in the record, and recovery
    replays the journal and nothing else. Rationale: two rounds of rules
    that inferred an unfinished transition from how the record and the log
    compare each left interleavings open (a return cut short read as an
    end cut short; a late hand-off left its successor under a provisional
    stamp). Alternative rejected: a longer table. Date/Author: 2026-11-18,
    the composite's holder; the entry's shape and its six rules are this
    plan's (Interfaces §6).
  - The hold stops pushing and asking and nothing else; settlements still
    run under the delivery lock, and the late-verdict paths ask the hold
    (M3).
  - Every reader of membership goes through one reducer, with no
    exception (M1; the first revision had left three on the raw last
    event).
  - A spawn's child is told by the launch token in its own environment,
    whatever the binding's state (M1; the first revision read the
    binding).
  - The `/clear` witness is sminos's own note of the engine's
    `SessionEnd`, from the composite's experiment, which also settled the
    compaction question: nothing is built, and M2 opens with no check.
  - A stuck question to devcloud is stopped by SIGTERM to the driver, a
    grace, then a kill of the driver and its descendants; the census's
    state has a file of its own (M5).
  - Against 1.27.10 the suite asserts what that revision does; the
    settlement by a stale deliverer is not in the fixture (M6).
- 2026-11-18 — **Mechanisms the rulings left to this plan,** each with its
  reason in the milestone named:
  - the journal's entry carries the events whole, each event carries the
    entry's id, and an event is appended only when its session's own
    events hold none of that kind with that id; a first join, an adoption
    and the stop mark are not journaled, since a rule that exists
    finishes each (M1; Interfaces §6);
  - a spawn's child with no seat is given twice the launcher's own
    polling span from its process's start, and a launcher slower than
    that absorbs the record made meanwhile (M1);
  - an absorption lives in the record of the thread that goes on, deletes
    the other record as its last step, and is refused, with nothing of
    reach carried, when that record fails its guards (M2);
  - the process that handed a session off is told from a later return by
    the `pid` its retirement recorded, as today (M2);
  - a thread's row is read per episode (M2; Interfaces §4);
  - a held session may be passed by without a delivery pass only on the
    memory of a full pass in which nothing settled, while nothing that
    pass read has changed (M3);
  - a held event does not follow a continuation: `_owed` reads no lineage
    and delivery is keyed by the addressed session throughout; logged as
    debt (M3);
  - both places that start a process for a seat check for a human-opened
    record under the seat's lock (M3);
  - X3's value is built in `lifecycle` (M3);
  - questions are closed while a thread is stopped, by a mark of the stop
    that was swept (M3);
  - the note of a `/clear` is a file named by the engine's pid, written by
    a hook that starts no Python, believed for a minute by the start of
    the same process; the alias is released by a mark on the old thread's
    record that alias selection honours until a new process holds its
    session (M3);
  - an ended thread is returned by any process when its end saw none (M4);
  - the census is a child process of the daemon, one per machine (M5);
  - devcloud's version is read from the manifest beside the copy found
    (M5);
  - `test-older-cli.sh` fetches the one revision it needs and fails
    without it (M6).
- 2026-11-18 — **Residue decided in the first version and kept,** which
  the composite holds: `--owner-unknown` at a terminal alone; two stores
  behind one module; `seat add --session` refused for a human-opened
  thread; a refill's event keeps `replaced` and gets no `to`; the hold is
  a delivery outcome, and `resume`, `fill --resume` and `send --wait` aimed
  at a held thread exit 4; the three-day clock runs from the stop the
  sweep recorded; an ended thread reads `retired` in lists; `sminos resume`
  no longer returns an ended spawned thread; only exit 6 reads as none.

## Outcomes & Retrospective

Pending — written at finish.
