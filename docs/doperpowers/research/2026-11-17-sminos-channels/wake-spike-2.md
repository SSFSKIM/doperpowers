# The wake, measured again on 2.1.329 (2026-11-20)

> Research for `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md` (D2, and the engine facts E1 to E16 of its Grounding Baseline). It follows `wake-spike.md` (2.1.327) and `bg-resume-experiment.md` (2.1.326).
> Session ids are shortened to their first eight characters. Scratch paths are written `<scratch>/...`.

Claude Code `2.1.329 (Claude Code)`, on a Mac, 2026-11-20.

**Method.** Every engine process ran under a scratch `HOME` and a scratch `CLAUDE_CONFIG_DIR` (`<scratch>/cfg`), in an isolated tmux server, with the environment stripped (`env -i`) except a fixed `PATH`, the locale, and the variables the API gateway needs (copied at run time, never written down). The scratch engine started its own background supervisor (`daemon run`, spare directory `/tmp/cc-daemon-<uid>/<hash>/` with a hash of its own), so the machine's real supervisor and session registry never saw a scratch session. Each scratch directory had a `.claude/settings.local.json` with `defaultMode: "acceptEdits"` and `model: "claude-haiku-4-5-…"`, and every launch passed `--model haiku` (served as `claude-haiku-5-5`), so the settings' defaults and the flags can be told apart in the transcript.

Each claim is **measured** (seen in a trial), **read** (from help text or the installed program) or **inferred**. A turn's mode is `permissionMode` on its prompt row. The model and effort a turn ran under are on the transcript's `api-request` row (`params.model`, `params.output_config.effort`), and the model served is `message.model` on an assistant row with a `requestId`.

## 1. The row (E8)

**Measured.** It is still `jobs/<first eight>/state.json` under the config dir, plus a `jobs/pins.json` (`[]`). A session that had only run in a terminal had no row. Its first background resume wrote one, before the command returned. Keys of a row whose worker started:

    backend children cliVersion createdAt cwd daemonShort detail firstTerminalAt inFlight intent
    lastTerminalAt linkScanOffset linkScanPath name nameSource needs output providerEnv
    respawnFlags resumeSessionId sessionId state template tempo tokens updatedAt

- **What names the session:** `sessionId` (full id) and `resumeSessionId`.
- **What names the directory:** `cwd`.
- **The saved options:** `respawnFlags`, for example `["--permission-mode","acceptEdits","--add-dir","<scratch>/x/b2","--model","haiku"]`.
- **Optional keys:** `name`/`nameSource` appear once the session has a name. A row whose worker failed or sits idle lacks `cliVersion`, `inFlight`, `tokens` and `linkScanPath`. A row written by `/background` adds `interactiveLineage: true` and `bgIsolation: "none"`.
- **`providerEnv`:** holds only `ANTHROPIC_DEFAULT_*_MODEL`, `CLAUDE_CONFIG_DIR` and `CLAUDE_BG_SESSION_CREDENTIAL`. The last is a 9-character handle, not the gateway token. `ANTHROPIC_BASE_URL` is not among them.

## 2. Flags on a first background resume (E2, E12)

Each trial was a first `claude --bg --resume <id> … <message>` on a session that had only run in a terminal. Unless noted: exit 0, the banner `backgrounded · <same id>`, no copy note, and the flags saved in `respawnFlags`.

| Flags | In effect in the resumed turn (**measured**) |
|---|---|
| `--permission-mode auto --model haiku --effort low --settings <file with env>` | `permissionMode: "auto"`. Request `model: claude-haiku-5-5`, `effort: low`. `T2SET=from-settings` in Bash. |
| `--permission-mode acceptEdits --add-dir <x> --model haiku` | `permissionMode: "acceptEdits"`. A Write into `<x>` ran without a prompt. A Bash call with `${…}` stopped at a permission prompt (`state: blocked`, `waitingFor: "permission prompt"`). |
| `--permission-mode bypassPermissions --model haiku` | `permissionMode: "bypassPermissions"`. Only once the bypass disclaimer had been accepted (below). |
| `--dangerously-skip-permissions --model haiku` | `permissionMode: "bypassPermissions"`. Saved as `"--dangerously-skip-permissions"`. |
| `--allow-dangerously-skip-permissions --permission-mode bypassPermissions` | `permissionMode: "bypassPermissions"`. Both flags saved. |
| `--add-dir <dir not trusted>` | **Refused, exit 1, no row:** `Added folder not trusted: <dir>. Leave out its --add-dir or, if you trust it and everything in its repository or below it, start `claude` there once and accept the trust prompt.` |

