import { ASK_TOOL } from './ask'
import { TEXT_CAP, isRecord, loopKey, state } from './bridge-state'
import type { BridgeEvent, TranscriptRecord } from './bridge-state'
import { emit, releaseStepEnd } from './bridge-stream'
import { callEnded } from './bridge-requests'

/**
 * Streaming is per content block: each response row the engine writes is
 * paired with its block (`block-row`), which settles the block.
 *
 * Row order (DC2 M4, for DC7): every row the session keeps is named once, as
 * its append resolves, so in the order it is written: a response row by its
 * `block-row`, any other by `row-seen`. Each loop's last notice is its cut,
 * which the resync carries, so a reader of the transcript knows which rows
 * the stream has accounted for and which are still to come. A loop that had
 * rows before the module loaded (a reload, a resume, a subagent running at
 * load) holds rows no notice of this module named: the module's first hello
 * seeds its cut with the last row the child read in its transcript, and a
 * model request of it begun before that hello never streams (its rows come
 * through the transcript), so no block streams whose row is at or before its
 * loop's cut. A loop the module saw from its first row (the main loop of a
 * session it started with, a subagent it saw spawned) is cut by its notices
 * alone, and streams from the start.
 *
 * Messages to the host (DC2 M4): the main loop's rows that may carry one, a
 * text row with a mark and an async ask with its result, go to the child as
 * they are kept (`export`), and the child appends them to the project's log
 * through the Stop hook's own writer and keys, so they reach the log as they
 * complete and the Stop hook's export finds them already there.
 */

/** A response row's block, as its chunks name its kind. */
const ROW_KIND: Record<string, string> = { text: 'text', thinking: 'thinking', redacted_thinking: 'thinking', tool_use: 'tool' }
/**
 * A text that may hold a mark for the host: an opening tag of the mark or one
 * of its aliases, or the header the streaming hook draws (hooks/to-human-stream.sh).
 * A superset of what sminos_marks.py reads as a span; the child's parser decides.
 */
const MAY_MARK = /<(?:message|to-human|essential|need-input|insight)>|\x1b\[1;/
/** Async asks whose other row (the call, or its result) has not been kept yet. */
const ASKS_KEPT = 50

/** A result's text: a string, or its text blocks joined. */
function resultText(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  return Array.isArray(content) ? content.map((b) => (isRecord(b) && typeof b.text === 'string' ? b.text : '')).join('\n') : ''
}

/** A row's notice: its loop's cut moves to it. */
export function noticeRow(e: BridgeEvent & { uuid: string; agentId: string | null }) {
  state.cut.set(e.agentId ?? 'main', e.uuid)
  emit(e)
}

/**
 * A row the session kept, named on the stream as it is written: a response
 * row by the block it holds (`block-row`), any other, a response row whose
 * block never streamed included, by `row-seen`. A queue record is no row of
 * the conversation, and is named by none.
 */
export function announceRow(door: string, message: { name?: string; content?: unknown }, uuid: string, agentId: string | null) {
  const content = Array.isArray(message.content) ? message.content.filter(isRecord) : []
  // A hook's success with nothing to say is raised here but never written
  // to the transcript (the engine keeps one only with content or output):
  // named, it would be a row a reader waits for and never finds.
  const isUnkept = message.name === 'hook_success' && !content.some((b) => typeof b.text === 'string' && b.text.trim() !== '')
  if (door === 'queue' || isUnkept) {
    return
  }
  if (door !== 'response' || !nameBlock(agentId, uuid, content[0])) {
    noticeRow({ type: 'row-seen', uuid, agentId, door })
  }
}

/** A row the session kept: a call's result may settle a request. */
export function observeRow(door: string, message: { name?: string; content?: unknown }, uuid: string) {
  const content = Array.isArray(message.content) ? message.content.filter(isRecord) : []
  if (door === 'tool-result') {
    for (const block of content) {
      if (block.type === 'tool_result' && typeof block.tool_use_id === 'string') {
        callEnded(block.tool_use_id, { text: resultText(block.content), uuid })
      }
    }
  }
}

/**
 * The main loop's rows that may hold a message to the host, handed to the
 * child as the transcript keeps them, so `sminos record`'s own reading of
 * them (sminos.host_events) decides what is logged: a text row that may hold
 * a mark, and an async ask once both its call and its result are kept, in
 * whichever order. A text past TEXT_CAP is left to the Stop hook's export,
 * which reads the transcript whole and appends it under the same keys.
 */
export function exportRow(door: string, message: { content?: unknown }, uuid: string, origin: unknown) {
  const content = Array.isArray(message.content) ? message.content.filter(isRecord) : []
  if (door === 'response') {
    const texts = content.filter((b) => b.type === 'text' && typeof b.text === 'string')
    if (texts.some((b) => MAY_MARK.test(b.text as string))) {
      if (texts.some((b) => (b.text as string).length > TEXT_CAP)) {
        state.log?.(`bridge: row ${uuid}: a text past ${TEXT_CAP} characters; the Stop hook exports it`)
      } else {
        emit({ type: 'export', records: [{ type: 'assistant', uuid, message: { content: texts } }] })
      }
    }
    for (const b of content) {
      if (b.type === 'tool_use' && b.name === ASK_TOOL && typeof b.id === 'string' && isRecord(b.input) && b.input.async === true) {
        keepAsk(b.id, { use: { type: 'assistant', uuid, message: { content: [b] } } })
      }
    }
  } else if (door === 'tool-result') {
    const isAsk = isRecord(origin) && origin.kind === 'tool' && origin.tool === ASK_TOOL
    for (const b of content) {
      if (b.type === 'tool_result' && typeof b.tool_use_id === 'string' && (isAsk || state.asks.has(b.tool_use_id))) {
        keepAsk(b.tool_use_id, { result: { type: 'user', uuid, message: { content: [b] } } })
      }
    }
  }
}

/** One row of an ask call; once its call and its result are both kept, the pair is exported. */
function keepAsk(id: string, row: { use?: TranscriptRecord; result?: TranscriptRecord }) {
  const ask = { ...state.asks.get(id), ...row }
  if (ask.use !== undefined && ask.result !== undefined) {
    state.asks.delete(id)
    emit({ type: 'export', records: [ask.use, ask.result] })
    return
  }
  state.asks.set(id, ask)
  if (state.asks.size > ASKS_KEPT) {
    state.asks.delete(state.asks.keys().next().value as string)
  }
}

/**
 * Pairs a response row with its block: by the row's block type and the order
 * the loop's latest request started its blocks (a tool call by its id), not
 * by the row's own position. A row whose block never streamed names none
 * (false).
 */
function nameBlock(agentId: string | null, uuid: string, block: Record<string, unknown> | undefined): boolean {
  const s = state.stepBlocks.get(loopKey(agentId))
  const kind = ROW_KIND[String(block?.type)]
  if (s === undefined || kind === undefined) {
    return false
  }
  const open = s.starts.filter((b) => b.kind === kind && !s.named.has(b.index))
  const start = (kind === 'tool' ? open.find((b) => b.id === block?.id) : undefined) ?? open[0]
  if (start === undefined) {
    return false
  }
  s.named.add(start.index)
  noticeRow({ type: 'block-row', uuid, turnId: s.turnId, agentId: s.agentId, step: s.step, index: start.index })
  if (s.heldEnd !== undefined && s.starts.every((b) => s.named.has(b.index))) {
    releaseStepEnd(loopKey(agentId))
  }
  return true
}
