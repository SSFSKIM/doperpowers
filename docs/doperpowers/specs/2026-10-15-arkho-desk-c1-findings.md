# Arkho A8 — C1 findings: the bridge, live (2026-10-15)

> **Cites:** `docs/doperpowers/specs/2026-10-15-arkho-project-web-design.md`,
> child **C1** (Bridge spike — spike, findings, never a merge), parent pin
> **8257d780**. Answers that child's Acceptance list and the design's §8
> unknown 1, against §2 (Bridge, Without the bridge) and §5 (Control). The
> spec's writer folds the verdicts into its Surprises & Discoveries; this
> file is the evidence they point to.

## Verdicts

| # | Primitive (C1 Acceptance) | Terminal | `--bg` | Verdict |
|---|---|---|---|---|
| 1 | `$.process.spawn` session-lifetime child; its lines reach the mod idle, mid-model-call, mid-Bash | yes (0–11 ms) | yes (≤ 3 ms) | **promote** |
| 2 | `$.prompt.submit({asUser: true})` from a timer starts a turn in an idle session | yes | yes | **promote** |
| 3 | `$.session.append` mid-turn, read at the next request; does the terminal draw it | read: yes; drawn: **no** | same | **promote** with the `$.ui.log` mirror §8 anticipated |
| 4 | `$.turn.abort` stops a running turn | yes, 13–29 ms | same | **promote-with-change**: a running Bash is moved to the background, not killed |
| 5 | `classic.PermissionRequest` long-polls the daemon and answers with the dialog open; the terminal answering first | answer: yes; terminal-first: hook never told | same | **promote-with-change**: retraction needs its own signal |
| 6 | `tool.call` hook answers a native AskUserQuestion with the dialog open | native alone: yes; under the doperpowers ask mod: **breaks the turn** | same | **promote-with-change**: answer through `classic.PermissionRequest` `updatedInput.answers` instead |
| 7 | `$.config.set` switches the model | switches at once, **and rewrites the user's settings.json default** | not run (would rewrite `~/.claude/settings.json`) | **promote-with-change**: build on a `turn.step` model rewrite |
| 8 | `turn.step` chunk rate with two subagents | streams every loop with `agentId` | same | **promote** |
| 9 | `$.session.compact()` (added by the coordinator) | idle: yes; mid-turn: rejected | same | **promote-with-change**: the bridge holds a compact until `turn.complete` |
| 10 | A background subagent's permission prompt (added by the coordinator) | the dialog waits for the hook: none drawn for 40 s of polling; a 3 s bound drew it at 3.3 s | consistent (§5: presence `busy` while the hook polled); the bound not run there | **promote-with-change**: bound the hook for async subagents |
| 11 | A person-only ask (added by the coordinator) | no `PermissionRequest`, no `tool.call`: the terminal alone answers | — | **confirmed**: show it as "waiting in the terminal" |

Nothing in the list is a discard. Three of the changes alter §5's table
(rows Interrupt, Answer a question, Model); two change how C2 treats pending
requests (§3 Pending requests: retraction, and the bound for background
subagents); the rest are notes.

## Setup

- **Engine:** Claude Code 2.1.300 (`builtAt 2026-10-14T12:54:55Z`, as
  `$.session.version()` reported in every session).
- **Probe:** a throwaway plugin, `/tmp/c1probe/plugin/` (`hooks/register.ts`,
  about 370 lines), loaded with `--plugin-dir`. It hooks `session.start`
  (spawns the child), `turn.start` / `turn.complete` (tracks the main turn id),
  `turn.step` (forwards every chunk, POSTs each text chunk), `tool.call` on
  Bash and on AskUserQuestion, `classic.PermissionRequest`, `session.append`
  (logs every non-response row), `classic.PostModelSwitch`, `session.end`.
  `claude plugin validate` passed; `tsc` against the 2.1.300 declarations was
  clean.
