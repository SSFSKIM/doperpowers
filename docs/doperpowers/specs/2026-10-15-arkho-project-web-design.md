# Arkho, re-chartered: the project's place on the web

Status: design draft from brainstorming, 2026-10-15; revised after one
critique round. Not yet approved. Born in doperpowers (worktree `smns-erb`)
and moved to the arkho repository at materialization, as the 2026-08-04
Arkho roadmap was.

## 1. Purpose

**Higher purpose.** The owner runs software projects as the host of a swarm:
several long-lived Claude Code sessions per project, each in charge of one
part, on more than one machine, with the human deciding, answering, and
directing. `.smns` (doperpowers 7.153.0) made the project the unit: one
identity, one append-only log of everything that crosses sessions, a family
with no join step, a daemon per machine. What is still missing is the place
where the human works with that project.

**What it is for.** The first release replaces the terminal tabs and SSH the
owner uses today to work with sessions across Macs. At the desk, a browser
tab per project is the place of work: the project's group chat, each session
in depth (live transcript, subagents, streaming, diff), answering questions
and approvals, steering, starting a session on any machine, retiring one.
One owner; the data model is an org from day one (an org of one is the
default), so collaborators and other products can follow without a rewrite.

**The scene at its best.** Open Arkho: a grid of projects, each card showing
which machines are online, how many sessions are working and how many are
waiting on you. Open MAWS: on the left `# MAWS`, then the sessions as direct
channels grouped by "waiting on you", "working", "idle", each with its
machine and what it is in charge of. In the middle the group chat streams:
`maws-fe` reports a merged migration; `maws-45` asks which column name to
keep, with the choices as buttons; a permission prompt from `cua_repl@mini`
to run `pnpm e2e` sits with Allow and Deny. You click a choice; `maws-45`
resumes within a second. Agent-to-agent traffic is one folded row, "4
messages between agents". Open `maws-45`: your exchange with it, the work
between your messages folded as its working record; unfold it and the
transcript streams token by token, its subagent tree beside it, the diff of
its worktree one tab over. You type a correction while it works and it
reads it at its next step, without losing the command it is running.
"+ Session" asks for a machine, a checkout, a worktree, a brief; seconds
later the new session is in the sidebar, an ordinary `claude --bg` job that
you could also attach to from that machine's terminal.

**What it must not be.**
- A second copy of what sessions and repositories already hold. Transcripts
  stay on the machine that ran them and are relayed on demand, never stored
  by the hub; git, PRs, and the board are read from their sources.
- A host that changes how sessions run. Sessions stay ordinary Claude Code
  sessions (terminal or `--bg`) on the unmodified engine, with every
  setting, hook, plugin, and skill exactly as in the terminal.
- A log viewer with a send box. Depth per session is the first release's
  scene.
- Dependent on Anthropic's Remote Control, which refuses a custom
  `ANTHROPIC_BASE_URL` and so cannot run behind the owner's gateway.
- An open remote-execution surface. The machine decides what it executes;
  the hub routes.
- A fifth parallel control surface. Arkho was chartered for this purpose and
  is re-chartered; MAWS stays the local deep workstation and lends its UX;
  afleet's Slack-like presentation is the taste precedent.

## 2. What changes, in Arkho and in `.smns`

The 2026-08-04 Arkho roadmap made the board the human↔agent surface and
recorded "the human does not steer live sessions" (its parent's Decision
Log); the web UI (A3) and the terminal gateway (A6, deliberately late) were
never dispatched. Practice since has gone the other way: sminos seats, MAWS,
and `.smns` exist because the owner steers live sessions every day. The
re-charter reverses that decision and replaces A3 and A6 with this design.
The board service (A1, live on Render) stays the board's backend and returns
as one view of the project in phase 2. Contract X2 (one identity issuer) is
revisited when the board view lands; in phase 1 the hub and the board
authenticate separately.

`.smns` says twice that remote control of a session's process is not part of
it (its §2 and §9). This design adds that control, as a layer beside the log
rather than inside it: the log stays what crosses sessions, and control
travels on the session plane (§4).

## 3. Architecture

```
browser ──wss── Cloudflare Worker (web app, auth) ── Durable Object per project
                                                       │  (log, presence, routing)
                         HTTPS, outbound only (SSE ↓, POST ↑)
            machine A: sminos daemon ── unix socket ── bridge in each session
            machine B: sminos daemon ── unix socket ── bridge in each session
```

- **Hub** (Cloudflare). A Worker serves the web app, authenticates, and
  routes connections. One Durable Object per project stores the project log,
  holds the project's live presence and pending requests in memory, routes
  commands and session subscriptions to the right machine, and fans events
  out to browsers. A registry (one Durable Object or D1) holds the org, its
  members and roles, its machines, and its projects.
