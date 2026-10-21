# tests/

A bare directory name is this directory's; `tests/…` paths are the repository's.

Shell + harness integration tests, one subdir per harness (`claude-code/`, `codex/`, `shell-lint/`, …). Run via each dir's `run-*.sh`. `mods/` holds the function-hook mods' TypeScript tests, run with `tests/mods/run-mods-tests.sh` (it stages a plugin folder, which `claude plugin test` requires), and `typecheck.sh`, the `mods-types` gate: `tsc` over all four plugins' mods and tests. `mods/interim-audit/run.sh <since>` audits the interim-notification filter against this machine's transcripts (every dropped prompt, a check on each interim drop, and why each let-in notice passed); rerun it when the Claude Code engine version changes. (Note: `opencode/`, `kimi/`, `pi/`, `antigravity/` test harnesses whose plugin dirs were already pruned — orphaned, not wired to any runner.)
