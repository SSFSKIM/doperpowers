---
name: review-code
description: Use when a committed change needs an independent code review — cross-model correctness review of a branch, routed by effort level to a registered reviewer or a multi-lens panel.
---

# Review Code

`<skill-base>` is this skill's directory, printed when it loads.

## 1. Pin the target and pick the level

```bash
base=main; mb=$(git merge-base "$base" HEAD); head=$(git rev-parse HEAD)
git diff --stat "$mb" "$head" | tail -1
```

The review covers the committed range `mb..head`; commit uncommitted work first
(a work-in-progress commit is fine).

| Level | What runs | When |
|---|---|---|
| low | `doperpowers:reviewer-low` | a small, low-stakes diff |
| medium | `doperpowers:reviewer-medium` | the default for a focused diff |
| high | `doperpowers:reviewer-high` | a focused diff whose stakes warrant the frontier model |
| xhigh | the panel: derived lenses, parallel reviewers, one verifier | ~20+ files or a couple thousand changed lines |
| max | the panel on frontier models | the largest or highest-stakes ranges |

An explicitly named level always wins; with none named, medium, or xhigh once
the diff is panel-sized. Models and efforts are pinned per level; you never
choose them.

## 2. Run it

**low / medium / high** — dispatch the level's agent through the Agent tool
(from any session or subagent) with this brief:

> Review the code changes against the base branch '`<base>`'. The merge base
> commit for this comparison is `<mb>`; the reviewed head is `<head>`. Run
> `git diff <mb> <head>` to inspect the changes relative to `<base>`. Provide
> prioritized, actionable findings.

Append `Lens for this review: …` (two plain sentences at most) to point it at
one structural risk surface.

**xhigh / max** — the panel, from the main session only (subagents have no
Workflow tool; a subagent hands the pinned range and level up):

```
Workflow({ scriptPath: "<skill-base>/workflows/code-review.js",
           args: { level: "<level>", base: "<base>", baseCommit: "<mb>", headCommit: "<head>" } })
```

It runs in the background. [references/panel.md](references/panel.md) has the
result contract, the optional args (`repo` for a worktree, `lenses`), and the
isolation guarantee. Don't commit to the branch under review while a run is
in flight; when it returns, re-resolve `mb` and `head`, and read a moved pin as
`interrupted`.

For uncommitted work, dispatch a reviewer agent on the working tree instead
(staged, unstaged, and untracked against HEAD `<head>`), and don't edit under
it.

Working with the findings, at any level: references/panel.md, last section.
