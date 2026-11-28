# skills/manager/scripts/ — the session manager's command

`manager` (a launcher that resolves its real path, then runs `manager.py`) is the manager skill's read-only command over the sessions the owner follows; `manager.py`'s module docstring is its usage. It belongs to the manager skill alone: it adds no sminos verb and appears nowhere in `sminos help` or the sminos skill. The design is `docs/doperpowers/specs/2026-10-31-session-manager-design.md`, whose Interfaces section holds the commands, JSON shapes, entry kinds and state file.

## Modules

- `manager.py`: the CLI. Member resolution (`resolve`, `resolve_stored`, `historical`), `transcript`, `pending` with the seen marks, `subscriptions`, `ledger` and `ledger apply`, `query` (through `sminos_fork`), and `serve`'s entry.
- `manager_window.py`: the transcript window reader and the entry classifier, provenance included (`window`, `Classifier`, `OwnerWords`).
- `manager_ledger.py`: the state file (version 2, its migration, lock and archive), `apply` (the one way an update changes the state), and the ledger's views (`view`, `render`).
- `manager_serve.py`: `manager serve`, the ledger's read-only page for the owner's tailnet, with its launchd install and status.
- Outside this directory: `../SKILL.md` and `../references/digest-brief.md` (what the manager model and its digest subagents read), `../assets/page.html` (the page, whose design law is `../assets/DESIGN.md`), and `../references/sminos-manager.plist` (the launchd agent's template).

## Invariants and traps

- The command is read-only. Nothing here appends to a session's conversation, interrupts it or writes to a project log, so it never calls the functions behind `say`, `send`, `steer`, `interrupt`, `answer`, `decide`, `compact`, `model`, `charge`, `status` or a cursor-advancing `chat`. That lets the owner point it at any session without disturbing it. The only writes are the manager's own state file and archive, plus `serve.json` and the launchd agent at install. Resolving a member may still let sminos reconcile a project's membership, as any sminos read does.
- `manager.py` imports sminos's modules from `../../sminos/scripts` and leans on their private helpers (`S._own_events`, `S._ask_events`, `B._tool_summary`, …). `manager_window.py` also copies constants the bridge writes (`hooks/mods/bridge.tsx`). A change to either side can break the manager while the CLI's own tests stay green, so run the manager's tests after one.
- Provenance is where the reader is most likely to be wrong, and inventing the owner's words is the worst mistake it can make. No row reads as `you` without an origin that says outright the owner typed it. A delivery counts as the owner's (`you·desk`) only when exactly one log event matches its exact text, checked frame by frame (`manager_window`'s module docstring, `OwnerWords.corroborates`).
- A transcript is never read whole. The reader bisects to a seek point over an mmap and skips request records unparsed, because transcripts run to hundreds of MB and `pending` reads every subscription's window at each update.
- A subscription is keyed by the session id it stored, never its alias, because aliases recur and change. Its member is a lineage of sessions (`continued_in`, `sminos_bridge.successor`). A lineage session in the window with no transcript on this machine makes that subscription an `error`, never an inactive one, so the update leaves its `covered` where it was.
- Every read-modify-write of the state holds `<name>.lock`. `ledger apply` validates the whole change before writing anything, and a refusal exits 2 naming every problem.
- The page relies on the tailnet's ingress for its security. Every request must carry exactly one `Tailscale-User-Login` equal to the owner, checked before the method or the path. While serving, it starts no process and opens no outbound connection; the tests enforce both with an audit hook.
- `../SKILL.md` and the digest brief are behavior, and they read this command's output shapes. Before relying on a change to either file, or to the shapes they read, rerun the pressure scenarios, and for the brief a replay update as well (`docs/doperpowers/specs/2026-10-31-session-manager-replay.md`).

## Tests

- `sminos/tests/test_manager.py` and `sminos/tests/test_manager_serve.py` are the `sminos-suites-a` gate (`sminos/tests/run-sminos-tests.sh suites-a`). Each file's docstring says what it stands in for.
- `sminos/tests/mods/live-manager-check.py` runs `manager query` and `sminos derive` against a throwaway live session. It spends model calls, so it runs by hand and is not a gate; its docstring has its flags.
