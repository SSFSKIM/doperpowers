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

- [ ] M1 — Presence and the session plane (DC7.G1, its first half)
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
  It joins them through the DX5 extension DC2 builds for this: a
  transcript cut in the bridge's snapshot, and an order for the rows after
  it (the composite's DX5, as folded when DC2's M4 lands; until then, the
  composite's Decision Log entry on DC7's plan review states the need).
  The proof includes a row flushed to disk ahead of a delayed bridge post,
  across subscription establishment and across a reconnect.
- *A `resync`* on a DX5 subscription the daemon already holds ends the DX4
  subscriptions it touches with `end {reason: "discontinuity"}`, as a
  `gap` does (DX4). That includes a child that answered before the mod's
  first `resync`. A test subscribes before the first `resync`.
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

## Surprises & Discoveries

## Outcomes & Retrospective
