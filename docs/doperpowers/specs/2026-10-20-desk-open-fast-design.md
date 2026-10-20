# The desk: a session opens fast and dependably on a loaded Mac (2026-10-20)

Branch `desk-open-fast` off `main` at `219b150a`. sminos plugin at 1.1.2.
Design approved by the owner's brief of 2026-10-20 (the fix list of the
bridge bench, scoped to what stays inside today's machine↔hub wire
protocol); revised the same day after two independent reviews (Decision
Log). Written by execspec steps 1–2; the independent review and the
execution are the owner's.

## Purpose

The desk is the web control center for sminos projects (MAWS `apps/desk-web`
and `apps/desk-hub`); the machine side is the sminos plugin in this repo
(`sminos/`). Today a session view takes seconds to open and sometimes never
opens: this morning a resumed session's first page took 5.4 s, and on the
MacBook under load two opens of live sessions were abandoned by the browser
after 19 s and 51 s. The owner's one remaining worry about the desk's
architecture is this speed.

After this change a session view opens in about a second whenever the
machine can run at all: while a message is streaming, right after the
sminos daemon restarted, when the browser leaves and comes back, and for the
second open of the same session as for the first. The way to see it: open
any live session in the desk and the page is there under a second; the
plane's `open` line in `~/.claude/sminos/daemon.log` says where the machine's
share went, phase by phase; `sminos/tests/bench_open.py` reproduces the same
opens end to end — an isolated session, the real uplink, the real hub code
on a local runtime, a browser client — and prints the figures.

Most of the work is the machine side — the plane, the uplink, the bridge
child and the bridge mod. Two pieces are MAWS's, each its own milestone: the
hub stops coupling a session's frames to the log's reply chain (§8), and the
web keeps a streaming block the fresh snapshot carries across a reconnect
(§9). Nothing on the wire between machine and hub changes; no Durable
Object storage changes. One hub-side bug this investigation found — the
stream the hub ends every fifteen minutes — is being diagnosed by another
agent; §8 is designed from the code and is checked against that diagnosis
before it is built (Decision Log).

## Progress

