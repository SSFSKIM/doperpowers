EXECUTION (gate passed) — name the mode in the gate comment.
Every claim of done carries EVIDENCE appropriate to the change — never
claim completion on reasoning alone:
- testable logic: TDD (doperpowers:test-driven-development) — failing
  test first. Green checks are what keep your PR self-merge-eligible.
- UI/visual changes: build + run it — verify the actual rendered
  behavior (E2E where the repo has it); write tests only where behavior
  is assertable without theater.
- config/docs/infra: the relevant check (build, lint, dry-run) passes.
Modes:
- DIRECT: the pre-spec is the plan — evidence discipline above, commit
  frequently, open the PR.
- EXECPLAN: the work needs the document to survive context death —
  multiple sequenced milestones, OR big-but-atomic work that cannot land
  halfway → doperpowers:execplan (the gate already served as its grill;
  author the ExecPlan from ticket + gate findings, execute to the letter).
Subagents (research, exploration, parallel fan-out) are yours to use as
the work warrants. writing-plans and subagent-driven-development are
interactive-session skills — never a daemon worker's; you execute your
own plan in this session.
