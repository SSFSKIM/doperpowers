---
name: codex-companion
description: Use when work should go to the Codex runtime — an independent or second-opinion code review, an adversarial or lens-focused challenge review of a diff or branch, delegating diagnosis, research, or implementation to Codex (GPT) models, resuming a prior Codex thread, or when another skill or CLAUDE.md routes a review to codex.
---

# Codex Companion

A vendored copy of OpenAI's Codex companion runtime (`runtime/`, from the
codex-plugin-cc plugin — see `runtime/VENDORED-FROM`). You drive it
directly with Bash; there is no subagent, slash command, or hook in the
path. It needs the `codex` CLI installed and authenticated on this
machine (the `setup` verb diagnoses both).

Every invocation follows one shape — `<skill-base>` is this skill's base
directory, printed when the skill loads:

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:$HOME/.claude/doperpowers/codex-companion/no-broker.sock" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" <verb> [flags…]

Both env vars are mandatory. `CLAUDE_PLUGIN_DATA` pins where job state and
resumable threads live — unset, the runtime falls back to a purgeable
tmpdir, and a leftover OpenAI-plugin hook can silently redirect it.
`CODEX_COMPANION_APP_SERVER_ENDPOINT` points at a socket that never
exists, which forces the per-call direct app-server path — without it,
every review/task spawns a detached broker + codex process pair that
outlives the session (the upstream plugin cleaned these up with a
SessionEnd hook this bundle deliberately does not have; we observed ~30
leaked pairs before adopting this kill-switch). references/jobs.md has
the details on both.

Verbs, and where each is specified:

- `review` — Codex's native code review of the working tree or a branch
  (`--base <ref>`); non-steerable by design → references/reviews.md
- `adversarial-review` — challenge review of design and assumptions;
  trailing text is a lens, parallel lenses for big diffs → references/reviews.md
- `task` — any prompt to a resumable Codex thread; one-shot delegation
  or a standing multi-turn partner (critique debates, steered execution);
  read-only unless `--write` → references/amigo.md
- `status` / `result` / `cancel` — job history and backgrounding
  mechanics (background Bash detaches and auto-wakes; don't poll) → references/jobs.md
- `setup` — preflight: is codex installed and authenticated?

Two standing rules. Never patch anything under `runtime/` — it is
byte-identical to upstream so bugfix releases import as a clean diff;
behavior changes belong at the call site (flags, env) or in these docs.
And reviews are advisory input to your own judgment: read the findings,
adopt what survives scrutiny, and never present Codex output as your own
analysis.
