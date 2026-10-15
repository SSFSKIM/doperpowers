# The desk, DC2 — the bridge: execution (2026-10-15)

> **Composite:** `docs/doperpowers/specs/2026-10-15-desk-design.md` in the
> MAWS repository (`SSFSKIM/MAWS`, branch `smns-erb`; locally
> `/Users/new/Developer/GitHub/MAWS/.claude/worktrees/smns-erb/`), child
> **DC2** (The bridge — plan). **Parent pin:** blob `7a6fae25` of that file
> at MAWS commit `269f5212` (dispatched against doperpowers blob
> `8acb3958` of the old path, now a pointer stub). The child's
> section there is its design; this document carries only the constraints
> and the milestones. Read the composite's §2 (Bridge, Without the bridge),
> §3 (sending, liveness of messages), §5 (both tables), §6 (the bridge's
> channel), DX4, DX5, and the DC1 findings
> (`docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md`) before M1.

## Progress

- [ ] M1 — The bridge's spine and the local protocol (DC2.G1)
- [ ] M2 — The control verbs and delivery (DC2.G2)
- [ ] M3 — Requests from outside and their settlement (DC2.G2, G3)
- [ ] M4 — Live export, the acceptance walk, docs, version (DC2.G4)

## Constraints that bind every milestone

- **The composite has one writer**, the session that dispatched this plan.
  The controller records this plan's decisions in its own Decision Log
  below and messages that session at M1's end with DX5 and with any
  decision that touches a contract; it does not edit the composite.
