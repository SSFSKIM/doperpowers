# Code map: a channel as a log with declared, plural membership

> Research for `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, kept as it was written,
> before the design's later revisions. The spec is the authority: this map's §6 ("the smallest coherent
> implementation") and its table of hard items were overturned in part (no declaration record, `join` keeps its
> meaning, membership is a statement in the member's own project log). It is kept for what it locates in the code
> at the two commits named below; line numbers have moved since, function names mostly have not.

**What was read** (2026-11-17)
- doperpowers `main` at `601b8e9d`. Paths are relative to this repository's `sminos/`; `S/` = `skills/sminos/scripts/`.
- MAWS's trunk at `77af813a4` (2026-11-16). Paths are relative to that repository.

**Who read what**
- I read the sminos side.
- A subagent mapped the MAWS side. I re-read five of its load-bearing citations and they match the code: `registry.ts:726-746`, `notify.ts:185`, `project-registry.ts:219`, `members.ts:47-52`, `project.ts:69`.
- **[read]** = seen in code. **[inf]** = my inference.

## Headline

1. **The log plane is already almost channel-shaped. [read]**
   - The hub creates a log for any lowercase-UUID id a machine `hello`s. It inserts it as `kind='hub'` and checks nothing else (`apps/desk-hub/src/objects/registry.ts:726-746`; grammar `apps/desk-hub/src/objects/project.ts:69`).
   - A session already writes under its writer `<machine>/<session>` into logs it is not a member of: a cross-project `say`, and its copy into the home log (`S/sminos.py:6578` `record_copy`, `6771` `cmd_say`).
   - Every log-plane key, on both sides, is per project:
     - `(project, writer, seq)`;
     - delivery records;
     - receipts;
     - words?/reach? asks;
     - the bridge's delivery mark `<project>/<writer>` (`hooks/mods/bridge.tsx:1231`).
   - Membership of N logs changes none of these keys.

2. **sminos enforces "one project per session" in three places, not throughout. [read]**
   - Resolution returns one project: `S/sminos.py:2622-2659` `session_project`/`_session_project` (the override, else the launch directory).
   - The override file holds one id: `S/sminos.py:2564-2590` (`sessions/<sid>.json {"project"}`).
   - Reconciliation retires every membership that is not the resolved one: `S/sminos.py:4349,4354` → `retire_moved` `4416`, written as `retired` with reason `moved`.
   - Everything else is computed per log and keyed `(project, session)`: views, delivery, chat, presence, subscriptions.

3. **The wire carries one project per session. These shapes are contracts.**
   - RL10 `member` [read]:
     - `S/sminos_uplink.py:698` sends `"project": pid`.
     - A session in two projects' rows "is sent for the first" (`S/sminos_uplink.py:1793`, `1833`).
     - MAWS `Member.project: string` is keyed by session (`src/endpoint/rl10/members.ts:47-52,131`).
   - Signed listings carry `fields.project` [read]. Sources: `apps/org-protocol/src/types.ts:119-127`, and the hub's `listings (machine, session)` primary key with one project column (`apps/desk-hub/src/objects/org-records.ts:59-61`).
   - Notify and pending carry `project` [read]: `apps/org-protocol/src/relay.ts:140,150`; `relay_pending (session PK, project NOT NULL)`.
   - The app's rows hold one project each (`src/main/org/rows.ts`) [read].
   - The app's project list drops every project with no location (`src/main/org/project-registry.ts:219`) [read].

4. **Nothing durably says that a log exists apart from a folder. [read]**
   - The registry's minted id exists only when anchored to a folder (`src/services/index/statements.ts:280-284`).
   - The only location-less form is `known`, which is transient and held while sessions run (`apps/org-protocol/src/types.ts:178-179`; `src/endpoint/registry.ts:236-243`).
   - `OrgState.projects` is reserved and nothing writes it (`types.ts:86-90`).
   - A declared channel therefore needs a new signed record. Its authority — who may assert a channel and its members — is the design's real open decision, not a code one.

5. **"A thread for every member" is the most hazardous part.**
   - A background resume is `claude --bg --resume <id> <msg>` with no flags; any flag starts a copy (observed v2.1.257; `S/sminos.py:10720-10725`, `11352`) [read].
   - A human-opened session resumed in the background therefore runs on its saved options, its permission mode included. A terminal session's saved options are rarely ones suited to running unattended. [inf]

---

## 1. One project per session

| Place | What it assumes | What plural membership requires |
|---|---|---|
| **Session record** `S/sminos_records.py` (no `project` field anywhere) | Nothing. Provenance, owners, and `access`/`shares`/`policyRev` are per session [read]. | No change. Policy and owners are already independent of the channel. |
| **Join override** `S/sminos.py:2564-2590` (`$SMINOS_HOME/sessions/<sid>.json {"project","at"}`; `override_of` returns one id) | One declared project that **replaces** the directory's [read]. | A set of declared channels **beside** the automatic one. Today `join` *moves* (`move_session` `S/sminos.py:12849-12866`: `retired moved` in the old log, `joined` in the new). |
| **`join` verb** `S/sminos.py:12869-12932` | `join <p>` moves; `--cwd` moves back. A seat is refused (`12907-12908`: "a seat's project is where it was spawned") [read]. | `join <channel>` adds and `leave <channel>` removes; seats may join. "Wrong project" (join as a correction) becomes either a separate verb or an override of the *automatic* channel [inf]. |
| **`join_refusal`** `S/sminos.py:2603-2619` | Target must be a hub project of this org, not `local-`, not retired [read]. | Holds for channels too. |
| **Resolution**: `session_project`/`_session_project` `S/sminos.py:2622-2659`, `record_project` `2700`, `seat_project` `2097-2132`, `caller_project` `2425-2435`, `last_project` `2665-2696` | Each returns **one** `Project` [read]. | Split into `home_project(session)` (today's rule, unchanged) and `channels_of(session)` (home + declared). Classify every caller as "the home" or "each membership". |
| **Reconciliation**: `_reconcile` `S/sminos.py:4310-4387`, `_local_sessions` `4286-4307`, `here_now` `4401`, `retire_moved` `4416-4434`, `moved_here` `4465` | A joined member whose resolved project is not this log is retired `moved` (`4349`, `4354`). A session counts as local evidence only where `record_project`/`seat_project` equals the log (`4295`, `4304`). The docstring treats dual membership as an artifact lasting one tick (`4335-4336`) [read]. | `_local_sessions` asks "project ∈ channels_of(session)". `retire_moved` fires only when the session leaves the automatic channel (its directory changed) or a declared channel is removed. **This is the core change.** |
| **Export target of the record hook**: `cmd_record` `S/sminos.py:7989-8020` → `record_session` `7711-7750` → `export_host` `7517`; bridge export `export_live` `7833-7862`; export position per project, `position_init` `7370` (`projects/<id>/cursors/export/<sid>`) | Host events (`message`, `question`, `answered`) and the export cursor go to the one resolved project [read]. | Keep exactly one home for them (§3). The hook joins on sight in every declared channel. |
| **Host store**: `append_host` `S/sminos.py:7640-7684`, `host_store_holds` `7601`, `HOST_STORE` `6965`, `host_events_of` `7687` | One store per project, `projects/<id>/host/<writer>.jsonl`, with the store's own seqs [read]. | Home only (§3). |
| **Session-start guide**: `guide_text` `S/sminos.py:12959-13030` (`13014`: "you are %s in project %s …") | One project and one reason [read]. | Name the automatic and declared channels, and how `say` picks one. The roster (`_roster_exchanges` `13037`) already takes a list of projects. |
| **`list` and its filters**: `list_scope` `S/sminos.py:12302-12326`, `cmd_list` `12654-12733`, `row_matches` `12329` | No filter means the caller's project (`view_projects("")`). Filters build rows per project, so a session in N projects shows N rows [read]. | Default to the caller's channels. `--org`/`find` dedupe by session, with its channels in one row. Today `one_per_session` (`6285`) dedupes only for addressing. |
| **Alias resolution and its namespace**: `_resolve_tag` `S/sminos.py:6365-6411`, `resolve_tags` `6413-6452`, `shadowing` `4666-4689`, `held_alias` `4642-4664` | A bare `@alias` resolves **only in the sender's project** (`6402`). Uniqueness (shadowing) is per project. `@short` and `@alias#short` are org-wide. One message reaches one project (`6451`) [read]. | A bare `@alias` resolves over the sender's channels, refusing ambiguity. Aliases are published per log, so per-log shadowing can give one session **different aliases in different channels**. Decide that an alias belongs to the session [inf]. |
| **`say` destination**: `cmd_say` `S/sminos.py:6771-6833` | An untagged `say` from a session goes to `caller_project`, and `--in` is refused for a session (`6780-6781`) [read]. | `say --in <channel>` (or a default channel) for a session in more than one channel. |
| **Delivery**: `deliver_next` `S/sminos.py:5313`, `push_event` `6071`, `push_member` `6485`; records `projects/<id>/delivered/<sid>.json` (`delivered_load` `3457`); bridge mark `<project>/<writer>` (`hooks/mods/bridge.tsx:1210-1231`) | Per (project, session) [read]. | Nothing structural. The daemon already walks every project's members. |
| **Lifecycle events**: `lifecycle` `S/sminos.py:4190-4233`. Daemon publishers `S/sminos_daemon.py:616` (`publish_state`), `646` (renames), `676` (titles), `718` (`rejoin_former`), each per project view. `in-charge`: `S/sminos.py:8185-8190`, derive `8612`. `status`: `12086`, `12109` | Membership is per log (`_memberships` `4389`, `_projection` `4880`). The daemon publishers already run per log. `in-charge` and `status` are written once, into the resolved project [read]. | `joined`/`retired` per log is already the model. `state`/`titled`/`renamed` become N× automatically [inf]. `in-charge`/`status` fan out, or are read from the home. |
| **Endpoint listings**: `src/endpoint/rl10/members.ts:47-89,131,171-195`; `link.ts:438-445` `sessionProjects` (session → one project, which feeds `known`); `link.ts:529-549` (lane A RPC uses `member.project`); `listings.ts:161-168,236-238` | One project per session; the last frame wins [read, via subagent]. | `member.channels[]`, a session → set map, and a spawn that names its channel (§6). |
| **App**: `src/main/org/rows.ts:8,24-26,620-623`; local `sessions.project_id` FK (`src/services/index/migrations.ts:46,55`); `project-registry.ts:219`; lane B `place()` `src/services/channel/register.ts:58-65` | One project per row; located projects only; lane B entries placed in one project [read, via subagent]. | Membership on rows, a row kind for a location-less channel, plural placement. |
| **Sminos-Session address**: `hooks/mods/address.tsx:8` | `(<project> on <machine>)` [read]. | Keep the home: it is an address, not a membership list. |

