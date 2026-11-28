# sminos/hooks/ — the sminos plugin's hooks

Paths are named from `sminos/`. `hooks.json` registers both kinds of hook: the shell hooks here and the function hooks under `mods/`, whose detail is in `hooks/mods/CLAUDE.md`. Each shell hook is a thin gate in front of a `sminos` verb (`skills/sminos/scripts/sminos`): how a hook works is in its header comment, what the verb does in the docstrings it names below.

## The hooks

- `smns-record.sh` (`Stop`; `SessionStart` except `compact`) pipes the payload to `sminos record` (`run_record`, `cmd_record`, `record_sheet` in `sminos.py`): joins the session to its project, exports what it sent its human into the project log, and at Stop writes what its question sheet owes the log.
- `smns-derive.sh` (`SessionStart`, `compact`) starts `sminos derive <session> --compacted` detached, output to `daemon.log` (`cmd_derive`, `derive_refusal`, `clear_status`).
- `smns-guide.sh` (`SessionStart`, every source) prints `sminos guide` on a machine enrolled at a desk hub (`cmd_guide`, `guide_text`, `roster_text`).
- `smns-cleared.sh` (`SessionEnd`) keeps a `/clear`'s payload and the identity of the question sheet left under `$SMINOS_HOME/cleared/<CLAUDE_PID>.*`, read by the new session's hooks (`cleared_from`) and the daemon's sweep (`sminos_sheet.remove_record`).

## Invariants and traps

- Every hook exits 0 and prints nothing but the guide's text, because a `SessionStart` hook's stdout joins the model's context and a failing hook must never block a turn or a start; failures go to `daemon.log`.
- Every hook does nothing under `SMNS_INTERNAL`, because sminos's own headless forks (derive's) must never join, be recorded or be guided.
- The hooks are the only sminos code that runs in the session's own environment (`CLAUDE_PID`, `CLAUDE_PROJECT_DIR`, `CLAUDE_CONFIG_DIR`, `SMINOS_LAUNCH`), so whatever the CLI or the daemon needs from that environment later (the config dir, a spawn's launch claim, a `/clear`'s witness) has to be recorded by a hook.
- A shell preflight only decides whether Python starts, and the verb decides again, so a preflight may admit too much but must never refuse a session the verb would act on: a cwd it cannot judge, `$CLAUDE_PROJECT_DIR`, a `join` override, a question sheet and an enrolled machine all admit.
- `smns-cleared.sh` stays bash with no Python and one write and rename per file, because an ending session's hooks are given little time.
- Time bounds differ by hook: `record` bounds itself (`SMNS_RECORD_TIMEOUT`, default 5 s; `run_record` says what it may cut), while the others rely on `hooks.json`'s `timeout`, which is the engine's kill.

Tests: `tests/test-smns-guide-hook.sh`, and the hooks run end to end in `tests/test-join.sh`, `test-org.sh`, `test-remote.sh` and `test_sheet_log.py`; all through `tests/run-sminos-tests.sh`.
