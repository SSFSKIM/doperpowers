# sminos — its own plugin

**Date.** 2026-10-19. **Status.** Outline approved by the owner on 2026-10-19 (split, same marketplace;
AskUserQuestion moves and is renamed; the peer roster is a separate initiative); this document is the
design and its execution, written against the code and the engine (2.1.302 bundle, 2.1.303 installed);
revised 2026-10-19 after two independent review rounds and the devcloud setup session's container
results (Decision Log). Rebased on `origin/main` 0176e090 (#273, doperpowers 7.189.0; #274, devcloud
0.4.2; #270, the copy/fork resume rebuilding async asks, which the first draft waited on). **Prior
art, reference only.** `docs/doperpowers/specs/2026-10-15-devcloud-design.md` (the second plugin
carved out of this repository, and the `$.state` marker another plugin reads);
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
- [x] (2026-10-19 18:00Z) First independent review round (two reviewers) absorbed: the roll's reload
      path, MAWS's plugin-name readers, devcloud hosts' managed settings, the permission-prompt leak
      as a prerequisite, the board files, the drift against main (Decision Log, 2026-10-19).
- [x] (2026-10-19 21:00Z) Second round and the devcloud container results absorbed: the order probe
      moved to `next.trace` as a spike at the head of M3, the ask's `PLUGIN` literal, the rehearsal's
      git remote, the reload mod's trigger, the versions, M0's `enabledPlugins` as a precondition, the
      hosts' current state (Decision Log, 2026-10-19).
- [x] (2026-10-19, the owner) **M0, first step, on the Macs**: `prependPlugins` applied in
      `~/.claude/settings.json` on the MacBook and the Mac mini; probe sessions show `to-human` and
      `doperpowers` in the prepend tier, `devcloud` inner.
- [x] (2026-10-19, the owner) **M0, second step**: `enabledPlugins["sminos@doperpowers"] = true` on
      the MacBook and the Mac mini, each `settings.json` backed up as `settings.json.bak-*` before
      the edit (the owner approved both one-time edits). A debug-log probe confirmed to-human and
      doperpowers in the prepend tier with cua and devcloud inside them; until the plugin exists the
      engine logs "Skipping orphaned enabledPlugins entry" for sminos at debug level. M0 is complete
      on both Macs.
- [x] (2026-10-19) P0 — the bridge raises a permission request's input in the handle form it
      captured: #276, merge 02ef424f, doperpowers 7.189.3, rolled to both Macs. Its residue is in
      `docs/doperpowers/TECH-DEBT.md` ("the bridge's raise and the secrets guard"); a separate change
      fixes that section's second item (the bridge's tool result event carries no text for a result
      devcloud scrubbed) in `bridge.tsx`, merged into the milestone branches once it lands.
- (2026-10-19) #269 (`smns-guide-fork`) merged as 2018dab2; #271 (`smns-guide-roster`) merged as
  cf8a3b26 (7.189.4), #278 (the reload's rows) as 457d2367 (7.189.5) and #279 (the bridge's text for
  a scrubbed result, P0's residue) as 92387afa (7.189.6), each taken into M1 by a merge of main.
- [x] (2026-10-19 17:30Z) M3a — the `next.trace` spike: **promote**, amended to a verdict on every
      dispatch (Surprises & Discoveries, Decision Log; report in the run's SDE workspace,
      `task-3-report.md`; temp tree `/tmp/m3a-spike.cX0Q8E`).
- [x] (2026-10-19 17:50Z) M2 — MAWS PR https://github.com/SSFSKIM/MAWS/pull/74, merge 9fd93735e
      (gate run 39295926848 green; task review approved), deployed by the author 17:53Z
      (hub@9fd93735, web@master.9fd93735). Residue: MAWS #75 (the live spec's to-human path).
- [x] (2026-10-19 19:10Z) M1 — doperpowers' readers accept both names; the reload mod installs a
      plugin's new dependencies and updates whenever an installed version differs from the clone's,
      holding back a failed dependency's closure and every reload that would load a plugin over a
      missing dependency (doperpowers 7.189.7, to-human 0.1.2). Reviewed clean: task review (opus)
      and branch review (reviewer-high on fable), two fix waves (Decision Log, M1 review and fix
      waves). PR https://github.com/SSFSKIM/doperpowers/pull/281, merge 359c71a6 (ci-gate GREEN,
      run 39303896510).
- [x] (2026-10-19 23:56Z) M3 — The carve-out and the rename, opened by the `next.trace` spike
      (M3a), rehearsed on a local git remote. Built in three steps on `sminos-m3-carveout`, each
      task-reviewed clean: M3.1 (20:51Z, the carve-out and the rename), M3.2 (22:20Z, the probe, three
      fix waves), M3.3 (23:00Z, the rehearsal: the roll applied on its own, no `--force`; A1, A2's
      blocking clause, A5 (a)–(f), A8's rehearsal half all held). The xhigh panel (the author's, opus
      finders and a fable verifier) returned incorrect with five confirmed findings, fixed or logged
      and re-reviewed clean. PR https://github.com/SSFSKIM/doperpowers/pull/282, merge 7c809e84
      (ci-gate GREEN, run 39343694214): sminos 1.0.0, doperpowers 7.190.0, to-human 0.2.0, devcloud
      0.6.0.
