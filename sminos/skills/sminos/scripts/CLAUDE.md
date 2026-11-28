# sminos/skills/sminos/scripts/ — the sminos CLI, the daemon and its uplink

Paths are named from `sminos/`. How a module works, and the invariants that bind it alone, are in its docstring; why, in the spec or plan the docstring cites. This file holds what spans modules.

## Modules

- `sminos` — launcher: resolves its own real path and execs `sminos.py`.
- `lib.sh` — sourced shell half: registry root and host/boot identity for the board's dispatchers.
- `sminos.py` — the CLI and core: projects, members, seats, the log, delivery, derive, find, engine files.
- `sminos_daemon.py` — `daemon` verbs: the tick loop, git mirror sync, project duties, sweeps, the service.
- `sminos_archive.py` — a hub project's log archived to its git remote by the designated machine.
- `sminos_audience.py` — which writer stream an event goes under, from the endpoint's audience frames.
- `sminos_bridge.py` — the bridge mod's child serving a session's endpoint socket, and `sminos watch`.
- `sminos_channels.py` — declared channels: finding, registering, roster, threads placed, delivery, the `channel` verbs.
- `sminos_chart.py` — the project families drawn as boxes: snapshot, layout, render, all pure.
- `sminos_codes.py` — canonical JSON and base64url, byte for byte as the desk's TypeScript writes them.
- `sminos_control.py` — steer, interrupt, stop, model, compact, command, read, decide, answer; a delivery's last hop.
- `sminos_fork.py` — forks of a session (btw, fork agent, headless) and find's fresh model call; no verb.
- `sminos_holder.py` — the bridge child's gate client on MAWS lane B's holder socket, relaying to the mod.
- `sminos_holder_deliveries.py` — per-process gate/legacy mode and durable delivery receipts; its docstring is the contract.
- `sminos_hub.py` — `hub` verbs: this machine's org identity as its endpoint gave it.
- `sminos_hublog.py` — one hub project's log plane over RL10: hello vectors, uploads, intake.
- `sminos_jobs.py` — subagents, background jobs and MCP status derived purely from transcript rows.
- `sminos_marks.py` — Python port of to-human's mark parser (`<message>` spans), pinned by `tests/marks_parity.py`.
- `sminos_media.py` — a desk upload's files, written link-safely under `<cwd>/.claude/desk-uploads/`.
- `sminos_on.py` — `spawn --on <vm>|new`: a session opened on a devcloud VM.
- `sminos_outcomes.py` — outcomes of delivering events written outside this machine, recorded for the hub.
- `sminos_owed.py` — versioned files of what the uplink still owes the hub across restarts.
- `sminos_plane.py` — the session plane: presence, subscriptions, transcript indexes and their warmer.
- `sminos_policy.py` — the machine's policy (read_only, ceiling) and its known checkouts.
- `sminos_profile.py` — `daemon profile`: a live daemon loop profiles itself on request.
- `sminos_records.py` — each session's machine-held record: owners, origin, inference, access.
- `sminos_requests.py` — sessions' permission prompts and questions relayed to the hub as raised and settled.
- `sminos_rl10.py` — the local endpoint (RL10): discovery, connection, cutover identity, revocations.
- `sminos_rpc.py` — RPCs from members' devices: ordered checks, ledger, execution, outcomes.
- `sminos_sheet.py` — the question sheet's record: its door, reader, step shell and `sheet` verbs.
- `sminos_sheet_step.py` — the question sheet's state machine as a pure function.
- `sminos_subagents.py` — `list --subagents`: each subagent's lifecycle from the bridge, else from disk.
- `sminos_threads.py` — lane A thread records, the lifecycle stamp, the membership reducer and its journal.
- `sminos_tui.py` — the org chart as an interactive terminal screen.
- `sminos_uplink.py` — `daemon uplink`: the endpoint connection, its writer lanes, the main-thread pump.
- `sminos_visibility.py` — `access` and `share`: who may reach a session, as its owner sets it.
- `sminos_wake.py` — what waking a stopped thread reads and says, with no effects of its own.

## Before you change anything