**Measured: bypass needs the disclaimer.** With the user settings lacking `skipDangerousModePermissionPrompt: true`, all three bypass forms failed (exit 1, no row) with `--bg with bypassPermissions requires accepting the disclaimer first. Run `claude --dangerously-skip-permissions` once interactively.` With that setting present, `--permission-mode bypassPermissions` alone was accepted. None of the three is needed beyond the disclaimer.

**Measured: the name.** No `-n` was passed on these resumes.
- A first resume **with** a message lost the terminal's name. A session named `term-b` in the terminal (`custom-title` and `agent-name` rows `term-b`) was woken with a message, and the bg process wrote an `ai-title` row and a new `agent-name` row with a generated title. `sessions/<pid>.json` and `claude agents` then gave that title, with `nameSource: "auto"`. The `custom-title` row still says `term-b`. Seen twice (`term-b`, `term-i`).
- A first resume **without** a message (sections 11 and 14) kept the name (`term-a`, `term-j`, `nameSource: "user"`).

## 3. Mode names (measured)

`claude --help` lists `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`. `default` is no longer listed but is still accepted.

| `--permission-mode` | transcript `permissionMode` |
|---|---|
| `manual` | `default` |
| `default` | `default` |
| `acceptEdits` | `acceptEdits` |
| `auto` | `auto` |
| `bypassPermissions` (or `--dangerously-skip-permissions`) | `bypassPermissions` |
| `dontAsk` | `dontAsk` |
| `plan` | `plan` |

**Measured.** `respawnFlags` also writes `manual` as `default`: after a switch to manual mode inside an attached session the row read `"--permission-mode","default"` (section 6). In an attached background session the mode key cycled acceptEdits → plan → manual → acceptEdits.

**Measured.** The transcript also carries `{"type":"permission-mode","permissionMode":…}` metadata rows. They are re-appended at each process start and are not the turn's mode: a session's bg turn ran under `auto` while the latest such row still said `default`. Read the prompt row.

## 4. A later resume, and the copy notes (E2, E3, E14)

**Measured.** All on stderr. The banner is on stdout and the exit status is 0.

- **Flagless, stopped, row present.** Continued the same id under the row's options. The banner now carries the name:

      backgrounded · 354a0e73 · touch test file path
      note: woke session 354a0e73 with its saved options (--permission-mode, --add-dir, --model).

- **Any flag (`--model haiku`), stopped, row present:**

      backgrounded · 87396850
      note: background session 354a0e73 keeps its own saved options, so the flags you passed started a copy as 87396850. Without flags, the same command continues 354a0e73 itself.

- **Flagless, bg process live:**

      note: session 97746c13 is already running in the background, so this started a copy as a2778067. `claude attach 97746c13` opens the original.

- **Flagless, terminal process live:**

      note: session 4497cc3d is open in another Claude Code process, so this started a copy as 96a1142e. The original conversation is unchanged.

**Measured.** A copy started because the session was already running ran under the **settings' defaults**, not the row's options. Copy `9d611372` of a session whose row said `bypassPermissions`/`haiku` ran `acceptEdits` on `claude-haiku-4-5`.

**Measured.** A first background launch also printed `Starting background service…` on stderr when it started the supervisor.

## 5. A worker that fails before it starts (E8, E12)

