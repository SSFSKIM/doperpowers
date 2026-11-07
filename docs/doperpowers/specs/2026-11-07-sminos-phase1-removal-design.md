# sminos: the phase-1 hub path removed (board #153)

Since P5's cutover finished (O14 B4, 2026-11-07), every enrolled machine runs RL1 to MAWS's relay and RL10 to its own endpoint (`mawsd`). The desk hub refuses DX2 enrollment, and no machine holds a `hub.json` any more (P5 Decision Logs 239 and 242). sminos still carries the machine side of phase 1: the hub's HTTP/SSE uplink, the DX1 request codes, the `coded` branches that serve them, and the `sminos hub enroll` machinery. Nothing can reach that code now. Its tests are about a third of the `sminos-suites` gate's ~20 minutes (board #170), and they also prove a good deal of shared behaviour only through DX2.

This change leaves sminos with one hub protocol on the machine side. Its tests prove only what runs: every shared behaviour that is now proven only through DX2 is proven again on RL10 before the DX2 code leaves.

The detailed map this spec was written from, every module, function and test by file:line and class, is [the removal map](2026-11-07-sminos-phase1-removal-map.md), read at doperpowers `904b0a35` (sminos 1.39.0). Its section numbers are cited as "map §N".

## Progress

- [x] (2026-11-07) The map (read-only, doperpowers `904b0a35`, MAWS `1a11fedf6`).
- [x] (2026-11-07) This spec.
- [x] (2026-11-07) The spec's review: adversarial-reviewer on the design and on the execution section, one round each. Every finding was folded in (Decision Log, 2026-11-07, the review).
- [x] (2026-11-07) M1: devcloud's DX2 enrollment out (devcloud 0.16.0, `1585356b`; review clean, devcloud gates GREEN, run 42338569325).
- [x] (2026-11-07) M2: the opt-in local-hub modes out (tests only; `0e2a69d6`; review clean, sminos gates GREEN, run 42339386393).
- [ ] M3a: the unit flips (tests only).
- [ ] M3b: the endpoint stand-in ports, the session plane and the RPCs (tests only).
- [ ] M3c: the shell suites' one-machine cases (tests only).
- [ ] M3d: the two-machine compositions (tests only).
- [ ] M3e: open latency on RL10 (tests only).
- [ ] M4: the `hub` verbs and `hub.json` reduced (the sminos 1.40.0 bump).
- [ ] M5: the DX2 transport and the supervisor's DX2 arm out.
- [ ] M6: `coded` collapsed.
- [ ] M7: docs and labels.
- [ ] The branch review and the merge.
- [ ] M8: the release verified (both Macs' daemons, the gate's runtime).

## What changes and what doesn't (acceptance)

1. **No sminos code path speaks DX2.** Shipped sminos has no HTTP/SSE uplink to the hub, no DX1 request codes, no `coded=True` branch, and nothing that enrolls a machine at the hub or reads `hub.json` as a credential. A grep of `sminos/skills/` and `sminos/hooks/` for `run_dx2`, `load_credential`, `Stream(`, `Sender(`, `hub_standin` and `coded=True` finds nothing.
2. **The RL10 path behaves exactly as before.** Two things stay fixed. First, MAWS's RL10 conversation frames: `sminos/tests/rl10-conversation.json` is byte-for-byte unchanged, and the conformance replay (`rl10_conformance.py`) keeps today's ok count with 0 FAIL. Second, the behavioural assertions of `test_rl10`, `test_words`, `test_reach_gate`, `test_visibility` and `test_streams`: none is removed or weakened. Those suites may change only by the mechanical migrations the constraints list, and each such change is named in the PR. The session plane DX4 defined is still served over RL10 (MAWS's `src/endpoint/plane-a.ts` subscribes to it): `sminos_plane.py` and `Link`'s session-lane dispatch stay (map §0.1).
3. **`sminos hub`:**
   - `hub enroll`, `hub check` and `hub leave` print the line a cut-over machine prints today: this machine's enrollment is its endpoint's (`mawsd endpoint enroll|status`). They exit 1.
   - `hub show` reads `daemon/identity.json`. It prints the machine's name, hub and org. On a machine not cut over, it says the enrollment is the endpoint's and that sminos takes it at the endpoint's first welcome, and it exits 1.
4. **Enrolled means cut over.** A machine with no `identity.json` runs no uplink (the supervisor's `waiting`), keeps the terminal gate for widening (O18 D10, P5 Decision Logs 231 and 235), and is hubless to the hooks. A stray `hub.json` makes nothing count as enrolled. Its one remaining reader is `Link.on_legacy_key`, which answers the endpoint's `legacy-key?` from its `org` and `key` alone. MAWS's RL10 fixture still replays that exchange (map §3).
5. **Coverage holds.** Every behaviour in map §2.4 (items 1–18) has an RL10 test that drives real sminos code on both sides it touches.
   - A behaviour of one machine runs on one sminos, with the other machines' events injected through `endpoint_standin`.
   - A behaviour between machines (items 3 and 8–10: two-machine sync, cross-machine addressing and broadcast, repository-by-remote, join and move) runs as a composition. A real producer sminos runs against one stand-in, and the frames that stand-in accepted reach a second real sminos home's stand-in as arrivals, by the stand-in's own echo transform, never written by hand. The consumer's result is asserted. No MAWS suite is counted, because MAWS's `e2e:remote` runs a fake sminos.
   - Open latency (item 12) runs on RL10 through the real uplink child.
   - The PR body lists each item and its test.
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
- **How coverage moves: one machine with other machines' events injected, and compositions for what spans machines.** `endpoint_standin`'s `arriving`, `echo`, `resend`, `refuse` and `send` stand in for every other machine (map §2.4).
  - For a behaviour between machines, one test runs two real sminos homes in sequence. The producer's accepted frames become the consumer's arrivals through the stand-in's own transform. This proves sminos's publication and its import, resolution and delivery against each other.
  - What it leaves to MAWS is the relay between the endpoints, which is MAWS's code.
  - Rejected: a live two-machine relay stand-in. It is a few hundred lines whose extra reach is MAWS's relay, not sminos.
  - Rejected: counting MAWS's `e2e:remote`. Its scene runs a fake sminos (`e2e/support/fake-sminos.ts`), so it proves MAWS's side alone.
- **`hub.json` is reduced, not removed** (map §3). MAWS's RL10 conversation fixture (case 2) still has the endpoint ask `legacy-key?`, and the conformance replay checks every line as written. Production never asks, since it reads `legacyRetired` (P5 Decision Log 239). The file's last reader goes once MAWS drops `legacy-key?` from RL10 and its fixture; that is a follow-up for O14 and O10's fixture.
  - Rejected: removing it now, which turns the replay red.
- **The `hub` verbs keep a pointer instead of being deleted.** Every production machine already answers `enroll`, `check` and `leave` that way. Making it unconditional changes nothing anyone runs, and it leaves someone who types the old command a way forward.
  - Rejected: deleting them, which turns the old command into a usage error with no hint.
- **The Resume, Retire and Stop RPCs and steer-without-a-bridge** (map §0.7) are already refused on RL10 as unfenced (`sminos_rpc.py:288`). MAWS O10 offers none of them until a child fences them. Collapsing `coded` leaves their admission and execution unreachable, and those are deleted with it (the architect's ruling, Decision Log). A fenced form would be built against RL10 and the bridge's launch fence, so it would not reuse this code; history keeps it.
  - **What stays: the recovery of a persisted claim.** `Rpcs.__init__` reconciles the ledger on every start, whatever `coded` is. An unfinished Resume claim from before the cutover reaches `launched_by` through `reconcile` and `trace` (`sminos_rpc.py:783`, `:1600`, `:2738` at `904b0a35`). That recovery, and any copy cleanup it does, keeps its outcome. It is tested on RL10 with an unfinished claim of each removed kind.
  - Deleting the recovery waits on a follow-up: both Macs' ledgers checked free of such claims, and a load-time settlement for any that remain.
- **The version is minor (1.40.0).** No running machine notices the change: every one is cut over, and the verbs that change already answer the pointer there.
  - Rejected: a major. The CLI verbs change only on machines that no longer exist.

## Execution

### Constraints that bind every milestone

- **Every commit is green, and coverage leaves only after its RL10 replacement is in.** A milestone that deletes code first greps the tree for every caller of what it deletes, tests and benches included (`hub_standin`, `Stream(`, `Sender(`, `load_credential`, `credential_path`, `run_dx2`, `coded`). It moves or removes each caller in the same commit or earlier.
- **The RL10 path is untouched in behaviour** (acceptance 2). These are the only allowed changes to its suites, and each is named in the PR:
  - a constructor argument that no longer exists is dropped (`coded=False` on `Link`, `HubLog`, `Rpcs`, `Requests`);
  - a fixture that wrote `hub.json` to name or enroll a machine writes `identity.json` through one shared helper, or sets `DAEMON_HOST`;
  - a test of a historical persisted format keeps its data and loses only the DX2 machinery that built it;
  - an assertion whose subject is a DX2-only behaviour goes with that behaviour. There are two known ones: `test_rl10.py:1064–1065`, where DX2's restoration keeps a sealed outbox unchanged, and `test_visibility.py:1178–1180`, the `RL10_ONLY` set and DX2's RPC-name exclusion. Both files' neighbouring RL10 assertions stay: the sealed outbox restored as an RL10 draft, and the launch-independent `context_refusal` at `test_visibility.py:1181–1182`. Any other assertion that goes is named in the PR, with the DX2 behaviour that is its subject.

  An assertion about RL10 is never removed or loosened to make a migration pass. Anything beyond these changes is a design change, recorded in the Decision Log.
- **Tests never touch the real registry.** Every test runs with a temporary `HOME` and `SMINOS_HOME`. A working copy's CLI never runs against `~/.claude/sminos` or `~/.claude.json`.
- **Gates run on GitHub Actions through `ci-gate`:**
  - for sminos, `--gates sminos,sminos-suites,sminos-mods,mods-types,repo-checks,version-bump`;
  - for devcloud (M1), `--gates devcloud-unit,devcloud-host,devcloud-systemd,devcloud-mods,devcloud-image,repo-checks,version-bump`.
  - Run gates in the background. One focused test file locally while iterating is fine.
- **Versions:** sminos's `tests/*` is unshipped (`.version-bump.json`), so M2 and M3 need no bump. The branch bumps sminos once, to 1.40.0, in M4's first shipping commit, and devcloud once in M1, both with `scripts/bump-version.sh`. `scripts/bump-version.sh --since origin/main` passes before each push.
- **Git:** merge `origin/main` when needed, never rebase. Commit by explicit paths. Every commit message ends with the session's `Sminos-Session:` line.
- **Scope:** leave the always-empty `refused` map and the no-op `hold`/`release` gates in place (map §5, step 4's risk). Collapsing them is a separate change.

### Plan of Work

#### M1 — devcloud's DX2 enrollment out

Remove the following (map §1.11 and §5 step 0): `sminos_host.enroll` with its `hub check` and `hub enroll` calls; `at_hub`'s `hub.json` leg; `departure._endpoint_leave`'s `hub leave` arm; `DEVCLOUD_SMINOS_SECRET`; `[desk] provisioning_secret` (v1); `--enroll-code` and `enroll-code`; and the README's v1 passage (around 505–535). A profile that still names v1 is refused with a line saying so. Bump devcloud.

**Proof:** devcloud's gates are green; a test refuses a v1 profile; devcloud's own fake sminos sees no `hub` verb on boot or departure.

#### M2 — The opt-in local-hub modes out (tests only)

Remove `LocalHub`, `make_hub`'s local arm and `DESK_HUB` from `test_session_plane`, `test_rpcs` and `test_policy_requests`. Remove `bench_rig.py`'s `Local` and `LocalBrowser`, and the `--hub local` and `--maws` flags of `bench_open` and `bench_scale` (map §2.3). CI never selects these modes.

**Proof:** both suite parts are green, with counts unchanged.

#### M3 — Shared coverage re-pointed at RL10 (tests only, five batches)

Each batch adds RL10 tests beside the DX2 ones they replace, so every batch only adds. A batch may extend `endpoint_standin.py`, without changing what its existing tests see; the extension is covered by its own tests. The report file keeps one checklist: map §2.4's items 1–18, each against the test that now covers it on RL10.

- **M3a, the unit flips:**
  - `test_rpcs` Checks onto `remote_mode()`;
  - `test_policy_requests` Requests onto `Requests(None)`;
  - the coded `HubLog`s in `test_owed`, `test_reach` Admitted, `test_scale` and `test_heads`;
  - `test_session_plane` Lifecycle's three `Link` fakes onto `coded=False`.
  - **Proof:** each flipped test passes uncoded beside its coded twin.
- **M3b, the endpoint stand-in ports:**
  - `test_withheld` Dx2 and Restate;
  - the Uplink classes of `test_session_plane`, `test_rpcs` and `test_policy_requests`;
  - `test_visibility` Unlisting;
  - and, from `test_rpcs`, the recovery of an unfinished persisted claim of each kind M6 removes (Resume, Retire, Stop) under `coded=False`, with its outcome and copy cleanup. This is the recovery that stays (the design).
  - **Proof:** map §2.4 items 13–18 checked.
- **M3c, the shell suites' one-machine cases:**
  - test-uplink's supervision cases, onto its RL10 block;
  - test-archive, on the stand-in's `archive` flag;
  - test-org's one-machine cases;
  - test-sync's former-name, leave, presence, spent and too-large cases.
  - **Proof:** items 1, 2, 4–7 and 11 checked.
- **M3d, the two-machine compositions:**
  - Two-machine sync (bootstrap, members and states, says, titles, restart resync: test-sync, including the messages reaching both sessions at `test-sync.sh:444` and the titles derived from the publishing machine's events at `:485`).
  - Cross-machine addressing and scoped broadcast (test-address, test-broadcast).
  - Repository-by-remote (test-remote).
  - join and move reaching another machine (test-join).

  Each runs as the design's composition. A real producer sminos runs against its stand-in. The frames the stand-in accepted reach a second real sminos home's stand-in as arrivals through the stand-in's echo transform, and the consumer's result is asserted, whether delivered, resolved or recorded.
  - **Proof:** items 3 and 8–10 checked, both halves asserted in each test.
- **M3e, open latency on RL10:**
  - The bench-open integration assertions move onto the RL10 session lane through the real uplink child and `endpoint_standin`: complete snapshots with no holes or duplicates, and a snapshot placed correctly during a message (`test_session_plane.py:3339` at `904b0a35`).
  - So does `test_scale`'s `BenchOpens`: cold, warm and post-restart opens, with saved builds reused (`:1032`).
  - `bench_open` and `bench_scale opens` gain an `--rl10` mode that does the same, so the measurement survives M5's removal of `--uplink`.
  - **Proof:** item 12 checked. The RL10 `BenchOpens` passes, and `bench_open --rl10` prints its cold, warm and restarted open times.

#### M4 — The `hub` verbs and `hub.json` reduced

This is the code and tests of map §5 step 5. It comes before the transport's removal, because `sminos_hub` and `test-hub.sh` use the transport's helpers and `hub_standin`. Bump sminos to 1.40.0 in this milestone's first commit.
- `sminos_hub` is cut to `show` (identity.json only), `enrolled_hub`, `add_hub`, `credential_lock`, `sessions_under`, and the pointer for `enroll`, `check` and `leave`. Its calls to the transport's helpers go with the enrollment code.
- `sminos.enrollment`, `enrolment_stamp`, `machine_identity`, `sminos_daemon.enrolled_at` and `enrollment_inspected` read `identity.json` alone. `hooks/smns-guide.sh` and `smns-record.sh` test `identity.json` alone.
- `on_legacy_key` reads `hub.json`'s `org` and `key` through a small path helper of its own, so that it no longer depends on `credential_path`, which M5 removes.
- test-hub's enrollment assertions, `enroll_parity.py` and `dx7-enroll-codes.*` go. In their place are the tests for acceptance 3 and 4: the pointer, `show`, and the hooks with a stray `hub.json`.
- **The DX2 integration cases whose machines enroll at the hub go here too, not in M5.** They can't take the `identity.json` fixture, because `cmd_uplink` then selects RL10 instead of their hub stand-in (`sminos_uplink.py:3219–3223`), and `DAEMON_HOST` doesn't replace an enrollment. They include test-sync's DX2 cases (`hub enroll` at `test-sync.sh:248`), the other shell suites' DX2 blocks that enroll, `test_happy_eyeballs.py` (it calls `hub.redeem_once` and `hub.TIMEOUT`, `:133–139`), and the benches that enroll. Each goes only after its M3 replacement is checked. Before committing, grep the tests and benches for `hub enroll`, `redeem_once`, `hub.TIMEOUT` and `enroll_with`. M5 is left with what tests the transport alone.
- Every fixture that wrote `hub.json` to name or enroll a machine writes `identity.json` through one shared helper, or sets `DAEMON_HOST` (map §2.5). Where delivery is asserted, it uses the endpoint stand-in or a kept `audiences.json`.
- **`rl10_conformance.stage_machine`** sets `DAEMON_HOST=rl10-host` before it creates any project or writer, so the staged writers come out as `rl10-host`. It keeps the `hub.json` that `legacy-key` answers from. It leaves `identity.json` absent until the replay's welcome, the transition `rl10_conformance.py:610–619` checks. Run the replay and `test_words` first.

**Proof:**
- The replay keeps today's ok count with 0 FAIL.
- Acceptance 3 and 4 each have a test; acceptance 4's supervisor clause belongs to M5.
- Both parts are green.

#### M5 — The DX2 transport and the supervisor's DX2 arm out

This is map §5 step 3:
- `sminos_uplink.py`'s (a) list (map §1.1), with `credential_path`;
- `cmd_uplink`'s credential branch;
- `sminos_daemon`'s `credential_bytes`, `LEFT_THE_HUB`, the `dx2` arms of `uplink_wanted` and `uplink_change`, and `uplink_status`'s `hub.json` line;
- the DX2 tests the step lists that M4 hasn't already retired: those of the transport alone;
- `hub_standin.py`, `pause_proxy.py`, `bench_codes.py`, `bench_rig.py`'s DX2 parts, `bench_open --uplink`/`held`, `bench_scale run` without `--rl10`, `bench_scale opens` without `--rl10`, and `measure_pages` part 2.

Each DX2 test goes only after its M3 replacement is checked.

**Proof:**
- The constraint's grep is empty.
- A test shows that a machine with a `hub.json` and no `identity.json` gets `waiting` from the supervisor and starts no uplink.
- Acceptance 2 holds.
- Both parts are green.

#### M6 — `coded` collapsed

This is map §5 step 4:
- `HubLog`, `refusal`, `take`, `same`, `uploads`, `presence`, `on_refused`;
- `Rpcs`' key, `coded`, `RPC_NAMES` and `RL10_ONLY`;
- `Requests`' key, with `uncoded` becoming the restore path;
- `outcomes.message`;
- `Link`'s `coded` and `transport`;
- `Plane`'s `host`, `launches` and `kinds`, and `Rpcs.kinds`;
- `hublog.machine_policy` and `policy.machine_policy`;
- the DX1 MAC half of `sminos_codes`, with `codes_parity`'s MAC vectors.

The admission and execution of Resume, Retire and Stop go, with steer without a bridge, their tests and `live-resume-check.py`. Before any function goes, list its callers, the ledger's `reconcile` and `trace` paths included. The recovery of a persisted claim stays, `launched_by` with it, under M3b's tests.

Acceptance 2's suites change only by the listed migration: the dropped `coded=False` argument (`test_rl10.py:1112`, `rl10_conformance.py:454`, `test_words.py:233`). Their old sealed-outbox test (`test_rl10.py:1051–1070`) keeps its persisted data and its RL10-draft assertion. It loses the DX2 request builder and the DX2 restoration's assertion (`:1064–1065`), and `test_visibility.py:1178–1180` goes with `RL10_ONLY`, as the constraints list.

**Proof:** acceptance 2 holds, which is the milestone's whole claim (behaviour-neutral on RL10); M3b's recovery tests are green; both parts are green.

#### M7 — Docs and labels

- The `run_suites` labels.
- `sminos/skills/sminos/scripts/CLAUDE.md`, `references/setup.md` (its "The desk hub" section), `SKILL.md`, about twelve module docstrings and the usage text (map §6).
- The repository docs that name `hub enroll`: README, `docs/whats-inside.md`, `INSTALL-doperpowers.md` and `TECH-DEBT.md`.

The `SKILL.md` edit gets a sanity read through `doperpowers:writing-skills`, since the description drives triggering. Fix `sminos_plane.py`'s `AGENT_ID.match` to `fullmatch` at the `subscribe` check (`:2873` at `904b0a35`), where `$` admits a trailing newline. Reword #149's residue from "DX2's lane" to "the RL10 lane".

**Proof:** a grep of the docs for `hub enroll`, `DX2`, `provisioning_secret` and `hub.json` finds only historical or pointer mentions; a test covers the trailing-newline `agentId`.

#### M8 — The release verified (after the merge; the coordinating session's)

This is after the branch review and the merge, and it is not part of the branch's completion.
- Each Mac's sminos daemon runs 1.40.0 with its uplink on RL10. On the MacBook that is read from files (`daemon.log`'s restart line, the launchd agent's state, `daemon/uplink.json`), never through `machine.sock`; the mini through mini-ops.
- `sminos-suites`' runtime on the merged head is recorded against today's (runs 42329775929 and 42329436955, ~20–22 min), and the figure goes on board #170.
- Board #153 is closed with both.

**Proof:** acceptance 8 and 9's evidence lines, in Outcomes.

### Concrete Steps

    W=/Users/new/.local/share/p5-desk-track-owner/wt/dp-153-phase1
    CG=/Users/new/.claude/plugins/cache/doperpowers/ci-kit/9d50b3af02d9/bin/ci-gate
    $CG $W --gates sminos,sminos-suites,sminos-mods,mods-types,repo-checks,version-bump     # expected: GREEN <run-url>
    $CG $W --gates devcloud-unit,devcloud-host,devcloud-systemd,devcloud-mods,devcloud-image,repo-checks,version-bump   # M1
    bash $W/scripts/bump-version.sh --since origin/main                         # before each push
    # one suite locally while iterating, under a temporary HOME and SMINOS_HOME:
    HOME=$(mktemp -d) SMINOS_HOME=$(mktemp -d) python3 -B $W/sminos/tests/test_<x>.py

### Interfaces and Dependencies

- **MAWS's RL10 conversation fixture** (`test/endpoint/rl10/conversation.json`; sminos's copy is `sminos/tests/rl10-conversation.json`) is the contract. This change modifies no RL10 frame. A failing replay means the change was wrong, never the fixture.
- **`endpoint_standin.py`** is the one-machine RL10 test peer. M3 may extend it, without changing what existing tests see.
- **devcloud** consumes `sminos hub` only through M1's paths. After M1, nothing outside sminos calls a `hub` verb except a person.
- **MAWS's** `apps/desk-hub/deploy/README.md:173` still says `sminos hub enroll`. The architect is fixing it, along with the rest of its "After the first deploy" section (chat 1207).

## Surprises & Discoveries

- Observation (map): the DX4 session plane did not end with DX2. RL10 carries it, so the ticket's "no path serves DX4" now reads "nothing is served over the hub's DX2 stream".
  Evidence: MAWS `src/endpoint/plane-a.ts`; P5 Decision Log 241.
- Observation (map): P5 Decision Log 231's "enrolled means `hub.json`" was never what the code did. Decision Log 235 reworded it as "not cut over", and 1.39.0's `widening_through_app` keys on `rl10.cut_over()` and the kept `record`.
  Evidence: `sminos_audience.py:174` at `904b0a35`.
- Observation (map): board #149's bound (a lane closes past 16 MiB unsent) applies to RL10 unchanged. Only the DX2 half of its test goes.
  Evidence: `SEND_QUEUE_MAX`; RL10 splits frames over 1 MiB into parts.

- Observation (the review): MAWS's `e2e:remote` runs a fake sminos that builds its own presence, member and session-plane frames, so it proves MAWS's side alone. No existing suite composes two real sminos homes over RL10.
  Evidence: MAWS `e2e/support/remote-scene.ts:233`; `e2e/support/fake-sminos.ts`.
- Observation (the review): refusing Resume on RL10 does not make its recovery unreachable. `Rpcs.__init__` reconciles the ledger whatever `coded` is, and an unfinished pre-cutover Resume claim reaches `launched_by`. A reviewer ran the extracted functions with `coded=False`: they reconciled, and with the helper deleted they raised `NameError`.
  Evidence: `sminos_rpc.py:783`, `:1600`, `:2738` at `904b0a35`.

- Observation (M2): `bench_scale.py` never had the `--hub local` or `--maws` flags the spec and map §5 step 1 name; it needed no change in M2.
  Evidence: `bench_scale.py`'s parsers at `0e2a69d6`.

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

- Decision (the spec's review, 2026-11-07: adversarial-reviewer on the design and on the execution section, one round each; every finding folded in):
  - The hub reduction now comes before the transport's removal (new M4 before M5). `sminos_hub` and `test-hub.sh` use the transport's helpers and `hub_standin`, and `on_legacy_key` uses `credential_path`, so removing the transport first breaks the green-commit rule.
  - Acceptance 2's suites are fixed in their assertions and MAWS's frames, not in their bytes. Removing `coded` and the `hub.json` fixtures has to touch `test_rl10`, `test_words` and the conformance staging, so the constraints list the allowed mechanical migrations.
  - The two-machine behaviours get real-sminos compositions (M3d) instead of MAWS's `e2e:remote`, which runs a fake sminos.
  - Open latency (map §2.4 item 12) gets an RL10 replacement (M3e) before its instruments go.
  - The recovery of persisted Resume, Retire and Stop claims stays and is tested on RL10.
  - M3 is split into five batches, each with its own proof.
  - The release's evidence is a milestone of its own (M8).
  - From the execution reviewer's re-check: the DX2 integration cases that enroll go in M4, with the enrollment, not in M5. The DX2-only assertions inside acceptance 2's suites that may go are listed by file and line.
  Date/Author: 2026-11-07, p5-desk-track-owner, on the two reviews.

- Decision (M1, the executor; devcloud 0.16.0):
  - A boot descriptor that still names `DEVCLOUD_SMINOS_SECRET` is refused by name, as a profile's `[desk] provisioning_secret` is. No live host is expected to carry it: the owner's `driver.toml` names only the v2 code.
  - The step-11 enrollment deferral goes whole. A boot clears a leftover `enroll` record, and `devcloud enroll` finishes only step 13's provisioning.
  - The `devcloud-enroll=code` label value is still accepted and worded by the reaper, because `set-labels` re-checks an existing VM's whole label set; the driver no longer writes it.
  - `hub.json` stays in the sandbox identity check (harmless, map §1.11). `LEAVE_TIMEOUT` stays 180 s; it already bounds the endpoint's retirement.
  - The departure tests run on a cut-over VM whose endpoint holds a certificate; `test_the_desk_not_answering_the_leave_goes_on` (DX2 only) goes.
  - TECH-DEBT's desk-key expiry (2027-01-19) is deleted as the v1 key's. Whether the v2 code expires was not checked.
  Date/Author: 2026-11-07, plan-executor (M1).

- Decision (M2, the executor):
  - `bench_open --scenario held` is refused before any rig is built, and stays in the tree until M5. It only ever ran on the local hub (its uploader used `Local.mint`), and deleting it now would take `test_session_plane`'s two analyser tests (`probe_blocked`, `machine_vector`) with it.
  - `make_hub` goes: the three Uplink classes call `StandinHub` directly. `Hub`, `StandinHub` and `call` stay until M5.
  - `ws_client.py` goes with `LocalHub` and `LocalBrowser`, its only users.
  Date/Author: 2026-11-07, plan-executor (M2).

## Outcomes & Retrospective

(At completion.)
