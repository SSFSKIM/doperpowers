# sminos environments, EN.G2 — a spawn placed in a channel, a VM in `channel show`, a notice in a channel's timeline: execution (2026-11-23)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **EN** (Environments), acceptance group **G2** (child id **EN.G2**).
> **Parent pin:** that file's blob `e0c6561fc1ff67850ae5415bfebbaa75a3b53387`,
> as `origin/main` holds it at `1b5b56f9`, which this branch has merged:
> the composite as its writer revised it from this plan's last section
> (pull request #621). The child's section in the
> composite is its spec. D4 is its design, binding where marked, with D3
> (Listing, The timeline, The lead), D5 and D7; X2, X3, X6, X7, X8 and X9 are
> its contracts; CH's document
> (`docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`: C1, C2,
> C5, C6, Y1 to Y3) is what it builds on. This document carries the
> constraints and the milestones and nothing of the design. It edits neither
> design: what it found against them is in its last section.
>
> **Read before M1:** the composite's Purpose, Terms, D3 (The timeline, The
> lead, Listing), D4 whole, D7, the sections EN and CH, X2, X6, X7, X8, X9,
> Risks and Deferred; CH's document, C1, C2, C5 and C6; G1's plan
> `docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md`, its
> Constraints, Interfaces §1 to §3, §7 to §10 and Concrete Steps' "M5, the
> scene"; CH2's plan `docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md`,
> Interfaces §2 (the doors) and §5 (the post); `sminos/CLAUDE.md`,
> `devcloud/CLAUDE.md` and, in `sminos/skills/sminos/scripts/CLAUDE.md`, the
> channel paragraphs and the paragraph on which hosts a thread owns.

A session on a Mac can open a thread on a cloud VM with one command (G1),
and threads from several repositories and machines can be gathered in a
declared channel and speak there (CH). The two do not meet yet. A thread
opened on a VM is in no channel until someone adds it. A channel's pool
lists the VM as a machine and says nothing of who pays for it or since
when. And the VM's idle and lease notices go to the one thread that owns
it and to that thread's project, so the other threads working with that VM
never see that it has idled for three days.

After this child:

- **One command opens a thread on a VM and places it.** `sminos spawn
  <alias> <task> --on <vm>|new --channel <channel>` opens the thread and
  it is in the channel, with nobody adding it.
- **A channel shows what its VMs are.** `sminos channel show <channel>`,
  run on a machine that has devcloud, lists each VM of the pool with the
  thread that owns it, how long it has run and what it has cost so far.
  Anywhere else it says that those facts are not shown, and why.
- **A VM's notice is in the channel's timeline.** Each notice a VM sends
  is also recorded, as that machine's notice and prompting no one, in the
  log of every channel whose pool holds the VM. `sminos chat <channel>`
  shows it from `devcloud@<vm>`.

How to see it working is the Acceptance below: suites that run a real
sminos and a real devcloud driver against stand-ins, and one check on the
owner's fleet at the end (M5), which is parent acceptance line 5.

## Progress

- [x] (2026-11-23) The code read against each acceptance clause (What is
  already built), and this plan written against the composite at the
  parent pin (sminos 1.55.0, devcloud 0.18.1).
- [x] (2026-11-23) `origin/main` at `6577f179` merged into the branch (sminos
  1.55.1: eight globs escaped in `S/sminos.py`, one TECH-DEBT row closed);
  the plan's first review (thirteen findings), the holder's rulings on
  four of them, and this revision (Decision Log, "The plan's review").
- [x] (2026-11-23) The plan's second review (ten findings), the holder's
  rulings on what the first revision had opened, and this revision, the
  last before the build (Decision Log, "The plan's second review").
- [x] (2026-11-23) The owner's answers to O1 and O6 (Decisions that are
  the owner's): O1 "지금까지 쓴 금액", the amount spent so far, as built;
  O6 "원문 그대로", the notice's own full text is what a host records in a
  channel (`CHANNEL_TEXT = "full"`, built in the whole-range fix wave).
  O2 to O5 build their defaults, unanswered.
- [x] (2026-11-23) M1 — A spawn placed in a channel. Commits
  14b80ade0..943becdb5, fixes 7ac6f0feb and 93a5f7097; review clean.
  GREEN on 93a5f7097: `sminos-idle` 32081, `sminos-channels` 4m06s.
- [x] (2026-11-23) M2 — `channel show`: a VM's owner, age and cost.
  Commit 628f11876, fix 42a9e9f16; review clean. GREEN on 42a9e9f16:
  `sminos-idle` 32236, `sminos-channels` 4m08s.
- [x] (2026-11-23) M3 — A VM's notice in the timelines of the channels
  whose pool holds it. Commits 66868f287..cc30634a1, fixes 3fcc5e4b0 and
  959533ca2; review clean. Built at O6's default (`CHANNEL_TEXT =
  "short"`); the holder has confirmed the owner has not answered, and puts
  it to them once more before the merge. GREEN on 3fcc5e4b0; on 959533ca2
  every gate but `devcloud-host` (an `apt-get` install that failed in its
  `devenv up`; no devcloud file changed, and it passed on its rerun):
  `sminos-idle` 32858, `sminos-channels` 3m35s.
- [x] (2026-11-23) M4 — What sessions are taught, what sits beside the
  code, and the gates on the final head. Commits 24c394442 and a8bd68be0,
  fix b554a06bb; review clean. GREEN on b554a06bb: `sminos-idle` 32105,
  `sminos-channels` 3m18s, `sminos-suites-c` 13m06s.
- [ ] The whole range read once (Decision Log, "Verification"), its fix
  wave, and the merge.
- [ ] M5 — The live check, on the merged change.

Each milestone's entry records, when it closes, the commit its gates were
GREEN on and the figure the `sminos-idle` gate read there.

## Acceptance

G2 of the composite's EN section, as observable items. "A Mac" is a machine
where devcloud's driver runs; "a VM" is a devcloud host, an adopted machine
included; `desk` is a declared channel the machine knows and `<desk>` its
id; `<sid>` is the first eight characters of the new session's id. Each
item is proved where Concrete Steps' proof map says.

1. **A thread opened on a VM is placed.** From a session on a Mac, `sminos
   spawn <alias> - --on <vm> --channel desk <<'EOF' … EOF` prints the line
   `seat spawned on <vm>: …` and then `<alias>#<sid>: in desk`, exit 0.
   On the VM, the new thread's project log holds its `channels` statement
   naming `<desk>`, under the new session's writer and after its
   `joined`; no request is written into `desk`'s log. Once the VM's events
   arrive, `sminos list desk` on the Mac lists the thread and `sminos
   channel show desk` lists `<vm>` in the pool with one live thread.
   `--channel` given twice places the thread in both channels. `--on new`
   does the same after the VM is made. The spawner need not be in `desk`,
   and the new thread is in no channel that was not named.
2. **A thread spawned here is placed.** `sminos spawn <alias> <task>
   --channel desk` with no `--on` prints `seat spawned: …` and
   `<alias>#<sid>: in desk`. With `--wait` the thread is placed before
   the wait begins. A spawn onto a stopped seat that is already in another
   channel leaves it in both, and its statement is written under the
   refill's new writer.
3. **The new thread can reach its spawner and its channels by what it was
   told,** on a VM whose sminos is this change's. Spawned with `--on …
   --channel`, its preamble gives the spawner's address as `@<the
   spawner's project id>/<the spawner's short>`, and that tag, run on the
   VM when the thread starts, reaches the spawner's session whatever a
   member of `desk` in another project is called (one whose alias is the
   spawner's short included). The address is checked when the thread is
   admitted and is kept apart from other projects' aliases; it is not
   bound to the spawner afterwards, and the preamble says to answer by
   the reply line of the spawner's latest message once there is one.
   Every command the preamble and the Mac's lines give names a channel by
   its id and a thread by its session's whole id, and run as printed it
   reads or writes that channel's log and names that thread, on a machine
   where another log answers to the name `desk` and a local member's
   alias is the remote session's short.
4. **Refused before anything is made or launched,** each saying why: a
   `--channel` name that no log answers, that several answer, or that is a
   project's (exit 4, in the words `sminos channel add` gives for it);
   more than 128 distinct channels; a channel whose log this machine's
   enrollment does not carry; with `--on`, a spawner whose project id
   cannot be written as a tag's qualifier. All of those are decided on the
   machine the command is typed on, with `--on` before devcloud is called
   (no VM is made). Then the placing machine's own: an endpoint whose kept
   welcome lists no `channels`; a channel it already knows and does not
   carry; the spawner's address naming someone else there, or several
   (`spawner-shadowed`). With `--on` these are the VM's refusals, shown as
   the VM's line with exit 1, and a VM that `--on new` made is said to be
   kept and whose it is.
5. **A machine that has kept no welcome yet is waited on, not refused.**
   Where the VM's sminos has no kept welcome to read (none written yet,
   or one that cannot be read), `--on` says what it waits for and tries
   again within G1's one wait of eleven minutes, and spawns when the
   welcome is kept. At the wait's end no thread was opened, the exit is
   75, and the words say that the same command with `--on <its name>`
   opens it later. Without `--on` the same state is a refusal that says
   the welcome is not kept yet, never that the endpoint serves no
   channels.
6. **After the launch nothing is a refusal.** A placement that cannot be
   recorded once the session runs leaves the thread opened and says, in
   one warning for each channel, that it was not placed, why, and the
   command that places it; the exit is 0, as it is for a spawn whose
   `joined` could not be written. The reasons: the thread's record holds
   an unfinished operation; the thread is at 128 channels; the channel's
   log is there and cannot be read; the channel's registration on the
   placing machine is missing, retired or not carried when the placement
   reads it again, or the machine's own enrollment is no longer the
   request's; the time for placing ran out (on the placing machine all of
   a spawn's placements wait 30 seconds together at most, a lock that
   another process holds included); and, under `--worktree`, the seat
   landed in a project the VM's enrollment does not carry, where no
   placement is made at all and the Mac says that none of the placements
   asked for was made and that this project's memberships will not be
   seen from here, without saying which channels the thread is in (a
   refilled seat keeps what it held). A VM whose sminos predates this
   change opens the thread, and the Mac says that the VM did not carry
   out the placements asked for, again without saying which channels the
   thread is in. Where the call to the VM is lost after the launch (the
   Mac's own wait for the call can end while a healthy VM is still
   placing), the Mac says, as G1 does, that the outcome is not known and
   that nothing should be spawned again, and gives one command that lists
   every seat on the VM whatever its project, run from the VM's login
   directory, and one for the engine's jobs, and says that a channel
   which does not list the thread shows nothing about whether it was
   launched. Exactly one session was launched in every one of these
   cases.
7. **`channel show` on a Mac.** For a pool that holds a VM, the VM's line
   reads `<vm>  1 live, 0 stopped  vm owned by <alias>#<short>, up 3d4h,
   12.34 EUR so far`: the thread that owns it by devcloud's own word, its
   age to the minute as `devcloud vm ls` prints one, and what it has cost
   at its type's list price. After `devcloud vm owner <vm> <thread>` the
   line names the new thread. An adopted machine reads `adopted, owned by
   …`, with no age and no cost. A machine devcloud has no host for keeps
   today's line, and "added by hand" stays where it was. `--json` gives
   each such pool entry a `vm` object and the answer a `devcloud` object
   (Interfaces §3).
8. **`channel show` where the answer is missing or partial.** On a machine
   with no devcloud CLI, with a devcloud older than 0.19.0, or on a
   devcloud host, the pool prints as today and one line after it says that
   a VM's owner, age and cost are not shown here, and why. Where devcloud
   is asked and gives no whole answer (no answer in time, another exit,
   output that is not the answer, a number that is not finite), the line
   says that instead. Where it answers and its coverage is partial, one
   line for each cause says so: an account it could not list, an account
   it did not reach in its time, an account this Mac's profile never used
   (a VM another Mac made there is not seen from here), and a name two
   hosts answer to (neither is shown). The hosts it did read keep their
   suffix. In every case the members, the requests, the two counts and
   the exit status are what they were, and `--json` says the same in its
   `devcloud` object.
9. **A notice in the timeline.** A VM whose machine is in the pool of
   `desk` (a thread of it runs there) and of `ops` (a member added it by
   hand), and in no pool of `other`, sends its idle notice or its lease
   warning. Afterwards `desk`'s and `ops`'s logs each hold one `human`
   event under `<vm>/human` with `notice` `devcloud` and `to` `"*"`, whose
   text is the notice's own full text (O6, the owner's answer of 2026-11-23), the
   repositories with unpushed work named, and `other`'s holds none. `sminos chat desk` on
   another machine prints it from `devcloud@<vm>`. No frame is delivered
   for it, no thread is woken, the lead of `desk` is not addressed, and
   the manager's reading of what the owner said leaves it out. The pool
   tested is the pool as the VM's own copy of the logs holds it then: a VM
   that has not read its removal from a pool still records there, and a
   hand-add by a member the VM may not read is not honoured (both pinned
   by tests, and said where the code is described).
10. **The notice's own delivery is unchanged.** To the thread that owns
    the VM, on to its project's live members, then into its project's log,
    then the journal and `wall`: each step runs with the arguments, the
    full text and the order it has today, whatever became of the
    channels' record. On a host whose sminos does not know `--pools`, the
    host says so in its journal and sends nothing a second time. On a
    machine in no pool, nothing is recorded and the call exits 0. On a
    host whose writer still waits for its head after enrolling, the call
    exits 0 saying that it waits, the host calls nothing again, and the
    channel's log holds exactly one such event once the uplink has
    released it.
11. **Nothing else changed** (parent acceptance line 8 for this surface).
    A `spawn` without `--channel` (its banner, its preamble, the request
    it sends a VM and the outcome line it reads), a `say` without
    `--pools`, and `channel show` of a channel whose pool holds only the
    machine it is run on print and exit as before, byte for byte against
    the merge base, in every spelling the help documents. Two undocumented
    ones stop working: `--c` for `spawn`'s `--cwd` and `--p` for `say`'s
    `--project`, which the parser took as unique prefixes and now refuses
    as ambiguous. Nothing is added to the daemon or the uplink, and the
    `sminos-idle` gate reads what it read.
12. **What sessions are taught is true** (X6): `sminos help`, the two
    skills and the spawn preamble say what the tree does, and the changes
    to the skills and the preamble were evaluated.
13. **On the fleet.** On the merged versions, M5's scene runs and each of
    its expectations is observed, or it is reported as not run with what
    is missing. This plan claims item 13 only when it ran.

## What is already built

Read in the code at the parent pin, clause by clause.

| G2's clause | Built | Missing |
|---|---|---|
| `spawn --on … --channel` places the new thread | A thread's own add of a channel: `sminos_channels.change(thread_id, channel, "add", session)`, a journaled write of the record and one `channels` statement (CH1). Finding a channel by name, the one refusal for a name several logs answer (`find_channel`), registering one by id (`register`), the capability test (`sminos_audience.advertised("channels")`), the uncarried refusal (`_refuse_uncarried`). `spawn --on` whole (G1): the request, the VM side, the outcome line. | Everything of `--channel`: `spawn` has no such flag, the request to a VM carries no channel, the outcome line reports none, and nothing calls `change` at a spawn. |
| `channel show` lists the VM with its owner, age and cost | `pool(channel, rows)`: one entry a machine with `live`, `stopped`, `by_hand`; `show` prints it, with `--json` (CH1). sminos's finder and bound for devcloud's CLI (`sminos_threads.find_devcloud`, `devcloud_version`, `devcloud_timeout`, `stop_tree`), used by `owned_by`. devcloud knows every fact: `devcloud vm ls --json` has `creator`, `created`, `spent` and `currency` a row. | A question sminos can ask. `vm ls` runs the reaper and probes every host over ssh before it answers, and reports a partial fleet as whole; `vm owned-by` (X9) answers by owner, not by host, and carries neither age nor cost. Nothing in `show` asks devcloud or says that it cannot. |
| A notice in the timeline of each channel whose pool holds the machine, marked, never the owner's post | The marker and every reader of it (X8; G1's M1 and CH2's M4, M8 and M9): `sminos say --notice devcloud --in <channel> <text>` writes an untagged marked `human` event from a machine that holds no member of the channel, the lead rule leaves it out, `chat` shows `devcloud@<machine>`, the manager's classifier does not take it for the owner's, a tagged one is delivered as a peer's frame whatever the endpoint's word. Tests: `test_channels_say.Words`, `test_channels_lead` (three cases), MAWS's fixture case 19. | The sender. A host's delivery (`devcloud/boot/devcloudlib/notices.py`) names no channel, and nothing tells it, or computes for it, which channels' pools hold its machine: CH2 lets a notice into any channel registered on the machine "with no check of the pool" (its open point 2). |

So the third clause's reading half is whole, and G2 builds three senders'
halves on machinery that exists. It adds no event kind, no field of an
event, no frame, no lock, no record key and no duty of the daemon or the
uplink.

## Words this document adds

The composite's Terms define the owner, thread, project, log, writer,
member, channel, pool, deliver, wake, the daemon, the hub, the endpoint,
reach and devcloud. G1's plan defines a host, the driver, the boot
library, the descriptor, the owning thread, enrolled, a marked event, the
Mac side and the VM side of `spawn --on`, the outcome line and the recipe
hash; they mean the same here. Added:

- **The placing machine** is the machine a spawned thread runs on: this
  machine for a `spawn` without `--on`, the VM for one with it. Only it
  writes the thread's statement.
- **The request** is the JSON value of `--asked-from`, which the Mac side
  sends the VM side (G1's Interfaces §8).
- **The chain** is a host's delivery of one notice as G1 built it: the
  owning thread, then its project's live members, then its project's log,
  then the journal and `wall` (`notices.deliver`).
- **The channels' record** is what M3 adds after the chain: the notice
  written into the log of each channel whose pool holds the host. **The
  full text** of a notice is what the chain carries today; **the short
  text** is the one composed for a channel (Interfaces §5).
- **The kept welcome** is what a machine's uplink wrote down of its
  endpoint's last welcome, its capabilities among it
  (`sminos_audience.keep_capabilities`); a machine that has not connected
  since it enrolled has none.
- **The qualified address** of a session is `@<its project's id>/<its
  short>`, the form a frame's reply line gives (`sminos.reply_line`).
- **The stand-ins**: `sminos/tests/devcloud_standin.py` plays devcloud's
  CLI for sminos's suites; `devcloud/tests/fixtures/sminos.py` plays sminos
  for the host's integration tests; the boot library's unit tests inject
  `call` and `say`; `sminos/tests/endpoint_standin.py` plays MAWS's
  endpoint.
- **`S/`** is `sminos/skills/sminos/scripts/`, **`T/`** is `sminos/tests/`,
  **`D/`** is `devcloud/`.

## Constraints that bind every milestone

- **The designs have one writer,** the session that holds the composite.
  This document's controller records decisions and discoveries here and
  sends that session whatever touches the child's purpose, its acceptance,
  a contract or a binding decision; it edits neither design. A statement
  the code makes unbuildable stops that part and goes to the holder with
  the evidence; the rest is built.
- **What binds, by id.** D4's marked decisions: sminos places and devcloud
  provisions (no scheduler); the pool constrains nothing and chooses
  nothing; a VM is owned by the thread that made it and devcloud is the
  authority for who that is; sminos keeps no copy of what a thread owns; a
  VM that `--on new` makes is kept. D3: a message belongs to one log; a
  channel's log never carries a `message`, a `question` or an `answered`;
  a machine's notice is never read as the owner's post. C1: a channel's
  view has no members, and nothing is published under a channel id. C2:
  a thread that adds itself writes a statement and no request. X8 as the
  composite carries it. X9 unchanged: its command, its reply and its
  matching. D7 and X7: nothing here may need both machines updated at
  once (Interfaces §6 is the table, and it binds). And the holder's
  rulings of 2026-11-23 on this plan's review, each stated where it binds
  (Decision Log, "The plan's review"): a spawn onto a stopped seat places
  by the thread's own statement; the pool a host tests is the pool its
  own copy of the logs holds; what a host records in a channel is the
  notice's full text (O6, the owner's answer of 2026-11-23); the child's address
  for its spawner is checked in the form the child will use.
- **Nothing new on the wire or in a log.** No event kind, no field, no
  frame, no capability. A notice in a channel is the `human` event with
  `notice` that every copy from 1.53.0 reads; a placement is the
  `channels` statement CH1 writes. So no reader ships ahead of a writer,
  MAWS is asked for nothing, and the vendored RL10 fixture is not touched.
- **Nothing in the daemon, nothing in the uplink.** Every path this child
  adds is a command's: `spawn`, `say`, `channel show`. No tick, no pass
  and no consumer-thread path gains a line, so a machine that holds no
  channel pays nothing more a tick and the consumer thread does nothing it
  did not do (C1); a host's notice queued behind its writer's head is one
  more caller of the promotion a terminal's post into a channel already
  has there. The `sminos-idle` gate is the check: its limit is
  33,570 Python calls a second and the merged head of CH2 read 32,261,
  with about 2.6% between runs. A milestone that finds it must add to
  either says so, with the reason, before it does.
- **No new writer in sminos's store.** A placement is `change`, the
  journaled operation `channels` through `set_channels`, under the locks it
  takes today and in today's order (the delivery lock, the seat's
  lifecycle lock, the wake lock, a store lock, a log's lock). A channel a
  VM does not know is registered by `register`, as `channel create`
  registers one. The channels' record is `say`'s own append under the
  machine's human writer.
  `channel show` writes nothing beyond what reading a roster already
  reconciles.
- **A refusal comes before its side effect; after a launch nothing is a
  refusal.** Whatever can be known before a VM is made or a session is
  launched is decided then and writes nothing. Once the launcher has
  returned a job, a placement that fails is said and the spawn stands
  (acceptance 6): the session runs, and a refusal would leave it running
  under a line that says nothing was spawned.
- **One deadline for what a spawn waits on after its launch, on the
  machine that places.** Registering a channel and every placement share
  one bound there, and no wait inside the placement is without it: a
  lock that another process holds costs that placement, never the others
  or the outcome line. The guarantee is of the placing machine's own
  waits and of nothing else: the asking Mac's wait for the call counts
  from before devcloud found the host and ssh connected, and the VM
  cannot know how much of it is left. A call that the Mac gives up on
  while the VM still works is G1's outcome that is not known, and its
  words say to look, where to look, and not to spawn again.
- **What is placed is decided from what the files say then.** At the
  placement the machine's identity, the org's directory and each
  registration are read afresh (`sminos.forget_caches`, the read a long
  process already makes), never from what the process read before the
  launch.
- **What a thread or a person is told to run resolves where it is run.**
  A command this child prints or renders names a channel by its id and a
  thread by its session's whole id, never by a name or a short that
  another log or another member on that machine may answer to. A name,
  and `<alias>#<the session's first eight characters>` (never the
  outcome's `short`), appear in prose and in a line's label. One address
  keeps a short on purpose: the spawner's, which is the reply line's
  form, checked at admission (R17).