**Measured.** Command: `claude --bg --resume <id> --output-style Explanatory --model haiku "<msg>"` (first resume).
- **The command:** exit 0, stdout `backgrounded · b9e9a8cb`, nothing on stderr. It returned after 0.82 s, and the job was already `failed` at the first poll after return (0.04 s later).
- **`claude agents --json --all`:** `{"id":"b9e9a8cb","kind":"background","sessionId":"<full>","name":"<the message text>","state":"failed"}`. No `pid` and no `detail` in the list.
- **The row:** `state: "failed"`, `detail: "exit 1 before init — error: unknown option '--output-style'"`, and `respawnFlags: ["--model","haiku"]`. The flags the worker would have accepted are kept; 2.1.327 left `[]`.
- **The transcript** was byte-for-byte unchanged (same SHA-1 before and after), and the message is in it nowhere.
- **The next resume with a flag** started a copy, with the "keeps its own saved options" note.
- **`claude rm b9e9a8cb`** answered `removed b9e9a8cb` and kept the transcript. A flagged resume afterwards (`--permission-mode auto --model haiku`) continued `b9e9a8cb` itself, with no note, and the turn ran `auto` on haiku-5-5.

**Inferred.** Since the row keeps the accepted flags, a flagless resume of such a row would run under them, not the settings' defaults. Not tried.

## 6. `/model` and a mode change inside an attached background session

**Measured.** Fresh `claude --bg --permission-mode acceptEdits --model haiku -n bg-h "<msg>"`, which saved `["--permission-mode","acceptEdits","-n","bg-h","--model","haiku"]`. Then `claude attach`, `/model claude-haiku-4-5-…` (confirmed), the mode key to manual, one turn, and the window killed.

- **The row was rewritten:** `["-n","bg-h","--model","claude-haiku-4-5-…","--permission-mode","default"]`.
- **Stop, then a flagless `claude --bg --resume`:** `note: woke session 007fb7f7 with its saved options (-n, --model, --permission-mode).` The turn ran `permissionMode: "default"` on `claude-haiku-4-5-…`, which is what the session last used, not the launch's flags.
- **Without a turn:** attached again, the mode key to acceptEdits and `/model haiku`, then detached with no turn. The row was rewritten at once to `"--permission-mode","acceptEdits","--model","haiku"`.

**Measured, E10 again.** A terminal process does not do this. Session `aef2131e` had a row (`acceptEdits`, `haiku`). It was stopped and reopened with `claude --resume` in a terminal. It ran there on the settings' default model, Haiku 4.5 (E7), switched to manual and ran a turn. The row was unchanged. The next flagless background resume ran `acceptEdits` on haiku-5-5, the row's options.

## 7. Two resumes at once (E13)

**Measured.** Two `subprocess.Popen` launches from one script, each `claude --bg --resume <id> "<msg>"`. "Close" means the second was spawned 1.7 to 2.6 ms after the first, the closest this harness could get. Rows were removed with `claude rm` between the no-row pairs.

| Row before | Apart | Pairs | Every pair |
|---|---|---|---|
| none | 2.1–2.6 ms | 3 | Both printed `backgrounded · <same id>`, exit 0. One process. One of the two messages in the transcript. |
| saved | 1.7–2.1 ms | 3 | Both printed the banner and `note: woke session … with its saved options`. One process. One message. |
| none | 105–108 ms | 3 | The original, plus a copy with "is already running in the background". Each message in its own transcript. |
| saved | 104–108 ms | 3 | The same: the original woke, the second became a copy. |

The lost messages were in no transcript under the config dir about ten minutes later. No pair left two processes on one id.

## 8. A terminal resume of a woken session (E4, E7)

**Measured.**
- **While the bg worker was live:** `claude --resume aef2131e` in a terminal re-executed as `<engine binary> attach aef2131e`. `ps` showed one session process, and `sessions/` and `claude agents --json` showed only the background pid.
- **After `claude stop`:** the same command ran `<engine binary> --resume <full id>` as `kind: "interactive"` under the same id, on the settings' default model (section 6).

## 9. The engine's own records of a woken session

