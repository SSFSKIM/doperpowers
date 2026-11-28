# hooks/mods/ — the doperpowers plugin's function hooks ("mods")

Bare file names are this directory's; other paths are the repository's. `register.tsx` registers the mods; `README.md` beside this file is their manual, one section per mod: how each works, the engine facts it stands on, its known limits. Read a mod's section before changing it.

| File | What it is |
|------|-----------|
| `fork-guard.tsx` | Holds the sminos bridge's fork agents (the session manager's `manager query`) to reading. Registered first in `register.tsx`, so its hooks are the plugin's outermost. |
| `kairos.tsx` | The `[ kairos off ]` / `[ kairos on ]` footer button; reads the mode's state from the shell hooks, never writes it. |
| `compact.tsx` | `mcp__doperpowers__compact`, the model compacting its own context, its turn-end offer, and the guidance it places in every loop's MCP server instructions. |
| `appeal.tsx`, `appeal-judge.tsx` | `mcp__doperpowers__appeal`: an auto-mode classifier block contested to an independent judge. `appeal-judge.tsx` is the logic that takes no `$`. |
| `interim.ts` | Drops an agent's interim task notification that tells the session nothing new. |
| `reload.tsx` | Applies a plugin update another process installed, by `/reload-plugins`, and empties the rows that run leaves. |

`/secret KEY` is the `cua` plugin's; the secrets guard is devcloud's (`devcloud/`).

## Traps

- The engine admits one unmatched registration of an event per module, and `$` may only be passed to functions in the same file, so a mod that shares an event with another takes it with a matcher rather than sharing a registration.
- The engine hands every subagent every MCP tool and a hook cannot filter per agent; the agent definitions withhold the session-only tools through `disallowedTools` (see the root `CLAUDE.md`).
- A `prompt.attachment` answer is cached process-wide by attachment UUID, which forks inherit: what it puts in place must read the same in every loop.
- The engine compacts only between turns, and starts whatever waits in its queue before a turn's `turn.complete` hooks run; no hook can reorder that.
- A hook's own time is bounded by the engine's 10 s hook budget; past it the hook is gone and what it held passes on.
- The fork guard has to be another plugin's than sminos: the bridge spawns its fork outside every hook frame, which bypasses sminos's hooks. Its probe strings are spelled the same in `sminos/hooks/mods/bridge-ask.tsx`.

## Tests

`tests/mods/run-mods-tests.sh` runs the mods' tests (`tests/mods/<mod>.test.ts`); the `live-*-check.py` files there spend model calls and run by hand. `tests/mods/typecheck.sh` is the `mods-types` gate, against the declarations the engine lays in each plugin's gitignored `.claude-plugin/types/` as a session loads it (`--lay` has the installed engine do it headless).
