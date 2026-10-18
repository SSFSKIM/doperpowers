# The sminos org directory: every session in the org can find, judge, and reach every other

The owner runs many Claude Code sessions that collaborate across three repositories (doperpowers, ci-kit, MAWS) on three kinds of machine (the MacBook `macbook`, the Mac mini `mini`, the devcloud hosts), all enrolled in one desk-hub org, `ssfskim`. Today a session finds a peer in another repository only when the owner pastes its name; the harness's own `ListAgents` sees one machine; a bare sminos `@alias` never leaves the sender's project; and a session in a directory that is no project (the home directory, `~/claude-code-bundle`, a one-off clone) is invisible to every other session and to the desk.

After this change every session on every enrolled machine is in a project the hub syncs, so any session can run `sminos list --org`, `sminos find <words>`, `sminos projects` or `sminos machines`, read who works on what anywhere in the org — alias, kind, state, machine, project, repository and branch, in-charge line, activity — judge for itself whom to talk to, and reach that session with `sminos say "@short …"` or `"@<project>/<alias> …"`, the message recorded in both projects' logs and delivered through the receiver's own machine. A session whose directory misfiles it declares its own project with `sminos join`. The owner sees every live session of every project on one desk screen, those waiting on them first. sminos replaces the harness's `ListAgents` (board ticket #93 is absorbed here, and where this design supersedes #93 it says so), and once the evals hold the owner denies `ListAgents` in their settings.

To see it working: on an enrolled machine, in any directory, `sminos list --here` prints every session the harness's `ListAgents` would, each with its kind and a state that agrees with the engine's record; `sminos find ci-kit` prints the ci-kit sessions on every machine; `sminos say "@mini/new-7e did the devcloud image build?"` from a doperpowers session arrives in the `new-7e` session on the mini as a peer message with a reply line, and `sminos chat` in both the doperpowers project and the mini's machine project shows it; the desk's org view lists that session among every other, with the ones waiting on the owner at the top.

## Progress

- [ ] M1 — Rows from the engine's records, the filter layer, `--here`, the subagent tree
- [ ] M2 — Hub (MAWS): the `org` frame, follow-only hellos, machine projects at the Registry, machines' online state
- [ ] M3 — Every enrolled machine follows every org project; machine projects; the org-only `.smns`; doperpowers' and ci-kit's `.smns`
- [ ] M4 — `sminos join`, `session_project`, moves when a resolved project changes
- [ ] M5 — Addressing across the org and the copy in the sender's log
- [ ] M6 — Desk (MAWS): the org view, outbound copies in both timelines, machine projects on the grid
- [ ] M7 — Guidance at session start, its evals, documentation, release

## Terms

Terms from `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` ("the log design") keep their meaning: project, `.smns`, member, alias, short, writer, event, log, projection, daemon, frame, internal fork. Terms from the desk's design (`docs/doperpowers/plans/2026-10-15-desk-dc4-uplink.md`, DX2/DX3/DX4) too: the hub (the Cloudflare Worker at `apps/desk-hub` in MAWS and its Durable Objects — the `Registry`, one per org; a `Project` per project; a `Machine` per enrolled machine), the uplink (`skills/sminos/scripts/sminos_uplink.py`, the daemon's child holding the machine's one stream to the hub), `hello` (the frame that opens a project on a stream), the lease (a machine is online in a project while its lease is fresh), presence (DX4's session and machine messages). New here:

