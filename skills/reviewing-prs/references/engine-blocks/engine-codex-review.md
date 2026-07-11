REVIEW ENGINE — the native Codex reviewer via the COOKBOOK pattern (plain
`codex exec` with a self-diffing prompt). Run it from the worktree root
(`codex exec` has no -C flag for this; cd there first).

DO NOT use the `codex exec review` subcommand with a target flag: `--base`,
`--commit`, and `--uncommitted` each hard-conflict with a custom PROMPT at
the CLI parser (exit 2, no output) — no targeting flag can be combined with
custom spec-compliance criteria in one call. Instruct the diff in the prompt
instead, so a plain `codex exec` reviews the full multi-commit PR range.

If YOU are yourself a Codex worker (this call would nest codex-in-codex),
first give the inner call its own writable home, or its app-server client
fails to start ("Operation not permitted"):

  mkdir -p .codex-home && ln -sf ~/.codex/auth.json .codex-home/auth.json
  export CODEX_HOME="$PWD/.codex-home"

And give the inner call file-based TLS roots — under the sandbox a nested
codex cannot reach the OS keychain/trustd for platform trust, so every
connection dies with `invalid peer certificate: UnknownIssuer` (surfacing
as "stream disconnected" retry loops). If not already in your env:

  export SSL_CERT_FILE=/etc/ssl/cert.pem   # macOS; on Linux point at the distro CA bundle

(The nested review then runs under stock read-only defaults — exactly what a
reviewer needs.) A Claude worker skips both steps — its `codex exec` is not
nested.

Then compose the review call — paste the ticket brief's requirements /
acceptance criteria into the COMPLIANCE section (when the ticket is "none",
drop that section and review correctness only):

  cd <worktree-root> && codex exec --ephemeral -m {{CODEX_REVIEW_MODEL}} \
    -c model_reasoning_effort={{CODEX_REVIEW_EFFORT}} \
    -c features.hooks=false \
    -o /tmp/review-pr-{{PR_NUMBER}}-findings.txt - <<'CRITERIA'
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
  CRITERIA

The findings are the engine's final message (also in the -o file). The
verdict is YOURS, derived from the findings: approve when no critical/high
finding remains unresolved; needs-attention otherwise. Never add
--dangerously-bypass-approvals-and-sandbox / --yolo to the engine call.