- [x] (2026-10-20 02:25Z, the author and the owner) M4 — The roll and each machine's migration, on
      the MacBook and the Mac mini. Rolled by the CLI at about 23:56Z, no `--force` (`claude plugin
      marketplace update doperpowers`, `plugin install sminos@doperpowers --scope user`, `plugin
      update` of the four), both at sminos 1.0.0 / doperpowers 7.190.0 / to-human 0.2.0 / devcloud
      0.6.0, then rolled on to #283 (sminos 1.0.1, 00:40Z) and #284 (sminos 1.1.0, 00:52Z). A1: the
      order to-human, sminos, doperpowers (prepend), then prompt-autosave, cua, devcloud on both.
      A2/A3: two async asks opened under `mcp__doperpowers__AskUserQuestion` before the roll were
      answered after it and delivered as `The sminos plugin sent a message: …`, both answers whole.
      The owner's `astra.md` and `sol-xhigh.md` name the new tool beside the old. A7: `sminos daemon
      install` rerun at about 02:24–02:25Z on both; the plist's `ProgramArguments[1]` is
      `~/.claude/plugins/marketplaces/doperpowers/sminos/skills/sminos/scripts/sminos.py`, the daemons
      run it, the uplinks connected (MacBook stream 196 at 02:24:59Z, mini stream 165 at 02:25:35Z),
      and no forward line since the 23:57Z one of the roll. No devcloud host is enrolled, so M5's
      image condition holds vacuously.
- [x] (2026-10-20 03:31Z) M5 — Cleanup and acceptance, on `sminos-m5-cleanup` off origin/main
      2ddab4c5: the shim, the ask's shape-1 takeover and the agents' old name removed, the gate path
      dropped (7974a3e5; doperpowers 7.190.1, sminos 1.1.1). A1–A6, A8's rehearsal half and A9's grep
      held in temporary HOMEs at that head, A4 for the first time, the rehearsal rolling a HOME from
      origin/main to it unattended; every suite green; the branch review (`reviewer-high` on fable)
      found nothing material; ci-gate GREEN on the PR head's tree. The author merges, rolls and checks
      A7 and A9 on both Macs.
- Not a milestone here: the devcloud hosts' placement (§8, I8), the devcloud setup session's; a
  precondition for enrolling a host, blocked today.

## Terms

- **Plugin.** A directory with `.claude-plugin/plugin.json` that the harness installs from a
  marketplace; this repository is one marketplace (`.claude-plugin/marketplace.json`) holding
  `doperpowers` (source `./`, the repository root), `devcloud` (`./devcloud`), `to-human`
  (`./to-human`), `ci-kit` (a URL source, another repository), and after this work `sminos`
  (`./sminos`). A plugin is addressed as `<name>@<marketplace>`: `sminos@doperpowers`.
- **Hooks module.** A plugin's function hooks: the `modules` entry of its `hooks/hooks.json` (here
  always `./mods/register.tsx`), loaded only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. A **mod** is
  one file of it that registers hooks on `on(...)`. A **module instance** is one load of it: the
  process's first, or a reload's.
- **Outer and inner.** The engine runs every plugin's hooks on an event as nested wrappers: the
  module registered first is outermost, sees the event first and the result last; the one registered
  last is innermost, closest to the engine's own action. The order is decided per session at load
  and again at a reload (§4). A hook sees what settled beneath it on its last `next()` in
  `next.trace`: one entry per link beneath, nearest first, each with the link's `plugin`, `tier` and
  `index` (0 the outermost), ending at the engine's own entry.
- **A guard.** A mod that keeps secrets out of what the model reads: devcloud's (`devcloud/hooks/mods/secrets.tsx`)
  and `cua`'s vendored copy of it (`cua` 0.15.0, `hooks/mods/guard/`), which acts only when
  devcloud's is absent. In `tool.call` a guard restores a handle's secret bytes into a Bash or Write
  call's input before calling `next`, and scrubs the result on the way out; in `session.append` it
  scrubs a row before calling `next`. devcloud's loaded module answers a marker, `{ plugin:
  'devcloud', key: 'secrets-guard' }`, at version 0 through its own `state.get` hook, and stores
  nothing: only that version-0 answer means devcloud's guard is loaded now, and a stored value at
  version 1 or more is one an older devcloud left, which can outlive its module (board #101).
  cua's writes none.
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
  only its owner writes it; `state.set` is a hookable event any plugin may observe.
- **The roll.** The moment a machine's marketplace clone and installed plugins move to the M3
  release and its live sessions reload — unattended: the reload mod (`hooks/mods/reload.tsx`)
  fetches the `autoUpdate` marketplaces every five minutes, updates the enabled plugins installed from
  them, and runs `/reload-plugins` in every idle session.

## Acceptance

Numbered so milestones can point at them. Each is checked on this machine in a temporary HOME and
SMINOS_HOME unless it names another machine or the real HOME.

- **A1 — The plugin exists and is placed.** In a HOME with `sminos@doperpowers` enabled and the
  settings of §8 applied (a temporary one in M3 with the rehearsal's marketplace; the real one on each
  machine in M4), `HOME=<that> claude --debug -p "reply ok" --max-turns 1` in an empty directory with
  `SMNS_INTERNAL=1` writes a debug log (`<that HOME>/.claude/debug/<session>.txt`) whose `hooks
  module … loaded (worker, environment N, tier …)` lines come in the order `to-human@doperpowers`,
  `sminos@doperpowers`, `doperpowers@doperpowers`, each `tier prepend`, before every other plugin's
  module (`tier user`), and `sminos@doperpowers`'s line lists `session.start`, `tool.call`,
  `session.append`, `attribution.text`, `tool.describe` among its events. On a devcloud host it
  holds only once the hosts' placement (§8) exists; none is enrolled today.
- **A2 — The ask round trip under the new name.** In an interactive session in a project (this
  repository), the model calls `mcp__sminos__AskUserQuestion` with `async: true`; the call returns at
  once with the waiting text; the question shows behind `[ answer ]` and in the `N open questions`
  band; after the answer, the model's next message quotes it, and `sminos chat --host` lists the
  `question` and `answered` events; the desk (MAWS, with M2 deployed) shows the question card and its
  answer. The transcript's user row opens `The sminos plugin sent a message:` when the session was
  idle. A blocking call (`async` absent) opens the engine's dialog with every question of the call,
  not the first alone (the ask's own raise is claimed and widened under the plugin's real name, §3).
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
- **A5 — The bridge knows its place among the guards, per module instance.** In the rehearsal's HOME
  with `devcloud` and `sminos` enabled, if M3a promoted the probe: (a) no `prependPlugins`, with sminos registered inside devcloud (devcloud ahead of it in
  `enabledPlugins`): after the
  session's first tool call the debug log carries a line opening `sminos: the bridge is off` naming
  `prependPlugins` (an interactive session shows it as a toast too), no `tool` event was posted
  before it (the hold is a barrier, §4), and `$SMINOS_HOME/bridge/<session>.sock` serves nothing after it;
  (b) with `prependPlugins`: the first tool call's `tool` events carry their payloads once the verdict
  is in, and the line is absent; (c) with `prependPlugins`, after `claude plugin update
  sminos@doperpowers` (a version bump in the marketplace) and `/reload-plugins`, the new module
  reaches the same verdict on its first tool call and the socket is served; (d) the same after
  updating both devcloud and sminos; (e) as (a) after updating both: still off; (f) off recovers: in
  (a)'s HOME, setting `prependPlugins` and running `/reload-plugins` re-instantiates sminos at its new
  tier, so a new module's first verdict is safe and the socket is served again, with no off line and
  no "back" toast (a replaced instance is not a recovered one); the in-instance recovery is seen when
  the guard moves inward instead — with sminos off, `appendPlugins: ["devcloud@doperpowers"]` and
  `/reload-plugins` reload devcloud alone, and the living sminos instance logs and toasts `sminos: the
  bridge is on again`, serves the socket, and posts the next call's payloads. If M3a discarded the
  probe, A5 is: the rehearsal's debug log shows the order of A1 and no verdict line exists.
- **A6 — appeal and reload read the asks through the channel.** `tests/mods/appeal.test.ts` passes
  with the judge's evidence carrying an answered ask read from `{ plugin: 'sminos', key: 'ask' }`,
  a pass ending when that value's `answered` count grows, and a block devcloud's guard turned into a
  `{ deny }` beneath appeal still appealed (§4, "appeal outside the guard"); `tests/mods/reload.test.ts`
  passes with the reload waiting while the value says a dialog is up, seeded from a read at
  `session.start`.
- **A7 — The daemon survives the roll and reinstalls at the new path.** On each machine (the MacBook
  `SK`, the Mac mini, each enrolled devcloud host once one exists): after the roll, `sminos daemon
  status` reports the daemon running and the hub shows the machine, the daemon's stderr
  (`$SMINOS_HOME/daemon.out`, not `daemon.log`) naming the shim's forward once; after `sminos daemon install` and the service reload, the service file names
  `<marketplace clone>/sminos/skills/sminos/scripts/sminos.py` (`plutil -p ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`
  on macOS, `systemctl --user cat sminos-daemon.service` on Linux).
- **A8 — Every suite is green in the new layout.** `ci-gate` on the M3 commit is GREEN with the gates
  of §10, `claude plugin validate sminos/.claude-plugin/plugin.json` and
  `claude plugin validate .claude-plugin/plugin.json` both pass, and the rehearsal (§10) ends with
  the reload mod having rolled the HOME on its own, its open question still open, the bridge's socket
  served, to-human folding the transcript, `sminos chat --host` listing the question, and the
  reload's answer recorded (applied, or held for `--force`).
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
repository root; after the move the plugin root, one level up rather than two — Surprises, M3.1), `envelope_parity.py` and
`fake_session.py` build `skills/sminos/scripts` from `__file__` the same way, and `test_rpcs.py`
finds `mods/live-resume-check.py` beside itself. M3 gives every one of them one name,
`PLUGIN_ROOT`, in place of the `REPO_ROOT` that no longer means the repository, and the suite fails if any run ever reaches the shim (§7).

### 3. The tool's new name, and every reader accepting both

The MCP tool a plugin registers is named `mcp__<plugin>__<tool>` by the engine, so the move renames
it: `mcp__sminos__AskUserQuestion`. The plugin prompt framing follows the same way:
`The sminos plugin sent a message:`, and so does the `origin.name` of every row the ask or the bridge
submits. None of the old forms can be rewritten out of existing transcripts, and a session may be
resumed, compacted or forked across the roll, so **every reader accepts both names, both framings and
both origin names, for good** — not for a transition. The readers, from the grep of 2026-10-19 on
`origin/main` (the ones that match on the name rather than merely mention it):

| Reader | What it matches today | After |
|---|---|---|
| `hooks/mods/ask.tsx`: `asksIn` (`block.name === ASK_TOOL`), `deliveryTexts` and `historyAsks`' `prompt()` (`text.startsWith(PLUGIN_PROMPT)`), `STORED_FORMS` (the search's literals) | the one name, the one framing | the sets `ASK_TOOLS` and `PLUGIN_PROMPTS` beside `ASK_TOOL`, which stays the registered name (`PLUGIN_PROMPT`, a reader's constant only, removed in M1); `STORED_FORMS` carries one literal per name and per framing |
| `hooks/mods/appeal-judge.tsx`: `PLUGIN_PROMPT = /^The \S+ plugin sent a message:\n/` | any plugin | unchanged |
| `to-human/hooks/mods/to-human.tsx`: `ASK_TOOL`, `ASK_DELIVERY` | the one name, the one framing | both |
| `skills/sminos/scripts/sminos.py`: `ASK_TOOL` (3306; read at 3452 and 3807), `PLUGIN_PROMPT` (3312; read at 3367) | the one name, the one framing | both; `tests/sminos/test-bridge-export.sh` 137 and 153 follow |
| `hooks/mods/ask.tsx`: `PLUGIN = 'doperpowers'` (12), **a literal, not `$.plugin.name`** — read by `claim()` (the ask's own `$.ui.ask` raise, claimed only when `origin.plugin === PLUGIN`), the widening hook on `AskUserQuestion`, the bridge's `isDialog` (`bridge.tsx`) and `enteredRow` (`bridge-rows.tsx`, `origin.name !== PLUGIN`) | the plugin's name as the string `doperpowers` | the plugin's real name: M3 sets `PLUGIN` from `$.plugin.name` at `session.start` (or changes the literal to `sminos` explicitly), and a test asserts it equals `sminos/.claude-plugin/plugin.json`'s `name`. Left as is, the ask's own raise would pass unwidened and unclaimed (a blocking ask would show one question), `isDialog` would be false and `enteredRow` would never match — and the suites would stay green, because the fixtures hard-code the same string (`ask.test.ts` 154; `bridge.test.ts` 177, 2123, 3171, 3219, 3407): they import `PLUGIN` instead |
| MAWS (§11) | the one name and the one plugin name | both |

The mid-turn framing (`The <plugin> plugin sent a message while you were working:`) is matched by no
reader in either repository — the ask submits only when the session is idle — and stays unmatched.

`ASK_TOOL` stays the one registered name: `bridge.tsx`, `bridge-rows.tsx`, `bridge-requests.tsx`,
`bridge.test.ts` and `test-ask-search.sh` import it as such, and the `tool.describe` / `tool.call`
matchers, `WITHDRAWN`'s sentence and the `AskSnapshot` key read it. M3 changes its value and
`PLUGIN`'s, with the readers already dual (`PLUGIN_PROMPT` went in M1: it had readers only, the engine
writing the framing, so the set replaced it; Decision Log, M1). The nine agent definitions' `disallowedTools` name the
new tool beside the old through M4 (an entry naming no tool is inert, and a session resumed mid-roll
may still see the old one); M5 drops the old. The output style names the new tool and keeps its
fallback sentence for a session without it. The owner's own `~/.claude/agents/astra.md` and
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
   needed); an unmet one leaves the dependent unloaded ("Dependency … is not installed"), and the
   engine's own session-start pass resolves missing dependencies on its own (~157455). `claude plugin
   install` writes the plugin's `enabledPlugins` entry into the user's `settings.json`
   (779613–779620).
5. The user's tier keys count only where no managed settings, organization seat or hosted session
   places mods: `E5` reads the user's `prependPlugins` only when `Vee()` — any non-empty
   `/etc/claude-code/managed-settings.json` — is false; on a managed machine the policy's
   `prependPlugins` is read instead. On a managed machine with no policy `prependPlugins`, the
   built-in `cc-plugin-sec-default@builtin` is seated outermost (since 2.1.287) and every hook of a
   person-installed plugin on `prompt.*`, `session.compact`, `settings.read`, `classic.*` and
   `session.append`'s attachment, hook-context and compaction doors settles in sec-default alone (the
   validate note `Mir` names the list); a policy `prependPlugins` that does not list sec-default
   leaves it unseated, and then every such hook runs, for listed and unlisted plugins alike (`Mir`
   is a note, not a second gate — observed in a container, §8). The tier a policy list gives goes
   today only to a plugin read in place from a local-folder marketplace; a policy-enabled plugin
   installed from a remote source lands in tier `user` ("gains the tier in a later release", the
   engine's own words).
6. The process's first start raises one nested `session.start` chain through every module (`Ko`,
   381344–381356); a module loaded later gets a `session.start` of its own, filtered to that plugin
   (`Vo` 381331–381341, `yse({ only })`, `_vs(…, { only })` 795273). So at a reload, the reloaded
   module's `next` on `session.start` contains no other plugin's hook, and nothing it observes
   there tells it where it stands. The order is recomputed at a reload as at a start, and every
   ordinary dispatch after it — `tool.call`, `session.append` — runs through every module in that
   order, each hook's `next.trace` naming the links beneath it.

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
Macs on 2026-10-19 (M0), ahead of every milestone, so the roll lands sminos placed. **Placement is
what holds the invariant**; the runtime probe below, if M3a promotes it, is the backstop that turns
a misplaced machine into a loud refusal, and without it the rehearsal (§10) and M0's precondition are
the whole proof.

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
host the user's key is shadowed by any managed settings (rule 5); §8 is the hosts' state.

**What placement alone does not cover.** Two paths carry a call's input past the bridge's own
`tool.call` hook whatever the order: the engine's permission check runs after every `tool.call` hook
has rewritten the input, so `tool.check`'s `e.input` and `classic.PermissionRequest`'s `tool_input`
hold the restored bytes, and the bridge raises them to the desk (`bridge.tsx`: `state.checks.push({…
input: e.input })`, `capped(e.tool_input)`, `rawInput`). **P0**, a separate change in flight before
M1, has the bridge raise a request's input in the handle form it captured in its own `tool.call`,
keyed by `tool_use_id`, with the pending-request digest kept consistent (the desk's answer names the
digest of what was raised). That capture is the handle form only when the bridge is outside the
guard, so the invariant is the two together: placement, and the bridge raising only what it captured.

**The bridge's probe of its own place — a spike (M3a), from `next.trace`.** A hook sees, after its
`next()` settles, every link beneath it with the link's `plugin`, `tier` and `index` (Terms). So the
bridge can decide where it stands from the first settled dispatch of an event both it and a guard
hook — `tool.call` (every call) or `session.append` (every row): the links beneath name `devcloud`
or `cua` or neither. The rule: a guard is **loaded** when devcloud's marker is **live** —
`$.state.get({ plugin: 'devcloud', key: 'secrets-guard' })` answers `{ owner: 'devcloud', version: 1 }`
at state version 0, which only devcloud's loaded module gives, through its own `state.get` hook
(devcloud 0.5.0, #101); `undefined`, or a stored value at version 1 or more that devcloud 0.4.x or
older left behind, is no live marker (devcloud's guard), or, with no live marker, when `cua@cua` is
among the enabled plugins (cua's copy acts then; read from the user settings through
`$.settings.read`, as appeal reads them); the bridge is **safe** when
every loaded guard has an entry beneath it, **off** when a loaded guard has none (it is outside the
bridge). Until the first verdict the bridge's post queue holds a barrier at its first `tool` event:
nothing past it is posted (a payload stripped and posted later would need a second event, a change to
DX5), and no permission request is raised except a question or an async ask (the others go to the
terminal unraised); a `safe` verdict posts the waiting events whole and in order, an `off` verdict
drops them, says why — a toast
and a debug line, `sminos: the bridge is off — sminos must load outside devcloud and cua; set
prependPlugins in ~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers",
"doperpowers@doperpowers"]` — and ends the child, so the session is unreachable from the desk while
the verdict stands. The rule is evaluated on **every** settled `tool.call` and `session.append`, not
once per instance (M3a: `/reload-plugins` re-instantiates only the modules that changed, so a guard
enabled mid-session can load outside a bridge instance that lives on). **`off` is recoverable**
(Decision Log, M3.2 review): while off nothing is posted, what waits is dropped, the barrier is
re-armed and no permission input is raised, and a `/clear`'s restart refuses; the bridge comes back
only through a dispatch that began after the transition to off and reads `safe` on positive
evidence — a guard the reads report as loaded has its link beneath, or the trace names both
`devcloud` and `cua`; "no guard loaded" never turns an off bridge back on, and a dispatch that began
before the last transition changes nothing (Decision Log, M3.2 re-review) — by the same path as
a reload (a new child and a new hello nonce, so the old instance is refused); each transition, off and
back on, is toasted once and logged. A bridge inside a loaded guard reads `off` on every dispatch,
since the guard is never beneath it, so it does not flap. The hold-and-release applies to the first
verdict, and to each return from off; otherwise each event posts under the verdict standing at that
moment. No kept state, nothing to carry across a
reload, nothing that a reload's filtered `session.start` could mislead (rule 6), and it covers cua's
guard, which writes no marker. **The residual window, accepted:** a guard newly loaded outside a
living bridge instance, followed by a tool call whose `call` phase (its `input`, posted before the
bridge's own `next`) comes before any row is appended; a reload appends command rows, typed (M3a)
or run by the reload mod's `$.command.run` (M3.3), after the new modules are in, which close it. Its bound: it needs an unplaced machine (no `prependPlugins`) that
enables a guard mid-session — on a placed machine a guard loaded mid-session lands in tier `user`,
inside the bridge — and M4 places every machine. Holding every call's input until its own `next`
settles would close it at the cost of the desk's live input streaming for every long-running call;
declined. What the
spike settles, nobody having used `next.trace` in a mod yet: that a hooks module's `next.trace` lists
the other plugins' links beneath it on `tool.call` and `session.append` with their `plugin` names as
documented; that it does so for the first dispatch after a reload; what the engine's own entry looks
like at the bottom; and whether `session.append` or `tool.call` comes first in a session so the
verdict lands before the first payload matters. Promote: the rule above, in `bridge.tsx`, with
`bridge.test.ts` cases for each row of the table below. Discard: no runtime probe at all — the
invariant rests on M0's precondition (the `prependPlugins` line on every machine before the roll),
the rehearsal's debug-log order (A1) and A7's per-machine check; the `off` line and the payload hold
do not exist, and A5 reads as its last sentence says.

| Loaded guards (marker; cua enabled) | Links beneath the bridge name | Verdict |
|---|---|---|
| devcloud (live marker: the version-0 answer) | `devcloud` | safe |
| devcloud (live marker: the version-0 answer) | no `devcloud` | off |
| cua's copy (no live marker — absent, or stored at version ≥ 1 — and `cua@cua` enabled) | `cua` | safe |
| cua's copy (no live marker — absent, or stored at version ≥ 1 — and `cua@cua` enabled) | no `cua` | off |
| none (no live marker, cua not enabled) | anything | safe |

`bridge.test.ts` pins the stale case too: a stored marker at version 1 with no `devcloud` beneath and
cua not enabled is `safe`, and with cua enabled reads as cua's row.

The design the second draft carried — devcloud's marker *version* moving during the bridge's
`session.start` `next`, a verdict kept under a sminos key across reloads — is not the plan: at a
reload the bridge's `session.start` `next` holds no other plugin's hook (rule 6), so every live
session's new sminos module at the roll would read the marker as present-first and switch itself
off on a machine the owner had already placed; and with no `prependPlugins` the version can move
between the two reads by a race across workers, reading `outside` while the bridge sits inside the
guard — the unsafe direction. Recorded in Surprises & Discoveries.

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
moves (the next minor above main's at the time) in M3 with the dependency — which is what makes
the roll install sminos on a machine that never ran `/plugin install sminos@doperpowers` (§10, "The
roll").

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

**M0 — before the roll (the Macs):**

1. `prependPlugins`: `["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]` (§4).
   Safe ahead of the plugin's existence: a name that is not an enabled plugin with a hooks module is
   skipped (§4, rule 1). **Done** on both Macs on 2026-10-19; probe sessions confirm the prepend tier.
2. `enabledPlugins`: add `"sminos@doperpowers": true`. **A precondition of the roll, not optional**,
   and an owner step that still needs their explicit OK (they approved step 1 alone): the engine's
   own `claude plugin install` writes a plugin's `enabledPlugins` entry into the user's
   `settings.json` (§4, rule 4), so the roll — the reload mod installing sminos as to-human's new
   dependency (§10) — would otherwise write the owner's file on its own, on every Mac, unasked.
   Written by the owner first, the entry is theirs, it installs and loads nothing by itself (the
   engine lists it in `/plugin` as not installed), and the roll's install only confirms it. M3's
   rehearsal confirms both halves (§10).

**M4 — at the roll, per machine:**

0. Precondition, checked rather than assumed: the roll moves devcloud to 0.6.0 and sminos to 1.0.0
   together (the author's roll script updates doperpowers, to-human, devcloud and sminos in one
   pass), so no machine runs sminos 1.0.0 beside a devcloud 0.4.x or older, whose stored marker the
   probe reads as no live marker (§4) — `safe` even inside that guard when cua is not enabled. Check
   `installed_plugins.json` on the machine after the roll: `devcloud@doperpowers` at 0.6.0 or later
   wherever `sminos@doperpowers` is at 1.0.0.

3. `~/.claude/agents/astra.md` and `sol-xhigh.md`: `disallowedTools` names `mcp__sminos__AskUserQuestion`
   (and keeps `mcp__doperpowers__compact`).
4. Let the reload mod roll the machine, or run `/plugin marketplace update doperpowers`, then
   `/plugin install sminos@doperpowers` (before any reload: a reload after the marketplace update
   loads the new doperpowers, without the ask, at once — Surprises, M1), then `/reload-plugins` in a
   session; a session that must keep its open asks across the swap keeps them
   (§5). The rehearsal's roll applied without `--force` (the ask's `$.tool.register` server is not
   counted as an added plugin MCP server; M3.3); if a machine's reload answers that it needs
   `--force` all the same, run `/reload-plugins --force` when the session is idle. The first
   interactive session opened after the merge may roll itself before the reload mod acts (Surprises,
   M3.3); that converges.
