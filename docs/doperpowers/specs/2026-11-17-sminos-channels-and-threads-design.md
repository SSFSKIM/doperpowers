# sminos: channels and threads (2026-11-17)

> **Parent:** root — the sminos plugin's standing purpose (`sminos/CLAUDE.md`, its first paragraph; design `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`). **Consumes:** the research under `docs/doperpowers/research/2026-11-17-sminos-channels/` (`prior-art.md`, `code-map.md`, `bg-resume-experiment.md`), and MAWS's desk design (2026-10-15) and project registry design (2026-11-10), in that repository's `docs/doperpowers/specs/`. This document is the design the owner approved on 2026-11-17, extended in place with its roadmap: the design up top, the children below. Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact (plan, ledger, findings, PR) opens by citing this document (path + child id + parent pin).

## Purpose

sminos connects one person's Claude Code sessions across repositories and machines, so that the sessions coordinate as a team and that person supervises them as one. Three things about how it does that today are wrong, and each was observed on the fleet on 2026-11-17 (Grounding Baseline):

1. **The unit of coordination is where a session was launched, which is not whom it works with.** A coordinator and the session it directs sit in different projects; three sessions on one branch are split between two machines' projects.
2. **Standing responsibilities are not durable.** A session its human opened stops being a member when its process ends, and no message wakes it. Only a session another session spawned stays and is woken.
3. **Where a session runs is not a choice.** A spawned session opens on its spawner's machine, and most of the fleet runs on one overloaded Mac.

After this work:

