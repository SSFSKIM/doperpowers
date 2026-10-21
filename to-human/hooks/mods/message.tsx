import type { On } from 'claude-code'

import { previewLine } from './notify'

/**
 * The message tool: how a session under the to-human output style sends its
 * human a message before another tool call. Written there as text, the
 * message comes back from the API (claude-opus-5-5, claude-fable-5-1) as a
 * progress note's paraphrase without its `<message>` tags and reaches no one;
 * a tool's input is never summarized, so it arrives word for word. The view
 * draws the call where it sits, and sminos exports it to the project's log
 * by this name (design: docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md).
 *
 * The name, input, result and refusal are a contract MAWS and the desk build
 * on; nothing renames them.
 */
export const MESSAGE_TOOL = 'mcp__to-human__message' // the name register() returns; a test pins it

export const DESCRIPTION =
  'Send the human a message now, word for word. Use it for a message you send before another tool call, in the same response as that call; a message at the end of your turn stays a <message> span.'

export const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    text: { type: 'string', description: 'The message, in Markdown: what you would write inside <message>…</message>.' },
  },
  required: ['text'],
}

/** What an accepted call returns. */
export const SENT = 'sent'

export const SUBAGENT_REFUSAL =
  'message is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'

/** A call with nothing to send: it is refused, so nothing is drawn, notified or exported for it. */
export const EMPTY_REFUSAL = 'message needs its text: the message to send, in Markdown.'

const ESCAPES: Record<string, string> = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f' }

/**
 * The message a call's input carries: `{ text }` once the input is whole, or,
 * while it streams as JSON text, the `text` field read so far (an escape cut
 * in two left out). Undefined when no text has arrived; never the raw JSON.
 */
export function readMessage(input: unknown): { text: string; isWhole: boolean } | undefined {
  if (typeof input === 'string') {
    try {
      return readMessage(JSON.parse(input))
    } catch {
      return partialText(input)
    }
  }
  if (typeof input === 'object' && input !== null && typeof (input as { text?: unknown }).text === 'string') {
    return { text: (input as { text: string }).text, isWhole: true }
  }
  return undefined
}

function partialText(json: string): { text: string; isWhole: boolean } | undefined {
  const start = /"text"\s*:\s*"/.exec(json)
  if (start === null) return undefined
  let text = ''
  for (let at = start.index + start[0].length; at < json.length; at++) {
    const char = json[at]!
    if (char === '"') break
    if (char !== '\\') {
      text += char
      continue
    }
    const escape = json[at + 1]
    if (escape === undefined) break
    if (escape === 'u') {
      const hex = json.slice(at + 2, at + 6)
      if (!/^[0-9a-fA-F]{4}$/.test(hex)) break
      text += String.fromCharCode(parseInt(hex, 16))
      at += 5
      continue
    }
    text += ESCAPES[escape] ?? escape
    at += 1
  }
  return { text, isWhole: false }
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/**
 * Registers the tool and serves it. It is registered as an interactive
 * session starts (nobody reads a headless session's report), except under
 * MAWS (`MAWS_NATIVE_TO_HUMAN`), whose launches register their own
 * `mcp__maws__message`. It is always loaded, so the first message costs no
 * ToolSearch. A call from the main conversation raises the person's
 * notification and returns `sent`; a subagent's is refused, since only the
 * main conversation reaches the human. The notification is raised here, not
 * from the call's row, because the row is kept before the call runs and a
 * refused call sends nothing.
 */
export function registerMessage(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    const maws = await $.env.get('MAWS_NATIVE_TO_HUMAN')
    if (maws === undefined || maws === '') {
      try {
        const { tool } = await $.tool.register({ name: 'message', description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
        if (tool !== MESSAGE_TOOL) {
          $.ui.log(`to-human: the message tool registered as ${tool}, not ${MESSAGE_TOOL}: the view and the export know it by ${MESSAGE_TOOL}`, { to: 'debug' })
        }
      } catch (error) {
        $.ui.log(`to-human: the message tool is not registered: ${message(error)}`, { to: 'debug' })
      }
    }
    return next(e)
  })

  // A plugin's tool is an MCP tool to the engine, which defers it behind
  // ToolSearch: the model would see its name alone.
  on('tool.describe', { tool: MESSAGE_TOOL }, async (_, e, next) => ({ ...(await next(e)), isDeferred: false }))

  on('tool.call', { tool: MESSAGE_TOOL }, async ($, e) => {
    if (e.agentId !== undefined) {
      return { deny: SUBAGENT_REFUSAL }
    }
    const text = (e as { text?: unknown }).text
    if (typeof text !== 'string' || text.trim() === '') {
      return { deny: EMPTY_REFUSAL }
    }
    // Not awaited, as a span's notification is not: the person's hooks it runs would hold the call.
    const preview = previewLine(text)
    if (preview !== undefined && (await $.env.get('SMNS_INTERNAL')) === undefined) {
      $.ui.notify(preview).catch((error) => $.ui.log(`to-human: a message's notification failed (${String(error)})`, { to: 'debug' }))
    }
    return { result: SENT }
  })
}
