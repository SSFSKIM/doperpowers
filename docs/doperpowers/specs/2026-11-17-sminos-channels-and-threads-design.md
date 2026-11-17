# sminos: channels and threads (2026-11-17)

> **Parent:** root — the sminos plugin's standing purpose (`sminos/CLAUDE.md`, its first paragraph; design `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`). **Consumes:** the research under `docs/doperpowers/research/2026-11-17-sminos-channels/` (`prior-art.md`, `code-map.md`, `bg-resume-experiment.md`), and MAWS's desk design (2026-10-15) and project registry design (2026-11-10), in that repository's `docs/doperpowers/specs/`. This document is the design the owner approved on 2026-11-17, extended in place with its roadmap: the design up top, the children below. Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact (plan, ledger, findings, PR) opens by citing this document (path + child id + parent pin).

## Purpose

sminos connects one owner's Claude Code sessions across repositories and machines, so that the sessions coordinate as a team and the owner supervises them as one. Three things about how it does that today are wrong, and each was observed on the owner's fleet on 2026-11-17 (Grounding Baseline):

1. **The unit of coordination is where a session was launched, which is not whom it works with.** A coordinator and the session it directs sit in different projects; three sessions on one branch are split between two machines' projects.
2. **Standing responsibilities are not durable.** A session the owner opened stops being a member when its process ends, and no message wakes it. Only a session another session spawned stays and is woken.
3. **Where a session runs is not a choice.** A spawned session opens on its spawner's machine, and most of the fleet runs on one overloaded Mac.

After this work:

- **Every member is a thread.** It keeps its identity when its process ends, a message addressed to it wakes it in the background, and it ends only when it is retired or has been stopped for more than three days.
- **A channel is a named set of threads with a log of its own,** created with one command, crossing repositories and machines. One command places any number of threads in it, and no session has to act to be placed. A thread is in any number of channels.
- **A thread can be opened on another machine,** a new cloud VM included, with one command; the thread that made a VM owns it.

How to see it working is the scene in Parent-Level Acceptance.

**What it must not become.** These are the owner's rulings and bind every child:

- *An owner.* A channel owns no lifecycle and no machine. The owner's words: "채널은 그냥 machine pool과 연관된 repo들, 그리고 그 채널에 속한 세션들만 가지고 있으면 된다" (a channel only has to hold a machine pool, the related repositories and the sessions in it).
- *A hierarchy.* "리드 없음 -- 모든 멤버가 sibling이다" (no lead; every member is a sibling). Coordinators emerge from the work; none is defined.
- *A permission boundary.* Who may read or reach a thread stays a property of the thread.
- *A second surface.* No MCP tools. The CLI is the one way in.
- *A scheduler.* No default placement and no autoscaler.
- *Something a session must act on to be placed.* "세션이 직접 channel join을 할 필요가 없다" (a session need not join a channel itself).

MAWS, the owner's desktop app that shows sminos's sessions, will later show this model as its channel interface. That view is a later design; this document is the model it will show.

## Parent-Level Acceptance

The unit closes when this scene runs on the owner's fleet, on released versions, and each numbered line is observed. "A" is a thread in one repository on a Mac; "B" is a thread the owner opened in another repository, in a terminal, in `auto` mode.

