import { describe, expect, test, tier } from 'claude-code/testing'

import { ASYNC_RESULT } from '../../hooks/mods/ask'
import { SHEET_TOOL } from '../../hooks/mods/sheet-model'
import type { View } from '../../hooks/mods/sheet-model'
import { HOME, S1, gated, harness, linesOf, ok, sheetOn } from './sheet-harness'
import type { StepEvent } from './sheet-harness'

tier('user')

/**
 * The terminal's drawing and the import of today's asks (plan
 * docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, M5; the
 * composite's §8.3, §9): the line above the prompt, a call's row and its
 * receipts, and a resume's open asks of today's tool staged for its start.
 */

const LINK = `http://sheet.localhost:47590/s/${S1}`
const NOW = Date.parse('2026-11-24T10:00:30.000Z')

/** A sheet session whose start answered with `over` as its view. */
async function startedWith(over: Partial<View>, options: Parameters<typeof sheetOn>[0] = {}) {
  const h = sheetOn({ step: (event, n) => ok(n, {}, over), ...options })
  await h.ready()
  return h
}

/** The band as the engine draws it: the sheet's line hook outside the ask's (register.tsx). */
async function band(h: ReturnType<typeof harness>, props: Record<string, unknown> = { hasSurvey: false }) {
  return h.render('AbovePrompt', props)
}

const open = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `q${i + 1}`, revision: 1, asker: 'main' as const, question: `Q${i + 1}?`, askedAt: '2026-11-24T10:00:00.000Z' }))

describe('the line above the prompt (§8.3)', () => {
  test('open questions and the link, above what the hooks beneath drew; none while a survey holds the band, or with nothing open or owed', async () => {
    const h = await startedWith({ open: open(3) })
    const drawn = await band(h)
    expect(linesOf(drawn)).toEqual([`3 open questions · ${LINK}`])
    expect((drawn as { children: unknown[] }).children.at(-1)).toBe('beneath')
    expect(await band(h, { hasSurvey: true })).toBe('beneath')
    const empty = await startedWith({})
    expect(await band(empty)).toBe('beneath')
  })

  test('with no surface the page is unreachable and the command reads them; answers owed across a stop go with the next message', async () => {
    expect(linesOf(await band(await startedWith({ open: open(3), surface: null })))).toEqual(['3 open questions · the page is unreachable: sminos sheet show 5eed0000'])
    expect(linesOf(await band(await startedWith({ open: open(3), owedAcrossStop: 2 })))).toEqual([`3 open questions · ${LINK} · 2 answers go with your next message`])
    expect(linesOf(await band(await startedWith({ owedAcrossStop: 2 })))).toEqual(['2 answers go with your next message'])
  })

  test("not under the sheet, or in a MAWS-run session, the sheet draws no line", async () => {
    const today = harness()
    await today.ready()
    expect(await band(today)).toBe('beneath')
    const maws = await startedWith({ open: open(3) }, { env: { MAWS_QUESTION_SHEET: S1 } })
    expect(await band(maws)).toBe('beneath')
  })

  test('between steps every third tick reads the registrations by age alone: a stale one makes the page unreachable, a fresh one links again, each change redrawn', async () => {
    const reg = (heartbeatAt: string) => JSON.stringify({ v: 1, name: 'standin', pid: 99999, url: 'http://sheet.localhost:47590/', reach: 'local', heartbeatAt })
    const dir = `${HOME}/sheet/surfaces`
    const h = await startedWith({ open: open(2) }, { files: { [`${dir}/standin.json`]: reg('2026-11-24T09:59:00.000Z'), [`${dir}/.standin.tmp`]: 'half' }, now: NOW })
    await h.tick()
    await h.tick()
    expect(h.calls.filter((c) => c.op === 'fs.list')).toEqual([])
    const before = h.calls.length
    await h.tick()
    expect(h.calls.filter((c) => c.op === 'fs.list')).toHaveLength(1)
    expect(linesOf(await band(h))).toEqual(['2 open questions · the page is unreachable: sminos sheet show 5eed0000'])
    expect(h.calls.slice(before).some((c) => c.op === 'ui.invalidate' && c.args === 'ui.render')).toBe(true)
    h.files.set(`${dir}/standin.json`, reg('2026-11-24T10:00:20.000Z'))
    for (let i = 0; i < 3; i++) await h.tick()
    expect(linesOf(await band(h))).toEqual([`2 open questions · ${LINK}`])
  })
})