5. `sminos daemon install`, then reload the service: on macOS `launchctl bootout gui/$(id -u)/com.doperpowers.sminos-daemon`
   then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`;
   on Linux `systemctl --user daemon-reload && systemctl --user restart sminos-daemon.service`. Until
   this step the daemon runs through the shim (§7).
6. Verify A1 and A7 on the machine. The shim's forward line goes to the daemon's stderr,
   `$SMINOS_HOME/daemon.out`, not `daemon.log`. On macOS a `launchctl bootstrap` right after the
   `bootout` can fail with error 5 ("Try re-running the command as root"); a retry a few seconds
   later loads the agent, and the cold start takes about half a minute to the uplink (the MacBook,
   2026-10-20).

**devcloud hosts — the devcloud setup session's, and a precondition for enrolling one at the desk.**
A host receives the owner's `~/.claude` as a receive-only clone (reset to its remote every 30 minutes,
reconciled on a new commit; design §5), so `settings.json` with M0's lines reaches every host by
itself; what decides whether it counts there is `/etc/claude-code/managed-settings.json`, which boot
step 10 writes from the profile (seven keys today: the gateway's base URL and switches, blanks for
the Mac-only `CLAUDE_CODE_PLUGIN_DIRS` and the extension token). The devcloud setup session, which
owns boot, settled the hosts' state in a Linux container on 2026-10-19 (2.1.303, Ubuntu 24.04):

- With today's env-only managed file, `cc-plugin-sec-default@builtin` is seated outermost, and
  `classic.PermissionRequest`, `classic.SessionStart`, devcloud's `prompt.*` and `session.compact`
  settle in sec-default alone: a stand-in token went raw to the gateway. True since 2.1.287; no host
  is running today.
- `Mir` is not a second gate: with sec-default unseated, every passed-over hook ran, for listed and
  unlisted plugins alike.
- With the candidate lists (`prependPlugins` and `enabledPlugins` copied from the synced
  `settings.json` into the managed file), sec-default is unseated — but a policy-enabled plugin
  installed from the cache lands in tier `user` (rule 5), so the bridge stays inside the guard. The
  Mac layout is reproduced only by managed `extraKnownMarketplaces` declaring doperpowers as a local
  directory (a root-owned clone) with no GitHub record; a leftover GitHub record loses every
  doperpowers-marketplace plugin until a reconcile.
- **The decision**: boot now always writes a managed `prependPlugins` that seats no sec-default
  (`[]` first; the copied lists as the fallback), which stops the raw-token path; the
  directory-marketplace route is deferred until a host must enroll, or until the engine gives
  cache-installed policy plugins the tier. **Enrolling a devcloud host at the desk stays blocked on
  it** (`sminos hub enroll` on a host is refused by the operator's checklist, not by code).

Two routes lost on the way. The host's process environment, set by boot for every launcher: settings
`env` overwrites the process environment tier by tier (`applySafeConfigEnvironmentVariables`,
verified on 2.1.303; the same reading as `jp` at cli.pretty.js 481468), and the synced file sets
`ANTHROPIC_BASE_URL` to the Mac's loopback relay `127.0.0.1:8641`, which nothing serves on a host.
An overlay rewriting the received `settings.json` after each pull (this spec's second draft): the
clone is reset every 30 minutes with an invalid push URL and re-applied on a new commit, so a rewrite
is undone at every reset, running sessions hot-reload the Mac's values in between, and the clone is
left dirty — the file is the Mac's, and only the managed tier is the host's to write.

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
  text; `sminos.py`'s `ASK_TOOLS` / `PLUGIN_PROMPTS` sets (§3, dual since M1). Its `.smns`, registry and log layout do not
  change.
- **The live checks** stage a plugin folder from `REPO` two levels above themselves and launch it
  with `--plugin-dir` (`live-bridge-check.py` `REPO`, `PLUGIN_PARTS`, `sminos()`; `live-resume-check.py`
  and `live-stop-check.py` `SCRIPTS`): after the move `REPO` is the sminos plugin root and
  `PLUGIN_PARTS` names its parts (`.claude-plugin`, `hooks`, `skills`, `types`). A `--plugin-dir`
  load registers as `<name>@inline`, which `prependPlugins` never matches; the live checks stage one
  plugin, so nothing orders them, and the rehearsal (§10) uses a marketplace for that reason.

### 10. Versioning, marketplace, gates, the roll, documents

- **Versions, one commit (M3).** `.version-bump.json` gains a `sminos` plugin: files
  `sminos/.claude-plugin/plugin.json` (`version`) and `.claude-plugin/marketplace.json`
  (`plugins[name=sminos].version`), audit root `sminos`; doperpowers' audit `exclude` gains `sminos`.
  `scripts/bump-version.sh --plugin sminos` then works. Starting version **1.0.0**: the component is
  mature and its protocol (DX5) is pinned by MAWS; a 0.x would misstate it (devcloud and to-human
  started at 0.1.0 as new work). doperpowers, to-human and devcloud each move to the next minor
  above `main`'s at the time (main moves under this spec: 7.189.0, 0.1.1 and 0.4.2 at this writing),
  each by the script, in the same M3 commit as the change: the marketplace updates by version number
  alone. M1's bumps are the next patch above `main`'s at the time.
- **The marketplace entry.** `.claude-plugin/marketplace.json` adds `sminos`, source `./sminos`, the
  description of what it is (the orchestration interface: the machine side of the MAWS desk, and how
  sessions and humans reach each other). `tests/codex/test-marketplace-manifest.sh`'s
  `expected_sources` gains `"sminos": "./sminos"`.
- **The roll** (§Terms) is unattended, so the M3 release must survive it with no owner present. The
  reload mod's update path runs `claude plugin marketplace update doperpowers` and then `claude
  plugin update <key> --scope user` for each enabled plugin installed from it — only installed ones,
  and only when the clone's head moved (`fetchOne` returns early once the local head equals the
  remote's). Left as it is, a machine's roll would update doperpowers (the ask and the bridge gone),
  update to-human (depending on a sminos that is not installed, so unloaded), and reload; whether
  `plugin update` installs a plugin's new dependency closure as `plugin install` does is what the
  rehearsal must show, and the mod must not rely on it. **M1 changes the reload mod**: its step runs
  whenever an enabled plugin's installed version differs from its manifest in the clone (not only
  when the head moved — a fetch that found the head in place but a plugin behind still acts, so a
  refused batch is retried); before updating, it reads each enabled plugin's manifest in the clone,
  installs every dependency not yet installed (`claude plugin install <dep>@<marketplace> --scope
  user`) and, with a debug line, holds back every plugin whose dependency chain reaches one that cannot
  be installed (Decision Log, M1 review); it updates the rest of the batch; then it reloads once. The
  reloader in every session holds a due reload on the same rule, so a reload never loads a plugin
  over a missing dependency whoever applied the update. The engine's own session-start pass resolving missing dependencies
  (§4, rule 4) is the same intent at a different moment. M1 ships this because M1's code is what runs
  on the machines during the roll. With M0 in place, sminos lands placed and already enabled by the
  owner's hand.
- **The rehearsal** (M3's proof of the roll), in a temporary HOME: a clone of this repository at
  the M1 commit served as a git remote over loopback (`git daemon` or `git http-backend` behind
  `http://127.0.0.1:<port>/doperpowers.git`), added with `claude plugin marketplace add <that url>`
  so `known_marketplaces.json` records a `git` source named `doperpowers` with `autoUpdate` true —
  not `marketplace add <path>`, which records `source: "directory"` (817032), which `reload.tsx`'s
  `autoUpdating` (only `github` or `git`) never fetches; the name must be `doperpowers`, because
  `prependPlugins` names `<plugin>@doperpowers` and a `--plugin-dir` load registers as `@inline`.
  The settings of §8 applied there (both M0 steps), doperpowers, to-human and devcloud installed at
  M1, the gateway keys for a model call, one interactive session with an async ask open; then the
  served clone is moved to the M3 commit, the reload mod's fetch is forced (remove
  `<config>/autoreload/fetch.stamp` and wait past `ROLLING_MS`), and after the reload: the ask is
  still open behind `[ answer ]` and answers, `$SMINOS_HOME/bridge/<session>.sock` is served,
  to-human folds the transcript, `sminos chat --host` lists the question, `installed_plugins.json`
  holds `sminos@doperpowers`, and the debug log shows the order of A1. Recorded with the result:
  whether the reload applied or answered that it needs `--force` — a new plugin's `$.tool.register`
  server may count as an added MCP server (`L8`, 940925–940940), in which case the mod's own
  "/reload-plugins --force applies it" line is the expected answer and M4's step 4 says so. The
  rehearsal spends model calls; it runs inside `/tmp/maws-review/with-slot.sh`.
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
  in this spec's Decision Log record the path change they describe and the hosts' managed
  `prependPlugins` (the devcloud session's change, documented there when it lands). Old specs
  (`2026-10-13-ask-async-design.md` and the rest) are history and keep the old name.

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
  readers of names only here. P0 changes what the bridge raises, not the protocol's shape; the
  probe's payload hold (§4) withholds fields an event already has, adding none.
- A marker of cua's own for its vendored guard: no longer needed by the `next.trace` probe; not
  pursued.
- The devcloud hosts' placement (boot step 10's managed `prependPlugins`, §8, I8): the devcloud
  setup session's change, on its own schedule; this spec relies on its result and names it as a
  precondition for enrolling a host.
