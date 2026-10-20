import type { On } from 'claude-code'

import { parse } from './to-human'

// A banner shows two lines or so; the message itself is in the session.
const PREVIEW = 200

/**
 * What a row's notification says: the first message it sends, as one line,
 * the markup a banner would show raw (backticks, emphasis, a link's target,
 * the critical block's rules) dropped. Undefined for a row that sends none.
 */
export function previewOf(content: readonly { type: string; [field: string]: unknown }[]): string | undefined {
  for (const block of content) {
    if (block.type !== 'text' || typeof block.text !== 'string') continue
    for (const span of parse(block.text).spans) {
      const line = span.text
        .replace(/\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)/g, '$1')
        .replace(/`|\*\*|─+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
      if (line !== '') return line.length > PREVIEW ? `${line.slice(0, PREVIEW - 1)}…` : line
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
