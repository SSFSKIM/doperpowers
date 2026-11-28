# sminos/

A fourth plugin in this marketplace, standalone: it declares no dependency, and nothing of doperpowers' is needed for it to run. It holds the project family (sessions of one project sharing an append-only log), its CLI, daemon and shell hooks, the bridge, the ask tool, the question sheet and the session's address. Versioned on its own: `scripts/bump-version.sh --plugin sminos`. Design: `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`; the project log `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`; remote-derived project identity `docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md`; channels `docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md`.

Paths below are named from `sminos/`; `docs/` paths are the repository's.

## Where things live

| Path | What it is |
|---|---|
| `skills/sminos/scripts/` | The CLI (`sminos.py`), the daemon and its uplink, channels, threads, the sheet's record; its `CLAUDE.md` maps the modules |
| `bin/sminos` | Runs the CLI; the engine puts a plugin's `bin/` on a session's Bash PATH (`bin/sminos`'s header), so what a session is told names it `sminos` |
| `hooks/` | Shell hooks (`smns-*.sh`): record, derive on compaction, `/clear` witness, the session-start guide; `hooks/CLAUDE.md` |
| `hooks/mods/` | Function hooks: bridge, backtick guard, ask tool, question sheet, address, naming; `hooks/mods/CLAUDE.md` |
| `skills/sminos/SKILL.md`, `skills/sminos/references/setup.md` | What a member acts on; machine setup (mirror, hub enrollment, daemon, policy) |
| `skills/manager/` | The owner's read-only session manager (`docs/doperpowers/specs/2026-10-31-session-manager-design.md`); its command imports the CLI's modules and adds no verb |
| `types/sheet/` | The question sheet's published contract, which MAWS pins; see below |
| `tests/` | `run-sminos-tests.sh` (the hermetic suite; `SMINOS_PART` picks the part a gate runs, `.github/ci-kit.yml`), `mods/run.sh` (the `sminos-mods` gate) |

## Where to stop and read first

- **Hook order across plugins**: it comes from the tier lists in settings (the owner's `prependPlugins` in `~/.claude/settings.json`, or a host's managed settings when present), not from a plugin dependency. `hooks/mods/bridge-place.tsx`'s header and `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md` say why and what the bridge checks; read them before changing either.
- **The CLI's path in what sessions are told**: what a session reads names `sminos` (on PATH through `bin/`), while a peer frame's reply line names the absolute path (`reply_line` says why). The daemon's service names the path `daemon install` wrote; rerun `sminos daemon install` after the CLI moves.
- **Whole-value checks**: Python's `$` matches before a trailing newline, so an id, name or file name read from a frame or record is checked with `fullmatch` (board #179); the mods' JavaScript `$` without the `m` flag has no such gap.
- **`types/sheet/`**: MAWS pins it. `types/sheet/README.md` says how it is written and changed; editing it to match the code breaks the pin.
- **The question sheet** is off by default; what turns it on is the start-choice table in `hooks/mods/sheet-model.tsx`. Its design is MAWS's composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`, child C2, plan `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`.
