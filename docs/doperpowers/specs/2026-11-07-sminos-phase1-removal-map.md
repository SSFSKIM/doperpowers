# Board #153: mapping sminos's phase-1 (DX2/DX4) removal

Read-only map of doperpowers `origin/main` at merge `904b0a35` (sminos 1.39.0), read from an export (`git archive`) so the shared checkout was untouched. MAWS was read at `origin/master` `1a11fedf6`. Line numbers are origin/main's. Paths are under `sminos/skills/sminos/scripts/` unless they say otherwise.

## 0. What the map changes about the ticket

1. **The DX4 session plane is not unreachable; RL10 carries it.** The endpoint's plane A subscribes upstream to sminos over RL10 (MAWS `src/endpoint/plane-a.ts`, header: "DX2's session lane over RL10"; RL10's `subscribe`, `rows`, `diff`, `output` and `read`, plus `presence`, `raised`, `settled`, `op` and `delivery`). DL 241 (2026-11-07) confirms sminos serves an agent's transcript over RL10 "as it does the hub's".
   - So `sminos_plane.py` stays almost whole, and so does `Link`'s session-lane dispatch.
   - What goes is the DX2 transport under the plane, the DX1 codes, and the hub enrollment.
   - Read the criterion "no sminos code path serves DX4" as "serves nothing over the hub's DX2 stream". The DX4 message envelope is RL10's too.
2. **One `Link` serves both protocols; the `coded` flag is the switch.** `sminos_uplink.py` is mostly RL10 code: `Link`, `serve`, `SocketLane`, `SocketTransport`, `run_rl10`, `cmd_probe`, `Parts`/`to_wire`. The DX2-only part is the HTTP/SSE transport and the `coded=True` branches.
3. **What picks the protocol at runtime is `daemon/identity.json`.**
   - The supervisor's choice is `sminos_daemon.uplink_wanted` (`sminos_daemon.py:1581`): `rl10.cut_over()` gives `rl10` or `waiting`; else hub.json's bytes give `dx2`.
   - The child's choice is `sminos_uplink.cmd_uplink` (`:3204`): `rl10.cut_over()` runs `run_rl10`; else `load_credential()` runs `run_dx2`.
   - `Kept.__init__` (`:3079`) sets `coded = key is not None`.
   - Every other `cut_over()` check (words, reach, host store, widening, labels, `machines`) separates "has an endpoint" from "has no upstream", not DX2 from RL10. Those stay.
4. **`hub.json` is already gone from every production machine** (B4 step 5, DL 239 and DL 242). Readers keep it alive for three reasons:
   - the RL10 conformance fixture's `legacy-key?` case;
   - fixtures in the tests;
   - devcloud's DX2 enrollment path.
5. **DL 231's "enrolled means hub.json" is not what the code does.** DL 235 rewrote the exception as "not cut over", and sminos 1.39.0 built it that way: `sminos_audience.widening_through_app` (`sminos_audience.py:174`) keys on `rl10.cut_over()` and the kept `record` capability. Neither the audience nor the visibility module reads hub.json.
6. **devcloud calls the verbs this removes.** It runs `sminos hub check`, `hub enroll` and `hub leave`, and tests for hub.json:
   - `devcloud/boot/devcloudlib/sminos_host.py:99-242` and `departure.py:334-396`;
   - its v1 `provisioning_secret` and `--enroll-code` (`devcloud/driver/profile.py:219-231`, `up.py:130`).

   The path is dead in production (DL 242 step 6 destroyed the v1 code and its secret), but it needs its own commit and a devcloud bump. Section 5 covers the ordering.
7. **Collapsing `coded` also kills the Resume, Retire and Stop RPCs, plus steer-without-a-bridge.**
   - On RL10, `plan` refuses `UNFENCED = ("resume", "retire", "stop")` with `unsupported` (`sminos_rpc.py:288`, 1122-1124). `context_refusal` refuses a session with no bridge `context`, so the steer fallback `steer_without_bridge` (1203, 2489) never runs either.
   - MAWS O10 offers none of them "until a child that needs them fences them" (`2026-10-27-p5-o10-endpoint.md:239`, 563).
   - Once the DX2 branch goes, `resume`, `retire`, `launched_by` and `steer_without_bridge` (2489-2760) and their tests become unreachable code.
   - **Owner's call (product).** My recommendation: delete them in the same commit, and bring them back from history when a fenced child needs them. Their fence is new work in any case.
8. **The real cost is the tests, not the code.**
   - About 220 Python tests and about 330 shell assertions exercise shared or RL10 behaviour, but drive it through DX2: coded fixtures, or `hub_standin.py`.
   - About 20 shared behaviours have no other coverage (section 2.4).
   - No two-machine RL10 rig exists. `endpoint_standin.py` is one machine, with no hub behind it.
   - Re-pointing has to land before the transport goes, or the gate stays green while coverage silently drops.

## 1. Code on the DX2/DX4 path

Classes: **(a)** DX2/DX4-only, safe to delete; **(b)** shared, losing only the named DX2 branch; **(c)** looks phase-1 but RL10 uses it, so it stays (call cited).

### 1.1 `sminos_uplink.py` (3250 lines)

**(a) delete: the hub's HTTP/SSE transport and the DX2 credential**
- `CredentialBad` 189, `credential_path` 193, `hub_admitted` 197, `load_credential` 208. Their only other user is `sminos_hub` (`check`, `leave`, `held`, `stored`), which goes too. `on_legacy_key` uses `credential_path()`; it should name the path itself (see the (c) list).
- `dial` 234 (Happy Eyeballs), `HTTPConnection` 293, `HTTPSConnection` 302, `connection` 306, `admission` 313. Their only other user is `sminos_hub.redeem_once` (169-171) and `ask` (503-506), both of which go.
- `sse_events` 320, `heartbeat_at` 346, `Stream` 357-497. This is the SSE reader plus the `hb-ack` acker and its `take_org` priority.
- `frame_headers` 581, `post` 585, `shut` 612, `watched` 620, `exchange` 654, `readable` 674, `idle_close` 683.
- `RENEWED_KINDS` 708, `renewed` 711, `Entry` 726, `Dial` 751, `Sender` 761-1158 (the two HTTP lanes, the `not-open` gate, `hold` and `release`).
- `project_of` 690 is used by `Sender` and `refused_whole`. Check that `by_project` 699 stays (see (c)).
- `run_dx2` 3094.
- Constants:
  - Go: `STREAM_PATH`, `FRAMES_PATH`, `HEARTBEAT_MS`, `SILENT_PERIODS`, `LINE_MAX`, `LOOPBACK`, `POST_TIMEOUT`, `STAGGER`, `ANSWER_MAX`, `ACK_GAP`, `IDLE_CLOSE` (`SMINOS_IDLE_CLOSE`), `SLOW_POST_SECONDS`, `CONNECTIONS`, `STALE` (151-186).
  - `POST_LIMIT` goes as a name, but `UPLOAD_AHEAD = POST_LIMIT` (173) is RL10's, so keep the 4 MiB value.
  - Imports: `errno`, `http.client`, `selectors`, `ssl`, `urllib.parse`.
- `Link.on_hb` 1977 (no-op; the `hb` frame is DX2's). `Link.refused_whole` 2034 is a `Sender` callback; on RL10 nothing is ever refused whole.

**(b) shared, losing a DX2 branch** (each `self.coded` test becomes its RL10 arm)
- `Link.__init__` 1502.
  - Drop the `coded` and `transport=None` params.
  - `self.plane = Plane(..., host=not coded, launches=not coded)` becomes always on.
  - `Rpcs(..., coded=coded)` becomes `Rpcs(machine)`.
  - The RL10 handlers (1573-1582) are merged into the main table.
  - `self.generation` is always `transport.number`.
- `Link.on_welcome` 1646. Drop the `if self.coded:` arm (1647-1655: generation and DX2 `welcome.kinds`) and the `Sender` start (1694-1700). Keep `kinds = EVERY_KIND`, or drop `kinds` altogether (next bullet).
- `kinds` filtering, DX2's `welcome.kinds`:
  - `EveryKind` and `EVERY_KIND` 1161-1169;
  - `Plane.kinds` (`sminos_plane.py:2659`), its `catalog_allowed` (2898) and its `read` gate (2960);
  - `Rpcs.kinds` (`sminos_rpc.py:778`) and `Rpcs.due`'s "the hub lists no `op`" drop (1677-1682).

  On RL10 every kind passes, so the whole mechanism can go.
- `Link.deliver_imports` 2129, `open` 2241, `upload` 2304, `machine_presence` 2441 (`machine_policy() if self.coded`), `tick` 2838-2927 (six `self.coded` tests). Each RL10 arm becomes unconditional.
- `Link.open` 2165. `session_lane.hold`/`release` are no-ops on `SocketLane` (1211-1216), so the `flying`/`dropped` re-open heal is dead on RL10.
  - Minimal option: keep the calls (they return `None, []`).
  - Fuller option: delete `hold`, `release`, `Plane.say_again` (2819) and `Requests.stale`'s re-open use.
- The `refused` map that every continuation takes (`Link.uploaded` 2319, `reported`, `Requests.delivered`, `Rpcs.delivered`): `SocketLane` always passes `{}` (1258). Keeping the parameter is behaviour-neutral. Dropping it is optional cleanup across four modules.
- `Link.on_refused` 2021. Its `not-open` early return is DX2's copy of a POST answer; keep the rest (RL10 sends `refused`, as the conformance fixture's two `down: refused` show).
- `serve` 2945 drops the `coded` param. `Kept.__init__` 3075 becomes `Requests(machine)` / `Rpcs(machine)`.
- `cmd_uplink` 3204. Drop the `load_credential()` branch (3224-3232). Not cut over now means "nothing to connect", and the supervisor's probe cuts the machine over.
- Module docstring 1-114: rewrite.

