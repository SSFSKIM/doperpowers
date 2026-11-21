# sminos environments, EN.G1 — a thread on a VM, a VM handed on, a VM's notice: execution (2026-11-21)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, child **EN** (Environments), acceptance group **G1**. **Parent pin:** `main` at `5a5ec39d`, that file's blob `86c24bd71da5c4e0301168ec0259af848cbe08df`. The child's section in the composite is its spec. D4 is its design, binding where marked, with D1 ("Naming a thread", "Lifecycle"), D2 ("One path", "Not woken") and D7; X2, X3, X6, X7, X8 and X9 are its contracts. On 2026-11-21 the composite's holder ruled on ten points that D4 left open or stated against the code (R1 to R10, written after the code map below was read) and, the same day, relayed the answers of MAWS's architect and ruled on the thirteen findings of this plan's review. Those rulings have D4's standing where they revise it. They live in no file of this tree, so this document states each one where it binds (Constraints, a milestone's Decisions, Interfaces), and its last section lists the sentences of the composite they replace. G2 (`--channel`, `sminos channel show`, a notice in a channel's timeline) is not in this plan. This document carries the constraints and the milestones and nothing of the design.
>
> **Read before M1:** the composite's Purpose, Terms, D1, D2, D4, D7, the sections EN, T1, T2 and DV, and X1 to X3 and X6 to X9; the code map `docs/doperpowers/research/2026-11-17-sminos-channels/en-code-map.md` (the code as it stood at `dba3f5e8`, with what this plan's author corrected marked in it); `devcloud/CLAUDE.md`, `sminos/CLAUDE.md` and, in `sminos/skills/sminos/scripts/CLAUDE.md`, the paragraph on which hosts a thread owns; T1's plan `docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`, Interfaces §7 (the question put to devcloud); T2's plan `docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md`, Interfaces §4 and §5 (what delivery does with a stopped thread, and the lines a sender reads).

Today a session on a Mac that wants work done on a cloud machine runs `devcloud vm up`, then `devcloud vm ssh <name> -- sminos spawn …` by hand. The session it gets there is "spawned by the operator", is invisible to every other machine unless the VM happened to be made with the MAWS project, and cannot tell its spawner anything unless it was given a tag in its task. The VM belongs to the session that made it for as long as that session lives, and nobody else can take it over. Its idle and lease notices go to that session's short id as a person's words.

After this child:

- **One command opens a thread on a VM.** `sminos spawn --on <vm> <alias> <task>` opens it on a VM that exists, and `sminos spawn --on new <alias> <task>` makes the VM first, with the spawner's repository at its pushed branch, enrolled in the org and kept. The new thread knows who spawned it and how to reach it.
- **A VM can be handed on.** `devcloud vm owner <vm> <thread>` gives a VM to another thread of the same Mac. The thread that gave it up can then be retired; the one that took it cannot until it downs the VM or hands it on.
- **A VM's notice is a machine's notice.** It reaches the current session of the thread that owns the VM, wakes that thread if it is stopped, and arrives framed as coming from `devcloud@<vm>`, never as the person's words. Where the VM's own `say` reports that the owning thread is held and will not be woken with it, the notice goes on to the live members of that thread's project.

How to see it working is the acceptance below, proved by suites that run a real sminos and a real devcloud driver against stand-ins, and at the end by one check on the owner's fleet (M5).

## Progress

- [x] (2026-11-21) The code map for EN.G1 written at `dba3f5e8` and the holder's rulings R1 to R10 on its open choices.
- [x] (2026-11-21) This plan written against the composite at `5a5ec39d` (sminos 1.52.2, devcloud 0.17.3), with the three answers of MAWS's architect folded in.
- [x] (2026-11-21) The plan's one review for buildability (thirteen findings), the holder's ruling on each, and this revision (Decision Log, "The plan's review").
- [ ] M1 — A machine's notice: the marker, the exit that lets it go on, and the host that sends both.
- [ ] M2 — A VM handed to another thread.
- [ ] M3 — A thread opened on a VM with one command.
- [ ] M4 — What sessions are taught, what sits beside the code, and the gates on the final head.
- [ ] The whole range reviewed (Decision Log, "Verification"), its fixes, and the merge.
- [ ] M5 — The live check, on the merged change.

## Acceptance

G1 of the composite's EN section, as observable items. "A Mac" is a machine where devcloud's driver runs; "a VM" is a devcloud host, an adopted machine included. Each item is proved where Concrete Steps' proof map says.

1. **One command, a new VM.** From a session on a Mac, in a worktree whose current branch origin holds at the worktree's commit, `sminos spawn --on new <alias> - <<'EOF' … EOF` prints devcloud's own lines while the VM is made, then one line `seat spawned on <vm>: …`. devcloud was called as `vm up --enroll --keep --expect-creator <the spawner's short id> --label <alias> --project <owner>/<repo>@<branch>`, and with `--confirmed` only when `--vm-confirmed` was passed. devcloud makes nothing when the creating session it reads is another, or none. `devcloud vm ls` shows the VM kept, its owner the spawning session's short id.
2. **One command, a VM that exists.** `sminos spawn --on <vm> <alias> <task>` opens a session on that VM, an adopted machine included, in the VM's checkout of the spawner's repository, or in the directory `--cwd` names there. The task travels on standard input, and a task holding quotes, backticks, `$` and several lines arrives as written. The Mac prints the spawn's line only on one whole outcome line from the VM (Interfaces §8); on none, two, a malformed one or one the exit status contradicts, it says that the outcome is not known, exits non-zero and names the command that shows what is on the VM.
3. **The spawner travels with the spawn.** The new session's first message names its spawner's alias, short id, project and machine and the tag that reaches it, and `sminos say "@<that short> …"` run on the VM reaches the spawner's current session. Spawned from a terminal with `--on <vm>`, it says "the operator" as today.
4. **Refusals, each saying why, with nothing made and nothing spawned:** `--on` run on a devcloud host; `--on` from a machine that is not enrolled; `--on` naming this machine; `--on` from a session that is no member of a project, or whose project syncs through no hub; `--on` from a session whose reach is not its machine's default or cannot be resolved (read again before each call to the VM, so a reach narrowed while a VM is made refuses the spawn, saying that the VM is kept); `--on <name>` that devcloud has no VM for (devcloud's own line, and the Mac's reason added when the org lists that name as a machine); `--on <vm>` whose machine is not enrolled in the org, or is enrolled in another org; a VM whose checkout, where the directory was inferred, is another repository's; `--on new` under a profile that cannot enroll a VM (devcloud's refusal, before any VM exists); `--on new` from a terminal; `--on new` from a worktree on no branch, on a branch origin lacks, or whose commit origin's branch is not at, each with the two ways out; `--on` with `--wait` or `--settings`. A cap refusal of devcloud passes through with devcloud's exit 4 and its line.
5. **Waiting for enrollment.** `--on new` whose VM is up and not enrolled yet says what it waits for, tries again for up to eleven minutes, and spawns when the VM enrolls. Past the bound it exits 1 saying that the VM is kept, who owns it, and the command that spawns on it later.
6. **The handover.** `devcloud vm owner <vm> <thread>` takes any name sminos resolves to a thread (an alias, `alias#short`, a tag, a short id, a thread id, a former session's id), accepts a thread of the machine it is run on that has not ended, a stopped one included, and prints who owned the VM and who owns it now. It refuses a thread of another machine, an ended one, a vacant seat and a name that is no thread, changing nothing. It works for an adopted machine and for a host made before this change. It reports a handover only after reading both of its writes back: stopped between them, crossed by another handover, or left without a reply by the host or the provider, it says what each side holds, exits non-zero where they differ, and run again it settles. The host is told the thread's project by its id.
7. **Who a retire refuses.** After a handover, `sminos retire` of the thread that gave the VM up succeeds, and `sminos retire` of the thread that took it exits 1 naming the VM and both ways on (`devcloud vm down <vm>`, `devcloud vm owner <vm> <thread>`).
8. **A notice follows the thread.** A VM's notice reaches the current session of the thread that owns the VM after that thread changed session id (a hand-off to a background job, a refill), once the VM has read that change, and wakes that thread when it is stopped. This holds for a host made before this change, whose descriptor names a former session's short id and whose boot library is unchanged. A notice written before the VM has read the change names the session the thread left: it is in the project's log and counted unread for the current session, and is not pushed (accepted; Decision Log, "The lagging view").
9. **A notice is a machine's.** From a host made with this change, read by a sminos of this change, the notice reaches the session as `[sminos chat <project> <ref> from devcloud@<vm>… → @you]` in the peer envelope with no reply line, and never through the bridge or a background job's supervisor, whichever verdict the endpoint gave, nor inside one payload with a person's words. `sminos chat` and the TUI show the same sender. The manager's reading of what the owner said leaves it out.
10. **A notice goes on.** When the VM's `say` reports that the owning thread is held and not woken (for any reason its machine published), has ended, or is no member, the notice goes to the live members of that thread's project; when none is live, into that project's log as an untagged note, whatever the first step recorded; then to the host's journal and `wall`.
11. **Nothing else changed** (parent acceptance line 8 for this surface). A `say` without the two new flags, a `spawn` without `--on`, a `who` without `--thread` and a `retire` of a thread that owns nothing print and exit as before; the retire refusal's words are the one visible change. Every suite that passed before passes.
12. **On the fleet.** On the merged versions, M5's check runs and each of its expectations is observed, or it is reported as not run with what is missing. This plan claims item 12 only when it ran.

## Words this document adds

The composite's Terms define the owner (the person, and only the person), thread, project, log, writer, member, seat, deliver, wake, the daemon, the hub, the endpoint, reach, lane B and devcloud. T2's plan defines held and woken. Added here:

- **A host** is a machine devcloud manages: a VM it made, or a machine it adopted. **The driver** is `devcloud vm`, the part of devcloud that runs on a Mac (`devcloud/driver/`). **The boot library** is what a host itself runs (`devcloud/boot/`), installed when the host is built and never updated afterwards.
- **The descriptor** is a host's `/etc/devcloud/boot.env`: `KEY="value"` lines the driver composed, which the host reads again at every tick of its lease service (five minutes). `DEVCLOUD_CREATOR` holds a sminos tag and `DEVCLOUD_CREATOR_PROJECT` a project's name or id.
- **The owning thread** of a host is the thread one of whose sessions the host names. A host names a session by its **short id**, the first eight characters of the session id, in up to three places: the provider's label `devcloud-creator` (a VM) or the Mac's adoption record (an adopted machine), and the descriptor. The stored names keep the word "creator"; after a handover what they hold is the owning thread's session.
- **Enrolled** is said of a machine whose sminos has an identity from MAWS's endpoint (`daemon/identity.json` under sminos's home, read by `enrollment()`). Only an enrolled machine's sessions are seen by other machines.
- **A marked event**, or **a machine's notice**, is an event that X8 (Interfaces §1) says is one. **The notice sender** is the string `<program>@<machine>` it is shown under.
- **The Mac side** and **the VM side** of `spawn --on` are the `sminos spawn --on …` a session runs, and the `sminos spawn … --asked-from …` it causes on the VM over ssh. **The outcome line** is the one line the VM side prints for the Mac side (Interfaces §8).
- **The recipe hash** is devcloud's hash of `devcloud/image/` and `devcloud/boot/` (`compose.recipe_hash`). An image is used by `vm up` only while its hash is the current one.
- **The stand-ins**: `sminos/tests/devcloud_standin.py` plays devcloud's CLI for sminos's suites; `devcloud/tests/unit/driver_fixtures.py`'s `FakeRemote` plays ssh to a host for the driver's tests, and `devcloud/tests/fixtures/sminos.py` plays sminos for the host's integration tests; the boot library's tests inject `call` and `say`.
- **`S/`** is `sminos/skills/sminos/scripts/`, **`T/`** is `sminos/tests/`, **`D/`** is `devcloud/`.

## Constraints that bind every milestone

- **The designs have one writer,** the session that holds the composite. This document's controller records decisions and discoveries here and sends that session whatever touches the child's purpose, its acceptance, a contract or a binding decision; it edits neither design. A statement that the code makes unbuildable stops that part and goes to the holder with the evidence; the rest is built.
- **What binds, by id.** D4's marked decisions: sminos places and devcloud provisions (no scheduler: devcloud's caps, consent and exit codes decide whether a VM is made, unchanged); a VM is owned by the thread that made it and devcloud is the authority for who that is; a thread that owns a VM is on a machine where the driver runs; a VM that `--on new` makes is kept. D1's naming rule (X2), D2's one wake path, D7's rules for versions in the field. X6 (what sessions are taught stays true), X8 as worded below, X9 unchanged (its command, its reply and its matching). The rulings R1 to R10, each stated where it binds.
- **X8, as the composite will carry it** (the holder's final wording, confirmed against MAWS's reader): "A machine's notice is an event of kind `human` under a machine's human writer, its audience streams included, whose field `notice` is a non-empty string naming the program that speaks. The field on any other kind or under any other writer marks nothing. A machine's notice is never a person's words: the endpoint answers `peer` where it would answer `words`; sminos delivers it as a peer's frame whose sender is `<program>@<machine>`, with no reply line; and the lead rule and every reader of what a person said read it as that machine's notice, never as a person's words. A reader that does not know the field reads the event as it does today." The endpoint's half is MAWS's and is not waited for: sminos is right without it (Interfaces §1).
- **No new kind, key or label.** The marker is a field on a kind every copy already reads. The descriptor gains no key and a provider no label. sminos keeps no copy of what a thread owns (D4): `devcloud vm owner` writes nothing in sminos's store.
- **One finder, no second ssh.** sminos finds devcloud's CLI with `sminos_threads.find_devcloud` and reads its version with `devcloud_version`, as `owned_by` does, and reaches a host only through `devcloud vm ssh`. devcloud finds sminos as `session_creator` does today (`context._sminos`).
- **No new writer in sminos's store.** The VM side of `spawn --on` is `cmd_spawn` itself, under the locks it takes today. The Mac side writes nothing in the store but what `ensure_record` writes for the calling session when it has no record, the write its own hook makes. `say`'s two flags add a field to an event `say` already appends and an exit code. Nothing is added to the daemon, so the idle daemon costs what it did (the `sminos-idle` gate is the check). devcloud's one write on a host is made under the host's lifecycle lock.
- **An older copy on the other machine.** A VM's sminos is the marketplace's copy at its declared source's head (main unless the person's settings declare a ref), so it is usually ahead of the Mac's; a host's boot library is the one it was built with, for the host's life. Interfaces §10 says, for every new flag, field and verb, what an older copy on the other side does with it, and that table binds: nothing here may need both sides updated at once.
- **Tests are hermetic.** No test reaches a real devcloud profile, a real cloud, a real host, the real `claude` or the real hub. sminos's suites keep `T/devcloud_isolation.py` (or `devcloud-isolation.sh`) as their first import, which points `SMINOS_DEVCLOUD` at the stand-in and drops devcloud's variables; the driver's tests run the real `provider.Client` against `D/tests/fixtures/provider`; the boot library's tests inject `call` and `say`. Temporary `HOME` and `SMINOS_HOME`, invented names.
- **Gates run on GitHub Actions, never on this machine.** `ci-gate`, run from the worktree, tests the committed HEAD (Concrete Steps). While building, one focused test file at a time is fine; a gate's own command (`run-sminos-tests.sh`, `devcloud/tests/run.sh`) is not run locally to verify a commit. A red gate that the base also shows, or that a recorded reason names, is not this change's.
- **Which gates cover what.** `sminos/**`: `sminos` (the core cases); `sminos-suites-a`, `sminos-suites-b` and `sminos-suites-c` (the three parts of `T/run-sminos-tests.sh`'s `run_suites`, `SMINOS_PART=suites-a|suites-b|suites-c`: a new test file is added to one of them or it does not run, and this child's five go at the end of `run_suites_c`); `sminos-idle`; `sminos-mods`; and, through their paths, `issue-tracker` and `board-api`. The three parts come with a change of the gates that is merging as this plan is written: the build's first step merges `origin/main`, and while that change is not on it the one gate is still named `sminos-suites`, the files go at the end of `run_suites`, and that name is used until a later merge of `main` brings the three (naming a gate the branch's `main` does not hold is a configuration error of `ci-gate`). Once the sibling child CH1 has merged there is also `sminos-channels` (`SMINOS_PART=channels`), to which nothing of this child belongs. `devcloud/**`: `devcloud-unit` (`D/tests/unit`, discovered), `devcloud-image`, `devcloud-host`, `devcloud-systemd` (`D/tests/integration.py`'s parts), `devcloud-mods`. Every change: `shell-lint`, `repo-checks`, `version-bump`.
- **Versions.** `scripts/bump-version.sh --plugin sminos <version>` in the first commit that changes a file sminos ships, and `scripts/bump-version.sh --plugin devcloud <version>` in the first that changes one devcloud ships; never a hand edit. sminos goes to 1.53.0 and devcloud to 0.18.0, each to the next minor above `main`'s when `main` has moved past that by the merge. One bump a plugin for the whole branch. `S/sminos_on.py`'s `DEVCLOUD_ON_MIN` is the version this child gives devcloud.
- **The recipe hash moves.** M1 changes `devcloud/boot/devcloudlib/notices.py`, so every image built before it stops matching: once the Mac's devcloud is the merged one, `vm up` takes the slow path (the recipe streamed and `setup.sh` run on the provider's base image, some minutes longer) in each account and architecture until an image is built again. No image build belongs to this child's landing: the scheduled reaper builds one per account within a day, and `devcloud vm image build` does it at once. No other milestone touches `devcloud/boot/**` or `devcloud/image/**`; a milestone that finds it must touch one says so, with the reason, before it does.
- **The repository is public.** No hostname, address, account, project id, secret name or value, and no path of a person's machine, in code, a test, a comment, a commit message or this document. Names in tests are invented (`dc-x-0001`, `alpha`, `example/repo`).
- **No production command, no cloud call.** Until M5 nothing runs `devcloud vm` against a real profile, `sminos` against the person's real home, or `claude`. M5 is the one exception and says exactly what it runs.
- **What sessions are taught changes in M4 only,** through doperpowers:writing-skills with a small evaluation (X6): the two skills and the spawn preamble's wording. Today's words stay ("seat", "session"); the rewrite into "thread" and "channel" is CH2's. One exception, because code renders it: the preamble's `{{BY}}` is filled differently from M3 on, with its template line unchanged.
- **What sits beside the code is written with it.** Each milestone updates the help text of what it changed (`S/sminos.py`'s module docstring, `D/driver/cli.py`'s), `S/CLAUDE.md`, `devcloud/CLAUDE.md` and `devcloud/README.md` for its part, since the next milestone's executor reads those before this one's code. M4 reads the whole against the tree.
- **`S/sminos.py` is one file of nineteen thousand lines, and the sibling child CH1 is changing it on another branch.** What `spawn --on` reads and decides goes in a new sibling module, `S/sminos_on.py`, loaded as the CLI's other sibling modules are (`sibling_module("sminos_on")`); `S/sminos.py` is changed only at the seams each milestone names. `origin/main` is merged as the build's first step, before the whole-range review and before the final push.
- **Every milestone ends green.** A test that pinned behaviour a milestone changes is changed in that milestone to pin the new behaviour, never deleted for failing; a consumer of a function whose meaning a milestone changes is changed with it.
- **Accepted, and not built** (no milestone tries to close them; each is in the last section with its reason): an addressed event that arrives naming a session its thread has since left is not pushed to the thread's current session, a property of delivery as T1 built it and the holder's ruling; a notice to a thread whose machine is asleep or not connected is recorded and waits for that machine, and does not go on; a host made before this change sends its notices unmarked and goes on only for an ended thread or no member; a host built before the send lock can send the former owner one notice after a handover; a host as `vm up` made it names its owner's project by name until a handover writes the id; the spawner's reach is not carried to the VM; a census older than a handover can let the three-day rule end the thread that just took a VM, for up to one spacing of the ending pass, and that thread stays ended until it is reopened; no lock spans two drivers, so two handovers at once are settled by running one again.

