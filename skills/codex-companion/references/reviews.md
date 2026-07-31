# Reviews: `review` and `adversarial-review`

Both verbs run Codex's reviewer against local git state and print rendered
findings (or an explicit no-findings result) to stdout. Both record a job
(see references/jobs.md). Neither ever edits files.

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:$HOME/.claude/doperpowers/codex-companion/no-broker.sock" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" review \
      [--wait|--background] [--base <ref>] [--scope auto|working-tree|branch] [--model <m>] [--json] [--cwd <dir>]

`adversarial-review` takes the same flags plus trailing positional focus
text.

Target selection (shared by both):

- `--base <ref>` — branch review: the diff from `merge-base HEAD <ref>` to
  HEAD. This is the form for "review this branch against main".
- `--scope branch` — same, against the auto-detected default branch.
- `--scope working-tree` — uncommitted work (staged + unstaged + untracked).
- default (`auto`) — working-tree changes when present, otherwise the
  branch against the detected default branch.

`review` is Codex's native reviewer, deliberately non-steerable: it errors
on focus text and on staged-only/unstaged-only scopes. `--model` takes a
literal model name only — the `spark` alias is task-only; review forwards
the value un-normalized, so an alias reaches the app-server as an unknown
model. Left unset, the user's codex `config.toml` decides. There is no
`--effort` on reviews.

`adversarial-review` is the steerable challenge review: it questions the
chosen design, tradeoffs, and hidden assumptions rather than only hunting
defects. The trailing focus text is a lens, e.g.

    … adversarial-review --base main challenge whether this caching and retry design is right
    … adversarial-review --background look for race conditions and question the chosen approach

For a multi-lens sweep of a big diff, launch several `adversarial-review`
runs in parallel background Bash calls, one lens each — and give each run
its own state root (e.g. `CLAUDE_PLUGIN_DATA=…/codex-companion-lens2`):
the job ledger is an unlocked read-modify-write of one `state.json`, so
concurrent runs sharing a root can silently drop each other's job records.

Working-tree and adversarial reviews embed the contents of untracked
files — following symlinks — into the review prompt before any sandbox
applies. Don't run them on a checkout you don't trust.

`--json` prints the structured result object instead of rendered text —
use it when a program (not a human) consumes the findings.

Foreground (`--wait`) suits small diffs; anything multi-file belongs in a
background Bash call (see references/jobs.md for the mechanics). If codex
may be missing or unauthenticated, run the `setup` verb first — it
diagnoses install and auth state.
