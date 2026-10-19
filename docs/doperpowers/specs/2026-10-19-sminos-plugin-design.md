# sminos — its own plugin

**Date.** 2026-10-19. **Status.** Outline approved by the owner on 2026-10-19 (split, same marketplace;
AskUserQuestion moves and is renamed; the peer roster is a separate initiative); this document is the
design and its execution, written against the code and the engine (2.1.302 bundle, 2.1.303 installed);
revised 2026-10-19 after the first independent review round (Decision Log). Rebased on `origin/main`
5395bbc2 (#270, 7.188.10: the copy/fork resume rebuilding async asks, which the first draft waited
on). **Prior art, reference only.** `docs/doperpowers/specs/2026-10-15-devcloud-design.md` (the second
plugin carved out of this repository, and the `$.state` marker another plugin reads);
`docs/doperpowers/specs/2026-10-13-ask-async-design.md` (the ask tool);
`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` and
`docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md` (the bridge, DX5).

## Purpose

sminos is the machine side of the MAWS desk and the way sessions and humans reach each other: the CLI,
the daemon and its uplink, the bridge mod that makes a session reachable, the async ask, and the hooks
that record what a session sent its human. Today it lives inside the doperpowers plugin, among the
methodology skills, so a machine cannot run the desk's machine side without the methodology, and the
methodology cannot be installed without a daemon and a bridge. After this work `sminos` is a plugin of
the same marketplace, beside `devcloud` and `to-human` (the marketplace's fifth entry; `ci-kit` is
another repository's), versioned on its own; a person installs `sminos@doperpowers` on a machine and
gets the whole orchestration interface, with or without `doperpowers@doperpowers`; and the ask tool
is `mcp__sminos__AskUserQuestion`.

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
- [x] (2026-10-19 18:00Z) First independent review round (two reviewers) absorbed: the order probe
      redesigned for reloads, M0 and the roll's reload path, MAWS's plugin-name readers, devcloud
      hosts' managed settings, the permission-prompt leak as a prerequisite, the board files, the
      drift against main (Decision Log, 2026-10-19).
- [x] (2026-10-19, the owner) **M0 on the Macs**: `prependPlugins` applied in `~/.claude/settings.json`
      on the MacBook and the Mac mini; probe sessions show `to-human` and `doperpowers` in the
      prepend tier, `devcloud` inner. Pending in M0: the `sminos@doperpowers` entry (§8).
- [ ] P0 — the bridge raises a permission request's input in the handle form it captured (§4; a
      separate change, in flight, lands before M1).
- [ ] The devcloud hosts' placement (§8, I8): the devcloud setup session's route, in verification in
      a Linux container; a precondition for enrolling a host, not a milestone here.
- [ ] Second review round on the revised sections.
- [ ] M1 — doperpowers' readers accept both names; the reload mod installs a plugin's new
      dependencies before it reloads.
- [ ] M2 — MAWS's readers accept both names and both plugin names (a PR in MAWS; the app rebuilt on
      each machine).
- [ ] M3 — The carve-out and the rename, rehearsed on a local marketplace.
- [ ] M4 — The roll and each machine's migration (owner steps).
- [ ] M5 — Cleanup and acceptance.

## Terms

- **Plugin.** A directory with `.claude-plugin/plugin.json` that the harness installs from a
  marketplace; this repository is one marketplace (`.claude-plugin/marketplace.json`) holding
  `doperpowers` (source `./`, the repository root), `devcloud` (`./devcloud`), `to-human`
  (`./to-human`), `ci-kit` (a URL source, another repository), and after this work `sminos`
  (`./sminos`). A plugin is addressed as `<name>@<marketplace>`: `sminos@doperpowers`.
- **Hooks module.** A plugin's function hooks: the `modules` entry of its `hooks/hooks.json` (here
  always `./mods/register.tsx`), loaded only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. A **mod** is
  one file of it that registers hooks on `on(...)`.
- **Outer and inner.** The engine runs every plugin's hooks on an event as nested wrappers: the
  module registered first is outermost, sees the event first and the result last; the one registered
  last is innermost, closest to the engine's own action. The order is decided per session at load
  and again at a reload (§4).
