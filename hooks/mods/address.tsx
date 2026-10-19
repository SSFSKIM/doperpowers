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
 * pr), so the line is kept and asked again only when the session id changes
 * (a session sent to the background goes on under a new one) or the kept
 * one is a minute old (an alias renamed mid-session). A subagent's request
 * reads the parent's session id: its commits carry the session someone can
 * reach.
 */

/** How long a line is kept before the CLI is asked again. */
export const ADDRESS_TTL_MS = 60_000

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

type Kept = { session: string; line: string; at: number }

const state: { kept?: Kept; asking?: Promise<void> } = {}

/** Forgets the kept line (tests). */
export function resetAddress() {
  state.kept = undefined
  state.asking = undefined
}

/** The address line of `session`: the kept one while fresh, else asked of the CLI once for every caller waiting. */
export async function addressLine($: EngineInterface, session: string, now: () => number = Date.now): Promise<string> {
  const kept = state.kept
  if (kept !== undefined && kept.session === session && now() - kept.at < ADDRESS_TTL_MS) {
    return kept.line
  }
  state.asking ??= (async () => {
    let line = kept?.session === session ? kept.line : ''
    try {
      const r = await $.process.run([`${$.plugin.root}/skills/sminos/scripts/sminos`, 'who', '--session', session], { timeoutMs: 10_000 })
      if (r.exitCode === 0) {
        line = r.stdout.trim().split('\n')[0] ?? ''
      }
    } catch {
      // Kept as it was: a CLI that cannot run now is asked again a minute on.
    }
    state.kept = { session, line, at: now() }
  })().finally(() => {
    state.asking = undefined
  })
  await state.asking
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
}
