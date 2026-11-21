# CH code map: declared channels in today's code

> For the cut and plan of child **CH** of `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`.
> Written 2026-11-20 against doperpowers `origin/main` at `1fdc73a0` (sminos 1.52.0), in the worktree
> `.claude/worktrees/sminos-channels-ch`, and MAWS's trunk (its own checkout, read only)
> at `master` `1ae7f5c96`. Replaces, for CH, the line numbers of `docs/doperpowers/research/2026-11-17-sminos-channels/code-map.md`
> (which predates T1 and T2). `S/` = `sminos/skills/sminos/scripts/`, `T/` = `sminos/tests/`. Every line number is
> at that commit.
>
> **[read]** = seen in code at the place named. **[inf]** = my inference. **[not found]** = the design names it and I could not find it.
>
> Who read what: I read §1–§5, §7, §8 and the sminos side of §1. A subagent read the taught surface (§6, the reply line
> and the manager); another read MAWS (§1.6–§1.9). I re-read the load-bearing citations of both that this map leans on.

## The one finding to plan around

**Every delivery, addressing, `@all` and presence path keys on "the members of the log the event is in"**, which is
`view_of(project).members`: the sessions whose own `joined` is in effect *in that log* [read: `deliver_owed`
`S/sminos_daemon.py:926` loops `view.members`; `deliver_say` `S/sminos.py:9054` builds `by_session` from
`members(dest)`; `match_members` `S/sminos.py:8126` loops `members(p)`; `resolve_tags`' `@all` `S/sminos.py:8337`
uses `members(project)`; `reach_due` `S/sminos.py:7740` takes the plane's `member_rows[pid]`; `Plane.refresh`
`S/sminos_plane.py:2707` builds `here`, `members`, `member_rows` from `view_of(project)`]. A declared channel's log, by
the design, holds **no** `joined` of its members (membership is a statement in each member's project log, D3; and
`known_checkouts` would otherwise turn every member's directory into a checkout of the channel, D6). So as the code
stands a message in a channel log is owed to nobody, a tag `@<channel>/<alias>` resolves to nobody, `@all` reaches
nobody, and the uplink follows the channel (`holds` reads `plane.members`).

So CH has to give a channel log a **roster-derived member set** that delivery, tags, `@all`, the reach pass and the
uplink's `holds` read, while the same set is **kept out of** everything that publishes per-log membership: the `member`
frames (`publish_members` sends a session in two logs' rows "for the first", by sorted id, so a channel id could win),
session presence (`Plane.presence`), machine presence (`holds` → no `follow` → `machine` frame), `rejoin_former`,
`publish_state`, `restate_withheld`, `known_checkouts`, `Here.has_session`. Where that set is built (inside `view_of`
for a channel id, or a separate `channel_view` that the delivery and tag paths call) is the cut's first design
decision; both halves of CH depend on it (§8).

---

## 1. Logs, and how a machine follows them

### 1.1 How a log is opened at the hub [read]

- `HubLog.hello(follow=False)` `S/sminos_hublog.py:628`: `{"t":"hello","project","name","have"}` plus `"follow": true`.
- Sent from three places in `S/sminos_uplink.py`: the connect bundle `Link.open(hl)` `:1446` (bundle at `:1463–1499`):
  `follow = not self.holds(pid)`, and **when not following the bundle carries the machine's `machine` presence**:
  `self.log_lane.send([hl.hello(follow)] + ([] if follow else [machine]) + sessions + ...)` (`:1494`);
  `machine_presence` `:1706` re-hellos when `follow` flips and sends `machine` for every held project (`:1732–1745`);
  the archive confirm `:2252` re-hellos with the kept `follows[pid]`.
- `Link.holds(pid)` `:1369`:
  `return pid == self.own or bool(self.plane.members.get(pid)) or self.checkouts.get(pid, False)`.
- **What CH must change:** `holds` must be true for a channel while a local thread's declared memberships name it
  (D6), *and* the two sends that follow a held project (the `machine` frame at `:1494` and `:1732–1745`, and the
  `sessions` presence list at `:1470`) must send nothing under a channel id. So "held" splits into "held for `follow`"
  and "held for presence" for channel ids [inf]. `machine_sent`/`follows`/`checkouts` dicts are keyed by pid
  and reset on every welcome (`on_welcome` `:900`).
- The plane's member read is cached on inputs that include the thread store (`Plane.stale` `S/sminos_plane.py:2728`:
  `seats = (..., sminos.threads_module().store_key())`), so a `set_channels` write moves it [read].

### 1.2 The directory, `known`, registration, leaving [read]

- `keep_org(frame, cred)` `S/sminos_uplink.py:446` keeps the org frame and registers every unretired entry as a
  rootless followed project (`register_if_absent(make_project(id, name, "", "", hub))`). **It drops every entry whose
  `kind` is not `"hub"` or `"machine"`** (`:461`); 1.27.10 has the same filter (its `sminos_uplink.py:1323`). MAWS
  sends a channel as `kind: "hub"` (§1.8), so every deployed sminos registers it as an ordinary followed project, and
  this version must tell it apart by the id alone (`isChannelId`), in `keep_org`/`project_kind`/`holds`.
- `hub_projects(cred)` `:393`: every known project of this org, rooted or not, minus retired and `has_left`. A channel
  created here enters it once it is registered here (a `project.json` under `projects/<id>/`) [inf: `channel create`
  must register the channel's project locally before the hub lists it, as `keep_org` does].
- `known_checkouts(project, here)` `S/sminos_policy.py:131`: the root, every directory a session of the project
  *joined from* here that still resolves to the project, and declared locations. For a channel with no `joined` events
  and no root it is `[]` [read], which is what keeps a member's repository from becoming a checkout of the channel.
- Leaving: `Link.may_leave(p)` `:1376` (not held, not a machine project, no known checkout), `Leaving` `:498`
  (`LEAVE_AFTER_S = 86400` `:152`), `leave_pass` `:1405`, `has_left(p)` `S/sminos.py:1145`. A channel no local thread is
  in and that complete directories lack leaves after a day of connected time, its log kept: this is exactly D3's
  "stops following it a day later", provided `holds` counts declared membership [inf].
- `org_entry(pid)` `S/sminos.py:1108`, `org_retired` `:1114`, `project_kind(project)` `:4063` (`hub|machine|local`:
  a channel is `hub` today).

### 1.3 Ids: minted, derived, told apart [read]

- Minted: `cmd_project` (`project init`) `S/sminos.py:11451`, `str(uuidlib.uuid4())` (version 4).
- Derived (version 5): `machine_project_id(org, machine)` `:1056` (`uuid5(NAMESPACE_URL, "smns-machine:%s:%s")`),
  `repo_project_id(org, key)` `:1818` (`"smns-repo:%s:%s"`).
- Grammar: `NAME_RE = ^[A-Za-z0-9._-]{1,64}$` `:305`, `valid_name(n)` `:382`; `UUID_RE` `:308` (lowercase 8-4-4-4-12,
  no version check). Nothing in sminos reads a UUID's version.
- **`isChannelId`'s counterpart does not exist** (grep for `is_channel`/`isChannelId`/`channel_id` in `S/` finds
  nothing). Its natural place is beside `UUID_RE`/`valid_name` in `S/sminos.py` (~`:308`/`:382`), since every place
  that takes an id imports from there; the threads module reaches `sminos` too [inf]. Shared vectors would sit in
  `T/vectors/maws/` next to `project-rule.json`, written by `T/vectors/maws/sync.sh` with a `*.PIN.json` (§1.8).
- What takes an id today, each a place a channel id must be refused or handled:
  - `.smns`: `read_smns(path)` `:956` (accepts any `valid_name`), adopted by `_smns_decision` through `_first_smns`
    (`:1524` area) inside `decision(cwd)` `:1508`. The design's "sminos does not take a `.smns` id that passes
    `isChannelId` as a project (the session is told why and is filed in its machine's project)" lands here. **Caution:**
    `decision` is pinned to MAWS's `project-rule.json` by `T/project_rule_parity.py`; a sminos-only exception must
    either be in MAWS's rule too or sit outside the pinned function [inf].
  - `join`: `cmd_join` `S/sminos.py:17827` → `find_project(a.project)` `:17885` → `join_refusal(target)` `:2713`
    (local, other org, retired). `sminos join <channel>` is refused there [inf: a fourth clause of `join_refusal`, or a
    check before it that names `sminos channel add`]. `session_project` `:2732` also reads the override through
    `join_refusal`, so a channel override an older copy wrote is read as absent (the session moves back) if the clause
    is in `join_refusal` itself [inf, and probably wanted].
  - `--project` (list's and say's scope flags, `scope_flags` `:18803`), `say --in`, `list <name>`, `chat <project>`,
    tags `@<project>/<alias>`: all go through `find_project(q)` `:2473` / `project_tiers(q)` `:2427` /
    `_name_tiers(q)` `:2442`, which look up by id, then by name in the tiers `hub`, `machine`, `local`. A channel and
    a project sharing a name are **both `hub`** today, so `_name_tiers` already reports the clash and
    `project_tiers` exits 4 `ambiguous project '<q>': <name> (<id>), ...` [read]. The design wants each listed "with its
    kind and `name#short`"; today's message gives the full id and no kind [read]. `tag_project(p)` `:2465` decides how
    a tag names a project (name, else id).
  - `known_project(pid)` `:2704`, `known_projects()` `:2408` (every registered project plus seats' projects).

### 1.4 Capabilities [read]

- sminos advertises `CAPABILITIES = ("audience", "record", "locations")` `S/sminos_rl10.py:297`, in `hello_frame`
  `:300`. Adding `"channels"` is the switch that makes MAWS count `member.channels` (§1.7).
- The welcome's list is read in `Link.welcomed_rl10` `S/sminos_uplink.py:935`
  (`self.visibility = "access" in caps`, `self.reach = "reach" in caps`) and kept on disk by
  `audience.keep_capabilities(caps)` (`daemon/audiences.json`, `S/sminos_audience.py:48`).
- The CLI reads the kept list with `sminos_audience.advertised(capability)` `S/sminos_audience.py:173` (false for no
  file or no list: "a capability whose absence leaves things as they were"). That is the check for "`channel create`
  and `channel add` are refused on a machine whose endpoint has not advertised `channels`" [inf: it is the existing
  helper for exactly this shape]. `_kept_word` `:160` is the fail-closed variant.
- The pattern to copy for gating a frame field is `member_frame(..., visibility=False)` (§1.5) with
  `self.visibility` from the welcome.

### 1.5 The `member` frame [read]

- `member_frame(pid, m, launch=None, visibility=False)` `S/sminos_uplink.py:679`: `{"t":"member","session","alias",
  "project": pid,"lane","state"}` + `title`, `cwd`, `worktree`, `launch`, `owners`, `ownersProof`, `origin`,
  `principal`/`inference`/`controller`, and `access`/`shares`/`policyRev` when `visibility`.
- Built and cached by `Link.fresh_frame(pid, m, ...)` `:1874`. **Its cache key `made_of` is the session record file's
  stat, the pid, the row's fields, the launch and the visibility** (`:1902`). The thread record (`<seat>.json` or
  `threads/<id>.json`) is not in it, so a `channels` change would not rebuild the frame: the key must take the
  thread's channel set [read the key; the consequence is inf].
- Published by `publish_members` `:1817` over `plane.member_rows` sorted by pid; a session in two logs' rows is sent
  once, for the first (`seen`); a lane change sends `gone` first (`:1846`). `members_before` `:1929` is the "member
  frame first" barrier the words/reach pass uses.
- X5: "A thread in no declared channel is sent with no `channels` key, never with an empty list", the first 128 ids
  count [design]; MAWS counts them only for lane A and only with the capability (§1.8), and the fixture's case 13
  compares whole frames, so the key's absence is tested byte for byte (§1.6). The set to send is this machine's record (`sminos_threads.get(...)["channels"]`), not a read of the
  log [inf: the frame is only for local sessions].

### 1.6 The fixture: what a fresh copy brings, and what it retires

MAWS read at `master` `1ae7f5c96` (the fixture's blob there is `4322826f`, the same at `267233774`, the commit MAWS
handed over for it). Case and step numbers are 0-based, as the harness keys them. [read, by the MAWS subagent with
`diff`/`jq`; I re-read the S4 rule and the harness check named below.]

- **The pin.** `T/rl10-conversation.source.json` names MAWS commit `85e93436`, the path and blob `7e73b41`;
  `T/rl10_conformance.py:136-149` fails on a copy whose git blob differs. A copy is made by hand (no script; earlier
  re-pins `fd43855d`, `f6d266a2`): `git -C <MAWS> show 267233774:test/endpoint/rl10/conversation.json >
  sminos/tests/rl10-conversation.json` and the pin's `commit`/`blob` set to `4322826f…`.
- **Every difference a fresh copy brings:**
  - bindings: `"channel:C": "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"`.
  - case 0: steps 1 and 4 (hellos) list `["audience","record","locations","channels"]`; step 5 (welcome)
    `["access","reach","record","locations","channels"]`.
  - case 4: step 0 `have` S2 1→2; step 4 (first upload) gains `thread` on S1's `joined` and `titled` and on S4's
    `joined`, an inserted S2 seq 2 stamped `joined`, and wider `vary`; a new step 17 (`hub-holds` scene for S2 seq 2),
    appended, so no case 4 index moves.
  - case 11 (40 → 41 steps): steps 5–6 gain `channels`; **a new step 12**, S4's member frame (`lane A`, **`state:
    "gone"`**, no title/launch/controller), so **every later step moves down by one**; the old step 16 (now 17), S4's
    `withdrawn` scene, gains `"held": {"lane":"A","state":"gone"}`; the old step 18 (now 19) `have` S2 1→2, S4 2→1.
  - **case 13 (new, 6 steps), the only case with `member.channels`:** up `hello {project: C, name:
    "desk-integration", have: {}}` with **no `follow`**; down `have`; up S1's member frame (case 11 step 10's, plus
    `"channels": [C]`); scene `holds` true; up the same frame with **no `channels` key**; scene `holds` false.
- **What it retires** (`T/rl10_conformance.py`): `AMENDMENTS[(4,0)]` (`:872-873`), `AMENDMENTS[(4,4)]` /
  `amend_threads_upload` (`:855-868`, `:874-875`) and `AMENDMENTS[(11,18)]` (`:876-877`, now step 19) all equal the
  new lines; with them `S2_WRITER`, `S4_WRITER`, `STAMPED` and the docstring's T1 paragraph (`:33-38`, `:820-837`).
  `check_restated`'s S4 clause (`:987-1004`), the harness's own check of the stopped member's frame, is superseded by
  step 12.
- **What breaks on replay, and must be decided before the copy:**
  1. **S4's state word.** The harness asserts `("A", "stopped")` for S4 (`:1001`); sminos sends `stopped` for a
     human-opened thread whatever its transcript (`S/sminos.py:6418`:
     `"stopped" if threads_module().stopped_human(sid) or transcript_path(sid) else "gone"`). The new step 12 expects
     `gone`, and MAWS's step 17 `withdrawn` scene depends on it (MAWS lists a `stopped` lane A member; only `gone`
     withdraws: its plan's Decision Log 18, `docs/doperpowers/plans/2026-11-18-mw-sminos-channels.md:751`). X5's
     sentence "MAWS's fixture on its master holds that frame field for field as T1 sends it" is therefore **false
     for the state word** (X5 says "`gone` when it has no transcript" and leaves out that a human-opened thread is
     `stopped` regardless). Either the fixture changes in MAWS (MAWS's architect's call) or CH keeps one amendment at
     (11,12), contradicting "the copy retires the amendments" [read both sides; that the replay fails is inferred,
     not run].
  2. **Case 11's index shift.** Every table keyed `(11, n≥12)` moves +1: `PROBES` (11,35)/(11,36) `:816-817`; `CHECK`
     (11,38) `:722`; `late_checks` (11,21), (11,29), (11,33) `:732-733`; (11,28), (11,31) `:723-724`; the dead
     `run_deferred`'s `(11,13)` `:1012`.
  3. **The capability in the hello.** Hellos are matched whole, so `CAPABILITIES` must end with `"channels"`
     (`S/sminos_rl10.py:297`), and the literal in `T/test_rl10.py:285` moves with it. So **the copy and advertising the
     capability are one change**: advertising before the copy fails the old fixture's hellos, the copy before it fails
     the new ones.
  4. **Case 13 needs staging:** S1 placed in channel C (the binding's id is a valid version-8 id); sminos must open C
     with `have {}` and no `follow`, and send S1's frame with `channels: [C]` and nothing else changed; then remove
     S1 and send the frame without the key (`matches` compares whole frames, `:222-237`, so `channels: []` fails).
  5. The replay never fails on extra lines, so "no presence or checkout under a channel id" is not proved by it: that
     needs a test of its own [inf].

### 1.7 `isChannelId` and the shared vectors [read]

- MAWS `apps/org-protocol/src/channel-id.ts:7-12`:
  ```ts
  export const CHANNEL_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  export function isChannelId(value: unknown): value is string {
    return typeof value === 'string' && CHANNEL_ID.test(value);
  }
  ```
  Callers: the endpoint's `memberChannels` (`src/endpoint/rl10/members.ts:95`) and member refusal (`:242`), the link
  refusal (`src/services/index/statements.ts:303`), the hub registry (`apps/desk-hub/src/objects/registry.ts:760,
  1761, 1822`).
- `apps/org-protocol/vectors/channel-rule.json`: `about`, `version` (1), `ids` (29 `{id, channel, why}`: 4 true, 25
  false: other versions, wrong variant digit, nil, max, upper case, no hyphens, braces, URN, trailing newline, spaces,
  wrong length, non-hex, a full-width digit, `"desk-integration"`, `""`), `retired` (T1's five cases). sminos's copy
  `T/vectors/maws/channel-rule.json` is byte-identical, pinned by `channel-rule.PIN.json` (commit `8a7f308ff`);
  `sync.sh <MAWS> <commit> [<file>]` writes copy and pin. **Only `retired` has a consumer in sminos**
  (`T/test_threads.py:67-68, 480-499`); `ids` is CH's to consume (X4) [read].
- MAWS's plan (§B, `:428-505`): a change raises `version`; neither side edits the file alone.

### 1.8 The endpoint and the hub [read]

- **Capability.** `CHANNELS_CAPABILITY = 'channels'` (`src/endpoint/rl10/link.ts:96`); the hello's capabilities kept
  (`:697`, ≤32 strings); the welcome echoes `channels` last and only when the hello listed it (`:708`). sminos should
  gate on the welcome's list, as it gates `access` and `reach` [inf].
- **`member.channels`.** `MEMBER_CHANNELS_MAX = 128` (`members.ts:85`); `memberChannels` (`:91-100`) keeps entries
  passing `isChannelId`, deduplicated, in order, up to 128, silently. Read in one place, `sminosView().sessionProjects()`
  (`link.ts:474-484`): `channels && member.lane === 'A' ? [member.project, ...memberChannels(member)] :
  [member.project]`. So a lane B member's channels, or any without the capability, count for nothing.
- **`known`** (`src/endpoint/registry.ts:244-250`, `#knownNow`): the logs this sminos opened **without `follow`** whose
  id a held member's `sessionProjects` names. **Both are needed**: a channel opened with `follow` is never known, and a
  channel no member frame names is never known. Its name is the log-plane hello's `name` (`log-relay.ts:240-241`,
  ≤128 chars). While sminos is away or restating, the last answer stands.
