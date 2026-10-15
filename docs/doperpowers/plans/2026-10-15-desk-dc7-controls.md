# The desk, DC7 — the machine's controls: execution (2026-10-15)

> **Composite:** MAWS `docs/doperpowers/specs/2026-10-15-desk-design.md`
> (branch `smns-erb`; on this machine
> `/Users/new/Developer/GitHub/MAWS/.claude/worktrees/smns-erb/`), child
> **DC7** (The machine's controls — plan). **Parent pin:** the blob of that
> file at dispatch, recorded by the controller in this plan's pre-flight.
> The child's section there is its design; this document carries only the
> constraints and the milestones. Read the composite's §3 (the session
> plane), §5 (both tables), §6 (the daemon as the execution boundary,
> codes, digests, read-only), and the Interfaces DX1, DX2, DX4, DX5 (all of
> it, with its M2 and M3 extensions), and DX6 before M1. The hub's
> reference for the codes is MAWS `apps/desk-hub/src/protocol/`; DC4's
> Python codes module and uplink are this child's base.

## Progress

- [x] M1 — Presence and the session plane (DC7.G1, its first half) — reviewed clean 2026-10-15 (`19b50561`, fixes `3aa64d21`..`d51c6956`); proved against DC3's local hub at `f22e0839` (uplink walks 7/7); the proof against DC2's real M4 child, with a seeded cut, waits on DC2's M4
- [ ] M2 — The machine's policy, pending requests, settlements, and delivery outcomes (DC7.G1's second half; DC7.G3's delivery clauses)
- [ ] M3 — The RPCs (DC7.G2; DC7.G3's RPC clauses)
- [ ] M4 — Resume; the walk against the local hub; docs and version (DC7.G4)

## Constraints that bind every milestone

- **The composite has one writer**, the session that dispatched this plan.
  The controller records this plan's decisions in its own Decision Log and
  messages that session with any decision that touches a contract (DX2,
  DX4 as producer, DX5 as consumer, DX6's policy, which this child owns)
  and at each milestone's end; it does not edit the composite. DX2, DX4's
  envelope, and DX6's shapes are DC3's; DX5 is DC2's. A contract that
  proves wrong goes to that session, never patched on one side.
- **Where the code lives.** The daemon side of sminos in doperpowers:
  `skills/sminos/scripts/` beside DC4's uplink (`sminos_uplink.py`,
  `sminos_codes.py`, `sminos_hublog.py`) and DC2's bridge
  (`sminos_bridge.py`, `sminos_control.py`, `hooks/mods/bridge.tsx`). This
  child's branch starts from DC2's branch and merges DC4's branch
  (`worktree-agent-a6d7f69a8ab5f500f`) at the commit the dispatch names; it
  merges both again as they move and never rebases them. A change DC7
  needs inside the bridge or the uplink is a message to the composite's
  writer, who routes it to its owner; small, local seams (a hook point, a
  dispatch entry by `t`) may be made here and named in the milestone's
  message.
- **The daemon is the execution boundary** (§6). Nothing executes, and no
  outside-origin event is delivered, unless its code verifies against the
  org key, its freshness and nonce pass, its digest matches what is still
  pending, and the machine's policy admits it. A refusal is reported,
  never silent.
- **Isolation.** Every manual run of `sminos.py`, its daemon, a hook, or a
  bridge uses a temporary `HOME` and `SMINOS_HOME`; never modify
  `~/.claude/settings.json`, `~/.claude.json`, the plugin store, or the
  real `~/.claude/sminos`; never run `daemon install` against the real
  `HOME`; never enroll the owner's real machine. Live engine runs (Resume,
  spawn, the walk) follow DC2's live checks (`tests/sminos/live-*-check.py`)
  for how a throwaway session is started and torn down.
- **Stdlib Python**, as the daemon is today; no dependency is added.
- **The hub to test against** is DC3's local hub (the composite's "Running
  the local hub"), run from a temporary copy so DC3's worktree is never
  written; until DC3's M3 (the session plane and RPC forwarding) lands, a
  Python stand-in of DX2's session and RPC frames kept under
  `tests/sminos/`, rerun against the local hub once it does.
