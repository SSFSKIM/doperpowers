# desk-open-fast — execution report (interim, 2026-10-20)

Status: in progress. The harness forced this hand-back while M2's executor
was still running. Resume the plan-executor with SendMessage: its state is
in the spec's Progress, its Decision Log, and the SDE ledger at
`.doperpowers/sde/2026-10-20-desk-open-fast-design/progress.md`, which is
gitignored and lives in this worktree.

## Where the plan stands

- M1 (sminos instruments: open line, reference consumer, inventory, fixtures,
  HTTP/1.1 stand-in, pause proxy): reviewed clean after three fix rounds.
  Commits 9bd55c49 (sminos 1.2.2), f106af71, b66e4d8f, c762b8d7.
- M4 (MAWS hub, reply chain decoupled, plus a fourth change against the
  periodic 503): reviewed clean after one fix round. MAWS PR #85, merged as
  e94098c9 and deployed 09:34:39Z.
- M3 (MAWS web, carried block kept across a reconnect): reviewed clean. §9
  was amended so that a named block keeps its drawn text. MAWS PR #86, merged
  as c26b74cc and deployed 10:54:34Z. The owner's refresh of every desk tab
  and PWA window is pending; the coordinator confirms it.
- main merged into the branch at 56b51fb8: main is at sminos 1.2.3, this
  branch at 1.2.4.
- M2 (bench_open.py, bench_scale.py opens): executing. Its executor is
  `a4d9bac73dcd13283`, base 56b51fb8, report
  `.doperpowers/sde/2026-10-20-desk-open-fast-design/task-2-report.md`. It
  will bump sminos to 1.2.5.
- M5–M9: not started. M5 needs the owner's client refresh before it rolls,
  not before it is built. M5 also carries the reference consumer's amendment
  to match amended §9, plus a fixture case where the drawn text differs from
  the carried copy, which needs a test-only MAWS follow-up copying the
  fixture.

## Residue so far

- The web rows store's `older()` (`apps/desk-web/src/depth/source/desk-transcript.ts`)
  does not dedupe within a page. A row a page carries twice is held twice,
  and the duplicate feeds rebuilds, `merged` and `landing`.
- After M8, a reconnect during an unnamed block larger than 65,536
  characters draws only its tail until the row lands. A web rule that
  splices the tail onto overlapping drawn text would fix it.
- The periodic 503's mechanism is to be confirmed after deploy. Look for
  `run-failed` with `Subrequest depth limit exceeded` in the hub's
  observability.
