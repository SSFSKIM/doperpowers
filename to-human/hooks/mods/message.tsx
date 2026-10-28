import type { ApiContentBlock, On } from 'claude-code'

import { previewLine } from './notify'

/**
 * The message tool: how a session under the to-human output style sends its
 * human every message; a `<message>` tag is the form only where the tool is
 * not registered. Written as text before a tool call, a message comes back
 * from the API (claude-opus-5-5, claude-fable-5-1) as a progress note's
 * paraphrase without its tags and reaches no one; a tool's input is never
 * summarized, so it arrives word for word. The view draws the call where it
 * sits, and sminos exports it to the project's log by this name (design:
 * docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md). A
 * message that ends the turn says so (`final: true`), and the turn ends once
 * it is sent, with no request after it (`registerMessage`).
 *
 * The name, input, result and refusal are a contract MAWS and the desk build
 * on; nothing renames them.
 */
export const MESSAGE_TOOL = 'mcp__to-human__message' // the name register() returns; a test pins it

// When to use it is the style's rule, not the description's: the style is its one source.
export const DESCRIPTION = 'Send the human a message.'

export const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    text: { type: 'string', description: 'The message, in Markdown.' },
    final: {
      type: 'boolean',
      description: 'True when this message ends your turn: once it is sent the turn ends, and you write nothing after it.',
    },
  },
  required: ['text'],
}

/**
 * The response the plugin answers in place of the request that would follow
 * a final message: what the transcript keeps as the turn's last row (no
 * request id, the engine's `answeredWithoutRequest` flag), which the view
 * draws as nothing (`isMadeUp`).
 */
export const FINAL_ANSWER = 'Message sent to the human.'

/**
 * The output style the tool is registered under, as `/config`'s `outputStyle`
 * row names it (`$.config.list()`, read live on 2.1.305: a plugin's style is
 * `<plugin>:<name>`). Under any other style no rule tells the model when to
 * use the tool, so it is not offered.
 */
export const TO_HUMAN_STYLE = 'doperpowers:to-human'

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

const isFinal = (input: unknown) => typeof input === 'object' && input !== null && (input as { final?: unknown }).final === true

const resultText = (content: unknown): string | undefined =>
  typeof content === 'string'
    ? content
    : Array.isArray(content) && content.length === 1 && (content[0] as ApiContentBlock).type === 'text'
      ? String((content[0] as ApiContentBlock).text)
      : undefined

/**
 * The attachments the engine puts beside a request whatever happened before
 * it, which ask nothing of the model, so a final message still ends the turn
 * with them unread: the style's reminder (`<style> output style is active`)
 * and the token budget's, live on 2.1.312 after a message call's result, and
 * the announcements of tools and skills now available. In the owner's
 * transcripts (2026-10-27, 672 responses of message calls alone) these were
 * what stood after the results but for a prompt queued mid-turn
 * (`queued_command`, 37 of them), which is for the model to read, as is any
 * other attachment.
 */
export const STANDING_ATTACHMENTS: ReadonlySet<string> = new Set(['output_style', 'total_tokens_reminder', 'deferred_tools_delta', 'skill_listing'])

/** What the main loop kept since its last step began, as the next request would carry it. */
type Since = { calls: number; finals: number; sent: number; isOther: boolean }

const fresh = (): Since => ({ calls: 0, finals: 0, sent: 0, isOther: false })

/**
 * One kept main-loop row taken into `since`: a response's calls (any but the
 * message tool's is other), a tool result (any but `sent` is other: a
 * refusal, an error, context beside it), a standing attachment (nothing), a
 * row no request carries or that carries no block (nothing), and any other
 * row a request carries (a prompt typed mid-turn, a delivery, a hook's
 * context, a reminder, a steer).
 */
export function note(since: Since, door: string, message: { role?: string; name?: string; content: readonly ApiContentBlock[] }): Since {
  if (message.role === undefined || message.content.length === 0) {
    return since
  }
  if (door === 'response') {
    const calls = message.content.filter((block) => block.type === 'tool_use')
    return {
      ...since,
      calls: since.calls + calls.length,
      finals: since.finals + calls.filter((call) => call.name === MESSAGE_TOOL && isFinal(call.input)).length,
      isOther: since.isOther || calls.some((call) => call.name !== MESSAGE_TOOL),
    }
  }
  if (door === 'tool-result') {
    const isSent = (block: ApiContentBlock) => block.type === 'tool_result' && block.is_error !== true && resultText(block.content) === SENT
    return { ...since, sent: since.sent + message.content.filter(isSent).length, isOther: since.isOther || !message.content.every(isSent) }
  }
  if (door === 'attachment' && message.name !== undefined && STANDING_ATTACHMENTS.has(message.name)) {
    return since
  }
  return { ...since, isOther: true }
}

/** Whether the main loop's step after `since` would carry nothing for the model but final messages sent. */
export const endsOnFinal = (since: Since) => since.finals > 0 && since.sent === since.calls && !since.isOther

let isRegistered = false
// The main loop's rows since its last step began.
let since = fresh()
// Whether a made-up response streamed and its row is still to be kept; and the rows kept for one.
let isMakingUp = false
const madeUpRows = new Set<string>()

