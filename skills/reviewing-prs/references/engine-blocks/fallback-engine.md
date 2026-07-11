ENGINE FALLBACK — there is no second engine; the reviewer is codex-only.
If the engine script fails (codex missing — rc 127, auth failure, or
API errors), retry twice with a short backoff. Still failing:
- post the review-trail comment recording the outage ("engine
  unavailable: <error>");
- touch NO board state — the ticket stays in-review. An infra outage is
  not a human decision; needs-human stays reserved for judgment/input.
- end your turn with a final message whose LAST LINE is exactly:
  ENGINE-UNAVAILABLE
The sweep re-dispatches this PR when it sees that marker (~30 min
cadence), so the review resumes by itself once the engine is healthy.
