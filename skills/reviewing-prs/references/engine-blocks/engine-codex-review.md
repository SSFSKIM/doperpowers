REVIEW ENGINE — the native `codex exec review` engine, run as a PURE
correctness review: it receives no criteria, no developer instructions,
no ticket or spec input of any kind. Ticket/spec compliance is YOUR
audit, not the engine's. The engine call is a TOOL invocation, not a
nested agent. Never add --dangerously-bypass-approvals-and-sandbox /
--yolo to anything.

1. Run `mktemp -d "${TMPDIR:-/tmp}/review-pr-{{PR_NUMBER}}.XXXXXX"`
   once. Treat the returned path as `<review-tmp>` for this invocation and
   remove that directory before ending the turn.
2. From the worktree root, start the engine IN THE BACKGROUND (round N
   uses findings-rN.txt):

   CODEX_REVIEW_MODEL={{CODEX_REVIEW_MODEL}} \
   CODEX_REVIEW_EFFORT={{CODEX_REVIEW_EFFORT}} \
     {{REVIEW_ENGINE}} --base origin/{{BASE_REF}} \
     --out <review-tmp>/findings-r1.txt

   Use your harness's background execution for this command and keep the
   task handle. Do NOT wait on it and do NOT read the findings file yet —
   the protocol's COMPLIANCE AUDIT runs while the engine reviews, and its
   JOIN step is the only place engine output is read.
3. At JOIN: wait for the background task. Bound the wait — an engine
   task that has neither completed nor failed 45 minutes after start is
   hung: kill it and treat the round as an engine failure (the fallback
   block below owns retries and the outage path).
4. Read the findings file — that compact verdict IS the engine's output.
   Do NOT read the full PR diff yourself: the engine reviews the whole
   range; you read only what the protocol tells you to read.

The verdict is YOURS, derived from the findings: approve when no
critical/high finding remains unresolved; needs-attention otherwise. On
RE-REVIEW rounds re-run the same command with a fresh --out file, again
in the background.