- **Refusals.** A member whose `project` passes `isChannelId` is logged and treated as `gone` (not kept, no listing)
  (`members.ts:242-245`); a link to a channel id is refused (`statements.ts:303`). A log-plane `hello` for a channel
  id is opened like any project (`log-relay.ts:216-227`).
- **Event kinds.** The hub requires only a string `kind` (`apps/desk-hub/src/objects/log-store.ts:66`); no reader keys
  on channel ids or on new kinds; no `request` or `lead` kind exists anywhere in MAWS.
- **Retention** (`apps/desk-hub/src/objects/registry.ts`): the row is `kind 'hub'` with an `unlisted` column (`:125`,
  `:155`); `CHANNEL_RETENTION_MS` 7 days (`:188`), recheck daily (`:190`); retired after 7 days unlisted (`:1776-1800`),
  reactivated by a stored record that lists it (`:1822-1828`); **a hello does not revive a retired row** (`:752`,
  `:757`).
- **The `org` frame** (`src/endpoint/rl10/org-directory.ts:36-49`) is built from the endpoint's assembled directory,
  not the hub table: `...hub.map((p) => ({id, name, kind: 'hub', retired: false}))` (`:45`). **A channel arrives as
  `kind: "hub"`**, passes `keep_org`'s filter, and every machine's sminos registers it as an ordinary followed hub
  project unless CH tells it apart by `isChannelId` [read the frame; the consequence is inf]. It leaves the frame as
  soon as no machine's record lists it as known; the hub's 7-day retirement affects only the hub's own grid.