- Re-cutting the old specs under the new name.
- The `qa-loop`, the board's dispatch, and the worker protocols' behaviour, which stay dormant and
  unarmed; this work changes only how their scripts find the CLI.

## Execution

### Constraints that bind every milestone

- M1 is based on `origin/main` at or after 0176e090 (#273, #274). #269 (`smns-guide-fork`) and
  #271 (`smns-guide-roster`), open at this writing, change `cmd_guide` and `smns-guide.sh`; M3's move
  takes whatever of them has merged and rebases on the rest.
- P0 — the bridge raising a request's input in the handle form it captured — lands on `main` before
  M1; M1's base carries it.
- M0's two steps are preconditions of the roll (§8): no machine rolls (M4) before both are on it.
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
  change (CLAUDE.md, working conventions), to the next patch (M1) or minor (M3) above `main`'s at
  the time. Commit messages carry no attribution trailer other than the `Sminos-Session:` line the
  engine adds.
- Each plugin's module respects the engine's limits as the code does today: one unmatched
  registration of an event per module; `$` passed only to functions in the module's own file; the
  state reference's `plugin` and `key` as literals.
- The engine is 2.1.303 on this machine; a milestone that finds the engine's behaviour differs from
  §4, §5 or §10 records it in Surprises & Discoveries and returns to the spec's author before building
  on it.
- MAWS is read at `/Users/new/Developer/GitHub/MAWS` (the checkout is on `sminos-hub`; read
  `origin/master` with `git show` / `git grep`); M2 alone writes there, from its own worktree.

### Plan of Work

M0 (owner; its first step done, its second awaiting their OK), then five milestones, ordered so no
live session breaks: readers first in both repositories with the reload mod made safe for the roll,
then the carve-out with the rename in one release — opened by the `next.trace` spike (M3a), whose
verdict decides whether the bridge carries a runtime probe — rehearsed on a served git remote, then
the roll with each machine's steps, then cleanup. M1 and M2 are independent of each other and may run
side by side; M3a may run beside them (it reads the engine, changes nothing that ships); M3 waits for
all three; M4 waits for M3's release, M2's deployment and M0 complete; M5 waits for every machine of
M4.

### M1 — doperpowers' readers accept both names; the reload mod rolls a machine whole

**What exists at its end.** A doperpowers release (the next patch above main's) whose ask, to-human
and sminos record export read a transcript carrying either tool name and either framing, whose
appeal judge already does, and whose reload mod installs a plugin's new dependencies before it
reloads a machine and acts whenever an installed version is behind the clone's. A session on it,
resumed later from a transcript written by sminos 1.0.0, sees its asks; a machine on it rolls to M3
without a reload that lacks sminos.

**What it touches.** `hooks/mods/ask.tsx` (`ASK_TOOLS` and `PLUGIN_PROMPTS` beside `ASK_TOOL` and
`PLUGIN_PROMPT`; `asksIn`, `deliveryTexts`, `historyAsks`' `prompt()`, `STORED_FORMS`, `searchArgs` /
`grepArgs`'s literals); `to-human/hooks/mods/to-human.tsx` (`ASK_TOOL`, `ASK_DELIVERY`);
`skills/sminos/scripts/sminos.py` (`ASK_TOOL` at 3306, read at 3452 and 3807; `PLUGIN_PROMPT` at
3312, read at 3367 in `_delivery_texts`); `hooks/mods/reload.tsx` (the update path of §10);
their tests (`tests/mods/ask.test.ts`, `tests/mods/test-ask-search.sh`, `tests/mods/reload.test.ts`,
`to-human/tests/mods/to-human.test.ts`, `tests/sminos/run-sminos-tests.sh` around `ASK =`,
`tests/sminos/test-bridge-export.sh` 137 and 153). Versions: doperpowers and to-human.

**Decisions.** The registered name stays `mcp__doperpowers__AskUserQuestion` here: `ASK_TOOL`'s
value, `PLUGIN`, the `tool.describe` / `tool.call` matchers and `WITHDRAWN` do not change in M1. The
new name and framing are spelled once each, as the first member of each set, so M3 changes
`ASK_TOOL` to `ASK_TOOLS[0]` and `PLUGIN` to the plugin's real name (§3), and nothing else of the
names (`PLUGIN_PROMPT` is gone, Decision Log, M1). The search's `STORED_FORMS` gets one literal
per name and per framing so a transcript over 4 MiB is still found by `grep -F` (a5bc8c15). The
record export's Python mirrors the TypeScript sets. The reload mod's step is triggered by a version
difference between `installed_plugins.json` and the clone's manifests (the marketplace's `source`
paths in the clone's `.claude-plugin/marketplace.json`), installs with the engine's CLI as it updates
with it, and treats a refusal as holding back the plugins whose dependency chain reaches it, logged,
acted on again at the next fetch because the difference remains (Decision Log, M1 review).

**What it does not touch.** No file moves; no manifest, gate or document changes beyond the
version bump.

**What it proves.** A3's reader half: tests pin a transcript whose call carries the old name and
whose delivery carries the new framing, and the reverse, each rebuilt as one open or answered ask by
`asksIn`, and the same pair rebuilt by `historyAsks` from a fake `$.session.messages()`; to-human's
`promptRow` reads both framings as the person's answer; `sminos record` exports a `question` and
`answered` from each. The reload mod: a fake clone whose to-human manifest names a dependency not
installed makes the mod install it before `plugin update`; a failing install holds back the plugins
whose chain reaches it, and the next fetch, the head unchanged but the version still behind, tries
again; a reload is held while what it would load lacks a dependency; a clone whose head is
unchanged and whose versions match applies nothing. `tests/mods/run-mods-tests.sh`,
`to-human/tests/mods/run.sh`, `tests/sminos/run-sminos-tests.sh` green; `ci-gate` GREEN.

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

### M3a — Spike: the bridge's place from `next.trace`

**The question.** Does a hooks module's `next.trace` tell the bridge which plugins sit beneath it,
reliably enough to carry the verdict of §4's table — on `tool.call` and on `session.append`, at the
process's first start and on the first dispatch after a reload — and which of the two events a
session dispatches first?

**What to build and run.** A throwaway mod (not shipped) in a temporary plugin folder loaded beside
`devcloud` and `cua` in a temporary HOME, placed outside them by `prependPlugins` in one run and
inside them in another (a served marketplace as the rehearsal uses, §10, or a `--plugin-dir` load
with a dependency-free order, whichever reaches both placements); it hooks `tool.call` and
`session.append` and logs, after `next`, `next.trace.map(({ plugin, tier, index, outcome }) => …)` to
the debug log, then reloads itself (`claude plugin update` on the served marketplace, or a save under
`--plugin-dir`'s hot reload) and logs the same on its first dispatch as a new instance. Run inside
`/tmp/maws-review/with-slot.sh`; one prompt that makes one tool call is enough per run.

**What to observe.** In each run and after each reload: the entries beneath the mod name `devcloud`
and `cua` when it is outside them and name neither when it is inside; the engine's entry closes the
list; the first dispatch after a reload reads the same; which event fires first after a prompt.

**Promote or discard.** Promote when every observation holds: M3 builds the probe of §4 as written
(the table's five rows in `bridge.test.ts` against a fake `next.trace`, the payload hold, the `off`
line), and A5 reads as its first form. Discard when any fails — the trace empty or missing plugin
names in a hooks module, a reload's first dispatch misleading, the hold's window unsafe: M3 builds no
runtime probe, the invariant rests on M0's precondition, the rehearsal's A1 and A7's per-machine
check, A5 reads as its last sentence, and the `order` of the verdict is never kept anywhere. The
verdict and its evidence go to Surprises & Discoveries, dated.

### M3 — The carve-out and the rename

**What exists at its end.** One release of four plugins: `sminos` 1.0.0 at `sminos/` with the layout
of §2, the tool `mcp__sminos__AskUserQuestion`, `PLUGIN` as the plugin's real name (§3), the channel
of §5, the bridge's probe of §4 if M3a promoted it, the shim of §7; `doperpowers` (the next minor)
without sminos, reading the asks through the channel, with the board resolver of §9; `to-human` (the
next minor) depending on sminos; `devcloud` (the next minor) with step 11 looking for the CLI at the
new path (the hosts' placement, step 10, is the devcloud session's own change, §8, and lands on its
own schedule). Every gate green in the new layout; the rehearsal of §10 passed; the documents of §10
say what is.

**What it touches.** The moves of §1 (`git mv`, so history follows); `sminos/.claude-plugin/plugin.json`,
`sminos/hooks/hooks.json`, `sminos/hooks/mods/register.tsx`, `sminos/types/sminos.d.ts`,
`sminos/README.md`, `sminos/tests/mods/run.sh`; `hooks/hooks.json` and `hooks/mods/register.tsx`
(doperpowers' remaining mods and shell hooks); `hooks/mods/appeal.tsx`, `reload.tsx`, `compact.tsx`
(§5; appeal's fake-guard case, §4); `ask.tsx` (the values of `ASK_TOOL` and
`PLUGIN`, `KEPT`, the shape-1 fallback, `isDialogUp` and `answered` in the snapshot); `bridge.tsx`
(the probe, if promoted); `agents/*.md` (nine), `output-styles/to-human.md`;
`skills/issue-tracker/scripts/_lib.sh`, `execute-dispatch.sh`, `board-sweep.sh`,
`review-dispatch.sh`, `_sweep_api.sh`, `board-gc.sh`, the three worker-protocol references and the
issue-tracker and board-api tests of §9; `skills/sminos/scripts/sminos_daemon.py` (`installed_cli`),
the two service templates, `skills/sminos/scripts/sminos.py` (the shim, in doperpowers, new) and the
`sminos` launcher beside it; `devcloud/boot/devcloudlib/sminos_host.py`,
`devcloud/tests/unit/test_sminos_host.py`, `devcloud/tests/integration.py`;
`.claude-plugin/marketplace.json`, `.version-bump.json`, `to-human/.claude-plugin/plugin.json`,
`.github/ci-kit.yml`, `tests/codex/test-marketplace-manifest.sh`, `tests/claude-code/run-skill-tests.sh`;
`sminos/tests/run-sminos-tests.sh` and every moved test file (the `PLUGIN_ROOT` name of §2, the cache
fixture and the shim's pin of §7, the hook paths, the live checks' staging of §9, the fixtures that
import `PLUGIN`); `CLAUDE.md`, `README.md`, `hooks/mods/README.md` → `sminos/hooks/mods/README.md`,
`sminos/skills/sminos/SKILL.md`, `references/setup.md`.

**Decisions.** One milestone, one release: the rename, the move, the manifests and the gates must land
in the same cutover (a half state — a tool registered under one name by two plugins, or a gate
pointing at a path that moved — is invalid). `PLUGIN` is read from `$.plugin.name` at the ask's
`session.start` and handed to the bridge's modules through `bridge-state` (or set as the literal
`sminos` — the executor's call, with the manifest-equality test as the judge); the fixtures import
it. The sminos tests' root variable is `PLUGIN_ROOT`, the plugin root. The doperpowers types file
keeps the `types` key only while it declares a value (it declares none after the move; drop the key
or keep an empty contract — the executor's call, with `claude plugin validate` as the judge). The
appeal's read of `{ plugin: 'sminos', key: 'ask' }` types through `import type` from
`../../sminos/types/sminos` (erased at run time; `devcloud/types/devcloud.d.ts` shows the read form);
if `claude plugin validate` on doperpowers refuses a read of a contract that is not enabled in the
staged test plugin, the validate output is the authority and the doperpowers types contract declares
the key it reads. The probe, if promoted, reads devcloud's key and the user settings' `enabledPlugins`
with the forms appeal uses. The shim is Python 3.9-safe (it may run under macOS's own `python3`
before the real CLI's version check). The board resolver reads `known_marketplaces.json` with
`python3 -c` or `jq`, whichever `_lib.sh` already uses. The `sminos/README.md` is short: what the
plugin is, the install lines with `prependPlugins`, pointers.

**What it does not touch.** `~/.claude/*` on any machine; MAWS; the old specs; the dormant board
doctrine's behaviour; DX5; devcloud's boot step 10.

**What it proves.** A1 (the module loads with the events listed; the order of the `loaded` lines, in
the rehearsal's HOME), A2's blocking-dialog clause (a blocking ask's dialog carries every question),
A5 (in its promoted or discarded form, in the rehearsal's HOME, (c) and (d) through `claude plugin
update` then `/reload-plugins`), A6 (`tests/mods/appeal.test.ts` with the channel and the fake guard,
`tests/mods/reload.test.ts` with a fake `$.state` seeded at start), A8 (every gate; both validates;
the rehearsal, its reload answer recorded). Tests pin: the ask tool registers under the new name;
`PLUGIN` equals the manifest's name, the ask's own raise is claimed and widened, `isDialog` and
`enteredRow` match under it; the snapshot carries `isDialogUp` and `answered`, and a shape-1 value
under doperpowers' key is taken up once; the bridge names a compact-tool compaction's rows through
its `session.compact` hook; the probe's table row by row against a fake `next.trace`, the payload
hold and its release, if promoted; `installed_cli` returns the new clone path and its refusal names
it; the shim forwards to the sibling, else the installed plugin, else exits 1 naming `daemon
install`, and writes its line to stderr; the suite fails on that line; `sminos_host.py` finds the new
path, then the old; the resolver finds the CLI in each of its three places and `lib.sh` beside it.
The issue-tracker and board-api gates run the board scripts against the checkout's CLI through
`SMINOS_CLI`.

### M4 — The roll and each machine's migration

**What exists at its end.** Every machine runs sminos 1.0.0 placed as §4 says, with its daemon
installed at the new path, and the owner's agents name the new tool. The desk shows all machines.

**What it touches.** Nothing in the repository but this spec's Progress and record. The owner's
files and services of §8, by the owner or on their explicit approval, one machine at a time.

**Decisions.** M0 complete and M2 deployed before the first machine rolls. The steps of §8 (M4's)
in that order on each machine; A1 and A7 checked on each; a session with an open async ask at the
swap is the test of §5's fallback (ask on one session before the reload, answer after); the reload's
answer (applied, or `--force` needed) noted per machine. The executor of this milestone is the
session the owner works with: it prepares each step's exact command and waits for the owner's word
per machine.

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

# The rehearsal (M3) — §10: a clone at M1 served over loopback as a git remote
git clone --bare <this repository at the M1 commit> $H/served/doperpowers.git
git -C $H/served/doperpowers.git update-server-info     # then: python3 -m http.server <port> --directory $H/served  (or git daemon)
HOME=$H claude plugin marketplace add http://127.0.0.1:<port>/doperpowers.git     # known_marketplaces.json: source git, name doperpowers; set autoUpdate true
# ... install doperpowers, to-human, devcloud at user scope; apply §8's settings in $H; open a session, ask async ...
# move the served clone to the M3 commit; then force the fetch:
rm $H/.claude/autoreload/fetch.stamp           # (the mod's <config>/autoreload/fetch.stamp)
# wait past ROLLING_MS (60 s); the mod updates and reloads, or answers that --force is needed — record which
# expect after the reload: the ask still open and answerable; $SMINOS_HOME/bridge/<session>.sock served;
#   to-human folding; `sminos chat --host` listing the question; installed_plugins.json holding sminos@doperpowers;
#   the debug log's order as in A1

# A5 — the probe, in the rehearsal's HOME with devcloud and sminos enabled (promoted form)
#   (a) no prependPlugins: after the first tool call, a debug line opening "sminos: the bridge is off" (a toast in an interactive session);
#       the tool events before it carried no input/text; no $SMINOS_HOME/bridge/<session>.sock afterwards
#   (b) prependPlugins set: the first tool call's events carry their payloads once the verdict is in; no line
#   (c) bump sminos's version in the served clone; HOME=$H claude plugin update sminos@doperpowers; /reload-plugins: (b) again from the new instance's first call
#   (d) bump devcloud's and sminos's; update both; /reload-plugins: (b) again
#   (e) as (a); update both; /reload-plugins: still off
#   (discarded form: the debug log shows A1's order and no verdict line exists)

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
at version 0 where sminos is not loaded. sminos keeps no other state value: the bridge's verdict,
if M3a promotes it, lives in the module instance alone.

**I2 — The probe's inputs** (§4, if promoted): `next.trace` after the bridge's `next()` on
`tool.call` or `session.append` — `readonly TraceEntry[]`, each `{ index, plugin, tier, event,
outcome, … }`, nearest link first, the engine's entry last (`.claude/types/claude-code.d.ts`
6732–6740, 13881); devcloud's marker `{ plugin: 'devcloud', key: 'secrets-guard' }` →
`{ value: { owner: 'devcloud'; version: 1 } | undefined, version }` (its `types/devcloud.d.ts`),
which devcloud's loaded module answers at version 0 and never stores: only the version-0 answer
means devcloud's guard is loaded now, and a stored value at version 1 or more is one an older
devcloud left, which can outlive its module (board #101); and the user settings'
`enabledPlugins["cua@cua"]` through `$.settings.read({ source: 'user' })`.

**I3 — The names.** In each reader, beside the registered name:
`ASK_TOOLS = ['mcp__sminos__AskUserQuestion', 'mcp__doperpowers__AskUserQuestion']` and
`PLUGIN_PROMPTS = ['The sminos plugin sent a message:\n', 'The doperpowers plugin sent a message:\n']`
(ask.tsx, to-human.tsx, sminos.py, and the equivalents in MAWS's readers of §11, which also hold the
plugin-name set `['sminos', 'doperpowers']`) — no shared module crosses plugins or repositories.
`ASK_TOOL` and `PLUGIN` stay the one registered name and this plugin's own name, in `ask.tsx` alone:
in M1 their values are the old ones; from M3, `ASK_TOOLS[0]` and `$.plugin.name` (asserted equal to
the manifest's `name`). No reader keeps a single framing constant: the engine writes the framing, so
from M1 every reader holds only the set (`PLUGIN_PROMPT` in `ask.tsx`, `ASK_TOOL` and `PLUGIN_PROMPT`
in `sminos.py`, `ASK_TOOL` in `to-human.tsx` were replaced by the sets).

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
profile's `env` and a managed `prependPlugins` that seats no sec-default — `[]` today; the lists
copied from the synced `~/.claude/settings.json` as the fallback — written by boot step 10 and
`devcloud reconcile` after every pull. The placement that puts the three plugins in the prepend tier
on a host waits on the directory-marketplace route or on the engine giving cache-installed policy
plugins the tier; until then no host enrolls.

**Dependencies.** The engine at 2.1.303 (hooks modules, `$.state` with `state.set`, `next.trace`,
`prependPlugins`); bun and `claude plugin test` for the mods' tests; P0 on `main`; M0 on each
machine; MAWS `origin/master` at or after M2's merge, deployed, for A2's desk half and the roll.

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
  hookable event, so a plugin can observe another's writes.
  Evidence: `.claude/types/claude-code.d.ts` 3460 ("held by the host for the session … survives a hot
  reload … Any plugin reads any value; its owner alone writes it. Persist through `$.store`"), 12648
  (`on("state.set", DRIVE, …)`); `cua`'s `one-guard.tsx` reads devcloud's marker.
- Observation: a reloaded module cannot learn its place from `session.start`: only the process's
  first start raises one nested chain through every module; a module loaded later gets a raise of
  its own, filtered to its plugin. So the first draft's probe (the marker's presence at
  `session.start`) would have switched the bridge off at every `/reload-plugins`, and the second
  draft's (the marker's version moving during `next`, a verdict kept across reloads) would have
  read every live session's new module at the roll as `present-first` and switched it off on a
  machine already placed, while with no `prependPlugins` a version moving between the two reads by a
  race across workers could read `outside` from inside the guard. The third design reads
  `next.trace` on an ordinary dispatch instead (§4, M3a).
  Evidence: `cli.pretty.js` 381344–381356 (`Ko`, the one nested `session.start` at first start),
  381331–381341 (`Vo`, `yse({ only: s.name })`), 795273 (`_vs(…, { only })`); `ask.tsx`'s own
  `session.start` ("A module loaded into a running session (a reload) takes up the asks the one
  before it kept"); the second review round, 2026-10-19. `next.trace`'s shape:
  `.claude/types/claude-code.d.ts` 6732–6740 and `TraceEntry` 13881 (`index`, `plugin`, `tier`);
  no mod uses it yet, hence the spike.
- Observation: cua 0.15.0 carries devcloud's guard as a vendored copy that acts when devcloud is
  absent and writes no marker; a marker-based probe could not see it, a trace-based one can.
  Evidence: `~/.claude/plugins/cache/cua/cua/0.15.0/hooks/mods/guard/secrets.tsx` 280–291 ("cua
  adaptation: devcloud's marker write is removed") and `one-guard.tsx` ("cua never writes it, nor any
  marker of its own"). Since #101 (doperpowers #280, devcloud 0.5.0; cua#173, cua 0.16.0; both Macs
  on them, 2026-10-19) devcloud stores no marker: its loaded module answers the read at state version
  0 through a `state.get` hook, and cua's copy counts only that version-0 answer as devcloud loaded,
  so a stored marker an older devcloud left no longer stands cua down.
- Observation: the ask's `PLUGIN` is the literal `'doperpowers'`, not `$.plugin.name`, and the
  fixtures hard-code the same string, so a move under a new plugin name would silently stop the ask's
  own raise being claimed and widened and the bridge's `isDialog` and `enteredRow` matching, with
  every suite green.
  Evidence: `hooks/mods/ask.tsx` 12 (`export const PLUGIN = 'doperpowers'`), `claim()` (~1319), the
  widening hook (~1615), `bridge.tsx` (~1409), `bridge-rows.tsx` 380; `tests/mods/ask.test.ts` 154,
  `bridge.test.ts` 177, 2123, 3171, 3219, 3407; the second review round, 2026-10-19.
- Observation: a call's input reaches the bridge's permission-request path in the restored form
  whatever the order: the engine's permission check runs after every `tool.call` hook has rewritten
  the input.
  Evidence: `bridge.tsx` `tool.check` (`input: e.input`) and `classic.PermissionRequest`
  (`capped(e.tool_input)`, `rawInput`); the adversarial review of 2026-10-19; P0 in flight.
- Observation: the roll is unattended and updates only installed plugins, and only when the clone's
  head moved, so a release that moves the ask into a plugin nobody installed would reload sessions
  without it and a refused batch would never be retried; the engine installs a plugin's dependency
  closure on install, tracks auto-installed dependencies (`claude plugin prune`), resolves missing
  dependencies in its own session-start pass, and writes a plugin's `enabledPlugins` entry into the
  user's `settings.json` on `plugin install` — which is why M0's second step is the owner's hand,
  before the roll's.
  Evidence: `reload.tsx` 293–300 and 407–414 (`claude plugin marketplace update <name>`, then
  `claude plugin update <key> --scope user` per enabled installed plugin), `fetchOne`'s early return
  on an unmoved head; `cli.pretty.js` 779586 (the closure walked at install), 410058 ("auto-installed
  dependencies no longer needed … `claude plugin prune`"), 239075 ("Dependency … is not installed"),
  ~157455 (the session-start pass), 779613–779620 (`enabledPlugins` written at install); the second
  review round, 2026-10-19.
- Observation: `claude plugin marketplace add <path>` records `source: "directory"`, which the reload
  mod never fetches; a rehearsal of the roll needs a `git` source — a clone served over loopback —
  with `autoUpdate` true, and the fetch forced by removing the mod's stamp; and a reload that adds
  a plugin MCP server may answer that it needs `--force`.
  Evidence: `cli.pretty.js` 817032 (the directory source), `reload.tsx` `autoUpdating` (`github` or
  `git` only), `FETCH_MS` / `ROLLING_MS` / the stamp, 149 ("A plugin update is not applied: this
  reload would add or remove a plugin MCP or LSP server … /reload-plugins --force applies it"),
  `L8` 940925–940940; the second review round, 2026-10-19.
- Observation: a `prependPlugins` name may be listed before its plugin exists.
  Evidence: `rSr` (744547): `names ${K}, which is not an enabled plugin with a hooks module; skipped`
  — a debug line, not a refusal; the owner's probe sessions after M0 on 2026-10-19 show to-human and
  doperpowers in the prepend tier with sminos not yet installed.
- Observation: on a managed machine the engine ignores the user's tier keys; with no policy
  `prependPlugins` the built-in sec-default is seated outermost and every hook of a person-installed
  plugin on `prompt.*`, `session.compact`, `settings.read`, `classic.*` and three `session.append`
  doors settles in it alone — a token went raw to the gateway in a container with today's env-only
  managed file (true since 2.1.287; no host running). `Mir` is not a second gate: with sec-default
  unseated by a policy `prependPlugins` that does not list it, every such hook ran, listed and
  unlisted alike. But a policy-enabled plugin installed from the cache lands in tier `user`; the
  prepend tier reaches only a plugin read in place from a local-folder marketplace ("a plugin
  delivered from a remote source gains the tier in a later release"), reproduced only by managed
  `extraKnownMarketplaces` naming doperpowers as a root-owned local directory with no GitHub record.
  Evidence: `E5` (410255), `Vee` (409728), `Mir` (949953; `passedOverNoteOf`, the note appended to
  the `hooks:` diagnostic line), `Z8r` (949946); the devcloud setup session's container run,
  2.1.303 on Ubuntu 24.04, 2026-10-19, and its decision (§8).
- Observation: a process-environment value cannot override a key the synced `settings.json` carries:
  settings `env` overwrites the process environment tier by tier; and a host-side rewrite of the
  received `settings.json` cannot stand, the clone being receive-only and reset every 30 minutes. The
  managed file stays the hosts' one place to write.
  Evidence: `applySafeConfigEnvironmentVariables`, verified on 2.1.303 by the devcloud setup session;
  the same reading in `cli.pretty.js` 481455–481468 (`KL`, `jp`) and 1037482–1037490 (`o0r`); the
  synced file's `ANTHROPIC_BASE_URL` is `127.0.0.1:8641` (the owner); the devcloud spec's §5 and
  `devcloudlib/steps.py` `home()`; the devcloud setup session's account (2026-10-19).
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
- Observation (M3a, 2026-10-19): a hooks module's `next.trace` names the plugins beneath it by their
  bare names, one entry per module, on `tool.call` and on `session.append`: outside the guards it
  names `devcloud` and `cua`, inside it names neither; the engine's `{ plugin: "engine", tier: "core",
  outcome: "returned" }` closes every list; a reloaded module's first dispatch reads the same (sminos
  updated alone, sminos and devcloud together, and the inside case — A5's (c), (d), (e)), and its own
  `session.start` trace holds the engine alone (rule 6 confirmed); `session.append` always fires
  before the first `tool.call` (the prompt row, or after a reload the `/reload-plugins` command rows).
  Evidence: the spike's report `task-3-report.md` in the run's SDE workspace, temp tree
  `/tmp/m3a-spike.cX0Q8E` (`logs/`: the debug logs and tmux panes; the probe
  `mkt/doperpowers/sminos/hooks/mods/register.tsx`, a plugin named `sminos` in a marketplace named
  `doperpowers`, loaded from a directory marketplace; reloads typed in interactive sessions, headless
  refusing `/reload-plugins`).
- Observation (M3a): `/reload-plugins` re-instantiates only the modules that changed, so the chain
  changes around a bridge instance that lives on: devcloud enabled mid-session in an unplaced HOME
  loaded at index 0, outside a probe that was not reloaded, whose next trace changed from
  `["1:engine/core/returned"]` to `["2:engine/core/returned"]` behind devcloud with the marker
  present. A verdict taken once per instance would have stayed safe from inside the guard — hence the
  verdict on every dispatch (§4).
  Evidence: the spike's runC, debug-log lines 188, 261, 374, 575; runA and runB the reverse (devcloud
  unloaded, sminos not re-instantiated).
- Observation (M3a): devcloud's `$.state` marker outlives devcloud's module; with devcloud disabled
  and the session reloaded, cua's vendored guard reads it and stands down, so no guard acts (a
  token-shaped test string reached the transcript raw while the pane drew a handle). For the bridge's
  probe it errs only toward `off`. Outside this split: routed to the guards' owners as board #101,
  fixed by doperpowers #280 (devcloud 0.5.0, the marker answered live at version 0 and never stored)
  and cua#173 (cua 0.16.0); §4's rule reads only the version-0 answer as live.
  Evidence: the spike's runB lines 435 and 600, runF.
- Observation (M3a): a directory-source marketplace reloads its plugins in place from the source
  folder; `claude plugin update` keeps a plugin's place in `installed_plugins.json`, so an update does
  not push it innermost. Not observed: a subagent's `tool.call`, a `--resume` start, and whether the
  reload mod's `$.command.run({ command: 'reload-plugins' })` appends rows as a typed one does.
  Evidence: the spike's report, Surprises 3 and Not covered.
- Observation (M1): `/reload-plugins` loads a path-sourced plugin at its clone manifest's version
  whatever its record says, so after the marketplace update any reload loads the new doperpowers and
  to-human; the record writes are what make the reload mod's watchers fire, and only the dependency's
  install makes the new dependency load. A person typing `/reload-plugins` between the marketplace
  update and that install gets the new doperpowers without the ask; the mod cannot prevent it, only
  not reload into it itself. A dependency named without `@` resolves to the dependent's marketplace.
  Evidence: `hooks/mods/README.md` (reload section), 2.1.302 `NMe({ cacheOnly: false })`, `RF`
  (`cli.pretty.js` 409801); M1's report.

- Observation (M3.1): the moved tests are not at the same depth: `tests/sminos/X` →
  `sminos/tests/X` sits one level below the plugin root, so every `../..` became `..` (§2's "by the
  same depth" was wrong; the suite's RED run caught `test_rpcs.py`'s); files in `sminos/tests/mods`
  kept their depth. `claude plugin validate` refuses a `$.state` reference const that is also handed
  to `on`. `tests/skill-links/test-cross-doc-refs.sh` counts every directory under `skills/` as a
  skill, so the shim-only `skills/sminos` counts as the fifteenth.
  Evidence: M3.1's report, Discoveries.

- Observation (M3.2): no gate typechecks the mods; `tsc` against `.claude/types/claude-code.d.ts`
  shows errors that predate this work (`sminos/hooks/mods/ask.tsx` ~1007, 1689, 1732;
  `ask.test.ts` ~1397–1403; `bridge.test.ts` ~2137). The engine's re-entry rule (a plugin's own raise
  skips its own hooks) is described two ways in the types and the docs; the probe's origin rule (a
  dispatch raised by a guard's own plugin gives no verdict for that guard) relies on it.
  Evidence: M3.2's report, Concerns and Decisions.

- Observation (M3.3): the roll rehearsed whole on a served git remote (M1 359c71a6 → the M3
  head): the reload mod installed `sminos@doperpowers` headless (about 4 s, no prompt), then updated
  doperpowers 7.190.0, devcloud 0.6.0 and to-human 0.2.0, and reloaded once — `Reloaded: 4 plugins …
  0 plugin MCP servers`, no `--force`; the open async ask stayed open, was answered after the roll
  and delivered under `The sminos plugin sent a message:`; the bridge's socket was served by a new
  child from `sminos/1.0.0`; `installed_plugins.json` ended at sminos 1.0.0 beside devcloud 0.6.0.
  With sminos made uninstallable, to-human was held back, the reload waited with the debug line and
  the toast and transcript line naming `/plugin install sminos@doperpowers`, and the next fetch
  repaired it. The post barrier lifted promptly after a mod-run reload, at a `--resume` start, and
  for a subagent's first call after a reload; the reload mod's `$.command.run` reload appends its
  command rows after the new modules load. The bridge names a compact-tool compaction's rows through
  its own `session.compact` hook (the live compact-offer check, 7 of 7). Guard reads, with devcloud
  alone, settle in 0.3–0.8 ms each; with both guards beneath, none are made.
  Evidence: M3.3's report `task-6-report.md`; temp tree `/tmp/m33-rehearsal.TPq6oL` (`logs/`, pane
  snapshots), `/tmp/brl.83ey8dsh`.
- Observation (M3.3): a new interactive session on an M0 machine rolls itself before the reload mod
  acts: M0's `enabledPlugins["sminos@doperpowers"]` names a plugin the M1 catalog lacks, so the
  engine refreshes the marketplace at start (`refresh-on-miss`), loads every plugin at the clone's
  manifest version, sminos placed, and leaves `installed_plugins.json` unchanged; the reload mod's
  next fetch then installs sminos and updates the records, and the other sessions reload. It
  converges. A headless start does not do this. Until M3 is on the remote, every interactive start
  on the Macs refreshes the clone once.
  Evidence: `logs/fresh2.debug.txt` in the rehearsal's tree.
- Observation (M3.3): a tier change re-instantiates a module at `/reload-plugins` (setting or removing
  `prependPlugins` reloaded to-human, sminos and doperpowers, whose versions had not changed).
  `$.process.spawn`'s `result` settles with nothing after `return()`, where the types say it rejects
  (the bridge logged a false "child failed" on every stop; fixed). A resumed session logs `Tool
  mcp__sminos__AskUserQuestion not found in render-time tools` while history rows render before the
  tool registers (harmless, any plugin tool). After the roll the bridge raises an open ask under the
  registered new name while the transcript's call row keeps the old one; the desk joins a raise to
  its row by the request id and reads both names, and to-human reads the rows, never the raise, so
  neither is affected. The engine here is 2.1.304; nothing in §4, §5 or §10 behaved differently on it.
  Evidence: M3.3's report, Discoveries 2–7.

- Observation (M4): on macOS, `launchctl bootstrap` immediately after `launchctl bootout` of the
  sminos daemon can fail with error 5; a retry 3 s later succeeded, and the cold start took about 20 s
  to `daemon run started` and 16 s more to the uplink (the MacBook; the mini was fine). The shim's
  forward line is written to `daemon.out` (stderr), not `daemon.log`.
  Evidence: the author's M4 account, 2026-10-20.

- Observation (M5): without `prependPlugins`, where sminos lands relative to devcloud follows the
  order of `enabledPlugins` (install order), not the absence of the setting alone. With sminos
  installed first, the engine registered doperpowers, to-human, sminos, devcloud, which puts sminos
  outside devcloud; the bridge rightly stayed on and posted payloads. With devcloud first, sminos
  registered innermost and went off as A5 (a) says. The probe judges the real order either way; M3.3's
  unplaced HOME happened to have sminos installed last, by the roll. A5 (a) now names the condition.
  The roll to the M5 head reloaded only sminos and doperpowers (to-human and devcloud were at their
  clones' versions), and the open ask, the socket and the fold carried across.
  Evidence: M5's report, Discoveries 1–2 (`/tmp/m5-rehearsal/logs/a5u1.*`, `a5u3.*`).

## Decision Log

- Decision: verification — one independent spec review by the `doperpowers:adversarial-reviewer`
  agent (dispatched with `model: opus` while the Codex models are at their limit, until 2026-10-24)
  and, the execution section having five milestones, its buildability review in the same round; the
  branch review for each code milestone through doperpowers:review-code at **xhigh** (the panel): the
  change crosses four plugins, a settings-placed guard invariant and every machine. M2's branch is
  reviewed by MAWS's own rule.
  Rationale: the stakes, not the size; the owner named xhigh.
  Date/Author: 2026-10-19, the spec's author.
- Decision: the plugins' order is placed by the owner's `prependPlugins` (three entries); sminos
  declares no dependency.
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
- Decision: sminos starts at 1.0.0; the other three plugins move to the next minor above `main`'s
  at the time, one commit.
  Rationale: §10. The owner may name another starting version; nothing depends on the number.
  Literal numbers for the others were dropped in the second round: `main` moves under this spec
  (7.189.0 by #273 while it was reviewed).
  Date/Author: 2026-10-19, the spec's author.
- Decision: `devcloud/README.md` and the devcloud spec's §5, §6 and §8 describe the CLI at
  `<clone>/skills/sminos/scripts/sminos.py` and the hosts' managed settings as an `env` block alone;
  from M3 the CLI is `<clone>/sminos/skills/sminos/scripts/sminos.py`, and the managed file carries
  a `prependPlugins` that seats no sec-default (§8, I8). Recorded here rather than rewriting that
  spec.
  Date/Author: 2026-10-19, the spec's author.
- Decision (first review round): M0 — `prependPlugins` and the `sminos@doperpowers` entry before
  the roll; M1's reload mod installs new dependencies before it reloads; M3 is rehearsed on a
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
- Decision (first review round, settled the same day by the devcloud setup session): the devcloud
  hosts' placement is that session's — a managed `prependPlugins` that seats no sec-default now, the
  directory-marketplace route deferred until a host must enroll or the engine gives cache-installed
  policy plugins the tier; enrolling a host stays blocked. This spec relies on it (I8) and builds
  nothing for it.
  Rationale: §8 and Surprises — any managed settings shadow the user's `prependPlugins`; the
  env-only file seats sec-default, which ate the guard's and the bridge's hooks; the copied lists
  unseat it but give cache-installed plugins no tier. Rejected: the process-environment route
  (settings `env` overwrites it; the synced base URL would win); this spec's second-draft overlay on
  the received `settings.json` (undone at every reset, the Mac's values hot-reloaded in between, the
  clone left dirty — the file is the Mac's).
  Date/Author: 2026-10-19, the spec's author, after the adversarial reviewer, the owner's account,
  and the devcloud setup session's container results and decision.
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
  `origin/main` and MAWS `origin/master`. Nothing rejected in that round; one finding (the M3 proof's
  "the old name is refused with `WITHDRAWN`") was dropped as unprovable — no plugin registers the old
  name after M3.
  Date/Author: 2026-10-19, the spec's author.
- Decision (second review round): the bridge's probe of its place reads `next.trace` on the first
  settled `tool.call` or `session.append`, per module instance, with no kept state, holding tool
  payloads until the verdict; built only if the spike M3a confirms the trace's shape in a hooks
  module and across a reload; discarded otherwise, the invariant then resting on M0's precondition,
  the rehearsal and A7. The marker-version design is withdrawn.
  Rationale: §4 and Surprises — a reloaded module's `session.start` holds no other plugin's hook,
  and the version read races across workers in the unsafe direction. Rejected: keeping a verdict in
  `$.state` across reloads (misreads the roll); any probe at `session.start`.
  Date/Author: 2026-10-19, the spec's author, after the second round.
- Decision (second review round): `PLUGIN` is the plugin's real name from M3 (`$.plugin.name`, or
  the literal changed), the fixtures import it, and a test pins it to the manifest's name; the
  rehearsal serves the M1 clone as a loopback git remote with `autoUpdate` true, forces the mod's
  fetch, and records the reload's answer; M1's reload mod acts on a version difference, not on a
  moved head alone; version numbers are "the next patch/minor above `main`'s at the time"; M0's
  `enabledPlugins` entry is a precondition of the roll, an owner step awaiting their explicit OK.
  Rationale: the second round's findings 2–6, each checked (Surprises). Nothing rejected.
  Date/Author: 2026-10-19, the spec's author.
- Decision (execution pre-flight): each milestone ships as its own branch off `origin/main` and its
  own PR, opened, gated, reviewed and merged by the plan's executor (M2 the same in MAWS, off
  `origin/master`); this spec's living sections ride the milestone PRs. The executor merges only
  once `origin/main` is an ancestor of the head and the gate's tree equals the head's, with
  `--match-head-commit`; after each merge it tells the spec's author, who rolls the Macs and deploys
  the desk, and waits for that before building on the merge as live (M1 rolled before M3's
  rehearsal relies on it; M2 deployed before M3's roll). M2's ticket on MAWS's board is not
  registered by the executor (it writes no board): the PR carries §11 as its body, and a ticket, if
  wanted, is the author's to register. M1 is built beside #278 (`reload-rows-out-of-context`), open
  on `reload.tsx` at this writing; whichever lands second merges `origin/main`.
  Rationale: the author's dispatch of 2026-10-19 (the split of hands).
  Date/Author: 2026-10-19, the plan's executor.
- Decision (revises the verification entry above): M1's and M5's branch reviews are
  `doperpowers:reviewer-high` dispatched with `model: fable`, after each milestone's task review
  (`doperpowers:task-reviewer` with `model: opus`); M3 keeps the xhigh panel, run by the spec's
  author from the main session with Claude models in every lane, on the range the executor sends
  once M3's PR is gated green. M2 stays under MAWS's rule.
  Rationale: sol and astra are at their usage limit until 2026-10-24 13:40 PDT, and the panel
  workflow runs only from the main session; the carve-out and the rename are where an adequate
  review costs the most, so M3 alone keeps the panel.
  Date/Author: 2026-10-19, the plan's executor, on the author's ruling.
- Decision (M3a): promote the bridge's probe, amended: the rule is evaluated on every settled
  `tool.call` and `session.append`, `off` terminal for the instance (made recoverable by the M3.2
  review's decision), the hold-and-release on the first
  verdict only; the residual window (§4) is accepted and documented with its bound.
  Rationale: the spike's four observations held; a module that is not reloaded keeps its instance
  while the chain changes around it (Surprises, M3a), so a once-per-instance verdict errs in the
  unsafe direction. Rejected: holding every call's input until its own `next` settles (closes the
  window at the cost of the desk's live input streaming for every long-running call, a window M4
  closes on every machine).
  Date/Author: 2026-10-19, the plan's executor, accepted by the spec's author.
- Decision (M1): the readers hold only the sets of I3; `PLUGIN_PROMPT` is removed from `ask.tsx` (it
  had readers only — the engine writes the framing), and `sminos.py` and `to-human.tsx` keep no
  single-name constant; `ask.tsx` keeps `ASK_TOOL` (the registered name, imported by the bridge) and
  `PLUGIN`, the two values M3 changes. The ask's `ToolUse` / `ToolResult` render hooks read both
  names too (a resumed session draws its old rows through them, so an open ask keeps its
  `[ answer ]`). The reload mod takes as its batch every enabled user-scope plugin of the marketplace
  whose recorded version differs from its clone manifest's (`plugin.json` at the entry's string
  `source`); a plugin with no such manifest version (a url source like ci-kit) updates only on a
  moved head, as before. Before the batch it installs every dependency the enabled plugins' clone
  manifests name that has no user or managed record (superseded in part by the two entries below:
  the closure, the narrower hold, and the `fetch.applying` mark in place of `fetch.lock`). Every
  session's reloader holds while the fetch applies, so a batch of installs and updates reloads once at
  its end. `hooks/mods/README.md`'s reload section
  describes the new path.
  Rationale: M1's report — the sets make `PLUGIN_PROMPT` dead code; the render hooks match stored
  rows by name; a batch's writes land more than one watcher period apart, and each gap would reload
  every idle session (restarting the bridge's child) on a half-applied batch.
  Date/Author: 2026-10-19, M1's executor, folded by the plan's executor.
- Decision (M1 review, revises §10's "refuses the whole batch"): the missing dependencies are
  gathered from every enabled plugin of the marketplace and installed whoever wrote the records (the
  mod's own fetch, a session's startup auto-update, a person's `claude plugin update`); a failed
  install holds back only the plugins it affects, along the dependency closure — a changed plugin is
  held when any plugin in its dependency chain is missing or itself held, so a dependent never
  updates or reloads over a held dependency (to-human over a doperpowers held for sminos); the
  reloader holds a due reload on the same rule and fires once the dependency is installed.
  Rationale: the task review found the reloader reloading into a missing dependency when another
  actor applied the update, with the fetcher never repairing it (it returned when nothing was
  behind); the branch review (fable, P3) found that one plugin's uninstallable dependency, outside the
  batch, would block the roll of the whole marketplace on every fetch. Rejected: the whole-batch
  refusal (P3's block).
  Date/Author: 2026-10-19, the plan's executor, on the spec's author's ruling.
- Decision (M1 fix wave): the reloader's hold reads what the reload would load, not only the changed
  records: a path-sourced plugin counts as changing when its clone manifest's version differs from the
  one the session runs (its dependencies read from the clone), any other plugin when its record moves
  (its dependencies from its install's `plugin.json`); one held plugin holds the whole reload, since a
  reload loads everything; a plugin that already lacked a dependency holds nothing. The reloads wait on
  a `fetch.applying` mark the fetch writes around its installs and updates (stale after
  `APPLY_STALE_MS`, 3 minutes), not on `fetch.lock`, so a session that dies mid-fetch holds the
  machine's reloads for 3 minutes rather than 30.
  Rationale: M1's discovery — `/reload-plugins` loads a path-sourced plugin at the clone's version
  whatever its record says — makes a records-only hold fail the real roll: with sminos not installed,
  to-human held and doperpowers (depending on nothing) updated, that record change would reload
  doperpowers at M3 without the ask and to-human without sminos. A reload held for a dependency that
  never installs waits until the records change; M3's rehearsal checks the held reload's debug line.
  Date/Author: 2026-10-19, M1's fixer, folded by the plan's executor.
- Decision (M1 fix wave 2): the dependency hold is evaluated on the tick that would fire, just before
  the reload, not when the records changed (a clone can move under a pending reload with no record
  write — the fetcher's own marketplace update, or a person's); the `fetch.applying` mark is written
  before each marketplace's refresh and at the top of each marketplace's pass once a batch has
  started, so a two-marketplace batch stays under it; a held reload is told once per hold (plugin and
  missing dependency) as a toast and a transcript line, as `FORCE_TEXT` is — "A plugin update is not
  applied: <key> would load without <missing>, which is not installed. /plugin install <missing>
  installs it, and the reload follows." — with the debug line kept.
  Rationale: the branch re-review's P2 (a stale pending reload loading M3 from the clone without
  sminos) and P3 (two reloads on a slow two-marketplace roll); the task re-review's minor that a
  held reload, which holds every reload on the machine, was said only in the debug log, unseen on the
  unattended Mac mini.
  Date/Author: 2026-10-19, M1's fixer, folded by the plan's executor.

- Decision (M3's execution): M3 stays one milestone, one branch and one release, built by three
  executors in sequence on `sminos-m3-carveout`, each task-reviewed before the next: M3.1 the
  carve-out and the rename (everything M3 touches but the bridge's probe and the rehearsal — the
  moves, the sminos plugin's files, `ASK_TOOL` and `PLUGIN`, the `sminos.ask` channel with its
  shape-1 fallback, appeal's and reload's reads and appeal's fake-guard case, the compact → bridge
  path, the shim, `installed_cli`, the service templates and `sminos_host.py`, the board resolver and
  templates, the manifests, the gates, the versions, the agents, the output style and the
  documents; proved by A8's suites, both validates and ci-gate); M3.2 the bridge's probe (§4 as
  amended); M3.3 the rehearsal and the live acceptance in the rehearsal's HOME (A1, A2's
  blocking-dialog clause, A5, A8's rehearsal half), changing code only to fix what it finds. The
  xhigh panel reviews the whole PR once it is gated green.
  Rationale: M3 is several times any other milestone; the probe is separable code with its own case
  table, and the rehearsal is live, slot-bound, and needs the built release to roll onto.
  Date/Author: 2026-10-19, the plan's executor.

- Decision (M3.1): `PLUGIN` is the literal `'sminos'`, not `$.plugin.name` (`claim()`, `isDialog`,
  `enteredRow` and the bridge's modules run where `$` is not passed, and a value read at
  `session.start` leaves a window with no name); `test-ask-search.sh` pins it, and `ASK_TOOL` as
  `mcp__<name>__AskUserQuestion`, to the manifest's `name`. doperpowers' `types` key is dropped (it
  declares no value; `claude plugin validate` passes, reporting the `sminos.ask` read as another
  plugin's, not checked). appeal and reload write the `state.set` matcher as a literal, since
  `validate` refuses a reference const also handed to `on`. `answered` counts once per human act (a
  dialog's outcome, or an answer from outside); appeal ends its passes only when it grows against a
  count seeded at `session.start`; a guard's `{ deny }` is appealable, the notice appended to its
  text; a grant on input carrying a handle leaves no pass and says so (`NO_PASS`, the log's
  `no-pass`). The shim prefers a user-scope install record to a managed one and ignores project
  scope; the suite fails on the shim's forward line seen on its runner's stderr (output a test
  captures itself is not seen) and reaches the shim at `$PLUGIN_ROOT/../skills/sminos/scripts`.
  `maws-to-human-contract` stays 4 and the `dx4-jobs.*` vectors are untouched (MAWS vendors them);
  old-name fixtures stay beside M1's new-name ones. The moved live checks stage `PLUGIN_ROOT`'s
  parts; `live-compact-offer-check` and `live-reload-rows-check` stay in `tests/mods` and stage both
  plugins. The cutover is one commit.
  Rationale: M3.1's report; each is the executor's call M3 left open, or the spirit of §3–§10.
  Date/Author: 2026-10-19, M3.1's executor, folded by the plan's executor.

- Decision (M3.2): the probe lives in `sminos/hooks/mods/bridge-place.tsx` (the pure rule) and
  `bridge.tsx`. The first verdict's hold is a barrier in the post queue (§4), not stripped payloads.
  `off` needs a trace that reaches the engine's entry, while `safe` does not: a trace cut short by a
  link that answered itself (a plugin's own tool, a refused row) gives no verdict, so a placed
  machine never turns itself off on one. A dispatch raised by a guard's own plugin gives no verdict
  for that guard (cua's `/secret` note reaches the bridge without passing cua's hooks). When the
  trace names both `devcloud` and `cua`, no host read is made (the placed Macs' case). A failed read
  gives no verdict and a debug line. `off` retires the bridge before it toasts, so no later
  `session.start` revives it (superseded by the M3.2 review's decision: `off` is recoverable through
  a later safe dispatch only). devcloud's contract is read through `import type`, appeal's form.
  Rationale: M3.2's report; the barrier keeps DX5 unchanged, and since `session.append` fires
  before the first `tool.call` (M3a), the barrier normally lasts until the session's first row.
  Unobserved, for M3.3: the barrier's length after a reload made by the reload mod's
  `$.command.run`, at a `--resume` start, and for a subagent's first call after a reload.
  Date/Author: 2026-10-19, M3.2's executor, folded by the plan's executor.
- Decision (M3.1, I6): the board resolver lives in `skills/issue-tracker/scripts/_sminos_cli.sh`,
  which `_lib.sh` sources, because the dispatchers and the sweep need the CLI before they `cd` into
  the consumer repository, where `_lib.sh` dies, and `board-gc.sh` never sources `_lib.sh`. Any
  `SMINOS_CLI` override must point into a directory that also holds `lib.sh`, so the tests that stub
  the CLI link the real `lib.sh` beside the stub.
  Date/Author: 2026-10-19, M3.1's executor, folded by the plan's executor.

- Decision (M3.2 review, revises §4's "`off` is terminal for the module instance"): `off` is
  recoverable. While off: nothing posted, what waits dropped, the barrier re-armed, no permission
  input raised, a `/clear`'s `state.restart` refused. Back on only through a dispatch that began after
  the transition to off and reads `safe`, by a reload's path (a new child, a new hello nonce); each
  transition toasted once and logged. In the same wave: the row is announced before it is judged
  (DX5's write order; a guard's `session.append` scrubs before its `next` either way); a persistent
  read failure is toasted once per module instance; `isLiveMarker` requires exactly devcloud's two
  keys, as cua 0.16.0's `isDevcloudMarker` does; devcloud's two hooks carry a comment that the probe
  relies on them staying unmatched.
  Rationale: the task review found two ways a safe bridge turns itself off for good: the cua leg
  reads the settings' intent (`enabledPlugins['cua@cua']` is written before cua's module loads, so
  an install or enable reads cua loaded and not beneath, deterministically), and the trace and the
  reads are taken at different moments (a guard loaded while a call is in flight). Safety comes from
  never posting while off; terminality adds none. (The claim first written here, that the
  re-evaluation reads with the first verdict's rules and so opens no new false safe, was wrong —
  see the next entry.) Rejected: confirm-before-terminal (off terminal
  only once a later dispatch also reads off) — it heals the second case but not the first, which
  reads off on every dispatch until a reload; a marker of cua's own (out of scope).
  Date/Author: 2026-10-19, the plan's executor, on the spec's author's ruling.
- Decision (M3.2 re-review): an off bridge turns back on only on positive evidence: a guard the
  reads report as loaded has its link beneath, or the trace names both `devcloud` and `cua`. "No
  guard loaded" settles a first verdict, never a recovery. A dispatch that began before the last
  transition (either way) changes no state and posts nothing, so calls in flight across a
  transition do not flap the bridge. Turning off withdraws only permission requests, never a
  question (an ask's answer dialog or a native AskUserQuestion): a question's input never came
  through the guard, and an ask's dialog is mapped only once it has its answer, so its own record,
  or the `RECORD_WAIT_MS` fallback, settles the dialog and the ask together (a wave that withdrew
  the dialog and kept the ask open stranded an answered ask as pending; reversed).
  Rationale: the re-review found that recovery through "no guard loaded" reopens the leak direction:
  cua's leg reads the settings' intent, so a person who disables cua after the off toast, without
  reloading, leaves cua's module outside the bridge while the reads say no guard — the first
  verdict meets that gap only before a module instance's first dispatch, an off bridge sits in it
  for as long as the fix takes, and the toast invites the fix. devcloud's leg is a fact (its loaded
  module answers the marker), not a setting. Cost accepted: a bridge whose guard is truly removed
  stays off until sminos reloads. The stale-dispatch rule and the questions' exemption are the same
  review's minors.
  Date/Author: 2026-10-19, the plan's executor, within the author's ruling (its premise restored).

- Decision (M3.3, A5 (f)): (f) is worded to the observed paths: a tier change re-instantiates the
  module, so `prependPlugins` set mid-session brings the bridge back as a new instance whose first
  verdict is safe, silently; the in-instance recovery, toast included, is the one shown when the guard
  moves inward (`appendPlugins` for devcloud). No code change; a new instance remembering that its
  predecessor was off would need state across instances, which I1 rules out.
  Rationale: M3.3's rehearsal, Discoveries 2; the author's ruling.
  Date/Author: 2026-10-20, the plan's executor, on the spec's author's ruling.
- Decision (M3.3): the rehearsal served the remotes over smart HTTP (`git http-backend` behind a
  loopback server), since the engine's marketplace clone is shallow and dumb HTTP refuses shallow
  fetches; the live compact-offer check ran through a wrapper that keeps no key on disk. A child the
  bridge stopped is logged as stopped (`7bd8276f`). Left as they are, on the author's ruling: the
  repository's live checks write the gateway keys to a 0600 env file (residue); the value a committed
  doc carries is the local relay's marker, not a credential.
  Date/Author: 2026-10-20, M3.3's executor and the spec's author, folded by the plan's executor.

- Decision (M3 xhigh panel, 2026-10-20; verdict incorrect, every finding confirmed by the verifier):
  (1) reload's turn tracking must be outer to compact's `turn.complete`, or its flag drops before the
  compact tool's compaction runs and a reload tick can fire mid-compaction — `registerReload` now runs
  ahead of `registerCompact` in doperpowers' `register.tsx` (every reload hook is matched, so the
  one-unmatched-registration limit holds); (2) the bridge's PermissionRequest hook rechecks the
  transition count after its `await next`, so a request whose window saw an off is not raised; (3)
  the ask takes up doperpowers' shape-1 snapshot only when its `store.sessionId` is this session's
  (none taken without a `store`); (4) the bridge's `session.compact` comment names the compact tool's
  compaction as reaching it only through that hook; (5) appeal's `carriesHandle` drops the pass for
  any grant quoting a handle, also for tools the guard never restores — safe and narrow, logged in
  `docs/doperpowers/TECH-DEBT.md` rather than fixed (fixing it would copy devcloud's restore set into
  doperpowers). Re-review of the fix range by a task reviewer (opus); no second panel.
  Date/Author: 2026-10-20, the spec's author's panel, fixed by the M3 fixer, folded by the plan's
  executor.

- Decision (M5's acceptance re-run): M5 re-runs A1–A6 and A8 as written, in temporary HOMEs on the
  MacBook, with §10's rehearsal rolling a HOME from origin/main's marketplace state to the M5 head (so
  the reload mod rolls the cleanup itself), and A4 for the first time; A9's grep runs at the M5 head
  and again after the merge. A7 and the desk clause of A2 are real-machine criteria and stand as
  checked live on both Macs in M4: M5 changes nothing on the daemon's service path, and its removal
  of the shim is safe only because A7 held on every machine.
  Rationale: M5 removes the transition scaffolding (the shim, the shape-1 fallback, the old name in
  the agents, the gate path); the rehearsal's roll from the current main is the one place that
  removal meets a live HOME before the owner's machines.
  Date/Author: 2026-10-20, the plan's executor.

- Decision (M5): `keptBefore` stays, reading only sminos's own shape-2 value at
  `{ plugin: 'sminos', key: 'ask' }`; M5 removed its shape-1 branch and `KEPT_BEFORE`.
  Rationale: the own-key read is the reload takeover (a `/reload-plugins` or the autoreload keeps the
  asks), which is the hook's other behavior and must stay; only the takeover from `doperpowers.ask`
  was transition scaffolding.
  Date/Author: 2026-10-20, M5's executor.
- Decision (M5): A3 ran against a transcript recorded at M1 (`359c71a6`), the last state that
  registered the old name; the repository's live check records its own transcript, so a subclass in
  the rehearsal's tree ran its checks against the recording, keyless.
  Rationale: origin/main registers the new name, so no session there can record an old-name call, and
  no M3.3 transcript held an old-name ask answered under the old framing.
  Date/Author: 2026-10-20, M5's executor.
- Decision (M5): A5 (a)'s wording names its real condition, sminos registered inside devcloud
  (devcloud ahead of it in `enabledPlugins`), rather than the absence of `prependPlugins` alone.
  Rationale: the M5 observation above; the probe was right in both orders, the criterion's premise
  was not.
  Date/Author: 2026-10-20, the plan's executor.

## Outcomes & Retrospective

**What was achieved.** The purpose holds as written. `sminos@doperpowers` is a plugin of its own
(1.1.1 at M5), carrying the CLI, the daemon and uplink, the bridge, the async ask and the record and
guide hooks; doperpowers no longer carries any of them, and the ask tool is
`mcp__sminos__AskUserQuestion`. Both Macs rolled to it without `--force` (M4), their daemons run from
the plugin's own path, and asks opened under the old name before the roll were answered after it.
M5's rehearsal re-proved the rest at the cleanup head: A1's order, A2's round trip and blocking
dialog, A3's resume and `/branch` copy of an old-name transcript, A4 (sminos alone and doperpowers
alone, run for the first time), A5 (a)–(f), A6, A8's unattended roll and A9's grep. MAWS's desk reads
both names (M2). What stays for good: the readers of both names (§3), which a transcript from before
the rename needs.

**What went differently from the plan.**
- M3 was split into three steps (carve-out, probe, rehearsal) once its size was clear; each was
  task-reviewed on its own, and the xhigh panel then reviewed the whole.
- The `next.trace` probe was promoted with its verdict evaluated on every dispatch, and `off` became
  recoverable on positive evidence (the author's ruling) rather than terminal; it took three fix waves
  to settle what "positive evidence" and a stale dispatch are.
- The reload mod grew past "act on a version difference": it installs a missing dependency whoever
  applied the update, holds back a failed dependency's closure, and judges the hold on the tick that
  would fire. M1's reviews found each of those as a way an unattended roll could strand a machine.
- A5's criteria were worded to the paths observed (f, and in M5 a) rather than the ones first
  imagined; in both cases the code was right and the criterion's premise was not.

**Lessons.**
- An unattended roll is only as safe as its worst intermediate state: a reload that lands between the
  marketplace's update and a dependency's install loads a plugin with a hole in it. Judging readiness
  on what the reload would load, at the moment it fires, was the fix that made the roll trustworthy.
- Hook placement is decided by the engine from settings, tiers and install order together; a probe
  that reads the live order (`next.trace`) beat any reasoning about what the order should be, and the
  acceptance had to be written against the order observed.
- Keeping the readers of both names permanently, and removing only the writers' scaffolding at the
  end, let every step ship alone and every machine roll at its own time.
