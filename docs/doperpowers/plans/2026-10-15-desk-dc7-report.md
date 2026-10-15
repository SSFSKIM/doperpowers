# DC7 (the machine's controls): execution report (2026-10-15)

Status: DONE. The plan is `docs/doperpowers/plans/2026-10-15-desk-dc7-controls.md`, and the composite is MAWS `docs/doperpowers/specs/2026-10-15-desk-design.md` (branch `smns-erb`). Branch `worktree-agent-ab2de4f299f415dbf`, at version 7.157.0 over main's 7.156.1.

## What was built

The daemon side of the desk:

- **Session plane** (`skills/sminos/scripts/sminos_plane.py`).
  - Presence comes from the engine's records, within 1 s.
  - DX4 subscriptions join transcript rows with the bridge's stream in disk order, using DX5's seeded cut and its row notices.
  - Snapshots, `rows`, `diff`, `step-end`, and discontinuity are all served.
  - After a disconnect, a new stream publishes null presence for sessions that ended meanwhile, cut off by a watermark the hub has accepted.
- **Policy** (`sminos_policy.py`, `sminos daemon policy`).
  - Read-only and the permission ceiling are configurable; an unreadable policy file makes the machine read-only.
  - The read-only guard sits at the one delivery boundary, `deliver_next`.
- **Requests, settlements, and delivery outcomes** (`sminos_requests.py`, `sminos_outcomes.py`).
  - DX4 `raised` and `settled` carry codes.
  - The complete pending set waits for the bridges' first snapshots.
  - A closed terminal session gets `recorded`, an unanswered push gets `uncertain`, and a read-only machine gets `refused-read-only`.
- **RPCs** (`sminos_rpc.py`).
  - Refusals run in this order: code, binding, ledger, freshness, policy, fit and digest, then the session's kind.
  - An at-most-once ledger guards execution and fails closed when unreadable.
  - Reconciliation works from each action's own trace.
  - Each RPC executes through the bridge or through `sminos`.
  - Resume is attributed to its own launch.
- **Bridge, additive changes** (`hooks/mods/bridge.tsx`, `sminos_bridge.py`, after DC2 closed).
  - `raised.toolUseId` names the ask mod's outer call.
  - The 409s carry who-won fields.

## Milestones and review

| Milestone | Commits | Review |
| --- | --- | --- |
| M1 | `19b50561`; fixes `3aa64d21`..`d51c6956`; real-child wave `a7b38ace`, `4bf53309` | clean |
| M2 | `c71b751f`; fixes `f357a00a`, `526b9eb8` | clean |
| M3 | `99d8fd62`, `73c821fc`, `298254af`; fixes `4dc19fa7`, `74f078ea`, `3cd17348` | clean |
| M4 | `f263bbd5`, `69a9ad75`, `4bba978a`, `c317d37c`, `762f780a`; fixes `bd84f1c9`, `b870a9c0` | clean |
| Final `high` review | 4 P2 fixed in `3e89aa1e`, `8304923c`, `5dfa5150`, `da98a3ff` | re-review: correct |

Merges:
- DC4 at `7252a5d7`.
- DC2 at `89c9f8da` and `5003ca2e`.
- `origin/main` three times, the last at 7.156.1 (`6ee5293c`).

Every contract ruling the composite's writer made during execution is in the plan's Decision Log.

## Evidence on the final head

Load was 85–160 throughout.

- **Full sminos suite** (`tests/sminos/run-sminos-tests.sh`, on `da98a3ff`): 1740/1742. The two failures:
  - "the say lands within two seconds" is the git-mirror push bound. It also fails on main and is listed in TECH-DEBT.md.
  - "the terminal won, as a field" was a race in DC7's own assertion. Under load the watcher settles the request first, so the refusal is "already settled". Fixed in `d7bac20e`; `test-bridge-requests.sh` then passed 75/75.
- **Mods suite** (`tests/mods/run-mods-tests.sh`): 298 pass, 0 fail, plus the ask search checks.
- **Against DC3's local hub:** M4's walk passed 17/17 (MAWS `349f2512`, G1–G4), and `test_rpcs.py` passed 30/30.
- **Live Resume check** against claude 2.1.301 under a temporary HOME: 5/5.

## Rests on a stand-in

These Resume behaviours were proven only against a stand-in for `claude`, not the live engine:
- two Resumes at once;
- delivery after Resume;
- claim reconciliation;
- the seat cases.

## Friction routed around

- The `with-slot.sh` load wrapper was unavailable in worktree sessions. The composite's writer waived it, and heavy runs went one at a time.
- My guard refuses any command that overrides HOME. With the composite's writer's agreement, the mods suite ran as the script stands: it touches neither sminos nor the hook, and stages its own copy under mktemp.

## Tech debt logged

All in `docs/doperpowers/TECH-DEBT.md`:
- the suite's load flakes;
- the uplink tick-loop candidate flake;
- a compact's nonce lost after the ledger is repaired at runtime;
- a non-`OSError` from the claim write.
