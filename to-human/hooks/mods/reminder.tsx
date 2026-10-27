import type { On } from 'claude-code'

import { isMessageToolOn } from './message'

/**
 * The context sizes, in tokens, past which the next prompt carries the
 * reminder again. The style is attached once, at the head of the context
 * window, so by these sizes it stands that far back. A transcript audit
 * (2026-10-27, 186 sessions) found the model forgetting to send what it wrote
 * for the human mostly in long windows: 85% of the misses fell at 150k tokens
 * or more. The owner set these points, and no more, so a reminder stays rare.
 */
export const REMIND_AT = [150_000, 300_000, 450_000] as const

export const REMINDER =
  "Output style active: the human reads only what you send them. Send it with the message tool (`mcp__to-human__message`) within a turn, or wrap the turn's final message in a `<message>` tag."

/** How many of the reminder's points a context of `tokens` has passed: 0 below the first. */
export function pointOf(tokens: number | undefined): number {
  return REMIND_AT.filter((at) => tokens !== undefined && tokens >= at).length
}

/**
 * Puts the reminder beside the prompt (as `prompt.submit` context the model
 * reads and the person never sees) at a session's start and once the context
 * passes each of `REMIND_AT`. The first prompt this module meets is a
 * session's start when no response has been answered yet. Otherwise the module
 * has started over mid-session (a reload), and it takes the point the context
 * stands at without reminding, so updates do not repeat the reminder. A
 * compaction re-arms the points: the context starts over, and the engine
 * attaches the style again. Only where the message tool is registered, since
 * the reminder names it. A prompt that runs a slash command carries none. A
 * prompt dropped beneath gives the reminder to the next one.
 */
export function registerReminder(on: On) {
  // The highest point reminded in this window; undefined until the first prompt.
  let reached: number | undefined

  on('session.compact', { trigger: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && e.trigger !== 'precompute' && result.skip === undefined) {
      reached = 0
    }
    return result
  })

  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    if (!isMessageToolOn() || e.command !== undefined) {
      return next(e)
    }
    const { tokens } = (await $.session.usage()).context
    const point = pointOf(tokens)
    if (reached === undefined && tokens !== undefined) {
      reached = point
      return next(e)
    }
    if (reached !== undefined) {
      // A compaction that raised no event leaves the context below a point it had passed.
      reached = Math.min(reached, point)
      if (point === reached) {
        return next(e)
      }
    }
    const before = reached
    reached = point
    const result = await next({ ...e, context: [...(e.context ?? []), REMINDER] })
    if (result.drop !== undefined) {
      reached = before
    }
    return result
  }).catch((_, e, next) => next(e))
}
