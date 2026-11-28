# sminos/

A fourth plugin in this marketplace, standalone: it declares no dependency, and nothing of doperpowers' is needed for it to run. It holds the project family (sessions of one project sharing an append-only log), its CLI, daemon and shell hooks, the bridge, the ask tool, the question sheet and the session's address. Versioned on its own: `scripts/bump-version.sh --plugin sminos`. Design: `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`; the project log `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`; remote-derived project identity `docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md`; channels `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`.

Paths below are named from `sminos/`; `docs/` paths are the repository's.

## Where things live

| Path | What it is |
|---|---|
| `skills/sminos/scripts/` | The CLI (`sminos.py`), the daemon and its uplink, channels, threads, the sheet's record; its `CLAUDE.md` maps the modules |
| `bin/sminos` | Runs the CLI; the engine puts a plugin's `bin/` on every session's Bash PATH, so what a session is told names it `sminos` |
| `hooks/` | Shell hooks (`smns-*.sh`): record, derive on compaction, `/clear` witness, the session-start guide; `hooks/CLAUDE.md` |
| `hooks/mods/` | Function hooks: bridge, backtick guard, ask tool, question sheet, address, naming; `hooks/mods/CLAUDE.md` |
| `skills/sminos/SKILL.md`, `references/setup.md` | What a member acts on; machine setup (mirror, hub enrollment, daemon, policy) |
| `skills/manager/` | The owner's read-only session manager (`docs/doperpowers/specs/2026-10-31-session-manager-design.md`); its command imports the CLI's modules and adds no verb |
| `types/sheet/` | The question sheet's published contract, which MAWS pins; see below |
| `tests/` | `run-sminos-tests.sh` (the `sminos` gate), `mods/run.sh` (the `sminos-mods` gate) |

## Before you change anything

- **Hook order is the owner's settings, not a dependency.** `prependPlugins` in `~/.claude/settings.json` (a host's managed settings likewise) seats `to-human`, `sminos`, `doperpowers` outermost, outside every user-tier plugin. A dependency cannot do this: the engine puts a dependent outside its dependency and pushes a depended-on plugin behind every other.
- **A peer frame's reply line names the CLI by absolute path**, not `sminos`: its recipient may run without the plugin's `bin/` on PATH (`reply_line`). The daemon's service also names `<clone>/sminos/skills/sminos/scripts/sminos.py` directly, so a service installed from an older path fails until `sminos daemon install` is rerun.
- **A whole-value check is `fullmatch`, never `match` against `^…$`.** Python's `$` also matches before a trailing newline, so `match` passes `"x\n"` for an id, name or file name read from a frame or record (board #179). The mods' JavaScript `$` without the `m` flag does not have this problem.
- **`types/sheet/` is frozen.** It is written by `tests/sheet-contract.gen.py`, never by the code it holds to account, and changes only by a ruling of the composite's writer with a new `version` in its manifest (`types/sheet/README.md`). Editing it to match the code breaks MAWS's pin.
- **The question sheet is off by default** (`SMINOS_QUESTION_SHEET`); its design is MAWS's composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`, child C2, plan `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`.
