import type { On } from 'claude-code'

import { parse } from './to-human'

// A banner shows two lines or so; the message itself is in the session.
const PREVIEW = 200

/**
 * What a message's notification says, whether it was sent as a span or
 * through the message tool: the message as one line, the markup a banner
 * would show raw (backticks, emphasis, a link's target, a quote's markers,
 * the rules of a critical block in the earlier form) dropped, cut to a
 * banner's length. Undefined when nothing is left.
 */
export function previewLine(text: string): string | undefined {
  const line = text
    .replace(/\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)/g, '$1')
    .replace(/^[ \t]*>/gm, '')
    .replace(/`|─+/g, ' ')
    .replace(/\*+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (line === '') return undefined
  return line.length > PREVIEW ? `${line.slice(0, PREVIEW - 1)}…` : line
}

/**
 * What a row's notification says: its first message that says something
 * (`previewLine`). Undefined for a row that sends none. A `tool_use` block
 * raises nothing here: the message tool notifies from its call, once the call
 * is accepted.
 */
export function previewOf(content: readonly { type: string; [field: string]: unknown }[]): string | undefined {
  for (const block of content) {
    if (block.type !== 'text' || typeof block.text !== 'string') continue
    for (const span of parse(block.text).spans) {
      const line = previewLine(span.text)
      if (line !== undefined) return line
    }
  }
  return undefined
}

/**
 * Tells the person when the model sends them a message: each response row
 * of the main conversation that carries one raises a native notification
 * through their own channel (`$.ui.notify`), which their `Notification`
 * hooks read as `plugin_notification`. It is raised as the row is kept, so a
 * message sent mid-turn reaches them then, not when the turn stops, and a
 * turn that sends none raises nothing. Not awaited: the hooks it runs (a
 * settings hook calling out to a terminal app) would hold the row's append,
 * and the engine waits for each row's append before it passes the block on.
 * A sminos internal fork (`SMNS_INTERNAL`, a headless session under the
 * person's settings that nobody reads) raises none.
 */
export function registerNotify(on: On) {
  on('session.append', { door: 'response' }, async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && stored.deny === undefined && (await $.env.get('SMNS_INTERNAL')) === undefined) {
      const preview = previewOf(stored.message.content)
      if (preview !== undefined) {
        $.ui.notify(preview).catch((error) => $.ui.log(`to-human: a message's notification failed (${String(error)})`, { to: 'debug' }))
      }
    }
    return stored
  })
}