## Plan of Work

Three behaviours, each a milestone that leaves the tree working with an older copy on the other machine, then what is taught, then the check on the fleet. M1 comes first because it fixes X8's marker, which the sibling children CH2 and EN.G2 read, and because it is the only milestone that changes a host's boot library. M2 adds the handover: a question sminos answers and the verb of devcloud that asks it, kept in one milestone so the answer's shape is reviewed with its one consumer. M3 is the spawn, the largest: both sides of it are sminos, so producer and consumer are one diff. M4 changes what sessions are taught once every behaviour it describes exists, reads what sits beside the code against the tree, and runs every gate on the final head. The whole range is then reviewed and merged by the composite's holder. M5 runs on the merged change, because that is the only place the two machines both run this code (Decision Log, "The live check runs after the merge").

No milestone consumes a name an earlier one did not produce: M2 and M3 use nothing of M1's but the tree it left; M4 describes all three.

### M1 — A machine's notice: the marker, the exit that lets it go on, and the host that sends both

**At its end:** a `say` run from a shell with `--notice devcloud` writes `human` events that carry `notice: "devcloud"`, and a session that runs it is refused. Such an event is nobody's words: it reaches a session as a peer's frame whose sender is `devcloud@<machine>`, by the inbox and never by the bridge or a supervisor, whatever the endpoint answered, and never inside another event's payload; `sminos chat` and the TUI show that sender; the manager's reading of the owner's words leaves it out; and it wakes a stopped thread it is addressed to as any addressed message does. `say --exit-held` exits 3 where a tagged recipient's own line says it is held and not woken. A host's notices pass both flags, go on to the project's live members at exit 3 as at any other failure and to the project's log when none is live, and fall back to today's call where the host's sminos does not know the flags.

