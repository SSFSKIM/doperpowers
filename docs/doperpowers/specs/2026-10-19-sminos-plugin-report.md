# sminos plugin — execution report

This report covers the execution of the Plan of Work in
`docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`, for the session that wrote that spec. The
spec's living sections (Progress, Surprises & Discoveries, Decision Log) are the detailed record. This
report gives the overall account.

## What shipped

| Milestone | Where | Result |
|---|---|---|
| M0 | owner, both Macs | `prependPlugins` = to-human, sminos, doperpowers; `enabledPlugins["sminos@doperpowers"]` |
| P0 | doperpowers #276 (02ef424f) | the bridge raises a request's input in the handle form it captured |
| M1 | doperpowers #281, merge 359c71a6, 7.189.7 / to-human 0.1.2 | both ask names and framings read; the reload mod rolls a machine whole; rolled 19:13Z |
| M2 | MAWS #74, merge 9fd93735e | the desk reads both names; deployed 17:53Z |
| M3a | spike, no code | `next.trace` probe promoted, with the verdict evaluated on every dispatch |
| M3 | doperpowers #282, merge 7c809e84 | sminos 1.0.0 carved out, ask renamed; doperpowers 7.190.0, to-human 0.2.0, devcloud 0.6.0 |
| M4 | the author and the owner, both Macs | rolled about 23:56Z without `--force`; A1, A2, A3 and A7 held live; daemons reinstalled at the new path 02:24–02:25Z |
| M5 | doperpowers PR (this branch, `sminos-m5-cleanup`), doperpowers 7.190.1 / sminos 1.1.1 | the shim, the ask's shape-1 takeover and the agents' old name removed; A1–A6, A8 and A9 re-run in temporary HOMEs, A4 for the first time; the author merges, rolls and checks A7 and A9 |

## How it ran

The SDE loop put each milestone on its own branch off `origin/main`, gated with ci-gate (tree
compared), reviewed and merged by the plan's executor. Reviews followed the author's routing while
sol and astra were out:
- task reviews ran on opus;
- M1's branch review was `reviewer-high` on fable;
- M3's branch review was the xhigh panel (opus finders, fable verifier), run by the author.

Review rounds and what they caught:
- M1: two fix waves.
  - A reload into a missing dependency when another actor applied the update.
  - One plugin's uninstallable dependency blocking the whole marketplace.
  - The hold evaluated at read time rather than fire time.
  - A gap in the applying mark.
- M3 was built in three steps (M3.1 carve-out, M3.2 probe, M3.3 rehearsal).
  - M3.2 took three fix waves. A terminal `off` could leave a safe bridge off for good, so `off` was made recoverable on the author's ruling. Recovery now needs positive evidence. Stale dispatches no longer flap the bridge. Questions are never withdrawn.
  - The panel then found one P2 and three P3s. The P2: reload's turn flag was inner to compact's.

- M5: one commit, built and acceptance-run by one executor; the branch review was `reviewer-high` on fable.

M3.3's rehearsal on a served git remote proved the roll unattended:
- a headless sminos install;
- no `--force`;
- the open ask survived;
- held and retried correctly when sminos could not install.

## Validation

- M1: ci-gate run 39303896510, 9/9.
- M2: MAWS gate run 39295926848.
- M3: ci-gate run 39343694214, 13/13; tree 72cc7867 = head b0e36352.
- Local suites at M3's head:
  - sminos mods 373;
  - doperpowers mods 193;
  - sminos suite 2084 assertions;
  - to-human 64;
  - devcloud 93;
  - board loops green.
- The live acceptance in the rehearsal: A1, A2's blocking clause, A5 (a)–(f), A8's rehearsal half, and the compact-offer check 7/7.
- M4, live on both Macs: A1's order, A2/A3 (two old-name asks answered across the roll), A7 (the plist names the plugin's path; uplinks connected 02:24:59Z and 02:25:35Z).
- M5 at its head (7974a3e5):
  - every suite green (sminos suite 2125 assertions, doperpowers mods 193, the ask test 127/127), both `claude plugin validate`s;
  - a HOME at origin/main rolled by the reload mod to the head with no `--force`, its open ask delivered as `The sminos plugin sent a message:`;
  - A3 against an old-name transcript recorded at M1: 5/5, plus the interactive resume and a `/branch` copy;
  - A4 both halves, A5 (a)–(f), A6, A9's grep.
  - Logs: `/tmp/m5-rehearsal/logs`, `/tmp/m5-accept`.
- M5 ci-gate: GREEN on the PR head; the run is in the PR body.

## Residue (for the dispatching session to register)

- No gate typechecks the mods. `tsc` errors predate this work (sminos `ask.tsx`, `ask.test.ts`, `bridge.test.ts`). A tsc gate over the three plugins' mods would catch drift that `claude plugin test` does not.
- The live checks write the gateway keys into a 0600 env file (`sminos/tests/mods/live-bridge-check.py` `setup()`). The rehearsal's `env -i` by-reference wrapper keeps keys off disk.
- to-human draws a resumed session's old marks raw until the first new mark (`hasSeenMark`). This predates the work.
- MAWS #75: the live spec's to-human path. Already registered.
- The held-reload notice: a held reload re-reads the records every 15 s and tells the hold once per session, so every open session on a machine shows it. That is acceptable for now, but a machine-wide stamp would show it once.
- Unconfirmed: whether `claude plugin update`'s "already at the latest version" check reads the clone's `plugin.json` or the marketplace entry. The bump script moves both, so this has not been seen to matter.
- devcloud's `sminos_host.py` still falls back to the removed shim path. The branch never matches now, so it is harmless, but it and its comments (`devcloud/boot/devcloudlib/sminos_host.py:64`, `devcloud/tests/unit/test_sminos_host.py:155`) are dead and belong to the devcloud session.
- A machine with doperpowers but without to-human (and so without its dependency on sminos) gets a doperpowers with no async ask. The style's fallback sentence covers it; A4 checks that half.
