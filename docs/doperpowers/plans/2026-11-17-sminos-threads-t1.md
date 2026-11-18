# sminos threads, T1 — identity and lifecycle: execution (2026-11-17)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **T1** (Threads: identity and lifecycle — plan). **Parent pin:** `main`
> `279bb44a`, that file's blob `681c00756223671eb498ccb2a63e1b2023e7e693`.
> The child's section there is its spec, D1 and D7 its design, X1, X2, X3, X6,
> X7 and X9 its contracts. This document carries the constraints and the
> milestones and nothing of the design. Read before M1: the composite's
> Purpose, Grounding Baseline (the sminos part and its table), Terms, D1, D7,
> D2's "Not woken" and D4's paragraphs on ownership (what T2 and EN build on
> what T1 leaves), the T1 section, the Cross-Child Contracts (X9 holds
> devcloud's command as built), and its Decision Log's last two entries. The
> code map the composite cites
> (`docs/doperpowers/research/2026-11-17-sminos-channels/code-map.md`, §1 and
> §5) locates most of what changes; its line numbers have moved, its function
> names mostly have not.

After this child a session its human opened no longer leaves its project when
its terminal closes. It stays, listed `stopped`, under its name and its
in-charge line; a new session of the same name is told apart from it; what is
sent to it waits and reaches it when its human opens it again. It ends only
when it is retired or has been stopped for more than three days, and it comes
back as itself when it is reopened. Nothing wakes such a session yet (T2
does), and a sender is told so as it sends. A session sminos spawned is woken
as today. How to see it working is T1's acceptance in the composite, run as
Concrete Steps gives it.

## Progress

- [x] (2026-11-17) The plan written against the code at `main` 279bb44a and the composite at the pin above.
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
- **Short id**: the first eight characters of a session id, what `@short`
  and `alias#short` carry and what devcloud keeps of a VM's creator.
- **The hold**: what happens to a message addressed to a stopped
  human-opened thread until T2 ships. It is recorded, stays owed, and
  starts no process.
- **The thread sweep**: the daemon's pass over this machine's threads (M3,
  M4), run by `sminos daemon run` and by `sminos daemon tick`.
- **The engine**: Claude Code, the `claude` CLI. Its **session record** is
  the file it keeps per running process under its config directory
  (`peer_records` reads them); sminos's own **session record** is
  `sminos_records.py`'s, which holds a session's owners and reach. Where
  the two could be confused the text says whose.
- **The driver**: devcloud's VM driver, `devcloud vm …`, which runs on a
  Mac that holds a seed key and nowhere else.

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
  only.
- **Lane B keeps today's rules entirely** (D1). Whether a session is lane A
  is read by one function, the one the endpoint's `member` frame is built
  with, so a session is a thread exactly when sminos tells the endpoint it
  is lane A.
- **Older code on the same machine** is defended by D7's two rules and
  nothing else: a human-opened thread's record is in the thread store, and
  every reader that knows threads passes by an unstamped `retired` with
  reason `ended` for a session whose latest `joined` is stamped. What D7
  lists as accepted is not defended; where older code leaves the log and a
  record disagreeing, this code brings them back together (Interfaces §6,
  the rows for older code) and defends nothing more.
- **The record first, then the event,** for every transition that writes
  both (Interfaces §6), as `_retire_one` orders a retire today: a membership
  event is appended under its writer file's lock with a guard that reads the
  record again, so no reconciliation can undo a transition between the two
  writes.
- **What a session reads keeps today's words** (X6): the guide, the skill,
  the spawn preamble, `sminos help` and a verb's output say session, seat
  and member. "Thread" appears in code, in records and in the event field.
  The rewrite into the new words, and the manager's skill, are CH's. Each
  milestone writes the lines its verbs print; M6 evaluates them with the
  skill.
- **`sminos/skills/sminos/scripts/sminos.py` is one file of some fourteen
  thousand lines,** and T2 changes the same functions after this child.
  New logic goes in `sminos_threads.py`; `sminos.py` gets calls at seams.
  `origin/main` is merged before M1 and before the final push.
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
  per-tick duty reads an ended thread's record. The `sminos-idle` gate is
  the check.
- **Tests are hermetic.** The suite's stub `claude`, its temporary `HOME`
  and `SMINOS_HOME` stay the only engine and store a test meets. No test
  reaches a real devcloud driver: the suite's shared setup points the
  lookup (M5) at a stand-in. Fixtures use invented names; the repository is
  public, so no hostname, account name, project id or local path enters a
  test, a comment or this document.
- **The manager's command imports the CLI's modules**
  (`sminos/skills/manager/scripts/`). Its tests pass after every milestone
  and its skill is not touched; a sentence of its scripts' `CLAUDE.md` that
  a milestone makes false is corrected in that milestone.
- **One change, one version.** The child merges as one pull request that
  leaves the repository releasable beside an older sminos on another
  machine (D7), with sminos's version bumped in it
  (`scripts/bump-version.sh --plugin sminos`). It adds no event kind: an
  older reader meets new fields only (`thread`, `wake`, `closed`), which it
  does not read.

## Plan of Work

T1 changes one state machine: a thread's record on its machine and the
lifecycle events that machine writes about it. M1 gives every member the
record and the stamp, under today's rules. M2 says which session ids are one
thread and makes any of them reach the current one. M3 replaces "its process
ended, so it left" with `stopped` and the hold. M4 adds the two ways a thread
ends and the two ways it returns. M5 puts devcloud's answer in front of every
path that ends one. M6 changes what sessions are told, checks an older sminos
against the new store, pins the vectors shared with MAWS, and runs the
acceptance.

Each milestone ends with the suites green for what it touched and with the
nested `CLAUDE.md` beside the code it changed, and `sminos help`'s text
(the module docstring of `sminos.py`), true again. The skill, the preamble
and their evaluation are M6's.

**One unit.** The composite sees one unit with one verification strategy, and
so does this plan: one state owner (the thread's machine), one store, one
hermetic suite. Three parts are verified differently (M2's live check of the
engine, M5's question to another program, M6's evaluation of text), and each
is small and cannot land without the rest: M4 without M5 would end the
owners of VMs, and M3 without M4 would keep every closed session forever. If
the unit had to be cut, the seam is after M2: the record, the stamp and the
naming change nothing a session sees and are what T2, CH and EN read, and
M3 to M6 are the lifecycle.

### M1 — Every member has a thread record, and its events say which thread

**What exists at its end.** Every lane A session of this machine that is a
member has a thread record from its first join: a spawned one in its seat
record, a human-opened one in the thread store. Members and seats that
existed before are adopted the first time this code reconciles them. Every
lifecycle event sminos writes for such a session is stamped, and
`sminos list --json` shows each member's `thread`. A reader that knows
threads still counts a member after an unstamped `ended`. The record and the
log agree at every step, under today's rules: a human-opened session still
leaves when its process ends, now by a stamped `ended` its record holds too,
and comes back when it runs again.

**What it touches.** New: `sminos/skills/sminos/scripts/sminos_threads.py`;
`sminos/tests/test_threads.py`, registered in `run_suites` of
`sminos/tests/run-sminos-tests.sh`; `channel-rule.json` and its pin under
`sminos/tests/vectors/maws/`, with `sync.sh` there taking the file's name.
In `sminos.py`: `lifecycle` (the stamp, and the record's copy of the alias),
`join_on_sight`, `joinable`, `join_seat`, `spawn_fresh` and `cmd_seat_add`
(the record at first join), `_reconcile` (adoption, and the rows for older
code), `cmd_retire`, `_retire_one` and `cmd_remove` (the record before the
event, for a human-opened session too), the membership readers
(`latest_membership`, `_memberships`, `_projection`, `_lineage_scan`,
`retirement_holds`, `handed_to`), `_member`, `Member` and `member_json`
(`thread`, `opened`), `cmd_record` and `record_session` (the launch's
options). In `sminos_records.py`: `lane_of`, which `member_frame` in
`sminos_uplink.py` then calls. The other membership readers found while
planning: `closed_sessions` in `sminos_outcomes.py`, `rejoin_former`,
`publish_titles` and `restate_withheld` in `sminos_daemon.py`,
`sminos_visibility.py`'s snapshot. The executor finds the rest by what they
read (`MEMBERSHIP`, a `retired` event's `kind`). `Plane.stale` and `inputs`
in `sminos_plane.py`.

**Interfaces.** Exposes the thread record (X1, Interfaces §1), the stamp
(§2), the reader rule (X7, §3) and `lane_of` (§8). Consumes nothing.

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
- *An ended human-opened record moves aside,* into `threads/ended/`.
  Reason: D1 keeps an ended thread's record, every closed terminal session
  becomes one, and nothing bounds their number, while the daemon reads the
  live ones at every tick. No view lists from that directory; it is read
  when a session of an ended thread runs again.
- *The thread id.* A spawned thread's is its seat id, which is its first
  session id for every seat `spawn` made and is already what its `joined`
  events carry in `seat`. A human-opened thread's is its first session id;
  for a member adopted from before threads, the oldest session id its
  continuation chain holds in this machine's log (`lineage_of`), so that an
  old `Sminos-Session` line or creator tag names the thread. Two
  exceptions to D1's lean: a seat registered vacant (`seat add` with no
  session) has an id before it has a session, and keeps it; and M2 mints
  one for a former session that runs again. So a thread id is matched as
  its own kind of name, never assumed to be a session's.
- *`opened` is fixed when the record is first made, and no verb changes
  it.* A record that begins as a seat (a `spawn`, a `seat add`) is
  `spawned`; one that begins on sight is `human`. Every seat that exists
  when this code first runs is `spawned`, so nothing that is resumed today
  stops being resumed.
- *`seat add --session` aimed at a session that already is a human-opened
  thread is refused,* saying that its record already keeps it. Reason: D1
  says such a thread does not take a seat's fixed alias and project, a
  thread has one record, and the seat would be the way around D1's rule
  that no verb but the wake starts a process for it. For a session with no
  thread the verb does what it does today: the core suite makes most of
  its seats this way, around invented sessions.
- *Adoption is lazy and writes one event.* The first reconciliation by
  this code of a joined local member with no record makes the record and
  joins it again, stamped, as `publish_owners` joins a member again
  (`joined_again` gives the fields); the guard is "its latest `joined` is
  unstamped", so it happens once. Without that `joined` the reader rule
  would not cover a member that joined before the update. The same guard
  stamps again a member an older copy joined since: a session started
  before the update runs the older hooks for as long as it lives, and
  their `refresh_joined` and `publish_owners` write an unstamped `joined`,
  after which the older code's `ended` would be honoured.
- *The record is this machine's truth for its own threads.* Reconciliation
  brings the log to it, or it to the log, in the three cases older code
  can make (Interfaces §6, rows 15 to 17), and in no other.
- *A thread record is evidence of membership,* as a seat is: `joinable`
  answers yes for a session whose human-opened thread has not ended,
  whether or not a process runs it. The first join keeps today's test (the
  engine records it `interactive` or `bg`, no headless run unless marked).
- *The reader rule lives in one predicate* (Interfaces §3) that every
  reader of "is this session a member" goes through. A guard that decides
  under a writer file's lock reads through it too, so an older CLI's
  unstamped `ended` neither makes this code join the member again nor
  stops a later event of its own.
- *The rule's cases are MAWS's file,* `channel-rule.json`, whose `retired`
  list this milestone's test runs through every such reader. MAWS's master
  may not hold the file when M1 runs: then the copy is written from
  Interfaces §B of MAWS's execution document for MW (the MAWS repository,
  `docs/doperpowers/plans/2026-11-18-mw-sminos-channels.md`), byte for
  byte, with no pin, and M6 sets the pin. One pin per vendored file
  (`channel-rule.PIN.json` beside `PIN.json`, which `project_rule_parity.py`
  reads as it is), so that vendoring this file does not move the project
  rule's pin. The check fails on a copy whose hash is not its pin's and
  says, without failing, that a copy has no pin yet.
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

**What it does not touch.** Which sessions are one thread, and how a
former id resolves (M2). `_reconcile`'s `ended` for a process that is gone,
beyond writing the record with it (M3). Delivery, the daemon's duties.
What sessions are taught. The alias and project rules of either kind of
thread: a spawned one's alias stays fixed and `join` stays refused for it;
a human-opened one is named and moved as today. The `channels` field
beyond creating it empty and carrying it.

**What it proves.** Acceptance 7's first half (the stamp); the reader half
of acceptance 10; 11 for its surface. Its tests pin:

- a session that joins on sight has a record in the thread store and none
  in the seat store; a spawned one has the thread keys in its seat record
  and nothing in the thread store; a lane B session has neither and its
  events are unstamped;
- a member and a seat from before threads are adopted at the first
  reconciliation, with one stamped `joined`, and no second one at the next;
  an unstamped `joined` written after it is stamped again, once;
- the four `retired` cases of the vectors through every reader of
  membership; and a guard under a writer file's lock reads through the
  rule: after an unstamped `ended`, a later event of the session's own is
  still appended;
- record and log agree after each of today's transitions: its process
  gone (ended, the record moved aside), run again (restored), retired by
  hand, moved by `join`;
- rows 15 to 17 of Interfaces §6, each from a log an older copy wrote
  (what rows 15 and 16 mean for a session with no process is M3's, once a
  stop no longer ends a thread);
- `seat add --session` on a human-opened thread is refused, and on a
  session with no thread makes the seat as today;
- a record write from the hook that cannot have its lock in time is
  skipped and made by the next reconciliation;
- launch options: a path with a space is one value, an inline JSON value
  and an option outside the list are not recorded, and an unreadable
  argument list leaves `options` absent;
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
machine that only reads the log too. A `/clear`, a fork and an in-session
`/resume` each leave the new session id with a thread of its own and no
link to the session it came from, and a fork's start guide says it is a
copy with an identity of its own.

**The milestone opens with a live check** (the composite's Delegated
unknown, assigned to T1): *does a compaction give a session a new id, and
if it does, what does the engine write that says so?* A friction entry
reports a long-lived background session going on under a new id "from a
compaction summary"; no code shows it. Run it on the engine version
installed when the milestone runs, twice each for an interactive session
and a `claude --bg` one (Concrete Steps): note the session id, compact, and
observe the id after, whether the process is the same, what the
`SessionStart` payload says, and whether the old transcript ends in a
record naming the new session, as a hand-off's does. Promote: if a run
shows a new id and the engine left a record of its own that names both
sessions, compaction is a second continuation, read from that record as
`continued_in` reads a hand-off's and passed through `hand_off`, and the
record hook's `SessionStart` matcher in `sminos/hooks/hooks.json` gains
`compact` if the hook must see it. Discard: if every run keeps its id,
nothing is built. If a run shows a new id and no such record, nothing is
built either, the new session is another thread (the constraint on doubt),
and the composite's holder is told, since a standing responsibility would
then split at every compaction. Whichever it is, the verdict, with the
engine version and what was observed, goes to Surprises & Discoveries and
to the composite's holder. The friction entry also reports a finished
background job resumed under a new id with its history copied; that is the
engine starting a copy, which stays another thread.

**What it touches.** In `sminos.py`: `hand_off` and `follow_seat` (the
record advances with the session, for a human-opened thread as for a
seat), `spawn_fresh` and `cmd_seat_add` (a refill advances the thread),
`_projection`, `lineage` and `_member` (what `former` holds),
`match_members`, `find_target`, `_resolve_tag`, `who_matches` and
`who_lines` (a former id, and the thread id, as names), `guide_text` (the
fork line). `sminos/tests/test_threads.py`, `sminos/tests/test-guide.sh`,
`sminos/tests/test-who.sh` and the core suite's hand-off and occupancy
cases. `sminos/hooks/hooks.json` only if the check promotes.

**Interfaces.** Consumes M1's `advance`, `thread_of`, `ensure` and the
stamp. Exposes the resolution rule (X2, Interfaces §4), the continuation
and refill event shapes (§2), `Member.former` as §8 gives it.

**Decisions.**

- *The continuation is today's, and nothing is added to its evidence.*
  `continued_in`, `predecessor` and `handed_to` decide that one session
  continues another; `hand_off` records it. `hand_off` already carries the
  cursor and the join override, moves a seat, retires the old session
  `continued`, renames the new one, and is ordered so that a hand-off cut
  short is finished by the next. The thread record's `advance` joins that
  sequence where the seat's move is, before the retirement, so the same
  holds for it, and a hand-off whose log part an older copy wrote is
  finished the same way. The one call that carries reach stays
  `ensure_record(…, former=[old])`; nothing else passes `former`.
- *A refill keeps today's event:* `retired`, reason `replaced`, stamped,
  with no `to`. This overturns the composite's advisory lean (an event
  shaped as hand-off's, with `to`, under a reason of its own). Evidence: a
  `to` is a reference to another session, and only under reason
  `continued` is it one the two repositories guard: `session_refs` in
  `sminos_audience.py`, pinned to MAWS's `sessionRefs` by
  `sminos/tests/audience-vectors.json`, is what `redact` nulls for an
  audience that may not reach the session named and what the hub checks.
  Under `replaced` it would name the new session, whose reach is its own
  launch's, in the old session's stream, to that stream's audience,
  unredacted and unchecked. The stamp links the two sessions without
  either naming the other.
- *What `former` holds.* A member's `former` (the session ids a name
  still reaches it by) becomes its continuation chain, then the other
  sessions its thread has had, read from the stamps of the log, so that it
  is the same on a machine that holds no record. `_member` takes alias,
  in-charge line, status, `by` and worktree along all of them, and owners
  along the continuation chain only.
