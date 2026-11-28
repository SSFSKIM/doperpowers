import { describe, expect, test, tier } from 'claude-code/testing'

import { RING, RING_DROP } from '../../hooks/mods/sheet-model'
import type { Recipient } from '../../hooks/mods/sheet-model'
import { sheetNudge } from '../../hooks/mods/sheet'
import { HOME, MODEL, S1, S2, gated, ok, sheetOn } from './sheet-harness'
import type { StepEvent, StepScript } from './sheet-harness'

tier('user')

/**
 * Delivery in a terminal session (plan
 * docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I9 and M4):
 * the routes, landing, a start's search and context, a compaction's context,
 * subagents; and in a MAWS-run session (MAWS's question-sheet C5: F8, F33,
 * F34), the same routes, MAWS's ring and a stopped turn. The record is a fake
 * of the step's that keeps what is pending and packs a recipient's envelope
 * from it, the wakers first, as the composer does (I7), and under runner
 * `maws` the main conversation's with its answers first; the composer's own
 * packing is the step's tests'.
 */

const PLUGIN_ROW = { kind: 'plugin', name: 'sminos' }
const RESULT_ROW = { kind: 'plugin', event: 'tool.call' }
const PROMPT_ROW = { kind: 'plugin', event: 'prompt.submit' }
/** A session MAWS launched with the sheet: the form and its id (MAWS's C5, F32). */
const MAWS = { MAWS_QUESTION_SHEET: `2:${S1}` }
/** The sentence alone, without the ring's mark: a person's words, which the tool never drops. */
const PLAIN = 'The human answered questions on your sheet.'

type Out = { key: string; id: string; kind: 'answer' | 'dismiss'; recipient: Recipient; acrossStop: boolean; acceptedAt: string }

/** When the step accepted an outcome: before any Stop a test makes (the mod stamps a Stop with the real clock), or after it. */
const BEFORE = '2020-01-01T00:00:00.000Z'
const AFTER = '2099-01-01T00:00:00.000Z'

/** An answer (or dismissal) pending for `recipient`, accepted before any Stop unless the test says otherwise. */
const out = (key: string, id: string, over: Partial<Out> = {}): Out => ({ key, id, kind: 'answer', recipient: 'main', acrossStop: false, acceptedAt: BEFORE, ...over })

const wakes = (o: Out) => o.kind === 'answer' && !o.acrossStop

/** An envelope in I7's form for `outs`: a head, a line an answer, the block last. */
function envelopeOf(outs: readonly Out[], recipient: Recipient, more = false): string {
  const answered = outs.filter((o) => o.kind === 'answer')
  const dismissed = outs.filter((o) => o.kind === 'dismiss')
  const block = { v: 1, keys: [...answered, ...dismissed].map((o) => o.key), answered: answered.map((o) => ({ id: o.id, revision: 1, picks: [], text: 'yes', images: [] })), dismissed: dismissed.map((o) => o.id), ...(more && { more: true }) }
  return [
    ...(recipient === 'main' ? [] : ['From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet.']),
    answered.length > 0 ? `[sheet v1] The human answered questions on your sheet.${more ? ' More follows.' : ''}` : '[sheet v1] The human dismissed questions on your sheet; no answer will come for them.',
    ...answered.map((o) => `${o.id} "Which?" → their text: "yes"`),
    ...(dismissed.length > 0 ? [`Dismissed: ${dismissed.map((o) => o.id).join(', ')}.`] : []),
    `<sheet-delivery>${JSON.stringify(block)}</sheet-delivery>`,
  ].join('\n')
}

/** The view's `mainAcceptedAt`, absent when no answer is pending for the main conversation. */
function mainAcceptedAt(pending: readonly Out[]): { mainAcceptedAt?: string } {
  const times = pending.filter((o) => o.kind === 'answer' && o.recipient === 'main').map((o) => o.acceptedAt)
  return times.length === 0 ? {} : { mainAcceptedAt: times.reduce((a, b) => (b > a ? b : a)) }
}

const same = (a: Recipient, b: Recipient) => (a === 'main' ? b === 'main' : b !== 'main' && a.agentId === b.agentId)

/**
 * A record as the step keeps it, for the mod's side: every step drains what
 * the test queued, applies `landed`, `reroute`, a start and the `agents`
 * rule, and answers a view whose `ready` packs each recipient's envelope, at
 * most `per` outcomes, the wakers first.
 */
function record(initial: readonly Out[] = [], options: { per?: number; context?: (event: StepEvent) => string | undefined; open?: unknown[]; listed?: number } = {}) {
  const pending: Out[] = initial.map((o) => ({ ...o }))
  const queued: Out[] = []
  let seq = 0
  const per = options.per ?? 200
  const envelope = (recipient: Recipient, runner = 'terminal') => {
    const mine = pending.filter((o) => same(o.recipient, recipient))
    if (mine.length === 0) return undefined
    const first = runner === 'maws' && recipient === 'main' ? (o: Out) => o.kind === 'answer' : wakes
    const packed = [...mine.filter(first), ...mine.filter((o) => !first(o))].slice(0, per)
    const more = packed.length < mine.length
    return { recipient, keys: packed.map((o) => o.key), text: envelopeOf(packed, recipient, more), wakes: packed.some(wakes), more }
  }
  const script: StepScript = (event) => {
    seq += 1
    const before = pending.map((o) => o.key)
    pending.push(...queued.splice(0))
    const keys = (event.keys as string[] | undefined) ?? []
    if (event.event === 'landed') {
      for (let i = pending.length - 1; i >= 0; i--) if (keys.includes(pending[i]!.key)) pending.splice(i, 1)
    }
    if (event.event === 'reroute') pending.filter((o) => keys.includes(o.key)).forEach((o) => (o.recipient = 'main'))
    if (event.event === 'start') pending.forEach((o) => ((o.recipient = 'main'), (o.acrossStop = true)))
    const running = (event.agents as { running?: string[] } | undefined)?.running
    if (running !== undefined) pending.filter((o) => o.recipient !== 'main' && !running.includes(o.recipient.agentId)).forEach((o) => (o.recipient = 'main'))
    const recipients: Recipient[] = ['main']
    pending.forEach((o) => o.recipient !== 'main' && !recipients.some((r) => same(r, o.recipient)) && recipients.push(o.recipient))
    const ready = recipients.map((r) => envelope(r, String(event.runner))).filter((e) => e !== undefined)
    const context = options.context?.(event) ?? (event.event === 'start' || event.context === 'compact' ? `[sheet v1] context ${seq}: ${pending.map((o) => o.key).join(' ')}` : undefined)
    return ok(
      seq,
      {
        ...(event.event === 'start' && { start: { empty: null, before: before.slice(0, 200), beforeCount: before.length, imported: [] } }),
        ...(event.event === 'call' && { result: 'Added q1.' }),
        ...(context !== undefined && { context }),
      },
      {
        nextId: 2,
        ready,
        open: (options.open ?? []) as never,
        pending: pending.slice(0, options.listed).map((o) => ({ key: o.key, id: o.id, kind: o.kind, recipient: o.recipient, taken: o.recipient !== 'main', acrossStop: o.acrossStop })),
        pendingCount: pending.length,
        // The latest `acceptedAt` among every pending answer for the main conversation, past the listed ones too.
        ...mainAcceptedAt(pending),
      },
    )
  }
  return { pending, queued, script, envelope }
}

/** A session under the sheet, started, whose record is `rec`. */
async function started(rec: ReturnType<typeof record>, over: Parameters<typeof sheetOn>[0] = {}) {
  const h = sheetOn({ step: rec.script, ...over })
  await h.ready()
  await h.hop()
  return h
}

/** An answer reaches the record and the bridge's nudge drains it. */
async function answered(h: Awaited<ReturnType<typeof started>>, rec: ReturnType<typeof record>, ...outs: Out[]) {
  rec.queued.push(...outs)
  await sheetNudge(outs.map((o) => o.key))
  await h.settle()
}

const steps = (h: { steps: StepEvent[] }, event: string) => h.steps.filter((s) => s.event === event)
const contextOf = (r: { result: { context?: string[] } }) => r.result.context ?? []

describe('the routes (I9)', () => {
  test('a view adopted while no main turn runs opens the idle route for an envelope that wakes, from the hop, never inside the dispatch that adopted it', async () => {
    const rec = record()
    const h = await started(rec)
    // A subagent's tool call: its check finds the inbox grown and drains, adopting the view inside its dispatch.
    rec.queued.push(out('k1', 'q1'))
    h.files.set(`${HOME}/sheet/${S1}/inbox.jsonl`, '{}\n')
    const subagents = await h.call('Read', { file_path: '/work/a' }, 'a1')
    await h.settle()
    expect(steps(h, 'drain')).toHaveLength(1)
    expect(contextOf(subagents)).toEqual([])
    expect(h.submits).toEqual([])
    await h.hop()
    expect(h.submits).toEqual([rec.envelope('main')?.text ?? envelopeOf([out('k1', 'q1')], 'main')])
  })

  test('a main turn that completes with the answer opens the idle route; one the human stopped does not, and the next prompt carries it', async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    expect(h.submits).toEqual([])
    await h.turnComplete('t1', 'aborted')
    await h.hop()
    expect(h.submits).toEqual([])
    const entered = (await h.prompt('go on')) as { context?: string[] }
    expect(entered.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])

    const rec2 = record()
    const h2 = await started(rec2)
    await h2.turnStart('t1')
    await answered(h2, rec2, out('k1', 'q1'))
    await h2.turnComplete('t1', 'answer')
    await h2.settle()
    await h2.hop()
    expect(h2.submits).toHaveLength(1)
  })

  test("a call of the model's main loop carries the envelope on its result; a subagent's, an aborted, a denied and another plugin's call do not", async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    expect(contextOf(await h.call('Read', {}, 'a1'))).toEqual([])
    const aborted = new AbortController()
    aborted.abort()
    expect(contextOf(await h.call('Read', {}, undefined, MODEL, undefined, aborted.signal))).toEqual([])
    expect(contextOf(await h.call('Read', {}, undefined, MODEL, undefined, undefined, { deny: 'no' }))).toEqual([])
    expect(contextOf(await h.call('Read', {}, undefined, { plugin: 'other', tier: 'user' }))).toEqual([])
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    // Taken: the next result carries nothing.
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test("the tool's own call is a result route too", async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    const asked = await h.ask({ ask: [{ question: 'More?' }] })
    expect(asked.result).toMatchObject({ result: 'Added q1.', context: [envelopeOf([out('k1', 'q1')], 'main')] })
  })

  test('a prompt that enters carries the envelope and a notice waiting, each an entry of its own; a slash command does not', async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    await h.turnComplete('t1', 'aborted')
    await h.hop()
    const command = (await h.prompt('/review', { command: { name: 'review', args: '' } })) as { context?: string[] }
    expect(command.context).toBeUndefined()
    const entered = (await h.prompt('go on', { context: ['theirs'] })) as { context?: string[] }
    expect(entered.context).toEqual(['theirs', envelopeOf([out('k1', 'q1')], 'main')])
  })

  test('an envelope that does not wake opens no idle route, and leaves with the next route that opens', async () => {
    const rec = record()
    const h = await started(rec)
    await answered(h, rec, out('k1', 'q1', { kind: 'dismiss' }))
    await h.hop()
    await h.tick()
    expect(h.submits).toEqual([])
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1', { kind: 'dismiss' })], 'main')])
  })

  test("what is owed across a stop and a fresh answer, before any prompt, leave together on the fresh answer's idle turn", async () => {
    const rec = record([out('old', 'q1')])
    const h = sheetOn({ step: rec.script })
    await h.ready('resume')
    await h.hop()
    expect(h.submits).toEqual([])
    await answered(h, rec, out('fresh', 'q2'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["fresh","old"]')
  })
})

