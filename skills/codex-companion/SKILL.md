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
      node "<skill-base>/runtime/scripts/codex-companion.mjs" <verb> [flags…]

The `CLAUDE_PLUGIN_DATA` prefix is mandatory: it pins where job state and
resumable threads live. Unset, the runtime falls back to a purgeable
tmpdir, and a leftover OpenAI-plugin hook can silently redirect it —
references/jobs.md has the details.

Verbs, and where each is specified:

- `review` — Codex's native code review of the working tree or a branch
  (`--base <ref>`); non-steerable by design → references/reviews.md
- `adversarial-review` — challenge review of design and assumptions;
  trailing text is a lens, parallel lenses for big diffs → references/reviews.md
- `task` — delegate any prompt; read-only unless `--write`; resumable
  threads make it a multi-turn partner → references/delegation.md
- `status` / `result` / `cancel` — job history and backgrounding
  mechanics (background Bash detaches and auto-wakes; don't poll) → references/jobs.md
- `setup` — preflight: is codex installed and authenticated?

Two standing rules. Never patch anything under `runtime/` — it is
byte-identical to upstream so bugfix releases import as a clean diff;
behavior changes belong at the call site (flags, env) or in these docs.
And reviews are advisory input to your own judgment: read the findings,
adopt what survives scrutiny, and never present Codex output as your own
analysis.
