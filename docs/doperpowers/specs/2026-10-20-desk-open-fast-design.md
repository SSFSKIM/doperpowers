# The desk: a session opens fast and dependably on a loaded Mac (2026-10-20)

Branch `desk-open-fast` off `main` at `219b150a`. sminos plugin at 1.1.2.
Design approved by the owner's brief of 2026-10-20 (the fix list of the
bridge bench, scoped to what stays inside today's machine↔hub protocol);
written by execspec steps 1–2 only, the independent review and the
execution being the owner's.

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
plane's `open` line in `~/.claude/sminos/daemon.log` says where the time
went, phase by phase; `sminos/tests/bench_open.py` reproduces the same opens
against an isolated session and prints the figures.

The work is the machine side alone — the plane, the uplink, the bridge
child and the bridge mod — and changes nothing on the wire between machine
and hub. No hub deploy is needed (§1 says why, correcting the bench on one
point); one hub-side bug this investigation found is flagged for the owner
(Surprises & Discoveries) and left alone.

## Progress

- [ ] M1 — The open line stamped at arrival, and the instruments
- [ ] M2 — The snapshot goes at once
- [ ] M3 — The uplink's sender lanes
- [ ] M4 — The build saved, warmed, and off the open path
- [ ] M5 — The child respawns at once; a resync fits the engine's limit
- [ ] M6 — Acceptance, documents, the branch review

## Terms

- **The desk**: the web (`apps/desk-web`) and the hub (`apps/desk-hub`, a
  Cloudflare Worker with Durable Objects) in MAWS. The web subscribes to a
  session through the hub; the hub forwards the subscription to the machine
  and relays what comes back.
- **The uplink**: `sminos daemon uplink` (`sminos/skills/sminos/scripts/sminos_uplink.py`),
  the process holding the machine's connection to the hub: a Server-Sent
  Events **stream** down (`GET /machine/stream`) and **POSTs** up
  (`POST /machine/frames`, NDJSON frames under the stream's generation).
  Its **main thread** does every sminos call and, today, every POST; a
  **reader** thread reads the stream; an **acker** thread answers heartbeats.
- **The plane**: `sminos_plane.py`, the session plane on the machine: the
  sessions' presence and the hub's **subscriptions**, each a `Subscription`
  joining a transcript on disk with the bridge's live stream. The **pump**
  is `Subscription.pump`, run from the main thread's **tick** on every wake
  or every 0.25 s (`POLL`), which produces the DX4 messages now due.
- **An open**: from the hub's `subscribe` frame to the subscription's
  `snapshot` message. **N** is that time; **M** is when the bridge's
  snapshot line was taken off the reader's queue.
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
  are **history**, rows past it are **live**.
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
**[M]**. The open path is what is slow, in four mechanisms, with this
investigation's corrections against the code at `219b150a`:

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

Two corrections to the bench, from the hub's code at the same commit:

- **The hub does not hold a POST until the browser has its reply.**
  `Machine.frames` (`apps/desk-hub/src/objects/machine.ts`) answers once
  each project's `fromMachine` (`objects/project.ts`) returns, and
  `fromMachine` awaits only the project's send queue to the *machine's own
  stream* — the `have`, backlog, `resend` and `refused` frames a `hello` or
  an `events` upload owes; a subscription's `session` message goes to the
  browser's socket with `toSocket`, unawaited, and owes nothing. A POST of
  plane messages is held for one Durable Object round trip. So no hub
  change is needed for any fix here, and the owner's example ("the hub
  holding a machine's POST until the browser has its reply") is not a
  mechanism in the code.
- **The long holds have one cause, and it is periodic.** Every stream of the
  owner's uplink ends with the same 503 `delivery-failed` 15:01–16:14 after
  it connected (seven streams on 2026-10-20, 03:42Z–06:52Z, daemon.log),
  which is `ARCHIVE_EVERY` (900 s) after the welcome: the POST that fails is
  the archive-period re-`hello` batch (`Link.tick`, `next_confirm`), held by
  the hub for up to a minute (the 503 came 1–74 s after the re-`hello` was
  due; the uplink's own bounds are a 30 s socket timeout and 60 s in all),
  then answered 503 with `frames`
  (what the hub applied before the frame that failed: 7 on most streams).
  Every subscription dies with the stream
  (`Link.on_welcome` → `Plane.close`; the hub ends the browsers'
  subscriptions `machine-offline`), and the browser subscribes again. That
  is a hub-side defect in `Project.hello` or the machine stream's write
  path, for the owner (Surprises & Discoveries); this spec makes the hold
  harmless to opens (§3) and the re-open after the stream's end fast (§2,
  §4), and does not touch its cause.

The bench's fix list, in its impact order, and what this spec does with each:

| # | the bench's fix | here |
|---|---|---|
| 1 | a sender thread; one persistent connection; the hub not holding a POST | §3: two sender lanes with persistent connections. The hold is not the hub's to drop (above) |
| 2 | no gate on the cut's row | §2 |
| — | a "waiting" open re-checked by the event, not the poll | subsumed by §2: no build answers "waiting" any more; every other wake is already event-driven |
| 3 | tail-first snapshot; index that survives a restart; builds cancelled | §4: the build saved and warmed; the look off the open path. The tail-first snapshot and the cancellation are dropped, §4 says why |
| 4 | the open line stamped at the reader's arrival | §5 |
| 5 | one connection from the mod to the child; or the child's role into the daemon | out of scope (the next phase, MAWS #52) |
| 6 | serialize once per event in the child | dropped, §8 says why |
| 7 | the first respawn without delay | §6 |
| 8 | resyncs under the engine's 4 MB | §7 |

## Acceptance

Each item names its instrument. Load is the 1-minute load average
(`uptime`) during the run, and a figure holds at the load named. **N** is
the plane's share: from the subscribe frame's arrival at the uplink's
reader to the snapshot message's emission, as the open line reports it
(§5) and `bench_open.py` prints it. The browser's end-to-end timings
(`window.deskLatency()`) are the owner's to take and are the point of the
whole: with N as below and the hub's hops (one SSE write down, one POST up on
a warm connection, one WebSocket write to the browser) at 50–150 ms each,
an open reads about a second in the browser.