- **Daemon stand-in:** `/tmp/c1probe/daemon.py`, stdlib asyncio, two Unix
  sockets in `/tmp/c1probe` (mode 0600): `d.sock` speaks HTTP for the mod's
  `$.http.fetch(..., {socketPath})` and for the operator (`/event`,
  `/pending`, `/wait` long-poll held 20 s, `/decide`, `/cancel`, `/cmd`);
  `b.sock` is the line protocol to each session's child,
  `/tmp/c1probe/bridge_child.py` (HELLO with session id and pid, then every
  command line copied to stdout, reconnecting when the daemon restarts). Every
  event carries the mod's clock (`mt`) and the daemon's (`dt`).
- **Sessions** (all `--model haiku --permission-mode default`, cwd
  `/tmp/c1work`):
  - **T1**, the owner's real setup in tmux: user settings, doperpowers 7.153.0
    (ask, to-human, kairos, agents, compact mods), cua, fullscreen TUI.
    Session `a15eddde-333f-4d28-92ff-427d27dd9a56`.
  - **T3**, the probe alone, in tmux, under an isolated `CLAUDE_CONFIG_DIR`
    (`/tmp/c1cfg`: no user settings, hooks or installed plugins; gateway env
    passed in the process environment). Used for the native AskUserQuestion,
    the engine's own drawing without the to-human view, and `$.config.set`
    (whose write landed in `/tmp/c1cfg/settings.json`, not the user's).
    Session `05b798ba-1e33-433a-b2fc-7e940f366620`.
  - **BG**, `claude --bg --plugin-dir /tmp/c1probe/plugin --model haiku
    --permission-mode default -n c1probe-bg "…"` from `/tmp/c1work` (the
    supervisor's launch), job `088ddf6c`, watched through `claude attach
    088ddf6c` in a tmux pane, and once with no client attached.
  - **T5**, T1's setup again, for background subagents (item 10). Session
    `1807420a-ad1f-46ae-b284-409e82b2c1b1`.
  - **T6**, T3's isolated setup again, for a person-only ask (item 11).
    Session `f5500cfc-edef-4177-8b87-29be50cb21ac`.
- **Function hooks reach the session:** the probe read
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` = `"1"` in T1, T3 and BG.
- **The permission case, made real.** The owner's `PreToolUse` hook
  `~/.claude/hooks/bash-guardrail.sh` answers `allow` for every Bash command
  it does not classify as destructive, so `touch`, `python3 -c …` and
  `sleep …; echo …` ran without a dialog in default mode (observed). The
  dialog cases therefore use `rm -rf /tmp/c1work/junkX && …`, which the
  guardrail defers; in T3 (no guardrail) `python3 -c 'import time;
  time.sleep(12)…'` raised the dialog itself.
- **Evidence:** `/tmp/c1probe/daemon.log` (2,562 JSON lines, every quote below
  that names a log event), the session transcripts under
  `~/.claude/projects/-private-tmp-c1work/` (`a15eddde-…`, `088ddf6c-…`,
  `1807420a-…`) and `/tmp/c1cfg/projects/-private-tmp-c1work/` (`05b798ba-…`,
  `f5500cfc-…`).

## 1. A session-lifetime child — promote

**Ran.** `session.start` awaits `next(e)`, then starts
`$.process.spawn({argv: ['/usr/bin/python3', '-u', CHILD, sessionId]})` in a
detached async loop that splits stdout on newlines and dispatches each line.
The daemon wrote `{"op":"ping"}` lines to the child's socket: once idle; 40
times at 250 ms while the model streamed a 400-word story; during a 15 s Bash
call; while a permission dialog and an AskUserQuestion dialog were open.

**Observed.**
- The child is a direct child of the session process (T1: pid 24259, ppid
  23275 = `claude --plugin-dir /tmp/c1probe/plugin …`; BG: ppid 25681 =
  `claude bg-spare …`). Its first stdout line reached the mod 3 ms after it
  connected.
- Every command reached the mod in every state. `cmd-recv` lag (daemon write
  to mod receipt): idle 0 ms; streaming 40/40 received, 0–11 ms, each with
  `"modelStreaming": true`; mid-Bash 1 ms with `"bashRunning": 1`; with the
  AskUserQuestion dialog open (T3) 1 ms. BG: 41/41, max 3 ms.
- Session end kills the child: `child-ended {"code": null, "signal":
  "SIGTERM"}` then `session-end` in T1, T3 and BG; no orphan remained.
- A module reload (an edit under `--plugin-dir`) kills the child and runs
  `session.start` again, which spawns a new one: the daemon sees a disconnect
  and a new HELLO from a new pid.

**For C2.** The child should reconnect to the daemon on its own (the probe's
did, across a daemon restart: `"connects": 2`), and the daemon should treat a
new HELLO for a session as the same session's bridge, since reloads and
daemon restarts both happen.

## 2. `$.prompt.submit({asUser: true})` from a timer — promote

**Ran.** Command `submit` scheduled with `$.clock.after(1500, …)`, the callback
calling `$.prompt.submit({text, asUser: true})`, into an idle session; then
again while a 12 s Bash call ran.

**Observed.**
- Idle: `timer-fired` at 01:10:20.573, the prompt row and `turn-start` 16 ms
  later, the call resolving with the turn's start (`resolved_after_ms: 16`;
  T3 28 ms; BG 52 ms). The model obeyed it bare ("c1-submitted-ok").
- The transcript row: `origin: {"kind": "plugin", "name": "c1probe",
  "asUser": true}`, `promptSource: "system"`.
- The terminal names the plugin. T3 (the engine's own view):
  ```
  › Prompt from the c1probe plugin
  ❯ (sent from the web) Reply with exactly one line: c1-submitted-ok
  ⏺ c1-submitted-ok
  ```
  T1 and BG (fullscreen, to-human view) draw only `› Prompt from the c1probe
  plugin`.
- Busy: the call queued, drew `› Prompt from the c1probe plugin` at once,
  and resolved 10.3 s later as its own turn started, right after the running
  turn completed. That is §4's Send ("queued for when the session is idle").

**For C2.** The model reads the words as the human's; the terminal shows
them as the plugin's. If the terminal should credit the web's sender, that is
a `UserMessage` render hook in the bridge, not a property of `asUser`.

## 3. `$.session.append` mid-turn — promote, with the mirror

**Ran.** During a 20 s Bash call (T1), a 12 s one (T3, BG):
`$.session.append({message: {type: 'user', content: [{type: 'text', text:
'[steer from the web] … include the word PINEAPPLE …'}]}})`, in T1 and BG
followed by `$.ui.log('steer (web): …')`.

**Observed.**
- The call resolved with the stored row: `{"type": "user", "role": "user",
  "isMeta": true, …}` and a uuid.
- The running Bash call was not disturbed (T1 `bash-end` 20,130 ms, output
  intact). The next request carried the row (T1 step 1 `messageCount` 177
  against 172 for step 0) and the model acted on it: "The command printed
  c1-steer-done after its 20-second sleep. PINEAPPLE" — in T1, T3 and BG.
- The transcript stores the row between the `tool_use` and its
  `tool_result`, `isMeta: true`, `origin: {"kind": "plugin", "name":
  "c1probe"}`; the request the engine sent merged them into one user message
  (`api-request-blob`: `tool_result:c1-steer-done | [steer from the web] …`).
- **The terminal does not draw the row** — T3, the engine's own view, during
  and after the turn shows only the Bash call and the reply. The `$.ui.log`
  mirror draws as `⏺ c1probe: steer (web): [steer from the web] …` and is
  stored as a `system` notice.
- The bridge's own `session.append` hook does not see its own append (the
  re-entry rule); other plugins' hooks do.

**Verdict.** As §8 anticipated: the steer is real and the bridge mirrors it
with `$.ui.log` so the terminal shows the same conversation.

## 4. `$.turn.abort` — promote-with-change

**Ran.** `$.turn.abort({turnId})` with the id the main loop's `turn.start`
handed the probe: mid-Bash (a 30 s Python sleep) and mid-stream (a long
story), in T1 and BG. For comparison, Esc in the terminal on the same Bash
call.

**Observed.**
- Command receipt to `turn-complete {"reason": "aborted"}`: T1 mid-Bash 22 ms,
  mid-stream 13 ms; BG mid-Bash 29 ms, mid-stream 15 ms.
- **A running Bash call is moved to the background, not stopped.** The
  tool_result recorded for it: `Command running in background with ID:
  b5y6zo7fe. Output is being written to: …`; `ps` still showed the Python
  process after the abort, and its completion notification later woke the
  model in a new turn. Esc on the same call killed the process and recorded "The user
  doesn't want to proceed with this tool use. …".
- `$.tool.call({tool: 'TaskStop', task_id: <that id>})` from the mod killed
  the backgrounded command: `"Successfully stopped task: bqirg9evw (python3
  -c …)"`, no process left (BG).

**Change.** If Interrupt should mean what Esc means, the bridge follows the
abort with `TaskStop` on the task id the aborted call's tool_result names (the
bridge sees that row in its `session.append` hook, door `tool-result`). If
leaving the command running is acceptable, say so in §4 instead; either way
the current reading of §5 ("Interrupt stops the turn") hides that the
command survives.