- **Daemon uplink** (`sminos daemon`, one per machine). One outbound
  connection to the hub, multiplexing the machine's projects: it syncs each
  project's log, serves the session plane, and answers command RPCs. The
  daemon is the machine's only connection to the hub. The daemon's loop is
  serial today (`cmd_run`: git phases with 30 s bounds, delivery, derive,
  then sleep), so the uplink does not live inside it: the daemon becomes
  concurrent, and an event that arrives from the hub nudges delivery instead
  of waiting for the next tick. Whether that is a thread in the daemon or a
  process beside it is the uplink child's call.
- **Bridge** (a doperpowers mod, loaded into every session under function
  hooks). At session start it spawns a child for the session's life
  (`$.process.spawn` of `sminos bridge --session <id>`, connected to the
  daemon's socket) and reads commands from it line by line, at any point in
  a turn. It streams the session's live events to the daemon with
  `$.http.fetch` over the daemon's `socketPath`: `turn.step` chunks for the
  main loop and every subagent (the only source of subagent token deltas
  anywhere in the harness), tool calls and results, turn boundaries,
  subagent lifecycle, usage, and pending requests. Its permission and
  AskUserQuestion hooks long-poll the daemon for a web answer while the
  terminal's own dialog stays open; whichever answers first wins, and the
  engine abandons the other.
- **Web client** (React), its skeleton copied from MAWS's renderer
  (transcript and its presentation model, request card, composer, attention,
  subagents panel, diff review). MAWS's presentation model reads stream-json;
  an adapter turns transcript rows, `turn.step` chunks, and presence into the
  shape it expects.

The daemon knows a session has a bridge by the bridge child's connection to
its socket. A live session in the registry with no bridge connection after a
short grace takes the fallback path below. A session without the bridge
(function hooks off, another harness) degrades to what the daemon and the
engine can do without it. A `--bg` seat keeps a
great deal through the engine's supervisor (`control.sock`): `reply` sends
as the human (queued for the next step) and answers a pending
AskUserQuestion, and presence, spawn, and retire need no bridge. What a seat
loses is permission decisions, interrupt, model changes, and token
streaming. A terminal session without the bridge is read-only plus delivery
as a cross-session frame.

## 4. Two planes

**The log plane** is durable and replicated: the `.smns` log, with the hub as
its mirror. It carries what crosses between sessions and humans, `human`,
`say`, `message`, `question`, `answered`, and the lifecycle, and it is what
the group chat and the direct channels are drawn from.

- Sync between a daemon and the hub is a version-vector handshake: each side
  sends `{writer: max seq}` per project, the other streams the missing
  suffix of each writer in seq order, inserts are idempotent on
  `(writer, seq)`, and the connection then tails live. The project's
  Durable Object stamps every arriving event with a project offset;
  browsers resume after an offset and never see writer vectors.
- A human on the web writes through the hub into a hub-held feed (writer
  `hub/<member-id>`, sequenced by the Durable Object, its one writer). `from`
  stays `"human"`, as everywhere in `.smns`, so every member still sees one
  host; a `member` field names which of the org's people wrote it.
- Sending to a session is the existing `human` event, delivered through the
  bridge as the human's own words (`$.prompt.submit` with `asUser`), by
  `.smns`'s delivery as it stands: at least once, so the push carries the
  event's id and the bridge drops a repeat before submitting; and a `human`
  to a member that is no longer live resumes it, so a message sent from the
  web to a closed terminal session brings it back as a `--bg` job on its
  machine. That is intended: the web is where the owner works, and a
  session they address should answer.
- The bridge exports `<message>` spans and async questions as they happen.
  The Stop hook's `sminos record` stays as the fallback for sessions without
  the bridge, and the `(kind, src)` idempotency already de-duplicates the
  two.
- A project that names a hub syncs only through the hub; the hub exports
  the log to the project's git remote on a schedule, as an archive and for
  bootstrapping a new machine. Two live transports writing the same writer
  files would bring back the conflicts one file per writer removed. A
  project without a hub keeps the git mirror as `.smns` built it (owner,
  2026-10-15). The cost is that two machines on one LAN, with the internet
  down, no longer see each other's events.

**The session plane** is live, served on demand, and not replicated.
- **Depth:** a session's transcript rows, its subagent tree and their
  transcripts, the streaming chunks, context use, and the diff of its
  working tree. When a browser opens a session, the hub asks its machine;
  the daemon answers from the transcript files (flushed every 100 ms),
  `subagents/*.meta.json`, and the bridge's stream, and the hub relays it,
  keeping at most a reconnect buffer in memory.
- **Presence:** each session's `status`, `waitingFor`, and `needs`, which the
  engine itself writes to `~/.claude/sessions/<pid>.json` the moment they
  change. The sidebar's grouping and a card's "N waiting on you" read this,
  within a second. The log's `state` events, written only after two ticks of
  persistence, remain the record for a machine that is offline.
- **Pending requests:** a permission prompt or a question that is waiting.
  The bridge reports it, the project's Durable Object keeps the pending set
  in memory, and the daemon republishes it on reconnect, since the session
  is still blocked. The group chat shows pending requests in place; once
  answered they leave the pending set, and the transcript holds the outcome.
  Who decided what, and from where, is kept in the Durable Object's own
  storage as an audit record, not in the project log.
- **Commands** are RPCs over the uplink that return `done` or `failed` at
  once. An RPC to a machine that is offline fails immediately; nothing is
  queued to run later, because an interrupt, an approval, or an answer is
  only meaningful against the moment it was given. Spawn and retire record
  their effect as the `joined` and `retired` events they already write,
  with `by`.

A machine that is offline shows its sessions' depth and presence as
unavailable; everything they sent the human is still in the log.

## 5. The web, phase 1

- **Projects.** The home is the grid of the org's projects.
- **A project.** Left: `# <project>`, then the sessions as direct channels,
  grouped by waiting on you / working / idle / ended, each with its machine
  and its in-charge line; "+ Session". Center: the selected channel. Right:
  the selected session's depth (transcript, subagents, diff, session info).
- **The group chat** shows what is addressed to the human: messages,
  questions (answerable in place), permission prompts while pending
  (decidable in place), lifecycle as system lines, and what humans posted.
  Traffic between agents folds into one row per run. Posting follows
  `sminos say`: untagged is a record that wakes no one, `@alias` delivers,
  `@all` wakes every live member.
- **A direct channel** is one session's exchange with the human: its
  messages, questions, and permission prompts, and what the human sent it,
  with the working record between them folded, as the to-human mod draws a
  session in the terminal. Unfolding opens the live transcript.
- **The composer** has the terminal's three verbs. Send queues the message
  for when the session is idle; steer puts it into the running turn at the
  next model request, without stopping the tool that is running, as typing
  mid-turn does in the terminal; interrupt stops the turn. Beside it: model
  and compact.
- **Notifications.** A browser notification when a question, permission
  prompt, or message arrives while the tab is hidden.

## 6. Control

| From the web | Path |
| --- | --- |
| Send | `human` event → its daemon delivers → bridge `$.prompt.submit({asUser: true})`, queued until idle |
| Steer | RPC → bridge `$.session.append` of a user row, read at the loop's next request |
| Interrupt | RPC → bridge `$.turn.abort` |
| Answer a question | RPC → bridge: the `tool.call` hook's result for a native AskUserQuestion, the ask mod's external-answer path for an async one |
| Allow / deny | RPC → bridge `classic.PermissionRequest`, racing the terminal's dialog |
| Model, compact | RPC → bridge `$.config.set`, `$.session.compact` |
| Spawn | RPC → daemon runs `sminos spawn` (`claude --bg`) |
| Retire | RPC → `sminos retire` |

Every control goes through the bridge, for every kind of session. The
owner's sessions are mostly terminal sessions, for which the bridge is the
only path; the bridge is already required for permissions, interrupt, model,
and streaming; and one path means one behavior and one test surface. The
supervisor's `control.sock` serves bg seats only when the bridge is absent
(§3); it is internal and versioned, and depending on it for everything would
add a second internal surface beside the mod API.

Not in phase 1, because the mod API cannot do them reliably: switching a
live session's permission mode, interrupting one subagent, rewind and fork.

## 7. Security, phase 1

- Humans sign in through Cloudflare Access in front of the Worker; the
  registry holds one org with the owner as its admin.
- A machine enrolls with a one-time code issued on the web and receives an
  Access service token, kept under `$SMINOS_HOME/daemon/` (mode 0600). It
  connects outbound only; the hub never connects into a machine.
- The daemon accepts only the typed RPCs above. It spawns only into
  checkouts of the project already known on that machine (the working
  directories its members joined from), with a permission mode no looser
  than the machine's ceiling, and passes no arbitrary flags, environment, or
  shell. A machine's owner can set it read-only.
- The typed boundary is not enough on its own: a `human` message delivered
  to a session in auto mode is code execution, classifier permitting. So a
  compromised hub, a leaked token, or an Access misconfiguration would
  execute on every enrolled Mac. **[Owner question pending]** The proposal
  is that the browser signs every `human` text and every command with a key
  derived from the owner's passkey (WebAuthn PRF) or a passphrase, and every
  daemon verifies it before acting: the hub stores and routes but cannot
  forge. What remains is a compromised deployment of the web app itself,
  which could take the key from the page. The alternative is to accept the
  hole for one owner and sign in the org phase.
- The bridge's channel is the daemon's socket in an owner-only directory;
  commands never travel as inbox frames.
- No redaction layer, as `.smns` ruled. Transcripts pass through the hub
  and are not stored there.
- Deferred to the org phase: a member list signed by an admin, which daemons
  verify signatures against; a passkey step-up for spawn and approvals.

## 8. Phases

1. **The desk** (this design): hub, uplink, bridge, web; one owner, every
   machine. Done when a working day across two Macs needs no terminal.
2. **The repository**: source control (worktrees, branches, commits, diffs),
   pull requests, the board view over the Arkho board service, and a web
   terminal in a session's working directory for break-glass, opened behind
   a step-up check (owner, 2026-10-15; until then, SSH and `claude attach`).
3. **The org**: invitations, roles (viewer, member, operator, admin),
   signed member lists, presence of people, direct-channel privacy, and a
   review of what operating one member's subscription-backed sessions by
   several people means under Anthropic's terms.
4. Beyond: convergence with MAWS's artifacts (documents, design systems)
   and the product for teachers; the chief-of-staff agent; mobile.

Phase 1 decomposes into children after the spec is written: the bridge, the
uplink, the hub, the web shell with the group chat, session depth, spawn
and retire.

## 9. Delegated unknowns

1. **The bridge, live.** Each primitive is in the 2.1.300 declarations and
   passed `claude plugin validate`; the combination has not run. A spike
   first, in a terminal session and a `--bg` job: the session-lifetime
   child, submit as the user, `session.append` mid-turn, abort, the
   permission race, an AskUserQuestion answered from outside, and
   `turn.step` throughput with subagents running. Two things to settle
   there. `$.session.append` stores its row as meta, a row the person does
   not see as typed: if the terminal does not draw a steer sent from the
   web, the bridge mirrors it (a `$.ui.log` line) so that both surfaces show
   the same conversation. And a web answer wins only when the bridge's hook
   settles above the ask mod's, so `register.tsx` registers the bridge
   first, and the bridge child's interface pins that order rather than
   leaving it to accident.
2. **The uplink.** Leaning to the HTTP pair (SSE down, POST up), which a
   Durable Object holds as well as a WebSocket and which stdlib Python
   speaks without a hand-written RFC 6455 client; and how the daemon becomes
   concurrent. Decided in the uplink child.
3. **Durable Object throughput.** Streaming chunks from several active
   sessions through one project's object; measured, with one object per
   session for the session plane as the fallback.
4. **The path to watch.** The engine's channel servers (an MCP server
   declaring `claude/channel` that pushes messages into a session, which
   replies through a tool) are the engine's own shape for "an outside
   service talks to a session", gated today behind a flag and an allowlist.
   If they open, the send and answer half of the bridge becomes a small
   server with native provenance.