- *A name's order.* A name that is a member's current alias or current
  session comes before one that only matches a former session or alias,
  as `match_members` orders a former alias today. The thread id is matched
  like a session id. Session ids stay what addresses a message: the event
  names the current session.
- *A former session that runs again is another thread.* The cases: an
  interactive session resumed by id after it was handed to a job, and a
  replaced session of a seat resumed in a terminal. Today's code already
  makes the first its own member and drops the link (`_projection`: a
  `joined` after its own `continued` clears `to`). Its thread is
  human-opened, under its session id unless a thread already has that id,
  then a minted one. The thread that went on keeps the id and keeps the
  session in `sessions`; `thread_of(session)` answers the thread whose
  current session it is before one that only had it.
- *A `/clear`, a fork and an in-session `/resume` are pinned, not built.*
  Nothing in the code links them today, and nothing is added: each new id
  joins on sight (M1) and gets its record owners from its own evidence.
  `_hook_engine` lends such a session the process's engine record so that
  it can join; it lends no lineage. The tests below hold that line.
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
`stopped` (M3). The wake.

**What it proves.** Acceptance 3, but for the `stopped` listing of the
session a `/clear` left (M3); acceptance 7's second half. Its tests pin:

- a human-opened session handed to a background job: the record names
  the job as current with both ids in `sessions`, one stamp on both
  sessions' events, the job's record has the old one's owners, access and
  shares, the member lists once under the alias and in-charge line it had;
