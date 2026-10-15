# Arkho — the desk: the project's place on the web (2026-10-15)

> **Parent:** the Arkho platform roadmap, `docs/specs/2026-08-04-arkho-platform-roadmap.md`
> in `SSFSKIM/arkho`, re-chartered by this document (§2); child id **A8**,
> which replaces A3 (web UI) and A6 (terminal gateway). **Level name:** Phase 1.
> **Consumes:** the `.smns` project log as built in doperpowers 7.153.0
> (`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`, cited below
> as *smns §n*); the MAWS renderer (`SSFSKIM/MAWS`, `src/renderer/`) as a UX
> source; the Arkho board service (A1) for phase 2. Children dispatch per
> their grain hint, each carrying its section as its spec; each child's
> artifact opens by citing this document (path + child id + parent pin).
> This document is doperpowers:brainstorming's approved design (2026-10-15)
> extended in place: design up top, roadmap below. It was born in
> doperpowers (worktree `smns-erb`) and moves to the arkho repository at
> materialization, as the Arkho roadmap itself did.

## Purpose

The owner runs software projects as the host of a swarm: several
long-lived Claude Code sessions per project, each in charge of one part, on
more than one machine, with the human deciding, answering, and directing.
`.smns` made the project the unit — one identity, one append-only log of
everything that crosses sessions, a family with no join step, a daemon per
machine. What is still missing is the place where the human works with
that project. Today it is a terminal tab per session per machine, and SSH.

After this unit, a browser tab per project is that place at the desk, and
the same app on the phone's home screen carries what needs the owner when
they are away from it. The owner opens
Arkho, sees every project with its machines and how many sessions are
working and waiting on them, opens one, and works there: a group chat of
everything the project's sessions said to the human, each session in depth
(its live transcript streaming token by token, its subagents, the diff of
its working tree), answering questions and permission prompts in place,
sending, steering, and interrupting as in the terminal, starting a session
on any machine and retiring one. One owner uses it; the data model is an
org from day one (an org of one), so collaborators, and later the product
for teachers that MAWS's co-work phase imagines, can follow without a
rewrite.

**To see it working.** With the daemon enrolled on two Macs and a project
whose `.smns` names the hub: open the hub's URL, sign in, open the project.
A `<message>` a session writes on one Mac appears in `# <project>` within
two seconds. Ask a session on the other Mac something that makes it call
AskUserQuestion; the question appears with its choices; click one, and the
session continues while the dialog in its terminal closes by itself.

### The scene at its best

Open MAWS: on the left `# MAWS`, then the sessions as direct channels
grouped by "waiting on you", "working", "idle", each with its machine and
what it is in charge of. The group chat streams: `maws-fe` reports a merged
migration; `maws-45` asks which column name to keep, with the choices as
buttons; a permission prompt from `cua_repl@mini` to run `pnpm e2e` sits
with Allow and Deny. You click a choice; `maws-45` resumes within a second.
Agent-to-agent traffic is one folded row, "4 messages between agents".
Open `maws-45`: your exchange with it, the work between your messages
folded as its working record; unfold it and the transcript streams, its
subagent tree beside it, the diff of its worktree one tab over. You type a
correction while it works and it reads it at its next step, without losing
the command it is running. "+ Session" asks for a machine, a checkout, a
worktree, a brief; seconds later the new session is in the sidebar, an
ordinary `claude --bg` job you could also attach to from that machine's
terminal. Later, laptop closed, the phone buzzes: `maws-45` asks something.
The notification only says so; tapping it opens the question's card in the
app, and the answer from the phone moves the session on the mini.

### What it must not be

- **A second copy of what sessions and repositories already hold.**
  Transcripts stay on the machine that ran them and are relayed on demand,
  never stored by the hub; git, PRs, and the board are read from their
  sources.
- **A host that changes how sessions run.** Sessions stay ordinary Claude
  Code sessions (terminal or `--bg`) on the unmodified engine, with every
  setting, hook, plugin, and skill exactly as in the terminal.
- **A log viewer with a send box.** Depth per session is this phase's
  scene.
- **Dependent on Anthropic's Remote Control**, which refuses a custom
  `ANTHROPIC_BASE_URL` and so cannot run behind the owner's gateway, and
  whose client endpoints are unpublished.
- **An open remote-execution surface.** The machine decides what it
  executes and verifies who asked; the hub routes.
- **A fifth parallel control surface.** Arkho was chartered for this
  purpose (2026-08-04) and is re-chartered; MAWS stays the local deep
  workstation and lends its UX; afleet's Slack-like presentation
  (2026-09-03) is the taste precedent.

## Parent-Level Acceptance

Phase 1 closes when all of the following hold on the owner's two Macs and phone, with
the hub deployed, checked by hand and recorded with evidence in Outcomes.

1. **Projects.** Signed in through Access, the grid lists every project
   whose `.smns` names the hub; each card's machines-online and
   working/waiting counts match `sminos list` run on each machine, within
   2 seconds of a change.
2. **Messages.** A `<message>` span written by a session on machine A is in
   the project's group chat within 2 seconds of the session's turn writing
   it, attributed to the session's alias and machine.
3. **Questions.** A session on machine B calls the native AskUserQuestion;
   the question and its choices appear in the group chat and in the
   session's channel; choosing one from the web makes the session continue
   with that answer, the terminal's dialog on B closes, and the transcript
   records the answer. The same for an async question from the ask mod.
4. **Permissions.** A session on machine A in `default` permission mode
   reaches a Bash call that needs approval; the prompt appears in the group
   chat with Allow and Deny; Deny from the web stops that call, the
   terminal's dialog closes, the transcript shows the denial, and the
   decision with who made it is in the hub's audit record. Answering in the
   terminal instead removes the prompt from the web within 2 seconds.
5. **Depth.** Opening a session's channel shows its live transcript with
   the model's text streaming as it is generated, a running subagent's text
   streaming in the subagent tree, and the diff of the session's working
   tree against its base branch.
6. **The three verbs.** Steer, typed while the session runs
   `python3 -c 'import time; time.sleep(60)'` (the engine blocks a long
   foreground `sleep`), does not stop the call, and the model acts on it at its next
   request; interrupt stops the running turn within 2 seconds; send to an
   idle session starts a turn whose prompt is the sent text, read by the
   model as the human's words.
7. **Spawn, retire, resume.** "+ Session" on machine B, choosing a known
   checkout and a brief, starts a `claude --bg` job that is in the sidebar
   within 10 seconds, carries the brief as its in-charge line, and can be
   attached with `claude attach` on B; retiring it from the web ends it and
   records `retired` with the owner as `by`. A terminal session the owner
   closed keeps its channel and history; a message sent to it shows as
   recorded, not delivered; Resume brings it back on its machine as a
   `--bg` job with the same session id, and it rejoins.
8. **The machine decides.** Each of these, placed at the hub without the
   org key (simulated by writing into the project's Durable Object
   directly), is refused by every daemon, and the refusal shows in the web:
   a `human` event, a `say` under another machine's writer, and an RPC. An
   Allow whose request card the hub altered (a different command shown than
   the one pending) is refused because its digest does not match. A spawn
   into a directory that is not a known checkout of the project on that
   machine is refused. On a machine set read-only, a send to a live session
   and to a stopped seat starts nothing and shows as not delivered.
9. **Offline.** With machine B's daemon stopped, B's sessions show their
   depth and presence as unavailable, everything they sent is still in the
   group chat, and an RPC to B fails at once with "machine offline".
10. **No loss across restarts.** Redeploying the Worker, restarting a
    daemon, and reloading the browser lose no log events and duplicate
    none: the counts of events per writer agree between each machine's log
    files and the hub after reconnection.
11. **The desk.** The owner works a day across the two Macs without
    opening a terminal for anything the sessions needed from them, and says
    so (a verdict, recorded in Outcomes with what still sent them to one).
12. **The phone.** With the laptop closed and the app installed to the
    phone's home screen, a question and a permission prompt raised by a
    session on the mini each push a notification to the phone; tapping one
    opens its card; answering from the phone continues the session, and
    the mini's terminal dialog closes.

## Design

Terms used throughout:

- **Hub** — the cloud service: a Cloudflare **Worker** (a serverless
  function that serves HTTP and holds connections) plus **Durable Objects**
  (Cloudflare's single-threaded stateful objects, each with its own SQLite
  storage and connection handling; one is addressed by a name, here the
  project id).
- **Access** — Cloudflare Access, the identity gate in front of the
  Worker; a **service token** is Access's credential for a non-human
  client.
- **Daemon** — `sminos daemon` (smns §8), one per machine, a launchd agent;
  its **uplink** is the part that talks to the hub.
- **Bridge** — the doperpowers mod (a function-hook module the engine loads
  into every session when `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`) that gives
  the daemon control of the session it is loaded in.
- **Log plane** / **session plane** — §4.
- **RPC** — a request from the web to one machine that returns `done` or
  `failed` at once (§4).
- **SSE** — Server-Sent Events, a one-way HTTP stream from server to
  client.

### 1. What changes, in Arkho and in `.smns`