describe("a call's row (§8.3, I11)", () => {
  const INPUT = {
    ask: [
      { question: 'The login fails on Safari. Which auth method should it use?', header: 'Auth method', options: [{ label: 'OAuth' }, { label: 'Passkeys' }] },
      { question: 'What should the empty state say?' },
    ],
  }
  const row = (over: Record<string, unknown> = {}) => ({ tool: SHEET_TOOL, tool_use_id: 'toolu_1', input: INPUT, output: 'Added q1, q2.', isRunning: false, isErrored: false, isInterrupted: false, ...over })

  test("the engine's head, then one line a question; after the outcome, its receipt from the view; the result block stands aside", async () => {
    const h = await startedWith({ open: [{ id: 'q2', revision: 1, asker: 'main', question: 'What?', askedAt: '2026-11-24T10:00:00.000Z' }], closed: { q1: { how: 'answered', revision: 1, header: 'Auth method', receipt: 'Passkeys' } } })
    const drawn = await h.render('ToolUse', row())
    expect((drawn as { children: unknown[] }).children[0]).toBe('beneath')
    expect(linesOf(drawn)).toEqual(['  ⎿  ', 'q1 Auth method → Passkeys', 'q2 — What should the empty state say?'])
    expect(linesOf(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 'toolu_1', output: 'Added q1, q2.', isErrored: false }))).toEqual([])
    expect(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 'toolu_1', output: 'Added q1, q2.', isErrored: false })).toMatchObject({ type: 'Box' })
    // The view holds both: no read of the conversation for them.
    expect(h.calls.filter((c) => c.op === 'session.messages')).toEqual([])
  })

  test('a call still running, refused whole, cut, unfolded (ctrl+o), or of another tool is the engine\'s; so is a result of none of the three forms', async () => {
    const h = await startedWith({})
    for (const over of [{ isRunning: true, output: undefined }, { isErrored: true, output: 'InputValidationError: …' }, { isInterrupted: true }, { isExpanded: true }, { tool: 'Read' }, { output: 'The question could not be asked: x' }]) {
      expect(await h.render('ToolUse', row(over))).toBe('beneath')
    }
    expect(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 't', output: 'InputValidationError: x', isErrored: true })).toBe('beneath')
    expect(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 't', output: 'Added q1.', isErrored: false, isExpanded: true })).toBe('beneath')
  })

  test('the stored result as content blocks reads the same', async () => {
    const h = await startedWith({})
    expect(linesOf(await h.render('ToolUse', row({ output: [{ type: 'text', text: 'Nothing done.\nNot done: q3 is not open (withdrawn at 09:12).' }] })))).toEqual(['  ⎿  ', 'Nothing done.'])
  })

  test("with no record (today's tool here), its receipts come from the blocks the conversation holds: one read, made when a row first needs it, then redrawn; a question neither knows is its line bare", async () => {
    const block = `<sheet-delivery>${JSON.stringify({ v: 1, keys: ['k1'], answered: [{ id: 'q1', revision: 1, picks: [2], text: '', images: [] }], dismissed: [] })}</sheet-delivery>`
    const quoted = `<sheet-delivery>${JSON.stringify({ v: 1, keys: ['k2'], answered: [], dismissed: ['q2'] })}</sheet-delivery>`
    const h = harness({
      messages: {
        rows: [],
        api: [
          { role: 'user', content: [{ type: 'text', text: `<system-reminder>\ntool.call hook additional context: [sheet v1] The human answered questions on your sheet.\n${block}\n</system-reminder>` }] },
          // The human quoting a dismissal names nothing.
          { role: 'user', content: quoted },
        ],
      },
    })
    await h.ready('resume')
    expect(linesOf(await h.render('ToolUse', row()))).toEqual(['  ⎿  ', 'q1 Auth method — Which auth method should it use?', 'q2 — What should the empty state say?'])
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'session.messages')).toHaveLength(1)
    expect(h.calls.some((c) => c.op === 'ui.invalidate' && c.args === 'ui.render')).toBe(true)
    expect(linesOf(await h.render('ToolUse', row()))).toEqual(['  ⎿  ', 'q1 Auth method → Passkeys', 'q2 — What should the empty state say?'])
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'session.messages')).toHaveLength(1)
  })

  test("a conversation not readable yet (a copy's first start, C0's P5) is read once more after a turn has started, and never again", async () => {
    const h = harness()
    await h.ready('fork')
    // The reads from here on are the rows' (today's ask read the copy's conversation at its start).
    const reads = () => h.calls.slice(before).filter((c) => c.op === 'session.messages')
    const before = h.calls.length
    await h.render('ToolUse', row())
    await h.settle()
    await h.render('ToolUse', row())
    await h.settle()
    expect(reads()).toHaveLength(1)
    await h.turnStart('t1')
    h.converse({ rows: [], api: [] })
    await h.render('ToolUse', row())
    await h.settle()
    expect(reads()).toHaveLength(2)
    await h.turnStart('t2')
    await h.render('ToolUse', row())
    await h.settle()
    expect(reads()).toHaveLength(2)
  })

  test('a row drawn before the session started reads the conversation once the session has', async () => {
    const h = harness({ messages: { rows: [], api: [] } })
    await h.render('ToolUse', row())
    expect(h.calls.filter((c) => c.op === 'session.messages')).toEqual([])
    await h.ready('resume')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'session.messages')).toHaveLength(1)
  })

  test('a block a route delivered, as the landing hook sees it, is a receipt where the view does not hold the question', async () => {
    const h = await startedWith({ seq: 1 })
    const block = `<sheet-delivery>${JSON.stringify({ v: 1, keys: ['k1'], answered: [], dismissed: ['q1'] })}</sheet-delivery>`
    await h.append({ door: 'hook-context', origin: { kind: 'plugin', event: 'tool.call' }, text: `<system-reminder>\ntool.call hook additional context: [sheet v1] The human dismissed questions on your sheet; no answer will come for them.\n${block}\n</system-reminder>` })
    await h.settle()
    expect(linesOf(await h.render('ToolUse', row()))[1]).toBe('q1 Auth method · Dismissed')
  })
})

