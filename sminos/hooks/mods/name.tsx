import type { ClassicEventOf, ClassicResultOf, EngineInterface, On } from 'claude-code'

/**
 * A session is renamed after what it is in charge of: `sminos derive` asks
 * the session's fork for its in-charge line and a charge name with it, and,
 * when the engine name it would replace is still the session's, hands the
 * name over as a pending file, `<sminos home>/names/<session>.json`
 * (docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md §3).
 *
 * The engine renames a session the way sminos needs only for a
 * `UserPromptSubmit` hook's `sessionTitle`: the engine name is registered
 * with source `hook`, the transcript keeps `custom-title` and `agent-name`,
 * and the engine's title promotion leaves it alone. `SessionStart`'s sets
 * the title alone, and `/rename` would register the owner's `user`. So a
 * pending name applies at the session's next prompt, whoever submits it.
 *
 * Before it applies, the CLI checks the name is still due (`sminos
 * name-due`): the engine name is still the one the file replaces (no
 * owner's /rename, no resume under a new name since) and the name is still
 * free. That check runs once per pending file, not once per prompt; a
 * prompt with no new file pays one failed read.
 */

type Event = ClassicEventOf['classic.UserPromptSubmit']
type Result = ClassicResultOf['classic.UserPromptSubmit']

/**
 * How long the check may take, as the address bounds `who`: `name-due`
 * reconciles the session's project before it answers, a read comparable to
 * `who`'s. A `$` call costs the hook's own budget nothing, and the prompt
 * waits on it only when a name is pending and new.
 */
export const NAME_DUE_TIMEOUT_MS = 10_000

/** The one line the model reads when its session was renamed. */
export function renamedContext(name: string): string {
  return `sminos renamed this session to "${name}" after its standing responsibility; other sessions now see and address it by that name.`
}

/** The text of the pending file the CLI last answered for: checked once. */
const state: { handled?: string } = {}

/** Forgets the handled file (tests). */
export function resetName() {
  state.handled = undefined
}

/** The sminos home as the CLI's root() resolves it: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos. */
async function sminosHome($: EngineInterface): Promise<string> {
  const own = (await $.env.get('SMINOS_HOME')) || (await $.env.get('DAEMON_HOME'))
  return own || `${(await $.env.get('HOME')) ?? ''}/.claude/sminos`
}

/** The hook: what the hooks beneath answered, with the pending name applied when it is due. */
export async function applyPendingName($: EngineInterface, e: Event, next: (e: Event) => Promise<Result>): Promise<Result> {
  const result = await next(e)
  // The poll-event channel's pass runs as an event is enqueued, before it is
  // delivered; the prompt's own submit follows and applies the name there.
  if (result.sessionTitle !== undefined || e.source === 'poll_event' || (await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return result
  }
  const pending = await $.fs.read(`${await sminosHome($)}/names/${e.session_id}.json`).catch(() => undefined)
  if (pending === undefined || pending === state.handled) {
    return result
  }
  let answer
  try {
    answer = await $.process.run([`${$.plugin.root}/skills/sminos/scripts/sminos`, 'name-due', '--session', e.session_id], {
      timeoutMs: NAME_DUE_TIMEOUT_MS,
    })
  } catch {
    // Not answered (it could not start, or timed out): the next prompt asks again.
    return result
  }
  state.handled = pending
  const name = answer.exitCode === 0 ? (answer.stdout.trim().split('\n')[0] ?? '').trim() : ''
  if (name === '') {
    return result
  }
  return { ...result, sessionTitle: name, additionalContext: [...(result.additionalContext ?? []), renamedContext(name)] }
}

export function registerName(on: On) {
  on('classic.UserPromptSubmit', { hook_event_name: 'UserPromptSubmit' }, ($, e, next) => applyPendingName($, e, next))
}
