import type { EngineInterface, ModelForkResult } from 'claude-code'
import { message, state } from './bridge-state'
import type { Answer } from './bridge-state'
import { emit, emitOwed } from './bridge-stream'

/**
 * The desk's side question (DX5 `btw`, the desk control surface spec's §9;
 * MW2): one tool-less completion over the session's own transcript as the
 * main thread last sent it (`$.model.fork`), which writes nothing into the
 * conversation and runs beside a turn. The op answers at once, `started`;
 * the answer follows on the stream as `btw` start and end, which the child
 * annotates with the RPC's nonce and the daemon relays as DX4 `op`.
 *
 * Every side question answered `started` ends once. A reload of the module
 * aborts its fork with the environment that holds it, which posts nothing
 * more (its child turns it away), so each open one is kept in `$.state`,
 * which the host holds for the session across a reload, from before its
 * answer until the child took its end; the module that loads next ends each
 * it finds there, `aborted`. An end the child has not taken yet goes again
 * after the next resync (emitOwed): a child that crashed, a post lost.
 */

/**
 * What the person's question is put under. Unframed mid-turn, a fork goes on
 * with the open task or reaches for a tool (every fork tool is denied, so it
 * answers with nothing): S3 measured both.
 */
export const BTW_FRAME = 'Answer the following without using any tools and without continuing your current task; one reply, then stop.'
/** The answer's text an end carries at most, in UTF-8 bytes (spec §3: an `op` body goes to every browser, in one frame). */
export const BTW_TEXT_MAX = 65_536
/**
 * How long the op's answer waits on the fork before it says `started`: a fork
 * with nothing to fork resolves without a request, so the engine knows it at
 * once, and the op is refused with it instead of starting.
 */
export const BTW_REFUSAL_WAIT_MS = 250
/** The refusal when the session holds no main-thread request to fork (before its first, after a /clear). */
export const NOTHING_TO_FORK = 'nothing to fork yet: the session has made no model request since it started or was cleared'

/** The session's open side questions, by id, as `$.state` keeps them for a module that loads after this one (types/sminos.d.ts). */
const OPEN = { plugin: 'sminos', key: 'btw' } as const

/** Writes the open side questions as they stand now, after any write before it. */
function keepOpen($: EngineInterface): Promise<void> {
  const open = [...state.btwOpen]
  state.btwWrites = state.btwWrites.then(
    () => $.state.set(OPEN, open).then(() => undefined),
    () => undefined,
  ).catch((error: unknown) => state.log?.(`bridge: the open side questions are not kept for a reload: ${message(error)}`))
  return state.btwWrites
}

/** Its end posted and taken by the child: no module after this one ends it again. */
async function ended($: EngineInterface, id: string, end: Record<string, unknown>) {
  await emitOwed({ type: 'btw', phase: 'end', id, ...end })
  state.btwOpen.delete(id)
  await keepOpen($)
}

/**
 * At the module's session start: the side questions a module before this
 * one left open (a reload aborted their forks) end, `aborted`, each once,
 * and are let go once the child took the end. Its own are never among them.
 */
export async function endOrphanedSideQuestions($: EngineInterface) {
  let kept: unknown
  try {
    kept = (await $.state.get(OPEN)).value
  } catch (error) {
    state.log?.(`bridge: the open side questions could not be read: ${message(error)}`)
    return
  }
  const orphans = (Array.isArray(kept) ? kept : []).filter((id): id is string => typeof id === 'string' && !state.btwOpen.has(id))
  for (const id of orphans) {
    state.btwOpen.add(id)
    void ended($, id, { reason: 'aborted' })
  }
}

/** The prompt the fork is sent: the frame, then the person's question as asked. */
export const framed = (prompt: string) => `${BTW_FRAME}\n\n${prompt}`

/** UTF-8 bytes of one code point. */
const bytesOf = (cp: number) => (cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4)

/** The text held to BTW_TEXT_MAX UTF-8 bytes, cut between code points, and whether it was cut. */
export function boundedText(text: string, max = BTW_TEXT_MAX): { text: string; truncated: boolean } {
  let bytes = 0
  let at = 0
  for (const ch of text) {
    bytes += bytesOf(ch.codePointAt(0)!)
    if (bytes > max) {
      return { text: text.slice(0, at), truncated: true }
    }
    at += ch.length
  }
  return { text, truncated: false }
}

/** The fork's cost, in the shape the end carries (DX5: `{input, output, cacheRead?, cacheWrite?}`). */
function usageOf(u: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }) {
  return { input: u.input_tokens, output: u.output_tokens, cacheRead: u.cache_read_input_tokens, cacheWrite: u.cache_creation_input_tokens }
}

/**
 * An end's fields from what the fork resolved to: the answer's `text`
 * (bounded, `truncated` when cut) and `usage`, or the `reason` there is none
 * (`nothing-to-fork`, `api-error` with the HTTP `status` and the engine's
 * `error` kind, `empty-reply`, `aborted`), with `usage` wherever a request
 * was made.
 */
export function btwEnd(result: ModelForkResult): Record<string, unknown> {
  if (result.isAnswered) {
    const bounded = boundedText(result.text)
    return { text: bounded.text, ...(bounded.truncated && { truncated: true }), usage: usageOf(result.usage) }
  }
  if (result.reason === 'nothing-to-fork') {
    return { reason: result.reason }
  }
  return { reason: result.reason, ...(result.reason === 'api-error' && { status: result.status, error: result.error }), usage: usageOf(result.usage) }
}

/** What a fork that rejected (a `$` call failing, not the provider) ends with: the op still ends. */
const failedEnd = (error: unknown) => ({ reason: 'failed', error: message(error) })

/**
 * DX5 `btw {prompt}`: the fork asked at once, under the frame. Answered
 * `{started: true, id}` unless the engine says within BTW_REFUSAL_WAIT_MS that
 * there is nothing to fork (refused, `nothing-to-fork`); the start and the end
 * follow on the stream after the answer (`after`), so the child holds the
 * RPC's nonce for both. An Esc does not refuse it, and nothing waits for the
 * main turn: the fork runs beside it.
 */
export async function sideQuestion($: EngineInterface, id: string, prompt: unknown): Promise<Answer & { after?: () => void }> {
  if (typeof prompt !== 'string' || prompt.trim() === '') {
    return { ok: false, error: 'a side question is its text' }
  }
  const asked: Promise<Record<string, unknown>> = $.model.fork({ prompt: framed(prompt) }).then(btwEnd, failedEnd)
  let waited: { cancel: () => void } | undefined
  const early = await Promise.race([asked, new Promise<undefined>((resolve) => (waited = $.clock.after(BTW_REFUSAL_WAIT_MS, () => resolve(undefined))))])
  waited?.cancel()
  if (early?.reason === 'nothing-to-fork') {
    return { ok: false, error: NOTHING_TO_FORK, code: 'nothing-to-fork' }
  }
  // Kept before it is answered started: a reload from here on finds it.
  state.btwOpen.add(id)
  await keepOpen($)
  return {
    ok: true,
    result: { started: true, id },
    after: () => {
      emit({ type: 'btw', phase: 'start', id })
      void asked.then((end) => ended($, id, end))
    },
  }
}
