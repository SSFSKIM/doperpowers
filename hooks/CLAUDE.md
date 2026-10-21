# hooks/ — the doperpowers plugin's hooks

Bare file names and `mods/` are this directory's; other paths are the repository's. The function hooks' detail is in `mods/CLAUDE.md`.

The `kairos` proactive mode: `kairos.sh` on `SessionStart` injects the `kairos` skill's body at startup and after every compaction for a session in the mode — launched with `KAIROS=1`, or switched on mid-session by typing `/kairos`, which `kairos-toggle.sh` (on `UserPromptExpansion`) records as a flag file under `~/.claude/kairos/<session-id>`; `/kairos off` removes it. Every other session gets nothing.

The project family's shell hooks and the ask tool, the bridge and the session's address are the sminos plugin's (`sminos/`).

`mods/` holds the plugin's function hooks ("mods"): `hooks.json` names `mods/register.tsx` under `modules`, which the engine loads only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` and ignores elsewhere.

`to-human-stream.sh` on `MessageDisplay` draws the `<message>` mark's labels flush by flush while a message streams (the engine mounts an `AssistantMessage` only once a block is whole); the report view that folds the transcript to those marks is the `to-human` plugin (`to-human/`), whose parser reads either that form or the raw tags.

`compact-instructions.md` is printed by a `PreCompact` hook on every compaction, auto or `/compact`: the harness appends a PreCompact hook's stdout to the summary request as "Additional Instructions" (confirmed in the 2.1.283 source and by a canary hook), after the stock nine-section template that tells the summarizer to follow its structure — text that does not say it overrides the template is read as a hint and barely moves the summary (2026-09-28: the first wording produced summaries indistinguishable from no instructions), so each summary is written as the note a memory-reset self resumes from — pointers for what is on disk, copies of what lived only in the conversation (the summarizer can call no tools, and the transcript path is appended after the summary). Subagent compactions receive it too (60 of the 62 subagent summaries on this machine since it landed carry its `[verified]` marks, none of the 84 before).

The upstream `SessionStart` bootstrap that used to live here (injecting the `using-doperpowers` skill index) was torn out; skills load from `skills/` directly.
