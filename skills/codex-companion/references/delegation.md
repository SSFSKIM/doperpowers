# Delegation: `task`

Hands an arbitrary prompt to a Codex thread in this workspace — diagnosis,
research, implementation, a second-opinion pass. Prints Codex's final
response; records a job (see references/jobs.md).

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" task \
      [--background] [--write] [--resume-last|--fresh] \
      [--model <m|spark>] [--effort none|minimal|low|medium|high|xhigh] \
      [--prompt-file <path>] [prompt text]

- Read-only by default. `--write` lets Codex edit the working tree — pass
  it only when edits are the point (a fix, an implementation), not for
  review/diagnosis/research.
- `--model` and `--effort` left unset defer to the user's codex
  `config.toml`. `spark` is an alias for `gpt-5.3-codex-spark`.
- Long or structured prompts go in a file via `--prompt-file` instead of
  fighting shell quoting.

Threads are resumable, which makes `task` a multi-turn discussion partner:
run once, read the answer, then continue the same thread with
`--resume-last` and a follow-up prompt. `--resume-last` picks the most
recent task thread in this workspace (`--resume` is an accepted synonym);
`--fresh` forces a new thread when the request merely sounds like a
follow-up.
