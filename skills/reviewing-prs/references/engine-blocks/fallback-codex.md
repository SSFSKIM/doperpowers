ENGINE FALLBACK — you have no second engine. If the review engine call
(`codex exec`) fails (auth failure, or repeated API errors after 2 retries
with a short backoff): when the ticket is not "none", park —
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-human "review engine unavailable: <error>"
— otherwise leave the escalation as a PR comment. Then end your turn.
Record in the review-trail comment that the engine was unavailable.
