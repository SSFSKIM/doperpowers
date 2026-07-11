REVIEW ENGINE — the native Codex correctness + compliance review. The
REVIEW CRITERIA below are identical for both worker species; what differs
is who runs the engine:

If YOU are a Codex worker, you ARE the native engine: perform the review
IN-THREAD, yourself. Do NOT nest a second `codex exec` — codex-in-codex is
structurally broken under the worker sandbox (the nested process cannot
apply its own seatbelt profile: `sandbox-exec: sandbox_apply: Operation
not permitted`; nor reach the OS keychain for TLS trust), and the
work-alone rule forbids nested agents regardless. Run the diff command
from the criteria, read any surrounding files you need, and produce the
findings yourself.

If you are a Claude worker, call the engine via the COOKBOOK pattern
(plain `codex exec` with the criteria as its stdin prompt), from the
worktree root (`codex exec` has no -C flag; cd there first). Your call is
not nested, so it needs no special environment. DO NOT use the `codex exec
review` subcommand with a target flag: `--base`, `--commit`, and
`--uncommitted` each hard-conflict with a custom PROMPT at the CLI parser
(exit 2, no output) — instruct the diff in the prompt instead, so a plain
`codex exec` reviews the full multi-commit PR range. Never add
--dangerously-bypass-approvals-and-sandbox / --yolo to the engine call.

  cd <worktree-root> && codex exec --ephemeral -m {{CODEX_REVIEW_MODEL}} \
    -c model_reasoning_effort={{CODEX_REVIEW_EFFORT}} \
    -c features.hooks=false \
    -o /tmp/review-pr-{{PR_NUMBER}}-findings.txt - <<'CRITERIA'
  <the REVIEW CRITERIA below, verbatim>
  CRITERIA

REVIEW CRITERIA (both species; paste the ticket brief's requirements into
the COMPLIANCE section — when the ticket is "none", drop that section and
review correctness only):

  Review PR #{{PR_NUMBER}} ({{PR_TITLE}}). FIRST run
  `git diff origin/{{BASE_REF}}...HEAD` to see the ENTIRE PR range — every
  commit since the branch left origin/{{BASE_REF}}, not just the last commit —
  and review that whole diff.
  Review it for CORRECTNESS as a rigorous reviewer would (bugs, broken edge
  cases, unsafe or regressive changes), AND for SPEC COMPLIANCE against its
  ticket:
  <ticket requirements / acceptance criteria — paste from the brief below>
  Compliance checks: (1) does the diff fulfill every acceptance criterion?
  (2) is anything in the diff outside the ticket's scope? (3) does the PR
  body claim anything that is not actually in the diff?
  Report each finding as "- [severity] title (file:lines)"; compliance
  gaps are findings too.

The findings are the engine's output — a Claude worker reads the cookbook
call's final message (also in the -o file); a Codex worker's own analysis
IS the output. The verdict is YOURS, derived from the findings: approve
when no critical/high finding remains unresolved; needs-attention
otherwise.