- a hand-off cut short after the record advanced, and one whose
  `continued` an unstamped writer wrote, are each finished by the next
  reconciliation;
- a refill: one thread id across both sessions, `retired` `replaced`
  stamped and without `to`, the new session's owners from its own launch
  and never its predecessor's (read on another machine's copy of the log
  too), the alias and the in-charge line kept;
- the thread id, and each former session id, as `@short`, `@alias#short`
  and a full id, reach the current session after a hand-off and after a
  refill, from another machine's copy of the log, for `say`, `send` and
  `who`;
- a `SessionStart` of source `clear` under a new id in the process that
  held a thread's session: two thread ids, no `continued` event, no owner,
  access or share carried from the old session's record;
- an in-session `/resume` of another session (source `resume`, same
  process): two threads, no `continued` event, the resumed session keeps
  its own owners;
- a fork (source `fork`), in the same process and in another: a thread of
  its own whose record owners come from its own evidence, no `continued`
  event, and the guide's fork line;
- a handed-off session resumed by id, and a replaced seat session resumed
  in a terminal: each a human-opened thread of its own, the first under a
  minted id, and its short id names it, not the thread that went on;
- the compaction case, if promoted.

### M3 — A closed session stays: stopped, held, and its sender told

**What exists at its end.** A session opened in a terminal and then exited
is listed `stopped` by `sminos list --stopped` and folded by `sminos list`,
under its alias and in-charge line; a new session with its name is told
apart from it as two live ones are today. Reopened with `claude --resume`,
it is live again under the same alias, and what was addressed to it
meanwhile arrives. The session a `/clear` left is listed the same way and
comes back when its id is resumed. While a session is stopped an addressed
message is recorded and held, and the sender's line says the session is
stopped and is not woken because its human opened it, with the machine it
waits on when that is another one. `sminos send` to it is held the same
way; `sminos resume`, `fill --resume` and `send --wait` aimed at it record
their message, start no process and say so; a fresh `fill` of it is
refused. A spawned session is resumed exactly as today. A stopped session's
open asynchronous questions are closed in its project's log, and a session
whose lane changes is told gone to the endpoint before its new frame.

