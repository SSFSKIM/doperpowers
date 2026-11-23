# sminos environments, EN.G2 — a spawn placed in a channel, a VM in `channel show`, a notice in a channel's timeline: execution (2026-11-23)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`,
> child **EN** (Environments), acceptance group **G2** (child id **EN.G2**).
> **Parent pin:** that file's blob `bd23edd6177ca411fa44d6c117c3ebb76455190e`,
> as `origin/main` holds it at `2003d1e3`. The child's section in the
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
- [ ] The plan's review, and the owner's answers to O1 to O6 (Decisions
  that are the owner's). The plan builds the recommended option of each
  unless an answer changes it.
- [ ] M1 — A spawn placed in a channel.
- [ ] M2 — `channel show`: a VM's owner, age and cost.
- [ ] M3 — A VM's notice in the timelines of the channels whose pool holds it.
- [ ] M4 — What sessions are taught, what sits beside the code, and the
  gates on the final head.
- [ ] The whole range read once (Decision Log, "Verification"), its fix
  wave, and the merge.
- [ ] M5 — The live check, on the merged change.

Each milestone's entry records, when it closes, the commit its gates were
GREEN on and the figure the `sminos-idle` gate read there.

## Acceptance

G2 of the composite's EN section, as observable items. "A Mac" is a machine
where devcloud's driver runs; "a VM" is a devcloud host, an adopted machine
included; `desk` is a declared channel the machine knows. Each item is
proved where Concrete Steps' proof map says.

1. **A thread opened on a VM is placed.** From a session on a Mac, `sminos
   spawn <alias> - --on <vm> --channel desk <<'EOF' … EOF` prints the line
   `seat spawned on <vm>: …` and then `<alias>#<short>: in desk`, exit 0.
   On the VM, the new thread's project log holds its `channels` statement
   naming `desk`'s id, under the new session's writer and after its
   `joined`; no request is written into `desk`'s log. Once the VM's events
   arrive, `sminos list desk` on the Mac lists the thread and `sminos
   channel show desk` lists `<vm>` in the pool with one live thread.
   `--channel` given twice places the thread in both channels. `--on new`
   does the same after the VM is made. The spawner need not be in `desk`,
   and the new thread is in no channel that was not named.
2. **A thread spawned here is placed.** `sminos spawn <alias> <task>
   --channel desk` with no `--on` prints `seat spawned: …` and
   `<alias>#<short>: in desk`. With `--wait` the thread is placed before
   the wait begins. A spawn onto a stopped seat that is already in another
   channel leaves it in both.
3. **Refused before anything is made or launched,** each saying why: a
   `--channel` name that no log answers, that several answer, or that is a
   project's (exit 4, in the words `sminos channel add` gives for it); a
   channel whose log this machine's enrollment does not carry; a placing
   machine whose endpoint serves no channels. With `--on`, the first two
   are decided on the Mac before devcloud is called (no VM is made); the
   last, and a channel the VM already knows and does not carry, are the
   VM's refusals, shown as the VM's line with exit 1, and a VM that `--on
   new` made is said to be kept and whose it is.
4. **After the launch nothing is a refusal.** A placement that cannot be
   recorded once the session runs (the thread's record holds an unfinished
   operation, the thread is at 128 channels, the channel's log is there and
   cannot be read) leaves the thread opened and says, in one warning for
   each channel, that it was not placed, why, and the `sminos channel add`
   that places it; the exit is 0, as it is for a spawn whose `joined` could
   not be written. A VM whose sminos predates this change opens the thread
   and places it nowhere, and the Mac says exactly that.
5. **`channel show` on a Mac.** For a pool that holds a VM, the VM's line
   reads `<vm>  1 live, 0 stopped  vm owned by <alias>#<short>, up 3d4h,
   12.34 EUR so far`: the thread that owns it by devcloud's own word, its
   age to the minute as `devcloud vm ls` prints one, and what it has cost
   at its type's list price. After `devcloud vm owner <vm> <thread>` the
   line names the new thread. An adopted machine reads `adopted, owned by
   …`, with no age and no cost. A machine devcloud has no host for keeps
   today's line, and "added by hand" stays where it was. `--json` gives
   each such pool entry a `vm` object and the answer a `devcloud` object
   (Interfaces §3).
6. **`channel show` anywhere else.** On a machine with no devcloud CLI, with
   a devcloud older than 0.19.0, or on a devcloud host, the pool prints as
   today and one line after it says that a VM's owner, age and cost are not
   shown here, and why. Where devcloud is asked and does not answer (a
   timeout, another exit, output that is not the answer), the line says
   that instead. Where it answers and one account could not be listed, a
   line names the account. In every case the members, the requests, the
   two counts and the exit status are what they were.
7. **A notice in the timeline.** A VM whose machine is in the pool of
   `desk` (a thread of it runs there) and of `ops` (a member added it by
   hand), and in no pool of `other`, sends its idle notice or its lease
   warning. Afterwards `desk`'s and `ops`'s logs each hold one `human`
   event under `<vm>/human` with `notice` `devcloud`, `to` `"*"` and the
   notice's text, and `other`'s holds none. `sminos chat desk` on another
   machine prints it from `devcloud@<vm>`. No frame is delivered for it,
   no thread is woken, the lead of `desk` is not addressed, and the
   manager's reading of what the owner said leaves it out.
8. **The notice's own delivery is unchanged.** To the thread that owns the
   VM, on to its project's live members, then into its project's log, then
   the journal and `wall`: each step runs with the arguments and in the
   order it has today, whatever became of the channels' record. On a host
   whose sminos does not know `--pools`, the host says so in its journal
   and sends nothing a second time. On a machine in no pool, nothing is
   recorded and the call exits 0.
9. **Nothing else changed** (parent acceptance line 8 for this surface). A
   `spawn` without `--channel` (its banner, its preamble, the request it
   sends a VM and the outcome line it reads), a `say` without `--pools`,
   and `channel show` of a channel whose pool holds only the machine it is
   run on print and exit as before, byte for byte against the merge base.
   Nothing is added to the daemon or the uplink, and the `sminos-idle` gate
   reads what it read.
10. **What sessions are taught is true** (X6): `sminos help`, the two
    skills and the spawn preamble say what the tree does, and the changes
    to the skills and the preamble were evaluated.
11. **On the fleet.** On the merged versions, M5's scene runs and each of
    its expectations is observed, or it is reported as not run with what is
    missing. This plan claims item 11 only when it ran.

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
  written into the log of each channel whose pool holds the host.
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
  once (Interfaces §6 is the table, and it binds).
- **Nothing new on the wire or in a log.** No event kind, no field, no
  frame, no capability. A notice in a channel is the `human` event with
  `notice` that every copy from 1.53.0 reads; a placement is the
  `channels` statement CH1 writes. So no reader ships ahead of a writer,
  MAWS is asked for nothing, and the vendored RL10 fixture is not touched.
- **Nothing in the daemon, nothing in the uplink.** Every path this child
  adds is a command's: `spawn`, `say`, `channel show`. No tick, no pass
  and no consumer-thread path gains a line, so a machine that holds no
  channel pays nothing more a tick and the consumer thread does nothing it
  did not do (C1). The `sminos-idle` gate is the check: its limit is
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
  (acceptance 4): the session runs, and a refusal would leave it running
  under a line that says nothing was spawned.
- **Byte for byte without the new flags** (acceptance 9). `--channel` and
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
  after the org retires it, until a member removes it.

## Plan of Work

Three behaviours, each a milestone that holds one contract between two
programs with both of its sides: the Mac and the VM of `spawn --on` (M1,
both sminos), sminos and devcloud's driver (M2), a host's boot library and
the host's sminos (M3). A reviewer of one milestone reads a producer with
its one consumer. M1 comes first because it carries the risk (the only
path of this child that runs after a launch) and the sminos version. M2
and M3 consume nothing of M1 and nothing of each other but
`sminos_channels.pool`, which exists and which none of them changes. M4
changes what is taught once every behaviour it describes exists, and runs
every gate on the final head. The whole range is then read once and
merged by the composite's holder. M5 runs on the merged change, the only
place a Mac and a VM both run this code. Who reviews what, and at which
rung, is the Decision Log's first entry ("Verification").

### M1 — A spawn placed in a channel

**At its end:** acceptance 1 to 4, and 9 for `spawn`. `sminos spawn …
--channel <channel>` places the new thread, here or on a VM; the sminos
plugin is 1.56.0.

**Touches:** `S/sminos.py` (the `spawn` parser; `cmd_spawn`, `spawn_here`
and `spawn_fresh` at the seam the placement needs; `render_preamble`; the
module docstring's `spawn` lines), `S/sminos_on.py` (the Mac's check of
the names, the request, the VM side's checks, `Answering.ok`,
`outcome_whole`, the Mac's lines), `S/sminos_channels.py` (the placement
of a spawned thread and what is decided before a launch),
`sminos/skills/sminos/references/spawn-preamble.md` (the place the
sentence is rendered into), `T/test_on.py`, `T/test-on.sh`,
`T/test_channels_spawn.py` (new), `T/test-channels-machines.sh`,
`T/run-sminos-tests.sh`, `S/CLAUDE.md`, the sminos version.

**Interfaces:** exposes Interfaces §1. Consumes, unchanged:
`sminos_channels.find_channel`, `register`, `change`, `_refuse_uncarried`,
`OWN_FAILED`, `LIMIT_REFUSAL`; `sminos_audience.advertised`;
`sminos.known_project`, `not_carried`, `valid_name`, `is_channel_id`;
`sminos_on.read_request`, `Answering`, `outcome_whole`, `carried`, `remote`.

**Seams:** none with an earlier milestone. With what is built: CH1's own
add, crossed by `T/test_channels_spawn.py` (a real spawn, then the record
and the statement as CH1's readers take them: `roster`, `channels_of`)
and, between machines, by `T/test-channels-machines.sh`, whose machines
run daemons and whose `claude` is the test engine: a thread spawned with
`--channel` on `beta` is in the roster and the pool as `alpha` reads
them. And G1's request and outcome line, crossed by `T/test-on.sh`, where
the VM side runs for real on a second home (that suite starts no daemon,
so what it shows of the placement is what the VM's own store holds).

**Decisions:** R1 to R6 of the Decision Log, and O5. And, seen in the
code:

- **The thread's id is the seat's, the session the launch's.** A spawned
  thread's record is its seat's (`spawn_fresh` returns `seat` and
  `session`), and `change(seat, channel, "add", session)` is the call. It
  needs the session to be a member of its project, which the launch's
  journaled `joined` makes; where that `joined` was left to the next
  reading verb, `change` finishes the entry first, and where it cannot,
  it answers `entry` or `between` and the warning of acceptance 4 is said.
- **Where the placement runs.** After `spawn_fresh` has released the
  seat's lifecycle lock and before `--wait` begins to watch
  (`finish_turn`), so a thread watched for its first turn is already
  placed. `spawn_fresh` gains what it needs for that as an argument whose
  absence is today's behaviour, call for call. A `retire` or a `fill` of
  the seat that lands between the unlock and the placement is answered by
  `change` itself (`moved`, `vacant`) and said as acceptance 4 says.
- **The VM side prints no placement line.** Its standard output is passed
  through to the Mac, which prints its own from the outcome line. A
  placement on the VM side raises nothing past `Answering`: every way it
  ends is one entry of the outcome's `channels` (Interfaces §1), since an
  exit or an exception after the launch prints no outcome and the Mac
  then says the spawn is not known.
- **The Mac resolves names; the VM is given ids.** A name is a label on
  one machine's registrations and an id always works (the composite's D3), so the Mac
  resolves each `--channel` with `find_channel` after it has checked that
  this machine is enrolled and before it looks for devcloud, and sends
  the id with the name it knows it by.
- **The order of the VM side's checks.** After `hold_to_spawner`: the
  capability, then for each channel it knows, that its enrollment carries
  it. Nothing is registered before the launch: a channel the VM does not
  know is registered when it is placed, so a refused spawn leaves no
  registration behind.

**Does not touch:** `change`, `set_channels`, `place`, `carry_due` or any
path of a request; `fill`, `seat add`, `resume`; the daemon and the
uplink; `WHYS` (a VM's refusal for a channel is `why` `other`, exit 1,
its words on standard error); devcloud; the two skills.

**Proves:** acceptance 1 to 4 and 9 (a spawn). Its tests also pin: that
the statement is the one an own add writes (C2's fields, after the
`joined`, under the new writer) and that the channel's log gains no
event; that `vm up` and `vm ssh` are not called when a name is refused on
the Mac; that a request without `--channel` and its outcome are byte for
byte G1's; that a request's `channels` outside §1's shape ends the VM
side with exit 2 and no outcome line, and an outcome's `channels` outside
it is an outcome that is not known; that each try of the Mac's wait sends
the same channels; that a VM which does not know the channel registers
it under the id and the name sent, and one that knows it keeps its own
registration; that a spawn from a terminal with `--on <vm> --channel`
places the thread; that a refill with `--channel` adds to the set the
thread holds; and, with the merge base's sminos (1.55.0) extracted from
git and run as the VM side, that the thread opens, no `channels` comes
back, and the Mac says so.

### M2 — `channel show`: a VM's owner, age and cost

**At its end:** acceptance 5 and 6. devcloud answers a program what a
named host is, and `channel show` prints it or says why it cannot; the
devcloud plugin is 0.19.0.

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
`adopt.records`, `provider.never_passed`, a provider client's `types`;
`sminos_threads.find_devcloud`, `devcloud_version`, `devcloud_timeout`,
`stop_tree`; `sminos_channels.pool`, `roster`, `show`.

**Seams:** with M1, through the roster alone: a thread that `spawn
--channel` placed on another machine is what puts that machine in a pool.
`T/test-channels-machines.sh` crosses it: after M1's case there, `channel
show` on `alpha`, its devcloud stand-in answering `vm info` for `beta`,
prints `beta`'s line with its suffix. With CH1: every case of
`T/test_channels_roster.py` that pins the pool today runs unchanged, and
its new cases stage another machine's thread as that file does (`far`).

**Decisions:** R7 to R10 of the Decision Log, and O1 and O4. And:

- **Asked once a call, and only when it could matter.** `show` asks
  devcloud once, for every machine of the pool but the one it runs on,
  and not at all when the pool holds no other machine: a machine is never
  a host devcloud can describe from itself.
- **A machine's name is a host's name.** A host's boot sets its hostname
  to its devcloud name and sminos names the machine after it, which G1's
  `is_org_machine` already rests on; names are compared without regard to
  case on both sides.
- **Who the owner is, in words.** devcloud holds a short id (X9). `show`
  prints the thread it names as `<alias>#<short>` of that thread's
  current session, resolved by the rule a `@<short>` tag resolves by
  (X2), over the org's scope and without ending the command where nothing
  or more than one answers: then it prints the `@<short>` devcloud holds.
- **The price of a type that cannot be read is no failure.** Where a
  provider's type list fails or holds no price, the host is still
  reported, with no cost, as `vm ls` prints `-`.
- **The reply is held from both sides.** devcloud's unit test pins the
  reply's shape under a name that says who reads it, and sminos's
  `T/test_vm_info.py` builds the replies its stand-in plays with the
  driver's own module imported from this tree, as `T/test_on.py` imports
  devcloud's parser; the `sminos-on-devcloud` gate runs both files, so a
  change of the reply on either side fails in the change that makes it.

**Does not touch:** `vm owned-by`, `owned_by`, `owned_vms` and X9's reply;
`vm ls`; `D/bin/devcloud` and `D/boot/**` (a host's CLI already answers
exit 6 to every `vm` verb; where no Python 3.11 is on PATH the launcher's
own answer is exit 1, which `show` reads as no answer); `pool`; `sminos
list`; the daemon's census.

**Proves:** acceptance 5 and 6, and 9 for `channel show`. Its tests also
pin: that `vm info` asks no host, runs no reaper and writes nothing (the
fixtures' call records); that a host in an account that could not be
listed is absent and the account is in `unknown`, never a host with
invented facts; that an account whose provider never passed is under
`unused`; that a name of another case finds its host; that `show` on a
machine whose devcloud is 0.18.1 does not run it; that a devcloud that
hangs is stopped at the bound and the roster still prints; that `--json`
of a channel whose pool holds only this machine is byte for byte the
merge base's.

### M3 — A VM's notice in the timelines of the channels whose pool holds it

**At its end:** acceptance 7 and 8. A host's notice is recorded in each
such channel's log by the host's own `say`, and read everywhere as CH2
already reads it.

**Touches:** `S/sminos.py` (`say`'s `--pools` in the parser and
`cmd_say`'s branch, the docstring's `say` lines), `S/sminos_channels.py`
(the writer), `D/boot/devcloudlib/notices.py`, `D/tests/unit/test_idle.py`
and `test_lease.py` (or one new file for `notices.deliver`),
`D/tests/fixtures/sminos.py`, `D/tests/integration.py` where its host
part reads the stand-in's calls, `T/test_channels_pools.py` (new),
`T/test-channels-machines.sh`, `T/run-sminos-tests.sh`, `S/CLAUDE.md`,
`devcloud/CLAUDE.md`, `devcloud/README.md`.

**Interfaces:** exposes Interfaces §4 (`say --notice <program> --pools`)
and §5 (the host's call). Consumes, unchanged: `sminos.known_channels`,
`host_name`, `not_carried`, `notice_field`, `notice_of`;
`sminos_channels.pool`, `speak`; `notices.deliver`'s `MARKED`, `HELD` and
`UNKNOWN`; `sminos_host.cli` and `cut_over`.

**Seams:** with M1: the pool a host is in is most often made by a thread
placed at its spawn. `T/test-channels-machines.sh` crosses it: with the
thread M1's case spawned on `beta`, and `gamma` added to the pool by
hand, `say --notice devcloud --pools` on each, then `chat` of that
channel on `alpha`, which holds both from `devcloud@beta` and
`devcloud@gamma`. With M2, by what it must not
do: `T/test_channels_pools.py` runs with a devcloud stand-in that records
every call and asserts none was made. With CH2: its tests of a notice in
a channel (acceptance 7's last sentence) run unchanged.

**Decisions:** R11 to R14 of the Decision Log, and O2, O3 and O6. And:

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
- **The pool is read as `channel show` reads it,** `pool(channel)` over
  one sweep of the rosters, and devcloud is never asked (Constraints).
- **The host's part is one call after the chain,** made whatever the
  chain's steps returned and changing none of them; it never sends the
  text a second time, and a failure of it changes neither the chain's
  outcome nor the host's lifetime.

**Does not touch:** the chain's three steps, their arguments and their
exits; `say --notice` without `--pools`; the readers of a marked event
(`notice_of`, `notice_sender`, the lead rule, the manager); a channel's
delivery; `D/driver/**`; the descriptor (no key is added).

**Proves:** acceptance 7 and 8, and 9 for `say`. Its tests also pin:
`--pools` without `--notice`, inside a session, beside `--in`, beside a
selector and before a text that opens with a tag, each refused before
anything is written; a machine in no pool (exit 0, nothing recorded); a
pool held by hand alone and by a stopped thread alone; two channels
written and a third passed over; the same text recorded once a channel
for one call; between machines (`test-channels-machines.sh`), the event
written on a machine that holds no member of the channel (in its pool by
hand) reaching another machine's copy of the channel's log; on the host, the fourth call's
arguments, that it follows each way the chain ends (sent at the first
step, gone on, fallen to the journal), that exit 2 says its line and
calls nothing again, and that a host with no sminos or not cut over
makes no call.

### M4 — What sessions are taught, what sits beside the code, and the gates on the final head

**At its end:** acceptance 10, and 9 whole. Every sentence a session
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
  thread is placed in each as it starts, it is in none of its spawner's
  otherwise, and a placement that failed is said with the command that
  places it. The Channels section's `channel show` line says what the
  pool shows of a VM and where, and one sentence says that a line in a
  channel's chat from `devcloud@<vm>` is that machine's notice, recorded
  for the channel and addressed to no one: the thread that owns the VM
  was told separately, and nobody answers the line. `--pools` is a
  program's and stays out of the skill, as `--notice` does; `sminos help`
  lists it.
- **What changes in `D/skills/vm/SKILL.md`:** "Its end" says that each
  notice is also recorded in the channels whose pool holds the VM, read
  with `sminos chat <channel>`, and that `sminos channel show <channel>`
  on a Mac shows who owns each VM of the channel, how long it has run and
  what it has cost. `vm info` stays out, as `vm owned-by` does.
- **What the skills must not promise:** a notice recorded in a channel
  is delivered to no one, so it is no substitute for the notice to the
  owning thread; it is recorded only by a VM made from now on, whose own
  sminos is updated ("a VM made from now on", as G1's text says it); the
  cost is the list price times the age; and `channel show` shows a VM
  only where the Mac it runs on can list the VM's account.
- **The evaluation is small and aimed at what a wrong reading costs.**
  Four scenarios, run as doperpowers:writing-skills prescribes, against
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
  that the facts are not shown there, and invents none). The report says
  what each run did under each text.
- **TECH-DEBT rows,** in the section "sminos environments", each with
  what would promote it: the six of Constraints' "Accepted, and not
  built". The row "A machine still downloading a project's log reads a
  member's absence as a fact" gains the pool as one more reader.

**Does not touch:** any behaviour; the guide (`guide_text`), which says
nothing of spawning or VMs and lists a thread's channels from its record
at its next start; the manager's skill.

**Proves:** acceptance 10 (X6 for this child) and 9 whole: every gate on
the final head, and the focused files of Concrete Steps run once more as
the acceptance's own commands.

### M5 — The live check, on the merged change

**At its end:** acceptance 11: the scene of Concrete Steps has run on the
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

- **Kept to what the stand-ins cannot show.** Three things: a VM enrolled
  moments ago placing its thread (its endpoint's welcome kept by then,
  the channel registered from the request or the directory); devcloud's
  real answer about a real server (a creation time, a price, the time the
  question takes); and a real host's boot library, a real sminos and the
  real endpoint and hub carrying a host's `human` event under a channel's
  id to another machine, which CH2 proved against the fixture and a
  stand-in only. The refusals, the older copies and every failure path
  stay the suites'.
- **What it costs.** One VM of the profile's default type for under an
  hour (cents at list price), and about forty minutes: `vm up` on the
  slow path, since M3 moved the recipe hash, and up to fifteen minutes
  for the org's directory to retire the machine after the down. No retry
  makes a second VM without the holder's word.
- **A scratch channel, made and emptied by the run.** The run creates it
  and is its first member, and removes itself last, so the channel is
  left with no member and leaves the directory by its own rule. Its log
  stays at the hub, as every channel's does; the report says so.

**Proves:** acceptance 11, which is parent acceptance line 5 on released
versions.

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
| 2 a thread spawned here is placed | M1: `test_channels_spawn.py` (a new seat, a refill, `--wait`, the statement's shape, no request) |
| 3 refused before anything is made | M1: `test_on.py` (the names and the uncarried channel, with devcloud's stand-in recording no call), `test-on.sh` (the VM's capability refusal and the kept VM's words), `test_channels_spawn.py` (the same refusals here, no launch) |
| 4 after the launch nothing is a refusal | M1: `test_channels_spawn.py` (each `failed` word and the limit), `test-on.sh` (the outcome's `channels` with a failed entry; the merge base's sminos as the VM side) |
| 5 `channel show` on a Mac | M2: `test_driver_info.py` (the reply for a VM, an adopted machine, a host with no price, a handed-on host), `test_vm_info.py` (sminos's reading of the driver's own replies), `test_channels_roster.py` (the lines and `--json`), `test-channels-machines.sh` (the suffix for a machine a spawned thread put in the pool); M5 |
| 6 `channel show` anywhere else | M2: `test_vm_info.py` (no CLI, an older devcloud, exit 6, a timeout, another exit, a malformed answer, an account not listed), `test_channels_roster.py` (the line for each, the roster unchanged) |
| 7 a notice in the timeline | M3: `test_channels_pools.py` (which channels, the event, nothing delivered), `test-channels-machines.sh` (written on one machine, read by another's `chat`); built by CH2 and run unchanged: `test_channels_say.Words`, `test_channels_lead` (the lead rule, a tagged notice, the manager's classifier); M5 |
| 8 the notice's own delivery is unchanged | M3: `test_idle.py`, `test_lease.py` (the chain's calls as before, the fourth call, exit 2), the `devcloud-host` gate (the host's services against the sminos stand-in) |
| 9 nothing else changed | M1 to M3: a comparison with the merge base's sminos, extracted from git, in each milestone's suite (the banner, the preamble, the request and the outcome of a spawn with no channel; a `say`; `channel show` of a pool of one); M4: every gate on the final head |
| 10 what sessions are taught is true | M4: the evaluation's report; the tests that pin the preamble's lines and `sminos help` |
| 11 on the fleet | M5 |

**M5, the scene.** Run by the plan's executor in a session on a Mac where
devcloud's driver runs, after this child's pull request is merged, as one
script it writes in a scratch directory outside the repository, under
G1's M5 rules (the ledger of intents, the stamps, one cleanup, three
states). `<run>` is four hex digits drawn for the run; `<A>` is the short
id of the session that runs it, which must be a thread of that Mac whose
reach is the machine's default, in a worktree whose branch origin holds
at its commit.

0. Before anything is made: this Mac's marketplace clone and its daemon
   run sminos 1.56.0 or later and devcloud 0.19.0 or later, and
   `en-live-<run>` names no channel, no seat and no host. Otherwise: not
   run, with what is missing.
1. `sminos channel create en-live-<run>`. Expect the session placed in it,
   and `sminos list en-live-<run>` listing it alone.
2. A local scratch seat: `sminos spawn en-live-b-<run> "Say ready, then
   stop and wait." --stamp en_live_run=<run>`.
3. The spawn, with `DEVCLOUD_TEST_RUN=en-live-<run>` in its environment:

       sminos spawn en-live-<run> - --on new --channel en-live-<run> \
           --stamp en_live_run=<run> <<'EOF'
       Say where you run, to your spawner, then stop and wait.
       EOF

   Expect: devcloud's lines, perhaps the notes that it waits, then `seat
   spawned on <vm>: …`, `en-live-<run>#<short>: in en-live-<run>`, the
   note that the VM is kept and this session's thread owns it, exit 0.
4. The VM's sminos, before anything is attributed to this release: its
   plugin manifest on the host names 1.56.0 or later (G1's step 3). A host
   whose declared source is pinned elsewhere shows another: the report
   then says which copy the steps ran on and claims none for this release.
5. Within two minutes `sminos list en-live-<run>` lists two threads, the
   second on `<vm>`. `sminos channel show en-live-<run>` prints, in its
   pool, `<vm>  1 live, 0 stopped  vm owned by <this session's
   alias>#<A>, up <minutes>m, <a small amount> <currency> so far`. The
   command is timed three times; the report gives the three wall times
   beside one of `sminos channel show` of a channel whose pool holds only
   this Mac.
6. A notice, through the host's own delivery, as root (G1's step 8, the
   same program):

       devcloud vm ssh <vm> --root -- 'python3 -P - <<"PY"
       import os, sys
       sys.path.insert(0, os.path.dirname(os.path.realpath("/usr/local/bin/devcloud")))
       from devcloudlib import descriptor, notices
       from devcloudlib.proc import User
       d = descriptor.load()
       notices.deliver(User.from_image(), d, "devcloud on %s: a check of the notice path; nothing to do" % d.name)
       PY'

   Expect, on the host: `devcloud notice: sent: …`, then a line `devcloud
   notice: channels: recorded <ref> in en-live-<run>`. On the Mac, within
   two minutes: `sminos chat en-live-<run> -n 5 --json` holds a `human`
   event under `<vm>/human` with `notice` `devcloud` and `to` `"*"`, and
   `sminos chat en-live-<run> -n 5` prints it from `devcloud@<vm>`; the
   session received the notice addressed to it in its project as G1
   delivers it, and no second frame for the channel's record.
7. Hand the VM on and try to retire its new owner:

       devcloud vm owner <vm> en-live-b-<run>
       sminos channel show en-live-<run>
       sminos retire en-live-b-<run>

   Expect: the pool's line now names `en-live-b-<run>#…`; the retire is
   refused, exit 1, naming `<vm>`.
8. `devcloud vm down <vm>`, then `sminos retire en-live-b-<run>`, which
   succeeds. Within fifteen minutes (the org's directory retires the
   machine about ten minutes after the down) `sminos list en-live-<run>`
   lists this session alone and `sminos channel show en-live-<run>` lists
   no `<vm>` in the pool.
9. `sminos channel remove en-live-<run>`: the channel has no member, and
   `sminos list --org` no longer shows it.

The report opens with every intent and its state; then, for each step, its
command and what it printed; the time `vm up` took and whether it took the
slow path; the three timings of step 5; and the versions the Mac and the
VM ran.

## Interfaces and Dependencies

Names in the code today are given as they are; what a milestone adds is
marked with its milestone. Sentences given in full are decisions (a test
or another program reads them); any other wording is the executor's.

### §1. `spawn --channel` (M1)

**The flag.** `sminos spawn … --channel <channel>`, given any number of
times; each value a channel's name, `name#short` or id, as `find_channel`
takes one; a channel named twice counts once. It adds: a spawn onto a seat
whose thread is already in channels leaves those as they are.

**Decided before a launch, on the machine `spawn` is typed on:**

| Condition | What happens |
|---|---|
| a name no log answers, several answer, or a project's | exit 4, `find_channel`'s words; with `--on`, before devcloud is looked for |
| the channel's log is not carried by this machine's enrollment (a registration of no hub or another org, one the directory retired; not one that has left this machine, which a placement brings back) | exit 1, with the reason `_refuse_uncarried` gives, saying that nothing was spawned |
| no `--on`, and this machine's endpoint serves no channels (`advertised("channels")` false) | exit 1, saying so and that dropping `--channel` spawns it in no channel |

**The request** (the Mac side to the VM side) gains one key, present only
when `--channel` was given:

    "channels": [{"id": "<the channel's id>", "name": "<its name on the asking machine>"}, …]

`read_request` takes it only whole: a list of 1 to 128 objects, each `id`
a channel's id (`is_channel_id`) and each `name` a name (`valid_name`),
no id twice. Present and anything else: exit 2 and no outcome line, as
for any request this version does not read.

**The VM side, before its launch,** after `hold_to_spawner`, each a
refusal of `why` `other`, exit 1, its words on standard error ending
"nothing was spawned": its endpoint serves no channels; a channel it
already knows whose log its enrollment does not carry. It registers
nothing and writes nothing before the launch.

**The placement,** on the placing machine, once the launcher has returned
the session: for each channel in the order asked, registered first where
the machine does not know it (`register(id, name)`, on the VM side only:
here `find_channel` already found it), then `change(<the seat's id>,
<channel>, "add", <the new session>)`.

**The outcome line** gains one key on a success, present exactly when the
request carried `channels`, one entry a channel in the request's order:

    "channels": [{"id": "<id>", "state": "applied" | "refused" | "failed", "why": "<word>"}, …]

`why` is `""` or `unchanged` for `applied`; `limit` for `refused`; for
`failed`, `change`'s word (a key of `OWN_FAILED`), `unregistered` (it
could not be registered there) or `error` (anything else, said on the
VM's standard error). `outcome_whole` takes the key, where present, only
as such a list; a Mac that sent no channel ignores it. The Mac holds it
to its call as it holds the alias: a list that does not name exactly the
ids asked, in order, is an outcome that is not known.

**What is printed,** after the seat's line, one line a channel:

| Case | Line |
|---|---|
| placed | `<alias>#<short>: in <channel>` (`already in <channel>` where the thread held it), on standard output |
| not placed, here | warning: `spawn completed, but <alias>#<short> was not placed in <channel> (<why>): sminos channel add <channel> <alias>#<short> places it` |
| not placed, on a VM | warning: the same, with `on <machine>` after the channel and ending `sminos channel add <channel> <short> asks its machine, once it is listed here` |
| a success line with no `channels` when some were asked | warning: `spawn completed, but <machine>'s sminos placed <alias>#<short> in no channel (it predates spawn --channel): sminos channel add <channel> <short> asks its machine, once it is listed here`, naming every channel asked |

`<why>` in words: `OWN_FAILED`'s sentence for its word, `LIMIT_REFUSAL`'s
reason for `limit`, and a word the Mac does not know as itself. The exit
is 0 in all four.

**The preamble** gains one sentence, rendered only where channels were
asked, after the paragraph that explains channels, naming them as the
spawner's machine names them:

> You are being placed in the channel "desk", as your spawner asked:
> `sminos list desk` shows you there once it is recorded, `sminos chat
> desk` reads it, and `sminos say --in desk "…"` speaks in it.

(for several: `the channels "desk" and "ops"`, the three commands shown
for the first). Without `--channel` the rendered preamble is today's,
byte for byte.

### §2. `devcloud vm info` (M2)

A program's verb, like `vm owned-by`: out of the vm skill, in
`devcloud/CLAUDE.md` and the driver's synopsis.

    devcloud vm info <name>...

One JSON object on one line of standard output, exit 0:

    {"hosts":   [{"name": "dc-x-0001", "account": "main", "provider": "hetzner",
                  "creator": "@1a2b3c4d", "created": 1763850000, "spent": 0.47, "currency": "EUR"},
                 {"name": "box-1", "account": "adopted", "provider": null, "adopted": true,
                  "creator": "@5e6f7a8b", "created": null, "spent": null, "currency": null}],
     "unknown": [{"account": "…", "provider": "…", "failed": "account" | "listing", "reason": "…"}],
     "listed":  ["main"],
     "unused":  []}

- `hosts`: every server of every configured account (`Context.census(kinds=None)`)
  and every adoption record whose name equals a name asked, compared
  without regard to case. A name no host has is absent.
- `creator`: `@` and the short id the host holds (the label
  `devcloud-creator`, an adoption record's `creator`), or null where it
  holds none. The word is the label's; after a handover it is the owning
  thread's session, as in X9.
- `created`: Unix seconds, as the provider reports the server's creation;
  null for an adopted machine.
- `spent` and `currency`: the type's hourly list price times the server's
  age when asked, and the price's currency, by the rule `vm ls` prints
  SPENT with; both null for an adopted machine, for a type with no price
  and where the provider's type list could not be read.
- `unknown`, `listed`, `unused`: X9's meanings and shapes, computed as
  `vm owned-by` computes them.
- No name: a usage error, exit 2. Exit 6: the driver does not run on this
  machine, said by the copy that has no driver or by the driver for a
  missing seed key, as for every `vm` verb. Any other exit printed no
  answer.
- It asks no host, runs no reaper and writes nothing.

sminos asks it through one function beside `owned_by` in
`S/sminos_threads.py`, found, bounded and stopped as `owned_by`'s
question is, and run only from a devcloud of `DEVCLOUD_INFO_MIN = (0, 19,
0)` or later (the copy `SMINOS_DEVCLOUD` names is taken at its word). Its
bound is the smaller of 20 seconds and `devcloud_timeout()`.

### §3. `channel show`'s pool (M2)

`show` asks §2 once, naming every machine of the pool but its own, and
not at all for a pool that holds no other. What it concludes is one of:

| State | When | What is printed after the pool's lines |
|---|---|---|
| asked | exit 0 and a whole reply | for each entry of the reply's `unknown`: `(devcloud could not list <account>: a VM there shows no owner, age or cost)` |
| unavailable | no CLI found; a version that cannot be read or is older than 0.19.0 (not run); exit 6 | `(a VM's owner, age and cost are not shown here: <why>)` |
| failed | it could not be run; no answer within the bound (stopped); another exit; output that is not a whole reply | `(a VM's owner, age and cost are not shown: <why>)` |
| unasked | the pool holds no machine but this one | nothing |

A whole reply is an object with the four keys of §2, each of its type,
each host's name among those asked, and each host in one of two forms (a
provider named and no `adopted`; no provider and `adopted: true`), with
`creator` null or `@` and hex digits, `created` and `spent` numbers or
null, and `currency` a string or null. Anything else is `failed`.

A pool line for a machine a host answers for gains a suffix:

    dc-x-0001  1 live, 0 stopped  vm owned by coord#1a2b3c4d, up 3d4h, 12.34 EUR so far
    box-1      0 live, 1 stopped, added by hand  adopted, owned by coord#5e6f7a8b

`up` is the age as `vm ls` prints one (`3d4h`, `5h10m`, `12m`), from
`created` and this machine's clock; the amount has two decimals and its
currency where one is given, and is left out, with its comma, where
`spent` is null; `owned by` is left out where `creator` is null. The
owner is `<alias>#<short>` of the current session of the thread the short
id names, or the `@<short>` devcloud holds where no thread, or more than
one, answers to it. Every other line is today's.

`--json`: such a pool entry gains

    "vm": {"adopted": false, "account": "main", "provider": "hetzner",
           "owner": {"creator": "@1a2b3c4d", "thread": "<thread id>", "session": "<its current session>", "alias": "coord"},
           "created": 1763850000, "spent": 0.47, "currency": "EUR"}

(`owner` null where the host holds no creator; `thread`, `session` and
`alias` null where the short id resolves to no one thread), and the
answer gains, in every state but unasked,

    "devcloud": {"state": "asked" | "unavailable" | "failed", "why": "<the line's reason, or \"\">", "unknown": [ … ]}

### §4. `say --notice <program> --pools` (M3)

    sminos say --notice <program> --pools <text>

Records `<text>`, untagged, as this machine's notice in the log of every
channel whose pool holds this machine. A program's form: it is what a
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
  lead. Its line on standard output is `say`'s own, `recorded <ref> in
  <channel>`.
- A channel that has left this machine is passed over without a word.
  One whose log this machine's enrollment does not carry, or whose append
  fails, is said on standard error and passed over; the others are
  written.
- No channel holds this machine: `no channel's pool holds this machine:
  nothing was recorded` on standard output.
- The exit: 0, or 1 when a channel was passed over for a failure. Never
  2 for anything but a usage error: a host reads 2 as a sminos that does
  not know the flag.
- It writes into no project's log, delivers nothing and wakes no one.

### §5. A host's delivery (`D/boot/devcloudlib/notices.py`, M3)

`deliver(user, d, text, call, say)` keeps its chain as it is. After the
chain, whichever way it ended, and only where the chain itself would call
sminos (a CLI found by `sminos_host.cli`, the host cut over), it makes one
more call, as the same user, with the same environment, working
directory, log and timeout:

    say --notice devcloud --pools <text>

| Exit | What the host says, and does |
|---|---|
| 0 | each line of sminos's standard output, as `devcloud notice: channels: <line>` |
| 2 | `devcloud notice: this host's sminos does not know --pools; no channel's timeline was written`; nothing is called again |
| any other | `devcloud notice: the channels' record failed (exit <n>): <error>` |

Whether the notice falls through to the journal and `wall` is the chain's
alone, as today. The call changes no lifetime and takes no lock the chain
does not take.

### §6. An older copy on the other side

| What is new | The older copy | What happens |
|---|---|---|
| the request's `channels` | a VM's sminos 1.53.0 to 1.55.x | It reads the fields it knows and opens the thread in no channel; its outcome has no `channels`; the Mac says the thread was placed in none (§1). |
| the outcome's `channels` | a Mac's sminos up to 1.55.x | It sent none, so none comes back. |
| a host's `--pools` call | the host's sminos up to 1.55.x | A usage error, exit 2: the host says its line and calls nothing again; the chain is as it was. |
| a sminos that knows `--pools` | a host built before this change | No such call is made: its notices are in no channel's timeline, for its life (accepted). |
| `vm info` | a Mac's devcloud up to 0.18.x | Not run: sminos reads the version first and prints the unavailable line. |
| devcloud 0.19.0 | a sminos up to 1.55.x | It never asks. |
| a notice in a channel's log | any sminos, MAWS's endpoint and app | No new kind and no new field: an untagged marked `human`, which 1.55.0 reads as that machine's notice and 1.54.1 stores. A copy from before channels follows the channel's log as a project's (D7) and delivers an untagged event to no one; one older than 1.53.0 shows it under `human`, as it shows every notice. |
| a thread placed at its spawn | any reader | The `channels` statement CH1 writes, read as any own add. |

### §7. What the tests are built on

- `T/devcloud_standin.py` learns `vm info`, playing replies that
  `T/test_vm_info.py` builds with the driver's own `info` module from this
  tree, and each way of giving no answer (as it plays `owned-by`'s).
- `T/test-on.sh`'s second home is the VM: the VM side runs for real there,
  over the stand-in's `vm ssh`. One case runs the merge base's sminos
  (1.55.0), extracted from git as `T/test_channels_say.py`'s `extracted`
  does, as that VM side.
- `T/test-channels-machines.sh`'s three machines, each a real home with
  its daemon and an endpoint stand-in that serves `channels`, their
  `claude` the test engine (`T/wake_engine.py`), carry a project's and a
  channel's log between machines: it is where a spawn on one machine is
  read by another. `T/test-on.sh` starts no daemon, so it shows only what
  each home's own store holds.
- `D/tests/fixtures/sminos.py` learns `--pools`: it records the call as a
  sminos that knows the flag, and with `sminos-old-say` in the state
  directory answers exit 2, as it does for the notice flags.
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
the milestone a different answer would change.

- **O1. What `channel show` prints for a VM's cost, and in what unit.**
  (a) What it has cost so far: the type's hourly list price times its
  age, in the provider's currency, as `devcloud vm ls` prints SPENT
  (`12.34 EUR so far`). (b) The hourly price alone. (c) Both.
  **Built: (a).** It is the figure the Grounding Baseline's own
  observation is made in (a VM kept twenty days, above 100 euros), and
  one command and the other then agree. It is an estimate at list price,
  not a bill, and is absent for an adopted machine and a type with no
  price. A different answer changes §3's suffix (M2).
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
- **O6. The words of a notice in a channel.** (a) The notice's own text,
  as the host sends it to the owning thread: the VM's name, how long it
  has idled or when its lease ends, and the repositories on it that hold
  unpushed work. (b) A shorter text for channels that names the VM and
  the event and leaves the repositories out. **Built: (a).** The event is
  plain: every reader of the channel's log reads it, whatever the reach
  of the thread that owns the VM. That is already so of the note the
  chain leaves in the owning thread's project, and a channel's readers
  are a wider set than a project's. A different answer changes §5's call
  (M3), and must be given before M3 is built, since a host keeps what it
  was built with.

## Open points

1. **How long `channel show` takes on the fleet** once it asks devcloud
   (O4). Not measurable from the tree; M5's step 5 measures it.
2. **Whether a VM enrolled moments ago has kept its endpoint's welcome by
   the time it has read its spawner.** §1's VM side refuses, and is not
   waited on, where `advertised("channels")` is false. The welcome is kept
   at the uplink's first connection and the spawner's row comes from that
   connection's download, so it should always be there first; M5 is where
   that is seen. If it is not, the refusal joins the two the Mac waits on,
   as a patch.
3. **A host's `human` event under a channel's id through the real endpoint
   and hub.** CH2 proved it against MAWS's fixture and a stand-in and says
   it was not yet read from a real endpoint. M5's step 6 is the first real
   reading; a failure there is the wire's, and goes to the holder.
4. **An adopted machine whose own name differs from its devcloud name**
   shows no owner in `channel show`, since the two are matched by name.
   No such machine is known; a row if one is seen.
5. **Who runs M5.** As in G1, the plan's executor, which must be a thread
   of a Mac where the driver runs; if the executor's session is none, the
   holder runs the scene from one.
6. **The `sminos-channels` gate's room.** Two new files join a part that
   took up to 3m38s against 8 minutes. Each milestone reports it.
7. **A machine added to a pool by hand and since retired by the org**
   stays in `channel show` with no thread and, being no host any more,
   with no suffix. CH1 built that, and O3's recommended answer leaves it;
   a TECH-DEBT row records it.

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

## Decision Log

The entries R1 to R16 are the residue decisions made while this plan was
written, each with the alternative it beat; a milestone's Decisions slot
points at them. The owner's decisions are not here: they are O1 to O6,
above.

- 2026-11-23 — **Verification.** This plan gets one review before it is
  built, by the `doperpowers:adversarial-reviewer` agent, on buildability:
  the milestones against the code, the shapes and sentences of Interfaces
  against the composite, and §6's table against what each older copy
  really does. The build runs under `doperpowers:plan-executor`, a fresh
  executor a milestone, each milestone reviewed at its close by the
  execution loop's reviewer. After M4 the composite's holder reads the
  whole range once, through doperpowers:review-code at the panel rung
  `xhigh`, with these lenses given: each of the three contracts read from
  both of its sides (§1's request and outcome, §2's reply and §3's
  reading of it, §4's flag and §5's call); that every refusal comes
  before its side effect and nothing after a launch is one; §6's older
  copies; and acceptance 9 over the whole diff. Its confirmed findings go
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
  lens. What a milestone's reviewer cannot see here is the other machine
  and the older copy, which is what the one whole reading is aimed at.
  *Alternative rejected:* no whole reading, since each contract sits in
  one milestone: the claim of acceptance 9 and §6's table are properties
  of the whole diff.
- 2026-11-23 — **R1. A spawn places its thread by the thread's own
  statement, on the placing machine.** `change`, the path of a thread
  that adds itself (C2), with no request in the channel's log. Who may
  place a thread is not in question: the spawner made it. *Alternative
  rejected:* the spawner's `channel add` after the outcome line, a
  request the VM carries out. The Mac would have to name a thread whose
  `joined` it has not read yet, the placement would wait for the VM to
  download the channel's log and for its endpoint's word, and `channel
  show` would list a request nobody needed.
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
  is not waited on.** `WHYS` keeps its rows. *Alternative rejected:* a
  row of its own that the Mac waits out, as it waits out `not-enrolled`:
  nothing shows the case arises once the spawner has been read (Open
  point 2), and a wait built for a case never seen is a wait that hides
  the real refusal.
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
  roster prints whatever becomes of it.** `owned_by`'s minute is right
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
- 2026-11-23 — **R13. One program word, `devcloud`, and the notice's own
  text** (O6 is the owner's question on the text).
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

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

What this plan found against the composite's text, each with its evidence
and the clause it bears on. Nothing here is edited by this child.

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
