# The desk, DC2 — the bridge: controller report (interim, 2026-10-15)

Plan: `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md` (the living
record: Progress, Decision Log, Surprises, DX5 in Interfaces). SDE ledger:
`.doperpowers/sde/2026-10-15-arkho-desk-c2-bridge/progress.md` (gitignored), with
each milestone's executor report beside it (`task-N-report.md`).

## State at handback

This report was handed back early on the harness's demand, with M4's fix
wave still running. The run is **not finished**.

| Milestone | State | Commits |
| --- | --- | --- |
| M1 spine, local protocol (G1, DX5 v1) | reviewed clean | `fbd19b1a`, fixes `79bb122b`, `6ac34e14` |
| M2 control verbs, delivery (G2) | reviewed clean | `56619f3d`, fixes `75faba58`, `7842ae4e` |
| M3 requests, settlement (G2, G3), block-row | reviewed clean | `3a33efcd`, fixes `10f913d5`, `4b13cb9e` |
| M4 live export (G4), row notices and cut, walk, docs, version 7.154.0 | built `6d6aa211`; review needed fixes; fix wave 1 partly landed (`828ade6c`: post fence and leaking-test fix) | in progress |

Uncommitted in the worktree, and owned by M4's executor (agent
`aff91d1f151e942ee`, still running): change C (notices after `next()`, the
consumer emitting in disk order with release on a later notice) and the cut
seed. These touch `CLAUDE.md`, `hooks/mods/README.md`, `hooks/mods/bridge.tsx`,
`skills/sminos/scripts/sminos_bridge.py`, `tests/mods/bridge.test.ts`,
`tests/mods/live-walk-check.py`, and `tests/sminos/bridge_order.py`. The latest
instruction to it narrows the seed exclusion to loops that predate the module.
It also asks the executor to confirm that the module loads before the first
prompt row's `session.append` in a `--bg` job started with a prompt.

## Still to do

1. Finish M4 fix wave 1. That means:
   - commit C and the seed;
   - run both suites and prove `pgrep -f 'ctl.py supervisor'` is empty afterwards;
   - get one fully passing run of the committed live walk, plus the three earlier live checks;
   - report the largest flush-to-notice lag.
2. Re-review M4 by resuming task-reviewer `a7b969b4731dea386` with the fix package (`fix-base 6d6aa211`).
3. Fold M4's DX5 extension into the plan and tick M4. Send DX5 M4 to the composite's writer, who refreshes DX5 and relays it to DC7.
4. Run the whole-branch `high` review (doperpowers:review-code) and its fix loop.
5. Write Outcomes & Retrospective and open the PR. No `Closes` line: the ticket is a composite child, not a GitHub issue.

## Contract decisions sent to the composite's writer, all confirmed and folded

DX5 v1 and its M2/M3 extensions:
- the per-block streaming shape and `block-row`;
- DX4's raised/settled values;
- settlement from the engine's exact-id `tool_decision` telemetry record;
- the delivery dedup residual (at-least-once);
- §5 rows: steer refused when idle; interrupt `{turnId, stopped, running}`; model on the main loop with alias resolution; compact answering `queued`/`started`; `reply` always with `nextTurn`;
- row notices and the snapshot cut;
- readiness, and a later resync ending subscriptions;
- notices after the write with the consumer in disk order;
- the post fence;
- the seed rule.

## Test debt and residue candidates

- `tests/sminos/run-sminos-tests.sh` ≈ line 4838 ("at most once more: two frames in all") flakes. It is already logged by DC4 and not re-logged here.
- Plugin-validate baseline warnings: root `CLAUDE.md`, and `agents/codex/README.md` frontmatter.
- `tests/sminos/test-bridge-control.sh` kept-notification count can race the watcher. This was deferred Minor from M2.
- `$SMINOS_HOME/bridge/<id>.json` files accumulate. A sweep could come with DC7.
- `hooks/mods/bridge.tsx` is about 1,750 lines. `$` cannot cross files, so splitting it needs closures.
- The bridge's own compaction rows and the engine's reload line get no notice, so consumers receive them as unnamed rows.
- A `--bg` job starts in permission mode `auto` (2.1.300), so it rarely raises requests.
- Environment: 44 leaked stand-in processes from the control test were killed by the controller, and 77 more by M4's executor. The test is fixed in `828ade6c`.