The 2026-08-04 Arkho roadmap made the board the human↔agent surface and
recorded "the human does not steer live sessions" (its parent's Decision
Log, 2026-08-04). The web UI (A3) and the terminal gateway (A6, deliberately
late) were never dispatched; A1 (the board service) and A2 (the plugin's
board adapter) closed in August. Practice since has gone the other way:
sminos seats, MAWS, and `.smns` exist because the owner steers live
sessions every day. **[binding — owner, 2026-10-15]** The re-charter
reverses the steering decision and replaces A3 and A6 with this unit (A8).
The board service stays the board's backend and returns as a view of the
project in phase 2; A4, A5, and the A1 read surface stay on the roadmap as
the board line, unchanged; A7 (a native macOS app) stays conditional, now
next to MAWS. Contract X2 of the roadmap (one identity issuer) is revisited
when the board view lands; in phase 1 the hub and the board authenticate
separately.

`.smns` says twice that remote control of a session's process is not part
of it (smns §2, §9). This unit adds that control as a layer beside the log,
not inside it: the log stays what crosses between sessions and humans, and
control travels on the session plane.

### 2. Architecture

```
browser ──wss── Worker (web app, Access) ── Durable Object per project
                                              (log, presence, pending, routing, audit)
                       HTTPS, outbound only from each machine
     machine A: sminos daemon (uplink) ── unix socket ── bridge in each session
     machine B: sminos daemon (uplink) ── unix socket ── bridge in each session
```

**Hub.** The Worker serves the web app, admits humans through Access and
machines through service tokens, and routes connections to Durable Objects.
One Durable Object per project stores the project's log, holds its live
presence and pending requests in memory, routes RPCs and session-plane
subscriptions to the right machine, fans events out to browsers, and keeps
the audit record of decisions. A registry (one Durable Object, or D1) holds
the org, its members and roles, its machines, and its projects.

Cloudflare's limits shape the hub (Durable Objects documentation, read
2026-10-15): 1,000 requests per second per object (soft), 30 seconds of CPU
per request by default, 10 GB of storage per object, 2 MB per stored row
or string, 32 MiB per received WebSocket message; hibernation only when the
object is a WebSocket server, and on eviction "in-memory state is reset";
every deploy restarts every object and disconnects every connection. So:

- **Presence, the pending set, and delivery outcomes are kept in the
  object's storage**, not only in memory. A hibernating object can be
  evicted while its sockets stay connected; no reconnect follows, so no
  daemon republishes, and state held only in memory would be gone. The
  daemon's republish on reconnect still reconciles what storage holds.
- **Every frame is bounded at 1 MiB**; a larger payload (a big tool result
  in a transcript row, a snapshot) is split into numbered parts.
- **After a deploy** browsers and daemons reconnect with backoff, and the
  daemon republishes presence, pending requests, and unacknowledged RPC
  results (X2, X6).

**Daemon uplink.** **[binding — the hub never connects into a machine,
which is what makes the machine's own policy the execution boundary]** Each
machine's daemon holds the machine's only connection to the hub, opened
outbound and multiplexing the machine's projects: it syncs each project's
log, serves the session plane, and executes RPCs. The daemon's loop is
serial today (`cmd_run` and `tick_all` in
`skills/sminos/scripts/sminos_daemon.py`: git phases with 30-second bounds,
delivery, derivation, then sleep), so the uplink does not live inside it:
the daemon becomes concurrent, and an event that arrives from the hub
nudges delivery (`daemon/nudge` exists) instead of waiting for the next
tick. A thread in the daemon or a process beside it is C4's call. The
transport leans to an HTTP pair, SSE down and POST up, which a Durable
Object holds as well as a WebSocket and which stdlib Python speaks without
a hand-written RFC 6455 client (delegated unknown 2).

**Bridge.** At session start it spawns a child for the session's life
(`$.process.spawn` of `sminos bridge --session <id>`), which serves the
session's endpoint on `$SMINOS_HOME/bridge/<session-id>.sock` in an
owner-only directory; the mod reads commands from the child's output line
by line, at any point in a turn, and streams the session's live events to
the child with `$.http.fetch` over that `socketPath`, where local clients —
the CLI, the daemon — send commands and subscribe (C2's residue,
2026-10-15: local control then works without the daemon running, and the
daemon finds bridges by listing the directory): `turn.step` chunks for the
main loop and every subagent (`turn.step` is the only source of subagent
token deltas anywhere in the harness; the SDK wire streams the main thread
only), tool calls and results, turn boundaries, subagent lifecycle, usage,
and pending requests. **[binding — C1's findings, measured on 2.1.300]**
- **Requests from outside go through `classic.PermissionRequest`**, which
  long-polls the daemon (looped under `$.http.fetch`'s 30-second bound; a
  `$` call in flight stops the hook's 10-second budget) while the
  terminal's own dialog stays open; a web answer closes the terminal's
  dialog within a second. A native AskUserQuestion is answered the same
  way, returning `updatedInput: {questions, answers}`: answering it from a
  `tool.call` hook instead ends the turn `aborted` under the doperpowers ask
  mod, and the `PermissionRequest` path works with or without it, so the
  order of the two mods' hooks no longer matters.
- **The bridge withdraws a request the terminal answered.** The engine
  does not tell the hook when the terminal answers first: the poll would
  run on and a late web answer would be silently ignored. The bridge
  watches for the request's end itself — the session record leaving
  `waiting`, the matching `tool.call` settling, `turn.complete` — then
  stops polling and settles the request with the terminal as the winner.
- **A background subagent's prompt gets a bounded window.** For a
  background subagent the engine awaits the hooks before it draws the
  dialog (no dialog for 40 seconds of polling in C1), so the bridge waits
  at most 3 seconds there, publishes that deadline with the request, and
  after it the prompt is the terminal's alone.
- **A person-only prompt never reaches the hooks**; the web shows it as
  waiting in the terminal, from the session record.
- **A prompt the bridge submits** is drawn in the terminal as "› Prompt
  from the doperpowers plugin"; the model reads it as the human's words
  (`asUser`), and the web draws it as the human's.

The strongest alternative, inbox frames consumed by a `session.receive`
hook, lost: frames drain only at the next tool round, so a frame cannot
answer the permission prompt that blocks that round.

**Why a bridge and not an SDK host.** **[binding — owner, 2026-10-15]** A
per-machine host running sessions on the SDK stream-json wire (MAWS's engine
host) gives full control, but its sessions cannot be held by a terminal,
sessions opened in a terminal become read-only "foreign" sessions, and an
SDK-built product on subscription credentials sits near Anthropic's
February 2026 terms. The bridge keeps every session an ordinary Claude Code
session and reaches nearly the same control (§5), with more streaming than
the SDK wire gives.

**Web client.** React, its skeleton copied from MAWS's renderer (React 19,
Zustand stores, TanStack Query; the transcript and its presentation model,
the request card, the composer, the attention model, the subagents panel,
the diff review). MAWS's presentation model reads stream-json; an adapter
turns transcript rows, `turn.step` chunks, and presence into the shape it
expects. Copied, not shared as a package, so that neither app's pace binds
the other.

**Without the bridge.** A session has a bridge when its endpoint socket
answers; a live session in the registry with no answering endpoint after
a short grace takes the fallback. A `--bg`
seat keeps a great deal through the engine's supervisor (`control.sock`,
same-uid plus `~/.claude/daemon/control.key`): `reply` sends as the human,
queued for the next step, and answers a pending AskUserQuestion; presence,
spawn, and retire need no bridge. It loses permission decisions,
interrupt, model changes, and token streaming. A terminal session without
the bridge is read-only plus delivery as a cross-session frame (smns §4).

### 3. The two planes

**[binding — this split is what lets the log stay a record of facts while
control stays bound to the moment it was given]**

**The log plane** is durable and replicated: the `.smns` log (smns §3),
with the hub as its mirror. It carries what crosses between sessions and
humans: `human`, `say`, `message`, `question`, `answered`, and the
lifecycle (`joined`, `retired`, `in-charge`, `status`, `renamed`, `state`).
The group chat and the direct channels are drawn from it.

- **Sync** between a daemon and the hub is a version-vector handshake:
  each side sends `{writer: max seq}` per project, the other streams the
  missing suffix of each writer in seq order, inserts are idempotent on
  `(writer, seq)`, a gap (`seq` not one past the last) asks for a resend,
  and the connection then tails live. The project's Durable Object stamps
  every event it stores with a project **offset** (a counter in arrival
  order); browsers resume after an offset and never see writer vectors.
  This is Secure Scuttlebutt's feed replication without the gossip; it
  needs no conflict resolution because every file has one writer.
- **One writer per feed, enforced.** The git mirror's machine-name claim
  (smns §8, `check_claim` in `sminos_daemon.py`) runs inside git
  integration, which hub projects no longer use, so the hub replaces it: a
  machine enrolls under a name unique in the org (X7), its daemon writes
  only under that name, the hub accepts from a machine's connection only
  events whose writer begins with that name, and an event arriving at an
  existing `(writer, seq)` with a different payload is refused and
  reported, never silently dropped. Two installations sharing a host name
  cannot both enroll it; the second picks another name.
- **Hub projects sync only through the hub.** **[binding — owner,
  2026-10-15]** A project whose `.smns` names a hub stops using the git
  mirror as a live path; the log is archived to the project's git remote
  on a schedule, and a new machine bootstraps from the hub. Two live
  transports writing the same writer files would bring back the conflicts
  one file per writer removed. A project without a hub keeps the git
  mirror as smns §8 built it. The cost: two machines on one LAN with the
  internet down no longer see each other's events. The archive is written
  by one machine the owner designates for the project (recorded in the
  registry, X7), because a Worker cannot run git and the GitHub API would
  bind the archive to GitHub; that daemon copies the log files into an
  archive clone kept apart from the log directory and pushes, so git never
  feeds the live log. If the machine is retired, the owner designates
  another; one designated writer needs no lease.
- **Web writes.** A human on the web writes through the hub into a
  hub-held feed, writer `hub/<member-id>`, sequenced by the project's
  Durable Object (its one writer). `from` stays `"human"`, as everywhere in
  `.smns`, so every member still sees one host; `member` names which of the
  org's people wrote it. Every event the hub carries, from any writer,
  carries an authentication code (§6).
- **Sending to a session** is the existing `human` event, delivered by
  `deliver_next` (smns §4) with the bridge as its last hop
  (`$.prompt.submit({asUser: true})`). Delivery stays at least once, so the
  push carries the event's `(writer, seq)` and the bridge drops a repeat
  before submitting. A `human` addressed to a member that is no longer live
  follows smns §4 as built: a seat is resumed; a session sminos did not
  spawn, such as a terminal session the owner closed, is never resumed by
  a message (`push_member`: "it is the human's to reopen") — the message is
  recorded and the web shows it as not delivered. The session's channel
  offers Resume instead, an RPC that brings it back on its machine (§5):
  the human's explicit act of reopening.
- **Liveness of messages.** The bridge exports `<message>` spans and async
  questions as they complete, not at Stop. The Stop hook's `sminos record`
  stays as the fallback for sessions without the bridge, and the existing
  `(kind, src)` idempotency de-duplicates the two.

**The session plane** is live, served on demand, and not replicated.

- **Depth:** a session's transcript rows, its subagent tree and their
  transcripts, the streaming chunks, context use, and the diff of its
  working tree. When a browser opens a session, the hub asks its machine;
  the daemon answers from the transcript files (the engine flushes them
  every 100 ms), `subagents/*.meta.json`, and the bridge's stream, and the
  hub relays it, keeping at most a reconnect buffer in memory.
  **[binding — the hub never stores transcripts]**
- **Presence:** each session's `status` (busy, shell, idle, waiting),
  `waitingFor`, and `needs`, which the engine writes to
  `~/.claude/sessions/<pid>.json` the moment they change; the daemon
  watches those files and publishes changes at once. The sidebar's
  grouping and a card's counts read presence. The log's `state` events,
  written only after two ticks of persistence (smns §8), remain the record
  for a machine that is offline.
- **Pending requests:** a permission prompt or a question that is waiting.
  The bridge reports it, the project's Durable Object keeps the pending set
  in memory, and the daemon republishes its pending requests on reconnect,
  since the sessions are still blocked. The group chat shows a pending
  request in place; once answered it leaves the pending set and the
  transcript holds the outcome. Questions are also log events (`question`,
  `answered`, as smns §3 has them); permission prompts are not. Who decided
  what, and from where, is the Durable Object's audit record, not the log.
- **RPCs** are requests to one machine that return `done` or `failed` at
  once. **[binding — an interrupt, an approval, or an answer is only
  meaningful against the moment it was given]** An RPC to a machine that is
  offline fails immediately; nothing waits to run later. Spawn and retire
  record their effect as the `joined` and `retired` events they already
  write, with `by`.

A machine that is offline shows its sessions' depth and presence as
unavailable; everything they sent the human is still in the log.

### 4. The web, phase 1

- **Projects.** The home is the grid of the org's projects.
- **A project.** Left: `# <project>`, then the sessions as direct
  channels, grouped by waiting on you / working / idle / ended, each with
  its machine and its in-charge line; "+ Session". Center: the selected
  channel. Right: the selected session's depth (transcript, subagents,
  diff, session info: machine, cwd, worktree, model, context, cost).
