# sminos/skills/sminos/scripts/ — the sminos CLI, the daemon and its uplink

Paths are named from `sminos/`. A module's working and its own invariants are its docstring; why, the spec it cites. This file holds what spans modules.

## Modules

- `sminos` — launcher of `sminos.py`.
- `lib.sh` — sourced shell half: registry root and host/boot identity for the board's dispatchers.
- `sminos.py` — the CLI and core: projects, members, seats, the log, delivery, derive, find.
- `sminos_daemon.py` — `daemon` verbs: the tick loop, git mirror, duties, sweeps, the service.
- `sminos_archive.py` — a hub project's log archived to its git remote by the designated machine.
- `sminos_audience.py` — which writer stream an event goes under, from the endpoint's audience frames.
- `sminos_bridge.py` — the bridge mod's child serving a session's endpoint socket, and `sminos watch`.
- `sminos_channels.py` — declared channels: registry, roster, placement, delivery, the `channel` verbs.
- `sminos_chart.py` — the project families drawn as boxes, pure.
- `sminos_codes.py` — canonical JSON and base64url, byte for byte as the desk writes them.
- `sminos_control.py` — the control verbs (steer, interrupt, decide, answer, …) and a delivery's last hop.
- `sminos_fork.py` — forks of a session (btw, fork agent, headless) and find's fresh model call; no verb.
- `sminos_holder.py` — the bridge child's gate client on MAWS lane B's holder socket, relaying to the mod.
- `sminos_holder_deliveries.py` — per-process gate/legacy mode and durable delivery receipts.
- `sminos_hub.py` — `hub` verbs: this machine's org identity as its endpoint gave it.
- `sminos_hublog.py` — one hub project's log plane over RL10: hello vectors, uploads, intake.
- `sminos_jobs.py` — subagents, background jobs and MCP status derived purely from transcript rows.
- `sminos_marks.py` — Python port of to-human's `<message>` parser (`tests/marks_parity.py`).
- `sminos_media.py` — a desk upload's files, written link-safely under the session's directory.
- `sminos_on.py` — `spawn --on <vm>|new`: a session opened on a devcloud VM.
- `sminos_outcomes.py` — outcomes of delivering events written outside this machine, recorded for the hub.
- `sminos_owed.py` — versioned files of what the uplink still owes the hub across restarts.
- `sminos_plane.py` — the session plane: presence, subscriptions, transcript indexes and their warmer.
- `sminos_policy.py` — the machine's policy (read_only, ceiling) and its known checkouts.
- `sminos_profile.py` — `daemon profile`: a live loop profiles itself on request.
- `sminos_records.py` — each session's machine-held record: owners, origin, inference, access.
- `sminos_requests.py` — sessions' permission prompts and questions relayed to the hub as raised and settled.
- `sminos_rl10.py` — the local endpoint (RL10): discovery, connection, cutover identity, revocations.
- `sminos_rpc.py` — RPCs from members' devices: ordered checks, ledger, execution, outcomes.
- `sminos_sheet.py` — the question sheet's record: its door, reader, step shell and `sheet` verbs.
- `sminos_sheet_step.py` — the question sheet's state machine as a pure function.
- `sminos_subagents.py` — `list --subagents`: each subagent's lifecycle from the bridge, else from disk.
- `sminos_threads.py` — lane A thread records, the lifecycle stamp, the membership reducer and its journal.
- `sminos_tui.py` — the org chart as a terminal screen.
- `sminos_uplink.py` — `daemon uplink`: the endpoint connection, its writer lanes, the main-thread pump.
- `sminos_visibility.py` — `access` and `share`: who may reach a session, as its owner sets it.
- `sminos_wake.py` — what waking a stopped thread reads and says, with no effects of its own.

## Before you change anything