1. A runs `sminos channel create desk-integration` and `sminos channel add desk-integration <B>`. Neither B nor its human does anything. `sminos list` run by A and by B shows `# desk-integration` beside each one's project, with both threads in its roster.
2. A runs `sminos say --in desk-integration "@<B> ..."`. B receives it framed as coming from that channel, and B's reply lands in that channel's log without B naming it. A `say` with no `--in`, from either, lands where it does today.
3. The owner closes B's terminal. `sminos list --stopped` shows B as `stopped`, in its project and in the channel. A sends B an addressed message: within two minutes one background process holds B's session id, under the permission mode and model B last ran with, and no copy of the session exists. B's first line of that turn says it was woken in the background and its human is not watching. The owner runs `claude --resume <B's session>` in a terminal and is attached to that same process.
4. A thread C whose last mode asks for approval (`default`, `plan` or `acceptEdits`) is closed. A's `sminos say "@<C> ..."` reports, when it is sent, that C is stopped and will not be woken, and why. No process starts. C receives the message when its human reopens it.
5. A runs `sminos spawn --on new --channel desk-integration <alias> <task>`. A devcloud VM is made under devcloud's own caps and consent rules, and a thread opens on it and appears in the channel. `sminos channel show desk-integration` lists the VM in the channel's pool with A as its owner, its age and its cost. `sminos retire <A>` is refused and names the VM. After `devcloud vm down` of that VM (or a handover with `devcloud vm owner`), the retire succeeds.
6. A thread stopped for more than three days is ended: `sminos list` and `sminos list --stopped` no longer show it, `--all` does, and a message addressed to it reports that it has ended. Reopened, it is listed under the alias, in-charge line and channel memberships it had.
7. A runs `sminos channel remove desk-integration <B>`: B leaves the roster and is not retired. When the last member that has not ended is removed or ends, the channel leaves `sminos list --org`.
8. A session that never uses a channel sees no change: every suite that passed before passes, and `say`, `list`, `spawn`, `join` and `retire` behave as they did, apart from lines 3, 4 and 6 above.

## Grounding Baseline

**The fleet, 2026-11-17** (`sminos list --org`, `sminos machines`, `devcloud vm ls`): 29 live sessions. 19 run on one Mac, whose load average was 38 to 42 during this design's own experiment. A coordinator is filed in one repository's project and the seat it directs in another's, on a VM. Three sessions on one branch are split between two machines' own projects. One session serves four repositories from the project of the one it was launched in. One machine's own project holds six unrelated sessions. One VM made for a seat had been kept for 20 days at a cost above 100 euros, its creator recorded as a session id.

**The code, at `main` 601b8e9d** (`code-map.md` has the line-level map; `S/` is `sminos/skills/sminos/scripts/`):

- *One project per session is enforced in three places, not throughout:* `session_project` (one project: the `join` override, else the launch directory), the override file (`override_path`: one id), and `_reconcile`, which retires `moved` every membership that is not the resolved one. Everything else is computed per log and keyed `(project, session)`.
- *A seat and a seat-less member differ in these paths* (all in `S/sminos.py`):

  | Path | Seat (a spawned session) | Seat-less (a session the owner opened) | Function |
  |---|---|---|---|
  | Process gone | stays a member, reads `stopped` | retired `ended`; joins again if it runs again | `_reconcile` |
  | Addressed message while stopped | resumed: `claude --bg --resume` | recorded, never resumed | `push_member`, `push_event` |
  | `retire` | record `retired`, process stopped | event only, holds for the process's life | `_retire_one`, `cmd_retire`, `retirement_holds` |
  | Alias | fixed at spawn | the engine's name, else the held alias | `held_alias`, `join_on_sight` |
  | Project | its directory's; `join` refused | the override, else the launch directory | `seat_project`, `cmd_join` |
  | Hand-off to a background job | `follow_seat` moves the seat | override and cursor carried | `hand_off`, `predecessor`, `continued_in` |

  `sminos seat add <group> <alias> --session <id>` (`cmd_seat_add`) already gives a running session the owner opened a seat.
- *Today's resume passes no flags* (`resume_session`; `claude_args` launches a spawned seat with `--permission-mode auto`).
- *The log plane is per log already:* the hub creates a log for any id of UUID shape a machine says hello for, and every key on both sides is `(project, writer, seq)`.

**The engine, Claude Code 2.1.326** (`bg-resume-experiment.md`). These are measured facts the wake is built on:

| # | Fact |
|---|---|
| E1 | `claude --bg --resume <id> <message>` on a session that has only run in a terminal continues the same session id, under the settings' defaults (`permissions.defaultMode`, `model`), not the options its terminal process was launched with. |
| E2 | That first background resume accepts flags (`--permission-mode` and `--model` were tried) under the same id and saves them. A later background resume continues under the saved options; given any flag it starts a copy under a new id and prints "started a copy as". |
| E3 | `claude --bg --resume` on a session that any process holds, terminal or background, starts a copy and says so. |
| E4 | `claude --resume <id>` in a terminal, on a session whose background process is live, attaches to that process. There is one process. |
| E5 | Three signals show a process holding a session, and agreed in every check: `claude agents --json`, `~/.claude/sessions/<pid>.json`, and the sminos bridge's socket for the session. |
| E6 | In a mode that asks for approval, a background session waits at its first tool call (`waitingFor: "permission prompt"`; five and a half minutes observed, no timeout seen). |
| E7 | A stopped background session reopened with `claude --resume` in a terminal runs as an interactive process under the interactive defaults, same id. |

Not established, and assigned under Delegated unknowns: how the engine decides that a session has saved options, what `claude rm` or the expiry of the engine's row does to them, which other launch options a first background resume accepts, and whether the owner is notified that a background session waits at a prompt.

## Terms

- **The owner.** The person whose sessions these are.
- **Project.** A repository's identity and its locations on machines, as MAWS's project registry defines it. Every session has exactly one, read from the directory it was launched in unless it declared another with `sminos join`.
- **Log.** A project's append-only record, one file per writer, which the machines of the org sync through the hub. A **writer** is `<machine>/<session>`; only that machine appends to it.
- **Member.** A session that has joined a project's log. **Seat** is today's word for a member with a record that outlives its process, which is what `sminos spawn` makes.
- **Thread.** What every member becomes (D1).
- **Channel.** A named set of threads with a log. A project's log is the **automatic channel** of the threads whose project it is, unchanged by this work. A **declared channel** is created with `sminos channel create`, crosses projects, and has the members it was given. "Channel" alone means a declared one below.
- **Pool.** The machines a channel's threads run on, plus machines added to it by hand. Derived, like a channel's repositories (those its members work in).
- **Environment.** A machine and a location on it: a property of the session that fills a thread.
- **The daemon.** sminos's background service on each machine (`sminos daemon`). It delivers messages, resumes stopped seats, and keeps the machine's connection to MAWS.
- **The hub** (MAWS's desk hub) keeps every log of the org. **The endpoint** is the MAWS process on a machine that connects sminos to the hub. **RL10** is the protocol between sminos and the endpoint; its `member` frame states one session and its project. A **capability** is a named feature each side advertises, so that neither sends the other a shape it does not know.
- **Reach.** Who may read a thread and send to it: its access level, its shares, its owners. A session record's property.
- **Lane B.** A session MAWS itself launched and reopens. Every other session is lane A.
- **A wake.** The daemon starting a background process for a stopped thread because a message was addressed to it.
- **devcloud.** The plugin that makes and deletes cloud VMs (`devcloud vm up|down|ls|owner`), with caps on how many may exist unconfirmed.

## Design

Decisions marked **[binding]** were settled with the whole picture in view, or are the owner's; a child does not reopen them and reports evidence against one to the session holding this document. Everything unmarked is advisory: a child starts from it and may overturn it with evidence, recording the overturn in the Decision Log.

### D1. Threads

**Every member is a thread** **[binding — the owner: "모든 세션이 seat형 스레드"]**. A thread takes four things from today's seat: a durable identity, staying a member when its process ends, being woken by an addressed message, and ending only by a retire or the three-day rule. It does not take a seat's fixed alias or fixed project: a session the owner opened is still named after what it is in charge of, and `sminos join` still moves it. *Alternative: keep seats and seat-less members and let a channel hold both.* It lost because the durability fault is exactly that difference: the fleet's standing responsibilities are sessions the owner opened.

**The record.** Every member gets a thread record at its first join, on its own machine: a thread id, its alias, its declared channel memberships (D3), the machines it owns (D4), and what its process was launched with and last ran under (D2). The thread id is stable across the thread's session ids and never reused; it is what other parts name a thread by when the name must outlive a session id. Its form, and whether the record extends the seat record or stands beside it, are T1's (contract X1).

**Continuation** **[binding — a continuation carries its predecessor's owners and reach (`lineage_provenance`, `ensure_record`), so a wrong one is a privacy fault that cannot be undone]**. A thread moves to a new session id in two cases only:

1. A session start whose source is `clear`, under a new id that has no record, in the process that held the old id.
2. The engine's hand-off to a background job, by the record the engine leaves for it (`continued_in`, `hand_off`).

An in-session `/resume` and a fork are other threads. A fork's start guide says so, since its transcript claims to be the original. *Alternative: "the same process, therefore the same thread."* It lost because one process can resume an unrelated session.

**Lifecycle** **[binding — the owner's rulings of 2026-11-17]**.

- A process ending leaves the thread `stopped`. Today a session the owner opened is retired `ended` at that point.
- A message addressed to a stopped thread wakes it (D2).
- A thread ends on an explicit `sminos retire`, which a thread may run on itself (how a session being closed for good says so), or once it has been stopped for more than three days. The rule covers every thread, spawned ones included. An ended thread is folded out of lists and is not woken; a sender is told it has ended.
- An ended thread's record is kept. Reopened or filled (`sminos fill`), it returns with its alias, its in-charge line and its memberships.
- A thread that owns a machine (D4) is not ended by the three-day rule. The machine's idle notice wakes it.

A thread's default is standing work under an in-charge line. Short use is allowed: the owner, "thread는 중장기가 가능한 형태이고 그것이 기본이지 단기가 불가능할 이유는 없다" (a thread is a form that can be long-lived, which is its default; nothing makes short use impossible). Bounded work that needs another environment opens a thread there, and the three-day rule clears it without a retire. *Alternative: a "resolved" state a thread sets when its work is done* (the prior-art survey's suggestion). It lost to the owner's rule that work with a defined end is a subagent's, so a thread needs no completion state.

**Aliases.** One per thread, the same in every channel. A bare `@alias` resolves among the threads that share the sender's project or a declared channel with the sender; when two answer, the refusal lists `alias#short` for each. Today a bare `@alias` resolves in the sender's project only (`_resolve_tag`), and uniqueness is kept per log (`shadowing`).