- **The group chat** shows what is addressed to the human: messages,
  questions (answerable in place), permission prompts while pending
  (decidable in place), lifecycle as system lines, and what humans posted.
  Traffic between agents folds into one row per run, expandable. Posting
  follows `sminos say` (smns §4): untagged is a record that wakes no one,
  `@alias` delivers, `@all` wakes every live member.
- **A direct channel** is one session's exchange with the human — its
  messages, questions, and permission prompts, and what the human sent it —
  with the working record between them folded, as the to-human mod draws a
  session in the terminal. Unfolding opens the live transcript. An ended
  session's channel keeps its history and offers Resume. A message
  the bridge submitted as the human's words is drawn as the human's.
- **The composer** has the terminal's three verbs. **Send** queues the text
  for when the session is idle. **Steer** puts it into the running turn at
  the next model request, without stopping the tool that is running, as
  typing mid-turn does in the terminal. **Interrupt** stops the turn. Beside
  them: model and compact. The strongest alternative, "steer = interrupt
  then send", lost: it kills the running tool, which the terminal does not.
- **The phone.** **[binding — owner, 2026-10-15]** The web app is also a
  PWA (a web app installed to the home screen, with a manifest and a
  service worker). On a phone it draws the loop of seeing what needs the
  owner and answering it: the grid with its waiting counts, the group chat,
  a direct channel, and request cards answerable in place. Session depth
  (the transcript stream, the subagent tree, the diff) stays desktop-only.
- **Notifications are Web Push.** A push fires when a question or a
  permission prompt is raised, or a `<message>` arrives, and no browser of
  that member has the project open and visible. Each member device's push
  subscription is stored in the registry (X7). The Worker sends with VAPID
  (ES256) and RFC 8291 payload encryption on WebCrypto; the npm `web-push`
  package depends on Node's crypto and does not run there. **A push only
  points to a card**: the service worker draws its text without the org
  key, so a notification carries no Allow or Deny; tapping opens the app,
  which checks the code and the digest as everywhere else. Actions on the
  notification would put the org key in the service worker, a §6 decision
  not taken. iOS delivers web push only to an app installed to the home
  screen (16.4 and later).

Visual design follows MAWS's tokens and density (Codex-density chrome,
Claude-style transcript typography, light first); the Slack-like layout is
afleet's. Taste-heavy surfaces are reviewed as mockups in the web children.

### 5. Control

