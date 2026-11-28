# sminos/hooks/ — the sminos plugin's hooks

Paths are named from `sminos/`. `hooks.json` registers both kinds of hook: the shell hooks here and the function hooks under `mods/`, whose detail is in `hooks/mods/CLAUDE.md`. Each shell hook is a thin gate in front of a `sminos` verb (`skills/sminos/scripts/sminos`): how a hook works is in its header comment, what the verb does in the docstrings it names below.

## The hooks

- `smns-record.sh` (`Stop`; `SessionStart` except `compact`) pipes the payload to `sminos record` (`run_record`, `cmd_record`, `record_sheet` in `sminos.py`): joins the session to its project, exports what it sent its human into the project log, and at Stop writes what its question sheet owes the log.
- `smns-derive.sh` (`SessionStart`, `compact`) starts `sminos derive <session> --compacted` detached, its output to `daemon.log` when the sminos home exists (`cmd_derive`, `derive_refusal`, `clear_status`).
- `smns-tasks.sh` (`SessionStart`, every source) prints the Task Board's start line through `sminos task remind`, then marks those keys shown; its header states the order and why.
- `smns-guide.sh` (`SessionStart`, each source `hooks.json` lists) prints `sminos guide` on a machine enrolled at a desk hub (`cmd_guide`, `guide_text`, `roster_text`).
- `smns-cleared.sh` (`SessionEnd`) keeps a `/clear`'s payload and the identity of the question sheet left under `$SMINOS_HOME/cleared/<CLAUDE_PID>.*`, read by the new session's hooks (`cleared_from`) and the daemon's sweep (`sminos_sheet.remove_record`).

## Where to stop and read first

- **Quiet exits**: each hook exits 0 and prints nothing but the guide's text, since a `SessionStart` hook's output joins the model's context and a failing hook must not block a turn. Where a failure is logged differs by hook and verb: read the hook's header and the verb's docstring before relying on `daemon.log` for one.
- **Internal forks**: each script returns early under `SMNS_INTERNAL` (grep the four).
- **The session's environment**: the hooks run in it, as do the bridge's child and a verb a session's tools run; the daemon does not, and reads what was recorded (`record_config_dir`, the engine config-dir comment block in `sminos.py`). Check which side a reader is on before adding one.
- **Preflights**: a shell preflight decides whether Python starts, and the verb decides again. Read `smns-record.sh`'s header before tightening one, since refusing a session the verb would act on loses its record.
- **`smns-cleared.sh`**: bash with no Python and one write and rename per file, because an ending session's hooks get little time.
- **Time bounds**: `run_record`'s docstring says what `SMNS_RECORD_TIMEOUT` bounds and what it lets finish; `hooks.json`'s `timeout` is the engine's kill of the hook process, not of the `nohup`ed derive it starts.

Tests: `tests/test-smns-guide-hook.sh`, `tests/test-tasks-hook.sh`, and the hooks run end to end in `tests/test-join.sh`, `test-org.sh`, `test-remote.sh` and `test_sheet_log.py`; `tests/run-sminos-tests.sh` runs them.
