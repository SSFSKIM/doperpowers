import type { SessionMessage } from 'claude-code'

import { ASK_TOOL, DELIVERY_HEAD, PLUGIN } from './ask'
import { TEXT_CAP, isRecord, loopKey, state } from './bridge-state'
import type { BridgeEvent, HeldRow, TranscriptRecord } from './bridge-state'
import { emit, hold, isHold, releaseStepEnd } from './bridge-stream'
import type { Hold } from './bridge-stream'
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
 * A compaction's rows: the engine writes those of a manual compaction (the
 * person's /compact, a command run, a plugin's `$.session.compact`) through
 * no `session.append` (live, 2.1.301; an auto compaction's it raises), so no
 * hook names them. Once a compaction stands, a hold (bridge-stream.tsx) keeps
 * everything later in the queue while the rows past the loop's cut that no
 * notice named, up to the first one a later notice names, are read from the
 * transcript, and their `row-seen`s (door `compaction`) take its place.
 *
 * Messages to the host (DC2 M4): the main loop's rows that may carry one, a
 * text row with a mark, an async ask with its result, a message tool's call
 * with its result, and a row that may answer an ask, go to the child as they
 * are kept (`export`), and the child appends them to the project's log
 * through the Stop hook's own writer and keys, so they reach the log as they
 * complete and the Stop hook's export finds them already there.
 *
 * A delivery's row (DC8.G6): the prompt row a delivery submitted becomes is
 * named once it is kept (`delivered` `entered`, enteredRow).
 */

/** A response row's block, as its chunks name its kind. */
const ROW_KIND: Record<string, string> = { text: 'text', thinking: 'thinking', redacted_thinking: 'thinking', tool_use: 'tool' }
/**
 * A text that may hold a mark for the host: an opening tag of the mark or one
 * of its aliases, or the header the streaming hook draws (hooks/to-human-stream.sh).
 * A superset of what sminos_marks.py reads as a span; the child's parser decides.
 */
const MAY_MARK = /<(?:message|to-human|essential|need-input|insight)>|\x1b\[1;/
/** Calls paired for the export (async asks, message calls) whose other row (the call, or its result) has not been kept yet. */
const PAIRS_KEPT = 50
/** MAWS's ask tool, which a session under MAWS asks through instead of the plugin's (sminos.MAWS_ASK_TOOL). */
const MAWS_ASK_TOOL = 'mcp__maws__ask'
/** A call of an ask tool that does not wait for its answer: the plugin's with `async` true, MAWS's with `blocking` false. */
const isAsyncAsk = (name: unknown, input: Record<string, unknown>) =>
  (name === ASK_TOOL && input.async === true) || (name === MAWS_ASK_TOOL && input.blocking === false)
/**
 * The message tools a transcript may hold (sminos.MESSAGE_TOOLS): the to-human
 * plugin's, and MAWS's own, which a MAWS launch registers in its place. sminos
 * declares no dependency on either, so it knows them by name.
 */
const MESSAGE_TOOLS: readonly string[] = ['mcp__to-human__message', 'mcp__maws__message']
/** A call of a message tool. */
const isMessageCall = (b: Record<string, unknown>) => b.type === 'tool_use' && typeof b.id === 'string' && MESSAGE_TOOLS.includes(String(b.name))
/** A record holding a text past TEXT_CAP, a message call's or a text block's: the Stop hook's to export. */
const isLong = (record: TranscriptRecord) =>
  'message' in record &&
  record.message.content.some((b) => {
    const text = b.type === 'text' ? b.text : isMessageCall(b) && isRecord(b.input) ? b.input.text : undefined
    return typeof text === 'string' && text.length > TEXT_CAP
  })
/** The tag a MAWS steer opens with (sminos.MAWS_STEER_RE). */
const MAWS_STEER = '[MAWS ask '
/** A text that may answer an async ask: the ask mod's delivery, or a MAWS steer. The child's parser decides. */
const mayAnswer = (text: string) => text.includes(DELIVERY_HEAD) || text.includes(MAWS_STEER)
/**
 * The engine's framing of an attachment's rendering, which session.append
 * hands in place of its payload (2.1.302): a hook's context is
 * `<system-reminder>\n<hook> hook additional context: <entries, a line
 * apart>\n</system-reminder>` (its `ROe`); the human's prompt taken into a
 * running turn is the prompt between MID_TURN_OPEN and MID_TURN_CLOSE (its
 * `oJe`, `D4n` and `Al`; every rendered one in this machine's transcripts,
 * 2.1.259–2.1.302, was).
 */
const CONTEXT_OPEN = '<system-reminder>\n'
const CONTEXT_LABEL = ' hook additional context: '
const CONTEXT_CLOSE = '\n</system-reminder>'
const MID_TURN_OPEN = '<system-reminder>\nThe user sent a new message while you were working:\n'
const MID_TURN_CLOSE =
  '\n\nThis is how Claude Code surfaces messages the user sends mid-turn — within the running turn, often alongside the next tool result, rather than as a separate conversation turn. Address the message above as you continue this turn.\n</system-reminder>'
/**
 * What the engine's renderings write for a `<` they escape (a system-reminder
 * tag in a hook's context, in another sender's prompt, in an id'd reminder):
 * a rendering holding it is not read back, since a literal one the human
 * typed reads the same.
 */
const ESCAPED = '&lt;'
/**
 * A row's origin as the transcript names it, where sminos reads whether a
 * steer is the human's: the event's `composer` and `bridge` are the
 * transcript's `human`; every other kind is named alike in both. A row the
 * transcript keeps with no origin reaches the hook as `unclassified`, which
 * sminos reads as not the human's: such a row waits for the Stop hook's
 * export, which reads the transcript's own.
 */
const transcriptOrigin = (origin: unknown) => (isRecord(origin) && (origin.kind === 'composer' || origin.kind === 'bridge') ? { kind: 'human' } : origin)
/** A row's text blocks; a string content is one. */
function textBlocks(content: unknown): { type: 'text'; text: string }[] {
  if (typeof content === 'string') {
    return [{ type: 'text', text: content }]
  }
  return Array.isArray(content) ? content.filter((b): b is { type: 'text'; text: string } => isRecord(b) && b.type === 'text' && typeof b.text === 'string') : []
}
/** How many of each loop's latest notices' rows are remembered, to tell the rows past its cut no notice named. */
const NAMED_KEPT = 200
/**
 * After a compaction, its rows are looked for on disk this often, so many
 * times at most (the engine flushed them about 130 ms after the compaction
 * resolved, live, 2.1.301; the consumer releases an unnamed row after 2 s).
 */
export const ROWS_POLL_MS = 50
export const ROWS_POLLS = 30

/** A result's text: a string, or its text blocks joined. */
function resultText(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  return Array.isArray(content) ? content.map((b) => (isRecord(b) && typeof b.text === 'string' ? b.text : '')).join('\n') : ''
}

/** A row's notice: its loop's cut moves to it. */
export function noticeRow(e: BridgeEvent & { uuid: string; agentId: string | null }) {
  const loop = e.agentId ?? 'main'
  state.cut.set(loop, e.uuid)
  remember(loop, e.uuid)
  emit(e)
}

function remember(loop: string, uuid: string) {
  let named = state.named.get(loop)
  if (named === undefined) {
    named = new Set()
    state.named.set(loop, named)
  }
  named.add(uuid)
  if (named.size > NAMED_KEPT) {
    named.delete(named.values().next().value as string)
  }
}

/**
 * A compaction that stood in a loop (the main one, or a subagent's): its
 * rows past the loop's cut that no notice named, each named by `row-seen`
 * once they are on disk, ahead of anything the session did after it. `messages`
 * is the compaction's result: the first, its summary, carries the summary
 * row's uuid as its `handle` (live, 2.1.301), which says when its rows are on
 * disk, or that the engine raised them and each is named already.
 */
export function compacted(agentId: string | null, messages: readonly SessionMessage[] | undefined) {
  const loop = agentId ?? 'main'
  // The main conversation compacted holds its rows in a summary, not
  // verbatim, so the delivered rows still tracked (bridge.tsx,
  // recheckDeliveries) would all read as missing and be given twice: every
  // one is let go. A row a rewind left on a dead branch before the
  // compaction is the accepted loss.
  if (agentId === null) {
    state.deliveredRows = []
    state.compactions++
  }
  const after = state.cut.get(loop)
  const summary = messages?.[0]?.handle
  // With no cut yet (a module that has not read its first hello) there is
  // nothing to read past, and with no summary row (a hook answered with
  // messages of its own) nothing says when the rows are in: they are
  // released unnamed, as any row no notice names.
  if (after === undefined || typeof summary !== 'string') {
    return
  }
  // The rows the loop's notices named so far, kept with the hold: one of them
  // may lie past the cut on disk (the engine's write order), however many
  // notices come after it.
  const h: Hold = { type: '@hold', loop, after, named: new Set(state.named.get(loop)), run: () => nameCompaction(h, agentId, summary) }
  hold(h)
}

/**
 * The compaction's rows, read until its summary row is past the cut on disk,
 * and once more a poll later, so the rest of the batch it was flushed in is
 * whole: the unnamed ones of that read, in disk order, up to the first row a
 * notice queued behind the hold names (it and the rows after it were written
 * after a row the session named since, a later compaction's included). None
 * when the summary was named (the engine raised its rows), when it did not
 * come within ROWS_POLLS reads, or when the hold left the queue (a resync's
 * cut covers its rows).
 */
async function nameCompaction(h: Hold, agentId: string | null, summary: string): Promise<BridgeEvent[]> {
  const { loop, after } = h
  let wasOnDisk = false
  for (let poll = 1; ; poll++) {
    const rows = await state.rowsAfter?.(loop, after).catch(() => undefined)
    const at = state.queue.indexOf(h)
    if (at === -1) {
      return []
    }
    // The loop's notices since the hold was placed: all still queued behind
    // it, as the poster posts nothing past a hold and a resync that took any
    // of them took the hold too.
    const queued = new Set(state.queue.slice(at + 1).filter((e) => (e.type === 'block-row' || e.type === 'row-seen') && (e.agentId ?? 'main') === loop).map((e) => e.uuid))
    const live = state.named.get(loop)
    const isNamed = (u: string) => h.named.has(u) || live?.has(u) === true || queued.has(u)
    if (isNamed(summary)) {
      return []
    }
    const end = rows?.findIndex((u) => queued.has(u)) ?? -1
    const unnamed = rows?.slice(0, end === -1 ? undefined : end).filter((u) => !isNamed(u)) ?? []
    const isOnDisk = rows?.includes(summary) === true
    if (isOnDisk && (wasOnDisk || poll >= ROWS_POLLS)) {
      for (const u of unnamed) {
        remember(loop, u)
      }
      const last = unnamed[unnamed.length - 1]
      if (last !== undefined) {
        // Every later hold of the loop counts them as named, and one placed at
        // the same cut (nothing of the loop came between them) reads past them.
        for (const e of state.queue) {
          if (isHold(e) && e !== h && e.loop === loop) {
            unnamed.forEach((u) => e.named.add(u))
            if (e.after === after) {
              e.after = last
            }
          }
        }
        // The cut moves to them unless a later notice, queued behind the hold, moved it first.
        if (state.cut.get(loop) === after) {
          state.cut.set(loop, last)
        }
      }
      const t = Date.now()
      return unnamed.map((uuid) => ({ type: 'row-seen', uuid, agentId, door: 'compaction', t }))
    }
    if (poll >= ROWS_POLLS || state.after === undefined) {
      state.log?.(`bridge: a compaction's rows past ${after} were not on disk after ${ROWS_POLLS} reads; they go unnamed`)
      return []
    }
    wasOnDisk = isOnDisk
    const wait = state.after
    await new Promise<void>((resolve) => wait(ROWS_POLL_MS, resolve))
  }
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
 * The main loop's rows that may hold a message to the host, or an answer to
 * its question, handed to the child in the shape the transcript keeps them,
 * so `sminos record`'s own reading of them (sminos.host_events) decides what
 * is logged: a text row that may hold a mark; an async ask or a message
 * tool's call once both its call and its result are kept, in whichever order
 * (the child logs the call only if its result is no error); a row that may
 * answer an ask (answerRecord). A text past TEXT_CAP, a message call's
 * included, is left to the Stop hook's export, which reads the transcript
 * whole and appends it under the same keys.
 *
 * The log keeps events in the order they are appended, so the exports keep
 * the transcript's (exportInOrder): a row holding a message call is held
 * until every message call in it has its result, then goes once, its texts
 * and calls with all their results, so the child reads its blocks in order
 * (a span's src counts the row's spans); what the main loop keeps after it
 * waits behind it.
 */
export function exportRow(door: string, message: { name?: string; content?: unknown }, uuid: string, origin: unknown) {
  const content = Array.isArray(message.content) ? message.content.filter(isRecord) : []
  if (door === 'response') {
    const texts = textBlocks(content)
    const sent = content.filter((b) => b.type === 'text' || isMessageCall(b))
    const row: TranscriptRecord = { type: 'assistant', uuid, message: { content: sent } }
    const calls = content.filter(isMessageCall)
    if (calls.length > 0 && !isLong(row)) {
      state.exportHold.push({ row, calls: new Set(calls.map((b) => String(b.id))), results: [] })
      calls.forEach((b) => keepPair(String(b.id), { use: row }))
      boundHold()
    } else if (texts.some((b) => MAY_MARK.test(b.text))) {
      exportRecord(uuid, texts, { type: 'assistant', uuid, message: { content: texts } })
    }
    for (const b of content) {
      if (b.type === 'tool_use' && typeof b.id === 'string' && isRecord(b.input) && (isAsyncAsk(b.name, b.input) || (isMessageCall(b) && isLong(row)))) {
        keepPair(b.id, { use: { type: 'assistant', uuid, message: { content: [b] } } })
      }
    }
  } else if (door === 'tool-result') {
    const tool = isRecord(origin) && origin.kind === 'tool' ? String(origin.tool) : undefined
    const isPaired = tool !== undefined && (tool === ASK_TOOL || tool === MAWS_ASK_TOOL || MESSAGE_TOOLS.includes(tool))
    for (const b of content) {
      if (b.type === 'tool_result' && typeof b.tool_use_id === 'string' && (isPaired || state.pairs.has(b.tool_use_id))) {
        keepPair(b.tool_use_id, { result: { type: 'user', uuid, message: { content: [b] } } })
      }
    }
  } else {
    const answer = answerRecord(door, message, uuid, origin)
    if (answer !== undefined) {
      exportRecord(uuid, answer.texts, answer.record)
    }
  }
}

/** One row's export, unless a text of it is past TEXT_CAP: that row is the Stop hook's, said in the debug log. */
function exportRecord(uuid: string, texts: { text: string }[], record: TranscriptRecord) {
  if (texts.some((b) => b.text.length > TEXT_CAP)) {
    state.log?.(`bridge: row ${uuid}: a text past ${TEXT_CAP} characters; the Stop hook exports it`)
    return
  }
  exportInOrder([record])
}

/**
 * An export, in the transcript's order: while a row holding a message call
 * waits for its calls' results (a HeldRow in `state.exportHold`), it waits
 * behind it.
 */
function exportInOrder(records: TranscriptRecord[]) {
  if (state.exportHold.length === 0) {
    emit({ type: 'export', records })
    return
  }
  state.exportHold.push(records)
  boundHold()
}

/**
 * A result the bridge never sees (kept while it was down, or refused beneath)
 * holds at most PAIRS_KEPT exports, held rows of later message calls among
 * them: past that the waiting row at the head is given up, exported with the
 * results it has, and the Stop hook exports the calls it lacks.
 */
function boundHold() {
  for (let head = state.exportHold[0]; state.exportHold.length > PAIRS_KEPT && head !== undefined && !Array.isArray(head); head = state.exportHold[0]) {
    state.log?.(`bridge: row ${head.row.uuid}: no result for ${[...head.calls].join(', ')} after ${PAIRS_KEPT} exports; the Stop hook exports them`)
    head.calls.forEach((id) => state.pairs.delete(id))
    head.calls.clear()
    releaseHeld()
  }
}

/** The held row waiting for this message call's result, if any. */
const heldFor = (id: string) => state.exportHold.find((e): e is HeldRow => !Array.isArray(e) && e.calls.has(id))

/** A held row's call settled (with its result) or given up (without): once none waits, the row goes, and what waited behind it. */
function settleCall(held: HeldRow, id: string, result?: TranscriptRecord) {
  held.calls.delete(id)
  if (result !== undefined) {
    held.results.push(result)
  }
  releaseHeld()
}

/** The exports at the head of the hold, in order, up to the first row still waiting for a call. */
function releaseHeld() {
  for (let head = state.exportHold[0]; head !== undefined; head = state.exportHold[0]) {
    if (!Array.isArray(head) && head.calls.size > 0) {
      return
    }
    state.exportHold.shift()
    emit({ type: 'export', records: Array.isArray(head) ? head : [head.row, ...head.results] })
  }
}

/**
 * A main-loop row that may answer an async ask, as the transcript keeps it,
 * with the texts it is judged by (sminos._delivery_texts, _maws_steer_texts):
 * a prompt row whole, the ask mod's answer (submitted while the session was
 * idle) or the human's MAWS steer; the attachment of an answer the ask mod
 * gave as context (`hook_additional_context`, door `hook-context`), or of a
 * steer the engine took into a running turn (`queued_command`, door
 * `delivery`), its payload read back from its rendering, which is all the
 * hook is handed of it. None for any other row, and none for an attachment
 * whose rendering does not give its payload back exactly (not in the
 * engine's framing, or holding an escape), said in the debug log: the Stop
 * hook reads that row's payload itself.
 */
function answerRecord(door: string, message: { name?: string; content?: unknown }, uuid: string, origin: unknown): { texts: { text: string }[]; record: TranscriptRecord } | undefined {
  const texts = textBlocks(message.content)
  if (door === 'prompt') {
    return texts.some((b) => mayAnswer(b.text)) ? { texts, record: { type: 'user', uuid, origin: transcriptOrigin(origin), message: { content: texts } } } : undefined
  }
  const isContext = door === 'hook-context' && message.name === 'hook_additional_context'
  const isQueued = door === 'delivery' && message.name === 'queued_command'
  const rendered = isContext || isQueued ? texts.find((b) => mayAnswer(b.text))?.text : undefined
  if (rendered === undefined) {
    return undefined
  }
  // The entries, joined a line apart (each delivery is read up to the next),
  // or the queued prompt whole, so the child's start and end checks decide.
  const payload = isContext ? unframed(rendered, CONTEXT_OPEN, CONTEXT_CLOSE, CONTEXT_LABEL) : unframed(rendered, MID_TURN_OPEN, MID_TURN_CLOSE)
  if (payload === undefined || payload.includes(ESCAPED)) {
    state.log?.(`bridge: row ${uuid}: its rendering does not give its ${message.name} back exactly; the Stop hook exports it`)
    return undefined
  }
  const attachment = isContext
    ? { type: 'hook_additional_context', content: [payload] }
    : { type: 'queued_command', commandMode: 'prompt', prompt: payload, origin: transcriptOrigin(origin) }
  return { texts: [{ text: payload }], record: { type: 'attachment', uuid, attachment } }
}

/** The text between a rendering's exact framing (after `label`'s first occurrence, if given), or undefined when it is not framed so. */
function unframed(rendered: string, open: string, close: string, label?: string): string | undefined {
  if (!rendered.startsWith(open) || !rendered.endsWith(close) || rendered.length < open.length + close.length) {
    return undefined
  }
  const inner = rendered.slice(open.length, rendered.length - close.length)
  if (label === undefined) {
    return inner
  }
  const at = inner.indexOf(label)
  return at === -1 ? undefined : inner.slice(at + label.length)
}

/**
 * The row a delivery became (DC8.G6): a main-loop prompt row this plugin
 * submitted as the human's words (origin `plugin`, this plugin, `asUser`)
 * whose prompt — its first text block, the text as submitted; context blocks
 * follow it — is exactly the text of one delivery still awaiting its row,
 * named `delivered` `entered` with the row's uuid. A delivery's text opens
 * with its frame, which names its key, so two waiting with one text do not
 * happen; if they ever do, neither is named. A text a hook rewrote on its way
 * in matches none, and is not named: no row is guessed.
 */
export function enteredRow(door: string, message: { content?: unknown }, uuid: string, origin: unknown) {
  if (door !== 'prompt' || state.submissions.length === 0 || !isRecord(origin) || origin.kind !== 'plugin' || origin.name !== PLUGIN || origin.asUser !== true) {
    return
  }
  const first = Array.isArray(message.content) ? message.content.filter(isRecord).find((b) => b.type === 'text') : undefined
  const text = typeof message.content === 'string' ? message.content : first?.text
  const matching = state.submissions.filter((s) => s.text === text)
  if (matching.length !== 1) {
    return
  }
  const [submission] = matching
  state.submissions = state.submissions.filter((s) => s !== submission)
  emit({ type: 'delivered', key: submission!.key, outcome: 'entered', uuid })
}

/**
 * One row of a paired call (an async ask, a message tool's); once its call and
 * its result are both kept, the pair is exported, unless the call is a message
 * past TEXT_CAP: that pair is the Stop hook's, said in the debug log, and
 * holds nothing after it (the one exception to the order, the design's). A
 * message call's result goes to the row that holds it (exportRow), which
 * goes once all of its calls have theirs.
 */
function keepPair(id: string, row: { use?: TranscriptRecord; result?: TranscriptRecord }) {
  const pair = { ...state.pairs.get(id), ...row }
  if (pair.use !== undefined && pair.result !== undefined) {
    state.pairs.delete(id)
    if (isLong(pair.use)) {
      state.log?.(`bridge: row ${pair.use.uuid}: a message past ${TEXT_CAP} characters; the Stop hook exports it`)
      return
    }
    const held = heldFor(id)
    if (held !== undefined) {
      settleCall(held, id, pair.result)
    } else {
      exportInOrder([pair.use, pair.result])
    }
    return
  }
  state.pairs.set(id, pair)
  if (state.pairs.size > PAIRS_KEPT) {
    // A call whose other row never came: what waits behind it goes on (the Stop hook exports the call).
    const oldest = state.pairs.keys().next().value as string
    state.pairs.delete(oldest)
    const held = heldFor(oldest)
    if (held !== undefined) {
      settleCall(held, oldest)
    }
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
