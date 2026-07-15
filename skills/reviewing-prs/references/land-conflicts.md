# Land worker — conflict-resolution procedure

Opened on demand by a land worker whose PR GitHub reports unmergeable (or
whose dry-run merge attempt hit conflicts). Your spawn prompt carries the
INSTANCE facts — the base branch, the head branch, the detached-HEAD push
form, the land mode, the risk-surface manifest; this file carries only the
PROCEDURE and grants no authority beyond your prompt's.

1. In the worktree: `git fetch origin <base> <head>`, then
   `git merge origin/<base>`. NEVER rebase, NEVER force-push — the
   direction is always base INTO branch (a landing squash makes branch
   history irrelevant; a rebase would demand force-pushing a branch an
   implement worker may still hold).

2. Resolve ONLY the conflict hunks — anything beyond them is unreviewed
   code entering the branch unseen. Write the minimum that reconciles
   both sides.

3. Judge your RESOLUTION DELTA — the conflicted files and the lines you
   hand-wrote resolving them — against the LAND BOUNDS, which are stricter
   than the review loop's self-merge tier because a resolution delta is
   unreviewed by construction:
   - at most 50 hand-resolved lines across at most 3 conflicted files, AND
   - ZERO conflicted files on any RISK SURFACE: any path/pattern in the
     risk-surface manifest at the bottom of your prompt, and ALWAYS,
     manifest or not: CI/workflows, auth/security, migrations/schema,
     release/versioning, and the manifest files themselves
     (.doperpowers/risk-surfaces.md, .doperpowers/repo-facts.md).

4. Within bounds, LIVE mode → commit the merge, push
   (`git push origin HEAD:<head>` — you are on a detached HEAD), then land
   via your prompt's NATIVE FIRST path (checks re-run on the new head; arm
   auto-merge and watch bounded). The trail comment MUST name the delta:
   each conflicted file and what you chose. The push may demote
   confident-ready (synchronize automation) — correct and irrelevant to
   you: your authority is the human's approval, not the label. One edge:
   if the repo's only landing method is rebase-merge, your resolution
   merge commit may make that merge impossible — a refused merge after
   your push is a PARK, never an improvisation.
   Within bounds, DRY-RUN mode → never push: `git merge --abort` after the
   analysis and state in the one trail comment what a live run would have
   done (conflicted files, delta size, within bounds).

5. Out of bounds, or a conflict you cannot resolve mechanically:
   - LIVE mode → PARK per your prompt's PARK section, with the resolution
     kept as a LOCAL commit in the worktree (never push an out-of-bounds
     resolution — it is unreviewed code). Name the conflicted files and
     delta size in the park comment.
   - DRY-RUN mode → your prompt's dry-run contract stands: NO board
     writes, no pushes — `git merge --abort` and state in the one trail
     comment what a live run would have done (out of bounds: these files,
     this delta size, would park needs-human).
