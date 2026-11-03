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
 * took out is in no request. The live conversation names receipts, not
 * rows, so an id with a row seen after the cutoff (the inbox wrote it
 * again, a retry's wake) is not vouched for by an older row of it a rewind
 * may have taken out: it waits for a later request, unless the turn's own
 * text names it. The conversation's identity is read with it, and a report
 * names that session, whatever the bridge has moved to yet (a /clear). The markers are read wherever they stand in a
 * row's text, so the envelope's framing around the delivery's body (or a
 * rendering that wraps it) never hides one; an id names an unguessable
 * receipt the child checks, so a quoted one settles nothing it should not.
 */

/** The marker a delivery's text carries (sminos_holder_deliveries.MARKER, a wake's WAKE_MARKER), read anywhere in a row's text. */
const MARKER_RE = /\[sminos receipt ([0-9a-f]{24}\.[0-9a-f]{16}) attempt ([1-9][0-9]{0,8})( wake)?\]/g
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

/** The states the child's answer names that end an id in a report (sminos_holder_deliveries.admit, .release); any other, or none, is replayed. */
const ADMIT_ENDS = new Set(['admitted', 'gone', 'unknown', 'foreign'])
const RELEASE_ENDS = new Set(['released', 'admitted', 'gone', 'unknown', 'foreign', 'stale'])

/** The markers in a text, in order. */
export function marksIn(text: string | undefined): ReceiptMark[] {
  return [...(text ?? '').matchAll(MARKER_RE)].map((m) => ({ id: m[1]!, attempt: Number(m[2]), ...(m[3] !== undefined && { isWake: true }) }))
}

/** A receipt as the live conversation holds it: its highest attempt, and whether a full body of it is there (a wake alone is none). */
export type LiveMark = { attempt: number; hasBody: boolean }

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

/** The receipts the live conversation holds, as the requests read it; undefined when it cannot be read. */
export async function liveMarks($: EngineInterface): Promise<Map<string, LiveMark> | undefined> {
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
  const out = new Map<string, LiveMark>()
  for (const m of conversation.flatMap((c) => (isRecord(c) && c.role === 'user' ? marksIn(textOf(c.content)) : []))) {
    const was = out.get(m.id)
    out.set(m.id, { attempt: Math.max(was?.attempt ?? 0, m.attempt), hasBody: (was?.hasBody ?? false) || m.isWake !== true })
  }
  return out
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
 * the child's first ready names them (`retained`: those whose body the
 * conversation holds, a wake alone being none). A row seen since is ordered
 * by its own `seq`, not as one of these. A scan that could not read the
 * conversation is tried again by the next request that may carry a receipt.
 */
