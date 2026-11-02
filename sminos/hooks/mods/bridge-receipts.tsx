import type { EngineInterface } from 'claude-code'

import type { ReceiptReport, StoppedReceipt } from '../../types/sminos'

import { isRecord, state } from './bridge-state'
import type { FencedStep, ReceiptMark } from './bridge-state'

/**
 * The receipts a lane B observer's process was handed (O12 M4b): which of
 * them a model request carried, as the mod saw the rows go in. A `gate`
 * process's deliveries each carry a receipt's marker as a line of their text,
 * `[sminos receipt <id> attempt <n>]` (skills/sminos/scripts/
 * sminos_holder_deliveries.py prepares it before the inbox write); the
 * delivery is settled only once the mod reports that a request it admitted
 * carried the row, and the child records that durably
 * (bridge-holder.tsx sends what this module decides).
 *
 * A request carries a row when the row was in the live conversation before
 * the request was made. The mod sees every main-loop row as it is appended,
 * before it is stored, and orders it among the main turns' starts and
 * requests (`seq`): a turn's first request carries what was in when the turn
 * began, and its prompt, which the turn's own text names (the prompt's row
 * may be appended after the start); a later request carries what was in
 * when that request entered. A row appended after either is not that
 * request's, whatever else went in with it. The markers the conversation
 * held before this module saw any row (a reload, a resume) are older than
 * every turn it saw begin, and than every later request of a turn it did
 * not; a turn it did not see begin has no first request it can join to.
 * Every one is then checked against the live conversation
 * (`$.session.messages({ as: 'api' })`): a row a rewind or a compaction
 * took out is in no request. The markers are read wherever they stand in a
 * row's text, so the envelope's framing around the delivery's body (or a
 * rendering that wraps it) never hides one; an id names an unguessable
 * receipt the child checks, so a quoted one settles nothing it should not.
 */

/** The marker a delivery's text carries (sminos_holder_deliveries.MARKER), read anywhere in a row's text. */
const MARKER_RE = /\[sminos receipt ([0-9a-f]{24}\.[0-9a-f]{16}) attempt ([1-9][0-9]{0,8})\]/g
/** The doors by which a delivery's text enters the main conversation: a prompt, a delivery into a running turn, a queued one's attachment. */
const DOORS = new Set(['prompt', 'delivery', 'attachment'])
/** Rows carrying markers, ids settled, reports and stopped receipts kept, at most. */
const ROWS_KEPT = 256
const DONE_KEPT = 4096
export const REPORTS_KEPT = 64
const STOPPED_KEPT = 256
/** Receipt ids one report names at most (the child's REPORT_MAX). */
const REPORT_MAX = 512

const log = (text: string) => state.log?.(`bridge: receipts: ${text}`)

/** The markers in a text, in order. */
export function marksIn(text: string | undefined): ReceiptMark[] {
  return [...(text ?? '').matchAll(MARKER_RE)].map((m) => ({ id: m[1]!, attempt: Number(m[2]) }))
}

/** A row's or a message's text: its text blocks, or its string content. */
function textOf(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  return Array.isArray(content) ? content.flatMap((b) => (isRecord(b) && b.type === 'text' && typeof b.text === 'string' ? [b.text] : [])).join('\n') : ''
}

/** Each id once, its highest attempt. */
function byId(marks: Iterable<ReceiptMark>): Map<string, number> {
  const out = new Map<string, number>()
  for (const m of marks) {
    out.set(m.id, Math.max(out.get(m.id) ?? 0, m.attempt))
  }
  return out
}

/** The receipts the live conversation holds, as the requests read it, each id's highest attempt; undefined when it cannot be read. */
export async function liveMarks($: EngineInterface): Promise<Map<string, number> | undefined> {
  let conversation: unknown
  try {
    conversation = await $.session.messages({ as: 'api' })
  } catch (error) {
    log(`the conversation was not read: ${error instanceof Error ? error.message : String(error)}`)
    return undefined
  }
  if (!Array.isArray(conversation)) {
    return undefined
  }
  return byId(conversation.flatMap((m) => (isRecord(m) && m.role === 'user' ? marksIn(textOf(m.content)) : [])))
}

/**
 * A main-loop row on its way in, seen before it is stored: one carrying
 * markers is ordered now, so a read of the conversation that finds it is
 * never taken for an older row. Undone when the row is refused.
 */
