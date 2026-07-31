# Jobs: backgrounding, `status`, `result`, `cancel`

Every `review`, `adversarial-review`, and `task` run is recorded as a job
under the state root — which is why the `CLAUDE_PLUGIN_DATA` prefix is
mandatory on every invocation: unset, the runtime falls back to a tmpdir
that macOS periodically purges, and job history (`status`, `result`,
`--resume-last`) silently vanishes. Sessions that still have the OpenAI
codex plugin installed also inherit ITS `CLAUDE_PLUGIN_DATA` from a hook;
the explicit prefix wins over both.

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" status [job-id] [--all] [--json]
    …                                                          result [job-id] [--json]
    …                                                          cancel [job-id] [--json]

Backgrounding: a job flag alone does not detach anything — `--background`
only shapes the job record. Actual detachment is the harness's background
Bash (`run_in_background: true`) wrapping the whole command. A background
Bash job wakes this session when it finishes, so do not poll `status` in a
loop; it exists for mid-flight peeks at long runs and for picking up jobs
from a different session. Without a job id, `status`/`result` default to
the most recent job in this workspace (job records carry a Claude session
id only when `CODEX_COMPANION_SESSION_ID` is set in the environment;
absent that, listings are workspace-wide — fine for a single-user
machine).

`result` also prints the Codex session id of a finished job when
available, so the run can be reopened directly in Codex with
`codex resume <session-id>`.