- **Org** — the desk-hub org a machine is enrolled in (`$SMINOS_HOME/daemon/hub.json`'s `org`, written by `sminos hub enroll`); `ssfskim` for the owner. Every project whose `.smns` names the org, every enrolled machine, and every machine project together are **the org's directory**.
- **Enrolled machine** — one whose `daemon/hub.json` names a hub, an org and a machine name (`sminos.machine_identity()` reads it). Every other machine is **unenrolled**.
- **Machine project** — a hub project the hub creates for each enrolled machine, with no checkout anywhere: the project of every session on that machine that no `.smns` claims. Its id is `uuid5(uuid.NAMESPACE_URL, "smns-machine:<org>:<machine>")` with the machine's name lower-cased (the hub compares machine names without case, `machineNameKey`), its name is the machine's name as enrolled, and in a tag it is `@<machine>/<alias>`. Written `@mini` in prose.
- **Stray** — a session on an enrolled machine whose working directory resolves to no committed `.smns`: a home-directory session, one in `~/claude-code-bundle`, a one-off repository. A stray's project is its machine project.
- **Followed project** — a hub project of the org that a machine opens on its stream only to read and deliver (it has no checkout of it and no session in it). A **held project** is one the machine has a checkout of or a session in. Which a project is on a machine can change.
- **Join override** — a session's declaration that it works in another project than its directory says (`sminos join <project>`), kept at `$SMINOS_HOME/sessions/<session-uuid>.json`.
- **Move** — a session's resolved project changing while it runs (a `.smns` committed or removed under it, a join override): recorded as `retired` with reason `moved` in the old project and `joined` in the new one.
- **Copy** — the record of a cross-project message in the sender's own log, marked `copy`, which delivers nothing.
- **Engine record** — `~/.claude/sessions/<pid>.json`, what the harness writes for each running session (`name`, `sessionId`, `cwd`, `kind`, `status`, `pid`, `entrypoint`, `nameSource`, `updatedAt`); the same records the harness's `ListAgents` reads. `sminos.peer_records()` reads them.

## Owner decisions (2026-10-18)

The brainstorm's decisions, each dated, recorded here once and bound by the sections below:

- Directory first, channels later; channels must never limit reach (§10).
- A session declares its own project with `sminos join`; the working directory stays the default (§7).
- A cross-repo message is recorded in both projects' logs (§6).
- Scope: every session on every enrolled machine, revised at 11:55Z from "hub projects plus this machine" (§1, §1b).
- The filter layer — `--project`, `--machine`, `--state`, trailing words, `sminos projects`, `sminos machines` — proposed by the owner at 13:00Z (§4).
- A repository that gains a `.smns` moves its live sessions; asked by the owner at 13:05Z (§1a).
- Board #93 is folded in: sminos replaces `ListAgents`, with a project view, a machine view (`--here`), the caller's subagent tree, SessionStart guidance and evals; once the evals hold, the owner denies `ListAgents` in `permissions.deny` with a CLAUDE.md note; no mod tool and no refusal in the plugin; cross-session `SendMessage` is not blocked; cloud and Remote Control sessions are out of scope; built after the desk walk (§4, §9, #93's answers at board:643).
- The final ask, all as recommended: the design is approved; the desk org view is in this initiative (§8); sessions in machine projects export their `<message>` spans to the hub (§1b).

## 1. Every session on an enrolled machine is in a synced project

A session's project is resolved in this order, by one resolver, `session_project(session, cwd)` in `skills/sminos/scripts/sminos.py` (§7):

1. its join override, when the file exists and names a project known here;
2. the working directory's `.smns`, walking up (`resolve_project` as today), with the worktree rule of §1a;
3. on an enrolled machine, the machine's own machine project;
4. on an unenrolled machine, the local project of the owning git repository, `local-<repo>`, as today; a directory in no repository is no project, as today.

Consequences, each a decision:

- **One project per session, and every session on an enrolled machine is in a hub project**, so every one is synced to the hub and visible on the desk. The alternative, keeping strays out of every project and listing them from engine records alone (#93's "(no project)" group), lost because a stray could then be reached only from its own machine and only unrecorded, and the owner's scope revision made every session a directory entry.
- **`@all` is refused in a machine project** with "a machine project is not a team: tag who you mean". Its members share nothing but a machine.
- **`local-*` logs are not migrated.** They stay under `$SMINOS_HOME/projects/local-*/` and readable with `sminos chat local-<name>`. A session that was in `local-X` stays there until its process ends (its `retired` `ended` is written by that project's reconciliation as today) and joins its machine project on sight meanwhile: a transient dual membership, accepted, because migrating history into a hub project would upload every stray's past to the hub, which no one asked for.
- **Seats keep their group namespace** (`derive_group`, the seat key `group/alias`): the alias namespace and lifecycle lock stay per owning repository. Two same-named seats spawned in two non-hub repositories on one machine are both members of `@<machine>` and make a bare alias ambiguous there; the refusal names each as `group/alias`, which resolves.
- **doperpowers and ci-kit get a committed hub `.smns`** (§2's org-only shape), in the same milestone that switches the fallback to the machine project (M3), so a machine project only ever holds strays: home-directory sessions, `~/claude-code-bundle`, one-off repositories. Landing the files after the switch would put every doperpowers and ci-kit session of the fleet into machine projects for a while and move them later (§1a); landing them together costs nothing.

### 1a. A repository that gains or loses a `.smns`; linked worktrees

- New sessions in the repository resolve to the new project.
- Live sessions move. A session whose resolved project changed — a `.smns` committed or removed under its directory, or a join override written (§7) — is retired in the old project with `reason` `moved` and `project` the new project's id, and joined in the new one with `by` `move` and its real `cwd`, by the same path `sminos join` takes (§7). The daemon's tick does it, within one interval: each tick first maps every running engine session to its project through `session_project`, which registers a project not yet known here (`project_path` writes its `project.json`), so a project that appeared this tick is ticked this tick; then each project's reconciliation retires its local members whose session now resolves elsewhere and joins the sessions that resolve to it. One tick may join before it retires: a dual membership of one interval, accepted. This replaces the critic's "transient dual membership" as the steady state with a one-tick one.
- History stays in the old project's log; the `moved` event names the new project, and a tag that names the old project (`@mini/<name>` for a session that moved into a repository's new project) is refused with `<name> moved to <project>`; `@short` keeps working, since it resolves org-wide (§5). The desk's transcript view of a session does not depend on its project.
- An explicit join override is untouched by a `.smns` appearing: the override is step 1.
- **A linked worktree at a head that predates the `.smns`** resolves it from its main checkout: when the walk from the directory finds no `.smns` and `owning_repo(cwd)` (the main checkout, by the common git dir) differs from the directory's toplevel, `<main checkout>/.smns` is read if it exists. `skills/issue-tracker/scripts/_binding.sh` already resolves `board.json` this way ("a linked worktree reads the main checkout's file when it has none of its own"), for the same reason: a board worker checks out the head it was dispatched for, and an old branch must not split the repository into two projects. The alternative, requiring every branch to carry the file, lost there and loses here.
- Other machines move their sessions when they pull the commit, or at once through the main-checkout rule once the main checkout has it.

### 1b. The scope widening, stated

Before this change a stray recorded nothing: `hooks/smns-record.sh` exits where the directory resolves to no project, the bridge's export (`sminos.export_live`) appends nothing, and `derive --all` covers members only. After it a stray on an enrolled machine is a member of its machine project, so its `<message>` spans and async asks are exported to that project's log and uploaded to the hub (the owner approved this on 2026-10-18), its presence is published to the hub, and `derive` covers it. `SMNS_INTERNAL` forks stay excluded everywhere (`sminos.internal_pids`, the hook's first line), as do headless and SDK runs (`HEADLESS_ENTRYPOINT`). On an unenrolled machine nothing widens.

## 2. `.smns` names the org; the enrollment knows the URL

- The shape for a new hub project is `{"project": "<uuid>", "name": "<name>", "remote": "", "hub": {"org": "ssfskim"}}`. The hub's URL comes from the machine's enrollment (`sminos_hub.enrolled_hub()`), so moving the hub never means editing committed files in three repositories. `sminos project init --hub` writes this shape from now on. `read_smns` and `hub_wellformed` accept a `hub` with `org` and no `url`; `resolve_project` fills the `url` from the enrollment on an enrolled machine, and the `Project.hub` every reader sees is `{url, org}` as before.
- A present `url` is tolerated (MAWS's `.smns` has one today). When it differs from the enrollment's, sminos warns once per project on this machine — a stderr line from the verb that first sees it and a `daemon.log` line, remembered as `warned_url` in the project's `uplink.json` — and never refuses: the enrollment's URL is used. Refusing would make a committed file an outage.
- On a machine not enrolled in the org the `.smns` names (no enrollment, or another org), the project is a **local project with a hub marker**: `Project.hub` is `{"url": "", "org": "<org>"}`, so `mirrored()` stays false and git never syncs it (a `remote` it names is the log's archive, as today), the uplink never opens it (`hub_projects` matches the org), and a reading verb prints once a day `project <name> syncs through the desk hub of org <org>; this machine is not enrolled (sminos hub enroll)`, remembered in the project's `daemon.json`. No sync at all for a hub project outside a hub: two transports were worse than none in the log design, and remain so.

## 3. Every enrolled machine follows every org project

- **The `org` frame** (Interfaces): the hub sends the org's directory down each machine's stream — every project the Registry holds, with its kind (`hub` or `machine`) and whether it is retired, and every enrolled machine with whether it is online and when it was last seen. It goes out on `welcome` (the `Machine` object asks the `Registry` for it as it opens the stream), again whenever the `Registry` registers a project, and whenever a machine's online state or enrollment changes. The uplink keeps the latest at `$SMINOS_HOME/daemon/org.json` with the time it arrived; `sminos projects`, `sminos machines`, and the filter layer read it.
- **Follow-only hellos.** For each project in the frame that this machine does not hold, the uplink writes a `project.json` with `root` `""` and the frame's name and hub, and opens it with `hello` carrying `follow: true`. A follow-only hello starts the machine's lease as any hello does (so the stream's heartbeats keep it and a half-open stream lapses), but the `Project` records `follow` on the lease, excludes such leases from `reportSummary`'s `machines` and `machines_online`, and a follower posts no `machine` presence and no session presence (it has none), so it is out of the project's `machines` frame. When a followed project gains a local member (a `join`, §7), the uplink's next scan sends `hello` again with `follow: false` and the machine's presence, and the hub updates the lease; when the last local member leaves, the next hello says `follow: true` again. The alternative, counting followers as machines of the project, lost because the grid's "2 machines" would then read "every enrolled machine" for every project and say nothing.
- **Eligibility** becomes "the project's `project.json` names this org's hub and is not retired", whether or not it has a root (`sminos_uplink.hub_projects`): with a root, the root's `.smns` must still name the hub (as today); with none, `project.json` alone decides. RPCs, Resume included, therefore work on rootless projects: a Resume names the session's real `cwd` from its `joined`, which the plane already uses.
- **`known_checkouts` returns `[]` for a machine project**, explicitly: a stray's working directory resolves to the machine project and would otherwise be offered as a checkout. So a desk spawn into `@<machine>` is refused `unknown-checkout`; a scratch-session spawn can come later.
- **Machine projects at the Registry.** The `Registry` registers a machine's project (`kind` `machine`, the machine's name) when the machine's enrollment is confirmed (its first authenticated request), computing the id as the Terms define it, so the project is on the grid and in the `org` frame before the machine's first hello; the machine's own uplink hellos it as a held project (its strays are its members). When a machine is revoked, its machine project is marked `retired` at the `Registry`: the `org` frame says so, every uplink stops following it (and removes it from its `hub_projects`), `sminos projects` hides it (shown with `--all`), and its `Project` object keeps the log for history.
- **Machines' online state at the Registry**, for `sminos machines` and the `org` frame: each `Project` already reports a summary to the `Registry` when its counts change (`reportSummary`); the report gains the project's machines with whether each is online (follow leases included, since a machine that only follows is still online), and the `Registry` keeps per machine whether any project reports it online and when that last changed (`seen`). Half-open streams lapse through the `Project`'s lease alarm as today, which changes the report. The alternative, the `Machine` object telling the `Registry` on stream open and end, lost because the `Machine` object knows only TCP open and close: a half-open stream (a suspended daemon) is detected by the lease, which lives in `Project`, and duplicating the lease and its alarm in `Machine` is a second state machine for the same fact.
- **Measured cost** (the critic's reading, 2026-10-18): the MAWS hub log is 364 KB (about 235 events), desk-walk 240 KB, local-doperpowers 1.5 MB; every project on the MacBook totals 3,195 events. After the backlog, live traffic grows only with message volume.

## 4. One list with filters, plus project and machine lists

Every list prints the same row:

    alias [short]  kind  state  @machine  project  repo@branch  in charge: … (age)  · active <age>

- `alias [short]`: the alias and the session's eight-hex short, always (today `#short` appears only on a collision; the short is how a session is reached org-wide, §5, so every row carries it).
- `kind`: `interactive`, `bg`, or `seat` (sminos spawned it); from the engine record locally, from `joined` remotely (`kind` travels on `joined` from M1 on; an older `joined` shows `?`).
- `state`: the word as today (`busy`, `idle`, `waiting`, `stopped`, `gone`, `vacant`, `retired`); for a remote member its last published word. **Liveness and the live word come from the engine records**: a member is live when an engine record names its session and its process runs (`session_running`), and its word is the record's `status`; only when no running record exists does the word fall to `stopped`/`gone` by the transcript. The inbox socket's answer decides delivery, never the word. This fixes #93's finding (board:646): `devcloud setup` read `stopped` in sminos while the engine's record said `interactive`/`idle`.
- `@machine`, `project`: as the log says.
- `repo@branch`: the owning repository's basename and the branch of the session's working directory; read live for a local row (`sminos_policy.git_branch`), from `joined`'s `repo` and `branch` for a remote one (as at join; a branch change is not republished — it is a detail, not a fact worth an event).
- `in charge: … (age)`: the in-charge line with the age of its event; `· active <age>`: the engine record's `updatedAt` locally, the last `state` event's `ts` remotely.

Verbs and filters:

- `sminos list` with no filters shows the caller's project, as today. `--json` carries the new fields (`kind`, `repo`, `branch`, `charge_age`, `active_age`, `project`, `project_kind`).
- Filters combine, each takes a comma list, and **any filter widens the scope to the whole org before narrowing it** (the org here is every project known on this machine, which on an enrolled machine is every org project, §3, and on an unenrolled one every local project):
  - `--project MAWS,doperpowers` (name or id; a machine project by its machine's name);
  - `--machine mini,devcloud`, where a name matches a machine by prefix, so `devcloud` matches every devcloud host;
  - `--state waiting,busy`;
  - trailing `<words>` match, case-insensitively, the alias, the short, the project, the repository, the branch, the in-charge line, the status ("now") line and the title.
- `--org` means no narrowing at all. `--here` is shorthand for `--machine <this machine>`; on an unenrolled machine it also lists, under `(no project)`, every running engine session whose directory resolves to no project — the sessions `ListAgents` shows and nothing else does. `sminos find <words>` is shorthand for `list --org <words>`. `--all` keeps its meaning (nothing folded).
- Rows are grouped under a project heading when one project is shown, and flat with the project column when several are.
- `sminos projects` lists every project known here: name, kind (`hub`, `machine`, `local`), its live and waiting counts, and the machines with sessions in it; a retired machine project only with `--all`. `sminos machines` lists every enrolled machine from `org.json`: `online` or `last seen <age>`, its live session count, and the projects it has sessions in; on an unenrolled machine it says so and lists this machine alone. Both read the logs this machine holds and `org.json`; the age of `org.json` is printed when it is older than a minute.
- **Inside a session, `sminos list` ends with the caller's subagent tree** (#93 item 4): the session's current subagents nested under their parents — agent id, type, status — the ids `SendMessage` takes. Live ones (running, or waiting on their own background work) are listed, as `ListAgents` lists them; finished ones fold into `+N finished`, and `--all` shows them with their ids, since `SendMessage` to a finished agent's id resumes it from its transcript. Read from the session's bridge when it answers (the child keeps every agent's spawn and whether it runs, `sminos_bridge.py`), else derived from the transcript as DX4's jobs ledger does (`sminos_jobs.py`).

Where this supersedes #93: #93's machine view `sminos list --here` is a filter shorthand here, not a view of its own; #93's "(no project)" group exists only on an unenrolled machine (on an enrolled one every session has a project).

## 5. Addressing: bare names stay in the project

- `@alias` searches the sender's project only. When no member answers there, the refusal lists the org's candidates — every member of every project known here whose alias matches — as `@<project>/<alias>#<short>` and, for a stray, `@<machine>/<alias>#<short>`, with the line `a bare name reaches only your project; @short reaches anyone`. Today's refusal says only "no member".
- `@short` and `@alias#short` resolve org-wide: an eight-hex prefix of a session uuid is unique enough across the org that the message goes where it points. A short matching two sessions is refused naming both with their projects.
- `@<project>/<alias>` resolves the project among every project known here (today: `find_project` by name or id), so a stray is `@mini/<name>`. **When an ordinary project and a machine share a name**, the ordinary project is read first, and the machine project only when the ordinary project has no member of that alias — the rule `find_target` already applies to a qualifier that is both a project and a seat group. A team names its project deliberately and a machine is named after a host, so the team is the likelier meaning; `@short` reaches the stray regardless. The hub refuses no such collision: a committed `.smns` must never fail to sync because a host shares its name, and a refusal at enrollment cannot be complete since projects register later. The alternative, refusing the tag as ambiguous, lost because it makes a whole project unaddressable by name for the sake of a case `@short` already covers.
- `@all` reaches the sender's project only, and is refused in a machine project (§1).
- There is no silent org fallback for a bare name: the board spawns the same seat names (architect, executor, reviewer) in every repository, so `@executor` from a repository without one would wake another repository's executor.

Where this supersedes #93: `send --session <name|short>` (#93 item 5) is not built; `@short`, `@alias#short` and `@<machine>/<alias>` reach a stray through the tag rules, recorded in both logs (§6). `sminos send`'s unrecorded raw-harness-name route (from no project, to a session in no project) is left for unenrolled machines, where it is still the only route to such a session; on an enrolled machine no session is in no project, so the route is never taken there.

Where this supersedes the log design: §2's "from a directory that is no project a name resolves across every project known locally" is dead letter on an enrolled machine (no such directory exists) and stands on an unenrolled one; `@project/name` crosses to any project known here, the followed ones included.

## 6. Recorded in both logs

- A cross-project `say` (or `send`) writes the **destination** event first, in the destination project's log under the sender's writer, with `from_project` the sender's project id (as today): that event delivers.
- Then it writes a **copy** in the sender's own log: the same `say` with `to` each recipient as `{session, alias, project}` and `copy` `"<destination project id>:<writer>:<seq>"` naming the delivering event. `_owed` skips any event carrying `copy`, so the copy delivers nothing and no one is woken twice. A copy that cannot be written (the destination's append succeeded, the sender's failed) is a stderr warning, not a failure: the message was delivered.
- Both are ordinary local appends, uploaded by the ordinary uploader; both machines' daemons and the hub see them as any event. A reply works the same way in reverse: the frame's reply line already names the sender as `@<from_project>/<short>`, so the recipient's `say` is a cross-project message too.
- This holds for strays, since every session has a synced project (§1): a stray recipient reads what it received with `sminos chat` in its machine project.

## 7. `sminos join <project>`

- `sminos join <project>` (a project name or id known here) declares the calling session's project. It writes `retired` with `reason` `moved` and `project` the new project's id in the old project's log, and `joined` with `by` `join` and the session's real `cwd` in the new one's; the machine's presence follows (the plane reads the log). `sminos join --cwd` removes the override and moves the session back to what its directory says, by the same path. `sminos join` with no argument prints the session's project and whether an override holds.
- The override is `$SMINOS_HOME/sessions/<session-uuid>.json`: `{"project": "<id>", "at": "<ts>"}`. It is removed only by `join --cwd` or another `join`; the daemon sweeps overrides whose session's transcript has not changed for 30 days.
- Hand-off (the log design §2) copies the override to the successor session, as it copies the cursor.
- Seats cannot join: a seat's project is its record's `cwd` (its spawner chose it), so `join` from a seat is refused with "a seat's project is where it was spawned".
- **One resolver, `session_project(session, cwd)`**, serves the record hook (`cmd_record`), the bridge export (`export_live`), `_local_sessions`, `seat_project`, the plane's presence (`Plane.refresh`), `caller_project` and `caller_scope`. It does not serve `known_checkouts`, which must keep reading each `joined`'s `cwd` through `resolve_project` so a joined-by-override session's directory is never offered as a checkout of the project it joined.
- Resume (the RPC) uses the real `cwd` carried on `joined`, as it does today.

## 8. Desk

- Machine projects appear on the grid like any project, labelled by kind (`ProjectSummary.kind`), and open to the same project view; a retired one is not drawn.
- A cross-project message is drawn in both timelines: the destination's event as today, with its origin (`from_project`) named; the sender's copy marked with its destination (`→ <project>`), never as a message to the sender's own group.
- **The org view**: every live session of every project on one screen, waiting on the owner first, then working, then idle; ended sessions are not drawn. It is built on desk-web's existing projection — `apps/desk-web/src/log/projection.ts` and `shell/sessions.ts` — **lifted over all project sockets**: the view acquires a `ProjectConnection` for every project on the grid (`project/registry.ts` already shares one connection per project per tab), runs `useDeskSessions` on each, and merges the groups. A row is the session's name (`sessionName`: title, else alias) with its alias, project, machine, and in-charge line; a click opens the project view on that session. The alternative, an org-wide presence table held by the `Registry` and streamed on the grid socket, lost because the `Registry` cannot name a session — alias, title and in-charge line live in each project's sealed log, which browsers verify with the org key the hub never holds — and would duplicate the lease and presence state the `Project` objects own. The cost is one socket per project (a handful) and each log's first load, which the IndexedDB log record already caches.

## 9. Guidance at session start

- A SessionStart injection, `hooks/smns-guide.sh` beside `smns-record.sh`, registered in `hooks/hooks.json` on `SessionStart` with matcher `startup|resume|clear|compact` (a compaction loses the context too). It prints nothing unless the machine is enrolled and the session is no internal fork, and then at most these lines, filled with the session's real values by `sminos guide` (a verb that prints the text, so the shell hook stays a few lines): who you are (alias `[short]`, project, machine); `sminos list` for your project, `--here` for this machine, `--org` for every session in the org, `find <words>`; `@short` and `@<project>/<alias>` reach anyone, `@alias` your project; `join <project>` when your work belongs to another project; set your in-charge line with `charge`; `SendMessage` is for your own subagents. The CLI is named by its installed absolute path, since `sminos` is not on `PATH`.
- Why this injection earns its place when the repository tore out the upstream SessionStart bootstrap (CLAUDE.md, `hooks/`): that bootstrap injected a skill index into every session on every machine — generic text the skills' own descriptions already trigger. This one carries facts the model cannot derive and that are false on most machines (that it has peers across machines, under which alias and in which project it is seen, and the two verbs that reach them), is gated to enrolled machines, and stays only as long as its evals show it changes behavior.
- It goes through `doperpowers:writing-skills` evals (#93's constraints): a model with the guidance finds and messages peers through sminos unprompted, including when `ListAgents` is denied; it still uses `SendMessage` for its own subagents; it can name its own subagent tree from `sminos list`; plus two new scenarios — it finds and messages the right session in another repository unprompted ("tell whoever is on the CI gate that …"), and it joins when its directory misfiles it ("you are working on MAWS from a scratch clone"). Only lines that move the evals stay.
- Once the evals hold, the owner adds `ListAgents` to `permissions.deny` in their settings with a CLAUDE.md note on how an agent views peer sessions instead. That is the owner's step, after M7, not a change this spec makes.

## 10. Channels: later

A channel will be its own log; whoever is tagged in it is a participant; it never limits reach. Deferred, and the reach rule is fixed now: in the prior art (a research pass of 2026-10-18 over Slack's shared-channels engineering posts, Matrix MSC1772/MSC3083, Zulip's topics, and the agent frameworks), Slack's shared channels made reach a two-sided approval and spent years undoing it with standing auto-approval; Matrix's spaces grant eligibility at join time and leave a known gap on leaving; Zulip's topics are a reading label that never drives delivery; among agent systems, Teams bots wake only on mention and no system scopes addressing to a channel. The directory therefore comes first, waking stays a tag's doing, and a channel, when it comes, is a place to read, not a wall.

## 11. What this revises in the log design

`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` stays the doctrine of the log; this spec supersedes these parts of it:

- **Terms, "Project"**: "a directory in no git repository is no project" holds only on an unenrolled machine; on an enrolled one such a directory's session is in the machine project (§1).
- **§1, resolution**: `resolve_project`'s outcomes gain the worktree rule (§1a) and, on an enrolled machine, the machine-project fallback in place of "no project"; `session_project` adds the join override ahead of the directory (§7). `spawn --cwd` into a project-less directory still registers a local project on an unenrolled machine; on an enrolled one the seats land in the machine project.
- **§2, addressing**: "from a directory that is no project a name resolves across every project known locally" is dead letter on an enrolled machine; `@project/name` reaches any project known here, followed ones included; a bare name's refusal lists the org's candidates; `@short` and `@alias#short` resolve org-wide (§5).
- **§3, the event table**: `joined` gains `kind`, `repo`, `branch` and the `by` values `join`/`move`; `retired` gains `reason` `moved` with `project`; `say`/`human` gain `copy` and `to[].project` (Interfaces and Dependencies).
- **§4, `send`**: its unrecorded raw-name route is never taken on an enrolled machine (§5).
- **§7, views**: `list`'s row and flags are §4's; `--all` keeps its meaning.
- **§9, "stays"**: the hub's `.smns` shape of the desk design (`hub: {url, org}`) becomes `hub: {org}` for new projects, `url` tolerated (§2).

Nothing else moves: the writer model, delivery, the mirror, the daemon's duties, the hub's log plane and RPCs stand.

## Acceptance

Run on an enrolled machine (`sminos hub show` names a machine) with `sminos daemon run` running, unless a step says otherwise. "The mini" is a second enrolled machine of the same org; the suites simulate it with two homes on one machine as `tests/sminos/test-sync.sh` does.

1. `sminos list --here` in any directory lists every session the harness's `ListAgents` lists on this machine (on the MacBook, 2026-10-18: 17 peers, `new-7e` in `/Users/new` and the bundle session in `~/claude-code-bundle` among them), each with `[short]`, a kind, and a state that agrees with `ListAgents`; a session the engine records as `idle` is never `stopped`.
2. In a doperpowers checkout, `sminos list` prints one heading, `doperpowers` (its committed `.smns`), with the members on both machines; `sminos list --org` prints every session of every project, flat, with the project column; `sminos find ci-kit` prints only the ci-kit sessions; `sminos list --machine mini --state waiting` prints the mini's waiting sessions and nothing else. Run inside a session with one running subagent, the list ends with that subagent's id, type and status and `+N finished`.
3. `sminos projects` lists `doperpowers`, `ci-kit`, `MAWS` as `hub`, each enrolled machine's project as `machine`, each with live and waiting counts and its machines; `sminos machines` lists every enrolled machine as `online` or `last seen <age>` with its session count and projects. Stopping the mini's daemon makes its row `last seen` within two minutes (the lease is three heartbeats, 45 s).
4. A session in `/Users/new` on the mini is listed as a member of `mini` (`sminos list --project mini`); its `<message>done</message>` appears in `sminos chat --host mini` on the MacBook after the mini's export; `sminos derive --all` on the mini covers it.
5. From a doperpowers session, `sminos say "@new-7e hi"` is refused naming `@mini/new-7e#<short>` among the candidates and pointing to `@short`; `sminos say "@mini/new-7e hi"` and `sminos say "@<short> hi"` each arrive in `new-7e` on the mini as a peer message whose last line is a reply line; `sminos chat doperpowers` shows the copy marked with its destination and `sminos chat mini` shows the delivering event; `new-7e`'s reply through the reply line arrives in the doperpowers session. `sminos say "@all x"` in `/Users/new` is refused.
6. In a scratch repository on the MacBook with a live session and no `.smns`, the session is a member of `macbook`; after `sminos project init --hub` is committed there, within one daemon interval `sminos list --project macbook` no longer lists it, `sminos chat macbook` shows `retired (moved to <name>)` for it, and `sminos list` in the repository lists it under the new project; a linked worktree of that repository at an older head resolves to the new project (`sminos project show` there). `sminos say "@macbook/<alias> hi"` is refused with `moved to <name>`; `@short` still arrives.
7. In the same session, `sminos join MAWS` moves it to MAWS (`sminos list MAWS` shows it with its real `cwd` in `--json`); `sminos join --cwd` moves it back; from a seat, `sminos join MAWS` is refused.
8. The new repository's `.smns` carries `{"hub": {"org": "ssfskim"}}` and no `url`; on an unenrolled machine (a temporary `HOME` and `SMINOS_HOME` with no `hub.json`), `sminos list` there prints the once-a-day hint, `sminos project show` says `hub (not enrolled)`, and no git sync runs even with a `remote` present.
9. On the desk, the org view lists every live session of every project with the sessions waiting on the owner first, each with its project and machine; `mini` and `macbook` appear on the grid as machine projects; a cross-project message shows in both projects' timelines, the copy marked with its destination. A desk spawn into `mini` is refused `unknown-checkout`.
10. Every eval of §9 passes in `evals/`; with `ListAgents` in `permissions.deny`, the model still finds its peers.
11. `tests/sminos/run-sminos-tests.sh` passes in doperpowers; in MAWS, `scripts/ci-gate.sh <worktree> --class1a linux` is green for M2 and M6.

## Execution

Constraints binding every milestone:

- doperpowers code: Python 3 standard library only in `skills/sminos/scripts/`; the stub-`claude` harness in `tests/sminos/run-sminos-tests.sh` (with `hub_standin.py` standing in for the hub and two homes for two machines) is the test substrate, extended, never replaced; every verb keeps its exit codes; `HOME`, `SMINOS_HOME` and `DAEMON_HOST` remain the overrides tests use, and **every run of a working copy's sminos, daemon, hook or mod uses a temporary `HOME` and `SMINOS_HOME`** — the suites isolate both, and a run against the real `~/.claude/sminos` performs a one-way import. Never call the deployed hub; never print `~/.claude/sminos/daemon/hub.json`, anything under `~/.config/claude-secrets`, or any `.env`.
- MAWS milestones (M2, M6) are built in MAWS worktrees of `/Users/new/Developer/GitHub/MAWS` and gated with MAWS's own `scripts/ci-gate.sh <worktree> --class1a linux` (class 1a — static, unit, probes — on Linux); the desk-web e2e never runs on a Mac. Hub changes keep `apps/desk-hub/src/protocol/` the one definition of every frame, typed, and `apps/desk-hub/fake-machine/` able to play a machine that follows.
- Protocol compatibility: an older daemon passes by a frame it does not know (`Link.dispatch` logs and ignores), and an older hub ignores `hello.follow` and `kind`; nothing here requires both sides to change at once, but M3 is built against M2's hub (its tests run against `hub_standin.py` extended to M2's behavior).
- Version: the last doperpowers milestone (M7) bumps the plugin with `scripts/bump-version.sh` in the same commit as its change (CLAUDE.md, "Version bumps"); docs-only commits take no bump. ci-kit's `.smns` is one commit in `/Users/new/Developer/GitHub/ci-kit` (a branch and a PR there), landed before M3 merges.
- Rules for every executor and reviewer: never `cd` (absolute paths, `git -C`), do not touch other worktrees or branches, no `Co-Authored-By`.
- The spec runs through `doperpowers:plan-executor` (seven milestones; M1 and M2 are independent, M3 follows M2, M4 and M5 follow M3, M6 follows M2 and M5, M7 follows all).

### M1 — Rows from the engine's records, the filter layer, `--here`, the subagent tree

What exists at its end: `sminos list` prints §4's row for every member — `[short]` always, `kind`, a state read from the engine records, `repo@branch`, the in-charge age, `· active <age>` — and takes `--project`, `--machine`, `--state` (comma lists), `--org`, `--here` and trailing words, any filter widening to every project known here; `sminos find <words>`; `kind`, `repo` and `branch` on every `joined` this machine writes from now on; inside a session the list ends with the caller's subagent tree, live agents nested, finished folded behind `+N finished` and shown by `--all`. On an unenrolled machine `--here` lists `(no project)` sessions from the engine records.

Touches: `skills/sminos/scripts/sminos.py` (`cmd_list`, `view_projects`, `list_row`, `state_column`, `member_json`, `joined_fields`, `_member`, `seat_state`/`state` for the engine-record liveness, the argparse of `list`, a new `find`), `sminos_jobs.py` (the subagent tree from a transcript), `sminos_bridge.py` (the bridge serves the agents it keeps), `tests/sminos/run-sminos-tests.sh`.

Interfaces: produces the row and its JSON fields (Interfaces and Dependencies, `sminos list --json`) and the `kind`, `repo`, `branch` fields of `joined`. Consumes nothing new.

Decisions: liveness is the engine record (`session_running`), and the word is `peer_state(rec)`; the socket probe stays delivery's (`peer_for_session`) — the two were one and #93's finding is the result. `--machine` matches by prefix on the member's `machine`; `--project` by name or id; words match a lower-cased concatenation of the fields §4 names. `--org` on an unenrolled machine is every local project. `--state` with several words keeps today's folding rule: a named word is shown even when `HIDDEN`. `--json` adds fields and removes none. The subagent tree's source is the bridge first (`GET /agents` on the session's endpoint, the child's `agents` as it keeps them from the mod's `agent` events) because it is live, and the transcript second because an older session has no bridge; a session with neither prints no tree.

Does not touch: tags, the hub, the uplink, `.smns`, the daemon.

Proves: acceptance 1 and the local half of 2; tests pin that a session the stub engine records as `idle` lists `idle` while its inbox socket is dead; that `--here` on an unenrolled home lists a `(no project)` session from a record; that `--state waiting,busy` from a project directory widens to a second project; that `find` matches the in-charge line and the branch; that a `joined` written now carries `kind`; that the tree folds finished agents and `--all` shows their ids.

### M2 — Hub (MAWS): the `org` frame, follow-only hellos, machine projects at the Registry, machines' online state

What exists at its end: a connecting machine receives, after `welcome`, an `org` frame listing the org's projects (kind, retired) and machines (online, seen), again on every registration and every machine online flip; `hello` takes `follow: true`, which the `Project` records on the lease and leaves out of `reportSummary`'s machine counts; the `Registry` registers a machine project when a machine's enrollment is confirmed and marks it retired when the machine is revoked; the `Project`'s summary report carries its machines' online state and the `Registry` keeps each machine's `online` and `seen`; `ProjectSummary` carries `kind`; the fake machine can follow.

Touches (MAWS, `apps/desk-hub/`): `src/protocol/machine.ts` (`DownFrame` `org`, `hello.follow`), `src/protocol/browser.ts` (`ProjectSummary.kind`, `MachineSummary`), `src/protocol/identity.ts` (`ProjectRecord.kind`, `machineProjectId`), `src/objects/registry.ts` (`projects` and `machines` columns, `orgFrame`, `summary` with machines, `toMachines`, registration at confirmation, retirement at revocation), `src/objects/machine.ts` (`org` after `welcome`), `src/objects/project.ts` and `session-store.ts` (`Lease.follow`, `reportSummary`), `fake-machine/`, `test/`.

Interfaces: produces the `org` frame, `hello.follow`, the machine project id function, `ProjectSummary.kind` (Interfaces and Dependencies). Consumes nothing new.

Decisions: the machine project's id is computed on the hub side with the same UUID v5 (namespace URL, name `smns-machine:<org>:<lower-cased machine>`) — pinned by a vector in `src/protocol/vectors/` that `tests/sminos/` reads too, since two implementations must agree. A machine project is registered at enrollment confirmation and, for a machine enrolled before this change (the owner's three are), at the machine's first `hello` of it: `registerProject` recognizes the id of an enrolled machine's project and records `kind` `machine` whichever path registers it first. The `Registry` reaches a machine's stream through its `Machine` object's `send`, which answers `offline` when none is open: an `org` frame to an offline machine is simply not sent, since the next `welcome` carries the directory whole. `seen` is the time of the latest report that had the machine online; an online machine's `seen` is when it came online. A follow lease renews and lapses like any lease. A retired project's `Project` object refuses no hello (a machine may still hello it from a stale `org.json`) but its summary is dropped from the grid.

Does not touch: desk-web (M6), the daemon.

Proves: acceptance 3's hub side and 9's grid half; tests pin that the first frame after `welcome` is `org` with every project and machine; that a project registered while a machine is connected sends it a new `org`; that a `hello {follow: true}` leaves `machines` and `machines_online` unchanged and `machines` (the frame) without the follower while the lease is fresh; that a follower's lapse (no `hb-ack` for three periods) flips the `Registry`'s `online` and sends `org`; that a revoked machine's project is `retired` in the next `org`; that the vector's id matches the Python side's.

### M3 — Every enrolled machine follows every org project; machine projects; the org-only `.smns`; doperpowers' and ci-kit's `.smns`

What exists at its end: the uplink keeps `org.json`, follows every org project it does not hold (follow-only hello, rootless `project.json`), re-hellos as `follow: false` when a followed project gains a local member; `resolve_project` falls to the machine project on an enrolled machine; `.smns` with `hub: {org}` resolves with the enrollment's URL, a differing `url` warns once, an unenrolled machine reads it as local with a hub marker and the daily hint; `known_checkouts` is `[]` for a machine project; `@all` is refused there; `sminos projects` and `sminos machines`; the worktree-predating rule; doperpowers' committed `.smns`, and ci-kit's (its commit landed first). Strays are members of their machine project, so the hook, the export and `derive` cover them (§1b).

Touches: `sminos.py` (`read_smns`, `hub_wellformed`, `resolve_project`, `make_project`, `machine_project`, `known_projects`, `cmd_project`, new `cmd_projects`, `cmd_machines`, `resolve_tags` for `@all`), `sminos_uplink.py` (`hub_projects`, `Link.on_org`, `open` with `follow`, `machine_presence`), `sminos_hublog.py` (`hello(follow)`), `sminos_policy.py` (`known_checkouts`), `sminos_daemon.py` (the hint, `shared`), `tests/sminos/hub_standin.py` (the `org` frame, `follow`), `tests/sminos/test-uplink.sh`, `test-hub.sh`, `run-sminos-tests.sh`, this repository's `.smns` at its root, `skills/sminos/SKILL.md` (the `.smns` shape), and `.smns` at the root of the ci-kit repository.

Interfaces: produces `machine_project(org, machine)`, `session_project`'s step 3 input (the machine project), `org.json` (Interfaces and Dependencies), `cmd_projects`/`cmd_machines`. Consumes M2's `org` frame and `hello.follow`.

Decisions: a followed project's `project.json` has `root` `""`, `name` from the frame, `hub` `{url, org}` from the enrollment, and `followed: true`; `hub_projects` admits a rootless entry by `project.json` alone and drops one the frame marks retired. Held versus followed is decided at each scan: held when `known_checkouts(project)` is non-empty or the plane's local members are, else followed; the machine's own project is always held. The uplink registers this machine's own project locally (`machine_project` through `project_path`) at every scan, so it is hello'ed on the first stream whether or not the hub has listed it yet — that hello is what registers it at a hub whose machine enrolled before M2 (M2's decisions); `resolve_project`'s fallback writes the same `project.json` when a stray comes first (`project_path` is idempotent). `read_smns` on an unenrolled machine returns `hub {"url": "", "org": "<org>"}` — the existing "a hub project nothing feeds" branch, now the intended shape rather than a warning; the warning text becomes the daily hint. The doperpowers `.smns` is minted with `sminos project init --hub` in the worktree (a fresh uuid4), and ci-kit's likewise in a ci-kit worktree; their ids are whatever `init` mints. `shared()` stays true for a hub project on an unenrolled machine (states published into a local log cost a few events and keep the log identical once the machine enrolls).

Does not touch: tags beyond `@all`, `join`, the desk.

Proves: acceptance 3 (the CLI side), 4, 8; tests pin, with two homes and the stand-in: that a session in a bare temporary directory on the enrolled home is a member of the machine project and its `<message>` reaches the stand-in; that a project the stand-in's `org` frame names and neither home holds is opened `follow: true` and a message tagged into it from the enrolled home lands in its log; that `known_checkouts` of the machine project is `[]` and a spawn RPC into it is refused `unknown-checkout`; that `.smns` with `hub: {org}` resolves with the enrollment's URL and a differing `url` warns exactly once across three verbs; that an unenrolled home reads the same file as local with the hint once a day and runs no git; that a linked worktree without the file resolves to the main checkout's; that `@all` in the machine project is refused.

### M4 — `sminos join`, `session_project`, moves when a resolved project changes

What exists at its end: `sminos join <project>`, `join --cwd`, `join` alone; the override file and its sweep; `session_project(session, cwd)` serving every consumer §7 names; a `.smns` appearing or disappearing under a live session moves it within one tick; hand-off copies the override; seats are refused.

Touches: `sminos.py` (`session_project`, `cmd_join`, `caller_project`, `caller_scope`, `seat_project`, `_local_sessions`, `_reconcile` for `moved`, `hand_off`, `cmd_record`, `export_live`), `sminos_daemon.py` (`tick_all`'s session map, the override sweep), `sminos_plane.py` (`refresh`), tests.

Interfaces: produces `session_project`, the override file, the `retired` `moved` fields and `joined` `by` `join`/`move` (Interfaces and Dependencies). Consumes M3's machine project.

Decisions: `_reconcile(project, …)` retires a live local member whose `session_project` is now another project with `reason` `moved`, `project` the new id, and `by` `""`; the new project's reconciliation joins it as a live session whose project it is (the existing on-sight rule, with `session_project` in place of `resolve_project(cwd)`), `by` `move` when the join follows a move and `join` when `cmd_join` writes it directly. `cmd_join` writes the override, then runs both projects' reconciliation itself, so the move is visible before the verb returns. A `join` naming the session's current project is a no-op that says so. The sweep runs in the daemon's hourly duties beside `derive`, by the transcript's mtime (`transcript_path`), and removes only the file. A `moved` retirement holds against re-join by construction: on-sight joins only where `session_project` resolves.

Does not touch: tag resolution, the copy, the desk.

Proves: acceptance 6 and 7; tests pin that a `.smns` written into a live session's repository moves it on the next tick with `retired (moved)` in the old log and `joined (by: move)` in the new; that removing the file moves it back; that `join` from a seat is refused; that an override survives a `.smns` appearing; that hand-off (a `continued-in` record) carries the override to the successor; that an override whose transcript is 31 days old is swept and a 29-day one is not.

### M5 — Addressing across the org and the copy in the sender's log

What exists at its end: §5's resolution — bare names in the sender's project with a refusal that lists the org's candidates, `@short` and `@alias#short` org-wide, `@<project>/<alias>` with the machine-project fallback, `moved to <project>` refusals; §6's copy with `copy` and `to[].project`, skipped by `_owed`; `send` on an enrolled machine never takes the raw-name route.

Touches: `sminos.py` (`resolve_tags`, `match_members`, `name_scope`, `unreachable_hint`, `cmd_say`, `record_message`, `_owed`, `_send`, `find_target`), `sminos_control.py` if the frame's reply line needs the destination id (it already carries `from_project`), tests.

Interfaces: produces the `copy` event shape (Interfaces and Dependencies). Consumes `session_project`, the machine project.

Decisions: the org-wide scope for `@short` is every project known here (followed ones included), read from their logs; a short matching sessions in two projects is refused naming both as `@<project>/<alias>#<short>`. The copy is written after the destination event and carries the same `text`, `from`, and `ts`; `chat` prints a copy with `→ <project>` after the target, and `unread` does not count copies. `to[]` entries gain `project`: the hub carries events verbatim and types them open (`LogEvent = JsonObject & …`), and desk-web's readers of `to` take `session` and `alias` and pass over other keys — M6 confirms. `_owed`'s skip is by the `copy` key alone, so an older reader (one without this change) would deliver a copy to no one either: its `to` names recipients of another project's log, which that reader never finds in this one.

Does not touch: the desk, guidance.

Proves: acceptance 5; tests pin, with two homes: that `@alias` from project A for a member of B is refused naming `@B/alias#short`; that `@short` and `@B/alias` deliver and both logs hold the events, the sender's with `copy` naming the destination's position; that the copy is never pushed (the recipient's socket sees one frame); that a reply through the frame's reply line lands in A with its copy in B; that `@<machine>/<alias>` reaches a stray and `@<name>/<alias>` with a same-named ordinary project resolves to the ordinary project's member first; that `send` from an enrolled home never calls `send_frame` by raw name.

### M6 — Desk (MAWS): the org view, outbound copies in both timelines, machine projects on the grid

What exists at its end: an "All sessions" entry on the desk opens the org view — every live session of every project, waiting on the owner first, then working, then idle, each with name, alias, project, machine and in-charge line, a click opening the session in its project; machine projects on the grid labelled by kind, retired ones absent; cross-project messages drawn in both timelines, the copy marked with its destination and the destination's event with its origin.

Touches (MAWS, `apps/desk-web/src/`): `shell/layout.ts` (the `org` view), `views/grid/GridView.tsx` and `ProjectCard.tsx` (kind, the entry), a new `views/org/OrgView.tsx` on `shell/sessions.ts` and `project/registry.ts`, `views/project/ChannelView.tsx` or its message components (copy and origin marks), `log/projection.ts` only if the copy needs a field, tests beside each.

Interfaces: consumes `ProjectSummary.kind` (M2) and the `copy` event (M5). Produces nothing another milestone consumes.

Decisions: the org view acquires every project's connection while it is mounted (`acquireProject`/`releaseProject`) and releases them on leave; a locked tab (no org key) shows the grid's counts and no rows, as the sidebar does. Sorting within a group is newest `joinedAt` first, as the sidebar sorts. A copy is told by its `copy` key and drawn in the sender's timeline with `→ <destination project name>` (from the grid's names); the destination's event is drawn with `from <origin project name>` when `from_project` names another project.

Does not touch: the hub, sminos.

Proves: acceptance 9 (the web half); unit tests pin the merge and order of groups across two fake connections and the copy/origin marks; an e2e spec it adds runs on the Linux lane (`scripts/ci-gate.sh … --runner linux`), never on a Mac.

### M7 — Guidance at session start, its evals, documentation, release

What exists at its end: `hooks/smns-guide.sh` on `SessionStart` and `sminos guide`; the eval set under `evals/` for the scenarios §9 names, with before/after results recorded in this spec's Surprises & Discoveries; `skills/sminos/SKILL.md` and `CLAUDE.md`'s repo map updated (the directory, the filter layer, `join`, machine projects, the org-only `.smns`, the guidance hook); the plugin version bumped; the acceptance section run as written.

Touches: `hooks/smns-guide.sh` (new), `hooks/hooks.json`, `sminos.py` (`cmd_guide`), `skills/sminos/SKILL.md`, `CLAUDE.md`, `evals/`, `tests/claude-code/` (the hook's shape, as `test-to-human-stream-hook.sh` tests a hook), the manifests through `scripts/bump-version.sh`.

Interfaces: consumes everything above.

Decisions: the hook follows `smns-record.sh`'s shape — `set -uo pipefail`, one `read`, exit 0 on every path — and hands the SessionStart payload to `sminos guide` on stdin, printing what it prints; `sminos guide` reads `session_id` and `cwd` from the payload as `record` does (a hook's environment does not carry `CLAUDE_CODE_SESSION_ID`), and prints nothing on an unenrolled machine, under `SMNS_INTERNAL`, or for a payload naming no session, so the gate lives in one place. Its first line names the session as the directory sees it now (alias `[short]`, project, machine), so a stray reads that it is in `@<machine>` and a misfiled session reads which project it is in. The text is authored with `doperpowers:writing-skills`, run through its pressure tests, and cut to the lines that move the evals. The owner's `permissions.deny` entry is reported as the next step, not made.

Does not touch: the hub, the desk.

Proves: acceptance 10 and 11, and runs acceptance 1–9 as written on the owner's machines (the real two-machine run) with the transcript recorded in Surprises & Discoveries.

### Concrete Steps

In `/tmp/smns-org-dir` (doperpowers, branch `smns-org-directory`):

    tests/sminos/run-sminos-tests.sh                    # all parts; or SMINOS_PART=core | suites
    tests/sminos/test-uplink.sh; tests/sminos/test-hub.sh; tests/sminos/test-sync.sh
    scripts/lint-shell.sh hooks/smns-guide.sh
    scripts/bump-version.sh                             # M7 only, in the same commit as its change

Expected: each suite ends with `N passed, 0 failed` and exit 0. A CI-grade run of a commit: `ci-gate` from the worktree (the `sminos` and `sminos-suites` gates).

In a MAWS worktree (`git -C /Users/new/Developer/GitHub/MAWS worktree add <path> -b <branch> origin/master`):

    pnpm --filter desk-hub typecheck && pnpm --filter desk-hub test     # M2, local
    pnpm --filter desk-web typecheck && pnpm --filter desk-web test     # M6, local
    scripts/ci-gate.sh <worktree> --class1a linux                        # the gate: static, unit, probes on Linux

Expected: `GREEN <run-url>`. The desk-web e2e is a Linux lane; never run it on a Mac.

A live check on the owner's machines (acceptance 1–9) runs the installed plugin, never a working copy against the real `SMINOS_HOME`; a working copy's CLI is run only under a temporary `HOME` and `SMINOS_HOME`.

### Interfaces and Dependencies

**The `org` frame** (hub → machine, `apps/desk-hub/src/protocol/machine.ts`, `DownFrame`):

```ts
| { t: 'org'; projects: Array<{ id: string; name: string; kind: 'hub' | 'machine'; machine?: string; retired: boolean }>;
    machines: Array<{ name: string; online: boolean; seen: string | null }> }
```

Sent after `welcome` on every stream, on every project registration, on every change of a machine's `online` or enrollment. `seen`: ISO 8601 UTC with milliseconds, when the machine was last reported online (null: never).

**`hello`** gains an optional flag (`UpFrame`):

```ts
| { t: 'hello'; project: string; name: string; have: Vector; follow?: boolean }
```

`follow: true`: the machine holds no checkout and no session of the project; its lease counts toward no machine count and it posts no presence. Absent or false: as today.

**The summary report** (`Project` → `Registry`, `Registry.summary`): `counts` gains `machines_state: Array<{ name: string; online: boolean }>` — every leased machine, followers included, with whether its lease is fresh. `ProjectSummary` (`protocol/browser.ts`) gains `kind: 'hub' | 'machine'`.

**The machine project id**, in both implementations:

    Python: uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:%s:%s" % (org, machine.lower()))
    TS:     uuid v5 over the URL namespace of the same string (a small implementation in protocol/identity.ts; pinned by protocol/vectors/machine-project.json, which tests/sminos/ reads too)

**`org.json`** (`$SMINOS_HOME/daemon/org.json`): the latest `org` frame's `projects` and `machines` plus `at` (when it arrived, ISO 8601 UTC).

**`project.json`** of a followed project: `{"project", "name", "remote": "", "root": "", "hub": {"url", "org"}, "followed": true}`; `retired: true` once the frame says so.

**`session_project(session: str, cwd: str) -> Project | None`** in `sminos.py`: §1's order. `machine_project(org: str, machine: str) -> Project`: the machine project of this machine (`Project` with `root` `""`, `hub` from the enrollment). `resolve_project(cwd)` keeps its signature and gains the worktree rule and the machine-project fallback; `session_project` adds the override.

**The join override** (`$SMINOS_HOME/sessions/<session-uuid>.json`): `{"project": "<project id>", "at": "<ts>"}`.

**Log events** (additions to the log design §3's table):

| kind | new fields |
| --- | --- |
| `joined` | `kind` `interactive`/`bg`/`seat`; `repo` the owning repository's basename (`""` outside one); `branch` (`""` when detached or none); `by` may be `join` or `move` |
| `retired` | `reason` `moved` with `project` the new project's id |
| `say`, `human` | `to[]` entries may carry `project` (the recipient's project id); `copy` `"<project id>:<writer>:<seq>"` marks the sender's copy of a cross-project message; `from_project` as today |

**`sminos list --json`** rows gain: `kind`, `repo`, `branch`, `charge_age` (seconds, or null), `active_age` (seconds, or null), `project`, `project_id`, `project_kind`.

**CLI**:

    sminos list [project] [--project P,…] [--machine M,…] [--state W,…] [--org] [--here] [--all] [--json] [words…]
    sminos find <words…>                   # list --org <words>
    sminos projects [--all]
    sminos machines
    sminos join <project> | --cwd | (none)
    sminos guide                           # the SessionStart text, or nothing

**The guidance hook**: `hooks/smns-guide.sh`, `SessionStart`, matcher `startup|resume|clear|compact`, prints `sminos guide`'s stdout.

## Surprises & Discoveries

- Observation: `known_checkouts` would offer a stray's home directory as a checkout of the machine project, because it admits every `joined` cwd that resolves to the project.
  Evidence: `skills/sminos/scripts/sminos_policy.py`, `known_checkouts`: `p = sminos.resolve_project(cwd); if p is not None and p.id == project.id: paths.append(cwd)`. Hence §3's explicit `[]` for a machine project rather than relying on "it has no root".
- Observation: a project that appears (a `.smns` committed under a live session) is not visited by the daemon until something resolves it, because `tick_all` iterates `known_projects()`, which lists only projects with a `project.json` or a seat.
  Evidence: `sminos.known_projects` reads `projects/*/project.json` and the seats; `project_path` writes `project.json` on first use. Hence §1a's first step of each tick.

## Decision Log

- Decision: the verification this spec gets. One independent design review by a general-purpose subagent at model fable; the `doperpowers:adversarial-reviewer` buildability review of the execution section, dispatched in the same round; at the end, the branch review at doperpowers:review-code's xhigh panel, since the change is cross-repo (doperpowers, MAWS, ci-kit) and large.
  Rationale: the design is approved and the technical surface spans two codebases and a wire protocol; the stakes warrant the panel.
  Date/Author: 2026-10-18, the authoring session.
- Decision: the residuals the design left to the spec, settled here — the machine project's name is the machine's name and `@<name>/alias` reads the ordinary project first (§5); the `Registry` learns machines' online state from the `Project` summaries, not the `Machine` object (§3); the `org` frame goes out on welcome, registration, and online flips (§3); follow-only hellos carry `follow: true` and are leases without presence (§3); a differing `.smns` `url` warns once per project per machine (§2); an unenrolled machine's hub `.smns` is local with a hub marker, git barred (§2); the scope widening is stated (§1b); the `.smns` files land in M3 with the fallback (§1); moves run on the tick with a per-session map first (§1a); the org view is lifted over all project sockets (§8); the guidance earns its place by carrying facts the model cannot derive, gated and eval-bound (§9). Each section names the losing alternative.
  Date/Author: 2026-10-18, the authoring session.
- Decision: the owner's decisions of 2026-10-18 are recorded in "Owner decisions" with their times (the scope revision at 11:55Z, the filter layer at 13:00Z, §1a at 13:05Z, the final approval); board #93's answers (board:643) are folded in and the two places this design supersedes #93 are named in §4 and §5.
  Date/Author: 2026-10-18, the authoring session.

## Outcomes & Retrospective

Pending — written at finish.