| From the web | Plane | Path |
| --- | --- | --- |
| Send | log | `human` event → `deliver_next` → bridge `$.prompt.submit({asUser: true})`, queued until idle |
| Steer | RPC | bridge `$.session.append` of a user row, read at the loop's next request |
| Interrupt | RPC | bridge `$.turn.abort` (the main loop's turn), then `TaskStop` through `$.tool.call` on any Bash the abort moved to the background, as Esc kills it in the terminal |
| Answer a question | RPC | bridge: `classic.PermissionRequest` returning `updatedInput: {questions, answers}` for a native AskUserQuestion; the ask mod's external-answer path for an async one |
| Allow / deny | RPC | bridge `classic.PermissionRequest`, racing the terminal's dialog |
| Model, effort | RPC | bridge rewrites `model` and `effort` on each of the session's requests in `turn.step` (this session only). `$.config.set({key: 'model'})` was rejected: it also saves the model as the user's default in `settings.json` (C1) |
| Compact | RPC | bridge `$.session.compact()`; asked during a turn, the bridge holds it and runs it at `turn.complete` (the engine refuses it mid-turn) |
| Spawn | RPC | daemon runs `sminos spawn` (`claude --bg`) with brief, model, effort |
| Retire | RPC | daemon runs `sminos retire` |
| Resume an ended session | RPC | daemon runs `claude --bg --resume <session>` in the session's working directory with no other flags (a flag makes the engine start a copy, `claude_args` in `sminos.py`), serialized per session, after checking it is live nowhere; then verifies the session the engine reports is the same id and, if the engine started a copy (the owner reopened it in a terminal meanwhile), stops the copy and fails — the postcondition `resume_session` in `sminos.py` already checks for seats; it rejoins (smns §2) |

**[binding — one path means one behavior and one test surface]** Every
control goes through the bridge, for every kind of session. The owner's
sessions are mostly terminal sessions, for which the bridge is the only
path; the bridge is required regardless for permissions, interrupt, model,
and streaming. The supervisor's `control.sock` serves `--bg` seats only
when the bridge is absent (§2). The strongest alternative, routing send and
answer for seats through `control.sock` for its human-origin provenance,
lost: the model reads `asUser` text as the human's words, the web draws it
as the human's, and it would make a second internal, versioned surface
primary beside the mod API.

Every RPC that answers or decides a pending request carries the digest of
the request as the browser drew it, and the daemon executes it only if the
digest matches the request still pending in the session (§6).

**What each kind of session can do.** **[binding — the web reads this
table to show what a session cannot do and why, instead of failing when a
button is pressed; the acceptance timings cite it]**

| | bridged (terminal or `--bg`) | `--bg` seat, no bridge | terminal, no bridge | machine offline |
| --- | --- | --- | --- | --- |
| Send | log → `deliver_next` → `$.prompt.submit`, queued until idle | `control.sock` `reply`, at the next step | cross-session frame, at the next tool round | in the log; delivered when the daemon reconnects |
| Steer | `$.session.append`, at the next model request | `reply`, at the next step | as send | fails at once |
| Interrupt | `$.turn.abort` and `TaskStop`, within 2 s | no | no | fails at once |
| Question | native: `PermissionRequest` racing the dialog; async: the ask mod's external path | native: `reply` answers it; async: none (the ask mod is itself a mod) | terminal only | shown, not answerable |
| Allow / deny | `PermissionRequest` racing the dialog; a background subagent's prompt within its 3 s window, then terminal only; a person-only prompt terminal only | terminal only | terminal only | shown, not answerable |
| Model / compact | per request / at the turn's end | no | no | fails at once |
| Messages to the human | as each span completes | at Stop (the record hook) | at Stop | already in the log |
| Presence | the session record, within 1 s | same | same | the last `state` event, with its age |
| Depth | rows (100 ms flush) and `turn.step` chunks, subagents included | rows | rows | unavailable |
| Retire | `--bg`: `claude stop`; terminal: `retired` recorded, the process stays the human's | `claude stop` | `retired` recorded, the process stays the human's | fails at once |
| Resume (ended) | Resume RPC | Resume RPC | Resume RPC | fails at once |

Spawn is a machine RPC, not a session's; it fails at once for a machine
that is offline.

Not in phase 1, because the mod API cannot do them reliably: switching a
live session's permission mode, interrupting one subagent, rewind, and
fork.

### 6. Security, phase 1

- **Humans** sign in through Access in front of the Worker. The registry
  holds one org with the owner as its admin.
- **Machines** enroll with a one-time code the browser generates and the
  owner runs as `sminos hub enroll <code>` on the machine. The code carries
  the hub's URL, a one-time token the hub exchanges for the machine's
  Access service token, the machine name to claim (§3), and the org key
  (below). The hub sees the token, never the key. Token and key live under
  `$SMINOS_HOME/daemon/` (mode 0600). The machine connects outbound only.
- **The daemon is the execution boundary.** It accepts only the RPCs of §5.
  It spawns only into checkouts of the project already known on that
  machine (the working directories its members joined from), with a
  permission mode no looser than the machine's ceiling (default: the mode
  the user's own settings give), and passes no arbitrary flags,
  environment, or shell. A machine's owner can set it **read-only**: it
  then executes no RPC and delivers nothing that came from outside it — a
  `human` or `say` written on another machine or on the hub is recorded in
  its log, settled undelivered, and shown in the web as not delivered,
  while events written on the machine itself are delivered as before.
- **Everything the hub carries that can cause execution is authenticated
  with a key the hub never holds.** **[binding — owner, 2026-10-15: web
  writes are signed; the spec review showed that signing only web writes
  still lets the hub forge peer messages, which drive delivery and resume
  just as `human` does (`_owed`, `push_event`, `push_member` in
  `sminos.py`)]**
  - *The org key* is a 256-bit secret derived in the browser from the
    owner's passkey through the WebAuthn PRF extension (HKDF over the PRF
    output with the org id), or from a passphrase where PRF is unavailable;
    any browser holding the passkey derives the same key. It reaches each
    machine only inside the enrollment code, by the owner's hand.
  - *What carries a code:* every log event on the hub, from any writer (the
    daemon adds the code when it uploads its machine's events; the browser
    when it writes a `human`); every RPC; every pending request and its
    settlement (X4). The code is HMAC-SHA256 over canonical JSON (X1, X4,
    X6). Daemons verify before importing an event into their log or acting
    on an RPC; browsers verify before drawing a log event or a request card.
    What fails is refused, reported, and kept out of the log.
  - *Approvals are bound to what was shown.* An answer or a decision RPC
    carries the digest of the request as the browser drew it (session,
    tool-use id, tool name, SHA-256 of the input), and the daemon executes
    it only if the digest matches the request still pending in the session,
    as the bridge reports it locally.
  - *Freshness.* An RPC older than 60 seconds is refused, and a daemon
    refuses a nonce it has seen; a web `human` event, which may arrive late
    after an outage, carries the nonce check only.
  - *Why a shared key and not per-member signatures:* the daemon is stdlib
    Python, which has no Ed25519, and phase 1 is one owner whose browser
    and machines are one trust domain. Accepted residual: an enrolled
    machine that is compromised can forge any writer, and it can already
    execute as the owner. The org phase moves to per-member asymmetric keys
    and an admin-signed member list.
  - *What remains:* a compromised deployment of the web app could read the
    key from the page. Session depth (transcripts, streams, diffs) is
    relayed without codes: it is display, and what the human approves is
    bound by digest.
  - *Alternatives rejected:* Access alone for one owner (the owner's
    ruling); end-to-end encryption of the log (Happy Coder's shape), because
    the hub must read `to` and `kind` to route and the org phase would need
    group key distribution.
- **The bridge's channel** is the session's endpoint socket in an
  owner-only directory; commands never travel as inbox frames.
- **No redaction layer**, as `.smns` ruled (smns §3). Transcripts pass
  through the hub and are not stored there.

### 7. Phases

1. **The desk** — this unit.
2. **The repository** — source control (worktrees, branches, commits,
   diffs), pull requests, the board view over the Arkho board service, and a
   web terminal in a session's working directory for break-glass, opened
   behind a step-up check (owner, 2026-10-15; until then SSH and
   `claude attach`).
3. **The org** — invitations, roles (viewer, member, operator, admin),
   signed member lists, people's presence, direct-channel privacy, and a
   review of what several people operating one member's subscription-backed
   sessions means under Anthropic's terms.
4. **Beyond** — convergence with MAWS's artifacts (documents, design
   systems) and the product for teachers, which the owner can picture
   merging with this (2026-10-15); the chief-of-staff agent; a native
   mobile app, wherever A7 sits (the web app is on the phone from phase
   1).

Phases 2–4 are roadmap children of the Arkho parent, cut at their dispatch.

### 8. Delegated unknowns

1. **The bridge, live** (C1) — **resolved 2026-10-15**: every primitive
   works on 2.1.300 in a terminal session and a `--bg` job; six work
   differently than v1 assumed, and §2 and §5 now say how (the findings
   file, `docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md`).
   The terminal does not draw a row appended by `$.session.append`, so the
   bridge mirrors each steer as a `$.ui.log` line and both surfaces show
   the same conversation.
2. **The uplink's transport and concurrency** (C4): the HTTP pair against a
   WebSocket, and thread against process. Against SSE: an object holding a
   machine's open stream never hibernates and is billed for the whole time
   the stream is open; acceptable for a few machines, and the trade is
   recorded with the choice.
3. **Durable Object throughput** (C3): streaming chunks from several active
   sessions through one project's object, measured (C3.G6); one object per
   session for the session plane is the fallback, taken when the
   measurement crosses the threshold C3 records.
4. **WebAuthn PRF and Access on the phone** (C5): PRF support in the
   owner's browsers with an iCloud Keychain passkey, and inside an iOS
   home-screen app, whose storage is separate from Safari's, so the key is
   derived again there; Cloudflare Access sign-in inside the standalone app
   (the identity provider's redirect leaves the app's scope, so the Access
   cookie must land in the standalone context); Access session lifetime
   against a push tapped hours later. The passphrase path covers missing
   PRF.
5. **The path to watch.** The engine's channel servers (an MCP server
   declaring `claude/channel` that pushes messages into a session, which
   replies through a tool) are the engine's own shape for "an outside
   service talks to a session"; they are gated behind a flag and an
   Anthropic allowlist today. If they open, the send-and-answer half of the
   bridge can become a small server with native provenance.

## Children

### C1: Bridge spike — spike (findings, never a merge)

- **Purpose:** Prove, in real sessions on 2.1.300, that a mod can do what
  §2 and §5 assume, before two children build on it.
- **Acceptance:** findings recorded in
  `docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md` and folded
  into this spec's Surprises & Discoveries, with evidence, for each of: a
  session-lifetime child started with `$.process.spawn` whose output lines
  reach the mod at any point in a turn (idle, mid-model-call, mid-Bash);
  `$.prompt.submit({asUser: true})` from a timer starting a turn in an idle
  session; `$.session.append` mid-turn read at the next request, and whether
  the terminal draws it; `$.turn.abort` stopping a running turn; a
  `classic.PermissionRequest` hook long-polling a local socket and
  answering while the dialog is open, and what happens when the terminal
  answers first; the same for a background subagent's prompt, whose hooks
  the engine awaits before it opens the dialog
  (`awaitAutomatedChecksBeforeDialog`, SPEC 2.1.287 ch. 18), so a long poll
  there hides the terminal's dialog, and what bound keeps it visible; that
  a prompt marked person-only never reaches the hooks (SPEC ch. 24); a
  `tool.call` hook answering a native AskUserQuestion with
  the dialog open; `$.config.set` switching the model; `$.session.compact()`
  between turns and during one; `turn.step` chunk rate with two subagents
  running; all of it in a terminal session and in a `--bg` job. Verdict per
  item: promote, promote with a change to this design, or discard with the
  fallback.
