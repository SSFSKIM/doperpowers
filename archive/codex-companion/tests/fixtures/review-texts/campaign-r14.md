# Codex Review

Target: branch diff against origin/main

The lane scheduler can incorrectly consume destination capacity during handoffs, and scale-review dispatch violates both engine-routing and commit-availability requirements in supported scenarios. These defects can delay work or prevent the intended review from running correctly.

Full review comments:

- [P1] Require the worker role to match the charged lane — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/e1-lane-split/skills/implementing/scripts/implement-dispatch.sh:169-170
  When an Implementer escalates to `ready-for-architect` (or an Architect hands off to `ready-for-implementer`) while its daemon still reports `working`, this state-only test charges that source-lane worker to the destination lane. With the default architect cap of 1, one live Implementer handoff blocks every unrelated Architect until finalization or stall retirement, potentially 45 minutes, even though `docs/doperpowers/specs/2026-07-30-implement-lane-split-design.md:196-201` defines lane crossing as releasing the slot. Require both the persisted worker role and current ticket state to match the charged lane.

- [P2] Honor engine labels on scale-review epics — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/e1-lane-split/skills/reviewing-prs/scripts/review-dispatch.sh:439-439
  When an in-review epic has `engine:claude` or `engine:codex`, `dispatch_epic` ignores the ticket label and always uses `WORKER_ENGINE` or the codex default. Scale review is a QAgent route, which `docs/doperpowers/specs/2026-07-30-implement-lane-split-design.md:104-114` explicitly says must honor per-ticket engine overrides, so the requested experiment runs through the wrong model route. Carry the epic's engine label out of the board selector and let it override the environment.

- [P2] Fetch child PR heads before deleted-branch scale review — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/e1-lane-split/skills/reviewing-prs/scripts/review-dispatch.sh:466-466
  When the closure package records original child PR base/head SHAs and those children were squash- or rebase-merged with their branches deleted, fetching only the default branch does not fetch the head objects because they are not ancestors of that branch. In a fresh clone the prompt's required detach at each named head therefore fails, preventing the scale review. Fetch the package's child PR refs or head SHAs before dispatching the reviewer.
