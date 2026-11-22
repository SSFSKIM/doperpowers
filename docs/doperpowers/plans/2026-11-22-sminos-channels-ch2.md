# sminos channels, CH2 — speaking in a channel, and what sessions are taught: execution (2026-11-22)

> **Composite:** `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`,
> child **CH2** (Speaking in a channel, and what sessions are taught).
> **Parent pin:** the composite as revised by the owner's ruling of
> 2026-11-22 on who may write into a channel, commit `59782bb8`, that
> file's blob `8173f99212ffbb255569eaec2c23b141aab8b073`. The branch this
> plan was written on, `sminos-channels-ch2`, stands at `1a3c1ac5` (`main`
> with CH1 merged, `e0aa6d39`, sminos 1.54.0, and the fold of CH1's landing
> as corrected against the code, `b8145982`), one revision of the composite
> behind that pin; the holder brings it up to `main` before M1. The design
> the composite is itself a child of,
> `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`
> ("the parent" below), is read as that same commit holds it, blob
> `eb2f3aef4134089fb625e1e2fe2b76da5f52449d`. The child's section in the
> composite is its spec; C1, C2 and C5 there are its design, binding where
> marked; Y1, Y2 and Y3 its contracts with CH1, which it consumes as built.
> This document carries the constraints and the milestones and nothing of
> the design. Read before M1: the composite whole, above all its Decision
> Log's last three entries ("CH1 landed", with "What CH2 inherits"; "The
> fold of CH1's landing, read against the code"; and "The owner's ruling: a
> thread that is no member may write into a channel"); the parent's Purpose (the
> rulings under "What it must not become"), Terms, D3 (The timeline, The
> lead, Listing), D5, D6, D7, X4, X6, X8 and acceptance lines 2 and 8; CH1's
> plan `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md`, its
> Interfaces §1 to §9 and its Outcomes; T1's plan
> `docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`, its Interfaces §4
> (a thread's row and its names), §5 (what is held) and §6 (transitions);
> T2's plan `docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md`, its
> constraints (the lock order, the wake lock), §4 (delivery and the wake)
> and §5 (what a sender reads); EN.G1's plan
> `docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md`, its
> Interfaces §1 and §2 (a machine's notice); `docs/doperpowers/TECH-DEBT.md`,
> sections "sminos channels", "sminos threads", the first row of "sminos
> environments" and the third of "the backtick guard"; and
> `sminos/skills/sminos/scripts/CLAUDE.md`, its paragraphs on threads, the
> wake, a machine's notice and channels.

After this child a channel is a place to talk. A member runs `sminos say
--in desk-integration "@worker the schema changed"`: the message is one
event in the channel's log, the thread named receives it framed as coming
from that channel, a stopped one is woken for it where its machine wakes
it, and the reply it sends with the line its frame gives lands in the
channel's log and reaches the sender. `@desk-integration/worker` does the
same without `--in`, `@all` in a channel reaches its live members, and an
untagged post there is a record nobody is prompted for. A bare `@worker`
reaches a thread that shares only a channel with the sender, in that
thread's own project as a message to another project does today. A thread
that is not in the channel may say into it too: its message lies in the
channel's log as a message from another project lies in a project's,
reaches the members it names, is framed as from a thread outside the
channel, and is answered to its sender directly, in the sender's own
project. Membership decides who hears a channel: what its log owes a
thread follows the thread's membership, so a message that reached the
machine before the thread entered, or while it was out, is never pushed
to it, and nothing there is ever pushed to a thread that is no member. The owner, at a terminal, names a lead with
`sminos channel lead`, and an untagged message the owner then types into
the channel is addressed to that thread. `sminos chat desk-integration`
reads the channel's conversation. The session-start guide, the skill, the
spawn preamble and the manager's skill speak of threads and channels. A
session that is in no channel sends and prints what it did before. How to
see it working is CH2's acceptance in the composite (eleven items, numbered
B1 to B11 here in the order its section lists them), proved as Concrete
Steps maps it.

## Progress

- [x] (2026-11-22) CH1 landed (`e0aa6d39`, sminos 1.54.0); the composite and the parent revised for it (`81ea8848`) and corrected from a read against the code (`b8145982`).
- [x] (2026-11-22) This plan written against the code at `1a3c1ac5` (sminos 1.54.0) and the composite as the owner's ruling of that day left it (`59782bb8`), with MAWS's master read at `fcc992514`.
- [ ] The plan's review for buildability (the holder's), and its fold.
- [ ] M1 — Names through a channel.
- [ ] M2 — What a channel owes a thread: delivery on one machine.
- [ ] M3 — Saying into a channel: the doors, the reply, the read.
- [ ] M4 — The scene on a real engine, and the roster's cost.
- [ ] M5 — Across machines: the endpoint's word on a message.
- [ ] M6 — The lead, and whose words a post is.
- [ ] M7 — What reads a session's exchanges reads a channel's.
- [ ] The review of M1 to M7 as one range (the holder's), and its fixes.
- [ ] M8 — What sessions are taught, and its evaluation.
- [ ] M9 — Older copies, what is written beside the code, the version, and the acceptance.
- [ ] The merge (the holder's).

## Words this document adds

The parent's Terms define thread, project, log, writer, member, channel,
pool, deliver, wake, the daemon, the hub, the endpoint, reach and lane B.
CH1's plan defines the set, where a membership began, the statement, a
request, the thread's own project, the roster, opens without `follow`, the
endpoint's word, a cut, the stand-in, `S/` and `T/`. T2's plan defines the
wake lock, the delivery lock and held. Added here:

- **A message** is an event of kind `say` (a session's) or `human` (a
  person's at a terminal, or a machine's notice): `CHAT_KINDS` in
  `S/sminos.py`. It is **addressed** when its `to` is a list naming
  sessions, **for the live alone** when it also carries `wake` (an `@all`),
  and **untagged** when its `to` is `"*"`.
- **The boundary** of a thread in a channel is where its membership began:
  `began_of(thread, channel)`, each writer's latest seq in the channel's
  log as this machine held it then.
- **The lineage** of a thread's current session is the sessions that one
  continues, newest first, as the thread's own project's log states them
  (`Member.former`): a session the engine handed off, and the one before
  it. The occupants a refill displaced are the thread's other sessions
  (`Member.thread_sessions`) and are not in it.
- **The delivery record** of a session in a log is
  `projects/<log id>/delivered/<session>.json`: for each writer, the seq up
  to which what the log owed that session is **settled** (pushed, or
  dropped for good), with its marks of what is held. Its lock,
  `delivered/<session>.lock`, is the **delivery lock**.
- **What a channel owes a thread** is the addressed events of the channel's
  log that name the thread's current session or one of its lineage, past
  the boundary and not yet settled (Interfaces §3).
- **The delivery operation** is the five functions of `S/sminos.py` every
  push goes through: `deliver_next` (one member's owed events, pushed and
  settled), `deliver_verdict` and `deliver_reach` (one event, on the
  endpoint's word), and the two passes that say what to ask the endpoint
  about, `words_due` and `reach_due`.
- **The doors** are the places a `say` that names a channel is taken or
  refused: `cmd_say`, `resolve_tags`, `_resolve_tag`,
  `shortened_channel_qualifier`, and for a verb's target `find_target`.
- **The consumer thread** is the main thread of the uplink process
  (`serve_link` in `S/sminos_uplink.py`): it dispatches the endpoint's
  frames, delivers what they imported and runs the uplink's tick, so a
  wait there stops all three.
- **The checker** is `T/channel_wire.py`: what may be on the wire and on
  disk under a channel's id.
- **The lead** of a channel is the thread its `channel-lead` event in
  effect names (Interfaces §5).
- **A pass**, in a suite of several machines, is one relay between the
  stand-ins and one `sminos daemon tick` on each machine.
- **`M/`** is `sminos/skills/manager/scripts/`.

## Constraints that bind every milestone

- **The designs have one writer,** the session that holds the composite. This
  document's controller records decisions and discoveries here and sends that
  session whatever touches the child's purpose, its acceptance, a contract or
  a binding decision; it edits neither design. A statement of the composite
  that the code makes unbuildable stops that part and goes to the holder with
  the evidence; the rest is built.
- **What binds, by id.** The composite's C1 (two readings of "its members"),
  C2 (the kinds and their fields; `channel-lead` is this child's) and C5
  (where a message lands). The parent's D3 (The timeline, The lead), D5, D6
  and D7, and the rulings under "What it must not become". Contracts X4 (the
  lead's kind), X6 (this child owns the rewrite of what sessions are taught),
  X8 (the reader of a machine's notice), and Y1, Y2 and Y3, which this child
  consumes: CH1's names (its plan's Interfaces §1 to §9) are read and not
  changed, and a signature this child must widen gains an argument whose
  absence is today's behaviour.
- **A channel does not become a project.** `view_of` of a channel answers no
  member, `known_projects` holds no channel, and `find_project` and
  `project_tiers` keep refusing one, in CH1's words. A path that speaks or
  addresses through a channel is given the roster explicitly, before it
  reaches a project lookup, and keeps two things apart: the log an event is
  in, and the project of the thread it found. Reason: a verb that finds a
  thread through a log writes to that log (`find_target` returns the project
  it searched), and every publisher reads "the members of this log" from
  `view_of` (C1).
- **Nothing is published under a channel id** (C1). No `member` frame names a
  channel as `project`; no session presence, machine presence, checkout,
  `pending` set, host frame or delivery outcome is sent under one; this code
  writes no `joined`, `state`, `renamed`, `titled`, `in-charge`, `status`,
  `unlisted`, `channels`, `message`, `question` or `answered` into a
  channel's log. What this child adds to a channel's log is `say`, `human`
  and `channel-lead`; what it adds to the wire under a channel's id is those
  events in an upload, a `reach?` about a `say` or a `human`, and a `words?`
  about a `human`. Nothing else, and the checker (§8) is the test: every
  suite of this child that runs an uplink ends by calling it.
- **A fact about a thread is written to the thread's own project,** however
  the thread was named: its lifecycle events, its in-charge line, its
  status, its statements, its words to its human. A message is the one thing
  a thread writes into a channel's log.
- **Any thread may write a message into a channel's log; membership decides
  who hears it** (C5, the owner's ruling of 2026-11-22). A member's message
  carries no `from_project` and leaves no copy (`record_copy`), so its
  frame's reply line names the channel and the reply lands there. A
  message from a thread that is no member follows today's rule for a
  message to another project, the channel's log in the place of the
  target's: `from_project` names the sender's own project, a copy lies in
  that project's log, and its frame's reply line names the sender, so the
  reply goes to it in its own project. A machine's human writer writes as a
  member does. Which of the two a message is, is decided once, where it is
  written, by the sender's own record; every reader after that tells them
  apart by the event's `from_project` and by nothing else, and no reader
  looks a sender up in a roster. A bare `@alias` never puts a message into
  a channel's log.
- **Nothing a channel's log holds is owed to a thread that is no member.**
  What a channel owes is read from this machine's thread records, so a
  thread whose record does not hold the channel is delivered nothing from
  it, whatever names it there.
- **Delivery in a channel is the thread's own machine's, from its thread
  records.** No tick, no pass and nothing the uplink runs reads a roster or
  a project's view to decide what a channel owes: it reads this machine's
  records (`sminos_threads.set_holders`, the record's `channels` and `began`)
  and the channel's log. The roster is read by commands: addressing (M1,
  M3), the listing and `channel show`. Reason: a roster reads every
  project's view, and the idle budget below has no room for it.
- **One delivery operation.** A channel's messages are pushed, held, woken
  for and settled by the five functions every project's are (Words), with
  one added argument (§3) whose absence is today's behaviour, call for call.
  No second implementation of the push, the hold, the wake or the
  settlement is written for channels. Reason: T1's branch review found 82
  defects in and around that operation, and a copy of it would start again
  from none of those fixes.
- **What a channel owes is decided under the delivery lock, on the record as
  it is then.** Which thread a session fills, whether that thread is in the
  channel and where its membership began are read again from their files,
  never from a row, a roster or an earlier read, last before a push, a wake
  or a question to the endpoint (§3, the last check). What was read before
  the lock chooses only whether to try. A verdict the endpoint gives late is
  carried out against the record as it is when it arrives, never against a
  member saved when it was asked.
- **This child writes no position, and `finish` gains no step.** A record's
  `channels`, `began` and `answered` keep their three writers
  (`set_channels`; a return, `_began_anew`; an absorption's `_merge_absorbed`),
  and delivery is checked against all three. What delivery writes is a
  session's delivery record under a channel's log and nothing else. Reason:
  any copy from 1.51.0 on finishes an open entry it finds and skips a step
  it does not know, so nothing delivery needs may live in a journal step.
- **Lock order,** outermost first, as T2 fixed it and unchanged: the
  delivery lock; the seat's lifecycle lock; the wake lock; a store lock; a
  log's lock. `set_channels` takes the thread's wake lock, so a wake's hold,
  kept through its push, is what keeps a removal from landing between the
  last check and the frame's handoff. No lock is added.
- **Nothing this child adds to the consumer thread waits on a lock without a
  bound.** This is a requirement on CH2, not a property it inherits: CH1's
  request pass tries the locks of a request's carrying out, and two of CH1's
  paths there still wait without a bound (`member_under` at a channel's
  upload, and the pass's finish of its own entry, which can take a
  registration's lock through `project_path`; rows in TECH-DEBT). What CH2
  runs on that thread tries each lock or takes it with a deadline, reads a
  member's frame as the plane last read it (`Link.member_on_lane`, never a
  view), and builds its paths under a channel's home without a call that can
  write the registration. What it cannot do at once stays owed for its next
  pass. M5 proves it with the locks held by another process.
- **A machine that holds no channel pays nothing per tick,** in the daemon
  and in the uplink (the holder's ruling in CH1). Every per-tick duty this
  child adds is a loop over the channel set (`known_kinds`' channels,
  `Link.channels`), and inside it over this machine's threads that hold a
  set. The `sminos-idle` gate is the check: its limit is 33,570 Python calls
  a second, the last commit of CH1 that changed code read 32,230, and runs
  differ by about 2.6%, so one run's margin is not capacity. Each milestone
  records its figure in Progress, and a change that cannot keep a machine
  with no channel at `main`'s figure goes to the composite's holder before it
  lands. The gate's stand-in lists no channel, so what a machine that does
  hold channels pays is measured apart (M4).
- **Byte for byte for a session in no channel** (parent line 8). `say`,
  `list`, `chat`, `spawn`, `join`, `retire`, `send`, every event, every
  frame of the uplink and every line printed are what they were on a machine
  that knows no channel and for a thread that is in none. A key, a line or a
  lookup this child adds appears only where a channel does; an error for a
  store with no channel comes in the order it came before.
- **In a channel's log, "this machine's own" is what the machine appended**
  (`sminos_channels.appended_here`: a queued append, or an append receipt),
  for a message as CH1 made it for a request, and never a writer's machine
  name. It decides three things there: whether the read-only policy refuses
  an event, whether a push needs the endpoint's word (the same-owner
  shortcut), and whether a person's words are asked about. A `say` appended
  to a channel's log gets a receipt for it, as a `human` and a request do. A
  project's log keeps `sminos_policy.outside_origin` as on `main` (the
  TECH-DEBT row stays, narrowed to projects). Reason: the row's cost begins
  when messages are written into channels, and the channel path is new, so
  closing it there costs a project nothing.
- **Older copies** (D7). `channel-lead` names no one in `to` and is skipped
  by every installed copy. A message in a channel's log is inert to a copy
  from before CH: it delivers only to the members its view of that log
  holds, and a channel's log holds no `joined`. A machine on 1.54.0 stores a
  message and delivers nothing of it (`HubLog.deliver`, `channel_pass`): it
  is owed, and pushed when that machine updates, by the boundary 1.54.0
  itself kept (C5, "Between releases"). Nothing here defends against an
  older CLI run by hand beyond what M9 asserts.
- **The wire is another team's.** MAWS's conversation fixture is one file,
  copied byte for byte and never amended; this child adds no frame type and
  no field. At CH1's copy the fixture shows no message under a channel's
  id. MAWS's architect has agreed to add two cases (an upload under a
  channel's id by a session whose member frame is under its own project,
  and a `reach?` about a `say` there from a writer that is no member); M5
  copies the fixture when they land and replays them. For what no case
  shows (§4), the stand-in is what holds this child to MAWS's endpoint,
  taught from MAWS's source as read at its master `fcc992514`. A line that
  will not replay, or an answer of MAWS's architect that differs from §4,
  goes to the holder before anything is built on it.
- **What sessions are taught is behaviour.** The guide, the skill, the spawn
  preamble and the manager's skill change in M8 and nowhere else, through
  doperpowers:writing-skills with the evaluation Concrete Steps gives; a
  test that pins one of their lines verbatim is changed in that milestone.
  Before M8 only two taught things move, because they would otherwise be
  false: the sentences of the refusals M1 and M3 replace, and `sminos help`.
- **A check on a real engine runs only under a scratch home:** `HOME`,
  `CLAUDE_CONFIG_DIR`, `SMINOS_HOME` and `MAWS_USER_DATA` all under one
  scratch tree, never the person's real configuration (T1's first live pass
  joined real sessions and was discarded).
- **The repository is public.** No hostname, address, account, project id of
  the fleet, local path or secret's name enters a test, a comment, a commit
  message or this document. MAWS is named by its commits alone.
- **`S/sminos.py` is one file of twenty thousand lines.** What reads and
  decides for a channel (resolving through a roster, what a channel owes,
  the channel's delivery pass, the lead, the channel-aware read) goes in
  `S/sminos_channels.py`; `S/sminos.py` gets the changed seams.
- **What sits beside the code is written with it.** Each milestone adds what
  it built to `sminos/skills/sminos/scripts/CLAUDE.md` (the rules of this
  section a later change could break, the tests' names), since the next
  milestone's executor reads that file before it reads this one's code; M9
  reads the whole against the tree.
- **Tests are hermetic,** as in CH1: the test engine (`T/wake_engine.py`),
  the stand-in, temporary homes, invented names. **And they vary what a
  single case hides:** both kinds of thread (spawned and human-opened) as
  recipient, live and stopped, woken and held; the sender a member, a
  session that is no member, a person at a terminal and a machine's
  notice; one, two and five messages
  of one and of two writers; a message before and after an add, a removal, a
  removal and an add, an end and a return, a hand-off, an absorption, a
  refill, a `join` and a change of reach; the three deliverers (the sender's
  own call, the daemon's pass, the uplink on a word) and the order of their
  work; and a cut after each write. A guarantee tested with one message to
  one live human-opened thread is not tested.
- **One change, one version.** No release is cut between milestones. The
  child merges as one pull request that leaves the repository releasable
  beside a machine on 1.54.0 (D7), with sminos's version bumped in it
  (`scripts/bump-version.sh --plugin sminos 1.55.0`, or the next minor if
  `main` has moved past it). No other plugin's files change. `origin/main`
  is merged before M1 and at milestone boundaries, never inside one.
- **Every milestone ends green.** The gates of Concrete Steps pass at each
  milestone's last commit, run through `ci-gate` on the pushed commit and
  never as the gates' commands on this machine (one focused test file while
  iterating is fine). A test that pinned behaviour a milestone changes is
  changed in that milestone, to pin the new behaviour, and never deleted for
  failing.
- **Accepted, and not built** (the composite's rulings and the code's limits;
  no milestone tries to close them): where a membership began is this
  machine's positions then, not the sender's time of sending, so a message
  written elsewhere during an earlier membership and imported after a later
  add is owed (the holder, 2026-11-22); between a thread's `joined` and the
  statement that follows it other machines read it as in no channel, so a
  reply to it through the channel goes to it directly for that moment; a
  push to a live session has the base's own window, a hand-off or a removal
  between the last check and the frame's handoff (the TECH-DEBT row "The live
  push's own window"), where a wake has none; in a project an addressed
  event that names a session its thread has left is still not pushed (the
  owner's ruling of 2026-11-21: this child carries a channel's debt across
  a hand-off and leaves the project's row as it is, §3); a sender on a
  machine that reads an older statement addresses a thread that has left,
  and that message is delivered to no one; a frame's header names a log by
  its name, so a channel and a project of one name read alike there and the
  reply line's id tells them apart; and a machine on 1.54.0 delivers nothing
  from a channel until it updates.

## Plan of Work

Readers come before writers, one machine before two, code before what
sessions are taught. M1 gives addressing the roster where nothing is
written into a channel yet: a verb's target and a bare alias. M2 builds
what a channel owes a thread and its delivery on one machine, with the
doors still shut, so that when a door opens everything behind it is
already there and reviewed. M3 opens the doors: `say` into a channel, the
reply that lands there, and `chat` over a channel. M4 runs the scene on a
real engine, in the middle of the build where the engine is in the path,
and measures what a roster costs. M5 carries a message between machines on
the endpoint's word. M6 adds the lead. M7 teaches the two readers of a
session's exchanges to read a channel's. Between M7 and M8 the range is
reviewed whole by the composite's holder. M8 rewrites what sessions are
taught and evaluates it. M9 runs older copies against the result, reads
what sits beside the code, bumps the version and runs the acceptance.

Nine milestones. The composite's cut kept the taught surface in this child
unless its plan showed it tripping the gate. It stays (M8): the doors and
the texts must ship in one release, since from M3 on `sminos help` and
what `say` prints already say what the guide would otherwise contradict,
and X6 forbids shipping a taught surface that is false. It is the last
milestone that changes behaviour and consumes nothing but the CLI as M1 to
M7 leave it, so the holder can still cut it into a child of its own at the
frontier without touching M1 to M7.

**Where milestones meet.** CH1's lesson is that review of each milestone
missed what lives where one milestone's judgment meets another's wire. So
each milestone below names, under **Seams**, the earlier milestone it
meets, the one place the two are joined, and the test that crosses the
join; a seam is built once, by the later milestone, and its test fails
before that milestone and passes after. Two reviews are scheduled over
more than one milestone's diff:

- **M5's review reads M2 to M5 as one range** (the controller's, at the
  rung the Decision Log gives): what a channel owes, the doors and the wire
  are one path from a sender's command to a recipient's inbox on another
  machine, and no single diff holds it.
- **The frontier review.** When M7's review is clean the controller pushes
  the branch and returns to the composite's holder with the word
  `FRONTIER`, the range (`git merge-base origin/main HEAD` to `HEAD`) and
  nothing else to decide. The holder reviews that range through
  doperpowers:review-code at the panel rung, with lenses given, not
  derived: lock order, and what is read outside the lock it is acted on
  under (the delivery lock, the wake lock, a record's lock, the last
  check); an older copy on the same store, and a machine on 1.54.0 across
  the wire; what leaves the machine under a channel's id (every frame and
  every event, `from_project`, a copy, an outcome, and whether a reply or a
  lead names a private thread's session to a reader that may not read it);
  every door that relied on "nothing is said in a channel" (each refusal
  lifted, and each reader of a channel's log in §6's table); and the
  milestones' interactions (a message against an add, a removal, a removal
  and an add, an end, a return, a hand-off, an absorption, a refill, a
  `join`, a change of reach, a wake, the thread sweep and a late word; the
  lead against each). Its confirmed findings are fixed on the branch by
  the holder's fix wave, the range is read whole a second time if the
  first reading confirms more than ten, and there are three rounds at
  most. The controller is then continued for M8. It sits after M7 because
  every writer, reader and sender this child adds exists by then; M8
  changes texts and M9 adds none.

### M1 — Names through a channel

**At its end:** a verb's target may be named through a channel: `sminos
status desk-integration/worker "reviewing"`, `charge`, `retire` and `who
--thread` find the thread in the channel's roster and write where they
write today, in the thread's own project. A member's bare `@worker` reaches
a thread that shares only a channel with it, as a message to another
project does today (in that thread's project log, with `from_project` and
the sender's copy); two threads that answer are refused, each named
`alias#short`. A tag qualified by a channel and `--in <channel>` are still
refused in CH1's sentence: nothing is written into a channel.

**Touches:** `S/sminos_channels.py` (the resolver of §1), `S/sminos.py`
(`find_target`, `_resolve_tag`'s branch for a bare name, `no_member`),
`T/test_channels_names.py` (new), `T/test-channels.sh` (its section "a
verb's fact goes to the thread's own project", which pins the refusal
today), `T/test_channels.py` and `T/test_channels_requests.py` (their
cases that pin `find_target`'s refusal), `T/run-sminos-tests.sh`
(`run_channels`).

**Interfaces:** exposes §1 (`reach_in`, `shared_rows`). Consumes Y1
(`roster`, `channels_of`, `find_channel`, `names_channel`,
`ambiguous_name`).

**Seams:** none earlier. It leaves one for M3: tags qualified by a channel
reach members through `reach_in`, the same function `find_target` calls
here, so a name resolves alike in a verb and in a tag.

**Decisions:**

- `find_target` branches where it refuses today: after the exact seat group
  of a name no project has, which resolves as before (CH1's C4 and D4), and
  before `project_tiers`, which refuses a channel on its own. It answers
  what it answers for that thread found in its own project: `("seat", seat,
  session)` for a seat of this machine, else `("member", <the row's own
  project>, member)`, so no verb learns of the channel and each writes
  where it wrote. The row's own project is reconciled as `find_target`
  reconciles the projects it searches.
- The bare alias is widened for tags only. In `_resolve_tag`'s branch for a
  sender in a project and a name with no qualifier and no short, the
  candidates are that project's members of the alias, as today, and the
  rows of that alias in the rosters of the channels the sender's record
  holds (`channels_of`), each thread once. One: it, with its own project as
  the destination. Several: `one_member`'s refusal, each as `alias#short`.
  None: today's path from there on, unchanged. A sender whose record holds
  no channel reads no roster, and its lookups and errors are today's. A
  verb's bare name is not widened (the Decision Log's open point 3).
- The rule for a name in id form through a channel (§1) is built and tested
  here, where `find_target` uses it; M3 gives it to tags, for the reply.
  `reach_in` answers `out` for a thread that has had the id and is not in
  the channel now, and refuses nothing for it itself: here `find_target`
  refuses it in §2's sentence for a verb; a tag sends to that thread
  directly, which is M3's.
- The engine's collision name (E15, the composite's delegated unknown): a
  row is listed and matched by the alias its own project's view gives it.
  `held_alias` already never lets a name the engine made up, `collision`
  among them, replace an alias held, and two rows of one alias are told
  apart as `alias#short` (`member_label`). Nothing is added for a channel.

**Does not touch:** `cmd_say`, `resolve_tags`' check of a channel qualifier,
`channel_say_refusal`, `find_project`, `project_tiers`, delivery, the
uplink, the daemon, the guide.

**Proves:** B3. Its tests pin: `<channel>/<alias>` with the channel named by
its id, its `name#short` and its name, for a seat of this machine, a
thread its human opened here and a thread of another machine; `retire` and
`charge` through a channel leave the channel's log byte for byte as it was;
a name a project and a channel both answer is refused by `ambiguous_name`
at a verb and at a bare tag's refusal; the bare alias with one answer in
the project, one in a shared channel, one in each (refused), and one in a
channel the sender is not in (today's refusal, listing it elsewhere); a
sender in no channel makes no call of `rosters` (counted); and §1's four
cases of a name in id form.

### M2 — What a channel owes a thread: delivery on one machine

**At its end:** a message that lies in a channel's log, addressed to a
thread of this machine that is in the channel, is pushed to its live
session once by the next `sminos daemon tick`, wakes a stopped thread that
may be woken, and is held, owed, for one that may not; it is framed as
coming from the channel, and its reply line names the channel's id, or,
for a message that carries `from_project` (a sender outside the channel),
the frame says so and the line names the sender in its own project. What
the channel owes follows the membership through every row of §3's table,
and a thread whose record does not hold the channel is owed nothing.
`sminos daemon owed` counts it. The doors are still shut: the suites put
the message into the log themselves.

**Touches:** `S/sminos_channels.py` (`owing`, `still_owed`, `deliver`,
`owed_here`), `S/sminos.py` (`_owed`, `deliver_next`, `deliver_verdict`,
`deliver_reach`, `words_due`, `reach_due`, `holder_push`, `wake_member`,
`frame_of`, `_conclude`, `_write_receipts`, `ReachGate.needs`),
`S/sminos_daemon.py`
(`channel_pass`, `owed_in`), `S/sminos_outcomes.py` (`record`),
`T/test_channels_delivery.py` (new), `T/channel_wire.py` and its tests in
`T/test_channels_wire.py` (§8).

**Interfaces:** exposes §3. Consumes Y3 (`began_of`, the record's
`channels`), `sminos_threads.set_holders`, `appended_here`, T2's wake
(`holder_push`, `wake_member`).

**Seams:**

- *Delivery and CH1's membership* (Y3). Delivery meets the record's three
  writers at one place, `owing`, which reads the record under the delivery
  lock and settles the session's delivery record up to the boundary before
  anything is chosen; the tests that cross it are §3's rows D1 to D12, each
  staged through the transition itself (`change`, a request carried out,
  an end and a return, `hand_off`, a refill, an absorption) and never by
  editing a record.
- *Delivery and a writer that is no member.* An event in a channel's log
  may come from a thread with no membership statement there (C5). Delivery
  never looks its sender up: it reads the event's `to` for whom it is
  owed, and its `from_project` for how it is framed and where its reply
  goes. Crossed by: one message staged with `from_project` and one
  without, by the same writer to the same member: both are pushed; the
  first's frame carries §3's clause and a reply line naming
  `@<that project's id>/<short>`, the second's neither clause and a line
  naming `@<the channel's id>/<short>`; and a message in the channel that
  names a session whose thread is in no channel is pushed to no one.

**Decisions:**

- The channel pass (`sminos_daemon.channel_pass`) gains one step, last:
  after the channel's view (its reconciliation) and `carry_due`, the
  channel's delivery (`sminos_channels.deliver`). A request honoured in a
  tick has then set the boundary before that tick's delivery reads it.
- The pass costs a tick what the project's costs: a thread with nothing
  addressed to it or its lineage is passed by on the log's own index
  (`addressees`), with no lock and no record read, and a thread whose
  whole backlog is held is passed by on the memory of a full pass, as
  `deliver_owed` does with `_HELD_PASSES` (one memory for both, keyed by
  the log and the session).
- The last check sits in `holder_push`, which every deliverer pushes
  through, and again in `wake_member` once the wake's hold is taken and
  before a process is started. An event that fails it settles `recorded`:
  nothing pushed, nothing woken, nothing asked.
- What a frame says of a sender outside the channel is one clause after the
  sender's alias, where `sender_labels` puts its own (§3), composed in
  `frame_of` for an event of a channel's log that carries `from_project`.
  The reply line needs no change: `sminos_control._routes` already names
  an event's `from_project` where it carries one.
- No outcome of a channel's delivery is kept for the uplink
  (`sminos_outcomes.record` keeps none for a channel, and `_conclude` asks
  for none): §4 says why.
- `HubLog.deliver` stays as it is, nothing for a channel. An import already
  nudges the daemon, whose channel pass delivers; M5 adds what needs the
  endpoint's word. Reason: `HubLog.deliver` runs on the consumer thread,
  and the delivery lock it would take there has no bound today.
- The suites stage a message with `log_append` under a member's writer, and
  one from another machine as an imported event (a writer file under
  another machine's name carrying `verified`), as `T/test_words.py` and
  `T/test_wake_delivery.py` stage theirs; live and stopped recipients are
  T2's fixtures (`T/test_wake.py`'s `Engine`, `T/inbox_standin.py`).

**Does not touch:** the doors (they still refuse), `Link.ask_words` (on a
machine whose endpoint decides reach, an event that needs its word is left
owed and listed `gated`, as a project's is, and M5 asks), `deliver_owed`
(the project's pass), `settle_ended`, `sminos_threads.finish`,
`carry_hand_off`, `HubLog.deliver`, `Plane.refresh`.

**Proves:** B4 on one machine, row by row of §3; B7's first half for
delivery (no host kind is written by a push or a wake from a channel).
Beyond the table its tests pin: a message at the boundary (seq equal to
the kept position) is not owed and the next one is; two messages of one
writer are pushed in order and a failure stops that writer; an event for
the live alone settles `recorded` for a stopped member; a held message is
pushed once when the thread is reopened and once when it is woken; the
last check, with the membership changed after the pass chose the event
(removed; removed and added; the session another thread's), pushes and
wakes nothing; both sides of row D5 (a message this machine held before
the second add is never pushed; one it imports after it, though stamped
before the removal, is pushed); a message under this machine's own name
with no receipt is an outside event (refused `refused-read-only` on a
read-only machine, never the same-owner shortcut); a thread in the channel
with a private record; nothing is delivered for a thread whose record does not hold the
channel, whatever a roster says; and no file appears under any project for
a channel's delivery.

### M3 — Saying into a channel: the doors, the reply, the read

**At its end:** `sminos say --in desk-integration "@worker …"` and `sminos
say "@desk-integration/worker …"` by a member write one event into the
channel's log and deliver it as M2 does, at once for a recipient on the
same machine whose push needs no word of the endpoint; the recipient's
reply by its frame's reply line lands in the channel's log and reaches the
sender; `@all` reaches the channel's live members and an untagged post
prompts no one. A thread that is not in the channel says into it in the
same forms: its message lies in the channel's log with its project in
`from_project` and a copy in its own project's log, reaches the members it
names, and it reads one line saying that it is no member, that replies
come to it directly, and how to add itself; the reply by that frame's
line lands in the sender's project. A reply to a member that has since
left goes to that thread directly, and the replier is told. A person at a
terminal, and a machine's notice, write under the machine's human writer;
`sminos chat desk-integration` reads the conversation, and `sminos list
desk-integration` prints the channel as `--channel` does. On one machine.

**Touches:** `S/sminos.py` (`cmd_say`, `resolve_tags`, `_resolve_tag`,
`deliver_say`, `say_scoped`'s refusal, `cmd_chat`, `cmd_list`, the module
docstring that is `sminos help`; `channel_say_refusal` and
`find_target`'s CH1 sentence go), `S/sminos_channels.py` (`speak`, `chat`,
the sentences of §2), `T/test_channels_say.py` (new), `T/test-channels.sh`
(its section "nothing is said into a channel" becomes what is said),
`T/test_channels.py` (its cases that pin `channel_say_refusal`),
`T/test-channels-machines.sh` (the fourth step of CH1's scene),
`T/channel_wire.py` (§8).

**Interfaces:** exposes §2 and §6's `chat`. Consumes §1 (`reach_in`), §3
(`owing`, `deliver_next` with it).

**Seams:**

- *Sending and delivery* (M2). `deliver_say` is the one join: for a
  recipient of this machine it asks `owing` for the thread the roster's row
  names and calls `deliver_next` with it, so the sender's own call and the
  daemon's pass are one operation. Crossed by: a `say --in` to a live
  member prints `sent` and the inbox stand-in holds exactly one frame; to a
  stopped member that may be woken, `sent (woken)` and the test engine one
  launch; to one that may not, T2's held line; and a second `daemon tick`
  pushes nothing more.
- *The reply and the roster* (M1). A member's frame's reply line is
  `@<channel id>/<short>`, and the door gives a qualifier that names a
  channel to `reach_in`. Crossed by: the line taken from the recipient's
  frame and run as written lands in the channel's log and reaches the
  first sender; run after that sender was removed it lands in the sender's
  own project's log, reaches it there, and the replier reads §2's line;
  run after another thread came to hold that session id it is refused as
  ambiguous and reaches no one.
- *The two forms of the reply line* (M2). Which form a frame carries is
  read from the event alone. Crossed by: a non-member's `say --in`, the
  member's reply by its frame's line, and the non-member's answer by the
  line of the frame that reply arrived in: the first lies in the channel's
  log with `from_project`, the second in the non-member's project (a
  message to another project, as today), the third in the member's
  project; none of the three is refused, and the channel's log holds
  exactly the first.
- *The refusals lifted, and every door that relied on them.* §6's table
  names each reader of a channel's log and what it does with a message
  there; this milestone's tests visit every row that is a command.

**Decisions:**

- The door is one function (`sminos_channels.speak`), entered from
  `cmd_say` where `channel_say_refusal` stands today, after EN.G1's
  `--notice` checks and before a selector is read, for the two ways a say
  names a channel: `--in`, and a tag's qualifier (a name or an id). It
  decides, before anything is appended: the channel (`find_channel`'s
  refusals); that the machine's enrollment carries the channel's log, as
  CH1's verbs check it, since what is written would otherwise never leave
  the machine; who writes and how (§2); the recipients; and that every
  tag is in that one channel. §2's table says what takes each of CH1's
  refusals' place.
- The unquoted `@<name#short>/<alias>` opens no tag (a tag's qualifier
  takes no `#`: `TAG_RE`, which the audience split also reads), so it
  stays refused where `shortened_channel_qualifier` finds it, in a
  sentence that names the two forms that work.
- Whether the sender is a member is read once, in the door, from its own
  machine's record (`channels_of`), and decides two things there and
  nothing anywhere else: a member's event is appended as it is; a
  non-member's gains `from_project`, its copy is kept by `record_copy` as
  `cmd_say` keeps one for another project's log, and the sender reads §2's
  line. The tests of the two are two classes of their own (`Member`,
  `Outsider`).
- A tag qualified by the channel that names, by id, a thread that is not
  in it now (`reach_in`'s `out`: the reply line of an old frame) sends to
  that thread directly: the message goes to its own project's log by
  today's path for `@<short>`, and the replier reads §2's line. With
  `--in` the same tag is refused, as every tag that resolves in another
  log is (B1). A name in alias form that no member answers is refused in
  both.
- With `--in <channel>` every tag is looked up in that channel's roster
  alone, in any form a tag takes. A tag qualified by another log, or one no
  member of the channel answers, is refused before anything is written
  (B1's last sentence), saying where that name does answer when it does.
- Without `--in`, tags qualified by one channel make that channel the
  destination, and every other tag of the message must be qualified by it
  too: a bare name resolves to its thread's own project (M1), and "one
  message, one log" refuses the mix in today's words.
- The event is today's (`from`, `to`, `text`, `wake` for an `@all`,
  `notice` for a notice); `from_project` and the copy are a non-member
  session's alone. Audience streams split it as `streams_for` splits any
  say.
- `@all` in a channel is the roster's rows in a live state (`FILLED`), the
  sender left out; a machine's project's refusal of `@all` does not apply.
- A selector that names a channel stays refused, in a sentence that names
  `--in <channel> "@all …"` (open point 1); `--in <project>` from a session
  stays refused in today's sentence (the composite's Deferred).
- `cmd_chat` branches before `find_project` on `names_channel`, to a read
  of its own (§6): it never calls `reconcile`, which runs a project's
  reconciliation and would hand off or end what an older copy joined into
  the channel.
- `sminos help` gains `say --in <channel>`, the channel-qualified tag,
  `chat <channel>`, and loses "nothing is said in one in this version".
  The guide and the skill do not change here (M8).

**Does not touch:** the uplink (a recipient on another machine reads
`recorded (on <machine>)` or its machine's published hold, as for any
thread there, and M5 delivers it; a message whose push needs the
endpoint's word, a person's words from a terminal among them, is recorded
and left owed with today's line, and M5 asks), the lead (an untagged post
from a terminal is untagged until M6), the guide, the skill, the spawn
preamble.

**Proves:** B1, B2 and B5 on one machine; B11 for `say` and `chat` (a store
with no channel, compared with the merge base's output). Its tests pin,
beside the seams: each refusal of §2 with nothing appended to any log; a
member's event carries neither `from_project` nor `copy`, and no project's
log gains an event from it; a non-member's carries `from_project`, and its
copy in the sender's project names the channel's event and is owed to no
one; a non-member's `@all` reaches the live members and its untagged post
prompts no one; nothing the channel's log holds is pushed to the
non-member, an `@all` there and a reply addressed to a member among them;
a private recipient's stream; a notice into a channel from a machine that
holds no member of it, shown by `chat` as `<program>@<machine>` and
delivered with no reply line; `chat <channel>` over a channel's log in
which an older copy left a closed session's `joined` changes neither that
thread's record nor any file of the log (the fold's first correction);
`chat <channel>` after a hand-off prints only what is new to the thread;
and `chat` with no argument, and `list` with none, are today's.

### M4 — The scene on a real engine, and the roster's cost

**At its end:** the acceptance's scene on a real engine (B9) has been run
once under a scratch home against the code as M3 leaves it, each step
observed or its failure fixed and tested, and the figures of what a roster
costs are recorded. This milestone's deliverable is knowledge and the
fixes it forces; it sits here, and not at the end, because the engine is
in M2's and M3's path (a push to a live inbox, a wake, a hand-off, the
order of an engine's hooks), and T1 and T2 each found that order different
on a real engine from what their suites had staged.

**Touches:** `T/bench_scale.py` (a `--channels N` scale and three timings
in `verbs`), `T/test_scale.py` if the scale's shape is asserted there, and
whatever of M1 to M3 the pass shows wrong, with a test for each fix in the
suite of the milestone that owns it.

**Interfaces:** consumes everything of M1 to M3; exposes nothing.

**Seams:** *a hand-off and what a channel owes* (M2's rows D6 and D7), on a
real engine: the suites stage a hand-off by writing the engine's
`continued-in` line; here the engine writes it, in its own order. Crossed
by step 4 of Concrete Steps: the member handed off has a boundary that
holds a position, the job that continues it keeps that boundary byte for
byte, and a message said to it after the hand-off arrives once in the
job's conversation.

**Decisions:**

- The pass is Concrete Steps' five steps and nothing wider. If the
  executor's environment has no engine credentials it is reported as not
  run, never as passed, and M9 owes it.
- The member whose boundary is observed is the one placed by `channel add`,
  not the creator: a creator enters an empty log (an empty boundary), while
  a thread added by a request enters a log that holds that request, so its
  boundary names a position. CH1's check carried only the empty kind.
- The roster's cost is measured where it is paid. `rosters` reads every
  project's view once and sorts its rows by channel, so its cost follows
  the number of projects and members, not of channels; and from M1 on a
  member's tagged `say` pays it. The bench builds the MacBook's shape with
  thirty channels and times `sminos list` by a member, `sminos channel
  show`, and a tagged `say` by a member of all thirty, each beside the same
  command with no channel. It also reads the idle uplink's calls a second
  with thirty channels held, beside the gate's figure with none. The
  figures go to Surprises & Discoveries and to the holder, who decides with
  them whether the deferred index of statements, and the TECH-DEBT row "A
  roster can list a thread's obsolete row for a moment", are promoted (open
  point 7). Nothing is built on them here.

**Does not touch:** the gate's limits, `sminos-idle`'s stand-in, the
person's real configuration.

**Proves:** B9 (run again on the final head in M9 only for what changed
after this milestone), the composite's two delegated unknowns it names (a
roster's cost; a non-empty boundary across a real hand-off).

### M5 — Across machines: the endpoint's word on a message

**At its end:** a message said into a channel on one machine is uploaded
under the channel's id, reaches the machine of a member that runs
elsewhere, and is delivered there on the endpoint's word: pushed to a live
session, waking a stopped one, held for one that is not woken; the reply
travels back the same way. A recipient's machine that turned read-only
refuses it there; a word that arrives after the thread was removed pushes
and wakes nothing. Nothing but the events, their `reach?` and their
`words?` goes up under the channel's id.

**Touches:** `S/sminos_uplink.py` (`ask_words`' channel half, `on_words`,
`on_reach`, the asks held, `expire_asks`, and `Link.may_leave` if it lets
a followed channel go with an event of this machine's not yet uploaded),
`S/sminos_channels.py` (what
the pass asks and how a word is carried out), `S/sminos.py` (the bound on
the delivery lock in `deliver_verdict` and `deliver_reach`),
`T/endpoint_standin.py` (§8), `T/channel_wire.py` (`published`),
`T/test_channels_wire.py`, `T/test-channels-machines.sh` (its cases, and
this child's scene), `T/rl10-machines.sh` if a helper is missing,
`T/rl10-conversation.json` and `T/rl10-conversation.source.json` (MAWS's
copy with its two new cases, when it lands), `T/rl10_conformance.py` (only
what those cases need of the harness).

**Interfaces:** exposes §4. Consumes §3 (`owing`, the delivery operation
with it), CH1's `Link.member_on_lane`, `Link.senders_before`,
`Link.channels`, `Link.serves_channels`.

**Seams:**

- *Delivery and membership's positions* (M2), on the wire. The uplink keeps
  no member and no membership with an ask: when a word arrives it is kept,
  and the pass that carries it out asks `owing` again, so the delivery
  record it then reads is already settled to the boundary as it is now.
  Crossed by `T/test_channels_wire.py`: the stand-in's reply to a `reach?`
  is kept back, the thread is removed (and, in a second case, removed and
  added again; in a third, handed off), the reply is released, and the
  test engine records no launch and the inbox no frame in the first two,
  one frame in the job's inbox in the third.
- *What this machine held at the boundary* (the fold's fifth correction),
  on two machines: a message written on `alpha` during a membership of a
  thread on `beta` and relayed to `beta` only after that thread was removed
  and added again is pushed; the same message relayed before the removal
  is not pushed after it.
- *Sending and the wire* (M3). An upload of a channel's log is preceded by
  the member frame of each sender that is a member of a project now, and
  by none for a sender that has retired since it wrote
  (`Link.senders_before`, unchanged). Crossed by: a message whose sender
  retired before the upload goes up with no frame, so with no attestation
  of its own, and is delivered or refused at the other machine as that
  machine's endpoint says.
- *A machine that writes and holds no member* (C5: "what this needs of the
  sender's machine"). A machine with no thread in the channel only follows
  its log, and what it appended there still goes up, as a request's writer's
  does. Crossed by: on `gamma`, which holds no member, a session says
  `--in` the channel: the event is uploaded under the channel's id from a
  log opened with `follow`, preceded by its sender's member frame under
  its own project, and is delivered on `alpha` and `beta`; the member's
  reply reaches the sender in its project on `gamma`; and the leaving rule
  does not let the channel go from `gamma` while an event `gamma` appended
  to it has not gone up.
- *The sender's frame and the upload* (M3; MAWS's architect, 2026-11-22).
  The endpoint attests an upload from its writer's member frame, found by
  session alone: with none, the event goes up with no attestation, and a
  private session's stream is refused `audience`. Crossed by: for a
  member's message, for a non-member's, and for a private sender's stream,
  the stand-in received the sender's member frame, under the sender's own
  project, before the `events` frame that carries its message under the
  channel's id.
- *Opening a channel and the endpoint's policy cache* (MAWS's architect,
  2026-11-22). A log a machine opens joins the endpoint's rebuild of its
  policy cache, and until that log's `snapshots?` is answered `done` an
  upload that names a recipient the cache does not know is held. sminos
  answers a channel's with one page, empty and done (CH1,
  `Link.on_snapshots`). Crossed by: on a machine that holds no member and
  opens the channel with `follow`, the stand-in's `snapshots?` for the
  channel is answered `done` with no event, and the tagged message said
  there afterwards goes up.
- *Outcomes* (the fold's second correction). Crossed by: a message from
  `alpha` is pushed and settled on `beta`, `beta`'s uplink then runs its
  upload pass (which drains an outbox where there is one), and only then
  are `beta`'s stand-in's frames given to the checker: no `session` frame
  of kind `delivery` names the channel, and the channel's home holds no
  outbox file.

**Decisions:**

- The uplink asks about a channel's messages in a pass of its own, behind
  its message asks and beside `ask_requests`, run only while `Link.channels`
  is not empty: for each open channel, the threads of this machine in it,
  through `owing`, and `words_due` and `reach_due` given those (§4). It
  needs `channels` in the welcome, and `reach` for a `reach?`.
- The frame's `session` is the thread's current session, whatever session
  the signed event names: the endpoint finds its recipient by the frame's
  `session` alone, as for a request (`ask_of`).
- Before an ask, the recipient's member frame is on the lane under its own
  project, read as the plane last read it (`Link.member_on_lane`): the
  endpoint answers a `reach?` nothing, and a `words?` `peer`, for a session
  it holds no record of, and the second would hand a person's words over
  as a peer's.
- A word is kept, not carried out, by `on_reach` and `on_words` (as a
  request's is by `Link.request_answered`), and the next pass carries it
  out with every lock tried or bounded (§4). A word that could not be
  carried out, and a reply that names no verdict, wait for the ordinary
  interval; nothing is asked again at a reply's speed.
- The read-only policy, the revocation set and the hold are read again when
  the word is carried out, as `deliver_reach` and `deliver_verdict` read
  them today.
- The fixture is copied byte for byte from MAWS's master at the commit and
  blob the holder passes on when MAWS's two cases land, with
  `T/rl10-conversation.source.json` naming them, and the replay runs every
  line as written. If they have not landed when this milestone's review is
  clean, the milestone closes without them, Progress says so, and M9 owes
  the copy and the replay.
- A non-member's message and its copy are two events in two logs, each
  uploaded in its own log's turn; neither waits for the other, as for a
  message to another project today.
- A message for a machine on 1.54.0 needs no code here: the sender reads
  what it reads for any thread on another machine. M9 shows the receiving
  side with a real 1.54.0 copy over one store, then this code over the
  same store: the message is pushed once.

**Does not touch:** `Link.senders_before`, `Link.open_channel`,
`Link.on_snapshots`, the hello, `member_frame`, `Plane.refresh`, the
project's `ask_words` loop and its keys.

**Proves:** B1, B2 and B4 across two machines; B11 on the wire (the frames
of a machine that holds no channel, compared with the merge base's). Its
tests pin, beside the seams: one ask out at a time for a recipient and a
writer; a `refuse` settled `refused-reach` on that machine with no frame
back; a `peer` word on a person's message followed by a `reach?` about the
same event; a held recipient asked about nothing; the consumer thread's
bound (the delivery lock, the wake lock and the channel's registration
lock each held by another process while a word arrives and a pass runs:
the uplink's loop returns within its bound and the message stays owed);
the replay of MAWS's fixture with its two new cases, every line `ok`;
and the checker over every stand-in, with this child's rules.

### M6 — The lead, and whose words a post is

**At its end:** at a terminal, `sminos channel lead desk-integration
worker` asks for a typed yes and writes the lead; inside a session, and
where there is no terminal, it is refused. An untagged message the owner
then types into the channel is addressed to the lead, wakes it if it is
stopped, and on the lead's own machine reaches it as its human's words. A
lead event under a session's writer changes nothing; a lead that ended or
left is ignored; a machine's notice with no tag stays untagged. `sminos
channel show` prints the lead.

**Touches:** `S/sminos_channels.py` (`lead_of`, the verb, `show`),
`S/sminos.py` (the parser's `channel` family and its usage line, `cmd_say`'s
untagged branch for a channel through `speak`, the docstring),
`T/test_channels_lead.py` (new), `T/test-channels.sh`,
`T/test-channels-machines.sh`, `T/channel_wire.py` (the kind).

**Interfaces:** exposes §5. Consumes §2 (`speak`), §3, §4 (the `words?`
under a channel's id), `sminos_visibility.confirmed`, `notice_of`,
`owner_event`.

**Seams:**

- *The lead and the bridge.* A person's words reach a session as its
  human's only on the endpoint's `words`, and the endpoint gives it only on
  the machine that wrote them. Crossed by: on the lead's machine the
  stand-in answers `words` to a `words?` under the channel's id and the
  post is handed over as a person's words are for a project's log (the
  bridge's `deliver`, keyed by the channel's id; the supervisor's reply
  where no bridge takes it), never as a peer's inbox frame; from another
  machine the endpoint's word is `peer` and it arrives as a peer's frame
  from `human`; and in both, after the push, no `message`, `question` or
  `answered` lies under the channel and none in the lead's project names
  the channel (B7).
- *The lead and the roster* (M1). A lead is in effect only while its thread
  has a row in the roster. Crossed by: the lead removed, ended, and
  returned: an untagged post is untagged, untagged, and addressed again.

**Decisions:**

- The verb is refused inside a session before anything is read (the test
  every such verb makes: `CLAUDE_CODE_SESSION_ID` set), then `confirmed`
  asks at `/dev/tty` itself, which refuses where there is none. The event
  goes under the machine's human writer, plain.
- The lead is read where a post is written, on the machine the owner types
  at (D3): the receiving side reads no lead, it delivers an addressed
  event.
- `none` clears it. A thread whose alias is `none` is named `alias#short`.
- A lead on another machine than the one the command runs on is taken, and
  the command says that posts typed here reach it as a peer's message, not
  as its human's words (open point 5).
- Suites drive the typed yes on a real controlling terminal, as
  `T/test_visibility.py` and `T/test_threads_owner.py` drive `confirmed`.

**Does not touch:** `confirmed` itself, `words_route`, `sminos_control._routes`
(a notice's route and a person's are today's), the guide.

**Proves:** B6, and B5's "a machine's notice is never read as the owner's
post". Its tests pin: each refusal with nothing written; a `channel-lead`
under a session's writer, under `hub/<member>`, and carrying `notice`,
each ignored; two machines' human writers, the later by merge order
holding; a lead that is a stopped thread woken by the post; `channel show`
and its `--json` with and without a lead (no key without one).

### M7 — What reads a session's exchanges reads a channel's

**At its end:** the list of exchanges a session is given after a compaction
or a resume names a peer it spoke with only in a channel, with a tag that
reaches it; the manager's window marks an owner's post delivered from a
channel as the owner's, and tells apart two events of one writer and seq
that lie in two logs. Nothing a session or the bridge does while its
thread is in channels writes a word to a human under a channel's id, and a
stopped thread's questions are closed for its project alone.

**Touches:** `S/sminos.py` (`roster_text`, `_roster_exchanges`,
`_roster_peer`), `M/manager_window.py` (`frames`, `OwnerWords`),
`M/manager.py` (`cmd_transcript`'s logs), `M/CLAUDE.md`,
`T/test-guide.sh`, `T/test_channels.py` (its case
`test_a_resumes_roster_gives_no_tag_through_a_channel`, which pins today's
answer), `T/test_manager.py`, `T/test_channels_say.py` (B7).

**Interfaces:** exposes §6's two readers. Consumes Y1 (`channels_of`,
`known_channels`, `roster`), §1.

**Seams:** *the event's log and its reader* (M3). A message in a channel
carries neither `from_project` nor a copy, which are what
`_roster_exchanges` reads a cross-project exchange from today; so a
channel's exchanges are invisible to it until it reads the channel's own
log. Crossed by `T/test-guide.sh`: two sessions that exchanged messages
only by `say --in`, then a `compact` payload: each is listed for the other
with a tag that, run, reaches it.

**Decisions:**

- `roster_text` reads, beside the session's project and its launch
  directory's, the logs of the channels its thread's record holds now
  (`channels_of`). A channel the thread has left is not read: its
  exchanges are history the reader no longer shares. The budget
  (`ROSTER_BUDGET`) bounds it as before.
- In a channel's log "mine" is the session and its lineage as the thread's
  own project states it, not the channel's projection, which holds no
  membership. A peer met in a channel is listed once, with its own
  project's row and the tag that reaches it from here (`_roster_tag`: its
  own project's, never one qualified by the channel, so the tag is right
  after either leaves the channel); a peer met in both a project and a
  channel is one row, its last exchange the newest.
- A message from outside a channel needs nothing new here: read in the
  channel's log it carries `from_project`, which is how
  `_roster_exchanges` already finds an inbound peer's own project, and the
  sender's copy names its recipients under the channel's id, which
  `_roster_peer` now resolves to each one's own project.
- The manager's `OwnerWords` is keyed by the log's name with the ref, and
  `frames` keeps the log's name it already parses; `cmd_transcript` builds
  it from the subscription's project and the channels known on the machine
  (`known_channels`), since a window may look back past a membership.
- B7 is proved, not built: every writer of a word to a human takes its log
  from the session's own project (`session_project`), `append_host` raises
  for a channel, and `close_questions` walks `known_projects`. The tests
  drive a session in two channels through a turn that delivers a channel's
  frame by the inbox and one by the bridge, an ask, an answer, a stop and
  the sweep, and then read every log.

**Does not touch:** `append_host`, `export_live`, `close_questions`,
`session_project`, the manager's subscriptions (one project each, as
today: a thread has one project), `M/manager_ledger.py`,
`M/manager_serve.py`, the manager's `SKILL.md` (M8).

**Proves:** B7 and B8. Its tests pin: the manager's classifier on a frame
from a channel whose ref an event of the project's log also carries, with
different bodies (each marked by its own log); a peer met only in a
channel that has since ended (listed as ended, no tag); a non-member that
said into a channel and the member that answered it, each listed for the
other after a compaction; and the roster of a session in no channel, byte
for byte.

### M8 — What sessions are taught, and its evaluation

**At its end:** the session-start guide, `sminos/skills/sminos/SKILL.md`,
the spawn preamble and the manager's skill speak of threads and channels
and teach what M1 to M7 built; the evaluation of Concrete Steps has been
run on the texts as they were and as they are, and its record is in the
Decision Log; the reply line's debt row is closed or answered.

**Touches:** `S/sminos.py` (`guide_text`, and `reply_line` only under the
condition below), `sminos/skills/sminos/SKILL.md`,
`sminos/skills/sminos/references/spawn-preamble.md`,
`sminos/skills/manager/SKILL.md` and its `references/digest-brief.md`,
`sminos/hooks/CLAUDE.md`, `T/test-guide.sh`, `T/run-sminos-tests.sh` (the
preamble's pinned lines), `docs/doperpowers/TECH-DEBT.md` (the reply
line's row).

**Interfaces:** exposes §7. Consumes the CLI as M1 to M7 leave it.

**Seams:** *what is taught and what the doors say* (M3, M6). Every command
a text shows is run, as written, against the tree in the evaluation's
live scenario, and every refusal a text explains is the sentence §2
gives.

**Decisions:**

- Through doperpowers:writing-skills, by its method: a baseline first, on
  the text as it is; a line the baseline already produces is cut; five
  samples or more a variant, read by hand. §7 lists what each text must
  come to say and what it must stop saying; the wording is the
  evaluation's to settle.
- `send` leaves what sessions are taught (D5, the owner): the skill keeps
  it only as the script's verb (`--wait`).
- The reply line (the TECH-DEBT row "A peer message's reply line still
  models a double-quoted body…", due here). Its absolute path stays, for
  the row's own reason: a recipient may run without the plugin's `bin/`.
  Whether its words change is decided by the evaluation's scenario E4 (a
  reply that must carry code): if no sample of the baseline puts a live
  backtick, a quote or a `$` into the double-quoted form, the line stays
  and the row is closed as measured; if one does, the line gains, on the
  same single line, where the same tag goes on standard input, in §7's
  form, and the tests that read the line are changed with it (open point
  6: the line is what sessions copy most, and its words are the owner's).
- The manager's skill is rerun on its own terms (`M/CLAUDE.md`: a change to
  its skill or brief reruns its pressure scenarios, and for the brief a
  replay update).

**Does not touch:** any verb's behaviour; `sminos help` (M3 and M6 wrote
it); the backtick guard (its verb list already holds `channel`, and this
child adds no verb beside it).

**Proves:** B10; X6. `T/test-guide.sh` and the preamble's pins pass on the
new lines.

### M9 — Older copies, what is written beside the code, the version, and the acceptance

**At its end:** `T/test-older-cli.sh` runs 1.27.10, 1.51.0, 1.52.0 and
1.54.0 beside this code over a store whose channel holds messages, a lead
and a member with mail owed; `S/CLAUDE.md` has been read whole against the
tree; the public face follows it; TECH-DEBT holds what this child accepts
and no longer what it closed; sminos is 1.55.0; and the acceptance has
been run as Concrete Steps gives it.

**Touches:** `T/test-older-cli.sh`, `T/older_channel_wire.py`,
`sminos/skills/sminos/scripts/CLAUDE.md`, `sminos/CLAUDE.md`,
`sminos/README.md`, `docs/whats-inside.md`, `docs/doperpowers/TECH-DEBT.md`,
the files `scripts/bump-version.sh --plugin sminos` writes,
`.github/ci-kit.yml` (the `sminos-channels` gate's timeout).

**Interfaces:** consumes everything; exposes nothing new.

**Seams:** *a refusal lifted and a copy that still has it.* 1.54.0 refuses
every say into a channel and delivers none; this code writes them. Crossed
by the suite's 1.54.0 cases below, the two copies over one store.

**Decisions:**

- 1.54.0 is pinned as the merge that released it
  (`e0aa6d390359300dd37339c647b01bd66ba3a4fd`), fetched as the other three
  are. It differs from them where the suite's every-copy expectations
  speak of a channel: it lists no channel as a project, ticks none as one,
  refuses `join <channel>` itself, and wakes a thread its human opened; its
  arms say so.
- Per version, asserted over a store this code staged (a channel with two
  members, messages addressed to a session of that machine, a
  `channel-lead`, a delivery record under the channel): the copy's `list`,
  `list --json`, a tagged `say`, `send`, and its `daemon tick` do what
  they did over the same store with an empty channel; it pushes nothing
  from the channel and writes no delivery record there; the thread's
  `channels`, `began` and `answered` are what they were. For 1.54.0 also:
  its `channel show` prints the roster and the requests with the messages
  and the lead in the log; its say into the channel is refused in its own
  sentence; an add, a removal and a return it carries out leave a boundary
  that this code then delivers from (a message that arrived while it ran is
  pushed by this code when the thread was a member throughout, and never
  when 1.54.0 removed and added it after the message arrived).
- Then an uplink of this code over the store each copy left, and the
  checker with this child's rules.
- TECH-DEBT, section "sminos channels": each row whose trigger names CH2 is
  rewritten to what became of it (Concrete Steps lists them), and this
  child's own accepted limits are added, each with what would promote it.
- `docs/whats-inside.md` and `sminos/README.md` change their sminos rows in
  this change (the repository's rule: the public face follows the tree).
- The `sminos-channels` gate's timeout is set to about twice the part's
  measured run, and the part is split before it passes fifteen minutes
  (the four conditions agreed with the session that owns CI, in the
  composite's Decision Log).

**Does not touch:** the guide and the skill (M8 closed them), the fixture.

**Proves:** the older-copy clauses of B4 and of C5's "Between releases";
B11 whole (the gates on the final head, compared with the merge base);
every item by the proof map, on the final head.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-channels-ch2`).

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_channels_names.py
    python3 -B sminos/tests/test_channels_delivery.py
    python3 -B sminos/tests/test_channels_say.py
    python3 -B sminos/tests/test_channels_lead.py
    python3 -B sminos/tests/test_channels_wire.py
    python3 -B sminos/tests/test_manager.py
    bash sminos/tests/test-channels.sh
    bash sminos/tests/test-channels-machines.sh
    bash sminos/tests/test-guide.sh
    bash sminos/tests/test-older-cli.sh
    python3 -B sminos/tests/rl10_conformance.py sminos/skills/sminos/scripts sminos/tests/rl10-conversation.json

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. A shell file ends with its counts of passed and
failed and exits non-zero on any failure. The replay prints one `ok` or
`FAIL` line per line of the conversation it plays: 121 today, and more
from M5's copy of MAWS's fixture, which adds two cases and changes none.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-channels,sminos-idle,sminos-mods,shell-lint,repo-checks

with `mods-types` where a mod changes and `version-bump` in M9. Expected:
one `PASS` line per gate, then `GREEN` and the run's address. A `FAIL` that
the base also shows, or one a recorded reason names, is not this change's;
any other is diagnosed, not run again. Each milestone's report gives two
figures, which the controller writes into its Progress line: the
`sminos-idle` gate's `N of them Python functions` a second (its limit
33,570), and the `sminos-channels` gate's duration (its timeout in
`.github/ci-kit.yml` is kept at about twice that).

**The proof map.** Where each acceptance item of CH2's section is proved.
B1 to B11 number its items in the order the section lists them.

| Item | Proved in (milestone: file) |
|---|---|
| B1 `say --in` and `@<channel>/<alias>`: delivered framed as from the channel, a stopped member woken, the reply by the frame's line in the channel's log; a say with neither lands where it does today; `--in` with a tag that resolves elsewhere refused | M3: `test_channels_say.py`, `test-channels.sh`; M2: `test_channels_delivery.py` (the frame, the wake); M5: `test-channels-machines.sh` (another machine); M4 (a real engine) |
| B2 `@all` reaches the live members, an untagged post prompts no one; a thread that is no member is refused no form: its message in the channel's log with `from_project` and a copy in its project, delivered, framed as from outside, answered in the sender's project; the sender told in one line; nothing of the channel's pushed to it | M3: `test_channels_say.py` (`Member`, `Outsider`), `test-channels.sh`; M2: `test_channels_delivery.py` (the frame, the reply line's two forms, nothing owed to a thread that is no member); M5: `test-channels-machines.sh` (a machine that holds no member) |
| B3 a bare `@alias` through a shared channel; two answers refused with `alias#short`; a name a project and a channel both answer refused | M1: `test_channels_names.py`, `test-channels.sh` |
| B4 what a channel owes follows membership | M2: `test_channels_delivery.py` (§3's rows); M5: `test_channels_wire.py` (a late word), `test-channels-machines.sh` (what the machine held at the boundary); M9: `test-older-cli.sh` (a message that reached the machine while it ran 1.54.0; a return an older copy made) |
| B5 a reply after its sender left is delivered to that thread in its own project, the replier told, and reaches no other member; a notice written into a channel by a machine that holds no member | M1: `test_channels_names.py` (the rule); M3: `test_channels_say.py` (the reply line run); M5: `test-channels-machines.sh` (the notice from a third machine in the pool) |
| B6 the lead | M6: `test_channels_lead.py`, `test-channels-machines.sh` |
| B7 no word to a human under a channel's id; a stopped thread's questions closed for its project alone | M7: `test_channels_say.py`; M2 and M6 (after each push); the checker in every suite that runs an uplink |
| B8 the exchanges after a compaction or a resume; the manager's window | M7: `test-guide.sh`, `test_manager.py` |
| B9 a real engine | M4, and M9 for what changed since |
| B10 the skill's evaluation | M8 |
| B11 parent line 8 for this surface | every gate at every milestone; M1 (a sender in no channel reads no roster); M3 (`say` and `chat` compared with the merge base's); M5 (the frames of a machine with no channel); M7 (the roster of a session in no channel) |

**M4, the scene on a real engine.** In a scratch tree `<scratch>`:
`HOME=<scratch>/home`, `CLAUDE_CONFIG_DIR=<scratch>/home/.claude`,
`SMINOS_HOME=<scratch>/sminos`, `MAWS_USER_DATA=<scratch>/maws`, the
engine's credentials passed through the environment, workspace trust for
the two repositories written into the scratch config beforehand, the
scratch user settings giving `permissions.defaultMode: auto` (a wake runs
only in a mode that does not ask), and the plugin loaded from a directory
marketplace in the scratch config that points at the worktree, not by
`--plugin-dir` alone: a wake sminos starts does not carry a launch's
`--plugin-dir` (T2's lesson). `sminos` means the worktree's launcher in
every shell; the machine is cut over as `T/rl10-machines.sh` cuts one
over, a stand-in serving it with `channels` among its capabilities, and
the scratch daemon (`sminos daemon run --interval 5`) runs in a
multiplexer of its own. Never the person's real configuration.

1. In `<scratch>/a`, a git repository, a session A; in `<scratch>/b`,
   another, a session B; one turn each, both left open. A runs `sminos
   channel create probe` and `sminos channel add probe <B's short>`.
   Expect: `sminos list` from both shows `# probe` with both, and B's
   thread record holds for `probe` a boundary with one position (A's
   request).
2. A runs `sminos say --in probe "@<B's alias> <a nonce>"`. Expect: A's
   line for B reads `sent`; B's transcript gains one frame whose first line
   is `[sminos chat probe <ref> from <A's alias>… → @you]` and whose last is
   the reply line naming `@<probe's id>/<A's short>`. B is asked, in its
   next turn, to answer with the line its frame gives. Expect: `recorded
   <ref> in probe`; A's transcript gains B's frame from `probe`; the
   channel's log holds the two messages, neither repository's log gained
   one, and neither message carries `from_project` or `copy`.
3. B's terminal is closed. `sminos list --stopped --channel probe` shows B
   `stopped`. A runs `sminos say "@probe/<B's alias> <a second nonce>"`.
   Expect, within two minutes: one background process holds B's session
   id (one more job in `claude agents --json --all` than before, with that
   `sessionId`), no copy of the session exists, B's transcript holds the
   second nonce once, and the last paragraph of that frame is the
   machine's `[sminos] ` line saying it was woken.
4. B is handed to a background job by the engine's own hand-off from
   inside the session (as T1's and CH1's passes did it), after `claude
   --resume <B's session>` attaches to it. Expect, within two ticks: one
   row for B's thread in `# probe`, under the job's session id; the
   record's boundary for `probe` equal, byte for byte, to step 1's, and
   not empty. A runs `sminos say --in probe "@<B's alias> <a third
   nonce>"`. Expect: the third nonce once in the job's transcript, none in
   the session it continues.
5. The roster's cost, with no engine:

       python3 -B sminos/tests/bench_scale.py verbs sminos/skills/sminos/scripts --preset macbook --channels 30
       python3 -B sminos/tests/bench_scale.py verbs sminos/skills/sminos/scripts --preset macbook --channels 0
       python3 -B sminos/tests/bench_scale.py run sminos/skills/sminos/scripts --preset macbook --words 0 --working 30 --warmup 60 --seconds 10 --pycalls 60 --channels 30

   Expect: each prints its timings, and the third the idle uplink's calls
   a second with thirty channels held. The report gives the six command
   timings as pairs (with thirty channels, with none) and the idle figure
   beside the gate's.

Afterwards every scratch job is removed, the multiplexer and the scratch
daemon are stopped, and the report keeps what each step printed beside the
commands. A step that does not show what it expects is diagnosed: a fault
of M1 to M3 is fixed with a test in the suite of the milestone that owns
it; an order of the engine's hooks the suites did not stage is added to
the suites' staging.

**M8, the evaluation.** By doperpowers:writing-skills, each scenario on two
arms, the texts at the merge base and the texts as edited, five samples an
arm, each sample a fresh session, read by hand. Two kinds:

- *Live* (E1, E5): a fresh `claude -p` session with the plugin loaded from
  the worktree, under a scratch home as in M4, on a machine cut over to a
  stand-in that lists `channels`, with two other sessions staged as members
  of other projects. What passes is read from the store afterwards, not
  from what the session says.
- *Single-shot* (E2 to E4): a fresh session with no tools, given the guide
  as `guide_text` prints it for that arm, the skill, a conversation that
  ends in real CLI output, and asked for the commands it would run.

| | Scenario | Passes when |
|---|---|---|
| E1 | "Work with the session in the other two repositories on X; keep the three of you in one place." | it creates a channel, places the two others, and every message it then means for the three lies in the channel's log: none in a project's log, none refused and abandoned (B10's sentence) |
| E2 | a frame from a channel arrives; the session must answer | it answers with the frame's reply line, unchanged but for its text |
| E3 | the session, in no channel, is asked to tell a channel's members something once | its message lies in the channel's log, sent once; it reads the line it is given and neither adds itself unasked nor sends the same text again by another route |
| E4 | a frame arrives whose answer must quote code with a backtick and a `$` | the command it gives passes the text unharmed (standard input), and reaches the sender |
| E5 | a session in no channel, told to message a peer in its project and one in another | it does what the baseline does: no `channel` verb, no `--in` |

A scenario the baseline already passes adds no line to a text for it (the
method's rule). E1 failing on the edited texts, in any sample, is a
finding the milestone fixes in the texts and runs again. The manager's
skill: its six pressure scenarios, as
`docs/doperpowers/specs/2026-10-31-session-manager-design.md` lists them
and `docs/doperpowers/specs/2026-10-31-session-manager-replay.md` records
how they were run and scored, on the rewritten skill, with one of the two
workers a member of a channel and speaking in it; all six pass as that
record defines passing; and, since the brief changes, one replay update.
The report keeps every prompt and every answer outside the repository and
gives the counts here.

**M9, the acceptance.** The gates GREEN on the final head; the older-copy
suite; then the scene, which M5 builds as a second scene of
`T/test-channels-machines.sh` and M6 extends, run alone, printing each
command with what it printed:

    bash sminos/tests/test-channels-machines.sh --speak --show

Three machines, `alpha`, `beta` and `gamma`, each a sminos home with its
daemon, the test engine and a stand-in that lists `channels` and `reach`;
on `alpha` a live thread its human opened, A, a stopped spawned thread, S,
and a live thread X in no channel; on `beta` a stopped thread its human
opened, B, in another project, last run in a mode that does not ask; on
`gamma` no thread. Expected, step by step:

1. A runs `sminos channel create desk-integration` and `sminos channel add
   desk-integration <S> <B>`; after a pass the roster on both machines
   holds the three.
2. A runs `sminos say --in desk-integration "@<B> one"`: its line for B is
   what a sender reads for a thread on another machine. After a pass
   `beta`'s test engine has recorded one launch for B's session and B's
   input holds one frame, its first line naming `desk-integration`, its
   last paragraph the `[sminos] ` line, the reply line naming the
   channel's id and A's short.
3. B's reply, the line run as written on `beta`, is recorded in
   `desk-integration`; after a pass A's inbox holds it once. No project's
   log on either machine has changed since step 1 but for the threads' own
   lifecycle, and no event of the channel's log carries `from_project` or
   `copy`.
4. A runs `sminos say --in desk-integration "@all two"`: B, live since
   step 2, receives it after a pass; S, stopped, receives nothing and is
   owed nothing. A runs `sminos say --in desk-integration "a note"`: no
   inbox gains a frame. A runs `sminos say "@desk-integration/<S> three"`:
   S is woken on `alpha` with no question to the endpoint (one owner's
   sessions of one machine).
5. X, in no channel, runs `sminos say --in desk-integration "@<A> five"`:
   recorded in `desk-integration`, with a copy in X's project and one line
   saying that X is no member, that replies come to it directly, and
   `sminos channel add`. A's inbox holds the frame, which says its sender is
   not in the channel and whose reply line names X in X's project; A's
   reply by that line lies in X's project's log and reaches X, and the
   channel's log holds only X's message of the two. X runs `sminos say
   "@desk-integration/<B> six"` and `sminos say --in desk-integration
   "@all seven"`: each is delivered after a pass to whom it names, and
   nothing of the channel's log, the `@all` of step 4 among it, was ever
   pushed to X. A runs `sminos say "@<B's alias> four"`: recorded in B's
   project's log with a copy in A's, as a message to another project is.
6. A runs `sminos channel remove desk-integration` (itself). B runs the
   reply line of step 2's frame: recorded in A's project's log, not the
   channel's, with one line saying that A is not in the channel now and
   was sent to directly; A receives it. A runs `sminos channel add
   desk-integration`, and B's line run again is recorded in the channel's
   log and reaches A after a pass. A runs `sminos channel remove
   desk-integration <B>`, and after a pass `sminos say
   "@desk-integration/<B's alias> x"` is refused: no member of the channel
   answers that name, and the refusal says where B is.
7. A runs `sminos channel env add desk-integration gamma`. At a terminal
   on `gamma`:
   `sminos say --notice devcloud --in desk-integration "lease ends"`.
   It is recorded; after a pass `sminos chat desk-integration` on `alpha`
   shows it from `devcloud@gamma`, and no session was prompted.
8. At a terminal on `alpha`, `sminos channel lead desk-integration <S>`
   with a typed yes, then `sminos say --in desk-integration "do it"`: the
   event names S in `to`, the stand-in was asked one `words?` under the
   channel's id and answered `words`, and S received it as a person's
   words are handed to a session, never as a peer's frame. The same verb
   run as A is refused.
9. The checker passes over the three stand-ins and the three stores with
   this child's rules: under the channel's id nothing went up but
   `events`, `reach?` and `words?` frames of the kinds §8 allows, no
   `delivery`, no word to a human, no event there carries `copy`, and
   `from_project` is carried by X's three messages alone.

Then B9 on the final head, for what changed after M4: steps 2 to 4 of
M4's pass are run again if any of `S/sminos.py`'s delivery operation,
`S/sminos_channels.py`'s `owing` or the wake changed since, and reported
as not run, with the reason, otherwise.

**M9, the TECH-DEBT rows.** Each row whose trigger names this child, and
what becomes of it:

| Row | Becomes |
|---|---|
| `chat <channel>`, `list <channel>` and a target qualified by a channel are refused | removed: M1 and M3 |
| A return that keeps where a membership began from before the end | kept, saying that this child pushes once what the channel gained meanwhile, in those two cases alone, and where it is tested (M2's row D10) |
| No lock holds a channel's log still | kept, saying which side of the boundary each case falls (M2, M5) |
| The message path trusts a machine name | narrowed to a project's log: a channel's is held to what the machine appended (M2) |
| A roster can list a thread's obsolete row for a moment | kept or promoted on M4's figures (the holder's call); it now says that addressing through the roster reads the same row |
| A remote-only add after the last holder left… | kept unchanged: this child places nothing through the roster |
| The uplink's thread can block in `finish_thread` | kept unchanged: this child adds no caller that reads a view on the consumer thread (M5's bound), and a message's upload meets `senders_before` as a request's does |
| A malformed answer to a message's reach ask is asked again at the reply's speed | kept for a project's message; a channel's takes the requests' rule (M5) |
| The idle gate's margin was spent without a note | answered by M1's figure and the holder's word on it (open point 8) |
| A peer message's reply line still models a double-quoted body… | closed or rewritten by M8, as its evaluation decides |
| An addressed event that names a session its thread has left is not pushed; A held event does not follow a continuation | kept for a project's log, saying that a channel's debt is carried (§3) and that `_owed`'s lineage argument is the mechanism a project would take |

## Interfaces and Dependencies

CH1's names (its plan's Interfaces §1 to §9) are consumed as built and not
repeated. A name below that an executor finds unbuildable as stated is
changed here, by the controller, with a dated line in the Decision Log,
before the milestone that exposes it closes.

### §1. Names through a channel

In `S/sminos_channels.py`:

    def shared_rows(session) -> [(Project, Member)]
        # the rows of the rosters of the channels the thread whose current session this is holds (channels_of),
        # each thread once though it is in two of them; [] with no roster read when the record holds none
    def reach_in(channel, name, short="") -> ("in" | "out", Project, Member)
        # "in": the one row of roster(channel) the name reaches, with its own project. "out": the id rule's
        # second row below, with that thread's row in its own project; its caller says what that means.
        # Every other miss exits 4, in §2's words.
        #   with `short`: a row whose alias is `name` and whose session id begins with `short`
        #   a name in id form (a full id, or eight hex digits): the id rule below
        #   else an alias: the rows whose current alias it is, and only when there is none those that held it
        #   before (current_first); several are refused, each as alias#short (candidate_labels)

**A name in id form, through a channel.** It names a session (or a thread
id). The threads that have had it are read from every project's view this
reader reads, rows that have ended included (`View.ended`), by what names
a row besides its alias (`former_ids`: its session, the sessions it
continues, its thread's other sessions, its thread's id).

| The id has been | Answer |
|---|---|
| one thread's, and that thread has a row in the channel's roster | that row: its current session |
| one thread's, with no row in the roster | `out`: a verb's target is refused; a tag qualified by the channel sends to that thread directly, in its own project; with `--in` it is refused (§2) |
| more than one thread's | refused as ambiguous, the roster's rows among them each as `alias#short`; it reaches none |
| no thread's that this reader can read | `no member <name> in channel <channel>` |

Reason: a member's frame's reply line names its sender by a session's
short, a session id can come to be another thread's (T1's row 15), and C5
binds that a reply to a member that has left goes to that thread and is
never given to another member that came to hold the sender's session id.
The current-before-former order `match_members` applies in a project
would give it exactly that member.

`find_target` (M1) and the door (`speak`, M3) call `reach_in` for a
qualifier that `names_channel` answers; `_resolve_tag`'s branch for a bare
name calls `shared_rows`. Nothing else reads a roster to address.

### §2. The doors, the event and the sentences

    sminos say --in <channel> <text>            # any thread, or a person at a terminal; the tags are looked up in the channel
    sminos say "@<channel>/<name> …"            # the same, the channel named by the tag
    sminos chat <channel> [-n N] [--since TS] [--kind K] [--json]
    sminos list <channel>                       # as list --channel <channel>

In `S/sminos_channels.py`:

    def speak(channel, a, session, tags) -> None
        # the door (M3; its arguments are M3's to shape, what it decides and in what order is the contract):
        # before anything is appended, that the machine's enrollment carries the channel's log (CH1's
        # refusal for a verb that writes); who writes and how (below); the recipients; that every tag is in
        # this channel. Then it appends and delivers as cmd_say does for a project. `session` "" for a
        # person at a terminal.

**Who writes, and how.** Any session, and a person at a terminal, on a
machine where the channel is registered (`find_channel`; a name no log
answers to is the unknown name it is today) and whose enrollment carries
its log. The door reads once whether the sender is a member, from its own
machine's record (`channels_of(<the session>)` holds the channel), and
that decides the event's shape and nothing else:

| The sender | The event | Besides |
|---|---|---|
| a member | no `from_project`; no copy | nothing |
| a session that is no member | `from_project`: the sender's own project (`caller_project`), as `cmd_say` sets it for another project's log | its copy in that project's log (`record_copy`, unchanged: the copy names the channel's event and is owed to no one), and one line to the sender, below |
| a person at a terminal, a machine's notice | no `from_project`; no copy (the operator writes none today) | nothing; the pool is not consulted (open point 2) |

A tag is looked up in the channel's roster whoever sends (`reach_in`),
`@all` is the roster's live rows, and an untagged post names no one.
Delivery, the wire, the lead and the readers never read a sender's
membership: they tell the two shapes apart by the event's `from_project`.

**The event** is the one `cmd_say` writes today, in the channel's log:

| Kind, writer | Fields |
|---|---|
| `say`; the session's writer in the channel's log, or its audience stream as `streams_for` splits it | `from`: the sender's alias; `to`: `[{"session", "alias"}, …]`, the session each row holds now, or `"*"` for an untagged post; `text`; `wake: true` for an `@all`; `from_project`: the sender's project's id, for a sender that is no member and for no other |
| `human`; the machine's human writer, or its stream | the same, `from: "human"`; `notice`: the program, for a notice |

Never `copy` in a channel's log. The one second event is a non-member's
copy, in its own project's log, as `record_copy` writes it today.

**The sentences that are decisions** (`%s` as given; each refusal leaves
every log as it was):

| Where | Exit | Words |
|---|---|---|
| a session that is no member says into the channel (after its `recorded …` line) | 0 | `you are not in %s: replies to this come to you directly, in %s. sminos channel add %s places you in it` |
| a name in the channel's roster that no member answers (`--in` or a qualified tag) | 4 | `no member %s in channel %s`, then, when the name answers elsewhere, `; elsewhere: <each as the name that reaches it>` and, with `--in`, `Drop --in to reach it in its own project` |
| a tag qualified by the channel names by id a thread that is not in it now (the reply line of an old frame) | 0 | before its `recorded …` line: `%s is not in %s now: sent to it directly, in %s` |
| the same tag with `--in <channel>` | 4 | `%s is not in %s now (it left the channel, or its thread ended): nothing was recorded. Drop --in to reach it in its own project` |
| a verb's target named through a channel that is not in it now (`find_target`, M1) | 4 | `'%s' names a thread through %s, which it is not in now: name it by its own name (<alias>#<short> or <short>)` |
| an id more than one thread has had | 4 | `ambiguous %s in %s: the session it names has been more than one thread's: <each as alias#short> — name the one you mean` |
| `--in <channel>` with a tag qualified by another log, or tags that name a channel and another log | 4 | `one message, one log: the tags name %s` (among projects alone the sentence stays today's, `one message, one project: …`) |
| a selector that names a channel (`say --project <channel>`) | 1 | `%s is a channel, and a selector names projects: sminos say --in %s "@all …" reaches its live members` |
| `chat --host <channel>` | 1 | `%s is a channel, and what a session sends its human is in its own project's log: sminos chat --host <project>` |
| a say into a channel the machine's enrollment does not carry | 1 | CH1's sentence (`_refuse_uncarried`), unchanged |
| a recipient of this machine whose record does not hold the channel though a roster's row does | — | its line reads `<alias>: recorded (it is not in <channel> on its machine now: not delivered)` |

**CH1's refusals, and what takes the place of each:**

| CH1 refuses | Where | From this child on |
|---|---|---|
| `say --in <channel>` | `cmd_say`, by `channel_say_refusal` | `speak` (M3) |
| a tag `@<channel>/<name>` | `resolve_tags`, before any member is looked up, and `_resolve_tag` | `speak`, which gives the name to `reach_in` (M3) |
| a say whose destination is a channel however reached (an older copy's rooted registration, whose directory a caller stands in) | `cmd_say`, after `resolve_tags` | refused still, naming `--in`: a channel is spoken in only by naming it, never by standing in a directory (`%s is a channel, and no directory's project: say --in %s to speak in it`, exit 1) |
| the unquoted `@<name#short>/<alias>` | `cmd_say`, by `shortened_channel_qualifier` | refused still: `%s opens no tag (a tag's qualifier takes no #): nothing was recorded. Say it as sminos say --in %s "@<alias> …", or qualify the tag with the channel's id` (exit 1) |
| a selector that names a channel | `cmd_say`, the same loop as `--in` | refused still, in the sentence above |
| a verb's target `<channel>/<alias>` | `find_target` | `reach_in` (M1) |
| a channel where a project is asked for (`chat`, `list <name>`, `--project`) | `find_project`, `project_tiers` | refused still by both; `cmd_chat` and `cmd_list` branch to the channel before they ask for a project (M3) |
| `join <channel>`, a `.smns` naming a channel | `channel_join_refusal`, `_smns_decision` | unchanged |

Three of CH1's sentences go: `channel_say_refusal`, `find_target`'s
"names a thread through a channel…", and the help's "nothing is said in
one in this version". A recipient's line is otherwise what
`deliver_say` prints today (`sent`, `sent (woken)`, T2's held lines,
`recorded (on <machine>)`, the endpoint's `recorded; the endpoint decides
its delivery`), and `say --exit-held` reads it as today.

### §3. What a channel owes a thread

In `S/sminos_channels.py`:

    class Owing(NamedTuple):
        channel: Project
        thread: str           # the thread the debt is owed to
        session: str          # its current session: the key of the delivery record, and the process pushed to
        project: Project      # the thread's own project
        member: Member        # its row there: what the delivery operation takes as `member`
        also: tuple           # the lineage of `session`, less any session another record holds as current

    def owing(channel, record, member=None, lock_until=None) -> Owing | None
        # None when the record has ended, holds no session, does not hold the channel, its session is lane B,
        # or its session has no row in a project now; None too, nothing done, while the record is there and
        # cannot be read. `member`: the thread's row in its own project when the caller holds it (a roster's
        # row; in the uplink the plane's, which reads no view); else it is read from that project's view.
        # Then the entry settlement below, under the delivery lock of (channel, session), taken for it and
        # let go (LockBusy past `lock_until`; with none it waits, for a command and the daemon), and the
        # Owing.
    def still_owed(o, e) -> bool
        # the last check, on files as they are and under the delivery lock its caller holds: the record's
        # current session is o.session, it has not ended, its set holds the channel, e's seq is past the
        # boundary for e's writer, and e names o.session or one of o.also
    def deliver(channel, lock_until=None) -> (int, [alias])
        # the channel's delivery pass (the daemon's channel pass, after carry_due): for each thread of this
        # machine that holds the channel (sminos_threads.set_holders) with anything addressed to its session
        # or lineage, owing(), then sminos.deliver_next(channel, o.member, owing=o) when something is owed
    def owed_here(channel) -> [(Owing, [event])]     # what `daemon owed` counts for a channel: reads, no write

In `S/sminos.py`, one argument each, whose absence is today's behaviour:

    def _owed(events, session, record, also=())      # also: an event that names one of them is the session's
    def deliver_next(project, member, due=False, owing=None)
    def deliver_verdict(project, member, event, verdict, owing=None, lock_until=None)
    def deliver_reach(project, member, event, verdict, reason=None, owing=None, lock_until=None)
    def words_due(project, members, owing=None)      # owing: {session: Owing} for a channel's pass
    def reach_due(project, members, owing=None)
    def holder_push(project, member, session, e, events, cursor, words=None, retry=False, due=False, owing=None)

With `owing` (the log is a channel's), and only then:

- what is owed is `_owed(events, session, record, also=owing.also)`;
- an event is from outside this machine when it is not
  `appended_here(channel, e)`, and the same-owner shortcut
  (`ReachGate.needs`) holds only for one that is;
- the frame of an event that carries `from_project` says its sender is
  outside the channel: `frame_of` puts ` (not in <the channel's name>)`
  first after the sender's alias, before `sender_labels`' clause, where a
  reader of a frame already expects a label (an alias is read to its first
  `,` or ` (`); its reply line is `sminos_control._routes`' today, which
  names `from_project`;
- `holder_push` makes the last check first, and `wake_member` again once
  the wake's hold is taken and before a process is started: an event that
  fails it settles `recorded`, with nothing pushed, woken or asked;
- no outcome is kept for the uplink (`sminos_outcomes.record` keeps none
  for a channel);
- `lock_until` bounds the delivery lock: past it nothing is done and the
  answer is None, the event still owed.

The three that push (`deliver_next`, `deliver_verdict`, `deliver_reach`)
refuse a channel's log given without `owing` (an assertion): the default
would push what precedes a membership. The two passes are reached for a
channel only through `Link.ask_messages`, and gain no check a project
would pay for. `_write_receipts` receipts a `say` appended to a channel's
log, beside the kinds of `RECEIPTED_KINDS`.

**The entry settlement.** Under the delivery lock of (channel, session),
before anything is chosen: for each writer, the session's delivery record
is settled up to the larger of the boundary (`began_of(thread, channel)`)
and what the delivery record of each session of `also` has settled for
that writer. One write, and none when nothing lies below. It is the only
thing this child writes for a membership, it only ever raises a settled
position, and a mark or a count at or below a position it settles goes
with it, as `delivered_settle` drops them. So every later reader of that
delivery record (the passes, a late word, `daemon owed`) reads the
boundary without knowing of it. A delivery record that cannot be read
reads as empty, as it does today (the TECH-DEBT row "An unreadable
delivery record is replaced as though empty").

**The transitions.** What the record's own operation writes is CH1's and
T1's and is not changed; the last column is this child's, and each row is
a test of M2 staged through the transition itself.

| # | What happens to the thread T in channel C | The record (CH1, T1) | What delivery does |
|---|---|---|---|
| D1 | T enters C (its own add, a request honoured) | `began[C]`: the log's positions now | the next `owing` settles up to them: what this machine held then is never pushed |
| D2 | a message addressed to T arrives while it is a member | none | live: pushed and settled; stopped and woken: T2's wake, then pushed; stopped and not woken: held, owed, marked for T; for the live alone: `recorded` for a stopped T |
| D3 | T is reopened, or woken, while still a member | none | what was held is pushed once and settled |
| D4 | T is removed from C | `began[C]` dropped | `owing` is None: nothing delivered, asked or settled for C; what was held stays unsettled and is never pushed |
| D5 | T is removed and added again | a new `began[C]` | as D1: what the machine held at the second add, D4's held mail included, is settled unpushed; what it imports afterwards is owed, whenever it was written |
| D6 | T's session is handed off, s to s′ | `current`, `sessions`; `began` untouched | `owing` for s′ has s in `also`: the entry settlement takes over what s's record settled, and what C owed s past that, held mail included, is pushed to s′ once; a message that names s after the hand-off is s′'s too |
| D7 | T absorbs a provisional thread that had entered C | `_merge_absorbed`: `began[C]` the absorbed record's | as D6, from the boundary brought |
| D8 | T is refilled (a new occupant) | `current`; `began` untouched | the lineage is empty: nothing that names the displaced occupant is pushed to the new one; what names the new one is owed |
| D9 | T ends | T1's; the three keys untouched | `owing` is None while it is ended: nothing delivered or settled |
| D10 | T returns | `began` anew for every channel; kept from before the end over a channel whose log cannot be read, and by a return an older copy makes | as D1: what arrived while it was ended is settled unpushed; in the two kept cases it lies past the boundary and is pushed once (Y3) |
| D11 | a session T had runs again as a thread of its own, T′ | a new record, in no channel | the session leaves T's `also` (another record's current one); T′ is owed nothing in C until it enters, and then from its own boundary |
| D12 | T's session turns lane B, or its record cannot be read | — | `owing` is None; unreadable: nothing is done this pass and nothing settled |

The linearization point of every row's delivery is the delivery lock of
(C, T's current session): the entry settlement is made under it, and
then, under it again (`deliver_next` takes it itself), the choice, the
last check, the push and the settlement. The last check reads the
boundary afresh, so a removal and an add that land between the two
takings are seen. A removal is under
another lock (the wake lock, then the record's); a wake's hold is that
same wake lock, kept through its push, so for a woken thread no removal
lands between the last check and the frame's handoff. For a live push
that window is the base's and is accepted (Constraints). Nothing is
written at an end, at a hand-off or at a removal for a channel: an older
finisher that carries one of those entries does all there is to do.

A project's log is untouched by all of it: `hand_off` still settles what
the project owed the session it leaves (`settle=old`), and an event there
that names a session its thread has left is still not pushed (the owner's
ruling). `also` is the second half of that row's sized fix; taking it for
projects would add a lineage lookup to `deliver_owed`'s loop over every
member every tick, which the idle budget cannot take unmeasured, and would
change what a hand-off's settlement means to an older finisher (open point
9).

### §4. The wire

Nothing is added to RL10: no frame type, no field, no capability. What
this child sends under a channel's id that CH1 did not, each in today's
shape:

| Frame | When | What it carries |
|---|---|---|
| `events` (up) | the upload of a channel's log, as CH1's, from a machine that holds a member (no `follow`) and from one that holds none (`follow`) alike | a `say` (with `from_project` when its sender is no member), a `human` (with `notice` for a notice), a `channel-lead`, signed under the channel's id; preceded, under its own project, by the member frame of each sender that is a member of a project now |
| `reach? {id, project, session, event}` | the uplink's pass, for a message a push would hand over as a peer's frame | `project`: the channel's id; `session`: the recipient thread's current session, whatever session the event's `to` names; `event`: the message as stored, `verified` left out |
| `words? {id, project, session, event}` | the same pass, for a `human` event the endpoint's word decides (`words_route` `ask`) | the same |

and receives the answers `reach {verdict: deliver | refuse, reason}` and
`words {verdict: words | peer | refuse}`. A wake is not on the wire: the
recipient's own machine starts its stopped thread, on its own endpoint's
word about the message, as it does for a project's. Not sent under a
channel's id, now as before: `member`, any `session` message (presence, `machine`,
`host`, `raised`, `settled`, and `delivery`), `pending`.

In `S/sminos_uplink.py`:

    def Link.ask_messages(self) -> None
        # behind ask_words' project loop and beside ask_requests, only while self.channels is not empty and
        # the welcome listed `channels`: first each word kept (below) carried out, then for each open
        # channel the Owing of each thread of this machine in it (sminos_channels.owing, lock tried),
        # sminos.words_due and sminos.reach_due given them, and one ask queued for each event due
    Link.message_words: {key: (kind, verdict, reason, event_key, deadline)}
        # a word kept by on_words / on_reach for a channel's message, under the ask's key
        # (channel id, session, writer); consumed once by the next ask_messages

- An ask is held under `(channel id, session, writer)` with the event's key
  (`sminos_channels.event_key`'s shape: the channel, the writer, the seq,
  the event's hash) and marked a channel's; it holds no member and no
  membership.
- Before an ask goes, `Link.member_on_lane(<the thread's own project>,
  <its session>)` holds for the recipient, and for the sender too when it
  is a session of this machine that is a member of a project now; else the
  ask waits for the plane's next read. The recipient's row for `owing` is
  the plane's (`Plane.member_rows`), never a view's.
- An upload of a message meets `Link.senders_before` as a request's does,
  unchanged: for a sender whose frame is already on the lane under its own
  project it reads no view.
- `on_words` and `on_reach`, for an ask marked a channel's, keep the word
  and mark the pass due; they carry out nothing. A reply that names no
  verdict consumes nothing: its ask stays held to its deadline.
- The pass carries a kept word out through `sminos_channels.owing(channel,
  <the record of the thread whose current session the ask named>,
  lock_until=<now>)` and then `deliver_reach` or `deliver_verdict` with it
  and the same bound. None from `owing` (removed, ended, the session
  another's): the word is dropped, nothing done. A busy lock: the word is
  kept until its deadline (`REACH_WAIT`, `WORDS_WAIT` from the answer),
  then dropped, and the event, still owed, is asked about again at the
  ordinary interval. A `peer` word on a person's message, where the
  endpoint decides reach, queues the `reach?` about the same event, as
  `ask_peer` does.
- A session this machine holds is asked about nothing (`queue_asks`, as
  for a project).

**Why a channel's outcomes stay on the machine.** For a project, the
outcome of an outside event's delivery is kept (`sminos_outcomes.record`)
and uploaded as a `session` message of kind `delivery` under the log's
id. Under a channel's id that is a publication C1 forbids, MAWS draws
nothing from it for a channel, and no sminos reads one. So none is kept
for a channel. What a sender on another machine reads is what it reads
today for any thread there: `recorded (on <machine>)`, or that machine's
published hold.

**What MAWS's endpoint and hub do with these.** Confirmed by MAWS's
architect on 2026-11-22 against its master `fcc992514`, with no change to
MAWS:

- An upload: the endpoint finds the writer's member by session alone,
  attests the event from that frame, takes its audience by session, and
  signs it over the org and the channel's id. Nothing at the endpoint, at
  the hub or in a view assumes that the writer of an event under a
  channel's id is a member of that channel.
- `reach?` is decided as for a request: the recipient by the frame's
  `session` alone, the sender verified under the frame's `project`.
  `words?` finds its recipient by session too; `project` there is only the
  scope of its ledger, its verification and its index.
- `known` lists a channel only for a machine that holds a member, so the
  machine of a sender that is no member does not publish it. Relaying is
  not gated by that: acknowledgements and what is written under the
  channel reach a machine for as long as it keeps the channel open.
- MAWS's views draw no channel's log and read no `from_project`; a copy in
  the sender's own project's log is drawn as any message there.

As read in its source by this plan's author and not yet confirmed (the
stand-in is held to it; Dependencies):

- `words?`: no member held for the recipient, `peer`. This machine's own
  `<name>/human`: `words` when the recipient's owners include an owner of
  the machine, else `peer`; `refuse` when its ledger holds another body at
  that position. Another machine's `human`: `peer` at best. A notice:
  `peer` wherever the word would be `words`.
- `reach?`: no member or no record held for the recipient, no answer;
  `deliver`, or `refuse` with `not-reachable` or `unverified`. Nothing
  reads the event's kind, or checks the frame's `session` against the
  event's `to`.
- The hub, at an upload: an event whose audience does not fit a
  recipient's is withheld (`not-reachable`), and one with `to: "*"` names
  no one.

### §5. The lead

| Kind | Log, writer | Fields |
|---|---|---|
| `channel-lead` | the channel's log; the machine's human writer, plain | `thread`: the lead's thread id, or `null` for none. Nothing else: no `to`, no `session` |

In `S/sminos_channels.py`:

    def is_lead(e) -> bool
        # kind channel-lead; its base writer `<machine>/human` with a machine's name by the notice's grammar
        # (sminos.NOTICE_MACHINE_RE, never hub or legacy); no `notice`; `thread` a non-empty string or None
    def lead_of(channel, rows=None) -> (Project, Member) | None
        # the last is_lead event of the merged log decides, whoever wrote the ones before it: None for a
        # `thread` of None; else the roster's row whose thread it is; None when no row is (it ended, left, or
        # this reader may not read it). An earlier lead never comes back in its place.

    sminos channel lead <channel> <thread|none>

Refused inside a session; refused without the capability or where the
enrollment does not carry the channel, as CH1's verbs that write; refused
for a thread that has no row in the roster; then `confirmed` at the
terminal. Exit 0 once the event is appended, 1 for a refusal, 4 for a
name that is unknown or ambiguous.

| Where | Exit | Words |
|---|---|---|
| inside a session | 1 | `channel lead is for a person at a terminal, and this runs inside a session: nothing was written. Report it to your human instead` |
| no terminal | 1 | `naming a channel's lead needs its owner at a terminal to confirm it, and this has none: nothing was written` |
| the prompt | — | `Make %s the lead of %s? A message you type into %s with no tag, on this machine, is then addressed to it. Confirm? [y/N] ` (for `none`: `Clear the lead of %s? Confirm? [y/N] `) |
| not confirmed | 1 | `not confirmed: nothing was written` |
| the target is not in the channel | 1 | `%s is not in %s: sminos channel add %s <thread> places it first` |
| done | 0 | `%s leads %s`; for a lead on another machine, then `(on <machine>: a message you type here reaches it as a peer's, not as its human's words)`; `%s has no lead` |

**The post.** In `speak`, for a call with no session, no `--notice` and
no tag: when `lead_of(channel)` answers a row, the event's `to` is that
row's session and alias, and it is delivered as any addressed event is.
Every other untagged post is untagged. `channel show` prints a line
`lead  <alias>#<short>` after its heading, and `--json` a key `lead` (the
thread id), each only while a lead is in effect.

### §6. What reads a channel's messages

Lifting "nothing is said in a channel" changes what each reader of a
channel's log meets there. Every reader, and what it does with a `say` or
a `human` in a channel's log from this child on:

| Reader | Does |
|---|---|
| `view_of`, `_reconcile_channel`, `Plane.refresh` | nothing: a message is no membership event; a channel's view still has no member |
| `sminos_daemon.tick` (a project's) | not run for a channel, as before |
| `sminos_daemon.channel_pass` | delivers it (`sminos_channels.deliver`, M2), after the view and `carry_due` |
| `HubLog.deliver` (an import) | nothing for a channel, as before; the import's nudge brings the channel pass |
| `Link.ask_words` | its project loop asks nothing for a channel, as before; `ask_messages` asks (M5) |
| `Link.upload`, `senders_before` | uploads it under the channel's id, senders' frames first (CH1's path) |
| `Link.deliveries`, the outbox | nothing: no outcome is kept for a channel |
| `HubLog.show_notices` | tells the sending session of this machine when the hub withheld its message, as for a project (keyed by session; no change) |
| `outstanding` | unchanged: it reads requests alone |
| `sminos_channels.requests_of`, `pool`, `answers` | skip it (they read their own kinds) |
| `sminos_daemon.owed_in` (`daemon owed`) | counts what `owed_here` gives for a channel (M2) |
| `deliver_say` | the sender's own delivery (M3) |
| `record_copy` | keeps a non-member's copy in its own project's log, as for a message to another project (no change); a member's say calls it not |
| `cmd_chat` | reads it through `sminos_channels.chat` (M3) |
| `frame_of`, `holder_wake`, `frame_landed` | name the channel by its name, as they name a project; `frame_of` adds §3's clause for an event that carries `from_project` (M2) |
| `sminos_control._routes` | the reply line names the event's `from_project` where it carries one, else the log it lies in, the channel (no change) |
| `Link.may_leave` | does not let a followed channel go while an event this machine appended to it has not gone up (M5) |
| `append_host`, `export_live`, `close_questions` | never see a channel: a session's project is never one (no change; B7's tests) |
| `roster_text` (after a compaction or a resume) | reads the channels the thread holds (M7) |
| the manager's `OwnerWords` | reads the channels known on the machine, keyed by the log's name (M7) |
| a copy on 1.54.0 | stores it, delivers nothing, refuses to say; its `channel show` and its roster are unmoved |
| a copy from before CH | takes the channel for a project with no member: delivers nothing, settles nothing |

In `S/sminos_channels.py`:

    def chat(channel, a, session) -> None
        # cmd_chat's body over a channel's log: the channel's own view first (view_of, which reconciles a
        # channel as a channel) and never sminos.reconcile; the window, the cursor of (channel, session) and
        # the lines as cmd_chat makes them, a line whose event carries `from_project` with §3's clause after
        # its sender; `--host` refused (§2). Any reader that can read the log may: a channel bounds no one's
        # reach.

**The cursor follows the thread.** A hand-off carries a project's chat
cursor in its journal step (`carry_hand_off`), which an older finisher
also runs and which knows no channel. For a channel nothing is carried:
where the session holds no cursor under the channel's log, `chat` and the
frame's unread count (`frame_of`, through `owing`) read the newest cursor
of its lineage there. No write at the hand-off.

**The exchanges after a compaction or a resume** (M7): `roster_text` gives
`_roster_exchanges` the logs of `channels_of(session)` beside its two
projects. In a channel's log a `say` counts as today's does (addressed,
not for the live alone); "mine" is the session and its lineage; a peer is
keyed by its session alone, so that one met in a project and in a channel
is one row; `_roster_peer` finds its row in its own project
(`sminos_channels.roster`'s row for it, else as today) instead of
answering none for a channel.

**The manager's window** (M7): `M/manager_window.py`'s `frames` returns
the log's name it already parses from a chat frame's header, and
`OwnerWords` holds each owner's event under `(log name, ref)`;
`corroborates` asks with the frame's log name. `M/manager.py` builds it
from the subscription's project's log and the logs of `known_channels`.

### §7. What sessions are taught

The wording is M8's evaluation's to settle; what each text must come to
say, and stop saying, is fixed here.

| Text | Comes to say | Stops saying |
|---|---|---|
| the guide (`guide_text`) | that the session is a thread; the channels it is in, by name, when it is in any (a line that is absent for a thread in none); `say --in <channel>` and `@<channel>/<alias>`; that a bare `@alias` reaches its project and the channels it shares | that a bare `@alias` reaches only its project |
| `sminos/skills/sminos/SKILL.md` | thread and channel as the parent's Terms have them; `channel create`, `add`, `remove`, `show`; speaking in a channel and the reply line that keeps a reply there; that a thread may say into a channel it is not in, that its answers then come to it directly, and that only members hear the channel; that adding wakes no one; `chat <channel>`; that `join` declares a project and a channel is never joined | `send` as a way to message a member (it stays as the script's verb, `--wait`); the project as the only unit |
| `references/spawn-preamble.md` | the same two forms for a channel, in the paragraph that teaches tags | nothing |
| `sminos/skills/manager/SKILL.md`, `references/digest-brief.md` | that a subscription may be named `<channel>/<alias>`; that an exchange may be a channel's, and how the window marks it | "project log" where a channel's is meant too |

The lines the suites pin verbatim, each changed in M8 only if its line
changes: in `T/test-guide.sh`, the guide's opening pair, the `list
--subagents` line, the heredoc line, and its loop of fragments (among
them `@<short>`, `@<project>/<alias>`, `join <project>`, `wakes no one`);
in `T/run-sminos-tests.sh`, the preamble's lines (`You are "researcher", a
member of the project "work", spawned by`, `only the tags that open a
message`, `@<project>/<alias>`, the three `sminos say` examples, `Your
task follows.` and the rest of that block); in `T/test-remote.sh` and
`T/test_threads_stopped.py`, one fragment of the guide's first line each.

**The reply line.** `reply_line` keeps its one line, its absolute path and
its first form, which the suites and the manager's `REPLY_LINE_RE` read
(`[To reply, run in Bash: <path> say "@<log id>/<short> <your reply>"]`).
If M8's scenario E4 fails on the baseline, the line becomes, still one
line and still closed by `]`:

    [To reply, run in Bash: <path> say "@<log id>/<short> <your reply>" — a reply with a backtick, a quote or a $ goes on stdin instead: <path> say - <<'EOF', its first words @<log id>/<short>]

and `T/test-broadcast.sh`, `T/test-address.sh`, `T/test-bridge-control.sh`
and `T/envelope_parity.py`, which take the command out of the line, are
changed to take its first form.

### §8. What the tests are built on

**The checker,** `T/channel_wire.py`. Its rules change, not only its
arguments:

    ALLOWED_SPOKEN = ALLOWED + ("say", "human", "channel-lead")    # what this child's suites pass as `allowed`

| Rule | From this child on |
|---|---|
| a `words?` under a channel's id | a breach unless its event's kind is `human` |
| a `reach?` under a channel's id | a breach unless its event's kind is `channel-request`, `say` or `human` |
| a `session` message under a channel's id | a breach as before, `delivery` named in the rule's own tests |
| a delivery record under a channel's log | allowed with `deliveries=False`, which every suite of this child that delivers passes |
| an event under a channel's id, on the wire or on disk, that carries `copy`; a `human` or a `channel-lead` there that carries `from_project` (a `say` may: a sender that is no member) | a breach (new) |
| a `channel-lead` that carries `to` or `session` | a breach (new) |
| `member`, `pending`, presence, `machine`, `host`, a `snapshots` answer with an event, a `retired` that undoes no older `joined`, `member.channels` out of shape, anything in a channel's host store | breaches as before |

Its own tests (`T/test_channels_wire.py`, class `Checker`) gain a case for
each new rule and each rule changed. M2 changes the disk rules, M3 the
kinds, M5 the wire rules, M6 the lead's.

**The stand-in** (`T/endpoint_standin.py`) answers `words?` and `reach?`
from its configuration today (`verdict`, `verdicts`, `reach_verdict`,
`reach_verdicts`). It gains what §4 reads of MAWS's endpoint for the two
questions under any project id: no answer to a `reach?`, and `peer` to a
`words?`, for a session it holds no member frame of; `peer` for a notice
where it would answer `words`. A test that needs a word late takes the
ask's id from the frames the stand-in kept and sends the answer itself, as
`T/test_channels_wire.py`'s `Asks` stages one after a hand-off.

**The engine** is T2's test engine (`T/wake_engine.py`): its `launches`,
`calls.log` and `inputs/<session>` are what shows a wake and the frame it
was woken with; a live session's inbox is `T/inbox_standin.py`.
`T/test-channels-machines.sh` runs a no-op engine stub today; this child's
cases there take the test engine as `T/test-notice-machines.sh` does. A
typed yes is given on a real controlling terminal, as `T/test_visibility.py`
gives one.

**The bench.** `T/bench_scale.py` gains `--channels N` (M4): N channels
registered, each with members drawn from the shape's threads across its
projects, statements written as the verbs write them; `verbs` then times
`list` by a member, `channel show` and a tagged `say` by a member, and
`run` reads the idle figures with those channels held. No gate reads it.

**Where each new file sits,** and the neighbour it is built like:
`test_channels_names.py` and `test_channels_say.py` load the CLI's modules
under a temporary home and drive the launcher, as `test_channels_roster.py`
does; `test_channels_delivery.py` is built like `T/test_wake_delivery.py`
(`Deliveries` over the test engine) with `test_channels_life.py`'s staging
of T1's transitions; `test_channels_lead.py` like `T/test_threads_owner.py`
for the terminal. All run in the `channels` part of
`T/run-sminos-tests.sh` (`run_channels`) and in no other; the older-copy
suite, the guide's and the manager's stay in the parts that run them
today.

### Dependencies

- MAWS's master with its child MW, as CH1's plan lists it. Nothing in this
  child's suites runs MAWS: the stand-in and the conformance replay stand
  for it. The replay, 121 lines at CH1's copy, shows none of this child's
  traffic until M5's copy.
- MAWS's two fixture cases (Constraints), at the commit and blob the
  holder passes on; M5 copies and replays them.
- **Open with MAWS's architect,** carried by the composite's holder. §4
  states what this child builds on; an answer that differs comes back to
  the holder before M5 is built on it.
  1. A delivery outcome under a channel's id (a `session` frame of kind
     `delivery` whose `project` is a channel). sminos sends none: a
     channel's outcomes stay on the recipient's machine (§4). Whether MAWS
     wants one, now or for the app's later channel view, and under which
     id.
  2. `words?` under a channel's id, the lines of §4 not yet confirmed:
     `peer`, not silence, for a recipient the endpoint holds no member of
     (which is why sminos sends that frame first); `words` only on the
     writing machine; `peer` for a notice. And a fixture case for it (a
     `human` under a channel, and a notice), which the two cases agreed do
     not hold.
  3. `reach?` where the frame's `session` is not among the event's `to`
     (the thread's current session, the event naming one it continues):
     that nothing checks the one against the other, for a message as for
     a request.
  4. `channel-lead`: a kind in a channel's log with `thread` and neither
     `to` nor `session`; that MAWS gives it no meaning and that the name is
     free.
  5. MAWS's own row on a `reach?` for an event imported with no local
     receipt (its tracker at `fcc992514`): when that field lands, a
     channel's messages take it as its requests do.
- Python's standard library alone, as every module of `S/` today.
- An engine and its credentials for M4 and M8's live scenarios; without
  them those are reported as not run.

## Surprises & Discoveries

None yet. What the reading for this plan found against the composite is
in the Decision Log's first entry, under "Where the composite and the
code differ".

## Decision Log

- 2026-11-22 — **The plan as written, and its verification.** Written by a
  session the composite's holder dispatched, against the code at `1a3c1ac5`
  (sminos 1.54.0), MAWS's master read at `fcc992514`, and the composite as
  three revisions left it during the writing: CH1's landing (`81ea8848`),
  its correction from a read against the code (`b8145982`, which this
  branch took by a fast-forward to `1a3c1ac5` that brought nothing else),
  and the owner's ruling that a thread that is no member may write into a
  channel (`59782bb8`, blob `8173f992`), which this plan builds and the
  branch does not hold yet. MAWS's architect answered that day, against
  its master `fcc992514`, that nothing there assumes a writer under a
  channel's id is a member, and agreed two fixture cases (§4,
  Dependencies). *Verification:* this plan is reviewed for buildability by
  `doperpowers:adversarial-reviewer`, dispatched by the holder, before M1;
  each milestone through doperpowers:review-code, three reviews at most
  (the owner's bound), at the medium rung, and at the high rung for M2 and
  M5 (the delivery operation; the wire); M5's review reads M2 to M5 as one
  range; the range M1 to M7 by the holder's panel at the frontier, with the
  lenses Plan of Work gives; and the panel on the branch at the end, the
  holder's.
  - *Decided by this plan, where the composite does not* (each a technical
    consequence; the holder folds them into the composite's Decision Log
    or overturns them here).
    1. Delivery in a channel reads this machine's thread records and the
       channel's log, never a roster, and no tick reads a roster. The
       roster's new readers are commands: a verb's target, a tag, a
       sender's own delivery line. *Alternative: the channel's pass reads
       the roster for its local rows.* It lost to the idle budget, and to
       C1: a row is what a log states, the record is what the machine
       holds.
    2. One delivery operation, with `owing`; a channel's debt is kept in
       the delivery record of the channel's log and the thread's current
       session. *Alternative: a pass of its own for channels.* It lost
       because the operation's guarantees (a held event, a wake's hold, a
       receipt, a revocation) would each be built a second time.
    3. The boundary is applied by the entry settlement, under the delivery
       lock, the first time a session is delivered to after a membership
       begins, returns or changes session; nothing is written for a channel
       at an end, a hand-off or a removal. C5's "settled at its end" is met
       by the return's `began` and that settlement. *Alternative: a floor
       passed to every reader.* It lost because a reader that forgot it
       would push what precedes a membership; a settled position cannot be
       forgotten. *Alternative: a step in the journal at each change.* It
       lost, as in CH1's plan: an older finisher skips it.
    4. A channel's debt is carried across a hand-off by reading, for the
       current session, the events that name a session it continues
       (`also`): what was queued before the hand-off and what names the
       stale session after it are both the thread's, pushed once. Not
       across a refill, and not for a session another record now holds.
    5. The project's row (an addressed event that names a session its
       thread has left) is not closed here (§3, open point 9).
    6. The last check is in `holder_push`, and again under the wake's hold;
       the live push keeps the base's window.
    7. In a channel's log "this machine's own" is `appended_here` for a
       message, and a `say` there is receipted; a project's path is left.
    8. A channel's delivery outcomes stay on the machine (§4).
    9. `HubLog.deliver` is not changed. The composite's C1 notes that CH2
       changes it on purpose; delivery on an import is instead the daemon's
       channel pass (which the import already nudges) and the uplink's own
       pass, since `HubLog.deliver` runs on the consumer thread and takes
       the delivery lock without a bound.
    10. The uplink keeps a word and carries it out on its next pass, asking
        `owing` again; an ask holds no member. A reply that names no
        verdict to a channel's message ask takes the requests' rule.
    11. A name in id form through a channel resolves by the threads that
        have had the session, and reaches no one when more than one has
        (§1).
    12. With `--in` the tags are looked up in the channel alone; a message
        whose tags name a channel and another log is refused.
    13. Whether a sender is a member is read once, in the door, from its own
        machine's record, never from a roster; every later reader tells a
        member's message from an outsider's by `from_project` alone. A say
        into a channel needs the channel registered on the machine and its
        enrollment's carry of the log, and no capability: it is an event in
        a log, as a message into a project is.
    13a. A reply to a member that has left is sent directly only for a tag
        qualified by the channel (the reply line's form); with `--in`,
        which names the log outright, it is refused as every tag that
        resolves in another log is (B1). A verb's target through a channel
        that the thread is not in is refused. Where the session an old
        frame's line names has since been two threads', the reply is
        refused and names both: nothing in a reply line says which of them
        wrote the message, and C5 forbids giving it to the wrong one.
    13b. What a frame says of a sender outside the channel is a clause after
        its alias, ` (not in <channel>)`, and `chat <channel>` shows the
        same; a person's post and a notice carry no `from_project`.
    13c. A followed channel is not left while an event this machine
        appended to it has not been uploaded.
    14. `chat <channel>` is a read of its own, open to any reader of the
        log, its cursor read through the lineage; `list <channel>` is
        `list --channel`; `find_project` keeps refusing a channel
        everywhere else.
    15. `channel-lead` carries `thread` or `null` and nothing else, under a
        machine's plain human writer; the last such event decides, and a
        lead that is not in effect does not give way to an earlier one.
    16. The engine's collision name (E15): nothing is added; a roster lists
        what the row's own project lists.
    17. The exchanges after a compaction read the channels the thread holds
        now; the manager's window reads the channels known on the machine,
        keyed by the log's name.
    18. The checker gains two rules (an event under a channel's id with
        `copy`, or a `human` or a lead there with `from_project`; a lead
        with `to` or `session`) and changes two (`words?`, `reach?`).
    19. The scene on a real engine is a milestone in the middle (M4), and
        the roster's cost is measured by a bench at the fleet's shape, on a
        member's tagged `say` as well as on the listing.
    20. The taught surface stays in this child (M8); `send` leaves what is
        taught; sminos becomes 1.55.0; 1.54.0 joins the older-copy suite as
        its merge commit.
  - *Open points: the owner's, or the holder's, each built on the
    recommendation named, which is cheap to change before the merge.*
    1. A selector that names a channel (`say --project <channel>`).
       Recommended and built: refused, pointing at `--in <channel> "@all
       …"`. The other reading makes it `@all` in the channel.
    2. Who may write under the human writer. Recommended and built: any
       machine where the channel is registered and carried, with no check
       of the pool. The acceptance's "a channel whose pool holds the
       machine" is read as the scene to show, not as a condition.
    3. A verb's bare name (`send worker`, `status worker`, `retire
       worker`). Recommended and built: not widened to shared channels; a
       verb reaches a thread of another project through a channel only as
       `<channel>/<alias>`. C5 widens the tag; a wider `retire` is a
       behaviour a person would notice.
    4. The sentences of §2 and §5, and the clause a frame carries for a
       sender outside the channel (§3), are this plan's drafts of what a
       session and a person are told.
    5. A lead on another machine than the one the command runs on.
       Recommended and built: taken, and said.
    6. The reply line's words (§7): changed only if the evaluation shows
       sessions still breaking a reply on it.
    7. What the roster's cost (M4) is allowed to be before the deferred
       index of statements is promoted: the holder's call on the figures.
    8. The idle gate's limit (the TECH-DEBT row whose trigger is this
       child's first milestone). Recommended: not derived again here; this
       child adds nothing for a machine with no channel, and M1's figure is
       the row's answer.
    9. Whether the project's path takes the same carry (§3). Recommended:
       not in this child.
    10. `chat <channel>` by a thread that is not in the channel, and `list
        <channel>` as a positional. Recommended and built: both allowed.
    11. Nine milestones in one child. Recommended: kept whole (Plan of
        Work says why); M8 can still be cut at the frontier.
  - *Where the composite and the code differ,* for the holder (each is
    built as the code allows, and none stops a milestone):
    - C1's note that CH2 changes `HubLog.deliver` on purpose (decision 9).
    - Risks: "CH2 adds delivery from channels' logs and a roster read to
      the tick". No roster is read in a tick (decision 1).
    - C5's "settled at its end": `finish` settles only its entry's own
      project, and a step for a channel would be one an older finisher
      skips (decision 3).
    - The Grounding Baseline's "delivery state, the hold and the wake are
      keyed by (log, session) and need no new key": true of the keys. But
      every membership check inside delivery (`push_event`'s and
      `wake_member`'s `latest_membership(_own_events(project, session))`,
      `canonical_end`, `deliver_owed`'s loop over the view's members) reads
      the log the event is in, which for a channel says nothing: the last
      check is new work, as the fold's third correction found for a late
      word.
    - "What a roster costs to read when channels number in the tens", and
      the acceptance's "with thirty channels registered": `rosters` reads
      every project's view once, so its cost follows projects and members;
      thirty channels alone measure little (decision 19).
    - The child's inheritance says the checker is "called with the kinds
      CH2 adds and with `deliveries=False`": no argument allows a `words?`
      or a `reach?` about a message, so two of its rules change.
    - The acceptance's "a machine's notice is written into a channel whose
      pool holds the machine": no door reads the pool today, and none is
      added (open point 2).

## Outcomes & Retrospective

Pending — written at finish.