### 1.9 The hub's and the endpoint's reach checks [read]

- **The hub, at upload** (`apps/desk-hub/src/objects/project.ts`, `upload` `:554-639`, `judge` `:2039-2080`,
  `factsOf` `:2001-2011`) reads `sessionRefs(event)` (`apps/org-protocol/src/audience.ts:39-58`) **for every kind**:
  `to[i].session` and **`session` when it is not the writer's own session** are *addressing* refs;
  `origin.spawnerSession`, `attest.origin.spawnerSession` and a `continued`'s `to` are provenance. An addressing ref
  to an unknown session, or to a session with an audience the event's audience does not fit, is **withheld**: a
  tombstone at that position, `refused {reason: not-reachable}` back, the writer goes on.
- **The endpoint, before it signs an own event** (`src/endpoint/rl10/log-relay.ts` `#judge` `:416-447`), with the same
  refs: an event naming a private session must be written under that session's audience stream; differing audiences
  are refused; an unknown session while the policy cache rebuilds is held.
- So a request naming its target in **`session`** (not `to`) is exactly "where the hub's check of who may reach a
  session reads it" (D3) [read], and sminos's readers do not mistake it for the target's own event: `_own_events`
  reads the session's own writer files and `_projection` requires the writer's session to be the event's
  (`S/sminos.py:6115`) [read]. A self-request (`session` = the writer's own) carries no ref [read].
- **`reach?`** (`src/endpoint/rl10/reach.ts:33-49`): `deliver` when a verified sender shares an owner with the
  recipient, or **every sender holds at least `list`** on the recipient's record (`rankAtLeast(..., 'list')`); with no
  verified sender, `deliver` unless the recipient is private (`refuse unverified`); else `refuse not-reachable`. Its
  `project` serves only to verify the sender and read the ledger, so a channel id works there. It is unanswered when
  the recipient's member or record is not held.

**Consequence for "who may ask":** the endpoint's `reach?` grants at `list`, not at `converse`. D3 says a request is
honoured when its writer "may converse with the thread". If CH honours requests by `reach?` (§2.3), the rule it applies
is today's message reach (`list`), not `converse` [read the threshold; whether the design meant today's reach is for
the plan to settle, likely with MAWS's architect].

---

## 2. Membership

### 2.1 The record field and its writer [read]

- `channels` is a field of both record kinds: `_of_seat` `S/sminos_threads.py:285` reads it (`[]` when absent);
  `_create_human` `:1063` writes `"channels": []`; adoption sets it `[]` (`:1032`); `SEAT_KEYS` `:67` lists it.
- `set_channels(thread_id, channels)` `:779` = `update(thread_id, {"channels": [...]})`.
- `update(thread_id, fields, remove=(), guard=None, lock_until=None)` `:735`: merged under the store's lock, **refused
  (returns False, nothing written) while the record has an open `pending` entry or `guard` fails**, never a journaled
  key. Its docstring and X1 both say `update` is "a change that owes no event".
- **A statement is an event** (D3: a membership change is written to the thread's project log). So `set_channels` as
  built is a record write with no event, and the statement is a separate append: a crash between them leaves the
  record and the log disagreeing, and nothing replays it. T1's own rule for exactly that is the journal (`begin` /
  `finish` `:1301` / `:1520`: "the record is written first, and a reconciliation finishes exactly what `pending`
  names"). Either CH adds an operation to the journal (its events written by `finish` through `lifecycle`, so
  `op` stamps them and a replay skips what the log holds), or it accepts the window and has the restatement on the
  next new writer repair it [inf; I would take the journal: it is the one mechanism the store already trusts].
- `follow(...)` `:1474` queues an operation behind an open entry, which is what a request met during a hand-off would
  need instead of a refused `update` [inf].

### 2.2 Where a thread gets a new writer (where the statement is restated) [read]

Every lifecycle event goes through **one function**, `lifecycle(log_project, session, kind, guard=None,
required=True, **fields)` `S/sminos.py:4628`, which picks the writer (`own_stream(log_project, session)` `:4235`:
`<machine>/<session>`, or its audience stream `~<digest>`), adds the `thread` stamp (`threads_module().stamp`), adds
X3's `wake`/`why` on a `state`, and appends under the writer file's lock with an optional `guard`. Journaled
operations append through it too (`finish_thread` `:4798` passes `append=lifecycle`). So "restate the statement
whenever the thread gets a new writer" has a single choke point [inf]. The new-writer moments:

| Moment | Where | What is written today |
|---|---|---|
| Continuation (engine hand-off) | `hand_off(project, old, new)` `S/sminos.py:5805` → journal **advance** / **absorb** (`S/sminos_threads.py`), carried by `carry_hand_offs` | `retired continued` on old, `joined` on new, one stamp |
| Refill (`fill` without `--resume`, `spawn` onto the alias) | `spawn_fresh` `:13762`, `cmd_fill` `:14350`; two advances (T1 §6 row 6) | `retired replaced` on old, `joined` on new |
| `join` | `cmd_join` `:17827` → `move_session(sid, old, new, by)` `:17807` → `retire_moved` `:5301` + `join_on_sight` `:5451` | `retired moved` in old log, `joined` in new |
| A directory that resolves elsewhere | `_reconcile` `:4910` → `retire_moved`; the new log's reconciliation joins it | the same |
| A change of reach that opens a new stream | `sminos_visibility.complete` `S/sminos_visibility.py:352` → `snapshot(sid, project)` `:400` | the `unlisted` notice, then `joined` + `state` under the new writer |
| A machine rename / re-enrolment (former writer) | `rejoin_former(project, view)` `S/sminos_daemon.py:751` | `joined` under the name now |
| A withheld own snapshot | `restate_withheld` `S/sminos_daemon.py:1149` | `joined`/`state` restated |
| A return (ended thread reopened or filled) | journal **return**, `join_seat(..., returns=True)` `:4697` | `joined`, stamped |

`joined` writers, all through `lifecycle`: `S/sminos.py:4587` (`joined_again`), `:4728` (`join_seat`), `:5144`,
`:5272` (`adopt`), `:5347` (`refresh_joined`), `:5575` (`join_on_sight`), `S/sminos_daemon.py:782`
(`rejoin_former`), `S/sminos_visibility.py:414` (`snapshot`). [inf] The rule "a `joined` under a writer whose latest
statement is not in that writer's file is followed by a statement" covers every row of the table, including the
continuation and the reach change, without a call per site; it is also what a reader needs, since D3 reads "the latest
statement **under the thread's current writer**".

### 2.3 "In the same pass that holds the reach permit for that writer" [read the permit; the reading is inf]

The only "reach permit" in the code is the uplink's single-use push permit:
`_REACH_PERMITS` / `reach_permit(project, session, e)` `S/sminos.py:7426`/`:7435`, granted around the one push the
endpoint answered `deliver` for (`Link.on_reach` `S/sminos_uplink.py:1050` → `deliver_reach(project, member, event,
verdict, reason)` `S/sminos.py:7791`, which pushes `with reach_permit(...)`). The reach pass is `Link.ask_words`
`S/sminos_uplink.py:1994`, which sends `reach? {id, project, session, event}` for `reach_due(project, members)`
`S/sminos.py:7740` (first owed event per writer, owed by `to`, for the plane's local member rows of that log).

So the sentence reads as: the thread's machine asks the endpoint `reach?` about the **request** event with
`session` = the thread's current session, and writes the statement (applied, or refused `not-reachable`) when the
answer comes, in `deliver_reach`'s place, under the delivery lock of that (channel, session) [inf]. That fits D3's
"who may ask: the requester may converse with the thread" and "the hub checks reach and no other authority": sminos
holds no grade logic (`S/CLAUDE.md`, "sminos holds no grade logic") and could not decide "may converse" itself. What
this needs that does not exist:
- `reach_due` and `ask_words` iterate the plane's member rows of the log and events owed by `to`
  (`addressees(events)` `:6664`); a request is neither (it names its target elsewhere, D3), so CH adds a third ask
  source, "requests in channel logs naming a thread of this machine, not yet answered by a statement" [inf].
- `same_owner_local` `S/sminos.py:7467` (same machine, same owners, no ask) and `ReachGate.capable`
  (`audience.reach_capable()`; a machine whose endpoint does not advertise `reach` has no gate) give the two no-ask
  cases; `policy.read_only()` + `policy.outside_origin(e)` (`S/sminos_policy.py:118`, `:122`) the read-only refusal;
  `sminos_records.lane_of(rec)` `S/sminos_records.py:293` the lane B refusal. These are the reusable pieces (§3).
- **Ambiguity to settle in the plan:** if "the reach permit for that writer" means something else (for instance the
  audience stream `own_stream` chooses, i.e. "the writer the thread's reach gives it now"), the statement is simply a
  `lifecycle` append and no ask is involved. The design does not say which; the code supports only the first as a
  "permit", and the permit is sminos-local (the endpoint keeps no per-writer permit, §1.9).
- **What MAWS already enforces without any ask** (§1.9): a request carrying its target in `session` is refused by the
  endpoint unless written under the target's audience stream when the target is private, and withheld by the hub when
  its audience does not fit. So a request a private thread's audience excludes never reaches the thread's machine at
  all, and "pending" for it is indistinguishable from an off machine on the requester's side unless sminos reads the
  `not-reachable` refusal of its own position (`HubLog.withhold_own`, `S/CLAUDE.md`'s "The sender's side") [inf].
  And `reach?`'s threshold is `list`, not `converse` (§1.9).

### 2.4 The reducers, and how an unknown kind is treated [read]

- `MEMBERSHIP = ("joined", "retired")` `S/sminos.py:686`; `LIFECYCLE = MEMBERSHIP + ("renamed", "state", "titled",
  "in-charge", "status", "unlisted")` `:689`.
- `Fold` `S/sminos_threads.py:106` (`add(session, event)`, `effect`, `joined`), `in_effect(events)` `:130`,
  `stamped` `:91`, `passed_by` `:97`; used by `_memberships(events)` `S/sminos.py:5275` (for `_reconcile`, memoized by
  `log_memo(events, "memberships", ...)`) and `_projection(events)` `:6069` (cached in `_PROJECTED[project.id]`
  keyed on the log files' signature, and `_VIEWS[project.id]`).
- **This version:** `_projection` skips any kind not in `LIFECYCLE` (`:6113`: `if kind not in LIFECYCLE ...: continue`);
  `_memberships` reads `MEMBERSHIP` only; chat shows only `CHAT_KINDS = ("say", "human")` `:674` unless `--kind`;
  `parse_event` `:2925` accepts any string kind. Delivery owes **any kind** whose `to` lists the
  session (`addressed_to` `:3424`, `_addressees` `:6672`, `_owed` `:6635`: no kind check).
- **The oldest version the older-copy suite runs, 1.27.10** (`REV_1_27=aefb80aa` in `T/test-older-cli.sh:53`; also
  1.51.0 at `:54`, and `--older <path>` for any cached copy): `LIFECYCLE` without `unlisted` (its `sminos.py:606`),
  the same skip in `_projection` (its `:3592`), membership by `latest_membership` over `MEMBERSHIP` (its `:2901`),
  and the same kind-blind `addressed_to` (its `:2244`). So a **new kind with no `to` naming the target is inert to
  every installed reader** for membership, projection and delivery [read]. A new kind that carried `to` would be
  delivered (and would wake a seat) by every version: that is the design's reason for keeping the target out of `to`.
- Two places invalidate caches on `LIFECYCLE` kinds only: `_append` `S/sminos.py:3250` and the hub import
  `S/sminos_hublog.py:324` (`_VIEWS.pop(project.id)`). If the statement kind is not added to `LIFECYCLE`, its append
  does not drop the view cache of its own project [inf: harmless for the project's view, but see §5.3 for the
  channel's roster cache, which is keyed on other logs].
- Adding the statement kind to `LIFECYCLE` is the cheap way to have `_projection` fold it per session (the row gains
  e.g. `channels`), and only this version reads it [inf].

### 2.5 `_local_sessions`, `_reconcile`, `retire_moved` [read]

- `_local_sessions(project, all_seats)` `S/sminos.py:4886`: seats whose project is this log, and running engine
  records whose `record_project` is this log. For a channel it is empty [read: nothing resolves to a channel id]
  unless an older copy `join`ed a session into it.
- `_reconcile(project, events, local, by_session, all_seats)` `:4910`: finishes open journal entries, `older_writes`,
  `older_hand_offs`, then for each local member whose latest is `joined`: `retire_moved` / `hand_off` / `end_closed`;
  then `join_on_sight` for local evidence. Run by `view_of` on every read. On a channel log with no `joined` it
  appends nothing [read]. The design's advisory "`_local_sessions`, `_reconcile` and `retire_moved` are where
  membership is decided today" is true of *project* membership; declared membership needs none of them, by the design
  as it now stands (statement in the project log, no `joined` in the channel) [inf]. What it does need from them: a
  `joined` an older sminos wrote **into a channel log** (by `join <channel>`) is today reconciled like any member's;
  `retire_moved` would move it back once `join_refusal` refuses the override (`session_project` reads an ineligible
  override as absent) [inf].
- `retire_moved(project, sid, where, recheck=None)` `:5301`, `here_now` `:5286`, `moved_here` `:5350`.

### 2.6 What the absorb does to a membership [read]

`absorbable(record, session)` `S/sminos_threads.py:625` (human-opened, not ended, `sessions == [session]`, no entry)
checks nothing of `channels`; the absorb's last step deletes the absorbed record (`entry["other"]`, `:1755–1777`).
So a membership the provisional job's record gained before the hand-off was seen is **dropped silently** today; CH
decides (the design's residue) whether the advance merges it [inf: a union into the continuing record's `channels`
inside the advance's write is the natural fix; only an `add` the job made of itself, or that a request made of it,
can be there].

### 2.7 Where a daemon pass could carry out a request [read]

- `daemon run` ticks **every known project, followed channel logs included**: `tick_all` `S/sminos_daemon.py:1307` →
  `tick(project)` `:1229`, which reads `view_of(project)` and runs `rejoin_former`, `publish_state`,
  `restate_withheld`, `publish_renames`, `deliver_owed`. Then `sweep_threads()` `:1383` once per tick.
- The uplink delivers what it imports at once: `deliver_imports` `S/sminos_uplink.py:1341` → `HubLog.deliver()`.
- The reach pass (§2.3) is the uplink's, after its upload pass.
- [inf] A request is best carried out where its verdict arrives: the reach pass on a machine whose endpoint has `reach`,
  `deliver_owed`'s place in `tick(<channel>)` where it has not (no gate: every request honoured but the read-only and
  lane B refusals). Both paths must write the statement under one lock per thread (the "one writer" rule; `Fold`'s
  single-writer assumption is per session's own file) and apply requests "in the order they reach it" (D3: by the
  channel log's merge order as this machine read it, `_store_whole`/`log_read` order). A request a statement already
  names (channel id, writer, seq) is not applied again: that is the idempotence key.

---

## 3. Who may ask [read]

- **Reach is decided by the endpoint, never by sminos.** Pieces a request check can reuse:
  - `ReachGate(project)` `S/sminos.py:7480` (`capable`, `applies`, `needs(e, session, words)`, `held`), and the ask
    `reach?` with its answer path (`Link.on_reach` → `deliver_reach`), §2.3.
  - `same_owner_local(e, session, project)` `S/sminos.py:7467`: no ask between one owner's sessions of this machine,
    only where `own_writers_here(project)` `:7448` (a hub project of this org with no remote: a channel log
    qualifies [inf]).
  - `owners_meet(sender, recipient)` `:7543`: the raw `send` rule (no log event).
  - `WordsGate` `:7348` / `words_route` `:7327`: a person's words (`human` kind) are the endpoint's to verify
    (`words?`), relevant to the lead's untagged post (§4.7).
  - `policy.read_only()` / `policy.outside_origin(e)` `S/sminos_policy.py:118`/`:122`: the machine admits nothing
    from outside.
  - `records.lane_of(rec)` `S/sminos_records.py:293`.
  - `records.unreadable(sid)`: a recipient whose record cannot be read is owed, never asked (P5 O18 D10).
- The access setters: `sminos_visibility.set_visibility(sid, *, access, share, operator)`
  `S/sminos_visibility.py:132`; `widens` `:123`.
- **`confirmed(name, w, prompt=None, none=None)`** `S/sminos_visibility.py:476`: reads a y/N from `/dev/tty`
  (`os.open("/dev/tty", O_RDWR|O_NOCTTY)`), exits 1 with `none` (or the widening text) when there is no terminal;
  accepts `y`/`yes`. Already reused with a custom `prompt` by `retire --owner-unknown` (T1 M5), which is the precedent
  for `channel lead` [read]. Widening is also refused inside a session (`CLAUDE_CODE_SESSION_ID` set) by the callers,
  and moves to the app once the welcome advertises `record` (`terminal_may_widen` `:535`,
  `sminos_audience.widening_through_app`). [inf] `channel lead` wants the session refusal and `confirmed`, not the
  `record` cutover (the lead is not reach).

---

## 4. Saying something in a log

### 4.1 `cmd_say` end to end [read] (`S/sminos.py:9215`)

1. From a session: `--in` is refused (`:9225`: `"--in is for an operator, not a session — tag @<project>/<name> to
   speak into another project"`); `home = caller_project(caller_seat())`, `kind = "say"`, `writer = writer_id(sid)`.
   From a terminal: `home = find_project(a.in_)` or `caller_project()`, `sender = "human"`, `kind = "human"`,
   `writer = writer_id()` (`<machine>/human`).
2. A selector (`--org|--project|--machine|--here|--state`) goes to `say_scoped` `:9162`.
3. `resolve_tags(home, text, raws)` `:8324` → `(dest, recipients, text, wake)`: no tags → `dest = home`, untagged;
   `@all` alone → the live members of `home` (`members(project)`, `m.state in FILLED`), refused in a machine project;
   otherwise each tag via `resolve_tag` → `_resolve_tag(project, t)` `:8275`, and **"one message, one project"**: tags
   reaching two logs are refused (`:8361`).
4. `streams_for(dest, sid, recipients, text, raws)` `:4246` splits by audience (P5 O18 D4).
5. Per split: `log_append(dest, writer, kind, from=, to=rs or "*", text=, wake?, from_project?)`.
   **`from_project = home.id` whenever `dest != home`** (`:9263`; also in `say_scoped` `:9194` and `send` `:16119`), "where a reply finds it".
6. `record_copy(home, [(dest, e)])` `:9007` when `dest != home`: a copy in the sender's own project log (`copy` key,
   owed to no one).
7. `deliver_say(dest, e, writer, recipients)` `:9054`: for each recipient that is a member of `dest`, local ones by
   `deliver_next(dest, member, due=True)` `:6967` (push, wake, hold lines), remote ones `remote_line(member)` `:6875`
   and a nudge.

What CH changes there [inf]:
- `--in` for a session, limited to a declared channel (a project stays reachable by tag only, as today).
- With dest a channel: **no `from_project`** (else the reply line names the sender's home project and the reply lands
  outside the channel: `push_live` uses `from_project` as the reply line's log, `S/sminos_control.py:266`), and
  **no `record_copy`** if "a message belongs to one log" is read strictly (the copy is a second event of the same
  words in the project log; today it is how a cross-project sender sees its own message in its chat). Both are
  decisions; the code forces the first.

### 4.2 Tags [read]

- `_resolve_tag(project, t)` `:8275`: `@<p>/<alias>` in `project_tiers(p)`'s logs in turn; `@alias#short` and
  `@short` across `org_scope()` `:2484`; bare `@alias` **in the sender's project only**, then as a short/id across the
  org; the refusal `no_member` `:8242` lists other projects' members of that alias (`BARE_NAME` `:8239`). Matching is
  `match_members(name, short, projects, alias=True, ids=True)` `:8126` over `members(p)` (skips retired and
  `has_ended`), `current_first` `:8077` (current names before former ones), `id_reach` `:8043`, `alias_reach` `:8057`,
  `former_ids` `:8035`, `one_per_session` `:8153`, `candidate_labels` `:8166` (`alias#short`, behind `<project>/`
  when they span projects), `note_former` `:8098`.
- `find_target(q)` `:11547` (send, status, retire, the verbs) resolves non-id names "as a tag is".
- CH: a bare `@alias` resolves over "the sender's project ∪ its declared channels' rosters" (D1, "Aliases"), the
  refusal listing `alias#short` per candidate (`candidate_labels` already does); `@<channel>/<alias>` resolves in the
  channel's roster. Both need `members(<channel>)` to be the roster (the headline). Which log a bare-`@alias` message
  that reached its target *through a channel* goes into is not settled by the design: "With neither [`--in` nor a
  channel-qualified tag], `say` does exactly what it does today" says the target's project log with a copy in the
  sender's (today's cross-project rule), and the design's residue "a tagged message from outside follows today's
  cross-project rule" agrees [inf: so a bare tag never lands in a channel log].

### 4.3 Event kinds, and keeping host kinds out of channel logs [read]

- `say` (session) and `human` (operator) are the chat kinds a `say` writes (`CHAT_KINDS` `:674`).
- `message`, `question`, `answered` (`HOST_KINDS` `:9409`) are written only by the host export path: `cmd_record`
  `:10573` → `record_session` `:10221` → `export_host` `:9986` / bridge `export_live` `:10416` → `append_host`
  `:10150` (host store, `HOST_STORE`, `host_store_holds` `:10070`), into **the session's resolved project**
  (`session_project`), and `close_questions(thread)` `:10112` writes `answered` "in the project it was asked in".
  None of these takes a log from the caller; they take `session_project`. So no channel id can be their target
  **unless a session's project resolves to a channel** (an older copy's `join <channel>`, a `.smns` naming a version-8
  id) [inf]. The two guards that make it impossible are therefore `join_refusal` and the `.smns` rule (§1.3); a cheap
  belt is an assertion in `append_host` that the project is not a channel id [inf].
- No RL10 `host` or pending frame under a channel id: the uplink's host pass reads `host_store_holds` per project
  (`S/sminos_uplink.py`, the host pass around `:1617`), so the same two guards cover it [inf].

### 4.4 Delivery: whom an event is owed to [read]

- `addressed_to(e, session)` `:3424` (`to` is a list naming the session, no `copy`), `_addressees` `:6672`,
  `addressees(events)` (memoized on the event list), `_owed(events, session, record)` `:6635` (per writer, past
  `settled`, not revoked), `owed(project, member)` `:6684`, `delivered_load(project, session)`
  (`projects/<id>/delivered/<sid>.json`, lock `delivered/<sid>.lock`).
- `deliver_next(project, member, due=False)` `:6967` → `push_event(project, member, session, e, events, cursor,
  words=None)` `:7874` → `push_member(member, text, tagged, session, event, project, words)` `:8857` →
  `push_live` (`S/sminos_control.py`) or `wake(record, session, ...)` `:14689`.
- `frame_of(project, e, events, session, cursor)` `:7856`: a `send` (has `msg_id`) → `compose_frame(sender, msg_id,
  msg, label)` `:15577` (`[sminos message from <s> id=<id>]`); otherwise `compose_chat_frame(project.name, ref, sender,
  target, unread, text, label)` `:7902` (`[sminos chat <log name> <ref> from <s> → <target>[ | unread N]]`). So a
  channel message is already "framed as coming from that channel" by name once delivery runs on the channel log
  [read the composition; inf for channels].
- Delivery state (`delivered/`, cursors, the held marks `[seq, thread]`) is all keyed `(log, session)`; nothing needs
  a new key for a second log [read: T1 §5 and `delivered_load`].

### 4.5 The reply line [read] (detail in the subagent's notes, verified)

- `reply_line(session, project="")` `S/sminos.py:12454`:
  `'[To reply, run in Bash: %s say "@%s%s <your reply>"]' % (shlex.quote(os.path.join(SCRIPT_DIR, "sminos")), "<project>/" if valid, session[:8])`.
  `peer_envelope` `:12472` appends it as the last line inside `<cross-session-message>`; `send_frame` `:12490`.
- It names the log as `@<log id>/<short>` (the event's `from_project` if valid, else the log's; `S/sminos_control.py:266`).
  A reply `say "@<channel id>/<short> ..."` lands in the channel's log **only if** the sender's short resolves in the
  channel's roster and `say` from a session accepts a channel-qualified tag; otherwise it is refused [inf].
- It still models a double-quoted body under an absolute path: TECH-DEBT row `docs/doperpowers/TECH-DEBT.md:786`,
  "Trigger: the skill's rewrite for channels and threads", i.e. this child.
- Pinned by `T/envelope_parity.py` (hostile project names, exactly two `"`), `T/test-broadcast.sh:291-297`,
  `T/test-address.sh:268-285`, `T/test-bridge-control.sh:721-722, 796-806`, `T/test_wake.py:61`,
  `T/test_wake_delivery.py:515-526, 562`, and the manager's `REPLY_LINE_RE`
  (`sminos/skills/manager/scripts/manager_window.py:61`).
- The wake's note contract (D2 step 3) fixes the order: header at offset 0, the `[sminos] ` note the last paragraph,
  the reply line after it and last on the inbox route (`S/sminos_control.py:228-233` splices the note before routing).
  A channel frame must keep that layout; the to-human classifier reads the header only
  (`to-human/hooks/mods/to-human.tsx:340-360`: `→ @(?:you|all)` — a channel frame's target must stay `@you` or `@all`
  to classify) [read by the subagent; I re-read the regex].

### 4.6 The wake on a channel message [read the path; inf for channels]

A tagged message in a channel log to a stopped thread reaches `deliver_next(<channel>, member)` → `push_member` →
`wake(record, session, due, ...)` `:14689` exactly as a project message does, **provided the member row exists in the
channel's view** (the headline). The hold machinery is per `(log, session)` (`_HELD_PASSES` keyed `(project.id,
session)` in `deliver_owed`; held marks in `projects/<log>/delivered/<sid>.json`), the wake lock per thread
(`wake_lock`, `launch_hold`), the hold reason per session (`hold_for` `:6741`, `hold_now` `:6751`). `@all` sets
`wake: True` on the event, which is "for the live alone" and never wakes (T2 §4) [read]. Nothing in T2's wake keys on
"the session's own project" [read: `wake` takes the record and session], so it should carry over unchanged.

### 4.7 `send`, and the lead [read]

- `cmd_send` `:15961` → `find_target` → `send_to_member(project, m, sender, via, text, msg_id)` `:16167` /
  `send_to_seat` `:15589` / `verb_to_thread` `:8606`. `send` records into the target's project log
  (`record_message`). D5: `send` leaves the taught surface; it needs no channel form [design].
- The lead: an untagged operator `say` (`kind: "human"`, writer `<machine>/human`) into a channel whose lead event is
  in effect is addressed, on this machine, to the lead thread. That is a branch in `cmd_say` after `resolve_tags`
  returns no recipients and `dest` is a channel [inf]. Its delivery is a person's words (`WordsGate`, `words?`); the
  design notes it works only where the words can be verified (MAWS `src/endpoint/rl10/words.ts`).
- X8's machine-notice marker does not exist yet (EN writes it) [not found]; the reader that skips it is CH's.

---

## 5. Listing

### 5.1 The views [read]

- `View(members, rows, retired, events, info, reconciled, ended)` `S/sminos.py:6485`; `Member` `:4022` (now with
  `thread`, `opened`, `thread_sessions`, `wake`, `why`, `end`, `end_by`, `named`).
- `view_of(project, all_seats=None, titles=True)` `:6553`: seats → `_local_sessions` → `_store_whole(project, "log")`
  → `_reconcile` → `_projection` (cached `_PROJECTED` by files signature) → rows by `_member` `:6364` per joined
  session, `thread_current` `:8109` (one row per thread), seats no member stands for, `retired`, `ended_rows` lazily.
  Cached in `_VIEWS[project.id]` per cache generation (`forget_caches`), dropped on a `LIFECYCLE` append to that
  project. `project_view` `:6545`, `members(project)` `:6615`, `project_rows` `:17206`.
- A roster row "built from the member's own project log as the reader may read it" is exactly `view_of(<its
  project>).members` filtered to the threads whose latest statement (under their current writer) names the channel:
  `_member` already applies `unlisted_here` (a private session drops out) and `has_ended` [read], which gives D3's
  "a thread that went private drops out" and "an ended thread is not in it" for free [inf].
- **Cache coupling:** a channel's roster depends on statements in *other* logs. `_VIEWS`/`_PROJECTED` are keyed by the
  log's own project id and files, so a roster cached under the channel's id would not see a new statement in a
  member's project log [inf]. Either the roster is not cached under the channel's id, or its key is the set of logs it
  read (the plane's `stale` already computes per-log input keys, `S/sminos_plane.py:2728`).

### 5.2 `cmd_list` [read] (`S/sminos.py:17608`)

- `list_scope(a)` `:17246`: no filter → `view_projects("")` `:17193` (the caller's project; from no project, every
  project); a name or `--project` → `find_project`; any other filter (`--machine`, `--state`, `--here`, `--org`,
  words) → **every known project not `has_left`**. `row_matches` `:17273`.
- Text: one section prints the project name as a heading then rows; several sections print a flat table with a
  project column (`row_cells(m, p)` `:17369`, `print_rows` `:17409`). Stopped/retired/gone fold into "+N hidden"
  (`HIDDEN`), `--stopped` unfolds stopped, `--all` everything; `View.ended` rows only with `--all`/`--state retired`.
- `--json`: a flat JSON list of `member_json(m, project, private=not a.org)` `:4078` objects (`project`,
  `project_id`, `project_kind` prepended), plus `(no project)` rows and other live sessions under `--here`.
  **Not versioned**: fields have been added in place (`thread`, `opened` by T1) [read]. A channel membership would be a
  new key (e.g. `channels: [...]`) or rows under a `project_kind: "channel"` [inf]; X1 forbids exporting `sessions`,
  `launch`, `pending`.
- **Where `# name` sections attach:** the `sections` list in `cmd_list` (`:17626`) is a list of `(project, rows)`;
  bare `list` today has one section and prints its name as a heading. D3's bare `list` (the caller's project and every
  declared channel it is in, each with its roster, the channel's stopped members shown) is more sections in that list
  with their own fold rule; the one-section/flat-table switch at `:17668` must change so that several sections each
  keep a heading [inf].
- `--org` cost: one `view_of` per known project (each a `_store_whole` read, reconcile and projection, cached by files
  signature) [read]. A channel roster costs the same read of every project log a member could be in; on this
  machine's fleet that is "every project known here" (88 projects, 56k events on the MacBook copy cited in
  `S/CLAUDE.md`) [read the figure; the cost for a roster is inf]. Reading only the logs of threads whose `joined` is
  recent is not possible without an index; the cheap bound is to read only logs this machine follows, which is all of
  them.
