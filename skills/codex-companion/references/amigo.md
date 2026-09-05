# Amigo: `task`

An arbitrary prompt to a Codex thread in this workspace — and because
threads resume, this is more than one-shot delegation: it is a standing
partner. One-shot uses: diagnosis, research, implementation, a
second-opinion pass. Resumed uses: a design critique partner you debate
over multiple turns, a rescue thread that digs deeper on request, an
executor you steer mid-task. Prints Codex's final response; records a job
(see references/jobs.md).

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
    CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:$HOME/.claude/doperpowers/codex-companion/no-broker.sock" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" task \
      [--write] [--resume-last|--fresh] \
      [--model <m|spark>] [--effort none|minimal|low|medium|high|xhigh] \
      [--prompt-file <path>] -- [prompt text]

The `--` before inline prompt text is load-bearing: a prompt passed as one
quoted argument gets re-tokenized, so flag-like words inside it become
real flags — observed: `task 'explain why --write must be opt-in'` parsed
as `write: true` with the token stripped from the prompt, silently
granting edit permission. `--` stops flag parsing and keeps the prompt
intact; `--prompt-file` avoids the issue entirely. And don't use the
runtime's own `--background` flag here — it spawns a detached worker with
a persist-after-spawn race that can strand the job as "queued" forever;
for a long task, background the whole foreground command with harness
Bash instead (references/jobs.md). Codex's answer is stdout-only — send
stderr to a scratch file (`2> …`) so an exploration-heavy turn's streamed
progress doesn't multiply what you read back.

- Read-only by default. `--write` lets Codex edit the working tree — pass
  it only when edits are the point (a fix, an implementation), not for
  review/diagnosis/research. A `--write` task runs Codex's Auto preset:
  actions that cross the sandbox (network, files outside the workspace,
  escalated commands) are judged by Codex's built-in auto-review guardian
  instead of failing outright. A denial comes back in the answer — Codex
  is told to take a safer path or stop and ask.
- Choose `--model` and `--effort` from the routing table in SKILL.md. Left
  unset, both defer to the user's codex `config.toml`.
- Tier 3's `max` effort is newer than the vendored task parser. Apply it at
  the call site instead:

      node "<skill-base>/scripts/with-effort.mjs" --effort max -- \
        task --model gpt-5.6-luna -- [prompt text]

  Omit the task verb's own `--effort`; the private app-server supplies `max`.
- Long or structured prompts go in a file via `--prompt-file` instead of
  fighting shell quoting.

The multi-turn loop: run once, read the answer, continue the same thread
with `--resume-last` and a follow-up prompt — challenge its critique,
narrow its focus, ask it to apply the fix it proposed (add `--write` on
the resumed turn). `--resume-last` picks this session's most recent task
thread (`--resume` is an accepted synonym) — session-scoped by the
`CODEX_COMPANION_SESSION_ID` prefix, so parallel sessions in the same
workspace can't grab each other's threads or trip over each other's
running tasks; to continue *another* session's thread, take the Codex
session id that `result <job-id>` prints and open it with
`codex resume <id>` (there is no per-thread flag on `task`). `--fresh`
forces a new thread when the request merely sounds like a follow-up.

## Computer use

Codex's computer-use stack rides into task threads: the app-server path
loads whatever plugins the user's codex install has enabled (the bundled
`computer-use` and `browser` plugins run through the `node_repl`
code-mode host), and nothing here strips them. Three things gate whether
desktop control actually works headless:

- `--write` is required. The read-only default's `approvalPolicy: never`
  auto-denies the per-app Computer Use approval, so every desktop action
  dies with "not approved" regardless of what the prompt says.
- Codex must run its computer-use plugin skill's bootstrap
  (`setupComputerUseRuntime`) before `sky.*` exists — left unprompted it
  can skip it and report `sky is not defined`. The REPL global dies with
  the turn: a resumed thread gets a fresh app-server and fresh
  node_repl, so tell it to re-bootstrap every turn.
- First approval for an app the service hasn't seen can block forever —
  the approval UI belongs to the desktop app, and this client implements
  no permission callback. If a call hangs, have your human partner
  approve that app once in an interactive Codex session; for browser
  work prefer the Chrome plugin (`agent.browsers.get("chrome")`) over
  Computer Use, as Codex's own instructions direct.

A capture of an app with no open window fails with the opaque
`Computer Use server error -10005: cgWindowNotFound` — target something
visible, not a windowless background app.

## As design critic

doperpowers:brainstorming's peer-review layer routes technical-heavy
designs here (product/judgment-heavy ones go to the doperpowers:critique
agent). The opening prompt carries the charge and the pointers — Codex
explores the repo itself, so paths beat pasted content:

    …you are an independent peer reviewer for a matured design. Read
    <design doc path> and its reasoning, explore the codebase it touches,
    and attack the blind spots: alternatives nobody named, decisions made
    before knowing enough. Order findings by what would change the
    decision; say plainly what is sound.

Then debate over `--resume-last`: adopt what survives your scrutiny,
rebut what doesn't, and hold the thread until it converges. A
disagreement that survives honest debate goes to the human partner as an
open question, not another round. Keep the critic read-only — never
`--write` in this role.
