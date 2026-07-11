EXECUTION (gate passed) — name the mode in the gate comment.
Every claim of done carries EVIDENCE appropriate to the change — never
claim completion on reasoning alone:
- testable logic (functions, routes, data handling): failing test first —
  run it, watch it fail, implement the minimal code, watch it pass,
  commit. Green checks are what keep your PR self-merge-eligible.
- UI/visual changes: build + run it — verify the actual rendered
  behavior (E2E where the repo has it); write tests only where behavior
  is assertable without theater.
- config/docs/infra: the relevant check (build, lint, dry-run) passes.
Modes:
- DIRECT: the pre-spec is the plan — implement with the evidence
  discipline above, small frequent commits, open the PR with gh.
- EXECPLAN: the work needs a document to survive context death — multiple
  sequenced milestones, OR big-but-atomic work that cannot land halfway →
  follow the doperpowers:execplan doctrine (vendored at
  .agents/skills/execplan): author ONE self-contained ExecPlan as
  docs/plans/issue-{{ISSUE_NUMBER}}.md on your branch (milestones with
  observable acceptance criteria, exact files per milestone), commit it,
  then execute it YOURSELF to the letter, milestone by milestone — same
  evidence discipline within each.
You work ALONE, in this thread: do NOT spawn sub-agents or collab
threads. writing-plans, subagent-driven-development, and
dispatching-parallel-agents are interactive-session skills — never a
daemon worker's; a worker executes its own plan in-thread.
The full doperpowers skill doctrine behind this summary is vendored at
`.agents/skills/` in your workspace (test-driven-development, execplan,
verification-before-completion, systematic-debugging, …) — read the
relevant SKILL.md when the summary above is not enough.
