# sminos — its own plugin

**Date.** 2026-10-19. **Status.** Outline approved by the owner on 2026-10-19 (split, same marketplace;
AskUserQuestion moves and is renamed; the peer roster is a separate initiative); this document is the
design and its execution, written against the code and the engine (2.1.302 bundle, 2.1.303 installed);
awaiting independent review. Execution starts after doperpowers-79 (d88ef4c3, the copy/fork resume
rebuilding open async asks in `hooks/mods/ask.tsx`) merges. **Prior art, reference only.**
`docs/doperpowers/specs/2026-10-15-devcloud-design.md` (the second plugin carved out of this repository,
and the `$.state` marker another plugin reads); `docs/doperpowers/specs/2026-10-13-ask-async-design.md`
(the ask tool); `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` and
`docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md` (the bridge, DX5).

## Purpose

sminos is the machine side of the MAWS desk and the way sessions and humans reach each other: the CLI,
the daemon and its uplink, the bridge mod that makes a session reachable, the async ask, and the hooks
that record what a session sent its human. Today it lives inside the doperpowers plugin, among the
methodology skills, so a machine cannot run the desk's machine side without the methodology, and the
methodology cannot be installed without a daemon and a bridge. After this work `sminos` is the fourth
plugin of the same marketplace, beside `devcloud` and `to-human`, versioned on its own; a person
installs `sminos@doperpowers` on a machine and gets the whole orchestration interface, with or without
`doperpowers@doperpowers`; and the ask tool is `mcp__sminos__AskUserQuestion`.

How to see it working: on a machine with both plugins enabled and placed (§4), a session in a project
asks `mcp__sminos__AskUserQuestion` with `async: true`, works on, and the answer pressed behind
`[ answer ]` reaches it in a message framed `The sminos plugin sent a message:`; the desk shows the
question card and the answer; `sminos chat --host` lists both; a session resumed from a transcript
recorded before the rename still shows its open question. With `doperpowers` disabled, every sminos
verb still runs; with `sminos` disabled, compact, appeal, kairos, the agents pane, interim and the
reload still run.

## Progress

- [x] (2026-10-19 15:30Z) Design and execution written against the code and the engine; the live
      hooks-module order probed (Surprises & Discoveries).
- [ ] Independent spec review and the buildability review (Decision Log, 2026-10-19).
- [ ] M1 — doperpowers' readers accept both names.
- [ ] M2 — MAWS's readers accept both names (a PR in MAWS).
- [ ] M3 — The carve-out and the rename.
- [ ] M4 — The roll and each machine's migration (owner steps).
- [ ] M5 — Cleanup and acceptance.

## Terms

- **Plugin.** A directory with `.claude-plugin/plugin.json` that the harness installs from a
  marketplace; this repository is one marketplace (`.claude-plugin/marketplace.json`) holding
  `doperpowers` (source `./`, the repository root), `devcloud` (`./devcloud`), `to-human`
  (`./to-human`), and after this work `sminos` (`./sminos`). A plugin is addressed as
  `<name>@<marketplace>`: `sminos@doperpowers`.
- **Hooks module.** A plugin's function hooks: the `modules` entry of its `hooks/hooks.json` (here
  always `./mods/register.tsx`), loaded only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. A **mod** is
  one file of it that registers hooks on `on(...)`.
- **Outer and inner.** The engine runs every plugin's hooks on an event as nested wrappers: the
  module registered first is outermost, sees the event first and the result last; the one registered
  last is innermost, closest to the engine's own action. The order is decided per session at load
  (§4).
- **The ask tool.** The MCP tool the ask mod registers, the built-in AskUserQuestion's input plus
  `async`; its name carries its plugin's name, `mcp__<plugin>__AskUserQuestion`.
- **The plugin prompt framing.** How the engine stores a prompt a plugin submits between turns:
  `The <plugin> plugin sent a message:\n<text>\n\nThis is how Claude Code surfaces a prompt a plugin
  submits between turns — …` (engine 2.1.302, `tOt`). The ask mod delivers an async answer this way
  when the session is idle.
- **The marketplace clone.** The harness's checkout of this repository at
  `~/.claude/plugins/known_marketplaces.json`'s `doperpowers.installLocation`
  (`~/.claude/plugins/marketplaces/doperpowers`), updated with the marketplace; stable across plugin
  updates, unlike the versioned plugin cache (`~/.claude/plugins/cache/doperpowers/<plugin>/<version>/`),
  which an update prunes.
- **The daemon.** `sminos daemon run`, one per machine, installed as a launchd agent (macOS) or a
  systemd user unit (Linux) by `sminos daemon install`, which points the service at the marketplace
  clone's `sminos.py`.
