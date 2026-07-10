ENGINE FALLBACK — if `codex` is unavailable (command missing, auth failure,
or repeated API errors after 2 retries with a short backoff): fall back to
a fresh Claude reviewer subagent at high effort over the same diff with the
same criteria, returning findings as "- [severity] title (file:lines)".
Record in the review-trail comment which engine reviewed.
