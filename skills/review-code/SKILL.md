---
name: review-code
description: Use when a committed change needs an independent code review — cross-model correctness review of a branch, routed by effort level to a registered reviewer or a multi-lens panel.
---

# Review Code

Registered reviewers (read-only, the codex review rubric on GPT through the
gateway) for the single-reviewer levels, and one workflow script for the panel
levels. `<skill-base>` is this skill's directory, printed when it loads.

## 1. Pin the target and pick the level

```bash
base=main; mb=$(git merge-base "$base" HEAD); head=$(git rev-parse HEAD)
git diff --stat "$mb" "$head" | tail -1
```

The review covers the committed range `mb..head`; commit uncommitted work first
(a work-in-progress commit is fine). Route by effort:

| Level | What runs | When |
|---|---|---|
| low | `doperpowers:reviewer-low` | a small, low-stakes diff |
| medium | `doperpowers:reviewer-medium` | the default for a focused diff |
| high | `doperpowers:reviewer-high` | a focused diff whose stakes warrant the frontier model |
| xhigh | panel workflow: derived lenses, parallel reviewers, one verifier | ~20+ files or a couple thousand changed lines — one reviewer's recall thins at that scale |
| max | the panel workflow on frontier models | the largest or highest-stakes ranges |

An explicitly named level always wins. With none named: medium for a focused
diff, xhigh once the diff is panel-sized. Models and efforts per level are
pinned on the agents and in the script; you never choose them.

## 2. Run it

**low / medium / high** — dispatch the level's agent through the Agent tool
with this brief (works from any session or subagent):

> Review the code changes against the base branch '`<base>`'. The merge base
> commit for this comparison is `<mb>`; the reviewed head is `<head>`. Run
> `git diff <mb> <head>` to inspect the changes relative to `<base>`. Provide
> prioritized, actionable findings.

Append `Lens for this review: …` (two plain sentences at most) to point it at
one structural risk surface. Its report is the findings: a `## Findings` list
and a `## Verdict`.

**xhigh / max** — the panel, from the main session only (subagents have no
Workflow tool; a subagent that needs a panel hands the pinned range and level
up to its main session):

```
Workflow({ scriptPath: "<skill-base>/workflows/code-review.js",
           args: { level: "<level>", base: "<base>", baseCommit: "<mb>", headCommit: "<head>" } })
```

It runs in the background; keep working until the result lands. The result is
`{verdict, findings, coverage, explanation, …}` with `verdict` one of `correct`,
`incorrect`, `interrupted` — [references/panel.md](references/panel.md) has the
full contract, the optional args (`repo` for a worktree, `lenses`), the
isolation guarantee, and how to work with the findings. Don't commit to the
branch under review while a run is in flight; when it returns, re-resolve
`mb` and `head`, and read a moved pin as `interrupted`.

For uncommitted work, dispatch a reviewer agent on the working tree instead
(staged, unstaged, and untracked files against HEAD `<head>`), and don't edit
under it: a working-tree review describes whatever the tree holds while it
runs.