## 5. `classic.PermissionRequest` long-polling the daemon — promote-with-change

**Ran.** The hook awaits `next(e)` (the settings hooks beneath), POSTs the
request to `/pending`, and loops `GET /wait` (the daemon holds 20 s, answers
200 with a decision, 204 on timeout, 410 when cancelled) until a decision
arrives or its signal aborts. Cases: web allow, web deny, terminal first
(Enter in the dialog), a late web decision after the terminal answered, a
subagent's Bash call, BG with a client attached and with none.

**Observed.**
- The hook fires while the dialog is drawn. T1, 01:03:15.944 `bash-start`,
  01:03:16.213 `perm-hook` (the owner's own settings `PermissionRequest` hook,
  `notify.sh permission`, ran beneath in 188–386 ms across runs; 17 ms in T3
  with none), the pane showing:
  ```
   Bash command
   rm -rf /tmp/c1work/junkA && sleep 8 && echo c1-perm-A
   Do you want to proceed?
   ❯ 1. Yes
     2. Yes, and always allow access to /tmp/c1work from this project
     3. Yes, and switch to auto mode · auto mode handles these prompts for you
     4. No
  ```
- **Web allow:** the daemon released the wait 11.7 s into its first round;
  within one second the dialog was gone and the command running; it finished
  (`c1-perm-A`) and the transcript shows `⎿ Allowed by PermissionRequest
  hook`.