- **A guard.** A mod that keeps secrets out of what the model reads: devcloud's (`devcloud/hooks/mods/secrets.tsx`)
  and `cua`'s vendored copy of it (`cua` 0.15.0, `hooks/mods/guard/`), which acts only when
  devcloud's is absent. In `tool.call` a guard restores a handle's secret bytes into a Bash or Write
  call's input before calling `next`, and scrubs the result on the way out; in `session.append` it
  scrubs a row before calling `next`. devcloud's writes a marker, `{ plugin: 'devcloud', key:
  'secrets-guard' }`, in its `session.start`; cua's writes none.
- **The ask tool.** The MCP tool the ask mod registers, the built-in AskUserQuestion's input plus
  `async`; its name carries its plugin's name, `mcp__<plugin>__AskUserQuestion`.
- **The plugin prompt framing.** How the engine stores a prompt a plugin submits between turns:
  `The <plugin> plugin sent a message:\n<text>\n\nThis is how Claude Code surfaces a prompt a plugin
  submits between turns — …` (engine 2.1.302, `tOt`). The ask mod delivers an async answer this way
  when the session is idle. A row the bridge submits (a steer, a delivery) carries the plugin's name
  in its `origin.name`.
- **The marketplace clone.** The harness's checkout of this repository at
  `~/.claude/plugins/known_marketplaces.json`'s `doperpowers.installLocation`
  (`~/.claude/plugins/marketplaces/doperpowers`), updated with the marketplace; stable across plugin
  updates, unlike the versioned plugin cache (`~/.claude/plugins/cache/doperpowers/<plugin>/<version>/`),
  which an update prunes.
- **The daemon.** `sminos daemon run`, one per machine, installed as a launchd agent (macOS) or a
  systemd user unit (Linux) by `sminos daemon install`, which points the service at the marketplace
  clone's `sminos.py`.
- **`$.state`.** Named values the engine holds for the session in memory: they survive a hot reload
  of a plugin's code, not a new process; addressed `{ plugin, key }`; any plugin reads any value,
  only its owner writes it; `state.set` is a hookable event any plugin may observe; a read answers
  `{ value, version }`, the version moving by one per write.
- **The roll.** The moment a machine's marketplace clone and installed plugins move to the M3
  release and its live sessions reload — unattended: the reload mod (`hooks/mods/reload.tsx`)
  fetches the `autoUpdate` marketplaces every five minutes, updates the enabled plugins installed from
  them, and runs `/reload-plugins` in every idle session.

## Acceptance

Numbered so milestones can point at them. Each is checked on this machine in a temporary HOME and
SMINOS_HOME unless it names another machine or the real HOME.

- **A1 — The plugin exists and is placed.** In a HOME with `sminos@doperpowers` enabled and the
  settings of §8 applied (a temporary one in M3 with a local marketplace named `doperpowers`; the
  real one on each machine in M4), `HOME=<that> claude --debug -p "reply ok" --max-turns 1` in an
  empty directory with `SMNS_INTERNAL=1` writes a debug log (`<that HOME>/.claude/debug/<session>.txt`)
  whose `hooks module … loaded (worker, environment N, tier …)` lines come in the order
  `to-human@doperpowers`, `sminos@doperpowers`, `doperpowers@doperpowers`, each `tier prepend`,
  before every other plugin's module (`tier user`), and `sminos@doperpowers`'s line lists
  `session.start`, `tool.call`, `session.append`, `attribution.text`, `tool.describe` among its
  events. On a devcloud host the same holds once its managed settings carry the copied lists (§8,
  the devcloud session's route), the three in `tier prepend` from the policy and
  `cc-plugin-sec-default@builtin` not among the loaded modules.
- **A2 — The ask round trip under the new name.** In an interactive session in a project (this
  repository), the model calls `mcp__sminos__AskUserQuestion` with `async: true`; the call returns at
  once with the waiting text; the question shows behind `[ answer ]` and in the `N open questions`
  band; after the answer, the model's next message quotes it, and `sminos chat --host` lists the
  `question` and `answered` events; the desk (MAWS, with M2 deployed) shows the question card and its
  answer. The transcript's user row opens `The sminos plugin sent a message:` when the session was
  idle.
- **A3 — A transcript from before the rename resumes whole.** A session resumed from a transcript that
  holds an `mcp__doperpowers__AskUserQuestion` call with `async: true`, accepted and unanswered, shows
  that question open within seconds of the resume (`sminos/tests/mods/live-ask-resume-check.py`, run
  against a recorded transcript), and one whose answer was delivered under the old framing shows it
  answered; a copy of a session (`/branch`) rebuilt from `$.session.messages()` under either framing
  does the same.
- **A4 — sminos alone, doperpowers alone.** In a temporary HOME with only `sminos@doperpowers`
  enabled, `sminos who --session <id>`, `sminos list`, `sminos watch <member>` and the address line
  on a commit all work, and the start hook prints the guide when the temporary SMINOS_HOME carries an
  enrollment file as `test-guide.sh` fakes one. In a temporary HOME with only
  `doperpowers@doperpowers` enabled, `/appeals` prints, the compact offer appears at the gate, the
  kairos button draws, no error names sminos in the debug log, and a session under the `to-human`
  output style asks through the native AskUserQuestion (the style's own fallback sentence) rather
  than failing on the tool the style names.
- **A5 — The bridge refuses to sit inside devcloud's guard, and stays on across reloads.** In a
  temporary HOME with `devcloud` and `sminos` enabled, with the local marketplace of A1:
  (a) no `prependPlugins`: the debug log carries a line opening `sminos: the bridge is off` naming
  `prependPlugins` (an interactive session shows it as a toast too) and `$SMINOS_HOME/bridge/<session>.sock`
  never appears; (b) with `prependPlugins`: the socket appears and the line is absent; (c) with
  `prependPlugins`, after `/reload-plugins` reloading sminos alone (a sminos version bump in the
  marketplace), the socket is served again and the line is absent; (d) with `prependPlugins`, after
  a reload of both devcloud and sminos, the same; (e) without `prependPlugins`, after a reload of
  both, the bridge stays off. The verdict's record (§4; I1's `OrderVerdict`) names its evidence in
  each case.
- **A6 — appeal and reload read the asks through the channel.** `tests/mods/appeal.test.ts` passes
  with the judge's evidence carrying an answered ask read from `{ plugin: 'sminos', key: 'ask' }`,
  a pass ending when that value's `answered` count grows, and a block devcloud's guard turned into a
  `{ deny }` beneath appeal still appealed (§4, "appeal outside the guard"); `tests/mods/reload.test.ts`
  passes with the reload waiting while the value says a dialog is up, seeded from a read at
  `session.start`.
- **A7 — The daemon survives the roll and reinstalls at the new path.** On each machine (the MacBook
  `SK`, the Mac mini, each enrolled devcloud host once one exists): after the roll, `sminos daemon
  status` reports the daemon running and the hub shows the machine, the daemon's log naming the
  shim's forward once; after `sminos daemon install` and the service reload, the service file names
  `<marketplace clone>/sminos/skills/sminos/scripts/sminos.py` (`plutil -p ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`
  on macOS, `systemctl --user cat sminos-daemon.service` on Linux).
- **A8 — Every suite is green in the new layout.** `ci-gate` on the M3 commit is GREEN with the gates
  of §10, `claude plugin validate sminos/.claude-plugin/plugin.json` and
  `claude plugin validate .claude-plugin/plugin.json` both pass, and the M3 rehearsal (§10, "The
  rehearsal") ends with its open question still open, the bridge's socket served, to-human folding
  the transcript and `sminos chat --host` listing the question.
- **A9 — The documents name what is.** `/usr/bin/grep -rn "mcp__doperpowers__AskUserQuestion"`
  outside `docs/`, `archive/`, test fixtures and the readers that accept both names returns nothing;
  `CLAUDE.md`'s repo map has a `sminos/` row; `README.md` lists the plugins and their install lines.

## Design

### 1. The split: what moves, what stays

| Moves to `sminos/` | Stays in doperpowers |
|---|---|
| `skills/sminos/` (SKILL.md, references, scripts: the CLI, `lib.sh`, daemon, uplink, bridge child, chart, TUI) | the 14 other skills |
| `hooks/mods/bridge.tsx`, `bridge-state.tsx`, `bridge-stream.tsx`, `bridge-requests.tsx`, `bridge-rows.tsx`, `bridge-agents.tsx` | `hooks/mods/compact.tsx`, `appeal.tsx` + `appeal-judge.tsx`, `kairos.tsx`, `agents.tsx`, `interim.ts`, `reload.tsx` |
| `hooks/mods/ask.tsx` (the ask tool, renamed) | `hooks/kairos.sh`, `kairos-toggle.sh`, `compact-instructions.md`, `to-human-stream.sh` + `.awk` |
| `hooks/mods/address.tsx` (the `Sminos-Session:` line; it runs `sminos who`) | `output-styles/to-human.md` (names the ask tool, now sminos's) |
| `hooks/smns-record.sh`, `hooks/smns-guide.sh` | `agents/` (their `disallowedTools` name the ask tool) |
| `types/doperpowers.d.ts`'s `AskSnapshot` → `sminos/types/sminos.d.ts` | `tests/mods/` for the mods that stay, among them `live-appeal-check.py` and `live-compact-offer-check.py`; `tests/mods/run-mods-tests.sh`; `tests/mods/interim-audit/` |
| `tests/sminos/` whole → `sminos/tests/`; `tests/mods/ask.test.ts`, `bridge.test.ts`, `address.test.ts`, `test-ask-search.sh`, and the live checks of the bridge, the ask and sminos's control (`live-bridge-check.py`, `live-ask-*.py`, `live-requests-check.py`, `live-resume-check.py`, `live-stop-check.py`, `live-control-check.py`, `live-peer-check.py`, `live-walk-check.py`, `live-agents-seed-check.py`, `live-delivery-cancel-probe.py`, `live-decision-probe`) → `sminos/tests/mods/`; `tests/claude-code/test-smns-guide-hook.sh` → `sminos/tests/` | `tests/claude-code/`, `tests/issue-tracker/`, the rest |

Two files the outline did not list move too: `address.tsx` is sminos (it exists to print the sminos
address, through the CLI) and `smns-guide.sh` is sminos (it runs `sminos guide`). `to-human-stream.sh`
stays: it draws the `<message>` mark of doperpowers' output style, which has no sminos in it.
`reload.tsx` stays: it applies any plugin's update, sminos's included, and its one need of the ask
(§5) becomes a read of the channel.

The board scripts (`skills/issue-tracker/scripts/`) stay in doperpowers and go on calling the sminos
CLI and sourcing its `lib.sh` (§9); the board's dispatch is dormant, its scripts tested and armed
nowhere, and this work changes only how they find them.

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
  tests/mods/                    ask.test.ts, bridge.test.ts, address.test.ts, test-ask-search.sh, live-*, run.sh
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
accepted; it also means a doperpowers checkout or cache always has a sibling `sminos/` beside it
(§7, §9). The alternative, a repository of its own, was declined by the owner (same marketplace).

The mods' tests live under the plugin so `claude plugin test sminos` finds them as the only
`*.test.ts` there — as `to-human/tests/mods/run.sh` and `devcloud/tests/mods/run.sh` do — rather than
staged as `tests/mods/run-mods-tests.sh` must stage doperpowers' (the repository root holds
`application-agents/`' TypeScript tests). The shell and Python suite reads nothing outside the
plugin: its runner and each test file compute their own root as `$SCRIPT_DIR/../..` (today the
repository root; after the move, by the same depth, the plugin root), `envelope_parity.py` and
`fake_session.py` build `skills/sminos/scripts` from `__file__` the same way, and `test_rpcs.py`
finds `mods/live-resume-check.py` beside itself. M3 gives every one of them one name,
`PLUGIN_ROOT`, in place of the `REPO_ROOT` that no longer means the repository, so the depth
coincidence is not what holds them up, and the suite fails if any run ever reaches the shim (§7).

### 3. The tool's new name, and every reader accepting both

The MCP tool a plugin registers is named `mcp__<plugin>__<tool>` by the engine, so the move renames
it: `mcp__sminos__AskUserQuestion`. The plugin prompt framing follows the same way:
`The sminos plugin sent a message:`, and so does the `origin.name` of every row the ask or the bridge
submits. None of the old forms can be rewritten out of existing transcripts, and a session may be
resumed, compacted or forked across the roll, so **every reader accepts both names, both framings and
both origin names, for good** — not for a transition. The readers, from the grep of 2026-10-19 on
`origin/main` 5395bbc2 (the ones that match on the name rather than merely mention it):

| Reader | What it matches today | After |
|---|---|---|
| `hooks/mods/ask.tsx`: `asksIn` (`block.name === ASK_TOOL`), `deliveryTexts` and `historyAsks`' `prompt()` (`text.startsWith(PLUGIN_PROMPT)`), `STORED_FORMS` (the search's literals) | the one name, the one framing | the sets `ASK_TOOLS` and `PLUGIN_PROMPTS` beside `ASK_TOOL` and `PLUGIN_PROMPT`, which stay the registered name and this plugin's own framing; `STORED_FORMS` carries one literal per name and per framing |
| `hooks/mods/appeal-judge.tsx`: `PLUGIN_PROMPT = /^The \S+ plugin sent a message:\n/` | any plugin | unchanged |
| `to-human/hooks/mods/to-human.tsx`: `ASK_TOOL`, `ASK_DELIVERY` | the one name, the one framing | both |
| `skills/sminos/scripts/sminos.py`: `ASK_TOOL` (3306; read at 3452 and 3807), `PLUGIN_PROMPT` (3312; read at 3367) | the one name, the one framing | both; `tests/sminos/test-bridge-export.sh` 137 and 153 follow |
| `hooks/mods/bridge.tsx`: `isDialog` by `next.origin.plugin === PLUGIN`; `bridge-rows.tsx`: `origin.name !== PLUGIN` | the plugin's own name | the plugin's own name, which is `sminos` once the mods move together — correct as is |
| MAWS (§11) | the one name and the one plugin name | both |

The mid-turn framing (`The <plugin> plugin sent a message while you were working:`) is matched by no
reader in either repository — the ask submits only when the session is idle — and stays unmatched.

`ASK_TOOL` stays the one registered name: `bridge.tsx`, `bridge-rows.tsx`, `bridge-requests.tsx`,
`bridge.test.ts` and `test-ask-search.sh` import it as such, and the `tool.describe` / `tool.call`
matchers, `WITHDRAWN`'s sentence and the `AskSnapshot` key read it. M3 changes only its value (and
`PLUGIN_PROMPT`'s), with the readers already dual. The nine agent definitions' `disallowedTools` name
the new tool beside the old through M4 (an entry naming no tool is inert, and a session resumed
mid-roll may still see the old one); M5 drops the old. The output style names the new tool and keeps
its fallback sentence for a session without it. The owner's own `~/.claude/agents/astra.md` and
`sol-xhigh.md` carry the old name in `disallowedTools`; until the owner edits them (M4, an owner
step), an `astra` or `sol-xhigh` subagent is offered the renamed tool and a call of it is refused by
the ask's own `SUBAGENT_REFUSAL` — a refusal, not a hang.

Readers ship before the rename (M1, M2), so no running or resumed session breaks: a session on the
dual-reader doperpowers reads old rows; a session on sminos reads old and new rows; the desk reads
both from the day M2 is deployed.

### 4. Hook order across plugins

**How the engine orders hooks modules** (2.1.302, `mBr`, `wSn`, `Stn`, `Dqn`, `rSr` in
`cli.pretty.js` 743472–744552, confirmed live in Surprises & Discoveries):

1. By tier: `prepend` (the user settings' `prependPlugins`, or an organization's seat), then `user`
   (every plugin not named by a tier key), then `append` (`appendPlugins`), then `builtin`. Within
   `prepend` and `append` the list's order is the rank, first outermost. A `prependPlugins` name
   that is not an enabled plugin with a hooks module is skipped with a debug line (`rSr`), so a name
   may be listed before its plugin exists.
2. Within one rank, by manifest `dependencies`: the sort takes, repeatedly, the first module that no
   remaining module depends on. So a dependent registers before (outside) its dependency — and a
   module that others depend on is pushed behind **every** module nobody depends on, not merely
   behind its dependents.
3. Otherwise, in the order the enabled plugins were chosen, which is `~/.claude/plugins/installed_plugins.json`'s
   key order — install order.
4. A dependency is enabled with its dependent (`rootRequiredByDependent`, 779611) and installed
   with it (the install closure, 779586; `claude plugin prune` removes dependencies no longer
   needed); an unmet one leaves the dependent unloaded ("Dependency … is not installed").
5. The user's tier keys count only where no managed settings, organization seat or hosted session
   places mods: `E5` reads the user's `prependPlugins` only when `Vee()` — any non-empty
   `/etc/claude-code/managed-settings.json` — is false; on a managed machine the policy's
   `prependPlugins` is read instead, and it seats only plugins the policy enables (its own
   `enabledPlugins`). On a managed machine with no policy `prependPlugins`, the built-in
   `cc-plugin-sec-default@builtin` is seated outermost (since 2.1.287) and passes the plugins a
   person installs over on `prompt.*`, `session.compact`, `settings.read`, every `classic.*` event
   and `session.append`'s attachment, hook-context and compaction doors (`Mir`, the note the
   validate diagnostic appends, names the list: "these events pass over the plugins you install, and
   only a plugin the organization lists in managed settings runs them"); a policy `prependPlugins`
   that does not list sec-default leaves it unseated, and the pass-over most likely goes with it.
   Read from the source, not yet observed; the devcloud session is confirming it (§8). The order is
   recomputed at a reload as at a start.

**What this did to today's doperpowers.** `to-human` depends on `doperpowers`, so rule 2 pushed
doperpowers' module behind `cua` and `devcloud`: the live order on 2026-10-19 was `prompt-autosave,
cua, devcloud, to-human, doperpowers`. The bridge, "registered first, so its hooks are the outermost",
was outermost only within doperpowers; across plugins it sat **inside devcloud's guard**, so its
`tool.call` hook saw a Bash or Write call's input after the guard restored the secret bytes into it
and the result before the guard scrubbed it (`bridge.tsx` emits `input` from `e` and `text` from what
`next(e)` returned); rows were safe either way, since a guard's `session.append` hook scrubs before
calling `next`. The stream to the hub carried unscrubbed tool inputs and results from this machine.
M0 (§8) closed it on the Macs the same day.

**What the order must be**, outer to inner:

- `to-human` outside `sminos`: it sees the ask's rows before the ask draws them, and its band above
  the prompt draws under the ask's band (the reason it was outside doperpowers).
- `sminos` outside every guard — devcloud's, and cua's vendored one where devcloud is absent: the
  bridge posts what the session showed and kept, so it must see a call's input with its handles and
  its result scrubbed, never the bytes.
- `sminos` outside `doperpowers`: the bridge reports the appeal's note on a blocked result and its
  allow on a passed re-run as the session showed them, and interim sits inside the ask's
  `prompt.submit` (the ask puts back what it attached to a prompt dropped beneath it). Fidelity, not
  safety: the desk reads the appeal's note from the transcript row either way.
- `doperpowers` and `devcloud` in either order (the appeal's note is text on a deny, which the guard
  scrubs or not; neither reads the other) — with one narrow consequence pinned below.

**The decision: the owner's user settings place the three, and sminos declares nothing.** On each
machine `~/.claude/settings.json` carries

```json
"prependPlugins": ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]
```

which puts them in the `prepend` tier in that order, outside every user-tier plugin (`devcloud`, `cua`,
`ptc`, the journals), whatever is installed later and in whatever order. `to-human`'s manifest keeps a
dependency, on `sminos` instead of `doperpowers` (it needs the ask's rows; enabling to-human then
enables and installs sminos, rule 4) — it has no ordering effect inside the prepend tier and
documents the need. `sminos` depends on nothing; `doperpowers` depends on nothing. Applied on both
Macs on 2026-10-19 (M0), ahead of every milestone, so the roll lands sminos placed.

Why not dependencies alone: the engine's only dependency rule puts the *dependent* outside, so
sminos outside doperpowers would need `sminos` to depend on `doperpowers` — the opposite of a
standalone sminos — and, by rule 2, to-human depending on sminos pushes sminos *inside* every
undepended plugin, devcloud included: the dependency that is needed produces the order that is
forbidden. Why not install order: a fresh `sminos@doperpowers` is appended last to
`installed_plugins.json` and registers innermost, inside devcloud. Why doperpowers is in the list too:
two entries would hold the guard invariant; the third restores the nesting the mods were written
for, at the cost of one more name in the same line. Why the settings file and not a manifest key:
the engine offers no manifest key for placement; `prependPlugins` is its one lever for "a mod above
the user tier", and the owner edits the same file for `enabledPlugins` anyway (§8). On a devcloud
host the user's key is shadowed by any managed settings (rule 5); §8 makes the hosts carry none.

**What placement alone does not cover.** Two paths carry a call's input past the bridge's own
`tool.call` hook whatever the order: the engine's permission check runs after every `tool.call` hook
has rewritten the input, so `tool.check`'s `e.input` and `classic.PermissionRequest`'s `tool_input`
hold the restored bytes, and the bridge raises them to the desk (`bridge.tsx`: `state.checks.push({…
input: e.input })`, `capped(e.tool_input)`, `rawInput`). **P0**, a separate change in flight before
M1, has the bridge raise a request's input in the handle form it captured in its own `tool.call`,
keyed by `tool_use_id`, with the pending-request digest kept consistent (the desk's answer names the
digest of what was raised). That capture is the handle form only when the bridge is outside the
guard, so the invariant is the two together: placement, and the bridge raising only what it captured.

**The bridge proves its place before it streams**, and keeps the verdict across reloads. devcloud
writes its marker in its `session.start` hook before calling `next` (`secretsStart`), `$.state`
starts empty in every process, and a reload of one plugin reruns that plugin's `session.start` only.
So the bridge's `session.start` hook, which today calls `next` first and then `bridgeStart`, reads
the marker `{ value, version }` before `next` and again after, and decides:

| Before `next` | After `next` | Meaning | Verdict |
|---|---|---|---|
| absent | present | devcloud's hook ran inside this one: devcloud is inner | `outside` (fresh evidence `moved`) |
| absent | absent | no devcloud loaded | `outside` (`absent`) |
| present, version v | version > v | devcloud reloaded with sminos, inside | `outside` (`moved`) |
| present, version v | version v | devcloud ran before this hook: at the process's first start that means devcloud is outer; at a reload of sminos alone it means nothing | the kept verdict if one exists (`kept`), else `inside` (`present-first`) |

The verdict and its evidence are written once per start under sminos's own key, `{ plugin: 'sminos',
key: 'order' }` (I1's `OrderVerdict`), which the next start of the same process reads back. `outside`: the bridge
starts. `inside`: it starts no child and says why — a toast and a debug line, `sminos: the bridge is
off — sminos must load outside devcloud; set prependPlugins in ~/.claude/settings.json to
["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]` — and the session is
unreachable from the desk for its life, as a session without function hooks is; the ask, the address
and the shell hooks serve either way. A `prependPlugins` change takes effect for the verdict at the
next process, not at a reload (the kept verdict stands when the evidence is ambiguous). cua's
vendored guard writes no marker and cannot be probed; placement alone covers it, and a marker of
cua's own — written only while its guard acts — would extend the probe (a cua change, recorded as
residue, not in scope). The alternative, streaming and hoping, was the state before M0; a loud
refusal on one machine beats a quiet leak to the hub.

