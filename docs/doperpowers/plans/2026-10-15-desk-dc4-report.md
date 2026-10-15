# DC4 (the uplink): execution report (2026-10-15)

**Status:** DONE. PR https://github.com/SSFSKIM/doperpowers/pull/194, against `main`. It merges after DC2's PR; the composite's writer runs the merges.

**Branch:** the local branch `worktree-agent-a6d7f69a8ab5f500f` and `origin/dc4-uplink` point at the same commits. DC4's commits are `4dddfb4b..HEAD`. The commits up to and including `4dddfb4b` are DC2's.

**Plan:** `docs/doperpowers/plans/2026-10-15-desk-dc4-uplink.md`. M1–M4 are each ticked as reviewed clean. The Decision Log records every decision and every ruling by the composite's writer. Outcomes & Retrospective is written.

## How it ran

The run used subagent-driven execution with one fresh `task-executor` per milestone and a `task-reviewer` at each milestone's end. A fix wave went back to the milestone's own executor. The whole-branch review used `doperpowers:reviewer-high`, and its findings went to one fresh fixer. The SDE ledger is in `.doperpowers/sde/2026-10-15-desk-dc4-uplink/progress.md`, and each milestone's executor report sits beside it in the same directory.

| Milestone | Code | Fix waves | Proved |
| --- | --- | --- | --- |
| M1: codes and a concurrent daemon | `98bd8a69` | 1 (busy-stream shutdown; canonical base64url) | DX1 parity with the hub's vectors; G4 |
| M2: enrollment and hub projects | `182eacca` | 2 (lost answer mid-body, former names per session, malformed hub fails closed, code off argv, argparse echo) | G1, stand-in and real hub (55/55 at MAWS `4d2c492f`) |
| M3: sync through the hub | `5f890398` | 2 (rejection state round-trips, cancellable uploads, projects leave the uplink, spent positions as tombstones; then a fully cancellable POST) | G2 (real hub 32/32 at MAWS `71083dd4`) |
| M4: archive, walk, docs, version | `dd6730d3` | 1 (symlink isolation, remote git policy, refresh `have`, version 7.155.0) | G3; G1–G4 walk 73/73 |
| Branch review (`high`) | `4d0dd34b` | 1 (P1: conversion races a mirror tick; P2: case-only rename, resend revives a refused writer, orphan at startup, stale metadata after re-join) | re-review: no material findings; walk 73/73 at MAWS `fa7f8e8d` |

## Contract traffic with the composite's writer

These were raised by this child and ruled by the writer:
- process rather than thread for the uplink;
- exactly-once delivery across the two processes;
- the code read from a prompt, never argv (composite `2bce24bb`);
- former names counted as self only for their own sessions;
- the derived nonce, `conflict` added to DX2's `rejected`, and spent positions as tombstones (composite `fcb07a5e`);
- the forgery cases split between the real browser path and a lying-hub stand-in, with no test hook in the hub;
- a repeated `hello` made idempotent (composite `b6cb686b`);
- SKILL.md deferred to a desk-wide skill update.

These were relayed down from the writer and folded in:
- the G1 amendment (MAWS `29294260`);
- canonical base64url (`91f839ee`, `e6bb0160`);
- DC3's M2 interfaces (`8711949a`);
- DC3's POST delivery rules;
- the three M3 rulings.

## Validation

At the last code commit:
- codes parity: 185 ok;
- uplink 95, hub 346, sync 90, archive 40 and bridge 81 assertions, all passing;
- shellcheck: clean;
- the full suite: 1723 of 1724. The one failure is the git-mirror "say lands within two seconds" bound, at load ~110. The final fixer's run of the same tree at load 70–100 passed 1724 of 1724.

The latency check, base against HEAD, interleaved, found identical per-tick CPU and git work on both. The base misses the bound just as often under the same load (11 of 48 runs at load ~130). So this is a load flake and not a slowdown; it is recorded in TECH-DEBT with a proposed fix. Throughout the run, the machine's load average was 100–450.

## Environmental friction routed around

- **git refusals.** The worktree-isolation guard refuses any git command it cannot verify stays in this worktree: `cd … &&` chains, git inside heredocs, `-C .`, and `git init` in a temp directory written in the command itself. Every git operation was rerun as plain `git -C <worktree>` commands. One micro-benchmark that needed a scratch git repository was abandoned rather than worked around, and a delegated executor did the measurement with test scripts instead.
- **Forced handbacks.** The harness forced six interim handbacks while children were still running. Each time the composite's writer resumed this controller.
- **Running the local hub.** The hub ran from temp copies of the MAWS tree. pnpm 11 needed `verifyDepsBeforeRun: false` in the copy's workspace file, and its options take no `--`.
- **One read-only git command in MAWS.** The final fixer ran a single read-only `git log` inside the MAWS worktree. Nothing changed.

## Residue

- **The sminos skill for the desk.** SKILL.md still describes a `remote` as a git mirror. Hub projects, the bridge and the web's controls need one eval-backed update after the children merge. The composite's writer holds this.
- **The suite's timing assertions under load.** Several assertions flake under heavy load, on the base as well. They are in TECH-DEBT with a proposed load-scaled bound, and are best handled together with a CI gate for the shell suites.