describe('a flight that fails (I9)', () => {
  test("a submit dropped, or one that rejects, makes the envelope ready again with today's toast; it is not retried by itself, but a fresh answer wakes the session and takes it along", async () => {
    for (const refusal of [() => ({ drop: 'a hook said no' }), () => Promise.reject(new Error('host refused'))]) {
      const rec = record()
      const h = await started(rec, { submit: refusal })
      await answered(h, rec, out('k1', 'q1'))
      await h.hop()
      expect(h.submits).toHaveLength(1)
      expect(h.calls.filter((c) => c.op === 'ui.toast').map((c) => c.args)).toEqual([expect.stringContaining('it goes with the next message')])
      // A dismissal wakes nothing: the failed answer is not retried for it.
      await answered(h, rec, out('d1', 'q3', { kind: 'dismiss' }))
      await h.hop()
      expect(h.submits).toHaveLength(1)
      // A fresh answer wakes the session, the failed one along.
      await answered(h, rec, out('k2', 'q2'))
      await h.hop()
      expect(h.submits).toHaveLength(2)
      expect(h.submits[1]).toContain('"keys":["k1","k2","d1"]')
      await h.hop()
      expect(h.submits).toHaveLength(2)
      await h.turnStart('t1')
      expect(contextOf(await h.call('Read', {}))).toEqual([rec.envelope('main')?.text])
    }
  })

  test('a fresh answer wakes the session though a full envelope of failed work hides it: failed work alone does not', async () => {
    const rec = record([], { per: 2 })
    const h = await started(rec, { submit: () => ({ drop: 'a hook said no' }) })
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    await answered(h, rec, out('d1', 'q4', { kind: 'dismiss' }))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    await answered(h, rec, out('k3', 'q3'))
    expect(rec.envelope('main')?.keys).toEqual(['k1', 'k2'])
    await h.hop()
    expect(h.submits).toHaveLength(2)
    await h.hop()
    expect(h.submits).toHaveLength(2)
  })

  test('a split envelope: once its first part lands and that turn completes, the next part goes by the idle route with no human input', async () => {
    const rec = record([], { per: 1 })
    const h = await started(rec, { submit: (text) => ({ text }) })
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2'))
    h.afters.push(() => void h.turnStart('ours'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["k1"]')
    await h.append({ door: 'prompt', origin: PLUGIN_ROW, text: `The sminos plugin sent a message:\n${h.submits[0]}` })
    await h.settle()
    await h.turnComplete('ours', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(2)
    expect(h.submits[1]).toContain('"keys":["k2"]')
  })

  test('the hidden fresh answer that opened a retry has spent its wake: an unchanged nudge or a turn that completes after the retry fails opens nothing; a newer answer opens one', async () => {
    const rec = record([], { per: 2 })
    const h = await started(rec, { submit: () => ({ drop: 'a hook said no' }) })
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2'))
    await h.hop()
    await answered(h, rec, out('k3', 'q3'))
    await h.hop()
    expect(h.submits).toHaveLength(2)
    // The same view again.
    await sheetNudge([])
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(2)
    await h.turnStart('t1')
    await h.turnComplete('t1', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(2)
    await answered(h, rec, out('k4', 'q4'))
    await h.hop()
    expect(h.submits).toHaveLength(3)
    await h.hop()
    expect(h.submits).toHaveLength(3)
  })

  test('an idle reservation let go before the hand-over spends no wake: the turn that took its place ends, and the idle route opens for it', async () => {
    const rec = record()
    const h = await started(rec)
    await answered(h, rec, out('k1', 'q1'))
    // A turn starts before the hop: the reservation is let go; that turn carries nothing, and its end reopens the route.
    await h.turnStart('t1')
    await h.hop()
    expect(h.submits).toEqual([])
    await h.turnComplete('t1', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(1)
  })

  test("at a turn's end only a route's framing counts: a human's prompt quoting the block lands nothing; a context holding part of the batch lands that part, the rest ready again", async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2'))
    expect(contextOf(await h.call('Read', {}))).toHaveLength(1)
    h.converse({ rows: [], api: [{ role: 'user', content: envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main') }] })
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    expect(steps(h, 'landed')).toEqual([])
    await h.turnStart('t2')
    expect(contextOf(await h.call('Read', {}))).toHaveLength(1)
    const part = `<system-reminder>\ntool.call hook additional context: ${envelopeOf([out('k1', 'q1')], 'main')}\n</system-reminder>`
    h.converse({ rows: [], api: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'x', content: [{ type: 'text', text: 'read' }, { type: 'text', text: part }] }] }] })
    await h.turnComplete('t2', 'aborted')
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
    await h.turnStart('t3')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k2', 'q2')], 'main')])
  })

  test('a prompt that keeps the envelope but drops a context waiting, or drops a context it carried alone, puts that context back for the next route', async () => {
    let fails = true
    const rec = record()
    const h = await started(rec, { step: (event, n) => (event.context === 'compact' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    await h.classicStart('compact')
    fails = false
    await h.tick()
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    const isContext = (c: string) => c.startsWith('[sheet v1] context')
    const kept = (await h.prompt('first', { turnId: 't1' }, async (e) => ({ text: e.text, context: (e.context as string[]).filter((c) => !isContext(c)) }))) as { context?: string[] }
    expect(kept.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    const alone = (await h.prompt('second', { turnId: 't1' }, async (e) => ({ text: e.text, context: [] }))) as { context?: string[] }
    expect(alone.context).toEqual([])
    expect(contextOf(await h.call('Read', {}))).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: $/)])
  })


  test('a notice the prompt that entered still carries is not put back with the envelope a hook took out', async () => {
    const rec = record([], { open: [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }] })
    const h = await started(rec, { agents: [{ id: 'a1', description: 'reviewer', type: 'general', status: 'running' }] })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    const entered = (await h.prompt('first', { turnId: 't1' }, async (e) => ({ text: e.text, context: (e.context as string[]).filter((c) => !c.includes('<sheet-delivery>')) }))) as { context?: string[] }
    expect(entered.context).toEqual([expect.stringContaining('ended with questions still open')])
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
  })

  test('a prompt that resolves without the envelope in its context, or is dropped beneath, makes it ready again', async () => {
    for (const bottom of [async (e: Record<string, unknown>) => ({ text: e.text, context: [] }), async () => ({ drop: 'blocked' })]) {
      const rec = record()
      const h = await started(rec)
      await h.turnStart('t1')
      await answered(h, rec, out('k1', 'q1'))
      await h.prompt('first', { turnId: 't1' }, bottom)
      expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    }
  })

  test("a result route's envelope a hook above dropped is ready again at that turn's end, in the same process; one the conversation holds is landed there", async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    expect(contextOf(await h.call('Read', {}))).toHaveLength(1)
    h.converse({ rows: [], api: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'x', content: 'read' }] }] })
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    expect(steps(h, 'landed')).toEqual([])
    const entered = (await h.prompt('again')) as { context?: string[] }
    expect(entered.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])

    await h.turnStart('t2')
    h.converse({ rows: [], api: [{ role: 'user', content: [{ type: 'text', text: `<system-reminder>\nprompt.submit hook additional context: ${envelopeOf([out('k1', 'q1')], 'main')}\n</system-reminder>` }] }] })
    await h.turnComplete('t2', 'answer')
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
  })

  test("an answer that comes while the idle submit waits: when that submit is dropped or rejects, the idle route opens again at once for the newer answer, the failed one along", async () => {
    for (const refusal of [{ drop: 'a hook said no' }, new Error('host refused')]) {
      let enter: (value: unknown) => void = () => {}
      let refuse: (error: Error) => void = () => {}
      const rec = record()
      const h = await started(rec, { submit: () => new Promise((resolve, reject) => ((enter = resolve), (refuse = reject))) })
      await answered(h, rec, out('kA', 'q1'))
      await h.hop()
      expect(h.submits).toHaveLength(1)
      await answered(h, rec, out('kB', 'q2'))
      await h.hop()
      expect(h.submits).toHaveLength(1)
      if (refusal instanceof Error) refuse(refusal)
      else enter(refusal)
      await h.settle()
      await h.hop()
      expect(h.submits).toHaveLength(2)
      expect(h.submits[1]).toContain('"keys":["kA","kB"]')
    }
  })

  test("the retry is judged by the wake that opened the failed submit: an answer the view hides that came while it waited still wakes the session", async () => {
    let enter: (value: unknown) => void = () => {}
    let answeredCount = 0
    // The view lists one pending outcome and packs one an envelope: the later answer shows only in the record's count.
    const rec = record([], { per: 1 })
    const script: StepScript = async (event, n) => {
      const answer = JSON.parse(await rec.script(event, n)) as { view: { answeredCount: number; pending: unknown[] } }
      answer.view.answeredCount = answeredCount
      answer.view.pending = answer.view.pending.slice(0, 1)
      return JSON.stringify(answer)
    }
    const h = await started(rec, { step: script, submit: () => new Promise((resolve) => (enter = resolve)) })
    answeredCount = 1
    await answered(h, rec, out('kA', 'q1'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    answeredCount = 2
    await answered(h, rec, out('kB', 'q2'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    enter({ drop: 'a hook said no' })
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(2)
    expect(h.submits[1]).toContain('"keys":["kA"]')
    // That one dropped too: nothing new since, nothing opens.
    enter({ drop: 'a hook said no' })
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(2)
  })
})

describe('which turn a flight belongs to (I9)', () => {
  test('a foreign prompt queued ahead of the idle submit: its turn ends before the submit enters and settles nothing; one envelope reaches the conversation, landed by its row', async () => {
    let enter: (value: unknown) => void = () => {}
    const rec = record()
    const h = await started(rec, { submit: (text) => new Promise((resolve) => (enter = () => resolve({ text }))) })
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    // The foreign prompt's turn runs and ends while the submit waits behind it: the conversation does not hold the envelope.
    h.converse({ rows: [], api: [] })
    await h.turnStart('foreign')
    await h.turnComplete('foreign', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toEqual([])
    // The submit's own prompt enters: its row lands it.
    await h.append({ door: 'prompt', origin: PLUGIN_ROW, text: `The sminos plugin sent a message:\n${h.submits[0]}\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns.` })
    await h.turnStart('ours')
    enter(undefined)
    await h.settle()
    await h.turnComplete('ours', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
  })

  test("an idle prompt that entered without its block landing: its own turn's end settles it, and it starts no turn again", async () => {
    const rec = record()
    const h = await started(rec, { submit: (text) => ({ text }) })
    await answered(h, rec, out('k1', 'q1'))
    // Its turn starts as the submit resolves (2.1.331: after the prompt's turn.start).
    h.afters.push(() => void h.turnStart('ours'))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    h.converse({ rows: [], api: [] })
    await h.turnComplete('ours', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toHaveLength(1)
    await h.turnStart('t2')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
  })

  test("a prompt typed over a running turn: that turn's end without it fails nothing; the next turn's end does", async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    const entered = (await h.prompt('also this', { turnId: 't1' })) as { context?: string[] }
    expect(entered.context).toHaveLength(1)
    h.converse({ rows: [], api: [] })
    await h.turnComplete('t1', 'answer')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toEqual([])
    await h.turnStart('t2')
    await h.turnComplete('t2', 'answer')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toHaveLength(1)
  })

  test("a prompt typed over a turn whose end is still reading the conversation when the next turn starts belongs to that next turn", async () => {
    let holding = false
    let read: () => void = () => {}
    const rec = record()
    const h = await started(rec, { apiRead: () => (holding ? new Promise<void>((resolve) => (read = resolve)) : Promise.resolve()) })
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    expect(((await h.prompt('also this', { turnId: 't1' })) as { context?: string[] }).context).toHaveLength(1)
    h.converse({ rows: [], api: [] })
    holding = true
    await h.turnComplete('t1', 'answer')
    await h.turnStart('t2')
    holding = false
    read()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toEqual([])
    await h.turnComplete('t2', 'answer')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'ui.toast')).toHaveLength(1)
  })

  test("a prompt typed over a turn that ends while the hooks beneath still hold the prompt: once that turn and the next have ended, its envelope is landed or ready again", async () => {
    for (const isHeld of [false, true]) {
      const rec = record()
      const h = await started(rec)
      await h.turnStart('A')
      await answered(h, rec, out('k1', 'q1'))
      let enter: () => void = () => {}
      const typed = h.prompt('also this', { turnId: 'A' }, (e) => new Promise((resolve) => (enter = () => resolve({ text: e.text, context: e.context, origin: e.origin }))))
      await h.settle()
      h.converse({ rows: [], api: [] })
      await h.turnComplete('A', 'answer')
      await h.settle()
      enter()
      const entered = (await typed) as { context?: string[] }
      expect(entered.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
      await h.turnStart('B')
      if (isHeld) h.converse({ rows: [], api: [{ role: 'user', content: `<system-reminder>\nprompt.submit hook additional context: ${entered.context?.[0]}\n</system-reminder>` }] })
      await h.turnComplete('B', 'answer')
      await h.settle()
      await h.hop()
      if (isHeld) {
        expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
        expect(h.submits).toEqual([])
      } else {
        // Ready again: the toast, and B's end opens the idle route for it.
        expect(h.calls.filter((c) => c.op === 'ui.toast')).toHaveLength(1)
        expect(h.submits).toHaveLength(1)
        expect(h.submits[0]).toContain('"keys":["k1"]')
      }
    }
  })

  test("a queued turn that starts and ends while the hooks beneath still hold a prompt typed over the turn before: nothing of its envelope is released or retried while the prompt can still enter; the turn the prompt opens settles it", async () => {
    for (const isHeld of [false, true]) {
      const rec = record()
      const h = await started(rec)
      const toasts = () => h.calls.filter((c) => c.op === 'ui.toast')
      await h.turnStart('A')
      await answered(h, rec, out('k1', 'q1'))
      let enter: () => void = () => {}
      const typed = h.prompt('also this', { turnId: 'A' }, (e) => new Promise((resolve) => (enter = () => resolve({ text: e.text, context: e.context, origin: e.origin }))))
      await h.settle()
      h.converse({ rows: [], api: [] })
      await h.turnComplete('A', 'answer')
      await h.settle()
      // A foreign prompt queued before it runs its turn while the prompt is still held.
      await h.turnStart('B')
      await h.turnComplete('B', 'answer')
      await h.settle()
      await h.hop()
      expect(toasts()).toEqual([])
      expect(h.submits).toEqual([])
      expect(contextOf(await h.call('Read', {}))).toEqual([])
      enter()
      const entered = (await typed) as { context?: string[] }
      expect(entered.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
      // The prompt that entered opens its own turn.
      await h.turnStart('C')
      if (isHeld) h.converse({ rows: [], api: [{ role: 'user', content: `<system-reminder>\nprompt.submit hook additional context: ${entered.context?.[0]}\n</system-reminder>` }] })
      await h.turnComplete('C', 'answer')
      await h.settle()
      await h.hop()
      if (isHeld) {
        expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
        expect(toasts()).toEqual([])
        expect(h.submits).toEqual([])
      } else {
        expect(toasts()).toHaveLength(1)
        expect(h.submits).toHaveLength(1)
        expect(h.submits[0]).toContain('"keys":["k1"]')
      }
    }
  })
})

describe('a reservation, checked again at the hop (I9)', () => {
  const A1 = { id: 'a1', description: 'reviewer', type: 'general', status: 'running' }

  test('a prompt that enters before the idle hop takes the envelope; the hop then submits nothing', async () => {
    const rec = record()
    const h = await started(rec)
    await answered(h, rec, out('k1', 'q1'))
    const entered = (await h.prompt('hello')) as { context?: string[] }
    expect(entered.context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    await h.hop()
    expect(h.submits).toEqual([])
  })

  test('a session change before the idle hop: the hop submits nothing for the session left', async () => {
    const rec = record()
    const h = await started(rec)
    await answered(h, rec, out('k1', 'q1'))
    await h.classicStart('clear', '5eed0000-0000-4000-8000-0000000000c2')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
  })

  test('a subagent that stops before the send hop is not sent to (a send would resume it); the stop hands its answer to the main conversation', async () => {
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1] })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await h.hop()
    expect(h.sends).toEqual([])
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["k1"]')
  })
})

describe('a call that runs across a session change (I9)', () => {
  test("a call of the session left, held across a fork in this process, returns as it was: it carries nothing of the copy's and reserves none of its envelopes", async () => {
    for (const tool of ['sheet', 'Read']) {
      let release: () => void = () => {}
      const held = new Promise<void>((resolve) => (release = resolve))
      const rec = record()
      const h = await started(rec, { step: async (event, n) => (event.event === 'call' && event.session === S1 ? (await held, rec.script(event, n)) : rec.script(event, n)) })
      await h.turnStart('t1')
      const calling = tool === 'sheet' ? h.ask({ ask: [{ question: 'Before the copy?' }] }) : h.call('Read', { file_path: '/work/a' }, undefined, MODEL, undefined, undefined, held.then(() => ({ result: 'read' })))
      await h.settle()
      rec.queued.push(out('k1', 'q1'))
      await h.classicStart('fork', S2)
      await h.settle()
      release()
      const { result } = await calling
      expect(result.context).toBeUndefined()
      // The copy's envelope is still ready, for its own next route.
      expect(contextOf(await h.call('Read', {}))).toEqual([rec.envelope('main')?.text])
    }
  })
})

describe('landing (I9)', () => {
  test("a row of the routes' kinds that holds a block lands its keys, the step not awaited by the hook; the rows redraw after", async () => {
    const rec = record([out('a', 'q1'), out('b', 'q2'), out('c', 'q3')])
    const h = await started(rec)
    const before = h.calls.length
    for (const [origin, door, key] of [[RESULT_ROW, 'hook-context', 'a'], [PROMPT_ROW, 'hook-context', 'b'], [PLUGIN_ROW, 'prompt', 'c']] as const) {
      await h.append({ door, origin, text: `<system-reminder>\nx hook additional context: ${envelopeOf([out(key, 'q')], 'main')}\n</system-reminder>` })
    }
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['a'], ['b'], ['c']])
    // Each landed step's view is drawn: once each.
    expect(h.calls.slice(before).filter((c) => c.op === 'ui.invalidate' && c.args === 'ui.render')).toHaveLength(3)
    expect(rec.pending).toEqual([])
  })

  test("a row a hook beneath rewrote without the block, a human's prompt quoting an envelope, another plugin's prompt, a subagent's row and a steer land nothing", async () => {
    const rec = record([out('a', 'q1')])
    const h = await started(rec)
    const text = envelopeOf([out('a', 'q1')], 'main')
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: '<system-reminder>\ntool.call hook additional context: [sheet v1] The human answered\n</system-reminder>' })
    await h.append({ door: 'prompt', origin: { kind: 'composer' }, text })
    await h.append({ door: 'prompt', origin: { kind: 'plugin', name: 'other' }, text })
    await h.append({ door: 'hook-context', origin: RESULT_ROW, agentId: 'a1', text })
    await h.append({ door: 'delivery', origin: { kind: 'composer' }, text })
    await h.append({ door: 'hook-context', origin: { kind: 'hook', event: 'UserPromptSubmit' }, text })
    await h.settle()
    expect(steps(h, 'landed')).toEqual([])
  })

  test('a row a module before a reload sent lands: nothing of its flight is known here', async () => {
    const rec = record([out('a', 'q1')])
    const h = await started(rec)
    await h.append({ door: 'prompt', origin: PLUGIN_ROW, text: `The sminos plugin sent a message:\n${envelopeOf([out('a', 'q1')], 'main')}` })
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['a']])
  })

  test('a landing whose step gives no answer keeps its keys from every route, and is ordered again at the next check', async () => {
    let fails = true
    const rec = record()
    const script: StepScript = (event, n) => (event.event === 'landed' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n))
    const h = await started(rec, { step: script })
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    expect(contextOf(await h.call('Read', {}))).toHaveLength(1)
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: envelopeOf([out('k1', 'q1')], 'main') })
    await h.settle()
    expect(steps(h, 'landed')).toHaveLength(1)
    await h.turnComplete('t1', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
    fails = false
    await h.tick()
    // Ordered again at every check until it answers; never anything but its own keys.
    expect(new Set(steps(h, 'landed').map((s) => JSON.stringify(s.keys)))).toEqual(new Set(['["k1"]']))
    expect(rec.pending).toEqual([])
    const ordered = steps(h, 'landed').length
    await h.tick()
    expect(steps(h, 'landed')).toHaveLength(ordered)
  })

  test("in a MAWS-run session one Send that answers the main conversation's question and a running subagent's: the subagent's goes by the send, the main conversation's by the next route, and its row lands it", async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS, agents: [{ id: 'a1', description: 'reviewer', type: 'general', status: 'running' }] })
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2', { recipient: { agentId: 'a1' } }))
    await h.hop()
    expect(h.submits).toEqual([])
    expect(h.sends.map((s) => s.agentId)).toEqual(['a1'])
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: envelopeOf([out('k1', 'q1')], 'main') })
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k2'], ['k1']])
    expect(rec.pending).toEqual([])
  })
})

