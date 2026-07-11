REVIEW ENGINE — the native `codex exec review` engine, identical for both
worker species; only the nesting differs (a codex worker's call runs
inside its own sandbox, a claude worker's on the host — the script
handles both). The engine call is a TOOL invocation, not a nested agent:
it does not violate the work-alone rule. Never add
--dangerously-bypass-approvals-and-sandbox / --yolo to anything.

1. Run `mktemp -d "${TMPDIR:-/tmp}/review-pr-{{PR_NUMBER}}.XXXXXX"`
   once. Treat the returned path as `<review-tmp>` for this invocation and
   remove that directory before ending the turn.
2. Write the REVIEW CRITERIA below to `<review-tmp>/criteria.md` — paste
   the ticket brief's requirements into the COMPLIANCE section; when the
   ticket is "none", drop that section and review correctness only.
3. From the worktree root, run (round N uses findings-rN.txt):

   CODEX_REVIEW_MODEL={{CODEX_REVIEW_MODEL}} \
   CODEX_REVIEW_EFFORT={{CODEX_REVIEW_EFFORT}} \
     {{REVIEW_ENGINE}} --base origin/{{BASE_REF}} \
     --criteria <review-tmp>/criteria.md \
     --out <review-tmp>/findings-r1.txt

4. Read the findings file — that compact verdict IS the engine's output.
   Do NOT read the full PR diff yourself: the engine reviews the whole
   range; you read only the code each finding names.

REVIEW CRITERIA (write to the criteria file):

  Review PR #{{PR_NUMBER}} ({{PR_TITLE}}) — the ENTIRE range against the
  review base: every commit since the branch left origin/{{BASE_REF}},
  not just the last commit.
  Review it for CORRECTNESS as a rigorous reviewer would (bugs, broken
  edge cases, unsafe or regressive changes), AND for SPEC COMPLIANCE
  against its ticket:
  <ticket requirements / acceptance criteria — paste from the brief below>
  Compliance checks: (1) does the diff fulfill every acceptance criterion?
  (2) is anything in the diff outside the ticket's scope? (3) does the PR
  body claim anything that is not actually in the diff?
  Report each finding as "- [severity] title (file:lines)"; compliance
  gaps are findings too.

The verdict is YOURS, derived from the findings: approve when no
critical/high finding remains unresolved; needs-attention otherwise. On
RE-REVIEW rounds re-run the same command with a fresh --out file.
