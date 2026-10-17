# The desk, DC8 — the machine: history and jobs: execution (2026-10-17)

> **Composite:** MAWS `docs/doperpowers/specs/2026-10-15-desk-design.md`
> (branch `smns-erb`; on this machine
> `/Users/new/Developer/GitHub/MAWS/.claude/worktrees/smns-erb/`), child
> **DC8** (The machine — history and jobs — plan). **Parent pin:** commit
> `62bd81840`, blob `f24db648ce8db120fa1ba93fb8f82f11ed7faba6` of that file
> (re-pinned 2026-10-17 from `77e82d832` to `f60dd668b` — the review's
> round 2, DX4's precedence and `output`'s `missing` with `path: null` —
> and then to `896f04acc`, which records this document's two pre-flight
> decisions and adds their fixture cases).
> The child's section there is its design; this document carries only the
> constraints and the milestones. Read before M1: the composite's §9 (all
> of it), the DC8 child section, DX4's 2026-10-17 rows and its three
> subsections "History and ended sessions", "Jobs and agent status" and
> "`output`", DX2's `output` frame, DX5's "For DC8 [2026-10-17]" and the
> parts of DX5 they rely on (the snapshot's `agents`, the `agent` events,
> `delivered`), and the 2026-10-17 Decision Log entry. Evidence:
> `docs/doperpowers/specs/2026-10-17-desk-session-view-survey.md` beside the
> composite. DC7's execution document
> (`docs/doperpowers/plans/2026-10-15-desk-dc7-controls.md`, this repo) is
> the record of the plane this child extends.

## Progress

- [x] M1 — The jobs ledger, the normalization table, `output`'s containment, and the shared fixture (DC8.G3's and G4's derivations) — reviewed clean 2026-10-17 (`38a45f6b`, fix `8b34237b`)
- [ ] M2 — The offset index, pages and the open off the uplink's thread, ended sessions pageable (DC8.G1, G2)
- [ ] M3 — The bridge: the `$.agent.list()` seed and refresh; a refused submission reported as a `failed` delivery (DC8.G3's seed, G5; G6 optional)
- [ ] M4 — The plane carries status, jobs and MCP names, the bridge's agent state forwarded, and answers `output` (DC8.G3, G4)

## Constraints that bind every milestone

- **The composite has one writer**, the design session that dispatched this
  child. This document's controller records decisions here and messages
  that session with any that touches a contract (DX4 as producer, DX2's
  `output` as consumer, DX5 as the owner of the seed and the refusal
  report); it never edits the composite. A contract that proves wrong goes
  to that session.
- **Where the code lives.** `skills/sminos/scripts/`: the plane
  (`sminos_plane.py`), the uplink (`sminos_uplink.py`, only a frame handler
  for `output`), the bridge child (`sminos_bridge.py`), delivery outcomes
  (`sminos_outcomes.py`); the mod (`hooks/mods/bridge.tsx`,
  `hooks/mods/bridge-stream.tsx`, `bridge-state.tsx`). New derivation code
  goes in a module of its own (`sminos_jobs.py`), pure: rows in, facts and
  the DX4 body out, no file or socket of its own beyond what its callers
  hand it, so the shared fixture drives it directly.
- **Other work in flight touches the same files.** A cheaper-tick PR
  changes the uplink's per-session `ps` and member reads (not `metas()` or
  the subscription paths); a titles PR changes the daemon and `sminos.py`.
  Keep edits to `sminos.py` and `sminos_uplink.py` to the seams this child
  needs (a handler, a call), so the merge of `origin/main` before the final
  push stays mechanical.