describe("a resume's asks of today's tool, imported once (§9; M5)", () => {
  const question = { question: 'Which port?', header: 'Port', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] }
  /** A transcript with an open async ask of today's tool (`t-open`, called at `at`) and an answered one. */
  const transcript = (at = '2026-11-20T08:00:00.000Z') =>
    [
      { type: 'assistant', timestamp: at, message: { role: 'assistant', content: [{ type: 'tool_use', id: 't-open', name: SHEET_TOOL, input: { questions: [question], async: true } }] } },
      { type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't-open', content: ASYNC_RESULT }] } },
    ]
      .map((row, i) => JSON.stringify({ parentUuid: i === 0 ? null : `u${i - 1}`, uuid: `u${i}`, ...row }))
      .join('\n') + '\n'
  const startOf = (h: { steps: StepEvent[] }) => h.steps.find((step) => step.event === 'start')?.start as { nonce: string; source: string; today?: { definite: boolean; asks: { file: string }[] } }

  test("a resume under the sheet: the ask's read of the transcript goes with the start, each open ask staged as a file of its own, its call's time kept", async () => {
    const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript() } })
    await h.ready('resume')
    const start = startOf(h)
    expect(start.today).toEqual({ definite: true, asks: [{ file: `start-${start.nonce}/ask-1.json` }] })
    expect(h.staged(`${HOME}/sheet/.staging/${S1}/start-${start.nonce}/ask-1.json`)).toEqual({ callId: 't-open', askedAt: '2026-11-20T08:00:00.000Z', questions: [question] })
  })

  test('a call with no time of its own is asked now', async () => {
    const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript('yesterday') }, now: NOW })
    await h.ready('resume')
    const start = startOf(h)
    expect(h.staged(`${HOME}/sheet/.staging/${S1}/start-${start.nonce}/ask-1.json`)).toMatchObject({ askedAt: '2026-11-24T10:00:30.000Z' })
  })

  test('a read that was not definite (a search that failed, or was cut) imports nothing and says so; the next start reads again', async () => {
    for (const exec of [() => ({ exitCode: 2, stdout: '' }), () => ({ exitCode: 0, stdout: transcript(), isStdoutTruncated: true })]) {
      // No file to read whole: the ask searches.
      const h = sheetOn({ exec })
      await h.ready('resume')
      expect(startOf(h).today).toEqual({ definite: false, asks: [] })
    }
    // A search that ran and found none is definite.
    const none = sheetOn({ exec: () => ({ exitCode: 1, stdout: '' }) })
    await none.ready('resume')
    expect(startOf(none).today).toEqual({ definite: true, asks: [] })
  })

  test('a copy, a startup and a /clear send no asks: a fork\'s first start records that it never imports', async () => {
    for (const source of ['fork', 'startup', 'clear']) {
      const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript() } })
      await h.ready(source)
      expect(startOf(h).today).toBeUndefined()
    }
  })

  test("not under the sheet, today's tool takes its asks up as it does today, and the sheet stages nothing", async () => {
    const h = harness({ files: { [`/t/${S1}.jsonl`]: transcript() } })
    await h.ready('resume')
    expect(h.steps).toEqual([])
    expect([...h.files.keys()].filter((path) => path.includes('/.staging/'))).toEqual([])
  })

  test('a start that refuses the asks it was given (a staged file gone) is ordered again without them', async () => {
    const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript() }, step: (event, n) => (event.event === 'start' && (event.start as { today?: { asks: unknown[] } }).today?.asks.length ? JSON.stringify({ ok: false, code: 'bad-event', error: 'a staged ask is missing' }) : ok(n)) })
    await h.ready('resume')
    await h.tick()
    const starts = h.steps.filter((step) => step.event === 'start').map((step) => step.start as { nonce: string; today?: { definite: boolean; asks: unknown[] } })
    expect(starts).toHaveLength(2)
    expect(starts[1]?.nonce).toBe(starts[0]?.nonce)
    expect(starts[1]?.today).toEqual({ definite: false, asks: [] })
    expect((h.kept.get('sminos.sheet') as { started?: string }).started).toBe(S1)
  })

  test("a launch's SessionStart before the choice: the start waits for the ask's read, bounded, and session.start never waits on it", async () => {
    const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript() } })
    const engine = h.engine as unknown as { fs: { read: (path: string) => Promise<string> } }
    let releaseRead: () => void = () => {}
    const read = engine.fs.read
    let isHeld = false
    engine.fs.read = async (path) => {
      if (path === `/t/${S1}.jsonl` && !isHeld) {
        isHeld = true
        await new Promise<void>((r) => (releaseRead = r))
      }
      return read(path)
    }
    // The SessionStart comes first; the ask's read of the transcript is held.
    const classic = h.classicStart('resume')
    await h.settle()
    await h.start()
    await h.settle()
    expect(h.steps.filter((step) => step.event === 'start')).toEqual([])
    // The bound runs out (the timer's hop) before the read: nothing imported at this start.
    await h.hop()
    await h.settle()
    expect(startOf(h).today).toEqual({ definite: false, asks: [] })
    releaseRead()
    await classic
  })

  test('the same, the read done in time: the start imports it', async () => {
    const g = gated(['start'])
    const h = sheetOn({ files: { [`/t/${S1}.jsonl`]: transcript() }, step: g.script })
    const classic = h.classicStart('resume')
    await h.settle()
    await h.start()
    await h.settle()
    await classic
    await h.settle()
    expect((g.waiting[0]?.event.start as { today?: { definite: boolean; asks: unknown[] } }).today).toMatchObject({ definite: true, asks: [{}] })
    g.waiting[0]?.release()
  })
})

describe('the row with no sheet chosen (I11: the sheet draws its form in every session)', () => {
  test('a session whose choice is none draws the lines too, from the input and the result alone', async () => {
    const h = harness({ env: { MAWS_NATIVE_TO_HUMAN: '1' } })
    await h.start()
    const drawn = await h.render('ToolUse', { tool: SHEET_TOOL, tool_use_id: 't', input: { withdraw: ['q4'] }, output: 'Withdrew q4.', isRunning: false, isErrored: false, isInterrupted: false })
    expect(linesOf(drawn)).toEqual(['  ⎿  ', 'q4 · Withdrawn'])
  })
})