**Measured.** Session `0279aad9` was opened in the terminal in `<scratch>/d/o` and exited. It was then resumed from `<scratch>/d/w` with `--permission-mode auto --model haiku -- "<msg>"`. Its `sessions/<pid>.json`:

    {"pid":99214,"sessionId":"0279aad9","cwd":"<scratch>/d/w","startedAt":1795170250467,
     "procStart":"Fri Nov 20 10:22:57 2026","version":"2.1.329","peerProtocol":1,
     "peerFeatures":["notify_idle","reply_across_default_dirs","artifact_yield"],"kind":"bg",
     "entrypoint":"cli","pidDomain":"darwin","asksForConvertedSkills":null,
     "messagingSocketPath":"/tmp/cc-socks/99214.sock","name":"<the message text>",
     "nameSince":…,"jobId":"0279aad9","updatedAt":…}

- **The record changes as it runs.** `name` became the generated title, with `nameSource: "auto"`, and `status`/`statusUpdatedAt` (plus `waitingFor` when blocked) were added.
- **A key file beside it.** Each record has a `sessions/<pid>.<64 hex>.key` (mode 0600, 108 bytes).
- **`startedAt` vs `procStart`.** `startedAt` is the claim time; `procStart` is when the pre-started spare process began, 73 s earlier (E16 holds).
- **The worker's argument vector** (`ps -o args=`) is `claude bg-spare --bg-spare /tmp/cc-daemon-<uid>/<hash>/spare/<x>.claim.sock`. It names neither the session nor its options.
- **Timing.** The record and the socket existed by the moment the command returned (3.5–3.7 s in these trials, 0.7–0.9 s in others). The order is in section 15.

**Measured: lingering (question 13).** After its turn ended the worker stayed up, with its record and socket in place, `status: "idle"` in the record and `state: "done", status: "idle"` with a `pid` in `claude agents --json --all`:
- The first woken worker was still up 24 minutes after its turn ended, at its last check before cleanup.
- Two others were still up 6 and 9 minutes after their turns (one at cleanup, one when stopped).
- No worker exited on its own while observed. They ended only on `claude stop` / `claude rm`. Each time, the record and the socket disappeared with the process.

## 10. The environment of a wake (E11)

**Measured.** The wake came from `<scratch>/d/w` with `T2WAKE=yes`, `CLAUDE_CODE_SESSION_ID=deadbeef-…`, `ANTHROPIC_API_KEY=<dummy>` and an extra `PATH` entry. The session had been opened in `<scratch>/d/o`. The woken turn's Bash printed:

    <scratch>/d/w
    WAKE=unset SID=0279aad9 KEY=
    <scratch>/wakebin:<scratch>/bin:/usr/bin:/bin:/usr/sbin:/sbin

So:
- It runs in the waking directory, and the row saves it as `cwd`.
- The waking shell's `PATH` is kept.
- The marker and `ANTHROPIC_API_KEY` are not passed.
- `CLAUDE_CODE_SESSION_ID` is the woken session's own id, not the waker's value.

The terminal launch's `--settings` env was also absent (section 2's B trial: `SET=unset` where the wake passed no `--settings`).

## 11. Where the message goes when a variadic option is passed

**Measured.**
- **Wrong:** `claude --bg --resume <id> … --add-dir <dir> "<msg>"`. Exit 0, banner `backgrounded · 97746c13 (idle — send a prompt to start)`, and on stderr:

      "Use the Bash tool to run exactly: pwd; …" was read as a value of --add-dir, not as a prompt, so the session starts with no prompt: put a prompt before --add-dir or after --

  The worker started idle, and the row saved the message, resolved against the directory, as a second `--add-dir` value.
- **These worked,** each running the message as the first turn:

      claude --bg --resume <id> "<msg>" --permission-mode acceptEdits --model haiku --add-dir <dir>
      claude --bg --resume <id> --permission-mode bypassPermissions --model haiku --add-dir <dir> -- "<msg>"
      claude --bg --resume <id> --permission-mode bypassPermissions --add-dir <dir> --model haiku "<msg>"

  `-- "<msg>"` last is the order that does not depend on which option comes last.