describe('a start (I9, I10)', () => {
  /** A line of the search's evidence (the stored rows are read by the real search: test-sheet-step.sh). */
  const stored = (key: string, kind: 'tool.call' | 'prompt.submit' | 'plugin') => JSON.stringify({ keys: [key], kind })

  test("the search finds one of two pending outcomes: it lands, the start is ordered again, and its context is the SessionStart's; the other goes owed across a stop", async () => {
    const rec = record([out('k1', 'q1'), out('k2', 'q2')])
    const searched: string[][] = []
    // The start's search (the ask's own read of today's asks searches too: M5's import).
    const h = sheetOn({ step: rec.script, exec: (argv) => (argv[1] === '-MJSON::PP' && searched.push([...argv]), { exitCode: 0, stdout: `${stored('k1', 'tool.call')}\n` }) })
    await h.start()
    const answered = (await h.classicStart('resume')) as { additionalContext?: string[] }
    expect(searched).toHaveLength(1)
    expect(searched[0]?.slice(0, 3)).toEqual(['perl', '-MJSON::PP', '-e'])
    // `before` lists every key pending: the search prints those keys alone.
    expect(searched[0]?.slice(4)).toEqual(['--', `/t/${S1}.jsonl`, 'k1', 'k2'])
    expect(h.steps.map((s) => s.event)).toEqual(['start', 'landed', 'start'])
    expect(h.steps[2]?.start).toEqual(h.steps[0]?.start)
    expect(steps(h, 'landed')[0]?.keys).toEqual(['k1'])
    expect(answered.additionalContext).toEqual(['[sheet v1] context 3: k2'])
    // What it did not find goes, owed across a stop, with the first route.
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k2', 'q2', { acrossStop: true })], 'main')])
  })

  test("each of the stored kinds lands, every key found (not only the first 200 `before` lists); nothing the session started with lands before the search's", async () => {
    const many = Array.from({ length: 250 }, (_, i) => out(`k${i}`, `q${i + 1}`))
    const rec = record(many)
    const h = sheetOn({ step: rec.script, exec: () => ({ exitCode: 0, stdout: [stored('k0', 'tool.call'), stored('k1', 'prompt.submit'), stored('k2', 'plugin'), stored('k249', 'tool.call')].join('\n') }) })
    await h.start()
    await h.classicStart('resume')
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k0', 'k1', 'k2', 'k249']])
  })

  test('a search output cut at its bound counts its whole lines: the newest rows, printed first', async () => {
    const rec = record([out('k1', 'q1'), out('k2', 'q2')])
    const h = sheetOn({ step: rec.script, exec: () => ({ exitCode: 0, stdout: `${stored('k2', 'plugin')}\n{"keys":["k1"],"ki`, isStdoutTruncated: true }) })
    await h.start()
    await h.classicStart('resume')
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k2']])
  })

  test("a reload before the start answered: its retry searches the transcript it was given, lands what it found, and its context goes by the next route", async () => {
    let fails = true
    const rec = record([out('k1', 'q1'), out('k2', 'q2')])
    const first = sheetOn({ step: (event, n) => (fails ? Promise.reject(new Error('the command did not start')) : rec.script(event, n)) })
    await first.start()
    await first.classicStart('resume')
    fails = false
    const searched: string[][] = []
    const reloaded = sheetOn({ kept: first.kept, step: rec.script, exec: (argv) => (argv[1] === '-MJSON::PP' && searched.push([...argv]), { exitCode: 0, stdout: `${stored('k1', 'tool.call')}\n` }) })
    await reloaded.start()
    await reloaded.settle()
    expect(searched.map((argv) => argv.slice(4))).toEqual([['--', `/t/${S1}.jsonl`, 'k1', 'k2']])
    expect(steps(reloaded, 'landed').map((s) => s.keys)).toEqual([['k1']])
    await reloaded.turnStart('t1')
    expect(contextOf(await reloaded.call('Read', {}))).toEqual([envelopeOf([out('k2', 'q2', { acrossStop: true })], 'main'), expect.stringMatching(/^\[sheet v1\] context \d+: k2$/)])
  })

  test("a search that fails lands nothing, and the start's own context is the SessionStart's", async () => {
    for (const exec of [() => ({ exitCode: 2, stdout: '' }), () => Promise.reject(new Error('no perl'))]) {
      const rec = record([out('k1', 'q1')])
      const h = sheetOn({ step: rec.script, exec })
      await h.start()
      const answered = (await h.classicStart('resume')) as { additionalContext?: string[] }
      expect(h.steps.map((s) => s.event)).toEqual(['start'])
      expect(answered.additionalContext).toEqual(['[sheet v1] context 1: k1'])
    }
  })

  test("a MAWS-run session's start searches the transcript as a terminal's does: an envelope that landed before the process died is not delivered again (the carriers round's B6)", async () => {
    const rec = record([out('k1', 'q1'), out('k2', 'q2')])
    const searched: string[][] = []
    const h = sheetOn({ step: rec.script, env: MAWS, exec: (argv) => (argv[1] === '-MJSON::PP' && searched.push([...argv]), { exitCode: 0, stdout: `${stored('k1', 'prompt.submit')}\n` }) })
    await h.start()
    const answered = (await h.classicStart('resume')) as { additionalContext?: string[] }
    expect(searched.map((argv) => argv.slice(4))).toEqual([['--', `/t/${S1}.jsonl`, 'k1', 'k2']])
    expect(h.steps.map((s) => s.event)).toEqual(['start', 'landed', 'start'])
    expect(steps(h, 'landed')[0]?.keys).toEqual(['k1'])
    expect(answered.additionalContext).toEqual(['[sheet v1] context 3: k2'])
    expect(((await h.prompt(RING)) as { context?: string[] }).context).toEqual([envelopeOf([out('k2', 'q2', { acrossStop: true })], 'main')])
  })

  test('a start with nothing pending before it searches nothing; a start with nothing to say adds no context', async () => {
    const rec = record([], { context: () => '' })
    const h = sheetOn({ step: rec.script, exec: () => Promise.reject(new Error('searched')) })
    await h.start()
    const answered = (await h.classicStart('resume')) as { additionalContext?: string[] }
    expect(h.runs().filter((r) => r.startsWith('-MJSON::PP'))).toEqual([])
    expect(answered.additionalContext).toBeUndefined()
  })

  test("a launch's SessionStart that came before the choice: the start's context goes on the next result or prompt route, once", async () => {
    let release: () => void = () => {}
    const rec = record([out('k1', 'q1')])
    const h = sheetOn({ step: rec.script, exec: () => ({ exitCode: 1, stdout: '' }) })
    // The choice's probe waits, so the SessionStart comes first.
    const choosing = new Promise<void>((resolve) => (release = resolve))
    const original = h.engine.process.run
    ;(h.engine.process as { run: unknown }).run = async (argv: readonly string[], init?: unknown) => {
      if (argv[2] === 'probe') await choosing
      return (original as (a: readonly string[], i?: unknown) => unknown)(argv, init)
    }
    const session = h.start()
    const early = (await h.classicStart('startup')) as { additionalContext?: string[] }
    expect(early.additionalContext).toBeUndefined()
    release()
    await session
    await h.settle()
    await h.turnStart('t1')
    const first = contextOf(await h.call('Read', {}))
    expect(first).toEqual([envelopeOf([out('k1', 'q1', { acrossStop: true })], 'main'), '[sheet v1] context 1: k1'])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })
})