export function scanConversation($: EngineInterface): Promise<void> {
  const r = state.holder.receipts
  r.scan ??= (async () => {
    const live = await liveMarks($)
    if (live === undefined) {
      r.scan = undefined
      return
    }
    const seen = new Set([...r.rows.values()].flatMap((row) => row.marks.map((m) => m.id)))
    r.retained = [...live].filter(([, m]) => m.hasBody).map(([id]) => id).slice(0, REPORT_MAX)
    for (const [id, m] of live) {
      if (!seen.has(id)) {
        r.preload.set(id, m.attempt)
      }
    }
    r.isScanned = true
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
  r.isScanned = false
}

/** A receipt as one session's: the key of `done`. */
const receiptKey = (session: string, id: string) => `${session} ${id}`
const isDone = (session: string, id: string) => state.holder.receipts.done.has(receiptKey(session, id))
const isPending = (session: string, id: string) => state.holder.receipts.reports.some((p) => p.kind === 'admit' && p.session === session && p.ids.includes(id))

/**
 * What a main-loop request at `index` of its turn would carry that is still
 * to be reported in `session`, before the live conversation is checked: none
 * for the first request of a turn this module did not see begin. An id with
 * a row seen at or after the cutoff is left for a later request (the live
 * conversation cannot say which of its rows it holds), unless the turn's own
 * text names it.
 */
function due(step: FencedStep, index: number, session: string): Map<string, number> {
  const h = state.holder
  const r = h.receipts
  const turn = h.turns.get(step.turnId)
  const cutoff = index === 0 ? turn?.seq : step.entered
  if (cutoff === undefined) {
    return new Map()
  }
  const own = marksIn(turn?.text)
  const marks: ReceiptMark[] = [...own]
  const late = new Set<string>()
  for (const [uuid, row] of r.rows) {
    if (row.marks.every((m) => isDone(session, m.id))) {
      r.rows.delete(uuid)
    } else if (row.seq < cutoff) {
      marks.push(...row.marks)
    } else {
      for (const m of row.marks) {
        late.add(m.id)
      }
    }
  }
  for (const [id, attempt] of r.preload) {
    marks.push({ id, attempt })
  }
  const out = byId(marks)
  for (const id of out.keys()) {
    if (isDone(session, id) || isPending(session, id) || (late.has(id) && !own.some((m) => m.id === id))) {
      out.delete(id)
    }
  }
  return out
}

/**
 * The receipts a request carries, as the conversation it was built from
 * names them, and that conversation's session: `marks` with their body in
 * it, admitted with the request; `bodiless`, a wake whose body a rewind took
 * out, admitted never, released `present` false (a full retry, the same id).
 */
export type Carried = { session: string; marks: ReceiptMark[]; bodiless: ReceiptMark[] }

/**
 * The receipts the request carries and has not reported: those due that the
 * live conversation still holds, with the session that conversation is
 * (read with it: a /clear's new one before the bridge has moved to it).
 * Reads the conversation only when one may be due; one that cannot be read
 * carries none now (a later request rechecks).
 */
export async function receiptsCarried($: EngineInterface, step: FencedStep, index: number): Promise<Carried | undefined> {
  // A first scan that failed: tried again, so what the conversation held
  // before this module (a reload's) is due.
  if (!state.holder.receipts.isScanned) {
    await scanConversation($)
  }
  // Asked first of the bridge's session, so a request carrying nothing reads
  // nothing; the rows a /clear's new conversation took in are not that
  // session's done ones (session.end forgot the old conversation's rows).
  if (state.session === undefined || due(step, index, state.session).size === 0) {
    return undefined
  }
  const [session, live] = await Promise.all([
    $.session.id().catch((error: unknown) => {
      log(`the session id was not read: ${error instanceof Error ? error.message : String(error)}`)
      return undefined
    }),
    liveMarks($),
  ])
  if (session === undefined || live === undefined) {
    return undefined
  }
  const marks: ReceiptMark[] = []
  const bodiless: ReceiptMark[] = []
  for (const [id, attempt] of due(step, index, session)) {
    const held = live.get(id)
    if (held !== undefined) {
      ;(held.hasBody ? marks : bodiless).push({ id, attempt: Math.max(attempt, held.attempt) })
    }
  }
  return marks.length === 0 && bodiless.length === 0 ? undefined : { session, marks, bodiless }
}

/** The receipts of `session` no admission is owed for any more: admitted, gone, never this session's, or of a process that takes none. */
function settledIds(session: string, ids: Iterable<string>) {
  const done = state.holder.receipts.done
  for (const id of ids) {
    done.delete(receiptKey(session, id))
    done.add(receiptKey(session, id))
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
export function admitCarried({ session, marks, bodiless }: Carried): boolean {
  // A wake whose body is gone: the model read no message, so nothing is
  // admitted; it is released for a full retry once no fence holds.
  for (const [id, attempt] of byId(bodiless)) {
    keepStopped({ session, id, attempt })
  }
  const ids = [...new Set(marks.map((m) => m.id))].filter((id) => !isPending(session, id))
  if (ids.length === 0) {
    return bodiless.length > 0
  }
  for (let i = 0; i < ids.length; i += REPORT_MAX) {
    queue({ kind: 'admit', session, ids: ids.slice(i, i + REPORT_MAX) })
  }
  const r = state.holder.receipts
  r.stopped = r.stopped.filter((s) => s.session !== session || !ids.includes(s.id))
  return true
}

/** A request the gate's `stop` ended, carrying these receipts: nothing is reported; each waits for its release in this launch. */
export function stopCarried({ session, marks, bodiless }: Carried): boolean {
  if (marks.length === 0 && bodiless.length === 0) {
    return false
  }
  for (const [id, attempt] of byId([...marks, ...bodiless])) {
    keepStopped({ session, id, attempt })
  }
  return true
}

function keepStopped(s: StoppedReceipt) {
  const r = state.holder.receipts
  const at = r.stopped.findIndex((t) => t.session === s.session && t.id === s.id)
  if (at === -1) {
    r.stopped.push(s)
  } else {
    r.stopped[at] = { ...s, attempt: Math.max(s.attempt, r.stopped[at]!.attempt) }
  }
  if (r.stopped.length > STOPPED_KEPT) {
    log(`more than ${STOPPED_KEPT} stopped receipts: the oldest wait for a new launch`)
    r.stopped.splice(0, r.stopped.length - STOPPED_KEPT)
  }
}

/**
 * A fence holds again: every release still waiting for the child goes back
 * among the stopped receipts, released again (its row's presence read
 * afresh) once no fence holds. Admission reports stay queued. True when one
 * went back.
 */
export function holdReleases(): boolean {
  const r = state.holder.receipts
  const held = r.reports.filter((p) => p.kind === 'release')
  if (held.length === 0) {
    return false
  }
  r.reports = r.reports.filter((p) => p.kind !== 'release')
  for (const p of held) {
    for (const i of p.items) {
      keepStopped({ session: p.session, id: i.id, attempt: i.attempt })
    }
  }
  return true
}

/**
 * Every stopped receipt released for its retry in this launch, its body's
 * presence in the live conversation said (a wake for one there, the full
 * body for one a rewind or a /clear took out, or whose only row is a wake):
 * one report per session.
 */
export function releaseStoppedNow(live: Map<string, LiveMark> | undefined) {
  const r = state.holder.receipts
  const stopped = r.stopped
  r.stopped = []
  const sessions = new Map<string, StoppedReceipt[]>()
  for (const s of stopped) {
    sessions.set(s.session, [...(sessions.get(s.session) ?? []), s])
  }
  for (const [session, items] of sessions) {
    for (let i = 0; i < items.length; i += REPORT_MAX) {
      queue({ kind: 'release', session, items: items.slice(i, i + REPORT_MAX).map((s) => ({ id: s.id, attempt: s.attempt, present: live?.get(s.id)?.hasBody ?? false })) })
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
 * answer, a storage failure, the activation not settled yet (`pending`), a
 * mode it cannot read now), the report left at the head, or rotated to the
 * back holding only what was not recorded. Only an admission's answer
 * settles its ids for good; a release's acknowledgement leaves them to be
 * admitted (its retry's row).
 */
export function reportAnswered(report: ReceiptReport, got: { status: number; answer?: Record<string, unknown> } | undefined): 'done' | 'retry' {
  if (got === undefined) {
    return 'retry'
  }
  const ids = report.kind === 'admit' ? report.ids : report.items.map((i) => i.id)
  const settled = (which: string[]) => report.kind === 'admit' && settledIds(report.session, which)
  if (got.status === 400) {
    log(`the child refused a ${report.kind} report as malformed: ${JSON.stringify(got.answer).slice(0, 200)}`)
    settled(ids)
    return 'done'
  }
  if (got.status !== 200 || !isRecord(got.answer)) {
    return 'retry'
  }
  const a = got.answer
  if (a.ok === true) {
    settled(ids)
    return 'done'
  }
  if (a.code === 'legacy' || a.code === 'launch') {
    log(`${report.kind} of ${ids.length} receipt(s) is moot: ${String(a.error)}`)
    settled(ids)
    return 'done'
  }
  if (a.code === 'storage' && isRecord(a.receipts)) {
    // Only an explicit outcome ends an id: one the answer names no state for
    // (or `unavailable`) is replayed.
    const states = a.receipts
    const left = (id: string) => !(report.kind === 'admit' ? ADMIT_ENDS : RELEASE_ENDS).has(String(states[id]))
    settled(ids.filter((id) => !left(id)))
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