**appeal outside the guard.** With doperpowers in the prepend tier, appeal's `tool.call` hook sits
outside devcloud's: a call the guard refuses (`{ deny: WITHHELD }` when the guard fails) reaches
appeal as a deny, not a classifier block, and the one-shot pass `takePass` records the input as
appeal saw it (the handle form) while `tool.check` sees the restored form, so a pass granted on a
call that carries a handle does not match its re-run. Narrow — calls with handles only — and the
order the mods ran in before 2026-10-17. M3 pins it in `tests/mods/appeal.test.ts` with a fake guard
beneath appeal: a block the guard turned into a deny is still appealable, and a pass on a call with a
handle is reported as not applied rather than silently missed.

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
of its own: seeded at its `session.start` from `$.state.get(ref)` (a reload of doperpowers alone
must not miss a dialog already up), then kept current by a `state.set` hook on the same reference
(no value ever written reads as no dialog); and it tracks the main turn itself with `turn.start` /
`turn.complete` hooks matched on `turnId` (compact.tsx and agents.tsx hold the module's one
unmatched registration of each; a matched one is unlimited). Why not read `isTurnRunning` from the
channel too: reload must work with sminos absent, and a turn is the engine's event, not the ask's.

**compact → bridge (`compacted`).** compact calls `compacted(null, outcome.messages)` after its own
`$.session.compact` because "its rows pass no hook of this plugin's, the bridge's included" — the
re-entry rule skips the calling plugin's hooks. After the split the bridge is another plugin: its
`session.compact` hook (`{ trigger: /^/ }`, which already calls `compacted` for the person's
`/compact`) fires for doperpowers' compaction as for any other. The import and the call go; M3 proves
the bridge names a compact-tool compaction's rows through the hook (a `bridge.test.ts` case driving
`session.compact` with the compaction's result, and `tests/mods/live-compact-offer-check.py`, which
already exercises the path and stays in doperpowers). The bridge's own `compact` command still calls
`compacted` directly (same plugin, re-entry).

**The ask's snapshot at the roll.** `/reload-plugins` swaps both modules at once; the new ask module
finds no `sminos.ask` and would start empty, forgetting open async asks until the next resume. For one
release it reads `{ plugin: 'doperpowers', key: 'ask' }` when its own key is empty and takes a
shape-1 value up as shape 2 (`isDialogUp: false`, `answered: 0`). M5 removes the fallback.

### 6. to-human's dependency

