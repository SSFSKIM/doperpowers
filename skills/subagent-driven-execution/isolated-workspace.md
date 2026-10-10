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

**Manual fallback** (no native tool): `git worktree add
.claude/worktrees/<branch> -b <branch>` at the project root, and confirm
`.claude/worktrees/` is gitignored first — add and commit the ignore line if
not. That directory is the only location the harness treats as its own: a
worktree anywhere else (a sibling directory, `.worktrees/`) makes every
later `EnterWorktree` into it a permission prompt that no allow rule, hook,
or classifier can answer, because entering it relocates the session's
permission root. A sandbox that denies the
add: say so and work in place. Run the project's setup and its test suite
before the first task, so a failure later is yours.

**Clean-checkout acceptance.** A step that proves a fresh install works by
cloning or `git clean`ing the workspace destroys the ledger under
`.doperpowers/sde/`, which is gitignored: run it in a second directory, or
copy the ledger out first.

**At finish.** Write the spec's `## Outcomes & Retrospective` entry and
commit it on the branch, then integrate the way the human partner wants —
merge, PR, or leave the branch. A branch whose spec, Decision Log, or
ledger cite commit SHAs as evidence merges — the base branch into it while
it runs, itself with `--no-ff` at the end — rather than rebases: a rebase
rewrites every cited SHA and leaves intermediate commits that may not
build. Rebase a branch whose record cites nothing, or record the old-to-new
mapping for every cited range when you must. Remove only a worktree you created (one
under `.claude/worktrees/`, `.worktrees/` or `worktrees/`), from outside it, and only after the
merge is confirmed; a harness-owned workspace is left in place or exited
through the harness's own tool. A removal refused for
`modified or untracked files` means those files exist nowhere else: never
`--force` it — show `git status` and let the human partner choose commit,
move, or delete.