- **Edges:** blocks C2.
- **Contracts:** —
- **Design inheritance:** §2 Bridge, §5, §8 unknown 1.
- **Required:** required.
- **Status:** landed (2026-10-15; findings folded).

### C2: The bridge — plan

- **Purpose:** Every session on a machine becomes controllable by that
  machine's daemon, and the daemon sees its live events and its pending
  requests: the mod, its session-lifetime child, and the daemon's local
  endpoint, usable from the CLI before the hub exists.
- **Acceptance:**
  - **G1 (local protocol):** X5 written into Interfaces and reviewed; C7
    may start on it.
  - **G2 (local control):** on one machine, without a hub, sminos verbs
    drive a terminal session and a `--bg` job: `sminos steer`, `sminos
    interrupt`, `sminos answer`, `sminos decide`, `sminos model`, `sminos
    compact` act as §5 says, a compact asked during a turn running at its
    end, an interrupt also ending a Bash the abort backgrounded, a model
    change staying in this session (the user's `settings.json` untouched),
    a steer mirrored in the terminal; `sminos
    answer` also answers an async question from the ask mod, through an
    external-answer path added to `hooks/mods/ask.tsx`; `sminos watch
    <member>` prints the live stream (text chunks, subagents included); a
    `human` delivered by `deliver_next` to a bridged session arrives as the
    human's words, once, under redelivery; a session without the bridge
    falls back per §2.
  - **G3 (settlement):** every request the bridge reports as raised is
    followed by a settlement naming the side whose answer the engine used,
    in four cases: answered from the CLI first, answered in the terminal
    first, both at once, and the daemon reconnecting after the request was
    answered.
  - **G4 (export):** `<message>` spans and async questions reach the log as
    they complete, de-duplicated against the Stop hook's export.
- **Edges:** blocked-by: C1; blocks: C7.
- **Contracts:** X5 (owner), X4 (producer), X1 (writer of `message` and
  `question`).
- **Design inheritance:** §2 Bridge and Without the bridge [binding], §3
  sending and liveness of messages, §5 [binding], §6 bridge channel.
  Advisory: `hooks/mods/bridge.tsx` beside the other mods, registered in
  `hooks/mods/register.tsx`; C1's probe (`/tmp/c1probe`, kept as evidence)
  is a working starting point for the child, the stand-in daemon, and the
  drivers (`/tmp/c1tools`). C1's measured rates bound X5: 50–70 chunks a
  second per streaming subagent, a post to the daemon p50 1–3 ms, p95 at
  most 35 ms.
- **Required:** required.
- **Status:** in-flight (2026-10-15).

### C3: The hub — plan

- **Purpose:** The cloud side: the Worker, the project Durable Objects, the
  registry, Access for humans and service tokens for machines, enrollment
  and machine names, log storage with sync, the session-plane relay, RPC
  routing, the pending set, the audit record, Web Push sending and push
  subscriptions, and a fake machine for the web children.
- **Acceptance:**
  - **G1 (protocols):** X2, X3, the X4 envelope, the X6 shapes, and X7
    written into Interfaces and reviewed; C4 and C5 may start on them.
  - **G2 (log):** a fake machine speaking X2 syncs a project's log in and
    out across reconnects and Worker redeploys with no loss and no
    duplicates; a browser client resumes after its offset; an event under
    another machine's name is refused at that connection; an event at an
    existing `(writer, seq)` with a different payload is refused and
    reported.
  - **G3 (routing and requests):** RPCs reach the named machine's
    connection and return `done` or `failed`; an RPC to a machine without a
    connection fails at once; session subscriptions relay to the subscribing
    browsers; a settlement removes its request from the pending set, and a
    request the daemon no longer republishes after a reconnect is dropped;
    the audit record holds the side that actually won, from the settlement,
    not the web's attempt; the latest delivery outcome per event and
    recipient is kept and returned to a browser that reconnects; an RPC
    whose machine dropped after forwarding is `uncertain` until the daemon's
    republished result resolves it; presence and the pending set survive
    the object's eviction while sockets stay open; a raised question or
    permission prompt, or a `<message>`, sends one Web Push to each of the
    member's subscribed devices when no browser of theirs has the project
    visible, and none when one has.
  - **G6 (measured):** three fake machines streaming chunks every 100 ms
    into one project, with several browsers subscribed; the report gives
    chunks per second per object, the fan-out cost, and the threshold at
    which the session plane moves to one object per session.
  - **G4 (deployed):** deployed to the owner's Cloudflare account behind
    Access; enrollment issues a service token and claims a machine name,
    refusing a name already enrolled; the designated archive machine is
    recorded per project; the fake machine works against the deployment.
  - **G5 (fake machine):** a tool that replays a recorded session
    (transcript JSONL, presence, pending requests and their settlements,
    delivery outcomes, two subagents) through X2 under the X4 subscription
    semantics, with the org key, including a chunk that arrives while a
    snapshot is being built, so C5 and C6 develop and test against the real
    protocol without a Mac.
- **Edges:** blocks: C4, C5 (start at G1; acceptance needs G5), C6
  (acceptance needs G5).
- **Contracts:** X2, X3, X7, the X4 envelope, the X6 shapes (owner); X1
  (stores, never alters).
- **Design inheritance:** §2 Hub, §3 [binding parts], §6, §8 unknown 3.
- **Required:** required.
- **Status:** not-dispatched (dispatchable now).

### C4: The uplink — plan

- **Purpose:** The machine's connection to the hub and the log plane over
  it: the daemon becomes concurrent, enrolls, syncs hub projects' logs with
  authentication codes, and writes the archive.
- **Acceptance:**
  - **G1 (enroll):** `sminos hub enroll <code>` enrolls a machine under its
    claimed name and stores the token and the org key; `sminos project init
    --hub` writes the `hub` field; a second installation with the same host
    name is refused at enrollment and told how to pick another name.
  - **G2 (sync):** a hub project's log is identical (per-writer event
    counts, last seq, and payload) between two machines and the hub after
    each of: a burst of `say` on both, a daemon restart, a dropped
    connection; a fresh machine bootstraps the project from the hub; the
    daemon never fetches git for a hub project; an event without a valid
    code is refused before it enters the log, including a forged `say`
    under another machine's writer, an authentic event of one project
    replayed into another project's feed, and a `hub/` event with a field
    its code does not cover (such as `via` or `msg_id`); a hub-less
    project's git mirror behaves as before (the existing sminos suite
    passes).
  - **G3 (archive):** the designated machine writes the log to the
    project's git remote on schedule from a clone outside the log
    directory; no other machine pushes it.
  - **G4 (concurrency):** a slow git phase of a hub-less project or a
    derivation does not delay the uplink; an event arriving from the hub
    nudges delivery at once.
- **Edges:** blocked-by: C3.G1; blocks: C7.
- **Contracts:** X1 (verifier and uploader), X2 (consumer), X7 (consumer).
- **Design inheritance:** §2 Daemon uplink [binding: outbound only, sole
  connection], §3 log plane [binding parts], §6 org key, §8 unknown 2.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C3.G1).

### C5: The web — projects and the conversation — plan

- **Purpose:** The web app's shell and everything drawn from the log plane:
  sign-in, the org key, the project grid, the project view, the group chat,
  direct channels, the composer's three verbs and model and compact,
  request cards for questions and permissions, the spawn, retire, and
  resume actions, notifications.
- **Acceptance:**
  - **G1 (shell):** MAWS's renderer skeleton copied and building as a web
    app served by the Worker, with X8 written into Interfaces; the grid and
    the project view against C3's fake machine.
  - **G2 (conversation):** group chat and direct channels draw a replayed
    project's log as §4 says (folding, the addressing grammar, system
    lines, an ended session's channel with Resume, controls a session
    cannot use shown disabled with the §5 table's reason, an `uncertain`
    RPC drawn as such and retried with its nonce); composer verbs and
    request cards issue authenticated X1 events and X6 RPCs, request cards
    carry the digest of what they drew, and results render; an event or a
    request whose code fails is not drawn; a send shows its X4 delivery
    outcome per recipient, including after a reload; when the fake machine
    disconnects, its sessions' presence and depth show as unavailable while
    the conversation stays.
  - **G3 (the key):** the org key derives from a passkey through PRF in the
    owner's browsers, or from a passphrase; the enrollment code it produces
    enrolls a machine through C4.
  - **G4 (the phone):** installed to an iPhone's home screen, the app signs
    in through Access, derives the org key, and draws the grid, the group
    chat, a direct channel, and request cards in mobile layouts; a question
    raised by the fake machine pushes a notification that opens its card,
    and the answer from the phone reaches the fake machine authenticated.
- **Edges:** blocked-by: C3.G1 to start, C3.G5 for G2; blocks: C6 (at G1).
- **Contracts:** X8 (owner); X3, X4, X7 (consumer); X1, X6 (author, with
  codes).