- **Stdlib Python**, as the daemon is; no dependency is added.
- **Isolation (the machine's rules; every worker and reviewer is bound).**
  Any run of sminos code — CLI, daemon, uplink, plane, bridge child,
  in-process import, probe — uses a temporary `HOME` and `SMINOS_HOME`.
  Reading the real `~/.claude/projects`, `~/.claude/sessions` and
  `~/.claude/sminos` for evidence is fine (with `python3 -I`, a script kept
  outside the data's directory); writing to them or running sminos against
  them is not. Leave the running daemon, uplink, bridges and sessions
  alone; never touch `~/.claude/settings.json`, `~/.claude.json` or the
  installed plugin; never call the deployed hub or deploy; never read
  `~/.config/claude-secrets` or print `~/.claude/sminos/daemon/hub.json`.
  Heavy commands run one at a time inside
  `/tmp/maws-review/with-slot.sh <command…>`: the suites
  (`SMINOS_PART=suites tests/sminos/run-sminos-tests.sh`,
  `SMINOS_PART=core …`), `tests/mods/run-mods-tests.sh`, and any
  measurement over a large transcript. Commit by explicit paths, no
  Co-Authored-By trailer, never rewrite history; an action denied is
  reported, not worked around.
- **Evidence for G1** is measured, not argued: a transcript of at least
  150 MB and 10,000 rows (a synthetic one the test writes, and a copy of
  the coordinator session's transcript under a temporary `HOME` for the
  recorded figure), the uplink against the hub stand-in
  (`tests/sminos/hub_standin.py`), heartbeat answers timed throughout.

## Plan of Work

### M1 — The jobs ledger, the normalization table, `output`'s containment, and the shared fixture

Owns the derivations both producers share, so DC9's fake machine can vendor
the fixture while M2–M4 build. Nothing here touches the plane's threads or
the wire.

- `sminos_jobs.py`: DX4's normalization table (raw word → `status`,
  terminal) as data; a ledger that ingests one loop's transcript rows in
  file order and keeps only what the body needs — the `tool_use` calls of
  `Agent`/`Task`, `Bash`, `Monitor` and `TaskStop` by id (their input's
  description and command), `tool_result`s for those ids (with
  `toolUseResult`), task-notifications (a user row's `queued_command`
  attachment with `commandMode: "task-notification"`: `<task-id>`,
  `<tool-use-id>`, `<output-file>`, `<status>`, `<summary>`), `task_status`
  attachments, `mcp_instructions_delta`, and each row's timestamp as `at`;
  the same ledger, fed a parent agent's transcript, yields a nested
  agent's outcome. A `derive(...)` that joins a ledger with the metas, the
  bridge's agent state (its snapshot's `agents` and `agent` events, with
  `running`), the agent files' facts, the nested agents' parent ledgers (or
  that a parent's transcript is gone or unreadable) and whether the
  session's process runs, and returns the widened body: `subagents` (one
  entry per meta, in the metas' order, with `status`, `evidence`,
  `running?`, `spawn?`, `outcome?`, `file?`), `jobs`, `mcp`, by DX4's
  precedence. Every status word, evidence word and field shape is DX4's.
