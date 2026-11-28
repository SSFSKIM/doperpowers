# skills/manager/scripts/ — the session manager's command

`manager` (a launcher that resolves its real path, then runs `manager.py`) is the manager skill's read-only command over the sessions the owner follows; `manager.py`'s module docstring is its usage. It belongs to the manager skill alone: it adds no sminos verb and appears nowhere in `sminos help` or the sminos skill. The design is `docs/doperpowers/specs/2026-10-31-session-manager-design.md`, whose Interfaces section holds the commands, JSON shapes, entry kinds and state file.

## Modules

- `manager.py`: the CLI. Member resolution (`resolve`, `resolve_stored`, `historical`), `transcript`, `pending` with the seen marks, `subscriptions`, `ledger` and `ledger apply`, `query` (through `sminos_fork`), and `serve`'s entry.
- `manager_window.py`: the transcript window reader and the entry classifier, provenance included (`window`, `Classifier`, `OwnerWords`).
- `manager_ledger.py`: the state file (version 2, its migration, lock and archive), `apply` (the one way an update changes the state), and the ledger's views (`view`, `render`).
- `manager_serve.py`: `manager serve`, the ledger's read-only page for the owner's tailnet, with its launchd install and status.
- Outside this directory: `../SKILL.md` and `../references/digest-brief.md` (what the manager model and its digest subagents read), `../assets/page.html` (the page, whose design law is `../assets/DESIGN.md`), and `../references/sminos-manager.plist` (the launchd agent's template).

## Where to stop and read first

- **The read-only contract**: `manager.py`'s module docstring says what the command writes and what resolving a member may cause. A change that calls the functions behind `say`, `send`, `steer`, `interrupt`, `answer`, `decide`, `compact`, `model`, `charge`, `status` or a cursor-advancing `chat` breaks it.
- **Reliance on sminos's internals**: `manager.py` imports sminos's modules from `../../sminos/scripts` and calls private helpers (`S._own_events`, `S._ask_events`, `B._tool_summary`, …); `manager_window.py` copies constants the bridge writes (`hooks/mods/bridge.tsx`). Run the manager's tests after a change on either side.
- **Owner provenance**: `manager_window`'s module docstring and `OwnerWords.corroborates`. A row wrongly shown as the owner's words is the costliest mistake this reader can make; read both before changing how a row is labelled.
- **Transcript reads**: `manager_window.window` seeks and scans with bounded memory, because transcripts run to hundreds of MB and `pending` reads each subscription's window at each update. Read its docstring before adding a read.
- **Subscriptions**: keyed by the stored session id, since aliases recur and change; a lineage session with no transcript here makes the read an error (the comment before `raise NoWindow` in `manager.py`).
- **The state file**: `manager_ledger`'s lock, `apply` (its docstring says what a refusal leaves unchanged) and `_check_fields`.
- **The page**: `manager_serve.py`'s docstring (the `Tailscale-User-Login` check, what serving may not do); the tests hold it with an audit hook.
- **The skill and the brief**: `../SKILL.md` and `../references/digest-brief.md` read this command's output shapes. A change to them, or to the shapes, wants the pressure scenarios rerun, and for the brief a replay update (`docs/doperpowers/specs/2026-10-31-session-manager-replay.md`).

## Tests

- `sminos/tests/test_manager.py` and `sminos/tests/test_manager_serve.py` run in the `sminos-suites-a` gate (from the repository root, `SMINOS_PART=suites-a bash sminos/tests/run-sminos-tests.sh`). Each file's docstring says what it stands in for.
- `sminos/tests/mods/live-manager-check.py` runs `manager query` and `sminos derive` against a throwaway live session. It spends model calls, so it runs by hand and is not a gate; its docstring has its flags.
