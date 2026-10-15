# The desk, DC4 — the uplink: execution (2026-10-15)

> **Composite:** MAWS `docs/doperpowers/specs/2026-10-15-desk-design.md`
> (branch `smns-erb`; on this machine
> `/Users/new/Developer/GitHub/MAWS/.claude/worktrees/smns-erb/`), child
> **DC4** (The uplink — plan). **Parent pin:** blob `1c4f1c42` of that file (MAWS commit `a52eb12e`), as it
> stood at dispatch. The child's section there is its design; this
> document carries only the constraints and the milestones. Read the
> composite's §2 (Daemon uplink), §3 (the log plane), §6 (machines, the org
> key, what carries a code), §8 unknown 2, and the Interfaces subsections
> DX1 (the code, its canonical JSON, the Python recipe for numbers, the
> vectors), DX2, and DX7 before M1. The hub's reference Python for DX1 is
> MAWS `apps/desk-hub/src/protocol/vectors/generate.py`, with its vectors
> `codes.json` beside it.

## Progress

- [ ] M1 — Codes in Python, and a daemon that is concurrent (DC4.G4)
- [ ] M2 — Enrollment and hub projects (DC4.G1)
- [ ] M3 — Sync through the hub (DC4.G2)
- [ ] M4 — The archive, the two-machine walk, docs, version (DC4.G3)

## Constraints that bind every milestone

- **The composite has one writer**, the session that dispatched this plan.
  The controller records this plan's decisions in its own Decision Log and
  messages that session with any decision that touches a contract (DX1,
  DX2, DX7) and at each milestone's end; it does not edit the composite. A
  contract that proves wrong or unbuildable goes to that session, never
  around it: DX2 and DX7 are DC3's, and the hub is being built against
  them in parallel.
- **Isolation.** Every manual run of `sminos.py`, its daemon, or a hook
  uses a temporary `HOME` and `SMINOS_HOME` (the CLI's one-way `migrate`
  runs before every verb). Never modify `~/.claude/settings.json`,
  `~/.claude.json`, the plugin store, or the real `~/.claude/sminos`; never
  run `daemon install` against the real `HOME`; never enroll the owner's
  real machine.
- **Stdlib Python**, as the daemon is today: HMAC-SHA256 from `hmac` and
  `hashlib`, HTTP and SSE from `http.client` and `urllib`, TLS from `ssl`.
  No dependency is added.