- **`sminos.py`'s module docstring is `sminos help`**, which sessions read: developer facts go at the function.
- **Run a working copy only under a temporary `HOME` and `SMINOS_HOME`**, as `tests/run-sminos-tests.sh` does: `migrate` runs before every verb and changes a real root one way.
- **Older sminos copies share the store and the log on a machine**, so a change of shape must pass `tests/test-older-cli.sh` (needs the network). Every `*.json` at the `$SMINOS_HOME` root is a seat to every copy, so a new store gets a directory of its own.
- **Whose words an event is, is decided in one place.** On a cut-over machine a `human` event is a person's words only by the endpoint's verdict, or an own-operator event by its matching append receipt, because a writer's name is not provenance (a git mirror can merge in a `<machine>/human` line); a machine's notice (`notice_of`, a predicate shared with MAWS) is nobody's words. A new deliverer routes through `words_route` / `WordsGate`.
- **Reach is checked inside the push primitives and fails closed.** Only the uplink, holding the endpoint's one RL10 connection, lets a push through, with a single-use permit (the comment above `_REACH_PERMITS`); a new deliverer leaves the event owed rather than pushing or checking reach itself. A private session whose audience is unknown at its `policyRev`, or whose record is unreadable, writes nothing: the symptom is silence, not an error.
- **A session's policy (`access`, `shares`, `policyRev`) changes only through `sminos_records.set_policy` / `add_owner`**, and every record writer keeps those fields, because the endpoint matches audiences by `policyRev`.
- **Nothing on the uplink's consumer thread, or under a record's store lock, may push, launch, read a view or wait on a lock without a bound**, since a blocked consumer stalls the whole stream and a view reconciles, replaying entries whose locks no deadline bounds: read files as they are and only try locks. The uplink keeps an answer in a file for the daemon's own pass to carry out (`Link.ask_messages`, `sminos_threads.set_channels`).
- **The daemon is the execution boundary for every remote RPC**: a new one goes through `sminos_rpc`'s ordered checks and its at-most-once ledger keyed by `opId`.
- **`daemon/identity.json` is the cutover** and the only enrollment (`hub.json` enrolls nothing); undo it endpoint first (`rl10.json`, its socket), or the next probe cuts over again. A hub project never syncs through git: its remote holds only the archive, and nothing is read back into `log/`.
- **Threads: one reducer, one journal, one lock order.** Membership is read only through `sminos_threads.in_effect` (MAWS's `channel-rule.json` vectors check it); journaled keys change only through `begin` / `finish`, which replay after a crash; locks go wake lock(s) by ascending thread id, `.metalock`, `threads/.lock`, the log's, never reversed (`claim_holds`).
- **`sminos.wake` is the one caller of `run_claude_bg --resume`**, never with a message after the id, since the engine would start a copy or rename the session (`tests/test_wake_seat.py` holds it).
- **A channel is no project.** Its log id is a version-8 UUID (`is_channel_id`), `known_projects` never returns one, and no ordinary traffic (lifecycle, plane frames, host store, outcomes) goes under a channel id, since a thread's facts belong to its project (`tests/channel_wire.py`). A machine holding no channel pays nothing for channels per tick or publish: new channel work goes behind `channels_here()` / `Link.channels` (the `sminos-idle` gate measures it).
- **A channel is keyed by thread, never by session**: its debt, receipts, bridge scope and cursor, because one session may serve one thread and then another. It is delivered only through `deliver_next` / `deliver_verdict` / `deliver_reach` with an `Owing`; a call without one must stay what a project's call was (`tests/test_channels_say.py`'s `SameAsBase` compares with the merge base). No project path writes into a channel: it is spoken in only by naming it.
- **A session's engine files are under its own config dir** (`CLAUDE_CONFIG_DIR`, else `~/.claude`): read one session's through `session_config_dir`, every session's through `engine_record_paths` filtered by `speaks_for`, since a copied dir carries others' records.
- **Caches are module globals cleared per generation in `forget_caches`**, or keyed on their inputs, never on time; a file read through `file_bytes` / `json_at` is written whole by rename, or a stat-keyed read misses the change.
- **On macOS, every look inside a session's or project's directory goes through `read_refused` / `git_refused`, and a child the daemon starts through `launch_refused`**, because a protected folder raises a privacy dialog charged to the daemon, which blocks it.
- **A directory's project is one rule shared with MAWS** (`sminos.decision`), held to vendored vectors; a change MAWS's `deriveOrg` lacks puts one folder in two projects.
- **Contracts with other plugins change in step**: `sminos say` exits 2 only for a usage error, since devcloud reads 2 as a sminos too old for `--notice` / `--pools` (`devcloud/boot/devcloudlib/notices.py`); devcloud's `vm owned-by` and `who --thread` JSON (`sminos_threads.owned_by`); the `owed: <session>` line (`OWED_LINE`) parsed by issue-tracker's `_sweep_api.sh`.
- **A glob over the sminos home wraps the home in `glob.escape`**, since a path holding `[` would match nothing.

## Pinned files and commands

- `tests/vectors/maws/*.json` and their pins are written only by `tests/vectors/maws/sync.sh <MAWS checkout> <commit> [<file>]`; `tests/rl10-conversation.json` is MAWS's fixture copied byte for byte, its source recorded in `rl10-conversation.source.json`. Re-copy, never amend: editing one to pass a test breaks parity with MAWS.
- `tests/run-sminos-tests.sh` is the hermetic suite (the `sminos` gate); `SMINOS_PART=channels` runs the channel suites (the `sminos-channels` gate). `python3 -B tests/rl10_conformance.py` replays the RL10 conversation. `python3 tests/bench_scale.py run <scripts-dir>` (also `tick`, `opens`, `verbs`; `--channels N`) measures the daemon's idle cost, exiting 1 when the scale gate fails.