The instruments:

- **`sminos/tests/bench_open.py`** (M1; a port of the bench's `plane_open.py`
  with `live_plane.py`'s scenarios): drives one `Subscription` exactly as
  `Plane.subscribe` builds it, against the bridge socket of a session under
  `$SMINOS_HOME`, pumped as the uplink pumps (on a wake, else every 0.25 s),
  and prints one JSON line per open with the phases of §5 and N. With
  `--live` it starts an isolated headless session the way
  `sminos/tests/mods/live-bridge-check.py` isolates one (temporary HOME,
  SMINOS_HOME and config dir, a staged copy of the plugin, the gateway keys
  through a 0600 env file; it spends haiku calls and is run by hand), sends
  prompts, and runs the scenarios named below, each N times, printing the
  per-open lines and a summary (min / p50 / max per scenario). It holds a
  reference consumer (the bench's `Browser`: DX4 applied as the web applies
  it) that counts holes, duplicates and `n` gaps.
- **`sminos/tests/bench_index.py`** (M4; a port of the bench's
  `real_index.py`): times the build of one transcript path, read-only, three
  ways — cold (a fresh `Transcript`), loaded (from a saved build it writes
  under a temporary SMINOS_HOME), warm (a second `extended()`) — printing CPU
  and wall for each, rows and bytes.
- **The open line** in `daemon.log` (§5), on the owner's Mac after the roll.
- **The hub stand-in** `sminos/tests/hub_standin.py`: `POST /control/post-fault`
  with fault `hold` holds the next matching POST until `POST /control/release`.
- **`tests/mods/bridge.test.ts`**'s harness (a fake engine with a clock, children
  and posts the test reads), for the mod.

The checks:

- **A1 — a warm idle open.** `bench_open.py --live --scenario idle` (ten
  opens, between turns, the build warm): N ≤ 0.10 s at load < 50, and
  N ≤ 0.5 s at load 100–300 (today 0.00–0.03 s at load 18–38 **[M]**;
  untested at 300).
