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

After this unit, a browser tab per project is that place. The owner opens
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
terminal.

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

Phase 1 closes when all of the following hold on the owner's two Macs with
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
6. **The three verbs.** Steer, typed while the session runs a `sleep 60`
   Bash call, does not stop the call, and the model acts on it at its next
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
(`$.process.spawn` of `sminos bridge --session <id>`, connected to the
daemon's socket) and reads commands from its output line by line, at any
point in a turn. It streams the session's live events to the daemon with
`$.http.fetch` over the daemon's `socketPath`: `turn.step` chunks for the
main loop and every subagent (`turn.step` is the only source of subagent
token deltas anywhere in the harness; the SDK wire streams the main thread
only), tool calls and results, turn boundaries, subagent lifecycle, usage,
and pending requests. Its permission and AskUserQuestion hooks long-poll
the daemon (looped under `$.http.fetch`'s 30-second bound; a `$` call in
flight stops the hook's 10-second budget) while the terminal's own dialog
stays open; the first answer wins and the engine abandons the other. The
strongest alternative, inbox frames consumed by a `session.receive` hook,
lost: frames drain only at the next tool round, so a frame cannot answer
the permission prompt that blocks that round.

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

**Without the bridge.** The daemon knows a session has a bridge by the
bridge child's connection to its socket; a live session in the registry
with no bridge connection after a short grace takes the fallback. A `--bg`
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
- **Notifications.** A browser notification when a question, a permission
  prompt, or a message arrives while the tab is hidden.

Visual design follows MAWS's tokens and density (Codex-density chrome,
Claude-style transcript typography, light first); the Slack-like layout is
afleet's. Taste-heavy surfaces are reviewed as mockups in the web children.

### 5. Control

| From the web | Plane | Path |
| --- | --- | --- |
| Send | log | `human` event → `deliver_next` → bridge `$.prompt.submit({asUser: true})`, queued until idle |
| Steer | RPC | bridge `$.session.append` of a user row, read at the loop's next request |
| Interrupt | RPC | bridge `$.turn.abort` (the main loop's turn) |
| Answer a question | RPC | bridge: the `tool.call` hook's result for a native AskUserQuestion; the ask mod's external-answer path for an async one |
| Allow / deny | RPC | bridge `classic.PermissionRequest`, racing the terminal's dialog |
| Model | RPC | bridge `$.config.set({key: 'model'})` |
| Compact | RPC | bridge `$.session.compact()` between turns; during a turn it returns busy |
| Spawn | RPC | daemon runs `sminos spawn` (`claude --bg`) with brief, model, effort |
| Retire | RPC | daemon runs `sminos retire` |
| Resume an ended session | RPC | daemon runs `claude --bg --resume <session>` in the session's working directory with no other flags (a flag makes the engine start a copy, `claude_args` in `sminos.py`), after checking the session is live nowhere; it rejoins (smns §2) |

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
- **The bridge's channel** is the daemon's socket in an owner-only
  directory; commands never travel as inbox frames.
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
   merging with this (2026-10-15); the chief-of-staff agent; mobile.

Phases 2–4 are roadmap children of the Arkho parent, cut at their dispatch.

### 8. Delegated unknowns

1. **The bridge, live** (C1). Each primitive is in the 2.1.300 mod API's
   declarations, and a probe module using them passed `claude plugin
   validate`; the combination has not run in a session. Also: whether the
   terminal draws a row appended by `$.session.append` (it is stored as
   meta, "a user-side row the person does not see as typed"; if hidden, the
   bridge mirrors the steer as a `$.ui.log` line so both surfaces show the
   same conversation), and the hook order that lets a web answer settle
   above the ask mod's.
2. **The uplink's transport and concurrency** (C4): the HTTP pair against a
   WebSocket, and thread against process.
3. **Durable Object throughput** (C3): streaming chunks from several active
   sessions through one project's object; one object per session for the
   session plane is the fallback.
4. **WebAuthn PRF** (C5): support in the owner's browsers with an iCloud
   Keychain passkey; the passphrase path covers its absence.
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
  answers first; a `tool.call` hook answering a native AskUserQuestion with
  the dialog open; `$.config.set` switching the model; `$.session.compact()`
  between turns and during one; `turn.step` chunk rate with two subagents
  running; all of it in a terminal session and in a `--bg` job. Verdict per
  item: promote, promote with a change to this design, or discard with the
  fallback.
- **Edges:** blocks C2.
- **Contracts:** —
- **Design inheritance:** §2 Bridge, §5, §8 unknown 1.
- **Required:** required.
- **Status:** in-flight (2026-10-15).

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
    compact` act as §5 says, compact answering busy during a turn; `sminos
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
  `hooks/mods/register.tsx` before `registerAsk` so its hooks settle above
  the ask mod's; the order is pinned by a test, not left to accident.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C1).

### C3: The hub — plan

- **Purpose:** The cloud side: the Worker, the project Durable Objects, the
  registry, Access for humans and service tokens for machines, enrollment
  and machine names, log storage with sync, the session-plane relay, RPC
  routing, the pending set, the audit record, and a fake machine for the
  web children.
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
    not the web's attempt.
  - **G4 (deployed):** deployed to the owner's Cloudflare account behind
    Access; enrollment issues a service token and claims a machine name,
    refusing a name already enrolled; the designated archive machine is
    recorded per project; the fake machine works against the deployment.
  - **G5 (fake machine):** a tool that replays a recorded session
    (transcript JSONL, presence, pending requests and their settlements,
    two subagents) through X2 under the X4 subscription semantics, with the
    org key, so C5 and C6 develop and test against the real protocol
    without a Mac.
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
    under another machine's writer; a hub-less project's git mirror behaves
    as before (the existing sminos suite passes).
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
    lines, an ended session's channel with Resume); composer verbs and
    request cards issue authenticated X1 events and X6 RPCs, request cards
    carry the digest of what they drew, and results render; an event or a
    request whose code fails is not drawn.
  - **G3 (the key):** the org key derives from a passkey through PRF in the
    owner's browsers, or from a passphrase; the enrollment code it produces
    enrolls a machine through C4.
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
  `subagents/*.meta.json`; the diff renders; a reconnect mid-response and a
  hub restart each end in a fresh snapshot with no gap and no duplicate.
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
    verified by a reconnect mid-response and a Worker restart overlapping
    transcript flushes, each including a subagent stream; pending requests
    and their settlements reach the hub with codes and are republished on
    reconnect.
  - **G2 (RPCs):** each RPC of §5 executes through C2's protocol; an RPC
    without a valid code, older than 60 seconds, or with a seen nonce is
    refused and the refusal reported; an answer or decision whose digest
    differs from the pending request is refused.
  - **G3 (policy):** a spawn outside the known checkouts or above the
    ceiling is refused; on a read-only machine every RPC is refused, and a
    `human` or `say` from outside the machine, addressed to a live session
    and to a stopped seat, starts nothing and settles undelivered with the
    reason shown.
  - **G4 (resume):** Resume brings an ended terminal session back on its
    machine as a `--bg` job with the same session id, which rejoins; it is
    refused while the session is live anywhere and on a read-only machine;
    two Resumes at once start one session.
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
    For a machine's writers the code covers the canonical JSON (sorted
    keys, no whitespace, UTF-8) of the whole event except `mac`, `writer`
    and `seq` included, so an event cannot be moved to another position.
    For a `hub/` writer, whose seq the browser cannot know, it covers
    `{"created", "from", "kind", "member", "nonce", "project", "text",
    "to", "wake"}`, and daemons refuse a nonce they have seen;
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
  the pending set republished on every reconnect. Binds C4, C7.
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
    numbered `n` from 1. The snapshot is the transcript rows on disk up to
    the last flushed row, the subagent tree, presence, and the partial text
    of every message still streaming. The daemon starts buffering live
    messages before it reads the snapshot and drops buffered rows the
    snapshot already holds, by row uuid — subscribe before snapshot, as
    MAWS's hydration does (`src/renderer/src/transcript/source/hydrate.ts`).
    A row's arrival settles the partial text of its message. Any
    discontinuity — a gap in `n`, a hub restart, a dropped connection —
    makes the browser subscribe again and take a fresh snapshot; nothing is
    resumed from a hub buffer, which is an optimization only;
  - **a pending request** is `raised {request: <tool-use id>, session,
    tool, input, mac}`, followed by exactly one `settled {request, winner:
    "web" | "terminal" | "other", outcome, by, mac}`, where the bridge names
    the side whose answer the engine used. The hub removes the request on
    `settled` and writes its audit record from it; after a reconnect it
    drops any request the daemon does not republish.
  The hub interprets only presence and pending; everything else it relays.
  Binds C2 and C7 (produce), C3 (relays, implements the semantics in its
  fake machine), C5 and C6 (consume).
- **X5 — Local bridge protocol (owner C2, at C2.G1).** The bridge's event
  stream to the daemon socket, the command lines to the session-lifetime
  child, the long-poll for answers and decisions, the bridge-presence
  signal, the redelivery key for `human`, and the pending request's current
  content for the daemon's digest check. Binds C7.
- **X6 — RPCs (shapes owner C3, at C3.G1; policy owner C7).** The RPC set
  of §5, each with its arguments, result, and errors, authenticated like X1
  over `{"args", "created", "machine", "member", "nonce", "project",
  "rpc"}`; an answer or decision carries in `args` the digest
  `{session, request, tool, input_sha256}` of the request as drawn. The
  policy C7 enforces: known checkouts, permission ceiling, read-only (RPCs
  and outside-origin delivery), 60-second freshness, nonce memory, digest
  match. Binds C5 (issues), C3 (routes), C7 (verifies and executes).
- **X7 — Identity (owner C3, at C3.G1).** The registry's org, member,
  machine, and project records; machine names unique in the org; the
  project's designated archive machine; Access for members, service tokens
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
        ├──G1──► C5 web: conversation ──G1──► C6 web: depth ────────────┤    (acceptance 1–11)
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
(§3: Resume is the explicit act instead).

**Explicitly out of scope (standing exclusions):** the hub storing
transcripts (§3); hosting sessions on the SDK wire (§2); depending on
Remote Control (Purpose); RPCs queued for a machine that is offline (§3);
a hub that connects into machines (§2).

## Tracking Map

| child | artifact | status |
| --- | --- | --- |
| C1 bridge spike | findings: `docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md` | in-flight (dispatched 2026-10-15 at 8257d780) |
| C2 bridge | — | not-dispatched |
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
  1–11) plus an xhigh panel per repository over the children's merged
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

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check:
verify Parent-Level Acceptance as written — all children landed is not the
same event — then retrospect.
