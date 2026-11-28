# sminos/hooks/mods/ — the sminos plugin's function hooks

A path here is named from `sminos/` when it is the plugin's own file; `docs/`, `sminos/…` and `to-human/…` paths are the repository's.

The plugin's one hooks module, `register.tsx` (named by `hooks/hooks.json` under `modules`), and the mods it registers. The engine loads it where function hooks are enabled (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`); the shell hooks in `hooks/` run without it. `README.md` here is the manual, a section per mod, with its known limits; a module's header comment is its contract. The bridge's wire protocol is DX5 in `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`; its child is `skills/sminos/scripts/sminos_bridge.py`.

## Modules

- `register.tsx`: registers, in this order, the bridge, the backtick guard, the sheet's band, the ask's band, the question sheet, the ask, the address, the name.
- `ask.tsx`: `mcp__sminos__AskUserQuestion`, blocking (the engine's dialog via `$.ui.ask`, widened by its own `tool.call` hook) or async (`[ answer ]`/`[ dismiss ]`, the `N open questions` band, delivery by result, idle prompt or next prompt); withdraws the built-in.
- `sheet.tsx`: the question sheet, the ask's second form: the start choice, the tool under the sheet's schema, a call staged and ordered as one `sminos sheet step`, the delivery routes, the band and a call's row, the `ask` snapshot and the project-log projection.
- `sheet-model.tsx`: the sheet's parts that take no `$` (description, schema, the start-choice table, validation, result texts, views' order).
- `backticks.tsx`: refuses a Bash call that hands `sminos` a backtick the shell would run, by lexing the command; gives up (lets it run) on syntax it does not model.
- `address.tsx`: appends `Sminos-Session: …` to the engine's attribution text, from `sminos who --session <id>`, kept with a TTL.
- `name.tsx`: applies a pending charge name from `$SMINOS_HOME/names/<session>.json` with the engine's `/rename`, on a 15 s idle tick, after `sminos name-due`.
- `bridge.tsx`: the hooks and the bridge's own code that takes `$`: the session start, the child (`sminos bridge --session <id>`), control ops, the wait for a decision, the guard reads, lane B, launch id.
- `bridge-place.tsx`: the rule judging the bridge's place among the secrets guards from `next.trace`, and its seat (whose plugin, which tier).
- `bridge-state.tsx`: the one state object, shared types, helpers, `resetBridge`.
- `bridge-stream.tsx`: the mod's copy of the live state a `resync` carries, the poster loop, body-size caps, the permission-mode fields.
- `bridge-requests.tsx`: permissions and questions raised to the desk, and their one `settled`.
- `bridge-rows.tsx`: each kept row's notice (`block-row`/`row-seen`), a compaction's rows from the transcript, the export to the project log, a delivery's row, a desk command's readback.
- `bridge-agents.tsx`: agents the module did not see spawn, learned from `$.agent.list()`.
- `bridge-routes.tsx`: the desk's slash-command route table as data, generated (below).
- `bridge-commands.tsx`: routing a command by that table (`routeOf`), and the refusals' words.
- `bridge-controls.tsx`: `capabilities.controls`, each desk control's key with whether this bridge can do it.
- `bridge-catalog.tsx`, `bridge-reads.tsx`: the desk's `read` catalog and its `usage`/`config`/`settings`/`mcp`, with the fields likeliest to hold a credential left out (`bridge-reads.tsx`'s header names them).
- `bridge-btw.tsx`: the desk's side question, one `$.model.fork`.
- `bridge-ask.tsx`: the owner's manager's question, a read-only fork agent with a tail of the running turn.
- `bridge-agent-ops.tsx`: `stop-agent` and `tell`, one subagent stopped or told.
- `bridge-media.tsx`: a desk upload read into the conversation by a synthetic native Read at a main-loop step.
- `bridge-holder.tsx`: a MAWS lane B observer's part in the host's release fence, turn origins, and the receipts' reports and releases.
- `bridge-receipts.tsx`: which delivery receipts a main-loop request carried.

