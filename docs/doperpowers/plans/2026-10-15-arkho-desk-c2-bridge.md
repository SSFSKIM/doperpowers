# A8 C2 — the bridge: execution (2026-10-15)

> **Composite:** `docs/doperpowers/specs/2026-10-15-arkho-project-web-design.md`
> (branch `worktree-smns-erb`), child **C2** (The bridge — plan). **Parent
> pin:** blob `8acb3958` of that file, as it stood at dispatch. The child's
> section there is its design; this document carries only the constraints
> and the milestones. Read the composite's §2 (Bridge, Without the bridge),
> §3 (sending, liveness of messages), §5 (both tables), §6 (the bridge's
> channel), X4, X5, and the C1 findings
> (`docs/doperpowers/specs/2026-10-15-arkho-desk-c1-findings.md`) before M1.

## Progress

- [ ] M1 — The bridge's spine and the local protocol (C2.G1)
- [ ] M2 — The control verbs and delivery (C2.G2)
- [ ] M3 — Requests from outside and their settlement (C2.G2, G3)
- [ ] M4 — Live export, the acceptance walk, docs, version (C2.G4)

## Constraints that bind every milestone

- **The composite has one writer**, the session that dispatched this plan.
  The controller records this plan's decisions in its own Decision Log
  below and messages that session at M1's end with X5 and with any
  decision that touches a contract; it does not edit the composite.
- **Isolation.** Every manual run of `sminos.py`, its daemon, or a hook uses
  a temporary `HOME` and `SMINOS_HOME` (the CLI's one-way `migrate` runs
  before every verb and once rewrote the owner's real registry). Never
  modify `~/.claude/settings.json`, `~/.claude.json`, the plugin store, or
  the real `~/.claude/sminos`; never run `daemon install` against the real
  `HOME`.
- **Live sessions** for checks run the worktree's plugin with
  `--plugin-dir` under a throwaway `CLAUDE_CONFIG_DIR` (C1 used
  `/tmp/c1cfg`), so the installed doperpowers mods do not load twice and
  nothing the session does reaches the owner's settings; prompts tiny,
  haiku or sonnet models; every `--bg` job started is stopped
  (`claude stop <short>`), every tmux session killed. C1's probe
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
  digests and the ledger, read-only policy (C3, C4, C7); the text of
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
`socketPath`); local clients — the CLI now, the daemon in C7 — send
commands there, which the child writes to its stdout for the mod to read
line by line, and subscribe to the event stream there. This puts local
control in place without the daemon running, and the daemon, when it
comes, discovers bridges by listing the directory. The socket answering
is the bridge-presence signal (§2's "bridge connected"); a stale socket
file whose child is gone is removed by whoever finds it. The composite's §2
says the child connects "to the daemon's socket"; this is the same
contract with the endpoint inverted, and the controller reports it to the
composite's writer with X5. Rejected: a single daemon socket every child
connects to, which would make the CLI verbs depend on the daemon running.

**Touches:** `hooks/mods/bridge.tsx`, `hooks/mods/register.tsx`,
`skills/sminos/scripts/sminos.py` (the `bridge` and `watch` verbs; a small
module beside it if the child grows past a few hundred lines),
`tests/mods/`, `tests/sminos/`.

**Interfaces:** produces X5 (below, written at this milestone's end and
sent to the composite's writer before M2 starts); produces the stream
shapes X4 names for chunks (passed through verbatim plus the three tags).

**Does not touch:** delivery (`deliver_next`, `push_member`), any control
verb, the daemon.

**Proves:** C2.G1. Tests pin: the child receives a command line at any
point of a turn (idle, mid-model, mid-Bash, dialog open — C1 item 1); the
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
  `$.ui.log` line, since the terminal does not draw the appended row (C1
  item 3).
- *Interrupt* is `$.turn.abort` on the main loop's turn, then `TaskStop`
  through `$.tool.call` on every Bash that the abort moved to the
  background in that turn — Esc's effect (C1 item 4).
- *Model and effort* are rewritten on each of the session's requests in
  `turn.step`; the session's choice lives in the bridge and in
  `$SMINOS_HOME/bridge/<session-id>.json` so a module reload keeps it.
  `$.config.set` is never called: it writes the user's default (C1 item 7).
- *Compact* asked during a turn is held and run at `turn.complete`; asked
  idle, it runs at once (C1 item 9).
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

**Interfaces:** consumes X5 from M1; extends it with the command lines for
these verbs and the delivery key.

**Does not touch:** permission and question handling (M3), export (M4),
the daemon's tick beyond what delivery already calls.

**Proves:** the steer, interrupt, model, compact, and send parts of
C2.G2. Tests pin: a steer during a long Bash (a Python sleep — the engine
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

**Decisions:** the composite's §2 bullets under "[binding — C1's
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

**Interfaces:** extends X5 with the long-poll, `raised`, and `settled`;
produces X4's pending-request shapes.

**Does not touch:** digests, authentication codes, the hub's pending set
(C7, C3).

**Proves:** the answer and decide parts of C2.G2, and C2.G3: settlement
in four cases — answered from the CLI first, in the terminal first, both
at once, and the CLI answering after the terminal did (refused as already
settled). Tests pin: a background subagent's dialog appears after the
3-second window; a terminal-first answer stops the poll within 2 seconds;
an AskUserQuestion answered through `updatedInput` reaches the model with
the doperpowers ask mod loaded.

### M4 — Live export, the acceptance walk, docs, version

**At its end:** a bridged session's `<message>` spans and async questions
reach the project log as each completes, not at Stop, and the Stop hook's
export finds them already there; C2's gates walked live in a terminal
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

**Proves:** C2.G4, and C2.G1–G3 again live. Concrete Steps has the walk.

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

X5 is written here at M1's end and sent to the composite's writer; M2 and
M3 extend it in place, each extension sent the same way.

## Decision Log

- Decision: Verification. Each milestone gets the subagent-driven
  execution's task review at its boundary; the branch gets a `high`
  review through `doperpowers:review-code` at the end, run by the
  controller.
  Rationale: one repository, a mod and a CLI with a live-session walk;
  the security boundary is C7's.
  Date/Author: 2026-10-15, the composite's writer at dispatch.
- Decision: The bridge child serves a per-session socket (M1).
  Rationale and the rejected alternative: M1.
  Date/Author: 2026-10-15, the composite's writer at dispatch.
- Decision: Parent re-pinned to blob `b5af3c65` (commit `b7a82a59`). The
  only change since `8acb3958` is the dispatch commit's own revision of §2,
  §6, and X5 to the per-session endpoint this plan already assumes; no
  sibling has landed, so no interface this plan consumes moved.
  Date/Author: 2026-10-15, controller (pre-flight).
- Decision: G3's fourth case. The composite's C2.G3 names "the daemon
  reconnecting after the request was answered"; M3's Proves names "the CLI
  answering after the terminal did". C2 covers both: with no daemon in this
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
  read. C1 carried it in the process environment, through an env file it
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

## Surprises & Discoveries

## Outcomes & Retrospective

Pending — written at finish.