- **Web deny** (`{behavior: 'deny', message}`): the dialog closed, the call
  ended `isError` with the message as its tool_result, the pane showed `⎿
  Denied by PermissionRequest hook`, and the turn went on (`reason:
  "answer"`); the model read the message.
- The transcript keeps each hook decision as an attachment:
  `{"type": "hook_permission_decision", "decision": "allow", "toolUseID":
  "toolu_0122ZFdnfRwMZPrpZ2H1dibc", "hookEvent": "PermissionRequest"}`.
- A long-poll across rounds holds: one hook waited 35.5 s over two rounds with
  no budget failure (a `$` call in flight stops the 10 s budget, as §2 says).
- `$.http.fetch` rejects at 30 s: `HooksError: c1probe:
  $.http.fetch(http://daemon/hold?ms=45000) over /tmp/c1probe/d.sock aborted:
  no complete answer within 30000ms` (30,034 ms). `HttpInit` has no
  `signal`, so the mod cannot cancel a poll in flight; only the daemon can
  end it.
- **Terminal first: the hook is never told.** Enter in the dialog ran the
  command at once, but the hook's `next.signal` did not abort: its round ended
  on the daemon's 20 s timeout with `"aborted": false` and it polled again (T1
  and BG). A web decision sent 35 s later resolved the hook and changed
  nothing, silently.
- The session's presence file tracks the dialog exactly: during it
  `{'status': 'waiting', 'waitingFor': 'permission prompt'}`, 0.7 s after
  Enter in the terminal `{'status': 'busy', 'waitingFor': None}`
  (`~/.claude/sessions/<pid>.json`; for an AskUserQuestion dialog
  `waitingFor: 'input needed'`).
