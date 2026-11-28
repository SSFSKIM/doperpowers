# sminos/skills/sminos/scripts/ — the sminos CLI, the daemon and its uplink

Paths are named from `sminos/`. A module's docstring states how it works and the rules that bind it; the spec it cites says why. This file names the places that bite and where their rules are written.

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
- `sminos_jobs.py` — subagents, background jobs and MCP status, from transcript rows and the bridge's and engine's facts.
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

## Where to stop and read first

Each entry names an area where a plausible change breaks something across modules, and where its rule is stated exactly. Read that before changing the area.

- **`sminos help`**: it is `sminos.py`'s module docstring, which sessions read. Put developer notes at the function.
- **The state root and migration**: `main` migrates the root before most verbs, one way; some verbs dispatch first. Read `migrate`'s docstring and the head of `main`. Try a working copy under a temporary `HOME` and `SMINOS_HOME`, as `tests/run-sminos-tests.sh` does.
- **Older copies on one machine**: they share the store and the log. Read the comment in `record_files` before adding a file at the `$SMINOS_HOME` root, and run `tests/test-older-cli.sh` (it needs the network) after a change of shape.
- **Whose words an event is**: `words_route`, `WordsGate` and `notice_of`. Read them before adding a deliverer or changing what counts as a person's words.
- **Reach and who may push**: `sminos_audience.reach_capable`, `audience_of`, `deliver_reach` and the comment above `_REACH_PERMITS`. Read them before changing a push path.
- **A session's policy**: `sminos_records.set_policy` and `add_owner` (both move `policyRev`, which the endpoint's audiences are matched by). Read the module docstring before writing a record.
- **The uplink's consumer thread and channel verdicts**: `Link.on_reach`, `keep_channel_word` and `sminos_channels.carry_words`. A blocked consumer stalls the stream; read them before adding work there.
- **Remote RPCs**: the `sminos_rpc` module docstring (ordered checks, the `opId` ledger). Add an RPC there.
- **Cutover and enrollment**: the `sminos_rl10` docstring and `sminos_daemon.UplinkSupervisor` (how to undo a cutover). A hub project's git remote is its archive: `sminos_archive`'s docstring.
- **Thread records**: `sminos_threads`' module docstring, `Fold`, `begin` / `finish`, `set_channels`, and the lock order at `claim_holds` and `claims_held`. Read them before changing membership, a record or a lock.
- **Waking a session**: `sminos.wake`, which `tests/test_wake_seat.py` holds to its `--resume` call.
- **Channels**: the `sminos_channels` module docstring, `known_projects`, `speak`, `record_in_pools`, and `sminos_holder_deliveries.key_hash` (a receipt's key includes the session; a channel's debt is the thread's, `sminos_channels.owed`). `tests/channel_wire.py` and `test_channels_say.py`'s `SameAsBase` hold the wire and the project path.
- **Engine files**: the comment block on the engine's config dirs in `sminos.py`, `session_config_dir`, `speaks_for`, `engine_spare`.
- **Caches**: `forget_caches` and `file_bytes`. Read both before adding a cache or a file read through it.
- **macOS protected folders**: the section comment in `sminos.py`, `read_refused`, `git_refused`, and `launch_refused` (for a child sminos starts on its own). A wrong read blocks the daemon on a privacy dialog.
- **A directory's project**: the section comment on the project rule in `sminos.py` and `decision`; MAWS applies the same rule, held by vendored vectors.
- **Contracts with other plugins**: devcloud reads a host's `say` exit codes (`devcloud/boot/devcloudlib/notices.py`, the comments in `cmd_say`) and `who --thread` / `vm owned-by` (`sminos_threads.owned_by`); `skills/issue-tracker/scripts/_sweep_api.sh` parses `OWED_LINE`.
- **Globs over the home**: the existing calls wrap the root in `glob.escape`, since a `[` in the path breaks a pattern.

## Pinned files and commands

- `tests/vectors/maws/*.json` and their pins are written by `tests/vectors/maws/sync.sh <MAWS checkout> <commit> [<file>]`; `tests/rl10-conversation.json` is MAWS's fixture, its source in `tests/rl10-conversation.source.json`. Re-copy them; an edit breaks parity with MAWS.
- `bash sminos/tests/run-sminos-tests.sh` (from the repository root) runs the hermetic suite; `SMINOS_PART=core|suites-a|suites-b|suites-c|channels` picks the part a CI gate runs (`.github/ci-kit.yml`).
- `python3 -B sminos/tests/rl10_conformance.py sminos/skills/sminos/scripts sminos/tests/rl10-conversation.json` replays the RL10 conversation.
- `sminos/tests/bench_scale.py` (`run`, `tick`, `opens`, `verbs`, each given the scripts directory) measures the daemon's idle cost; `.github/ci-kit.yml`'s `sminos-idle` has the gate's arguments.