- **Design inheritance:** §4, §5, §6 [binding], §8 unknown 4. Advisory:
  taste-heavy surfaces (the grid card, the folded agent-traffic row, the
  request cards) go to the owner as mockups before polish.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C3.G1).

### C6: The web — session depth — plan

- **Purpose:** The right-hand depth of a session: the live transcript with
  streaming through the adapter into MAWS's presentation model, the
  subagent tree with each subagent's transcript and stream, the diff of the
  working tree, session info.
- **Acceptance:** against C3's fake machine replaying a recorded session
  with two subagents: the transcript streams and settles into the same
  rows a reload shows; the subagent tree matches the session's
  `subagents/*.meta.json`; the diff renders; a reconnect mid-response, a hub
  restart, and a chunk arriving during the snapshot each end with no gap
  and no duplicated text, in the main thread and in a subagent.
- **Edges:** blocked-by: C5.G1 (X8), C3.G1 to start, C3.G5 for acceptance.
- **Contracts:** X8, X3, X4 (consumer).
- **Design inheritance:** §2 Web client (the adapter), §3 session plane, §4
  right panel.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C5.G1, C3.G1).

### C7: The machine's controls — plan

- **Purpose:** The session plane and the RPCs on the machine side: presence
  from the engine's session records, subscriptions served under the X4
  semantics, pending requests and settlements relayed with codes, the RPCs
  of §5 verified and executed through the bridge, the machine's policy, and
  Resume.
- **Acceptance:**
  - **G1 (session plane):** presence changes reach the hub within 1
    second; a subscribed session's snapshot and live stream follow X4,
    verified by a reconnect mid-response, a Worker restart overlapping
    transcript flushes, and a chunk arriving while the snapshot is being
    built, each including a subagent stream; pending requests
    and their settlements reach the hub with codes and are republished on
    reconnect.
  - **G2 (RPCs):** each RPC of §5 executes through C2's protocol; an RPC
    without a valid code, older than 60 seconds, or with a seen nonce is
    refused and the refusal reported; an answer or decision whose digest
    differs from the pending request is refused; cutting the connection
    after execution, or restarting the daemon between execution and report,
    shows `uncertain` on the hub and then resolves, the RPC executed once; a
    spawn retried with its nonce after a cut yields one session.
  - **G3 (policy):** a spawn outside the known checkouts or above the
    ceiling is refused; on a read-only machine every RPC is refused, and a
    `human` or `say` from outside the machine, addressed to a live session
    and to a stopped seat, starts nothing and settles undelivered; every
    settled delivery of an outside-origin event produces its X4 `delivery`
    outcome (delivered, recorded for a closed terminal session,
    refused-read-only), which the web shows.
  - **G4 (resume):** Resume brings an ended terminal session back on its
    machine as a `--bg` job with the same session id, which rejoins; it is
    refused while the session is live anywhere and on a read-only machine;
    two Resumes at once start one session; a Resume racing the owner
    reopening the session in a terminal ends with one session holding that
    id, any copy stopped, and the RPC failed with the reason.
- **Edges:** blocked-by: C2.G1, C4; blocks: — (integration at
  recomposition).
- **Contracts:** X6 policy (owner); X4 (producer); X5, X2 (consumer); X1,
  X6 (verifier).
- **Design inheritance:** §3 session plane [binding], §5 [binding], §6
  [binding: the daemon as boundary, codes, digests, read-only].
- **Required:** required.
- **Status:** not-dispatched (blocked-by C2.G1, C4).

## Cross-Child Contracts

The clauses below bind now. Where a contract's full shapes are delegated,
the owner writes them into Interfaces (below) at the named gate, and its
consumers start after that gate.

- **X1 — Log events (owner: this document; complete here).** smns §3's
  events, extended and nothing more:
  - web writes use writer `hub/<member-id>`, sequenced by the project's
    Durable Object;
  - a `human` event from the web carries `from: "human"` and `member:
    "<member-id>"`;
  - every event on the hub carries `mac: {"nonce": "<128-bit random,
    base64url>", "value": "<HMAC-SHA256 with the org key, base64url>"}`.
    The code covers the bytes `arkho-log-v1\n<project id>\n` followed by
    the canonical JSON (sorted keys, no whitespace, UTF-8) of **every field
    of the event except `mac`** — and, for a `hub/` writer only, except
    also `writer`, `seq`, and `ts`, which the hub assigns after the browser
    computed the code. So no field can ride along unauthenticated (the
    delivery path reads more than the text: `frame_of` and
    `compose_frame` in `sminos.py` interpolate `msg_id` and `via`), an event
    cannot be moved to another position in its feed, and an event cannot be
    transplanted into another project of the org, where its seqs and
    delivery cursors would be fresh. A web event carries `created` and the
    `mac` nonce, and daemons refuse a nonce they have seen. A daemon
    verifies against the project it is importing into; events it has
    stored keep their `mac`, and the archive carries it;
  - `.smns` gains `"hub": {"url": "<https url>", "org": "<org id>"}`;
  - no new log kinds for permission prompts or RPCs (§3).
  Binds C2 (writes `message` and `question` as today), C3 (stores, never
  alters), C4 (adds codes on upload, verifies on import), C5 (writes
  `human`, verifies before drawing).
- **X2 — Machine ↔ hub protocol (owner C3, at C3.G1).** Outbound from the
  machine; one connection per machine, admitted by its service token and
  bound to its enrolled name; per project the version-vector handshake of
  §3, then live tail both ways; RPC requests down and results up; session
  subscriptions down and X4 messages up; machine and session presence and
  the pending set republished on every reconnect, with every RPC result
  the hub has not acknowledged. Binds C4, C7.
- **X3 — Browser ↔ hub protocol (owner C3, at C3.G1).** Resume by project
  offset for the log; subscriptions for the session plane; log events,
  presence, the pending set, and X4 messages down; authenticated `human`
  events and RPCs up, with their results. Binds C5, C6.
- **X4 — Session-plane messages (envelope owner C3, at C3.G1; producers C2
  and C7; semantics complete here).** An envelope `{project, machine,
  session, kind, sub, n, body}` around the engine's own shapes, passed
  through rather than re-modelled:
  - transcript rows are the engine's JSONL rows verbatim; stream chunks are
    `turn.step`'s chunk objects verbatim plus `turnId`, `agentId`, and the
    chunk's index in its message; session presence is the `status`,
    `waitingFor`, and `needs` fields of `~/.claude/sessions/<pid>.json`
    plus whether a bridge is connected; the subagent tree is each
    `subagents/*.meta.json` verbatim; the diff is unified diff text against
    the session's base branch; machine presence is online, policy
    (read-only, ceiling), and the known checkouts per project (path,
    branch), which the spawn sheet offers;
  - **a subscription** (`sub`) delivers a snapshot, then live messages
    numbered `n` from 1. The snapshot is the latest transcript rows up to
    the last flushed row, newest first, as many as fit the frame budget
    (older rows come on request, as the reader scrolls, read from disk), the
    subagent tree, presence, and, for every
    message still streaming, its identity (`turnId`, `agentId`, and the
    ordinal of the model request within the turn), its partial text, and
    `upTo`, the index of the last chunk that text includes. The daemon
    starts buffering live messages before it reads the snapshot, takes each
    message's partial text and `upTo` together under the same lock that
    appends chunks to it, and then drops buffered rows the snapshot already
    holds (by row uuid) and buffered chunks at or below their message's
    `upTo` — subscribe before snapshot, as MAWS's hydration does
    (`src/renderer/src/transcript/source/hydrate.ts`), with the watermark
    standing in for event ids that aggregated text lacks. A row's arrival
    settles its message's partial text, and chunks for a settled message
    are ignored. Any discontinuity — a gap in `n`, a hub restart, a dropped
    connection — makes the browser subscribe again and take a fresh
    snapshot; nothing is resumed from a hub buffer, which is an
    optimization only;
  - **a pending request** is `raised {request: <tool-use id>, session,
    tool, input, mac}`, followed by exactly one `settled {request, winner:
    "web" | "terminal" | "other", outcome, by, mac}`, where the bridge names
    the side whose answer the engine used. The hub removes the request on
    `settled` and writes its audit record from it; after a reconnect it
    drops any request the daemon does not republish;
  - **a delivery outcome** is `delivery {event: {writer, seq}, session,
    outcome: "delivered" | "recorded" | "refused-read-only" | "failed",
    reason, mac}`, produced by the daemon when `deliver_next` settles an
    event for a recipient on its machine, one per event and recipient. It
    is how the web knows that a send reached the session, or was only
    recorded (a closed terminal session) or held back (a read-only
    machine). The hub keeps the latest outcome per key and returns it to a
    browser that reconnects. It is kept apart from `settled`, which is
    about a session's pending request, not a log event.
  The hub interprets presence, pending requests, and delivery outcomes;
  everything else it relays.
  Binds C2 and C7 (produce), C3 (relays, implements the semantics in its
  fake machine), C5 and C6 (consume).