- **Isolation.** Every manual run of `sminos.py`, its daemon, or a hook uses
  a temporary `HOME` and `SMINOS_HOME` (the CLI's one-way `migrate` runs
  before every verb and once rewrote the owner's real registry). Never
  modify `~/.claude/settings.json`, `~/.claude.json`, the plugin store, or
  the real `~/.claude/sminos`; never run `daemon install` against the real
  `HOME`.
- **Live sessions** for checks run the worktree's plugin with
  `--plugin-dir` under a throwaway `CLAUDE_CONFIG_DIR` (DC1 used
  `/tmp/c1cfg`), so the installed doperpowers mods do not load twice and
  nothing the session does reaches the owner's settings; prompts tiny,
  haiku or sonnet models; every `--bg` job started is stopped
  (`claude stop <short>`), every tmux session killed. DC1's probe
  (`/tmp/c1probe`: the mod, `bridge_child.py`, the stand-in `daemon.py`)
  and drivers (`/tmp/c1tools`) are working prior art.
- **Engine.** Claude Code 2.1.300; the mod API is early access and loads
  only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. Each primitive the
  bridge depends on is pinned by a test so a release that breaks one fails
  loudly.
- **Tests.** `tests/sminos/run-sminos-tests.sh` (stub `claude`; isolates
  `HOME` and `SMINOS_HOME`) and `tests/mods/run-mods-tests.sh` stay green at
  every milestone; shell files changed pass `shellcheck -S warning`.
  `tests/issue-tracker/test-execute-dispatch.sh` and
  `test-review-dispatch.sh` (run with `SMINOS_HOME` unset under a temporary
  `HOME`) stay green where delivery code changes.
- **Not in this child:** the hub, the uplink, authentication codes, RPC
  digests and the ledger, read-only policy (DC3, DC4, DC7); the text of
  `skills/sminos/SKILL.md` (an agent-facing behavior change needs eval
  evidence; the new verbs are for the human and the daemon, documented in
  the CLI's help and CLAUDE.md).
- No `Co-Authored-By` trailer. The version moves only through
  `scripts/bump-version.sh`, in M4's commit.

## Plan of Work

### M1 — The bridge's spine and the local protocol

**At its end:** in a session started with the worktree plugin, the bridge
mod (`hooks/mods/bridge.tsx`, registered in `hooks/mods/register.tsx`)
spawns its session-lifetime child, `sminos bridge --session <id>`, at
`session.start` (and again after a module reload, which kills the child),
and streams the session's events to it: `turn.step` chunks for the main
loop and every subagent (with `turnId`, `agentId`, and the chunk's index
in its message), tool calls and results, turn boundaries, subagent
lifecycle, usage, and a heartbeat. `sminos watch <member>` prints that
stream live, subagents included, from another terminal on the machine.

**Decision — the child is the per-session endpoint.** The child serves an
HTTP API on `$SMINOS_HOME/bridge/<session-id>.sock` (directory mode 0700):
the mod posts events and long-polls for answers there (`$.http.fetch` with
`socketPath`); local clients — the CLI now, the daemon in DC7 — send
commands there, which the child writes to its stdout for the mod to read
line by line, and subscribe to the event stream there. This puts local
control in place without the daemon running, and the daemon, when it
comes, discovers bridges by listing the directory. The socket answering
is the bridge-presence signal (§2's "bridge connected"); a stale socket
file whose child is gone is removed by whoever finds it. The composite's §2
says the child connects "to the daemon's socket"; this is the same
contract with the endpoint inverted, and the controller reports it to the
composite's writer with DX5. Rejected: a single daemon socket every child
connects to, which would make the CLI verbs depend on the daemon running.

**Touches:** `hooks/mods/bridge.tsx`, `hooks/mods/register.tsx`,
`skills/sminos/scripts/sminos.py` (the `bridge` and `watch` verbs; a small
module beside it if the child grows past a few hundred lines),
`tests/mods/`, `tests/sminos/`.

**Interfaces:** produces DX5 (below, written at this milestone's end and
sent to the composite's writer before M2 starts); produces the stream
shapes DX4 names for chunks (passed through verbatim plus the three tags).

**Does not touch:** delivery (`deliver_next`, `push_member`), any control
verb, the daemon.

**Proves:** DC2.G1. Tests pin: the child receives a command line at any
point of a turn (idle, mid-model, mid-Bash, dialog open — DC1 item 1); the
child is respawned after a module reload and a stale socket is replaced;
chunk events carry `agentId` for a subagent; `sminos watch` on a session
with no bridge says so and exits non-zero.

### M2 — The control verbs and delivery

**At its end:** from another terminal on the machine, `sminos steer
<member> <text>`, `sminos interrupt <member>`, `sminos model <member>
<model> [--effort E]`, and `sminos compact <member>` act on a terminal
session and on a `--bg` job as the composite's §5 says, and a `human` sent
with `sminos send`/`say` to a bridged member arrives as the human's words.

**Decisions:**
- *Steer* appends a user row with `$.session.append` (read at the loop's
  next request; the running tool keeps going) and mirrors it as a
  `$.ui.log` line, since the terminal does not draw the appended row (DC1
  item 3).
- *Interrupt* is `$.turn.abort` on the main loop's turn, then `TaskStop`
  through `$.tool.call` on every Bash that the abort moved to the
  background in that turn — Esc's effect (DC1 item 4).
- *Model and effort* are rewritten on each of the session's requests in
  `turn.step`; the session's choice lives in the bridge and in
  `$SMINOS_HOME/bridge/<session-id>.json` so a module reload keeps it.
  `$.config.set` is never called: it writes the user's default (DC1 item 7).
- *Compact* asked during a turn is held and run at `turn.complete`; asked
  idle, it runs at once (DC1 item 9).
- *Delivery.* `push_member` sends an owed `human` or `say` to a bridged
  member through the bridge: the bridge submits it with
  `$.prompt.submit({text, asUser: true})` (queued until idle), keyed by the
  event's `(writer, seq)`, and drops a key it has already submitted, since
  delivery is at least once. A member without a bridge keeps today's path,
  except that a live `--bg` seat without a bridge receives a `human` through
  the engine supervisor's `control.sock` `reply` (human-origin; SPEC 2.1.287
  §38.11, §20.15.14a), falling back to the inbox frame if the supervisor
  refuses. The frame's text for a bridged delivery is the same text the
  inbox frame carries today, so the model reads the same addressing.

**Touches:** `hooks/mods/bridge.tsx`, `skills/sminos/scripts/sminos.py`
(new verbs; `push_member`, `send_frame`'s callers), tests.

**Interfaces:** consumes DX5 from M1; extends it with the command lines for
these verbs and the delivery key.

**Does not touch:** permission and question handling (M3), export (M4),
the daemon's tick beyond what delivery already calls.

**Proves:** the steer, interrupt, model, compact, and send parts of
DC2.G2. Tests pin: a steer during a long Bash (a Python sleep — the engine
blocks a long foreground `sleep`) does not end it and is read next; an
interrupt ends a backgrounded Bash; a model change leaves the throwaway
config's `settings.json` untouched; a compact asked mid-turn runs after
it; one `human` redelivered three times is submitted once.

### M3 — Requests from outside and their settlement

**At its end:** a permission prompt or a native AskUserQuestion raised in
a bridged session appears in `sminos watch` as `raised`, can be answered
with `sminos decide <member> <request> allow|deny` or `sminos answer
<member> <request> <answers…>`, and ends with exactly one `settled` naming
the side whose answer the engine used; an async question from the ask mod
is answerable the same way.

**Decisions:** the composite's §2 bullets under "[binding — DC1's
findings]" are this milestone's design: `classic.PermissionRequest`
long-polls the child (looped under the 30-second fetch bound) and returns
the decision, or `updatedInput: {questions, answers}` for an
AskUserQuestion; the bridge withdraws a request the terminal answered
(the session record leaving `waiting`, the matching `tool.call` settling,
`turn.complete`) and settles it with the terminal as winner; a background
subagent's request is polled for at most 3 seconds, its deadline
published in `raised`; a person-only prompt raises nothing and the
session record carries it. The ask mod (`hooks/mods/ask.tsx`) gains an
external-answer path for its async questions: the bridge hands the answer
to it, and it delivers it by its existing route (tool-result context, or
a plugin prompt when idle). `raised` carries the request's tool, its
input, and its tool-use id, which is the request id; `settled` carries
the winner, the outcome, and who answered (`cli`, `terminal`, later
`web`).

**Touches:** `hooks/mods/bridge.tsx`, `hooks/mods/ask.tsx`,
`skills/sminos/scripts/sminos.py` (`decide`, `answer`), tests
(`tests/mods/ask.test.ts` keeps passing).

**Interfaces:** extends DX5 with the long-poll, `raised`, and `settled`;
produces DX4's pending-request shapes.

**Does not touch:** digests, authentication codes, the hub's pending set
(DC7, DC3).

**Proves:** the answer and decide parts of DC2.G2, and DC2.G3: settlement
in four cases — answered from the CLI first, in the terminal first, both
at once, and the CLI answering after the terminal did (refused as already
settled). Tests pin: a background subagent's dialog appears after the
3-second window; a terminal-first answer stops the poll within 2 seconds;
an AskUserQuestion answered through `updatedInput` reaches the model with
the doperpowers ask mod loaded.

### M4 — Live export, the acceptance walk, docs, version

**At its end:** a bridged session's `<message>` spans and async questions
reach the project log as each completes, not at Stop, and the Stop hook's
export finds them already there; DC2's gates walked live in a terminal
session and a `--bg` job; docs and the version current.

**Decisions:** the bridge exports through the same writer and the same
`(kind, src)` keys `sminos record` uses (span index for `message`, the
call's tool-use id for `question`), so the Stop hook's later export
de-duplicates against it (smns §4's idempotency); the export runs from
`turn.step`'s completed text blocks with the same code-aware mark parsing
(`sminos_marks.py` — its parity fixtures with `hooks/mods/to-human.tsx`
apply).

**Touches:** `hooks/mods/bridge.tsx`, `skills/sminos/scripts/sminos.py`
(record path shared), `CLAUDE.md` (the `hooks/` row: the bridge mod; the
`skills/` row: the new verbs), `docs/doperpowers/` nothing else, the
version via `scripts/bump-version.sh`.

**Does not touch:** `skills/sminos/SKILL.md`.

**Proves:** DC2.G4, and DC2.G1–G3 again live. Concrete Steps has the walk.

## Concrete Steps

From the worktree root, `/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/smns-erb`:

    tests/sminos/run-sminos-tests.sh          # ends "all N assertions passed"
    tests/mods/run-mods-tests.sh              # every file "all checks passed"
    shellcheck -S warning <changed .sh files> # no output

The live walk (M4), under a throwaway config directory, in a tmux pane:

    export CLAUDE_CONFIG_DIR=$(mktemp -d) HOME_T=$(mktemp -d)
    # start a terminal session with the worktree plugin
    claude --plugin-dir "$PWD" --model haiku --permission-mode default
    # from a second pane, with HOME and SMINOS_HOME set to the temporary ones:
    sminos watch <member>                      # chunks stream, subagents tagged
    sminos steer <member> "also print the date"   # during a Python sleep: sleep continues, steer read next
    sminos interrupt <member>                  # turn stops; a backgrounded Bash ends
    sminos decide <member> <request> deny      # terminal dialog closes; transcript shows the denial
    sminos answer <member> <request> "B"       # AskUserQuestion continues with B
    sminos compact <member>                    # during a turn: runs at its end
    sminos model <member> sonnet               # next request on sonnet; settings.json unchanged

Repeat with a `claude --bg` job; stop it afterwards.

## Interfaces and Dependencies

DX5 is written here at M1's end and sent to the composite's writer; M2 and
M3 extend it in place, each extension sent the same way.

### DX5 — Local bridge protocol (version 1)

The session endpoint of a bridged session. **Built at M1** unless marked
**reserved (M2)** or **reserved (M3)**; reserved shapes are proposals the
milestone that builds them fixes and sends as an extension.

#### Parties

- **The mod**, `hooks/mods/bridge.tsx`, inside the session.
- **The child**, `sminos bridge --session <session-id>`
  (`skills/sminos/scripts/sminos_bridge.py`), spawned by the mod with
  `$.process.spawn` for the session's life; a direct child of the session process.
- **Local clients**: the CLI (`sminos watch` now; the control verbs at M2/M3) and the
  daemon (DC7).

#### The endpoint and presence (built)

- **Path:** `$SMINOS_HOME/bridge/<session-id>.sock`; the directory is mode 0700, the socket
  0600. The path must fit a Unix socket (at most 103 bytes; the child exits 1 otherwise).
- **Transport:** HTTP/1.1 over the socket, JSON bodies, `Connection: close` on every
  response (one request per connection).
- **Placement:** the child binds `.<first 8 of id>.<pid>.sock` in the directory, listens,
  sets 0600, and renames it onto the path; then it writes `hello` on stdout. So the path
  never names a socket that is not yet listening.
- **Presence:** a session has a bridge when `GET /status` on its path answers 200 with its
  session id. (DX4's "bridge connected".)
- **Stale rule:** a socket file whose connect fails is stale; whoever finds it removes it,
  having checked its inode is the same before the connect and before the unlink
  (`sminos_bridge.remove_stale`). A starting child replaces a stale file by its rename.
- **Discovery (DC7):** list `$SMINOS_HOME/bridge/*.sock` (skip names beginning with `.`, a
  child's temporary bind) and probe each.
- **One child per session:** a newer child takes the path over; an older one exits within
  0.5 s of finding the path's inode no longer its own, without unlinking. A child also
  exits when its parent process is gone (the session ended or was killed), on SIGTERM or
  SIGHUP, or when its stdout breaks; it unlinks the path only if the inode is still its own.
- **When the mod spawns one:** at `session.start`; again after a module reload (the reload
  kills the child and runs `session.start` again); again after a child ends on its own
  (1 s, doubling to 60 s, back to 1 s once a child lived 30 s); and under the new id when
  the session id changes (a `/clear`), noticed at the next heartbeat (≤ 5 s). Never in a
  session with `SMNS_INTERNAL` set.

#### Routes

| Route | Built | Body | Answer |
| --- | --- | --- | --- |
| `GET /status` | M1 | — | 200 `{session, pid, protocol: 1, socket, started, subscribers, mod: {events, last}}` (`last`: epoch seconds of the mod's last post) |
| `POST /events` | M1 (the mod's) | a JSON array of events, oldest first (a single object is accepted) | 204; 400 when an item is not an object with a string `type` |
| `GET /events` | M1 | — | 200 `application/x-ndjson`, close-delimited: one snapshot line, then every event, each with `n` (below) |
| `POST /command[?wait=ms]` | M1 | `{op, ...args}` | `wait` absent or 0: 202 `{id, status: "sent"}`; `wait` 1–25000: 200 `{id, ok, result?, error?}` once the mod answered, 504 `{id, error}` on time-out; 400 for no string `op` or `op: "hello"`; 503 when the child can no longer write to the mod |
| any other | — | — | 404 `{error}` |
| `GET /requests/<request>/wait?ms=` | **reserved (M3)** | — | the mod's long-poll for a decision on a pending request (held ≤ 20 s, under the 30 s fetch bound): 200 the decision, 204 nothing yet, 410 withdrawn/settled |
| `GET /requests/<request>` | **reserved (M3)** | — | the pending request's current content for DC7's digest check: `{request, session, tool, input, agentId, deadline?}`; 404 when not pending, 410 settled (with the settlement) |
| `POST /requests/<request>/decision` | **reserved (M3)** | `{behavior: "allow"\|"deny", message?, updatedInput?, by}` (an answer is `allow` with `updatedInput: {questions, answers}`) | 200 accepted (the settlement follows on the stream); 409 already settled, naming the winner |

#### The child's stdout: lines for the mod (built)

One JSON object per line, flushed:

- First, once the socket answers:
  `{"op": "hello", "session": "<id>", "pid": <child pid>, "socket": "<path>", "protocol": 1}`.
  The mod posts nothing before it, then posts the session's start first.
- Then one line per command: `{"id": "<32 hex, minted by the child>", "op": "<op>", ...args}`,
  `id` first, the client's other fields as given (a client's own `id` is replaced). The mod
  answers every command with a `result` event (below) carrying the same `id`; an op it does
  not know is answered `{ok: false, error: "unknown op: <op>"}`.

| Op | Built | Arguments | Result |
| --- | --- | --- | --- |
| `ping` | M1 | — | `{pong: true, state: {mainTurn: <turnId or null>, isStreaming: <a main-loop model request streaming>, tools: [<tool names running>]}}` |
| `steer` | **reserved (M2)** | `{text}` | `{row: <uuid of the appended user row>}` (mirrored with `$.ui.log`) |
| `interrupt` | **reserved (M2)** | — | `{turnId, stopped: [<task ids TaskStop ended>]}` |
| `model` | **reserved (M2)** | `{model, effort?}` | `{model, effort}` in force; kept in `$SMINOS_HOME/bridge/<id>.json` |
| `compact` | **reserved (M2)** | `{instructions?}` | `{queued: true}` mid-turn, else the compaction's outcome |
| `deliver` | **reserved (M2)** | `{key: {writer, seq}, text}` | `{submitted: true}` or `{duplicate: true}`; the **delivery key** is the log event's `(writer, seq)`, remembered in `<id>.json` across reloads |

#### Events (the mod's posts; the stream's lines)

Every event is an object with `type` and `t` (the mod's clock, epoch ms). `agentId` is
`null` on the main loop and the subagent's id otherwise.

| `type` / `phase` | Built | Fields |
| --- | --- | --- |
| `session` / `start` | M1 | `session, cwd, surface, isInteractive, model, version` |
| `session` / `end` | M1 | `reason` (the engine's; `clear` for a /clear) — best effort, the process exits next |
| `turn` / `start` | M1 | `turnId, agentId, text` (the prompt) |
| `turn` / `complete` | M1 | `turnId, agentId, reason` (`answer`, `aborted`, `refusal`, `error`), `usage` (the turn's, or null) |
| `step` / `start` | M1 | `turnId, agentId, step` (the request's index in the turn), `model, effort, messageCount` |
| `step` / `end` | M1 | `turnId, agentId, step, stopReason, usage` |
| `chunk` | M1 | `turnId, agentId, step, chunkIndex, chunk` — **DX4's chunk:** `chunk` is `turn.step`'s chunk object verbatim (`text`, `thinking`, `tool`, `input`, `stop`; `engine` items are not sent); the three tags are `turnId`, `agentId`, and `chunkIndex`, the chunk's index in its message from 0; a message is identified by `(turnId, agentId, step)` |
| `tool` / `call` | M1 | `toolUseId, tool, agentId, input` (the tool's own arguments), `truncated?` |
| `tool` / `result` | M1 | `toolUseId, tool, agentId, isError, denied?, text?, truncated?` |
| `agent` / `spawn` | M1 | `agentId, parentAgentId, subagentType, description, name, background, model, toolUseId` |
| `agent` / `stop` | M1 | `agentId, agentType` |
| `usage` | M1 | `context: {tokens, window, percent}, cost` — after each main turn |
| `heartbeat` | M1 | `state` (as `ping`'s) — every 5 s |
| `result` | M1 | `id, op, ok, result?, error?` — the mod's answer to a command |
| `gap` | M1 | `dropped` — events lost on the way (a failed post); resubscribe |
| `command` | M1 (the child's own) | `id, op` — a command relayed to the mod |
| `raised` | **reserved (M3)** | `request` (the tool-use id), `tool, input, agentId, deadline?` (a background subagent's 3 s bound) — DX4's pending request |
| `settled` | **reserved (M3)** | `request, winner` (DX4's: the side whose answer the engine used), `outcome, by` (`cli`, `terminal`, later `web`) — exactly one per `raised` |
| `delivered` | **reserved (M2)** | `key: {writer, seq}, outcome: "submitted" \| "duplicate"` |

String fields of a tool's input, a result's text, a denial, and a prompt are held to
65,536 characters (`truncated: true` where cut). Events reach the child in the order they
happened: the mod keeps one post in flight, batches of up to 500.

#### Subscription (`GET /events`, built)

- **Line 1, the snapshot:**
  `{"type": "snapshot", "session", "protocol": 1, "pid", "sessionInfo": {...the session start, "ended"?}, "turns": [{turnId, agentId, t}], "streaming": [{turnId, agentId, step, model?, text, thinking, upTo}], "agents": [{agentId, ...the spawn's fields, agentType?, running}], "usage": <the last usage event or null>, "pending": [], "settled": []}`.
  `streaming` holds every message still streaming: its partial text and thinking and
  `upTo`, the `chunkIndex` of the last chunk they include (-1 for none). A message leaves
  it at its step's end or its turn's end.
  **`pending` and `settled` are reserved (M3)**: the requests pending now and the ones
  settled recently, so a subscriber that arrives after a request settled sees it settled
  (the plan's G3 fourth case).
- **Then every event** as posted, with `n` added, from 1 and one past the last.
- **No gap, no duplicate:** the child applies an event to its state and hands it to every
  subscriber under one lock, and takes a snapshot and adds the subscriber under the same
  lock (subscribe before snapshot, DX4).
- **Discontinuity:** the stream ends when the child ends or the subscriber falls 10,000
  events behind; a client subscribes again and takes a fresh snapshot. Nothing is resumed.

#### `sminos watch <member> [--json]` (built)

`<member>` is a member name as the other verbs take it, or a session id. Prints the stream:
the conversation as it streams (`[main] …`, `[<type> <agentId>] …` for a subagent), one
line per turn, tool call, failed tool, subagent start and stop, and command result; with
`--json`, the lines as the endpoint sends them. Exit: 4 when the member has no bridge on
this machine (a stale socket is removed), is unknown, holds no session, or runs on another
machine; 1 when the bridge ended and none answers again within 5 s; 0 when the session
ended or on Ctrl-C. A bridge that comes back within 5 s (a module reload) is followed:
"· the bridge restarted; reconnected", and a fresh snapshot.

## Decision Log

- Decision: Verification. Each milestone gets the subagent-driven
  execution's task review at its boundary; the branch gets a `high`
  review through `doperpowers:review-code` at the end, run by the
  controller.
  Rationale: one repository, a mod and a CLI with a live-session walk;
  the security boundary is DC7's.
  Date/Author: 2026-10-15, the composite's writer at dispatch.
- Decision: The bridge child serves a per-session socket (M1).
  Rationale and the rejected alternative: M1.
  Date/Author: 2026-10-15, the composite's writer at dispatch.
- Decision: Parent re-pinned to blob `b5af3c65` (commit `b7a82a59`). The
  only change since `8acb3958` is the dispatch commit's own revision of §2,
  §6, and DX5 to the per-session endpoint this plan already assumes; no
  sibling has landed, so no interface this plan consumes moved.
  Date/Author: 2026-10-15, controller (pre-flight).
- Decision: G3's fourth case. The composite's DC2.G3 names "the daemon
  reconnecting after the request was answered"; M3's Proves names "the CLI
  answering after the terminal did". DC2 covers both: with no daemon in this
  child, the reconnecting party is any client of the session endpoint, so a
  subscription opened after a request settled shows that request settled
  (its snapshot carries the current pending set and the recent
  settlements), never as still raised; and a late answer is refused as
  already settled.
  Date/Author: 2026-10-15, controller (pre-flight).
- Decision: How "Tests pin" is met for engine behaviour. Logic is pinned in
  the suites (`tests/mods/*.test.ts` under `claude-code/testing`,
  `tests/sminos/`). A behaviour only a running engine shows (a command
  reaching the mod mid-Bash, a reload respawning the child, an abort
  backgrounding a Bash) is pinned by a scripted live check kept in the
  repo, outside the default suites because it spends model calls, run at
  its milestone and again in M4's walk, its output quoted in the report.
  Rationale: the constraint wants a release that breaks a primitive to fail
  loudly; a check nobody can re-run does not.
  Date/Author: 2026-10-15, controller (pre-flight).
- Decision: Live sessions are isolated on every axis the plugin touches.
  Besides `CLAUDE_CONFIG_DIR`, a live session started with the worktree
  plugin runs with a temporary `HOME` and `SMINOS_HOME`, because the plugin
  itself runs sminos (the bridge child, and the Stop/SessionStart
  `smns-record.sh` hook) and would otherwise reach the real registry.
  Inference goes through the owner's loopback gateway, whose env lives in
  the real `~/.claude/settings.json`, which a throwaway config dir does not
  read. DC1 carried it in the process environment, through an env file it
  sourced (`/tmp/c1cfg/settings.json` holds only a model). So: the launch
  passes exactly the keys a session needs — `ANTHROPIC_BASE_URL`,
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL`,
  `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`, and
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` — from the executor's own
  environment, or from a 0600 env file under `/tmp` outside the repo; a
  tmux session gets them with `-e` or by sourcing that file, since a tmux
  server does not inherit the client's environment. No other key from the
  owner's settings is copied (not `CLAUDE_CODE_PLUGIN_DIRS`, not a browser
  token), and no secret is ever written into the repository, a report, or a
  log quoted in one. The dispatching session's own `CLAUDECODE`,
  `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, and
  `CLAUDE_CODE_MESSAGING_*` are unset for the launched session so it is not
  taken for this session's child.
  Date/Author: 2026-10-15, controller (pre-flight; gateway env refined the
  same day at the composite writer's request).
- Decision: Ids follow the composite's rename at `573ff54b`: children
  C1–C7 are DC1–DC7 and contracts X1–X8 are DX1–DX8, because the product's
  code lands in the MAWS repository, whose charter already binds C1–C12
  and X1–X8. This plan uses the new ids throughout. Parent re-pinned to
  blob `300379dd`. The composite now frames the product as independent and
  rooted in `.smns` rather than as Arkho's child; DC2's section, scope, and
  design are unchanged.
  Date/Author: 2026-10-15, controller.
- Decision: The composite moved to MAWS
  (`docs/doperpowers/specs/2026-10-15-desk-design.md`, MAWS commit
  `269f5212`), re-pinned to its blob `7a6fae25`; the doperpowers path is a
  pointer stub. Edits since the last pin touch DX1 (canonical JSON is RFC
  8785), the hub's offset storage, and the uplink transport, none of which
  DC2 consumes; the header now says which repository each path is in. The
  DC1 findings stay in doperpowers.
  Date/Author: 2026-10-15, controller.

- Decision (M1): The child lives in `skills/sminos/scripts/sminos_bridge.py`
  with thin `bridge`/`watch` verbs in `sminos.py`; `sminos bridge` is
  dispatched before `migrate()`, as `record` is — it starts in every session,
  reads no registry, and must never take the registry's lock.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): DX4's chunk is nested, not merged: `{type: "chunk",
  turnId, agentId, step, chunkIndex, chunk}` with the engine's object
  verbatim under `chunk` (its own `index` is the content block's and would
  collide). `step`, the request's index in the turn, is added because
  DX4's snapshot names a message by `(turnId, agentId, ordinal of the
  request)`. `engine`-kind chunks are not forwarded; `chunkIndex` and `upTo`
  count the forwarded ones.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): The child, not the daemon, keeps the session's live state
  and builds DX4's snapshot (partial text with `upTo`, open turns, agents,
  usage) under the one lock that applies events and adds subscribers, so
  every local client gets subscribe-before-snapshot exactly and DC7 gets the
  snapshot for free. Events reach the child in order: one post in flight,
  batches of up to 500; lost events surface as a `gap` event.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): Endpoint placement — bind a temporary name, listen, rename
  onto the path, so the path never names a socket not yet listening and a
  refused connect there is safely stale; stale removal checks the inode
  before connect and before unlink; a newer child takes the path over and
  the older exits; a child exits when its parent session is gone. A path
  over 103 bytes fails the child with a message naming `SMINOS_HOME`.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): The bridge registers first (outermost) in `register.tsx`,
  with match-everything matchers, because the other mods hold each event's
  one unmatched registration. `$` is never stored (the validator refuses
  it); long-lived posting runs on closures made in `session.start`.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): `/clear` changes the session id with no `session.start`;
  the heartbeat (5 s) notices and restarts the child under the new id.
  Date/Author: 2026-10-15, M1 executor.
- Decision (M1): `sminos watch` exits 4 when the member has no bridge here
  (or is unknown, seatless, or on another machine), 1 when the bridge ended
  and none answers within 5 s, 0 when the session ended; it follows a bridge
  that returns within 5 s. The endpoint tests live in
  `tests/sminos/test-bridge.sh` (a short `SMINOS_HOME` under `/tmp`, since
  macOS `mktemp -d` paths overrun the socket limit), run from
  `run-sminos-tests.sh`; the live check is `tests/mods/live-bridge-check.py`.
  Date/Author: 2026-10-15, M1 executor.

## Surprises & Discoveries

- (M1) With a permission dialog open, the bridge's outermost `tool.call`
  hook for that call is still in flight: the `PermissionRequest` and the
  `tool.call` of one call overlap in time, so M3 can match a request to its
  call and use the call's settling as a withdrawal signal.
- (M1) `/clear` fires `session.end` (reason `clear`) and no
  `session.start`, and the session id changes.
- (M1) macOS `mktemp -d` paths plus `/bridge/<uuid>.sock` exceed the
  104-byte `sun_path`; the real default (`~/.claude/sminos/bridge/…`) is
  about 75 bytes.
- (M1) The session's `end` event is best effort (the process exits right
  after); a consumer should read a vanished endpoint as the session gone.
- (M1) Live, the model again ran a "foreground" Agent call in the
  background (as in DC1); subagent chunks streamed with their `agentId`
  either way.

## Outcomes & Retrospective

Pending — written at finish.
