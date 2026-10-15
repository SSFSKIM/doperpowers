# DC7 (the machine's controls): execution report, interim (2026-10-15)

Status: in progress. The harness forced this hand-back while M4's executor was still running its own background work (a live Resume check).

## Where it stands

- **M1, presence and the session plane.** Reviewed clean and ticked. It is proven against DC2's real `sminos bridge` child with a seeded cut, and against DC3's reviewed hub at `a190a6d8` with `step-end`. One Minor from review (scripted endpoint fidelity on a resync) was carried into M4.
- **M2, policy, requests, settlements and delivery outcomes.** Reviewed clean and ticked: `c71b751f`, fixes `f357a00a` and `526b9eb8`.
- **M3, the RPCs.** Reviewed clean and ticked: `99d8fd62`, `73c821fc`, `298254af`, fixes `4dc19fa7`, `74f078ea` and `3cd17348`. `test_rpcs.py` passed 30/30 against DC3's local hub.
- **M4.** Two commits have landed:
  - `f263bbd5`: Resume, the bridge-file sweep, and the fixture fix.
  - `69a9ad75`: CLAUDE.md and the 7.157.0 bump.

  The executor has not reported yet, and `tests/mods/live-resume-check.py` is untracked in the worktree. M4's task review, the final `high` branch review, Outcomes & Retrospective, and the PR all remain.
- **Merges:**
  - DC4 at `7252a5d7` (`9e857943`).
  - DC2 at `89c9f8da` (`0563b977`) and `5003ca2e` (`712f6af3`).
  - origin/main (`93d01f3f`, `1c2fe0be`).
- **Every contract ruling is in the plan's Decision Log.**

## Open with the composite's writer

How M3 handles a misfit decision. Today these are refused `bad-shape` after the claim, from the bridge's 400:
- a deny on an async question;
- an answer to a permission;
- an allow on a question;
- answer keys the request does not ask.

I proposed catching them at check 7, before the claim, still as `bad-shape`. That needs DX6 to list `bad-shape` among the daemon's codes. The ruling is pending.

## Tech debt

The suite's load flakes are covered by DC4's entry in `docs/doperpowers/TECH-DEBT.md`.

## Next

1. Take M4's report and review it.
2. Apply the misfit ruling.
3. Run the final `high` review over `git merge-base origin/main HEAD`..HEAD.
4. Write Outcomes & Retrospective.
5. Open the PR.

The ledger is `.doperpowers/sde/2026-10-15-desk-dc7-controls/progress.md`.