- **`$.state`.** Named values the engine holds for the session in memory (they survive a hot reload of
  a plugin's code, not a new process), addressed `{ plugin, key }`; any plugin reads any value, only
  its owner writes it, and `state.set` is a hookable event any plugin may observe.

## Acceptance

Numbered so milestones can point at them. Each is checked on this machine unless it names another.

- **A1 — The plugin exists and is placed.** With `sminos@doperpowers` enabled and the settings of §8
  applied, `claude --debug -p "reply ok" --max-turns 1` in an empty directory with `SMNS_INTERNAL=1`
  writes a debug log (`~/.claude/debug/<session>.txt`) whose `hooks module … loaded (worker,
  environment N, tier …)` lines come in the order `to-human@doperpowers`, `sminos@doperpowers`,
  `doperpowers@doperpowers`, each `tier prepend`, before every other plugin's module (`tier user`),
  and `sminos@doperpowers`'s line lists `session.start`, `tool.call`, `session.append`,
  `attribution.text`, `tool.describe` among its events.
- **A2 — The ask round trip under the new name.** In an interactive session in a project (this
  repository), the model calls `mcp__sminos__AskUserQuestion` with `async: true`; the call returns at
  once with the waiting text; the question shows behind `[ answer ]` and in the `N open questions`
  band; after the answer, the model's next message quotes it, and `sminos chat --host` lists the
  `question` and `answered` events; the desk (MAWS, with M2 merged) shows the question card and its
  answer. The transcript's user row opens `The sminos plugin sent a message:` when the session was
  idle.
- **A3 — A transcript from before the rename resumes whole.** A session resumed from a transcript that
  holds an `mcp__doperpowers__AskUserQuestion` call with `async: true`, accepted and unanswered, shows
  that question open within seconds of the resume (`sminos/tests/mods/live-ask-resume-check.py`, run
  against a recorded transcript), and one whose answer was delivered under the old framing shows it
  answered.
- **A4 — sminos alone, doperpowers alone.** In a temporary HOME with only `sminos@doperpowers`
  enabled, `sminos who --session <id>`, `sminos list`, `sminos watch <member>` and the address line
  on a commit all work, and the start hook prints the guide when the temporary SMINOS_HOME carries an
  enrollment file as `test-guide.sh` fakes one. In a temporary HOME with only
  `doperpowers@doperpowers` enabled, `/appeals` prints, the compact offer
  appears at the gate, the kairos button draws, and no error names sminos in the debug log.
- **A5 — The bridge refuses to sit inside the secrets guard.** In a temporary HOME with `devcloud` and
  `sminos` enabled and no `prependPlugins`, the debug log carries a line opening `sminos: the bridge
  is off` naming `prependPlugins` (an interactive session shows it as a toast too) and
  `$SMINOS_HOME/bridge/<session>.sock` never appears; with `prependPlugins` set, the socket appears
  and the line is absent.
- **A6 — appeal and reload read the asks through the channel.** `tests/mods/appeal.test.ts` passes
  with the judge's evidence carrying an answered ask read from `{ plugin: 'sminos', key: 'ask' }`
  and a pass ending when that value's `answered` count grows; `tests/mods/reload.test.ts` passes with
  the reload waiting while the value says a dialog is up.
- **A7 — The daemon survives the roll and reinstalls at the new path.** On each machine (the MacBook
  `SK`, the Mac mini, each enrolled devcloud host): after the marketplace update, `sminos daemon
  status` reports the daemon running and the hub shows the machine; after `sminos daemon install` and
  the service reload, the service file names `<marketplace clone>/sminos/skills/sminos/scripts/sminos.py`
  (`plutil -p ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist` on macOS,
  `systemctl --user cat sminos-daemon.service` on Linux).
- **A8 — Every suite is green in the new layout.** `ci-gate` on the M3 commit is GREEN with the gates
  of §10, and `claude plugin validate sminos/.claude-plugin/plugin.json` and
  `claude plugin validate .claude-plugin/plugin.json` both pass.
- **A9 — The documents name what is.** `/usr/bin/grep -rn "mcp__doperpowers__AskUserQuestion"`
  outside `docs/`, `archive/`, test fixtures and the readers that accept both names returns nothing;
  `CLAUDE.md`'s repo map has a `sminos/` row; `README.md` lists the four plugins and their install
  lines.

## Design

### 1. The split: what moves, what stays

| Moves to `sminos/` | Stays in doperpowers |
|---|---|
| `skills/sminos/` (SKILL.md, references, scripts: the CLI, daemon, uplink, bridge child, chart, TUI) | the 14 other skills |
| `hooks/mods/bridge.tsx`, `bridge-state.tsx`, `bridge-stream.tsx`, `bridge-requests.tsx`, `bridge-rows.tsx`, `bridge-agents.tsx` | `hooks/mods/compact.tsx`, `appeal.tsx` + `appeal-judge.tsx`, `kairos.tsx`, `agents.tsx`, `interim.ts`, `reload.tsx` |
| `hooks/mods/ask.tsx` (the ask tool, renamed) | `hooks/kairos.sh`, `kairos-toggle.sh`, `compact-instructions.md`, `to-human-stream.sh` + `.awk` |
| `hooks/mods/address.tsx` (the `Sminos-Session:` line; it runs `sminos who`) | `output-styles/to-human.md` (names the ask tool, now sminos's) |
| `hooks/smns-record.sh`, `hooks/smns-guide.sh` | `agents/` (their `disallowedTools` name the ask tool) |
| `types/doperpowers.d.ts`'s `AskSnapshot` → `sminos/types/sminos.d.ts` | `tests/mods/` for the mods that stay, `tests/mods/run-mods-tests.sh`, `tests/mods/interim-audit/` |
| `tests/sminos/` whole → `sminos/tests/`; `tests/mods/ask.test.ts`, `bridge.test.ts`, `address.test.ts`, `test-ask-search.sh`, every `tests/mods/live-*` → `sminos/tests/mods/`; `tests/claude-code/test-smns-guide-hook.sh` → `sminos/tests/` | `tests/claude-code/`, `tests/issue-tracker/`, the rest |

Two files the outline did not list move too: `address.tsx` is sminos (it exists to print the sminos
address, through the CLI) and `smns-guide.sh` is sminos (it runs `sminos guide`). `to-human-stream.sh`
stays: it draws the `<message>` mark of doperpowers' output style, which has no sminos in it.
`reload.tsx` stays: it applies any plugin's update, sminos's included, and its one need of the ask
(§5) becomes a read of the channel.

The board scripts (`skills/issue-tracker/scripts/`) stay in doperpowers and go on calling the sminos
CLI (§9); the board's dispatch is dormant, its scripts tested and armed nowhere, and this work changes
only how they find the CLI.

### 2. The layout of the sminos plugin

```
sminos/
  .claude-plugin/plugin.json     name "sminos", version 1.0.0, types "./types/sminos.d.ts"
  README.md                      what the plugin is; points at SKILL.md, the mods' README, setup.md
  hooks/hooks.json               modules ["./mods/register.tsx"]; SessionStart + Stop: smns-record.sh; SessionStart: smns-guide.sh
  hooks/smns-record.sh
  hooks/smns-guide.sh
  hooks/mods/register.tsx        registerBridge, registerAskBand, registerAsk, registerAddress — in that order
  hooks/mods/ask.tsx, bridge*.tsx, address.tsx, tsconfig.json, README.md
  skills/sminos/SKILL.md, references/, scripts/
  types/sminos.d.ts
  tests/                         run-sminos-tests.sh and the suite (today's tests/sminos/), test-smns-guide-hook.sh
  tests/mods/                    ask.test.ts, bridge.test.ts, address.test.ts, test-ask-search.sh, live-*.py, run.sh
```

The skill keeps its name: `sminos/skills/sminos/SKILL.md` is the skill `sminos:sminos`
(was `doperpowers:sminos`; nothing outside `docs/` invokes it by the qualified name — checked). The
CLI stays at `skills/sminos/scripts/sminos` relative to its plugin root, so `CLAUDE_PLUGIN_ROOT` in the
shell hooks and `$.plugin.root` in `bridge.tsx` and `address.tsx` resolve unchanged, and the guide,
the spawn preamble (`{{SMINOS_CLI}}` is the CLI's own `LAUNCHER`) and the `Sminos-Session:` line need
no change. Relative to the repository root the CLI is `sminos/skills/sminos/scripts/sminos`; every
document that spelled the old repository-relative path says so (§10).

Why a plugin folder at the root like `devcloud/` and `to-human/`, not the root itself: the
marketplace's `doperpowers` entry has source `./`, so the doperpowers cache copies the whole
repository (`devcloud/`, `to-human/`, and now `sminos/` ride along as dead weight; observed in
`~/.claude/plugins/cache/doperpowers/doperpowers/7.188.8/`). That is the price of the existing layout,
accepted; it also means a doperpowers checkout or cache always has a sibling `sminos/` to fall back on
(§9). The alternative, a repository of its own, was declined by the owner (same marketplace).

The mods' tests live under the plugin so `claude plugin test sminos` finds them as the only
`*.test.ts` there — as `to-human/tests/mods/run.sh` and `devcloud/tests/mods/run.sh` do — rather than
staged as `tests/mods/run-mods-tests.sh` must stage doperpowers' (the repository root holds
`application-agents/`' TypeScript tests). The shell and Python suite (`run-sminos-tests.sh`) defines
its root as the plugin root; its `$REPO_ROOT/hooks/smns-record.sh`, `$REPO_ROOT/hooks/hooks.json` and
`$REPO_ROOT/skills/sminos/scripts/sminos` then hold as written (the suite reads no file outside
those three places — checked).

### 3. The tool's new name, and every reader accepting both

The MCP tool a plugin registers is named `mcp__<plugin>__<tool>` by the engine, so the move renames
it: `mcp__sminos__AskUserQuestion`. The plugin prompt framing follows the same way:
`The sminos plugin sent a message:`. Neither old form can be rewritten out of existing transcripts,
and a session may be resumed, compacted or forked across the roll, so **every reader accepts both
names and both framings, for good** — not for a transition. The readers, from the grep of
2026-10-19 (28 files in this repository carry the old name; the ones that match on it rather than
merely mention it):

| Reader | What it matches today | After |
|---|---|---|
| `hooks/mods/ask.tsx`: `rebuildAsks` (`block.name === ASK_TOOL`), `deliveryTexts` (`startsWith(PLUGIN_PROMPT)`), `STORED_FORMS` (the search's literals) | the one name, the one framing | a set of names `ASK_TOOLS` and a set of framings `PLUGIN_PROMPTS` (both plugins' names); `STORED_FORMS` carries one literal per name and per framing |
| `hooks/mods/appeal-judge.tsx`: `PLUGIN_PROMPT = /^The \S+ plugin sent a message:\n/` | any plugin | unchanged |
| `to-human/hooks/mods/to-human.tsx`: `ASK_TOOL`, `ASK_DELIVERY` | the one name, the one framing | both |
| `skills/sminos/scripts/sminos.py`: `ASK_TOOL`, `PLUGIN_PROMPT` (the record export, `sminos_marks`' consumer) | the one name, the one framing | both |
| `hooks/mods/bridge.tsx`: `isDialog` by `next.origin.plugin === PLUGIN`; `bridge-rows.tsx`: `origin.name !== PLUGIN` | the plugin's own name | the plugin's own name, which is now `sminos` — correct as is once the mods move together |
| MAWS (§11) | the one name in `classify.ts`, the fake machine, the desk-web `ask-answer.ts` framing and `origin.name`; suffix matches in `project.ts` and `card-state.ts` | both |

The mid-turn framing (`The <plugin> plugin sent a message while you were working:`) is matched by no
reader in either repository — the ask submits only when the session is idle — and stays unmatched.

The register of the tool (`tool.describe` and `tool.call` matchers in `ask.tsx`, `ASK_TOOL`,
`WITHDRAWN`'s sentence, the `AskSnapshot` key) moves to the new name in M3, with the readers already
dual. The nine agent definitions' `disallowedTools` name the new tool beside the old through M4 (an
entry naming no tool is inert, and a session resumed mid-roll may still see the old one); M5 drops
the old. The output style names the new tool. The owner's own `~/.claude/agents/astra.md` and
`sol-xhigh.md` carry the old name in `disallowedTools`; until the owner edits them (M4, an owner
step), an `astra` or `sol-xhigh` subagent is offered the renamed tool and a call of it is refused by
the ask's own `SUBAGENT_REFUSAL` — a refusal, not a hang.

Readers ship before the rename (M1, M2), so no running or resumed session breaks: a session on the
dual-reader doperpowers reads old rows; a session on sminos reads old and new rows; the desk reads
both from the day M2 merges.

### 4. Hook order across plugins

**How the engine orders hooks modules** (2.1.302, `mBr`, `wSn`, `Stn`, `Dqn`, `rSr` in
`cli.pretty.js` 743472–744552, confirmed live in Surprises & Discoveries):

1. By tier: `prepend` (the user settings' `prependPlugins`, or an organization's seat), then `user`
   (every plugin not named by a tier key), then `append` (`appendPlugins`), then `builtin`. Within
   `prepend` and `append` the list's order is the rank, first outermost.
2. Within one rank, by manifest `dependencies`: the sort takes, repeatedly, the first module that no
   remaining module depends on. So a dependent registers before (outside) its dependency — and a
   module that others depend on is pushed behind **every** module nobody depends on, not merely
   behind its dependents.
3. Otherwise, in the order the enabled plugins were chosen, which is `~/.claude/plugins/installed_plugins.json`'s
   key order — install order.
4. A dependency is enabled with its dependent (`rootRequiredByDependent`, 779611); an unmet one is
   reported.

**What this did to today's doperpowers.** `to-human` depends on `doperpowers`, so rule 2 pushed
doperpowers' module behind `cua` and `devcloud`: the live order is `prompt-autosave, cua, devcloud,
to-human, doperpowers`. The bridge, "registered first, so its hooks are the outermost", is outermost
only within doperpowers; across plugins it sits **inside devcloud's secrets guard**, so its `tool.call`
hook sees a Bash or Write call's input after the guard restored the secret bytes into it (the guard
restores handles before calling `next`) and the result before the guard scrubs it (it scrubs on the
way out of `next`; `bridge.tsx` emits `input` from `e` and `text` from what `next(e)` returned). Rows
are safe either way: the guard's `session.append` hook scrubs a row before calling `next`. The
stream to the hub carries unscrubbed tool inputs and results on this machine today. This spec does
not fix today's order (that is a
settings change the owner makes, §8, and it fixes itself in M4); it designs the split so the order
is declared, not inherited.

**What the order must be**, outer to inner:

- `to-human` outside `sminos`: it sees the ask's rows before the ask draws them, and its band above
  the prompt draws under the ask's band (the reason it was outside doperpowers).
- `sminos` outside `devcloud`: the bridge posts what the session showed and kept, so it must see a
  call's input with its handles and its result scrubbed, never the bytes. **This is a safety
  invariant.**
- `sminos` outside `doperpowers`: the bridge reports the appeal's note on a blocked result and its
  allow on a passed re-run as the session showed them, and interim sits inside the ask's
  `prompt.submit` (the ask puts back what it attached to a prompt dropped beneath it). Fidelity, not
  safety: the desk reads the appeal's note from the transcript row either way.
- `doperpowers` and `devcloud` in either order (the appeal's note is text on a deny, which the guard
  scrubs or not; neither reads the other).

**The decision: the owner's user settings place the three, and sminos declares nothing.** On each
machine `~/.claude/settings.json` carries

```json
"prependPlugins": ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]
```

which puts them in the `prepend` tier in that order, outside every user-tier plugin (`devcloud`, `cua`,
`ptc`, the journals), whatever is installed later and in whatever order. `to-human`'s manifest keeps a
dependency, on `sminos` instead of `doperpowers` (it needs the ask's rows; enabling to-human then
enables sminos) — it has no ordering effect inside the prepend tier and documents the need. `sminos`
depends on nothing; `doperpowers` depends on nothing.

Why not dependencies alone: the engine's only dependency rule puts the *dependent* outside, so
sminos outside doperpowers would need `sminos` to depend on `doperpowers` — the opposite of a
standalone sminos — and, by rule 2, to-human depending on sminos pushes sminos *inside* every
undepended plugin, devcloud included: the dependency that is needed produces the order that is
forbidden. Why not install order: a fresh `sminos@doperpowers` is appended last to
`installed_plugins.json` and registers innermost, inside devcloud. Why doperpowers is in the list too:
two entries would hold the safety invariant; the third restores the nesting the mods were written
for, at the cost of one more name in the same line. Why the settings file and not a manifest key:
the engine offers no manifest key for placement; `prependPlugins` is its one lever for "a mod above
the user tier", and the owner edits the same file for `enabledPlugins` anyway (§8). The engine honours
the user's key only where no managed policy, organization seat or hosted session places mods
(`E5`); a machine where it is ignored fails A1 and keeps its bridge off by the probe below — the
signal to return to this spec, not a silent degradation.

**The bridge proves its place before it streams.** `devcloud` sets `{ plugin: 'devcloud', key:
'secrets-guard' }` in its `session.start` hook before calling `next` (`secretsStart`), and `$.state`
starts empty in every process. So at the bridge's `session.start`, before it calls `next`, a read of
that value tells the order: present means devcloud's hook already ran, devcloud is outside sminos, and
the bridge would stream raw results. Then the bridge starts no child and says why — a toast and a
debug line, `sminos: the bridge is off — sminos must load outside devcloud; set prependPlugins in
~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]`
— and the session is unreachable from the desk for its life, as a session without function hooks is.
Absent means devcloud is inside sminos or not installed; the bridge starts. The ask, the address and
the shell hooks serve either way (none of them carries a tool result). The alternative, streaming and
hoping, is today's state; a loud refusal on one machine beats a quiet leak to the hub.

### 5. The channels that replace the imports

Three mods that stay import from mods that move. Across plugins a module cannot import another's
file (each plugin's module is evaluated in a realm of its own; probed 2026-10-17, 2.1.302, per
`secrets.tsx`), so each import becomes a channel the engine provides.

**appeal ← ask (`asyncAsks`, `observeAsks`).** The ask already keeps its asks in `$.state` so a
reload takes them up (`KEPT = { plugin: 'doperpowers', key: 'ask' }`, an `AskSnapshot`). That value
becomes the channel, under the new plugin: `{ plugin: 'sminos', key: 'ask' }`, shape 2, which adds
what the readers need (Interfaces, I1) and is written on every change of any field it carries. appeal
reads it at evidence time (`evidence()`: the answered asks' questions and answers for the judge) and
hooks `state.set` on the reference to bump its epoch when the human spoke — when `answered` grew,
which counts async answers and blocking dialog outcomes alike, the two cases `observeAsks` reported
as `answered` and `dialog`. Reading is allowed ("any plugin reads any value; its owner alone writes
it"; `cua` reads devcloud's marker the same way, `one-guard.tsx`), and `state.set` is the engine's
hookable write event (`on("state.set", REF, ...)`, typed `StateSetEvent`). With sminos absent the
value is `undefined` at version 0: no asks in the evidence, no bumps — doperpowers alone is whole.
The alternative, appeal reading answered asks from the transcript (`$.session.messages()` it already
fetches), would copy the delivery grammar and both framings into doperpowers — the knowledge this
split moves out — and gives no notice at the moment of an answer; rejected.

**reload ← ask (`isAskDialogUp`, `isMainTurnRunning`).** reload's idle check is synchronous (its
tick reads `io.isAskDialogUp()` and `io.isTurnRunning()`), so it mirrors `isDialogUp` into a variable
of its own from a `state.set` hook on the same reference (no value ever written reads as no dialog),
and tracks the main turn itself with `turn.start` / `turn.complete` hooks matched on `turnId`
(compact.tsx and agents.tsx hold the module's one unmatched registration of each; a matched one is
unlimited). Why not read `isTurnRunning` from the channel too: reload must work with sminos absent,
and a turn is the engine's event, not the ask's.

**compact → bridge (`compacted`).** compact calls `compacted(null, outcome.messages)` after its own
`$.session.compact` because "its rows pass no hook of this plugin's, the bridge's included" — the
re-entry rule skips the calling plugin's hooks. After the split the bridge is another plugin: its
`session.compact` hook (`{ trigger: /^/ }`, which already calls `compacted` for the person's
`/compact`) fires for doperpowers' compaction as for any other. The import and the call go; M3 proves
the bridge names a compact-tool compaction's rows through the hook (a `bridge.test.ts` case driving
`session.compact` with the compaction's result, and `live-compact-offer-check.py`, which already
exercises the path). The bridge's own `compact` command still calls `compacted` directly (same plugin,
re-entry).

**The ask's snapshot at the roll.** `/reload-plugins` swaps both modules at once; the new ask module
finds no `sminos.ask` and would start empty, forgetting open async asks until the next resume. For one
release it reads `{ plugin: 'doperpowers', key: 'ask' }` when its own key is empty and takes a
shape-1 value up as shape 2 (`isDialogUp: false`, `answered: 0`). M5 removes the fallback.

### 6. to-human's dependency

`to-human/.claude-plugin/plugin.json`'s `dependencies` becomes `["sminos"]`. to-human stays its own
plugin for the reason it was made one: the engine runs none of a plugin's render hooks on a row that
plugin submitted, and sminos submits the ask's deliveries and the bridge's sminos deliveries while
doperpowers submits the compact mod's resume prompt. Its readers accept both names (§3). Its version
moves (0.1.1 → 0.2.0) in M3 with the dependency.

### 7. The daemon, the service, and the transition shim

`sminos daemon install` writes the service to run the marketplace clone's `sminos.py` (`installed_cli`
in `sminos_daemon.py`: `<installLocation>/skills/sminos/scripts/sminos.py`), a path that outlives
plugin updates; after the split that path is `<installLocation>/sminos/skills/sminos/scripts/sminos.py`,
and `installed_cli`, its error text, `sminos-daemon.plist`'s and `sminos-daemon.service`'s comments,
and `devcloud/boot/devcloudlib/sminos_host.py` (step 11, which looks for the same file) all name it.
The marketplace's name, and so `known_marketplaces.json`'s entry, do not change.

**What happens to a running daemon when the clone updates.** The daemon watches the `.py` files beside
its own (`own_code`); when the set changes it stops its uplink and re-executes itself at the path it
started from (`restart_in_place`: `os.execv(sys.executable, [sys.executable] + sys.orig_argv[1:])`),
and when that fails it exits for the service manager to restart it under its throttle. After the
split the clone no longer has `skills/sminos/scripts/`: the exec fails, the service crash-loops every
60 s on a path that no longer exists, and the machine is off the desk until `daemon install` is
rerun — which the owner may not be there to do (the reload mod updates the marketplace clone every
five minutes on its own).

So doperpowers keeps, for the transition, a **shim** at the old path: `skills/sminos/scripts/sminos.py`
(and the `sminos` launcher beside it, unchanged) whose whole job is to find the real CLI and
`os.execv` it with the same arguments — the marketplace clone's `sminos/skills/sminos/scripts/sminos.py`
first, else the installed sminos plugin's (`installed_plugins.json`, `sminos@doperpowers`'s
`installPath`), else the sibling `../../../sminos/skills/sminos/scripts/sminos.py` of a checkout; when
none exists it prints one line naming `sminos daemon install` and exits 1. The running daemon's
restart then lands in the shim and goes on under the new code, with `sys.orig_argv` now the new path;
a service restart or a reboot goes through the shim again until `daemon install` is rerun on that
machine (M4), after which the shim is dead code and M5 removes it. The alternative — accept the
crash loop and make the rerun the first owner step — was rejected for the Mac mini and the devcloud
hosts, which update unattended.

The suite's test of the cache layout (`run-sminos-tests.sh`, "A CLI running from the versioned plugin
cache installs the marketplace clone's CLI") moves its fixture to
`cache/doperpowers/sminos/9.9.9/` and `<clone>/sminos/skills/sminos/scripts/sminos.py`.

### 8. Each machine's migration — the owner's steps

`~/.claude/settings.json` is the owner's file: no agent edits it. The steps below are performed by the
owner, or by a session on the owner's explicit approval of that step on that machine; the spec
names them so M4 can be run as a checklist. The machines: the MacBook `SK`, the Mac mini, each
enrolled devcloud host (whose `~/.claude` is received from git — one commit there carries the settings
to every host).

1. `enabledPlugins`: add `"sminos@doperpowers": true` (keep `doperpowers@doperpowers`, `to-human@doperpowers`,
   `devcloud@doperpowers` as they are).
2. `prependPlugins`: `["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]` (§4).
3. `~/.claude/agents/astra.md` and `sol-xhigh.md`: `disallowedTools` names `mcp__sminos__AskUserQuestion`
   (and keeps `mcp__doperpowers__compact`).
4. In each live session: `/reload-plugins` (or the reload mod does it when the session is idle); a
   session that must keep its open asks across the swap keeps them (§5).
5. `sminos daemon install`, then reload the service: on macOS `launchctl bootout gui/$(id -u)/com.doperpowers.sminos-daemon`
   then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`;
   on Linux `systemctl --user daemon-reload && systemctl --user restart sminos-daemon.service`. Until
   this step the daemon runs through the shim (§7).
6. On a devcloud host: update the `devcloud` plugin (M3 bumps it) before the next boot; `devcloud-boot`
   step 11 then finds the CLI at the new path.
7. Verify A1 and A7 on the machine.

The order across machines does not matter: the hub reads events, not plugin versions, and both
daemons speak the same protocol.

### 9. Board scripts, the guide, the preamble, plugin roots

- **The board scripts** (`skills/issue-tracker/scripts/_lib.sh`, `execute-dispatch.sh`,
  `board-sweep.sh`) default `SMINOS_CLI` to `$SKILL_DIR/../sminos/scripts/sminos`, a sibling skill that
  no longer exists. `_lib.sh` gains one resolver the other two call: `$SMINOS_CLI` when set; else the
  marketplace clone's `sminos/skills/sminos/scripts/sminos` (the path the daemon runs, read from
  `known_marketplaces.json`); else the checkout's sibling `$REPO_ROOT/sminos/skills/sminos/scripts/sminos`
  (present in a checkout and in the doperpowers cache, §2); else `die` naming `SMINOS_CLI`. The
  issue-tracker tests set `SMINOS_CLI` to the checkout's CLI.
- **The guide** (`sminos guide`, printed by `smns-guide.sh` at session start) prints the CLI's
  absolute path from its own location; nothing to change. **The spawn preamble**'s `{{SMINOS_CLI}}` is
  the CLI's `LAUNCHER`; nothing to change.
- **`CLAUDE_PLUGIN_ROOT`** in `smns-record.sh` and `smns-guide.sh`, and **`$.plugin.root`** in
  `bridge.tsx` and `address.tsx`, resolve to the sminos plugin's root once the files live there; the
  `skills/sminos/scripts/sminos` suffix holds. `reload.tsx`'s `$.plugin.root` is doperpowers' own.
- **The sminos CLI's own references to its plugin**: `installed_cli`'s clone path (§7) and its error
  text; `sminos.py`'s `ASK_TOOL` / `PLUGIN_PROMPT` (§3). Its `.smns`, registry and log layout do not
  change.

### 10. Versioning, marketplace, gates, documents

- **Versions, one commit (M3).** `.version-bump.json` gains a `sminos` plugin: files
  `sminos/.claude-plugin/plugin.json` (`version`) and `.claude-plugin/marketplace.json`
  (`plugins[name=sminos].version`), audit root `sminos`; doperpowers' audit `exclude` gains `sminos`.
  `scripts/bump-version.sh --plugin sminos` then works. Starting version **1.0.0**: the component is
  mature and its protocol (DX5) is pinned by MAWS; a 0.x would misstate it (devcloud and to-human
  started at 0.1.0 as new work). doperpowers moves to 7.189.0, to-human to 0.2.0, devcloud to 0.5.0,
  each by the script, in the same M3 commit as the change: the marketplace updates by version number
  alone.
- **The marketplace entry.** `.claude-plugin/marketplace.json` adds `sminos`, source `./sminos`, the
  description of what it is (the orchestration interface: the machine side of the MAWS desk, and how
  sessions and humans reach each other). `tests/codex/test-marketplace-manifest.sh`'s
  `expected_sources` gains `"sminos": "./sminos"`.
- **Gates** (`.github/ci-kit.yml`): `sminos` and `sminos-suites` run `sminos/tests/run-sminos-tests.sh`
  with paths `["sminos/**", ".github/**"]`; a new `sminos-mods` gate installs claude-code and bun as
  `mods` does and runs `sminos/tests/mods/run.sh` (`claude plugin test sminos` then
  `sminos/tests/mods/test-ask-search.sh`), paths `["sminos/**", ".github/**"]`; `board-api` and
  `issue-tracker` paths replace `skills/sminos/**` with `sminos/**` (the board scripts call the CLI);
  `mods` keeps `hooks/**` and `tests/mods/**`; `claude-code`, `devcloud-mods`, `to-human-mods`,
  `devcloud`, `repo-checks` as they are (their files change under them). `tests/claude-code/run-skill-tests.sh`
  drops `test-smns-guide-hook.sh`, which runs in the sminos suite.
- **Documents.** `CLAUDE.md`'s repo map: a `sminos/` row that takes the sminos paragraph from the
  `skills/` row and the bridge, ask and address paragraphs from the `hooks/` row, and says the plugin
  is standalone, where the CLI is, and the placement rule of §4; the `hooks/` row keeps kairos,
  compact, appeal, agents, interim, reload and the streaming hook; the `to-human/` row's dependency
  sentence names sminos and the real ordering rule (§4, rule 2 — the current "at equal rank the
  dependent is outer" is true but not the whole of it); the working conventions name
  `--plugin sminos`. `README.md`: the plugin list and install lines (`/plugin install sminos@doperpowers`,
  and the `prependPlugins` line), the `sminos` and `to-human` bullets. `hooks/mods/README.md`: the ask,
  bridge and address sections move to `sminos/hooks/mods/README.md`, the intro names the plugin's mods
  as they are. `skills/sminos/SKILL.md` and `references/setup.md`: the CLI sentence names the sminos
  plugin. `devcloud/README.md` and the devcloud spec's §8 are not rewritten; a dated line in this
  spec's Decision Log records the path change they describe. Old specs (`2026-10-13-ask-async-design.md`
  and the rest) are history and keep the old name.

### 11. MAWS's side

MAWS reads the tool name and the framing in these places on `origin/master` (2026-10-19), and all of
them must accept both before the rename ships (M2):

| File | Today | Change |
|---|---|---|
| `src/renderer/src/transcript/model/classify.ts` | `ASK_MOD_TOOL = 'mcp__doperpowers__AskUserQuestion'`, keyed into `ROW_KIND_TOOLS` | both names keyed as `question` (a set `ASK_MOD_TOOLS`; `ask-mod.ts`'s comment follows) |
| `apps/desk-web/src/conversation/ask-answer.ts` | `PLUGIN = 'doperpowers'` against `origin.name`; `PLUGIN_PROMPT = /^The doperpowers plugin sent a message:\n/` | a set of plugin names; `/^The (?:doperpowers\|sminos) plugin sent a message:\n/` |
| `apps/desk-hub/fake-machine/machine.ts` | `QUESTION_TOOLS = new Set(['AskUserQuestion', 'mcp__doperpowers__AskUserQuestion'])` | the sminos name added |
| `src/shared/owner/contract.ts` | the contract's sentence "`mcp__doperpowers__AskUserQuestion` is not available here" | names both (or "the doperpowers or sminos plugin's ask tool"); `contract.test.ts`'s needle follows. Whether the contract's version key moves is MAWS's rule to apply: its meaning (ask through `mcp__maws__ask` there) is unchanged |
| `e2e/to-human-live.spec.ts` | `nativeAsks` filter on the one name | both |
| `apps/desk-hub/src/objects/project.ts` (`endsWith('__AskUserQuestion')`), `apps/desk-web/src/conversation/card-state.ts` (same) | suffix | no change |
| recordings, `session-view.py`, tests naming the old name | fixtures | no change; a new fixture under the new name is welcome but not required |

The desk reads `raised.tool` from the bridge's events, which carry the registered name; a machine on
sminos 1.0.0 raises `mcp__sminos__AskUserQuestion`, a machine not yet rolled raises the old name, and
the desk must read a project whose machines are on either. M2 is a PR in MAWS, written by a session in
that repository from this section and the ticket M2 registers; it ships before M3's roll (M4).

## Out of scope

- The peer roster (a separate initiative, in flight).
- A repository of its own for sminos, or a change to the marketplace's name (`doperpowers`), which
  `known_marketplaces.json` and every daemon's service file name.
- Any change to DX5 (the bridge protocol) or to what the stream carries; the hub and the desk are
  readers of names only here.
- Fixing today's order on the owner's machines before M4 (a settings change the owner makes; §8).
- Re-cutting the old specs under the new name.
- The `qa-loop`, the board's dispatch, and the worker protocols, which stay dormant and unarmed.

## Execution

### Constraints that bind every milestone

- Execution starts after doperpowers-79 (d88ef4c3) merges; M1 is rebased on it.
- Every reader of the tool name and the framing accepts both, for good; no milestone removes the old
  name from a reader (§3). M1 and M2 ship before M3's rename.
- No milestone edits `~/.claude/settings.json`, `~/.claude/agents/*.md`, or the service files on any
  machine; M4 lists those as owner steps and records what the owner did.
- Never print or copy `~/.claude/sminos/daemon/hub.json` or any credential-bearing file; never touch
  `~/.config/claude-secrets`. Manual runs of a working copy's sminos, hook or mod use a temporary
  HOME and SMINOS_HOME (`tests/sminos/run-sminos-tests.sh` shows how). Heavy commands run one at a
  time inside `/tmp/maws-review/with-slot.sh`; `grep` is ugrep on this machine, use `/usr/bin/grep`.
- Version bumps go through `scripts/bump-version.sh` (one plugin per call), in the same commit as the
  change (CLAUDE.md, working conventions). Commit messages carry no attribution trailer other than
  the `Sminos-Session:` line the engine adds.
- Each plugin's module respects the engine's limits as the code does today: one unmatched
  registration of an event per module; `$` passed only to functions in the module's own file; the
  state reference's `plugin` and `key` as literals.
- The engine is 2.1.303 on this machine; a milestone that finds the engine's behaviour differs from
  §4 or §5 records it in Surprises & Discoveries and returns to the spec's author before building on
  it.
- MAWS is read at `/Users/new/Developer/GitHub/MAWS` (the checkout is on `sminos-hub`; read
  `origin/master` with `git show` / `git grep`); M2 alone writes there, from its own worktree.

### Plan of Work

Five milestones, ordered so no live session breaks: readers first in both repositories, then the
carve-out with the rename in one release, then the roll with each machine's steps, then cleanup. M1
and M2 are independent of each other and may run side by side; M3 waits for both; M4 waits for M3's
release; M5 waits for every machine of M4.

### M1 — doperpowers' readers accept both names

**What exists at its end.** A doperpowers release (7.188.x, bumped) whose ask, to-human and sminos
record export read a transcript carrying either tool name and either framing, and whose appeal judge
already does. A session on it, resumed later from a transcript written by sminos 1.0.0, sees its
asks.

**What it touches.** `hooks/mods/ask.tsx` (`ASK_TOOL` → `ASK_TOOLS`, `PLUGIN_PROMPT` →
`PLUGIN_PROMPTS`, `rebuildAsks`, `deliveryTexts`, `STORED_FORMS`, `searchArgs` / `grepArgs`'s
literals); `to-human/hooks/mods/to-human.tsx` (`ASK_TOOL`, `ASK_DELIVERY`); `skills/sminos/scripts/sminos.py`
(`ASK_TOOL`, `PLUGIN_PROMPT` and `_delivery_texts`); their tests (`tests/mods/ask.test.ts`,
`tests/mods/test-ask-search.sh`, `to-human/tests/mods/to-human.test.ts`, `tests/sminos/run-sminos-tests.sh`
around `ASK =`). Versions: doperpowers and to-human.

**Decisions.** The registered name stays `mcp__doperpowers__AskUserQuestion` here: the tool's own
`tool.describe` / `tool.call` matchers, `WITHDRAWN`, and the bridge's `PLUGIN` do not change in M1.
The new name and framing are spelled once each, beside the old, as the second member of each set.
The search's `STORED_FORMS` gets one literal per name and per framing so a transcript over 4 MiB is
still found by `grep -F` (a5bc8c15). The record export's Python mirrors the TypeScript sets.

**What it does not touch.** No file moves; no manifest, gate or document changes beyond the
version bump.

**What it proves.** A3's reader half: tests pin a transcript whose call carries the old name and
whose delivery carries the new framing, and the reverse, each rebuilt as one open or answered ask;
to-human's `promptRow` reads both framings as the person's answer; `sminos record` exports a
`question` and `answered` from each. `tests/mods/run-mods-tests.sh`, `to-human/tests/mods/run.sh`,
`tests/sminos/run-sminos-tests.sh` green; `ci-gate` GREEN.

### M2 — MAWS's readers accept both names

**What exists at its end.** A MAWS PR, merged, with the changes of §11: the desk, the renderer's
transcript model, the fake machine and the contract's sentence read both names and both framings;
the desk shows a question raised under either name as a question card and its answer on the row.

**What it touches.** The files of §11's table, in MAWS, on a branch off `origin/master`, in a
worktree of that repository.

**Decisions.** A ticket on MAWS's board registers this milestone with §11 as its body; the session
that takes it (a MAWS session, or this initiative's executor dispatched into that repository with the
spec path) owns the PR. The contract's version key moves only if MAWS's contract rule says a change of
wording moves it; the meaning does not change. Fixtures and recordings under the old name stay.

**What it does not touch.** The desk's protocol (`apps/desk-hub/src/protocol/session.ts`'s comments
may name both); no doperpowers file.

**What it proves.** A2's desk half: MAWS's unit tests for `classify.ts`, `ask-answer.ts`,
`card-state.ts` and the fake machine pin both names (`pnpm test` in MAWS, the files' suites);
`e2e/to-human-live.spec.ts` keeps passing with its filter widened. The PR URL is recorded in Progress.

### M3 — The carve-out and the rename

**What exists at its end.** One release of four plugins: `sminos` 1.0.0 at `sminos/` with the layout
of §2, the tool `mcp__sminos__AskUserQuestion`, the channel of §5, the bridge's order probe of §4,
the shim of §7; `doperpowers` 7.189.0 without sminos, reading the asks through the channel, with the
board resolver of §9; `to-human` 0.2.0 depending on sminos; `devcloud` 0.5.0 looking for the CLI at the
new path. Every gate green in the new layout; the documents of §10 say what is.

**What it touches.** The moves of §1 (`git mv`, so history follows); `sminos/.claude-plugin/plugin.json`,
`sminos/hooks/hooks.json`, `sminos/hooks/mods/register.tsx`, `sminos/types/sminos.d.ts`,
`sminos/README.md`, `sminos/tests/mods/run.sh`; `hooks/hooks.json` and `hooks/mods/register.tsx`
(doperpowers' remaining mods and shell hooks); `hooks/mods/appeal.tsx`, `reload.tsx`, `compact.tsx`
(§5); `ask.tsx`
(the name, `KEPT`, the shape-1 fallback, `isDialogUp` and `answered` in the snapshot); `bridge.tsx`
(the probe); `agents/*.md` (nine), `output-styles/to-human.md`; `skills/issue-tracker/scripts/_lib.sh`,
`execute-dispatch.sh`, `board-sweep.sh` and the issue-tracker tests' `SMINOS_CLI`; `skills/sminos/scripts/sminos_daemon.py`
(`installed_cli`), the two service templates, `skills/sminos/scripts/sminos.py` (the shim, in
doperpowers, new) and the `sminos` launcher beside it; `devcloud/boot/devcloudlib/sminos_host.py`;
`.claude-plugin/marketplace.json`, `.version-bump.json`, `to-human/.claude-plugin/plugin.json`,
`.github/ci-kit.yml`, `tests/codex/test-marketplace-manifest.sh`, `tests/claude-code/run-skill-tests.sh`,
`sminos/tests/run-sminos-tests.sh` (its root, the cache fixture of §7, the hook paths); `CLAUDE.md`,
`README.md`, `hooks/mods/README.md` → `sminos/hooks/mods/README.md`, `sminos/skills/sminos/SKILL.md`,
`references/setup.md`.

**Decisions.** One milestone, one release: the rename, the move, the manifests and the gates must land
in the same cutover (a half state — a tool registered under one name by two plugins, or a gate
pointing at a path that moved — is invalid). The sminos tests' root variable is the plugin root. The
doperpowers types file keeps the `types` key only while it declares a value (it declares none after
the move; drop the key or keep an empty contract — the executor's call, with `claude plugin validate`
as the judge). The appeal's read of `{ plugin: 'sminos', key: 'ask' }` types through `import type`
from `../../sminos/types/sminos` (erased at run time; `devcloud/types/devcloud.d.ts` shows the read
form); if `claude plugin validate` on doperpowers refuses a read of a contract that is not enabled in
the staged test plugin, the validate output is the authority and the doperpowers types contract
declares the key it reads. The bridge's probe reads devcloud's key with the same form. The shim is
Python 3.9-safe (it may run under macOS's own `python3` before the real CLI's version check). The
board resolver reads `known_marketplaces.json` with `python3 -c` or `jq`, whichever `_lib.sh` already
uses. The `sminos/README.md` is short: what the plugin is, the install lines with `prependPlugins`,
pointers.

**What it does not touch.** `~/.claude/*` on any machine; MAWS; the old specs; the dormant board
doctrine; DX5.

**What it proves.** A1 (the module loads with the events listed; the order of the `loaded` lines, in
a temporary HOME with the settings of §8 applied there), A5 (the probe, in a temporary HOME with
devcloud enabled and no `prependPlugins`, then with), A6 (`tests/mods/appeal.test.ts`,
`tests/mods/reload.test.ts` with a fake `$.state`), A8 (every gate; both validates). Tests pin: the
ask tool registers under the new name and the old name is refused with `WITHDRAWN`'s sentence naming
the new; the snapshot carries `isDialogUp` and `answered`, and a shape-1 value under doperpowers' key
is taken up once; the bridge names a compact-tool compaction's rows through its `session.compact`
hook; `installed_cli` returns the new clone path and its refusal names it; the shim execs the clone's
CLI, else the installed plugin's, else the sibling, else exits 1 naming `daemon install`; the resolver
finds the CLI in each of its three places. The issue-tracker gate runs the board scripts against the
checkout's CLI through `SMINOS_CLI`.

### M4 — The roll and each machine's migration

**What exists at its end.** Every machine runs sminos 1.0.0 placed as §4 says, with its daemon
installed at the new path, and the owner's agents name the new tool. The desk shows all machines.

**What it touches.** Nothing in the repository but this spec's Progress and record. The owner's
files and services of §8, by the owner or on their explicit approval, one machine at a time.

**Decisions.** The steps of §8 in that order on each machine; A1 and A7 checked on each; a session
with an open async ask at the swap is the test of §5's fallback (ask on one session before the
`/reload-plugins`, answer after). The executor of this milestone is the session the owner works with:
it prepares each step's exact command and waits for the owner's word per machine.

**What it does not touch.** The code.

**What it proves.** A1, A2 (end to end, with M2 merged), A3 (a real resume on a transcript from before
the roll), A4 (both halves in temporary HOMEs on this machine), A7 (each machine).

### M5 — Cleanup and acceptance

**What exists at its end.** The shim and the ask's shape-1 fallback are gone, the agent definitions
name one tool, and the acceptance section stands executed.

**What it touches.** `skills/sminos/` in doperpowers (removed whole), `hooks/mods/ask.tsx`
(the fallback), `agents/*.md`, versions of doperpowers and sminos.

**Decisions.** Runs only once every machine of M4 has rerun `daemon install` (A7 everywhere): the
shim is what a not-yet-reinstalled service runs. The readers keep both names (§3).

**What it does not touch.** Any reader's acceptance of the old name.

**What it proves.** A9, and the whole of A1–A8 re-run as written in Concrete Steps, plus every suite.

### Concrete Steps

Working directory is the repository root of the worktree unless shown.

```
# M1, M3, M5 — the suites and the gates
tests/mods/run-mods-tests.sh                 # doperpowers' mods
to-human/tests/mods/run.sh                   # to-human's mods
sminos/tests/mods/run.sh                     # from M3: sminos' mods (claude plugin test sminos; test-ask-search.sh)
bash sminos/tests/run-sminos-tests.sh        # from M3 (tests/sminos/run-sminos-tests.sh before); SMINOS_PART=core|suites
claude plugin validate sminos/.claude-plugin/plugin.json
claude plugin validate .claude-plugin/plugin.json
ci-gate                                      # on the committed HEAD; expect GREEN <run-url>

# A1 — the order, on a HOME that has the settings of §8 (a temporary one in M3, the real one in M4)
d=$(mktemp -d) && cd "$d" && SMNS_INTERNAL=1 /tmp/maws-review/with-slot.sh claude --debug -p "reply ok" --max-turns 1
/usr/bin/grep -h "hooks module .* loaded (worker" "$(ls -t ~/.claude/debug/*.txt | head -1)"
# expect, in this order:
#   hooks module to-human@doperpowers loaded (worker, environment 1, tier prepend); events: ...
#   hooks module sminos@doperpowers loaded (worker, environment 2, tier prepend); events: session.start,...,tool.call,...,session.append,...,attribution.text,...,tool.describe,...
#   hooks module doperpowers@doperpowers loaded (worker, environment 3, tier prepend); events: ...
#   hooks module <others> loaded (worker, environment N, tier user); ...
# (the engine logs a "hooks module order: dependencies register ..." line only when the dependency sort changed the order)

# A5 — the probe, in a temporary HOME with devcloud and sminos enabled and no prependPlugins
#   expect a debug line opening "sminos: the bridge is off" (a toast in an interactive session), and no $SMINOS_HOME/bridge/<session>.sock

# A7 — on each machine, after the roll
sminos daemon status                         # running; the hub lists the machine
sminos daemon install                        # wrote <plist|unit>: it runs <clone>/sminos/skills/sminos/scripts/sminos.py on <python>
plutil -p ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist | /usr/bin/grep sminos.py     # macOS
systemctl --user cat sminos-daemon.service | /usr/bin/grep ExecStart                                # Linux

# A9 — after M5
/usr/bin/grep -rn "mcp__doperpowers__AskUserQuestion" --exclude-dir=docs --exclude-dir=archive --exclude-dir=evals .
# expect: only the dual readers (ask.tsx, to-human.tsx, sminos.py, appeal-judge.tsx's regex) and their tests
```

### Interfaces and Dependencies

**I1 — The ask snapshot, `sminos/types/sminos.d.ts`** (the one value sminos publishes; read by
appeal and reload in doperpowers, written by the ask alone, on every change of any field):

```ts
export type AskSnapshot = {
  shape: 2
  /** The session's async asks, oldest first: the call's id, its questions, and the engine's text once answered. */
  asks: {
    id: string
    questions: { question: string; header: string; options: { label: string; description: string; preview?: string }[]; multiSelect: boolean }[]
    status: 'open' | 'answered'
    answer?: string
  }[]
  /** The answers that have not reached the model, in the order given: the call's id and the delivery text. */
  undelivered: { id: string; text: string }[]
  isTurnRunning: boolean
  /** An ask's dialog is up: open, or queued behind another. A reload waits for it. */
  isDialogUp: boolean
  /** How many times the human answered this session — an async ask's delivery, a blocking dialog's outcome — so a reader ends what must end when the human speaks (the appeal's passes). */
  answered: number
  /** Where the session's pasted pictures are kept, once the session start named it. */
  store?: { slug: string; sessionId: string; root?: string | null }
}

declare module 'claude-code' {
  interface PluginState {
    sminos: { ask: AskSnapshot }
  }
}
```

The reference, written as a literal in each reader: `{ plugin: 'sminos', key: 'ask' } as const`.
A reader hooks writes with `on('state.set', { plugin: 'sminos', key: 'ask' }, ($, e, next) => ...)`
and reads `e.value` as an `AskSnapshot`; `$.state.get(ref)` answers `{ value, version }`, `undefined`
at version 0 where sminos is not loaded.

**I2 — The order probe** (sminos reads, devcloud writes; defined by devcloud, `types/devcloud.d.ts`):
`{ plugin: 'devcloud', key: 'secrets-guard' }` → `{ owner: 'devcloud'; version: 1 } | undefined`. Read
once, in the bridge's `session.start` hook before `next`.

**I3 — The names.** `ASK_TOOLS = ['mcp__sminos__AskUserQuestion', 'mcp__doperpowers__AskUserQuestion']`
and `PLUGIN_PROMPTS = ['The sminos plugin sent a message:\n', 'The doperpowers plugin sent a message:\n']`,
spelled in each reader (ask.tsx, to-human.tsx, sminos.py, MAWS's readers of §11) — no shared module
crosses plugins or repositories. The registered name (one) is `ASK_TOOLS[0]` from M3.

**I4 — The CLI's stable path.** `<installLocation>/sminos/skills/sminos/scripts/sminos.py` where
`installLocation` is `known_marketplaces.json`'s `doperpowers.installLocation`; the launcher beside it
is `sminos`. Used by `installed_cli` (the daemon), `sminos_host.py` (devcloud boot), the board
resolver, and the shim.

**I5 — The shim.** `skills/sminos/scripts/sminos.py` in doperpowers, M3 through M4: `python3 sminos.py
<args>` execs `<real sminos.py> <args>` under `sys.executable`; exit 1 with one line on stderr naming
`sminos daemon install` when no real CLI is found. No other behaviour.

**I6 — The board resolver.** `_lib.sh`'s `sminos_cli` (a function, exported as `SMINOS_CLI` once
resolved) in the order of §9.

**I7 — The gates.** `sminos`, `sminos-suites`, `sminos-mods` as §10 names them; their `paths` are
`["sminos/**", ".github/**"]`.

**Dependencies.** The engine at 2.1.303 (hooks modules, `$.state` with `state.set`, `prependPlugins`);
bun and `claude plugin test` for the mods' tests; MAWS `origin/master` at or after M2's merge for A2's
desk half.

## Surprises & Discoveries

- Observation: the engine's dependency sort pushes a depended-upon plugin behind every plugin nobody
  depends on, and today's doperpowers — depended upon by to-human — therefore registers innermost,
  inside devcloud's secrets guard: the bridge's `tool.call` hook sees a call's input with the secret
  bytes restored and its result before it is scrubbed (rows are scrubbed before the chain, so
  `session.append` is safe). The mods' README's "registered first, so its hooks are the outermost"
  holds within doperpowers only.
  Evidence: `claude --debug -p "reply ok" --max-turns 1` on this machine, 2026-10-19 14:59Z,
  `~/.claude/debug/87962cba-e384-4f62-bca2-43a4fba5290d.txt`:
  `hooks module order: dependencies register prompt-autosave@inline, cua@cua, devcloud@doperpowers,
  to-human@doperpowers, doperpowers@doperpowers, cc-plugin-agents-md@builtin, …`; the sort is
  `wSn` in `cli.pretty.js` 743447 (first module with zero dependents, repeatedly). The 2026-10-17
  debug logs, from sessions where to-human's module had not loaded, show `doperpowers, cua, devcloud`
  — the install order — which is how the bridge was outside the guard when it was written.
- Observation: with no dependency between two plugins their modules register in
  `installed_plugins.json`'s key order, which is install order; a newly installed plugin lands
  innermost.
  Evidence: the 2026-10-17 logs' `doperpowers, cua, devcloud` matches the file's keys
  `doperpowers@doperpowers … cua@cua … devcloud@doperpowers`; `Ubn` / `rSr` (744519–744552) sort only
  by tier and dependency.
- Observation: `$.state` is in-memory per process and any plugin reads any value; `state.set` is a
  hookable event, so a plugin can observe another's writes.
  Evidence: `.claude/types/claude-code.d.ts` 3460 ("held by the host for the session … survives a hot
  reload … Any plugin reads any value; its owner alone writes it. Persist through `$.store`") and
  12648 (`on("state.set", DRIVE, …)`); `cua`'s `one-guard.tsx` reads devcloud's marker.
- Observation: a daemon whose scripts vanish re-executes itself at its original path and exits when
  that fails; the service then restarts it every 60 s against the same missing path.
  Evidence: `sminos_daemon.py` `own_code`, `restart_in_place` (`os.execv(sys.executable,
  [sys.executable] + sys.orig_argv[1:])`), the `except OSError` at its call site ("exiting for the
  service manager to restart it"); `ThrottleInterval 60` in `sminos-daemon.plist`.
- Observation: the doperpowers plugin cache is the whole repository, sibling plugin folders included.
  Evidence: `ls ~/.claude/plugins/cache/doperpowers/doperpowers/7.188.8/` lists `devcloud` and
  `to-human`; the marketplace entry's source is `./`.
- Observation: MAWS's desk matches the plugin's name in a prompt row's `origin.name` as well as the
  framing, so a rename that only widened the framing regex would still drop sminos's deliveries.
  Evidence: `apps/desk-web/src/conversation/ask-answer.ts` 26–45 on `origin/master`.

## Decision Log

- Decision: verification — one independent spec review by the `doperpowers:adversarial-reviewer`
  agent (dispatched with `model: opus` while the Codex models are at their limit, until 2026-10-24)
  and, the execution section having five milestones, its buildability review in the same round; the
  branch review for each code milestone through doperpowers:review-code at **xhigh** (the panel): the
  change crosses four plugins, a settings-placed safety invariant and every machine. M2's branch is
  reviewed by MAWS's own rule.
  Rationale: the stakes, not the size; the owner named xhigh.
  Date/Author: 2026-10-19, the spec's author.
- Decision: the plugins' order is placed by the owner's `prependPlugins`, and the bridge refuses to
  stream when it finds itself inside devcloud's guard; sminos declares no dependency.
  Rationale: §4 — the engine's dependency rule puts the dependent outside and pushes the depended-upon
  inward, so no declaration gives a standalone sminos the outer place; install order gives a fresh
  install the innermost. Rejected: `sminos` depending on `doperpowers` (not standalone, and still
  inside devcloud); `appendPlugins` for devcloud and doperpowers (the same owner edit with a
  stranger meaning); streaming regardless (today's leak).
  Date/Author: 2026-10-19, the spec's author.
- Decision: appeal and reload read the ask through `$.state` (`sminos.ask`, shape 2) and `state.set`;
  compact relies on the bridge's `session.compact` hook.
  Rationale: §5. Rejected: appeal reading the transcript (copies the delivery grammar into
  doperpowers, no notice at the answer); a shared module (plugins cannot import each other's files).
  Date/Author: 2026-10-19, the spec's author.
- Decision: doperpowers keeps a shim at the old CLI path through M4.
  Rationale: §7 — the Mac mini and the devcloud hosts update unattended; without it their daemons
  crash-loop until someone reruns `daemon install`. Rejected: accepting the loop.
  Date/Author: 2026-10-19, the spec's author.
- Decision: sminos starts at 1.0.0; doperpowers 7.189.0, to-human 0.2.0, devcloud 0.5.0, one commit.
  Rationale: §10. The owner may name another starting version; nothing depends on the number.
  Date/Author: 2026-10-19, the spec's author.
- Decision: `devcloud/README.md` and the devcloud spec's §8 ("sminos on hosts") describe the CLI at
  `<clone>/skills/sminos/scripts/sminos.py`; from M3 it is `<clone>/sminos/skills/sminos/scripts/sminos.py`.
  Recorded here rather than rewriting that spec.
  Date/Author: 2026-10-19, the spec's author.

## Outcomes & Retrospective

Pending — written at finish.