- **Tests.** `tests/sminos/run-sminos-tests.sh` stays green at every
  milestone; changed shell files pass `shellcheck -S warning`. No
  `Co-Authored-By` trailer. The version moves only through
  `scripts/bump-version.sh`, in M4's commit; if DC2 or DC4 bumped since,
  bump above them.

## Plan of Work

### M1 — Presence and the session plane

**At its end:** for every session of a hub project on this machine, a
change in the engine's session record (`~/.claude/sessions/<pid>.json`:
`status`, `waitingFor`, `needs`) reaches the hub as a DX4 `presence`
within a second, with `bridge` saying whether the session has a live
endpoint; machine presence (`machine`: policy and checkouts) is published
on connect. A DX2 `subscribe` for a session and an `agentId` is served
under DX4: a snapshot (rows newest first up to the last flushed row, as
many as fit; `more`; the subtree's metas; presence; the bridge's
`streaming` entries; `usage` on the main transcript), then `row`, `chunk`,
`block-row`, `subagents`, `usage` in order with no gap, `rows` pages on
request, `diff` on request (main transcript only), and `end` with its
reason, including `discontinuity` when the bridge's own stream reports a
gap.

**Decisions:**
- *One order from two sources* (DX4's watermark) is this milestone's
  central decision, recorded. The bridge's own snapshot covers only its
  in-memory state, and the mod's `block-row` can trail the row on disk, so
  the daemon cannot order transcript rows against the stream by itself.
  It joins them through the DX5 extension DC2 builds in its M4 (agreed;
  the composite's Decision Log entry on DC7's plan review, and DX5 as
  folded when it lands): every row the mod observes gets one notice
  before it is written (`block-row` for a response row, `row-seen` for any
  other), the snapshot carries a per-loop `cut` of notices applied,
  history is read from disk up to the cut, live rows follow their notices
  (read from disk once flushed; not there within 5 s ends the
  subscription as a discontinuity), a disk row past the cut that no
  notice named within 2 s is emitted in disk order, and a `block-row` for
  a row already emitted unnamed ends the subscription as a
  discontinuity.
  The proof includes a row flushed to disk ahead of a delayed bridge post,
  across subscription establishment and across a reconnect.
- *A DX5 subscription the child ends* ends the DX4 subscriptions it
  touches with `end {reason: "discontinuity"}`, as a `gap` does (DX4).
  The child holds `GET /events` until the mod's first `resync` is applied
  and ends every open subscription on any later one, so the daemon's rule
  is only "stream ended: resubscribe". A test subscribes across a module
  reload.
- *`diff`* answers DX2's `diff` down frame for a main-transcript sub.
- *Without a bridge* a subscription serves rows from the transcript alone,
  with `streaming` empty and `usage` null (§5's table).
- *Presence* reads the engine's records directly; the log's debounced
  `state` events stay the record for an offline machine and are not
  replaced.

**Touches:** a session-plane module beside the uplink; the uplink's frame
dispatch (a seam for the session frames); `tests/sminos/`.

**Proves:** the session-plane half of DC7.G1 against the stand-in, then
the local hub: presence within 1 s; a reconnect in the middle of a
response, a Worker restart overlapping transcript flushes, and a chunk
arriving while the snapshot is built, each ending with no gap and no
duplicated text, in the main transcript and in a subagent's.

### M2 — The machine's policy, pending requests, settlements, and delivery outcomes

**At its end:** the machine's policy exists and governs delivery before
anything from outside can execute: a file under `$SMINOS_HOME/daemon/`
the owner edits through a `sminos` verb, read at every use and published
in DX4's `machine`; known checkouts are the working directories the
project's members joined from on this machine; the default ceiling is the
mode the user's own settings give; on a read-only machine no
outside-origin `human` or `say` is delivered: it is recorded, settled
undelivered, and reported `refused-read-only`, while events written on
the machine itself deliver as before. The guard sits at the one delivery
boundary both the uplink's immediate delivery and the daemon's later
retries pass through, so a stopped seat is not resumed either. Every
request the bridge raises reaches the hub as DX4
`raised` with its code (DX1's `smns-hub-raised-v1`), with `terminal_only`
facts and background deadlines carried as DX4 has them; every settlement
as `settled` with its code; the machine's complete pending set is
republished on every reconnect (DX2 `pending`). Every settled delivery of
an outside-origin log event produces its DX4 `delivery` outcome with its
code (`delivered`, `recorded` for a closed terminal session,
`refused-read-only`, `failed`).

**Decisions:** the codes are computed with the org key from `hub.json`,
never shipped without one; the daemon signs only what its own bridges
reported, as they reported it.

**Proves:** the rest of DC7.G1 (requests and settlements reach the hub
with codes and are republished on reconnect), and DC7.G3's delivery
clauses: on a read-only machine a `human` or `say` from outside, to a live
session and to a stopped seat, starts nothing and settles undelivered with
its `delivery` outcome; every settled delivery of an outside-origin event
produces its outcome (`delivered`, `recorded`, `refused-read-only`).

### M3 — The RPCs and the machine's policy

**At its end:** each RPC of §5 that DX6 names (steer, interrupt, answer,
decide, model, compact, spawn, retire, resume) arrives through DX2, is
verified, executed through DC2's protocol or through `sminos` for spawn
and retire, and answered as `rpc-result`, republished until `rpc-ack`.

**Decisions:**
- *Order of refusal:* code (DX1, `smns-hub-rpc-v1`), then the binding
  (DX6: `machine` is this machine's enrolled name, `project` a hub project
  of this machine in its org, the session one of that project here;
  `wrong-machine`, `unknown-project`, `no-session`), then the ledger
  (a known nonce is answered from the ledger, before freshness), then
  freshness (older than 60 s), then policy, then the digest for an answer
  or a decision (DX6: `{session, request, tool, input_sha256}` against
  what is still pending), then the session's kind against §5's table
  (`unsupported`). Each refusal is a DX6 error code.
- *At most once* (DX6): the ledger under `$SMINOS_HOME/daemon/` claims the
  nonce before any effect and records the outcome before the result is
  sent; a nonce left `claimed` is reconciled from the action's own trace
  (a spawned seat carries its nonce; a steer's row is in the transcript),
  else answered `failed: interrupted`. Entries kept a day.
- *Results* follow DX6 as aligned with DC2's M2 (composite `744eae81`):
  steer `{row}` or `idle`; interrupt `{turnId, stopped, running}`; model
  `{model, effort}`; compact `{at}`.
- *The policy* from M2 governs every RPC: known checkouts and the
  ceiling for spawn; read-only refuses every RPC (`read-only`).
- *Compact's outcome* reaches browsers as DX4 `compact`, carrying the
  RPC's nonce, from the bridge's DX5 `compact` events for the command the
  daemon issued.

**Proves:** DC7.G2: each RPC executes through DC2's protocol; a bad code,
a stale RPC, and a seen nonce are refused and reported; a digest that
differs is refused; cutting the connection after execution, and
restarting the daemon between execution and report, each show
`uncertain` on the hub, then resolve, the RPC executed once; a spawn
retried with its nonce after a cut yields one session; a spawn outside
the known checkouts or above the ceiling is refused; on a read-only
machine every RPC is refused; an otherwise valid signed RPC routed to the
wrong machine, and one naming a session outside its signed project, are
refused before the ledger.

### M4 — Resume; the walk; docs and version

**At its end:** Resume brings an ended session back under its own id; one
walk against DC3's local hub covers DC7's acceptance; docs and the
version are current.

**Decisions:**
- *Resume* as §5 has it: `claude --bg --resume <session>` in the session's
  working directory with no other flags, serialized per session, after
  checking the session is live nowhere; then the session the engine
  reports is checked to be the same id, and a copy the engine started
  (the owner reopened it meanwhile) is stopped and the RPC failed
  `copy-started`. "Live anywhere" means any process of this machine
  holding the session, terminal or `--bg`: a session's transcript lives on
  the machine that ran it (DX6's `session-live`).

**Touches:** the RPC module (Resume), `CLAUDE.md`
(the `skills/` row: the session plane and the RPCs), `skills/sminos/SKILL.md`
only if an agent-facing behavior changes (it needs eval evidence), the
version.

**Proves:** DC7.G4 (Resume of an ended terminal session as a `--bg` job with the same
id that rejoins; refused while live anywhere and on a read-only machine;
two Resumes at once start one session; a Resume racing the owner's reopen
ends with one session, any copy stopped, the RPC failed with the reason),
and G1–G3 again in one walk against the local hub.

## Concrete Steps

From this child's worktree root:

    tests/sminos/run-sminos-tests.sh          # ends "all N assertions passed"
    shellcheck -S warning <changed .sh files> # no output

The local hub, from a temporary copy of the MAWS worktree, as the
composite's "Running the local hub" says:

    pnpm --filter desk-hub local              # the stand-in for Access on 127.0.0.1:8747

## Interfaces and Dependencies

Consumes DX1, DX2, DX5 (with its M2 and M3 extensions), and DX6's shapes;
produces DX4 as the machine-side producer and DX6's policy. Consumes DC3's
M3 (the session plane and RPC forwarding on the hub) for the proofs
against the local hub; until it lands, the stand-in.

## Decision Log

- Decision: Verification. Each milestone gets the subagent-driven
  execution's task review at its boundary; the branch gets a `high`
  review through `doperpowers:review-code` at the end, run by the
  controller.
  Rationale: the daemon is where a remote request becomes execution on the
  owner's machine; every refusal path is the boundary §6 binds, in stdlib
  Python against a TypeScript reference.
  Date/Author: 2026-10-15, the composite's writer at dispatch.

- Decision: The plan review (adversarial, 2026-10-15) found that the
  bridge's snapshot cannot order transcript rows against its stream, that
  an RPC's code does not bind it to the machine that runs it, that
  read-only delivery came after outside-origin delivery was enabled, and
  that `diff`, compact outcomes, a first `resync`, and Resume's scope had
  no written contract. All adopted: the ordering waits on a DX5 extension
  from DC2; the rest are in the composite (`71e32c68`), and the policy
  moved to M2, ahead of every path it guards.
  Date/Author: 2026-10-15, the composite's writer.

- Decision: Pre-flight. Parent pin: the composite's blob `6c8015ef` at
  MAWS `edf9dea7` (branch `smns-erb`), read at its live path, never from a
  copy on this branch. The branch is DC2's `worktree-smns-erb` at
  `664e4bd8` merged with DC4's branch at `7252a5d7` (the one conflict, the
  suite's tail in `run-sminos-tests.sh`, keeps both sides' sub-suites).
  Date/Author: 2026-10-15, controller.

- Decision: Pre-flight. M1 builds the row ordering against the agreed
  text (DC2's plan, Decision Log "M4 scope, agreed with the composite's
  writer for DC7", rules 1–4), not against DC2's code, which is
  uncommitted at dispatch: its tests drive a scripted DX5 endpoint that
  emits `row-seen`, `block-row`, the snapshot's `cut`, `ready`, and a
  stream ended on a later resync, as that text has them. When DC2's M4
  commits, the controller merges it and M1's ordering is proved against
  the real child (a follow-up wave on M1's executor); M1's tick means
  reviewed clean against the contract, and the real-child proof is
  recorded beside it when it lands.
  Rationale: the contract is agreed and DC2 builds to it; waiting would
  idle M1, and a mismatch found later is a contract question for the
  composite's writer, not a local patch.
  Date/Author: 2026-10-15, controller.

- Decision: Pre-flight. M1 publishes DX4 `machine` on connect with the
  checkouts and the policy read through one function M2 makes real; until
  M2 that function returns the default (`read_only: false`, the ceiling
  the user's settings give, or null when M1 cannot yet read it). M1 adds
  no execution path and no new outside-origin delivery, so the policy's
  place ahead of every path it guards (M2) holds.
  Date/Author: 2026-10-15, controller.

- Decision: Pre-flight. The hub stand-in for the session plane and the
  RPC frames builds on DC4's `tests/sminos/hub_standin.py` (the DX2 log
  plane's stand-in) from a file of this child's own that imports it, so
  DC4's still-moving branch merges without conflict; DC3's local hub
  replaces it in the proofs once its M3 lands, as the dispatch announces.
  The default ceiling is read from the user's own settings, never written.
  Date/Author: 2026-10-15, controller, confirmed by the composite's writer.

- Decision (M1): The session plane is `sminos_plane.py`, served on the
  uplink's stream through small seams (dispatch entries for `subscribe`,
  `unsubscribe`, `rows`, `diff`; presence in `open()`'s POST; the plane's
  tick in `Link.tick`; a wake item in `serve`). One plane per stream: a new
  stream drops the old subscriptions silently, since the hub fences routes
  by generation and ends them itself. `machine_policy()` in
  `sminos_hublog.py` is the function M2 makes real; its default ceiling is
  the string `"default"` (the engine's mode when settings name none), not
  null as the pre-flight allowed, because DC3's hub refuses a non-string
  ceiling.
  Date/Author: 2026-10-15, M1 executor.

- Decision (M1): Subscription edges. An `end` before any snapshot (unknown
  session, a bridge answering 503 when not ready, a cut row never on disk)
  is sent at `n` 0, as DC3's in-progress hub does. A bridge that answers
  503 ends the subscription `discontinuity` rather than serving the
  transcript alone, and a transcript-only subscription of a running
  session is ended `discontinuity` once its bridge answers, so streaming
  returns after a module reload. A session no longer running gets 1 s for
  its last flushes, then `session-ended`; an ended session can still be
  subscribed (snapshot, then `session-ended`). With a null cut, a
  `block-row` for a row history already holds is dropped, unless the
  subscriber holds that block's streamed text, in which case it ends
  `discontinuity`. Presence goes to the project's local members; a
  subscription may name any session that joined from this machine, ended
  ones included. Rows are complete JSONL objects with a string `uuid`;
  snapshots and pages carry up to 512 KiB of rows, at least one. The diff
  base is `origin/HEAD`, else `main`, else `master`, with read-only git on
  a worker thread, capped at 4 MiB.
  Date/Author: 2026-10-15, M1 executor.

- Decision: DX5's row order is disk order (composite `cd2667d8`, from
  DC2's M4 review: a notice posted at hook entry could precede a row the
  engine wrote earlier, and a compaction's unnamed rows were emitted after
  the next prompt). The producer now posts a row's notice after `next()`
  resolves, so within a loop notice order is write order and a notice may
  trail the flush. The consumer: history is each loop's disk rows up to
  and including its cut, once the cut's row is on disk (5 s, else
  discontinuity); live, each loop's rows go out strictly in disk order, a
  row past the cut released by the first of its own notice, a notice for
  any later row of the same loop, or 2 s with neither, and every later row
  waits behind it; a notice whose row is not on disk within 5 s is a
  discontinuity; a `block-row` for a row already released unnamed is a
  discontinuity; a `row-seen` for a released row is ignored. M1's
  out-of-order note is void. Also decided there: an `end` may be a sub's
  first message at `n` 0; a main-scope sub settles another agent's block
  on its `block-row`; the ceiling reports the settings' `defaultMode`
  (read only), `"default"` only when they name none, never as a
  placeholder.
  Date/Author: 2026-10-15, the composite's writer; M1's consumer adopts it
  in its fix wave.

- Decision: The producer seeds the cut (M1's review found a null-cut
  snapshot could draw a flushed, un-noticed row beside its streaming
  block). On its first `resync` the mod reports each loop's cut as the
  last row that loop had when the module loaded, from the engine's own
  message list, and no block of a loop enters `streaming` before its cut
  is seeded; `null` means only "this loop has no rows". The consumer then
  reads a null cut as empty history, every disk row live under the
  disk-order rule; the wait for a cut row to reach disk covers a seed not
  yet flushed. DX4's non-overlap holds with no exception. The consumer
  keeps its current null-cut handling against the scripted endpoint until
  DC2's M4 lands, then switches the endpoint to seed and is proved
  against the real child.
  Rejected: accepting the overlap as transient, healed by the
  discontinuity.
  Date/Author: 2026-10-15, the composite's writer (option a); DC2 builds
  the seed in its M4.

- Decision (M1 fix wave): Bridge presence is probed off the uplink's
  thread by `Bridges` (kept across streams; one probe at a time per
  session, rerun when the socket's inode changes or the answer is 2 s
  old; it wakes the uplink on a change), so a stalled endpoint cannot
  hold another session's presence. A pid seen dead loses its cached
  identity and is checked anew, and a running pid's identity is read
  again every 10 s, so a pid reused between two polls is found within
  that bound. The ceiling is `permissions.defaultMode`
  as the settings write it, else `"default"` (missing or malformed file
  included, as the engine reads it). `step-end` (composite `34ee27ca`) is
  relayed in DX5's order, so after its step's `block-row`s; rows waiting
  for release do not hold it. The uplink tests run against DC3's local
  hub when `DESK_HUB` names its stand-in for Access, enrolling through
  `/standin/enrollment-code` and reading as a DX3 browser
  (`tests/sminos/ws_client.py`); without it, against `hub_standin.py`.
  Date/Author: 2026-10-15, M1 executor.

- Decision: Unsubscribe differs between hubs and both stand. The real hub
  drops a sub's route before forwarding `unsubscribe`, so the machine's
  `end {reason: "unsubscribed"}` reaches no browser; the stand-in still
  delivers it. The test asserts each hub's own behaviour. `step-end` is
  not sent on local-hub runs until DC3's hub accepts it (DC3's plan
  `73a33de2`). The local hub runs as `pnpm --filter desk-hub local --port
  <n>` (no `--`).
  Date/Author: 2026-10-15, the composite's writer (`0e7da91e`).

- Decision: The suite gate under this machine's load. The three
  assertions outside the session plane that fail only at load above 200
  (Surprises, M1) are accepted as load flakes by the composite's writer
  (`0e7da91e`); a milestone whose own suites and the sub-suites it
  touches pass, with only those failing, meets the "stays green"
  constraint. The final review's evidence repeats the full suite when the
  load allows.
  Date/Author: 2026-10-15, controller, from the composite's writer.

## Surprises & Discoveries

- (M1) Under load above 200, three suite assertions outside the session
  plane fail and pass again at normal load: "at most once more: two
  frames in all" (in DC4's tech debt), "the watcher's finalize does not
  overwrite a retire" (a `sleep 0.8` race), and "the say lands within two
  seconds" (the mirror daemon's push). Recorded as load flakes.
- (M1) DC3's local hub at `f22e0839` passed the uplink walks 7/7 on two
  runs; it does not yet list `step-end` among its subscription kinds.
- (M1) `sminos.peer_records()` is cached until `forget_caches()`, and
  `view_of` runs `ps` for every live session, so membership is re-read
  when the set of running sessions changes, with a 10 s backstop, not on
  every 2 s scan.
- (M1) Presence within 1 s holds while the uplink's main thread is free;
  an immediate delivery or a stalled POST holds it (the uplink is serial
  by DC4's design).
- (M1) Contract notes sent to the composite's writer: DX4's main scope
  carries other agents' `block-row`s but not their rows, so the web needs
  a rule to settle those blocks; DX5 rule 3 with a null cut can leave
  streamed text beside its row (handled on the consumer side, above); a
  row no notice names waits 2 s and can arrive after a later named row.

## Outcomes & Retrospective
