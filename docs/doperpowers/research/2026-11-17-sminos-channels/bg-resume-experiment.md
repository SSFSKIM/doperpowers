# Experiment: background resume of terminal-opened sessions (2026-11-17, on a Mac)

> Research for `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md` (its section on the wake).
> Session ids are shortened to their first eight characters.

Engine: `claude --version` -> `2.1.326 (Claude Code)`. sminos CLI 1.47.0 from the plugin cache.
Load average during the run: 38-42. One scratch session at a time, isolated tmux server (`tmux -L bgrspike`),
env stripped of the calling session's vars (a small wrapper script).
Three scratch directories under the home directory, `bgr`, `bgr2`, `bgr3` (no trust dialog: the home directory is trusted and the directories are not git repositories).
Settings that matter: `~/.claude/settings.json` has `permissions.defaultMode: "auto"` and `model: "opus"`.
`S` below is the sminos CLI.

Sessions used: A `4b7eecde` (bgr, launched `claude --permission-mode manual --model haiku -n spike-bgr`),
B `6635007d` (bgr2, project `.claude/settings.local.json` = `{"permissions":{"defaultMode":"default"}}`, launched `claude --model haiku`),
C `428cb53b` (bgr3, launched `claude --permission-mode manual --model haiku`). Each got one prompt, then `/exit`.

## Q1. Background resume of a terminal-opened session

A, after `/exit` (process 78632 gone, `sessions/78632.json` gone, bridge socket gone):
```
$ claude --bg --resume 4b7eecde "Use the Bash tool to run exactly: touch approval-probe.txt  — then reply DONE."
backgrounded · 4b7eecde
```
Same session id, no copy. `claude agents --json`: `{"pid":89093,"id":"4b7eecde","kind":"background","sessionId":"4b7eecde","state":"working"}`.
The process was a pre-warmed spare: `ps` -> `89093 ... claude bg-spare --bg-spare /tmp/cc-daemon-501/.../spare/790fb414.claim.sock`, started a minute before the resume.

Mode and model of the resumed process: NOT the terminal launch's (`manual`, haiku). `claude logs` banner: `Opus 5.5 with high effort` ... `⏵⏵ auto mode on`.
```
$ S read spike-bgr status   ->  "model": "claude-opus-5-5", "permissionMode": "auto"
transcript permissionMode fields: "default" x6 (terminal turns), then {"type":"user","ts":"2026-11-17T09:49:00.935Z","permissionMode":"auto"}
```
`touch` ran without a prompt (auto mode). So the first background resume of a never-backgrounded session takes the
settings defaults (`defaultMode`, `model`), not the options the terminal process was launched with.

Confirmed with B (project settings `defaultMode: "default"`), resumed with no flags:
```
$ claude --bg --resume 6635007d "Use the Bash tool to run exactly: touch probe-3.txt ..."
backgrounded · 6635007d
claude agents --json -> "status":"waiting","waitingFor":"permission prompt","state":"blocked"
S read 6635007d status -> {"model":"claude-opus-5-5","permissionMode":"default","permissionModeFrom":"PermissionRequest"}
```
When a tool call needs approval, the process waits: state `blocked`, `waitingFor: "permission prompt"`. C stayed blocked
from 09:58:56Z to 10:04:23Z (about 5.5 min) and was still answerable; no timeout observed (longer waits not tested).
The request is visible and answerable from outside:
```
$ S watch 6635007d
· watching session 6635007d (bridge pid 83911)
· [main] permission: Bash touch probe-3.txt — request <request id>
$ S decide 6635007d <request id> deny --message "spike: denied on purpose"
6635007d: request <request id> settled from here: deny
(watch) · request ... settled: deny (cli)
        ⎿ [main] Bash failed: spike: denied on purpose
        · [main] turn ended: answer
```
Allow path (on copy 78aedefa, see Q2): `S decide 78aedefa <request id> allow` (prefix) -> `settled from here: allow`; `approval-probe-2.txt` was created; watch: `settled: allow (cli)`, `turn ended: answer`.
`watch` prints a request already pending when it starts (both tests started watch after the prompt was raised).

Answer: works, same id. Mode = settings `defaultMode` (auto on this Mac), model = settings `model`; the terminal launch's flags are lost.
In a mode that prompts, the turn blocks (seen up to ~5.5 min) and `sminos watch` / `sminos decide` see and settle it (allow and deny both verified).

## Q2. A flag on resume

Two different results, depending on whether the session has ever run in the background.

Already backgrounded (A, after its bg process was stopped):
```
$ claude --bg --resume 4b7eecde --permission-mode manual "Use the Bash tool ... touch approval-probe-2.txt ..."
note: background session 4b7eecde keeps its own saved options, so the flags you passed started a copy as 78aedefa. Without flags, the same command continues 4b7eecde itself.
backgrounded · 78aedefa
```
Copy under a new id (`78aedefa`, own transcript); the copy did run in the flagged mode (blocked on the prompt, `permissionMode: "default"`).