## 2. What ties a log to a directory

**sminos derives the id from the directory. [read]**
- `decision`/`resolve_project` (`S/sminos.py:1436`, `2065`) walk up from the directory: the nearer of a `.smns` and a stored statement decides, then the remote, then the machine project (`1160-1175`).
- Statements are the org frame's `locations` entries with `stated: minted|linked`, parsed by `_stated` (`1206-1226`).
- Ids match `NAME_RE [A-Za-z0-9._-]{1,64}` (`254`; `valid_name` `318`).
- The vectors are pinned to MAWS: `tests/vectors/maws/project-rule.json`.

**The endpoint relays any id; the hub requires a UUID. [read, via subagent]**
- The endpoint relays whatever sminos `hello`s (`src/endpoint/rl10/log-relay.ts:214-226`). Its only rule is the file-name rule (`signature-ledger.ts:74`).
- The hub accepts lowercase UUIDs only (`project.ts:69`; `relay.ts:437-440`; `worker.ts:56-58`).
- An unknown UUID is inserted on `hello` as `kind='hub'`, and the first name given wins (`registry.ts:726-746`).
- Nothing on either side checks the id against a directory, a remote, or the registry.
- The table is defined at `registry.ts:116-118`, with columns added at `147`.

**Would a log no directory derives be accepted and served?**
- Hub and endpoint: yes, if the id is a UUID [read]. The machine project (a uuid5 of org and machine) is a working precedent.
- sminos, receiving: yes, if the org frame lists it [read]:
  - `keep_org` registers each listed, unretired project with root `""` as a followed project (`S/sminos_uplink.py:445-482`);
  - `hub_projects` includes rootless projects (`393-414`);
  - `join_refusal` admits a `join` into it.