## Where to stop and read first

Each entry names an area where a plausible change breaks something across modules, and where its rule is stated exactly.

- **Registration order**: `register.tsx` (its order sets which hooks are outermost); across plugins, the owner's `prependPlugins` (`sminos/CLAUDE.md`).
- **The bridge's place among secrets guards**: `bridge-place.tsx`'s header, including what it cannot detect, and the paragraph on it in `bridge.tsx`'s header. The detection is a backstop, not a check that a placement is supported.
- **Module reloads**: what survives a reload of sminos itself is kept in `$.state` and reconciled by the next instance; a reload of another plugin can leave this module running. Read `bridge.tsx`'s header, `bridge-place.tsx` (why a surviving bridge is judged again) and the 409 handling in `bridge-stream.tsx`.
- **`$.state`'s `ask` snapshot**: another plugin reads it (`types/sminos.d.ts`); `ask.tsx` and `sheet.tsx` both write it.
- **The ask's two forms**: the start choice in `sheet-model.tsx` and `ask.tsx`'s `yieldAsk`; check a change to the ask against both.
- **The bridge's module graph and `$`**: `bridge.tsx`'s header lists the modules in import order and says which take `$`; keep it true when adding a module or an import.
- **Work that must outlive a hook**: a fetch begun inside a hook is aborted with that dispatch (an Esc, an interrupt). Read the poster loop in `bridge-stream.tsx`, the sheet's `$.clock.after(0)` routes, and `bridge-holder.tsx`'s `waitAtFence`, which keeps its calls inside the dispatch on purpose.
- **What a plugin hears of itself**: `$.command.run`, the plugin's own appends, a fork agent from the command listener, and `$.ui.ask` each skip some of the plugin's own hooks. `bridge-commands.tsx`'s header, the comments on the plugin's own append in `bridge.tsx`, `bridge-ask.tsx`'s header and `ask.tsx`'s comment on its widened dialog say which.
- **The mod–child protocol**: `sminos_bridge.py`, `sminos_holder.py` and `CONTROL_OPS` in `bridge.tsx` (lane B refusals); a change on one side needs the other and both gates.
- **Generated fixtures**: `bridge-routes.tsx` and `tests/mods/gate-fixture.ts` are written from JSON by the commands below; a check fails while they differ.
- **Engine behavior**: comments say on which engine a behavior was measured (`measured on 2.1.3xx`); a new claim of that kind gets a live check (`tests/mods/live-*-check.py`).
- **Internal forks** (`SMNS_INTERNAL`): `bridge.tsx`, `address.tsx`, `name.tsx` and `sheet-model.tsx`'s start choice read the marker; `backticks.tsx` does not.

## Commands and tests

```
sminos/tests/mods/run.sh               # the sminos-mods gate: claude plugin test + validate, then the ask's search and the sheet's step
tests/mods/typecheck.sh                # the repository's plugins' mods, typechecked (repository root); --lay has the engine lay the types
bash sminos/tests/run-sminos-tests.sh  # the hermetic suite, the bridge's child side (test-bridge*.sh, test_holder*.py) and the route check among it
python3 sminos/tests/routes_check.py --write sminos/tests/routes-*.json   # regenerate bridge-routes.tsx after editing a routes fixture
python3 -B sminos/tests/test_holder.py --write-gate-ts                    # regenerate tests/mods/gate-fixture.ts from p5-o16-gate.jsonl
claude --plugin-dir sminos --debug     # the plugin from this checkout, hot reload on save
```

The mods' tests are `tests/mods/*.test.ts`; the bridge's share `bridge-harness.ts`, the sheet's `sheet-harness.ts`, and the seat tests (`bridge-seat-*.test.ts`, one tier each through `bridge-seat-kit.ts`) load the real module so the engine's tier rule decides. `tests/mods/live-*-check.py` run real sessions and spend model calls: run them by hand, after a change that rests on engine behavior.