Never backgrounded (C, first background resume after `/exit`):
```
$ claude --bg --resume 428cb53b --permission-mode manual --model haiku "Use the Bash tool ... touch probe-4.txt ..."
backgrounded · 428cb53b
S read 428cb53b status -> {"model":"claude-haiku-5-5","permissionMode":"default"}
```
Same id, no copy, flags applied. They then became the saved options:
```
$ claude stop 428cb53b; claude --bg --resume 428cb53b "Reply with just the word AGAIN."
note: woke session 428cb53b with its saved options (--permission-mode, --model).
S read 428cb53b status -> {"model":"claude-haiku-5-5","permissionMode":"default"}
```
Answer: still a copy for a session that has background saved options (v2.1.257 behaviour holds on 2.1.326).
The FIRST background resume of a terminal-only session accepts flags under the same id and records them as its saved options;
so sminos could pass `--permission-mode auto` (or anything) on that first wake only, and must pass none afterwards.
How the engine decides "has saved options" (a terminal session resumed in the terminal after being backgrounded, then exited, then woken again) was not tested.

## Q3. Two processes

(a) Background process live, then terminal `claude --resume <id>` (A, bg pid 89093 live):
```
$ claude --resume 4b7eecde      (in tmux)
ps on the pane's tty:  9209 9203 claude attach 4b7eecde
```
The engine re-execs it as `claude attach`: no second process; `sessions/` and `claude agents --json` show only pid 89093.
A prompt typed in that terminal ("Reply with just the word ATTACHED.") was answered by 89093 into the same transcript.
`claude -r <id>` behaved the same (`42148 ... claude attach 4b7eecde`).

(b) Terminal process live, then `claude --bg --resume <id>` (A, interactive pid 78632 live, no flags):
```
note: session 4b7eecde is open in another Claude Code process, so this started a copy as 70159b35. The original conversation is unchanged.
backgrounded · 70159b35
```
Copy under new id `70159b35` with its own transcript. Same with a live background process (C, bg pid 36186):
```
note: session 428cb53b is already running in the background, so this started a copy as 85f8536f. `claude attach 428cb53b` opens the original.
```
So `claude --bg --resume` never makes a twin of one id now; it makes a copy and says so (sminos already parses "started a copy as").

(c) Not asked, but it is the remaining twin hazard: terminal process live, then a second terminal `claude --resume <id>` (C, interactive pid 51409 live):
second process 56754 `claude --resume 428cb53b` started, no warning shown; `claude agents --json` then listed two `"kind":"interactive"` rows,
pids 51409 and 56754, same sessionId. Only one sminos bridge process/socket for the id was found. The twin hazard is live only for interactive+interactive.

What a guard can read before a launch (all observed during the runs):
- `claude agents --json`: lists interactive sessions too (`{"pid":78632,"kind":"interactive","sessionId":"4b7eecde","status":"idle"}`), plus background rows with `id`, `pid`, `state`; a stopped bg session drops out of the default list (`--all` shows it with `pid: null`).
- `~/.claude/sessions/<pid>.json`: `sessionId`, `kind` ("interactive" or "bg"), `jobId` for bg, `tmux` pane for a tmux session, `status`; it was removed when the process exited (78632.json gone after `/exit`).
- `~/.claude/sminos/bridge/<sessionId>.sock`: present while the process ran, gone after exit (A).
All three agreed in every check. sminos's `running_now` already reads the `sessions/` records.

## Q4. Taking over

`claude attach <short|name>` is the engine's way (help: "Open the background session in this terminal. ← returns to agent view, Ctrl+Z drops back to your shell. The session keeps running either way.").
- Live bg process: `claude --resume <id>`, `claude -r <id>` and `claude attach` all end up as `claude attach <short>` against the one process (Q3a). Killing the attaching terminal left the bg process running.
- Stopped bg session: `claude attach 428cb53b` restarted it as a background process (new pid 36186, `kind: background`) under its saved options (`⏸ manual mode on`, Haiku) and attached: one process.
- Stopped bg session: `claude --resume 428cb53b` in a terminal instead starts an ordinary interactive process (pid 51409, `kind: interactive`) under the interactive defaults (`⏵⏵ auto mode on`, Opus), same id.
`sminos attach` was not tried (not in `sminos --help` output read here).

## Not established
- Whether a blocked permission prompt ever times out (longest observed wait ~5.5 min).
- Whether a notification reaches the human for a blocked background prompt (only the bridge watch and `claude agents` status were read).
- First-wake flag acceptance for a session that was backgrounded once and later used interactively; and on a machine without `defaultMode: auto`, behaviour was emulated with a project `settings.local.json`, not a different user config.
- Which of the twin processes in Q3c owns the bridge socket.

## Cleanup
All processes I started ended (`claude stop` / `/exit`; tmux server `bgrspike` killed). Copies 70159b35, 78aedefa, 85f8536f stopped and `claude rm`'d; rows 4b7eecde, 6635007d, 428cb53b `claude rm`'d.
The scratch sessions were seat-less members of the machine project; once their processes ended `sminos retire <id>` answered `no seat or member matching '<id>'` for each, so nothing to retire.
Left behind on that Mac: the scratch sessions' transcripts, their sminos launch and session records, and the scratch directories.