describe('a compaction (E12)', () => {
  test("its SessionStart orders its own drain, even while another drain runs, and returns the drain's context", async () => {
    let hold: () => void = () => {}
    const rec = record([out('k1', 'q1', { kind: 'dismiss' })])
    const h = await started(rec, {
      step: (event, n) => (event.event === 'drain' && event.context === undefined ? new Promise((resolve) => (hold = () => resolve(rec.script(event, n) as string))) : rec.script(event, n)),
    })
    void sheetNudge([])
    await h.settle()
    const compacted = (await h.classicStart('compact')) as { additionalContext?: string[] }
    expect(steps(h, 'drain').map((s) => s.context)).toEqual([undefined, 'compact'])
    expect(compacted.additionalContext).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: k1$/)])
    hold()
    await h.settle()
  })

  test("with no answer, the next check's drain composes the context, and the next result route carries it once", async () => {
    let fails = true
    const rec = record()
    const h = await started(rec, { step: (event, n) => (event.context === 'compact' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    const compacted = (await h.classicStart('compact')) as { additionalContext?: string[] }
    expect(compacted.additionalContext).toBeUndefined()
    fails = false
    await h.tick()
    expect(steps(h, 'drain').map((s) => s.context)).toEqual(['compact', 'compact'])
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: $/)])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test('in a MAWS-run session the context with no answer at the SessionStart rides the next route beside the envelope, once, as in a terminal session', async () => {
    let fails = true
    const rec = record()
    const h = await started(rec, { env: MAWS, step: (event, n) => (event.context === 'compact' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    await h.classicStart('compact')
    fails = false
    await h.tick()
    await answered(h, rec, out('k1', 'q1'))
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main'), expect.stringMatching(/^\[sheet v1\] context \d+: $/)])
    expect(((await h.prompt('steer', { turnId: 't1' })) as { context?: string[] }).context).toBeUndefined()
    expect(contextOf(await h.call('Read', {}))).toEqual([])

    // The same context, with no call before the prompt: the prompt carries it.
    let fails2 = true
    const rec2 = record()
    const h2 = await started(rec2, { env: MAWS, step: (event, n) => (event.context === 'compact' && fails2 ? Promise.reject(new Error('busy')) : rec2.script(event, n)) })
    await h2.classicStart('compact')
    fails2 = false
    await h2.tick()
    expect(((await h2.prompt('steer')) as { context?: string[] }).context).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: $/)])
    await h2.turnStart('t1')
    expect(contextOf(await h2.call('Read', {}))).toEqual([])
  })
})