- `channel show` attaches as a new verb that prints one channel's roster (the same rows) plus the pool; its VM columns
  are EN's (design).
- `cmd_projects` `:17723` lists every known project with its kind: a channel shows as `hub` with no live members
  until CH gives it a kind [read].
- `sminos who`/`find` (`cmd_find` `:17695` = `list --org`), `cmd_tui` (via `view_projects`), the roster in the
  guide (`_roster_exchanges` `:18111`, which reads only `[here] + [home]`) are other readers of "projects".

### 5.3 Aliases and former names [read]

- One alias per row, from the session's own project log (`_member`, `held_alias` `:5635`, uniqueness per log by
  `shadowing(project, session, info, all_seats, released)` `:5672`). In a channel roster two threads with one alias
  are told apart by `member_label` `:4105` (`alias#short` when another row shares it) [read]; nothing makes an alias
  unique across logs (D1 says "one per thread, the same in every channel": true by construction, since the row's
  alias is read from the thread's one project log) [inf].
- Former names resolve within one project's projection (`former_ids`, `_THREAD_INDEX` `:6200`, `episode_mark`,
  `row_thread`; T1 §4). "Reading a thread's history across logs is CH's" (design): for a roster built from project
  views, a thread that refilled into another project is found in its new project and its old names do not resolve
  there [read T1 §4; inf for channels].
