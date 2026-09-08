# Isolated workspace

Execution runs on its own branch in its own checkout so the human partner's
working tree and parallel work stay untouched. The facts below are the ones a
session cannot derive on its own.

**Check before creating.** `git rev-parse --git-dir` differing from
`--git-common-dir` means you are already in a linked worktree (or a
submodule — `git rev-parse --show-superproject-working-tree` prints a path
for a submodule). Already isolated: use it, never nest another.

**Native tool first.** If the harness has a worktree tool — `EnterWorktree`,
a `--worktree` flag, a `/worktree` command — use it. Running
`git worktree add` beside a native tool was the observed failure: it creates
a workspace the harness cannot see, follow, or clean up (validated 50/50
runs when the preference was stated explicitly). Ask before creating one
unless the human partner's instructions already state a preference.

**Manual fallback** (no native tool): `git worktree add .worktrees/<branch>
-b <branch>` at the project root, and confirm `.worktrees/` is gitignored
first — add and commit the ignore line if not. A sandbox that denies the
add: say so and work in place. Run the project's setup and its test suite
before the first task, so a failure later is yours.

**At finish.** Write the spec's `## Outcomes & Retrospective` entry and
commit it on the branch, then integrate the way the human partner wants —
merge, PR, or leave the branch. Remove only a worktree you created (one
under `.worktrees/` or `worktrees/`), from outside it, and only after the
merge is confirmed; a harness-owned workspace is left in place or exited
through the harness's own tool. A removal refused for
`modified or untracked files` means those files exist nowhere else: never
`--force` it — show `git status` and let the human partner choose commit,
move, or delete.
