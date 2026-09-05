---
name: codex-companion
description: Use when work should go to the Codex runtime — an independent or second-opinion review, delegating diagnosis, research, or implementation to Codex (GPT) models.
---

# Codex Companion

OpenAI's Codex companion runtime (`runtime/`). You drive it
directly with Bash; It needs the `codex` CLI installed and authenticated on this
machine (the `setup` verb diagnoses both).

## Model routing

Set both model and effort explicitly wherever the invocation surface supports
them. Route by the hardest judgment the delegated work requires; lower tier
numbers mean greater capability.

| Tier | Model and effort | Use |
|---|---|---|
| 0 | `gpt-6-astra` at `high` or `xhigh` | Absolute frontier intelligence for the most ambitious work. Default to `high`; reserve `xhigh` for the most important assignments because the difference is marginal. |
| 1 | `gpt-6-astra` at `medium` or `gpt-5.6-sol` at `xhigh` | Near-frontier intelligence for complex work. Prefer Sol when its marginal cost advantage matters. |
| 2 | `gpt-5.6-sol` at `high` | Trusted execution worker for well-defined, well-scoped tasks. |
| 3 | `gpt-5.6-luna` at `max` | Extremely cost-efficient worker for mechanical work and large-scale fan-out. |

`task` accepts `--model` and efforts through `xhigh` directly. For Tier 3,
wrap `task --model gpt-5.6-luna` with `scripts/with-effort.mjs --effort max`;
the vendored task parser predates `max`, while the wrapper applies it at the
app-server call site. For `review` and `adversarial-review`, pass `--model` to
the verb and set effort through the same wrapper. Workflow scripts set both on
each `agent` or `review` call; the bundled code-review panel deliberately
defaults to Tier 0.

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
pairs had leaked forever before the broker learned to self-reap after
30 minutes with no client); pointing it at a socket that never exists
forces the per-call direct path, so nothing detached spawns at all. Leave it OFF
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
  via the `scripts/with-effort.mjs` wrapper; big diffs (~20+ files) route
  to the `workflow` code-review panel instead → references/reviews.md
- `adversarial-review` — challenge review of design and assumptions;
  trailing text is a lens, parallel lenses for big diffs → references/reviews.md
- `task` — any prompt to a resumable Codex thread; one-shot delegation
  or a standing multi-turn partner (critique debates, steered execution);
  read-only unless `--write` (which includes guardian-reviewed escalation)
  → references/amigo.md
- `workflow` — run a JS orchestration script fanning out Codex workers
  (agents + native reviews) as ONE process; read-only, resumable
  → references/workflows.md
- `watch` — live progress tree for a workflow run (or a post-mortem
  snapshot); read-only, attach from any terminal → references/workflows.md
- `status` / `result` / `cancel` — job history and backgrounding
  mechanics → references/jobs.md
- `setup` — is codex installed and authenticated (assume it is in most case. diagnose only when blocked)?
