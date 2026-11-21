# sminos channels, CH1 — the channel and who is in it: execution (2026-11-21)

> **Composite:** `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`,
> child **CH1** (The channel and who is in it). **Parent pin:** branch
> `sminos-channels-ch` at `ef34f2ca`, that file's blob
> `1b7678de32030360d313da037c78dc372dda1cfe`. The design the composite is itself
> a child of, `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`
> ("the parent" below), is read as that same commit holds it, blob
> `ea0bee4ad3df40cc846a8fcbc8ec4856136b4d9a`: CH's cut revised four of its
> statements, and `main` at `1fdc73a0`, which this branch is built on, predates
> them. The child's section in the composite is its spec; C1 to C4 and C6
> there are its design, binding where marked; Y1, Y2 and Y3 its contracts with
> CH2. This document carries the constraints and the milestones and nothing of
> the design. Read before M1: the composite whole, its Decision Log included;
> the parent's Purpose (the rulings under "What it must not become"), Terms,
> D1, D3, D6, D7, X1, X2, X4, X5, X7, the Risks entry "The store has no writer
> in charge" and the Decision Log entry of 2026-11-21 on CH's cut; the code map
> `docs/doperpowers/research/2026-11-17-sminos-channels/ch-code-map.md`; T1's
> plan `docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`, its Interfaces
> §1 (the record), §3 (the reducer) and §6 (transitions, the journal, older
> copies); T2's plan `docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md`,
> its constraints (the lock order) and its Outcomes & Retrospective; and
> `docs/doperpowers/TECH-DEBT.md`, section "sminos threads".

After this child a declared channel exists and holds members, with nothing
said in it yet. A thread runs `sminos channel create desk-integration` and
`sminos channel add desk-integration <another thread>`: the other thread is
placed without acting, on the same machine when the command returns and on
another machine when that machine's daemon reads the request. `sminos list`
run by a member shows `# desk-integration` with its roster beside the
member's project, `sminos channel show` prints the roster, each request and
what became of it, and the machines the channel's threads run on, and
`sminos channel remove` takes a thread out without retiring it. A machine that
holds a member opens the channel's log at the hub as a holder, so MAWS lists
the channel for every machine while it has a member. Every form of message
into a channel is refused, saying that speaking in a channel comes in a later
version and which tag works today. A session that is in no channel sends and
prints what it did before. How to see it working is CH1's acceptance in the
composite (fourteen items, numbered A1 to A14 here in the order its section
lists them), proved as Concrete Steps maps it.

## Progress

- [x] (2026-11-21) CH cut into two children; its design reviewed twice and revised (`ef34f2ca`); MAWS's fixture on its master at `8ae3b0843`.
- [x] (2026-11-21) This plan written against the composite at `ef34f2ca` and the code at `1fdc73a0` (sminos 1.52.0).
- [ ] This plan reviewed for buildability (Decision Log, "Verification") and its findings folded in.
- [ ] M1 — A channel id is told from a project's at every door, and nothing is published under one.
- [ ] M2 — A thread's declared set: one operation, its statement, its marks, and the log kept equal to the record.
- [ ] M3 — Requests on one machine, and the verbs that write them.
- [ ] M4 — The roster, the listing and the pool.
- [ ] M5 — The wire: the capability, `member.channels`, opening without `follow`, MAWS's fixture.
- [ ] M6 — Requests across machines: the endpoint's word, and what a requester is told.
- [ ] The review of M1 to M6 as one range, by the composite's holder, and its fixes.
- [ ] M7 — Older copies, what is written beside the code, the version, and the acceptance.
- [ ] The branch reviewed at its end (Decision Log, "Verification"), and its fixes.

## Words this document adds

The parent's Terms define thread, project, log, writer, member, channel,
pool, hello, hold, follow, known, the directory, reach, lane B, the hub and
the endpoint. T1's plan defines spawned, human-opened, the seat store, the
thread store, stamped, the journal and its entry. T2's plan defines the wake
lock, the delivery lock and held. Added here:

- **The set** of a thread is its record's `channels`: the declared channels
  it is in, in the order they were added, on its own machine.
- **The statement** is the event of kind `channels` a thread's machine writes
  in the thread's project log (Interfaces §2). **What the log states** for a
  session is the set a reader takes from it by C2's rule (§5).
- **A request** is an event of kind `channel-request` in a channel's log
  asking that one thread be added or removed. Its **requester** is its
  writer; its **target** is the thread it names.
- **The thread's own project** is the project in whose log the thread's
  current session is a member: where its lifecycle events and its
  statements go, whatever log the thread was found through.
- **The roster** of a channel is the read of §5: the rows, each from its
  thread's own project's view, of the threads whose log states the channel.
- **A mark** is a writer's settled position in a delivery record
  (`projects/<log>/delivered/<session>.json`, T1's and T2's file) raised to
  what the log held at one moment, so that nothing up to it is owed (§4).
- **Opens without `follow`** is said of a channel's log on a machine whose
  hello for it carries no `follow` key: MAWS counts that machine as a holder.
  `Link.holds` keeps today's meaning, everything a held project is sent
  (the machine's presence, its checkouts, its sessions' presence), and is
  never true of a channel (§7).
- **The endpoint's word** is its answer to a `reach?` frame: `deliver`,
  `refuse`, or none while it holds no record of the session asked about.
- **The stand-in** is `sminos/tests/endpoint_standin.py`, the scripted
  endpoint the suites run a real sminos against; two or three machines in a
  suite are two or three sminos homes, each with its daemon and its stand-in,
  joined by `sminos/tests/rl10-machines.sh`.
- **`S/`** is `sminos/skills/sminos/scripts/`, **`T/`** is `sminos/tests/`.

## Constraints that bind every milestone

- **The designs have one writer,** the session that holds the composite. This
  document's controller records decisions and discoveries here and sends that
  session whatever touches the child's purpose, its acceptance, a contract or
  a binding decision; it edits neither design. A statement of the composite
  that the code makes unbuildable stops that part and goes to the holder with
  the evidence; the rest is built.
- **What binds, by id.** The composite's C1 (two readings of "its members"),
  C2 (the kinds and their fields), C3's "Who may ask", C4 (the wire) and, of
  C5, only that nothing is said into a channel yet. The parent's D3 (The id,
  Membership, "A channel exists while"), D6 and D7, and the rulings under
  "What it must not become". Contracts X1 (a field and an operation are added
  only through `S/sminos_threads.py`), X2 (a request names its target's
  thread), X4, X5, X7, and Y1, Y2 and Y3, whose names Interfaces fixes.
- **Nothing is published under a channel id.** No `member` frame names a
  channel as `project`; no session presence, machine presence or checkout,
  no `pending` set and no host frame is sent under one; no `joined`, `state`,
  `renamed`, `titled`, `in-charge`, `status`, `unlisted`, `channels`,
  `message`, `question` or `answered` is written into a channel's log. What
  a channel's log holds from this code is a `channel-request`, a
  `channel-env`, and the `retired` that undoes a `joined` an older copy wrote
  there. `T/channel_wire.py` (§9) is the check, and every suite of this child
  that runs an uplink ends by calling it.
- **A channel's view has no members, and the roster is a read of its own**
  (C1). `view_of` of a channel answers no member, by construction and
  whatever its log holds. No path that exists today (delivery, tag
  resolution, `@all`, `find_target`, the plane, the uplink's publishers, the
  guide) is given the roster in this child: its readers are `list`,
  `channel show`, `channel env` and the pool, and nothing else.
- **A fact about a thread is written to the thread's own project.** No verb
  and no pass writes a lifecycle event, an in-charge line, a status or a
  statement for a thread into a channel's log.
