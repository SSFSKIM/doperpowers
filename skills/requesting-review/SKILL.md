---
name: requesting-review
description: Use when work needs an independent quality review — a second-opinion code review of a branch or working tree, an adversarial challenge of a design or plan diff, or a multi-reviewer panel on a big diff.
---

# Requesting a Review

Independent review of local git state, served by the Codex runtime that the
sibling doperpowers:codex-companion skill vendors. `<skill-base>` is THIS
skill's base directory (printed when the skill loads); the runtime sits
beside it at `<skill-base>/../codex-companion` — both install from the same
plugin, so that layout is guaranteed. Every invocation carries the shared
env contract (mirrored from codex-companion's SKILL.md — a change to either
copy updates both):

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
    CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:$HOME/.claude/doperpowers/codex-companion/no-broker.sock" \
      node "<skill-base>/../codex-companion/runtime/scripts/codex-companion.mjs" <verb> [flags…]

`CLAUDE_PLUGIN_DATA` pins job state somewhere durable; the session id scopes
job reads to this session; the dead endpoint forces the per-call app-server
path so nothing detaches and outlives the run. The `workflow` verb ignores
the endpoint (its workers always spawn their own servers) — carrying it is
harmless. On a wrapped run (`with-effort.mjs` below) leave the endpoint OFF:
the wrapper provides its own live one.

## Choosing the shape

Three shapes, chosen by what the review is for:

- **Single native review** — the default for a focused diff. Codex's native
  reviewer, deliberately non-steerable: it errors on focus text.
- **The code-review panel** — for a big diff: as a rule of thumb, 20+ files
  or a couple thousand changed lines. One reviewer's recall thins at that
  scale — on the PR752 benchmark (22 files, +2,101 lines) the best single
  run found 10 of 13 confirmed defects while seven runs' union found all
  13 — so the panel runs one lens-free sweep, up to five scalpel lenses a
  deriver reads off the diff, and one binding verifier over the merged
  pool. Expect ~8 workers and ~20 minutes. A smaller diff whose weight
  concentrates on ground you consider high-stakes (declared risk surfaces,
  auth, money, data deletion) can be worth the panel too — the threshold
  is a default, not a gate.
- **Adversarial review** — when the question is the design rather than
  defects: it challenges the chosen approach, tradeoffs, and hidden
  assumptions. Trailing positional text is its focus lens, e.g.
  `… adversarial-review --base main challenge whether this caching design is right`.

Target selection (all shapes): `--base <ref>` reviews the diff from
`merge-base HEAD <ref>` to HEAD — the form for "review this branch against
main". `--scope working-tree` reviews uncommitted work; `--scope branch`
uses the auto-detected default branch; the default (`auto`) is working-tree
changes when present, otherwise the branch.

## Single and adversarial invocations

    … codex-companion.mjs review [--wait|--background] [--base <ref>] [--scope auto|working-tree|branch] [--model <m>] [--json] [--cwd <dir>]

`adversarial-review` takes the same flags plus the trailing focus text.
`--model` is a literal model name, forwarded un-normalized; unset, the
user's codex config.toml decides. The review protocol has no effort field —
to choose reasoning effort per run, wrap the invocation in
`<skill-base>/../codex-companion/scripts/with-effort.mjs`, which serves the
verb a private app-server carrying the override:

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
      node "<skill-base>/../codex-companion/scripts/with-effort.mjs" --effort xhigh -- \
      review --base main --wait

Everything after `--` is ordinary verb arguments; repeatable `-c key=value`
before `--` passes any other codex config override.

Findings are stdout-only; stderr streams per-command progress that dwarfs
the verdict, so always redirect it (`2> <scratch>.events.log`) and read
stdout. Keep the file: errors land there, checked on a nonzero exit. The
runtime fails closed when the reviewer's own fs sandbox was broken during
the run (a hollow "clean" is worse than no verdict) — that surfaces as a
nonzero exit naming the sandbox, and retrying it is pointless until the
host is fixed. Foreground `--wait` suits small diffs; anything multi-file
belongs in a background Bash call. Working-tree and adversarial reviews
embed untracked-file contents (following symlinks) into the prompt — don't
run them on a checkout you don't trust. If codex may be missing or
unauthenticated, the `setup` verb diagnoses both.

## The panel invocation

    … codex-companion.mjs workflow \
      --script "<skill-base>/../codex-companion/workflows/code-review.mjs" \
      --args '{"base":"origin/main"}' [--cwd <repo>] 2> <scratch>.events.log

`base` is the only required arg. Optional args: `lenses` (an array replacing
the derived set), `finderModel`/`finderEffort` (default `gpt-5.6-sol`/`xhigh`),
`verifierModel`/`verifierEffort` (default `gpt-5.6-sol`/`high`). It is ONE
foreground process — run it in a background Bash call and keep the handle.

Stdout is exactly one JSON object `{runId, result, agents, durationMs}`;
`result` is `{verdict, findings, coverage, lenses, explanation}`. `verdict`
`correct`/`incorrect` is the panel's answer — `findings` carries only
verifier-confirmed items (`{id, priority, title, file, lines, comment,
sources}`, priority-sorted), so `incorrect` means confirmed defects.
`interrupted` means no verdict can be asserted — a lane was lost or the
reviewed head moved mid-run (the panel pins merge-base AND HEAD at start
and re-resolves at assembly). Treat `interrupted` as an engine failure:
retry once, then treat the round as an outage. Don't commit to the branch
under review while a panel round is in flight — that is what moves the
head. `watch <run-id>` (same runtime) renders live progress from any
terminal.
