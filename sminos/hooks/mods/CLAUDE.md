# sminos/hooks/mods/ — the sminos plugin's function hooks

A path here is named from `sminos/` when it is the plugin's own file; `docs/`, `sminos/…` and `to-human/…` paths are the repository's.

The plugin's one hooks module, `register.tsx` (named by `hooks/hooks.json` under `modules`), and the mods it registers. The engine loads it only where function hooks are enabled (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`); the shell hooks in `hooks/` run everywhere. `README.md` here is the manual, a section per mod, with its known limits; each module's header comment is its contract and names its design or plan. The bridge's wire protocol is DX5 in `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`; its child is `skills/sminos/scripts/sminos_bridge.py`.

## Modules

- `register.tsx`: registers, in this order, the bridge, the backtick guard, the sheet's band, the ask's band, the question sheet, the ask, the address, the name.
- `ask.tsx`: `mcp__sminos__AskUserQuestion`, blocking (the engine's dialog via `$.ui.ask`, widened by its own `tool.call` hook) or async (`[ answer ]`/`[ dismiss ]`, the `N open questions` band, delivery by result, idle prompt or next prompt); withdraws the built-in.
- `sheet.tsx`: the question sheet, the ask's second form: the start choice, the tool under the sheet's schema, a call staged and ordered as one `sminos sheet step`, the delivery routes, the band and a call's row, the `ask` snapshot and the project-log projection.
- `sheet-model.tsx`: everything of the sheet that takes no `$` (description, schema, the start-choice table, validation, result texts, views' order).
- `backticks.tsx`: refuses a Bash call that hands `sminos` a backtick the shell would run, by lexing the command; gives up (lets it run) on syntax it does not model.
- `address.tsx`: appends `Sminos-Session: …` to the engine's attribution text, from `sminos who --session <id>`, kept with a TTL.
- `name.tsx`: applies a pending charge name from `$SMINOS_HOME/names/<session>.json` with the engine's `/rename`, on a 15 s idle tick, after `sminos name-due`.
- `bridge.tsx`: the hooks and every bridge line that takes `$`: the session start, the child (`sminos bridge --session <id>`), control ops, the wait for a decision, the guard reads, lane B, launch id.
- `bridge-place.tsx`: the rule judging the bridge's place among the secrets guards from `next.trace`, and its seat (whose plugin, which tier).
- `bridge-state.tsx`: the one state object, shared types, helpers, `resetBridge`.
- `bridge-stream.tsx`: the mod's copy of the live state every `resync` carries, the poster loop, body-size caps, the permission-mode fields.
- `bridge-requests.tsx`: permissions and questions raised to the desk, and their one `settled`.
- `bridge-rows.tsx`: each kept row's notice (`block-row`/`row-seen`), a compaction's rows from the transcript, the export to the project log, a delivery's row, a desk command's readback.
- `bridge-agents.tsx`: agents the module did not see spawn, learned from `$.agent.list()`.
- `bridge-routes.tsx`: the desk's slash-command route table as data, generated (below).
- `bridge-commands.tsx`: routing a command by that table (`routeOf`), and the refusals' words.
- `bridge-controls.tsx`: `capabilities.controls`, every desk control's key with whether this bridge can do it.
- `bridge-catalog.tsx`, `bridge-reads.tsx`: the desk's `read` catalog and its `usage`/`config`/`settings`/`mcp`, cut so nothing credential-bearing leaves the machine.
- `bridge-btw.tsx`: the desk's side question, one `$.model.fork`.
- `bridge-ask.tsx`: the owner's manager's question, a read-only fork agent with a tail of the running turn.
- `bridge-agent-ops.tsx`: `stop-agent` and `tell`, one subagent stopped or told.
- `bridge-media.tsx`: a desk upload read into the conversation by a synthetic native Read at a main-loop step.
- `bridge-holder.tsx`: a MAWS lane B observer's part in the host's release fence, turn origins, and the receipts' reports and releases.
- `bridge-receipts.tsx`: which delivery receipts a main-loop request carried.

## Invariants and traps

- **`register.tsx`'s order is load-bearing.** The bridge registers first so its hooks are the plugin's outermost and it reports what the session showed after every other mod; the sheet registers before the ask so it takes its own events and passes the rest on. Across plugins the order is the owner's `prependPlugins` (`sminos/CLAUDE.md`).
- **The bridge must sit outside every secrets guard.** Inside devcloud's (or cua's copy) it would be handed inputs with secrets restored and results before scrubbing, so `bridge-place.tsx` turns a misplaced bridge off on any settled `tool.call`/`session.append`; until the first verdict tool events wait and no permission's input is raised. A permission is raised with the call as the bridge's own `tool.call` hook saw it, never the engine's later input, for the same reason.
- **A reload replaces the module and empties its memory.** Anything that must outlive `/reload-plugins` or the autoreload goes in `$.state` (`{plugin: 'sminos', key}`: `ask`, `sheet`, `mode`, `lane`, `launch`, `holder`, `media`, `btw`, `bridgeAsk`), and the next module reconciles it (open forks ended `aborted`, owed ends re-posted after a resync). The old instance is unloaded before the new loads, so each key has one writer at a time; its posts carry the old child's nonce and are refused (409), after which it stops.
- **`$.state`'s `ask` is another plugin's contract.** Its shape is `types/sminos.d.ts`; doperpowers' appeal and reload read its `answered` count and `isDialogUp`. Under the sheet, `sheet.tsx` writes it instead of `ask.tsx`, so a change to either keeps the snapshot whole.
- **A process's first `session.start` chooses the sheet, today's ask, or neither, and the choice stands** (`sheet-model.tsx`'s table, kept in `$.state`); `ask.tsx` yields under the sheet (`yieldAsk`), so a change to the ask is checked against both forms.
- **In the bridge family, `$` stays in `bridge.tsx`** except where a module's header says it takes it (`bridge-catalog`, `-reads`, `-btw`, `-ask`, `-agent-ops`, `-media`, `-holder`, and `-receipts` only to read the conversation); the rest reach the engine through the calls the session start keeps in the state. `bridge.tsx`'s header lists them in dependency order, each importing only those before it, which keeps the graph acyclic: a new module or import keeps the list true.
- **Work that must outlive a hook starts outside any hook's dispatch.** A fetch begun inside a hook is aborted with that dispatch (an Esc, an interrupt), so the stream's posts (`/events`) go from the poster loop started at `session.start`, and the sheet's routes go from a `$.clock.after(0)` hop. The exception is deliberate: on a fenced lane B request the `turn.step` hook's `waitAtFence` keeps its `/holder` `turn` and wait calls in flight inside the dispatch, which pauses the hook's own time budget, and they end with it.
- **A plugin does not hear itself everywhere.** `$.command.run` of its own command skips its own `command.run` hooks (the desk refuses those, `self`); its own append passes none of its hooks; a fork agent spawned from the command listener bypasses every sminos hook, so the manager's fork is read-only only through doperpowers' fork guard, and is refused `no-guard` unless that guard answers its probe; `$.ui.ask`'s call is seen by every hook of the plugin but the calling one, which is how the ask widens its dialog.
- **The mod and its child share one protocol.** An op, event or field added on one side needs the other (`sminos_bridge.py`, `sminos_holder.py`), and both gates; MAWS's lane B controls a session through the same bridge, so every control op is refused `lane-b` for an observer and a new op that is no control is exempted explicitly (`CONTROL_OPS`).
- **A mod loads no JSON.** Fixtures reach it as generated TypeScript: `bridge-routes.tsx` and `tests/mods/gate-fixture.ts` are written from JSON and never edited by hand; a check fails while they differ.
- **Engine behavior the code rests on is measured, not documented**, and comments say on which engine (`measured on 2.1.3xx`); a new such claim gets a live check, and the routes table is per measured engine (a session uses the newest at or below its own).
- **Nothing in sminos's internal forks** (`SMNS_INTERNAL`, derive's headless fork): the bridge, address and name do nothing there, and the sheet's start choice picks none.

## Commands and tests

```
sminos/tests/mods/run.sh               # the sminos-mods gate: claude plugin test + validate, then the ask's search and the sheet's step
tests/mods/typecheck.sh                # every plugin's mods, typechecked (repository root); --lay has the engine lay the types
bash sminos/tests/run-sminos-tests.sh  # the hermetic suite, the bridge's child side (test-bridge*.sh, test_holder*.py) and the route check among it
python3 sminos/tests/routes_check.py --write sminos/tests/routes-*.json   # regenerate bridge-routes.tsx after editing a routes fixture
python3 -B sminos/tests/test_holder.py --write-gate-ts                    # regenerate tests/mods/gate-fixture.ts from p5-o16-gate.jsonl
claude --plugin-dir sminos --debug     # the plugin from this checkout, hot reload on save
```

The mods' tests are `tests/mods/*.test.ts`; the bridge's share `bridge-harness.ts`, the sheet's `sheet-harness.ts`, and the seat tests (`bridge-seat-*.test.ts`, one tier each through `bridge-seat-kit.ts`) load the real module so the engine's tier rule decides. `tests/mods/live-*-check.py` run real sessions and spend model calls: run them by hand, after a change that rests on engine behavior.