- **`sminos.py`'s module docstring is `sminos help`**, which sessions read: developer facts go at the function.
- **Run a working copy only under a temporary `HOME` and `SMINOS_HOME`**, as `tests/run-sminos-tests.sh` does: `main` runs `migrate`, which changes a real root one way, before every verb but the lock-free reads it dispatches first (`bridge`, `sheet --session`, `guide`, `daemon owed`; `migrate`'s docstring lists them), so a session's hooks never wait on the registry's lock.
- **Older sminos copies share the store and the log on a machine**, so a change of shape must pass `tests/test-older-cli.sh` (needs the network). Every `*.json` at the `$SMINOS_HOME` root is a seat to every copy, so a new store gets a directory of its own.
- **Whose words an event is, is decided in one place**, `words_route` / `WordsGate`. On a cut-over machine a `human` event reaches a session as a person's words only by the endpoint's verdict; an own-operator event's append receipt only qualifies it for that ask (without one it goes as an unverified peer's), because a writer's name is not provenance (a git mirror can merge in a `<machine>/human` line). A machine's notice (`notice_of`, shared with MAWS) is nobody's words.
- **Reach is checked inside the push primitives** (`push_live`, `resume_session`) on a machine whose endpoint advertises it: only `deliver_reach`, carrying out the endpoint's `reach` answer, grants the single-use permit for one push; every other deliverer leaves the event owed, but for one no-ask case. In a hub project an unknown audience leaves a delivery owed and fails an append (`StreamUnknown`); both are stated in the comment above `_REACH_PERMITS` and `sminos_audience`'s docstring.
- **A session's policy (`access`, `shares`, `policyRev`) changes only through `sminos_records.set_policy`**, and a record replaced for any other reason keeps it (the module docstring), because the endpoint matches audiences by `policyRev`.
- **A channel's word is carried out by the daemon, not on the uplink's consumer thread.** `Link.on_reach` calls `deliver_reach` at once for a project's event, but keeps a channel's verdict (`keep_channel_word`) for the daemon's `channel_pass` (`carry_words`), since waiting there for a thread's delivery lock would stall the whole stream. Code under a record's store lock (`sminos_threads.set_channels`'s `decide`) reads files, never a view, since a view reconciles.
- **The daemon is the execution boundary for every remote RPC**: a new one goes through `sminos_rpc`'s ordered checks and its at-most-once ledger keyed by `opId`.
- **`daemon/identity.json` is the cutover** and the only enrollment (`hub.json` enrolls nothing); undo it endpoint first (`rl10.json`, its socket), or the next probe cuts over again. A hub project never syncs through git: its remote holds only the archive, and nothing is read back into `log/`.
- **Threads: one reducer, one journal, one lock order.** Membership is read only through `sminos_threads.in_effect` (MAWS's vectors check it); journaled keys change only through `begin` / `finish`, which replay after a crash; a transition takes its wake locks first, by ascending thread id (`claim_holds`), then the stores' locks (`claims_held`), then the log's, never the reverse.
- **`sminos.wake` is the one caller of `run_claude_bg --resume`**, never with a message after the id, or the engine starts a copy or renames the session (`tests/test_wake_seat.py` holds it).
- **A channel is no project.** Its log id is a version-8 UUID (`is_channel_id`), `known_projects` never returns one, and no ordinary traffic (lifecycle, plane frames, host store, outcomes) goes under a channel id, since a thread's facts belong to its project (`tests/channel_wire.py`). New channel work goes behind `channels_here()` / `Link.channels`, so a machine holding none pays nothing (the `sminos-idle` gate).
- **A channel is keyed by thread, never by session**: its debt, receipts, bridge scope and cursor, since a session may serve one thread, then another. It is delivered only through `deliver_next` / `deliver_verdict` / `deliver_reach` with an `Owing`; a call without one must stay what a project's call was (`test_channels_say.py`'s `SameAsBase`). No project path writes into a channel: it is spoken in only by naming it.
- **A session's engine files are under its own config dir** (`CLAUDE_CONFIG_DIR`, else `~/.claude`): read one session's through `session_config_dir`, every session's through `engine_record_paths` filtered by `speaks_for`, since a copied dir holds others' records.
- **Caches are module globals cleared per generation in `forget_caches`**, or keyed on their inputs, never on time; a file read through `file_bytes` / `json_at` is written whole by rename, or a stat-keyed read misses the change.
- **On macOS a sminos process reads inside a protected folder only when its own working directory is in the same one, and a child it starts on its own sits neither inside nor above one** (`read_refused`, `git_refused`, `launch_refused`; the section comment in `sminos.py`), because the privacy dialog is charged to the daemon and blocks it.
- **A directory's project is one rule shared with MAWS** (`sminos.decision`), held to vendored vectors; a change MAWS's `deriveOrg` lacks puts one folder in two projects.
- **Contracts with other plugins change in step**: a host's `say --notice` / `--pools` exits 2 only for its usage errors, since devcloud reads 2 as a sminos too old for those flags (`devcloud/boot/devcloudlib/notices.py`); devcloud's `vm owned-by` and `who --thread` JSON (`sminos_threads.owned_by`); the `owed: <session>` line (`OWED_LINE`) parsed by issue-tracker's `_sweep_api.sh`.
- **A glob over the sminos home wraps it in `glob.escape`**: a `[` in the path matches nothing otherwise.

## Pinned files and commands

- `tests/vectors/maws/*.json` and their pins are written only by `tests/vectors/maws/sync.sh <MAWS checkout> <commit> [<file>]`; `tests/rl10-conversation.json` is MAWS's fixture copied byte for byte (source in `rl10-conversation.source.json`). Re-copy, never amend: an edit breaks parity with MAWS.
- `tests/run-sminos-tests.sh` is the hermetic suite, every part unless `SMINOS_PART` names one (`core`, the `sminos` gate; `suites-a|b|c`; `channels`). `python3 -B tests/rl10_conformance.py` replays the RL10 conversation. `tests/bench_scale.py` (`run`, `tick`, `opens`, `verbs`) measures the daemon's idle cost; `.github/ci-kit.yml`'s `sminos-idle` has the gate's form.
