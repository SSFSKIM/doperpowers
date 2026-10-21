# sminos/

A fourth plugin in this marketplace, standalone (versioned on its own: `scripts/bump-version.sh --plugin sminos`; it declares no dependency, and nothing of doperpowers' is needed for it to run): the project family, its CLI and shell hooks, the bridge, the ask tool and the session's address; design `docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`.

Its place in the hook order is the owner's settings': `prependPlugins` in `~/.claude/settings.json` (a host's managed settings likewise) names `to-human@doperpowers`, `sminos@doperpowers` and `doperpowers@doperpowers`, which seats its hooks outside doperpowers' and every user-tier plugin's, devcloud's secrets guard and cua's among them; no dependency can, since the engine puts a dependent outside its dependency and pushes a plugin others depend on behind every one nobody depends on.

The plugin's own files below are named from `sminos/` (`docs/` paths are the repository's). Each part's detail sits beside its code: the CLI, the daemon and its uplink in `skills/sminos/scripts/CLAUDE.md`, the shell hooks in `hooks/CLAUDE.md`, the function hooks in `hooks/mods/CLAUDE.md`.

The CLI is `skills/sminos/scripts/sminos.py` (its launcher `sminos` beside it), reached on a machine at `<clone>/sminos/skills/sminos/scripts/sminos.py`, the path `daemon install` writes into the service; doperpowers' old path, `skills/sminos/scripts/sminos.py`, no longer exists, so a service installed before the move fails until `sminos daemon install` is rerun.

The project family: a committed `.smns` names a project, every session working under it (spawned seat, one the human opened, or one the MAWS app launched, which marks it with `SMNS_MEMBER` since its entrypoint is `sdk-ts`) is a member from its start, its project read from the directory it was launched in (a `cd` never moves it) unless it declares another with `sminos join <project>`; on a machine enrolled at a desk hub a repository no `.smns` claims is the hub project its remote derives (`origin`, else its only remote, normalized: one id from every clone, worktree and machine, nothing committed; design `docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md`), and a directory neither claims is in the machine's own project (`@<machine>`), so every session there is in a synced project; and what crosses sessions — `say` to peers (untagged is a record, `@alias` delivers, `@all` wakes every live member, a selector — `list`'s filters — every live session of its scope in any project, recorded in each project it reaches), a member's `<message>` to the human, joining, an in-charge line, spawning a sibling, retiring — is one event in the project's append-only log, one file per writer under `$SMINOS_HOME/projects/<id>/log/`.

The skill's body is what a member acts on; machine setup (the project and its mirror, enrollment, the daemon, the policy) is its `references/setup.md`.

Design in `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`; the hub side in `docs/doperpowers/plans/2026-10-15-desk-dc4-uplink.md`, a child of the desk's composite design in MAWS.

Tests: `tests/run-sminos-tests.sh` (the `sminos` gate), `tests/mods/run.sh` (the `sminos-mods` gate).
