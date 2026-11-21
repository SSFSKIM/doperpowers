# sminos channels, CH1 — the channel and who is in it: execution (2026-11-21)

> **Composite:** `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`,
> child **CH1** (The channel and who is in it). **Parent pin:** branch
> `sminos-channels-ch` at `331e2dd5`, that file's blob
> `669a75c0d3e646c3d3cc2a03baa163c53803c45c`. The design the composite is itself
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
> its constraints (the lock order, the wake lock) and its Outcomes &
> Retrospective; and `docs/doperpowers/TECH-DEBT.md`, section "sminos
> threads".

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
- [x] (2026-11-21) This plan written against the composite at `ef34f2ca` and the code at `1fdc73a0` (sminos 1.52.0), commit `71575958`.
- [x] (2026-11-21) The plan's first review for buildability (fourteen findings); the composite revised for two of them (`95fef6b7`) and this plan revised on it (Decision Log, "The plan's review").
- [x] (2026-11-21) The revision's review, the second and last before the build (eight findings; the composite made exact in one place, `331e2dd5`), folded in (Decision Log, "The plan's second review").
- [x] (2026-11-21) M1 — A channel id is told from a project's at every door, and nothing is published under one. `dba3f5e8..eee82f3b`, three reviews (the bound), then the idle trim and round 3's last finding fixed (Decision Log, "M1's idle trim"); `sminos-idle` 32,161 calls a second.
- [x] (2026-11-21) M2 — A thread's declared set: one durable operation, its statement and the statement's reader. `5ec8f9d6..ec4034c1`, clean at its third review; `sminos-idle` 32,165 calls a second.
- [x] (2026-11-21) M3 — The set across a thread's life: the log kept equal to the record, a return, a continuation, an absorption. `54cacc3a..7748fde1`, three reviews (the bound), then round 3's last finding fixed; `sminos-idle` 32,024 calls a second.
- [x] (2026-11-21) M4 — Requests on one machine, and the verbs that write them. `04cc6146..9ffbe8c5`, three reviews (the bound), then round 3's last finding fixed; `sminos-idle` 32,232 calls a second.
- [x] (2026-11-21) M5 — The roster, the listing and the pool. `b4a9bdd7..10b8740a`, clean at its third review; `sminos-idle` 32,772 calls a second.
- [ ] M6 — The wire: the capability, `member.channels`, opening without `follow`, MAWS's fixture.
- [ ] M7 — Requests across machines: the endpoint's word, and what a requester is told.
- [ ] The review of M1 to M7 as one range, by the composite's holder, and its fixes.
- [ ] M8 — Older copies, what is written beside the code, the version, and the acceptance.
- [ ] The branch reviewed at its end (Decision Log, "Verification"), and its fixes.

## Words this document adds

The parent's Terms define thread, project, log, writer, member, channel,
pool, hello, hold, follow, known, the directory, reach, lane B, the hub and
the endpoint. T1's plan defines spawned, human-opened, the seat store, the
thread store, stamped, the journal and its entry. T2's plan defines the wake
lock, the delivery lock and held. Added here:

- **The set** of a thread is its record's `channels`: the declared channels
  it is in, in the order they were added, on its own machine.
- **Where a membership began** is, for one channel of the set, the positions
  of that channel's log as the thread's machine held it when the thread
  entered: each writer's latest seq then. The record keeps it (`began`,
  Interfaces §4); nothing of it is written into a log.
- **The statement** is the event of kind `channels` a thread's machine writes
  in the thread's project log (Interfaces §2). **What the log states** for a
  session is the set a reader takes from it by C2's rule (§5).
- **A request** is an event of kind `channel-request` in a channel's log
  asking that one thread be added or removed. Its **requester** is its
  writer; its **target** is the thread it names. Its **answer** is the
  statement that names its channel and id under its target's thread (§5).
- **The thread's own project** is the project in whose log the thread's
  current session is a member: where its lifecycle events and its
  statements go, whatever log the thread was found through.
- **The roster** of a channel is the read of §5: the rows, each from its
  thread's own project's view, of the threads whose log states the channel.
- **Opens without `follow`** is said of a channel's log on a machine whose
  hello for it carries no `follow` key: MAWS counts that machine as a holder.
  `Link.holds` keeps today's meaning, everything a held project is sent
  (the machine's presence, its checkouts, its sessions' presence), and is
  never true of a channel (§7).
- **The endpoint's word** is its answer to a `reach?` frame: `deliver`,
  `refuse`, or none while it holds no record of the session asked about.
- **A cut** is a process stopped between two writes of one transition; in a
  test, the first write made and the rest not called.
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
  no `pending` set and no host frame is sent under one; this code writes no
  `joined`, `state`, `renamed`, `titled`, `in-charge`, `status`, `unlisted`,
  `channels`, `message`, `question` or `answered` into a channel's log. What
  this code adds to a channel's log is a `channel-request`, a `channel-env`,
  and the `retired` that undoes a `joined` an older copy wrote there. What
  an older copy wrote into a channel's log under this machine's writers is
  uploaded in its place in the writer's order, as any own event not yet
  sent is (a writer's sequence has no hole), and this code's `retired`
  follows it. A question the endpoint asks about a channel (a snapshot
  request, a subscription) is answered as for a log with no member.
  `T/channel_wire.py` (§9) is the check, over what this code added to the
  store it found, and every suite of this child that runs an uplink ends by
  calling it.
- **Every verb that writes for a channel is refused without the
  capability:** `channel create`, `add`, `remove` and `env`, where the kept
  welcome lists no `channels`. Until M6 no real endpoint lists it (MAWS
  echoes the capability only to a hello that listed it), so nothing this
  code writes names a channel on the wire before then. One exception is
  intended: a channel the org's directory lists is registered and its log
  opened with `follow`, as every installed copy already does.
- **A channel's view has no members, and the roster is a read of its own**
  (C1). `view_of` of a channel answers no member, by construction and
  whatever its log holds. No path that exists today (delivery, tag
  resolution, `@all`, `find_target`, the plane, the uplink's publishers, the
  guide) is given the roster in this child: its readers are `list`,
  `channel show`, `channel env` and the pool, and nothing else.
- **A fact about a thread is written to the thread's own project.** No verb
  and no pass writes a lifecycle event, an in-charge line, a status or a
  statement for a thread into a channel's log.
- **One writer of a thread's set.** A record's `channels`, `began` and
  `answered` are written by `sminos_threads.set_channels` and by the
  journal's own writes (a return's, an absorption's merge), and a `channels`
  event is appended by `sminos_threads.finish` for an entry that owes one.
  Nothing else writes any of them: `update` refuses the three keys, and the
  reconciliation calls `set_channels` and never appends a statement itself.
- **What must survive an older finisher is in the record's write.** Any
  copy from 1.51.0 on finishes an open entry it finds: it appends the events
  the entry owes and clears it, and skips a step it does not know. So the
  operation's record write holds everything but the statement (the set,
  where each membership began, the request answered), and its entry owes the
  statement as an event and nothing else. A step only this code's `finish`
  runs (the absorption's merge) is one whose loss the composite accepts.
- **What an operation decides, it reads under the record's lock.** The new
  set, where a statement goes, and for a request the whole of §6's table
  (whom it names, whether it is answered, the earlier requests and the
  expiry, the branch that honours or refuses it, whether a word was asked
  for the thread as it is now, the limit) are evaluated in the write that
  makes the change, on a fresh read, never taken from a read made before
  it. What was read before the lock chooses only whether to try. T1's
  branch review found most of its 82 defects between a check and its
  write. One window is accepted: a reach narrowed between that read and the
  record's write is under another lock (the session record's), and a
  request it would have refused is honoured.
- **Lock order,** outermost first, as T2 fixed it and unchanged: the
  delivery lock; the seat's lifecycle lock; the wake lock; a store lock
  (`.metalock`, then `threads/.lock`); a log's lock. A record's finisher
  lock (`threads/.finish/<id>.lock`) is held by `finish` for its whole run,
  outside the store and log locks it takes. The membership operation takes
  the thread's wake lock as every transition of a thread does (T2: a wake
  sees the record before an entry or with it, never between), before any
  store lock, and lets it go at its record write; it takes no lifecycle
  lock and no delivery lock, and holds no store lock while it takes any
  other lock: what it reads under the store lock it reads without a lock.
  A wake in flight is a wait: nothing is written, a request stays
  `pending` for the next pass, and a thread's own change, which no later
  pass would carry out, fails and says so. A command waits for the wake
  lock as a transition does
  (`SWEEP_WAIT`); a reconciliation and a pass only try it. Interfaces §3
  names the lock of each writer this child adds.
- **No delivery record is touched.** This child delivers nothing in a
  channel and settles nothing there: where a membership began is the
  record's, and CH2 delivers from it.
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
  kind it does not know), the record's new keys are ones older code leaves
  in place, and nothing here defends against an older CLI run by hand beyond
  what M2 and M8 assert.
