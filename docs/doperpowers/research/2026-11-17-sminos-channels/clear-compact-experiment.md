# What the engine does at a /clear, an in-session /resume, a /fork and a compaction (2026-11-18)

Claude Code 2.1.327, on a Mac. Ten trials, two of each: `/clear`, in-session `/resume <id>`, `/fork`, `/compact` in an interactive session, `/compact` in a background session (attached). One scratch session at a time in an isolated terminal multiplexer, the caller's environment stripped. Each scratch directory registered one command hook for `SessionStart`, `SessionEnd` and `UserPromptSubmit` that logged its stdin payload, `CLAUDE_PID`, and the engine's per-process session record (`sessions/<pid>.json` under the config directory) as it was when the hook started. `CLAUDE_PID`, the shell's parent and `getppid()` agreed in every hook.

## /clear

Same process. In both trials, in this order, 0.2 to 0.5 s apart:

1. `SessionEnd`, payload `reason: "clear"`, `session_id` the OLD id; the process's record names the OLD id.
2. `SessionStart`, payload `source: "clear"`, `session_id` the NEW id; the process's record already names the NEW id.

The `SessionStart` payload holds `session_id`, `transcript_path`, `cwd`, `hook_event_name` and `source`, and nothing that names the old session; no environment value held the old id (`CLAUDE_CODE_SESSION_ID` and the others were the new one's). The old transcript's last record and the new one's first name only their own session. Later rows of the new transcript carry the old id in a snake-case `session_id` beside a camel-case `sessionId` of the new one; not established as a lineage mechanism.

**So:** the old id cannot be read at the new session's start. The witness is the `SessionEnd` with reason `clear` in the same process, which a hook has to keep for the `SessionStart` that follows.

## In-session /resume

Same process. `SessionEnd` with `reason: "resume"` and the source's id (the record names the source); then `SessionStart` with `source: "resume"` and the target's id, while the process's record STILL names the source (it named the target by the next prompt). Nothing in the target's start names the source.

## /fork

`/fork <prompt>` copies the conversation into a new background session in another process and the original keeps working (no `SessionEnd` for it). The copy's `SessionStart` has `source: "fork"`, its own id in the payload, the environment and its own process's record (`kind: "bg"`); nothing in them names the original. The copy's history contains the original's id in copied rows. `/branch` and the CLI's `--fork-session` were not run.

## Compaction

Four trials, interactive and background: the session id does not change. No `SessionEnd`; one `SessionStart` with `source: "compact"` and the same id in the payload, the environment and the process's record; the transcript file is the same and gains a `compact_boundary` record (`trigger: "manual"`). Automatic compaction was not triggered.

## Not established

The order inside function-hook mods; automatic compaction; a `/clear` in a background session; `--fork-session`; `/branch`; other engine versions. Two samples of each timing.