- **A subagent's prompt** carries `agent_id` in the hook input and was allowed
  from the web like any other; while it waited, the presence file read
  `{'status': 'busy', 'waitingFor': None}` (BG). That subagent ran in the
  background, and item 10 explains the reading: no dialog was open yet.
- `claude plugin validate` warns: hooks on `classic.PermissionRequest` "do not
  run in a plugin a person installs where an organization manages Claude Code
  … only a plugin the organization lists in managed settings runs them". The
  owner's machines have no managed settings; a future org-phase machine might.

**Change (for C2 and §3 Pending requests).**
1. The pending request must be retracted from a signal other than the hook's
   abort: the presence file leaving `waiting`, the matching `tool.call`
   settling (the bridge's own `tool.call` hook wraps the same call; the
   request has no `tool_use_id`, so match on tool name and input), and
   `turn.complete`. Presence speaks only while a dialog is actually drawn
   (item 10), so it cannot be the only signal.
2. On retraction the daemon answers the hook's open poll (410), so the hook
   returns and stops polling.
3. Publish the pending request before awaiting `next(e)`, so the settings
   hooks beneath (≈ 0.2–0.4 s on the owner's machine) do not delay the web.
4. For a background subagent the same hook must be bounded (item 10).
5. The hook's `next.signal` does abort when something above settles the call
   (observed in §6), so keep listening to it as well.

## 6. Answering a native AskUserQuestion — promote-with-change

**Ran.** (a) The `tool.call` hook on `AskUserQuestion` calls `next(e)` (the
dialog opens) and races it against the daemon; when the web answers first it
returns `{result: {questions, answers}}` without waiting. (b) The same
question answered instead through `classic.PermissionRequest`, which also
fires for AskUserQuestion, returning `{behavior: 'allow', updatedInput:
{questions, answers}}`. (c) The terminal answering first. Each in T1 and BG
(the doperpowers ask mod loaded, so the model calls
`mcp__doperpowers__AskUserQuestion`, whose `$.ui.ask` raises the built-in)
and (a) in T3 (the built-in called directly, no ask mod).

**Observed.**
- **(a) native, nothing beneath (T3):** works. The dialog closed, the pane
  shows `⏺ User answered Claude's questions: ⎿ · Which pet do you prefer? →
  Dog`, the model read "Your questions have been answered: …=\"Dog\"" and
  replied "You chose Dog." The abandoned engine dispatch settled internally
  with "The user doesn't want to proceed …", unseen by the model.
- **(a) under the doperpowers ask mod (T1, BG): breaks the turn.** The probe,
  loaded through `--plugin-dir`, sits above doperpowers in every chain
  (`next.trace`: `1:doperpowers/user`, `2:cua/user`, `3:engine/core`), so its
  hook saw the ask mod's narrow raise (`"header": "ask-1"`, empty option
  descriptions) and answered it. The ask mod reads the outcome of its own
  widening hook's `next` (`openDialog`, `hooks/mods/ask.tsx:480-523`), which
  the abandoned dialog settled as `Error: Permission for this tool use was
  denied …`; it took that as a refusal, latched, and the turn ended
  `"reason": "aborted"` with the model never seeing "Blue".