- The engine's collision name (E15): `name_source` `collision` is one of the sources `Member.name_source` carries
  [read]; whether the roster lists the short id instead is CH's call (design).

---

## 6. What sessions are taught (from the subagent; spot-checked)

- **Guide:** `guide_text(session, launch, source="", title="")` `S/sminos.py:18023-18103`, printed by `cmd_guide`
  `:18269` from `sminos/hooks/smns-guide.sh` (SessionStart, matcher `startup|resume|clear|compact|fork`); `roster_text`
  `:18215` (+ `_roster_exchanges` `:18111`, `_roster_tag`, `_roster_when`) on `compact|resume`. It names one project
  (`:18083-18084` "you are %s in project %s on machine %s ... A `cd` does not change your project."), the `join` line
  (`:18075`, omitted for a seat), and the verbs (`:18087-18099`: `list`, `say "..."`, `say "@<short> ..."` / `"@<project>/<alias> ..."` with "a bare @alias reaches only your project", the selector line, `say - <<'EOF'`). It never says thread, channel, stopped, woken or `--in`. `_roster_exchanges` reads only the session's own and launch-directory projects, so channel exchanges would not appear.
  - Tests: `T/test-guide.sh` (bash, real `sminos guide`, pins several lines **verbatim**: `:112-118`, the verb loop
    `:119-122` including `@<project>/<alias>` and `join <project>`, the fork text `:350-379`); `T/test-smns-guide-hook.sh`
    (the hook's wiring); `T/test_threads_stopped.py:906-971` (calls `guide_text` for the `/clear` witness).
- **Skill:** `sminos/skills/sminos/SKILL.md` (241 lines; headings at 6, 8, 30, 57, 140, 153, 197, 236). The project
  model at `:13-28`; tag resolution `:93-100` ("A bare `@alias` resolves only in your project", "A message into another
  project lands in its log, with a copy in yours marked `→ <project>`"); `join` `:142-151`; the wake `:176-195`.
  `references/setup.md` (205) has no say/tag/join text; `references/spawn-preamble.md` (56) names the project and tags
  (`:1-2`, `:8-18`). "thread" and "channel" appear in none of them.
  - Preamble: `PREAMBLE_PATH` `S/sminos.py:300`, `render_preamble(project, alias, by)` `:13602` (fills
    `{{PROJECT}}`, `{{ALIAS}}`, `{{BY}}`), one call site `:13805`. Pinned verbatim by `T/run-sminos-tests.sh`
    `:784-823`, `:1429`, `:2458-2464`, `:2589` (a reflow once broke a gate, commit `43a2f04c`).
  - `sminos help` is the module docstring `S/sminos.py:2-243` (`:62` `sminos say [--in <project>] <text>`, `:~111`
    `join`): a taught surface the design does not list [inf].
- **Manager:** `sminos/skills/manager/` (SKILL.md 206, `disable-model-invocation: true`; read-only). Its scripts put
  `../../sminos/scripts` on `sys.path` (`manager.py:36-37`) and import `sminos as S`, `sminos_bridge`, `sminos_fork`
  (`manager.py:40-45`), `sminos_jobs`, `sminos_marks`, `sminos_subagents` (`manager_window.py:25-29`). Uses
  `S.find_target`, `S.members`, `S.known_projects`, `S.seat_project`, `S.log_read`, `S._own_events`,
  `S.addressed_to`, `S.event_ref`, `S.LINE_START`, and copies the frame grammar in regexes
  (`manager_window.py:61-66`: `REPLY_LINE_RE`, `WAKE_NOTE_RE`, `CHAT_FRAME_RE` whose group 1 is the log's name,
  `MESSAGE_FRAME_RE`). Subscriptions store one `project`/`project_name` per member. A channel returned by
  `known_projects()` could be matched as a project by its `resolve()` (`manager.py:122-166`) [inf]. Tests
  `T/test_manager.py`, `T/test_manager_serve.py` (`run-sminos-tests.sh:423-426`). Its `scripts/CLAUDE.md` says a change
  to its SKILL.md or brief reruns its pressure scenarios and replay
  (`docs/doperpowers/specs/2026-10-31-session-manager-replay.md`).
- **Backtick guard:** `sminos/hooks/mods/backticks.tsx` (533 lines), registered on `tool.call` for Bash
  (`:527-533`), lexes only commands holding both a backtick and `sminos`; a sminos call after another command is
  recognised by **a hard-coded `VERBS` set** (`:36-41`), which has no `channel` (and lacks `census`, `profile`) [read].
  A new verb family must be added there; no parity test ties `VERBS` to the argparse list. Its refusal text
  (`:512-525`) teaches `sminos say - <<'EOF'`. Tests `T/mods/backticks.test.ts` (the `sminos-mods` gate).
- **TECH-DEBT rows CH inherits** (`docs/doperpowers/TECH-DEBT.md`): `:786` the reply line (CH's trigger, above);
  `:784`, `:785` the guard's misses; `:49` (row 34) `who` and a `say --in <old project>` note after a join; `:565` the
  `--bg` hand-off with a join override's one-tick gap; `:621-625` the guide on an in-session `/resume`; and the whole
  "sminos threads" section `:801-830`, of which `:810` (a `/clear` between binding and the inbox write; fix is a
  `session_id` in frames) and `:824` (a not-reachable notice carrying a wake line, which the manager shows) touch the
  frame. None names channels.
- **How the skill was evaluated before:** no repo-resident harness for the sminos skill (`evals/` absent;
  `tests/claude-code/` covers other skills; CI's `sminos*` gates run only `T/run-sminos-tests.sh`). T1 evaluated the
  guide and skill by "a baseline on the text as it is and a run on the edit, on four behaviors" (T1 plan
  `:1344-1352`, decisions `~:2885-2900`); an earlier pass used prompt files and fresh subagents
  (`docs/doperpowers/specs/2026-10-13-smns-project-log-m5-evals.md`); and the PATH/guard work ran real
  `claude -p --plugin-dir <worktree>/sminos` sessions in a throwaway project and `SMINOS_HOME`
  (the working files of that pass, `evals/run.sh`, `run-base.sh`, with transcripts beside them). The last is
  the closest to what CH's evaluation ("a fresh session creating a channel, placing others, and speaking in it") needs,
  but a channel needs a second machine or a stand-in endpoint advertising `channels` [inf].

---

## 7. The CLI's shape [read]

- `build_parser()` `S/sminos.py:18737`: one `argparse` subparser per verb (`sub.add_parser(name, add_help=False)`),
  each `set_defaults(fn=cmd_x)`; nested families use a second `add_subparsers` (`seat` → `add` `:18766`; `project`
  → `init|show|attach` `:18851`; `daemon` → `run|census|profile|policy|...` `:18863`). A `channel` family
  (`create`, `add`, `remove`, `lead`, `env add|remove`, `show`) is a fourth nested family of the same shape, with
  `main`'s usage line for a family given no op (`main` `:19080`: `if a.cmd == "seat": die("usage: ...")`).
- `main(argv)`: parse (any parse error exits 2), a few verbs that must not migrate or lock run first (`record`,
  `bridge`, `guide`, `rpc-query`, `daemon owed|profile`, `who` with no target), then `stdin_body(a)`, `migrate()`,
  `a.fn(a)`; `LogWriteFailed` → exit 1 "completed, but ...", `WakeBusy` → exit 1.
- Exit codes: `die(msg, code=EXIT_USAGE)` `:367`; `EXIT_USAGE = 2`, `EXIT_UNKNOWN = 4` `:302-303`; 1 for a refusal
  or failure by convention (`die(..., 1)`); 0 success. "Unknown or ambiguous name" is 4 throughout (`find_project`,
  `_resolve_tag`, `find_target`).
- `STDIN_BODIES` `:19057` (verbs whose prose may be `-`); a new verb with prose (none of `channel`'s has any) would
  be added there.
- `--json` outputs are not versioned (`list`, `chat`, `machines`...): fields are added in place [read]. Help is the
  module docstring (`usage()` `:18733`).
- `READING_VERBS` decides `HINTS["on"]` (`main`); a reading `channel show` would join it [inf].

---

## 8. Sizes and coupling

### 8.1 Sizes [read, `wc -l`]

`S/sminos.py` 19,141 · `S/sminos_daemon.py` 3,193 · `S/sminos_plane.py` 3,061 · `S/sminos_uplink.py` 2,564 ·
`S/sminos_rpc.py` 2,424 · `S/sminos_threads.py` 2,312 · `S/sminos_bridge.py` 2,103 · `S/sminos_hublog.py` 1,422 ·
`S/sminos_records.py` 701 · `S/sminos_control.py` 670 · `S/sminos_wake.py` 642 · `S/sminos_visibility.py` 569 ·
`S/sminos_audience.py` 564 · `S/sminos_rl10.py` 539 · `S/sminos_policy.py` 278. Total under `S/` 48,199.
Tests touched most: `T/run-sminos-tests.sh` 7,817 · `T/test_threads.py` 2,825 · `T/test_wake_delivery.py` 1,386 ·
`T/rl10_conformance.py` 1,243 · `T/test_visibility.py` 1,175 · `T/test-join.sh` 724 · `T/test_reach_gate.py` 710 ·
`T/test-org.sh` 655 · `T/test-address.sh` 566 · `T/test_leaving.py` 502 · `T/test-broadcast.sh` 486 ·
`T/test-guide.sh` 408 · `T/test_list_fold.py` 141.

### 8.2 The two candidate halves

**H1, membership and its wire.** The id rule and its vectors; `channel create|add|remove`; the request and its
application; the statement and its restatement; the record's `channels`; `holds`/presence; `member.channels` and the
capability; the fixture copy; `join <channel>` and `.smns` refusals; pending and expiry.
Functions: new `is_channel_id` (beside `UUID_RE`); `join_refusal` `:2713`; `_smns_decision`/`decision` `:1508`
(pinned, §1.3); `sminos_threads.set_channels`/`update`/`begin`/`finish` and `absorbable` (§2.1, §2.6); `lifecycle`
`:4628` (the restatement choke point); `sminos_visibility.snapshot` `:400` (if the restatement is per site);
`reach_due` `:7740`, `ask_words` `S/sminos_uplink.py:1994`, `deliver_reach` `:7791` / `on_reach` `:1050` (the ask, if
§2.3's reading holds); `Link.holds` `:1369`, `Link.open`'s bundle `:1463-1499`, `machine_presence` `:1706`;
`member_frame` `:679`, `fresh_frame` `:1874` (cache key), `CAPABILITIES` `S/sminos_rl10.py:297`;
`keep_org` `:446` and `project_kind` `:4063` (a channel arrives as `hub`, §1.8); `T/rl10_conformance.py` `AMENDMENTS`; a `channel` parser family.

**H2, traffic and the taught surface.** `say --in <channel>`, channel-qualified tags, bare `@alias` over shared
channels, `@all` in a channel, the reply line, the frame, the lead, `list` sections and `channel show`, aliases, the
guide, skill, preamble, manager, the guard's `VERBS`.
Functions: `cmd_say` `:9215` (`--in`, `from_project`, `record_copy`), `resolve_tags` `:8324`, `_resolve_tag` `:8275`,
`match_members` `:8126`, `no_member` `:8242`, `candidate_labels` `:8166`, `find_target` `:11547`, `deliver_say`
`:9054`, `reply_line` `:12454` and `push_live`'s origin `S/sminos_control.py:266`, `compose_chat_frame` `:7902`
(probably untouched), `cmd_list` `:17608`/`list_scope` `:17246`, `cmd_projects`, `guide_text` `:18023`,
`_roster_exchanges` `:18111`, `render_preamble` and `spawn-preamble.md`, `SKILL.md`, `manager_window.py` regexes,
`backticks.tsx` `VERBS`, `usage()`'s docstring.

**Changed by both (the real coupling):**

1. **The channel's member set** (the headline): `view_of` `:6553` / `members` `:6615` for a channel id, or a new
   roster function every caller below reads. H1 needs it for `holds` (via `Plane.refresh` `S/sminos_plane.py:2707`),
   for the reach ask's member rows (`ask_words` iterates `plane.member_rows[pid]`), and for `channel show`'s
   acceptance of `add`/`remove`; H2 needs it for `deliver_owed` (`S/sminos_daemon.py:926`), `deliver_say`,
   `match_members`, `@all`, `list`. And `Plane.refresh` is where H1 must keep it **out of** `member_rows` (else
   `publish_members` may send a member frame with `project: <channel id>`, which MAWS refuses) and out of
   `Plane.presence` (session presence under a channel id, forbidden by D6). One function, two opposite requirements
   from the two halves.
2. **The statement reader**: H1 writes statements; H2's roster reads "the latest statement under the thread's current
   writer" out of `_projection` (`:6069`) / `_member` (`:6364`) / `Member`. Its shape (field names, how a refusal and a
   request id are carried) is fixed by H1 and read by H2 (X4: CH owns the kinds' names and shapes).
3. **`find_project` / `project_tiers` / `_name_tiers` / `project_kind`** (`:2473`, `:2427`, `:2442`, `:4063`): H1
   needs "is this a channel" for `join`, `channel add`, the `.smns` rule; H2 needs the name refusal with kind and
   `name#short` for `--in`, `@name/alias`, `list <name>`.
4. **The cache keys**: `_VIEWS`/`_PROJECTED` (`:6553`), `Plane.stale` inputs, and `fresh_frame`'s `made_of`; a roster
   that reads other logs and a frame that reads the thread record both break today's "keyed on one log" assumption.
5. **`cmd_say`**'s refusal of `--in` from a session is H2's, but the capability refusal ("`channel create` and `add`
   are refused without `channels`") and the `from_project` rule (the reply must land in the channel) sit beside it.

[inf] The halves cut cleanly only if (1) and (2) are built first, inside H1, as an internal read API that H2 consumes
("the roster of channel C as this machine may read it", "the channels of thread T") with no CLI. Otherwise H2 starts
by changing H1's functions.

### 8.3 Statements of the design that the code makes hard, false or already done

- **Already done:** the record field and its writer (`channels`, `set_channels`) [read]; "a reader skips an unknown
  kind" holds for 1.27.10, 1.51.0 and this version as long as the new kinds carry no `to` naming the target (§2.4)
  [read]; `known_checkouts` excludes a channel's member directories by construction (§1.2) [read]; the per-`(log,
  session)` delivery keys, the wake and the hold need no new key (§4.4, §4.6) [read]; "framed as coming from that
  channel" is today's chat header with the log's name (§4.4) [read]; `confirmed` exists for the lead (§3) [read];
  `audience.advertised` exists for the capability refusal (§1.4) [read]; a name clash between a channel and a project
  is already refused (exit 4), though not in the design's words (§1.3) [read].
- **False as written:** X5's "MAWS's fixture on its master holds that frame field for field as T1 sends it": the new
  case 11 step 12 says `gone` where sminos sends `stopped` for a human-opened thread (§1.6). And "the copy retires the
  amendments" holds only once that is settled.
- **Not as the design words it:** D3 "may converse" vs `reach?`'s `list` threshold (§1.9); D6 "the hub registers it as
  it registers any id" is true, but as `kind 'hub'`, and the org frame hands it to every machine as an ordinary hub
  project (§1.8), so "every machine follows every channel" happens by itself and `isChannelId` must be applied on
  receipt, not only at creation.
- **Hard:** the headline (delivery, tags and presence all key on per-log `joined`); "the reach permit" (§2.3): no
  pass today asks reach about an event that is not owed by `to`, so honouring a request by the endpoint's reach needs a
  new ask source, or the design means something else by it; the statement through `update` (§2.1) contradicts X1's
  own "a change that owes no event goes through `update`".
- **Easy to get wrong:** `fresh_frame`'s cache key does not see the thread record (§1.5); `holds` → `machine` presence
  (§1.1); `from_project` sends a channel message's reply to the sender's project (§4.1); `publish_members`' "first
  pid wins" (§8.2 item 1); the absorb drops `channels` (§2.6); `VERBS` in the backtick guard (§6).
- **Unclear in the design, decided by the code's shape:** whether a bare `@alias` that reached its target through a
  shared channel lands in the target's project log (today's rule; my reading) or the channel's; whether a channel
  message keeps `record_copy`'s copy in the sender's project; the `.smns` rule against `project-rule.json`'s parity.

---

## What surprised me

- **Delivery has no notion of "a member of this log" other than a `joined` in it.** The design moved membership out
  of the channel's log (rightly, for `known_checkouts` and for one writer per membership), and in doing so removed the
  one thing every delivery, tag, `@all`, reach-ask and presence path reads. Nothing in the design names this; it is
  the first decision of the cut (the headline).
- **The fixture copy will not replay clean** (§1.6): `stopped` vs `gone` for a human-opened thread with no
  transcript. The design and MAWS's plan both say MAWS's master matches T1 field for field; the state word does not.
  The copy, the `channels` capability and the case 11 index shift must land in one change.
- **A channel already reaches every machine as an ordinary hub project** (§1.8): MAWS's org frame sends `kind: "hub"`,
  and every installed sminos, 1.27.10 included, registers it. "Every machine follows every channel" is not something CH
  builds; telling a channel from a project on receipt is.
- **`known` needs both the member frame and a non-`follow` hello** (§1.8), and today `holds` is false for a log with no
  local `joined`, so the holder would follow its own channel and MAWS would never list it. Holding it naively then
  sends machine presence under the channel id, which D6 forbids (§1.1).
- **`reach?` grants at `list`** (§1.9), so "may converse" is not what the only reach check MAWS answers checks.
- **`set_channels` goes through `update`**, whose contract is "a change that owes no event", while a membership change
  owes a statement (§2.1). And the absorb drops a provisional record's `channels` (§2.6).
- **`from_project` would route a channel message's replies out of the channel** (§4.1): a reply line names the
  sender's home project whenever the sender spoke into another log.
- **The backtick guard keeps its own hard-coded verb list** (§6), so a `channel` family is invisible to it in a
  pipeline until added.
- **The design's "the hub checks reach and no other authority" has a concrete field:** `session` is an addressing ref
  for every kind when it is not the writer's own (§1.9), which is what lets a request name its target without `to`.