- **The hub to test against** is DC3's local hub in the MAWS worktree:
  `wrangler dev` with its local stand-in for Access (DC3's M2 says how to
  run them; the composite's DX7 Interfaces say what they serve). Until
  DC3's M2 lands, milestones that need it test against a minimal Python
  stand-in of DX2 kept under `tests/sminos/`, and rerun against the real
  local hub once it exists. A disagreement between this daemon and DC3's
  hub is a contract question for the composite's writer, never patched on
  one side.
- **The daemon is the execution boundary** (§6). An event whose code does
  not verify never enters the log, never reaches delivery, and is reported;
  verification runs against the project being imported into.
- **DC2 is changing `sminos.py` on its own branch** (the bridge verbs,
  `push_member`'s delivery). Keep this child's changes in `sminos.py` to
  what the CLI's verbs and `.smns` need, and its daemon work in
  `sminos_daemon.py` and new modules beside it, so the two branches meet
  with small conflicts; whichever merges second resolves them.
- **Tests.** `tests/sminos/run-sminos-tests.sh` (stub `claude`; isolates
  `HOME` and `SMINOS_HOME`) stays green at every milestone, and a hub-less
  project's git mirror behaves exactly as before; shell files changed pass
  `shellcheck -S warning`. The DX1 vectors are copied into `tests/sminos/`
  with the MAWS commit they came from, and a test pins this
  implementation to every one, negatives included — as
  `tests/sminos/marks_parity.py` pins the mark grammar.
- No `Co-Authored-By` trailer. The version moves only through
  `scripts/bump-version.sh`, in M4's commit.

## Plan of Work

### M1 — Codes in Python, and a daemon that is concurrent

**At its end:** a module beside the daemon canonicalizes (RFC 8785, as
DX1 specifies it, numbers included) and computes and verifies every
shape's code, byte for byte with the vectors; and the daemon's loop no
longer blocks the uplink: a slow git phase of a hub-less project, or a
derivation, does not delay a stand-in uplink loop, and an event arriving
from the hub nudges delivery at once.

**Decisions:**
- *Thread against process* (§8 unknown 2, DC4's): decided here and
  recorded with the reason. What either must give: the uplink keeps its
  stream open and drains it while a tick runs; delivery of an event from
  the hub starts within a second of its arrival, through the existing
  nudge (`daemon/nudge`) or its equivalent; a crash of the uplink does not
  take the git ticks down, nor the reverse; the run lock and the restart
  on a change of the daemon's own code (`cmd_run`) keep working.
- *The codes module* refuses what DX1 refuses (a lone surrogate, NaN,
  infinities, a missing nonce, a value that is not base64url) and compares
  in constant time (`hmac.compare_digest`).

**Touches:** `skills/sminos/scripts/sminos_daemon.py`, a new codes module
and an uplink module beside it, `tests/sminos/`.

**Does not touch:** `.smns`, enrollment, any network call to a real hub.

**Proves:** DC4.G4, and DX1 parity: every vector reproduced; every
negative refused.

### M2 — Enrollment and hub projects

**At its end:** `sminos hub enroll <code>` enrolls the machine against
the local hub under its claimed name and stores what it needs; `sminos
project init --hub` writes the `hub` field; a second installation
claiming a name already enrolled is refused and told how to pick another.

**Decisions:**
- The code is DX7's (`smns-enroll-v1.` and base64url JSON); the CLI
  refuses what DX7's decoder refuses. The service token and the org key
  are stored under `$SMINOS_HOME/daemon/` with mode 0600, the key never
  printed or logged; the redemption's lost-response recovery is DX7's
  (redeeming the same token again while pending rotates the credential).
- **The enrolled name is the daemon's writer host**: after enrollment,
  `host_name()` (which reads `DAEMON_HOST`, then the system's host name)
  must return the enrolled name for every writer this machine creates, or
  the hub refuses its uploads as `writer-not-yours`. How the name reaches
  `host_name()` is this milestone's call, recorded; an installation whose
  host name differs from the enrolled one must not write under the old
  name to a hub project.
- `.smns` gains `"hub": {"url", "org"}` (DX1). A project with a hub stops
  using its git remote as a live path (§3); the remote stays for the
  archive.

**Touches:** `skills/sminos/scripts/sminos.py` (the `hub` verb, `project
init`), the daemon's credential store, `tests/sminos/`.

**Interfaces:** consumes DX7's enrollment endpoints, which DC3's M2 fixes
(the composite's writer relays their request, response, and error
contracts when they land): this milestone starts when they have.

**Proves:** DC4.G1 against the local hub (or the Python stand-in until it
exists, then again against the hub).

### M3 — Sync through the hub

**At its end:** for a hub project, the daemon holds DX2's stream, runs
the version-vector handshake per project, uploads its own writers'
suffixes with codes, imports what the hub sends after verifying each
code, follows `resend` and reports `refused`, tails live both ways, and
republishes on every reconnect what DX2 says it republishes (the parts
this child owns: `hello`; machine presence). It never runs a git phase for
a hub project. A fresh machine bootstraps a hub project from the hub.

**Decisions:**
- The uploader adds the code to each of its own events as it uploads
  them (DX1: every event on the hub carries one); events stored in the
  local log keep the `mac` they arrived with, and the archive carries it.
- Import is all-or-nothing per event: verify the code, and for a `hub/`
  event check what the code leaves out by shape (DX1: the writer is
  exactly `hub/` and the covered `member`, the seq a positive integer, the
  ts an ISO 8601 UTC time), then append to the writer's file through the
  same locked append the log uses, then nudge delivery. An event refused
  here is reported up (DX2's refusal report), never silently dropped.
- The daemon answers each of the hub's heartbeats (DX2): the hub renews
  the machine's lease only from the daemon's traffic.
- Liveness: a stream silent for three heartbeat periods is dead; the
  daemon reconnects with backoff (DX2).

**Touches:** the uplink module, `sminos_daemon.py`, `tests/sminos/`.

**Interfaces:** consumes DX1 and DX2; DC7 builds the session plane and
RPCs onto this stream later, so the stream's reader dispatches frames by
`t` and leaves room for the frames DC7 adds.

**Proves:** DC4.G2, every clause, with two machines simulated on one Mac
(two `SMINOS_HOME`s, two enrolled names) against the local hub: per-writer
counts, last seq, and payloads identical on both machines and the hub
after a burst of `say` on both, a daemon restart, and a dropped
connection; a fresh machine's bootstrap; no git fetch for a hub project;
refused before it enters the log — an event without a valid code, a
forged `say` under another machine's writer, an authentic event of one
project replayed into another's feed, and a `hub/` event carrying a field
its code does not cover (`via`, `msg_id`); the existing sminos suite
green.

### M4 — The archive, the two-machine walk, docs, version

**At its end:** the project's designated archive machine (DX2's
`have.archive`) writes the log to the project's git remote on a schedule,
from a clone outside the log directory; no other machine pushes it; the
docs and the version are current.

**Decisions:** git never feeds the live log of a hub project: the archive
clone is written from the log, never read into it. A machine that stops
being the designated one stops pushing at its next schedule.

**Touches:** the uplink and archive code, `CLAUDE.md` (the `skills/` row:
the hub verbs and the uplink), `skills/sminos/SKILL.md` only if an
agent-facing behavior changes (it needs eval evidence; the hub verbs are
the human's and the daemon's), the version through
`scripts/bump-version.sh`.

**Proves:** DC4.G3, and G1–G4 again in one walk against the local hub
with two simulated machines. The real two-Mac run is the composite's
recomposition, not this child's.

## Concrete Steps

From this child's worktree root:

    tests/sminos/run-sminos-tests.sh          # ends "all N assertions passed"
    shellcheck -S warning <changed .sh files> # no output

The local hub, from the MAWS worktree, as DC3's M2 documents it:

    cd /Users/new/Developer/GitHub/MAWS/.claude/worktrees/smns-erb
    pnpm --filter desk-hub exec wrangler dev  # plus the stand-in for Access

## Interfaces and Dependencies

Consumes DX1, DX2, and DX7 as folded in the composite's Interfaces;
produces nothing new for other children beyond the stream DC7 builds on.

## Decision Log

- Decision: Verification. Each milestone gets the subagent-driven
  execution's task review at its boundary; the branch gets a `high`
  review through `doperpowers:review-code` at the end, run by the
  controller.
  Rationale: the daemon becomes the place where codes are checked before
  anything enters the log or reaches a session — the execution boundary
  of §6 — in stdlib Python against a reference in TypeScript.
  Date/Author: 2026-10-15, the composite's writer at dispatch.

## Surprises & Discoveries

## Outcomes & Retrospective