- **X5 — Local bridge protocol (owner C2, at C2.G1).** The session
  endpoint's API (`$SMINOS_HOME/bridge/<session-id>.sock`): the bridge's
  event stream into it and the subscription out of it, the command lines
  the child relays to the mod, the long-poll for answers and decisions, the bridge-presence
  signal, the redelivery key for `human`, and the pending request's current
  content for the daemon's digest check. Binds C7.
- **X6 — RPCs (shapes owner C3, at C3.G1; policy owner C7).** The RPC set
  of §5, each with its arguments, result, and errors, authenticated like X1
  over `{"args", "created", "machine", "member", "nonce", "project",
  "rpc"}`; an answer or decision carries in `args` the digest
  `{session, request, tool, input_sha256}` of the request as drawn. The
  policy C7 enforces: known checkouts, permission ceiling, read-only (RPCs
  and outside-origin delivery), 60-second freshness, digest match.
  **An RPC runs at most once.** Its nonce is its id. The daemon keeps a
  durable ledger under `$SMINOS_HOME/daemon/` mapping each nonce to its
  outcome — `done` with what the RPC produced (the spawned session's id,
  the steer's row uuid) or `failed` with the reason — written before the
  result is sent and kept for a day, well past the freshness window and a
  reconnect. A nonce the ledger knows is answered from the ledger and never
  executed again, a check made before the freshness check; an unknown nonce
  older than 60 seconds is refused. The hub marks an RPC `uncertain` when
  the machine's connection drops after the RPC was forwarded and before its
  result arrived, and resolves it from the results the daemon republishes
  on reconnect (X2); a browser retry reuses the nonce. This matters for
  spawn (two sessions) and steer (the text twice); it queues nothing for an
  offline machine, because `uncertain` applies only to an RPC the machine
  already received. RPC states: `done | failed | uncertain`. Binds C5
  (issues, draws `uncertain`), C3 (routes, marks and resolves `uncertain`),
  C7 (verifies, executes, keeps the ledger).
- **X7 — Identity (owner C3, at C3.G1).** The registry's org, member,
  machine, and project records; machine names unique in the org; the
  project's designated archive machine; each member device's push
  subscription; Access for members, service tokens
  for machines; the enrollment code (hub URL, one-time token, machine name,
  org key), generated in the browser so the hub never sees the key. Binds
  C4, C5, C7. Written to outlive this unit: the org phase extends it.
- **X8 — The web shell's slots (owner C5, at C5.G1).** The slot, layout,
  session, and transcript-store interfaces the depth panel plugs into,
  copied from MAWS's `src/renderer/src/app/slots.ts` and
  `src/renderer/src/transcript/shell.tsx`. Binds C6.

## Interfaces

Filled by the contract owners at their gates: X2, X3, the X4 envelope, the
X6 shapes, and X7 by C3 at G1; X5 by C2 at G1; X8 by C5 at G1. Each lands as a subsection
here, reviewed with its gate, and a later change to one is a Decision Log
entry that flags its consumers.

## Ordering & Dependency Map

```
C1 spike ──► C2 bridge ──G1─────────────────────────┐
                                                    ▼
C3 hub ──G1──► C4 uplink ─────────────────────► C7 machine's controls ──┐
        │                                                               ├──► recomposition
        ├──G1──► C5 web: conversation ──G1──► C6 web: depth ────────────┤    (acceptance 1–12)
        └──G5 (fake machine) ──► C5.G2 and C6 acceptance ───────────────┘
```

C1 and C3 start at once. C3's G1 (the protocols) is its first deliverable
because three children wait on it; C2's G1 likewise for C7. C5 and C6 build
against C3's fake machine, so they do not wait for the machine side; the
real two-Mac integration happens at recomposition. C2, C4, and C7 change
doperpowers; C3, C5, and C6 change arkho.

## Risks & Mitigations

- **The mod API is early access** ("may change without notice"). C1 tests
  on the installed engine; measured churn 2.1.292 → 2.1.300 was additive.
  The bridge's degraded path (§2) is what remains if an API is withdrawn,
  and C2's tests pin each primitive so a release that breaks one fails
  loudly.
- **Function hooks are behind a flag.** Without
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` the bridge does nothing; the daemon
  reports bridge-less sessions in the web rather than failing silently.
- **Organization-managed installs.** `claude plugin validate` warns that
  `PermissionRequest` hooks do not run in a user-installed plugin where an
  organization manages Claude Code; on such a machine permissions and
  questions are the terminal's alone, as the §5 table's no-bridge columns
  say. Not the owner's machines; it matters for the org phase.
- **One Durable Object per project may not carry the stream** (unknown 3).
- **Porting MAWS's renderer is the largest piece of work.** C5 copies the
  skeleton, not the app; Electron-only surfaces (the in-app browser, voice,
  native menus) are not ported.
- **Anthropic converging.** Projects and Remote Control cover part of this
  for single users on first-party login; this unit's reason to exist is the
  project log shared by sessions and humans, the owner's machines behind
  their gateway, and the org model.

## Deferred / Out of Scope

**Deferred (may return):** phases 2–4 (§7); switching a live session's
permission mode, interrupting one subagent, rewind and fork; the channel
server path (§8 unknown 5); end-to-end encryption; sessions hosted by MAWS
(they stay outside the family, as `.smns` decided); sminos `send` to a live
seat moving from the inbox frame to the supervisor's `reply`, gaining
human-origin delivery (a `.smns` improvement independent of this unit);
per-member asymmetric keys, an admin-signed member list, and a passkey
step-up for spawn and approvals (the org phase, §6); authentication codes on
session depth (§6); a message reviving a closed terminal session by itself
(§3: Resume is the explicit act instead); a cross-project inbox as the
phone's landing view, listing every pending request across projects (the
grid's waiting counts and pushes that open the card carry phase 1; an inbox
needs a registry index the project objects update on raise and settle).

**Explicitly out of scope (standing exclusions):** the hub storing
transcripts (§3); hosting sessions on the SDK wire (§2); depending on
Remote Control (Purpose); RPCs queued for a machine that is offline (§3);
a hub that connects into machines (§2).

## Tracking Map

| child | artifact | status |
| --- | --- | --- |
| C1 bridge spike | findings: `docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md` | **landed 2026-10-15**: 11 items, every primitive promoted, six with a change folded into §2 and §5; probe kept at `/tmp/c1probe` |
| C2 bridge | plan: `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md` | in-flight (dispatched 2026-10-15, parent pin 8acb3958) |
| C3 hub | — | not-dispatched |
| C4 uplink | — | not-dispatched |
| C5 web: conversation | — | not-dispatched |
| C6 web: depth | — | not-dispatched |
| C7 machine's controls | — | not-dispatched |

## Surprises & Discoveries

- Observation: Remote Control cannot be the foundation on this machine.
  Evidence: 2.1.300 refuses it with "ANTHROPIC_BASE_URL is set and does not
  point at api.anthropic.com…", and the owner's settings route through a
  loopback gateway (SPEC §36.2.4; research agent, 2026-10-15).
- Observation: the engine's `--bg` supervisor's `permission-response` op is
  a no-op ("answers `{ok:true}` after the key check", SPEC 38.11.5), and
  `reply` cannot approve a permission prompt; permissions from outside need
  a hook in the session.
  Evidence: SPEC 38.11.5, 38.28.1c (critique round 1).
- Observation: `turn.step` streams subagents' token deltas; the SDK wire
  does not. Evidence: mod API declarations 2.1.300; MAWS
  `research/sdk-wire-gap.md` row 14.
- Observation: C1 (live, 2.1.300) — the engine never tells a
  `PermissionRequest` hook that the terminal answered first; a web answer
  arriving after that is silently ignored, and the hook polls on.
  Evidence: findings item 5, `daemon.log` in `/tmp/c1probe`.
- Observation: answering a native AskUserQuestion from a `tool.call` hook
  ends the turn `aborted` when the doperpowers ask mod is loaded; the same
  answer through `PermissionRequest` `updatedInput` works in every setup.
  Evidence: findings item 6.
- Observation: `$.config.set({key: 'model'})` switches the session and also
  writes the model into the user's `settings.json` as the default for
  every new session. Evidence: findings item 7 (seen in a throwaway config
  directory, `/tmp/c1cfg/settings.json`).
- Observation: `$.turn.abort` leaves a running Bash alive, moved to the
  background; `TaskStop` on its task id ends it. Evidence: findings item 4.
- Observation: a background subagent's prompt draws no dialog while its
  `PermissionRequest` hook polls (40 s observed); with a 3 s bound the
  dialog appeared at 3.3 s. Evidence: findings item 10.
- Observation: the engine blocks a long foreground `sleep` ("Blocked: sleep
  30 followed by: echo …"). Evidence: findings, notes for the builder.
- Observation: a message to a closed terminal session does not revive it
  in `.smns` as built; the v1 design said it did.
  Evidence: `push_member` in `skills/sminos/scripts/sminos.py`: "A session
  sminos did not spawn is never resumed: it is the human's to reopen, and
  reads the chat when it is back"; it returns `recorded` (spec review,
  2026-10-15).
- Observation: the daemon cannot verify Ed25519 signatures without a
  dependency: it is stdlib Python, and the standard library has no Ed25519.
  Evidence: `skills/sminos/scripts/sminos_daemon.py` imports only the
  standard library; `hashlib`/`hmac` give HMAC-SHA256 only.

## Decision Log

- Decision: Verification. This composite gets one independent review round
  on the whole document from `doperpowers:adversarial-reviewer` (the spec is
  technical-heavy) and, in the same round, a second
  `doperpowers:adversarial-reviewer` on the children and contracts for
  buildability. Each plan child names its own branch-review rung in its
  execution document, xhigh for C3, C4, C5, and C7 by their size. Recomposition
  is a scale review: the two-Mac acceptance walk (Parent-Level Acceptance
  1–12) plus an xhigh panel per repository over the children's merged
  range.
  Rationale: a coupled design across two repositories and a security
  boundary; the critique debate on the design already ran (two rounds,
  converged — see the next entry).
  Date/Author: 2026-10-15, design session.
- Decision: The design draft's critique (`doperpowers:critique`, two
  rounds) moved the following before approval: commands reach the bridge
  through a session-lifetime child, and the permission and ask hooks
  long-poll the daemon (inbox frames drain only at the next tool round);
  the three verbs replace "interrupt then send"; pending requests,
  presence, and commands move to the session plane, commands as RPCs never
  queued for an offline machine, the decision audit in the Durable Object;
  presence from the engine's session records, not the debounced `state`; a
  concurrent daemon and an HTTP-pair uplink; the channel servers as the
  path to watch; one host (`from: "human"` plus `member`); the
  bridge-presence rule; at-least-once delivery de-duplicated in the bridge.
  The critic conceded the bridge as the one primary path.
  Rationale: each change is argued where it lives in the design.
  Date/Author: 2026-10-15, design session with the critic.
- Decision: The log's git archive is written by one machine's daemon, not
  by the hub. The owner chose "hub live, git as archive" (2026-10-15); who
  performs the export was not part of the choice. (v1 said a machine
  holding the hub's archive lease; the spec review found no child delivered
  a lease, and a designated machine needs none — see the review entry.)
  Rationale: a Worker cannot run git, and committing through the GitHub API
  would tie the archive to GitHub when `.smns` remotes are any git URL.
  Date/Author: 2026-10-15, design session.
- Decision: Spec review round 1 (two `doperpowers:adversarial-reviewer`
  runs: the whole document; the children for buildability), folded:
  - **Authentication covers every actionable thing the hub carries, with
    one org key (HMAC-SHA256) instead of Ed25519 signatures on web writes
    only.** Rejected then: signing only `human` events and RPCs — a hub
    could still forge a `say`, which `_owed`/`push_event`/`push_member`
    deliver and which resumes a stopped seat; and Ed25519 — the stdlib
    daemon cannot verify it. The owner's ruling (sign web writes, so the hub
    cannot cause execution) is what this serves; the mechanism change is
    reported to the owner.
  - **Approvals carry the digest of the request as drawn**, checked by the
    daemon against the request still pending; a hub that altered the card
    can no longer turn an honest Allow into approval of another command.
  - **Read-only covers delivery**: outside-origin `human` and `say` are
    recorded and settled undelivered, not only RPCs refused.
  - **No revival by message**: v1's "a message revives a closed terminal
    session" misread smns §4 (Surprises); an explicit Resume RPC replaces it
    (C7.G4).
  - **Machine names are enforced by the hub** for hub projects, replacing
    the git integration's claim check; divergent payloads at an existing
    `(writer, seq)` are refused and reported.
  - **The archive is written by a designated machine** (above), with
    hub-only bootstrap and no git ingestion in C4's acceptance.
  - **The session plane's semantics are written here** (X4: subscribe
    before snapshot, numbered live messages, fresh snapshot on any
    discontinuity; pending requests raised then settled with the winner),
    so C6 does not wait on the machine side; C3's fake machine implements
    them.
  - **Settlement and audit have gates** (C2.G3, C3.G3), **compaction is in
    the spike and the local gate** (C1, C2.G2), **C6 waits on C5's shell**
    (X8, C5.G1), and **the fake machine gates acceptance, not start**
    (C3.G5).
  - **C4 split into C4 (the uplink and the log plane) and C7 (the machine's
    controls: session plane, RPCs, policy, Resume)**: different state
    owners (log files against live sessions) and verification strategies,
    and v1's C4 carried both.
  Rationale: each finding was reproduced against the code or the
  contracts; none was dismissed.
  Date/Author: 2026-10-15, design session.
- Decision: Spec review round 2 (the same two lenses, scoped to round 1's
  fold), folded: the authentication code now covers the project id
  (domain-separated) and every field of an event but `mac` — a hub could
  otherwise transplant an authentic feed into another project, where its
  messages are owed afresh (a reviewer ran `_owed` to show it), or add
  `via`/`msg_id` to an honest web event, which `compose_frame` writes into
  the prompt; X4 gains a per-message chunk watermark (`upTo`) so a
  snapshot's partial text and the buffered stream cannot both carry a
  chunk; X4 gains delivery outcomes so the web can say a send was
  recorded or held back rather than delivered; Resume gains
  per-session serialization and the same-id postcondition with copy
  cleanup that `resume_session` already applies to seats. Rejected then:
  a closed schema for web events (the full-field code covers it and every
  future field without a list to maintain).
  Rationale: two P1 and three P2, all reproduced; each fix is local to a
  contract and its gates.
  Date/Author: 2026-10-15, design session.
- Decision: Spec review stops at round 2. Round 2's findings were narrow,
  local to contracts, and the reviewers specified their fixes; the
  contracts' full shapes get their next adversarial read at C3.G1 and
  C2.G1, which are reviewed before any consumer starts.
  Rationale: a third round on these edits would review the reviewers'
  own wording; the gate reviews see the shapes in their final form.
  Date/Author: 2026-10-15, design session.
- Decision: Four imports from **sminos hub**
  (`MAWS/docs/doperpowers/plans/2026-10-15-sminos-hub.md`), a design for the
  same product written in parallel, whose per-machine host owned sessions
  over the SDK wire. The owner compared the two and ruled that this
  design's bridge is the base, relayed by the comparison session; the one
  scope change was confirmed with the owner directly the same day.
  (1) **The phone in phase 1** [owner]: the PWA, Web Push sent from the
  Worker, mobile layouts for the needs-you loop, a push that only points to
  a card; acceptance 12, C5.G4, C3.G3, X7, unknown 4. Rejected then: the
  phone in phase 4 as approved first; notification actions, which would
  need the org key in the service worker. (2) **One binding table of what
  each kind of session can do** (§5), filled from this spec and checked;
  the cells the comparison left open are settled there (an async question
  needs the ask mod, itself a mod; retiring a terminal session records it
  and leaves the process the human's). (3) **RPCs run at most once**: the
  nonce as id, the daemon's durable ledger answered before the freshness
  check, `uncertain` on a drop after forwarding, results republished on
  reconnect (X6, X2, C7.G2, C3.G3, C5.G2); spawn and steer were the cases
  that could double. (4) **Cloudflare's limits** stated where they bind
  (§2): presence, pending requests, and delivery outcomes persisted, since
  a hibernating object can be evicted while its sockets stay open and no
  republish follows; frames bounded at 1 MiB; reconnect with backoff after
  a deploy; SSE's cost in unknown 2; a measured throughput run (C3.G6).
  Also from the comparison: the SPEC's background-subagent exception to the
  permission race and the person-only prompt, added to C1 and to the §5
  table. Snapshots became newest-first under the frame bound (X4).
  Rationale: each import closes a gap this design had (a double spawn, a
  pending set lost to eviction) or follows the owner's scope call; none
  collides with a binding clause.
  Date/Author: 2026-10-15, design session.
- Decision: C1's verdicts folded (all 11 promoted; six with a change).
  Questions are answered through `PermissionRequest` `updatedInput`, not a
  `tool.call` result, which removes the hook-order question; the bridge
  withdraws a request the terminal answered; a background subagent's
  prompt gets a 3-second window with a published deadline; interrupt adds
  `TaskStop` for a Bash the abort backgrounded; model and effort are
  rewritten per request in `turn.step`, rejecting `$.config.set`, which
  writes the user's default; compact asked mid-turn runs at the turn's
  end; steers are mirrored as `$.ui.log` lines; acceptance 6 uses a Python
  sleep. C2 is dispatchable.
  Rationale: measured in real sessions (findings file); each change keeps
  the design's intent with the primitive that actually delivers it.
  Date/Author: 2026-10-15, design session.
- Decision: C2 residue — the bridge child serves a per-session endpoint
  (`$SMINOS_HOME/bridge/<session-id>.sock`) that the CLI and the daemon
  connect to, rather than connecting to one daemon socket. §2, §6, and X5
  revised. Rejected then: one daemon socket, which would make local control
  depend on the daemon running. Flags C7 (it discovers bridges by listing
  the directory).
  Date/Author: 2026-10-15, design session (C2's plan).

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check:
verify Parent-Level Acceptance as written — all children landed is not the
same event — then retrospect.