- The task-id → output-path map the ledger keeps (the latest path the rows
  named for each task: a `task_status`'s `outputFilePath`, a
  notification's `<output-file>`, a Bash result's "Output is being written
  to:") and `output_answer(...)`: given the request, the ledger, the
  session id and the canonical roots the caller derives, the DX4 `output`
  body — `unknown-task`, `missing` with `path: null` for a known task no
  row has named a file for yet, `refused` (suffix, containment of the
  opened target's realpath in whole path components, a regular file),
  `missing` with the path, `ok` (the last `tail` bytes read backward from the end, cut forward to
  the first line break inside the window when the window does not start the
  file, decoded UTF-8 with replacement, `from`, `size`, `truncated`).
  Deriving the roots from machine state is M4's; this function takes them
  as a list (see the Decision Log, 2026-10-17, on the roots).
- **The shared fixture**, `tests/sminos/dx4-jobs.json`, and its runner
  `tests/sminos/jobs_parity.py` (`ok <name>` / `FAIL <name>` lines, as
  `codes_parity.py`), wired into `run-sminos-tests.sh`'s suites. Each case:
  the inputs (main rows; each agent file's rows, size and `mtimeMs`, or
  `null` for a file gone; the metas; the bridge's agent state or `null`
  for no bridge; whether the session runs) and the expected `{subagents,
  jobs, mcp}`. It holds at least: the module-reload case (agents that ran
  before the bridge loaded, one still running and known only from the
  seed); a nested agent whose parent still runs; a nested agent under an
  ended parent (`exited`); a cold open of an ended session holding an
  agent with a `running` status and no completion notification (`exited`);
  a background agent's launch result that does not end it (a bridgeless
  running session's agent with only its `async_launched` result →
  `running`; the same in a cold open of the ended session → `exited`);
  each raw word of DX4's table, and an unrecognized word that changes
  nothing (kept in `outcome.raw`); each of the three `unknown` cases §9.3
  names; a background Bash and a Monitor started before the subscription
  with their notification, `task_status` and `TaskStop` ends, and a monitor
  just started with no path; MCP names added and removed. Its `output`
  cases describe a file layout under a placeholder root (regular files,
  symlinks) both implementations materialize in a temporary directory, and
  hold an unknown task, a deleted file (`missing` with its path), the
  just-started monitor (`missing` with `path: null`) and the same request
  once a `task_status` names its file (`ok`), a symlink whose target keeps all
  three suffix components elsewhere, a path under the original cwd's slug
  for a session whose transcript lives under another slug (`ok`, the roots
  given as the case's input), an ordinary symlink to a file of
  another name, an agent task's `.output` symlink into a transcript, a path
  other than the one the rows named, a window inside a file (cut at a line
  break, `truncated`) and a whole small file. The fixture states its rule
  in an `about` field and is self-describing enough to vendor (DC9 copies
  it); rows in it are shaped as the engine writes them (2.1.300), taken
  from real transcripts with their content cut down.
- On commit, the controller messages the design session the fixture's path
  and commit (DC9 vendors it).

Proof: `jobs_parity.py` all `ok`; unit tests of the ledger for incremental
ingestion (rows fed in two batches give the same facts as in one).

### M2 — The offset index, pages and the open off the uplink's thread, ended sessions pageable

- **The index** (beside `Tail` in `sminos_plane.py`): per transcript file
  (path and inode), each row's uuid, byte offset and length in file order,
  extended from where it stopped; shared by every subscription on that file
  and kept a while after the last one goes (a small LRU), so a second
  subscription, or the same browser subscribing again, builds nothing; a
  file replaced or shrunk drops it (its subscriptions end `discontinuity`
  as today, by their `Tail`). Measure whether anything cheaper than
  `json.loads` of each line finds the top-level uuid reliably (a tool
  result's own JSON can carry a nested `uuid`); keep the parse otherwise —
  the bound is one full parse today.
- **The thread.** Every read of a transcript's bulk — the open's build
  (index extension, the cut's position, the history's newest rows that fit
  `ROWS_BUDGET`, the rows past the cut), each page, and (M4) `output` and
  the disk facts — runs on a worker per transcript, serialized there, and
  hands its result to a queue the uplink's `tick` drains, as `diff` does
  today; the main thread never parses more than the bytes flushed since its
  `Tail` last read. The `Tail` of a subscription starts at the offset the
  open's build reached. A page reads only its own rows' bytes (one seek,
  one contiguous read of the span between the first and the last), after
  extending the index so rows flushed after the open are pageable.
- **Ended sessions.** `finish` no longer ends the subscription: once the
  process is gone and what it flushed is drawn (`END_GRACE`) the
  subscription stays, transcript-only and idle, answering `rows` (and, M4,
  `output`) until `unsubscribe`, the stream's end, or a discontinuity — a
  bridge answering for the session again ends it `discontinuity`, as
  `tick` already does for a transcript-only one. A subscribe to a session
  with no process is served a snapshot from disk and pages the same way.
  `end {session-ended}` goes only at `n` 0, for a session whose transcript
  this machine does not hold.
- **Proof.** `test_session_plane.py` updated where it pinned the old
  `session-ended` and extended: pages to the first row on a live and on an
  ended session (rows flushed after the open included), a second
  subscription building nothing, a replaced or shrunk transcript ending
  `discontinuity`, `session-ended` only at `n` 0, Resume's discontinuity.
  A measurement script (`tests/sminos/measure_pages.py`, not in the
  suites; run by hand) on a synthetic ≥ 150 MB, ≥ 10,000-row transcript
  and on a copy of the coordinator session's transcript: the index build
  against one full parse today, every page's latency from the frame's
  arrival over paging to the first row (≤ 200 ms each), and, with the
  uplink against the hub stand-in, the heartbeat answers' and presence's
  latencies while a subscribe builds and while pages run (DX2's bounds;
  DC7.G1's 1 s). The figures go into this document's Surprises &
  Discoveries.

### M3 — The bridge: the `$.agent.list()` seed and refresh; a refused submission reported as a `failed` delivery

Independent of M2 (different files); runs after it in the shared worktree.

- **The seed** (DX5 "For DC8"): at the module's load the mod seeds its
  agent state from `$.agent.list()` (`id`, `description`, `type`,
  `status`, `parentId`) and refreshes it while any agent runs, as
  `hooks/mods/agents.tsx` does, emitting `agent` spawn and stop for what it
  learns (an agent the spawn hook already reported is not spawned twice; a
  seeded spawn carries what the list gives — `{parentAgentId,
  subagentType, description, name}` — and no field the list does not
  have). The resync's `agents` carries them, so the child's snapshot does.
  The refresh rate lets a status reach the plane within DC8.G3's 1 s.
  Tests in `tests/mods/bridge.test.ts` (a faked `$.agent.list()`); a live
  check of the module-reload case if DC2's live-check pattern
  (`tests/mods/live-*-check.py`) runs here, by hand.
- **The refusal report** (G5): the child keeps a `delivered {outcome:
  "refused", reason}` with its key in what it keeps (`<id>.json`, bounded),
  and the delivery path reports it: for an outside-origin event of a hub
  project whose push was `delivered`, a second outcome for the same key and
  session, `failed`, with the bridge's reason, recorded once, on the
  delivery path's next pass (a call from `deliver_next`'s pass into
  `sminos_outcomes`; `sminos.py` keeps only that call). Tests beside DC7's
  delivery-outcome tests (`test_policy_requests.py`).
- **G6 (optional):** `delivered {outcome: "entered", uuid}` when the mod
  can name the submitted prompt's row from `session.append` without
  guesswork; otherwise left, and said so in the report.

### M4 — The plane carries status, jobs and MCP names, the bridge's agent state forwarded, and answers `output`

Consumes M1 (the ledger and `derive`), M2 (the worker and the index) and
M3 (the seeded `agents`).

- The open's build feeds the loop's rows to a ledger (on the worker), and
  the subscription keeps feeding it the rows its `Tail` reads afterwards
  (main thread, a few rows at a time). The disk facts — metas, each agent
  file's `{size, mtimeMs, firstAt, lastAt}`, and each nested agent's
  parent ledger — are refreshed on the worker every `METAS_EVERY`, each
  file stat'ed and read only when its size or mtime changed (the metas
  included: no meta file is opened twice for the same (size, mtime)).
- `event()` keeps the bridge's agent state: the snapshot's `agents` and
  every `agent` spawn and stop. The bridge's `running` stops counting once
  the session's process is gone: every entry is re-derived when presence's
  `record` goes null and a `subagents` message goes for what changed.
- The snapshot carries `subagents` widened, `jobs` and `mcp`; a
  `subagents` message goes whenever the derived body changes (a status, a
  job, a name, a meta). An agent-scope subscription carries its own
  agent's entry and its own loop's jobs.
- `output`: the uplink's handler for DX2's `output` frame, the plane's
  `output(frame)` checking the sub, `taskId` (`[A-Za-z0-9_-]{1,64}`) and
  `tail` (1–524288), the canonical roots derived from machine state (see
  the Decision Log), and the read on the transcript's worker; the answer is
  DX4 `output` on the sub. An idle (ended) subscription answers it too.
- **Proof.** `test_session_plane.py`: a session whose agents ran before
  the bridge (no `agent` events, the snapshot's `agents` seeded), nested
  agents with their parent running and over, a background Bash and a
  Monitor started before the subscription ending on their notification,
  `task_status` and `TaskStop`, a status reaching `subagents` within 1 s
  of its evidence on disk or on the stream, `output`'s four variants
  through the uplink against the hub stand-in, and a large session's agent
  files stat'ed, not read, on an unchanged check (counted). The fixture's
  cases pass through the plane's own path, not only `jobs_parity.py`.

### After M4 (the controller)

Merge `origin/main`; bump the version (`scripts/bump-version.sh`, the next
free above main) in the same commit as the last change; the whole-branch
review through `doperpowers:review-code` at `high` (the composite names no
rung for DC8); the PR opened, not merged; the report at
`docs/doperpowers/plans/2026-10-17-desk-dc8-report.md`.

## Interfaces and Dependencies

- M1 → M4: `sminos_jobs.Ledger` (rows in, in file order; copyable),
  `sminos_jobs.derive(...)`, `sminos_jobs.output_answer(...)`.
- M2 → M4: the per-transcript worker and its job queue, the index, the
  open's result handing the subscription its `Tail` offset (and, in M4, the
  ledger).
- M3 → M4: the child's snapshot `agents` carrying seeded agents with
  `running`.
- DX4 (producer), DX2 `output` (consumer), DX5 (the seed and the refusal
  report, owner).

## Decision Log

- Decision: Four milestones, M1 the pure derivation and the shared fixture
  first so DC9 vendors it early; M3 (the bridge) independent of M2; M4
  consumes all three.
  Rationale: the fixture is DC9's input; the plane's threading and the
  derivation are separable, and the derivation is the part both producers
  must agree on.
  Date/Author: 2026-10-17, controller (pre-flight).
- Decision: **The canonical roots for `output` are a set, all derived from
  machine state.** For session `S` with transcript
  `~/.claude/projects/<slug>/S.jsonl`, the roots are
  `<realpath(CLAUDE_CODE_TMPDIR or /tmp)>/claude-<uid>/<k>/S/tasks/` for
  each `k` in: the transcript's project directory name; the engine's slug
  (DX4's §35.2.1 rule: every character outside `[A-Za-z0-9]` → `-`, past
  200 characters cut with the base-36 hash of the original path) of the
  cwd the session joined the project with (the log's `joined`, the plane's
  `here`); and the slug of the cwd in the session's engine record when it
  runs. Plus `<adoptShellOutputRoot>/S/tasks/` when the engine's settings
  name one. The suffix check (`S/tasks/<taskId>.output`) and the realpath
  containment are unchanged.
  Rationale: DX4 derives one root from the transcript's project directory,
  but the engine's temp root is per *original* cwd (`QP() = ynn(ke())`,
  SPEC ch. 16, 20) and a session that moved into a worktree has its
  transcript under the worktree's slug while its earlier tasks' files stay
  under the launch cwd's: in the coordinator family's session
  `bd52b087…` (read-only, 2026-10-17) the rows name 387 output paths under
  `-Users-new-Developer-GitHub-doperpowers/bd52b087…/tasks/` and 137 under
  `…--claude-worktrees-sminos-family/bd52b087…/tasks/`, the transcript
  being in the latter's project directory. One root would refuse most of
  that session's shells. Every root is still derived from this machine's
  own state (the transcript's location, the log, the engine's record),
  never from a row, so the containment's purpose holds. 43 paths in that
  transcript name another session id (`cd5fc75d…`); they stay refused by
  the suffix rule. Reported to the design session as a DX4 correction.
  Date/Author: 2026-10-17, controller (pre-flight, from the evidence).

- Decision: **A background agent's launch result is `running` evidence
  from the rows** (`outcome {status: "running", raw: "async_launched"}`,
  `evidence: rows`), not terminal and not nothing.
  Rationale: DX4 says the result row of a background agent "is its start
  and does not count" as terminal, and its table has no row for the
  result's `status: "async_launched"`; read as no evidence, a background
  agent of a running session without a bridge would be `unknown` though
  its call has a result, which is none of the three named `unknown` cases.
  The launch is the engine's own word that the agent started, so it is
  start evidence at precedence (3), below every terminal word and below
  known process death. Reported to the design session.
  Date/Author: 2026-10-17, controller (pre-flight).

- Decision: **`output` containment is exact** — the opened target's
  realpath must equal `<realpath of a root>/<taskId>.output` (a strict
  subset of DX4's component-prefix rule; every engine-written path
  passes), so a symlink to another task's file in the same root is
  refused. Sent to the design session as a DX4 correction.
  Rationale: the prefix rule admits a sibling task's file, which is "a
  path other than the one the rows named" in G4's sense.
  Date/Author: 2026-10-17, M1 executor; adopted by the controller.
- Decision: **What M1 settled where DX4 is silent** (each pinned in
  `tests/sminos/dx4-jobs.json`'s `about`, which DC9 follows): an
  unrecognized word replaces only `outcome.raw` and is dropped with no
  outcome yet; a notification with no `<status>` (monitor events, expiry,
  resumes) is no evidence; an Agent result's raw word is `async_launched`,
  else `error` on `is_error`, else `toolUseResult.status`, else
  `completed`, and a non-error TaskStop's is `stopped`; once the process
  is gone `running` is dropped and `spawn` kept; within precedence (2)
  session death, then parent ended, then bridge stopped, within (3) the
  bridge before the rows; a job starts at its call row's time, `endedAt`
  only on a terminal word, `summary` from the deciding row; an MCP
  delta's removals before its additions; an output window with no line
  break is not cut; an open error other than `ELOOP` is `missing`. The
  fixture carries the bridge's agent *state* (with `running`), not its
  events; folding `agent` events into it is M4's. An agent-scope
  subscription needs two derivations (its own entry from its parent loop's
  ledger, its jobs and MCP names from its own).
  Date/Author: 2026-10-17, M1 executor (report `task-1-report.md`).

- Decision: **An expired monitor ends on its expiry notice**: a
  task-notification for a monitor task with no `<status>` whose `<event>`
  begins `[Monitor expired after ` or is `[Monitor timed out` is terminal —
  `completed` (the word MAWS's backfill gives a statusless notification,
  `backfill.ts:678-682`), raw `expired`, `endedAt` the notice's time,
  `summary` the event text. Other statusless notices stay no evidence.
  Rationale: the jobs view shows what is running; a 30-minute monitor
  shown running for hours defeats it (the design session, 2026-10-17).
  The notice is recognizable by shape, so no clock on `timeoutMs` is
  needed. Built in M1's fix wave, pinned by a fixture case.
  Date/Author: 2026-10-17, design session's ask; route chosen by the
  controller.

- Decision: **What M2 settled.** A page's (and the snapshot's) 512 KB
  budget counts each row's line bytes as the engine wrote them, so a page
  picks its span without parsing anything else. Lines without the bytes
  `"uuid"` are not parsed, in the index and in `Tail` (a top-level `uuid`
  key is always written so; a nested one only makes the line parsed, and
  the parse decides). The index registry is process-wide (`TRANSCRIPTS`,
  an LRU of 4), so it outlives a stream's reconnect, and the uplink is
  untouched. The worker's answers return on each subscription's own queue,
  drained by `pump`. An ended subscription keeps tailing its transcript,
  transcript-only: a Resume without a bridge streams into it; one with a
  bridge ends it `discontinuity` through `tick`'s existing check.
  `session-ended` is decided at the open (no process and no file for the
  subscription's transcript). A read failure ends the subscription
  `error`, a `Reset` `discontinuity`. The hub stand-in's heartbeat runs on
  a timer (every frame down used to postpone it, so none went out while
  pages ran). M4's seam: `Index.extend(on_row=…)` and the `Built` result,
  to which M4 adds the ledger copy exact at the offset the `Tail` continues
  from.
  Date/Author: 2026-10-17, M2 executor (report `task-2-report.md`).

## Surprises & Discoveries

- Observation: a session's task output paths name more than one project
  slug, and some name another session id, though every row's `sessionId`
  is the session's own.
  Evidence: `bd52b087-3acb-4630-be84-d87c9982dfdf.jsonl` (the
  `sminos-family` worktree's project directory), read with `python3 -I`
  2026-10-17: 387 paths under the launch cwd's slug, 137 under the
  worktree's, 43 under `cd5fc75d…`. See the Decision Log on the roots.

- Observation: `$.agent.list()` has no `name`; DX5's seed shape lists one.
  Evidence: `hooks/mods/agents.tsx:331-345` reads `{id, description, type,
  status, parentId}`. The derivation passes through whatever spawn fields
  the bridge entry has. Told to the design session.
- Observation: about 5,089 of 12,077 metas on this machine are of the
  older form with no `requestShape`; a background agent there is known as
  such only from `spawn.background` or its launch result.
  Evidence: read-only count, 2026-10-17 (M1 report).
- Observation: an expired monitor's notice carries no `<status>`; its
  `<event>` is one of the engine's fixed texts (`[Monitor expired after
  <dur> with … delivered. …]`, or the older `[Monitor timed out — re-arm
  if needed.]`; engine 2.1.300 `cli.pretty.js:900351-900352`, `dEr`).
  Seen 2 times in 300 recent transcripts, beside 26 statusless event
  notices. See the Decision Log on expiry.

- Observation: **G1's figures** (`tests/sminos/measure_pages.py`, copies
  under a temporary `HOME`, the machine under heavy load — load average
  216–267 — throughout). Index build against one full parse before DC8:
  synthetic 160 MB / 16,606 rows 0.62 s vs 1.00 s; the coordinator's copy
  178.9 MB / 13,683 rows 0.76 s vs 2.80 s; MAWS's 256 MB / 51,314 rows
  1.98 s vs 3.77 s; a second subscription builds nothing (its snapshot in
  7–22 ms). Pages from the newest row to the first line, frame sent to
  answer back: medians 8–16 ms, p95 21–95 ms; over 200 ms: 0 of 156
  (synthetic), 2 of 94 (coordinator, max 286 ms), 7 of 476 (MAWS, max
  750 ms) — the slow ones re-run at 1.3–1.7 ms in process (a page's read
  0.1–0.2 ms, its parse 1.3–2 ms), so scheduling stalls under that load;
  a run on a quiet machine settles the figure. Heartbeat answers at most
  26 ms in every phase; presence at most 443 ms, the build phase no slower
  than idle.
  Evidence: `task-2-report.md`, "G1 figures".
- Observation: 129 of the coordinator transcript's 178 MB are records with
  no `uuid` (`api-request` 110.6 MB, `api-request-blob` 8.8 MB); skipping
  them cut the parse from 3.15 s to 0.62 s. On MAWS's transcript rows are
  232 of 256 MB, so the skip saves little there.
  Evidence: `task-2-report.md`.

## Outcomes & Retrospective

(Written at the end.)