`to-human/.claude-plugin/plugin.json`'s `dependencies` becomes `["sminos"]`. to-human stays its own
plugin for the reason it was made one: the engine runs none of a plugin's render hooks on a row that
plugin submitted, and sminos submits the ask's deliveries and the bridge's sminos deliveries while
doperpowers submits the compact mod's resume prompt. Its readers accept both names (§3). Its version
moves (0.1.1 → 0.2.0) in M3 with the dependency — which is what makes the roll install sminos on a
machine that never ran `/plugin install sminos@doperpowers` (§10, "The roll").

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
`os.execv` it with the same arguments. It looks first beside itself — the sibling
`../../../sminos/skills/sminos/scripts/sminos.py`, which is the same file for the daemon (the shim
runs from the marketplace clone, whose `sminos/` is the real plugin) and the right one for a checkout
or a plugin cache (§2); then the installed sminos plugin's (`installed_plugins.json`,
`sminos@doperpowers`'s `installPath`); when neither exists it prints one line naming `sminos daemon
install` and exits 1. Every forward writes one line to stderr, `sminos: forwarded from the retired
path <shim>; rerun sminos daemon install`, so the daemon's log shows the hop and the test suite can
fail on it (§2). The running daemon's restart lands in the shim and goes on under the new code, with
`sys.orig_argv` now the real path; a service restart or a reboot goes through the shim again until
`daemon install` is rerun on that machine (M4), after which the shim is dead code and M5 removes it.
The alternative — accept the crash loop and make the rerun the first owner step — was rejected for
the Mac mini and the devcloud hosts, which update unattended.

**devcloud's boot runs the image's copy.** `devcloud/image/setup.sh` copies `boot/` into
`/usr/local/lib/devcloud` when the image is built, so a plugin update changes nothing in a running
host's `sminos_host.py`: an image older than M3 keeps looking for `<clone>/skills/sminos/scripts/sminos.py`
— the shim, which forwards; its `daemon install` (run through the shim) writes the real path. So an
old image works through the shim, and M5 removes the shim only once no host runs an image older than
M3 (today none is enrolled at the desk, so the condition holds vacuously). From M3 `sminos_host.py`
looks for the new path first and the old second, so a new image also boots against a clone that has
not moved yet; `devcloud/tests/unit/test_sminos_host.py` (`marketplace()`) and
`devcloud/tests/integration.py` (`enrolled_daemon`, which stages `skills/sminos/scripts`) stage the
new layout.

The suite's test of the cache layout (`run-sminos-tests.sh`, "A CLI running from the versioned plugin
cache installs the marketplace clone's CLI") moves its fixture to
`cache/doperpowers/sminos/9.9.9/` and `<clone>/sminos/skills/sminos/scripts/sminos.py`, and the same
section pins the shim: a doperpowers cache staged with the shim forwards to the sibling, then to the
installed plugin, then refuses, and the forward's line is on stderr.

### 8. Each machine's migration — the owner's steps

`~/.claude/settings.json` is the owner's file: no agent edits it. The steps below are performed by the
owner, or by a session on the owner's explicit approval of that step on that machine; the spec
names them so M0 and M4 can be run as a checklist. The machines: the MacBook `SK`, the Mac mini, and
each devcloud host once one is enrolled.

**M0 — before M1 (the Macs: done 2026-10-19 by the owner, except step 2):**

1. `prependPlugins`: `["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]` (§4).
   Safe ahead of the plugin's existence: a name that is not an enabled plugin with a hooks module is
   skipped (§4, rule 1). Done on both Macs; probe sessions confirm the prepend tier.
2. `enabledPlugins`: add `"sminos@doperpowers": true` now. An entry alone installs and loads nothing
   (the engine lists it in `/plugin` as not installed); it makes the install explicit when the roll
   brings sminos in as to-human's dependency, so a later `claude plugin prune` never reads sminos as
   an auto-installed dependency nobody asked for. M3's rehearsal confirms both halves (§10).

**M4 — at the roll, per machine:**

3. `~/.claude/agents/astra.md` and `sol-xhigh.md`: `disallowedTools` names `mcp__sminos__AskUserQuestion`
   (and keeps `mcp__doperpowers__compact`).
4. Let the reload mod roll the machine, or run `/plugin marketplace update doperpowers` and
   `/reload-plugins` in a session; a session that must keep its open asks across the swap keeps them
   (§5).
5. `sminos daemon install`, then reload the service: on macOS `launchctl bootout gui/$(id -u)/com.doperpowers.sminos-daemon`
   then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`;
   on Linux `systemctl --user daemon-reload && systemctl --user restart sminos-daemon.service`. Until
   this step the daemon runs through the shim (§7).
6. Verify A1 and A7 on the machine.

**devcloud hosts — owned by the devcloud setup session; a precondition for enrolling one at the
desk.** A host receives the owner's `~/.claude` (the configuration repository, reset to its remote
every 30 minutes and reconciled, design §5; the owner describes the hosts as mounting the Mac's
file), so `settings.json` with M0's lines reaches every host by itself. What stops it from counting
there is `/etc/claude-code/managed-settings.json`, which boot step 10 writes from the profile —
seven keys today: the gateway's base URL, its feature switches, and blanks for the Mac-only
`CLAUDE_CODE_PLUGIN_DIRS` and the browser-extension token — and any non-empty managed settings make
the engine ignore the user's `prependPlugins` (rule 5). Managed is the only tier above user that
every launch path on a host reads.

**The route**, chosen and built by the devcloud setup session, which owns boot: step 10 and its
reconcile write into `managed-settings.json` the profile's env as now, **`prependPlugins` copied from
the synced `settings.json`**, and **`enabledPlugins` true for exactly those ids** (the policy seats
only plugins it enables). The Macs' `settings.json` stays the single list; once sminos is in it (M0),
a host places sminos by copying. It is being verified in a Linux container before it lands, and
what decides it is the pass-over of rule 5: whether `cc-plugin-sec-default@builtin` is unseated by
a policy `prependPlugins` that does not list it, and whether the plugins a person installs are
still passed over on `prompt.*`, `session.compact`, `settings.read`, `classic.*` and
`attribution.text` once it is — the events the bridge (`classic.PermissionRequest`, the path that
raises permission prompts to the desk; `session.compact`), the ask (`classic.SessionStart`), the
address line (`attribution.text`), compact (`classic.Stop`) and devcloud's own guard
(`prompt.compose`, `prompt.context`, `prompt.attachment`, `session.compact`) need. The reading so
far: `Mir` is `passedOverNoteOf`, exported from the registry module that also holds the seat
(`cPr`), `PASSED_OVER_EVENTS` / `DOORS` and sec-default's `registerPlugin`, and its one call site
appends a note to a module's `hooks:` diagnostic line — so the pass-over is most likely carried out
by sec-default's own hooks module and ends when that module is unseated; not yet observed. The
container run watches hooks fire under the candidate managed file and under today's env-only one:
devcloud's and cua's `prompt.*` and `session.compact` (plugins the policy does not list), to-human's
`classic.SessionStart` and the bridge's `classic.PermissionRequest` (plugins it lists). If hooks of
unlisted user-tier plugins are still passed over, the fallback is a different design — every plugin
policy-listed in managed settings — which the devcloud session would then own too. This spec
defers to that result. Until a host boots an image carrying the route, the host does not enroll at
the desk (`sminos hub enroll` is refused by the operator's checklist, not by code); no host is
enrolled today.

Two routes lost. The host's process environment, set by boot for every launcher: settings `env`
overwrites the process environment tier by tier (`applySafeConfigEnvironmentVariables`, verified on
2.1.303 by the devcloud session; the same reading as `jp` at cli.pretty.js 481468), and the synced
file sets `ANTHROPIC_BASE_URL` to the Mac's loopback relay `127.0.0.1:8641`, which nothing serves on
a host, so a process value would lose to it. An overlay that rewrites the received `settings.json`
after each pull (this spec's second draft): on a host `~/.claude` is a receive-only clone of the
configuration repository — a timer runs `git reset --hard origin/<branch>` every 30 minutes, the
push URL is invalid, and `devcloud reconcile` re-applies boot steps 5–11 when the fetched commit
changes — so a host-side rewrite is undone at every reset, running sessions hot-reload the Mac's
values (the `127.0.0.1:8641` base URL) between the reset and the re-apply, and the clone is left
dirty. Only the managed tier is the host's to write.

The order across machines does not matter: the hub reads events, not plugin versions, and both
daemons speak the same protocol.

### 9. Board scripts, the guide, the preamble, plugin roots

- **The board scripts and references** reach the sminos CLI by a relative path that stops existing:
  `_lib.sh` (58), `execute-dispatch.sh` (53), `board-sweep.sh` (97), `review-dispatch.sh` (133, and
  139 sources `../sminos/scripts/lib.sh`), `_sweep_api.sh` (192), `board-gc.sh` (64); the worker
  protocol templates `implement-worker-protocol.md` (309), `architect-worker-protocol.md` (178, 231,
  524), `review-standin-protocol.md` (23), which spell `{{BOARD_SCRIPTS}}/../../sminos/scripts/sminos`;
  and the tests `tests/issue-tracker/test-execute-dispatch.sh` (1000) and `test-review-dispatch.sh`
  (2708, `REAL_SMINOS`), `test-board-gc.sh`, `tests/claude-code/board-api/test-sweep-*.sh` and
  `integration/test-bg-worker-actor.sh` (48). `_lib.sh` gains one resolver (I6) every script sources
  or calls: `$SMINOS_CLI` when set; else the checkout's sibling `$REPO_ROOT/sminos/skills/sminos/scripts/sminos`
  (present in a checkout and in the doperpowers cache, §2); else the marketplace clone's
  `sminos/skills/sminos/scripts/sminos` (the path the daemon runs, read from `known_marketplaces.json`);
  else `die` naming `SMINOS_CLI`. `lib.sh`, the sourced half of sminos for shell consumers, moves
  with the CLI and is sourced from the resolved CLI's directory (`$(dirname "$SMINOS_CLI")/lib.sh`);
  the templates get a `{{SMINOS_CLI}}` placeholder the dispatcher fills from the resolver, as the
  spawn preamble's is filled. The tests set `SMINOS_CLI` to the checkout's CLI.
- **The guide** (`sminos guide`, printed by `smns-guide.sh` at session start) prints the CLI's
  absolute path from its own location; nothing to change. **The spawn preamble**'s `{{SMINOS_CLI}}` is
  the CLI's `LAUNCHER`; nothing to change.
- **`CLAUDE_PLUGIN_ROOT`** in `smns-record.sh` and `smns-guide.sh`, and **`$.plugin.root`** in
  `bridge.tsx` and `address.tsx`, resolve to the sminos plugin's root once the files live there; the
  `skills/sminos/scripts/sminos` suffix holds. `reload.tsx`'s `$.plugin.root` is doperpowers' own.
- **The sminos CLI's own references to its plugin**: `installed_cli`'s clone path (§7) and its error
  text; `sminos.py`'s `ASK_TOOL` / `PLUGIN_PROMPT` (§3). Its `.smns`, registry and log layout do not
  change.
- **The live checks** stage a plugin folder from `REPO` two levels above themselves and launch it
  with `--plugin-dir` (`live-bridge-check.py` `REPO`, `PLUGIN_PARTS`, `sminos()`; `live-resume-check.py`
  and `live-stop-check.py` `SCRIPTS`): after the move `REPO` is the sminos plugin root and
  `PLUGIN_PARTS` names its parts (`.claude-plugin`, `hooks`, `skills`, `types`). A `--plugin-dir`
  load registers as `<name>@inline`, which `prependPlugins` never matches; the live checks stage one
  plugin, so nothing orders them, and the rehearsal (§10) uses a local marketplace for that reason.

### 10. Versioning, marketplace, gates, the roll, documents

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
- **The roll** (§Terms) is unattended, so the M3 release must survive it with no owner present. The
  reload mod's update path runs `claude plugin marketplace update doperpowers` and then `claude
  plugin update <key> --scope user` for each enabled plugin installed from it — only installed ones.
  Left as it is, a machine's roll would update doperpowers to 7.189.0 (the ask and the bridge gone),
  update to-human to 0.2.0 (depending on a sminos that is not installed, so unloaded), and reload;
  whether `plugin update` installs a plugin's new dependency closure as `plugin install` does is what
  the rehearsal must show, and the mod must not rely on it. **M1 changes the reload mod**: before
  updating, it reads each enabled plugin's manifest in the refreshed clone, installs every dependency
  not yet installed (`claude plugin install <dep>@<marketplace> --scope user`) and refuses the whole
  batch, with a debug line, when one cannot be installed; it updates the batch; then it reloads once.
  M1 ships this because M1's code is what runs on the machines during the roll. With M0's
  `prependPlugins` already in place, sminos lands placed.
- **The rehearsal** (M3's proof of the roll): a temporary HOME with a local marketplace named
  `doperpowers` (`claude plugin marketplace add <a clone of this repository at the M1 commit>`; the
  name must be `doperpowers`, because `prependPlugins` names `<plugin>@doperpowers` and a
  `--plugin-dir` load registers as `@inline`), the settings of §8 applied there, doperpowers,
  to-human and devcloud installed at M1, the gateway keys for a model call, one interactive session
  with an async ask open; then the clone is moved to the M3 commit, the reload mod is let act (or its
  fetch is forced), and after the reload: the ask is still open behind `[ answer ]` and answers,
  `$SMINOS_HOME/bridge/<session>.sock` is served, to-human folds the transcript, `sminos chat --host`
  lists the question, and the debug log shows the order of A1. The rehearsal spends model calls; it
  runs inside `/tmp/maws-review/with-slot.sh`.
- **Gates** (`.github/ci-kit.yml`): `sminos` and `sminos-suites` run `sminos/tests/run-sminos-tests.sh`
  with paths `["sminos/**", "skills/sminos/**", ".github/**"]` (the second for the shim, which the
  suite pins); a new `sminos-mods` gate installs claude-code and bun as `mods` does and runs
  `sminos/tests/mods/run.sh` (`claude plugin test sminos` then `sminos/tests/mods/test-ask-search.sh`),
  paths `["sminos/**", ".github/**"]`; `mods` keeps `hooks/**` and `tests/mods/**` and adds
  `sminos/types/**` and `sminos/hooks/mods/ask.tsx` (appeal's and reload's tests read the snapshot
  the ask writes); `board-api` and `issue-tracker` paths replace `skills/sminos/**` with `sminos/**`
  (the board scripts call the CLI); `claude-code`, `devcloud-mods`, `to-human-mods`, `devcloud`,
  `repo-checks` as they are (their files change under them). `tests/claude-code/run-skill-tests.sh`
  drops `test-smns-guide-hook.sh`, which the sminos suite runs (it was in no gate; now it is in
  `sminos`).
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
  plugin. `devcloud/README.md` and the devcloud spec's §5, §6 and §8 are not rewritten; dated lines
  in this spec's Decision Log record the path change they describe and the placement lists the
  hosts' managed settings gain (the devcloud session's change, documented there when it lands).
  Old specs (`2026-10-13-ask-async-design.md` and the rest) are history and keep the old name.

### 11. MAWS's side

MAWS reads the tool name, the framing and the plugin's name in these places on `origin/master`
(2026-10-19), and all of them must accept both before the rename ships (M2):

| File | Today | Change |
|---|---|---|
| `src/renderer/src/transcript/model/classify.ts` | `ASK_MOD_TOOL = 'mcp__doperpowers__AskUserQuestion'`, keyed into `ROW_KIND_TOOLS` | both names keyed as `question` (a set `ASK_MOD_TOOLS`; `ask-mod.ts`'s comment follows) |
| `apps/desk-web/src/conversation/ask-answer.ts` | `PLUGIN = 'doperpowers'` against `origin.name`; `PLUGIN_PROMPT = /^The doperpowers plugin sent a message:\n/` | a set of plugin names; `/^The (?:doperpowers\|sminos) plugin sent a message:\n/` |
| `apps/desk-web/src/conversation/delivery-frame.ts` | `BRIDGE_PLUGIN = 'doperpowers'` (`isBridgeRow`: the bridge's steers, mid-turn deliveries, interrupt rows, by `origin.name`) | the set |
| `apps/desk-web/src/depth/source/bridge-rows.ts` | `MIRRORS` on the bridge's plugin name | the set |
| `apps/desk-hub/fake-machine/machine.ts` | `QUESTION_TOOLS = new Set(['AskUserQuestion', 'mcp__doperpowers__AskUserQuestion'])`; a steer row's `origin: { kind: 'plugin', name: 'doperpowers' }` (725) | the sminos name added; the fake machine raises under the new name where it plays a rolled machine |
| `apps/desk-hub/fake-machine/session.ts` | `origin: { kind: 'plugin', name: 'doperpowers' }` (537) | both, as the machine it plays |
| `src/shared/owner/contract.ts` | the contract's sentence "`mcp__doperpowers__AskUserQuestion` is not available here" | names both (or "the doperpowers or sminos plugin's ask tool"); `contract.test.ts`'s needle follows. Whether the contract's version key moves is MAWS's rule to apply: its meaning (ask through `mcp__maws__ask` there) is unchanged |
| `e2e/to-human-live.spec.ts` | `nativeAsks` filter on the one name | both |
| `apps/desk-hub/src/objects/project.ts` (`endsWith('__AskUserQuestion')`), `apps/desk-web/src/conversation/card-state.ts` (same) | suffix | no change |
| recordings, `session-view.py`, `dx4-jobs.json`, tests naming the old name | fixtures | no change; a new fixture under the new name is welcome but not required |

M2's executor greps MAWS for every `'doperpowers'` literal compared against an `origin.name`, a
plugin name or a tool name (`git grep -n "'doperpowers'" -- apps src`) and widens each; the table is
the list on 2026-10-19, not a bound.

The desk reads `raised.tool` and a row's `origin.name` from the bridge's events and the transcript,
which carry the registered name; a machine on sminos 1.0.0 raises `mcp__sminos__AskUserQuestion` and
submits rows as `sminos`, a machine not yet rolled uses the old names, and the desk must read a
project whose machines are on either. M2 is a PR in MAWS, written by a session in that repository
from this section and the ticket M2 registers; M3's roll (M4) waits until M2 is **deployed** — merged
and the app rebuilt on each machine that runs the desk — not merely merged.

## Out of scope

- The peer roster (a separate initiative, in flight).
- A repository of its own for sminos, or a change to the marketplace's name (`doperpowers`), which
  `known_marketplaces.json` and every daemon's service file name.
- Any change to DX5 (the bridge protocol) or to what the stream carries; the hub and the desk are
  readers of names only here. P0 changes what the bridge raises, not the protocol's shape.
- A marker of cua's own for its vendored guard (residue, §4).
- The devcloud hosts' placement (boot step 10 writing the copied lists into managed settings, §8,
  I8): the devcloud setup session's change, on its own schedule; this spec relies on its result and
  names it as a precondition for enrolling a host.
- Re-cutting the old specs under the new name.
- The `qa-loop`, the board's dispatch, and the worker protocols' behaviour, which stay dormant and
  unarmed; this work changes only how their scripts find the CLI.

## Execution

### Constraints that bind every milestone

- M1 is based on `origin/main` at or after 5395bbc2 (#270). #269 (`smns-guide-fork`) and #271
  (`smns-guide-roster`), open at this writing, change `cmd_guide` and `smns-guide.sh`; M3's move
  takes whatever of them has merged and rebases on the rest.
- P0 — the bridge raising a request's input in the handle form it captured — lands on `main` before
  M1; M1's base carries it.
- Every reader of the tool name, the framing and the plugin name accepts both, for good; no milestone
  removes the old name from a reader (§3). M1 and M2 ship — M2 deployed — before M3's roll.
- No milestone edits `~/.claude/settings.json`, `~/.claude/agents/*.md`, or the service files on any
  machine; M0 and M4 list those as owner steps and record what the owner did.
- Never print or copy `~/.claude/sminos/daemon/hub.json` or any credential-bearing file; never touch
  `~/.config/claude-secrets`. Manual runs of a working copy's sminos, hook or mod use a temporary
  HOME and SMINOS_HOME (`tests/sminos/run-sminos-tests.sh` shows how), and A1's probe runs `claude`
  against that HOME, reading `<HOME>/.claude/debug/`, never the real one. Heavy commands run one at a
  time inside `/tmp/maws-review/with-slot.sh`; `grep` is ugrep on this machine, use `/usr/bin/grep`.
- Version bumps go through `scripts/bump-version.sh` (one plugin per call), in the same commit as the
  change (CLAUDE.md, working conventions). Commit messages carry no attribution trailer other than
  the `Sminos-Session:` line the engine adds.
- Each plugin's module respects the engine's limits as the code does today: one unmatched
  registration of an event per module; `$` passed only to functions in the module's own file; the
  state reference's `plugin` and `key` as literals.
- The engine is 2.1.303 on this machine; a milestone that finds the engine's behaviour differs from
  §4, §5 or §10 records it in Surprises & Discoveries and returns to the spec's author before building
  on it.
- MAWS is read at `/Users/new/Developer/GitHub/MAWS` (the checkout is on `sminos-hub`; read
  `origin/master` with `git show` / `git grep`); M2 alone writes there, from its own worktree.

### Plan of Work

M0 (owner, mostly done), then five milestones, ordered so no live session breaks: readers first in
both repositories with the reload mod made safe for the roll, then the carve-out with the rename in
one release, rehearsed, then the roll with each machine's steps, then cleanup. M1 and M2 are
independent of each other and may run side by side; M3 waits for both; M4 waits for M3's release and
M2's deployment; M5 waits for every machine of M4.

### M1 — doperpowers' readers accept both names; the reload mod installs new dependencies

**What exists at its end.** A doperpowers release (7.188.x, bumped) whose ask, to-human and sminos
record export read a transcript carrying either tool name and either framing, whose appeal judge
already does, and whose reload mod installs a plugin's new dependencies before it reloads a machine.
A session on it, resumed later from a transcript written by sminos 1.0.0, sees its asks; a machine on
it rolls to M3 without a reload that lacks sminos.

**What it touches.** `hooks/mods/ask.tsx` (`ASK_TOOLS` and `PLUGIN_PROMPTS` beside `ASK_TOOL` and
`PLUGIN_PROMPT`; `asksIn`, `deliveryTexts`, `historyAsks`' `prompt()`, `STORED_FORMS`, `searchArgs` /
`grepArgs`'s literals); `to-human/hooks/mods/to-human.tsx` (`ASK_TOOL`, `ASK_DELIVERY`);
`skills/sminos/scripts/sminos.py` (`ASK_TOOL` at 3306, read at 3452 and 3807; `PLUGIN_PROMPT` at
3312, read at 3367 in `_delivery_texts`); `hooks/mods/reload.tsx` (the update path of §10);
their tests (`tests/mods/ask.test.ts`, `tests/mods/test-ask-search.sh`, `tests/mods/reload.test.ts`,
`to-human/tests/mods/to-human.test.ts`, `tests/sminos/run-sminos-tests.sh` around `ASK =`,
`tests/sminos/test-bridge-export.sh` 137 and 153). Versions: doperpowers and to-human.

**Decisions.** The registered name stays `mcp__doperpowers__AskUserQuestion` here: `ASK_TOOL`'s
value, the `tool.describe` / `tool.call` matchers, `WITHDRAWN`, and the bridge's `PLUGIN` do not
change in M1. The new name and framing are spelled once each, as the first member of each set, so M3
changes `ASK_TOOL` and `PLUGIN_PROMPT` to `ASK_TOOLS[0]` and `PLUGIN_PROMPTS[0]` and nothing else.
The search's `STORED_FORMS` gets one literal per name and per framing so a transcript over 4 MiB is
still found by `grep -F` (a5bc8c15). The record export's Python mirrors the TypeScript sets. The
reload mod's dependency step reads the refreshed clone's manifests by the marketplace's `source`
paths (`.claude-plugin/marketplace.json` in the clone), installs with the engine's CLI as it updates
with it, and treats a refusal as "this fetch applies nothing", logged, retried at the next fetch.

**What it does not touch.** No file moves; no manifest, gate or document changes beyond the
version bump.

**What it proves.** A3's reader half: tests pin a transcript whose call carries the old name and
whose delivery carries the new framing, and the reverse, each rebuilt as one open or answered ask by
`asksIn`, and the same pair rebuilt by `historyAsks` from a fake `$.session.messages()`; to-human's
`promptRow` reads both framings as the person's answer; `sminos record` exports a `question` and
`answered` from each. The reload mod: a fake clone whose to-human manifest names a dependency not
installed makes the mod install it before `plugin update`, and a failing install applies nothing.
`tests/mods/run-mods-tests.sh`, `to-human/tests/mods/run.sh`, `tests/sminos/run-sminos-tests.sh`
green; `ci-gate` GREEN.

### M2 — MAWS's readers accept both names

**What exists at its end.** A MAWS PR, merged and deployed on each machine that runs the desk, with
the changes of §11: the desk, the renderer's transcript model, the fake machine and the contract's
sentence read both tool names, both framings and both plugin names; the desk shows a question raised
under either name as a question card and its answer on the row, and a steer or delivery the bridge
submits under either plugin name as the bridge's row.

**What it touches.** The files of §11's table and whatever its grep adds, in MAWS, on a branch off
`origin/master`, in a worktree of that repository.

**Decisions.** A ticket on MAWS's board registers this milestone with §11 as its body; the session
that takes it (a MAWS session, or this initiative's executor dispatched into that repository with the
spec path) owns the PR. The contract's version key moves only if MAWS's contract rule says a change of
wording moves it; the meaning does not change. Fixtures and recordings under the old name stay.

**What it does not touch.** The desk's protocol (`apps/desk-hub/src/protocol/session.ts`'s comments
may name both); no doperpowers file.

**What it proves.** A2's desk half: MAWS's unit tests for `classify.ts`, `ask-answer.ts`,
`delivery-frame.ts`, `bridge-rows.ts`, `card-state.ts` and the fake machine pin both names (`pnpm
test` in MAWS, the files' suites); `e2e/to-human-live.spec.ts` keeps passing with its filter widened.
The PR URL and the deployment on each machine are recorded in Progress.

### M3 — The carve-out and the rename

**What exists at its end.** One release of four plugins: `sminos` 1.0.0 at `sminos/` with the layout
of §2, the tool `mcp__sminos__AskUserQuestion`, the channel of §5, the bridge's order verdict of §4
(I1's `OrderVerdict`), the shim of §7; `doperpowers` 7.189.0 without sminos, reading the asks through the channel,
with the board resolver of §9; `to-human` 0.2.0 depending on sminos; `devcloud` 0.5.0 with step 11
looking for the CLI at the new path (the hosts' placement, step 10, is the devcloud session's own
change, §8, and lands on its own schedule). Every gate green in the new layout; the rehearsal of §10
passed; the documents of §10 say what is.

**What it touches.** The moves of §1 (`git mv`, so history follows); `sminos/.claude-plugin/plugin.json`,
`sminos/hooks/hooks.json`, `sminos/hooks/mods/register.tsx`, `sminos/types/sminos.d.ts`,
`sminos/README.md`, `sminos/tests/mods/run.sh`; `hooks/hooks.json` and `hooks/mods/register.tsx`
(doperpowers' remaining mods and shell hooks); `hooks/mods/appeal.tsx`, `reload.tsx`, `compact.tsx`
(§5; appeal's fake-guard case, §4); `ask.tsx` (the values of `ASK_TOOL` and `PLUGIN_PROMPT`, `KEPT`,
the shape-1 fallback, `isDialogUp` and `answered` in the snapshot); `bridge.tsx` (the verdict);
`agents/*.md` (nine), `output-styles/to-human.md`; `skills/issue-tracker/scripts/_lib.sh`,
`execute-dispatch.sh`, `board-sweep.sh`, `review-dispatch.sh`, `_sweep_api.sh`, `board-gc.sh`, the
three worker-protocol references and the issue-tracker and board-api tests of §9;
`skills/sminos/scripts/sminos_daemon.py` (`installed_cli`), the two service templates,
`skills/sminos/scripts/sminos.py` (the shim, in doperpowers, new) and the `sminos` launcher beside it;
`devcloud/boot/devcloudlib/sminos_host.py`, `devcloud/tests/unit/test_sminos_host.py`,
`devcloud/tests/integration.py`; `.claude-plugin/marketplace.json`,
`.version-bump.json`, `to-human/.claude-plugin/plugin.json`, `.github/ci-kit.yml`,
`tests/codex/test-marketplace-manifest.sh`, `tests/claude-code/run-skill-tests.sh`;
`sminos/tests/run-sminos-tests.sh` and every moved test file (the `PLUGIN_ROOT` name of §2, the cache
fixture and the shim's pin of §7, the hook paths, the live checks' staging of §9); `CLAUDE.md`,
`README.md`, `hooks/mods/README.md` → `sminos/hooks/mods/README.md`, `sminos/skills/sminos/SKILL.md`,
`references/setup.md`.

**Decisions.** One milestone, one release: the rename, the move, the manifests and the gates must land
in the same cutover (a half state — a tool registered under one name by two plugins, or a gate
pointing at a path that moved — is invalid). The sminos tests' root variable is `PLUGIN_ROOT`, the
plugin root. The doperpowers types file keeps the `types` key only while it declares a value (it
declares none after the move; drop the key or keep an empty contract — the executor's call, with
`claude plugin validate` as the judge). The appeal's read of `{ plugin: 'sminos', key: 'ask' }` types
through `import type` from `../../sminos/types/sminos` (erased at run time; `devcloud/types/devcloud.d.ts`
shows the read form); if `claude plugin validate` on doperpowers refuses a read of a contract that is
not enabled in the staged test plugin, the validate output is the authority and the doperpowers types
contract declares the key it reads. The bridge's verdict reads devcloud's key with the same form and
writes its own (I1's `OrderVerdict`). The shim is Python 3.9-safe (it may run under macOS's own `python3` before the
real CLI's version check). The board resolver reads `known_marketplaces.json` with `python3 -c` or
`jq`, whichever `_lib.sh` already uses. The `sminos/README.md` is short: what the plugin is, the
install lines with `prependPlugins`, pointers.

**What it does not touch.** `~/.claude/*` on any machine; MAWS; the old specs; the dormant board
doctrine's behaviour; DX5.

**What it proves.** A1 (the module loads with the events listed; the order of the `loaded` lines, in
the rehearsal's HOME; on a devcloud image through the devcloud gate), A5 (all five cases, in the
rehearsal's HOME), A6 (`tests/mods/appeal.test.ts` with the channel and the fake guard,
`tests/mods/reload.test.ts` with a fake `$.state` seeded at start), A8 (every gate; both validates;
the rehearsal). Tests pin: the ask tool registers under the new name; the snapshot carries
`isDialogUp` and `answered`, and a shape-1 value under doperpowers' key is taken up once; the bridge
names a compact-tool compaction's rows through its `session.compact` hook; the verdict table of §4,
row by row, with a fake `$.state` whose marker appears before or after `next` and whose version
moves or not, and the kept verdict reused; `installed_cli` returns the new clone path and its refusal
names it; the shim forwards to the sibling, else the installed plugin, else exits 1 naming `daemon
install`, and writes its line to stderr; the suite fails on that line; `sminos_host.py` finds the new
path, then the old; the resolver finds the CLI in each of its three places and `lib.sh` beside it. The issue-tracker and board-api gates run the board scripts against
the checkout's CLI through `SMINOS_CLI`.

### M4 — The roll and each machine's migration

**What exists at its end.** Every machine runs sminos 1.0.0 placed as §4 says, with its daemon
installed at the new path, and the owner's agents name the new tool. The desk shows all machines.

**What it touches.** Nothing in the repository but this spec's Progress and record. The owner's
files and services of §8, by the owner or on their explicit approval, one machine at a time.

**Decisions.** The steps of §8 (M4's) in that order on each machine; A1 and A7 checked on each; a
session with an open async ask at the swap is the test of §5's fallback (ask on one session before
the reload, answer after). M2 is deployed before the first machine rolls. The executor of this
milestone is the session the owner works with: it prepares each step's exact command and waits for
the owner's word per machine.

**What it does not touch.** The code.

**What it proves.** A1, A2 (end to end, with M2 deployed), A3 (a real resume on a transcript from
before the roll, and a `/branch` of one), A4 (both halves in temporary HOMEs on this machine), A7
(each machine).

### M5 — Cleanup and acceptance

**What exists at its end.** The shim and the ask's shape-1 fallback are gone, the agent definitions
name one tool, and the acceptance section stands executed.

**What it touches.** `skills/sminos/` in doperpowers (removed whole), `hooks/mods/ask.tsx`
(the fallback), `agents/*.md`, `.github/ci-kit.yml` (the `skills/sminos/**` path of the sminos
gates), versions of doperpowers and sminos.

**Decisions.** Runs only once every machine of M4 has rerun `daemon install` (A7 everywhere) and no
devcloud host runs an image older than M3 (§7): the shim is what a not-yet-reinstalled service or an
old image runs. The readers keep both names (§3).

**What it does not touch.** Any reader's acceptance of the old name.

**What it proves.** A9, and the whole of A1–A8 re-run as written in Concrete Steps, plus every suite.

### Concrete Steps

Working directory is the repository root of the worktree unless shown. `$H` is the temporary HOME
of the milestone's probe or rehearsal (never the real one for a probe).

```
# M1, M3, M5 — the suites and the gates
tests/mods/run-mods-tests.sh                 # doperpowers' mods
to-human/tests/mods/run.sh                   # to-human's mods
sminos/tests/mods/run.sh                     # from M3: sminos' mods (claude plugin test sminos; test-ask-search.sh)
bash sminos/tests/run-sminos-tests.sh        # from M3 (tests/sminos/run-sminos-tests.sh before); SMINOS_PART=core|suites
claude plugin validate sminos/.claude-plugin/plugin.json
claude plugin validate .claude-plugin/plugin.json
ci-gate                                      # on the committed HEAD; expect GREEN <run-url>

# A1 — the order, on a HOME that has the settings of §8 (the rehearsal's in M3, the real one in M4)
d=$(mktemp -d) && cd "$d" && HOME=$H SMNS_INTERNAL=1 /tmp/maws-review/with-slot.sh claude --debug -p "reply ok" --max-turns 1
/usr/bin/grep -h "hooks module .* loaded (worker" "$(ls -t $H/.claude/debug/*.txt | head -1)"
# expect, in this order:
#   hooks module to-human@doperpowers loaded (worker, environment 1, tier prepend); events: ...
#   hooks module sminos@doperpowers loaded (worker, environment 2, tier prepend); events: session.start,...,tool.call,...,session.append,...,attribution.text,...,tool.describe,...
#   hooks module doperpowers@doperpowers loaded (worker, environment 3, tier prepend); events: ...
#   hooks module <others> loaded (worker, environment N, tier user); ...
# (the engine logs a "hooks module order: dependencies register ..." line only when the dependency sort changed the order)

# A5 — the verdict, in the rehearsal's HOME with devcloud and sminos enabled
#   (a) no prependPlugins: a debug line opening "sminos: the bridge is off" (a toast in an interactive session), no $SMINOS_HOME/bridge/<session>.sock
#   (b) prependPlugins set: the socket; no line
#   (c) then bump sminos's version in the local marketplace, /reload-plugins: the socket served again; the verdict record says kept
#   (d) bump devcloud's and sminos's: the socket; the record says moved
#   (e) as (a), bump both, /reload-plugins: still off

# The rehearsal (M3) — see §10; its end state is checked as A2's terminal half plus A1 and A5(b)

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

**I1 — The ask snapshot, `sminos/types/sminos.d.ts`** (the one value sminos publishes about asks;
read by appeal and reload in doperpowers, written by the ask alone, on every change of any field):

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

/** The bridge's place among the guards, decided at the process's first start and kept across reloads (§4). */
export type OrderVerdict = {
  verdict: 'outside' | 'inside'
  /** What decided it: devcloud's marker moved during `next` (inside sminos), was absent throughout, was present before the first `next`, or the kept verdict was reused. */
  evidence: 'moved' | 'absent' | 'present-first' | 'kept'
  at: number
}

declare module 'claude-code' {
  interface PluginState {
    sminos: { ask: AskSnapshot; order: OrderVerdict }
  }
}
```

The references, written as literals in each reader: `{ plugin: 'sminos', key: 'ask' } as const` and
`{ plugin: 'sminos', key: 'order' } as const`. A reader hooks writes with `on('state.set', { plugin:
'sminos', key: 'ask' }, ($, e, next) => ...)` and reads `e.value` as an `AskSnapshot`;
`$.state.get(ref)` answers `{ value, version }`, `undefined` at version 0 where sminos is not loaded.

**I2 — The order probe's input** (sminos reads, devcloud writes; defined by devcloud, `types/devcloud.d.ts`):
`{ plugin: 'devcloud', key: 'secrets-guard' }` → `{ owner: 'devcloud'; version: 1 } | undefined`,
with its `version`. Read twice in the bridge's `session.start` hook, before and after `next`.

**I3 — The names.** In each reader, beside the registered name:
`ASK_TOOLS = ['mcp__sminos__AskUserQuestion', 'mcp__doperpowers__AskUserQuestion']` and
`PLUGIN_PROMPTS = ['The sminos plugin sent a message:\n', 'The doperpowers plugin sent a message:\n']`
(ask.tsx, to-human.tsx, sminos.py, and the equivalents in MAWS's readers of §11, which also hold the
plugin-name set `['sminos', 'doperpowers']`) — no shared module crosses plugins or repositories.
`ASK_TOOL` and `PLUGIN_PROMPT` stay the one registered name and this plugin's own framing: in M1
their values are the old ones; from M3, `ASK_TOOLS[0]` and `PLUGIN_PROMPTS[0]`.

**I4 — The CLI's stable path.** `<installLocation>/sminos/skills/sminos/scripts/sminos.py` where
`installLocation` is `known_marketplaces.json`'s `doperpowers.installLocation`; the launcher beside it
is `sminos`, and `lib.sh` beside that. Used by `installed_cli` (the daemon), `sminos_host.py`
(devcloud boot; the old path second), the board resolver, and the shim.

**I5 — The shim.** `skills/sminos/scripts/sminos.py` in doperpowers, M3 through M4: `python3 sminos.py
<args>` execs `<real sminos.py> <args>` under `sys.executable`, the sibling first, the installed
plugin's second; one stderr line per forward, `sminos: forwarded from the retired path <shim>; rerun
sminos daemon install`; exit 1 with one line on stderr naming `sminos daemon install` when no real
CLI is found. No other behaviour.

**I6 — The board resolver.** `_lib.sh`'s `sminos_cli` (a function, exported as `SMINOS_CLI` once
resolved) in the order of §9, and `sminos_lib` = `$(dirname "$SMINOS_CLI")/lib.sh` for the scripts
that source it; the worker-protocol templates take `{{SMINOS_CLI}}`.

**I7 — The gates.** `sminos`, `sminos-suites`, `sminos-mods` as §10 names them, with their `paths`;
the `mods` gate's added paths.

**I8 — The hosts' managed placement** (devcloud's, owned by the devcloud setup session, §8; what this
spec relies on, not what it builds): `/etc/claude-code/managed-settings.json` on a host carries the
profile's `env`, `prependPlugins` copied from the synced `~/.claude/settings.json`, and
`enabledPlugins` true for exactly those ids; boot step 10 and `devcloud reconcile` write it after
every pull, so a change to the Macs' list reaches every host by itself.

**Dependencies.** The engine at 2.1.303 (hooks modules, `$.state` with `state.set` and versions,
`prependPlugins`); bun and `claude plugin test` for the mods' tests; P0 on `main`; MAWS
`origin/master` at or after M2's merge, deployed, for A2's desk half and the roll.

## Surprises & Discoveries

- Observation: the engine's dependency sort pushes a depended-upon plugin behind every plugin nobody
  depends on, and doperpowers — depended upon by to-human — therefore registered innermost, inside
  devcloud's secrets guard: the bridge's `tool.call` hook saw a call's input with the secret bytes
  restored and its result before it was scrubbed (rows are scrubbed before the chain, so
  `session.append` was safe). The mods' README's "registered first, so its hooks are the outermost"
  held within doperpowers only. Closed on the Macs by M0 the same day.
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
  hookable event, so a plugin can observe another's writes; and because the values survive a hot
  reload while a reload reruns only the reloaded plugin's `session.start`, a marker's mere presence
  cannot tell order at a reload — its version moving during `next` can, and otherwise a kept verdict
  must.
  Evidence: `.claude/types/claude-code.d.ts` 3460 ("held by the host for the session … survives a hot
  reload … Any plugin reads any value; its owner alone writes it. Persist through `$.store`"), 12648
  (`on("state.set", DRIVE, …)`), and the `StateRead` type's version ("goes up by one on every write
  that lands"); `ask.tsx`'s own `session.start` ("A module loaded into a running session (a reload)
  takes up the asks the one before it kept"); `cua`'s `one-guard.tsx` reads devcloud's marker. The
  first draft's probe would have switched the bridge off at every `/reload-plugins` (first review,
  both reviewers).
- Observation: cua 0.15.0 carries devcloud's guard as a vendored copy that acts when devcloud is
  absent and writes no marker, so no probe sees it; only placement covers it.
  Evidence: `~/.claude/plugins/cache/cua/cua/0.15.0/hooks/mods/guard/secrets.tsx` 280–291 ("cua
  adaptation: devcloud's marker write is removed") and `one-guard.tsx` ("cua never writes it, nor any
  marker of its own").
- Observation: a call's input reaches the bridge's permission-request path in the restored form
  whatever the order: the engine's permission check runs after every `tool.call` hook has rewritten
  the input.
  Evidence: `bridge.tsx` `tool.check` (`input: e.input`) and `classic.PermissionRequest`
  (`capped(e.tool_input)`, `rawInput`); the adversarial review of 2026-10-19; P0 in flight.
- Observation: the roll is unattended and updates only installed plugins, so a release that moves
  the ask into a plugin nobody installed would reload sessions without it; the engine installs a
  plugin's dependency closure on install and tracks auto-installed dependencies (`claude plugin
  prune`), which M1's reload mod makes explicit for updates.
  Evidence: `reload.tsx` 293–300 and 407–414 (`claude plugin marketplace update <name>`, then
  `claude plugin update <key> --scope user` per enabled installed plugin); `cli.pretty.js` 779586
  (the closure walked at install), 410058 ("auto-installed dependencies no longer needed … `claude
  plugin prune`"), 239075 ("Dependency … is not installed").
- Observation: a `prependPlugins` name may be listed before its plugin exists.
  Evidence: `rSr` (744547): `names ${K}, which is not an enabled plugin with a hooks module; skipped`
  — a debug line, not a refusal; the owner's probe sessions after M0 on 2026-10-19 show to-human and
  doperpowers in the prepend tier with sminos not yet installed.
- Observation: on a managed machine the engine ignores the user's tier keys and gates whole events
  for plugins a person installs, and devcloud hosts are managed today by a four-key `env` block.
  Evidence: `E5` (410255: the user's `prependPlugins` read only when `Vee() || s8n()` is false),
  `Vee` (409728: any non-empty `policySettings`), `Mir` (949953: the gated events "pass over the
  plugins you install, and only a plugin the organization lists in managed settings runs them"),
  `Z8r` (949946: the event list); `devcloud/boot/devcloudlib/steps.py` 34 (`MANAGED_SETTINGS`) and
  the devcloud spec's §6; the owner's account of the hosts' managed file (2026-10-19).
- Observation: a process-environment value cannot override a key the synced `settings.json` carries:
  settings `env` overwrites the process environment tier by tier. So the hosts' values stay in the
  managed file (seven keys, not four: the gateway's base URL and switches, and blanks for
  `CLAUDE_CODE_PLUGIN_DIRS` and the extension token), and the placement lists join them there (§8).
  Evidence: `applySafeConfigEnvironmentVariables`, verified on 2.1.303 by the devcloud setup session
  (2026-10-19); the same reading in `cli.pretty.js` 481455–481468 (`KL` merges each scope's `env`;
  `jp` returns `{ ...dte(), ...KL(WL()) }`) and 1037482–1037490 (`o0r` writes the computed env back
  into `process.env`); the synced file's `ANTHROPIC_BASE_URL` is the Mac's loopback relay
  `127.0.0.1:8641` (the owner, 2026-10-19).
- Observation: a host-side rewrite of the received `settings.json` (this spec's second draft) cannot
  stand: `~/.claude` on a host is a receive-only clone reset to its remote every 30 minutes, with an
  invalid push URL and a reconcile that re-applies boot steps 5–11 on a new commit; a rewrite is
  undone at every reset, sessions hot-reload the Mac's values in between, and the clone is left
  dirty.
  Evidence: the devcloud spec's §5; `devcloudlib/steps.py` `home()` (the files written into the
  user's home) and the devcloud setup session's account (2026-10-19).
- Observation: on a managed machine with no policy `prependPlugins`, the built-in
  `cc-plugin-sec-default@builtin` is seated outermost and passes the plugins a person installs over
  on `prompt.*`, `session.compact`, `settings.read`, `classic.*` and three `session.append` doors; a
  policy `prependPlugins` that does not list it leaves it unseated, and the pass-over most likely
  goes with it, `Mir` being only the note the diagnostic appends. A reading of the source, not yet
  observed; the devcloud session's container run decides it, hooks watched under the candidate
  managed file and under today's env-only one (§8).
  Evidence: `cli.pretty.js` ~191161 (the registry module exporting `passedOverNoteOf` = `Mir`,
  `cPr` the seat, `PASSED_OVER_EVENTS` / `DOORS`, sec-default's `registerPlugin`), ~246146 (its one
  call site, on the `hooks:` diagnostic line), 949943–949952 (`Z8r`, the event list); present since
  2.1.287 (the devcloud session, 2026-10-19).
- Observation: a daemon whose scripts vanish re-executes itself at its original path and exits when
  that fails; the service then restarts it every 60 s against the same missing path; and devcloud's
  boot runs the image's copy of `sminos_host.py`, not the plugin's.
  Evidence: `sminos_daemon.py` `own_code`, `restart_in_place` (`os.execv(sys.executable,
  [sys.executable] + sys.orig_argv[1:])`), the `except OSError` at its call site ("exiting for the
  service manager to restart it"); `ThrottleInterval 60` in `sminos-daemon.plist`;
  `devcloud/image/setup.sh` 86–87 (`cp -R "$plugin/boot/." /usr/local/lib/devcloud/`).
- Observation: the doperpowers plugin cache is the whole repository, sibling plugin folders included.
  Evidence: `ls ~/.claude/plugins/cache/doperpowers/doperpowers/7.188.8/` lists `devcloud` and
  `to-human`; the marketplace entry's source is `./`.
- Observation: MAWS matches the plugin's name in more places than the ask: a prompt row's
  `origin.name` in `ask-answer.ts`, the bridge's rows in `delivery-frame.ts` and `bridge-rows.ts`,
  and the fake machine's rows; a rename that only widened the tool name and the framing regex would
  still drop sminos's deliveries and steers.
  Evidence: `git grep -n "'doperpowers'" origin/master -- apps src` on 2026-10-19:
  `apps/desk-web/src/conversation/ask-answer.ts:24`, `delivery-frame.ts:53` (`BRIDGE_PLUGIN`),
  `depth/source/bridge-rows.ts`, `apps/desk-hub/fake-machine/machine.ts:725`, `session.ts:537`,
  `session-view.py:395`.
- Observation: the board's dormant scripts and their worker-protocol templates reach the CLI, and
  `lib.sh`, by a relative path through the skills folder in nine files and five tests, not the three
  the first draft named.
  Evidence: `git grep -n "sminos/scripts" origin/main -- skills/issue-tracker tests` on 2026-10-19
  (the list in §9).

## Decision Log

- Decision: verification — one independent spec review by the `doperpowers:adversarial-reviewer`
  agent (dispatched with `model: opus` while the Codex models are at their limit, until 2026-10-24)
  and, the execution section having five milestones, its buildability review in the same round; the
  branch review for each code milestone through doperpowers:review-code at **xhigh** (the panel): the
  change crosses four plugins, a settings-placed guard invariant and every machine. M2's branch is
  reviewed by MAWS's own rule.
  Rationale: the stakes, not the size; the owner named xhigh.
  Date/Author: 2026-10-19, the spec's author.
- Decision: the plugins' order is placed by the owner's `prependPlugins` (three entries), and the
  bridge refuses to stream when it finds itself inside devcloud's guard; sminos declares no dependency.
  Rationale: §4 — the engine's dependency rule puts the dependent outside and pushes the depended-upon
  inward, so no declaration gives a standalone sminos the outer place; install order gives a fresh
  install the innermost. Rejected: `sminos` depending on `doperpowers` (not standalone, and still
  inside devcloud); `appendPlugins` for devcloud and doperpowers (the same owner edit with a
  stranger meaning); streaming regardless (the state before M0).
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
- Decision: `devcloud/README.md` and the devcloud spec's §5, §6 and §8 describe the CLI at
  `<clone>/skills/sminos/scripts/sminos.py` and the hosts' managed settings as an `env` block alone;
  from M3 the CLI is `<clone>/sminos/skills/sminos/scripts/sminos.py`, and the managed file gains
  the placement lists when the devcloud session's route lands (§8, I8). Recorded here rather than
  rewriting that spec.
  Date/Author: 2026-10-19, the spec's author.
- Decision (first review round): the order probe decides by the marker's version moving during
  `next` and keeps its verdict under `sminos.order` across reloads; `prependPlugins` changes take
  effect at a new process.
  Rationale: a marker's presence is ambiguous at a reload (Surprises); the first draft's probe would
  have switched the bridge off at every `/reload-plugins`, the roll's included. Rejected: probing at
  every start by presence alone; clearing devcloud's marker (not sminos's to write).
  Date/Author: 2026-10-19, the spec's author, after both reviewers.
- Decision (first review round): M0 — `prependPlugins` and the `sminos@doperpowers` entry before
  M1; M1's reload mod installs new dependencies before it reloads; M3 is rehearsed on a local
  marketplace named `doperpowers`.
  Rationale: the roll is unattended and updates only installed plugins (§10). Rejected: relying on
  `plugin update` to install a new dependency (unverified; the rehearsal checks it, the mod does not
  depend on it); asking the owner to be present at each machine's roll.
  Date/Author: 2026-10-19, the spec's author, after both reviewers; M0's first step done by the
  owner the same day.
- Decision (first review round): the guard invariant is placement plus the bridge raising only the
  input it captured (P0, a prerequisite), not placement alone.
  Rationale: the permission path carries the restored input past every `tool.call` hook (§4).
  Date/Author: 2026-10-19, the spec's author, after the adversarial reviewer.
- Decision (first review round, superseded the same day): devcloud hosts' placement is the devcloud
  setup session's route — the managed file keeps the profile's env and gains `prependPlugins` copied
  from the synced `settings.json` and `enabledPlugins` for those ids (I8) — owned and built by that
  session, pending its container result, with the sec-default seat and the pass-over of unlisted
  plugins' hooks as what decides it and "every plugin policy-listed" as the fallback if unlisted
  hooks are still passed over; a host enrolls at the desk only once it boots an image carrying the
  route. This spec defers to it.
  Rationale: §8. Rejected: the process-environment route (settings `env` overwrites it tier by
  tier; the synced base URL would win); this spec's second-draft overlay on the received
  `settings.json` (undone at every 30-minute reset, the Mac's values hot-reloaded in between, the
  clone left dirty — the file is the Mac's, and only the managed tier is the host's to write). Both
  in Surprises.
  Date/Author: 2026-10-19, the spec's author, after the adversarial reviewer, the owner's account of
  the hosts' settings, and the devcloud setup session's decision.
- Decision (first review round): `ASK_TOOL` and `PLUGIN_PROMPT` stay the registered name and the
  plugin's own framing, with `ASK_TOOLS` and `PLUGIN_PROMPTS` beside them for readers; the shim tries
  the sibling first; every moved test file names its root `PLUGIN_ROOT` and the suite fails on the
  shim's stderr line; `sminos_host.py` accepts the old path second and M5 waits for every image
  older than M3 to be gone; all board files and templates route through I6 and `lib.sh` is sourced
  beside the resolved CLI; `live-appeal-check.py` and `live-compact-offer-check.py` stay; the `mods`
  gate watches `sminos/types/**` and `ask.tsx`; `test-smns-guide-hook.sh` joins the sminos suite;
  reload seeds its dialog mirror at `session.start`; A1 and the rehearsal run against a temporary
  HOME; appeal outside the guard is pinned, not reordered.
  Rationale: the buildability and adversarial findings of 2026-10-19, each checked against
  `origin/main` 5395bbc2 and MAWS `origin/master`. Nothing rejected in that round; one finding
  (the M3 proof's "the old name is refused with `WITHDRAWN`") was dropped as unprovable — no plugin
  registers the old name after M3.
  Date/Author: 2026-10-19, the spec's author.

## Outcomes & Retrospective

Pending — written at finish.
