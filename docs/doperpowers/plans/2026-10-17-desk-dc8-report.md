# The desk, DC8 — the machine: history and jobs: report (2026-10-17)

Execution of child DC8 of MAWS's composite `docs/doperpowers/specs/2026-10-15-desk-design.md` (branch
`smns-erb`, last pinned at `a87d7fa04`), from its execution document
`docs/doperpowers/plans/2026-10-17-desk-dc8-machine.md` (Progress, Decision Log, Surprises & Discoveries,
Outcomes & Retrospective there are the record; this file is the run's account). Branch `desk-dc8`, version
7.168.0, merged with `origin/main` at `ca793e40` (main reached 7.167.0 while the branch was in review).

## Status

All four milestones were built and reviewed clean.

The whole-branch xhigh panel (wf_23f926ab-0cc) ran in the design session on
`b8f7d19702a6dd13832591427d86dbbff6691060..d5a54a13fa948aa88626fcdf30faa91ad78d1931`.
It confirmed three P2s:
- a delivery refusal lost across the bridge's resync;
- legacy background launches derived `completed` when the state was rebuilt cold;
- a `/clear` retry that could hide a new conversation's agent.

One fix wave fixed all three (`370662a2`, `578b11b8`, `c81b77fc`). reviewer-high read that delta and found that
the launch text could override an explicit `toolUseResult`. That was fixed at `48f254aa`, which is also the
shared-fixture commit DC9 vendors, and reviewer-high's verdict on the fix was "correct".

The PR is open and not merged; the design session merges it.

## Milestones

| | what | commits | review |
| --- | --- | --- | --- |
| M1 | `sminos_jobs.py` (ledger, normalization table, precedence, `derive`, `output_answer`); the shared fixture `tests/sminos/dx4-jobs.json` with `jobs_parity.py` | `38a45f6b`; fixes `8b34237b`, `b7511dd9` | clean after 2 rounds |
| M2 | Offset index per transcript; open, build and pages on a worker per transcript; ended subscriptions stay pageable; `session-ended` only at `n` 0 | `545a8b17`; fix `e0d22d10` | clean after 2 rounds |
| M3 | The mod seeds and refreshes agent state from `$.agent.list()`; a dropped delivery is reported as a second `failed`; G6's `delivered {entered, uuid}` at the bridge | `60e58b42`; fixes `9765fa83`, `f19e3c8f`; merged `5de16866` | clean after 3 rounds |
| M4 | The plane carries `status`, `evidence`, `spawn`, `outcome`, `file`, `jobs` and `mcp`; forwards the bridge's agents; re-derives when the process goes; answers `output` | `21577369`; fixes `ff18df3f`, `4afee326` | clean after 2 rounds |

The controller ran M3 in its own worktree (branch `desk-dc8-m3`) in parallel with M2, then merged it once it was
reviewed clean. M4 was dispatched before M3's last fix wave landed. That was safe because M4 consumes only the
DX5 shapes the fixture fixes.

## Contract changes sent up and recorded in the composite

- `output`'s canonical roots are a set: the slugs of the transcript's project directory, of the log's joined cwd
  and of the engine record's cwd. The engine's temp root is per *original* cwd, so a session that moved into a
  worktree splits its outputs across two slugs. `adoptShellOutputRoot` was struck: in 2.1.300 it is in-process
  `--bg` state, not a setting.
- Containment is exact. The opened file's own path (F_GETPATH / `/proc/self/fd`) must equal
  `<realpath root>/<taskId>.output`.
- A background agent's `async_launched` result counts as `running` evidence.
- An expired monitor ends on its expiry notice: `completed`, with raw word `expired`.
- Task-notifications are read in both of the engine's forms. One is the `queued_command` attachment. The other is
  a plain user row with `origin.kind: "task-notification"`, raw in main transcripts and behind a fixed preamble in
  subagent transcripts. All 4,946 such rows in the newest 300 sessions carry that origin.
- The DX5 seed carries `name` when the list gives one. `delivered.uuid` stays on the bridge's stream.
- The refusal journal is at-least-once.
- The fixture's `about` is normative where DX4 is silent.

## Evidence (commands on the merged tree, `00d1f3c2`+)

- `SMINOS_PART=suites tests/sminos/run-sminos-tests.sh` (through the slot): rc 0, all 85 assertions passed;
  `test_session_plane.py` 107 tests OK; `jobs_parity.py` 71/71 ok.
- `SMINOS_PART=core tests/sminos/run-sminos-tests.sh`: rc 0, all 1776 assertions passed.
- `tests/mods/run-mods-tests.sh`: rc 0, 345 tests, 0 fail; ask search checks passed.
- The M3 executor ran `tests/mods/live-agents-seed-check.py` by hand: 4/4. An agent running across a module reload
  is in the new child's first snapshot, and its end reaches the stream as a stop.
- G1 measurements (`tests/sminos/measure_pages.py`, copies under a temporary HOME, machine load 213–343
  throughout), in the execution document's Surprises & Discoveries:
  - The index build takes 0.76 s against one full parse of 2.80 s before DC8 (coordinator copy, 179 MB, 13.7k
    rows).
  - Pages, timed daemon-side: median 11–15 ms, p95 73–200 ms. 4 of 95 and 5 of 476 exceed 200 ms. Those
    pages re-run in process in 1.5–5 ms.
  - Heartbeat answers stay at or below 51 ms in every phase. Presence stays at or below 315 ms. Deliveries peak at
    422 ms during pages, with none lost.
  - With M4: the first snapshot of the coordinator session takes 3.4 s, about 1.9 s of it the first disk-facts
    look (once per process). An agent-scope snapshot takes 773 ms. The first read of the main ledger for an
    agent-scope subscription takes 0.8–1.4 s, once per process, off the uplink's thread.

## Friction

- The session's worktree guard refuses a shell-level `HOME=` assignment, and refused several reviewers' isolated
  probes. Tests set `HOME` and `SMINOS_HOME` in-process, as `test_session_plane.py` already did. No reviewer
  worked around the guard, so some reviews rest on inspection plus the executor's runs.
- The machine sat at load 130–630 all day. The design session ruled that G1's page bound is judged on the page's
  own work, with the distribution reported alongside the load.

## Residue (for tickets)

- **Carry `delivered.uuid` to the web.** The bridge emits `delivered {entered, uuid}`, but neither the plane nor
  DX4 carries it. It matters only if the engine ever rewrites a delivery frame, since the web matches by the
  frame's `(writer, seq)`.
- **MAWS's backfill reads neither the subagent-preamble form of a task-notification nor the origin gate.** Nested
  agents' notifications are lost there. The design session noted this for the parked S2 work.
- **Adopted shells' outputs are refused.** A `--bg` session that took over another session's shells writes under
  a root nothing on the machine names. This needs an engine-visible record of the adoption before it can be
  served.
- **`sminos_plane.py` is about 1,700 lines.** The disk-facts code (about 250 lines) could move to a module of its
  own.
- **The first snapshot of a very large session waits for the disk-facts look** (about 1.9 s on the coordinator
  session). If that proves noticeable, the alternative is a snapshot first and a `subagents` correction after,
  which the design session rejected for now.