- **Every member is a thread** (sessions the MAWS app itself launches keep MAWS's rule). A thread keeps its identity when its process ends, a message addressed to it wakes it in the background, and it ends only when it is retired or has been stopped for more than three days.
- **A channel is a named set of threads with a log of its own,** created with one command, crossing repositories and machines. One command places any number of threads in it, and no session has to act to be placed. A thread is in any number of channels.
- **A thread can be opened on another machine,** a new cloud VM included, with one command; the thread that made a VM owns it.

How to see it working is the scene in Parent-Level Acceptance.

**What it must not become.** These are the owner's rulings and bind every child:

- *An owner of things.* A channel owns no lifecycle and no machine. The owner's words: "채널은 그냥 machine pool과 연관된 repo들, 그리고 그 채널에 속한 세션들만 가지고 있으면 된다" (a channel only has to hold a machine pool, the related repositories and the sessions in it).
- *A hierarchy.* "리드 없음 -- 모든 멤버가 sibling이다" (no lead; every member is a sibling). Coordinators emerge from the work; none is defined.
- *A permission boundary.* Who may read or reach a thread stays a property of the thread.
- *A second surface.* No MCP tools. The CLI is the one way in.
- *A scheduler.* No default placement and no autoscaler.
- *Something a session must act on to be placed.* "세션이 직접 channel join을 할 필요가 없다" (a session need not join a channel itself).

MAWS, the owner's desktop app that shows sminos's sessions, will later show this model as its channel interface. That view is a later design; this document is the model it will show.

## Parent-Level Acceptance

The unit closes when this scene runs on the owner's fleet, on released versions, and each numbered line is observed. "A" is a thread in one repository on a Mac; "B" is a thread its human opened in another repository, in a terminal, in `auto` mode, and never yet run in the background.

1. A runs `sminos channel create desk-integration` and `sminos channel add desk-integration <B>`. Neither B nor its human does anything. `sminos list` run by A and by B shows `# desk-integration` beside each one's project, with both threads in its roster.
2. A runs `sminos say --in desk-integration "@<B> ..."`. B receives it framed as coming from that channel, and B's reply, sent with the reply line that frame gives, lands in the channel's log. A `say` with neither `--in` nor a tag qualified by a channel lands where it does today.
3. The owner closes B's terminal. `sminos list --stopped` shows B as `stopped`, in its project and in the channel. A sends B an addressed message: within two minutes one background process holds B's session id, in the permission mode B last ran in and with the model it last ran with, and no copy of the session exists. B's first line of that turn says it was woken in the background and its human is not watching. The owner runs `claude --resume <B's session>` in a terminal and is attached to that same process.
4. A thread C whose last mode asks for approval (`default`, `plan` or `acceptEdits`) is closed. A's `sminos say "@<C> ..."` reports, when it is sent, that C is stopped and will not be woken, and why. No process starts. C receives the message when its human reopens it.
5. A runs `sminos spawn --on new --channel desk-integration <alias> <task>`. A devcloud VM is made under devcloud's own caps and consent rules, and a thread opens on it and appears in the channel. `sminos channel show desk-integration` lists the VM in the channel's pool with A as the thread that owns it, its age and its cost. `sminos retire <A>` is refused and names the VM. After `devcloud vm down` of that VM (or `devcloud vm owner <vm> <another thread>`), the retire succeeds, and the thread that ran on the downed VM is out of the roster.
6. A thread stopped for more than three days is ended: `sminos list` and `sminos list --stopped` no longer show it, `--all` does, and a message addressed to it reports that it has ended. Reopened by its human, it is listed under the alias, in-charge line and channel memberships it had.
7. A runs `sminos channel remove desk-integration <B>`: B leaves the roster and is not retired. When the last member that has not ended is removed or ends, the channel leaves `sminos list --org`.
8. A session that never uses a channel sees no change: every suite that passed before passes, and `say`, `list`, `spawn`, `join` and `retire` behave as they did, apart from lines 3, 4 and 6 above and two visible consequences of them: a stopped thread keeps its alias, so a new session with the same name is told apart as two live ones are today, and a question a thread left open for its human is closed when the thread's process stops.

## Grounding Baseline

**The fleet, 2026-11-17** (`sminos list --org`, `sminos machines`, `devcloud vm ls`): 29 live sessions. 19 run on one Mac, whose load average was 38 to 42 during this design's own experiment. A coordinator is filed in one repository's project and the seat it directs in another's, on a VM. Three sessions on one branch are split between two machines' own projects. One session serves four repositories from the project of the one it was launched in. One machine's own project holds six unrelated sessions. One VM made for a seat had been kept for 20 days at a cost above 100 euros, its creator recorded as a session's tag.

**sminos, at `main` 601b8e9d** (`code-map.md` has the line-level map; `S/` is `sminos/skills/sminos/scripts/`):

- *One project per session is enforced in three places, not throughout:* `session_project` (one project: the `join` override, else the launch directory), the override file (`override_path`: one id), and `_reconcile`, which retires `moved` every membership that is not the resolved one. Everything else is computed per log and keyed `(project, session)`.
- *A seat and a seat-less member differ in these paths* (all in `S/sminos.py`):

  | Path | Seat (a spawned session) | Seat-less (a session its human opened) | Function |
  |---|---|---|---|
  | Process gone | stays a member, reads `stopped` | retired `ended`; joins again if it runs again | `_reconcile` |
  | Addressed message while stopped | resumed: `claude --bg --resume` | recorded, never resumed | `push_member`, `push_event` |
  | `retire` | record `retired`, process stopped | event only, holds for the process's life | `_retire_one`, `cmd_retire`, `retirement_holds` |
  | Alias | fixed at spawn | the engine's name, else the held alias | `held_alias`, `join_on_sight` |
  | Project | its directory's; `join` refused | the override, else the launch directory | `seat_project`, `cmd_join` |
  | Hand-off to a background job | `follow_seat` moves the seat | override and cursor carried | `hand_off`, `predecessor`, `continued_in` |

  `sminos seat add <group> <alias> --session <id>` (`cmd_seat_add`) already gives a running session its human opened a seat. `fill` without `--resume`, and a `spawn` onto an existing alias, start a new session in the same seat with a fresh launch record (`cmd_fill`, `spawn_fresh`). The verbs that take a seat (`resume`, `fill`, `send --wait`, `seat remove`, `retire --purge`) go through `resolve_seat`.
- *Every path that resumes a stopped session goes through `resume_session`,* which passes no flags; `claude_args` launches a spawned seat with `--permission-mode auto`. A sender's own CLI process does local delivery (`deliver_say`, `deliver_next`, `push_member`), so a resume is started by whichever CLI sent the message, not only by the daemon.
- *Several sminos versions run on one machine and write one store.* The daemon runs the marketplace clone (`installed_cli` in `S/sminos_daemon.py`); a session's hooks run the copy of the plugin version the session loaded (`sminos/hooks/smns-record.sh` calls `$CLAUDE_PLUGIN_ROOT/skills/sminos/scripts/sminos`), for as long as the session lives.
- *A continuation is already an event:* `retired` with reason `continued` and the successor's id in `to`.
- *A resume launches inside a macOS protected folder today,* where a spawn or a fill from outside it is refused (`S/CLAUDE.md`).
- *The latest permission mode of a session is held in its bridge's memory* and is not restored when the bridge restarts (`load_kept` in `S/sminos_bridge.py`); the bridge may know no mode at all.
- *Nothing publishes a machine's load or whether it is on* (`cmd_machines`).

**devcloud, at the same commit:** a VM's descriptor records its creator as a sminos tag (`@alias`, `@alias#short`, `@short` or `@project/alias`; `devcloud/boot/devcloudlib/descriptor.py`) and the creator's project. Idle and lease notices are sent **from the VM**, by its own `sminos say`, to that tag, then to the creator's project's live members, then into that project's log (`devcloud/boot/devcloudlib/notices.py`). devcloud's verbs are `up`, `adopt`, `ls`, `ssh`, `lease`, `down`, `image`, `reap` and `provider`; it runs on Macs only and exits 6 on a VM.

**MAWS, at its trunk 77af813a4,** as its architect read it against this design on 2026-11-17:

- The hub creates a log for any id of UUID shape a machine says hello for and registers it as `kind 'hub'` (`registerProject`); no check of a project id reads the UUID's version, and the hub's event check accepts any string kind. A log with no location gets no row in the desktop app and is hidden by default in the web desk.
- A machine's `known` list holds a log that has no location while the machine holds a member of it **and** its sminos opened that log without `follow` (`#knownNow` in `src/endpoint/registry.ts`).
- The endpoint withdraws a session's listing only when sminos says it is gone, and never branches on a member's state; the app draws `stopped` as done.
- The hub closes a session's open question only when it is answered or the session is retired.
- The hub never retires or deletes a `kind 'hub'` row.
- The hub checks that a writer may reach a session an event names; it checks no other authority.
- The endpoint's dedup of to-human notifications is keyed `(writer, seq)` with no project, while sminos numbers a writer's events per project: a fault that exists today, independent of this work, filed as MAWS #761.

**The engine, Claude Code 2.1.326** (`bg-resume-experiment.md`). These are measured facts the wake is built on:

| # | Fact |
|---|---|
| E1 | `claude --bg --resume <id> <message>` on a session that has only run in a terminal continues the same session id, under the settings' defaults (`permissions.defaultMode`, `model`), not the options its terminal process was launched with. |
| E2 | That first background resume accepts flags (`--permission-mode` and `--model` were tried) under the same id and saves them. A later background resume continues under the saved options; given any flag it starts a copy under a new id and says that the session keeps its saved options. |
| E3 | `claude --bg --resume` on a session that any process holds, terminal or background, starts a copy and says that the session is open elsewhere. |
| E4 | `claude --resume <id>` in a terminal, on a session whose background process is live, attaches to that process. There is one process. |
| E5 | Three signals show a process holding a session, and agreed in every check: `claude agents --json`, `~/.claude/sessions/<pid>.json`, and the sminos bridge's socket for the session. |
| E6 | In a mode that asks for approval, a background session waits at its first tool call (`waitingFor: "permission prompt"`; five and a half minutes observed, no timeout seen). |
| E7 | A stopped background session reopened with `claude --resume` in a terminal runs as an interactive process under the interactive defaults, same id. |

Not established, and assigned under Delegated unknowns: how the engine decides that a session has saved options, what `claude rm` or the expiry of the engine's row does to them, which other launch options a first background resume accepts, and whether the person is notified that a background session waits at a prompt.

## Terms

- **The owner.** The person whose sessions these are. Used for the person only. A session record's `owners` field is called "the record's owners", and a VM has "the thread that owns it".
- **Project.** A repository's identity and its locations on machines, as MAWS's project registry defines it. A **location** is a folder of the project on one machine. Every session has exactly one project, read from the directory it was launched in unless it declared another with `sminos join`.
- **Log.** A project's append-only record, one file per writer, which the machines of the org sync through the hub. A **writer** is `<machine>/<session>` (a person at a terminal writes as `<machine>/human`); only that machine appends to it.
- **Member.** A session that has joined a project's log. **Seat** is today's word for a member with a record that outlives its process, which is what `sminos spawn` makes.
- **Thread.** What every member becomes, except a session the MAWS app launched (D1).
- **Channel.** A named set of threads with a log. A project's log is the **automatic channel** of the threads whose project it is, unchanged by this work. A **declared channel** is created with `sminos channel create`, crosses projects, and has the members it was given. "Channel" alone means a declared one below.
- **Pool.** The machines a channel's threads run on, plus machines added to it by hand. Derived, like a channel's repositories (those its members work in).
- **Environment.** A machine and a location on it: a property of the session that fills a thread.
- **Deliver** and **wake.** A message is *delivered* to a live session at its next turn boundary. A *wake* is sminos starting a background process for a stopped thread because a message was addressed to it.
- **The daemon.** sminos's background service on each machine (`sminos daemon`). It delivers messages, resumes stopped seats, and keeps the machine's connection to MAWS.
- **The hub** (MAWS's desk hub) keeps every log of the org. **The endpoint** is the MAWS process on a machine that connects sminos to the hub. **RL10** is the protocol between sminos and the endpoint; its `member` frame states one session and its project. A **capability** is a named feature each side advertises, so that neither sends the other a shape it does not know.
- **Hello, hold, follow, known, the directory.** sminos opens a log at the hub with a *hello*. A machine *holds* a log when it has a session or a checkout there, and otherwise only *follows* it (reads it). Each machine signs a record of the projects it has locations for and of the location-less logs it holds (`known`); the hub assembles the records into the org's *directory* of projects, which every machine receives and follows.
- **Reach.** Who may read a thread and send to it: its access level, its shares, its record's owners. A session record's property.
- **Lane B.** A session MAWS itself launched and reopens. Every other session is lane A.
- **devcloud.** The plugin that makes and deletes cloud VMs (`devcloud vm up|down|ls`), with caps on how many may exist unconfirmed.

## Design

Decisions marked **[binding]** were settled with the whole picture in view, or are the owner's; a child does not reopen them and reports evidence against one to the session holding this document. A mark on a paragraph covers the bullets under it. Everything unmarked is advisory: a child starts from it and may overturn it with evidence, recording the overturn in the Decision Log.

### D1. Threads

**Every lane A member is a thread** **[binding — the owner: "모든 세션이 seat형 스레드"; lane B is left out because MAWS keeps its own record of those sessions, and a second authority over their listing would conflict with it]**. A thread takes four things from today's seat: a durable identity, staying a member when its process ends, being woken by an addressed message, and ending only by a retire or the three-day rule. It does not take a seat's fixed alias or fixed project: a session its human opened is still named after what it is in charge of, and `sminos join` still moves it. A lane B session keeps every rule it has today: it is retired when its process ends, it is never woken by sminos, and it is not placed in a declared channel. *Alternative: keep seats and seat-less members and let a channel hold both.* It lost because the durability fault is exactly that difference: the fleet's standing responsibilities are sessions their human opened.

**The record.** Every thread has a record on its own machine from its first join: a thread id, the session ids it has had, its alias, how it was opened (spawned, or by its human), its declared channel memberships (D3), what its process was launched with, and the permission mode and model it was last observed running under. The record of a thread its human opened is kept where no sminos released before threads reads a seat **[binding — an older CLI on the same machine resumes any seat it sees, with no flags and none of D2's checks (D7)]**; whether it shares code with the seat record is T1's. The mode and model are written as they are observed while the process runs, and say "unknown" where they never were: the bridge's memory of them does not survive its restart, and the mode at a session's last prompt may not be its last mode.

**Naming a thread** **[binding — two other parts name a thread from another machine: a channel request (D3) and a VM's notice (D4)]**. A thread's machine publishes the thread id in the thread's own events. Any machine that may read those events resolves a thread id, or any session id the thread has had, to the thread's current session. The id is the thread's first session id unless T1 finds a reason against it, so that a name recorded before threads existed (a VM's creator tag, a commit's `Sminos-Session` line) already names the thread (contract X2).

**Continuation and refill** **[binding — a continuation carries its predecessor's record owners and reach (`lineage_provenance`, `ensure_record`), so a wrong one is a privacy fault that cannot be undone]**. A thread gets a new session id in three ways, and only the first two carry reach:

1. *Continuation:* a session start whose source is `clear`, under a new id that has no record, in the process that held the old id.
2. *Continuation:* the engine's hand-off to a background job, by the record the engine leaves for it (`continued_in`, `hand_off`).
3. *Refill:* `sminos fill` without `--resume`, or a `spawn` onto the alias, starts a fresh session in a spawned thread. The thread keeps its id, alias, in-charge line and memberships; the new session's record owners and reach come from its own launch, as today.

An in-session `/resume` and a fork are other threads. A fork's start guide says so, since its transcript claims to be the original. *Alternative: "the same process, therefore the same thread."* It lost because one process can resume an unrelated session.

**Lifecycle** **[binding — the owner's rulings of 2026-11-17]**.

- A process ending leaves the thread `stopped`. Today a session its human opened is retired `ended` at that point.
- A message addressed to a stopped thread wakes it (D2).
- A thread **ends** on an explicit `sminos retire`, which a thread may run on itself (how a session being closed for good says so), or once it has been stopped for more than three days. The rule covers every thread, spawned ones included. The end is an event the thread's own machine writes, since only that machine can know the exemption below. An ended thread is folded out of lists and is not woken; a sender is told it has ended.
- An ended thread's record is kept. It **returns**, with its alias, its in-charge line and its memberships, when its human reopens its session, or, for a spawned thread, when it is filled. Nothing else returns it.
- A thread that owns a VM (D4) is not ended by the three-day rule: its machine asks devcloud before ending a thread, and does not end one that devcloud names as a VM's owner, nor one it cannot get an answer about. The VM's idle notice wakes it.
- A thread on a machine that has been retired (a VM that was downed) can write no end of its own. Every reader counts it as ended, from the machine's retirement in the org's state, as such a member reads `gone` today.

A thread's default is standing work under an in-charge line. Short use is allowed: the owner, "thread는 중장기가 가능한 형태이고 그것이 기본이지 단기가 불가능할 이유는 없다" (a thread is a form that can be long-lived, which is its default; nothing makes short use impossible). Bounded work that needs another environment opens a thread there, and the three-day rule clears it without a retire. *Alternative: a "resolved" state a thread sets when its work is done* (the prior-art survey's suggestion). It lost to the owner's rule that work with a defined end is a subagent's, so a thread needs no completion state.

**What stops with the process.** A thread's open asynchronous questions to its human are closed in its project log when its process stops: the question's state lives in the process that asked, and the hub would otherwise count the thread as waiting on its human until it is retired. sminos also tells the endpoint a member is gone when its lane changes, so that a thread MAWS reopens as lane B is not listed twice.

**Verbs that start a process** **[binding — every such path ends in `resume_session`, and D2's guarantees are worth nothing if one path skips them]**. No verb starts a process for a thread its human opened except the wake (D2). `sminos resume`, `fill --resume` and `send --wait` aimed at one go through the wake, with its steps and exclusions, and until T2 ships they are held as an addressed message is. A fresh `fill` of a thread its human opened is refused: its sessions are its human's to open. For a spawned thread these verbs do what they do today, and from T2 on their resumes run the wake's steps too. The verbs that only manage a record (`seat remove`, `retire --purge`) apply to every thread.

**Aliases.** One per thread, the same in every channel. A bare `@alias` resolves among the threads that share the sender's project or a declared channel with the sender; when two answer, the refusal lists `alias#short` for each. Today a bare `@alias` resolves in the sender's project only (`_resolve_tag`), and uniqueness is kept per log (`shadowing`). A stopped thread holds its alias until it ends.

### D2. The wake

**A wake has four steps** **[binding — each closes a fault the experiment or the code showed; engine facts E1 to E7]**:

1. **Refuse while any process holds the session** (E5's three signals). A wake onto a held session would start a copy (E3).
2. **On a first background resume, pass flags; afterwards pass none.** The flags are the permission mode and the model in the thread's record (their last observed values, not the launch's, since both change within a session), the mode capped by the machine's policy ceiling, and from the launch the options the engine accepts on a first background resume. A later resume runs under what the engine saved (E2). Where sminos cannot tell whether the session has run in the background before, it passes the flags: passing none on a true first wake resumes under the settings' default mode (E1), which on the owner's Macs is `auto`. If the engine then answers that it started a copy, stop the copy and repeat step 1: when no process holds the session, the copy was E2's, so wake once more with no flags and remember that this session has saved options; when a process does hold it, the copy was E3's, and the message is delivered to that process as to any live session.
3. **Read the mode the wake actually runs under** from the transcript's new row, which carries it at submission. When it is looser than the recorded mode, or one that asks for approval, stop the process, leave the thread stopped, and publish that its wake came up in the wrong mode (X3), which holds until the thread next runs under its human. The message has reached the transcript by then and counts as delivered; this window is stated and not closed. The model is not enforced: a later wake runs with what the engine saved, and the opening line says which.
4. **Open the wake with a line outside the envelope that carries a peer's words,** telling the thread that it was woken in the background by a message, that its human is not watching, under which mode and model it runs, and which of its launch options were not carried.

**Not woken** **[binding — each is a case where a wake would be unsafe, impossible, or another party's to do]**. Each of these stays `stopped` with the message recorded for it:

- a session under another `CLAUDE_CONFIG_DIR` than the waking process's (`resume_session` refuses it today);
- a thread whose directory is gone;
- a thread its human opened whose directory is inside a macOS protected folder: the daemon's launch there would raise a system dialog charged to the daemon. A spawned thread is resumed there as today;
- a thread on a machine whose policy admits nothing from outside (`read_only`);
- a thread whose last known mode asks for approval (`plan`, `default`, `acceptEdits`). The owner's ruling: "깨우지 않는다" (it is not woken). Woken unattended, it would stop at its first tool call (E6) and wait for a person who is not there. *Alternative: wake it and let it wait.* It lost because nothing established that the owner would learn a background thread was waiting;
- a thread whose mode was never observed. It cannot be shown to be safe, so it is treated as one that asks, until it has run once under a version that records its mode;
- a thread whose last wake came up in the wrong mode (step 3).

A lane B session is not a thread and is never woken (D1).

**Whether a thread's machine will wake it is published in its state** (contract X3), so that a sender's own CLI says so when it sends. The statement is about what the thread's machine will do: nothing publishes whether that machine is on, so a sender is told that the message waits for the machine, and that the thread will or will not be woken there, and why.

`sminos decide`, which answers another session's permission prompt and checks nothing about its caller today, is left as it is. It is a separate matter from the wake.

### D3. Channels

**Creating.** `sminos channel create <name>`, run by a thread, which becomes the first member, or by the owner at a terminal, who names a thread of that machine as the first member. A channel starts with a member on the creating machine because of how logs are followed: the other machines follow a location-less log only while some machine holds a member of it and has opened it without `follow` (D6), and a request reaches another machine only once that machine follows the log. `channel create` and `channel add` are refused on a machine whose endpoint has not advertised the `channels` capability, since the channel could be followed nowhere else.

**The id** **[binding — agreed with MAWS's architect, 2026-11-17; X4]** is a minted UUID, lowercase, with RFC 9562's variant bits and version nibble 8 (the custom version). A project id is version 4 when minted and version 5 when derived from a remote or a machine's name, so every machine tells a channel from a project by the id alone, with no change to the protocol. A hand-written `.smns` id is unconstrained, so MAWS checks its table for an existing version-8 id before the rule is adopted, and `channel create` refuses an id the directory already holds. `sminos join <channel>` is refused and names `sminos channel add`: `join` moves a thread's project, and a channel must never become one. *Alternative: a hub record that declares a channel and its members.* It lost when membership became the member's own statement (below): nothing was left for the record to say, and it needed an authority for who may assert another machine's membership. *Alternative: a field on the hub's row.* It lost because the hub keeps the first hello's facts forever.

**Names.** The name reaches the hub with the log's first hello, as a project's does. A name is a label: two channels may share one, and a channel may share one with a project. Wherever a name is taken (`--in`, `@name/alias`, `channel add`), one that more than one log answers is refused, listing each with its kind and `name#short`; an id always works.

**Membership** **[binding — the log's standing invariant that a thread's membership has one writer (`lifecycle`, `_memberships`, `_projection`), and the registry's rule that a change to a machine is a request that machine carries out and then states]**. `sminos channel add <channel> [<thread>...]` and `sminos channel remove`; with no thread named, the caller. An add or a remove of another thread is a request, and the thread's machine carries it out. Two records:

- *The request,* in the channel's log: one event per thread, naming the thread by a session id it has had. It names the target where the hub's check of who may reach a session reads it. It never names the target in the field that addresses a message, which today's sminos would deliver and wake a seat for (`_owed`, `push_event`).
- *The statement,* in the thread's project log: its own kind of event, written by the thread's machine under the thread's current writer, in the same pass that holds the reach permit for that writer. A statement carries the thread's whole set of declared channels and, when it answers a request, that request's writer and seq and whether it was applied or refused, with the reason. The latest statement under the thread's current writer is the thread's membership. The machine restates the set whenever the thread gets a new writer: a continuation, a refill, a `join`, or a change of reach that opens a new stream.

What follows from that:

- *Who may ask* **[binding — the hub checks reach and no other authority, so every reader must apply one rule]**. A thread's machine honours a request when the request's writer may converse with the thread, and a thread may always add or remove itself. There is no other authority: members are siblings. A request it does not honour gets a statement that refuses it: the requester may not converse with the thread, the machine's policy admits nothing from outside, or the session is lane B.
- *Order.* The thread's machine applies requests in the order they reach it, and its statements record that order. A request a statement already names is not applied again. No clock decides between machines.
- *Roster.* A roster is read across project logs, which every machine of the org follows. A row is built from the member's own project log as the reader may read it, so a thread that went private is not kept visible by an old add. A thread that has ended, or whose machine was retired, is not in it.
- *Pending* is a request that no statement names yet and that has not expired. It is listed with the machine it waits for and since when; sminos cannot tell an off machine from one whose sminos predates channels, and says so.
- A thread's memberships live with its record and return with it (D1).
- A thread learns of a channel from the frame of the first message that reaches it from there, and from the guide at its next start. Adding wakes no one, and neither does removing.

*Alternative: the actor writes the membership into the channel's log* (the first design). It lost to the critic's first pass: two machines writing one thread's membership need an order between machines, and the log has none.

**A channel exists while it has a member that has not ended** **[binding — it follows from a channel owning nothing: there is no one to end it]**. When its last such member ends or is removed it leaves the directory, each machine's sminos stops following it a day later (its leaving rule), and the hub retires its row once no machine's record has listed it as known for seven days. It returns, and the hub's row is active again, when a member does. The hub keeps the log throughout, and a machine that stops following keeps its copy (`has_left`). There is no archive verb and no record of a channel beside its log and its members' statements. *Alternative: an event that ends a channel.* It lost because someone would have to be allowed to write it.

**The timeline** **[binding — a message belongs to one log, and MAWS drives its notifications and waiting counts from three kinds of event]**. A message goes into a channel's log when it names the channel: `sminos say --in <channel> ...`, or a tag qualified with it, `@<channel>/<alias>`, as `@<project>/<alias>` names a project's log today. With neither, `say` does exactly what it does today. In a channel the tags mean what they mean in a project's log: `@thread` is delivered or wakes, `@all` is delivered to the channel's live members, untagged is a record nobody is prompted for. The reply line in a message's frame names the log the message came in, so a reply lands there. A channel's log never carries a `message`, a `question` or an `answered` event, and no RL10 host or pending frame names a channel id: a thread's words to its human stay in its project's log. *Alternative: a session's "current channel" as the default target.* It lost because a wrong default sends work to the wrong audience without an error; the survey's strongest finding on routing is to make the address explicit.

**The lead** **[binding — the owner]**. None by default. `sminos channel lead <channel> <thread|none>` is the owner's act alone: it is run at a terminal and confirmed there by a typed yes (the check `confirmed` in `S/sminos_visibility.py` makes for widening reach), and is refused where there is no terminal. The event is written under the machine's human writer, and every reader ignores a lead event under a session's writer. While a lead is set, a message the owner posts to the channel with no tag is addressed, on the machine where the owner types it, to that thread; a lead that has ended or left is ignored. A machine delivers a person's words only when it can verify them (MAWS `src/endpoint/rl10/words.ts`), so until the app posts to channels this works from a terminal on the lead's own machine. A machine's notice (D4) is never read as the owner's post.

**Listing.** Bare `sminos list` shows the caller's project and every declared channel it is in, each with its roster. A declared channel's roster shows its stopped members; a project's folds them as today. `--channel` filters; today's filters stay. `sminos channel show <name>` prints one channel: its members and its pool.

### D4. Environments

**Opening a thread elsewhere.** `sminos spawn ... --on <machine>` opens the thread on that machine, and `--on new` makes a devcloud VM first. sminos places and devcloud provisions **[binding — the owner: no scheduler]**: `--on new` runs `devcloud vm up`, whose caps, consent rules and exit codes are unchanged and decide whether a VM is made; sminos waits for the machine's enrollment and spawns there. `--channel <name>` (repeatable) names the declared channels the new thread starts in; a new thread does not inherit its opener's.

The first version reaches a VM over ssh from a Mac, as `devcloud vm ssh <name> -- sminos spawn` does by hand today. Two cases are refused, each naming its reason, and wait for a later design: `--on` asked from a VM (devcloud does not run there), and `--on` naming a Mac (a Mac's login keychain is closed to an ssh session, so `claude` over ssh to a Mac is not relied on). Both want the shape of a channel add: a request the target machine's daemon carries out under its own policy.

**The pool** is derived: the machines a channel's threads run on, and machines added by hand (`sminos channel env add|remove <channel> <machine>`, events in the channel's log, honoured from any member that has not ended; the last by merge order holds, as a status does). A machine may be in many pools. The pool constrains nothing and chooses nothing **[binding — the owner: "채널은 단순히 어떤 env pool이 이 채널에 존재하는지 명시할 뿐이다"]**. `sminos channel show` prints it with, for each machine, how many threads are live and how many stopped there, counted from the logs the reader may read, and for a VM the thread that owns it, its age and its cost, where the command runs on a machine that has devcloud; elsewhere it says those columns are not available. *Alternative: a machine belongs to one pool* (what Buildkite and GitHub's runner groups moved to). It lost because those systems needed a security boundary between teams, and this fleet has one owner. A machine's load average is not shown: nothing publishes it (Deferred).

**A VM is owned by the thread that made it** **[binding — the owner]**, and devcloud is the authority for who that is. devcloud records the creator as it does today, as a tag naming the creating session; D1's naming rule makes that tag a name of the thread, so a VM made before this work is already owned by a thread. `devcloud vm owner <vm> <thread>`, a new verb, hands a VM to another thread. sminos keeps no copy: when it would retire a thread or end one by the three-day rule, the thread's machine asks devcloud which VMs name the thread, refuses the retire while there is one, naming it, and neither retires nor ends a thread it cannot get an answer about. *Alternative: sminos keeps what a thread owns in the thread's record* (this design's first form, chosen so that a retire need not ask a cloud). It lost because nothing would keep the copy true through a `vm down`, a handover to a thread on another machine, a lease's end or a `reap`, and a stale entry would refuse a retire forever.

**Notices.** A VM's idle and lease notices are sent from the VM, as today, to the tag of the thread that owns it, which reaches the thread's current session and wakes it if it is stopped. When that thread cannot be woken, devcloud's order holds as today: the live members of the owning thread's project, then that project's log. A notice is also recorded in the timeline of each channel whose pool holds the machine. It is written as it is today, by the VM's own `say` under the VM's human writer, with a marker that says it is a machine's notice; the lead rule and every reader of "what the owner posted" leave marked events out (contract X8).

**A VM that `--on new` makes is kept** **[binding — the owner: "kept, 소유 스레드가 내린다"]**, which is devcloud's default. It lives until the thread that owns it downs it; the idle notice, every three idle days, wakes that thread to decide. `devcloud vm down` refuses over unpushed work, so no deadline takes work with it. *Alternative: a lease that renews while a thread on the machine has not ended.* It lost because a VM whose lease ends is deleted with everything on it (`devcloud/skills/vm/SKILL.md`), unpushed work and its threads' transcripts included, so those threads could not return. A spawner that wants a lease makes the VM with `devcloud vm up` itself and names it with `--on`.

### D5. The CLI and what sessions are taught

One surface **[binding — the owner]**. MCP tools were weighed and declined: the owner, "say와 send를 하나로만 둔다면 굳이 mcp가 필요할지" (if `say` and `send` are one, is MCP needed at all). What tools would have fixed was fixed in the CLI in sminos 1.48.0 (PR #509): `sminos` on a session's PATH through the plugin's `bin/`, a message body from standard input, and a hook that refuses a sminos call whose arguments hold a backtick the shell would run (six of 4,311 `say` and `send` calls in 21 days did; one ran a command on the sender's machine).

- `send` leaves what sessions are taught: for a member it does what a tagged `say` does. It stays for scripts (`--wait`, Codex threads).
- `join` keeps today's meaning, declaring a thread's project, since everything the owner looks at is keyed by project until the app has a channel view. A thread that should leave a repository's automatic channel joins its machine's project.
- The session-start guide and the skill (`sminos/skills/sminos/SKILL.md`) speak of threads and channels. The skill is behaviour: it changes through doperpowers:writing-skills and is evaluated. The manager's skill (`sminos/skills/manager/`), which imports the CLI's modules, moves with it (contract X6).

### D6. Storage and the wire

- **A declared channel is a log,** which sminos opens with an ordinary hello and the hub registers as it registers any id it does not hold.
- **A thread's own facts stay in its project's log** **[binding — MAWS keys the per-session view, notifications and pending counts by project, and the hub refuses a second copy of a reach change]**: its lifecycle events, its membership statements, its words to its human. A declared channel's log holds requests, hand-added machines, the lead, and what is said in the channel. Nothing is duplicated.
- **A thread's project stays single** **[binding — MAWS's listings, notifications and the app's rows each hold one project per session]**; its declared memberships are a set beside it. The three places that hold one project per session (Grounding Baseline) keep doing so.
- **What sminos does for a channel on the wire** **[binding — MAWS's conditions]**: the member's machine opens the channel's log without `follow` while it holds a member of it; it sends no machine presence and no checkout under a channel id; and it sends no host or pending frame under one (D3).
- **The contract with MAWS** **[binding — agreed with MAWS's architect, 2026-11-17; X5]** is one change in that repository:
  - a capability pair named `channels`, in hello and welcome, with the RL10 conversation fixture extended in the same change on both sides;
  - the `member` frame's optional `channels`, a bounded list of ids, counted only when the hello listed the capability, and read in one place, so that a channel is in the machine's `known` while the machine holds a member of it;
  - one predicate, `isChannelId`, with test vectors shared with sminos's suite; by it MAWS refuses to link a folder to a channel id and refuses a member whose project is a channel id (which an older sminos would allow by `join`);
  - the hub retiring a channel's row once no machine's record has listed it as known for seven days, and making it active again at the next record that lists it;
  - for threads: the endpoint withdrawing a session's old listing when its lane changes, and the web desk's two sentences that say a closed terminal session is reopened only by its human.
  No declaration record, no new kind of project at the hub, and no change to listings or notifications. MAWS treats no channel event as authoritative.
- **MAWS #761** (Grounding Baseline) is independent of all of this and wanted regardless.

### D7. Versions in the field

The owner's machines update sminos at different times, and one machine runs several versions at once, so each release must be safe beside an older one **[binding — the Grounding Baseline's facts about which copy each process runs]**.

*Between machines.*

- A reader comes before its writer. A machine on an older sminos must skip an event kind it does not know (as read, `_projection` skips kinds outside `LIFECYCLE`; each child that adds a kind verifies this against the oldest version still installed, and ships the reader a release ahead if it does not hold).
- A request to a machine whose sminos predates channels stays pending (D3). A sender on an older sminos is told what it is told today, not what X3 publishes.
- An older sminos sees a channel as a project and would let a session `join` it; MAWS's endpoint refuses that member (D6).
- Each child's merge leaves both repositories releasable, and bumps its plugin's version in the same change (`scripts/bump-version.sh`).

*On one machine.* A session started before an update keeps running the version it loaded, in its hooks and in any CLI path it was told, while the daemon runs the newest. An older CLI applies the old rules to the shared store: it retires a stopped seat-less session `ended`, and it resumes any seat it finds stopped. So:

- No sminos of any released version wakes a thread its human opened before T2's wake is in force on that machine. This is why such a thread's record is kept where older code reads no seat (D1).
- A change to who stays a member, who is retired or who is resumed takes two releases. The first teaches every CLI path that reconciles membership, retires or resumes to stand down when the machine's store says rules newer than the CLI knows are in force, and records each session's CLI version where the daemon can read it. The second carries the rules, and the daemon puts them in force on a machine only when no live session there runs a CLI older than the first. Until then that machine keeps the old rules, and the daemon names the sessions it waits for.

### Delegated unknowns

Each is assigned to the child that settles it.

| Unknown | Settled by |
|---|---|
| How the engine decides a session has saved options; what `claude rm` or the expiry of the engine's row does to them; which launch options a first background resume accepts beyond the mode and the model; first-wake flags on a session that was backgrounded once and then used in a terminal; what differs in a wake's environment from the terminal's | T2's spike milestone |
| Whether a compaction gives a background session a new id. A friction entry says so; no code shows it. If it does, it is a third continuation case, keyed as `clear` is | T1, a live check before the continuation rule is built |
| Whether a plugin reload moves a live session's hooks to the new version, which decides how long a machine waits for the rules to come into force | T1, before its second release |
| How a thread whose reach is not the default says something in a channel: which stream it is written under, and how the channel's hub object learns that stream's policy | CH, with MAWS |
| How long a pending request lives before it expires | CH |
| How `--on new` derives the VM's label, project and branch and the new thread's directory | EN (leaning: from the spawner's repository and branch, as `devcloud vm up` reads them from the directory it runs in) |
| Whether the three-day clock should stop while a machine is off. A thread returns when reopened, so the simple rule costs a fold, not a loss | Observation after T1 |
| Noise from plural membership. The survey found no account of it either way; the lever is that a post prompts no one | Observation after CH |

## Children

### T1: Threads: identity and lifecycle — plan

- **Purpose:** make every lane A member a thread in everything but the wake: the record and the published id, `stopped` in place of `ended`, the three-day rule, self-retire, the return of an ended thread, continuation and refill, and the observation of mode and model that the wake will need. This is the half of the durability fault that needs no engine experiment, and it is what every later child reads.
- **Acceptance:**
  - **G1 (required), the stand-down release.** With it installed, a CLI that finds the machine's store marked with rules newer than it knows does not reconcile membership, retire or resume, and says so once. Each session's CLI version is recorded where the daemon reads it, and a command names the live sessions that still run older code. Nothing else changes.
  - **G2 (required), the lifecycle,** in force on a machine once no live session there runs a CLI older than G1's:
    1. A session opened in a terminal, then exited, is listed `stopped` by `sminos list --stopped`, where today it is gone. Reopened with `claude --resume`, it is listed live under the same alias and in-charge line, and receives what was recorded for it meanwhile.
    2. A message addressed to it while stopped is recorded, and the sender's CLI says the thread is stopped and is not woken because its human opened it (the hold T2 lifts). `sminos resume`, `fill --resume` and `send --wait` aimed at it start no process either, and a fresh `fill` of it is refused. A spawned thread is woken exactly as today.
    3. After `/clear`, the new session id carries the thread: same thread id, alias, in-charge line, record owners and reach. A fork and an in-session `/resume` are other threads, and a fork's start guide says it is a copy with an identity of its own. A refill keeps the thread and takes its reach from the new launch.
    4. A thread stopped for more than three days (a clock a test can set) is ended by an event its machine writes: out of `sminos list` and `--stopped`, shown by `--all`, and a message addressed to it reports that it ended. A thread devcloud names as the owner of a VM, by today's creator tags, is not ended, and neither is one devcloud could not be asked about. Reopening it, or for a spawned thread `sminos fill`, returns it with its alias and in-charge line.
    5. `sminos retire` run by a session on itself ends its thread, and the end holds after its process exits against everything but its human reopening it.
    6. The thread's events carry its thread id, and a tag that names a former session id of a thread (`@alias#short`, `@short`) reaches its current session, from another machine too.
    7. A thread's record holds its launch's options and the mode and model it was last observed under, current to within the bridge's heartbeat, and "unknown" where none was observed.
    8. A stopped thread's open asynchronous questions are closed in its project log, and a member whose lane changes is told gone to the endpoint first.
    9. A thread on a retired machine is listed as ended on every other machine.
    10. The oldest sminos the fleet can still run from a plugin cache, run against a store on which the new rules are in force, neither resumes a thread its human opened nor retires a stopped one.
    11. Parent acceptance line 8 for this child's surface: the sminos suites pass, with the tests that pinned `ended` for a seat-less session changed to pin `stopped`.
- **Edges:** blocked-by: —. blocks: T2, CH, EN.
- **Contracts:** X1 (owner), X2 (owner), X3 (the first values), X6, X7 (owner of the two-release mechanism).
- **Design inheritance:** D1 whole and D7 (binding where marked). Advisory: the differences to remove are the rows of the Grounding Baseline's table; `retirement_holds` loses its reason once a retire is a record; the continuation event for `/clear` can take the shape hand-off's has (`retired`, reason `continued`, `to`), and a refill a reason of its own, since it carries no reach; devcloud's driver already resolves a session to its tag through `sminos who --session` (`devcloud/driver/context.py`, `session_creator`), and the reverse question, which VMs name this thread, is asked of devcloud's inventory on a Mac and is "none" on a machine without devcloud.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (dispatchable once the owner has looked at this cut).

### T2: The wake — plan, opening with a spike

- **Purpose:** let an addressed message wake any stopped thread, a session its human opened included, without starting a copy, loosening its permission mode, or leaving a process waiting on a person who is not there.
- **Acceptance:**
  - **G1 (required), the spike's findings** recorded in this document's Surprises & Discoveries, each Delegated unknown assigned to T2 answered, or shown unanswerable with what the wake does instead.
  - **G2 (required):**
    1. Parent acceptance line 3: same session id, one process, the recorded mode (capped by the machine's ceiling, never looser) and on a first wake the recorded model, the opening line, and a terminal `claude --resume` that attaches.
    2. Parent acceptance line 4, and the same for each other case of D2's "Not woken": no process starts, the message is recorded, and the reason is in the thread's published state and in the sender's output, on the thread's machine and on another.
    3. A thread stopped before its mode was ever recorded (one closed before T1's second release, or whose mode changed after its last prompt with no observation) is not woken and says why, until it has run once under its human.
    4. With a process holding the session, no wake is attempted and no copy exists afterwards. When a process takes the session between the check and the launch, the copy is stopped, the message is delivered to that process, and nothing is remembered about saved options.
    5. When the engine starts a copy because the session already had saved options, the copy is stopped, the thread is woken once more without flags, and a second wake of that thread passes none.
    6. A wake that comes up looser than recorded, or in a mode that asks for approval, is stopped within the turn; the thread stays `stopped`, publishes the reason, and a second message starts no process.
    7. `sminos resume`, `fill --resume` and `send --wait` aimed at a thread its human opened run the same steps and exclusions as a message does; a spawned thread in a protected folder is resumed as today.
- **Edges:** blocked-by: T1. blocks: EN.G1 (a notice wakes a stopped thread that owns a VM).
- **Contracts:** X1 (reads the mode, model and launch options), X3 (owner), X6, X7.
- **Design inheritance:** D2 whole (binding). Engine facts E1 to E7. Advisory: `resume_session` is the path to extend, and its `copy_started` check already parses the engine's note of a copy; the transcript row that carries `permissionMode` at submission is the reading for step 3; the experiment ran one session at a time on a Mac at load 40, so timings there are upper bounds. A wake runs in the waking process's environment, not the terminal's (`resume_session`'s docstring): a gateway route or credentials the terminal process had are not carried, the session record's `inference` is not applied again, and the spike records what differs so that the opening line can say it.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1).

### MW: MAWS: channels at the endpoint and the hub — brief, in the MAWS repository

- **Purpose:** MAWS's half of the wire, as one change: a machine's record lists a declared channel as known while the machine holds a member of it, a channel id is told from a project id everywhere MAWS takes one, an emptied channel's row is retired, and a thread that stays `stopped` is handled where MAWS assumed a closed session was gone.
- **Acceptance:** D6's contract, item by item, each with MAWS's own test: with the capability advertised by both sides, a `member` frame carrying `channels: [<id>]` puts `<id>` in the machine's `known` while that member is held and its log is opened without `follow`, and removes it when the last such member goes; without the capability on either side, frames and `known` are byte for byte what they are today; `isChannelId` passes the shared vectors; a link to a channel id and a member whose project is a channel id are refused; a channel's row retires after seven days unlisted and is active again when listed; a lane change withdraws the old listing. The RL10 conversation fixture (`test/endpoint/rl10/conversation.json` in MAWS, copied to `sminos/tests/rl10-conversation.json` and replayed by `sminos/tests/rl10_conformance.py`) carries the capability and one case with `channels`.
- **Edges:** blocked-by: —. blocks: CH's cross-machine gates. It is inert until sminos advertises the capability, and its two thread items are wanted by T1's second release without blocking it (sminos sends gone at a lane change on its own).
- **Contracts:** X4, X5 (owner of MAWS's half).
- **Design inheritance:** D6 (binding). MAWS's own process decides how the change is built and reviewed there; this section is the contract it is built to, and MAWS's architect holds it.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (contract agreed 2026-11-17; built in MAWS once the owner has looked at this cut).

### CH: Channels — decomposing at dispatch

- **Purpose:** the declared channel itself: the membership set and its statements, the request and its application by the member's machine, channel logs and how machines follow them, the `channel` verbs, saying something in a channel, listing, aliases across channels, the lead, and the skill and guide that teach all of it.
- **Acceptance:** coarse, sharpened at its own cut:
  - parent acceptance lines 1, 2 and 7, across two machines, and line 8 for its surface;
  - a request to a machine that is off is listed pending with the machine and since when, and is applied when the machine returns; a request the thread's machine does not honour is answered by a statement that says why;
  - a thread that goes private drops out of a roster a reader may no longer see it in; an ended thread that returns is in the channels it was in (parent line 6);
  - a bare `@alias` reaches a thread that shares only a declared channel with the sender, and two answers are refused with `alias#short` for each; a name that a project and a channel both answer is refused the same way;
  - `sminos join <channel>` is refused and names `channel add`; `channel create` and `add` are refused on a machine whose endpoint lacks the capability;
  - the lead: set by the owner at a terminal with a typed confirmation, refused from a session, and an untagged post of the owner's reaches that thread; a lead event under a session's writer changes nothing;
  - `channel env add|remove` shows in `channel show`, with the thread counts of D4;
  - no `message`, `question` or `answered` event and no presence or checkout is ever written under a channel id;
  - the skill's evaluation shows a fresh session creating a channel, placing others, and speaking in it without a message in the wrong log.
- **Edges:** blocked-by: T1; its cross-machine gates blocked-by MW. blocks: EN.G2.
- **Contracts:** X1 (the memberships field), X4 (owner), X5 (sminos's half), X6 (owner of the rewrite), X7, X8 (the reader).
- **Design inheritance:** D3 whole, D5, D6 (binding where marked). Advisory, from the code map: `_local_sessions`, `_reconcile` and `retire_moved` are where membership is decided today; `holds` (the uplink) decides whether a log is opened as followed and must count a declared membership as a session there; `known_checkouts` counts every directory a session joined a project from, which is why membership is not a `joined` event in the channel's log; `cmd_say` refuses `--in` for a session today; the peer frame's reply line (`reply_line`) still models a double-quoted body under an absolute path and is due in this child's skill work (`docs/doperpowers/TECH-DEBT.md`, the backtick guard). Residue for its own cut, with the answers this design leans to: an untagged post or `@all` in a channel is a member's, while a tagged message from outside follows today's cross-project rule; `channel show` and `channel env` belong here and the VM columns to EN; a likely seam is membership and its wire on one side, traffic and the taught surface on the other.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1; deliberately late — see Ordering).

### EN: Environments — plan, in sminos and devcloud

- **Purpose:** open a thread on another machine with one command, and make a VM's owner a thread, which outlives the session that made the VM.
- **Acceptance:**
  - **G1 (required):** `sminos spawn --on <vm>` and `--on new` from a Mac open a thread on the VM, with devcloud's caps and consent rules deciding whether a VM is made and its refusals passed through; `--on` from a VM and `--on <a Mac>` are refused, each naming its reason. `sminos retire` of a thread that owns a VM is refused and names it, until the VM is downed or handed over with the new `devcloud vm owner`. A VM's notice reaches the current session of the thread that owns it after that thread changed session id, for a VM made before this work too; it wakes that thread if it is stopped, and when the thread cannot be woken it goes on to the project's live members and then the project's log, as today.
  - **G2 (required):** parent acceptance line 5: `--channel` places the new thread, `sminos channel show` lists the VM with the thread that owns it, its age and its cost on a machine that has devcloud, and a notice is recorded in the timeline of each channel whose pool holds the machine, marked as a machine's notice and never taken for the owner's post.
- **Edges:** G1 blocked-by: T1, T2. G2 blocked-by: CH.
- **Contracts:** X2, X3, X6, X7, X8 (owner).
- **Design inheritance:** D4 whole (binding where marked). devcloud is a plugin of its own and versioned on its own (`scripts/bump-version.sh --plugin devcloud`); `vm owner`, the marker on a notice and any change to how the creator is written are devcloud's changes. Advisory: `devcloud vm ssh <name> -- sminos spawn` is today's manual path.
- **Required:** required for parent acceptance.
- **Status:** not-dispatched (blocked-by T1, T2; deliberately late).

## Cross-Child Contracts

- **X1. The thread record.** Owner: T1, which fixes its names in its plan's Interfaces section before T2 starts. One record per thread on the thread's machine, read and written through one module. Fields the design requires: the thread id; the session ids the thread has had and its current one; the alias; how it was opened; the launch's options and the last observed permission mode and model (T1 writes these; T2 reads them); the declared channel memberships (CH writes these). A child adds a field only through that module. The record is local to the machine and is never what another machine reads: others see what the thread's machine wrote to the log.
- **X2. Naming a thread from elsewhere.** A thread's events carry its thread id. A thread id, or any session id a thread has had, resolves to the thread's current session on any machine that may read the thread's events; a tag that names a former session reaches the current one. Session ids stay what addresses a message. Owner: T1. Consumers: CH (a request's target), EN and devcloud (a VM's creator tag).
- **X3. Whether a thread's machine will wake it.** Published by the thread's machine in the thread's state in its project log: woken or not, and when not, one reason from a fixed list (opened by its human while the wake is not shipped, which T1 writes and T2 retires; another config dir; directory gone; a protected folder; the machine admits nothing from outside; a mode that asks for approval; mode never observed; its last wake came up in the wrong mode; ended). A sender's CLI reads it at send time on any machine and reports it with the machine the message waits for. Owner: T2. T1 lands the three values it needs: woken (a spawned thread, as today), held (opened by its human), and ended.
- **X4. Which log holds what, who writes it, and what a reader honours.** A thread's lifecycle events and membership statements: its project log, under its own writer, by its own machine. A channel's log: requests, hand-added machines, the lead, and what is said in the channel; never a `message`, `question` or `answered`. No event about a thread is written by another machine's writer, except a request, which states what is asked and nothing about what is. A request is honoured as D3's "who may ask" says; a hand-added machine from any member that has not ended; a lead only under a machine's human writer. The channel id is as D3 states, and one set of vectors for it is kept in MAWS and copied to sminos's suite. Owner: CH for the kinds' names and shapes; the placement and the rules bind every child now.
- **X5. The wire.** RL10 stays at its version; the capability pair `channels` gates `member.channels`. Each side is inert until the other advertises it. The conversation fixture is one file, changed in MAWS and copied byte for byte. Owner: MW for MAWS, CH for sminos.
- **X6. What sessions are taught stays true.** Each child changes the guide text, `sminos/skills/sminos/SKILL.md`, the spawn preamble and the nested `CLAUDE.md` files for what it changes, through doperpowers:writing-skills with a small evaluation. The rewrite into the words "thread" and "channel", and the manager's skill, are CH's. Until then a child uses today's words and adds only what became false.
- **X7. Releases.** D7, for every child. T1 builds the two-release mechanism; T2, and any later child that changes who is retired or resumed, uses it.
- **X8. A machine's notice.** An event written by a machine's own `say` under its human writer that carries the notice marker is a machine's notice. It is never the owner's post: the lead rule skips it, and so does anything else that reads what a person said. Owner: EN (devcloud writes the marker). Reader: CH.

## Ordering & Dependency Map

```
T1.G1 ─▶ T1.G2 ──▶ T2 ──▶ EN.G1 ──┐
            │                     ├──▶ EN.G2
            └──────▶ CH ──────────┘
                     ▲
MW ──────────────────┘ (CH's cross-machine gates)      MAWS #761: independent
```

T1 first: it is what every other child reads, and it needs nothing from the engine. Its first release has to be installed across the fleet before its second takes effect anywhere, so it ships early and alone. T2 next, so that the durability fault is whole before channels exist. CH and EN are cut when they near execution: their boundaries depend on what T1's record looks like, and a cut drawn now would be redrawn. MW can be built in MAWS at any time; it is inert until sminos advertises the capability. EN.G1 needs only T1 and T2 and could run beside CH. T1 and T2 change the same functions of `S/sminos.py` and run one after the other.

## Risks & Mitigations

- **A wake under a looser mode than its human chose.** Steps 2 and 3 of D2, the "mode never observed" exclusion, and T2's gate G1 before any wake code ships. T1 ships with every path into `resume_session` held for a thread its human opened.
- **An older sminos on the same machine applies the old rules.** D7's two releases, the record kept where older code reads no seat, and T1's acceptance 10.
- **A wrong continuation hands one thread's record owners and reach to another.** The rule is two cases, keyed on evidence the engine writes, and T1 pins a fork, an in-session `/resume` and a refill as not carrying reach.
- **A long-quiet spawned thread now ends after three days,** where today it would be woken a week later. The sender is told it ended; `sminos fill` returns it. Watched after T1 (Delegated unknowns).
- **A VM whose owning thread cannot be woken** (a mode that asks, a Mac that is off) keeps costing while its notices are only recorded. devcloud's order sends the notice on to the project's live members; `sminos channel show` lists the VM's age and cost.
- **Every machine follows every channel's log,** which costs the hub one renewal per open log per heartbeat and each machine one policy rebuild per newly opened log (`code-map.md` §2). An emptied channel leaves the directory and its row is retired after seven days. Measured in CH if channels number in the tens.
- **A woken thread runs with the waking process's environment,** which may route inference or hold credentials differently from the terminal it was opened in. T2's spike measures the difference and the opening line states it.
- **Two repositories, two release trains.** X5's capability makes each side inert alone; X7 orders reader before writer.
- **`S/sminos.py` is one file of some thirteen thousand lines.** Children that change the same functions run in sequence (Ordering).

## Deferred / Out of Scope

**Deferred (may return):**

- A spawn the target machine's daemon carries out on request: a thread opened from a VM, and from one Mac on the other.
- The app's view of channels in MAWS, under a word of its own ("channel" already names two other things there), and with it the lead set and used from any device, and waking or sending to a stopped thread from the app.
- A machine publishing its load and whether it is on, and with it a load column in `channel show` and a sender being told that a thread's machine is off.
- An answer to a stopped thread's question that wakes it, in place of the question being closed.
- A channel that carries questions to the owner.
- Moving a thread to another machine, and the handoff document that would need.
- The stopped state, without the three-day rule, for lane B sessions.
- A check of who calls `sminos decide`.

**Explicitly out of scope (standing exclusions):** MCP tools for sminos's verbs; a scheduler or default placement; a channel owning a lifecycle or a machine; a structural lead; a channel as a boundary of who may read (see Purpose).

## Tracking Map

| Child | Artifact | Status |
|---|---|---|
| (landed before this cut) CLI on PATH, stdin bodies, the backtick guard | PR #509, sminos 1.48.0; residue in `docs/doperpowers/TECH-DEBT.md` | landed 2026-11-17; PATH verified on an installed 1.48.0 in an interactive session, a `--bg` seat and a subagent (PR #510) |
| T1 | — | not-dispatched: waits for the owner's look at this cut |
| T2 | — | not-dispatched: blocked-by T1 |
| MW | the contract of D6, agreed with MAWS's architect in the two projects' sminos chat on 2026-11-17 | not-dispatched: waits for the owner's look |
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
- Observation: one machine runs several sminos versions against one store, so a rule about who is resumed or retired is only as strong as the oldest CLI a live session still runs.
  Evidence: `installed_cli` (the daemon runs the marketplace clone); `smns-record.sh` runs `$CLAUDE_PLUGIN_ROOT/skills/sminos/scripts/sminos`; both reviewers of this document reproduced the two old paths (`_reconcile`'s `ended`, `push_member`'s resume of a seat) by reading and by an isolated probe.
- Observation: a VM's notices are sent from the VM, addressed by a tag, so the name of the thread that owns a VM must resolve on a machine that is not the thread's.
  Evidence: `devcloud/boot/devcloudlib/notices.py`, `deliver`; `descriptor.py`, `_CREATOR`.

## Decision Log

- 2026-11-17 — **Verification.** The design was debated with the `doperpowers:critique` agent in two passes before approval; each finding was checked against the code it cited (see the entries below). This document gets one independent design review (a general-purpose agent on the frontier model) and, in the same round, the `doperpowers:adversarial-reviewer` on the roadmap sections for whether the children are complete, well cut and buildable from this document and the code. Each code-bearing child's branch gets doperpowers:review-code at the high rung: T1 and T2 change who stays a member and what is launched unattended, with privacy and permission consequences. Closing the unit is a scale review at recomposition: two repositories and cross-child invariants. The spec and its roadmap were written as one document and reviewed in one round, in place of a spec review followed by a second review of the cut: the design was already matured and debated, and the reviewers read a more complete artifact.
- 2026-11-17 — **Approval, with a condition.** The owner approved the design and asked to look again before implementation starts. Nothing is dispatched until then.
- 2026-11-17 — **What the critic's first pass changed.** Membership became a request the member's machine applies, which removed the question of order between machines, a hub record declaring a channel, and an archive verb. A reach change is no longer written into every log: the hub would refuse the second copy. Thread identity moved ahead of channels in the order of work. The wake gained its checks and its opening line. `join` kept its meaning. One Mac opening a thread on the other left the first version.
- 2026-11-17 — **What the critic's second pass changed.** A thread is no longer "today's seat" whole: the four things it takes are named, and T1 holds the wake until T2. The membership statement is placed in the thread's project log and the request's shape fixed. A channel starts with a member on the creating machine and its id says what it is. The continuation rule is keyed on the start's source. The wake passes the last known mode and model, has a rule for doubt, reads the mode from the transcript, and publishes whether a thread can be woken.
- 2026-11-17 — **The owner's last three rulings.** A thread whose mode asks for approval is not woken (and a wake that comes up in such a mode is stopped, taken as that ruling's consequence). A VM made by `--on new` is kept. MAWS's architect was sent the contract before approval.
- 2026-11-17 — **Decided without asking,** each a technical consequence of the design: no archive; a new thread starts in the channels `--channel` names and does not inherit its opener's; a thread learns of an add or a remove from the first message from that channel or the guide at its next start; the words stay "channel" and "thread", and MAWS's "direct channel" becomes "thread" in documents as they are touched; a thread carries no handoff document; a spawner that wants a lease makes the VM itself.
- 2026-11-17 — **The cut.** T1 and T2 are cut to plan grain now; CH and EN are left coarse and cut at dispatch (the frontier rule: a boundary drawn for far-off work goes stale as its siblings land). MAWS's half of the wire is its own child because another repository's process builds it. Alternative rejected: one child for all of sminos's side, which chains unrelated behaviours and would put the wake's engine risk in the same branch as the membership model.
- 2026-11-17 — **MAWS's reading** (its architect, against MAWS's trunk, in answer to five questions). No objection to the shape. Taken: lane B keeps today's rules entirely, so "every member" became "every lane A member" (a change to a ruling of the owner's, reported to the owner); a channel's log is opened without `follow`, and carries no presence, checkout, host frame or word to a human; the id is version 8 under one shared predicate; MAWS refuses a link to a channel id and a member whose project is one; the capability is named `channels`; sminos closes a stopped thread's open questions and says gone at a lane change; who may add, remove and lead is stated for every reader. Retention was MAWS's request: this design proposed the derived rule over an event, and MAWS set seven days. Alternative rejected: an event that retires a channel, which needs someone allowed to write it.
- 2026-11-17 — **The review round** (one design review, one adversarial review of the roadmap; each finding checked in code before it was taken). Taken:
  - Several versions on one machine: D7's second half, the record kept where older code reads no seat, and T1's two releases. Before, D7 covered other machines only.
  - `fill` is a third way a thread changes session id: continuation and refill are told apart, and the verbs that start a process are held to the wake.
  - A thread's mode and model are observed and recorded from T1 on, and a thread whose mode was never observed is not woken. Before, T2 was to write them, which left every thread stopped before T2 without them.
  - devcloud is the authority for who owns a VM and sminos asks it. Before, the thread's record held a copy that nothing kept true; this also covers a VM made before this work, which the three-day rule would otherwise have ended the owner of. `devcloud vm owner` is named as new.
  - A thread is named from another machine through its published id and its former session ids. Before, X2 assumed the name was read on the thread's own machine; a VM's notice is sent from the VM.
  - A thread on a retired machine counts as ended; the three-day end is an event of the thread's machine.
  - A membership statement carries the whole set and the request it answers; refusals are statements; requests are applied in the order they reach the thread's machine.
  - A message is in a channel when it names the channel, by `--in` or a qualified tag, and the reply line names it. Before, acceptance asked for a reply that landed in the channel with nothing naming it.
  - A machine's notice keeps today's writer and gains a marker. Before, it was to go under a new writer, which MAWS would have read as a session.
  - The wake tells an E3 copy from an E2 copy, guarantees the mode on every wake and the model on the first, and publishes a wake that came up wrong. The protected-folder exclusion is for threads their human opened; a spawned thread is resumed there as today.
  - The lead is confirmed at a terminal. Before, it borrowed the rule for widening reach, which on a machine cut over to MAWS refuses a terminal too.
  - `channel show` counts live and stopped threads per machine and drops the load average, which nothing publishes (reported to the owner as a reduction).
  - Acceptance was added for the lead, `channel env`, aliases across channels, the `join` refusal and the returned thread's memberships; names shared by a project and a channel got a rule; `channel create` is refused where the endpoint lacks the capability.
  Not taken: nothing was dismissed. Left for the children, by name, in Delegated unknowns: how `--on new` derives its VM's settings, and reach in a channel's log.

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check: verify Parent-Level Acceptance as written — all children landed is not the same event — then retrospect.