- **Catch:** `keep_org` keeps only entries of kind `"hub"` or `"machine"` (`S/sminos_uplink.py:461`) [read].
  - A new `kind: "channel"` would be dropped by every deployed sminos.
  - That direction is safe, but it means either reusing `"hub"` with a marker, or gating on a capability.
- sminos, creating: no verb creates a log apart from a folder [read]. The only ways in are `project init` with a `.smns`, or a statement at a folder.

**What the registry changed. [read, via subagent]**
- Each machine signs a `ProjectsRecord {locations[], known[]}` (`apps/org-protocol/src/types.ts:143-179`; `shapes.ts:260-310`).
- `assembleProjects` merges them (`apps/org-protocol/src/projects.ts:109-136`).
- A minted id is a `randomUUID()`, but only for a folder: `mintRow` refuses one with no anchor (`src/services/index/statements.ts:280-284,318,337`).
- A minted id whose folder vanished is a location in state `missing`/`replaced`, not a location-less id.

**Is "a minted id with no location" a state the code admits? No. [read, via subagent; the lifetime is inf]**
- The only location-less form is `known`: non-`follow` hellos intersected with the sessions held, and dropped once the id is located (`src/endpoint/registry.ts:236-243`; `src/endpoint/projects.ts:266-277`).
- [inf] When its last session ends, the id falls out of every record, then out of the directory (`registry.ts:157-159`).
- Then sminos's leaving rule removes it from every machine after 24 h of complete frames (`S/sminos_uplink.py:499-520`; `LEAVE_AFTER_S` `152`; `may_leave` `1376-1390`) [read].
- So a channel whose sessions all ended would evaporate.

