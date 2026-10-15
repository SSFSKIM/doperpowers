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

- [x] M1 — Codes in Python, and a daemon that is concurrent (DC4.G4) —
  2026-10-15, reviewed clean (98bd8a69..cc3c49e1; one fix wave: a busy
  stream's shutdown, canonical base64url)
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
- Decision: Refresh against the parent. The composite at MAWS `5c5aab90`
  (blob `ff2454ff`) differs from the pin `1c4f1c42` only in the children's
  status lines and the Tracking Map; DX1, DX2 and DX7 are as pinned. The
  vectors come from MAWS `140c834b`
  (`apps/desk-hub/src/protocol/vectors/codes.json`, unchanged since). A G1
  amendment is being folded by the composite's writer (DX1 negatives for a
  `hub/` event's writer, seq and ts; DX2's `hb-ack` and `rejected`
  frames): when it lands, the vectors are re-copied from the commit it
  cites and the test pins the new negatives. This child's branch is the
  worktree's (`worktree-agent-a6d7f69a8ab5f500f`), not the
  `smns-erb-uplink` the Tracking Map names: an earlier attempt there could
  not run git.
  Date/Author: 2026-10-15, controller (pre-flight).
- Decision: **Process, not thread** (§8 unknown 2). The uplink is its own
  process, `sminos daemon uplink`, which `daemon run` starts as a child and
  supervises from a small supervisor thread (restart with backoff when it
  exits; SIGTERM to it, then a kill, when the loop stops or restarts on a
  change of its own code, which now counts the uplink and codes modules).
  The uplink holds `daemon/uplink.lock` so at most one runs per
  `SMINOS_HOME`, and exits when its parent is gone (an orphan left by a
  killed loop does not outlive it). Inside, a reader thread only reads the
  stream (SSE parse, no sminos calls) into a queue, and the process's main
  thread does every sminos call — verify, import, deliver — so sminos's
  per-invocation module caches (`_PROJECTS`, `_VIEWS`, `forget_caches`)
  are never shared between threads.
  Rationale: sminos.py's caches are module globals that `tick_all` clears
  at its start, so an uplink thread calling `view_of` or `deliver_next`
  beside the tick would race them; every cross-process interaction is
  already file-locked, because the CLI's fast path already runs beside the
  daemon (`deliver_next` under `delivered/<session>.lock`, `_append` under
  `.sync.lock` shared and the file's lock). A process also isolates a
  `sminos.die` (SystemExit) or a hang in either side from the other. Cost:
  one more Python process per machine. The SSE trade (§8 unknown 2): the
  machine's `Machine` object holding the open stream never hibernates and
  is billed while it is open; accepted for a few machines.
- Decision: **Delivery of an imported event is the uplink's own**, not
  only a nudge of the tick loop: the nudge waits behind a tick that sits
  in a 30-second git phase, which would break "within a second". After an
  import the uplink runs `deliver_next` itself for that project's local
  members with anything owed (the daemon's `deliver_owed`, the same
  operation the sender's fast path calls), and touches `daemon/nudge` too.
  A delivery that blocks (a seat being resumed) delays later imports but
  never the reader thread, which keeps draining the stream.
- Decision: **What M1 builds of the import path.** To prove G4's nudge,
  M1 builds the import of an `events` frame per M3's decision bullet:
  verify each event's code against the frame's `project`, check a `hub/`
  event's writer, seq and ts by shape (DX1), append verbatim through a
  locked append beside sminos's `_append` (the same `.sync.lock` shared
  and the writer file's lock; an event at an existing `(writer, seq)` with
  the same canonical form is skipped, with a different one refused; a seq
  that is not one past the last is a gap, not appended), then deliver. A
  refused event is logged to `daemon.log` and never appended; reporting it
  up, `hello`/`have`, upload, `resend`, seen nonces, heartbeat answers,
  and liveness belong to M3. An `events` frame is imported only into a
  project known on this machine whose `.smns` names a hub; M1 reads the
  `hub` field from the `.smns` file itself (no change to sminos.py's
  `Project`), and M2's `project init --hub` writes it.
- Decision: **The credential store** is one file,
  `$SMINOS_HOME/daemon/hub.json`, mode 0600: `{hub, org, machine,
  client_id, client_secret, key}` (`key` the org key as base64url). M1's
  uplink reads it (absent → no uplink runs); M2's enrollment writes it.
- Decision: **Where the code and tests go.** The codes module is
  `skills/sminos/scripts/sminos_codes.py`, which also holds DX1's shape
  check of a `hub/` event, so the vectors pin it; the uplink module is
  `sminos_uplink.py`. The vectors are copied verbatim as
  `tests/sminos/dx1-codes.json`, the MAWS commit named in
  `tests/sminos/codes_parity.py` (the test, run from the suite as
  `marks_parity.py` is); the stand-in hub is `tests/sminos/hub_standin.py`;
  the uplink's tests live in `tests/sminos/test-uplink.sh`, called from
  `run-sminos-tests.sh` as `test-bridge.sh` is, so DC2's edits to the
  suite and these meet in a line or two.
  Date/Author: 2026-10-15, controller (M1's decisions, before dispatch).
- Decision: Exactly-once delivery across the two processes is pinned by a
  test (the composite's writer asked for it): a tick's push held at the
  inbox while the uplink imports a `human` for the same member; the
  uplink waits on `deliver_next`'s `delivered/<session>.lock`, and each
  event arrives once with each writer settled once. The lock is the
  mechanism; the test keeps it true.
  Date/Author: 2026-10-15, the composite's writer, built in M1.
- Decision: M1's executor's calls, kept. (1) "Nor the reverse" under the
  process model: a tick that fails or hangs never stops the uplink; the
  death of the `daemon run` process ends its uplink by design (launchd
  restarts both). (2) An import at an existing `(writer, seq)` is
  "present" when the canonical forms *without `mac`* agree, because this
  machine's own events are stored without a code and the uploader adds it
  on upload; M3 revisits this with the upload side. (3) A seq written
  `3.0` is stored as `3` (sminos's readers skip a non-int seq; the code is
  the same). (4) Beyond DX1, an imported event must be one sminos's log
  can hold — a printable writer with one inner `/`, an integer seq, string
  `ts` and `kind` — or it is refused. (5) A frame is imported only into a
  project whose `.smns` `hub.org` is `hub.json`'s `org`; the URL is not
  compared. (6) `hub.json`'s hub is `https`, or `http` on a loopback host
  only, since the service token rides on every request. (7) The stream's
  read bound is three heartbeat periods (DX2's liveness, simplest form;
  M3 owns `hb-ack`). (8) No `hub.json`, no uplink; restarts back off from
  1 s to 60 s. (9) The uplink stays in the daemon's process group, so
  launchd's bootout reaps it. (10) A nonce must be a string, as the hub's
  TypeScript requires, no stricter; an RPC without a string `nonce` is
  refused.
  Date/Author: 2026-10-15, M1's executor, folded by the controller.
- Decision: Canonical base64url (composite MAWS `91f839ee`; hub
  `e6bb0160`): no padding, the last character's unused bits zero, refused
  otherwise and never normalized; a code value is exactly 32 bytes and a
  nonce exactly 16, an event's `mac.nonce` and an RPC's `nonce` alike. The
  vectors are re-copied from `e6bb0160` (four `fails_by: "encoding"`
  negatives; checks in the order encoding, position, code). Reverses M1's
  call (10), "a nonce only has to be a string".
  Built in `cc3c49e1`: `sminos_codes.failure()` classifies in that order
  (anything that is not a JSON object fails by `encoding`; a lone
  surrogate, NaN or an infinity inside a well-encoded event fails by
  `code`), and one strict decoder reads the code, the nonce, and
  `hub.json`'s org key.
  Date/Author: 2026-10-15, the composite's writer; built as M1's first fix.
- Decision: **M2's shape** (against DX7's endpoints marked *M2,
  provisional* in the composite at `91f839ee`). (1) `sminos hub enroll
  <code> [--name <name>]` decodes the code as DX7's decoder does (prefix,
  canonical base64url body, JSON object, every field a non-empty string,
  `hub` https or http on a loopback host, `key` 32 bytes, `machine` an
  admitted name, which `--name` replaces), redeems at `POST
  <hub>/machine/enroll {token, machine}`, checks the answer's `org` and
  `machine` against what it asked, and writes `daemon/hub.json` (mode
  0600, written whole by rename) with the key; the key and the secret are
  never printed or logged. Each DX7 error is said in a sentence that tells
  what to do: `name-taken` names `--name` with the same code; `busy`,
  `mint-failed`, and a lost answer say to run the same command again
  (DX7: the same token and name rotate the credential), and the CLI
  retries a lost answer itself a few times before saying so. (2) An
  installation already enrolled refuses a new enrollment unless
  `--replace` is given, so a stray code never swaps the machine's
  identity. (3) **The enrolled name is the writer host**: `host_name()`
  returns `hub.json`'s `machine` when this `SMINOS_HOME` is enrolled,
  before `DAEMON_HOST` and the system name, so every writer this machine
  creates afterwards — hub project or not — is under the enrolled name,
  and nothing is written under the old one to a hub project. Enrolling
  under a name other than the current `host_name()` says so, and says
  that events already written under the old name stay local (the hub
  admits only `<machine>/…` writers). The read is cached per process
  (sminos's per-invocation rule). (4) `sminos project init --hub` writes
  `"hub": {"url", "org"}` from this machine's enrollment (refused when
  not enrolled); on a directory whose `.smns` exists, `--hub` adds the
  field to it, keeping every other field, and changes nothing else. (5) A
  project whose `.smns` names a hub is never synced through git from here
  on: the tick skips its git phases and `project attach` refuses it; its
  `remote` stays for M4's archive. (6) The Python stand-in gains DX7's
  redemption (states `open`/`pending`/`confirmed`, rotation on a second
  redemption while pending, `name-taken` compared without case,
  `token-used`, `expired`) and a test-only way to mint a token; M2
  proves G1 against it, and again against DC3's local hub when its M2
  lands and its run instructions exist.
  Date/Author: 2026-10-15, controller (before M2's dispatch).
- Decision: M2's identity rules, confirmed by the composite's writer with
  two additions. The name is global — one machine, one name — never per
  project. (a) The code's `machine` is what the browser proposes, but the
  CLI's default is the current `host_name()` whenever that passes DX7's
  grammar: an enrollment run as `sminos hub enroll <code>` on a machine
  whose host name is admitted claims the host name (and says so when the
  code proposed another), so most enrollments rename nothing; `--name`
  is the only way to claim another. Pinning the name in `hub.json` also
  stops macOS's `.local` drift (`SK-2.local` after a Bonjour conflict)
  from changing the writer host. (b) **A rename never makes this
  machine's own state read as another machine's.** `host_name()` is the
  machine's identity throughout sminos.py — a seat's meta `host`,
  `identity_local(host, boot)`, a member's `machine`, the ended-member
  scan's `e["machine"] != host_name()` — and the log cannot be rewritten.
  So `hub.json` records `former`, the names this installation wrote
  under before enrolling (the pre-enrollment `host_name()`), and one
  helper (`is_self(name)`: the current name or a former one) replaces
  every equality test that decides locality; writers are created only
  under the enrolled name. Chosen over rewriting the seat records at
  enrollment because log events (`joined.machine`, `state.machine`)
  carry the old name too and are append-only, so a rewrite would cover
  only half of it. A test keeps a seat local and controllable (list,
  send, retire) across a rename. On a rename the CLI states the real
  consequence: events already written under the old name stay on this
  machine and, once a project is a hub project, never reach the hub or
  any other machine (DX2 refuses `<old>/…` as `writer-not-yours`).
  Date/Author: 2026-10-15, the composite's writer (confirmation) and
  controller (the means).
- Decision: M2's executor's calls, kept. (1) Whether a project is a hub
  project is on `Project` (`hub`) and recorded in `project.json`, so the
  tick still knows when the checkout's root is gone; M1's uplink keeps
  reading `.smns` itself (a long-lived uplink must not see
  `resolve_project`'s per-process cache). (2) A `.smns` whose `hub` is
  present but malformed is still a hub project, with a warning: no git
  sync, and nothing imported (its org is empty) — fail closed. (3)
  `lifecycle` guards and `_own_events` read a session's files under its
  former names too, so an ended member retires across a rename. (4)
  `publish_state` runs for hub projects too (they have other machines).
  (5) The CLI's decoder refuses, beyond the hub's, only spellings no
  browser origin produces (blanks, `https:host`, `127.1`, a written-out
  IPv6 loopback); on every code the hub's encoder builds it agrees,
  pinned by `enroll_parity.py`. (6) Exit 2 for a refused code or
  `--name`, 1 for a hub refusal, an enrollment already held, or `--hub`
  unenrolled. (7) After a rename the hint says to use a new code, since
  the redeemed token is bound to the name. (8) `sminos hub show` prints
  the identity, never a secret. (9) The stand-in's error order is DC3's
  registry's (expired, confirmed, token-used, name-taken). (10) A lost
  answer is retried three times (1 s, 2 s), 30 s per attempt.
  Date/Author: 2026-10-15, M2's executor, folded by the controller.
- Decision: For M3, from the composite's writer's rulings on M2's
  concerns. (1) The uplink's reader catches any exception once `closing`
  is set (a chunked stream closed from this end raises `AttributeError`
  inside http.client; reproduced by `/tmp/dc4m2/streamclose.sh`). (2)
  When M3 opens a hub project, each live local member whose latest
  `joined` was written under a former name is re-joined once — a fresh
  `joined` under the enrolled name — so a renamed machine's live sessions
  show on the hub; their earlier history stays local. Tested with a
  rename across a live seat. (3) The supervisor restarts the uplink when
  `hub.json` changes, as the loop restarts on its own code, so `hub
  enroll --replace` takes effect at once.
  Date/Author: 2026-10-15, the composite's writer.

## Surprises & Discoveries

- The hub's `base64urlDecode` (MAWS `base64url.ts`) ignores the two spare
  bits of a 43-character value, so one code has four spellings the hub
  accepts; `sminos_codes` accepts only the canonical one. Harmless for
  verification (same bytes); anything keyed on the value string should
  know. Reported to the composite's writer for DC3. (M1, 2026-10-15)
  Resolved the same day: base64url is canonical in every contract and
  the hub's decoder strict (MAWS `91f839ee`, `e6bb0160`).
- `part` frames are not reassembled in M1, so an `events` frame over
  1 MiB is not imported until M3 builds parts. (M1)
- `peer_live`'s probe (connect, send nothing, close) reaches an inbox
  stand-in as an empty connection; a stand-in that holds should hold only
  on a real frame. (M1's tests)
- DC3's M2 landed at MAWS `bd266073` during M2: its local hub
  (`local/run.ts`) runs as documented and serves `POST
  /standin/enrollment-code`, which builds a code as the browser will. G1
  passed against it (51/51) as well as against the Python stand-in. (M2)
- sminos.py already needs Python 3.10+ (`float | None` in `Member`);
  macOS's `/usr/bin/python3` is 3.9. New code stays 3.9-safe. (M2)

## Outcomes & Retrospective
