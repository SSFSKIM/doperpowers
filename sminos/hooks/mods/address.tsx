import type { AttributionTextInput, AttributionTextResult, EngineInterface, On } from 'claude-code'

/**
 * The session's address in every commit and pull request it writes: the
 * engine composes the attribution text the model is told to end a commit
 * message and a PR body with (the settings' attribution, its own
 * `Claude-Session:` trailer) and passes it through `attribution.text`; this
 * appends `Sminos-Session: <alias>#<short> (<project> on <machine>)`, which
 * `sminos who` reads back. The line is the sminos CLI's (`sminos who
 * --session <id>`), empty for a session in no project, an internal fork, or
 * one that is no member, and then nothing is added.
 *
 * The engine asks before every model request of every loop (commit, then
 * pr), and the CLI is a Python start, so the line is kept and the CLI asked
 * again only when it may answer otherwise: for a new session id (a session
 * sent to the background goes on under a new one; a module loaded afresh,
 * as at each session start, holds none), after a compaction, and once the
 * kept line is ten minutes old (an alias renamed mid-session, a `sminos
 * join`). No file's change stands in for that timer: what the line is
 * composed from — the engine's record of the session (its name), the
 * session's own log file (the alias it joined or was renamed under), the
 * project's log (a name another member holds), the transcript (where the
 * session was moved to), the join override, the machine's enrollment —
 * lies mostly in files the engine and the session rewrite at every turn or
 * message for reasons of their own, so their times would ask about once a
 * turn. A request never waits on a line it already has: one past its time
 * is used while the CLI is asked in the background. A subagent's request
 * reads the parent's session id: its commits carry the session someone can
 * reach.
 */

/** How long a line is kept before the CLI is asked again. */
export const ADDRESS_TTL_MS = 10 * 60_000

/** How soon the CLI is asked again when it answered no line (as for a session the engine has not registered yet) or failed (the line kept as it was). */
export const ADDRESS_RETRY_MS = 60_000

/** A git trailer line: a token, a colon, a space (git's own separator). */
const TRAILER_LINE = /^[A-Za-z0-9-]+:\s/

/**
 * The composed text with the address added: a commit's as a trailer (in the
 * trailer block when the text ends in one, else a paragraph of its own), a
 * PR body's as its last line. The text alone when there is no line, for
 * another kind, or when it already carries the line.
 */
export function withAddress(kind: string, text: string, line: string): string {
  if (line === '' || (kind !== 'commit' && kind !== 'pr')) {
    return text
  }
  const base = text.trimEnd()
  if (base === '') {
    return line
  }
  if (base.split('\n').some((l) => l.trim() === line)) {
    return text
  }
  const last = base.slice(base.lastIndexOf('\n') + 1)
  return kind === 'commit' && TRAILER_LINE.test(last) ? `${base}\n${line}` : `${base}\n\n${line}`
}

type Kept = { session: string; line: string; until: number }

/** An ask of the CLI in flight: the session it is for, and its end. */
type Asking = { session: string; done: Promise<void> }

const state: { kept?: Kept; asking?: Asking } = {}

/** Forgets the kept line (tests). */
export function resetAddress() {
  state.kept = undefined
  state.asking = undefined
}

/** Makes the kept line due: the next request asks the CLI again, and keeps the line should the CLI fail. */
export function refreshAddress() {
  if (state.kept !== undefined) {
    state.kept = { ...state.kept, until: 0 }
  }
}

/** Asks the CLI for `session`'s line: what to keep, its answer or `line` when it cannot answer. */
async function askCli($: EngineInterface, session: string, line: string, now: () => number): Promise<Kept> {
  let answered = false
  try {
    const r = await $.process.run([`${$.plugin.root}/skills/sminos/scripts/sminos`, 'who', '--session', session], { timeoutMs: 10_000 })
    if (r.exitCode === 0) {
      line = r.stdout.trim().split('\n')[0] ?? ''
      answered = true
    }
  } catch {
    // Kept as it was: a CLI that cannot run now is asked again a minute on.
  }
  return { session, line, until: now() + (answered && line !== '' ? ADDRESS_TTL_MS : ADDRESS_RETRY_MS) }
}

/**
 * Starts the one ask for `session`; its answer is kept unless an ask for
 * another session started meanwhile (the session went on under a new id,
 * whose line it would overwrite).
 */
function startAsk($: EngineInterface, session: string, line: string, now: () => number): Asking {
  const asking: Asking = { session, done: Promise.resolve() }
  asking.done = askCli($, session, line, now).then((kept) => {
    if (state.asking === asking) {
      state.kept = kept
      state.asking = undefined
    }
  })
  state.asking = asking
  return asking
}

/**
 * The address line of `session`: the kept one, the CLI asked once for every
 * caller of the session when it is due — in the background when a line is
 * kept, the caller waiting only for a session with none.
 */
export async function addressLine($: EngineInterface, session: string, now: () => number = Date.now): Promise<string> {
  const kept = state.kept?.session === session ? state.kept : undefined
  if (kept !== undefined && now() < kept.until) {
    return kept.line
  }
  const asking = state.asking?.session === session ? state.asking : startAsk($, session, kept?.line ?? '', now)
  if (kept !== undefined) {
    return kept.line
  }
  await asking.done
  return state.kept?.session === session ? state.kept.line : ''
}

/** The hook: what the engine composed, the address added. */
export async function addressText(
  $: EngineInterface,
  e: AttributionTextInput,
  next: (e: AttributionTextInput) => Promise<AttributionTextResult>,
  now: () => number = Date.now,
): Promise<AttributionTextResult> {
  const composed = await next(e)
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return composed
  }
  const line = await addressLine($, await $.session.id(), now)
  return { text: withAddress(e.kind, composed.text, line) }
}

export function registerAddress(on: On) {
  on('attribution.text', { kind: /^(?:commit|pr)$/ }, ($, e, next) => addressText($, e, next))
  // A compaction that stood (a precompute replaces nothing; a skip leaves the
  // conversation as it was): a long session's checkpoint, where the line is
  // asked for again.
  on('session.compact', { trigger: /^(?:manual|auto|plugin)$/ }, async (_, e, next) => {
    const r = await next(e)
    if (r.skip === undefined) {
      refreshAddress()
    }
    return r
  })
}