**How a machine follows a log. [read]**
- The endpoint's `org` frame (`src/endpoint/rl10/org-directory.ts:31-47`) lists every assembled hub project and each machine project.
- sminos registers each one (`keep_org`).
- `hub_projects` is the set it `hello`s, with `follow` when the machine has neither a checkout nor a session there (`holds`, `S/sminos_uplink.py:1369-1374`).
- "Every machine follows every log of its org" still holds. It is sminos policy (`S/sminos_uplink.py:32-36`), not MAWS enforcement; the only exception is the leaving rule.
- Cost: each RL1 heartbeat costs one `Project.renew` per open project (`relay.ts:428-433`), and each newly opened project costs one policy-cache rebuild (`src/endpoint/rl10/rebuild.ts:1-6`) [read, via subagent]. C channels × M machines all open [inf].
- [inf] A channel's machine list is the natural follow set.

**A side effect to design around. [read]**
- `known_checkouts` counts every directory a session of the project joined from (`S/sminos_policy.py:131-160`).
- Spawns are admitted there (`S/sminos_rpc.py:1599-1612`), and `holds` reads it.
- So a session in repository R that joins channel C would make R's checkout "a checkout of C": C becomes held, R is listed in C's machine presence, and desk spawns into C are admitted at R.
- The cwd a declared membership joined from must not count. Channels need their own spawn rule. [inf]

## 3. A session's own events under plural membership

