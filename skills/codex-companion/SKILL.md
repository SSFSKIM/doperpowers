---
name: codex-companion
description: Use when work should go to the Codex runtime — an independent or second-opinion review, delegating diagnosis, research, or implementation to Codex (GPT) models.
---

# Codex Companion

OpenAI's Codex companion runtime (`runtime/`). You drive it
directly with Bash; It needs the `codex` CLI installed and authenticated on this
machine (the `setup` verb diagnoses both).

Every invocation follows one shape — `<skill-base>` is this skill's base
directory, printed when the skill loads:

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
    CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:$HOME/.claude/doperpowers/codex-companion/no-broker.sock" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" <verb> [flags…]

`CLAUDE_PLUGIN_DATA` goes on every verb: it pins where job state and
resumable threads live — unset, the runtime falls back to a purgeable
tmpdir, and a leftover OpenAI-plugin hook can silently redirect it.
`CODEX_COMPANION_SESSION_ID` also goes on every verb: it stamps this
session's jobs and scopes listings, no-id `result`, `--resume-last`,
and the running-task gate to them. Without it, parallel sessions in the
same workspace share one job namespace — a session gets "Task … is
still running" off a neighbor's task (or a killed session's record,
which stays `running` forever), and no-id reads land on whichever job
is newest workspace-wide. An explicit job id still reaches any
session's job.
`CODEX_COMPANION_APP_SERVER_ENDPOINT` goes on `review`,
`adversarial-review`, and `task` only — those verbs otherwise spawn a
detached broker + codex process pair that outlives the session (upstream
reaped these with a SessionEnd hook this bundle deliberately lacks; ~30
leaked pairs observed before this kill-switch); pointing it at a socket
that never exists forces the per-call direct path. Leave it OFF
`setup`/`status`/`result`/`cancel`: they never spawn a broker, and
`setup`'s auth probe has no direct fallback, so the dead endpoint makes
it misreport auth failure. references/jobs.md has the details on both.

Work-verb output is split by stream: stdout carries only the final
rendered result, written after the turn completes; stderr streams
`[codex]` progress — a line per command Codex runs, plus a truncated
copy of the final answer — which on a real run dwarfs the verdict.
Redirect it (`2> <scratch>.events.log`) so what you read back is just
the result. The same progress persists in the job log, and errors also
land on stderr, so keep the file and check it only on a nonzero exit.

Verbs, and where each is specified:

- `review` — Codex's native code review of the working tree or a branch
  (`--base <ref>`); non-steerable by design; reasoning effort is choosable
  via the `scripts/with-effort.mjs` wrapper → references/reviews.md
- `adversarial-review` — challenge review of design and assumptions;
  trailing text is a lens, parallel lenses for big diffs → references/reviews.md
- `task` — any prompt to a resumable Codex thread; one-shot delegation
  or a standing multi-turn partner (critique debates, steered execution);
  read-only unless `--write` → references/amigo.md
- `workflow` — run a JS orchestration script fanning out codex workers
  (agents + native reviews) as ONE process; read-only, resumable
  → references/workflows.md
- `status` / `result` / `cancel` — job history and backgrounding
  mechanics → references/jobs.md
- `setup` — is codex installed and authenticated (assume it is in most case. diagnose only when blocked)?