# Reviews: `review` and `adversarial-review`

Both verbs run Codex's reviewer against local git state and print rendered
findings (or an explicit no-findings result) to stdout. Both record a job
(see references/jobs.md). Neither ever edits files.

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
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

Route by diff size: on a big diff — as a rule of thumb, 20+ files or a
couple thousand changed lines — run the `workflow` verb's code-review
panel instead of a single `review`. One reviewer's recall thins at that
scale; the panel (diff-derived lenses + a lens-free sweep + a binding
verifier) surfaced over twice the confirmed findings of a plain
single-worker sweep on the same 85-file PR. Invocation and output
contract: references/workflows.md. Expect ~8 workers and ~20 minutes;
smaller, focused diffs stay with plain `review`.

`review` is Codex's native reviewer, deliberately non-steerable: it errors
on focus text and on staged-only/unstaged-only scopes. `--model` takes a
literal model name only ; review forwards the value un-normalized, so an 
alias reaches the app-server as an unknown model. Left unset, the user's 
codex `config.toml` decides.

Reasoning effort: the review protocol has no effort field — a review runs
at whatever `model_reasoning_effort` the serving app-server process was
configured with (the user's global config.toml default). To choose it
per-run, wrap the invocation in `<skill-base>/scripts/with-effort.mjs`,
which serves the verb a private app-server started with the override:

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
      node "<skill-base>/scripts/with-effort.mjs" --effort medium -- \
      review --base main --wait

Everything after `--` is ordinary verb arguments (works for
`adversarial-review` too; `task` has a native `--effort` flag and doesn't
need it). Repeatable `-c key=value` before `--` passes any other codex
config override the same way. Don't set
`CODEX_COMPANION_APP_SERVER_ENDPOINT` yourself on a wrapped run — the
wrapper provides its own live endpoint, and its per-connection app-servers
die with the run, so the broker kill-switch isn't needed there either.

`adversarial-review` is the steerable challenge review: it questions the
chosen design, tradeoffs, and hidden assumptions rather than only hunting
defects. The trailing focus text is a lens, e.g.

    … adversarial-review --base main challenge whether this caching and retry design is right
    … adversarial-review --background look for race conditions and question the chosen approach

For a multi-lens sweep of a big diff, launch several `adversarial-review`
runs in parallel background Bash calls, one lens each. Concurrent runs may
share one state root: every ledger writer takes the state lock, so parallel
runs no longer drop each other's job records.

Working-tree and adversarial reviews embed the contents of untracked
files — following symlinks — into the review prompt before any sandbox
applies. Don't run them on a checkout you don't trust.

`--json` prints the structured result object instead of rendered text.

Foreground (`--wait`) suits small diffs; anything multi-file belongs in a
background Bash call (see references/jobs.md for the mechanics). Either
way, add `2> <scratch>.events.log`: findings are stdout-only, and the
redirect keeps the streamed per-command progress — and its truncated
copy of the verdict — out of what you read back. On a wrapped run the
same redirect also catches the private app-server's noise. If codex
may be missing or unauthenticated, run the `setup` verb first — it
diagnoses install and auth state.