describe('subagents (§6, I9)', () => {
  const A1 = { id: 'a1', description: 'reviewer', type: 'general', status: 'running' }

  test("a running subagent's envelope is sent from the hop, and lands as it is delivered; the main conversation's is not", async () => {
    const rec = record()
    const h = await started(rec, { agents: [A1] })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    expect(h.sends).toEqual([])
    await h.hop()
    expect(h.sends).toEqual([{ agentId: 'a1', text: envelopeOf([out('k1', 'q1', { recipient: { agentId: 'a1' } })], { agentId: 'a1' }) }])
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
    expect(h.submits).toEqual([])
  })

  test('a send not delivered, and one that rejects, each order reroute and land nothing; the answer then goes to the main conversation', async () => {
    for (const send of [() => ({ isDelivered: false, reason: 'gone' }), () => Promise.reject(new Error('no such agent'))]) {
      const rec = record()
      const h = await started(rec, { agents: [A1], send })
      await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
      await h.hop()
      expect(steps(h, 'reroute').map((s) => s.keys)).toEqual([['k1']])
      expect(steps(h, 'landed')).toEqual([])
      await h.hop()
      expect(h.submits).toHaveLength(1)
    }
  })

  test('an agent gone from the list before the step is never sent to; one that stopped is never sent to either', async () => {
    // The view holds the subagent's question, so every step carries the agents running.
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [] })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h.hop()
    expect(h.sends).toEqual([])
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: [], direct: true })
    expect(h.submits).toHaveLength(1)

    const rec2 = record([], { open })
    const h2 = await started(rec2, { agents: [A1] })
    await h2.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await answered(h2, rec2, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h2.hop()
    expect(h2.sends).toEqual([])
    // It starts again (another's send resumed it): it is sent to again.
    await h2.turnStart('r1', 'a1')
    await answered(h2, rec2, out('k2', 'q2', { recipient: { agentId: 'a1' } }))
    await h2.hop()
    expect(h2.sends.map((s) => s.agentId)).toEqual(['a1'])
  })

  test('a subagent that stops with questions open is named on the next result route, once', async () => {
    const open = [
      { id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' },
      { id: 'q5', revision: 1, asker: 'main', question: 'Mine?', askedAt: '2026-11-24T10:00:00.000Z' },
      { id: 'q6', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'And the tests?', askedAt: '2026-11-24T10:00:00.000Z' },
    ]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1] })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([
      '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?", q6 "And the tests?". Their answers will come to you; withdraw what you no longer need.',
    ])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test('the notice is ready at the stop itself: a prompt that enters before the stop\'s drain answers carries it', async () => {
    // A background agent's completion reaches the main conversation as a prompt a few milliseconds after its
    // SubagentStop, well before a step answers (2.1.331, the live check).
    const open = [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    let hold: (() => void) | undefined
    const h = await started(rec, {
      agents: [A1],
      step: (event, n) => (event.event === 'drain' ? new Promise((resolve) => (hold = () => resolve(rec.script(event, n) as string))) : rec.script(event, n)),
    })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    const entered = (await h.prompt('<task-notification>done</task-notification>')) as { context?: string[] }
    expect(entered.context).toEqual([
      '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?". Their answers will come to you; withdraw what you no longer need.',
    ])
    await h.settle()
    expect(hold).toBeDefined()
    hold?.()
    await h.settle()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test('a stop while a send to it is awaited: every step until its receipt passes the agent as running, so the stop takes nothing back; after, it is not', async () => {
    let receipt: (value: unknown) => void = () => {}
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1], send: () => new Promise((resolve) => (receipt = resolve)) })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h.hop()
    expect(h.sends).toHaveLength(1)
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: ['a1'], direct: true })
    expect(rec.pending.map((o) => o.recipient)).toEqual([{ agentId: 'a1' }])
    receipt({ isDelivered: true })
    await h.settle()
    expect(steps(h, 'landed').at(-1)).toMatchObject({ keys: ['k1'], agents: { running: ['a1'], direct: true } })
    await sheetNudge([])
    await h.settle()
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: [], direct: true })
  })

  test('a notice waiting when the idle route opens goes in its prompt, above the envelope, and on no route after', async () => {
    const open = [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1] })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    const notice = '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?". Their answers will come to you; withdraw what you no longer need.'
    expect(h.submits).toEqual([`${notice}\n\n${envelopeOf([out('k1', 'q1')], 'main')}`])
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test('a second stop names only the questions not named before', async () => {
    const open: unknown[] = [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1] })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    open.push({ id: 'q6', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'And the tests?', askedAt: '2026-11-24T10:00:00.000Z' })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([
      '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?". Their answers will come to you; withdraw what you no longer need.',
      '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q6 "And the tests?". Their answers will come to you; withdraw what you no longer need.',
    ])
  })

  test("a send's receipt with no answer keeps the agent owning its key: a drain meanwhile passes it as running, until the retry lands it", async () => {
    let fails = true
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1], step: (event, n) => (event.event === 'landed' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h.hop()
    await h.settle()
    expect(h.sends).toHaveLength(1)
    expect(steps(h, 'landed')).toHaveLength(1)
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: ['a1'], direct: true })
    expect(rec.pending.map((o) => o.recipient)).toEqual([{ agentId: 'a1' }])
    fails = false
    await h.tick()
    expect(rec.pending).toEqual([])
    await sheetNudge([])
    await h.settle()
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: [], direct: true })
  })

  test('an answer accepted for a stopped agent while it still owns a sent key goes to the main conversation once its receipt lands', async () => {
    let receipt: (value: unknown) => void = () => {}
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open })
    const h = await started(rec, { agents: [A1], send: () => new Promise((resolve) => (receipt = resolve)) })
    await answered(h, rec, out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    await h.hop()
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    await answered(h, rec, out('k2', 'q2', { recipient: { agentId: 'a1' } }))
    expect(rec.pending.map((o) => [o.key, o.recipient])).toEqual([['k1', { agentId: 'a1' }], ['k2', { agentId: 'a1' }]])
    receipt({ isDelivered: true })
    await h.settle()
    expect(rec.pending.map((o) => [o.key, o.recipient])).toEqual([['k2', 'main']])
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["k2"]')
    expect(h.sends).toHaveLength(1)
  })

  test("a reload: its first drain, with no view held yet, passes the subagents running, so a running subagent's answer stays its own", async () => {
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const first = await started(record([], { open }), { agents: [A1] })
    const rec = record([], { open })
    rec.queued.push(out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    const reloaded = sheetOn({ kept: first.kept, agents: [A1], step: rec.script })
    await reloaded.start()
    await reloaded.settle()
    expect(steps(reloaded, 'drain')[0]?.agents).toEqual({ running: ['a1'], direct: true })
    await reloaded.hop()
    expect(reloaded.sends.map((s) => s.agentId)).toEqual(['a1'])
  })

  test("a subagent's call settled after that agent stopped: each settle names the agents running then, so the stopped one is not", async () => {
    let hold: ((error: Error) => void) | undefined
    const rec = record()
    const h = await started(rec, {
      agents: [A1],
      step: (event, n) => {
        if (event.event === 'call') return Promise.reject(new Error('timed out'))
        if (event.event === 'settle' && hold === undefined) return new Promise<string>((_, reject) => (hold = reject))
        return rec.script(event, n)
      },
    })
    const asking = h.ask({ ask: [{ question: 'Ship it?' }] }, 'a1')
    await h.settle()
    expect(steps(h, 'settle').map((s) => s.agents)).toEqual([{ running: ['a1'], direct: true }])
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    hold?.(new Error('timed out'))
    await asking
    expect(steps(h, 'settle').map((s) => s.agents)).toEqual([{ running: ['a1'], direct: true }, { running: [], direct: true }])
  })
  test("a settle that listed an agent running before its stop's drain committed gives a fresh answer to that agent: the view adopted orders one drain with the agents as they are now, and the answer goes to the main conversation, once", async () => {
    let commit: () => void = () => {}
    const rec = record()
    let settles = 0
    const h = await started(rec, {
      agents: [A1],
      step: async (event, n) => {
        // The call commits and its answer is lost; the first settle samples the agents, then waits for the lock.
        if (event.event === 'call') return 'Traceback: the answer was lost'
        if (event.event === 'settle' && ++settles === 1) await new Promise<void>((resolve) => (commit = resolve))
        return rec.script(event, n)
      },
    })
    const asking = h.ask({ ask: [{ question: 'Ship it?' }] }, 'a1')
    await h.settle()
    expect(steps(h, 'settle').map((s) => s.agents)).toEqual([{ running: ['a1'], direct: true }])
    // The agent stops; its drain commits before the settle takes the lock.
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    // A put: the settle, holding a1 as running, gives the answer to it.
    rec.queued.push(out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    commit()
    await asking
    await h.settle()
    await h.hop()
    expect(steps(h, 'drain').at(-1)?.agents).toEqual({ running: [], direct: true })
    expect(h.sends).toEqual([])
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["k1"]')
    await h.tick()
    expect(h.submits).toHaveLength(1)
  })

  test("a view that still gives the answer to the stopped agent after its corrective drain orders no other; nor does one from a step that already left that agent out", async () => {
    let commit: () => void = () => {}
    let settles = 0
    let isStuck = false
    const open = [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const stuck = [{ key: 'k1', id: 'q1', kind: 'answer', recipient: { agentId: 'a1' }, taken: true, acrossStop: false }]
    // A step that ignores `agents`: once the answer is given to a1, every view gives it there. Its seq is the record's
    // order of commits, so the settle that waited for the lock answers the newer view.
    let seq = 0
    const viewOf = () => ok(++seq, {}, { open: open as never, ...(isStuck && { pending: stuck as never, pendingCount: 1 }) })
    const h = await started(record(), {
      agents: [A1],
      step: async (event) => {
        if (event.event === 'call') return 'Traceback: the answer was lost'
        if (event.event === 'settle' && ++settles === 1) {
          await new Promise<void>((resolve) => (commit = resolve))
          isStuck = true
        }
        return viewOf()
      },
    })
    const asking = h.ask({ ask: [{ question: 'Ship it?' }] }, 'a1')
    await h.settle()
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    const before = steps(h, 'drain').length
    commit()
    await asking
    await h.settle()
    // The settle listed a1: one corrective drain, with a1 left out.
    expect(steps(h, 'drain').slice(before).map((s) => s.agents)).toEqual([{ running: [], direct: true }])
    await sheetNudge([])
    await h.tick()
    await h.tick()
    // The nudge's drain, and nothing more: its view, from a step that left a1 out, orders none either.
    expect(steps(h, 'drain')).toHaveLength(before + 2)
  })

  test("a corrective drain whose agent lookup failed stays owed: the next check orders it again with the agents read, and the answer goes to the main conversation, once", async () => {
    let commit: () => void = () => {}
    const rec = record()
    let settles = 0
    const h = await started(rec, {
      agents: [A1],
      step: async (event, n) => {
        if (event.event === 'call') return 'Traceback: the answer was lost'
        if (event.event === 'settle' && ++settles === 1) await new Promise<void>((resolve) => (commit = resolve))
        return rec.script(event, n)
      },
    })
    const asking = h.ask({ ask: [{ question: 'Ship it?' }] }, 'a1')
    await h.settle()
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    rec.queued.push(out('k1', 'q1', { recipient: { agentId: 'a1' } }))
    // The next lookup of the agents fails.
    const engine = h.engine as unknown as { agent: { list: () => Promise<unknown> } }
    const list = engine.agent.list
    engine.agent.list = () => ((engine.agent.list = list), Promise.reject(new Error('the agents could not be listed')))
    const before = steps(h, 'drain').length
    commit()
    await asking
    await h.settle()
    await h.hop()
    // The corrective drain went without agents: nothing moved, and nothing is ordered straight after it.
    expect(steps(h, 'drain').slice(before).map((s) => s.agents)).toEqual([undefined])
    expect(h.submits).toEqual([])
    await h.tick()
    expect(steps(h, 'drain').slice(before).map((s) => s.agents)).toEqual([undefined, { running: [], direct: true }])
    expect(h.submits).toHaveLength(1)
    expect(h.submits[0]).toContain('"keys":["k1"]')
    await h.tick()
    await h.tick()
    expect(h.submits).toHaveLength(1)
  })
})

describe("a MAWS-run session's routes (MAWS's C5, F8): a terminal's, but the idle route", () => {
  const A1 = { id: 'a1', description: 'reviewer', type: 'general', status: 'running' }
  const OPEN = [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
  const NOTICE = '[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?". Their answers will come to you; withdraw what you no longer need.'

  /** A MAWS-run session whose subagent a1 stopped with q4 open: its notice waits. */
  async function ended(over: Parameters<typeof sheetOn>[0] = {}) {
    const rec = record([], { open: OPEN })
    const h = await started(rec, { env: MAWS, agents: [A1], ...over })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    return h
  }

  test("an ended subagent's open questions are named on the next result route, once", async () => {
    const h = await ended()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([NOTICE])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
    expect(((await h.prompt('next')) as { context?: string[] }).context).toBeUndefined()
    expect(h.submits).toEqual([])
  })

  test('the result route keeps its other conditions: a subagent\'s, an aborted, a denied and another plugin\'s call carry nothing, and the notice waits', async () => {
    const h = await ended()
    await h.turnStart('t1')
    const aborted = new AbortController()
    aborted.abort()
    expect(contextOf(await h.call('Read', {}, 'a2'))).toEqual([])
    expect(contextOf(await h.call('Read', {}, undefined, MODEL, undefined, aborted.signal))).toEqual([])
    expect(contextOf(await h.call('Read', {}, undefined, MODEL, undefined, undefined, { deny: 'no' }))).toEqual([])
    expect(contextOf(await h.call('Read', {}, undefined, { plugin: 'other', tier: 'user' }))).toEqual([])
    expect(contextOf(await h.call('Read', {}))).toEqual([NOTICE])
  })

  test('on a prompt, once; put back when the prompt was dropped beneath or entered without it, and then on the next route', async () => {
    const h = await ended()
    expect(((await h.prompt('first')) as { context?: string[] }).context).toEqual([NOTICE])
    expect(((await h.prompt('second')) as { context?: string[] }).context).toBeUndefined()

    const dropped = await ended()
    await dropped.prompt('dropped', {}, async () => ({ drop: 'a hook beneath' }))
    await dropped.prompt('stripped', {}, async (e) => ({ text: e.text, context: [] }))
    expect(((await dropped.prompt('third')) as { context?: string[] }).context).toEqual([NOTICE])
    await dropped.turnStart('t1')
    expect(contextOf(await dropped.call('Read', {}))).toEqual([])
  })

  test("a call's late outcome, once three settles went unanswered, is told on the main conversation's next route", async () => {
    let isDown = true
    const rec = record()
    const h = await started(rec, {
      env: MAWS,
      step: (event, n) => (event.event === 'call' || (event.event === 'settle' && isDown) ? Promise.reject(new Error('timed out')) : event.event === 'settle' ? ok(n, { result: 'Added q1, q2.' }) : rec.script(event, n)),
    })
    const { id } = await h.ask({ ask: [{ question: 'A?' }, { question: 'B?' }] })
    isDown = false
    await h.tick()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([`[sheet v1] Your earlier call (${id}) did change the sheet: Added q1, q2.`])
    expect(contextOf(await h.call('Read', {}))).toEqual([])
  })

  test("no idle submit is ever made there, whatever the view holds: a fresh answer while no turn runs, a turn's end with the answer, a stopped one", async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS, messages: { rows: [], api: [] } })
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    await h.tick()
    await h.turnStart('t1')
    await answered(h, rec, out('k2', 'q2'))
    await h.turnComplete('t1', 'answer')
    await h.settle()
    await h.hop()
    await h.turnStart('t2')
    await h.turnComplete('t2', 'aborted')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    expect(h.calls.filter((c) => c.op === 'prompt.submit')).toEqual([])
    // What is ready waits for a route that opens.
    expect(((await h.prompt('next')) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main')])
  })
})

describe("MAWS's ring in a MAWS-run session (MAWS's C5, F33)", () => {
  const ring = (h: { prompt: (text: string, over?: Record<string, unknown>) => Promise<unknown> }, over: Record<string, unknown> = {}) => h.prompt(RING, over) as Promise<{ text?: string; context?: string[]; drop?: string }>
  const DROPPED = { drop: RING_DROP }
  const rings = (h: { logs: () => string[] }) => h.logs().filter((line) => line.startsWith('sheet: a ring '))

  test('a ring with an answer ready enters with the envelope as its context; the stored hook-context row lands its keys; a second ring is dropped', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    expect(h.submits).toEqual([])
    const envelope = envelopeOf([out('k1', 'q1')], 'main')
    expect(await ring(h)).toEqual({ text: RING, context: [envelope], origin: { kind: 'composer' } })
    await h.append({ door: 'hook-context', origin: PROMPT_ROW, text: envelope })
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
    expect(rec.pending).toEqual([])
    expect(await ring(h)).toEqual(DROPPED)
    expect(rings(h)).toEqual(["sheet: a ring is filled: the main conversation's envelope, 1 key", 'sheet: a ring is dropped: no envelope is ready for the main conversation'])
  })

  test('a ring when only a dismissal is ready is dropped, and the dismissal rides the next prompt that enters, or the next tool result', async () => {
    const dismissal = out('d1', 'q1', { kind: 'dismiss' })
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, dismissal)
    expect(await ring(h)).toEqual(DROPPED)
    expect(rings(h)).toEqual(["sheet: a ring is dropped: the main conversation's envelope holds no answer"])
    expect(rec.pending.map((o) => o.key)).toEqual(['d1'])
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([envelopeOf([dismissal], 'main')])

    const rec2 = record()
    const h2 = await started(rec2, { env: MAWS })
    await answered(h2, rec2, dismissal)
    expect(await ring(h2)).toEqual(DROPPED)
    await h2.turnStart('t1')
    expect(contextOf(await h2.call('Read', {}))).toEqual([envelopeOf([dismissal], 'main')])
  })

  test('A5: a ring written for an answer that a tool result then landed, with a dismissal adopted before the hook ran, is dropped', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    // MAWS, told k1 is owed, rings once the turn ends; meanwhile the turn's tool result carries it and its row lands it.
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: envelopeOf([out('k1', 'q1')], 'main') })
    await h.settle()
    await answered(h, rec, out('d2', 'q2', { kind: 'dismiss' }))
    await h.turnComplete('t1', 'answer')
    await h.settle()
    expect(await ring(h)).toEqual(DROPPED)
    expect(rec.pending.map((o) => o.key)).toEqual(['d2'])
  })

  test('a ring whose only ready answer was applied at a start (owed across a stop) is filled', async () => {
    const rec = record([out('k1', 'q1')])
    const h = await started(rec, { env: MAWS })
    expect(rec.pending).toEqual([out('k1', 'q1', { acrossStop: true })])
    expect((await ring(h)).context).toEqual([envelopeOf([out('k1', 'q1', { acrossStop: true })], 'main')])
  })

  test("B4a: 250 outcomes pending, the main conversation's envelope of dismissals alone, one of its dismissals past the view's two hundredth: the ring is dropped", async () => {
    const A1 = { id: 'a1', description: 'reviewer', type: 'general', status: 'running' }
    const rec = record([], { listed: 200 })
    const h = await started(rec, { env: MAWS, agents: [A1] })
    const theirs = Array.from({ length: 150 }, (_, i) => out(`a${i}`, `q${i + 1}`, { recipient: { agentId: 'a1' } }))
    const mine = Array.from({ length: 100 }, (_, i) => out(`d${i}`, `q${i + 151}`, { kind: 'dismiss' }))
    await answered(h, rec, ...theirs, ...mine)
    expect(rec.pending).toHaveLength(250)
    expect(rec.envelope('main', 'maws')?.keys).toEqual(mine.map((o) => o.key))
    // The view lists the subagent's 150 answers and 50 of the main conversation's dismissals; it cannot say what one envelope holds.
    expect(await ring(h)).toEqual(DROPPED)
  })

  test("B4b: at a resume, every outcome owed across a stop, dismissals enough to fill an envelope and one answer accepted after them: the main conversation's envelope leads with the answer, and the ring is filled", async () => {
    const dismissals = Array.from({ length: 200 }, (_, i) => out(`d${i}`, `q${i + 1}`, { kind: 'dismiss' }))
    const rec = record([...dismissals, out('k1', 'q201')])
    const h = await started(rec, { env: MAWS })
    const filled = await ring(h)
    expect(filled.context).toHaveLength(1)
    const text = filled.context?.[0] ?? ''
    expect(text.split('\n')[0]).toBe('[sheet v1] The human answered questions on your sheet. More follows.')
    expect(text).toContain('<sheet-delivery>{"v":1,"keys":["k1",')
  })

  test("a ring with nothing ready takes neither a notice nor a start's context that waits, which the next prompt that enters then carries; a ring before the session's start has answered is dropped", async () => {
    const OPEN = [{ id: 'q4', revision: 1, asker: { agentId: 'a1', name: 'reviewer' }, question: 'Ship it?', askedAt: '2026-11-24T10:00:00.000Z' }]
    const rec = record([], { open: OPEN })
    const h = await started(rec, { env: MAWS, agents: [{ id: 'a1', description: 'reviewer', type: 'general', status: 'running' }] })
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    expect(await ring(h)).toEqual(DROPPED)
    expect(((await h.prompt('next')) as { context?: string[] }).context).toEqual([expect.stringContaining('ended with questions still open')])

    let fails = true
    const rec2 = record()
    const h2 = await started(rec2, { env: MAWS, step: (event, n) => (event.context === 'compact' && fails ? Promise.reject(new Error('busy')) : rec2.script(event, n)) })
    await h2.classicStart('compact')
    fails = false
    await h2.tick()
    expect(await ring(h2)).toEqual(DROPPED)
    expect(((await h2.prompt('next')) as { context?: string[] }).context).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: $/)])

    const held = gated(['start'])
    const h3 = sheetOn({ env: MAWS, step: held.script })
    await h3.start()
    void h3.classicStart('startup')
    await h3.settle()
    expect(held.waiting).toHaveLength(1)
    expect(await ring(h3)).toEqual(DROPPED)
    expect(rings(h3)).toEqual(['sheet: a ring is dropped: the sheet has not started in this session'])
    held.waiting[0]?.release()
    await h3.settle()
  })

  test('the sentence under another origin enters and carries what is ready; so does the sentence with a line break after it from the composer, and the sentence in a terminal session, whatever its origin', async () => {
    const dismissal = out('d1', 'q1', { kind: 'dismiss' })
    const carried = [envelopeOf([dismissal], 'main')]
    for (const origin of [{ kind: 'scheduled-trigger' }, { kind: 'task-notification' }, { kind: 'peer' }, { kind: 'plugin', name: 'sminos' }]) {
      const rec = record()
      const h = await started(rec, { env: MAWS })
      await answered(h, rec, dismissal)
      expect(await ring(h, { origin })).toEqual({ text: RING, context: carried, origin })
    }
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, dismissal)
    expect(await h.prompt(`${RING}\n`)).toEqual({ text: `${RING}\n`, context: carried, origin: { kind: 'composer' } })
    // The plain sentence, unmarked, as the engine may hand a person's message ending in it (trimmed), or beside a block.
    for (const text of [PLAIN, `${PLAIN}\n`, `${PLAIN}\n${carried[0]}`]) {
      const plain = record()
      const p = await started(plain, { env: MAWS })
      await answered(p, plain, dismissal)
      expect(await p.prompt(text)).toEqual({ text, context: carried, origin: { kind: 'composer' } })
    }
    for (const origin of [{ kind: 'composer' }, { kind: 'peer' }]) {
      const terminal = record()
      const t = await started(terminal)
      await answered(t, terminal, dismissal)
      expect(await ring(t, { origin })).toEqual({ text: RING, context: carried, origin })
    }
  })

  test("C1: the plain sentence in each form P9's engine gave the hook (as is, after a line break, before one, and joined and trimmed beside an image), nothing ready on the sheet, enters as any prompt and is not dropped", async () => {
    // Beside an image the engine joins the message's text blocks and trims them: the hook reads the sentence as is.
    for (const text of [PLAIN, `\n${PLAIN}`, `${PLAIN}\n`]) {
      const h = await started(record(), { env: MAWS })
      expect(await h.prompt(text)).toEqual({ text, context: undefined, origin: { kind: 'composer' } })
      expect(h.logs().filter((line) => line.startsWith('sheet: a ring '))).toEqual([])
    }
  })

  test('C3: an engine that strips the mark gives the plain sentence, which is no ring: it enters with the envelope when an answer is ready, and bare when none is', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    expect(await h.prompt(PLAIN)).toEqual({ text: PLAIN, context: [envelopeOf([out('k1', 'q1')], 'main')], origin: { kind: 'composer' } })
    const empty = await started(record(), { env: MAWS })
    expect(await empty.prompt(PLAIN)).toEqual({ text: PLAIN, context: undefined, origin: { kind: 'composer' } })
    expect([...h.logs(), ...empty.logs()].filter((line) => line.startsWith('sheet: a ring '))).toEqual([])
  })

  test('a tool result carries the envelope while a turn runs, and a ring folded into that turn afterwards is dropped', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    expect(contextOf(await h.call('Read', {}))).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    expect(await ring(h, { turnId: 't1' })).toEqual(DROPPED)
    expect(rings(h)).toEqual(["sheet: a ring is dropped: the main conversation's envelope is on a route already"])
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: envelopeOf([out('k1', 'q1')], 'main') })
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
  })

  test('a sheet longer than one envelope: each ring carries what fits and says more follows, the next carries the rest, nothing twice', async () => {
    const outs = ['k1', 'k2', 'k3', 'k4', 'k5'].map((key, i) => out(key, `q${i + 1}`))
    const rec = record([], { per: 2 })
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, ...outs)
    const carried: string[] = []
    for (const [part, more] of [[outs.slice(0, 2), true], [outs.slice(2, 4), true], [outs.slice(4), false]] as const) {
      const envelope = envelopeOf(part, 'main', more)
      expect((await ring(h)).context).toEqual([envelope])
      await h.append({ door: 'hook-context', origin: PROMPT_ROW, text: envelope })
      await h.settle()
      carried.push(...part.map((o) => o.key))
    }
    expect(await ring(h)).toEqual(DROPPED)
    expect(carried).toEqual(['k1', 'k2', 'k3', 'k4', 'k5'])
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1', 'k2'], ['k3', 'k4'], ['k5']])
  })
})

