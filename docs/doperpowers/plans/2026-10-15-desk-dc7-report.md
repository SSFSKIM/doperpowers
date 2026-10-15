# DC7 (the machine's controls): execution report, interim (2026-10-15)

Status: in progress. Handed back while M1's fix wave was still running.

## Where it stands

- Branch `worktree-agent-ab2de4f299f415dbf`: DC2's branch at `664e4bd8` merged with DC4's at `7252a5d7` (merge `9e857943`; the one conflict, the tail of `run-sminos-tests.sh`, keeps both sides).
- Pre-flight `5227ff12`: parent pin is blob `6c8015ef` at MAWS `edf9dea7`.
- M1 executed at `19b50561` (`sminos_plane.py`, uplink seams, `tests/sminos/test_session_plane.py`, `fake_session.py`). Its suite passed 23/23 and the full sminos suite passed 1726 assertions.
- M1's task review found three Important issues:
  - Blocking bridge probes break the 1 s presence bound. Sent to the fix wave.
  - A cached process identity survives PID reuse. Sent to the fix wave.
  - A null cut lets a snapshot overlap. Taken to the composite's writer, who chose option (a): the producer seeds the cut. DC2 builds the seed in its M4.
- M1's fix wave is running on M1's executor, with these items:
  1. Adopt the disk-order rule (composite `cd2667d8`).
  2. Move presence probes off the uplink thread.
  3. PID identity: invalidate the cache on observed death, and revalidate.
  4. Confirm the ceiling is the settings' `defaultMode`.
  5. After the fix, rerun the uplink walks against DC3's real local hub (MAWS `f22e0839`) from a temporary copy, run directly and serially (the composite's writer waived the load wrapper).
- The fix wave has landed in three commits. The executor's own report on them, with the local-hub results, has not arrived yet:
  - `3aa64d21`: disk order, presence probes off the uplink thread, and PID identity.
  - `3ade2b72`: the uplink tests run against DC3's local hub through `DESK_HUB`.
  - `80fa84a0`: DX4 `step-end` (composite `34ee27ca`).
- Decisions folded into the plan's Decision Log: `26155809`, `f4b699bc`, `12b0387a`.

## Next

1. Take M1's fix report and re-review it with the M1 reviewer, using a fix package from `f4b699bc` (or the HEAD the fix lands on).
2. Once clean, tick M1.
3. When DC2's M4 commits, merge it, switch the scripted endpoint to a seeded cut, and prove M1 against the real child.
4. Then M2, M3 and M4, the final `high` review, and the PR.

The ledger is in `.doperpowers/sde/2026-10-15-desk-dc7-controls/progress.md`.