**(c) stays: RL10 runs it**
- `wire_text`, `escaped_size`, `to_wire`, `Parts`, `EndStream`, `NotDelivered`, `Stopping` (499-578). `SocketLane.send` calls `to_wire` (1195), and the endpoint reassembles parts (MAWS `rl10/server.ts:271-283`).
- `by_project` 699: `relay_requests` 2489 and `relay_rpcs` 2502.
- `SocketLane` 1172, `SocketTransport` 1264, `hub_projects`, `register_own`, `keep_org`, `hub_project`, `_snapshot_index`, `snapshot_page`, `joined_dirs`, `member_frame`, `Here` (1303-1478).
- All of `Link`'s RL10 handlers:
  - `welcomed_rl10`, `on_policy`, `sync_policy`, `on_revoked`, `on_words`, `held_ask`, `ask_peer`, `on_reach`, `on_audience`, `complete_transitions`, `on_snapshots`, `on_query`, `on_tombstone`, `on_spent` (1704-2015);
  - the shared log-plane handlers `on_have`, `on_events`, `on_resend`, `on_refused`, `on_part`, `on_org`;
  - the session-plane relays `on_subscribe` … `on_rpc_ack` (2075-2106; RL10 sends `rpc` and `rpc-ack`, as the fixture's four and three show);
  - members, words, host pass, mark_revoked, restated (2358-2828).
- `Link.on_legacy_key` 1931. RL10 code, and it reads `hub.json`'s DX1 key. The conformance fixture's case 2 ("the legacy key handed over once, kept 0600 and never logged") replays `legacy-key?` and needs the answer, and the replay fails on any line it cannot send as written. It stays until MAWS drops `legacy-key?` from RL10 and the fixture (section 3).
- `run_rl10` 3146, `rl10_connection` 3111, `cmd_probe` 3171, `take_lock`, `supervisor`, `Kept` (`adopt` handles RL10 renames).

### 1.2 `sminos_daemon.py`

- **(b) `uplink_wanted` 1581.** Drop the `dx2` arm (1591-1592). Not cut over returns `(None, None)` while the probe runs.
- **(b) `uplink_change` 1595.** Drop the arms naming `dx2` (1597-1600 and 1607-1609). `rl10 → None` (identity.json removed) needs wording: "the cutover is undone; the endpoint is probed again".
- **(a) `credential_bytes` 1562 and `LEFT_THE_HUB` 1572.**
- **(c) `UplinkSupervisor` 1612**, `probe` and `stop_probe` stay. A probe's whole welcome is how a new machine cuts over. Only its docstring (1613-1636) changes.
- **(b) `uplink_status` 2016.** Drop the hub.json line (2027-2030) and the "and stays on the hub" clause (2032).
- **(b) `enrolled_at` 757.** Drop the hub.json fallback (764-769).
- **(b) `enrollment_inspected` 2345.** Drop the hub.json arm (2356-2360). Not cut over is "not enrolled".
- **(c) `daemon owed`** (`cmd_owed` 2368, `OWED_KINDS` and the rest) stays whole. Only its comment's "a `hub leave` before the first `have`" (2109) goes stale.

### 1.3 `sminos_hublog.py`

- **(a)** `NONCE_DOMAIN` 117, `nonce_for` 169, `seal` 180, `same_event` 252, `machine_policy` 470, `HubLog.nonce_index` 1335 and `self.nonces` (488).
- **(a)** `ask_wait` 285, `ASK_MS` 148 (`SMINOS_ASK_MS`), `HubLog.paused` (505, read at 1256-1260, set only at 1070-1074). This is the `state-unavailable` direct-stream pause, which is DX2 only; on RL10 the endpoint rewinds.
- **(b) `refusal` 212.** Drop the `coded` param and the code check (223-231); the shape checks stay.
- **(b) `HubLog.__init__` 480.** Drop `coded` and `key`.
- **(b) `HubLog.take` 1361.**
  - Drop the `self.coded and is_tombstone(raw)` arm (1372-1378), which handles a DX2 tombstone arriving. RL10 says it as `spent withheld`.
  - Drop the coded refusal (1379-1380), the seen-nonce check (1391-1394) and the nonce index upkeep (1402-1403).
  - `unwrapped`/`verified` becomes the only path.
- **(b) `HubLog.same` 1350.** `same_uncoded` becomes the only comparison.
- **(b) `HubLog.uploads` 1280.** `as_uploaded(e)` becomes unconditional.
- **(b) `HubLog.presence` 690.** `wire_policy()` and `desk(rl10=True)` become unconditional. `desk` 456 lists `RL10_RPC_NAMES` only.
- **(b) `HubLog.on_refused` 1036.** The `malformed` stop (1055-1056) becomes unconditional; drop the `state-unavailable` arm (1070-1074).
- **(c) everything else.** `is_tombstone` and `tombstone` (the archive writes tombstones), `rejected` (RL10 reports rejections up; fixture case 8), the `have`/`resend`/`taken`/`bound`/`conflicts` state, `withhold_own`, `spend`/`spend_own`, `release_heads`, `voided`/`dead`, `show_notices`, `deliver`.

### 1.4 `sminos_rpc.py`

- **(b) `Rpcs.__init__` 755.** Drop `key` and `coded`.
- **(b) `receive` 803.** Drop the `codes.failure` check (811-814; `bad-code`). `RPC_NAMES if self.coded else RL10_RPC_NAMES` (825) becomes one list, so `RL10_ONLY` and its "offered through the endpoint alone" refusal (299, 826-827) collapse. `target_of` (838-839) becomes unconditional.
- **(b) `dispatch` 843.** The `op-conflict` check (860-864) and `binding_of` in `flight` (904) become unconditional.
- **(b) The rest of `Rpcs`.**
  - `admit` 935: `context_refusal` becomes unconditional.
  - `keep` 970: `entry_of(..., remote=True)`.
  - `ack` 994: the opId fallback becomes unconditional.
  - `run` 1067.
  - `plan` 1113: `remote = True`.
  - `result_frame` 1663: always carries `opId`.
- **(c) the nonce-keyed ledger.** `op_of` falls back to the nonce, `ledger_view`, and `binding_of` returns none for a DX2-era entry. These stay: the fixture stages "the ledger's entry from before RL10" and checks that "a DX2-era entry answers none" (case 11). `refuse_loose`'s `codes.b64url_bytes(nonce, NONCE_BYTES)` stays (RL10 RPCs carry a nonce).
- **(b) docstring 1-210.** Check 1's DX1 code goes, and the `coded=False` contrast (159-168) becomes the only text.

### 1.5 `sminos_requests.py`, `sminos_outcomes.py`, `sminos_owed.py`

- **(b) `Requests`** (`sminos_requests.py:271`).
  - Drop `key` (277). `seal` 451 returns the draft always (drop the `codes.seal` arm, 456-457).
  - `restore` 302: `uncoded` (325) becomes unconditional, which is exactly the RL10 behaviour now. It strips a pre-cutover `mac` and renames to the machine now, so keep it.
- **(c) `shown_input`/`RAISED_INPUT_MAX`** (#149) stays (section 4).
- **(b) `sminos_outcomes.message` 417.** Drop `key` and the `codes.seal` arm (423-430). Its caller is `sminos_uplink.py:2341`.
- **(c) `sminos_owed.py` (71 lines).** No DX2 code. The docstring (POST 200, `refused not-open`, MAWS #88) needs rewording: owed until the endpoint's socket took the frame.

### 1.6 `sminos_codes.py`

- **(a) the MAC half.** `DOMAINS` 42, `CODE_BYTES` 49, `covered` 207, `covered_bytes` 228, `_digest` 232, `code` 236, `seal` 241, `failure` 250, `verifies` 276, and `is_hub_position` 316 if `failure` is its only user.
- **(c) the rest.** `b64url*`, `loads`, `number`, `string`, `canonical`, `NotCanonical`, `NONCE_BYTES`, `MEMBER_RE`, `ISO_MILLIS_RE`, `is_hub_writer`, `input_sha256`, `is_log_seq` and `is_iso_millis` stay. RL10 uses them for canonical proof checks (`record_proof`), RPC nonces, the decide digest (`args.digest` is still DX1's `{session, request, tool, input_sha256}`, fixture case 10), part ids and log-seq shapes.
- The module docstring (1-31) becomes "canonical JSON and base64url". Renaming the module is optional.

### 1.7 `sminos_plane.py` (3050 lines): (c) almost whole

- Its callers on RL10 are `Link.on_subscribe`/`rows`/`diff`/`output`/`read` (2075-2100), `Plane.presence` in `open`, `Plane.member_rows` in `Link.members`, `Plane.tick` (2918), and `host_body`/host events (264-271, 1528, 1868-1887).
- **(b)** `Plane.__init__` 2629: `host=` and `launches=` default to off for DX2; make them always on. The `kinds` filter: see 1.1.
- **(c)** the tombstone marks (`tombstone_path` 2603, `accepted` 2837, `take_read` 2831) run on RL10 too, since `open`'s continuation runs once written.
- Docstring 1-6 and 169-170: "DX2's session frames", "`read` goes only to a hub whose welcome lists it".

### 1.8 `sminos_hub.py` (697 lines)

- **(a)** The DX7 code and redemption: `CODE_PREFIX`, `PROVISION_PREFIX`, `KINDS`, `MACHINE_RE`, `RESERVED`, `REDEEM_PATH`, `ATTEMPTS`, `TIMEOUT`, `ANSWER_MAX` (71-90), `CodeRefused`, `Lost`, `is_machine_name`, `_no_constant`, `check_hub`, `decode_code`, `redeem_once`, `redeem`, `said`, `refusal` (92-245).
- **(a)** `held` 247, `read_code` 289, `refuse_case_twin` 321, `enroll` 352, `ENROLLMENT_PATH`/`ACCESS_*`, `recheck_after`, `whole_body`, `ask`, `authenticated`, `stored`, `check`, `leave`, `enroll_args` (467-687).
- **(c)** stays; RL10 or `project init --hub` uses them:
  - `credential_lock` 262 (`sminos_rl10.welcomed` 402; rename to an identity lock if you like);
  - `sessions_under` 305 (`sminos_rl10.welcomed` 414 and 417);
  - `add_hub` 628 (`sminos.py:7747`).
- **(b) `enrolled_hub` 275** (`sminos.py:7743`): identity.json only, with the not-enrolled message pointing at mawsd.
- **(b) `show` 434:** the identity.json arm only.
- **(b) `refuse_cut_over` 341:** it becomes the pointer `enroll`/`check`/`leave` answer with (section 3).
- **(b) `cmd_hub` 688 and `USAGE` 664.**
- What's left is about 150 lines. Fold it into `sminos_rl10.py` or `sminos.py` if you want one module fewer.

### 1.9 `sminos.py`

- **(b) `enrollment()` 815, `enrolment_stamp()` 2010 and `machine_identity()` 8773.** Drop the hub.json fallback (825-829, 2016-2021, 8786-8793). `machine_identity` becomes identity.json, else `DAEMON_HOST`, else the host name.
- **(b) `hub_here` 944.** The not-enrolled warning says "(sminos hub enroll)" (954-955); point it at mawsd.
- **(b) `cmd_machines` 11805-11856.** Drop the DX2 rendering (`online`/`last seen` 11850-11852, "the daemon has not connected to the hub" 11836). After the removal `e is not None` implies cut over, so `rl10` is always true where an org exists. `org_age_line` 11754: drop the "stream has said nothing newer" arm (11765). "not enrolled at a desk hub (sminos hub enroll)" (11832): reword.
- **(b) The usage text and the `hub` parser.** Usage 92-94 (`sminos hub enroll … | show`) and the `hub` parser 12773-12780 follow section 3's outcome.
- **(c)** every `rl10.cut_over()` gate: `deliver_next` 4465, `words_held` 4679, `sender_labels` 5206, `host_store_holds` 6669, `SendDelivery` 10722. Each tells "has an endpoint" from "has no upstream", which stays meaningful.
- **(c)** `desk_proof` 2852 (comment "(a DX2 spawn)") and the `waits_for_head` / heads machinery (2000-2230) stay. Only their comments name `hub enroll`.

### 1.10 `sminos_rl10.py`, `sminos_audience.py`, `sminos_visibility.py`, `sminos_archive.py`, `sminos_bridge.py`, `sminos_policy.py`, hooks

- **(c) `sminos_rl10.py`, whole.**
  - `cut_over` 338: "removing it undoes that" stays true; the next probe cuts the machine over again.
  - `welcomed` 392 reads hub.json indirectly, through `sminos.machine_identity()` at the first welcome (406-408). Once `machine_identity` drops hub.json, a DX2-enrolled machine that never cut over would cut over under its host name and lose its `former` sessions. No such machine exists (all three cut over, and the hub refuses DX2), but the conformance replay stages one. See section 2.
- **(c) `sminos_audience.py`** (`widening_through_app` 174, `reach_capable` 147) and **`sminos_visibility.py`** read `rl10.cut_over()` and `daemon/audiences.json`, never hub.json. Only the comment "enrolled at no hub: no hub, no welcome" (188) changes.
- **(c) `sminos_archive.py`** has no DX2 branch: it already builds `HubLog(..., coded=False)` (142). Its docstring's "the hub tells that machine in `have.archive`" stays true, since the endpoint relays the hub's `have`.
- **(c) `sminos_bridge.py`** has no DX2 path. The ticket names it, but its only DX4 mentions are the snapshot/gap rules the plane still serves.
- **(a)/(b) `sminos_policy.py`.** `machine_policy` 101 goes once `hublog.machine_policy` and `Link.machine_presence` stop calling it; `wire_policy` 107's docstring "DX2's hub takes the mode it resolves to" (111) goes too.
- **(b) hooks.** `hooks/smns-guide.sh:15` and `hooks/smns-record.sh:34` test `hub.json || identity.json` for "enrolled"; make that identity.json alone.

### 1.11 Outside sminos: devcloud (its own plugin and version)

- `devcloud/boot/devcloudlib/sminos_host.py`:
  - `IDENTITY` 46 (hub.json listed for the sandbox check: harmless to keep);
  - `at_hub` 99;
  - `hub_json` 182;
  - `enroll` 186-242, which runs `sminos hub check` then `hub enroll --name … [--replace]` with the v1 key on stdin.
- `departure.py:_endpoint_leave` 383-396 (`sminos hub leave` when hub.json is a file).
- `descriptor.py` (`DEVCLOUD_SMINOS_SECRET`, 23, 61, 182-211), `driver/profile.py` (`[desk] provisioning_secret`, the v1 code, 87 and 219-231), `driver/cli.py`, `up.py`, `hostctl.py` (`--enroll-code`, `/etc/devcloud/enroll-code`), `bake_check.py:24`, and `README.md:505-535`.
- devcloud's unit tests use their own fake sminos (`devcloud/tests/fixtures/sminos.py`), so sminos's change cannot turn devcloud's suite red. Only a live VM with a v1 secret or an enroll code would fail, and that path is dead now that the hub refuses DX2 and the v1 secret is deleted.

## 2. Tests and benches

### How the runner counts

- **Core cases.** `tests/run-sminos-tests.sh`'s own cases count `PASSES` (`pass()` at L43; `summary` at 480-490).
- **Suites.** Each suite in `run_suites` (352-478) is **one** pass or fail line, decided by its exit code. A suite's own count ("Ran N tests", or "all N … passed") never reaches the top level.
- **Exceptions, one line per printed `ok`.**
  - In `run_suites`: `rl10_conformance.py` (about 98), `jobs_parity.py`, `routes_check.py`.
  - In the core part: `codes_parity.py` (4745; 194 lines), `machine_project_parity`, `remote_key_parity`, `marks_parity`, `engine_relocated_shape`.
  - `enroll_parity.py` is counted inside `test-hub.sh`.
- **What the removal does to the counts.**
  - Trimming a suite changes the top level by 0. Deleting a suite file and its line changes it by 1.
  - On these numbers, the top level loses exactly **1 suite line** (`test_happy_eyeballs.py`) and about **141 core lines** (`codes_parity`'s MAC, seal and verify cases, of 194).
  - Each trimmed suite's own count drops by its (a) count below.
  - That is the "count of removed tests matching the removed code" to quote in the PR, per file.

Classes: **(a)** goes with its code; **(b)** shared behaviour driven through DX2, so it needs re-pointing (a twin is named where one exists); **(c)** stays. Counts are unittest's effective counts, or runtime assertions for the shell files.

### 2.1 Python suites (`unittest`, one `run_suites` line each)

| File (total) | (a) go | (b) re-point | (c) |
|---|---|---|---|
| `test_session_plane.py` (270) | **38** (48 if `bench_open --uplink` goes). Instruments L2859 (7, tests of `hub_standin`/`pause_proxy`); BenchOpen L3246, L3293, L3339, L3360 (plus 10 analysers); Lifecycle L4493, 4591, 4632, 4712, 4720, 4730 (`say_again`), 4751; Lanes L5147 (18, `Sender`); Uplink `test_h` L6262, `test_i` L6302. Also `Hub`/`StandinHub`/**`LocalHub`**/`make_hub`/`call` (L5583-5737), and `ScriptedHub` L5039 once the rest is moved. | **16**. Lifecycle L4396 (twin `test_rl10::Policy.test_the_ceiling_settings_is_the_users_defaultmode_both_ways`), L4771, L4804, L4832 (no twin: `Link` on a fake lane). Uplink L5739's 12 (L5815 … L6392): rows, diff, output, read, unsubscribe, reload, ended paging, reconnect mid-response, presence latency, mode, warmer, capabilities. Only partial twins. | 206: Engine, RealChild, Jobs, Desk, McpDisabled, Catalog, ChainRules, TranscriptIndex, Warmer, TickCost and the rest. Small edits once `Plane` drops `host`/`launches`/`kinds` (L320, 1904, 2487, 2510, 2746). |
| `test_rpcs.py` (162) | **27**. Checks `test_a_bad_code` L614; k×5 L977-1031; L1256 (steer with no bridge); L1389 (no `op` listed); j×14 L2418-2772 (resume, retire, stop: see §0.7); L3547 ("send offered through the endpoint alone"); LaunchStart L3879 (3); Uplink `test_f` L4258. | **111**. The other 103 of Checks a-q drive a sealed `Rpcs(KEY)`; re-point through the existing `remote_mode()`/`remote()` (L3207). Uplink L3944's 8: `test_i` (twin `test_rl10::Raised…lanes_bound…`), `test_a` (partial twin `test_rl10::Rpcs.test_an_rpc_down_rl10`), and `test_b` to `test_h` with none (executed-once across a cut, restart mid-report, retried spawn, compact/op to browsers, spawn into the machine project). | 24: Checks r and s (L3239-3679), LaneVerdict, SendsPruned, CopyNames. |
| `test_policy_requests.py` (57) | **6**: RelayedOnLanes L1570, 1608, 1635, 1667, 1703, 1741 (`not-open` and per-POST refusals). | **30**. Requests L833 (21, `Requests(KEY)` to `Requests(None)`, drop `codes.verifies`; L1319 is #149's, §4); Owed L1396; RelayedOnLanes L1519, 1535, 1777; Uplink L1844 (5), with partial twins in conformance cases 9, 12, 13, `test_rl10::Policy` and `test_words::Revoked`. | 21: Policy, Delivery, Refusals. Their `hub_human()` (L182) seals with `codes.seal`, so give it the RL10 stored form when `seal` goes. |
| `test_withheld.py` (20) | 0 | **18**. Class `Dx2` L127 (7; 2 twinned in `Rl10`); `Restate` L241 (11, no twin). The code is shared; re-point through `endpoint_standin`'s `refuse` ctl. | 2 (`Rl10` L426). |
| `test_reach.py` (30) | **12**. HubStandin L165 (10, tests of the stand-in); Retry L601 (coded `state-unavailable`); Dead L737 (DX2 tombstone; twin `test_rl10::Spent…`). | **11**. Admitted L418 (10: a coded `hl()` becomes `coded=False`); Dead L724. | 7 |
| `test_heads.py` (26) | **5** (if `hub enroll`/`leave` go): Dx2 L138, 180, 205; Renamed L457, 487. | **10**. Dx2 L100 (twin `Rl10…cutovers_welcome_holds…`), L118, 130, 142, 154, 216; Streams L248, 268; Renamed L409, 504. Trigger them through `rl10.welcomed` and an uncoded HubLog. | 11 |
| `test_owed.py` (42) | 3 on hub.json: Enrollment L706, L713; Upload L299, whose meaning flips. | **12**. A coded HubLog or Link becomes uncoded, a trivial flip: Taken L385; TakenBounds L420 (4); TakenResumes L611-643; TakenWrites L665 (3). | 27 |
| `test_scale.py` (44) | 2: OrgAhead L1007, BenchStops L1182 (`test_sigterm_on_dx2`). Add BenchOpens L1038 and L1074 if `bench_scale opens` goes. | 10: HotLooks L300 (8), CheckoutsFromTheRead L887 (2), both coded. | 30 |
| `test_visibility.py` (49) | 1 (L1178 `test_dx2_never_carries_them`) | 2 (Unlisting L750, L786: the readers' projection through `hub_standin`'s filter; no twin) | 46 |
| `test_happy_eyeballs.py` (4) | **4, the whole file** (`dial`, `hub.redeem_once`): the `run_suites` line goes | 0 | 0 |
| `test_org_retired.py` (9) | 4 (class Hub L153: `test_machines` L162, and 3 Rows variants twinned in CutOver) | 0 | 5 |
| `test_rl10.py` (44) | 0 | 0 | 44. LegacyKey L468 holds only while hub.json's key does. Trim Drafts L1051's DX2 half. |
| `test_words` (63), `test_snapshots` (5), `test_reach_gate` (32), `test_records` (61), `test_manager` (109), `test_holder_deliveries` (57), `test_streams` (23), and the other `test_*.py` | 0 | 0 | All stay. The hub.json fixtures are treated in §2.3. |

**Totals:** about **115 go** (127 with the bench analysers), and about **220 are re-pointed**.

**Helpers and fixtures:**
- `pause_proxy.py` goes.
- `bench_codes.py` goes.
- `codes_parity.py` and `dx1-codes.json` are **trimmed, not deleted**: they lose 141 lines and keep 53 (canonical, loads, `input_sha256`, which RL10 uses).
- `enroll_parity.py` and `dx7-enroll-codes.{json,gen.mjs}` go if `hub enroll` goes.
- These stay: `dx4_consumer.py`, `dx4-stream.*`, `dx4-jobs.*`, `jobs_parity.py`, `envelope_parity.py`, `remote_key_parity.py`, `machine_project_parity.py`, `inbox_standin.py`.
- `hub_standin.py` goes once its last user goes. Its users are the (b) tests above, the shell suites below and the benches.

### 2.2 Shell suites and core cases

Counts are runtime assertions; each file is one `run_suites` line.

**`test-uplink.sh` (~194): about 93 go, about 60 re-pointed, about 40 stay.**
- **(a)** About 93:
  - the credential (258-273);
  - opening the stream with the token (275-293);
  - the SSE drain, codes and forgeries (303-336);
  - leaving the hub (575-615);
  - slow and held POSTs (617-713);
  - the lease (715-767);
  - coded own-writer positions (769-860; twinned in `test_rl10` LogPlane and Spent);
  - and inside the RL10 block: `dx2_holds` ×4, "hub's uplink stopped", "for good" (1011-1037), and "undone, back to DX2" (1039-1104).
- **(b)** About 60, with no RL10 twin anywhere. These are the uplink child's supervision:
  - its own process and locks;
  - delivery within 1 s while a derivation runs or a fetch hangs;
  - an import during a tick's delivery is delivered once;
  - tick and uplink fail apart, and a killed uplink restarts;
  - SIGTERM and orphan endings;
  - a code-change restart in place;
  - orphaned at start;
  - ending promptly under traffic (275-573).

  They run on DX2 only because the child needs something to connect to. Re-point them onto the RL10 block's endpoint stand-in. Its scaffolding (`start_run` waits on the hub stand-in's generation; `hub_seen`) has to be rewritten, not deleted.
- **(c)** The RL10 block (862-1104) and the setup.

**`test-hub.sh` (~534): about 455 go if `hub enroll`/`check`/`leave` go.**
- **(a)**
  - the code and `enroll_parity` (177-229, about 197);
  - enrolling (230-262; its heads mark twinned in `test_heads` Rl10);
  - a taken name, case twins (263-278, 353-383);
  - the hub's answers (384-465);
  - provisioning keys (763-846);
  - check and leave (847-1062, about 108);
  - secrets (1129-1148);
  - the cut-over block's 8 "enroll/check/leave exit 1, nothing reached the hub", which become the pointer's own assertions.
- **(b)** About 13: the rename's seats, members, send and retire (279-352). Only the `is_self` part is twinned (`test_rl10::test_a_welcome_that_renames_the_machine`).
- **Setup-only.** These use `hub enroll` only so that `project init --hub` works:
  - hub projects 466-556 (30);
  - the conversion race 557-762 (21);
  - the cut-over block's other ~14.

**`test-sync.sh` (~116): about 48 go, about 53 re-pointed, about 15 stay.**
- **(a)**
  - codes and nonces;
  - dropped, 503 and silent streams;
  - hub.json changes;
  - parts (the downward half is twinned);
  - hb-ack;
  - forgeries and seen-nonce (727-835).
- **(b)** Two-machine sync:
  - bootstrap;
  - `rejoin_former` and `notice_former_writers`;
  - cross-machine members, states, says and titles;
  - restart resync;
  - "no longer a hub project" (`EndStream`);
  - presence before uploads;
  - delivery past spent positions;
  - too-large and resend not followed (836-861).
- **(c)** Gamma (868-950), which already runs on RL10 with a git mirror.

**`test-archive.sh` (~67): about 7 go, about 37 re-pointed, about 23 stay.**
- **(a)**
  - "keeps each imported event's code";
  - "one hello per POST";
  - the direct-stream `state-unavailable` retry (366-398).
- **(b)** Designation off, on, moved and cleared; git never feeding the log; steering protection; a rejected push retried; a repeated hello (195-457).

  One RL10 machine is enough: the endpoint stand-in's `archive` flag designates it, and `arriving` brings another machine's events.

  Two in-process cases construct a coded `HubLog`; flip them.
- **(c)** Gamma (458-575). Its setup runs `hub enroll` (467).

**`test-org.sh` (~89)**
- **Setup-only, about 35:** `hub enroll` at 189.
- **(b) on one RL10 machine, about 18:** follow vs held, `org.json`, retire then re-follow (390-429, 503-525).
- **(b) needing a second machine, about 24:** beta follows alpha's stray; the `projects`/`machines` tables (430-502).
- **(c):** not enrolled (179-186, 364-389).
- Line 373 expects "(sminos hub enroll)".

**`test-address.sh` (~84)**
- **(b), about 69:** two machines through the hub (159-388).
- **(c), about 15:** "the logs alone" (389-505).

**`test-broadcast.sh`**
- **(b), about 67:** two machines (177-369).
- **(c), 5.**

**`test-remote.sh`**
- **Setup-only, 43:** `hub enroll` at 192.
- **(b), about 10:** a stray moving at enrollment; the hub registering under the basename (350-398).

**`test-join.sh`**
- **Setup-only, about 86:** `hub enroll` at 185.
- **(b), 15:** two machines (601-670). Only "beta reads" ×2 needs a second machine; the `org`-frame retirements fit one.

**Setup-only, hub.json as a marker:**
- `test-who.sh` (46), `test-guide.sh` (about 70);
- `test-smns-guide-hook.sh` (8, plus the hub.json leg of its gate loop);
- `test-bridge-export.sh` (about 6).

**Core cases**
- `codes_parity` (4745) loses about 141 lines. Everything else in the core part is (c), including the identity.json cases (3141-3200, 5526-5562, 6522-6566) and the h1/h2 git-mirror pair.

**`tests/mods`**
- The TypeScript tests are clean.
- `live-resume-check.py` (136-170) builds coded `Rpcs` and seals RPCs. With §0.7 it goes; otherwise it is re-pointed.

### 2.3 Benches, the conformance replay, and the opt-in local-hub modes

- **`bench_rig.py` is DX2 throughout, not just `Local`.**
  - DX2: `Standin` (289-311) is `hub_standin` with a DX1 hub.json; `Local` (313-386) is MAWS's DX2 local hub through `hub enroll`; `Rig.build` (657-700) always enrolls at one of the two.
  - The rest is hub-independent: `line_key`, `install_tee`, `synthetic_transcript`, `FakeKind`, `LiveKind`, `probe_gaps`.
  - RL10 has no browser-side hub to re-point it at. So `Local` goes, and the rig goes with `hub_standin` unless someone wants a rig on the endpoint stand-in.
- **`test_session_plane.py`, `test_rpcs.py` and `test_policy_requests.py`'s Uplink classes** are parameterised over `StandinHub` and **`LocalHub`** (`DESK_HUB`). Both are DX2, so both modes go. The (b) Uplink tests are re-pointed through `endpoint_standin`'s `ep.send` instead.
- **`bench_open.py`:** `--uplink` (either hub) and the `held` scenario (748-810: the pause proxy and a sealed uploader) go. `--micro` stays.
- **`bench_scale.py`**
  - Non-`--rl10` `run` (435-500, `import_burst` 399-433) and `opens` (697-730 onward) are DX2 and go.
  - `tick`, `profile`, `verbs` and **`run --rl10` stay**. But the machine build writes a DX1 hub.json (277-280), and `--rl10`'s probe takes its first welcome's name from it.
  - With §3's change, have the build set `DAEMON_HOST` or write identity.json. Make `--rl10` the default, or drop the flag.
- **`measure_pages.py`:** part 1 (in-process) stays. Part 2 runs through the uplink against `hub_standin`; it goes, or is re-pointed at the endpoint stand-in.
- **`bench_index.py`** stays. **`bench_codes.py`** goes.
- **`rl10_conformance.py`** stays.
  - It stages hub.json with the DX1 key (458-465) and a DX2-era ledger entry. MAWS's byte-for-byte fixture plays `legacy-key?`/`legacy-key` (cases 1-2) and "a DX2-era entry answers none" (case 11).
  - Keep the key in hub.json, and keep the ledger's nonce-keyed path.
  - Move the machine's name to `DAEMON_HOST` (`rl10-host`) when `machine_identity` stops reading hub.json.

### 2.4 Shared behaviours covered only through DX2 (the gaps a straight deletion opens)

Shell:
1. The uplink child's supervision, and delivery while the tick is stuck (test-uplink 275-573).
2. A machine's former name: `rejoin_former`, `notice_former_writers`, and seats/send/retire after a rename (test-sync 319-444; test-hub 279-352).
3. Two-machine sync: bootstrap, members and states, says, titles, restart resync (test-sync).
4. A project leaving the hub (test-sync 611-650).
5. Machine presence and hello-before-upload (test-sync 690-726; partial in `test_rl10`).
6. The archive's designation, git never feeding the log, steering, push retry (test-archive 232-457).
7. The org directory on the uplink side (test-org 390-525).
8. Cross-machine addressing and scoped broadcast (test-address 203-388, test-broadcast 229-369).
9. Repository-by-remote across machines (test-remote 350-398).
10. join/move reaching another machine (test-join 601-670).
11. Too-large refused, and the resend not followed (test-sync 836-861).
12. Open latency through the real uplink (`bench_open --uplink`, `bench_scale opens`, `measure_pages` part 2).

Python:

13. The session plane through the real uplink (`test_session_plane::Uplink`): rows, diff, output, read, unsubscribe, reload, ended paging, reconnect, presence, mode, warmer.
14. The RPC checks (103 Checks), and executed-once across a cut or restart (`test_rpcs::Uplink`).
15. The keyless `Requests` relay: reconcile, raise again, relayed once, the outbox, owed across a restart.
16. `Link`'s `settle_marks` retry, the outbox drop retry, `UPLOAD_AHEAD` pacing.
17. Withheld handling and all of Restate (`test_withheld`).
18. `archive_have`/`copy_log` (`test_reach` Admitted); a void from elsewhere; the #147 queue under the enrolment trigger; `taken` bounds; HotLooks; the unlisting projection.

**How to close them: one machine, other machines' events injected.**
- Most of these need no second machine: other machines' events can be injected with `endpoint_standin`'s `arriving`, `echo`, `resend`, `refuse` and `send`. That covers 1, 2, 4-7, 11 and 13-18, and the resolution and recording halves of 8-10.
- What only two machines prove end to end is a delivery from one sminos to another. On RL10 that crosses MAWS's relay (RL1), not sminos code. sminos's contract ends at the socket, and MAWS's `e2e:remote` already drives two machines.
- So I would not build a two-machine RL10 relay stand-in. Its only gain would be testing MAWS's relay inside sminos's suite.
- If the owner wants sminos-side two-machine proof anyway, the rig is a relay serving two endpoint directories. It re-sends what one accepts as `arriving` on the other, merges `have`, and forwards `org` and the session lane. That is new test infrastructure, a few hundred lines.

### 2.5 hub.json as a fixture in RL10 suites

Most RL10 Python suites write hub.json to give the machine its name ("testhost") and org before a welcome cuts it over:
- `test_words.Machine.setUp` L134, inherited by `test_reach_gate`, `test_visibility`, `test_withheld` and `test_streams`;
- `test_owed.Machine.enrol` L106;
- `test_heads.Machine.enrol` L65;
- `test_reach.Plane.setUp` L384;
- `test_rl10.Machine.hub_json` L99;
- `test_snapshots` L119;
- `test_holder_deliveries.Rig` L88;
- `test_scale` L32;
- `test_org_retired.Hub` L156;
- `test_visibility.Unlisting.reader` L728.

Shell suites do the same through `hub enroll` or a written hub.json: who, guide, remote, join, org, smns-guide-hook, bridge-export, archive, the test-hub setup.

Once §3's change lands, these need a shared helper that writes identity.json, or sets `DAEMON_HOST` before the welcome. **That is not a plain swap.** A machine cut over behaves differently:
- operator `say`/`send` become words-gated ("the endpoint decides its delivery");
- peer pushes are held until `daemon/audiences.json` holds a welcome's capabilities;
- a hub project's host events go to the host store.

So:
- Suites that only read identity can swap the file.
- Suites that assert delivery need the endpoint stand-in answering verdicts, or a kept `audiences.json`: test-hub's rename, test-join's local sends, test-org's say.
- Suites that model "enrolled at a hub but not cut over" must choose cut over or not enrolled, since that state no longer exists: most of `test_owed` and `test_holder_deliveries`, `test_words` L547 and L1429, `test_policy_requests` Delivery/Refusals.

`test_policy_requests` Delivery/Refusals are the only coverage of read-only refusals at `deliver_next`. Keep them as not-enrolled machines, where delivery is ungated.

## 3. `hub.json` and `sminos hub enroll`

### Writers

- **`sminos_hub.enroll`** (`sminos_hub.py:410-421`) writes `{hub, org, machine, client_id, client_secret, key, former, enrolled}` at 0600, under `credential_lock`, after `sminos.mark_enrolled`.
- **`sminos_hub.leave`** (`:604-611`) removes the file.
- Nothing else in sminos writes it. In production, B4 step 5 removed it by hand on all three machines (DL 239 and 242).
- Test fixtures write it widely to make a machine look enrolled. Section 2 counts them.

### Readers

| # | Reader | What it decides | After the removal |
|---|---|---|---|
| 1 | `sminos.enrollment` `sminos.py:815` | Whether the machine is enrolled, and its org and hub URL. Feeds `hub_here` (which .smns hub projects sync here), the machine's own project, `machines`, and the daemon's and `owed`'s upstream. | identity.json alone. |
| 2 | `sminos.enrolment_stamp` `sminos.py:2010` | `(name, enrolled)`, which `waits_for_head` compares with `daemon/heads.json` (#147's operator-writer queue). | identity.json alone. |
| 3 | `sminos.machine_identity` `sminos.py:8773` | This machine's name and former names: every writer's name, `host_name`, `is_self`. | identity.json, else `DAEMON_HOST`, else the host name. |
| 4 | `sminos_daemon.enrolled_at` `:757` | `notice_former_writers`' "since". | identity.json alone. |
| 5 | `sminos_daemon.credential_bytes` `:1562` → `uplink_wanted` / `uplink_change` | Runs DX2. | Delete. |
| 6 | `sminos_daemon.uplink_status` `:2028` | The status line "uplink: running" on DX2. | Delete the line. |
| 7 | `sminos_daemon.enrollment_inspected` `:2345` | `daemon owed`'s unreadable-enrollment check. | identity.json alone. |
| 8 | `sminos_uplink.load_credential` `:208` (`hub_admitted`, `credential_path`) | The DX2 credential: hub URL, Access token, org key. | Delete. |
| 9 | `sminos_uplink.Link.on_legacy_key` `:1931` | `org` and `key`: the DX1 key handed over at RL10's `legacy-key?`. | **Keep** (below). |
| 10 | `sminos_hub.held` 247, `stored` 553, `enrolled_hub` 275, `show` 434 | `enroll`'s "already enrolled", `check`/`leave`'s credential, `project init --hub`'s org, `hub show`. | `held` and `stored` go; `enrolled_hub` and `show` read identity.json alone. |
| 11 | `sminos_rl10.welcomed` `:406`, through #3 at the first welcome | The name and former names copied into identity.json; the rename check. | Follows #3. |
| 12 | `hooks/smns-guide.sh:15`, `hooks/smns-record.sh:34` (existence only) | Enrolled: guidance is printed, and every directory is a project. | identity.json alone. |
| 13 | devcloud `sminos_host._identity`/`at_hub`/`hub_json`, `departure.py:385` | "Enrolled on DX2", and which `hub` verbs to run. | devcloud's own commit (section 1.11). |
| 14 | `tests/rl10_conformance.py:457` `stage_machine` | The replayed machine's name, through #3, and the legacy key, through #9. | Name through `DAEMON_HOST`; the file kept for the key. |

**DL 231's hubless gate reads none of these.** `widening_through_app` and `reach_capable` key on identity.json and the `record` capability `audiences.json` keeps. DL 235 made that the rule ("Decision Log 231's exception becomes 'not cut over'"), and 1.39.0 built it.

### Recommendation: reduce

sminos stops treating hub.json as an enrollment or a credential. It never writes the file again, and nothing reads it but `on_legacy_key`, which reads `org` and `key` alone.
- `enroll`, `check` and `leave` lose their code.
- `hub show` prints identity.json. On a machine not cut over it says the enrollment is the endpoint's (`mawsd endpoint enroll`), that sminos takes it at the endpoint's first welcome, and exits 1.
- `hub enroll|check|leave` keep the one line every cut-over machine answers with today (`refuse_cut_over`'s "this machine's enrollment is its endpoint's: `mawsd endpoint enroll|status`"), exit 1.

Why not remove hub.json entirely now:
- MAWS's RL10 conversation fixture, case 2, has the endpoint ask `legacy-key?` and expects sminos's `legacy-key {org, key}` back. `rl10_conformance.py` replays every line as written, so dropping the answer turns the replay red.
- In production the ask never fires. The endpoint asks only while its `legacy.json` holds no key and the org state has not retired it (MAWS `src/endpoint/rl10/link.ts:497`), and production reads `legacyRetired` (DL 239).
- So hub.json goes for good once MAWS drops `legacy-key?` from RL10 and the fixture. That is a follow-up for O14 and O10's fixture, not part of this ticket.

Why the verbs keep a pointer and are not deleted outright:
- On every production machine `hub enroll|check|leave` already answer exactly that line and exit 1. Making it unconditional changes nothing anyone runs, and it leaves a person typing the old command a way forward.
- Deleting them, so `sminos hub` gives a usage error except `show`, is sound too if a smaller surface matters more than the hint. It also makes devcloud's dead path fail with exit 2 instead of 1.

What this means for DL 231's hubless rule:
- After the removal, "enrolled" and "cut over" are the same fact (identity.json in the same sminos home as the records). DL 231's intent and DL 235's wording therefore coincide: a machine never welcomed by an endpoint keeps the terminal gate.
- A cut-over machine whose endpoint has not advertised `record` keeps it too, unchanged.
- A stray hub.json no longer counts as enrolled anywhere. That includes the hooks, so a hand-made hub.json can no longer make the hooks treat a hubless machine as enrolled.
- Record in O18's notes that the gate reads identity.json, as it already has since 1.39.0, and that hub.json plays no part.

What the reduction costs in tests: every fixture that wrote hub.json to name or enroll a machine must write identity.json or set `DAEMON_HOST` instead. `rl10_conformance.stage_machine` is the delicate one: its staged sessions are written under `machine_identity()`'s name before the first welcome, so the name must still come out as `rl10-host`.

## 4. Board #149 on RL10

#149 is a board ticket, not GitHub #149 (that is an Arkho mirror about api renewals). It is **done**: merged as PR #424, sminos 1.27.2. It relates to #153.

**Its failure mode is not DX4's alone, and it does not end with this removal.**
- The session lane it protects is RL10's too: `raised` and `pending` cross the socket, and the endpoint relays them (plane A's cards).
- The fix is `sminos_requests.shown_input` with `RAISED_INPUT_MAX` (256 KiB) and `INPUT_CAP` (`sminos_requests.py:96-167`). It runs where the raise is framed, independent of the carrier, so it stays as it is.

What actually closes the lane on RL10:
- **No single line can.** sminos writes no line past 1 MiB: `SocketLane.send` goes through `to_wire`, which splits a frame into `part`s. The endpoint reassembles them (MAWS `src/endpoint/rl10/server.ts:271-283`), and closes only on a single line over `LINE_LIMIT` (1 MiB), which sminos never sends.
- **`SocketLane`'s own bound does.** More than `SEND_QUEUE_MAX` (16 MiB) unsent raises `NotDelivered` and reconnects (`sminos_uplink.py:1199-1206`). That is the same constant as DX2's `Sender`, so the 256 KiB cap keeps one raise as far from it on RL10 as it did on DX2.
- **The endpoint's side.** The endpoint drops a connection whose sminos has taken nothing for 64 MiB (`UNREAD_LIMIT`). That is the endpoint's to bound.

#149's logged residue still applies on RL10 unchanged: a reviewer's P2 noted that a project's complete `pending` set passes 16 MiB at about sixty requests at the bound. The set goes as one frame (as parts) on the one lane. Keep that residue entry, and reword it from "DX2's lane" to "the RL10 lane".

**Tests.** `test_policy_requests.py`'s `Requests.test_an_input_past_the_lanes_bound_goes_cut_and_marked_and_its_draw_decides_it` (1319) checks both carriers in one test:
- the DX2 half: `Requests(KEY, …)` and `codes.verifies(KEY, "raised", …)`;
- the RL10 half: `Requests(None, …)`, "RL10: the same body, as a draft".

Once the removal goes in, only the RL10 half stays. Rewrite the test around `Requests(machine)`, drop the `codes.verifies` assertion, and keep the digest checks.

## 5. Commit order

Each step below is green on its own. One rule holds them together: coverage moves to RL10 first, and the code leaves after. A single PR or a short stack both work.
- The sminos version-bump gate checks each PR (`scripts/bump-version.sh --plugin sminos --since origin/main`). Bump sminos once per PR that ships to a session.
- Steps 1-2 touch only `sminos/tests/`, which `.version-bump.json` lists as `unshipped` for sminos (`tests/*`, beside `CLAUDE.md` and `README.md`), so they need no bump. Steps 3-6 change shipped code, `SKILL.md` and `references/`, so they do.
- A minor bump (1.40.0) fits a removal that no running machine notices. A major is defensible because CLI verbs change meaning; that is the owner's call.

### 0. devcloud's DX2 enrollment out (own PR, devcloud bump)

- Remove `sminos_host.enroll` with its `hub check`/`hub enroll` calls, `at_hub`'s hub.json leg, `departure._endpoint_leave`'s `hub leave` arm, `DEVCLOUD_SMINOS_SECRET`, `[desk] provisioning_secret` (v1), `--enroll-code`/`enroll-code`, and README 505-535.
- devcloud's tests use their own fake sminos, so this step's order against the sminos steps is free.
- Land it before step 5, so that no released sminos answers a verb that devcloud still calls.

### 1. The opt-in local-hub modes out (tests only)

- `LocalHub`, `make_hub`'s local arm and `DESK_HUB` in `test_session_plane`, `test_rpcs` and `test_policy_requests`.
- `bench_rig.py`'s `Local`/`LocalBrowser`, and `bench_open`/`bench_scale`'s `--hub local`/`--maws` flags.
- CI never runs these modes, so nothing can turn red.

### 2. Re-point shared coverage at RL10 while DX2 still runs (tests only, several commits by area)

- **Unit flips with no transport behind them.**
  - `test_rpcs` Checks (103) onto `remote_mode()`;
  - `test_policy_requests` Requests (21) onto `Requests(None)`;
  - coded `HubLog`s in `test_owed` (12), `test_reach` Admitted (10), `test_scale` (10) and `test_heads` (10);
  - `test_session_plane` Lifecycle's three `Link` fakes onto `coded=False`.
- **Endpoint stand-in ports, one machine with injected arrivals.**
  - `test_withheld` Dx2 and Restate (18);
  - the Uplink classes of `test_session_plane` (12), `test_rpcs` (6) and `test_policy_requests` (4);
  - `test_visibility` Unlisting (2);
  - test-uplink's supervision cases (about 60) onto its RL10 block;
  - test-archive (about 37) on the stand-in's `archive` flag;
  - test-org's one-machine cases (about 18);
  - test-sync's former-name, leave, presence, spent and too-large cases;
  - the resolution and recording halves of test-address, test-broadcast, test-remote and test-join.
- **The owner decides here** what to do with the truly two-machine end-to-end assertions (§2.4). My recommendation is to leave them to MAWS's `e2e:remote`, not to build a relay rig.
- The new tests sit beside the DX2 ones, so the step is additive and green.
- Expected size: the bulk of the work, about 220 Python tests and about 200 shell assertions rewritten.

### 3. The DX2 transport and the supervisor's DX2 arm out

Code:
- `sminos_uplink.py`'s (a) list (§1.1);
- `cmd_uplink`'s credential branch;
- `sminos_daemon`'s `credential_bytes`, `LEFT_THE_HUB`, `uplink_wanted`/`uplink_change`'s `dx2` arms and `uplink_status`'s hub.json line.

Tests:
- `test_happy_eyeballs.py` (−1 `run_suites` line);
- test-uplink's (a) about 93;
- test-sync's about 48;
- test-archive's about 7;
- `test_session_plane`'s Instruments, Lanes, BenchOpen, the Lifecycle DX2 cases and Uplink `h`/`i`;
- `test_rpcs` Uplink `f`;
- `test_policy_requests` RelayedOnLanes (6);
- `test_reach` HubStandin (10);
- `test_org_retired` Hub (4);
- `test_scale` OrgAhead and BenchStops;
- `test_visibility` L1178;
- the DX2 halves of the parameterised Uplink classes.

Delete with them:
- `hub_standin.py`, `pause_proxy.py`, `bench_rig.py` (or keep its hub-independent helpers), `bench_codes.py`;
- `bench_open --uplink`/`held`, `bench_scale run` without `--rl10` and `opens`, and `measure_pages` part 2.

**Risk: any surviving test or bench that still spawns `hub_standin.py` goes red in this step.** Before committing, grep the tree for `hub_standin`, `Stream(`, `Sender(`, `load_credential` and `run_dx2`.

### 4. Collapse `coded` (behaviour-neutral on RL10)

Code:
- `HubLog`, `refusal`, `take`, `same`, `uploads`, `presence`, `on_refused`;
- `Rpcs` (key, coded, `RPC_NAMES`/`RL10_ONLY`);
- `Requests` (key; `uncoded` becomes the restore path);
- `outcomes.message`;
- `Link`'s `coded` and `transport` params;
- `Plane`'s `host`/`launches`/`kinds` and `Rpcs.kinds`;
- `hublog.machine_policy` and `policy.machine_policy`;
- the DX1 MAC half of `sminos_codes`.

If §0.7 is decided "delete": `resume`, `retire`, `launched_by` and `steer_without_bridge`, with `test_rpcs` j×14, k×5, LaunchStart (3) and the retire half of `test_g`, plus `live-resume-check.py`.

Tests:
- `test_rpcs` `test_a_bad_code` and "no `op` listed";
- `test_reach` Retry L601 and Dead L737;
- `codes_parity` (−141 core lines) and `dx1-codes.json`'s MAC vectors.

The proof that this step changes nothing on RL10: `rl10_conformance.py`, `test_rl10`, `test_words`, `test_reach_gate` and `test_visibility`, untouched and green.

Risk: scope creep. Leave the always-empty `refused` map and the no-op `hold`/`release` gates in place, or collapse them in a separate commit. They thread through four modules.

### 5. `hub` verbs and hub.json reduced

Code:
- `sminos_hub` cut to `show` (identity.json only), `enrolled_hub`, `add_hub`, `credential_lock` and `sessions_under`, plus the pointer for `enroll`/`check`/`leave`;
- `sminos.enrollment`, `enrolment_stamp`, `machine_identity`, `sminos_daemon.enrolled_at` and `enrollment_inspected` read identity.json alone;
- `hooks/smns-guide.sh` and `smns-record.sh` test identity.json alone;
- `on_legacy_key` keeps reading hub.json's `org` and `key` alone.

Tests:
- test-hub's about 455 assertions, `enroll_parity.py` and `dx7-enroll-codes.*`;
- `test_heads` (5), `test_owed` (3);
- a shared identity.json helper for every fixture in §2.5, plus the endpoint stand-in or a kept `audiences.json` where delivery is asserted;
- the setup-only shell suites;
- `bench_scale`'s machine build;
- `rl10_conformance.stage_machine`'s name via `DAEMON_HOST`.

**Risk, the most delicate step:**
- Every fixture that relied on "enrolled, not cut over" changes behaviour.
- `rl10_conformance` must still produce `rl10-host` writers and answer `legacy-key`.
- Run the conformance replay and `test_words` first.

### 6. Docs, labels and the bump (§6)

- `run_suites` labels.
- `C`, `setup.md`, `SKILL.md` (a skill edit: a sanity read through `doperpowers:writing-skills`), README, `whats-inside.md`, `INSTALL-doperpowers.md`, `TECH-DEBT.md`.
- Bump sminos here, or in the PR's first shipping commit.
- In the PR body, quote the per-file removed counts from §2.
- Outside sminos: MAWS's `apps/desk-hub/deploy/README.md:173` still tells a person to run `sminos hub enroll`. That is MAWS's to fix.

### Follow-ups this ticket does not close

- **hub.json's last reader goes once MAWS drops `legacy-key?` from RL10 and its conversation fixture** (O14 M5a's retirement already holds in production).
- **A fenced Resume, Retire and Stop**, if MAWS ever offers them (O10 Interfaces §G).
- **#149's residue** (a complete `pending` set past 16 MiB) stays logged, now against the RL10 lane.

## 6. Docs to update

Biggest first. `C` is `sminos/skills/sminos/scripts/CLAUDE.md`, where each paragraph is one long line.

### 1. `C` L7: the hub-project paragraph

Rewrite the lead sentence. Today it reads: "on a machine enrolled by `sminos hub enroll` … `daemon uplink`, a child process holding the hub's stream, which uploads … sealed with authentication codes and verifies every event". It should say the project syncs through the endpoint over RL10, the machine enrolled by mawsd.

The same paragraph also needs these changes:
- Cut "each only to a hub whose welcome lists its kind" (the `kinds` filter).
- Change "sent again until the hub acknowledges it" to say the endpoint.
- Reword the nonce-keying clause, but keep that DX2-era ledger entries answer none.
- Keep the session plane, RPC and policy text as it is: all of it is RL10's.

### 2. `C` L11: the cutover paragraph

Split it into what stays and what goes.

What stays:
- `rl10.json` discovery, the probe, the whole welcome, and identity.json;
- revoked.json, the policy, the conformance replay, `spent`;
- the RPC binding and fence.

What goes:
- "Before the cutover … beside the hub's uplink and never in its place … leaves the hub's stream as it is";
- "the hub's uplink is stopped";
- "DX2's parts beyond";
- "`hub enroll`, `check` and `leave` exit 1 there": this becomes the general rule;
- "after which the supervisor runs DX2 from hub.json … (test-uplink.sh pins both orders)": becomes "the next probe cuts it over again";
- the `coded=False` and `same_uncoded` contrast: becomes the only description;
- "go as drafts (`Requests.seal`, `outcomes.message` with no key)";
- "`Rpcs(..., coded=False)` skips the code check alone";
- "The DX2 path carries no context, binding or proof, and runs as before."

Keep "`legacy-key?` is answered from hub.json's key", as the one remaining use of hub.json.

### 3. `C`: the other paragraphs

- **L55 (the file map).**
  - `sminos_hub.py`: what is left of it.
  - `sminos_uplink.py` and `sminos_hublog.py`: drop the two HTTP sender lanes, POST 200, "DX2's `refused`, MAWS #88" and the TLS-handshake text.
  - `sminos_requests.py` and `sminos_outcomes.py`: they no longer send "the hub's sealed messages".
  - `sminos_codes.py`: now canonical JSON and base64url.
  - `bench_scale.py`: the default mode now drives the endpoint stand-in. Its `--rl10` flag goes, or becomes the default.
- **L9.** Drop "where on DX2 an old one means a silent stream".
- **L17 (`daemon owed`).** Drop "the hub or" and "identity.json or hub.json".
- **L19.** Drop `hub enroll --replace`, "So `hub enroll` and a welcome …", "the hub's backlog imported on DX2", and "`hub leave` before the first `have`". Rewrite around the endpoint's welcome alone.
- **L23 (end).**
  - Drop the direct-stream `state-unavailable` pause and "a hub tombstone arriving on DX2".
  - "The stand-ins: `hub_standin.py` …": only `endpoint_standin.py` remains, once `hub_standin.py` goes (section 2).
  - Re-list the tests.
- **L36.** Change "(no hub, so no welcome)" to "never welcomed by an endpoint".
- **L44.** Cut ", a hub tombstone on DX2,".
- **L59.** Drop hub.json from the stat-cached files and `credential_bytes` from the loop's polls.

### 4. `sminos/skills/sminos/references/setup.md`

- **L67-132, "## The desk hub".** This is the user-facing dead path:
  - `hub enroll`/`show`/`check`/`leave`;
  - Machines → Enroll a machine;
  - `$SMINOS_HOME/daemon/hub.json`;
  - `smns-provision-v1.` and `printf %s "$CODE" | sminos hub enroll`;
  - `hub check`'s exit table and boot rule;
  - `hub leave`.

  Replace it with a short "enroll the machine with mawsd; sminos's daemon follows at the endpoint's first welcome (`sminos hub show`, `sminos daemon status`)". Keep the `project init --hub` and org-follow paragraphs.
- **L3-4.** Reword.
- **L147-149.** "the one stream to the hub" becomes "the one RL10 connection to the endpoint".
- **L151-167.** Drop "the hub or" from `daemon owed`.

### 5. `sminos/skills/sminos/SKILL.md`

- **L3 (description, auto-trigger).** Drop "enrolling a machine at the desk hub".
- **L210-215.** Drop "enrolling a machine at the desk hub (by hand, or unattended through a provisioning key), checking and ending its enrollment". This is a skill edit, so it falls under the repo's skill-change rule (`doperpowers:writing-skills`). It is a deletion of a dead path, so a sanity read is enough.

### 6. Other sminos files

- **`sminos/README.md`** L7 and L33-34: "a desk hub", "enrollment at the desk hub".
- **`sminos/CLAUDE.md`** L9: "enrollment" is no longer sminos's setup.
- **`sminos/CLAUDE.md`** L11: the DC4 uplink plan is cited as "the hub side". Mark it superseded.
- **`sminos/hooks/CLAUDE.md`** L7: `hub.json` or `identity.json` becomes identity.json. The same goes for the comments in `smns-guide.sh:2-15` and `smns-record.sh:22-34`.
- **Module docstrings:**
  - Rewrite: `sminos_uplink.py` 1-114, `sminos_hub.py` 1-49, `sminos_hublog.py` 1-98 (the DX1 sealing, `bad-code`, `seen-nonce`, the coded/uncoded contrast, the direct stream, `ASK_MS`).
  - The code-check paragraphs: `sminos_rpc.py` 1-210 (check 1, the `coded` contrast, "DX2 refuses it `unsupported`").
  - "sealed with the org key" and "Nothing leaves this machine without its code": `sminos_requests.py` 1-62, `sminos_outcomes.py` 51-53.
  - `sminos_owed.py` 2-19 (POST 200, `not-open`).
  - "DX2's session frames" and the `kinds` gate: `sminos_plane.py` 1-6 and 169-170.
  - "in place of DX2 to the hub" and "before hub.json": `sminos_rl10.py` 6-31.
  - "no desk hub" and "the uplink to the desk hub": `sminos_daemon.py` 4-8 and 49-55, plus the supervisor docstring 1613-1636.
  - `sminos_codes.py` 1-31.
  - `sminos_policy.py:111`, `sminos_audience.py:188`.
- **`sminos.py`:**
  - usage 92-94 (`sminos hub enroll … | show`);
  - the hint at 954-955 and the `machines` line at 11832 ("(sminos hub enroll)");
  - the 8776-8777 docstring and the 2217 comment;
  - the parser comment 12773-12777.
- **`tests/run-sminos-tests.sh` `run_suites` labels (393-412).** "the uplink to the hub", "past a blackholed IPv6", "enrollment and hub projects", "the hub stand-in's M1 rules". Change them with the tests they name.

### 7. Root and repository docs

- Root `README.md:105` ("a git mirror or a desk hub").
- `docs/whats-inside.md:88` ("through a git mirror or the desk hub").
- `docs/INSTALL-doperpowers.md:62` ("an enrollment at the desk hub").
- The root `CLAUDE.md`'s sminos row needs nothing.
- `docs/doperpowers/TECH-DEBT.md`:
  - Delete T3, the uplink POST past its 60 s deadline (≈292-301).
  - Delete the section "the desk hub and many projects in one POST" (≈646-650).
  - Drop the `test-uplink.sh` speed-claim bullet (≈270-272).
  - Reword `spend_own`'s "lying hub" to "endpoint" (≈303-310).
  - Delete the struck `hub_standin` entry (≈570-575), or leave it as history.
  - Revisit the devcloud desk-key expiry item (≈689) with devcloud's commit.
  - Reword #149's residue to RL10's lane.

### 8. devcloud (its own commit)

`devcloud/README.md:505-535`, 616 and 661: the `sminos hub enroll` / `hub show` walkthrough, and `--enroll-code`.

### What needs nothing

The design history under `docs/doperpowers/{plans,specs}`. Optionally add a one-line "superseded by RL10" note to `2026-10-15-desk-dc4-uplink.md`, which `sminos/CLAUDE.md` cites.