**Per session today [read]**
- The record: owners and policy (`S/sminos_records.py`).
- The audience (`audiences.json` keyed by session; `S/sminos_audience.py:271-295`).

**Per log today [read]**
- Lifecycle events.
- The host store (`projects/<id>/host/`).
- The export position (`cursors/export/`).
- The chat cursor (`S/sminos.py:3426`).
- Delivery records.
- `streams.json` (`S/sminos_audience.py:519`).
- The uplink's `host_sent` cursor (`S/sminos_hublog.py:656-672`).

**What duplication across N logs would do**

| Item | Effect |
|---|---|
| `joined`, `state`, `titled`, `renamed` | N× through the per-view publishers (`S/sminos_daemon.py:616-760`). Tolerable [inf]. |
| Host events, if copied | Each store assigns its own seqs. The host pass sends N `host` messages (`S/sminos_uplink.py:1617-1704`; the envelope's `project` is per store) [read → inf]. |
| MAWS journal entries | N entries: journal `src` is `<project>/<writer>/<seq>` (`link.ts:844-861`) [read, via subagent]. |
| `wrote` marks | N marks: `state.hosts[project][writer]` (`link.ts:826-842`) [read, via subagent]. |
| `open_questions` | N rows. The grid's `waiting` (`registry.ts:1001`) over-counts until every log closes it [read, via subagent; the over-count is inf]. |

**What breaks**
- The endpoint Notifier dedups on `` `${writer}\n${seq}` `` with **no project** (`src/endpoint/notify.ts:185-186`) [read].
- So the same session writer at the same seq in two host stores loses the second, different message's notification [inf].
- This can already happen today: a session that `join`s one project and then another starts a host store in each.

**What the desk's per-session view reads**
- The project "Channel" page reads two things [read, via subagent]:
  - the hub log over the Project socket (`src/main/org/channel/channel.ts:1-40`);
  - each machine's to-human journal for that project id (`src/services/channel/journal.ts`, capped at 2,000).
- Lane A entries are placed by the `host` message's `project`. Lane B entries are placed by `place()`, which returns the checkout's one `smnsId` (`register.ts:58-65`).
- A session subscription is served per `(project, session)`. Its host events come from `host_events_of(project, sid)` (`S/sminos_plane.py:2868-2920`; host at `2917`) [read].
- So a subscription opened under a channel that is not the session's home would show no host events [inf].

**Keys**
- `(project, writer, seq)` covers the log, the signature ledger, receipts and the bridge mark. One ask per `(project, session, writer)` covers words/reach. All of these are correct as they stand [read].
- Two keys must change:
  - the Notifier key, which needs the project;
  - the endpoint's `#members` map, keyed by session and fed a single project (`members.ts:131`).

**Recommendation**
- Host events and the export cursor stay in **one home log**, the automatic channel.
- Channel logs carry membership, lifecycle snapshots and `say`.
- The per-session view reads the home.
- "All channels" views dedupe by session.
- Fix the Notifier key regardless.

## 4. Reach

**Per session [read]**
- sminos: the record's `access`/`shares`/`policyRev`; the `audience {session, owners, members, digest, policyRev}` frame (`S/sminos_audience.py:242-286`); stream names `<machine>/<session>~<digest>`.
- MAWS [read, via subagent]:
  - `session_policies (session PK…)` in the Registry (`apps/desk-hub/src/objects/policies.ts:1-37`);
  - the endpoint's audience and policy cache;
  - the policy fields on the single `member` record (`members.ts:64-68`).

**Per log [read]**
- The stream catalogue: sminos `streams.json` (`S/sminos_audience.py:519-560`); hub `streams` (`log-store.ts:21`).
- The hub's `known_policies` and withheld tombstones, per project Durable Object (`project.ts:184,532,743-760`).
- The endpoint's rebuild-done set (`policy-cache.ts:16-17,100-110`).

**What plural membership does**
- The same stream name appears in each log with independent seqs. That is consistent, because the audience is the session's [inf].
- **The gap: the policy transition is written into one log only.**
  - sminos writes the `unlisted` notice and the new snapshot into one project: the member frame's, else the first holding the session (`Link.visibility_project` `S/sminos_uplink.py:1099-1108`; `sminos_visibility.complete` `352-387`, `_notice` `315-330`, `snapshot` `400-418`) [read].
  - Under plural membership the other logs keep serving the old stream to withdrawn readers, and their `known_policies` lag.
  - The notice and snapshot must go into every joined log. This is a privacy correctness item [inf].

**What stays unaffected [read]**
- The `access`/`share` setters and the record RPCs act on the session record (`S/sminos_visibility.py`). They require "a session of a hub project of this machine that joined it from here" (`S/sminos_rpc.py:767-788`; `Here.has_session` `S/sminos_uplink.py:727-733`), which any membership meets.
- Admission to a log is org-wide (`project.ts:458-462`; `worker.ts:309-313`) [read, via subagent].
- So a channel's member list is a listing and follow concept, not access control, unless a per-log ACL is built. Privacy stays per writer stream [inf].

## 5. Seat for every member

### Where a seat and a seat-less member differ [read]

| Path | Seat | Seat-less | Cite (`S/sminos.py`) |
|---|---|---|---|
| Membership on sight | Joined unless its record is retired | Joined only while the harness shows it `interactive`/`bg` (an unmarked `sdk-*` never) | `joinable` `4479-4489` |
| Process gone | Stays joined; reads `stopped` | Retired `ended`; re-joins if it runs again | `_reconcile` `4355-4365` |
| `retire` | Seat record `retired` + event; stopped by `stop_session` | Event only; holds for the process's life, and an interactive process runs on | `_retire_one` `12207-12231`; `cmd_retire` `12175-12204`; `retirement_holds` `4535-4556` |
| Addressed message while stopped | `resume_session` → `claude --bg --resume` | `"recorded"`: "never resumed: it is the human's to reopen" | `push_member` `6485-6575` (`6491-6505`); `push_event` `6071-6081` |
| `fill`, `fill --resume` | Yes | — | `cmd_fill` `11188-11230` |
| Hand-off to a background job | `follow_seat` moves the seat, then `retired continued` | Override and cursor carried, then `retired continued` | `hand_off` `4791-4851`; `predecessor` `4769` |
| Alias source | The seat's alias, fixed | Harness name, else the held alias, under per-project shadowing | `held_alias` `4642`; `join_on_sight` `4596-4614` |
| Project | Its cwd's; `join` refused | Override, else the launch directory | `seat_project` `2097`; `12907-12908` |
| Desk RPC | `resume`/`retire`/`stop` refused `unsupported` | Same, for everyone | `S/CLAUDE.md:11` |

### What exists to build on [read]
- `sminos seat add <group> <alias> --session <sid>` (`S/sminos.py:11116-11171`) already gives a running human-opened session a seat. Its cwd is `os.getcwd()`; it joins and from then on follows every seat path above.
- [inf] "A thread for every member" could be an implicit `seat add --session` at first join. The seat's `group` would need a channel-neutral meaning.

### What giving every member a seat's lifecycle touches [inf from the read paths]
- `ended` goes (`4365`), and human sessions show `stopped` instead of disappearing.
- `retirement_holds` becomes moot.
- `push_member`'s seat-less branch goes: every addressed message to a stopped member resumes it in the background.
- `joinable` stops depending on the harness kind for re-join.
- `join`'s refusal for seats goes.

### Hazards
- **Permission mode on resume.**
  - `--bg --resume` takes no flags (`S/sminos.py:10720-10725`) [read]. A terminal session resumes on its saved mode, typically `default`, where every tool call raises a permission request that only the desk or bridge can answer [inf].
  - Spawned seats launch with `--permission-mode auto` (`10726`) [read].
  - The machine's policy ceiling caps spawns (`admit_spawn`), not resumes [read].
  - Settle with a live test on the current engine: resume an interactive session with `--bg --resume`, read its `permissionMode`, and check whether a flag on resume still forks a copy (last observed v2.1.257).
- **The owner reopens it in a terminal while the background resume runs.**
  - `resume_session` refuses only what it sees running (`S/sminos.py:11336-11349`) [read].
  - Its resume lock is a flock between sminos processes (`11313-11325`); a terminal `claude --resume` takes no part in it [read].
  - Resuming a running session starts a copy, the behavior `copy_started` guards against (`11358-11371`) [read]. The human gets a fork, or two writers on one transcript [inf].
  - This needs a lease the human's path can see, such as the guide or a bridge notice.
- **Config dir.** A session under a non-default `CLAUDE_CONFIG_DIR` is refused resume from elsewhere (`foreign_config`, `S/sminos.py:11303-11307`) [read], so such threads are unresumable by the daemon.
- **Credentials.** A resume runs with the resuming process's environment (`resume_session` docstring `11245-11250`) [read]. A terminal session's gateway route may differ, and the record's `inference` is not re-applied [inf].
- **Lane B.** A MAWS lane B session is MAWS's to reopen and is refused `lane-b` (`S/CLAUDE.md:7`) [read]. It stays excluded.
- **Protected folders.** A resume launches even inside a protected folder (`S/CLAUDE.md:63`) [read]. A session in `~/Documents` resumed by the daemon could raise the TCC dialog that is charged to the daemon (the 2026-11-07 incident class) [inf].

## 6. The smallest coherent implementation

### Shape
- The automatic channel is today's project, unchanged.
- A declared channel is a hub log with a UUID id and a signed declaration: name, members, machines, repositories.
- A session's memberships are {automatic} ∪ declared.
- Host events and the export cursor stay in the home log.
- Channel logs carry `joined`/`retired`, snapshots, and `say`.

### sminos components
1. **Membership model.**
   - The override becomes `{channels: [...]}` (migrate today's single override).
   - `channels_of` sits beside `home_project`.
   - `_local_sessions`/`_reconcile`/`retire_moved`/`here_now` work on set membership (`S/sminos.py:2564-2659`, `4286-4434`).
2. **Verbs.**
   - `join` adds and `leave` removes; seats allowed.
   - `say --in <channel>` for sessions (`6780`).
   - Bare `@alias` over the caller's channels (`6365-6411`).
   - `list`'s default scope.
   - The guide (`12959-13030`).
3. **Fan-out of `in-charge`/`status`** to every membership (`8185-8190`, `8612`, `12086-12109`), or read them from the home.
4. **Policy transition into every membership** (`S/sminos_uplink.py:1099`; `S/sminos_visibility.py:315-418`).
5. **Uplink.**
   - `member` frames carry the channels behind a capability (`S/sminos_uplink.py:676-713`, `1781-1960`).
   - `keep_org` takes channel entries (`461`).
   - `known_checkouts` ignores the cwds of declared memberships (`S/sminos_policy.py:131`).
   - Leaving exempts a channel while its declaration stands (`S/sminos_uplink.py:1376`).
6. **`channel create`.** It asks the endpoint for a signed declaration; sminos signs nothing itself.
7. **Later, separately:** a thread for every member (§5).

### MAWS components [read, via subagent; the shape is inf]
1. A durable signed declaration. Candidates:
   - a new record kind;
   - folder-less entries in `ProjectsRecord` (`shapes.ts:296-310`; `src/endpoint/projects.ts:266-277`; `assembleProjects`);
   - the reserved `OrgState.projects`.
2. The `org` frame lists channels (`org-directory.ts:31-47`).
3. `Member` carries channels, and `sessionProjects` becomes plural (`members.ts`; `link.ts:438-445`).
4. Listings, notify and pending stay the **home** project.
   - A listing says where a session lives; channel membership is read from the channel logs' `joined` events.
   - This is the smaller move.
5. The Notifier key adds the project (`notify.ts:185`).
6. A spawn names its channel (`link.ts:517-518`, today "the first presence listing the checkout").
7. The app:
   - `project-registry.ts:219` stops dropping location-less entries;
   - rows carry membership;
   - lane B `place()` becomes plural;
   - the hub's `kind` gains `'channel'`, or keeps `'hub'` (`registry.ts:116-118,147`).

### Contract surfaces
- **RL10 stays `{1,0}`.** Add a capability pair on the `locations` precedent [read]:
  - sminos `CAPABILITIES` (`S/sminos_rl10.py:297`);
  - the endpoint's constant and gates (`src/endpoint/registry.ts:31,112-115,186-191`);
  - the welcome echo (`link.ts:76-89,650-653`).
- **Under a `channels` capability:**
  - `member` carries `channels: [...]`, with `project` still the home for old readers;
  - the `org` frame carries channel entries (old sminos drops unknown kinds, `S/sminos_uplink.py:461`);
  - a declare/create frame or RPC.
- **Fixtures:**
  - Extend `test/endpoint/rl10/conversation.json`. It is copied byte for byte to `tests/rl10-conversation.json` and replayed by `tests/rl10_conformance.py`.
  - `project-rule.json` is untouched: automatic channels derive as before.
- **Hub:** the RL1 welcome advertises after a probe (`relay.ts:27-36`). This matters only if the hub gains channel tables.

### Order that keeps both repositories releasable
1. **MAWS:** the Notifier key gets the project. A standalone bug fix.
2. **sminos, internal only:**
   - set-valued membership with no declared channels yet, so behavior is unchanged;
   - the transition into every membership;
   - `known_checkouts` excludes non-home cwds.
3. **MAWS:** the declaration record, the org frame's channel entries, and the `channels` capability. Inert until sminos advertises it.
4. **sminos:**
   - advertise `channels`;
   - `keep_org` takes channel entries;
   - `join`/`leave`/`say --in`/`list`/the guide;
   - `member` frames carry channels.
5. **MAWS app:** location-less rows, membership on rows, lane B placement.
6. **After a live engine test:** a thread for every member.

### Hard or unknown, and what settles each
| Item | Settled by |
|---|---|
| Who signs a channel's existence and membership. A machine record cannot vouch for other machines; the head is admin-gated. | The owner's decision. Prior art: registry design §4-§5, which chose machine records over the head. |
| Lifetime. Without a declaration, a channel with no live session evaporates (`known` gone, then the 24 h leaving rule). | The declaration record, with the leaving rule reading it. |
| Follow cost of every machine opening every channel. | Measure hub Durable Object calls per heartbeat at the expected channel count, or follow by the channel's machine list. |
| Background resume of a human session: mode, terminal re-open race, config dir, credentials. | A live engine test and a lease design. Keep it out of the first release. |
| Alias divergence across channels (per-log shadowing). | Decide the alias belongs to the session. Test with two same-named sessions joining one channel. |
| Vocabulary: "channel" already names RL1's multiplex channels, RL2's app↔machine channels, and the per-project "Channel" page in MAWS. | Pick the term before interfaces are written. |
| Id grammars disagree: the hub takes UUIDs only, records take `[A-Za-z0-9._-]{1,64}`. | Mint channel ids as UUIDs. |

## Not covered
- **sminos:**
  - the manager skill;
  - `sminos_tui.py` and `sminos_chart.py`;
  - archive behavior for a channel log;
  - git-mirrored projects (a channel is hub-only by construction);
  - the tests, beyond locating the ones that pin today's rules: `tests/test-join.sh`, `tests/test_locations_kept.py`, `tests/test_leaving.py`.
- **MAWS** (per the subagent):
  - the renderer's sidebar grouping;
  - desk-web;
  - the hub's DX2 HTTP path;
  - the archive machine;
  - the internals of `src/endpoint/channels.ts` and `channel-feed.ts`.
- **Engine behavior:** not re-tested. The latest observation the code cites (a flag on a `--bg --resume` starts a copy) is from v2.1.257.