## 12. `claude respawn`

**Read:** `Usage: claude respawn <id>|--all — Restart a background session (or all of them) so it picks up the current Claude binary.`

**Measured.** On a live session (pid 22999) it printed `restarted 354a0e73` (exit 0). A new worker (pid 30765) came up under the same session id, and `respawnFlags` was unchanged. No turn ran: the last transcript row was unchanged, and the worker was idle. On a stopped session it did the same: a new idle worker under the same id.

**Inferred.** It behaves as a flagless, message-less background resume under the row.

## 14. A background resume with no message

**Measured.** `claude --bg --resume e499b6be --permission-mode auto --model haiku` with nothing after it, on a session that had only run in a terminal:
- **The command:** exit 0, `backgrounded · e499b6be (idle — send a prompt to start)`.
- **The worker:** it started for the same id and sat idle with a messaging socket. No turn ran: the transcript was byte-for-byte unchanged.
- **The row:** `state: "working"`, `detail: "(idle — send a prompt to start)"`, `needs`, `respawnFlags: ["--permission-mode","auto","--model","haiku"]`.
- **`claude agents --json --all`:** `{"pid":9710,…,"name":"term-j","status":"idle","state":"blocked"}`.
- **`sessions/9710.json`:** `kind: "bg"`, `status: "idle"`, `name: "term-j"`, `nameSource: "user"`.
- **The flags took effect.** The first turn, pushed through the socket (section 16), ran `permissionMode: "auto"` on haiku-5-5, not the settings' acceptEdits / haiku-4-5.
- **How long it stays up:** it lingered as in section 9 until stopped.
- **A later message-less resume** (`claude --bg --resume <id>`, row present) printed `note: woke session e499b6be with its saved options (--permission-mode, --model).`

## 15. Evidence that a launch's prompt was admitted

**Measured**, seconds after the command was started (the order of the first two depends on poll resolution):

| Trial | `sessions/<pid>.json` and socket | command returned | `claude agents` row with pid | prompt row in transcript | turn ended |
|---|---|---|---|---|---|
| first resume, flags | ≤ 3.61 | 3.61 | 3.85 | 3.89 | 8.76 |
| later resume, row | 3.55 | 3.72 | 3.72 | 4.26 | 5.49 |
| first resume, no row | 3.68 | 3.87 | 3.80 | 4.25 | 6.94 |

So:
- The record and the socket appear first, before or as the command returns.
- The job list shows the pid within about 0.2 s of the return.
- The prompt row lands 0.3 to 0.5 s after the return.

**Measured: a worker that fails before it starts.** See section 5: the transcript is unchanged; the job list says `state: "failed"` with no `detail`; the row says `state: "failed"`, `detail: "exit 1 before init — error: unknown option '--output-style'"`.

**Measured: copies.**
- A copy's own transcript (seeded with the original's history) held the new prompt 0.33 s after the command returned.
- `claude rm <copy>` issued right at the return (0.7 s after it) came too late: the prompt was already in the copy's transcript, though no reply had been written.
- `claude rm <copy>` while the copy was mid-turn (prompt written, no reply yet) returned `removed <copy>` with exit 0, and stopped the worker before it replied.

## 16. Handing a prompt to a live background session