- **A2 — an open mid-message.** `--scenario mid-message` (five opens in a
  session started with thinking on, the prompt asking for a 400-word story
  after reasoning, each open made on the text block's first chunk, after the
  thinking block's `block-row` and before the message ends — the window the
  bench's P1 hit, 2.3–2.4 s wide **[M]**): N ≤
  0.10 s at load < 50 (today 1.96–2.22 s **[M]**), the line's `waits` is 0,
  the snapshot's `streaming` carries the named block's text with its
  `uuid`, a `block-row` naming it is the subscription's message n=1, the
  row goes out as `row` once flushed, and the reference consumer reports 0
  holes, 0 duplicates, 0 gaps. Also: `--scenario after-prompt` (subscribed
  within 100 ms of a prompt): N ≤ 0.15 s (today 0.40–0.51 s **[M]**).
- **A3 — after a daemon restart, and a live session's first open.**
  `bench_index.py <transcript ≥ 100 MB>`: loaded ≤ 0.35 CPU-s where cold ≥
  0.7 CPU-s (CI-opt's 317 MB is the owner's reference transcript; the
  check reads it, prints none of it). `bench_open.py --scenario restart
  --synthetic-rows 15000` (a synthetic transcript of 15,000 rows written
  under the instrument's temporary HOME as a session's main transcript,
  opened transcript-only cold, which saves its build; then the instrument's
  process started anew and the same open made): the loaded open's N ≤ 1.0 s
  at load < 50, the cold one's recorded beside it (today 1.65 s wall at
  load 63 for CI-opt **[M]**, tens of seconds under load **[I]**). A live
  session's first open warm: pinned by M4's unit test ("a live member's
  transcript is held and extended before any subscription"), and on the
  owner's Mac the first open line of any session live for 2 × `WARM_EVERY`
  or longer reads `build: warm`.
- **A4 — an open while the hub holds a POST.** Deterministic, in
  `test_session_plane.py`'s `Uplink` class: with `SMINOS_ARCHIVE_EVERY=1`
  the stand-in is armed to `hold` the next POST carrying `hello`; after it
  is held, a `subscribe` is sent down the stream; the snapshot message
  reaches the stand-in within 1 s while the held POST is still held; then
  `release`, the stream ends as today (a POST not answered 200), a new
  stream opens and the subscription is served again. On the owner's Mac:
  the open lines in the minute before each `a POST was not delivered (…503…)`
  line show `taken − arrived` ≤ 0.05 s (today: M of 16.15 s and 35.97 s
  **[M]**).
- **A5 — the open line.** Every open line carries the fields of §5; pinned
  by the unit test of M1; visible in the owner's daemon.log after the roll.
- **A6 — a child crash.** `--scenario kill` (the child SIGKILLed
  mid-stream): the successor's snapshot reaches the subscriber ≤ 0.35 s
  after the kill at load < 50 (today 1.18 s **[M]**, of which 1.0 s the
  fixed delay).
- **A7 — a 5 MB streaming block.** `bridge.test.ts`: a tool call whose
  `input` streams 5,000,000 characters, then a reload (a new child's hello):
  every post body the harness saw is under 4,194,304 characters; the
  resync's block carries `truncated: true` and the last 65,536 characters;
  no `gap` and no second resync follow. `bridge_order.py` (the real child):
  its snapshot after that resync carries the block so marked.
- **A8 — no regression.** The gates `sminos`, `sminos-suites`, `sminos-mods`
  and `mods-types` green on the branch's head (`ci-gate`); by hand,
  `sminos/tests/mods/live-bridge-check.py` and `live-resume-check.py` pass
  against the branch.

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
  the entry, its key added to `held`, and its uuid entered in `noticed` at
  `now − age`, `age` read from `namedAt` against the wall clock — so
  `NOTICE_WAIT` runs from the real notice, not from the snapshot; a named
  block older than `NOTICE_WAIT` already (a response the engine dropped) is
  dropped from the entry and not noticed; if its row lands later it goes out
  unnamed after `UNNAMED_WAIT`, as any unnoticed row, and no `block-row` can
  follow (it came before the snapshot). For an entry of another loop the
  subscription carries (the main subscription carries every agent's), a
  named block is kept in its entry and its `block-row` relayed after the
  snapshot, as a live one is relayed today; it enters `noticed` of no
  subscription but its own loop's.
- Right after the snapshot (n=0), one `block-row` message per kept named
  block, entry order then block index, before anything else of the
  subscription: the web (`apps/desk-web/src/depth/stream/layer.ts`,
  `blockRow`, idempotent) marks the block settled-by that uuid and keeps
  drawing its text until the row lands.
- `release` is unchanged: a row whose uuid is in `noticed` goes out at
  once when the Tail reads it, and releases the rows before it in disk order.
- The residual hole: a snapshot taken between a step's end (the message's
  entry leaves `streaming`) and the flush of its rows (within the engine's
  100 ms flush timer, since the step end waits for the rows to be named)
  carries neither; the rows land within that time. Accepted.

Nothing on the wire to the hub changes: DX4's snapshot already carries
`streaming` entries and `block-row` messages; the web's `load` draws the
blocks a snapshot carries and `resume` keeps its own drawn copy when the
old subscription had named it. One DX4 document line in MAWS is stale
after this ("the producer removes a block from its snapshot state when it
applies the block's `block-row`", `apps/desk-hub/src/protocol/session.ts`'s
`Streaming.blocks` comment): for the owner, a doc edit, no deploy.

**`sminos watch`** draws a snapshot's named blocks as streamed text — a
finished block's text in the catch-up, where today it was missing. Fine.

**Why not read the row's text elsewhere.** The engine holds the unflushed
rows in memory only; the child's `/rows` route reads the disk. The text the
mod streamed is the only copy outside the engine, and the mod already keeps
it until the step ends. The alternative — the plane sending the snapshot
with a hole and the row later — loses the continuity the gate protected.

**Why not keep the gate and poll the file faster** (the bench's "until
then"): a message that streams more than 5 s after its first block's row
is announced still fails the open, and long answers after a thinking block
on a slower model do that routinely.

## 3. The uplink's sender lanes

**Today** `Link.post` runs the whole HTTP exchange on a helper thread and
the main thread waits on it, so the pump — every subscription's chunks,
rows and snapshots — stops for each POST (140–230 ms on a fresh TLS
connection; up to a minute when the hub holds one). The reader and the acker already
run apart so the stream drains and the lease renews whatever the main
thread does.

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

**Head-of-line.** The 15-minute re-`hello` hold (§1) now stalls the log lane
alone for its duration; opens, chunks, requests and RPC results flow on the
session lane. Uploads and imports wait, which is today's behavior and not
latency-sensitive.

**The persistent connection.** One `http.client` connection per sender
(`connection(cred, POST_TIMEOUT)`, dialled as today by `dial`), kept across
POSTs: each answer is read whole (`resp.read()`), a `Connection: close`
answer or any failure drops it, and the next POST dials afresh. A failure
raised while *sending* the request on a reused connection (`BrokenPipeError`,
`ConnectionResetError` from `request`/`send`: the hub closed an idle
connection, nothing of the body was processed) is retried once on a fresh
connection; a failure after the request was sent (`RemoteDisconnected`,
`BadStatusLine`, a timeout) is a loss as today — the hub may have applied the
POST, and the handshake is what heals it. A connection idle for `IDLE_CLOSE`
(60 s) is closed by the sender, so a stale keep-alive the edge dropped is
rarely met. **Warming**: `on_subscribe` calls `session_lane.warm()`, which
makes the sender dial now if it holds no connection, so the TLS handshake
overlaps the reader's connect and the build rather than following the
snapshot. The executor verifies against the real hub, from an enrolled
machine by hand, that a second POST on the same connection is served (the
daemon.log counts `a POST was not delivered` lines before and after a
quiet hour; a spurious reset per idle period would show there) and records
the edge's observed idle bound in Surprises & Discoveries; `IDLE_CLOSE`
moves below it if it is shorter.

**Bounds.** A lane whose queued bytes pass `SEND_QUEUE_MAX` (16 MiB: the hub
is not taking frames) ends the stream as a lost POST does. The sender logs
nothing per POST; a POST slower than 5 s is said once in daemon.log with its
lane and duration, so a held hub shows there.

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
fire on it. The two lanes collapse into one socket, since a hub that no
longer answers a POST with the replies it owes holds nothing: `have` and the
backlog are just frames down. `Sender.send(frames, then)`, the marks' two
classes, and the gate stay; only the transport under the sender changes.

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

**The warmer.** Live sessions' builds are kept current in the background,
so a live session's first open is warm:

- In `Plane.tick`, every `WARM_EVERY` (2 s): for each session that is live
  (`self.live`) and a member of an open project (`self.members`), whose main
  transcript is located (`sminos.transcript_now`, asked on the main thread
  as `Subscription.path` asks it, cached once found), the plane holds its
  Transcript (`acquire` once; `release` when the session is no longer live or
  no longer a member) and submits one job: `extended()`, then
  `look(disk, main, None, {}, ())` so the `Disk` cache is warm too, then the
  save rule above. The job's cost is the bytes flushed since the last one.
- `INDEX_KEEP` rises from 4 to 32: a build is 8.9 MB in memory for 15,000
  rows (Surprises & Discoveries), and the machine's live sessions are tens,
  few of them large. Eviction stays least-recently-used among transcripts
  with no subscription and no live session, saving first. A transcript the
  warmer holds is never evicted while its session is live; if the uplink's
  memory ever matters (forty live sessions of 15,000 rows would be 360 MB),
  the hold can be capped by bytes with the least recently grown saved and
  released first — not done now, and the figure to watch is the uplink's
  resident size in `sminos daemon status`.
- Agent transcripts are not warmed: they are opened less and are smaller;
  a cold one builds on its worker as today, saved after.

**The look off the open path.** `opening(t)` runs the build alone; the
snapshot goes with the subscription's `facts` as they stand (`Facts()` on a
first open) and `next_look = now`, so the look is asked on the pump right
after the snapshot and the first `subagents` message follows it (the plane
already sends one whenever the derived body changes). A cold look is
0.53 CPU-s for CI-opt's 136 metas **[M]**, which with the build off the path
would have been the open's largest remaining cost after a restart. The
desk's tree therefore refines within the look's time rather than delaying
the page; `test_a_cold_open_and_a_live_one_reach_the_same_statuses` reads
"reach" as after that first `subagents`.

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
but finds it done. *Giving opens priority over background work*: the
warmer's jobs are small (the bytes since its last run) and each transcript
has its own worker; the GIL's share between a cold build and a warm open was
measured small (0.01–0.03 s **[M]**).

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
  the web ignores today.
- **A resync is posted alone.** The poster ends a batch before a resync and
  after it, so a body holding one holds nothing else. `resyncEvent` measures
  its JSON and, over `RESYNC_MAX` (4,000,000 characters — the bounded blocks
  make this a pathological case of thousands of open requests), drops
  streaming entries oldest first and marks the resync `truncated: true`; the
  child takes what it carries.
- Pending requests' inputs are already cut at 65,536 characters with
  `truncated: true` (DX5); unchanged.

## 8. Dropped and out of scope

- **Serialize once per event in the child** (`_fan_out` dumping JSON per
  subscriber, one write per line): production has one subscriber, the
  daemon; `sminos watch` a second now and then. The gain appears at 5+
  subscribers past 3,000 events/s **[M]**, which nothing produces; the
  child's share of the hop is 0.3–1 ms **[M]**. Dropped; logged in the
  backlog with this reasoning.
- **One connection from the mod to the child, or the child's role in the
  daemon**: the next phase's design (MAWS #52), out of scope.
- **The machine↔hub WebSocket**: out of scope; §3 says how the sender
  carries over.
- **The hub's 15-minute 503**: hub-side, the owner's (§1, Surprises &
  Discoveries).
- **The web** (`apps/desk-web`): untouched; one stale DX4 comment in the hub's
  protocol types is for the owner's doc edit (§2).

## Execution

### Constraints that bind every milestone

- The Python the sminos scripts already require, standard library only (no
  new dependency); TypeScript under the engine's function-hook runtime as
  the mods are built today.
- Nothing on the wire between machine and hub changes (DX2, DX4). DX5 (the
  machine-local bridge protocol) changes only as Interfaces says, and the
  DX5 plan document gets a dated amendment line per change
  (`docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`, the DX5
  table, as earlier waves amended it).
- Every milestone that changes a file under `sminos/` ends with
  `scripts/bump-version.sh --plugin sminos <next patch>` in its own commit,
  in the same commit as the change or the one right after it on the branch.
- Running a working copy's sminos, daemon, child or mods goes under a
  temporary HOME and SMINOS_HOME, as every test here does. Never the real
  `~/.claude/sminos`, `~/.claude/settings.json` or `~/.claude.json`; never
  `~/.config/claude-secrets`; never `~/.claude/sminos/daemon/hub.json`; the
  deployed hub is called with credentials only by hand, as §3's keep-alive
  verification says, from an enrolled machine's uplink.
- Reading the owner's transcripts and `daemon.log` is read-only, for sizes,
  stamps and the open lines; nothing of their content is printed into a
  report or a test.
- Tests live beside the suites they extend: `sminos/tests/test_session_plane.py`
  (the plane; its `Uplink` class for the uplink against the stand-in),
  `sminos/tests/test-uplink.sh`, `sminos/tests/bridge_order.py` (the real
  child's order rules), `sminos/tests/mods/bridge.test.ts` (the mod). Live
  checks spend model calls and are run by hand.
- Commit by explicit paths; never rewrite history; commit messages end with
  the session's `Sminos-Session` line; no attribution trailers.
- The module docstrings of `sminos_plane.py`, `sminos_uplink.py` and
  `sminos_bridge.py` are the contract's home in the code: each milestone
  updates the paragraph its change touches.

### Plan of Work

The milestones run in order; M1 lands the instruments the others' proofs
read. M5 depends on nothing but M2's edits in the same files and follows it.
M6 executes the acceptance.

### M1 — The open line stamped at arrival, and the instruments

What exists after: every open line reads as §5; `bench_open.py` and its
scenarios run against a session, and `--live` against an isolated one.

Touches: `sminos/skills/sminos/scripts/sminos_plane.py` (`BridgeReader.put`
stamps, `Subscription.opened` from the frame's receipt, `noted`'s fields,
the build's kind and CPU answered with the build), `sminos_uplink.py`
(`Plane.subscribe(project, frame_, received)` passing `Link.received`),
`sminos/tests/test_session_plane.py`, new `sminos/tests/bench_open.py`.

Decisions: `Built` gains `how` (how the index came: `warm` or `cold` in M1,
`loaded` with M4) and `cpu_ms` (`time.thread_time` around `extended()`),
which `noted` reads. The instrument's `--live` isolation imports `Live`
from `sminos/tests/mods/live-bridge-check.py` as the bench's `benchlib.py`
did, rather than copying it; its scenarios are A1, A2 and A6's (`idle`,
`after-prompt`, `mid-message`, `kill`) with `--live`, and A3's `restart`
with `--synthetic-rows` (no session: a synthetic transcript, as the build
measurement in Surprises & Discoveries shaped one, opened transcript-only;
its loaded half takes effect with M4 and reads `cold` twice before).
Mid-message: a probe subscription watches the stream; the open is made on
the first text chunk after a `block-row` of the same step, and the open's
line records whether that block's row was on disk (the case the scenario is
for is `cut not on disk`). The reference consumer is the bench's `Browser`,
ported.

Does not touch: any behavior of the open; the figures the line reports
change in later milestones, the line's shape does not.

Proves: A5 (the line's fields, pinned in the unit test; `waits` counts the
"waiting" builds and reads 1 or more mid-message in M1, 0 after M2); the
instrument reproduces the bench's figures within its spread on the branch's
head before M2 (an `idle` open 0.00–0.05 s; a `mid-message` open ≥ 1 s),
recorded in Surprises & Discoveries as the baseline.

### M2 — The snapshot goes at once

What exists after: an open mid-message, right after a prompt, or with a
transcript not yet on disk gets its snapshot on the first pump after the
bridge's; the named block's text is in the snapshot and its row follows
when flushed; no build answers "waiting".

Touches: `sminos/hooks/mods/bridge-stream.tsx` (`track` on `block-row`,
`shownMessage`, `resyncEvent`), `sminos/hooks/mods/bridge-state.tsx` (the
block type), `sminos_bridge.py` (`_apply` on notices, `_message`, `_shown`),
`sminos_plane.py` (`build`, `Subscription.open`, `unlocated`, `snapshot`,
the kept blocks' `block-row` messages), tests in `bridge.test.ts`,
`bridge_order.py` and `test_session_plane.py`, the DX5 plan's amendment
line, the docstrings' continuity paragraph.

Decisions: §2 whole. The `namedAt` stamp is the notice event's `t` (every
emitted event is stamped in `emit`). In the child, `_message` keeps a block
whose index is in `settled` when the block carries `uuid` (today it drops
every settled block), and `_fold` still ignores chunks for settled indices;
in the mod, `track` on `block-row` keeps the block in `blocks` and marks it,
`settled` unchanged. The tests rewritten to the new rule:
`test_cut_row_not_yet_on_disk_while_chunks_arrive` (the snapshot goes at
once with the block, chunks past the watermark follow, the row lands
named), `test_cut_row_that_never_reaches_disk` (the block stays drawn until
`NOTICE_WAIT` from its notice, the subscription ends with the discontinuity
naming the row; a subscription made after that gets the snapshot without the
block and waits for nothing), `test_each_open_is_said_once…` (`waits 0`),
`test_a_null_cut_row_flushed_beside_its_streaming_block` and
`test_a_module_reload_with_the_seeded_cut` as the rule now reads; new:
"a history row's named block is dropped from the snapshot's streaming", "the
kept blocks' block-rows are the messages after the snapshot, in order", "an
open with no transcript file yet and a cut gets an empty snapshot". In
`bridge_order.py`, the `Consumer` (DX5's reference reader) takes the same
rule. The web's `resume` path (an old subscription that named the block,
the new snapshot carrying it) is exercised by the reference consumer in
`bench_open.py`'s `mid-message` scenario with a re-subscribe.

Does not touch: the uplink; the build's persistence; `release`'s rules.

Proves: A2 (by the unit tests for the mechanism; by `bench_open.py
--scenario mid-message` and `after-prompt` for the figures, recorded in
Surprises & Discoveries).

### M3 — The uplink's sender lanes

What exists after: the main thread never blocks on a POST; a held POST on
the log lane delays no open; POSTs reuse connections; the stream still ends
on any POST not answered 200.

Touches: `sminos_uplink.py` (`Sender`; `Link.post`, `post_session`, `open`,
`upload`, `deliveries`, `on_events`, `machine_presence`, `relay_requests`,
`relay_rpcs`, `tick`, `close`; `serve_link`'s handling of `("sent", …)` and
`("closed", …)` items; `on_subscribe`'s warm), `sminos_hublog.py` and
`sminos_outcomes.py` only if an in-flight flag is best kept there,
`sminos/tests/test_session_plane.py` (`Uplink`), `sminos/tests/test-uplink.sh`,
`sminos/tests/hub_standin.py` only if a control it lacks is needed (it has
`hold`, `release`, `post-delay`), the uplink's docstring.

Decisions: §3 whole; the state table is the implementation's shape. `post()`
and `exchange()` stay as the acker's path; the sender's exchange reuses
`exchange`'s deadline and shutdown-on-end logic over a kept connection
rather than a per-POST one. The in-flight flags live on `Link` keyed by
project unless the producer's own object is the natural home. The keep-alive
verification against the real hub is a by-hand step of this milestone
(Concrete Steps), its finding recorded; the executor must not call the hub
with credentials from a test.

Does not touch: the plane's internals beyond `subscribe`'s warm call; the
acker; the hub stand-in's DX2 behavior (a control endpoint may be added).

Proves: A4 (the deterministic half, in `Uplink`); the existing `Uplink`
and `test-uplink.sh` cases pass unchanged in meaning (a reconnect
mid-response, a dropped stream, a 503, a stalled POST, uploads and
`have`); new: "marks in a POST's continuation run after its 200 and never
when it fails", "a project's session messages wait for its hello's
acknowledgement and other projects' do not", "a lane past
`SEND_QUEUE_MAX` ends the stream", "a stale keep-alive on send is retried
once on a fresh connection; a failure after the send is a loss".

### M4 — The build saved, warmed, and off the open path

What exists after: a daemon restart costs an open a load, not a parse; a
live session's first open is warm; the snapshot does not wait for the look.

Touches: `sminos_plane.py` (`Transcript.load`/`save`, `Transcripts`
eviction and `INDEX_KEEP`, the warmer in `Plane.tick`, `opening` without the
look, `noted`'s `loaded`), `sminos_uplink.py` (the save at stop, the sweep
at start), `sminos/tests/test_session_plane.py` (`TranscriptIndex`, `Session`),
new `sminos/tests/bench_index.py`, the plane's docstring.

Decisions: §4 whole. Format and constants as Interfaces. The warmer's
`transcript_now` lookups are cached per session in the plane for the
session's life. Saving runs on the worker; the uplink's stop save is a job
submitted to each worker and joined with the bound.

Does not touch: agent transcripts' warming; the Disk cache's persistence
(its look is warmed by the warmer and is off the open path).

Proves: A3 (by `bench_index.py` on a large transcript and `bench_open.py
--scenario restart --synthetic-rows 15000`); unit tests: "a saved build loads and
extends from its end", "a saved build of another format, inode, or a
shorter file is removed and the build starts cold", "a live member's
transcript is held and extended before any subscription", "eviction saves
first and a later open loads", "the snapshot goes before the look and the
first `subagents` follows", "the stop saves every held build".

### M5 — The child respawns at once; a resync fits the engine's limit

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
fan-out (§8).

Proves: A6 (by `bench_open.py --scenario kill`; the unit test pins the
timers), A7 (by the unit tests named there).

### M6 — Acceptance, documents, the branch review

What exists after: the acceptance section executed as written and its
figures recorded; the documents current; the branch ready for its review.

Touches: `docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md`
(Progress, Surprises & Discoveries, the figures), `CLAUDE.md` (the sminos
row of the repo map: the plane's saved builds and warmer, the uplink's
sender lanes, in a clause each), `sminos/skills/sminos/references/setup.md`
only if a knob the owner sets is named (none is planned), the three
docstrings read once more as a whole.

Decisions: the acceptance runs on the owner's MacBook under whatever load it
has, the load recorded with each figure; a check that misses its figure at
the load it ran at is reported with the figure, not retried for a quieter
moment. The by-hand live checks (A8) run last. The version bump of this
milestone is the branch's last.

Proves: A1–A8 as written.

### Concrete Steps

Working directory: the branch's worktree root. The suites, per area:

```
bash sminos/tests/run-sminos-tests.sh                     # all; SMINOS_PART=core|suites for one part
python3 sminos/tests/test_session_plane.py                # the plane and the uplink against the stand-in
python3 sminos/tests/test_session_plane.py Session.test_cut_row_not_yet_on_disk_while_chunks_arrive
bash sminos/tests/test-uplink.sh
bash sminos/tests/mods/run.sh                             # the mods (claude plugin test), then the shell checks
ci-gate --gates sminos,sminos-suites,sminos-mods,mods-types   # the committed HEAD, on Actions
```

A passing suite prints `ok` lines and a summary with 0 failures; `ci-gate`
prints one line per gate then `GREEN <run-url>`.

The instruments, by hand (they spend haiku calls; the gateway keys in the
environment as `live-bridge-check.py` takes them):

```
python3 sminos/tests/bench_open.py --live --scenario idle --opens 10
python3 sminos/tests/bench_open.py --live --scenario mid-message --opens 5
python3 sminos/tests/bench_open.py --live --scenario after-prompt --opens 5
python3 sminos/tests/bench_open.py --live --scenario kill --opens 3
python3 sminos/tests/bench_open.py --scenario restart --synthetic-rows 15000   # no session: a cold open, then a loaded one in a new process
python3 sminos/tests/bench_open.py --session <id> --sminos-home <dir>      # one open of an existing session
python3 sminos/tests/bench_index.py <transcript.jsonl>
```

Each `bench_open.py` open prints one JSON line, e.g.
`{"scenario": "mid-message", "load1": 42.1, "N": 0.07, "arrived": 0.02, "taken": 0.02, "build": "warm", "cpu_ms": 3, "rows": 1512, "cut": "not on disk", "waits": 0, "holes": 0, "dups": 0, "gaps": 0}`,
then a summary per scenario; `bench_index.py` prints three lines,
`cold cpu 0.78 s wall 1.02 s`, `loaded cpu 0.27 s …`, `warm cpu 0.00 s …`,
with the rows and bytes.

M3's keep-alive verification, by hand on an enrolled machine running the
branch's uplink under its real SMINOS_HOME (the owner's machine, with the
owner): read `daemon.log` for `a POST was not delivered` lines over an
hour of normal use before and after; the sender's slow-POST line names any
POST over 5 s. Nothing is typed into a test from this.

Version bumps: `scripts/bump-version.sh --plugin sminos 1.1.3` (M1), then
each next patch per milestone; `scripts/bump-version.sh --check --plugin
sminos` confirms no drift.

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

**DX4 (machine ↔ hub ↔ web): unchanged on the wire.** A snapshot's
`streaming` block may now carry `uuid`, `namedAt` and `truncated`, keys the
web passes over; the subscription's messages after such a snapshot begin with
one `block-row` per block carrying `uuid`.

**`sminos_plane.py`:**

```python
class BridgeReader(threading.Thread):
    # items: ("line", obj, at) | ("unavailable", why, at) | ("refused", status, at) | ("closed", why, at); at = time.time()

class Plane:
    def subscribe(self, project, frame_, received=None): ...   # received: the frame's arrival (epoch s), the open's start

def build(t, cut, bridged):                                     # -> ("built", Built) | ("reset", why) | ("failed", why); never "waiting"
class Built:  how: str  # "loaded" | "warm" | "cold"; cpu_ms: int

class Transcript:
    def load(self): ...     # the saved build into index, ledger, chain; False and the file removed when it cannot be used
    def save(self): ...     # atomic; called under the save rule
    # the Transcript records how its index came (loaded, warm, cold) and the CPU its last extend cost; build() copies them into Built

INDEX_KEEP = 32
WARM_EVERY = 2.0
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

IDLE_CLOSE = 60.0
SEND_QUEUE_MAX = 16 << 20
SLOW_POST_SECONDS = 5.0
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

**Instruments:** `sminos/tests/bench_open.py` (`--live --scenario
{idle,after-prompt,mid-message,kill} --opens N`; `--scenario restart
--synthetic-rows N`; `--session <id> --sminos-home <dir>`),
`sminos/tests/bench_index.py <transcript>`; both import the scripts from the
plugin root they sit under, never from a plugin cache, and both run under a
temporary HOME and SMINOS_HOME of their own unless `--sminos-home` names one.

**Review rung for the branch:** `doperpowers:review-code` at **xhigh** (the
panel). The branch changes the uplink's threading, the plane's continuity
rules and the bridge's protocol in two languages; a single reviewer reads
one of those well in a pass.

## Surprises & Discoveries

- Observation: the hub holds a machine's POST for the replies it owes the
  machine's own stream, not for the browser. A plane message owes nothing.
  Evidence: `apps/desk-hub/src/objects/project.ts` `fromMachine` — "Settled
  at once for a frame that owes no reply, which most of a stream's frames
  are" — awaiting `this.queues.get(queueKey(ctx.machine, ctx.generation))`;
  a subscription's message ends in `this.toSocket(socket, …)`, unawaited.
- Observation: every stream of the owner's uplink ends in the same 503
  `delivery-failed`, `ARCHIVE_EVERY` after it connected; the POST is the
  re-`hello` batch, held up to a minute first.
  Evidence (daemon.log, 2026-10-20): connected 03:42:17 → 503 03:57:18;
  04:27:06 → 04:42:07; 04:42:08 → 04:57:10; 05:28:40 → 05:44:02; 06:06:21 →
  06:22:35; 06:22:37 → 06:37:38; 06:37:39 → 06:52:54 — each
  `{"error":"delivery-failed", …, "frames":7}` (6 or 9 on two). `ARCHIVE_EVERY
  = 900` (`sminos_archive.py`); `Link.tick` posts `[hello…]` for every opened
  project at `next_confirm`. The two abandoned opens (06:19:34, 06:22:02) sit
  inside stream 219's last minutes. The hub's side is the owner's: which
  project's `fromMachine` fails on a re-`hello`, and why its answer takes a
  minute (`wrangler tail` on the hub shows the `end` line's cause).
- Observation: a build's size and cost, on a synthetic transcript shaped
  like a real one (15,000 rows, user / assistant text / tool_use / tool_result
  with `api-request` noise, 163 MB).
  Evidence (this machine, 2026-10-20): `build cpu 0.82 s wall 1.11 s, state
  8.9 MB (peak 42.1 MB)`, `pickle 2.2 MB in 0.008 cpu s`, `unpickle in 0.284
  cpu s`, `page: 124 rows in 0.003 cpu s`. A load is a third of a build, not
  free; the warmer is what makes a live session's open warm.
- Observation: the web's `blockRow` is idempotent (`named.add`,
  `settledBy = uuid`), and `resume` keeps a block the old subscription
  named when the new snapshot carries it, resetting `settledBy` to null for
  the new `block-row` to set — the shape §2 relies on.
  Evidence: `apps/desk-web/src/depth/stream/layer.ts` at `4914cf4d`.

## Decision Log

- Decision: verification. The spec gets one independent review by the
  `doperpowers:adversarial-reviewer` agent (technical-heavy) and, its
  execution section having six milestones, that agent's buildability
  review in the same round; the branch is reviewed by
  `doperpowers:review-code` at xhigh (the panel). The independent review and
  the execution are the owner's, by their brief.
  Rationale: the design is a measured fix list, not a novel architecture;
  the risk is in the concurrency of §3 and the continuity rules of §2, which
  the adversarial read and the panel cover.
  Date/Author: 2026-10-20, the authoring session (smns-erb-71).
- Decision: no hub milestone. Rationale: §1's first correction — the hub's
  hold is for the machine's own replies; no fix here needs the hub. A
  Durable Object storage change is therefore not in question.
  Date/Author: 2026-10-20, the authoring session.
- Decision: two sender lanes with marks split by whether the handshake heals
  them (§3), over the plane on its own thread, one lane, or parallel POSTs.
  Rationale in §3. Date/Author: 2026-10-20, the authoring session.
- Decision: named blocks ride in `streaming` with their row's uuid (§2),
  over a faster file poll under the gate, or a snapshot with a hole.
  Rationale in §2. Date/Author: 2026-10-20, the authoring session.
- Decision: the build saved and warmed; the tail-first snapshot and build
  cancellation dropped; the look off the open path (§4). Rationale in §4.
  Date/Author: 2026-10-20, the authoring session.
- Decision: serialize-once in the child dropped (§8). Rationale there.
  Date/Author: 2026-10-20, the authoring session.

## Outcomes & Retrospective

Pending — written at finish.
