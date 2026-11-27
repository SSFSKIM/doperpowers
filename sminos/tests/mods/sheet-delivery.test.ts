import { describe, expect, test, tier } from 'claude-code/testing'

import type { Recipient } from '../../hooks/mods/sheet-model'
import { sheetNudge } from '../../hooks/mods/sheet'
import { HOME, MODEL, S1, S2, ok, sheetOn } from './sheet-harness'
import type { StepEvent, StepScript } from './sheet-harness'

tier('user')

/**
 * Delivery in a terminal session (plan
 * docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I9 and M4):
 * the routes, landing, a start's search and context, a compaction's context,
 * subagents. The record is a fake of the step's that keeps what is pending
 * and packs a recipient's envelope from it, the wakers first, as the
 * composer does (I7); the composer's own packing is the step's tests'.
 */

const PLUGIN_ROW = { kind: 'plugin', name: 'sminos' }
const RESULT_ROW = { kind: 'plugin', event: 'tool.call' }
const PROMPT_ROW = { kind: 'plugin', event: 'prompt.submit' }

type Out = { key: string; id: string; kind: 'answer' | 'dismiss'; recipient: Recipient; acrossStop: boolean }

/** An answer (or dismissal) pending for `recipient`. */
const out = (key: string, id: string, over: Partial<Out> = {}): Out => ({ key, id, kind: 'answer', recipient: 'main', acrossStop: false, ...over })

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

const same = (a: Recipient, b: Recipient) => (a === 'main' ? b === 'main' : b !== 'main' && a.agentId === b.agentId)

/**
 * A record as the step keeps it, for the mod's side: every step drains what
 * the test queued, applies `landed`, `reroute`, a start and the `agents`
 * rule, and answers a view whose `ready` packs each recipient's envelope, at
 * most `per` outcomes, the wakers first.
 */
function record(initial: readonly Out[] = [], options: { per?: number; context?: (event: StepEvent) => string | undefined; open?: unknown[] } = {}) {
  const pending: Out[] = initial.map((o) => ({ ...o }))
  const queued: Out[] = []
  let seq = 0
  const per = options.per ?? 200
  const envelope = (recipient: Recipient) => {
    const mine = pending.filter((o) => same(o.recipient, recipient))
    if (mine.length === 0) return undefined
    const packed = [...mine.filter(wakes), ...mine.filter((o) => !wakes(o))].slice(0, per)
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
    const recipients: Recipient[] = event.runner === 'maws' ? [] : ['main']
    pending.forEach((o) => o.recipient !== 'main' && !recipients.some((r) => same(r, o.recipient)) && recipients.push(o.recipient))
    const ready = recipients.map(envelope).filter((e) => e !== undefined)
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
        pending: pending.map((o) => ({ key: o.key, id: o.id, kind: o.kind, recipient: o.recipient, taken: o.recipient !== 'main', acrossStop: o.acrossStop })),
        pendingCount: pending.length,
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

  test('in a MAWS-run session no route of the main conversation opens and no row lands; a running subagent is still sent its envelope', async () => {
    const rec = record()
    const h = await started(rec, { env: { MAWS_QUESTION_SHEET: S1 }, agents: [{ id: 'a1', description: 'reviewer', type: 'general', status: 'running' }] })
    await answered(h, rec, out('k1', 'q1'), out('k2', 'q2', { recipient: { agentId: 'a1' } }))
    await h.hop()
    expect(h.submits).toEqual([])
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([])
    expect(((await h.prompt('steer')) as { context?: string[] }).context).toBeUndefined()
    await h.append({ door: 'prompt', origin: PLUGIN_ROW, text: envelopeOf([out('k1', 'q1')], 'main') })
    await h.settle()
    expect(h.sends.map((s) => s.agentId)).toEqual(['a1'])
    expect(steps(h, 'landed').map((s) => s.keys)).toEqual([['k2']])
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

  test('a MAWS-run session searches nothing at its start: there only a `delivered` line moves an outcome (§5.4)', async () => {
    const rec = record([out('k1', 'q1')])
    const h = sheetOn({ step: rec.script, env: { MAWS_QUESTION_SHEET: S1 }, exec: () => Promise.reject(new Error('searched')) })
    await h.start()
    const answered = (await h.classicStart('resume')) as { additionalContext?: string[] }
    expect(h.steps.map((s) => s.event)).toEqual(['start'])
    expect(answered.additionalContext).toEqual(['[sheet v1] context 1: k1'])
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

  test('in a MAWS-run session the context with no answer at the SessionStart rides the next prompt alone: no answer goes by a route there', async () => {
    let fails = true
    const rec = record()
    const h = await started(rec, { env: { MAWS_QUESTION_SHEET: S1 }, step: (event, n) => (event.context === 'compact' && fails ? Promise.reject(new Error('busy')) : rec.script(event, n)) })
    await h.classicStart('compact')
    fails = false
    await h.tick()
    await answered(h, rec, out('k1', 'q1'))
    await h.turnStart('t1')
    expect(contextOf(await h.call('Read', {}))).toEqual([])
    const entered = (await h.prompt('steer', { turnId: 't1' })) as { context?: string[] }
    expect(entered.context).toEqual([expect.stringMatching(/^\[sheet v1\] context \d+: $/)])
    expect(((await h.prompt('again', { turnId: 't1' })) as { context?: string[] }).context).toBeUndefined()
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
})
