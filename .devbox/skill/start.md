# Working in doperpowers

doperpowers is a plugin — skills, agents, hooks and output styles — not a running app: there is no
service to start. `devenv up doperpowers` installs the one dependency tree
(`application-agents/triaging-feedback`, `npm ci`); everything else runs straight from the
checkout.

Run the checks for what you touched:

- Shell scripts: `scripts/lint-shell.sh` (changed files; `--all` for the tracked baseline).
- The feedback poller: `cd application-agents/triaging-feedback && npm test`.
- Function-hook mods (`hooks/mods/`): `tests/mods/run-mods-tests.sh` (needs the `claude` CLI).
- sminos: `tests/sminos/run-sminos-tests.sh` (hermetic, stubbed `claude`).
- Skill behavior: `tests/claude-code/run-skill-tests.sh` drives the real `claude` CLI and spends
  model calls — run it for the skill you changed, not by default.

A change to a skill or the plugin ships with `scripts/bump-version.sh` in the same commit
(`CLAUDE.md`, Working conventions). Before calling work done, go through `validation.md`.
