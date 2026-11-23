# sminos channels, CH2 — speaking in a channel, and what sessions are taught: execution (2026-11-22)

> **Composite:** `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`,
> child **CH2** (Speaking in a channel, and what sessions are taught).
> **Parent pin:** branch `sminos-channels-ch2` at `f2c737f2` (`main` at
> `61b27ebe`: CH1 merged, the fold of CH1's landing as corrected against
> the code, the owner's ruling of 2026-11-22 on who may write into a
> channel, sminos 1.54.1, and the composite as the holder amended it on
> this plan's reads), that file's blob
> `940a5a0b1c63237f91cdb1e5824b2e0ca0cf5f15`. The design the composite is
> itself a child of,
> `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`
> ("the parent" below), is read as that same commit holds it, blob
> `b264d3fa845bc399a90f3f9d390a52e8c8bf3ec9`. The child's section in the
> composite is its spec; C1, C2 and C5 there are its design, binding where
> marked; Y1, Y2 and Y3 its contracts with CH1, which it consumes as built.
> This document carries the constraints and the milestones and nothing of
> the design. Read before M1: the composite whole, above all its Decision
> Log's last four entries ("CH1 landed", with "What CH2 inherits"; "The
> fold of CH1's landing, read against the code"; "The owner's ruling: a
> thread that is no member may write into a channel"; and "CH2's plan, its
> reads, and the holder's rulings on them"); the parent's Purpose (the
> rulings under "What it must not become"), Terms, D1, D3 (The timeline,
> The lead, Listing), D5, D6, D7, X1, X2, X4, X6, X8 and acceptance lines 2
> and 8; CH1's plan
> `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md`, its Interfaces
> §1 to §9 and its Outcomes; T1's plan
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
channel's log and reaches the sender's thread, whatever session that
thread runs in by then. `@desk-integration/worker` does the same without
`--in`, `@all` in a channel reaches its live members, and an untagged post
there is a record nobody is prompted for. A bare `@worker` reaches a
thread that shares only a channel with the sender, in that thread's own
project as a message to another project does today. A thread that is not
in the channel may say into it too: its message lies in the channel's log
as a message from another project lies in a project's, reaches the members
it names, is framed as from a thread outside the channel, and is answered
to its sender directly, in the sender's own project. Membership decides
who hears a channel: what its log owes is owed to a thread, by its thread
id, for as long as it is a member, so a message that reached the machine
before the thread entered, or while it was out, is never pushed to it,
and nothing there is ever pushed to a thread that is no member. The owner,
at a terminal, names a lead with `sminos channel lead`, and an untagged
message the owner then types into the channel is addressed to that
thread. `sminos chat desk-integration` reads the channel's conversation.
The session-start guide, the skill, the spawn preamble and the manager's
skill speak of threads and channels. A session that is in no channel sends
and prints what it did before. How to see it working is CH2's acceptance
in the composite (eleven items, numbered B1 to B11 here in the order its
section lists them), proved as Concrete Steps maps it.

## Progress

- [x] (2026-11-22) CH1 landed (`e0aa6d39`, sminos 1.54.0); the composite and the parent revised for it (`81ea8848`), corrected from a read against the code (`b8145982`), and revised for the owner's ruling that a thread that is no member may write into a channel (`59782bb8`).
- [x] (2026-11-22) This plan written against the code at `1a3c1ac5` (sminos 1.54.0), with MAWS's master read at `fcc992514` (`07fabf12`).
- [x] (2026-11-22) The plan's two reviews (a design read, eleven findings; a buildability read, fourteen), the holder's rulings on them, and this revision against the code at `bc528d6d` (sminos 1.54.1): a channel's message is owed to a thread by its thread id, nothing a channel's message causes on the uplink's consumer thread pushes or launches, and eleven milestones where there were nine (Decision Log, "The plan's two reviews").
- [x] (2026-11-22) The third read of the plan, over what the revision rewrote (fourteen P1, two P2), the holder's rulings on it, and this last revision before the build: no absorbed id is kept, no delivery over an open journal entry, a seat made again over a purged seat's session is that thread, the three paths the consumer thread still had are bounded or deferred, and what a verdict is good for is said (Decision Log, "The third read").
- [x] (2026-11-22) The fourth read, narrow, of what the third revision changed (six P1, four P2: "ready with the listed edits, no further design round"); all ten written in, and the header re-pinned to the branch with the composite's amendment merged (`f2c737f2`) (Decision Log, "The fourth read").
- [x] (2026-11-22) M1 — Names through a channel. `de0ed736`, fixes `6e2b7b90`, `78b07c42`; reviewed clean at the third review. Gates GREEN on `78b07c42`; sminos-idle 32,191; sminos-channels 1m37s.
- [x] (2026-11-22) M2 — What a channel owes a thread: the debt and its transitions. `a604658a`, fix `00e1b6b5`; two reviews at the high rung, the second's two findings (a corrupt record's shapes no writer emits) logged in TECH-DEBT. Gates GREEN on `00e1b6b5`; sminos-idle 32,766; sminos-channels 1m51s.
- [x] (2026-11-22) M3 — Pushing and waking from a channel's log. `af78de21`, `11482879`, fixes `b544d7f4`, `0c969840`, `dddf22b4`; three reviews at the high rung (the bound), the third's four fixes (`dddf22b4`) made after it and named to M6's review of M2 to M6. Gates GREEN on `dddf22b4`; sminos-idle 32,724; sminos-channels 2m08s.
- [x] (2026-11-22) M4 — Saying into a channel: the doors, the reply, the read. `d5c345bc`, fixes `934afd76`, `b9fc61a4`; reviewed clean at the third review (one Minor on a draft sentence's wording left for open point 4). Gates GREEN on `b9fc61a4`; sminos-idle 32,663; sminos-channels 2m06s.
- [x] (2026-11-22) M5 — The scene on a real engine. Run whole against `f775004d` (Claude Code 2.1.330, haiku, a scratch home): all four steps showed what they expect; no fault of M1 to M4, no code changed; the checker found nothing over the stand-in's frames and the store; every process stopped. Step 4's hand-off made as Surprises says.
- [x] (2026-11-22) M6 — Across machines: asking, and carrying out off the consumer thread. `5af6ab8c`, fixes `e7742001`, `d5b03b63`, `15198aa9`, `52d5241d`; reviewed with M2 to M6 as one range (three reviews on the medium rung, the bound), the third's fix (`52d5241d`) made after it and named to the frontier panel. Gates GREEN on `52d5241d`; sminos-idle 32,216; sminos-channels 3m15s of its 6m timeout.
- [ ] M7 — Held to MAWS's fixture, and what a channel costs.
- [ ] M8 — The lead, and whose words a post is.
- [ ] M9 — What reads a session's exchanges reads a channel's.
- [ ] The review of M1 to M9 as one range (the holder's), and its fixes.
- [ ] M10 — What sessions are taught, and its evaluation.
- [ ] M11 — Older copies, what is written beside the code, the version, and the acceptance.
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
  `S/sminos.py`. It is **addressed** when its `to` is a list of entries,
  **for the live alone** when it also carries `wake` (an `@all`), and
  **untagged** when its `to` is `"*"`. In a channel's log each entry of
  `to` **names a thread**: it carries the recipient's thread id in
  `thread`, beside the session that thread held when the message was
  written (§2).
- **The boundary** of a thread in a channel is where its membership began:
  `began_of(thread, channel)`, each writer's latest seq in the channel's
  log as this machine held it then.
- **The delivery record** of a thread in a channel is
  `projects/<channel id>/delivered/<thread id>.json`: for each writer, the
  seq up to which what the channel's log owed that thread is **settled**
  (pushed, or dropped for good), with its marks of what is held. Its lock,
  `delivered/<thread id>.lock`, is **the thread's delivery lock** there.
  In a project's log both are a session's, as today.
- **What a channel owes a thread** is the events of the channel's log that
  name the thread, past the boundary and not settled in that record
  (Interfaces §3). It is the thread's whatever session the thread holds.
- **The delivery operation** is the five functions of `S/sminos.py` every
  push goes through: `deliver_next` (one member's owed events, pushed and
  settled), `deliver_verdict` and `deliver_reach` (one event, on the
  endpoint's word), and the two passes that say what to ask the endpoint
  about, `words_due` and `reach_due`.
- **A kept word** is the endpoint's answer to a `reach?` or a `words?`
  about a channel's message, written by the uplink to a file under the
  channel's home and carried out by a deliverer in another process (§4).
- **An open entry** is a thread's record's `pending`: the journal entry of
  a transition that is not finished (T1). While a thread's record holds
  one, nothing of a channel is delivered to it or asked about for it.
- **The doors** are the places a `say` that names a channel is taken or
  refused: `cmd_say`, `resolve_tags`, `_resolve_tag`,
  `shortened_channel_qualifier`, and for a verb's target `find_target`.
- **The consumer thread** is the main thread of the uplink process
  (`serve_link` in `S/sminos_uplink.py`): it dispatches the endpoint's
  frames, delivers what they imported and runs the uplink's tick, so a
  wait there stops all three. The daemon (`sminos daemon run`) is another
  process, the uplink's parent.
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
  (where a message lands), each as the holder's rulings on this plan's
  reviews amend it (Decision Log). The parent's D3 (The timeline, The lead),
  D5, D6 and D7, and the rulings under "What it must not become". Contracts
  X1 (a field of the thread's record is added only through
  `S/sminos_threads.py`), X4 (the lead's kind), X6 (this child owns the
  rewrite of what sessions are taught), X8 (the reader of a machine's
  notice), and Y1, Y2 and Y3, which this child consumes: CH1's names (its
  plan's Interfaces §1 to §9) are read and not changed, and a signature
  this child must widen gains an argument whose absence is today's
  behaviour.
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
  carries no `from_project` and leaves no copy, so its frame's reply line
  names the channel and the reply lands there. A message from a thread that
  is no member follows today's rule for a message to another project, the
  channel's log in the place of the target's: `from_project` names the
  sender's own project, a copy lies in that project's log where today's
  rule leaves one (`record_copy`, its privacy guard untouched), and its
  frame's reply line names the sender, so the reply goes to it in its own
  project. A machine's human writer writes as a member does. Which of the
  two a message is, is decided once, where it is written, by the sender's
  own record; every reader after that tells them apart by the event's
  `from_project` and by nothing else, and no reader looks a sender up in a
  roster. A bare `@alias` never puts a message into a channel's log.
- **In a channel a message is owed to a thread, by its thread id** (the
  holder's ruling of 2026-11-22 on this plan's reviews). Each entry of a
  channel message's `to` carries the recipient's thread id; delivery reads
  that and never the entry's `session`, which stays for the endpoint (it is
  what gives the event its audience). There is one delivery record and one
  delivery lock for a thread in a channel, whatever session the thread
  holds: a hand-off, a refill, a return and a wake carry nothing and merge
  nothing, and a session that runs again as a thread with another id
  brings no debt with it. A thread's id is the thread: a seat's id is its
  first session's, and a seat made again over a session whose earlier seat
  was purged is that thread again, with its delivery record. And a thread
  that an absorption took into another is gone: what names its id
  afterwards is owed to no one. Reason: a session is the wrong key for
  something the design gives the thread, and every scheme that keyed the
  debt by session and then moved it lost or doubled mail at the move.
- **Nothing a channel's log holds is owed to a thread that is no member.**
  What a channel owes is read from this machine's thread records, so a
  thread whose record does not hold the channel is delivered nothing from
  it, whatever names it there.
- **Delivery in a channel is the thread's own machine's, from its thread
  records.** No tick, no pass and nothing the uplink runs reads a roster or
  a project's view to decide what a channel owes: it reads this machine's
  records (`sminos_threads.set_holders`, the record's `channels` and
  `began`) and the channel's log. The roster is read by commands:
  addressing (M1, M4), the listing and `channel show`. Reason: a roster
  reads every project's view, and the idle budget below has no room for it.
- **One delivery operation, one selection.** A channel's messages are
  pushed, held, woken for and settled by the five functions every project's
  are (Words), with one added argument (§3) whose absence is today's
  behaviour, call for call; no second implementation of the push, the hold,
  the wake or the settlement is written for channels. And what a channel
  owes a thread is chosen by one function (`sminos_channels.owed`), which
  the daemon's pass, a sender's own delivery, both ask loops, the carrying
  out of a kept word and `daemon owed` all call. Reason: T1's branch review
  found 82 defects in and around that operation, and this plan's own first
  form let one reader (the ask loops) choose by another rule than the rest.
- **What a channel owes is decided under the thread's delivery lock, on the
  record as it is then, and a pass that lost its session does nothing.**
  Which session the thread holds, whether its record holds an open entry,
  that the session's current record, read afresh, is this thread's and
  holds none either, whether the thread is in the channel, where its
  membership began, that its session's record is not one that is there
  and unreadable and is not lane B (one that is not there at all is lane
  A, as every reader takes it), and that the thread's own project is
  still the one the pass captured (by literal paths, a tie deciding for
  neither), are read again from their files, last before a push, a wake
  or a question to the endpoint (§3, the last check), and for a wake once
  more after the launch returns and before the text is handed over, there
  with the two refusals the operation makes itself (a revoked signer; a
  read-only machine, for an event from outside it). A deliverer that
  finds any of them changed, or a record it cannot read, pushes nothing
  and settles nothing: the debt is still the thread's, and a later pass
  delivers it. An event
  is settled without a push only where the operation settles one today on
  its own evidence (a revoked signer, the read-only refusal, the
  endpoint's refusal, an event for the live alone that finds its thread
  stopped, a failure given up after `DELIVERY_ATTEMPTS`).
- **Nothing is delivered, and nothing asked, over an open entry.** While a
  thread's record holds `pending`, whatever its operation, its current
  session is not yet settled (an absorption's claim can still be undone),
  so `owing` answers none for it. Delivery and the asks defer; they finish
  no entry. The daemon's own reconciliation finishes entries, as today,
  and the consumer thread never does.
- **This child writes nothing in a thread's record, and `finish` gains no
  step.** A record's `channels`, `began` and `answered` keep their three
  writers (`set_channels`; a return, `_began_anew`; an absorption's
  `_merge_absorbed`), and delivery is checked against all three. What
  delivery writes is a thread's delivery record under a channel's log, and
  a kept word's file, and nothing else. Reason: any copy from 1.51.0 on
  finishes an open entry it finds and skips a step it does not know, so
  nothing delivery needs may live in a journal step.
- **Lock order,** outermost first, as T2 fixed it and unchanged: the
  delivery lock (in a channel, the thread's); the seat's lifecycle lock; the
  wake lock; a store lock; a log's lock. `set_channels` takes the thread's
  wake lock, so a wake's hold, kept through its push, is what keeps a
  removal from landing between the last check and the frame's handoff. No
  lock is added.
- **Nothing a channel's message causes on the consumer thread launches an
  engine, pushes to a process, or waits on a lock without a bound** (the
  holder's ruling). The uplink asks the endpoint about a channel's
  messages and keeps each answer in a file; a deliverer in another process
  (the daemon's channel pass) carries it out (§4). On the consumer thread
  a channel's message causes reads, the queuing of frames, the creation of
  that file, and the two appends those reads already make under no lock (a
  line in the daemon's log; the receipts' mark that a young process may
  yet activate them), and nothing else: no delivery lock, no store lock,
  no wake, no `project_path` over a home whose registration it would have
  to read or write. Three paths are named because the mechanism alone left
  them: the receipts' lock inside the choice of what to ask is only tried,
  and a busy one defers the ask; an ask that goes unanswered writes
  nothing there; and a message's upload reads its sender's frame as the
  plane last read it, never through a view. M6 proves each with the lock
  in question held by another process. What a project's message does on
  that thread today is not this child's to change, and neither is what a
  request's upload does there (`member_under`; the request pass's finish
  of its own entry; rows in TECH-DEBT).
- **A machine that holds no channel pays nothing per tick,** in the daemon
  and in the uplink (the holder's ruling in CH1). Every per-tick duty this
  child adds is a loop over the channel set (`known_kinds`' channels,
  `Link.channels`), and inside it over this machine's threads that hold a
  set: a machine that only follows channels, holding no member, reads no
  channel's log for a debt. The `sminos-idle` gate is the check, and it
  stays as it is: its limit is 33,570 Python calls a second, the last
  commit of CH1 that changed code read 32,230, and runs differ by about
  2.6%, so one run's margin is not capacity. Each milestone records its
  figure in Progress, and a change that cannot keep a machine with no
  channel at `main`'s figure goes to the composite's holder before it
  lands. The gate's stand-in lists no channel, so what a machine that does
  follow or hold channels pays is measured apart (M7).
- **Byte for byte for a session in no channel** (parent line 8). `say`,
  `list`, `chat`, `spawn`, `join`, `retire`, `send`, every event, every
  frame of the uplink and every line printed, a frame's reply line
  included, are what they were on a machine that knows no channel and for
  a thread that is in none. A key, a line or a lookup this child adds
  appears only where a channel does; an error for a store with no channel
  comes in the order it came before.
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
  from before CH that has joined no session into it: it delivers only to
  the members its view of that log holds. A machine on 1.54 stores a
  message and delivers nothing of it (`HubLog.deliver`, `channel_pass`): it
  is owed, and pushed when that machine updates, by the boundary 1.54
  itself kept (C5, "Between releases"). Nothing here defends against an
  older CLI run by hand beyond what M11 asserts.
- **The wire is another team's.** MAWS's conversation fixture is one file,
  copied byte for byte and never amended; this child adds no frame type and
  no field of a frame. MAWS's master at `5a88bcd83` (the fixture's blob
  `5ffdd4a2`) adds case 16 (a session that is a member under its project
  alone uploads a `say` under a channel, attested from that frame), case
  17 (a non-member's `say` under a channel, its `reach?` answered `deliver`
  for one recipient and `refuse` for another), case 18 (a `words?` about a
  `human` under a channel) and case 19 (the same with a notice). M7
  copies the fixture and replays it.
  The stand-in proves the order and the shape of frames; what the endpoint
  attests and what its policy cache holds are proved by the fixture, not by
  the stand-in. A line that will not replay, or an answer of MAWS's
  architect that differs from §4, goes to the holder before anything is
  built on it.
- **What sessions are taught is behaviour.** The guide, the skill, the spawn
  preamble and the manager's skill change in M10 and nowhere else, through
  doperpowers:writing-skills with the evaluation Concrete Steps gives; a
  test that pins one of their lines verbatim is changed in that milestone.
  Before M10 only two taught things move, because they would otherwise be
  false: the sentences of the refusals M1 and M4 replace, and `sminos help`.
  A change to a frame's words is scoped to a channel's frames; a change to
  every frame is the owner's.
- **A check on a real engine runs only under a scratch home:** `HOME`,
  `CLAUDE_CONFIG_DIR`, `SMINOS_HOME` and `MAWS_USER_DATA` all under one
  scratch tree, never the person's real configuration (T1's first live pass
  joined real sessions and was discarded).
- **The repository is public.** No hostname, address, account, project id of
  the fleet, local path or secret's name enters a test, a comment, a commit
  message or this document. MAWS is named by its commits alone.
- **`S/sminos.py` is one file of twenty thousand lines.** What reads and
  decides for a channel (resolving through a roster, what a channel owes,
  the channel's delivery pass, the kept words, the lead, the channel-aware
  read) goes in `S/sminos_channels.py`; `S/sminos.py` gets the changed
  seams.
- **What sits beside the code is written with it.** Each milestone adds what
  it built to `sminos/skills/sminos/scripts/CLAUDE.md` (the rules of this
  section a later change could break, the tests' names), since the next
  milestone's executor reads that file before it reads this one's code; M11
  reads the whole against the tree.
- **Tests are hermetic,** as in CH1: the test engine (`T/wake_engine.py`),
  the stand-in, temporary homes, invented names. **And they vary what a
  single case hides:** both kinds of thread (spawned and human-opened) as
  recipient, live and stopped, woken and held; the sender a member, a
  session that is no member, a person at a terminal and a machine's
  notice; one, two and five messages of one and of two writers; a message
  before and after an add, a removal, a removal and an add, an end and a
  return, a hand-off, an absorption, a refill, a `join` and a change of
  reach; the deliverers (the sender's own call, the daemon's pass, the
  daemon carrying out a kept word) and the order of their work, held apart
  by a barrier where the order is the point; and a cut after each write. A
  guarantee tested with one message to one live human-opened thread is not
  tested.
- **One change, one version.** No release is cut between milestones. The
  child merges as one pull request that leaves the repository releasable
  beside a machine on 1.54 (D7), with sminos's version bumped in it
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
  add is owed (the holder, 2026-11-22), and so is a person's message that
  waited in this machine's queue across a removal and an add, which has no
  position until it is released; nothing is written at a thread's end, so
  a return that keeps the earlier boundary (over a channel log that could
  not be read; an older copy's) is pushed everything past it and unsettled,
  what was held before the end included (the holder, 2026-11-22); a
  message that names a thread which an absorption has since taken into
  another is owed to no one (the holder, 2026-11-22: such a thread lives
  for moments, and its mail is not worth a second record to every event);
  a seat made again over a purged seat's session is that thread, so mail
  that names the id and reaches the machine after the new seat entered
  the channel is owed to it (the accepted shape of the boundary); between a
  thread's `joined` and the statement that follows it other machines read
  it as in no channel, so a reply to it through the channel goes to it
  directly for that moment; a push to a live session has the base's own
  window, a hand-off or a removal between the last check and the frame's
  handoff (the TECH-DEBT row "The live push's own window"), where a wake
  has none; in a project an addressed event that names a session its
  thread has left is still not pushed (the owner's ruling of 2026-11-21);
  a sender on a machine that reads an older statement addresses a thread
  that has left, and that message is delivered to no one; a frame's header
  names a log by its name, so a channel and a project of one name read
  alike there and the reply line's id tells them apart; a receipt (a `gate`
  process's) is handed to a session, so a thread handed off between a
  receipt's handoff and its admission is pushed that event again in its
  next session; the endpoint's word is carried out within sixty seconds
  and across one launch, and what only the endpoint knows (who is in the
  org, a machine's owners, the sender's owners) is not seen again inside
  that window, as it is not for a project's verdict across its launch
  today; a channel's ask the endpoint never answers is asked again each
  interval and never given up, and holds back that writer's later
  messages to that thread and nothing else; a home whose path holds a
  bracket is misread by the base's scan of memberships
  (`member_project_now`'s glob), which a channel's upload still asks, so
  its senders' frames may not go first there (a TECH-DEBT row written in
  M3; delivery's own last check does not use that scan); and a machine on
  1.54 delivers nothing from a channel until it updates.

## Plan of Work

Readers come before writers, one machine before two, code before what
sessions are taught. M1 gives addressing the roster where nothing is
written into a channel yet: a verb's target and a bare alias. M2 builds
what a channel owes a thread, as a debt that can be read, with every
transition of a thread's life against it, and pushes nothing. M3 gives
that debt to the delivery operation: the push, the hold and the wake. Both
are built with the doors still shut, so that when a door opens everything
behind it is already there and reviewed. M4 opens the doors: `say` into a
channel, the reply that lands there, and `chat` over a channel. M5 runs
the scene on a real engine, in the middle of the build where the engine is
in the path. M6 carries a message between machines on the endpoint's word,
asked by the uplink and carried out off its consumer thread. M7 holds the
wire to MAWS's fixture and measures what a channel costs. M8 adds the
lead. M9 teaches the two readers of a session's exchanges to read a
channel's. Between M9 and M10 the range is reviewed whole by the
composite's holder. M10 rewrites what sessions are taught and evaluates
it. M11 runs older copies against the result, reads what sits beside the
code, bumps the version and runs the acceptance.

Eleven milestones, two more than this plan's first form: its buildability
review asked that the debt and the push be reviewed apart (M2, M3), and
the holder that the wire's scheduling be reviewed apart from its
conformance to the endpoint (M6, M7). The composite's cut kept the taught
surface in this child unless its plan showed it tripping the gate. It
stays (M10): the doors and the texts must ship in one release, since from
M4 on `sminos help` and what `say` prints already say what the guide would
otherwise contradict, and X6 forbids shipping a taught surface that is
false. It is the last milestone that changes behaviour and consumes
nothing but the CLI as M1 to M9 leave it, so the holder can still cut it
into a child of its own at the frontier without touching M1 to M9.

**Where milestones meet.** CH1's lesson is that review of each milestone
missed what lives where one milestone's judgment meets another's wire. So
each milestone below names, under **Seams**, the earlier milestone it
meets, the one place the two are joined, and the test that crosses the
join; a seam is built once, by the later milestone, and its test fails
before that milestone and passes after. Two reviews are scheduled over
more than one milestone's diff:

- **M6's review reads M2 to M6 as one range** (the controller's, at the
  rung the Decision Log gives): the debt, the push, the doors and the wire
  are one path from a sender's command to a recipient's inbox on another
  machine, and no single diff holds it.
- **The frontier review.** When M9's review is clean the controller pushes
  the branch and returns to the composite's holder with the word
  `FRONTIER`, the range (`git merge-base origin/main HEAD` to `HEAD`) and
  nothing else to decide. The holder reviews that range through
  doperpowers:review-code at the panel rung, with lenses given, not
  derived:
  - lock order, and what is read outside the lock it is acted on under:
    the thread's delivery lock in a channel and its one owner when a kept
    word is carried out, the wake lock, a record's lock, the last check
    (before a push, before a launch and after it), the record made
    consistent with the selection, and a pass that lost its session, its
    project or its lane;
  - the thread as the key: every place a channel's debt, its record, its
    lock, an ask, a kept word, a receipt or a cursor could still be read
    or written by a session's id, every helper that reads a thread's
    membership from the log an event lies in, and a seat's id that comes
    back after a purge;
  - the consumer thread: everything a channel's message causes there, down
    the call graph, against "no push, no launch, no lock without a bound":
    the answers, the choice of what to ask, an ask that is never answered,
    and a message's upload;
  - what only reads: `daemon owed` over a cold store with an entry open,
    and every reader of a delivery record that cannot be read;
  - an older copy on the same store, and a machine on 1.54 across the
    wire;
  - what leaves the machine under a channel's id: every frame and every
    event, `from_project`, a copy, an outcome, and whether a reply, a lead
    or an entry of `to` shows a private thread's session or thread id to a
    reader that may not read it;
  - every door that relied on "nothing is said in a channel": each refusal
    lifted, and each reader of a channel's log in §6's table;
  - the milestones' interactions: a message against an add, a removal, a
    removal and an add, an end, a return, a hand-off, an absorption and
    its undo, a refill, a purge and a seat made again, a `join`, a change
    of lane, a change of reach, a failed attempt, a wake and its launch,
    the thread sweep, a late word and a channel that left the machine; the
    lead against each.

  Its confirmed findings are fixed on the branch by the holder's fix wave,
  the range is read whole a second time if the first reading confirms more
  than ten, and there are three rounds at most. The controller is then
  continued for M10. It sits after M9 because every writer, reader and
  sender this child adds exists by then; M10 changes texts and M11 adds
  none.

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

**Interfaces:** exposes §1 (`reach_in`, `shared_rows`, `thread_of_row`,
`claimants`, `once_in`). Consumes Y1 (`roster`, `channels_of`, `find_channel`,
`names_channel`, `ambiguous_name`).

**Seams:** none earlier. It leaves one for M4: tags qualified by a channel
reach members through `reach_in`, the same function `find_target` calls
here, so a name resolves alike in a verb and in a tag, and the reply line
M3 composes (a thread id's first eight) is a name this milestone already
resolves.

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
  no channel reads no roster, and its lookups and errors are today's; what
  it pays is the one read of its own record that says so, which M7's bench
  times beside the base. A verb's bare name is not widened (open point 3).
- A name in id form through a channel is read as a thread id's prefix
  first, then as a session's (§1): the whole rule is built and tested here,
  where `find_target` uses it. `reach_in` answers `out` for a thread that
  was once in the channel and is not now, and refuses nothing for it
  itself: here `find_target` refuses it in §2's sentence for a verb; a tag
  sends to that thread directly, which is M4's.
- Who has had a session is read from the logs' episodes
  (`_projection`'s `episodes`: a session's stretches under one thread,
  each with its stamp), over every project's view, and not from displayed
  rows: `View.ended` leaves out seated rows and holds only sessions whose
  latest membership is an end, and a row's `former_ids` does not hold its
  own session. An episode an older copy left unstamped is counted with
  the thread of the statement that took effect in it, and where it has
  none the session's history is unknown: the id then names no one thread.
- Which thread a row is addressed as (`thread_of_row`) is read from the
  roster's own sweep: `_sweep` keeps, beside the rows it gives, what it
  read of each row's view (the row's `joined` stamp and its statement in
  effect, from that view's `info`), so the thread and the session a `to`
  entry carries come from one reading, and no second lookup is made after
  a row is found.
- Whether a thread was ever in the channel (`once_in`) is read from
  statements that took effect, by the fold's own rule (under the writer of
  the session's `joined` in effect then, after it), and whose `thread`
  that `joined`'s stamp bears out or does not contradict. A statement that
  never took effect, and another writer's, prove nothing: a stamp alone
  is any writer's to set (CH1's `answer_of` says the same of an answer).
- The engine's collision name (E15, the composite's delegated unknown): a
  row is listed and matched by the alias its own project's view gives it.
  `held_alias` already never lets a name the engine made up, `collision`
  among them, replace an alias held, and two rows of one alias are told
  apart as `alias#short` (`member_label`). Nothing is added for a channel.

**Does not touch:** `cmd_say`, `resolve_tags`' check of a channel qualifier,
`channel_say_refusal`, `find_project`, `project_tiers`, delivery, the
uplink, the daemon, the guide.

**Proves:** B3, and B5's rule. Its tests pin: `<channel>/<alias>` with the
channel named by its id, its `name#short` and its name, for a seat of this
machine, a thread its human opened here and a thread of another machine;
`retire` and `charge` through a channel leave the channel's log byte for
byte as it was; a name a project and a channel both answer is refused by
`ambiguous_name` at a verb and at a bare tag's refusal; the bare alias with
one answer in the project, one in a shared channel, one in each (refused),
and one in a channel the sender is not in (today's refusal, listing it
elsewhere); a sender in no channel makes no call of `rosters` (counted);
and every row of §1's table for a name in id form, among them a thread's
id whose session has since become another member's (the thread is
reached, by its id), a session's id that two threads have had (nothing
reached, each named), a session whose one episode is unstamped with no
statement (nothing reached), a seat made again over a purged seat's
session (the same id, the same thread: reached), an ended seat, a thread
that moved projects, a thread's id that was never in the channel (no old
reply: the unknown-name refusal), and one whose only statement of the
channel never took effect (the same).

### M2 — What a channel owes a thread: the debt and its transitions

**At its end:** what a channel's log owes each thread of this machine can
be read, and is right after every transition of a thread's life: `sminos
daemon owed` lists, for a channel, the messages that name a member thread
of this machine past its boundary and not settled, under that thread, and
nothing for a thread that is not in the channel, whatever session ids the
messages carry; for a thread whose delivery record is there and cannot be
read it says that it cannot tell, and a thread whose own record cannot be
read is attributed no debt. Reading it changes no file. Nothing is
pushed yet and the doors are shut: the suites put messages into the log
themselves, and settle by calling the record's own writers.

**Touches:** `S/sminos_channels.py` (`Debt`, `debt`, `Owing`, `owing`,
`owed`, `first_owed`, `delivered`, `still_owed`, `owed_here`),
`S/sminos_daemon.py` (`owed_in`), `T/test_channels_debt.py` (new),
`docs/doperpowers/TECH-DEBT.md` (the row on a thread absorbed with mail
that names it), `T/channel_wire.py` and its tests (§8: a delivery record
under a channel's log).

**Interfaces:** exposes §3's first half (the debt). Consumes Y3 (`began_of`,
the record's `channels`), `sminos_threads.set_holders`, the delivery
record's own writers (`delivered_settle`, `delivered_fail`), which take a
thread's id where they take a session's.

**Seams:** *the debt and CH1's membership* (Y3). The debt meets the
record's three writers of `began` at one place, `debt`, which reads the
record whole; the tests that cross it are §3's rows D1 to D14, each staged
through the transition itself (`change`, a request carried out, an end and
a return, `hand_off`, a refill, an absorption) and never by editing a
record.

**Decisions:**

- The selection is one function over the channel's log and the thread's
  record, and it applies the boundary itself: nothing is written into a
  delivery record when a membership begins, returns or changes session.
  This plan's first form wrote the boundary into the session's record and
  merged records at a hand-off; with one record a thread there is nothing
  to merge and nothing to write.
- What the selection needs (`Debt`: the thread, its boundary, the
  channel) is read from the thread's record alone. What a push needs
  beside it (`Owing`: the thread's row in its own project, its session's
  reach) is read only by a deliverer. `daemon owed` reads the first and
  never the second: it reaches no view, no reconciliation, no lock and no
  write, as its contract says today.
- A channel's delivery record that is there and cannot be read is neither
  empty nor settled (`delivered`): the selection claims nothing for that
  thread, delivery defers, and `daemon owed` lists it among what it could
  not inspect, as it lists a project's. A record that is not there is an
  empty one. `delivered_load` itself, which reads both as empty, is left
  for projects.
- An entry of `to` with no `thread` names no one. Nothing in a channel is
  owed by a session id.
- No absorbed thread's id is kept. After an absorption the thread that
  goes on is owed what names its own id, past its boundary as CH1's merge
  left it; a message that names the absorbed thread is owed to no one,
  and that thread's delivery record under the channel stays on disk,
  read by nothing, as an ended thread's does. The TECH-DEBT row is
  written here, with what would promote it: a report of a message in a
  channel that named a thread absorbed moments later and reached no one.
- `daemon owed` (`owed_in`) counts a channel's debt through `owed_here`,
  under the thread's alias as its record has it, and counts a thread that
  is stopped and held as waiting, not as a debt, as it does for a project.
  It is built on `set_holders`, which gives only records that read: a
  thread whose own file cannot be read has no membership, no alias and no
  debt to attribute, and is not named by this diagnostic.
- A session's record is read one way wherever eligibility is decided
  (§3): one that is not there is the default CH1's last check reads (lane
  A), one that is there and cannot be read defers, and lane B defers.
- The suites stage a message with `log_append` under a writer in the
  channel's log, its `to` entries carrying `thread`, and one from another
  machine as an imported event (a writer file under another machine's
  name carrying `verified`), as `T/test_words.py` stages one.

**Does not touch:** `deliver_next` and the rest of the delivery operation,
`holder_push`, `wake_member`, the daemon's channel pass, the doors (they
still refuse), the uplink, `settle_ended`, `sminos_threads.py`,
`delivered_load`, `carry_hand_off`.

**Proves:** B4's rules as a debt, row by row of §3: what `owed` returns
and what `daemon owed` prints after each transition. Beyond the table its
tests pin: a message at the boundary (seq equal to the kept position) is
not owed and the next one is; two messages of one writer are owed in
order; a message that names a session the thread holds and another
thread's id is not this thread's; a message that names this thread's id
and a session it never held is; both sides of row D5; a late import that
names a thread whose old session another member now holds under another
id (row D13: owed to the thread named, never to the other); a seat over a
session, in the channel, purged, a seat made again over that session and
added, and a late import that names the id (row D15: owed to the seat,
which is that thread, when it lies past the new boundary, and not when
the machine held it before the add); a thread absorbed with unsettled
mail that names it (row D7: owed to no one; the thread that goes on is
owed what names its own id, as before); two messages across an end, one
held before it and one gained while ended, under each kind of return (a
return of this code's: neither owed; one over a channel log that could not
be read, and an older copy's: both owed); a thread whose own record is
there and cannot be read (no debt is attributed to it, and nothing is
settled); one whose delivery record is there and cannot be read (nothing
owed is claimed, nothing settled, and `daemon owed` lists that record
among what it could not inspect), beside one whose delivery record is
absent (owed from the boundary); a thread whose session has no record at
all (`owing` answers, lane A, with the token an absent record gives)
beside one whose session's record is there and cannot be read (`owing`
answers none); and
`daemon owed` run cold over a store in which a thread's record holds an
open entry: the debt is listed, and no file under the home has changed.

### M3 — Pushing and waking from a channel's log

**At its end:** a message that lies in a channel's log and names a thread
of this machine that is in the channel is pushed to that thread's current
session once by the next `sminos daemon tick`, wakes a stopped thread that
may be woken, and is held, owed, for one that may not; it is framed as
coming from the channel, and its reply line names the channel's id and the
sender's thread, or, for a message that carries `from_project` (a sender
outside the channel), the frame says so and the line names the sender in
its own project. A pass that has lost its session, and one that meets an
open entry, a move to another project or a change of lane, pushes and
settles nothing. The doors are still shut.

**Touches:** `S/sminos.py` (`_owed`'s callers in `deliver_next`,
`deliver_verdict`, `deliver_reach`, `words_due`, `reach_due`, `_first_owed`;
`holder_push`, `push_event`, `wake_member`, `held_owed`, `held_decided`,
`frame_of`, `_conclude`, `_write_receipts`, `ReachGate.needs`,
`WordsGate.held`), `S/sminos_control.py` (`_routes`: whom a channel's
frame's reply line names), `S/sminos_holder_deliveries.py` (`key_hash`
and every lookup made through it, a receipt's key, `sweep`),
`S/sminos_channels.py` (`deliver`, `own_row`, `normalize`), `S/sminos_daemon.py`
(`channel_pass`), `S/sminos_outcomes.py` (`record`),
`T/test_channels_delivery.py` (new), `docs/doperpowers/TECH-DEBT.md` (the
row on a home whose path holds a bracket).

**Interfaces:** exposes §3's second half (the delivery operation with
`owing`). Consumes M2's `owing`, `owed`, `first_owed`, `delivered`,
`still_owed`; `appended_here`; T2's wake.

**Seams:**

- *The push and the debt* (M2). The delivery operation takes its choice
  from `owed`, and splits what it reads by a session in a project into
  two: the thread's id for every delivery record, mark and lock, the
  thread's current session for every process, hold, reach and receipt.
  Crossed by: a message pushed to a live member is settled in the thread's
  record and in no session's; and by the two interleavings of a hand-off,
  held apart by a barrier. In the first, a pass for the old session has
  chosen an event and waits before its last check; the hand-off lands;
  the pass goes on: the old session receives nothing, nothing is settled,
  and the next pass pushes one frame to the session that continues the
  thread. In the second, the old session's push has been made and its
  settlement waits; the hand-off lands; the pass for the new session
  waits on the same lock and pushes nothing more.
- *A record that remembers an event the debt has dropped* (M2's boundary).
  A failed attempt leaves `pending` in the delivery record, and
  `_next_check` then refuses to settle or to fail any other event of that
  writer; a removal and an add can put that event below the boundary,
  where `owed` no longer selects it. The mark is cleared only on that
  evidence: its seq at or below the boundary as read then for its writer.
  An event that is merely missing from the selection (its writer's file
  could not be read) clears nothing. Crossed by: one writer's first
  message fails once; the thread is removed and added again; the writer's
  second message arrives; two ticks: the second is pushed once and
  settled, and the first never. The same across a return that writes the
  boundary anew. And: one writer's message has failed once and its file
  then cannot be read, a second writer's message is pushed by a pass, and
  the file is restored: the first writer's mark and its count are as they
  were, and its message is attempted again.
- *The helpers that read "the member's log"* (the ruling's ninth point).
  `held_owed`, `held_decided`, `push_event`, `holder_push` and
  `wake_member` read a session's membership, and `canonical_end` an end,
  from the log the event lies in; for a channel that log says nothing, and
  an older copy's `joined` there, undone by CH1's `retired` `moved`, says
  the wrong thing. With `owing` each reads membership from the thread's
  own project and the debt from the channel. Crossed by: a held member
  whose inbox fails once stays held, owed, with no attempt counted, and is
  pushed when the inbox answers; and a current member whose own writer in
  the channel's log holds that old retirement is pushed to, and woken, as
  any member.
- *The thread's own project, and its lane, at the last check.* The project
  `owing` captured may stop being the thread's (a `join` elsewhere), and a
  session may turn lane B, with the thread, the session and the channel
  all unchanged. The check is CH1's last guard's own reads (§3): the
  session's own events in the captured project by literal paths, and
  whether that project is where the session is now, a tie deciding for
  neither. Crossed by, each with an event already selected and the pass
  held at a barrier before its last check: the thread `join`s another
  project; the destination's `joined` bears the very millisecond of the
  source's (CH1's tie); its session's record turns lane B; its session's
  record becomes unreadable. In each nothing is pushed and nothing settled
  (never `recorded`), and after the move the next pass, which captures the
  new project, pushes one frame. And two that must not defer: a session
  that has no record at all is lane A and is pushed to; and under a home
  whose path holds a bracket a member is pushed to as under any other.
- *An open entry* (the holder's ruling on the third read), from both
  sides. Crossed by: an absorption cut immediately after its `begin` (the
  continuing record's `current` already the job's, its entry open), the
  channel's delivery run by itself (`sminos_channels.deliver`: a tick's
  reconciliation would finish the entry before it), then the lost claim's
  undo: nothing was pushed to the provisional process, nothing settled,
  and the pass left the entry as the cut left it. And from the old side: a
  pass that selected an event for the provisional thread before the
  `begin`, held before its last check and let go after the `begin` and
  before the provisional record is reserved, pushes nothing: that record's
  own file still names the session and holds no entry, and the session's
  current record, read afresh, is the continuing thread's.
- *A wake's launch and the last check.* A launch can take minutes, and
  what was checked before it can have changed. A removal is not among
  what can: `set_channels` needs the wake lock, which the wake holds
  through its push. Crossed by, each with the test engine's launch stalled
  at its barrier and the barrier then lifted: the session's reach changed
  (the process runs, no text is handed to it, the event is still owed, and
  no second launch is made for it); the machine turned read-only, for an
  event from outside it (no text; the event is refused as the same check
  refuses it before a push); the event's signer revoked (no text; the
  event goes the way a revoked signer's goes before a push); and a removal
  attempted meanwhile, which is busy and lands only after the push: the
  frame is handed over, since the thread was a member under the hold. A
  removal made before the wake's hold is taken starts no process, and the
  event is then not owed.
- *A receipt and the thread it was for.* An event that names two threads
  can meet one session twice: the session one of them held runs again as
  the other. Crossed by: an event addressed to both, a receipt for the
  first still held under that session, never admitted, and in a second
  case admitted; the second thread, now holding the session, is pushed
  its own frame once and is settled on no admission but its own.
- *Delivery and a writer that is no member.* An event in a channel's log
  may come from a thread with no membership statement there (C5). Delivery
  never looks its sender up: it reads the event's `to` for whom it is
  owed, and its `from_project` for how it is framed and where its reply
  goes. Crossed by: one message staged with `from_project` and one
  without, by the same writer to the same member: both are pushed; the
  first's frame carries §3's clause and a reply line naming
  `@<that project's id>/<the writer's session's short>`, the second's
  neither clause and a line naming `@<the channel's id>/<the first eight
  of the sender's thread id>`.

**Decisions:**

- The channel pass (`sminos_daemon.channel_pass`) gains one step, last:
  after the channel's view (its reconciliation) and `carry_due`, the
  channel's delivery (`sminos_channels.deliver`). A request honoured in a
  tick has then set the boundary before that tick's delivery reads it.
- The pass costs a tick what the project's costs: a thread that nothing in
  the log names is passed by on the log's own index, with no lock and no
  record read, and a thread whose whole backlog is held is passed by on
  the memory of a full pass, as `deliver_owed` does with `_HELD_PASSES`
  (one memory for both, keyed by the log and, for a channel, the thread).
  A machine that follows channels and holds no member reads no channel's
  log for it.
- Under the thread's lock the operation does three things before it
  chooses: the last check; the delivery record read strictly, where one
  that cannot be read stops the pass; then the record made consistent with
  the boundary (`normalize`: a writer's `pending` whose seq is at or below
  the boundary, read afresh for that writer, is cleared, with the attempt
  count and the pushed note that ride with it, in one write; the settled
  prefix is never moved by it, and nothing else of the record changes).
  Transitions themselves still write nothing. The record's own writers,
  given a channel's log, read it strictly too, and write nothing over a
  record that cannot be read.
- The last check is made again in `holder_push` before anything is handed
  over, in `wake_member` once the wake's hold is taken and before a
  process is started, and once more after a wake's launch returns and
  before its text is handed over, there with the session's reach, the
  event's signer's revocation and, for an event from outside this
  machine, the machine's read-only policy read again as well. A pass that
  fails it stops for that thread: nothing pushed, nothing woken, nothing
  settled, no attempt counted. A refusal the operation makes on its own
  evidence (a revoked signer; a read-only machine) is made after the
  launch as it is made before a push, and hands nothing over. After a
  launch that leaves the debt owed to a session that now runs: the next
  pass pushes to it, or the endpoint is asked again, and nothing launches
  twice.
- The last check's reads are CH1's last guard's (`set_channels`' check
  under its lock): that the session's current record, read afresh
  (`current_record(…, fresh=True)`), is this thread's and holds no open
  entry, beside the captured thread's own file; the session's record by
  the one rule of M2; and the captured project by `own_events_now` and
  `_current_here`, which read registrations and logs by literal paths and
  let a tie decide for neither. `member_project_now` is not used for it:
  it takes the later of two equal timestamps by the scan's order, and its
  glob reads a bracket in the home's path as a pattern. That second fault
  is the base's, and a channel's upload still meets it
  (`Link.senders_before`): a TECH-DEBT row is written here, with what
  would promote it (a home under such a path whose channel uploads go
  without their senders' frames), and nothing of it is fixed.
- Inside the operation, for a channel, `push_event` finding the session
  retired in the captured project (a `moved` among the reasons) is that
  same stop, never `recorded`.
- A hold's mark in a thread's record is that thread's: with `owing`,
  `stale_hold` and `held_unreadable`, which compare a mark with the
  session's stamp to settle a hold another thread left behind, are not
  asked, and `wake_member`'s own comparison of the mark with the thread it
  wakes reads the thread's record, where the two are one.
- A receipt (`sminos_holder_deliveries`: an event handed to a `gate`
  process and settled at its admission) is found, for a channel's event,
  by its thread beside its session: `key_hash` takes the thread, and so
  does every lookup made through it (`exists`, `plan`, `words_of`,
  `handed`, `admitted`, `settled`). `sweep` reads that thread's record to
  drop a settled receipt, never the record a session's id would name
  there. The admitting side needs nothing of it: it finds a receipt by the
  id its marker carries, whose first part is the key's hash
  (`_held_receipt`), and checks the session alone. Reasons: an event that
  names two threads would otherwise share one receipt between them when
  one session serves both in turn, and a seat's thread id is a session's
  id, so a session's id read as a record's key under a channel can be
  another thread's record.
- What a frame says of a sender outside the channel is one clause after the
  sender's alias, where `sender_labels` puts its own (§3), composed in
  `frame_of` for an event of a channel's log that carries `from_project`.
  The reply line is `reply_line`'s one form, unchanged; what changes, in
  `_routes`, is the name it is given for an event of a channel's log that
  carries no `from_project`: the event's `thread`.
- No outcome of a channel's delivery is kept for the uplink
  (`sminos_outcomes.record` keeps none for a channel, and `_conclude` asks
  for none): §4 says why.
- `HubLog.deliver` stays as it is, nothing for a channel. An import already
  nudges the daemon, whose channel pass delivers; M6 adds what needs the
  endpoint's word. Reason: `HubLog.deliver` runs on the consumer thread.
- Live and stopped recipients are T2's fixtures (`T/test_wake.py`'s
  `Engine`, `T/inbox_standin.py`); a barrier is the test engine's own
  switch, or a lock the test holds.

**Does not touch:** the doors (they still refuse), `Link.ask_words` (on a
machine whose endpoint decides reach, an event that needs its word is left
owed and listed `gated`, as a project's is, and M6 asks), `deliver_owed`
(the project's pass), `settle_ended`, `sminos_threads.py`,
`carry_hand_off`, `HubLog.deliver`, `Plane.refresh`, `reply_line`,
`_next_check`, `delivered_load`, `member_project_now` and its glob, a
project's receipts (their key is as it was).

**Proves:** B4 as pushes, on one machine: rows D2, D3, D6 to D10 and D15
of §3 through a real push or wake; B7's first half for delivery (no host
kind is written by a push or a wake from a channel). Beyond the seams its
tests pin: two messages of one writer are pushed in order and a failure
stops that writer; an event for the live alone settles `recorded` for a
stopped member; a held message is pushed once when the thread is reopened
and once when it is woken; a lane A refill's new occupant is pushed what
names the thread; an event marked held and since passed by a new boundary
is never pushed, and its mark is gone once that writer's next event is
settled; the last check, for a live recipient, with the membership
changed after the pass chose the event (removed; removed and added;
ended), pushes nothing and settles nothing; a message
under this machine's own name with no receipt is an outside event (refused
`refused-read-only` on a read-only machine, never the same-owner
shortcut); a thread in the channel with a private record; a receipt for a
channel's event whose session's id is another seat's thread id, swept by
that seat's settled record never; and no file appears under any project
for a channel's delivery.

### M4 — Saying into a channel: the doors, the reply, the read

**At its end:** `sminos say --in desk-integration "@worker …"` and `sminos
say "@desk-integration/worker …"` by a member write one event into the
channel's log and deliver it as M3 does, at once for a recipient on the
same machine whose push needs no word of the endpoint; the recipient's
reply by its frame's reply line lands in the channel's log and reaches the
sender's thread; `@all` reaches the channel's live members and an untagged
post prompts no one. A thread that is not in the channel says into it in
the same forms: its message lies in the channel's log with its project in
`from_project` and a copy in its own project's log where today's rule
leaves one, reaches the members it names, and it reads one line saying
that it is no member, that replies come to it directly, and how to add
itself; the reply by that frame's line lands in the sender's project. A
reply to a member that has since left goes to that thread directly, and
the replier is told. A person at a terminal, and a machine's notice, write
under the machine's human writer; `sminos chat desk-integration` reads the
conversation, and `sminos list desk-integration` prints the channel as
`--channel` does. On one machine.

**Touches:** `S/sminos.py` (`cmd_say`, `resolve_tags`, `_resolve_tag`,
`deliver_say`, `frame_landed`, `say_scoped`'s refusal, `cmd_chat`,
`list_scope`, the module docstring that is `sminos help`;
`channel_say_refusal` and `find_target`'s CH1 sentence go),
`S/sminos_channels.py` (`speak`, `chat`, the sentences of §2),
`T/test_channels_say.py` (new), `T/test-channels.sh` (its section "nothing
is said into a channel" becomes what is said), `T/test_channels.py` (its
cases that pin `channel_say_refusal`), `T/test-channels-machines.sh` (the
fourth step of CH1's scene), `T/channel_wire.py` (§8).

**Interfaces:** exposes §2 and §6's `chat`. Consumes §1 (`reach_in`), §3
(`owing`, `deliver_next` with it).

**Seams:**

- *Sending and delivery* (M3). `deliver_say` is the one join: for a
  recipient of this machine it asks `owing` for the thread the entry
  names and calls `deliver_next` with it, so the sender's own call and the
  daemon's pass are one operation, and what it then reads to word its
  line (a held mark, a settlement another deliverer made meanwhile) it
  reads in the thread's record. Crossed by: a `say --in` to a live
  member prints `sent` and the inbox stand-in holds exactly one frame; to a
  stopped member that may be woken, `sent (woken)` and the test engine one
  launch; to one that may not, T2's held line, and `--exit-held` its exit;
  a sender racing the daemon's pass for one message reads `sent` from
  whichever pushed and never `pending` for a message already delivered;
  and a second `daemon tick` pushes nothing more.
- *The reply and the roster* (M1, M3). A member's frame's reply line is
  `@<channel id>/<the first eight of the sender's thread id>`, and the
  door gives a qualifier that names a channel to `reach_in`. Crossed by:
  the line taken from the recipient's frame and run as written lands in
  the channel's log and reaches the first sender; run after that sender
  was handed off, it reaches the session that continues it; run after
  that sender was removed, it lands in the sender's own project's log,
  reaches it there, and the replier reads §2's line; run after another
  member came to hold the sender's old session id, it still reaches the
  sender's thread and never that member.
- *The two forms of the reply line* (M3). Which form a frame carries is
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
  the machine (a channel that has left this machine is not refused: the
  write brings its log back, M6); who writes and how (§2); the
  recipients, each with its thread and its session taken together from
  one reading of its row, the `info` of the view the roster's own sweep
  read it from and never a lookup made after the row was found (§2: a row
  whose stamp and statement name two threads is not addressed, and the
  sender is told); and that every tag
  is in that one channel. §2's table says what takes each of CH1's refusals' place.
- The unquoted `@<name#short>/<alias>` opens no tag (a tag's qualifier
  takes no `#`: `TAG_RE`, which the audience split also reads), so it
  stays refused where `shortened_channel_qualifier` finds it, in a
  sentence that names the two forms that work.
- Whether the sender is a member is read once, in the door, from its own
  machine's record (`channels_of`), and decides two things there and
  nothing anywhere else: a member's event is appended as it is; a
  non-member's gains `from_project`, its copy is `record_copy`'s to keep
  or not, exactly as for a message to another project, and the sender
  reads §2's line. The tests of the two are two classes of their own
  (`Member`, `Outsider`).
- The copy follows `record_copy` as it is. Where the sender's own project
  would disclose a private recipient's text (a home whose log is not
  filtered by audience), none is written and `record_copy`'s own warning
  says so; where the recipients split into several audiences there is one
  copy an audience; a copy that cannot be written is a warning after the
  delivery. None of that is changed, and M4 tests each beside the
  non-member's line.
- A tag qualified by the channel that names, by id, a thread that was once
  in the channel and is not now (`reach_in`'s `out`: the reply line of an
  old frame) sends to that thread directly: the message goes to its own
  project's log by today's path for `@<short>`, and the replier reads §2's
  line. With `--in` the same tag is refused, as every tag that resolves in
  another log is (B1). A name in alias form that no member answers, and
  the id of a thread that was never in the channel, are refused in both.
- With `--in <channel>` every tag is looked up in that channel's roster
  alone, in any form a tag takes. A tag qualified by another log, or one no
  member of the channel answers, is refused before anything is written
  (B1's last sentence), saying where that name does answer when it does.
- Without `--in`, tags qualified by one channel make that channel the
  destination, and every other tag of the message must be qualified by it
  too: a bare name resolves to its thread's own project (M1), and "one
  message, one log" refuses the mix in today's words.
- `@all` in a channel is the roster's rows in a live state (`FILLED`), the
  sender left out; a machine's project's refusal of `@all` does not apply.
- A selector that names a channel stays refused, in a sentence that names
  `--in <channel> "@all …"` (open point 1); `--in <project>` from a session
  stays refused in today's sentence (the composite's Deferred).
- `cmd_chat` branches before `find_project` on `names_channel`, to a read
  of its own (§6): it never calls `reconcile`, which runs a project's
  reconciliation and would hand off or end what an older copy joined into
  the channel.
- `sminos list <channel>` keeps `list_scope`'s reading of its arguments:
  the first token is the scope and the rest are row filters, `--subagents`
  first. A first token that names a channel is `--channel` of it.
- `frame_landed` names a frame by its log's name and its ref, and already
  claims nothing where another event of that log shows the same ref and
  text. It claims nothing either where another log of that name known on
  the machine holds such an event: a project and a channel may share a
  name.
- `sminos help` gains `say --in <channel>`, the channel-qualified tag,
  `chat <channel>`, and loses "nothing is said in one in this version".
  The guide and the skill do not change here (M10).

**Does not touch:** the uplink (a recipient on another machine reads
`recorded (on <machine>)` or its machine's published hold, as for any
thread there, and M6 delivers it; a message whose push needs the
endpoint's word, a person's words from a terminal among them, is recorded
and left owed with today's line, and M6 asks), the lead (an untagged post
from a terminal is untagged until M8), `record_copy`, `reply_line`, the
guide, the skill, the spawn preamble.

**Proves:** B1, B2 and B5 on one machine; B11 for `say` and `chat` (a store
with no channel, compared with the merge base's output). Its tests pin,
beside the seams: each refusal of §2 with nothing appended to any log;
every entry of a channel message's `to` carries the row's thread, and a
`say` its sender's; a row an older copy left unstamped is addressed by its
statement's thread, and one whose stamp and statement disagree is not
addressed; a member's event carries neither `from_project` nor
`copy`, and no project's log gains an event from it; a non-member's
carries `from_project`, and its copy in the sender's project names the
channel's event and is owed to no one; a non-member in a project whose log
is not filtered by audience, to a private member: delivered, no copy,
`record_copy`'s warning and the non-member's line both printed; recipients
of two audiences: two events, a copy each; a non-member's `@all` reaches
the live members and its untagged post prompts no one; nothing the
channel's log holds is pushed to the non-member, an `@all` there and a
reply addressed to a member among them; a notice into a channel from a
machine that holds no member of it, recorded (and, on a cut-over machine,
left for the endpoint's word, which M6 asks), and shown by `chat` as
`<program>@<machine>`; `chat <channel>` over a channel's log in which an
older copy left a closed session's `joined` changes neither that thread's
record nor any file of the log (the fold's first correction); `chat
<channel>` after a hand-off prints only what is new to the thread; `list
<channel> <word>` filters the channel's rows by the word; and `chat` with
no argument, and `list` with none, are today's.

### M5 — The scene on a real engine

**At its end:** the acceptance's scene on a real engine (B9) has been run
under a scratch home against the code as M4 leaves it, each step observed
or its failure fixed and tested. This milestone's deliverable is knowledge
and the fixes it forces; it sits here, and not at the end, because the
engine is in M3's and M4's path (a push to a live inbox, a wake, a
hand-off, the order of an engine's hooks), and T1 and T2 each found that
order different on a real engine from what their suites had staged.

**Touches:** whatever of M1 to M4 the pass shows wrong, with a test for
each fix in the suite of the milestone that owns it.

**Interfaces:** consumes everything of M1 to M4; exposes nothing.

**Seams:** *a hand-off and what a channel owes* (M2's row D6, M3's first
seam), on a real engine: the suites stage a hand-off by writing the
engine's `continued-in` line; here the engine writes it, in its own order.
Crossed by step 4 of Concrete Steps: the member handed off has a boundary
that holds a position, the thread keeps that boundary byte for byte and
its one delivery record across the hand-off, and a message said to it
after the hand-off, by the reply line of a frame it sent before, arrives
once in the job's conversation.

**Decisions:**

- The pass is Concrete Steps' four steps and nothing wider.
- One completed scene is required before the acceptance. If the executor's
  environment has no engine credentials the milestone reports the scene as
  not run, never as passed, and M11 then owes the whole scene, not a
  rerun of what changed.
- The two repositories are two different projects, and the pass asserts
  it: each carries a `.smns` that names its own hub project of the scratch
  org, as the scene of `T/test-channels-machines.sh` writes them, and the
  two sessions' `joined` events lie in the logs of two different project
  ids, read from the registrations under the scratch home (a bare `join`
  prints a project's name, not its id). Two plain repositories on an
  enrolled scratch machine would both be the machine's own project.
- Both sessions are ones that join: interactive sessions in a terminal
  multiplexer, never a bare `claude -p`, which is no member unless its
  host marks it.
- No word of the endpoint is in this pass: M6 does not exist yet. The
  scratch stand-in lists `channels` and not `reach`, and before step 2 the
  pass reads that the two sessions' records name the same owners, so that
  `sent` is what step 2 must print and a `recorded; the endpoint decides
  its delivery` there is a failure of the staging, not of the code.
- The member whose boundary is observed is the one placed by `channel add`,
  not the creator: a creator enters an empty log (an empty boundary), while
  a thread added by a request enters a log that holds that request, so its
  boundary names a position. CH1's check carried only the empty kind.

**Does not touch:** the gate's limits, `sminos-idle`'s stand-in, the
person's real configuration.

**Proves:** B9, once it has run whole; the composite's delegated unknown
of a non-empty boundary across a real hand-off.

### M6 — Across machines: asking, and carrying out off the consumer thread

**At its end:** a message said into a channel on one machine is uploaded
under the channel's id, reaches the machine of a member that runs
elsewhere, and is delivered there on the endpoint's word: the uplink asks,
keeps the answer in a file, and the daemon's channel pass carries it out,
pushing to a live session, waking a stopped one, holding for one that is
not woken; the reply travels back the same way. A recipient's machine
that turned read-only refuses it there; a word that arrives after the
thread was removed, or after its reach changed, pushes and wakes nothing.
The uplink goes on handling frames while the locks a push, a receipt, an
unanswered ask or a reconciliation would take are held elsewhere and a
launch is stalled. A machine that only wrote into a channel keeps its log
open until what it wrote has gone up. Nothing but the events, their
`reach?` and their `words?` goes up under the channel's id.

**Touches:** `S/sminos_uplink.py` (`ask_words`' channel half, `on_words`,
`on_reach`, `queue_asks`, the asks held, `expire_asks`, `senders_before`
for a frame that carries a message, `may_leave`), `S/sminos_channels.py`
(`asks_due`, `keep_word`, `carry_words`, `unsent`), `S/sminos.py`
(`deliver_verdict` and `deliver_reach` taking a kept word; `holder_due`,
which `holder_owed` and a channel's `reach_due` both ask),
`S/sminos_holder_deliveries.py` (`plan`'s lock, tried),
`S/sminos_daemon.py` (`channel_pass`), `T/endpoint_standin.py` (§8),
`T/channel_wire.py` (`published`), `T/test_channels_wire.py`,
`T/test-channels-machines.sh` (its cases, and this child's scene),
`T/rl10-machines.sh` if a helper is missing.

**Interfaces:** exposes §4. Consumes §3 (`owing`, `owed`, `first_owed`,
`still_owed`, the delivery operation with `owing`), CH1's
`Link.member_on_lane`, `Link.senders_before`, `Link.channels`,
`Link.serves_channels`, `reach_token`.

**Seams:**

- *The uplink and the delivery operation* (M3), which is the consumer
  thread's seam. The uplink never calls `deliver_next`, `deliver_verdict`,
  `deliver_reach`, `holder_push` or a wake for a channel's message: it
  chooses what to ask by M2's selection, queues the question, and on the
  answer writes one file (`keep_word`); the daemon's channel pass, nudged,
  carries it out. Crossed by `T/test_channels_wire.py`, each case with the
  lock in question held by another process, a frame the endpoint sends
  meanwhile handled within the uplink's bound, and the message still owed
  when the lock is let go:
  - *an answer*: the thread store's lock, the thread's delivery lock and
    the channel's registration lock held, the test engine's launch
    stalled at its barrier, and the stand-in's `reach` answer about a
    channel's message arriving: the kept word's file is there and nothing
    was pushed; the locks let go, the daemon's tick pushes one frame;
  - *the choice of what to ask*: an event of a channel for which a receipt
    is held, the receipts' lock held: no ask goes for it this pass, the
    pass ends, and it is asked about on a later one;
  - *an ask the endpoint never answers*: a `words?` and a `reach?` about a
    channel's messages left unanswered past their deadlines with the
    thread's delivery lock held: each is dropped, no delivery record is
    written, and each is asked again at the ordinary interval;
  - *a recipient the plane has no row for*: a message owed to a thread
    whose session joined since the plane last read its project, with that
    project's finisher lock held: the thread is passed by before `owing`
    is asked, no view is read and no ask goes, and it is asked about after
    the plane's next ordinary read;
  - *an upload whose sender the plane has no row for*: a message appended
    by a session that joined since the plane last read its project, with
    that project's reconciliation held up by a lock: the frame is not
    sent, no view is read for it, and it goes up after the plane's next
    ordinary read. A sender that has retired since it wrote waits for
    nothing: its message goes up with no frame, row or no row.
- *Who holds the thread's lock when a word is carried out.* `deliver_reach`
  and `deliver_verdict` take the thread's delivery lock themselves, on a
  file descriptor of their own, so a caller that held it would wait on
  itself. `carry_words` takes none: it hands each kept word to the entry
  point, which takes the lock once and, under it, reads the word again,
  checks it and removes it before it acts. Crossed by: two real processes
  carrying one kept word at once, under a timeout: one frame is pushed,
  the other process does nothing, and neither hangs.
- *A kept word and what was asked* (M2's membership). A word is bound to
  the thread, the session it held then, the recipient's reach
  (`reach_token`) and the event it was asked about (`event_key`). Crossed
  by: the stand-in's reply to a `reach?` is kept back, and before it is
  released the thread is removed; removed and added again; handed off;
  its session's access changed. In each the released word is dropped
  unused, the test engine records no launch and the inbox no frame from
  that word; after the hand-off and after the change of access the
  message is asked about again, for the session and the reach as they are
  then, and delivered on that answer; after the removal and add it is not
  owed.
- *A word and a launch* (M3's last check after a launch). Crossed by: a
  word carried out for a stopped thread, its launch stalled, the
  session's access changed meanwhile, the barrier lifted: no text is
  handed over on that word; the message, owed to a session that now runs,
  is asked about again and delivered on the new answer with no second
  launch. And apart from it, the same with the machine turned read-only
  meanwhile, for a message from another machine: no text is handed over,
  and the message is refused `refused-read-only` there, as it is before a
  push.
- *The ask and the push, over a receipt* (M3's receipts). A stopped
  thread's event whose receipt was handed to a process that is gone and
  never admitted is, for the push, a retry that wakes the thread
  (`holder_owed`), and for the ask, as `reach_due` reads a receipt today,
  nothing to ask about: where the endpoint decides reach the push then
  waits for a word no one asks for. Both read one classification
  (`holder_due`). Crossed by: `T/test_wake_delivery.py`'s `Awaiting`
  fixture staged in a channel on a machine whose endpoint decides reach:
  one `reach?` goes, the answer is kept, the thread is woken once, and the
  event is settled.
- *Where an ask is checked.* Membership and the boundary are read where
  the selection is made, again where the ask is queued (`queue_asks`, the
  last step before the frame goes, which today rechecks the hold alone),
  and again where the push or the wake is made (M3's last check). Crossed
  by: a removal between the selection and the queuing sends no question.
- *What this machine held at the boundary* (the fold's fifth correction),
  on two machines: a message written on `alpha` during a membership of a
  thread on `beta` and relayed to `beta` only after that thread was removed
  and added again is pushed; the same message relayed before the removal
  is not pushed after it. And row D13: a message relayed late that names a
  thread whose old session another member on `beta` now holds, under
  another thread id, is pushed to the thread named and never to that
  member.
- *Sending and the wire* (M4). An upload of a channel's log is preceded by
  the member frame of each sender that is a member of a project now, and
  by none for a sender that has retired since it wrote. Crossed by, on the
  stand-in, for a member's message, a non-member's and a private sender's
  stream: the sender's member frame, under its own project, was received
  before the `events` frame that carries its message under the channel's
  id; and a message whose sender retired before the upload goes up with
  no frame.
- *A machine that writes and holds no member* (C5: "what this needs of the
  sender's machine"). Crossed by: on `gamma`, which holds no member, a
  session says `--in` the channel: the event is uploaded under the
  channel's id from a log opened with `follow`, preceded by its sender's
  member frame under its own project, and is delivered on `alpha` and
  `beta`; the member's reply reaches the sender in its project on `gamma`;
  the channel does not leave `gamma` while that event, or a person's
  message still in `gamma`'s queue, has not gone up; and a say into a
  channel that has already left `gamma` brings its log back and goes up.
- *Outcomes* (the fold's second correction). Crossed by: a message from
  `alpha` is pushed and settled on `beta`, `beta`'s uplink then runs its
  upload pass (which drains an outbox where there is one), and only then
  are `beta`'s stand-in's frames given to the checker: no `session` frame
  of kind `delivery` names the channel, and the channel's home holds no
  outbox file.

**Decisions:**

- The uplink asks about a channel's messages in a pass of its own, behind
  its message asks and beside `ask_requests`, run only while `Link.channels`
  holds a channel a thread of this machine is in: `asks_due` gives, for
  each such thread, the first owed event of each writer by M2's selection,
  and says of each whether the endpoint's word on a person's words or on
  reach is needed, by the rules `words_due` and `reach_due` apply to a
  project's (§4). It needs `channels` in the welcome, and `reach` for a
  `reach?`. The two loops' own skips by session (a member whose current
  session no entry names; the cache by session and record) are not on
  this path.
- The receipts' planner, which `reach_due` asks for an event a receipt is
  held for, takes the receipts' lock without a bound today
  (`sminos_holder_deliveries.plan`). For a channel's choice it is only
  tried (`plan` gains a deadline, absent for every caller of today's), and
  an event whose inquiry found the lock busy is left for the next pass.
  `exists`, which reads a receipt's file under no lock, is asked as it is.
- Whether an event a receipt is held for is next pushed is one function,
  `holder_due`, reads only: the plan says `push` or `legacy`, or it says
  `awaiting` while no process runs and the session is the current one of a
  lane A thread. `holder_owed` answers `HOLDER_RETRY` by it, for every
  log, as it does today by the same two tests; `reach_due` chooses by it
  where it is given `owing`. A project's `reach_due` keeps its own test
  (`push` or `legacy`), so a project's ask is today's call for call; the
  same fault there is the base's and gets a TECH-DEBT row here, with what
  would promote it (a report of a stopped session, on a machine whose
  endpoint decides reach, whose message with a receipt left by an earlier
  process is never delivered).
- The row a channel's choice reads for a thread is the plane's, and a
  thread the plane holds no row for is passed by before `owing` is asked:
  `owing` takes its row from its caller and never looks one up (§3), so
  nothing on the consumer thread reaches a view through it.
- The frame's `session` is the thread's current session, whatever session
  the event's entry names: the endpoint finds its recipient by the frame's
  `session` alone, as for a request (`ask_of`).
- Before an ask, the recipient's member frame is on the lane under its own
  project, read as the plane last read it (`Link.member_on_lane`): the
  endpoint answers a `reach?` nothing, and a `words?` `peer` at once, for
  a session it holds no member of, and the second would hand a person's
  words over as a peer's.
- A channel's ask that passes its deadline unanswered is dropped and asked
  again at the ordinary interval, and that is all: nothing is written on
  the consumer thread, no attempt is counted for a `words?` there (a
  project's counts one in the session's delivery record,
  `words_unanswered`), and `expire_asks` reads no `member` from an ask
  that holds none. So a channel's message the endpoint never answers is
  never given up (Constraints, accepted). What it holds back is the later
  messages of the same writer to the same thread, which wait behind it
  (`first_owed`); no other writer's, and no other thread's.
- A frame of a channel's upload waits for the plane only for a sender
  that is a member of a project now. One that fresh membership says has
  retired owes no frame, as in CH1, and its message goes up without one.
- A frame of a channel's upload that carries a message reads each
  sender's member frame as the plane last read it (`member_on_lane`), and
  while the plane holds no row for a sender the frame is undrawn for a
  later pass. A frame that carries CH1's kinds alone keeps today's path
  (`member_under`), which is CH1's and has its row in TECH-DEBT.
- What the endpoint's word is good for: to begin being carried out within
  `WORD_KEPT` (sixty seconds) of its answer, and across one launch, as a
  project's verdict is good across its launch today. One the daemon has
  not begun to carry out by then is discarded where it is found, and the
  uplink, which remembers until then that it holds one, asks again at its
  ordinary interval. What this machine can read is read again after the
  launch (M3); what only the endpoint knows is not seen inside that
  window, and is on the accepted list. Reason: reach is asked for each
  push (P5 O18 D8), so an answer stands for one push and for nothing
  later; sixty seconds covers a nudged tick behind a slow one.
- A `peer` word on a person's message, where the endpoint decides reach,
  is not kept: the `reach?` about the same event is queued, as `ask_peer`
  does, and its answer is what is kept. A reply that names no verdict
  consumes nothing and its ask stays held to its deadline, as `main` now
  has it for every ask.
- The daemon's channel pass carries kept words out before its own
  delivery (`carry_words`, then `deliver`). A sender's own call carries
  out none: it has just written the message.
- The leaving rule counts messages (`Link.may_leave`, which today counts
  requests alone through `outstanding`): a followed channel does not
  leave, and one that left comes back, while this machine's writers hold
  there an event the upstream has not taken, or a queued append (`unsent`,
  §4: what `daemon owed` lists for it as `upload` and `queued`). A write
  after the channel left reopens its log.
- A person's message that waits in this machine's queue has no position
  until it is released (`channel_positions` reads the log's writer files
  alone). It is then past every boundary taken while it waited, and is
  owed to the thread it names if that thread is a member when it enters
  the log (Constraints, accepted).
- A non-member's message and its copy are two events in two logs, each
  uploaded in its own log's turn; neither waits for the other, as for a
  message to another project today.
- A message for a machine on 1.54 needs no code here: the sender reads
  what it reads for any thread on another machine. M11 shows the receiving
  side.

**Does not touch:** `Link.open_channel`, `Link.on_snapshots`, the hello,
`member_frame`, `Plane.refresh`, the project's `ask_words` loop, its keys,
its expiry and what it carries out on the consumer thread,
`Link.member_under` and a request's upload, `words_unanswered`,
`T/rl10-conversation.json` (M7).

**Proves:** B1, B2 and B4 across two machines; B11 on the wire (the frames
of a machine that holds no channel, compared with the merge base's). Its
tests pin, beside the seams: one ask out at a time for a thread and a
writer; a `refuse` settled `refused-reach` on that machine with no frame
back; a `peer` word on a person's message followed by a `reach?` about the
same event; a held recipient asked about nothing; a thread whose record
holds an open entry asked about nothing; a word older than `WORD_KEPT`
carried out by no one and its message asked about again; two words for
one event (the uplink restarted between) pushed once; an unanswered head
of one writer holding back that writer's next message to the same thread
and no other writer's; a notice tagged to a
member on a cut-over machine, recorded in M4, delivered here on the
endpoint's word as a peer's frame from `<program>@<machine>`; and the
checker over every stand-in, with this child's rules.

### M7 — Held to MAWS's fixture, and what a channel costs

**At its end:** MAWS's conversation fixture with its cases for a message
under a channel's id is this tree's copy, byte for byte, and every line of
it replays; and the figures of what a channel costs a machine are
recorded: the listing, a tagged `say`, the idle uplink and an upload, for
a machine that knows no channel, one that follows channels and holds no
member, and one that holds members.

**Touches:** `T/rl10-conversation.json`, `T/rl10-conversation.source.json`
(MAWS's master `5a88bcd83`, the fixture's blob `5ffdd4a2`: cases 16 to
19), `T/rl10_conformance.py` (only what those cases need of the harness),
`T/bench_scale.py` (`--channels N` and `--held H`, the capabilities its
stand-in lists, `verbs`), `T/test_scale.py` if the scale's shape is
asserted there.

**Interfaces:** consumes the wire as M6 leaves it; exposes nothing.

**Seams:** *sminos and the endpoint* (M4, M6). The stand-in shows that
sminos sends the right frames in the right order; that the endpoint then
attests an upload from its sender's member frame, and holds an upload
that names a recipient its policy cache does not know until the log's
`snapshots?` is answered, are MAWS's behaviours, which only its fixture
states. Crossed by the replay, each line `ok` with no amendment: case 16
(a session that is a member under its project alone uploads a `say` under
a channel); case 17 (a non-member's `say` under a channel and its
`reach?`, `deliver` for one recipient and `refuse` for another); case 18
(a `human` under a channel and its `words?`: a phone's words answered
`peer` before the recipient's member frame and `words` after it, the
recipient private and shared with that member at `converse`; another
machine's human writer answered `peer`; this machine's own human writer,
to a thread of its own, answered `words`); and case 19 (that same event
carrying a notice, answered `peer`).

**Decisions:**

- The copy is taken at MAWS's master `5a88bcd83`, byte for byte, with
  `T/rl10-conversation.source.json` naming that commit and blob. A line of
  a new case that sminos cannot send as written goes to the holder as the
  exact line, before anything is amended (CH1's rule).
- The zero-channel gate is not touched: `sminos-idle` runs as it runs,
  against a stand-in that lists no capability.
- The bench's channel scenarios run against a stand-in that lists
  `channels` and `reach`, since without them the uplink skips the work to
  be measured. Three shapes, each named in the output: no channel known
  (the gate's shape); channels followed with no thread of this machine in
  any; channels held. The second must read no channel's log for a debt,
  and the bench shows it by the count of reads.
- `verbs` times only commands that succeed, and says so: it checks each
  exit code and prints a failure as one. Matched pairs: `list` by a thread
  in thirty channels and by the same thread in none; a tagged `say` by a
  thread in thirty channels and by one in none (M1's one record read, and
  the roster's sweep); `channel show` of one channel on a machine that
  knows one and on a machine that knows thirty. Before it times, the bench
  reads from the sender's record that it holds the memberships.
- The upload scenario says K messages into a channel from one sender and
  from several, and reads the uplink's calls for the upload pass: every
  distinct sender of every drawn frame of a channel's log calls
  `member_project_now`, which reads every registration and each project's
  own events of that session, and CH1 paid it for a request where this
  child pays it for a message.
- `rosters` reads every project's view once and sorts its rows by channel,
  so its cost follows the number of projects and members, not of channels;
  the figures are taken at the MacBook's shape with thirty channels. They
  go to Surprises & Discoveries and to the holder, who decides with them
  whether the deferred index of statements, and the TECH-DEBT row "A
  roster can list a thread's obsolete row for a moment", are promoted
  (open point 7). Nothing is built on them here.

**Does not touch:** the gate's limits and its stand-in's shape for the
gate, `S/` (a fault the replay or the bench shows is fixed in the
milestone that owns it, with a test there).

**Proves:** the wire half of B1 and B2 against MAWS's own statement of it;
the composite's delegated unknown of a roster's cost. Its report gives the
replay's count of lines, the timings as pairs, the idle figure for each of
the three shapes beside the gate's, and the upload's cost a message.

### M8 — The lead, and whose words a post is

**At its end:** at a terminal, `sminos channel lead desk-integration
worker` asks for a typed yes and writes the lead; inside a session, and
where there is no terminal, it is refused. An untagged message the owner
then types into the channel is addressed to the lead, wakes it if it is
stopped, and on the lead's own machine reaches it as its human's words. A
lead event under a session's writer changes nothing; a lead that ended or
left is ignored; a machine's notice with no tag stays untagged, and a
notice tagged to the lead reaches it as a machine's notice whatever the
endpoint's word. A reader that may not read a private lead reads no lead.
`sminos channel show` prints the lead.

**Touches:** `S/sminos_channels.py` (`lead_of`, the verb, `show`),
`S/sminos.py` (the parser's `channel` family and its usage line, `cmd_say`'s
untagged branch for a channel through `speak`, the docstring),
`T/test_channels_lead.py` (new), `T/test-channels.sh`,
`T/test-channels-machines.sh`, `T/channel_wire.py` (the kind).

**Interfaces:** exposes §5. Consumes §2 (`speak`), §3, §4 (the `words?`
under a channel's id, a kept word), `sminos_visibility.confirmed`,
`stream_choice`, `notice_of`, `owner_event`.

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
- *A notice and the lead* (X8). Crossed by: with a lead set, a notice
  tagged to the lead, under a stand-in that answers `words` and under one
  that answers `peer`: in both it arrives as an inbox frame whose sender is
  `<program>@<machine>`, with no reply line, the bridge is handed nothing,
  and the manager's classifier does not mark it the owner's.
- *The lead and the roster* (M1). A lead is in effect only while its thread
  has a row in the roster. Crossed by: the lead removed, ended, and
  returned: an untagged post is untagged, untagged, and addressed again.
- *The lead and a private thread* (the design review's sixth finding). A
  thread's id may be a session's (a seat made over a session takes that
  session's id), so a lead written plainly could show a private session's
  id to every reader of the channel. Crossed by: a private thread named
  lead, on the same machine and on another whose policy the writing
  machine's endpoint holds; the event as the stand-in received it is
  under the human writer's stream of that thread's audience; a machine
  outside that audience holds no such event and reads no lead.

**Decisions:**

- The verb is refused inside a session before anything is read (the test
  every such verb makes: `CLAUDE_CODE_SESSION_ID` set), then `confirmed`
  asks at `/dev/tty` itself, which refuses where there is none.
- The event takes the audience of the thread it names, as a request's
  does (`stream_choice` for that one recipient): it carries the thread's
  current session beside its thread id, and goes under the machine's human
  writer, plain for a thread that is not private and under that writer's
  audience stream for one that is. A lead of `none` carries neither and is
  plain. Where the stream choice refuses (the thread's audience is not
  known here) the verb is refused in the choice's own words, as `channel
  add` is. The endpoint uses only an audience it knows: a local session's
  from its member frame, a remote one's from its policy cache, and one it
  does not know is held while the cache rebuilds and counts as listed
  after, which is today's rule for any reference to a session of another
  project.
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
and its `--json` with and without a lead (no key without one); and the raw
upload and a less-privileged reader's copy of the channel's log, read for
the private lead.

### M9 — What reads a session's exchanges reads a channel's

**At its end:** the list of exchanges a session is given after a compaction
or a resume names a peer it spoke with only in a channel, with a tag that
reaches it, also after either has left the channel; the manager's window
marks an owner's post delivered from a channel as the owner's, and tells
apart two events of one writer and seq that lie in two logs, of two names
or of one. Nothing a session or the bridge does while its thread is in
channels writes a word to a human under a channel's id, and a stopped
thread's questions are closed for its project alone.

**Touches:** `S/sminos.py` (`roster_text`, `_roster_exchanges`,
`_roster_peer`), `M/manager_window.py` (`frames`, `OwnerWords`),
`M/manager.py` (`cmd_transcript`'s logs), `M/CLAUDE.md`,
`T/test-guide.sh`, `T/test_channels.py` (its case
`test_a_resumes_roster_gives_no_tag_through_a_channel`, which pins today's
answer), `T/test_manager.py`, `T/test_channels_say.py` (B7).

**Interfaces:** exposes §6's two readers. Consumes Y1 (`known_channels`,
`roster`), §1, §2 (the event's `thread` and its entries').

**Seams:** *the event's log and its reader* (M4). A member's message in a
channel carries neither `from_project` nor a copy, which are what
`_roster_exchanges` reads a cross-project exchange from today; so a
channel's exchanges are invisible to it until it reads the channel's own
log. Crossed by `T/test-guide.sh`: two sessions that exchanged messages
only by `say --in`, then a `compact` payload: each is listed for the other
with a tag that, run, reaches it; and the same after the reader was
removed from the channel, and after the peer ended (listed as ended, by
the name the message gave it).

**Decisions:**

- `roster_text` reads, beside the session's project and its launch
  directory's, the logs of the channels its thread's own statements have
  named, those it has left included: the ten whose latest statement is
  newest (`ROSTER_CHANNELS`), of those registered on the machine, each
  read once inside the budget (`ROSTER_BUDGET`) that bounds the whole
  already. The statements are in the session's own project's log, which
  it reads anyway. Reason: two members' exchange leaves no copy in any
  project, so a reader that left the channel would otherwise be told
  nothing of it.
- In a channel's log "mine" is by thread: a message the reader's thread
  sent (the event's `thread`) or one that names it (an entry's `thread`).
  A peer is its thread, found now by its id (its row in its own project,
  wherever its session went), and tagged by
  `_roster_tag` with its own project's tag, never one qualified by the
  channel, so the tag is right after either leaves. Where no row can be
  found for it the line carries the name the event gave it (`from`, or the
  entry's `alias`) and says no tag reaches it. A peer met in a project and
  in a channel is one row, its last exchange the newest.
- A message from outside a channel needs nothing new: read in the
  channel's log it carries `from_project`, which is how
  `_roster_exchanges` already finds an inbound peer's own project, and the
  sender's copy names its recipients under the channel's id, which
  `_roster_peer` now resolves to each one's own project.
- The manager never takes a display name alone for a log. `OwnerWords`
  holds, under a frame's log name and ref, every candidate event of every
  log of that name it was given, each with its log's id; a frame is the
  owner's only when exactly one candidate under its key has its body; no
  candidate, or more than one, certifies nothing, and the entry is marked
  as an unverified owner line is today. `cmd_transcript` builds it from
  the subscription's project's log and the logs of the channels known on
  the machine (`known_channels`), since a window may look back past a
  membership.
- B7 is proved, not built: every writer of a word to a human takes its log
  from the session's own project (`session_project`), `append_host` raises
  for a channel, and `close_questions` walks `known_projects`. The tests
  drive a session in two channels through a turn that delivers a channel's
  frame by the inbox and one by the bridge, two questions, an answer to
  the first, a stop and the sweep: the second question is then closed in
  the thread's own project; a control question left open by another
  session in another project is still open; and no log of a channel holds
  a host kind.
- *(Added 2026-11-22, the holder's check on M3's bridge key.)* Since M3 a
  person's words reach the bridge under `project = <channel>#<thread>`
  (Decision Log, "M3 as built"), and the bridge keeps that field. B7 is
  proved with a bridge that has actually taken a channel's frame under
  that key, twice: the bridge as a 1.54 session has it loaded, and this
  tree's. After it, that session's next words to its human and a question
  it opens land in the thread's own project, and nothing is appended or
  queued under the channel's id, nor under the `#` form as a log (no
  directory, no queue entry, no outbox, no frame under it). `T/
  test_channels_delivery.py`'s
  `test_a_persons_words_reach_the_bridge_scoped_by_the_thread_they_are_owed_to`
  pins only the key the bridge is given, not what the bridge does after.

**Does not touch:** `append_host`, `export_live`, `close_questions`,
`session_project`, the manager's subscriptions (one project each, as
today: a thread has one project), `M/manager_ledger.py`,
`M/manager_serve.py`, the manager's `SKILL.md` (M10).

**Proves:** B7 and B8. Its tests pin: the manager's classifier on a frame
from a channel whose ref an event of the project's log also carries, with
different bodies, where the two logs have different names and where they
have the same name (each marked by its own body; with the same body under
the same name, neither certified); a non-member that said into a channel
and never received an answer, listed for itself by its copy and for the
member by the channel's log; a peer met only in a channel that has since
ended; and the roster of a session in no channel, byte for byte.

### M10 — What sessions are taught, and its evaluation

**At its end:** the session-start guide, `sminos/skills/sminos/SKILL.md`,
the spawn preamble and the manager's skill speak of threads and channels
and teach what M1 to M9 built; the evaluation of Concrete Steps has been
run on the texts as they were and as they are, and its record is in the
Decision Log; the reply line's debt row is closed or answered.

**Touches:** `S/sminos.py` (`guide_text`; and a channel's frame's reply
line only under the condition below), `sminos/skills/sminos/SKILL.md`,
`sminos/skills/sminos/references/spawn-preamble.md`,
`sminos/skills/manager/SKILL.md` and its `references/digest-brief.md`,
`sminos/hooks/CLAUDE.md`, `T/test-guide.sh`, `T/run-sminos-tests.sh` (the
preamble's pinned lines), `docs/doperpowers/TECH-DEBT.md` (the reply
line's row).

**Interfaces:** exposes §7. Consumes the CLI as M1 to M9 leave it.

**Seams:** *what is taught and what the doors say* (M4, M8). Every command
a text shows is run, as written, against the tree in the evaluation's
live scenario, and every refusal a text explains is the sentence §2
gives.

**Decisions:**

- Through doperpowers:writing-skills, by its method: a baseline first, on
  the text as it is; a line the baseline already produces is cut; five
  samples or more a variant, read by hand. §7 lists what each text must
  come to say and what it must stop saying; the wording is the
  evaluation's to settle.
- Both arms of every scenario run the same executable, this tree's: the
  baseline arm is this tree with the texts alone as the merge base has
  them (the three files, and `guide_text`'s lines), so that a difference
  between the arms is the texts' and not a command's that only one of
  them has.
- `send` leaves what sessions are taught (D5, the owner): the skill keeps
  it only as the script's verb (`--wait`).
- The reply line (the TECH-DEBT row "A peer message's reply line still
  models a double-quoted body…", due here). Its absolute path stays, for
  the row's own reason: a recipient may run without the plugin's `bin/`.
  A project's frame keeps its line byte for byte, whatever the evaluation
  shows: a change to every frame is the owner's, and parent line 8
  promises a session in no channel what it had. Whether a channel's
  frame's line gains words is decided by scenario E4 (a reply that must
  carry code): if no sample of the baseline puts a live backtick, a quote
  or a `$` into the double-quoted form, the line stays and the row is
  answered as measured and taught; if one does, a channel's frame's line
  gains, on the same single line, where the same tag goes on standard
  input, in §7's form, and the row says that a project's frame is the
  owner's to change (open point 6).
- The manager's skill is rerun on its own terms (`M/CLAUDE.md`: a change to
  its skill or brief reruns its pressure scenarios, and for the brief a
  replay update).

**Does not touch:** any verb's behaviour; `sminos help` (M4 and M8 wrote
it); a project's frame; the backtick guard (its verb list already holds
`channel`, and this child adds no verb beside it).

**Proves:** B10; X6. `T/test-guide.sh` and the preamble's pins pass on the
new lines.

### M11 — Older copies, what is written beside the code, the version, and the acceptance

**At its end:** `T/test-older-cli.sh` runs 1.27.10, 1.51.0, 1.52.0 and
1.54 beside this code over a store whose channel holds messages, a lead
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

**Seams:** *a refusal lifted and a copy that still has it.* 1.54 refuses
every say into a channel and delivers none; this code writes them. Crossed
by the suite's 1.54 arm below, the two copies over one store.

**Decisions:**

- 1.54.1 is pinned as the merge that released it
  (`e678dfb711164f9925451e2a504bc3aefde845c5`), fetched as the other three
  are, and it gets an arm of its own, since the suite's every-copy
  expectations are a copy's from before channels and its store is not
  enrolled. The 1.54 arm's home is
  enrolled, cut over to a stand-in that lists `channels`, so that 1.54's
  own `channel add`, `remove` and a return run for real. Its
  expectations: it wakes a thread its human opened, as 1.52 does; it
  ticks no channel as a project and lists none as one; it refuses `join
  <channel>` itself; its return writes the boundary anew; it refuses a say
  into the channel in its own sentence; and it never delivers a channel's
  mail.
- For 1.54, compared with the same store holding an empty registered
  channel: its `list`, `list --json`, a tagged `say`, `send`, `channel
  show` and its `daemon tick` over a channel that holds messages, a lead
  and a delivery record of this code's; the delivery record is then byte
  for byte what it was, and the thread's `channels`, `began` and
  `answered` are what they were. Then this code over the store 1.54 left:
  a message that arrived while 1.54 ran is pushed once when the thread was
  a member throughout, and never when 1.54 removed and added it after the
  message arrived.
- For the three copies from before channels, over the unenrolled store
  this code staged: each copy's verbs and its tick do what they did over
  the same store with an empty channel, push nothing from the channel and
  leave the delivery records there as they were. A copy that joins a
  session into the channel's id by hand is a case of its own, asserted as
  CH1 left it (the undo), not a proof that such a copy never delivers
  there.
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

**Does not touch:** the guide and the skill (M10 closed them), the fixture.

**Proves:** the older-copy clauses of B4 and of C5's "Between releases";
B11 whole (the gates on the final head, compared with the merge base, and
the final exchange of two sessions that use no channel on a machine that
knows channels, their frames and reply lines included, compared with the
merge base's); every item by the proof map, on the final head.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-channels-ch2`).

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_channels_names.py
    python3 -B sminos/tests/test_channels_debt.py
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
`FAIL` line per line of the conversation it plays: 121 at CH1's copy, and
more from M7's copy of MAWS's fixture, which adds cases and changes none.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-channels,sminos-idle,sminos-mods,shell-lint,repo-checks

with `mods-types` where a mod changes and `version-bump` in M11. Expected:
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
| B1 `say --in` and `@<channel>/<alias>`: delivered framed as from the channel, a stopped member woken, the reply by the frame's line in the channel's log; a say with neither lands where it does today; `--in` with a tag that resolves elsewhere refused | M4: `test_channels_say.py`, `test-channels.sh`; M3: `test_channels_delivery.py` (the frame, the wake); M6: `test-channels-machines.sh` (another machine); M7: the replay (cases 16, 17); M5 (a real engine) |
| B2 `@all` reaches the live members, an untagged post prompts no one; a thread that is no member is refused no form: its message in the channel's log with `from_project` and a copy in its project, delivered, framed as from outside, answered in the sender's project; the sender told in one line; nothing of the channel's pushed to it | M4: `test_channels_say.py` (`Member`, `Outsider`), `test-channels.sh`; M3: `test_channels_delivery.py` (the frame, the reply line's two forms); M2: `test_channels_debt.py` (nothing owed to a thread that is no member); M6: `test-channels-machines.sh` (a machine that holds no member); M7: the replay (case 17) |
| B3 a bare `@alias` through a shared channel; two answers refused with `alias#short`; a name a project and a channel both answer refused | M1: `test_channels_names.py`, `test-channels.sh` |
| B4 what a channel owes follows membership | M2: `test_channels_debt.py` (§3's rows, as a debt; `daemon owed` run cold); M3: `test_channels_delivery.py` (as pushes; the hand-off's two interleavings; an attempt the boundary has passed, and one whose writer's file could not be read; an open entry, from both sides; a move to another project, a tie, a change of lane, a session with no record; a launch crossed by a change of reach, of the machine's policy and of the signer; two threads one event names over one session's receipt); M6: `test_channels_wire.py` (a late word; a word across a launch; two carriers of one word; a stopped thread's receipt asked about and woken for), `test-channels-machines.sh` (what the machine held at the boundary; a late import after a session's reuse); M11: `test-older-cli.sh` (a message that reached the machine while it ran 1.54; a return an older copy made) |
| B5 a reply after its sender left is delivered to that thread in its own project, the replier told, and reaches no other member; a notice written into a channel by a machine that holds no member | M1: `test_channels_names.py` (the rule); M4: `test_channels_say.py` (the reply line run); M6: `test-channels-machines.sh` (the removal relayed first; the notice from a third machine in the pool) |
| B6 the lead | M8: `test_channels_lead.py`, `test-channels-machines.sh` |
| B7 no word to a human under a channel's id; a stopped thread's questions closed for its project alone | M9: `test_channels_say.py`; M3 and M8 (after each push); the checker in every suite that runs an uplink |
| B8 the exchanges after a compaction or a resume; the manager's window | M9: `test-guide.sh`, `test_manager.py` |
| B9 a real engine, and the roster's cost | M5, completed; M11 for what changed since, or whole if M5 could not run it; M7 for the roster's cost, which a bench measures (the Decision Log says why not the engine) |
| B10 the skill's evaluation | M10 |
| B11 parent line 8 for this surface | every gate at every milestone; M1 (a sender in no channel reads no roster); M4 (`say` and `chat` compared with the merge base's); M6 (the frames of a machine with no channel); M9 (the roster of a session in no channel); M11 (the final exchange of two sessions that use no channel, on a machine that knows channels) |

**M5, the scene on a real engine.** In a scratch tree `<scratch>`:
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
over, a stand-in serving it with `channels` among its capabilities and
without `reach`, and the scratch daemon (`sminos daemon run --interval 5`)
runs in a multiplexer of its own. `<scratch>/a` and `<scratch>/b` are git
repositories, each with a `.smns` naming a hub project of its own in the
scratch org. Never the person's real configuration.

1. In `<scratch>/a` an interactive session A, in `<scratch>/b` an
   interactive session B, each in a multiplexer window; one turn each,
   both left open. Expect first: the two sessions' `joined` events lie
   under two different project ids (the two directories under
   `<scratch>/sminos/projects/` whose registrations name `<scratch>/a` and
   `<scratch>/b`), and the two sessions' records name the same owners. A runs `sminos channel create probe` and `sminos channel add
   probe <B's short>`. Expect: `sminos list` from both shows `# probe`
   with both, and B's thread record holds for `probe` a boundary with one
   position (A's request).
2. A runs `sminos say --in probe "@<B's alias> <a nonce>"`. Expect: A's
   line for B reads `sent`; B's transcript gains one frame whose first line
   is `[sminos chat probe <ref> from <A's alias>… → @you]` and whose last
   is the reply line naming `@<probe's id>/<the first eight of A's thread
   id>`. B is asked, in its next turn, to answer with the line its frame
   gives. Expect: `recorded <ref> in probe`; A's transcript gains B's frame
   from `probe`; the channel's log holds the two messages, each entry of
   their `to` carrying a `thread`; neither repository's log gained one, and
   neither message carries `from_project` or `copy`.
3. B's terminal is closed. `sminos list --stopped --channel probe` shows B
   `stopped`. A runs `sminos say "@probe/<B's alias> <a second nonce>"`.
   Expect, within two minutes: one background process holds B's session
   id (one more job in `claude agents --json --all` than before, with that
   `sessionId`), no copy of the session exists, B's transcript holds the
   second nonce once, and the last paragraph of that frame is the
   machine's `[sminos] ` line saying it was woken.
4. B is handed to a background job by the engine's own hand-off from
   inside the session (as T1's and CH1's passes did it): B's job is
   stopped, `claude --resume <B's session>` opens it in a terminal, and
   `/background` there hands it off (on 2.1.330 a resume of a running
   background job only attaches to it, and `/background` in an attached
   view only detaches; M5's pass). Expect, within two ticks: one
   row for B's thread in `# probe`, under the job's session id; the
   record's boundary for `probe` equal, byte for byte, to step 1's, and
   not empty; and one delivery record under the channel's log for B's
   thread, the file it was before the hand-off. A runs the reply line of
   the frame B sent it in step 2, with a third nonce. Expect: the third
   nonce once in the job's transcript, none in the session it continues.

Afterwards every scratch job is removed, the multiplexer and the scratch
daemon are stopped, and the report keeps what each step printed beside the
commands. A step that does not show what it expects is diagnosed: a fault
of M1 to M4 is fixed with a test in the suite of the milestone that owns
it; an order of the engine's hooks the suites did not stage is added to
the suites' staging.

**M7, the fixture and the figures.**

    python3 -B sminos/tests/rl10_conformance.py sminos/skills/sminos/scripts sminos/tests/rl10-conversation.json
    python3 -B sminos/tests/bench_scale.py verbs sminos/skills/sminos/scripts --preset macbook --channels 30
    python3 -B sminos/tests/bench_scale.py verbs sminos/skills/sminos/scripts --preset macbook --channels 0
    python3 -B sminos/tests/bench_scale.py run sminos/skills/sminos/scripts --preset macbook --words 0 --working 30 --warmup 60 --seconds 10 --pycalls 60 --channels 30 --held 0
    python3 -B sminos/tests/bench_scale.py run sminos/skills/sminos/scripts --preset macbook --words 0 --working 30 --warmup 60 --seconds 10 --pycalls 60 --channels 30

Expect: the replay's first line names MAWS's commit and blob as
`T/rl10-conversation.source.json` gives them (`5a88bcd83`, `5ffdd4a2`),
and every line is `ok`, cases 16 to 19 among them. Each
`verbs` run prints one line a command with its timing, and `FAILED` with
its exit code for a command that did not succeed (none may). The two
`run`s print the idle uplink's calls a second with thirty channels
followed and none held (`--held 0`), and with thirty held; the second also
runs the upload scenario and prints its calls a message. The report gives
each timing as a pair, the three idle figures beside the gate's, and the
upload's cost.

**M10, the evaluation.** By doperpowers:writing-skills, each scenario on
two arms that run the same executable (this tree's): the texts as the
merge base has them, and the texts as edited. Five samples an arm, each
sample a fresh session, read by hand. Two kinds:

- *Live* (E1, E3, E5): a fresh session that joins: a headless `claude -p`
  whose host marks it a member, as `sminos/tests/mods/live-bridge-check.py`
  starts one, or an interactive one; a bare `claude -p` is no member and
  is given no guide. Under a scratch home as in M5, on a machine cut over
  to a stand-in that lists `channels`, with two other sessions staged as
  threads of two other hub projects, their project ids asserted different
  before the sample runs. What passes is read from the store afterwards,
  not from what the session says.
- *Single-shot* (E2, E4): a fresh session with no tools, given the guide
  as `guide_text` prints it for that arm, the skill, a conversation that
  ends in real CLI output, and asked for the commands it would run.

| | Scenario | Passes when |
|---|---|---|
| E1 | "Work with the session in the other two repositories on X; keep the three of you in one place, and tell them what you found." | the store holds a channel it created with the two others placed in it, and at least one `say` of its own in that channel's log that carries what it was to tell them; no message meant for the three lies in a project's log, and none was refused and abandoned (B10's sentence). A sample that created the channel and said nothing fails |
| E2 | a frame from a channel arrives; the session must answer | it answers with the frame's reply line, unchanged but for its text |
| E3 | the session, in no channel, is asked to tell a channel's members something once | its message lies in the channel's log, sent once; it reads the line it is given and neither adds itself unasked nor sends the same text again by another route |
| E4 | a frame from a channel arrives whose answer must quote code with a backtick and a `$` | the command it gives passes the text unharmed (standard input), and reaches the sender |
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

**M11, the acceptance.** The gates GREEN on the final head; the older-copy
suite; then the scene, which M6 builds as a second scene of
`T/test-channels-machines.sh` and M8 extends, run alone, printing each
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
   channel's id and the first eight of A's thread id.
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
6. A runs `sminos channel remove desk-integration` (itself), and a pass
   relays it. B runs the reply line of step 2's frame: recorded in A's
   project's log, not the channel's, with one line saying that A is not
   in the channel now and was sent to directly; A receives it. A runs
   `sminos channel add desk-integration`, and after a pass B's line run
   again is recorded in the channel's log and reaches A. A runs `sminos
   channel remove desk-integration <B>`, and after a pass `sminos say
   "@desk-integration/<B's alias> x"` is refused: no member of the channel
   answers that name, and the refusal says where B is.
7. A runs `sminos channel env add desk-integration gamma`. At a terminal
   on `gamma`:
   `sminos say --notice devcloud --in desk-integration "lease ends"`.
   It is recorded; after a pass `sminos chat desk-integration` on `alpha`
   shows it from `devcloud@gamma`, and no session was prompted.
8. At a terminal on `alpha`, `sminos channel lead desk-integration <S>`
   with a typed yes, then `sminos say --in desk-integration "do it"`: the
   event names S's thread in `to`, the stand-in was asked one `words?`
   under the channel's id and answered `words`, and S received it as a
   person's words are handed to a session, never as a peer's frame. Then,
   at that terminal, `sminos say --notice devcloud --in desk-integration
   "@<S> lease ends"`: S receives an inbox frame from `devcloud@alpha` with
   no reply line, though the stand-in's word for it was `words`. The lead
   verb run as A is refused.
9. The checker passes over the three stand-ins and the three stores with
   this child's rules: under the channel's id nothing went up but
   `events`, `reach?` and `words?` frames of the kinds §8 allows, no
   `delivery`, no word to a human, no event there carries `copy`, and
   `from_project` is carried by X's three messages alone.

Then B9 on the final head. If M5 completed the scene, steps 2 to 4 of its
pass are run again only if `S/sminos.py`'s delivery operation,
`S/sminos_channels.py`'s `owing` and `owed`, or the wake changed since,
and reported as not run, with the reason, otherwise. If M5 could not run
it, the whole scene is run here: the acceptance does not close on a scene
that never completed.

Then parent line 8's last comparison, on one machine that knows a channel:
two sessions that are in none exchange a tagged message and its reply by
the frame's line; the two frames as their inboxes received them, reply
lines included, and the two events as the log holds them, are byte for
byte what the merge base's code produces for the same exchange, but for
ids and times.

**M11, the TECH-DEBT rows.** Each row whose trigger names this child, and
what becomes of it:

| Row | Becomes |
|---|---|
| `chat <channel>`, `list <channel>` and a target qualified by a channel are refused | removed: M1 and M4 |
| A return that keeps where a membership began from before the end | kept, saying that this child pushes everything past the kept boundary and unsettled, what was held before the end included (the holder's ruling), and where it is tested (M2's row D10) |
| No lock holds a channel's log still | kept, saying which side of the boundary each case falls, a queued message among them (M2, M6) |
| The message path trusts a machine name | narrowed to a project's log: a channel's is held to what the machine appended (M3) |
| A roster can list a thread's obsolete row for a moment | kept or promoted on M7's figures (the holder's call); it now says that addressing through the roster reads the same row |
| A remote-only add after the last holder left… | kept unchanged: this child places nothing through the roster |
| The uplink's thread can block in `finish_thread` | kept for a request's upload and the request pass's own finish: nothing a channel's message causes on the consumer thread reads a view or waits on a lock (M6), and a message's upload reads its sender's frame from the plane's rows alone |
| The idle gate's margin was spent without a note | answered by M1's figure and the holder's word on it (open point 8) |
| A peer message's reply line still models a double-quoted body… | answered by M10: taught, and measured; a channel's frame's line changed or not as E4 decides; a project's frame's line the owner's |
| An addressed event that names a session its thread has left is not pushed; A held event does not follow a continuation | kept for a project's log, saying that in a channel the debt is the thread's (§3) and what a project would need to take the same shape |

New rows, this child's own: a message that names a thread absorbed moments
later reaches no one (written in M2); a home whose path holds a bracket,
read as a pattern by the membership scan (written in M3); in a project, a
stopped session's receipt left by an earlier process is never asked about
where the endpoint decides reach (written in M6); a receipt handed to a
session, across a hand-off; a kept word's sixty seconds and one launch,
and what only the endpoint knows inside them; a channel's ask the endpoint
never answers, never given up; a queued person's message past a boundary
taken while it waited; a seat made again over a purged seat's session is
that thread.
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
        # "in": the one row of roster(channel) the name reaches, with its own project. "out": a thread that
        # was once in the channel and is not now, with its row in its own project; its caller says what that
        # means. Every other miss exits 4, in §2's words.
        #   with `short`: a row whose alias is `name` and whose session id begins with `short`
        #   a name in id form (a full id, or eight hex digits): the id rule below
        #   else an alias: the rows whose current alias it is, and only when there is none those that held it
        #   before (current_first); several are refused, each as alias#short (candidate_labels)
    def thread_of_row(project, member) -> (thread id, session) | None
        # whom a roster's row is addressed as, both from one read of that one row: the thread its `joined`
        # is stamped with, or, where an older copy left it unstamped, the `thread` of the statement in
        # effect for it; and the session the row holds. Read from the `info` of the view the roster's own
        # sweep (_sweep) took the row from, which the sweep keeps beside its rows from M1 on, never from a
        # lookup made after the row was found. None where the stamp and the statement in effect are both
        # there and disagree: the row is not addressed, and the sender is told (§2)
    def claimants(session_id) -> {thread id} | None
        # the threads that have had a session, as this reader's logs say: the marks of the session's episodes
        # (_projection's `episodes`: its stretches under one thread) in every project's view known here, an
        # episode the log shows unlisted to this reader left out. An unstamped episode is counted with the
        # thread of the statement that took effect in it; where one has neither, None: the id names no one
        # thread. Not from displayed rows: View.ended leaves out seated rows, and a row's former_ids does
        # not hold its own session
    def once_in(channel) -> {thread id}
        # every thread that has ever been in the channel, as this reader's logs say: the `thread` of each
        # `channels` statement whose set holds it and that took effect (the fold's rule, C2: under the writer
        # of the session's `joined` in effect then, and after it), where that `joined`'s stamp is the same
        # thread or is absent. A statement that never took effect, and another writer's, count for nothing.
        # Kept beside each merged log

**A name in id form, through a channel.** Read as a thread id's prefix
first, and only then as a session's.

| The name is | Answer |
|---|---|
| the id, or the first eight or more of the id, of one thread that has a row in the channel's roster | `in`: that row, whatever session it holds |
| that of several roster rows' threads | refused as ambiguous, each as `alias#short` |
| that of one thread this reader can read which has no row in the roster and is in `once_in(channel)` | `out`, with its row in its own project now; where it has none (it has ended, or this reader may not read it), nothing is sent and the caller says so |
| that of a thread that was never in the channel | no old reply: `no member <name> in channel <channel>`, with where it is |
| no thread's, and a session's: `claimants` holds exactly one thread | as the first, third or fourth row for that thread |
| a session's that several threads have had, or whose history this reader cannot tell (`claimants` is None) | nothing is sent: refused, each of them that has a row in the roster named as `alias#short` |
| nothing this reader can read | `no member <name> in channel <channel>` |

An id form comes before an alias, as `match_members` orders them in a
project. `out` means: a verb's target is refused; a tag qualified by the
channel sends to that thread directly, in its own project; with `--in` it
is refused (§2).

Reason: a member's frame's reply line names its sender's thread (§3), so
a reply reaches its author's thread wherever its session went, goes to it
directly when it has left the channel (C5), and is never given to a thread
that came to hold the author's session id under another thread's id. A
session's id typed by hand has no such binding, so it reaches a thread
only when one thread alone has had it. A seat made again over a purged
seat's session has that seat's id and is that thread (§3): a reply by an
old frame's line reaching it is right.

`find_target` (M1) and the door (`speak`, M4) call `reach_in` for a
qualifier that `names_channel` answers; `_resolve_tag`'s branch for a bare
name calls `shared_rows`. Nothing else reads a roster to address.

### §2. The doors, the event and the sentences

    sminos say --in <channel> <text>            # any thread, or a person at a terminal; the tags are looked up in the channel
    sminos say "@<channel>/<name> …"            # the same, the channel named by the tag
    sminos chat <channel> [-n N] [--since TS] [--kind K] [--json]
    sminos list <channel> [words..]             # as list --channel <channel>, the words its row filters

In `S/sminos_channels.py`:

    def speak(channel, a, session, tags) -> None
        # the door (M4; its arguments are M4's to shape, what it decides and in what order is the contract):
        # before anything is appended, that the machine's enrollment carries the channel's log (CH1's
        # refusal for a verb that writes, which spares a channel that left this machine); who writes and
        # how (below); the recipients, each with its thread; that every tag is in this channel. Then it
        # appends and delivers as cmd_say does for a project. `session` "" for a person at a terminal.

**Who writes, and how.** Any session, and a person at a terminal, on a
machine where the channel is registered (`find_channel`; a name no log
answers to is the unknown name it is today) and whose enrollment carries
its log. The door reads once whether the sender is a member, from its own
machine's record (`channels_of(<the session>)` holds the channel), and
that decides the event's shape and nothing else:

| The sender | The event | Besides |
|---|---|---|
| a member | no `from_project`; no copy | nothing |
| a session that is no member | `from_project`: the sender's own project (`caller_project`), as `cmd_say` sets it for another project's log | its copy, where `record_copy` leaves one (below), and one line to the sender |
| a person at a terminal, a machine's notice | no `from_project`; no copy (the operator writes none today) | nothing; the pool is not consulted (open point 2) |

A tag is looked up in the channel's roster whoever sends (`reach_in`),
`@all` is the roster's live rows, and an untagged post names no one.
Delivery, the wire, the lead and the readers never read a sender's
membership: they tell the two shapes apart by the event's `from_project`.

**The event** is the one `cmd_say` writes today, in the channel's log,
with a thread's id where a channel's delivery needs one:

| Kind, writer | Fields |
|---|---|
| `say`; the session's writer in the channel's log, or its audience stream as `streams_for` splits it | `from`: the sender's alias; `thread`: the sender's own thread id (`sminos_threads.stamp`); `to`: `[{"session", "alias", "thread"}, …]` or `"*"` for an untagged post; `text`; `wake: true` for an `@all`; `from_project`: the sender's project's id, for a sender that is no member and for no other |
| `human`; the machine's human writer, or its stream | `from: "human"`; `to` as above; `text`; `wake`; `notice`: the program, for a notice. No `thread` of its own |

An entry of `to` carries the recipient's thread id and the session its
row holds, both from one read of the row (`thread_of_row`); a row it
answers None for is given no entry. The session is the
endpoint's: it is what the event's audience, and so its stream, is taken
from, and what the hub reads as the session addressed. The thread is
delivery's: what a channel owes is read from it alone (§3). Both are
signed as any field is, and neither changes an audience (MAWS's architect,
2026-11-22). A reader takes a `thread` of the wrong type as absent, and an
entry with none as naming no one. Never `copy` in a channel's log.

**The copy** of a non-member's message is `record_copy`'s, as it is: one
in the sender's own project's log for each audience its recipients split
into, naming the channel's event and owed to no one; none where that
project's log is not filtered by audience and the message went under a
private recipient's stream, with `record_copy`'s own warning (`delivered;
its copy is not kept in <project>: …`); a warning, after the delivery,
where it could not be written.

**The sentences that are decisions** (`%s` as given; each refusal leaves
every log as it was):

| Where | Exit | Words |
|---|---|---|
| a session that is no member says into the channel (after its `recorded …` line) | 0 | `you are not in %s: replies to this come to you directly, in %s. sminos channel add %s places you in it` |
| a name in the channel's roster that no member answers (`--in` or a qualified tag), the id of a thread that was never in the channel among them | 4 | `no member %s in channel %s`, then, when the name answers elsewhere, `; elsewhere: <each as the name that reaches it>` and, with `--in`, `Drop --in to reach it in its own project` |
| a tag qualified by the channel names by id a thread that was in it and is not now (the reply line of an old frame) | 0 | before its `recorded …` line: `%s is not in %s now: sent to it directly, in %s` |
| the same, where that thread has no row now (it ended, or cannot be read from here) | 4 | `%s was in %s and cannot be reached now (it has ended, or this machine may not read it): nothing was recorded` |
| the same tag with `--in <channel>` | 4 | `%s is not in %s now (it left the channel, or its thread ended): nothing was recorded. Drop --in to reach it in its own project` |
| a verb's target named through a channel that is not in it now (`find_target`, M1) | 4 | `'%s' names a thread through %s, which it is not in now: name it by its own name (<alias>#<short> or <short>)` |
| a session's id that several threads have had | 4 | `ambiguous %s in %s: the session it names has been more than one thread's: <each as alias#short> — name the one you mean` |
| `--in <channel>` with a tag qualified by another log, or tags that name a channel and another log | 4 | `one message, one log: the tags name %s` (among projects alone the sentence stays today's, `one message, one project: …`) |
| a selector that names a channel (`say --project <channel>`) | 1 | `%s is a channel, and a selector names projects: sminos say --in %s "@all …" reaches its live members` |
| `chat --host <channel>` | 1 | `%s is a channel, and what a session sends its human is in its own project's log: sminos chat --host <project>` |
| a say into a channel the machine's enrollment does not carry | 1 | CH1's sentence (`_refuse_uncarried`), unchanged |
| a recipient of this machine whose record does not hold the channel though a roster's row does | — | its line reads `<alias>: recorded (it is not in <channel> on its machine now: not delivered)` |
| a roster's row whose stamp and statement name two threads (`thread_of_row` is None) | — | its line reads `<alias>: not addressed (its membership of <channel> names two threads: nothing was recorded for it)` |

**CH1's refusals, and what takes the place of each:**

| CH1 refuses | Where | From this child on |
|---|---|---|
| `say --in <channel>` | `cmd_say`, by `channel_say_refusal` | `speak` (M4) |
| a tag `@<channel>/<name>` | `resolve_tags`, before any member is looked up, and `_resolve_tag` | `speak`, which gives the name to `reach_in` (M4) |
| a say whose destination is a channel however reached (an older copy's rooted registration, whose directory a caller stands in) | `cmd_say`, after `resolve_tags` | refused still, naming `--in`: a channel is spoken in only by naming it, never by standing in a directory (`%s is a channel, and no directory's project: say --in %s to speak in it`, exit 1) |
| the unquoted `@<name#short>/<alias>` | `cmd_say`, by `shortened_channel_qualifier` | refused still: `%s opens no tag (a tag's qualifier takes no #): nothing was recorded. Say it as sminos say --in %s "@<alias> …", or qualify the tag with the channel's id` (exit 1) |
| a selector that names a channel | `cmd_say`, the same loop as `--in` | refused still, in the sentence above |
| a verb's target `<channel>/<alias>` | `find_target` | `reach_in` (M1) |
| a channel where a project is asked for (`chat`, `list <name>`, `--project`) | `find_project`, `project_tiers` | refused still by both; `cmd_chat` and `list_scope` branch to the channel before they ask for a project (M4) |
| `join <channel>`, a `.smns` naming a channel | `channel_join_refusal`, `_smns_decision` | unchanged |

Three of CH1's sentences go: `channel_say_refusal`, `find_target`'s
"names a thread through a channel…", and the help's "nothing is said in
one in this version". A recipient's line is otherwise what
`deliver_say` prints today (`sent`, `sent (woken)`, T2's held lines,
`recorded (on <machine>)`, the endpoint's `recorded; the endpoint decides
its delivery`), and `say --exit-held` reads it as today.

### §3. What a channel owes a thread

In `S/sminos_channels.py`:

    class Debt(NamedTuple):       # what the selection needs, read from the thread's record alone
        channel: Project
        thread: str           # the thread the debt is owed to: the key of its delivery record and of its lock
        session: str          # the session its record names as current when this was read
        boundary: dict        # began_of(thread, channel) as read then

    class Owing(NamedTuple):      # a Debt's four fields, and what a push needs beside them
        channel: Project
        thread: str
        session: str          # where a push or a wake goes
        boundary: dict
        project: Project      # the thread's own project: where its membership is read
        member: Member        # its row there: what the delivery operation takes as `member`
        reach: tuple | None   # reach_token(session) as read then: None for a session with no record

    def debt(channel, record) -> Debt | None
        # From the record given and nothing else: no view, no reconciliation, no lock, no write. None when
        # the record has ended, holds no session, or does not hold the channel. An open entry hides no debt.
    def owing(channel, record, row) -> Owing | None
        # debt(), then what a push needs. Reads only, and looks no row up: `row` is the thread's own project
        # and its Member there, given by the caller (own_row for a deliverer; the plane's for the uplink; a
        # roster's for a sender), and None for it is None. None where debt() is None, and also while the
        # record holds an open journal entry (its `pending`, whatever the operation), and while its
        # session's record defers by the rule below (there and unreadable; lane B).
    def own_row(record) -> (Project, Member) | None
        # the thread's row in its own project, read from that project's view. For a deliverer in a process
        # of its own (the daemon's pass, a sender's call): never called on the uplink's consumer thread.
    def delivered(channel, thread) -> dict | None
        # the thread's delivery record under the channel, read strictly: {} when no file is there; None when
        # one is there and cannot be read or is no whole record. sminos.delivered_load, which answers {} to
        # both, is left for projects.
    def owed(d, events, record=None) -> [event] | None
        # THE selection, and the only one, of a Debt or an Owing: the events of the channel's log, in the
        # log's order, each once, an entry of whose `to` names d.thread (its `thread`), that lie past
        # d.boundary for their writer, and are neither settled nor revoked in the thread's delivery record
        # (`record`, or delivered() read here). An event the thread itself wrote (its own `thread`) is none.
        # None when the delivery record cannot be read: nothing is claimed.
    def first_owed(d, writer, events) -> event | None       # owed's first of that writer
    def still_owed(o, e=None, reach=False) -> bool
        # the last check, on files as they are (a deliverer makes it holding the thread's delivery lock),
        # by the reads of CH1's last guard (sminos_threads' check under set_channels' lock):
        #   o.thread's own file reads, has not ended, holds no open entry, holds the channel, and names
        #     o.session as current;
        #   the session's current record read afresh (current_record(o.session, fresh=True)) is that
        #     thread's, and holds no open entry;
        #   the session's record does not defer, by the rule below;
        #   the session's own events in o.project (sminos.own_events_now) leave it a member there, and
        #     o.project is where it is now (sminos._current_here: literal paths, a tie for neither);
        #   with `reach`, the session's reach_token is still o.reach;
        #   and, given `e`, it is past the boundary as it is now.
        # False settles nothing.
    def normalize(o) -> None
        # under the thread's delivery lock, after still_owed: a writer's `pending` in the delivery record
        # whose seq is at or below the boundary read afresh for that writer (began_of) is cleared, with the
        # attempt count and the pushed note that ride with it, in one write. Nothing else is evidence: a
        # `pending` whose event the selection merely does not hold (a writer file that could not be read)
        # stays. The settled prefix, the revoked seqs and the held marks are as they were.
    def deliver(channel) -> (int, [alias])
        # the channel's delivery pass (the daemon's channel pass, last): for each thread of this machine
        # that holds the channel (sminos_threads.set_holders) and that the log names, owing() with
        # own_row(), and sminos.deliver_next(channel, o.member, owing=o) when owed(o, …) is not empty
    def owed_here(channel) -> [(Debt, [event] | None)]
        # what `daemon owed` counts for a channel, from debt(), delivered() and the log alone: no Member, no
        # view, no lock, no write. None for a thread whose delivery record cannot be read.

Nothing is added to a thread's record, and `S/sminos_threads.py` is not
changed: no key, nothing in `_merge_absorbed`, `JOURNALED` or `SEAT_KEYS`.

**A session's record, read one way,** at `owing` and at `still_owed`
alike, as CH1's last guard reads it. A record that is not there (its path
gone: `FileNotFoundError` and nothing else) is the default every reader
already takes for it, lane A, and does not defer; its reach token is what
`reach_token` answers for it, None, which is equal to itself and to no
record's token, so a record written since counts as a change of reach. A
record that is there and cannot be read defers (`owing` None, the last
check False): it is not known to be lane A, and it gives no token. Lane B
defers.

In `S/sminos.py`, an argument each, whose absence is today's behaviour,
and one function (`holder_due`):

    def deliver_next(project, member, due=False, owing=None)
    def deliver_verdict(project, member, event, verdict, owing=None, word=None)
    def deliver_reach(project, member, event, verdict, reason=None, owing=None, word=None)
    def words_due(project, members, owing=None)      # owing: {session: Owing}, for a channel's choice
    def reach_due(project, members, owing=None)
    def holder_push(project, member, session, e, events, cursor, words=None, retry=False, due=False, owing=None)
    def holder_due(session, plan, peer) -> bool
        # whether an event whose held receipt `plan` describes (plan(existing_only=True, prepare=False)) is
        # next pushed: it says push or legacy, or it says awaiting while no process runs and the session is
        # the current one of a lane A thread (handed to a process that is gone, never admitted: the push
        # goes to the process a wake starts). Reads only. holder_owed's HOLDER_RETRY is this, for every log;
        # reach_due chooses by it where it is given `owing`, and by its own test (push or legacy) otherwise.

and in `S/sminos_holder_deliveries.py`:

    def key_hash(project_id, session, writer, seq, thread=None)
        # thread: for a channel's event, part of what a receipt is found by. Absent, the hash is today's.
    def exists(project_id, session, e, thread=None)       # likewise admitted, words_of, handed, settled
    def plan(project_id, session, e, event_hash, peer_pid, words=None, existing_only=False, prepare=True,
             thread=None, lock_until=None)
        # thread: as key_hash's, and kept in the receipt's key beside its session. lock_until: the
        # receipts' lock is tried until then (sminos.LockBusy); absent, it is waited for as today.

With `owing` (the log is a channel's), and only then, the operation is the
same and reads three things where it reads one for a project:

- **The thread, for the debt.** The one lock taken is the thread's
  (`delivered/<thread id>.lock`), once, by the entry point
  (`deliver_next`, `deliver_verdict`, `deliver_reach`); no caller holds it
  already. What is owed is `owed(o, events)`, and `_first_owed`'s answer is
  `first_owed`'s; the two passes' own skips (a member whose current
  session no entry names; the share kept by session and record) are not
  used. Every read of the delivery record is `delivered(o.channel,
  o.thread)`, and every write of it and of its marks (`delivered_settle`,
  `delivered_fail`, `delivered_pushed`, `delivered_held`,
  `delivered_revoke`) is under the thread's id; given a channel's log
  those writers load the record through `delivered` too, and over one
  that cannot be read they write nothing and their caller defers. A mark
  there is that
  thread's: `stale_hold` and `held_unreadable` are not asked,
  `wake_member`'s comparison of a mark with the thread it wakes reads this
  record, and a mark is read only for an event the selection chose (one
  left below the settled prefix is dropped by the record's own writer,
  `_entry`). `deliver_say`'s reads of a held mark and of a settlement made
  by another deliverer meanwhile are of this record too, so a sender that
  races the daemon is told what happened (`pending`, `--exit-held`).
- **The session, for the process.** Every read of a hold, a peer, a
  reach and a permit, and every push and wake, is of `o.session`. A
  receipt is found by that session and `o.thread` together, in every
  lookup (`exists`, `plan`, `words_of`, `handed`, `admitted`, `settled`),
  so two threads an event names never share one, whatever session served
  them. `sweep` drops a channel's receipt on the record of the thread its
  key names (`delivered`), never on
  `delivered_load(<channel>, <session>)`, and keeps one whose record
  cannot be read. The admitting side is unchanged: it finds a receipt by
  the id its marker carries and checks the session.
- **The thread's own project, for membership.** `held_owed`, `push_event`,
  `holder_push` and `wake_member` read whether the session is still a
  member, and `canonical_end` its end, from `o.project`, never from the
  channel's log.
- **Under the lock, in this order:** `still_owed(o)`; the strict read of
  the delivery record, where None stops the pass; `normalize(o)`;
  then the choice. `holder_push` makes the last check again for its event
  before anything is handed over, and `wake_member` again once the wake's
  hold is taken and before a process is started. After a wake's launch
  returns and before its text is handed over it is made once more, with
  `reach=True`, and the two refusals the operation makes on its own
  evidence are read again with it: the event's signer's revocation, and,
  for an event from outside this machine, the machine's read-only policy.
  Where the last check fails the pass stops for that thread: nothing
  pushed, nothing woken (or nothing handed over, after a launch), nothing
  settled, no attempt counted; and `push_event` finding the session
  retired in `o.project` (a `moved` among the reasons) is that same stop,
  never `recorded`. Where one of the two refusals is found after a launch,
  nothing is handed over and the event is refused as that check refuses
  it before a push. After a launch that leaves the debt owed, it is owed
  to a session that now runs: the next pass pushes it, or asks the
  endpoint about it again, and nothing is launched twice.
- **A kept word** (§4), given as `word` to `deliver_verdict` or
  `deliver_reach`: under the lock, after the last check (made there with
  `reach=True`), the word's file is read again and removed, and the
  operation goes on only if it was still there, is younger than
  `WORD_KEPT`, names `o.thread`, `o.session` and `o.reach`, and
  `first_owed` of its writer is the event of its seq and hash. Otherwise
  nothing is done on it.
- An event is from outside this machine when it is not
  `appended_here(channel, e)`, and the same-owner shortcut
  (`ReachGate.needs`) holds only for one that is.
- The frame of an event that carries `from_project` says its sender is
  outside the channel: `frame_of` puts ` (not in <the channel's name>)`
  first after the sender's alias, before `sender_labels`' clause, where a
  reader of a frame already expects a label (an alias is read to its first
  `,` or ` (`). Its reply line names `from_project` and the sender's
  session, as `sminos_control._routes` makes it today. The frame of an
  event that carries none has `reply_line(<the event's `thread`>,
  <the channel's id>)`: `@<channel id>/<the first eight of the sender's
  thread id>`. A `human` event has no reply line, as today.
- The chat cursor a frame's unread count reads is the thread's (§6).
- No outcome is kept for the uplink (`sminos_outcomes.record` keeps none
  for a channel).

The three that push (`deliver_next`, `deliver_verdict`, `deliver_reach`)
refuse a channel's log given without `owing` (an assertion). The two
passes are reached for a channel only through `asks_due` (§4), and gain no
check a project would pay for. `_write_receipts` receipts a `say` appended
to a channel's log, beside the kinds of `RECEIPTED_KINDS`.

**What is settled without a push.** Only what the operation settles today
on its own evidence: a revoked signer's event, an outside event on a
read-only machine, the endpoint's `refuse`, an event for the live alone
whose thread is stopped, and a failure given up after `DELIVERY_ATTEMPTS`.
A membership never settles anything: an event at or below the boundary is
not selected, a thread that is not in the channel has no pass, and the
delivery record keeps whatever it held. So nothing is written when a
thread enters, leaves, ends, returns or changes session. The one write a
transition leaves for later is `normalize`'s, made by the next pass under
the lock it already holds: without it a failed attempt on an event the
boundary has since passed would stop its writer for good (`_next_check`
lets nothing be settled or failed for a writer but the event its
`pending` names).

**A thread's id is the thread.** A thread a human opened has an id minted
for it. A seat's id is its first session's (the parent's X2), so a seat
made again over a session whose earlier seat was purged has that seat's
id, and is that thread again: the same delivery record in a channel, owed
what names the id past the boundary its new membership gets (row D15),
and a reply by an old frame's line reaches it. What the debt is never
keyed by is a session that some thread merely holds or held.

**The transitions.** What the record's own operation writes is CH1's and
T1's, and this child adds nothing to it; the last column is this child's,
and each row is a test of M2 (what `owed` returns) staged through the
transition itself, and of M3 where a push shows it.

| # | What happens to the thread T in channel C | The record (CH1, T1) | What C owes T, and what delivery does |
|---|---|---|---|
| D1 | T enters C (its own add, a request honoured) | `began[C]`: the log's positions now | only what names T past them: what this machine held then is never selected |
| D2 | a message naming T arrives while it is a member | none | live: pushed and settled in T's record; stopped and woken: T2's wake, then pushed; stopped and not woken: held, owed, marked; for the live alone: `recorded` for a stopped T |
| D3 | T is reopened, or woken, while still a member | none | what was held is pushed once and settled |
| D4 | T is removed from C | `began[C]` dropped | no debt: nothing delivered, asked or settled; T's record under C stays as it is |
| D5 | T is removed and added again | a new `began[C]` | what the machine held at the second add, D4's held mail included, lies at or below the boundary and is never selected; what it imports afterwards is owed, whenever it was written. A `pending` the record kept for an event now below the boundary is cleared by the next pass (`normalize`) |
| D6 | T's session is handed off, s to s′ | `current`, `sessions`; `began` untouched | nothing is carried and nothing merged: the same record, the same lock. The next pass pushes to s′ what is owed, whatever session an entry names; a pass that held s stops at its last check; while the hand-off's entry is open, nothing is delivered |
| D7 | T absorbs a provisional thread P | `_merge_absorbed`, as CH1 wrote it: the set; `began` (T's own kept where both were in C, P's taken where only P was); `answered` | T is owed what names T, past its boundary for C as the merge left it. What names P is owed to no one from then: P's record under C stays on disk and nothing reads it, and what was pushed to P while it existed stays pushed (accepted; TECH-DEBT). While the absorption's entry is open, nothing is delivered to T |
| D8 | T is refilled on lane A (a new occupant) | `current`; `began` untouched | the same thread: what names it and is not settled is owed to the new occupant. A lane B repoint drops the seat's keys, memberships included (CH1): row D4 |
| D9 | T ends | T1's; the keys untouched | no debt while it is ended: nothing delivered, nothing settled, nothing written |
| D10 | T returns | `began` anew for every channel; kept from before the end over a channel whose log cannot be read, and by a return an older copy makes | anew: what was held before the end and what arrived while ended lie at or below the boundary (a `pending` kept for one of them is cleared as in D5); kept: both lie past it and unsettled, and both are pushed once (the holder's ruling) |
| D11 | a session T had runs again as a thread with another id, T′ | a new record, in no channel | nothing: no debt is by session. T′ is owed what names T′, from its own boundary, once it enters |
| D12 | T's session turns lane B, its session's record is there and cannot be read, or T's record holds an open entry | — | `owing` is None: nothing is done this pass and nothing settled. `daemon owed` still lists what `debt` gives. A session with no record at all is lane A and is delivered to. A thread whose own file cannot be read is not among `set_holders`: no pass, and no debt attributed |
| D13 | a message naming T reaches the machine late, when a thread with another id, T′, holds the session its entry names and is in C | none | owed to T, if T is in C and the event is past T's boundary; never to T′ |
| D14 | a person's message waited in this machine's queue across T's removal and add | none | it has no position until it is released, and is then past the new boundary: owed (Constraints, accepted) |
| D15 | a seat over the session S, in C, is purged; a seat is made again over S and added to C | the first seat's record is gone; the second's id is S, the first's; `began[C]`: the positions at its add | the same thread, and the delivery record under C that the first left: owed what names the id past the new boundary and is not settled there. A message the machine held before the add is not owed; one it imports after it is, whenever it was written |

The linearization point of every row's delivery is the thread's delivery
lock under C: the last check, the record made consistent, the choice, the
push and the settlement are made under it, by whichever pass holds it,
and a pass for a session the thread no longer holds does nothing there. A
removal is under another lock (the wake lock, then the record's); a
wake's hold is that same wake lock, kept through its launch and its push,
so for a woken thread no removal lands between the last check and the
frame's handoff: one attempted then is busy, and lands after.
For a live push that window is the base's and is accepted (Constraints).

A project's log is untouched by all of it: `hand_off` still settles what
the project owed the session it leaves (`settle=old`), and an event there
that names a session its thread has left is still not pushed (the owner's
ruling). For a project to take a channel's shape its messages would have
to name threads, which every installed copy writes and reads by session:
that is a change of the project's event, not of this child (open point 9).

### §4. The wire

Nothing is added to RL10: no frame type, no field of a frame, no
capability. What this child sends under a channel's id that CH1 did not,
each in today's shape:

| Frame | When | What it carries |
|---|---|---|
| `events` (up) | the upload of a channel's log, as CH1's, from a machine that holds a member (no `follow`) and from one that holds none (`follow`) alike | a `say` (with `from_project` when its sender is no member), a `human` (with `notice` for a notice), a `channel-lead`, signed under the channel's id; preceded, under its own project, by the member frame of each sender that is a member of a project now |
| `reach? {id, project, session, event}` | the uplink's pass, for a message a push would hand over as a peer's frame | `project`: the channel's id; `session`: the recipient thread's current session, whatever session the event's entry names; `event`: the message as stored, `verified` left out |
| `words? {id, project, session, event}` | the same pass, for a `human` event the endpoint's word decides (`words_route` `ask`) | the same |

and receives the answers `reach {verdict: deliver | refuse, reason}` and
`words {verdict: words | peer | refuse}`. A wake is not on the wire: the
recipient's own machine starts its stopped thread, on its own endpoint's
word about the message, as it does for a project's. Not sent under a
channel's id, now as before: `member`, any `session` message (presence,
`machine`, `host`, `raised`, `settled`, and `delivery`), `pending`.

**Who does what.** The uplink asks and keeps; a deliverer in another
process carries out.

In `S/sminos_channels.py`:

    WORD_KEPT = 60        # seconds within which a kept word may begin to be carried out
    def asks_due(channel, rows, kept=()) -> [(Owing, event, "words?" | "reach?")]
        # the uplink's choice, reads only and no lock waited for. `rows`: {session: (Project, Member)} as
        # the plane holds them. For each thread of this machine in the channel (set_holders): one whose
        # session `rows` does not hold is passed by, before owing() is asked; else owing() with that row;
        # unless this machine holds its session (hold_for), the first owed event of each writer
        # (first_owed), less one whose key is in `kept` and less what words_due and reach_due leave out for
        # a project (an outside event on a read-only machine, one noted pushed, a recipient whose record
        # cannot be read); "words?" where words_route says ask, else "reach?" where ReachGate.needs. Built
        # on words_due and reach_due given the Owings, not beside them. An event a receipt is held for
        # (holder exists, which takes no lock) is planned with the receipts' lock only tried
        # (plan(…, lock_until=now)): left out of this pass when the lock is busy, and asked about when
        # holder_due says it is next pushed (§3).
    def keep_word(channel_id, thread, ask, word) -> None
        # the uplink's one write: projects/<channel id>/words/<thread>.<ask>.json, created whole and never
        # rewritten, its path built from the two ids alone (no registration read, no lock):
        # {"kind": "reach" | "words", "verdict", "reason", "thread", "session", "reach": <reach_token>,
        #  "writer", "seq", "hash", "at"}
    def carry_words(channel) -> int
        # the daemon's channel pass, before deliver. It takes no delivery lock. For each thread with kept
        # words, oldest first: one older than WORD_KEPT, or whose thread has no owing() now (with
        # own_row()), is removed where it lies; each other is handed to sminos.deliver_reach or deliver_verdict with the Owing and
        # the word (owing=o, word=<its path and what was read>), which takes the thread's lock once and
        # there reads the word again, checks it and removes it (§3). How many were carried out.
    def unsent(channel) -> bool
        # whether this machine's writers hold in the channel's log an event the upstream has not taken, or
        # a queued append: what `daemon owed` lists for it as `upload` and `queued`

In `S/sminos_uplink.py`:

    def Link.ask_messages(self) -> None
        # behind ask_words' project loop and beside ask_requests, only while a channel a thread of this
        # machine is in is open and the welcome listed `channels`: asks_due for each, and one ask queued
        # for each event due
    Link.words_kept: {key: deadline}     # the keys a kept word is still good for; forgotten at the deadline

- An ask is held under `(channel id, thread, writer)`, marked a channel's,
  with the thread, the session and the reach it was put for and the
  event's key (`sminos_channels.event_key`'s shape); it holds no member.
- `expire_asks`, for an ask marked a channel's that passed its deadline,
  of either kind: the ask is dropped and one line goes to the daemon's
  log, once for the event. It reads no `member`, calls no
  `words_unanswered`, takes no lock and writes no record; the next pass
  that finds the event still owed asks again, at the ordinary interval.
  While it goes unanswered it holds back the later events of its writer
  to that thread (`first_owed`), and nothing of any other writer or
  thread.
- Before an ask goes, `Link.member_on_lane(<the thread's own project>,
  <its session>)` holds for the recipient, and for the sender too when it
  is a session of this machine that is a member of a project now; else the
  ask waits for the plane's next read.
- `queue_asks`, the last step before a frame goes, makes `still_owed` for
  a channel's ask beside the hold it rechecks today, and drops one that
  fails.
- `on_words` and `on_reach`, for an ask marked a channel's: a verdict is
  kept (`keep_word`), the key noted in `words_kept`, the daemon nudged
  (`nudge_daemon`), and nothing else. A `peer` word on a person's message,
  where the endpoint decides reach, queues the `reach?` about the same
  event instead. A reply that names no verdict consumes nothing.
- `Link.upload` tells `senders_before` whether the frame it is about to
  send carries a message (a `say` or a `human`). For one that does, each
  sender that is a member of a project now is looked for in the plane's
  rows as they are (`member_on_lane`), and while the plane holds none for
  a sender the frame is undrawn and waits for the plane's next ordinary
  read: no view is read and no reconciliation run for it. A sender that
  is a member of no project now (it retired since it wrote) owes no frame
  and is waited for by nothing, as in CH1. A frame of CH1's kinds alone
  keeps today's path (`member_under`).
- `Link.may_leave` reads `unsent` beside `outstanding`: a followed channel
  does not leave, and one that left comes back, while either holds.

**What the endpoint's word is good for.** To begin being carried out
within `WORD_KEPT` of its answer, and across one launch, as a project's
verdict is good across its launch today. Before a push and after a wake's
launch this machine reads again what it can read: the thread's current
session, its membership and boundary, its lane, its session's reach token
(`reach_token`: this machine's own record of that session's access, and
nothing of the endpoint's), and the signer's revocation. A change leaves
the message owed and asked about again. What only the endpoint knows (who
is in the org, a machine's owners, the sender's owners) is not seen
inside that window: the base's property, accepted (Constraints).

**Why a channel's outcomes stay on the machine.** For a project, the
outcome of an outside event's delivery is kept (`sminos_outcomes.record`)
and uploaded as a `session` message of kind `delivery` under the log's
id. Under a channel's id that is a publication C1 forbids, and MAWS wants
none (its architect, 2026-11-22). So none is kept for a channel. What a
sender on another machine reads is what it reads today for any thread
there: `recorded (on <machine>)`, or that machine's published hold.

**What MAWS's endpoint and hub do with these,** as MAWS's architect
confirmed on 2026-11-22, with no change to MAWS:

- An upload: the endpoint finds the writer's member by session alone,
  attests the event from that frame, takes its audience by session, and
  signs it over the org and the channel's id. Nothing at the endpoint, at
  the hub or in a view assumes that the writer of an event under a
  channel's id is a member of that channel. Extra keys in an entry of
  `to`, and a `thread` on the event, are carried and signed as any field.
- `reach?`: the recipient by the frame's `session` alone; nothing is
  checked against the event's `to`, whose `session`s are addressing
  references. The sender is verified under the frame's `project`.
- `words?`: the recipient by session; `project` is only the scope of the
  endpoint's own record of answers, the verification and the index. `peer`
  at once for a session it holds no member of. `words` for this machine's
  own human writer only when the recipient's owners meet the machine's;
  `words` for a phone's `hub/<member>` when that member holds `converse`
  on the recipient; `peer` for another machine's `<machine>/human`, for
  anything older than a day, and for a notice. The fixture's cases 18 and
  19 state these under a channel's id (M7). For an event from elsewhere the content must be
  in this machine's inbound index under the channel, which holds while the
  machine has the channel open.
- `known` lists a channel only for a machine that holds a member; relaying
  is not gated by that: what is written under the channel, and its
  acknowledgements, reach a machine for as long as it keeps the channel
  open.
- A log a machine opens joins the endpoint's rebuild of its policy cache,
  and an upload that names a recipient the cache does not know is held
  until that log's `snapshots?` is answered `done` (sminos answers a
  channel's with one empty page, done: CH1, `Link.on_snapshots`).
- MAWS's views draw no channel's log and read no `from_project`.
  `channel-lead` is relayed as a kind MAWS does not know, and its name is
  free.

### §5. The lead

| Kind | Log, writer | Fields |
|---|---|---|
| `channel-lead` | the channel's log; the machine's human writer, plain or under its audience stream as the thread it names requires | `thread`: the lead's thread id, with `session`: that thread's current session; or `thread: null` and no `session`, for none. Never `to` |

The event takes the audience of the thread it names, as a request does
(`stream_choice` for that one recipient): `session` is where the endpoint
and the hub read whom it refers to. A thread's id is not always opaque (a
seat made over a session has that session's id), so a lead written
plainly could show a private session's id to every reader of the channel.
Before an event that goes under a stream, the verb writes a plain
`{"thread": null}`: a machine that cannot read the lead then reads that
there is none, and not an earlier lead it could read.

In `S/sminos_channels.py`:

    def is_lead(e) -> bool
        # kind channel-lead; its base writer `<machine>/human` with a machine's name by the notice's grammar
        # (sminos.NOTICE_MACHINE_RE, never hub or legacy); no `notice`; `thread` a non-empty string (with a
        # `session`) or None
    def lead_of(channel, rows=None) -> (Project, Member) | None
        # the last is_lead event of the merged log this machine holds decides, whoever wrote the ones before
        # it: None for a `thread` of None; else the roster's row whose thread it is; None when no row is (it
        # ended, left, or this reader may not read it). An earlier lead never comes back in its place.

    sminos channel lead <channel> <thread|none>

Refused inside a session; refused where the enrollment does not carry the
channel, as CH1's verbs that write, and without the capability; refused
for a thread that has no row in the roster; refused where the stream
choice refuses (the thread's audience is not known on this machine), in
the choice's own words; then `confirmed` at the terminal. Exit 0 once the
event is appended, 1 for a refusal, 4 for a name that is unknown or
ambiguous.

| Where | Exit | Words |
|---|---|---|
| inside a session | 1 | `channel lead is for a person at a terminal, and this runs inside a session: nothing was written. Report it to your human instead` |
| no terminal | 1 | `naming a channel's lead needs its owner at a terminal to confirm it, and this has none: nothing was written` |
| the prompt | — | `Make %s the lead of %s? A message you type into %s with no tag, on this machine, is then addressed to it. Confirm? [y/N] ` (for `none`: `Clear the lead of %s? Confirm? [y/N] `) |
| not confirmed | 1 | `not confirmed: nothing was written` |
| the target is not in the channel | 1 | `%s is not in %s: sminos channel add %s <thread> places it first` |
| done | 0 | `%s leads %s`; for a lead on another machine, then `(on <machine>: a message you type here reaches it as a peer's, not as its human's words)`; for a private one, then `(private: only machines that may read it see that it leads)`; `%s has no lead` |

**The post.** In `speak`, for a call with no session, no `--notice` and
no tag: when `lead_of(channel)` answers a row, the event's `to` is that
row's session, alias and thread, and it is delivered as any addressed
event is. Every other untagged post is untagged. `channel show` prints a
line `lead  <alias>#<short>` after its heading, and `--json` a key `lead`
(the thread id), each only while a lead is in effect for this reader.

### §6. What reads a channel's messages

Lifting "nothing is said in a channel" changes what each reader of a
channel's log meets there. Every reader, and what it does with a `say` or
a `human` in a channel's log from this child on:

| Reader | Does |
|---|---|
| `view_of`, `_reconcile_channel`, `Plane.refresh` | nothing: a message is no membership event; a channel's view still has no member |
| `sminos_daemon.tick` (a project's) | not run for a channel, as before |
| `sminos_daemon.channel_pass` | carries out kept words (M6), then delivers (`sminos_channels.deliver`, M3), after the view and `carry_due` |
| `HubLog.deliver` (an import) | nothing for a channel, as before; the import's nudge brings the channel pass |
| `Link.ask_words` | its project loop asks nothing for a channel, as before; `ask_messages` asks (M6) |
| `Link.on_words`, `Link.on_reach` | keep a channel's word in a file and carry out nothing (M6) |
| `Link.upload`, `senders_before` | uploads it under the channel's id, senders' frames first; for a frame that carries a message a sender's frame is looked for in the plane's rows alone, and the frame waits where there is none (M6); a frame of CH1's kinds alone keeps CH1's path |
| `Link.expire_asks` | drops a channel's ask that passed its deadline and writes nothing (M6) |
| `sminos_holder_deliveries` (`key_hash`, `exists`, `plan`, `words_of`, `handed`, `admitted`, `settled`, `sweep`) | a channel's receipt is found by its session and its thread together, and swept on that thread's record (M3); the admitting side as it is |
| `holder_owed`, `reach_due` | one classification of a held receipt's next step (`holder_due`), so a channel's ask goes where the push would retry (M6) |
| `Link.deliveries`, the outbox | nothing: no outcome is kept for a channel |
| `HubLog.show_notices` | tells the sending session of this machine when the hub withheld its message, as for a project (keyed by session; no change) |
| `Link.may_leave` | does not let a followed channel go, and brings one back, while this machine's messages there have not gone up (`unsent`, M6) |
| `outstanding` | unchanged: it reads requests alone |
| `sminos_channels.requests_of`, `pool`, `answers` | skip it (they read their own kinds) |
| `sminos_daemon.owed_in` (`daemon owed`) | counts what `owed_here` gives for a channel, by thread, reading no view and writing nothing; lists a delivery record it cannot read among what it could not inspect (M2) |
| `deliver_say` | the sender's own delivery (M4) |
| `record_copy` | keeps a non-member's copy in its own project's log where today's rule leaves one, as for a message to another project (no change); a member's say calls it not |
| `cmd_chat` | reads it through `sminos_channels.chat` (M4) |
| `frame_of`, `holder_wake` | name the channel by its name, as they name a project; `frame_of` adds §3's clause for an event that carries `from_project` (M3) |
| `frame_landed` | claims nothing where another log of that name holds an event of the same ref and text (M4) |
| `sminos_control._routes` | the reply line names the event's `from_project` and the sender's session where it carries one; else, in a channel's log, the channel and the sender's thread (M3) |
| `held_owed`, `push_event`, `holder_push`, `wake_member`, `canonical_end` | read a member's membership and end from the thread's own project, given `owing` (M3) |
| `append_host`, `export_live`, `close_questions` | never see a channel: a session's project is never one (no change; B7's tests) |
| `roster_text` (after a compaction or a resume) | reads the channels the thread's statements have named (M9) |
| the manager's `OwnerWords` | reads the channels known on the machine; never certifies by a display name alone (M9) |
| a copy on 1.54 | stores it, delivers nothing, refuses to say; its `channel show` and its roster are unmoved |
| a copy from before CH | takes the channel for a project with no member: delivers nothing, settles nothing, unless it was made to join a session into it by hand |

In `S/sminos_channels.py`:

    def chat(channel, a, session) -> None
        # cmd_chat's body over a channel's log: the channel's own view first (view_of, which reconciles a
        # channel as a channel) and never sminos.reconcile; the window and the lines as cmd_chat makes them,
        # a line whose event carries `from_project` with §3's clause after its sender; `--host` refused
        # (§2). Any reader that can read the log may: a channel bounds no one's reach.

**The cursor is the thread's.** In a channel's log the chat cursor (what
`chat` has shown, and what a frame's unread count is counted from) is kept
under the reader's thread id, as its delivery record is, so a hand-off
carries nothing there either. A session that is no thread, and a person
at a terminal, keep theirs as today.

**The exchanges after a compaction or a resume** (M9): `roster_text` gives
`_roster_exchanges`, beside its two projects, the logs of the channels the
thread's own statements have named (the newest ten by their latest
statement, of those registered here: `ROSTER_CHANNELS`). In a channel's
log a `say` counts as today's does (addressed, not for the live alone);
"mine" is a message whose `thread` is the reader's thread or an entry of
whose `to` names it; a peer is keyed by its thread; `_roster_peer` finds
that thread's row in its own project now instead of answering none for a
channel, and where it finds none the line gives the name the event gave
the peer and says no tag reaches it.

**The manager's window** (M9): `M/manager_window.py`'s `frames` returns
the log's name it already parses from a chat frame's header. `OwnerWords`
holds, under `(log name, ref)`, every candidate owner's event of every log
of that name it was given, each with its log's id and its body;
`corroborates` passes a frame only when exactly one candidate under its
key has the frame's body, and says which log it lies in. `M/manager.py`
builds it from the subscription's project's log and the logs of
`known_channels`.

### §7. What sessions are taught

The wording is M10's evaluation's to settle; what each text must come to
say, and stop saying, is fixed here.

| Text | Comes to say | Stops saying |
|---|---|---|
| the guide (`guide_text`) | that the session is a thread; the channels it is in, by name, when it is in any (a line that is absent for a thread in none); `say --in <channel>` and `@<channel>/<alias>`; that a bare `@alias` reaches its project and the channels it shares | that a bare `@alias` reaches only its project |
| `sminos/skills/sminos/SKILL.md` | thread and channel as the parent's Terms have them; `channel create`, `add`, `remove`, `show`; speaking in a channel and the reply line that keeps a reply there; that a thread may say into a channel it is not in, that its answers then come to it directly, and that only members hear the channel; that adding wakes no one; `chat <channel>`; that `join` declares a project and a channel is never joined | `send` as a way to message a member (it stays as the script's verb, `--wait`); the project as the only unit |
| `references/spawn-preamble.md` | the same two forms for a channel, in the paragraph that teaches tags | nothing |
| `sminos/skills/manager/SKILL.md`, `references/digest-brief.md` | that a subscription may be named `<channel>/<alias>`; that an exchange may be a channel's, and how the window marks it | "project log" where a channel's is meant too |

The lines the suites pin verbatim, each changed in M10 only if its line
changes: in `T/test-guide.sh`, the guide's opening pair, the `list
--subagents` line, the heredoc line, and its loop of fragments (among
them `@<short>`, `@<project>/<alias>`, `join <project>`, `wakes no one`);
in `T/run-sminos-tests.sh`, the preamble's lines (`You are "researcher", a
member of the project "work", spawned by`, `only the tags that open a
message`, `@<project>/<alias>`, the three `sminos say` examples, `Your
task follows.` and the rest of that block); in `T/test-remote.sh` and
`T/test_threads_stopped.py`, one fragment of the guide's first line each.

**The reply line.** `reply_line` keeps its one form, its absolute path and
its one line (`[To reply, run in Bash: <path> say "@<log id>/<short>
<your reply>"]`), which the suites and the manager's `REPLY_LINE_RE` read;
for a project's frame nothing of it changes in this child. If M10's
scenario E4 fails on the baseline, the line of a channel's frame, and of
no other, becomes, still one line and still closed by `]`:

    [To reply, run in Bash: <path> say "@<channel id>/<short> <your reply>" — a reply with a backtick, a quote or a $ goes on stdin instead: <path> say - <<'EOF', its first words @<channel id>/<short>]

and the manager's `REPLY_LINE_RE`, which reads a line to its closing `]`,
still reads it. A change to every frame's line is the owner's.

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
| a `say` or a `human` this code wrote under a channel's id whose `to` is a list with an entry that carries no `thread` | a breach (new) |
| a `channel-lead` that carries `to`, or a `session` with no `thread` | a breach (new) |
| `member`, `pending`, presence, `machine`, `host`, a `snapshots` answer with an event, a `retired` that undoes no older `joined`, `member.channels` out of shape, anything in a channel's host store | breaches as before |

Its own tests (`T/test_channels_wire.py`, class `Checker`) gain a case for
each new rule and each rule changed. M2 changes the disk rule for a
delivery record, M4 the kinds and the message's shape, M6 the wire rules,
M8 the lead's. A kept word (`words/` under a channel's home) is no event
and no breach.

**The stand-in** (`T/endpoint_standin.py`) proves the order and the shape
of what sminos sends, and answers `words?` and `reach?` from its
configuration (`verdict`, `verdicts`, `reach_verdict`, `reach_verdicts`).
It gains, for the two questions under any project id, what §4 says of the
endpoint: no answer to a `reach?`, and `peer` to a `words?`, for a session
it holds no member frame of; and `peer` for a notice where it would
answer `words`, unless a test configures it to answer `words` all the
same (the test of sminos's own guard, M8). It does not attest and holds
no policy cache: its relay signs every upload alike and gates none on a
`snapshots?`, so no test reads either from it; MAWS's fixture states them
(M7). A test that needs a word late, or never, takes the ask's id from
the frames the stand-in kept and sends the answer itself, or none, as
`T/test_channels_wire.py`'s `Asks` stages one after a hand-off.

**A receipt left by a process that is gone** is `T/test_wake_delivery.py`'s
`Awaiting` fixture (a receipt written by hand, pushed and never admitted),
which M3 keys by the thread too and M6 stages in a channel on a machine
whose endpoint decides reach.

**A lock held elsewhere** is the lock's file taken with `flock` outside
the code under test and kept until the test lets it go: by a child
process, or on a descriptor of the test's own, as
`T/test_channels_wire.py` holds a wake's lock for "a wake of the thread
in flight in another process" (an `flock` belongs to its open file, so
the code under test waits on it as on another process's). M6's two
carriers are two real processes of the CLI under a timeout, and no mock
of a handler.

**The engine** is T2's test engine (`T/wake_engine.py`): its `launches`,
`calls.log` and `inputs/<session>` are what shows a wake and the frame it
was woken with, and its `barrier` what stalls a launch; a live session's
inbox is `T/inbox_standin.py`. `T/test-channels-machines.sh` runs a no-op
engine stub today; this child's cases there take the test engine as
`T/test-notice-machines.sh` does. A typed yes is given on a real
controlling terminal, as `T/test_visibility.py` gives one.

**The bench.** `T/bench_scale.py` gains `--channels N` and `--held H`
(M7): N channels registered, H of them (all, by default) with members
drawn from the shape's threads across its projects, statements written as
the verbs write them; with either, its stand-in lists `channels` and
`reach`. `verbs` checks each command's exit code and gains the matched
pairs of M7; `run` reads the idle figures for the shape it was given and,
with channels held, runs the upload scenario. Without `--channels` the
bench is what the gate runs today, byte for byte. No gate reads the new
figures.

**Where each new file sits,** and the neighbour it is built like:
`test_channels_names.py` and `test_channels_say.py` load the CLI's modules
under a temporary home and drive the launcher, as `test_channels_roster.py`
does; `test_channels_debt.py` like `test_channels_life.py`, whose staging
of T1's transitions it takes; `test_channels_delivery.py` like
`T/test_wake_delivery.py` (`Deliveries` over the test engine) and
`T/test_wake_senders.py` for an interleaving; `test_channels_lead.py` like
`T/test_threads_owner.py` for the terminal. All run in the `channels` part
of `T/run-sminos-tests.sh` (`run_channels`) and in no other; the
older-copy suite, the guide's and the manager's stay in the parts that run
them today.

### Dependencies

- MAWS's master with its child MW, as CH1's plan lists it. Nothing in this
  child's suites runs MAWS: the stand-in and the conformance replay stand
  for it.
- MAWS's fixture at its master `5a88bcd83` (`conversation.json`, blob
  `5ffdd4a2`), with cases 16 to 19; M7 copies and replays it.
- **Open with MAWS's architect,** carried by the composite's holder:
  MAWS's own row on a `reach?` for an event imported with no local
  receipt (its tracker at `fcc992514`): when that field lands, a
  channel's messages take it as its requests do.
- Python's standard library alone, as every module of `S/` today.
- An engine and its credentials for M5 and M10's live scenarios. M10's are
  reported as not run without them; M5's scene must complete before the
  acceptance, in M5 or in M11.

## Surprises & Discoveries

- Observation: a session is the wrong key for a channel's debt. This
  plan's first form kept the debt in the delivery record of the channel
  and the thread's current session and moved it between sessions (a
  lineage argument to `_owed`, a larger-of merge of settled positions, a
  last check that settled). Both reviews broke it from different sides:
  one writer's earlier message held for a thread and its later one pushed
  to a provisional job leave a merged position that drops the first; a
  pass that lost its session to a hand-off settled the event it could not
  push; two sessions of one thread had two locks.
  Evidence: `_conclude` advances the writer's settled seq for any outcome
  it concludes; `delivered_load` and its lock are keyed by what
  `reader_key` is given; `_merge_absorbed` keeps the continuing thread's
  `began` where both threads were in a channel. The rulings of 2026-11-22
  (Decision Log) make the thread the key.
- Observation: the delivery operation reads a member's membership from the
  log the event lies in, in five places, and both ask loops choose by the
  current session before any selection runs.
  Evidence: `held_owed`, `push_event`, `holder_push` and `wake_member` each
  read `latest_membership(_own_events(project, session))`, and
  `canonical_end` the fold of the same; `words_due` and `reach_due` skip a
  member whose session is not in `addressees(events)` and take
  `_owed_kept`'s share by session; `_first_owed` selects by session.
- Observation: a push made from the consumer thread is not bounded by
  bounding its delivery lock.
  Evidence: `holder_push` plans a receipt under the receipts' own locks
  (`sminos_holder_deliveries`), a wake writes its line under a store lock
  and launches an engine with a timeout of minutes, and `project_path` can
  wait on a registration's lock for a home it has not seen.
- Observation: a displayed row is no history of who held a session.
  Evidence: `View.ended` is built from sessions whose latest membership is
  an end and that no seat stands for; `former_ids` leaves out a row's own
  session; `_projection`'s `episodes` hold each stretch of a session under
  one thread, with its stamp.
- Observation: the leaving rule counts requests alone, and CH1's refusal
  of a write the enrollment does not carry spares a channel that has left.
  Evidence: `Link.may_leave` reads `sminos_channels.outstanding`;
  `_refuse_uncarried` passes `LEFT_HERE`; a person's append may wait in
  `queued/` with no seq, and `channel_positions` reads `log/*.jsonl`.
- Observation: three fixtures would have proved less than this plan first
  claimed of them. The stand-in's relay attests every upload alike and
  gates none on a `snapshots?`; the bench's stand-in lists no capability,
  and its `verbs` checks no exit code; two plain repositories on an
  enrolled machine are one project, the machine's own, and a bare `claude
  -p` is no member (`joinable`).
- Observation: a delivery record remembers an attempt after the debt has
  dropped its event, and then lets nothing else of that writer through.
  Evidence: a failed attempt leaves `pending` in the writer's entry
  (`delivered_fail`), and `_next_check`, which `delivered_settle` and
  `delivered_fail` both call, raises for any other seq while it is set. In
  a project nothing takes an owed event away but its settlement; in a
  channel a boundary does.
- Observation: a thread's id is not always new. A seat's id is its first
  session's (`seat add --session S` makes the seat `S`), a purge deletes
  the seat's file, and a seat made again over `S` has the id again.
- Observation: an unreadable delivery record reads as an empty one.
  Evidence: `delivered_load` answers `{}` for a file that is not there and
  for one that does not parse; `daemon owed` inspects the file itself
  before it trusts the answer.
- Observation: the replies were not the only work a channel's message
  would have put on the consumer thread. Evidence: `reach_due` plans an
  event that has a receipt under the receipts' lock
  (`sminos_holder_deliveries.plan`, which waits for it; without `prepare`
  it takes no other); `expire_asks` reads `held["member"]` and calls
  `words_unanswered`, which takes the session's delivery lock and counts
  an attempt; `senders_before`, for a sender whose frame is not on the
  lane, reaches `member_under`, `Plane.refresh` and a view.
- Observation: keeping an absorbed thread's mail cost more than the mail.
  An absorbable record is the one a session got of its own before its
  hand-off was read (`absorbable`: opened by its human, one session, no
  open entry), so it lives for moments; keeping what named it needed a
  key in the merge, a second delivery record and lock for one event, a
  list scoped by channel, a seat's projection of the key (`_of_seat`
  copies a fixed list) and a third stale-mark rule in the wake. The third
  read's findings 6, 9, 10 and 11 were each one of those.
- Observation: CH1 had already written the last check this child needs.
  `set_channels`' check under its lock reads, in order: that the
  session's current record, read afresh, is the thread's
  (`current_record(…, fresh=True)`); the session's record, where missing
  is absence (lane A) and there-and-unreadable is not; the reach token;
  the session's own events by this machine's names as its file has them
  now (`own_events_now`); and whether the project is where the session is
  now (`_current_here`: registrations and logs by literal paths, two
  memberships of one millisecond deciding for neither). The third
  revision named `member_project_now` for the last of these, which takes
  the later of two equal timestamps by its scan's order and globs the
  home's path, so a bracket in it is read as a pattern.
- Observation: the ask and the push read a held receipt by two rules.
  Evidence: `holder_owed` turns a plan of `awaiting`, with no process
  running and the session the current one of a lane A thread, into a
  retry that wakes; `reach_due` asks only about a plan of `push` or
  `legacy`. Where the endpoint decides reach the retry then waits for a
  word no one asks for, in a project as in a channel.
- Observation: a receipt is found by an id that carries its key's hash,
  and the admitting side never computes that hash (`_held_receipt` takes
  the path from the id and checks the session), so what a receipt is
  found by can gain the thread without the bridge knowing a thread.
- Observation: a removal cannot land under a wake. `set_channels` takes
  the wake lock, which `wake_member` keeps through the launch and the
  push; so what can change across a launch is the reach, the machine's
  policy and a signer's revocation, and a removal is busy until the push
  is done.
- Observation: `main` moved under the plan. sminos 1.54.1 holds a
  message's ask on a reply that names no verdict, for a project too, so
  the TECH-DEBT row on it is gone and this child has nothing to decide
  there.
- Observation: the scene on a real engine (M5) held as the suites staged
  it, and the composite's delegated unknown, a non-empty boundary across a
  real hand-off, holds: the engine's own order kept the thread's boundary
  byte for byte, its one delivery record (the same file, the same inode),
  and a reply line of a frame sent before the hand-off reached the job
  once. Both of the scene's pushes went through the engine's inbox (live
  and on a wake); none went through the bridge.
  Evidence: M5's report, step 4.
- Observation: on Claude Code 2.1.330 `claude --resume` of a running
  background job attaches to it, and `/background` in an attached view only
  detaches; a hand-off needs a terminal process (stop the job, resume,
  `/background`). Concrete Steps' step 4 is worded so.
- Observation: the engine's auto mode judges a peer reply call by call:
  one session's unasked reply by a channel frame's line was refused as
  unsanctioned communication and allowed once its user asked; another's
  was allowed. It bears on what M10's E2 and E4 can expect of a session.
- Observation: a long `SMINOS_HOME` defeats the bridge silently: a
  `bridge/<uuid>.sock` path past 103 characters cannot be bound by Python
  on macOS. The base's; a TECH-DEBT row ("sminos channels") records it.
- Observation: the checker (`channel_wire.published`) reads a dict as a
  bare frame, so the stand-in's control `state()["received"]` (dicts of
  `conn` and `frame`) passes unchecked; the suites pass `ep.received`
  (tuples) and are unaffected. M6, which touches `published`, makes it
  refuse a shape it does not know.
- Observation: what a channel costs (M7's bench, the MacBook's shape,
  thirty channels). A thread in channels pays about half a second more a
  command, flat in the number of channels: `list` 0.95 s against 0.35 s,
  a tagged `say` 0.80 s against 0.32 s, `channel show` 1.25 s with thirty
  known and 1.35 s with one. The idle uplink: 32,909 calls a second with
  no channel, 39,033 with thirty followed and none held (no debt read),
  41,504 with thirty held; the merge base reads 37,995 with thirty
  followed. An upload costs 5,730 calls a message from one sender and
  9,406 from ten.
  Evidence: M7's report, §2.

## Decision Log

- 2026-11-22 — **The plan as written, and its verification.** Written by a
  session the composite's holder dispatched, against the code at `1a3c1ac5`
  (sminos 1.54.0), MAWS's master read at `fcc992514`, and the composite as
  three revisions left it during the writing: CH1's landing (`81ea8848`),
  its correction from a read against the code (`b8145982`), and the
  owner's ruling that a thread that is no member may write into a channel
  (`59782bb8`). *Verification:* this plan is reviewed before M1 (the
  entry below); each milestone through doperpowers:review-code, three
  reviews at most (the owner's bound), at the medium rung, and at the high
  rung for M2, M3 and M6 (the debt; the delivery operation; the wire);
  M6's review reads M2 to M6 as one range; the range M1 to M9 by the
  holder's panel at the frontier, with the lenses Plan of Work gives; and
  the panel on the branch at the end, the holder's.
- 2026-11-22 — **The plan's two reviews, the holder's rulings, and this
  revision.** Two adversarial reads of the plan as first committed
  (`07fabf12`): of its design, eleven findings, and of its buildability,
  fourteen. The holder ruled on them the same day, and this document was
  revised in place against the code at `bc528d6d` (sminos 1.54.1). The
  rulings, in short: in a channel a message is owed to a thread, by its
  thread id, in nine points (addressing; the debt and its record; a pass
  that lost its session; the absorption; a reused session; the asks; a
  kept answer's binding; the reply line; the helpers that read "the
  member's log"); nothing a channel's message causes on the consumer
  thread launches, pushes or waits without a bound; "settled at its end"
  as the plan had it; the lead takes its thread's audience; the copy as
  `record_copy` has it; the manager never keys by a display name alone;
  and the proofs each read asked for. MAWS's architect answered that day
  what §4 now states, and its fixture's cases 16 and 17 landed
  (`81372fd61`).
  - *Every finding, and what became of it.* "D" is the design read's,
    "B" the buildability read's, in their order.

    | Finding | Became |
    |---|---|
    | D1 a delayed message can wake a thread that came to hold the session | a message names a thread; nothing is owed by session (§2, §3 row D13); tested on one machine (M2) and two (M6) |
    | D2 the old reply line names a session's prefix, not its author | the reply line names the sender's thread; `reach_in` reads a thread id first, a session's id through `claimants`, and a thread that was never in the channel is no old reply (§1); the scene relays the removal before it expects the direct reply |
    | D3, B1 the larger of two settled positions drops mail at an absorption | no position is merged: one record a thread, an absorbed id's mail judged by that id's own record (§3 row D7), with the two-message, one-writer test in both orders (M2); row D7 now says CH1 keeps the continuing thread's boundary where both were members |
    | D4, B2 a losing pass settles the successor's mail; two sessions, two locks | one record and one lock a thread; the last check settles nothing and a pass that lost its session stops (§3); both interleavings behind a barrier (M3) |
    | D5 nothing settled at an end widens the older return's exception | accepted by the holder as the plan had it; row D10 and Constraints say so, and M2 tests two messages under each kind of return |
    | D6 a plain lead can publish a private session's id | the lead carries its thread's session and takes its audience; a plain clearing event goes first (§5); M8 reads the raw upload and a less-privileged reader's log |
    | D7, B9 the outsider's copy is not guaranteed by `record_copy` | the copy is `record_copy`'s as it is, its privacy guard kept; Constraints and §2 say "where today's rule leaves one"; M4 crosses an unfiltered home with a private recipient, and split audiences |
    | D8, B14 the manager keys a log by its display name | candidates under a display key with their logs' ids, certified only by exactly one matching body (§6); tested with a project and a channel of one name (M9); `frame_landed` likewise claims nothing across logs of one name (M4) |
    | D9 a compaction forgets an exchange when a member leaves | `roster_text` reads the channels the thread's statements have named, the newest ten; a peer by its thread, its name from the event where no row gives one (§6, M9) |
    | D10 the live and skill proofs can pass without the behaviour | one completed scene before the acceptance (M5, M11); E1's store must hold an intended `say` (M10); B7 with a second question closed and a control left open (M9) |
    | D11 the taught milestone could change every frame's reply line after B11's comparison | any change is a channel's frame's alone; M11 compares the final exchange of sessions that use no channel on a machine that knows one |
    | the design read's notes: a write into a channel that already left; a tagged notice with a lead under `words` and `peer`; the choices a person would notice | M6 (the write reopens the log); M8's seam and the scene's step 8; the open points below, which now list each of them |
    | B3 the wire pass can block the uplink behind a push or a wake | the uplink pushes nothing for a channel: it keeps the word in a file and the daemon's channel pass carries it out (§4); M6 proves frames handled with the locks held and a launch stalled |
    | B4 the hold and retirement checks read the wrong log | with `owing` each reads the thread's own project (§3); M3's second seam; M2 and M3 are two milestones |
    | B5 a kept verdict is not bound to the recipient's reach | a word is bound to the thread, its session, its `reach_token` and the event; the check is made at the selection, at `queue_asks` and at the push (§4, M6) |
    | B6 extending `_owed` alone leaves inherited mail unaskable | one selection, `owed`, which both ask loops, the reply's carrying out and the first-owed lookup use (§3, §4) |
    | B7 a displayed row is no history of who held an id | `claimants` reads the logs' episodes across projects (§1) |
    | B8 leaving must handle queued writes and departed channels | `unsent` and `Link.may_leave`, mandatory in M6; the queued message's boundary rule stated (§3 row D14) |
    | B10 the bench sat before the wire it was to measure, and could time failed verbs | the bench moved behind the wire (M7): three shapes, the stand-in listing the capabilities, exit codes checked, matched pairs, the upload's cost; the gate untouched |
    | B11 the stand-in cannot prove attestation or the snapshot gate | the stand-in proves order and shape; MAWS's fixture states the rest, replayed in M7 (§8) |
    | B12 the live proofs lacked prerequisites | distinct hub projects, asserted; sessions that join; both arms one executable; M4 asserts a cut-over notice recorded, M6 its delivery (Concrete Steps) |
    | B13 the older-copy matrix needs an enrolled 1.54 arm | M11's own arm, with its own expectations |
    | the buildability read's note on `list` | `list_scope`'s split of its arguments kept (M4) |

  - *What the code made of the rulings.* Each of the nine points was read
    against the code before it was written here, and none is worse built
    than what the plan had. Three things the code adds to them:
    - *(Withdrawn with `absorbed`: the entry below.)* The continuing
      record keeps no absorbed thread's id today
      (`_merge_absorbed` writes `channels`, `began`, `answered` and the
      entry's `merged`), so the fourth point needs a key of its own in
      that merge, `absorbed`, and an absorption an older finisher carries
      has none. And where both threads were in a channel the absorbed
      thread's own boundary is not kept, so its mail is judged past the
      continuing thread's.
    - The thread as the key runs through the delivery operation, not
      beside it: `deliver_next` reads one `session` for the record, the
      lock, the marks, the hold, the reach, the receipt and the push, and
      with `owing` that one name becomes three (§3). It is the larger
      change to the operation of the two this plan has had, and the
      reason M2 and M3 are now two milestones.
    - A thread-keyed debt reaches a refill's new occupant (row D8), where
      T1 never carried a held event across a refill in a project. It
      follows from the ruling as worded; it is listed as an open point.
  - *Decided by this plan, where the composite does not,* as the list
    stands after the revision (the holder folds it into the composite's
    Decision Log, or overturns an entry here).
    1. Delivery in a channel reads this machine's thread records and the
       channel's log, never a roster, and no tick reads a roster.
    2. One delivery operation, with `owing`: in it the thread's id for the
       debt, its record and its lock; the session for the process; the
       thread's own project for membership.
    3. One selection, `owed`, which applies the boundary itself. Nothing
       is written when a thread enters, leaves, ends, returns or changes
       session, and no two records are ever merged.
    4. The last check settles nothing: a pass that fails it stops for
       that thread. Nothing is settled without a push but what the
       operation settles today on its own evidence.
    5. The absorbed ids are kept in the record (`absorbed`) by the
       absorption's merge; mail that names one is judged by that id's own
       record, past the continuing thread's boundary as merged.
       *(Withdrawn on 2026-11-22 by the third read's rulings: the entry
       below.)*
    6. A refill's new occupant is owed what names the thread.
    7. A `say` in a channel carries its sender's thread; an entry of `to`
       carries its recipient's, taken from the row's statement; an entry
       with none names no one.
    8. A member's frame's reply line is `reply_line`'s one form given the
       sender's thread and the channel; an outsider's is today's.
    9. A name in id form through a channel: a thread's first, a session's
       through `claimants`; `once_in` tells an old reply from a stranger's
       id; a thread once in the channel with no row now is sent nothing.
    10. The project's path keeps its session-addressed events and its
        open row.
    11. In a channel's log "this machine's own" is `appended_here` for a
        message, and a `say` there is receipted.
    12. A channel's delivery outcomes stay on the machine.
    13. `HubLog.deliver` is not changed.
    14. The uplink asks about a channel's messages and keeps each answer
        in a file; the daemon's channel pass carries it out. A kept word
        is bound to the thread, its session, its reach and the event, and
        is good for sixty seconds.
    15. Membership and the boundary are read at the selection, at
        `queue_asks` and at the push or the wake.
    16. A followed channel does not leave, and one that left comes back,
        while this machine's messages there have not gone up; a queued
        person's message is past a boundary taken while it waited.
    17. With `--in` the tags are looked up in the channel alone; a message
        whose tags name a channel and another log is refused; a reply to a
        member that has left is sent directly only for a tag qualified by
        the channel.
    18. Whether a sender is a member is read once, in the door, from its
        own machine's record. A say into a channel needs the channel
        registered and the enrollment's carry of its log, and no
        capability.
    19. A non-member's copy is `record_copy`'s as it is; its frame says
        ` (not in <channel>)` after the alias, and `chat <channel>` shows
        the same.
    20. `chat <channel>` is a read of its own, open to any reader of the
        log; in a channel the chat cursor is the thread's; `list
        <channel>` keeps `list_scope`'s reading; `find_project` keeps
        refusing a channel everywhere else; `frame_landed` claims nothing
        across logs of one name.
    21. `channel-lead` carries `thread` and that thread's `session`, under
        the audience the thread requires; a plain clearing event goes
        before a private one; the last event a machine can read decides,
        and a lead not in effect does not give way to an earlier one; the
        verb is refused where the stream choice is.
    22. The engine's collision name (E15): nothing is added.
    23. The exchanges after a compaction read the ten channels the
        thread's statements named most recently; a peer is its thread.
    24. The manager certifies an owner's post only by exactly one
        candidate body under its display key.
    25. The checker's rules: three new (a `copy`, or a `from_project` on a
        `human` or a lead; an entry with no `thread`; a lead with `to`),
        two changed (`words?`, `reach?`).
    26. One completed scene on a real engine before the acceptance, run in
        the middle (M5) against a stand-in without `reach`.
    27. The fixture's replay and the bench come after the wire (M7); the
        idle gate is not touched.
    28. The taught surface stays in this child; both arms of its
        evaluation run this tree's executable; `send` leaves what is
        taught; a frame's reply line may change for a channel's frame
        alone.
    29. 1.54.1 joins the older-copy suite as its merge commit, with an
        enrolled arm of its own; sminos becomes 1.55.0.
    30. Eleven milestones; M6's review reads M2 to M6; the frontier after
        M9.
  - *Open points: the owner's, or the holder's, each built on the
    recommendation named, which is cheap to change before the merge.*
    1. A selector that names a channel (`say --project <channel>`).
       Recommended and built: refused, pointing at `--in <channel> "@all
       …"`. The other reading makes it `@all` in the channel.
    2. Who may write under the human writer. Recommended and built: any
       machine where the channel is registered and carried, with no check
       of the pool; D4 gives EN the duty to post into each pool channel
       and prescribes no check at the door. The acceptance's "a channel
       whose pool holds the machine" is read as the scene to show.
    3. A verb's bare name (`send worker`, `status worker`, `retire
       worker`). Recommended and built: not widened to shared channels; a
       verb reaches a thread of another project through a channel only as
       `<channel>/<alias>`.
    4. The sentences of §2 and §5, the clause a frame carries for a
       sender outside the channel (§3), and the lines of a recipient this
       machine does not deliver to, are this plan's drafts of what a
       session and a person are told.
    5. A lead on another machine than the one the command runs on.
       Recommended and built: taken, and said; a private lead is said to
       be private.
    6. The reply line's words (§7): a channel's frame's line changes only
       if the evaluation shows sessions still breaking a reply on it; a
       project's frame's line is not touched.
    7. What the roster's cost (M7) is allowed to be before the deferred
       index of statements is promoted: the holder's call on the figures.
    8. The idle gate's limit (the TECH-DEBT row whose trigger is this
       child's first milestone). Recommended: not derived again here.
    9. Whether a project's messages should name threads too (§3).
       Recommended: not in this child; it changes an event every
       installed copy reads.
    10. `chat <channel>` by a thread that is not in the channel (allowed),
        `chat --host <channel>` (refused), and `list <channel>` as a
        positional (allowed).
    11. Eleven milestones in one child. Recommended: kept whole (Plan of
        Work says why); M10 can still be cut at the frontier.
    12. A refill's new occupant receives what its thread was owed (row
        D8). Recommended and built, as the ruling reads; T1's rule for a
        project is the opposite.
    13. Sixty seconds for a kept word, and ten channels for the
        exchanges' look back: both this plan's figures.
    14. A private lead is announced to the readers who may not read it as
        "no lead" (the plain clearing event), which also tells them that
        the lead changed. Recommended and built.
  - *Where the composite and this plan differ beyond what the rulings
    already amend,* for the holder (the rulings' own list: C5's
    thread-addressed message and its reply line, "settled at its end", the
    copy; C2's lead; C1 on `HubLog.deliver`; Risks on a roster read in the
    tick):
    - Y3 says CH2 adds "the settlement, in the thread's delivery records,
      of what it pushed or dropped". Nothing dropped is settled here
      (decisions 3 and 4), and the records are a thread's.
    - The Grounding Baseline's "delivery state, the hold and the wake are
      keyed by (log, session) and need no new key": in a channel the
      delivery state is keyed by the log and the thread.
    - The parent's X2, "session ids stay what addresses a message": in a
      channel a thread's id addresses it for delivery, and the session's
      stays for the endpoint. X1's list of the record's fields gains
      `absorbed`, and C3's "a provisional thread that is absorbed" gains
      that its id is kept. *(The second sentence is withdrawn with
      `absorbed`: the entry below.)*
    - C1 and the parent's D3 ("a channel exists while"): a machine keeps
      following a channel while it holds a request it wrote that is
      outstanding; now also while a message it wrote there has not gone
      up.
    - The delegated unknown "what a roster costs…, measured in its live
      pass", and the acceptance's line that lists the roster's cost with
      the scene on a real engine: it is measured by the bench, after the
      wire (M7), at the fleet's shape, since `rosters` reads every
      project's view and thirty channels alone measure little.
    - "CH2's older-copy suite gains 1.54.0": 1.54.1, which `main` has
      since released.
    - The child's inheritance says the checker is "called with the kinds
      CH2 adds and with `deliveries=False`": no argument allows a `words?`
      or a `reach?` about a message, so its rules change.
    - C5's "the sender is told … in one line": where `record_copy` keeps
      no copy for privacy, the sender reads that warning as well.

- 2026-11-22 — **The third read, the holder's rulings on it, and the
  last revision before the build.** One adversarial read of the revision
  (`2e6d8d1b`), over the parts it rewrote: sixteen findings, fourteen P1
  and two P2. The holder ruled the same day, and this document was revised
  in place against the code at `bc528d6d`; the header's pins are the
  holder's to move. The rulings, in short: no absorbed thread's id is
  kept, and what names an absorbed thread is owed to no one; nothing is
  delivered or asked over an open entry; a seat's id over a purged seat is
  that thread; a `pending` the debt has dropped is cleared under the lock
  before anything is pushed; one owner of the lock when a kept word is
  carried out; the three paths the consumer thread's mechanism had left;
  what the endpoint's word is good for; the last check reads the lane, the
  session's record and the thread's own project; a row is addressed from
  one reading of it; `daemon owed` stays a read, and a delivery record
  that cannot be read is not an empty one; a channel's receipt names its
  thread; and three smaller ones. What the read found sound stays as it
  was: the order of M2, M3, M6 and M7, a minted id as a record's key, the
  launch barrier, the bench's options made in the milestone that uses
  them, and that a missed nudge or a dropped word loses no debt.
  - *Every finding, and what became of it,* in the read's order.

    | Finding | Became |
    |---|---|
    | 1 a purged seat's thread id can be issued to another seat | by the holder's ruling it is the same thread: the same record, owed what names it past the boundary its new membership gets (§3, "A thread's id is the thread", row D15); D13 narrowed to a thread with another id; tested in M2 and as a push in M3 |
    | 2 a kept verdict can outlive the authority for its push | what the word is good for is stated (§4): `WORD_KEPT` to begin, and one launch; what this machine can read is read again after the launch and before the text is handed over (§3, M3's and M6's seams); what only the endpoint knows is on the accepted list; `reach_token` is nowhere called the endpoint's |
    | 3 a failed event below a new boundary wedges its writer | `normalize`, under the thread's lock after the last check (§3); transitions still write nothing; M3 crosses a failed attempt, a removal and add, a second message and two ticks, and the same over a return anew |
    | 4 carrying a kept word reacquires the lock already held | `carry_words` takes none; `deliver_reach` and `deliver_verdict` take the thread's lock once and check and remove the word under it (§3, §4); two real carrying processes under a timeout (M6) |
    | 5 asking, timeout and upload still block the consumer | the receipts' lock is tried and a busy one defers the ask; a channel's unanswered ask is dropped and writes nothing; a message's upload reads the plane's row and waits where there is none (§4); each proved with its lock held elsewhere (M6) |
    | 6 absorption makes removed memberships eligible again | gone with `absorbed`: a thread is owed what names its own id and nothing else (§3 row D7) |
    | 7 a provisional current owner can receive mail before a rollback | `owing` is None while the record holds an open entry (§3 rows D6, D7, D12; Constraints); M3 cuts an absorption after its `begin`, runs a pass and undoes the claim |
    | 8 moving projects or changing lanes defeats the last check | `still_owed` reads the session's record, its lane and the project it is a member of now; `push_event`'s `retired moved` is a stop for a channel (§3); M3 crosses a `join`, a change of lane and an unreadable record with an event already selected |
    | 9 absorbed hold marks can suppress the wake | gone with `absorbed`: a mark is in the thread's own record, where `wake_member`'s comparison holds (§3) |
    | 10 a multi-address event cannot settle every matching record | gone with `absorbed`: an event is settled in one record, the thread's |
    | 11 spawned records do not expose the absorbed ids | gone with `absorbed`: `S/sminos_threads.py` is not changed |
    | 12 a raw thread stamp does not prove membership | `thread_of_row` gives the thread and the session from one reading of the row and answers none where the stamp and the statement in effect disagree; `once_in` counts statements that took effect; `claimants` answers none over an episode with no thread (§1, §2; M1, M4) |
    | 13 `daemon owed` loses its read-only contract | `Debt` (the record alone) apart from `Owing` (a row, a reach); `owed_here` reads no view and writes nothing (§3); M2 runs it cold over an open entry and compares the home before and after |
    | 14 recovery and the sender's report still take a session for the record | a channel's receipt keeps its thread in its key and `sweep` reads that thread's record; `deliver_say` reads the thread's record for a held mark and a settlement (§3; M3, M4) |
    | 15 an unreadable delivery record reads as no deliveries | `delivered`, strict: delivery defers and `daemon owed` says it cannot tell; an absent record is an empty one (§3; M2) |
    | 16 the scene asserts an id the command does not print | the two projects' ids are read from the registrations and the two `joined` events (M5, Concrete Steps) |

  - *What the code made of the rulings.* Each was read against the code
    before it was written in, and each can be built as stated. Where the
    code shaped the form:
    - *The pending mark.* The ruling names a writer's `pending` and its
      attempt count. A pushed note rides in the same entry
      (`delivered_pushed` writes it with `pending`), so it goes with them.
      A held mark is left: it stops nothing in `_next_check`, it is read
      only for an event the selection chose, and the record's own writer
      drops it once the prefix passes it (`_entry`).
    - *The receipts' lock.* `plan` without `prepare` takes that one lock
      and no other (`handoff` without `choose` reads the process's mode
      under none), so a deadline on it (`lock_until`, as `flocked` already
      takes one) is the whole change, and `exists` reads under no lock
      already.
    - *(Replaced by the fourth read: decision 46 below.)* *The project a
      thread is in now* is `member_project_now`, which
      reads every project's registration and the session's own events
      there under no lock. It answers the destination of a move whose
      source's retirement is not written yet, which is the "between two"
      the ruling names. It is paid only where a pass has an event to hand
      over.
    - *A seat's open entry* is readable where a human-opened record's is:
      `_of_seat` copies `pending` into the record it gives.
  - *Decided by this plan in this revision,* beside the list of the entry
    above (whose 5 is withdrawn, and whose 2, 3, 4, 7, 9, 14 and 15 are
    amended by these):
    31. No absorbed thread's id is kept, and what names an absorbed thread
        is owed to no one (the holder's ruling; a TECH-DEBT row written in
        M2). This child writes nothing in a thread's record.
    32. What the selection needs (`Debt`) is read from the thread's record
        alone, and an open entry hides no debt from `daemon owed`; what a
        push needs (`Owing`) is not given while an entry is open.
    33. A channel's delivery record is read strictly (`delivered`); one
        that cannot be read stops delivery for that thread and is listed
        by `daemon owed` among what it could not inspect.
    34. `normalize` clears a dropped event's `pending`, with the attempt
        count and the pushed note in its entry, and leaves held marks.
    35. The last check reads the session's record, its lane and
        `member_project_now`, and after a wake's launch the session's
        reach and the signer's revocation as well; a failure there hands
        nothing over and launches nothing again. *(Amended by the fourth
        read: 44 and 46 below.)*
    36. A kept word is checked and removed under the thread's lock by the
        entry point that carries it out; `carry_words` takes no lock.
    37. A channel's ask that goes unanswered is dropped and asked again at
        the ordinary interval, for a `words?` as for a `reach?`: no
        attempt is counted, so it is never given up (a project's `words?`
        is, after `DELIVERY_ATTEMPTS`). The ruling allowed the count if
        the daemon kept it; none is kept, since it would need a second
        file from the uplink for a case that ends in a person's words
        dropped.
    38. The receipts' lock is tried in a channel's choice of what to ask
        (`plan`'s `lock_until`), and a busy one leaves the event for the
        next pass.
    39. Any frame of a channel's upload that carries a `say` or a `human`
        takes the plane's row for each sender and waits where there is
        none, whatever else the frame carries; a frame of CH1's kinds
        alone keeps CH1's path.
    40. A channel's receipt keeps `thread` in its key beside its session;
        its lookup stays by session. *(Replaced by the fourth read: 47
        below.)*
    41. A row is addressed from one reading of it (`thread_of_row`), and
        one whose stamp and statement name two threads is given no entry
        and the sender a line; a session whose history holds an episode
        with no thread names no one thread.
    42. A seat made again over a purged seat's session is that thread
        (row D15), on the holder's ruling.
    43. The fixture is copied at MAWS's master `5a88bcd83`, cases 16 to
        19.
  - *Open points, added.*
    15. A channel's `words?` the endpoint never answers is asked for as
        long as the message is owed (decision 37). Recommended and built;
        the other reading gives it up as a project's is given up.
    16. The line a sender reads for a row that is not addressed (§2) is
        this plan's draft.
  - *Where the composite and this plan differ beyond what the two sets of
    rulings already amend* (the second set's own list: no `absorbed`, the
    open-entry deferral, a seat's id over a purged seat, the verdict's
    window). The list of the entry above stands but for its sentence on
    `absorbed`. Added by this revision:
    - CH2's inheritance says a message written into a channel meets
      `Link.senders_before` "as a request does". A frame that carries a
      message now reads the plane's row alone and waits where there is
      none (decision 39); only a frame of CH1's kinds meets it as before.
    - The acceptance's "pushed … to the session that continues the thread
      after a hand-off" and "when the thread is woken or reopened while
      still a member" hold once the transition's entry is closed, and
      while the thread's session is a member of the project the pass
      read: a pass that meets a move to another project, a change of lane
      or a record it cannot read delivers nothing and leaves the debt
      (decision 35).
    - Nothing in the composite says what an unanswered `words?` about a
      channel's message becomes; a reader who takes the project's rule
      for it (given up after `DELIVERY_ATTEMPTS`) reads the opposite of
      decision 37.
    - Y3 and C3 give a membership's boundary as the whole of what delivery
      reads of a transition. The delivery record of a channel can also
      hold a `pending` from before the boundary, which this child clears
      (decision 34): the one write a transition leaves for delivery.

- 2026-11-22 — **The fourth read, and the edits before the build.** One
  narrow read of what the third revision changed (`db270e65`): ten
  findings, six P1 and four P2, with the verdict "ready with the listed
  edits, not as written; no further design round". The holder took all
  ten as stated, with notes; each was read against the code (unchanged
  under `sminos/` between `bc528d6d` and the pin) and written in as
  stated. The header is re-pinned to the branch with the composite's
  amendment merged (`f2c737f2`). Nothing reads this document again before
  the build: what it leaves goes to the executor as amendments here.
  - *Every finding, and what became of it,* in the read's order.

    | Finding | Became |
    |---|---|
    | 1 the post-launch check omits the machine's read-only policy | after a launch the two refusals the operation makes itself are read again, a revoked signer and, for an outside event, a read-only machine; found there, nothing is handed over and the event is refused as before a push (§3); M3 and M6 cross the barrier with a machine-policy change apart from a change of reach |
    | 2 a stopped recipient with a receipt can wait forever without an ask | `holder_due`, one reads-only classification: `holder_owed` answers by it and a channel's `reach_due` chooses by it (§3, §4); M6 stages the `Awaiting` fixture in a channel with endpoint reach on: one ask, one wake, a settlement |
    | 3 the old side of an in-progress absorption can still pass the check | the last check requires that the session's current record, read afresh, is `o.thread`'s and holds no open entry, beside the captured thread's own file (§3); M3 lets go a pass selected for the provisional record before `begin` and before the reservation |
    | 4 the fresh project lookup can pick a tie or find no project | the last check reads the captured project by `own_events_now` and `_current_here`, not `member_project_now` (§3); M3 crosses the same-millisecond tie and a home whose path holds a bracket; the glob's reading of a bracket is the base's, a TECH-DEBT row written in M3 |
    | 5 receipt lookup can use another thread's admission | a channel's receipt is found by its session and its thread together: `key_hash` and every lookup through it, and `sweep` (§3); the admitting side finds a receipt by its id and needs no thread; M3 serves two addressees of one event from one session in turn |
    | 6 normalization treats a read failure as proof | `normalize` clears a `pending` only at or below the boundary read afresh for its writer (§3); M3 makes one writer's file unreadable beside a readable one and restores it |
    | 7 a missing session record has two rules | one rule at `owing` and `still_owed`: not there is lane A, with the token `reach_token` gives for it (None, equal to itself alone); there and unreadable defers (§3); M2 and M3 cover a genuine absence |
    | 8 the launch/removal proof needs a forbidden interleaving | the seam now says a removal is busy under the wake's hold and lands after the push, and that one made before the hold leaves nothing owed; the invalidations after a launch are reach, the machine's policy and the signer (M3) |
    | 9 the unreadable-thread diagnostic cannot be built from `set_holders` | narrowed: no debt is attributed to a thread whose own file cannot be read, and an unreadable delivery record is what `daemon owed` diagnoses (M2, §3 row D12) |
    | 10 an absent plane row must not invoke `owing`'s fallback | `owing` takes its row from its caller and looks none up; `asks_due` passes by a thread the plane has no row for; a deliverer reads the row with `own_row` (§3, §4); M6 covers an absent recipient row under a held finisher lock, and a retired sender that owes no frame |
    | the verdict: the row a `to` entry is taken from | `thread_of_row` reads what the roster's own sweep read of the row's view, kept beside the rows from M1 on (§1) |
    | the verdict: the strict loader for the writers too | given a channel's log, the delivery record's writers load through `delivered` and write nothing over a record that cannot be read (§3) |
    | the verdict: what decision 37 holds back | the later messages of the same writer to the same thread, and nothing of another writer or thread (§4, Constraints) |

  - *Decided by this plan in this revision,* beside the lists above
    (whose 34, 35, 37, 40 and 41 these amend).
    44. After a wake's launch the operation's own two refusals are read
        again and made as before a push; any other change leaves the debt
        owed (amends 35).
    45. One classification of a held receipt's next step, `holder_due`,
        for the push in every log and for a channel's ask. A project's
        ask keeps its test, so its calls are today's: the same fault
        there is the base's and is a TECH-DEBT row written in M6.
    46. The last check's reads are CH1's last guard's: the session's
        current record read afresh, the session's record by one rule,
        and the captured project by `own_events_now` and `_current_here`
        (replaces 35's `member_project_now`).
    47. A channel's receipt is found by its session and its thread
        together, in every lookup; a project's key is as it was
        (replaces 40).
    48. `normalize` needs the boundary alone and reads no selection
        (amends 34).
    49. A session with no record is lane A and its reach token is None;
        a record written since is a change of reach.
    50. `owing` looks no row up. A deliverer reads it (`own_row`), the
        uplink takes the plane's, and a thread the plane has none for is
        asked about nothing until it has.
    51. `daemon owed` names no thread whose own file cannot be read; it
        is built on `set_holders`, which gives only records that read.
    52. `_sweep` keeps what it read of each row's view beside the rows,
        and a `to` entry's thread and session come from it (amends 41).
    53. The delivery record's writers read strictly where the log is a
        channel's.
  - *Open point, added.*
    17. Whether a project's ask should take `holder_due` too (decision
        45). Recommended and built: not here; it is one condition to
        drop, and it changes what a project's uplink sends.
  - *Where the composite as amended (`940a5a0b`) and this plan differ.*
    Its C1, C2, C3, C5, Y3 and CH2's section were read against this
    document; no sentence there is contradicted, and four are now
    narrower than what is built:
    - Its Decision Log's "the session for the process (the hold, the
      receipt, the reach, the push and the wake)": a channel's receipt is
      found by the session and the thread together (decision 47).
    - Its list of what is read again after a wake's launch (the session,
      the membership, the lane, the reach token, the signer's
      revocation): the machine's read-only policy, for an outside event,
      is read again too (decision 44).
    - C5's "while a thread's record holds an open journal entry nothing is
      delivered to it or asked about it": nor while the session's current
      record, read afresh, is another thread's, which is the moment
      between an absorption's `begin` and the reservation of the record
      it absorbs (decision 46).
    - Y3's "what it adds is the settlement": it also clears, in that
      delivery record, a failed attempt's mark that the boundary has
      passed, as the composite's own Decision Log says.
- 2026-11-22 — **M1 as built** (`de0ed736`). Decisions the executor made
  where the plan is silent, kept by the controller:
  - A name in id form (a whole id, or its first eight characters or more,
    matched as a prefix) that matches no thread and no session known here
    is read as an alias; a known thread's or session's id is never read as
    one.
  - `reach_in` gains a keyword `at=""`, how its `; elsewhere:` list names a
    row: empty for a verb, `"@"` for a tag (M4 passes it). A thread once in
    the channel with no row now is `("out", None, None)`, and its caller
    words it; the verb's refusal fills the thread's own `alias#short` where
    it has a row, and keeps the literal placeholders where it has none.
  - Three refusals §2 does not give are the executor's drafts (open point
    4): an alias or a thread prefix two rows of the channel answer, a
    session whose thread cannot be told here (`claimants` None), and a list
    of labels none of which can be reached.
  - The bare alias reaches only channel rows of projects a tag may write
    into (`org_scope`); the sender's own project and a verb's target are not
    filtered by it. Two answers are refused as `alias#short`, with no
    project.
  - *(As amended by its reviews, `6e2b7b90`, `78b07c42`.)* Each roster row
    carries what the sweep that produced it read (`_SweptRow`, a `Member`
    with a `swept` field), and `thread_of_row` answers that reading, after
    any later sweep, and never reads again; a row rebuilt with `_replace`
    carries none, so a caller asks `thread_of_row` before it transforms a
    row. `claimants` gives a statement to the episode of the `joined` it
    took effect under, in fold order, never by time; the episode split and
    mark rule is one function, `sminos.episode_step`, which `_projection`
    and the channel fold both call. An episode a seat stamped counts as
    that seat's thread. Rows of one thread (stamp, else the statement in
    effect: `row_thread`, never used to address a row) are one row
    wherever the roster is read (CH1's `list`, `channel show`, the pool
    included), and a bare alias folds them into the roster's row before
    any name is matched, so a name only a stale row held reaches nothing.
    A row whose stamp and statement disagree is neither in nor out and is
    refused, with no recipient offered (the sentence is a draft).
    `reach_in(..., how=True)` adds what the name matched, and a seat found
    through a channel binds its session only for `alias#short`, a
    session's id, or an alias it held before; `alias#short` matches the
    current alias and the current session's prefix at any length. `once_in` and `claimants` leave out sessions the log hides from
    this reader.
  - `sminos help` is not changed in M1 (M4 rewrites it).
  - `channel add` finds its target through `find_target`, so it now takes a
    name through a channel too.
- 2026-11-22 — **M2 as built** (`a604658a`). Decisions the executor made
  where the plan is silent, kept by the controller:
  - `delivered_load`'s parsing is one function, `sminos.delivered_entries`,
    which the channel's strict reader (`delivered`) shares; a project's
    behaviour is unchanged (`delivered_load` still reads a missing and an
    unparsable record as empty). A whole record is a JSON object of writer
    entries, each an object whose `settled` and `attempts` are
    non-negative integers and whose `pending` is an integer or null.
  - `owed` leaves out copies and `legacy/` writers, as `_owed` does for a
    project, and reads through an index by thread kept beside the log
    (`addressed_threads`).
  - `owing` and `still_owed` read the session's record once, the lane and
    the reach token from that one read.
  - `daemon owed` for a channel (`channel_owed`, beside the project path
    moved unchanged into `member_owed`) lists a debt under the thread
    record's alias, a held thread's as waiting, a person's words on a
    cut-over machine as `words`, and an unreadable delivery record among
    the files it could not inspect.
  - The checker, with `deliveries=False`, allows under a channel's
    `delivered/` only `<thread id>.json` (a JSON object of writer entries)
    and `<thread id>.lock`; before, anything there was allowed.
  - *(As amended by its first review, `00e1b6b5`.)* A channel's delivery
    record is whole only when every writer entry has the shape the writers
    write (`whole_entry`): `settled`, `attempts` and `pending` present and
    typed, `revoked`, `held` and `pushed` typed where present; a top-level
    `{}` is an empty record. A record file that is a link to nothing is
    there and unreadable, not absent. `owed_here` reads the shared copy of
    the log, so the index by thread is built once a log. Rows D1 (a
    request carried out), D3 (a stopped thread reopened while a member),
    D6 (the journal still open through the diagnostic), D8 (a seat
    repointed to a lane B session) and D14 (the real queue and its release)
    are staged through the transition itself.
- 2026-11-22 — **M3 as built** (`af78de21`, `11482879`). Decisions the
  executor made where the plan is silent, kept by the controller:
  - The last check fails as an exception, `PassLost`, raised from
    `holder_push`, `wake_member`, `push_event` and `woken_unpushed` and
    caught by the three entry points: no outcome string leaves the record
    alone (a `held:` writes a mark, `recorded` settles), and an exception
    crosses the wake's unlock cleanly. In a channel every `recorded` those
    helpers would return for a lost session (a stale mark, a vacated or
    retired seat, the session now another thread's or ended, an open entry
    after the launch, a wake's `gone`, `lane` or `ended`) is that stop.
  - After a launch the reach, the revocation and the read-only policy are
    read first, then T2's re-read of the member. A revoked signer found
    there is the wake's outcome, treated as the check before a push treats
    one; a read-only machine settles as before a push; a revocation set
    that cannot be read, or a mark that could not be kept, is the stop.
  - A project's pass gets exactly today's arguments: the channel's keywords
    are added only for a channel (`_kw`, `_th`). What is new on a project's
    path is pure predicates (`is_channel_id`, `_thread_of`) and one
    indirection (`_verdict_choice`).
  - The record's writers read strictly by the log's id (`is_channel_id`),
    not by a new argument. `normalize` builds the cleared entry by hand,
    copying the settled prefix, `revoked` and `held`, and drops `pushed`
    with `pending`.
  - `own_row` reads `last_project` and that project's view (`titles=False`;
    the tick's cached views in the daemon); the pass passes by a thread
    whose record holds an open entry before calling it, since a view
    reconciles. `words_due` and `reach_due`, given `owing`, ignore
    `members`. `deliver` catches `DeliveryUnreadable` for a thread and logs
    it; the channel's held-pass memory is daemon functions beside
    `deliver_owed`.
  - The bracket case could not be built as stated: the membership scan's
    unescaped glob sits behind `last_project` and CH1's `change` and
    `_registered_at` too, so under a home whose path holds a bracket no
    thread can be placed in a channel at all. The test stages the record
    by hand and proves the last check and the push there; the TECH-DEBT row
    says channels do not work under such a home and gives the one-line fix.
  - *(As amended by its three reviews, `b544d7f4`, `0c969840`,
    `dddf22b4`.)* A deliverer reads a session's row without reconciling
    (`sminos.member_row`, sharing `view_of`'s cached projection), so a pass
    finishes no other thread's open entry; `own_row` finds the project by
    `member_project_now`'s rule over literal registration paths
    (`_project_now`, validating a moved destination with `valid_name`
    first), which a bracket in the home's path does not defeat, and the last
    check still owns the tie. Each event gets one `still_owed(o, e)` at the
    start of its turn in all three entry points, before any hold,
    revocation, verdict refusal, or an earlier pass's admitted receipt or
    noted push is accepted; nothing is checked between this pass's own
    hand-over and its settlement. A channel's failure is counted only after
    `still_owed(o, e)` is read again, in `_conclude`, and an outcome is
    published only after `_conclude` returns. `holder_push` decides what a
    `recorded` means: after a wake, while the event is still owed,
    `held:starting`; otherwise the stop; and in a channel a recipient with no
    current thread, or retired in its own project, is the stop. With the
    wake lock busy and the session live, `wake_member` answers
    `UNHELD_LIVE` after the last check is read again, and only on that does
    `holder_push` push to the process read afresh; nothing launches without
    the pass's own hold. A person's words reach the bridge under the scope
    `<channel>#<thread>` in the field every loaded bridge keys its marks on
    (`project`), so a 1.54 bridge in a running session keeps two threads
    apart; `sminos/hooks` is unchanged. (Its test pins the key alone; what a bridge
    that took a frame under it writes after is proved in M9, the holder's
    check of 2026-11-22.) A channel's receipt lookup indexes
    the receipt file by seq, remembering its inode, size, mtime and ctime,
    reading on from where the index ends when the file grew and from the
    start when it changed without growing, and answering None when it
    cannot be read; a project's lookup is the old code. The held-pass memory
    of a channel is forgotten when it loses its last holder, a channel
    frame's unread count is by thread alone, and a project's receipt calls
    pass no thread.
- 2026-11-22 — **M4 as built** (`d5c345bc`). Decisions the executor made
  where the plan is silent, kept by the controller:
  - The door is `speak(channel, a, session, tags)`, which works out itself
    whether the say came through `--in`. `cmd_say`'s tail is one path for a
    project and a channel (`say_into`); a channel's say adds a `Said`, and
    a project's runs as before.
  - Refusals the plan does not word, each a draft (open point 4): a
    selector beside `--in <channel>` (exit 1); every tagged row torn
    (nothing recorded, exit 4); a say into a channel id registered nowhere
    ("no channel … known", exit 4; `chat` and `list` of such an id keep
    CH1's refusal). `--in <project>` with a channel's tag is the mix
    refusal from a terminal (exit 4) and today's "--in is for an operator"
    from a session (exit 2). Without `--in`, the mix refusal resolves the
    bare tag to name its project, which reconciles; CH1's test that said no
    member is looked up first now pins "refused, nothing recorded".
  - Several `out` tags to one project go as one direct message to it; any
    other mix with them is the mix refusal. `reach_in` gains `then=""`, for
    `--in`'s "Drop --in to reach it…".
  - A local recipient whose delivery defers (an open entry, lane B) or
    whose delivery record cannot be read reads `pending`. A non-member
    session with no home project writes the member's shape (not possible on
    an enrolled machine).
  - `chat <channel>` leaves out `retired` and `moved` lines. `frame_landed`'s
    rule for two logs of one name applies only where one of them is a
    channel, so a project's is as before.
  - B11 is held by `test_channels_say.py`'s `SameAsBase`, which builds the
    merge base `61b27ebe` from git and compares `say` and `chat` over a
    store with no channel (frames and log, but for ids, times and paths).
  - *(Decided on its second review.)* §2's "nothing appended to any log"
    for a refusal is read as nothing the say itself writes: no message, no
    copy, and nothing the refusal's own path causes, which reads by
    `sminos.logged_members` and reconciles nothing. A refused name that
    reaches `reach_in` still reads the roster, whose sweep reads each
    project's view and so reconciles as every view does (CH1's roster,
    `list`, `channel show`); the lifecycle facts that writes are true either
    way, and making the roster's read not reconcile would change CH1's
    roster for every reader. An old reply to a thread whose project is
    retired or has left the machine is refused in `CANNOT_REACH`'s words by
    the `org_scope` check `@<short>` makes; a torn row's tag is cut from
    the text on every route; a channel's copy is attempted after its
    delivery; one chat body (`sminos.chat_read`) serves a project and a
    channel.
  - *(Its second review.)* The mixed-tag refusal names no project for a
    bare alias it has not resolved: "one message, one log: the tags name
    <logs>; @<alias> resolves outside <channel>" (a draft, open point 4;
    its last review notes it overclaims for a tag no member answers
    anywhere). `@alias#short` and an id-form tag still get their project
    named, from a read that does not reconcile.
- 2026-11-22 — **M6 as built** (`5af6ab8c`). Decisions the executor made
  where the plan is silent, kept by the controller:
  - `unsent` counts a channel's `say` and `human` events alone (counting
    every event broke CH1's leaving rule for its own kinds).
  - A kept word's key (`word_key`) holds the session and the reach, so
    after a hand-off or a change of access the message is asked about again
    at once. A word whose carrying out stops on `PassLost` or an unreadable
    record stays until the next carrying pass or its expiry.
  - The plane's rows (`plane_rows`) leave out a session that two projects'
    rows show until the plane's next read. A `reach?` whose sender is a
    session of this machine with no row on the plane waits while that
    sender is a member of a project now (`_project_now`, files alone).
  - The stand-in applies §8's rules under any project id;
    `T/test-notice-machines.sh` gained `notice_words: true` so it still
    tests sminos's own guard. `T/wire_scene.py` drives one uplink in one
    process, so the wire's comparison with the merge base
    (`WireSameAsBase`) is deterministic. The checker raises on a frame
    shape it does not know.
  - The speak scene of `T/test-channels-machines.sh` covers M11's steps 1
    to 7 and 9 on fresh machines (each with an `auto` policy ceiling);
    M6's cross-machine cases run after it in a channel of their own. Three
    cases are proved by unit tests and not across machines: row D13 (a
    session id another thread reuses), a writing machine's log kept open
    until its message has gone up (a follower leaves only after a day), and
    the read-only refusal after a launch.
  - *(As amended by the range review of M2 to M6, `e7742001`, `d5b03b63`,
    `52d5241d`.)* Every push from a channel reads the last check with the
    reach once more inside the receipts' planner (`plan`'s `check=`), under
    the receipts' lock, just before a plan that pushes is returned (a
    `legacy` plan with no process running, a `legacy` plan after `handoff`
    chose it, past any wait on the process's mode lock, a `push` plan
    without `prepare`) and, for a `gate` process, just before its receipt
    is written; a push it stops leaves no prepared receipt, and an earlier
    receipt is left as it was. A kept word is dated from when the uplink's
    reader took the answer's frame, not from its dispatch. `unsent` counts
    an event only when its writer is exactly this machine's.
- 2026-11-22 — **The holder's rulings on M6 and the range review of M2 to
  M6.** (1) The import of a relayed channel event on the uplink's consumer
  thread (`HubLog.take` → `append_verbatim`, a log's writer locks with no
  deadline) is the base's, as for a project's log and CH1's requests; the
  consumer-thread constraint binds what this child adds there (the asks,
  the answers, a message's upload). Its TECH-DEBT row stands, no deferral
  is built, and the frontier's consumer-thread lens is told this path is
  ruled out of scope. (2) The `sminos-channels` gate's timeout is 6
  minutes from M6 on (`09139114`; 2m48s at M6, twice rounded up), said in
  the pull request's body. (3) The range review of M2 to M6 ran on the
  medium rung (the high rung's reviewer stopped on a gateway error) and is
  accepted as that review; the frontier panel reads the range on the
  frontier model. (4) Row D13, a writing machine's log kept open until its
  message has gone up, and the read-only refusal after a launch are proved
  by unit tests; if M11's scene has a writing machine that holds no member,
  it shows that machine's log staying open until its message has gone up.
- 2026-11-22 — **M7, ruled by the holder.** *The fixture:* MAWS's cases
  16 to 19 at `5a88bcd83` (blob `5ffdd4a2`) do not replay: their `to`
  entries carry no `thread` and the say none, two lines ask about
  threads that are no members (S1, S9), one asks before the recipient's
  member frame (17.2), and 15.2 expects a hello the log's state does not
  send (M7's report, §1). The design does not move (owed by thread id,
  nothing owed to a non-member, the member frame before an ask); the
  cases predate the thread-key ruling, and the holder has asked MAWS's
  architect to amend them on those four points, with a contract point
  that a phone's words under a channel carry `thread` in each entry.
  Until the amended commit arrives through the holder, the tree keeps
  CH1's pin (`27e7208a`, blob `78282c78`) and nothing of the fixture is
  committed; the harness defects the cases exposed (`probe_one_body`
  keyed without the log; `probe_as_stored`, `probe_project` and
  `probe_members` assuming P, Q and S1 to S5; `machine-event` without
  `owners`) are fixed now; and if the commit has not come when M9
  closes, the replay moves to M11, and the proof map's wire half of B1
  and B2 stays unproved until then. *The bench (open point 7):* accepted,
  the index of statements not promoted; the figures (Surprises) and what
  would promote it are a TECH-DEBT row.


## Outcomes & Retrospective

Pending — written at finish.
