---
name: codex-migration
description: Migrate a Claude Code session into Codex so it can be resumed from the Codex desktop app.
disable-model-invocation: true
---

# Codex Migration

Move one Claude Code session transcript into Codex as a resumable thread,
filed under the folder the user actually works in, visible in the Codex
desktop app. Everything runs through Codex's own machinery: the built-in
external-agent importer and the app-server JSON-RPC API. Never hand-write
rollout files.

What carries over: user and assistant messages, in order. Tool calls, file
diffs, and command output do not; Codex will re-read files before it
continues. Say so in the final report.

## 1. Locate the source

The transcript is `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`,
where `<encoded-cwd>` is the working directory with `/` replaced by `-`.
Take the session id from the user; if they only give a name, match it
against `ai-title` / custom-title records in the candidate files. Note the
transcript's `cwd` values: the importer takes the **first** one it sees,
which is stale whenever the repo has since moved or been renamed.

## 2. Drive the app-server over stdio

Spawn `codex app-server` and speak newline-delimited JSON-RPC on its stdin
and stdout. Send `initialize` with `capabilities.experimentalApi: true`
(the project methods are experimental), then the `initialized`
notification, then the requests below. Wait for a response by matching
`id`; notifications arrive with `method` and no `id`. Keep one small Python
or Node client in a scratch dir for the whole job.

A fresh stdio server writes to the same `~/.codex` state as the desktop
app's server, but the desktop app does **not** watch for changes made by
other processes: it caches the project list and a thread catalog. Every
step that should become visible in the app ends with a full quit and
relaunch of the ChatGPT app.

## 3. Import

Call `externalAgentConfig/import` with one SESSIONS item; detection is
optional because the importer validates the path itself:

```json
{"migrationItems": [{"itemType": "SESSIONS", "description": "Import sessions", "cwd": null,
  "details": {"sessions": [{"path": "<transcript>", "cwd": "<intended cwd>", "title": "<session name>"}]}}],
 "providerId": "claude_code"}
```

The response carries an `importId`; the real result is the
`externalAgentConfig/import/completed` notification with that id. A
`successes` entry names the new thread id. **Empty successes and empty
failures means the file was already imported at its current mtime**: the
ledger at `~/.codex/external_agent_session_imports.json` maps source path
to `imported_thread_id`, and a re-import of a grown file appends only the
new messages to that thread. Read the ledger to find the thread.

## 4. Fix the working directory

Check the thread's `cwd` in `thread/list` (`useStateDbOnly: true`). If it
is not the folder the user resumes in, re-root it with a fork, which is the
only sanctioned way to change a thread's cwd:

1. `thread/fork` `{threadId, cwd, excludeTurns: true, ephemeral: false}`.
   Verify the new rollout has the same user and assistant message counts
   as the original.
2. `thread/name/set` on the fork with the session name.
3. `thread/archive` the mis-rooted original so one copy shows.
4. Point the ledger record's `imported_thread_id` at the fork so later
   re-imports append to the right thread. Back the ledger up first.

## 5. Convert to paginated history

The desktop app stores its own threads in paginated history mode and its
project view silently drops legacy-mode threads, even when they are intact
and correctly filed. Imports and forks come out in legacy mode, so run
`codex migrate-rollouts --thread <id> --apply` and confirm
`threads.history_mode` in `~/.codex/state_5.sqlite` reads `paginated`.
This step is what makes the thread appear; do not skip it.

## 6. Make the folder exist in the app

The sidebar lists threads per registered project, matching a thread's cwd
against each project's root exactly or as a path prefix. A thread whose cwd
is under no registered root is invisible even though it is fully intact.
Call `project/list`; if no root covers the cwd, call `project/create`
`{name, roots: [{path}], metadata: {}, idempotencyKey}`. Watch for a
sidebar entry whose name matches the folder but whose root is an old path;
that is the usual reason a user cannot find an imported thread.

## 7. Verify and report

- `thread/list` with `cwd: [<folder>]` returns the thread, not archived.
- Message counts in the rollout match the source.
- `codex resume <thread-id>` from the folder works as a fallback.
- Tell the user to quit and relaunch the ChatGPT app, name the sidebar
  project to look under, and state the tool-output limitation.
