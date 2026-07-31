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

The broker kill-switch (`CODEX_COMPANION_APP_SERVER_ENDPOINT` pointed at
a never-existing socket) belongs on `review`/`adversarial-review`/`task`
only. Left off those, the first run spawns a detached broker +
`codex app-server` pair per workspace that outlives the session —
upstream reaped these with a SessionEnd hook this bundle doesn't have;
with it, each call fails over to a per-call direct app-server that dies
with it. The job verbs above never spawn a broker and take only the
state-root env; `setup`'s auth probe would actually misread the dead
endpoint as an auth failure. If leaked pairs accumulate anyway (from
running work verbs without the kill-switch), find them with
`ps -axo pid,command | grep app-server-broker`, kill the pids, and
delete the workspace's stale `broker.json` under the state root —
`setup`/`status` keep probing the dead socket it records until it's
gone.

Backgrounding differs by verb. For reviews, `--background` only shapes
the job record — nothing detaches. For `task`, the runtime's own
`--background` DOES spawn a detached worker, and it has a
persist-after-spawn race that can strand the job (worker exits "No stored
job found" while the record stays queued forever) — don't use it. The one
backgrounding mechanism for everything: run the plain foreground command
inside the harness's background Bash (`run_in_background: true`). That
wakes this session on completion, so don't poll `status` in a loop; it
exists for mid-flight peeks at long runs and for picking up jobs from a
different session. Without a job id, `status`/`result` default to the
most recent job in this workspace (job records carry a Claude session id
only when `CODEX_COMPANION_SESSION_ID` is set in the environment; absent
that, listings are workspace-wide — fine for a single-user machine).

`result` also prints the Codex session id of a finished job when
available, so the run can be reopened directly in Codex with
`codex resume <session-id>`.