### D2. The wake

**A wake has four steps** **[binding — each closes a fault the experiment or the code showed; engine facts E1 to E7]**:

1. **Refuse while any process holds the session** (E5's three signals). A wake onto a held session would start a copy (E3).
2. **Pass flags unless the engine shows the session has run in the background before.** The flags are the permission mode and the model the thread last ran under (both change within a session, so the launch's values would be stale), the mode capped by the machine's policy ceiling, and from the launch the options the engine accepts on a first background resume. In doubt, pass them: passing none on a true first wake resumes under the settings' default mode (E1), which on the owner's Macs is `auto`. If the engine answers that it started a copy (E2), stop the copy, wake once more with no flags, and remember that this session has saved options.
3. **Read the mode the wake actually runs under** from the transcript's new row, which carries it at submission. When it is looser than intended, or one that asks for approval, stop the process and leave the thread stopped. The message has started by then; this window is stated and not closed.
4. **Open the wake with a line outside the envelope that carries a peer's words,** telling the thread that it was woken in the background by a message, that its human is not watching, and which of its launch options were not carried.

**Not woken.** Each of these stays `stopped` with the message recorded for it **[binding]**:

- a lane B session (MAWS reopens it);
- a session under another `CLAUDE_CONFIG_DIR` than the daemon's (`resume_session` refuses it today);
- a session whose directory is inside a macOS protected folder (the daemon's launch would raise a system dialog charged to the daemon);
- a session whose directory is gone;
- a thread whose last known mode asks for approval (`plan`, `default`, `acceptEdits`). The owner's ruling: "깨우지 않는다" (it is not woken). Woken unattended, it would stop at its first tool call (E6) and wait for a person who is not there. *Alternative: wake it and let it wait.* It lost because nothing established that the owner would learn a background thread was waiting.

**Whether a thread can be woken is published in its state** (contract X3), so that a sender's own CLI says so when it sends. A sender on another machine has no other way to learn the outcome.

`sminos decide`, which answers another session's permission prompt and checks nothing about its caller today, is left as it is. It is a separate matter from the wake.

### D3. Channels

**Creating.** `sminos channel create <name>`, run by a thread, which becomes the first member, or by the owner at a terminal, who names a thread of that machine as the first member. A channel starts with a member on the creating machine because of how logs are followed: a machine follows a log that has no location only while some machine's record holds a member of it (D6), and a request reaches another machine only once that machine follows the log.

**The id** **[binding, pending MAWS's reading — X4]** is a minted UUID whose version nibble is 8 (RFC 9562's custom version). A minted project id is version 4 and a machine's own project id version 5, so every machine tells a channel from a project by the id alone, with no change to the protocol. `sminos join <channel>` is refused and names `sminos channel add`: `join` moves a thread's project, and a channel must never become one. The name reaches the hub with the log's first hello, as a project's does. A name is a label: two channels may share one, and a reference that two answer is refused with `name#short` for each, as aliases are. *Alternative: a hub record that declares a channel and its members.* It lost when membership became the member's own statement (below): nothing was left for the record to say, and it needed an authority for who may assert another machine's membership.

**Membership** **[binding — the log's standing invariant that a thread's membership has one writer (`lifecycle`, `_memberships`, `_projection`), and the registry's rule that a change to a machine is a request that machine carries out and then states]**. `sminos channel add <channel> [<thread>...]` and `sminos channel remove`; with no thread named, the caller. An add of another thread is a request, and the thread's machine carries it out. Two records:

- *The request,* in the channel's log: one event per thread, naming it by its current session id with its thread id beside it. It names the target where the hub's check of who may reach a session reads it, so that who may message a thread may ask to add it. It never names the target in the field that addresses a message, which today's sminos would deliver and wake a seat for (`_owed`, `push_event`).
- *The membership,* in the thread's project log: its own kind of event, naming the channel, written by the thread's machine under the thread's writer, in the same pass that holds the reach permit for that writer. With the thread's other facts it follows the thread through a change of reach, a `/clear` and a `join`.

What follows from that:

- Order is the member's own sequence; no clock decides between machines. A request older than the last one applied is dropped.
- A roster is read across project logs, which every machine of the org follows. A row, a pending one included, is built from the member's own project log as the reader may read it, so a thread that went private is not kept visible by an old add.
- *Pending* is a request whose asked state the thread's project log does not show yet: its machine is off, or its sminos predates channels. A request ends by being applied, refused or expiring.
- A thread's memberships live with its record and return with it (D1).
- A thread learns of a channel from the frame of the first message that reaches it from there, and from the guide at its next start. Adding wakes no one, and neither does removing.

*Alternative: the actor writes the membership into the channel's log* (the first design). It lost to the critic's first pass: two machines writing one thread's membership need an order between machines, and the log has none.

**A channel exists while it has a member that has not ended** **[binding]**. When its last such member ends or is removed it leaves the directory, and returns when a member does. The hub keeps the log (nothing in MAWS deletes one), and a machine that stops following keeps its copy (`has_left`). There is no archive verb and no record of a channel beside its log and its members' statements.

**The timeline** **[binding — a message belongs to one log]**. Channel traffic is what is said `--in` the channel: `sminos say --in <channel> ...`, with the tags a project's log has: `@thread` delivers, `@all` wakes the channel's live members, untagged is a record nobody is woken for. Without `--in`, `say` does exactly what it does today, into project logs. A reply defaults to the log its message came in. `@<channel>/<alias>` addresses as `@<project>/<alias>` does, so a channel's name fits the grammar sessions know. *Alternative: a session's "current channel" as the default target.* It lost because a wrong default sends work to the wrong audience without an error; the survey's strongest finding on routing is to make the address explicit.

**The lead** **[binding — the owner]**. None by default. `sminos channel lead <channel> <thread|none>` is the owner's act alone, refused from a session as widening reach is. While it is set, a message the owner posts to the channel with no tag is addressed, on the machine where the owner types it, to that thread; a lead that has ended or left is ignored. A machine delivers a person's words only when it can verify them (MAWS `src/endpoint/rl10/words.ts`), so until the app posts to channels this works from a terminal on the lead's own machine. A machine's notice recorded in a channel (D4) is never read as the owner's post.

**Listing.** Bare `sminos list` shows the caller's project and every declared channel it is in, each with its roster. A declared channel's roster shows its stopped members; a project's folds them as today. `--channel` filters; today's filters stay. `sminos channel show <name>` prints one channel: its members and its pool.

### D4. Environments

**Opening a thread elsewhere.** `sminos spawn ... --on <machine>` opens the thread on that machine, and `--on new` makes a devcloud VM first. sminos places and devcloud provisions **[binding — the owner: no scheduler]**: `--on new` runs `devcloud vm up`, whose caps, consent rules and exit codes are unchanged and decide whether a VM is made; sminos waits for the machine's enrollment and spawns there. `--channel <name>` (repeatable) names the declared channels the new thread starts in; a new thread does not inherit its opener's.

The first version reaches a VM over ssh from a Mac, as `devcloud vm ssh <name> -- sminos spawn` does by hand today. Two cases wait for a later design: a spawn asked from a VM, and one Mac opening a thread on the other (a Mac's login keychain is closed to an ssh session, so `claude` over ssh to a Mac is not relied on). Both want the shape of a channel add: a request the target machine's daemon carries out under its own policy.

**The pool** is derived: the machines a channel's threads run on, and machines added by hand (`sminos channel env add|remove <channel> <machine>`, events in the channel's log; the last by merge order holds, as a status does). A machine may be in many pools. The pool constrains nothing and chooses nothing **[binding — the owner: "채널은 단순히 어떤 env pool이 이 채널에 존재하는지 명시할 뿐이다"]**. `sminos channel show` prints it with each machine's load and live threads and, for a VM, its owner, age and cost: information for whoever opens the next thread. *Alternative: a machine belongs to one pool* (what Buildkite and GitHub's runner groups moved to). It lost because those systems needed a security boundary between teams, and this fleet has one owner.

**A VM's owner is the thread that made it** **[binding — the owner]**. devcloud records the thread id where it records the creating session's tag today (`DEVCLOUD_CREATOR`), and sminos keeps what a thread owns in its record, so that `retire` can refuse an owner without asking a cloud. Idle and lease notices go to that thread, waking it if it is stopped, and are recorded in the timeline of each channel whose pool holds the machine, under a writer that is not read as the owner's. An owner is retired only once its machines are downed or handed over (`devcloud vm owner <name> <thread>`).

**A VM that `--on new` makes is kept** **[binding — the owner: "kept, 소유 스레드가 내린다"]**, which is devcloud's default. It lives until its owner thread downs it; the idle notice, every three idle days, wakes that thread to decide. `devcloud vm down` refuses over unpushed work, so no deadline takes work with it. *Alternative: a lease that renews while a thread on the machine has not ended.* It lost because a VM whose lease ends is deleted with everything on it (`devcloud/skills/vm/SKILL.md`), unpushed work and its threads' transcripts included, so those threads could not return. A spawner that wants a lease makes the VM with `devcloud vm up` itself and names it with `--on`.

### D5. The CLI and what sessions are taught

One surface **[binding — the owner]**. MCP tools were weighed and declined: the owner, "say와 send를 하나로만 둔다면 굳이 mcp가 필요할지" (if `say` and `send` are one, is MCP needed at all). What tools would have fixed was fixed in the CLI in sminos 1.48.0 (PR #509): `sminos` on a session's PATH through the plugin's `bin/`, a message body from standard input, and a hook that refuses a sminos call whose arguments hold a backtick the shell would run (six of 4,311 `say` and `send` calls in 21 days did; one ran a command on the sender's machine).

- `send` leaves what sessions are taught: for a member it does what a tagged `say` does. It stays for scripts (`--wait`, Codex threads).
- `join` keeps today's meaning, declaring a thread's project, since everything the owner looks at is keyed by project until the app has a channel view. A thread that should leave a repository's automatic channel joins its machine's project.
- The session-start guide and the skill (`sminos/skills/sminos/SKILL.md`) speak of threads and channels. The skill is behaviour: it changes through doperpowers:writing-skills and is evaluated. The manager's skill (`sminos/skills/manager/`), which imports the CLI's modules, moves with it (contract X6).

### D6. Storage and the wire

- **A declared channel is a log.** The hub creates a log for any id of UUID shape a machine says hello for and registers it as it registers any project it does not hold (MAWS `apps/desk-hub/src/objects/registry.ts`, `registerProject`). Its id check reads shape alone (`PROJECT_ID`), and its event check accepts any string kind (`eventShapeError`).
- **A thread's own facts stay in its project's log** **[binding — MAWS keys the per-session view, notifications and pending counts by project, and the hub refuses a second copy of a reach change]**: its lifecycle events, its memberships, its messages to its human. A declared channel's log holds requests, hand-added machines, the lead, and what is said `--in` it. Nothing is duplicated.
- **A thread's project stays single** **[binding]**; its declared memberships are a set beside it, in its record. The three places that hold one project per session (Grounding Baseline) keep doing so.
- **The contract with MAWS is one field** **[binding, pending MAWS's reading — X5]**. The RL10 `member` frame gains an optional `channels: string[]` behind a new capability, as `locations` was added. The endpoint reads it in one place, so that a channel is in the machine's `known` list while the machine holds a member of it, a stopped member included, and the other machines follow its log (`sminosView().sessionProjects()` in MAWS `src/endpoint/rl10/link.ts`, read by `#knownNow` in `src/endpoint/registry.ts`). No declaration record, and no change to listings or notifications. Until the app has a channel view, a channel shows in the hub's grid as a project does, and the grid does not shed one that has emptied.
- **A fault that exists today, independent of this work:** the endpoint's in-memory dedup of to-human notifications is keyed `(writer, seq)` with no project, while sminos numbers a writer's events per project. A session whose project changed starts again at seq 1 under the same writer, and each message whose seq was already seen for the old project is not notified. MAWS's architect confirmed the reading and filed it as MAWS #761.

### D7. Versions in the field

The owner's machines update sminos at different times, so each release must be safe beside an older one **[binding]**:

- A reader comes before its writer. A machine on an older sminos must skip an event kind it does not know (as read, `_projection` skips kinds outside `LIFECYCLE`; each child that adds a kind verifies this against the oldest version still installed, and ships the reader a release ahead if it does not hold).
- A request to a machine whose sminos predates channels stays pending and says why (D3).
- Each child's merge leaves both repositories releasable, and bumps its plugin's version in the same change (`scripts/bump-version.sh`).

### Delegated unknowns

Each is assigned to the child that settles it.

| Unknown | Settled by |
|---|---|
| How the engine decides a session has saved options; what `claude rm` or the expiry of the engine's row does to them; which launch options a first background resume accepts beyond the mode and the model; first-wake flags on a session that was backgrounded once and then used in a terminal | T2's spike milestone |
| Whether a compaction gives a background session a new id. A friction entry says so; no code shows it. If it does, it is a third continuation case, keyed as `clear` is | T1, a live check before the continuation rule is built |
| Whether MAWS takes the channel marker in the id, and its answers on the contract (asked 2026-11-17) | MW; the fallback for the marker is a first event in the channel's log |
| How a thread whose reach is not the default says something `--in` a channel: which stream it is written under, and how the channel's hub object learns that stream's policy | CH, with MAWS |
| How long a pending request lives before it expires | CH |
| Whether anything in MAWS assumes that a lane A session nobody spawned stops being a member when its process ends (asked 2026-11-17, the fifth question) | MAWS's architect, before T1 is dispatched |
| Whether the three-day clock should stop while a machine is off. A thread returns when reopened, so the simple rule costs a fold, not a loss | Observation after T1 |
| Noise from plural membership. The survey found no account of it either way; the lever is that a post wakes no one | Observation after CH |

## Children

### T1: Threads: identity and lifecycle — plan

- **Purpose:** make every member a thread in everything but the wake: a thread record with a durable id, `stopped` in place of `ended` when a process ends, the three-day rule, self-retire, the return of an ended thread, and the continuation rule. This is the half of the durability fault that needs no engine experiment, and it is the record every later child reads.
- **Acceptance:**
  1. A session opened in a terminal, then exited, is listed `stopped` by `sminos list --stopped`, where today it is gone. Reopened with `claude --resume`, it is listed live under the same alias and in-charge line, and receives what was recorded for it meanwhile.
  2. A message addressed to it while stopped is recorded, and the sender's CLI says the thread is stopped and is not woken because its human opened it (the hold D2's wake lifts in T2). A spawned thread is woken exactly as today.
  3. After `/clear`, the new session id carries the thread: same thread id, alias, in-charge line, owners and reach. A fork and an in-session `/resume` are other threads, and a fork's start guide says it is a copy with an identity of its own.
  4. A thread stopped for more than three days (a clock a test can set) is ended: out of `sminos list` and `--stopped`, shown by `--all`, and a message addressed to it reports that it ended. A thread whose record names an owned machine is exempt. `sminos fill`, or reopening it, returns it with its alias and in-charge line.
  5. `sminos retire` run by a session on itself ends its thread and holds after its process exits.
  6. Parent acceptance line 8 for this child's surface: the sminos suites pass, with the tests that pinned `ended` for a seat-less session changed to pin `stopped`.
- **Edges:** blocked-by: external: MAWS's answer to the fifth question (a start-time input on what the endpoint and the app do with a member that stays `stopped`; T1 runs either way). blocks: T2, CH, EN.
- **Contracts:** X1 (owner), X2 (owner), X3 (the first values), X6, X7.
- **Design inheritance:** D1 whole (binding where marked). D7. Advisory: the existing `sminos seat add --session` path and the seat record are the natural base, and the differences to remove are the rows of the Grounding Baseline's table; `retirement_holds` loses its reason once a retire is a record. Lane B sessions become threads like any other and are never woken (D2). MAWS's architect was asked on 2026-11-17 whether anything in MAWS assumes that a session's membership ends with its process; an answer that something does comes back to this document as a change to D1, not as a local exception.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (dispatchable once the owner has looked at this cut).

### T2: The wake — plan, opening with a spike

- **Purpose:** let an addressed message wake any stopped thread, a session the owner opened included, without starting a copy, loosening its permission mode, or leaving a process waiting on a person who is not there.
- **Acceptance:**
  1. Parent acceptance line 3: same session id, one process, the mode (capped by the machine's ceiling) and model the thread last ran under, the opening line, and a terminal `claude --resume` that attaches.
  2. Parent acceptance line 4, and the same for each of the other four exclusions of D2: no process starts, the message is recorded, and the reason is in the thread's published state and in the sender's output, on the thread's machine and on another.
  3. With a process holding the session, no wake is attempted and no copy exists afterwards.
  4. When the engine starts a copy because the session already had saved options, the copy is stopped, the thread is woken once more without flags, and a second wake of that thread passes none.
  5. A wake that comes up looser than intended, or in a mode that asks for approval, is stopped within the turn, and the thread stays `stopped` with the reason recorded.
- **Gates:** G1 (required) the spike's findings recorded in this document's Surprises & Discoveries, each Delegated unknown assigned to T2 answered or shown unanswerable with what the wake does instead. G2 (required) acceptance 1 to 5.
- **Edges:** blocked-by: T1. blocks: EN (a notice wakes a stopped owner).
- **Contracts:** X1 (the fields it adds), X3 (owner), X6, X7.
- **Design inheritance:** D2 whole (binding). Engine facts E1 to E7. Advisory: `resume_session` is the path to extend, and its `copy_started` check already parses "started a copy as"; the transcript row that carries `permissionMode` at submission is the reading for step 3; the experiment ran one session at a time on a Mac at load 40, so timings there are upper bounds. A wake runs in the daemon's environment, not the terminal's (`resume_session`'s docstring): a gateway route or credentials the terminal process had are not carried, the session record's `inference` is not applied again, and the spike records what differs so that the opening line can say it.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1).

### MW: MAWS: the `channels` capability — brief, in the MAWS repository

- **Purpose:** let a machine's record list a declared channel as known while the machine holds a member of it, so that every machine of the org follows the channel's log.
- **Acceptance:** with the capability advertised by both sides, a `member` frame carrying `channels: [<id>]` puts `<id>` in the machine's `known` while that member is held and removes it when the last such member goes; without the capability on either side, frames and `known` are byte for byte what they are today. The RL10 conversation fixture (`test/endpoint/rl10/conversation.json` in MAWS, copied to `sminos/tests/rl10-conversation.json` and replayed by `sminos/tests/rl10_conformance.py`) carries the new frame.
- **Edges:** blocked-by: external: MAWS's architect's reading of the contract (asked 2026-11-17, five questions). blocks: CH's cross-machine gates.
- **Contracts:** X4, X5 (owner of the endpoint's half).
- **Design inheritance:** D6 (binding, pending that reading). MAWS's own process decides how the change is built and reviewed there; this section is the contract it is built to.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (waiting-external).

### CH: Channels — decomposing at dispatch

- **Purpose:** the declared channel itself: memberships as a set in the thread's record and their statement in the project log, the request and its application by the member's machine, channel logs and how machines follow them, the `channel` verbs, `say --in`, listing, aliases across channels, and the skill and guide that teach all of it.
- **Acceptance:** parent acceptance lines 1, 2 and 7, across two machines, and line 8 for its surface; a request to a machine that is off is listed pending and applied when the machine returns; a thread that goes private drops out of a roster a reader may no longer see it in; the skill's evaluation shows a fresh session creating a channel, placing others, and speaking in it without a wrong-log message.
- **Edges:** blocked-by: T1; its cross-machine gates blocked-by MW. blocks: EN.G2.
- **Contracts:** X1 (the memberships field), X4 (owner), X5 (sminos's half), X6 (owner of the rewrite), X7.
- **Design inheritance:** D3 whole, D5, D6 (binding where marked). Advisory, from the code map: `_local_sessions`, `_reconcile` and `retire_moved` are where membership is decided today; `holds` (the uplink) decides whether a log is opened as followed and must count a declared membership as a session there; `known_checkouts` counts every directory a session joined a project from, which is why membership is not a `joined` event in the channel's log; `cmd_say` refuses `--in` for a session today; the peer frame's reply line (`reply_line`) still models a double-quoted body under an absolute path and is due in this child's skill work (`docs/doperpowers/TECH-DEBT.md`, the backtick guard). Residue for its own cut, with the answers this design leans to: an untagged post or `@all` in a channel is a member's, while a tagged message from outside follows today's cross-project rule; `channel show` and `channel env` belong here and the VM columns to EN; a likely seam is membership and its wire on one side, traffic and the taught surface on the other.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1; deliberately late — see Ordering).

### EN: Environments — plan

- **Purpose:** open a thread on another machine with one command, and give every VM an owner that outlives the session that made it.
- **Acceptance:**
  - G1 (required): `sminos spawn --on <vm>` and `--on new` from a Mac open a thread on the VM, with devcloud's caps and consent rules deciding whether a VM is made and its refusals passed through; the VM's recorded creator is the thread id; `sminos retire` of an owner is refused and names its machines until they are downed or handed over with `devcloud vm owner`; an idle notice wakes a stopped owner.
  - G2 (required): parent acceptance line 5: `--channel` places the new thread, `sminos channel show` lists the VM with its owner, age and cost, and a notice is recorded in the timeline of each channel whose pool holds the machine, under a writer that is not read as the owner's.
- **Edges:** G1 blocked-by: T1, T2. G2 blocked-by: CH.
- **Contracts:** X1 (the owned-machines field), X2, X3, X6, X7.
- **Design inheritance:** D4 whole (binding where marked). Advisory: `devcloud vm ssh <name> -- sminos spawn` is today's manual path; devcloud runs on Macs only and exits 6 on a host, which is why a spawn asked from a VM waits for a later design.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1, T2; deliberately late).

## Cross-Child Contracts

- **X1. The thread record.** Owner: T1, which fixes its names in its plan's Interfaces section before T2 starts. It is one record per thread on the thread's machine, read through one module. Fields the design requires: the thread id; the current session id; the alias; how the thread was opened (spawned, or by its human); the launch's options and the last known permission mode and model (T2 writes these); the declared channel memberships (CH writes these); the owned machines (EN writes these; T1 reads them for the three-day exemption). A child adds a field only through that module. The record is local to the machine and is never the authority another machine reads: what others see is what the thread's machine wrote to the log.
- **X2. Naming a thread where the name must outlive a session id.** The thread id, alone where the reader is on the thread's machine (devcloud's creator), and beside the current session id where another machine must find it (a channel request). Session ids stay what addresses a message. Owner: T1.
- **X3. Whether a thread can be woken.** Published by the thread's machine in the thread's state in its project log: woken or not, and when not, one reason from a fixed list (opened by its human while the wake is not shipped, which T1 writes and T2 retires; lane B; another config dir; a protected folder; directory gone; a mode that asks for approval; ended). A sender's CLI reads it at send time on any machine. Owner: T2. T1 lands the three values it needs: woken (a spawned thread, as today), held (opened by its human), and ended.
- **X4. Which log holds what, and who writes it.** A thread's lifecycle and membership events: its project log, under its own writer, by its own machine. A channel's log: requests, hand-added machines, the lead, and what is said `--in` it. No event about a thread is written by another machine's writer, except a request, which states what is asked and nothing about what is. The channel id is a UUID with version nibble 8. Owner: CH for the kinds' names and shapes; the placement binds every child now.
- **X5. The wire.** RL10 stays at its version; a capability named by MAWS gates `member.channels[]`. Each side is inert until the other advertises it. The conversation fixture is one file, changed in MAWS and copied byte for byte. Owner: MW for the endpoint, CH for sminos.
- **X6. What sessions are taught stays true.** Each child changes the guide text, `sminos/skills/sminos/SKILL.md`, the spawn preamble and the nested `CLAUDE.md` files for what it changes, through doperpowers:writing-skills with a small evaluation. The rewrite into the words "thread" and "channel", and the manager's skill, are CH's. Until then a child uses today's words and adds only what became false.
- **X7. Releases.** D7, for every child.

## Ordering & Dependency Map

```
T1 ──▶ T2 ──▶ EN.G1 ──┐
 │                    ├──▶ EN.G2
 └──────▶ CH ─────────┘
          ▲
MW ───────┘ (CH's cross-machine gates)        MAWS #761: independent
```

T1 first: it is the record every other child reads, and it needs nothing from MAWS or the engine. T2 next, so that the durability fault is whole before channels exist. CH and EN are cut when they near execution: their boundaries depend on what T1's record looks like and on MAWS's answers, and a cut drawn now would be redrawn. MW can be built in MAWS at any time after its reading; it is inert until sminos advertises the capability. If MAWS's answer is slow, EN.G1 can run before CH, since it needs only T1 and T2. T1 and T2 change the same functions of `S/sminos.py` and run one after the other; CH and EN.G1 touch different paths and could run side by side.

## Risks & Mitigations

- **A wake under a looser mode than its human chose.** Steps 2 and 3 of D2, and T2's gate G1 before any wake code ships. T1 ships with the wake held for sessions the owner opened.
- **A wrong continuation hands one thread's owners and reach to another.** The rule is two cases, keyed on evidence the engine writes, and T1 pins a fork and an in-session `/resume` as other threads.
- **A long-quiet spawned thread now ends after three days,** where today it would be woken a week later. The sender is told it ended; `sminos fill` returns it. Watched after T1 (Delegated unknowns).
- **Every machine follows every channel's log,** which costs the hub one renewal per open log per heartbeat and each machine one policy rebuild per newly opened log (`code-map.md` §2). At the fleet's size this is small; a channel that empties leaves the directory. Measured in CH if channels number in the tens.
- **Two repositories, two release trains.** X5's capability makes each side inert alone; X7 orders reader before writer.
- **A woken thread runs with the daemon's environment,** which may route inference or hold credentials differently from the terminal it was opened in. T2's spike measures the difference and the opening line states it.
- **`S/sminos.py` is one file of some thirteen thousand lines.** Children that change the same functions run in sequence (Ordering).

## Deferred / Out of Scope

**Deferred (may return):**

- A spawn the target machine's daemon carries out on request: a thread opened from a VM, and from one Mac on the other.
- The app's channel view in MAWS, and with it the lead set and used from any device, and the grid shedding an emptied channel.
- Moving a thread to another machine, and the handoff document that would need.
- A check of who calls `sminos decide`.

**Explicitly out of scope (standing exclusions):** MCP tools for sminos's verbs; a scheduler or default placement; a channel owning a lifecycle or a machine; a structural lead; a channel as a boundary of who may read (see Purpose).

## Tracking Map

| Child | Artifact | Status |
|---|---|---|
| (landed before this cut) CLI on PATH, stdin bodies, the backtick guard | PR #509, sminos 1.48.0; residue in `docs/doperpowers/TECH-DEBT.md` | landed 2026-11-17 |
| T1 | — | not-dispatched: waits for the owner's look at this cut |
| T2 | — | not-dispatched: blocked-by T1 |
| MW | MAWS's architect holds the contract and five questions | waiting-external |
| CH | — | not-dispatched: blocked-by T1; cut at dispatch |
| EN | — | not-dispatched: blocked-by T1, T2 |
| (independent) the notification dedup key | MAWS #761 | filed 2026-11-17 |

## Surprises & Discoveries

- Observation: a background resume of a terminal session does not bring back the options it was launched with; it runs under the settings' defaults, which on the owner's Macs is `auto`.
  Evidence: `bg-resume-experiment.md`, Q1: a session launched with `--permission-mode manual --model haiku` came back as `"permissionMode": "auto"`, Opus.
- Observation: the first background resume of a session accepts flags under the same id; every later one with a flag starts a copy.
  Evidence: same file, Q2: "backgrounded · 428cb53b" with flags on a first resume; "the flags you passed started a copy as 78aedefa" on a later one.
- Observation: MAWS's endpoint drops a to-human notification whose `(writer, seq)` it has seen in another project.
  Evidence: `src/endpoint/notify.ts`, `hostMessage`: the id is the writer and the seq; sminos's `_append` numbers each project's store from its own last line. Confirmed by MAWS's architect, MAWS #761.
- Observation: six of 4,311 distinct `say` and `send` calls in 21 days of one Mac's transcripts passed a body in which the shell ran a backtick; one ran a command that stops a service on the sender's machine, and the recipient read the command's output in place of its name.
  Evidence: the guard run over 32,707 commands that mention sminos refused exactly those six (PR #509).

## Decision Log

- 2026-11-17 — **Verification.** The design was debated with the `doperpowers:critique` agent in two passes before approval; each finding was checked against the code it cited (see the entries below). This document gets one independent design review (a general-purpose agent on the frontier model) and, in the same round, the `doperpowers:adversarial-reviewer` on the roadmap sections for whether the children are complete, well cut and buildable from this document and the code. Each code-bearing child's branch gets doperpowers:review-code at the high rung: T1 and T2 change who stays a member and what is launched unattended, with privacy and permission consequences. Closing the unit is a scale review at recomposition: two repositories and cross-child invariants. The spec and its roadmap were written as one document and reviewed in one round, in place of a spec review followed by a second review of the cut: the design was already matured and debated, and the reviewers read a more complete artifact.
- 2026-11-17 — **Approval, with a condition.** The owner approved the design and asked to look again before implementation starts. Nothing is dispatched until then.
- 2026-11-17 — **What the critic's first pass changed.** Membership became a request the member's machine applies, which removed the question of order between machines, a hub record declaring a channel, and an archive verb. A reach change is no longer written into every log: the hub would refuse the second copy. Thread identity moved ahead of channels in the order of work. The wake gained its checks and its opening line. `join` kept its meaning. One Mac opening a thread on the other left the first version.
- 2026-11-17 — **What the critic's second pass changed.** A thread is no longer "today's seat" whole: the four things it takes are named, and T1 holds the wake until T2. The membership statement is placed in the thread's project log and the request's shape fixed. A channel starts with a member on the creating machine and its id says what it is. The continuation rule is keyed on the start's source. The wake passes the last known mode and model, has a rule for doubt, reads the mode from the transcript, and publishes whether a thread can be woken.
- 2026-11-17 — **The owner's last three rulings.** A thread whose mode asks for approval is not woken (and a wake that comes up in such a mode is stopped, taken as that ruling's consequence). A VM made by `--on new` is kept. MAWS's architect was sent the contract before approval.
- 2026-11-17 — **Decided without asking,** each a technical consequence of the design: no archive; a new thread starts in the channels `--channel` names and does not inherit its opener's; a thread learns of an add or a remove from the first message from that channel or the guide at its next start; the words stay "channel" and "thread", and MAWS's "direct channel" becomes "thread" in documents as they are touched; a thread carries no handoff document; a spawner that wants a lease makes the VM itself.
- 2026-11-17 — **The cut.** T1 and T2 are cut to plan grain now; CH and EN are left coarse and cut at dispatch (the frontier rule: a boundary drawn for far-off work goes stale as its siblings land). The MAWS half of the wire is its own child because another repository's process builds it. Alternative rejected: one child for all of sminos's side, which chains unrelated behaviours and would put the wake's engine risk in the same branch as the membership model.

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check: verify Parent-Level Acceptance as written — all children landed is not the same event — then retrospect.