const isFinalAnswer = (text: string) => text.trim() === FINAL_ANSWER

/**
 * Whether the assistant row `id`, which reads `text`, is the response this
 * module made up after a final message, not a model's saying the same: a row
 * kept as one, or, while the made-up response's row is still to be kept, a
 * row with its text. The view reads a resumed transcript's for itself.
 */
export const isMadeUp = (id: string, text: string) => isFinalAnswer(text) && (madeUpRows.has(id) || isMakingUp)

/** Whether this session registered the tool under its contract name: the reminder names it. */
export const isMessageToolOn = () => isRegistered

/**
 * The MAWS contract version from which MAWS offers no message tool of its
 * own, its sessions sending through this one (MAWS's Decision Log 92).
 */
const MAWS_WITHOUT_TOOL = 8

/**
 * Whether the launch is MAWS's and MAWS registers its own message tool:
 * `MAWS_NATIVE_TO_HUMAN`, the contract version MAWS advertises, is a number
 * below `MAWS_WITHOUT_TOOL`. Unset, empty or from 8 on, this one registers.
 */
const mawsHasOwnTool =(advertised: string | undefined) =>
  advertised !== undefined && advertised.trim() !== '' && Number(advertised) < MAWS_WITHOUT_TOOL

/**
 * Registers the tool and serves it. It is registered as an interactive
 * session starts under the to-human style (nobody reads a headless session's
 * report, and only the style says when to use the tool), except under a MAWS
 * that registers its own `mcp__maws__message` (`mawsHasOwnTool`: so a
 * session never has two message tools, or none, across MAWS's switch to
 * this one). The style is read once, at the start: a session that
 * switches to the style in `/config` gets the tool at its next start. It is always loaded, so the first message costs no
 * ToolSearch. A call from the main conversation raises the person's
 * notification and returns `sent`; a subagent's is refused, since only the
 * main conversation reaches the human. The notification is raised here, not
 * from the call's row, because the row is kept before the call runs and a
 * refused call sends nothing.
 *
 * A final message ends the turn once it is sent. The engine would otherwise
 * ask the model again after every tool result, and that request, over the
 * whole context, buys a closing text that mostly restates the message. So the
 * main loop's next step is answered here, without `next` and so without a
 * request, by a made-up response (`FINAL_ANSWER`, stopping `end_turn`), and
 * the turn ends as any answered turn does. Only when that step would carry
 * nothing else for the model, which the main loop's rows kept since the
 * step before tell (`note`, `endsOnFinal`): a final call beside another
 * tool's, a refused call, or anything kept beside the results but the
 * engine's standing reminders lets the request go. A subagent's step is
 * never answered here (its calls are refused), nor a turn's first. The step
 * answered here reaches no hook beneath, so sminos' bridge streams no step
 * for it; the call's rows and the made-up response's are kept and exported
 * as any row is, and the view draws the made-up one as nothing.
 */
export function registerMessage(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    isRegistered = false
    const maws = await $.env.get('MAWS_NATIVE_TO_HUMAN')
    let style: unknown
    try {
      style = (await $.config.list()).find((row) => row.key === 'outputStyle')?.value
    } catch (error) {
      $.ui.log(`to-human: the message tool is not registered: the output style could not be read (${message(error)})`, { to: 'debug' })
    }
    if (!mawsHasOwnTool(maws) && style === TO_HUMAN_STYLE) {
      try {
        const { tool } = await $.tool.register({ name: 'message', description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
        isRegistered = tool === MESSAGE_TOOL
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
    // Only the main conversation reaches the human, by the human's ruling;
    // letting a subagent message them directly is SSFSKIM/doperpowers#310.
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

  on('session.append', { door: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && result.deny === undefined) {
      const [block, ...rest] = result.message.content
      if (isMakingUp && e.door === 'response' && rest.length === 0 && block?.type === 'text' && isFinalAnswer(String(block.text))) {
        madeUpRows.add(result.uuid)
        isMakingUp = false
      }
      since = note(since, e.door, result.message)
    }
    return result
  })

  on('turn.step', { turnId: /^/ }, async function* ($, e, next) {
    if (e.agentId !== undefined) {
      return yield* next(e)
    }
    // A made-up response's row is kept before the main loop's next step.
    isMakingUp = false
    const before = since
    since = fresh()
    // A turn's first step follows the person's prompt, not a message (a turn cut short after one).
    if (e.index === 0 || before.finals === 0) {
      return yield* next(e)
    }
    if (!endsOnFinal(before)) {
      $.ui.log('to-human: the turn goes on after a final message: the request carries more for the model', { to: 'debug' })
      return yield* next(e)
    }
    $.ui.log('to-human: a final message ends the turn, with no request after it', { to: 'debug' })
    isMakingUp = true
    yield { kind: 'text', index: 0, text: FINAL_ANSWER }
    yield { kind: 'stop', stopReason: 'end_turn', usage: null }
    return { turnId: e.turnId, index: e.index, answer: FINAL_ANSWER, toolUses: [], stopReason: 'end_turn', usage: null }
  })
}