describe("MAWS's ring: what it leaves, and a Stop on its own turn (MAWS's C5, F33; A.d, A.e)", () => {
  const ring = (h: { prompt: (text: string, over?: Record<string, unknown>) => Promise<unknown> }) => h.prompt(RING) as Promise<{ context?: string[]; drop?: string }>
  const atPrompt = (text: string) => [{ role: 'user', content: [{ type: 'text', text: `<system-reminder>\nprompt.submit hook additional context: ${text}\n</system-reminder>` }] }]

  test('a ring orders no step, dropped or filled, though a drain is owed; a prompt that is not a ring orders it', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    // The inbox has grown past the view: any check now would drain.
    h.files.set(`${HOME}/sheet/${S1}/inbox.jsonl`, '{}\n')
    const ordered = h.steps.length
    expect((await ring(h)).context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    expect(await ring(h)).toEqual({ drop: RING_DROP })
    await h.settle()
    expect(h.steps).toHaveLength(ordered)
    await h.prompt('a person writes')
    await h.settle()
    expect(steps(h, 'drain').length).toBeGreaterThan(0)
    expect(h.steps.length).toBeGreaterThan(ordered)
  })

  test('W4a under runner `maws`: an answer landed, then a /clear, then a ring: the ring is dropped and the answer is not delivered again', async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    const envelope = envelopeOf([out('k1', 'q1')], 'main')
    expect((await ring(h)).context).toEqual([envelope])
    await h.append({ door: 'hook-context', origin: PROMPT_ROW, text: envelope })
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
    await h.sessionEnd('clear')
    await h.classicStart('clear', S2)
    await h.settle()
    expect(h.steps.some((s) => s.event === 'start' && s.session === S2)).toBe(true)
    expect(await ring(h)).toEqual({ drop: RING_DROP })
    expect(((await h.prompt('next')) as { context?: string[] }).context).toBeUndefined()
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([])
    expect(steps(h, 'landed')).toHaveLength(1)
  })

  test("a Stop on the ring's own turn: the envelope the conversation holds at the turn's end lands there", async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    const envelope = envelopeOf([out('k1', 'q1')], 'main')
    expect((await ring(h)).context).toEqual([envelope])
    await h.turnStart('t1')
    h.converse({ rows: [], api: atPrompt(envelope) })
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k1']])
    expect(rec.pending).toEqual([])
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toBeUndefined()
    expect(h.submits).toEqual([])
  })

  test("a Stop on the ring's own turn: an envelope the conversation does not hold at the turn's end rides the person's next message, once", async () => {
    const rec = record()
    const h = await started(rec, { env: MAWS })
    await answered(h, rec, out('k1', 'q1'))
    const envelope = envelopeOf([out('k1', 'q1')], 'main')
    expect((await ring(h)).context).toEqual([envelope])
    await h.turnStart('t1')
    h.converse({ rows: [], api: [] })
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    await h.hop()
    expect(steps(h, 'landed')).toEqual([])
    expect(h.submits).toEqual([])
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([envelope])
    expect(((await h.prompt('and then')) as { context?: string[] }).context).toBeUndefined()
  })
})