- **Accepted, and not built** (the composite's reviews; no milestone tries
  to close them): a sender removed from the org between a request's import
  and the endpoint's answer is honoured; an absorption that an older copy
  finishes drops what the provisional record had gained; an older copy that
  itself begins a return leaves the record's positions as they were before
  the end, so a later release may push what the channel's log gained while
  the thread was ended, and so does a return of this code's over a channel
  whose log is there and cannot be read, for that channel alone (the
  holder's ruling of 2026-11-21); a session an older copy joined into a channel and
  that is closed before this code's next reconciliation is listed in
  neither until it runs again; a 1.51.0 or 1.52.0 copy's `list --json`
  shows a spawned thread's record keys it does not know, the positions and
  the answered ids (the set it knows, and hides); a narrowing whose
  withdrawn audience could not be named leaves the old row standing in a
  roster as in the project's view; requests of two machines whose clocks
  disagree are carried out in the stamped order, and a request stamped
  more than seven days behind is never carried out; two adds contending
  for a thread's last place under the limit are not ordered; two machines,
  or two commands at once, creating one name make two channels of that
  name, which the name rule refuses until one is named by its id. And no
  lock holds a channel's log still: where a membership began, and the
  order of requests, are observed at the last read before the record's
  write, so an event imported between that read and the write counts as
  after it (a message so placed is one CH2 pushes; a request so placed is
  carried out as one that arrived later). The rereads of §6 bound what one
  call acts on; they do not close that window, and nothing claims the
  stamped order across it.
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
  gains `channels` (M6). A key or a line this child adds appears only where
  a channel does. Two projects of one name in different tiers keep today's
  precedence (the hub project is found first).
- **What sits beside the code is written with it.** Each milestone adds
  what it built to `sminos/skills/sminos/scripts/CLAUDE.md` (the new
  module, the rules of this section that a later change could break, the
  tests' names), since the next milestone's executor reads that file before
  it reads this one's code; M8 reads the whole against the tree.
- **Tests are hermetic,** as in T1 and T2: the test engine, the stand-in,
  temporary `HOME` and `SMINOS_HOME`, invented names. The repository is
  public: no hostname, account, project id or local path enters a test, a
  comment or this document.
- **Tests vary what a single case hides:** both kinds of thread (spawned
  and human-opened) as target, live and stopped; one, two and five requests;
  one and two requesters; the three callers of the carrying out (the
  command, the daemon's tick, the uplink at an answer) and the order of
  their answers; a request before and after a continuation, a refill, a
  `join`, a change of reach, an end and a return; and a cut after each
  write of each transition. A guarantee tested with one request to one live
  human-opened thread is not tested.
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
M2 builds the one operation that writes a thread's set, durable across a
cut and across an older copy's finisher, with its statement and the
statement's reader. M3 carries the set through a thread's life: the
reconciliation that keeps the log equal to the record, a return, a
continuation, an absorption. M4 adds requests and the verbs that write
them, on one machine. M5 builds the roster and everything that prints it.
M6 turns the wire on: the capability, the member frame's `channels`, MAWS's
fixture. M7 carries requests between machines, on the endpoint's word.
Between M7 and M8 the range is reviewed whole by the composite's holder. M8
runs older copies against the result, reads what sits beside the code,
bumps the version and runs the acceptance.

Eight milestones, one more than the bound this plan was first cut to: its
review advised reviewing the durable transition and the ownership of a set
across transitions each on its own, and they are two verification
strategies (cuts injected at the store; T1's hand-off, refill, `join` and
return driven through their own fixtures), so M2 and M3 are two.

**The frontier review.** When M7's review is clean the controller pushes the
branch and returns to the composite's holder with the word `FRONTIER`, the
range (`git merge-base origin/main HEAD` to `HEAD`) and nothing else to
decide. The holder reviews that range through doperpowers:review-code at the
panel rung, with lenses given, not derived: lock order, and what is read
outside the lock it is acted on under; an older copy on the same store;
what leaves the machine (every frame and every event under a channel id,
and whether anything names a private requester's session, or another
member's writer, to a reader of its target); and the milestones'
interactions (a request against an end, a return, a hand-off, an
absorption, a `join`, a change of reach, a wake and the thread sweep; the
reconciliation against each of them). Its confirmed findings are fixed on
the branch by the holder's fix wave, the range is read whole a second time
if the first reading confirms more than ten, and there are three rounds at
most. The controller is then continued for M8. It sits after M7 because
every writer and every sender this child adds exists by then and M8 adds
none; T2's review of its first four milestones as one range confirmed 62
findings over three rounds, five of them a lost message or a wrong
recipient, after each milestone had been reviewed clean.

### M1 — A channel id is told from a project's at every door, and nothing is published under one

**At its end:** an id that passes `is_channel_id`, however it reached this
machine (the org's directory, a `.smns`, a join override an older copy
wrote, an argument), is a channel to every lookup. `sminos projects` and
`sminos list` show no channel as a project; `sminos join <channel>` is
refused and names `sminos channel add`; a `.smns` that names one files its
directory in the machine's project and says why; `say --in <channel>`, a tag
qualified by a channel, a selector naming one, and a verb's target qualified
by one are refused in §8's words with nothing appended; a name that a
channel shares with another log is refused by one function, listing each
with its kind and `name#short`. The channel's log is opened at the hub with
`follow` and kept; while a process or a seat holds the session, a `joined`
an older copy wrote into it is retired `moved`; and nothing of the
constraint "Nothing is published under a channel id" is sent or written. No
verb creates a channel yet: the tests register one as the org's directory
does.

**Touches:** `S/sminos.py` (the predicate beside `UUID_RE`; `project_kind`;
`known_projects`, new `known_channels` and `known_logs`; `_name_tiers`,
`project_tiers`, `find_project` and the one refusal; `join_refusal`,
`cmd_join`; `_smns_decision`; `view_of`; `lifecycle`; `append_host`;
`cmd_say`, `say_scope`, `_resolve_tag`, `find_target`; `cmd_projects`),
`S/sminos_channels.py` (new: `find_channel`, `register`, `held_channels`,
`opens_unfollowed`), `S/sminos_uplink.py` (`hub_projects`, `Here.project`,
`Link.holds`, new `Link.unfollowed`, `open`, `machine_presence`,
`host_pass`, `relay_requests`, `members`, `tick_passes`, `may_leave`,
`on_snapshots`), `S/sminos_plane.py` (`Plane.refresh`),
`S/sminos_daemon.py` (`tick_all`, and the channel pass of §6 with its
reconciling half alone), `T/test_channels.py` (new), `T/test-channels.sh`
(new), `T/channel_wire.py` and `T/test_channels_wire.py` (new),
`T/run-sminos-tests.sh` (a third part, `channels`), `.github/ci-kit.yml`
(the gate `sminos-channels`).

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
  syncs: a request for a private thread goes under a stream (M4).
- Names: among projects the tiers and their precedence are today's (a hub
  project is found before a machine's of its name, and two of one tier are
  the clash). A channel is in no tier: a name a channel shares with any
  other log, a second channel included, is refused, every log of that name
  listed. The refusal's text is rewritten once (§8), so two projects of one
  tier now read it too.
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
  back (`retire_moved`), as for any ineligible override. That
  reconciliation acts on a session a process or a seat holds: one closed
  before it stays as the older copy left it until it runs again (accepted,
  the composite's C4), and this milestone builds nothing for it.
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
  for it as for any log: an own writer's events there go up in sequence,
  an older copy's `joined` among them, and the `retired` after it.
  `may_leave` reads `unfollowed`.
- What the endpoint asks about a channel is answered as for a log with no
  member: `snapshots?` with one page, empty and done (a channel's log holds
  no session's `joined` or `state` of this code's, and an older copy's is
  no snapshot of a member); a `subscribe` with the `end` a project answers
  for a session it does not hold, which the empty plane gives.
- The daemon ticks no channel as a project: for each channel known here the
  channel pass reads its view (the reconciliation, and nothing published),
  and none of `rejoin_former`, `publish_state`, `publish_titles`,
  `restate_withheld`, `publish_renames`, `deliver_owed`, the mirror sync or
  the archive duty runs for it.
- `chat <channel>` and `list <channel>` are refused by `find_project`'s
  line for a channel (§8): reading a channel's log as a conversation is
  CH2's, with speaking in it.
- The new suites are a third part of `T/run-sminos-tests.sh`
  (`SMINOS_PART=channels`) with a gate of their own, on the four conditions
  agreed with the session that owns CI. The parts stay disjoint:
  `SMINOS_PART=suites` runs no channel suite, `all` runs all three, and the
  runner's own list of parts takes `channels`. The gate's `paths` are its
  siblings' (`sminos/**`, `.github/ci-kit.yml`, `.github/workflows/**`). Its
  timeout is about twice its first measured duration, set again as the part
  grows, not thirty by habit. If the channel suites pass about fifteen
  minutes the part is split again. When the pull request exists the
  executor sends the holder its number, for that session to read the hunk.

**Does not touch:** the thread record, any event kind, `LIFECYCLE`, the
capability list, `member_frame`, `cmd_list`'s output, the guide, the skill.

**Proves:** A8 (the `join` and `.smns` halves), A10, A11 (no channel is
ever the project a verb's target is found in), A12's test of its own, for a
channel that holds no member yet. Its tests pin: `is_channel_id` on every
entry of the shared vectors' `ids`; the kind; each lookup that lists
projects with a channel registered beside them (text and `--json`
unchanged against the same store without it); a hub project and a machine
project of one name with no channel present, found as today; the one
refusal for a name that a channel and a project share, two channels share,
and two projects of one tier share, and `name#short` reaching each; each
refusal of §8 with the logs' files unchanged; the `.smns` rule and the
parity suite still passing; an override naming a channel read as absent
and the running session moved back with a `retired` `moved` in the
channel's log and no `joined` of this code's; a `snapshots?` and a
`subscribe` for a channel id answered as above; and, through the checker
over a real uplink against the stand-in, a first connection, a
reconnection, a channel this machine's records name (staged by writing a
record's `channels` in the test) and one they do not, and a store in which
an older copy's `join` wrote a `joined` under the channel, the baseline
taken before this code reads it. The checker's own tests feed it breaches
and expect each named: a position the baseline holds for one channel
appearing with another event, or under a second channel; a `retired` under
a channel with no older `joined` of that session there; one with a reason
other than `moved`; and each frame of the breach list.

### M2 — A thread's declared set: one durable operation, its statement and the statement's reader

**At its end:** `sminos_threads.set_channels` is the one way a record's
`channels`, `began` and `answered` change (§3). Its record write holds the
whole change, and its entry owes one event, the statement, which `finish`
appends through `lifecycle` in the thread's own project; so a cut after the
record's write is finished by the next reconciliation, this code's or a
1.51.0 or 1.52.0 copy's, with the record as it was written. The write that
puts a thread in a channel records where that membership began (§4), and a
removal drops it. Every reader takes a session's membership from the log by
C2's rule (`Fold.state`, the projection's row, `Member.channels`). There is
no verb yet: `sminos_channels.change` (a thread's own add or remove) drives
it from tests.

**Touches:** `S/sminos_threads.py` (`OPS`, `JOURNALED`, `SEAT_KEYS`,
`_of_seat`, `set_channels`, `update`, `Fold`, `stated_set`), `S/sminos.py`
(`LIFECYCLE`, `_projection`, `Member`, `_member`, what a listing exports of
a seat, new `channel_positions`), `S/sminos_channels.py` (`change`,
`channels_of`, `began_of`, `Outcome`), `T/test_channels_store.py` (new),
`T/test-older-cli.sh` (the 1.52.0 pin and the cut-and-older-finisher
cases), and the two tests of T1 that pin today's form
(`T/test_threads_ended.py`, which calls `set_channels` with a list;
`T/test_threads.py`, which expects `update` to answer false for `channels`
on a held record, where it now raises).

**Interfaces:** exposes §2 (the statement), §3's fields, `set_channels`
and rows C1 and C2, §4, §5's fold and `Member.channels`, §6's `Outcome`.
Consumes T1's journal (`_change`, `finish`'s steps, `open_entries`), T2's
`transition_hold`, and §1.

**Decisions:**

- The operation is `channels` in `OPS`. It takes the thread's wake lock as
  `begin` takes it for every transition, by a bounded poll until its
  deadline, reads and writes the record under it, and lets it go at that
  write. The hold is always its own: where the calling process already
  holds that wake lock (a wake of the thread is under way in it, and a
  reconciliation runs inside), the operation is refused as for any wake in
  flight, since an entry opened there would stand between the wake's check
  and its own record writes. Without it a `resume` that had checked the wake and
  was about to stop a live turn could find its wake refused by an entry
  opened in between, the turn stopped and nothing started; and a launch
  already made could lose the write that records its job and its grace.
  The operation is not a lifecycle write of a seat and does not move its
  generation: a turn's watcher stands down at a generation it did not see,
  and a membership changed during a turn must not cost that turn its reply.
- `set_channels(thread_id, decide)` runs `decide` on a fresh read of the
  record under the store lock, only when the record has not ended and has
  no open entry, and writes what it returns in one write (§3). Everything a
  caller knew before the lock reaches `decide` as what to compare against,
  never as what to write. Where each membership began is not the caller's
  to give: `set_channels` reads it, under the lock, for each channel that
  enters the set.
- The entry owes the statement and nothing else, and `finish` gains no step
  for it: every finisher from 1.51.0 on appends an entry's events and
  clears it, whatever its operation. `T/test-older-cli.sh` proves that on
  each pinned copy and does not take it from this paragraph.
- `channels` joins `LIFECYCLE`, which invalidates the project's view at an
  append and at an import. `_projection` needs a branch of its own for it:
  as the code stands a `LIFECYCLE` kind it does not name falls into the
  last branch and is appended to the row's `status`.
- Where a statement goes is the project in whose log the thread's current
  session is a member at the write, checked under the lock from that
  session's own events there. A thread with no session (a vacant spawned
  thread) or whose session is a member of no project at that moment
  (between the two halves of a move) is not written.
- What cannot be written is said by what can still happen to it. A request
  stays `pending`: it is in the log, and a later pass carries it out. A
  thread's own add or remove has no request, so `change` answers `failed`
  with the reason (the wake lock, an open entry, no session or no project
  now): the command exits 1, says that nothing was recorded and to run it
  again, and no tick ever finishes it.
- A move between the record's write and the statement does not redirect
  the statement: it is appended in the project the entry names, under the
  session's writer there, after that writer's `retired`, where it states
  nothing to a reader of membership; the project the thread moved to gets
  its statement from the reconciliation (M3), and a requester finds the
  answer wherever it lies (§5's answers).
- This code's listings export neither `began` nor `answered`
  (`public_seat`, `member_json`).

**Does not touch:** `_reconcile`, `begin`, `finish`, requests, any verb,
the uplink, `cmd_list`.

**Proves:** A5's stop between the record's write and the statement; A9 for
an own add and removal, and its last clause (an older copy that finishes an
entry this version began leaves the positions as written); the reader half
of A6. Its tests pin: the fold on hand-written logs (a statement before its
writer's `joined`, under another writer than the `joined`'s, after a
`retired`, two statements, one with an empty list, ids that are no
channel's, a 129th id); rows C1 and C2 from `set_channels`, with a `decide`
that is given a record changed between its caller's read and the lock;
`began` after an add into a channel whose log is empty, holds other
writers' events, and already holds events addressed to the thread, and its
absence after a removal; a cut after the record's write, finished by this
code's next reconciliation with exactly one statement; the same cut
finished by each pinned copy's reading verb, after which this code reads
the record's set, positions and answered requests as written and the log
states the set once (1.27.10, which has no journal, finishes nothing, and
this code's next verb does); a cut after the record's write followed by a
`join` to another project, the statement landing in the project left; both
interleavings with a wake, injected (a `resume` paused between its check
and its stop, and a launch paused before it records its job, each with the
operation attempted meanwhile, from another process and from the caller
that holds the wake lock itself), asserting that the operation wrote
nothing, the engine's process count, its launch count, the record's job
and grace, and that the caller's own hold is still live afterwards; a
thread's own change that timed out on the wake lock answering `failed`,
and a quiet tick after it changing nothing; as a statement of the accepted
rule and no guarantee of an order, an event imported into the channel's
log between the positions' read and the record's write ending past `began`;
`update` raising on each of the three keys; and `list --json` holding
neither `began` nor `answered`.

### M3 — The set across a thread's life: the log kept equal to the record, a return, a continuation, an absorption

**At its end:** `_reconcile` notices a thread of this machine whose log
states otherwise than its record and has the operation state the set, so
every reader takes the record's set after a continuation, a refill, a
`join`, a return, a change of reach and a `joined` an older copy wrote. A
return writes anew where each membership began; a continuation carries the
set and its positions untouched; an absorption gives the continuing thread
the absorbed record's channels, their positions and its answered requests;
a session that comes to be another thread's brings none of them.

**Touches:** `S/sminos_threads.py` (`begin` for a return, `finish`'s merge
for an absorption), `S/sminos.py` (`_reconcile`'s last step and the memo it
reads), `S/sminos_channels.py` (`restate`), `T/test_channels_life.py`
(new).

**Interfaces:** exposes §3's rows C5 to C9 and `restate`. Consumes §3's
`set_channels`, §4's `channel_positions`, §5's fold.

**Decisions:**

- The reconciliation is the last step of `_reconcile`, after its own
  appends, so that a `joined` this pass wrote is followed by its statement
  in the same pass. It compares, for each thread of this machine that has
  not ended and has no open entry, whose current session's membership in
  effect in this log is a `joined` of this machine, what the log states (a
  memo beside the merged log, with this pass's appends folded in) with the
  record's set, and on a difference calls `restate` (§3, row C5) with what
  it read. It appends nothing itself. It only tries the wake lock; a busy
  lock (another process's wake, or one under way in this very process), or
  a stream that cannot be chosen, is left to the next pass, as its other
  appends' failures are.
- `restate` is compare-and-state: under the lock the record's set, its
  current session, that session's membership in the project and its writer
  there must each be what the reconciliation read, else nothing is written
  and the next reconciliation notices afresh. So a reconciliation overtaken
  by a removal or a move states nothing.
- A return's positions are written by `begin` for that operation, in its
  record write, for every channel of the set, so that every path that
  returns a thread leaves them without a change of its own. An older copy
  that begins a return itself writes none: the positions stay as they were
  before the end (accepted; the constraint's list).
- The absorption's merge is a write of its own in `finish`, after the
  absorbed record is reserved (nothing writes a reserved record) and before
  the events: the continuing record's set, then the absorbed record's
  channels not in it, up to the limit, an addition past it dropped and said
  in `daemon.log`; `began` kept for the continuing record's own channels
  and taken from the absorbed record for those it brings; `answered`
  united. The statement follows from the reconciliation, since the entry's
  `joined` leaves the log stating nothing. An older finisher skips the
  merge (accepted).

**Does not touch:** requests, any verb, the uplink, `cmd_list`, an end (the
set, its positions and the answered requests stay through one).

**Proves:** A6 but for the roster's own rows (M5); A9's end and return,
continuation, absorption and "a session that became another thread's
brings none"; the absorption's half of A8's limit. Its tests pin, each
through T1's own fixtures for the transition and for both kinds of thread
where both can make it: the reconciliation after a continuation, a refill,
a `join`, a `join` back to a project left with another set, a change of
reach and back, a `joined` an older copy wrote, a return, and a `/clear`
(the thread left keeps its set, the new one states none), every reader
taking the record's set, the empty set included; the reconciliation paused
between its read and its call while the thread is removed from the
channel, and while it moves to another project, stating nothing in either
case; a wake in flight leaving the difference to the next pass; `began`
unchanged by an end, rewritten by the return with the log's positions
then, also over events addressed to the thread while it was ended, and
unchanged by a hand-off and a refill; a former session that runs again as a
thread of its own holding an empty set and no positions; the absorption
with a set on both sides, at the limit, its positions for the channels
brought, its answered requests united, and its replay.

### M4 — Requests on one machine, and the verbs that write them

**At its end:** `sminos channel create <name> [<thread>]`, `sminos channel
add <channel> [<thread>...]` and `sminos channel remove <channel>
[<thread>...]` work on one machine whose endpoint lists `channels`, and are
refused where it does not. A thread adds and removes itself with a
statement alone. Another thread of the machine is named by a request the
command writes into the channel's log and then carries out itself, from
the request in hand; a request left by a command that died is carried out
by the daemon's tick. Each target is told applied, refused with its
reason, or pending and why. What is refused before anything is written is
refused (§8), and the limit binds every path.

**Touches:** `S/sminos_channels.py` (the requests of a log, `judge`,
`carry_out`, `carry_due`, `sender_verified`, `reach_token`, the three
verbs), `S/sminos.py` (`build_parser`, `main`'s usage line for the
family), `S/sminos_daemon.py` (the channel pass calls `carry_due`),
`T/test_channels_requests.py` (new), `T/test-channels.sh`.

**Interfaces:** exposes §2 (the request), §3's rows C3 and C4, §6, §8's
three verbs. Consumes §3's `set_channels`, §5's `channels_of`,
`stream_choice`, `same_owner_local`, `owners_meet`, `policy.read_only`,
`policy.outside_origin`, `audience.advertised`.

**Decisions:**

- One function decides a request, `judge` (§6's table), with no effect; one
  function carries it out, `carry_out`; one pass calls that in the log's
  order, `carry_due`. `carry_out` evaluates `judge` before the lock, to say
  `pending` or `ignored` without taking one, and again whole inside
  `decide`, on a fresh read: the outcome is the second one's. The command,
  the daemon's tick and (M7) the uplink at an answer are the pass's
  callers.
- The earlier requests and the expiry are those of the last read before
  the record's write: `decide` compares the signature of the log's files
  and of this machine's queued appends for it (the one the read is kept
  by) with the one `earlier` was read under, and a difference writes
  nothing; `carry_out` then reads again and tries again, three times in
  one call, and past that says `pending`. That bounds what one call acts
  on. It holds no log still: a request imported after the last read is
  carried out as one that arrived later (the constraints' accepted list).
- The ordered input of a carrying out is the channel's log as merged and
  then this machine's queued appends for that log, in the queue's order: a
  second terminal's command sees the first one's queued request ahead of
  its own, and waits behind it.
- A word is bound to the event it was asked about, as the reach path binds
  a permit: the request's log, writer, position and event hash. The
  `answered` ledger stays keyed by channel and id. A request whose id an
  earlier request of that log under another writer already used is not
  carried out, and `channel show` says so: a second writer cannot ride on
  the first one's answer or its word.
- The second evaluation is fresh in fact, not a second look at this
  process's caches (§3): the records by `current_record(..., fresh=True)`,
  what `outside_origin` and the same-owner case rest on read from their
  files then, and a session's existing writer files read by a path that
  takes no lock and writes nothing.
- A word of the endpoint's, `deliver` or `refuse`, is bound to the thread
  it was asked for before it is read as a verdict: if the thread's current
  session or its reach is no longer what the question was put for, the
  word is dropped and the request asked about again (M7 builds the asking;
  this milestone proves the table with words handed in).
- A command carries out the request it just wrote from the event in hand,
  as `log_append` returned it, and does not depend on finding it in the
  merged log: an operator's append to a log this machine has just
  registered can be queued with no position yet (`waits_for_head`). It is
  then in the queue, which the ordered input reads, behind whatever was
  queued before it. When the queued event later reaches the log the record
  already holds its answer.
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
- `channel create` checks, before it registers anything, the capability,
  the name, the first member and the limit. It refuses a name a log known
  on this machine already answers to, naming it, with one exception: a
  channel of that name registered here that has no member as this machine
  can tell (no record of this machine names it, and the org's directory it
  keeps does not list it) is brought back under its id, whether its
  creation was interrupted or its last member left, and the command says
  so (§8). That is what "it returns when a member does" means for a name.
  Otherwise it mints the id (again if the machine knows it), registers
  the channel, and places the first member by the same paths as `add`. A
  session's own first membership that cannot be recorded is a failure as
  any own change is (M2): the channel stays registered with no member,
  and the same command run again brings it back.
- A request that names no thread of this machine as §6's third row reads
  it (not this machine's, ended, a session it never had, a session that is
  now another thread's, lane B) gets no statement here and expires: a
  statement is written under a thread's writer, and no thread here is the
  one named.

**Does not touch:** the uplink, the capability list, `cmd_list`,
`channel show`, `channel env`.

**Proves:** A1; A4's cases at the function (the same owner on one machine;
a verified sender with each word; an unverified sender; no word yet; an
endpoint without `channels`); A5 but its last clause on the path (M7); A8's
capability and limit halves; A9 for a request's add and removal. Its tests
pin every row of §6's table, each also with the fact it reads changed
between the first evaluation and the lock (the owners, the policy, the
revocation set, the capability); a word of each kind, `deliver` and
`refuse`, handed in for a session and for a reach the thread no longer
has, neither recorded; a request of a second writer under an id the first
writer's request already used, arriving while the first one's question is
outstanding, not carried out and not given that word; the facts the
second evaluation reads (the owners, the policy, the revocation set, the
capability, the machine's identity, the session's membership) changed by
another process after this one's caches were warmed and with no
`forget_caches` in between, and on a stream whose writer file this
process never read, the fresh value deciding and nothing locked or
written by the read; an earlier-sorting request imported while a carrier
is paused after its read, the later one not carried out ahead of it, and,
as a statement of the accepted rule, one imported between the last read
and the record's write carried out as a later arrival; two terminals'
requests for one thread both queued, the first command cut after its
append, the second waiting behind it, and the membership after the queue
drains; an
add then a remove of one thread in one channel, and the reverse, with each
carried by the command or by the tick and the words handed over in either
order; two requests in two channels answered once each by the statement
naming its channel and id; a request read twice, and again after the
thread changed session, project and reach, and after its record was
absorbed; a request behind an open entry, and behind a wake in flight; five
requests for one thread from two requesters; an operator's request queued
for its writer's head, carried out by the command and not again when it
reaches the log; `create` cut after its registration and run again, and
`create` of a name whose channel was emptied, each bringing the channel
back under its id with the line §8 gives; a session's `create` whose first
membership could not be recorded exiting 1; the
limit at `create` (before registration), at `add` for oneself, at `add`
for another (a refusing statement), and with two adds for the 128th place;
each refusal before writing, `remove` without the capability among them,
with every log unchanged; a request whose `session` is another thread's
current one changing neither; and no session's turn started by any of it.

### M5 — The roster, the listing and the pool

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

**Touches:** `S/sminos_channels.py` (`rosters`, `roster`, `answers`,
`answer_of`, the requests as shown, `pool`, `show`, `env`), `S/sminos.py`
(`cmd_list`, `list_scope`, the parser's `--channel`, `member_json`, the
module docstring that is `help`), `sminos/hooks/mods/backticks.tsx`
(`VERBS`), `T/mods/backticks.test.ts`, `T/test-channels.sh`,
`T/test_channels.py`.

**Interfaces:** exposes §5's roster and answers (Y1), §2's `channel-env`,
§8's listing. Consumes §2, §5's `Member.channels`, §6's reading of
requests.

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
- What became of a request is read from an index of its own, not from the
  fold that reads membership: every `channels` event that carries
  `answers`, in any project's log this machine reads, whatever statement is
  in effect there now and whatever project the thread has since moved to;
  an answer is a request's only when its `thread` stamp is the request's
  `thread` and its writer's session is one that thread has had, as this
  reader can tell (§5): the stamp alone is a field any writer can set. A
  request whose id another writer's earlier request used reads `not
  carried out` (§6's `duplicate`). A request with no answer is pending,
  with the machine the
  target's row was last seen on and the request's age (the hub's
  withholding is M7's reader). A request older than seven days by its own
  timestamp is not shown, answered or not.
- `channel env` is refused, before anything is written, without the
  capability, from a terminal, and from a thread that is not in the
  channel: no reader would honour the event. The machine named must be one
  the org's directory lists.
- A `channel-env` event carries its writer's thread id (§2) and is honoured
  when the roster, as it is read, holds a row for that thread that lists
  the writer's session among the sessions it has had; an association the
  reader cannot make is not honoured. The last honoured event by merge
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
projects and each of applied, refused and pending; the answers index with
several requests for one target, an answer followed by a restatement, an
answer left in a project the thread then moved from, an unrelated
thread's statement naming the same channel and id, and a statement with
the request's thread stamp under a writer that thread never had, neither
taken; a request shown as not carried out for its reused id; the pool's
counts, a machine added and removed by hand, an env event from a writer no
longer in the roster, one whose thread id is another thread's, and one
with none, each ignored; `channel env` without the capability refused
with nothing appended to any log; the guard refusing a `sminos channel …`
call that holds a live backtick.

### M6 — The wire: the capability, `member.channels`, opening without `follow`, MAWS's fixture

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

### M7 — Requests across machines: the endpoint's word, and what a requester is told

**At its end:** a request written on one machine for a thread of another
is uploaded, reaches the target's machine, and is carried out there when
the endpoint answers `deliver` for a verified sender, with no turn of any
session. The requester's `channel show` reads applied, refused with its
reason, refused as not reachable when the hub withheld the request, or
pending with the target's machine and since when; after seven days it reads
nothing, and a request that arrives that old is not carried out.

**Touches:** `S/sminos_uplink.py` (the request source of the ask pass,
`on_reach`, the asks held), `S/sminos_channels.py` (`ask_of`, the withheld
reading in what `channel show` prints), `S/sminos_hublog.py` (a read of a
project's withheld positions for the CLI), `T/test_channels_wire.py`,
`T/test-channels-machines.sh`.

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
  time for a request. An ask is held under the event it asks about
  (`event_key`: the channel, the request's writer, position and event
  hash, as a reach permit is keyed), with what it was put for: the session
  and its reach (`reach_token`). `on_reach` hands an answer for such an
  ask, whichever word it is, to `carry_due` under that key and with that
  binding, so a word answers the event it was asked about and no other
  request, whatever id that other carries; a word whose
  binding no longer holds under the lock is recorded as nothing, and the
  request is asked about again at the next pass. An answer past
  `REACH_WAIT` is none, and the request is asked again, with no count and
  no bound.
- An import of a channel's log nudges the daemon and marks the ask pass
  due, as an import does today, so a request is carried out within a tick
  of its arrival.
- The requester's machine reads "the hub withheld it" from the withheld
  positions its uplink keeps for the channel's log (`uplink.json`), by a
  read that takes no lock and changes nothing; `channel show` gains that
  state here, with its proof.

**Does not touch:** `deliver_reach` and the message asks (their keys,
their hold filter, their counts stay), the fixture, `cmd_list`.

**Proves:** A3; A4 on the path (a verified sender the endpoint delivers
for; a sender it refuses; an unverified sender it would deliver words for,
refused by sminos; no answer, pending; an endpoint without `channels`,
pending); A5's last clause; A1's "placed on another machine when its daemon
runs". Its tests pin: one ask per due request and none for one that needs
no word; an answer used once; a `deliver` and a `refuse` each arriving
after the thread's hand-off, and after a change of its reach, neither
recorded and each leading to a second ask; a second writer's request
under the same id imported while the first one's question is outstanding,
the answer then carrying out the first alone; two requests for one thread and
channel asked one at a time in order; a stopped thread placed with no
launch recorded by the test engine; each outcome at the requester on two
machines, the withheld one staged by the stand-in refusing the upload
`not-reachable`; an expired request relayed late; the roster on both
machines; and the checker over both stand-ins.

### M8 — Older copies, what is written beside the code, the version, and the acceptance

**At its end:** `T/test-older-cli.sh` runs 1.27.10, 1.51.0 and 1.52.0
beside this code over a store that holds statements, a thread in channels,
a registered channel and a `channel-env` event; `S/CLAUDE.md`, which each
milestone added to, has been read whole against the tree;
`docs/doperpowers/TECH-DEBT.md` holds what this child accepts; sminos is
1.53.0; and the acceptance has been run as Concrete Steps gives it, the
narrow check on a real engine included.

**Touches:** `T/test-older-cli.sh`, `sminos/skills/sminos/scripts/CLAUDE.md`,
`sminos/CLAUDE.md` (one sentence naming the channel family and where its
detail is), `docs/doperpowers/TECH-DEBT.md`, the files
`scripts/bump-version.sh --plugin sminos` writes.

**Interfaces:** consumes everything; exposes nothing new.

**Decisions:**

- The older-copy suite's machines are not enrolled, so `channel create` is
  refused on them: the store is staged through this code's own functions
  (`sminos_channels.register`, `change`, and a `channel-env` and a
  `channel-request` appended as the verbs append them), and each older copy
  then runs its verbs over it. 1.52.0 is pinned, since M2, as the merge
  that released it (`f051d4f2a28615d7b3517963aed0ac68233435fb`), fetched as
  the other two are.
- Per version, asserted: each copy's `list`, `list --json`, a tagged `say`
  and a `send` to the thread in channels, and its `daemon tick`, do what
  they did over the same store without channels (the every-copy
  expectations and each version's own, unchanged); the record's
  `channels`, `began` and `answered` are what they were after each; a
  `joined` the copy writes for the session is followed, at this code's next
  reconciliation, by a statement of the same set; the copy lists the
  registered channel as a project with no member and this code still lists
  it as none. Accepted and asserted as it is: a 1.51.0 or 1.52.0 copy's
  `list --json` hides a spawned thread's `channels`, which it knows, and
  shows its `began` and `answered`, which it does not; a return such a
  copy begins leaves `began` as it was before the end.
- Then, for each copy: its `join <channel id>` by hand from a running
  session, after which this code's next reconciliation leaves the session a
  member of its one project with its set as it was and a `retired` `moved`
  in the channel's log; the same with the session closed before that
  reconciliation, listed in neither until it runs again, then recovered;
  and the checker, baselined on the store as the older copy left it, clean
  over an uplink run on it: the older copy's `joined` uploaded in its
  place, then this code's `retired`, and nothing else of this code's.
- TECH-DEBT rows, each with what would promote it: the composite's
  accepted list (the constraint above); `chat <channel>` and a target
  qualified by a channel are refused until CH2.
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
    python3 -B sminos/tests/test_channels_life.py
    python3 -B sminos/tests/test_channels_requests.py
    python3 -B sminos/tests/test_channels_wire.py
    bash sminos/tests/test-channels.sh
    bash sminos/tests/test-channels-machines.sh
    bash sminos/tests/test-older-cli.sh
    python3 -B sminos/tests/rl10_conformance.py sminos/skills/sminos/scripts sminos/tests/rl10-conversation.json

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. A shell file ends with its counts of passed and
failed and exits non-zero on any failure. The replay prints one `ok` or
`FAIL` line per line of the conversation it plays; from M6 on it prints no
`amend` line.

**At each milestone's end, and before the frontier review,** the gates, on
the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,sminos-channels,sminos-idle,sminos-mods,shell-lint,repo-checks

with `mods-types` from M5 on (the guard mod changes) and `version-bump` in
M8. Expected: one `PASS` line per gate, then `GREEN` and the run's address.
A `FAIL` that the base also shows, or one a recorded reason names, is not
this change's; any other is diagnosed, not run again. Each milestone's
report gives the `sminos-channels` gate's duration; its timeout in
`.github/ci-kit.yml` is kept at about twice that.

**The proof map.** Where each acceptance item of CH1's section is proved.
A1 to A14 number its items in the order the section lists them.

| Item | Proved in (milestone: file) |
|---|---|
| A1 create, add, remove; with none named, the caller; placed when the command returns but for its waits; refused before writing | M4: `test-channels.sh` (the verbs), `test_channels_requests.py` (an earlier request, an open entry, a wake in flight); M7: `test-channels-machines.sh` (another machine) |
| A2 `list`, `--channel`, `channel show`, `channel env` and the pool's counts | M5: `test-channels.sh`, `test_channels.py` |
| A3 across two machines: pending with the machine and since when, carried out by that machine's daemon, the roster on both; each outcome where it can be known | M7: `test-channels-machines.sh` |
| A4 who may ask, case by case | M4: `test_channels_requests.py` (every row of §6, before and under the lock); M7: `test_channels_wire.py` and `test-channels-machines.sh` (the path) |
| A5 order and identity | M4: `test_channels_requests.py`; M2: `test_channels_store.py` (the stop between two writes); M3: `test_channels_life.py` (the absorbed record's answers); M7: `test_channels_wire.py` (asked about again, for either word) |
| A6 membership as others read it | M2: `test_channels_store.py` (the reader); M3: `test_channels_life.py` (every reader takes the record's set; the reconciliation overtaken; `/clear`); M5: `test-channels.sh` (private, ended, reopened, in the roster) |
| A7 a remove does not retire; `known` for two holders and a follower; the last member; `list --org`; a return | M6: `test-channels-machines.sh`; M5: `test-channels.sh` (`list --org` on one machine) |
| A8 `join`, `.smns`, the capability, the 129th | M1: `test-channels.sh`, `test_channels.py`; M4: `test-channels.sh`, `test_channels_requests.py`; M3: `test_channels_life.py` (an absorption) |
| A9 where a membership began | M2: `test_channels_store.py` (an add, a removal), `test-older-cli.sh` (an older finisher leaves it); M3: `test_channels_life.py` (an end and a return, a continuation, an absorption, a session that became another thread's); M4: `test_channels_requests.py` (a request's add and removal) |
| A10 nothing is said into a channel | M1: `test-channels.sh` (from a session and from a terminal) |
| A11 a verb's fact goes to the thread's own project | M1: `test-channels.sh` (`charge`, `status`, `retire` naming a thread by its short, its id, `alias#short` and a channel-qualified name; M4 runs it again with the thread in a channel) |
| A12 the wire | M6: `rl10_conformance.py`, `test_channels_wire.py`; M1: `test_channels_wire.py` (the checker before any member) |
| A13 parent line 8 for this surface | every gate at every milestone; M1: `test_channels.py` (two projects of one name); M5: the listing compared with the merge base's; M6: the frames of a thread in no channel compared with the old fixture's |
| A14 older copies | M8: `test-older-cli.sh`; M2: `test-older-cli.sh` (the entry an older copy finishes) |

**M8, the acceptance.** The gates GREEN on the final head; then the scene,
which M7 builds as the last case of `T/test-channels-machines.sh` and which
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
   three stores, and no delivery record exists under the channel's log on
   any of them.

**M8, the check on a real engine.** In a scratch tree `<scratch>`:
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
   ticks: one row for A's thread in `# probe`, under the job's session id,
   one statement of that set under the job's writer in A's project log,
   and the record's positions for `probe` as they were before the
   hand-off.

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
        # as today over known_logs(), with two changes. `<name>#<short>` (short: the first hex digits of an id,
        # eight or more) names the logs of that name whose id begins with it. And a channel is in no tier: when
        # a channel is among the logs a name answers and is not the only one, every one of them is the clash.
        # Among projects alone the tiers, their order and their clash are today's
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
| `channels` (the statement) | the thread's own project; the thread's current session's writer, as `lifecycle` chooses it (its plain writer, or its audience stream) | `session`: the writer's own session, and no other; `thread`; `op`: the journal entry's id; `channels`: the whole set, a list of channel ids in the order added, `[]` for none. When it answers a request: `answers`: `{"channel": <id>, "id": <the request's id>}`, `result`: `"applied"` or `"refused"`, and with `refused` `reason`: `"not-reachable"`, `"read-only"` or `"limit"`. A refusal carries the set unchanged. Never a position of a channel's log |
| `channel-request` | the channel's log; the requester's writer there: for a session, the stream `stream_choice` gives for the target as its one recipient; for a person at a terminal, the machine's human writer or its stream by the same choice | `op`: `"add"` or `"remove"`; `session`: the target thread's current session as the requester reads it; `thread`: the target's thread id; `id`: `uuid.uuid4().hex`, minted for this request. Nothing else, and never `to` |
| `channel-env` | the channel's log; the writing thread's own stream there (`own_stream`) | `op`: `"add"` or `"remove"`; `machine`: a machine's name as the org's directory lists it; `thread`: the writer's own thread id |

A reader takes a field of the wrong type as absent, and an event missing a
required field as no event of its kind. A request's `op` is the request's
verb and has nothing to do with the journal's `op` on a lifecycle event;
the field's name is C2's. `channel-env` names its writer's thread because
a session id can come to be another thread's, and the writer's session
alone would let that thread's membership honour an event it never wrote.

### §3. The record and its operation (X1, Y3)

In `S/sminos_threads.py`. Three keys of the record, all of the thread and
kept across its occupants and an end:

| Field | Type | Meaning |
|---|---|---|
| `channels` | list of strings | the set (T1's field; `[]` when made) |
| `began` | object, `{channel id: {writer: seq}}`, or absent for an empty set | where each membership began (§4): for every channel of the set, and for no other |
| `answered` | list of `[channel id, request id, the request's ts]`, or absent | the requests this thread has answered, oldest first. An entry whose `ts` is older than the request lifetime (§6) is dropped by the next write of the operation: such a request can no longer be pending |

All three are read for either store's record (`_of_seat` gives a seat's).
This code's listings export neither `began` nor `answered`. Adoption and
the making of a record write `channels: []` themselves, not through
`update`, and keep doing so.

    OPS = (..., "channels")
    JOURNALED = (..., "channels", "began", "answered")     # update() raises on any of them
    SEAT_KEYS = (..., "began", "answered")
    CHANNEL_LIMIT = 128

    def set_channels(thread_id, decide, lock_until=None, wake_until=None) -> dict | None
        # (M3: `wake_until`, when given, bounds the wake lock's poll alone, so a reconciliation only tries it
        # while it still waits its turn at the store lock up to `lock_until`)
        # The one way a thread's set, where its memberships began, its answered requests or a statement is
        # written. Takes the thread's wake lock as begin() does for a transition (sminos.wake_lock, a bounded
        # poll until `lock_until`, SWEEP_WAIT from now by default), and lets it go once the record is written;
        # WakeBusy, nothing written, when a wake holds it past that or this process holds it already (a wake of
        # the thread under way here: the hold is never a caller's). Under the record's store lock, on a fresh read,
        # when the record has not ended and has no open entry: decide(record) answers None (nothing is written)
        # or a Change, and the Change is written in one write with its entry. Returns the entry as written,
        # None when nothing was. Does not move a seat's generation.
        #
        # Change = {"project": Project,       # the thread's own project: where the statement goes
        #           "session": str,           # the record's current session, which the statement is written under
        #           "channels": list[str],    # the set after the change (the same list for a refusal or a restatement)
        #           "answer": {"channel", "id", "ts", "result", "reason"} | None}
        #
        # In that write `began` gains, for each channel entering the set, sminos.channel_positions(id) as read
        # just before it, under the lock, and loses each channel leaving it; no caller gives a position. No
        # lock holds the channel's log still: what is imported after that read counts as gained after it. A Change whose session is not the
        # record's current one, or whose `channels` holds more than CHANNEL_LIMIT ids or an id that is no
        # channel's, is a caller's error (ValueError), never written.

`decide` runs while the record's store lock is held, and for a spawned
thread that is the lock every seat's write waits on. It reads the record it
is given, other records by `get` and `current_record(..., fresh=True)`, a
session's own writer files in one project, the signature of a channel's
log files and of its queue, a session's record, the machine's identity and
enrollment, the policy, the kept capabilities and the revocation set, and
nothing else. Each of those reads is fresh in fact: from its file as it is
then, never from a value this process cached for its invocation, since
nothing forgets those caches between a caller's first read and the lock.
And each takes no lock and writes nothing: the writer files are read as
existing files (no project registered, no directory made, no stream
kept), a file that is not there reading as none. It never reads a view, a
roster or a target (`view_of`, `members`, `find_target`): each of those
reconciles, and a reconciliation takes store locks this process then
already holds.

The entry, which owes the statement and nothing else:

    "pending": {"id": <minted>, "op": "channels", "at": <timestamp>, "project": <the Change's project's id>,
                "events": [<the statement of §2, whole>]}

`finish` carries it as it carries any entry (T1 §6, step 2): the statement
is appended through `lifecycle` under the entry's id, skipped when the
session's own events in that project hold a `channels` with that `op`, and
the entry is cleared. It gains no step for this operation, so a finisher of
1.51.0 or 1.52.0 carries the entry to the same end. Before `set_channels`
a caller finishes the record's open entry with no wake lock held, as
`thread_transition` does.

**The transitions.** Each row's write is its linearization point; "the
lock" is the record's store lock, taken under the thread's wake lock.

| # | What happens | Read under the lock (else nothing is written) | The record's write | The statement owed |
|---|---|---|---|---|
| C1 | a thread adds itself (`channel add <c>`, `channel create`) | its current session is the caller's; that session is a member of the project; the set lacks `c` and holds fewer than 128 | `channels` with `c` appended; `began[c]` the log's positions now | the new set |
| C2 | a thread removes itself | as C1, and the set holds `c` | `channels` without `c`; `began[c]` dropped | the new set |
| C3 | a request is honoured | §6's table, whole, again; the session a member of the project | as C1 or C2 (nothing of the set or of `began` when it already reads so); `answered` gains the request | the set, with `answers` and `result` `applied` |
| C4 | a request is refused | §6's table, whole, again; the session a member of the project | `answered` gains the request | the set unchanged, with `answers`, `result` `refused` and `reason` |
| C5 | the log states otherwise than the record (the reconciliation) | the set, the current session, that session a member of the project the difference was read in, and its writer there (`own_stream`), each as the reconciliation read it | none but the entry | the set |
| C6 | an end (T1 §6, rows 9 to 11 and 13) | T1's | T1's; the three keys untouched | T1's `retired` |
| C7 | a return (row 12) | T1's | T1's, and in that write `began` written anew for every channel of the set, the log's positions now | T1's `joined`; C5 follows at the next reconciliation |
| C8 | a continuation or a refill (rows 4 and 6) | T1's | T1's; the three keys untouched | T1's; C5 follows, the new session's `joined` leaving the log stating nothing |
| C9 | an absorption (row 5) | T1's, and the absorbed record reserved | `channels`: its own, then the absorbed record's that it lacks, up to 128; `began`: its own kept, the absorbed record's for each channel brought; `answered`: both, one entry per request | T1's; C5 follows |

A thread in no channel that has never been in one has no statement and
needs none. C1 and C2 on a set that already reads so write nothing and say
so. A former session of a thread that runs again as a thread of its own
(T1's row 15) is a new record: an empty set, no positions, nothing
answered. After any row the caller nudges the daemon, so the uplink sees
the record within a scan.

In `S/sminos_channels.py`, the callers that build `decide`:

    def change(thread_id, channel, op, session, lock_until=None) -> Outcome
        # C1, C2 (§6's Outcome): `applied`; `refused` `limit` for an add past 128, nothing written; or
        # `failed` with why it could not be recorded (`wake`, `entry`, `vacant`, `between`, `moved`: the
        # session is no longer the thread's current one, or the record ended or is gone; `unreadable`: the
        # channel's log or a writer file of it is there and could not be read); never `pending`,
        # since no request exists for a later pass to carry out
    def restate(project, thread_id, session, writer, seen, appended=None) -> bool
        # (M3: `appended`, this pass's own appends; restate finishes its own entry, so the statement shows in
        # the same pass)
        # C5: `seen` the set the reconciliation read from the record. Only tries the wake lock. True when a
        # statement was owed and its entry begun; a failure to finish it is the next reconciliation's

**The lock of each writer this child adds.**

| What is written | By | Under |
|---|---|---|
| the record's `channels`, `began`, `answered` and the entry | `set_channels`, called by a command, the daemon's tick, the uplink at an answer, and a reconciliation in any process | the thread's wake lock (its own hold: waited for by a command, only tried by a pass and a reconciliation, refused where the process holds it already), then the record's store lock (`.metalock` for a spawned thread's, `threads/.lock` for a human-opened one's), one write; refused while an entry is open |
| `began` at a return | `begin`, as it writes the return (T1) | as every return: the wake lock, then the store lock, in the return's own write |
| the merge of an absorption | `finish`, for the entry that absorbs | the absorbing record's finisher lock, then its store lock, one write, after the absorbed record is reserved; both records' wake locks were held where the absorption began (T1) |
| the statement | `finish`, through `lifecycle`, whoever calls it | the record's finisher lock, then the writer file's lock, with the guard that the log holds none under the entry's id |
| a request, a `channel-env` event | the command, by `log_append` under its caller's own writer in the channel's log | that writer file's lock alone |
| a channel's registration | `channel create`, and `keep_org` as today | `register_if_absent`'s own lock |
| the asks held for requests | the uplink | one process, its main thread |

### §4. Where a membership began (Y3)

In `S/sminos.py`:

    def channel_positions(channel_id) -> {writer: seq}
        # every writer's latest seq in the channel's log as this machine holds it now; {} for a log that holds
        # nothing, and for a channel not registered here. Read with no lock: by set_channels for a channel
        # entering a set, by begin for a return, each under the record's lock

In `S/sminos_channels.py`:

    def began_of(thread_id, channel_id) -> dict | None
        # the record's positions for that channel; None when the thread is not in it. An entry the record lacks
        # for a channel of its set (which this code never leaves) reads as {}: nothing was held then

The positions are the thread's: they are in its record alone, a
continuation and a refill leave them as they are, an absorption brings the
absorbed record's for the channels it brings, a return writes them anew,
and a removal drops them. They are never written into a log or a frame:
they name the channel's other writers, and a statement is read by everyone
who may read the thread. This child reads them nowhere but in tests; CH2
owes a thread, in a channel, only what the log holds past them, and
settles what it pushed or dropped in the thread's delivery records, which
this child never opens for a channel.

### §5. Reading membership and answers (Y1)

**What the log states.** In `S/sminos_threads.py`, beside the reducer:

    class Fold:                       # gains the slot `stated`: {session: its statement in effect}
        def state(self, session, event) -> None
            # folds one own `channels` event of `session`: it is the session's statement in effect when its
            # writer is the writer of the session's latest `joined` (self.joined) and its seq is above that
            # `joined`'s; any other is none. add() of a `joined` clears the session's statement, and a
            # `retired` in effect for that writer ends it: no statement is in effect without its `joined`
    def stated_set(event) -> tuple
        # a statement's `channels` as a reader takes them: its strings that pass is_channel_id, in order, each
        # once, the first 128; () for no statement

Every reader of what a log states folds through `Fold.state`: `_projection`
(the row's `stated`) and the memo `_reconcile` reads. `Member.channels` (a
tuple, `()` by default) is `stated_set` of its row's statement: what every
machine that may read the thread's writer takes as its membership.

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

**A request's answer** is read from an index of its own, never from the
fold above, which keeps only the statement in effect:

    def answers() -> {(channel id, request id): [statement, ...]}
        # every `channels` event that carries a well-formed `answers`, in every project's log this machine reads
        # (sminos.known_projects), in the merged read's order, whatever is in effect there now; kept beside each
        # merged log and for the cache generation
    def answer_of(channel, request) -> dict | None
        # (M5: `channel` is passed, since a request event does not carry its channel's id)
        # the first of answers() for its channel and id whose `thread` stamp is the request's `thread` and whose
        # writer's session is one that thread has had, as this reader can tell: a session its row lists (its
        # current one, those it continues, its thread's others), or one whose own `joined` in the log the
        # statement lies in is stamped with that thread, a project the thread has since left included. None
        # for none this reader may read

So an answer still answers after the thread restated its set, moved to
another project or changed writer; a statement of another thread that
names the same channel and id answers nothing; and neither does one that
carries the right stamp under a writer the thread never had.

### §6. Requests and their carrying out

In `S/sminos_channels.py`:

    REQUEST_TTL = 7 * 86400       # seconds a request can be pending, by its own ts; SMINOS_CHANNEL_REQUEST_TTL
    REASONS = ("not-reachable", "read-only", "limit")
    class Outcome(NamedTuple):
        state: str                # "applied" | "refused" | "pending" | "ignored" | "failed"
        why: str                  # refused: one of REASONS; pending, ignored and failed: a word of the tables
                                  # below; applied: "unchanged" when the set already read so, "" else
    def requests_of(channel) -> (signature, list[dict])
        # the ordered input: the log's `channel-request` events of §2's shape in the merged read's order, then
        # those among this machine's queued appends for that log, in the queue's order (seq None, read without
        # changing the queue); with the signature of the files both were read under
    def event_key(channel, request) -> tuple
        # (the channel's id, the request's writer, its seq, its event hash): what a word is asked and kept under
    def expired(request, now=None) -> bool        # its ts is unreadable or older than REQUEST_TTL
    def sender_verified(channel, request) -> True | False | None
        # True for a writer of this machine in a log where its name is provenance (own_writers_here). Else from the
        # key an import stores on the event, `verified`: False when it is no object or its signer's kind is
        # `legacy`; None while the revocation set cannot be read; False when the set names the signer; else True
    def reach_token(session) -> tuple | None
        # the session's record's owners with its access, shares and policyRev (sminos_audience.policy_of); None
        # while the record cannot be read
    def judge(channel, request, record, earlier, word=None, asked=None, *, project=None, now=None, facts=None) -> Outcome
        # (M4: `project` chosen before the lock and never looked up under it; `now` for the expiry; `facts`
        # the evaluation's fresh reader)
        # the table below and nothing else: reads, no write, no lock. `record`: the target's, as its caller read
        # it. `earlier`: the requests of the ordered input before this one. `word`: the endpoint's ("deliver" |
        # "refuse" | None), the one kept under this request's event_key and no other. `asked`: {"session",
        # "reach"} the word was asked for. "applied" and "refused" are what a write would record; nothing has
        # been written
    def carry_out(channel, request, word=None, asked=None, lock_until=None, wake_until=None) -> Outcome
        # one request: judge() on what it reads, then, when that says a statement is owed, set_channels with a
        # decide that runs judge() again on the record it is given and on fresh reads, and writes that second
        # answer or nothing. An input whose signature moved since `earlier` was read is read again, three
        # times in the call, then pending `moved`
    def ask_of(request) -> dict | None
        # what the endpoint is asked about a request left pending `endpoint`, read now: {"key": its event_key,
        # "thread", "session": the thread's current session, "project": the thread's own project, "reach":
        # reach_token(session)}; None when row 3 or 7 holds, or the record cannot be read
    def carry_due(channel, words=None, also=(), lock_until=None, wake_until=None) -> list[(dict, Outcome)]
        # (M4: the daemon passes `wake_until` now, so it only tries the wake lock; a command waits SWEEP_WAIT)
        # the pass: every request of the ordered input that is not expired and names a thread of this machine,
        # in order, then the requests of `also` it does not hold (a command's own, in hand), each through
        # carry_out; a request pending leaves the later ones for its thread pending `earlier`.
        # `words`: {event_key: (word, asked)}

`judge` answers by the first row that holds. T is the record whose id is
the request's `thread`.

| # | What is read | Outcome |
|---|---|---|
| 1 | the request is expired | ignored `expired` |
| 2 | a request among `earlier` under another writer carries this request's `id` | ignored `duplicate`: not carried out, and `channel show` says so |
| 3 | T is no record of this machine, or has ended, or never had the request's `session`, or that session is now another record's current one, or T's session is lane B | ignored `not-here`: nothing is written for either thread, and the request expires |
| 4 | T's `answered` holds the request's channel and id | ignored `answered` |
| 5 | a request among `earlier` for the same thread is not expired, passes rows 2 and 3, and is not in T's `answered` | pending `earlier` |
| 6 | T has an open entry | pending `entry` |
| 7 | T holds no session; or its session is a member of no project now | pending `vacant`; pending `between` |
| 8 | the request is from elsewhere (`policy.outside_origin`) and the kept welcome lists no `channels` | pending `no-channels` |
| 9 | the request is from elsewhere and the machine admits nothing from outside (`policy.read_only`) | refused `read-only` |
| 10 | its writer is this machine's own and shares the thread's owners: a session's writer by `same_owner_local`, the human writer by `owners_meet("", session)` | honoured |
| 11 | `sender_verified` is False; is None | refused `not-reachable`; pending `unverifiable` |
| 12 | no word for this event | pending `endpoint` |
| 13 | a word, either one, and T's current session or its `reach_token` is not what `asked` holds | pending `moved`: the word is dropped and the request asked about again |
| 14 | the word is `refuse` | refused `not-reachable` |
| 15 | the word is `deliver` | honoured |

Honoured: an add of a channel the set lacks while it holds 128 is refused
`limit`; anything else is applied. Before `set_channels`, `carry_out`
finishes T's open entry if it can (row 6 is what is left). A wake lock
that cannot be had (a wake holds it past the caller's wait, or the calling
process holds it) is `pending` `wake`, with nothing written. Under the
lock `decide` runs the whole table again, on reads that are fresh in fact
(§3), with `earlier` taken as read only if the input's signature is the
one it was read under: what it then answers is what is written, and an
answer that is no longer `applied` or `refused` writes nothing and is the
outcome. That is the last read before the record's write; what is
imported after it is a later arrival. Requests for different channels are
not ordered against each other.

The pass's three callers: the command, for each request it wrote for a
thread of its own machine (handed in as `also`, no words); the daemon's
tick, for every channel known here, after the channel's reconciliation;
the uplink, at each ask pass and at each answer (M7), which asks about
what the pass left pending `endpoint`.

The words a command and `channel show` print:

| | Words |
|---|---|
| `not-reachable` | its machine does not let you message it |
| `read-only` | its machine admits nothing from outside |
| `limit` | it is in 128 channels, the limit |
| `duplicate` | not carried out: another request in this channel used its id first |
| `earlier` | behind an earlier request for it in this channel |
| `entry` | its record holds an unfinished operation |
| `wake` | it is being woken; its machine's next pass carries this out |
| `vacant`, `between` | the thread holds no session now; its session is between two projects |
| `no-channels` | its machine's endpoint does not serve channels |
| `unverifiable` | its machine cannot read its revocation set |
| `endpoint` | its machine's endpoint has not said whether you may message it |
| `moved` | its session, its reach or the channel's log changed while its machine decided: tried again |
| `failed` (a thread's own change) | nothing was recorded (`<the pending word for why>`): run the command again |

On another machine a requester reads none of the pending words: it reads
`pending on <machine> since <time>`, which covers a machine that is off, one
whose sminos or MAWS predates channels, and an answer it may not read.

### §7. The wire (X5)

In `S/sminos_rl10.py`: `CAPABILITIES = ("audience", "record", "locations",
"channels")`, in that order (the fixture's hello).

In `S/sminos_uplink.py`:

    Link.serves_channels: bool               # the welcome listed `channels` (welcomed_rl10); M6, since M1's
                                             # `Link.channels` is the set of open channels' logs
    def Link.unfollowed(self, pid) -> bool   # the hello carries no `follow`: holds(pid) for a project,
                                             # sminos_channels.opens_unfollowed(pid) for a channel
    def Link.holds(self, pid) -> bool        # as today for a project; False for a channel
    def member_frame(pid, m, launch=None, visibility=False, channels=()) -> dict
        # `channels`, when it is not empty, as the frame's last key: a list

| For a log that is | `hello` | `machine`, session presence, `pending`, host frames | uploads |
|---|---|---|---|
| a project this machine holds | no `follow` | as today | as today |
| a project it follows | `follow` | none, as today | as today |
| a channel a record of this machine names | no `follow` | none | its own writers' events in their order: this code's requests and `channel-env` events, what an older copy wrote there, and the `retired` that undoes an older copy's `joined` |
| a channel no record here names | `follow` | none | the same |

A thread's `member` frame names its own project as `project`, as today,
and never a channel; while `Link.serves_channels` it carries the thread's
`channels`. A `snapshots?` for a channel is answered with one page, empty
and done; a `subscribe` for one with the `end` a project gives for a
session it does not hold.

`fresh_frame` passes `channels_of(m.session)`'s entries that pass
`is_channel_id`, the first 128, for a lane A member while `Link.serves_channels`,
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
applied or is pending, or was answered already by its machine with no
answer this command can read (it says so, and where the thread is now);
1 when the verb or any target was refused, or the
caller's own change could not be recorded; 4 for a name that is unknown or
ambiguous; 2 for usage.

**Refused before anything is written,** each naming its target: `create`,
`add`, `remove` and `env` where the kept welcome lists no `channels`;
`create` with a name that is no valid name, or that a log known here
already answers to (but a channel of that name registered here with no
member, which `create` brings back: M4); a
target that is no thread as this machine reads it (its row carries no
`thread`, or on this machine its lane is B); one that has ended; one that
holds no session; an add, and a `create`, that would be a 129th channel
where this machine can see the set (its own record, or the row's
`channels`), checked for `create` before the channel is registered; a
target the stream choice refuses; from a session, `create` with a thread
named (the caller is the first member, and `add` places the others); from
a terminal, no thread named, or for `create` a thread of another machine;
`env` from a terminal, from a thread not in the channel, or naming a
machine the org's directory does not list.

**The sentences that are decisions** (`%s` the name as given):

| Where | Exit | Words |
|---|---|---|
| `say --in <channel>`, a tag `@<channel>/<alias>`, a selector `--project <channel>`, from a session or a terminal | 1 | `%s is a channel, and speaking in a channel is not available in this version of sminos yet: nothing was recorded. Tag the thread itself (@<alias>#<short> or @<short>), which reaches it in its own project as today` |
| a verb's target `<channel>/<alias>` (`find_target`) | 4 | `'%s' names a thread through a channel, which is not available in this version of sminos yet: name it by its own name (<alias>#<short> or <short>)` |
| `join <channel>` | 1 | `cannot join %s: it is a channel, not a project — sminos channel add %s places a thread in it, and its project stays where it is` |
| a project asked for, a channel named (`find_project`: `chat`, `list <name>`, `--project`) | 4 | `'%s' is a channel, not a project: sminos channel show %s prints it` |
| a name a channel shares with another log, or two projects of one tier share (`ambiguous_name`) | 4 | `ambiguous name '%s': <each> — name one as listed, or by its id`, each as `<name>#<the first eight of its id> (<kind>)`, kind one of `channel`, `project`, `machine project`, `local project`; a log whose id is no UUID by its whole id |
| a `.smns` naming a channel id (a warning on standard error) | — | `ignoring %s: it names a channel's id, and a channel is no project; this directory is in the machine's project` |
| `create`, `add`, `remove`, `env` without the capability | 1 | `this machine's endpoint does not serve channels (its welcome listed no channels): nothing was written` |
| the limit, before writing | 1 | `%s is in 128 channels, the limit: nothing was written` |

**What a target's line says:** `<alias>#<short>: in <channel>`, `out of
<channel>`, `already in <channel>`, `was not in <channel>`, `refused: <§6's
words>`, `pending: <§6's words>`, or, for a thread of another machine,
`asked; pending on <machine>: its machine carries it out when its daemon
reads the request`. `pending` is said only of a request, which a later
pass carries out. The caller's own add or remove that could not be
recorded says `nothing was recorded (<§6's words>): run the command again`
and exits 1. `create` says `created channel <name> (<id>) with <thread>`;
of a channel of that name registered here with no member, `<name> exists
and has no member: <thread> is in it again`.

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
reachable (the hub withheld it)` (from M7), `not carried out: another
request in this channel used its id first`, or `pending on <machine> since
<time>`; `pool`, one line a machine: its name, `<n> live, <m> stopped`
counted from the roster's rows there (`live`: a state of `FILLED`;
`stopped`: `stopped` or `gone`), and `added by hand` for one a
`channel-env` holds in. With `--json`: `{"id", "name", "members": [<a list
--json row, with its project keys>], "requests": [{"id", "op", "thread",
"session", "target", "by", "ts", "state": "applied" | "refused" |
"withheld" | "duplicate" | "pending", "reason", "machine"}], "pool": [{"machine",
"live", "stopped", "by_hand"}]}`.

`sminos help` (the module's docstring) lists the six lines above. The
backtick guard's `VERBS` gains `channel`.

### §9. What the tests are built on

**The checker,** `T/channel_wire.py`, called by every suite of this child
that runs an uplink, and by CH2's. It judges what this code added to the
store it was given, so a suite over a store an older copy wrote into takes
the baseline first:

    ALLOWED = ("channel-request", "channel-env", "retired", "void")
    def baseline(sminos_home, channel_ids) -> dict
        # {(channel id, writer, seq): the event held there} for every event the channels' logs hold now: what
        # was there before this code ran. Taken before any verb, tick or uplink of this code reads the store,
        # since a reading verb reconciles
    def published(frames, channel_ids, before={}, allowed=ALLOWED) -> list[str]
        # each breach among the frames a stand-in kept, one line each; [] for none
    def written(sminos_home, channel_ids, machine, before={}, allowed=ALLOWED) -> list[str]
        # the same over the store: the channel's log files of this machine's writers, its host store, and any
        # delivery record under a channel's log

A breach is: a `member` frame whose `project` is a channel id; a
session-plane message whose project is one (`presence`, `machine`, `host`,
a subscription's), but the `end` that refuses a `subscribe`; a `pending`
frame for one; a `words?` for one; a `reach?` for one whose event is no
`channel-request`; a `snapshots` answer for one that carries an event; an
`events` frame for one carrying, at a position the baseline does not hold
for that channel with that same event, a kind outside `allowed`; a
`member` frame with `channels` that is empty, holds more than 128 ids,
holds an id that is no channel's, or is sent on a connection whose welcome
did not list `channels`; on disk, an event of this machine's writers in a
channel's log, at a position the baseline does not hold with that event,
of a kind outside `allowed`, anything in a channel's host store, or (in
this child) a delivery record under a channel's log. A new `retired` under
a channel, on the wire as on disk, is accepted only as the undo of an
older `joined`: its reason is `moved`, and the baseline holds, in that
same channel, a `joined` of its session with no `retired` after it; any
other is a breach. An event the baseline holds is uploaded in its writer's
order like any own event and is no breach. The checker has negative tests
of its own (M1). CH2 calls it with the kinds it adds and without the
delivery-record rule.

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
every suite of this child asserts that it recorded no launch, and M2's
wake interleavings read its process and launch counts.

**Where each new file sits,** and the neighbour it is built like:
`test_channels.py`, `test_channels_store.py`, `test_channels_life.py` and
`test_channels_requests.py` are `unittest` modules that load the CLI's
modules under a temporary home, as `test_threads.py` and
`test_threads_ended.py` do (`test_channels_life.py` drives T1's
transitions as `test_threads_branch_a.py` and `test_threads_stopped.py`
stage them); `test_channels_wire.py` runs a real `Link` against an
in-process `endpoint_standin.Endpoint`, as `test_rl10.py` and
`test_leaving.py` do; `test-channels.sh` drives the launcher on one
cut-over home with a stand-in beside it, as `test-join.sh` does;
`test-channels-machines.sh` joins two and three homes with
`rl10-machines.sh`, as `test-org.sh` joins three. All run in the `channels`
part of `T/run-sminos-tests.sh` and in no other; the older-copy suite and
the replay stay where they run today.

### Dependencies

- MAWS's master with its child MW (the endpoint echoes `channels`, counts
  `member.channels`, refuses a member whose project is a channel id, and
  lists a known channel in the org frame as kind `hub`), installed on the
  owner's machines. Nothing in this child's suites runs MAWS: the stand-in
  and the conformance replay stand for it.
- MAWS's fixture at `8ae3b0843` (M6) and its vectors `channel-rule.json`
  at the pinned version 1 (M1).
- Python's standard library alone, as every module of `S/` today.

## Surprises & Discoveries

The controller records here what changes the understanding of the design
while the milestones are built, one observation and its evidence each.

- (M1) `_stated_decision` would take an org-frame location statement that
  names a channel's id as that folder's project; MAWS refuses linking a
  folder to a channel id. Guarded by the holder's ruling (Decision Log,
  2026-11-21, "A location statement naming a channel").
- (M1) An older copy's `end_closed` writing a `retired` for a closed session
  into a channel's log is stopped by nothing but `lifecycle`'s guard; the
  undoing `retired` is the one write the constraint allows there (C4).
- (M1) The `sminos-channels` gate runs in about 20 to 25 seconds at M1.
- (M2) T2's wake writes its record's fields (`wake_job`, `wake_line`,
  `wake_done`) through `update`, which refuses a record with an open entry:
  the concrete reason the operation must refuse inside a wake's own hold.
- (M2) 1.51.0 and 1.52.0 finish a `channels` entry by their own `_owe` and
  `lifecycle`, unchanged (their `_finish` checks no operation); 1.27.10
  leaves record and entry alone, and this code's next `list` finishes it.
  All three keep `began` and `answered`, since they rewrite a record whole.
- (M2) `project_path` creates a project's home and its `project.json` on
  first use, so a reader that must create nothing (`channel_positions`)
  joins `project.home` itself.
- (M4) `same_owner_local`, `outside_origin` and `own_writers_here` read
  identity and enrollment from per-invocation caches, so the second
  evaluation re-reads them from `identity.json` itself (`_Facts`).

## Decision Log

- 2026-11-21 — **Verification.** This plan is reviewed before it is handed
  over by the `doperpowers:adversarial-reviewer` agent, on buildability: the
  milestones against the code, the names of Interfaces against the two
  designs, and §3's and §6's tables against the store's locks. The first
  round returned fourteen findings and the second, on the revision, eight
  (the two entries at the end of this log); there is no third before the
  build.
  The build runs under `doperpowers:plan-executor`, a fresh executor a
  milestone; each milestone is reviewed at its close by the execution
  loop's reviewer, three reviews at most (the owner's bound). The range M1
  to M7 is reviewed whole by the composite's holder at the frontier,
  through doperpowers:review-code at the panel rung with the four lenses
  named in Plan of Work, a second whole reading if the first confirms more
  than ten, three rounds at most. After M8 the branch is reviewed once more
  through doperpowers:review-code at the panel rung, on the whole range,
  before the pull request merges. The composite's own scene on two of the
  owner's machines is not this plan's: the holder runs it once CH2 has
  landed.
- 2026-11-21 — **Listing before the wire, the frontier after the seventh
  milestone.** Readers and refusals first (M1), the store's operation and
  its life (M2, M3), then its two consumers on one machine (M4, M5), then
  the wire (M6) and what crosses it (M7). *Alternative: the wire second, so
  that a real endpoint could be used from the start.* It lost because MAWS
  echoes the capability only to a hello that lists it: until the fixture is
  copied no real endpoint serves channels anyway, and the copy needs the
  operation to place the replay's session. *Alternative: M1 cut in two
  (names; the publishers).* It lost because M1 is one idea, the predicate
  applied at every door, and one reviewer reads it as such.
- 2026-11-21 — **The operation does not move a seat's lifecycle
  generation.** `begin` moves it for every journaled operation, so that a
  watcher whose snapshot predates a lifecycle write stands down. *Alternative:
  move it, as every other operation does.* It lost because a turn's watcher
  is one of those: a thread placed in a channel during its turn would have
  that turn's reply go unrecorded.
- 2026-11-21 — **`known_projects` returns no channel; `known_logs` returns
  both.** Some two dozen callers enumerate projects for a person or a
  session, and a handful open, reconcile or leave logs. *Alternative: leave
  the enumeration whole and filter where a channel must not show.* It lost
  because the two failures are not alike: a caller that wrongly lacks a
  channel fails this child's own tests (its log is never opened), while one
  that wrongly keeps one prints or publishes a channel as a project in a
  path no test visits.
- 2026-11-21 — **A channel's view has no members by construction,** and
  `lifecycle` writes nothing but a `retired` under a channel id. C1 says
  the view "returns none, as it does today", which holds only while the log
  holds no `joined`; an older copy's `join` writes one. *Alternative: rely
  on the reconciliation retiring it.* It lost because the plane, the member
  set and the forced presence read the view before and after that
  `retired`, and because a closed session's is not retired at all until it
  runs.
- 2026-11-21 — **`name#short` is taken wherever an argument takes a
  name.** The composite wants each log listed with `name#short`, which
  nothing accepts today. *Alternative: list full ids, as today's refusal
  does.* It lost to C6's text. A tag's grammar (`TAG_RE`) cannot carry `#`
  in its qualifier, so a tag takes the id; whether it should take more is
  CH2's, with the tags.
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
- 2026-11-21 — **Where a membership began is `began`, keyed by channel,
  and `set_channels` reads the positions itself.** The composite fixes what
  is kept and when; the key's name and shape are this plan's. *Alternative:
  the caller hands the positions in with its change.* It lost because a
  caller's read is from before the lock, and the positions must be the
  log's at the write that enters the channel.
- 2026-11-21 — **A request that names no thread here gets no statement,**
  for every case of §6's row 3, and expires. The composite says so for a
  session that became another thread's and for lane B; an ended thread and
  a session the thread never had are the same case to this machine, and to
  one that holds no such thread at all the request is simply another
  machine's. *Alternative: a refusing statement with a fourth reason.* It
  lost because C3 fixes the reasons at three and a statement needs a thread
  to be written under.
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
  (`SMINOS_PART=channels`, `sminos-channels`), on the four conditions M1
  states, agreed with the session that owns CI. The `sminos-suites` gate
  ran 18 to 20 of its 30 minutes before T1 and T2 added theirs.
  *Alternative: add to `suites`.* It lost to that margin, and to reading
  A13 off two gates this child does not change.
- 2026-11-21 — **One narrow check on a real engine, in M8.** The composite
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
- 2026-11-21 — **The plan's review, and what it changed.** The first
  review for buildability returned fourteen findings. Two changed the
  composite (`95fef6b7`) and this plan follows it; the rest changed this
  plan alone. Each line gives what stands now and the alternative that
  lost.
  - *Where a membership began is kept in the record, and no delivery record
    is touched* (the composite's C3 and Y3; §3, §4). *Lost: a mark in the
    thread's delivery records at each change* (this plan's first form, from
    the composite's second): a delivery record is keyed by session, so a
    mark could settle another thread's mail, and a finisher of 1.51.0 or
    1.52.0 skips a step it does not know, where it leaves a record's keys
    alone.
  - *The operation takes the wake lock, as every transition does* (the
    composite's C3; §3). *Lost: none, as a release takes none* (this plan's
    first choice, overruled): a `resume` that has checked its wake and is
    about to stop a live turn would find the wake refused by an entry
    opened in between, and a launch already made would lose the write of
    its job and its grace. A wake in flight is one more wait. The debt row
    this plan had for the exposure is gone with it.
  - *The entry owes the statement and nothing else, and `finish` gains no
    step for the operation* (§3; M2's older-finisher cases). *Lost: steps
    of this code's `finish` alone carrying part of the change.* Only the
    absorption's merge stays such a step, and its loss to an older finisher
    is the composite's accepted one.
  - *The whole of §6's table is evaluated again under the lock, and a word
    of either kind is bound to the thread it was asked for before it is
    read* (§6, rows 13 to 15; M4, M7). *Lost: re-reading only the rows that
    name the record, and binding `deliver` alone:* a refusal for a reach
    the thread no longer has would be recorded for good, and an owner, a
    policy or a revocation changed between the first read and the lock
    would be acted on as read. The window that stays, a reach narrowed
    between that read and the record's write, is under another lock and is
    accepted (the constraints).
  - *A statement owed when its thread moves lands in the project the entry
    names* (M2). *Lost: appending it where the thread is by then:* the
    journal skips an event by reading one project's log for the entry's id,
    an older finisher would not redirect, and the requester finds an answer
    wherever it lies.
  - *An answer is read from an index of every statement that carries
    `answers`, taken only under the request's own `thread`* (§5; M5).
    *Lost: reading it from the statement in effect:* a restatement, a new
    writer or a move replaces that statement, and another thread's
    statement naming the same request would answer it.
  - *`channel-env` carries its writer's thread id, and is honoured through
    that thread's roster row* (§2; M5). *Lost: the writer's session
    alone:* a session id can come to be another thread's.
  - *Every verb that writes for a channel is refused without the
    capability, `remove` and `env` included* (§8; the constraints). *Lost:
    `create` and `add` alone, the composite's letter:* a removal's request
    or an env event would name a channel on the wire before M6. The
    followed hello for a channel the directory lists is the intended
    exception.
  - *The wire check judges what this code added to the store it found,
    and an older copy's `joined` under a channel is uploaded in its
    writer's order, followed by this code's `retired`* (§9; M1, M8). *Lost:
    a check over everything the store holds, and holding an older copy's
    event back from upload:* the first fails on what an older copy wrote,
    and a writer's sequence admits no hole. A snapshot request and a
    subscription for a channel are answered as for a log with no member.
  - *A command carries out the request in hand, and an interrupted
    `create` can be run again* (§6's `also`; M4). *Lost: finding its own
    request in the merged log, and refusing every name already
    registered:* an operator's append to a new log can be queued with no
    position, and a channel registered with no member would hold its name
    for good. The limit is checked before the channel is registered.
  - *The earlier requests and the expiry are those of the log at the
    decision, by its files' signature, with a retry* (§6; M4). *Lost:
    merging the channel's log under the store lock:* that lock is the one
    every seat's write waits on. *Lost too: trusting the pass's read:* a
    request that sorts earlier can be imported while a carrier is paused.
    What this leaves open is in the second review's entry: no lock holds
    the log still.
  - *Among projects, names keep today's tiers; a channel is in no tier*
    (the composite's C6; §1; M1's test of a hub and a machine project of
    one name). *Lost: refusing every name several logs answer*, which
    would change what a session that never uses a channel is told.
  - *The recovery after an older copy's `join` into a channel is for a
    session a process or a seat holds* (the composite's C4; M1, M8). *Lost:
    retiring a closed session's `joined` from the channel as well:*
    `retire_moved` and the re-join act on what runs, and a closed thread
    has no evidence to join it back with.
  - *This code's listings export neither new key; an older copy's
    `list --json` shows a spawned thread's* (the constraints; M8). *Lost:
    the first draft's claim that no listing does,* which was false of an
    older copy and is not worth building around.
  - *M2 is two milestones* (the review's advice; Plan of Work). *Lost:
    one, with two proofs:* a milestone is reviewed as one diff, and the
    durable write and the ownership of a set across transitions are two
    lenses and two kinds of test. The count is eight.
  - *The proof that the hub's withholding is shown moves to M7,* where its
    reader is built. *Lost: M5's list of request states including it.*
  - *The new gate stands on four conditions* (M1). *Lost: a timeout of
    thirty minutes by habit, and parts that overlap.*

- 2026-11-21 — **The plan's second review, and what it changed.** The
  last review before the build kept the cut of eight milestones and
  returned eight findings and four notes. One made the composite exact
  (`331e2dd5`); the rest changed this plan alone. Each line gives what
  stands now and the alternative that lost.
  - *No lock holds a channel's log still* (the composite's C3; the
    constraints' accepted list). Where a membership began and the order of
    requests are observed at the last read before the record's write, and
    what is imported after it counts as after it. *Lost: presenting the
    three rereads as closing that window.* They bound what one call acts
    on; the tests state the rule at the boundary and promise no order.
  - *The ordered input of a carrying out includes this machine's queued
    appends for the channel's log* (§6's `requests_of`; M4). *Lost: the
    merged log and the caller's own request alone:* a second terminal's
    command would not see the first one's queued request ahead of its own.
  - *A word is kept and used under the event it was asked about* (the
    request's log, writer, position and hash; §6's `event_key`, rows 2 and
    12; M4, M7), and a request whose id another writer used first is not
    carried out and is shown so. *Lost: a word keyed by the request's id:*
    a second writer's request under that id would have been carried out on
    the first one's answer. The `answered` ledger stays keyed by channel
    and id.
  - *The evaluation under the lock reads what it rests on from its files
    then, by reads that lock and write nothing* (§3; M4's test with warmed
    caches and another process's change). *Lost: calling the same
    functions a second time:* several of them answer from a cache this
    process keeps for its invocation.
  - *A thread's own change that cannot be recorded fails* (`change`
    answers `failed`; exit 1; §3, §6, §8; M2), and so does the first
    membership of a channel a session creates. *Lost: `pending`:* no
    request exists for a later pass to carry out, so nothing would ever
    finish it.
  - *`create` of a name whose channel is registered here with no member
    brings that channel back under its id,* interrupted or emptied (§8;
    M4). *Lost: taking back only a channel whose log is empty.* Two
    creators of one name at once make two channels of it; accepted, and
    said in the constraints.
  - *The wire check's baseline is keyed by channel, writer and position
    with the event held, taken before this code reconciles, and a new
    `retired` under a channel passes only as the `moved` undo of an older
    `joined` in that channel* (§9; M1's negative tests). *Lost: a set of
    writer and position:* it passed a position of another channel and any
    `retired`.
  - *An answer is taken only when its writer's session is one the
    request's thread has had* (§5's `answer_of`; M5). *Lost: the `thread`
    stamp alone,* a field any writer can set.
  - *Notes taken:* `channel env` without the capability is asserted in M5,
    with nothing appended; the wake tests also try from a caller that
    holds the lock and confirm its hold is live afterwards (M2); 1.51.0
    and 1.52.0 hide `channels` and expose `began` and `answered` (M8, the
    accepted list); §2 no longer calls `channel-env`'s `thread` an
    addition, since the composite's C2 names it.
- 2026-11-21 — **M1 as built.** `cmd_projects` needed no change: its input
  is `known_projects`, which never yields a channel, so the fourth kind its
  tier order would raise on never reaches it; the listings with a channel
  registered beside them are pinned byte for byte. `project_label`,
  `moved_here`, the private-stream lookup and `daemon status`/owed read
  `known_logs` (they serve a log, not a person's choice of project);
  `_holding_projects` and `last_project` skip a channel, which is never a
  session's project. `Plane.refresh` of a channel does not call `view_of`:
  the daemon's channel pass is the one reconciler of a channel's log.
  `find_channel(required=False)` still exits on a project or an ambiguous
  name and returns none only when nothing matches, so a caller asking "is
  this a channel" never silently takes a project. `name#short` takes a
  non-UUID id whole, else a hex prefix of eight or more. `append_host`
  raises `LogWriteFailed` for a channel, handled at `main` as any failed
  write. `register` takes the enrollment's hub and org and raises on a
  machine not enrolled (a channel's log syncs only through a hub).
  `held_channels` is cached by the cache generation and the thread stores'
  stat key. §9's checker: `published(frames, welcomed=())` takes the
  stand-in's `(conn, frame)` pairs or bare frames, `welcomed` the
  connections whose welcome listed `channels`; `written(..., deliveries=True)`,
  which CH2 passes false.
- 2026-11-21 — **A location statement naming a channel** (the holder's
  ruling). C1 and C4 hold at every door by this copy's own check, not by
  another program's refusal: an org location statement that names a
  channel id as a folder's project is read as no statement for that folder,
  which resolves as if it were absent, with one test beside M1's door
  tests.
- 2026-11-21 — **The `sminos-channels` gate's timeout** (the holder's
  ruling). Five minutes through the build, since the part grows at every
  milestone to M7 and one minute for a 24-second run goes red on a slow
  runner; M8 sets it to about twice the measured run of the whole part.
  This replaces, for M1 to M7, Concrete Steps' "kept at about twice" and
  M1's "set again as the part grows".
- 2026-11-21 — **M1's review, round 1, as fixed.** Every door holds
  without registration: an explicit channel id at a refusing door is
  classified by `is_channel_id` alone (an unregistered one stands in as a
  project with no root, so `names_channel` keeps one type), while
  `find_channel` still needs a registration; `join`'s channel refusal comes
  before the seat's. A rooted guess and the seat's fallback never yield a
  channel, so `known_projects` holds none and `say` never takes one as its
  destination. A channel's reconciliation is its own function,
  `_reconcile_channel`: it only undoes an older copy's `joined` (`retired`
  `moved`) while a seat or a live process holds the session, and leaves a
  closed one as it is; an import into a channel's log runs no project
  reconciliation and no delivery, and still nudges the daemon. Every tag's
  qualifier is checked before any member lookup. An exact project name wins
  over a `name#short` spelling, the qualifier parsed from the right. An org
  directory entry with a channel id is never a machine, and a record's
  `channels` that is not a list reads as absent.
- 2026-11-21 — **M1's review, rounds 2 and 3.** Round 2's fixes: an
  unregistered channel id is refused as a channel at the project-lookup
  doors too (`chat`, `list`, `list --project`); a refusal's label for a log
  is the first spelling that resolves back to that log alone (`name#short`,
  then `name#<whole id>`, then the bare id), exact-name precedence
  unchanged; the tag preflight exits only on a clash that includes a
  channel, so a store with no channel refuses tags in today's order. Left
  open after round 3, the owner's bound, and sent to the holder: a project
  whose exact name is an unregistered channel's id is still found by that
  name at `project_tiers` and `find_project` (`list <id>` shows it; `say
  --in <id>` refuses it; nothing is written either way). Handed to M2: the
  uplink's `open_projects()` classifies every open project at each tick on a
  machine with no channel, against the constraint "The idle daemon stays
  cheap" (sminos-idle once 0.5% over its calls ceiling at `79985839`, then
  passed).
- 2026-11-21 — **CI's split of the suites gate** (PR #588, taken in with
  `origin/main` at the boundary of M1 and M2). `sminos-suites` is three
  gates, `sminos-suites-a`, `-b` and `-c` (`run_suites_a|b|c`, `run_suites`
  calling all three); Concrete Steps' gate line names the three. The
  channel part stays its own: `SMINOS_PART` takes `channels` beside the
  three, and `all` runs every suites part and then `run_channels`. A suite
  this child adds to the general list goes at the end of `run_suites_c`.
- 2026-11-21 — **The idle cost of channels** (the holder's ruling). A
  machine that holds no channel pays nothing per tick for channels: whether
  a log is a channel's is decided once, when it is opened or first known,
  and kept as state beside the open logs; the tick's loops read that state
  and call no per-log function for it, and a duty only channels have runs
  over the channel set alone. Built in M1 after its third review. Proof:
  `sminos-idle`'s own figure back at main's within the spread between runs
  (about 1%; main 32.6k calls a second, M1 at 33.4k to 33.7k before the
  trim), no new test. From M2 to M7 every milestone records the idle figure
  at its gate, makes anything it adds to the tick conditional on a channel
  held or open, and brings to the holder, before it lands, any change that
  cannot keep the figure at main's. `bench_scale.py`'s limits stay.
- 2026-11-21 — **M1's idle trim, and round 3's last finding, as built**
  (`eee82f3b`, after the third review; no fourth). The uplink decides when
  it opens a log whether it is a channel's and keeps the answer in
  `Link.channels` beside `opened`; the tick's loops read that set and ask
  no log's id, and the re-hello on a flip of `unfollowed` runs over the
  channel set alone. `unfollowed` still asks the id of a log that is not
  open (one that left), so a channel a thread here is in can come back;
  that costs nothing while every log is open. The daemon's tick reads
  projects and channels from one pass over the registrations
  (`known_kinds`); the seat's guard sits inside `seat_project`'s cached
  resolution; `_holding_projects` asks a log's id only after the listing
  shows it holds the session. `sminos-idle`: 32,161 calls a second at 3.78
  ticks (main 32,582 at 3.83; about 8,500 a tick either way). The project
  resolvers (`project_tiers`, `find_project`) refuse a channel-shaped
  argument before any name lookup, so a project named like a channel's id
  no longer shadows it and stays reachable by its own id.
- 2026-11-21 — **M2 as built** (`5ec8f9d6..dcbbb18e`). The fold ends a
  session's statement at its writer's `retired` as well as at a new
  `joined`: C2 reads membership as the statement after the `joined` in
  effect, and with a `retired` in effect there is none, so a statement
  written after the writer's `retired` (a move between the record's write
  and the statement) states nothing (§5 amended). `change` takes its
  project from `last_project` before the lock, which only chooses where to
  look; under the lock it reads the session's own events in that project
  (no lock, nothing written), and a session no longer a member there drops
  the caches and asks once more an attempt, three at most, the same answer
  again being `failed between`. `change`'s outcomes gain `failed moved`
  (the session is no longer the thread's current one, or the record ended
  or is gone) and `refused limit` for an own add past 128, nothing written
  (§3 amended). `change` refuses at once in a process that holds the
  thread's wake lock, before it finishes any entry. `REQUEST_TTL`,
  `REASONS`, `expired` and `request_ttl()` are defined in M2, since
  `set_channels` prunes `answered` and checks an answer's reason; §6 names
  them as before. `T/test-older-cli.sh` runs 1.52.0 on the cut case alone:
  that copy wakes a stopped thread itself, so the every-copy expectation
  "launched nothing" cannot hold for it, and its own expectations are M8's.
- 2026-11-21 — **M2's review, round 1, as fixed** (`e78b7204`). The read
  under the store lock is read-only on every stream (audience streams read
  by their literal paths, never through `project_path`). The membership
  check that chooses the statement's project is the last read before the
  record write, after the positions; a move during the position read
  writes nothing, and `change` looks for the session again in its new
  project or answers `failed between`. No lock coordinates with a move:
  the window left is in effect the accepted move after the record's write,
  which the reconciliation (M3) repairs. A log or writer file that is
  there and cannot be read raises `sminos.PositionsUnread`, and `change`
  answers `failed unreadable` with no partial `began` (§3 amended); a log
  that does not exist still reads `{}`. The fold takes an event as a
  statement only with a statement's fields (`is_statement`: a `channels`
  list, a `thread`, an `op`). A finisher's timeout after the record has
  committed answers `applied`, nudges the daemon and leaves the entry for
  replay.
- 2026-11-21 — **M2's review, round 2, as fixed** (`ec4034c1`). The
  membership guard is the last read before the write: `set_channels` builds
  the whole change first (positions, the walk of `answered`, the entry) and
  only then reads the session's own events in the change's project.
  `channel_positions` reads the channel's `project.json` itself: missing is
  "not registered" and `{}`; a read error, unparseable JSON, or a file that
  is not this channel's registration raises `PositionsUnread`, since where a
  membership begins cannot then be known. `known_project` keeps its
  tolerance; the two share `_registered_as`.
- 2026-11-21 — **M3 as built** (`54cacc3a..aa816f2d`). The reconciliation
  is `_reconcile`'s last step, `_keep_sets`, over the `_memberships` memo,
  which now also returns the statements in effect, with the pass's own
  appends folded in. It runs only when a log states some set or a thread
  here holds one: the holders are `sminos_threads.set_holders()`, derived
  from `_live_index` and cached while that index is the same object, so a
  machine with no channel compares nothing. The candidates are the holders
  and the sessions whose log states a non-empty set; sets are compared as a
  reader takes them (`stated_set`). The writer compared is the one of the
  session's `joined` in effect, and the reconciliation passes a session
  whose `own_stream` differs from it (a change of reach not yet snapshot),
  since a statement there would state nothing, again at every pass.
  `restate` takes its project, session and writer from what the
  reconciliation read and never scans for them; this is what repairs M2's
  accepted window (the project moved to gets its statement at its own
  reconciliation). `set_channels` gains `wake_until` and `restate` gains
  `appended` (§3 amended). A return writes `began` anew in its own record
  write (`_began_anew`); a channel whose log is there and cannot be read
  then keeps its position from before the end, with a warning, rather than
  hold the return up, as an older copy's return leaves it. The absorption's
  merge is a write of its own in `finish` (`_merge_absorbed`), marked
  `merged` in the entry so that a replay merges once. A seat cannot `join`,
  so the `join` cases are of threads their humans opened. Left to M4's
  fresh reads: the `own_stream` read inside `restate`'s `decide` uses the
  module's ordinary readers; a stale writer can only skip a statement or
  write one that states nothing, which the next pass repairs.
- 2026-11-21 — **A return over an unreadable channel log** (the holder's
  ruling; Y3). A return over a channel whose log is there and cannot be
  read keeps that channel's `began` from before the end, writes the others
  anew, commits, and says so once; it is on the accepted list beside the
  older copy's return. A return must not wait on one channel's log: a
  thread that cannot come back because a log it only reads is unreadable
  is the worse fault, and a wake would inherit it. What the kept positions
  cost: events the channel gained while the thread was ended count as
  after its membership began, so CH2 may push them once at the return,
  where the design means them not owed; nothing is lost or misaddressed
  (they are the channel's own events, and the thread is a member). *Lost:
  an unknown-boundary marker,* a third state of the record that CH2 and
  every older finisher would have to read, for a local read error a
  healthy machine does not produce. An add differs on purpose: it has no
  earlier positions to keep, so it stays `failed unreadable` with nothing
  written (M2). The holder folds this into the composite (C3, Y3) at CH1's
  landing.
- 2026-11-21 — **M3's review, round 1, as fixed** (`483a1e69`). A
  restatement's last guard, under the record's lock, is
  `sminos.restated_holds`, reading files as they are: the session's
  `joined` in effect is under the Change's `writer`; that writer is the one
  its events go under now, with the machine's name read afresh
  (`machine_name_now`), not from the per-invocation cache; and that
  `joined` is the session's newest on this machine (`_joined_since`), which
  is what "its current project" means here. C1 to C4 keep M2's guard. The
  reconciliation's step is gated first by `channels_here()` (one stat of
  `projects/` a cache generation), and `set_holders()` runs only when the
  log states a set or a channel is registered here; so a set made only of
  channels not registered here is not kept equal to the record, which only
  M2's test-only `change` can make today. The notice of channels dropped
  past the limit at an absorption is written before the merge's write, so
  a cut repeats it rather than losing it. The united `answered` is sorted
  oldest first.
- 2026-11-21 — **M3's review, rounds 2 and 3, as fixed** (`cb09530c`,
  `7748fde1`). Where a session is now (`_current_here`, the restatement's
  guard) is `last_project`'s rule read fresh and read-only: among the
  membership events in effect in every log here the newest decides, a
  `retired` `moved` standing for its destination, so a past `joined` a
  later `retired` ended vetoes nothing (a join back is stated). A tie at
  the newest moment that names two projects makes no project current and
  writes nothing; the move's `retired`, newer than both, decides the next
  pass. This last fix came after the third review and had none of its
  own. The return's notice over an unreadable channel log is best-effort:
  one line in an ordinary run, possibly none across a cut between the
  return's write and the line (replaying it would need a new entry key
  and a finisher step). `channels_here()` never caches a failed listing:
  only ENOENT answers no channel, for the generation; any other error
  looks the holders up.
- 2026-11-21 — **M4 as built** (`04cc6146..f5f93f62`). `judge` takes
  `project` (chosen before the lock by `last_project`, passed in, never
  looked up under it), `now` and `facts`, the second evaluation's fresh
  reader (`_Facts`: identity and enrollment from `identity.json`, the
  policy by `stored()`, since `sminos_policy.load` writes to `daemon.log`);
  `carry_out` and `carry_due` take `wake_until` (§6 amended). `carry_due`
  passes by, unjudged, a request whose thread is gone, ended or expired, or
  that the record already answered; a command's own request is always
  judged. Every pass judges afresh, so a request ignored `not-here` while
  its thread was lane B is carried out once it is lane A again. Words
  added: pending `busy` (the store lock) and `unreadable`; ignored
  `expired` and `not-here`, which a command prints with exit 1; and
  `change`'s failures (`OWN_FAILED`) with M2's `moved` and `unreadable`.
  A command whose own request the daemon answered first prints what the
  record holds now. `create` brings a channel back only when it is the
  one log answering the name, no live record names it and `org.json`
  lists it not; otherwise the name is refused. A channel id is a uuid4
  with its version nibble set to 8. Row 3's lane B is read from the
  target's current session's record. A queued request is dropped from the
  ordered input once the log holds its writer and id. Every path keeps M3's
  gate: a request is carried out only for a channel registered here.
- 2026-11-21 — **M4's review, round 1, as fixed** (`0a43efe5`). Every
  membership check under a lock (`_member_of`, `set_channels`' last guard,
  `_current_here`) picks writer files by the identity `identity.json` holds
  now; `is_self`, `own_writers_here`, `same_owner_local` and
  `outside_origin` take `fresh`, and `_Facts` calls them rather than keep
  copies of the same-owner rule. A terminal's `create` runs the first
  member's stream choice against the channel about to be made before it
  registers anything. A request read from a former name's queue is pending
  `queued` until `release_queued` rewrites it under the current name, and
  sorts after the log's requests as every queued append does; no event
  logged under a former name is trusted. The store-locked comparison of
  the ordered input is by file stats alone (`input_signature`). A command
  whose request was answered first reports from the statement that
  answered it (the record's open entry, else its sessions' events), and
  when neither can be read says it was answered and where the thread is
  now, exit 0. A failed write for one target is that target's outcome.
- 2026-11-21 — **M4's review, rounds 2 and 3, as fixed** (`ba2c784c`,
  `9ffbe8c5`). A request from a former name's queue is deferred `queued`
  only after §6's rows 3 and 4 (whom it names, the answered ledger), so one
  that names no thread here is `ignored not-here` and holds no later
  request back. A command's row keeps the recorded outcome of a request
  answered first (`_answered_line` returns the line and the `Outcome`), and
  `create`'s summary is built from it. `_current_here` takes one fresh
  identity for its whole scan. `create`'s stream choice: the preflight
  against the channel about to be made refuses an unreachable target with
  nothing registered; `place` chooses again at the append for that one
  recipient, and when that choice refuses or gives another writer or
  audience it appends nothing, says the channel stays registered with no
  member and that the same command run again brings it back, and exits 1.
  That race (the target's reach narrowed during the registration) is the
  one exception to "refused before anything is written": a registration
  with no member is left, never a request under an audience the target no
  longer has. This last fix came after the third review and had none of
  its own.
- 2026-11-21 — **M5 as built** (`b4a9bdd7..f5644cc9`). Y1's
  `answer_of` takes the channel, `answer_of(channel, request)`, since a
  request event does not carry its channel's id (§5 amended; sent to the
  holder for CH2). The roster is cached while every project view it read is
  still the one `view_of` returns, so it is dropped exactly when a view is.
  The sessions a thread has had are its member rows' (current, `former`,
  `thread_sessions`) and any whose own `joined` in the statement's log is
  stamped with that thread. A bare `list` is one with no scope filter
  (`--stopped` and `--all` are still bare); `--channel` sections fold
  nothing and print no `+N hidden` line; `--org`'s channel sections are
  narrowed by the other filters, and a section emptied by them is left out;
  `find` prints none. `channel show` needs no capability (it only reads);
  it prints times to the second and a requester as `alias#short`,
  `<short>@<machine>` or "the person at <machine>". `channel env`'s
  "not in the channel" reads the roster, and the machine is matched
  case-insensitively against the org's directory. `member_json`, which the chart's
  member JSON also uses, carries `channels` only on a row in a channel. The
  M5 unit tests are `T/test_channels_roster.py`, in the `channels` part.
  A13 for the listing: `list`, `list --org`, `list --json`, `list
  --stopped`, `list --all` and `list --org --json`, from a terminal and
  from a session, identical to the merge base's over one store with no
  channel (ages normalised).
- 2026-11-21 — **M5's review, round 1, as fixed** (`4ab6784f`). `env`
  checks the terminal, the machine and then membership, and that last
  check (`_states`) reads only the session's own events in its project, so
  a refusal never reconciles or appends; its membership is what the
  thread's log states, so while a restatement is due a channel only the
  record holds is refused. A session with rows in two projects' views keeps
  the row of the project its newest membership points to (`_where_now`,
  `last_project`'s rule), in the roster, `list --channel --json` (which
  keeps exactly the roster's rows) and the pool; at a tie of two projects
  the roster keeps neither, as `_current_here` writes nothing then. A
  refusal answers a request only with a `reason` in `REASONS`. A pending
  request takes its target's machine and label from the last ended row
  this reader may still read, never put back in a roster. `member_json`'s
  `channels` follows the roster's test for an ended row. Reversed: the pool
  does not count queued `channel-env` appends (an `env` has a session
  writer, and the queue holds the operator's appends alone); it reads the
  merged log.
- 2026-11-21 — **M5's review, round 2, as fixed** (`10b8740a`). After the
  same-session move rule, a thread whose rows appear in several projects'
  views keeps the row with the newest `joined` in effect (`_newest_row`;
  a tie keeps neither), so a refill across projects is one row. `env`'s
  preflight requires the `joined` in effect to be stamped with the record's
  thread, still reading files alone. A pending target's fallback is the
  latest visible end, by its `retired` in effect.
- 2026-11-21 — **M6 as built** (`442c9784..563c4531`). The welcome's word
  is `Link.serves_channels` (§7 renamed: M1's `Link.channels` is the set of
  open channels' logs). The frame's set is `sminos_channels.frame_channels(
  session, holders)`, equal to `channels_of` filtered to channels' ids
  (pinned) but reading `set_holders()` once a publish, so a thread in no
  channel costs one lookup where MAWS lists `channels`; `made_of` takes the
  tuple, which is `()` without the word, so a flip of the word is covered;
  the lane A rule sits in `member_frame`. The replay plays all 112 lines of
  the fixture `ok`, with no amendment; the harness gains `AFTER = {(13, 4):
  (13, 2)}` (step 13.4 must match a frame sent after 13.2's, so the removal
  is proven), which amends no line. Case 13 is staged in a subprocess
  (`register`, then `change`), as a verb runs, so it does not race the
  uplink's thread. The stand-in's `known` takes the first 128 entries and
  then filters by the predicate (X5's reading); a suite's directory
  (`rl10_known_directory`) names a known log by the hello that opened it.
  The three-machine "return" is T1's end and return (`retire`, then the
  session running again); a removal and a re-add is its own case.

## Outcomes & Retrospective

Pending — written at finish.