## 10. Silent decisions

- The hub is TypeScript on Workers; the web app is served from the same
  Worker. Both live in the arkho repository beside `board-service/`.
- The bridge is `hooks/mods/bridge.tsx` in doperpowers; the uplink lives
  with the sminos daemon.
- MAWS's renderer components are copied into Arkho, not shared as a
  package, so neither app's pace binds the other.
- `.smns` gains a `hub` field naming the project's hub and org.
- MAWS-hosted (SDK) sessions stay outside the family, as `.smns` decided.
- Separately from this design, sminos's own `send` to a live seat can move
  from the inbox frame to the supervisor's `reply`, gaining human-origin
  delivery.

## 11. Critique (2026-10-15, two rounds, converged)

A `doperpowers:critique` debate on the first draft. Adopted: commands reach
the bridge through a session-lifetime child and the permission and ask hooks
long-poll the daemon, because inbox frames drain only at the next tool round
and so cannot answer the prompt that blocks it; the composer's three verbs
(send, steer, interrupt) in place of "interrupt, then send"; pending
requests, presence, and commands on the session plane, with commands as RPCs
that are never queued for a machine that is offline, and the decision audit in
the Durable Object rather than the log; presence read from the engine's own
session records rather than the log's debounced `state`; a concurrent daemon
and an HTTP-pair uplink; the channel servers as the path to watch; one host
(`from: "human"` plus `member`); the bridge-presence rule; at-least-once
delivery with de-duplication in the bridge. Conceded by the critic: the
bridge as the one primary control path for every session kind, with the
supervisor's `control.sock` as the fallback for seats without the bridge
(provenance and timing are not visible in the scene, and the bridge is
required regardless for permissions, interrupt, model, and streaming). Put
to the owner: whether phase 1 signs web writes (§7).
