# sminos: the phase-1 hub path removed (board #153)

Since P5's cutover finished (O14 B4, 2026-11-07), every enrolled machine runs RL1 to MAWS's relay and RL10 to its own endpoint (`mawsd`). The desk hub refuses DX2 enrollment, and no machine holds a `hub.json` any more (P5 Decision Logs 239 and 242). sminos still carries the machine side of phase 1: the hub's HTTP/SSE uplink, the DX1 request codes, the `coded` branches that serve them, and the `sminos hub enroll` machinery. Nothing can reach that code now. Its tests are about a third of the `sminos-suites` gate's ~20 minutes (board #170), and they also prove a good deal of shared behaviour only through DX2.

This change leaves sminos with one hub protocol on the machine side. Its tests prove only what runs: every shared behaviour that is now proven only through DX2 is proven again on RL10 before the DX2 code leaves.

The detailed map this spec was written from, every module, function and test by file:line and class, is [the removal map](2026-11-07-sminos-phase1-removal-map.md), read at doperpowers `904b0a35` (sminos 1.39.0). Its section numbers are cited as "map §N".

## Progress

- [x] (2026-11-07) The map (read-only, doperpowers `904b0a35`, MAWS `1a11fedf6`).
- [x] (2026-11-07) This spec.
- [x] (2026-11-07) The spec's review: adversarial-reviewer on the design and on the execution section, one round each. Every finding was folded in (Decision Log, 2026-11-07, the review).
- [x] (2026-11-07) M1: devcloud's DX2 enrollment out (devcloud 0.16.0, `1585356b`; review clean, devcloud gates GREEN, run 42338569325). The coordinator's correction (the host tolerates the v1 key) landed as `82c4aea9`, reviewed clean, GREEN, run 42345027485.
- [x] (2026-11-07) M2: the opt-in local-hub modes out (tests only; `0e2a69d6`; review clean, sminos gates GREEN, run 42339386393).
- [x] (2026-11-07) M3a: the unit flips (tests only; `c9b0240d`, `673a7851`; review clean, sminos gates GREEN, run 42343036908).
- [x] (2026-11-07) M3b: the endpoint stand-in ports, the session plane and the RPCs (tests only; `1ee32911..84417b8e`, fix `71ac14b0`; review clean, sminos gates GREEN on `84417b8e`, run 42344457872).
- [x] (2026-11-07) M3c: the shell suites' one-machine cases (tests only; `a192e1dc..6d4817ef`, fixes `f4112d95`, `43a448db`, `e433dec0`; review clean, sminos gates GREEN on `e433dec0`, run 42354783123).
- [x] (2026-11-07) M3d: the two-machine compositions (tests only; `65e8870c..95c94a7f`, fixes `289ca204`, `6e4397ff`, `e7121bd0`; review clean, sminos gates GREEN on `e7121bd0`, run 42354037484).
- [x] (2026-11-07) M3e: open latency on RL10 (tests only; `a021ef36`, fix `9b402981`; review clean, sminos gates GREEN on `e433dec0`, run 42354783123). Every map §2.4 item has its RL10 test; the checklist is in the PR body.
- [x] (2026-11-07) M4: the `hub` verbs and `hub.json` reduced (the sminos 1.40.0 bump; `d2a87149`, `a76f947e`; review clean, sminos gates GREEN on `a76f947e`, run 42358177740; replay 107 ok, 0 FAIL). origin/main merged at `8d5efdfd`.
- [x] (2026-11-07) M5: the DX2 transport and the supervisor's DX2 arm out (`34538211`; review clean, sminos gates GREEN, run 42365283498; replay 107 ok, 0 FAIL).
- [x] (2026-11-07) M6: `coded` collapsed (`e9afa4e8`, fix `f9bd7b49`; review clean, sminos gates GREEN on `f9bd7b49`, run 42377347462; replay 107 ok, 0 FAIL; sminos-suites 18m54s).
- [ ] M7: docs and labels.
- [ ] The branch review and the merge.
- [ ] M8: the release verified (both Macs' daemons, the gate's runtime).

## What changes and what doesn't (acceptance)

1. **No sminos code path speaks DX2.** Shipped sminos has no HTTP/SSE uplink to the hub, no DX1 request codes, no `coded=True` branch, and nothing that enrolls a machine at the hub or reads `hub.json` as a credential. A grep of `sminos/skills/` and `sminos/hooks/` for `run_dx2`, `load_credential`, `credential_path`, `Sender(`, `hub_standin` and `coded=True` finds nothing, and `Stream(` finds only `sminos_control.Stream` (the control socket's reader, which is not the hub's).
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

- Observation (M3a): `test_rpcs` runs about 75 s locally instead of 36 s while both arms run, until M6. An existing race in `Checks::test_l_a_command_running_when_its_child_is_replaced_keeps_its_end` prints a thread traceback while the test passes; it is not fixed here.
  Evidence: task 3's report; sminos-suites took 22m33s on `673a7851` (run 42343036908).

- Observation (M3d): sminos-suites ran 24–27.5 min across M3's heads, against its 30-minute timeout, while the DX2 and RL10 arms both run. M4 and M5 bring it down.
  Evidence: runs 42351913496, 42352004893, 42352577867, 42354037484.
- Observation (M3d): two DX2 cases have no RL10 form. A `<message>` stays in its machine's host store and goes only to its endpoint, so beta reading alpha's stray's message becomes the stray's membership; the endpoint carries no presence, so "last seen" becomes the `last event … ago` row.
  Evidence: task 6's report.

- Observation (M5): `Plane.say_again`, `Plane.again` and `GONE_KEEP` are unreachable on RL10, since `SocketLane.hold` always returns None. They belong with the no-op `hold`/`release` gates this change scopes out (Constraints, Scope).
  Evidence: task 9's report.
- Observation (M5): sminos-suites took 19m08s on `34538211` (run 42365283498), against 23m56s at M4 and ~20–22 min before the branch.

- Observation (M6): `SocketLane`'s `unsent` count can go negative after a close during a held write. Harmless and from before the branch; not fixed here.
  Evidence: task 10's report.

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

- Decision (the coordinator's correction to M1, 2026-11-07): the host side tolerates a descriptor or `boot.env` that still names `DEVCLOUD_SMINOS_SECRET` (or the v1 `provisioning_secret`): it ignores the key with one log line and never fails a step over it. A live `keep` VM (`dc-linux171-1e68`) still carries it. The refusal stays on the driver side only, where a profile naming v1 at `vm up`, `adopt` or `reconcile` planning makes no new host. This reverses M1's first decision for the host side; the fix lands in its own commit with a test. TECH-DEBT's deleted v1 desk-key row is replaced by a pointer: the v2 delegation's expiry (about 2027-01-26) is MAWS board #512.
  Date/Author: 2026-11-07, p5-desk-track-owner (coordinator).
- Decision (M3a, the executor):
  - The RL10 twins are subclasses over seams (`coded`/`key`, `started`, `rpc`, `relay`, `no_bridge`, `op_for`, `bound`, `keyed`), so each test body runs on both paths. The coded bodies look the op key up through `rpcs.op_of` (the nonce on DX2), so their meaning is unchanged. M6 collapses each pair by deleting the coded arm.
  - `ChecksOnRl10` sends RPCs in the endpoint's shape, with the opId derived from the nonce so a resend is the same op. Three of its tests are overridden for RL10 (the cd lone-surrogate case, the spawn half of spawn-and-retire, the opId-keyed ledger without DX2's nonce-keyed RPC). Not rerun on RL10: `test_r`/`test_s` (already RL10); DX1's code, the unfenced steer and `welcome.kinds` (DX2 only); Stop k×5, Resume j×14 and the reseal test that leans on Resume's refusal (they go with `coded`; their recovery is M3b's); three tests no RPC controller takes part in.
  - The twins keep the `hub.json` fixture and flip only `coded`; the move to `identity.json` is M4's. The `test_heads` twins are the exception and trigger through `rl10.welcomed`, since that trigger is what they test.
  - The Lifecycle twins run on the real `SocketLane` over a socketpair, the endpoint's slowness modelled as a held first write.
  Date/Author: 2026-11-07, plan-executor (M3a).

- Decision (M3b, the executor):
  - Withheld and Restate run in-process: an uncoded `HubLog` against the stand-in's own `take`/`have`, since their steps depend on order and the live uplink uploads every 0.5 s. `RestateThroughTheUplink` runs one restatement end to end through `run_rl10`.
  - `endpoint_standin` gains `withhold`, an in-process callable, None by default. It refuses an upload `not-reachable`, lists and counts it in the next `have`, and answers a resend `not-reachable` again or `conflict`. Its tests are `StandinWithholds`; with it unset, admission is unchanged.
  - Unlisting: each reader's log is the stand-in's `echo` carrying the `audience`/`policyRev` the endpoint signs in, chosen by `hub_standin`'s `may_read` rule. The readers are cut over through `identity.json`.
  - Recovery of a persisted claim: Checks' three Resume reconciliations (launch and copy cleanup included) run in `ChecksOnRl10`; a new test reconciles Retire and Stop claims `interrupted` at once and sends them with `opId: null`, as the code does for a DX2-era claim keyed by nonce.
  - `RelayedOnRl10` (item 15) resets requests and RPCs per stream by hand, as `on_welcome` does, so `welcomed_rl10` writes no `identity.json` into the module's shared home. Its six DX2-only cases are None.
  - RL10 values in the ported Uplink classes: the machine policy ceiling `settings`, `desk.rpcs` = `RL10_RPC_NAMES`, each `codes.verifies` replaced by "no `mac`", and the op/compact `rpc` is the opId.
  - Not green alone: `eaa4ef8c` carries part of `test_rpcs`' `UplinkOnRl10`, which refers to `test_policy_requests.EndpointHome` before `0301a5da` adds it. Tests only. No rebase rewrites it; every commit from `0301a5da` on is consistent, and the PR names it.
  Date/Author: 2026-11-07, plan-executor (M3b).

- Decision (M3c, the executor):
  - Machines in the RL10 shell blocks cut over through `daemon probe` (test-uplink; test-sync, with a rename by `former`) or a hand-written `identity.json` (test-archive, test-org). No RL10 block uses `hub enroll`, `hub.json` or `hub_standin`.
  - test-uplink's RL10 block reuses helpers defined in its DX2 sections; M5 keeps those definitions (task 5's report lists them). Its 4 MB burst goes as several ctl sends, each under the ctl channel's 1 MiB line.
  - test-uplink's RL10 derivation case adds a session with ten tool calls so the derivation really forks; the DX2 twin's never did (its transcript has none) and passes trivially until M5 removes it.
  - Item 2's test-hub half (L279–352: seats, members, send and retire after a rename) was in neither M3 batch's list. It joined M3c, in test-sync's RL10 rename case, with the other `betaold` holder's joined arriving from the stand-in. The leave case waits for what it asserts instead of assuming one scan.
  Date/Author: 2026-11-07, plan-executor (M3c and its review).
- Decision (M3d, the executor): the stand-in gains `accepted()` (its own `echo` of what it took) and `hand()`, which passes those wrapped events to another stand-in's connection as arrivals; `relay` is a ctl command, one process a pass, retrying only a vanished data connection and failing on anything else, with stderr kept. `rl10-machines.sh` is the shared shell helper (identity fixtures, endpoints, hand-off passes). The one-pass design composes; it does not reimplement MAWS's relay.
  Date/Author: 2026-11-07, plan-executor (M3d and its review).
- Decision (M3e, the executor): `bench_rig` gains an endpoint hub that starts `endpoint_standin`, points the machine at it and cuts it over by `daemon probe`; the rig then runs the real uplink child. `BenchOpenOnRl10::test_opens_after_the_uplinks_restart` asserts the post-restart build `loaded` unconditionally, since `BenchOpens`' timed sample may honestly be missing under load.
  Date/Author: 2026-11-07, plan-executor (M3e and its review).
- Decision (the M3/M4 boundary, confirmed by the coordinator):
  - `measure_pages` part 2 is not re-pointed at RL10. Benches are measurements, not gates; `bench_open --rl10` and `bench_scale opens --rl10` measure the open through the real uplink, and M3e names only them. Rejected: porting part 2 onto `endpoint_standin`, which would duplicate what the two benches measure.
  - test-uplink's 300-event "burst while every POST is slow" is not ported: it measures DX2's batching. On RL10 the backlog's pacing is `UPLOAD_AHEAD`'s, proven by `test_session_plane.py::Lifecycle::test_a_paced_backlog_is_drawn_once_across_its_upload_passes_on_rl10` (item 16).
  - M3d's re-review found that a composition wrapper's passing predicate masks a relay command's non-zero exit. Dismissed: stderr is kept, and the predicate passes only once the consumer has the frames.
  - Item 6's second archiver (designated onto a remote another machine's archive already wrote) is not the first designation's path, and gets its own test before M4. Item 7's two-machine half (test-org: beta follows alpha's stray, the `projects`/`machines` tables) and item 2's alpha-side view of a renamed beta are composed in M3d.
  Date/Author: 2026-11-07, p5-desk-track-owner (coordinator) and plan-executor.

- Decision (M4, the executor; reviewed clean):
  - The pointer has two endings: on a cut-over machine, today's line naming the identity file; on a machine no endpoint has welcomed, that sminos takes the enrollment at the first welcome, with the machine's current name. Words after `enroll`, `check` or `leave` are ignored.
  - The milestone is two commits: a tests-only commit that holds on the old code (`d2a87149`), then the shipping commit with the 1.40.0 bump (`a76f947e`).
  - The shared fixtures are `tests/rl10_identity.py` (Python) and `rl10_cut_over` (shell, with an optional former map).
  - DX2 transport tests that still pass stay for M5, including the stand-ins' own `.enroll(` methods (`StandinHub.enroll`, `bench_rig.Standin.enroll`), which write `hub.json` as a DX2 credential and are not `hub enroll`.
  - M3 lacked a few RL10 twins: two in test-address, one in test-broadcast, test-sync's lone-surrogate writer, and two test_heads assertions with a new owed test. Each was added in `d2a87149` before its DX2 original went, since the DX2 blocks need `hub enroll` and could not stay running. The review confirmed each twin is real.
  - `test_rl10.py:282`'s first-welcome assertion is inverted. The import of `hub.json`'s former names at the first welcome is a DX2-only behaviour that goes (allowed migration d); the PR names it.
  - `sminos.queued_counts` goes as dead code. Left for M7: the user strings that still say `sminos hub enroll` (`hub_here`'s hint, `cmd_machines`, the usage text, the `run_suites` labels). Left for M6/M7: `cmd_machines`' DX2 presence branch, which nothing reaches.
  - test-sync's "neither machine ever ran git" is now asserted on the one-machine RL10 block alone.
  Date/Author: 2026-11-07, plan-executor (M4).
- Decision (the coordinator, 2026-11-07): origin/main (`fcf0b6a5`, PR #469, sminos 1.39.1, the macOS protected-folder guard) is merged into the branch, never rebased, before the whole-branch review. Where the branch deletes phase-1 code the deletion wins; the guards stay in whatever survives, and `test_protected.py` stays green (its `hub.json` fixture moves to `identity.json`). 1.40.0 stays above 1.39.1.
  Date/Author: 2026-11-07, p5-desk-track-owner (coordinator).

- Decision (M5, the executor):
  - test-uplink's four in-process coded `HubLog.take` cases stay for M6: they test the coded branch, not the transport. `on_welcome`'s coded arm loses only the `Sender` start; its generation and `kinds` lines are M6's.
  - `uplink_change` keeps three cases; an undone cutover says "no uplink runs until a probe's welcome cuts this machine over again". `uplink_status` prints no uplink line on a machine that is not cut over.
  - `HubLog.closed` goes with `refused_whole`, its only caller. `UPLOAD_AHEAD` is the literal `4 << 20` now that `POST_LIMIT` goes as a name.
  - The DX2 base classes are folded into their RL10 classes, keeping the class and method names the M3 checklist cites. `bench_scale` runs RL10 by default and still accepts `--rl10` as a no-op; `bench_open` takes `--rl10 | --micro`.
  - Two RL10 twins were added before their DX2 Lifecycle originals went (`Link.open`'s continuation: the marks move only once the hello is taken).
  Date/Author: 2026-11-07, plan-executor (M5).

- Decision (M5's review, 2026-11-07): acceptance 1's grep is revised. `Stream(` can never come up empty while `sminos_control.Stream` (`sminos_control.py:439`, `:487`) exists, and that class is the control socket's reader, not the hub's SSE `Stream`. The grep now names `credential_path` and expects `sminos_control.Stream` as its one `Stream(` hit. M6 adds an RL10 test that drives `SocketLane.send` past `SEND_QUEUE_MAX` into `NotDelivered`: the deleted `Lanes` test proved `Sender`'s copy of #149's bound, and no RL10 test went past it (a gap from before the branch).
  Date/Author: 2026-11-07, plan-executor, on M5's review.

- Decision (M6, the executor; reviewed):
  - `policy.machine_policy` stays, against the design's list: test_rl10 (`:398`, `:450`) and rl10_conformance (`:638`) assert through it, and it is RL10's resolved-policy reader. `hublog.machine_policy`, the DX2 wrapper, goes.
  - Resume, Retire and Stop stay offered, shape-checked and refused `unsupported`, which is what RL10 did and what acceptance 2 pins. Only their admission and execution go, with the `dispatch` facts only they read. `live-stop-check.py` goes with `live-resume-check.py` (it drives `rpc.stop`). `LaunchStart` stays: it tests `launched_by`'s start-time path in the recovery that stays.
  - `Link`'s `transport` is a required keyword. `Requests.seal` stays and returns the draft. `on_refused`'s `not-open` return and `Subscription`'s `catalog_allowed` switch stay (behaviour-neutral, in the scoped-out refused-map area).
  - `is_hub_writer`/`HUB_PREFIX` and `hublog.is_tombstone` go, against the map's class (c): their only callers were the MAC half and the coded `take`. The credential's `"key"` leaves shipped code; test dicts keep `"key": None`.
  - test-uplink's four coded `take` cases are ported to RL10, not deleted. The lane-bound test (`SocketLane.send` past `SEND_QUEUE_MAX`) lives in test_session_plane's `Lifecycle`. test_rl10's nonce-index patch is the one acceptance-2 migration beyond the list, forced by the method's removal; the PR names it. test_reach's kept Retry test trades `hl.paused == {}` for a behavioural check.
  - The review found that dropping the MAC half's position vectors took the only tests of `is_log_seq`'s and `is_iso_millis`'s edge branches, which RL10 runs (acceptance 6). They come back as direct checks, with Stop's RL10 shape check, in M6's fix.
  Date/Author: 2026-11-07, plan-executor (M6 and its review).

## Outcomes & Retrospective

(At completion.)