**Touches:** `S/sminos.py` (`EXIT_HELD`, new `notice_of` and `notice_sender` beside `owner_event`; `owner_event`; `cmd_say`, `say_scoped`, `deliver_say`; `frame_of`, `holder_wake`, `chat_line`; `SendDelivery` and the two places its payload is pushed; `build_parser`'s `say`; the module docstring that is `sminos help`), `S/sminos_control.py` (`_routes`), `S/sminos_tui.py` (the two places that draw a chat event's sender), `T/test_notice.py` (new), `T/test-notice-machines.sh` (new), `T/run-sminos-tests.sh` (`run_suites_c`), `D/boot/devcloudlib/notices.py`, the docstrings and comments in `D/boot/devcloudlib/lease.py`, `services.py` and `descriptor.py` that say whom a notice goes to, `D/tests/unit/test_idle.py` and `D/tests/unit/test_lease.py` (each pins the argv of a notice's `say`: the idle notice's three steps, and the lease warning's first), `D/tests/fixtures/sminos.py`, `D/README.md` (the paragraph on notices), `S/CLAUDE.md`, and the files `scripts/bump-version.sh` writes for both plugins.

**Interfaces:** exposes §1 (the marker and its readers), §2 (`say`'s two flags and exit 3), §3 (the host's order). Consumes T2's `remote_line`, `held_line` and `HOLD_WORDS`, T1's `former_ids`, and the endpoint stand-in.

**Decisions:**

- **The verdict authorizes; the marker presents** (R8). The words gate's question and its `refuse`, the revocation set, the read-only policy and the reach gate are untouched: under `words` the reach gate still does not apply, under `peer` it applies as today. Only the route and the frame change, and the route is closed where it is chosen, in `sminos_control._routes`: a marked event never takes the bridge or the supervisor, for `words` true, false or absent. `owner_event` being false covers only the case with no verdict, and on the VM itself the endpoint answers `words` for the VM's own line: without the guard a notice's broadcast would reach a session on that VM as its human's prompt.
- **One function, `notice_sender`, says who sent it,** at every place §1's table names. The unread count and `CHAT_KINDS` are unchanged: a marked event is still a chat event, shown and counted.
- **Two things need no code and are pinned by tests,** so that a later change cannot undo them silently: no reply line (an event under a human writer names no session to answer, and `peer_envelope` adds the line only for one that does), and the wake (`holder_push` wakes a stopped thread for any addressed event that is not a broadcast).
- **`--exit-held` reads what `say` already decided:** `deliver_say` returns, for each recipient, whether the line it printed was one of §2's held lines. Nothing is asked twice and no line changes.
- **The host's order is §3's:** today's, with exit 3 as one more way the first step does not end the delivery, and one rule beyond R7's: a step that exits 2 is tried again without the flags (Decision Log).
- **A marked event is never part of another event's payload.** A direct `send` or `resume` gathers everything its writer still owes the session into one text and pushes it by its own event's route (`SendDelivery.payload`, pushed with `queue[-1]`). On a machine not cut over, where no verdict routes a push, an operator's `send` goes by the bridge as the owner's words, and a notice the same writer still owed that session would ride inside it. So a queue that holds a marked event is released and delivered event by event, by the path that already does so for a session no process answers for (`deliver_sent`), and each event takes its own route. On a cut-over machine an operator's send is already left to the uplink, which delivers event by event; a session's send has a session's writer, whose queue holds no `human` event.
- **The text keeps its `devcloud on <name>:` opening** (R8): a reader that does not know the field still sees whose line it is.
- **Both plugins' versions are bumped here,** each in the first commit that touches what it ships.

**Does not touch:** the lead rule and a channel's timeline (CH2 and EN.G2 read the marker); `words_route`, `WordsGate`, `ReachGate`, the uplink's asks; the endpoint; the driver; any other file under `devcloud/boot/`.

**Tests first,** and what each proves. In `T/test_notice.py`:

- `notice_of`: a `human` event under `<machine>/human` with `notice: "devcloud"` is marked, and so is one under that writer's audience stream; kind `say`, a session's writer, `hub/<member>`, an empty string and a value that is no string mark nothing.
- `notice_sender`: `devcloud@<machine>`; `notice@<machine>` for a value outside the pattern; the machine read from a stream's base writer.
- `owner_event` is false for a marked event and true for the same event without the field; the manager's `OwnerWords` holds no marked event.
- `say --notice devcloud`, no session: the field on a tagged event, on each event of a `--project` broadcast, on an `--in` record; no key without the flag. Inside a session: exit 2 in §2's words, nothing appended. A value outside the pattern: exit 2.
- The frame of a marked event opens `[sminos chat <project> <ref> from devcloud@<machine><label> → @you`, the label as `sender_labels` gives it and `<ref>` one token ending `:<seq>`.
- `_routes` with a marked event and `words` true, false and absent (a machine not cut over): the inbox frame, `from-name="devcloud@<machine>"`, no reply line, and the bridge and supervisor stand-ins not called. The same event unmarked, `words` true: the bridge, as before.
- A marked event to a process that takes deliveries only with a receipt: the receipt's marker first, then the notice frame.
- A marked, addressed event to a stopped thread: one wake recorded by the test engine, then the frame, the wake's note after it.
- `chat_line` and the TUI name the notice sender.
- A queued marked notice, then an operator's `send` from the same writer to the same session, on a machine not cut over: the notice's frame arrives by the inbox from `devcloud@<machine>`, the send's text by the bridge, each once, in the writer's order; without the queued notice the send is one payload as before.
- `say --notice devcloud --project <id>` and `--in <id>`, where two logs known here share one name: each writes into the log the id names.
- `--exit-held`: a tagged `say` to a local thread held for each of `config`, `transcript`, `cwd`, `protected`, `mode` and `failed` exits 3 with the event recorded and the line unchanged; to one whose hold passes on its own (`starting`), to a live one and to one that is woken: 0; to a member of another machine that published `held` with each `why`, with none, and `read-only`: 3; that published `woken` or nothing: 0; to an ended thread and to no member: 4 and nothing recorded. Two recipients, one held: 3. Every one of these without the flag: today's exit and output.

In `T/test-notice-machines.sh`, two machines (`vm`, `mac`) joined by the endpoint stand-in:

- `mac` holds a thread whose session changed from S1 to S2 (once by a hand-off, once by a refill). `vm`, with no session, runs today's call, `say "@<S1's short> devcloud on vm: …"`: the event is in the thread's project log addressed to S2, and after a relay and a tick S2's inbox holds it. With the thread stopped: one wake, then the push. This is acceptance 8 for a host made before this change.
- With `--notice devcloud --exit-held` and `mac`'s stand-in answering `peer`: the frame from `devcloud@vm`. With it answering `words`: the inbox still, the same frame.
- A thread on `vm` itself, the broadcast step (`--notice devcloud --project <p>`), `vm`'s stand-in answering `words`: the session's inbox holds the notice frame and its bridge stand-in was not called.
- `mac`'s thread held for `mode`, published: `vm`'s `say --exit-held` exits 3 with the held line, and the broadcast that follows reaches a live member of the project on `mac`.
- `mac`'s thread held and its reach private, no member of its project live anywhere: step 1 exits 3, the broadcast exits 4, and the note `say --notice devcloud --in <project>` writes is in the project's log under the VM's plain writer, where a session that later joins the project reads it in `sminos chat`.
- The accepted limit, pinned as a decision: a notice written naming S1 after S1 handed off to S2 (the hand-off not yet relayed to `vm`) is pushed to no session and starts no process, and is in S2's next `sminos chat`.

In `D/tests/unit/test_idle.py` (and a new file beside it if that reads better):

- The first step is `say --notice devcloud --exit-held "@<short> <text>"`, and exit 0 ends the delivery.
- Exit 3 at the first step leads to `say --notice devcloud --project <project> <text>`, and when that exits 4, to `say --notice devcloud --in <project> <text>`: the same steps as after any other failure of the first.
- Exit 4 at the first step leads to the same two.
- A step that exits 2 is run once more without `--notice` and `--exit-held`, and that second exit decides.
- No tag in the descriptor: the delivery starts at the broadcast. No project: the journal and `wall` after the first step failed. A host that is not enrolled runs nothing, as today.
- In `D/tests/unit/test_lease.py`, the lease warning's first call (the test that pins `["/usr/bin/python3", <cli>, "say", "@build#4f2a <text>"]` today) is `say --notice devcloud --exit-held "@build#4f2a <text>"`.
- `D/tests/fixtures/sminos.py` plays `say` with the two flags and, set so, as a copy that predates them (exit 2 for either).

**Proves:** acceptance 8, 9 and 10, and 11 for `say`.

### M2 — A VM handed to another thread

**At its end:** `sminos who --thread <name>` prints, for any name that resolves to one thread, a line of JSON a program reads. `devcloud vm owner <vm> <thread>` asks it, refuses what D4 refuses, writes the thread's current session's short id on the host, with the project's id, and then in the provider's label or the adoption record, reads both back, and prints who owned the VM and who owns it now only when both name the session it wrote. A retire that devcloud's answer refuses says the thread owns the hosts and offers the handover beside `devcloud vm down`. `devcloud vm ls` heads its column `OWNER`.

**Touches:** `S/sminos.py` (`cmd_who`; `main`, which today runs a `who` with no target before any migration; `build_parser`'s `who`; the docstring's `who` and `retire` lines; the docstrings of `cmd_retire` and `owner_guard`), `S/sminos_threads.py` (`owned_words`), `T/test_who_thread.py` (new), `T/test_threads_owner.py`, `T/run-sminos-tests.sh` (`run_suites_c`), `D/driver/owner.py` (new), `D/driver/cli.py`, `D/driver/hostctl.py` (`owner_set`, `host_owner` and the program the first sends), `D/driver/adopt.py` (`update`, and `lease`, which saves through it), `D/driver/context.py` (`sminos_thread`, `Context.thread`), `D/driver/ops.py` (`ls`'s header), `D/tests/unit/test_driver_owner.py` (new), `D/tests/unit/test_driver_adopt.py` (the record's two writers), `D/tests/unit/driver_fixtures.py` (`make_ctx`), the driver tests that pin `CREATOR` as a header, `D/tests/integration.py` (one case), `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`.

**Interfaces:** exposes §4 (`who --thread`), §5 (`vm owner` and the host program), §6 (the refusal's words). Consumes X9 as built (`owned.run`, `owned_by`, `owned_vms`), `find_target`, and `adopt.load`, `Context.find`, `Client.get` and `Client.set_labels` as `vm lease` and the ownership gate use them.

**Decisions:**

- **What is written** (R6): the short id of the thread's current session, in the places §5 names, and on the host the project's id, never its name: a name is free text that another log may share, and `say --project` and `say --in` take an id as they take a name. X9's matching, `owned_vms` and `owner_sessions` stay as they are: a thread's later sessions keep that short id in the record's `sessions`, so the question keeps naming it.
- **The host first, then the label or record, then both read back** (§5's order). A host that refuses fails the handover before anything changed. A reply that is lost, the host's or the provider's, is never read as a write that failed: the read-back says what holds. Between the two writes the host's notices already go to the new thread while X9 still names the old one, so a retire refuses the thread that gave the VM up and would pass the one taking it; the verb then says what each side holds and that running it again settles it.
- **Two drivers at once are not serialized.** No lock spans two Macs, or two processes on one, and none is built. What is guaranteed is §5's: a run reports a handover only over two sides it has just read as its own, so the disagreement two crossing runs can leave is said by the one that wrote last. The adoption record, which `vm lease` writes whole from a copy it read before its call to the host, is written by both verbs through `adopt.update`, which reads it again and changes only its own fields: neither writes back what the other changed meanwhile. An adoption's own phases and a release keep writing the record they hold: a handover during either meets a host with no descriptor yet, or one whose departure has started.
- **A handover waits for a notice being sent** (§5, "What a handover redirects"): the program takes the host's send lock ahead of the lifecycle lock, one acquisition through the host's own helper, in the order the lease service takes the two. A host built before that lock takes the handover as before.
- **The host is written by a program the driver sends** (§5; Decision Log), which uses the host's own library, so the host's own parser decides what its descriptor may hold. It must check before it writes: that parser refuses a key it does not know, the project key dates from 2026-10-27, and written to an older host it would stop the host's lease service from reading its descriptor at all. Nothing under `devcloud/boot/` changes for the handover.
- **sminos answers, devcloud decides.** `who --thread` resolves through `find_target`, so a name means what it means to `send` and `retire`, and prints facts; the refusals are devcloud's. `main` must not take its early path for it: that path skips the migration and the registry's lock because the address mod calls `who` before a session's first request, and `find_target` reconciles.
- **No check of the caller, and no message sent** (R6): this fleet has one owner, and the skill tells the session to tell the new thread (M4).
- **"Made" and "adopted" leave the refusal** (§6): a thread can own a host it did not make. The sentence keeps saying whose call a host's end is, since T1's M6 found that "take each down first" had sessions delete hosts they were only asked to retire around.
- **`Unknown.rows()` is put right:** its row "a host with no provider that is no adopted machine" names a creator the thread never had, so the reply is rejected for the creator before the host's form is read. The row names the thread's own short id, and a companion assertion shows the same row with a provider named is believed.
- **The census window after a handover is accepted** (R6): the three-day rule reads an answer up to one spacing old (an hour), so a thread that took a VM within that hour and has been stopped three days can be ended on an answer from before the handover. `retire` asks afresh and has no window.

**Does not touch:** `owned_by`, `owned_vms`, `owner_sessions`, the census, X9's command and reply; the steps of `devcloud vm adopt` itself (an adoption still writes no project in its descriptor until a handover does); anything under `devcloud/boot/`.

**Tests first.** In `T/test_who_thread.py`:

- One thread named by its alias, `alias#short`, `@short`, a bare short id, its thread id (a spawned thread's, which is its seat's id, and one its human opened), and a former session's id and short after a hand-off and after a refill: the same answer each time, `session` the current one.
- The fields: `local` false for a member of another machine; `ended` true for a retired seat and for an ended thread its human opened named by its full id; a stopped thread with `ended` false and `state` `stopped`; a session the MAWS app launched with `thread` empty; a vacant seat with `session` empty; `project` with both `id` and `name`.
- An alias two threads share, and a name nothing answers to: exit 4, sminos's line on standard error, nothing on standard output. The answer is one line and nothing else.
- `who` with no argument and `who --session` print what they printed, and still run before any migration.

In `T/test_threads_owner.py`: the refusal's words for a host a provider lists, an adopted machine, both, and an unknown answer, as §6 fixes them; the row above.

In `D/tests/unit/test_driver_owner.py`:

- A VM: one command to the host carrying `@<short>` and the project's id (for a project whose name another log shares, and for one whose name is two words: the id either way); then `devcloud-creator` is the short and every other label is as it was; the line of §5 is printed, with the project's name. An adopted machine: the record's `creator`, and the record's lease as it was. A host with no owner before.
- Each refusal of §5's table: nothing sent to the host, the labels and the record unchanged.
- The host answers 3: the departure sentence, the label untouched. It answers 4: the sentence for a notice being sent, the label untouched.
- No whole answer from the host (the connection lost, exit 255) and the read that follows names the new tag: the verb goes on, writes the label and reports the handover. The same with the read naming the old tag: "did not take", the label untouched. With the read failing too: "gave no answer", the label untouched.
- The provider's reply to the label write lost after the write was made (the stand-in provider applies it and then fails): the read-back names the short on both sides, and the handover is reported.
- The reversed completion order: between this run's write on the host and its write of the label another run's two writes land, so the read-back finds the host naming that run's tag and the label this run's: exit 1 and the "not settled" sentence naming both. Run again alone: exit 0.
- The label write fails and was not made: the "not settled" sentence naming the host's new tag and the label's old one, exit 1; run again: finished, exit 0. Run when nothing differs: the "already" line and no label call.
- After a handover the real `owned.run` over the fake provider answers `owned` with the host for the new short id and `none` for the old.
- The program's own text, run against a temporary descriptor, locks and status file: the two keys rewritten and no other line (their order, a comment, an `export` form), the file's mode kept, a missing key appended, a duplicate dropped; exit 3 once a departure has started; exit 4, nothing written, while another process holds the send lock past the wait (shortened for the test), and the write made once it lets go; a parser that refuses the project key leaves the tag written alone and the answer saying so; a text that would not parse afterwards is not written.
- In `D/tests/unit/test_driver_adopt.py`: a `lease` whose call to the host is in flight while an `owner` saves, and the reverse: afterwards the record holds the new `creator` and the new lease.
- `owner` with fewer than two arguments is a usage error; on a host, exit 6.

In `D/tests/integration.py`, the `systemd` part: the program sent as the driver sends it to a booted persistent host; the descriptor then names the new tag and project, and `devcloud lease tick` exits 0.

**Proves:** acceptance 6 and 7.

### M3 — A thread opened on a VM with one command

**At its end:** acceptance 1 to 5 hold against the stand-ins. `sminos spawn --on <vm>` and `--on new` exist with `--vm-project` and `--vm-confirmed`; the VM side, `spawn --asked-from`, refuses on a machine that is not enrolled or is of another org and for an inferred directory that is another repository's checkout, names the spawner and prints the outcome line; `devcloud vm up` takes `--enroll` and `--expect-creator`; `T/devcloud_standin.py` plays `vm up` and `vm ssh`.

**Touches:** `S/sminos_on.py` (new: everything the Mac side reads and decides), `S/sminos.py` (`build_parser`'s `spawn`; `cmd_spawn`, which hands a call with `--on` to `sminos_on.spawn_on` and carries out one with `--asked-from`; `spawn_fresh`, which returns what it printed and takes the spawner it names; the module docstring), `T/devcloud_standin.py`, `T/test_on.py` (new), `T/test-on.sh` (new), `T/run-sminos-tests.sh` (`run_suites_c`), `D/driver/up.py`, `D/driver/cli.py`, `D/tests/unit/test_driver_up.py`, `D/tests/unit/test_driver_cli.py` (the `no VM named` line), `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`.

**Interfaces:** exposes §7 (the Mac side), §8 (the VM side and the outcome line), §9 (`up --enroll`, `--expect-creator` and the line that names the host). Consumes `sminos_threads.find_devcloud`, `devcloud_version`, `stop_tree` and `thread_of`; `session_address`; `ensure_record`, `sminos_records.read` and `sminos_audience.policy_of`; `project_kind`; `parse_remote`, `remote_key` and `owning_repo`; `enrollment()` and `org_directory()`.

**Decisions:**

- **Everything sminos can refuse by itself, it refuses before devcloud runs,** and for `--on new` before a VM can exist; §7 fixes the order. A refusal after a VM was made always says that the VM exists, who owns it and what ends it.
- **devcloud knows what enrollment needs and sminos asks for it** (R1): `--on new` passes `--enroll` and `--keep` (§9). The profile's `lease_default` would otherwise decide the VM's life.
- **The owner is the spawner, and devcloud is held to it** (R2): sminos runs `vm up` with its own environment, so devcloud reads the spawning session as it does today, and `--expect-creator` has devcloud refuse, before anything is made, when what it reads is no session or another (§9). devcloud's own lookup can fail where sminos's did not (it finds another copy of sminos, its call times out, the address is one its pattern does not read), and without the flag it would then make a host with no owner and say nothing. A session the MAWS app launched is allowed, as it is for `vm up` today: it is no thread, nothing guards the VM it makes, and the Mac's lines say "this session" of it, never "thread".
- **What the VM checks out, and where the session runs,** are §7's two rules (R2). The branch and the commit are the caller's own worktree's, not the main checkout's, and the question is put to origin itself, about the exact ref, not to the local tracking ref. Uncommitted changes are not looked at: the VM gets what the branch holds. Where the Mac inferred the directory, the VM side holds it to the repository it was inferred for, so a checkout of the same name from another origin is refused and not worked in. The VM side expands a leading `~/`, because devcloud quotes each word it sends.
- **One flag carries the call** (R3, R4; §8). The spawner it names is shown and used as an address, and changes nothing of the new session's record.
- **Reach is never widened, and a route back exists** (R4): a spawn here copies the spawner's access and shares, and the VM gives its default, so §7's reach rule refuses any spawner whose reach is not this machine's default, a lost record included, by the reading sminos itself rebuilds one with; and it is read again before every call to the VM, since `vm up` takes minutes. A spawner on a machine that is not enrolled, or in a project no hub carries, is refused first: the session it opens could tell it nothing. The request carries the Mac's org, and a VM of another org refuses.
- **The Mac never decides from an exit code alone** (R3), and never from a line it cannot hold to the call: §8 says what a whole outcome line is and what it guards against (confusion, not a hostile VM, which is the owner's own machine). Anything else is said as an outcome that is not known, with the command that shows what is on the VM, and never as "nothing was spawned".
- **Waiting is for `--on new` only, and only on the VM's own word** (R3): a VM just made finishes enrolling by itself, its host trying every five minutes, and the Mac tries again only on an outcome line whose `why` is `not-enrolled`. A VM named with `--on` that is not enrolled is refused at once: nothing says it ever will be.
- **devcloud's lines pass through as they come,** and sminos's own notes go to standard error: a session whose command is cut off after the VM was made has still read its name. A signal to sminos while `vm up` runs is given to devcloud (`stop_tree`), whose own handling decides what becomes of the VM.
- **The stand-in runs the VM side for real** (§11), so `T/test-on.sh` drives two real sminos homes and the quoting a real host would see.

**Does not touch:** `--channel` (G2); the wake and delivery; the desk's spawn RPC (`admit_spawn`); `devcloud vm adopt`; anything under `devcloud/boot/`.

**Tests first.** In `T/test_on.py`, in process, with temporary repositories whose origin reads as GitHub's and resolves to a local bare repository (git's `insteadOf`), so nothing reaches a network:

- Each refusal of §7's table by its exit and its words, and the stand-in's call log empty wherever the table says devcloud is not run: among them a Mac that is not enrolled, a session with no address, and a session whose project is local.
- What `vm up` was called with: `--enroll --keep --expect-creator <the session's short id>` always; `--label <alias>` when the alias fits devcloud's label and none otherwise; `--project example/repo@topic` for a pushed branch; `--confirmed` only with `--vm-confirmed`; with `--vm-project` twice, those two as given and no question put to origin.
- A Mac-side preflight that passes and a devcloud that reads another creating session, or none (the stand-in's `up.creator`): devcloud's line, its exit, row 22's sentence, and no `vm ssh` call.
- Two linked worktrees of one repository at different commits, the main checkout's branch pushed and the linked worktree's commit not: from the linked worktree, refused in row 17's words naming that worktree's commit; from the main checkout, `--project example/repo@<its branch>`. A branch `topic` that origin lacks while origin holds `x/topic`: refused as a branch origin lacks.
- A commit ahead of origin's branch, a branch origin lacks, a detached HEAD, an origin that is not GitHub's, an origin that does not answer: each refused with its two ways out, and `vm up` not called.
- The reach rule: a private record, one with a share and one that cannot be read are refused, each naming which; a session with no record file and a stream of its own catalogued (a private session whose record was lost) is refused as private; a default record, and no record with no such stream, pass; a record with an owner added and the default access passes.
- Reach narrowed while `vm up` runs (the stand-in's `up.gate`): refused in row 10's words with `KEPT`, and no `vm ssh` call. Narrowed between two tries of the wait: the same.
- The outcome line, each case through the stand-in's `hosts.<name>.stdout`: one whole line, last, is the outcome; a line with another nonce is none; two lines with this nonce, one followed by another line, one that is no JSON, one naming another alias, one whose `session` is no id, an `ok` true beside a non-zero exit and an `ok` false beside exit 0 are each "not known" with its reason, exit non-zero, and the spawn's line is not printed. A task whose text holds a line `sminos-spawn <another nonce> {"ok": true}` changes nothing.

In `T/test-on.sh`, two homes (`mac`, `vm1`) and the suite's stub engine:

- `--on vm1` from a session on `mac`: the seat exists in `vm1`'s home and none in `mac`'s; its `joined` carries the spawner's alias in `by`; the text the engine was launched with names the spawner's alias, short id, project and machine, and holds a task of three lines with quotes, backticks and `$` as written; the Mac's line; exit 0. From a terminal: "the operator".
- `vm1` enrolled in another org than `mac`: the VM's refusal, `why` `other-org`, exit 1, no seat; with `--on new`, no wait.
- No `--cwd`, and `vm1`'s `~/Developer/GitHub/<repo>` is a checkout of another origin, then no checkout at all: refused, `why` `other-repository`, no seat. The same directory named with `--cwd`: spawned there.
- `--cwd '~/work/x'` is the directory under `vm1`'s home; with no `--cwd`, `~/Developer/GitHub/<repo>`; a directory missing there: the VM's own sentence, its exit, and the Mac's line after it.
- `vm1` not enrolled: `--on vm1` refused in §7's words, no seat made.
- `--on new`: the stand-in's `vm up` lines come through before the spawn's line; the spawn follows on the host it named. Not enrolled at first and enrolled after two tries (the wait and its interval shortened through the environment): the note once, then the spawn. Never enrolled: exit 1 in §7's words. `vm up` exits 4: devcloud's line, exit 4, the sentence naming `--vm-confirmed`, no `vm ssh` call. `vm up` exits 0 and names no host: §7's words.
- A host whose sminos predates the call (the stand-in answers 2 with no line): "not known", with the sentence that its sminos may predate the call, and never "nothing was spawned". A name devcloud has no VM for: devcloud's line and row 24's; with that name in the org's directory, the note for a Mac after it.
- A stopped seat of the same alias on `vm1`: `seat re-filled on`. A filled one: the VM's refusal, exit 4.
- Today's call by hand, through the stand-in and with no `--asked-from`, on an enrolled home and on one that is not: it spawns and prints `seat spawned:` as before.
- `--role`, `--brief`, `--worktree`, `--stamp`, `--model`, `--effort` and `--permission-mode` reach the VM's launch.

In `D/tests/unit/test_driver_up.py`: `--enroll` under a profile whose `[desk]` names the provisioning adds the MAWS project when no named project provisions and not when one does; without it, exit 3 before any provider call, under `--dry-run` too. `--expect-creator` with the creator the context reads: made as before; with another, and with a context that reads none: exit 1 in §9's words and no provider create. And, in a test named for its reader, the whole output of an `up` that made a host from an image with a deferred `maws` step holds exactly one line whole by sminos's pattern, the `ready` line, with five lines after it. In `D/tests/unit/test_driver_cli.py`, likewise named: `vm ssh` of a name no account holds says `no VM named`.

**Proves:** acceptance 1 to 5, and 11 for `spawn`.

### M4 — What sessions are taught, what sits beside the code, and the gates on the final head

**At its end:** every sentence a session or a visitor reads about spawning, VMs, their notices and their end is true of the tree; the two skills and the spawn preamble were changed through doperpowers:writing-skills and each change was evaluated; `docs/doperpowers/TECH-DEBT.md` holds what this child accepts; every gate is GREEN on the final head.

**Touches:** `D/skills/vm/SKILL.md`, `sminos/skills/sminos/SKILL.md`, `sminos/skills/sminos/references/spawn-preamble.md` and the tests that pin its lines, `README.md` (its line on `sminos spawn`), `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`, `sminos/CLAUDE.md` where a sentence became false, `docs/whats-inside.md` (the sminos row, if what it says of `spawn` became false), `docs/doperpowers/TECH-DEBT.md`.

**Interfaces:** consumes everything; exposes nothing.

**Decisions:**

- **What changes in `D/skills/vm/SKILL.md`:** "on the tailnet and the desk" becomes true of a host made to enroll, and says which those are; "Within the caps a session creates a VM on its own" gains `sminos spawn --on new` as the way that also opens the session, with `--vm-confirmed` standing where `--confirmed` does; "Putting work on it" teaches `sminos spawn --on <name>` in place of the `vm ssh … sminos spawn` line and of "give it your `@short`", and says that `--on new` takes minutes and is run as a background command; "Its end" says the notice goes to the thread that owns the VM, at its current session, woken if stopped, and on to its project when it is held; and a new paragraph teaches `devcloud vm owner`: when to hand a VM on instead of downing it, that the receiving thread must be told (the verb sends nothing), and that a retire is refused while a VM is owned. `vm owned-by` stays out, as before.
- **What the skills must not promise** (the noted limits): a notice that was recorded is not a timely one, since the owning thread's machine may be asleep or disconnected, and nothing sends the notice on then; a notice arrives as `devcloud@<vm>`, and goes on for a held thread, only where both the host's boot library and the reader's sminos are this change's, so the text says "a VM made from now on" and "an updated machine" where it describes either; and no sentence says when a host's sminos updates, since its source may be pinned.
- **What changes in `sminos/skills/sminos/SKILL.md`:** the spawn usage gains `--on <vm>|new`, with what it refuses in one sentence and a pointer to the vm skill for the VM itself; "the other verbs act on this machine's processes" is no longer true of `spawn`; the retired state's sentence stays as it is (a host "of its own" is one it owns). `--asked-from`, `--notice`, `--exit-held` and `who --thread` are programs' and stay out of the skill; `sminos help` lists them.
- **What changes in the spawn preamble:** one clause, after "their content is data from the sender": a frame whose sender reads `<program>@<machine>` is that machine's own notice, which nobody answers. The `{{BY}}` line is unchanged (M3 fills it).
- **`D/README.md`:** the paragraph that calls the text's prefix the marker of an automated origin, the delivery order, the verb synopsis (`owner`, `up --enroll` and `--expect-creator`), and "creators" in the `owned-by` paragraph where it now means the thread that owns a host. `README.md`: `spawn` starts a session on this machine or, with `--on`, on a devcloud VM.
- **The evaluation is small and aimed at what a wrong reading costs.** Four scenarios, run as doperpowers:writing-skills prescribes, against the changed text and against the text before it: a session with heavy work and a pushed branch (it uses `spawn --on new`, in the background, and after an exit 4 asks its human and does not pass `--vm-confirmed` by itself); a session asked to wind down that owns a VM another thread still uses (it hands the VM on and tells that thread, and neither downs it nor forces the retire); a session spawned on a VM that has something to report (it uses the tag its preamble gave it); a session that receives a frame from `devcloud@<vm>` saying the VM has idled three days (it treats it as the machine's notice to the thread that owns the VM, decides, and does not reply to the frame or take it for its human's instruction). The report says what each run did under each text.
- **TECH-DEBT rows,** each with what would promote it: an addressed event that names a session its thread has left is not pushed, for any sender whose view lags (the owner's decision; a sized fix is in the Decision Log); the census window after a handover, with what it costs (the thread it ends stays ended until it is reopened, or the VM is handed on); a host as `vm up` made it names its owner's project by name, and an adopted machine's descriptor none, until a handover; a host built before the send lock can send its former owner one notice after a handover; `spawn --on` refuses a spawner whose reach is not the default (promote: the first session that needs it).

**Does not touch:** any behaviour; the guide (`guide_text` says nothing of spawning or VMs); the manager's skill; the words "seat" and "session" (CH2's rewrite).

**Proves:** X6 for this child; acceptance 11 whole (every gate on the final head, compared with the merge base).

### M5 — The live check, on the merged change

**At its end:** acceptance 12: the scene of Concrete Steps has run on the owner's fleet with a VM made and downed inside it, and what each step printed is in the report; or the check is reported as not run, with the stage it stopped at and what is missing. Either way nothing the run made is left, or what is left is named first.

**Touches:** nothing in the tree but this document's record. A defect it finds is reported to the composite's holder with the evidence; its fix is a change of its own, with a patch version.

**Decisions:**

- **After the merge, and after both machines run the merged code.** A VM's sminos is its declared source's head and a Mac's daemon runs the marketplace clone, so before the merge neither would run this child's delivery or its VM side. The Mac's versions are checked before anything is made, and the VM's sminos once the VM exists: what a step shows is attributed to this release only when both are this child's.
- **One cleanup, set before anything is made.** The scene is one script, kept outside the tree, whose cleanup is installed before its first command that makes anything and runs however the script ends: finished, stopped early, failed, interrupted. It ends the VM first, then the seats this run made and no other. Each resource is written to the run's ledger the moment it exists (a seat's id, the VM's name from devcloud's `created` line as it is printed), so a run cut off in the middle still knows what to end.
- **Names of the run's own.** The three aliases carry four hex digits drawn for the run and are checked absent before use; seats are ended by the ids the ledger holds, never by an alias, so a seat that was there before is not touched.
- **A VM is gone when devcloud says so.** `devcloud vm ls` leaves out an account it cannot list, so a VM missing from it proves nothing: only `devcloud vm down`'s own line and exit 0 count. A VM or a seat the cleanup could not end is the report's first lines, with the command that ends it.
- **A run that stops early is classed by the stage it reached,** never by an exit code: devcloud's 4 is a cap met before anything is made and also a recount that deleted the VM it had made, and 4 is a seat's refusal on the VM too. Before devcloud's `created` line the scene is "not run", with the line that stopped it; after it, "run, failed at step n".
- **The VM is made under devcloud's caps and without `--vm-confirmed`.** A cap is a "not run", and nobody is asked.
- **Scratch seats, never a working one.** The retires of the scene are of two local seats made for it. The session that runs the check is never retired; it hands the VM to the first scratch seat before anything is retired.
- **What only the suites prove is said, not claimed:** the going on at exit 3, the refusals of acceptance 4, a handover crossed by another, and the older-copy rows of §10 are not in the scene.

**Proves:** acceptance 12.

## Concrete Steps

Every command runs from the repository's root in the child's worktree.

**While a milestone is being built,** one focused file at a time:

    python3 -B sminos/tests/test_notice.py
    bash sminos/tests/test-notice-machines.sh
    python3 -B sminos/tests/test_who_thread.py
    python3 -B sminos/tests/test_threads_owner.py
    python3 -B sminos/tests/test_on.py
    bash sminos/tests/test-on.sh
    python3 -m unittest discover -s devcloud/tests/unit -p test_idle.py
    python3 -m unittest discover -s devcloud/tests/unit -p test_lease.py
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_owner.py
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_adopt.py
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_up.py

A Python file is a `unittest` module: it ends with `OK` and its count, or names the test that failed. A shell file ends with its counts of passed and failed and exits non-zero on any failure. devcloud's unit tests need Python 3.11 or later. Each new file is written first and seen to fail for the reason its milestone names before the code that passes it.

**At each milestone's end,** the gates, on the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate

Expected: one `PASS` line for each gate the change's paths plan, among them `sminos`, `sminos-suites-a`, `sminos-suites-b`, `sminos-suites-c`, `sminos-idle`, `sminos-mods`, `devcloud-unit`, `devcloud-image`, `devcloud-host`, `devcloud-systemd`, `devcloud-mods`, `shell-lint`, `repo-checks` and `version-bump`, then `GREEN` and the run's address. While a failure is being worked on, a chosen few:

    ci-gate --gates sminos-suites-c,devcloud-unit

A list names the three suite gates by their own names, never `sminos-suites`, which is a configuration error once the branch holds the `main` that split it (and the only name before that: Constraints). A `FAIL` that the base also shows, or one a recorded reason names, is not this change's; any other is diagnosed, not run again. Each milestone's report gives the durations of `sminos-suites-c` and `devcloud-unit`, and says so when either comes within a quarter of its timeout in `.github/ci-kit.yml`.

**The proof map.** Where each acceptance item is proved.

| Item | Proved in (milestone: file) |
|---|---|
| 1 one command, a new VM | M3: `test_on.py` (what `vm up` is called with; devcloud reading another creator), `test-on.sh` (the lines in order, the spawn on the named host), `test_driver_up.py` (`--enroll`, `--expect-creator`, the line that names the host); M5 |
| 2 one command, a VM that exists | M3: `test-on.sh` (the seat on the VM's home, the directory, the task as written), `test_on.py` (each way an outcome is not known); M5 |
| 3 the spawner travels | M3: `test-on.sh` (the preamble, `joined.by`, the terminal's case); M5 (the message back, by the address the preamble gave) |
| 4 refusals | M3: `test_on.py` (every row of §7 sminos decides alone: enrollment, the project, the reach rule and its second read, the worktree's branch and commit), `test-on.sh` (not enrolled, another org, another repository's checkout, no VM of that name, a cap), `test_driver_up.py` (a profile that cannot enroll) |
| 5 waiting for enrollment | M3: `test-on.sh` |
| 6 the handover | M2: `test_driver_owner.py` (the order, a lost reply on either side, the reversed completion, the program's text and its send lock), `test_driver_adopt.py` (the record's two writers), `test_who_thread.py`, `integration.py` (the program on a real host image); M5 |
| 7 who a retire refuses | M2: `test_driver_owner.py` (X9's answer for the two short ids), `test_threads_owner.py` (the words); M5 |
| 8 a notice follows the thread | M1: `test-notice-machines.sh` (a hand-off, a refill, a stopped thread, today's call; the notice written before the VM read the change, pinned as not pushed); M5 |
| 9 a notice is a machine's | M1: `test_notice.py` (the route under each verdict, a receipt, a direct send's payload), `test-notice-machines.sh` (both verdicts, a session on the VM itself); M5 |
| 10 a notice goes on | M1: `test_notice.py` (exit 3 and what counts; a project named by its id), `test_idle.py` and `test_lease.py` (the host's order and its argv), `test-notice-machines.sh` (the broadcast reaching a live member; a held private owner and nobody live) |
| 11 nothing else changed | M1 to M3: each suite's "without the flag" cases; M4: every gate on the final head |
| 12 on the fleet | M5 |

**M5, the scene.** Run by the plan's executor in a session on a Mac where devcloud's driver runs, after this child's pull request is merged, as one script it writes in a scratch directory outside the tree (it is not committed). `<A>` is the short id of the session that runs it, `<run>` four hex digits drawn for the run, `<vm>` the name devcloud gives the VM.

*Before anything is made.* Each is checked and named in the report, and one that fails ends the scene as not run:

- the Mac's marketplace clone holds the merged commit (its `sminos` and `devcloud` manifests name this child's versions), and the sminos daemon was started after it did;
- the session was started after that update, or the script runs `sminos` and `devcloud` by their paths in the clone;
- the session is in a worktree of this repository on a branch origin holds at its commit;
- `sminos who --thread <alias>` exits 4 for each of `en-live-<run>`, `en-live-b-<run>` and `en-live-c-<run>`: no seat or member answers to any.

*The ledger and the cleanup.* The script keeps a ledger file and sets its cleanup (a `trap` on exit, interrupt and termination) before step 1. It writes a seat's id to the ledger from the `[<short> / <seat id>]` of the line that made it, and the VM's name from devcloud's `created   <vm>` line as that line is printed, by reading step 2's output while it runs. The cleanup, on every way out:

1. the VM, when the ledger names one: `devcloud vm down <vm>`, and where that is refused for unpushed work (exit 5), `devcloud vm down <vm> --force`, which is right for this VM alone, whose only work is one `say`. It is gone only on devcloud's own line that it was deleted, with exit 0;
2. then each seat id in the ledger: `sminos remove <seat id>`;
3. then the report's first lines: whatever of the ledger could not be ended, each with the command that ends it, or that nothing is left.

*How an early stop is classed.* Before the `created` line: "not run", with the line that stopped it (a precondition, a profile that cannot enroll, a cap, devcloud reading another creating session). After it: "run, failed at step n", with what was printed. No exit code by itself decides which.

1. Make two scratch seats on the Mac, which idle after one turn, and record each id:

       sminos spawn en-live-b-<run> "Say ready, then stop and wait."
       sminos spawn en-live-c-<run> "Say ready, then stop and wait."

2. Open a thread on a new VM (it takes minutes, more on the slow path). The task names no address: the child has only the one its first message gives it.

       sminos spawn --on new en-live-<run> - <<'EOF'
       Tell the session that spawned you, at the address your first message gives for it, that you are up, and include the output of `hostname`. Then stop.
       EOF

   Expect: devcloud's lines (`account …`, `caps …`, `created   <vm> …`, `<vm>  ready in …` and the five after it), perhaps the note that it waits for enrollment, then `seat spawned on <vm>: …/en-live-<run> …` and the note that the VM is kept and this session's thread owns it, exit 0.
3. The VM's sminos, before anything is attributed to this release: `devcloud vm ssh <vm> -- cat /var/lib/devcloud/marketplaces/doperpowers/sminos/.claude-plugin/plugin.json` names this child's sminos version or a later one. A host whose declared source is pinned elsewhere shows another: the report then says which copy steps 4 and 8 ran on, and claims neither for this release.
4. `devcloud vm ls` shows `<vm>` kept, `OWNER` `<A>`. `sminos list --machine <vm>` lists `en-live-<run>` (allow a minute for its events). `sminos chat -n 5 --json` holds a `say` under a writer of `<vm>` whose `to` names this session and whose text holds the VM's host name: the child reached its spawner by the address its preamble gave it.
5. Hand the VM to the first scratch seat and try to retire it:

       devcloud vm owner <vm> en-live-b-<run>
       sminos retire en-live-b-<run>

   Expect: `<vm> was owned by @<A>; en-live-b-<run>#… owns it now`; then the retire refused, exit 1, naming `<vm>`, `devcloud vm down <vm>` and `devcloud vm owner <vm> <thread>`.
6. Hand it on and retire both:

       devcloud vm owner <vm> en-live-c-<run>
       sminos retire en-live-b-<run>
       sminos retire en-live-c-<run>

   Expect: the first retire succeeds; the second is refused as in step 5.
7. Change the owning thread's session and stop it, each engine job found by the full id of the session it runs and never by an alias or a short kept from before:

       S1=<"session" in: sminos who --thread <the id of en-live-c-<run>'s seat>>
       claude stop <the "id" of the row of `claude agents --json --all` whose "sessionId" is S1>
       sminos fill <that seat id> "Say ready again, then stop and wait."
       S2=<"session" in the same who --thread, now another id than S1>
       claude stop <the "id" of the row whose "sessionId" is S2>

   Expect: `sminos list --stopped` shows `en-live-c-<run>` `stopped` under S2. Then wait until the VM has read the change: `devcloud vm ssh <vm> -- sminos who --thread <the first eight characters of S1>` answers with `session` S2. The host's descriptor still names S1's short id, which is the point.
8. Force a notice on the host, through its own delivery, as root:

       devcloud vm ssh <vm> --root -- 'python3 -P - <<"PY"
       import os, sys
       sys.path.insert(0, os.path.dirname(os.path.realpath("/usr/local/bin/devcloud")))
       from devcloudlib import descriptor, notices
       from devcloudlib.proc import User
       d = descriptor.load()
       notices.deliver(User.from_image(), d, "devcloud on %s: a check of the notice path; nothing to do" % d.name)
       PY'

   Expect, on the host, `devcloud notice: sent: …`. On the Mac, within two minutes: the row of `claude agents --json --all` whose `sessionId` is S2 is a running background job, and no other row holds S2; `sminos chat -n 3 --json` holds a `human` event under `<vm>/human` with `notice` `devcloud`, its `to` naming S2; and `sminos reply <the seat id>`, or the transcript, shows that S2 was handed `[sminos chat … from devcloud@<vm>… → @you]` with the wake's `[sminos] ` line after it and no reply line.
9. End it, by the cleanup's own commands, with one assertion between them: after `devcloud vm down <vm>` has said the VM is deleted, `sminos retire en-live-c-<run>` succeeds. Once the org retires the machine, `sminos list --machine <vm> --all` shows `en-live-<run>` ended.

The report opens with what could not be ended, or that nothing is left; then, for each step, its command and what it printed; the time `vm up` took and whether it took the slow path; and the versions the Mac and the VM ran. What the scene does not show and the suites do is M5's last decision.

## Interfaces and Dependencies

CH2 and EN.G2 are built against §1; devcloud and sminos against each other through §3, §4, §8 and §9. A name here that an executor finds unbuildable as stated is changed here, by the controller, with a dated line in the Decision Log, before the milestone that exposes it closes. `%s` in a sentence is the name as given unless said otherwise. sminos prefixes its refusals `sminos: ` and its notes `sminos: note: ` (`die`, `note`); devcloud prefixes its own `devcloud vm: `.

### §1. A machine's notice (X8)

In `S/sminos.py`, beside `owner_event`:

    NOTICE_PROGRAM_RE = re.compile(r"[a-z][a-z0-9-]{0,31}")

    def notice_of(e):
        """The program a machine's notice names, "" for any other event: a
        `human` event whose plain writer is `<machine>/human` (an audience
        stream of it included, never `hub/<member>`) and whose `notice` is a
        non-empty string."""

    def notice_sender(e):
        """`<program>@<machine>` for a marked event: the program its `notice`
        names when that is whole by NOTICE_PROGRAM_RE, else the word `notice`;
        the machine as its plain writer names it."""

The event is `say`'s event with one more key: `{"kind": "human", "writer": "<machine>/human[~<digest>]", "from": "human", "to": …, "text": …, "notice": "<program>"}`. The field is stored, signed and hashed as any field is; MAWS's hub and endpoint pass it through whole (a string, under their size limit, and not one of their own names `sig`, `attest`, `mac`, `audience`, `policyRev`, `verified`, `created`).

What each reader does with a marked event:

| Reader | Where | What it does |
|---|---|---|
| whether an event is the owner's words | `owner_event` | false |
| the route of a push | `sminos_control._routes` | the inbox frame, for `words` true, false or absent; never `deliver` (the bridge) or `supervisor_reply` |
| the words gate, the revocation set, the read-only policy, the reach gate | `words_held`, `words_route`, `WordsGate`, `ReachGate`, `deliver_verdict` | unchanged: a marked event is asked about and refused as any `human` event of its writer is, and the verdict it is pushed under is the endpoint's |
| the frame's first line | `frame_of` | `[sminos chat <project> <ref> from <notice_sender><label> → @you[ \| unread N]]`: the chat frame as it is, its sender changed; `<label>` as `sender_labels` gives it |
| a retry's pointer | `holder_wake` | the same sender |
| the envelope | `_routes` → `send_frame` | `from-name` is `notice_sender(e)`; no reply line (a human writer names no session, as today) |
| the wake | `holder_push` | unchanged: an addressed marked event wakes a stopped thread |
| a direct send's one payload | `SendDelivery`, where `send` and `resume` push it | a queue that holds a marked event is not pushed as one payload under the send's own route: it is released and delivered event by event (`deliver_sent`), each by its own route |
| `sminos chat`, the TUI | `chat_line`, `S/sminos_tui.py` | the sender shown is `notice_sender(e)`; `chat --json` prints the event as stored |
| the unread count, `CHAT_KINDS`, `addressed_to` | `frame_of`, `sminos_hublog` | unchanged: it is a chat event, counted and shown |
| the manager's reading of the owner's words | `manager_window.OwnerWords` | leaves it out (through `owner_event`) |
| the report view's classifier, MAWS's reader | `to-human/hooks/mods/to-human.tsx`, MAWS | unchanged code: both read a delivery as the person's only when its frame's sender is exactly `human` |
| the lead rule, a channel's timeline | CH2, EN.G2 | read `notice_of`; not built here |

The frame line and the envelope are confirmed by MAWS's architect against MAWS's reader (2026-11-21): the sender `devcloud@<machine>` parses with and without a label and an unread count, and `from-name="devcloud@<machine>"` parses in the envelope.

### §2. `say`'s two flags

    sminos say --notice <program> [--exit-held] <text>                    # tagged, or untagged
    sminos say --notice <program> --in <project> <text>
    sminos say --notice <program> [--project P,..] [--machine M,..] … <text>
    sminos say --exit-held <text>

    EXIT_HELD = 3

`--notice` puts `notice: <program>` on every event the call appends. `--exit-held` changes the exit and nothing else: the call exits 3 when, for at least one tagged recipient, the line `say` printed was a held one. Held lines, and no other: for a recipient of this machine, `held_line(why)` with `why` in `HOLD_WORDS` (`config`, `transcript`, `cwd`, `protected`, `mode`, `failed`); for a recipient of another machine, whatever `remote_line` returned for a published `held`: `held_line(why, machine)`, `held_line_151(machine)`, or the `read-only` sentence. A hold that passes on its own (`PASSING_LINE`, `UNREAD_LINE`), a woken thread, a live one, a pending or a gated line, and `recorded (on <machine>)` exit 0. An ended thread and no member exit 4 with nothing recorded, with or without the flag. Without a tag the flag changes nothing.

| Where | Exit | Words |
|---|---|---|
| `--notice` inside a session | 2 | `--notice marks a notice of a machine's own program, and a session is not one: drop it` |
| `--notice` with a value outside `NOTICE_PROGRAM_RE` | 2 | `--notice names the program that speaks, as a lower-case word of letters, digits and hyphens (32 at most): %s` |

`sminos help` gains one line for each flag; neither is in the skill.

### §3. A host's delivery (`D/boot/devcloudlib/notices.py`)

`NOTICE = "devcloud"`. `deliver(user, d, text, call, say)` keeps its signature and what it does on a host that is not enrolled (nothing run; the journal and `wall`). Each step is one `say` as the host's user with no session id, as today:

| Step | Runs | Then |
|---|---|---|
| 1, when the descriptor names a tag | `say --notice devcloud --exit-held "<tag> <text>"` | 0: delivered. Any other exit, 3 among them: go on |
| 2, when the descriptor names a project | `say --notice devcloud --project <project> <text>` | 0: delivered. 4 (no member is live): step 3. Any other: the journal and `wall` |
| 3 | `say --notice devcloud --in <project> <text>` | 0: delivered. Any other: the journal and `wall` |

This is today's order, with exit 3 as one more way step 1 does not end the delivery. Step 3 runs whenever the broadcast reached no live member, whatever step 1 recorded: what step 1 recorded for a held thread whose reach is private sits under a writer only that thread's audience reads, and is no note the project's next session finds. For a held thread of default reach the project's log then holds the notice twice, which is accepted. `<project>` is what the descriptor holds: an id after a handover (§5), the name `sminos who` printed for a host as `vm up` made it.

A step whose `say` exits 2 is run once more as it was before this change (without `--notice` and `--exit-held`), and that run's exit decides; the journal says `devcloud notice: this host's sminos does not know the notice flags; sent without them`. At exit 3 the journal says `devcloud notice: recorded for the thread that owns this host, which is not woken with it now; going on to its project`. The other journal lines, and the lock that keeps two sends apart, are unchanged.

### §4. `sminos who --thread`

    sminos who --thread <name>

`<name>` is what `find_target` takes, with one leading `@` dropped: an alias, `alias#short`, `<project>/<alias>`, a short id, a seat's or a thread's id, a session id that is or was the thread's. One line of JSON on standard output and exit 0 when one seat or member answers; exit 4 with sminos's own line on standard error when none does or several do; exit 2 for usage. It takes the migration and the locks every reading verb takes (`main` sends only a `who` with neither a target nor `--thread` down its early path).

    {"thread": "<thread id, or \"\" for a session that is no thread>",
     "session": "<its current session id, or \"\" for a vacant seat>",
     "short": "<the first eight characters of session>",
     "alias": "<alias>",
     "opened": "spawned" | "human" | "",
     "state": "<the row's state, as list --json gives it>",
     "ended": true | false,
     "local": true | false,
     "machine": "<the machine it runs on>",
     "project": {"id": "<project id>", "name": "<project name>"}}

`ended` is true for a retired seat and for a thread whose end is in effect; a thread its human opened that has ended answers only to its full session or thread id (`ended_target`), and to any other name the exit is 4, as for a name nothing answers to. `project` is null when the project of a seat's directory cannot be read from where the command runs (a folder macOS protects). Nothing else is exported: no former session, no launch, nothing of the record's journal (X1).

| Case | Exit | Words |
|---|---|---|
| nothing answers the name | 4 | `no seat or member matching '%s'` (`retire`'s words) |
| several answer it | 4 | `find_target`'s own sentence, which names each |

### §5. `devcloud vm owner`

    devcloud vm owner <name> <thread>

In `D/driver/context.py`:

    def sminos_thread(env, name):
        """§4's answer for `name`, as a dict; DriverError(FAILED, …) in §5's
        words when sminos is not found, exits non-zero or prints no answer."""

    class Context:  # a new keyword, `thread=None`, injected by the tests as `creator` is
        thread: Callable[[str], dict]

In `D/driver/hostctl.py`:

    @dataclasses.dataclass(frozen=True)
    class OwnerSet:
        was_tag: str | None        # the descriptor's DEVCLOUD_CREATOR before
        was_project: str | None
        tag: str                   # what it holds now
        project: str | None        # None: the host's parser does not know the key, and it was left out

    def owner_set(ctx, host, tag, project):
        """The owner program run on the host as root. Its answer as an OwnerSet;
        DriverError in §5's words for a departure that has started (the program's
        exit 3) and for a notice being sent (4); None when no whole answer came
        back (a lost connection, any other exit, a line that is not the answer),
        which says nothing of whether the write was made."""

    def host_owner(ctx, host):
        """The tag the host's descriptor holds in DEVCLOUD_CREATOR, "" when it
        holds none, None when it could not be read: one read over ssh, as
        host_expires reads the lease."""

In `D/driver/adopt.py`:

    def update(ctx, name, **fields):
        """The adoption record of `name` read again and saved with only `fields`
        changed; the record as saved. What `lease` (expires, lifetime) and
        `owner` (creator) write through, so that neither writes back a field it
        read before the other's write."""

In `D/driver/owner.py`: `run(ctx, name, given)`, dispatched from `cli.py` as `owner`, with `name` and `thread` as positionals.

**The order.**

1. `ctx.thread(given)` and the refusals below, before anything is asked of a host or a provider.
2. The host: `adopt.load(ctx, name)`, else `ctx.find(name)`, as `vm lease` finds one. `old` in the sentences below is the short id the label or the record holds now.
3. The host's write: `hostctl.owner_set(ctx, host, "@" + short, <the thread's project id>)`. The descriptor takes the project's id, never its name, which another log may share. A departure or a notice being sent ends the verb with nothing changed. No whole answer is not a failure: `host_owner` is read, and the verb goes on when the host names the new tag, and ends in the "did not take" or the "gave no answer" sentence when it names another or cannot be read.
4. The label or the record, when it differs: for a VM, `client.set_labels(id, {"devcloud-creator": short}, merge=True)`; for an adopted machine, `adopt.update(ctx, name, creator=short)`. A failure or a lost reply here does not end the verb either: step 5 says what holds.
5. Both sides read back, on every path that reached step 4: `host_owner`, and `client.get(id)`'s label or `adopt.load`'s `creator`. The handover is reported only when the host names `@<short>` and the label or record names `<short>`. Otherwise the verb exits 1 saying what each side holds.

Run again, every step finds its part done, or does it, and the verb exits 0. No lock spans two drivers and none is built: two handovers of one host at once can leave the host naming one thread and the label the other, and then at least one of them says so. A disagreement at rest was made by two runs' last writes, and the run that wrote last reads both sides after that write, so it never reports a handover over one.

**The owner program** is a Python text the driver sends on standard input to `python3 -P - <tag> <project>` on the host, as root. It imports the host's own library from beside the real path of `/usr/local/bin/devcloud` (`devcloudlib.lease`, `devcloudlib.status.departure_started`, `devcloudlib.descriptor`, `devcloudlib.envfile.quote`, `devcloudlib.proc.write_file`) and:

1. takes the host's send lock, the file `notices.lock` beside the lifecycle lock, which the lease service holds while it sends a notice: `lease.locked(path=…, timeout=20)`, one acquisition through the host's own helper. Not had in twenty seconds: exit 4, nothing written. On a host built before the send lock (2026-10-28) no service takes that file, and the step excludes nothing;
2. takes the lifecycle lock, exclusively (`lease.locked()`), the send lock before it as the lease service takes the two;
3. exits 3 when the host's departure has started, writing nothing;
4. reads the descriptor and builds its new text: the first assignment of `DEVCLOUD_CREATOR` replaced, any later one dropped, the line appended when there was none, and the same for `DEVCLOUD_CREATOR_PROJECT`; every other line as it was;
5. parses the new text with the host's own `descriptor.parse` (`allow_http` as the host's CLI sets it). When it is refused and the same text without the project key parses, that text is taken and the answer's `project` is null; when it is refused otherwise, exits 1 with the parser's line and writes nothing;
6. writes it through `proc.write_file` with the file's own mode, reads it back, and prints one line, `{"was": {"tag": …, "project": …}, "now": {"tag": …, "project": …}}`, exit 0.

Its paths (the descriptor, the two locks, the status file) and its wait are parameters with the host's defaults, so a unit test runs the very text against a temporary host.

**What a handover redirects.** The notices of every tick of the host's lease service that starts after it. A notice being sent as the handover is asked finishes first, to the thread that owned the host then: the program waits for it, and refuses when it is still being sent after twenty seconds. On a host built before the send lock, a notice whose tick read the descriptor before the handover can still go to the former owner after the verb has returned.

| Case | Exit | Words (after `devcloud vm: `) |
|---|---|---|
| handed on | 0 | `%(name)s was owned by @%(old)s; %(alias)s#%(short)s (%(project)s on %(machine)s) owns it now`, on standard output without the prefix, `project` the project's name; for a host with no owner, `%(name)s had no owner; … owns it now` |
| nothing differed | 0 | `%(name)s is owned by %(alias)s#%(short)s (%(project)s on %(machine)s) already` |
| the host's parser left the project out | 0 | a second line: `%(name)s was built before a host kept its owner's project: a notice no session of %(alias)s takes ends in its journal` |
| no sminos CLI | 1 | `owner: no sminos CLI was found, and only sminos says which thread a name is: nothing was changed` |
| sminos exits 2 | 1 | `owner: this machine's sminos does not answer who --thread (it is older than 1.53.0): update the sminos plugin; nothing was changed` |
| sminos exits otherwise, or prints no answer | 1 | `owner: sminos names no thread for %(given)s (%(line)s): nothing was changed`, `line` its last line on standard error |
| `thread` empty | 1 | `owner: %(given)s is a session, not a thread (one the MAWS app launched keeps MAWS's rules), and a VM is owned by a thread: nothing was changed` |
| `session` empty | 1 | `owner: %(alias)s holds no session (a vacant seat); fill it first: nothing was changed` |
| `local` false | 1 | `owner: %(alias)s#%(short)s is a thread of %(machine)s, and a VM is handed to a thread of the machine this runs on, the only place sminos asks devcloud what a thread owns: run it on %(machine)s; nothing was changed` |
| `ended` true | 1 | `owner: %(alias)s has ended (retired, or stopped for three days), and a VM is handed to a thread that has not: nothing was changed` |
| `project` null | 1 | `owner: sminos could not read %(alias)s's project from here (its directory is in a folder macOS protects): run it from inside that folder; nothing was changed` |
| the host's departure has started | 1 | `%(name)s's departure has started; its owner stays as it is` |
| the host is sending a notice | 1 | `%(name)s is sending a notice now, and a handover waits for it, so that none goes to the thread that gives the host up once it is done: nothing was changed; run it again in a minute` |
| no whole answer, and the host names another tag | 1 | `%(name)s did not take the new owner (%(seen)s) and still names %(host)s: nothing else was changed`, `seen` the exit and the program's last line, `host` a tag or `no owner` |
| no whole answer, and the host cannot be read | 1 | `%(name)s gave no answer about its owner (%(seen)s): whether it took the new one is not known, and nothing else was changed; run devcloud vm owner %(name)s %(given)s again` |
| the two sides do not both name the session written | 1 | `%(name)s's owner is not settled: the host, which sends its notices, names %(host)s, and %(where)s, which decides whom sminos refuses to retire, names %(label)s; this run wrote @%(short)s. Another devcloud vm owner ran at the same time, or a write did not land: run devcloud vm owner %(name)s %(given)s again to settle it`, `where` being `its provider's label` or `this Mac's adoption record`, `host` and `label` each a tag, `no owner`, or `what could not be read` |
| fewer than two arguments | 2 | argparse's own |

`devcloud vm ls` heads the column `OWNER`; `ls --json` keeps the key `creator`. The usage text in `cli.py` and `D/README.md`'s synopsis gain `devcloud vm owner <name> <thread>`.

### §6. The retire refusal's words (`sminos_threads.owned_words`)

For an answer that names hosts:

    it owns hosts that still exist: <hosts>; what becomes of a host is its owner's call: once nothing on it is needed, <downs>; or hand it to a thread of this machine that stays, <hands>; then it can be retired

`<hosts>` is `host_words` of each, joined by `, `, as today (`dc-x-0001 (hetzner, account main)`, `box (an adopted machine)`). `<downs>` is, for each host, `` `devcloud vm down <name>` deletes it `` or, for an adopted machine, `` `devcloud vm down <name>` releases it and leaves it running ``, joined by `; `. `<hands>` is `` `devcloud vm owner <name> <thread>` `` for each, joined by `, `.

For what devcloud could not ask, alone or after `and `:

    devcloud could not tell whether it owns a host that still exists: <what>

`owner_guard`'s frame around them (`%s is not %s: %s`, and the sentence naming `sminos retire … --owner-unknown`) is unchanged. `sminos help` says of `retire`: "Refused for a session that owns a devcloud host that still exists (it names the host, with devcloud vm down and devcloud vm owner), and when devcloud cannot tell".

### §7. `spawn --on`, the Mac side (`S/sminos_on.py`)

    sminos spawn <alias> <task|-> --on <vm>  [--cwd <path on the VM>] [--role R] [--brief B] [--worktree W]
                 [--stamp F=V]... [--permission-mode M] [--model M] [--effort E]
    sminos spawn <alias> <task|-> --on new   [--vm-project owner/repo[@ref]]... [--vm-confirmed] [the same]

    HOST_MARKER = "/etc/devcloud/boot.env"      # devcloud's own test of a host
    DEVCLOUD_ON_MIN = (0, 18, 0)                 # the devcloud that has `up --enroll --expect-creator` and `vm owner`
    CHECKOUTS = "~/Developer/GitHub"             # where a host's boot checks projects out
    LABEL_RE = re.compile(r"[a-z0-9-]{1,20}")    # devcloud's rule for --label
    READY_RE = re.compile(r"(\S+)  ready in \d+m\d\ds")   # the one line in which `vm up` names its host
    ENROLL_WAIT, ENROLL_POLL, REMOTE_TIMEOUT = 660, 30, 480   # seconds; SMINOS_ON_ENROLL_WAIT, _POLL, SMINOS_ON_TIMEOUT

    # `new` always means a VM to be made: a host of that name is reached with `devcloud vm ssh`, never with --on.

    def spawn_on(a):
        """`spawn` with --on: the checks in §7's order, `vm up` for `new`, the
        VM side over `devcloud vm ssh`, the wait, the line. Exits; returns nothing."""

    def reach_refusal(session):
        """Why the session's reach is not this machine's default, in row 10's
        words; "" when it is."""

**The order.** (a) Usage: the alias as `spawn` checks it; `--vm-project` or `--vm-confirmed` without `--on new`; `--wait`; `--settings`; a `--cwd` that is neither absolute nor `~/…`. (b) This machine is a devcloud host. (c) This machine is not enrolled. (d) `--on` names this machine (`host_name()`, compared without case). (e) From a session: it has an address (`session_address` is not empty); its project syncs through a hub or is a machine's own (`project_kind` is not `local`); the reach rule. (f) devcloud's CLI: found, and at least `DEVCLOUD_ON_MIN` (the copy `SMINOS_DEVCLOUD` names is taken at its word, as `owned_by` takes it). (g) For `new`: a session runs it; the projects; the directory. For a VM: the directory. (h) For `new`: `vm up`. (i) The VM side, each run of it preceded by the reach rule read afresh, and tried again only on an outcome line whose `why` is `not-enrolled`, for `new` only.

**The reach rule.** A route back comes first: a session opened elsewhere answers its spawner through the org's hub, so the spawner's machine must be enrolled and its project one the hub carries. Then the rule itself, `reach_refusal`, read at (e) and again immediately before every run of the VM side, the tries of the wait included, since a reach narrowed while a VM is being made must not be outrun. The session's record is what `ensure_record` gives for it, the function by which sminos itself rebuilds a record that was lost (from the session's lineage, and private with no shares when a stream of its own is catalogued); on a later read, what `sminos_records.read` gives. No record (one that cannot be read, or could not be written) refuses. A record refuses unless `sminos_audience.policy_of` gives it the default access (`listed`) and no shares. Its owners are not part of the rule: a thread opened with `--on` is as readable as a default spawn made here, and is owned by the VM's owners, whose words it takes (the last section, (b)).

**The projects, for `new`.** With `--vm-project`: those, in order, as given. Else one, `<owner>/<repo>@<branch>`. `<owner>/<repo>` is the path of the `origin` of the repository the command runs in (`parse_remote`; its host `github.com`). `<branch>` and the commit are read at the directory the command runs in, which is the caller's own worktree and never the repository's main checkout (`git -C <cwd> symbolic-ref --short HEAD`, `git -C <cwd> rev-parse HEAD`): `owning_repo` answers the main checkout for a linked worktree, and is used for the origin alone. The project is taken only when `git ls-remote origin refs/heads/<branch>` (thirty seconds) answers one line whose ref is exactly that and whose commit is the worktree's. `ls-remote --heads origin <branch>` is not used: it also answers for a branch whose name ends in `/<branch>`.

**The directory.** `--cwd` as given; the request's `origin` (§8) is then null. Else it is inferred, `CHECKOUTS/<repo>`: for `new`, `<repo>` of the first project when it is `owner/repo[@ref]`; for a VM, of the repository the command runs in. The request's `origin` is then that repository's remote key (`remote_key`: `github.com/<owner>/<repo>`, the path lower-cased), and the VM side holds the directory to it.

**What `vm up` is run with:** `devcloud vm up --enroll --keep --expect-creator <short> [--label <alias>] --project <p>... [--confirmed]`: `<short>` the calling session's short id, the label when the alias is whole by `LABEL_RE`, `--confirmed` only for `--vm-confirmed`. Its environment is this process's, with the directory of sminos's own interpreter first on `PATH` (as `owned_by`); standard input empty; each line of its standard output and error written through as it comes. Exit 0 and exactly one line of its standard output whole by `READY_RE` name the host.

**What the VM side is run with:** `devcloud vm ssh <vm> -- sminos spawn <alias> - --asked-from <json> --cwd <dir> --permission-mode <mode>` and each carried flag that was given, the task on standard input, bounded by `REMOTE_TIMEOUT` (then `stop_tree`). Its standard output is read for the outcome line (§8) and every other line of it written through; its standard error is written through and kept for the one sentence sminos reads in it (`no VM named`).

**After a VM was made,** every refusal and every unknown outcome ends with `KEPT`: `. The VM %(vm)s is kept and %(owner)s owns it: devcloud vm down %(vm)s ends it`. `%(owner)s` is `this session's thread` when `sminos_threads.thread_of` gives the calling session a record, and `this session` when it gives none (a session the MAWS app launched is no thread, and devcloud records it as it does for `vm up` today).

**Exit codes.** 2: usage. 1: any other refusal or failure sminos decides itself. Else what it was told: `vm up`'s own exit when that is not 0; the VM side's exit from an outcome line that is not ok; where the outcome is not known, `devcloud vm ssh`'s exit, or 1 when that was 0.

| # | Where | Exit | Words |
|---|---|---|---|
| 1 | `--vm-project`, `--vm-confirmed` without `--on new` | 2 | `--vm-project and --vm-confirmed are for the VM that --on new makes: drop them, or pass --on new` |
| 2 | `--wait` | 2 | `spawn --on: --wait watches a seat of this machine, and this seat is made on another: drop it (the session reports with sminos say)` |
| 3 | `--settings` | 2 | `spawn --on: --settings names a file of this machine, which the other machine does not hold: drop it (the session runs on that machine's settings)` |
| 4 | a relative `--cwd` | 2 | `spawn --on: --cwd is a path on the other machine: give it absolute, or from the home there as ~/…` |
| 5 | on a devcloud host | 1 | `spawn --on: this machine is a devcloud host, and devcloud's driver, which makes and reaches hosts, runs on a Mac only: nothing was spawned. Run it from a session on a Mac; here, sminos spawn without --on spawns on this machine` |
| 6 | this machine is not enrolled | 1 | `spawn --on: this machine is not enrolled in the org, so a session on another machine could tell this one nothing and would not be listed here: nothing was spawned` |
| 7 | `--on` names this machine | 2 | `spawn --on: %s is this machine: drop --on` |
| 8 | from a session with no address | 1 | `spawn --on: this session is no member of a project yet (sminos who prints no address), so the session opened there would have no one to answer: nothing was spawned` |
| 9 | from a session whose project is local | 1 | `spawn --on: this session's project, %s, syncs through no hub, so nothing a session on another machine says would reach it: nothing was spawned. Run it from a session in a project the org shares` |
| 10 | the reach rule | 1 | `spawn --on: this session's reach is not this machine's default (%s), and a session opened on another machine takes that machine's default, which could be wider: nothing was spawned. Spawn it here, or from a session whose reach is the default`, `%s` one of `its access is <access>`, `it has shares`, `its record cannot be read`; then `KEPT` when a VM was made |
| 11 | no devcloud CLI | 1 | `spawn --on: no devcloud CLI was found here (looked at: %s), and the devcloud plugin is what makes and reaches a VM: nothing was spawned` |
| 12 | devcloud too old | 1 | `spawn --on: the devcloud at %s is %s, and spawn --on needs %s or later: update the devcloud plugin; nothing was spawned` |
| 13 | `new`, no session | 1 | `spawn --on new: no session runs this, so the VM would have no owner: run it from a session, or make the VM yourself (devcloud vm up) and name it (sminos spawn --on <name>)` |
| 14 | `new`, no repository on GitHub | 1 | `spawn --on new: %s is in no repository whose origin is on GitHub, so there is nothing to tell the VM to check out: name it with --vm-project owner/repo[@ref]` |
| 15 | `new`, on no branch | 1 | `spawn --on new: this checkout is on no branch, and the VM clones a branch or a ref from GitHub: check a pushed branch out, or name the ref with --vm-project %s@<ref>` |
| 16 | `new`, origin lacks the branch | 1 | `spawn --on new: origin has no branch %s, and the VM clones from GitHub, so it would not get this work: push it (git push -u origin %s), or name what the VM checks out with --vm-project %s@<ref>` |
| 17 | `new`, the worktree's commit is not origin's | 1 | `spawn --on new: origin's %s is at %s and this checkout is at %s, so the VM would clone without what differs: push it, or name the ref with --vm-project %s@<ref>` |
| 18 | `new`, origin gave no answer | 1 | `spawn --on new: origin did not say where %s is (%s): try again, or name the ref with --vm-project %s@<ref>` |
| 19 | `new`, the first project is a registry name and no `--cwd` | 2 | `spawn --on new: %s is a registry name, whose checkout only its registry places: name the session's directory on the VM with --cwd` |
| 20 | a VM, no `--cwd`, no repository on GitHub | 2 | `spawn --on: %s is in no repository whose origin is on GitHub, so the session's directory on %s cannot be derived: name it with --cwd` |
| 21 | before `vm up` (a note) | — | `making a VM (a few minutes; devcloud's own lines follow): devcloud vm up %s` |
| 22 | `vm up` exits other than 0 | its own | `spawn --on new: devcloud vm up exited %d; its own lines above say why, and what became of any VM it made. Nothing was spawned`, and for exit 4: `. The cap is the person's: after their yes to this exact request, pass --vm-confirmed` |
| 23 | `vm up` exits 0 and names no host, or more than one | 1 | `spawn --on new: devcloud vm up succeeded and did not name one host where sminos reads it: find the VM with devcloud vm ls, then sminos spawn --on <name>` |
| 24 | devcloud has no host of that name (its line opens `no VM named`) | devcloud's | `spawn --on: devcloud has no host named %s (its line is above): nothing was spawned`; and, when the org's directory lists the name, the note `%s is a machine of this org that devcloud has no host for. If it is a Mac: a session is not opened on a Mac from another machine in this version, since a Mac's login keychain is closed to an ssh session and claude needs it; open it on that Mac` |
| 25 | a VM answers `not-enrolled` | 1 | `spawn --on: %s is not enrolled in the org (no endpoint on it has been welcomed: a host made without the MAWS project, or one whose enrollment has not finished; devcloud vm ssh %s -- devcloud status shows its maws step), so no other machine would see a session there: nothing was spawned` |
| 26 | `new`, the VM answers `not-enrolled` (a note, once) | — | `%s is up and not enrolled in the org yet: waiting up to %d minutes for its endpoint (the host tries again every 5), then spawning` |
| 27 | `new`, the wait is over | 1 | `spawn --on new: %s did not enroll within %d minutes: nothing was spawned. Once sminos machines lists it, sminos spawn --on %s spawns there`, then `KEPT` |
| 28 | the VM side answered not ok, for any other `why` | its exit | `spawn --on: %s's sminos answered exit %d; its line above says why, and what, if anything, exists there`, then `KEPT` when a VM was made |
| 29 | the outcome is not known | `devcloud vm ssh`'s, 1 for 0 | `spawn --on: the outcome on %s is not known (%s): a session may or may not have started there, and devcloud vm ssh %s -- sminos list shows`, `%s` one of `no outcome line came back`, `more than one outcome line came back`, `the outcome line is not the last line it printed`, `the outcome line does not read as one`, `the outcome line names another alias than the one asked`, `the outcome line and the exit status disagree`; for exit 2 with no outcome line, also `. It ended with a usage error, so its sminos may predate this call`; then `KEPT` when a VM was made |
| 30 | no answer within the bound | 1 | `spawn --on: %s gave no outcome within %d minutes, and the call was stopped: a session may or may not have started there, and devcloud vm ssh %s -- sminos list shows`, then `KEPT` when a VM was made |
| 31 | spawned (standard output) | 0 | `seat spawned on %(machine)s: %(group)s/%(alias)s  [%(short)s / %(seat)s]  status=%(status)s  (message it: sminos say "@%(session8)s …"; it is listed here once %(machine)s's events arrive)`; `seat re-filled on …` for a refill; `session8` the first eight characters of the outcome's `session` |
| 32 | after 31, for `new` (a note) | — | `%(vm)s is kept and %(owner)s owns it: devcloud vm down %(vm)s ends it, and it sends a notice after three idle days` |

`sminos help` lists `--on`, `--vm-project` and `--vm-confirmed` under `spawn`, and `--asked-from` as the form another machine's sminos calls.

### §8. `spawn --asked-from`, the VM side, and the outcome line

    sminos spawn <alias> - --asked-from <json> [--cwd <dir>] [the carried flags]

    {"v": 1, "nonce": "<16 hex>",
     "org": "<the org the asking machine is enrolled in>",
     "origin": "<the remote key of the repository the directory was inferred for>" | null,
     "by": {"alias": "<alias>", "short": "<8 hex>", "project": "<project id>",
            "project_name": "<project name>", "machine": "<machine>"} | null}

`by` is null when no session ran the Mac side; `origin` is null when the Mac side was given `--cwd`. A value that is not this object whole (`v` 1, the nonce, `org` a non-empty string, `origin` null or a string, `by` null or its five strings, the short eight hex digits) exits 2 with `spawn: --asked-from is not a request this version reads` and prints no outcome line. `--asked-from` with `--wait` is a usage error.

Under it `cmd_spawn` does what it does without it, and:

1. on a machine that is not enrolled (`enrollment()` is None) spawns nothing, says `spawn: this machine is not enrolled in the org, and a session opened here for another machine would be seen by none: nothing was spawned`, and exits 1 with `why` `not-enrolled`;
2. on a machine enrolled in another org than `org` spawns nothing, says `spawn: this machine is enrolled in another org than the machine that asked, so the session and its spawner could not reach each other: nothing was spawned`, and exits 1 with `why` `other-org`;
3. expands a `--cwd` that opens `~/` from the user's home directory;
4. where `origin` is given, holds the directory to it: it must be a checkout whose `origin` has that remote key (`remote_key`). Otherwise it spawns nothing, says `spawn: %(dir)s is %(what)s, and the machine that asked took it for its checkout of %(origin)s: nothing was spawned. Name the directory with --cwd`, `what` one of `no checkout`, `a checkout with no origin`, `a checkout of <its remote key>`, and exits 1 with `why` `other-repository`. A directory that does not exist is refused as `spawn` refuses one today;
5. names the spawner: the preamble's `{{BY}}` is `%(alias)s (@%(short)s, in %(project_name)s on %(machine)s; sminos say "@%(short)s …" reaches it)` and the `joined`'s `by` is the alias; with `by` null both are as today (`the operator`, empty). The new session's record is what a spawn from this machine's terminal gives (`spawn_provenance`'s last case): the origin names no spawner's session, and nothing of `by` is a grant;
6. prints no `seat spawned:` line; its last line on standard output, for every way it ends after the value was read, is the outcome line:

       sminos-spawn <nonce> {"ok": true, "refilled": false, "group": "<group>", "alias": "<alias>",
                             "short": "<the engine's job id>", "seat": "<seat id>", "session": "<session id>",
                             "status": "<status>", "project": {"id": "<id>", "name": "<name>"},
                             "machine": "<this machine's name>", "cwd": "<the directory it runs in>"}
       sminos-spawn <nonce> {"ok": false, "exit": <the exit code>,
                             "why": "not-enrolled" | "other-org" | "other-repository" | "other"}

   one line, the JSON without a line break. What `spawn` says on standard error (a refusal's sentence, a warning that an event could not be appended) is said as today.

**What the line guards against.** The VM is the owner's own machine, reached with the driver's key, and its sminos is trusted: the line is no defence against a hostile VM, and none is built. It guards against confusion: a task's text or a tool's noise that looks like an answer, an answer cut short, a copy that predates the call.

**How the Mac side reads it.** The outcome is known only when all of this holds, and is "not known" (§7, row 29) otherwise:

- exactly one line of standard output opens `sminos-spawn <its nonce> `, and it is the last line;
- the rest of that line is one JSON object whose `ok` is a boolean;
- for `ok` true: `devcloud vm ssh` exited 0, `alias` is the alias asked for, `session` and `seat` are whole by `UUID_RE`, and `short`, `group`, `status` and `machine` are non-empty strings;
- for `ok` false: `exit` is an integer other than 0 and is `devcloud vm ssh`'s exit, and `why` is a string.

It acts on `why` `not-enrolled` alone (row 25, or the wait of rows 26 and 27) and takes every other value as row 28: a VM of another org, or another repository's checkout, is never waited on. No exit code by itself is read as an outcome: an exit 2 with no line is said as a copy that may predate the call, never as nothing spawned.

Without `--asked-from`, `spawn` is byte for byte what it was: that is the call an older Mac, or a person, makes over `devcloud vm ssh` today.

### §9. `devcloud vm up --enroll` and `--expect-creator`, and the line that names the host

    devcloud vm up --enroll --expect-creator <short> …

With `--enroll`, `up` requires the host to provision MAWS's endpoint: where `compose.provisions(profile, projects)` is false and the profile's `[desk]` names the provisioning, `compose.MAWS_PROJECT` is appended to the projects (after those named, so the first project's `host.toml` still governs) and `up` says `enroll    the MAWS project is added: its setup installs the endpoint this host enrolls with`.

With `--expect-creator <short>` (eight hex digits, else a usage error), `up` makes nothing unless the creating session it reads itself (`ctx.creator()`, as it records one today) is that one. It is how a caller that already knows who runs it, `sminos spawn --on new`, keeps devcloud from making a host it records no owner for, or another.

Both are checked before anything is listed, priced or made, under `--dry-run` too:

| Case | Exit | Words (after `devcloud vm: `) |
|---|---|---|
| `--enroll`, a profile whose `[desk]` names no provisioning | 3 | `--enroll: the profile's [desk] names no provisioning (provisioning_secret_v2 with delegation_id), so a host it makes cannot join the org: nothing was made` |
| `--expect-creator`, no creating session read | 1 | `--expect-creator: the caller expects @%(short)s as this host's creator, and devcloud read no creating session here (sminos who --session gave it no address it reads): nothing was made` |
| `--expect-creator`, another session read | 1 | `--expect-creator: the caller expects @%(short)s as this host's creator, and devcloud read @%(read)s: nothing was made` |

Without either flag `up` is what it was. Two of `up`'s lines are read by sminos, and each is pinned by a test in `D/tests/unit` named for that reader: `<name>  ready in <m>m<ss>s`, as the one line of that form in everything a whole `up` prints (the account and caps lines before it, `created`, a `maws      deferred` line, and the five lines of the host's particulars after it); and the opening `no VM named` of `Context.find`'s refusal.

### §10. An older copy on the other side

A host's sminos follows the source its synced settings declare, which may be pinned to a ref: nothing here says, or may say, that a host updates within a fixed time.

| What is new | Who may meet it older | What then |
|---|---|---|
| `notice` on a `human` event | a reader on a sminos before 1.53.0 (a Mac not yet updated, a session's hooks from a cached copy, a host whose source is pinned); MAWS before its own change | it reads the event as today: a person's line, asked of the endpoint, framed `from human`; on another machine the endpoint answers `peer`, so it arrives as a peer's frame either way. Accepted (X8's last sentence, D7). So a notice is a machine's to its reader only when both the host's boot library and the reader's sminos are this child's |
| `say --notice`, `say --exit-held` | a host whose sminos does not know them (a devcloud run from a checkout ahead of the host's source, or a host whose source is pinned behind) | usage error, exit 2, nothing recorded; the host runs the step again without them (§3) |
| a boot library that passes them | every host made before devcloud 0.18.0, for its life | it sends as before: unmarked, and going on only at a non-zero exit, so not for a held thread. The receiving side is unchanged for it: X2 takes the tag to the thread's current session and the wake starts a stopped one (acceptance 8) |
| `sminos who --thread` | devcloud 0.18.0 beside a sminos before 1.53.0 | exit 2; `vm owner` refuses in §5's words and changes nothing |
| the refusal that names `devcloud vm owner` | sminos 1.53.0 beside a devcloud before 0.18.0 | devcloud answers the verb with a usage error; `devcloud vm down` is still the way on. Accepted: both update from one marketplace |
| `devcloud vm up --enroll --expect-creator` | sminos 1.53.0 beside a devcloud before 0.18.0 | `spawn --on` refuses before it calls (§7, row 12) |
| `spawn --asked-from` | a VM whose sminos is older | usage error, exit 2, no outcome line; the Mac says the outcome is not known and that the copy may predate the call (§7, row 29) |
| `devcloud vm ssh <vm> -- sminos spawn …` by hand, with no `--asked-from` | a VM on this sminos, called by an older Mac or a person | unchanged (§8's last sentence) |
| the owner program | a host made before 0.18.0 | it runs: it needs only the host's own library as it has been since `lease set` existed. A host whose parser predates the project key takes the tag alone, and one built before the send lock (2026-10-28) can still send the former owner a notice it had read the descriptor for (§5) |
| the `OWNER` header | whatever read `devcloud vm ls`'s table | nothing in this tree parses the table; `--json` is unchanged |

### §11. What the tests are built on

**`T/devcloud_standin.py`** keeps `vm owned-by` exactly as it is and learns two verbs, both set through the same `$HOME/devcloud-standin.json` and logged to `devcloud-standin.calls`:

- `vm up …`: prints the lines its `up.lines` holds (by default a whole `up`'s: the account and caps lines, `created   <up.name> (id 1) from base, slow path`, `<up.name>  ready in 0m01s` and the five lines after it), writes `up.stderr`, and exits `up.exit` (0). `up.gate`, a path, holds its answer back until the file exists, so a test can change something while a VM is being made. With `up.creator` set, it answers `--expect-creator` as devcloud does: exit 1 and devcloud's line when the short it was given is another.
- `vm ssh <name> -- <words>`: for a `<name>` its `hosts` holds, joins the words as `shlex.join` does and runs the line with `/bin/sh -c` under that host's `env` (its `HOME`, `SMINOS_HOME`, `DAEMON_HOST`, `PATH`), standard input passed on, the word `sminos` at the line's head replaced by the launcher `sminos` names, and exits as that line did; `hosts.<name>.exit`, when set, is answered instead with nothing run (2 for a copy that predates the call, 255 for a host that does not answer), and `hosts.<name>.stdout`, when set, is printed in place of what the line printed (an outcome line twice, one cut short, one for another alias). For any other name: `devcloud vm: no VM named <name> in any usable account`, exit 1.

**`T/test-on.sh` and `T/test-notice-machines.sh`** are two sminos homes named as `T/rl10-machines.sh` names them (`rl10_as`, `rl10_cut_over`), the second also served by `T/endpoint_standin.py` with the verdict the case sets. A machine is "not enrolled" when its home holds no `daemon/identity.json`, and "of another org" when its identity names one.

**`D/tests/unit/driver_fixtures.py`**: `make_ctx` passes `thread=`, a function from a name to §4's answer, as it passes `creator=`; `FakeRemote` answers the owner program by a rule on `python3 -P -` and the read of a host's owner by a rule on `DEVCLOUD_CREATOR`, each through its `fn` where a test changes what a later read finds; and the program's own behaviour is tested by running its text.

**`D/tests/fixtures/sminos.py`** plays `say` with the two flags, and, where its state says so, as a copy that does not know them.

**The gates' parts.** The five suite files this child adds (`T/test_notice.py`, `T/test-notice-machines.sh`, `T/test_who_thread.py`, `T/test_on.py`, `T/test-on.sh`) go at the end of `run_suites_c` in `T/run-sminos-tests.sh`, the third of the three parts `run_suites` calls (Constraints). None belongs to the part `channels`, which is the sibling child's.

### Dependencies

Nothing is added: Python's standard library on both sides, `git` on the Mac for the worktree's branch and commit and the one question put to origin, devcloud's driver as it is. The Mac side of `spawn --on` needs devcloud 0.18.0, and `devcloud vm owner` needs sminos 1.53.0; each says so when it meets less. M5 needs what `devcloud vm up` needs (a seed key, a profile with an account and a `[desk]`) and the person's registry to hold the MAWS project under the name devcloud's README gives it.

## Surprises & Discoveries

What the code map and this plan's own reading found that D4 did not expect. Each shaped a milestone or an interface above.

- Observation: a devcloud VM is a sminos machine only when it is made with the MAWS project under a profile that names the provisioning; otherwise its boot installs no daemon, a session spawned there is seen by no other machine, and its notices never reach sminos.
  Evidence: `compose.provisions`; `sminos_host` returning `sminos: not enrolled, local-only`; `notices.deliver` running `say` only `if program and sminos_host.cut_over(user, env)`; the unit test `test_a_vm_without_the_maws_project_is_not_enrolled`.
- Observation: a notice moves to its next step only on a non-zero exit of `say`, and a recipient on another machine that is held gives exit 0, so a held thread's notice stopped there.
  Evidence: `notices.deliver`; `deliver_say`'s branch for a member that is not local, which prints `remote_line(member)` and continues.
- Observation: who owns a host is stored in three places, in two forms, and nothing rewrote them after `up`: the provider's label (a bare short id), the descriptor (a tag, and the project), and for an adopted machine the Mac's record (a bare short id, with a descriptor that names no project).
  Evidence: `compose.labels`, `compose.descriptor`, `adopt.Record.creator`, `adopt._prepare`.
- Observation: a host's descriptor parser refuses a key it does not know, and the project key dates from 2026-10-27, so writing it to an older host would stop that host's lease service from reading its descriptor.
  Evidence: `descriptor.parse` (`unknown key … in the boot descriptor`); `git log -S DEVCLOUD_CREATOR_PROJECT -- devcloud/boot/devcloudlib/descriptor.py`.
- Observation: over ssh the VM's `spawn` has no spawner: it writes "spawned by the operator", an empty `by`, and a record with the VM's default reach, where a spawn from a session copies the spawner's access and shares.
  Evidence: `caller_alias`, `render_preamble`, `spawn_provenance`'s three cases.
- Observation: `owner_event` being false does not keep a marked event off the bridge: the route is chosen from the endpoint's verdict before the writer is looked at, and on the VM itself the endpoint answers `words` for the VM's own line.
  Evidence: `sminos_control._routes` (`owner = words if words is not None else … owner_event(event)`); MAWS's architect, 2026-11-21.
- Observation: a process that takes deliveries only with a receipt gets every delivery through the inbox, a person's words included, so what tells a reader whose words a delivery is, is the frame's sender alone.
  Evidence: `_routes`'s `marker` branch; `to-human.tsx`'s `SMINOS_FRAMES`; MAWS's reader, as its architect ran it.
- Observation: delivery is keyed by the session an event names. An event that arrives naming a session its thread has since left is owed to no member: it is pushed to no process and wakes nothing, and the thread's current session meets it only when it next reads the chat. A hand-off carries the chat cursor and not the delivery record, so the successor's record cannot tell such an event from one its predecessor was given.
  Evidence: `_owed` (`not addressed_to(e, session)`), `deliver_owed` (`m.session not in to`), `hand_off` and `carry_hand_off`.
- Observation: nothing a sender holds says whether another machine is connected: the endpoint sends every machine as `online: false`.
  Evidence: `cmd_machines`'s docstring and its reading of `org.json`.
- Observation: with the marker's flag on every step, a host whose sminos does not know it would fail every step with a usage error and leave the notice at the journal; and the host's integration stand-in plays `say` only with exactly one argument.
  Evidence: `notices.deliver`'s three calls; `devcloud/tests/fixtures/sminos.py` (`args[:1] == ["say"] and len(args) == 2`).
- Observation: both machines run sminos from `main`: a host's copy is its declared source's head, and a Mac's daemon runs the marketplace clone. A branch's delivery code and its VM side run on neither until it is merged.
  Evidence: `plugins.refresh`, `sminos_daemon.installed_cli`.
- Observation: `devcloud vm up` reads nothing from the directory it runs in but the first project's `devenv/host.toml`; it prints its host's name in two human lines and has no output for a program.
  Evidence: `up.run`, `hostfile.read`.
- Observation: the adoption record has no lock, and `vm lease` saves the copy it read before its call to the host, so a second writer of the record would have its field written back.
  Evidence: `adopt.lease` (`record.expires, record.lifetime = …; save(ctx, record)`); no `flock` in `devcloud/driver/adopt.py`.
- Observation: devcloud's lookup of the creating session can fail where sminos's own did not, and `vm up` then makes a host with no owner and says nothing.
  Evidence: `session_creator` returning `(None, None, None)` for no CLI found, a timeout, a non-zero exit or an address its pattern does not read; `up.run` composing the descriptor and the labels from it unchecked.
- Observation: sminos already rebuilds a lost record's reach: a session with no record is private with no shares when a stream of its own is catalogued, and a spawn made here reads a parent with no record as the machine's default.
  Evidence: `ensure_record` and `has_own_stream`; `spawn_provenance` (`parent = parent or records.default_provenance()`).
- Observation: a direct `send` pushes everything its writer still owes the session as one text, under its own event's route.
  Evidence: `SendDelivery.payload`, pushed with `delivery.queue[-1]` in both places `send` and `resume` push it; `deliver_sent` is the path that delivers the same queue event by event.
- Observation: `owning_repo` answers a linked worktree's main checkout, and `git ls-remote --heads origin <name>` also answers for a branch whose name ends in `/<name>`.
  Evidence: `owning_repo`'s docstring; git's own matching of an `ls-remote` pattern against a ref's trailing components.
- Observation: `vm up` prints five lines after the one that names its host, and two unit tests of devcloud pin the argv of a notice's `say`, not one.
  Evidence: `up.run`'s last six `ctx.say` calls; `devcloud/tests/unit/test_idle.py` and `test_lease.py` (`["/usr/bin/python3", <cli>, "say", "@build#4f2a <text>"]`).
- Observation: the host's lease service holds a send lock of its own while it delivers a notice, from a descriptor it read before, and has done so since 2026-10-28.
  Evidence: `lease.tick` (`notices.lock`, taken before the lifecycle lock, never waited for); `git log -S notices.lock -- devcloud/boot/devcloudlib/lease.py`.
- Observation: MAWS's hub and endpoint pass an unknown field on a `human` event through whole; for a host's line reaching a session on another machine the endpoint answers `peer`, never `words`; no way exists to put MAWS's endpoint on a machine without the MAWS project; and two sessions of default access have one audience on a Mac and on a provisioned VM (the whole org reads and messages them), while their owners are each machine's own.
  Evidence: MAWS's architect, relayed by the composite's holder on 2026-11-21.

## Decision Log

- 2026-11-21 — **Verification.** This plan gets one review before it is built, by the `doperpowers:adversarial-reviewer` agent, on buildability: the milestones against the code, the names and sentences of Interfaces against the composite and the rulings, and §10's table against what each older copy really does. The build runs under `doperpowers:plan-executor`, a fresh executor a milestone; each milestone is reviewed at its close by the execution loop's reviewer. After M4, the last milestone that changes the tree, the composite's holder reviews the whole range through doperpowers:review-code at the panel rung `xhigh`, with these lenses given: what leaves a machine (a notice's fields and frame, what `--asked-from` carries, what the outcome line and `who --thread` export); that every refusal comes before its side effect (nothing made, spawned or written); the two plugins' contract read from both sides (§3, §4, §5, §8, §9); and §10's older copies. Its confirmed findings go to a fix wave, weighed as the owner's rule for review findings weighs them. M5 changes nothing and is not reviewed; what it finds is a change of its own. The review of this plan returned thirteen findings (the last entry).
- 2026-11-21 — **The lagging view is not built** (the holder's ruling after the plan's review; R7's third point had made it this plan's). An event that names a session its thread has left is pushed to no process and wakes none (Surprises & Discoveries). That is a property of delivery as T1 built it, for every sender whose view lags, a VM's notice among them, and nothing this change introduces. The event is not lost: it is in the project's log and counted unread for the thread's current session, which reads it at its next `sminos chat`. What it costs, said plainly: the window is the time between a change of session on the owning machine and the VM reading it, seconds while both are connected and as long as the disconnect when one is not; and the event that lands in it can be a lease warning, sent once per lease, thirty minutes before the VM is deleted, where an idle notice comes again every three idle days. The holder puts the limit to the owner; if they want it closed it is a milestone of its own. This plan pins the outcome in a test (M1), records it in TECH-DEBT, and words acceptance 8 by the condition under which it holds. The fix sized for that milestone: keep in the thread record the project log's positions at each change of session (CH1 keeps such positions for a channel), and let `_owed` read, for the current session, what names a former one past them. Alternative rejected: the daemon saying a marked notice again under the Mac's own human writer, which closes it for notices only and makes the Mac the notice's sender.
- 2026-11-21 — **A machine that is not connected is not a case of going on** (R7's parenthesis asked for it "if the sender's view already tells it"). It does not: the endpoint publishes no presence. Alternative rejected: reading `online` in the org's directory as kept, which is false for every machine. The composite already defers a machine publishing whether it is on.
- 2026-11-21 — **The live check runs after the merge** (R10 has it close the plan). Both machines run sminos from their marketplace's declared source, `main` unless a ref is pinned, so a check before the merge would exercise neither the VM side nor the Mac's delivery. Alternative rejected: pointing the VM's copy at the branch by hand, which the host's own refresh undoes when it next runs.
- 2026-11-21 — **The host is written by a program the driver sends** (R6 allowed this or a way for an existing host to get a new verb). Alternative rejected: a verb of the host's CLI with this as its fallback, two paths where every host alive at landing would take the fallback.
- 2026-11-21 — **devcloud decides what enrollment needs: `vm up --enroll`** (R1 named the MAWS project as what is needed today). Alternative rejected: sminos passing `--project maws` and reading the profile itself, which puts devcloud's knowledge in sminos twice and has to change in both plugins when MAWS ships its endpoint apart.
- 2026-11-21 — **The VM's name is read from `up`'s own `ready` line,** pinned by a test on devcloud's side as the one line of that form in a whole `up`'s output (five lines follow it; this plan first called it the last line). Alternative rejected: a machine-readable output for `up`, new surface for one word that `up` already prints in a fixed form.
- 2026-11-21 — **One flag carries the remote call, `--asked-from`, as JSON** (R3 and R4 each asked for a flag). The nonce, the asking machine's org, the repository an inferred directory was meant for, the spawner, and the refusals that rest on them are one mode, known or not known to a VM's copy as a whole. Under it the Mac prints the spawn's line itself: the VM's `seat spawned:` line ends with `sminos reply <short>`, which is false on another machine. Alternative rejected: one flag for the outcome line and one for the spawner, which lets a copy know one and not the other.
- 2026-11-21 — **`sminos who --thread` is the answer devcloud reads** (R6 left its form open). Alternatives rejected: exporting a thread's sessions in `list --json`, which X1 withholds on purpose; devcloud importing sminos's modules, which ties two plugins' internals.
- 2026-11-21 — **Exit 3 and the name `--exit-held`** (R7: any code but 4). 3 is the first code sminos does not use; "held" is the word T2's lines already give a sender. Alternative rejected: devcloud reading the line `say` prints, which makes a sentence written for a person a contract with a program.
- 2026-11-21 — **The host retries a step without the flags at exit 2** (R7 called the usage error "the safe side" for a host whose sminos lacks the flag; with the marker on every step it would be the journal). This plan first also skipped the log step after an exit 3, so that one log would not hold the notice twice. The review showed what that loses (the last entry, 7), and the step runs whenever nobody was live.
- 2026-11-21 — **The reach rule is access and shares, by the reading sminos rebuilds a lost record with.** Refused unless that reading gives the default access and no shares, and a record that cannot be resolved refuses. A spawner whose access is wider than the default is refused too, though the VM's default would be narrower: one rule a session can be told in one sentence. Owners are not in the rule: with the default access the whole org reads and messages a session whoever owns it, so an owner added here widens nothing there. This plan first passed a session with no record and refused one with an added owner; the review, and MAWS's architect's answer on reach, changed both. Carrying reach is not built.
- 2026-11-21 — **`--on new` asks origin where the branch is** (`git ls-remote origin refs/heads/<branch>`, the exact ref), for the branch and the commit of the caller's own worktree, and does not trust the local tracking ref. Alternative rejected: the tracking ref, which says what origin held at the last fetch and passes a branch someone else moved.
- 2026-11-21 — **The names:** `--vm-project` and `--vm-confirmed` (what reaches `vm up`, said by one prefix; `--project` on `say` and `list` already means a sminos project), `vm up --expect-creator` (devcloud's own word for what it records), `S/sminos_on.py`, `EXIT_HELD`, `notice_of`, `notice_sender`, `reach_refusal`, `adopt.update`, `hostctl.host_owner`. Rejected: `--checkout`, which names what the VM does and hides that it is `vm up`'s argument. The waits: eleven minutes for enrollment (two of the host's five-minute tries and a minute), a try every thirty seconds, eight minutes for one remote call (the engine's own launch bound is five), twenty seconds for a notice a host is sending.
- 2026-11-21 — **sminos's own `--on` refusals exit 2 (usage) or 1; every other exit is what it was told.** devcloud's 4 (a cap) and a seat refusal's 4 on the VM both pass through as 4, as R2 has devcloud's codes pass; the line printed tells them apart. Alternative rejected: mapping devcloud's codes onto codes of sminos's own, which hides from a session the code devcloud's skill taught it.
- 2026-11-21 — **`devcloud vm ls`'s header becomes `OWNER`.** After a handover the column holds a thread that made nothing. The label, the descriptor's keys and `--json`'s key keep "creator": renaming them would orphan every host alive.
- 2026-11-21 — **A session the MAWS app launched is not refused `--on new`.** devcloud records it as it does for `vm up` today, and nothing guards a VM so made, since such a session is no thread; the Mac's lines say "this session" of it and never "thread". Alternative rejected: refusing it, a rule no ruling asked for and that takes away what `vm up` allows.
- 2026-11-21 — **What is taught changes in one milestone at the end,** not with each behaviour: a skill must not teach `--on` before the verb, the handover and the notice it describes all exist, and one evaluation reads the whole.
- 2026-11-21 — **The plan's review, 2026-11-21.** The buildability review returned thirteen findings and the composite's holder ruled on each. Every premise was read against the code before anything was built on it. All thirteen hold; two are narrower in the code than as reported, and one ruling was applied in its narrower reading, each said where it stands. **Changed:**
  - *1. Two writers of a handover* (§5; M2). The verb reads both sides back after its writes and reports a handover only when both name the session it wrote; a lost reply, the host's or the provider's, is settled by that read and never taken for a write that failed; where the sides differ it exits non-zero naming what each holds. The adoption record, which has no lock and which `vm lease` saved from a copy read before its call to the host, is written by both verbs through `adopt.update`. No serialization across drivers is built: what two crossing runs can leave is said by the one that wrote last.
  - *2. The creator devcloud records* (§9, §7; M3). `vm up --expect-creator <short>`: devcloud makes nothing when the creating session it reads itself is none or another, and `--on new` passes it. Ordinary `vm up` is unchanged. The Mac-side check that the project's name is one word is dropped, since devcloud's own check covers what it guessed at. The Mac's lines say "this session" where the caller is no thread.
  - *3. A missing record* (§7; M3). The reach rule reads the record `ensure_record` gives, lost records rebuilt as sminos rebuilds them; one that cannot be resolved refuses; and it is read again immediately before every call to the VM. The rule is on access and shares (the entry "The reach rule").
  - *4. A route back* (§7, §8; M3). Refused: a Mac that is not enrolled, a session with no address, a session whose project no hub carries, and, by the VM, a request from another org (the request carries the Mac's org; that refusal is never waited on).
  - *5. The outcome line* (§8; M3). What it guards against is stated (confusion, not a hostile VM); it is read strictly (one line with the nonce, the last, its fields held to the call and to the exit status); anything else is an outcome that is not known; the wait tries again only on the VM's own `not-enrolled`; and a usage exit with no line is said as a copy that may predate the call.
  - *6. A notice inside another event's payload* (§1; M1). Real, and narrower than reported: only an operator's `send` or `resume` on a machine that is not cut over pushes a human writer's owed events as one text (a cut-over machine leaves an operator's send to the uplink, event by event, and a session's send has no `human` event in its queue). Such a queue is now delivered event by event.
  - *7. Where a notice goes on to* (§3, §5; M1, M2). A handover writes the project's id; and the log step runs whenever the broadcast reached nobody live, whatever the first step recorded. Applied in its narrower reading: `vm up`'s own write of the project is left as it is (the name `sminos who` prints), since the ruling on 2 leaves ordinary `vm up` unchanged; it is listed as a limit, for the holder to say whether the wider reading was meant.
  - *9. M5's teardown* (M5; Concrete Steps). Aliases of the run's own, checked absent; a ledger written as each resource comes to exist; one cleanup set before the first side effect, for every way out, the VM first and then this run's seats alone; an early stop classed by the stage reached; a VM gone only on devcloud's own word; what could not be ended reported first.
  - *11. The wrong checkout* (§7, §8; M3). The branch and the commit are the caller's own worktree's, asked of origin by the exact ref; the request carries the repository an inferred directory was meant for, and the VM refuses a checkout of another origin.
  - *12. Tests that contradict the tree* (M1, M3; §9). `test_lease.py`'s pin of the argv is among the tests M1 changes; `up`'s `ready` line is pinned as the one line of its form in a whole output; every sentence that called it the last line is corrected.
  - *13. M5's proof* (Concrete Steps). An engine job is found by the full id of the session it runs; the child reports by the address its preamble gave it, which the task does not restate; and the VM's sminos is checked, as the Mac's is, before a result is attributed to this release.

  **Accepted, with the reason:**
  - *8. A notice in flight during a handover.* Taken as far as one acquisition goes: the program the driver sends takes the host's send lock ahead of the lifecycle lock, so on a host built since 2026-10-28 a handover waits for a notice being sent, and none goes to the former owner once the verb has returned. An older host can still send one. What a handover redirects, on any host: the notices of ticks that start after it.
  - *10. The lagging view.* Not built, on the holder's ground (the entry above).
  - *The noted limits.* A recorded notice is not a timely one when the owning machine is asleep or disconnected; a notice is a machine's to its reader, and goes on for a held thread, only where both the host's boot library and the reader's sminos are this change's; no sentence promises when a host's sminos updates, since its source may be pinned; and a thread the census window ends does not come back by itself an hour later: it is reopened, or the VM is handed on. M4 holds what is taught to these.
  - *Reach across owners* (MAWS's architect). A thread opened with `--on` is as readable as a default spawn made here, and is owned by the VM's owners, whose words it takes; in an org with more than one owner those may be other people than the owners of the spawner's machine. A known property, recorded and not refused.
- 2026-11-21 — **The suite gates are three.** A change of the gates that is merging as this plan is revised splits `sminos-suites` into `sminos-suites-a`, `-b` and `-c`. The plan is written against the three (its five files at the end of `run_suites_c`), and the build's first step, a merge of `origin/main`, decides which names hold until then (Constraints).

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

**(a) Sentences of the composite this plan makes false or completes, each with the replacement proposed.**

D4:

1. "`--on new` runs `devcloud vm up`, whose caps, consent rules and exit codes are unchanged and decide whether a VM is made; sminos waits for the machine's enrollment and spawns there." → "`--on new` runs `devcloud vm up --enroll --keep --expect-creator <the spawner's short id>` with the spawner's repository at the branch of the worktree it runs in, which origin must hold at that worktree's commit (or with the projects `--vm-project` names). devcloud's caps, consent rules and exit codes are unchanged and decide whether a VM is made; `--confirmed` reaches it only as `--vm-confirmed`. devcloud makes nothing where the profile cannot enroll a VM, or where the creating session it reads is none or another than the spawner; a call with no session is refused by sminos, since the VM would have no owner. sminos then spawns over ssh and, while the VM answers that it is not enrolled yet, tries again for eleven minutes."
2. "The first version reaches a VM over ssh from a Mac, as `devcloud vm ssh <name> -- sminos spawn` does by hand today." → add: "The call is that command with the task on standard input and one flag, `--asked-from`, carrying a nonce, the asking machine's org, who asked, and the repository the directory was inferred for. The VM's sminos refuses where its machine is not enrolled or is of another org, and where an inferred directory is another repository's checkout; it names the spawner in the new thread's preamble and answers with one line the Mac reads. The VM is the owner's own machine and trusted: the line guards against confusion, and the Mac prints a spawn only on one whole line it can hold to its call, saying otherwise that the outcome is not known. A spawner needs a route back (its machine enrolled, its project one the hub carries). The new thread takes the VM's default reach, so `--on` is refused from a spawner whose own reach is not its machine's default or cannot be resolved, read again before each call to the VM (carrying it is Deferred). `--wait` and `--settings` are refused with `--on`."
3. "Two cases are refused, each naming its reason, and wait for a later design: `--on` asked from a VM …, and `--on` naming a Mac …" → add: "A VM is told by its descriptor file, as devcloud tells one. sminos cannot tell a Mac from any other machine: a name devcloud has no host for gets devcloud's own line, and where the org lists that name as a machine, the Mac's reason is added, worded as a condition. `--on` naming a VM that is not enrolled is refused too: no other machine would see the thread."
4. "devcloud records the creator as it does today, as a tag naming the creating session; D1's naming rule makes that tag a name of the thread, so a VM made before this work is already owned by a thread." → "devcloud records who owns a host as it records its creator today: the session's short id in the provider's label or the adoption record, and on the host a tag of that short id with the owning thread's project, which is where a notice goes on to. D1's naming rule makes the short id a name of the thread, so a VM made before this work is already owned by one."
5. "`devcloud vm owner <vm> <thread>`, a new verb, hands a VM to another thread." → add: "It writes the short id of that thread's current session in each of those places, and on the host the thread's project by its id: the host first, under its send lock and its lifecycle lock, by a program the driver sends (so a host made before the verb takes it), then the label or the record; then it reads both back, and reports a handover only when both name the session it wrote. Between the two writes a retire still refuses the thread that gave the VM up. No lock spans two drivers: two handovers at once are settled by running one again, which the one that wrote last says. A handover redirects the notices of ticks of the host that start after it. It asks sminos which thread a name is (`sminos who --thread`), accepts a thread of the machine it is run on that has not ended, a stopped one included, checks nothing about its caller, and sends no message."
6. "A VM's idle and lease notices are sent from the VM, as today, to the tag of the thread that owns it, which reaches the thread's current session and wakes it if it is stopped." → add: "The tag is resolved on the VM, from the VM's reading of the thread's project log. A notice written before the VM has read a change of session names the session the thread left: it is in the project's log, counted unread for the current session, and not pushed. That is delivery as T1 built it, for any sender whose view lags; the window is seconds while both machines are connected and as long as a disconnect otherwise, and a lease warning can be the notice in it (accepted, the owner told; `docs/doperpowers/TECH-DEBT.md`)."
7. "When that thread cannot be woken, devcloud's order holds as today: the live members of the owning thread's project, then that project's log." → "When the VM's own `say` reports that the thread is held and not woken (for any reason its machine published), has ended, or is no member, the notice goes on: to the live members of the owning thread's project, and when none is live, into that project's log as an untagged note, whatever the first step recorded. The signal is `say --exit-held`, exit 3. A thread whose machine is asleep or not connected is not such a case: the notice is recorded and waits for that machine (nothing publishes presence: Deferred). A host made before this work goes on only for an ended thread or no member, as before."
8. "It is written as it is today, by the VM's own `say` under the VM's human writer, with a marker that says it is a machine's notice; …" → after "a machine's notice": "(the field `notice`, set by `say --notice devcloud`, which a session is refused)".
9. "… **[binding — the owner: "kept, 소유 스레드가 내린다"]**, which is devcloud's default." → "…, which `--on new` asks for (`--keep`): devcloud keeps a VM by default only while the profile sets no `lease_default`."

The EN section:

10. G1's "`--on` from a VM and `--on <a Mac>` are refused, each naming its reason" → add the rest of this plan's acceptance 4 by pointing at it.
11. "From T1 as built: `owned_by` and `owned_vms` (its plan's §7) are the one place sminos runs devcloud" → "… are the one place sminos asks devcloud what a thread owns; `S/sminos_on.py` runs `devcloud vm up` and `devcloud vm ssh`, found by the same finder."
12. Its Status and the Tracking Map's row: this plan's path, and "G1 in flight".

Delegated unknowns, the row "How `--on new` derives the VM's label, project and branch and the new thread's directory": settled by this plan. The label is the alias where it fits devcloud's rule; the project is the spawner's repository as GitHub names it, at the branch of the worktree the command runs in, which origin must hold at that worktree's commit; the directory is the VM's checkout, `~/Developer/GitHub/<repo>`, which the VM holds to that repository; `devcloud vm up` reads none of these from its directory, against the row's lean.

X8: the holder's final wording stands as built (Constraints quotes it). To add: "The writer's side is `sminos say --notice <program>`, a lower-case word of at most 32 characters, refused inside a session; devcloud's hosts pass `devcloud`. The test is `notice_of` in `S/sminos.py`, and the sender string `notice_sender`."

X9:

13. "**Matching.** A host holds its creator's short id and nothing else (the provider label `devcloud-creator`; an adoption record's `creator`)" → "A host holds the short id of the session that made it, or of the current session of the thread it was last handed to (`devcloud vm owner`), in the provider label `devcloud-creator` or an adoption record's `creator`; the command, its reply and the word `creator` in them are unchanged."
14. "`owned_by` is the one function that runs devcloud" → "… the one function that asks this question".
15. "A refusal exits 1 and names each host with what `devcloud vm down` would do to it" → add "and `devcloud vm owner`, which hands it to a thread that stays".

X3, to add: "A sender that passes `say --exit-held` gets exit 3 where a tagged recipient's line is a held one, the message recorded as without it."

Risks, "A VM whose owning thread cannot be woken (a mode that asks, a Mac that is off) …": true of "a mode that asks" from this child on, for a host made with it; not of "a Mac that is off".

**(b) What this plan leaves Deferred, or accepts as a known limit.**

- A thread opened from a VM, and on a Mac: the composite's own Deferred item, unchanged.
- MAWS's endpoint on a machine without the MAWS project: it waits on MAWS publishing its `mawsd` pack as a release artifact, which is the owner's decision and has not been asked.
- Carrying the spawner's reach to the VM: `--on` is refused from a spawner whose reach is not the default, since a wrong carry is a privacy fault and a refusal is not.
- `--wait` and `--settings` with `--on`: each reads something of this machine.
- An addressed event that names a session its thread has left is not pushed, for any sender whose view lags, a VM's notice among them: delivery as T1 built it and the holder's ruling. The event stays in the log, counted unread. The window is seconds while both machines are connected and as long as the disconnect otherwise, and a lease warning, sent once thirty minutes before a VM is deleted, can be what lands in it. Closing it is a milestone of its own if the owner asks; TECH-DEBT.
- A notice to a thread whose machine is asleep or not connected is recorded and waits for that machine, and does not go on: nothing publishes presence (the composite's Deferred). A recorded notice is not a timely one.
- A host made before devcloud 0.18.0 sends its notices unmarked and goes on only for an ended thread or no member: a host keeps the boot library it was built with. A notice is a machine's to its reader only where the reader's sminos is this change's too.
- A host built before its send lock (2026-10-28) can send its former owner one notice after a handover has returned: its lease service reads the descriptor before it sends, and nothing there waits for a handover.
- A host as `vm up` made it names its owner's project by the name `sminos who` prints, where a handover writes the id: ordinary `vm up` is left unchanged. Until a handover, a name two logs of the VM share is refused by `say` as ambiguous, or read as the first of its tiers.
- A host's sminos follows the source its settings declare, which may be pinned: nothing says when a host's copy updates.
- A host built before 2026-10-27 takes a new owner without the project: its parser refuses the key.
- An adopted machine's descriptor holds no project until a handover writes one: `devcloud vm adopt` is not changed here.
- A census older than a handover can let the three-day rule end the thread that just took a VM, for up to an hour (R6: accepted). The VM is not lost, but the thread does not come back by itself when the next census names it: it is reopened by its human, or filled, or the VM is handed on.
- Between the handover's two writes, a retire refuses the thread that gave the VM up and would pass the one taking it; and two handovers at once can leave the two sides naming different threads. Neither is locked against: the verb reads both sides back, says what each holds, and run again it settles.
- A VM made from a session the MAWS app launched is recorded under that session, as `vm up` does today, and nothing guards it: such a session is no thread.
- sminos cannot tell a Mac from another machine, so that refusal is worded as a condition: nothing publishes a machine's kind.
- A thread opened with `--on` is as readable as a default spawn made on the spawner's machine (the whole org reads and messages both), and is owned by the VM's owners, whose words it takes. In an org with more than one owner those may be other people than the owners of the spawner's machine. A known property, not a refusal (MAWS's architect, 2026-11-21).
- `--on new` does not look at uncommitted changes: the VM gets what the pushed branch holds.
- sminos reads two of devcloud's human lines (`<name>  ready in …`, `no VM named …`): each is pinned by a test on devcloud's side.
- After the merge `vm up` takes the slow path until an image is built for the new recipe hash: the scheduled reaper does it within a day.
- `sminos spawn --on new` takes minutes and blocks: the skill has a session run it as a background command.

**(c) Files this plan changes that the sibling child CH1 also changes** (its plan `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md`), and whether the two can be built at once.

| File | What CH1 changes | What this plan changes |
|---|---|---|
| `S/sminos.py` | the predicate and the lookups for a channel, `join`, `view_of`, `lifecycle`, `cmd_say`'s and `_resolve_tag`'s refusals of a channel, `find_target`, `cmd_list`, `member_json`, `build_parser` (the `channel` family, `list --channel`), the help text | `owner_event` and two functions beside it, `cmd_say` and `say_scoped` (a field, an exit), `deliver_say` (what it returns), `frame_of`, `holder_wake`, `chat_line`, `SendDelivery` and where it is pushed, `cmd_who`, `main`, `cmd_spawn`, `spawn_fresh`, `build_parser` (flags on `say`, `who`, `spawn`), the help text |
| `S/sminos_threads.py` | the record's operation for a thread's channels, `update`, `Fold` | `owned_words` |
| `S/CLAUDE.md` | a section for channels | sentences on notices, the handover and `--on` |
| `T/run-sminos-tests.sh` | a part of its own, `channels` | five files added at the end of `run_suites_c` |
| `docs/doperpowers/TECH-DEBT.md` | its rows | its rows |
| `sminos/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | sminos to 1.53.0 | sminos to 1.53.0, devcloud to 0.18.0 |

No function changes meaning for the other child. The one this plan calls and CH1 changes is `find_target`, which CH1 teaches to refuse a name qualified by a channel: `who --thread` then refuses such a name as every verb does. The two shared functions both edit are `cmd_say`, where CH1 adds refusals at its head and this plan a field and an exit at its end, and `build_parser`, in different verbs. CH1 leaves what sessions are taught alone, so the skills and the preamble meet no other hand until CH2.

Judgment: build both at once, on separate branches. This plan keeps its sminos code in a module of its own and touches `S/sminos.py` at named seams for that reason. The overlap is textual, and whichever merges second merges `main` first and takes the next version (both plans say so). If CH1 merges first, this branch merges `main` before its whole-range review, so the review reads the tree that will ship.

**What MAWS does on its side,** after this plan's review, none of it this plan's work and none of it waited for: its endpoint answers `peer` where it would answer `words` for a marked event; its app's channel shows a marked event as that machine's notice; and a vector pins the frame line `[sminos chat <project> <ref> from <program>@<machine>… → @you]`.