export function receiptRow(door: string, content: unknown, uuid: string): (() => void) | undefined {
  if (!DOORS.has(door)) {
    return undefined
  }
  const marks = marksIn(textOf(content))
  if (marks.length === 0) {
    return undefined
  }
  const r = state.holder.receipts
  r.rows.set(uuid, { marks, seq: ++state.holder.seq })
  if (r.rows.size > ROWS_KEPT) {
    r.rows.delete(r.rows.keys().next().value!)
  }
  return () => void r.rows.delete(uuid)
}

/**
 * The markers this module's conversation held when it was first read, before
 * any row it saw (a reload, a resume): read once per conversation, before
 * the child's first ready names them (`retained`). A row seen since is
 * ordered by its own `seq`, not as one of these.
 */
export function scanConversation($: EngineInterface): Promise<void> {
  const r = state.holder.receipts
  r.scan ??= (async () => {
    const live = await liveMarks($)
    if (live === undefined) {
      return
    }
    const seen = new Set([...r.rows.values()].flatMap((row) => row.marks.map((m) => m.id)))
    r.retained = [...live.keys()].slice(0, REPORT_MAX)
    for (const [id, attempt] of live) {
      if (!seen.has(id)) {
        r.preload.set(id, attempt)
      }
    }
  })()
  return r.scan
}

/** A /clear: the new conversation's rows are its own, read afresh at its child's ready. Reports and stopped receipts name their sessions and stay. */
export function forgetReceiptRows() {
  const r = state.holder.receipts
  r.rows.clear()
  r.preload.clear()
  r.retained = []
  r.scan = undefined
}

const isPending = (id: string) => state.holder.receipts.reports.some((p) => p.kind === 'admit' && p.ids.includes(id))

/**
 * What a main-loop request at `index` of its turn would carry that is still
 * to be reported, before the live conversation is checked: none for the
 * first request of a turn this module did not see begin.
 */
function due(step: FencedStep, index: number): Map<string, number> {
  const h = state.holder
  const r = h.receipts
  const turn = h.turns.get(step.turnId)
  const cutoff = index === 0 ? turn?.seq : step.entered
  if (cutoff === undefined) {
    return new Map()
  }
  const marks: ReceiptMark[] = [...marksIn(turn?.text)]
  for (const [uuid, row] of r.rows) {
    if (row.marks.every((m) => r.done.has(m.id))) {
      r.rows.delete(uuid)
    } else if (row.seq < cutoff) {
      marks.push(...row.marks)
    }
  }
  for (const [id, attempt] of r.preload) {
    marks.push({ id, attempt })
  }
  const out = byId(marks)
  for (const id of out.keys()) {
    if (r.done.has(id) || isPending(id)) {
      out.delete(id)
    }
  }
  return out
}

/**
 * The receipts the request carries and has not reported: those due that the
 * live conversation still holds. Reads the conversation only when one is
 * due; one that cannot be read carries none now (a later request rechecks).
 */
export async function receiptsCarried($: EngineInterface, step: FencedStep, index: number): Promise<ReceiptMark[]> {
  if (state.session === undefined) {
    return []
  }
  const want = due(step, index)
  if (want.size === 0) {
    return []
  }
  const live = await liveMarks($)
  return live === undefined ? [] : [...want].filter(([id]) => live.has(id)).map(([id, attempt]) => ({ id, attempt: Math.max(attempt, live.get(id)!) }))
}

/** The ids no report is owed for any more. */
export function settledIds(ids: Iterable<string>) {
  const done = state.holder.receipts.done
  for (const id of ids) {
    done.delete(id)
    done.add(id)
    state.holder.receipts.preload.delete(id)
  }
  while (done.size > DONE_KEPT) {
    done.delete(done.values().next().value!)
  }
}

function queue(report: ReceiptReport) {
  const r = state.holder.receipts
  r.reports.push(report)
  if (r.reports.length > REPORTS_KEPT) {
    const dropped = r.reports.shift()!
    log(`more than ${REPORTS_KEPT} reports wait for the child: the oldest (${dropped.kind}, ${dropped.session}) is dropped; its receipts stay owed`)
  }
}

/**
 * The mod's final admission of a request carrying these receipts (a
 * `proceed`, no fence, a lease's expiry): one admission report, queued with
 * no await, so nothing comes between this and the request's `next`. Its
 * stopped receipts are stopped no more. True when a report was queued.
 */
