# Arkho, re-chartered: the project's place on the web

Status: design draft from brainstorming, 2026-10-15. Not yet approved.
Born in doperpowers (worktree `smns-erb`) and moved to the arkho repository
at materialization, as the 2026-08-04 Arkho roadmap was.

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
its worktree one tab over. "+ Session" asks for a machine, a checkout, a
worktree, a brief; seconds later the new session is in the sidebar, an
ordinary `claude --bg` job that you could also attach to from that
machine's terminal.

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

## 2. What changes in Arkho

The 2026-08-04 roadmap made the board the human↔agent surface and recorded
"the human does not steer live sessions" (its parent's Decision Log); the web
UI (A3) and the terminal gateway (A6, deliberately late) were never
dispatched. Practice since has gone the other way: sminos seats, MAWS, and
`.smns` exist because the owner steers live sessions every day. The
re-charter reverses that decision and replaces A3 and A6 with this design.
The board service (A1, live on Render) stays the board's backend and
returns as one view of the project in phase 2. Contract X2 (one identity
issuer) is revisited when the board view lands: in phase 1 the hub and the
board authenticate separately.

## 3. Architecture

```
browser ──wss── Cloudflare Worker (web app, auth) ── Durable Object per project
                                                       │  (log, presence, routing)
                                    wss, outbound only │
            machine A: sminos daemon ── unix socket ── bridge mod in each session
            machine B: sminos daemon ── unix socket ── bridge mod in each session
```

- **Hub** (Cloudflare). A Worker serves the web app, authenticates, and
  routes WebSockets. One Durable Object per project stores the project log,
  knows which machines are connected and which sessions live where, routes
  commands and session subscriptions to the right machine, and fans events
  out to browsers. A registry (one Durable Object or D1) holds the org, its
  members and roles, its machines, and its projects.
- **Daemon uplink** (`sminos daemon`, one per machine, extended). One
  outbound WebSocket to the hub, multiplexing the machine's projects. It
  syncs each project's log with the hub, executes typed commands, and serves
  session subscriptions. The daemon is the machine's only connection to the
  hub.
- **Bridge** (a doperpowers mod, loaded into every session under function
  hooks). It streams the session's live events to the daemon over a Unix
  socket and performs the controls the daemon relays: submit a prompt as the
  human, steer, interrupt, answer a question, decide a permission, switch the
  model, compact. Every primitive it uses is in the 2.1.300 mod API
  (`turn.step` chunks for main loop and subagents, `$.prompt.submit` with
  `asUser`, `$.session.append`, `$.turn.abort`, `classic.PermissionRequest`
  racing the dialog, a `tool.call` result for AskUserQuestion,
  `$.config.set` for the model, `session.receive` to consume its own inbox
  frames, `$.http.fetch` over a `socketPath`).
- **Web client** (React), its skeleton ported from MAWS's renderer
  (transcript and its presentation model, request card, composer, attention,
  subagents panel, diff review).

A session without the bridge (function hooks off, another harness) degrades
to what the daemon can do alone: the transcript tailed from disk, delivery
as a cross-session frame, retire by signal.

## 4. Two planes

**The log plane** is durable and replicated: the `.smns` log, with the hub as
a mirror. It carries everything that crosses between sessions and humans,
and it is what the group chat and the direct channels are drawn from.

- Sync between a daemon and the hub is a version-vector handshake: each side
  sends `{writer: max seq}` per project, the other streams the missing
  suffix of each writer in seq order, inserts are idempotent on
  `(writer, seq)`, and the connection then tails live. The project's
  Durable Object stamps every arriving event with a project offset;
  browsers resume after an offset and never see writer vectors.
- A human on the web writes through the hub into their own feed (writer
  `hub/<member-id>`, sequenced by the Durable Object, its single writer).
  `from` is the member's display name; the machine-local operator stays
  `<machine>/human`.
- New kinds: `permission` (a session's pending permission request: tool, a
  summary of the input, `src` the tool-use id), `decided` (its resolution,
  with who answered and where, the local terminal included), and `command`
  (a human's instruction to a machine: spawn, retire, interrupt, answer,
  decide, set model; executed once by the named machine's daemon, which
  records the effect and a `done` or `failed` naming the command's id).
  Sending to a session needs no new kind: it is the existing `human` event,
  delivered through the bridge as the human's own words.
- The bridge exports `<message>` spans, async questions, and permission
  requests as they happen. The Stop hook's `sminos record` stays as the
  fallback for sessions without the bridge; the `(kind, src)` idempotency
  already de-duplicates the two.
- A command written while its machine is offline waits in the log and runs
  when the daemon reconnects; the log is its audit trail.
- A project that names a hub syncs only through the hub; the hub exports
  the log to the project's git remote on a schedule, as an archive and for
  bootstrapping a new machine. Two live transports writing the same writer
  files would bring back the conflicts one file per writer removed. A
  project without a hub keeps the git mirror as `.smns` built it (owner,
  2026-10-15).

**The session plane** is live, served on demand, and not replicated: a
session's transcript rows, its subagent tree and their transcripts, the
streaming chunks, its status and what it waits for, context use, and the
diff of its working tree. When a browser opens a session, the hub asks that
session's machine; the daemon answers from the transcript files (flushed
every 100 ms), `subagents/*.meta.json`, `sessions/<pid>.json`, and the
bridge's stream, and relays through the hub. The hub keeps at most a
reconnect buffer in memory. A machine that is offline shows its sessions'
depth as unavailable; everything they sent the human is still in the log.

## 5. The web, phase 1

- **Projects.** The home is the grid of the org's projects.
- **A project.** Left: `# <project>`, then the sessions as direct channels,
  grouped by waiting on you / working / idle / ended, each with its machine
  and its in-charge line; "+ Session". Center: the selected channel. Right:
  the selected session's depth (transcript, subagents, diff, session info).
- **The group chat** shows what is addressed to the human: messages,
  questions (answerable in place), permission prompts (decidable in place),
  lifecycle as system lines, and what humans posted. Traffic between agents
  folds into one row per run. Posting follows `sminos say`: untagged is a
  record that wakes no one, `@alias` delivers, `@all` wakes every live
  member.
- **A direct channel** is one session's exchange with the human: its
  messages, questions, and permission prompts, and what the human sent it,
  with the working record between them folded, as the to-human mod draws a
  session in the terminal. Unfolding opens the live transcript. Its composer
  sends as the human's own words; beside it, interrupt, steer now, model,
  compact.
- **Notifications.** A browser notification when a question, permission
  prompt, or message arrives while the tab is hidden.

## 6. Control

| From the web | Path |
| --- | --- |
| Send to a session | `human` event → its daemon delivers → bridge `$.prompt.submit({asUser: true})` (queued until idle); without the bridge, an inbox frame |
| Steer now | `command interrupt` then the send |
| Interrupt | `command interrupt` → bridge `$.turn.abort` |
| Answer a question | `command answer` → bridge `tool.call` result (native), or the ask mod's external-answer path (async) |
| Allow / deny | `command decide` → bridge `classic.PermissionRequest`, racing the terminal's dialog; first answer wins and both are recorded |
| Model | `command model` → bridge `$.config.set` |
| Spawn | `command spawn` → daemon runs `sminos spawn` (`claude --bg`) |
| Retire | `command retire` → `sminos retire` |

Not in phase 1, because the mod API cannot do them reliably: switching a
live session's permission mode, interrupting one subagent, rewind and fork.

## 7. Security, phase 1

- Humans sign in through Cloudflare Access in front of the Worker; the
  registry holds one org with the owner as its admin.
- A machine enrolls with a one-time code issued on the web and keeps its
  credential under `$SMINOS_HOME/daemon/` (mode 0600). It connects outbound
  only; the hub never connects into a machine.
- The daemon is the execution boundary. It accepts only the typed commands
  above. It spawns only into checkouts of the project already known on that
  machine (the working directories its members joined from), with a
  permission mode no looser than the machine's ceiling, and passes no
  arbitrary flags, environment, or shell. A machine's owner can set it
  read-only.
- The bridge socket lives in an owner-only directory, and every frame
  carries a per-session secret, since a frame's plugin tag is only what its
  sender claims.
- No redaction layer, as `.smns` ruled. Transcripts pass through the hub
  and are not stored there.
- Deferred to the org phase: commands signed by the member and verified by
  the daemon against an admin-signed member list, so that a compromised hub
  can read but not execute; a passkey step-up for spawn and approvals.

## 8. Phases

1. **The desk** (this design): hub, uplink, bridge, web; one owner, every
   machine. Done when a working day across two Macs needs no terminal.
2. **The repository**: source control (worktrees, branches, commits, diffs),
   pull requests, the board view over the Arkho board service, and a web
   terminal in a session's working directory for break-glass, opened behind
   a step-up check (owner, 2026-10-15; until then, SSH and `claude attach`).
3. **The org**: invitations, roles (viewer, member, operator, admin),
   signed commands, presence, direct-channel privacy, and a review of what
   operating one member's subscription-backed sessions by several people
   means under Anthropic's terms.
4. Beyond: convergence with MAWS's artifacts (documents, design systems)
   and the product for teachers; the chief-of-staff agent; mobile.

Phase 1 decomposes into children after the spec is written: the bridge, the
uplink, the hub, the web shell with the group chat, session depth, spawn
and retire.

## 9. Delegated unknowns

1. **The bridge, live.** Each primitive is in the API declarations and
   passed `claude plugin validate`; the combination has not run. A spike
   first: in a terminal session and a `--bg` job, submit as the user, abort,
   race a permission dialog, answer an AskUserQuestion, consume a bridge
   frame from the inbox, and measure `turn.step` throughput.
2. **The daemon's WebSocket.** The daemon is stdlib Python; a minimal
   RFC 6455 client against a streamed HTTP alternative, decided in the
   uplink child.
3. **Durable Object throughput.** Streaming chunks from several active
   sessions through one project's object; measured, with one object per
   session for the session plane as the fallback.
4. **Access and machines.** Cloudflare Access for browser WebSockets and a
   machine credential that is not an Access identity.

## 10. Silent decisions

- The hub is TypeScript on Workers; the web app is served from the same
  Worker. Both live in the arkho repository beside `board-service/`.
- The bridge is `hooks/mods/bridge.tsx` in doperpowers; the uplink lives in
  `sminos_daemon.py`.
- MAWS's renderer components are copied into Arkho, not shared as a package,
  so neither app's pace binds the other.
- `.smns` gains a `hub` field naming the project's hub and org.
- MAWS-hosted (SDK) sessions stay outside the family, as `.smns` decided.