**What it touches.** In `sminos.py`: `_reconcile` (no `ended` for a
thread), `push_member` and `push_event` (the hold), `resume_session` (the
hold at the one place every resume passes), `resolve_seat`, `cmd_resume`,
`cmd_fill`, `_send`, `send_to_member`, `deliver_say` (the sender's line),
`unreachable_hint`, `who_lines`, `derive_refusal`. In `sminos_daemon.py`:
`publish_state` (X3's field), `sweep_threads` (new), `owed_in`. In
`sminos_outcomes.py`: `closed_sessions`, `of_push`. In `sminos_uplink.py`:
`publish_members`. The tests that pin `ended` for a session its human
opened, in the core suite and in the suites that hold the word
(`test_owed.py`, `test_session_plane.py`, `test_manager.py`,
`test_idle_reads.py`, `test_scale.py`, `test_holder.py`, `test-uplink.sh`,
`test-sync.sh`, `test-guide.sh`), and the sentence of
`sminos/skills/manager/scripts/CLAUDE.md` that says sminos retires such a
session once its process ends.

**Interfaces.** Consumes M1's record (`opened`), `lane_of` and the reader
rule. Exposes X3's first two values and `wake_of` (Interfaces §5), the
hold's outcome (§8), the closing event (§2), and the record's `stopped`
mark, which M4's clock reads.

**Decisions.**

- *What ends with its process, and what does not.* Reconciliation writes
  `ended` only for a session that is not a thread: a lane B session, as
  today. A lane B session that has a thread record from an earlier lane A
  life gets that `ended` stamped, so every reader honours it, with its
  record ended first (Interfaces §6, row 11).
- *The hold is an outcome of the one delivery operation.* An addressed
  event owed to a stopped thread its machine will not wake comes out of
  `deliver_next` in the `held:` family that `_conclude` already leaves
  owed with no attempt counted, on the sender's fast path and the daemon's
  alike. Today's code answers `recorded` there and settles the event,
  which would lose it for the reopened session: today it survives only
  because a closed session is no member, so delivery never sees it. An
  outside sender is told `recorded` once and the event stays owed, as
  `report_closed` does today for a closed terminal session:
  `closed_sessions` becomes "this machine's stopped sessions that are not
  woken". An `@all` reaches only the live, as for a stopped seat today. A
  read-only machine settles what comes from outside as it does today.
- *`resume_session` holds for `human`, whatever else is true.* D1 says
  every path that starts a process ends there, so the check sits there,
  and it does not depend on whether the thread has a seat: an older CLI
  may have given a human-opened session one (D7), and this code still
  holds it. T2 replaces the hold with the wake at the same place.
- *The verbs.* `send` to a stopped human-opened session does what a tagged
  `say` does: recorded, held, exit 0. `resume`, `fill --resume` and
  `send --wait` record their message as an addressed one, which is held
  like one (D1), say that nothing was started and why, and exit 4, the
  code for a target a verb cannot reach now: what they were asked for (a
  process, a reply) did not happen, and a script must not read it as
  done. A fresh `fill` is refused and records nothing. For these verbs
  `resolve_seat` has to find a thread that has no seat; it answers
  through `find_target`'s rules, so a name that is ambiguous for `send` is
  ambiguous here.
- *X3's first values* are published on the thread's `state` event when
  its word is `stopped`, and the event is written again when the value
  changes while the word does not (Interfaces §5). A sender reads them with
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
- *Closing the questions* is the sweep's, at the same transition: for each
  `question` of the thread's sessions with no `answered` for its `src`, an
  `answered` is appended through `append_host` (which chooses the store
  and the asker's writer, and drops a second copy), with the text and the
  marker Interfaces §2 gives. A closing is final in the log: the log
  admits one answer per ask, so nothing reopens it.
- *After a `/clear` the alias stays with the session that was left.* The
  engine keeps a session's name across a `/clear`, the stopped thread
  holds that name as its alias (D1), and `held_alias` never gives a new
  session a name another member holds (`shadowing`): the new session goes
  by its short id until it is named, and a message to the alias is held
  for the stopped one. Today the cleared session takes the alias, because
  the session it left is retired at once. This follows from the owner's
  ruling and from D1's alias rule; it is pinned so that it is seen, and
  reported to the composite's holder.
- *`derive` does not fork a stopped human-opened session.* `derive --all`
  forks every local member with enough activity and no line; today a
  closed terminal session is no member, so it is never forked. Keeping it
  that way keeps the daemon from starting an engine in a closed session's
  directory, which for a protected folder is the fault D2 names.
- *`gone` before a frame whose lane differs from the one last sent,* in
  `publish_members`, so the endpoint withdraws the old listing before it
  takes the new one. MAWS's endpoint will withdraw it on its own when a
  `member` frame states the other lane (its child MW); sminos's `gone`
  stays, and is harmless beside it.

**What it does not touch.** The wake's steps and its other exclusions
(T2). The three-day rule and `retire` (M4). How a spawned thread is
resumed, the protected-folder rule for it included. `sminos decide`.
Whether a machine is on.

**What it proves.** Acceptance 1, 2 and 8; the rest of 3; 11 (the tests
that pinned `ended` for a session its human opened now pin `stopped`). Its
tests pin:

- its process gone: no `retired`, `stopped` in `list --stopped`, folded in
  `list`; reopened: live under the same alias and in-charge line, and what
  was owed is pushed, in order;
- after a `/clear`: the session left is `stopped` under its alias and its
  in-charge line, the new one is a member under its short id, a message to
  the alias is held for the stopped one, and the stopped one is live again
  when a process resumes its id;
- a lane B session still leaves with its process, unstamped when it never
  was a thread, stamped and with its record ended when it was;
- an older copy's unstamped `ended` for a stopped thread: `list --stopped`
  still shows it and reconciliation writes nothing; the same after an
  unstamped `joined`: it is joined again, stamped, at the next
  reconciliation (Interfaces §6, rows 15 and 16);
- an addressed `say` to it: recorded, still owed after daemon passes with
  no attempt counted, the sender's line as above; an outside sender's
  outcome is `recorded`, once; an `@all` settles as for a stopped seat;
- `send`, `resume`, `fill --resume`, `send --wait` and a fresh `fill`, each
  as decided above, with no `claude` call in the stub's log;
- a human-opened session that also has a seat record is held;
- the spawned cases of the suite pass unchanged;
- a `state` event for a stopped thread carries the value, is written again
  when only the value changes, and a sender on another machine reports it
  with the machine; with none published it reports today's line;
- an open asynchronous question is closed after two passes, once, not
  during a resume's stop and relaunch, and a later answer in the reopened
  session appends nothing;
- a lane change sends `gone` first;
- `derive --all` forks no stopped human-opened session;
- `daemon owed` counts an event held for such a session as it counts one
  waiting for a closed session today.

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
`cmd_remove`, `join_on_sight` and `joinable` (the return),
`retirement_holds` (removed: the record says it), `view_of` and `cmd_list`
(rows for ended threads), `_member` (a retired machine), `unreachable_hint`
and `no_member` (what a sender is told), `cmd_resume`, `resume_session` and
`send_to_seat` (an ended spawned thread). In `sminos_daemon.py`:
`sweep_threads`' ending pass.

**Interfaces.** Consumes the record's `stopped` (M3), `end`, `restore`,
`purge` (M1). Exposes the end events (Interfaces §2), X3's `ended` (§5),
and `has_ended`, which CH's rosters read.

**Decisions.**

- *An end is a record.* `end` marks the record, and for a spawned thread
  sets the seat's `status` to `retired`, the form older code reads as a
  retired seat (D7); then the stamped `retired` is appended. The explicit
  retire keeps reason `retire`; the three-day rule writes reason `ended`,
  which the shared vectors already call a stamped `ended`.
- *A session that retires itself is recorded before it is stopped.*
  `_retire_one` stops the process first today; run by the session being
  stopped, that can end the caller before the record and the event exist.
  A self-retire writes both, then stops what there is to stop.
- *"Reopened" is a process holding the thread's current session that
  started after the end.* It is the test `retirement_holds` makes from the
  event today, now made from the record's `ended` (its time, and the pid
  seen), for every thread: the process that ran when the thread was
  retired does not return it, however long it runs on in its terminal, and
  a new one does. A former session that runs again is another thread (M2).
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
- *The word in lists is `retired`* for an ended thread of either kind,
  today's word for a membership that ended and already in the chart's, the
  TUI's and `--state`'s vocabularies; where a line has room it says why
  (ended after three days stopped, retired by whom). A thread on a retired
  machine keeps today's `gone`, which the views and their tests pin, and
  is counted as ended by everything that asks: a tag naming it is refused
  saying its machine was retired, and it is not woken.
- *`--all` shows an ended thread from the log,* on its own machine as on
  any other: a session whose membership in effect is a stamped `retired`
  with reason `retire` or `ended`. A spawned one shows as a retired seat
  does today. No horizon is put on them: the composite gives none, and how
  long an ended thread stays in `--all` is reported to its holder.
- *A message addressed to an ended thread* is refused when it is sent, as
  a tag naming a retired member is today. An event already owed to it
  stays owed and is delivered if it returns.
- *`remove` and `retire --purge` apply to every thread* (D1): for a
  human-opened one they end it and delete its record. (The composite
  writes `seat remove`; the verb is `sminos remove`.)

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
- reopened by a new process: `joined` again under the same thread id,
  alias and in-charge line, the record back in the thread store with its
  `channels` as they were, and what was owed is delivered;
- after a self-retire the same process's hooks do not join it again, and
  a new process does; a spawned session's self-retire leaves the record
  and the event written even when the stop ends the caller;
- a spawned thread ended: its seat reads `retired` to this code and to the
  seat store's older readers; `fill` and `fill --resume` return it; `send`,
  `resume` and a tagged `say` do not;
- `retire --purge` and `remove` of a human-opened thread delete its record;
- a member of a retired machine: a tag naming it is refused saying so, and
  its word in `list --all` is `gone`.

### M5 — A thread that owns a VM is neither retired nor ended

DV is on `main` at this plan's pin (devcloud 0.17.0). The command, its
answer, its exits and its matching rule are the composite's X9, with an
example of each answer in DV's ledger
(`docs/doperpowers/ledgers/2026-11-17-DV.md`); this document repeats none
of it, and the milestone reads both as they stand when it runs.

**What exists at its end.** `sminos retire` of a thread that devcloud names
as a host's creator is refused, naming each host, and the three-day rule
leaves such a thread stopped. The same holds when devcloud gives no answer
it stands behind, and the refusal then names what could not be asked. Where
devcloud says its driver does not run, threads retire and end as M4 left
them. A person at a terminal can retire a thread whose answer is unknown,
with a flag that nothing else accepts.

**What it touches.** `sminos_threads.py` (`owned_by`, the one function that
runs devcloud, and `owned_vms`); `sminos.py`: `cmd_retire`, `_retire_one`,
`cmd_remove`, the `retire` parser; `sminos_daemon.py`: `sweep_threads`'
ending pass, `service_env`; `sminos_visibility.py`'s `confirmed`, made
usable with another prompt; the suite's shared setup (the stand-in).

**Interfaces.** Consumes X9. Exposes `owned_by` and `owned_vms` (Interfaces
§7), which EN's handover and `channel show` also read.

**Decisions.**

- *Where each guard runs.* The retire guard runs in the process running
  the verb: a session's Bash tool or a person's terminal. The three-day
  guard runs in the daemon, whose environment is the one its service file
  recorded at install (`service_env`): its `PATH` need not hold devcloud's
  `bin/`, and it has none of a session's variables.
- *How the CLI is found,* in this order, the first that exists being the
  one asked:

  | Where | Why there |
  |---|---|
  | the path in `SMINOS_DEVCLOUD` | the suite's stand-in; an operator's override |
  | `devcloud/bin/devcloud` beside the running sminos plugin's root | the copy in the same clone or checkout: where the daemon runs from (`installed_cli`), and never older than this sminos |
  | the same file in the doperpowers marketplace clone, found as `installed_cli` finds the clone | what a CLI running from the plugin cache has, where the cache holds sminos alone |
  | `devcloud` on `PATH` | last, because a long-lived session's `PATH`, or a service's recorded one, can name the cache directory of a devcloud from before `owned-by` |

  The launcher needs a Python 3.11 on `PATH`, sminos runs on 3.10, and the
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
  | exit 6 | none | devcloud says the driver does not run on this machine (a devcloud host, or no seed key) |
  | no copy of the CLI found | unknown | nothing on this machine said the driver does not run: the CLI ships beside sminos, so its absence is a broken install; the refusal says where it looked |
  | any other exit, a timeout, exit 0 with output that is not the JSON object, a launcher that cannot be run | unknown | the refusal gives the exit code and the first line of what it printed (no Python 3.11 is one of these, exit 1) |

  A provider tool missing from the daemon's `PATH` comes back from
  devcloud as `unknown` with its reason, so it holds the thread and is
  named.
- *Exit 6 is only as good as the environment it was asked in.* devcloud
  finds its seed and its profile under `HOME` unless `DEVCLOUD_SEED_FILE`
  or `DEVCLOUD_PROFILE` is set. `service_env` records those two for the
  daemon when the installing environment sets them, as it records the
  gateway's keys. Two wrong nones are left, both rare and bounded: the one
  D4 accepts (a Mac that lost its seed key), and a Mac whose sessions set
  one of the two variables after its service file was written. In either
  the VM's notices still go on to the project's live members, and the
  ended thread returns when reopened. The second is reported to the
  composite's holder beside the first. *Alternative: the record hook notes
  each pair of the two variables it meets, and the daemon asks under each.*
  It lost as more machinery than an override nobody is known to set
  deserves.
- *The names asked about* are the short ids of every session id the
  thread has had (`sessions`), bare: X9 matches a short id whole, and
  nothing through an alias.
- *One question per ending pass, and none when no thread is due.* The
  sweep asks once for every thread that is due and reads each thread's
  answer from the one reply (Interfaces §7). A thread that is owned or
  unknown is asked about again at the next pass, and `daemon.log` gets a
  line when its answer changes, not at every pass.
- *Asked before any lock, checked again under it.* The call takes seconds
  and a network, and is bounded (Interfaces §8); the end is written only if
  the thread is still as the decision found it (still stopped, the same
  current session), so a thread that came back meanwhile is not ended.
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
(EN). A copy in sminos of what a thread owns: there is none (D4).

**What it proves.** Acceptance 6. Its tests, against the stand-in, pin:

- owned: `retire` refused naming the host, an adopted machine named as
  one, the thread still a member; the ending pass leaves it stopped and
  says so once;
- each row of the second table that reads unknown: refused naming it, and
  the pass leaves the thread stopped;
- none and exit 6: the retire and the end go through;
- the lookup's order, each place found when the ones before it are absent;
- the names passed are the short ids of every session the thread has had;
- `--owner-unknown`: refused from a session, refused with no terminal,
  retires on unknown at a terminal after a typed yes, refused on owned;
- one call for all due threads in a pass, each thread's answer its own,
  and no call when none is due;
- a thread that came back between the question and the end is not ended.

### M6 — What sessions are told, an older sminos beside this one, the shared vectors, and the acceptance run

**What exists at its end.** The skill, the spawn preamble, the guide and
`sminos help` say what is now true, in today's words, with an evaluation
that shows the change in behavior. A script shows that the oldest sminos
still in a plugin cache, run against a store this code wrote, resumes no
human-opened session and that the `ended` it writes changes nothing for
this code. The vectors shared with MAWS are the copy of a named commit of
MAWS's master, pinned. The acceptance has been run as Concrete Steps gives
it, the version is bumped, and the branch is ready for its review.

**What it touches.** `sminos/skills/sminos/SKILL.md`,
`sminos/skills/sminos/references/spawn-preamble.md`, `guide_text`'s fork
line and the lines M3 to M5 made their verbs print; `sminos/CLAUDE.md`,
`sminos/skills/sminos/scripts/CLAUDE.md` and `sminos/hooks/CLAUDE.md`
wherever a milestone left a sentence behind; `docs/whats-inside.md` only if
a row's sentence became false; a new `sminos/tests/test-older-cli.sh`;
`sminos/tests/vectors/maws/channel-rule.json` and its pin; the version
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
- *The older CLI.* The version to run is the oldest one present in a
  plugin cache of the owner's machines when the milestone runs: the
  executor reads its own machine's cache and asks the composite's holder
  for the others'. The script takes the path of an older `sminos`
  launcher, so it runs against a cached copy on a machine and against a
  revision extracted from this repository's history (`git archive` of the
  commit that set that version) in the suite, where the clone has that
  history, and says so in one line where it has not. It drives this code
  and the older one against one registry with the suite's stub engine:
  this code makes a human-opened thread, stops it and holds a message for
  it; the older CLI then runs every verb that reads the store (`list`,
  `say` with its tag, `send`, `resume`, `fill`, `daemon tick`); the stub's
  log holds no `--resume` of that session; then this code's
  `list --stopped` still shows it. D7's accepted degradations (the older
  CLI settles the message it only recorded; it writes its `ended`) are
  asserted as what happens, so a change in them is seen.