- **Byte for byte without the new flags, in the documented spellings**
  (acceptance 11; the holder's ruling of 2026-11-23). The parser takes a
  unique prefix of a long flag, and two prefixes that were unique are not
  any more: `spawn --c` (`--cwd`, beside `--channel`) and `say --p`
  (`--project`, beside `--pools`). Both become argparse's ambiguity
  error, exit 2; no alias keeps them, and the comparison with the merge
  base's parser lists them as its two known differences and finds no
  third. `--channel` and
  `--pools` are read only where given. A request, an outcome line, a
  preamble and a banner gain a key, a sentence or a line only where a
  channel was asked, never an empty one; and `channel show` prints
  anything new only for a pool that holds a machine other than the one it
  runs on.
- **`pool` stays what it is.** `sminos_channels.pool(channel, rows=None)`
  keeps its signature and its entries' four keys (`machine`, `live`,
  `stopped`, `by_hand`). What devcloud says of a host is joined in `show`
  and nowhere else, so that the channels' record, which reads the pool on
  a host, never asks devcloud.
- **One finder, no second ssh** (G1). sminos finds devcloud's CLI with
  `sminos_threads.find_devcloud`, reads its version with
  `devcloud_version`, bounds it with `devcloud_timeout` and stops it with
  `stop_tree`, as `owned_by` does, and reaches a host only through
  `devcloud vm ssh`. devcloud's host finds sminos with `sminos_host.cli`.
- **A host's boot library is never updated.** What M3 puts in
  `D/boot/devcloudlib/notices.py` runs on a host for that host's life, with
  whatever sminos the host has then. Its call and the exits it reads are
  fixed in Interfaces §4 and §5 before it is built, and reviewed from both
  sides in M3.
- **The recipe hash moves** (M3 changes `D/boot/`): once the Mac's devcloud
  is the merged one, `vm up` takes the slow path in each account and
  architecture until an image is built again, as after G1. No image build
  belongs to this child's landing. M3 is the only milestone that touches
  `D/boot/**`, and none touches `D/image/**`.
- **Tests are hermetic.** No test reaches a real devcloud profile, a real
  cloud, a real host, the real `claude` or the real hub. sminos's suites
  keep `T/devcloud_isolation.py` (or `devcloud-isolation.sh`) as their
  first import; the driver's tests run the real `provider.Client` against
  `D/tests/fixtures/provider`; the boot library's tests inject `call` and
  `say`. Temporary `HOME` and `SMINOS_HOME`, invented names.
- **No production command, no cloud call** until M5, which says exactly
  what it runs.
- **Gates run on GitHub Actions, never on this machine.** `ci-gate`, run
  from the worktree, tests the committed HEAD. While building, one focused
  test file at a time is fine; a gate's own command is not run locally to
  verify a commit. A red gate that the base also shows, or that a recorded
  reason names, is not this change's.