**Read.** There is no `send` command in `claude --help`; `attach` and `logs` take no input. The installed program addresses peers as `uds:<socket path>` (the SendMessage tool's peer addressing). The socket handler reads a JSON line, refuses one whose `session_id` does not match, and delivers it as a message with `origin.kind: "peer"` (priority `next` when unset).

**Measured.** One JSON line written to `/tmp/cc-socks/<pid>.sock` was admitted and ran a turn:

    {"type":"user","message":{"role":"user","content":"Reply with just the word SOCKET."},"session_id":"<full id>","from":"spike"}

The prompt row reads `Another Claude session sent a message:\n<text>\n\nThis came from another Claude session — not typed by your user, …`, with `isMeta: true` and `origin: {"kind":"peer","from":"spike","verifiedPeerPid":<pid>}`.

A line sent the instant the socket appeared, 0.18 s before the launching `claude --bg --resume <id>` command had returned, was admitted and answered: it was queued, not lost. That was one trial.

## Also: `/background` inside a terminal session

**Measured.** `/background` ("Send this session to the background and free the terminal") in a live terminal session `4497cc3d`:
- The terminal process exited and printed `backgrounded · 4f593715`.
- The background session has a **new id**. Its row (`interactiveLineage: true`) saved `["--permission-mode","acceptEdits","--model","haiku"]`, the terminal's effective mode and its `--model`.
- Its transcript, written at its first turn, begins with a copy of the original's history; the model answered from it.
- The original id's transcript is unchanged, and the original id has no row.

## Differs from 2.1.327

Each is **measured** unless marked.

1. **E8:** a worker that fails before it starts leaves a row that keeps the flags the worker would have accepted (`["--model","haiku"]`), not `[]`.
2. **E8, E10:** the row is rewritten by `/model` and by a mode change inside an attached background session, at once and without a turn. A flagless resume then runs under what the session last used. "The engine changes a row only by removing it" no longer holds for changes made inside a background process. A terminal (`kind: interactive`) process still does not change the row.
3. **E12:** `--add-dir` naming a directory that is not trusted is refused (exit 1, no row). *Possibly not a version change:* the earlier spikes ran under a home whose directories were trusted.
4. **E12, new:** a message placed right after `--add-dir <dir>` is taken as a directory. The engine now says so on stderr and starts the worker idle (`(idle — send a prompt to start)`), saving the message as an `--add-dir` value.
5. **E2, new:** `bypassPermissions` on `--bg` needs the bypass disclaimer accepted (`skipDangerousModePermissionPrompt`); without it, exit 1 and no row, whichever bypass flag is used.
6. **E14:** the note texts are unchanged. The banner of a resume of a named session now carries the name (`backgrounded · <id> · <name>`), and a resume without a prompt says `(idle — send a prompt to start)`. The supervisor's first start prints `Starting background service…` on stderr.
7. **E12 (`-n`):** a first background resume with a message replaces the session's name with a generated title (`nameSource: "auto"`). Without a message the terminal's name is kept.
8. **E3, new:** a copy started because the session is already running runs under the settings' defaults, not the row's options.
9. **E13:** pairs about 2 ms apart (not 0.1 ms) still lost one message while both reported success. The pattern is otherwise as before, now three of three in each of four cases.
10. **E14:** `permission-mode` metadata rows in the transcript are stale at a bg process start. Read the prompt row's `permissionMode`, as before.
11. **Read:** `--permission-mode` no longer lists `default` (it is still accepted). `manual` is written as `default` in transcripts and rows.
12. **The terminal's exit hint** now carries its launch flags: `claude --model haiku --permission-mode manual --resume <id>`.

E1 was not re-run as such: every wake here passed flags or had a row. E4, E5 (minus the sminos socket: no sminos in the scratch config), E6, E7, E9, E10 (terminal side), E11 and E16 held.

## Not established

- **Whether a woken worker ever exits on its own:** the longest observation was 24 minutes idle.
- **Whether a first resume of a session whose row has accepted flags but `state: "failed"` runs under them without flags** (section 5, inferred).
- **The exact width of the race window.** The close pairs were 1.7–2.6 ms apart; 0.1 ms was not reached.
- **Whether a socket push during a worker's start is always queued:** one trial.

## Cleanup

All 20 scratch background sessions and copies were removed with `claude rm` under the scratch config. `claude agents --json --all` then listed none. The scratch tmux server and the liveness loggers were killed. The scratch supervisor had already exited with its spares; no process naming its spare directory remained, and that directory was removed. The scratch config's `.claude.json` (it held the trust entries), its `backups/` and the scratch daemon's `auth` and `control.key` were deleted. No scratch file held the gateway token (checked by search). Left on that Mac is `<scratch>/`: the scratch sessions' transcripts, the scratch directories, the wrapper and the helper scripts.