- *The vectors' pin.* `sminos/tests/vectors/maws/sync.sh` copies
  `apps/org-protocol/vectors/channel-rule.json` from the commit of MAWS's
  master that holds it when the milestone runs, named in the pin, and the
  `retired` cases pass on that copy. A difference from the copy M1 wrote
  is a change of contract to pass, not to edit away. If MAWS's master does
  not hold the file by then, M1's copy stays, byte for byte what MAWS's
  execution document gives, the pin stays unset, and the open item goes to
  the composite's holder and into Progress: the build does not wait.
- *The live pass.* Two acceptance items rest on what the real engine does
  at a session's start and end (1, and 3's `/clear`, fork and in-session
  `/resume`), which the stub only models. They are run once on a real
  engine against a scratch store, the session loading the sminos plugin
  from the worktree in place of the installed copy (Concrete Steps). If
  the two copies cannot be kept apart on the machine the milestone runs
  on, that pass is run on the released version as the first step of the
  parent's acceptance, and is an open item reported with the branch.

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

**M2's live check** (the compaction question), on the machine the
milestone runs on, with the installed sminos; it changes nothing in the
repository:

1. `claude --version`, recorded with the verdict.
2. In a scratch directory, in a terminal multiplexer's own server so that
   nothing of the executor's session leaks into it, start `claude`, give it
   one prompt with a tool call, and note its session id (`claude agents
   --json`, or the transcript's file name).
3. A throwaway `SessionStart` hook that appends its payload to a file, set
   in that directory's local settings, shows `source` and `session_id` at
   each start.
4. Type `/compact`. Read: the session id after (the same two places), the
   process id before and after, the payload the hook wrote, and the last
   records of the transcript that held the old id.
5. The same for a background session: `claude --bg "<prompt>"` in the
   scratch directory, then `sminos compact <its short id>`.
6. Each form twice. The verdict is one of M2's three, written to
   Surprises & Discoveries with the version and what was read.

**M6: the vectors.** With a checkout of MAWS at hand and the commit of its
master that holds `apps/org-protocol/vectors/channel-rule.json`:

    sminos/tests/vectors/maws/sync.sh <MAWS checkout> <commit> channel-rule.json
    python3 -B sminos/tests/test_threads.py

The first prints the file's name, the commit and the copy's sha256, and
rewrites the copy and `channel-rule.PIN.json`; the second passes the four
`retired` cases on that copy and its line for the pin says pinned. Without
such a commit, neither file changes and the open item is recorded.

**M6: the version.**

    scripts/bump-version.sh --plugin sminos <the next minor version>
    scripts/bump-version.sh --since origin/main

The second lists the plugins whose shipped files changed since `origin/main` and exits 0
once sminos's version is above the base's.

**M6: the acceptance run.** T1's acceptance in the composite, item by item.
Each item is shown by the suite's cases named for it, run through the gates
above; the table says which, and what a person sees. Items 1 and 3 are also
run live, below.

| Item | Shown by | What is seen |
|---|---|---|
| 1 | M3's cases "its process gone" and "reopened"; the live pass | `sminos list --stopped` holds the closed session's row with the word `stopped`; after `claude --resume`, `sminos list` holds it live under the same alias and in-charge line, and the held message is in its context |
| 2 | M3's hold and verb cases | the sender's line says recorded, stopped, not woken, opened by its human; the stub's log holds no `claude --bg --resume` for it; `fill` of it exits non-zero and says its sessions are its human's to open; a spawned one's line says `woken` as today |
| 3 | M2's hand-off, refill, `clear`, fork and `/resume` cases; M3's `/clear` case; the live pass | `sminos list --stopped --json` gives the session a `/clear` left and the new one two `thread` values; a hand-off and a refill give one |
| 4 | M4's three-day cases, with `SMINOS_THREAD_END_AFTER` set short | after `sminos daemon tick` past the period: gone from `list` and `--stopped`, in `--all` as `retired`; `sminos say "@<alias> …"` exits 4 saying it ended |
| 5 | M4's self-retire cases | the session's own `sminos retire <itself>` prints the retirement; its row stays out of `list` after its process exits and through later hooks of that process |
| 6 | M5's cases against the stand-in | `sminos retire` exits non-zero naming the host; with the stand-in answering unknown, naming the account that could not be asked; with it exiting 6, the retire goes through |
| 7 | M1's stamp cases, M2's naming cases | every `joined`, `retired` and `state` of a thread in the log carries `thread`; `sminos say "@<former short> …"` is delivered to the current session, from a second registry that only holds the log |
| 8 | M3's question and lane cases | the project's host events hold an `answered` with `closed` for the open question; the endpoint stand-in receives `gone` before the frame of the other lane |
| 9 | M4's retired-machine case | on another registry, `list --all` shows the member `gone` and a tag naming it is refused saying its machine was retired |
| 10 | `test-older-cli.sh`; the vectors' `retired` cases | no `--resume` of the human-opened session in the stub's log after every older verb; `list --stopped` of this code still shows it |
| 11 | the `sminos` and `sminos-suites` gates | `GREEN` |

**M6: the live pass,** on a real engine, against a scratch store:

1. A scratch git repository in a scratch directory, a scratch
   `SMINOS_HOME` exported, and a terminal multiplexer's own server. The
   session is started so that the sminos it loads is the worktree's and
   not the installed copy (`claude --plugin-dir <worktree>/sminos`, with
   the installed sminos plugin disabled for that launch); inside it,
   `command -v sminos` names the worktree. If it names the installed copy,
   stop: the pass cannot be run here (M6's decision says what then).
2. Give the session a name and one prompt, then `/exit`. From the scratch
   repository, with the worktree's CLI: `sminos list --stopped` shows the
   session `stopped`. `sminos say "@<name> hello"` prints the held line,
   and `claude agents --json` shows no process for the session.
3. `claude --resume <its id>` in the multiplexer. `sminos list` shows it
   live under the same name; its transcript holds the message's frame.
4. Type `/clear`. `sminos list --stopped --json` shows two members: the old
   id `stopped` under the name, the new id live under its short id, with
   different `thread` values, and the old one's events hold no `retired`.
   Resume the old id in a second pane: it is live under the name.
5. Fork a session (the engine's own command for a copy). The copy's guide
   line carries the fork sentence, and `list --json` gives it a `thread`
   of its own.
6. In a session, `/resume` into another session of the directory. Both are
   members with their own `thread`, and no `retired` with reason
   `continued` was written for either.
7. What was seen, with the engine's version, goes to Surprises &
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
| `threads/<thread id>.json` | a human-opened thread that has not ended | `threads/.lock` |
| `threads/ended/<thread id>.json` | a human-opened thread that has ended; `end` moves it here and `restore` back | `threads/.lock` |

Each file is one JSON object, mode 0600, written by atomic replace.

**The record,** as the module returns it for either kind:

| Field | Type | Meaning |
|---|---|---|
| `thread` | string | the thread id: a spawned thread's seat id; a human-opened thread's first session id, or a minted UUID in M2's one case |
| `opened` | `"spawned"` or `"human"` | fixed when the record is made |
| `sessions` | list of strings | every session id the thread has had, oldest first; its last is `current` whenever there is one |
| `current` | string | the session that fills it now; `""` for a vacant spawned thread |
| `alias` | string | a spawned thread's seat alias; for a human-opened one, the alias its latest `joined` or `renamed` carried: a copy for readers without the log, whose own events decide the alias |
| `launch` | `{"cwd": string, "options": list of strings, "at": timestamp}` | the directory and the options of the engine process that last started `current`; `options` is option tokens in order, kept for `LAUNCH_OPTIONS` alone, and is absent when they could not be read |
| `channels` | list of strings | declared channel ids. T1 makes it `[]` and carries it through an end and a return; CH writes it |
| `stopped` | timestamp, or absent | since when the thread sweep has found no process holding `current` |
| `ended` | `{"at": timestamp, "reason": "retire" or "ended", "by": string, "pid": integer or null}`, or absent | the end: who retired it (`by`, `""` for the rule) and the process seen then |
| `created`, `updated` | timestamps | |

A human-opened file holds exactly these, and `"v": 1`. A seat record gains
the stored keys `opened`, `sessions`, `launch`, `channels`, `stopped` and
`ended`; `thread`, `current` and `alias` are read from what it already
holds, and its `status` is `retired` whenever `ended` is set. A seat record
without the keys reads as `opened: "spawned"`, `sessions: [current]`,
`launch: {"cwd": <its cwd>}`, `channels: []`. One whose `status` is
`retired` and that holds no `ended` (a seat retired before this code, or by
an older copy) reads as ended at its `updated`. Timestamps are
`sminos.now()`'s.

**The functions:**

    OPENED = ("spawned", "human")
    LAUNCH_OPTIONS = (...)     # the option names launch.options keeps; T2 extends it

    def all_threads(ended=False) -> list[dict]
        # this machine's threads of both stores; the ended human-opened ones only on request
    def get(thread_id) -> dict | None
    def thread_of(session) -> dict | None
        # the thread whose current session it is, else one that had it, ended ones included
    def stamp(session) -> str
        # the thread id an event of this session carries; "" for a session that is no thread
    def ensure(session, seat=None, project=None, events=None, lock_until=None) -> dict | None
        # the record of the thread the session fills, made when there is none (project and
        # events: the log an adopted member's first session id is read from); None for lane B
    def update(thread_id, fields, remove=(), guard=None, lock_until=None) -> bool
        # the one writer: a merge under the store's lock, applied only if guard(record) holds
    def advance(thread_id, old, new, lock_until=None) -> bool
        # current old -> new, new appended to sessions; False when current is not old
    def note_launch(thread_id, cwd, options=None) -> bool
    def end(thread_id, reason, by="", pid=None, at=None) -> bool
    def restore(thread_id) -> bool          # ended and stopped removed; a seat's status as fill leaves it
    def purge(thread_id) -> bool
    def has_ended(thread) -> bool
    def set_channels(thread_id, channels) -> bool          # CH's writer

`lock_until` is the hook's deadline: past it the write raises `LockBusy`
and nothing is written, as `meta_set` does. A child adds a field through
`update`, and names it here.

### §2. Events T1 adds to or changes

No kind is new. Every event below is written by the thread's machine,
under the session's own writer, in its project's log.

| Event | Shape | When |
|---|---|---|
| the stamp | `"thread": <thread id>` on every event `lifecycle` appends for a session that is a thread, whatever its kind (`joined`, `retired`, `renamed`, `state`, `titled`, `in-charge`, `status`) | from the session's first `joined` by this code |
| continuation | `retired`, `"reason": "continued"`, `"to": <new session>`, `"pid"` when a process was seen, stamped: today's event | the engine's hand-off (`hand_off`) |
| refill | `retired`, `"reason": "replaced"`, `"by"`, stamped; no `to` | `spawn_fresh` onto a seat, `seat add` over a held one |
| end by a retire | `retired`, `"reason": "retire"`, `"by": <who>`, `"pid"` when a process was seen, stamped | `retire`, `retire --purge`, `remove` |
| end by the rule | `retired`, `"reason": "ended"`, `"by": ""`, stamped | the sweep, after three days stopped; and a lane B session's process ending, when it has a thread record |
| return | `joined`, stamped with the thread id it had | a reopened or filled ended thread |
| whether it is woken | `state` with `"state": "stopped"` gains `"wake": "woken"` or `"wake": "held"` | `publish_state`, again when the value changes |
| a question closed | `answered`, `"src": <the question's>`, `"from": <the asker's alias>`, `"text": "closed: the session stopped before this was answered"`, `"closed": "stopped"` | the sweep, when it marks the stop |

A `moved` retirement and the `joined` that follows it in the other log are
today's, stamped. The reasons a reader meets on a `retired` are `ended`,
`moved`, `continued`, `retire` and `replaced`.

### §3. The reader rule (X7)

    def stamped(event) -> bool
        # its `thread` is a non-empty string
    def passed_by(event, latest_joined) -> bool
        # event is a `retired` with reason `ended` that is not stamped, and latest_joined,
        # the latest `joined` of the same session before it in its own writer's order, is stamped

A reader that decides membership from lifecycle events treats an event
that is passed by as absent. Every other `retired` takes effect, whoever
wrote it. The rule's cases are the `retired` list of
`sminos/tests/vectors/maws/channel-rule.json`, MAWS's file:

| Case | One session's own events, in order | A member after each |
|---|---|---|
| 1 | stamped `joined`; unstamped `retired` `ended` | yes; yes |
| 2 | case 1, then unstamped `retired` `moved` | yes; yes; no |
| 3 | case 1, then stamped `retired` `ended` | yes; yes; no |
| 4 | unstamped `joined`; unstamped `retired` `ended` | yes; no |

### §4. Naming a thread (X2)

On any machine, from the log as that machine may read it: the sessions of
a thread are those whose own events carry its id in `thread`; its current
session is the one among them whose membership is in effect, and when none
is (it has ended), the one whose `joined` is latest. A name that is the
thread id or the id of any of those sessions, in the forms a session id
takes today (`@short`, `@alias#short`, a full id), resolves to that
current session. Where a name is one member's current session or alias and
another's former one, the first is the match, as a former alias is ordered
today. A session whose events carry no stamp resolves as today, through
its `continued` chain. An event that addresses a message names the current
session's id.

### §5. Whether a thread is woken (X3, the first values)

    def wake_of(member) -> str | None
        # "woken" | "held" | "ended", or None when its machine published nothing

| Value | Thread | Read from |
|---|---|---|
| `woken` | spawned and stopped: an addressed message resumes it, as today | on its own machine, the record; elsewhere, `wake` on its latest `state` |
| `held` | human-opened and stopped: recorded and held until its human reopens it. T1 writes this value and T2 retires it for the reasons of its own list | the same |
| `ended` | ended by a retire or by the rule | its membership: a stamped `retired` with reason `retire` or `ended`, in effect |

A sender's CLI reads it when it sends and says it with the machine the
message waits on. With `None` (an older sminos on that machine) it says
what it says today.

### §6. The transition table

A thread is `live` (a process holds `current`), `stopped` (none does),
`ended` (its record says so) or, spawned only, `vacant`. The record's
write, under its store's lock, is each transition's linearization point;
the event is appended after it under the writer file's lock, with a guard
that reads the record again and writes nothing when the record no longer
says what the event would.

| # | What happens | Guard | The record | The event |
|---|---|---|---|---|
| 1 | a lane A session with no thread is seen for the first time (the hook, a reconciliation) | joinable as today | `ensure`: a human-opened record | `joined`, stamped |
| 2 | `spawn` makes a seat; `seat add` | as today | the seat record, with the thread keys | `joined`, stamped |
| 3 | a member or seat from before threads, or one whose latest `joined` an older copy wrote | this machine's, lane A, its latest `joined` unstamped | `ensure` | `joined` again, stamped |
| 4 | the engine hands a session to a background job | `continued_in`'s evidence, as today | `ensure_record(new, former=[old])`, then `advance` | `retired` `continued` on the old, `joined` or `renamed` on the new, one stamp |
| 5 | a refill | the seat's lock, as today | `advance` | `retired` `replaced` on the old, `joined` on the new, one stamp |
| 6 | no process holds `current` | two consecutive sweep passes, no resume lock held | `stopped` set | none for membership; `state` `stopped` with `wake`; `answered` for each open question |
| 7 | a process holds `current` again | — | `stopped` removed | none; what was held is delivered |
| 8 | `retire`, by another or by itself | M5's answer is none, or unknown with the terminal's flag | `end(reason="retire")` | `retired` `retire`, stamped; then the process is stopped where sminos can stop it |
| 9 | stopped for more than the period | the sweep's ending pass; M5's answer is none; still stopped with the same `current`, read again under the lock | `end(reason="ended")` | `retired` `ended`, stamped |
| 10 | an ended thread's session is held by a process that started after the end, or a spawned one is filled | the record's `ended`, its time and pid | `restore` (a fresh fill then goes on as row 5) | `joined`, stamped |
| 11 | a thread's session becomes lane B | `lane_of` | kept; when its process ends, `end(reason="ended")` | `gone` to the endpoint before the new frame; at its process's end `retired` `ended`, stamped. Reopened as lane A it returns by row 10 |
| 12 | `retire --purge`, `remove` | as row 8 | the id read, then `purge` | `retired` `retire`, stamped |
| 13 | a `join`, or a directory that resolves elsewhere | as today | unchanged | `retired` `moved` and `joined`, today's, stamped |
| 14 | a former session of a thread runs again | it is not the thread's `current` | `ensure`: a human-opened record of its own, its id minted when a thread has its session id | `joined`, stamped with the new id |
| 15 | an older copy wrote `retired` `ended`, unstamped, after a stamped `joined` | — | unchanged | none: passed by |
| 16 | an older copy wrote an unstamped `joined`, and then perhaps its `ended`, which then takes effect | the record has not ended | unchanged | `joined` again, stamped (row 3's guard) |
| 17 | an older copy retired a thread (`retired` `retire`, unstamped, honoured) | the record has not ended | `end(reason="retire")` from the event's `by`, `pid` and time | none |

A `/clear`, a fork and an in-session `/resume` are rows 1 and 6: the new
id is seen for the first time, and the session left has no process.

### §7. Which hosts a thread owns (X9, as consumed)

    class Owned(NamedTuple):
        answer: str        # "owned" | "none" | "unknown"
        vms: list          # devcloud's `vms` entries
        unknown: list      # devcloud's `unknown` entries, or one entry sminos makes for no answer
        asked: list        # the short ids asked about

    def owned_by(shorts) -> Owned          # the one function that runs devcloud
    def owned_vms(thread) -> Owned         # owned_by for the short ids of thread["sessions"]

`owned_by` runs `devcloud vm owned-by <short>...` as M5 finds and reads
it. The command's exact form and answer are X9's in the composite, read
again when M5 runs; nothing else in sminos runs devcloud or reads its
output. One reply answers for many threads: a thread owns the hosts of
`vms` whose `creator` is `@` and one of its short ids; a thread that owns
none is unknown when `unknown` is not empty, and none otherwise. An entry
sminos makes for no answer has devcloud's keys, with `account` and
`provider` null, `failed` `"query"` and the reason in `reason`.

### §8. Other names

- `S/sminos_records.py`: `lane_of(record) -> "A" | "B"`, the rule
  `member_frame` holds today, moved there; `record` may be `None`.
- `Member` (the view's row) gains `thread` (the thread id, `""` for none)
  and `opened` (`"spawned"`, `"human"` or `""`); `former` holds the
  continuation chain, then the thread's other sessions. `member_json`
  prints `thread`.
- `S/sminos_daemon.py`: `sweep_threads()`, called by the daemon's loop and
  by `daemon tick`: the stop pass at every call, the ending pass on its
  spacing.
- The hold's outcome from `deliver_next` and `push_member` is
  `"held:human"`.
- `sminos retire <member> --owner-unknown`.
- Environment, each read where its default is defined:
  `SMINOS_THREAD_END_AFTER` (seconds; default three days),
  `SMINOS_THREAD_END_EVERY` (seconds between ending passes; default 3600),
  `SMINOS_DEVCLOUD` (the devcloud CLI to run),
  `SMINOS_DEVCLOUD_TIMEOUT` (seconds one question may take; default 60).

### §9. Dependencies

- Python's standard library alone, at sminos's floor (3.10).
- devcloud 0.17.0 or later for `devcloud vm owned-by` (on `main` at this
  plan's pin). An older devcloud answers exit 2, which reads as unknown.
- The engine: the facts the code already rests on (`continued_in`'s
  record, the session record per process, `CLAUDE_PID` in a hook's
  environment). M2's check and M6's live pass record the version they ran
  on.
- MAWS, none that blocks: the vectors' file (M1 carries its content, M6
  pins it); its endpoint's own withdrawal at a lane change and its app's
  reader rule are MW's and are wanted by this child's release without
  holding it.

## Surprises & Discoveries

Found while the plan was written against the code; the executor adds its
own below.

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
- Observation: any JSON file at the root of `$SMINOS_HOME` reads as a seat.
  Evidence: `record_files` globs `*.json` there, and `load_seat` gives
  every missing field a default.
- Observation: the reader rule does not cover a session whose latest
  `joined` an older copy wrote, and a session started before an update
  writes such a `joined` from its own hooks for as long as it lives.
  Evidence: `refresh_joined` and `publish_owners` append a `joined` built
  by `joined_fields`; the vectors' fourth case.
- Observation: after a `/clear` the new session carries the name of the
  session it left, and a name another member holds is never taken.
  Evidence: `held_alias` and `shadowing`; the composite's own account of a
  `/clear`, under its Surprises.
- Observation: `sminos resume` returns a retired seat to its project
  today.
  Evidence: `resume_session`'s `launched` calls `join_seat`, whose guard is
  only that the latest membership is not `joined`.
- Observation: devcloud's launcher wants a Python 3.11 on `PATH`, where
  sminos runs on 3.10, and the driver runs a provider's own tool from the
  `PATH` it is given.
  Evidence: `devcloud/bin/devcloud`; `MIN_PYTHON` in `S/sminos.py`; the
  comment at the head of `devcloud/boot/devcloud`'s `vm` branch.
- Observation: every closed terminal session becomes an ended thread whose
  record D1 keeps, and a `/clear` makes one each time. Nothing bounds
  their number.
  Evidence: D1's lifecycle; the thread store's layout in Interfaces §1 is
  the answer for the daemon's cost, and `list --all` has none.

## Decision Log

- 2026-11-17 — **Verification.** This plan gets one
  `doperpowers:adversarial-reviewer` pass before it is executed, on whether
  each milestone can be built from this document and the code and whether
  the names in Interfaces are enough for T2 and CH. Execution runs through
  doperpowers:subagent-driven-execution, a review at each milestone's
  boundary before the next consumes it. The branch gets
  doperpowers:review-code at the high rung, as the composite's Decision Log
  sets for T1: it changes who stays a member, with privacy consequences.
- 2026-11-17 — **The pin moved twice while the plan was written,** from
  the composite's blob `8c29b665` at `main` `88e771ba` to `681c0075` at
  `279bb44a`. What moved with it: a `/clear` is no continuation (M2 was
  built around it and is now the hand-off, the refill and the naming, with
  a `/clear` pinned as another thread; the record lost the field that held
  the process, which only that case read); X9 is devcloud's command as
  built (M5); the reader rule's cases are a file of MAWS's (M1, M6).
- 2026-11-17 — **Residue decided in this plan,** each with its reason in
  the milestone named, for the composite's holder to fold under T1:
  - a person at a terminal may retire a thread whose ownership answer is
    unknown, with `--owner-unknown`, and never one that is owned (M5: the
    composite's lean);
  - the record of a spawned thread is its seat record and that of a
    human-opened one a file of the thread store, behind one module, an
    ended one moved aside (M1);
  - the thread id is the first session id but for a vacant seat's and a
    former session that runs again (M1, M2);
  - `seat add --session` is refused for a session that already is a
    human-opened thread (M1);
  - a refill's event keeps reason `replaced` and gets no `to`, which
    overturns the composite's advisory lean (M2, with its evidence);
  - `retirement_holds` goes, as the composite's advisory says: the
    record's `ended` holds the time and the process (M4);
  - the hold is an outcome of delivery that leaves the event owed, and
    `resume`, `fill --resume` and `send --wait` aimed at a held thread
    record their message and exit 4 (M3);
  - the three-day clock runs from the stop the sweep recorded, so nothing
    ends in the first three days after the update (M4);
  - an ended thread reads `retired` in lists and is shown by `--all` from
    the log (M4);
  - a devcloud CLI that cannot be found or run reads as unknown, and only
    exit 6 as none; the daemon's service carries the two variables that
    move devcloud's seed and profile (M5);
  - what older code leaves disagreeing between the log and a record is
    brought back together in three cases and no more (Interfaces §6, rows
    15 to 17).

## Outcomes & Retrospective

Pending — written at finish.
