# Project environment manifests — execution report

Spec: `docs/doperpowers/specs/2026-10-02-project-env-manifest-design.md` (the living record: Progress,
Concrete Steps, Decision Log, Surprises, Outcomes). Executed 2026-10-02 → 2026-10-03 by a
plan-executor as SDE controller: one task-executor (opus/high) and one task-reviewer (sol/xhigh)
per milestone, a medium-rung whole-branch review at the end.

## Status

E1, E2, E3 complete and reviewed clean; the whole branch (E1–E3, four repositories) passed the
medium-rung review after one fix wave. **E4 is open**: it needs the host layer's devbox (M3), which
does not exist yet (cax41 out of stock in every EU location at last check; Tailscale policy and
`tag:devbox` key pending the human). No pull request is open: the design session holds E4 as the
one remaining item and the branch stays open for it.

## Commits

**doperpowers, branch `project-env-manifest`** (pushed; merge-base 0aa14b74): code — 13858369,
30d39690, 0a0ecd32 (doperpowers' own `.devbox/`), da7efb47 (`cloud-env-setup` skill, 7.134.0),
c20101e7, da136174, d2389f72 (`scripts/env-names` and its test); the rest are spec commits.

**claude-config (`~/.claude`)**
- On `main` (E1–E2, before the human's 2026-10-03 constraint): f86ae18, 2b16ebb, 15d94dd, 40187a0,
  b84a386, 2c9fe4f, 437b1da (an auto-sync capture of E1's fix), 703e1ba, 683b8be, ad70f3c,
  01cadb4, 954a7a8, 6772c2c, 95087f2, e308662, b2d1b19 (auto-sync capture), f1899ec, 5ffe2ab,
  dce0853, c083196.
- On branch `project-env-manifest` (pushed, **not merged** — the constraint forbids main): d66e0bf,
  518c63a, 2a386b6 (the final review's fixes), in the worktree
  `/Users/new/Developer/GitHub/claude-config-project-env`. Until the human merges it,
  `~/.claude/tools` holds the pre-fix `devenv`/`reap`.

**MAWS, branch `devbox-manifest`** (pushed, not merged): 7de5000f, 60fce2f0, 97d9e68d, 7c0e2932.
**claude-usage-menubar, branch `devbox-manifest`** (new from origin/main; pushed, not merged):
0af16f1, ec58650.

## Validation evidence

| Claim | Command | Result |
|---|---|---|
| tools suite (branch with final fixes) | `python3 -m unittest discover -s tools/tests` in the claude-config worktree | `Ran 175 tests … OK (skipped=1)` (2026-10-03, this controller) |
| env-names extractor | `bash tests/claude-code/test-cloud-env-setup-env-names.sh` | `all passed` |
| version manifests | `scripts/bump-version.sh --check` | `All declared files are in sync at 7.134.0` |
| `devenv`/`reap` on PATH from a fresh login | `env -i HOME=$HOME /bin/zsh -l -c 'command -v devenv reap'` | `/Users/new/.local/bin/devenv`, `/Users/new/.local/bin/reap` |
| acceptance 1, 2, 3 (fake-backed), 5, 6, 8, 9; 4 (MAWS, isolated); 7 (spawn and resume) | laptop runs in scratch `<GH>` | transcripts in the spec's Concrete Steps (E1, E2, E3) and the task reports |
| whole branch | `doperpowers:reviewer-medium` over all four repositories | three P2s → fixed → "correct, no material findings" |

Not yet verified (E4): acceptance 10; `gh api user` and every real-handler run of acceptance 3;
the seat-under-sandbox check of 7; `reap`'s Linux subreaper path (modeled on macOS only); MAWS's
Linux install (`--ignore-scripts`, typecheck/lint/unit tests); the mini receiving the tools by sync.

## What E4 needs

1. A devbox from the host layer's M3, reachable from this laptop, with `secret-env` and its
   service-account key (and the list-only role), `GH_TOKEN` in the background daemon's environment
   (host M4), and the canonical clones trusted in its `~/.claude.json` (seats refuse an untrusted
   `--cwd`).
2. The claude-config branch `project-env-manifest` available there without merging to main — run
   `devenv`/`reap` from a separate checkout of that branch by absolute path rather than switching
   the devbox's `~/.claude` (its sync would commit to main).
3. The spec's E4 milestone: pre-existing clones prepared (clean → switch to the manifest branch,
   dirty → stop), MAWS's Linux install made real, the `http.server` fixture for acceptance 4, and
   acceptance 1–10 recorded in Concrete Steps.

## Incidents (detail in the spec's Surprises)

- E2's MAWS acceptance run wrote to the person's real MAWS userData twice (a dev build with the
  default data directory; then a hand-run probe), migrating its settings and deleting its engine
  copy. Reported to the human at once; no repair attempted by us. MAWS now runs only with
  `MAWS_USER_DATA` under `.devbox`.
- E2's probe and seat sessions (11) landed in `~/.claude/projects`, which MAWS displays; deleted on
  the human's decision. Every test `claude` run now uses a seeded scratch `CLAUDE_CONFIG_DIR`.
- E3's executor once ran `run-skill-tests.sh` whole, whose SDE test drives the real CLI under the
  real config (9 sessions, deleted at once; confirmed none remain).
- The 23:06 rebuild of MAWS.app in the person's checkout was the human's own MAWS session, not this
  work (every agent transcript scanned).

## Environmental friction routed around

- claude-config's 30-minute sync committed work-in-progress twice under its own message (437b1da,
  b2d1b19); executors moved mutation checks to copies outside `~/.claude`.
- No GitHub SSH key on the laptop: HTTPS URLs throughout (also the devbox's form).
- npm 12 blocks dependency install scripts unless allow-listed; harmless for doperpowers (noise).

## Unresolved review findings

None deferred. One Minor was dismissed: npm 12 `install-scripts` warnings in doperpowers' install
are harmless noise (the poller's 117 tests pass without approving scripts) — recorded in Surprises.

## Residue (for tickets)

1. **Per-seat project secrets.** A seat's environment is the background daemon's, so project
   secrets reach only `devenv claude` sessions (v1 limitation, spec §3/§5). Needs a
   daemon-independent spawn path or a change to Claude Code's dispatch allowlist.
2. **sminos skill doc: resume and the environment.** `sminos resume` goes through
   `claude --bg --resume`, and a resumed seat saw `GH_TOKEN` unset though the caller exported it;
   the skill's "resume inherits this process's environment" is untrue for allowlist-dropped
   variables.
3. **claude-usage-menubar `HistoryStore.record` prunes by `Date()` instead of the passed `now`.**
   Two `HistoryStoreTests` fail on main once the date is past their 2026-08-29 fixtures; its
   validate is build-only until fixed.
4. **`tests/claude-code/run-skill-tests.sh` drives the real `claude` CLI under the real config**
   (`test-subagent-driven-execution.sh`), creating sessions in the person's store; it should run
   under a seeded scratch `CLAUDE_CONFIG_DIR` or be marked integration-only.
5. **A sminos test assumes the canonical `/private/tmp` path** ("reading chat is the first sminos
   instruction" fails when the checkout sits under the `/tmp` symlink).
6. **Merges waiting on the human:** claude-config `project-env-manifest` (blocked by the
   MacBook–mini constraint), MAWS and claude-usage-menubar `devbox-manifest`, then this branch;
   afterwards the registry refs move to the default branches with a dated Decision Log line.