export function admitCarried(marks: readonly ReceiptMark[]): boolean {
  const session = state.session
  const ids = [...new Set(marks.map((m) => m.id))].filter((id) => !isPending(id))
  if (session === undefined || ids.length === 0) {
    return false
  }
  for (let i = 0; i < ids.length; i += REPORT_MAX) {
    queue({ kind: 'admit', session, ids: ids.slice(i, i + REPORT_MAX) })
  }
  const r = state.holder.receipts
  r.stopped = r.stopped.filter((s) => !ids.includes(s.id))
  return true
}

/** A request the gate's `stop` ended, carrying these receipts: nothing is reported; each waits for its release in this launch. */
export function stopCarried(marks: readonly ReceiptMark[]): boolean {
  const session = state.session
  if (session === undefined || marks.length === 0) {
    return false
  }
  const r = state.holder.receipts
  for (const [id, attempt] of byId(marks)) {
    const at = r.stopped.findIndex((s) => s.id === id)
    if (at === -1) {
      r.stopped.push({ session, id, attempt })
    } else {
      r.stopped[at] = { session, id, attempt: Math.max(attempt, r.stopped[at]!.attempt) }
    }
  }
  if (r.stopped.length > STOPPED_KEPT) {
    log(`more than ${STOPPED_KEPT} stopped receipts: the oldest wait for a new launch`)
    r.stopped.splice(0, r.stopped.length - STOPPED_KEPT)
  }
  return true
}

/**
 * Every stopped receipt released for its retry in this launch, its row's
 * presence in the live conversation said (a wake for one there, the full
 * body for one a rewind or a /clear took out): one report per session.
 */
export function releaseStoppedNow(live: Map<string, number> | undefined) {
  const r = state.holder.receipts
  const stopped = r.stopped
  r.stopped = []
  const sessions = new Map<string, StoppedReceipt[]>()
  for (const s of stopped) {
    sessions.set(s.session, [...(sessions.get(s.session) ?? []), s])
  }
  for (const [session, items] of sessions) {
    for (let i = 0; i < items.length; i += REPORT_MAX) {
      queue({ kind: 'release', session, items: items.slice(i, i + REPORT_MAX).map((s) => ({ id: s.id, attempt: s.attempt, present: live?.has(s.id) ?? false })) })
    }
  }
}

/** The receipt a main turn's own text names: `turn.delivery` (OX10), the first when it names several. */
export function turnDelivery(turnId: string | undefined): string | undefined {
  return turnId === undefined ? undefined : marksIn(state.holder.turns.get(turnId)?.text)[0]?.id
}

/**
 * The child's answer to a report: `done` (recorded, or nothing more can be:
 * the process takes no receipts, the report was malformed), `retry` (no
 * answer, a storage failure, a mode it cannot read now), the report left
 * at the head, or rotated to the back holding only what was not recorded.
 */
export function reportAnswered(report: ReceiptReport, got: { status: number; answer?: Record<string, unknown> } | undefined): 'done' | 'retry' {
  if (got === undefined) {
    return 'retry'
  }
  const ids = report.kind === 'admit' ? report.ids : report.items.map((i) => i.id)
  if (got.status === 400) {
    log(`the child refused a ${report.kind} report as malformed: ${JSON.stringify(got.answer).slice(0, 200)}`)
    settledIds(ids)
    return 'done'
  }
  if (got.status !== 200 || !isRecord(got.answer)) {
    return 'retry'
  }
  const a = got.answer
  if (a.ok === true) {
    settledIds(ids)
    return 'done'
  }
  if (a.code === 'legacy' || a.code === 'launch') {
    log(`${report.kind} of ${ids.length} receipt(s) is moot: ${String(a.error)}`)
    settledIds(ids)
    return 'done'
  }
  if (a.code === 'storage' && isRecord(a.receipts)) {
    const states = a.receipts
    const left = (id: string) => states[id] === 'unavailable'
    settledIds(ids.filter((id) => !left(id)))
    const r = state.holder.receipts
    r.reports.shift()
    const rest: ReceiptReport | undefined =
      report.kind === 'admit' ? (report.ids.some(left) ? { ...report, ids: report.ids.filter(left) } : undefined) : report.items.some((i) => left(i.id)) ? { ...report, items: report.items.filter((i) => left(i.id)) } : undefined
    if (rest !== undefined) {
      r.reports.push(rest)
    }
    log(`${report.kind}: not recorded yet (${String(a.error)}): replayed`)
    return 'retry'
  }
  log(`${report.kind}: ${String(a.code)}: ${String(a.error)}: replayed`)
  return 'retry'
}
