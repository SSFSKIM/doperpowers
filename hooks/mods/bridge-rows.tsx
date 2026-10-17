import type { SessionMessage } from 'claude-code'

import { ASK_TOOL, PLUGIN } from './ask'
import { TEXT_CAP, isRecord, loopKey, state } from './bridge-state'
import type { BridgeEvent, TranscriptRecord } from './bridge-state'
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
 * text row with a mark and an async ask with its result, go to the child as
 * they are kept (`export`), and the child appends them to the project's log
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
/** Async asks whose other row (the call, or its result) has not been kept yet. */
const ASKS_KEPT = 50
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
