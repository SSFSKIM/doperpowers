# tests/

A bare directory name is this directory's; `tests/…` paths are the repository's.

One subdir per area (`claude-code/`, `codex/`, `mods/`, `issue-tracker/`, …), each run by its `run-*.sh` or its `test-*` files directly. Which of them CI runs, and how, is `.github/ci-kit.yml`; tests that call a live model are left out of it and run by hand.

- `mods/`: the function-hook mods' TypeScript tests, run with `run-mods-tests.sh`, which stages a plugin folder because `claude plugin test` requires one. `typecheck.sh` is the `mods-types` gate.
- `mods/interim-audit/run.sh <since>` audits the interim-notification filter against this machine's transcripts; rerun it when the Claude Code engine version changes, since the filter matches the engine's own wording.
