# interim (`interim.ts`)

A subagent that ends its turn while its own subagent or background shell
still runs makes the engine send its parent a completion notification anyway,
and again each time that work wakes it and it stops to wait once more: in one
MAWS session (2026-09-29) 277 of 486 notifications were these, each one a
parent turn spent on "still running, nothing to do". The engine marks them,
writing "This agent stopped with background work of its own still running"
into the notification's `<note>` (the final one carries the other note), so a
`prompt.submit` hook matched on `origin.kind: 'task-notification'` drops those
before they enter the session, but only when the status is `completed`, the
`<note>` element carries that marker, and the whole `<result>` is one of the
engine's placeholders (the report is still to come through SubagentHandback,
or was already delivered as a message). A result holding anything else, the
agent's words where hand-back is off or an engine warning beside the
placeholder, passes, as do the final notification and a report that merely
quotes the marker. Replayed over that session, the filter drops 280
notifications, every one a placeholder. What it gives up: an agent killed
after a dropped placeholder gets no fresh notification from the engine, so
the parent hears of the kill only if it did the killing or looks. A hook
that fails lets the notification through.

Retired from `hooks/mods/` in 7.145.0 and kept here unwired. To restore it,
move `interim.ts` back into `hooks/mods/`, `interim.test.ts` into
`tests/mods/` (its import path is `../../hooks/mods/interim`), add
`registerInterim(on)` to `hooks/mods/register.tsx`, and put this section back
in `hooks/mods/README.md`.
