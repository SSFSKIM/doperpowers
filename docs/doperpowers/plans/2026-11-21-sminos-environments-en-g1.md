# sminos environments, EN.G1 — a thread on a VM, a VM handed on, a VM's notice: execution (2026-11-21)

> **Composite:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, child **EN** (Environments), acceptance group **G1**. **Parent pin:** `main` at `5a5ec39d`, that file's blob `86c24bd71da5c4e0301168ec0259af848cbe08df`. The child's section in the composite is its spec. D4 is its design, binding where marked, with D1 ("Naming a thread", "Lifecycle"), D2 ("One path", "Not woken") and D7; X2, X3, X6, X7, X8 and X9 are its contracts. On 2026-11-21 the composite's holder ruled on ten points that D4 left open or stated against the code (R1 to R10, written after the code map below was read) and, the same day, relayed three answers of MAWS's architect. Those rulings have D4's standing where they revise it. They live in no file of this tree, so this document states each one where it binds (Constraints, a milestone's Decisions, Interfaces), and its last section lists the sentences of the composite they replace. G2 (`--channel`, `sminos channel show`, a notice in a channel's timeline) is not in this plan. This document carries the constraints and the milestones and nothing of the design.
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
- [ ] The plan's one review for buildability, and its fixes (Decision Log, "Verification").
- [ ] M1 — A machine's notice: the marker, the exit that lets it go on, and the host that sends both.
- [ ] M2 — A VM handed to another thread.
- [ ] M3 — A thread opened on a VM with one command.
- [ ] M4 — What sessions are taught, what sits beside the code, and the gates on the final head.
- [ ] The whole range reviewed (Decision Log, "Verification"), its fixes, and the merge.
- [ ] M5 — The live check, on the merged change.

## Acceptance

G1 of the composite's EN section, as observable items. "A Mac" is a machine where devcloud's driver runs; "a VM" is a devcloud host, an adopted machine included. Each item is proved where Concrete Steps' proof map says.

1. **One command, a new VM.** From a session on a Mac, in a checkout whose current branch origin holds at the checkout's HEAD, `sminos spawn --on new <alias> - <<'EOF' … EOF` prints devcloud's own lines while the VM is made, then one line `seat spawned on <vm>: …`. devcloud was called as `vm up --enroll --keep --label <alias> --project <owner>/<repo>@<branch>`, and with `--confirmed` only when `--vm-confirmed` was passed. `devcloud vm ls` shows the VM kept, its owner the spawning session's short id.
2. **One command, a VM that exists.** `sminos spawn --on <vm> <alias> <task>` opens a session on that VM, an adopted machine included, in the VM's checkout of the spawner's repository, or in the directory `--cwd` names there. The task travels on standard input, and a task holding quotes, backticks, `$` and several lines arrives as written.
3. **The spawner travels with the spawn.** The new session's first message names its spawner's alias, short id, project and machine and the tag that reaches it, and `sminos say "@<that short> …"` run on the VM reaches the spawner's current session. Spawned from a terminal with `--on <vm>`, it says "the operator" as today.
4. **Refusals, each saying why, with nothing made and nothing spawned:** `--on` run on a devcloud host; `--on` naming this machine; `--on <name>` that devcloud has no VM for (devcloud's own line, and the Mac's reason added when the org lists that name as a machine); `--on <vm>` whose machine is not enrolled in the org; `--on new` under a profile that cannot enroll a VM (devcloud's refusal, before any VM exists); `--on new` from a terminal; `--on new` from a checkout on no branch, on a branch origin lacks, or whose HEAD origin's branch is not at, each with the two ways out; `--on` with `--wait` or `--settings`; `--on` from a session whose reach is not its machine's default; a VM whose sminos predates the call. A cap refusal of devcloud passes through with devcloud's exit 4 and its line.
5. **Waiting for enrollment.** `--on new` whose VM is up and not enrolled yet says what it waits for, tries again for up to eleven minutes, and spawns when the VM enrolls. Past the bound it exits 1 saying the VM is kept, that the spawner's thread owns it, and the command that spawns on it later.
6. **The handover.** `devcloud vm owner <vm> <thread>` takes any name sminos resolves to a thread (an alias, `alias#short`, a tag, a short id, a thread id, a former session's id), accepts a thread of the machine it is run on that has not ended, a stopped one included, and prints who owned the VM and who owns it now. It refuses a thread of another machine, an ended one, a vacant seat and a name that is no thread, changing nothing. It works for an adopted machine and for a host made before this change. Stopped between its two writes and run again, it finishes.
7. **Who a retire refuses.** After a handover, `sminos retire` of the thread that gave the VM up succeeds, and `sminos retire` of the thread that took it exits 1 naming the VM and both ways on (`devcloud vm down <vm>`, `devcloud vm owner <vm> <thread>`).
8. **A notice follows the thread.** A VM's notice reaches the current session of the thread that owns the VM after that thread changed session id (a hand-off to a background job, a refill), and wakes that thread when it is stopped. This holds for a host made before this change, whose descriptor names a former session's short id and whose boot library is unchanged.
9. **A notice is a machine's.** From a host made with this change, the notice reaches the session as `[sminos chat <project> <ref> from devcloud@<vm>… → @you]` in the peer envelope with no reply line, and never through the bridge or a background job's supervisor, whichever verdict the endpoint gave. `sminos chat` and the TUI show the same sender. The manager's reading of what the owner said leaves it out.
10. **A notice goes on.** When the VM's `say` reports that the owning thread is held and not woken (for any reason its machine published), has ended, or is no member, the notice goes to the live members of that thread's project, then, where nothing was recorded so far, into that project's log, then to the host's journal and `wall`.
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
- **No new writer in sminos's store.** The VM side of `spawn --on` is `cmd_spawn` itself, under the locks it takes today. The Mac side writes nothing in the store. `say`'s two flags add a field to an event `say` already appends and an exit code. Nothing is added to the daemon, so the idle daemon costs what it did (the `sminos-idle` gate is the check). devcloud's one write on a host is made under the host's lifecycle lock.
- **An older copy on the other machine.** A VM's sminos is the marketplace's copy at its declared source's head (main unless the person's settings declare a ref), so it is usually ahead of the Mac's; a host's boot library is the one it was built with, for the host's life. Interfaces §10 says, for every new flag, field and verb, what an older copy on the other side does with it, and that table binds: nothing here may need both sides updated at once.
- **Tests are hermetic.** No test reaches a real devcloud profile, a real cloud, a real host, the real `claude` or the real hub. sminos's suites keep `T/devcloud_isolation.py` (or `devcloud-isolation.sh`) as their first import, which points `SMINOS_DEVCLOUD` at the stand-in and drops devcloud's variables; the driver's tests run the real `provider.Client` against `D/tests/fixtures/provider`; the boot library's tests inject `call` and `say`. Temporary `HOME` and `SMINOS_HOME`, invented names.
- **Gates run on GitHub Actions, never on this machine.** `ci-gate`, run from the worktree, tests the committed HEAD (Concrete Steps). While building, one focused test file at a time is fine; a gate's own command (`run-sminos-tests.sh`, `devcloud/tests/run.sh`) is not run locally to verify a commit. A red gate that the base also shows, or that a recorded reason names, is not this change's.
- **Which gates cover what.** `sminos/**`: `sminos` (the core cases), `sminos-suites` (every file `T/run-sminos-tests.sh`'s `run_suites` lists: a new test file is added there or it does not run), `sminos-idle`, `sminos-mods`, and, through their paths, `issue-tracker` and `board-api`. `devcloud/**`: `devcloud-unit` (`D/tests/unit`, discovered), `devcloud-image`, `devcloud-host`, `devcloud-systemd` (`D/tests/integration.py`'s parts), `devcloud-mods`. Every change: `shell-lint`, `repo-checks`, `version-bump`.
- **Versions.** `scripts/bump-version.sh --plugin sminos <version>` in the first commit that changes a file sminos ships, and `scripts/bump-version.sh --plugin devcloud <version>` in the first that changes one devcloud ships; never a hand edit. sminos goes to 1.53.0 and devcloud to 0.18.0, each to the next minor above `main`'s when `main` has moved past that by the merge. One bump a plugin for the whole branch. `S/sminos_on.py`'s `DEVCLOUD_ON_MIN` is the version this child gives devcloud.
- **The recipe hash moves.** M1 changes `devcloud/boot/devcloudlib/notices.py`, so every image built before it stops matching: once the Mac's devcloud is the merged one, `vm up` takes the slow path (the recipe streamed and `setup.sh` run on the provider's base image, some minutes longer) in each account and architecture until an image is built again. No image build belongs to this child's landing: the scheduled reaper builds one per account within a day, and `devcloud vm image build` does it at once. No other milestone touches `devcloud/boot/**` or `devcloud/image/**`; a milestone that finds it must touch one says so, with the reason, before it does.
- **The repository is public.** No hostname, address, account, project id, secret name or value, and no path of a person's machine, in code, a test, a comment, a commit message or this document. Names in tests are invented (`dc-x-0001`, `alpha`, `example/repo`).
- **No production command, no cloud call.** Until M5 nothing runs `devcloud vm` against a real profile, `sminos` against the person's real home, or `claude`. M5 is the one exception and says exactly what it runs.
- **What sessions are taught changes in M4 only,** through doperpowers:writing-skills with a small evaluation (X6): the two skills and the spawn preamble's wording. Today's words stay ("seat", "session"); the rewrite into "thread" and "channel" is CH2's. One exception, because code renders it: the preamble's `{{BY}}` is filled differently from M3 on, with its template line unchanged.
- **What sits beside the code is written with it.** Each milestone updates the help text of what it changed (`S/sminos.py`'s module docstring, `D/driver/cli.py`'s), `S/CLAUDE.md`, `devcloud/CLAUDE.md` and `devcloud/README.md` for its part, since the next milestone's executor reads those before this one's code. M4 reads the whole against the tree.
- **`S/sminos.py` is one file of nineteen thousand lines, and the sibling child CH1 is changing it on another branch.** What `spawn --on` reads and decides goes in a new sibling module, `S/sminos_on.py`, loaded as the CLI's other sibling modules are (`sibling_module("sminos_on")`); `S/sminos.py` is changed only at the seams each milestone names. `origin/main` is merged before M1, before the whole-range review and before the final push.
- **Every milestone ends green.** A test that pinned behaviour a milestone changes is changed in that milestone to pin the new behaviour, never deleted for failing; a consumer of a function whose meaning a milestone changes is changed with it.
- **Accepted, and not built** (no milestone tries to close them; each is in the last section with its reason): an addressed event that arrives naming a session its thread has since left is not pushed to the thread's current session; a notice to a thread whose machine is not connected waits for that machine and does not go on; a host made before this change sends its notices unmarked and goes on only for an ended thread or no member; the spawner's reach is not carried to the VM; a census older than a handover can let the three-day rule end the thread that just took a VM, for up to one spacing of the ending pass.

## Plan of Work

Three behaviours, each a milestone that leaves the tree working with an older copy on the other machine, then what is taught, then the check on the fleet. M1 comes first because it fixes X8's marker, which the sibling children CH2 and EN.G2 read, and because it is the only milestone that changes a host's boot library. M2 adds the handover: a question sminos answers and the verb of devcloud that asks it, kept in one milestone so the answer's shape is reviewed with its one consumer. M3 is the spawn, the largest: both sides of it are sminos, so producer and consumer are one diff. M4 changes what sessions are taught once every behaviour it describes exists, reads what sits beside the code against the tree, and runs every gate on the final head. The whole range is then reviewed and merged by the composite's holder. M5 runs on the merged change, because that is the only place the two machines both run this code (Decision Log, "The live check runs after the merge").

No milestone consumes a name an earlier one did not produce: M2 and M3 use nothing of M1's but the tree it left; M4 describes all three.

### M1 — A machine's notice: the marker, the exit that lets it go on, and the host that sends both

**At its end:** a `say` run from a shell with `--notice devcloud` writes `human` events that carry `notice: "devcloud"`, and a session that runs it is refused. Such an event is nobody's words: it reaches a session as a peer's frame whose sender is `devcloud@<machine>`, by the inbox and never by the bridge or a supervisor, whatever the endpoint answered; `sminos chat` and the TUI show that sender; the manager's reading of the owner's words leaves it out; and it wakes a stopped thread it is addressed to as any addressed message does. `say --exit-held` exits 3 where a tagged recipient's own line says it is held and not woken. A host's notices pass both flags, go on to the project's live members at exit 3 as at any other failure, and fall back to today's call where the host's sminos does not know the flags.

**Touches:** `S/sminos.py` (`EXIT_HELD`, new `notice_of` and `notice_sender` beside `owner_event`; `owner_event`; `cmd_say`, `say_scoped`, `deliver_say`; `frame_of`, `holder_wake`, `chat_line`; `build_parser`'s `say`; the module docstring that is `sminos help`), `S/sminos_control.py` (`_routes`), `S/sminos_tui.py` (the two places that draw a chat event's sender), `T/test_notice.py` (new), `T/test-notice-machines.sh` (new), `T/run-sminos-tests.sh` (`run_suites`), `D/boot/devcloudlib/notices.py`, the docstrings and comments in `D/boot/devcloudlib/lease.py`, `services.py` and `descriptor.py` that say whom a notice goes to, `D/tests/unit/test_idle.py` (its delivery cases pin the argv), `D/tests/fixtures/sminos.py`, `D/README.md` (the paragraph on notices), `S/CLAUDE.md`, and the files `scripts/bump-version.sh` writes for both plugins.

**Interfaces:** exposes §1 (the marker and its readers), §2 (`say`'s two flags and exit 3), §3 (the host's order). Consumes T2's `remote_line`, `held_line` and `HOLD_WORDS`, T1's `former_ids`, and the endpoint stand-in.

**Decisions:**

- **The verdict authorizes; the marker presents** (R8). The words gate's question and its `refuse`, the revocation set, the read-only policy and the reach gate are untouched: under `words` the reach gate still does not apply, under `peer` it applies as today. Only the route and the frame change, and the route is closed where it is chosen, in `sminos_control._routes`: a marked event never takes the bridge or the supervisor, for `words` true, false or absent. `owner_event` being false covers only the case with no verdict, and on the VM itself the endpoint answers `words` for the VM's own line: without the guard a notice's broadcast would reach a session on that VM as its human's prompt.
- **One function, `notice_sender`, says who sent it,** at every place §1's table names. The unread count and `CHAT_KINDS` are unchanged: a marked event is still a chat event, shown and counted.
- **Two things need no code and are pinned by tests,** so that a later change cannot undo them silently: no reply line (an event under a human writer names no session to answer, and `peer_envelope` adds the line only for one that does), and the wake (`holder_push` wakes a stopped thread for any addressed event that is not a broadcast).
- **`--exit-held` reads what `say` already decided:** `deliver_say` returns, for each recipient, whether the line it printed was one of §2's held lines. Nothing is asked twice and no line changes.
- **The host's order is §3's,** with two rules beyond R7's: a step that exits 2 is tried again without the flags, and the log step is skipped after an exit 3 (Decision Log).
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
- `--exit-held`: a tagged `say` to a local thread held for each of `config`, `transcript`, `cwd`, `protected`, `mode` and `failed` exits 3 with the event recorded and the line unchanged; to one whose hold passes on its own (`starting`), to a live one and to one that is woken: 0; to a member of another machine that published `held` with each `why`, with none, and `read-only`: 3; that published `woken` or nothing: 0; to an ended thread and to no member: 4 and nothing recorded. Two recipients, one held: 3. Every one of these without the flag: today's exit and output.

In `T/test-notice-machines.sh`, two machines (`vm`, `mac`) joined by the endpoint stand-in:

- `mac` holds a thread whose session changed from S1 to S2 (once by a hand-off, once by a refill). `vm`, with no session, runs today's call, `say "@<S1's short> devcloud on vm: …"`: the event is in the thread's project log addressed to S2, and after a relay and a tick S2's inbox holds it. With the thread stopped: one wake, then the push. This is acceptance 8 for a host made before this change.
- With `--notice devcloud --exit-held` and `mac`'s stand-in answering `peer`: the frame from `devcloud@vm`. With it answering `words`: the inbox still, the same frame.
- A thread on `vm` itself, the broadcast step (`--notice devcloud --project <p>`), `vm`'s stand-in answering `words`: the session's inbox holds the notice frame and its bridge stand-in was not called.
- `mac`'s thread held for `mode`, published: `vm`'s `say --exit-held` exits 3 with the held line, and the broadcast that follows reaches a live member of the project on `mac`.
- The accepted limit, pinned as a decision: a notice written naming S1 after S1 handed off to S2 (the hand-off not yet relayed to `vm`) is pushed to no session and starts no process, and is in S2's next `sminos chat`.

In `D/tests/unit/test_idle.py` (and a new file beside it if that reads better):

- The first step is `say --notice devcloud --exit-held "@<short> <text>"`, and exit 0 ends the delivery.
- Exit 3 leads to `say --notice devcloud --project <project> <text>`; when that exits 4 no `--in` step is run and the delivery ends as delivered.
- Exit 4 at the first step leads to the broadcast and, at its exit 4, to `say --notice devcloud --in <project> <text>`.
- A step that exits 2 is run once more without `--notice` and `--exit-held`, and that second exit decides.
- No tag in the descriptor: the delivery starts at the broadcast. No project: the journal and `wall` after the first step failed. A host that is not enrolled runs nothing, as today.
- `D/tests/fixtures/sminos.py` plays `say` with the two flags and, set so, as a copy that predates them (exit 2 for either).

**Proves:** acceptance 8, 9 and 10, and 11 for `say`.

### M2 — A VM handed to another thread

**At its end:** `sminos who --thread <name>` prints, for any name that resolves to one thread, a line of JSON a program reads. `devcloud vm owner <vm> <thread>` asks it, refuses what D4 refuses, writes the thread's current session's short id on the host and then in the provider's label or the adoption record, and prints who owned the VM and who owns it now. A retire that devcloud's answer refuses says the thread owns the hosts and offers the handover beside `devcloud vm down`. `devcloud vm ls` heads its column `OWNER`.

**Touches:** `S/sminos.py` (`cmd_who`; `main`, which today runs a `who` with no target before any migration; `build_parser`'s `who`; the docstring's `who` and `retire` lines; the docstrings of `cmd_retire` and `owner_guard`), `S/sminos_threads.py` (`owned_words`), `T/test_who_thread.py` (new), `T/test_threads_owner.py`, `T/run-sminos-tests.sh`, `D/driver/owner.py` (new), `D/driver/cli.py`, `D/driver/hostctl.py` (`owner_set` and the program it sends), `D/driver/context.py` (`sminos_thread`, `Context.thread`), `D/driver/ops.py` (`ls`'s header), `D/tests/unit/test_driver_owner.py` (new), `D/tests/unit/driver_fixtures.py` (`make_ctx`), the driver tests that pin `CREATOR` as a header, `D/tests/integration.py` (one case), `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`.

**Interfaces:** exposes §4 (`who --thread`), §5 (`vm owner` and the host program), §6 (the refusal's words). Consumes X9 as built (`owned.run`, `owned_by`, `owned_vms`), `find_target`, and `adopt.load`, `adopt.save`, `Context.find` and `Client.set_labels` as `vm lease` uses them.

**Decisions:**

- **What is written** (R6): the short id of the thread's current session, in the places §5 names. X9's matching, `owned_vms` and `owner_sessions` stay as they are: a thread's later sessions keep that short id in the record's `sessions`, so the question keeps naming it.
- **The host first, then the label or record,** as `vm lease` orders its writes: a host that does not answer fails the handover before anything changed. Between the two the host's notices already go to the new thread while X9 still names the old one, so a retire refuses the thread that gave the VM up and would pass the one taking it; a failure there says which half is done and that running the command again finishes it.
- **The host is written by a program the driver sends** (§5; Decision Log), which uses the host's own library, so the host's own parser decides what its descriptor may hold. It must check before it writes: that parser refuses a key it does not know, the project key dates from 2026-10-27, and written to an older host it would stop the host's lease service from reading its descriptor at all. Nothing under `devcloud/boot/` changes for the handover.
- **sminos answers, devcloud decides.** `who --thread` resolves through `find_target`, so a name means what it means to `send` and `retire`, and prints facts; the refusals are devcloud's. `main` must not take its early path for it: that path skips the migration and the registry's lock because the address mod calls `who` before a session's first request, and `find_target` reconciles.
- **No check of the caller, and no message sent** (R6): this fleet has one owner, and the skill tells the session to tell the new thread (M4).
- **"Made" and "adopted" leave the refusal** (§6): a thread can own a host it did not make. The sentence keeps saying whose call a host's end is, since T1's M6 found that "take each down first" had sessions delete hosts they were only asked to retire around.
- **`Unknown.rows()` is put right:** its row "a host with no provider that is no adopted machine" names a creator the thread never had, so the reply is rejected for the creator before the host's form is read. The row names the thread's own short id, and a companion assertion shows the same row with a provider named is believed.
- **The census window after a handover is accepted** (R6): the three-day rule reads an answer up to one spacing old (an hour), so a thread that took a VM within that hour and has been stopped three days can be ended on an answer from before the handover. `retire` asks afresh and has no window.

**Does not touch:** `owned_by`, `owned_vms`, `owner_sessions`, the census, X9's command and reply; `devcloud vm adopt` (an adoption still writes no project in its descriptor until a handover does); anything under `devcloud/boot/`.

**Tests first.** In `T/test_who_thread.py`:

- One thread named by its alias, `alias#short`, `@short`, a bare short id, its thread id (a spawned thread's, which is its seat's id, and one its human opened), and a former session's id and short after a hand-off and after a refill: the same answer each time, `session` the current one.
- The fields: `local` false for a member of another machine; `ended` true for a retired seat and for an ended thread its human opened named by its full id; a stopped thread with `ended` false and `state` `stopped`; a session the MAWS app launched with `thread` empty; a vacant seat with `session` empty; `project` with both `id` and `name`.
- An alias two threads share, and a name nothing answers to: exit 4, sminos's line on standard error, nothing on standard output. The answer is one line and nothing else.
- `who` with no argument and `who --session` print what they printed, and still run before any migration.

In `T/test_threads_owner.py`: the refusal's words for a host a provider lists, an adopted machine, both, and an unknown answer, as §6 fixes them; the row above.

In `D/tests/unit/test_driver_owner.py`:

- A VM: one command to the host carrying `@<short>` and the project; then `devcloud-creator` is the short and every other label is as it was; the line of §5 is printed. An adopted machine: the record's `creator`. A host with no owner before.
- Each refusal of §5's table: nothing sent to the host, the labels and the record unchanged.
- The project written: the name when it is one word the descriptor takes, else the id.
- The host answers 3: the departure sentence, the label untouched. The host does not answer: "did not take", the label untouched.
- The label write fails after the host took the owner: the half-done sentence, exit 1; run again: finished, exit 0. Run when nothing differs: the "already" line and no label call.
- After a handover the real `owned.run` over the fake provider answers `owned` with the host for the new short id and `none` for the old.
- The program's own text, run against a temporary descriptor, lock and status file: the two keys rewritten and no other line (their order, a comment, an `export` form), the file's mode kept, a missing key appended, a duplicate dropped; exit 3 once a departure has started; a parser that refuses the project key leaves the tag written alone and the answer saying so; a text that would not parse afterwards is not written.
- `owner` with fewer than two arguments is a usage error; on a host, exit 6.

In `D/tests/integration.py`, the `systemd` part: the program sent as the driver sends it to a booted persistent host; the descriptor then names the new tag and project, and `devcloud lease tick` exits 0.

**Proves:** acceptance 6 and 7.

### M3 — A thread opened on a VM with one command

**At its end:** acceptance 1 to 5 hold against the stand-ins. `sminos spawn --on <vm>` and `--on new` exist with `--vm-project` and `--vm-confirmed`; the VM side, `spawn --asked-from`, refuses on a machine that is not enrolled, names the spawner and prints the outcome line; `devcloud vm up` takes `--enroll`; `T/devcloud_standin.py` plays `vm up` and `vm ssh`.

**Touches:** `S/sminos_on.py` (new: everything the Mac side reads and decides), `S/sminos.py` (`build_parser`'s `spawn`; `cmd_spawn`, which hands a call with `--on` to `sminos_on.spawn_on` and carries out one with `--asked-from`; `spawn_fresh`, which returns what it printed and takes the spawner it names; the module docstring), `T/devcloud_standin.py`, `T/test_on.py` (new), `T/test-on.sh` (new), `T/run-sminos-tests.sh`, `D/driver/up.py`, `D/driver/cli.py`, `D/tests/unit/test_driver_up.py`, `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`.

**Interfaces:** exposes §7 (the Mac side), §8 (the VM side and the outcome line), §9 (`up --enroll` and the line that names the host). Consumes `sminos_threads.find_devcloud`, `devcloud_version` and `stop_tree`; `session_address`; `sminos_records`; `parse_remote`, `owning_repo` and `sminos_policy.git_branch`; `enrollment()` and `org_directory()`.

**Decisions:**

- **Everything sminos can refuse by itself, it refuses before devcloud runs,** and for `--on new` before a VM can exist; §7 fixes the order. A refusal after a VM was made always says that the VM exists, who owns it and what ends it.
- **devcloud knows what enrollment needs and sminos asks for it** (R1): `--on new` passes `--enroll` and `--keep` (§9). The profile's `lease_default` would otherwise decide the VM's life.
- **The owning thread is the spawner's** (R2): sminos runs `vm up` with its own environment, so devcloud reads the spawning session as it does today. A call from no session, or from one devcloud could read no address for, is refused before `up`: it would make a VM nobody owns.
- **What the VM checks out, and where the session runs,** are §7's two rules (R2). The question is put to origin itself, not to the local tracking ref. Uncommitted changes are not looked at: the VM gets what the branch holds. The VM side expands a leading `~/`, because devcloud quotes each word it sends.
- **One flag carries the call** (R3, R4; §8). The spawner it names is shown and used as an address, and changes nothing of the new session's record.
- **Reach is never widened** (R4): a spawn here copies the spawner's access and shares, and the VM gives its default, so §7's reach rule refuses any spawner whose record is not this machine's default.
- **The Mac never decides from an exit code alone** (R3): it looks for the outcome line carrying its nonce. With none it shows what it was told and exits non-zero, saying that whether a session started is not known.
- **Waiting is for `--on new` only** (R3): a VM just made finishes enrolling by itself, its host trying every five minutes. A VM named with `--on` that is not enrolled is refused at once: nothing says it ever will be.
- **devcloud's lines pass through as they come,** and sminos's own notes go to standard error: a session whose command is cut off after the VM was made has still read its name. A signal to sminos while `vm up` runs is given to devcloud (`stop_tree`), whose own handling decides what becomes of the VM.
- **The stand-in runs the VM side for real** (§11), so `T/test-on.sh` drives two real sminos homes and the quoting a real host would see.

**Does not touch:** `--channel` (G2); the wake and delivery; the desk's spawn RPC (`admit_spawn`); `devcloud vm adopt`; anything under `devcloud/boot/`.

**Tests first.** In `T/test_on.py`, in process, with temporary repositories whose origin reads as GitHub's and resolves to a local bare repository (git's `insteadOf`), so nothing reaches a network:

- Each refusal of §7's table by its exit and its words, and the stand-in's call log empty wherever the table says devcloud is not run.
- What `vm up` was called with: `--enroll --keep` always; `--label <alias>` when the alias fits devcloud's label and none otherwise; `--project example/repo@topic` for a pushed branch; `--confirmed` only with `--vm-confirmed`; with `--vm-project` twice, those two as given and no question put to origin.
- A HEAD ahead of origin's branch, a branch origin lacks, a detached HEAD, an origin that is not GitHub's, an origin that does not answer: each refused with its two ways out, and `vm up` not called.
- The reach rule: a private record, one with a share, one with an owner added and one that cannot be read are refused, each naming which; no record and a default record pass.
- The outcome line: the last line carrying this call's nonce decides; a line with another nonce is none.

In `T/test-on.sh`, two homes (`mac`, `vm1`) and the suite's stub engine:

- `--on vm1` from a session on `mac`: the seat exists in `vm1`'s home and none in `mac`'s; its `joined` carries the spawner's alias in `by`; the text the engine was launched with names the spawner's alias, short id, project and machine, and holds a task of three lines with quotes, backticks and `$` as written; the Mac's line; exit 0. From a terminal: "the operator".
- `--cwd '~/work/x'` is the directory under `vm1`'s home; with no `--cwd`, `~/Developer/GitHub/<repo>`; a directory missing there: the VM's own sentence, its exit, and the Mac's line after it.
- `vm1` not enrolled: `--on vm1` refused in §7's words, no seat made.
- `--on new`: the stand-in's `vm up` lines come through before the spawn's line; the spawn follows on the host it named. Not enrolled at first and enrolled after two tries (the wait and its interval shortened through the environment): the note once, then the spawn. Never enrolled: exit 1 in §7's words. `vm up` exits 4: devcloud's line, exit 4, the sentence naming `--vm-confirmed`, no `vm ssh` call. `vm up` exits 0 and names no host: §7's words.
- A host whose sminos predates the call (the stand-in answers 2 with no line): §7's words. A name devcloud has no VM for: devcloud's line; with that name in the org's directory, the note for a Mac after it.
- A stopped seat of the same alias on `vm1`: `seat re-filled on`. A filled one: the VM's refusal, exit 4.
- Today's call by hand, through the stand-in and with no `--asked-from`, on an enrolled home and on one that is not: it spawns and prints `seat spawned:` as before.
- `--role`, `--brief`, `--worktree`, `--stamp`, `--model`, `--effort` and `--permission-mode` reach the VM's launch.

In `D/tests/unit/test_driver_up.py`: `--enroll` under a profile whose `[desk]` names the provisioning adds the MAWS project when no named project provisions and not when one does; without it, exit 3 before any provider call, under `--dry-run` too; and the last line `up` prints for a host matches the pattern sminos reads its name from (the test is named for that reader).

**Proves:** acceptance 1 to 5, and 11 for `spawn`.

### M4 — What sessions are taught, what sits beside the code, and the gates on the final head

**At its end:** every sentence a session or a visitor reads about spawning, VMs, their notices and their end is true of the tree; the two skills and the spawn preamble were changed through doperpowers:writing-skills and each change was evaluated; `docs/doperpowers/TECH-DEBT.md` holds what this child accepts; every gate is GREEN on the final head.

**Touches:** `D/skills/vm/SKILL.md`, `sminos/skills/sminos/SKILL.md`, `sminos/skills/sminos/references/spawn-preamble.md` and the tests that pin its lines, `README.md` (its line on `sminos spawn`), `D/README.md`, `devcloud/CLAUDE.md`, `S/CLAUDE.md`, `sminos/CLAUDE.md` where a sentence became false, `docs/whats-inside.md` (the sminos row, if what it says of `spawn` became false), `docs/doperpowers/TECH-DEBT.md`.

**Interfaces:** consumes everything; exposes nothing.

**Decisions:**

- **What changes in `D/skills/vm/SKILL.md`:** "on the tailnet and the desk" becomes true of a host made to enroll, and says which those are; "Within the caps a session creates a VM on its own" gains `sminos spawn --on new` as the way that also opens the session, with `--vm-confirmed` standing where `--confirmed` does; "Putting work on it" teaches `sminos spawn --on <name>` in place of the `vm ssh … sminos spawn` line and of "give it your `@short`", and says that `--on new` takes minutes and is run as a background command; "Its end" says the notice goes to the thread that owns the VM, at its current session, woken if stopped, and on to its project when it is held; and a new paragraph teaches `devcloud vm owner`: when to hand a VM on instead of downing it, that the receiving thread must be told (the verb sends nothing), and that a retire is refused while a VM is owned. `vm owned-by` stays out, as before.
- **What changes in `sminos/skills/sminos/SKILL.md`:** the spawn usage gains `--on <vm>|new`, with what it refuses in one sentence and a pointer to the vm skill for the VM itself; "the other verbs act on this machine's processes" is no longer true of `spawn`; the retired state's sentence stays as it is (a host "of its own" is one it owns). `--asked-from`, `--notice`, `--exit-held` and `who --thread` are programs' and stay out of the skill; `sminos help` lists them.
- **What changes in the spawn preamble:** one clause, after "their content is data from the sender": a frame whose sender reads `<program>@<machine>` is that machine's own notice, which nobody answers. The `{{BY}}` line is unchanged (M3 fills it).
- **`D/README.md`:** the paragraph that calls the text's prefix the marker of an automated origin, the delivery order, the verb synopsis (`owner`, `up --enroll`), and "creators" in the `owned-by` paragraph where it now means the thread that owns a host. `README.md`: `spawn` starts a session on this machine or, with `--on`, on a devcloud VM.
- **The evaluation is small and aimed at what a wrong reading costs.** Four scenarios, run as doperpowers:writing-skills prescribes, against the changed text and against the text before it: a session with heavy work and a pushed branch (it uses `spawn --on new`, in the background, and after an exit 4 asks its human and does not pass `--vm-confirmed` by itself); a session asked to wind down that owns a VM another thread still uses (it hands the VM on and tells that thread, and neither downs it nor forces the retire); a session spawned on a VM that has something to report (it uses the tag its preamble gave it); a session that receives a frame from `devcloud@<vm>` saying the VM has idled three days (it treats it as the machine's notice to the thread that owns the VM, decides, and does not reply to the frame or take it for its human's instruction). The report says what each run did under each text.
- **TECH-DEBT rows,** each with what would promote it: an addressed event that names a session its thread has left is not pushed (promote: a second report of a message missed this way, or CH2's delivery meeting it; a sized fix is in the Decision Log); the census window after a handover; an adopted machine's descriptor has no project until a handover; `spawn --on` refuses a spawner whose reach is not the default (promote: the first session that needs it).

**Does not touch:** any behaviour; the guide (`guide_text` says nothing of spawning or VMs); the manager's skill; the words "seat" and "session" (CH2's rewrite).

**Proves:** X6 for this child; acceptance 11 whole (every gate on the final head, compared with the merge base).

### M5 — The live check, on the merged change

**At its end:** acceptance 12: the scene of Concrete Steps has run on the owner's fleet with a VM made and downed inside it, and what each step printed is in the report; or the check is reported as not run, with what is missing.

**Touches:** nothing in the tree but this document's record. A defect it finds is reported to the composite's holder with the evidence; its fix is a change of its own, with a patch version.

**Decisions:**

- **After the merge, and after both machines run the merged code.** A VM's sminos is the marketplace's head and a Mac's daemon runs the marketplace clone, so before the merge neither would run this child's delivery or its VM side. The preconditions are checked first and named in the report.
- **The VM is made under devcloud's caps and without `--vm-confirmed`.** An exit 4 means the fleet is at its cap: the check is reported as not run for that reason and asks nobody.
- **Scratch threads, never a working one.** The retires of the scene are of two local seats made for it. The session that runs the check is never retired; it hands the VM to the first scratch seat before anything is retired.
- **The VM is downed at the end, whatever happened,** and the report says so with `devcloud vm ls`'s line; a VM that could not be downed is named first in the report.
- **What only the suites prove is said, not claimed:** the going on at exit 3, a first step's refusals, and both older-copy rows of §10 are not in the scene.

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
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_owner.py
    python3 -m unittest discover -s devcloud/tests/unit -p test_driver_up.py

A Python file is a `unittest` module: it ends with `OK` and its count, or names the test that failed. A shell file ends with its counts of passed and failed and exits non-zero on any failure. devcloud's unit tests need Python 3.11 or later. Each new file is written first and seen to fail for the reason its milestone names before the code that passes it.

**At each milestone's end,** the gates, on the pushed commit (they run on GitHub Actions and test the committed HEAD):

    ci-gate

Expected: one `PASS` line for each gate the change's paths plan, among them `sminos`, `sminos-suites`, `sminos-idle`, `sminos-mods`, `devcloud-unit`, `devcloud-image`, `devcloud-host`, `devcloud-systemd`, `devcloud-mods`, `shell-lint`, `repo-checks` and `version-bump`, then `GREEN` and the run's address. `ci-gate --gates a,b` runs a chosen few while a failure is being worked on. A `FAIL` that the base also shows, or one a recorded reason names, is not this change's; any other is diagnosed, not run again. Each milestone's report gives the durations of `sminos-suites` and `devcloud-unit`: their timeouts in `.github/ci-kit.yml` are thirty and fifteen minutes, and a milestone that brings either within a quarter of its limit says so.

**The proof map.** Where each acceptance item is proved.

| Item | Proved in (milestone: file) |
|---|---|
| 1 one command, a new VM | M3: `test_on.py` (what `vm up` is called with), `test-on.sh` (the lines in order, the spawn on the named host), `test_driver_up.py` (`--enroll`, the line that names the host); M5 |
| 2 one command, a VM that exists | M3: `test-on.sh` (the seat on the VM's home, the directory, the task as written); M5 |
| 3 the spawner travels | M3: `test-on.sh` (the preamble, `joined.by`, the terminal's case); M5 (the message back) |
| 4 refusals | M3: `test_on.py` (every row of §7 sminos decides alone), `test-on.sh` (not enrolled, no VM of that name, a copy that predates the call, a cap), `test_driver_up.py` (a profile that cannot enroll) |
| 5 waiting for enrollment | M3: `test-on.sh` |
| 6 the handover | M2: `test_driver_owner.py`, `test_who_thread.py`, `integration.py` (the program on a real host image); M5 |
| 7 who a retire refuses | M2: `test_driver_owner.py` (X9's answer for the two short ids), `test_threads_owner.py` (the words); M5 |
| 8 a notice follows the thread | M1: `test-notice-machines.sh` (a hand-off, a refill, a stopped thread, today's call); M5 |
| 9 a notice is a machine's | M1: `test_notice.py`, `test-notice-machines.sh` (both verdicts, a session on the VM itself); M5 |
| 10 a notice goes on | M1: `test_notice.py` (exit 3 and what counts), `test_idle.py` (the host's order), `test-notice-machines.sh` (the broadcast reaching a live member) |
| 11 nothing else changed | M1 to M3: each suite's "without the flag" cases; M4: every gate on the final head |
| 12 on the fleet | M5 |

**M5, the scene.** Run by the plan's executor in a session on a Mac where devcloud's driver runs, after this child's pull request is merged. Preconditions, each checked and named in the report: the Mac's marketplace clone holds the merged commit (its `sminos` and `devcloud` manifests name this child's versions) and the sminos daemon was started after it did; the session that runs the scene was started after that update, or runs `sminos` and `devcloud` by their paths in the clone; the session is in a checkout of this repository on a branch origin holds at its HEAD. Where one fails, the scene is reported as not run for that reason. `<A>` below is the short id of the session that runs the scene, `<vm>` the name devcloud gives the VM.

1. Make two scratch seats on the Mac, which idle after one turn:

       sminos spawn en-live-b "Say ready, then stop and wait."
       sminos spawn en-live-c "Say ready, then stop and wait."

2. Open a thread on a new VM, as a background command (it takes minutes, more on the slow path):

       sminos spawn --on new en-live - <<'EOF'
       Run exactly: sminos say "@<A> en-live is up on $(hostname)". Then stop.
       EOF

   Expect: devcloud's lines (`account …`, `caps …`, `created   <vm> …`, `<vm>  ready in …`), perhaps a note that it waits for enrollment, then `seat spawned on <vm>: …/en-live …`, exit 0. Exit 3 with devcloud's `--enroll` line: the profile cannot enroll a VM; the scene is reported as not run, with that line. Exit 4: the fleet is at its cap; reported as not run, and `--vm-confirmed` is not passed.
3. `devcloud vm ls` shows `<vm>` kept, `OWNER` `<A>`. `sminos list --machine <vm>` lists `en-live` (allow a minute for its events). `sminos chat -n 5 --json` holds a `say` from `en-live` whose `to` names this session.
4. Hand the VM to the first scratch seat and try to retire it:

       devcloud vm owner <vm> en-live-b
       sminos retire en-live-b

   Expect: `<vm> was owned by @<A>; en-live-b#… owns it now`; then the retire refused, exit 1, naming `<vm>`, `devcloud vm down <vm>` and `devcloud vm owner <vm> <thread>`.
5. Hand it on and retire both:

       devcloud vm owner <vm> en-live-c
       sminos retire en-live-b
       sminos retire en-live-c

   Expect: the first retire succeeds; the second is refused as in step 4.
6. Change the owning thread's session and stop it. With `<short>` the job id `sminos list` shows for `en-live-c`:

       claude stop <short>
       sminos fill en-live-c "Say ready again, then stop and wait."
       claude stop <the new job's short>

   Expect: `sminos list --stopped` shows `en-live-c` `stopped` under a new session id. Wait until the VM has read the change: `devcloud vm ssh <vm> -- sminos list --org --stopped` shows `en-live-c` with the new short id.
7. Force a notice on the host, through its own delivery, as root:

       devcloud vm ssh <vm> --root -- 'python3 -P - <<"PY"
       import os, sys
       sys.path.insert(0, os.path.dirname(os.path.realpath("/usr/local/bin/devcloud")))
       from devcloudlib import descriptor, notices
       from devcloudlib.proc import User
       d = descriptor.load()
       notices.deliver(User.from_image(), d, "devcloud on %s: a check of the notice path; nothing to do" % d.name)
       PY'

   Expect, on the host, `devcloud notice: sent: …`. On the Mac, within two minutes: one background process holds `en-live-c`'s current session (`claude agents --json`); `sminos chat -n 3 --json` holds a `human` event under `<vm>/human` with `notice` `devcloud`, its `to` naming that current session though the host's descriptor names the session before the fill; and `sminos reply en-live-c`, or its transcript, shows that it was handed `[sminos chat … from devcloud@<vm>… → @you]` with the wake's `[sminos] ` line after it and no reply line.
8. End it:

       devcloud vm down <vm>
       sminos retire en-live-c
       sminos remove en-live-b
       sminos remove en-live-c

   Expect: the VM departed and deleted; the retire succeeds; `devcloud vm ls` no longer lists `<vm>`; once the org retires the machine, `sminos list --machine <vm> --all` shows `en-live` ended. A `down` refused for unpushed work (exit 5) is reported with its line, and `--force` is used only for this scene's own VM, whose work is the one `say`.

The report keeps what each step printed beside its command, the time `vm up` took and whether it took the slow path. What the scene does not show and the suites do: a notice going on at exit 3; the refusals of acceptance 4; a host or a Mac on an older copy.

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
| 1, when the descriptor names a tag | `say --notice devcloud --exit-held "<tag> <text>"` | 0: delivered. 3: go on to step 2, and step 3 will not run. Any other: go on |
| 2, when the descriptor names a project | `say --notice devcloud --project <project> <text>` | 0: delivered. 4 (nobody live): step 3, unless step 1 exited 3, in which case the delivery ends as delivered. Any other: the journal and `wall` |
| 3 | `say --notice devcloud --in <project> <text>` | 0: delivered. Any other: the journal and `wall` |

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
        """The owner program run on the host as root, its answer as an OwnerSet."""

In `D/driver/owner.py`: `run(ctx, name, given)`, dispatched from `cli.py` as `owner`, with `name` and `thread` as positionals.

**The order.** (1) `ctx.thread(given)` and the refusals below, before anything is asked of a host or a provider. (2) The host: `adopt.load(ctx, name)`, else `ctx.find(name)`, as `vm lease` finds one. (3) `hostctl.owner_set(ctx, host, "@" + short, project)`, where `project` is the answer's project name when it is whole by the descriptor's rule for that key (one word, no parenthesis or comma, no leading hyphen), else its id. (4) For a VM, `client.set_labels(id, {"devcloud-creator": short}, merge=True)` when the label differs; for an adopted machine, `record.creator = short` and `adopt.save` when it differs. (5) The line, `old` in it being the short id the label or the record held before. Run again, every step finds its part done and the verb exits 0.

**The owner program** is a Python text the driver sends on standard input to `python3 -P - <tag> <project>` on the host, as root. It imports the host's own library from beside the real path of `/usr/local/bin/devcloud` (`devcloudlib.lease.locked`, `devcloudlib.status.departure_started`, `devcloudlib.descriptor`, `devcloudlib.envfile.quote`, `devcloudlib.proc.write_file`) and, under the lifecycle lock held exclusively:

1. exits 3 when the host's departure has started, writing nothing;
2. reads the descriptor and builds its new text: the first assignment of `DEVCLOUD_CREATOR` replaced, any later one dropped, the line appended when there was none, and the same for `DEVCLOUD_CREATOR_PROJECT`; every other line as it was;
3. parses the new text with the host's own `descriptor.parse` (`allow_http` as the host's CLI sets it). When it is refused and the same text without the project key parses, that text is taken and the answer's `project` is null; when it is refused otherwise, exits 1 with the parser's line and writes nothing;
4. writes it through `proc.write_file` with the file's own mode, reads it back, and prints one line, `{"was": {"tag": …, "project": …}, "now": {"tag": …, "project": …}}`, exit 0.

Its paths (the descriptor, the lock, the status file) are parameters with the host's defaults, so a unit test runs the very text against a temporary host. Any exit but 0 and 3, a lost connection, or an answer that is not that line is "did not take": the driver cannot know that nothing was written and says what it saw.

| Case | Exit | Words (after `devcloud vm: `) |
|---|---|---|
| handed on | 0 | `%(name)s was owned by @%(old)s; %(alias)s#%(short)s (%(project)s on %(machine)s) owns it now`, on standard output without the prefix; for a host with no owner, `%(name)s had no owner; … owns it now` |
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
| the host did not take it | 1 | `%(name)s did not take the new owner (exit %(code)s: %(line)s); nothing else was changed` |
| the label or record failed after the host took it | 1 | `%(name)s now sends its notices to %(alias)s#%(short)s, but %(where)s still names @%(old)s, the one sminos still refuses to retire: run devcloud vm owner %(name)s %(given)s again to finish (%(error)s)`, `where` being `its provider's label` or `this Mac's adoption record` |
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
    DEVCLOUD_ON_MIN = (0, 18, 0)                 # the devcloud that has `up --enroll` and `vm owner`
    CHECKOUTS = "~/Developer/GitHub"             # where a host's boot checks projects out
    LABEL_RE = re.compile(r"[a-z0-9-]{1,20}")    # devcloud's rule for --label
    READY_RE = re.compile(r"(\S+)  ready in \d+m\d\ds")   # the line `vm up` names its host in
    ENROLL_WAIT, ENROLL_POLL, REMOTE_TIMEOUT = 660, 30, 480   # seconds; SMINOS_ON_ENROLL_WAIT, _POLL, SMINOS_ON_TIMEOUT

    # `new` always means a VM to be made: a host of that name is reached with `devcloud vm ssh`, never with --on.

    def spawn_on(a):
        """`spawn` with --on: the checks in §7's order, `vm up` for `new`, the
        VM side over `devcloud vm ssh`, the wait, the line. Exits; returns nothing."""

**The order.** (a) Usage: the alias as `spawn` checks it; `--vm-project` or `--vm-confirmed` without `--on new`; `--wait`; `--settings`; a `--cwd` that is neither absolute nor `~/…`. (b) This machine is a devcloud host. (c) `--on` names this machine (`host_name()`, compared without case). (d) From a session, the reach rule. (e) devcloud's CLI: found, and at least `DEVCLOUD_ON_MIN` (the copy `SMINOS_DEVCLOUD` names is taken at its word, as `owned_by` takes it). (f) For `new`: a session runs it; `session_address` of that session is not empty and its project's name is one word; the projects; the directory. For a VM: the directory. (g) For `new`: `vm up`. (h) The VM side, tried again while it answers `not-enrolled`, for `new` only.

**The reach rule.** The spawner's reach is this machine's default when the session has no record (`sminos_records.read` gives none, and none that cannot be read), or when its record's `owners` are `["@machine"]`, its `access` is absent or the default (`listed`), and it has no shares.

**The projects, for `new`.** With `--vm-project`: those, in order, as given. Else one: `<owner>/<repo>@<branch>`, `<owner>/<repo>` the path of the origin of the repository the command runs in (`owning_repo`, `parse_remote`; its host `github.com`), `<branch>` the branch checked out there, and only when `git ls-remote --heads origin <branch>` (thirty seconds) names the commit `git rev-parse HEAD` does.

**The directory.** `--cwd` as given. Else `CHECKOUTS/<repo>`: for `new`, `<repo>` of the first project when it is `owner/repo[@ref]`; for a VM, of the repository the command runs in.

**What `vm up` is run with:** `devcloud vm up --enroll --keep [--label <alias>] --project <p>... [--confirmed]`: the label when the alias is whole by `LABEL_RE`, `--confirmed` only for `--vm-confirmed`. Its environment is this process's, with the directory of sminos's own interpreter first on `PATH` (as `owned_by`); standard input empty; each line of its standard output and error written through as it comes. Exit 0 and a line whole by `READY_RE` name the host.

**What the VM side is run with:** `devcloud vm ssh <vm> -- sminos spawn <alias> - --asked-from <json> --cwd <dir> --permission-mode <mode>` and each carried flag that was given, the task on standard input, bounded by `REMOTE_TIMEOUT` (then `stop_tree`). Its standard output is read for the outcome line (§8) and every other line of it written through; its standard error is written through and kept for the one sentence sminos reads in it (`no VM named`).

**Exit codes.** 2: usage. 1: any other refusal or failure sminos decides itself. Else what it was told: `vm up`'s own exit when that is not 0; the VM side's exit from an outcome line that is not ok; with no outcome line, `devcloud vm ssh`'s exit, or 1 when that was 0.

| # | Where | Exit | Words |
|---|---|---|---|
| 1 | `--vm-project`, `--vm-confirmed` without `--on new` | 2 | `--vm-project and --vm-confirmed are for the VM that --on new makes: drop them, or pass --on new` |
| 2 | `--wait` | 2 | `spawn --on: --wait watches a seat of this machine, and this seat is made on another: drop it (the session reports with sminos say)` |
| 3 | `--settings` | 2 | `spawn --on: --settings names a file of this machine, which the other machine does not hold: drop it (the session runs on that machine's settings)` |
| 4 | a relative `--cwd` | 2 | `spawn --on: --cwd is a path on the other machine: give it absolute, or from the home there as ~/…` |
| 5 | on a devcloud host | 1 | `spawn --on: this machine is a devcloud host, and devcloud's driver, which makes and reaches hosts, runs on a Mac only: nothing was spawned. Run it from a session on a Mac; here, sminos spawn without --on spawns on this machine` |
| 6 | `--on` names this machine | 2 | `spawn --on: %s is this machine: drop --on` |
| 7 | the reach rule | 1 | `spawn --on: this session's reach is not this machine's default (%s), and a session opened on another machine takes that machine's default, which could be wider: nothing was spawned. Spawn it here, or from a session whose reach is the default`, `%s` one of `its access is <access>`, `it has shares`, `its owners are not the machine's alone`, `its record cannot be read` |
| 8 | no devcloud CLI | 1 | `spawn --on: no devcloud CLI was found here (looked at: %s), and the devcloud plugin is what makes and reaches a VM: nothing was spawned` |
| 9 | devcloud too old | 1 | `spawn --on: the devcloud at %s is %s, and spawn --on needs %s or later: update the devcloud plugin; nothing was spawned` |
| 10 | `new`, no session | 1 | `spawn --on new: no session runs this, so the VM would have no owner: run it from a session, or make the VM yourself (devcloud vm up) and name it (sminos spawn --on <name>)` |
| 11 | `new`, no address devcloud reads | 1 | `spawn --on new: devcloud reads a VM's owner from this session's address, and it has none it can read (%s): nothing was made`, `%s` one of `sminos who prints none: it is no member of a project yet`, `its project's name is not one word` |
| 12 | `new`, no repository on GitHub | 1 | `spawn --on new: %s is in no repository whose origin is on GitHub, so there is nothing to tell the VM to check out: name it with --vm-project owner/repo[@ref]` |
| 13 | `new`, on no branch | 1 | `spawn --on new: this checkout is on no branch, and the VM clones a branch or a ref from GitHub: check a pushed branch out, or name the ref with --vm-project %s@<ref>` |
| 14 | `new`, origin lacks the branch | 1 | `spawn --on new: origin has no branch %s, and the VM clones from GitHub, so it would not get this work: push it (git push -u origin %s), or name what the VM checks out with --vm-project %s@<ref>` |
| 15 | `new`, HEAD is not origin's | 1 | `spawn --on new: origin's %s is at %s and this checkout is at %s, so the VM would clone without what differs: push it, or name the ref with --vm-project %s@<ref>` |
| 16 | `new`, origin gave no answer | 1 | `spawn --on new: origin did not say where %s is (%s): try again, or name the ref with --vm-project %s@<ref>` |
| 17 | `new`, the first project is a registry name and no `--cwd` | 2 | `spawn --on new: %s is a registry name, whose checkout only its registry places: name the session's directory on the VM with --cwd` |
| 18 | a VM, no `--cwd`, no repository on GitHub | 2 | `spawn --on: %s is in no repository whose origin is on GitHub, so the session's directory on %s cannot be derived: name it with --cwd` |
| 19 | before `vm up` (a note) | — | `making a VM (a few minutes; devcloud's own lines follow): devcloud vm up %s` |
| 20 | `vm up` exits other than 0 | its own | `spawn --on new: devcloud vm up exited %d; its own lines above say why, and what became of any VM it made. Nothing was spawned`, and for exit 4: `. The cap is the person's: after their yes to this exact request, pass --vm-confirmed` |
| 21 | `vm up` exits 0 and names no host | 1 | `spawn --on new: devcloud vm up succeeded and named no host where sminos reads it: find the VM with devcloud vm ls, then sminos spawn --on <name>` |
| 22 | a VM that is not enrolled | 1 | `spawn --on: %s is not enrolled in the org (no endpoint on it has been welcomed: a host made without the MAWS project, or one whose enrollment has not finished; devcloud vm ssh %s -- devcloud status shows its maws step), so no other machine would see a session there: nothing was spawned` |
| 23 | `new`, not enrolled yet (a note, once) | — | `%s is up and not enrolled in the org yet: waiting up to %d minutes for its endpoint (the host tries again every 5), then spawning` |
| 24 | `new`, the wait is over | 1 | `spawn --on new: %s did not enroll within %d minutes: nothing was spawned. The VM is kept and this session's thread owns it: devcloud vm down %s ends it, and once sminos machines lists it, sminos spawn --on %s spawns there` |
| 25 | the VM side answered not ok | its exit | `spawn --on: %s's sminos answered exit %d; its line above says why, and what, if anything, exists there`, and after `vm up`: `. The VM %s is kept and this session's thread owns it` |
| 26 | no outcome line, exit 2 | 2 | `spawn --on: %s's sminos answered with a usage error and no outcome: its copy is older than spawn --on. A devcloud host brings its copy to the marketplace's head at each configuration pull, within half an hour: try again then. Nothing was spawned` |
| 27 | no outcome line, any other exit | that exit, 1 for 0 | `spawn --on: no outcome came back from %s (devcloud vm ssh exited %d; its lines are above): whether a session started there is not known, and devcloud vm ssh %s -- sminos list shows` |
| 28 | as 27, when devcloud's line says `no VM named` and the org's directory lists the name (a note after it) | — | `%s is a machine of this org that devcloud has no host for. If it is a Mac: a session is not opened on a Mac from another machine in this version, since a Mac's login keychain is closed to an ssh session and claude needs it; open it on that Mac` |
| 29 | no answer within the bound | 1 | `spawn --on: %s gave no outcome within %d minutes, and the call was stopped: whether a session started there is not known, and devcloud vm ssh %s -- sminos list shows` |
| 30 | spawned (standard output) | 0 | `seat spawned on %(machine)s: %(group)s/%(alias)s  [%(short)s / %(seat)s]  status=%(status)s  (message it: sminos say "@%(session8)s …"; it is listed here once %(machine)s's events arrive)`; `seat re-filled on …` for a refill; `session8` the first eight characters of the outcome's `session` |
| 31 | after 30, for `new` (a note) | — | `%s is kept and this session's thread owns it: devcloud vm down %s ends it, and it sends a notice after three idle days` |

`sminos help` lists `--on`, `--vm-project` and `--vm-confirmed` under `spawn`, and `--asked-from` as the form another machine's sminos calls.

### §8. `spawn --asked-from`, the VM side, and the outcome line

    sminos spawn <alias> - --asked-from <json> [--cwd <dir>] [the carried flags]

    {"v": 1, "nonce": "<16 hex>",
     "by": {"alias": "<alias>", "short": "<8 hex>", "project": "<project id>",
            "project_name": "<project name>", "machine": "<machine>"} | null}

`by` is null when no session ran the Mac side. A value that is not this object whole (`v` 1, the nonce, `by` null or its five strings, the short eight hex digits) exits 2 with `spawn: --asked-from is not a request this version reads` and prints no outcome line. `--asked-from` with `--wait` is a usage error.

Under it `cmd_spawn` does what it does without it, and:

1. on a machine that is not enrolled (`enrollment()` is None) spawns nothing, says `spawn: this machine is not enrolled in the org, and a session opened here for another machine would be seen by none: nothing was spawned`, and exits 1 with `why` `not-enrolled`;
2. expands a `--cwd` that opens `~/` from the user's home directory;
3. names the spawner: the preamble's `{{BY}}` is `%(alias)s (@%(short)s, in %(project_name)s on %(machine)s; sminos say "@%(short)s …" reaches it)` and the `joined`'s `by` is the alias; with `by` null both are as today (`the operator`, empty). The new session's record is what a spawn from this machine's terminal gives (`spawn_provenance`'s last case): the origin names no spawner's session, and nothing of `by` is a grant;
4. prints no `seat spawned:` line; its last line on standard output, for every way it ends after the value was read, is the outcome line:

       sminos-spawn <nonce> {"ok": true, "refilled": false, "group": "<group>", "alias": "<alias>",
                             "short": "<the engine's job id>", "seat": "<seat id>", "session": "<session id>",
                             "status": "<status>", "project": {"id": "<id>", "name": "<name>"},
                             "machine": "<this machine's name>", "cwd": "<the directory it runs in>"}
       sminos-spawn <nonce> {"ok": false, "exit": <the exit code>, "why": "not-enrolled" | "other"}

   one line, the JSON without a line break. What `spawn` says on standard error (a refusal's sentence, a warning that an event could not be appended) is said as today.

The Mac side takes as the outcome the last line of standard output that is whole by `sminos-spawn <its nonce> <one JSON object with a boolean ok>`. It acts on `why` `not-enrolled` and treats any other value as `other`.

Without `--asked-from`, `spawn` is byte for byte what it was: that is the call an older Mac, or a person, makes over `devcloud vm ssh` today.

### §9. `devcloud vm up --enroll`, and the line that names the host

    devcloud vm up --enroll …

With it, `up` requires the host to provision MAWS's endpoint: where `compose.provisions(profile, projects)` is false and the profile's `[desk]` names the provisioning, `compose.MAWS_PROJECT` is appended to the projects (after those named, so the first project's `host.toml` still governs) and `up` says `enroll    the MAWS project is added: its setup installs the endpoint this host enrolls with`; where the profile names none, `up` ends before anything is listed, priced or made, under `--dry-run` too:

| Case | Exit | Words (after `devcloud vm: `) |
|---|---|---|
| `--enroll`, a profile whose `[desk]` names no provisioning | 3 | `--enroll: the profile's [desk] names no provisioning (provisioning_secret_v2 with delegation_id), so a host it makes cannot join the org: nothing was made` |

Without `--enroll`, `up` is what it was. The line `up` ends a host's making with, `<name>  ready in <m>m<ss>s`, is read by sminos (`READY_RE`): a test in `D/tests/unit/test_driver_up.py` named for that reader pins it, and so does the opening `no VM named` of `Context.find`'s refusal.

### §10. An older copy on the other side

| What is new | Who may meet it older | What then |
|---|---|---|
| `notice` on a `human` event | a reader on a sminos before 1.53.0 (a Mac not yet updated, a session's hooks from a cached copy); MAWS before its own change | it reads the event as today: a person's line, asked of the endpoint, framed `from human`; on another machine the endpoint answers `peer`, so it arrives as a peer's frame either way. Accepted (X8's last sentence, D7) |
| `say --notice`, `say --exit-held` | a host whose sminos does not know them (only a devcloud run from a checkout ahead of `main` builds one) | usage error, exit 2, nothing recorded; the host runs the step again without them (§3) |
| a boot library that passes them | every host made before devcloud 0.18.0, for its life | it sends as before: unmarked, and going on only at a non-zero exit, so not for a held thread. The receiving side is unchanged for it: X2 takes the tag to the thread's current session and the wake starts a stopped one (acceptance 8) |
| `sminos who --thread` | devcloud 0.18.0 beside a sminos before 1.53.0 | exit 2; `vm owner` refuses in §5's words and changes nothing |
| the refusal that names `devcloud vm owner` | sminos 1.53.0 beside a devcloud before 0.18.0 | devcloud answers the verb with a usage error; `devcloud vm down` is still the way on. Accepted: both update from one marketplace |
| `devcloud vm up --enroll` | sminos 1.53.0 beside a devcloud before 0.18.0 | `spawn --on` refuses before it calls (§7, row 9) |
| `spawn --asked-from` | a VM whose sminos is older (a host that has not pulled since the merge) | usage error, exit 2, no outcome line; the Mac says so (§7, row 26) |
| `devcloud vm ssh <vm> -- sminos spawn …` by hand, with no `--asked-from` | a VM on this sminos, called by an older Mac or a person | unchanged (§8's last sentence) |
| the owner program | a host made before 0.18.0 | it runs: it needs only the host's own library as it has been since `lease set` existed. A host whose parser predates the project key takes the tag alone (§5) |
| the `OWNER` header | whatever read `devcloud vm ls`'s table | nothing in this tree parses the table; `--json` is unchanged |

### §11. What the tests are built on

**`T/devcloud_standin.py`** keeps `vm owned-by` exactly as it is and learns two verbs, both set through the same `$HOME/devcloud-standin.json` and logged to `devcloud-standin.calls`:

- `vm up …`: prints the lines its `up.lines` holds (by default `created   <up.name> (id 1) from base, slow path` and `<up.name>  ready in 0m01s`), writes `up.stderr`, and exits `up.exit` (0).
- `vm ssh <name> -- <words>`: for a `<name>` its `hosts` holds, joins the words as `shlex.join` does and runs the line with `/bin/sh -c` under that host's `env` (its `HOME`, `SMINOS_HOME`, `DAEMON_HOST`, `PATH`), standard input passed on, the word `sminos` at the line's head replaced by the launcher `sminos` names; `hosts.<name>.exit`, when set, is answered instead with nothing run (2 for a copy that predates the call, 255 for a host that does not answer). For any other name: `devcloud vm: no VM named <name> in any usable account`, exit 1.

**`T/test-on.sh` and `T/test-notice-machines.sh`** are two sminos homes named as `T/rl10-machines.sh` names them (`rl10_as`, `rl10_cut_over`), the second also served by `T/endpoint_standin.py` with the verdict the case sets. A machine is "not enrolled" when its home holds no `daemon/identity.json`.

**`D/tests/unit/driver_fixtures.py`**: `make_ctx` passes `thread=`, a function from a name to §4's answer, as it passes `creator=`; `FakeRemote` answers the owner program by a rule on `python3 -P -`, and the program's own behaviour is tested by running its text.

**`D/tests/fixtures/sminos.py`** plays `say` with the two flags, and, where its state says so, as a copy that does not know them.

### Dependencies

Nothing is added: Python's standard library on both sides, `git` on the Mac for the one question put to origin, devcloud's driver as it is. The Mac side of `spawn --on` needs devcloud 0.18.0, and `devcloud vm owner` needs sminos 1.53.0; each says so when it meets less. M5 needs what `devcloud vm up` needs (a seed key, a profile with an account and a `[desk]`) and the person's registry to hold the MAWS project under the name devcloud's README gives it.

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
- Observation: MAWS's hub and endpoint pass an unknown field on a `human` event through whole; for a host's line reaching a session on another machine the endpoint answers `peer`, never `words`; no way exists to put MAWS's endpoint on a machine without the MAWS project.
  Evidence: MAWS's architect, relayed by the composite's holder on 2026-11-21.

## Decision Log

- 2026-11-21 — **Verification.** This plan gets one review before it is built, by the `doperpowers:adversarial-reviewer` agent, on buildability: the milestones against the code, the names and sentences of Interfaces against the composite and the rulings, and §10's table against what each older copy really does. The build runs under `doperpowers:plan-executor`, a fresh executor a milestone; each milestone is reviewed at its close by the execution loop's reviewer. After M4, the last milestone that changes the tree, the composite's holder reviews the whole range through doperpowers:review-code at the panel rung `xhigh`, with these lenses given: what leaves a machine (a notice's fields and frame, what `--asked-from` carries, what the outcome line and `who --thread` export); that every refusal comes before its side effect (nothing made, spawned or written); the two plugins' contract read from both sides (§3, §4, §5, §8, §9); and §10's older copies. Its confirmed findings go to a fix wave, weighed as the owner's rule for review findings weighs them. M5 changes nothing and is not reviewed; what it finds is a change of its own.
- 2026-11-21 — **The lagging view is not closed here** (against R7's third point, which made a lost notice this plan's to fix on the receiving side). As built the event is not pushed (Surprises & Discoveries). Closing it means either a second ledger through the delivery core (the owed list, the delivery record, the hold marks, the receipts and the two asks are all keyed by the session an event names) or a new writer in the daemon that says a notice again to the thread's current session; both sit where T1's and T2's reviews found most of their defects. Against that: the window is the seconds between a session change on the Mac and the VM reading it, a notice is sent once in three idle days, and the idle notice comes again. So this plan pins the outcome in a test, records it in TECH-DEBT with what would promote it, and reports it. The fix this author would choose when it is promoted: keep in the thread record the project log's positions at each change of session (CH1 keeps such positions for a channel), and let `_owed` read, for the current session, what names a former one past them. Alternative rejected: the daemon re-saying a marked notice under the Mac's own human writer, which closes it for notices only and makes the Mac the notice's sender.
- 2026-11-21 — **A machine that is not connected is not a case of going on** (R7's parenthesis asked for it "if the sender's view already tells it"). It does not: the endpoint publishes no presence. Alternative rejected: reading `online` in the org's directory as kept, which is false for every machine. The composite already defers a machine publishing whether it is on.
- 2026-11-21 — **The live check runs after the merge** (R10 has it close the plan). Both machines run sminos from `main`, so a check before the merge would exercise neither the VM side nor the Mac's delivery. Alternative rejected: pointing the VM's copy at the branch by hand, which the host's own refresh undoes within half an hour.
- 2026-11-21 — **The host is written by a program the driver sends** (R6 allowed this or a way for an existing host to get a new verb). Alternative rejected: a verb of the host's CLI with this as its fallback, two paths where every host alive at landing would take the fallback.
- 2026-11-21 — **devcloud decides what enrollment needs: `vm up --enroll`** (R1 named the MAWS project as what is needed today). Alternative rejected: sminos passing `--project maws` and reading the profile itself, which puts devcloud's knowledge in sminos twice and has to change in both plugins when MAWS ships its endpoint apart.
- 2026-11-21 — **The VM's name is read from `up`'s own last line,** pinned by a test on devcloud's side. Alternative rejected: a machine-readable output for `up`, new surface for one word that `up` already prints in a fixed place.
- 2026-11-21 — **One flag carries the remote call, `--asked-from`, as JSON** (R3 and R4 each asked for a flag). The nonce, the spawner and the refusal on a machine that is not enrolled are one mode, known or not known to a VM's copy as a whole. Under it the Mac prints the spawn's line itself: the VM's `seat spawned:` line ends with `sminos reply <short>`, which is false on another machine. Alternative rejected: one flag for the outcome line and one for the spawner, which lets a copy know one and not the other.
- 2026-11-21 — **`sminos who --thread` is the answer devcloud reads** (R6 left its form open). Alternatives rejected: exporting a thread's sessions in `list --json`, which X1 withholds on purpose; devcloud importing sminos's modules, which ties two plugins' internals.
- 2026-11-21 — **Exit 3 and the name `--exit-held`** (R7: any code but 4). 3 is the first code sminos does not use; "held" is the word T2's lines already give a sender. Alternative rejected: devcloud reading the line `say` prints, which makes a sentence written for a person a contract with a program.
- 2026-11-21 — **The host retries a step without the flags at exit 2, and skips the log step after exit 3** (R7 called the usage error "the safe side" for a host whose sminos lacks the flag; with the marker on every step it would be the journal). Alternative rejected for the second: writing the untagged note anyway, which says the notice twice in one log.
- 2026-11-21 — **The reach rule is the ruling's, to the letter:** refused unless the spawner's record is the machine's default. A spawner whose access is wider than the default is refused too, though the VM's default would be narrower: one rule a session can be told in one sentence. Carrying reach is not built.
- 2026-11-21 — **`--on new` asks origin where the branch is** (`git ls-remote`) and does not trust the local tracking ref. Alternative rejected: the tracking ref, which says what origin held at the last fetch and passes a branch someone else moved.
- 2026-11-21 — **The names:** `--vm-project` and `--vm-confirmed` (what reaches `vm up`, said by one prefix; `--project` on `say` and `list` already means a sminos project), `S/sminos_on.py`, `EXIT_HELD`, `notice_of`, `notice_sender`. Rejected: `--checkout`, which names what the VM does and hides that it is `vm up`'s argument. The waits: eleven minutes for enrollment (two of the host's five-minute tries and a minute), a try every thirty seconds, eight minutes for one remote call (the engine's own launch bound is five).
- 2026-11-21 — **sminos's own `--on` refusals exit 2 (usage) or 1; every other exit is what it was told.** devcloud's 4 (a cap) and a seat refusal's 4 on the VM both pass through as 4, as R2 has devcloud's codes pass; the line printed tells them apart. Alternative rejected: mapping devcloud's codes onto codes of sminos's own, which hides from a session the code devcloud's skill taught it.
- 2026-11-21 — **`devcloud vm ls`'s header becomes `OWNER`.** After a handover the column holds a thread that made nothing. The label, the descriptor's keys and `--json`'s key keep "creator": renaming them would orphan every host alive.
- 2026-11-21 — **A session the MAWS app launched is not refused `--on new`.** devcloud records it as it does for `vm up` today, and nothing guards a VM so made, since such a session is no thread. Alternative rejected: refusing it, a rule no ruling asked for and that takes away what `vm up` allows.
- 2026-11-21 — **What is taught changes in one milestone at the end,** not with each behaviour: a skill must not teach `--on` before the verb, the handover and the notice it describes all exist, and one evaluation reads the whole.

## Outcomes & Retrospective

Pending — written at finish.

## For the composite's writer

**(a) Sentences of the composite this plan makes false or completes, each with the replacement proposed.**

D4:

1. "`--on new` runs `devcloud vm up`, whose caps, consent rules and exit codes are unchanged and decide whether a VM is made; sminos waits for the machine's enrollment and spawns there." → "`--on new` runs `devcloud vm up --enroll --keep` with the spawner's repository at its current branch, which origin must hold at the spawner's HEAD (or with the projects `--vm-project` names). devcloud's caps, consent rules and exit codes are unchanged and decide whether a VM is made; `--confirmed` reaches it only as `--vm-confirmed`. A profile that cannot enroll a VM is refused by devcloud before one is made, and a call with no session is refused by sminos, since the VM would have no owner. sminos then spawns over ssh and, while the VM answers that it is not enrolled yet, tries again for eleven minutes."
2. "The first version reaches a VM over ssh from a Mac, as `devcloud vm ssh <name> -- sminos spawn` does by hand today." → add: "The call is that command with the task on standard input and one flag, `--asked-from`, carrying a nonce and who asked. The VM's sminos refuses where its machine is not enrolled, names the spawner in the new thread's preamble, and answers with one line the Mac reads; the Mac never decides from an exit code alone. The new thread takes the VM's default reach, so `--on` is refused from a spawner whose own reach is not its machine's default (carrying it is Deferred). `--wait` and `--settings` are refused with `--on`."
3. "Two cases are refused, each naming its reason, and wait for a later design: `--on` asked from a VM …, and `--on` naming a Mac …" → add: "A VM is told by its descriptor file, as devcloud tells one. sminos cannot tell a Mac from any other machine: a name devcloud has no host for gets devcloud's own line, and where the org lists that name as a machine, the Mac's reason is added, worded as a condition. `--on` naming a VM that is not enrolled is refused too: no other machine would see the thread."
4. "devcloud records the creator as it does today, as a tag naming the creating session; D1's naming rule makes that tag a name of the thread, so a VM made before this work is already owned by a thread." → "devcloud records who owns a host as it records its creator today: the session's short id in the provider's label or the adoption record, and on the host a tag of that short id with the owning thread's project, which is where a notice goes on to. D1's naming rule makes the short id a name of the thread, so a VM made before this work is already owned by one."
5. "`devcloud vm owner <vm> <thread>`, a new verb, hands a VM to another thread." → add: "It writes the short id of that thread's current session in each of those places: the host first, under its lifecycle lock, by a program the driver sends (so a host made before the verb takes it), then the label or the record. Between the two a retire still refuses the thread that gave the VM up. It asks sminos which thread a name is (`sminos who --thread`), accepts a thread of the machine it is run on that has not ended, a stopped one included, checks nothing about its caller, and sends no message."
6. "A VM's idle and lease notices are sent from the VM, as today, to the tag of the thread that owns it, which reaches the thread's current session and wakes it if it is stopped." → add: "The tag is resolved on the VM, from the VM's reading of the thread's project log. A notice sent in the seconds before the VM has read a change of session names the session the thread left, and is not pushed (accepted; `docs/doperpowers/TECH-DEBT.md`)."
7. "When that thread cannot be woken, devcloud's order holds as today: the live members of the owning thread's project, then that project's log." → "When the VM's own `say` reports that the thread is held and not woken (for any reason its machine published), has ended, or is no member, the notice goes on: to the live members of the owning thread's project, then, where no step has recorded it, into that project's log. The signal is `say --exit-held`, exit 3. A thread whose machine is not connected is not such a case (nothing publishes that: Deferred), and a host made before this work goes on only for an ended thread or no member, as before."
8. "It is written as it is today, by the VM's own `say` under the VM's human writer, with a marker that says it is a machine's notice; …" → after "a machine's notice": "(the field `notice`, set by `say --notice devcloud`, which a session is refused)".
9. "… **[binding — the owner: "kept, 소유 스레드가 내린다"]**, which is devcloud's default." → "…, which `--on new` asks for (`--keep`): devcloud keeps a VM by default only while the profile sets no `lease_default`."

The EN section:

10. G1's "`--on` from a VM and `--on <a Mac>` are refused, each naming its reason" → add the rest of this plan's acceptance 4 by pointing at it.
11. "From T1 as built: `owned_by` and `owned_vms` (its plan's §7) are the one place sminos runs devcloud" → "… are the one place sminos asks devcloud what a thread owns; `S/sminos_on.py` runs `devcloud vm up` and `devcloud vm ssh`, found by the same finder."
12. Its Status and the Tracking Map's row: this plan's path, and "G1 in flight".

Delegated unknowns, the row "How `--on new` derives the VM's label, project and branch and the new thread's directory": settled by this plan. The label is the alias where it fits devcloud's rule; the project is the spawner's repository as GitHub names it, at its current branch, which origin must hold at the spawner's HEAD; the directory is the VM's checkout, `~/Developer/GitHub/<repo>`; `devcloud vm up` reads none of these from its directory, against the row's lean.

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
- An addressed event that names a session its thread has left is not pushed (any sender whose view lags, a VM's notice among them): seconds wide, costly to close in the delivery core; TECH-DEBT.
- A notice to a thread whose machine is not connected waits for that machine: nothing publishes presence (the composite's Deferred).
- A host made before devcloud 0.18.0 sends its notices unmarked and goes on only for an ended thread or no member: a host keeps the boot library it was built with.
- A host built before 2026-10-27 takes a new owner without the project: its parser refuses the key.
- An adopted machine's descriptor holds no project until a handover writes one: `devcloud vm adopt` is not changed here.
- A census older than a handover can let the three-day rule end the thread that just took a VM, for up to an hour (R6: accepted; the VM is not lost and the thread returns when reopened).
- Between the handover's two writes, a retire refuses the thread that gave the VM up and would pass the one taking it: run again, the verb finishes.
- A VM made from a session the MAWS app launched is recorded under that session, as `vm up` does today, and nothing guards it: such a session is no thread.
- sminos cannot tell a Mac from another machine, so that refusal is worded as a condition: nothing publishes a machine's kind.
- The two machines' default reach is taken to be one audience: this fleet has one owner.
- `--on new` does not look at uncommitted changes: the VM gets what the pushed branch holds.
- sminos reads two of devcloud's human lines (`<name>  ready in …`, `no VM named …`): each is pinned by a test on devcloud's side.
- After the merge `vm up` takes the slow path until an image is built for the new recipe hash: the scheduled reaper does it within a day.
- `sminos spawn --on new` takes minutes and blocks: the skill has a session run it as a background command.

**(c) Files this plan changes that the sibling child CH1 also changes** (its plan `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md`), and whether the two can be built at once.

| File | What CH1 changes | What this plan changes |
|---|---|---|
| `S/sminos.py` | the predicate and the lookups for a channel, `join`, `view_of`, `lifecycle`, `cmd_say`'s and `_resolve_tag`'s refusals of a channel, `find_target`, `cmd_list`, `member_json`, `build_parser` (the `channel` family, `list --channel`), the help text | `owner_event` and two functions beside it, `cmd_say` and `say_scoped` (a field, an exit), `deliver_say` (what it returns), `frame_of`, `holder_wake`, `chat_line`, `cmd_who`, `main`, `cmd_spawn`, `spawn_fresh`, `build_parser` (flags on `say`, `who`, `spawn`), the help text |
| `S/sminos_threads.py` | the record's operation for a thread's channels, `update`, `Fold` | `owned_words` |
| `S/CLAUDE.md` | a section for channels | sentences on notices, the handover and `--on` |
| `T/run-sminos-tests.sh` | a third part, `channels` | five files added to `run_suites` |
| `docs/doperpowers/TECH-DEBT.md` | its rows | its rows |
| `sminos/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | sminos to 1.53.0 | sminos to 1.53.0, devcloud to 0.18.0 |

No function changes meaning for the other child. The one this plan calls and CH1 changes is `find_target`, which CH1 teaches to refuse a name qualified by a channel: `who --thread` then refuses such a name as every verb does. The two shared functions both edit are `cmd_say`, where CH1 adds refusals at its head and this plan a field and an exit at its end, and `build_parser`, in different verbs. CH1 leaves what sessions are taught alone, so the skills and the preamble meet no other hand until CH2.

Judgment: build both at once, on separate branches. This plan keeps its sminos code in a module of its own and touches `S/sminos.py` at named seams for that reason. The overlap is textual, and whichever merges second merges `main` first and takes the next version (both plans say so). If CH1 merges first, this branch merges `main` before its whole-range review, so the review reads the tree that will ship.

**What MAWS does on its side,** after this plan's review, none of it this plan's work and none of it waited for: its endpoint answers `peer` where it would answer `words` for a marked event; its app's channel shows a marked event as that machine's notice; and a vector pins the frame line `[sminos chat <project> <ref> from <program>@<machine>… → @you]`.
