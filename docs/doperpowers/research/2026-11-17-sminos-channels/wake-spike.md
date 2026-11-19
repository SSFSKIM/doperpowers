# What the engine keeps of a background session, and what a second resume does (2026-11-18)

> Research for `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md` (its section on the wake, and the first row of its Delegated unknowns).
> Session ids are shortened to their first eight characters.

Claude Code 2.1.327, on a Mac. The method of `bg-resume-experiment.md`: scratch sessions in scratch directories, one at a time, in an isolated terminal multiplexer with the caller's environment stripped, on the cheapest models. A scratch `.claude/settings.local.json` set the directory's defaults (`acceptEdits`, one model) so that they differed from what each terminal launch passed. Each claim below is **measured** (seen in a trial), **read** (from the engine's help text or its installed program, not exercised) or **inferred**.

E1, E2 and E3 of the first experiment held on this version.

## 1. Where the saved options are

**Measured.** The engine keeps one directory per background session, `jobs/<first eight of the id>/` under its configuration directory, with a `state.json` that names the full `sessionId`. A session that has only run in a terminal has none. A fresh `--bg` launch writes it, and so does a first background resume. Its `respawnFlags` is the list of options the launch passed, for example

    ["-n", "<name>", "--permission-mode", "manual", "--effort", "low", "--settings", "<file>", "--model", "haiku"]

and beside it are `cwd`, `providerEnv` (selected variables, not the launching shell's environment), `name`, and where they apply `sessionPermissionRules`, `worktreePath`, `worktreeBranch` and `worktreeHookBased`.

**Measured.** A background launch whose worker failed before it started (`state: "failed"`, `detail: "exit 1 before init"`) still left the row, with `respawnFlags: []`. The next resume with a flag started a copy: "keeps its own saved options, so the flags you passed started a copy".

**Read.** The engine's test is that a readable row for the session exists, not that the row holds any option or that a turn completed.

**Not established:** every writer of the row (an in-session `/background` was not tried); whether a `/model` or a mode change made inside an attached background session rewrites `respawnFlags`; the layout on an engine with another backend.

## 2. Losing them

**Measured.** `claude rm <id>` removed the session's job directory, stopped a live worker and removed its process record, and kept the transcript. A flagged background resume afterwards (`--permission-mode manual --model <id>`) continued the same session id with no copy note, and wrote a new row with those flags. `rm` also deletes the session's worktree when the engine judges that safe (its help text: "If it's safe, remove a background session from the list and delete its worktree. Its conversation is kept"); with a hook-made worktree and no removal hook it refused until the directory was gone.

**Read.** The engine's cleanup removes job directories whose files are older than `cleanupPeriodDays` (30 when unset), live and pinned ones excepted; transcripts are kept on a rule of their own. The lapse itself was not observed.

## 3. What a first background resume accepts

Each trial began with the session stopped and no row. Unless noted, the command answered `backgrounded · <the same id>` with no copy note. The answer alone proves neither that the worker started nor that the option took effect, so each was checked in the resumed session.

| Option | Result |
|---|---|
| `--permission-mode`, `--model` | In effect: the turn's row has `permissionMode: "default"` for `manual`; the request names the model passed. |
| `-n <name>` | In effect: the session's title and agent name. |
| `--settings <file>` and `--settings '<json>'` with an `env` block | In effect: the variable is set in the session's Bash calls. |
| `--effort <level>` | In effect: the request's effort. |
| `--add-dir <dir>` | In effect: a write there ran without a prompt. |
| `--worktree` | In an untrusted git directory: exit 1, "Workspace not trusted". With a worktree hook: same id, and the turn ran in the hook's directory, saved as `worktreePath`. |
| `--append-system-prompt`, `--system-prompt`, `--agent`, `--tools`, `--disallowedTools`, an `outputStyle` in `--settings` | Saved. In effect only when the session's saved system prompt and tool list are rebuilt (`--system-prompt-snapshot off`); without that the resumed session kept the old ones. |
| `--output-style <name>` | **Refused by the worker after the launcher answered success:** exit 0 and the banner, then the job `failed`, "unknown option '--output-style'", and an empty row left (section 1). |
| `--allowedTools`, `--mcp-config` with `--strict-mcp-config`, `--setting-sources`, `--autocompact`, `--fallback-model`, `--disable-slash-commands` | Same id, saved in `respawnFlags`; their effect was not checked. |

**Not established:** a `--worktree` resume in a trusted git repository; the options not listed.

## 4. Backgrounded, then used in a terminal

**Measured.** A session with a row (`manual`, model A) was reopened with `claude --resume <id>` in a terminal, switched to another model and to plan mode, ran a turn, and exited. Then:

- `claude --bg --resume <id> <message>` with no flag answered "woke session … with its saved options (--permission-mode, --model)", and the turn ran under `manual` and model A: the row's, not the terminal turn's and not the directory's defaults.
- The same with `--permission-mode` and `--model` started a copy.

So after a first background run, a flagless resume does not follow what the human last used in a terminal, and a flag cannot correct it.

## 5. Reading a turn's mode and model

**Measured.** In the transcript:

    {"type":"user","permissionMode":"plan","message":{"content":"…"}}
    {"type":"assistant","requestId":"req_…","message":{"model":"<model id>"}}

- The mode of a turn is `permissionMode` on the row of the prompt that began it. A mode change made with the mode key writes nothing until the next prompt.
- The model served is `message.model` on an assistant row whose `requestId` is set. Rows a plugin's hook writes also carry `message.model`, with `requestId: null` and a `message.id` beginning `msg_hook_`; they are not the session's turns. A `/model` change writes only the command's own rows until the next turn.
- A background turn writes the same fields as a terminal turn.
- In plan mode the model served was not the one the session had selected (a third model answered). The cause was not traced.

**Not established:** the option a session holds after a change that no turn followed.

## 6. The engine's notes of a copy

**Measured.** All three are on stderr; the banner `backgrounded · <short id>` is on stdout and names the copy; the exit status is 0.

    note: session <id> is open in another Claude Code process, so this started a copy as <copy>. The original conversation is unchanged.
    note: session <id> is already running in the background, so this started a copy as <copy>. `claude attach <id>` opens the original.
    note: background session <id> keeps its own saved options, so the flags you passed started a copy as <copy>. Without flags, the same command continues <id> itself.

The first two are a held session (a terminal process, a background process); the third is saved options. `claude stop <copy>` ends the copy's worker and keeps its row; `claude rm <copy>` removes the row too, on a live copy as well, and keeps whatever transcript the copy wrote. A `SIGTERM` to the worker removed its process record and left the row at `working`.

## 7. The environment and directory of a wake

**Measured.** A session was launched in a terminal in directory O with a marker variable in the shell, another through `--settings`, a `PATH` entry and an `--add-dir`, and exited. Its first background resume was issued from directory W, from a shell with other markers.

- The resumed session's Bash calls and its hooks ran in **W**, and the row saved W as `cwd`. The transcript stayed where it was. A later flagless resume issued from O still ran in W.
- Neither environment was inherited whole: the terminal's markers and the waking shell's marker were all unset; the waking shell's `PATH` entry was present, and on a later resume the `PATH` was the later caller's.
- The `--settings` variable of the terminal launch was unset, and the `--add-dir` grant was gone: the same write that had run in the terminal stopped at a permission prompt.

**Read.** A background launch is handed to the engine's supervisor, whose worker gets selected variables from the caller, `PATH` among them.

## 8. Two resumes at once

**Measured**, six pairs of `claude --bg --resume <id> <message>` on one stopped session:

| Row before | Started apart by | Afterwards |
|---|---|---|
| saved | 0.09 ms | one process; one of the two messages in the transcript |
| saved | 0.05 ms | one process; one of the two messages |
| saved | 105 ms | the original and a copy |
| none | 0.2 ms | one process; one of the two messages |
| none | 0.3 ms | one process; one of the two messages |
| none | 151 ms | the original and a copy |

In the four close pairs both commands printed the banner for the same id and exited 0. No trial left two background processes on one id.

**Not established:** the width of the window; whether the missing message would have appeared had the worker been left running longer.

## Also seen

A background session stopped at a permission prompt fired the `Notification` hook with `notification_type: "permission_prompt"`; whether anything reaches the person, and whether the prompt times out, were not established.

## Cleanup

Every scratch process ended, every scratch row and copy was removed with `claude rm`, and the multiplexer's server was killed. Left on that Mac: the scratch sessions' transcripts and the scratch directories.