- **(b) through `classic.PermissionRequest` works in every setting.** Its
  `tool_input` is the widened set the dialog shows (`"header": "Fruit"`, with
  descriptions). Allowing with `updatedInput.answers` closed the dialog; the
  engine's own record followed (`⏺ User answered Claude's questions: ⎿ · Which
  fruit do you prefer? → Mango`), the ask mod's tool returned "Your questions
  have been answered: …", and the model replied "You chose Mango." (T1; BG:
  Apple, same rows.)
- **(c) terminal first:** answered normally; the `tool.call` hook saw the
  engine settle first (it can retract), the `PermissionRequest` hook again was
  not told (same as §5).

**Change (§5 row "Answer a question", §8 unknown 1).** Answer every
AskUserQuestion dialog through the same `classic.PermissionRequest` hook as
permissions, with `updatedInput: {questions, answers}`. One path for both
kinds of prompt; it answers exactly the dialog on screen; the engine writes
its own record; and the hook order between the bridge and the ask mod stops
mattering, which closes §8's "the hook order that lets a web answer settle
above the ask mod's". Answers are keyed by question text, multi-select labels
comma-joined, free text as given.

**Not covered here:** §5's "the ask mod's external-answer path for an async
one". The ask mod has no such path today: an async ask is answered only by
pressing its `[ answer ]`, which opens the dialog (`answerAsk`,
`ask.tsx:928`). Since the bridge will live in the same module, C2 can add a
function there that marks an ask answered and calls the existing `deliver`.

## 7. `$.config.set` switching the model — promote-with-change

**Ran.** In T3 only (isolated config dir): `$.config.list()`, then
`$.config.set({key: 'model', value: 'sonnet'})`, then back to `haiku`, with a
`classic.PostModelSwitch` hook logging. Then the alternative: a `turn.step`
hook passing `next({...e, model})` for main-loop steps, in T3 and BG.

**Observed.**
- The row is `model` (`{"key": "model", "value": "haiku"}`). The call
  resolved `{value: 'sonnet'}` and `$.session.model()` read
  `claude-sonnet-5-5[1m]` at once.
- **It persisted the choice as the user's global default:**
  `/tmp/c1cfg/settings.json` went from `{"model": "haiku"}` to `{"model":
  "sonnet"}`, the same write `/model` makes. It also fired
  `PostModelSwitch` (`"source": "command"`, `"requested_model": "sonnet"`).
  On the owner's machine the write would land in `~/.claude/settings.json`,
  where his own `keep-default-model.sh` (`PostModelSwitch`) restores `opus`
  three seconds later; anyone without that hook keeps the web's pick as the
  default for every new session.
- Not run in BG or T1: there it would have rewritten
  `~/.claude/settings.json`.
- **The `turn.step` rewrite is session-scoped.** With the session on sonnet
  and the override set to `claude-haiku-5-5[1m]`, the step reported
  `"model": "claude-sonnet-5-5[1m]", "override": "claude-haiku-5-5[1m]"` and
  the response's `usage.model` was `claude-haiku-5-5`; BG the other way round
  (`usage.model = claude-sonnet-5-5`). No settings write. `$.session.model()`
  and the terminal's status line keep the launch model.

**Change (§5 row "Model").** Build the Model control on the `turn.step`
rewrite: the bridge holds the session's chosen model, rewrites every main-loop
step, and reports the effective model in presence itself, since the terminal's
status line will not. `$.config.set` is right only if a web switch should
change the machine's default for new sessions, which the design does not
intend.

## 8. `turn.step` with two subagents — promote

**Ran.** One prompt spawning two general-purpose subagents in one message
(model haiku), each writing 250 words; every text chunk POSTed to the daemon
fire-and-forget as it passed the hook (T1, BG). Also the main loop alone (a
400-word story).

**Observed.**
- `turn.step` fires for each subagent's loop with its `agentId`, as for main;
  `turn.start` / `turn.complete` too. (The model ran the two Agent calls in
  the background although asked for foreground; the main turn ended and the
  task notifications woke it later. The subagents streamed either way.)
- Chunk kinds: `text`, `thinking`, `tool`, `input`, `stop`, `engine`. Text
  chunks average 24 characters.
- Rates (`/tmp/c1tools/chunks.py` over `daemon.log`), during text output:

  | Session | Loop | Text chunks | Characters | Text span | Rate |
  |---|---|---|---|---|---|
  | T1 | main, story alone | 92 | 2,196 | 1.8 s | 50/s |
  | T1 | subagent "sea" | 58 | 1,406 | 1.1 s | 52/s |
  | T1 | subagent "mountains" | 61 | 1,542 | 1.2 s | 51/s |
  | BG | subagent "mountains" | 62 | 1,541 | 0.9 s | 71/s |
  | BG | subagent "sea" | 57 | 1,406 | 1.0 s | 55/s |

  Text arrives in bursts after the thinking phase (the "sea" subagent: first
  thinking chunk 1.1 s after its request, text from 7.1 s, all text within
  1.1 s). Peak across all loops in any one second: 51 (T1), 62 (BG, main and
  a subagent overlapping).
- Per-chunk `$.http.fetch` over the socket kept up: lag p50 1 ms, max 10 ms
  (T1); p50 3 ms, p95 35 ms, max 98 ms (BG, under the overlap). The forwarded
  stream to the screen was unaffected.

**For C3.** Size the session plane for bursts of about 50–70 chunks a second
per active loop, about 1.2 KB/s of text each, rather than for averages.

## 9. `$.session.compact()` — promote-with-change

**Ran.** From the bridge's command loop, idle and while a 12 s Bash call ran,
in T1 and BG.

**Observed.**
- Idle, T1: compacted in 23.9 s, `tokensBefore 45,592 → tokensAfter 5,743`;
  the pane shows `Conversation compacted (ctrl+o for history)`. BG: 17.0 s,
  `40,519 → 5,206`.
- **BG counts as interactive:** `session.start` reported `"isInteractive":
  true, "surface": "terminal"` in the BG job, so `compact.tsx`'s
  `{isInteractive: true}` registration includes `--bg` seats; the note at
  `hooks/mods/compact.tsx:143-146` ("a headless (-p / SDK) session has no
  compactor a plugin can call") means `-p` and the SDK, not `--bg`.
- Mid-turn, both: rejected at once, not queued: `HooksError: c1probe:
  $.session.compact: a turn is running (b20d5e79-0929-43d7-94c2-dd1a37a31e85);
  the conversation compacts between turns, so call it from turn.complete or
  later`.

**Change.** The bridge holds a Compact that arrives mid-turn and runs it at
that turn's `turn.complete`, as `compact.tsx` does; the RPC answers "queued
for the end of the turn" rather than `done`.

## 10. A background subagent's permission prompt — promote-with-change

The engine spec for 2.1.287 says an async subagent's `PermissionRequest`
hooks are awaited before its dialog opens (`awaitAutomatedChecksBeforeDialog`,
`~/claude-code-bundle/2.1.287/SPEC/18-agent-tool-and-subagents.md`, step 3 of
the child-context builder; `24-permission-system.md`, the interactive-REPL row
of the consent-surface table). Checked on 2.1.300.

**Ran.** In T5 (the owner's setup), the model spawned one general-purpose
subagent with `run_in_background: true` whose prompt runs `rm -rf
/tmp/c1work/junkBG1 && echo c1-bgsub-1`. The probe's hook long-polled as in
§5. Then a second such subagent with the hook bounded to 3 s (on the bound it
returns the settings hooks' answer, here none).

**Observed.**
- Unbounded: the hook fired at 01:31:11.687 with `"agent_id":
  "ad5546a2fa3f887e8"`. For the next 40 s **no dialog was drawn anywhere**:
  the pane showed the idle prompt and the agents strip `◯ general-purpose  Run
  scratch-path removal command  37s`; presence read `{'status': 'busy',
  'waitingFor': None}`; the poll's first round ended on the daemon's timeout
  with `"aborted": false` and it polled again. A web allow at 01:31:51
  released it (`after_ms: 40064`) and the command ran (`c1-bgsub-1`).
- Bounded to 3 s: the hook returned no decision at 3.3 s (`wait-bound`,
  `"decision": null, "after_ms": 3301`) and the dialog appeared then, headed
  `Bash command · from the general-purpose agent`, with presence `{'status':
  'waiting', 'waitingFor': 'permission prompt'}`. No second
  `PermissionRequest` was raised once it was open; Enter in the terminal
  allowed it (`c1-bgsub-2`). From that moment the web could no longer answer.
- The hook input cannot tell a background subagent from a foreground one
  (`agent_id` is on both); `AgentInfo` from `$.agent.list()` has no background
  flag either. The bridge learns it where the agent starts: the Agent call's
  `run_in_background`, which an `agent.spawn` hook reads, or the tool_result
  "Async agent launched successfully" with its agent id.

**Change (C2, §3 Pending requests).** For a background subagent the hook is a
gate in front of the terminal's dialog, not a racer beside it. The bridge
bounds its wait there (a few seconds is enough to answer from a web page that
is open; the owner's choice of bound is the trade), publishes the request with
its deadline so the web can show the countdown, and on the bound returns no
decision, which hands the prompt to the terminal; the web then shows it as
"waiting in the terminal" from presence. An unbounded poll would make the web
the only place that prompt can be answered and leave the terminal blank,
which only suits a seat nobody is attached to.

## 11. A person-only ask — confirmed

The same spec says an ask marked `personOnly` never consults
`PermissionRequest` hooks (`24-permission-system.md`, "A person-only ask never
consults `PermissionRequest` hooks"). Producers it names include the mods
hot-reload question, an Artifact share confirmation, and some restricted-mode
and host-credential shell-write safety asks.

**Ran.** In T6 (isolated config dir), `/plugin-authoring` started the engine's
watch on `/tmp/c1cfg/dev-mods/f5500cfc-…/`, then a manifest written there from
outside raised the person-only question.

**Observed.** The pane showed `☐ Mods │ Enable hot reloading for this
session? … 1. How does this work? 2. Enable for this session 3. Not now`,
presence read `{'status': 'waiting', 'waitingFor': 'input needed'}`, and the
probe logged nothing for 10 s: no `PermissionRequest`, no `tool.call` on
AskUserQuestion, no pending request. "Not now" in the terminal closed it, and
the engine queued its own notice to the model ("The person declined mod
hot-reloading: …").

**Verdict.** Confirmed on 2.1.300. The web cannot answer such a prompt; when
presence says `waiting` and the bridge has no pending request for the session,
the web shows "waiting in the terminal" and offers nothing to click.

## What a bridge builder must also know

- **Hook order.** A `--plugin-dir` plugin sits outermost among user plugins
  (above doperpowers, then cua, then the engine). In production the bridge is
  part of doperpowers' own module, where registration order inside
  `register.tsx` decides; with §6's change no bridge decision depends on it.
- **`--bg` jobs** are pre-started `claude bg-spare` processes (this one
  started hours before the launch) under a `claude bg-pty-host`, claimed by
  the supervisor. `--plugin-dir` on `claude --bg` is honored. Presence file:
  `"kind": "bg"`, `"jobId": "088ddf6c"`. Everything above behaved the same
  attached and with no client attached.
- **Spawn and processes.** Child stdin is a one-shot string, so commands must
  come over the daemon's socket, as the design has it. The child must flush
  each line it writes (the probe ran Python with `-u` and flushed).
- **The engine refuses long foreground sleeps.** `sleep 30; echo …` was
  answered `<tool_use_error>Blocked: sleep 30 followed by: echo c1-abort-done.
  To wait for a condition, use Monitor …`, and the model re-ran it in the
  background. Parent Acceptance 6 ("a `sleep 60` Bash call") needs another
  long-running command, for example `python3 -c 'import time;
  time.sleep(60)'`.
