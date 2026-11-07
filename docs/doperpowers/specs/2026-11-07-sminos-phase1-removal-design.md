# sminos: the phase-1 hub path removed (board #153)

Since P5's cutover finished (O14 B4, 2026-11-07), every enrolled machine runs RL1 to MAWS's relay and RL10 to its own endpoint (`mawsd`). The desk hub refuses DX2 enrollment, and no machine holds a `hub.json` any more (P5 Decision Logs 239 and 242). sminos still carries the machine side of phase 1: the hub's HTTP/SSE uplink, the DX1 request codes, the `coded` branches that serve them, and the `sminos hub enroll` machinery. Nothing can reach that code now. Its tests are about a third of the `sminos-suites` gate's ~20 minutes (board #170), and they also prove a good deal of shared behaviour only through DX2.

This change leaves sminos with one hub protocol on the machine side. Its tests prove only what runs: every shared behaviour that is now proven only through DX2 is proven again on RL10 before the DX2 code leaves.

The detailed map this spec was written from, every module, function and test by file:line and class, is [the removal map](2026-11-07-sminos-phase1-removal-map.md), read at doperpowers `904b0a35` (sminos 1.39.0). Its section numbers are cited as "map §N".

## Progress

- [x] (2026-11-07) The map (read-only, doperpowers `904b0a35`, MAWS `1a11fedf6`).
- [x] (2026-11-07) This spec.
- [ ] The spec's review: adversarial-reviewer on the design and the execution section.
- [ ] M1: devcloud's DX2 enrollment out (devcloud bump).
- [ ] M2: the opt-in local-hub modes out (tests only).
- [ ] M3: shared coverage re-pointed at RL10 (tests only).
- [ ] M4: the DX2 transport and the supervisor's DX2 arm out.
- [ ] M5: `coded` collapsed.
- [ ] M6: the `hub` verbs and `hub.json` reduced.
- [ ] M7: docs, labels and the bump (sminos 1.40.0).
- [ ] The branch review, merge, and both Macs' daemons restarted on 1.40.0.

## What changes and what doesn't (acceptance)

1. **No sminos code path speaks DX2.** Shipped sminos has no HTTP/SSE uplink to the hub, no DX1 request codes, no `coded=True` branch, and nothing that enrolls a machine at the hub or reads `hub.json` as a credential. A grep of `sminos/skills/` and `sminos/hooks/` for `run_dx2`, `load_credential`, `Stream(`, `Sender(`, `hub_standin` and `coded=True` finds nothing.
2. **The RL10 path behaves exactly as before.** These run unchanged and stay green: the RL10 conformance replay against MAWS's fixture (`rl10_conformance.py`, with today's ok count and 0 FAIL), `test_rl10`, `test_words`, `test_reach_gate`, `test_visibility` and `test_streams`. The session plane DX4 defined is still served over RL10 (MAWS's `src/endpoint/plane-a.ts` subscribes to it): `sminos_plane.py` and `Link`'s session-lane dispatch stay (map §0.1).
3. **`sminos hub`:**
   - `hub enroll`, `hub check` and `hub leave` print the line a cut-over machine prints today: this machine's enrollment is its endpoint's (`mawsd endpoint enroll|status`). They exit 1.
   - `hub show` reads `daemon/identity.json`. It prints the machine's name, hub and org. On a machine not cut over, it says the enrollment is the endpoint's and that sminos takes it at the endpoint's first welcome, and it exits 1.
4. **Enrolled means cut over.** A machine with no `identity.json` runs no uplink (the supervisor's `waiting`), keeps the terminal gate for widening (O18 D10, P5 Decision Logs 231 and 235), and is hubless to the hooks. A stray `hub.json` makes nothing count as enrolled. Its one remaining reader is `Link.on_legacy_key`, which answers the endpoint's `legacy-key?` from its `org` and `key` alone. MAWS's RL10 fixture still replays that exchange (map §3).
5. **Coverage holds.** Every behaviour in map §2.4 (items 1–18) has an RL10 test, on one machine with the other machines' events injected through `endpoint_standin`. The exception is the end-to-end delivery from one sminos to another, which crosses MAWS's relay and not sminos code; there the PR names the MAWS `e2e:remote` test that proves it. The PR body lists each item and its test.
6. **The counts match.** `sminos/tests/run-sminos-tests.sh` is green on both parts. The PR body gives the removed tests per file (map §2), and they match the removed code: nothing RL10 runs loses its only test.
7. **devcloud calls no `sminos hub` verb.** Its v1 `provisioning_secret` and `--enroll-code` are gone, its gates (`devcloud-unit`, `devcloud-host`, `devcloud-systemd`, `devcloud-mods`, `devcloud-image`) are green, and devcloud is bumped.
8. **Both Macs' daemons restart cleanly on the release.** After the merge, the MacBook's and the mini's sminos daemons are each running 1.40.0 with their uplink on RL10. The MacBook is checked by reading files (`daemon.log`, the launchd state), never through `machine.sock`; the mini through mini-ops.
9. **The gate gets faster.** `sminos-suites`' runtime on the merged head is recorded against today's (~20–22 min, runs 42329775929 and 42329436955), and the figure goes on board #170.

## The design

- **What goes** (map §1):
  - `sminos_uplink.py`'s HTTP/SSE transport (`Stream`, `Sender`, `dial`, `run_dx2`, `load_credential`) and `cmd_uplink`'s credential branch;
  - `sminos_daemon`'s DX2 supervision arm (`credential_bytes`, `LEFT_THE_HUB`, the `dx2` arms of `uplink_wanted` and `uplink_change`, `uplink_status`'s `hub.json` line);
  - every `coded` parameter and branch (`HubLog`, `Rpcs`, `Requests`, `outcomes.message`, `Link`, `Plane`);
  - the DX1 MAC half of `sminos_codes`;
  - `sminos_hub`'s enrollment code;
  - the stand-ins and benches that drive the hub over DX2 (`hub_standin.py`, `pause_proxy.py`, `bench_codes.py`, `bench_rig.py`'s DX2 parts, `bench_open --uplink`, `bench_scale` without `--rl10`, `measure_pages` part 2);
  - their tests.
- **What stays** (map §1, class (c)):
  - `Link`, `serve`, `SocketLane`, `SocketTransport`, `run_rl10`, `cmd_probe`, `Parts`/`to_wire`;
  - the session plane;
  - every `cut_over()` check that separates "has an endpoint" from "has no upstream";
  - `daemon probe`, which is how a new machine cuts over;
  - the owed state, `daemon owed`, the uplink-taken resume state;
  - `endpoint_standin.py` and `bench_scale.py --rl10`.
- **Why coverage moves first.** About 220 Python tests and 330 shell assertions prove shared or RL10 behaviour through DX2 fixtures or `hub_standin` (map §0.8). Deleting the transport first would keep the gate green while that coverage silently went. So M3 adds the RL10 tests beside the DX2 ones, and only M4 onward removes code.
- **How coverage moves: one machine, other machines' events injected.** `endpoint_standin`'s `arriving`, `echo`, `resend`, `refuse` and `send` stand in for every other machine (map §2.4). sminos's contract ends at the RL10 socket. A delivery from one sminos to another crosses MAWS's relay, which MAWS's `e2e:remote` drives across two machines.
  - Rejected: a two-machine RL10 relay stand-in in sminos's suite. That would be a few hundred lines that test MAWS's relay, not sminos.
- **`hub.json` is reduced, not removed** (map §3). MAWS's RL10 conversation fixture (case 2) still has the endpoint ask `legacy-key?`, and the conformance replay checks every line as written. Production never asks, since it reads `legacyRetired` (P5 Decision Log 239). The file's last reader goes once MAWS drops `legacy-key?` from RL10 and its fixture; that is a follow-up for O14 and O10's fixture.
  - Rejected: removing it now, which turns the replay red.
- **The `hub` verbs keep a pointer instead of being deleted.** Every production machine already answers `enroll`, `check` and `leave` that way. Making it unconditional changes nothing anyone runs, and it leaves someone who types the old command a way forward.
  - Rejected: deleting them, which turns the old command into a usage error with no hint.
- **The Resume, Retire and Stop RPCs and steer-without-a-bridge** (map §0.7) are already refused on RL10 as unfenced (`sminos_rpc.py:288`). MAWS O10 offers none of them until a child fences them. Collapsing `coded` leaves them unreachable. They are deleted with it (the architect's ruling, Decision Log). A fenced form would be built against RL10 and the bridge's launch fence, so it would not reuse this code; history keeps it.
- **The version is minor (1.40.0).** No running machine notices the change: every one is cut over, and the verbs that change already answer the pointer there.
  - Rejected: a major. The CLI verbs change only on machines that no longer exist.

## Execution

### Constraints that bind every milestone

- **Every commit is green, and coverage leaves only after its RL10 replacement is in.** Before any commit that deletes a stand-in or a transport, grep the tree for what it removes (`hub_standin`, `Stream(`, `Sender(`, `load_credential`, `run_dx2`, `coded`).
- **The RL10 path is untouched in behaviour.** The proof is acceptance 2's suites, green and unmodified at every milestone. A change to one of them is a design change, recorded in the Decision Log.
- **Tests never touch the real registry.** Every test runs with a temporary `HOME` and `SMINOS_HOME`. A working copy's CLI never runs against `~/.claude/sminos` or `~/.claude.json`.
- **Gates run on GitHub Actions through `ci-gate`:**
  - for sminos, `--gates sminos,sminos-suites,sminos-mods,mods-types,repo-checks`;
  - for devcloud, `--gates devcloud-unit,devcloud-host,devcloud-systemd,devcloud-mods,devcloud-image,repo-checks`.
  - Run gates in the background. One focused test file locally while iterating is fine.
- **Versions:** sminos's `tests/*` is unshipped (`.version-bump.json`), so M2 and M3 need no bump. The branch bumps sminos once, to 1.40.0, in M4's first shipping commit, and devcloud once in M1, both with `scripts/bump-version.sh`. `scripts/bump-version.sh --since origin/main` passes before each push.
- **Git:** merge `origin/main` when needed, never rebase. Commit by explicit paths. Every commit message ends with the session's `Sminos-Session:` line.
- **Scope:** leave the always-empty `refused` map and the no-op `hold`/`release` gates in place (map §5, step 4's risk). Collapsing them is a separate change.

### Plan of Work

#### M1 — devcloud's DX2 enrollment out

Remove the following (map §1.11 and §5 step 0): `sminos_host.enroll` with its `hub check` and `hub enroll` calls; `at_hub`'s `hub.json` leg; `departure._endpoint_leave`'s `hub leave` arm; `DEVCLOUD_SMINOS_SECRET`; `[desk] provisioning_secret` (v1); `--enroll-code` and `enroll-code`; and the README's v1 passage (around 505–535). A profile that still names v1 is refused with a line saying so. Bump devcloud.

**Proof:** devcloud's gates green; a test that a v1 profile is refused; devcloud's own fake sminos sees no `hub` verb on boot or departure.

#### M2 — The opt-in local-hub modes out (tests only)

Remove `LocalHub`, `make_hub`'s local arm and `DESK_HUB` from `test_session_plane`, `test_rpcs` and `test_policy_requests`. Remove `bench_rig.py`'s `Local` and `LocalBrowser`, and the `--hub local` and `--maws` flags of `bench_open` and `bench_scale` (map §2.3). CI never selects these modes.

**Proof:** both suite parts green with unchanged counts.

#### M3 — Shared coverage re-pointed at RL10 (tests only)

Work through map §5 step 2, area by area, one commit each:
- **The unit flips:** `test_rpcs` Checks onto `remote_mode()`; `test_policy_requests` Requests onto `Requests(None)`; the coded `HubLog`s in `test_owed`, `test_reach` Admitted, `test_scale` and `test_heads`; `test_session_plane` Lifecycle's three `Link` fakes onto `coded=False`.
- **The endpoint stand-in ports:**
  - `test_withheld` Dx2 and Restate;
  - the Uplink classes of `test_session_plane`, `test_rpcs` and `test_policy_requests`;
  - `test_visibility` Unlisting;
  - test-uplink's supervision cases, onto its RL10 block;
  - test-archive, on the stand-in's `archive` flag;
  - test-org's one-machine cases;
  - test-sync's former-name, leave, presence, spent and too-large cases;
  - the resolution and recording halves of test-address, test-broadcast, test-remote and test-join.

A new test sits beside the DX2 one it replaces, so M3 only adds tests. Where an RL10 test can't be written without changing a stand-in's contract, the change to `endpoint_standin.py` is part of the commit, and its own tests cover it.

Keep a checklist in the report file: map §2.4's items 1–18, each with its new test, or, for a two-machine end-to-end delivery, the MAWS `e2e:remote` test that proves it (find it in MAWS `origin/master`'s `test/e2e`).

**Proof:** both suite parts green; the checklist complete; acceptance 2's suites untouched.

#### M4 — The DX2 transport and the supervisor's DX2 arm out

The code and tests in map §5 step 3. Bump sminos to 1.40.0 in this milestone's first commit.

**Proof:** the step's grep is empty; both parts green; acceptance 2's suites untouched and green; a test that a machine with a `hub.json` and no `identity.json` gets `waiting` from the supervisor and starts no uplink.

#### M5 — `coded` collapsed

The code and tests in map §5 step 4:
- `HubLog`, `refusal`, `take`, `same`, `uploads`, `presence`, `on_refused`;
- `Rpcs`' key, `coded`, `RPC_NAMES` and `RL10_ONLY`;
- `Requests`' key, with `uncoded` becoming the restore path;
- `outcomes.message`;
- `Link`'s `coded` and `transport`;
- `Plane`'s `host`, `launches` and `kinds`, and `Rpcs.kinds`;
- `hublog.machine_policy` and `policy.machine_policy`;
- the DX1 MAC half of `sminos_codes`, with `codes_parity`'s MAC vectors.

The Resume, Retire and Stop RPCs, `launched_by` and `steer_without_bridge` go with their tests and `live-resume-check.py`.

**Proof:** acceptance 2's suites untouched and green. This is the milestone's whole claim: behaviour-neutral on RL10.

#### M6 — The `hub` verbs and `hub.json` reduced

The code and tests in map §5 step 5:
- `sminos_hub` cut to `show` (identity.json only), `enrolled_hub`, `add_hub`, `credential_lock`, `sessions_under`, and the pointer for `enroll`, `check` and `leave`;
- `sminos.enrollment`, `enrolment_stamp`, `machine_identity`, `sminos_daemon.enrolled_at` and `enrollment_inspected` reading `identity.json` alone;
- `hooks/smns-guide.sh` and `smns-record.sh` testing `identity.json` alone;
- `on_legacy_key` reading `hub.json`'s `org` and `key` alone.

Every fixture that wrote `hub.json` to name or enroll a machine instead writes `identity.json` through one shared helper, or sets `DAEMON_HOST` (map §2.5). Where delivery is asserted, it uses the endpoint stand-in or a kept `audiences.json`.

The delicate part is `rl10_conformance.stage_machine`. Its staged writers must still come out as `rl10-host`, and it must still answer `legacy-key`. Run the replay and `test_words` first.

**Proof:** acceptance 3 and 4 each have a test, including the hooks with a stray `hub.json`; the replay's ok count unchanged with 0 FAIL; both parts green.

#### M7 — Docs, labels and the bump

- The `run_suites` labels.
- `sminos/skills/sminos/scripts/CLAUDE.md`, `references/setup.md` (its "The desk hub" section), `SKILL.md`, about twelve module docstrings and the usage text (map §6).
- The repository docs that name `hub enroll`: README, `docs/whats-inside.md`, `INSTALL-doperpowers.md` and `TECH-DEBT.md`.

The `SKILL.md` edit gets a sanity read through `doperpowers:writing-skills`, since the description drives triggering. Fix `sminos_plane.py`'s `AGENT_ID.match` to `fullmatch` at the `subscribe` check (`:2873` at `904b0a35`), where `$` admits a trailing newline. Reword #149's residue from "DX2's lane" to "the RL10 lane".

**Proof:** a grep of the docs for `hub enroll`, `DX2`, `provisioning_secret` and `hub.json` finds only historical or pointer mentions; a test for the trailing-newline `agentId`.

### Concrete Steps

    W=/Users/new/.local/share/p5-desk-track-owner/wt/dp-153-phase1
    CG=/Users/new/.claude/plugins/cache/doperpowers/ci-kit/9d50b3af02d9/bin/ci-gate
    $CG $W --gates sminos,sminos-suites,sminos-mods,mods-types,repo-checks     # expected: GREEN <run-url>
    $CG $W --gates devcloud-unit,devcloud-host,devcloud-systemd,devcloud-mods,devcloud-image,repo-checks   # M1
    bash $W/scripts/bump-version.sh --since origin/main                         # before each push
    # one suite locally while iterating, under a temporary HOME and SMINOS_HOME:
    HOME=$(mktemp -d) SMINOS_HOME=$(mktemp -d) python3 -B $W/sminos/tests/test_<x>.py

### Interfaces and Dependencies

- **MAWS's RL10 conversation fixture** (`test/endpoint/rl10/conversation.json`; sminos's copy is `sminos/tests/rl10-conversation.json`) is the contract. This change modifies no RL10 frame. A failing replay means the change was wrong, never the fixture.
- **`endpoint_standin.py`** is the one-machine RL10 test peer. M3 may extend it, without changing what existing tests see.
- **devcloud** consumes `sminos hub` only through M1's paths. After M1, nothing outside sminos calls a `hub` verb except a person.
- **MAWS's** `apps/desk-hub/deploy/README.md:173` still says `sminos hub enroll`. That is MAWS's to fix (the architect is told).

## Surprises & Discoveries

- Observation (map): the DX4 session plane did not end with DX2. RL10 carries it, so the ticket's "no path serves DX4" now reads "nothing is served over the hub's DX2 stream".
  Evidence: MAWS `src/endpoint/plane-a.ts`; P5 Decision Log 241.
- Observation (map): P5 Decision Log 231's "enrolled means `hub.json`" was never what the code did. Decision Log 235 reworded it as "not cut over", and 1.39.0's `widening_through_app` keys on `rl10.cut_over()` and the kept `record`.
  Evidence: `sminos_audience.py:174` at `904b0a35`.
- Observation (map): board #149's bound (a lane closes past 16 MiB unsent) applies to RL10 unchanged. Only the DX2 half of its test goes.
  Evidence: `SEND_QUEUE_MAX`; RL10 splits frames over 1 MiB into parts.

## Decision Log

- Decision (verification, at authoring): the design and the execution section each get one `doperpowers:adversarial-reviewer` pass before execution. The branch gets the xhigh panel through `doperpowers:review-code`: the diff runs to thousands of lines across many files, and most of the risk is coverage silently lost rather than a defect in what is added. Acceptance 8's daemon check closes it.
  Date/Author: 2026-11-07, p5-desk-track-owner.
- Decision (scope, on the map's first open call): cross-machine coverage stays on one machine with injected arrivals, and a two-machine delivery is left to MAWS's `e2e:remote`.
  Rationale: sminos's contract ends at the RL10 socket; the delivery between machines is MAWS's relay, which `e2e:remote` drives.
  Rejected: a two-machine RL10 relay stand-in in sminos's suite.
  Date/Author: 2026-11-07, p5-desk-track-owner.
- Decision (the architect's ruling, sminos chat 1207, on the map's second open call): the Resume, Retire and Stop RPCs and steer without a bridge are deleted with `coded`. No P5 child plans a fenced form: P5 Decision Log 51 deferred it with no owner and no child, O12 refuses all three remotely as unsupported and a remote steer without a bridge as `context`, and O9 lists them among its remote gaps.
  Rationale: a fenced form would be built against RL10 and the bridge's launch fence, so the unfenced code would not be reused.
  Rejected: keeping them as unreachable code.
  Date/Author: 2026-11-07, the architect (chat 1207).

## Outcomes & Retrospective

(At completion.)
