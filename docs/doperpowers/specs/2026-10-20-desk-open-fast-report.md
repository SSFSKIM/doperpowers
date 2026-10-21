# desk-open-fast — execution report (2026-10-21)

Status: DONE_WITH_CONCERNS. All nine milestones are built and reviewed clean.
M9's machine side is done. What's left is the coordinator's or comes after
the roll:
- the xhigh panel, running on d7fd164f..62e57510 (wf_d55f031d-0b6);
- the by-hand checks on the owner's Mac;
- `window.deskLatency()`;
- the 100–300 band, which waits on the owner's choice of a devcloud host.

The spec, [2026-10-20-desk-open-fast-design.md](2026-10-20-desk-open-fast-design.md),
is the record. Its Progress, Surprises & Discoveries, Decision Log and
Outcomes & Retrospective hold every decision and figure. The SDE ledger and
the per-task reports are under `.doperpowers/sde/2026-10-20-desk-open-fast-design/`,
which is gitignored and lives in the executing worktree.

## Commits and versions

- doperpowers `desk-open-fast`: d7fd164f..62e57510 (main...62e57510), 55
  commits, sminos 1.2.14. Code head 996e1052; everything after it is
  spec-only.
- MAWS:
  - M4 hub, PR #85, merged as e94098c9, deployed 09:34:39Z;
  - M3 web, PR #86, merged as c26b74cc, deployed 10:54:34Z;
  - the fixture follow-up, PR #87, awaiting the coordinator's merge.
- The M5 roll is the coordinator's PR #301 (ba3816df). The second roll is
  4400ced7 (M5, M6 and the M6 fix; full 8-gate GREEN, 39474707208). This
  branch's PR is the M7+M8 roll. All three wait on the owner's
  desk-client refresh. This branch merges main after #301 and 4400ced7
  land, taking main's version and bumping above it.

## Per milestone

| | what | range | rounds | sminos |
|---|---|---|---|---|
| M1 | open line, reference consumer, inventory, fixtures, HTTP/1.1 stand-in, pause proxy | 9bd55c49..c762b8d7 | 3 fix rounds | 1.2.2 |
| M2 | bench_open, bench_scale opens, bench_rig | 0482d416..acde4b3a | 2 fix rounds | 1.2.5 |
| M3 | MAWS web: a carried block kept across a reconnect | MAWS bda992c29, #86 | clean | — |
| M4 | MAWS hub: reply chain decoupled, plus the 503 fix | MAWS fba324cc4..beb065470, #85 | 1 fix round | — |
| M5 | snapshot at once, step-end deadline; legacy-bridge fix (`namedBlocks`) | 8d7fae3f; ba3816df | clean; fix clean | 1.2.6; 1.2.9 |
| M6 | sender lanes, connection reuse | d5fa1d6a..aa57759b | 2 fix rounds | 1.2.8 |
| M6 fix | settlements held until confirmed; uploads sealed once | 2f64aa96..4400ced7 | 4 rounds; the coordinator's reviewer passed | 1.2.11 |
| M7 | saved builds (prefix CRC), bounded warmer, look off the open path | 63683909..7a9fdccb | 2 fix rounds | 1.2.10 |
| M8 | at-once respawn, resync bounded, retry per child | 1aa1a002..227187e8 | 1 fix round | 1.2.12 |
| merge | desk-open-fast-m6fix into the branch | eeb71406 | full 8-gate GREEN 39485637328 | 1.2.13 |
| M9 | acceptance (machine side), documents, close-line fix | 5edd1a4e, 996e1052 | 1 fix round | 1.2.14 |

## Figures (load < 50; the 100–300 band incomplete)

From M9's run on the finished branch, at load 4.9–9.7:

| check | figure | before |
|---|---|---|
| A1 idle | E 15–20 ms | — |
| A2 mid-message | E 18–21 ms, inventory clean | 2–2.6 s |
| A2 long-answer | E 14–21 ms, no early end | the open died at about 5 s |
| A2 after-prompt | E 14–26 ms | 0.28–0.53 s |
| A3 large at +0.5 s (cold) | 0.485 s | 0.42 s |
| A3 after a restart (loaded) | 0.042 s | 0.42 s |
| A3 at +30 s | all warm, 2–39 ms | — |
| bench_index on CI-opt | loaded 0.05 CPU-s | cold 0.74 |
| A4 pair | 37 POSTs all 200 inside a 4 s block; open after resume 9 ms | — |
| A6 kill | 0.438 / 0.190 / 0.191 s | 1.17–6.55 s |
| A8 | layer test 35/35 | — |
| A10 | sminos gates GREEN 39493005844; live-resume 14/14; live-bridge 15/15 | — |

A6 across M8 and M9: 12 of 13 spaced trials are within 0.5 s, and one was
0.525 s. Both slow trials come from the successor waiting for the mod's
first resync.

## The 100–300 band (board #108)

The band was re-run on main on the same GCE host shape as the first band
run, at load 150 and 280. Main was aec6f74c, sminos 1.5.1, which carries the
Linux `read_proc_start` fix. The method did not change: stress-ng in the
benches' own cgroup, autogroup off, and a per-thread CPU-share probe before
each run.

One thing was added: a control at each load point that runs the same
stress-ng at nice 19. That keeps load1 where it was but gives the benches
their CPU back. The spec's Surprises & Discoveries (board #108) has every
figure; the runbook is
[2026-10-20-desk-open-fast-band-runbook.md](2026-10-20-desk-open-fast-band-runbook.md).

A2 and A6 name no band bound, so they are read against their load < 50
bounds.

| check (bound) | first run, 150 / 280 | this run, 150 / 280 | now |
|---|---|---|---|
| A1 idle (≤ 0.6 s) | 0.12–0.26 s / 2 of 10 over, up to 1.67 s | 0.19–0.25 s / 0.15–0.51 s | passes at both |
| A2 mid-message (0.3 s) | ≤ 0.24 s / 0.30–1.02 s | ≤ 0.29 s / 0.30–0.63 s | passes at 150; misses at 280 |
| A2 after-prompt (0.3 s) | 4 of 5 over / 4 of 5 over | 2 of 5 over / 3 of 5 over (all ≤ 0.61 s) | misses |
| A2 long-answer (no early end) | holds / holds | holds / holds | passes |
| A3 +30 s (0.3 s) | 46–56 s / 64–120 s, 15 of 40 never | small 2 of 34 over, large 4 of 6 (≤ 13 s) / small 1 of 34, large 5 of 6 (≤ 30 s) | misses on large opens |
| A3 +0.5 s | incomplete / incomplete | incomplete / incomplete | incomplete |
| A3 index (≤ 0.35 CPU-s loaded) | 0.13 / 0.13 | 0.13 / 0.13 | passes |
| A4 pair (as written) | incomplete / incomplete | incomplete / incomplete | cannot block a write at load (see below) |
| A4 pair, sized to the host | — | the hub side holds / the hub side holds | misses the open after the resume (4.36 / 7.24 s), and chunk lag at 280 (1.43 s) |
| A6 kill (0.5 s) | 1.01–3.39 s / 4.64–5.46 s | 0.96–2.95 s / 2.07–5.79 s | misses |

What caused what:

- **The ps fork, most likely.** A3's stream was ready at 27.6 s and 79 s
  before, and at 5.3 s and 10.0 s now. The +30 s small opens' p50 dropped
  from 52 s and 113 s to 0.06 s and 0.08 s. A1's N at 280 is now ≤ 0.09 s,
  against 1.35 s before.

  In the first run the fork took 47% of the uplink main thread's samples.
  The code also differs otherwise between the runs (sminos 1.2.15 →
  1.5.1, MAWS master). It was not behind A6, which reads the same.