- **Presence values seen:** `idle`, `busy`, `waiting` with `waitingFor`
  `"permission prompt"` or `"input needed"`. The `/config` row
  `permissionMode` shows the settings default (`auto`), not the live mode a
  `--permission-mode` flag set (`default`).
- **Timings in one place:** child line to mod 0–11 ms; submit to turn start
  16–52 ms; abort to turn end 13–29 ms; web decision to dialog gone under 1 s
  (the coarsest measurement here: a pane capture one second later);
  `PermissionRequest` after the tool call starts ≈ 0.25–0.5 s on the owner's
  setup (its own settings hook takes most of it); compact 17–24 s;
  `$.http.fetch` bound 30 s.

## Left in place

- `/tmp/c1probe/` — the probe plugin, the daemon stand-in and child, and
  `daemon.log` (the evidence quoted above).
- `/tmp/c1tools/` — the drivers (`cmd.py`, `say.py`, `tail.py`, `chunks.py`)
  and prompt files.
- `/tmp/c1cfg/` — the isolated config dir of T3 and T6, holding their
  transcripts, the `settings.json` that `$.config.set` rewrote, and the
  manifest under `dev-mods/` that raised the person-only question.

The BG job was stopped (`claude stop 088ddf6c`), the tmux sessions killed,
the daemon stopped; no bridge child or test command remained running.
