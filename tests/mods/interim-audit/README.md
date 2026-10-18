# interim-audit

Audits the interim-notification filter (`hooks/mods/interim.ts`) against what
actually happened on this machine: every prompt a hook dropped, and every
interim notice the filter let in, across all main-session transcripts under
`~/.claude/projects/` touched since a given UTC time.

```bash
tests/mods/interim-audit/run.sh 2026-10-18T08:00
```

It reads transcripts only and spends no model calls. Three reports:

- **Every dropped prompt.** Drops by reason, so a hook other than the filter
  shows up as `other dropped prompts`. Then each interim drop paired with the
  notification it removed, per agent: was a hand-back report and a final
  notification seen afterwards, and how many messages the agent sent in the
  meantime.
- **Checks on each interim drop.** A drop was wrong if any of these fail:
  the text is one completed envelope whose whole result is the engine's
  waiting placeholder (checked independently of the filter's regex); the
  agent's transcript shows the hand-back contract on, so the engine wrote
  that sentence; for a worktree agent or an orphan, an earlier notice of it
  was already in the conversation; and the agent's report arrived later, or
  its transcript was written in the last two hours (it is still working).
  `with a problem: 0` is the pass line.
- **Interim notices that were let in.** Each one with the reason it passed:
  by design (agent text or a warning in the result, a pointer to a delivered
  report, a first worktree or orphan notice), a failed provenance check, or
  `SHOULD HAVE DROPPED`, which means the session ran a plugin without the
  filter or something regressed.

A notification's transcript link (`<output-file>` under the engine's temp
dir) lives only as long as the engine's task files, so the provenance check
needs a recent window.