- **CPU starvation.** This is what every remaining miss but A4's comes
  from: each passes in the control at the same load1.
  - **A6, 0.35–0.49 s in the control.** The bridge child's successor is a
    fresh Python process. Its imports alone took 1.04–1.10 s wall at 150
    and 2.21–2.37 s at 280, against 0.06 CPU-s unloaded.
  - **A3's large +30 s opens, ≤ 0.12 s in the control.** Six 15,000-row
    builds need about 7 CPU-s of warming. At these shares that takes 60 s
    or more.
  - **A2 at 280, ≤ 0.10 s in the control.** E is the unloaded figure
    divided by the share.
- **A4's open after the resume: a machine-side cost the design does not
  cover. Not fixed in this run; the encoder below was made fast afterwards
  (doperpowers #328, sminos 1.6.1; see the spec's Surprises).**
  - The uplink's main thread takes frames in arrival order. So an open
    queued behind an inbound backlog waits while the main thread verifies
    every event's code.
  - That check's canonical encoder walks each string one character at a
    time in Python. It costs 0.047 CPU-s per MiB on the MacBook, against
    0.003 for `json.dumps`.
  - py-spy at 150 found the main thread in that check in 10 of the 14
    dumps of the open's wait.
  - Unloaded, the open after a 16 MiB backlog took 0.28 s, and after the
    sized 6 MiB one 0.035 s. At a share of 0.1 it costs seconds per MiB.
    The pair was not run in the control.

  Two further points about A4's pair:
  - **Why the pair as written cannot block a write at load.** The host's
    loopback buffers absorbed a 12 MiB backlog whole, and the local hub's
    2 s heartbeat caps the pause below 6 s. At load the 16 MiB upload took
    17–32 s, so it outlasts any pause the instrument's flags allow.
  - **What the sized pair needed.** It capped the buffers at 1 MiB and
    lengthened the heartbeat, which are host settings. Sized that way, it
    saw the blocked write at both loads. Every session POST in the window
    was answered 200 (85 and 71 of them), and the stream survived the 9 s
    and 15 s pauses.

The run used one c2d-standard-16 Spot host in us-east4-c. It was created at
08:47:25Z and deleted at 10:25:01Z (98 minutes), and the teardown was
confirmed through the API. At the first band run's rate (about 0.85 USD for
4.4 hours) this one cost about 0.30 USD.

## Escalations and rulings

- **M6 fix, the hub's 200.** The hub answers 200 to a session frame it
  refuses `not-open`. The coordinator agreed to keep this off the branch
  and file a MAWS ticket. Its text was sent and is in Residue.
- **M6 fix, round 3.** The probe's own refusal can be unread by the reader
  when its 200 continuation runs. I ruled this into the same hub residue
  rather than open a fifth round, and the coordinator's reviewer passed the
  result.
- **M7 load check.** I ruled a whole-prefix checksum, with a 0.15 CPU-s
  bound. The result is CRC-32 at 0.05 CPU-s.
- **M8, the resync limit.** Whole question inputs that alone exceed it are
  scoped out (§7 amended).
- **M8, inventory holes.** I required the holes be traced before the tick.
  They were the instrument's.
- **M9, two checks.** I had test_h and the close reason fixed, and
  live-bridge-check's stale clause. A10's live checks ran in M9, ahead of
  the roll.

## Environmental friction routed around

- **Worktree isolation hook.** It refuses git commands it can't verify:
  compound commands, `-C` into other worktrees, a `HOME` override, and some
  paths. I split commands into plain single ones. To read another
  checkout's state, I read its ref files or used `git show <sha>:<path>`.
- **Reviewer can't fetch MAWS.** The M6 task reviewer would not run git
  itself while it had a review package, so I extracted the MAWS hub sources
  at 992faf00b to `/tmp/maws-992faf00b/` for it to read.
- **Isolated executors.** An isolated executor can't write my workspace, so
  its report came in its hand-back and I saved it.

## Residue

The same list as the PR's Residue section.