describe("a stopped turn (MAWS's C5, F34): the Stop is a time, and only an answer accepted after it opens the idle route, until a prompt enters", () => {
  const A1 = { id: 'a1', description: 'reviewer', type: 'general', status: 'running' }

  /** A terminal session (or `over`'s) whose main turn t1 the person stopped while answer k1, accepted before, was pending. */
  async function stopped(over: Parameters<typeof sheetOn>[0] = {}, rec = record()) {
    const h = await started(rec, over)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'))
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    return { h, rec }
  }

  test('the Stop is kept for its session, in the state a reload reads', async () => {
    const { h } = await stopped()
    const kept = h.kept.get('sminos.sheet') as { session: string; stoppedAt?: string }
    expect(kept.session).toBe(S1)
    expect(kept.stoppedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    expect(Date.parse(kept.stoppedAt ?? '')).toBeGreaterThan(Date.parse(BEFORE))
  })

  test('after it, an answer accepted after the Stop wakes a terminal session, its envelope carrying the held answer too; a dismissal, a `landed` retry and a held answer alone open nothing', async () => {
    let fails = true
    const rec = record()
    const h = await started(rec, { step: (event, n) => (event.event === 'landed' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    await h.turnStart('t1')
    await answered(h, rec, out('k0', 'q0'))
    expect(contextOf(await h.call('Read', {}))).toHaveLength(1)
    await h.append({ door: 'hook-context', origin: RESULT_ROW, text: envelopeOf([out('k0', 'q0')], 'main') })
    await h.settle()
    await answered(h, rec, out('k1', 'q1'))
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    fails = false
    await h.tick()
    expect(rec.pending.map((o) => o.key)).toEqual(['k1'])
    await answered(h, rec, out('d2', 'q2', { kind: 'dismiss', acceptedAt: AFTER }))
    await h.hop()
    expect(h.submits).toEqual([])
    await answered(h, rec, out('k3', 'q3', { acceptedAt: AFTER }))
    await h.hop()
    expect(h.submits).toEqual([envelopeOf([out('k1', 'q1'), out('k3', 'q3'), out('d2', 'q2', { kind: 'dismiss' })], 'main')])
  })

  test("E1: a running subagent's answer whose send is unanswered at the Stop, then rerouted to the main conversation, opens no idle route", async () => {
    let refuse: (value: unknown) => void = () => {}
    const sending = new Promise((resolve) => (refuse = resolve))
    const rec = record()
    const h = await started(rec, { agents: [A1], send: () => sending })
    await h.turnStart('t1')
    await answered(h, rec, out('a1k', 'q4', { recipient: { agentId: 'a1' } }))
    await h.hop()
    expect(h.sends.map((s) => s.agentId)).toEqual(['a1'])
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    refuse({ isDelivered: false, reason: 'gone' })
    await h.settle()
    await h.hop()
    expect(steps(h, 'reroute').map((s) => s.keys)).toEqual([['a1k']])
    expect(rec.pending.map((o) => [o.key, o.recipient])).toEqual([['a1k', 'main']])
    expect(h.submits).toEqual([])
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([envelopeOf([out('a1k', 'q4')], 'main')])
  })

  test("E2: a step ordered before the Stop whose reply comes after it and shows an answer accepted after it (a late reader): that answer wakes the session once, the held one with it", async () => {
    let gate = false
    const drains = gated(['drain'])
    const rec = record()
    const h = await started(rec, { step: (event, n) => (gate && event.event === 'drain' ? drains.script(event, n) : rec.script(event, n)) })
    await h.turnStart('t1')
    gate = true
    rec.queued.push(out('k1', 'q1'))
    void sheetNudge(['k1'])
    await h.settle()
    expect(drains.waiting).toHaveLength(1)
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    // It took the lock after a step of the Stop's side applied k2: its reply shows both.
    rec.queued.push(out('k2', 'q2', { acceptedAt: AFTER }))
    const reply = rec.script(drains.waiting[0]!.event, 0) as string
    drains.waiting.splice(0).forEach((w) => w.release(reply))
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main')])
    gate = false
    await h.tick()
    expect(h.submits).toHaveLength(1)
  })

  test("E3: a step ordered before the Stop that commits an answer and loses its reply: the retry finds it pending and opens no idle route", async () => {
    let gate = false
    const drains = gated(['drain'])
    const rec = record()
    const h = await started(rec, { step: (event, n) => (gate && event.event === 'drain' ? drains.script(event, n) : rec.script(event, n)) })
    await h.turnStart('t1')
    gate = true
    rec.queued.push(out('k1', 'q1'))
    void sheetNudge(['k1'])
    await h.settle()
    // Committed, then its reply is lost.
    rec.script(drains.waiting[0]!.event, 0)
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    drains.waiting.splice(0).forEach((w) => w.release(new Error('the step answered no JSON')))
    gate = false
    await h.settle()
    await h.tick()
    await h.hop()
    expect(rec.pending.map((o) => o.key)).toEqual(['k1'])
    expect(h.submits).toEqual([])
  })

  test('E4: stopped answers that fill two envelopes: the prompt that enters takes the first and ends the hold, and once that turn ends with its answer the second goes by the idle route', async () => {
    const rec = record([], { per: 1 })
    const h = await started(rec)
    await h.turnStart('t1')
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2'))
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    const first = envelopeOf([out('k1', 'q1')], 'main', true)
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([first])
    expect((h.kept.get('sminos.sheet') as { stoppedAt?: unknown }).stoppedAt).toBeUndefined()
    await h.turnStart('t2')
    await h.append({ door: 'hook-context', origin: PROMPT_ROW, text: first })
    await h.settle()
    await h.turnComplete('t2', 'answer')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([envelopeOf([out('k2', 'q2')], 'main')])
  })

  test('a prompt that is dropped beneath does not end the hold; one that enters does', async () => {
    const { h, rec } = await stopped()
    await h.prompt('dropped', {}, async () => ({ drop: 'a hook beneath' }))
    expect((h.kept.get('sminos.sheet') as { stoppedAt?: unknown }).stoppedAt).toBeDefined()
    await answered(h, rec, out('d2', 'q2', { kind: 'dismiss' }))
    await h.hop()
    expect(h.submits).toEqual([])
  })

  test('E5: a reload after the Stop keeps it: the reloaded module drains the record and opens no idle route, and an answer accepted after the Stop still wakes it', async () => {
    const { h, rec } = await stopped()
    const reloaded = sheetOn({ kept: h.kept, step: rec.script })
    await reloaded.start()
    await reloaded.settle()
    await reloaded.hop()
    expect(steps(reloaded, 'drain').length).toBeGreaterThan(0)
    expect(reloaded.submits).toEqual([])
    await answered(reloaded, rec, out('k2', 'q2', { acceptedAt: AFTER }))
    await reloaded.hop()
    expect(reloaded.submits).toEqual([envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main')])
  })

  test('E5: a /clear and a fork start without the hold: an answer accepted before the Stop wakes the new session', async () => {
    for (const source of ['clear', 'fork']) {
      const rec = record()
      const h = await started(rec)
      await h.turnStart('t1')
      await h.turnComplete('t1', 'aborted')
      await h.settle()
      if (source === 'clear') await h.sessionEnd('clear')
      await h.classicStart(source, S2)
      await h.settle()
      await h.hop()
      await answered(h, rec, out('k1', 'q1'))
      await h.hop()
      expect(h.submits).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
    }
  })

  test("an answer whose step was ordered before the Stop and answered after it opens none, out of reply order as well; one accepted after the Stop does, its envelope holding the stopped answer too", async () => {
    let gate = false
    const drains = gated(['drain'])
    const rec = record()
    const h = await started(rec, { step: (event, n) => (gate && event.event === 'drain' ? drains.script(event, n) : rec.script(event, n)) })
    await h.turnStart('t1')
    await answered(h, rec, out('k0', 'q0'))
    const k0 = envelopeOf([out('k0', 'q0')], 'main')
    expect(contextOf(await h.call('Read', {}))).toEqual([k0])
    gate = true
    rec.queued.push(out('k1', 'q1'))
    void sheetNudge(['k1'])
    await h.settle()
    const committed = rec.script(drains.waiting[0]!.event, 0) as string
    // The Stop; a `landed` step ordered after it answers first, its view holding k1.
    h.converse({ rows: [], api: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'x', content: [{ type: 'text', text: 'read' }, { type: 'text', text: `<system-reminder>\ntool.call hook additional context: ${k0}\n</system-reminder>` }] }] }] })
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k0']])
    await h.hop()
    expect(h.submits).toEqual([])
    drains.waiting.splice(0).forEach((w) => w.release(committed))
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    gate = false
    await answered(h, rec, out('k2', 'q2', { acceptedAt: AFTER }))
    await h.hop()
    expect(h.submits).toEqual([envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main')])
  })

  test('an aborted end read after a later main turn has begun (a message preempted it) sets no Stop', async () => {
    const rec = record()
    const h = await started(rec)
    await h.turnStart('t1')
    await h.turnStart('t2')
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    expect((h.kept.get('sminos.sheet') as { stoppedAt?: unknown }).stoppedAt).toBeUndefined()
    await h.turnComplete('t2', 'answer')
    await h.settle()
    await answered(h, rec, out('k1', 'q1'))
    await h.hop()
    expect(h.submits).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
  })

  test("the mod's own idle prompt entering ends the hold, as a prompt that enters does", async () => {
    const { h, rec } = await stopped()
    await answered(h, rec, out('k2', 'q2', { acceptedAt: AFTER }))
    await h.hop()
    expect(h.submits).toHaveLength(1)
    expect((h.kept.get('sminos.sheet') as { stoppedAt?: unknown }).stoppedAt).toBeUndefined()
  })

  test('an idle reservation made before a turn that ends aborted before the hop submits nothing; what it held rides the next prompt', async () => {
    const rec = record()
    const h = await started(rec)
    await answered(h, rec, out('k1', 'q1'))
    await h.turnStart('t1')
    await h.turnComplete('t1', 'aborted')
    await h.settle()
    await h.hop()
    expect(h.submits).toEqual([])
    expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
  })

  test('in both runners a prompt that enters carries everything pending at the Stop, a dismissal sent since with it; so does the prompt of a message that preempted the turn; under runner `maws` no idle submit, and a ring is filled', async () => {
    for (const env of [{}, MAWS]) {
      const { h, rec } = await stopped({ env })
      await answered(h, rec, out('d2', 'q2', { kind: 'dismiss' }))
      await h.hop()
      expect(h.submits).toEqual([])
      expect(((await h.prompt('go on')) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1'), out('d2', 'q2', { kind: 'dismiss' })], 'main')])

      const rec2 = record()
      const h2 = await started(rec2, { env })
      await h2.turnStart('t1')
      await answered(h2, rec2, out('k1', 'q1'))
      expect(((await h2.prompt('instead', { turnId: 't1' })) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
      await h2.turnComplete('t1', 'aborted')
      await h2.settle()
      await h2.hop()
      expect(h2.submits).toEqual([])
    }
    const { h, rec } = await stopped({ env: MAWS })
    await answered(h, rec, out('k2', 'q2', { acceptedAt: AFTER }))
    await h.hop()
    expect(h.submits).toEqual([])
    expect(((await h.prompt(RING)) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1'), out('k2', 'q2')], 'main')])
  })
})

describe("a ring while a reload's session.start has not yet restored the choice (MAWS's C5, F33)", () => {
  test('E6: a marked ring from the composer in that interval is dropped at once, without awaiting the restore; a prompt of other words enters', async () => {
    const rec = record()
    const first = await started(rec, { env: MAWS })
    await answered(first, rec, out('k1', 'q1'))
    const reloaded = sheetOn({ env: MAWS, kept: first.kept, step: rec.script })
    let restore: () => void = () => {}
    const restoring = new Promise<void>((resolve) => (restore = resolve))
    const read = reloaded.engine.state.get
    ;(reloaded.engine.state as { get: unknown }).get = async (ref: unknown) => {
      await restoring
      return (read as (r: unknown) => unknown)(ref)
    }
    const starting = reloaded.start()
    await reloaded.settle()
    expect(await reloaded.prompt(RING)).toEqual({ drop: RING_DROP })
    expect(await reloaded.prompt('a person writes')).toEqual({ text: 'a person writes', context: undefined, origin: { kind: 'composer' } })
    restore()
    await starting
    await reloaded.settle()
    expect(reloaded.logs()).toContain('sheet: a ring is dropped: the choice is not restored yet')
    expect(((await reloaded.prompt(RING)) as { context?: string[] }).context).toEqual([envelopeOf([out('k1', 'q1')], 'main')])
  })
})
