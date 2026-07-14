REVIEW ENGINE — the pure native correctness reviewer, identical for both
worker species; only the nesting differs (a codex worker's call runs inside
its own sandbox, a claude worker's on the host — the script handles both).
The engine call is a TOOL invocation, not a delegated reviewer or nested
agent. Never add --dangerously-bypass-approvals-and-sandbox / --yolo.

1. Run `mktemp -d "${TMPDIR:-/tmp}/review-pr-{{PR_NUMBER}}.XXXXXX"`
   once. Treat the returned path as `<review-tmp>` for this invocation and
   remove that directory before ending the turn.
2. From the worktree root, start this command as a background task using the
   current harness's native background execution facility. Retain its task
   handle and output path; do not wait for it now (round N uses findings-rN.txt):

   CODEX_REVIEW_MODEL={{CODEX_REVIEW_MODEL}} \
   CODEX_REVIEW_EFFORT={{CODEX_REVIEW_EFFORT}} \
     {{REVIEW_ENGINE}} --base origin/{{BASE_REF}} \
     --out <review-tmp>/findings-r1.txt

3. Do not read the findings file yet. While the native task runs, complete the
   Review Worker Protocol's independent IMPLEMENTER-PROTOCOL AUDIT and write
   `<review-tmp>/protocol-audit.md`.
4. At JOIN THE TWO TRACKS, wait for the background task. A successful task's
   compact findings file is the native correctness output. On failure, apply
   ENGINE FALLBACK before reading or routing any partial output.

The native engine reviews code correctness, rates its own severity, and cites
file:lines. It receives no ticket specification. On RE-REVIEW, start the same
command in the background with a fresh findings-rN.txt while re-checking the
spec impact of the fixes, then join again.
