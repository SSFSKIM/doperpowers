EXECUTION (gate passed) — name the mode in the gate comment:
- DIRECT: the pre-spec is the plan — strict TDD: for each behavior write
  the FAILING test first, run it and watch it fail, implement the minimal
  code, watch it pass, commit. Small, frequent commits. Open the PR with gh.
- PLAN: 2+ milestones, or enough files/design sequencing that a fresh
  session would need a document to survive context death → author a plan
  file first (docs/plans/issue-{{ISSUE_NUMBER}}.md on your branch:
  milestones with observable acceptance criteria, exact files per
  milestone), commit it, then execute it to the letter milestone by
  milestone — same TDD discipline within each.
The full doperpowers skill doctrine behind this summary is vendored at
`.agents/skills/` in your workspace (test-driven-development,
writing-plans, verification-before-completion, systematic-debugging, …) —
read the relevant SKILL.md when the summary above is not enough.
