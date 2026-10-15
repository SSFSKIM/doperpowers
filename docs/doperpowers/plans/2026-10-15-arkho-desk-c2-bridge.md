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

- [x] M1 — The bridge's spine and the local protocol (DC2.G1) — reviewed
  clean 2026-10-15 (`fbd19b1a`, fixes `79bb122b`, `6ac34e14`). Carried to
  M4's walk: a `--bg` run, and a module reload in the middle of a response
  (the resync source is module-local state).
- [x] M2 — The control verbs and delivery (DC2.G2) — reviewed clean
  2026-10-15 (`56619f3d`, fixes `75faba58`, `7842ae4e`). Carried to M4's
  walk: `send --wait` to a bridged seat, model and compact on a bridged
  `--bg` job, and a foreground subagent's Bash under interrupt.
- [x] M3 — Requests from outside and their settlement (DC2.G2, G3) —
  reviewed clean 2026-10-15 (`3a33efcd`, fixes `10f913d5`, `4b13cb9e`).
  Carried to M4's walk: an async question's `[ answer ]` pressed in the
  terminal (needs a mouse press; harness-covered).
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

### DX5 — Local bridge protocol (version 1, as amended by fix wave 1)

Rows changed by fix wave 1 are marked **[fw1]**.

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
  never names a socket that is not yet listening. **[fw1]** A child's identity is the
  inode of its own socket, read from the temporary name before the rename (never from
  the path after it, where a newer child's socket may already stand).
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
  the session id changes. **[fw1]** A `/clear` is seen at its `session.end` (reason
  `clear`): from then nothing more goes to the old child, the new id is looked for every
  100 ms (up to 5 s), and once found the old child is given up to 1 s to receive what was
  already queued for it, then stopped, and a child for the new id started. The heartbeat
  (every 5 s) is the fallback for a change of id with no `session.end`. Never in a session
  with `SMNS_INTERNAL` set.

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
  The mod posts nothing before it. **[fw1]** Its first post to a child is always the
  session's `start` then a `resync`; events queued while no child answered are not sent
  (the resync holds their effect on the live state).
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
| `session` / `end` | M1 | `reason` (the engine's; `clear` for a /clear) — best effort, the process exits next. **[fw1]** After a `clear` end, the old child gets nothing more; the next session's events go to its own child |
| `turn` / `start` | M1 | `turnId, agentId, text` (the prompt), `truncated?` **[fw1]** |
| `turn` / `complete` | M1 | `turnId, agentId, reason` (`answer`, `aborted`, `refusal`, `error`), `usage` (the turn's, or null) |
| `step` / `start` | M1 | `turnId, agentId, step` (the request's index in the turn), `model, effort, messageCount` |
| `step` / `end` | M1 | `turnId, agentId, step, stopReason, usage` |
| `chunk` | M1 | `turnId, agentId, step, chunkIndex, chunk` — **DX4's chunk:** `chunk` is `turn.step`'s chunk object verbatim (`text`, `thinking`, `tool`, `input`, `stop`; `engine` items are not sent); the three tags are `turnId`, `agentId`, and `chunkIndex`, the chunk's index in its message from 0; a message is identified by `(turnId, agentId, step)` |
| `tool` / `call` | M1 | `toolUseId, tool, agentId, input` (the tool's own arguments), `truncated?` |
| `tool` / `result` | M1 | `toolUseId, tool, agentId, isError, denied?, text?, truncated?` |
| `agent` / `spawn` | M1 | `agentId, parentAgentId, subagentType, description, name, background, model, toolUseId` |
| `agent` / `stop` | M1 | `agentId, agentType` |
| `usage` | M1 | `context: {tokens?, window, percent?}, cost: {usd} \| null` — the engine's `$.session.usage()` context and cost as it returns them (tokens and percent absent before the first response; cost null without a ledger) — after each main turn |
| `heartbeat` | M1 | `state` (as `ping`'s) — every 5 s |
| `result` | M1 | `id, op, ok, result?, error?` — the mod's answer to a command |
| `gap` | M1 | `dropped` — events that reached no child (a failed post, an overflowing queue). **[fw1]** Always followed at once by a `resync`; a live subscriber may also resubscribe |
| `resync` | M1 **[fw1]** | `turns: [{turnId, agentId, t}], streaming: [{turnId, agentId, step, model, text, thinking, upTo}], agents: [...]` — the mod's own copy of the session's live state, whole; the child replaces its turns, streaming messages and subagents with it. Sent as the first post to every child (after the session's start) and right after every `gap`; after it, chunks follow on from each message's `upTo` |
| `command` | M1 (the child's own) | `id, op` — a command relayed to the mod |
| `raised` | **reserved (M3)** | `request` (the tool-use id), `tool, input, agentId, deadline?` (a background subagent's 3 s bound) — DX4's pending request |
| `settled` | **reserved (M3)** | `request, winner` (DX4's: the side whose answer the engine used), `outcome, by` (`cli`, `terminal`, later `web`) — exactly one per `raised` |
| `delivered` | **reserved (M2)** | `key: {writer, seq}, outcome: "submitted" \| "duplicate"` |

**[fw1]** Every string in a tool's input, at any depth, a result's text, a denial, and a
prompt is held to 65,536 characters, and the event carrying any cut says `truncated: true`. Events reach the child in the order they
happened: the mod keeps one post in flight, batches of up to 500.

#### Subscription (`GET /events`, built)

- **Line 1, the snapshot:**
  `{"type": "snapshot", "session", "protocol": 1, "pid", "sessionInfo": {...the session start, "ended"?}, "turns": [{turnId, agentId, t}], "streaming": [{turnId, agentId, step, model?, text, thinking, upTo}], "agents": [{agentId, ...the spawn's fields, agentType?, running}], "usage": <the last usage event or null>, "pending": [], "settled": []}`.
  `streaming` holds every message still streaming: its partial text and thinking and
  `upTo`, the `chunkIndex` of the last chunk they include (-1 for none). A message leaves
  it at its step's end or its turn's end. **[fw1]** A snapshot never claims an `upTo` its
  text does not cover: a chunk that does not follow its message's `upTo` (one was lost, or
  the message began before this child) takes the message out of `streaming` until the
  next `resync` puts it back whole.
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
**[fw2]** On a `gap`, the human view says so, subscribes again at once, and prints the fresh
snapshot, each streaming message whole, then follows on (DX4's rule on a discontinuity).
With `--json`, the `gap` and its `resync` are passed through for the reader to act on.

#### M2 extension (as reviewed clean; rows changed by its fix waves marked [fw1]/[fw2])

Every DX5 row M2 built or changed, as it should now read (rows fix waves 1 and 2 changed are also marked **[fw1]** and **[fw2]**). Rows not listed here stand as
M1 left them (with fw1/fw2). Changed rows are marked **[M2]**.

##### Parties

- **Local clients**: the CLI (`sminos watch`; `steer`, `interrupt`, `model`, `compact`;
  the log's delivery, `deliver_next` and `send`, through `push_live`) and the daemon
  (DC7). **[M2]**

##### What the child keeps (built, M2) **[M2]**

- **File:** `$SMINOS_HOME/bridge/<session-id>.json`, mode 0600, written whole
  (temporary name, then rename) whenever it changes:
  `{"override": {"model": <id or null>, "effort": <effort or null>} | null, "delivered": {"<writer>": <seq>}}`.
- **Written from the mod's events:** `model` (sets `override`; null when both are null),
  `delivered` with outcome `submitted` (raises the writer's seq), `resync` (replaces
  `override` and `delivered` with the mod's copy).
- **[fw1] A failed write is not taken as kept.** The child holds the mod's copy in memory and
  writes it whole whenever it differs from what the file holds; what the file holds moves
  only after a write succeeds. **[fw2]** The write is made at the end of every batch of the
  mod's events (`POST /events`), whatever the batch carries, so a failed write is retried by
  any later event — a duplicate `delivered`, a heartbeat — not only by one that changes what
  is kept. Writing that starts to fail is said once as the child's own `kept {ok: false}`
  event, and writing that works again as `kept {ok: true}` (below).
- **Lifetime:** outlives the child (a module reload) and the session's process (a session
  resumed under its id goes on with both). Discovery (DC7) lists `*.sock` only.

##### The child's stdout: lines for the mod

- First, once the socket answers:
  `{"op": "hello", "session": "<id>", "pid": <child pid>, "socket": "<path>", "protocol": 1, "kept": {"override": …, "delivered": {…}}}`
  **[M2]** `kept` is what the child keeps for the session (above). A module that holds no
  kept state yet (fresh, after a reload) takes it; one that already holds its own (a child
  restarted, a /clear) keeps its own and hands it to the child in the resync. The mod's
  first post is still the session's `start` then a `resync` (fw1).

| Op | Built | Arguments | Result |
| --- | --- | --- | --- |
| `steer` | M2 **[M2]** **[fw1]** | `{text}` | `{row: <uuid of the appended user row>}`. During the main turn: `$.session.append` of a user row (one text block), read at the main loop's next model request; the running tool goes on; mirrored as the transcript line `steer: <text>` (`$.ui.log`). Refused idle (`ok: false`, "no turn is running to steer: send it instead"). **[fw1]** The steer is bound to the main turn it was given in before the append is awaited. When that turn ends with `answer` and no main-loop request of it began after the row was in (or the turn ended while the append was pending, and the row then lands), the bridge submits **one wake prompt** (`asUser`) that does not repeat the steer. **[fw2]** The wake is owned by the originating turn: it is decided once the turn has ended *and* every append given in it has settled (in, refused, or failed), and is issued at most once per turn: "I added a note to the conversation while you were finishing your answer. Read it and act on it." (`STEER_WAKE`); the next request reads the row. A turn ending `aborted`/`error`/`refusal` wakes nothing. One wake per turn, however many steers |
| `interrupt` | M2 **[M2]** **[fw1]** | — | `{turnId, stopped: [<task ids>], running: [<task ids>]}`: `$.turn.abort` on the main turn, then `TaskStop` (`$.tool.call`) on each Bash call **attributable to that turn** and running at the abort whose result names the background task the abort moved it to (`running in background with ID: <id>`; their results awaited at most 3 s). **[fw1]** Attributable: a main-loop call made during that turn, or a call of a foreground subagent spawned in it (nested foreground subagents inherit their parent's turn); a background subagent's calls never are. **[fw1]** `running` names each task whose TaskStop failed (an `isError` result or a rejection): the interrupt is incomplete when it is not empty. Idle: `{turnId: null, stopped: [], running: []}` |
| `model` | M2 **[M2]** | `{model, effort?}` — `model` an id, a family alias, `"default"` or null; `effort` one of `low medium high xhigh max`, or null | `{model, effort}` now in force (null: the session's own). Rewritten on every **main-loop** `turn.step` request, subagents untouched; never `$.config.set`. A family alias (`haiku`, `sonnet`, `opus`, `fable`) is resolved through the session's `ANTHROPIC_DEFAULT_<FAMILY>_MODEL`; one it does not map is refused, naming the id to use. Emits `model`; kept by the child |
| `compact` | M2 **[M2]** | `{instructions?}` | During the main turn `{queued: true, turnId}`: held, and run inside that turn's `turn.complete` (a second while one is held keeps the first). Idle `{started: true}`: run at once. Either way the outcome follows on the stream as `compact` events carrying this command's `id` |
| `deliver` | M2 **[M2]** **[fw1]** | `{key: {writer, seq}, text}` | `{submitted: true}` or `{duplicate: true}`. `text` is submitted with `$.prompt.submit({text, asUser: true})` (queued until the session is idle; not awaited). **The delivery key** is the log event's `(writer, seq)` — for a push carrying several events of one writer, the last. A key whose seq is at or below the highest already submitted for its writer is a duplicate and dropped (delivery goes per writer in seq order). The per-writer seqs are kept by the child across reloads; a /clear starts them anew (a new id is a new recipient). **[fw1]** The `delivered` event is emitted before the submission is made, so it is the next thing posted. Deduplication across a module reload is **best effort when the reload lands mid-submission**: a key submitted whose `delivered` had not reached the child is not kept, and a redelivery of it may submit again (a residual of at-least-once delivery, §3) |

##### Events (the mod's posts; the stream's lines)

| `type` / `phase` | Built | Fields |
| --- | --- | --- |
| `step` / `start` | M1, **[M2]** | `turnId, agentId, step, model, effort, messageCount` — **[M2]** `model` and `effort` are what the request was sent with, after the bridge's rewrite |
| `resync` | M1 **[fw1]**, **[M2]** | `turns, streaming, agents` (fw1) **and `override, delivered`** — what the child keeps, which it replaces with these |
| `model` | M2 **[M2]** | `model, effort` — the choice now in force (null: the session's own) |
| `compact` / `start` | M2 **[M2]** | `id` — the `compact` command's id |
| `compact` / `end` | M2 **[M2]** | `id`, and one of: `tokensBefore, tokensAfter` (null when the engine recorded none); `skip` (a hook vetoed it); `error` (the engine refused it, as during a turn) |
| `delivered` | M2 **[M2]** (was reserved) | `key: {writer, seq}, outcome: "submitted" \| "duplicate" \| "refused"`, `reason?` — `refused` follows a `submitted` when the engine later dropped or rejected the prompt |
| `kept` | M2 **[fw1]** **[fw2]** (the child's own) | `ok: false, error` when writing `<id>.json` starts to fail (said once, however many batches it keeps failing; retried at the end of every batch); `ok: true` when a write works again after a failure |

##### Subscription (`GET /events`)

- **Line 1, the snapshot** gains **`"override": {model, effort} | null`** **[M2]**: the
  session's model choice made through the bridge (the session start's `model` stays the
  launch model).

##### The control verbs (built, M2) **[M2]**

`<member>` resolves as for `watch` (a name, `alias#short`, a seat, or a session id; exit 4
for unknown, seatless, or another machine's).

| Verb | Bridged | No bridge | Exit |
| --- | --- | --- | --- |
| `sminos steer <member> <text>` | op `steer` | live `--bg` job: the supervisor's `reply` (raw text, human origin, `nextTurn`); else a live session: inbox frame `[sminos steer from human]\n<text>`; not live: exit 4 | 0; 1 refused (idle) or no answer |
| `sminos interrupt <member>` | op `interrupt`; prints the stopped tasks, or "idle: nothing to interrupt". **[fw1]** A non-empty `running` is printed as "incomplete: background task(s) … still running (TaskStop failed)" and exits 1 | refused, exit 4 "no bridge" | 0; 1 |
| `sminos model <member> <model\|default> [--effort E]` | op `model` | refused, exit 4 | 0; 1; 2 bad effort |
| `sminos compact <member> [instructions]` | subscribes, then op `compact`; queued: says so and exits; started: waits (≤ 300 s from the command, **[fw1]** a monotonic deadline, not reset by other events) for its `compact` end and prints the counts | refused, exit 4 | 0; 1 error or no outcome |

##### Delivery's last hop (`push_live`, built, M2) **[M2]**

For a live recipient, `deliver_next` (through `push_member`) and `send` (through
`send_to_seat` / `send_to_member`) push the frame text the inbox would carry, in this
order:

1. **The bridge**, when the push carries a log event: op `deliver` keyed by the last event
   (wait 10 s). Answered `ok` (submitted or duplicate): delivered (`sent`). No bridge
   answering: next path. Refused (nothing submitted): a warning, next path. Taken and not
   answered: uncertain (`sent?`, settled, never pushed again).
2. **The engine supervisor**, for a `human` event to a live `--bg` job (the engine record's
   `kind: "bg"` and 8-hex `jobId`): `{"proto": 1, "op": "reply", "short", "text", "auth":
   <~/.claude/daemon/control.key>, "nextTurn": true}` on
   `/tmp/cc-daemon-<uid>/<sha256(abspath(~/.claude))[:8]>/control.sock`. `ok`: delivered;
   refused or unreachable: next path; written and unanswered: uncertain.
3. **The inbox frame**, as before.

A push with no log event (a seat outside any project, the raw session-name route) goes
straight to the inbox frame.

##### Reserved for M3 (unchanged)

The `/requests/…` routes, the `raised` and `settled` events, and the snapshot's `pending`
and `settled` stand as M1 reserved them.

#### M3 extension (as reviewed clean; rows changed by its fix waves marked [fw1]/[fw2])

Every DX5 row M3 built or changed, as it should now read. Rows not listed stand as M1
and M2 left them. Changed rows are marked **[M3]**; rows fix wave 1 changed are also marked **[fw1]**.

##### Parties

- **Local clients**: the CLI (`watch`; `steer`, `interrupt`, `model`, `compact`;
  **`decide`, `answer`**; the log's delivery) and the daemon (DC7). **[M3]**

##### Routes

| Route | Built | Body | Answer |
| --- | --- | --- | --- |
| `GET /requests` | M3 **[M3]** | — | 200 `{pending: [<raised>…], settled: [<settlement>…]}` (the snapshot's two lists) |
| `GET /requests/<request>` | M3 **[M3]** | — | 200 the pending request's `raised` fields plus `session` (DC7's digest check); 404 `{error}` when not pending; 410 `{error: "settled", settled}` once settled |
| `GET /requests/<request>/wait?ms=` | M3 **[M3]** **[fw1]** (the mod's) | — | Held up to `min(ms, 20000)`. 200 `{decision: {behavior, message?, updatedInput?}, by}`: a client's decision, handed out once. 410 `{reason: "terminal"}`: the terminal answered it (the session record left `waiting`); this only ends the poll and closes the request to new decisions, and settles nothing. 410 `{reason: "settled", settled}`: settled. 204: nothing yet (an unknown request is held too, since its `raised` may still be in flight). **[fw1]** `watch=1` is gone: once its hook stops polling, nothing watches a request; the engine's record settles it |
| `POST /requests/<request>/decision` | M3 **[M3]** | `{behavior: "allow"\|"deny", message?, updatedInput?: {answers: {<question>: <answer>}}, by}`. `by` is `cli` or a member id (`terminal` and `bridge` are reserved). `updatedInput` only for a question, whose allow requires `answers` keyed by its questions. An async question cannot be denied | 200 `{accepted: true, request}`: the settlement follows on the stream. 400 `{error}`: malformed or not allowed. 404: not pending. 409 `{error: "already settled", settled}`. 409 `{error: "already answered by <by>; …"}`. 409 `{error: "the window … closed; the terminal answers it", terminalOnly: true}`: past a background deadline minus 200 ms. 409 `{error: "the terminal answered it; …"}`. For an async question, the child relays it as op `answer` (wait 5 s); the mod's refusal is a 409 carrying its error |

##### The child's stdout: lines for the mod

| Op | Built | Arguments | Result |
| --- | --- | --- | --- |
| `answer` | M3 **[M3]** | `{request, answers: {<question>: <answer>}, by}`: an async question's answer, relayed from `POST …/decision` | `{answered: true}` once the ask mod took it, which delivers it as tool-result context or as a plugin prompt when the session is idle; `ok: false` with the ask mod's reason otherwise (not pending, already answered, its dialog is up, not serving) |

##### Events

| `type` / `phase` | Built | Fields |
| --- | --- | --- |
| `raised` | M3 **[M3]** (was reserved) | `request` (the call's tool-use id; `toolu_plugin_…` for the ask mod's dialog; `request-<base36>-<n>` for a call no check named), `tool`, `input` (strings capped, fw1), `agentId`, `deadline?` (epoch ms, only for a background subagent: raise + 3000), `async?: true` (an ask mod async question, tool `mcp__doperpowers__AskUserQuestion`), `truncated?`. DX4's pending request. Raised only when the settings hooks beneath did not decide. A person-only prompt raises nothing |
| `settled` | M3 **[M3]** (was reserved), **[fw1]** | `request, winner, outcome, by`. `outcome` ∈ `allow \| deny \| answered \| withdrawn`. `winner` ∈ `terminal \| other \| web`. `by` is `terminal` when the terminal's answer was used, `cli` when the CLI's was (winner `other`), the member id when the web's was (winner `web`), and `bridge` for `withdrawn` (winner `other`). A passed deadline settles nothing: the request stays pending, answerable only in the terminal, until the terminal's answer settles it as `terminal` with its real outcome. Exactly one per `raised`. **[fw1] Evidence, all tied to the call's own id:** (1) the engine's `tool_decision` record for the call, which arrives at decision time: source `hook` with the bridge's handed-out decision of the same behavior means the decider; `user_temporary`, `user_permanent` or `user_reject` means the terminal, with the record's real outcome (accept is `allow`/`answered`, reject is `deny`); anything else (`user_abort`, `config`, a hook's decision the bridge did not hand out) means `withdrawn` by `bridge`. A request the bridge's interrupt aborted is `withdrawn` whatever the record says. (2) With no record within 1 s of a real call's result row, the call's transcript (its subagent's own for a subagent) once the result row is in it: a `hook_permission_decision` mark carrying the call's `toolUseID` means the hook's answer was used (then as (1) with source `hook`); none means the terminal's, with the outcome the result shows. (3) Neither available (the ask mod's dialog keeps no rows; the transcript unreadable or the result never written within about 2 s): `withdrawn` by `bridge`. A turn's end and the session's end withdraw as before. An async question answered through a dialog a press opened settles with that dialog's request: `answered` by its `by` (or `withdrawn` when the dialog's was) |
| `block-row` | M3 **[M3]** | `uuid, turnId, agentId, step, index`: the transcript row `uuid` holds block `index` of that message. Posted from `session.append` for each response row, paired by the row's block type and the order of the step's block starts (a tool row by its call id), never by position. The child removes the block from `streaming` under the lock; later chunks of that block are ignored. A row whose block never streamed (a server tool) names none |
| `chunk` | M1, **[M3]** | Unchanged on the wire. The child now folds each chunk into its **block** (`chunk.index`) |
| `resync` | M1 fw1, M2, **[M3]**, **[fw1]** | `turns, streaming` (per block, as the snapshot's, **[fw1]** each entry also carrying `settled: [<index>…]`, the blocks a `block-row` settled), `agents, override, delivered`, **`pending`** (each `raised`'s fields with `t`), **`settled`** (recent settlements). The child replaces its pending set with `pending` (keeping a request's decided/closed state) and merges `settled` with its own. **[fw1]** The child keeps an entry's `settled` blocks out of the message and ignores their late chunks, and a block it saw settled itself stays settled across the resync, even when the copy does not name it (the snapshot's `streaming` entry shape is unchanged: `settled` is never shown) |

**The mod's evidence [fw1].** The mod hooks `telemetry.log` (`{to: "collector"}`) and
reads the engine's `tool_decision` records: `attributes.tool_use_id`, `source`, `decision`.
The engine raises them to plugins whether or not an OTel collector is configured. This
was confirmed live on 2.1.300, including with `DISABLE_TELEMETRY=1` and
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` both set, so no machine yet known runs the
transcript fallback. Should a release stop raising them, the fallback (2) above runs for
real calls, and the ask mod's dialogs settle `withdrawn` (3). DC7 and the web will see
that difference. The live check pins the records.

**Posting [M3].** The mod's posts all begin in one poster loop started at
`session.start`. Events emitted inside any hook are queued and the loop is woken. A post
begun inside another hook's dispatch would be aborted with it (an Esc, an interrupt).
Order, batching (≤ 500) and one post in flight are unchanged.

##### Subscription (`GET /events`)

- **Line 1, the snapshot** **[M3]**:
  - `"streaming": [{turnId, agentId, step, model?, upTo, blocks: [{index, kind, text, upTo, id?, name?}]}]`.
    One entry per message still streaming. `blocks` are its blocks with no
    `block-row` yet, in index order.
    - `kind` is `text`, `thinking` or `tool`.
    - `text` is the block's partial text (for a tool, its streamed argument JSON;
      `id` and `name` are the call's).
    - A block's `upTo` is the last chunk folded into it.
    - The message's `upTo` is the last chunk of the message applied, and is the fw1
      continuity check: a chunk that does not follow it takes the message out until
      the next `resync`.
  - `"pending": [<raised fields>…]`: the requests pending now.
  - `"settled": [{request, winner, outcome, by, t}…]`: the last 100 settlements, so a
    subscriber that arrives after a request settled sees it settled (G3's fourth case),
    and a late answer is refused as already settled.
- `sminos watch` prints a raised request as `· [<loop>] permission: <tool> <summary> — request <id>`
  (or `question: …` with its options, `async question: …`, and ", answerable from outside
  until HH:MM:SS" for a window), its settlement as `· request <id> settled: <outcome> (<by>)`, and the
  snapshot's pending requests and per-block text.

##### The verbs (built, M3) **[M3]**

| Verb | Bridged | No bridge | Exit |
| --- | --- | --- | --- |
| `sminos decide <member> <request> allow\|deny [--message M]` | Subscribes and finds the request in the snapshot (by exact id or a unique prefix). Then `POST …/decision` `{behavior, message?, by: "cli"}`, then waits up to 30 s for its `settled`. Prints "<member>: request <id> settled from here: <outcome>" | exit 4 "no bridge" | 0 the engine used this answer; 1 already settled (snapshot or 409), not pending, window closed, terminal answered, another side's answer used (naming it), or no settlement; 2 a 400 |
| `sminos answer <member> <request> <answer>…` | As `decide`, with `allow` and `updatedInput.answers`: one answer per question, in order. An answer is an option's number or label (any case), a multi-select's labels comma-separated, or free text | exit 4 | as `decide`; 2 also for a count that does not match the questions, or a request that asks no question |

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
- Decision (M1 review): Recovery is authoritative, not just announced. The
  mod keeps its own copy of the live state (open turns, streaming messages
  with text and `upTo`, subagents); its first post to every child, and its
  next post after any loss, carry a `resync` the child replaces its state
  with. The child refuses a chunk that does not follow its message's `upTo`
  and drops that message from snapshots until the next resync, so no
  snapshot claims an `upTo` its text does not cover. `sminos watch`'s human
  view resubscribes on a `gap`. A child's identity is its own socket's
  inode, read before the rename, so an older child cannot claim a newer
  one's path. At `session.end(clear)` routing to the old child stops; the
  new id is polled every 100 ms (heartbeat as fallback).
  Rationale: the task review reproduced "AC, upTo 2" after a lost chunk, a
  socket theft under overlapping startups, and a 5-second window in which a
  cleared session's events reached the old endpoint.
  Date/Author: 2026-10-15, controller, from M1's review and fix waves 1–2.
- Decision (for M3, agreed with the composite's writer for DC3): DX4's
  pending-request values. `settled.outcome` is one of `allow | deny |
  answered | withdrawn`; `withdrawn` means the request ended with no answer
  the engine used (the turn aborted with the dialog open, the session
  ended, the call settled otherwise), with winner `other` and by `bridge`.
  `settled.by` is the member id when the web won (carried from the decision
  body's `by`, which DC7 fills from the RPC's `member`), `cli` when the CLI
  won (winner `other`, since DX4's winner is `web | terminal | other`), and
  `terminal` when the terminal won. `raised.deadline` is optional, present
  only for a background subagent's 3-second window. A passed deadline
  settles nothing: the request stays pending, no longer answerable from
  outside (the web shows "waiting in the terminal"), until the terminal's
  answer settles it with winner `terminal` and its real outcome — exactly
  one `settled` per `raised`.
  Date/Author: 2026-10-15, controller with the composite's writer.
- Decision (M3 scope, approved by the composite's writer): Pairing a
  streaming block with its transcript row. The mod never sees the API
  message id or request id (not on `turn.step`'s input, chunks, result or
  usage; not on `session.append`'s input), and the engine writes one
  transcript row per content block, the rows of one response sharing
  `message.id` (DC1's transcripts). What it does see is the row's `uuid` at
  `session.append` (door `response`, with the loop's `agentId`), the same
  uuid the transcript keeps. So:
  1. DX5 gains `{type: "block-row", uuid, turnId, agentId, step, index}`,
     posted from the `session.append` hook for each response row; `index`
     is the content block's, the same `index` its chunks carry. The row is
     matched to its block by the row's block type plus the order of the
     step's block starts, not by assuming the nth row is block n; M3's first
     live run checks that assumption anyway and records what it finds. The
     daemon relays the event as DX4 kind `block-row`, same body (DX4's `row`
     is the transcript row verbatim; one name per thing at both layers).
  2. The snapshot's `streaming` entries become per block: `{turnId,
     agentId, step, blocks: [{index, kind, text, upTo}]}`, replacing M1's
     aggregated `text`/`thinking` per message; the mod's `resync` state
     follows the same shape. Applying a `block-row` removes its block from
     `streaming` under the same lock, so a snapshot holds only unsettled
     blocks, and chunks for a settled block are ignored.
  3. DX4 (the composite's): a transcript row whose `uuid` a `block-row`
     named settles that block.
  Date/Author: 2026-10-15, controller with the composite's writer.
- Decision (M2): Delivery. The key is deduplicated per writer as a
  high-water seq (delivery runs per writer in seq order and stops a writer
  at its first failure), and a push carrying several events of one writer is
  keyed by the last. Both `human` and `say` reach a bridged session
  `asUser` with the inbox frame's text, as this plan's M2 says. A push the
  bridge accepted is `sent` (the submission queues until idle); a refusal
  falls through to the next path; taken and unanswered is `sent?`. A
  module reload landing between a submission and the child persisting its
  key can submit it twice: accepted as a residual of at-least-once
  delivery (composite §3), since persisting first would trade it for a
  loss window. The child keeps the per-writer seqs and the model choice in
  `$SMINOS_HOME/bridge/<id>.json`, written at the end of every batch while
  it differs from the file, a failing stretch reported once as `kept`.
  Date/Author: 2026-10-15, M2 executor; reload residual ruled by the
  controller.
- Decision (M2): Without a bridge, a `human` to a live `--bg` job goes
  through the supervisor's `control.sock` `reply` with `nextTurn: true`
  (without it the reply could answer an open question dialog); a peer's
  `say` stays the inbox frame, since `reply` stamps human origin. The
  socket is computed as the engine does from `~/.claude`, so a temporary
  `HOME` always names a temporary supervisor.
  Date/Author: 2026-10-15, M2 executor.
- Decision (M2): Steer. Refused idle. Bound to its originating main turn
  before the append is awaited; if that turn answers with a steer row
  unread, one wake prompt that does not repeat the text is submitted once
  every append of that turn has settled; an aborted or failed turn wakes
  nothing.
  Date/Author: 2026-10-15, M2 executor, after two review rounds.
- Decision (M2): Interrupt stops only the aborted turn's Bash calls the
  abort moved to the background: the main loop's and those of foreground
  subagents spawned in that turn (the abort ends them, as Esc does), never a
  background subagent's. A TaskStop that fails is reported in `running`,
  and `sminos interrupt` exits 1.
  Date/Author: 2026-10-15, M2 executor.
- Decision (M2): Model applies to the main loop only. A `turn.step` model
  rewrite is sent on the wire as given, so the bridge resolves a family
  alias through the session's `ANTHROPIC_DEFAULT_<FAMILY>_MODEL` and refuses
  one it does not map; the web should offer model ids. `step/start` reports
  the model actually sent.
  Date/Author: 2026-10-15, M2 executor.
- Decision (M2): Compact answers at once (`queued` mid-turn, `started` idle)
  and reports its outcome as `compact` events; `sminos compact` waits on a
  fixed 300 s deadline for a started one.
  Date/Author: 2026-10-15, M2 executor.
- Decision (M3): Request identity. A request's id is its call's
  `tool_use_id`, matched from the bridge's `tool.check` (the
  PermissionRequest input carries none); every PermissionRequest takes its
  check whether or not anything is raised. The ask mod's blocking question
  has the engine's `toolu_plugin_…` id; a request no check names gets a
  synthetic `request-<base36>-<n>`.
  Date/Author: 2026-10-15, M3 executor, check consumption after review.
- Decision (M3): Raised after the settings hooks beneath, not before (DC1
  suggested before): a request a settings hook then decided would need a
  fourth `by`. Cost: up to about 0.4 s before the web sees it. Confirmed by
  the composite's writer. The raise-or-skip decision is made after the
  hook's last await.
  Date/Author: 2026-10-15, M3 executor; confirmed by the composite's writer.
- Decision (M3, after review): Settlement names the winner from the
  engine's own exact-id evidence, never a guess. Primary: the OTel
  `tool_decision` record the engine raises to a mod's `telemetry.log` hook
  at decision time (~0.1–0.2 s), carrying `tool_use_id`, `decision` and
  `source` — `hook` with the bridge's decision handed out: the decider
  wins; `user_*`: the terminal wins with its real outcome, except
  `user_abort`, which is `withdrawn` by `bridge`; `hook` with none of ours
  handed out (a mod above decided): `withdrawn`. Fallback for a real call
  with no record: the transcript's `hook_permission_decision` mark by
  `toolUseID` at the call's result (hook won) or its absence (terminal
  won). Only where neither exists is a request `withdrawn` by `bridge`.
  Records are kept by call id (last 200) until a raise or an attribution
  has used them. A live witness mod pins the record. It still arrives with
  `DISABLE_TELEMETRY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set.
  Rejected: the 1.5 s grace and answer comparison of M3's first build,
  which could credit the wrong side.
  Date/Author: 2026-10-15, controller with M3 executor, from M3's review.
- Decision (M3): Async questions from the ask mod are raised with `async:
  true`, cannot be denied, settle `answered` or `withdrawn` (when the ask
  mod forgets them; a turn's end does not withdraw them), and an answer
  given through the dialog an async ask opened is credited to whoever
  answered that dialog. A decision may carry `updatedInput` only as a
  question's answers; `by: terminal` and `by: bridge` are reserved (400).
  A decision within 200 ms of a background request's deadline gets 409
  `{terminalOnly: true}`. The snapshot keeps the last 100 settlements; the
  resync carries `pending`, `settled`, and each streaming message's settled
  block indexes, so a resync never resurrects a settled block.
  Date/Author: 2026-10-15, M3 executor.
- Decision (M3): The mod posts to the child only from a loop started at
  `session.start`: a `$.http.fetch` begun inside a hook's dispatch dies when
  that hook is aborted. Pinned by the live check (no gaps across an
  interrupt).
  Date/Author: 2026-10-15, M3 executor.
- Decision (M4 scope, agreed with the composite's writer for DC7): Row
  order and the snapshot cut. DC7 joins transcript rows read from disk with
  the bridge's stream; DX4 needs one gap-free order in which no row is both
  in the snapshot and still streaming. The mod's `session.append` hook runs
  before `next()` writes the row, so it announces each row before disk has
  it, and the daemon reads the content by uuid:
  1. Every observed row gets exactly one notice, in write order, on the
     ordered stream: a response row's is its `block-row` (atomic: the block
     leaves `streaming` as the row becomes known); every other row's is
     `{type: "row-seen", uuid, agentId, door}`; the bridge's own appends
     (steer rows, which its hook does not see) get a `row-seen` from the
     append's returned uuid; door `queue` (no transcript row) gets nothing.
  2. The snapshot gains `cut: {"main" | <agentId>: <uuid> | null}`, the
     last notice applied per loop, under the lock that guards `streaming`:
     every row at or before a loop's cut has had its notice applied, so no
     block in `streaming` has its row at or before the cut. `null`: nothing
     observed since the module loaded. The mod's `resync` carries the cut.
  3. The consumer rule (DX5's, for DC7): history is each loop's disk rows
     up to and including its cut (null: to EOF at snapshot time, later
     notices for uuids already emitted dropped); live, each notice emits the
     row with that uuid from disk once flushed, in notice order, and a row
     not on disk within 5 s ends the DX4 subscription; a disk row past the
     cut that no notice named within 2 s is emitted in disk order; a
     `row-seen` for a uuid already emitted is ignored; a `block-row` for a
     uuid already emitted as an unnamed row ends the DX4 subscription (a
     discontinuity; the fresh snapshot heals the block that would otherwise
     stay beside its row).
  4. Readiness: `GET /status` gains `ready` (the mod's first resync to this
     child applied); `GET /events` holds until ready (≤ 5 s, else 503); the
     child ends every open subscription when it applies any later resync, so
     no subscriber sees a `resync` line and "the stream ended" is the one
     discontinuity.
  5. M4's live run compares notices with the transcripts (main and
     `subagents/*.jsonl`) and reports every row kind without a notice.
  Tests: the real child, with a reference consumer implementing rule 3 in
  the test, through a disk flush ahead of a delayed notice across
  subscription establishment and across a reconnect, a subscription opened
  between a response's last chunk and its `block-row`, `GET /events` held
  before the first resync, and a response row's notice delayed past the 2 s
  bound.
  Date/Author: 2026-10-15, controller with the composite's writer.
- Decision (M4 review, agreed with the composite's writer): Notices follow
  the write, and the consumer follows the disk. Superseding the entry
  above where they differ. A notice posted at hook entry did not match the
  engine's write order (live: a session's first prompt was noticed before
  its environment attachment but written after it), and the reference
  consumer emitted unnamed compaction rows behind a later prompt. So:
  1. The mod posts a row's notice after `next()` resolves; notice order is
     write order within a loop. The cut and its invariant are unchanged.
  2. The consumer rule: history waits until each loop's cut row is on disk
     (5 s, else a discontinuity) and reads up to and including it; live,
     disk rows are emitted strictly in disk order, a row past the cut
     released on whichever comes first — its own notice, a notice for any
     later row of the same loop (a row passed over is unnamed), or 2 s
     with neither — and every later row waits behind it. A notice whose
     row is not on disk within 5 s, and a `block-row` for a uuid already
     released unnamed, end the subscription; a `row-seen` for an already
     released uuid is ignored.
  3. The live walk fails on any break between notice order and disk order
     and records the largest flush-to-notice lag it sees, while chunks
     stream too; a lag near the 2 s window raises the window.
  4. Posts are fenced to the module instance that read the child's
     `hello`: the child mints a nonce there and refuses (409) any post
     without it, so an old module's in-flight dispatch after a reload
     cannot roll back the cut, the model override, or the delivery
     high-water mark.
  Date/Author: 2026-10-15, controller with the composite's writer, from
  M4's review.
- Decision (M4, from DC7's M1 review, ruled by the composite's writer):
  Each loop's cut is seeded at load. A `null` cut sent history to EOF, so
  a row flushed after the module loaded but before its notice could sit in
  the snapshot's history while its block was still in `streaming`. Now the
  mod's first `resync` reports each loop's cut as the last row that loop
  had when the module loaded; `null` means only "this loop had no rows".
  The invariant: no block of a loop enters `streaming` before that loop's
  cut is seeded, and no block in `streaming` has its row at or before the
  cut. A seed row not yet on disk is covered by the consumer's 5 s wait for
  a cut row. The engine's message list (`$.session.messages()`) carries no
  row uuids, so the seed cannot come from it; the means are M4's executor's
  to choose against the invariant, proven by a race test (a row flushed
  between the module's load and the seed). Ruled the same day: the seed is
  each loop's transcript tail, and a message whose step began before the
  tail read *completed* never enters `streaming`; its chunks reach no
  subscriber, and it surfaces only through its rows (at or before the seed
  in history, or past the cut and released live, its `block-row` settling
  nothing). Accepted cost: no partial text for a message streaming at a
  module load. Tests: the race, and a message beginning while the read is
  in flight (excluded).
  Date/Author: 2026-10-15, controller with the composite's writer.
- Decision: Merge order with DC4's branch. DC4 also bumps the version in
  its M4, so whichever branch merges second re-bumps through
  `scripts/bump-version.sh` above the first; no version number is merged by
  hand. The sminos-suite flake ("at most once more: two frames in all",
  `run-sminos-tests.sh` ≈ line 4838) is already in DC4's
  `docs/doperpowers/TECH-DEBT.md`; this branch adds no second entry.
  Date/Author: 2026-10-15, controller, from the composite's writer.

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
- (M2) A `turn.step` model rewrite reaches the API verbatim: `sonnet`
  failed every request at the gateway (`400 … got sonnet`); the resolved id
  worked.
- (M2) The module validator requires `$.env.get` to take a literal name.
- (M2) The aborted Bash call's result (`Command running in background with
  ID: …`) reaches the bridge's outermost `tool.call` hook; no
  `session.append` hook is needed to find the task. Abort to turn end
  0.64–0.65 s live.
- (M2) A bridged delivery's prompt row is `origin: {kind: "plugin", name:
  "doperpowers", asUser: true}`; a supervisor `reply` row is `origin: {kind:
  "human"}, promptSource: "queued"`.
- (M2) A supervisor under a temporary config needs
  `CLAUDE_CODE_DAEMON_COLD_START=transient` so it does not offer to install
  a service; `claude daemon stop --any` under that config stops it.
- (M3) The `hook_permission_decision` mark is written only with the call's
  result (+20.24 s on a 20 s call), but the engine's `tool_decision`
  telemetry record reaches a mod's `telemetry.log` hook at decision time,
  for permission dialogs and the ask mod's question alike.
- (M3) A `$.http.fetch` begun inside a hook's dispatch is aborted with that
  dispatch (Esc, interrupt), even through a `$` captured earlier.
- (M3) In three live runs the nth response row of a step was block n every
  time; the bridge still pairs rows by kind and start order.
- (M3) A `--bg` job starts in permission mode `auto` (2.1.300); a plain
  Bash call raises nothing there. Requests come from a `--bg` job only in a
  prompting mode or for calls `auto` escalates.
- (M3) A background subagent's dialog is drawn only once the hook returns,
  as DC1 found; with the 3 s window it appeared just after the deadline.
- (M1) Live, the model again ran a "foreground" Agent call in the
  background (as in DC1); subagent chunks streamed with their `agentId`
  either way.

## Outcomes & Retrospective

Pending — written at finish.
