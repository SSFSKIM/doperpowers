import type { On } from 'claude-code'

import { isMessageToolOn } from './message'

/**
 * The context sizes, in tokens, past which the next prompt carries the
 * reminder. The style is attached once, at the head of each context window,
 * so by these sizes it stands that far back. A transcript audit
 * (2026-10-27, 186 sessions) found the model forgetting to send what it wrote
 * for the human mostly in long windows: 85% of the misses fell at 150k tokens
 * or more. The owner set these points, and no more, so a reminder stays rare.
 */
export const REMIND_AT = [150_000, 300_000, 450_000] as const

export const REMINDER =
  'Output style active: the human reads only what you send with the message tool (`mcp__to-human__message`). When a message ends your turn, send it with `final: true`.'

/**
 * What the engine's own style reminder gains: the `output_style` attachment
 * (`<style> output style is active. Remember to follow the specific guidelines
 * for this style.`), which the engine puts beside every request of the main
 * loop, the turn's prompt and each tool result alike, so it stands where the
 * model decides whether its turn ends. It names no rule of the style; this one
 * saves a request each turn: a final message ends the turn with none after it
 * (the message mod), and only one sent alone. The engine caches an
 * attachment's answer process-wide by its UUID, and a fork inherits main's, so
 * the answer cannot depend on the loop that asks first; it depends on the
 * engine's text and on whether the message tool is registered, which hold for
 * every loop.
 */
export const STYLE_FINAL = 'When a message is the last thing you do in a turn, send it alone with `final: true`.'

/** How many of the reminder's points a context of `tokens` has passed: 0 below the first. */
export function pointOf(tokens: number | undefined): number {
  return REMIND_AT.filter((at) => tokens !== undefined && tokens >= at).length
}

/**
 * Puts the reminder beside the prompt (as `prompt.submit` context the model
 * reads and the person never sees) once the context passes each of
 * `REMIND_AT`, and nowhere else: the engine attaches the style's whole body at
 * the head of every context window (a session's start, a resume, a
 * compaction, `/clear`), where a reminder would only repeat it. The module
 * takes the point the context stands at from the first prompt it meets, a
 * slash command's included, and reminds nothing then, so a fresh session, a
 * reload and a resume each start from where the context stands and updates
 * do not repeat the reminder; a figure the engine does not have (before the
 * first response, or after a compaction until the next one) stands at no
 * point. A compaction re-arms the points, and so does a figure that fell
 * below one without the event (a `/clear`). Only where the message tool is
 * registered, since the reminder names it. A prompt that runs a slash command
 * carries none. A prompt dropped beneath gives the reminder to the next one,
 * unless a newer prompt moved the point while it waited. The engine's style
 * reminder carries `STYLE_FINAL` after its own words wherever the message tool
 * is registered, the same text for every loop (see `STYLE_FINAL`).
 */
export function registerReminder(on: On) {
  // The highest point reminded in this window; undefined until the first
  // prompt. Every move replaces the object, so a dropped prompt knows whether
  // the point is still the one it set.
  let reached: { point: number } | undefined

  // Loop-independent: see STYLE_FINAL.
  on('prompt.attachment', { type: 'output_style' }, async (_, e, next) => {
    const result = await next(e)
    if (result.text === null || !isMessageToolOn()) {
      return result
    }
    return { ...result, text: `${result.text} ${STYLE_FINAL}` }
  })

  on('session.compact',{ trigger: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && e.trigger !== 'precompute' && result.skip === undefined) {
      reached = { point: 0 }
    }
    return result
  })

  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    if (!isMessageToolOn()) {
      return next(e)
    }
    const point = pointOf((await $.session.usage()).context.tokens)
    if (reached === undefined) {
      reached = { point }
      return next(e)
    }
    if (e.command !== undefined) {
      return next(e)
    }
    if (point <= reached.point) {
      if (point < reached.point) {
        // A compaction that raised no event leaves the context below a point it had passed.
        reached = { point }
      }
      return next(e)
    }
    const before = reached
    const mine = (reached = { point })
    const result = await next({ ...e, context: [...(e.context ?? []), REMINDER] })
    if (result.drop !== undefined && reached === mine) {
      reached = before
    }
    return result
  }).catch((_, e, next) => next(e))
}