- **Which gates cover what.** `sminos/**`: `sminos`, `sminos-suites-a`,
  `sminos-suites-b`, `sminos-suites-c`, `sminos-channels`, `sminos-idle`,
  `sminos-mods`, and through their paths `issue-tracker` and `board-api`.
  `devcloud/**`: `devcloud-unit` (discovered), `devcloud-image`,
  `devcloud-host`, `devcloud-systemd`, `devcloud-mods`, and
  `sminos-on-devcloud` for `devcloud/driver/**`. Every change:
  `shell-lint`, `repo-checks`, `version-bump`. A new test file of sminos is
  added to one list of `T/run-sminos-tests.sh` (`run_channels` for a
  channel's suites, the end of `run_suites_c` for the rest) or it does not
  run.
- **Versions.** `scripts/bump-version.sh --plugin sminos 1.56.0` in the
  first commit that changes a file sminos ships (M1), and
  `scripts/bump-version.sh --plugin devcloud 0.19.0` in the first that
  changes one devcloud ships (M2); never a hand edit; each the next minor
  above `main`'s when `main` has moved past it by the merge. One bump a
  plugin for the branch. No other plugin's files change.
- **The repository is public.** No hostname, address, account, project id
  of the fleet, secret name or value, and no path of a person's machine,
  in code, a test, a comment, a commit message or this document. Names in
  tests are invented (`dc-x-0001`, `desk`, `example/repo`).
- **`S/sminos.py` is one file of some twenty-one thousand lines.** What
  this child reads and decides goes in `S/sminos_channels.py`,
  `S/sminos_on.py` and `S/sminos_threads.py`; `S/sminos.py` is changed at
  the seams each milestone names. `origin/main` is merged as the build's
  first step and at milestone boundaries, never inside one.
- **What sits beside the code is written with it.** Each milestone updates
  the help of what it changed (`S/sminos.py`'s module docstring,
  `D/driver/cli.py`'s) and `S/CLAUDE.md`, `devcloud/CLAUDE.md` and
  `devcloud/README.md` for its part. What sessions are taught (the two
  skills, the preamble's sentence as evaluated) changes in M4, through
  doperpowers:writing-skills; one exception because code renders it: M1
  adds the preamble's sentence with the code that fills it, in the words
  of Interfaces §1, and M4 evaluates it.
- **Every milestone ends green.** A test that pinned behaviour a milestone
  changes is changed in that milestone to pin the new behaviour, never
  deleted for failing.
- **Accepted, and not built** (each a TECH-DEBT row written in M4, with
  what would promote it): a host built before this change records no
  notice in a channel, for its life; a thread runs in no channel between
  its launch and its statement, and its start guide, read in that window,
  lists none; `channel show` asks devcloud at each call and keeps nothing;
  what it shows of a VM is what the asking Mac's devcloud profile can
  list, and its cost is the type's list price times its age, not a bill;
  a host still downloading the org's logs can miss a pool it is in (the
  row "A machine still downloading a project's log reads a member's
  absence as a fact"); a machine added to a pool by hand stays listed
  after the org retires it, until a member removes it; a host records a
  notice in a channel it was removed from while it has not read the
  removal, and records none for a hand-add it may not read (the pool is
  its own copy's); a thread spawned without `--channel` and added to a
  channel afterwards keeps the bare short of its spawner in its preamble,
  which a channel-mate's alias of the same text takes (CH2's order of a
  bare name: an alias before an id); the qualified address a placed
  thread is given is good for the spawner as it was at the spawn: once
  the spawner has moved to another project or handed off to another
  session, a member of that project who has taken the short as an alias
  is who the address reaches, alone and with no error; a 1.55 VM asked
  for channels checks and gives the bare short as before, also on a
  refill of a seat that already has channel-mates; without `--channel`
  the lost-call words keep G1's inspection (`sminos list` over ssh),
  which reads one project from the login directory and can miss the
  seat; an account the
  asking Mac's profile never used is coverage `channel show` does not
  have, and says so.

## Plan of Work

Three behaviours, each a milestone that holds one contract between two
programs with both of its sides: the Mac and the VM of `spawn --on` (M1,
both sminos), sminos and devcloud's driver (M2), a host's boot library and
the host's sminos (M3). A reviewer of one milestone reads a producer with
its one consumer. M1 comes first because it carries the risk (the only
path of this child that runs after a launch, and the address a placed
thread is given) and the sminos version. M2
and M3 consume nothing of M1 and nothing of each other but
`sminos_channels.pool`, which exists and which none of them changes. M4
changes what is taught once every behaviour it describes exists, and runs
every gate on the final head. The whole range is then read once and
merged by the composite's holder. M5 runs on the merged change, the only
place a Mac and a VM both run this code. Who reviews what, and at which
rung, is the Decision Log's first entry ("Verification").

### M1 — A spawn placed in a channel

**At its end:** acceptance 1 to 6, and 11 for `spawn`. `sminos spawn …
--channel <channel>` places the new thread, here or on a VM; the sminos
plugin is 1.56.0.

**Touches:** `S/sminos.py` (the `spawn` parser; `cmd_spawn`, `spawn_here`
and `spawn_fresh` at the seam the placement needs; `render_preamble` and
the words it is given for the spawner; the module docstring's `spawn`
lines), `S/sminos_on.py` (the Mac's check of the names and of the whole
request, the request, the VM side's checks, `WHYS` and `WAITED_ON`,
`hold_to_spawner`, `Answering.ok`, `outcome_whole`, the Mac's lines),
`S/sminos_channels.py` (what is decided before a launch, the placement of
a spawned thread, `register`'s deadline), `S/sminos_audience.py` (the
three-valued read of a kept capability),
`sminos/skills/sminos/references/spawn-preamble.md` (the place the
sentence is rendered into), `T/test_on.py`, `T/test-on.sh`,
`T/test_channels_spawn.py` (new), `T/test-channels-machines.sh`,
`T/run-sminos-tests.sh`, `S/CLAUDE.md`, the sminos version.

**Interfaces:** exposes Interfaces §1. Consumes, unchanged:
`sminos_channels.find_channel`, `change` (with its `lock_until`),
`_refuse_uncarried`, `OWN_FAILED`, `LIMIT_REFUSAL`; `sminos.flocked`,
`_resolve_tag`, `leading_tags`, `reply_line`'s form of an address,
`known_project`, `not_carried`, `valid_name`, `is_channel_id`;
`sminos_audience._read_kept`; `sminos_on.read_request`, `Answering`,
`outcome_whole`, `carried`, `remote`. Widens, each by an argument whose
absence is today's behaviour: `sminos_channels.register` (a deadline for
its lock) and `sminos.spawn_fresh` (what the placement needs).

**Seams:** none with an earlier milestone. With what is built: CH1's own
add, crossed by `T/test_channels_spawn.py` (a real spawn, then the record
and the statement as CH1's readers take them: `roster`, `channels_of`)
and, between machines, by `T/test-channels-machines.sh`, whose machines
run daemons and whose `claude` is the test engine: a thread spawned with
`--channel` on `beta` is in the roster and the pool as `alpha` reads
them. And G1's request, its preflight and its outcome line, crossed by
`T/test-on.sh`, where the VM side runs for real on a second home (that
suite starts no daemon, so what it shows of the placement is what the
VM's own store holds).

**Decisions:** R1 to R6, R17 to R21 and R24 of the Decision Log, and O5.
And, seen in the code:

- **The thread's id is the seat's, the session the launch's.** A spawned
  thread's record is its seat's (`spawn_fresh` returns `seat` and
  `session`), and `change(seat, channel, "add", session, lock_until)` is
  the call. It needs the session to be a member of its project, which the
  launch's journaled `joined` makes; where that `joined` was left to the
  next reading verb, `change` finishes the entry first, and where it
  cannot, it answers `entry` or `between` and the warning of acceptance 6
  is said.
- **Where the placement runs.** After `spawn_fresh` has released the
  seat's lifecycle lock and before `--wait` begins to watch
  (`finish_turn`), so a thread watched for its first turn is already
  placed. A `retire` or a `fill` of the seat that lands between the
  unlock and the placement is answered by `change` itself (`moved`,
  `vacant`) and said as acceptance 6 says.
- **One deadline for all of a spawn's placements** (R18). It is fixed
  when the placement begins, `PLACE_BUDGET` from then, and every wait
  inside takes what is left of it: the registration's lock (`register`'s
  new argument, down to `flocked`'s `lock_until`) and `change`'s
  `lock_until`. A channel whose turn comes after the deadline is not
  tried and is reported `time`; one whose lock was busy past it likewise.
  It bounds the placing machine's waits and promises nothing about the
  Mac's: the request carries no time, since the Mac's figure would count
  from before the driver found the host.
- **Read afresh at the placement** (R21). The placement opens with
  `sminos.forget_caches()`, which drops the invocation's enrollment, the
  org's directory and every registration read (it is what `remote`
  already calls before each try), then holds this machine's enrollment to
  the request's org and reads the seat's project and each channel again.
  No new machinery: the window left is between those reads and `change`'s
  write, which is `change`'s own.
- **The VM side prints no placement line.** Its standard output is passed
  through to the Mac, which prints its own from the outcome line. A
  placement on the VM side raises nothing past `Answering`: every way it
  ends is one entry of the outcome's `channels` (Interfaces §1), since an
  exit or an exception after the launch prints no outcome and the Mac
  then says the spawn is not known.
- **The Mac resolves names, checks the whole request, and only then calls
  devcloud.** A name is a label on one machine's registrations and an id
  always works (the composite's D3), so the Mac resolves each `--channel`
  with `find_channel`, folds the ids, holds the folded list to the shape
  the VM will hold it to (`read_request`'s own test, run on the outgoing
  request), and does all of it after it has checked that this machine is
  enrolled and before it looks for devcloud. A request the VM would
  refuse for its shape is never the reason a VM was made.
- **The address a child placed in channels is given is the one a frame's
  reply line gives** (R17): `@<the spawner's project id>/<short>`, which
  `_resolve_tag` reads in that one project, by id before alias, and never
  through a roster. That is a check at admission and a wall against other
  projects' aliases, and no more (R17). `hold_to_spawner` asks the
  resolver that same tag,
  built by the one function that builds the preamble's, so what is checked
  is what the child will run. Without `--channel` both stay G1's bare
  short, byte for byte.
- **The order of the VM side's checks.** After `hold_to_spawner`: the kept
  welcome (unknown: `welcome-unknown`, which the Mac waits out; a welcome
  that lists no `channels`: a refusal), then for each channel it knows,
  that its enrollment carries it. Nothing is registered before the launch:
  a channel the VM does not know is registered when it is placed, so a
  refused spawn leaves no registration behind.
- **Carriage is read again at the placement** (R21), from the
  registration as it is then and against the request's org: a
  registration made meanwhile by an older copy, without a hub, is kept by
  `register` and would otherwise be placed into.

**Does not touch:** `change`, `set_channels`, `place`, `carry_due` or any
path of a request; `fill`, `seat add`, `resume`; a spawn's preamble and
preflight without `--channel`; the daemon and the uplink; devcloud; the
two skills.

**Proves:** acceptance 1 to 6 and 11 (a spawn). Its tests, each of which
fails without the behaviour it names:

- *The statement.* It is the one an own add writes (C2's fields, after
  the `joined`, under the new writer), and the channel's log gains no
  event. A refill with `--channel` adds to the set the thread holds, and
  its statement is under the refill's new writer, not the displaced
  session's.
- *Before devcloud.* `vm up` and `vm ssh` are not called when a name is
  refused on the Mac; 129 distinct channels are refused there; more than
  128 `--channel` values that fold to a valid set are accepted and sent
  folded; a project id that fits no qualifier is refused there.
- *The address.* A member of a requested channel, in another project,
  whose alias is the spawner's short: the VM side's check passes, and the
  preamble's tag, run as the child on the VM once it is placed, reaches
  the spawner. A member of the spawner's own project whose alias is the
  short: `spawner-shadowed`, nothing launched. The bare `@<short>` run by
  that same child is pinned as reaching the channel-mate, which is the
  limit this decision is for.
- *The commands as printed.* On a VM that knows `<desk>` as `ops` and
  another channel as `desk`, and on a Mac where two channels answer to
  `desk`: each command of the rendered preamble and of each of the Mac's
  lines is run as printed and reads or writes `<desk>`'s log. The Mac's
  `channel add` for a thread not placed on the VM, run as printed on a
  Mac that holds a local member whose alias is the remote session's
  first eight characters: the request written names the remote thread
  and its session, and the local member is not asked. A line's label
  shows the session's first eight characters where the outcome's `short`
  is another value (the fixture's `spawned` already gives two).
- *The welcome.* No kept welcome on the VM: `welcome-unknown`, waited on
  and spawned once the file is there; a welcome with a capabilities list
  that lacks `channels`: refused at once; the wait's end: exit 75, no
  launch. The same two states for a spawn without `--on`, each with its
  own words.
- *Time.* With the stand-in holding the call for a while before the VM
  side starts, and a lock held by another process on the second of two
  channels: the placement ends `PLACE_BUDGET` after it began whatever
  came before it, the first is `applied`, the second `time`, the outcome
  line is whole, one launch. The same with a Mac's bound that ends while
  the VM side still waits on that lock: the Mac says not known and exits
  non-zero, the VM's own store holds the seat and the first statement,
  and one launch was made. No test withholds an outcome line to stand
  for a reserve: none is claimed.
- *Looking after a lost call.* The inspection command the Mac printed is
  run as printed from the VM's login directory, outside the seat's
  repository, and lists the seat; the words hold the engine's command
  and the sentence that a channel which does not list the thread shows
  nothing about the launch.
- *Carriage.* A registration without a hub made between the pre-launch
  check and the placement: `not-carried` for that channel, the others
  placed. A channel the VM already knew, retired in the org's directory
  between the two (the directory's file rewritten while the stand-in
  engine launches): `not-carried`. The VM's identity gone, or of another
  org, by then: every channel `identity`, no statement written. A
  `--worktree` spawn onto a stopped seat that is already in one of the
  requested channels, landing in a project the VM does not carry: no
  statement written, each channel `project-not-carried`, the seat's
  record still holds the channel it held, and the Mac's lines say that
  no placement asked for was made, name no channel the thread is or is
  not in, and hold neither "once it is listed here" nor a `channel
  add`.
- *The shapes.* A request without `--channel` and its outcome are byte
  for byte G1's, and the merge base's parser and this one agree on every
  spelling of every flag of `spawn` but `--c`. A request's `channels`
  outside §1's shape
  ends the VM side with exit 2 and no outcome line; an outcome's
  `channels` outside it is an outcome that is not known. Each try of the
  Mac's wait sends the same channels. A VM that does not know the channel
  registers it under the id and the name sent, and one that knows it
  keeps its own registration. A spawn from a terminal with `--on <vm>
  --channel` places the thread.
- *An older VM.* With the merge base's sminos (1.55.1) extracted from git
  and run as the VM side, onto a stopped seat that is already in one of
  two requested channels and in a third: the thread opens, no `channels`
  comes back, the seat is still in the two it was in, and the Mac's line
  says the VM did not carry out the placements, naming no channel the
  thread is or is not in.

### M2 — `channel show`: a VM's owner, age and cost

**At its end:** acceptance 7 and 8. devcloud answers a program what a
named host is, and `channel show` prints it or says why it cannot, and
how much of the answer is missing; the devcloud plugin is 0.19.0.

**Touches:** `D/driver/info.py` (new), `D/driver/cli.py` (the verb and
the docstring's synopsis), `D/driver/ops.py` (only if `_spent` is shared
from where it is), `D/tests/unit/test_driver_info.py` (new),
`devcloud/CLAUDE.md`, `devcloud/README.md`, the devcloud version;
`S/sminos_threads.py` (the question, beside `owned_by`),
`S/sminos_channels.py` (`show`, the pool's lines), `S/sminos.py` (the
docstring's `channel show` lines), `T/devcloud_standin.py` (`vm info`),
`T/test_vm_info.py` (new), `T/test_channels_roster.py`,
`T/test-channels-machines.sh`, `T/run-sminos-tests.sh`,
`.github/ci-kit.yml` (the `sminos-on-devcloud` gate's run line),
`S/CLAUDE.md`.

**Interfaces:** exposes Interfaces §2 (devcloud's verb) and §3 (what
`show` prints and exports). Consumes, unchanged: `Context.census`,
`Context.bounded` and `remaining`, `adopt.records`,
`provider.never_passed`, a provider client's `types`;
`sminos_threads.find_devcloud`, `devcloud_version`, `devcloud_timeout`,
`stop_tree`; `sminos_channels.pool`, `roster`, `show`.

**Seams:** with M1, through the roster alone: a thread that `spawn
--channel` placed on another machine is what puts that machine in a pool.
`T/test-channels-machines.sh` crosses it: after M1's case there, `channel
show` on `alpha`, its devcloud stand-in answering `vm info` for `beta`,
prints `beta`'s line with its suffix. With CH1: every case of
`T/test_channels_roster.py` that pins the pool today runs unchanged, and
its new cases stage another machine's thread as that file does (`far`).

**Decisions:** R7 to R10 and R22 of the Decision Log, and O1 and O4. And:

- **Asked once a call, and only when it could matter.** `show` asks
  devcloud once, for every machine of the pool but the one it runs on,
  and not at all when the pool holds no other machine: a machine is never
  a host devcloud can describe from itself.
- **A machine's name is a host's name.** A host's boot sets its hostname
  to its devcloud name and sminos names the machine after it, which G1's
  `is_org_machine` already rests on; names are compared without regard to
  case on both sides. Where two hosts answer to one name so compared,
  devcloud reports both and sminos shows neither, saying so: an owner is
  never chosen between two rows.
- **Who the owner is, in words.** devcloud holds a short id (X9). `show`
  prints the thread it names as `<alias>#<short>` of that thread's
  current session, resolved by the rule a `@<short>` tag resolves by
  (X2), over the org's scope and without ending the command where nothing
  or more than one answers: then it prints the `@<short>` devcloud holds.
- **The providers work inside a budget, and the report has a margin
  beyond it** (R22). `--within` bounds the providers' calls
  (`Context.bounded`); sminos's cutoff is that budget and a fixed five
  seconds for the driver to start and to print. `info.py` walks the
  accounts itself, as `Context.census` does, because the census records a
  call that the budget cut short as an ordinary failed listing and goes
  on: which account ran out of time is recorded at that account, from
  the error and the time left there, never judged after the walk.
- **What X9 may leave unasked, an inventory may not call whole** (R22).
  X9's `unused` is sound for its question (a thread of this Mac owns no
  host in an account this profile never used) and says nothing of a VM
  another Mac made in that account, which can be in a pool. `vm owned-by`
  and X9 are untouched; `vm info` reports the same accounts under the
  same key, and `show` reads them as coverage it does not have.
- **The reply is held from both sides, field by field.** devcloud's unit
  test pins the reply's shape under a name that says who reads it, and
  sminos's `T/test_vm_info.py` builds the replies its stand-in plays with
  the driver's own module imported from this tree, as `T/test_on.py`
  imports devcloud's parser; the `sminos-on-devcloud` gate runs both
  files, so a change of the reply on either side fails in the change that
  makes it. sminos's own test of a reply (§3) is what its renderers
  trust: they are never given a value that test let through and they
  cannot print.

**Does not touch:** `vm owned-by`, `owned_by`, `owned_vms`, X9's reply and
either guard that asks it; `vm ls`; `D/bin/devcloud` and `D/boot/**` (a
host's CLI already answers exit 6 to every `vm` verb; where no Python
3.11 is on PATH the launcher's own answer is exit 1, which `show` reads
as no answer); `pool`; `sminos list`; the daemon's census.

**Proves:** acceptance 7 and 8, and 11 for `channel show`. Its tests,
each of which fails without the behaviour it names:

- *The driver.* `vm info` asks no host, runs no reaper and writes nothing
  (the fixtures' call records). A host in an account that could not be
  listed is absent and the account is in `unknown`, never a host with
  invented facts. Four accounts in order, the first listed, the second
  failing at once, the third stalled on its list (the fixture's `gate`),
  the fourth never started: the reply holds the first's hosts, `listing`
  for the second, `time` for the third and for the fourth, and comes
  within the budget and the margin. A type list
  that stalls: the host is reported with no cost. An account whose
  provider never passed is under `unused`. A name of another case finds
  its host; two hosts of one name are both reported.
- *The reading.* Each of these replies is no whole reply: `NaN` or an
  infinity in `created` or `spent`; a boolean or a string there; a
  provider's host with `created` null; an adopted host with a number
  there; a negative number; an entry of `unknown` that is no object, or
  lacks `account`; a host whose name was not asked. For each, the text
  and the `--json` renderers are run: the roster, the requests, the two
  counts and exit 0 are unchanged, and the one line says the answer was
  not whole.
- *Coverage.* A pool machine that is a VM in an account the asking
  profile never used (a second profile's, staged with the driver's
  fixtures): its line has no suffix, the line for an unused account is
  printed, and `--json`'s `coverage` is `partial`. An account not listed,
  and one not reached in time, each with its line. Two rows for one name:
  no suffix and the line that says so.
- *The edges.* `show` on a machine whose devcloud is 0.18.1 does not run
  it; a devcloud that never answers is stopped at the bound and the
  roster still prints; `--json` of a channel whose pool holds only this
  machine is byte for byte the merge base's.

### M3 — A VM's notice in the timelines of the channels whose pool holds it

**At its end:** acceptance 9 and 10. A host's notice is recorded in each
such channel's log by the host's own `say`, and read everywhere as CH2
already reads it.

**The text a host records is the notice's own** (O6, the owner's answer of 2026-11-23:
"원문 그대로"). What this milestone puts in a host's boot library is frozen
on every host built from it, and a text posted into a channel cannot be
recalled. It was built and reviewed with the short text, the default
while the owner had not answered; the answer changed one constant and
the tests that pin it, in the whole-range fix wave.

**Touches:** `S/sminos.py` (`say`'s `--pools` in the parser and
`cmd_say`'s branch, the docstring's `say` lines), `S/sminos_channels.py`
(the writer), `D/boot/devcloudlib/notices.py`, `D/boot/devcloudlib/idle.py`
and `lease.py` (each text's short form), `D/tests/unit/test_idle.py` and
`test_lease.py` (or one new file for `notices.deliver`),
`D/tests/fixtures/sminos.py`, `D/tests/integration.py` where its host
part reads the stand-in's calls, `T/test_channels_pools.py` (new),
`T/test-channels-machines.sh`, `T/run-sminos-tests.sh`, `S/CLAUDE.md`,
`devcloud/CLAUDE.md`, `devcloud/README.md`.

**Interfaces:** exposes Interfaces §4 (`say --notice <program> --pools`)
and §5 (the host's call and its text). Consumes, unchanged:
`sminos.known_channels`, `host_name`, `not_carried`, `notice_field`,
`notice_of`, `waits_line`; `sminos_channels.pool`, `speak`;
`notices.deliver`'s `MARKED`, `HELD` and `UNKNOWN`; `sminos_host.cli` and
`cut_over`; `idle.text`, `lease.warning_text`.

**Seams:** with M1: the pool a host is in is most often made by a thread
placed at its spawn. `T/test-channels-machines.sh` crosses it: with the
thread M1's case spawned on `beta`, and `gamma` added to the pool by
hand, `say --notice devcloud --pools` on each, then `chat` of that
channel on `alpha`, which holds both from `devcloud@beta` and
`devcloud@gamma`. With M2, by what it must not do:
`T/test_channels_pools.py` runs with a devcloud stand-in that records
every call and asserts none was made. With CH2: its tests of a notice in
a channel (acceptance 9's last sentences on delivery) run unchanged.

**Decisions:** R11 to R14, R23 and R24 of the Decision Log, and O2, O3 and
O6.
And:

- **The pool is the host's own copy's** (the holder's ruling, R23). The
  writer reads `pool(channel)` over one sweep of the rosters on the
  machine that sends, as `channel show` reads it there, and asks no one
  else; devcloud is never asked (Constraints). Both ways that copy can be
  wrong are limits, written into `S/CLAUDE.md` and `devcloud/README.md`
  with the code: a notice is recorded in a channel after a removal the
  host has not read (a host that was cut off when a member removed it, a
  thread of it that left); and a hand-add the host cannot honour from
  what it may read (`_by_hand` honours an event only through a row of the
  roster as the reader reads it) records nothing.
- **What goes into a channel is the notice's full text** (O6, the
  owner's answer; R23). `notices.py` holds one constant that says which
  of the two texts the channels' record takes, now `"full"`; each text
  keeps the function that composes its short form (§5), so the other
  answer stays one constant and its tests. Every reader of the channel's
  log reads the repositories' names, and a host that has not read its
  removal from a pool records one more notice there, names included.
- **One channel's trouble is that channel's.** The writer goes through
  every channel whose pool holds the machine: one it cannot write to (a
  registration its enrollment does not carry, a log that cannot be
  appended) is said and passed over, the rest are written, and the exit
  is 1 when any was passed over for a failure. A channel that has left
  this machine is passed over without a word.
- **The event is the one `say --notice … --in <channel>` writes today**
  with no tag: kind `human`, the machine's human writer, `to` `"*"`,
  `notice` the program, the text as given. It goes through the door a
  terminal's post takes (`speak`), so the read of the lead that door
  makes for a person's post is skipped by `--notice`, as it is now.
- **A queued append is a success.** On a machine enrolled moments ago the
  human writer waits for its upstream head: `say` queues the event, says
  that it waits (`waits_line`) and exits 0, and the uplink appends it
  once, later (the path a terminal's post into a channel takes today; the
  TECH-DEBT row on where that promotion runs covers this caller too). The
  host takes exit 0 as done whatever the lines say, and nothing in this
  milestone sends a text twice.
- **The host's part is one call after the chain,** made whatever the
  chain's steps returned and changing none of them; a failure of it
  changes neither the chain's outcome nor the host's lifetime.

**Does not touch:** the chain's three steps, their arguments, their text
and their exits; `say --notice` without `--pools`; the readers of a
marked event (`notice_of`, `notice_sender`, the lead rule, the manager);
a channel's delivery; `D/driver/**`; the descriptor (no key is added).

**Proves:** acceptance 9 and 10, and 11 for `say`. Its tests, each of
which fails without the behaviour it names:

- *The form.* `--pools` without `--notice`, inside a session, beside
  `--in`, beside a selector and before a text that opens with a tag, each
  refused before anything is written. The merge base's parser and this
  one agree on every spelling of every flag of `say` but `--p`, which is
  now refused as ambiguous.
- *Which channels.* A machine in no pool (exit 0, nothing recorded); a
  pool held by hand alone and by a stopped thread alone; two channels
  written and a third passed over; the same text recorded once a channel
  for one call.
- *The copy's two errors, pinned as stated.* A `channel-env` remove this
  machine's copy does not hold yet (written on another machine, not
  imported): the notice is recorded; once it is imported, the next call
  records nothing there. A hand-add whose writer's row this machine may
  not read: nothing is recorded.
- *Queued.* With the human writer waiting for its head: the call exits 0
  and prints the waiting line, no event is in the channel's log; after
  the release the log holds exactly one marked event with the text, and a
  second release adds none.
- *Between machines* (`test-channels-machines.sh`): the event written on
  a machine that holds no member of the channel (in its pool by hand)
  reaches another machine's copy of the channel's log.
- *On the host.* The fourth call's arguments, with the full text the
  chain's steps carry (and, with the constant set to `"short"`, the
  short text); that it follows each way the
  chain ends (sent at the first step, gone on, fallen to the journal);
  that exit 2 says its line and calls nothing again; that exit 0 with a
  waiting line calls nothing again; that a host with no sminos or not cut
  over makes no call; and that the short text of an idle notice and of a
  lease warning, which the constant can still choose, holds no
  repository's name where the full one does.

### M4 — What sessions are taught, what sits beside the code, and the gates on the final head

**At its end:** acceptance 12, and 11 whole. Every sentence a session
reads about spawning into a channel, a channel's pool and a VM's notice
is true of the tree; the two skills and the preamble's sentence were
changed through doperpowers:writing-skills and evaluated;
`docs/doperpowers/TECH-DEBT.md` holds what this child accepts; every gate
is GREEN on the final head.

**Touches:** `sminos/skills/sminos/SKILL.md`, `D/skills/vm/SKILL.md`,
`sminos/skills/sminos/references/spawn-preamble.md` and the tests that
pin its lines, `S/CLAUDE.md`, `sminos/CLAUDE.md`, `devcloud/CLAUDE.md`
and `devcloud/README.md` where a sentence became false, `README.md` and
`docs/whats-inside.md` only where what they say of `spawn`, `channel
show` or a VM's notice became false, `docs/doperpowers/TECH-DEBT.md`.

**Interfaces:** consumes everything; exposes nothing.

**Decisions:**

- **What changes in `sminos/skills/sminos/SKILL.md`:** the two `spawn`
  usages gain `[--channel <channel>]...`, with one sentence: the new
  thread is placed in each as it starts (the flag adds memberships, and
  without it none is added; a refilled seat keeps what it held), and a
  placement that failed is said, with the command that places it where
  one can; a spawn whose outcome is not known is looked at, with the
  commands its line gives, and not run again because a look found
  nothing. The Channels section's `channel show` line says what the
  pool shows of a VM and where, and one sentence says that a line in a
  channel's chat from `devcloud@<vm>` is that machine's notice, recorded
  for the channel and addressed to no one: the notice to the thread that
  owns the VM is delivered separately, which the record stands in for in
  no way, and nobody answers the line. (M4's review: "was told
  separately" claimed a delivery the chain may not have made.) `--pools` is a
  program's and stays out of the skill, as `--notice` does; `sminos help`
  lists it.
- **What changes in `D/skills/vm/SKILL.md`:** "Its end" says that each
  notice is also recorded, where it can be, in the channels whose pool
  holds the VM, read with `sminos chat <channel>`, and that `sminos
  channel show <channel>` on a Mac shows who owns each VM of the channel,
  how long it has run and what it has cost, where devcloud has them, with
  a note after the pool where devcloud could not be asked or did not
  cover an account. `vm info` stays out, as `vm owned-by` does.
- **What the skills must not promise:** a notice recorded in a channel
  is delivered to no one, so it is no substitute for the notice to the
  owning thread, and the repositories' names are left out of this
  additional record and of nothing else: the notice itself keeps its
  full text wherever today's delivery takes it, which is the owning
  thread and, when that thread is held, ended or no member, its
  project's live members and then its project's log. No sentence says
  the full text reaches the owning thread alone. A kept address for a
  spawner is not taught as safe to reuse after the spawner moved or went
  on in another session: the reply line of its latest message is. The
  record is made only by a VM made from now on,
  whose own sminos is updated ("a VM made from now on", as G1's text says
  it), and in the channels whose pool that VM reads itself in then; the
  cost is the list price times the age; and `channel show` shows a VM
  only where the Mac it runs on can list the VM's account, and says when
  it could not.
- **The evaluation is small and aimed at what a wrong reading costs.**
  Five scenarios, run as doperpowers:writing-skills prescribes, against
  the changed text and against the text before it: a session that
  coordinates work in a channel and needs a heavy job on a VM (it spawns
  with `--on new --channel`, in the background, and does not spawn and
  then add); a session told its spawn "was not placed in" a channel (it
  runs the `channel add` it was given, and does not spawn again); a
  member reading a channel's chat that holds `devcloud@<vm>`'s idle
  notice for a VM another thread owns (it does not reply to it, does not
  take it for its human's instruction and does not down the VM; at most
  it tells the owning thread); a session asked what a channel's VMs cost,
  once on a Mac (it reads `channel show`) and once on a VM (it reports
  that the facts are not shown there, and invents none); and a live
  member of a project whose thread owns a VM and is held, which receives
  the VM's full idle notice gone on from the owner while the channel it
  is in holds the short one (it reads the two as one notice, treats the
  full one as the machine's and not its human's, tells the owner's
  thread or its human as the vm skill says, and neither downs the VM nor
  repeats the repositories' names into the channel). The report says
  what each run did under each text.
- **TECH-DEBT rows,** in the section "sminos environments", each with
  what would promote it: those of Constraints' "Accepted, and not
  built". The row "A machine still downloading a project's log reads a
  member's absence as a fact" gains the pool as one more reader, and the
  row "A queued terminal post in a channel is promoted on the uplink's
  consumer thread" a host's notice as one more such post.

**Does not touch:** any behaviour; the guide (`guide_text`), which says
nothing of spawning or VMs and lists a thread's channels from its record
at its next start; the manager's skill.

**Proves:** acceptance 12 (X6 for this child) and 11 whole: every gate on
the final head, and the focused files of Concrete Steps run once more as
the acceptance's own commands.

### M5 — The live check, on the merged change

**At its end:** acceptance 13: the scene of Concrete Steps has run on the
owner's fleet with a VM made and downed inside it, and what each step
printed is in the report; or the check is reported as not run, with the
stage it stopped at and what is missing. Either way the report opens with
what became of everything the run set out to make: removed, left, or not
known.

**Touches:** nothing in the tree but this document's record. A defect it
finds goes to the composite's holder with the evidence; its fix is a
change of its own, with a patch version.

**Decisions:** G1's M5 decisions hold as written there and are not
restated: after the merge and after both machines run the merged code;
intent before each launch, with a first-write `--stamp` on every seat and
`DEVCLOUD_TEST_RUN` with the alias as the VM's label; one cleanup set
before anything is made; three states and no fourth; names of the run's
own; a VM is gone when devcloud says so; a run that stops early is
classed by the stage it reached; the VM is made under devcloud's caps and
without `--vm-confirmed`, and a cap is a "not run"; scratch seats, never
a working one. Added for this scene:

- **A disposable thread makes the VM, by running the spawn as its own
  task** (the holder's rulings on the first review's thirteenth finding
  and on how it is done). Parent acceptance line 5 asks that the thread
  which made the VM is refused its retire while it owns it, and retired
  after the VM is handed on or downed. So the spawner is a scratch seat
  A, never the session that runs the check, and no session id is set
  from outside its session: A is spawned with a task whose text is the
  one command to run and what to report back, as G1's live threads were
  given theirs. The checking session reads what was made from the run's
  marks (the stamp on the seat, the VM's label and its owner), and A's
  report only for the lines the command printed. A's retire is tried
  before the handover and made after it, and the second scratch seat B
  is refused and then retired as in G1's scene. It needs no second VM.
- **Kept to what the stand-ins cannot show.** Three things: a VM enrolled
  moments ago placing its thread (its welcome kept, the channel
  registered from the request, the child's first message by the address
  its preamble gave); devcloud's real answer about a real server (a
  creation time, a price, the time the question takes); and a real
  host's boot library, a real sminos and the real endpoint and hub
  carrying a host's `human` event under a channel's id to another
  machine, which CH2 proved against the fixture and a stand-in only. The
  refusals, the older copies and every failure path stay the suites'.
- **A queued notice is a pass on the host.** On a VM made minutes ago the
  host's line for the channels' record may be the waiting line; what the
  scene requires is the event on the Mac.
- **What it costs.** One VM of the profile's default type for under an
  hour (cents at list price), and about forty minutes: `vm up` on the
  slow path, since M3 moved the recipe hash, and up to fifteen minutes
  for the org's directory to retire the machine after the down. No retry
  makes a second VM without the holder's word.
- **A scratch channel, made and emptied by the run.** The session that
  runs the check creates it and is its first member, and removes itself
  last, so the channel is left with no member and leaves the directory
  by its own rule. Its log stays at the hub, as every channel's does; the
  report says so.

**Proves:** acceptance 13, which is parent acceptance line 5 on released
versions, its retires included.

## Concrete Steps

Every command runs from the repository's root in the child's worktree.

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_on.py                  # M1
    bash sminos/tests/test-on.sh                        # M1
    python3 -B sminos/tests/test_channels_spawn.py      # M1
    bash sminos/tests/test-channels-machines.sh         # M1, M2, M3
    python3 -B sminos/tests/test_vm_info.py             # M2
    python3 -B sminos/tests/test_channels_roster.py     # M2
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_info.py   # M2
    python3 -B sminos/tests/test_channels_pools.py      # M3
    python3 -m unittest discover -s devcloud/tests/unit -p test_idle.py          # M3
    python3 -m unittest discover -s devcloud/tests/unit -p test_lease.py         # M3

A Python file is a `unittest` module: it ends with `OK` and its count, or
names the test that failed. A shell file ends with its counts of passed
and failed and exits non-zero on any failure. devcloud's unit tests need
Python 3.11 or later. Each new test is written first and seen to fail for
the reason its milestone names before the code that passes it.

**At each milestone's end,** the gates, on the pushed commit:

    ci-gate

Expected: one `PASS` line for each gate the change's paths plan
(Constraints, "Which gates cover what"), then `GREEN` and the run's
address. While a failure is being worked on, a chosen few:

    ci-gate --gates sminos-channels,sminos-suites-c,devcloud-unit

A `FAIL` that the base also shows, or one a recorded reason names, is not
this change's; any other is diagnosed, not run again. Each milestone's
report gives the figure `sminos-idle` read and the durations of
`sminos-channels` (timeout 8 minutes; 2m39s to 3m38s through CH2's waves)
and `sminos-suites-c`, and says so when either comes within a quarter of
its timeout in `.github/ci-kit.yml`.

**The proof map.** Where each acceptance item is proved.

| Item | Proved in (milestone: file) |
|---|---|
| 1 a thread opened on a VM is placed | M1: `test-on.sh` (the VM side for real on a second home: the lines, the record and the statement there, two channels, a terminal's spawn), `test_on.py` (what the request carries; `--on new`'s order against the stand-in), `test-channels-machines.sh` (a thread spawned with `--channel` on one machine, in the roster and the pool as another reads them); M5, the one place the three are seen in one run |
| 2 a thread spawned here is placed | M1: `test_channels_spawn.py` (a new seat, a refill and its statement's writer, `--wait`, the statement's shape, no request) |
| 3 what the thread was told works | M1: `test-on.sh` (the preamble's tag run as the child beside a channel-mate named for the spawner's short; every printed command run under conflicting registrations on both machines; the `channel add` run on a Mac with a local member named for the remote short), `test_on.py` (the label from `session`, not `short`; the whole session id in every command); M5 (the child's first message) |
| 4 refused before anything is made | M1: `test_on.py` (the names, 129 channels, a set that folds to a valid one, the uncarried channel and the project id, with devcloud's stand-in recording no call), `test-on.sh` (the VM's refusals: a welcome without `channels`, a channel it does not carry, `spawner-shadowed` in the qualified form; the kept VM's words), `test_channels_spawn.py` (the same refusals here, no launch) |
| 5 no welcome kept yet | M1: `test-on.sh` (waited on, spawned once the welcome is kept; the wait's end, exit 75, no launch), `test_channels_spawn.py` (the refusal without `--on`, in its own words) |
| 6 after the launch nothing is a refusal | M1: `test_channels_spawn.py` (each `failed` word, the limit, a lock held on the second channel), `test-on.sh` (the outcome's `channels` with each failed entry; a registration made uncarried, a known channel retired and the identity changed between the check and the placement; the `--worktree` refill of a seat that holds a requested channel; the merge base's sminos as the VM side onto a seat already in channels; a delay before the VM side starts, then the held lock, with a Mac's bound that outlasts it and one that does not; the inspection run from the login directory), each asserting one launch |
| 7 `channel show` on a Mac | M2: `test_driver_info.py` (the reply for a VM, an adopted machine, a host with no price, a handed-on host), `test_vm_info.py` (sminos's reading of the driver's own replies), `test_channels_roster.py` (the lines and `--json`), `test-channels-machines.sh` (the suffix for a machine a spawned thread put in the pool); M5 |
| 8 `channel show`, missing or partial | M2: `test_vm_info.py` (no CLI, an older devcloud, exit 6, no answer in time, another exit, each reply that is not whole), `test_driver_info.py` (four accounts: listed, failed, stalled, not started; a stalled type list; the second profile's account), `test_channels_roster.py` (both renderers on each: the line, `coverage`, the roster and the exit unchanged) |
| 9 a notice in the timeline | M3: `test_channels_pools.py` (which channels, the event, nothing delivered, the removal not yet read and the hand-add not readable), `test_idle.py` and `test_lease.py` (the full text, and the short one the constant can choose), `test-channels-machines.sh` (written on one machine, read by another's `chat`); built by CH2 and run unchanged: `test_channels_say.Words`, `test_channels_lead` (the lead rule, a tagged notice, the manager's classifier); M5 |
| 10 the notice's own delivery is unchanged | M3: `test_idle.py`, `test_lease.py` (the chain's calls as before, the fourth call, exit 2, exit 0 with a waiting line), `test_channels_pools.py` (the queued event, once, after its release), the `devcloud-host` gate (the host's services against the sminos stand-in) |
| 11 nothing else changed | M1 to M3: a comparison with the merge base's sminos, extracted from git, in each milestone's suite (the banner, the preamble, the request and the outcome of a spawn with no channel; a `say`; `channel show` of a pool of one; the two parsers, flag by flag and prefix by prefix, differing in `spawn --c` and `say --p` and nowhere else). For `say` the parser is compared with the merge base (1b5b56f9, `T/test_channels_pools.py`) and the output with CH2's base (61b27ebee, `test_channels_say.SameAsBase`, unchanged): between those two bases `say`'s output did not change (1.55.1 only escaped globs), and a second copy of the scene would lengthen `sminos-channels` for nothing (the holder's word); M4: every gate on the final head |
| 12 what sessions are taught is true | M4: the evaluation's report; the tests that pin the preamble's lines and `sminos help` |
| 13 on the fleet | M5 |

**M5, the scene.** Run by the plan's executor in a session on a Mac where
devcloud's driver runs, after this child's pull request is merged, as one
script it writes in a scratch directory outside the repository, under
G1's M5 rules (the ledger of intents, the stamps, one cleanup, three
states). `<run>` is four hex digits drawn for the run. `<W>` is a
worktree whose branch origin holds at its commit, and `<me>` the checking
session's own short id.

0. Before anything is made: this Mac's marketplace clone and its daemon
   run sminos 1.56.0 or later and devcloud 0.19.0 or later, and
   `en-live-<run>` names no channel, no seat and no host. Otherwise: not
   run, with what is missing.
1. `sminos channel create en-live-<run>`, by the session that runs the
   check. Expect it placed, and `sminos list en-live-<run>` listing it
   alone. `<C>` is the channel's id, from `sminos channel show
   en-live-<run> --json`.
2. The second scratch seat: `sminos spawn en-live-b-<run> "Say ready,
   then stop and wait." --stamp en_live_run=<run>`.
3. The intent is written to the ledger (a VM labelled `en-live-<run>`, a
   seat `en-live-<run>` on it), and then the scratch thread that makes
   them is spawned, its task the command:

       sminos spawn en-live-a-<run> - --cwd <W> --stamp en_live_run=<run> <<'EOF'
       Run exactly this one command, as a background command, from the
       directory you are in, and change nothing in it:

           DEVCLOUD_TEST_RUN=en-live-<run> sminos spawn en-live-<run> "Say where you run, to your spawner, then stop and wait." --on new --channel <C> --stamp en_live_run=<run>

       When it ends, send everything it printed and its exit status with
       sminos say "@<me> …", then stop and wait. If it is refused or
       fails, send that the same way and do nothing else: do not run it
       again and do not change it.
       EOF

   `<A>` is this seat's session id, read with `sminos who --thread
   en-live-a-<run>`. Expect, within twenty-five minutes, A's message to
   the checking session holding: devcloud's lines, perhaps the notes that
   it waits (for the VM's enrollment, for its reading of A, for its
   welcome), then `seat spawned on <vm>: …`, `en-live-<run>#<sid>: in
   en-live-<run>`, the note that the VM is kept and its thread owns it,
   and exit 0. Whatever A reports, `devcloud vm ls` is read for a VM
   whose name holds `en-live-<run>`: one that exists is the run's, with
   A's short as its owner. No message and no VM by then: not run, with
   A's transcript's last lines; a message that the command was refused:
   not run, with the refusal.
4. The VM's sminos, before anything is attributed to this release: its
   plugin manifest on the host names 1.56.0 or later (G1's step 3). A host
   whose declared source is pinned elsewhere shows another: the report
   then says which copy the steps ran on and claims none for this release.
5. Within two minutes `sminos list <C>` lists two threads, the second on
   `<vm>`, and A's project log holds a `say` under a writer of `<vm>`
   whose `to` names `<A>`: the child reached its spawner, the scratch
   thread, by the address its preamble gave. `sminos channel show <C>` prints, in its pool,
   `<vm>  1 live, 0 stopped  vm owned by en-live-a-<run>#<A's first
   eight>, up <minutes>m, <a small amount> <currency> so far`, and no
   line of partial coverage that names the VM's account. The command is
   timed three times; the report gives the three wall times beside one
   of `sminos channel show` of a channel whose pool holds only this Mac.
6. The thread that made the VM cannot be retired: `sminos retire
   en-live-a-<run>` exits 1 naming `<vm>`, `devcloud vm down <vm>` and
   `devcloud vm owner <vm> <thread>`.
7. A notice, through the host's own delivery, as root (G1's step 8, the
   same program; a channel records the full text, O6):

       devcloud vm ssh <vm> --root -- 'python3 -P - <<"PY"
       import os, sys
       sys.path.insert(0, os.path.dirname(os.path.realpath("/usr/local/bin/devcloud")))
       from devcloudlib import descriptor, notices
       from devcloudlib.proc import User
       d = descriptor.load()
       notices.deliver(User.from_image(), d,
                       "devcloud on %s: a check of the notice path; unpushed: none; nothing to do" % d.name,
                       short="devcloud on %s: a check of the notice path" % d.name)
       PY'

   Expect, on the host: `devcloud notice: sent: …`, then one line
   `devcloud notice: channels: …` that is either `recorded <ref> in
   en-live-<run>` or the line that the event waits for the upstream's
   head. On the Mac, within five minutes: `sminos chat <C> -n 5 --json`
   holds exactly one `human` event under `<vm>/human` with `notice`
   `devcloud`, `to` `"*"` and the full text, and `sminos chat <C> -n 5`
   prints it from `devcloud@<vm>`; A was handed the full text in its
   project as G1 delivers it, and no frame for the channel's record.
8. Hand the VM on, retire the thread that made it, and try the new owner:

       devcloud vm owner <vm> en-live-b-<run>
       sminos retire en-live-a-<run>
       sminos channel show <C>
       sminos retire en-live-b-<run>

   Expect: the handover's line; A's retire succeeds; the pool's line now
   names `en-live-b-<run>#…`; B's retire is refused, exit 1, naming
   `<vm>`.
9. `devcloud vm down <vm>`, then `sminos retire en-live-b-<run>`, which
   succeeds. Within fifteen minutes (the org's directory retires the
   machine about ten minutes after the down) `sminos list <C>` lists the
   checking session alone and `sminos channel show <C>` lists no `<vm>`
   in the pool.
10. `sminos channel remove <C>`: the channel has no member, and `sminos
    list --org` no longer shows it.

The report opens with every intent and its state; then, for each step, its
command and what it printed; the time `vm up` took and whether it took the
slow path; the three timings of step 5; whether step 7's line was the
recorded one or the waiting one; and the versions the Mac and the VM ran.

## Interfaces and Dependencies

Names in the code today are given as they are; what a milestone adds is
marked with its milestone. Sentences given in full are decisions (a test
or another program reads them); any other wording is the executor's.

### §1. `spawn --channel` (M1)

**The flag.** `sminos spawn … --channel <channel>`, given any number of
times; each value a channel's name, `name#short` or id, as `find_channel`
takes one; values that name one channel count once. It adds: a spawn onto
a seat whose thread is already in channels leaves those as they are.

**Words used below.** `<id>` is a channel's id, and every command this
section prints names a channel by it; a channel's name appears only in
prose, as the machine that prints it knows it. `<sid>` is the first eight
characters of the new session's id (the outcome's `session`), never the
outcome's `short`, which is the engine's job id.

**Decided before a launch, on the machine `spawn` is typed on,** with
`--on` before devcloud is looked for:

| Condition | What happens |
|---|---|
| a name no log answers, several answer, or a project's | exit 4, `find_channel`'s words |
| more than 128 distinct channels | exit 1: a thread is in at most 128 channels; nothing was spawned |
| the channel's log is not carried by this machine's enrollment (a registration of no hub or another org, one the directory retired; not one that has left this machine, which a placement brings back) | exit 1, with the reason `_refuse_uncarried` gives, saying that nothing was spawned |
| `--on`, from a session whose project id is not one a tag's qualifier takes (`valid_name`) | exit 1: the thread placed in channels could be given no address for its spawner that a channel-mate's name cannot take; spawn without `--channel` and add it after |
| `--on`: the request as it will be sent fails `read_request`'s own test | exit 1, said as this sminos's fault; nothing was spawned |
| no `--on`, and this machine's kept welcome lists no `channels` (`kept_capability("channels")` is `False`) | exit 1, saying so and that dropping `--channel` spawns it in no channel |
| no `--on`, and no welcome is kept or it cannot be read (`None`) | exit 1: this machine has kept no welcome of its endpoint yet, so whether it serves channels is not known; nothing was spawned; run it again once `sminos daemon status` shows the uplink connected |

`sminos_audience.kept_capability(capability)` (new) answers `True` where
the kept welcome's capabilities list holds it, `False` where that list is
there without it, and `None` where there is no file, it cannot be read,
or it holds no capabilities list. `advertised` is unchanged.

**The request** (the Mac side to the VM side) gains one key, present
only when `--channel` was given, the same on every try of one command:

    "channels": [{"id": "<the channel's id>", "name": "<its name on the asking machine>"}, …]

`read_request` takes it only whole: a list of 1 to 128 objects, each `id`
a channel's id (`is_channel_id`) and each `name` a name (`valid_name`),
no id twice. Present and anything else: exit 2 and no outcome line, as
for any request this version does not read. The request carries no time
(R18).

**The spawner's address.** Where the request carries `channels` and names
a spawner's session, the preamble's `{{BY}}` gives the address as

    <alias> (@<project id>/<short>, in <project name> on <machine>; sminos say "@<project id>/<short> …" reaches it as it is now; once it has sent you a message, answer by the reply line of its latest message)

and `hold_to_spawner` asks the resolver that tag in place of `@<short>`:
resolved to the spawner's session in the request's project, the launch
goes on; a refusal that opens `ambiguous`, or any other member,
`spawner-shadowed`; anything else, `spawner-unknown`, waited on as today.
One function in `S/sminos_on.py`, `spawner_tag(by, qualified)` (new),
builds the tag for both. Without `channels` the words and the check are
G1's. What the check gives: at admission the tag reaches the spawner, and
no alias in another project can take it. What it does not: the tag is
read in the spawner's project, an id before an alias only among current
names, so after the spawner has moved away or gone on in another session,
a member of that project whose alias is the short is who it reaches.

**The VM side, before its launch,** after `hold_to_spawner`:

| What it finds | Its answer |
|---|---|
| `kept_capability("channels")` is `None` | `why` `welcome-unknown`, exit 1: this machine has kept no welcome of its endpoint yet; nothing was spawned |
| it is `False` | `why` `other`, exit 1: this machine's endpoint serves no channels; nothing was spawned |
| a channel it already knows whose log its enrollment does not carry, against the request's `org` | `why` `other`, exit 1, naming the channel and the reason; nothing was spawned |

`WHYS` gains `"welcome-unknown": (1,)` and `WAITED_ON` gains it: the Mac
waits it out as it waits out `spawner-unknown`, for a named VM as for a
new one (the holder's ruling), inside the one wait counted from the first
waited-on answer. At the wait's end no thread was opened, the exit is 75
(`EXIT_LATER`), and the words say that the VM's sminos had kept no
welcome within the wait, that `devcloud vm ssh <vm> -- sminos daemon
status` shows its uplink, and that the same command with `--on <vm>`
opens the thread once it has. Only a Mac that sent `channels` can be
answered so. The VM side registers no channel and writes nothing of the
channels before the launch; G1's preflight before these checks
(`hold_to_spawner`) may register the seat's project and reconcile the
spawner's, as it does for every `spawn --on` (Decision Log, "Execution:
M1 and M2").

**The placement,** on the placing machine, once the launcher has returned
the session. One function, `sminos_channels.place_spawned(thread_id,
session, seat, asked, org)` (new; `seat` is the seat's `{cwd, group}` on
a VM, from which step 2 reads the project afresh, and `None` here), which never exits and never raises,
and returns `(entries, carriage)`: one entry a channel in the order
asked, and `carriage`, `{project, not_carried}` from the one fresh read of
the seat's project that step 2 makes (`None` here). It opens with
`sminos.forget_caches()` and fixes one deadline, `PLACE_BUDGET` (30
seconds; `SMINOS_PLACE_BUDGET`) from then, for every wait in it. `org` is
the request's on a VM, and on a spawn without `--on` the org this machine
was enrolled in when the command began. Then:

1. this machine's enrollment, read now: none, or of another org than
   `org`: no channel is tried, each is `failed`, `identity`;
2. on the VM side, the seat's project, read now: one that machine's
   enrollment does not carry (`not_carried(project, org)`): no channel is
   tried, each is `failed`, `project-not-carried` (a spawn without `--on`
   places as `sminos channel add` would there, and makes no such test);

and for each channel, while time is left:

3. where the machine does not know the channel: `register(id, name,
   lock_until=<the deadline>)` (`register` gains the argument; a lock not
   had by then is `time`);
4. the registration and the org's directory as they are now: no
   registration, `unregistered`; `not_carried(channel, org)` anything but
   "" or the word for a channel that has left this machine,
   `not-carried`;
5. `change(thread_id, channel, "add", session, lock_until=<the deadline>)`.

A channel whose turn comes with no time left is `failed`, `time`, and is
not tried. The outcome's own `not_carried` (G1's) is `carriage`'s, so the
project it names is the one the placement read; where that read did not
get that far (the deadline came first), the outcome names the launch's
project with the word `CARRIAGE_UNREAD` ("whether its enrollment carries
it could not be read"), and the Mac promises no reach. G1's own read
stands only for a request without `channels`. Only a Mac that sent
`channels` can receive the word, and it reads any word as no promise.

Every wait inside the placement takes what is left of the deadline,
however deep (`sminos.waits_until`, and `wait_left` for the child
processes on the path): the registration's lock, the finisher's, the
record stores', the project's registration lock, the replay's cursor
lock, the writer locks of the statement. A finish that would stop a
purged seat's process is left open inside a placement (its checks wait
on `ps`, `sysctl` and the engine), and that channel is `time`. A lock
met after the membership is committed answers `applied`, with the
warning that the statement is left to the next reconciliation, as
`sminos channel add` says it; a lock met before the commit is `time`,
but for the wake lock and a nested settlement, whose expiry reads `wake`
and `entry` (recorded at M1's review, not fixed: the placement is still
said failed, with its command).

**The outcome line** gains one key on a success, present exactly when the
request carried `channels`, one entry a channel in the request's order:

    "channels": [{"id": "<id>", "state": "applied" | "refused" | "failed", "why": "<word>"}, …]

`why` is `""` or `unchanged` for `applied`; `limit` for `refused`; for
`failed`, `change`'s word (a key of `OWN_FAILED`), `identity`,
`unregistered`, `not-carried`, `project-not-carried`, `time`, or `error`
(anything else, said on the VM's standard error). `outcome_whole` takes
the key, where present, only as such a list; a Mac that sent no channel
ignores it. The Mac holds it to its call as it holds the alias: a list
that does not name exactly the ids asked, in order, is an outcome that is
not known.

**What is printed,** after the seat's line, one line a channel. `<name>`
is the channel's name on the printing machine and `<sid>` the session's
first eight characters, both for reading only; `<session>` is the new
session's whole id, which is what a command names the thread by:

| Case | Line |
|---|---|
| placed | `<alias>#<sid>: in <name>` (`already in <name>` where the thread held it), on standard output |
| not placed, here | warning: `spawn completed, but <alias>#<sid> was not placed in <name> (<why>): sminos channel add <id> <session> places it` |
| not placed, on a VM | warning: `spawn completed, but <alias>#<sid> was not placed in <name> on <machine> (<why>): sminos channel add <id> <session> asks its machine, once sminos list --machine <machine> shows it here` |
| `identity` | one warning for the spawn: `spawn completed, but none of the placements asked for was made: <machine> is no longer enrolled in this org`; no command |
| `project-not-carried` | after G1's note that the seat will not be listed or reached from here, one warning: `none of the placements asked for (<names>) was made: its project on <machine> is not carried, and this project's memberships will not be seen from here`; no command, and nothing said of which channels the thread is in |
| a success line with no `channels` when some were asked | warning: `spawn completed, but <machine>'s sminos did not carry out the placements asked for (it predates spawn --channel). Which channels <alias>#<sid> is in is not known here: sminos list <id> shows, once its events arrive, and sminos channel add <id> <session> asks its machine. It was told to reach you as @<short>, which a member of a channel it is already in can answer to if that is its alias` (the last sentence only where a spawner was named), the two commands given for each channel asked |

`<why>` in words: `OWN_FAILED`'s sentence for its word, `LIMIT_REFUSAL`'s
reason for `limit`, and for the new words: "its registration there is
missing", "its machine's enrollment does not carry it now", "the time for
placing ran out". A word the Mac does not know is printed as itself. The
exit is 0 in all of these.

With `--channel`, the seat's own line (G1's banner) names the thread in
its `sminos say` by the session's whole id, not by `@<short>`, which a
member named for the short would answer (M1's review); without it the
banner is G1's, byte for byte.

**Where the call to the VM is lost after the request was sent** (no
outcome line within the Mac's own bound, output that never ended, an
outcome that is not whole) and channels were asked, the line that says
the outcome is not known names this inspection in place of G1's bare
`sminos list`, which reads one project from the login directory:

> Do not spawn it again before looking: `devcloud vm ssh <vm> -- sminos
> list --here --all` lists every seat on <vm>, in any project, and
> `devcloud vm ssh <vm> -- claude agents` the engine's jobs there, if a
> session started and no seat was recorded. `devcloud vm ssh <vm> --
> sminos list <id>` shows who is in <name> there; a channel that does not
> list it shows nothing about whether it was launched.

(the third command for each channel). Without `--channel` every such line
is G1's, unchanged.

**The preamble** gains one sentence, rendered only where channels were
asked, after the paragraph that explains channels. The name is prose, as
the placing machine knows the channel (the asking machine's, from the
request, where it does not know it yet); the commands carry the id:

> You are being placed in the channel "desk", as your spawner asked:
> once that is recorded on your machine, `sminos list 0f3c…` shows you
> there, `sminos chat 0f3c…` reads it, and `sminos say --in 0f3c… "…"`
> speaks in it.

(the id written whole; for several channels the sentence is said once for
each). Without `--channel` the rendered preamble is today's, byte for
byte.

### §2. `devcloud vm info` (M2)

A program's verb, like `vm owned-by`: out of the vm skill, in
`devcloud/CLAUDE.md` and the driver's synopsis.

    devcloud vm info [--within <seconds>] [--] <name>...

(sminos always passes the names after `--`: a pool's names come from other
machines' events, and one that opens with `-` stays a name.)

One JSON object on one line of standard output, exit 0:

    {"hosts":   [{"name": "dc-x-0001", "account": "main", "provider": "hetzner",
                  "creator": "@1a2b3c4d", "created": 1763850000, "spent": 0.47, "currency": "EUR"},
                 {"name": "box-1", "account": "adopted", "provider": null, "adopted": true,
                  "creator": "@5e6f7a8b", "created": null, "spent": null, "currency": null}],
     "unknown": [{"account": "…", "provider": "…", "failed": "account" | "listing" | "time", "reason": "…"}],
     "listed":  ["main"],
     "unused":  []}

- `hosts`: every server of every configured account (`Context.census(kinds=None)`)
  and every adoption record whose name equals a name asked, compared
  without regard to case. A name no host has is absent; a name two hosts
  have gives two rows.
- `creator`: `@` and the short id the host holds (the label
  `devcloud-creator`, an adoption record's `creator`), or null where it
  holds none. The word is the label's; after a handover it is the owning
  thread's session, as in X9.
- `created`: Unix seconds, as the provider reports the server's creation;
  null for an adopted machine and for no other.
- `spent` and `currency`: the type's hourly list price times the server's
  age when asked, and the price's currency, by the rule `vm ls` prints
  SPENT with; both null for an adopted machine, for a type with no price
  and where the provider's type list could not be read, in time or at
  all.
- **Its time.** `--within` is the budget for the providers' work, 12
  seconds where it is not given: the accounts are walked one after
  another under `Context.bounded(<seconds>)`, and after them the price
  reads. What became of an account is decided at that account, as it is
  walked, and is one of: listed; an ordinary failure (`account` where
  its client could not be made, `listing` where its list failed with
  time left); `time`, where its call was not started because the budget
  was spent (`Spent`), or was started and ended only when the budget
  did. One stalled account can take everything that is left: the
  accounts after it are `time`, the hosts of those before it are in
  `hosts`, and a price not read is no price. The reply is composed and
  printed after the budget, in what its caller leaves for that.
- `unknown` (but for `"time"`), `listed`, `unused`: X9's shapes, computed
  as `vm owned-by` computes them. What `unused` means to this verb's
  reader is §3's, not X9's.
- No name, or a `--within` that is no positive number: a usage error,
  exit 2. Exit 6: the driver does not run on this machine, said by the
  copy that has no driver or by the driver for a missing seed key, as
  for every `vm` verb. Any other exit printed no answer.
- It asks no host, runs no reaper and writes nothing.

sminos asks it through one function beside `owned_by` in
`S/sminos_threads.py` (`vm_info(names)`, new), found and stopped as
`owned_by`'s question is, and run only from a devcloud of
`DEVCLOUD_INFO_MIN = (0, 19, 0)` or later (the copy `SMINOS_DEVCLOUD`
names is taken at its word). Its cutoff is the smaller of 20 seconds and
`devcloud_timeout()`, and it passes `--within` that cutoff less
`DEVCLOUD_INFO_MARGIN` (5 seconds, fixed), at least 1: the margin is the
driver's start and its report, and the budget is the providers'.

### §3. `channel show`'s pool (M2)

`show` asks §2 once, naming every machine of the pool but its own, and
not at all for a pool that holds no other. What it concludes is one of:

| State | When | What is printed after the pool's lines |
|---|---|---|
| asked | exit 0 and a whole reply | one line for each cause of partial coverage, below; nothing where there is none |
| unavailable | no CLI found; a version that cannot be read or is older than 0.19.0 (not run); exit 6 | `(a VM's owner, age and cost are not shown here: <why>)` |
| failed | it could not be run; no answer within the bound (stopped); another exit; output that is not a whole reply | `(a VM's owner, age and cost are not shown: <why>)` |
| unasked | the pool holds no machine but this one | nothing |

**A whole reply** is JSON read with the constants `NaN`, `Infinity` and
`-Infinity` refused, an object with the four keys of §2, and:

- `hosts`, a list of objects, each with `name` a string equal, without
  regard to case, to a name asked; `account` a non-empty string;
  `creator` null or `@` and a printable word with no space (a short id
  of hex digits resolves to a thread; any other label, which the driver
  allows, is shown as itself and that host keeps its age and cost: the
  whole-range reading's W3); and one of two
  forms. A provider's: `provider` a non-empty string, no `adopted`,
  `created` a finite number of 0 or more (never null, never a boolean),
  `spent` null or a finite number of 0 or more, `currency` null or a
  string. An adopted machine's: `provider` null, `adopted` `true`, and
  `created`, `spent` and `currency` all null.
- `unknown`, a list of objects, each with `account` a non-empty string,
  `provider` a string or null, `failed` one of `account`, `listing` and
  `time`, and `reason` a string.
- `listed` and `unused`, lists of non-empty strings.

Anything else is `failed`, and nothing of it is printed.

**Partial coverage,** one line for each cause, after the pool:

| Cause | Line |
|---|---|
| an entry of `unknown` with `failed` `account` or `listing` | `(devcloud could not list <account>: a VM there shows no owner, age or cost)` |
| an entry with `failed` `time` | `(devcloud did not reach <account> in time: a VM there shows no owner, age or cost)` |
| an entry of `unused` | `(devcloud did not ask <account>: this Mac's profile has never used it, so a VM another Mac made there shows no owner, age or cost)` |
| two or more of `hosts` answer to one machine's name | `(devcloud holds more than one host named <name>: neither is shown)` |

A pool line for a machine that exactly one host answers for gains a
suffix, after two spaces; the lines keep today's form and are not
aligned in columns (aligning would change today's lines for every pool of
two machines or more), and the notes of the table above are printed after
the pool, unindented:

    dc-x-0001  1 live, 0 stopped  vm owned by coord#1a2b3c4d, up 3d4h, 12.34 EUR so far
    box-1  0 live, 1 stopped, added by hand  adopted, owned by coord#5e6f7a8b

`up` is the age as `vm ls` prints one (`3d4h`, `5h10m`, `12m`), from
`created` and this machine's clock, never less than `0m`; the amount has
two decimals and its currency where one is given, and is left out, with
its comma, where `spent` is null; `owned by` is left out where `creator`
is null. The owner is `<alias>#<short>` of the current session of the
thread the short id names, or the `@<short>` devcloud holds where no
thread, or more than one, answers to it. Every other line is today's.

`--json`: such a pool entry gains

    "vm": {"adopted": false, "account": "main", "provider": "hetzner",
           "owner": {"creator": "@1a2b3c4d", "thread": "<thread id>", "session": "<its current session>", "alias": "coord"},
           "created": 1763850000, "spent": 0.47, "currency": "EUR"}

(`owner` null where the host holds no creator; `thread`, `session` and
`alias` null where the short id resolves to no one thread), and the
answer gains, in every state but unasked,

    "devcloud": {"state": "asked" | "unavailable" | "failed", "why": "<the line's reason, or \"\">",
                 "coverage": "whole" | "partial" | "none",
                 "unknown": [ … ], "unused": [ … ], "ambiguous": ["<name>", …]}

`coverage` is `none` in the states unavailable and failed, `partial`
where any of the four causes holds, else `whole`; the three lists are
empty outside the state asked.

### §4. `say --notice <program> --pools` (M3)

    sminos say --notice <program> --pools <text>

Records `<text>`, untagged, as this machine's notice in the log of every
channel whose pool holds this machine, as this machine's own copy of the
logs holds that pool when it is called. A program's form: it is what a
devcloud host calls (§5), and `sminos help` lists it under `say`.

- Refused before anything is read, as a usage error: `--pools` without
  `--notice`; beside `--in`; beside a selector; before a text that opens
  with a tag. `--notice`'s own refusals stand before these (inside a
  session; exit 1 on a machine whose name the mark does not take).
- The channels: each of `known_channels()` for which an entry of
  `pool(channel)` names `host_name()`, compared without regard to case.
- In each, one event: kind `human`, this machine's human writer, `to`
  `"*"`, `notice` the program, `text` as given; written by the door a
  terminal's untagged post into a channel takes, with no read of the
  lead. Its line on standard output is `say`'s own: `recorded <ref> in
  <channel>`, or, where the writer waits for its upstream head, the line
  that it waits (`waits_line`). The second is a success: the event is
  queued, and the uplink appends it once.
- A channel that has left this machine is passed over without a word.
  One whose log this machine's enrollment does not carry, or whose append
  fails, is said on standard error and passed over; the others are
  written.
- No channel holds this machine: `no channel's pool holds this machine:
  nothing was recorded` on standard output.
- The exit: 0, or 1 when a channel was passed over for a failure. Never
  2 for anything but a usage error: a host reads 2 as a sminos that does
  not know the flag.
- It writes no notice into a project's log, delivers nothing and wakes no one.

### §5. A host's delivery (`D/boot/devcloudlib/notices.py`, M3)

`deliver(user, d, text, call=proc.call, say=print, short=None)` keeps its
chain as it is, with `text`. After the chain, whichever way it ended, and
only where the chain itself would call sminos (a CLI found by
`sminos_host.cli`, the host cut over), it makes one more call, as the
same user, with the same environment, working directory, log and
timeout:

    say --notice devcloud --pools <the channels' text>

**The channels' text.** One constant, `CHANNEL_TEXT = "full"` (O6,
the owner's answer; built `"short"` until it came), says which text the
call carries: with `"full"` the chain's `text`, or with `"short"` the
`short` argument. With `"short"` and no `short` given, the call is not
made: a full text is never recorded in a channel by omission. The two
callers give it, each from its own composer, which gains `short=False`
(`idle.text(d, state, current, found, short=False)`,
`lease.warning_text(name, expires, found, short=False)`):

| Notice | The full text (unchanged) | Its short form |
|---|---|---|
| idle (`idle.text`) | `devcloud on <name>: idle <d>d <h>h; last active <time>; <lifetime><cost>; unpushed: <repositories>; end it with devcloud vm down <name>` | `devcloud on <name>: idle <d>d <h>h; last active <time>; <lifetime><cost>` |
| lease (`lease.warning_text`) | `devcloud on <name>: lease ends at <time>; unpushed: <repositories>` | `devcloud on <name>: lease ends at <time>` |

The short form leaves out what is on the machine (the repositories with
unpushed work, by name) and the instruction that is the owning thread's
alone to follow.

| Exit | What the host says, and does |
|---|---|
| 0 | each line of sminos's standard output, as `devcloud notice: channels: <line>`, a line that the event waits included; nothing is called again |
| 2 | `devcloud notice: this host's sminos does not know --pools; no channel's timeline was written`; nothing is called again |
| any other | `devcloud notice: the channels' record failed (exit <n>): <error>`; nothing is called again |

Whether the notice falls through to the journal and `wall` is the chain's
alone, as today. The call changes no lifetime and takes no lock the chain
does not take.

### §6. An older copy on the other side

| What is new | The older copy | What happens |
|---|---|---|
| the request's `channels` | a VM's sminos 1.53.0 to 1.55.x | It reads the fields it knows and opens the thread, changing no membership; its outcome has no `channels`; the Mac says the VM did not carry out the placements, and claims nothing of what the thread is in (§1). |
| the qualified address in `{{BY}}` and in the preflight | a VM's sminos 1.53.1 to 1.55.x | It gives the child the bare `@<short>` and checks that tag from a process with no session, so through no roster. This spawn places its thread in nothing, but a spawn onto a stopped seat that already holds channels opens a child that reads its channel-mates' aliases first (1.55.x), and one named for the short takes the child's reply. Accepted: the Mac's line for such a VM says which address the child was given and what can answer to it (§1). |
| the same | a VM's sminos 1.53.0 | It has no check of the spawner's address at all and launches at once, as G1 records; the same line is printed. |
| the `why` `welcome-unknown` | a Mac's sminos up to 1.55.x | It is never sent: a VM answers so only to a request that carries `channels`. |
| the outcome's `channels` | a Mac's sminos up to 1.55.x | It sent none, so none comes back. |
| a host's `--pools` call | the host's sminos up to 1.55.x | A usage error, exit 2: the host says its line and calls nothing again; the chain is as it was. |
| a sminos that knows `--pools` | a host built before this change | No such call is made: its notices are in no channel's timeline, for its life (accepted). |
| `vm info` | a Mac's devcloud up to 0.18.x | Not run: sminos reads the version first and prints the unavailable line. |
| devcloud 0.19.0 | a sminos up to 1.55.x | It never asks. |
| a notice in a channel's log | any sminos, MAWS's endpoint and app | No new kind and no new field: an untagged marked `human`, which 1.55.0 on reads as that machine's notice and 1.54.1 stores. A copy from before channels follows the channel's log as a project's (D7) and delivers an untagged event to no one; one older than 1.53.0 shows it under `human`, as it shows every notice. |
| a thread placed at its spawn | any reader | The `channels` statement CH1 writes, read as any own add. |

### §7. What the tests are built on

- `T/devcloud_standin.py` learns `vm info`, playing replies that
  `T/test_vm_info.py` builds with the driver's own `info` module from this
  tree, and each way of giving no answer (as it plays `owned-by`'s).
- `T/test-on.sh`'s second home is the VM: the VM side runs for real there,
  over the stand-in's `vm ssh`. One case runs the merge base's sminos
  (1.55.1), extracted from git as `T/test_channels_say.py`'s `extracted`
  does, as that VM side, onto a seat that copy first placed in channels.
- `T/test-channels-machines.sh`'s three machines, each a real home with
  its daemon and an endpoint stand-in that serves `channels`, their
  `claude` the test engine (`T/wake_engine.py`), carry a project's and a
  channel's log between machines: it is where a spawn on one machine is
  read by another. `T/test-on.sh` starts no daemon, so it shows only what
  each home's own store holds.
- `D/tests/fixtures/sminos.py` learns `--pools`: it records the call as a
  sminos that knows the flag, and with `sminos-old-say` in the state
  directory answers exit 2, as it does for the notice flags.
- A stalled provider is `D/tests/fixtures/provider` held on its `gate`,
  as the driver's tests hold a merge of labels open; a second profile is
  a second profile directory of the same fixtures, whose account never
  passed under the first.
- A human writer waiting for its head is staged as the suites that pin
  `waits_line` stage it today, and released by the uplink's own
  promotion.
- A comparison with the merge base is made against that revision's sminos
  extracted from git, never against a recorded transcript.

### Dependencies

Nothing is added: Python's standard library on both sides, devcloud's
driver and providers as they are, sminos's own modules. The live check
needs what G1's needed: a Mac where the driver runs, the profile's caps
not met, and a session that is a thread of that Mac.

## Decisions that are the owner's

Product, taste and scope calls this plan does not make. Each gives the
options and the one this plan builds unless the answer changes it, with
the milestone a different answer would change. O1 to O5 build the option
this plan recommends; O6 builds the option that can still be widened
later.

- **O1. What `channel show` prints for a VM's cost, and in what unit.**
  (a) What it has cost so far: the type's hourly list price times its
  age, in the provider's currency, as `devcloud vm ls` prints SPENT
  (`12.34 EUR so far`). (b) The hourly price alone. (c) Both.
  **Built: (a).** It is the figure the Grounding Baseline's own
  observation is made in (a VM kept twenty days, above 100 euros), and
  one command and the other then agree. It is an estimate at list price,
  not a bill, and is absent for an adopted machine and a type with no
  price. A different answer changes §3's suffix (M2). **Answered by the
  owner, 2026-11-23: "지금까지 쓴 금액", (a), as built.**
- **O2. Whether a notice in a channel prompts anyone.** (a) No one: an
  untagged record, read at the next `sminos chat <channel>`. (b) `@all`:
  a turn in every live member of every channel whose pool holds the VM,
  at each idle notice. (c) The channel's lead, where one is set.
  **Built: (a),** which is D4's word ("recorded in the timeline") and
  costs no turn; the thread that owns the VM is still told directly. (c)
  is not only the owner's: D3 says the lead rule leaves a machine's
  notice out, so it would be a new rule and goes through the composite's
  holder. A different answer changes §4's event (M3).
- **O3. What a channel's timeline shows for a VM that is gone.** (a)
  Nothing new: the notices it sent stay as history, its threads leave the
  roster when the org retires the machine, and the pool no longer lists
  it. (b) A last notice, written by the host as its departure begins
  ("leaving: downed by its owner", or "its lease ended"). **Built: (a).**
  (b) is a new kind of notice in a host's departure, which is the one
  path of a host that must finish before its certificate is retired, and
  for a `vm down` it tells the channel what one of its own members just
  did. A different answer adds a milestone in `D/boot/`.
- **O4. Whether `channel show` asks devcloud at every call.** (a) Yes,
  whenever the pool holds another machine, bounded at 20 seconds. (b)
  Only with a flag (`--vms`), the plain command printing as today with a
  line that names the flag. **Built: (a),** as parent acceptance line 5
  words the command. It makes `channel show` slower by a listing of every
  cloud account on a Mac that has devcloud; M5 measures by how much, and
  the figure goes to the owner with this question if it is more than a
  few seconds. A different answer changes §3's "asked once a call" (M2).
- **O5. Whether `--channel` works on a spawn without `--on`.** (a) Yes.
  (b) Refused without `--on`. **Built: (a).** G2's acceptance names only
  the spawn on a VM, but the VM side of that spawn is this very path, and
  D4's sentence gives the flag to `spawn` without a condition; (b) would
  be a refusal written to take something away. A different answer
  removes acceptance 2 (M1).
- **O6. The words of a notice in a channel.** (a) The short text: the
  VM's name, how long it has idled or when its lease ends, its lifetime
  and its estimated cost so far, and nothing of what is on it. (b) The
  full text the owning thread gets, which also names the repositories on
  the VM that hold unpushed work and says how to end it. **Built: (a),
  while the owner has not answered** (the holder's ruling on the review's
  sixth finding; this plan first built (b)). The event is plain: every
  reader of the channel's log reads it, whatever the reach of the thread
  that owns the VM, and a channel's readers are a wider set than a
  project's. The three reasons for the default: the full text still
  reaches the owning thread through the chain; a short text can be
  lengthened for hosts built later; a full text once posted cannot be
  recalled, nor changed on a host already built. The answer is one
  constant in `D/boot/devcloudlib/notices.py` and its tests (§5).
  **Answered by the owner, 2026-11-23: "원문 그대로", (b).** A host records
  the notice's own full text in a channel, repository names included;
  the constant is `"full"`, and the vm skill and devcloud's README say
  plainly that a channel holds it.

## Open points

1. **How long `channel show` takes on the fleet** once it asks devcloud
   (O4). Not measurable from the tree; M5's step 5 measures it. Its upper
   end is fixed: 20 seconds, 15 of them the providers'.
2. **G1's own words after a lost call name an inspection that can miss
   the seat.** Without `--channel` this plan leaves them as they are
   (`devcloud vm ssh <vm> -- sminos list`, which reads the login
   directory's project). The better command is one line of
   `S/sminos_on.py` and changes what every `spawn --on` prints when a
   call is lost; it is G1's to patch, or this child's with the holder's
   word, and until then a TECH-DEBT row (M4).
3. **The scratch thread may not run the command it is given.** M5's VM
   is made by a real session whose task is the spawn command. If it
   declines, asks, or changes the command, the scene is "not run" with
   what it said; the checking session finds what was made by the run's
   marks, never by that session's report alone.
4. **A host's `human` event under a channel's id through the real endpoint
   and hub.** CH2 proved it against MAWS's fixture and a stand-in and says
   it was not yet read from a real endpoint. M5's step 7 is the first real
   reading; a failure there is the wire's, and goes to the holder.
5. **An adopted machine whose own name differs from its devcloud name**
   shows no owner in `channel show`, since the two are matched by name.
   No such machine is known; a row if one is seen.
6. **Who runs M5.** As in G1, the plan's executor, in a session on a Mac
   where the driver runs. It creates the scratch channel, so it is a
   thread or the holder runs the scene from one.
7. **The `sminos-channels` gate's room.** Two new files and three new
   scenes of `test-channels-machines.sh` join a part that took up to
   3m38s against 8 minutes. Each milestone reports it, and a part past
   six minutes has its timeout set again in the same change.
8. **A machine added to a pool by hand and since retired by the org**
   stays in `channel show` with no thread and, being no host any more,
   with no suffix. CH1 built that, and O3's default leaves it; a
   TECH-DEBT row records it.

## Surprises & Discoveries

Found while this plan was written, by reading the code at the parent pin.

- Observation: X9's command cannot answer `channel show`, though X9 names
  `channel show` as its consumer. It answers by owner and carries no age
  and no cost; `vm ls`, which has them, runs the reaper and probes every
  host over ssh before it prints, and reports what it could list as the
  whole fleet.
  Evidence: `devcloud/driver/owned.py` (`vms` rows of `name`, `account`,
  `provider`, `creator`); `devcloud/driver/ops.py`, `ls` (`reaper.run`,
  `idle_states`, `ctx.fleet()`).
- Observation: nothing ties a notice in a channel to the pool today. CH2
  built the door and every reader, and left the pool out on purpose.
  Evidence: CH2's plan, Interfaces §2's table ("a person at a terminal, a
  machine's notice … the pool is not consulted (open point 2)");
  `sminos_channels.speak` has no read of `pool`.
- Observation: a spawned thread's id is its first session's, which exists
  only once the launcher has answered, so a thread cannot be placed before
  it runs. D4's "starts in" is, in the code, "is placed in as it starts".
  Evidence: `sminos.spawn_fresh` (the provisional record promoted to the
  session's uuid; `threads.ensure(uuid, seat=…)` after the launch).
- Observation: a host knows its own facts. Its descriptor holds
  `DEVCLOUD_CREATED`, `DEVCLOUD_HOURLY_PRICE`, `DEVCLOUD_CURRENCY` and
  `DEVCLOUD_CREATOR`. Nothing publishes them, and D4 asks the Mac's
  devcloud; the alternative is in the Decision Log (R7).
  Evidence: `devcloud/boot/devcloudlib/descriptor.py`.
- Observation: a host's CLI answers exit 6 to every `vm` verb, but the
  launcher's own answer where no Python 3.11 is on PATH covers `vm
  owned-by` alone. `vm info` there is exit 1, which `channel show` reads
  as no answer; no guard rests on it, so the launcher is left as it is.
  Evidence: `devcloud/boot/devcloud` (the two refusals before the driver
  is imported); `devcloud/bin/devcloud` (`[ "${2:-}" = owned-by ]`).
- Observation: the test the composite's EN section says this child puts
  right (`test_threads_owner.Unknown.rows()`, a row rejected for its
  creator alone) was put right by G1: `rows` takes the short id of the
  thread asked about, so a row whose fault is its host's form is rejected
  for the form.
  Evidence: `sminos/tests/test_threads_owner.py`, `Unknown.rows(self,
  short="abcd1234")` and its docstring.
- Observation: no row of `docs/doperpowers/TECH-DEBT.md` names EN, G2,
  `channel show`'s VM facts or a notice in a channel as its trigger. Three
  rows bear on this child without being its to close: "The message path
  trusts a machine name" (a project's path; a channel's reads what the
  machine appended, and an untagged notice is delivered to no one); "A
  machine still downloading a project's log reads a member's absence as a
  fact" (the pool read on a fresh host is one more such reading); "A
  thread in channels pays about half a second more a command" (`--pools`
  and `channel show` pay it once, as commands).
  Evidence: the file's sections "sminos environments" and "sminos
  channels".

- Observation (the plan's review, read again in the code): a bare name in
  a tag is looked up as an alias before it is read as an id, and for a
  sender in channels the aliases searched are those of its channels'
  rosters too. So `@<short>` from a thread in a channel goes to a
  channel-mate whose alias is that text, in any project, with no error.
  G1's preflight asked the resolver from a process in no channel.
  Evidence: `sminos._resolve_tag` (`_with_shared(name, project, rows)`
  before `match_members(…, alias=False)`); `sminos.reply_line`, which
  gives `@<project id>/<short>` "so a reply reaches it from any project
  and on any machine".
- Observation: `advertised("channels")` answers no for three states that
  are not the endpoint's no: no kept file, one that cannot be read, one
  with no capabilities list. The uplink keeps the capabilities when the
  welcome arrives and goes on serving if that write fails, and a spawn
  from a terminal skips the wait for the spawner that would otherwise
  come first.
  Evidence: `sminos_audience.advertised` beside `_kept_word`;
  `sminos_uplink.py`, the welcome's `audience.keep_capabilities(caps)`
  under `except OSError`; `sminos_on.hold_to_spawner`'s first return.
- Observation: `register_if_absent` takes its lock with no deadline and
  keeps whatever registration is there, a hubless one an older copy made
  included; `change` tests the channel's id and nothing of its carriage.
  Evidence: `sminos.register_if_absent` (`flocked(path + ".lock")`, `if
  registration(project.id): return`), beside `register_listed_channel`,
  whose docstring names that older-copy case.
- Observation: a `say` under a writer that waits for its upstream head is
  queued, prints a line with no reference and exits 0; the uplink appends
  it later, once.
  Evidence: `sminos.say_into` (`if e["seq"] is None: print(waits_line(…))`).
- Observation: X9's leave to skip an account whose provider never passed
  rests on whose thread could own a host there, which is the wrong
  premise for an inventory of machines other Macs may have made. And a
  census lists accounts one after another, each provider call bounded at
  two minutes unless the run is bounded as a whole.
  Evidence: `devcloud/driver/owned.py`'s docstring on `unused`;
  `provider.SHORT`; `Context.census`; `Context.bounded`.

Found while it was built.

- Observation: `change` takes no lock of the channel's own; the waits a
  placement can meet are the registration's lock, the thread's lifecycle
  path and the project's store. So `time` from a busy lock is made, in
  the tests, by holding the registration's lock of a channel the machine
  does not know yet.
  Evidence: `sminos_channels.change`; `T/test_channels_spawn.py`,
  `Deadline`.
- Observation: `json.loads` reads `1e400` as infinity with no `Infinity`
  literal, so refusing the three constants does not refuse every number
  that is not finite; sminos's reading of `vm info` tests each number.
  And devcloud's provider client reads a provider's JSON with Python's
  default, which takes `NaN`: a price can be `NaN`, which `vm ls` prints
  as `nan` (left as it is: not this child's; residue).
  Evidence: `T/test_vm_info.py` (`1e400`); `D/driver/provider.py`.
- Observation: `speak` lets a channel that has left the machine through,
  as `_refuse_uncarried` means it to; a writer "into each channel" must
  test `has_left` itself, which `--pools` does.
  Evidence: `sminos_channels.record_in_pools`.
- Observation: a project's view, built to read a roster, reconciles the
  project's log (a `joined` may be written). `--pools` reads no roster
  when no channel is a candidate, so a host in no channel writes nothing;
  with candidates it reconciles as `channel show` does.
  Evidence: `T/test_channels_pools.py`, `Which`.

## Decision Log

The entries R1 to R24 are the residue decisions made while this plan was
written, each with the alternative it beat; a milestone's Decisions slot
points at them. The owner's decisions are not here: they are O1 to O6,
above.

- 2026-11-23 — **Verification.** This plan is reviewed before it is
  built, by the `doperpowers:adversarial-reviewer` agent, on buildability:
  the milestones against the code, the shapes and sentences of Interfaces
  against the composite, and §6's table against what each older copy
  really does. The first review returned thirteen findings and the
  second, of the revision, ten (the entries "The plan's review" and "The
  plan's second review"); there is no third before the build. The build
  runs under `doperpowers:plan-executor`, a fresh
  executor a milestone, each milestone reviewed at its close by the
  execution loop's reviewer. After M4 the composite's holder reads the
  whole range once, through doperpowers:review-code at the panel rung
  `xhigh`, with these lenses given: each of the three contracts read from
  both of its sides (§1's request and outcome, §2's reply and §3's
  reading of it, §4's flag and §5's call); that every refusal comes
  before its side effect and nothing after a launch is one; what happens
  to time after a launch (every wait under the one deadline, the report
  never lost to a lock); that every command the change prints or renders
  resolves, on the machine that runs it, to what was asked; §6's older
  copies; and acceptance 11 over the whole diff. Its confirmed findings go
  to one fix wave, weighed as the owner's rule for review findings weighs
  them; a second reading is made only if the first sends more than ten
  findings into the wave, or one in the path that runs after a launch. M5
  changes nothing and is not reviewed. *Why one reading where CH2 took
  three:* CH2's two whole readings each confirmed about forty defects
  after its per-milestone reviews, most of them where one milestone's
  check met another's wait: it added deliverers, a delivery record and
  questions to the endpoint to a store with no writer in charge. This
  child adds no deliverer, no lock, no record and no duty of the daemon
  or the uplink. One place of that kind is left, M1's placement after the
  seat's lock is released, and it is inside one milestone and named as a
  lens. The plan's own review bore that out: eight of its thirteen
  findings were in M1, and none was one milestone's check meeting
  another's wait. What a milestone's reviewer cannot see here is the other machine
  and the older copy, which is what the one whole reading is aimed at.
  *Alternative rejected:* no whole reading, since each contract sits in
  one milestone: the claim of acceptance 11 and §6's table are properties
  of the whole diff.
- 2026-11-23 — **R1. A spawn places its thread by the thread's own
  statement, on the placing machine,** a new seat and a spawn onto a
  stopped seat alike (revised by the holder's ruling on the review's
  third finding). `change`, the path of a thread that adds itself (C2),
  with no request in the channel's log. *Why the caller may:* the door
  that fills a seat launches its session and sets its record's owners and
  its reach (the composite's D1), which is more than the reach a request
  checks before a thread's machine honours it, so a caller who may fill a
  seat may place it. This plan's first reason, "the spawner made it", was
  wrong for a refill, which makes a session and not the thread. The
  request path (`place`, `carry_out`, who may ask) is untouched, and the
  rule is an extension of D4 that the composite's writer records there.
  *Alternative rejected:* the spawner's `channel add` after the outcome
  line, a request the VM carries out. The Mac would have to name a thread
  whose `joined` it has not read yet, the placement would wait for the VM
  to download the channel's log and for its endpoint's word, and `channel
  show` would list a request nobody needed. For a refill it would also
  give one command two authorities, the fill's and the request's.
- 2026-11-23 — **R2. The channels travel in the request, as ids with
  names.** *Alternative rejected:* `--channel=<id>` flags on the VM side's
  command line. A VM whose sminos predates the flag would end with a usage
  error before it read the request, and the Mac could only say the spawn
  is not known; with the key such a VM opens the thread and the Mac says
  what is missing. The name beside the id is what lets a VM register a
  channel it does not know (R3).
- 2026-11-23 — **R3. A VM that does not know the channel registers it
  from the request,** as `channel create` brings back a channel that has
  a registration and no member. *Alternative rejected:* waiting until the
  org's directory lists it. A channel with no member is in no directory,
  and placing a member is what brings it back, so that wait could never
  end.
- 2026-11-23 — **R4. Placed after the launch; a failure is a warning and
  the exit is 0.** *Alternatives rejected:* placing before the launch
  (the thread's id is the launched session's: Surprises); a non-zero exit
  (a caller would take the spawn for failed and run it again, onto a
  live seat); stopping the session that could not be placed (it destroys
  work to keep a label true).
- 2026-11-23 — **R5. The preamble says the placement is asked for, not
  done.** The sentence is rendered before the launch and the statement is
  written after it. *Alternatives rejected:* "you are in", which is false
  for a placement that fails; no sentence, which leaves a thread that was
  spawned for a channel to learn of it from the first message there,
  since its start guide is read before the statement exists.
- 2026-11-23 — **R6. A VM's refusal for a channel is `why` `other`, and
  is not waited on; a welcome not kept yet is no such refusal** (revised
  after the review's eighth finding; R19). `WHYS` gains one row,
  `welcome-unknown`, for the state that passes by itself.
- 2026-11-23 — **R7. A new program's verb in the driver, `vm info`.**
  *Alternatives rejected:* `vm ls --json`, which runs the reaper (a
  command that only reads would delete what outlived its lease), probes
  every host for up to ten seconds, and reports a partial fleet as whole;
  more keys on `vm owned-by`'s rows, which X9 fixes and sminos checks
  whole, and which answers another question (by owner, not by host); the
  host stating its own facts in the channel, which needs a new event kind
  on every machine and moves the authority D4 gives devcloud on the Mac.
- 2026-11-23 — **R8. devcloud gives facts and sminos words them.**
  `created`, `spent` and `currency` as values; the age and the line are
  sminos's. *Alternative rejected:* devcloud printing the cells `vm ls`
  prints, which makes a table written for a person a contract with a
  program (G1's reason for `--exit-held`).
- 2026-11-23 — **R9. The question is bounded at 20 seconds, and the
  roster prints whatever becomes of it** (the driver keeps its own time
  inside that: R22). `owned_by`'s minute is right
  for a guard that must not guess and wrong for a listing a person
  waits for. *Alternative rejected:* a variable of its own; the one that
  exists already lowers the bound, which is all a test needs.
- 2026-11-23 — **R10. Where the facts cannot be shown, one line says so
  and why, after the pool.** D4's words ("elsewhere it says those columns
  are not available"). *Alternative rejected:* a dash in each line, which
  marks every Mac in the pool as a VM with unknown facts: without
  devcloud's answer sminos cannot tell which machines are VMs.
- 2026-11-23 — **R11. `say --pools`: sminos chooses the channels, the
  host makes one call.** *Alternatives rejected:* a verb that lists the
  channels whose pool holds a machine, with the host looping over `say
  --notice --in`, which puts the loop and its failure handling in a boot
  library that is never updated on a host; recording in the pools at
  every `say --notice`, which would cover hosts built since G1 without a
  rebuild but writes three records for one notice (the chain makes up to
  three calls), unless a flag about exit codes or a leading tag is made
  to mean "this is the first", a contract nobody could read off the call.
- 2026-11-23 — **R12. After the chain, never instead of a step, never a
  second send.** The notice to the thread that owns the VM is the one
  that can stop a cost; the record is for the channel's other readers.
  On exit 2 the host does not fall back to the call without its flags, as
  the chain does for the notice flags: without them the same words would
  be a plain `say` into whatever project the host's directory is in.
- 2026-11-23 — **R13. One program word, `devcloud`.** Which text is
  R23's and O6's.
- 2026-11-23 — **R14. A host built before this change is left as it is.**
  *Alternative rejected:* the driver sending a program that rewrites a
  live host's boot library, as `vm owner` sends one to write a
  descriptor: that program writes one value under two locks, and this
  would replace code a running lease service has imported.
- 2026-11-23 — **R15. Three building milestones, each one contract with
  both its sides.** *Alternatives rejected:* one milestone (three
  verification strategies and two plugins in one review pass); a cut by
  plugin (devcloud's two changes, then sminos's), which puts every
  producer in one milestone and its consumer in the next, the seam CH2's
  whole readings found defects at.
- 2026-11-23 — **R16. sminos 1.56.0, devcloud 0.19.0,** each a new flag
  or verb. `DEVCLOUD_ON_MIN` stays at 0.18.0: `spawn --on` needs nothing
  of 0.19.0.
- 2026-11-23 — **R17. A thread placed at its spawn is given its spawner's
  qualified address, and that same tag is what the preflight asks** (the
  first review's first finding; the holder ruled for extending G1's check
  to the requested channels' rosters, and for a form the resolver takes
  without a roster's aliases where one exists; reworded after the second
  review's seventh). One exists and is the one sminos already gives every
  reply: `@<project id>/<short>` (`reply_line`), read in that project
  alone. *What it guarantees, and no more:* at admission the tag reaches
  the spawner, and no alias in another project, a channel-mate's
  included, can take it. It is not bound to the spawner afterwards: in
  that project a current alias comes before another id of a member
  (`current_first`), so once the spawner has moved away or gone on in
  another session, a member who has taken the short as an alias is who
  the kept address reaches, alone. Nothing taught calls a kept address
  safe to reuse then; the preamble says to answer by the reply line of
  the spawner's latest message. Given only with `--channel` (the
  holder's ruling: a spawn with no channel stays byte for byte), and
  `--on --channel` is refused on the Mac where the spawner's project id
  fits no qualifier (the holder's ruling). *Alternative rejected:* the
  roster-extended check of the bare short. It can only see the rosters
  the VM holds when it checks, and the child would still run a tag that
  the next channel it is added to can take. *Noted, not taken in this
  revision:* the spawner's whole session id after the qualifier, which
  no alias would plausibly equal and which would shrink the limit above
  to nearly nothing; it departs from the reply line's form and was not
  before either review, so it is the holder's to take or leave.
- 2026-11-23 — **R18. One deadline for a spawn's placements, on the
  placing machine, and no promise about the Mac's wait** (the first
  review's second finding; rewritten after the second review's third,
  which offered two ways and this is the second). Thirty seconds from the
  placement's start cover every wait in it. This plan first sent the
  Mac's remaining time in the request (`within`) and reserved ten seconds
  of it for the report. That figure counts from before `devcloud vm ssh`
  found the host, read its lifecycle and connected, none of which is
  bounded, so the VM would have aged it by a guess, and the reserve would
  have been a claim no test could hold. The key is gone. *What is
  accepted:* on a last try that the Mac's wait has cut short, a healthy
  VM can still be placing when the Mac gives up, which is G1's outcome
  that is not known, as it already is when the launch itself outlasts
  that try. The outcome's HEAD read stays G1's, with its own bound.
- 2026-11-23 — **R19. A kept welcome is read as one of three: it lists
  channels, it does not, or it is not known; the third is waited on** (the
  review's eighth finding, which closes this plan's own open point
  instead of leaving it to the live check). `kept_capability`, beside
  `advertised`, which keeps its two answers for its callers.
  *Alternative rejected:* treating unknown as yes and letting the
  placement fail after the launch: the capability is what makes a
  membership leave the machine at all, so a thread would be opened that
  no placement can then fix.
- 2026-11-23 — **R20. Commands name a channel by its id and a thread by
  its session's whole id** (the first review's fourth finding, and the
  second's first: a short is looked up as an alias in the caller's
  project before it is read as an id, `find_target`, so a local member
  named for a remote session's short would be the one asked). The short
  and the names are for reading. *Alternative rejected:* a name checked
  to be the only one on the machine that prints it. The preamble is
  rendered before the VM has registered the channel, and the check would
  be true of the moment it was made.
- 2026-11-23 — **R21. What is placed is decided from fresh reads at the
  placement, and what they find then is a failure, not a refusal** (the
  first review's fifth finding, and the second's second). The cheapest
  form the code offers is the one it already uses between tries of
  `spawn --on`: `forget_caches`, which drops the cached enrollment and
  directory with the registrations. A thread whose own project the VM
  does not carry gets no placement (the holder's ruling), and the Mac
  says what was not done, never which channels the thread is in.
- 2026-11-23 — **R22. For an inventory, an account not asked is coverage
  not had; the providers work inside a budget, and the report has a
  margin beyond it** (the first review's tenth finding, and the second's
  eighth). X9 and `vm owned-by` are unchanged: the narrowing of
  2026-11-22 is about what this Mac's threads can own. A stalled provider
  call ends only when the budget does and then raises as any failed
  listing does, so an answer "inside" the budget was not buildable:
  `--within` is the providers' budget, the caller's cutoff a fixed five
  seconds more, and each account's fate is recorded as it is walked.
  *Alternatives rejected:* asking every account for `vm info`,
  never-passed ones included (such an account has no usable provider
  under this profile); a share of the budget for each account, which
  the driver has no seam for and one command does not need.
- 2026-11-23 — **R23. The pool a host tests is its own copy's, and what
  it records there is the notice's full text** (the holder's ruling on
  the review's sixth finding for the pool; for the text, the owner's
  answer to O6, which replaced the short text built as its default). *Alternative rejected for the pool:* a
  host asking another machine, or the hub, whether it is still in a
  pool: nothing answers such a question today, and the notice would wait
  on it.
- 2026-11-23 — **The plan's review** (the adversarial reviewer's first
  read, thirteen findings; the holder ruled on four and took nine as
  stated). `origin/main` at `6577f179` was merged first (sminos 1.55.1),
  and each finding was read again in the code before its fix was
  written; all thirteen held. What moved:
  1. *The child's reply address* (R17; acceptance 3; §1; M1).
  2. *Time after the launch* (R18, as first written: a `within` key and
     a reserve, both withdrawn at the second review; `PLACE_BUDGET` and
     the line for a call that is lost stayed).
  3. *A refill* (R1's reason; acceptance 2; the test of the statement's
     writer). Ruled by the holder.
  4. *Names in commands* (R20; the constraint "What a thread or a person
     is told to run"; §1's lines and preamble; acceptance 3).
  5. *Carriage at the placement* (R21; §1's steps and the words
     `unregistered`, `not-carried` and `project-not-carried`).
  6. *The notice's audience and text* (R23; O6's default; M3's hold on
     its merge; §5's constant and short forms; acceptance 9). Ruled by
     the holder.
  7. *The whole request checked before devcloud* (§1's table; M1).
  8. *A welcome not kept yet* (R19, R6; acceptance 5; §1's
     `welcome-unknown`).
  9. *What an older VM's answer lets the Mac say* (§1's last line; §6).
  10. *Coverage, and the driver's time* (R22; §2's `--within` and
      `"time"`; §3's four causes and `coverage`; acceptance 8).
  11. *The reply's test* (§3, field by field; M2's tests of both
      renderers).
  12. *A queued notice* (§4, §5; acceptance 10; M5's step 7).
  13. *The live check's retires* (M5: a scratch thread makes the VM).
      Ruled by the holder.
  The build as now planned is about thirty files and 2,400 lines: some
  550 in sminos's scripts, 220 in devcloud, 1,450 of tests and 180 of
  what is taught and what sits beside the code. M1 still carries the
  risk, and more of it than before.
- 2026-11-23 — **R24. Two prefixes the parser took stop working, and no
  alias keeps them** (the holder's ruling on the second review's ninth
  finding). `spawn --c` and `say --p` were never documented and are now
  argparse's ambiguity error. The promise of "byte for byte" is of the
  documented spellings. *Alternative rejected:* hidden aliases for the
  two, which would keep alive two spellings nobody was taught, each one
  prefix away from the next flag added.
- 2026-11-23 — **The plan's second review** (ten findings; the holder
  ruled on the points the first revision opened and on the ninth, and
  this is the last revision before the build). Each was read again in
  the code; all ten held. The rulings on what was open: a named VM is
  waited on for `welcome-unknown`; the qualified address only with
  `--channel`; no placement for a seat in a project the VM does not
  carry; `--on --channel` refused where the spawner's project id fits no
  qualifier; in M5 no session id is set from outside its session; the
  short text as written is O6's default. What moved:
  1. *The recovery command's thread* (R20; §1's lines; M1's test with a
     local alias equal to the remote short).
  2. *Fresh reads at the placement* (R21; the constraint "What is placed
     is decided from what the files say then"; §1's steps 1, 2 and 4 and
     the word `identity`).
  3. *The deadline* (R18: the placing machine's waits alone; `within`
     and the reserve removed from §1, §6 and the tests).
  4. *Looking after a lost call* (§1's inspection, run from the login
     directory in M1's test; acceptance 6).
  5. *The `--worktree` warning* (§1; acceptance 6; the refilled seat's
     test).
  6. *Acceptance 3's scope and the older VMs* (§6's two rows; §1's line
     for a VM that predates the change).
  7. *What the qualified address guarantees* (R17; §1; the `{{BY}}`
     words; M4).
  8. *The driver's time* (R22; §2; M2's four-account test).
  9. *The two prefixes* (R24; the constraint; acceptance 11; the parser
     comparisons in M1 and M3). Ruled by the holder.
  10. *What the skills say of the full text* (M4, and its fifth
      scenario).
  And M5: the scratch thread runs the spawn as its own task.
  The size is as restated above; M1 gains two tests and loses the
  request's second key.
- 2026-11-23 — **Execution: M1 and M2.** What the builders decided where
  the plan left room, kept here for the readers that follow.
  M1: `place_spawned` takes the seat, not its project, so the project is
  read after the launch (§1). The qualified tag's own check that the
  spawner's short is no other member's alias applies where the seat's
  project is the spawner's; elsewhere the tag is read in the spawner's
  project alone. A spawn here keeps its caller's alias in `{{BY}}` (the
  qualified address is the request's). A welcome that cannot be read is
  not known (`None`), never "serves no channels". Several channels'
  sentences in the preamble are one paragraph. An `error` placement
  reads "it failed, as said above", its cause on standard error. The
  inspection words after a lost call, with channels, are said at each of
  G1's four sites. *The VM side's writes before its launch* (the task
  review's fourth finding, dismissed with the holder's word):
  `hold_to_spawner`, G1's, may register the seat's project and reconcile
  the spawner's before the channels' refusals; G1 calls for it, a
  refusal then leaves no seat and no channel registration, and §1's
  sentence now says "registers no channel". D4's "refused before
  anything is made or launched" is of the VM and the session, and holds.
  M2: the names follow `--` (§2); `ops._spent` is shared as `ops.spent`;
  a type's price that is no finite number of 0 or more is no price, so
  one bad entry costs one host its cost and not the reply; `currency` is
  null wherever `spent` is; the pool's lines keep today's form, the
  suffix after two spaces, with no alignment (§3, corrected to what was
  built); the owner is resolved by the org-wide id step of
  `_resolve_tag`, `@<short>` where none or several answer; the reading
  of a reply takes keys it does not know and needs every one of §2's, so
  a later devcloud that adds one does not blank an older sminos's pool;
  `ambiguous` lists the pool's spelling of the name; the stand-in's `vm
  info` answers an empty whole reply unless a test sets one.
- 2026-11-23 — **Execution: M3.** The channels' record is made whenever
  §5's condition holds (a sminos CLI found, the host cut over), even where
  the chain itself called no sminos for want of a creator or a project.
  The host's `--pools` call is guarded against any exception, so a
  failure there can never make a lease tick send the notice again.
  `say`'s `--in`, `--project` and `--machine` record that they were
  given, and the `--pools` form refuses them by presence (`--in=` is
  refused too); `say` without `--pools` reads them as before.
  `--exit-held` beside `--pools` is not refused: nothing is tagged, so it
  changes nothing. A channel's failure is said from `speak`'s own exit as
  one warning naming the channel; channels are written in name order.
  *Not taken, from the task review:* the `--pools` form's checks run
  after the store's `migrate()`, which every command runs, a valid call
  included; §4's "before anything is read" is of the logs.

## Outcomes & Retrospective

2026-11-23, at the frontier before the whole-range reading (M1 to M4
built and reviewed clean; the reading, its fix wave, the merge and M5
remain).

**What exists.** `sminos spawn … --channel <channel>` places the new
thread by its own statement on the machine it runs on, here or on a VM
(acceptance 1 to 6), with every refusal before devcloud is called or a
session launched and nothing after the launch a refusal; a spawn's
placements share one deadline on the placing machine, carried to every
wait however deep (`waits_until`). `devcloud vm info` answers a program
what named hosts are without touching a host, and `channel show` prints a
VM's owner, age and cost where devcloud has them and says, in one line a
cause, what it could not show (acceptance 7, 8). A devcloud host built
from this change records its idle notice and lease warning, in the short
text (O6's default), in the log of every channel whose pool its own copy
holds it in, through `say --notice devcloud --pools`, after its delivery
chain and never instead of a step (acceptance 9, 10). The two skills, the
preamble and `sminos help` teach it, evaluated against the text before
(acceptance 12). sminos 1.56.0, devcloud 0.19.0. Every gate GREEN on the
final head; `sminos-idle` read 32105 to 32858 calls a second across the
milestones against 33570, `sminos-channels` 3m18s to 4m11s against 8
minutes. Acceptance 13 (M5) is not claimed: it runs after the merge.

**What the reviews found.** Each milestone's review sent it back once or
twice; nothing reached a design decision but two wordings this plan
prescribed. M1, twice: the placement's deadline did not reach the
project's registration lock, the replay's cursor lock or a purge's
process checks; the Mac's banner named the child by a short a local alias
could take; the outcome's carriage note came from a read older than the
placement's. M2: a malformed reply could abort `channel show`, an older
writer's thread was lost from the owner, a cost could overflow to
`Infinity` and blank the reply, and the owner was resolved once per
creator. M3: `--pools` refused its forbidden flags by value rather than
by presence, and a sweep of the rosters, moved earlier for speed, wrote
reconciliations on a host in no channel. M4: five taught sentences said
more than the code does (the owner "was told", a reply line that
"follows" a move, three facts for every VM, "in none" for a refill,
recovery that places at once); the evaluation's first scenario allowed a
leased VM and was re-run with a fixture that calls for a kept one.

**Lessons.** The plan's one risk was named rightly: every M1 finding was
in the path after the launch, and a wait list written into the ledger
after the first fix let the second review check a list instead of
rediscovering one. A deadline passed by argument reaches only the waits
written to take one; a scoped deadline (`waits_until`) reaches the rest.
A plan's sentences given in full are still claims about code that does
not exist yet; two of them were wrong in ways only the built code showed,
and the taught text is where such a claim does harm.

## For the composite's writer

What this plan found against the composite's text, and what its review
changed for the parent, each with its evidence and the clause it bears
on. Nothing here is edited by this child. Items 8 to 14 are the
revision's, 15 and 16 its second's, which also reworded 9, 13 and 14.

1. **X9, "Consumers: … EN (the handover, `channel show`)".** X9's command
   cannot serve `channel show`: it answers by owner, with no age and no
   cost (Surprises, first entry). This plan adds `devcloud vm info` beside
   it and leaves X9 as it is. The sentence wants `channel show`'s question
   named as another one, with its verb.
2. **D4, The pool: "its age and its cost".** What devcloud holds is the
   type's hourly list price times the server's age (`ops._spent`): an
   estimate, absent for an adopted machine and for a type with no price,
   and shown only for a host in an account the asking Mac's profile can
   list. Risks' row "A VM whose owning thread cannot be woken" rests on
   that line ("`sminos channel show` lists the VM's age and cost") and
   holds under the same conditions.
3. **D4, Notices: "It is written as it is today, by the VM's own `say`".**
   Today's call names no channel and cannot know the pools. It becomes a
   second call with a flag the host's boot library must hold (§4, §5), so
   a host built before this change records nothing in a channel for its
   life; D4 and the Risks do not list that. X8's writer's side gains
   `--pools`.
4. **CH's document, the Decision Log's "a notice write into any channel
   registered on the machine, with no check of the pool".** It stays true
   of `say --notice --in <channel>`. The pool is tested by the writer of
   `--pools` alone, which D4's sentence reads as a property of every
   notice in a channel.
5. **D4: "names the declared channels the new thread starts in".** A
   thread is placed once its session runs, since its id is that session's
   (Surprises, third entry): it runs in no channel for a moment, and a
   placement that fails leaves it opened and unplaced, said to the
   spawner. And D3's "A thread learns of a channel from the frame of the
   first message that reaches it from there, and from the guide at its
   next start" gains a third way for a spawned thread: its preamble.
6. **Parent acceptance line 5: "the thread that ran on the downed VM is
   out of the roster".** It is, once the org's directory has retired the
   machine, which G1's live check saw about ten minutes after the down
   (G1's plan, Concrete Steps, step 9: "allow fifteen"). The line gives no
   time; M5 waits fifteen minutes for it.
7. **EN's inheritance: "One of T1's tests of an unknown answer passes for
   the wrong reason … this child puts it right when it changes the
   reply".** G1 put it right (Surprises, sixth entry), and this plan does
   not change X9's reply. The sentence is stale.
8. **D4 and D3's Membership, extended by the holder's ruling (R1).**
   `spawn --channel` onto a stopped seat adds the named channels by the
   thread's own statement, with no request. D3 says an add of another
   thread is a request; the ruling's ground is that the door which fills
   a seat sets its record's owners and its reach (D1), more than the
   reach a request checks. The request path is untouched. The holder
   adds the parent's Decision Log entry.
9. **D4's refusal "where it would reach anyone else … it refuses at
   once", and CH2's rule for a bare name.** G1's check asks the resolver
   from a process in no channel, and a bare `@<short>` from a thread in
   channels is read as a channel-mate's alias before it is read as an id
   (`_resolve_tag`). With `--channel`, on a VM that has this change, the
   address given and checked becomes `@<project id>/<short>` (R17). What
   D4's sentence can claim is narrower than it reads: the check is of
   the moment of admission and isolates the address from other
   projects' aliases; after the spawner moves or hands off, a member of
   its old project named for the short is who the address reaches. A
   thread spawned with `--on` and no channel, and added to one later,
   keeps the bare short, and so does every child of a 1.55 VM, a refill
   of a seat that already holds channels included (§6); a 1.53.0 VM
   makes no check at all.
10. **D4's wait: "while the VM answers that it is not enrolled yet or
    that it has not yet read the spawner".** A third answer is waited on
    when channels were asked: the VM has kept no welcome of its endpoint
    yet (R19), for a named VM too, ending in the exit 75 the second
    answer ends in.
11. **D4, Notices: "recorded in the timeline of each channel whose pool
    holds the machine".** The pool is the one the host's own copy of the
    logs holds when it sends (R23): recorded after a removal the host has
    not read, not recorded for a hand-add it may not read. And what is
    recorded is a shorter text than the owning thread gets, unless the
    owner answers O6 otherwise: D4 says "written as it is today".
12. **D4, The pool: "elsewhere it says those columns are not available",
    and X9's narrowing of 2026-11-22.** There is a third state between
    shown and not available: asked, with coverage that is partial (R22).
    An account "whose provider confirmably never passed" may be left
    unasked for X9's question and may not be called covered for an
    inventory, since another Mac's VM there can be in a pool. X9 is
    unchanged.
13. **D4's second paragraph, on `--worktree`: "the Mac prints the launch
    with a note that the thread will not be listed or reached from
    here".** With `--channel`, none of the placements asked for is made
    for that thread, and the Mac says that and that the project's
    memberships will not be seen from here; it does not say which
    channels the thread is in, since a refilled seat keeps what it held
    (R21, the holder's ruling).
14. **Parent acceptance line 5, its retires.** M5 observes them on the
    thread that made the VM by having a scratch thread make it, running
    the spawn as its own task (the holder's rulings); the line is
    otherwise as G1's live run saw it for a thread a VM was handed to.
15. **D4's "the words say to look before asking again", as G1 built
    them.** The command G1's lines name, `devcloud vm ssh <vm> -- sminos
    list`, runs in the VM's login directory and lists that directory's
    project, so it can miss the seat it is offered to find. With
    `--channel` this plan's lines name `sminos list --here --all` and the
    engine's job list; without it G1's line stands (Open point 2).
16. **Parent acceptance line 8, "behave as they did".** Two flag
    prefixes argparse accepted, `spawn --c` and `say --p`, become
    ambiguous with `--channel` and `--pools` (the holder's ruling, R24):
    the line holds for the documented spellings.