- **One writer of a thread's set.** A record's `channels` and `answered`
  are written by `sminos_threads.set_channels` and by the journal's own
  steps (an absorption's merge), and a `channels` event is appended by
  `sminos_threads.finish` for an entry that owes one. Nothing else writes
  either: `update` refuses both keys, the reconciliation calls
  `set_channels` and never appends a statement itself.
- **What an operation decides, it reads under the record's lock.** The new
  set, whether a request is already answered, whether an earlier one still
  waits, whether the thread's session and reach are the ones a question was
  put for, the limit, and where the statement goes are read in the write
  that makes the change, on a fresh read of the record, never taken from a
  read made before it (Interfaces §3). What was read before the lock chooses
  only whether to try. T1's branch review found most of its 82 defects
  between a check and its write.
- **Lock order,** outermost first, as T2 fixed it and unchanged: the
  delivery lock; the seat's lifecycle lock; the wake lock; a store lock
  (`.metalock`, then `threads/.lock`); a log's lock. A record's finisher
  lock (`threads/.finish/<id>.lock`) is held by `finish` for its whole run,
  outside the store and log locks it takes. The one place a delivery lock
  is taken under a finisher lock is the journal's settlement, with a bounded
  wait (T1); the marks are that same step and add no other. The membership
  operation takes no wake lock and no lifecycle lock, and holds no store
  lock while it takes any other lock: what it reads under the store lock
  (other records, a session's record, log files) it reads without a lock.
  Interfaces §3 names the lock of each writer this child adds.
- **Nothing is said into a channel.** Every form that would write a `say`
  or a `human` event into a channel's log is refused before anything is
  appended, from a session and from a terminal, in §8's words. This child is
  released ahead of CH2 (the owner's ruling), so the refusal is what a user
  meets: it says that speaking in a channel is not available in this version
  yet and names the plain tag that works today.
- **Three kinds, and no other.** `channels`, `channel-request` and
  `channel-env`, with exactly §2's fields. `channel-lead` is CH2's. None
  names anyone in `to`. MAWS gives a meaning to `say`, `human`, `message`,
  `question`, `answered`, `joined`, `retired`, `renamed`, `titled`, `state`,
  `status`, `in-charge`, `unlisted` and `void`: no new kind takes one of
  those names. A `session` on an event that is not its writer's own session
  is, to the hub and the endpoint, a session being addressed: only a request
  carries one, and a statement never does.
- **Older code on the same machine** keeps D7's rules. The new kinds are
  inert to every installed copy (no `to`; every copy's `_projection` skips a
  kind it does not know), the record's new key is one older code leaves in
  place, and nothing here defends against an older CLI run by hand beyond
  what M7 asserts.
- **Accepted, and not built** (the composite's second review; no milestone
  tries to close them): a sender removed from the org between a request's
  import and the endpoint's answer is honoured; an absorption that an older
  copy finishes drops what the provisional record had gained; a narrowing
  whose withdrawn audience could not be named leaves the old row standing in
  a roster as in the project's view; requests of two machines whose clocks
  disagree are carried out in the stamped order, and a request stamped more
  than seven days behind is never carried out; two adds contending for a
  thread's last place under the limit are not ordered.
- **What sessions are taught does not change.** The session-start guide,
  `sminos/skills/sminos/SKILL.md`, the spawn preamble and the manager's
  skill say nothing of channels until CH2, and the tests that pin their
  lines verbatim pass untouched. `sminos help` lists the new verbs, and the
  backtick guard knows `channel`.
- **`S/sminos.py` is one file of nineteen thousand lines.** What reads and
  decides for channels (finding one, the roster, requests and their
  carrying out, the pool, the `channel` verbs) goes in a new sibling module,
  `S/sminos_channels.py`, loaded as the CLI's other sibling modules are
  (`sibling_module("sminos_channels")`); `S/sminos.py` gets the predicate
  and the changed seams, `S/sminos_threads.py` the record's operation.
  `origin/main` is merged before M1 and before the final push.
- **The idle daemon stays cheap.** On a machine that knows no channel every
  per-tick and per-scan duty this child adds is a loop over nothing. With
  channels, what a tick or a scan reads is cached by the files it read (the
  merged log's memo, the stores' stat key, the cache generation); no tick
  reads a roster, and none reads every project's log for a channel. The
  `sminos-idle` gate is the check.
- **Byte for byte for a session in no channel.** `say`, `list`, `list
  --json`, `chat`, `spawn`, `join`, `retire`, every event and every frame of
  the uplink are what they were for a machine that knows no channel and a
  thread that is in none, with one exception: the hello's capability list
  gains `channels` (M5). A key or a line this child adds appears only where
  a channel does.
- **What sits beside the code is written with it.** Each milestone adds
  what it built to `sminos/skills/sminos/scripts/CLAUDE.md` (the new
  module, the rules of this section that a later change could break, the
  tests' names), since the next milestone's executor reads that file before
  it reads this one's code; M7 reads the whole against the tree.
- **Tests are hermetic,** as in T1 and T2: the test engine, the stand-in,
  temporary `HOME` and `SMINOS_HOME`, invented names. The repository is
  public: no hostname, account, project id or local path enters a test, a
  comment or this document.
- **Tests vary what a single case hides:** both kinds of thread (spawned
  and human-opened) as target, live and stopped; one, two and five requests;
  one and two requesters; the three callers of the carrying out (the
  command, the daemon's tick, the uplink at an answer) and the order of
  their answers; a request before and after a continuation, a refill, a
  `join`, a change of reach, an end and a return. A guarantee tested with
  one request to one live human-opened thread is not tested.
- **One change, one version.** No release is cut between milestones. The
  child merges as one pull request that leaves the repository releasable
  beside a machine on 1.52.0 (D7), with sminos's version bumped in it
  (`scripts/bump-version.sh --plugin sminos`, to 1.53.0 unless `main` has
  moved past it). No other plugin's files change.
- **Every milestone ends green.** The gates of Concrete Steps pass at each
  milestone's last commit. A test that pinned behaviour a milestone changes
  is changed in that milestone, to pin the new behaviour and never deleted
  for failing; a consumer of a function whose meaning a milestone changes
  is changed in the same milestone.

## Plan of Work

Readers and refusals come first, writers after them, and the wire last. M1
makes a channel id a channel to every lookup and closes every path that
would publish under one, before anything in the tree can create a channel.
M2 builds the one operation that writes a thread's set, with its statement,
its marks and the reconciliation that keeps the log equal to the record,
driven from tests alone. M3 adds requests and the verbs that write them, on
one machine. M4 builds the roster and everything that prints it. M5 turns the
wire on: the capability, the member frame's `channels`, MAWS's fixture. M6
carries requests between machines, on the endpoint's word. Between M6 and M7
the range is reviewed whole by the composite's holder. M7 runs older copies
against the result, writes what sits beside the code, bumps the version and
runs the acceptance.

Until M5 no real endpoint lists `channels` in its welcome (MAWS echoes the
capability only to a hello that listed it), so `channel create` and
`channel add` are refused on every real machine while M1 to M4 land; their
tests stage the kept capability or run against the stand-in.

**The frontier review.** When M6's review is clean the controller pushes the
branch and returns to the composite's holder with the word `FRONTIER`, the
range (`git merge-base origin/main HEAD` to `HEAD`) and nothing else to
decide. The holder reviews that range through doperpowers:review-code at the
panel rung, with lenses given, not derived: lock order, and what is read
outside the lock it is acted on under; an older copy on the same store;
what leaves the machine (every frame and every event under a channel id,
and whether anything names a private requester's session to a reader of its
target); and the milestones' interactions (a request against an end, a
return, a hand-off, an absorption, a `join`, a change of reach and the
thread sweep; the reconciliation against each of them; the marks against a
delivery pass). Its confirmed findings are fixed on the branch by the
holder's fix wave, the range is read whole a second time if the first
reading confirms more than ten, and there are three rounds at most. The
controller is then continued for M7. It sits after M6 because every writer
and every sender this child adds exists by then and M7 adds none; T2's
review of its first four milestones as one range confirmed 62 findings over
three rounds, five of them a lost message or a wrong recipient, after each
milestone had been reviewed clean.

### M1 — A channel id is told from a project's at every door, and nothing is published under one

**At its end:** an id that passes `is_channel_id`, however it reached this
machine (the org's directory, a `.smns`, a join override an older copy
wrote, an argument), is a channel to every lookup. `sminos projects` and
`sminos list` show no channel as a project; `sminos join <channel>` is
refused and names `sminos channel add`; a `.smns` that names one files its
directory in the machine's project and says why; `say --in <channel>`, a tag
qualified by a channel, a selector naming one, and a verb's target qualified
by one are refused in §8's words with nothing appended; a name that several
logs answer is refused by one function, listing each with its kind and
`name#short`. The channel's log is opened at the hub and kept; a `joined` an
older copy wrote into it is retired `moved`; and nothing of the constraint
"Nothing is published under a channel id" is sent or written. No verb
creates a channel yet: the tests register one as the org's directory does.

**Touches:** `S/sminos.py` (the predicate beside `UUID_RE`; `project_kind`;
`known_projects`, new `known_channels` and `known_logs`; `_name_tiers`,
`project_tiers`, `find_project` and the one refusal; `join_refusal`,
`cmd_join`; `_smns_decision`; `view_of`; `lifecycle`; `append_host`;
`cmd_say`, `say_scope`, `_resolve_tag`, `find_target`; `cmd_projects`),
`S/sminos_channels.py` (new: `find_channel`, `register`, `held_channels`,
`opens_unfollowed`), `S/sminos_uplink.py` (`hub_projects`, `Here.project`,
`Link.holds`, new `Link.unfollowed`, `open`, `machine_presence`,
`host_pass`, `relay_requests`, `members`, `tick_passes`, `may_leave`),
`S/sminos_plane.py` (`Plane.refresh`), `S/sminos_daemon.py` (`tick_all`, and
the channel pass of §6 with its reconciling half alone),
`T/test_channels.py` (new), `T/test-channels.sh` (new), `T/channel_wire.py`
and `T/test_channels_wire.py` (new), `T/run-sminos-tests.sh` (a third part,
`channels`), `.github/ci-kit.yml` (the gate `sminos-channels`).

**Interfaces:** exposes §1, §7's `unfollowed` and `holds`, §8's refusals,
§9's checker. Consumes T1's `sminos_threads.all_threads` and
`record_ended` (for `held_channels`, which reads records and finds none
naming a channel until M2 writes one).

**Decisions:**

- Every caller of `known_projects`, `project_kind`, `find_project`,
  `project_tiers`, `org_scope`, `hub_projects` and of an org entry's `kind`
  is read and put in one of three classes, the list kept in the milestone's
  report. It lists or looks up projects for a person or a session: it gets
  no channel, because `known_projects` returns none (§1). It opens,
  reconciles or leaves logs: it asks `known_logs` (found while planning:
  `hub_projects`, the uplink's `member_known`, which the leaving rule's
  come-back reads, and the daemon's tick). It resolves a name: it goes
  through §1's resolver. Found while planning to need a change of their
  own: `cmd_projects` (its tier order raises on a fourth kind), `_name_tiers`
  (a channel matches none of its three tiers), `Here.project` (an RPC that
  names a channel as its project is answered as one naming no project
  here). `streams_here` keeps answering yes for a channel, which the hub
  syncs: a request for a private thread goes under a stream (M3).
- `view_of` of a channel reconciles its log and returns no member and no
  seat row, whatever the log holds. `Plane.refresh` of a channel leaves
  every map of it empty (`here`, `member_rows`, `members`, `left`):
  otherwise, once an older copy's `joined` there is retired, the plane's
  forced presence says that session "not running" under the channel id.
- `lifecycle` appends nothing but a `retired` into a channel's log, whoever
  asks (the rule beside its refusal of a `joined` into a guessed project),
  and `append_host` raises on a channel: two guards behind the two that
  make the case unreachable (`join_refusal`, the `.smns` rule).
- `join_refusal` answers for a channel first, before it reads the
  enrollment, so `session_project` reads an override that names a channel
  as absent on any machine and the session's next reconciliation moves it
  back (`retire_moved`), as for any ineligible override.
- The `.smns` rule sits in `_smns_decision`, the one place a `.smns`
  becomes a decision: for a channel id the decision is the machine's
  project (`own_machine_project`; on a machine not enrolled, what
  `_last_rungs` gives), with one warning on standard error naming the file.
  `decision` stays pinned to MAWS's `project-rule.json`
  (`T/project_rule_parity.py`), whose cases hold no version-8 id; the test
  of this rule is sminos's own, beside that pin, and says so.
- `Link.unfollowed(pid)` decides the hello's `follow` for every log:
  `holds(pid)` for a project, `opens_unfollowed(pid)` for a channel. `holds`
  answers false for a channel and keeps deciding everything else a held
  project is sent. For a channel `open` sends its `hello`, the rejections
  not yet reported and the RPC results owed, and nothing else: no `machine`
  frame, no session presence, no `pending` set (`Requests.opening` is not
  asked), and `rejoin_former` is not run; `machine_presence` sends it a new
  `hello` when `unfollowed` flips and never a `machine` frame; `host_pass`
  passes it by; `Plane.tick` and `relay_requests` are given the open
  projects without the channels. Uploads, delivery outcomes and notices run
  for it as for any log. `may_leave` reads `unfollowed`.
- The daemon ticks no channel as a project: for each channel known here the
  channel pass reads its view (the reconciliation, and nothing published),
  and none of `rejoin_former`, `publish_state`, `publish_titles`,
  `restate_withheld`, `publish_renames`, `deliver_owed`, the mirror sync or
  the archive duty runs for it.
- `chat <channel>` and `list <channel>` are refused by `find_project`'s
  line for a channel (§8): reading a channel's log as a conversation is
  CH2's, with speaking in it.
- The new suites are a third part of `T/run-sminos-tests.sh`
  (`SMINOS_PART=channels`) with a gate of their own, so the two existing
  gates run what they ran (A13 is read off them unchanged) and neither is
  pushed toward its timeout.

**Does not touch:** the thread record, any event kind, `LIFECYCLE`, the
capability list, `member_frame`, `cmd_list`'s output, the guide, the skill.

**Proves:** A8 (the `join` and `.smns` halves), A10, A11 (no channel is
ever the project a verb's target is found in), A12's test of its own, for a
channel that holds no member yet. Its tests pin: `is_channel_id` on every
entry of the shared vectors' `ids`; the kind; each lookup that lists
projects with a channel registered beside them (text and `--json`
unchanged against the same store without it); the one refusal for a name
that a channel and a project share, two channels share, and two projects
share, and `name#short` reaching each; each refusal of §8 with the logs'
files unchanged; the `.smns` rule and the parity suite still passing; an
override naming a channel read as absent and the session moved back with a
`retired` `moved` in the channel's log and no `joined`; and, through the
checker over a real uplink against the stand-in, a first connection, a
reconnection, a channel this machine's records name (staged by writing a
record's `channels` in the test) and one they do not, and a store in which
an older copy's `join` wrote a `joined` under the channel.

### M2 — A thread's declared set: one operation, its statement, its marks, and the log kept equal to the record

**At its end:** `sminos_threads.set_channels` is the one way a record's
`channels` and `answered` change (§3). Its entry is carried by `finish`:
the marks, then the statement, appended through `lifecycle` in the thread's
own project. An end and a return mark every channel of the set; an
absorption gives the continuing thread the absorbed record's channels and
answered requests. Every reader takes a session's membership from the log
by C2's rule (`Fold.state`, the projection's row, `Member.channels`), and
`_reconcile` notices a thread of this machine whose log states otherwise
than its record and has the operation state the set. There is no verb yet:
`sminos_channels.change` (a thread's own add or remove) and the
reconciliation drive it from tests.

**Touches:** `S/sminos_threads.py` (`OPS`, `JOURNALED`, `SEAT_KEYS`,
`set_channels`, `update`, `begin`, `finish`, `Fold`, `stated_set`),
`S/sminos.py` (`LIFECYCLE`, `_projection`, `Member`, `_member`,
`_reconcile`'s last step, `finish_thread`, new `channel_marks` and
`mark_channels`), `S/sminos_channels.py` (`change`, `restate`,
`channels_of`, `Outcome`), `T/test_channels_store.py` (new), and the two
tests of T1 that pin today's form (`T/test_threads_ended.py`, which calls
`set_channels` with a list; `T/test_threads.py`, which expects `update` to
answer false for `channels` on a held record, where it now raises).

**Interfaces:** exposes §2 (the statement), §3, §4, §5's fold and
`Member.channels`. Consumes T1's journal (`_change`, `_apply`, `finish`'s
steps, `open_entries`) and §1.

**Decisions:**

- The operation is `channels` in `OPS`. It opens without the wake lock and
  does not move a seat's lifecycle generation, as a release does not: a
  membership ends no thread and changes no occupant, which are what the
  wake lock and the generation guard, and a wake in flight must not turn a
  local add into a third kind of wait (A1 names two). Its linearization
  point is the record's write under its store lock.
- `set_channels(thread_id, decide)` runs `decide` on a fresh read of the
  record under that lock, only when the record has no open entry, and
  writes what it returns in one write (§3). Everything a caller knew before
  the lock reaches `decide` as what to compare against, never as what to
  write.
- `channels` joins `LIFECYCLE`, which invalidates the project's view at an
  append and at an import. `_projection` needs a branch of its own for it:
  as the code stands a `LIFECYCLE` kind it does not name falls into the
  last branch and is appended to the row's `status`.
- The reconciliation is the last step of `_reconcile`, after its own
  appends, so that a `joined` this pass wrote is followed by its statement
  in the same pass. It compares, for each thread of this machine that has
  not ended and has no open entry, whose current session's membership in
  effect in this log is a `joined` of this machine, what the log states (a
  memo beside the merged log, with this pass's appends folded in) with the
  record's set, and on a difference calls `restate` (§3, row C5) with what
  it read. It appends nothing itself. A failure (a busy lock, a stream that
  cannot be chosen) is warned of and left to the next pass, as its other
  appends are.
- Where a statement goes is the project in whose log the thread's current
  session is a member at the write, checked under the lock from that
  session's own events there. A thread with no session (a vacant spawned
  thread) or whose session is a member of no project at that moment (between
  the two halves of a move) is not written: its caller is told `pending`.
- The marks of an end and a return are computed by `begin` for those two
  operations, for every channel of the set, so that every path that ends or
  returns a thread (a retire, the rule, a purge, a lane B end, an older
  copy's retire taken as an end) leaves them without a change of its own.
- The absorption's merge is a write of its own in `finish`, after the
  absorbed record is reserved (nothing writes a reserved record) and before
  the events: the continuing record's set, then the absorbed record's
  channels not in it, up to the limit, an addition past it dropped and said
  in `daemon.log`; `answered` united; the marks of the channels added. The
  statement follows from the reconciliation, since the entry's `joined`
  leaves the log stating nothing.

**Does not touch:** requests, any verb, the uplink, `cmd_list`.

**Proves:** A6 but for the roster's own rows (M4), A9 for an own add and
removal, an end and a return, and the absorption's half of A8's limit. Its
tests pin: the fold on hand-written logs (a statement before its writer's
`joined`, under another writer than the `joined`'s, after a `retired`, two
statements, one with an empty list, ids that are no channel's, a 129th id);
each row of §3's table from `set_channels`, with a `decide` that is given a
record changed between its caller's read and the lock; a process killed
between the record's write and the statement, and between the marks and
the statement, finished by the next reconciliation with one statement;
`update` refusing both keys; the reconciliation after a continuation, a
refill, a `join`, a `join` back to a project left with another set, a
change of reach and back, a `joined` an older copy wrote, a return, and a
`/clear` (the thread left keeps its set, the new one states none); the
reconciliation paused between its read and its call while the thread is
removed from the channel, and while it moves to another project, stating
nothing in either case; the marks after each of the four transitions, with
the channel's log already holding events addressed to the thread's
sessions; the absorption with a set on both sides, at the limit, and its
replay.

### M3 — Requests on one machine, and the verbs that write them

**At its end:** `sminos channel create <name> [<thread>]`, `sminos channel
add <channel> [<thread>...]` and `sminos channel remove <channel>
[<thread>...]` work on one machine whose endpoint lists `channels`. A
thread adds and removes itself with a statement alone. Another thread of
the machine is named by a request the command writes into the channel's log
and then carries out itself; a request left by a command that died is
carried out by the daemon's tick. Each target is told applied, refused with
its reason, or pending and why. What is refused before anything is written
is refused (§8), and the limit binds every path.

**Touches:** `S/sminos_channels.py` (the requests of a log, `carry_out`,
`carry_due`, `sender_verified`, `reach_token`, the three verbs),
`S/sminos.py` (`build_parser`, `main`'s usage line for the family),
`S/sminos_daemon.py` (the channel pass calls `carry_due`),
`T/test_channels_requests.py` (new), `T/test-channels.sh`.

**Interfaces:** exposes §2 (the request), §6, §8's three verbs. Consumes
§3's `set_channels`, §5's `channels_of`, `stream_choice`,
`same_owner_local`, `owners_meet`, `policy.read_only`,
`policy.outside_origin`, `audience.advertised`.

**Decisions:**

- One function carries out a request, `carry_out`, and one pass calls it,
  `carry_due`, in the order the channel's log is read; the command, the
  daemon's tick and (M6) the uplink at an answer all call the pass. A
  command that finds an earlier request for the same thread and channel
  unanswered carries that one out first when it can, and reports its own
  as pending behind it when it cannot.
- `carry_out` takes the endpoint's word as an argument (§6). This milestone
  proves the whole decision table by handing it each word over hand-written
  requests, some carrying an import's `verified` key; M6 builds the path
  that asks.
- A request for a private thread is written under the stream
  `stream_choice` gives for that one recipient; a choice that refuses is
  the command's "refused: not reachable" for that target, with nothing
  written for it. One event per target, each with an id of its own.
- A person at a terminal has no thread: `channel create` there names a
  thread of this machine, and `channel add` and `channel remove` there name
  their threads. The request is written under the machine's human writer
  and honoured when the machine's owners meet the thread's
  (`owners_meet("", session)`): `same_owner_local` answers only for a
  session's writer.
- `channel create` refuses, before anything is written, a name a log known
  on this machine already answers to, naming it. It mints the id, registers
  the channel, and places the first member by the same paths as `add`. An
  id the machine already knows is minted again.
- A request that names no thread of this machine as §6's first rows read it
  (not this machine's, ended, a session it never had, a session that is now
  another thread's, lane B) gets no statement here and expires: a statement
  is written under a thread's writer, and no thread here is the one named.

**Does not touch:** the uplink, the capability list, `cmd_list`,
`channel show`, `channel env`.

**Proves:** A1; A4's cases at the function (the same owner on one machine;
a verified sender with each word; an unverified sender; no word yet; an
endpoint without `channels`); A5 but the last clause (M6); A8's capability
and limit halves; A9 for a request's add and removal. Its tests pin every
row of §6's table; an add then a remove of one thread in one channel, and
the reverse, with each carried by the command or by the tick and the words
handed over in either order; two requests in two channels answered once
each by the statement naming its channel and id; a request read twice, and
again after the thread changed session, project and reach, and after its
record was absorbed; a request behind an open entry; five requests for one
thread from two requesters; the limit at `create`, at `add` for oneself, at
`add` for another (a refusing statement), and with two adds for the 128th
place; each refusal before writing, with every log unchanged; a request
whose `session` is another thread's current one changing neither; and no
session's turn started by any of it.

### M4 — The roster, the listing and the pool

**At its end:** `sminos list` run by a thread that is in channels prints
its project as before and then each of its channels under `# <name>` with
the roster, stopped members shown; `--channel <name>` prints that channel's
section for any caller; `sminos list --org` ends with a section for each
channel that has a member and none for one whose last member left;
`list --json` keeps one row per session, a row in channels carrying
`channels`. `sminos channel show <channel> [--json]` prints the roster, the
requests of the last seven days with what became of each, and the pool;
`sminos channel env add|remove <channel> <machine>` changes the pool it
prints. `sminos help` lists the `channel` verbs, and the backtick guard
knows the family.

**Touches:** `S/sminos_channels.py` (`rosters`, `roster`, the requests as
shown, `pool`, `show`, `env`), `S/sminos.py` (`cmd_list`, `list_scope`, the
parser's `--channel`, `member_json`, the module docstring that is `help`),
`sminos/hooks/mods/backticks.tsx` (`VERBS`), `T/mods/backticks.test.ts`,
`T/test-channels.sh`, `T/test_channels.py`.

**Interfaces:** exposes §5's roster (Y1), §8's listing. Consumes §2, §5's
`Member.channels`, §6's reading of requests.

**Decisions:**

- The sections of a bare `list` are the caller's own set (`channels_of`),
  so a thread in no channel reads no other project's log and prints what it
  printed. The project's `+N hidden` line stays directly under the
  project's rows; channel sections follow it, each row with its project's
  column as the several-project table prints one.
- `--channel` is a row filter like the others: it widens to every project
  known here and keeps the rows whose `channels` hold that channel; in text
  it prints them under the channel's heading, in `--json` as the flat list.
- A row's `channels` key is present in `list --json` only when the row is
  in a channel, as the wire sends no key for a thread in none: the output
  for a store without channels is byte for byte what it was.
- A request older than seven days by its own timestamp is not shown,
  answered or not. What became of a newer one is read from the statement
  that names its channel and id in any project's log this machine reads,
  else from a position of this machine's the hub withheld (M6 adds that
  reader), else it is pending, with the machine the target's row was last
  seen on and the request's age.
- `channel env` is refused from a terminal and from a thread that is not in
  the channel, before anything is written: no reader would honour the
  event. The machine named must be one the org's directory lists.
- A `channel-env` event is honoured when its writer's session is, or was,
  a session of a thread in the roster as it is read; the last by merge
  order holds for each machine.

**Does not touch:** delivery, tags, `find_target` (no path is given the
roster), the guide, the skill, `sminos projects` (which lists no channel).

**Proves:** A2; A6's roster clauses (a thread that goes private leaves the
roster of a reader that may no longer read it; an ended thread leaves it
and is back in it when reopened); A7's `list --org` clause on one machine;
A13 for the listing (the outputs of `list`, `list --org`, `list --json`,
`list --stopped` and `list --all` over a store with no channel, compared
with the merge base's). Its tests pin: each section and its order; a
stopped and a `gone` member shown in a roster and folded in the project's
section; two members of one alias labelled apart; `--channel` with
`--machine`, `--state` and words; `channel show` with a roster spanning two
projects and each state of a request; the pool's counts, a machine added
and removed by hand, an env event from a writer no longer in the roster
ignored; the guard refusing a `sminos channel …` call that holds a live
backtick.

### M5 — The wire: the capability, `member.channels`, opening without `follow`, MAWS's fixture

**At its end:** sminos advertises `channels` in its hello and, when the
welcome lists it, sends a lane A thread's set as `channels` on its `member`
frame, with no key for a thread in none. A machine whose records name a
channel opens its log without `follow`. The conformance replay passes on
MAWS's fixture as its master holds it at `8ae3b0843`, copied byte for byte,
with no amendment left in the harness. Across three machines the stand-in's
`known` lists a channel for the two that hold members and not for the
third, follows a removal and a return, and is empty when the last member
leaves.

**Touches:** `S/sminos_rl10.py` (`CAPABILITIES`), `S/sminos_uplink.py`
(`welcomed_rl10`, `member_frame`, `fresh_frame`),
`T/rl10-conversation.json` and `T/rl10-conversation.source.json`,
`T/rl10_conformance.py`, `T/test_rl10.py`, `T/endpoint_standin.py` and
`T/test_endpoint_standin.py`, `T/rl10-machines.sh`,
`T/test_channels_wire.py`, `T/test-channels-machines.sh` (new).

**Interfaces:** exposes §7. Consumes §3 (to place the replay's session),
§5's `held_channels` and `channels_of`, §9.

**Decisions:**

- The copy, the advertisement and the frame's key are one change: hellos
  are matched whole, so the capability fails the old fixture and the new
  fixture fails without it, and its case 13 fails without the key.
- The fixture is taken from a checkout of MAWS at `8ae3b0843`, path
  `test/endpoint/rl10/conversation.json`, whose git blob is
  `ad878efbccfa04e6ffdfcfd4b3ca93a783cc8da2`; the copy's `git hash-object`
  equals it, and `T/rl10-conversation.source.json` names that commit and
  blob. The holder names the checkout to read; nothing is written there.
- What the copy retires in `T/rl10_conformance.py`: the three `AMENDMENTS`
  and what only they use (`S2_WRITER`, `S4_WRITER`, `STAMPED`,
  `amend_threads_upload`, the docstring's paragraph), and
  `check_restated`'s clause for S4's frame, which the fixture's new step 12
  of case 11 states. That step moves every later step of case 11 down by
  one, so every table keyed `(11, n)` with n of 12 or more moves with it
  (`CHECK`, `late_checks`, `PROBES`, the step `run_deferred` reads). Case 13
  is staged by registering the channel under the fixture's own id and name
  and placing S1 by `sminos_channels.change`, which writes nothing into the
  channel's log (the hello's `have` is `{}`), then removing it.
- **If a line of the replay then differs from what sminos sends,** in a
  field and not in a missing stage, no amendment is written: the exact line
  as the fixture has it and as sminos sent it goes to the holder, who takes
  it to MAWS's architect, and the milestone waits on that one answer with
  everything else built.
- The frame's `channels` is the record's set as `channels_of` reads it, its
  entries that pass `is_channel_id`, at most the first 128, and only for a
  lane A member while the welcome listed `channels`. `fresh_frame`'s key
  takes that tuple and the welcome's word.
- The stand-in gains MAWS's rule for `known`, read from the frames it
  already keeps (§9), and lists `channels` in its welcome only to a hello
  that listed it. The org's directory the machines of a suite are given is
  built from the stand-ins' `known`, so a machine follows a channel in a
  suite for the reason it would on the fleet.

**Does not touch:** `ask_words`, `on_reach`, requests, `cmd_list`.

**Proves:** A12 (the replay; the frame with the key only under the
capability and never as an empty list; the test of its own, now over
members in channels, on a first connection, a reconnection and a store an
older copy wrote into); A7's wire clauses. Its tests pin: the hello's
capabilities; a frame rebuilt when the set changes and only then; no key
for lane B, for an ended thread, without the welcome's word; a channel's
hello gaining and losing `follow` as the last record naming it goes and
returns, with no `machine` frame either way; the stand-in's `known` against
MAWS's rule on hand-fed frames; and the three-machine case.

### M6 — Requests across machines: the endpoint's word, and what a requester is told

**At its end:** a request written on one machine for a thread of another
is uploaded, reaches the target's machine, and is carried out there when
the endpoint answers `deliver` for a verified sender, with no turn of any
session. The requester's `channel show` reads applied, refused with its
reason, refused as not reachable when the hub withheld the request, or
pending with the target's machine and since when; after seven days it reads
nothing, and a request that arrives that old is not carried out.

**Touches:** `S/sminos_uplink.py` (the request source of the ask pass,
`on_reach`, the asks held), `S/sminos_channels.py` (`ask_of`, the
binding of an answer, the withheld reading), `S/sminos_hublog.py` (a read
of a project's withheld positions for the CLI),
`T/test_channels_wire.py`, `T/test-channels-machines.sh`.

**Interfaces:** exposes §6's `ask_of` and the answer's path. Consumes
§6's `carry_due`, `Link.members_before`, the uplink's `asks`.

**Decisions:**

- The question is `reach? {id, project: <the channel>, session: <the
  thread's current session>, event: <the request, without verified>}`,
  sent where the words pass sends its own, after the tick's upload pass. It
  needs both `reach` and `channels` in the welcome. The thread's member
  frame goes first under the thread's own project: `members_before` asked
  with the channel finds no row there and answers that nothing is due.
- A request's ask does not go through the hold filter the message asks go
  through (`queue_asks` drops an ask whose recipient this machine holds): a
  stopped thread is asked about and placed while it stays stopped.
- The ask pass is itself a caller of `carry_due`, and asks about each
  request that pass left pending `endpoint` (`ask_of`), one ask out at a
  time for a request. An ask is held under a key of its own (the channel,
  the thread, the request's id), with what it was put for: the session and
  its reach (`reach_token`). `on_reach` hands an answer for such an ask to
  `carry_due` with that binding; the operation uses it only if, under the
  lock, the thread's current session and reach are still those, and
  otherwise the request is asked about again at the next pass. An answer
  past `REACH_WAIT` is none, and the request is asked again, with no count
  and no bound.
- An import of a channel's log nudges the daemon and marks the ask pass
  due, as an import does today, so a request is carried out within a tick
  of its arrival.
- The requester's machine reads "the hub withheld it" from the withheld
  positions its uplink keeps for the channel's log (`uplink.json`), by a
  read that takes no lock and changes nothing.

**Does not touch:** `deliver_reach` and the message asks (their keys,
their hold filter, their counts stay), the fixture, `cmd_list`.

**Proves:** A3; A4 on the path (a verified sender the endpoint delivers
for; a sender it refuses; an unverified sender it would deliver words for,
refused by sminos; no answer, pending; an endpoint without `channels`,
pending); A5's last clause; A1's "placed on another machine when its daemon
runs". Its tests pin: one ask per due request and none for one that needs
no word; an answer used once; the answer after the thread's hand-off, and
after a change of its reach, leading to a second ask; two requests for one
thread and channel asked one at a time in order; a stopped thread placed
with no launch recorded by the test engine; each outcome at the requester
on two machines, the withheld one staged by the stand-in refusing the
upload `not-reachable`; an expired request relayed late; the roster on both
machines; and the checker over both stand-ins.

### M7 — Older copies, what is written beside the code, the version, and the acceptance

**At its end:** `T/test-older-cli.sh` runs 1.27.10, 1.51.0 and 1.52.0
beside this code over a store that holds statements, a thread in channels
and a registered channel; `S/CLAUDE.md`, which each milestone added to,
has been read whole against the tree;
`docs/doperpowers/TECH-DEBT.md` holds what this child accepts;
sminos is 1.53.0; and the acceptance has been run as Concrete Steps gives
it, the narrow check on a real engine included.

**Touches:** `T/test-older-cli.sh`, `sminos/skills/sminos/scripts/CLAUDE.md`,
`sminos/CLAUDE.md` (one sentence naming the channel family and where its
detail is), `docs/doperpowers/TECH-DEBT.md`, the files
`scripts/bump-version.sh --plugin sminos` writes.

**Interfaces:** consumes everything; exposes nothing new.

**Decisions:**

- The older-copy suite's machines are not enrolled, so `channel create` is
  refused on them: the store is staged through this code's own functions
  (`sminos_channels.register`, `change`), and each older copy then runs its
  verbs over it. 1.52.0 is pinned as the merge that released it
  (`f051d4f2a28615d7b3517963aed0ac68233435fb`), fetched as the other two
  are.
- Per version, asserted: each copy's `list`, `list --json`, a tagged `say`
  and a `send` to the thread in channels, and its `daemon tick`, do what
  they did over the same store without channels (the every-copy
  expectations and each version's own, unchanged); the record's `channels`
  and `answered` are what they were after each; a `joined` the copy writes
  for the session is followed, at this code's next reconciliation, by a
  statement of the same set; the copy lists the registered channel as a
  project with no member and this code still lists it as none. Then, for
  each copy: its `join <channel id>` by hand, after which this code's next
  reconciliation leaves the session a member of its one project with its
  set as it was, a `retired` `moved` in the channel's log, and the checker
  clean over an uplink run on that store.
- TECH-DEBT rows, each with what would promote it: the composite's
  accepted list (the constraint above); a wake that launches while a
  membership entry is open loses its own record writes for that attempt
  (the same shape as the row for a delayed release); a mark reports no
  delivery outcome for an event it buries; `chat <channel>` and a target
  qualified by a channel are refused until CH2; a session an older copy
  joined into a channel that stops before this code's next reconciliation
  is retired from the channel only once it runs again (`retire_moved` acts
  on a session a process or a seat holds), and until then is listed in
  neither.
- **A check on a real engine, narrow, and here.** The engine is in this
  child's path only where T1 already put it: a `/clear`, a hand-off to a
  background job and its absorption, whose order of hooks T1 and T2 each
  found different on a real engine from what their suites staged. Concrete
  Steps gives three steps under a scratch home. CH2 holds the full pass on
  a real engine (the composite's Risks); this one costs minutes and reads
  the two transitions this child adds to. If the executor's environment has
  no engine credentials it is reported as not run, never as passed.

**Does not touch:** the guide, the skill, the spawn preamble, the manager's
skill, `docs/whats-inside.md` (no skill, agent or hook is added).

**Proves:** A14; A13 whole (the gates on the final head, compared with the
merge base); every item by the proof map, on the final head.

## Concrete Steps

Every command runs from the repository's root in the child's worktree
(branch `sminos-channels-ch`).

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_channels.py
    python3 -B sminos/tests/test_channels_store.py
    python3 -B sminos/tests/test_channels_requests.py
    python3 -B sminos/tests/test_channels_wire.py
    bash sminos/tests/test-channels.sh
    bash sminos/tests/test-channels-machines.sh
    bash sminos/tests/test-older-cli.sh
    python3 -B sminos/tests/rl10_conformance.py sminos/skills/sminos/scripts sminos/tests/rl10-conversation.json

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. A shell file ends with its counts of passed and
failed and exits non-zero on any failure. The replay prints one `ok` or
`FAIL` line per line of the conversation it plays; from M5 on it prints no
`amend` line.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites,sminos-channels,sminos-idle,sminos-mods,shell-lint,repo-checks

with `mods-types` from M4 on (the guard mod changes) and `version-bump` in
M7. Expected: one `PASS` line per gate, then `GREEN` and the run's address.
A `FAIL` that the base also shows, or one a recorded reason names, is not
this change's; any other is diagnosed, not run again.

**The proof map.** Where each acceptance item of CH1's section is proved.
A1 to A14 number its items in the order the section lists them.

| Item | Proved in (milestone: file) |
|---|---|
| A1 create, add, remove; with none named, the caller; placed when the command returns but for the two waits; refused before writing | M3: `test-channels.sh` (the verbs), `test_channels_requests.py` (the waits); M6: `test-channels-machines.sh` (another machine) |
| A2 `list`, `--channel`, `channel show`, `channel env` and the pool's counts | M4: `test-channels.sh`, `test_channels.py` |
| A3 across two machines: pending with the machine and since when, carried out by that machine's daemon, the roster on both; each outcome where it can be known | M6: `test-channels-machines.sh` |
| A4 who may ask, case by case | M3: `test_channels_requests.py` (every row of §6); M6: `test_channels_wire.py` and `test-channels-machines.sh` (the path) |
| A5 order and identity | M3: `test_channels_requests.py`; M2: `test_channels_store.py` (the stop between two writes; the absorbed record); M6: `test_channels_wire.py` (asked about again) |
| A6 membership as others read it | M2: `test_channels_store.py` (every reader takes the record's set; the reconciliation overtaken; `/clear`); M4: `test-channels.sh` (private, ended, reopened, in the roster) |
| A7 a remove does not retire; `known` for two holders and a follower; the last member; `list --org`; a return | M5: `test-channels-machines.sh`; M4: `test-channels.sh` (`list --org` on one machine) |
| A8 `join`, `.smns`, the capability, the 129th | M1: `test-channels.sh`, `test_channels.py`; M3: `test-channels.sh`, `test_channels_requests.py`; M2: `test_channels_store.py` (an absorption) |
| A9 the marks | M2: `test_channels_store.py` (own add and removal, end, return); M3: `test_channels_requests.py` (a request's) |
| A10 nothing is said into a channel | M1: `test-channels.sh` (from a session and from a terminal) |
| A11 a verb's fact goes to the thread's own project | M1: `test-channels.sh` (`charge`, `status`, `retire` naming a thread by its short, its id, `alias#short` and a channel-qualified name; M3 runs it again with the thread in a channel) |
| A12 the wire | M5: `rl10_conformance.py`, `test_channels_wire.py`; M1: `test_channels_wire.py` (the checker before any member) |
| A13 parent line 8 for this surface | every gate at every milestone; M4: the listing compared with the merge base's; M5: the frames of a thread in no channel compared with the old fixture's |
| A14 older copies | M7: `test-older-cli.sh` |

**M7, the acceptance.** The gates GREEN on the final head; then the scene,
which M6 builds as the last case of `T/test-channels-machines.sh` and which
is run alone, printing each command with what it printed:

    bash sminos/tests/test-channels-machines.sh --scene --show

Three machines, `alpha`, `beta` and `gamma`, each a sminos home with its
daemon and a stand-in that lists `channels`; on `alpha` a live thread its
human opened, A, and a stopped spawned thread, S; on `beta` a stopped
thread its human opened, B, in another project; on `gamma` no thread. A
"pass" below is one relay between the stand-ins and one `sminos daemon tick`
on each machine. Expected, step by step:

1. A runs `sminos channel create desk-integration`: one line naming the
   channel, its id and A. A runs `sminos channel add desk-integration <S>
   <B>`: S is reported in the channel, B as asked and pending on `beta`.
   The test engine has recorded no launch.
2. After a pass, A's `sminos channel show desk-integration` lists A, S and
   B under members, each with its own project; the request for B as
   applied; and the pool as `alpha` with one live and one stopped, `beta`
   with one stopped. `sminos list` run as A and as B shows the caller's
   project and then `# desk-integration` with the three rows.
3. The stand-ins of `alpha` and `beta` list the channel in `known`;
   `gamma`'s does not. On `gamma`, `sminos list --org` ends with the
   `# desk-integration` section.
4. A runs `sminos say --in desk-integration "x"` and `sminos say
   "@desk-integration/<B's alias> x"`; a terminal on `alpha` runs the
   first: each is refused in §8's sentence, and no file of any log has
   changed. A runs `sminos join desk-integration`: refused, naming
   `sminos channel add`.
5. A runs `sminos channel remove desk-integration <B>`; after a pass B is
   out of the roster, `sminos list --stopped` on `beta` still shows B
   `stopped` in its project, and `beta`'s `known` no longer lists the
   channel while `alpha`'s does.
6. A runs `sminos channel remove desk-integration <S>` and `sminos channel
   remove desk-integration`; after a pass no stand-in lists the channel in
   `known`, and `sminos list --org` on `gamma` shows no section for it.
7. `T/channel_wire.py`'s check passes over the three stand-ins and the
   three stores.

**M7, the check on a real engine.** In a scratch tree `<scratch>`:
`HOME=<scratch>/home`, `CLAUDE_CONFIG_DIR=<scratch>/home/.claude`,
`SMINOS_HOME=<scratch>/sminos`, `MAWS_USER_DATA=<scratch>/maws`, the
engine's credentials passed through the environment, the plugin loaded
from the worktree (`--plugin-dir <worktree>/sminos`), `sminos` meaning the
worktree's launcher in every shell, the machine cut over as
`T/rl10-machines.sh` cuts one over, a stand-in serving it with `channels`
among its capabilities, and the scratch daemon (`sminos daemon run
--interval 5`) in a multiplexer of its own. Never the person's real
configuration.

1. In `<scratch>/a` a session A, in `<scratch>/b` a session B, each one
   turn, both left open. A runs `sminos channel create probe` and `sminos
   channel add probe @<B's short>`. Expect: B's transcript unchanged, and
   `sminos list` from both showing `# probe` with both.
2. `/clear` in B. Expect: `sminos list --channel probe` shows the thread B
   left, `stopped`, and not the new session; `sminos list` from the new
   session shows no channel section. `claude --resume <the session left>`
   in another window: it is listed live in `# probe`.
3. A is handed to a background job (the engine's own hand-off from inside
   the session, as T1's pass on a real engine did it). Expect, within two
   ticks: one row for A's thread in `# probe`, under the job's
   session id, and one statement of that set under the job's writer in A's
   project log.

Afterwards every scratch job is removed, the multiplexer and the scratch
daemon are stopped, and the report keeps what each step printed beside the
commands.

## Interfaces and Dependencies

CH2 is built against the names in this section (Y1, Y2, Y3). A name here
that an executor finds unbuildable as stated is changed here, by the
controller, with a dated line in the Decision Log, before the milestone
that exposes it closes.

### §1. Ids, kinds and names (Y1)

In `S/sminos.py`, beside `UUID_RE`:

    CHANNEL_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
    def is_channel_id(value) -> bool
        # a str that CHANNEL_ID_RE.fullmatch()es: MAWS's isChannelId. No I/O; callable from anywhere
    def project_kind(project) -> "channel" | "machine" | "hub" | "local"
        # "channel" first, by the id alone, whatever the org's directory calls the entry
    def known_projects(all_seats=None) -> list[Project]   # as today, without the channels
    def known_channels() -> list[Project]                 # the logs registered here whose id is a channel's
    def known_logs(all_seats=None) -> list[Project]       # both: for what opens, reconciles or leaves logs
    def _name_tiers(q) -> (tiers, clash)
        # as today over known_logs(), with two changes: `<name>#<short>` (short: the first hex digits of an id,
        # eight or more) names the logs of that name whose id begins with it; and when a channel is among the logs
        # a name answers and it is not the only one, every one of them is the clash, whatever tier it is in
    def ambiguous_name(q, logs) -> str                    # the one refusal (§8), for every caller
    def project_tiers(q), find_project(q, required=True)  # as today; a channel is refused in §8's words
                                                          # (with required=False it answers None, as no project)

In `S/sminos_channels.py`:

    def find_channel(q, required=True) -> Project | None
        # the channel `q` names, by its id, `name#short` or name; exit 4 with ambiguous_name when several logs
        # answer, with "no channel '<q>' is known on this machine" for none, with "'<q>' is a project, not a
        # channel" for a project; with required=False, None for none
    def register(channel_id, name) -> Project
        # the channel registered here as the org's directory registers a log (register_if_absent: no root, the
        # enrollment's hub); refuses an id that is no channel's

The vectors are the `ids` list of `T/vectors/maws/channel-rule.json`
(MAWS's file, pinned beside it; neither side edits it alone): every entry's
`channel` is what `is_channel_id` answers for its `id`.

### §2. The events (Y2)

Each as its log stores it, beside the log's own `ts`, `writer` and `seq`.

| Kind | Log, writer | Fields |
|---|---|---|
| `channels` (the statement) | the thread's own project; the thread's current session's writer, as `lifecycle` chooses it (its plain writer, or its audience stream) | `session`: the writer's own session, and no other; `thread`; `op`: the journal entry's id; `channels`: the whole set, a list of channel ids in the order added, `[]` for none. When it answers a request: `answers`: `{"channel": <id>, "id": <the request's id>}`, `result`: `"applied"` or `"refused"`, and with `refused` `reason`: `"not-reachable"`, `"read-only"` or `"limit"`. A refusal carries the set unchanged |
| `channel-request` | the channel's log; the requester's writer there: for a session, the stream `stream_choice` gives for the target as its one recipient; for a person at a terminal, the machine's human writer or its stream by the same choice | `op`: `"add"` or `"remove"`; `session`: the target thread's current session as the requester reads it; `thread`: the target's thread id; `id`: `uuid.uuid4().hex`, minted for this request. Nothing else, and never `to` |
| `channel-env` | the channel's log; the writing thread's own stream there (`own_stream`) | `op`: `"add"` or `"remove"`; `machine`: a machine's name as the org's directory lists it |

A reader takes a field of the wrong type as absent, and an event missing a
required field as no event of its kind. A request's `op` is the request's
verb and has nothing to do with the journal's `op` on a lifecycle event;
the field's name is C2's.

### §3. The record and its operation (X1, Y3)

In `S/sminos_threads.py`. Two keys of the record, both of the thread and
kept across its occupants, an end and a return:

| Field | Type | Meaning |
|---|---|---|
| `channels` | list of strings | the set (T1's field; `[]` when made) |
| `answered` | list of `[channel id, request id, the request's ts]`, or absent | the requests this thread has answered, oldest first. An entry whose `ts` is older than the request lifetime (§6) is dropped by the next write of the operation: such a request can no longer be pending |

Both are read for either store's record (`_of_seat` gives a seat's), and
`answered` is exported by no listing, as `sessions` and `pending` are not.
Adoption and the making of a record write `channels: []` themselves, not
through `update`, and keep doing so.

    OPS = (..., "channels")
    JOURNALED = (..., "channels", "answered")     # update() raises on either
    SEAT_KEYS = (..., "answered")
    CHANNEL_LIMIT = 128

    def set_channels(thread_id, decide, lock_until=None) -> dict | None
        # The one way a thread's set, its answered requests or a statement is written. Under the record's store
        # lock, on a fresh read, when the record has not ended and has no open entry: decide(record) answers None
        # (nothing is written) or a Change, and the Change is written in one write with its entry. Returns the
        # entry as written, None when nothing was. Takes no wake lock; does not move a seat's generation.
        #
        # Change = {"project": Project,       # the thread's own project: where the statement goes
        #           "session": str,           # the record's current session, which the statement is written under
        #           "channels": list[str],    # the set after the change (the same list for a refusal or a restatement)
        #           "answer": {"channel", "id", "ts", "result", "reason"} | None,
        #           "marks": {channel id: {writer: seq}}}      # §4; {} for none
        #
        # A Change whose session is not the record's current one, or whose `channels` holds more than
        # CHANNEL_LIMIT ids or an id that is no channel's, is a caller's error (ValueError), never written.

`decide` runs while the record's store lock is held, and for a spawned
thread that is the lock every seat's write waits on. It reads the record it
is given, other records by `get` and `current_record`, a session's own
writer files in one project (`_own_events`), a channel's log positions
(§4) and a session's record, all without a lock, and nothing else. It
never reads a view, a roster or a target (`view_of`, `members`,
`find_target`): each of those reconciles, and a reconciliation takes store
locks this process then already holds.

The entry:

    "pending": {"id": <minted>, "op": "channels", "at": <timestamp>, "project": <the Change's project's id>,
                "events": [<the statement of §2, whole>],
                "marks": {<channel id>: {<writer>: <seq>}}}

`finish` carries it in this order and clears it: the marks (§4), then the
statement, appended through `lifecycle` under the entry's id as every
journaled event is (T1 §6, step 2: skipped when the session's own events
hold a `channels` with that `op`). The entries of an **end** and a
**return** gain `marks` too, written by `begin` for every channel of the
record's set and carried with their settlement (a return's before its
`joined`, an end's after its `retired`). An **absorption**'s entry gains
`merged` (set once its merge is written) and the `marks` of the channels
the merge added.

**The transitions.** Each row's write is its linearization point; "the
lock" is the record's store lock.

| # | What happens | Read under the lock (else nothing is written) | The record's write | Marks | The statement owed |
|---|---|---|---|---|---|
| C1 | a thread adds itself (`channel add <c>`, `channel create`) | its current session is the caller's; that session is a member of the project; the set lacks `c` and holds fewer than 128 | `channels` with `c` appended | `c` | the new set |
| C2 | a thread removes itself | as C1, and the set holds `c` | `channels` without `c` | `c` | the new set |
| C3 | a request is honoured | §6's rows 2 to 4 and 13 again, the limit for an add, the session a member of the project | `channels` with `c` appended or taken out (unchanged when it already reads so); `answered` gains the request | `c`, when the set changed | the set, with `answers` and `result` `applied` |
| C4 | a request is refused | §6's rows 2 to 4 again, the session a member of the project | `answered` gains the request | none | the set unchanged, with `answers`, `result` `refused` and `reason` |
| C5 | the log states otherwise than the record (the reconciliation) | the set, the current session, that session a member of the project the difference was read in, and its writer there (`own_stream`), each as the reconciliation read it | none but the entry | none | the set |
| C6 | an end (T1 §6, rows 9 to 11 and 13) | T1's | T1's; the set and `answered` kept | every channel of the set | T1's `retired` |
| C7 | a return (row 12) | T1's | T1's; the set and `answered` kept | every channel of the set | T1's `joined`; C5 follows at the next reconciliation |
| C8 | an absorption (row 5) | T1's, and the absorbed record reserved | `channels`: its own, then the absorbed record's that it lacks, up to 128; `answered`: both, one entry per request | each channel added | T1's; C5 follows |

A thread in no channel that has never been in one has no statement and
needs none. C1 and C2 on a set that already reads so write nothing and say
so. After any row the caller nudges the daemon, so the uplink sees the
record within a scan.

In `S/sminos_channels.py`, the callers that build `decide`:

    def change(thread_id, channel, op, session) -> Outcome      # C1, C2: a thread's own add or remove (§6's Outcome)
    def restate(project, thread_id, session, writer, seen) -> bool
        # C5: `seen` the set the reconciliation read from the record. True when a statement was owed and its
        # entry begun; a failure to finish it is the next reconciliation's

**The lock of each writer this child adds.**

| What is written | By | Under |
|---|---|---|
| the record's `channels`, `answered` and the entry | `set_channels`, called by a command, the daemon's tick, the uplink at an answer, and a reconciliation in any process | the record's store lock (`.metalock` for a spawned thread's, `threads/.lock` for a human-opened one's), one write; refused while an entry is open |
| the merge of an absorption | `finish`, for the entry that absorbs | the absorbing record's finisher lock, then its store lock, one write, after the absorbed record is reserved |
| the statement | `finish`, through `lifecycle`, whoever calls it | the record's finisher lock, then the writer file's lock, with the guard that the log holds none under the entry's id |
| a mark | `finish`, through `sminos.mark_channels` | the record's finisher lock, then the delivery lock of that session for the channel's log, waited for with the settlement's bound; no store lock and no log lock held |
| a request, a `channel-env` event | the command, by `log_append` under its caller's own writer in the channel's log | that writer file's lock alone |
| a channel's registration | `channel create`, and `keep_org` as today | `register_if_absent`'s own lock |
| the asks held for requests | the uplink | one process, its main thread |

### §4. The marks (Y3)

In `S/sminos.py`:

    def channel_marks(channel_ids) -> {channel id: {writer: seq}}
        # for each channel registered here, every writer's latest seq in its log as this machine holds it now;
        # {} for one not registered here. Read with no lock, by `decide` and by `begin` under the record's lock
    def mark_channels(marks, sessions, lock_until=None) -> bool
        # for each channel and each session, under that session's delivery lock for the channel's log: each
        # writer's `settled` raised to the mark when it is below it, what the record held for a position at or
        # below the mark (`pending`, `pushed`, `held`, `revoked`) dropped with it; never lowered. False when a
        # lock could not be had in time: the entry stays open. Reports no delivery outcome

`sessions` is every session the record has had (its `sessions`, as `finish`
reads them): what a channel's log owes is kept per session, and a message
addressed to a session the thread had before is one CH2 may carry to the
session that continues it. After a mark, the thread is owed in that channel
only what its log gains from then on.

### §5. Reading membership (Y1)

**What the log states.** In `S/sminos_threads.py`, beside the reducer:

    class Fold:                       # gains the slot `stated`: {session: its statement in effect}
        def state(self, session, event) -> None
            # folds one own `channels` event of `session`: it is the session's statement in effect when its
            # writer is the writer of the session's latest `joined` (self.joined) and its seq is above that
            # `joined`'s; any other is none. add() of a `joined` clears the session's statement
    def stated_set(event) -> tuple
        # a statement's `channels` as a reader takes them: its strings that pass is_channel_id, in order, each
        # once, the first 128; () for no statement

Every reader of what a log states folds through `Fold.state`: `_projection`
(the row's `stated`), the memo `_reconcile` reads, and the index `channel
show` reads answers from. `Member.channels` (a tuple, `()` by default) is
`stated_set` of its row's statement: what every machine that may read the
thread's writer takes as its membership.

**What the record holds,** on the thread's own machine, in
`S/sminos_channels.py`:

    def channels_of(session) -> tuple
        # the set of the thread whose current session this is, when it is a thread of this machine that has not
        # ended; () otherwise. What the member frame carries and what a bare `list` reads for its caller
    def held_channels() -> frozenset
        # every channel id in the set of a thread of this machine that has not ended (sminos_threads.all_threads),
        # kept for the cache generation and the stores' stat key
    def opens_unfollowed(channel_id) -> bool      # channel_id in held_channels(): read from records and nothing else

**The roster.**

    def rosters() -> {channel id: [(Project, Member), ...]}
        # one sweep over view_of(p).members for p in sminos.known_projects(): each row whose `channels` holds the
        # id and that has not ended (has_ended), with the project whose view it is in. Kept for the cache
        # generation and dropped wherever a view is dropped (forget_caches, a lifecycle append, an import)
    def roster(channel) -> [(Project, Member), ...]       # rosters()'s rows for it, by alias, then short id

A row is the member's row in its own project's view, with every rule that
builds it: a thread this reader may not read is absent, a stopped one is
there with its state, one whose machine the org retired is not. `roster`
and `rosters` are called from `cmd_list`, `channel show`, `channel env` and
the pool. They are never called from `view_of`, `_reconcile`, the plane,
the uplink or anything those call, and in this child from no delivery or
addressing path (C1; CH2 gives each of those the roster on purpose).

### §6. Requests and their carrying out

In `S/sminos_channels.py`:

    REQUEST_TTL = 7 * 86400       # seconds a request can be pending, by its own ts; SMINOS_CHANNEL_REQUEST_TTL
    REASONS = ("not-reachable", "read-only", "limit")
    class Outcome(NamedTuple):
        state: str                # "applied" | "refused" | "pending" | "ignored"
        why: str                  # refused: one of REASONS; pending and ignored: a word of the tables below;
                                  # applied: "unchanged" when the set already read so, "" else
    def requests_of(channel) -> list[dict]
        # the log's `channel-request` events of §2's shape, in the merged read's order, kept beside the merged log
    def expired(request, now=None) -> bool        # its ts is unreadable or older than REQUEST_TTL
    def sender_verified(channel, request) -> True | False | None
        # True for a writer of this machine in a log where its name is provenance (own_writers_here). Else from the
        # key an import stores on the event, `verified`: False when it is no object or its signer's kind is
        # `legacy`; None while the revocation set cannot be read; False when the set names the signer; else True
    def reach_token(session) -> tuple | None
        # the session's record's owners with its access, shares and policyRev (sminos_audience.policy_of); None
        # while the record cannot be read
    def carry_out(channel, request, earlier, word=None, asked=None, lock_until=None) -> Outcome
        # one request, by the table below. `earlier`: the requests of this log before it for the same thread.
        # `word`: the endpoint's ("deliver" | "refuse" | None). `asked`: {"session", "reach"} the word was asked for
    def ask_of(request) -> dict | None
        # what the endpoint is asked about a request left pending `endpoint`, read now: {"thread", "session": the
        # thread's current session, "project": the thread's own project, "reach": reach_token(session)}; None
        # when row 2 or 6 holds, or the record cannot be read
    def carry_due(channel, words=None, only=None, lock_until=None) -> list[(dict, Outcome)]
        # the pass: every request of the log that is not expired and names a thread of this machine, in order,
        # each through carry_out; a request pending leaves the later ones for its thread pending `earlier`.
        # `words`: {request id: (word, asked)}. `only`: thread ids to keep to (a command's own targets)

`carry_out` answers by the first row that holds. T is the record whose id
is the request's `thread`.

| # | What is read | Outcome |
|---|---|---|
| 1 | the request is expired | ignored `expired` |
| 2 | T is no record of this machine, or has ended, or never had the request's `session`, or that session is now another record's current one, or T's session is lane B | ignored `not-here`: nothing is written for either thread, and the request expires |
| 3 | T's `answered` holds the request's channel and id | ignored `answered` |
| 4 | a request among `earlier` is not expired, passes row 2, and is not in T's `answered` | pending `earlier` |
| 5 | T has an open entry that `finish` does not clear now | pending `entry` |
| 6 | T holds no session; or its session is a member of no project now | pending `vacant`; pending `between` |
| 7 | the request is from elsewhere (`policy.outside_origin`) and the kept welcome lists no `channels` | pending `no-channels` |
| 8 | the request is from elsewhere and the machine admits nothing from outside (`policy.read_only`) | refused `read-only` |
| 9 | its writer is this machine's own and shares the thread's owners: a session's writer by `same_owner_local`, the human writer by `owners_meet("", session)` | honoured |
| 10 | `sender_verified` is False; is None | refused `not-reachable`; pending `unverifiable` |
| 11 | no word | pending `endpoint` |
| 12 | the word is `refuse` | refused `not-reachable` |
| 13 | the word is `deliver`, and T's current session or its `reach_token` is not what `asked` holds | pending `moved` |
| 14 | the word is `deliver` | honoured |

Honoured: an add of a channel the set lacks while it holds 128 is refused
`limit`; anything else is applied. Rows 2, 3, 4, 13 and the limit are read
again by `decide` under the lock (§3, C3 and C4), which answers None when
any has changed: the outcome is then that row's, and nothing was written.
Requests for different channels are not ordered against each other.

The pass's three callers: the command that wrote a request for a thread of
its own machine (`only` its targets, no words); the daemon's tick, for
every channel known here, after the channel's reconciliation; the uplink,
at each ask pass and at each answer (M6), which asks about what the pass
left pending `endpoint`.

The words a command and `channel show` print:

| | Words |
|---|---|
| `not-reachable` | its machine does not let you message it |
| `read-only` | its machine admits nothing from outside |
| `limit` | it is in 128 channels, the limit |
| `earlier` | behind an earlier request for it in this channel |
| `entry` | its record holds an unfinished operation |
| `vacant`, `between` | the thread holds no session now; its session is between two projects |
| `no-channels` | its machine's endpoint does not serve channels |
| `unverifiable` | its machine cannot read its revocation set |
| `endpoint` | its machine's endpoint has not said whether you may message it |
| `moved` | its session or its reach changed while its machine asked: asked again |

On another machine a requester reads none of the pending words: it reads
`pending on <machine> since <time>`, which covers a machine that is off, one
whose sminos or MAWS predates channels, and an answer it may not read.

### §7. The wire (X5)

In `S/sminos_rl10.py`: `CAPABILITIES = ("audience", "record", "locations",
"channels")`, in that order (the fixture's hello).

In `S/sminos_uplink.py`:

    Link.channels: bool                      # the welcome listed `channels` (welcomed_rl10)
    def Link.unfollowed(self, pid) -> bool   # the hello carries no `follow`: holds(pid) for a project,
                                             # sminos_channels.opens_unfollowed(pid) for a channel
    def Link.holds(self, pid) -> bool        # as today for a project; False for a channel
    def member_frame(pid, m, launch=None, visibility=False, channels=()) -> dict
        # `channels`, when it is not empty, as the frame's last key: a list

| For a log that is | `hello` | `machine`, session presence, `pending`, host frames | uploads |
|---|---|---|---|
| a project this machine holds | no `follow` | as today | as today |
| a project it follows | `follow` | none, as today | as today |
| a channel a record of this machine names | no `follow` | none | this machine's requests and `channel-env` events, and a `retired` that undoes an older copy's `joined` |
| a channel no record here names | `follow` | none | the same |

A thread's `member` frame names its own project as `project`, as today,
and never a channel; while `Link.channels` it carries the thread's
`channels`.

`fresh_frame` passes `channels_of(m.session)`'s entries that pass
`is_channel_id`, the first 128, for a lane A member while `Link.channels`,
and `()` otherwise; its key (`made_of`) takes that tuple.

### §8. The CLI

    sminos channel create <name> [<thread>]            # the caller is the first member; from a terminal, <thread>
    sminos channel add    <channel> [<thread>...]      # with none named, the caller
    sminos channel remove <channel> [<thread>...]
    sminos channel show   <channel> [--json]
    sminos channel env    add|remove <channel> <machine>
    sminos list … [--channel <channel>]…

A `<channel>` is an id, a `name#short` or a name (`find_channel`); a
`<thread>` is what `find_target` takes. Exit 0 when every target was
applied or is pending; 1 when the verb or any target was refused; 4 for a
name that is unknown or ambiguous; 2 for usage.

**Refused before anything is written,** each naming its target: `create`
and `add` where the kept welcome lists no `channels`; `create` with a name
that is no valid name, or that a log known here already answers to; a
target that is no thread as this machine reads it (its row carries no
`thread`, or on this machine its lane is B); one that has ended; one that
holds no session; an add that would be a 129th channel where this machine
can see the set (its own record, or the row's `channels`); a target the
stream choice refuses; from a session, `create` with a thread named (the
caller is the first member, and `add` places the others); from a terminal,
no thread named, or for `create` a thread of another machine; `env` from a terminal, from a thread not in the
channel, or naming a machine the org's directory does not list.

**The sentences that are decisions** (`%s` the name as given):

| Where | Exit | Words |
|---|---|---|
| `say --in <channel>`, a tag `@<channel>/<alias>`, a selector `--project <channel>`, from a session or a terminal | 1 | `%s is a channel, and speaking in a channel is not available in this version of sminos yet: nothing was recorded. Tag the thread itself (@<alias>#<short> or @<short>), which reaches it in its own project as today` |
| a verb's target `<channel>/<alias>` (`find_target`) | 4 | `'%s' names a thread through a channel, which is not available in this version of sminos yet: name it by its own name (<alias>#<short> or <short>)` |
| `join <channel>` | 1 | `cannot join %s: it is a channel, not a project — sminos channel add %s places a thread in it, and its project stays where it is` |
| a project asked for, a channel named (`find_project`: `chat`, `list <name>`, `--project`) | 4 | `'%s' is a channel, not a project: sminos channel show %s prints it` |
| a name several logs answer (`ambiguous_name`) | 4 | `ambiguous name '%s': <each> — name one as listed, or by its id`, each as `<name>#<the first eight of its id> (<kind>)`, kind one of `channel`, `project`, `machine project`, `local project`; a log whose id is no UUID by its whole id |
| a `.smns` naming a channel id (a warning on standard error) | — | `ignoring %s: it names a channel's id, and a channel is no project; this directory is in the machine's project` |
| `create`, `add` without the capability | 1 | `this machine's endpoint does not serve channels (its welcome listed no channels): nothing was written` |
| the limit, before writing | 1 | `%s is in 128 channels, the limit: nothing was written` |

**What a target's line says:** `<alias>#<short>: in <channel>`, `out of
<channel>`, `already in <channel>`, `was not in <channel>`, `refused: <§6's
words>`, `pending: <§6's words>`, or, for a thread of another machine,
`asked; pending on <machine>: its machine carries it out when its daemon
reads the request`.

**`list`.** A bare `list` from a thread: its project's section exactly as
today, the `+N hidden` line included, then for each channel of
`channels_of(<the caller>)`, by name then id, a line `# <name>` and the
roster's rows with the project column, none folded. `--channel` (which may
be given more than once) prints one such section per channel named, its
rows narrowed by the other filters. `--org` prints today's table and then
a section for each channel known here whose roster is not empty. In
`--json` a row gains `channels` (a list of ids) when its thread is in any,
and no key otherwise; the sections add nothing to it.

**`channel show`.** A heading `# <name>  <id>`; `members`, the roster's rows
with the project column (`(none)` for none); `requests`, one line each for
the log's requests that have not expired, oldest first: its time, its verb,
its target, its requester, and `applied`, `refused: <words>`, `refused: not
reachable (the hub withheld it)` or `pending on <machine> since <time>`;
`pool`, one line a machine: its name, `<n> live, <m> stopped` counted from
the roster's rows there (`live`: a state of `FILLED`; `stopped`: `stopped`
or `gone`), and `added by hand` for one a `channel-env` holds in. With
`--json`: `{"id", "name", "members": [<a list --json row, with its project
keys>], "requests": [{"id", "op", "thread", "session", "target", "by",
"ts", "state": "applied" | "refused" | "withheld" | "pending", "reason",
"machine"}], "pool": [{"machine", "live", "stopped", "by_hand"}]}`.

`sminos help` (the module's docstring) lists the six lines above. The
backtick guard's `VERBS` gains `channel`.

### §9. What the tests are built on

**The checker,** `T/channel_wire.py`, called by every suite of this child
that runs an uplink, and by CH2's:

    ALLOWED = ("channel-request", "channel-env", "retired", "void")
    def published(frames, channel_ids, allowed=ALLOWED) -> list[str]
        # each breach among the frames a stand-in kept, one line each; [] for none
    def written(sminos_home, channel_ids, machine, allowed=ALLOWED) -> list[str]
        # the same over the store: the channel's log files of this machine's writers, its host store

A breach is: a `member` frame whose `project` is a channel id; any
session-plane message (`presence`, `machine`, `host`, a subscription's)
whose project is one; a `pending` frame for one; a `words?` for one; a
`reach?` for one whose event is no `channel-request`; an `events` frame
for one carrying a kind outside `allowed`; a `member` frame with
`channels` that is empty, holds more than 128 ids, holds an id that is no
channel's, or is sent on a connection whose welcome did not list
`channels`; on disk, an event of this machine's writers in a channel's log
of a kind outside `allowed`, or anything in a channel's host store. CH2
calls it with the kinds it adds.

**The stand-in** (`T/endpoint_standin.py`) gains what MAWS's endpoint does
for channels, read from MAWS's master at `8ae3b0843` (`#knownNow` in
`src/endpoint/registry.ts`, `sessionProjects` in
`src/endpoint/rl10/link.ts`, `memberChannels` in
`src/endpoint/rl10/members.ts`): `known()`, and `known` in its state, the
logs the live connection opened without `follow` whose id a held member
names: its `project`, and, when the hello listed `channels`, each id of a
lane A member's `channels` that passes the predicate, the first 128; a
member frame whose `project` is a channel id is treated as that session
gone; and its welcome lists `channels`, when configured to, only to a
hello that listed it. `T/rl10-machines.sh` gains a helper that builds the
org's directory for a suite's machines from their stand-ins' `known` (each
project, and each channel some machine knows, as an entry of kind `hub`)
and sends it to each, so a machine follows a channel for the reason it
would on the fleet. Today's stand-in keeps every hello and member frame
and computes no `known`: this addition is what lets two holders and a
follower be shown, with three homes.

**The engine** is T2's test engine (`T/wake_engine.py`, its shell stub):
every suite of this child asserts that it recorded no launch.

**Where each new file sits,** and the neighbour it is built like:
`test_channels.py`, `test_channels_store.py` and `test_channels_requests.py`
are `unittest` modules that load the CLI's modules under a temporary home,
as `test_threads.py` and `test_threads_ended.py` do; `test_channels_wire.py`
runs a real `Link` against an in-process `endpoint_standin.Endpoint`, as
`test_rl10.py` and `test_leaving.py` do; `test-channels.sh` drives the
launcher on one cut-over home with a stand-in beside it, as `test-join.sh`
does; `test-channels-machines.sh` joins two and three homes with
`rl10-machines.sh`, as `test-org.sh` joins three. All run in the `channels`
part of `T/run-sminos-tests.sh`; the older-copy suite and the replay stay
where they run today.

### Dependencies

- MAWS's master with its child MW (the endpoint echoes `channels`, counts
  `member.channels`, refuses a member whose project is a channel id, and
  lists a known channel in the org frame as kind `hub`), installed on the
  owner's machines. Nothing in this child's suites runs MAWS: the stand-in
  and the conformance replay stand for it.
- MAWS's fixture at `8ae3b0843` (M5) and its vectors `channel-rule.json`
  at the pinned version 1 (M1).
- Python's standard library alone, as every module of `S/` today.

## Surprises & Discoveries

None yet. The controller records here what changes the understanding of the
design while the milestones are built, one observation and its evidence
each.

## Decision Log

- 2026-11-21 — **Verification.** This plan is reviewed before it is handed
  over by the `doperpowers:adversarial-reviewer` agent, on buildability: the
  milestones against the code, the names of Interfaces against the two
  designs, and §3's and §6's tables against the store's locks. A second
  round reads the revision if the first changes a milestone's cut or a
  table, and there is no third before the build. The build runs under
  `doperpowers:plan-executor`, a fresh executor a milestone; each milestone
  is reviewed at its close by the execution loop's reviewer, three reviews
  at most (the owner's bound). The range M1 to M6 is reviewed whole by the
  composite's holder at the frontier, through doperpowers:review-code at the
  panel rung with the four lenses named in Plan of Work, a second whole
  reading if the first confirms more than ten, three rounds at most. After
  M7 the branch is reviewed once more through doperpowers:review-code at the
  panel rung, on the whole range, before the pull request merges. The
  composite's own scene on two of the owner's machines is not this plan's:
  the holder runs it once CH2 has landed.
- 2026-11-21 — **Seven milestones, listing before the wire, the frontier
  after the sixth.** Readers and refusals first (M1), the store's operation
  alone (M2), then its two consumers on one machine (M3, M4), then the wire
  (M5) and what crosses it (M6). *Alternative: the wire second, so that a
  real endpoint could be used from the start.* It lost because MAWS echoes
  the capability only to a hello that lists it: until the fixture is copied
  no real endpoint serves channels anyway, and the copy needs the operation
  to place the replay's session. *Alternative: M1 cut in two (names; the
  publishers).* It lost to the bound of five to seven; M1 is one idea, the
  predicate applied at every door, and one reviewer reads it as such.
- 2026-11-21 — **"The thread's lock" is the record's store lock for the
  write and its finisher lock for the carrying out; the operation takes no
  wake lock.** C3 says "under the thread's own transition lock". Every
  journaled operation but a release opens under the wake lock (`begin`),
  because it ends a thread or changes its occupant; a membership does
  neither. *Alternative: take the wake lock, as an end does.* It lost
  because a wake in flight holds that lock for seconds: a local add would
  then meet a third wait beside the two A1 names, and a reconciliation in a
  reading verb would stall on it. What is given up: a wake that launches in
  the instant a membership entry is open loses its own record writes for
  that attempt, as it does across a delayed release (logged in M7).
- 2026-11-21 — **`known_projects` returns no channel; `known_logs` returns
  both.** Some two dozen callers enumerate projects for a person or a
  session, and a handful open, reconcile or leave logs. *Alternative: leave the enumeration
  whole and filter where a channel must not show.* It lost because the two
  failures are not alike: a caller that wrongly lacks a channel fails this
  child's own tests (its log is never opened), while one that wrongly keeps
  one prints or publishes a channel as a project in a path no test visits.
- 2026-11-21 — **A channel's view has no members by construction,** and
  `lifecycle` writes nothing but a `retired` under a channel id. C1 says
  the view "returns none, as it does today", which holds only while the log
  holds no `joined`; an older copy's `join` writes one. *Alternative: rely
  on the reconciliation retiring it.* It lost because the plane, the member
  set and the forced presence read the view before and after that
  `retired`.
- 2026-11-21 — **A channel shares no tier, and `name#short` is taken
  wherever an argument takes a name.** Today a hub project is found before
  a machine's of its name; the composite wants every log a name answers
  listed once a channel is among them, with `name#short`, which nothing
  accepts today. *Alternative: list full ids, as today's refusal does.* It
  lost to C6's text. A tag's grammar (`TAG_RE`) cannot carry `#` in its
  qualifier, so a tag takes the id; whether it should take more is CH2's,
  with the tags.
- 2026-11-21 — **`find_project` refuses a channel, so `chat <channel>` and
  `list <channel>` are refused until CH2,** and `find_target` refuses a
  target qualified by a channel. Nothing in the composite gives CH1 a
  reader of a channel's conversation or an addressing path through one, and
  Y1 leaves each path that takes the roster to CH2. *Alternative: resolve a
  qualified target through the roster now.* It lost because it is the
  first addressing path through a channel, built without the rule for
  which log its writes go to having a test in this child. A11 is met by
  the verbs' targets never being found in a channel.
- 2026-11-21 — **The `.smns` rule is in `_smns_decision` and gives the
  machine's project.** *Alternative: in `read_smns`, as a file that names
  no valid id.* It lost because the walk would then go on to an outer
  `.smns` or the remote's project, where the composite says the machine's.
  MAWS's own rule derives a version-8 id from a `.smns` as a project's; its
  shared cases hold none, so the parity pin stands.
- 2026-11-21 — **`channel create` refuses a name a log known here already
  answers to.** D3 lets two channels share a name, and two machines can
  still make that happen; but one thread creating `desk` twice by mistake
  would leave every later `channel add desk` ambiguous. *Alternative: allow
  it and print the id.* It lost to that mistake's cost against a refusal
  that costs one other name.
- 2026-11-21 — **`list --json` carries `channels` only on a row that is in
  one.** C6 says the output "gains a `channels` key"; A13 says a session in
  no channel prints byte for byte what it did. The wire's own rule (no key
  for a thread in none) settles it the same way. *Alternative: an empty
  list on every row.* It lost to A13.
- 2026-11-21 — **`answered` is `[channel, request id, the request's ts]`,
  pruned by that ts at each write of the operation.** The composite says
  the record keeps what it answered "for as long as a request can be
  pending", which is seven days from the request's own timestamp; keeping
  the timestamp makes the pruning and the expiry one comparison on one
  clock.
- 2026-11-21 — **A request that names no thread here gets no statement,**
  for every case of §6's row 2, and expires. The composite says so for a
  session that became another thread's and for lane B; an ended thread and
  a session the thread never had are the same case to this machine, and to
  one that holds no such thread at all the request is simply another
  machine's. *Alternative: a refusing statement with a fourth reason.* It
  lost because C3 fixes the reasons at three and a statement needs a thread
  to be written under.
- 2026-11-21 — **A mark covers every session the record has had, reports
  no delivery outcome, and an absorption marks the channels it adds.** The
  composite says "the thread's delivery record for that log"; the record is
  kept per session, and CH2 carries a channel's debt from a session to the
  one that continues it, which would bring back what only the current
  session's mark had settled. *Alternative: the current session alone.* It
  lost to that. *Alternative: an outcome for each outside event a mark
  buries, as an end's settlement reports one.* It lost because CH1 has no
  delivery in a channel and would be the first to send a `delivery` message
  under a channel id; what the sender reads meanwhile is what it reads for
  any thread on another machine.
- 2026-11-21 — **A statement goes to the project in whose log the session
  is a member at the write; a thread with no session, or between two
  projects, waits.** *Alternative: the project the caller found the thread
  in.* It lost because a `join` between the lookup and the write would put
  the statement, and the answer to the requester, under a writer whose
  membership had just ended there.
- 2026-11-21 — **A person at a terminal asks by a request under the
  machine's human writer, honoured when the machine's owners meet the
  thread's.** `same_owner_local`, the code's "same owner on one machine",
  answers only for a session's writer. *Alternative: write the statement
  directly, with no request.* It lost because every placement of another
  thread would then have two paths, and the tick could not finish one a
  terminal's command left.
- 2026-11-21 — **The endpoint's word is asked for only where the welcome
  lists both `reach` and `channels`,** and also for a request of this
  machine's own writer whose owners differ from the thread's. Without
  `reach` no check exists, and a request with no check is not honoured: it
  stays pending.
- 2026-11-21 — **A sender is held as verified from the key an import
  stores on the event.** Every event that arrives over RL10 carries
  `verified` with its signer (`S/sminos_hublog.py`), the same key the
  frame's label and the words gate read; a legacy signer and a revoked one
  are not verified, and an unreadable revocation set leaves the request
  pending, as the words pass leaves a signed event unasked.
- 2026-11-21 — **"Its reach has not changed" is read as the session
  record's owners, access, shares and policyRev,** compared as one value
  between the question and the write.
- 2026-11-21 — **The uplink's ask pass is a caller of `carry_due`,** and
  asks about what that pass left pending for the endpoint's word, under a
  key of its own and past the hold filter the message asks use.
  *Alternative: a second function that lists what is due to be asked.* It
  lost because it would be a second copy of §6's table that the first can
  drift from.
- 2026-11-21 — **`channel env` is a member's alone,** refused from a
  terminal and from a thread outside the channel, since C2 honours it only
  from a writer whose thread is in the roster.
- 2026-11-21 — **An RPC that names a channel as its project is answered as
  one naming no project here** (`Here.project`). MAWS's app lists a channel
  a machine knows among its projects until it has a channel view, so such
  an RPC can arrive.
- 2026-11-21 — **The channel suites are a part and a gate of their own**
  (`SMINOS_PART=channels`, `sminos-channels`). The `sminos-suites` gate ran
  18 to 20 of its 30 minutes before T1 and T2 added theirs. *Alternative:
  add to `suites`.* It lost to that margin, and to reading A13 off two
  gates this child does not change.
- 2026-11-21 — **One narrow check on a real engine, in M7.** The composite
  puts the pass on a real engine in CH2, where the engine is in the path.
  Here it is in the path only through a `/clear` and a hand-off, which
  this child adds a restatement and a merge to, and T2's retrospective
  says what the suites missed there twice. *Alternative: none until CH2.*
  It lost to three steps' cost against finding it after a release.
- 2026-11-21 — **The stand-in computes `known`, and a suite's directory is
  built from it.** *Alternative: assert the hellos and member frames and
  leave `known` to MAWS's own tests.* It lost because A7 is stated in terms
  of `known`, and a suite whose directory is written by hand follows a
  channel for a reason the fleet does not have.

## Outcomes & Retrospective

Pending — written at finish.