- [x] M1 — The open line stamped at arrival; the reference consumer and the inventory; the fixtures (2026-10-20, reviewed clean after three fix rounds; 9bd55c49..c762b8d7, sminos 1.2.2)
- [ ] M2 — The instruments: `bench_open.py` (micro and full path), `bench_scale.py opens`
- [x] M3 — The web keeps a carried block across a reconnect (MAWS) (2026-10-20, reviewed clean; MAWS `desk-open-fast-web` bda992c29, PR #86)
- [x] M4 — The hub's reply chain decoupled (MAWS) (2026-10-20, reviewed clean; MAWS `desk-open-fast-hub` fba324cc4..beb065470, master merged at ef190e5e2)
- [ ] M5 — The snapshot goes at once; a notice's row is due at its step's end
- [ ] M6 — The uplink's sender lanes, with connection reuse proven
- [ ] M7 — The build saved and warmed, bounded; the look off the open path
- [ ] M8 — The child respawns at once; a resync fits the engine's limit
- [ ] M9 — Acceptance, documents, the branch review

## Terms

- **The desk**: the web (`apps/desk-web`) and the hub (`apps/desk-hub`, a
  Cloudflare Worker with Durable Objects: a `Machine` object per enrolled
  machine holding its stream, a `Project` object per project) in MAWS. The
  web subscribes to a session through the hub; the hub forwards the
  subscription to the machine and relays what comes back.
- **The local hub**: the same Worker code on a local runtime —
  `pnpm --filter desk-hub local` (`apps/desk-hub/local/run.ts`, wrangler dev
  behind a stand-in for Access) as the desk's e2e gate and
  `test_session_plane.py`'s `LocalHub` use it, and the hub's own vitest
  suites' Miniflare (`apps/desk-hub/test/support/local.ts`) with the suites'
  Worker seam (`test/support/worker-under-test.ts`: `/__test/…` paths that
  hold a `Machine`'s next send, list a `Project`'s queues, and more). No
  test and no agent calls the deployed hub with credentials.
- **The uplink**: `sminos daemon uplink` (`sminos/skills/sminos/scripts/sminos_uplink.py`),
  the process holding the machine's connection to the hub: a Server-Sent
  Events **stream** down (`GET /machine/stream`) and **POSTs** up
  (`POST /machine/frames`, NDJSON frames under the stream's generation).
  Its **main thread** does every sminos call and, today, every POST; a
  **reader** thread reads the stream; an **acker** thread answers heartbeats.
- **The reply chain**: in the hub's `Project`, one ordered queue of writes
  per machine stream (`toMachineAll`, `this.queues`), through which every
  frame the project sends down that stream goes — the `have`, backlog,
  `resend` and `refused` a `hello` or an upload owes, and the `subscribe`,
  `rows`, `rpc` and the rest the browsers' side sends. `fromMachine` awaits
  its tail after every frame of a POST.
- **The plane**: `sminos_plane.py`, the session plane on the machine: the
  sessions' presence and the hub's **subscriptions**, each a `Subscription`
  joining a transcript on disk with the bridge's live stream. The **pump**
  is `Subscription.pump`, run from the main thread's **tick** on every wake
  or every 0.25 s (`POLL`), which produces the DX4 messages now due.
- **An open**: from the browser's `subscribe` to the `snapshot` drawn. **E**
  is the end-to-end time a client measures; **N** is the machine's share
  (the subscribe frame's arrival at the uplink's reader to the snapshot's
  emission), a diagnostic phase the open line reports; **M** is when the
  bridge's snapshot line was taken off the reader's queue.
- **The bridge**: the mod in the session (`sminos/hooks/mods/bridge*.tsx`)
  and its **child** (`sminos bridge`, `sminos_bridge.py`), a per-session
  Python process serving the session's endpoint `$SMINOS_HOME/bridge/<id>.sock`
  (DX5, `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`). The
  mod **posts** events to the child; the child keeps the live state and
  serves subscribers a **snapshot** line then events.
- **A notice**: the mod's event naming a transcript row as the engine
  appends it — `block-row` for a response row (it also settles the block
  whose text streamed), `row-seen` for any other. **The cut**: per loop, the
  last notice applied, carried in the child's snapshot; rows at or before it
  are **history**, rows past it are **live**. **A step**: one model request
  of a turn, `(turnId, agentId, step)`; its blocks stream, its rows are
  named, and its end (`step` phase `end`, or the turn's completion cutting
  it off) is when the engine has the whole message and flushes its rows.
- **The build**: what an open reads on the transcript's **worker** thread
  (`Transcript`, one per file, jobs one at a time): the **index** (each
  row's uuid, byte offset and length), the loop's jobs **ledger**
  (`sminos_jobs.Ledger`), and the **chain** (`Chain`: which rows the engine
  still holds after an Esc or a /rewind). Built by parsing every row of the
  file; today lost with the process.
- **The look**: `look()`, the disk facts a subscription's `subagents` body
  reads (each subagent's meta file, its transcript's size and stamps, a
  parent loop's reduced ledger), cached in `Disk` per process.
- **A sender lane**: new here (§3): a thread with its own persistent
  connection to the hub, posting what the main thread queues for it, in
  order.
- **The saved build**, **the warmer**: new here (§4): the build written to
  disk and read back, and the plane extending live sessions' builds in the
  background.
- **The reference consumer** and **the inventory**: new here (M1): a
  Python module applying DX4 as the web's streaming layer does, and an
  independent list of what should have been drawn, so a test can say a
  block or a row went missing.
- **The GIL**: Python's global interpreter lock; one thread of the uplink
  runs Python at a time, in slices, so a worker's parse and the main thread's
  pump share the process's one core of Python.
- **The bench**: the measurement of 2026-10-20 06:00–06:45Z on the MacBook,
  `research/desk-remote/bridge-perf-bench.md` and its scripts in
  `research/desk-remote/bridge-bench/` at MAWS commit `4914cf4d` (the same
  files at `/Users/new/claude-code-bundle/2.1.300/notes/bridge-bench/`).
  **[M]** marks a figure it measured, **[I]** one it inferred.

## 1. What was measured, and what the code says

The bench settled where the time goes. The bridge hop (engine → mod → child
→ subscriber) is 1.8 / 5.7 ms p50 / p95 at load 14–17 and 4–14 / 19–62 ms at
load 110–456 **[M]**; a hub POST on a fresh TLS connection is 140–230 ms
**[M]**. The open path is what is slow, in four mechanisms, read against
the sminos code at `219b150a` and the hub's at MAWS `dc3f9d87e`
(origin/master):

1. **The snapshot waits for a row that is not on disk.** The child's `cut`
   names the last row noticed; the plane's `build` answers `"waiting"` until
   that row is in the index (`sminos_plane.build`, `Subscription.open`), up
   to `NOTICE_WAIT` (5 s), then ends the subscription with a discontinuity.
   The engine announces a response row at its block's end but flushes a
   message's rows only when the message ends: 2.0–2.4 s later **[M]**. Opens
   mid-message waited 1.96–2.22 s **[M]**; one made right after a prompt
   waited 0.40–0.51 s for a row that was on disk ~100 ms after its notice
   **[M]**, because
2. **a "waiting" answer wakes nothing**: `Subscription.ask` wakes the uplink
   for any answer but "waiting", so the build is asked again only on the
   next pump — a reader line, another wake, or the 0.25 s poll.
3. **A cold build parses the whole transcript**, 0.75 CPU-s for CI-opt's
   317 MB and 15,180 rows, plus 0.53 CPU-s for its look (136 metas) **[M]**,
   tens of seconds when the machine is starved **[I]**; the daemon restarted
   38 times since 10-17 (its code changed), each losing every build **[M]**,
   and `Transcripts` keeps only `INDEX_KEEP` (4) after their subscriptions
   go.
4. **The main thread blocks on every POST**, each on a fresh TLS
   connection, pumping nothing meanwhile (`Link.post` → `post` →
   `exchange`), for up to `2 × POST_TIMEOUT` (60 s) when the hub holds one.
   The two abandoned opens sat in the last minutes of a stream the hub ended
   with a 503 **[I]**.

And the same mechanism's other half, in the hub: **a POST is held behind
the project's reply chain, and so is a subscribe.** `Project.fromMachine`
awaits `this.queues.get(queueKey(machine, generation))` — the tail of the
project's one send chain to that machine's stream — after *every* frame,
session frames included ("settled at once for a frame that owes no reply"
is true only while nothing is queued). The chain is per machine stream, not
per connection: a `hello` whose `have` or backlog page is still being
written holds every POST of that machine to that project, whichever
connection carries it. `Project.carry` queues the browser's `subscribe` on
the same chain, so an open waits behind the backlog before it reaches the
uplink at all. And `Machine.write` has no bound: a stream whose client
stops reading blocks every write to it until the stream ends
(`test/machine-end.test.ts` pins that ending it releases them). So two
sender lanes on the machine (§3) isolate nothing on their own; §8 removes
the coupling at the hub, and the lanes remove it at the machine. The bench's
reading that the hub "holds the answer until its replies are written to the
browser's stream" is wrong in detail — the replies are the machine's own,
and a subscription's message to a browser is written unawaited — but its
conclusion stands.

**The long holds have one cause, and it is periodic.** Every stream of the
owner's uplink ends with the same 503 `delivery-failed` 15:01–16:14 after
it connected (seven streams on 2026-10-20, 03:42Z–06:52Z, daemon.log),
which is `ARCHIVE_EVERY` (900 s) after the welcome: the POST that fails is
the archive-period re-`hello` batch (`Link.tick`, `next_confirm`), held by
the hub for up to a minute (the 503 came 1–74 s after the re-`hello` was
due; the uplink's own bounds are a 30 s socket timeout and 60 s in all),
then answered 503 with `frames` (what the hub applied before the frame that
failed: 7 on most streams). Every subscription dies with the stream
(`Link.on_welcome` → `Plane.close`; the hub ends the browsers' subscriptions
`machine-offline`), and the browser subscribes again. Another agent is
diagnosing it on the hub's side; §8 is the same queue and hello path, and
its milestone is checked against the diagnosis before it is built.

The bench's fix list, in its impact order, and what this spec does with each:

| # | the bench's fix | here |
|---|---|---|
| 1 | a sender thread; one persistent connection; the hub not holding a POST | §3 the lanes, §8 the hub's chain decoupled: both are needed |
| 2 | no gate on the cut's row | §2; and the 5 s notice expiry re-based on the step's end, which the gate had hidden |
| — | a "waiting" open re-checked by the event, not the poll | subsumed by §2: no build answers "waiting" any more; every other wake is already event-driven |
| 3 | tail-first snapshot; index that survives a restart; builds cancelled | §4: the build saved and warmed under a bound; the look off the open path. The tail-first snapshot and the cancellation are dropped, §4 says why |
| 4 | the open line stamped at the reader's arrival | §5 |
| 5 | one connection from the mod to the child; or the child's role into the daemon | out of scope (the next phase, MAWS #52) |
| 6 | serialize once per event in the child | dropped, §10 says why |
| 7 | the first respawn without delay | §6 |
| 8 | resyncs under the engine's 4 MB | §7 |
| — | the web keeps a block the fresh snapshot carries | §9, found in review: without it §2's snapshot loses a block on a reconnect |

## Acceptance

Success is an arrival, measured end to end through the real uplink and the
real hub code: **E** runs from a browser client's `subscribe` to its
receipt of the `snapshot`, and the reference consumer then says the drawing
is whole. **N**, the machine's share from the open line (§5), is reported
beside E as a diagnostic, never as the result. Each check names its
instrument and its figure.

**Load.** Load is the 1-minute load average (`uptime`) during a run; a
figure holds at the load band it names. The owner's Macs are never loaded
artificially: a target-band figure (100–300) comes from the MacBook's own
frequent high-load windows (the bench ran at 14–475), or from an isolated
host loaded synthetically (a devcloud host under `stress-ng`, never a Mac
the owner works on). A check with no result in its target band is recorded
as **incomplete at that band**, never as a pass at another load.

**The instruments.**

- **`sminos/tests/bench_open.py`** (M2), two modes with one output shape (one
  JSON line per open, a summary per scenario: min / p50 / max).
  - *The full path* (`--uplink --hub local|standin`): the branch's
    `sminos daemon uplink` under a temporary HOME and SMINOS_HOME, enrolled
    at a local hub the instrument starts (`--maws <MAWS worktree>`:
    `pnpm --filter desk-hub local --state <tmp> --port <n>`, the enrollment
    as `test_session_plane.py`'s `LocalHub.enroll` does it) or at the HTTP/1.1
    hub stand-in (M1); a browser client (`sminos/tests/ws_client.py` on the
    local hub's project socket; the stand-in's `/control/send` and its
    stamped `sessions` list) that subscribes and stamps the snapshot's
    receipt: **E**. With `--live` the session is an isolated headless one
    the way `sminos/tests/mods/live-bridge-check.py` isolates one (temporary
    config dir, a staged copy of the plugin, the gateway keys through a 0600
    env file; it spends haiku calls and is run by hand); otherwise the
    session is `fake_session.py`'s scripted one, or a synthetic transcript
    (`--synthetic-rows N`, shaped as the build measurement in Surprises &
    Discoveries shaped one) with no bridge. The reference consumer applies
    what the client received and the inventory says what is missing.
  - *The micro-benchmark* (`--micro --session <id> --sminos-home <dir>`):
    one `Subscription` driven in-process as `Plane.subscribe` builds it,
    pumped as the uplink pumps, the phases of §5 stamped — the bench's
    `plane_open.py`, ported. It leaves out the reader queue, the record
    scan, the ticks, the refreshes, the warmer and the uplink's thread, and
    says so in its output (`"mode": "micro"`); its figure is **N_micro**,
    not N and not E, for diagnosing one open's phases.
- **`sminos/tests/bench_scale.py opens`** (M2): the synthetic machine
  `bench_scale.py` already builds (DIRS × PER_DIR transcripts, LIVE running
  sessions under engine records, the hub stand-in), with `--large N`
  transcripts of 15,000 rows among the live sessions; starts the uplink
  fresh and sends subscribes through the stand-in at stated moments
  (before warming completes, after it, after a second restart), for a large
  session and a small one, printing each E.
- **`sminos/tests/bench_index.py <transcript>`** (M7): the build of one
  transcript path, read-only, three ways — cold, loaded from a saved build
  it writes under a temporary SMINOS_HOME, warm — CPU and wall each, rows
  and bytes.
- **The open line** in `daemon.log` (§5) and the sender's connection lines
  (§3), on the owner's Mac after the roll.
- **The hub stand-in** `sminos/tests/hub_standin.py` (M1): HTTP/1.1 with
  keep-alive, each request recorded with its connection's id, each session
  message with its arrival stamp; `POST /control/post-fault` with fault
  `hold` holds the next matching POST until `/control/release`.
- **The pause proxy** `sminos/tests/pause_proxy.py` (M1): a TCP proxy the
  uplink is pointed at as its hub, with a control to stop forwarding the
  stream connection's bytes to the uplink and to resume them; the other
  connections pass. With the stream paused and a backlog larger than the
  socket buffers queued for it, the hub's writes to that stream block: the
  reply chain is blocked for real, through the real hub code.
- **The hub's vitest suites** (`apps/desk-hub/test/`, the seam's
  `SEND_HOLD_PATH` on `have`) and **the web's** (`apps/desk-web/src/depth/stream/layer.test.ts`),
  for the MAWS milestones; MAWS gates `scripts/ci-gate.sh <worktree> --gates static,unit`
  (the hub) and `--gates static,unit,e2e:desk-web` (the web).
- **`tests/mods/bridge.test.ts`**'s harness (a fake engine with a clock, children
  and posts the test reads), for the mod.
- **Owner-visible, after rollout**: `window.deskLatency()` in the owner's
  browser against the deployed hub — `view.snapshot` (subscribe to snapshot)
  and `resume.gap` — the whole path with the WAN and the drawing. Named here
  so the figures below have their counterpart; not a check an agent runs.

**The checks.** E on the local hub at load < 50 unless said otherwise; the
same opens at load 100–300 are the second figure of each line.

- **A1 — a warm idle open.** `bench_open.py --uplink --hub local --live
  --scenario idle --opens 10` (between turns, the build warm): E ≤ 0.3 s;
  at load 100–300, E ≤ 0.6 s. N ≤ 0.10 s / ≤ 0.5 s reported beside it (today
  N 0.00–0.03 s at load 18–38 **[M]**; E unmeasured).
- **A2 — an open mid-message, and right after a prompt.** `--scenario
  mid-message --opens 5` (a session with thinking on, the prompt asking for
  a 400-word story after reasoning; each open made on the text block's
  first chunk, after the thinking block's `block-row` and before the message
  ends — the window the bench's P1 hit, 2.3–2.4 s wide **[M]**): E ≤ 0.3 s
  (today N alone 1.96–2.22 s **[M]**); the open line's `waits` is 0; the
  snapshot's `streaming` carries the thinking block's text with its `uuid`;
  the row goes out as `row` once the message ends; the consumer and the
  inventory report 0 holes, 0 duplicates, 0 gaps across the whole message.
  `--scenario long-answer --opens 3`: a message whose thinking block's row
  stays unflushed 12 s or more (a 900-word story after reasoning), opened at
  +1 s and reconnected at +7 s: no `end` before the message's, the block
  drawn throughout, its row once. `--scenario after-prompt --opens 5`: E ≤
  0.3 s (today N alone 0.40–0.51 s **[M]**).
- **A3 — after a daemon restart, and a live session's first open.**
  `bench_scale.py opens --live 40 --large 6` (forty live sessions, six of
  15,000 rows): with the uplink started fresh, an open of a small session at
  +0.5 s has E ≤ 0.5 s while the large ones' builds run; an open of a large
  session at +0.5 s has E ≤ 1.5 s (a saved build loads) and, with no saved
  build, E equals its cold build plus 0.3 s, reported; opens after warming
  (+30 s) have E ≤ 0.3 s for every session; a second restart repeats the
  loaded figures. `bench_index.py <transcript ≥ 100 MB>`: loaded ≤ 0.35
  CPU-s where cold ≥ 0.7 CPU-s (CI-opt's 317 MB is the owner's reference
  transcript; the check reads it, prints none of it). On the owner's Mac:
  the first open line of any session live for 2 × `WARM_EVERY` or longer
  reads `build: warm`.
- **A4 — opens while the reply chain is blocked.** Three proofs, each where
  the coupling lives:
  - the hub (M4, vitest): with the seam holding the `Machine`'s next `have`
    send, a session POST on a second connection is answered 200 within
    200 ms, a browser `subscribe` carried on the control chain reaches the
    machine client while the hold stands, and a `hello` POST is answered
    503 `write-stalled` within `WRITE_TIMEOUT_MS` + 1 s;
  - the uplink (M6, `test_session_plane.py`'s `Uplink`): with the stand-in
    holding the re-`hello` POST (`SMINOS_ARCHIVE_EVERY=1`, fault `hold` on
    `hello`), a `subscribe` sent during the hold has its snapshot at the
    stand-in within 1 s, and three more opens over the next 20 s each within
    1 s; `release` ends the stream as today and the next stream serves them
    again;
  - the pair (M9, `bench_open.py --uplink --hub local --scenario held
    --pause-stream 4 --backlog 4m`), in M2's order with each step observed
    before the next: a subscription is open and its client has a first
    chunk of the fake session's scripted stream; a second client's upload
    of 4 MB of events is answered 200, so the hub fans them out down the
    uplink's stream on the same generation; the proxy, armed, pauses on the
    first of those frames and reports it — the window starts there — and
    the hub's remaining fan-out writes block behind the paused socket for
    4 s, one duration in every run, below the local hub's silence bound
    (three 2 s heartbeats) so the uplink keeps the stream and continuity,
    not reconnection, is what is measured: every session POST the uplink
    sends in the window is answered 200 (the local hub's request log), each
    chunk reaches the browser client within 1 s of its stamp, the hub's
    stream survives the pause (no `end` at the client, the same generation
    after), and an open made 1 s after the proxy reports `resumed` has E ≤
    1 s. The write bound is the hub proof's (a stalled write, not a held
    send).
  On the owner's Mac: open lines in the minute before each `a POST was not
  delivered (…503…)` line show `taken − arrived` ≤ 0.05 s (today M of
  16.15 s and 35.97 s **[M]**).
- **A5 — the open line and the connection lines.** Every open line carries
  the fields of §5 (pinned by M1's unit test); the sender's lines (§3) show
  dials and closes with their counts; both visible in the owner's
  daemon.log after the roll.
- **A6 — a child crash.** `--scenario kill --opens 3` (the child SIGKILLed
  mid-stream): the successor's snapshot at the browser client ≤ 0.5 s after
  the kill (today 1.18 s to the subscriber **[M]**, of which 1.0 s the
  fixed delay).
- **A7 — a 5 MB streaming block.** `bridge.test.ts`: a tool call whose
  `input` streams 5,000,000 characters, then a reload (a new child's hello):
  every post body the harness saw is under 4,194,304 characters; the
  resync's block carries `truncated: true` and the last 65,536 characters;
  no `gap` and no second resync follow. `bridge_order.py` (the real child):
  its snapshot after that resync carries the block so marked.
- **A8 — a carried block survives a reconnect (the web).** `layer.test.ts`
  and the shared fixture `dx4-stream.json` (M1, M3): an empty-history
  reconnect whose fresh snapshot carries a block the old subscription had
  named keeps the block drawn with the snapshot's text until its row lands,
  then drops it once; the reference consumer gives the same drawn state on
  the same fixture.
- **A9 — connection reuse.** `test_session_plane.py`'s `Uplink` against the
  HTTP/1.1 stand-in: five POSTs on a lane share one connection id; with
  `SMINOS_IDLE_CLOSE=1` the next POST after a 2 s pause comes on a new one;
  the sender's connection lines say the same. By hand on the owner's Mac
  (M6): over an hour of normal use the connection lines show a handful of
  dials per lane, each serving many POSTs, and idle closes, never a dial per
  POST.
- **A10 — no regression.** The gates `sminos`, `sminos-suites`,
  `sminos-mods` and `mods-types` green on the branch's head (`ci-gate`);
  MAWS's `static,unit` for the hub change and `static,unit,e2e:desk-web` for
  the web change; by hand, `sminos/tests/mods/live-bridge-check.py` and
  `live-resume-check.py` pass against the branch.

## 2. The snapshot goes at once

**What the gate protected.** A block's text leaves the child's `streaming`
when its `block-row` is applied (the child's `_apply`, the mod's `track`),
and its row is not on disk yet. A snapshot taken then holds neither the
text nor the row: the gate waited for the row so the subscriber never saw
a hole where a finished block should be. That is the continuity to keep.

**The change: the text rides along until the row lands.** DX5 amendment
(Interfaces): a block stays in its message's `blocks` after its
`block-row`, carrying `uuid` (the row it was named by) and `namedAt` (the
notice's `t`, ms), until its step ends or its turn completes — in the mod
(`track` on `block-row` keeps the block and marks it; `shownMessage` and so
`resyncEvent` carry it) and in the child (`_apply` on a notice keeps the
block and marks it; `_message` and `_shown` carry it; `settled` keeps the
indices as today, so late chunks for a named block stay ignored). The
child's snapshot `streaming` therefore carries every block of each open
request, the named ones marked.

**The plane serves the snapshot without waiting**, from what is on disk:

- `build(t, cut, bridged)` never answers `"waiting"`. The cut's row in the
  index: history ends after it, as today. Not in the index: history is
  every row on disk (`split = n`), because rows reach disk in notice order
  within a loop, so nothing past a row not yet flushed is flushed either;
  the cut's row and what follows arrive through the Tail as live rows.
  `Subscription.unlocated` likewise: a live session with no transcript file
  yet gets an empty snapshot at once, cut or no cut.
- The snapshot's `streaming`: for each carried entry, a block without
  `uuid` is passed as today. For the subscription's own loop (`mine`): a
  block with `uuid` whose row is in the history (`emitted`) is dropped from
  the entry — its row is in the page or pageable, and the guard "a
  `block-row` for a history row whose block the subscriber still holds"
  stays as a guard; a block with `uuid` whose row is not on disk is kept in
  the entry, its key added to `held`, and its uuid entered in `noticed` as a
  notice of its step (the expiry rule below). For an entry of another loop
  the subscription carries (the main subscription carries every agent's), a
  named block is kept in its entry and its `block-row` relayed after the
  snapshot, as a live one is relayed today; it enters `noticed` of no
  subscription but its own loop's.
- Right after the snapshot (n=0), one `block-row` message per kept named
  block, entry order then block index, before anything else of the
  subscription: the web marks the block settled-by that uuid (§9: it reads
  the snapshot's `uuid` too) and keeps drawing its text until the row lands.
- `release` is unchanged in what it releases: a row whose uuid is in
  `noticed` goes out at once when the Tail reads it, and releases the rows
  before it in disk order.

**When a named row is due: at its step's end, not at its notice.** Today
`release` ends the subscription when a notice's row is not on disk
`NOTICE_WAIT` (5 s) after the notice. The engine flushes a message's rows
when the message ends, so a thinking block named at its end and followed by
a long answer has its row unflushed for the answer's whole length: today
that kills a live subscription 5 s in, and under this spec's first draft it
would have killed an open the same way and dropped the carried text on the
re-subscribe (review finding P1-2). From here, **a notice's row is due
`NOTICE_WAIT` after the end of its loop's step that was open when the
notice came** — the `step` phase `end` event for that key, or the turn's
`complete` cutting it off — **and, when no step of its loop was open, after
the notice itself** (a prompt row, a tool result between requests, a
compaction's rows: the engine's 100 ms flush timer covers them). The plane
keeps `noticed[uuid] = (step key or None, at)`, sets each uuid's deadline
when its step ends (`steps.discard` and the turn's cut-off both do), and
`release` ends the subscription only past a deadline. A notice of a loop
whose step is open (a `block-row`, or a `row-seen` for an assistant row that
did not stream) therefore waits as long as the answer runs; a `row-seen`
between requests keeps today's 5 s. This is the DX5 consumer rule's one
amendment, written into the DX5 plan with the date.

**The residual hole**: a snapshot taken between a step's end (the message's
entry leaves `streaming`) and the flush of its rows (within the engine's
100 ms flush timer, since the step end waits for the rows to be named)
carries neither; the rows land within that time. Accepted.

**Why not read the row's text elsewhere.** The engine holds the unflushed
rows in memory only; the child's `/rows` route reads the disk. The text the
mod streamed is the only copy outside the engine, and the mod already keeps
it until the step ends. The alternative — the plane sending the snapshot
with a hole and the row later — loses the continuity the gate protected.

**Why not keep the gate and poll the file faster** (the bench's "until
then"): a message that streams more than 5 s after its first block's row
is announced still fails the open, and long answers after a thinking block
on a slower model do that routinely.

**`sminos watch`** draws a snapshot's named blocks as streamed text — a
finished block's text in the catch-up, where today it was missing. Fine.

## 3. The uplink's sender lanes

**Today** `Link.post` runs the whole HTTP exchange on a helper thread and
the main thread waits on it, so the pump — every subscription's chunks,
rows and snapshots — stops for each POST (140–230 ms on a fresh TLS
connection; up to a minute when the hub holds one). The reader and the
acker already run apart so the stream drains and the lease renews whatever
the main thread does. The lanes below make the machine side independent of
the network; §8 makes the hub side independent of the reply chain. Both are
needed: without §8 a held `hello` holds the session lane's POST at the hub
too (§1).

**The design.** Two **sender lanes**, each a thread (`Sender` in
`sminos_uplink.py`, Interfaces) with one persistent connection to the hub,
made at the stream's welcome (`Link.on_welcome`, where the generation every
POST names becomes known; nothing is posted before it) and closed with the
stream (`Link.close`):

- the **log lane**: `hello` with the connect's bundle (the machine's
  presence, the connect's session presence, unreported rejections, the
  pending set, RPC results owed), the `events` uploads, delivery outcomes,
  rejections of imported events, the machine's presence and re-`hello`s
  (`machine_presence`), the archive-period re-`hello`;
- the **session lane**: everything `Plane.tick` produces (presence changes,
  every subscription's messages), `relay_requests` (`raised` / `settled`)
  and `relay_rpcs` (`rpc-result`).

The main thread never waits on the network: `Link.post(frames)` becomes
`lane.send(frames, then=None)`, which converts the frames to wire lines on
the main thread (`to_wire`, parts included) and queues them; the sender
posts in FIFO order, taking everything queued as one or more bodies of at
most `POST_LIMIT` as `post` splits them today. After a body's 200 the sender
puts `("sent", [then…])` on the stream's item queue, and the main loop runs
each `then` in order as it takes the item (a `then` that raises is logged as
a frame handler's failure, not the stream's). A non-200 answer, an error, or
a POST that outlasts `2 × POST_TIMEOUT` puts `("closed", why)` on the item
queue once — the main loop logs it as today's `a POST was not delivered`
and returns, the stream ends, the next one redoes the handshake — and the
sender drops its queue and exits. Between bodies and before each the sender
checks `ended()` and stops silently (today's `Stopping`); `Sender.close()`
shuts its socket so a blocked exchange raises, and drops the queue.

**Marks and acknowledgement.** Today every mark follows its POST's 200.
With a sender, each mark is placed by whether the next stream's handshake
heals it:

- **At enqueue** (healed by the handshake if the POST is lost, or re-sent
  until acknowledged on its own): `opened.add`, `follows`, `machine_sent`,
  `hl.took(reach)` (the hub's `have` on the next hello resets it),
  `requests.sent` (the complete pending set goes after every connect),
  `rpcs.sent` (results are re-sent until `rpc-ack`).
- **In the POST's `then`** (not healed: a loss would be silent):
  `plane.accepted(pid)` (the presence tombstone mark), `hl.reported(frames)`
  (rejections reported), `box.drop(lines)` (delivery outcomes dropped from
  the outbox). Their producers hold an **in-flight flag** per project until
  the `then` ran, and `deliveries(hl)` and `unreported()` are not taken again
  while it is held, so nothing is posted twice.
- What `open(hl)` posts after the hello (`deliveries(hl)`) stays where it
  is: a lane is one connection, FIFO, so the hub applies it after the hello,
  and a hello that fails ends the stream before any `then` behind it runs.

**The session lane's gate.** A session-lane frame for a project may reach
the hub only after that project's `hello` was answered, or the hub refuses
it `not-open` and the subscription's first message is lost. The log lane's
hello carries `then = lambda: session_lane.release(pid)`; the session sender
holds a project's entries aside (in order, per project) until released and
posts the others meanwhile, so an un-acknowledged `hello` of one project
(a new project opened mid-stream) delays no other project's messages. The
release set is the sender's, reset with the stream. The acker is unchanged
and keeps its own exchange: a held log-lane POST must not delay a heartbeat's
answer.

**Head-of-line.** A re-`hello` the hub holds now stalls the log lane alone
for its duration; opens, chunks, requests and RPC results flow on the
session lane. Uploads and imports wait, which is today's behavior and not
latency-sensitive.

**The persistent connection, and proving it.** One `http.client`
connection per sender (`connection(cred, POST_TIMEOUT)`, dialled as today by
`dial`), kept across POSTs: each answer is read whole (`resp.read()`), a
`Connection: close` answer or any failure drops it, and the next POST dials
afresh. A failure raised while *sending* the request on a reused connection
(`BrokenPipeError`, `ConnectionResetError` from `request`/`send`: the hub
closed an idle connection, nothing of the body was processed) is retried
once on a fresh connection; a failure after the request was sent
(`RemoteDisconnected`, `BadStatusLine`, a timeout) is a loss as today — the
hub may have applied the POST, and the handshake is what heals it. A
connection idle for `IDLE_CLOSE` (60 s) is closed by the sender, so a stale
keep-alive the edge dropped is rarely met. **Warming**: `on_subscribe` calls
`session_lane.warm()`, which makes the sender dial now if it holds no
connection, so the TLS handshake overlaps the reader's connect and the
build rather than following the snapshot. **The connection lines**: a
sender writes one daemon.log line per dial — `uplink: <lane> lane dialled
the hub (connection #n)` — and one per close — `uplink: <lane> lane closed
connection #n after <k> POSTs (<idle|the hub closed it|failed: why>)` — and
one for any POST slower than `SLOW_POST_SECONDS` (5) with its lane and
duration. The hub stand-in speaks HTTP/1.1 from M1 (today HTTP/1.0, which
closes every connection, so reuse could not be seen there) and records each
request's connection id; the owner's daemon.log shows reuse and the idle
close on the real edge, and the executor reads an hour of it by hand in M6
and records the edge's observed idle bound in Surprises & Discoveries;
`IDLE_CLOSE` moves below it if it is shorter.

**Bounds.** A lane whose queued bytes pass `SEND_QUEUE_MAX` (16 MiB: the hub
is not taking frames) ends the stream as a lost POST does.

**The state table** (per sender; the linearization point is the item queue,
read by the main loop in arrival order):

| state | `send(frames, then)` | `warm()` | body answered 200 | body not 200 / error / deadline | `close()` / `ended()` |
|---|---|---|---|---|---|
| idle (no conn) | queue; wake → posting (dials first) | dial → idle (conn) | — | — | closed |
| idle (conn) | queue; wake → posting | — | — | — | conn shut; closed |
| posting | queue (posted after the bodies in flight) | — | `("sent", thens)` on the items; more queued → posting, else idle | `("closed", why)` on the items; queue dropped → closed | conn shut; the exchange raises → closed, nothing put |
| closed | dropped | — | — | — | — |

**Alternatives.** *The session plane on its own thread* (the log lane's
POSTs left blocking on the main thread): fewer post sites to touch, but the
plane's membership and presence state is read by the RPC checks and the
request relay on the main thread, `refresh` makes sminos calls that must
stay there, and `tick` would split in two with a lock between — more shared
state for less. *One lane*: simpler, and it reintroduces the minute's stall
behind the re-`hello` hold. *Posting in parallel*: breaks a subscription's
`n` order. *Marks all in `then`*: the hub writes `have` down the stream
before answering the hello's POST, so `on_have` would find the project not
yet opened and drop it; and a second upload pass before the acknowledgement
would post the same suffix twice.

**How this carries to a machine↔hub WebSocket** (MAWS #52, the next phase):
a sender's contract is an ordered queue of frames per lane, an
acknowledgement per batch on which the continuations run, and a failure that
ends the stream. On a socket the lane's connection is the socket, a batch is
one message, the acknowledgement is the hub's per-batch ack frame (the
`frames` count of today's 200), and the continuations and the release gate
fire on it. The two lanes collapse into one socket once the hub answers a
batch without waiting for the replies it owes (§8 is the first step of
that): `have` and the backlog are just frames down. `Sender.send(frames,
then)`, the marks' two classes, and the gate stay; only the transport under
the sender changes.

## 4. The build saved, warmed, and off the open path

**The saved build.** A transcript's build is written to disk and read back,
so a daemon restart or an eviction costs a load, not a parse:

- Where: `$SMINOS_HOME/daemon/plane/<sha256(realpath)[:24]>.build`, mode
  0600, written to a temporary name and `os.replace`d.
- What: `BUILD_FORMAT` (an integer the executor bumps whenever `Index`,
  `Ledger` or `Chain` change what they hold), the transcript's realpath and
  inode, `index.end`, and the Transcript's index, ledger and chain as of
  `end`. Serialization is the executor's: `pickle` protocol 5 is the
  measured default (Surprises & Discoveries: 2.2 MB and 0.28 CPU-s to load
  for 15,000 rows, against 0.82 CPU-s to build); `marshal` of plain
  containers is the alternative to try if the load is slower than
  0.3 CPU-s for 15,000 rows. The file is the daemon's own under a 0700
  directory: loading it is trusted.
- When saved, on the worker: after an `extended()` that is the first build
  of the transcript in this process or that grew the index by at least
  `SAVE_GROWTH` (16 MiB of transcript bytes) since the last save; when a
  Transcript leaves memory (`Transcripts.release`'s eviction); and at the
  uplink's stop (`cmd_uplink`, after `serve` returns for the last time), for
  every held Transcript, bounded by `STOP_SAVE_SECONDS` (5).
- When loaded: `Transcripts.acquire` for a path not held makes a Transcript
  whose first job loads the saved build before anything extends it. A load
  that fails for any reason — format, path or inode mismatch, the file
  shorter than `end`, any exception — removes the file and starts cold;
  `Reset` semantics after a load are today's (a replaced or shrunk file
  starts over).
- Sweep: at the uplink's start, saved builds whose mtime is older than
  `BUILD_KEEP_DAYS` (14) are removed.

**The warmer, bounded.** Live sessions' builds are kept current in the
background, so a live session's first open is warm — without starving the
opens (review finding P1-3: an unbounded warm pass after a restart is
dozens of cold builds at once, every open queued behind its own transcript's
warm job, and the `Disk` cache churned):

- **Two queues per worker.** `Transcript.submit(job)` is the foreground
  queue — an open's build, a page, a look for a subscription, an `output` —
  and `Transcript.submit_background(job)` the background one; `work` takes
  a foreground job whenever one is queued, a background job only when none
  is. A running job is never interrupted: an open on a transcript whose
  warm build is running waits for it, which is the open's own build.
- **Coalesced.** At most one warm job is queued or running per transcript
  (`Transcript.warming`); the warmer skips a transcript that has one.
- **Bounded across the process.** At most `WARM_PARALLEL` (2) warm jobs run
  at once in the process (a counter under a lock, released in the job's
  `finally`); the warmer submits none while the count is full, and visits
  the live sessions round-robin from a rotating list, so after a restart
  every live session gets its turn, two at a time, the large ones taking
  theirs without blocking the small ones' opens. The GIL's share between a
  cold build and a warm open was measured small (0.01–0.03 s **[M]**); two
  builds beside the pump is the budget.
- **What a warm job does.** `extended()`, then the save rule. **It does not
  look**: the look is off the open path (below) and is asked by the
  subscription when one exists; warming looks for every live session would
  churn `DISK_KEEP` (4,096) for sessions nobody opens.
- **Who is warmed.** In `Plane.tick`, every `WARM_EVERY` (2 s): each session
  that is live (`self.live`) and a member of an open project
  (`self.members`), whose main transcript is located
  (`sminos.transcript_now`, asked on the main thread as `Subscription.path`
  asks it, cached per session for its life). The plane holds its Transcript
  (`acquire` once; `release` when the session is no longer live or no longer
  a member). Agent transcripts are not warmed: they are opened less and are
  smaller; a cold one builds on its worker as today, saved after.
- `INDEX_KEEP` rises from 4 to 32: a build is 8.9 MB in memory for 15,000
  rows (Surprises & Discoveries), and the machine's live sessions are tens,
  few of them large. Eviction stays least-recently-used among transcripts
  with no subscription and no live session, saving first. A transcript the
  warmer holds is never evicted while its session is live; if the uplink's
  memory ever matters (forty live sessions of 15,000 rows would be 360 MB),
  the hold can be capped by bytes with the least recently grown saved and
  released first — not done now, and the figure to watch is the uplink's
  resident size in `sminos daemon status`.

**The look off the open path.** `opening(t)` runs the build alone; the
snapshot goes with the subscription's `facts` as they stand (`Facts()` on a
first open) and `next_look = now`, so the look is asked on the pump right
after the snapshot (a foreground job) and the first `subagents` message
follows it (the plane already sends one whenever the derived body changes).
A cold look is 0.53 CPU-s for CI-opt's 136 metas **[M]**, which with the
build off the path would have been the open's largest remaining cost after
a restart. The desk's tree therefore refines within the look's time rather
than delaying the page; `test_a_cold_open_and_a_live_one_reach_the_same_statuses`
reads "reach" as after that first `subagents`.

**Dropped, and why.** *The tail-first snapshot* (the bench's "read backward
from EOF for the newest rows"): the snapshot's `offChain` and its
`subagents` body need the chain and the ledger, which are fed every row in
file order (`Chain.add`'s branch and rejoin rules, a null parent continuing
the chain, rows written ahead of their parent); a suffix fed to `Chain`
places nothing, and a backward walk of the leaf's ancestry is a second
implementation of the engine's loader semantics that `ChainRules` pins in
one. With the saved build and the warmer, a cold parse happens once per
transcript (the first open of a session that ended before the warmer held
it), on its own worker, delaying no other open. *Cancelling builds when the
subscriber leaves*: the build's product is kept and saved; cancelling it
discards work the next open needs, and a retry no longer queues behind it
but finds it done.

## 5. The open line stamped at arrival

`Subscription.noted` writes one line per open. Its fields, from here on:

```
plane: open <sub> of <sid8>[/<agent>]: <outcome> after <N> s from the subscribe's arrival
  (bridge: snapshot arrived <A> s, taken <M> s; build: <loaded|warm|cold> <cpu> ms <rows> rows, cut <on disk|not on disk|null>; waits <k>)
```

- `N`: from the subscribe frame's arrival at the uplink's reader
  (`Link.received`, the reader's epoch stamp, passed into `Plane.subscribe`
  and kept as the subscription's `opened`) to the snapshot's emission, or to
  the end before one.
- `A`: the bridge's snapshot line's arrival at `BridgeReader` (each item the
  reader puts carries a stamp); `M`: when `open` took it. `taken − arrived`
  is the main thread's absence — a held POST today, nothing after §3.
- `build`: how the index came — loaded from a saved build, warm in memory,
  or cold — with the build's CPU time on the worker and the rows indexed;
  whether the cut's row was on disk when the snapshot went; `waits`, how
  many builds answered "waiting" (0 after §2; kept so the line reads the
  same on any version).
- Without a bridge the bridge clause reads `(no bridge)`; the outcomes and
  the "closed before its snapshot" line keep today's wording.

Every future open line then says which of §1's mechanisms, if any, it hit.
The line is written once per open as today, pinned by
`test_each_open_is_said_once_with_the_wait_that_ended_it`, extended to the
fields.

## 6. The child respawns at once

`startChild` waits `RESPAWN_FIRST_MS` (1,000) before the first respawn of a
child that ended on its own, doubling to a minute while it keeps ending at
once; nearly all of a crash's 1.18 s recovery **[M]** is that delay. From
here: the first respawn after a stable run (`STABLE_MS`) is immediate
(`RESPAWN_FIRST_MS` 0), the next waits `RESPAWN_STEP_MS` (1,000), then
doubling as today to `RESPAWN_MAX_MS`. A child that dies at once in a loop
thus costs one extra immediate try. `bridge.test.ts`'s respawn test pins
`[0]` then `[0, 1000, 2000]` where it pins `[1000]` and `[1000, 2000]`.

## 7. A resync fits the engine's limit

`$.http.fetch` refuses a body over 4,194,304 characters (the bench, from the
2.1.300 bundle **[I]**); a resync larger than that is refused, counted lost,
and queued again every `RETRY_MS` for ever — a huge tool input streaming is
enough. Two bounds, and a rule:

- **A block's catch-up text is bounded.** In the mod's `trackChunk` and the
  child's `_fold` alike, a block's kept text is its last `BLOCK_TAIL`
  (65,536) characters once it passes that, marked `truncated: true`. Chunk
  events still carry every chunk whole: a subscriber that streamed from the
  start holds the whole text; only the catch-up copy a snapshot or a resync
  gives is the tail. The flag reaches DX4's `StreamingBlock` as an extra key
  the web passes over.
- **A resync is posted alone.** The poster ends a batch before a resync and
  after it, so a body holding one holds nothing else. `resyncEvent` measures
  its JSON and, over `RESYNC_MAX` (4,000,000 characters — the bounded blocks
  make this a pathological case of thousands of open requests), drops
  streaming entries oldest first and marks the resync `truncated: true`; the
  child takes what it carries.
- Pending requests' inputs are already cut at 65,536 characters with
  `truncated: true` (DX5); unchanged.

## 8. The hub: the reply chain decoupled

The wire stays as it is (DX2's `POST /machine/frames` with its 200 / 409 /
413 / 503 answers, the SSE stream down); what changes is what a POST's
answer waits for and what shares a queue, in `apps/desk-hub/src/objects/project.ts`
and `objects/machine.ts`. No Durable Object storage changes: `queues` is an
in-memory map, and nothing stored gains a table, column or key.

1. **A POST waits for its own replies, never the chain's tail.**
   `fromMachineFrame` returns the `sent` promises of the writes the frame
   itself queued — a `hello`'s `have` (not its backlog pages: they stream
   behind, and a page that cannot be written ends the stream through
   `Machine.write`'s own failure path as before), an upload's `resend` and
   `refused` — and `fromMachine` awaits those; a `session`, `pending`,
   `rpc-result` or `rejected` frame awaits nothing. **Every owed reply must
   resolve `'written'`.** A timed-out or failed write returns false from
   `Machine.write`, which `Machine.send` and `toMachineAll` hand back as a
   fulfilled `'offline'` (after `leaveFanOut`), never as a throw — and
   `fromMachine` today counts only a throw as failure, so a timed-out
   `hello` would count as applied, the opening bundle's frames after it
   would be refused `not-open` yet counted, and the 200 would run the
   uplink's `then` marks (§3: the presence tombstone, rejections reported,
   outcomes dropped) and suppress their retry (review finding D1). So: an
   owed reply that resolves `'offline'` stops the batch as `failed` without
   counting that frame, exactly as a throw does; the frames after it are
   not applied. The POST's answer then means "applied, and the replies it
   owes are on the stream", and `failed` (503 `delivery-failed`) means one
   of those replies was not written — by a throw, a timeout, or a stream
   gone. A session POST is held for one object round trip whatever the log
   lane is doing.
2. **Two chains per machine stream.** `toMachineAll` takes a lane:
   `replies` for what the log plane writes down a machine's stream — what
   its own frames owe it (`have`, backlog pages, `resend`, `refused` to a
   machine frame) and the live `events` fan-out of other machines' uploads
   (`fanOut`) — and `control` for what the browsers' side sends (`carry`'s
   `subscribe`, `unsubscribe`, `rows`, `diff`, `output`, forwarded `rpc` and
   `rpc-ack`, a `refused` of a session-plane frame), keyed
   `${name}#${generation}#${lane}`; both end at `Machine.send` → `write`,
   whose writer serializes them. A browser's subscribe no longer waits behind
   a backlog being paged to the machine; a stuck stream still stops both (3).
3. **A write is bounded.** `Machine.write` races `writer.write` against
   `WRITE_TIMEOUT_MS` (10,000): past it the stream ends `write-stalled` (a
   new `EndCause`, logged as the others) and the write answers false, so a
   chain blocked by a client that stopped reading fails within the bound
   and the POSTs on it answer 503 `delivery-failed` then rather than at the
   machine's 60 s; the machine reconnects as it does after any 503. A frame
   of 1 MiB taking 10 s is 100 KB/s — a dead link, not a slow one.

**Against the diagnosis.** The periodic 503 (§1) is the same hello path
and queue; its diagnosis is pending from another agent. Before M4 starts,
its executor reads the diagnosis the owner forwards and records in the
Decision Log whether 1–3 cover the cause; a cause they do not cover is
added to M4 as a fourth change, and the rest of this section stands.

**The test seams** the suites' Worker already has reach this: `SEND_HOLD_PATH`
(a `Machine` armed to hold its next send of one frame kind until released)
is the blocked reply chain; `PROJECT_QUEUES_PATH` lists a project's queue
keys, which now show both lanes; `PROJECT_BACKLOG_PATH` the pages read.

**Alternatives.** *Answer every POST on receipt*: changes DX2's meaning of a
200 (the uplink's `NotDelivered` semantics rely on it) — the WebSocket
phase's change, not this one. *One chain, session frames exempt from the
await*: leaves the subscribe behind the backlog. *No write bound*: a stuck
stream holds everything for a minute, which is what the owner saw.

## 9. The web: a carried block kept across a reconnect

`apps/desk-web/src/depth/stream/layer.ts` draws a snapshot's `streaming`
blocks (`load`) and reconciles a fresh snapshot after a disruption with what
it drew (`resume`). Today `resume` deletes the fresh snapshot's copy of
every block the old subscription had named (`request.blocks.delete(index)`
for `old.named`) and keeps the old drawn block only if its row will land
(`lands(uuid)`) or a `landing` row exists; on an empty-history reconnect
neither holds and the block vanishes — and `blockRow` cannot bring it back,
since it only marks a block that is drawn (review finding P2-4). With §2 the
fresh snapshot carries exactly such blocks, so the web must keep them.

**The rule.** A block the fresh snapshot carries is drawn from the snapshot,
named or not:

- `snapshotEntry` reads a block's `uuid` (a string, else null); `load` sets
  `settledBy: uuid` and adds a named block's index to `request.named`, so a
  block named before the subscription takes no later chunk and settles when
  its row lands, whether or not a `block-row` reaches it (the plane sends
  one anyway, idempotent).
- `resume`: for each old request and index, if the fresh snapshot carries
  the block, the fresh copy is kept — its text the snapshot's, except for a
  block the old subscription had named, which keeps the text already drawn
  (a `block-row` follows a block's last chunk, so that text is whole, and it
  stays whole when §7 cuts the carried copy to its tail; Decision Log, M3), `settledBy`
  the fresh `uuid` if named else the old `settledBy` (a block the old
  subscription had named and the snapshot still carries unnamed is named by
  the `block-row` that follows), the block's identity (its live label's
  clock) the old one's as today; only a block the fresh snapshot does not
  carry goes through today's `lands` / `landing` reasoning. The watermark
  rule (a snapshot older than what was drawn changes nothing) and the ended
  request rule stay.
- `settle(uuid)` drops it once its row lands, as today.

The parity fixture `dx4-stream.json` (M1; a copy under
`apps/desk-web/src/depth/stream/`, as `dx4-jobs.json` is shared with the
hub's fake machine) scripts the sequences — a first snapshot with named and
unnamed blocks of thinking, text and tool kinds; chunks; `block-row`;
`step-end`; `row` landing; a fresh snapshot after a disruption with empty
history carrying the named block; one carrying it no longer; one older than
what was drawn — and the drawn blocks expected after each message, so
`layer.test.ts` and the reference consumer prove the same rule. The DX4 type
comment in `apps/desk-hub/src/protocol/session.ts` (`Streaming.blocks`:
"only blocks without a block-row yet") is amended with the three keys and
the new rule; the hub relays the body uninterpreted and needs no code.

## 10. Dropped and out of scope

- **Serialize once per event in the child** (`_fan_out` dumping JSON per
  subscriber, one write per line): production has one subscriber, the
  daemon; `sminos watch` a second now and then. The gain appears at 5+
  subscribers past 3,000 events/s **[M]**, which nothing produces; the
  child's share of the hop is 0.3–1 ms **[M]**. Dropped; logged in the
  backlog with this reasoning.
- **One connection from the mod to the child, or the child's role in the
  daemon**: the next phase's design (MAWS #52), out of scope.
- **The machine↔hub WebSocket**: out of scope; §3 says how the sender
  carries over, and §8 is its first step on the hub.
- **The periodic 503's cause**: another agent's diagnosis; §8's milestone
  is checked against it.
- **A browser's `subscribe` while the stream is stuck**: no chain can carry
  it; §8's write bound ends the stream fast and the browser subscribes on the
  next one. Accepted.

## Execution

### Constraints that bind every milestone

- The Python the sminos scripts already require, standard library only (no
  new dependency); TypeScript under the engine's function-hook runtime as
  the mods are built today; the hub and the web as MAWS builds them (pnpm,
  vitest, Playwright for e2e).
- Nothing on the wire between machine and hub changes (DX2, DX4). DX5 (the
  machine-local bridge protocol) changes only as Interfaces says, and the
  DX5 plan document gets a dated amendment line per change
  (`docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`, the DX5
  table and the consumer rule, as earlier waves amended them). No Durable
  Object storage change: a milestone that finds it needs one stops and says
  so (the owner decides).
- The sminos milestones are on this branch; the MAWS milestones on a MAWS
  branch `desk-open-fast` in a worktree of `/Users/new/Developer/GitHub/MAWS`
  off `origin/master`, each its own commit set, gated with
  `scripts/ci-gate.sh <worktree> --gates …` as each milestone names; the
  owner deploys the hub and the web. **Rollout order and the open
  clients**: M4 (the hub) is deployed before M6 rolls; M3 (the web) is
  deployed before M5 rolls to any machine, **and before M5 rolls the owner
  refreshes or relaunches every open desk client — browser tabs and
  installed PWA windows — onto M3's build**: the desk's service worker
  claims its clients but does not reload their code
  (`apps/desk-web/src/pwa/service-worker.ts`,
  `apps/desk-web/src/sw/service-worker.ts`), so an open client keeps the
  streaming layer it loaded, and against M5's snapshots that layer drops a
  carried block on a reconnect (§9). M5's hand-off to the owner says this
  in plain words, as a step to do, and names the clients it means. Rolling
  the web back while M5 is live brings that block loss back; rolling M5
  back while M3 is live loses nothing (M3 draws today's snapshots as
  today). The hub change and the lanes are independent of client code.
- Every milestone that changes a file under `sminos/` ends with
  `scripts/bump-version.sh --plugin sminos <next patch>` in its own commit,
  in the same commit as the change or the one right after it on the branch.
- Running a working copy's sminos, daemon, child or mods goes under a
  temporary HOME and SMINOS_HOME, as every test here does. Never the real
  `~/.claude/sminos`, `~/.claude/settings.json` or `~/.claude.json`; never
  `~/.config/claude-secrets`; never `~/.claude/sminos/daemon/hub.json`; the
  deployed hub is never called with credentials by an agent or a test —
  "real hub" means the local hub (Terms). The by-hand reads of the owner's
  daemon.log are reads.
- Reading the owner's transcripts and `daemon.log` is read-only, for sizes,
  stamps and the open lines; nothing of their content is printed into a
  report or a test.
- The owner's Macs are never loaded artificially (Acceptance, Load).
- Tests live beside the suites they extend: `sminos/tests/test_session_plane.py`
  (the plane; its `Uplink` class for the uplink against the stand-in or the
  local hub), `sminos/tests/test-uplink.sh`, `sminos/tests/bridge_order.py`
  (the real child's order rules), `sminos/tests/mods/bridge.test.ts` (the
  mod), `apps/desk-hub/test/` and `apps/desk-web/src/depth/stream/layer.test.ts`
  (MAWS). Live checks spend model calls and are run by hand.
- Commit by explicit paths; never rewrite history; commit messages end with
  the session's `Sminos-Session` line; no attribution trailers.
- The module docstrings of `sminos_plane.py`, `sminos_uplink.py` and
  `sminos_bridge.py` are the contract's home in the code: each milestone
  updates the paragraph its change touches.

### Plan of Work

M1 and M2 land the instruments every later proof reads. M3 and M4 are the
MAWS milestones and may run beside M5–M8 (different repositories), but M6's
pair proof (A4) and M9 need M4 deployed to the local hub the instrument
starts, which is just the MAWS worktree at M4's commit. M5–M8 run in order
on this branch. M9 executes the acceptance.

### M1 — The open line stamped at arrival; the reference consumer and the inventory; the fixtures

What exists after: every open line reads as §5; a reference DX4 consumer
with thinking, text and tool blocks, the web's reconciliation rule (§9) and
a sequence reset per subscription, with an inventory that names every block
and row that should have been drawn; the hub stand-in on HTTP/1.1 recording
connection ids and arrival stamps; the pause proxy.

Touches: `sminos/skills/sminos/scripts/sminos_plane.py` (`BridgeReader.put`
stamps, `Subscription.opened` from the frame's receipt, `noted`'s fields,
`Built.how` and `cpu_ms`), `sminos_uplink.py` (`Plane.subscribe(project,
frame_, received)` passing `Link.received`), new `sminos/tests/dx4_consumer.py`
and `sminos/tests/dx4-stream.json`, `sminos/tests/test_session_plane.py`
(its `Browser` replaced by the consumer; a test of the consumer against the
fixture), `sminos/tests/hub_standin.py` (HTTP/1.1, `conn` on each `posted`
record, `at` on each session message), new `sminos/tests/pause_proxy.py`.

Decisions: `Built` gains `how` (`warm` or `cold` in M1, `loaded` with M7)
and `cpu_ms` (`time.thread_time` around `extended()`). The consumer
(`dx4_consumer.Consumer`): one instance per subscription (`n` starts over;
a re-subscribe is a new instance handed the old one's drawn state for
`resume`), applies `snapshot` (`load` or `resume` as §9), `chunk`,
`block-row`, `step-end`, `row` (`settle`), `rows`, `subagents`, `end`,
keeps every drawn block's text by kind and every row, and records errors:
an `n` gap, a duplicate row, a chunk at or below the watermark, a block
whose drawn text differs from its row's, a block that vanished before its
row landed, a message after `end`. The inventory (`dx4_consumer.Inventory`)
is built from the sources of truth — the transcript file's rows (every row
on disk, whether delivered or not) and the DX5 events the fake session or a
probe subscription emitted (every block that streamed, its final text) —
and `Inventory.check(consumer)` names each row never drawn (a hole), each
block drawn with partial text after its row landed, and each block drawn
twice. The fixture `dx4-stream.json` is the sequences §9 names with the
expected drawn state after each message; the consumer's test replays it,
and M3 copies it to the web. The stand-in: `protocol_version = "HTTP/1.1"`
(every answer carries `Content-Length` already; the stream and the `hold`
faults set `close_connection`), a connection sequence number assigned in
`setup()` and written as `conn` on each `posted` record, `at` (epoch s) on
each session message, `/control/state` exposing both. The pause proxy:
`pause_proxy.py <hub-url> <port-file>` listens on 127.0.0.1, forwards every
connection to the hub, recognizes the one whose first line is
`GET /machine/stream`, and takes its controls on its own port (Interfaces): armed to pause now or on the
next `"t":"events"` frame it forwards on that connection, for a stated
number of seconds, it stops reading from the hub side of that connection
and reports `paused` with the bytes held back, so the hub's writes back up
once the socket buffers fill; it reports `resumed` when it reads again.

Does not touch: any behavior of the open; the figures the line reports
change in later milestones, the line's shape does not.

Proves: A5's fields (the unit test pins the line); the consumer finds, on
the fixture, every planted hole, duplicate and vanished block the fixture
marks as expected errors; the stand-in's `conn` is the same across requests
on one keep-alive connection (a test with `http.client` reusing one).

### M2 — The instruments: `bench_open.py` (micro and full path), `bench_scale.py opens`

What exists after: `bench_open.py --uplink --hub local|standin [--live |
--synthetic-rows N] --scenario … --opens N [--pause-stream S --backlog B]`
measures E through the real uplink and real hub code and runs the consumer
and the inventory on what the client received; `--micro` measures N_micro;
`bench_scale.py opens` measures E at scale across a restart.

Touches: new `sminos/tests/bench_open.py`, `sminos/tests/bench_scale.py`
(the `opens` mode, `--large`), `sminos/tests/ws_client.py` only if a stamp
it lacks is needed.

Decisions: the local hub is started from `--maws <worktree>` with its own
`--state` directory under the instrument's temporary root and a free port;
the uplink is enrolled as `LocalHub.enroll` does, the project created as
`Uplink.setUpClass` does; the `--live` session is `live-bridge-check.py`'s
`Live` imported, not copied, and **extended in this milestone**: today
`Live.start_session()` takes no options and runs one interactive tmux
command fixed at haiku (`sminos/tests/mods/live-bridge-check.py`). It
gains `start_session(headless=False, thinking=False, model="haiku")`
under the same isolation contract as `setup()` — the temporary HOME whose
`.claude` is the config dir, the temporary SMINOS_HOME, the staged copy of
the plugin loaded with `--plugin-dir`, the gateway keys and
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` through the 0600 env file, nothing
else of the caller's environment, every process it starts ended by
`cleanup()`. `headless=True` runs `claude -p --input-format stream-json
--output-format stream-json --include-partial-messages` as a subprocess
with piped stdin and stdout under that env (the bench's `live_headless.py`
shape), prompts written as stream-json user messages, no tmux;
`thinking=True` sets the engine's thinking budget in the env file
(`MAX_THINKING_TOKENS`, the engine's override for extended thinking) and
`model` the `--model`; the existing live checks keep their call unchanged.
`bench_open.py --live` uses headless; `--thinking` passes `thinking=True`,
and the first scenario run proves the knob: the probe must see a
`thinking` block's `block-row` followed by a text chunk of the same step
in a trial message before any open counts, else the run stops and says the
model or the budget gave no thinking (then `--model sonnet`, which the
gateway keys also map). Scenarios: `idle`, `after-prompt`, `mid-message`
(a probe subscription watches the stream and, per message, records the
thinking block's `block-row` time and the step's end; the open is made on
the first text chunk after that `block-row`; **an open counts only when
the probe shows it fell inside that window** — after the thinking
`block-row`, before the step's end — and the run reports each window's
length, the opens that counted and the opens that missed, needing
`--opens N` counted ones; the open's line also records `cut not on disk`),
`long-answer` (the same window proof; open at +1 s, reconnect at +7 s,
assert no `end` before the step's), `kill` (SIGKILL the child by the pid
its `/status` answers; measure from the kill to the successor's snapshot
at the client), `restart` (with `--synthetic-rows`: a cold open, then the
uplink restarted and the same open), `held` (`--pause-stream S --backlog
B`, the pause proxy between the uplink and the hub, **in this order, each
step observed before the next**: (1) the uplink connects through the proxy
and hellos; a subscription is opened and the client has received its
snapshot and a first chunk of the fake session's scripted stream — the
chain is live on this generation; (2) the instrument arms the proxy with
`pause-on-next-events` and the proxy acknowledges; a second client uploads
B bytes of events to the project and its POST is answered 200 — the hub
fans them out down the uplink's stream on the same generation as `events`
frames; (3) the proxy pauses when it has forwarded the first of those
frames and reports `paused` with the byte count, which starts the window;
the remaining fan-out writes block behind the paused socket; (4) through
the window of S seconds — **one duration, 4 s, below the local hub's 6 s
silence bound (three 2 s heartbeats), in every run and every command** —
the pre-pause subscription's chunks are stamped at the client and every
POST of the uplink is read from the hub's request log; (5) the proxy
resumes at S and reports `resumed`; one open at +1 s after it. B is raised
if the executor finds the proxy's and wrangler's buffers absorb 4 MB
without blocking; the proxy's `paused` report carries how many bytes it
held back, so a run whose hub never blocked shows as such). Each open prints `{"mode", "scenario", "load1", "E",
"N", "arrived", "taken", "build", "cpu_ms", "rows", "cut", "waits",
"holes", "dups", "gaps", "vanished"}`; the summary gives min / p50 / max of
E and N per scenario and the load's range. `bench_scale.py opens`: the
synthetic machine with `--live L --large G`, the uplink started fresh,
subscribes sent through the stand-in's `/control/send` at +0.5 s (one small,
one large), at +30 s (every live session, in sequence), then the uplink
restarted and the +0.5 s pair again; E from the stand-in's `at` stamps; the
saved-build directory kept across the restart (same SMINOS_HOME).

Does not touch: any behavior; `bench_scale.py`'s other modes.

Proves: on the branch's head before M5, the full path reproduces the bench
within its spread — an `idle` open's N 0.00–0.05 s, a `mid-message` open's
N ≥ 1 s, E a hub hop larger — and `bench_scale.py opens` records the
restart baseline (a large session's first open cold); both recorded in
Surprises & Discoveries as the baseline.

### M3 — The web keeps a carried block across a reconnect (MAWS)

What exists after: the web draws a block the fresh snapshot carries, named
or not, through a reconnect; the DX4 type comment says so.

Touches (MAWS): `apps/desk-web/src/depth/stream/layer.ts` (`snapshotEntry`,
`load`, `resume`), `apps/desk-web/src/depth/stream/layer.test.ts`, new
`apps/desk-web/src/depth/stream/dx4-stream.json` (M1's fixture, copied),
`apps/desk-hub/src/protocol/session.ts` (the `Streaming.blocks` and
`StreamingBlock` comments and the three optional keys), `apps/desk-web/src/depth/source/desk-transcript.ts`
only if `resume`'s signature changes.

Decisions: §9 whole. The fixture test replays `dx4-stream.json` through
`StreamingLayer` and compares `blocks(agentId)` after each message to the
expected drawn state; the existing `resume` tests stay and still pass (the
rule only adds the carried-block case).

Does not touch: the hub's code; the web's rows store; the transcript's
reducer.

Proves: A8 (the web half); gates `scripts/ci-gate.sh <worktree> --gates static,unit,e2e:desk-web`.

### M4 — The hub's reply chain decoupled (MAWS)

What exists after: a session POST is answered without waiting for the
project's reply chain; a browser's subscribe is carried on a chain of its
own; a stuck stream ends within `WRITE_TIMEOUT_MS`.

Touches (MAWS): `apps/desk-hub/src/objects/project.ts` (`fromMachine`,
`fromMachineFrame`, `hello`, `upload`, `toMachine`/`toMachineAll` with a
lane, `carry`, `unsubscribe`, `rows`, `diff`, `output`, the RPC forwards),
`apps/desk-hub/src/objects/machine.ts` (`write`'s bound, the `EndCause`),
`apps/desk-hub/test/support/worker-under-test.ts` (the seams' queue listing
shows both lanes), new `apps/desk-hub/test/reply-chain.test.ts`, the DX2
comments in `objects/machine.ts` and `project.ts` that describe the wait.

Decisions: §8 whole. First task: read the periodic-503 diagnosis the owner
forwards and write the Decision Log line §8 asks for. The test, two parts: (a) a
`MachineClient` (`test/support/clients.ts`) opens a stream and hellos with
a `have` behind the project's log so a backlog is owed; the seam holds the
`Machine`'s next `have` send; a second `MachineClient` connection posts a
`session` frame for the project and is answered 200 within 200 ms; a
`BrowserClient` subscribes and the `subscribe` frame reaches the first
client's stream while the hold stands (the control chain); the seam
released, the hello's POST is answered 200, and the backlog pages arrive in
order. (b) As `machine-end.test.ts` builds a `Machine` on Node's streams
with a client that stopped reading: a write past `WRITE_TIMEOUT_MS` ends
the stream `write-stalled`, the chain's pending sends answer offline, and a
`hello` POST held on it is answered 503 within `WRITE_TIMEOUT_MS` + 1 s.
(c) The timed-out hello inside an opening bundle (D1): one POST carrying
`hello`, then the machine presence, the sessions' presence, a `rejected`
and a `pending` frame, on a stream whose client stopped reading; the
answer is 503 `delivery-failed` with `frames` 0 (nothing before the hello
was applied, the hello is not counted, nothing after it is applied); the
project's `machines` row for that generation is gone (`leaveFanOut`) and
no `refused` was queued for the trailing frames; and, in
`test_session_plane.py`'s `Uplink` (M6), the uplink that received that 503
kept its marks (M6's proof names them).

Does not touch: the wire; storage; the Registry; the web.

Proves: A4 (the hub proof); the existing suites (`latency.test.ts`,
`reconnect.test.ts`, `machine-end.test.ts`, `stream-close.test.ts`,
`session-plane.test.ts`) pass; gates `scripts/ci-gate.sh <worktree> --gates static,unit`.

### M5 — The snapshot goes at once; a notice's row is due at its step's end

What exists after: an open mid-message, right after a prompt, or with a
transcript not yet on disk gets its snapshot on the first pump after the
bridge's; the named block's text is in the snapshot and its row follows
when flushed; a subscription survives a long answer; no build answers
"waiting".

Touches: `sminos/hooks/mods/bridge-stream.tsx` (`track` on `block-row`,
`shownMessage`, `resyncEvent`), `sminos/hooks/mods/bridge-state.tsx` (the
block type), `sminos_bridge.py` (`_apply` on notices, `_message`, `_shown`),
`sminos_plane.py` (`build`, `Subscription.open`, `unlocated`, `snapshot`,
the kept blocks' `block-row` messages, `notice`, `event` on `step`/`turn`,
`release`'s deadlines), tests in `bridge.test.ts`, `bridge_order.py` and
`test_session_plane.py`, the DX5 plan's amendment lines (the block shape;
the consumer rule), the docstrings' continuity paragraph.

Decisions: §2 whole. The `namedAt` stamp is the notice event's `t` (every
emitted event is stamped in `emit`). In the child, `_message` keeps a block
whose index is in `settled` when the block carries `uuid` (today it drops
every settled block), and `_fold` still ignores chunks for settled indices;
in the mod, `track` on `block-row` keeps the block in `blocks` and marks it,
`settled` unchanged. **The child's resync merge** (`_apply` on `resync`:
"a block this child saw settled stays settled, whatever the copy says")
today adds the old message's `settled` to the new one and pops every block
at those indices — which would drop a carried named block on a resync to
the same child (a lost post's recovery, a `lose`), leaving the next
snapshot with neither block nor row (review finding D2). From here the
merge keeps a block that carries `uuid` (the mod's copy is at least as new
as the child's: `track` names a block before `emit` queues its notice),
still adds the old `settled` so late chunks stay ignored, and still pops a
block at a settled index that carries no `uuid` (a stale unnamed copy).
`bridge_order.py` gains the scenario: a block streams and is named, the mod
resyncs the same child, a new subscription opens before the step ends —
its snapshot carries the block with its `uuid` and its text, and the row
settles it once when it lands. The deadline bookkeeping: `noticed` maps a uuid to
`(step_key, at)`, `due` maps a uuid to its deadline once set; `event` on a
`step` end or a `turn` complete sets `due` for every noticed uuid of that
step; `release` ends on `now > due[u]`; a carried named block's uuid enters
`noticed` with its entry's step key and no deadline. The tests rewritten to
the new rules: `test_cut_row_not_yet_on_disk_while_chunks_arrive` (the
snapshot goes at once with the block, chunks past the watermark follow, the
row lands named), `test_cut_row_that_never_reaches_disk` (the block stays
drawn through the step; `NOTICE_WAIT` after the step's end the subscription
ends naming the row; a subscription made after that gets the snapshot
without the block and waits for nothing), `test_notice_whose_row_never_flushes`
(a `row-seen` between requests keeps the 5 s from the notice; one during an
open step waits for the step), `test_each_open_is_said_once…` (`waits 0`),
`test_a_null_cut_row_flushed_beside_its_streaming_block` and
`test_a_module_reload_with_the_seeded_cut` as the rules now read; new, with
the consumer and the inventory: "a long answer after a thinking block: opens
at +1 s and +7 s and a live subscription from the start all draw the block
throughout a 12 s message and its row once" (A2's `long-answer`, on the
fake session with the clock), "a history row's named block is dropped from
the snapshot's streaming", "the kept blocks' block-rows are the messages
after the snapshot, in order", "an open with no transcript file yet and a
cut gets an empty snapshot", "a main subscription carries an agent loop's
named block and relays its block-row". In `bridge_order.py`, the `Consumer`
(DX5's reference reader) takes the same rules.

Does not touch: the uplink; the build's persistence.

Hand-off: this milestone's report to the owner states, as a step to do
before the plugin rolls, that the M3 web must be deployed and every open
desk client — each browser tab and each installed PWA window — refreshed
or relaunched onto it, and that rolling the web back while this is live
brings back the block loss on reconnect (the constraints' rollout order).

Proves: A2 (by the unit tests for the mechanism; by `bench_open.py --uplink
--hub local --live --scenario mid-message`, `long-answer` and
`after-prompt` for the figures, recorded in Surprises & Discoveries).

### M6 — The uplink's sender lanes, with connection reuse proven

What exists after: the main thread never blocks on a POST; a held POST on
the log lane delays no open at the machine; POSTs reuse connections, and
the log shows it; the stream still ends on any POST not answered 200.

Touches: `sminos_uplink.py` (`Sender`; `Link.post`, `post_session`, `open`,
`upload`, `deliveries`, `on_events`, `machine_presence`, `relay_requests`,
`relay_rpcs`, `tick`, `close`; `serve_link`'s handling of `("sent", …)` and
`("closed", …)` items; `on_subscribe`'s warm; the connection lines),
`sminos_hublog.py` and `sminos_outcomes.py` only if an in-flight flag is
best kept there, `sminos/tests/test_session_plane.py` (`Uplink`),
`sminos/tests/test-uplink.sh`, the uplink's docstring.

Decisions: §3 whole; the state table is the implementation's shape. `post()`
and `exchange()` stay as the acker's path; the sender's exchange reuses
`exchange`'s deadline and shutdown-on-end logic over a kept connection
rather than a per-POST one. The in-flight flags live on `Link` keyed by
project unless the producer's own object is the natural home.
`SMINOS_IDLE_CLOSE` overrides `IDLE_CLOSE` for a test. The by-hand read of
the owner's daemon.log (A9) is this milestone's last step, with the owner,
on a machine running the branch's plugin; its finding goes to Surprises &
Discoveries.

Does not touch: the plane's internals beyond `subscribe`'s warm call; the
acker; the hub stand-in's DX2 behavior.

Proves: A4 (the uplink proof); A9 (the stand-in half); the existing
`Uplink` and `test-uplink.sh` cases pass unchanged in meaning (a reconnect
mid-response, a dropped stream, a 503, a stalled POST, uploads and
`have`); new: "marks in a POST's continuation run after its 200 and never
when it fails", "a project's session messages wait for its hello's
acknowledgement and other projects' do not", "a lane past
`SEND_QUEUE_MAX` ends the stream", "a stale keep-alive on send is retried
once on a fresh connection; a failure after the send is a loss", "the
connection lines name each dial and close with its count", "a hello POST
answered 503 leaves the presence tombstone mark, the unreported rejections
and the delivery outbox exactly as they were, and the next stream's hello
says the leavers, reports the rejections and posts the outcomes again"
(the uplink's side of D1).

### M7 — The build saved and warmed, bounded; the look off the open path

What exists after: a daemon restart costs an open a load, not a parse; a
live session's first open is warm; the warmer never queues ahead of an open
and runs at most two builds at once; the snapshot does not wait for the look.

Touches: `sminos_plane.py` (`Transcript.load`/`save`, `submit_background`
and the two-queue `work`, `Transcripts` eviction and `INDEX_KEEP`, the
warmer in `Plane.tick` with its bound and round-robin, `opening` without
the look, `noted`'s `loaded`), `sminos_uplink.py` (the save at stop, the
sweep at start), `sminos/tests/test_session_plane.py` (`TranscriptIndex`,
`Session`, a `Warmer` class), new `sminos/tests/bench_index.py`, the plane's
docstring.

Decisions: §4 whole. Format and constants as Interfaces. Saving runs on
the worker; the uplink's stop save is a background job submitted to each
worker and joined with the bound.

Does not touch: agent transcripts' warming; the Disk cache's persistence
(the look is off the open path and is not warmed).

Proves: A3 (by `bench_index.py` on a large transcript and `bench_scale.py
opens --live 40 --large 6`, before and after this milestone, both figures
recorded); unit tests: "a saved build loads and extends from its end", "a
saved build of another format, inode, or a shorter file is removed and the
build starts cold", "a live member's transcript is held and extended before
any subscription", "an open's build runs ahead of a queued warm job and a
warm job never queues twice", "at most two warm jobs run at once across
forty live transcripts, visited round-robin", "eviction saves first and a
later open loads", "the snapshot goes before the look and the first
`subagents` follows", "the stop saves every held build".

### M8 — The child respawns at once; a resync fits the engine's limit

What exists after: a crashed child's successor serves within ~0.3 s; a 5 MB
streaming block never stalls the bridge.

Touches: `sminos/hooks/mods/bridge.tsx` (`startChild`), `bridge-state.tsx`
(`RESPAWN_FIRST_MS`, `RESPAWN_STEP_MS`), `bridge-stream.tsx` (`trackChunk`'s
tail bound, `resyncEvent`'s measure, the poster's batch boundary around a
resync), `sminos_bridge.py` (`_fold`'s tail bound, `_message` keeping
`truncated`), `tests/mods/bridge.test.ts`, `sminos/tests/bridge_order.py`,
the DX5 amendment lines.

Decisions: §6 and §7 whole.

Does not touch: chunk events (whole, as today); the child's subscriber
fan-out (§10).

Proves: A6 (by `bench_open.py --scenario kill`; the unit test pins the
timers), A7 (by the unit tests named there).

### M9 — Acceptance, documents, the branch review

What exists after: the acceptance section executed as written, each check's
figure recorded with its load band or marked incomplete at the band it
missed; the documents current; the branch ready for its review.

Touches: `docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md`
(Progress, Surprises & Discoveries, the figures), `CLAUDE.md` (the sminos
row of the repo map: the plane's saved builds and bounded warmer, the
uplink's sender lanes and connection lines, in a clause each),
`sminos/skills/sminos/references/setup.md` only if a knob the owner sets is
named (none is planned), the three docstrings read once more as a whole.

Decisions: the target-band runs (100–300) are taken from the MacBook's own
high-load windows (`uptime` read before each run; the band's runs made when
it is there) or on an isolated devcloud host under synthetic load; a check
with no result in its band is written as incomplete at that band. The
by-hand live checks (A10) run last. The owner's `window.deskLatency()`
figures are written in when the owner supplies them. The version bump of
this milestone is the branch's last.

Proves: A1–A10 as written.

### Concrete Steps

Working directory: the branch's worktree root (sminos); the MAWS worktree
for M3 and M4. The suites, per area:

```
bash sminos/tests/run-sminos-tests.sh                     # all; SMINOS_PART=core|suites for one part
python3 sminos/tests/test_session_plane.py                # the plane and the uplink against the stand-in
DESK_HUB=http://127.0.0.1:8747 python3 sminos/tests/test_session_plane.py Uplink   # the same against the local hub
python3 sminos/tests/test_session_plane.py Session.test_cut_row_not_yet_on_disk_while_chunks_arrive
bash sminos/tests/test-uplink.sh
bash sminos/tests/mods/run.sh                             # the mods (claude plugin test), then the shell checks
ci-gate --gates sminos,sminos-suites,sminos-mods,mods-types   # the committed HEAD, on Actions
pnpm --filter desk-hub local --state /tmp/desk-local --port 8747     # MAWS worktree: the local hub
pnpm --filter desk-hub test                               # MAWS worktree: the hub's vitest suites
scripts/ci-gate.sh <MAWS worktree> --gates static,unit    # M4
scripts/ci-gate.sh <MAWS worktree> --gates static,unit,e2e:desk-web   # M3
```

A passing suite prints `ok` lines and a summary with 0 failures; `ci-gate`
prints one line per gate then `GREEN <run-url>`.

The instruments, by hand (the `--live` runs spend haiku calls; the gateway
keys in the environment as `live-bridge-check.py` takes them; `uptime`
before each run, and the band it falls in written with the result):

```
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --live --scenario idle --opens 10
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --live --thinking --scenario mid-message --opens 5
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --live --thinking --scenario long-answer --opens 3
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --live --scenario after-prompt --opens 5
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --live --scenario kill --opens 3
python3 sminos/tests/bench_open.py --uplink --hub standin --scenario restart --synthetic-rows 15000
python3 sminos/tests/bench_open.py --uplink --hub local --maws <MAWS worktree> --scenario held --pause-stream 4 --backlog 4m   # 4 s: under the local hub's 6 s silence bound, continuity not reconnection
python3 sminos/tests/bench_open.py --micro --session <id> --sminos-home <dir>     # one open's phases, in-process
python3 sminos/tests/bench_scale.py opens <scripts-dir> --live 40 --large 6
python3 sminos/tests/bench_index.py <transcript.jsonl>
```

Each `bench_open.py` open prints one JSON line, e.g.
`{"mode": "uplink", "scenario": "mid-message", "load1": 42.1, "E": 0.21, "N": 0.07, "arrived": 0.02, "taken": 0.02, "build": "warm", "cpu_ms": 3, "rows": 1512, "cut": "not on disk", "waits": 0, "holes": 0, "dups": 0, "gaps": 0, "vanished": 0}`,
then a summary per scenario; `bench_scale.py opens` prints one line per
open with its moment (`+0.5 s`, `+30 s`, `restart +0.5 s`), size and E;
`bench_index.py` prints three lines, `cold cpu 0.78 s wall 1.02 s`,
`loaded cpu 0.27 s …`, `warm cpu 0.00 s …`, with the rows and bytes.

M6's read of the owner's daemon.log, by hand with the owner, on a machine
running the branch's plugin: the connection lines over an hour of normal
use — dials per lane, POSTs per connection, idle closes — and any
`a POST was not delivered` line. Nothing is typed into a test from this.

Version bumps: `scripts/bump-version.sh --plugin sminos 1.1.3` (M1), then
each next patch per sminos milestone; `scripts/bump-version.sh --check
--plugin sminos` confirms no drift.

### Interfaces and Dependencies

**DX5 (machine-local; the mod ↔ the child ↔ the plane), amended:**

- A streaming entry's `blocks[]` element gains `uuid?: string` and
  `namedAt?: number` (the notice's `t`, ms) once its `block-row` was applied,
  and `truncated?: true` once its kept text was cut to its last `BLOCK_TAIL`
  characters; a named block stays in `blocks` until its step ends or its
  turn completes. `settled` is unchanged. This holds in the mod's
  `resyncEvent` and in the child's snapshot line alike.
- A resync travels in a post of its own; `resyncEvent` may carry
  `truncated: true` when it dropped streaming entries to fit `RESYNC_MAX`.
- The consumer rule: a notice's row is due `NOTICE_WAIT` after the end of
  the loop's step open when the notice came, or after the notice when none
  was; the rest of the rule as written.

**DX4 (machine ↔ hub ↔ web): unchanged on the wire.** A snapshot's
`streaming` block may now carry `uuid`, `namedAt` and `truncated`; the
subscription's messages after such a snapshot begin with one `block-row` per
block carrying `uuid`; a consumer draws a block the snapshot carries, named
or not (§9).

**DX2 (machine ↔ hub): unchanged on the wire.** A POST's 200 means the
frames were applied and the replies *those frames* owe are on the stream;
503 `delivery-failed` means one of those could not be written, which now
includes a write past `WRITE_TIMEOUT_MS` (`write-stalled`).

**`sminos_plane.py`:**

```python
class BridgeReader(threading.Thread):
    # items: ("line", obj, at) | ("unavailable", why, at) | ("refused", status, at) | ("closed", why, at); at = time.time()

class Plane:
    def subscribe(self, project, frame_, received=None): ...   # received: the frame's arrival (epoch s), the open's start

def build(t, cut, bridged):                                     # -> ("built", Built) | ("reset", why) | ("failed", why); never "waiting"
class Built:  how: str  # "loaded" | "warm" | "cold"; cpu_ms: int

class Transcript:
    def submit(self, job): ...             # foreground: an open's build, a page, a look, an output
    def submit_background(self, job): ...  # the warmer's; runs only when no foreground job is queued
    warming: bool                          # a warm job queued or running
    def load(self): ...     # the saved build into index, ledger, chain; False and the file removed when it cannot be used
    def save(self): ...     # atomic; called under the save rule
    # the Transcript records how its index came (loaded, warm, cold) and the CPU its last extend cost; build() copies them into Built

class Subscription:
    noticed: dict   # uuid -> (step key or None, at)
    due: dict       # uuid -> the deadline, once its step ended (or at once for a notice with no open step)

INDEX_KEEP = 32
WARM_EVERY = 2.0
WARM_PARALLEL = 2
SAVE_GROWTH = 16 << 20
STOP_SAVE_SECONDS = 5.0
BUILD_FORMAT = 1
BUILD_KEEP_DAYS = 14
BUILD_DIR = "plane"         # under daemon/
```

The open line, §5's format, is pinned by its test as an exact string with
the figures substituted.

**`sminos_uplink.py`:**

```python
class Sender(threading.Thread):
    def __init__(self, lane, cred, generation, put, ended): ...   # lane: "log" | "session"; put: the stream's items.put
    def send(self, frames, then=None): ...     # main thread; frames -> wire lines queued as one entry
    def warm(self): ...                        # main thread; dial now if no connection is held
    def release(self, project): ...            # session lane: this project's entries may go
    def close(self): ...                       # shut the socket, drop the queue, exit

# items the sender puts on the stream's queue, read by serve_link in arrival order:
#   ("sent", [then, ...])     each then() run on the main thread, in order
#   ("closed", why)           as a NotDelivered today: the stream ends

IDLE_CLOSE = 60.0            # SMINOS_IDLE_CLOSE overrides, for a test
SEND_QUEUE_MAX = 16 << 20
SLOW_POST_SECONDS = 5.0
# daemon.log lines: "uplink: <lane> lane dialled the hub (connection #n)";
#   "uplink: <lane> lane closed connection #n after <k> POSTs (idle|the hub closed it|failed: <why>)";
#   "uplink: a <lane> lane POST took <s> s"
```

`Link` holds `self.log_lane` and `self.session_lane`; `Link.post(frames)`
is removed in favor of `self.log_lane.send(...)` / `self.session_lane.send(...)`
at each site §3 assigns; `post()` and `exchange()` stay for the acker.

**The mod (`bridge-state.tsx`, `bridge-stream.tsx`, `bridge.tsx`):**

```ts
export const RESPAWN_FIRST_MS = 0
export const RESPAWN_STEP_MS = 1_000
export const BLOCK_TAIL = 65_536          // characters of a block's catch-up text kept
export const RESYNC_MAX = 4_000_000       // characters of a resync's JSON
type Block = { index: number; kind: string; text: string; upTo: number; id?: string; name?: string; uuid?: string; namedAt?: number; truncated?: true }
```

**The child (`sminos_bridge.py`):** `BLOCK_TAIL = 65536`; `_message` and
`_fold` keep `uuid`, `namedAt`, `truncated`.

**The hub (`apps/desk-hub/src/objects/project.ts`, `machine.ts`):**

```ts
type Lane = 'replies' | 'control'
protected toMachine(name: string, generation: number, frame: DownFrame, lane: Lane): Promise<'written' | 'offline'>
private toMachineAll(name: string, generation: number, frames: Iterable<DownFrame>, lane: Lane): Promise<'written' | 'offline'>
// queueKey(name, generation, lane) = `${name}#${generation}#${lane}`
private async fromMachineFrame(ctx: MachineContext, frame: UpFrame): Promise<'stale' | Promise<unknown>[]>   // the writes the frame queued
export const WRITE_TIMEOUT_MS = 10_000      // machine.ts; EndCause gains 'write-stalled'
```

**The web (`apps/desk-web/src/depth/stream/layer.ts`):** `snapshotEntry`
reads `uuid`; `load` names a block that carries one; `resume` keeps a block
the fresh snapshot carries (§9). `dx4-stream.json`: `[{ "name", "steps":
[{ "message": <DX4 envelope or "resubscribe">, "drawn": { "<agentId or
main>": [{ "turnId", "agentId", "step", "index", "kind", "text",
"settledBy" }] } }] }]`, the consumer's and the layer's test replaying it.

**The reference consumer (`sminos/tests/dx4_consumer.py`):** `Consumer(scope_agent, previous=None)`
with `take(envelope)`, `blocks(agent)`, `rows`, `errors`;
`Inventory.from_sources(transcript_path, dx5_events)` with
`check(consumer) -> {"holes": [...], "vanished": [...], "partial": [...], "dups": [...]}`.

**Fixtures:** `hub_standin.py` on HTTP/1.1 with `posted[].conn` and
`sessions[].at`; `pause_proxy.py <hub-url> <port-file>` with
`POST /control/arm {"on": "next-events" | "now", "seconds"}` (answered once
armed), `GET /control/state` (`armed` | `paused` with the bytes held back and
when | `resumed`), and `POST /control/resume`; the instrument waits on
`state` for each step. `Live.start_session(headless=False, thinking=False,
model="haiku")` in `sminos/tests/mods/live-bridge-check.py` (M2), the
existing call unchanged in meaning.

**Instruments:** `sminos/tests/bench_open.py` (`--uplink --hub local|standin
[--maws DIR] [--live [--thinking] | --synthetic-rows N] --scenario
{idle,after-prompt,mid-message,long-answer,kill,restart,held} --opens N
[--pause-stream S --backlog B]`; `--micro --session <id> --sminos-home <dir>`),
`sminos/tests/bench_scale.py opens <scripts-dir> --live L --large G`,
`sminos/tests/bench_index.py <transcript>`; all import the scripts from the
plugin root they sit under, never from a plugin cache, and run under a
temporary HOME and SMINOS_HOME of their own unless `--sminos-home` names one.

**Review rung for the branch:** `doperpowers:review-code` at **xhigh** (the
panel). The branch changes the uplink's threading, the plane's continuity
rules and the bridge's protocol in two languages, with two MAWS changes
beside; a single reviewer reads one of those well in a pass.

## Surprises & Discoveries

- Observation: the hub holds a machine's POST for the replies it owes the
  machine's own stream, not for the browser — but it waits on the whole
  reply chain's tail, which is shared across every connection to that
  machine, and the browser's subscribe is queued on the same chain.
  Evidence: `apps/desk-hub/src/objects/project.ts` at `dc3f9d87e`:
  `fromMachine` — "Settled at once for a frame that owes no reply, which
  most of a stream's frames are" — awaiting
  `this.queues.get(queueKey(ctx.machine, ctx.generation))` after every
  frame; `carry` → `this.toMachine(route.machine, route.generation, { t:
  'subscribe', … })`; `toMachineAll` chaining on `this.queues.get(key)`.
  A subscription's message to a browser ends in `this.toSocket(socket, …)`,
  unawaited. (Review finding P1-1, 2026-10-20.)
- Observation: every stream of the owner's uplink ends in the same 503
  `delivery-failed`, `ARCHIVE_EVERY` after it connected; the POST is the
  re-`hello` batch, held up to a minute first.
  Evidence (daemon.log, 2026-10-20): connected 03:42:17 → 503 03:57:18;
  04:27:06 → 04:42:07; 04:42:08 → 04:57:10; 05:28:40 → 05:44:02; 06:06:21 →
  06:22:35; 06:22:37 → 06:37:38; 06:37:39 → 06:52:54 — each
  `{"error":"delivery-failed", …, "frames":7}` (6 or 9 on two). `ARCHIVE_EVERY
  = 900` (`sminos_archive.py`); `Link.tick` posts `[hello…]` for every opened
  project at `next_confirm`. The two abandoned opens (06:19:34, 06:22:02) sit
  inside stream 219's last minutes. Another agent diagnoses the hub's side.
- Observation: today's 5 s notice expiry cannot survive a long answer after
  a thinking block, since the engine flushes a message's rows at its end;
  the open gate hid it (an open mid-message died at the gate first), and the
  live path's discontinuities are not logged.
  Evidence: `release`'s `if now - at > NOTICE_WAIT: end("discontinuity", …)`;
  the bench's 2,445 ms and 2,319 ms from a thinking block's notice to its
  flush at the message's end **[M]**; `grep -c "did not reach the
  transcript" daemon.log` → 0, and `Subscription.end` logs only an end
  before the snapshot. (Review finding P1-2.)
- Observation: a build's size and cost, on a synthetic transcript shaped
  like a real one (15,000 rows, user / assistant text / tool_use / tool_result
  with `api-request` noise, 163 MB).
  Evidence (this machine, 2026-10-20): `build cpu 0.82 s wall 1.11 s, state
  8.9 MB (peak 42.1 MB)`, `pickle 2.2 MB in 0.008 cpu s`, `unpickle in 0.284
  cpu s`, `page: 124 rows in 0.003 cpu s`. A load is a third of a build, not
  free; the warmer is what makes a live session's open warm.
- Observation: the web's `resume` drops a block the fresh snapshot carries
  when the old subscription had named it and the reconnect's history is
  empty; `blockRow` cannot restore it.
  Evidence: `apps/desk-web/src/depth/stream/layer.ts` at `dc3f9d87e`,
  `resume`: `for (const index of old.named) { request.blocks.delete(index);
  … }` then `settledBy = … lands(block.settledBy) ? … : landing; if
  (settledBy === null) continue;` with `lands = (uuid) => merged !== null ||
  this.uuids.has(uuid)` from `desk-transcript.ts`. (Review finding P2-4.)
- Observation: the hub stand-in speaks HTTP/1.0 (`protocol_version =
  "HTTP/1.0"`, `hub_standin.py`), so connection reuse could not have been
  observed against it. (Review finding B3.)

- Observation: the every-15-minutes 503 is a count of projects in one POST,
  not a timer: the archive confirmation posts one `hello` per opened project
  in a single POST, and the deployed hub answers 503 `delivery-failed` once
  a POST carries more than about six projects' hellos.
  Evidence (the owner's forwarded diagnosis, `/tmp/dsk-scripts/503-diagnosis.md`,
  2026-10-20, read from both Macs' daemon.log): `"frames":N` was 6 or 7 in 56
  cases (5, 9 or 10 in three); the failing project varies; the failures began
  when the machines reached a seventh project and every confirmation fails at
  13; the connect handshake's 13 one-project POSTs all succeed. The hub's
  `Machine.frames` and `Project.fromMachine` discard the exception (logs show
  only `machine-stream` `end`, cause `undeliverable`); the likeliest
  mechanism, unconfirmed, is the Workers call-chain limit ("Subrequest depth
  limit exceeded", about 16), each project's `have` callback into the same
  `Machine` deepening the chain within one POST. The machine-side fix is
  doperpowers PR #296 (sminos 1.2.1: one POST per project's confirmation);
  `relay_rpcs` still batches reply-owing `rpc-result` frames across projects
  (`docs/doperpowers/TECH-DEBT.md`). M4 owns the hub side (its first task).

## Decision Log

- Decision: verification. The spec gets one independent review by the
  `doperpowers:adversarial-reviewer` agent (technical-heavy) and, its
  execution section having nine milestones, that agent's buildability
  review in the same round; the branch is reviewed by
  `doperpowers:review-code` at xhigh (the panel). The independent review and
  the execution are the owner's, by their brief.
  Rationale: the design is a measured fix list, not a novel architecture;
  the risk is in the concurrency of §3 and §8 and the continuity rules of
  §2 and §9, which the adversarial read and the panel cover.
  Date/Author: 2026-10-20, the authoring session (smns-erb-71).
- Decision: two sender lanes with marks split by whether the handshake heals
  them (§3), over the plane on its own thread, one lane, or parallel POSTs.
  Rationale in §3. Date/Author: 2026-10-20, the authoring session.
- Decision: named blocks ride in `streaming` with their row's uuid (§2),
  over a faster file poll under the gate, or a snapshot with a hole.
  Rationale in §2. Date/Author: 2026-10-20, the authoring session.
- Decision: the build saved and warmed; the tail-first snapshot and build
  cancellation dropped; the look off the open path (§4). Rationale in §4.
  Date/Author: 2026-10-20, the authoring session.
- Decision: serialize-once in the child dropped (§10). Rationale there.
  Date/Author: 2026-10-20, the authoring session.
- Decision (review round 1, P1-1): a hub milestone (M4, §8) — a POST waits
  for its own replies, two chains per stream, a bounded write — replacing
  the first draft's "no hub change". Rejected: answering every POST on
  receipt (changes DX2's 200; the WebSocket phase's); a hub test control in
  the deployed Worker for the pair proof (the pause proxy reproduces a
  blocked chain through the real code without one).
  Rationale: the chain is shared across connections and carries the
  subscribe, so the lanes alone isolate nothing at the hub (§1). No Durable
  Object storage change. Date/Author: 2026-10-20, the authoring session.
- Decision (P1-2): a notice's row is due at its step's end, not at its
  notice (§2), for carried and live notices alike; the first draft's
  backdated `noticed` is withdrawn. Rejected: a longer fixed `NOTICE_WAIT`
  (any fixed value fails some answer's length).
  Date/Author: 2026-10-20, the authoring session.
- Decision (P1-3): the warmer bounded — a background queue behind
  foreground jobs, one warm job per transcript, `WARM_PARALLEL` 2, round-robin,
  no look warming (§4); the scale proof `bench_scale.py opens`. Rejected: a
  semaphore held inside the job (it would block the worker and the opens
  behind it).
  Date/Author: 2026-10-20, the authoring session.
- Decision (P2-4): a web milestone (M3, §9): a block the fresh snapshot
  carries is kept, named from the snapshot's `uuid`; the parity fixture
  `dx4-stream.json` shared with the reference consumer. Rejected: having the
  plane withhold carried blocks on a reconnect (it cannot tell a reconnect
  from a first open, and the hole would return).
  Date/Author: 2026-10-20, the authoring session.
- Decision (P2-5, B1): acceptance measured end to end (E) through the real
  uplink and the real hub code on the local hub, N kept as a diagnostic;
  `bench_open.py` split into the full path and a labelled micro-benchmark;
  the target load band taken from the MacBook's own windows or an isolated
  host, a missing band result recorded as incomplete; the deployed-hub
  timings named as the owner's.
  Date/Author: 2026-10-20, the authoring session.
- Decision (B2): a reference consumer with thinking, text and tool blocks,
  per-subscription sequence, the web's reconciliation rule, and an
  inventory from the sources of truth (M1), replacing the first draft's
  pointer to a `Browser` the bench never had.
  Date/Author: 2026-10-20, the authoring session.
- Decision (B3): the stand-in on HTTP/1.1 with connection ids, the sender's
  permanent connection lines, and a by-hand read of the owner's log for the
  real edge (M6); the first draft's "count not-delivered lines" withdrawn.
  Date/Author: 2026-10-20, the authoring session.
- Decision: rollout order — the hub (M4) before the lanes (M6) roll; the
  web (M3) before the sminos snapshot change (M5) rolls, and every open
  desk client refreshed or relaunched onto M3 before M5 rolls (review
  finding D3; the first draft's "either order degrades to today, never
  worse" withdrawn: an open client keeps its loaded streaming layer, and a
  web rollback under a live M5 brings the block loss back).
  Rationale: with new sminos and an old or unrefreshed web, a reconnect
  mid-message loses a block (P2-4); with new sminos and old hub, a held
  re-`hello` still holds the session POST (P1-1).
  Date/Author: 2026-10-20, the authoring session.
- Decision (review round 2, D1): in the hub, every owed reply must resolve
  `'written'`; an `'offline'` stops the POST as failed without counting
  the frame (§8), tested with a timed-out hello inside an opening bundle
  (M4) and the uplink's marks preserved on the 503 (M6).
  Date/Author: 2026-10-20, the authoring session.
- Decision (D2): the child's resync merge keeps a uuid-bearing block while
  still adding the old `settled` and dropping stale unnamed copies (M5), with
  a real-child scenario in `bridge_order.py`.
  Date/Author: 2026-10-20, the authoring session.
- Decision (X1): the pair proof's steps ordered and each observable
  (subscription streaming → upload on the same generation → the proxy armed
  and reporting `paused` → a 4 s window, one duration everywhere, under the
  local hub's silence bound → `resumed` → the open); the 15 s run withdrawn
  (it measured reconnection, not continuity).
  Date/Author: 2026-10-20, the authoring session.
- Decision (X2): extending `Live.start_session` (headless, thinking, model)
  under its isolation contract is part of M2; a thinking scenario counts an
  open only when the probe shows it fell inside the thinking-to-text window.
  Date/Author: 2026-10-20, the authoring session.

- Decision (pre-flight): version numbers. main moved to sminos 1.2.0 (PR
  #297) and 1.2.1 follows (PR #296), so the Concrete Steps' `1.1.3` for M1 is
  stale. Each sminos milestone bumps to the next patch above both main's
  sminos version and the branch's last; when main moves the controller merges
  it into the branch (never a rebase), takes main's side of a version
  conflict, and bumps above it in the same commit as the next change.
  Date/Author: 2026-10-20, the plan-executor (controller).
- Decision (pre-flight): M3 and M4 go on two MAWS branches,
  `desk-open-fast-hub` (M4) and `desk-open-fast-web` (M3), each in its own
  worktree off `origin/master` and its own PR, rather than one branch
  `desk-open-fast`. Rationale: M4 needs nothing from M1 and starts beside it,
  M3 needs M1's fixture and starts later; one shared worktree would put two
  executors in one tree; and the rollout deploys the web and the hub at
  different moments (the web before M5 rolls, the hub before M6 rolls), which
  two PRs merge independently.
  Date/Author: 2026-10-20, the plan-executor (controller).
- Decision (pre-flight): M6 starts only once PR #296 (the per-project
  confirmation, `Link.tick`) is merged into this branch, since M6 rewrites
  every post site `Link.tick` uses.
  Date/Author: 2026-10-20, the plan-executor (controller).

- Decision (M4, against the 503 diagnosis): §8's changes 1–3 do not cover
  the periodic 503's likeliest cause, so M4 adds a fourth. Under change 1 a
  `hello` still owes its `have`, which the `Project` writes by calling back
  into the same `Machine` while the POST is open, and `Machine.frames`
  handed a POST's projects their runs one after another. The counts fit a
  call-depth limit of about 16 (one hop Worker→Machine, two per project:
  Machine→Project, Project→Machine.send, so about 7 projects; the logged
  `"frames":6|7` in 56 of 59 cases). The local runtime has no such check, so
  one POST of 13 or 30 hellos answers 200 there before and after. **The
  fourth change**: `Machine.frames` hands every project's first run to its
  project in one synchronous pass; each project's later runs wait behind its
  earlier ones and none follows a failed or stale run; the answer is read in
  POST order, so a 503's `frames` counts the frames before the failed run in
  POST order, and other projects' runs after it may have applied uncounted —
  the handshake heals that as for any 503 (uploads idempotent, re-`hello`s
  harmless). Rejected: the `Machine` writing owed replies itself (reorders
  `have` against the backlog), a self-call per run (does not reset the depth
  under the same hypothesis), an explicit bound (every non-200 ends the
  uplink's stream). The failing run is now logged (`machine-stream`
  `run-failed` with its position and error; the `Project`'s `frame-failed`,
  `reply-unwritten`, `send-failed`), so production names the mechanism the
  next time it happens. Unverified in production: with uplinks at sminos
  1.2.1 the batched re-`hello` no longer occurs.
  Date/Author: 2026-10-20, the M4 executor, folded by the controller.
- Decision (M4): lanes for frames §8 does not list — a `not-open` refusal of
  an `events` frame, and a bad `hello` or `events` list's refusal, go on
  `replies` and are owed; a `not-open` refusal of a session-plane frame and
  `relay`'s `unsubscribe` for a sub with no route go on `control`, unowed.
  The write bound is the head frame's wait for the reader, not its wait in
  the queue: `Machine.write` queues every write to a stream behind the one
  before it, whichever project or lane sent it, and `Machine.take` starts
  `WRITE_TIMEOUT_MS` when the frame reaches the head (reversed on review the
  same day: the first build started the clock at `write`, and since the
  queues are per project, thirteen projects' backlog pages queued together
  ended a healthy, draining stream `write-stalled`; a paced-reader test with
  twelve projects pins it). Bounding the aggregate in-flight writes across
  projects was rejected (a count shared between Project objects, and still a
  bound tied to queue depth). Heartbeats are bounded too.
  Part (b) of the test lives in `machine-end.test.ts` (the Node suites are
  typed apart from the Worker's); part (c) stalls the `have` write through a
  seam (`WRITE_STALL_PATH` over a new protected `Machine.put`, `Timing`
  gaining `writeTimeoutMs` so the suite bounds it at 1 s), since local
  socket buffers absorb a small frame.
  Date/Author: 2026-10-20, the M4 executor, folded by the controller.
- Decision (for M6, from M4): the log lane never merges two `send()` entries
  into one body: each entry is posted as its own body or bodies, and each
  call site sends one project's reply-owing frames per entry (the connect's
  bundle is one project's, as today; uploads one project per entry). The
  machine-side half of the bound, as sminos 1.2.1 does for the
  confirmation, whatever the hub's mechanism turns out to be. The session
  lane's frames owe no reply under §8 and may share a body.
  Date/Author: 2026-10-20, the controller.

- Decision (M1): the open line's `N` counts from the subscribe frame's
  arrival (`opened`, backdated through the wall clock's `Link.received`),
  while `OPEN_WAIT` still counts from the subscribe call (`started`), since
  M1 changes no behavior of the open. N and M are on the subscription's
  monotonic clock, A on the wall clock. §5's two-line block is one
  daemon.log line; missing pieces read `no bridge`, `bridge: no snapshot`,
  `build: none`, `cut null`. `Built` also carries `rows`; the cut's
  on-disk state is computed in the Subscription (`cut in built.emitted`),
  so M5 needs no change to `Built`. `warm` / `cold` is a Transcript flag:
  the first extend of an index, or the one after a Reset, is cold.
  Date/Author: 2026-10-20, the M1 executor, folded by the controller.
- Decision (M1): the reference consumer's errors are strings led by their
  kind; it records and does not apply messages after `end`; its watermark
  error is per subscription (an inherited drawn watermark is dropped
  silently, as the web does); it holds paged rows before the snapshot's, as
  `desk-transcript.ts` does; its merge leaves out the web's offChain
  vouching (the plane's own tests prove chains). On resume, a fresh copy of
  a block the old subscription named and no longer draws (its row landed) is
  drawn when named, dropped when unnamed. The inventory: holes from the
  first row seen (or the first on disk once `more: false`); `partial` a
  block drawn while its row was held; `vanished` the consumer's named-block
  vanishes plus unnamed leaves whose row was not held; `dups` rows delivered
  twice plus own-loop blocks drawn after they settled; block checks cover
  the consumer's own loop. `fake_session.py` records the events it emitted
  (the inventory's DX5 source).
  Date/Author: 2026-10-20, the M1 executor, folded by the controller.
- Decision (M1): `dx4-stream.json` keeps Interfaces' top-level array and
  adds per sequence `about`, `agent`, `errors` and an optional `inventory`,
  per step an optional `note` and the store-side replay keys `settle`,
  `landing`, `lands`, so M3's layer test replays it without a store. The
  stand-in keeps its existing `received` beside the new `at` (the same
  stamp; `measure_pages.py` reads `received`), and closes a connection whose
  request body went unread. The pause proxy's port file is JSON
  `{"proxy", "control"}`; its `held` counts bytes read and not forwarded
  plus `FIONREAD` on the hub socket, keeping the maximum after resume.
  Date/Author: 2026-10-20, the M1 executor, folded by the controller.

- Decision (M1, three review rounds): the inventory's `check(consumer)`
  returns six keys — `holes`, `vanished`, `partial`, `dups`, `undrawn`,
  `residual`. An own-loop block that streamed (in the DX5 source), whose row
  reached the subscription live (a `row` after the snapshot, not history or a
  page) and was never drawn before it landed, is `undrawn`, unless the DX5
  source positively shows §2's accepted hole: the snapshot event naming that
  subscription (`{"type":"snapshot","sub":<the DX4 sub it served>, …}`) comes
  after that request's step `end` (a turn `complete` does not count). With no
  such keyed snapshot event the block is `undrawn` — the strict reading: a
  run whose DX5 source records no keyed snapshots can never report
  `residual`. A page holding a row twice is held once and recorded as a dup
  (a held row paged again is not). A truncated tool block's tail is not
  compared against a reserialized row (JSON whitespace is free); the
  inventory checks it as an exact suffix of the input the source streamed,
  a mismatch reported as `partial`. Inventory source reads raise on any
  failure but a missing transcript. A waiting build answer carries its
  figures, so an open that ends waiting reports the first build's kind, the
  CPU summed across builds and the last build's rows. The consumer's page
  marks apply only to the rows a page newly holds, as `desk-transcript.ts`
  does. The web's own `older()` does not dedupe within a page (left to M3).
  Date/Author: 2026-10-20, the M1 executor and its reviewer, folded by the
  controller.
- Decision (for M2): a live instrument that wants `residual` to be
  reportable records, in one ordered DX5 stream, the bridge's snapshot line
  for each subscription stamped with the DX4 `sub` it served, and the step
  ends. The plane knows which subscription a snapshot line served and the
  bridge does not; how the instrument learns it (a probe of its own, or a
  log line in the plane) is M2's to choose, within M2's "does not touch any
  behavior".
  Date/Author: 2026-10-20, the controller.

- Decision (M3, amending §9): on `resume`, a carried block the old
  subscription had named keeps the text already drawn, not the snapshot's.
  The `block-row` follows a block's last chunk, so that drawn text is whole,
  and keeping it also keeps it whole when §7 cuts the carried copy to its
  last `BLOCK_TAIL` characters. The web's existing `resume` test, which M3
  must keep passing, expects exactly this (`Named` over the copy's `Nam`).
  The fixture cannot tell the two readings apart; the reference consumer
  (which took the snapshot's text) is amended to match in M5. A block the old
  subscription already settled: an unnamed copy in the snapshot is dropped,
  a named one drawn (consumer and web alike). The fixture is replayed whole
  by `layer.test.ts` (all 14 sequences, rows landing through each step's
  `settle`); its `errors` and `inventory` keys judge the whole view and are
  not replayed there. Two differences between the consumer and the web,
  left as they are: after an `n` gap the web's project client resubscribes
  and never delivers that message, where the consumer applies it (a line in
  the consumer's docstring, M5); and the rows store's `older()` holds a row
  a page carries twice (confirmed by M3; out of its scope, residue).
  Date/Author: 2026-10-20, the M3 executor, folded by the controller.
- Decision (M3, consequence for M8): a block still streaming (unnamed) takes
  the snapshot's text on a reconnect, so once §7 cuts catch-up copies to
  their tail, a reconnect during a block larger than `BLOCK_TAIL` draws only
  its tail until the block's row lands and draws it whole. Accepted for this
  branch: blocks past 65,536 characters streaming across a reconnect are
  rare (a huge tool input), and the loss is cosmetic and self-healing; a web
  rule splicing a truncated tail onto overlapping drawn text is residue.
  Date/Author: 2026-10-20, the controller.

## Outcomes & Retrospective

Pending — written at finish.
